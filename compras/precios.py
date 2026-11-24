# Precios de las líneas de cotización y de orden (CMP-02a, D-89). Se guarda el TOTAL de la línea (``total_linea``, 2 decimales); el unitario
# no se guarda: se deriva acá, con 4 decimales y ``ROUND_HALF_UP`` (D-89 punto 1), y lo usan todas las pantallas y los servicios.
# Son funciones puras sobre ``Decimal`` (nunca ``float``). Sirven para ``DetalleCotizacion`` (``cantidad_cotizada``) y, cuando exista,
# ``DetalleOrdenCompra`` (``cantidad_detalle_orden``, CMP-03).

from decimal import ROUND_HALF_UP, Decimal

DOS_DECIMALES = Decimal("0.01")
CUATRO_DECIMALES = Decimal("0.0001")


def _cantidad_de(linea):
    """La cantidad de una línea de cotización o de orden de compra; ``ValueError`` si no es mayor que cero."""
    cantidad = getattr(linea, "cantidad_cotizada", None)
    if cantidad is None:
        cantidad = linea.cantidad_detalle_orden
    if cantidad <= 0:
        raise ValueError("La cantidad de una línea tiene que ser mayor que cero.")
    return cantidad


def precio_unitario(linea):
    """D-89 punto 1: ``total_linea / cantidad`` con cuatro decimales (``ROUND_HALF_UP``). Es el que se usa para las cuentas."""
    return (linea.total_linea / _cantidad_de(linea)).quantize(CUATRO_DECIMALES, ROUND_HALF_UP)


def precio_unitario_para_mostrar(linea):
    """D-89 punto 7: el unitario derivado con dos decimales (``ROUND_HALF_UP``), para pantallas, correos y comprobantes."""
    return precio_unitario(linea).quantize(DOS_DECIMALES, ROUND_HALF_UP)


def unitario_cierra_con_el_total(linea):
    """D-89 punto 7: True si el unitario mostrado × la cantidad da el total guardado. Si no, la pantalla muestra el total, que manda."""
    return total_desde_unitario(precio_unitario_para_mostrar(linea), _cantidad_de(linea)) == linea.total_linea


def total_desde_unitario(unitario, cantidad):
    """D-89 punto 2: el total de una línea cuando el proveedor carga el unitario; dos decimales, ``ROUND_HALF_UP``."""
    if not isinstance(unitario, Decimal) or not isinstance(cantidad, Decimal):
        raise TypeError("El unitario y la cantidad son Decimal: el dinero no se calcula con float.")
    return (unitario * cantidad).quantize(DOS_DECIMALES, ROUND_HALF_UP)


def valor_recibido(linea, recibido):
    """D-89 punto 4: el valor de lo recibido de una línea. Si se recibió todo, el ``total_linea`` exacto; si no,
    ``round(recibido × precio_unitario, 2)``. Con el acumulado antes y después sale el asiento de cada recepción sin diferencias."""
    cantidad = _cantidad_de(linea)
    if recibido < 0 or recibido > cantidad:
        raise ValueError("Lo recibido no puede ser negativo ni superar la cantidad de la línea.")
    if recibido == cantidad:
        return linea.total_linea
    return (recibido * precio_unitario(linea)).quantize(DOS_DECIMALES, ROUND_HALF_UP)
