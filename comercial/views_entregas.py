# Vistas de «Entregas» de Comercial: la pestaña (COM-05a1) y asignar o cambiar el transportista (COM-ASG-TRP, COM-05b; al final). La pestaña (COM-05a1; docs/casos_de_uso/comercial/entregas.md, «Pantallas»): la lista de entregas del Gerente y del Vendedor, con filtros en la URL
# (estado, invernadero, transportista y los dos parámetros `?entrega=` de la alerta y `?transportista=` de «Logística»). Acciones: «Ver contrato» y «Asignar»/«Cambiar transportista» (COM-05b); «Concretar retiro» es de COM-06. La vista solo orquesta: arma los filtros, llama al servicio y renderiza; sin JavaScript todo funciona (el formulario es un GET común con «Filtrar»;
# con HTMX solo se redibuja la tabla). Nunca se filtra mientras se tipea (`.claude/rules/interfaz.md`).

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import Entrega
from comercial.servicios import atencion, entregas
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import stock

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def lista(request):
    """Pestaña «Entregas» (`tabEntregas` del prototipo): las entregas del alcance del usuario, de a 50, con sus filtros. El Gerente ve todas y el Vendedor las de sus contratos; el
    Agrónomo y el Capataz reciben 403 (SEG-13). Con HTMX devuelve solo la tabla. No audita."""
    filtros = entregas.FiltrosDeEntregas.desde_get(request.GET)
    datos = entregas.lista_de_entregas(request.user, filtros, stock.hoy())
    contexto = {
        "datos": datos,
        "filtros": filtros,
        "estados": entregas.ESTADOS_DE_LA_LISTA,
        "sin_transportista": entregas.SIN_TRANSPORTISTA,
        "es_gerente": request.user.rol == GERENTE,
        "consulta": urlencode({k: v for k, v in request.GET.items() if k != "pagina"}),
    }
    plantilla = "comercial/entregas/_tabla.html" if request.headers.get("HX-Request") == "true" else "comercial/entregas/lista.html"
    return render(request, plantilla, contexto)


# ---- COM-ASG-TRP · Asignar / Cambiar transportista (COM-05b) ----
# La vista solo orquesta: arma la elección del pedido, llama al servicio y renderiza; las reglas son del servicio. Con HTMX, al elegir un transportista se redibuja solo la tarjeta «Cómo queda»
# (`calcular/`, que no escribe); sin JavaScript, «Ver cómo queda» manda el mismo formulario a `calcular/` y vuelve la página con la tarjeta. Nunca se valida al tipear (`.claude/rules/interfaz.md`).

# Los códigos con los que el servicio avisa que la entrega ya no se puede asignar o cambió: no hay elección que corregir, se vuelve a la lista con el mensaje (extensiones 3a y 8a).
SIN_SALIDA = {"entrega_sin_envio", "entrega_no_a_realizar", "entrega_en_curso", "entrega_cambio", "invernadero_inactivo"}


def _codigos(error):
    if hasattr(error, "error_dict"):
        return {e.code for lista in error.error_dict.values() for e in lista}
    return {e.code for e in error.error_list}


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _pagina_de_asignacion(request, entrega_id, seleccionado="", error=""):
    """La pantalla con los candidatos de ahora y, si se eligió uno que cumple, «Cómo queda». Un error del campo (8b, `transportista_no_cumple`) se muestra bajo la tabla."""
    datos = entregas.datos_de_asignacion(request.user, entrega_id)
    como, error_transportista = None, error
    if seleccionado and not error:
        try:
            como = entregas.resumen_de_asignacion(request.user, entrega_id, seleccionado)
        except ValidationError as problema:
            error_transportista = " ".join(problema.messages)
    contexto = {"datos": datos, "seleccionado": str(seleccionado or ""), "como": como, "error_transportista": error_transportista, "es_gerente": request.user.rol == GERENTE}
    return render(request, "comercial/entregas/asignar.html", contexto)


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def asignar(request, entrega_id):
    """«Asignar / Cambiar transportista» (`VIEWS.asg`). El GET muestra la entrega y sus candidatos. El POST confirma (paso 7): vuelve a verificar todo bajo bloqueo y escribe. 3a y 8a (la entrega
    ya no se puede asignar o cambió) vuelven a la lista con el mensaje; 8b (el elegido ya no cumple) vuelve a la pantalla con los candidatos actualizados y el motivo; sin elegir, el error del campo."""
    if request.method != "POST":
        return _pagina_de_asignacion(request, entrega_id)
    try:
        entrega = entregas.asignar_transportista(request.user, entrega_id, request.POST.get("transportista", ""), request.POST.get("huella", ""))
    except ValidationError as error:
        if _codigos(error) & SIN_SALIDA:
            messages.error(request, " ".join(error.messages))
            return redirect("comercial:entregas")
        return _pagina_de_asignacion(request, entrega_id, error=" ".join(error.messages))
    texto = f"{entrega.codigo} asignada a {entrega.transportista.get_full_name()}."
    if entrega.se_reprogramo:
        texto += " Se reprogramó para hoy y se avisó el retraso."
    messages.success(request, texto)
    return redirect("comercial:entregas")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def asignar_calcular(request, entrega_id):
    """«Cómo queda» (paso 6) para el transportista elegido, sin escribir nada: con HTMX, solo la tarjeta; sin él, la página completa con la tarjeta («Ver cómo queda»)."""
    seleccionado = request.POST.get("transportista", "").strip()
    if not _es_htmx(request):
        return _pagina_de_asignacion(request, entrega_id, seleccionado)
    como, error = None, ""
    if seleccionado:
        try:
            como = entregas.resumen_de_asignacion(request.user, entrega_id, seleccionado)
        except ValidationError as problema:
            error = " ".join(problema.messages)
    return render(request, "comercial/entregas/_como_queda.html", {"como": como, "error_transportista": error})


# ---- COM-ATN-ENR · Atender entrega no reconocida (COM-06b) ----
# El Gerente abre la alerta crítica que crea la respuesta «no recibí» del cliente (la campana lo trae acá), ve todo lo que generó la entrega y registra qué averiguó. La vista solo orquesta: arma la ficha,
# llama al servicio y renderiza; las reglas son del servicio. Sin JavaScript funciona igual (una página y un POST).


def _pagina_de_atencion(request, alerta_id, errores=None, resultado="", descripcion=""):
    ficha = atencion.ficha_de_no_reconocida(request.user, alerta_id)
    errores = errores or {}
    return render(
        request, "comercial/entregas/no_reconocida.html", {"ficha": ficha, "errores": errores, "generales": errores.get("__all__", []), "resultado": resultado, "descripcion": descripcion}
    )


@rol_requerido(GERENTE)
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def no_reconocida(request, entrega_id):
    """`/comercial/entregas/<id>/no-reconocida/` (COM-ATN-ENR): GET muestra la entrega con todo lo que generó (regla 1) y el formulario del resultado; POST resuelve la alerta (regla 2) y vuelve a la ficha
    del suministro con el aviso. Solo el Gerente (los demás roles, 403). Una entrega sin alerta activa (ya se resolvió, o nunca la hubo) vuelve a la ficha del suministro con el mensaje."""
    entrega = get_object_or_404(Entrega, pk=entrega_id)
    volver = redirect("comercial:suministro", entrega.contrato_entrega_id)
    alerta_id = atencion.alerta_activa_de(entrega.pk)
    if alerta_id is None:
        messages.info(request, f"{entrega.codigo} no tiene una alerta de entrega no reconocida para atender.")
        return volver
    try:
        if request.method != "POST":
            return _pagina_de_atencion(request, alerta_id)
        resultado, descripcion = request.POST.get("resultado", ""), request.POST.get("descripcion", "")
        try:
            atencion.atender_entrega_no_reconocida(request.user, alerta_id, resultado, descripcion)
        except ValidationError as error:
            if "alerta_resuelta" in _codigos(error):
                raise
            errores = {campo: [e.messages[0] for e in lista] for campo, lista in error.error_dict.items()}
            return _pagina_de_atencion(request, alerta_id, errores, resultado, descripcion.strip())
    except ValidationError as error:  # la alerta se resolvió mientras tanto
        messages.error(request, " ".join(error.messages))
        return volver
    messages.success(request, f"La alerta de {entrega.codigo} quedó resuelta.")
    return volver
