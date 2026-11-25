# Vistas de la cobranza de suministros (COM-08a; docs/casos_de_uso/comercial/cobranza.md, «Pantallas»): la pestaña «Cobranza» («Por cobrar» y «Cobros registrados»), «Registrar cobro» (con su resumen), la ficha del
# cobro, el comprobante imprimible y «Reenviar comprobante». Las vistas SOLO orquestan: arman los datos del pedido, llaman al servicio (`cobranza`) y renderizan. Nada se valida ni se recalcula mientras se tipea
# (`.claude/rules/interfaz.md`): marcar una entrega y los filtros son selectores que redibujan el cuerpo sin validar (HTMX, con `show:none`); «Calcular total» es el respaldo sin JavaScript; las reglas corren en
# «Revisar y registrar» (el resumen, que no escribe) y en «Confirmar cobro». Vendedor y Gerente; el Vendedor, solo sus contratos (403 con mensaje fuera de ellos). COM-08b suma «Anular» (solo el Gerente; una página,
# como «Anular resolución» de COM-07a) y la fecha del cobro anulado en «Registrar cobro» (7a: `?anulacion=<id>` y la casilla «Usar la fecha del cobro anulado»).

from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import PagoCliente
from comercial.servicios import cobranza
from comercial.servicios.compra_ventas import texto_de_pesos
from comercial.servicios.cobranza import DatosDeCobro, FiltrosDeCobranza, FiltrosDeCobros
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import stock

GERENTE, VENDEDOR = Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR
MEDIOS = PagoCliente.Medio.choices


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _codigos(error):
    if hasattr(error, "error_dict"):
        return {e.code for lista in error.error_dict.values() for e in lista}
    return {e.code for e in error.error_list}


def _mensaje(error):
    return " ".join(error.messages)


# ---- la pestaña «Cobranza» ----


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_safe
def lista(request):
    """`/comercial/cobranza/` (`tabCobranza`): dos subpestañas, «Por cobrar» (los clientes con deuda, cada uno con sus entregas, de la que vence primero a la última) y «Cobros registrados». Son enlaces: cada una es
    una página y funciona sin JavaScript. Un filtro mal formado se ignora."""
    hoy = stock.hoy()
    vista = "cobros" if request.GET.get("vista") == "cobros" else "pendientes"
    contexto = {"vista": vista, "es_gerente": request.user.rol == GERENTE, "hoy": hoy}
    if vista == "cobros":
        estado = request.GET.get("estado", "")
        filtros = FiltrosDeCobros(estado=estado if estado in ("vigente", "anulado") else "")
        contexto["datos"] = cobranza.cobros_registrados(request.user, filtros, request.GET.get("pagina"))
        contexto["filtros"] = filtros
    else:
        contexto["grupos"] = cobranza.clientes_con_deuda(request.user, hoy)
    return render(request, "comercial/cobranza/lista.html", contexto)


# ---- «Registrar cobro» ----


def _filtros(post):
    """Los filtros de «Entregas que paga»: el contrato y el estado de pago."""
    contrato = (post.get("contrato") or "").strip()
    estado = (post.get("estado") or "").strip()
    return FiltrosDeCobranza(contrato_id=int(contrato) if contrato.isdigit() else None, estado=estado if estado in ("pendiente", "en_mora") else "")


def _contexto(request, datos, filtros, *, errores=None, error="", resumen=None):
    """El contexto de la pantalla: los clientes con deuda (para elegir), el cliente elegido con sus entregas cobrables (filtradas), lo marcado, el total parcial y los errores. No valida nada."""
    hoy = stock.hoy()
    errores = errores or {}
    grupos = cobranza.clientes_con_deuda(request.user, hoy)
    cliente = next((g for g in grupos if str(g.cliente_id) == str(datos.cliente_id)), None)
    anulacion = _anulacion_de(request, datos)
    usa_fecha = bool(anulacion is not None and anulacion.usa_fecha and datos.usar_fecha_anulada)  # 7a: con la casilla, la fecha y el atraso son los del cobro anulado
    fecha_pago = anulacion.fecha if usa_fecha else hoy
    todas, filas = [], []
    if cliente is not None:
        todas = cobranza.entregas_cobrables(request.user, cliente.cliente_id, hoy, fecha_pago=fecha_pago)
        filas = cobranza.entregas_cobrables(request.user, cliente.cliente_id, hoy, filtros, fecha_pago=fecha_pago)
        if usa_fecha:  # con la fecha del cobro anulado solo se pueden elegir las entregas de ese cobro
            propias = set(anulacion.entrega_ids)
            todas, filas = [f for f in todas if f.entrega_id in propias], [f for f in filas if f.entrega_id in propias]
    marcadas = {str(i) for i in datos.entrega_ids}
    elegidas = [f for f in todas if str(f.entrega_id) in marcadas]
    visibles = {f.entrega_id for f in filas}
    return {
        "grupos": grupos,
        "cliente": cliente,
        "cliente_fijo": bool(getattr(request, "_cliente_fijo", False)),
        "filas": filas,
        "contratos": sorted({(f.contrato_id, f.contrato_codigo) for f in todas}, key=lambda c: c[1]),
        "datos": datos,
        "filtros": filtros,
        "marcadas": marcadas,
        "ocultas": [f.entrega_id for f in elegidas if f.entrega_id not in visibles],  # elegidas que el filtro de ahora no muestra: siguen elegidas
        "elegidas": elegidas,
        "base": sum((f.monto_a_cobrar for f in elegidas), Decimal("0.00")),
        "indemnizacion": sum((f.indemnizacion for f in elegidas), Decimal("0.00")),
        "total": cobranza.total_del_cobro(elegidas),
        "hay_pendientes": any(f.solicitudes_pendientes for f in elegidas),
        "medios": MEDIOS,
        "errores": errores,
        "error": error,
        "resumen": resumen,
        "hoy": hoy,
        "anulacion": anulacion,
        "usa_fecha": usa_fecha,
        "fecha_pago": fecha_pago,
    }


def _anulacion_de(request, datos):
    """7a: la anulación que trae el pedido (`AnulacionParaRegistrar`) o `None` si no hay, no es de un cobro, ya se usó o el actor no es el Gerente (en esos casos el servicio rechaza el cobro con su código)."""
    if not str(datos.anulacion_id or "").isdigit():
        return None
    try:
        return cobranza.anulacion_para_registrar(request.user, int(datos.anulacion_id))
    except (ValidationError, PermissionDenied, Http404):
        return None


def _datos_de_get(request):
    """Lo que trae la URL: `?cliente=` (desde «Registrar cobro» de un grupo o de una ficha) o `?entrega=` (desde la alerta: 1a de COM-REG-CBR, con esa entrega ya elegida)."""
    anulacion = (request.GET.get("anulacion") or "").strip()
    if anulacion.isdigit():  # paso 7 de COM-ANL-CBR: «Registrar el cobro correcto»: el cliente y las entregas del cobro anulado ya elegidos y, si el cliente pagó ese día, la casilla marcada
        x = cobranza.anulacion_para_registrar(request.user, int(anulacion))  # 403 (no es el Gerente) / 404 / «ya se registró» (ValidationError: la pantalla lo informa)
        request._cliente_fijo = True
        return DatosDeCobro(cliente_id=str(x.cliente_id), entrega_ids=[str(i) for i in x.entrega_ids], medio_pago="", anulacion_id=x.anulacion.pk, usar_fecha_anulada=x.usa_fecha)
    entrega = (request.GET.get("entrega") or "").strip()
    cliente = (request.GET.get("cliente") or "").strip()
    elegidas = []
    if entrega.isdigit():
        cliente = str(cobranza.cliente_de_la_entrega(request.user, int(entrega)))  # 403 / 404 / 1a1 (ya pagada)
        elegidas = [entrega]
        request._cliente_fijo = True
    elif cliente.isdigit():
        request._cliente_fijo = True
    return DatosDeCobro(cliente_id=cliente, entrega_ids=elegidas, medio_pago="")


def _pagina(request, contexto):
    """Con HTMX solo el cuerpo (sin mover el scroll); sin él, la página entera."""
    plantilla = "comercial/cobranza/_cuerpo.html" if _es_htmx(request) else "comercial/cobranza/registrar.html"
    return render(request, plantilla, contexto)


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def registrar(request):
    """`/comercial/cobranza/registrar/` (COM-REG-CBR). GET: la pantalla, con el cliente y la entrega que traiga la URL (1a). POST sin `accion`, o con «Calcular total»: vuelve a dibujar el cuerpo con el total,
    sin validar nada (los selectores y el respaldo sin JavaScript). POST con `accion=confirmar`: registra el cobro (paso 10) con la huella del resumen: ya pagada (10a) o cambió algo (10b), vuelve con los datos
    nuevos y lo que pasó; si salió bien, a la ficha del cobro. Un Vendedor que no es de los contratos: 403."""
    if request.method != "POST":
        try:
            datos = _datos_de_get(request)
        except ValidationError as error:  # 1a1: la entrega de la alerta ya está pagada; 7a: el cobro correcto de esa anulación ya se registró
            messages.info(request, _mensaje(error))
            return redirect("comercial:cobranza")
        return render(request, "comercial/cobranza/registrar.html", _contexto(request, datos, FiltrosDeCobranza()))
    datos = cobranza.datos_de_cobro(request.POST)
    filtros = _filtros(request.POST)
    if request.POST.get("accion") != "confirmar":
        request._cliente_fijo = request.POST.get("cliente_fijo") == "1"
        return _pagina(request, _contexto(request, datos, filtros))
    try:
        pago = cobranza.registrar_cobro(request.user, datos, request.POST.get("huella", ""))
    except ValidationError as error:
        codigos = _codigos(error)
        request._cliente_fijo = request.POST.get("cliente_fijo") == "1"
        if codigos & {"entrega_ya_pagada", "cobro_cambio"}:
            # 10a: vuelve al paso 4 con los datos actualizados; 10b: al paso 6 con los montos recalculados. En los dos casos, lo marcado que ya no se puede cobrar se saca.
            cobrables = {str(f.entrega_id) for f in cobranza.entregas_cobrables(request.user, int(datos.cliente_id), stock.hoy())} if str(datos.cliente_id).isdigit() else set()
            datos = DatosDeCobro(datos.cliente_id, [i for i in datos.entrega_ids if str(i) in cobrables], datos.medio_pago, datos.anulacion_id, datos.usar_fecha_anulada)
            return render(request, "comercial/cobranza/registrar.html", _contexto(request, datos, filtros, error=_mensaje(error)))
        return render(request, "comercial/cobranza/registrar.html", _contexto(request, datos, filtros, error=_mensaje(error)))
    messages.success(request, f"{pago.codigo} registrado: {texto_de_pesos(pago.monto_pagado)} cobrados a {pago.cliente.nombre_visible}. El asiento no se genera en esta ronda (contabilidad).")
    return redirect("comercial:cobro", pago.pk)


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def revisar(request):
    """`/comercial/cobranza/registrar/revisar/` (paso 8): valida lo elegido y muestra el resumen (el cliente, las entregas con su monto a cobrar y su indemnización, el total, el medio y la fecha del pago), con
    «Confirmar cobro». **No escribe nada.** Con errores (ninguna entrega, sin medio) vuelve a la pantalla con el error junto al campo; una entrega que ya no se puede cobrar, a la pantalla con lo que pasó."""
    datos = cobranza.datos_de_cobro(request.POST)
    filtros = _filtros(request.POST)
    fijo = request.POST.get("cliente_fijo") == "1"
    request._cliente_fijo = fijo
    try:
        resumen = cobranza.resumen_de_cobro(request.user, datos)
    except ValidationError as error:
        return render(request, "comercial/cobranza/registrar.html", _contexto(request, datos, filtros, error=_mensaje(error)))
    if resumen.hay_errores:
        return render(request, "comercial/cobranza/registrar.html", _contexto(request, datos, filtros, errores=resumen.errores))
    contexto = _contexto(request, datos, filtros, resumen=resumen)
    contexto["medio_texto"] = dict(MEDIOS)[resumen.medio_pago]
    contexto["con_fecha_anulada"] = bool(datos.usar_fecha_anulada and resumen.fecha_pago != stock.hoy())
    return render(request, "comercial/cobranza/resumen.html", contexto)


# ---- la ficha del cobro, el comprobante y «Reenviar» ----


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_safe
def cobro(request, pago_id):
    """`/comercial/cobranza/cobros/<id>/`: la ficha del cobro (el cobro, sus entregas con lo cobrado y el atraso, y el estado del comprobante con «Reenviar» o «Imprimir»). Un cobro de una compra-venta: 404; el de
    un contrato ajeno: 403."""
    return render(request, "comercial/cobranza/ficha.html", {"ficha": cobranza.ficha_de_cobro(request.user, pago_id)})


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_safe
def comprobante(request, pago_id):
    """El comprobante de cobro para imprimir (el cliente sin correo: «Imprimir comprobante»): de uso interno, sin validez fiscal."""
    cobranza.ficha_de_cobro(request.user, pago_id)  # el alcance
    return render(request, "comercial/cobranza/comprobante.html", cobranza.contexto_del_comprobante_de_cobro(pago_id))


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def reenviar_comprobante(request, pago_id):
    """«Reenviar comprobante» (11a): vuelve a mandar el comprobante. Siempre vuelve a la ficha con el resultado."""
    try:
        salio = cobranza.reenviar_comprobante_de_cobro(request.user, pago_id)
    except ValidationError as error:
        messages.error(request, _mensaje(error))
    else:
        if salio:
            messages.success(request, "Se envió el comprobante al cliente.")
        else:
            messages.warning(request, "El comprobante sigue pendiente de envío: se reintenta solo cada día.")
    return redirect("comercial:cobro", pago_id)


# ---- anular un cobro (COM-ANL-CBR; COM-08b) ----


def _pagina_de_anulacion(request, pago_id, *, motivo="", cliente_pago_en_fecha=False, errores=None, error=""):
    """El contexto de «Anular cobro»: qué va a pasar (`datos_de_anulacion_de_cobro`), el motivo y la casilla tal como estaban, y los errores por campo."""
    datos = cobranza.datos_de_anulacion_de_cobro(request.user, pago_id)
    return {"datos": datos, "motivo": motivo, "cliente_pago_en_fecha": cliente_pago_en_fecha, "errores": errores or {}, "generales": (errores or {}).get("__all__", []), "error": error, "hoy": stock.hoy()}


def _errores_por_campo(error):
    """`{campo: [mensajes]}` de un `ValidationError` con `error_dict`."""
    return {campo: [e.message for e in lista] for campo, lista in error.error_dict.items()} if hasattr(error, "error_dict") else {"__all__": error.messages}


@rol_requerido(GERENTE)
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def anular(request, pago_id):
    """`/comercial/cobranza/cobros/<id>/anular/` (COM-ANL-CBR): GET muestra qué va a pasar con cada entrega, el motivo y la casilla «El cliente pagó en esa fecha»; POST anula el cobro (paso 5). Una página sin JavaScript
    (la ventana del prototipo es una página, D-61). Solo el Gerente (el Vendedor recibe 403). Un cobro de compra-venta (1a) o ya anulado (5a) no se anula: mensaje y vuelta. Con éxito vuelve a la ficha del cobro anulado,
    que ofrece «Registrar el cobro correcto»."""
    try:
        if request.method != "POST":
            return render(request, "comercial/cobranza/anular.html", _pagina_de_anulacion(request, pago_id))
        motivo = (request.POST.get("motivo") or "").strip()
        pago_en_fecha = bool(request.POST.get("cliente_pago_en_fecha"))
        try:
            anulacion = cobranza.anular_cobro(request.user, pago_id, motivo, pago_en_fecha, request.POST.get("huella", ""))
        except ValidationError as error:
            if _codigos(error) & {"cobro_de_compra_venta", "cobro_ya_anulado"}:
                raise
            if "cambio_simultaneo" in _codigos(error):  # vuelve al paso 2 con lo que pasa ahora
                return render(request, "comercial/cobranza/anular.html", _pagina_de_anulacion(request, pago_id, motivo=motivo, cliente_pago_en_fecha=pago_en_fecha, error=_mensaje(error)))
            return render(request, "comercial/cobranza/anular.html", _pagina_de_anulacion(request, pago_id, motivo=motivo, cliente_pago_en_fecha=pago_en_fecha, errores=_errores_por_campo(error)))
    except ValidationError as error:
        messages.error(request, _mensaje(error))
        return redirect("comercial:cobro", pago_id) if "cobro_ya_anulado" in _codigos(error) else redirect("comercial:cobranza")
    messages.success(request, f"{anulacion.pago_cliente.codigo} anulado. Sus entregas vuelven a estar sin pagar: ya podés registrar el cobro correcto.")
    return redirect("comercial:cobro", pago_id)
