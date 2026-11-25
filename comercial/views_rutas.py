# Vistas de la ruta y la concreción de entregas (COM-06a; docs/casos_de_uso/comercial/rutas.md, «Pantallas»): «Mi ruta» del Transportista, iniciar y finalizar la ruta, el intento fallido y concretar
# una entrega (el Transportista, con envío; el Vendedor, un retiro). Las vistas SOLO orquestan: arman los datos del pedido, llaman al servicio (`rutas.py`, `concrecion.py`) y renderizan. Sin JavaScript todo
# funciona: cada ventana del prototipo es una página, «Ver resumen» manda el formulario a `calcular/` (que no escribe) y vuelve la misma página con el resumen; con HTMX solo se redibuja el resumen.
# Nunca se valida ni se recalcula al tipear (`.claude/rules/interfaz.md`). Los errores por campo van debajo de su campo; el aviso breve al terminar es un `messages.success` (D-29).

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import PagoCliente
from comercial.servicios import concrecion, rutas
from core.acceso import rol_requerido
from core.models import Usuario

TRANSPORTISTA = Usuario.Rol.TRANSPORTISTA
VENDEDOR = Usuario.Rol.VENDEDOR

# Los códigos con los que el servicio avisa que la ruta o la entrega ya no se pueden operar: no hay dato que corregir, se vuelve a la pantalla de origen con el mensaje.
SIN_SALIDA = {"entrega_no_concretable", "ruta_no_iniciada", "ruta_ya_iniciada", "sin_vehiculo", "vehiculo_inactivo", "sin_entregas_de_ruta", "invernadero_inactivo"}


def _codigos(error):
    if hasattr(error, "error_dict"):
        return {e.code for lista in error.error_dict.values() for e in lista}
    return {e.code for e in error.error_list}


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _params(error):
    """Los `params` del primer error que los trae (`ruta_cambio`, `ruta_con_entregas_pendientes`)."""
    lista = [e for lista in error.error_dict.values() for e in lista] if hasattr(error, "error_dict") else error.error_list
    return next((e.params for e in lista if e.params), {}) or {}


def _a_la_ruta(request, error):
    """Un rechazo sin salida (la entrega ya no es concretable, la ruta ya no existe…): el mensaje y a «Mi ruta» (o a la lista de entregas del Vendedor)."""
    messages.error(request, " ".join(error.messages))
    return redirect("comercial:ruta" if request.user.rol == TRANSPORTISTA else "comercial:entregas")


# ---- «Mi ruta» ----


@rol_requerido(TRANSPORTISTA)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def ruta(request):
    """«Mi ruta» (`VIEWS.ruta` del prototipo): el vehículo, las entregas de hoy (las demoradas primero, después por localidad), el peso y la capacidad, las próximas y, según la situación,
    «Iniciar ruta» o «Finalizar ruta». Solo el Transportista; no escribe."""
    return render(request, "comercial/rutas/mi_ruta.html", {"datos": rutas.ruta_del_dia(request.user)})


@rol_requerido(TRANSPORTISTA)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def iniciar(request):
    """«Iniciar ruta» (`MODALS.inirut`): el GET muestra la confirmación con la lista (pasos 2 y 3, extensiones 2b y 2c); el POST inicia (paso 5). Si las entregas cambiaron (5c) vuelve a esta página
    con lo agregado y lo quitado; el resto de los rechazos (5a, 5b, 5d) vuelven a «Mi ruta» con el mensaje."""
    if request.method != "POST":
        return render(request, "comercial/rutas/iniciar.html", {"datos": rutas.ruta_del_dia(request.user)})
    try:
        rutas.iniciar_ruta(request.user, request.POST.get("huella", ""))
    except ValidationError as error:
        if "ruta_cambio" in _codigos(error):
            parametros = _params(error)
            return render(
                request,
                "comercial/rutas/iniciar.html",
                {"datos": rutas.ruta_del_dia(request.user), "cambio": parametros, "error": " ".join(error.messages)},
            )
        return _a_la_ruta(request, error)
    messages.success(request, "Ruta iniciada. Ya podés concretar tus entregas.")
    return redirect("comercial:ruta")


@rol_requerido(TRANSPORTISTA)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def finalizar(request):
    """«Finalizar ruta» (`MODALS.finrut`): con entregas pendientes, cada una con «Concretar» e «Intento fallido» (regla 1 de COM-FIN-RUT); sin pendientes, la confirmación. El POST finaliza."""
    if request.method == "POST":
        try:
            rutas.finalizar_ruta(request.user)
        except ValidationError as error:
            if "ruta_con_entregas_pendientes" not in _codigos(error):
                return _a_la_ruta(request, error)
            messages.error(request, " ".join(error.messages))
            return redirect("comercial:ruta_finalizar")
        messages.success(request, "Ruta finalizada.")
        return redirect("comercial:ruta")
    return render(request, "comercial/rutas/finalizar.html", {"pendientes": rutas.pendientes_de_la_ruta(request.user), "datos": rutas.ruta_del_dia(request.user)})


# ---- intento fallido ----


@rol_requerido(TRANSPORTISTA)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def intento_fallido(request, entrega_id):
    """«Intento fallido» (`MODALS.fallo`): motivo de la lista (obligatorio) y descripción opcional. Sin JavaScript, una página. Un rechazo sin salida vuelve a «Mi ruta»; un error de campo, a la página."""
    try:
        fila = rutas.entrega_de_la_ruta(request.user, entrega_id)
    except ValidationError as error:  # 14a: la entrega ya no está en la ruta (p. ej. ya registró el intento y pasó a mañana)
        return _a_la_ruta(request, error)
    contexto = {"fila": fila, "motivos": rutas.IntentoFallido.Motivo.choices, "motivo": "", "descripcion": ""}
    if request.method == "POST":
        contexto["motivo"], contexto["descripcion"] = request.POST.get("motivo", ""), request.POST.get("descripcion", "")
        try:
            rutas.registrar_intento_fallido(request.user, entrega_id, contexto["motivo"], contexto["descripcion"])
        except ValidationError as error:
            if _codigos(error) & SIN_SALIDA:
                return _a_la_ruta(request, error)
            errores = {campo: [e.message for e in lista] for campo, lista in error.error_dict.items()} if hasattr(error, "error_dict") else {"__all__": error.messages}
            contexto["generales"] = errores.pop("__all__", [])  # una plantilla no puede leer una clave que empieza con guion bajo
            contexto["errores"] = errores
            return render(request, "comercial/rutas/intento_fallido.html", contexto)
        messages.success(request, f"Intento fallido registrado. {fila.codigo} pasa a mañana.")
        return redirect("comercial:ruta")
    return render(request, "comercial/rutas/intento_fallido.html", contexto)


# ---- concretar una entrega ----


def _volver(request):
    """A dónde vuelve «Volver»: «Mi ruta» para el Transportista; la lista de entregas para el Vendedor (retiro)."""
    return reverse("comercial:ruta") if request.user.rol == TRANSPORTISTA else reverse("comercial:entregas")


def _pagina(request, entrega_id, datos, *, resumen=None, error=""):
    """La pantalla de concretar (pasos 4 a 12, una sola página con sus pasos): el formulario con lo que cargó la persona y, si se pidió, el resumen con la huella. Los errores por campo del resumen
    salen debajo de cada campo."""
    if resumen is None:
        resumen = concrecion.resumen_de_concrecion(request.user, entrega_id, datos)
    contexto = {
        "resumen": resumen,
        "datos": datos,
        "form": _formulario(resumen, datos),
        "mostrar_resumen": False,
        "error": error,
        "volver": _volver(request),
        "medios": PagoCliente.Medio.choices,
        "es_retiro": resumen.entrega.es_retiro,
    }
    return contexto


def _mensajes(resumen, campo):
    """Los textos de error de un campo del resumen."""
    return [mensaje for _, mensaje in resumen.errores.get(campo, [])]


def _formulario(resumen, datos):
    """Lo que dibuja el formulario: por línea y por envase, el valor que cargó la persona (o la propuesta) y los errores de su campo. Las líneas quitadas (planificada 0) no se muestran."""
    lineas = []
    for lr in resumen.lineas:
        pk = lr.leida.linea.pk
        if lr.leida.planificada == 0:
            continue
        lineas.append(
            {
                "lr": lr,
                "pk": pk,
                "llego": datos.llego.get(pk, str(lr.leida.planificada)),
                "acepta": datos.acepta.get(pk, True),
                "recibio": datos.recibio.get(pk, ""),
                "e_llego": _mensajes(resumen, f"llego_{pk}"),
                "e_recibio": _mensajes(resumen, f"recibio_{pk}"),
            }
        )
    envases = [
        {
            "e": e,
            "pk": e.existencia.pk,
            "utilizada": datos.utilizada.get(e.existencia.pk, f"{e.reservada.normalize():f}"),
            "devuelta": datos.devuelta.get(e.existencia.pk, ""),
            "confirmo": e.existencia.pk in datos.confirmo_exceso,
            "e_utilizada": _mensajes(resumen, f"utilizada_{e.existencia.pk}"),
            "e_devuelta": _mensajes(resumen, f"devuelta_{e.existencia.pk}"),
        }
        for e in resumen.envases
    ]
    ofrecidos = (
        [
            {"existencia": i, "pk": i.pk, "valor": datos.declarado.get(i.pk, ""), "errores": _mensajes(resumen, f"declarado_{i.pk}")}
            for i in resumen.lectura.ofrecidos.values()
        ]
        if resumen.sin_envasado
        else []
    )
    return {"lineas": lineas, "envases": envases, "ofrecidos": ofrecidos, "e_envases": _mensajes(resumen, "envases"), "e_medio": _mensajes(resumen, "medio_pago")}


@rol_requerido(TRANSPORTISTA, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def concretar(request, entrega_id):
    """«Concretar entrega» (`VIEWS.cncent`). El GET muestra la pantalla con lo propuesto; el POST confirma (paso 14): vuelve a verificar todo bajo bloqueo y registra. Un rechazo sin salida (14a) vuelve
    a «Mi ruta» o a la lista; un cambio simultáneo o un error de campo vuelve a la pantalla con los datos cargados y lo que hay que corregir."""
    if request.method != "POST":
        try:
            contexto = _pagina(request, entrega_id, concrecion.DatosDeConcrecion())
        except ValidationError as error:
            return _a_la_ruta(request, error)
        return render(request, "comercial/rutas/concretar.html", contexto)
    datos = concrecion.datos_de_concrecion(request.POST)
    try:
        entrega = concrecion.concretar_entrega(request.user, entrega_id, datos, request.POST.get("huella", ""))
    except ValidationError as error:
        if _codigos(error) & SIN_SALIDA:
            return _a_la_ruta(request, error)
        try:
            contexto = _pagina(request, entrega_id, datos, error=" ".join(error.messages) if "cambio_simultaneo" in _codigos(error) else "")
        except ValidationError as otro:
            return _a_la_ruta(request, otro)
        contexto["mostrar_resumen"] = not contexto["resumen"].hay_errores and "cambio_simultaneo" not in _codigos(error)
        return render(request, "comercial/rutas/concretar.html", contexto)
    texto = f"{entrega.codigo} concretada."
    cobrado = PagoCliente.objects.filter(compra_venta_id=entrega.contrato_entrega_id, estado_pago="vigente").first()
    if cobrado is not None and entrega.pk:
        texto += f" Total cobrado: ${cobrado.monto_pagado}."
    messages.success(request, texto)
    return redirect("comercial:entrega_comprobante", entrega.pk)


@rol_requerido(TRANSPORTISTA, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def concretar_calcular(request, entrega_id):
    """«Ver resumen» (paso 12): valida lo cargado y calcula los montos, sin escribir nada. Con HTMX devuelve solo el resumen; sin él, la página completa con el resumen. Con errores no hay botón de confirmar."""
    datos = concrecion.datos_de_concrecion(request.POST)
    try:
        contexto = _pagina(request, entrega_id, datos)
    except ValidationError as error:
        return _a_la_ruta(request, error)
    contexto["mostrar_resumen"] = True
    return render(request, "comercial/rutas/_resumen.html" if _es_htmx(request) else "comercial/rutas/concretar.html", contexto)


@rol_requerido(TRANSPORTISTA, VENDEDOR)
@never_cache
@require_safe
def comprobante(request, entrega_id):
    """La pantalla final de una entrega concretada (paso 16): el total cobrado y el comprobante para imprimir (para el cliente sin correo). Solo quien la concretó: el Transportista asignado o el Vendedor."""
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import get_object_or_404

    from comercial.models import Entrega

    entrega = get_object_or_404(Entrega.objects.select_related("contrato_entrega__cliente"), pk=entrega_id)
    if entrega.estado_orden != "concretada" or not _es_suya(request.user, entrega):
        raise PermissionDenied("Tu cuenta no tiene acceso a esta acción.")
    contexto = concrecion.contexto_del_comprobante(entrega)
    contexto.update({"entrega": entrega, "volver": _volver(request), "estado_aviso": entrega.estado_aviso_cliente})
    return render(request, "comercial/rutas/comprobante.html", contexto)


def _es_suya(usuario, entrega):
    """El Transportista asignado (con envío) o el Vendedor del contrato (en un retiro)."""
    if usuario.rol == TRANSPORTISTA:
        return entrega.transportista_id == usuario.pk
    return entrega.es_retiro and entrega.contrato_entrega.vendedor_id == usuario.pk
