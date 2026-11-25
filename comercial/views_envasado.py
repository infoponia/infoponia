# Vistas del envasado de las entregas (COM-05a2, PROD-PNF-ENV; docs/casos_de_uso/produccion/envasado.md, «Pantallas»): «Envasado» (la lista de entregas a envasar del Agrónomo), la carga
# de envases de una entrega, su resumen y la confirmación. Las vistas SOLO orquestan: arman la carga desde el pedido, llaman al servicio (`comercial/servicios/envasado.py`) y renderizan; todas
# las reglas son del servicio. Sin JavaScript todo funciona: cada pantalla es una página, «Actualizar» redibuja, «Revisar» muestra el resumen y «Confirmar envasado» escribe. Con HTMX solo se
# redibuja el bloque de la carga desde los botones (Actualizar, Buscar, Agregar y Quitar), con ``hx-swap="innerHTML show:none"``; NUNCA se valida ni se calcula al tipear
# (`.claude/rules/interfaz.md`). `calcular/` y `revisar/` no escriben nada. Rutas con el prefijo de `comercial/`, el mismo de las pantallas de cosecha del Agrónomo (COM-04).

from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import envasado
from comercial.servicios.envasado import CargaDeEnvasado
from core.acceso import rol_requerido
from core.models import Usuario

AGRONOMO = Usuario.Rol.AGRONOMO
# Códigos con los que el servicio avisa que la entrega ya no se puede envasar (10a y 3b) o que su invernadero está inactivo: no hay carga que corregir, se vuelve a la lista.
SIN_SALIDA = {"entrega_no_a_realizar", "entrega_en_curso", "invernadero_inactivo"}


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _codigos(error):
    """Los códigos de un `ValidationError` del servicio (con o sin diccionario de campos)."""
    if hasattr(error, "error_dict"):
        return {e.code for lista in error.error_dict.values() for e in lista}
    return {e.code for e in error.error_list}


def _generales(error):
    """Los mensajes de un `ValidationError` que no son de una fila (8a, 8c, 10b y 10c): los de `__all__` y el aviso de 10b, que trae la fila y lo disponible vigente."""
    if not hasattr(error, "error_dict"):
        return error.messages
    return [e.message for campo, lista in error.error_dict.items() for e in lista if campo == "__all__" or e.code == "disponible_cambio"]


def _a_la_lista(request, error):
    """10a, 3b o invernadero inactivo: no se registra nada, se informa la situación y se vuelve a la lista."""
    messages.error(request, " ".join(error.messages))
    return redirect("comercial:envasado")


def _entero(texto):
    texto = (texto or "").strip()
    return int(texto) if texto.isdigit() else None


def _fecha(texto):
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


# ---- la lista (pasos 2 y 2a) ----


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def lista(request):
    """«Envasado» (`tabEnvasado`): las entregas «a realizar» de los invernaderos del Agrónomo, por fecha programada, con los filtros de invernadero (si tiene más de uno) y de fecha. Formulario
    GET común con «Filtrar» (sin JavaScript funciona igual); con HTMX solo se redibuja la tabla. No escribe."""
    invernadero_id = _entero(request.GET.get("invernadero"))
    fecha = _fecha(request.GET.get("fecha"))
    invernaderos = envasado.invernaderos_para_envasar(request.user)
    filas = envasado.entregas_para_envasar(request.user, invernadero_id=invernadero_id, fecha=fecha)
    contexto = {
        "filas": filas,
        "invernaderos": invernaderos if len(invernaderos) > 1 else [],
        "invernadero_id": str(invernadero_id or ""),
        "fecha": fecha.isoformat() if fecha else "",
        "hay_filtros": bool(invernadero_id or fecha),
        "activa": "ordenes",
    }
    return render(request, "comercial/envasado/_tabla.html" if _es_htmx(request) else "comercial/envasado/lista.html", contexto)


# ---- la carga (pasos 4 a 6) y la confirmación (pasos 9 a 11) ----


def _contexto(request, entrega_id, carga=None, busqueda="", generales=()):
    """Lo que necesita la carga: los datos del servicio (la entrega, los envases ofrecidos, las filas con su error, la huella y los avisos). Solo lectura."""
    datos = envasado.datos_de_envasado(request.user, entrega_id, carga, busqueda)
    return {
        "datos": datos,
        "fila": datos.fila,
        "busqueda": busqueda,
        "generales": list(generales),
        "hay_errores": any(f.error for f in datos.filas),
        "modifica": any(f.anterior is not None for f in datos.filas) or datos.fila.tiene_envasado,
        "activa": "ordenes",
    }


def _pagina(request, entrega_id, carga=None, busqueda="", generales=()):
    """La página completa de la carga o, con HTMX, solo el bloque del formulario. Una entrega que ya no está «a realizar» (10a) vuelve a la lista con su estado."""
    try:
        contexto = _contexto(request, entrega_id, carga, busqueda, generales)
    except ValidationError as error:
        if _codigos(error) & SIN_SALIDA:
            return _a_la_lista(request, error)
        raise
    return render(request, "comercial/envasado/_carga_formulario.html" if _es_htmx(request) else "comercial/envasado/carga.html", contexto)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def entrega(request, entrega_id):
    """«Planificar / modificar envasado» (`VIEWS.env`). El GET abre la carga con las reservas vigentes (3a) o vacía; el POST confirma (paso 9): vuelve a verificar todo bajo bloqueo y escribe.
    10a (ya no «a realizar» o en curso) vuelve a la lista; 10c (otra persona cambió el envasado) vuelve a abrir la carga con las reservas vigentes; 10b y los errores de las filas
    conservan lo cargado."""
    if request.method != "POST":
        return _pagina(request, entrega_id)
    carga = CargaDeEnvasado.desde_post(entrega_id, request.POST)
    busqueda = request.POST.get("busqueda", "")
    try:
        planificada = envasado.planificar_envasado(request.user, carga)
    except ValidationError as error:
        codigos = _codigos(error)
        if codigos & SIN_SALIDA:
            return _a_la_lista(request, error)
        if "envasado_cambio" in codigos:
            messages.error(request, " ".join(error.messages))
            return redirect("comercial:envasado_entrega", entrega_id=entrega_id)
        return _pagina(request, entrega_id, carga, busqueda, _generales(error))
    messages.success(request, f"Envasado de {planificada.codigo} planificado.")
    return redirect("comercial:envasado")


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def calcular(request, entrega_id):
    """Redibuja la carga con lo que escribió la persona (agregar, quitar, buscar o actualizar) y lo disponible de cada envase. **No escribe.**"""
    carga = CargaDeEnvasado.desde_post(entrega_id, request.POST)
    return _pagina(request, entrega_id, carga, request.POST.get("busqueda", ""))


@rol_requerido(AGRONOMO)
@never_cache
@require_POST
def revisar(request, entrega_id):
    """«Revisar» (paso 8): el resumen como página (anterior → nueva, quitados y el aviso de 8b). Con errores de fila (6a, 6b), sin envases (8a) o sin cambios (8c) vuelve a la carga con el
    mensaje. **No escribe.**"""
    carga = CargaDeEnvasado.desde_post(entrega_id, request.POST)
    busqueda = request.POST.get("busqueda", "")
    try:
        resumen = envasado.resumen_de_envasado(request.user, carga)
    except ValidationError as error:
        if _codigos(error) & SIN_SALIDA:
            return _a_la_lista(request, error)
        return _pagina(request, entrega_id, carga, busqueda, _generales(error))
    contexto = {"resumen": resumen, "fila": resumen.fila, "carga": carga, "busqueda": busqueda, "activa": "ordenes"}
    return render(request, "comercial/envasado/resumen.html", contexto)
