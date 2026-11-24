# Vistas del Sistema IoT (IOT-02; desactivar, activar y dar de baja, IOT-06): «IoT» → «Sistema IoT» (ficha del nodo), registrar (IOT-REG-SIS: elegir el invernadero, datos con «Revisar» y confirmación),
# modificar y regenerar el token (IOT-MOD-SIS). Las vistas solo orquestan (docs/patrones/abm.md, sección 1): validan la entrada, llaman al servicio y
# renderizan. Consultan el Gerente y el Agrónomo; opera quien lo dice ``iot/alcance.py`` y quien solo consulta no ve botones de escritura (D-30).
#
# El token se ve UNA sola vez (D-70, pasos 9 y 10 de IOT-REG-SIS): la respuesta al POST que registra o regenera RENDERIZA la pantalla del token (no
# redirige: no se guarda en ningún lado para mostrarlo después) con ``never_cache`` y ``Cache-Control: no-store``; recargarla vuelve a pedir el POST y no
# lo muestra de nuevo. Las ventanas (regenerar) son fragmentos con HTMX y, sin JavaScript, la ficha con la ventana abierta.

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.catalogo import URL_GUIA_DEL_NODO
from iot.contexto import codigos_del_servicio, contexto_del_modulo, errores_del_servicio, es_htmx, sin_cache
from iot.models import SistemaIoT
from iot.servicios import hardware as api_hardware
from iot.servicios import reglas as api_reglas
from iot.servicios import sistemas as api
from iot.textos import estado_legible

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO

# Los errores generales que mandan al paso 2 (elegir el invernadero): extensiones 8a y 8b de IOT-REG-SIS.
ERRORES_DEL_PASO_2 = {"fuera_de_alcance", "sistema_existente", "invernadero_inactivo"}
PLANTILLA_DE_REGENERAR = "iot/sistema/_ventana_regenerar.html"
PLANTILLA_DE_DESACTIVAR = "iot/sistema/_ventana_desactivar.html"
PLANTILLA_DE_BAJA = "iot/sistema/_ventana_baja.html"


def _url_de_la_api(request):
    """La dirección de la API del nodo que se muestra con el token (docs/casos_de_uso/iot/sistema_iot.md, «Mostrar el token una sola vez»)."""
    return request.build_absolute_uri("/api/iot/v1/")


def _datos_del_nodo(sistema):
    """Los datos del formulario de modificación: el nodo del sistema y su rango."""
    nodo = api.nodo_del_sistema(sistema)
    return api.DatosDeSistema(
        invernadero_id=sistema.invernadero_id,
        nombre=nodo.nombre_nodo,
        modelo=nodo.modelo_hardware,
        numero_serie=nodo.numero_serie,
        temp_min="" if sistema.temp_solucion_min is None else str(sistema.temp_solucion_min),
        temp_max="" if sistema.temp_solucion_max is None else str(sistema.temp_solucion_max),
    )


# ---- «Sistema IoT»: la ficha del nodo (consulta) ----


def _contexto_de_la_ficha(request, forzado=None, **extra):
    """Lo que dibuja la pestaña «Sistema IoT»: el marco, el sistema del invernadero elegido, su nodo, la conectividad y los botones (``acciones_permitidas``)."""
    contexto = contexto_del_modulo(request, "sistema", forzado)
    elegido = contexto["elegido"]
    contexto |= {"sistema": None, "url_de_la_api": _url_de_la_api(request), "url_de_la_guia": URL_GUIA_DEL_NODO, "acciones": frozenset()}
    if elegido is not None:
        sistema = api.sistema_del_invernadero(request.user, elegido.pk)
        contexto["sistema"] = sistema
        if sistema is None:
            contexto["hay_insumos"] = api.insumos_de_hardware().exists()
        else:
            nodo = api.nodo_del_sistema(sistema)
            contexto |= {
                "nodo": nodo,
                "conectividad": api.conectividad(nodo, timezone.now()),
                "anuncio": api.anuncio_del_nodo(sistema),
                "acciones": api.acciones_permitidas(request.user, sistema),
            }
    return contexto | extra


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
def sistema(request):
    """La pestaña «Sistema IoT» (``sistema`` del prototipo): la ficha del nodo del invernadero elegido, o «no tiene Sistema IoT» con «Registrar sistema IoT»
    (a quien lo opera). Solo consulta; no audita (SEG-14)."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "iot/sistema/pagina.html", _contexto_de_la_ficha(request))


# ---- registrar (IOT-REG-SIS) ----


def _contexto_del_formulario(request, elegible, datos, errores=None, general=None, modificar=False, sistema=None):
    """Lo que dibuja el formulario del nodo, para registrar (``elegible`` es el invernadero ofrecido) o para modificar."""
    return {
        "elegible": elegible,
        "datos": datos,
        "errores": errores or {},
        "general": general or [],
        "insumos": [] if modificar else list(api.insumos_de_hardware()),
        "hoy": timezone.localdate().isoformat(),
        "modificar": modificar,
        "sistema": sistema,
    }


def _pantalla_del_token(request, sistema_con_token, token, regenerado):
    """La pantalla del token (pasos 9 y 10): el token UNA sola vez, la dirección de la API y la guía. Sin caché."""
    nodo = api.nodo_del_sistema(sistema_con_token)
    respuesta = render(
        request,
        "iot/sistema/token.html",
        {
            "sistema": sistema_con_token,
            "nodo": nodo,
            "token": token,
            "regenerado": regenerado,
            "url_de_la_api": _url_de_la_api(request),
            "url_de_la_guia": URL_GUIA_DEL_NODO,
        },
    )
    return sin_cache(respuesta)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sistema_registrar(request):
    """Registrar el sistema IoT de un invernadero (IOT-REG-SIS, ``sys-form`` y ``open-sys-form`` del prototipo), en tres pantallas: elegir el invernadero
    (paso 2), los datos del nodo con el resumen «Revisar» (pasos 5 y 6) y la confirmación «Registrar y generar token» (paso 8), que muestra el token
    una sola vez. Sin insumo de «Repuestos de hardware» (precondición c) no ofrece registrar."""
    elegibles = api.invernaderos_para_registrar(request.user)
    hay_insumos = api.insumos_de_hardware().exists()
    crudo = request.POST.get("invernadero") if request.method == "POST" else request.GET.get("invernadero")
    if not crudo:  # paso 2: elegir el invernadero
        return render(
            request,
            "iot/sistema/registrar_elegir.html",
            {"elegibles": elegibles, "hay_insumos": hay_insumos, "es_agronomo": request.user.rol == AGRONOMO},
        )
    elegible = next((e for e in elegibles if str(e.invernadero.pk) == crudo.strip()), None)
    if elegible is None:
        messages.error(request, "Ese invernadero no se puede registrar: ya tiene un sistema IoT o no lo operás.")
        return redirect("iot:sistema_registrar")
    if not hay_insumos:
        return redirect("iot:sistema_registrar")
    if request.method != "POST":
        datos = api.DatosDeSistema(invernadero_id=elegible.invernadero.pk, fecha_instalacion=timezone.localdate().isoformat())
        return render(request, "iot/sistema/formulario.html", _contexto_del_formulario(request, elegible, datos))
    datos = api.DatosDeSistema.desde_post(request.POST, elegible.invernadero.pk)
    if "editar" in request.POST:
        return render(request, "iot/sistema/formulario.html", _contexto_del_formulario(request, elegible, datos))
    try:
        if "confirmar" in request.POST:
            creado, token = api.registrar_sistema_iot(request.user, datos)
            return _pantalla_del_token(request, creado, token, regenerado=False)
        resumen = api.resumen_de_registro(request.user, datos)
    except ValidationError as error:
        if ERRORES_DEL_PASO_2 & set(codigos_del_servicio(error)):
            messages.error(request, error.messages[0])
            return redirect("iot:sistema_registrar")
        errores, general = errores_del_servicio(error)
        return render(request, "iot/sistema/formulario.html", _contexto_del_formulario(request, elegible, datos, errores, general))
    return render(request, "iot/sistema/resumen.html", {"resumen": resumen, "datos": datos, "elegible": elegible})


# ---- modificar y regenerar el token (IOT-MOD-SIS) ----


def _sistema_a_modificar(request, sistema_id):
    """El sistema ``sistema_id`` si ``request.user`` lo consulta (fuera del alcance o que no existe, 404); uno dado de baja no se modifica (404 desde la URL)."""
    sistema_elegido = get_object_or_404(SistemaIoT.objects.para(request.user).select_related("invernadero"), pk=sistema_id)
    if sistema_elegido.estado_sistema == SistemaIoT.Estado.INACTIVO:
        raise Http404("Un sistema IoT dado de baja no se modifica.")
    return sistema_elegido


def _a_la_ficha(invernadero_id):
    """Vuelve a la pestaña «Sistema IoT» del invernadero."""
    return redirect(f"{reverse('iot:sistema')}?invernadero={invernadero_id}")


def _sin_permiso(request, sistema_elegido):
    """Si ``request.user`` solo consulta este sistema (por ejemplo, el Gerente con un Agrónomo activo), avisa y vuelve a la ficha (D-30)."""
    messages.error(request, "Solo consultás este sistema IoT: lo opera el Agrónomo del invernadero.")
    return _a_la_ficha(sistema_elegido.invernadero_id)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sistema_modificar(request, sistema_id):
    """Modificar el nodo central y el rango de la solución (IOT-MOD-SIS, reglas 2 y 7; ``sys-form`` con ``mod`` del prototipo). Un sistema dado de baja da 404."""
    sistema_elegido = _sistema_a_modificar(request, sistema_id)
    if api.ACCION_MODIFICAR not in api.acciones_permitidas(request.user, sistema_elegido):
        return _sin_permiso(request, sistema_elegido)
    if request.method == "POST":
        datos = api.DatosDeSistema.desde_post(request.POST, sistema_elegido.invernadero_id)
        try:
            api.modificar_sistema_iot(request.user, sistema_elegido.pk, datos)
        except ValidationError as error:
            errores, general = errores_del_servicio(error)
            return render(
                request, "iot/sistema/formulario.html", _contexto_del_formulario(request, None, datos, errores, general, True, sistema_elegido)
            )
        messages.success(request, "Sistema IoT modificado correctamente.")
        return _a_la_ficha(sistema_elegido.invernadero_id)
    return render(
        request, "iot/sistema/formulario.html", _contexto_del_formulario(request, None, _datos_del_nodo(sistema_elegido), modificar=True, sistema=sistema_elegido)
    )


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sistema_regenerar_token(request, sistema_id):
    """Regenerar el token del nodo (IOT-MOD-SIS, postcondición b y reglas 3 y 4; ventana ``regen`` del prototipo), con confirmación previa. Abrirla (GET) no
    cambia nada; regenerar es un POST que RENDERIZA el token nuevo, una sola vez (sin redirigir)."""
    sistema_elegido = _sistema_a_modificar(request, sistema_id)
    if api.ACCION_REGENERAR_TOKEN not in api.acciones_permitidas(request.user, sistema_elegido):
        return _sin_permiso(request, sistema_elegido)
    if request.method == "POST":
        try:
            token = api.regenerar_token(request.user, sistema_elegido.pk)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return _a_la_ficha(sistema_elegido.invernadero_id)
        return _pantalla_del_token(request, sistema_elegido, token, regenerado=True)
    if es_htmx(request):
        return render(request, PLANTILLA_DE_REGENERAR, {"sistema": sistema_elegido})
    contexto = _contexto_de_la_ficha(request, sistema_elegido.invernadero_id, plantilla_de_ventana=PLANTILLA_DE_REGENERAR)
    return render(request, "iot/sistema/pagina.html", contexto)


# ---- desactivar, activar y dar de baja (IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS; IOT-06) ----


def _sistema_del_ciclo(request, sistema_id):
    """El sistema ``sistema_id`` si ``request.user`` lo consulta (fuera del alcance o que no existe, 404). A diferencia de ``_sistema_a_modificar``, uno dado de baja NO da 404: la pantalla
    explica que la baja es definitiva y vuelve a la ficha."""
    return get_object_or_404(SistemaIoT.objects.para(request.user).select_related("invernadero"), pk=sistema_id)


def _ventana_del_ciclo(request, sistema_elegido, plantilla, **extra):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la ficha del sistema con la ventana abierta (respaldo sin JavaScript)."""
    if es_htmx(request):
        return render(request, plantilla, {"sistema": sistema_elegido, "nodo": api.nodo_del_sistema(sistema_elegido), **extra})
    contexto = _contexto_de_la_ficha(request, sistema_elegido.invernadero_id, plantilla_de_ventana=plantilla, **extra)
    return render(request, "iot/sistema/pagina.html", contexto)


def _accion_del_ciclo(request, sistema_id, accion, funcion, mensaje, plantilla=None, **extra):
    """Lo común de desactivar y activar: sin permiso o con el sistema en otro estado, avisa y vuelve a la ficha; un POST llama al servicio; un GET abre la ventana de confirmación
    (``plantilla``), salvo que no tenga (activar no pregunta: no pierde nada)."""
    sistema_elegido = _sistema_del_ciclo(request, sistema_id)
    if accion not in api.acciones_permitidas(request.user, sistema_elegido):
        if sistema_elegido.estado_sistema == SistemaIoT.Estado.INACTIVO:
            messages.error(request, "El sistema IoT está dado de baja: la baja es definitiva.")
            return _a_la_ficha(sistema_elegido.invernadero_id)
        return _sin_permiso(request, sistema_elegido)
    if request.method == "POST":
        try:
            funcion(request.user, sistema_elegido.pk, timezone.now())
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, mensaje)
        return _a_la_ficha(sistema_elegido.invernadero_id)
    return _ventana_del_ciclo(request, sistema_elegido, plantilla, **extra)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sistema_desactivar(request, sistema_id):
    """Desactivar el sistema IoT (IOT-DSC-SIS; ventana ``desc`` del prototipo), con confirmación previa. Abrirla (GET) no cambia nada; desactivar es un POST."""
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])
    return _accion_del_ciclo(
        request,
        sistema_id,
        api.ACCION_DESACTIVAR,
        api.desactivar_sistema_iot,
        "Sistema IoT desconectado: sus comandos pendientes se cancelaron y sus alertas se resolvieron. Podés activarlo de nuevo cuando quieras.",
        PLANTILLA_DE_DESACTIVAR,
    )


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@require_POST
def sistema_activar(request, sistema_id):
    """Activar el sistema IoT (IOT-ACT-SIS; ``sys-activar`` del prototipo). Sin ventana, como el prototipo: es un POST del botón «Activar», que no pierde nada."""
    return _accion_del_ciclo(
        request, sistema_id, api.ACCION_ACTIVAR, api.activar_sistema_iot, "Sistema IoT activado: sus reglas de actuación empiezan a evaluarse desde la próxima lectura."
    )


def _linea_de_equipo(equipo):
    """Una línea de la lista de la baja (regla 8 de IOT-BAJ-SIS): el equipo con su nombre y, de un actuador, su último estado informado por el nodo (regla 7 de IOT-BAJ-HDW)."""
    ultimo = ""
    if equipo.clase == "actuador":
        if equipo.estado_informado:
            desde = f" desde las {timezone.localtime(equipo.estado_informado_en):%H:%M}" if equipo.estado_informado_en else ""
            ultimo = f"{estado_legible(equipo.estado_informado).lower()}{desde}"
        else:
            ultimo = "desconocido"
    return {"equipo": equipo, "nombre": api_hardware.nombre_del_equipo(equipo), "ultimo": ultimo}


def _linea_de_regla(regla):
    """Una línea de la lista de la baja: el código y la frase de una regla activa."""
    return {"codigo": f"RGL-{regla.pk}", "texto": api_reglas.texto_de_regla(regla)}


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sistema_baja(request, sistema_id):
    """Dar de baja el sistema IoT (IOT-BAJ-SIS; ventana ``baj`` sin id del prototipo): antes de confirmar, la ventana muestra lo que se da de baja (regla 8) y, si hay comandos
    pendientes u órdenes a realizar, no deja confirmar y explica cómo resolverlo (regla 4). Abrirla (GET) no cambia nada; la baja es un POST."""
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])
    sistema_elegido = _sistema_del_ciclo(request, sistema_id)
    if api.ACCION_BAJA not in api.acciones_permitidas(request.user, sistema_elegido):
        if sistema_elegido.estado_sistema == SistemaIoT.Estado.INACTIVO:
            messages.error(request, "El sistema IoT ya está dado de baja.")
            return _a_la_ficha(sistema_elegido.invernadero_id)
        return _sin_permiso(request, sistema_elegido)
    error = []
    if request.method == "POST":
        try:
            api.baja_sistema_iot(request.user, sistema_elegido.pk, timezone.now())
        except ValidationError as rechazo:
            error = rechazo.messages  # los impedimentos de la regla 4 (la ventana los vuelve a mostrar, con el estado de ahora)
        else:
            messages.success(request, "Sistema IoT dado de baja: su nodo, su hardware y sus reglas quedaron inactivos y el token dejó de servir. Su historial se conserva.")
            return _a_la_ficha(sistema_elegido.invernadero_id)
    datos = api.datos_de_baja_del_sistema(request.user, sistema_elegido.pk)
    equipos = [_linea_de_equipo(e) for e in datos.equipos]
    return _ventana_del_ciclo(
        request,
        sistema_elegido,
        PLANTILLA_DE_BAJA,
        datos=datos,
        equipos=equipos,
        hay_actuadores=any(e["equipo"].clase == "actuador" for e in equipos),
        reglas=[_linea_de_regla(r) for r in datos.reglas],
        error=error,
    )
