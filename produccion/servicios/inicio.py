# Inicio del Agrónomo (PRD-04, paso 6; D-51 punto 10, D-43): los indicadores de la sección que `produccion` registra con `registrar_seccion_de_inicio`.
# No es un caso de uso. Fuente: `VIEWS.inicio` del prototipo (lotes activos, órdenes vencidas, ocupación e insumos por vencer) y la tarea PRD-04.
# Una consulta por indicador (no por invernadero) y, sin invernaderos válidos, ninguna: todo en cero y `sin_invernaderos`.

from collections import namedtuple
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.models import Usuario, rol_de
from inventario.alertas import INSUMO_POR_VENCER
from maestros.models import Alerta, Invernadero, SectorProduccion
from produccion.errores import ErrorDeProduccion
from produccion.models import Lote, OcupacionSector, OrdenTrabajo
from produccion.servicios import ordenes

IndicadoresDelAgronomo = namedtuple(
    "IndicadoresDelAgronomo",
    "lotes_activos plantas_en_pie ordenes_a_realizar ordenes_vencidas agujeros_ocupados agujeros_totales porcentaje_de_ocupacion "
    "insumos_por_vencer sin_invernaderos",
)
VACIOS = IndicadoresDelAgronomo(0, 0, 0, 0, 0, 0, 0, 0, True)


def indicadores_del_agronomo(actor, invernadero_ids):
    """Los indicadores del Inicio del Agrónomo para los invernaderos de `invernadero_ids` que sean ACTIVOS y estén a su cargo (los demás se
    ignoran: el Agrónomo ve solo los suyos). Solo el Agrónomo activo (`sin_permiso`).

    - Lotes activos y sus plantas; órdenes «a realizar» de siembra y transición y cuántas están vencidas (fecha programada anterior a hoy).
    - Ocupación: agujeros ocupados ÷ agujeros totales de los sectores ACTIVOS (los fuera de servicio no se ofrecen), en porcentaje entero
      redondeado; sin agujeros, 0.
    - Insumos por vencer: las alertas activas `inv_insumo_por_vencer` destinadas al actor (`Alerta.objects.para(actor)`) de esos invernaderos.
      No hay función nueva en `inventario`.
    Si no queda ningún invernadero válido, `sin_invernaderos` y ceros, sin consultar los indicadores."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise ErrorDeProduccion("sin_permiso", "Tu cuenta no tiene acceso a esta información.")
    validos = list(
        Invernadero.objects.filter(
            pk__in=list(invernadero_ids), agronomo_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO
        ).values_list("pk", flat=True)
    )
    if not validos:
        return VACIOS
    hoy = timezone.localdate()
    lotes = Lote.objects.filter(invernadero_id__in=validos, estado_lote=Lote.Estado.ACTIVO).aggregate(
        n=Count("pk"), plantas=Sum("cantidad_actual")
    )
    pendientes = OrdenTrabajo.objects.filter(
        invernadero_id__in=validos, estado_orden=OrdenTrabajo.Estado.A_REALIZAR, tipo_orden__in=list(ordenes.TIPOS_DE_PRODUCCION)
    ).aggregate(n=Count("pk"), vencidas=Count("pk", filter=Q(fecha_programada_orden__lt=hoy)))
    totales = (
        SectorProduccion.objects.filter(invernadero_id__in=validos, estado_sector=SectorProduccion.Estado.ACTIVO).aggregate(
            t=Sum("cant_agujeros_total")
        )["t"]
        or 0
    )
    ocupados = (
        OcupacionSector.objects.filter(
            sector__invernadero_id__in=validos, sector__estado_sector=SectorProduccion.Estado.ACTIVO
        ).aggregate(t=Sum("cant_agujeros_ocupados"))["t"]
        or 0
    )
    por_vencer = (
        Alerta.objects.para(actor).activas().filter(tipo_alerta=INSUMO_POR_VENCER, invernadero_id__in=validos).count()
    )
    porcentaje = int((Decimal(ocupados) * 100 / totales).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if totales else 0
    return IndicadoresDelAgronomo(
        lotes["n"], lotes["plantas"] or 0, pendientes["n"], pendientes["vencidas"], ocupados, totales, porcentaje, por_vencer, False
    )
