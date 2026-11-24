# Servicios de transición de etapa de `produccion` (PRD-02, PROD-PNF-TRN y PROD-CNC-TRN). Este archivo tiene, por ahora, la LECTURA
# (paso 2): los lotes trasladables, la fecha mínima de una transición y el reparto proporcional; y PLANIFICAR (paso 4, al final). La
# lectura no escribe ni bloquea y pide los datos de varios lotes con listas de ids y una consulta por tabla. Concretar se agrega en el paso 5.
# Fuente: docs/casos_de_uso/produccion/transicion.md («Reglas de negocio» y «Cómo se aplica en la ronda»), docs/api/produccion.md
# (sección 2), regla 1 de 8.20 y reglas 1 a 5 de 8.21 del modelo de dominio.

from collections import defaultdict, namedtuple
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q
from django.http import Http404
from django.utils import timezone

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import ciclos, variedades
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Lote, Merma, OcupacionSector, OrdenTrabajo, TransicionEtapa
from produccion.servicios import lotes as api_lotes
from produccion.servicios import mermas, ordenes
from produccion.servicios.bloqueos import traducir as _bloquear

# Un lote de los que ve el Agrónomo al planificar (paso 2 del CU), con lo que pide el CU y el motivo por el que no se puede elegir
# (extensiones 3a y 3b): `motivo` es `None` si se puede trasladar; si no, `ultima_etapa`, `transicion_a_realizar` o `sin_capataz`.
# `sectores` es una lista de `(sector_id, nombre, agujeros ocupados)`; `transicion_pendiente` es `(codigo, fecha programada)` o `None`.
FilaDeLoteTrasladable = namedtuple(
    "FilaDeLoteTrasladable",
    "lote_id codigo invernadero_id invernadero variedad_id variedad_nombre perfil_familia etapa_id etapa_nombre etapa_codigo "
    "fecha_de_entrada fecha_estimada_de_fin etapa_siguiente_id etapa_siguiente_nombre etapa_siguiente_codigo "
    "etapa_siguiente_dias cantidad_actual sectores transicion_pendiente motivo trasladable",
)

MOTIVOS = {
    "ultima_etapa": "Está en la última etapa de su ciclo: lo que sigue es la cosecha.",
    "transicion_a_realizar": "Ya tiene una transición a realizar.",
    "sin_capataz": "El invernadero no tiene un Capataz activo que pueda recibir la orden.",
}


def lotes_trasladables(actor):
    """Paso 2 de PROD-PNF-TRN: los lotes activos de los invernaderos ACTIVOS a cargo del Agrónomo `actor`, cada uno con su
    `motivo` si no se puede trasladar (regla «Lote trasladable»: activo, con plantas, no en la última etapa del ciclo y sin otra
    transición «a realizar»; más la extensión 3b: invernadero con Capataz activo). Para cualquier otra cuenta, lista vacía. Ordenados
    por id de lote. La etapa siguiente es la inmediata posterior en `puesto_global` entre las del ciclo de su variedad (regla 1 de 8.20).
    Una consulta por tabla (lotes, ciclos, ocupaciones, transiciones y fechas de entrada), sin consultas por fila."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) != Usuario.Rol.AGRONOMO:
        return []
    lotes = list(
        Lote.objects.filter(
            invernadero__in=Invernadero.objects.en_alcance_de(actor), estado_lote=Lote.Estado.ACTIVO, cantidad_actual__gt=0
        )
        .select_related("invernadero__capataz", "siembra__variedad__cultivo", "etapa__tipo_etapa")
        .order_by("id")
    )
    if not lotes:
        return []
    ids = [lote.pk for lote in lotes]
    etapas = ciclos.etapas_de({lote.siembra.variedad_id for lote in lotes})
    entradas = api_lotes.entradas_a_la_etapa(lotes, etapas)
    sectores = defaultdict(list)
    for o in (
        OcupacionSector.objects.filter(lote_id__in=ids, cant_agujeros_ocupados__gt=0).select_related("sector").order_by("id")
    ):
        sectores[o.lote_id].append((o.sector_id, o.sector.nombre_sector, o.cant_agujeros_ocupados))
    pendientes = {
        lote_id: (f"OT-{numero:04d}", fecha)
        for lote_id, numero, fecha in TransicionEtapa.objects.filter(lote_id__in=ids, estado_orden=OrdenTrabajo.Estado.A_REALIZAR)
        .order_by("-pk")
        .values_list("lote_id", "numero", "fecha_programada_orden")
    }
    filas = []
    for lote in lotes:
        variedad = lote.siembra.variedad
        del_ciclo = etapas[variedad.pk]
        posicion = next((i for i, e in enumerate(del_ciclo) if e.etapa_id == lote.etapa_id), None)
        siguiente = del_ciclo[posicion + 1] if posicion is not None and posicion + 1 < len(del_ciclo) else None
        capataz = lote.invernadero.capataz
        if siguiente is None:
            motivo = "ultima_etapa"
        elif lote.pk in pendientes:
            motivo = "transicion_a_realizar"
        elif capataz is None or not capataz.is_active:
            motivo = "sin_capataz"
        else:
            motivo = None
        entrada = entradas[lote.pk]
        filas.append(
            FilaDeLoteTrasladable(
                lote_id=lote.pk,
                codigo=lote.codigo,
                invernadero_id=lote.invernadero_id,
                invernadero=lote.invernadero.nombre_invernadero,
                variedad_id=variedad.pk,
                variedad_nombre=str(variedad),
                perfil_familia=variedad.perfil_familia,
                etapa_id=lote.etapa_id,
                etapa_nombre=lote.etapa.tipo_etapa.nombre_etapa,
                etapa_codigo=lote.etapa.tipo_etapa.codigo,
                fecha_de_entrada=entrada,
                fecha_estimada_de_fin=None if entrada is None else entrada + timedelta(days=lote.etapa.duracion_estimada_dias),
                etapa_siguiente_id=siguiente.etapa_id if siguiente else None,
                etapa_siguiente_nombre=siguiente.nombre if siguiente else None,
                etapa_siguiente_codigo=siguiente.codigo if siguiente else None,
                etapa_siguiente_dias=siguiente.duracion_dias if siguiente else None,
                cantidad_actual=lote.cantidad_actual,
                sectores=sectores.get(lote.pk, []),
                transicion_pendiente=pendientes.get(lote.pk),
                motivo=motivo,
                trasladable=motivo is None,
            )
        )
    return filas


def fecha_minima_de_transicion(lote):
    """Fecha mínima admitida al concretar (pasos 4 y 6 y extensión 6b de PROD-CNC-TRN): la mayor entre la fecha de entrada del lote a
    su etapa actual y la fecha de su último registro de bitácora asociado a esa etapa, si lo tiene. `None` si no se conoce ninguna."""
    return _fecha_minima_con_origen(lote)[0]


def repartir_proporcional(cantidad, planificado):
    """Reparto proporcional de PROD-CNC-TRN (paso 4 y extensión 13c), función pura. Reparte `cantidad` entre los sectores en
    proporción a lo `planificado` en cada uno (una lista de enteros, en el orden de la orden) y devuelve una lista del mismo largo:
    cada sector recibe la parte entera de su cuota y las unidades restantes van de a una a los de mayor parte decimal (método del
    resto mayor); si hay empate, al de más agujeros planificados y, si sigue, al primero de la lista. Si `cantidad` alcanza o supera
    lo planificado, cada sector conserva lo suyo (nunca recibe más de lo planificado). Se hace con enteros: sin errores de redondeo."""
    planificado = list(planificado)
    if cantidad < 0 or any(p < 0 for p in planificado):
        raise ValueError("La cantidad y lo planificado no pueden ser negativos.")
    total = sum(planificado)
    if total == 0 or cantidad >= total:
        return planificado
    cuotas = [(cantidad * p) // total for p in planificado]
    restos = [(cantidad * p) % total for p in planificado]
    faltan = cantidad - sum(cuotas)
    orden = sorted(range(len(planificado)), key=lambda i: (-restos[i], -planificado[i], i))
    for i in orden[:faltan]:
        cuotas[i] += 1
    return cuotas


# ============================================================================================================================
# PROD-PNF-TRN · Planificar Transición (paso 4)
# ============================================================================================================================
# - `datos_de_planificacion`: lo que presentan los pasos 2 a 7. No escribe ni bloquea.
# - `resumen_de_planificacion`: valida TODO y devuelve el resumen del paso 11. No escribe ni bloquea.
# - `planificar_transicion`: una verificación liviana (permiso, lote, fechas: lo que dice qué bloquear), bloquea en el orden de
#   bloqueos.md (cuentas → invernadero → variedad → sectores destino, por id → lote → filas propias), y recién ENTONCES vuelve a
#   verificar TODO, incluidos los cambios que la persona no vio (`cambio_simultaneo`, extensiones 13a y 13b) y la capacidad de los sectores
#   (13c); después escribe: la orden, sus ocupaciones, el aviso al Capataz y un único registro de auditoría. Sin reservas de insumo
#   (la transición no consume) ni asientos (D-45).
# Todos los rechazos de negocio son `ErrorDeProduccion(codigo, mensaje, campo, datos)`, en voseo rioplatense.

PRIORIDADES = ("alta", "media", "baja")
LARGO_DE_LA_DESCRIPCION = 500


@dataclass(frozen=True)
class DatosDeTransicion:
    """Lo que el Agrónomo carga en los pasos 3 a 10. `distribucion` es `((sector_id, plantas), ...)`. `cantidad` y `etapa_actual_id` son
    lo que la persona VIO del lote (su cantidad actual y su etapa): si al confirmar cambiaron, `cambio_simultaneo` con el dato nuevo
    (extensiones 13a y 13b); `None` no lo verifica. La vista los arma desde el formulario."""

    lote_id: int
    fecha_programada: date
    distribucion: tuple = ()
    prioridad: str | None = None
    descripcion: str = ""
    cantidad: int | None = None
    etapa_actual_id: int | None = None


# Lo que presenta la pantalla de «Nueva transición» (pasos 2 a 7). Con `lote_id`, todo lo demás; sin él, solo `lotes`.
DatosDePlanificacionDeTransicion = namedtuple(
    "DatosDePlanificacionDeTransicion",
    "lotes lote etapa_destino cantidad capataz fecha_propuesta dias_de_atraso fecha_estimada_de_fin diferencia_en_dias "
    "fecha_maxima_de_cosecha sectores no_elegibles",
)
SectorElegible = namedtuple("SectorElegible", "sector_id nombre libres")
# `motivo`: `fuera_de_servicio`, `perfil_incompatible` o `sin_lugar`; `texto`, la explicación (con los lotes y órdenes que lo ocupan).
SectorNoElegible = namedtuple("SectorNoElegible", "sector_id nombre motivo texto")
# El resumen del paso 11. `distribucion` y `sectores_de_origen` son listas de `(sector, plantas)`.
ResumenDeTransicion = namedtuple(
    "ResumenDeTransicion",
    "invernadero lote variedad etapa_origen etapa_destino cantidad sectores_de_origen distribucion fecha_programada "
    "fecha_estimada_de_fin diferencia_en_dias fecha_maxima_de_cosecha prioridad descripcion capataz",
)
# Todo lo que `_verificar` resuelve y que `planificar_transicion` usa para escribir.
Plan = namedtuple(
    "Plan",
    "lote invernadero capataz variedad etapa_origen etapa_destino cantidad fecha prioridad descripcion distribucion "
    "fecha_estimada_de_fin elegibles no_elegibles",
)


# ---- Errores y verificaciones ----


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


def _exigir_agronomo_activo(actor):
    """Precondición a: `actor` es un Agrónomo activo (se lee de la base: pudo darse de baja mientras tanto)."""
    if (
        actor is None
        or rol_de(actor) != Usuario.Rol.AGRONOMO
        or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise _error("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")


def _lote_a_cargo(actor, lote_id):
    """El lote (con lo que se muestra cargado) de un invernadero a cargo de `actor`: `Http404` si no existe, `sin_permiso` si no es suyo."""
    lote = (
        Lote.objects.select_related("invernadero__capataz", "siembra__variedad__cultivo", "etapa__tipo_etapa")
        .filter(pk=lote_id)
        .first()
    )
    if lote is None:
        raise Http404("No existe ese lote.")
    if lote.invernadero.agronomo_id != actor.pk:
        raise _error("sin_permiso", "Ese lote no es de un invernadero a tu cargo.")
    return lote


def _exigir_trasladable(lote, *, con_pendiente=True):
    """Precondiciones b y c, «Lote trasladable» y extensiones 3a y 3b. Devuelve `(etapa_origen, etapa_destino)` del ciclo (regla 1 de 8.20)."""
    if not lote.invernadero.activo:
        raise _error("invernadero_inactivo", "El invernadero está inactivo: no se puede planificar una transición en él.")
    if lote.estado_lote != Lote.Estado.ACTIVO or lote.cantidad_actual <= 0:
        raise _error("lote_no_trasladable", f"El lote {lote.codigo} ya no está activo o no tiene plantas: no se puede trasladar.")
    del_ciclo = ciclos.etapas_de([lote.siembra.variedad_id])[lote.siembra.variedad_id]
    posicion = next((i for i, e in enumerate(del_ciclo) if e.etapa_id == lote.etapa_id), None)
    if posicion is None or posicion + 1 >= len(del_ciclo):
        raise _error("lote_no_trasladable", f"El lote {lote.codigo} está en la última etapa de su ciclo: lo que sigue es la cosecha.")
    # `con_pendiente=False` en la pasada liviana de antes de bloquear: «otra transición a realizar» se mira recién con el lote bloqueado
    # (si no, una cancelación a punto de confirmarse haría rechazar de más a quien planifica otra).
    pendiente = (
        TransicionEtapa.objects.filter(lote=lote, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).order_by("pk").first()
        if con_pendiente
        else None
    )
    if pendiente is not None:
        raise _error(
            "lote_con_transicion",
            f"El lote {lote.codigo} ya tiene la transición {pendiente.codigo}, programada para el {pendiente.fecha_programada_orden:%d/%m/%Y}.",
            datos={"codigo": pendiente.codigo, "fecha": pendiente.fecha_programada_orden},
        )
    capataz = lote.invernadero.capataz
    if capataz is None or not capataz.is_active:
        raise _error(
            "sin_capataz_activo",
            "No hay un Capataz activo asignado a este invernadero que pueda recibir la orden: pedile al Gerente que lo asigne.",
        )
    return del_ciclo[posicion], del_ciclo[posicion + 1]


def _exigir_lo_que_se_vio(lote, datos, etapa_origen):
    """Extensiones 13a y 13b, DESPUÉS de bloquear el lote: la etapa y la cantidad actual siguen siendo las que la persona vio."""
    if datos.etapa_actual_id is not None and datos.etapa_actual_id != etapa_origen.etapa_id:
        raise _error(
            "cambio_simultaneo",
            f"Mientras planificabas, el lote {lote.codigo} cambió de etapa: ahora está en {etapa_origen.nombre}. Volvé a elegirlo.",
            datos={"etapa_actual": etapa_origen.nombre},
        )
    if datos.cantidad is not None and datos.cantidad != lote.cantidad_actual:
        raise _error(
            "cambio_simultaneo",
            f"Mientras planificabas, cambió la cantidad del lote {lote.codigo} (por ejemplo, por una merma): ahora tiene "
            f"{lote.cantidad_actual} plantas. Volvé a distribuirlas.",
            datos={"cantidad_actual": lote.cantidad_actual},
        )


def _exigir_formato(datos):
    """Fecha, prioridad y descripción (extensión 6a y paso 10). Devuelve `(fecha, prioridad, descripcion)`."""
    fecha = datos.fecha_programada
    if not isinstance(fecha, date):
        raise _error("fecha_invalida", "Indicá la fecha programada.", "fecha_programada")
    if fecha < timezone.localdate():
        raise _error("fecha_invalida", "La fecha programada no puede ser anterior a hoy.", "fecha_programada")
    prioridad = datos.prioridad or None
    if prioridad is not None and prioridad not in PRIORIDADES:
        raise _error("prioridad_invalida", "La prioridad tiene que ser alta, media o baja.", "prioridad")
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    return fecha, prioridad, descripcion


def _sectores_del_destino(lote, etapa_destino):
    """Los sectores del tipo de la etapa destino (regla «Sector elegible», pasos 7 a 9 y extensión 3c): `(elegibles, no_elegibles)`.
    Elegible: ACTIVO, compatible por perfil familiar y con capacidad libre mayor que cero. Los inactivos no figuran; los fuera de servicio,
    los de otro perfil y los llenos van entre los no elegibles con su motivo. No se valida el umbral ambiental."""
    sectores = list(
        SectorProduccion.objects.filter(invernadero_id=lote.invernadero_id, tipo_etapa_id=etapa_destino.tipo_id)
        .exclude(estado_sector=SectorProduccion.Estado.INACTIVO)
        .select_related("tipo_etapa")
        .order_by("id")
    )
    agujeros = api_sectores.agujeros_de(sectores)
    perfiles = api_lotes.perfil_de_sector([s.pk for s in sectores])
    perfil = lote.siembra.variedad.perfil_familia
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


def _exigir_capacidad_total(lote, elegibles, no_elegibles):
    """Extensión 3c: la capacidad libre total de los sectores elegibles alcanza para el lote; si no, informa la capacidad frente a la
    cantidad y qué sectores del tipo destino no son compatibles por perfil familiar, y con qué lotes u órdenes."""
    libre = sum(a.libres for _, a in elegibles.values())
    if libre >= lote.cantidad_actual:
        return
    incompatibles = [n for n in no_elegibles if n.motivo == "perfil_incompatible"]
    detalle = " ".join(f"{n.nombre}: {n.texto}" for n in incompatibles)
    raise _error(
        "capacidad_insuficiente",
        f"La capacidad libre de los sectores elegibles es de {libre} agujeros y el lote {lote.codigo} tiene {lote.cantidad_actual} plantas."
        + (f" Sectores no compatibles por perfil familiar. {detalle}" if detalle else ""),
        datos={"capacidad_libre": libre, "cantidad": lote.cantidad_actual, "no_compatibles": [n.sector_id for n in incompatibles]},
    )


def _distribucion_valida(distribucion, cantidad, elegibles):
    """Pasos 8 a 10 y extensiones 9a, 9b y 10a: cada sector es uno que se ofrece, con una cantidad entera positiva que entra en su
    capacidad libre, y todo suma exactamente la cantidad del lote. Devuelve `[(sector, plantas)]`."""
    vistos, resultado = set(), []
    for par in distribucion:
        sector_id, plantas = par
        if sector_id not in elegibles:
            raise _error(
                "sector_no_elegible",
                "Ese sector no se puede elegir: tiene que ser un sector activo del tipo de la etapa destino, compatible y de este invernadero.",
                "distribucion",
            )
        if sector_id in vistos or not isinstance(plantas, int) or isinstance(plantas, bool) or plantas <= 0:
            raise _error("cantidad_invalida", "Cada sector se usa una sola vez y con una cantidad entera mayor que cero.", "distribucion")
        sector, agujeros = elegibles[sector_id]
        if plantas > agujeros.libres:
            raise _error(
                "capacidad_insuficiente",
                f"El sector {sector.nombre_sector} tiene {max(0, agujeros.libres)} agujeros libres: indicá una cantidad menor o elegí otro sector.",
                "distribucion",
            )
        vistos.add(sector_id)
        resultado.append((sector, plantas))
    total = sum(n for _, n in resultado)
    if total != cantidad:
        quedan = cantidad - total
        detalle = f"faltan ubicar {quedan}" if quedan > 0 else f"te pasaste por {-quedan}"
        raise _error("distribucion_incompleta", f"La distribución tiene que sumar {cantidad} plantas: {detalle}.", "distribucion")
    return resultado


def _fin_estimado(lote):
    """Fecha estimada de fin de la etapa actual (entrada + duración), o `None` si no se conoce la entrada."""
    return api_lotes.fecha_estimada_de_fin_de_etapa(lote)


def _verificar(actor, datos, *, completo=True):
    """Las verificaciones de PROD-PNF-TRN, en el orden del caso de uso; lee siempre de la base y no escribe. Con `completo=False` es la
    pasada liviana de antes de bloquear (permiso, lote, Capataz, fechas: lo que dice qué bloquear): no compara lo que la persona vio ni
    mira la distribución. Con `completo=True` (el resumen y, después de bloquear, la planificación), todo, incluidas las extensiones
    13a a 13c. Devuelve el `Plan`; el primer rechazo es un `ErrorDeProduccion`."""
    _exigir_agronomo_activo(actor)
    lote = _lote_a_cargo(actor, datos.lote_id)
    fecha, prioridad, descripcion = _exigir_formato(datos)
    etapa_origen, etapa_destino = _exigir_trasladable(lote, con_pendiente=completo)
    if completo:
        _exigir_lo_que_se_vio(lote, datos, etapa_origen)
    elegibles, no_elegibles = ({}, []) if not completo else _sectores_del_destino(lote, etapa_destino)
    distribucion = []
    if completo:
        _exigir_capacidad_total(lote, elegibles, no_elegibles)
        distribucion = _distribucion_valida(datos.distribucion, lote.cantidad_actual, elegibles)
    return Plan(
        lote, lote.invernadero, lote.invernadero.capataz, lote.siembra.variedad, etapa_origen, etapa_destino, lote.cantidad_actual,
        fecha, prioridad, descripcion, distribucion, _fin_estimado(lote), elegibles, no_elegibles,
    )


def _diferencia(fecha, fin):
    """Días entre la fecha elegida y el fin estimado de la etapa (positivo si es posterior); `None` si falta alguno."""
    return None if fecha is None or fin is None else (fecha - fin).days


def _fecha_maxima(etapa_destino, fecha):
    """Fecha máxima de cosecha estimada: solo si el destino es Maduración, la programada más su duración (pasos 7 y 11)."""
    if fecha is None or etapa_destino.codigo != ciclos.MADURACION:
        return None
    return fecha + timedelta(days=etapa_destino.duracion_dias)


# ---- Pasos 2 a 7 y 11: lo que se presenta ----


def asignar_sector(distribucion, sector_id, plantas):
    """Pasos 8 y 9 y extensiones 8-9a y 8-9b, función pura: la distribución con `plantas` en `sector_id`. Si el sector ya estaba, la
    nueva cantidad reemplaza a la anterior en el mismo lugar; con `plantas` en 0 o `None`, se quita. No modifica lo que recibe."""
    quitar = not plantas
    resultado, puesto = [], False
    for sid, n in distribucion:
        if sid == sector_id:
            puesto = True
            if not quitar:
                resultado.append((sid, plantas))
        else:
            resultado.append((sid, n))
    if not puesto and not quitar:
        resultado.append((sector_id, plantas))
    return tuple(resultado)


def por_distribuir(cantidad, distribucion):
    """Paso 9: lo que falta ubicar (la cantidad del lote menos lo asignado; negativo si se pasó)."""
    return cantidad - sum(n for _, n in distribucion)


def datos_de_planificacion(actor, lote_id=None, fecha=None):
    """Lo que presentan los pasos 2 a 7 de PROD-PNF-TRN. No escribe ni bloquea.

    - Siempre: los lotes de sus invernaderos activos, cada uno con el `motivo` por el que no se puede elegir (`lotes_trasladables`).
    - Con `lote_id`: la etapa destino, la cantidad (la del lote), el Capataz, la fecha propuesta (la mayor entre hoy y el fin estimado de
      la etapa actual; extensión 4a: con el fin vencido, hoy y los días de atraso), los sectores elegibles con su capacidad libre y los que
      no, con su motivo. Rechaza como el caso de uso el lote que no se puede elegir (extensiones 3a y 3b) o sin capacidad (3c).
    - Con `fecha` además: la diferencia en días con el fin estimado (extensión 6b, sin bloquear) y la fecha máxima de cosecha.
    """
    _exigir_agronomo_activo(actor)
    lotes = lotes_trasladables(actor)
    if lote_id is None:
        return DatosDePlanificacionDeTransicion(lotes, None, None, None, None, None, None, None, None, None, [], [])
    lote = _lote_a_cargo(actor, lote_id)
    _, etapa_destino = _exigir_trasladable(lote)
    elegibles, no_elegibles = _sectores_del_destino(lote, etapa_destino)
    _exigir_capacidad_total(lote, elegibles, no_elegibles)
    hoy = timezone.localdate()
    fin = _fin_estimado(lote)
    propuesta = hoy if fin is None or fin < hoy else fin
    atraso = (hoy - fin).days if fin is not None and fin < hoy else None
    fila = next(f for f in lotes if f.lote_id == lote.pk)
    return DatosDePlanificacionDeTransicion(
        lotes,
        fila,
        etapa_destino,
        lote.cantidad_actual,
        lote.invernadero.capataz,
        propuesta,
        atraso,
        fin,
        _diferencia(fecha, fin),
        _fecha_maxima(etapa_destino, fecha or propuesta),
        [SectorElegible(s.pk, s.nombre_sector, a.libres) for s, a in elegibles.values()],
        no_elegibles,
    )


def resumen_de_planificacion(actor, datos):
    """Paso 11: valida TODO (los mismos rechazos que `planificar_transicion`) y devuelve el resumen de la orden. No escribe, no numera la
    orden y no bloquea: lo que se presenta puede cambiar hasta la confirmación, que lo vuelve a verificar (extensión 13)."""
    return _resumen(_verificar(actor, datos))


def _resumen(plan):
    """El `ResumenDeTransicion` de un `Plan`."""
    return ResumenDeTransicion(
        plan.invernadero,
        plan.lote,
        plan.variedad,
        plan.etapa_origen,
        plan.etapa_destino,
        plan.cantidad,
        [(o.sector, o.cant_agujeros_ocupados) for o in api_lotes.sectores_de_origen(plan.lote)],
        plan.distribucion,
        plan.fecha,
        plan.fecha_estimada_de_fin,
        _diferencia(plan.fecha, plan.fecha_estimada_de_fin),
        _fecha_maxima(plan.etapa_destino, plan.fecha),
        plan.prioridad,
        plan.descripcion,
        plan.capataz,
    )


# ---- PROD-PNF-TRN ----


def planificar_transicion(actor, datos):
    """PROD-PNF-TRN: planifica la transición de un lote a la etapa siguiente de su ciclo y devuelve la `TransicionEtapa`.

    - Precondiciones y reglas: ver `_verificar`; la pasada liviana va antes de bloquear y la COMPLETA después (extensión 13).
    - Postcondición a: la orden «a realizar» (`tipo_orden = transicion`, número de la secuencia). Postcondición b: una ocupación por sector
      destino con los agujeros planificados y los ocupados en cero, sin lote. Postcondición c: los agujeros comprometidos de cada sector suben
      (se derivan de las ocupaciones, D-50). Postcondición d: aviso al Capataz, dentro de la transacción (D-42). Postcondiciones e, f y g
      y D-36: UN registro `planificacion_transicion`. La transición no reserva insumos.
    - Bloqueos (docs/patrones/bloqueos.md, sección `produccion`), todos `FOR NO KEY UPDATE`: las cuentas del Agrónomo y del Capataz (en
      orden de id) → el invernadero → la variedad → los sectores destino (en orden de id) → el lote. Un lote con una sola transición «a
      realizar» se garantiza bloqueando el lote ANTES de verificar. `cambio_simultaneo` se evalúa recién con el lote bloqueado.
    - Todo o nada (D-22): si algo falla, no queda nada.
    """
    pronto = _verificar(actor, datos, completo=False)
    sector_ids = sorted({sector_id for sector_id, _ in datos.distribucion if isinstance(sector_id, int)})
    with transaction.atomic():
        capataz_id = pronto.capataz.pk
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, capataz_id}).order_by("pk"))
        _exigir_agronomo_activo(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(
            bloquear_invernadero_activo, pronto.invernadero.pk, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)}
        )
        _bloquear(variedades.bloquear_variedad, pronto.variedad.pk)
        if sector_ids:
            _bloquear(
                api_sectores.bloquear_sectores,
                pronto.invernadero.pk,
                sector_ids,
                equivalencias={"sector_no_disponible": ("sector_no_elegible", "distribucion")},
            )
        Lote.objects.select_for_update(no_key=True).filter(pk=pronto.lote.pk).first()
        plan = _verificar(actor, datos)  # extensión 13: todo de nuevo, con lo bloqueado
        if plan.capataz.pk != capataz_id:
            raise _error("cambio_simultaneo", "Mientras se confirmaba, cambió el Capataz del invernadero. Volvé a intentarlo.")
        return _escribir(actor, plan)


def _escribir(actor, plan):
    """Pasos 13 a 15: crea la orden y las ocupaciones; avisa al Capataz y escribe el único registro de auditoría."""
    hoy = timezone.localdate()
    sectores = [sector for sector, _ in plan.distribucion]
    antes = api_sectores.agujeros_de(sectores)
    orden = TransicionEtapa.objects.create(
        tipo_orden=OrdenTrabajo.Tipo.TRANSICION,
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=hoy,
        fecha_programada_orden=plan.fecha,
        prioridad_orden=plan.prioridad,
        descripcion_orden=plan.descripcion,
        agronomo_id=actor.pk,
        invernadero=plan.invernadero,
        capataz_id=plan.capataz.pk,
        lote=plan.lote,
        etapa_destino_id=plan.etapa_destino.etapa_id,
    )
    ocupaciones = [
        OcupacionSector.objects.create(orden=orden, sector=sector, cant_agujeros_planificados=n) for sector, n in plan.distribucion
    ]
    nombre = actor.get_full_name() or actor.email
    detalle = (
        f"Transición del lote {plan.lote.codigo} ({plan.variedad}) a {plan.etapa_destino.nombre}: {plan.cantidad} plantas para el "
        f"{plan.fecha:%d/%m/%Y} en {plan.invernadero.nombre_invernadero}. La planificó {nombre}."
    )
    notificaciones.notificar(plan.capataz, f"Nueva orden {orden.codigo}", detalle if len(detalle) <= 500 else detalle[:499] + "…")
    datos = {
        "invernadero": referencia(plan.invernadero),
        "lote": referencia(plan.lote),
        "capataz": referencia(plan.capataz),
        "etapa_destino": plan.etapa_destino.nombre,
        "cantidad_actual": str(plan.cantidad),
        "fecha_programada_orden": f"{plan.fecha:%d/%m/%Y}",
    }
    if plan.prioridad:
        datos["prioridad_orden"] = plan.prioridad
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.PLANIFICACION_TRANSICION,
        afectados=[orden, *ocupaciones, *sectores],
        detalle={
            "cambios": {
                "agujeros_comprometidos": {
                    "antes": [f"{s.nombre_sector}: {antes[s.pk].comprometidos}" for s in sectores],
                    "despues": [f"{s.nombre_sector}: {antes[s.pk].comprometidos + n}" for s, n in plan.distribucion],
                }
            },
            "datos": datos,
        },
    )
    return orden


# ============================================================================================================================
# PROD-CNC-TRN · Concretar Transición (paso 5)
# ============================================================================================================================
# - `datos_de_concrecion`: lo que propone el paso 4 (fecha de hoy, lo planificado por sector, con el reparto proporcional si el lote perdió
#   plantas, la fecha mínima y de dónde viene). No escribe ni bloquea.
# - `resumen_de_concrecion`: valida TODO y devuelve el resumen del paso 11. No escribe ni bloquea.
# - `concretar_transicion`: una lectura liviana (permiso y qué bloquear), bloquea en el orden de bloqueos.md (cuentas → invernadero →
#   variedad → sectores destino y de origen, por id y sin repetir → lote → la orden y sus ocupaciones) y recién ENTONCES verifica todo
#   (13b y 13a/13c incluidos). Escribe en este orden: la merma de las plantas sin trasladar (`aplicar_merma`, en la etapa de origen y con
#   la fecha efectiva) → las ocupaciones destino → las de origen en cero → la etapa y la cantidad del lote → la orden → la bitácora de la
#   transición → el aviso al Agrónomo → UN registro de auditoría. Sin asientos ni ejercicio (D-45) y sin movimiento de stock.

LARGO_DE_LA_DESCRIPCION_DE_LA_MERMA = 300
LARGO_DEL_AVISO = 500


@dataclass(frozen=True)
class DatosDeConcrecionDeTransicion:
    """Lo que el Capataz carga en los pasos 5 a 10. `cantidades` es `((sector_id, plantas), ...)` y SOLO lleva los sectores que difieren de
    lo propuesto (paso 8: los demás toman la propuesta). `causa` y `descripcion` valen solo si faltan plantas (extensión 10a). `cantidad` es la
    cantidad actual del lote que la persona vio: si cambió al confirmar, `cambio_simultaneo` con la nueva cantidad y la propuesta
    (extensión 13c); `None` no lo verifica. La vista los arma desde el formulario."""

    fecha_efectiva: date
    cantidades: tuple = ()
    causa: str = ""
    descripcion: str = ""
    cantidad: int | None = None


# Un sector destino de la orden: lo planificado y lo que se propone ubicar (la planificada o su parte proporcional).
FilaDeDestino = namedtuple("FilaDeDestino", "sector_id nombre planificados propuesto")
# Lo que propone el paso 4. `sectores_de_origen` y `distribucion` son listas; `origen_de_la_fecha_minima` es `entrada` o `bitacora`.
PropuestaDeConcrecion = namedtuple(
    "PropuestaDeConcrecion",
    "orden lote variedad etapa_origen etapa_destino cantidad_actual sectores_de_origen distribucion fecha_propuesta fecha_minima "
    "origen_de_la_fecha_minima",
)
# El resumen del paso 11. `distribucion` es `[(sector, planificado, ubicado)]`; `sectores_que_se_liberan`, `[(sector, agujeros)]`.
ResumenDeConcrecion = namedtuple(
    "ResumenDeConcrecion",
    "orden lote variedad etapa_origen etapa_destino fecha_efectiva diferencia_con_la_programada cantidad_actual total_ubicado "
    "plantas_sin_trasladar causa descripcion sectores_que_se_liberan distribucion fecha_maxima_de_cosecha maduracion_vencida",
)
# Todo lo que `_planear_concrecion` resuelve y que `concretar_transicion` usa para escribir.
PlanDeConcrecion = namedtuple(
    "PlanDeConcrecion",
    "orden lote invernadero agronomo variedad etapa_origen etapa_destino destino origen ubicadas total sin_trasladar causa descripcion fecha",
)


def _exigir_capataz_activo(actor):
    """Precondición a: `actor` es un Capataz activo (se lee de la base: pudo darse de baja mientras tanto)."""
    if (
        actor is None
        or rol_de(actor) != Usuario.Rol.CAPATAZ
        or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise _error("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")


def _orden_del_capataz(actor, orden_id):
    """La orden de transición (con lo que se muestra cargado) asignada a `actor`: `sin_permiso` si no es Capataz activo o la orden es
    de otro; `Http404` si no existe o no es una transición. NO verifica el estado de la orden (se hace después de bloquear, 13b)."""
    _exigir_capataz_activo(actor)
    orden = (
        TransicionEtapa.objects.select_related(
            "invernadero__agronomo", "lote__siembra__variedad__cultivo", "lote__etapa__tipo_etapa", "etapa_destino__tipo_etapa"
        )
        .filter(pk=orden_id)
        .first()
    )
    if orden is None:
        raise Http404("No existe esa orden de transición.")
    if orden.capataz_id != actor.pk:
        raise _error("sin_permiso", "Esa orden no está asignada a tu cuenta.")
    return orden


def _ocupaciones_de(orden):
    """`(destino, origen)`: las ocupaciones de la orden (sus sectores destino) y las vigentes del lote (sus sectores de origen), por id."""
    destino = list(OcupacionSector.objects.filter(orden_id=orden.pk).select_related("sector").order_by("pk"))
    origen = list(
        OcupacionSector.objects.filter(lote_id=orden.lote_id, cant_agujeros_ocupados__gt=0).select_related("sector").order_by("pk")
    )
    return destino, origen


def _fecha_minima_con_origen(lote):
    """`(fecha mínima, origen)`: la mayor entre la entrada del lote a su etapa actual y su último registro de bitácora en ella; `origen`
    es `entrada` o `bitacora` según de dónde viene. `(None, "entrada")` si no se conoce ninguna."""
    entrada = api_lotes.fecha_de_entrada_a_la_etapa(lote)
    ultimo = Bitacora.objects.filter(lote=lote, etapa_id=lote.etapa_id).aggregate(f=Max("fecha_bitacora"))["f"]
    if ultimo is not None and (entrada is None or ultimo > entrada):
        return ultimo, "bitacora"
    return entrada, "entrada"


def _exigir_orden_y_lote(orden, lote):
    """Extensiones 13b, 4a y 13a, en este orden: la orden sigue «a realizar»; el lote tiene plantas; y está en la etapa anterior a la
    destino de la orden. Devuelve `(etapa_origen, etapa_destino)` del ciclo."""
    if orden.estado_orden != OrdenTrabajo.Estado.A_REALIZAR:
        raise _error(
            "orden_no_pendiente",
            f"La orden {orden.codigo} ya no está «a realizar»: su estado actual es «{OrdenTrabajo.Estado(orden.estado_orden).label}».",
        )
    if not orden.invernadero.activo:
        raise _error("invernadero_inactivo", "El invernadero está inactivo: no se puede concretar la transición.")
    if lote.estado_lote != Lote.Estado.ACTIVO or lote.cantidad_actual <= 0:
        raise _error(
            "lote_sin_plantas",
            f"El lote {lote.codigo} no tiene plantas: no es posible concretar la transición. El Agrónomo tiene que cancelar la orden.",
        )
    del_ciclo = ciclos.etapas_de([lote.siembra.variedad_id])[lote.siembra.variedad_id]
    posicion = next((i for i, e in enumerate(del_ciclo) if e.etapa_id == lote.etapa_id), None)
    if posicion is None or posicion + 1 >= len(del_ciclo) or del_ciclo[posicion + 1].etapa_id != orden.etapa_destino_id:
        raise _error(
            "cambio_simultaneo",
            f"Mientras cargabas los datos, el lote {lote.codigo} cambió de etapa: ahora está en {lote.etapa.tipo_etapa.nombre_etapa}.",
            datos={"etapa_actual": lote.etapa.tipo_etapa.nombre_etapa},
        )
    return del_ciclo[posicion], del_ciclo[posicion + 1]


def _propuesta_de_ubicacion(lote, destino):
    """Paso 4 y regla «Reparto proporcional»: `{sector_id: plantas}` propuesto: lo planificado, o, si el lote perdió plantas, la cantidad
    actual repartida en proporción (resto mayor)."""
    reparto = repartir_proporcional(lote.cantidad_actual, [o.cant_agujeros_planificados for o in destino])
    return {o.sector_id: n for o, n in zip(destino, reparto)}


def _exigir_cantidad_vista(lote, destino, datos):
    """Extensión 13c: la cantidad actual sigue siendo la que la persona vio; si no, informa la nueva y vuelve a proponer el reparto."""
    if datos.cantidad is not None and datos.cantidad != lote.cantidad_actual:
        propuesta = _propuesta_de_ubicacion(lote, destino)
        raise _error(
            "cambio_simultaneo",
            f"Mientras cargabas los datos, cambió la cantidad del lote {lote.codigo} (por ejemplo, por una merma): ahora tiene "
            f"{lote.cantidad_actual} plantas. Revisá la distribución propuesta.",
            datos={"cantidad_actual": lote.cantidad_actual, "propuesta": list(propuesta.items())},
        )


def _exigir_fecha_efectiva(lote, fecha):
    """Pasos 5 y 6 y extensiones 6a y 6b: entre la fecha mínima y hoy, ambas inclusive. Puede ser anterior a la creación de la orden y a
    la programada."""
    if not isinstance(fecha, date):
        raise _error("fecha_invalida", "Indicá la fecha del traslado.", "fecha_efectiva")
    if fecha > timezone.localdate():
        raise _error("fecha_invalida", "La fecha del traslado no puede ser posterior a hoy.", "fecha_efectiva")
    minima, origen = _fecha_minima_con_origen(lote)
    if minima is not None and fecha < minima:
        de_donde = (
            f"el lote entró a {lote.etapa.tipo_etapa.nombre_etapa} el {minima:%d/%m/%Y}"
            if origen == "entrada"
            else f"el lote tiene un registro en la bitácora del {minima:%d/%m/%Y}"
        )
        raise _error(
            "fecha_invalida",
            f"La fecha del traslado no puede ser anterior al {minima:%d/%m/%Y}: {de_donde}.",
            "fecha_efectiva",
            {"fecha_minima": minima, "origen": origen},
        )


def _ubicadas(destino, lote, datos):
    """Pasos 7 a 10 y extensiones 8a, 10b y 10c: `{sector_id: plantas ubicadas}` (la propuesta, pisada por lo que indicó el Capataz) y su
    total. Cada cantidad es un entero de 0 a lo planificado en ese sector; no se admiten sectores fuera de la orden."""
    ubicadas = _propuesta_de_ubicacion(lote, destino)
    planificados = {o.sector_id: o.cant_agujeros_planificados for o in destino}
    vistos = set()
    for sector_id, plantas in datos.cantidades:
        if sector_id not in planificados:
            raise _error("sector_no_elegible", "Ese sector no es de la distribución planificada de esta orden.", "cantidades")
        if sector_id in vistos or not isinstance(plantas, int) or isinstance(plantas, bool) or plantas < 0:
            raise _error("cantidad_invalida", "Cada sector se indica una sola vez, con un número entero de 0 o más.", "cantidades")
        if plantas > planificados[sector_id]:
            raise _error(
                "cantidad_invalida",
                f"La orden reservó {planificados[sector_id]} agujeros en ese sector: indicá una cantidad menor.",
                "cantidades",
                {"sector": sector_id, "planificado": planificados[sector_id]},
            )
        vistos.add(sector_id)
        ubicadas[sector_id] = plantas
    total = sum(ubicadas.values())
    if total == 0:
        raise _error(
            "cantidad_invalida",
            "No es posible concretar una transición sin plantas trasladadas: corregí las cantidades o pedile al Agrónomo que cancele la orden.",
            "cantidades",
        )
    if total > lote.cantidad_actual:
        raise _error(
            "cantidad_invalida",
            f"El lote tiene {lote.cantidad_actual} plantas y ubicaste {total}: corregí las cantidades.",
            "cantidades",
            {"cantidad_actual": lote.cantidad_actual},
        )
    return ubicadas, total


def _causa_de_la_merma(datos, sin_trasladar):
    """Extensión 10a y regla «Merma de la transición»: si faltan plantas, la causa es obligatoria y de la lista del lote en pie, y la
    descripción tiene hasta 300 caracteres. Devuelve `(causa, descripcion)`; sin plantas perdidas, vacías."""
    if sin_trasladar <= 0:
        return "", ""
    if not datos.causa:
        raise _error("causa_obligatoria", "La causa de las plantas que no se trasladaron es obligatoria.", "causa")
    if datos.causa not in Merma.CAUSAS_EN_PIE:
        raise _error("causa_invalida", "Esa causa no corresponde a un lote en pie.", "causa")
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION_DE_LA_MERMA:
        raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION_DE_LA_MERMA} caracteres.", "descripcion")
    return datos.causa, descripcion


def _planear_concrecion(actor, orden_id, datos):
    """TODAS las verificaciones de PROD-CNC-TRN, en el orden del caso de uso; lee siempre de la base y no escribe. Sirve para el resumen
    (sin bloquear) y, después de bloquear, para la concreción (extensiones 13a a 13c). Devuelve el `PlanDeConcrecion`."""
    orden = _orden_del_capataz(actor, orden_id)
    lote = orden.lote
    etapa_origen, etapa_destino = _exigir_orden_y_lote(orden, lote)
    destino, origen = _ocupaciones_de(orden)
    _exigir_cantidad_vista(lote, destino, datos)
    _exigir_fecha_efectiva(lote, datos.fecha_efectiva)
    ubicadas, total = _ubicadas(destino, lote, datos)
    sin_trasladar = lote.cantidad_actual - total
    causa, descripcion = _causa_de_la_merma(datos, sin_trasladar)
    return PlanDeConcrecion(
        orden, lote, orden.invernadero, orden.invernadero.agronomo, lote.siembra.variedad, etapa_origen, etapa_destino, destino, origen,
        ubicadas, total, sin_trasladar, causa, descripcion, datos.fecha_efectiva,
    )


def _fecha_maxima_de_la_concrecion(plan):
    """Fecha máxima de cosecha estimada: solo si el destino es Maduración, la fecha efectiva más su duración (pasos 11 y 13)."""
    return _fecha_maxima(plan.etapa_destino, plan.fecha)


# ---- Lectura: lo que se propone y el resumen ----


def datos_de_concrecion(actor, orden_id):
    """Paso 4 de PROD-CNC-TRN: lo que propone la pantalla. No escribe ni bloquea. Rechaza una orden que ya no está «a realizar» (13b),
    un lote sin plantas (4a) o que cambió de etapa (13a)."""
    orden = _orden_del_capataz(actor, orden_id)
    lote = orden.lote
    etapa_origen, etapa_destino = _exigir_orden_y_lote(orden, lote)
    destino, origen = _ocupaciones_de(orden)
    propuesta = _propuesta_de_ubicacion(lote, destino)
    minima, de_donde = _fecha_minima_con_origen(lote)
    hoy = timezone.localdate()
    return PropuestaDeConcrecion(
        orden,
        lote,
        lote.siembra.variedad,
        etapa_origen,
        etapa_destino,
        lote.cantidad_actual,
        [(o.sector, o.cant_agujeros_ocupados) for o in origen],
        [FilaDeDestino(o.sector_id, o.sector.nombre_sector, o.cant_agujeros_planificados, propuesta[o.sector_id]) for o in destino],
        hoy,
        minima,
        de_donde,
    )


def resumen_de_concrecion(actor, orden_id, datos):
    """Paso 11: valida TODO (los mismos rechazos que `concretar_transicion`) y devuelve el resumen. No escribe ni bloquea: lo que se
    presenta puede cambiar hasta la confirmación, que lo vuelve a verificar (extensiones 13a a 13c)."""
    plan = _planear_concrecion(actor, orden_id, datos)
    maxima = _fecha_maxima_de_la_concrecion(plan)
    return ResumenDeConcrecion(
        plan.orden,
        plan.lote,
        plan.variedad,
        plan.etapa_origen,
        plan.etapa_destino,
        plan.fecha,
        (plan.fecha - plan.orden.fecha_programada_orden).days,
        plan.lote.cantidad_actual,
        plan.total,
        plan.sin_trasladar,
        plan.causa,
        plan.descripcion,
        [(o.sector, o.cant_agujeros_ocupados) for o in plan.origen],
        [(o.sector, o.cant_agujeros_planificados, plan.ubicadas[o.sector_id]) for o in plan.destino],
        maxima,
        maxima is not None and maxima < timezone.localdate(),
    )


# ---- PROD-CNC-TRN ----


def concretar_transicion(actor, orden_id, datos):
    """PROD-CNC-TRN: concreta una orden de transición y devuelve la `TransicionEtapa` concretada.

    - Precondición a y requisito especial: Capataz activo asignado a la orden (`sin_permiso`). Las precondiciones c y d (ejercicio y
      cuentas contables) no existen en la ronda (D-45).
    - Verificaciones, DESPUÉS de bloquear: `orden_no_pendiente` (13b), `lote_sin_plantas` (4a), `cambio_simultaneo` (13a y 13c), la fecha
      efectiva (6a y 6b), las cantidades (8a, 10b y 10c) y la causa de la merma (10a).
    - Postcondición a: la orden «concretada», con fecha de resolución = hoy, fecha efectiva y cantidad transferida = el total ubicado.
      Postcondición b: el lote pasa a la etapa destino con la cantidad ubicada. c y d: ocupaciones destino con los agujeros ocupados
      (con lote las que tienen plantas) y las de origen en cero (conservan el lote). e y f: los agujeros de cada sector se actualizan (se
      derivan de las ocupaciones, D-50). g: registro de bitácora de la transición. h e i: si faltan plantas, la merma (`aplicar_merma`,
      en la etapa de origen y con la fecha efectiva) y sus alertas. j: aviso al Agrónomo a cargo, dentro de la transacción (D-42). k, l y
      m y D-36: UN registro `concrecion_transicion` con todo, incluida la merma.
    - Bloqueos (docs/patrones/bloqueos.md, sección `produccion`), todos `FOR NO KEY UPDATE`: las cuentas del Capataz y del Agrónomo (en
      orden de id) → el invernadero → la variedad → los sectores destino y de origen (por id, sin repetir) → el lote → la orden y las
      ocupaciones. Lo que se leyó antes de bloquear se relee: si cambió, `cambio_simultaneo`.
    - Todo o nada (D-22), incluida la merma que la extiende.
    """
    orden = _orden_del_capataz(actor, orden_id)
    destino, origen = _ocupaciones_de(orden)
    sector_ids = sorted({o.sector_id for o in destino} | {o.sector_id for o in origen})
    with transaction.atomic():
        cuentas = {actor.pk, *([orden.invernadero.agronomo_id] if orden.invernadero.agronomo_id else [])}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        _exigir_capataz_activo(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(
            bloquear_invernadero_activo, orden.invernadero_id, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)}
        )
        _bloquear(variedades.bloquear_variedad, orden.lote.siembra.variedad_id)
        _bloquear(
            api_sectores.bloquear_sectores,
            orden.invernadero_id,
            sector_ids,
            equivalencias={"sector_no_disponible": ("cambio_simultaneo", None)},
        )
        Lote.objects.select_for_update(no_key=True).filter(pk=orden.lote_id).first()
        OrdenTrabajo.objects.select_for_update(no_key=True).filter(pk=orden.pk).first()
        list(
            OcupacionSector.objects.select_for_update(no_key=True)
            .filter(Q(orden_id=orden.pk) | Q(lote_id=orden.lote_id))
            .order_by("pk")
        )
        plan = _planear_concrecion(actor, orden_id, datos)  # 13a a 13c: todo de nuevo, con lo bloqueado
        if not {o.sector_id for o in plan.destino} | {o.sector_id for o in plan.origen} <= set(sector_ids):
            raise _error("cambio_simultaneo", "Mientras cargabas los datos, cambiaron los sectores del lote. Volvé a abrir la orden.")
        return _escribir_concrecion(actor, plan)


def _texto_del_aviso(plan, orden):
    """Postcondición j: el texto del aviso al Agrónomo con lo planificado y lo realizado por sector, las plantas perdidas y su causa, y la
    fecha efectiva frente a la programada; avisa si es anterior a la creación de la orden. Hasta 500 caracteres: si no entra, se acorta con
    «…» la lista de sectores (lo demás va completo)."""
    cabeza = f"El lote {plan.lote.codigo} ({plan.variedad}) pasó a {plan.etapa_destino.nombre} el {plan.fecha:%d/%m/%Y}."
    sectores = " Sectores (planificado → realizado): " + "; ".join(
        f"{o.sector.nombre_sector} {o.cant_agujeros_planificados} → {plan.ubicadas[o.sector_id]}" for o in plan.destino
    ) + "."
    cola = ""
    if plan.sin_trasladar:
        cola += f" Plantas perdidas: {plan.sin_trasladar} ({Merma.Causa(plan.causa).label.lower()})."
    cola += f" Programada para el {orden.fecha_programada_orden:%d/%m/%Y}."
    if plan.fecha < orden.fecha_creacion_orden:
        cola += f" La fecha del traslado es anterior a la creación de la orden ({orden.fecha_creacion_orden:%d/%m/%Y})."
    sobra = len(cabeza) + len(sectores) + len(cola) - LARGO_DEL_AVISO
    if sobra > 0:
        sectores = sectores[: max(0, len(sectores) - sobra - 1)] + "…"
    return (cabeza + sectores + cola)[:LARGO_DEL_AVISO]


def _escribir_concrecion(actor, plan):
    """Pasos 13 a 15: escribe en el orden del caso de uso, avisa al Agrónomo y registra la auditoría única."""
    hoy = timezone.localdate()
    orden, lote = plan.orden, plan.lote
    sectores = [o.sector for o in plan.destino] + [o.sector for o in plan.origen]
    ocupados_antes = {pk: a.ocupados for pk, a in api_sectores.agujeros_de(sectores).items()}
    cantidad_antes, costo_antes = lote.cantidad_actual, Decimal(lote.costo_acumulado)
    # 1. La merma, antes del traslado: queda en la etapa de origen y con la fecha efectiva; la orden que se concreta no cuenta para las
    #    plantas comprometidas (extensión 10a de PROD-REG-MRM).
    resultado = None
    if plan.sin_trasladar:
        resultado = mermas.aplicar_merma(
            lote, plan.sin_trasladar, plan.causa, plan.descripcion, plan.fecha, actor, ordenes_excluidas=(orden.pk,)
        )
    # 2. Ocupaciones destino (con lote las que tienen plantas) y 3. las de origen en cero, que conservan su lote.
    for ocupacion in plan.destino:
        ocupacion.cant_agujeros_ocupados = plan.ubicadas[ocupacion.sector_id]
        ocupacion.lote = lote if ocupacion.cant_agujeros_ocupados else None
        ocupacion.save(update_fields=["cant_agujeros_ocupados", "lote"])
    for ocupacion in plan.origen:
        ocupacion.cant_agujeros_ocupados = 0
        ocupacion.save(update_fields=["cant_agujeros_ocupados"])
    # 4. La etapa del lote (la cantidad actual ya es el total ubicado: la bajó la merma).
    lote.etapa_id = plan.etapa_destino.etapa_id
    Lote.objects.filter(pk=lote.pk).update(etapa_id=lote.etapa_id)
    # 5. La bitácora de la transición y 6. la orden, que la enlaza.
    bitacora = Bitacora.objects.create(
        invernadero_id=lote.invernadero_id,
        lote=lote,
        etapa_id=plan.etapa_destino.etapa_id,
        responsable=actor,
        fecha_bitacora=plan.fecha,
        hora_bitacora=timezone.localtime().time(),
        tipo_evento=Bitacora.TipoEvento.TRANSICION,
        descripcion_evento=f"Transición del lote {lote.codigo} a {plan.etapa_destino.nombre}: {mermas.plantas(plan.total)}.",
    )
    bitacora.sectores.set([o.sector_id for o in plan.destino if plan.ubicadas[o.sector_id] > 0])
    orden.estado_orden = OrdenTrabajo.Estado.CONCRETADA
    orden.fecha_resolucion_orden = hoy
    orden.cant_transferido = plan.total
    orden.fecha_transicion = plan.fecha
    orden.bitacora_de_transicion = bitacora
    orden.save(update_fields=["estado_orden", "fecha_resolucion_orden", "cant_transferido", "fecha_transicion", "bitacora_de_transicion"])
    # 7. El aviso al Agrónomo a cargo (si hay uno activo), dentro de la transacción (D-42).
    if plan.agronomo is not None and plan.agronomo.is_active and plan.agronomo.pk != actor.pk:
        notificaciones.notificar(plan.agronomo, f"Transición concretada: {orden.codigo}", _texto_del_aviso(plan, orden))
    # 8. Un solo registro de auditoría con todo, incluida la merma y sus alertas (D-36).
    despues = {pk: a.ocupados for pk, a in api_sectores.agujeros_de(sectores).items()}
    cambios = {
        "estado": {"antes": OrdenTrabajo.Estado.A_REALIZAR.value, "despues": OrdenTrabajo.Estado.CONCRETADA.value},
        "fecha_resolucion_orden": {"antes": None, "despues": f"{hoy:%d/%m/%Y}"},
        "fecha_transicion": {"antes": None, "despues": f"{plan.fecha:%d/%m/%Y}"},
        "cantidad_transferida": {"antes": None, "despues": str(plan.total)},
        "etapa": {"antes": plan.etapa_origen.nombre, "despues": plan.etapa_destino.nombre},
        "agujeros_ocupados": {
            "antes": [f"{s.nombre_sector}: {ocupados_antes[s.pk]}" for s in sectores],
            "despues": [f"{s.nombre_sector}: {despues[s.pk]}" for s in sectores],
        },
    }
    if resultado is not None:  # D-36: solo lo que cambió (sin merma, la cantidad y el costo del lote no cambian)
        cambios["cantidad_actual"] = {"antes": str(cantidad_antes), "despues": str(lote.cantidad_actual)}
        cambios["costo_acumulado"] = {"antes": str(costo_antes), "despues": str(lote.costo_acumulado)}
    datos_de_auditoria = {"invernadero": referencia(plan.invernadero), "lote": referencia(lote)}
    afectados = [orden, lote, bitacora, *plan.destino, *plan.origen, *sectores]
    if resultado is not None:
        datos_de_auditoria["merma"] = referencia(resultado.merma)
        datos_de_auditoria["causa_merma"] = Merma.Causa(plan.causa).label
        afectados += [resultado.merma, *resultado.alertas]
        if resultado.alertas:
            datos_de_auditoria["alertas_creadas"] = [referencia(a) for a in resultado.alertas]
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.CONCRECION_TRANSICION,
        afectados=afectados,
        detalle={"cambios": cambios, "datos": datos_de_auditoria},
    )
    return orden
