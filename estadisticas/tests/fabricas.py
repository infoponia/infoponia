# Fábricas de las pruebas de `estadisticas` (EST-01). Arman lotes, mermas, salidas por cosecha, consumos y órdenes DIRECTO en la base y con
# FECHAS FIJAS (`HOY`), porque los servicios de estadísticas reciben `hoy` y las pruebas no dependen del día en que corren. Reutilizan las
# fábricas de `produccion`, `inventario`, `maestros` e `iot` (nada de armar ciclos, semillas o sistemas IoT a mano).
#
# Las órdenes de estas pruebas son filas de `OrdenTrabajo` sin su hija: EST-CNS-PRD solo lee la tabla padre (tipo, estado y fechas), igual
# que `orden_suelta` de `produccion` para los tipos que todavía no tenían hija. No sirven para pruebas que miren la hija.

from datetime import date, datetime, time, timedelta, timezone as zona
from decimal import Decimal

from django.utils import timezone

from inventario.tests.fabricas import categoria_del_sistema, existencia, insumo
from produccion.models import AplicacionInsumos, Consumo, Merma, MovimientoStock, OrdenTrabajo, Siembra
from produccion.servicios import ordenes
from produccion.tests.fabricas import cosecha, insumo_adicional, invernadero_con_produccion, lote_activo, lote_de_carga_inicial, partida_de, variedad_con_stock

HOY = date(2026, 11, 26)
DESDE = date(2026, 11, 1)  # el mes de HOY: el período por defecto es DESDE … HOY


def dos_invernaderos():
    """`(norte, sur)`: dos escenarios completos de `produccion` (cada uno con su Agrónomo y su Capataz)."""
    return invernadero_con_produccion("Invernadero Norte"), invernadero_con_produccion("Invernadero Sur", sufijo="_sur")


def _fijar_fechas_de_la_orden(orden_id, programada, resolucion):
    """Deja la orden concretada con fechas FIJAS (creada 30 días antes de `programada`). Las fábricas de `produccion` usan el día real de hoy,
    y una prueba de estadísticas no puede depender del día en que corre: una orden de hoy podría caer dentro del período del indicador 3."""
    OrdenTrabajo.objects.filter(pk=orden_id).update(
        fecha_creacion_orden=programada - timedelta(days=30), fecha_programada_orden=programada, fecha_resolucion_orden=resolucion
    )


def lote_sembrado(escenario, cantidad, fecha, *, variedad=None, costo="100.00", resolucion=None):
    """Un lote de una siembra NORMAL concretada, con `fecha_siembra` = `fecha` (la efectiva). La orden queda programada ese día y concretada el
    día `resolucion` (por defecto, el mismo): sirve para probar que EST mira `fecha_siembra` y no la resolución (D-103)."""
    lote = lote_activo(escenario, cantidad=cantidad, costo=costo, variedad=variedad)
    Siembra.objects.filter(pk=lote.siembra_id).update(fecha_siembra=fecha)
    _fijar_fechas_de_la_orden(lote.siembra_id, fecha, resolucion or fecha)
    return lote


def lote_cargado(escenario, cantidad, fecha_siembra, *, variedad=None):
    """Un lote de CARGA INICIAL (PRD-05) cuya siembra real es `fecha_siembra`. Su orden queda con las tres fechas en el día en que se registra
    (D-103; el día real de hoy): la de siembra va solo en `Siembra.fecha_siembra`. Una prueba que mire órdenes no debe usar esta fábrica."""
    return lote_de_carga_inicial(escenario, cantidad=cantidad, siembra=fecha_siembra, variedad=variedad)


def otra_variedad(escenario, nombre="Rúcula"):
    """Una segunda variedad con su ciclo y su semilla en el invernadero de `escenario`."""
    return variedad_con_stock(escenario, nombre=nombre)[0]


def nombre_de(variedad):
    """El nombre con el que las estadísticas muestran una variedad: «Lechuga Crespa» (cultivo y variedad, como el prototipo)."""
    return f"{variedad.cultivo.nombre_cultivo} {variedad.nombre_variedad}"


def orden(invernadero, tipo, programada, estado="concretada", resolucion=None):
    """Una orden de trabajo de `tipo` (`OrdenTrabajo.Tipo`), programada el `programada`, sin hija. «concretada» se resolvió el día que dice
    `resolucion` (por defecto, el programado); «cancelada» queda con su motivo; «a_realizar» no tiene resolución."""
    extra = {}
    if estado != "a_realizar":
        extra["fecha_resolucion_orden"] = resolucion or programada
    if estado == "cancelada":
        extra["motivo_cancelacion"] = "Motivo de prueba"
    if tipo in (OrdenTrabajo.Tipo.COSECHA, OrdenTrabajo.Tipo.MANTENIMIENTO):
        extra["prioridad_orden"] = "media"  # obligatoria en la cosecha y el mantenimiento (restricciones de `OrdenTrabajo`)
    return OrdenTrabajo.objects.create(
        tipo_orden=tipo,
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=programada - timedelta(days=30),
        fecha_programada_orden=programada,
        estado_orden=estado,
        invernadero=invernadero,
        **extra,
    )


def merma_de(lote, cantidad, causa, fecha, *, orden_de_entrega=None):
    """Una merma del `lote` escrita directo en la base. Las de lote en pie llevan etapa; las de cámara (`dano_en_camara`,
    `vencimiento_en_camara`) y la de la entrega, no (como las deja `mermas.aplicar_merma`). `dano_en_entrega` exige su `orden_de_entrega`."""
    de_lote_en_pie = causa not in ("dano_en_camara", "vencimiento_en_camara", "dano_en_entrega")
    return Merma.objects.create(
        invernadero=lote.invernadero,
        lote=lote,
        etapa=lote.etapa if de_lote_en_pie else None,
        tipo_evento="merma",
        fecha_bitacora=fecha,
        hora_bitacora=time(10, 0),
        cant_merma=cantidad,
        causa=causa,
        orden=orden_de_entrega,
    )


def merma_de_camara(lote, cantidad, causa, fecha, costo_unitario="2.5000"):
    """Una merma de partida en cámara tal como la deja `camara.aplicar_merma_de_partida`: la `Merma` (sin etapa) y su `MovimientoStock`
    `merma_en_camara` (origen: la merma; costo: el de la partida). Su costo es `cantidad × costo_unitario`; con `costo_unitario` en 0 no tiene costo
    y, por la regla H11, nunca tendrá asiento."""
    merma = merma_de(lote, cantidad, causa, fecha)
    partida = partida_de(lote, disponible=cantidad, costo=costo_unitario)
    MovimientoStock.objects.create(
        fecha=timezone.make_aware(datetime.combine(fecha, time(10, 0))),
        cantidad=cantidad,
        tipo_movimiento=MovimientoStock.TipoMovimiento.MERMA_EN_CAMARA,
        costo_unitario=Decimal(costo_unitario),
        origen_id=merma.pk,
        partida=partida,
    )
    return merma


def salida_por_cosecha(lote, cantidad, fecha, costo_unitario="2.0000", *, hora=time(12, 0), tipo="salida_por_cosecha", escenario=None):
    """Un `MovimientoStock` de salida del `lote` el `fecha` a las `hora` (hora local). Por defecto una salida por cosecha; `tipo` permite
    armar una `salida_por_merma` (que EST no cuenta). Su origen es una cosecha concretada ese día y a tiempo."""
    origen = cosecha(escenario or _Escenario(lote), estado="concretada")
    _fijar_fechas_de_la_orden(origen.pk, fecha, fecha)
    momento = timezone.make_aware(datetime.combine(fecha, hora))
    return MovimientoStock.objects.create(
        fecha=momento, cantidad=cantidad, tipo_movimiento=tipo, costo_unitario=Decimal(costo_unitario), origen_id=origen.pk, lote=lote
    )


class _Escenario:
    """Lo mínimo que `cosecha()` toma de un escenario: el invernadero, su Capataz y su variedad."""

    def __init__(self, lote):
        self.invernadero = lote.invernadero
        self.capataz = lote.invernadero.capataz
        self.variedad = lote.siembra.variedad


def aplicacion_de(invernadero, fecha):
    """Una aplicación de insumos del `invernadero` (el origen de los consumos de aplicación)."""
    return AplicacionInsumos.objects.create(
        invernadero=invernadero, tipo_evento="aplicacion", fecha_bitacora=fecha, hora_bitacora=time(9, 0)
    )


def consumo_de(invernadero, existencia_del_insumo, monto, cantidad, fecha, *, siembra=None, aplicacion=None, orden_de_entrega=None):
    """Un `Consumo` del `invernadero` con exactamente un origen (`siembra`, `aplicacion` u `orden_de_entrega`), con su fecha de consumo."""
    return Consumo.objects.create(
        invernadero=invernadero,
        tipo_evento="consumo",
        fecha_bitacora=fecha,
        hora_bitacora=time(9, 0),
        monto_consumo=Decimal(monto),
        cant_consumo=Decimal(cantidad),
        fecha_consumo=fecha,
        insumo_invernadero=existencia_del_insumo,
        siembra=siembra,
        aplicacion=aplicacion,
        orden=orden_de_entrega,
    )


def existencia_de_envase(invernadero, nombre="Bolsa", unidad="unidad"):
    """Un insumo de la categoría del sistema «envases» habilitado en el `invernadero` (lo que consume una entrega)."""
    return existencia(insumo(nombre, tipo=categoria_del_sistema("envases"), unidad=unidad), invernadero, precio="1.00")


def existencia_de(invernadero, insumo_del_catalogo):
    """El mismo insumo del catálogo habilitado también en otro `invernadero` (los insumos del catálogo se comparten entre invernaderos)."""
    return existencia(insumo_del_catalogo, invernadero, precio="1.00")


def instante_utc(anio, mes, dia, hora, minuto=0):
    """Un instante en UTC (para armar alertas cuyo día LOCAL, UTC−03:00, difiere del día UTC)."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=zona.utc)


__all__ = [
    "HOY", "DESDE", "dos_invernaderos", "lote_sembrado", "lote_cargado", "otra_variedad", "nombre_de", "orden", "merma_de", "merma_de_camara",
    "salida_por_cosecha", "aplicacion_de", "consumo_de", "existencia_de_envase", "existencia_de", "instante_utc", "insumo_adicional",
]
