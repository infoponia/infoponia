# Lectura de lotes de `produccion` (PRD-01): lotes activos, fechas de entrada y de fin de etapa, sectores de origen y perfil de un
# sector. Solo lee: no escribe ni bloquea. Los datos de más de un lote se piden con listas de ids y una consulta por tabla.
# Fuente: docs/api/produccion.md (sección 2) y docs/modelo/produccion.md («Lo que se calcula de un lote» y de las ocupaciones).
#
# Se completa en PRD-02: la fecha de entrada a una etapa que NO es la primera sale de la transición concretada (`TransicionEtapa`),
# que todavía no existe; en PRD-01 ningún lote sale de Germinación, así que esas fechas valen `None` (decisión del estudiante, PRD-01).

from collections import namedtuple
from datetime import timedelta

from django.db.models import Q
from django.db.models.functions import Coalesce

from inventario.servicios import ciclos
from produccion.models import Lote, OcupacionSector, OrdenTrabajo
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


def fecha_de_entrada_a_la_etapa(lote):
    """Regla 5 de 8.21. En la primera etapa del ciclo: `siembra.fecha_siembra`. En las demás sale de la transición concretada
    (PRD-02): hasta entonces, `None`."""
    etapas = ciclos.etapas_de([lote.siembra.variedad_id])[lote.siembra.variedad_id]
    return lote.siembra.fecha_siembra if _es_primera_etapa(lote.etapa_id, etapas) else None


def fecha_estimada_de_fin_de_etapa(lote):
    """Fecha de entrada a la etapa actual + `duracion_estimada_dias` de esa etapa; `None` si no se conoce la entrada."""
    entrada = fecha_de_entrada_a_la_etapa(lote)
    return None if entrada is None else entrada + timedelta(days=lote.etapa.duracion_estimada_dias)


def fecha_de_entrada_a_maduracion(lote):
    """Regla 2 de 8.20: la `fecha_transicion` de la transición concretada con destino Maduración; `None` si no entró.
    Se completa en PRD-02 (hoy ningún lote sale de Germinación)."""
    return None


def fecha_maxima_de_cosecha(lote):
    """Regla 3 de 8.20: entrada a Maduración + duración de esa etapa; `None` si no entró. Se completa en PRD-02."""
    return None


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
            perfil=Coalesce("lote__siembra__variedad__perfil_familia", "orden__siembra__variedad__perfil_familia")
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
    filas = []
    for lote in lotes:
        variedad = lote.siembra.variedad
        entrada = lote.siembra.fecha_siembra if _es_primera_etapa(lote.etapa_id, etapas[variedad.pk]) else None
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
