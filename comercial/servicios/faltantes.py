# El camino de faltante (COM-04a, paso 3; docs/patrones/stock_maduro.md, sección 8; docs/casos_de_uso/comercial/faltante.md, «El camino de faltante»): lo que
# pasa con un detalle que quedó con cantidad sin cubrir después de intentar cubrirlo con PROD-ASG-STK. Una sola función que usan PROD-CNC-CSC (13a),
# PROD-REG-MRM (10c), PROD-CNL-ORD (8c y 8d) y PROD-VNC-CAM (3a.2a). COM-DCD-FLT y el enlace del cliente (COM-04c) se suman en esta misma función.
#
# Corre en la transacción del caso de uso que la llama, con la venta y el detalle ya bloqueados. NO audita (D-36: lo pone el llamador en su registro) y NO
# notifica: cada caso de uso arma su texto para el Vendedor (los de cada uno son distintos).
# Fuente: D-64 puntos 8 y 13.

from collections import namedtuple

from django.db import transaction

from comercial.models import CompraVenta, DetalleVenta
from comercial.servicios.stock_maduro import Periodo
from inventario.servicios import stock

# `detalle` es el `DetalleVenta` ya cambiado (o `None` con un período); `venta`, su `CompraVenta` (o `None`); `sin_cubrir`, lo que quedó sin cubrir;
# `ya_pendiente`, si el detalle ya esperaba la decisión del cliente (8d de PROD-CNL-ORD: solo cambió la fecha).
CaminoDeFaltante = namedtuple("CaminoDeFaltante", "detalle venta sin_cubrir ya_pendiente")


def seguir_camino_de_faltante(detalle_o_periodo, sin_cubrir, *, origen):
    """Sigue el camino de faltante de `detalle_o_periodo` (un `DetalleVenta` o un `Periodo`) con `sin_cubrir` plantas sin cubrir.

    - `sin_cubrir` es un entero mayor que cero (si no, `ValueError`); `origen` es quien actúa (`Usuario`) o `None` si actúa InfoPonia (D-27): COM-04c lo
      usará para el enlace del cliente. Corre dentro de la transacción del llamador (sin ella, `RuntimeError`).
    - **Detalle de compra-venta**: pasa a «pendiente de decisión del cliente» con `fecha_pendiente_decision = hoy`; si ya lo estaba, solo cambia la fecha
      (8d de PROD-CNL-ORD). Un detalle «confirmado» que pierde producto (D-64 punto 13) vuelve a «pendiente» con la fecha de hoy y SIN `cant_entregada_venta`.
      La venta pasa a «pendiente de decisión del cliente» (si ya lo estaba, no cambia).
    - **Período de un suministro**: no cambia ningún estado; queda con cantidad sin cubrir y la pre-reserva diaria lo vuelve a intentar mientras su fecha
      esté en la ventana (sección 7 del patrón).
    """
    if transaction.get_autocommit():
        raise RuntimeError("`seguir_camino_de_faltante` corre dentro de la transacción del caso de uso que la llama.")
    if isinstance(sin_cubrir, bool) or not isinstance(sin_cubrir, int) or sin_cubrir <= 0:
        raise ValueError("`sin_cubrir` tiene que ser un entero mayor que cero.")
    if isinstance(detalle_o_periodo, Periodo):
        return CaminoDeFaltante(None, None, sin_cubrir, False)
    hoy = stock.hoy()
    pasado = detalle_o_periodo
    detalle = DetalleVenta.objects.get(pk=pasado.pk)  # relee: el llamador lo tiene bloqueado, y su copia en memoria puede ser vieja
    ya_pendiente = detalle.estado_detalle_venta == DetalleVenta.Estado.PENDIENTE_DECISION
    cambios = {"estado_detalle_venta": DetalleVenta.Estado.PENDIENTE_DECISION, "fecha_pendiente_decision": hoy}
    if detalle.estado_detalle_venta == DetalleVenta.Estado.CONFIRMADO:
        cambios["cant_entregada_venta"] = None  # D-64 punto 13: al cliente no le cambian lo que aceptó sin preguntarle
    DetalleVenta.objects.filter(pk=detalle.pk).update(**cambios)
    for campo, valor in cambios.items():
        setattr(detalle, campo, valor)
        setattr(pasado, campo, valor)
    venta = CompraVenta.objects.get(pk=detalle.compra_venta_id)
    if venta.estado_venta != CompraVenta.Estado.PENDIENTE_DECISION:
        CompraVenta.objects.filter(pk=venta.pk).update(estado_venta=CompraVenta.Estado.PENDIENTE_DECISION)
        venta.estado_venta = CompraVenta.Estado.PENDIENTE_DECISION
    return CaminoDeFaltante(detalle, venta, sin_cubrir, ya_pendiente)
