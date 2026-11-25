# PROD-PNR-FDS · Poner Sector Fuera de Servicio (PRD-04). Un caso de uso = una función pública dentro de `transaction.atomic()`; los
# helpers llevan guion bajo (D-37). Esta primera parte es la LECTURA (paso 3): lo que presentan los pasos 2, 4 y 6 del caso de uso
# y la fecha mínima de la regla «Fecha mínima». No escribe ni bloquea. La escritura (`poner_fuera_de_servicio`) está más abajo.
# Fuente: docs/casos_de_uso/produccion/sector_fuera_de_servicio.md (reglas y «Cómo se aplica en la ronda «Producción 1»»), D-51 y
# docs/patrones/bloqueos.md («Lote 5»). Quién lo ejecuta: solo el Agrónomo a cargo del invernadero del sector (regla «Quién lo ejecuta»).

from collections import defaultdict, namedtuple
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


from django.db import transaction
from django.db.models import Max, Q
from django.db.models.functions import Coalesce, Lower
from django.http import Http404
from django.utils import timezone

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import Insumo, InsumoInvernadero
from inventario.servicios import variedades
from maestros.extensiones import Aviso
from maestros.models import SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import (
    Bitacora,
    FueraDeServicio,
    Lote,
    Merma,
    OcupacionSector,
    OrdenTrabajo,
    Reubicacion,
    ReservaInsumo,
    Siembra,
    TransicionEtapa,
)
from produccion.servicios import alcance, asientos_de_produccion, costos, mermas
from produccion.servicios import lotes as api_lotes
from produccion.servicios import ordenes as api_ordenes
from produccion.servicios.bloqueos import traducir as _bloquear

Estado = OrdenTrabajo.Estado
Tipo = OrdenTrabajo.Tipo

# Paso 2: los invernaderos activos a cargo del Agrónomo con sus sectores activos, agrupados por tipo de etapa.
InvernaderoConSectores = namedtuple("InvernaderoConSectores", "invernadero grupos")
GrupoDeSectoresActivos = namedtuple("GrupoDeSectoresActivos", "tipo_etapa sectores")
# Paso 4: un lote que ocupa el sector (`plantas` son las que tiene EN el sector) y una orden «a realizar» con agujeros comprometidos en él.
LoteEnElSector = namedtuple("LoteEnElSector", "lote variedad perfil plantas costo_por_planta")
OrdenAfectada = namedtuple("OrdenAfectada", "orden tipo detalle agujeros fecha_programada")
# La fecha mínima y de dónde sale (extensión 6c). `fecha` es `None` si nada la determina.
FechaMinima = namedtuple("FechaMinima", "fecha origen")
DetalleDeSector = namedtuple(
    "DetalleDeSector", "sector invernadero lotes ordenes fecha_propuesta fecha_minima avisos sin_plantas sin_ordenes"
)
# Un sector de destino elegible: sus agujeros libres y su perfil familiar (`None` = sin plantas, acepta cualquiera).
Destino = namedtuple("Destino", "sector libres perfil")

CLAVE_DE_SECTOR_EN_AUDITORIA = "maestros.sectorproduccion"


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


def _exigir_agronomo(actor):
    """Solo el Agrónomo con la cuenta activa (el Capataz y el Gerente no): si no, `sin_permiso`."""
    alcance.exigir_actor(actor)
    if rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise _error("sin_permiso", "Solo el Agrónomo a cargo del invernadero puede poner un sector fuera de servicio.")


def sector_del_agronomo(actor, sector_id):
    """El sector (con su invernadero y su tipo de etapa) para operar: `sin_permiso` si no es el Agrónomo a cargo, `Http404` si no
    existe, `invernadero_inactivo` si el invernadero está dado de baja y `sector_no_activo` si el sector no está «activo» (regla
    «Sector que se puede poner fuera de servicio»)."""
    _exigir_agronomo(actor)
    sector = SectorProduccion.objects.select_related("invernadero", "tipo_etapa").filter(pk=sector_id).first()
    if sector is None:
        raise Http404("No existe ese sector.")
    alcance.exigir_en_alcance(actor, sector.invernadero)
    if sector.estado_sector != SectorProduccion.Estado.ACTIVO:
        raise _error("sector_no_activo", f"El sector {sector.nombre_sector} no está activo: solo se puede poner fuera de servicio un sector activo.", "sector")
    return sector


def sectores_para_fuera_de_servicio(actor):
    """Paso 2: `[InvernaderoConSectores]` con los invernaderos activos a cargo del Agrónomo que tienen al menos un sector activo y, por
    cada uno, sus sectores activos agrupados por tipo de etapa (en el orden de las etapas, después por nombre). Lista vacía = no hay nada
    que poner fuera de servicio (precondición b): la pantalla queda deshabilitada con su motivo. Dos consultas."""
    _exigir_agronomo(actor)
    invernaderos = alcance.invernaderos_del_actor(actor)
    if not invernaderos:
        return []
    sectores = (
        SectorProduccion.objects.filter(invernadero__in=invernaderos, estado_sector=SectorProduccion.Estado.ACTIVO)
        .select_related("tipo_etapa")
        .order_by("tipo_etapa__puesto_global", Lower("nombre_sector"), "pk")
    )
    por_invernadero = defaultdict(lambda: defaultdict(list))
    for sector in sectores:
        por_invernadero[sector.invernadero_id][sector.tipo_etapa].append(sector)
    return [
        InvernaderoConSectores(inv, [GrupoDeSectoresActivos(tipo, lista) for tipo, lista in por_invernadero[inv.pk].items()])
        for inv in invernaderos
        if inv.pk in por_invernadero
    ]


def _lotes_del_sector(sector):
    """`[LoteEnElSector]`: los lotes con plantas en el sector (suma de sus ocupaciones vigentes ahí), por id."""
    ocupaciones = (
        OcupacionSector.objects.filter(sector=sector, cant_agujeros_ocupados__gt=0, lote__isnull=False)
        .select_related("lote__siembra__variedad__cultivo")
        .order_by("lote_id", "pk")
    )
    plantas, lotes = defaultdict(int), {}
    for o in ocupaciones:
        plantas[o.lote_id] += o.cant_agujeros_ocupados
        lotes[o.lote_id] = o.lote
    return [
        LoteEnElSector(
            lote, lote.siembra.variedad, lote.siembra.variedad.perfil_familia, plantas[lote_id], costos.costo_por_planta(lote)
        )
        for lote_id, lote in sorted(lotes.items())
    ]


def ordenes_afectadas(sector):
    """`[OrdenAfectada]`: las órdenes de siembra o transición «a realizar» con agujeros comprometidos en el sector (paso 4, regla
    «Órdenes afectadas»), por fecha programada y id. `detalle` es la variedad (siembra) o el lote (transición). Tres consultas."""
    ocupaciones = list(
        OcupacionSector.objects.filter(sector=sector, orden__estado_orden=Estado.A_REALIZAR)
        .select_related("orden")
        .order_by("orden__fecha_programada_orden", "orden_id")
    )
    ids = [o.orden_id for o in ocupaciones]
    variedades = {s.pk: str(s.variedad) for s in Siembra.objects.filter(pk__in=ids).select_related("variedad__cultivo")}
    lotes = {t.pk: t.lote.codigo for t in TransicionEtapa.objects.filter(pk__in=ids).select_related("lote")}
    return [
        OrdenAfectada(
            o.orden,
            Tipo(o.orden.tipo_orden).label,
            variedades.get(o.orden_id) or f"lote {lotes.get(o.orden_id, '')}".strip(),
            o.cant_agujeros_planificados,
            o.orden.fecha_programada_orden,
        )
        for o in ocupaciones
    ]


def _avisos_del_ultimo_sector(sector):
    """Extensión 4a: si es el último sector activo de su tipo de etapa en el invernadero, el encabezado y lo que queda sin esa etapa
    (reutiliza `avisos_de_cambio_de_tipo` de PROD-MOD-SCT: lotes que todavía deben pasar por ella, siembras a realizar y variedades que
    dejan de poder sembrarse). No bloquea. Lista vacía si hay otro sector activo del tipo."""
    hay_otro = (
        SectorProduccion.objects.filter(
            invernadero_id=sector.invernadero_id, tipo_etapa_id=sector.tipo_etapa_id, estado_sector=SectorProduccion.Estado.ACTIVO
        )
        .exclude(pk=sector.pk)
        .exists()
    )
    if hay_otro:
        return []
    encabezado = Aviso(
        f"El invernadero {sector.invernadero.nombre_invernadero} se queda sin sectores activos de {sector.tipo_etapa.nombre_etapa}. "
        "Se recomienda registrar otro sector de esa etapa o cambiar el tipo de uno existente. No bloquea la operación.",
        None,
    )
    return [encabezado, *api_sectores.avisos_de_cambio_de_tipo(sector.invernadero, sector.tipo_etapa)]


def fecha_minima_fuera_de_servicio(sector):
    """Regla «Fecha mínima» y extensión 6c: `FechaMinima(fecha, origen)`, la más tardía entre (a) la última activación del sector
    (`SectorProduccion` no la guarda: se deriva de la fecha del último registro de auditoría `alta_sector` o `reactivacion_sector` que
    lo nombra y del `fecha_fin` del último registro «Fuera de servicio», D-51 punto 6), (b) la fecha en que llegó al sector cada lote que
    lo ocupa (la siembra, la transición o la reubicación de su ocupación vigente) y (c) el último registro de bitácora de esos lotes.
    `origen` es el texto que explica de dónde sale; si nada la determina, `FechaMinima(None, "")`. Cuatro consultas fijas."""
    candidatos = []  # (fecha, texto), en el orden de la regla: gana el primero entre iguales

    registro = (
        RegistroAuditoria.objects.filter(
            accion__in=[RegistroAuditoria.Accion.ALTA_SECTOR, RegistroAuditoria.Accion.REACTIVACION_SECTOR],
            afectados__contains=[{"modelo": CLAVE_DE_SECTOR_EN_AUDITORIA, "id": sector.pk}],
        )
        .order_by("-fecha_hora", "-id")
        .first()
    )
    if registro is not None:
        candidatos.append((timezone.localtime(registro.fecha_hora).date(), "la última activación del sector"))
    ultima_vuelta = FueraDeServicio.objects.filter(sector=sector, fecha_fin__isnull=False).aggregate(fecha=Max("fecha_fin"))["fecha"]
    if ultima_vuelta is not None:
        candidatos.append((ultima_vuelta, "la última vez que el sector volvió a servicio"))

    llegadas = (
        OcupacionSector.objects.filter(sector=sector, cant_agujeros_ocupados__gt=0, lote__isnull=False)
        .annotate(
            llegada=Coalesce("orden__siembra__fecha_siembra", "orden__transicionetapa__fecha_transicion", "reubicacion__fecha_bitacora")
        )
        .values_list("lote_id", "llegada")
        .order_by("lote_id", "pk")
    )
    lotes_del_sector = {}
    for lote_id, llegada in llegadas:
        lotes_del_sector[lote_id] = max(filter(None, [lotes_del_sector.get(lote_id), llegada]), default=None)
    codigos = {pk: f"L-{pk}" for pk in lotes_del_sector}
    for lote_id, llegada in lotes_del_sector.items():
        if llegada is not None:
            candidatos.append((llegada, f"la llegada del lote {codigos[lote_id]} al sector"))
    if lotes_del_sector:
        ultimos = (
            Bitacora.objects.filter(lote_id__in=list(lotes_del_sector)).values("lote_id").annotate(ultima=Max("fecha_bitacora")).order_by("lote_id")
        )
        for fila in ultimos:
            candidatos.append((fila["ultima"], f"el último registro de bitácora del lote {codigos[fila['lote_id']]}"))

    if not candidatos:
        return FechaMinima(None, "")
    fecha, texto = candidatos[0]
    for otra, otro_texto in candidatos[1:]:
        if otra > fecha:
            fecha, texto = otra, otro_texto
    return FechaMinima(fecha, f"{texto} ({fecha:%d/%m/%Y})")


def detalle_de_sector(actor, sector_id):
    """Pasos 3 y 4: el detalle del sector que elige el Agrónomo: su invernadero y tipo de etapa, los lotes que lo ocupan con las plantas
    de cada uno en él, las órdenes «a realizar» con agujeros comprometidos en él, la fecha actual como fecha propuesta, la fecha mínima y
    sus avisos (extensión 4a). `sin_plantas` (extensión 6d) y `sin_ordenes` son banderas para la pantalla. No escribe."""
    sector = sector_del_agronomo(actor, sector_id)
    lotes = _lotes_del_sector(sector)
    ordenes = ordenes_afectadas(sector)
    return DetalleDeSector(
        sector,
        sector.invernadero,
        lotes,
        ordenes,
        timezone.localdate(),
        fecha_minima_fuera_de_servicio(sector),
        _avisos_del_ultimo_sector(sector),
        not lotes,
        not ordenes,
    )


def _destinos_posibles(sector, lotes):
    """`{lote_id: [Destino]}` con los sectores del mismo invernadero y tipo de etapa, activos, distintos del origen y de perfil compatible,
    CON O SIN agujeros libres (la verificación de la cantidad distingue «no elegible» de «sin lugar», extensiones 8b y 6e)."""
    lotes = [getattr(l, "lote", l) for l in lotes]
    candidatos = list(
        SectorProduccion.objects.filter(
            invernadero_id=sector.invernadero_id, tipo_etapa_id=sector.tipo_etapa_id, estado_sector=SectorProduccion.Estado.ACTIVO
        )
        .exclude(pk=sector.pk)
        .order_by(Lower("nombre_sector"), "pk")
    )
    if not candidatos:
        return {lote.pk: [] for lote in lotes}
    agujeros = api_sectores.agujeros_de(candidatos)
    perfiles = api_lotes.perfil_de_sector([s.pk for s in candidatos])
    return {
        lote.pk: [
            Destino(s, agujeros[s.pk].libres, perfiles[s.pk])
            for s in candidatos
            if perfiles[s.pk] in (None, lote.siembra.variedad.perfil_familia)
        ]
        for lote in lotes
    }


def destinos_elegibles(sector, lotes):
    """Regla «Sector de destino elegible»: `{lote_id: [Destino]}` con los sectores del MISMO invernadero y del MISMO tipo de etapa que
    `sector`, «activos», distintos del origen, con perfil familiar compatible con el del lote (el de su variedad, o sin plantas ni
    órdenes) y con agujeros libres (`agujeros_de`: total − ocupados − comprometidos). Conservador a propósito: los comprometidos por las
    órdenes que esta misma operación cancela NO se cuentan como libres, para no depender del orden en que se apliquen. Un lote sin
    destinos devuelve lista vacía (extensión 6e). `lotes` son `Lote` (con `siembra__variedad` cargada) o `LoteEnElSector`. Tres consultas."""
    posibles = _destinos_posibles(sector, lotes)
    return {lote_id: [d for d in lista if d.libres > 0] for lote_id, lista in posibles.items()}


# ---- Verificación (pasos 5 a 12), resumen y escritura (paso 14) ----
# Orden de bloqueos (docs/patrones/bloqueos.md, «Lote 5»; todos `FOR NO KEY UPDATE`): cuentas (el actor, el Agrónomo y el Capataz que se
# notifica, por id) → invernadero → variedades de los lotes y órdenes afectados (id) → sectores (el de origen, los destinos pedidos y los de
# las órdenes a cancelar, por id y sin repetir; el de origen se bloquea ANTES de pasarlo a «fuera de servicio») → insumos de las reservas
# (`Insumo` y después `InsumoInvernadero`, id) → lotes (id) → órdenes, ocupaciones y reservas. Con el invernadero tomado nadie más cambia lo
# que hay en el sector (todo el que lo hace toma antes el invernadero): por eso lo que se bloquea se decide DESPUÉS de tomarlo, y la
# extensión 14a se evalúa DESPUÉS de todos los bloqueos.

LARGO_DEL_MOTIVO = 300
LARGO_DE_LA_DESCRIPCION = 300
LARGO_DE_LA_BITACORA = 500


@dataclass(frozen=True)
class DatosDeFueraDeServicio:
    """Lo que la persona carga (pasos 5, 7 y 9) y lo que VIO (extensión 14a).

    - `reubicaciones`: `((lote_id, sector_destino_id, plantas), ...)`; lo que no figura vale cero. `causas`: `((lote_id, causa, descripcion), ...)`,
      una por cada lote con plantas sin reubicar.
    - `plantas_vistas` (`((lote_id, plantas_en_el_sector), ...)`), `libres_vistos` (`((sector_destino_id, libres), ...)`) y `ordenes_vistas`
      (`(orden_id, ...)`) son lo que la pantalla mostró. Si ya no es lo vigente, `cambio_simultaneo` con lo vigente en `datos`. `None` (una
      llamada programática) no lo verifica y se opera sobre lo vigente ya bloqueado; informado, incluso vacío, cualquier diferencia lo dispara."""

    sector_id: int
    motivo: str = ""
    fecha: date | None = None
    reubicaciones: tuple = ()
    causas: tuple = ()
    plantas_vistas: tuple | None = None
    libres_vistos: tuple | None = None
    ordenes_vistas: tuple | None = None


# `reubicaciones` es `[(sector, plantas)]` (solo las mayores que cero); `valor_de_la_merma` es el de las plantas sin reubicar (paso 12).
LoteDelResumen = namedtuple(
    "LoteDelResumen", "lote variedad plantas reubicaciones reubicadas sin_reubicar causa descripcion valor_de_la_merma"
)
ResumenDeFueraDeServicio = namedtuple(
    "ResumenDeFueraDeServicio",
    "sector invernadero motivo fecha lotes ordenes avisos fecha_minima total_reubicado total_de_la_merma valor_total_de_la_merma hay_capataz",
)


def _entero(valor):
    """True si `valor` es un entero (no un booleano) mayor o igual que cero."""
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _exigir_lo_visto(datos, lotes, ordenes, destinos_libres):
    """Extensión 14a: lo que la persona vio ya no es lo vigente → `cambio_simultaneo` con lo vigente en `datos` (`plantas`, `ordenes`,
    `libres`). `destinos_libres` es `{sector_id: libres}` de los destinos que la persona vio (`None` si el sector ya no existe)."""
    plantas = {l.lote.pk: l.plantas for l in lotes}
    ids_de_ordenes = sorted(o.orden.pk for o in ordenes)
    cambio = datos.plantas_vistas is not None and {l: p for l, p in datos.plantas_vistas} != plantas
    cambio = cambio or (datos.ordenes_vistas is not None and sorted(datos.ordenes_vistas) != ids_de_ordenes)
    cambio = cambio or (
        datos.libres_vistos is not None and any(destinos_libres.get(s) != libres for s, libres in datos.libres_vistos)
    )
    if cambio:
        raise _error(
            "cambio_simultaneo",
            "Mientras cargabas los datos, otra operación cambió las plantas del sector, sus órdenes o los agujeros libres de un destino. "
            "Volvé a cargar los valores vigentes.",
            None,
            {"plantas": plantas, "ordenes": ids_de_ordenes, "libres": destinos_libres},
        )


def _libres_de(ids):
    """`{sector_id: agujeros libres o None}` de los sectores `ids` (`None` si no existe)."""
    sectores = list(SectorProduccion.objects.filter(pk__in=list(ids)))
    agujeros = api_sectores.agujeros_de(sectores)
    return {i: (agujeros[i].libres if i in agujeros else None) for i in ids}


def _planear(actor, datos):
    """Todas las verificaciones de los pasos 5 a 12 y de la extensión 14a con lo que haya en la base en este momento (`poner_fuera_de_servicio`
    vuelve a llamarla después de bloquear). No escribe. Orden: quién y qué sector, lo visto (14a), motivo (6a), fecha (6b, 6c), cantidades por
    lote y destino (8a, 8b, 8c y destino elegible) y causa de cada lote con plantas sin reubicar (12a)."""
    sector = sector_del_agronomo(actor, datos.sector_id)
    lotes, ordenes = _lotes_del_sector(sector), ordenes_afectadas(sector)
    posibles = _destinos_posibles(sector, lotes)
    libres_vistos = {s for s, _ in (datos.libres_vistos or ())}
    _exigir_lo_visto(datos, lotes, ordenes, _libres_de(libres_vistos) if libres_vistos else {})

    motivo = (datos.motivo or "").strip()
    if not motivo:
        raise _error("motivo_obligatorio", "Indicá el motivo.", "motivo")
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise _error("motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.", "motivo")
    fecha = datos.fecha
    if not isinstance(fecha, date):
        raise _error("fecha_invalida", "Indicá la fecha desde la que el sector está fuera de servicio.", "fecha")
    if fecha > timezone.localdate():
        raise _error("fecha_invalida", "La fecha no puede ser posterior a hoy.", "fecha")
    minima = fecha_minima_fuera_de_servicio(sector)
    if minima.fecha is not None and fecha < minima.fecha:
        raise _error(
            "fecha_invalida",
            f"La fecha no puede ser anterior al {minima.fecha:%d/%m/%Y}: es {minima.origen}.",
            "fecha",
            {"fecha_minima": minima.fecha, "origen": minima.origen},
        )

    plantas_de = {l.lote.pk: l.plantas for l in lotes}
    destinos_de = {lote_id: {d.sector.pk: d for d in lista} for lote_id, lista in posibles.items()}
    pedidas = {}  # lote_id -> {destino_id: plantas}
    asignado, por_lote = defaultdict(int), defaultdict(int)
    for lote_id, destino_id, cantidad in datos.reubicaciones:
        campo = f"reubicacion_{lote_id}_{destino_id}"
        if not _entero(cantidad):
            raise _error("cantidad_invalida", "La cantidad a reubicar debe ser un número entero, cero o mayor.", campo)
        if lote_id not in plantas_de:
            raise _error("cantidad_invalida", "Ese lote no tiene plantas en el sector.", campo, {"plantas": 0})
        destino = destinos_de[lote_id].get(destino_id)
        if destino is None:
            raise _error(
                "sector_no_elegible",
                "Ese sector no es un destino elegible: tiene que ser del mismo invernadero y tipo de etapa, estar activo y tener un perfil familiar compatible.",
                campo,
            )
        if cantidad == 0:
            continue
        libres = destino.libres - asignado[destino_id]
        if cantidad > libres:
            raise _error(
                "cantidad_invalida",
                f"{destino.sector.nombre_sector} tiene {max(libres, 0)} agujeros libres.",
                campo,
                {"libres": max(libres, 0)},
            )
        asignado[destino_id] += cantidad
        por_lote[lote_id] += cantidad
        if por_lote[lote_id] > plantas_de[lote_id]:
            raise _error(
                "cantidad_invalida",
                f"El lote tiene {plantas_de[lote_id]} plantas en el sector y reubicás {por_lote[lote_id]}.",
                campo,
                {"plantas": plantas_de[lote_id]},
            )
        pedidas.setdefault(lote_id, {})
        pedidas[lote_id][destino_id] = pedidas[lote_id].get(destino_id, 0) + cantidad

    causas = {lote_id: (causa, descripcion) for lote_id, causa, descripcion in datos.causas}
    filas = []
    for l in lotes:
        reubicaciones = [(destinos_de[l.lote.pk][d].sector, q) for d, q in pedidas.get(l.lote.pk, {}).items()]
        reubicadas = sum(q for _, q in reubicaciones)
        sin = l.plantas - reubicadas
        causa, descripcion, valor = "", "", Decimal("0.00")
        if sin > 0:
            campo = f"causa_{l.lote.pk}"
            causa, descripcion = causas.get(l.lote.pk, ("", ""))
            if not causa:
                raise _error("causa_obligatoria", f"Indicá la causa de la merma del lote {l.lote.codigo}.", campo)
            if causa not in Merma.CAUSAS_EN_PIE or causa == Merma.Causa.DESCARTE_POR_SELECCION:
                raise _error("causa_invalida", "Esa causa no corresponde a la merma de un lote en pie.", campo)
            descripcion = (descripcion or "").strip()
            if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
                raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.", campo)
            valor = costos.costo_de_la_merma(l.lote, sin)
        filas.append(LoteDelResumen(l.lote, l.variedad, l.plantas, reubicaciones, reubicadas, sin, causa, descripcion, valor))

    capataz = sector.invernadero.capataz
    return ResumenDeFueraDeServicio(
        sector,
        sector.invernadero,
        motivo,
        fecha,
        filas,
        ordenes,
        _avisos_del_ultimo_sector(sector),
        minima,
        sum(f.reubicadas for f in filas),
        sum(f.sin_reubicar for f in filas),
        sum((f.valor_de_la_merma for f in filas), Decimal("0.00")),
        capataz is not None and capataz.is_active,
    )


def resumen_de_fuera_de_servicio(actor, datos):
    """Paso 12: el resumen que se confirma (el sector, el motivo y la fecha; por lote, lo que se reubica y dónde, lo que se registra como
    merma con su causa y su valor; las órdenes que se cancelan; el aviso del último sector). Repite todas las verificaciones de los pasos 5 a
    12 y la 14a. NO escribe ni bloquea: `poner_fuera_de_servicio` las vuelve a hacer con todo bloqueado."""
    return _planear(actor, datos)


def _nombres(partes):
    """«A (5)», «A (5) y B (3)» o «A (5), B (3) y C (2)»: cada destino con las plantas que recibe."""
    nombres = [f"{s.nombre_sector} ({q})" for s, q in partes]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _bloquear_lo_que_toca(invernadero, sector, datos):
    """Después del invernadero: variedades, sectores, insumos, lotes, órdenes y ocupaciones, en ese orden y por id. Devuelve el sector de
    origen releído y bloqueado. Lo que se bloquea se lee sin bloquear (con el invernadero tomado no cambia) y se relee en `_planear`."""
    lotes, ordenes = _lotes_del_sector(sector), ordenes_afectadas(sector)
    orden_ids = [o.orden.pk for o in ordenes]
    lote_ids = {l.lote.pk for l in lotes} | set(TransicionEtapa.objects.filter(pk__in=orden_ids).values_list("lote_id", flat=True))
    variedad_ids = {l.variedad.pk for l in lotes}
    variedad_ids |= set(Siembra.objects.filter(pk__in=orden_ids).values_list("variedad_id", flat=True))
    variedad_ids |= set(TransicionEtapa.objects.filter(pk__in=orden_ids).values_list("lote__siembra__variedad_id", flat=True))
    for variedad_id in sorted(variedad_ids):
        _bloquear(variedades.bloquear_variedad, variedad_id)

    posibles = {d.sector.pk for lista in _destinos_posibles(sector, lotes).values() for d in lista}
    pedidos = {destino for _, destino, _ in datos.reubicaciones if isinstance(destino, int)} & posibles
    de_las_ordenes = set(OcupacionSector.objects.filter(orden_id__in=orden_ids).values_list("sector_id", flat=True))
    bloqueados = _bloquear(
        api_sectores.bloquear_sectores,
        invernadero.pk,
        {sector.pk} | pedidos | de_las_ordenes,
        equivalencias={"sector_no_disponible": ("cambio_simultaneo", None)},
    )

    existencia_ids = set(
        ReservaInsumo.objects.filter(orden_id__in=orden_ids, estado=ReservaInsumo.Estado.ACTIVA).values_list("insumo_invernadero_id", flat=True)
    )
    insumo_ids = set(InsumoInvernadero.objects.filter(pk__in=existencia_ids).values_list("insumo_id", flat=True))
    list(Insumo.objects.select_for_update(no_key=True).filter(pk__in=insumo_ids).order_by("pk"))
    list(InsumoInvernadero.objects.select_for_update(no_key=True).filter(pk__in=existencia_ids).order_by("pk"))

    list(Lote.objects.select_for_update(no_key=True).filter(pk__in=lote_ids).order_by("pk"))
    list(OrdenTrabajo.objects.select_for_update(no_key=True).filter(pk__in=orden_ids).order_by("pk"))
    list(
        OcupacionSector.objects.select_for_update(no_key=True)
        .filter(Q(sector=sector) | Q(lote_id__in=lote_ids) | Q(orden_id__in=orden_ids))
        .order_by("pk")
    )
    list(ReservaInsumo.objects.select_for_update(no_key=True).filter(orden_id__in=orden_ids).order_by("pk"))
    return next(s for s in bloqueados if s.pk == sector.pk)


def _texto_del_aviso(plan, canceladas):
    """`(título, detalle)` del aviso al Capataz (paso 15, regla «Notificación al Capataz»): el sector, la fecha efectiva, el motivo y las
    órdenes canceladas. El detalle no pasa de 500: si las órdenes no entran, se listan las primeras y «y N más»."""
    titulo = f"Sector {plan.sector.nombre_sector} fuera de servicio"
    base = f"Desde el {plan.fecha:%d/%m/%Y}. Motivo: {plan.motivo}."
    codigos = [o.codigo for o in canceladas]
    if not codigos:
        return titulo, base
    for cuantos in range(len(codigos), -1, -1):
        resto = len(codigos) - cuantos
        lista = ", ".join(codigos[:cuantos]) + (f"{' y ' if cuantos else ''}{resto} más" if resto else "")
        detalle = f"{base} Órdenes canceladas: {lista}."
        if len(detalle) <= 500:
            return titulo, detalle
    return titulo, base[:500]


def poner_fuera_de_servicio(actor, datos):
    """PROD-PNR-FDS: pone un sector «activo» fuera de servicio y devuelve el `FueraDeServicio`. Todo o nada (una sola transacción).

    - Quién: el Agrónomo activo a cargo del invernadero (`sin_permiso`); invernadero activo; sector «activo» (`sector_no_activo`).
    - Bloquea en el orden de `docs/patrones/bloqueos.md` y DESPUÉS verifica todo de nuevo con lo bloqueado, incluida la extensión 14a
      (`cambio_simultaneo` con lo vigente: `plantas`, `ordenes`, `libres`).
    - Orden de la escritura (paso 14): reubicaciones y sus ocupaciones (una `Reubicacion` por lote) → mermas con `aplicar_merma(...,
      sector_ids=[sector], ordenes_excluidas=<las que se cancelan>)`, sin `por_sector` → ocupación de origen en cero (conserva su lote) →
      cancelación de las órdenes con `cancelar_orden_incluida(..., avisar=False)` (motivo «Sector fuera de servicio: <sector>. <motivo>») →
      `pasar_a_fuera_de_servicio` → `FueraDeServicio` → UNA notificación al Capataz activo (si no hay, ninguna: extensión 15a) → UN registro
      de auditoría `fuera_de_servicio_sector` con todo lo tocado (D-36, D-51 punto 9).
    """
    previo = sector_del_agronomo(actor, datos.sector_id)
    invernadero = previo.invernadero
    with transaction.atomic():
        cuentas = {actor.pk} | {i for i in (invernadero.agronomo_id, invernadero.capataz_id) if i}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        _exigir_agronomo(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(
            bloquear_invernadero_activo, invernadero.pk, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)}
        )
        sector = sector_del_agronomo(actor, datos.sector_id)  # con el invernadero tomado: el estado vigente
        _bloquear_lo_que_toca(invernadero, sector, datos)
        plan = _planear(actor, datos)  # 14a y todas las verificaciones, con todo bloqueado
        return _escribir(actor, plan, datos)


def _escribir(actor, plan, datos):
    """Paso 14 (ver `poner_fuera_de_servicio`) y el único registro de auditoría."""
    sector, invernadero, fecha = plan.sector, plan.invernadero, plan.fecha
    hora = timezone.localtime().time()
    ordenes = [o.orden for o in plan.ordenes]
    sectores_de_las_ordenes = list(
        SectorProduccion.objects.filter(ocupaciones__orden_id__in=[o.pk for o in ordenes]).distinct().order_by("pk")
    )
    destinos = {s.pk: s for f in plan.lotes for s, _ in f.reubicaciones}
    con_ocupados = [sector, *sorted(destinos.values(), key=lambda s: s.pk)]
    con_comprometidos = [sector, *[s for s in sectores_de_las_ordenes if s.pk != sector.pk]]
    antes_ocupados = {pk: a.ocupados for pk, a in api_sectores.agujeros_de(con_ocupados).items()}
    antes_comprometidos = {pk: a.comprometidos for pk, a in api_sectores.agujeros_de(con_comprometidos).items()}
    lotes_antes = {f.lote.pk: (f.lote.cantidad_actual, Decimal(f.lote.costo_acumulado)) for f in plan.lotes}
    origen = list(OcupacionSector.objects.filter(sector=sector, cant_agujeros_ocupados__gt=0).order_by("pk"))
    origen_antes = {o.pk: o.cant_agujeros_ocupados for o in origen}

    # Paso 14.2: una reubicación por lote reubicado, con una ocupación nueva por destino.
    reubicaciones, ocupaciones_nuevas = [], []
    for f in plan.lotes:
        if not f.reubicadas:
            continue
        texto = (
            f"Reubicación de {mermas.plantas(f.reubicadas)} del lote {f.lote.codigo} desde {sector.nombre_sector} a "
            f"{_nombres(f.reubicaciones)}."
        )
        reubicacion = Reubicacion.objects.create(
            invernadero=invernadero, lote=f.lote, etapa=None, tipo_evento=Bitacora.TipoEvento.REUBICACION, fecha_bitacora=fecha,
            hora_bitacora=hora, responsable=actor, descripcion_evento=texto[:LARGO_DE_LA_BITACORA],
        )
        reubicacion.sectores.add(sector)
        reubicaciones.append(reubicacion)
        for destino, plantas in f.reubicaciones:
            ocupaciones_nuevas.append(
                OcupacionSector.objects.create(
                    reubicacion=reubicacion, sector=destino, lote=f.lote, cant_agujeros_planificados=plantas, cant_agujeros_ocupados=plantas
                )
            )

    # Paso 14.4: la merma de las plantas sin reubicar, en la etapa actual y asociada al sector; sin `por_sector` (los agujeros del origen los
    # deja en cero el paso siguiente) y sin contar como comprometidas las órdenes que se cancelan.
    resultados = [
        mermas.aplicar_merma(
            f.lote, f.sin_reubicar, f.causa, f.descripcion, fecha, actor, sector_ids=[sector.pk], ordenes_excluidas=[o.pk for o in ordenes]
        )
        for f in plan.lotes
        if f.sin_reubicar
    ]

    # Paso 14.3: la ocupación de origen en cero; conserva su lote.
    for ocupacion in origen:
        ocupacion.cant_agujeros_ocupados = 0
        ocupacion.save(update_fields=["cant_agujeros_ocupados"])

    # Paso 14.5: se cancelan todas las órdenes con agujeros comprometidos en el sector; el Capataz recibe UN aviso (no uno por orden).
    motivo_de_cancelacion = f"Sector fuera de servicio: {sector.nombre_sector}. {plan.motivo}"
    cancelaciones = [api_ordenes.cancelar_orden_incluida(actor, orden, motivo_de_cancelacion, avisar=False) for orden in ordenes]

    # Paso 14.1.
    api_sectores.pasar_a_fuera_de_servicio(sector)
    registro = FueraDeServicio.objects.create(
        invernadero=invernadero,
        tipo_evento=Bitacora.TipoEvento.FUERA_DE_SERVICIO,
        fecha_bitacora=fecha,
        hora_bitacora=hora,
        responsable=actor,
        descripcion_evento=f"El sector {sector.nombre_sector} quedó fuera de servicio desde el {fecha:%d/%m/%Y}. Motivo: {plan.motivo}"[:LARGO_DE_LA_BITACORA],
        motivo_fuera_de_servicio=plan.motivo,
        sector=sector,
    )
    registro.sectores.add(sector)

    # CON-04a (precondiciones c y d: se cumplen solas, D-92 punto 2; D-92 punto 9): un asiento por cada merma (Debe Pérdidas por Mermas / Haber Productos en
    # Proceso por su costo), con la fecha EFECTIVA del fuera de servicio. Va al final de los bloqueos: el ejercicio es lo último que se bloquea (D-86). La
    # reubicación y la cancelación de órdenes no asientan; una merma de costo $0 tampoco (H11).
    asientos_creados = asientos_de_produccion.referencias_de(
        [asientos_de_produccion.asentar_merma(actor, r.merma, r.costo, fecha, timezone.localdate()) for r in resultados]
    )

    # Paso 15 y extensión 15a: una sola notificación, solo si el invernadero tiene un Capataz activo.
    capataz = invernadero.capataz
    if capataz is not None and capataz.is_active:
        titulo, detalle = _texto_del_aviso(plan, ordenes)
        notificaciones.notificar(capataz, titulo, detalle)

    despues_ocupados = {pk: a.ocupados for pk, a in api_sectores.agujeros_de(con_ocupados).items()}
    despues_comprometidos = {pk: a.comprometidos for pk, a in api_sectores.agujeros_de(con_comprometidos).items()}
    alertas = [a for r in resultados for a in r.alertas]
    reservas = [r for c in cancelaciones for r in c.reservas]
    resueltas = [a for c in cancelaciones for a in c.alertas_resueltas]
    lotes = [f.lote for f in plan.lotes]
    cambios = {
        "estado": {"antes": "activo", "despues": "fuera_de_servicio"},
        "agujeros_ocupados": {
            "antes": [f"{s.nombre_sector}: {antes_ocupados[s.pk]}" for s in con_ocupados],
            "despues": [f"{s.nombre_sector}: {despues_ocupados[s.pk]}" for s in con_ocupados],
        },
        "agujeros_comprometidos": {
            "antes": [f"{s.nombre_sector}: {antes_comprometidos[s.pk]}" for s in con_comprometidos],
            "despues": [f"{s.nombre_sector}: {despues_comprometidos[s.pk]}" for s in con_comprometidos],
        },
    }
    if lotes:
        cambios["cantidad_actual"] = {
            "antes": [f"{l.codigo}: {lotes_antes[l.pk][0]}" for l in lotes],
            "despues": [f"{l.codigo}: {l.cantidad_actual}" for l in lotes],
        }
        cambios["costo_acumulado"] = {
            "antes": [f"{l.codigo}: {lotes_antes[l.pk][1]}" for l in lotes],
            "despues": [f"{l.codigo}: {l.costo_acumulado}" for l in lotes],
        }
    if origen:
        cambios["agujeros_ocupados_por_ocupacion"] = {
            "antes": [f"Ocupación #{o.pk}: {origen_antes[o.pk]}" for o in origen],
            "despues": [f"Ocupación #{o.pk}: 0" for o in origen],
        }
    # D-36: solo lo que cambió (un cambio con `antes` igual a `despues` se rechaza).
    cambios = {campo: v for campo, v in cambios.items() if v["antes"] != v["despues"]}
    datos_de_auditoria = {
        "invernadero": referencia(invernadero),
        "sector": referencia(sector),
        "registro_fuera_de_servicio": referencia(registro),
        "motivo": plan.motivo,
        "fecha_efectiva": str(fecha),
    }
    if reubicaciones:
        datos_de_auditoria["reubicaciones"] = [referencia(r) for r in reubicaciones]
    if resultados:
        datos_de_auditoria["mermas"] = [referencia(r.merma) for r in resultados]
        datos_de_auditoria["plantas_en_merma"] = str(sum(r.merma.cant_merma for r in resultados))
    if alertas:
        datos_de_auditoria["alertas_creadas"] = [referencia(a) for a in alertas]
    if ordenes:
        datos_de_auditoria["ordenes_canceladas"] = [referencia(o) for o in ordenes]
    if asientos_creados:
        datos_de_auditoria["asientos"] = [referencia(a) for a in asientos_creados]
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.FUERA_DE_SERVICIO_SECTOR,
        afectados=[
            sector, *destinos.values(), invernadero, registro, *reubicaciones, *ocupaciones_nuevas, *origen, *[r.merma for r in resultados],
            *alertas, *ordenes, *reservas, *resueltas, *lotes, *asientos_creados,
        ],
        detalle={"cambios": cambios, "datos": datos_de_auditoria},
    )
    return registro
