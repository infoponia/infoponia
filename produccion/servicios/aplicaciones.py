# Registrar Aplicación de Insumos (PRD-03, PROD-REG-APL): el uso de insumos sin una orden de trabajo (limpieza, nutrientes). Es un registro de
# bitácora (`AplicacionInsumos`) que origina un `Consumo` por insumo, descuenta los lotes de insumo, reparte el costo entre los lotes de plantas del
# alcance (`ImputacionCosto`) y reevalúa las alertas de stock. Las vistas solo orquestan: todas las reglas están acá.
# Fuente: docs/casos_de_uso/produccion/aplicacion_de_insumos.md («Cómo se aplica en la ronda «Producción 1»»), docs/patrones/costo_del_lote.md,
# docs/patrones/bloqueos.md (sección `produccion`, «Lote 5»), D-51 y D-52. Fuera de la ronda (D-45): el asiento (postcondición f) y las
# precondiciones c y d (ejercicio y cuentas). El Capataz NO recibe valores, destinos, reparto ni avisos de stock: los servicios no los devuelven
# (regla «Qué ve cada rol»), no solo la plantilla.

from collections import namedtuple
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario import alertas as alertas_de_inventario
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo, TipoInsumo
from inventario.servicios import insumos_invernadero, stock
from inventario.unidades import Unidad, validar_cantidad
from maestros.models import Alerta, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import AplicacionInsumos, Bitacora, Consumo, ImputacionCosto, Lote, OcupacionSector
from produccion.servicios import alcance, costos
from produccion.servicios.bloqueos import traducir as _bloquear

# `_partes_de_salida` es el único lugar que sabe cómo mandar el resto sin lote al «faltante sin lote» de `inventario` (PRD-01): se reutiliza.
from produccion.servicios.siembras import _partes_de_salida

CERO = Decimal("0")
LARGO_DE_LA_DESCRIPCION = 500
GASTO, COSTO_DE_LOS_LOTES = "gasto", "costo_de_los_lotes"
CAPATAZ = Usuario.Rol.CAPATAZ

FilaDeSectorAplicable = namedtuple("FilaDeSectorAplicable", "sector_id nombre tipo_etapa")
FilaDeInsumoAplicable = namedtuple(
    "FilaDeInsumoAplicable", "existencia_id insumo_id nombre unidad controla_vencimiento stock_libre lotes precio destino"
)
FilaDeReparto = namedtuple("FilaDeReparto", "lote_id codigo plantas porcentaje monto costo_por_planta_antes costo_por_planta_despues")
LineaDeResumen = namedtuple(
    "LineaDeResumen", "existencia_id insumo_id nombre unidad cantidad partes faltante valor destino reparto aviso"
)
ResumenDeAplicacion = namedtuple("ResumenDeAplicacion", "invernadero sectores descripcion lineas total_a_gasto")
ResultadoDeAplicacion = namedtuple("ResultadoDeAplicacion", "aplicacion lineas")


@dataclass(frozen=True)
class LineaDeAplicacion:
    """Un insumo y su cantidad (pasos 7 y 8). `reparto` es `((lote_insumo_id, cantidad), ...)` y solo vale si el insumo controla vencimiento
    (extensión 8c). `lotes_vistos` es `((lote_insumo_id, disponible), ...)`: los lotes vigentes que la persona vio (extensión 12a); con él, un insumo
    que ya no es aplicable es `cambio_simultaneo` y no `insumo_no_aplicable`. `cantidad` llega como texto o `Decimal`, nunca `float`."""

    existencia_id: int
    cantidad: object
    reparto: tuple | None = None
    lotes_vistos: tuple | None = None


@dataclass(frozen=True)
class DatosDeAplicacion:
    """Lo que la persona carga (pasos 3 a 9). `alcance` es «todo» (todos los sectores activos) o «sectores» (los de `sector_ids`).
    `plantas_vistas` es `((lote_id, plantas), ...)`: las plantas de los lotes del alcance que vio (extensión 12a); `None` no lo verifica."""

    invernadero_id: int
    alcance: str = "todo"
    sector_ids: tuple = ()
    lineas: tuple = ()
    descripcion: str = ""
    plantas_vistas: tuple | None = None


# Todo lo que `_planear` resuelve y que `registrar_aplicacion` usa para escribir. `lineas` son `LineaPlan`; `sectores` los de la bitácora (vacío = todo).
PlanDeAplicacion = namedtuple("PlanDeAplicacion", "invernadero sectores alcance_ids descripcion lineas plantas_por_lote lotes")
LineaPlan = namedtuple("LineaPlan", "existencia cantidad partes faltante valor destino reparto aviso")


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


def _texto(cantidad):
    """Una cantidad sin ceros de más: `Decimal('50.000')` → `'50'`."""
    return format(Decimal(cantidad).normalize(), "f")


def _es_capataz(actor):
    return rol_de(actor) == CAPATAZ


# ---- Lectura ----


def sectores_de_aplicacion(actor, invernadero_id):
    """Paso 4: los sectores ACTIVOS del invernadero (los fuera de servicio no se pueden elegir), por tipo de etapa y nombre."""
    invernadero = alcance.invernadero_del_actor(actor, invernadero_id)
    sectores = SectorProduccion.objects.filter(
        invernadero=invernadero, estado_sector=SectorProduccion.Estado.ACTIVO
    ).select_related("tipo_etapa")
    return [
        FilaDeSectorAplicable(s.pk, s.nombre_sector, s.tipo_etapa.nombre_etapa)
        for s in sorted(sectores, key=lambda s: (s.tipo_etapa_id, s.nombre_sector.lower(), s.pk))
    ]


def _aplicables(invernadero_id):
    """Los `InsumoInvernadero` habilitados y activos con consumo directo «como gasto» o «como costo de los lotes» (paso 6), por nombre."""
    return [
        iin
        for iin in insumos_invernadero.habilitados(invernadero_id)
        if iin.insumo.activo and iin.insumo.tipo_insumo.consumo_directo != TipoInsumo.ConsumoDirecto.NO_ADMITE
    ]


def _lotes_vigentes(iin_ids, hoy):
    """`{existencia_id: [LoteInsumo]}`: los lotes comunes vigentes con stock de cada existencia, en orden FEFO (los que vencen antes primero; los sin
    fecha al final, por ingreso). Una consulta para todos."""
    lotes = {i: [] for i in iin_ids}
    for lote in LoteInsumo.objects.filter(insumo_invernadero_id__in=list(iin_ids), es_faltante_sin_lote=False, cantidad_disponible__gt=0):
        if not stock.esta_vencido(lote, hoy):
            lotes[lote.insumo_invernadero_id].append(lote)
    for lista in lotes.values():
        lista.sort(key=lambda l: (l.fecha_vencimiento is None, l.fecha_vencimiento or hoy, l.fecha_ingreso, l.pk))
    return lotes


def insumos_aplicables(actor, invernadero_id):
    """Paso 6: los insumos que se ofrecen en el invernadero con su stock libre (sin lotes vencidos) y sus lotes vigentes. Al Agrónomo, además, el
    precio de referencia y el destino del costo; al Capataz, no (`None`). Lista vacía si no hay ninguno (extensión 6b)."""
    invernadero = alcance.invernadero_del_actor(actor, invernadero_id)
    aplicables = _aplicables(invernadero.pk)
    hoy = stock.hoy()
    existencias = stock.existencias([i.pk for i in aplicables], hoy)
    lotes = _lotes_vigentes([i.pk for i in aplicables], hoy)
    ve_valores = not _es_capataz(actor)
    return [
        FilaDeInsumoAplicable(
            iin.pk,
            iin.insumo_id,
            iin.insumo.nombre_insumo,
            iin.insumo.unidad_medida_insumo,
            iin.insumo.controla_vencimiento,
            existencias[iin.pk].libre,
            [(l.pk, l.cantidad_disponible, l.fecha_vencimiento) for l in lotes[iin.pk]],
            iin.referencia_precio if ve_valores else None,
            _destino_de_la_categoria(iin) if ve_valores else None,
        )
        for iin in aplicables
    ]


def _destino_de_la_categoria(iin):
    """«costo_de_los_lotes» o «gasto» según la categoría (la decide la categoría, no quien registra)."""
    if iin.insumo.tipo_insumo.consumo_directo == TipoInsumo.ConsumoDirecto.COMO_COSTO_DE_LOS_LOTES:
        return COSTO_DE_LOS_LOTES
    return GASTO


# ---- Verificaciones ----


def _sectores_del_alcance(invernadero, datos):
    """Paso 5 y extensiones 4a y 6a: `(sectores de la bitácora, ids de los sectores del alcance)`. «todo»: sin sectores en la bitácora y todos los
    activos como alcance. «sectores»: los elegidos, que deben ser activos del invernadero (`sector_no_elegible`); ninguno es `sin_sectores`."""
    activos = {
        s.pk: s
        for s in SectorProduccion.objects.filter(invernadero=invernadero, estado_sector=SectorProduccion.Estado.ACTIVO).order_by("pk")
    }
    if datos.alcance == "todo":
        return [], sorted(activos)
    if datos.alcance != "sectores" or not datos.sector_ids:
        raise _error("sin_sectores", "Marcá al menos un sector, o indicá que fue en todo el invernadero.", "sector_ids")
    elegidos = sorted(set(datos.sector_ids))
    if any(s not in activos for s in elegidos):
        raise _error("sector_no_elegible", "Un sector fuera de servicio, dado de baja o de otro invernadero no se puede elegir.", "sector_ids")
    return [activos[s] for s in elegidos], elegidos


def _cantidad(linea, iin):
    """Extensión 8a: la cantidad es un número mayor que cero con los decimales de la unidad (`cantidad_invalida`, con lo que admite)."""
    campo = f"cantidad_{iin.pk}"
    try:
        cantidad = validar_cantidad(linea.cantidad, iin.insumo.unidad_medida_insumo)
    except ValidationError as error:
        raise _error("cantidad_invalida", " ".join(error.messages), campo) from error
    if cantidad <= 0:
        raise _error("cantidad_invalida", "La cantidad usada debe ser mayor que cero.", campo)
    return cantidad


def _exigir_lotes_vistos(iin, linea, vigentes):
    """Extensión 12a: los lotes de insumo que la persona vio ya no son los vigentes (cambió una cantidad disponible o apareció o se agotó un lote)."""
    if linea.lotes_vistos is None:
        return
    vistos = {lote_id: Decimal(str(disponible)) for lote_id, disponible in linea.lotes_vistos}
    actuales = {l.pk: l.cantidad_disponible for l in vigentes}
    if vistos != actuales:
        raise _error(
            "cambio_simultaneo",
            f"Mientras cargabas los datos cambió el stock de {iin.insumo.nombre_insumo}. Revisá las cantidades.",
            None,
            {"cambios": [f"Cambió el stock de {iin.insumo.nombre_insumo}."]},
        )


def _partes(iin, linea, cantidad, vigentes, hoy):
    """Reparto entre los lotes de insumo: `(partes, faltante)`. En un insumo que controla vencimiento y con `reparto`, el corregido (8c.2a y 10b); en los
    demás, FEFO (`stock.proponer_lotes_fefo`). `faltante` es lo que ningún lote cubre (extensión 8b): no se bloquea."""
    if not (iin.insumo.controla_vencimiento and linea.reparto is not None):
        propuesta = stock.proponer_lotes_fefo(iin.pk, cantidad, hoy)
        return [(lote_id, parte) for lote_id, parte in propuesta.partes], propuesta.resto
    campo = f"reparto_{iin.pk}"
    disponibles = {l.pk: l.cantidad_disponible for l in vigentes}
    partes, vistos, unidad = [], set(), iin.insumo.unidad_medida_insumo
    for lote_id, texto in linea.reparto:
        try:
            parte = validar_cantidad(texto, unidad)
        except ValidationError as error:
            raise _error("cantidad_invalida", " ".join(error.messages), campo) from error
        disponible = disponibles.get(lote_id, CERO)
        if lote_id in vistos or parte < 0 or parte > disponible:
            raise _error(
                "reparto_supera_lote",
                f"Ese lote tiene {_texto(disponible)} disponible: la cantidad tiene que estar entre 0 y esa.",
                campo,
                {"lote_id": lote_id, "disponible": disponible},
            )
        vistos.add(lote_id)
        if parte > 0:
            partes.append((lote_id, parte))
    esperado = min(cantidad, sum(disponibles.values(), CERO))
    total = sum((p for _, p in partes), CERO)
    if total != esperado:
        raise _error(
            "distribucion_incompleta",
            f"El reparto de {iin.insumo.nombre_insumo} suma {_texto(total)} y debería sumar {_texto(esperado)}.",
            campo,
            {"debe_sumar": esperado},
        )
    return partes, cantidad - total


def _plantas_por_lote(sector_ids):
    """`{lote_id: plantas}`: las plantas de cada lote ACTIVO en los sectores del alcance (la suma de sus agujeros ocupados ahí)."""
    filas = (
        OcupacionSector.objects.filter(
            sector_id__in=sector_ids, lote__isnull=False, lote__estado_lote=Lote.Estado.ACTIVO, cant_agujeros_ocupados__gt=0
        )
        .values("lote_id")
        .annotate(total=Sum("cant_agujeros_ocupados"))
    )
    return {f["lote_id"]: f["total"] for f in filas}


def _reparto(iin, valor, plantas_por_lote, lotes):
    """`(destino, filas del reparto, partes por lote, aviso)` de un consumo: «como costo de los lotes» se reparte en centavos entre los lotes con plantas
    en el alcance (`costos.repartir_en_centavos`); sin lotes, o «como gasto», va a gasto sin imputaciones (extensión 10c: solo ahí hay aviso)."""
    if _destino_de_la_categoria(iin) != COSTO_DE_LOS_LOTES:
        return GASTO, [], {}, None
    if not plantas_por_lote:
        aviso = f"El costo de {iin.insumo.nombre_insumo} va a gasto porque no hay lotes de plantas en el alcance entre los que repartirlo."
        return GASTO, [], {}, aviso
    partes = costos.repartir_en_centavos(valor, plantas_por_lote)
    total = sum(plantas_por_lote.values())
    filas = []
    for lote_id in sorted(partes):
        lote = lotes[lote_id]
        antes = costos.costo_por_planta(lote)
        despues = costos.redondear_monto((Decimal(lote.costo_acumulado) + partes[lote_id]) / lote.cantidad_actual)
        porcentaje = (Decimal(plantas_por_lote[lote_id]) * 100 / total).quantize(Decimal("0.01"))
        filas.append(FilaDeReparto(lote_id, lote.codigo, plantas_por_lote[lote_id], porcentaje, partes[lote_id], antes, despues))
    return COSTO_DE_LOS_LOTES, filas, partes, None


def _planear(actor, datos):
    """Todas las verificaciones de los pasos 5 a 10 y de la extensión 12a con lo que haya en la base en este momento (registrar vuelve a llamarla
    después de bloquear). No escribe. Orden: permisos e invernadero, descripción, alcance, insumos, cantidades y reparto, lo visto (12a)."""
    invernadero = alcance.invernadero_del_actor(actor, datos.invernadero_id)
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    sectores, alcance_ids = _sectores_del_alcance(invernadero, datos)
    if not datos.lineas:
        raise _error("sin_insumos", "Indicá al menos un insumo.")
    aplicables = {i.pk: i for i in _aplicables(invernadero.pk)}
    hoy = stock.hoy()
    vigentes = _lotes_vigentes(set(aplicables), hoy)
    plantas_por_lote = _plantas_por_lote(alcance_ids)
    lotes = {l.pk: l for l in Lote.objects.filter(pk__in=list(plantas_por_lote))}
    if datos.plantas_vistas is not None and {l: p for l, p in datos.plantas_vistas} != plantas_por_lote:
        raise _error(
            "cambio_simultaneo",
            "Mientras cargabas los datos cambiaron las plantas de los lotes del alcance. Revisá el reparto.",
            None,
            {"cambios": ["Cambiaron las plantas de los lotes del alcance."]},
        )
    lineas, repetidos = [], set()
    for linea in datos.lineas:
        iin = aplicables.get(linea.existencia_id)
        campo = f"insumo_{linea.existencia_id}"
        if iin is None:
            if linea.lotes_vistos is not None:
                raise _error("cambio_simultaneo", "Cambió la habilitación o el estado de un insumo que habías elegido.", None, {"cambios": ["Un insumo ya no está habilitado."]})
            raise _error("insumo_no_aplicable", "Ese insumo no se ofrece en este invernadero.", campo)
        if iin.pk in repetidos:
            raise _error("insumo_repetido", f"{iin.insumo.nombre_insumo} ya está en la aplicación: cada insumo va una sola vez.", campo)
        repetidos.add(iin.pk)
        cantidad = _cantidad(linea, iin)
        _exigir_lotes_vistos(iin, linea, vigentes[iin.pk])
        partes, faltante = _partes(iin, linea, cantidad, vigentes[iin.pk], hoy)
        valor = costos.redondear_monto(cantidad * iin.referencia_precio)
        destino, filas, partes_de_costo, aviso = _reparto(iin, valor, plantas_por_lote, lotes)
        lineas.append(LineaPlan(iin, cantidad, partes, faltante, valor, destino, (filas, partes_de_costo), aviso))
    return PlanDeAplicacion(invernadero, sectores, alcance_ids, descripcion, lineas, plantas_por_lote, lotes)


def _lineas_publicas(plan, actor):
    """Las `LineaDeResumen` que se entregan: el Capataz ve insumos, cantidades y lotes de insumo; valor, destino, reparto, faltante y aviso, solo el Agrónomo."""
    ve_valores = not _es_capataz(actor)
    return [
        LineaDeResumen(
            l.existencia.pk,
            l.existencia.insumo_id,
            l.existencia.insumo.nombre_insumo,
            l.existencia.insumo.unidad_medida_insumo,
            l.cantidad,
            l.partes,
            l.faltante if ve_valores else None,
            l.valor if ve_valores else None,
            l.destino if ve_valores else None,
            l.reparto[0] if ve_valores else None,
            l.aviso if ve_valores else None,
        )
        for l in plan.lineas
    ]


def resumen_de_aplicacion(actor, datos):
    """Paso 10: valida todo como `registrar_aplicacion` (sin bloquear) y presenta cada insumo con sus lotes de origen y, al Agrónomo, el valor, el destino,
    el reparto entre los lotes de plantas y el monto que va a gasto. No escribe."""
    alcance.exigir_actor(actor)
    plan = _planear(actor, datos)
    lineas = _lineas_publicas(plan, actor)
    total = None if _es_capataz(actor) else sum((l.valor for l in lineas if l.destino == GASTO), Decimal("0.00"))
    return ResumenDeAplicacion(plan.invernadero, plan.sectores, plan.descripcion, lineas, total)


# ---- Escritura ----


def registrar_aplicacion(actor, datos):
    """PROD-REG-APL: registra una aplicación de insumos y devuelve `ResultadoDeAplicacion(aplicacion, lineas)` (las líneas, con la regla de roles).

    - Quién: Agrónomo a cargo o Capataz asignado, con la cuenta activa (`sin_permiso`); invernadero activo (`invernadero_inactivo`).
    - Bloqueos (docs/patrones/bloqueos.md y stock.md, sección 5), todos `FOR NO KEY UPDATE` y por id: las cuentas del actor y del Agrónomo → el
      invernadero → los sectores del alcance → `TipoInsumo` → `Insumo` → `InsumoInvernadero` → `LoteInsumo` (el faltante incluido) → los lotes de plantas
      del alcance. Las verificaciones se repiten DESPUÉS de bloquear, con lo bloqueado (extensión 12a: `cambio_simultaneo`).
    - Postcondiciones a a e y g a i: la bitácora, un `Consumo` por insumo (creado ANTES de su salida de stock, D-52), la salida por lote con su faltante sin
      lote (extensión 8b), las imputaciones (solo «como costo de los lotes» con lotes en el alcance) que suben `Lote.costo_acumulado`, las alertas de stock y UN
      registro `registro_aplicacion`. No cambia plantas, etapa ni ocupaciones. Todo o nada (D-22).
    """
    alcance.exigir_actor(actor)
    invernadero = alcance.invernadero_del_actor(actor, datos.invernadero_id)
    # Lo que dice qué bloquear se lee sin bloquear y se relee después.
    if datos.alcance == "sectores":
        sector_ids = sorted(set(datos.sector_ids))
    else:
        sector_ids = sorted(SectorProduccion.objects.filter(invernadero=invernadero, estado_sector="activo").values_list("pk", flat=True))
    iins = list(
        InsumoInvernadero.objects.filter(pk__in={l.existencia_id for l in datos.lineas}, invernadero=invernadero).select_related("insumo")
    )
    insumo_ids = sorted({i.insumo_id for i in iins})
    tipo_ids = sorted({i.insumo.tipo_insumo_id for i in iins})
    iin_ids = sorted(i.pk for i in iins)
    with transaction.atomic():
        cuentas = {actor.pk, *([invernadero.agronomo_id] if invernadero.agronomo_id else [])}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        alcance.exigir_actor(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(bloquear_invernadero_activo, invernadero.pk, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)})
        if sector_ids:
            equivalencia = ("sector_no_elegible", "sector_ids") if datos.alcance == "sectores" else ("cambio_simultaneo", None)
            _bloquear(api_sectores.bloquear_sectores, invernadero.pk, sector_ids, equivalencias={"sector_no_disponible": equivalencia})
        list(TipoInsumo.objects.select_for_update(no_key=True).filter(pk__in=tipo_ids).order_by("pk"))
        list(Insumo.objects.select_for_update(no_key=True).filter(pk__in=insumo_ids).order_by("pk"))
        list(InsumoInvernadero.objects.select_for_update(no_key=True).filter(pk__in=iin_ids).order_by("pk"))
        list(LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero_id__in=iin_ids).order_by("insumo_invernadero_id", "pk"))
        lote_ids = sorted(_plantas_por_lote(sector_ids))
        list(Lote.objects.select_for_update(no_key=True).filter(pk__in=lote_ids).order_by("pk"))
        plan = _planear(actor, datos)  # 12a y todas las verificaciones, con lo bloqueado
        if set(plan.alcance_ids) - set(sector_ids) or set(plan.plantas_por_lote) - set(lote_ids):
            raise _error("cambio_simultaneo", "Mientras cargabas los datos cambiaron los sectores del alcance. Volvé a cargar la aplicación.", None, {"cambios": ["Cambiaron los sectores."]})
        return _escribir(actor, plan, iin_ids)


def _descripcion_legible(plan):
    """D-51 punto 8: «Aplicación de insumos: Limpiador (5 L), Guantes (2 unidades)», hasta 500 caracteres."""
    lista = ", ".join(f"{l.existencia.insumo.nombre_insumo} ({_texto(l.cantidad)} {Unidad(l.existencia.insumo.unidad_medida_insumo).label})" for l in plan.lineas)
    texto = f"Aplicación de insumos: {lista}"
    return texto if len(texto) <= 500 else texto[:499] + "…"


def _escribir(actor, plan, iin_ids):
    """Pasos 12 y 13: escribe en el orden del caso de uso y registra la auditoría única."""
    hoy, hora = stock.hoy(), timezone.localtime().time()
    disponible_antes = {l.pk: l.cantidad_disponible for l in LoteInsumo.objects.filter(insumo_invernadero_id__in=iin_ids)}
    costo_antes = {pk: Decimal(l.costo_acumulado) for pk, l in plan.lotes.items()}
    ultima_alerta = Alerta.objects.aggregate(m=Max("pk"))["m"] or 0
    aplicacion = AplicacionInsumos.objects.create(
        invernadero=plan.invernadero,
        tipo_evento=Bitacora.TipoEvento.APLICACION,
        fecha_bitacora=hoy,
        hora_bitacora=hora,
        responsable=actor,
        descripcion_evento=plan.descripcion or _descripcion_legible(plan),
    )
    if plan.sectores:
        aplicacion.sectores.set([s.pk for s in plan.sectores])
    consumos, movimientos, imputaciones = [], [], []
    for linea in plan.lineas:
        iin = linea.existencia
        unidad = Unidad(iin.insumo.unidad_medida_insumo).label
        consumo = Consumo.objects.create(  # ANTES que su salida de stock: el movimiento lleva `origen` = el consumo (D-52)
            invernadero=plan.invernadero,
            tipo_evento=Bitacora.TipoEvento.CONSUMO,
            fecha_bitacora=hoy,
            hora_bitacora=hora,
            responsable=actor,
            descripcion_evento=f"Aplicación: {iin.insumo.nombre_insumo}, {_texto(linea.cantidad)} {unidad}"[:500],
            monto_consumo=linea.valor,
            cant_consumo=linea.cantidad,
            fecha_consumo=hoy,
            insumo_invernadero=iin,
            aplicacion=aplicacion,
        )
        consumos.append(consumo)
        movimientos += stock.registrar_salida_por_consumo(iin.pk, _partes_de_salida(iin, linea.partes, linea.faltante), origen_id=consumo.pk)
        for lote_id, parte in sorted(linea.reparto[1].items()):
            if parte > 0:  # un lote que recibe cero no tiene imputación
                imputaciones.append(ImputacionCosto.objects.create(consumo=consumo, lote_id=lote_id, monto_imputado=parte))
                lote = plan.lotes[lote_id]
                lote.costo_acumulado = costos.redondear_monto(Decimal(lote.costo_acumulado) + parte)
    lotes_con_costo = [plan.lotes[pk] for pk in sorted(plan.lotes) if plan.lotes[pk].costo_acumulado != costo_antes[pk]]
    for lote in lotes_con_costo:
        Lote.objects.filter(pk=lote.pk).update(costo_acumulado=lote.costo_acumulado)
    claves = [f"insumo:{i}" for i in iin_ids]
    alertas = list(
        Alerta.objects.filter(
            pk__gt=ultima_alerta,
            invernadero_id=plan.invernadero.pk,
            clave_estado__in=claves,
            tipo_alerta__in=[alertas_de_inventario.STOCK_INCONSISTENTE, alertas_de_inventario.INSUMO_BAJO_MINIMO],
        ).order_by("pk")
    )
    lotes_de_insumo = [l for l in LoteInsumo.objects.filter(insumo_invernadero_id__in=iin_ids).order_by("pk") if disponible_antes.get(l.pk, CERO) != l.cantidad_disponible]
    cambios = {
        "lotes_de_insumo": {
            "antes": [f"Lote #{l.pk}: {_texto(disponible_antes.get(l.pk, CERO))}" for l in lotes_de_insumo],
            "despues": [f"Lote #{l.pk}: {_texto(l.cantidad_disponible)}" for l in lotes_de_insumo],
        }
    }
    if lotes_con_costo:
        cambios["costo_acumulado"] = {
            "antes": [f"{l.codigo}: {costo_antes[l.pk]}" for l in lotes_con_costo],
            "despues": [f"{l.codigo}: {l.costo_acumulado}" for l in lotes_con_costo],
        }
    datos_de_auditoria = {
        "invernadero": referencia(plan.invernadero),
        "aplicacion": referencia(aplicacion),
        "alcance": ", ".join(s.nombre_sector for s in plan.sectores) or "Todo el invernadero",
        "consumos": [referencia(c) for c in consumos],
    }
    if alertas:
        datos_de_auditoria["alertas_creadas"] = [referencia(a) for a in alertas]
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.REGISTRO_APLICACION,
        afectados=[aplicacion, *consumos, *movimientos, *imputaciones, *lotes_de_insumo, *lotes_con_costo, *alertas],
        detalle={"cambios": cambios, "datos": datos_de_auditoria},
    )
    return ResultadoDeAplicacion(aplicacion, _lineas_publicas(plan, actor))


def plantas_del_alcance(actor, datos):
    """Las plantas de cada lote del alcance elegido como `((lote_id, plantas), ...)`, por lote: es lo que la pantalla guarda como `plantas_vistas` para
    la extensión 12a. No escribe ni bloquea; son cantidades de plantas (sin valores en dinero), que el Capataz también conoce de la merma."""
    alcance.exigir_actor(actor)
    invernadero = alcance.invernadero_del_actor(actor, datos.invernadero_id)
    _, ids = _sectores_del_alcance(invernadero, datos)
    return tuple(sorted(_plantas_por_lote(ids).items()))
