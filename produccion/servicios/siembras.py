# Servicios de siembra de `produccion` (PRD-01): PROD-PNF-SMB · Planificar Siembra (paso 5) y PROD-CNC-SMB · Concretar Siembra (paso 6, al final).
# Fuente: docs/casos_de_uso/produccion/siembra.md (casos y «Decisiones de aplicación»), docs/api/produccion.md, docs/patrones/bloqueos.md
# (sección `produccion`), docs/patrones/stock.md (sección 5) y D-22, D-30, D-32, D-36, D-40, D-42, D-45, D-50, D-52 y D-53.
#
# PLANIFICAR. Un caso de uso es una función de servicio dentro de `transaction.atomic()` (D-22); las vistas solo orquestan.
# - `datos_de_planificacion`: lo que presentan los pasos 2 a 12. No escribe.
# - `resumen_de_planificacion`: valida TODO y devuelve el resumen del paso 16. No escribe ni bloquea.
# - `planificar_siembra`: valida, bloquea en el orden de bloqueos.md (cuentas → invernadero → variedad → sectores → insumos → filas
#   propias), VUELVE A VERIFICAR TODO bajo bloqueo (extensión 18b) y recién entonces escribe: la orden, sus ocupaciones, sus reservas, el
#   aviso al Capataz y un único registro de auditoría. Sin asientos ni ejercicio (D-45).
# Todos los rechazos de negocio son `ErrorDeProduccion(codigo, mensaje, campo)`; los textos están en voseo rioplatense.

from collections import defaultdict, namedtuple
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, ciclos, stock, variedades
from inventario.unidades import Unidad, validar_cantidad
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Consumo, Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra
from produccion.servicios import consumos as consumos_de_reserva
from produccion.servicios import costos
from produccion.servicios import lotes as api_lotes
from produccion.servicios import ordenes
from produccion.servicios.bloqueos import traducir as _bloquear

Estado = OrdenTrabajo.Estado
LARGO_DE_LA_DESCRIPCION = 500
PRIORIDADES = ("alta", "media", "baja")
# Cómo se llama cada variable ambiental en los mensajes (los nombres de campo de `inventario.servicios.variedades.Rangos`).
NOMBRE_DE_LA_VARIABLE = {
    "temp_ambiente": "temperatura ambiente",
    "humedad": "humedad",
    "intensidad_luz": "intensidad lumínica",
    "fotoperiodo": "fotoperíodo",
}


# ---- Lo que recibe y lo que devuelve ----


@dataclass(frozen=True)
class DatosDeSiembra:
    """Lo que el Agrónomo carga en los pasos 3 a 15. `distribucion` es `((sector_id, plantines), ...)` e `insumos_adicionales`,
    `((existencia_id, cantidad), ...)`, con `existencia_id` el id del `InsumoInvernadero`. La vista los arma desde el formulario."""

    invernadero_id: int
    variedad_id: int
    cantidad: int
    fecha_programada: date
    distribucion: tuple = ()
    prioridad: str | None = None
    descripcion: str = ""
    insumos_adicionales: tuple = ()


# El resumen del paso 16. `distribucion` es `[(sector, plantines)]`; `reservas`, `[ReservaPrevista]` (la semilla primero).
ResumenDePlanificacion = namedtuple(
    "ResumenDePlanificacion",
    "invernadero variedad cantidad fecha_programada fecha_estimada_de_cosecha prioridad descripcion capataz distribucion reservas",
)
ReservaPrevista = namedtuple("ReservaPrevista", "existencia nombre unidad cantidad")
# Lo que presenta la pantalla de «Nueva siembra» (pasos 2, 4, 9 y 12).
DatosDePlanificacion = namedtuple("DatosDePlanificacion", "invernaderos variedades sectores insumos_adicionales")
InvernaderoOfrecido = namedtuple("InvernaderoOfrecido", "invernadero_id nombre capataz_nombre motivo")
VariedadOfrecida = namedtuple(
    "VariedadOfrecida", "variedad_id nombre perfil duracion_dias stock_libre compatible conflictos motivo"
)
Conflicto = namedtuple("Conflicto", "variable texto")
SectorOfrecido = namedtuple("SectorOfrecido", "sector_id nombre libres")
InsumoAdicional = namedtuple("InsumoAdicional", "existencia_id nombre unidad stock_libre")
# Todo lo que `_verificar` resuelve y que `planificar_siembra` usa para escribir.
Plan = namedtuple(
    "Plan",
    "invernadero capataz variedad semilla existencia_semilla adicionales sectores distribucion cantidad fecha prioridad descripcion",
)


# ---- Errores y traducciones ----


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


def _plural(cantidad, singular, plural):
    """«1 plantín» o «3 plantines»."""
    return f"{cantidad} {singular if cantidad == 1 else plural}"


# ---- Verificaciones (se hacen dos veces: antes de bloquear y después, extensión 18b) ----


def _exigir_agronomo_activo(actor):
    """Precondición a: `actor` es un Agrónomo activo (se lee de la base: pudo darse de baja mientras tanto)."""
    if (
        actor is None
        or rol_de(actor) != Usuario.Rol.AGRONOMO
        or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise _error("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")


def _invernadero_a_cargo(actor, invernadero_id):
    """Precondiciones a y b: el invernadero existe, está a cargo de `actor` y está activo."""
    invernadero = Invernadero.objects.select_related("capataz").filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if invernadero.agronomo_id != actor.pk:
        raise _error("sin_permiso", "Ese invernadero no está a tu cargo.")
    if not invernadero.activo:
        raise _error("invernadero_inactivo", "El invernadero está inactivo: no se puede planificar una siembra en él.")
    return invernadero


def _capataz_activo(invernadero):
    """Extensión 3a: el invernadero tiene un Capataz activo que pueda recibir la orden."""
    capataz = invernadero.capataz
    if capataz is None or not capataz.is_active:
        raise _error(
            "sin_capataz_activo",
            "No hay un Capataz activo asignado a este invernadero que pueda recibir la orden: pedile al Gerente que lo asigne.",
        )
    return capataz


def _conflictos(invernadero_id, incompatibles, nombres_por_variedad=None):
    """Una `Conflicto` por cada variable no compatible, con los lotes activos y las órdenes «a realizar» con las que choca (paso 4 y
    extensión 5a). `nombres_por_variedad` (`{variedad_id: [códigos]}`) se calcula una vez cuando hay muchas variedades."""
    if nombres_por_variedad is None:
        nombres_por_variedad = _codigos_presentes(invernadero_id)
    todos = [codigo for codigos in nombres_por_variedad.values() for codigo in codigos]
    conflictos = []
    for incompatible in incompatibles:
        referencias = nombres_por_variedad.get(incompatible.variedad_limitante_id, []) if incompatible.variedad_limitante_id else todos
        nombre = NOMBRE_DE_LA_VARIABLE[incompatible.variable]
        texto = f"{nombre}: choca con {', '.join(referencias)}" if referencias else nombre
        conflictos.append(Conflicto(incompatible.variable, texto))
    return conflictos


def _codigos_presentes(invernadero_id):
    """`{variedad_id: [códigos]}` de los lotes activos y de las siembras «a realizar» del invernadero (dos consultas)."""
    por_variedad = defaultdict(list)
    for lote in Lote.objects.filter(invernadero_id=invernadero_id, estado_lote=Lote.Estado.ACTIVO).select_related("siembra").order_by("id"):
        por_variedad[lote.siembra.variedad_id].append(lote.codigo)
    for siembra in Siembra.objects.filter(invernadero_id=invernadero_id, estado_orden=Estado.A_REALIZAR).order_by("id"):
        por_variedad[siembra.variedad_id].append(siembra.codigo)
    return por_variedad


def _exigir_compatible(invernadero, variedad):
    """Regla «Umbral efectivo» (pasos 4 y 5; extensiones 4a y 5a): la variedad es compatible si, al sumarla, ninguna intersección
    queda vacía. El cálculo es de `inventario` (una sola función, también la usa el IoT)."""
    umbral = variedades.umbral_efectivo([invernadero.pk])[invernadero.pk]
    incompatibles = variedades.variables_incompatibles(umbral, variedades.rangos_de([variedad.pk])[variedad.pk])
    if incompatibles:
        detalle = "; ".join(c.texto for c in _conflictos(invernadero.pk, incompatibles))
        raise _error(
            "variedad_incompatible",
            f"{variedad} no es compatible con las condiciones del invernadero. Variables en conflicto: {detalle}.",
            "variedad",
        )


def _totales_por_etapa(invernadero_id):
    """`{tipo_etapa_id: agujeros totales}` de los sectores activos o fuera de servicio (los inactivos no cuentan; los fuera de servicio
    sí, aunque no se ofrezcan para ubicar plantas): regla «Capacidad por etapa»."""
    totales = defaultdict(int)
    for tipo_id, total in SectorProduccion.objects.filter(
        invernadero_id=invernadero_id,
        estado_sector__in=[SectorProduccion.Estado.ACTIVO, SectorProduccion.Estado.FUERA_DE_SERVICIO],
    ).values_list("tipo_etapa_id", "cant_agujeros_total"):
        totales[tipo_id] += total
    return totales


def _etapas_sin_sector(invernadero_id, variedad):
    """Las etapas del ciclo de la variedad a las que el invernadero no les da un sector activo o fuera de servicio (extensión 5c)."""
    totales = _totales_por_etapa(invernadero_id)
    return [e for e in ciclos.etapas_de([variedad.pk])[variedad.pk] if totales.get(e.tipo_id, 0) == 0]


def _exigir_capacidad_por_etapa(invernadero, variedad, cantidad):
    """Extensiones 5c y 8d: un sector de cada etapa del ciclo, y que la cantidad no supere los agujeros de esos sectores en ninguna."""
    faltan = _etapas_sin_sector(invernadero.pk, variedad)
    if faltan:
        nombres = ", ".join(e.nombre for e in faltan)
        raise _error(
            "capacidad_insuficiente",
            f"El invernadero no tiene sectores activos ni fuera de servicio para: {nombres}. No se puede planificar una siembra de "
            f"{variedad} acá.",
            "variedad",
        )
    totales = _totales_por_etapa(invernadero.pk)
    por_etapa = [(e, totales[e.tipo_id]) for e in ciclos.etapas_de([variedad.pk])[variedad.pk]]
    for etapa, total in por_etapa:
        if cantidad > total:
            maximo = min(t for _, t in por_etapa)
            raise _error(
                "capacidad_insuficiente",
                f"En {etapa.nombre} entran como máximo {total} plantines. Con esta variedad, el invernadero admite hasta {maximo}.",
                "cantidad",
            )


def _sectores_de_germinacion(invernadero_id, variedad):
    """Los sectores de germinación ACTIVOS compatibles con el perfil familiar de la variedad, con sus agujeros (regla «Compatibilidad
    por perfil familiar»; paso 9): `{sector_id: (sector, Agujeros)}`. Los fuera de servicio no se ofrecen."""
    sectores = list(
        SectorProduccion.objects.filter(
            invernadero_id=invernadero_id,
            estado_sector=SectorProduccion.Estado.ACTIVO,
            tipo_etapa__codigo="germinacion",
        )
        .select_related("tipo_etapa")
        .order_by("id")
    )
    agujeros = api_sectores.agujeros_de(sectores)
    perfiles = api_lotes.perfil_de_sector([s.pk for s in sectores])
    return {
        s.pk: (s, agujeros[s.pk]) for s in sectores if perfiles[s.pk] in (None, variedad.perfil_familia)
    }


def _exigir_lugar_en_germinacion(candidatos, cantidad):
    """Extensiones 5b y 8e: algún sector de germinación compatible con lugar, y que la cantidad no supere el lugar total."""
    libre_total = sum(max(0, a.libres) for _, a in candidatos.values())
    if libre_total == 0:
        raise _error(
            "capacidad_insuficiente", "No hay sectores de germinación compatibles con ese perfil familiar y con lugar libre.", "variedad"
        )
    if cantidad > libre_total:
        raise _error(
            "capacidad_insuficiente",
            f"La capacidad libre de germinación es de {libre_total} plantines: reducí la cantidad.",
            "cantidad",
        )


def _distribucion_valida(distribucion, cantidad, candidatos):
    """Pasos 10 y 11 y extensiones 11a y 11b: cada sector es uno que se ofrece, con una cantidad entera positiva que entra en su
    capacidad libre, y todo suma exactamente la cantidad de plantines. Devuelve `[(sector, plantines)]`."""
    vistos, resultado = set(), []
    for par in distribucion:
        sector_id, plantines = par
        if sector_id not in candidatos:
            raise _error("sector_no_elegible", "Ese sector no se puede elegir: tiene que ser un sector de germinación activo, compatible y de este invernadero.", "distribucion")
        if sector_id in vistos or not isinstance(plantines, int) or isinstance(plantines, bool) or plantines <= 0:
            raise _error("cantidad_invalida", "Cada sector se usa una sola vez y con una cantidad entera mayor que cero.", "distribucion")
        sector, agujeros = candidatos[sector_id]
        if plantines > agujeros.libres:
            raise _error(
                "capacidad_insuficiente",
                f"El sector {sector.nombre_sector} tiene {max(0, agujeros.libres)} agujeros libres: indicá una cantidad menor o elegí otro sector.",
                "distribucion",
            )
        vistos.add(sector_id)
        resultado.append((sector, plantines))
    total = sum(n for _, n in resultado)
    if total != cantidad:
        quedan = cantidad - total
        detalle = f"faltan ubicar {quedan}" if quedan > 0 else f"te pasaste por {-quedan}"
        raise _error("distribucion_incompleta", f"La distribución tiene que sumar {cantidad} plantines: {detalle}.", "distribucion")
    return resultado


def _semilla_habilitada(invernadero, variedad):
    """Extensión 8b: la semilla de la variedad está habilitada (activa) en el invernadero. Devuelve `(semilla, existencia)`."""
    semilla = variedades.semilla_de([variedad.pk])[variedad.pk]
    existencia = InsumoInvernadero.objects.filter(
        insumo=semilla, invernadero=invernadero, estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO
    ).first()
    if existencia is None:
        raise _error(
            "semilla_no_habilitada",
            f"La semilla de {variedad} no está habilitada en este invernadero. Habilitala para poder planificar la siembra.",
            "variedad",
            # Extensión 8b: la pantalla enlaza a CMP-HAB-IIN con la semilla y el invernadero ya elegidos.
            datos={"semilla_id": semilla.pk, "invernadero_id": invernadero.pk},
        )
    return semilla, existencia


def _insumos_adicionales(invernadero, adicionales, fecha):
    """Pasos 12 a 14 y regla «Insumos adicionales»: insumos activos del mismo invernadero fuera de las categorías del sistema, con una
    cantidad válida para su unidad y dentro del stock libre. Devuelve `[(existencia, cantidad)]`."""
    resultado, vistos = [], set()
    for existencia_id, cantidad in adicionales:
        existencia = (
            InsumoInvernadero.objects.select_related("insumo__tipo_insumo")
            .filter(pk=existencia_id, invernadero=invernadero, estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO)
            .first()
        )
        if (
            existencia is None
            or not existencia.insumo.activo
            or existencia.insumo.tipo_insumo.es_del_sistema
            or existencia_id in vistos
        ):
            raise _error(
                "insumo_no_elegible",
                "Ese insumo no se puede reservar como adicional: tiene que estar activo en este invernadero, no repetirse y no ser "
                "de las categorías del sistema (semillas, envases, repuestos de hardware e infraestructura).",
                "insumos_adicionales",
            )
        try:
            cantidad = validar_cantidad(cantidad, existencia.insumo.unidad_medida_insumo)
        except ValidationError as error:
            raise _error("cantidad_invalida", " ".join(error.messages), "insumos_adicionales") from error
        if cantidad <= 0:
            raise _error("cantidad_invalida", "La cantidad de cada insumo adicional tiene que ser mayor que cero.", "insumos_adicionales")
        vistos.add(existencia_id)
        resultado.append((existencia, cantidad))
    if resultado:
        libres = stock.disponible_para_planificar([e.pk for e, _ in resultado], fecha)
        for existencia, cantidad in resultado:
            if cantidad > libres[existencia.pk]:
                raise _error(
                    "stock_insuficiente",
                    f"El stock libre de {existencia.insumo.nombre_insumo} es {libres[existencia.pk].normalize():f}: corregí la cantidad o quitá el insumo.",
                    "insumos_adicionales",
                )
    return resultado


def _verificar(actor, datos):
    """TODAS las verificaciones de PROD-PNF-SMB, en el orden del caso de uso. Lee siempre de la base, así que sirve igual antes de
    bloquear (rechazar pronto y saber qué bloquear: `resumen_de_planificacion`) y después de bloquear (extensión 18b). No escribe.
    Devuelve el `Plan`; el primer rechazo es un `ErrorDeProduccion`."""
    _exigir_agronomo_activo(actor)
    invernadero = _invernadero_a_cargo(actor, datos.invernadero_id)
    capataz = _capataz_activo(invernadero)
    cantidad, fecha = datos.cantidad, datos.fecha_programada
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad <= 0:
        raise _error("cantidad_invalida", "La cantidad de plantines tiene que ser un número entero mayor que cero.", "cantidad")
    if not isinstance(fecha, date):
        raise _error("fecha_invalida", "Indicá la fecha programada.", "fecha_programada")
    prioridad = datos.prioridad or None
    if prioridad is not None and prioridad not in PRIORIDADES:
        raise _error("prioridad_invalida", "La prioridad tiene que ser alta, media o baja.", "prioridad")
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    variedad = variedades.obtener_variedad(datos.variedad_id)
    if not variedad.activa or not variedad.cultivo.activo:
        raise _error("variedad_inactiva", "La variedad está inactiva: elegí otra.", "variedad")
    _exigir_compatible(invernadero, variedad)
    _exigir_capacidad_por_etapa(invernadero, variedad, 0)  # 5c: ¿hay un sector de cada etapa?
    if fecha < stock.hoy():
        raise _error("fecha_invalida", "La fecha programada no puede ser anterior a hoy.", "fecha_programada")
    semilla, existencia_semilla = _semilla_habilitada(invernadero, variedad)
    libre = stock.disponible_para_planificar([existencia_semilla.pk], fecha)[existencia_semilla.pk]
    if cantidad > libre:
        raise _error(
            "stock_insuficiente",
            f"El stock libre de la semilla de {variedad} a esa fecha es {libre.normalize():f}: reducí la cantidad o elegí otra variedad.",
            "cantidad",
        )
    _exigir_capacidad_por_etapa(invernadero, variedad, cantidad)  # 8d
    candidatos = _sectores_de_germinacion(invernadero.pk, variedad)
    _exigir_lugar_en_germinacion(candidatos, cantidad)  # 5b y 8e
    distribucion = _distribucion_valida(datos.distribucion, cantidad, candidatos)
    adicionales = _insumos_adicionales(invernadero, datos.insumos_adicionales, fecha)
    plan = Plan(
        invernadero, capataz, variedad, semilla, existencia_semilla, adicionales, candidatos, distribucion, cantidad, fecha, prioridad, descripcion
    )
    _exigir_que_no_sea_duplicada(actor, plan)
    return plan


def _exigir_que_no_sea_duplicada(actor, plan):
    """Extensión 18a: no hay ya una orden «a realizar» con los mismos valores en todos sus atributos (sin el identificador)."""
    existentes = Siembra.objects.filter(
        invernadero=plan.invernadero,
        variedad=plan.variedad,
        cant_plantines_siembra=plan.cantidad,
        fecha_programada_orden=plan.fecha,
        prioridad_orden=plan.prioridad,
        descripcion_orden=plan.descripcion,
        fecha_creacion_orden=stock.hoy(),
        agronomo_id=actor.pk,
        capataz_id=plan.capataz.pk,
        estado_orden=Estado.A_REALIZAR,
    ).prefetch_related("ocupaciones", "reservas")
    distribucion = {(sector.pk, n) for sector, n in plan.distribucion}
    reservas = {(plan.existencia_semilla.pk, Decimal(plan.cantidad))} | {(e.pk, c) for e, c in plan.adicionales}
    for existente in existentes:
        mismas_ocupaciones = {(o.sector_id, o.cant_agujeros_planificados) for o in existente.ocupaciones.all()} == distribucion
        mismas_reservas = {(r.insumo_invernadero_id, r.cantidad_reservada) for r in existente.reservas.all()} == reservas
        if mismas_ocupaciones and mismas_reservas:
            raise _error("orden_duplicada", f"Ya existe una orden idéntica: {existente.codigo}.")


# ---- Lectura ----


def datos_de_planificacion(actor, invernadero_id=None, variedad_id=None, fecha=None):
    """Lo que presentan los pasos 2 a 12 de PROD-PNF-SMB. No escribe ni bloquea.

    - Siempre: los invernaderos activos a cargo del Agrónomo (paso 2), cada uno con el motivo por el que no se puede elegir, si lo hay
      (extensiones 3a y 3b).
    - Con `invernadero_id`: las variedades activas con su perfil, la duración del ciclo, el stock libre de su semilla y su
      compatibilidad (paso 4; extensiones 4a, 5a y 5c), y los insumos adicionales con su stock libre (paso 12).
    - Con `variedad_id` además: los sectores de germinación que se ofrecen (paso 9).
    """
    _exigir_agronomo_activo(actor)
    fecha = fecha or stock.hoy()
    activos = list(Invernadero.objects.en_alcance_de(actor).select_related("capataz").order_by("nombre_invernadero", "id"))
    invernaderos = _invernaderos_ofrecidos(activos)
    variedades_ofrecidas, sectores, adicionales = [], [], []
    if invernadero_id is not None:
        invernadero = _invernadero_a_cargo(actor, invernadero_id)
        variedades_ofrecidas = _variedades_ofrecidas(invernadero, fecha)
        adicionales = _adicionales_ofrecidos(invernadero, fecha)
        if variedad_id is not None:
            variedad = variedades.obtener_variedad(variedad_id)
            sectores = [
                SectorOfrecido(s.pk, s.nombre_sector, a.libres)
                for s, a in _sectores_de_germinacion(invernadero.pk, variedad).values()
                if a.libres > 0
            ]
    return DatosDePlanificacion(invernaderos, variedades_ofrecidas, sectores, adicionales)


def _invernaderos_ofrecidos(activos):
    """Paso 2: cada invernadero con su motivo si no se puede elegir (3a: sin Capataz activo; 3b: sin lugar en germinación)."""
    sectores = list(
        SectorProduccion.objects.filter(
            invernadero__in=activos, estado_sector=SectorProduccion.Estado.ACTIVO, tipo_etapa__codigo="germinacion"
        )
    )
    libres = defaultdict(int)
    agujeros = api_sectores.agujeros_de(sectores)
    for sector in sectores:
        libres[sector.invernadero_id] += max(0, agujeros[sector.pk].libres)
    ofrecidos = []
    for invernadero in activos:
        capataz = invernadero.capataz
        motivo = None
        if capataz is None or not capataz.is_active:
            motivo = "No tiene un Capataz activo que pueda recibir la orden."
        elif libres[invernadero.pk] == 0:
            motivo = "No hay espacio de germinación libre en este invernadero."
        ofrecidos.append(
            InvernaderoOfrecido(
                invernadero.pk, invernadero.nombre_invernadero, capataz.get_full_name() or capataz.email if capataz else None, motivo
            )
        )
    return ofrecidos


def _variedades_ofrecidas(invernadero, fecha):
    """Paso 4: las variedades activas de cultivos activos con lo que hace falta para elegir (consultas fijas, no por variedad)."""
    activas = list(variedades.variedades_activas())
    ids = [v.pk for v in activas]
    if not ids:
        return []
    duracion = ciclos.duracion_del_ciclo(ids)
    rangos = variedades.rangos_de(ids)
    semillas = variedades.semilla_de(ids)
    existencias = {
        e.insumo_id: e
        for e in InsumoInvernadero.objects.filter(
            invernadero=invernadero,
            insumo_id__in=[s.pk for s in semillas.values()],
            estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO,
        )
    }
    libres = stock.disponible_para_planificar([e.pk for e in existencias.values()], fecha) if existencias else {}
    umbral = variedades.umbral_efectivo([invernadero.pk])[invernadero.pk]
    presentes = _codigos_presentes(invernadero.pk)
    totales = _totales_por_etapa(invernadero.pk)
    etapas = ciclos.etapas_de(ids)
    ofrecidas = []
    for variedad in activas:
        existencia = existencias.get(semillas[variedad.pk].pk)
        conflictos = _conflictos(invernadero.pk, variedades.variables_incompatibles(umbral, rangos[variedad.pk]), presentes)
        faltan = [e.nombre for e in etapas[variedad.pk] if totales.get(e.tipo_id, 0) == 0]
        ofrecidas.append(
            VariedadOfrecida(
                variedad.pk,
                str(variedad),
                variedad.perfil_familia,
                duracion[variedad.pk],
                libres[existencia.pk] if existencia else None,
                not conflictos,
                conflictos,
                f"Faltan sectores para: {', '.join(faltan)}." if faltan else None,
            )
        )
    return ofrecidas


def _adicionales_ofrecidos(invernadero, fecha):
    """Paso 12: insumos activos del invernadero fuera de las categorías del sistema, con su stock libre."""
    existencias = list(
        InsumoInvernadero.objects.filter(
            invernadero=invernadero,
            estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO,
            insumo__estado_insumo=Insumo.Estado.ACTIVO,
            insumo__tipo_insumo__es_del_sistema=False,
        )
        .select_related("insumo")
        .order_by("insumo__nombre_insumo", "id")
    )
    libres = stock.disponible_para_planificar([e.pk for e in existencias], fecha) if existencias else {}
    return [
        InsumoAdicional(e.pk, e.insumo.nombre_insumo, e.insumo.unidad_medida_insumo, libres[e.pk]) for e in existencias
    ]


def resumen_de_planificacion(actor, datos):
    """Paso 16: valida TODO (los mismos rechazos que `planificar_siembra`) y devuelve el resumen de la orden. No escribe, no numera
    la orden y no bloquea: lo que se presenta puede cambiar hasta la confirmación, que lo vuelve a verificar (extensión 18b)."""
    plan = _verificar(actor, datos)
    return _resumen(plan)


def _resumen(plan):
    """El `ResumenDePlanificacion` de un `Plan`: la fecha estimada de cosecha es la programada más los días hasta Maduración."""
    dias = ciclos.dias_hasta_maduracion([plan.variedad.pk])[plan.variedad.pk]
    semilla = plan.semilla
    reservas = [ReservaPrevista(plan.existencia_semilla, semilla.nombre_insumo, semilla.unidad_medida_insumo, Decimal(plan.cantidad))]
    reservas += [
        ReservaPrevista(e, e.insumo.nombre_insumo, e.insumo.unidad_medida_insumo, cantidad) for e, cantidad in plan.adicionales
    ]
    return ResumenDePlanificacion(
        plan.invernadero,
        plan.variedad,
        plan.cantidad,
        plan.fecha,
        plan.fecha + timedelta(days=dias),
        plan.prioridad,
        plan.descripcion,
        plan.capataz,
        plan.distribucion,
        reservas,
    )


# ---- PROD-PNF-SMB ----


def planificar_siembra(actor, datos):
    """PROD-PNF-SMB: planifica una siembra y devuelve la `Siembra` (con sus ocupaciones y reservas ya creadas).

    - Precondiciones y reglas: ver `_verificar`; se hacen antes de bloquear (rechazo pronto) y DE NUEVO después (extensión 18b).
    - Postcondición a: la orden de siembra «a realizar». Postcondición b: una ocupación por sector con los agujeros planificados y
      los ocupados en cero. Postcondición c: los agujeros comprometidos de cada sector suben (se derivan de las ocupaciones, D-50).
      Postcondiciones d y e: una reserva «activa» de la semilla y una por cada insumo adicional. Postcondición f: aviso al Capataz,
      dentro de la transacción (D-42). Postcondiciones g, h e i y D-36: UN registro `planificacion_siembra`.
    - Bloqueos (docs/patrones/bloqueos.md, sección `produccion`; stock.md, sección 5), todos `FOR NO KEY UPDATE`: las cuentas del
      Agrónomo y del Capataz (en orden de id) → el invernadero → la variedad → los sectores de la distribución → los insumos y sus
      existencias (en orden de id). Las filas nuevas no hacen falta bloquearlas. Si lo que se leyó antes cambió, `cambio_simultaneo`.
    - Todo o nada (D-22): si algo falla, no queda nada.
    """
    pronto = _verificar(actor, datos)
    with transaction.atomic():
        capataz_id = pronto.capataz.pk
        list(
            Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, capataz_id}).order_by("pk")
        )
        _exigir_agronomo_activo(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(
            bloquear_invernadero_activo, pronto.invernadero.pk, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)}
        )
        _bloquear(variedades.bloquear_variedad, pronto.variedad.pk, equivalencias={"variedad_inactiva": ("variedad_inactiva", "variedad")})
        _bloquear(
            api_sectores.bloquear_sectores,
            pronto.invernadero.pk,
            [sector.pk for sector, _ in pronto.distribucion],
            equivalencias={"sector_no_disponible": ("sector_no_elegible", "distribucion")},
        )
        ids_de_existencias = sorted({pronto.existencia_semilla.pk, *(e.pk for e, _ in pronto.adicionales)})
        # Orden de docs/patrones/stock.md, sección 5: `Insumo` antes que `InsumoInvernadero` (corregido en PRD-03: la aplicación de
        # insumos sigue ese orden y, con el inverso, una aplicación y una siembra sobre el mismo insumo podían trabarse entre sí).
        insumo_ids = set(InsumoInvernadero.objects.filter(pk__in=ids_de_existencias).values_list("insumo_id", flat=True))
        list(Insumo.objects.select_for_update(no_key=True).filter(pk__in=insumo_ids).order_by("pk"))
        existencias = list(
            InsumoInvernadero.objects.select_for_update(no_key=True).filter(pk__in=ids_de_existencias).order_by("pk")
        )
        plan = _verificar(actor, datos)  # extensión 18b: todo de nuevo, con lo bloqueado
        if plan.capataz.pk != capataz_id:
            raise _error("cambio_simultaneo", "Mientras se confirmaba, cambió el Capataz del invernadero. Volvé a intentarlo.")
        return _escribir(actor, plan)


def _escribir(actor, plan):
    """Pasos 18 a 20: crea la orden, las ocupaciones y las reservas; avisa al Capataz y escribe el único registro de auditoría."""
    hoy = stock.hoy()
    antes = api_sectores.agujeros_de([sector for sector, _ in plan.distribucion])
    siembra = Siembra.objects.create(
        tipo_orden=OrdenTrabajo.Tipo.SIEMBRA,
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=hoy,
        fecha_programada_orden=plan.fecha,
        prioridad_orden=plan.prioridad,
        descripcion_orden=plan.descripcion,
        agronomo_id=actor.pk,
        invernadero=plan.invernadero,
        capataz_id=plan.capataz.pk,
        cant_plantines_siembra=plan.cantidad,
        variedad=plan.variedad,
    )
    ocupaciones = [
        OcupacionSector.objects.create(orden=siembra, sector=sector, cant_agujeros_planificados=n) for sector, n in plan.distribucion
    ]
    reservas = [
        ReservaInsumo.objects.create(
            orden=siembra, insumo_invernadero=existencia, cantidad_reservada=cantidad, fecha_reserva=hoy
        )
        for existencia, cantidad in [(plan.existencia_semilla, Decimal(plan.cantidad)), *plan.adicionales]
    ]
    notificaciones.notificar(
        plan.capataz,
        f"Nueva orden {siembra.codigo}",
        f"Siembra de {plan.variedad}: {_plural(plan.cantidad, 'plantín', 'plantines')} para el {plan.fecha:%d/%m/%Y} en "
        f"{plan.invernadero.nombre_invernadero}. La planificó {actor.get_full_name() or actor.email}.",
    )
    sectores = [sector for sector, _ in plan.distribucion]
    datos = {
        "invernadero": referencia(plan.invernadero),
        "variedad": referencia(plan.variedad),
        "capataz": referencia(plan.capataz),
        "cant_plantines_siembra": str(plan.cantidad),
        "fecha_programada_orden": f"{plan.fecha:%d/%m/%Y}",
    }
    if plan.prioridad:
        datos["prioridad_orden"] = plan.prioridad
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.PLANIFICACION_SIEMBRA,
        afectados=[siembra, *ocupaciones, *reservas, *sectores],
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
    return siembra


# ============================================================================================================================
# PROD-CNC-SMB · Concretar Siembra (paso 6)
# ============================================================================================================================
# - `datos_de_concrecion`: lo que propone el paso 4 (fecha de hoy, lo planificado por sector, las reservas con sus cantidades y los
#   lotes de insumo FEFO). No escribe.
# - `resumen_de_concrecion`: valida todo y devuelve el resumen del paso 17. No escribe ni bloquea.
# - `concretar_siembra`: valida, bloquea (cuentas → invernadero → variedad → sectores → insumos y existencias → la orden y sus filas),
#   VUELVE A VERIFICAR TODO y escribe. Sin asientos ni ejercicio (D-45: la postcondición j y las precondiciones c y d no existen).


@dataclass(frozen=True)
class AjusteDeInsumo:
    """Lo que el Capataz cambia de la reserva de un insumo (`existencia_id`, el id del `InsumoInvernadero`); `None` = lo propuesto.
    `lotes` es `((lote_de_insumo_id, cantidad), ...)` (extensión 17b). La utilizada de la semilla no se cambia: es el total sembrado."""

    existencia_id: int
    utilizada: Decimal | None = None
    devuelta: Decimal | None = None
    lotes: tuple | None = None


@dataclass(frozen=True)
class DatosDeConcrecion:
    """Lo que el Capataz indica en los pasos 5 a 15: solo lo que difiere de lo propuesto. `sembrado` es `((sector_id, plantines), ...)`;
    el sector que no figura toma lo planificado. Sin `fecha_efectiva`, hoy."""

    fecha_efectiva: date | None = None
    sembrado: tuple | None = None
    motivo_diferencia: str = ""
    ajustes: tuple = ()


FilaDeSector = namedtuple("FilaDeSector", "sector_id nombre planificados propuesto")
FilaDeReserva = namedtuple(
    "FilaDeReserva", "existencia_id nombre unidad reservada utilizada devuelta consumida lotes resto monto es_semilla"
)
PropuestaDeConcrecion = namedtuple("PropuestaDeConcrecion", "orden fecha_propuesta fecha_minima distribucion reservas")
# `distribucion`: `[(sector, planificados, sembrados)]`. `costo`: la suma de los montos de consumo ya redondeados.
ResumenDeConcrecion = namedtuple(
    "ResumenDeConcrecion",
    "orden fecha_efectiva total_sembrado total_planificado diferencia motivo_diferencia distribucion reservas costo",
)
# Lo que `_verificar_concrecion` resuelve y `concretar_siembra` usa. `sembrado`: `[(ocupacion, sembrados)]`; `lineas`: `[LineaDeReserva]`.
PlanDeConcrecion = namedtuple("PlanDeConcrecion", "siembra fecha sembrado total motivo lineas")
LineaDeReserva = namedtuple("LineaDeReserva", "reserva existencia utilizada devuelta consumida partes resto monto es_semilla")

LARGO_DEL_MOTIVO = 300


def _entero_no_negativo(valor):
    """`True` si `valor` es un `int` (no `bool`) mayor o igual que cero."""
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _decimal_de_la_unidad(valor, unidad, campo):
    """`valor` como `Decimal` con los decimales de la unidad del insumo; si no es un número válido, `cantidad_invalida` en `campo`."""
    try:
        return validar_cantidad(valor, unidad)
    except ValidationError as error:
        raise _error("cantidad_invalida", " ".join(error.messages), campo) from error


def _texto(cantidad):
    """Una cantidad sin ceros de más: `Decimal('50.000')` → `'50'`."""
    return format(Decimal(cantidad).normalize(), "f")


def _lotes_de_salida(existencia, consumida, ajuste, fecha):
    """Pasos 17 y 19 y extensión 17b: los lotes de los que sale lo consumido y lo que ninguno cubre (el `resto`, que sale del «faltante
    sin lote»). Sin ajuste, FEFO a la fecha efectiva (`stock.proponer_lotes_fefo`). Con lotes indicados, cada uno aporta como máximo su
    cantidad disponible y el total no pasa de lo consumido. Devuelve `(partes, resto)`."""
    if ajuste is None or ajuste.lotes is None:
        propuesta = stock.proponer_lotes_fefo(existencia.pk, consumida, fecha)
        return [(lote_id, cantidad) for lote_id, cantidad in propuesta.partes], propuesta.resto
    unidad = existencia.insumo.unidad_medida_insumo
    lotes = {l.pk: l for l in LoteInsumo.objects.filter(insumo_invernadero=existencia, es_faltante_sin_lote=False)}
    partes, vistos = [], set()
    for lote_id, cantidad in ajuste.lotes:
        cantidad = _decimal_de_la_unidad(cantidad, unidad, "lotes")
        if lote_id not in lotes or lote_id in vistos or cantidad <= 0 or cantidad > lotes[lote_id].cantidad_disponible:
            raise _error(
                "cantidad_invalida",
                "Cada lote tiene que ser un lote de este insumo, usarse una sola vez y aportar una cantidad entre 0 y lo que tiene disponible.",
                "lotes",
            )
        vistos.add(lote_id)
        partes.append((lote_id, cantidad))
    total = sum((c for _, c in partes), Decimal("0"))
    if total > consumida:
        raise _error("cantidad_invalida", f"Los lotes suman {_texto(total)} y lo consumido es {_texto(consumida)}.", "lotes")
    return partes, consumida - total


def _linea_de_reserva(reserva, es_semilla, total, ajuste, fecha):
    """Pasos 10 a 15 de una reserva: cantidad utilizada, devuelta y consumida (regla «Cantidad devuelta»; extensiones 13a y 15a), el monto
    de consumo (consumido × precio de referencia, `ROUND_HALF_UP`, regla 14 de 8.9) y los lotes de los que sale."""
    existencia = reserva.insumo_invernadero
    unidad = existencia.insumo.unidad_medida_insumo
    reservada = reserva.cantidad_reservada
    if es_semilla:
        utilizada = Decimal(total)  # una semilla da origen a un plantín (variación 7a)
        if ajuste is not None and ajuste.utilizada is not None and Decimal(ajuste.utilizada) != utilizada:
            raise _error("cantidad_invalida", "La semilla utilizada es el total sembrado: no se cambia.", "utilizada")
    elif ajuste is not None and ajuste.utilizada is not None:
        utilizada = _decimal_de_la_unidad(ajuste.utilizada, unidad, "utilizada")
        if not 0 <= utilizada <= reservada:
            raise _error(
                "cantidad_invalida",
                f"La cantidad utilizada de {existencia.insumo.nombre_insumo} no puede superar la reservada ({_texto(reservada)}).",
                "utilizada",
            )
    else:
        utilizada = reservada
    maximo = reservada - utilizada
    if ajuste is not None and ajuste.devuelta is not None:
        devuelta = _decimal_de_la_unidad(ajuste.devuelta, unidad, "devuelta")
        if not 0 <= devuelta <= maximo:
            raise _error(
                "cantidad_invalida",
                f"La cantidad devuelta de {existencia.insumo.nombre_insumo} puede ser, como máximo, {_texto(maximo)}.",
                "devuelta",
            )
    else:
        devuelta = maximo
    consumida = reservada - devuelta
    monto = costos.redondear_monto(consumida * existencia.referencia_precio) if consumida > 0 else Decimal("0.00")
    partes, resto = _lotes_de_salida(existencia, consumida, ajuste, fecha) if consumida > 0 else ([], Decimal("0"))
    return LineaDeReserva(reserva, existencia, utilizada, devuelta, consumida, partes, resto, monto, es_semilla)


def _verificar_concrecion(actor, orden_id, datos):
    """TODAS las verificaciones de PROD-CNC-SMB, en el orden del caso de uso. Lee siempre de la base: sirve antes de bloquear (rechazo
    pronto) y después (extensión 19a: la orden pudo cambiar). No escribe. Devuelve el `PlanDeConcrecion`."""
    siembra = (
        Siembra.objects.select_related("invernadero", "variedad__cultivo", "agronomo").filter(pk=orden_id).first()
    )
    if siembra is None:
        raise Http404("No existe esa orden de siembra.")
    if (
        actor is None
        or rol_de(actor) != Usuario.Rol.CAPATAZ
        or siembra.capataz_id != actor.pk
        or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise _error("sin_permiso", "Solo el Capataz asignado a la orden puede concretarla.")
    if siembra.estado_orden != Estado.A_REALIZAR:
        raise _error(
            "orden_no_pendiente", f"La orden {siembra.codigo} ya no está «a realizar»: su estado actual es «{siembra.get_estado_orden_display()}»."
        )
    hoy = stock.hoy()
    fecha = datos.fecha_efectiva or hoy
    if not isinstance(fecha, date) or fecha > hoy:
        raise _error("fecha_invalida", "La fecha efectiva no puede ser posterior a hoy.", "fecha_efectiva")
    if fecha < siembra.fecha_creacion_orden:
        raise _error(
            "fecha_invalida", f"La fecha efectiva no puede ser anterior a la de creación de la orden ({siembra.fecha_creacion_orden:%d/%m/%Y}).", "fecha_efectiva"
        )
    ocupaciones = list(siembra.ocupaciones.select_related("sector").order_by("id"))
    indicadas = {}
    for sector_id, plantines in datos.sembrado or ():
        if sector_id in indicadas or sector_id not in {o.sector_id for o in ocupaciones}:
            raise _error("sector_no_elegible", "Ese sector no es parte de la distribución planificada de la orden.", "sembrado")
        indicadas[sector_id] = plantines
    sembrado = []
    for ocupacion in ocupaciones:
        plantines = indicadas.get(ocupacion.sector_id, ocupacion.cant_agujeros_planificados)
        if not _entero_no_negativo(plantines) or plantines > ocupacion.cant_agujeros_planificados:
            raise _error(
                "cantidad_invalida",
                f"En {ocupacion.sector.nombre_sector} se planificaron {ocupacion.cant_agujeros_planificados} plantines: sembraste de más o indicaste una cantidad inválida.",
                "sembrado",
            )
        sembrado.append((ocupacion, plantines))
    total = sum(n for _, n in sembrado)
    if total < 1:
        raise _error("cantidad_invalida", "No se puede concretar una siembra sin plantines sembrados.", "sembrado")
    motivo = (datos.motivo_diferencia or "").strip()
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise _error("motivo_largo", f"El motivo de la diferencia pasa de {LARGO_DEL_MOTIVO} caracteres.", "motivo_diferencia")
    if total >= siembra.cant_plantines_siembra:
        motivo = ""  # solo si el total sembrado fue menor que lo planificado
    semilla = variedades.semilla_de([siembra.variedad_id])[siembra.variedad_id]
    ajustes = {a.existencia_id: a for a in datos.ajustes}
    reservas = list(
        siembra.reservas.select_related("insumo_invernadero__insumo").order_by("id")
    )
    if any(r.estado != ReservaInsumo.Estado.ACTIVA for r in reservas):
        raise _error("cambio_simultaneo", "Las reservas de la orden cambiaron mientras la concretabas. Volvé a abrirla.")
    if set(ajustes) - {r.insumo_invernadero_id for r in reservas}:
        raise _error("cantidad_invalida", "Uno de los insumos indicados no está reservado por esta orden.", "ajustes")
    lineas = [
        _linea_de_reserva(r, r.insumo_invernadero.insumo_id == semilla.pk, total, ajustes.get(r.insumo_invernadero_id), fecha)
        for r in reservas
    ]
    return PlanDeConcrecion(siembra, fecha, sembrado, total, motivo, lineas)


def _fila_de_reserva(linea):
    """La `FilaDeReserva` que muestran la propuesta y el resumen."""
    existencia = linea.existencia
    return FilaDeReserva(
        existencia.pk,
        existencia.insumo.nombre_insumo,
        existencia.insumo.unidad_medida_insumo,
        linea.reserva.cantidad_reservada,
        linea.utilizada,
        linea.devuelta,
        linea.consumida,
        linea.partes,
        linea.resto,
        linea.monto,
        linea.es_semilla,
    )


def datos_de_concrecion(actor, orden_id):
    """Paso 4 de PROD-CNC-SMB: lo que propone el sistema para la orden (valores propuestos). No escribe ni bloquea."""
    plan = _verificar_concrecion(actor, orden_id, DatosDeConcrecion())
    distribucion = [
        FilaDeSector(o.sector_id, o.sector.nombre_sector, o.cant_agujeros_planificados, n) for o, n in plan.sembrado
    ]
    return PropuestaDeConcrecion(
        plan.siembra, stock.hoy(), plan.siembra.fecha_creacion_orden, distribucion, [_fila_de_reserva(l) for l in plan.lineas]
    )


def resumen_de_concrecion(actor, orden_id, datos):
    """Paso 17: valida TODO (los mismos rechazos que `concretar_siembra`) y devuelve el resumen. No escribe y no bloquea: lo que se
    presenta puede cambiar hasta la confirmación, que lo vuelve a verificar (extensión 19a)."""
    plan = _verificar_concrecion(actor, orden_id, datos)
    planificado = plan.siembra.cant_plantines_siembra
    return ResumenDeConcrecion(
        plan.siembra,
        plan.fecha,
        plan.total,
        planificado,
        planificado - plan.total,
        plan.motivo,
        [(o.sector, o.cant_agujeros_planificados, n) for o, n in plan.sembrado],
        [_fila_de_reserva(l) for l in plan.lineas],
        sum((l.monto for l in plan.lineas), Decimal("0.00")),
    )


def _partes_de_salida(existencia, partes, resto):
    """Lo que se le pasa a `registrar_salida_por_consumo`: las partes y, si los lotes no cubren lo consumido, el `resto` sumado a un lote
    que esa misma salida deja en cero (así `inventario` manda la diferencia al «faltante sin lote»: solo acepta lotes existentes).
    Si ningún lote queda en cero, usa uno ya agotado y, si no hay, el de menos stock. Una existencia sin ningún lote común no se puede
    descontar: es un caso que no ocurre (reservar exige haber tenido stock y los lotes no se borran)."""
    if resto <= 0:
        return partes
    disponibles = {l.pk: l.cantidad_disponible for l in LoteInsumo.objects.filter(insumo_invernadero=existencia, es_faltante_sin_lote=False)}
    if not disponibles:
        raise _error("cambio_simultaneo", f"El insumo {existencia.insumo.nombre_insumo} no tiene ningún lote del que descontar. Pedile al Agrónomo que lo regularice.")
    vaciados = [lote_id for lote_id, cantidad in partes if cantidad >= disponibles[lote_id]]
    if vaciados:
        return [(lote_id, cantidad + resto if lote_id == vaciados[-1] else cantidad) for lote_id, cantidad in partes]
    en_cero = [lote_id for lote_id, cantidad in disponibles.items() if cantidad <= 0 and lote_id not in {p for p, _ in partes}]
    portador = en_cero[0] if en_cero else min(disponibles, key=disponibles.get)
    return [*partes, (portador, resto)]


def _descripcion_de_consumo(siembra, existencia, consumida):
    """Texto legible de la bitácora del consumo (D-51 puntos 2 y 8): «Siembra OT-0004: Semilla Lechuga Butterhead, 200 unidades»."""
    unidad = existencia.insumo.unidad_medida_insumo
    nombre_de_la_unidad = "unidades" if unidad == "unidad" and consumida != 1 else Unidad(unidad).label
    return f"Siembra {siembra.codigo}: {existencia.insumo.nombre_insumo}, {_texto(consumida)} {nombre_de_la_unidad}"[:500]


def concretar_siembra(actor, orden_id, datos):
    """PROD-CNC-SMB: concreta una siembra y devuelve el `Lote` creado.

    - Precondiciones a y b y requisito especial: `actor` es el Capataz activo asignado a la orden (`sin_permiso`) y la orden está «a
      realizar» (`orden_no_pendiente`, extensión 19a, con el estado actual). Las c y d (ejercicio y cuentas) no se verifican (D-45).
    - Reglas y extensiones 6a, 6b, 8a, 9a, 10a, 13a, 15a, 17b y 19b: ver `_verificar_concrecion` y `_lotes_de_salida`.
    - Postcondición a: la orden pasa a «concretada» (fecha de resolución = hoy, fecha de siembra = la efectiva, motivo si lo hubo). b: el
      lote en Germinación con su costo (suma de los montos redondeados). c y d: las ocupaciones guardan lo sembrado y, con él, se liberan
      los agujeros comprometidos (se derivan, D-50). e y f: las reservas se cierran con `consumos.cerrar_reserva`. g e i: FEFO a la fecha
      efectiva (o los lotes elegidos) y un movimiento por lote; lo que no cubren sale del «faltante sin lote». h: un consumo por reserva
      consumida, CON SU BITÁCORA, creado ANTES que sus movimientos (D-52 punto 5). k: aviso al Agrónomo que planificó. l a o: UN registro.
      p: la alerta «stock inconsistente» la deja `inventario` al reevaluar. Sin asientos (D-45).
    - Bloqueos (`FOR NO KEY UPDATE`, docs/patrones/bloqueos.md): cuentas del Capataz y del Agrónomo (orden de id) → invernadero →
      variedad → sectores de la orden → insumos y existencias (orden de id) → [los lotes de insumo los toma `inventario`] → la orden,
      sus reservas y sus ocupaciones. Después se repite TODO lo verificado. Todo o nada (D-22).
    """
    pronto = _verificar_concrecion(actor, orden_id, datos)
    siembra = pronto.siembra
    with transaction.atomic():
        list(
            Usuario.objects.select_for_update(no_key=True)
            .filter(pk__in={actor.pk, *([siembra.agronomo_id] if siembra.agronomo_id else [])})
            .order_by("pk")
        )
        _bloquear(bloquear_invernadero_activo, siembra.invernadero_id, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)})
        _bloquear(variedades.bloquear_variedad, siembra.variedad_id, equivalencias={"variedad_inactiva": ("variedad_inactiva", "variedad")})
        _bloquear(api_sectores.bloquear_sectores, siembra.invernadero_id, [o.sector_id for o, _ in pronto.sembrado])
        existencias_ids = sorted({l.existencia.pk for l in pronto.lineas})
        # `Insumo` antes que `InsumoInvernadero` (stock.md, sección 5; corregido en PRD-03, ver arriba).
        list(Insumo.objects.select_for_update(no_key=True).filter(pk__in={l.existencia.insumo_id for l in pronto.lineas}).order_by("pk"))
        list(InsumoInvernadero.objects.select_for_update(no_key=True).filter(pk__in=existencias_ids).order_by("pk"))
        list(Siembra.objects.select_for_update(no_key=True).filter(pk=orden_id))
        list(ReservaInsumo.objects.select_for_update(no_key=True).filter(orden_id=orden_id).order_by("pk"))
        list(OcupacionSector.objects.select_for_update(no_key=True).filter(orden_id=orden_id).order_by("pk"))
        plan = _verificar_concrecion(actor, orden_id, datos)  # extensión 19a: todo de nuevo, con lo bloqueado
        return _registrar_concrecion(actor, plan)


def _registrar_concrecion(actor, plan):
    """Pasos 19 a 21: escribe todo lo de la concreción, avisa al Agrónomo y deja el único registro de auditoría."""
    siembra, fecha = plan.siembra, plan.fecha
    hoy = stock.hoy()
    sectores = [o.sector for o, _ in plan.sembrado]
    antes = api_sectores.agujeros_de(sectores)
    etapa_id = next(e.etapa_id for e in ciclos.etapas_de([siembra.variedad_id])[siembra.variedad_id] if e.codigo == "germinacion")
    costo = sum((l.monto for l in plan.lineas), Decimal("0.00"))
    lote = Lote.objects.create(
        invernadero=siembra.invernadero,
        etapa_id=etapa_id,
        siembra=siembra,
        cantidad_inicial=plan.total,
        cantidad_actual=plan.total,
        costo_acumulado=costo,
    )
    for ocupacion, sembrados in plan.sembrado:
        ocupacion.cant_agujeros_ocupados = sembrados
        ocupacion.lote = lote if sembrados > 0 else None
        ocupacion.save(update_fields=["cant_agujeros_ocupados", "lote"])
    donde_se_sembro = [o.sector for o, n in plan.sembrado if n > 0]
    # El consumo (con su bitácora) se crea ANTES que su salida de stock: el movimiento lo apunta como origen (D-52 punto 5).
    consumos_creados = []
    for linea in plan.lineas:
        if linea.consumida <= 0:
            continue
        consumo = Consumo.objects.create(
            invernadero=siembra.invernadero,
            lote=lote,
            etapa_id=etapa_id,
            responsable_id=actor.pk,
            fecha_bitacora=fecha,
            hora_bitacora=timezone.localtime().time(),
            tipo_evento=Bitacora.TipoEvento.SIEMBRA,
            descripcion_evento=_descripcion_de_consumo(siembra, linea.existencia, linea.consumida),
            monto_consumo=linea.monto,
            cant_consumo=linea.consumida,
            fecha_consumo=fecha,
            insumo_invernadero=linea.existencia,
            siembra=siembra,
        )
        consumo.sectores.set(donde_se_sembro)
        consumos_creados.append((consumo, linea))
    # Las reservas se cierran antes de la salida: así la reevaluación de alertas de `inventario` ya no las cuenta como activas.
    for linea in plan.lineas:
        consumos_de_reserva.cerrar_reserva(linea.reserva, linea.utilizada, linea.devuelta)
    movimientos = []
    for consumo, linea in consumos_creados:
        partes = _partes_de_salida(linea.existencia, linea.partes, linea.resto)
        movimientos += stock.registrar_salida_por_consumo(linea.existencia.pk, partes, origen_id=consumo.pk, fecha=fecha)
    for existencia in {l.existencia.pk: l.existencia for l in plan.lineas}.values():
        alertas_de_stock.reevaluar_alertas_del_insumo(existencia.pk)  # también los insumos cuya reserva quedó «cancelada»
    antes_de_la_orden = {"estado": siembra.estado_orden}
    siembra.estado_orden = Estado.CONCRETADA
    siembra.fecha_resolucion_orden = hoy
    siembra.fecha_siembra = fecha
    siembra.motivo_diferencia_siembra = plan.motivo
    siembra.save(update_fields=["estado_orden", "fecha_resolucion_orden", "fecha_siembra", "motivo_diferencia_siembra"])
    despues = api_sectores.agujeros_de(sectores)
    if siembra.agronomo is not None and siembra.agronomo.is_active:
        diferencia = siembra.cant_plantines_siembra - plan.total
        resumen = f"Se sembraron {plan.total} de {siembra.cant_plantines_siembra} plantines previstos"
        resumen += f" (faltaron {diferencia}). Motivo: {plan.motivo}." if diferencia and plan.motivo else (f" (faltaron {diferencia})." if diferencia else ", sin diferencias.")
        detalle = f"{resumen} Lote {lote.codigo} en {siembra.invernadero.nombre_invernadero}. La concretó {actor.get_full_name() or actor.email}."
        notificaciones.notificar(
            siembra.agronomo,
            f"Siembra {siembra.codigo} concretada",
            detalle if len(detalle) <= 500 else detalle[:499] + "…",  # el aviso no puede hacer fallar la concreción (D-42)
        )
    cambios = {
        "estado": {"antes": antes_de_la_orden["estado"], "despues": siembra.estado_orden},
        "fecha_resolucion_orden": {"antes": None, "despues": f"{hoy:%d/%m/%Y}"},
        "fecha_siembra": {"antes": None, "despues": f"{fecha:%d/%m/%Y}"},
        "agujeros_comprometidos": {
            "antes": [f"{s.nombre_sector}: {antes[s.pk].comprometidos}" for s in sectores],
            "despues": [f"{s.nombre_sector}: {despues[s.pk].comprometidos}" for s in sectores],
        },
        "agujeros_ocupados": {
            "antes": [f"{s.nombre_sector}: {antes[s.pk].ocupados}" for s in sectores],
            "despues": [f"{s.nombre_sector}: {despues[s.pk].ocupados}" for s in sectores],
        },
    }
    if plan.motivo:
        cambios["motivo_diferencia_siembra"] = {"antes": "", "despues": plan.motivo}
    lotes_de_insumo = {m.lote_insumo_id: m.lote_insumo for m in movimientos}
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.CONCRECION_SIEMBRA,
        afectados=[
            siembra,
            lote,
            *[o for o, _ in plan.sembrado],
            *sectores,
            *[l.reserva for l in plan.lineas],
            *{l.existencia.pk: l.existencia for l in plan.lineas}.values(),
            *lotes_de_insumo.values(),
            *[c for c, _ in consumos_creados],
            *movimientos,
        ],
        detalle={
            "cambios": cambios,
            "datos": {
                "lote": referencia(lote),
                "cantidad_sembrada": str(plan.total),
                "cant_plantines_siembra": str(siembra.cant_plantines_siembra),
                "costo_acumulado": str(costo),
            },
        },
    )
    return lote


def lotes_de_insumo_disponibles(existencia_ids):
    """`{existencia_id: [LoteInsumo]}`: los lotes comunes con stock de cada existencia, del que vence primero al que vence último, para que el
    Capataz elija de cuáles sale un insumo (extensión 17b). Una consulta; no escribe."""
    lotes = LoteInsumo.objects.filter(
        insumo_invernadero_id__in=list(existencia_ids), es_faltante_sin_lote=False, cantidad_disponible__gt=0
    )
    por_existencia = defaultdict(list)
    for lote in sorted(lotes, key=lambda l: (l.fecha_vencimiento is None, l.fecha_vencimiento or date.max, l.fecha_ingreso, l.pk)):
        por_existencia[lote.insumo_invernadero_id].append(lote)
    return dict(por_existencia)
