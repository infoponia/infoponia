# Vistas del Sistema IoT (IOT-02): «IoT» → «Sistema IoT» (ficha del nodo), registrar (IOT-REG-SIS: elegir el invernadero, datos con «Revisar» y confirmación),
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
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.catalogo import URL_GUIA_DEL_NODO
from iot.contexto import codigos_del_servicio, contexto_del_modulo, errores_del_servicio, es_htmx, sin_cache
from iot.models import SistemaIoT
from iot.servicios import sistemas as api

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO

# Los errores generales que mandan al paso 2 (elegir el invernadero): extensiones 8a y 8b de IOT-REG-SIS.
ERRORES_DEL_PASO_2 = {"fuera_de_alcance", "sistema_existente", "invernadero_inactivo"}
PLANTILLA_DE_REGENERAR = "iot/sistema/_ventana_regenerar.html"


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
