# Consumos y reservas de insumo de `produccion` (PRD-01): el cierre de una reserva. Es de NÚCLEO: corre dentro de la transacción de quien
# la llama, con la orden y la reserva ya bloqueadas, y no audita ni notifica (docs/api/produccion.md, sección 10). La usa
# `concretar_siembra` y la reutilizará COM-04a/COM-06a para los envases de una entrega, sin cambiarla (D-68 punto 3).
# Fuente: docs/modelo/produccion.md («ReservaInsumo») y docs/casos_de_uso/produccion/siembra.md (regla «Resolución de reservas»).

from decimal import Decimal

from produccion.errores import ErrorDeProduccion
from produccion.models import ReservaInsumo

CERO = Decimal("0")


def cerrar_reserva(reserva, utilizada, devuelta):
    """Cierra una reserva «activa» con lo `utilizada` y lo `devuelta` y la devuelve guardada.

    - `0 <= utilizada <= cantidad_reservada` y `0 <= devuelta <= cantidad_reservada − utilizada` (las restricciones de la base, que no
      cambian): si no, `ErrorDeProduccion('cantidad_invalida')`. Quien llama ya topeó la utilizada en la reservada si hubo exceso.
    - Lo consumido es `cantidad_reservada − devuelta`: queda «consumida» si es mayor que cero y «cancelada» si es cero (con lo
      utilizado y lo devuelto cargados), regla «Resolución de reservas». Ninguna reserva de una orden concretada queda «activa».
    - Una reserva que no está «activa» lanza `ErrorDeProduccion('reserva_no_activa')`.
    """
    if reserva.estado != ReservaInsumo.Estado.ACTIVA:
        raise ErrorDeProduccion("reserva_no_activa", "La reserva ya no está activa.")
    utilizada, devuelta = Decimal(utilizada), Decimal(devuelta)
    reservada = reserva.cantidad_reservada
    if not CERO <= utilizada <= reservada:
        raise ErrorDeProduccion("cantidad_invalida", f"La cantidad utilizada tiene que estar entre 0 y {reservada.normalize():f}.", "utilizada")
    maximo = reservada - utilizada
    if not CERO <= devuelta <= maximo:
        raise ErrorDeProduccion("cantidad_invalida", f"La cantidad devuelta tiene que estar entre 0 y {maximo.normalize():f}.", "devuelta")
    reserva.cantidad_utilizada = utilizada
    reserva.cantidad_devuelta = devuelta
    reserva.estado = ReservaInsumo.Estado.CONSUMIDA if reservada - devuelta > 0 else ReservaInsumo.Estado.CANCELADA
    reserva.save(update_fields=["cantidad_utilizada", "cantidad_devuelta", "estado"])
    return reserva
