# Cobertura de un pedido con un conjunto de cotizaciones (CMP-02a; la usa también CMP-03). Fuente: regla 14 de 8.16 («Pedido cubierto» de
# CMP-ENV-COT y «Cobertura mínima de un detalle» de CMP-GNR-ODC) y D-89 punto 3. Solo lee: no bloquea ni escribe. Un detalle está cubierto
# cuando la suma de las cantidades COTIZADAS (aunque superen la pedida) alcanza ``pedida × (1 − tolerancia / 100)``; el mínimo no se redondea.

from collections import namedtuple
from decimal import Decimal

from django.db.models import Sum

from compras.models import DetalleCotizacion, DetallePedido
from maestros.servicios import configuracion

CERO = Decimal("0")
CIEN = Decimal("100")

# ``minima`` es el mínimo con tolerancia; ``sobra`` lo cotizado por encima de lo pedido; ``falta`` lo que resta para el mínimo.
Cobertura = namedtuple("Cobertura", "detalle_id pedida minima cotizada cubierto sobra falta")


def cobertura(pedido, cotizaciones, *, tolerancia=None):
    """``{detalle_id: Cobertura}`` de cada detalle de ``pedido`` con las ``cotizaciones`` dadas (solo esas suman).

    ``tolerancia`` es el porcentaje de ``porc_tolerancia_cobertura_pedido``; sin pasarlo se lee de la configuración operativa en cada uso
    (nunca una copia). Quien compara antes y después (D-88 punto 7) la lee una vez y la pasa. Dos consultas, sin importar los detalles."""
    if tolerancia is None:
        tolerancia = configuracion.obtener().porc_tolerancia_cobertura_pedido
    factor = (CIEN - Decimal(tolerancia)) / CIEN
    sumas = {
        fila["detalle_pedido_id"]: fila["total"]
        for fila in DetalleCotizacion.objects.filter(
            cotizacion__in=[c.pk for c in cotizaciones], detalle_pedido__pedido=pedido
        )
        .values("detalle_pedido_id")
        .annotate(total=Sum("cantidad_cotizada"))
    }
    resultado = {}
    for detalle in DetallePedido.objects.filter(pedido=pedido).order_by("id"):
        pedida = detalle.cantidad_detalle
        minima = pedida * factor
        cotizada = sumas.get(detalle.pk, CERO)
        resultado[detalle.pk] = Cobertura(
            detalle_id=detalle.pk,
            pedida=pedida,
            minima=minima,
            cotizada=cotizada,
            cubierto=cotizada >= minima,
            sobra=max(CERO, cotizada - pedida),
            falta=max(CERO, minima - cotizada),
        )
    return resultado


def esta_cubierto(coberturas):
    """True si todos los detalles están cubiertos (y hay al menos uno): el pedido está «cubierto» (regla 14 de 8.16)."""
    return bool(coberturas) and all(c.cubierto for c in coberturas.values())
