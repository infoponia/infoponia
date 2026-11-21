# Textos de cantidades y precios para la auditoría (INV-01; docs/patrones/auditoria.md y docs/patrones/stock.md, sección 6).
# El detalle de la auditoría no admite ``Decimal`` ni fechas (D-36): se guardan como texto.

from decimal import Decimal

from inventario.unidades import cuantizar


def texto_cantidad(valor, unidad):
    """La cantidad como texto con los decimales de su unidad: ``texto_cantidad(Decimal("12.5"), "l") == "12.500"``."""
    return str(cuantizar(valor, unidad))


def texto_precio(valor):
    """El precio como texto con 2 decimales: ``texto_precio(Decimal("5")) == "5.00"``."""
    return str(Decimal(valor).quantize(Decimal("0.01")))
