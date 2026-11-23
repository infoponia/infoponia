# Inicio del Agrónomo (CMP-02a; D-87 punto 5, D-43): la sección «Compras» que ``compras`` registra con ``registrar_seccion_de_inicio`` en ``AppConfig.ready()`` (``panelAgr`` del
# prototipo: «Insumos bajo el mínimo» con «Pedir» y «Esperando cotizaciones»). «Pedidos por resolver», «Por recibir» y «Órdenes rechazadas» se suman en CMP-03 y CMP-04.

from collections import namedtuple

from compras.models import Pedido
from compras.servicios import pedidos as servicio_de_pedidos
from core.extensiones import SeccionDeInicio
from core.models import Usuario, rol_de
from inventario.servicios import stock

# Cuántos insumos bajo el mínimo se listan en el inicio (el resto se ve al hacer un pedido).
MAXIMO_EN_EL_INICIO = 5

IndicadoresDeCompras = namedtuple("IndicadoresDeCompras", "bajo_el_minimo cantidad_bajo_el_minimo esperando_cotizaciones")


def indicadores_del_agronomo(actor):
    """Los insumos bajo el mínimo de los invernaderos a cargo de ``actor`` (los primeros, con su stock y sugerida) y los pedidos «en cotización» cuya fecha límite no venció."""
    bajos = servicio_de_pedidos.insumos_bajo_el_minimo(actor)
    esperando = Pedido.objects.en_alcance_de(actor).filter(estado_pedido=Pedido.Estado.EN_COTIZACION, fecha_limite_cotizaciones__gte=stock.hoy()).count()
    return IndicadoresDeCompras(bajos[:MAXIMO_EN_EL_INICIO], len(bajos), esperando)


def seccion_de_inicio(usuario):
    """``registrar_seccion_de_inicio``: la sección «Compras» del Inicio del Agrónomo; ``None`` para los demás roles (el Gerente suma las suyas en CMP-03 y CMP-05)."""
    if not getattr(usuario, "is_active", False) or rol_de(usuario) != Usuario.Rol.AGRONOMO:
        return None
    return SeccionDeInicio("compras/_inicio_agronomo.html", {"indicadores": indicadores_del_agronomo(usuario)})
