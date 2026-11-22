# Fábricas compartidas por las pruebas de produccion/tests/ (PRD-01). Arman un invernadero completo, órdenes de siembra, órdenes
# sueltas de los tipos futuros (D-67 punto 1) y lotes, directo en la base y reutilizando las fábricas de `maestros` e `inventario`.
# NO armes ciclos, semillas ni lotes de insumo a mano: usá estas. Una siembra o una transición sin su hija rompería los invariantes:
# `orden_suelta` solo vale para los tipos que no tienen hija todavía (entrega, mantenimiento y, en una prueba, cosecha).

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from inventario.models import TipoInsumo
from inventario.tests.fabricas import existencia, insumo, lote as lote_de_insumo, tipo_de_insumo, variedad_con_semilla
from maestros.models import EtapaProductiva
from maestros.tests.fabricas import (
    crear_agronomo,
    crear_capataz_activo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    crear_sector,
)
from produccion.errores import ErrorDeProduccion
from produccion.models import Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.servicios import ordenes

CODIGOS_DE_ETAPA = ("germinacion", "crecimiento", "floracion", "fructificacion", "maduracion")


class Escenario:
    """Lo que devuelve `invernadero_con_produccion`: un invernadero activo con su Agrónomo y su Capataz, un sector por tipo de
    etapa (`sectores[codigo]`), una variedad con su ciclo, su semilla habilitada (`existencia_semilla`) y un lote de semillas
    con stock (`lote_de_semillas`)."""

    def __init__(self, invernadero, agronomo, capataz, sectores, variedad, semilla, existencia_semilla, lote_de_semillas):
        self.invernadero = invernadero
        self.agronomo = agronomo
        self.capataz = capataz
        self.sectores = sectores
        self.variedad = variedad
        self.semilla = semilla
        self.existencia_semilla = existencia_semilla
        self.lote_de_semillas = lote_de_semillas


def invernadero_con_produccion(
    nombre="Invernadero Norte", agujeros=100, stock_de_semillas=1000, etapas=CODIGOS_DE_ETAPA, perfil="hoja_verde", sufijo="",
    geografia_propia=False,
):
    """Un invernadero activo con Agrónomo y Capataz, un sector de `agujeros` agujeros por cada tipo de etapa, una variedad con
    el ciclo de `etapas` (10 días cada una) y su semilla habilitada con `stock_de_semillas` unidades en un lote vigente.
    `sufijo` permite armar un segundo invernadero en la misma prueba (los emails y nombres son únicos). Con `geografia_propia`
    (las pruebas de concurrencia, `TransactionTestCase`) el invernadero no usa Georef, que el `flush` vacía."""
    agronomo = crear_agronomo(email=f"agronomo{sufijo}@infoponia.com")
    capataz = crear_capataz_activo(email=f"capataz{sufijo}@infoponia.com")
    crear = crear_invernadero_con_geografia_propia if geografia_propia else crear_invernadero
    inv = crear(nombre, agronomo=agronomo, capataz=capataz)
    sectores = {c: crear_sector(inv, nombre=f"Sector {c}", tipo=c, agujeros=agujeros) for c in CODIGOS_DE_ETAPA}
    variedad = variedad_con_semilla(nombre=f"Crespa{sufijo}", perfil=perfil, etapas=etapas)
    semilla = variedad.semilla
    existencia_semilla = existencia(semilla, inv, precio="2.00")
    lote_semillas = lote_de_insumo(existencia_semilla, stock_de_semillas, vence=timezone.localdate() + timedelta(days=365))
    return Escenario(inv, agronomo, capataz, sectores, variedad, semilla, existencia_semilla, lote_semillas)


def orden_de_siembra(
    escenario, plantines=50, sector="germinacion", estado="a_realizar", dias=0, agujeros=None, prioridad=None,
    con_reserva=True, agronomo=True, capataz=None, variedad=None, existencia=None,
):
    """Una `Siembra` «a realizar» (o en el `estado` pedido) con una ocupación en el sector `sector` y, si `con_reserva`, la
    reserva de la semilla por `plantines`. Escribe directo en la base: no pasa por `planificar_siembra`. `dias` es cuántos días
    desde hoy se programa (0 = hoy). Una orden «cancelada» queda con su motivo y «concretada» con su fecha de resolución."""
    hoy = timezone.localdate()
    extra = {}
    if estado != "a_realizar":
        extra["fecha_resolucion_orden"] = hoy
    if estado == "cancelada":
        extra["motivo_cancelacion"] = "Motivo de prueba"
    siembra = Siembra.objects.create(
        tipo_orden=OrdenTrabajo.Tipo.SIEMBRA,
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=min(hoy, hoy + timedelta(days=dias)),  # una orden vencida se creó antes de su fecha
        fecha_programada_orden=hoy + timedelta(days=dias),
        estado_orden=estado,
        prioridad_orden=prioridad,
        agronomo=escenario.agronomo if agronomo else None,
        invernadero=escenario.invernadero,
        capataz=capataz or escenario.capataz,
        cant_plantines_siembra=plantines,
        variedad=variedad or escenario.variedad,
        **extra,
    )
    OcupacionSector.objects.create(
        orden=siembra, sector=escenario.sectores[sector], cant_agujeros_planificados=agujeros or plantines
    )
    if con_reserva:
        reservar(siembra, existencia or escenario.existencia_semilla, plantines, estado=estado)
    return siembra


def reservar(orden, insumo_invernadero, cantidad, estado="a_realizar"):
    """Una reserva de `cantidad` del insumo para la orden: «activa» salvo que la orden esté cancelada (entonces, «cancelada»,
    sin cantidades)."""
    return ReservaInsumo.objects.create(
        orden=orden,
        insumo_invernadero=insumo_invernadero,
        cantidad_reservada=Decimal(str(cantidad)),
        estado="cancelada" if estado == "cancelada" else "activa",
    )


def orden_suelta(invernadero, tipo, *, estado="a_realizar", reservas=()):
    """Una orden de un tipo sin hija todavía (D-67 punto 1): `entrega` o `mantenimiento` y, en una prueba, `cosecha`. SOLO esos:
    una siembra o una transición sin su hija rompería los invariantes. `reservas` es una lista de `(insumo_invernadero, cantidad)`."""
    hoy = timezone.localdate()
    extra = {}
    if estado != "a_realizar":
        extra["fecha_resolucion_orden"] = hoy
    if estado == "cancelada":
        extra["motivo_cancelacion"] = "Motivo de prueba"
    orden = OrdenTrabajo.objects.create(
        tipo_orden=tipo,
        numero=ordenes.siguiente_numero(),
        fecha_programada_orden=hoy,
        estado_orden=estado,
        invernadero=invernadero,
        **extra,
    )
    for insumo_invernadero, cantidad in reservas:
        reservar(orden, insumo_invernadero, cantidad, estado=estado)
    return orden


def lote_activo(escenario, cantidad=50, sector="germinacion", costo="100.00", etapa="germinacion", variedad=None):
    """Un lote «activo» de `cantidad` plantas, de una siembra concretada, con su ocupación vigente en `sector` y en la etapa
    `etapa` del ciclo de la variedad. Escribe directo en la base."""
    variedad = variedad or escenario.variedad
    siembra = orden_de_siembra(
        escenario, plantines=cantidad, sector=sector, estado="concretada", con_reserva=False, variedad=variedad
    )
    siembra.fecha_siembra = timezone.localdate()
    siembra.save(update_fields=["fecha_siembra"])
    nuevo = Lote.objects.create(
        invernadero=escenario.invernadero,
        etapa=EtapaProductiva.objects.get(ciclo__variedad=variedad, tipo_etapa__codigo=etapa),
        siembra=siembra,
        cantidad_inicial=cantidad,
        cantidad_actual=cantidad,
        costo_acumulado=Decimal(costo),
    )
    OcupacionSector.objects.filter(orden=siembra).update(lote=nuevo, cant_agujeros_ocupados=cantidad)
    return nuevo


def variedad_con_stock(escenario, nombre="Otra", perfil="hoja_verde", stock=100, habilitar=True, **columnas):
    """Una segunda variedad con su ciclo y su semilla, en el invernadero del `escenario`. Con `habilitar` la semilla queda
    habilitada con `stock` unidades en un lote vigente (si no, queda sin habilitar: extensión 8b). `columnas` pisa los rangos
    ambientales (`temp_ambiente_min="30"`). Devuelve `(variedad, existencia o None)`."""
    variedad = variedad_con_semilla(nombre=nombre, perfil=perfil, **columnas)
    if not habilitar:
        return variedad, None
    habilitada = existencia(variedad.semilla, escenario.invernadero, precio="2.00")
    if stock:
        lote_de_insumo(habilitada, stock, vence=timezone.localdate() + timedelta(days=365))
    return variedad, habilitada


def insumo_adicional(escenario, nombre="Fertilizante", stock=50, unidad="kg", precio="4.00", activo=True):
    """Un insumo adicional (de una categoría que no es del sistema) habilitado en el invernadero del `escenario`, con `stock`
    en un lote vigente. Devuelve su `InsumoInvernadero`."""
    tipo = TipoInsumo.objects.filter(nombre_tipo_insumo="Fertilizantes").first() or tipo_de_insumo(
        "Fertilizantes", consumo="como_costo_de_los_lotes"
    )
    habilitado = existencia(insumo(nombre, tipo=tipo, unidad=unidad), escenario.invernadero, precio=precio, activo=activo)
    if stock:
        lote_de_insumo(habilitado, stock, vence=timezone.localdate() + timedelta(days=365))
    return habilitado


def separar(resultados):
    """`(exitos, rechazos, otros)` de lo que devuelve `correr_a_la_vez`: los resultados normales, los rechazos de negocio
    (`ErrorDeProduccion` y `ValidationError`, que lanzan las bajas de `maestros` e `inventario`) y cualquier otra excepción
    (un `IntegrityError` sin traducir, que en pantalla sería un error 500). El `separar` de `core` solo conoce `ValidationError`."""
    exitos, rechazos, otros = [], [], []
    for resultado in resultados.values():
        if isinstance(resultado, (ErrorDeProduccion, ValidationError)):
            rechazos.append(resultado)
        elif isinstance(resultado, Exception):
            otros.append(resultado)
        else:
            exitos.append(resultado)
    return exitos, rechazos, otros


def codigos_del_rechazo(rechazo):
    """Los códigos de un rechazo: `[codigo]` de un `ErrorDeProduccion` o los de todos los errores de una `ValidationError`."""
    if isinstance(rechazo, ErrorDeProduccion):
        return [rechazo.codigo]
    if hasattr(rechazo, "error_dict"):
        return [e.code for errores in rechazo.error_dict.values() for e in errores]
    return [e.code for e in rechazo.error_list]
