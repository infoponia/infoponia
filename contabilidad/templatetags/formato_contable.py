# Filtros de plantilla de `contabilidad` (CON-03a). `contabilidad` es de nivel 2 y no puede cargar los de `inventario` (A1 de D-37), así que el
# formato de los importes se repite acá: «$ 1.500,00», con el signo menos delante.
from decimal import ROUND_HALF_UP, Decimal

from django import template

register = template.Library()


@register.filter
def pesos(valor):
    """Un importe en pesos con 2 decimales, punto de mil y coma decimal: «$ 1.500,00»; un negativo lleva «−» delante. Vacío si no hay valor."""
    if valor is None or valor == "":
        return ""
    numero = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero, _, decimales = f"{abs(numero):.2f}".partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    return f"{'−' if numero < 0 else ''}$ {entero},{decimales}"
