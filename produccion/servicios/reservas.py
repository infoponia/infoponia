# Funciones de NÚCLEO de las reservas de insumo de una orden (COM-05a2, docs/api/produccion.md, sección 9, «Lo que suma COM-05a2»; D-66 punto 8): crear, cambiar la
# cantidad y cancelar una `ReservaInsumo` «activa». Las usa `comercial` para el envasado de una entrega (PROD-PNF-ENV, A3: el caso de uso toca la entrega).
# Como las funciones de núcleo de la cámara (sección 8): corren dentro de la transacción de quien las llama (sin ella, `RuntimeError`), con el invernadero y el
# `InsumoInvernadero` YA bloqueados por quien llama (`docs/patrones/stock.md`, sección 5), NO validan contra el stock (eso lo hace el caso de uso, después de bloquear, con
# `stock.disponible_para_planificar`), NO auditan ni notifican, y devuelven la reserva creada o cambiada para el registro del caso de uso.

from decimal import Decimal

from produccion.errores import ErrorDeProduccion
from produccion.models import OrdenTrabajo, ReservaInsumo
from produccion.servicios.movimientos import exigir_transaccion

Estado = ReservaInsumo.Estado


def reservar(orden, insumo_invernadero, cantidad, fecha):
    """Una reserva «activa» de `cantidad` del insumo para la `orden`, con `fecha_reserva = fecha` y utilizada y devuelta nulas (postcondición a de PROD-PNF-ENV).
    `ErrorDeProduccion('orden_no_pendiente')` si la orden no está «a realizar»; `ErrorDeProduccion('reserva_duplicada')` si ya tiene una activa de ese insumo (la base
    también lo impide: restricción «a lo sumo una activa», D-66 punto 8). Una reserva cancelada de ese insumo no cuenta: el envase quitado puede volver a agregarse."""
    exigir_transaccion("reservar")
    if orden.estado_orden != OrdenTrabajo.Estado.A_REALIZAR:
        raise ErrorDeProduccion("orden_no_pendiente", "La orden ya no está pendiente: no se le pueden reservar insumos.")
    if ReservaInsumo.objects.filter(orden_id=orden.pk, insumo_invernadero_id=insumo_invernadero.pk, estado=Estado.ACTIVA).exists():
        raise ErrorDeProduccion("reserva_duplicada", "La orden ya tiene una reserva activa de ese insumo.")
    return ReservaInsumo.objects.create(
        orden_id=orden.pk,
        insumo_invernadero_id=insumo_invernadero.pk,
        cantidad_reservada=Decimal(str(cantidad)),
        estado=Estado.ACTIVA,
        fecha_reserva=fecha,
    )


def _exigir_activa(reserva):
    """Relee el estado de la reserva (el llamador ya bloqueó sus filas): una que ya no está «activa» no se cambia."""
    estado = ReservaInsumo.objects.filter(pk=reserva.pk).values_list("estado", flat=True).first()
    if estado != Estado.ACTIVA:
        raise ErrorDeProduccion("reserva_no_activa", "La reserva de insumo ya no está activa.")


def cambiar_cantidad(reserva, cantidad):
    """Cambia `cantidad_reservada` de una reserva «activa» y conserva su `fecha_reserva` (postcondición b de PROD-PNF-ENV).
    `ErrorDeProduccion('reserva_no_activa')` si no está activa."""
    exigir_transaccion("cambiar_cantidad")
    _exigir_activa(reserva)
    reserva.cantidad_reservada = Decimal(str(cantidad))
    reserva.estado = Estado.ACTIVA
    reserva.save(update_fields=["cantidad_reservada"])
    return reserva


def cancelar(reserva):
    """Pasa una reserva «activa» a «cancelada», con utilizada y devuelta nulas: lo mismo que `ordenes.cancelar_orden_incluida` hace con cada reserva de la orden
    (un envase quitado, postcondición b de PROD-PNF-ENV). `ErrorDeProduccion('reserva_no_activa')` si no está activa. El llamador reevalúa las alertas de stock."""
    exigir_transaccion("cancelar")
    _exigir_activa(reserva)
    reserva.estado = Estado.CANCELADA
    reserva.cantidad_utilizada = None
    reserva.cantidad_devuelta = None
    reserva.save(update_fields=["estado", "cantidad_utilizada", "cantidad_devuelta"])
    return reserva
