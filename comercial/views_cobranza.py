# Vistas de la cobranza de suministros (COM-08a; docs/casos_de_uso/comercial/cobranza.md, «Pantallas»): la pestaña «Cobranza» («Por cobrar» y «Cobros registrados»), «Registrar cobro» (con su resumen), la ficha del
# cobro, el comprobante imprimible y «Reenviar comprobante». Las vistas SOLO orquestan: arman los datos del pedido, llaman al servicio (`cobranza`) y renderizan. Nada se valida ni se recalcula mientras se tipea
# (`.claude/rules/interfaz.md`): marcar una entrega y los filtros son selectores que redibujan el cuerpo sin validar (HTMX, con `show:none`); «Calcular total» es el respaldo sin JavaScript; las reglas corren en
# «Revisar y registrar» (el resumen, que no escribe) y en «Confirmar cobro». Vendedor y Gerente; el Vendedor, solo sus contratos (403 con mensaje fuera de ellos).

from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
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
    todas, filas = [], []
    if cliente is not None:
        todas = cobranza.entregas_cobrables(request.user, cliente.cliente_id, hoy)
        filas = cobranza.entregas_cobrables(request.user, cliente.cliente_id, hoy, filtros)
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
    }


def _datos_de_get(request):
    """Lo que trae la URL: `?cliente=` (desde «Registrar cobro» de un grupo o de una ficha) o `?entrega=` (desde la alerta: 1a de COM-REG-CBR, con esa entrega ya elegida)."""
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
        except ValidationError as error:  # 1a1: la entrega de la alerta ya está pagada
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
            datos = DatosDeCobro(datos.cliente_id, [i for i in datos.entrega_ids if str(i) in cobrables], datos.medio_pago)
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
