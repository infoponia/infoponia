# Núcleo de la merma de un lote en pie (PRD-02, paso 3). NO es un caso de uso: es una función interna que corre en la transacción de
# quien la llama (Concretar Transición, PRD-02; Registrar Merma, PRD-03; Sector fuera de servicio, PRD-04) con el invernadero, la
# variedad, los sectores y el lote YA bloqueados (docs/patrones/bloqueos.md, sección `produccion`). No audita ni notifica: devuelve lo
# que creó para que el caso de uso lo ponga en su único registro de auditoría (D-36).
# Fuente: docs/casos_de_uso/produccion/transicion.md (extracto de PROD-REG-MRM y «Núcleo de la merma desde la transición»),
# docs/api/produccion.md (sección 6), docs/patrones/costo_del_lote.md, D-50 punto 6 y D-51 punto 5.
# Fuera de la ronda (D-45): el movimiento de stock «salida por merma» (postcondición d), el asiento (e), la condición 1 de plantas
# comprometidas (cosechas) y la partida en cámara.

from collections import namedtuple
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection
from django.db.models import Sum
from django.utils import timezone

from maestros.servicios import alertas, configuracion
from produccion.errores import ErrorDeProduccion
from produccion.models import AlertaDeMerma, Lote, Merma, OcupacionSector, OrdenTrabajo, TransicionEtapa
from produccion.servicios import costos

# Lo que devuelve `aplicar_merma`: la merma creada, lo que costó (se descontó del costo acumulado del lote) y las alertas creadas.
ResultadoMerma = namedtuple("ResultadoMerma", "merma costo alertas")

TIPO_UMBRAL = "produccion_merma_umbral"
TIPO_PLANTAS_COMPROMETIDAS = "produccion_plantas_comprometidas"
LARGO_DE_LA_DESCRIPCION = 300  # la que escribe quien registra; con el texto legible entra siempre en los 500 de la bitácora
LARGO_DE_LA_ALERTA = 200  # `Alerta.descripcion_alerta`


def _error(codigo, mensaje, campo=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo)


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
    if causa not in Merma.Causa.values:
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


def _alertas_de_plantas_comprometidas(lote, ordenes_excluidas):
    """Postcondición l y extensión 10a, condición 2 de la regla 15 de 8.8: la transición «a realizar» del lote (sin contar las
    `ordenes_excluidas`) queda con más plantas planificadas que `cantidad_actual`. Una alerta por orden afectada."""
    creadas = []
    pendientes = TransicionEtapa.objects.filter(lote=lote, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).exclude(
        pk__in=list(ordenes_excluidas)
    )
    for orden in pendientes.order_by("pk"):
        planificadas = OcupacionSector.objects.filter(orden_id=orden.pk).aggregate(t=Sum("cant_agujeros_planificados"))["t"] or 0
        if planificadas > lote.cantidad_actual:
            texto = f"{lote.codigo} tiene {lote.cantidad_actual} plantas y su transición {orden.codigo} planificó {planificadas}."
            creadas.append(alertas.crear_alerta_de_evento(lote.invernadero_id, TIPO_PLANTAS_COMPROMETIDAS, texto[:LARGO_DE_LA_ALERTA]))
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
    - Postcondiciones k y l: alerta de umbral y alerta de plantas comprometidas (condición 2), enlazadas con la merma por `AlertaDeMerma`.
      Un invernadero inactivo no genera alertas (`crear_alerta_de_evento` da `None`): la merma se registra igual.
    - Rechaza con `ErrorDeProduccion`: `cantidad_invalida`, `causa_obligatoria`, `causa_invalida`, `descripcion_larga`, `fecha_invalida`.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("aplicar_merma corre dentro de la transacción del caso de uso que la llama.")
    descripcion, ocupaciones = _verificar(lote, cantidad, causa, descripcion, fecha, por_sector)
    costo = costos.costo_de_la_merma(lote, cantidad)  # antes de cambiar la cantidad del lote (docs/patrones/costo_del_lote.md)
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
