# Pasos diarios de compras (CMP-03; D-87 punto 4, H16 y D-56). Los registra ``ComprasConfig.ready()`` con ``core.procesos.registrar_paso_diario``:
#
#   60 ``pedidos_vencidos``                  Pedidos vencidos: avisa del vencimiento o cancela el pedido que nadie cotizó.
#   61 ``recordatorio_de_validez``           Recordatorio de validez de cotizaciones: avisa que mañana vence la primera cotización elegible.
#   62 ``pedidos_sin_cotizacion_elegible``   Pedidos sin cotización elegible: cancela el pedido cuyas cotizaciones ya no se pueden elegir.
#
# Contrato de D-56 (punto 4): ``paso(hoy) -> ResumenDePaso``; idempotentes (el 60 y el 61 guardan en el pedido ``aviso_vencimiento_dado`` y
# ``recordatorio_validez_para``; el 62 y la cancelación del 60 sacan al pedido de «en cotización»); **nunca leen la fecha por su cuenta** (``hoy`` es un parámetro,
# también para la fecha de cierre de una cancelación); una transacción por pedido (``transaction.atomic()``), con el pedido bloqueado y releído (``FOR NO KEY UPDATE``;
# el orden de docs/patrones/bloqueos.md: pedido → cotizaciones → enlaces); y si un pedido falla se registra en el log, los demás siguen y el paso lanza
# ``RuntimeError`` al terminar para que ``proceso_diario`` lo informe como fallido (D-56 punto 5), igual que el paso 10 de inventario.
# Un pedido «vencido» es el «en cotización» con ``fecha_limite_cotizaciones < hoy``: el último día todavía se cotiza (D-88 punto 2). Los avisos son notificaciones
# de la campana (D-42; H21: ``destinatarios_por_destino`` sin excluir a nadie, no hay actor humano) y, junto con las marcas técnicas, no se auditan; las cancelaciones
# sí, con la auditoría de ``cancelar_pedido_automaticamente`` (CMP-02b). ``compras`` no importa de ``comercial`` ni de ``produccion`` (A1 de D-37).

import logging
from datetime import timedelta

from django.db import transaction

from compras.models import Cotizacion, DetalleCotizacion, DetallePedido, EnlaceProveedor, Pedido
from compras.servicios import avisos, cobertura, ordenes
from compras.servicios import pedidos as servicio_de_pedidos
from core import notificaciones
from core.procesos import ResumenDePaso

logger = logging.getLogger("infoponia.proceso_diario")

_UN_DIA = timedelta(days=1)

CODIGO_VENCIDOS = "pedidos_vencidos"
CODIGO_RECORDATORIO = "recordatorio_de_validez"
CODIGO_SIN_ELEGIBLE = "pedidos_sin_cotizacion_elegible"


# ---- comunes ----


def _vencidos(hoy):
    """Los pedidos «en cotización» con la fecha límite anterior a ``hoy`` (consulta sin evaluar)."""
    return Pedido.objects.filter(estado_pedido=Pedido.Estado.EN_COTIZACION, fecha_limite_cotizaciones__lt=hoy)


def _pedido_vencido_bloqueado(pedido_id, hoy):
    """El pedido bloqueado y releído, o ``None`` si ya no es un pedido vencido «en cotización» (otra operación lo resolvió mientras se esperaba)."""
    pedido = Pedido.objects.select_for_update(no_key=True, of=("self",)).get(pk=pedido_id)
    if not pedido.en_cotizacion or pedido.fecha_limite_cotizaciones >= hoy:
        return None
    return pedido


def _propuestas(pedido):
    """Las cotizaciones «propuesta» del pedido, con su proveedor, bloqueadas en orden de id."""
    return list(
        Cotizacion.objects.select_for_update(no_key=True, of=("self",))
        .filter(pedido=pedido, estado_cotizacion=Cotizacion.Estado.PROPUESTA)
        .select_related("proveedor")
        .order_by("id")
    )


def _destinos(pedido):
    """Los invernaderos de destino de los detalles del pedido."""
    return set(DetallePedido.objects.filter(pedido=pedido).values_list("insumo_invernadero__invernadero_id", flat=True))


def _recortar(texto):
    """``texto`` recortado al largo de una notificación."""
    return texto if len(texto) <= notificaciones.LARGO_DETALLE else texto[: notificaciones.LARGO_DETALLE - 1] + "…"


def _avisar(pedido, titulo, texto):
    """H21: la notificación a cada Agrónomo activo de los destinos del pedido y, por cada destino sin Agrónomo activo, al Gerente (sin excluir a nadie)."""
    notificaciones.notificar_a_varios(avisos.destinatarios_por_destino(_destinos(pedido)), titulo, _recortar(texto))


def _correr(codigo, pedido_ids, tratar):
    """Trata cada pedido de ``pedido_ids`` con ``tratar(pedido_id)``, una transacción por pedido (a cargo de ``tratar``). ``tratar`` devuelve ``None`` si el
    pedido ya no corresponde (no cuenta) o ``(creados, resueltos)``. Un pedido que falla se registra y no frena a los demás; al terminar, si alguno falló, lanza
    ``RuntimeError`` (D-56 punto 5). Devuelve ``ResumenDePaso(procesados, creados, resueltos)``."""
    procesados = creados = resueltos = 0
    fallidos = []
    for pedido_id in pedido_ids:
        try:
            resultado = tratar(pedido_id)
        except Exception:  # noqa: BLE001 - un pedido roto no puede dejar a los demás sin tratar (D-56 punto 5)
            logger.exception("Falló el paso diario «%s» con el pedido %s", codigo, pedido_id)
            fallidos.append(pedido_id)
            continue
        if resultado is None:
            continue
        procesados += 1
        creados += resultado[0]
        resueltos += resultado[1]
    if fallidos:
        raise RuntimeError(
            f"El paso «{codigo}» falló con {len(fallidos)} pedido(s) (ids {', '.join(map(str, fallidos))}); los demás se trataron "
            f"({procesados} procesados, {creados} creados, {resueltos} resueltos). Se reintentan en la próxima corrida."
        )
    return ResumenDePaso(procesados, creados, resueltos)


# ---- paso 60: pedidos vencidos ----


def _texto_del_vencimiento(pedido, propuestas):
    """El texto del aviso de vencimiento (regla «Aviso de vencimiento» de CMP-GNR-ODC): «venció la fecha límite del pedido N; hay X cotizaciones para revisar», por cada
    detalle cuántas líneas llegaron y si alcanzan la cantidad mínima y, si algún detalle no se puede cubrir, que el pedido deberá cancelarse."""
    coberturas = cobertura.cobertura(pedido, propuestas)
    lineas = _lineas_por_detalle(propuestas)
    cuantas = len(propuestas)
    texto = f"Venció la fecha límite del pedido {pedido}; hay {cuantas} {'cotización' if cuantas == 1 else 'cotizaciones'} para revisar. "
    por_detalle = []
    for detalle in DetallePedido.objects.filter(pedido=pedido).select_related("insumo_invernadero__insumo", "insumo_invernadero__invernadero").order_by("id"):
        n = lineas.get(detalle.pk, 0)
        alcanza = "alcanza" if coberturas[detalle.pk].cubierto else "no alcanza"
        por_detalle.append(f"{detalle}: {n} {'línea' if n == 1 else 'líneas'}, {alcanza} la cantidad mínima")
    texto += "; ".join(por_detalle) + "."
    if not cobertura.esta_cubierto(coberturas):
        texto += " Como algún detalle no se puede cubrir, el pedido deberá cancelarse."
    return texto


def _lineas_por_detalle(propuestas):
    """``{detalle_pedido_id: cantidad de líneas}`` de las ``propuestas`` (una consulta)."""
    cuenta = {}
    for detalle_id in DetalleCotizacion.objects.filter(cotizacion__in=propuestas).values_list("detalle_pedido_id", flat=True):
        cuenta[detalle_id] = cuenta.get(detalle_id, 0) + 1
    return cuenta


def _tratar_vencido(pedido_id, hoy):
    """Una unidad del paso 60: sin cotizaciones lo cancela («nadie cotizó»); con cotizaciones avisa al Agrónomo, marca el aviso y pasa a «vencido» sus enlaces
    vigentes. Devuelve ``(avisado, cancelado)`` o ``None`` si ya no corresponde."""
    with transaction.atomic():
        pedido = _pedido_vencido_bloqueado(pedido_id, hoy)
        if pedido is None or pedido.aviso_vencimiento_dado:
            return None
        propuestas = _propuestas(pedido)
        if not propuestas:
            cancelado = servicio_de_pedidos.cancelar_pedido_automaticamente(pedido, Pedido.Causa.NADIE_COTIZO, hoy=hoy)
            return (0, 1) if cancelado is not None else None
        vigentes = EnlaceProveedor.objects.select_for_update(no_key=True, of=("self",)).filter(invitacion__pedido=pedido, estado=EnlaceProveedor.Estado.VIGENTE)
        EnlaceProveedor.objects.filter(pk__in=[e.pk for e in vigentes.order_by("id")]).update(estado=EnlaceProveedor.Estado.VENCIDO)
        _avisar(pedido, f"Venció el pedido {pedido}", _texto_del_vencimiento(pedido, propuestas))
        pedido.aviso_vencimiento_dado = True
        pedido.save(update_fields=["aviso_vencimiento_dado"])
        return (1, 0)


def paso_pedidos_vencidos(hoy):
    """Paso 60 (D-87 punto 4): por cada pedido «en cotización» con la fecha límite anterior a ``hoy`` y sin aviso dado, lo cancela por «nadie cotizó» si no tiene
    cotizaciones o avisa al Agrónomo si las tiene. Idempotente. ``ResumenDePaso(procesados=pedidos tratados, creados=pedidos avisados, resueltos=pedidos cancelados)``."""
    ids = list(_vencidos(hoy).filter(aviso_vencimiento_dado=False).order_by("id").values_list("pk", flat=True))
    return _correr(CODIGO_VENCIDOS, ids, lambda pedido_id: _tratar_vencido(pedido_id, hoy))


# ---- paso 61: recordatorio de validez ----


def _tratar_recordatorio(pedido_id, hoy):
    """Una unidad del paso 61: si la primera cotización elegible (la de validez más próxima) vence mañana y todavía no se recordó esa fecha, avisa al Agrónomo y la
    guarda. Devuelve ``(recordados, 0)`` o ``None`` si el pedido ya no corresponde."""
    with transaction.atomic():
        pedido = _pedido_vencido_bloqueado(pedido_id, hoy)
        if pedido is None:
            return None
        elegibles = [c for c in _propuestas(pedido) if ordenes.motivo_no_elegible(c, hoy) is None]
        if not elegibles:
            return (0, 0)
        primera = min(elegibles, key=lambda c: (c.fecha_validez_cotizacion, c.pk))
        if primera.fecha_validez_cotizacion != hoy + _UN_DIA or pedido.recordatorio_validez_para == primera.fecha_validez_cotizacion:
            return (0, 0)
        _avisar(
            pedido,
            f"Vence mañana una cotización del pedido {pedido}",
            f"Mañana vence la cotización de {primera.proveedor} en el pedido {pedido}: si querés elegirla, generá la orden hoy.",
        )
        pedido.recordatorio_validez_para = primera.fecha_validez_cotizacion
        pedido.save(update_fields=["recordatorio_validez_para"])
        return (1, 0)


def paso_recordatorio_de_validez(hoy):
    """Paso 61 (D-87 punto 4): por cada pedido vencido sin resolver, si mañana vence la primera cotización elegible, recuerda al Agrónomo una sola vez por pedido y fecha
    (``recordatorio_validez_para``). Idempotente. ``ResumenDePaso(procesados=pedidos revisados, creados=recordatorios, resueltos=0)``."""
    ids = list(_vencidos(hoy).order_by("id").values_list("pk", flat=True))
    return _correr(CODIGO_RECORDATORIO, ids, lambda pedido_id: _tratar_recordatorio(pedido_id, hoy))


# ---- paso 62: pedidos sin cotización elegible ----


def _tratar_sin_elegible(pedido_id, hoy):
    """Una unidad del paso 62: si ninguna cotización «propuesta» se puede elegir (validez vencida o proveedor inactivo), cancela el pedido. Devuelve ``(0, cancelado)``
    o ``None`` si ya no corresponde."""
    with transaction.atomic():
        pedido = _pedido_vencido_bloqueado(pedido_id, hoy)
        if pedido is None:
            return None
        propuestas = _propuestas(pedido)
        if not propuestas:
            return None  # sin cotizaciones es del paso 60 («nadie cotizó»)
        if any(ordenes.motivo_no_elegible(c, hoy) is None for c in propuestas):
            return (0, 0)
        cancelado = servicio_de_pedidos.cancelar_pedido_automaticamente(
            pedido,
            Pedido.Causa.SIN_COTIZACIONES_ELEGIBLES,
            hoy=hoy,
            aviso=f"Se canceló el pedido {pedido} porque ninguna cotización se puede elegir (validez vencida o proveedor inactivo).",
        )
        return (0, 1) if cancelado is not None else None


def paso_pedidos_sin_cotizacion_elegible(hoy):
    """Paso 62 (D-87 punto 4): cancela («sin cotizaciones elegibles») cada pedido vencido sin resolver que tiene cotizaciones «propuesta» pero ninguna se puede elegir.
    Idempotente. ``ResumenDePaso(procesados=pedidos revisados, creados=0, resueltos=pedidos cancelados)``."""
    ids = list(
        _vencidos(hoy).filter(cotizaciones__estado_cotizacion=Cotizacion.Estado.PROPUESTA).distinct().order_by("id").values_list("pk", flat=True)
    )
    return _correr(CODIGO_SIN_ELEGIBLE, ids, lambda pedido_id: _tratar_sin_elegible(pedido_id, hoy))
