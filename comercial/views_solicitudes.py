# Vistas de las solicitudes de revisión (COM-07a; docs/casos_de_uso/comercial/solicitudes.md, «Pantallas»): la pestaña «Solicitudes de revisión» (lista), la ficha con el panel del Gerente (evaluar la discrepancia o resolver la
# queja), el resumen, «Anular resolución», el comprobante imprimible y «Reenviar aviso». Las vistas SOLO orquestan: arman los datos del pedido, llaman al servicio (`solicitudes.py`) y renderizan. Sin JavaScript todo funciona:
# «Ver resumen» manda el formulario a `resolver/revisar/` (que no escribe) y vuelve la misma página con el resumen; con HTMX solo se redibuja el resumen. Nada se valida ni se recalcula al tipear (`.claude/rules/interfaz.md`).
# Leer (la lista, la ficha, el comprobante y reenviar el aviso): el Gerente y el Vendedor (este último en lectura). Escribir (resolver y anular): solo el Gerente.

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import solicitudes
from comercial.servicios.solicitudes import FiltrosDeSolicitudes
from core.acceso import rol_requerido
from core.models import Usuario, Vendedor

GERENTE, VENDEDOR = Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR
# El medio del reintegro (6a y 6d): la lista de «Lista de tecnología».
MEDIOS = solicitudes.SolicitudRevision.MedioDeReintegro.choices


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _codigos(error):
    if hasattr(error, "error_dict"):
        return {e.code for lista in error.error_dict.values() for e in lista}
    return {e.code for e in error.error_list}


def _errores(error):
    """Los mensajes de un `ValidationError` por campo: ``{campo: [mensaje]}`` (los de `__all__` son los generales)."""
    if hasattr(error, "error_dict"):
        return {campo: [e.messages[0] for e in lista] for campo, lista in error.error_dict.items()}
    return {"__all__": list(error.messages)}


# ---- la lista ----


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def lista(request):
    """`/comercial/solicitudes/` (COM-CNS-SRV, reglas 1 y 2): la lista de las solicitudes del alcance con los filtros de la URL (formulario GET común: sin JavaScript funciona con «Filtrar»; con HTMX solo se
    redibuja la tabla). El contador de pendientes de la pestaña es solo del Gerente."""
    filtros = FiltrosDeSolicitudes.desde_get(request.GET)
    pagina = solicitudes.lista_de_solicitudes(request.user, filtros, request.GET.get("pagina"))
    consulta = "&".join(f"{k}={v}" for k, v in request.GET.items() if k != "pagina" and v)
    es_gerente = request.user.rol == GERENTE
    vendedores = [(v.pk, f"{v.first_name} {v.last_name}".strip() or v.email) for v in Vendedor.objects.filter(is_active=True).order_by("first_name", "last_name", "pk")] if es_gerente else []
    contexto = {"datos": pagina, "filtros": filtros, "consulta": consulta, "es_gerente": es_gerente, "vendedores": vendedores}
    return render(request, "comercial/solicitudes/_tabla.html" if _es_htmx(request) else "comercial/solicitudes/lista.html", contexto)


# ---- la ficha y el panel del Gerente ----


def _pagina(request, solicitud_id, datos=None, *, mostrar_resumen=False, error="", errores=None, confirmando=False):
    """El contexto de la ficha: la ficha y, para el Gerente con la solicitud pendiente, el panel con lo cargado y, si se pidió, el resumen (pasos 5 y 6)."""
    ficha = solicitudes.ficha_de_solicitud(request.user, solicitud_id)
    datos = datos or solicitudes.DatosDeResolucion()
    resumen = None
    if ficha.puede_evaluar and mostrar_resumen:
        resumen = solicitudes.resumen_de_resolucion(request.user, solicitud_id, datos)
    errores_del_resumen = {campo: [m for _, m in lista] for campo, lista in (resumen.errores.items() if resumen else [])}
    # Lo que bloquea el botón de confirmar: todo error salvo el del medio, que se elige en el mismo resumen.
    bloqueantes = {campo: mensajes for campo, mensajes in errores_del_resumen.items() if campo != "medio_reintegro"}
    return {
        "ficha": ficha,
        "s": ficha.solicitud,
        "datos": datos,
        "resumen": resumen,
        "mostrar_resumen": resumen is not None,
        "errores": {**errores_del_resumen, **(errores or {})},
        "bloqueantes": bloqueantes,
        "error": error,
        "confirmando": confirmando,
        "medios": MEDIOS,
        "es_gerente": ficha.es_gerente,
    }


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_safe
def ficha(request, solicitud_id):
    """`/comercial/solicitudes/<id>/` (COM-CNS-SRV, reglas 3 a 5 y 7): la ficha de una solicitud del alcance (la de un contrato ajeno, 403 con mensaje). Al Gerente con la solicitud pendiente le suma el panel
    «Evaluar la discrepancia» o «Resolver la queja»; al Vendedor, el aviso «La evalúa el Gerente»."""
    return render(request, "comercial/solicitudes/ficha.html", _pagina(request, solicitud_id))


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def resolver_revisar(request, solicitud_id):
    """«Ver resumen» (paso 6): valida lo cargado y calcula el monto y su aplicación, sin escribir nada. Con HTMX devuelve solo el resumen; sin él, la ficha completa con el resumen. Con errores no hay botón de confirmar."""
    datos = solicitudes.datos_de_resolucion(request.POST)
    try:
        contexto = _pagina(request, solicitud_id, datos, mostrar_resumen=True)
    except ValidationError as error:  # ya no está pendiente (1a1, 3a)
        messages.error(request, " ".join(error.messages))
        return redirect("comercial:solicitud", solicitud_id)
    return render(request, "comercial/solicitudes/_resumen.html" if _es_htmx(request) else "comercial/solicitudes/ficha.html", contexto)


@rol_requerido(GERENTE)
@never_cache
@require_POST
def resolver(request, solicitud_id):
    """«Confirmar la decisión» (paso 8 y 5a.4): registra la resolución con todas las verificaciones bajo bloqueo. Resuelta: vuelve a la ficha con el aviso. Ya no pendiente (8a): vuelve a la ficha con la decisión
    tomada. Cambió algún dato desde el resumen (8b): vuelve al paso 4 con los datos nuevos y lo que cambió. Un error de campo vuelve al panel con lo cargado."""
    datos = solicitudes.datos_de_resolucion(request.POST)
    try:
        resuelta = solicitudes.resolver_solicitud(request.user, solicitud_id, datos, request.POST.get("huella", ""))
    except ValidationError as error:
        codigos = _codigos(error)
        if "solicitud_no_pendiente" in codigos:
            messages.error(request, " ".join(error.messages))
            return redirect("comercial:solicitud", solicitud_id)
        cambio = "solicitud_cambio" in codigos
        try:
            contexto = _pagina(request, solicitud_id, datos if not cambio else None, mostrar_resumen=not cambio, error=" ".join(error.messages) if cambio else "", errores=None if cambio else _errores(error), confirmando=True)
        except ValidationError as otro:
            messages.error(request, " ".join(otro.messages))
            return redirect("comercial:solicitud", solicitud_id)
        return render(request, "comercial/solicitudes/ficha.html", contexto)
    if resuelta.estado_solicitud == "aceptada":
        messages.success(request, f"{resuelta.codigo} aceptada: indemnización de {solicitudes._pesos(resuelta.monto_indemnizacion)}. Se avisó al Vendedor y al cliente.")
    else:
        messages.success(request, f"{resuelta.codigo} rechazada. Se avisó al Vendedor y al cliente.")
    return redirect("comercial:solicitud", solicitud_id)


# ---- anular una resolución ----


def _pagina_de_anulacion(request, solicitud_id, *, motivo="", errores=None):
    """El paso 2 de COM-ANL-SRV con el motivo cargado. Una solicitud pendiente no se anula: vuelve a la ficha."""
    datos = solicitudes.datos_de_anulacion(request.user, solicitud_id)
    errores = errores or {}
    return {"datos": datos, "s": datos.solicitud, "motivo": motivo, "errores": errores, "generales": errores.get("__all__", [])}


@rol_requerido(GERENTE)
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def anular(request, solicitud_id):
    """`/comercial/solicitudes/<id>/anular/` (COM-ANL-SRV): GET muestra qué va a pasar (o el bloqueo 2a a 2c con «Volver») y el motivo; POST registra la anulación. Una página sin JavaScript (la ventana del prototipo
    es una página, D-61). Con éxito vuelve a la ficha con la solicitud pendiente y se puede volver a resolver."""
    try:
        if request.method != "POST":
            return render(request, "comercial/solicitudes/anular.html", _pagina_de_anulacion(request, solicitud_id))
        motivo = (request.POST.get("motivo") or "").strip()
        try:
            anulacion = solicitudes.anular_resolucion(request.user, solicitud_id, motivo, request.POST.get("huella", ""))
        except ValidationError as error:
            if _codigos(error) & {"solicitud_no_resuelta"}:
                raise
            return render(request, "comercial/solicitudes/anular.html", _pagina_de_anulacion(request, solicitud_id, motivo=motivo, errores=_errores(error)))
    except ValidationError as error:  # la solicitud no tiene una resolución para anular
        messages.error(request, " ".join(error.messages))
        return redirect("comercial:solicitud", solicitud_id)
    messages.success(request, f"{anulacion.solicitud.codigo} volvió a pendiente de revisión. Ya podés volver a resolverla.")
    return redirect("comercial:solicitud", solicitud_id)


# ---- el comprobante y el aviso al cliente ----


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_safe
def comprobante(request, solicitud_id):
    """El comprobante de indemnización o el aviso al cliente, para imprimir (el cliente sin correo, «Imprimir comprobante»): de uso interno, sin validez fiscal. Solo de una solicitud resuelta del alcance del actor."""
    _, s = solicitudes._del_alcance(request.user, solicitud_id)
    if s.estado_solicitud == "pendiente":
        raise Http404("Esta solicitud todavía no tiene resolución.")
    return render(request, "comercial/solicitudes/comprobante.html", solicitudes.contexto_del_aviso(s.pk))


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def reenviar_aviso(request, solicitud_id):
    """«Reenviar aviso» (9a): vuelve a mandar el comprobante o el aviso al cliente. Siempre vuelve a la ficha con el resultado."""
    try:
        salio = solicitudes.reenviar_aviso(request.user, solicitud_id)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if salio:
            messages.success(request, "Se envió el aviso al cliente.")
        else:
            messages.warning(request, "El aviso sigue pendiente de envío: se reintenta solo cada día.")
    return redirect("comercial:solicitud", solicitud_id)
