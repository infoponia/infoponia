# Vistas de la pestaña «Reglas de actuación» (IOT-06, paso 5; docs/casos_de_uso/iot/reglas_de_actuacion.md, «Cómo se aplica» y «Pantallas»; ``reglas``, ``rglText``, ``ultB``, ``rglTags``,
# ``rgl-new``, ``rgl-mod`` y ``rbaj:<id>`` del prototipo): la lista con sus filtros (IOT-CNS-RGL, reglas 2 y 3), la ficha con el historial de comandos (regla 4), el formulario de alta y de
# modificación con la frase de vista previa (IOT-ALT-RGL e IOT-MOD-RGL), la ventana de baja (IOT-BAJ-RGL) y «Reactivar». Las vistas solo orquestan (docs/patrones/abm.md, sección 1): validan
# la entrada, llaman al servicio y renderizan. Consultan el Gerente y el Agrónomo; opera quien lo dice ``iot/alcance.py`` y quien solo consulta no ve botones de escritura (D-30).
#
# El formulario es una página con HTMX y respaldo sin JavaScript: elegir el actuador o la acción manda el formulario a la misma URL con ``refrescar``, que lo vuelve a dibujar SIN llamar al
# servicio (con HTMX solo se reemplaza ``#formulario``). Nada se valida mientras se tipea (D-29, interfaz.md): las validaciones corren al apretar «Crear regla» o «Guardar cambios». La ventana
# de baja es un fragmento con HTMX y, sin JavaScript, la ficha de la regla con la ventana abierta.

from dataclasses import replace
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.contexto import codigos_del_servicio, contexto_del_modulo, errores_del_servicio, es_htmx
from iot.models import Actuador, ReglaActuacion, Sensor
from iot.servicios import comandos as api_comandos
from iot.servicios import reglas as api
from iot.servicios import sistemas as api_sistemas

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO
VENTANA_BAJA = "iot/reglas/_ventana_baja.html"
# Los errores generales que mandan de vuelta a la lista: ya no se puede operar o la regla cambió de estado (precondición b de ALT y de MOD, regla 6 de MOD).
ERRORES_QUE_SACAN_DEL_FORMULARIO = {"fuera_de_alcance", "sin_sistema_iot", "sistema_dado_de_baja", "regla_inactiva", "invernadero_inactivo"}
# Cuántos comandos del historial muestra la ficha (regla 4 de IOT-CNS-RGL); el resto se ve en «Comandos» con el filtro de origen «Regla de actuación».
COMANDOS_EN_LA_FICHA = 25
TONO_DE_EVALUACION = {"Se cumple": "warn", "Sin evaluar": "neutral", "No se cumple": "neutral"}


def _a_la_lista(invernadero_id):
    return redirect(f"{reverse('iot:reglas')}?{urlencode({'invernadero': invernadero_id})}")


def _a_la_ficha(regla):
    return redirect("iot:regla_ficha", regla_id=regla.pk)


def _tono_de_evaluacion(texto):
    """El tono de la insignia de la evaluación (prototipo ``ultB``): «Se cumple» de aviso, «Confirmando…» y «Confirmada…» informativas, el resto neutral."""
    return TONO_DE_EVALUACION.get(texto, "info")


# ---- consulta (IOT-CNS-RGL) ----


def _filtros(request):
    """Los filtros de la lista (estado, sensor y actuador); uno desconocido o vacío no filtra."""
    return api.FiltrosDeReglas(
        estado=request.GET.get("estado", "").strip(), sensor_id=request.GET.get("sensor", "").strip() or None, actuador_id=request.GET.get("actuador", "").strip() or None
    )


def _fila(request, fila, sistema):
    """Una fila de la lista: la regla con su situación y los botones que puede usar quien mira (``acciones_permitidas``, D-30)."""
    return {"fila": fila, "tono": _tono_de_evaluacion(fila.evaluacion), "acciones": api.acciones_permitidas(request.user, fila.regla, sistema)}


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def reglas(request):
    """La pestaña «Reglas de actuación» (``reglas`` del prototipo): las reglas del invernadero elegido con sus filtros, su situación y los motivos por los que no emiten. Con HTMX, los
    filtros reemplazan solo la tabla. Solo lectura: no audita (regla 6 de IOT-CNS-RGL)."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    contexto = contexto_del_modulo(request, "reglas")
    elegido = contexto["elegido"]
    filtros = _filtros(request)
    contexto |= {"filtros": filtros, "hay_filtros": bool(filtros.estado or filtros.sensor_id or filtros.actuador_id), "sistema": None, "filas": [], "hay_reglas": False}
    if elegido is not None:
        sistema = api_sistemas.sistema_del_invernadero(request.user, elegido.pk)
        contexto["sistema"] = sistema
        if sistema is not None:
            filas = api.buscar_reglas(request.user, elegido.pk, filtros)
            contexto["filas"] = [_fila(request, f, sistema) for f in filas]
            contexto["hay_reglas"] = bool(filas) or ReglaActuacion.objects.filter(sensor__sistema=sistema).exists()
            contexto["sensores_del_filtro"] = list(Sensor.objects.filter(sistema=sistema).order_by("identificador_equipo", "pk"))
            contexto["actuadores_del_filtro"] = list(Actuador.objects.filter(sistema=sistema).select_related("tipo_actuador").order_by("identificador_equipo", "pk"))
            contexto["puede_crear"] = contexto["opera"] and sistema.estado_sistema != "inactivo"
    if es_htmx(request) and contexto["sistema"] is not None:
        return render(request, "iot/reglas/_tabla.html", contexto)
    return render(request, "iot/reglas/lista.html", contexto)


def _contexto_de_la_ficha(request, ficha, **extra):
    """Lo que dibuja la ficha de una regla (regla 4 de IOT-CNS-RGL): el marco de su invernadero, su situación, sus botones y el historial de los comandos que generó."""
    regla = ficha.fila.regla
    contexto = contexto_del_modulo(request, "reglas", regla.sensor.sistema.invernadero_id)
    comandos = api_comandos.filas_de_comandos(ficha.comandos[:COMANDOS_EN_LA_FICHA], timezone.now())
    return contexto | {
        "regla": regla,
        "fila": ficha.fila,
        "tono": _tono_de_evaluacion(ficha.fila.evaluacion),
        "acciones": api.acciones_permitidas(request.user, regla),
        "comandos": comandos,
        "comandos_total": len(ficha.comandos),
        **extra,
    }


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
def regla_ficha(request, regla_id):
    """La ficha de una regla con su historial de comandos. Fuera del alcance de consulta o inexistente, 404 (D-28). Solo lectura."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "iot/reglas/ficha.html", _contexto_de_la_ficha(request, api.ficha_de_regla(request.user, regla_id)))


# ---- el formulario (IOT-ALT-RGL e IOT-MOD-RGL) ----


def _datos_de_una_regla(regla):
    """Los datos del formulario de una regla guardada."""
    return api.DatosDeRegla(
        sensor_id=regla.sensor_id,
        actuador_id=regla.actuador_id,
        condicion=regla.condicion,
        accion_id=regla.accion_id,
        valor="" if regla.aplicar_valor is None else str(regla.aplicar_valor),
    )


def _contexto_del_formulario(request, contexto_modulo, datos, regla=None, errores=None, general=None):
    """Lo que dibuja el formulario de la regla, para dar de alta (``regla`` es ``None``) o para modificar: lo que ofrece ``datos_para_regla``, la acción elegida y la frase de vista previa
    (prototipo ``rglText``). Si la acción elegida no es del actuador (cambió el actuador), la acción y el valor se limpian."""
    elegido = contexto_modulo["elegido"]
    if regla is None:
        sensores, actuadores, acciones = api.datos_para_regla(request.user, elegido.pk, datos.actuador_id)
        sensor = next((s for s in sensores if str(s.pk) == str(datos.sensor_id)), None)
        actuador = next((a for a in actuadores if str(a.pk) == str(datos.actuador_id)), None)
    else:  # el sensor y el actuador no se cambian (regla 3 de MOD)
        sensores, actuadores = [], []
        sensor, actuador = regla.sensor, regla.actuador
        acciones = api.acciones_ofrecidas(actuador)
    if str(datos.accion_id) not in {str(a.pk) for a in acciones}:
        datos = replace(datos, accion_id=None, valor="")
    accion = next((a for a in acciones if str(a.pk) == str(datos.accion_id)), None)
    return contexto_modulo | {
        "datos": datos,
        "regla": regla,
        "errores": errores or {},
        "general": general or [],
        "sensores": sensores,
        "actuadores": actuadores,
        "acciones": acciones,
        "sensor": sensor,
        "actuador": actuador,
        "accion": accion,
        "condiciones": ReglaActuacion.Condicion.choices,
        "vista_previa": api.texto_previo(sensor, datos.condicion, actuador, accion, datos.valor),
        "sin_umbral": api.sin_umbral_efectivo(elegido.pk),
        "sistema_desconectado": getattr(api_sistemas.sistema_del_invernadero(request.user, elegido.pk), "estado_sistema", "") == "desconectado",
    }


def _sistema_de_la_pantalla(request, invernadero_id=None):
    """``(contexto del módulo, sistema)`` del invernadero elegido; si no hay sistema, está dado de baja o quien mira no lo opera, avisa y devuelve la respuesta de vuelta."""
    contexto = contexto_del_modulo(request, "reglas", invernadero_id)
    elegido = contexto["elegido"]
    if elegido is None:
        raise Http404("No hay un invernadero elegido.")
    sistema = api_sistemas.sistema_del_invernadero(request.user, elegido.pk)
    if sistema is None:
        messages.error(request, "Este invernadero no tiene Sistema IoT: registralo antes de crear reglas.")
        return contexto, redirect(f"{reverse('iot:sistema')}?{urlencode({'invernadero': elegido.pk})}")
    if not contexto["opera"]:
        messages.error(request, "Solo consultás el IoT de este invernadero: lo opera su Agrónomo.")
        return contexto, _a_la_lista(elegido.pk)
    return contexto, sistema


def _guardar(request, contexto_modulo, regla, datos):
    """Llama al servicio del alta o de la modificación. Devuelve ``(respuesta, None)`` si salió bien o ``(None, contexto del formulario con errores)``."""
    elegido = contexto_modulo["elegido"]
    ahora = timezone.now()
    try:
        if regla is None:
            guardada = api.alta_regla(request.user, elegido.pk, datos, ahora)
            mensaje = f"RGL-{guardada.pk} creada: {api.texto_de_regla(guardada)}."
            if api.sin_umbral_efectivo(elegido.pk):  # regla 7 de ALT: advierte y deja continuar
                mensaje += " Este invernadero no tiene umbral efectivo: la regla se guarda, pero no se evalúa hasta que lo tenga."
        else:
            guardada = api.modificar_regla(request.user, regla.pk, datos, ahora)
            mensaje = f"RGL-{guardada.pk} modificada: su evaluación vuelve a empezar desde la próxima lectura."
    except ValidationError as error:
        if ERRORES_QUE_SACAN_DEL_FORMULARIO & set(codigos_del_servicio(error)):
            messages.error(request, error.messages[0])
            return _a_la_lista(elegido.pk), None
        errores, general = errores_del_servicio(error)
        return None, _contexto_del_formulario(request, contexto_modulo, datos, regla, errores, general)
    messages.success(request, mensaje)
    return _a_la_lista(elegido.pk), None


def _formulario(request, regla=None):
    """Alta (``regla`` es ``None``) o modificación. Un POST con ``refrescar`` solo vuelve a dibujar; si no, llama al servicio y, si lo rechaza, dibuja el formulario con los errores por campo
    y lo escrito."""
    contexto_modulo, sistema = _sistema_de_la_pantalla(request, regla.sensor.sistema.invernadero_id if regla else None)
    if hasattr(sistema, "status_code"):  # no hay sistema o quien mira no lo opera: ya avisó y devolvió la redirección
        return sistema
    if request.method == "POST":
        datos = api.DatosDeRegla.desde_post(request.POST)
        if regla is not None:  # el sensor y el actuador no se cambian
            datos = replace(datos, sensor_id=regla.sensor_id, actuador_id=regla.actuador_id)
        if "refrescar" not in request.POST:
            respuesta, contexto = _guardar(request, contexto_modulo, regla, datos)
            if respuesta is not None:
                return respuesta
            return render(request, "iot/reglas/formulario.html", contexto)
        return render(request, "iot/reglas/formulario.html", _contexto_del_formulario(request, contexto_modulo, datos, regla))
    datos = _datos_de_una_regla(regla) if regla is not None else api.DatosDeRegla(condicion="")
    return render(request, "iot/reglas/formulario.html", _contexto_del_formulario(request, contexto_modulo, datos, regla))


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def regla_nueva(request):
    """Nueva regla de actuación (IOT-ALT-RGL; ``rgl-new`` del prototipo). Solo quien opera el IoT del invernadero y con un sistema IoT."""
    return _formulario(request)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def regla_modificar(request, regla_id):
    """Modificar una regla (IOT-MOD-RGL; ``rgl-mod`` del prototipo). Una dada de baja solo se reactiva: vuelve a la ficha."""
    ficha = api.ficha_de_regla(request.user, regla_id)
    regla = ficha.fila.regla
    if api.ACCION_MODIFICAR not in api.acciones_permitidas(request.user, regla):
        messages.error(request, "Esta regla no se puede modificar: está dada de baja, su sistema IoT está dado de baja o solo la consultás.")
        return _a_la_ficha(regla)
    return _formulario(request, regla)


# ---- baja y reactivar (IOT-BAJ-RGL e IOT-MOD-RGL, postcondición b) ----


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def regla_baja(request, regla_id):
    """Dar de baja una regla (IOT-BAJ-RGL; ventana ``rbaj:<id>`` del prototipo), con confirmación previa. Abrirla (GET) no cambia nada; dar de baja es un POST. Los comandos pendientes
    de la regla siguen su curso (regla 2)."""
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])
    ficha = api.ficha_de_regla(request.user, regla_id)
    regla = ficha.fila.regla
    if api.ACCION_BAJA not in api.acciones_permitidas(request.user, regla):
        messages.error(request, "Esta regla no se puede dar de baja: ya está dada de baja o solo la consultás.")
        return _a_la_ficha(regla)
    if request.method == "POST":
        try:
            api.baja_regla(request.user, regla.pk, timezone.now())
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return _a_la_ficha(regla)
        messages.success(request, f"RGL-{regla.pk} dada de baja: deja de evaluarse y su historial se conserva.")
        return _a_la_lista(regla.sensor.sistema.invernadero_id)
    pendientes = [c for c in ficha.comandos if c.estado_comando == "pendiente"]
    extra = {"regla": regla, "fila": ficha.fila, "pendientes": pendientes}
    if es_htmx(request):
        return render(request, VENTANA_BAJA, extra)
    return render(request, "iot/reglas/ficha.html", _contexto_de_la_ficha(request, ficha, plantilla_de_ventana=VENTANA_BAJA, **extra))


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@require_POST
def regla_reactivar(request, regla_id):
    """Reactivar una regla dada de baja (IOT-MOD-RGL, postcondición b y regla 6). Sin ventana: el botón es un POST y el servicio explica por qué no se puede (sensor o actuador
    sin activar, una regla activa igual)."""
    ficha = api.ficha_de_regla(request.user, regla_id)
    regla = ficha.fila.regla
    if api.ACCION_REACTIVAR not in api.acciones_permitidas(request.user, regla):
        messages.error(request, "Esta regla no se puede reactivar: ya está activa, su sistema IoT está dado de baja o solo la consultás.")
        return _a_la_ficha(regla)
    try:
        api.reactivar_regla(request.user, regla.pk, timezone.now())
    except ValidationError as error:
        errores, general = errores_del_servicio(error)
        messages.error(request, " ".join(general or [m for lista in errores.values() for m in lista]))
    else:
        messages.success(request, f"RGL-{regla.pk} reactivada: su evaluación empieza desde cero con la próxima lectura.")
    return _a_la_ficha(regla)
