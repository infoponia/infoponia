# Consumos y reservas de insumo de `produccion` (PRD-01): el cierre de una reserva. Es de NÚCLEO: corre dentro de la transacción de quien
# la llama, con la orden y la reserva ya bloqueadas, y no audita ni notifica (docs/api/produccion.md, sección 10). La usa
# `concretar_siembra` y la reutilizará COM-04a/COM-06a para los envases de una entrega, sin cambiarla (D-68 punto 3).
# Fuente: docs/modelo/produccion.md («ReservaInsumo») y docs/casos_de_uso/produccion/siembra.md (regla «Resolución de reservas»).

from collections import namedtuple
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from inventario.servicios import stock
from produccion.errores import ErrorDeProduccion
from produccion.models import Consumo, ReservaInsumo
from produccion.servicios import movimientos

CERO = Decimal("0")
ResultadoConsumo = namedtuple("ResultadoConsumo", "consumo movimientos")


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


def registrar_consumo_de_orden(orden, insumo_invernadero, cantidad, fecha, responsable):
    """Consumo de insumo de una orden que no es una siembra (los envases de una entrega, COM-06a; COM-04a, D-68 punto 3 y sección 10 de la API).

    - `Consumo` (hijo de `Bitacora`, tipo interno `consumo`, como el de una aplicación: la consulta de la bitácora no lo lista) con `orden`, el
      invernadero de la orden, sin lote, etapa ni sectores, `cant_consumo = cantidad`, `monto_consumo = cantidad × referencia_precio` del insumo
      AL CONCRETAR (`ROUND_HALF_UP`, 2 decimales) y `fecha_consumo = fecha`. Se crea ANTES que sus movimientos (D-52 punto 5).
    - Después, FEFO con `stock.proponer_lotes_fefo` y `stock.registrar_salida_por_consumo(..., origen_id=consumo.id, fecha=fecha)`: lo que los
      lotes no cubren sale del «faltante sin lote», como en la siembra (PRD-01).
    - NO valida contra el stock (el hecho ya ocurrió) y NO reevalúa alertas: quien llama usa `alertas_de_stock.reevaluar_alertas_del_insumo`.
    - Corre en la transacción de quien llama (sin ella, `RuntimeError`), con el invernadero y el `InsumoInvernadero` ya bloqueados. No audita ni notifica.
    """
    from produccion.servicios.siembras import _partes_de_salida  # adentro: `siembras` importa este módulo

    movimientos.exigir_transaccion("registrar_consumo_de_orden")
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ErrorDeProduccion("cantidad_invalida", "La cantidad consumida debe ser mayor que cero.", "cantidad")
    monto = (cantidad * Decimal(insumo_invernadero.referencia_precio)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    consumo = Consumo.objects.create(
        invernadero_id=orden.invernadero_id,
        responsable=responsable,
        fecha_bitacora=fecha,
        hora_bitacora=timezone.localtime().time(),
        tipo_evento="consumo",
        descripcion_evento=f"Consumo de {orden.codigo}: {insumo_invernadero.insumo.nombre_insumo}"[:500],
        monto_consumo=monto,
        cant_consumo=cantidad,
        fecha_consumo=fecha,
        insumo_invernadero=insumo_invernadero,
        orden_id=orden.pk,
    )
    propuesta = stock.proponer_lotes_fefo(insumo_invernadero.pk, cantidad, fecha)
    partes = _partes_de_salida(insumo_invernadero, [(lote_id, parte) for lote_id, parte in propuesta.partes], propuesta.resto)
    salidas = stock.registrar_salida_por_consumo(insumo_invernadero.pk, partes, origen_id=consumo.pk, fecha=fecha)
    return ResultadoConsumo(consumo, salidas)
