# Inicio de «Compras» (CMP-02a y CMP-03; D-87 punto 5, D-43): la sección que ``compras`` registra con ``registrar_seccion_de_inicio`` en ``AppConfig.ready()`` (``panelAgr`` y ``panelGer``
# del prototipo). El Agrónomo ve «Insumos bajo el mínimo» con «Pedir», «Esperando cotizaciones» y, desde CMP-03, «Pedidos que vencieron» (con «Resolver») y «Órdenes rechazadas» (las de los
# últimos 7 días, como el prototipo); el Gerente ve «Órdenes pendientes de aprobación». «Por recibir» (Agrónomo) y «Reclamos sin emitir» (Gerente, CMP-06); «Pagos a proveedores pendientes» (CMP-05) es ``seccion_de_pagos``, del responsable contable.

from collections import namedtuple
from datetime import timedelta
from decimal import Decimal

from compras.models import OrdenCompra, Pedido
from compras.servicios import ordenes as servicio_de_ordenes
from compras.servicios import pagos as servicio_de_pagos
from compras.servicios import pedidos as servicio_de_pedidos
from compras.servicios import recepciones as servicio_de_recepciones
from compras.servicios import reclamos as servicio_de_reclamos
from contabilidad.servicios import responsables
from core.extensiones import SeccionDeInicio
from core.models import Usuario, rol_de
from inventario.servicios import stock

# Cuántos insumos bajo el mínimo se listan en el inicio (el resto se ve al hacer un pedido).
MAXIMO_EN_EL_INICIO = 5
# Cuántos días se muestra una orden rechazada en el inicio del Agrónomo (``panelAgr`` del prototipo: «days(o.fr, HOY) <= 7»).
DIAS_DE_ORDENES_RECHAZADAS = 7

IndicadoresDeCompras = namedtuple(
    "IndicadoresDeCompras",
    "bajo_el_minimo cantidad_bajo_el_minimo esperando_cotizaciones pedidos_por_resolver ordenes_rechazadas por_recibir cantidad_por_recibir",
    defaults=([], [], [], 0),
)
# El Gerente: las órdenes «pendiente de aprobación» (la más antigua primero) y cuántas son en total.
# CMP-06: los reclamos sin emitir (los primeros, con su proveedor y su recepción) y cuántos son en total.
IndicadoresDelGerente = namedtuple("IndicadoresDelGerente", "ordenes_por_aprobar cantidad_por_aprobar reclamos_sin_emitir cantidad_reclamos_sin_emitir", defaults=([], 0))


def indicadores_del_agronomo(actor):
    """Los insumos bajo el mínimo de los invernaderos a cargo de ``actor`` (los primeros, con su stock y sugerida), los pedidos «en cotización» cuya fecha límite no venció, los pedidos que vencieron y
    esperan que el Agrónomo resuelva (``ordenes.pedidos_resolubles``) y las órdenes rechazadas en los últimos días."""
    bajos = servicio_de_pedidos.insumos_bajo_el_minimo(actor)
    hoy = stock.hoy()
    esperando = Pedido.objects.en_alcance_de(actor).filter(estado_pedido=Pedido.Estado.EN_COTIZACION, fecha_limite_cotizaciones__gte=hoy).count()
    rechazadas = list(
        OrdenCompra.objects.en_alcance_de(actor)
        .filter(estado_orden_compra=OrdenCompra.Estado.RECHAZADA, fecha_resolucion__gte=hoy - timedelta(days=DIAS_DE_ORDENES_RECHAZADAS))
        .select_related("pedido")
        .order_by("-fecha_resolucion", "-id")
    )
    entregas = servicio_de_recepciones.entregas_pendientes(actor)  # CMP-04: «mercadería por recibir» (``panelAgr``)
    return IndicadoresDeCompras(
        bajos[:MAXIMO_EN_EL_INICIO], len(bajos), esperando, servicio_de_ordenes.pedidos_resolubles(actor), rechazadas, entregas[:MAXIMO_EN_EL_INICIO], len(entregas)
    )


def indicadores_del_gerente(actor):
    """Las órdenes de compra pendientes de aprobación, de la más antigua a la más reciente (``ordenes_por_aprobar``)."""
    filas = servicio_de_ordenes.ordenes_por_aprobar(actor)
    sin_emitir = servicio_de_reclamos.reclamos(actor, {"estado": "sin_emitir"})
    return IndicadoresDelGerente(filas[:MAXIMO_EN_EL_INICIO], len(filas), sin_emitir[:MAXIMO_EN_EL_INICIO], len(sin_emitir))


def seccion_de_inicio(usuario):
    """``registrar_seccion_de_inicio``: la sección «Compras» del Inicio del Agrónomo y del Gerente; ``None`` para los demás roles."""
    if not getattr(usuario, "is_active", False):
        return None
    rol = rol_de(usuario)
    if rol == Usuario.Rol.AGRONOMO:
        return SeccionDeInicio("compras/_inicio_agronomo.html", {"indicadores": indicadores_del_agronomo(usuario)})
    if rol == Usuario.Rol.GERENTE:
        return SeccionDeInicio("compras/_inicio_gerente.html", {"indicadores": indicadores_del_gerente(usuario)})
    return None


def seccion_de_pagos(usuario):
    """CMP-05 (D-91 punto 6, D-85): la sección «Pagos a proveedores pendientes» del Inicio del responsable contable, el Contador activo y, **sin** Contador activo, el Gerente
    (``responsables.puede_registrar_asientos``; el Gerente con un Contador activo no la ve). Sin pagos pendientes la muestra al día. ``None`` para cualquier otra cuenta."""
    if not getattr(usuario, "is_active", False) or not responsables.puede_registrar_asientos(usuario):
        return None
    pendientes = servicio_de_pagos.pagos_pendientes()
    datos = {"cantidad": len(pendientes), "monto_total": sum((p.monto for p in pendientes), Decimal("0.00")), "pendientes": pendientes[:MAXIMO_EN_EL_INICIO]}
    return SeccionDeInicio("compras/_inicio_pagos.html", datos)
