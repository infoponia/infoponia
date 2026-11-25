# Cálculos de la indemnización de una solicitud de revisión (COM-07a; docs/casos_de_uso/comercial/solicitudes.md, «Cálculos»; MD-114, MD-115, D-69 puntos 2 y 9): funciones PURAS, sin base de datos
# ni usuario, para poder probarlas con tablas. Todo en `Decimal` con `ROUND_HALF_UP` a centavos; nunca `float`. Las usan `solicitudes` (resumen y registro) y `confirmacion` (días de retraso).

import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

CENTAVOS = Decimal("0.01")
CERO = Decimal("0.00")
# El monto que carga el Gerente: un número de 0 o más, con coma o punto decimal. Los decimales de más se rechazan (regla «Tope del monto manual»: «con dos decimales»).
_MONTO = re.compile(r"^(\d+)(?:[.,](\d+))?$")


def redondear(valor):
    """Dos decimales, `ROUND_HALF_UP`."""
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def monto_de_linea(minima, entregada, por_planta):
    """Regla «Monto de la indemnización» de COM-EVL-DSC: ``(mínima estipulada − entregada) × indemnización por planta faltante``. Mínimo 80, 70 entregadas y $50 por planta: $500,00. Nunca negativo."""
    return redondear(max(0, minima - entregada) * Decimal(por_planta))


def montos_de_discrepancia(lineas):
    """``lineas`` son tuplas ``(mínima, entregada, por_planta)``: devuelve ``([monto de cada línea], total)``. El total es la suma de los montos de línea ya redondeados."""
    montos = [monto_de_linea(minima, entregada, por_planta) for minima, entregada, por_planta in lineas]
    return montos, redondear(sum(montos, CERO))


def dias_de_retraso(fecha_real, fecha_periodo, plazo_dias):
    """Regla «Retraso» de COM-RSV-QJA: ``fecha real de la entrega − (fecha del período + plazo de entrega)``, 0 si es negativo (es la misma cuenta de COM-CNF-ENT)."""
    return max(0, (fecha_real - (fecha_periodo + timedelta(days=plazo_dias))).days)


def monto_por_retraso(lineas):
    """``lineas`` son tuplas ``(días de retraso, indemnización por día)``: se suman solo las de más de cero días. 3 × $1.000 + 3 × $500 = $4.500,00."""
    return redondear(sum((dias * Decimal(por_dia) for dias, por_dia in lineas if dias > 0), CERO))


def tope_manual(montos_a_pagar):
    """Regla «Tope del monto manual» (MD-114): lo que el cliente paga por los detalles de la queja, la suma de ``cantidad entregada × precio unitario`` (`monto_pagar`) de cada uno."""
    return redondear(sum((Decimal(m) for m in montos_a_pagar), CERO))


def monto_manual(texto, tope):
    """El monto que carga el Gerente en una queja sin cláusula (extensión 4a): vacío es 0. `ValueError` con el mensaje para la persona si no es un número, es negativo, tiene más de dos
    decimales o supera el ``tope`` (el mensaje dice el tope, 4a.3a)."""
    texto = (texto or "").strip()
    if not texto:
        return CERO
    if texto.startswith("-"):
        raise ValueError("El monto no puede ser negativo.")
    encontrado = _MONTO.match(texto)
    if encontrado is None:
        raise ValueError("Escribí el monto como un número, por ejemplo 1500,50.")
    if len(encontrado.group(2) or "") > 2:
        raise ValueError("El monto tiene hasta dos decimales.")
    monto = redondear(Decimal(f"{encontrado.group(1)}.{encontrado.group(2) or '0'}"))
    if monto > tope:
        raise ValueError("El monto supera el tope.")
    return monto


def aplicacion(monto, monto_a_cobrar, pagada):
    """Regla «Aplicación de la indemnización» (MD-115; D-69 puntos 2 y 9): ``(descontado, reintegrado)``. Con la entrega pagada, todo se reintegra. Sin pagar, se descuenta hasta el monto a cobrar y
    el resto se reintegra. Con monto 0, ``(0, 0)``. Siempre ``descontado + reintegrado = monto``."""
    monto = redondear(monto)
    if monto <= 0:
        return CERO, CERO
    if pagada:
        return CERO, monto
    descontado = min(monto, redondear(max(CERO, monto_a_cobrar)))
    return descontado, monto - descontado
