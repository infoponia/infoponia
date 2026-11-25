# Sectores elegibles para ubicar plantas (regla «Sector elegible» de PROD-PNF-TRN), compartida por PROD-PNF-TRN y PROD-REG-LTE (PRD-05).
# Se movió acá desde `transiciones._sectores_del_destino` SIN cambiar su comportamiento (aclaración 6 de PRD-05): solo lee, no escribe ni bloquea.

from collections import namedtuple

from maestros.models import SectorProduccion
from maestros.servicios import sectores as api_sectores
from produccion.servicios import lotes as api_lotes

# Un sector del tipo pedido que NO se puede elegir, con su motivo: `fuera_de_servicio`, `perfil_incompatible` o `sin_lugar`.
SectorNoElegible = namedtuple("SectorNoElegible", "sector_id nombre motivo texto")


def sectores_elegibles(invernadero_id, tipo_etapa_id, perfil):
    """Los sectores del invernadero del tipo de etapa `tipo_etapa_id`: `(elegibles, no_elegibles)`. Elegible: ACTIVO, compatible por `perfil` familiar
    (`perfil` es el de la variedad) y con capacidad libre mayor que cero: `{sector_id: (sector, Agujeros)}`. Los inactivos no figuran; los fuera de
    servicio, los de otro perfil y los llenos van entre los no elegibles con su motivo. No se valida el umbral ambiental."""
    sectores = list(
        SectorProduccion.objects.filter(invernadero_id=invernadero_id, tipo_etapa_id=tipo_etapa_id)
        .exclude(estado_sector=SectorProduccion.Estado.INACTIVO)
        .select_related("tipo_etapa")
        .order_by("id")
    )
    agujeros = api_sectores.agujeros_de(sectores)
    perfiles = api_lotes.perfil_de_sector([s.pk for s in sectores])
    incompatibles = [s for s in sectores if s.estado_sector == SectorProduccion.Estado.ACTIVO and perfiles[s.pk] not in (None, perfil)]
    contenido = api_sectores.contenido_de_sectores(incompatibles) if incompatibles else {}
    elegibles, no_elegibles = {}, []
    for s in sectores:
        libres = agujeros[s.pk].libres
        if s.estado_sector != SectorProduccion.Estado.ACTIVO:
            no_elegibles.append(SectorNoElegible(s.pk, s.nombre_sector, "fuera_de_servicio", "Fuera de servicio: no se puede elegir."))
        elif perfiles[s.pk] not in (None, perfil):
            quienes = ", ".join(c.texto for c in contenido.get(s.pk, []))
            no_elegibles.append(
                SectorNoElegible(
                    s.pk, s.nombre_sector, "perfil_incompatible", f"Tiene plantas de otro perfil familiar ({perfiles[s.pk]}): {quienes}."
                )
            )
        elif libres <= 0:
            no_elegibles.append(SectorNoElegible(s.pk, s.nombre_sector, "sin_lugar", "Sin agujeros libres."))
        else:
            elegibles[s.pk] = (s, agujeros[s.pk])
    return elegibles, no_elegibles
