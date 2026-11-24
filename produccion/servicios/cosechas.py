# Núcleo físico de la cosecha (COM-04a, D-64 punto 2; docs/api/produccion.md, sección 8). NO son casos de uso: los llama PROD-CNC-CSC (en
# `comercial`, que decide qué pasa con las reservas) dentro de su transacción, con el invernadero, la variedad, los sectores y los lotes YA
# bloqueados (docs/patrones/bloqueos.md). No auditan ni notifican: devuelven lo que crearon para el único registro del caso de uso (D-36).
# Fuente: PROD-CNC-CSC (postcondiciones a a e y g), docs/patrones/costo_del_lote.md y D-64 puntos 3 y 4.

from collections import namedtuple
from decimal import Decimal

from django.utils import timezone

from inventario.servicios import stock
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Cosecha, Lote, MovimientoStock, OcupacionSector, OrdenTrabajo
from produccion.servicios import costos, movimientos
from produccion.servicios.mermas import plantas

# Lo que devuelve `cosechar_lote`: lo cosechado, el costo por planta de ANTES (4 decimales), lo que bajó del costo del lote, el registro de
# bitácora y el movimiento de stock (`None` si no se cosechó nada).
ResultadoCosechaDeLote = namedtuple("ResultadoCosechaDeLote", "cantidad costo_unitario costo bitacora movimiento")


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


def cosechar_lote(cosecha, lote, por_sector, fecha, responsable):
    """Baja `lote` en lo cosechado (`por_sector`: `{sector_id: plantas}`, 0 vale) y registra la bitácora y el movimiento (PROD-CNC-CSC, a a e y g).

    - Corre en la transacción de quien llama (sin ella, `RuntimeError`), con el lote ya bloqueado y releído. No audita ni notifica.
    - Calcula el costo por planta ANTES (`movimientos.costo_por_planta_exacto`, 4 decimales) y baja `cantidad_actual` y `costo_acumulado` con
      `costos.costo_de_la_merma` (si se cosecha todo, el costo entero: no sobran ni faltan centavos). Con cantidad 0 el lote no cambia.
    - Baja los agujeros ocupados de cada ocupación vigente (postcondición d); un lote que llega a 0 queda «finalizado» con costo 0 y sus
      ocupaciones conservan el lote.
    - Crea la `Bitacora` de tipo `cosecha` (con `cosecha`, el lote, su etapa actual, el invernadero, los sectores de `por_sector`, el responsable y
      la fecha efectiva con la hora actual) incluso si el lote rindió 0 (R152) y, si la cantidad es mayor que 0, el `MovimientoStock`
      `salida_por_cosecha` (origen: la cosecha; `costo_unitario` = el costo por planta de antes).
    - `ErrorDeProduccion('cosecha_supera_sector')` (extensión 8a) si un sector pasa de los agujeros que el lote ocupa en él; con
      `datos={"sector_id", "ocupados"}`. `cantidad_invalida` si una cantidad no es un entero mayor o igual que 0.
    """
    movimientos.exigir_transaccion("cosechar_lote")
    ocupaciones = list(
        OcupacionSector.objects.select_for_update(no_key=True).filter(lote=lote, cant_agujeros_ocupados__gt=0).order_by("pk")
    )
    ocupados = {}
    for o in ocupaciones:
        ocupados[o.sector_id] = ocupados.get(o.sector_id, 0) + o.cant_agujeros_ocupados
    for sector_id, plantas_del_sector in por_sector.items():
        if not isinstance(plantas_del_sector, int) or isinstance(plantas_del_sector, bool) or plantas_del_sector < 0:
            raise _error("cantidad_invalida", "Las plantas cosechadas deben ser un número entero, cero o más.", "cantidad")
        if plantas_del_sector > ocupados.get(sector_id, 0):
            raise _error(
                "cosecha_supera_sector",
                f"El lote {lote.codigo} ocupa {ocupados.get(sector_id, 0)} agujeros en ese sector: no se pueden cosechar {plantas_del_sector}.",
                "cantidad",
                {"sector_id": sector_id, "ocupados": ocupados.get(sector_id, 0)},
            )
    total = sum(por_sector.values())
    costo_unitario = movimientos.costo_por_planta_exacto(lote)
    costo = costos.costo_de_la_merma(lote, total) if total else Decimal("0.00")
    if total:
        quedan = lote.cantidad_actual - total
        lote.cantidad_actual = quedan
        lote.costo_acumulado = costos.redondear_monto(Decimal(lote.costo_acumulado) - costo) if quedan else Decimal("0.00")
        lote.estado_lote = Lote.Estado.ACTIVO if quedan else Lote.Estado.FINALIZADO
        Lote.objects.filter(pk=lote.pk).update(
            cantidad_actual=lote.cantidad_actual, costo_acumulado=lote.costo_acumulado, estado_lote=lote.estado_lote
        )
        # Postcondición d: cada sector libera lo que se cosechó ahí (si hay dos ocupaciones del mismo sector, en orden).
        faltan = {sector_id: q for sector_id, q in por_sector.items() if q}
        for o in ocupaciones:
            baja = min(faltan.get(o.sector_id, 0), o.cant_agujeros_ocupados)
            if baja:
                o.cant_agujeros_ocupados -= baja
                o.save(update_fields=["cant_agujeros_ocupados"])
                faltan[o.sector_id] -= baja
    registro = Bitacora.objects.create(
        invernadero_id=lote.invernadero_id,
        lote=lote,
        etapa_id=lote.etapa_id,
        responsable=responsable,
        fecha_bitacora=fecha,
        hora_bitacora=timezone.localtime().time(),
        tipo_evento=Bitacora.TipoEvento.COSECHA,
        cosecha=cosecha,
        descripcion_evento=f"Cosecha {cosecha.codigo}: {plantas(total)} de {lote.codigo}."[:500],
    )
    registro.sectores.set(list(por_sector))
    movimiento = None
    if total:
        movimiento = movimientos.registrar(
            MovimientoStock.TipoMovimiento.SALIDA_POR_COSECHA, total, costo_unitario, cosecha, lote=lote, fecha=fecha
        )
    return ResultadoCosechaDeLote(total, costo_unitario, costo, registro, movimiento)


def concretar_orden(cosecha, fecha):
    """Pasa la cosecha a «concretada» con `fecha_resolucion_orden` = hoy y `fecha_cosecha` = la efectiva `fecha` (postcondición a).
    Corre en la transacción de quien llama, con la cosecha ya bloqueada. `ErrorDeProduccion('orden_no_a_realizar')` (extensión 13b) si ya no
    estaba «a realizar»; el estado se relee de la base."""
    movimientos.exigir_transaccion("concretar_orden")
    estado = OrdenTrabajo.objects.filter(pk=cosecha.pk).values_list("estado_orden", flat=True).first()
    if estado != OrdenTrabajo.Estado.A_REALIZAR:
        raise _error(
            "orden_no_a_realizar",
            f"La orden {cosecha.codigo} ya no está «a realizar»: su estado actual es «{OrdenTrabajo.Estado(estado).label}».",
        )
    hoy = stock.hoy()
    OrdenTrabajo.objects.filter(pk=cosecha.pk).update(estado_orden=OrdenTrabajo.Estado.CONCRETADA, fecha_resolucion_orden=hoy)
    Cosecha.objects.filter(pk=cosecha.pk).update(fecha_cosecha=fecha)
    cosecha.estado_orden, cosecha.fecha_resolucion_orden, cosecha.fecha_cosecha = OrdenTrabajo.Estado.CONCRETADA, hoy, fecha
    return cosecha


def costo_unitario_de_cosecha(cosecha_ids, lote_ids):
    """`{(cosecha_id, lote_id): costo_unitario}` de cada «salida por cosecha» (D-64 punto 3: la partida que nace después, p. ej. el rechazo de un
    faltante, toma ESTE costo y no el del lote de hoy). Una sola consulta; un lote que rindió 0 no tiene salida y no figura."""
    cosecha_ids, lote_ids = list(cosecha_ids), list(lote_ids)
    if not cosecha_ids or not lote_ids:
        return {}
    filas = MovimientoStock.objects.filter(
        tipo_movimiento=MovimientoStock.TipoMovimiento.SALIDA_POR_COSECHA, origen_id__in=cosecha_ids, lote_id__in=lote_ids
    ).values_list("origen_id", "lote_id", "costo_unitario")
    return {(cosecha_id, lote_id): costo for cosecha_id, lote_id, costo in filas}
