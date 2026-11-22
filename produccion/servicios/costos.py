# Costo de un lote de plantas (PRD-01): costo por planta y costo de las plantas perdidas, con el promedio ponderado móvil de MD-79.
# Fuente: docs/patrones/costo_del_lote.md y D-50 punto 5. Todo con Decimal y ROUND_HALF_UP, nunca float. Estas funciones NO escriben:
# quien baja el costo del lote (la merma, PRD-02 y PRD-03) lo hace con el lote bloqueado y dentro de su transacción.

from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def redondear_monto(valor):
    """Redondea un monto a 2 decimales con ROUND_HALF_UP (docs/patrones/costo_del_lote.md)."""
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def costo_por_planta(lote):
    """Costo acumulado ÷ cantidad actual, a 2 decimales, solo para mostrar; `None` si el lote no tiene plantas."""
    if lote.cantidad_actual <= 0:
        return None
    return redondear_monto(Decimal(lote.costo_acumulado) / lote.cantidad_actual)


def costo_de_la_merma(lote, cantidad):
    """Lo que cuestan `cantidad` plantas perdidas de `lote` (con `0 < cantidad <= cantidad_actual`; si no, `ValueError`).

    Si se pierde el lote entero, es el costo acumulado completo (así no sobran ni faltan centavos); si no,
    `redondear(K × n ÷ c)`. Las plantas que quedan conservan su costo unitario (salvo el redondeo de a lo sumo un centavo)."""
    if not 0 < cantidad <= lote.cantidad_actual:
        raise ValueError(f"La merma ({cantidad}) debe ser mayor que 0 y no superar las plantas del lote ({lote.cantidad_actual}).")
    costo = Decimal(lote.costo_acumulado)
    if cantidad == lote.cantidad_actual:
        return redondear_monto(costo)
    return redondear_monto(costo * cantidad / lote.cantidad_actual)
