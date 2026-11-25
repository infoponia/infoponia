# Lectura de lotes de `produccion` (PRD-01): lotes activos, fechas de entrada y de fin de etapa, sectores de origen y perfil de un
# sector. Solo lee: no escribe ni bloquea. Los datos de más de un lote se piden con listas de ids y una consulta por tabla.
# Fuente: docs/api/produccion.md (sección 2) y docs/modelo/produccion.md («Lo que se calcula de un lote» y de las ocupaciones).
#
# PRD-05 (L3): sin transición concretada hacia la etapa actual, la entrada es la de la bitácora `carga_inicial` del lote.
#
# PRD-02 completa las fechas de las etapas que NO son la primera: salen de la transición concretada (`TransicionEtapa`, reglas 2 y 5
# de 8.21 y 8.20). Un lote sin esa transición (dato inconsistente) da `None`.

from collections import namedtuple
from datetime import timedelta

from django.db.models import Q
from django.db.models.functions import Coalesce

from inventario.servicios import ciclos
from produccion.models import Bitacora, Lote, OcupacionSector, OrdenTrabajo, TransicionEtapa
from produccion.servicios import costos

# Una fila de «Lotes activos» (ficha del invernadero y bandeja).
FilaDeLote = namedtuple(
    "FilaDeLote",
    "lote_id codigo invernadero_id variedad_id variedad_nombre etapa_id etapa_nombre etapa_codigo "
    "cantidad_inicial cantidad_actual costo_por_planta fecha_de_entrada fecha_estimada_de_fin",
)


def _es_primera_etapa(etapa_id, etapas_del_ciclo):
    """Si `etapa_id` es la primera etapa del ciclo (la de menor puesto global)."""
    return bool(etapas_del_ciclo) and etapas_del_ciclo[0].etapa_id == etapa_id


def _cargas_iniciales(lote_ids):
    """`{lote_id: (etapa_id, fecha de ingreso)}` de la entrada de bitácora `carga_inicial` de cada lote (PRD-05, L3; D-92 punto 12). Una
    consulta. Un lote cargado tiene una sola; si hubiera más, vale la última."""
    filas = (
        Bitacora.objects.filter(lote_id__in=list(lote_ids), tipo_evento=Bitacora.TipoEvento.CARGA_INICIAL)
        .order_by("fecha_bitacora", "pk")
        .values_list("lote_id", "etapa_id", "fecha_bitacora")
    )
    return {lote_id: (etapa_id, fecha) for lote_id, etapa_id, fecha in filas}


def entradas_a_la_etapa(lotes, etapas):
    """`{lote_id: fecha de entrada a su etapa actual}` (regla 5 de 8.21). `lotes` vienen con `siembra` cargada y `etapas` es
    `ciclos.etapas_de` de sus variedades. La `fecha_transicion` de la transición concretada del lote cuya etapa destino es la etapa actual
    (la más reciente si hubiera más de una); si no la hay, la fecha de ingreso de su entrada de bitácora `carga_inicial` en esa etapa (PRD-05,
    L3: un lote cargado en cualquier etapa, también la primera); si tampoco, en la primera etapa del ciclo, `siembra.fecha_siembra`. Dos
    consultas fijas (cargas iniciales y transiciones), no por lote."""
    lotes = list(lotes)
    cargas = _cargas_iniciales([l.pk for l in lotes]) if lotes else {}
    entradas, pendientes = {}, []
    for lote in lotes:
        carga = cargas.get(lote.pk)
        carga_en_la_etapa_actual = carga is not None and carga[0] == lote.etapa_id
        if _es_primera_etapa(lote.etapa_id, etapas[lote.siembra.variedad_id]) and not carga_en_la_etapa_actual:
            entradas[lote.pk] = lote.siembra.fecha_siembra
        else:
            pendientes.append(lote)
    if pendientes:
        concretadas = {}
        filas = (
            TransicionEtapa.objects.filter(lote_id__in=[l.pk for l in pendientes], estado_orden=OrdenTrabajo.Estado.CONCRETADA)
            .order_by("fecha_transicion", "pk")
            .values_list("lote_id", "etapa_destino_id", "fecha_transicion")
        )
        for lote_id, etapa_id, fecha in filas:
            concretadas[(lote_id, etapa_id)] = fecha  # la última pisa a las anteriores
        for lote in pendientes:
            carga = cargas.get(lote.pk)
            de_la_carga = carga[1] if carga is not None and carga[0] == lote.etapa_id else None
            entradas[lote.pk] = concretadas.get((lote.pk, lote.etapa_id), de_la_carga)
    return entradas


def fecha_de_entrada_a_la_etapa(lote):
    """Regla 5 de 8.21: la primera etapa, la fecha de siembra; las demás, la fecha efectiva de la transición concretada que la
    tuvo de destino (PRD-02). `None` si no se conoce."""
    etapas = ciclos.etapas_de([lote.siembra.variedad_id])
    return entradas_a_la_etapa([lote], etapas)[lote.pk]


def fecha_estimada_de_fin_de_etapa(lote):
    """Fecha de entrada a la etapa actual + `duracion_estimada_dias` de esa etapa; `None` si no se conoce la entrada."""
    entrada = fecha_de_entrada_a_la_etapa(lote)
    return None if entrada is None else entrada + timedelta(days=lote.etapa.duracion_estimada_dias)


def _etapa_de_maduracion(variedad_id):
    """La etapa de Maduración del ciclo de la variedad (`EtapaDelCiclo`), o `None` si su ciclo no la tiene."""
    return next((e for e in ciclos.etapas_de([variedad_id])[variedad_id] if e.codigo == ciclos.MADURACION), None)


def fecha_de_entrada_a_maduracion(lote):
    """Regla 2 de 8.20: la `fecha_transicion` de la transición concretada con destino Maduración; si no la hay, la fecha de ingreso de la
    entrada `carga_inicial` del lote en Maduración (PRD-05, L3); `None` si no entró."""
    maduracion = _etapa_de_maduracion(lote.siembra.variedad_id)
    if maduracion is None:
        return None
    transicion = (
        TransicionEtapa.objects.filter(
            lote=lote, etapa_destino_id=maduracion.etapa_id, estado_orden=OrdenTrabajo.Estado.CONCRETADA
        )
        .order_by("-fecha_transicion", "-pk")
        .values_list("fecha_transicion", flat=True)
        .first()
    )
    if transicion is not None:
        return transicion
    etapa_cargada, fecha = _cargas_iniciales([lote.pk]).get(lote.pk, (None, None))
    return fecha if etapa_cargada == maduracion.etapa_id else None


def fecha_maxima_de_cosecha(lote):
    """Regla 3 de 8.20: entrada a Maduración + `duracion_dias` de esa etapa; `None` si no entró."""
    entrada = fecha_de_entrada_a_maduracion(lote)
    if entrada is None:
        return None
    return entrada + timedelta(days=_etapa_de_maduracion(lote.siembra.variedad_id).duracion_dias)


def sectores_de_origen(lote):
    """Las ocupaciones del lote con `cant_agujeros_ocupados > 0`, con su sector, ordenadas por id."""
    return list(
        OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0).select_related("sector").order_by("id")
    )


def perfil_de_sector(sector_ids):
    """`{sector_id: perfil familiar o None}`: el de la variedad de los lotes con ocupaciones vigentes en el sector y de las órdenes
    «a realizar» que lo usan; `None` si no tiene ninguno (regla de compatibilidad de PROD-PNF-SMB). Una consulta."""
    ids = list(sector_ids)
    perfiles = {i: None for i in ids}
    filas = (
        OcupacionSector.objects.filter(sector_id__in=ids)
        .filter(Q(cant_agujeros_ocupados__gt=0) | Q(orden__estado_orden=OrdenTrabajo.Estado.A_REALIZAR))
        .annotate(
            # Un lote con plantas, una siembra «a realizar» o (PRD-02) una transición «a realizar» hacia el sector.
            perfil=Coalesce(
                "lote__siembra__variedad__perfil_familia",
                "orden__siembra__variedad__perfil_familia",
                "orden__transicionetapa__lote__siembra__variedad__perfil_familia",
            )
        )
        .values_list("sector_id", "perfil")
        .order_by("id")
    )
    for sector_id, perfil in filas:
        if perfiles[sector_id] is None and perfil:
            perfiles[sector_id] = perfil
    return perfiles


def lotes_activos_de(invernadero_ids):
    """Lotes activos de los invernaderos pedidos, con variedad, etapa, cantidad, costo por planta, fecha de entrada a la etapa y
    fecha estimada de fin. Ordenados por id. Consultas fijas: los lotes (con sus joins) y los ciclos de sus variedades."""
    ids = list(invernadero_ids)
    lotes = list(
        Lote.objects.filter(invernadero_id__in=ids, estado_lote=Lote.Estado.ACTIVO)
        .select_related("siembra__variedad__cultivo", "etapa__tipo_etapa")
        .order_by("id")
    )
    etapas = ciclos.etapas_de({lote.siembra.variedad_id for lote in lotes}) if lotes else {}
    entradas = entradas_a_la_etapa(lotes, etapas) if lotes else {}
    filas = []
    for lote in lotes:
        variedad = lote.siembra.variedad
        entrada = entradas[lote.pk]
        filas.append(
            FilaDeLote(
                lote_id=lote.pk,
                codigo=lote.codigo,
                invernadero_id=lote.invernadero_id,
                variedad_id=variedad.pk,
                variedad_nombre=str(variedad),
                etapa_id=lote.etapa_id,
                etapa_nombre=lote.etapa.tipo_etapa.nombre_etapa,
                etapa_codigo=lote.etapa.tipo_etapa.codigo,
                cantidad_inicial=lote.cantidad_inicial,
                cantidad_actual=lote.cantidad_actual,
                costo_por_planta=costos.costo_por_planta(lote),
                fecha_de_entrada=entrada,
                fecha_estimada_de_fin=None if entrada is None else entrada + timedelta(days=lote.etapa.duracion_estimada_dias),
            )
        )
    return filas
