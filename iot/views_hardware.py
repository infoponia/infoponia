# Vistas del Hardware (IOT-02): «IoT» → «Hardware» (lista con filtros y ficha del equipo; IOT-CNS-HDW), registrar (IOT-ALT-HDW), modificar, volver a activar y
# reactivar (IOT-MOD-HDW). Las vistas solo orquestan (docs/patrones/abm.md, sección 1): validan la entrada, llaman al servicio y renderizan. Consultan el
# Gerente y el Agrónomo; opera quien lo dice ``iot/alcance.py`` y quien solo consulta no ve botones de escritura (D-30).
#
# Los formularios son una página con HTMX y respaldo sin JavaScript: el cambio del tipo de equipo, de la variable o del tipo de actuador manda el formulario
# a la misma URL con ``refrescar``, que lo vuelve a dibujar SIN llamar al servicio (con HTMX solo se reemplaza ``#formulario``). Los avisos de «antes de
# guardar» (el identificador era de un equipo dado de baja, la compatibilidad con lo que anunció el nodo) llegan como un fragmento aparte al cambiar el
# identificador; sin JavaScript aparecen al volver a dibujar el formulario. Las ventanas (volver a activar, reactivar) son fragmentos con HTMX y, sin
# JavaScript, la ficha del equipo con la ventana abierta.

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.contexto import codigos_del_servicio, contexto_del_modulo, errores_del_servicio, es_htmx
from iot.models import Sensor, TipoActuador
from iot.servicios import compatibilidad as api_compatibilidad
from iot.servicios import hardware as api
from iot.servicios import sistemas as api_sistemas

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO
VENTANA_VOLVER_A_ACTIVAR = "iot/hardware/_ventana_volver_a_activar.html"
VENTANA_REACTIVAR = "iot/hardware/_ventana_reactivar.html"
# Los errores generales que mandan de vuelta a la lista: ya no se puede operar (extensiones 8a y 8b, precondición b).
ERRORES_QUE_SACAN_DEL_FORMULARIO = {"fuera_de_alcance", "sistema_dado_de_baja", "invernadero_inactivo", "equipo_dado_de_baja", "comando_pendiente"}


def _a_la_lista(invernadero_id):
    return redirect(f"{reverse('iot:hardware')}?invernadero={invernadero_id}")


def _a_la_ficha(equipo):
    return redirect("iot:hardware_ficha", equipo_id=equipo.pk)


# ---- consulta (IOT-CNS-HDW) ----


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def hardware(request):
    """La pestaña «Hardware» (``hardware`` del prototipo): el nodo central, los equipos del invernadero elegido con sus filtros y los identificadores que el nodo
    anunció y todavía no están registrados. Con HTMX, los filtros reemplazan solo la tabla. Solo lectura: no audita (regla 8)."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    contexto = contexto_del_modulo(request, "hardware")
    elegido = contexto["elegido"]
    filtros = {campo: request.GET.get(campo, "").strip() for campo in ("q", "tipo", "estado", "sector")}
    contexto |= {"filtros": filtros, "hay_filtros": any(valor not in ("", "todos") for valor in filtros.values()), "sistema": None}
    if elegido is not None:
        sistema = api_sistemas.sistema_del_invernadero(request.user, elegido.pk)
        contexto["sistema"] = sistema
        if sistema is not None:
            equipos = api.buscar_equipos(request.user, sistema, filtros)
            contexto |= {
                "filas": [{"equipo": e, "situacion": api.situacion_de(e)} for e in equipos],
                "hay_equipos": bool(equipos) or any(filtros.values()),
                "sectores": list(api.sectores_del_invernadero(elegido)),
                "nodo": api_sistemas.nodo_del_sistema(sistema),
                "libres": api.identificadores_anunciados_libres(sistema) if contexto["opera"] else [],
            }
            contexto["conectividad"] = api_sistemas.conectividad(contexto["nodo"], timezone.now())
    if es_htmx(request):
        return render(request, "iot/hardware/_tabla.html", contexto)
    return render(request, "iot/hardware/lista.html", contexto)


def _contexto_de_la_ficha(request, equipo, **extra):
    """Lo que dibuja la ficha del equipo (regla 6 de IOT-CNS-HDW): el marco del invernadero del equipo, sus datos, su situación, sus alertas activas y sus botones."""
    contexto = contexto_del_modulo(request, "hardware", equipo.sistema.invernadero_id)
    return contexto | {
        "equipo": equipo,
        "situacion": api.situacion_de(equipo),
        "alertas": api.alertas_activas_del_equipo(equipo),
        "acciones": api.acciones_permitidas(request.user, equipo),
        "nombre": api.nombre_del_equipo(equipo),
        **extra,
    }


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
def hardware_ficha(request, equipo_id):
    """La ficha de un sensor o de un actuador (``hw-ficha`` del prototipo). Fuera del alcance de consulta o inexistente, 404 (D-28). Solo lectura."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    equipo = api.ficha_del_equipo(request.user, equipo_id)
    return render(request, "iot/hardware/ficha.html", _contexto_de_la_ficha(request, equipo))


# ---- el formulario de un equipo (IOT-ALT-HDW e IOT-MOD-HDW) ----


def _datos_de_un_equipo(equipo):
    """Los datos del formulario de un equipo guardado."""
    datos = api.DatosDeEquipo(
        clase=equipo.clase,
        identificador=equipo.identificador_equipo,
        modelo=equipo.modelo_hardware,
        numero_serie=equipo.numero_serie,
        sector_id=equipo.sector_id,
    )
    if equipo.clase == "sensor":
        datos.variable = equipo.tipo_variable_sensor
        datos.nombre_sensor = equipo.nombre_sensor
        datos.calibracion_min = "" if equipo.valor_calibracion_min is None else str(equipo.valor_calibracion_min)
        datos.calibracion_max = "" if equipo.valor_calibracion_max is None else str(equipo.valor_calibracion_max)
    else:
        datos.tipo_actuador_id = equipo.tipo_actuador_id
        datos.descripcion = equipo.descripcion_actuador
    return datos


def _avisos_del_alta(sistema, datos):
    """Los avisos de «antes de guardar» del alta (reglas 12 y 14 de IOT-ALT-HDW): si el identificador era de un equipo dado de baja (con «Reactivar»), y, para un actuador, si lo
    que anunció el nodo cubre las acciones del tipo elegido. Solo lectura."""
    identificador = (datos.identificador or "").strip()
    avisos = {"baja": None, "compatibilidad": None, "anunciado": False}
    if not identificador:
        return avisos
    avisos["baja"] = api.baja_con_identificador(sistema, identificador)
    if datos.clase == "actuador" and str(datos.tipo_actuador_id or "").isdigit():
        tipo = TipoActuador.objects.filter(pk=int(datos.tipo_actuador_id)).first()
        en_uso = avisos["baja"] is None and api._equipo_con_identificador(sistema, identificador) is not None
        if tipo is not None and not en_uso:
            avisos["compatibilidad"] = api_compatibilidad.calcular_compatibilidad(sistema, identificador, tipo)
    return avisos


def _contexto_del_formulario(request, sistema, invernadero, datos, equipo=None, errores=None, general=None, desde_alerta=False):
    """Lo que dibuja el formulario del equipo, para registrar (``equipo`` es ``None``) o para modificar."""
    contexto = {
        "sistema": sistema,
        "elegido": invernadero,
        "datos": datos,
        "equipo": equipo,
        "errores": errores or {},
        "general": general or [],
        "desde_alerta": desde_alerta,
        "sectores": list(api.sectores_del_invernadero(invernadero)),
        "insumos": [] if equipo else list(api_sistemas.insumos_de_hardware()),
        "tipos": list(api.tipos_de_actuador_activos()),
        "variables": Sensor.Variable.choices,
        "unidad": Sensor.UNIDADES.get(datos.variable or "", ""),
        "libres": api.identificadores_anunciados_libres(sistema),
        "bloqueados": api.campos_bloqueados(equipo) if equipo else {},
        "hoy": timezone.localdate().isoformat(),
        "es_gerente": request.user.rol == GERENTE,
        "avisos": _avisos_del_alta(sistema, datos) if equipo is None else {"baja": None, "compatibilidad": None, "anunciado": False},
    }
    if equipo is not None and equipo.clase == "actuador" and datos.tipo_actuador_id not in (None, ""):
        tipo = TipoActuador.objects.filter(pk=int(datos.tipo_actuador_id)).first() if str(datos.tipo_actuador_id).isdigit() else None
        if tipo is not None and str(tipo.pk) != str(equipo.tipo_actuador_id):
            contexto["avisos"]["compatibilidad"] = api_compatibilidad.calcular_compatibilidad(sistema, datos.identificador or equipo.identificador_equipo, tipo)
    return contexto


def _sistema_de_la_pantalla(request, invernadero_id=None):
    """``(contexto del módulo, sistema)`` del invernadero elegido; si no hay sistema o quien mira no lo opera, avisa y devuelve la respuesta de vuelta a la lista."""
    contexto = contexto_del_modulo(request, "hardware", invernadero_id)
    elegido = contexto["elegido"]
    if elegido is None:
        raise Http404("No hay un invernadero elegido.")
    sistema = api_sistemas.sistema_del_invernadero(request.user, elegido.pk)
    if sistema is None:
        messages.error(request, "Este invernadero no tiene Sistema IoT: registralo antes de cargar equipos.")
        return contexto, redirect(f"{reverse('iot:sistema')}?invernadero={elegido.pk}")
    if not contexto["opera"]:
        messages.error(request, "Solo consultás el IoT de este invernadero: lo opera su Agrónomo.")
        return contexto, _a_la_lista(elegido.pk)
    return contexto, sistema


def _guardar(request, sistema, elegido, equipo, datos):
    """Llama al servicio del alta o de la modificación. Devuelve ``(respuesta, None)`` si salió bien o ``(None, contexto del formulario con errores)``."""
    try:
        if equipo is None:
            guardado = api.alta_hardware(request.user, sistema.pk, datos)
            mensaje = f"{api.nombre_del_equipo(guardado)} {guardado.identificador_equipo} registrado correctamente."
            if guardado.clase == "sensor" and guardado.sector_id and guardado.sector.estado_sector == "fuera_de_servicio":
                mensaje += f" El {guardado.sector} está fuera de servicio: este sensor no generará alertas ni activará reglas."
            if guardado.clase == "actuador" and guardado.compatibilidad == "incompatible":
                mensaje += " El nodo no anunció todos los comandos del tipo: quedó con configuración incompatible."
        else:
            guardado = api.modificar_hardware(request.user, equipo.pk, datos)
            mensaje = f"{api.nombre_del_equipo(guardado)} {guardado.identificador_equipo} modificado correctamente."
    except ValidationError as error:
        if ERRORES_QUE_SACAN_DEL_FORMULARIO & set(codigos_del_servicio(error)):
            messages.error(request, error.messages[0])
            return _a_la_lista(elegido.pk), None
        errores, general = errores_del_servicio(error)
        return None, _contexto_del_formulario(request, sistema, elegido, datos, equipo, errores, general)
    messages.success(request, mensaje)
    return _a_la_ficha(guardado), None


def _formulario(request, equipo=None):
    """Alta (``equipo`` es ``None``) o modificación. Un POST con ``refrescar`` solo vuelve a dibujar; «guardar» llama al servicio y, si lo rechaza, dibuja el formulario
    con los errores por campo y lo escrito."""
    contexto_modulo, sistema = _sistema_de_la_pantalla(request, equipo.sistema.invernadero_id if equipo else None)
    if hasattr(sistema, "status_code"):  # no hay sistema o quien mira no lo opera: ya avisó y devolvió la redirección
        return sistema
    elegido = contexto_modulo["elegido"]
    if request.method == "POST":
        datos = api.DatosDeEquipo.desde_post(request.POST, equipo.clase if equipo else "")
        if "refrescar" not in request.POST:
            respuesta, contexto = _guardar(request, sistema, elegido, equipo, datos)
            if respuesta is not None:
                return respuesta
            return render(request, "iot/hardware/formulario.html", contexto_modulo | contexto)
        return render(request, "iot/hardware/formulario.html", contexto_modulo | _contexto_del_formulario(request, sistema, elegido, datos, equipo))
    if equipo is None:
        identificador = request.GET.get("identificador", "").strip()
        datos = api.DatosDeEquipo(
            clase=request.GET.get("clase", ""), identificador=identificador, fecha_instalacion=timezone.localdate().isoformat()
        )
        contexto = _contexto_del_formulario(request, sistema, elegido, datos, desde_alerta=bool(identificador))
    else:
        contexto = _contexto_del_formulario(request, sistema, elegido, _datos_de_un_equipo(equipo), equipo)
    return render(request, "iot/hardware/formulario.html", contexto_modulo | contexto)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def hardware_nuevo(request):
    """Registrar hardware (IOT-ALT-HDW, ``hw-new`` y ``reg-alert`` del prototipo). Acepta ``?identificador=`` (desde la alerta «dispositivo no registrado», regla 12)."""
    return _formulario(request)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def hardware_modificar(request, equipo_id):
    """Modificar un equipo (IOT-MOD-HDW, ``hw-mod`` del prototipo). Uno dado de baja solo se reactiva: vuelve a la ficha."""
    equipo = api.ficha_del_equipo(request.user, equipo_id)
    if api.ACCION_MODIFICAR not in api.acciones_permitidas(request.user, equipo):
        messages.error(request, "Este equipo no se puede modificar: está dado de baja o solo lo consultás.")
        return _a_la_ficha(equipo)
    return _formulario(request, equipo)


@rol_requerido(GERENTE, AGRONOMO)
@require_GET
def hardware_avisos(request):
    """Los avisos de «antes de guardar» del alta, como fragmento (HTMX al cambiar el identificador): si era de un equipo dado de baja y la compatibilidad con lo que anunció el nodo."""
    contexto, sistema = _sistema_de_la_pantalla(request)
    if hasattr(sistema, "status_code"):
        return sistema
    datos = api.DatosDeEquipo(
        clase=request.GET.get("clase", ""), identificador=request.GET.get("identificador", ""), tipo_actuador_id=request.GET.get("tipo_actuador", "")
    )
    return render(request, "iot/hardware/_avisos.html", {"avisos": _avisos_del_alta(sistema, datos), "datos": datos, "elegido": contexto["elegido"]})


# ---- volver a activar y reactivar (IOT-MOD-HDW) ----


def _ventana(request, equipo, plantilla, **extra):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la ficha con la ventana abierta (respaldo sin JavaScript)."""
    if es_htmx(request):
        return render(request, plantilla, {"equipo": equipo, "nombre": api.nombre_del_equipo(equipo), **extra})
    return render(request, "iot/hardware/ficha.html", _contexto_de_la_ficha(request, equipo, plantilla_de_ventana=plantilla, **extra))


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def hardware_volver_a_activar(request, equipo_id):
    """Volver a activar un equipo fuera de servicio (IOT-MOD-HDW, postcondición b y regla 7; ventana ``react`` del prototipo), con confirmación previa. Lista las órdenes de
    mantenimiento a realizar que lo incluyen (regla 8, **se completa en IOT-07**). Abrirla (GET) no cambia nada; volver a activar es un POST."""
    equipo = api.ficha_del_equipo(request.user, equipo_id)
    if api.ACCION_VOLVER_A_ACTIVAR not in api.acciones_permitidas(request.user, equipo):
        messages.error(request, "Este equipo no se puede volver a activar.")
        return _a_la_ficha(equipo)
    if request.method == "POST":
        try:
            api.volver_a_activar(request.user, equipo.pk)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f"{api.nombre_del_equipo(equipo)} {equipo.identificador_equipo} volvió a estar activo.")
        return _a_la_ficha(equipo)
    return _ventana(request, equipo, VENTANA_VOLVER_A_ACTIVAR, ordenes=api.mantenimientos_a_realizar(equipo))


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def hardware_reactivar(request, equipo_id):
    """Reactivar un equipo dado de baja (IOT-MOD-HDW, postcondición c y regla 9; ventana ``rebaja`` del prototipo), con confirmación previa. Si otro equipo usa su identificador, su
    sistema está dado de baja o su tipo también, la ventana lo dice y no ofrece confirmar. Abrirla (GET) no cambia nada; reactivar es un POST."""
    equipo = api.ficha_del_equipo(request.user, equipo_id)
    if api.ACCION_REACTIVAR not in api.acciones_permitidas(request.user, equipo):
        messages.error(request, "Este equipo no se puede reactivar.")
        return _a_la_ficha(equipo)
    error = ""
    if request.method == "POST":
        try:
            api.reactivar_hardware(request.user, equipo.pk)
        except ValidationError as rechazo:
            error = rechazo.messages[0]
        else:
            messages.success(request, f"{api.nombre_del_equipo(equipo)} {equipo.identificador_equipo} se reactivó con su historial.")
            return _a_la_ficha(equipo)
    impedimento = api.impedimento_de_reactivacion(equipo)
    compatibilidad = None
    if impedimento is None and equipo.clase == "actuador":
        compatibilidad = api_compatibilidad.calcular_compatibilidad(equipo.sistema, equipo.identificador_equipo, equipo.tipo_actuador)
    return _ventana(request, equipo, VENTANA_REACTIVAR, impedimento=impedimento, error=error, compatibilidad=compatibilidad)
