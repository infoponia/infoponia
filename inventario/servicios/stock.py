# Lectura básica del stock (INV-01; docs/patrones/stock.md y docs/api/stock.md, «Lectura»). INV-02 agrega el resto de este
# módulo (existencias, FEFO, salida por consumo). Una sola función hace cada cuenta: ninguna pantalla ni otro servicio la repite.

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from inventario.models import LoteInsumo


def hoy():
    """La fecha de hoy en la zona del sistema (``America/Argentina/Buenos_Aires``): ``timezone.localdate()``. Usala siempre
    que necesites «hoy»: nada de ``date.today()``."""
    return timezone.localdate()


def stock_actual_de(iin_ids):
    """``{id: Decimal}``: el stock actual (``/cantActualInsumo``) de cada ``InsumoInvernadero``: la suma de la
    ``cantidad_disponible`` de TODOS sus lotes, incluido el faltante sin lote (puede ser negativo; regla 3 de 8.23). No se
    guarda: se calcula. Una sola consulta para toda la lista; lo que no tiene lotes da 0."""
    ids = list(iin_ids)
    stock = defaultdict(lambda: Decimal("0"))
    filas = (
        LoteInsumo.objects.filter(insumo_invernadero_id__in=ids)
        .values("insumo_invernadero_id")
        .annotate(total=Sum("cantidad_disponible"))
    )
    for fila in filas:
        stock[fila["insumo_invernadero_id"]] = fila["total"]
    return {i: stock[i] for i in ids}
