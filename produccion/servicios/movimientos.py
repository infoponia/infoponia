# Ayudas comunes de las funciones de NÚCLEO físico de `produccion` (COM-04a, docs/api/produccion.md, secciones 8 y 10): exigir la transacción del
# llamador, armar el momento de un movimiento (fecha efectiva con la hora actual, D-50 punto 7) y crear un `MovimientoStock`.
# Fuente: D-64 punto 2 (una sola función por efecto físico: el costo y la fecha se calculan en un solo lugar).

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection
from django.utils import timezone

from produccion.models import MovimientoStock

CUATRO_DECIMALES = Decimal("0.0001")


def exigir_transaccion(nombre):
    """Las funciones de núcleo corren dentro de la transacción del caso de uso que las llama: sin ella, `RuntimeError`."""
    if not connection.in_atomic_block:
        raise RuntimeError(f"{nombre} corre dentro de la transacción del caso de uso que la llama.")


def momento_de(fecha):
    """La `fecha` (efectiva) con la hora actual, como fecha y hora con zona (para `MovimientoStock.fecha`)."""
    return timezone.make_aware(datetime.combine(fecha, timezone.localtime().time()))


def costo_por_planta_exacto(lote):
    """Costo acumulado ÷ cantidad actual con 4 decimales (`ROUND_HALF_UP`): el costo por planta de ANTES de un movimiento del lote
    (D-64 puntos 1 y 3). `Decimal("0.0000")` si no tiene plantas."""
    if lote.cantidad_actual <= 0:
        return Decimal("0.0000")
    return (Decimal(lote.costo_acumulado) / lote.cantidad_actual).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def registrar(tipo, cantidad, costo_unitario, origen, *, lote=None, partida=None, fecha=None):
    """Crea un `MovimientoStock` de `tipo` (exactamente uno de `lote` y `partida`; la base lo exige) originado en `origen`."""
    return MovimientoStock.objects.create(
        fecha=momento_de(fecha) if fecha else timezone.now(),
        cantidad=cantidad,
        tipo_movimiento=tipo,
        costo_unitario=costo_unitario,
        origen_id=origen.pk,
        lote=lote,
        partida=partida,
    )
