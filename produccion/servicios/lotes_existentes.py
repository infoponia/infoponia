# Registrar Lote Existente (PRD-05): PROD-REG-LTE. El Agrónomo carga los lotes de plantas que ya estaban en los sectores al poner en marcha InfoPonia, con su
# etapa actual y un costo estimado; el valor entra a la contabilidad contra Capital Inicial. Solo en un invernadero que todavía no tuvo siembras NORMALES
# concretadas. Fuente: docs/casos_de_uso/produccion/lote_existente.md (y «Cómo se aplica (código)»), D-92 punto 12, D-86, D-50, D-51, D-53 y D-61;
# docs/patrones/bloqueos.md (secciones `produccion` y «Contabilidad»). Las vistas solo orquestan: las reglas están acá.
#
# - `invernaderos_disponibles`, `datos_de_registro`: lo que presentan los pasos 2, 4 y 6. No escriben ni bloquean.
# - `resumen_de_registro`: valida TODO y devuelve el resumen del paso 8 (con el asiento previsto). No escribe ni bloquea.
# - `registrar_lote_existente`: valida, bloquea (cuenta → invernadero → variedad → sectores en orden de id), VUELVE A VERIFICAR TODO (extensión 10a),
#   escribe la siembra, el lote, las ocupaciones, la bitácora y el asiento, y deja UN registro de auditoría. Todo o nada (D-22). El ejercicio contable lo
#   bloquea el servicio de asientos al final (D-86).
#
# DIFERENCIAS CON LAS FUENTES (anotadas en el «Cierre» de PRD-05):
# - Fechas de la orden: `fecha_creacion_orden = fecha_programada_orden = fecha_resolucion_orden = hoy`. D-92 punto 12 pide `fecha_programada_orden = fecha
#   de siembra`, imposible con el CHECK `orden_trabajo_programada_desde_creacion` (programada ≥ creación) de la tabla padre. La fecha indicada va en
#   `Siembra.fecha_siembra`; el asiento y la bitácora usan las fechas de las fuentes (hoy y el ingreso a la etapa).
# - Fecha de entrada en la primera etapa: manda la de ingreso cargada (la lectura está en `lotes.py`).
# - Código nuevo `etapa_invalida` (la etapa no es del ciclo de la variedad): un dato mal formado que el caso de uso no nombra.

from collections import namedtuple
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models.functions import Lower
from django.http import Http404
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import CuentaContable
from contabilidad.servicios import asientos
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import ciclos, variedades
from inventario.servicios.variedades import bloquear_variedad
from maestros.models import Invernadero
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Lote, OcupacionSector, OrdenTrabajo, Siembra
from produccion.servicios import ordenes, sectores_elegibles
from produccion.servicios.bloqueos import traducir as _bloquear

CENTAVOS = Decimal("0.01")
# `Lote.costo_acumulado` es `DecimalField(14, 2)`: 12 enteros y 2 decimales.
MAXIMO_DEL_COSTO = Decimal("999999999999.99")
LARGO_DE_LA_DESCRIPCION = 500
LARGO_DEL_ASIENTO = 300


# ---- Lo que recibe y lo que devuelve ----


@dataclass(frozen=True)
class DatosDeLoteExistente:
    """Lo que el Agrónomo carga en los pasos 3 a 7. `etapa_id` es el id de la `EtapaProductiva` del ciclo de la variedad. `distribucion` es
    `{sector_id: plantas}` o `((sector_id, plantas), ...)`: los pares dejan detectar un sector repetido. `costo_estimado` es un `Decimal`."""

    invernadero_id: int
    variedad_id: int
    etapa_id: int
    fecha_siembra: date | None
    fecha_ingreso_etapa: date | None
    cantidad: int
    costo_estimado: Decimal = Decimal("0.00")
    distribucion: object = ()


VariedadOfrecida = namedtuple("VariedadOfrecida", "variedad_id nombre perfil")
SectorOfrecido = namedtuple("SectorOfrecido", "sector_id nombre libres")
# Lo que presentan los pasos 2, 4 y 6. `etapas` es `[ciclos.EtapaDelCiclo]`; `sectores`, los elegibles con sus agujeros libres; `no_elegibles`, los
# del tipo de la etapa que no se pueden elegir y por qué (`sectores_elegibles.SectorNoElegible`).
DatosDeRegistro = namedtuple("DatosDeRegistro", "invernaderos variedades etapas sectores no_elegibles")
SectorDelResumen = namedtuple("SectorDelResumen", "sector_id nombre plantas libres_despues")
# `debe` y `haber` son `(código, nombre)` de la cuenta.
AsientoPrevisto = namedtuple("AsientoPrevisto", "debe haber importe")
ResumenDeRegistro = namedtuple(
    "ResumenDeRegistro",
    "invernadero variedad etapa fecha_siembra fecha_ingreso_etapa cantidad costo_estimado costo_por_planta distribucion asiento",
)
# Todo lo que `_verificar` resuelve y que `registrar_lote_existente` usa para escribir. `distribucion` es `[(sector, plantas)]`, por id de sector.
Plan = namedtuple(
    "Plan", "invernadero variedad etapa fecha_siembra fecha_ingreso_etapa cantidad costo distribucion agujeros hoy"
)


def _error(codigo, mensaje, campo=None, datos=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo, datos)


# ---- Verificaciones (se hacen dos veces: antes de bloquear y después, extensión 10a) ----


def _exigir_agronomo_activo(actor):
    """Precondición a: `actor` es un Agrónomo con la cuenta activa (se lee de la base: pudo darse de baja mientras tanto)."""
    if actor is None or rol_de(actor) != Usuario.Rol.AGRONOMO or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
        raise _error("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")


def _sin_siembras_normales(invernadero_id):
    """Precondición c: el invernadero no tiene siembras concretadas por el flujo normal (D-92 punto 12). Las «a realizar», las canceladas y las de
    carga inicial no cuentan."""
    return not Siembra.objects.filter(
        invernadero_id=invernadero_id, estado_orden=OrdenTrabajo.Estado.CONCRETADA, tipo_siembra=Siembra.TipoSiembra.NORMAL
    ).exists()


def _exigir_invernadero_disponible(actor, invernadero_id):
    """Precondiciones a, b y c, y extensión 2a: el invernadero existe, está a cargo de `actor`, está activo y sigue sin siembras normales."""
    invernadero = Invernadero.objects.filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if invernadero.agronomo_id != actor.pk:
        raise _error("sin_permiso", "Ese invernadero no está a tu cargo.")
    if not invernadero.activo:
        raise _error("invernadero_inactivo", "El invernadero está inactivo: no se puede registrar un lote en él.")
    if not _sin_siembras_normales(invernadero.pk):
        raise _error(
            "invernadero_con_siembras",
            "Este caso de uso solo se usa en invernaderos sin siembras por el flujo normal, y este ya tiene una siembra concretada.",
            "invernadero",
        )
    return invernadero


def _exigir_cantidad(cantidad):
    """Extensión 5b: un entero mayor que cero."""
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad <= 0:
        raise _error("cantidad_invalida", "La cantidad de plantas tiene que ser un número entero mayor que cero.", "cantidad")
    return cantidad


def _exigir_costo(costo):
    """Extensión 5c: un `Decimal` no negativo con dos decimales como mucho (y que entre en el campo del costo del lote)."""
    if (
        not isinstance(costo, Decimal)
        or not costo.is_finite()
        or costo < 0
        or costo != costo.quantize(CENTAVOS)
        or costo > MAXIMO_DEL_COSTO
    ):
        raise _error(
            "costo_invalido", "El costo estimado tiene que ser un monto de cero o más, con hasta dos decimales.", "costo_estimado"
        )
    return costo.quantize(CENTAVOS)


def _exigir_fechas(fecha_siembra, fecha_ingreso, hoy):
    """Extensión 5a: la siembra no es posterior a hoy y el ingreso a la etapa está entre la siembra y hoy."""
    if not isinstance(fecha_siembra, date):
        raise _error("fecha_invalida", "Indicá la fecha de siembra.", "fecha_siembra")
    if fecha_siembra > hoy:
        raise _error("fecha_invalida", "La fecha de siembra no puede ser posterior a hoy.", "fecha_siembra")
    if not isinstance(fecha_ingreso, date):
        raise _error("fecha_invalida", "Indicá la fecha de ingreso a la etapa.", "fecha_ingreso_etapa")
    if fecha_ingreso < fecha_siembra:
        raise _error("fecha_invalida", "El ingreso a la etapa no puede ser anterior a la fecha de siembra.", "fecha_ingreso_etapa")
    if fecha_ingreso > hoy:
        raise _error("fecha_invalida", "El ingreso a la etapa no puede ser posterior a hoy.", "fecha_ingreso_etapa")


def _variedad_activa(variedad_id):
    """La variedad (404 si no existe), activa y de un cultivo activo (`variedad_inactiva`)."""
    variedad = variedades.obtener_variedad(variedad_id)
    if not variedad.activa or not variedad.cultivo.activo:
        raise _error("variedad_inactiva", "La variedad está inactiva: elegí otra.", "variedad")
    return variedad


def _etapa_del_ciclo(variedad, etapa_id):
    """Paso 4: la etapa elegida es una del ciclo de la variedad (`etapa_invalida`). Cualquier etapa vale, no solo Germinación."""
    etapa = next((e for e in ciclos.etapas_de([variedad.pk])[variedad.pk] if e.etapa_id == etapa_id), None)
    if etapa is None:
        raise _error("etapa_invalida", "Esa etapa no es del ciclo de la variedad elegida.", "etapa")
    return etapa


def _pares(distribucion):
    """`distribucion` como lista de `(sector_id, plantas)`: acepta un diccionario o una secuencia de pares."""
    return list(distribucion.items()) if isinstance(distribucion, dict) else list(distribucion or ())


def _distribucion_valida(pares, cantidad, elegibles):
    """Pasos 7 y extensiones 7a y 7b: cada sector es uno de los que se ofrecen, se usa una vez con un entero mayor que cero que entra en sus agujeros
    libres, y todo suma exactamente la cantidad. Devuelve `[(sector, plantas)]` por id de sector."""
    vistos, resultado, excedidos = set(), [], {}
    for sector_id, plantas in pares:
        if sector_id not in elegibles:
            raise _error(
                "sector_no_elegible",
                "Ese sector no se puede elegir: tiene que ser un sector activo del tipo de la etapa, compatible y de este invernadero.",
                "distribucion",
            )
        if sector_id in vistos or not isinstance(plantas, int) or isinstance(plantas, bool) or plantas <= 0:
            raise _error("cantidad_invalida", "Cada sector se usa una sola vez y con una cantidad entera mayor que cero.", "distribucion")
        vistos.add(sector_id)
        sector, agujeros = elegibles[sector_id]
        if plantas > agujeros.libres:
            excedidos[sector_id] = (sector, agujeros.libres)
        resultado.append((sector, plantas))
    if excedidos:
        detalle = "; ".join(f"{sector.nombre_sector} tiene {max(0, libres)} agujeros libres" for sector, libres in excedidos.values())
        raise _error(
            "supera_agujeros",
            f"La cantidad supera los agujeros disponibles: {detalle}. Indicá una cantidad menor o elegí otro sector.",
            "distribucion",
            {"libres": {sector_id: max(0, libres) for sector_id, (_, libres) in excedidos.items()}},
        )
    total = sum(n for _, n in resultado)
    if total != cantidad:
        quedan = cantidad - total
        detalle = f"faltan ubicar {quedan}" if quedan > 0 else f"te pasaste por {-quedan}"
        raise _error("distribucion_incompleta", f"La distribución tiene que sumar {cantidad} plantas: {detalle}.", "distribucion")
    return sorted(resultado, key=lambda par: par[0].pk)


def _verificar(actor, datos, hoy):
    """TODAS las verificaciones de PROD-REG-LTE, en el orden del caso de uso. Lee siempre de la base, así que sirve igual antes de bloquear (rechazar
    pronto y saber qué bloquear) y después de bloquear (extensión 10a). No escribe. Devuelve el `Plan`; el primer rechazo es un `ErrorDeProduccion`."""
    _exigir_agronomo_activo(actor)
    invernadero = _exigir_invernadero_disponible(actor, datos.invernadero_id)
    cantidad = _exigir_cantidad(datos.cantidad)
    costo = _exigir_costo(datos.costo_estimado)
    _exigir_fechas(datos.fecha_siembra, datos.fecha_ingreso_etapa, hoy)
    variedad = _variedad_activa(datos.variedad_id)
    etapa = _etapa_del_ciclo(variedad, datos.etapa_id)
    elegibles, _ = sectores_elegibles.sectores_elegibles(invernadero.pk, etapa.tipo_id, variedad.perfil_familia)
    if not elegibles:
        raise _error(
            "sin_sectores",
            f"No hay sectores activos compatibles con {etapa.nombre} con lugar libre: creá o activá un sector, o elegí otra etapa.",
            "etapa",
        )
    distribucion = _distribucion_valida(_pares(datos.distribucion), cantidad, elegibles)
    agujeros = api_sectores.agujeros_de([sector for sector, _ in distribucion])
    return Plan(invernadero, variedad, etapa, datos.fecha_siembra, datos.fecha_ingreso_etapa, cantidad, costo, distribucion, agujeros, hoy)


# ---- Lectura (pasos 2, 4, 6 y 8) ----


def invernaderos_disponibles(actor):
    """Paso 2 y extensión 2a: los invernaderos ACTIVOS a cargo del Agrónomo `actor` sin una siembra normal concretada, por nombre. Cualquier otra
    cuenta (o una inactiva) no tiene ninguno: la pantalla no muestra la acción. No escribe ni bloquea."""
    if actor is None or rol_de(actor) != Usuario.Rol.AGRONOMO or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
        return []
    con_siembras = Siembra.objects.filter(
        estado_orden=OrdenTrabajo.Estado.CONCRETADA, tipo_siembra=Siembra.TipoSiembra.NORMAL
    ).values("invernadero_id")
    return list(
        Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO, agronomo_id=actor.pk)
        .exclude(pk__in=con_siembras)
        .order_by(Lower("nombre_invernadero"), "pk")
    )


def datos_de_registro(actor, invernadero_id=None, variedad_id=None, etapa_id=None):
    """Lo que presentan los pasos 2, 4 y 6. No escribe ni bloquea.

    - Siempre: los invernaderos disponibles (paso 2).
    - Con `invernadero_id` (que tiene que seguir disponible: extensión 2a): las variedades activas con ciclo (paso 4).
    - Con `variedad_id` además: las etapas de su ciclo.
    - Con `etapa_id` además: los sectores elegibles con sus agujeros libres (paso 6) y los que no se pueden elegir. Si no hay ninguno elegible, la
      pantalla informa la extensión 7d.
    """
    _exigir_agronomo_activo(actor)
    invernaderos = invernaderos_disponibles(actor)
    ofrecidas, etapas, sectores, no_elegibles = [], [], [], []
    if invernadero_id is not None:
        invernadero = _exigir_invernadero_disponible(actor, invernadero_id)
        activas = list(variedades.variedades_activas())
        ciclos_de = ciclos.etapas_de([v.pk for v in activas]) if activas else {}
        ofrecidas = [VariedadOfrecida(v.pk, str(v), v.perfil_familia) for v in activas if ciclos_de[v.pk]]
        if variedad_id is not None:
            variedad = _variedad_activa(variedad_id)
            etapas = ciclos.etapas_de([variedad.pk])[variedad.pk]
            if etapa_id is not None:
                etapa = _etapa_del_ciclo(variedad, etapa_id)
                elegibles, no_elegibles = sectores_elegibles.sectores_elegibles(invernadero.pk, etapa.tipo_id, variedad.perfil_familia)
                sectores = [SectorOfrecido(s.pk, s.nombre_sector, a.libres) for s, a in elegibles.values()]
    return DatosDeRegistro(invernaderos, ofrecidas, etapas, sectores, no_elegibles)


def _asiento_previsto(costo):
    """El asiento del paso 8 (Debe Productos en Proceso / Haber Capital Inicial por `costo`), o `None` si el costo es 0 (H11)."""
    if costo <= 0:
        return None
    nombres = dict(
        CuentaContable.objects.filter(codigo_cuenta__in=[cuentas.PRODUCTOS_EN_PROCESO, cuentas.CAPITAL_INICIAL]).values_list(
            "codigo_cuenta", "nombre_cuenta"
        )
    )
    debe, haber = cuentas.PRODUCTOS_EN_PROCESO, cuentas.CAPITAL_INICIAL
    return AsientoPrevisto((debe, nombres.get(debe, debe)), (haber, nombres.get(haber, haber)), costo)


def resumen_de_registro(actor, datos, *, hoy=None):
    """Paso 8: valida TODO (los mismos rechazos que `registrar_lote_existente`) y devuelve el resumen: la variedad, la etapa, las fechas, las cantidades,
    el costo estimado y por planta, la ocupación por sector con los agujeros que quedan libres y el asiento que se registrará. No escribe ni bloquea:
    lo que se presenta puede cambiar hasta la confirmación, que lo vuelve a verificar (extensión 10a)."""
    plan = _verificar(actor, datos, hoy or timezone.localdate())
    return ResumenDeRegistro(
        plan.invernadero,
        plan.variedad,
        plan.etapa,
        plan.fecha_siembra,
        plan.fecha_ingreso_etapa,
        plan.cantidad,
        plan.costo,
        (plan.costo / plan.cantidad).quantize(CENTAVOS, rounding=ROUND_HALF_UP),
        [SectorDelResumen(s.pk, s.nombre_sector, n, plan.agujeros[s.pk].libres - n) for s, n in plan.distribucion],
        _asiento_previsto(plan.costo),
    )


# ---- PROD-REG-LTE ----


def registrar_lote_existente(actor, datos, *, hoy=None):
    """PROD-REG-LTE: registra un lote existente y devuelve el `Lote`.

    - Precondiciones y reglas: ver `_verificar`; se hacen antes de bloquear (rechazo pronto) y DE NUEVO después (extensión 10a). Las precondiciones
      contables (ejercicio y cuentas) se cumplen solas (D-92 punto 2).
    - Postcondición a: la siembra «concretada» de carga inicial (sin Capataz, sin reservas ni consumos). b: el lote «activo» con la cantidad indicada,
      en la etapa elegida y con el costo estimado como costo acumulado, y la entrada de bitácora `carga_inicial`. c: una ocupación por sector; los
      agujeros libres bajan (se derivan, D-50). d: el asiento Debe Productos en Proceso / Haber Capital Inicial por el costo, con la fecha ACTUAL
      (D-92 punto 4); con costo 0, ninguno (H11). e y D-36: UN registro `registro_lote_existente`.
    - Bloqueos (`FOR NO KEY UPDATE`, docs/patrones/bloqueos.md): la cuenta del Agrónomo → el invernadero → la variedad → los sectores (orden de id) →
      las filas nuevas (no hace falta bloquearlas) → el ejercicio (lo toma el servicio de asientos, al final). Todo o nada (D-22).
    """
    hoy = hoy or timezone.localdate()
    pronto = _verificar(actor, datos, hoy)
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk))
        _exigir_agronomo_activo(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(bloquear_invernadero_activo, pronto.invernadero.pk, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)})
        _bloquear(bloquear_variedad, pronto.variedad.pk, equivalencias={"variedad_inactiva": ("variedad_inactiva", "variedad")})
        _bloquear(
            api_sectores.bloquear_sectores,
            pronto.invernadero.pk,
            [sector.pk for sector, _ in pronto.distribucion],
            equivalencias={"sector_no_disponible": ("sector_no_elegible", "distribucion")},
        )
        plan = _verificar(actor, datos, hoy)  # extensión 10a: todo de nuevo, con lo bloqueado
        return _escribir(actor, plan)


def _escribir(actor, plan):
    """Pasos 10 y 11: crea la siembra, el lote, las ocupaciones, la bitácora y el asiento, y deja el único registro de auditoría."""
    hoy = plan.hoy
    sectores = [sector for sector, _ in plan.distribucion]
    nombre_de_la_etapa = plan.etapa.nombre
    # Fechas de la orden: las tres en hoy (ver el encabezado: D-92 punto 12 pedía `fecha_programada_orden` = la de siembra, imposible con el CHECK).
    siembra = Siembra.objects.create(
        tipo_orden=OrdenTrabajo.Tipo.SIEMBRA,
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=hoy,
        fecha_programada_orden=hoy,
        fecha_resolucion_orden=hoy,
        estado_orden=OrdenTrabajo.Estado.CONCRETADA,
        agronomo_id=actor.pk,
        invernadero=plan.invernadero,
        capataz=None,
        tipo_siembra=Siembra.TipoSiembra.CARGA_INICIAL,
        cant_plantines_siembra=plan.cantidad,
        fecha_siembra=plan.fecha_siembra,
        variedad=plan.variedad,
    )
    # Crearlo no es «cambiar el costo»: no pasa por `costos.py` (D-92 punto 12).
    lote = Lote.objects.create(
        invernadero=plan.invernadero,
        etapa_id=plan.etapa.etapa_id,
        siembra=siembra,
        cantidad_inicial=plan.cantidad,
        cantidad_actual=plan.cantidad,
        costo_acumulado=plan.costo,
    )
    ocupaciones = [
        OcupacionSector.objects.create(
            orden=siembra, sector=sector, lote=lote, cant_agujeros_planificados=plantas, cant_agujeros_ocupados=plantas
        )
        for sector, plantas in plan.distribucion
    ]
    descripcion = (
        f"Carga inicial del lote {lote.codigo}: {plan.cantidad} plantas de {plan.variedad} en {nombre_de_la_etapa}, "
        f"desde el {plan.fecha_ingreso_etapa:%d/%m/%Y}."
    )[:LARGO_DE_LA_DESCRIPCION]
    bitacora = Bitacora.objects.create(
        invernadero=plan.invernadero,
        lote=lote,
        etapa_id=plan.etapa.etapa_id,
        responsable_id=actor.pk,
        fecha_bitacora=plan.fecha_ingreso_etapa,
        hora_bitacora=timezone.localtime().time(),
        tipo_evento=Bitacora.TipoEvento.CARGA_INICIAL,
        descripcion_evento=descripcion,
    )
    bitacora.sectores.set(sectores)
    asiento = None
    if plan.costo > 0:  # H11: con costo 0 no hay asiento. Se llama con todo lo propio ya bloqueado: el ejercicio se bloquea al final (D-86).
        asiento = asientos.registrar_asiento_automatico(
            actor,
            siembra,
            hoy,  # D-92 punto 4: el lote existente usa la fecha ACTUAL, no la de la siembra
            [(cuentas.PRODUCTOS_EN_PROCESO, DEBE, plan.costo), (cuentas.CAPITAL_INICIAL, HABER, plan.costo)],
            descripcion=f"Carga inicial del lote {lote.codigo}: {plan.variedad} en {nombre_de_la_etapa}"[:LARGO_DEL_ASIENTO],
            hoy=hoy,
        )
    despues = api_sectores.agujeros_de(sectores)
    datos = {
        "invernadero": referencia(plan.invernadero),
        "variedad": referencia(plan.variedad),
        "etapa": nombre_de_la_etapa,
        "lote": referencia(lote),
        "tipo_siembra": Siembra.TipoSiembra.CARGA_INICIAL.value,
        "cantidad_sembrada": str(plan.cantidad),
        "fecha_siembra": f"{plan.fecha_siembra:%d/%m/%Y}",
        "fecha_ingreso_etapa": f"{plan.fecha_ingreso_etapa:%d/%m/%Y}",
        "costo_estimado": str(plan.costo),
    }
    if asiento is not None:
        datos["asiento"] = referencia(asiento)
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.REGISTRO_LOTE_EXISTENTE,
        afectados=[siembra, lote, *ocupaciones, *sectores, bitacora, *([asiento] if asiento is not None else [])],
        detalle={
            "cambios": {
                "agujeros_ocupados": {
                    "antes": [f"{s.nombre_sector}: {plan.agujeros[s.pk].ocupados}" for s in sectores],
                    "despues": [f"{s.nombre_sector}: {despues[s.pk].ocupados}" for s in sectores],
                }
            },
            "datos": datos,
        },
    )
    return lote
