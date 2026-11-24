# Núcleo de la merma de un lote en pie (PRD-02, paso 3). NO es un caso de uso: es una función interna que corre en la transacción de
# quien la llama (Concretar Transición, PRD-02; Registrar Merma, PRD-03; Sector fuera de servicio, PRD-04) con el invernadero, la
# variedad, los sectores y el lote YA bloqueados (docs/patrones/bloqueos.md, sección `produccion`). No audita ni notifica: devuelve lo
# que creó para que el caso de uso lo ponga en su único registro de auditoría (D-36).
# Fuente: docs/casos_de_uso/produccion/transicion.md (extracto de PROD-REG-MRM y «Núcleo de la merma desde la transición»),
# docs/api/produccion.md (sección 6), docs/patrones/costo_del_lote.md, D-50 punto 6 y D-51 punto 5.
# Fuera de la ronda (D-45): el movimiento de stock «salida por merma» (postcondición d), el asiento (e) y la partida en cámara. La condición 1
# de plantas comprometidas (reservas de cosecha) la suma COM-02 (D-59), con `produccion.extensiones.reservado_de_lotes`.
# PRD-03 suma, al final, el caso de uso PROD-REG-MRM (Registrar Merma) sobre este núcleo: `registrar_merma` y sus lecturas.

from collections import namedtuple
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection, transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone

from core.models import RegistroAuditoria, Usuario, referencia
from inventario.servicios import variedades
from maestros.servicios import alertas, configuracion
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion import extensiones
from produccion.errores import ErrorDeProduccion
from produccion.models import AlertaDeMerma, Cosecha, Lote, Merma, MovimientoStock, OcupacionSector, OrdenTrabajo, TransicionEtapa
from produccion.servicios import alcance, costos, movimientos
from produccion.servicios.bloqueos import traducir as _bloquear

# Lo que devuelve `aplicar_merma`: la merma creada, lo que costó (se descontó del costo acumulado del lote) y las alertas creadas.
ResultadoMerma = namedtuple("ResultadoMerma", "merma costo alertas")

TIPO_UMBRAL = "produccion_merma_umbral"
TIPO_PLANTAS_COMPROMETIDAS = "produccion_plantas_comprometidas"
LARGO_DE_LA_DESCRIPCION = 300  # la que escribe quien registra; con el texto legible entra siempre en los 500 de la bitácora
LARGO_DE_LA_ALERTA = 200  # `Alerta.descripcion_alerta`


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


def plantas(cantidad):
    """«1 planta» o «12 plantas»."""
    return f"{cantidad} {'planta' if cantidad == 1 else 'plantas'}"


def _acotar(prefijo, variable, sufijo):
    """`prefijo + variable + sufijo` sin pasar de 200 caracteres: si no entra, se acorta `variable` (el nombre de la variedad) con «…»."""
    sobra = len(prefijo) + len(variable) + len(sufijo) - LARGO_DE_LA_ALERTA
    if sobra > 0:
        variable = variable[: max(0, len(variable) - sobra - 1)] + "…"
    return (prefijo + variable + sufijo)[:LARGO_DE_LA_ALERTA]


def _acumulada(lote):
    """Σ de las plantas de las mermas del lote en pie (con etapa; las de cámara no cuentan) sin el «descarte por selección»."""
    return (
        Merma.objects.filter(lote=lote, etapa__isnull=False)
        .exclude(causa=Merma.Causa.DESCARTE_POR_SELECCION)
        .aggregate(total=Sum("cant_merma"))["total"]
        or 0
    )


def merma_acumulada(lote):
    """Regla «Merma acumulada de un lote»: Σ de las mermas del lote en pie ÷ cantidad inicial, en porcentaje con 2 decimales
    (`ROUND_HALF_UP`). No cuenta el descarte por selección ni las mermas sin etapa (cámara, regla 7 de 8.9)."""
    return (Decimal(_acumulada(lote)) * 100 / lote.cantidad_inicial).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _verificar(lote, cantidad, causa, descripcion, fecha, por_sector):
    """Las reglas del núcleo (orden: cantidad, causa, descripción, fecha, sectores). Devuelve la descripción sin espacios al borde y
    las ocupaciones vigentes del lote (solo si viene `por_sector`, bloqueadas en orden de id)."""
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or not 0 < cantidad <= lote.cantidad_actual:
        raise _error(
            "cantidad_invalida",
            f"La cantidad perdida debe ser entre 1 y {lote.cantidad_actual} (las plantas del lote {lote.codigo}).",
            "cantidad",
        )
    if not causa:
        raise _error("causa_obligatoria", "Indicá la causa de la merma.", "causa")
    if causa not in Merma.CAUSAS_EN_PIE:  # COM-04a: `Merma.Causa` suma las de cámara y entrega
        raise _error("causa_invalida", "Esa causa no corresponde a un lote en pie.", "causa")
    descripcion = (descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    if fecha > timezone.localdate():
        raise _error("fecha_invalida", "La fecha de la merma no puede ser posterior a hoy.", "fecha")
    ocupaciones = []
    if por_sector is not None:
        ocupaciones = list(
            OcupacionSector.objects.select_for_update(no_key=True)
            .filter(lote=lote, cant_agujeros_ocupados__gt=0)
            .order_by("pk")
        )
        ocupadas = {o.sector_id: o.cant_agujeros_ocupados for o in ocupaciones}
        if sum(por_sector.values()) != cantidad or any(q < 0 or q > ocupadas.get(sector_id, 0) for sector_id, q in por_sector.items()):
            raise _error(
                "cantidad_invalida", "Las plantas perdidas por sector deben sumar la cantidad perdida y no superar las del lote ahí.", "cantidad"
            )
    return descripcion, ocupaciones


def _alerta_de_umbral(lote, merma):
    """Postcondición k y extensión 10b: si la merma acumulada SUPERA el porcentaje máximo y el lote todavía no tuvo una alerta de
    umbral, alerta al Agrónomo y al Gerente (decisión del estudiante, 22/11/2026: «supera y no tuvo alerta», para que un lote que ya
    estaba por encima la reciba aunque el porcentaje haya cambiado). Se compara con enteros: `acumulada × 100 > porcentaje × inicial`."""
    porcentaje = configuracion.obtener().porc_merma_maxima
    if _acumulada(lote) * 100 <= porcentaje * lote.cantidad_inicial:
        return None
    if AlertaDeMerma.objects.filter(merma__lote=lote, alerta__tipo_alerta=TIPO_UMBRAL).exists():
        return None
    acumulada = f"{(Decimal(_acumulada(lote)) * 100 / lote.cantidad_inicial).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}".replace(".", ",")
    descripcion = _acotar(f"{lote.codigo}: merma de {acumulada} % (", str(lote.siembra.variedad), f"). Superó el {porcentaje} % tolerado.")
    return alertas.crear_alerta_de_evento(lote.invernadero_id, TIPO_UMBRAL, descripcion)


def _alerta_por_reservas_de_cosecha(lote):
    """Condición 1 de la regla 15 de 8.8 (COM-02, D-59; «Diferencias», fila 8): lo reservado en líneas de reservas «activas» del lote
    (`extensiones.reservado_de_lotes`) supera su `cantidad_actual` y quedan cosechas sin cobertura. Una sola alerta por lote y por merma.
    Nombra las cosechas «a realizar» que lo usan con `detalle_de_cosechas` (lo pide la extensión 10a: «qué órdenes de cosecha quedaron
    sin cobertura»). Sin registrante (o sin reservas) no hace nada."""
    reservado = extensiones.reservado_de_lotes([lote.pk])[lote.pk]
    if reservado <= lote.cantidad_actual:
        return None
    candidatas = list(
        Cosecha.objects.filter(
            invernadero_id=lote.invernadero_id, variedad_id=lote.siembra.variedad_id, estado_orden=OrdenTrabajo.Estado.A_REALIZAR
        ).order_by("pk")
    )
    detalle = extensiones.detalle_de_cosechas([c.pk for c in candidatas])
    codigos = [c.codigo for c in candidatas if any(lote_id == lote.pk for lote_id, _, _ in detalle[c.pk].lotes)] if detalle else []
    texto = f"{lote.codigo} tiene {lote.cantidad_actual} plantas y {reservado} reservadas para cosechas"
    if codigos:
        texto += f": {', '.join(codigos)}"
    return alertas.crear_alerta_de_evento(lote.invernadero_id, TIPO_PLANTAS_COMPROMETIDAS, (texto + ".")[:LARGO_DE_LA_ALERTA])


def _alertas_de_plantas_comprometidas(lote, ordenes_excluidas):
    """Postcondición l y extensión 10a, condición 2 de la regla 15 de 8.8: la transición «a realizar» del lote (sin contar las
    `ordenes_excluidas`) queda con más plantas planificadas que `cantidad_actual`. Una alerta por orden afectada. La condición 1 (reservas
    de cosecha) la suma COM-02 al final de la lista."""
    creadas = []
    pendientes = TransicionEtapa.objects.filter(lote=lote, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).exclude(
        pk__in=list(ordenes_excluidas)
    )
    for orden in pendientes.order_by("pk"):
        planificadas = OcupacionSector.objects.filter(orden_id=orden.pk).aggregate(t=Sum("cant_agujeros_planificados"))["t"] or 0
        if planificadas > lote.cantidad_actual:
            texto = f"{lote.codigo} tiene {lote.cantidad_actual} plantas y su transición {orden.codigo} planificó {planificadas}."
            creadas.append(alertas.crear_alerta_de_evento(lote.invernadero_id, TIPO_PLANTAS_COMPROMETIDAS, texto[:LARGO_DE_LA_ALERTA]))
    creadas.append(_alerta_por_reservas_de_cosecha(lote))
    return creadas


def aplicar_merma(lote, cantidad, causa, descripcion, fecha, responsable, *, por_sector=None, sector_ids=(), ordenes_excluidas=()):
    """Registra la pérdida de `cantidad` plantas de `lote` (PROD-REG-MRM, lote en pie) y devuelve `ResultadoMerma(merma, costo, alertas)`.

    - Corre en la transacción de quien llama (sin ella, `RuntimeError`), con el lote ya bloqueado y releído. No audita ni notifica.
    - Postcondición a: crea la `Merma` (hija de `Bitacora`, tipo «merma») en la etapa ACTUAL del lote (la de origen, porque se ejecuta
      antes del traslado), con `fecha` (la efectiva, que puede ser anterior a hoy) y la hora actual. `descripcion_evento` es legible
      («Merma de 12 plantas por plaga.») más la descripción de `responsable`, si la hay (hasta 300 caracteres). `sectores` = `sector_ids`.
    - Postcondición b: baja `cantidad_actual` y `costo_acumulado` con `costos.costo_de_la_merma`; con cantidad cero el lote queda
      «finalizado» con costo 0. Cambia también la instancia recibida.
    - Postcondición c: solo si viene `por_sector` (`{sector_id: plantas}`, que pasa Registrar Merma, PRD-03): baja los agujeros ocupados de
      cada ocupación afectada (si el lote se pierde entero quedan todas en cero y CONSERVAN su lote, como en la concreción de una
      transición). Sin `por_sector` no toca ocupaciones: Concretar Transición libera todos los agujeros de origen.
    - Postcondiciones k y l: alerta de umbral y alertas de plantas comprometidas (condición 2: la transición; condición 1, desde COM-02: las
      reservas de cosecha), enlazadas con la merma por `AlertaDeMerma`.
      Un invernadero inactivo no genera alertas (`crear_alerta_de_evento` da `None`): la merma se registra igual.
    - Rechaza con `ErrorDeProduccion`: `cantidad_invalida`, `causa_obligatoria`, `causa_invalida`, `descripcion_larga`, `fecha_invalida`.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("aplicar_merma corre dentro de la transacción del caso de uso que la llama.")
    descripcion, ocupaciones = _verificar(lote, cantidad, causa, descripcion, fecha, por_sector)
    costo = costos.costo_de_la_merma(lote, cantidad)  # antes de cambiar la cantidad del lote (docs/patrones/costo_del_lote.md)
    costo_unitario = movimientos.costo_por_planta_exacto(lote)  # COM-04a: el costo por planta de ANTES, para el movimiento
    texto = f"Merma de {plantas(cantidad)} por {Merma.Causa(causa).label.lower()}."
    merma = Merma.objects.create(
        invernadero_id=lote.invernadero_id,
        lote=lote,
        etapa_id=lote.etapa_id,
        tipo_evento="merma",
        fecha_bitacora=fecha,
        hora_bitacora=timezone.localtime().time(),
        responsable=responsable,
        descripcion_evento=f"{texto} {descripcion}" if descripcion else texto,
        cant_merma=cantidad,
        causa=causa,
    )
    if sector_ids:
        merma.sectores.set(list(sector_ids))
    # COM-04a (D-64 punto 2): el movimiento «salida por merma» del lote (origen: la merma).
    movimientos.registrar(MovimientoStock.TipoMovimiento.SALIDA_POR_MERMA, cantidad, costo_unitario, merma, lote=lote, fecha=fecha)
    # Postcondición b.
    quedan = lote.cantidad_actual - cantidad
    lote.cantidad_actual = quedan
    lote.costo_acumulado = costos.redondear_monto(Decimal(lote.costo_acumulado) - costo) if quedan else Decimal("0.00")
    lote.estado_lote = Lote.Estado.ACTIVO if quedan else Lote.Estado.FINALIZADO
    Lote.objects.filter(pk=lote.pk).update(
        cantidad_actual=lote.cantidad_actual, costo_acumulado=lote.costo_acumulado, estado_lote=lote.estado_lote
    )
    # Postcondición c.
    for ocupacion in ocupaciones:
        perdidas = por_sector.get(ocupacion.sector_id, 0)
        if perdidas:
            ocupacion.cant_agujeros_ocupados -= perdidas
            ocupacion.save(update_fields=["cant_agujeros_ocupados"])
    # Postcondiciones k y l.
    creadas = [_alerta_de_umbral(lote, merma), *_alertas_de_plantas_comprometidas(lote, ordenes_excluidas)]
    creadas = [a for a in creadas if a is not None]
    for alerta in creadas:
        AlertaDeMerma.objects.create(merma=merma, alerta=alerta)
    return ResultadoMerma(merma, costo, creadas)


def aplicar_merma_de_entrega(orden, lote, cantidad, descripcion, responsable):
    """Merma «daño en la entrega» (COM-04a para COM-06a; docs/api/produccion.md, sección 10; D-68 punto 3): `Merma` con causa `dano_en_entrega`, la
    `orden` (la entrega, vista como `OrdenTrabajo`), el LOTE DE ORIGEN (R144), el invernadero de la orden, SIN etapa ni sectores, fecha y hora
    actuales y `responsable`. NO toca el lote (ni cantidad, costo ni agujeros: el producto ya fue cosechado) ni crea `MovimientoStock`: lo perdido
    ya salió del stock con la «salida por cosecha» o el egreso de la partida. Sin etapa, no suma a `merma_acumulada`. Corre en la transacción
    de quien llama (sin ella, `RuntimeError`); no audita ni notifica. `cantidad_invalida` si `cantidad <= 0`. Devuelve la `Merma`."""
    movimientos.exigir_transaccion("aplicar_merma_de_entrega")
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise _error("cantidad_invalida", "La cantidad perdida debe ser un número entero mayor que cero.", "cantidad")
    descripcion = (descripcion or "").strip()
    texto = f"Merma de {plantas(cantidad)} por {Merma.Causa.DANO_EN_ENTREGA.label.lower()}."
    return Merma.objects.create(
        invernadero_id=orden.invernadero_id,
        lote=lote,
        etapa=None,
        tipo_evento="merma",
        fecha_bitacora=timezone.localdate(),
        hora_bitacora=timezone.localtime().time(),
        responsable=responsable,
        descripcion_evento=f"{texto} {descripcion}"[:500] if descripcion else texto,
        cant_merma=cantidad,
        causa=Merma.Causa.DANO_EN_ENTREGA,
        orden_id=orden.pk,
    )


# ---- PROD-REG-MRM · Registrar Merma (PRD-03): el caso de uso sobre el núcleo de arriba ----
# Fuente: docs/casos_de_uso/produccion/merma.md («Cómo se aplica en la ronda «Producción 1»»), docs/patrones/bloqueos.md (sección
# `produccion`, «Lote 5») y D-83. Solo el lote en pie (D-45): sin partidas de cámara, asiento ni movimiento de stock.

FilaDeLoteConMerma = namedtuple("FilaDeLoteConMerma", "lote_id codigo variedad etapa cantidad_actual")
FilaDeSectorConMerma = namedtuple("FilaDeSectorConMerma", "sector_id nombre ocupados")
# Lo que presenta el paso 6. `causas` es `[(valor, texto)]`; `merma_acumulada` y `porcentaje_maximo` son porcentajes.
PropuestaDeMerma = namedtuple(
    "PropuestaDeMerma", "lote variedad etapa invernadero cantidad_actual sectores merma_acumulada porcentaje_maximo causas"
)
# El resumen del paso 8. `por_sector` es `[(sector, plantas)]` (con todos los sectores del lote); `transiciones_sin_cobertura`, `[(orden, planificadas)]`.
ResumenDeMerma = namedtuple(
    "ResumenDeMerma",
    "lote variedad etapa invernadero por_sector total causa descripcion cantidad_actual cantidad_resultante "
    "merma_acumulada_resultante porcentaje_maximo supera_umbral transiciones_sin_cobertura lote_finalizado",
)
# Todo lo que `_planear` resuelve y que `registrar_merma` usa para escribir. `por_sector` es `{sector_id: plantas}` (solo las mayores que cero).
PlanDeMerma = namedtuple("PlanDeMerma", "lote invernadero ocupaciones por_sector total causa descripcion")


@dataclass(frozen=True)
class DatosDeMerma:
    """Lo que la persona carga en el paso 7 (`cantidades` es `((sector_id, plantas), ...)`; los sectores que no figuran valen cero) y lo que
    VIO: `cantidad_actual` del lote y `ocupados` (`((sector_id, ocupados), ...)`). Si al confirmar cambiaron, `cambio_simultaneo` con lo
    vigente (extensión 10d); `None` no lo verifica. No hay fecha: la merma es de hoy."""

    lote_id: int
    cantidades: tuple = ()
    causa: str = ""
    descripcion: str = ""
    cantidad_actual: int | None = None
    ocupados: tuple | None = None


def _lote_del_actor(actor, lote_id):
    """El lote (con lo que se muestra cargado) de un invernadero activo del actor. `sin_permiso` si el actor no puede registrar o el lote
    no es de un invernadero suyo, `Http404` si no existe, `invernadero_inactivo` y `lote_no_activo` (campo `lote`)."""
    alcance.exigir_actor(actor)
    lote = (
        Lote.objects.select_related("invernadero", "siembra__variedad__cultivo", "etapa__tipo_etapa").filter(pk=lote_id).first()
    )
    if lote is None:
        raise Http404("No existe ese lote.")
    alcance.exigir_en_alcance(actor, lote.invernadero)
    if lote.estado_lote != Lote.Estado.ACTIVO:
        raise _error("lote_no_activo", f"El lote {lote.codigo} ya no está activo.", "lote")
    return lote


def _ocupaciones_vigentes(lote):
    """Las ocupaciones del lote con agujeros ocupados (paso 6), con su sector, por id."""
    return list(
        OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0).select_related("sector").order_by("pk")
    )


def _exigir_lo_visto(lote, ocupadas, datos):
    """Extensión 10d: si lo que la persona vio (la cantidad actual del lote y los agujeros ocupados por sector) ya no es lo vigente,
    `cambio_simultaneo` con lo vigente en `datos`."""
    cambio = datos.cantidad_actual is not None and datos.cantidad_actual != lote.cantidad_actual
    if datos.ocupados is not None and {s: o for s, o in datos.ocupados} != ocupadas:
        cambio = True
    if cambio:
        raise _error(
            "cambio_simultaneo",
            f"Mientras cargabas los datos, el lote {lote.codigo} cambió: ahora tiene {plantas(lote.cantidad_actual)}. Volvé a cargar las cantidades.",
            None,
            {"cantidad_actual": lote.cantidad_actual, "ocupados": ocupadas},
        )


def _exigir_cantidades(ocupadas, datos):
    """Extensiones 8a y 8b y regla «Cantidad válida»: cada sector entre cero y los agujeros que el lote ocupa ahí; en total, al menos una
    planta. Devuelve `{sector_id: plantas}` solo con las mayores que cero."""
    por_sector = {}
    for sector_id, cantidad in datos.cantidades:
        if not isinstance(cantidad, int) or isinstance(cantidad, bool) or not 0 <= cantidad <= ocupadas.get(sector_id, 0):
            ahi = ocupadas.get(sector_id, 0)
            raise _error(
                "cantidad_invalida",
                f"Las plantas perdidas en ese sector deben ser entre 0 y {ahi} (los agujeros que el lote ocupa ahí).",
                f"sector_{sector_id}",
                {"ocupados": ahi},
            )
        por_sector[sector_id] = por_sector.get(sector_id, 0) + cantidad
    por_sector = {s: q for s, q in por_sector.items() if q > 0}
    if any(q > ocupadas.get(s, 0) for s, q in por_sector.items()):  # el mismo sector repetido no puede pasarse
        raise _error("cantidad_invalida", "Las plantas perdidas en un sector no pueden superar las que el lote ocupa ahí.", "cantidad")
    if not por_sector:
        raise _error("cantidad_invalida", "La merma debe ser de al menos una planta.", "cantidad", {"minimo": 1})
    return por_sector


def _planear(actor, datos):
    """Todas las verificaciones de los pasos 7 y 8 y de la extensión 10d, con lo que haya en la base en este momento (registrar vuelve a
    llamarla después de bloquear). No escribe. Orden: alcance y estado, lo visto (10d), cantidades (8a, 8b), causa (8c) y descripción."""
    lote = _lote_del_actor(actor, datos.lote_id)
    ocupaciones = _ocupaciones_vigentes(lote)
    ocupadas = {o.sector_id: o.cant_agujeros_ocupados for o in ocupaciones}
    _exigir_lo_visto(lote, ocupadas, datos)
    por_sector = _exigir_cantidades(ocupadas, datos)
    if not datos.causa:
        raise _error("causa_obligatoria", "Indicá la causa de la merma.", "causa")
    if datos.causa not in Merma.CAUSAS_EN_PIE:
        raise _error("causa_invalida", "Esa causa no corresponde a un lote en pie.", "causa")
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    return PlanDeMerma(lote, lote.invernadero, ocupaciones, por_sector, sum(por_sector.values()), datos.causa, descripcion)


def lotes_con_merma_posible(actor, invernadero_id):
    """Paso 4: los lotes ACTIVOS del invernadero con su variedad, etapa y cantidad actual, por id. Lista vacía si no tiene (extensión 4b: la
    pantalla lo informa y ofrece otro invernadero o cancelar). `sin_permiso`, `invernadero_inactivo` o `Http404` como `alcance.invernadero_del_actor`."""
    invernadero = alcance.invernadero_del_actor(actor, invernadero_id)
    lotes = (
        Lote.objects.filter(invernadero=invernadero, estado_lote=Lote.Estado.ACTIVO)
        .select_related("siembra__variedad__cultivo", "etapa__tipo_etapa")
        .order_by("pk")
    )
    return [
        FilaDeLoteConMerma(l.pk, l.codigo, str(l.siembra.variedad), l.etapa.tipo_etapa.nombre_etapa, l.cantidad_actual) for l in lotes
    ]


def datos_de_merma(actor, lote_id):
    """Paso 6: la cantidad actual del lote, los sectores donde tiene ocupaciones vigentes con sus agujeros ocupados, la merma acumulada, el
    porcentaje máximo y las causas del lote en pie. El actor propone cero plantas en cada sector. No escribe ni bloquea."""
    lote = _lote_del_actor(actor, lote_id)
    return PropuestaDeMerma(
        lote,
        str(lote.siembra.variedad),
        lote.etapa.tipo_etapa.nombre_etapa,
        lote.invernadero,
        lote.cantidad_actual,
        [FilaDeSectorConMerma(o.sector_id, o.sector.nombre_sector, o.cant_agujeros_ocupados) for o in _ocupaciones_vigentes(lote)],
        merma_acumulada(lote),
        configuracion.obtener().porc_merma_maxima,
        [(c.value, c.label) for c in Merma.CAUSAS_EN_PIE],
    )


def _sin_cobertura(lote, cantidad_resultante):
    """Condición 2 de las plantas comprometidas (regla 15 de 8.8): las transiciones «a realizar» del lote con más plantas planificadas que
    `cantidad_resultante`, como `[(orden, planificadas)]`."""
    pendientes = list(TransicionEtapa.objects.filter(lote=lote, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).order_by("pk"))
    planificadas = {
        f["orden_id"]: f["total"]
        for f in OcupacionSector.objects.filter(orden_id__in=[o.pk for o in pendientes])
        .values("orden_id")
        .annotate(total=Sum("cant_agujeros_planificados"))
    }
    return [(o, planificadas.get(o.pk, 0)) for o in pendientes if planificadas.get(o.pk, 0) > cantidad_resultante]


def resumen_de_merma(actor, datos):
    """Paso 8: valida todo como `registrar_merma` (sin bloquear) y presenta el lote, las plantas perdidas por sector y en total, la causa,
    la cantidad resultante y las advertencias (umbral superado, plantas comprometidas sin cobertura). No escribe."""
    plan = _planear(actor, datos)
    lote = plan.lote
    resultante = lote.cantidad_actual - plan.total
    suma = _acumulada(lote) + (0 if plan.causa == Merma.Causa.DESCARTE_POR_SELECCION else plan.total)
    porcentaje = configuracion.obtener().porc_merma_maxima
    return ResumenDeMerma(
        lote,
        str(lote.siembra.variedad),
        lote.etapa.tipo_etapa.nombre_etapa,
        plan.invernadero,
        [(o.sector, plan.por_sector.get(o.sector_id, 0)) for o in plan.ocupaciones],
        plan.total,
        plan.causa,
        plan.descripcion,
        lote.cantidad_actual,
        resultante,
        (Decimal(suma) * 100 / lote.cantidad_inicial).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        porcentaje,
        suma * 100 > porcentaje * lote.cantidad_inicial,
        _sin_cobertura(lote, resultante),
        resultante == 0,
    )


def registrar_merma(actor, datos):
    """PROD-REG-MRM: registra la merma de un lote en pie y devuelve la `Merma`.

    - Quién: Capataz asignado o Agrónomo a cargo, con la cuenta activa (`sin_permiso`); invernadero activo; lote «activo».
    - Verificaciones DESPUÉS de bloquear (todo de nuevo, con lo bloqueado): lo visto (extensión 10d: `cambio_simultaneo` con la cantidad y los
      ocupados vigentes), las cantidades por sector (8a, 8b: `cantidad_invalida`), la causa (8c: `causa_obligatoria`, `causa_invalida`) y la
      descripción (`descripcion_larga`).
    - Postcondiciones a, b, c, k y l: `aplicar_merma(..., por_sector=..., sector_ids=...)`, con la fecha de hoy y el actor como responsable.
      m, n y D-36: UN registro `registro_merma` con la merma (que es el registro de bitácora), el lote, las ocupaciones y los sectores
      afectados (agujeros ocupados antes → después) y las alertas creadas.
    - Bloqueos (docs/patrones/bloqueos.md, sección `produccion`), todos `FOR NO KEY UPDATE`: las cuentas del actor y del Agrónomo (en orden
      de id) → el invernadero → la variedad → los sectores con pérdidas (por id) → el lote → sus ocupaciones (por id). Lo que se leyó antes
      de bloquear se relee. Todo o nada (D-22).
    """
    previo = _lote_del_actor(actor, datos.lote_id)
    pedidos = {s for s, q in datos.cantidades if isinstance(q, int) and q > 0}
    sector_ids = sorted(pedidos & {o.sector_id for o in _ocupaciones_vigentes(previo)})  # los que no son del lote fallan como 8a, sin bloquearlos
    with transaction.atomic():
        cuentas = {actor.pk, *([previo.invernadero.agronomo_id] if previo.invernadero.agronomo_id else [])}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        alcance.exigir_actor(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(
            bloquear_invernadero_activo, previo.invernadero_id, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)}
        )
        _bloquear(variedades.bloquear_variedad, previo.siembra.variedad_id)
        if sector_ids:
            _bloquear(
                api_sectores.bloquear_sectores,
                previo.invernadero_id,
                sector_ids,
                equivalencias={"sector_no_disponible": ("cambio_simultaneo", None)},
            )
        Lote.objects.select_for_update(no_key=True).filter(pk=previo.pk).first()
        list(OcupacionSector.objects.select_for_update(no_key=True).filter(lote_id=previo.pk).order_by("pk"))
        plan = _planear(actor, datos)  # 10d y todas las verificaciones, con lo bloqueado
        return _escribir(actor, plan)


def _escribir(actor, plan):
    """Pasos 10 y 11: `aplicar_merma` con las cantidades por sector y el único registro de auditoría."""
    lote = plan.lote
    sectores = [o.sector for o in plan.ocupaciones if o.sector_id in plan.por_sector]
    afectadas = [o for o in plan.ocupaciones if o.sector_id in plan.por_sector]
    ocupados_antes = {pk: a.ocupados for pk, a in api_sectores.agujeros_de(sectores).items()}
    cantidad_antes, costo_antes, estado_antes = lote.cantidad_actual, Decimal(lote.costo_acumulado), lote.estado_lote
    resultado = aplicar_merma(
        lote, plan.total, plan.causa, plan.descripcion, timezone.localdate(), actor, por_sector=plan.por_sector, sector_ids=sorted(plan.por_sector)
    )
    despues = {pk: a.ocupados for pk, a in api_sectores.agujeros_de(sectores).items()}
    cambios = {
        "cantidad_actual": {"antes": str(cantidad_antes), "despues": str(lote.cantidad_actual)},
        "costo_acumulado": {"antes": str(costo_antes), "despues": str(lote.costo_acumulado)},
        "agujeros_ocupados": {
            "antes": [f"{s.nombre_sector}: {ocupados_antes[s.pk]}" for s in sectores],
            "despues": [f"{s.nombre_sector}: {despues[s.pk]}" for s in sectores],
        },
    }
    if lote.estado_lote != estado_antes:
        cambios["estado"] = {"antes": estado_antes, "despues": lote.estado_lote}
    datos_de_auditoria = {
        "invernadero": referencia(plan.invernadero),
        "lote": referencia(lote),
        "merma": referencia(resultado.merma),
        "cantidad_merma": str(plan.total),
        "causa_merma": Merma.Causa(plan.causa).label,
    }
    if resultado.alertas:
        datos_de_auditoria["alertas_creadas"] = [referencia(a) for a in resultado.alertas]
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.REGISTRO_MERMA,
        afectados=[resultado.merma, lote, *afectadas, *sectores, *resultado.alertas],
        detalle={"cambios": cambios, "datos": datos_de_auditoria},
    )
    return resultado.merma
