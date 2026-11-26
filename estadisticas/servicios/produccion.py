# Estadísticas de producción (EST-CNS-PRD; D-93 punto 3): una función por indicador, todas de solo lectura y con un número fijo de
# consultas agregadas por bloque (D-93 punto 7), más `estadisticas_de_produccion`, que las arma con el alcance del actor.
# Dinero y porcentajes en `Decimal`, nunca `float`. Fuente de cada fórmula: D-93 punto 3.

from collections import namedtuple
from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest

from estadisticas.periodos import anterior, comparar
from inventario.unidades import Unidad
from iot.alertas import CODIGOS_DE_ALERTAS_IOT, TIPOS_DE_ALERTA_DE_IOT
from maestros import extensiones
from maestros.models import Alerta, Invernadero
from produccion.models import Consumo, Lote, Merma as ModeloMerma, MovimientoStock, OrdenTrabajo, Siembra
from produccion.servicios.ordenes import TIPOS_DE_PRODUCCION

# ---- Lo que devuelve cada indicador ----

# 1. Plantas sembradas y cosechadas, por variedad. `cosechadas` es None si la cosecha no está disponible (D-93 punto 5).
FilaDeVariedad = namedtuple("FilaDeVariedad", "variedad_id variedad sembradas cosechadas")
SembradasYCosechadas = namedtuple("SembradasYCosechadas", "filas sembradas cosechadas cosecha_disponible")

# 2. Merma: porcentaje sobre (en producción al inicio + sembradas en el período) y reparto por causa.
FilaDeCausa = namedtuple("FilaDeCausa", "causa texto plantas porcentaje")
ResultadoDeMerma = namedtuple("ResultadoDeMerma", "perdidas al_inicio sembradas_en_el_periodo denominador porcentaje por_causa")

# 3. Órdenes a tiempo frente a vencidas, con el desglose por tipo de orden.
FilaDeOrdenes = namedtuple("FilaDeOrdenes", "tipo texto a_tiempo vencidas total porcentaje_a_tiempo")
OrdenesATiempo = namedtuple("OrdenesATiempo", "filas a_tiempo vencidas total porcentaje_a_tiempo porcentaje_vencidas")

# 4. Costo promedio por planta cosechada. `costo_por_planta` es None sin plantas cosechadas o sin cosecha disponible.
CostoPorPlanta = namedtuple("CostoPorPlanta", "disponible plantas costo costo_por_planta")

# 5. Consumo de insumos: monto por categoría y cantidad por insumo (con su unidad) dentro de ella.
FilaDeInsumo = namedtuple("FilaDeInsumo", "insumo_id nombre unidad unidad_texto cantidad monto")
FilaDeCategoria = namedtuple("FilaDeCategoria", "tipo_insumo_id nombre monto insumos")
ConsumoDeInsumos = namedtuple("ConsumoDeInsumos", "categorias monto_total")

# 6. Alertas del IoT por tipo. La función devuelve None si ningún invernadero del alcance tiene IoT (el bloque no se muestra).
FilaDeAlertas = namedtuple("FilaDeAlertas", "codigo texto cantidad")
AlertasIot = namedtuple("AlertasIot", "filas total")

# Un invernadero del alcance del actor (lo que llena el selector de invernadero de la pantalla).
InvernaderoDelAlcance = namedtuple("InvernaderoDelAlcance", "pk nombre")

# Los seis bloques de un período y lo que arma `estadisticas_de_produccion`. `previo` y `comparaciones` quedan en None y {} sin comparar;
# `comparaciones` tiene una `Comparacion` por indicador que se muestra (sembradas, cosechadas, merma, ordenes_a_tiempo, costo_por_planta,
# consumo y, si hay IoT, alertas_iot).
Bloques = namedtuple("Bloques", "sembradas_y_cosechadas merma ordenes costo consumo alertas_iot")
EstadisticasDeProduccion = namedtuple(
    "EstadisticasDeProduccion", "periodo anterior invernaderos invernadero_id actual previo comparaciones"
)

# Las causas de merma de partidas en cámara: producto ya cosechado, no plantas en producción (D-93 punto 3.2).
CAUSAS_DE_CAMARA = (ModeloMerma.Causa.DANO_EN_CAMARA, ModeloMerma.Causa.VENCIMIENTO_EN_CAMARA)
UN_DECIMAL = Decimal("0.1")
DOS_DECIMALES = Decimal("0.01")


def _porcentaje(parte, total):
    """`parte` ÷ `total` × 100 con un decimal (`ROUND_HALF_UP`); `None` («—») si `total` es 0."""
    if not total:
        return None
    return (Decimal(parte) * 100 / Decimal(total)).quantize(UN_DECIMAL, rounding=ROUND_HALF_UP)


def _rango(periodo):
    """Los extremos del período, como los pide `__range` (los dos días incluidos)."""
    return (periodo.desde, periodo.hasta)


def cosecha_disponible():
    """El `disponible()` de los indicadores que leen la cosecha (1, cosechadas, y 4; D-93 punto 5): la app `produccion` está instalada y
    tiene el modelo `MovimientoStock`. Sin `try/except` sobre consultas."""
    return apps.is_installed("produccion") and "movimientostock" in apps.get_app_config("produccion").models


def _cosechas_del_periodo(invernadero_ids, periodo):
    """Las salidas por cosecha de los invernaderos con su fecha (local) dentro del período."""
    return MovimientoStock.objects.filter(
        tipo_movimiento=MovimientoStock.TipoMovimiento.SALIDA_POR_COSECHA,
        lote__invernadero_id__in=list(invernadero_ids),
        fecha__date__range=_rango(periodo),
    )


def sembradas_y_cosechadas(invernadero_ids, periodo):
    """Indicador 1: plantas sembradas (siembras normales concretadas con `fecha_siembra` en el período: la carga inicial no es una siembra del
    período, D-92 punto 12) y cosechadas (salidas por cosecha del período), por variedad (D-93 punto 3.1). 2 consultas."""
    disponible = cosecha_disponible()
    filas = {}  # variedad_id -> [nombre, sembradas, cosechadas]

    def fila(variedad_id, cultivo, variedad):
        return filas.setdefault(variedad_id, [f"{cultivo} {variedad}", 0, 0 if disponible else None])

    sembradas = (
        Lote.objects.filter(
            invernadero_id__in=list(invernadero_ids),
            siembra__tipo_siembra=Siembra.TipoSiembra.NORMAL,
            siembra__fecha_siembra__range=_rango(periodo),
        )
        .values("siembra__variedad_id", "siembra__variedad__cultivo__nombre_cultivo", "siembra__variedad__nombre_variedad")
        .annotate(total=Sum("cantidad_inicial"))
        .order_by()
    )
    for f in sembradas:
        fila(f["siembra__variedad_id"], f["siembra__variedad__cultivo__nombre_cultivo"], f["siembra__variedad__nombre_variedad"])[1] = f["total"]
    if disponible:
        cosechadas = (
            _cosechas_del_periodo(invernadero_ids, periodo)
            .values("lote__siembra__variedad_id", "lote__siembra__variedad__cultivo__nombre_cultivo", "lote__siembra__variedad__nombre_variedad")
            .annotate(total=Sum("cantidad"))
            .order_by()
        )
        for f in cosechadas:
            fila(
                f["lote__siembra__variedad_id"], f["lote__siembra__variedad__cultivo__nombre_cultivo"], f["lote__siembra__variedad__nombre_variedad"]
            )[2] = f["total"]
    ordenadas = sorted((nombre, vid, s, c) for vid, (nombre, s, c) in filas.items())
    return SembradasYCosechadas(
        filas=[FilaDeVariedad(vid, nombre, s, c) for nombre, vid, s, c in ordenadas],
        sembradas=sum(s for _, _, s, _ in ordenadas),
        cosechadas=sum(c for _, _, _, c in ordenadas) if disponible else None,
        cosecha_disponible=disponible,
    )


def _plantas_al_inicio(invernadero_ids, periodo):
    """Plantas en producción al inicio del período: por cada lote con `fecha_siembra` anterior a «desde» (también los de carga inicial),
    `cantidad_inicial` − sus mermas anteriores − sus plantas cosechadas anteriores, sin bajar de 0 (D-93 punto 3.2 con D-103). 1 consulta."""
    entero = IntegerField()
    mermas = (
        ModeloMerma.objects.filter(lote=OuterRef("pk"), fecha_bitacora__lt=periodo.desde)
        .exclude(causa__in=CAUSAS_DE_CAMARA)
        .order_by()
        .values("lote")
        .annotate(total=Sum("cant_merma"))
        .values("total")
    )
    previas = Coalesce(Subquery(mermas, output_field=entero), Value(0), output_field=entero)
    if cosecha_disponible():
        cosechas = (
            MovimientoStock.objects.filter(
                lote=OuterRef("pk"), tipo_movimiento=MovimientoStock.TipoMovimiento.SALIDA_POR_COSECHA, fecha__date__lt=periodo.desde
            )
            .order_by()
            .values("lote")
            .annotate(total=Sum("cantidad"))
            .values("total")
        )
        cosechadas = Coalesce(Subquery(cosechas, output_field=entero), Value(0), output_field=entero)
    else:
        cosechadas = Value(0, output_field=entero)
    base = Greatest(F("cantidad_inicial") - previas - cosechadas, Value(0), output_field=entero)
    total = (
        Lote.objects.filter(invernadero_id__in=list(invernadero_ids), siembra__fecha_siembra__lt=periodo.desde)
        .annotate(base=base)
        .aggregate(total=Sum("base"))["total"]
    )
    return total or 0


def merma(invernadero_ids, periodo):
    """Indicador 2 (D-93 punto 3.2): plantas perdidas en el período (mermas de lotes: no las de partidas en cámara) ÷ (plantas en producción
    al inicio + plantas sembradas en el período, también las cargas iniciales) × 100, y el reparto por causa. 3 consultas."""
    ids = list(invernadero_ids)
    cuentas = (
        ModeloMerma.objects.filter(invernadero_id__in=ids, fecha_bitacora__range=_rango(periodo))
        .exclude(causa__in=CAUSAS_DE_CAMARA)
        .values("causa")
        .annotate(plantas=Sum("cant_merma"))
        .order_by()
    )
    por_causa = sorted(((f["causa"], f["plantas"]) for f in cuentas), key=lambda f: (-f[1], f[0]))
    perdidas = sum(plantas for _, plantas in por_causa)
    al_inicio = _plantas_al_inicio(ids, periodo)
    del_periodo = Lote.objects.filter(invernadero_id__in=ids, siembra__fecha_siembra__range=_rango(periodo)).aggregate(
        normales=Sum("cantidad_inicial", filter=Q(siembra__tipo_siembra=Siembra.TipoSiembra.NORMAL)),
        cargas=Sum("cantidad_inicial", filter=Q(siembra__tipo_siembra=Siembra.TipoSiembra.CARGA_INICIAL)),
    )
    sembradas = (del_periodo["normales"] or 0) + (del_periodo["cargas"] or 0)
    denominador = al_inicio + sembradas
    return ResultadoDeMerma(
        perdidas=perdidas,
        al_inicio=al_inicio,
        sembradas_en_el_periodo=sembradas,
        denominador=denominador,
        porcentaje=_porcentaje(perdidas, denominador),
        por_causa=[FilaDeCausa(causa, ModeloMerma.Causa(causa).label, plantas, _porcentaje(plantas, perdidas)) for causa, plantas in por_causa],
    )


def ordenes_a_tiempo(invernadero_ids, periodo, hoy, solo_produccion=False):
    """Indicador 3 (D-93 punto 3.3): las órdenes con `fecha_programada_orden` en el período, sin las canceladas (con «Solo de producción»,
    solo siembra, transición y cosecha). A tiempo: concretada con resolución ≤ programada. Vencida: concretada después, o «a realizar» con
    programada < hoy; las «a realizar» que todavía no vencen no cuentan. 1 consulta."""
    Estado = OrdenTrabajo.Estado
    consulta = OrdenTrabajo.objects.filter(
        invernadero_id__in=list(invernadero_ids), fecha_programada_orden__range=_rango(periodo)
    ).exclude(estado_orden=Estado.CANCELADA)
    if solo_produccion:
        consulta = consulta.filter(tipo_orden__in=list(TIPOS_DE_PRODUCCION))
    a_tiempo = Q(estado_orden=Estado.CONCRETADA, fecha_resolucion_orden__lte=F("fecha_programada_orden"))
    vencida = Q(estado_orden=Estado.CONCRETADA, fecha_resolucion_orden__gt=F("fecha_programada_orden")) | Q(
        estado_orden=Estado.A_REALIZAR, fecha_programada_orden__lt=hoy
    )
    por_tipo = {
        f["tipo_orden"]: (f["a_tiempo"], f["vencidas"])
        for f in consulta.values("tipo_orden")
        .annotate(a_tiempo=Count("pk", filter=a_tiempo), vencidas=Count("pk", filter=vencida))
        .order_by()
    }
    filas = []
    for tipo in OrdenTrabajo.Tipo:  # en el orden de la lista: siembra, transición, cosecha, entrega, mantenimiento
        a, v = por_tipo.get(tipo.value, (0, 0))
        if a + v:
            filas.append(FilaDeOrdenes(tipo.value, tipo.label, a, v, a + v, _porcentaje(a, a + v)))
    a_tiempo_total = sum(f.a_tiempo for f in filas)
    vencidas_total = sum(f.vencidas for f in filas)
    total = a_tiempo_total + vencidas_total
    return OrdenesATiempo(
        filas, a_tiempo_total, vencidas_total, total, _porcentaje(a_tiempo_total, total), _porcentaje(vencidas_total, total)
    )


def costo_por_planta_cosechada(invernadero_ids, periodo):
    """Indicador 4 (D-93 punto 3.4): Σ costo de las salidas por cosecha del período (cantidad × costo por planta de cada movimiento) ÷ Σ
    plantas cosechadas, a 2 decimales (`ROUND_HALF_UP`). Sin cosecha disponible, no se muestra. 1 consulta."""
    if not cosecha_disponible():
        return CostoPorPlanta(False, None, None, None)
    costo_del_movimiento = ExpressionWrapper(
        F("cantidad") * F("costo_unitario"), output_field=DecimalField(max_digits=24, decimal_places=4)
    )
    totales = _cosechas_del_periodo(invernadero_ids, periodo).aggregate(plantas=Sum("cantidad"), costo=Sum(costo_del_movimiento))
    plantas = totales["plantas"] or 0
    costo = totales["costo"] or Decimal("0")
    por_planta = (costo / plantas).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP) if plantas else None
    return CostoPorPlanta(True, plantas, costo, por_planta)


def consumo_de_insumos(invernadero_ids, periodo):
    """Indicador 5 (D-93 punto 3.5): los consumos con su fecha en el período (siembra, aplicación y envases de entregas): monto por categoría
    y total; cantidad por insumo, con su unidad, dentro de su categoría (las de insumos distintos no se suman). 1 consulta."""
    c = "insumo_invernadero__insumo"
    filas = (
        Consumo.objects.filter(invernadero_id__in=list(invernadero_ids), fecha_consumo__range=_rango(periodo))
        .values(f"{c}_id", f"{c}__nombre_insumo", f"{c}__unidad_medida_insumo", f"{c}__tipo_insumo_id", f"{c}__tipo_insumo__nombre_tipo_insumo")
        .annotate(cantidad=Sum("cant_consumo"), monto=Sum("monto_consumo"))
        .order_by()
    )
    categorias = {}  # tipo_insumo_id -> [nombre, monto, [FilaDeInsumo]]
    for f in filas:
        unidad = f[f"{c}__unidad_medida_insumo"]
        categoria = categorias.setdefault(f[f"{c}__tipo_insumo_id"], [f[f"{c}__tipo_insumo__nombre_tipo_insumo"], Decimal("0"), []])
        categoria[1] += f["monto"]
        categoria[2].append(FilaDeInsumo(f[f"{c}_id"], f[f"{c}__nombre_insumo"], unidad, Unidad(unidad).label, f["cantidad"], f["monto"]))
    resultado = [
        FilaDeCategoria(tipo_id, nombre, monto, sorted(insumos, key=lambda i: i.nombre))
        for tipo_id, (nombre, monto, insumos) in sorted(categorias.items(), key=lambda par: par[1][0])
    ]
    return ConsumoDeInsumos(resultado, sum((cat.monto for cat in resultado), Decimal("0")))


def alertas_iot(invernadero_ids, periodo):
    """Indicador 6 (D-93 punto 3.6): las alertas de los tipos del IoT con su fecha (local) en el período, por tipo y de mayor a menor, solo
    de los invernaderos con sistema IoT; `None` si ninguno lo tiene (el bloque no se muestra). 2 consultas."""
    ids = list(invernadero_ids)
    estados = extensiones.estados_iot(ids)  # una sola llamada para todos (una consulta)
    con_iot = [i for i in ids if i in estados]
    if not con_iot:
        return None
    nombres = {codigo: nombre for codigo, nombre, *_ in TIPOS_DE_ALERTA_DE_IOT}
    cuentas = (
        Alerta.objects.filter(
            invernadero_id__in=con_iot, tipo_alerta__in=CODIGOS_DE_ALERTAS_IOT, fecha_hora_alerta__date__range=_rango(periodo)
        )
        .values("tipo_alerta")
        .annotate(cantidad=Count("pk"))
        .order_by()
    )
    filas = sorted(
        (FilaDeAlertas(f["tipo_alerta"], nombres[f["tipo_alerta"]], f["cantidad"]) for f in cuentas), key=lambda f: (-f.cantidad, f.codigo)
    )
    return AlertasIot(filas, sum(f.cantidad for f in filas))


def _bloques(ids, periodo, hoy, solo_produccion):
    """Los seis indicadores de un período."""
    return Bloques(
        sembradas_y_cosechadas(ids, periodo),
        merma(ids, periodo),
        ordenes_a_tiempo(ids, periodo, hoy, solo_produccion),
        costo_por_planta_cosechada(ids, periodo),
        consumo_de_insumos(ids, periodo),
        alertas_iot(ids, periodo),
    )


def _comparaciones(actual, previo):
    """Una `Comparacion` por indicador que se muestra (D-93 punto 2: diferencia absoluta y porcentual contra el período anterior)."""
    comparaciones = {
        "sembradas": comparar(actual.sembradas_y_cosechadas.sembradas, previo.sembradas_y_cosechadas.sembradas),
        "cosechadas": comparar(actual.sembradas_y_cosechadas.cosechadas, previo.sembradas_y_cosechadas.cosechadas),
        "merma": comparar(actual.merma.porcentaje, previo.merma.porcentaje),
        "ordenes_a_tiempo": comparar(actual.ordenes.porcentaje_a_tiempo, previo.ordenes.porcentaje_a_tiempo),
        "costo_por_planta": comparar(actual.costo.costo_por_planta, previo.costo.costo_por_planta),
        "consumo": comparar(actual.consumo.monto_total, previo.consumo.monto_total),
    }
    if actual.alertas_iot is not None and previo.alertas_iot is not None:
        comparaciones["alertas_iot"] = comparar(actual.alertas_iot.total, previo.alertas_iot.total)
    return comparaciones


def estadisticas_de_produccion(actor, invernadero_id, periodo, comparar_con_anterior, hoy, solo_produccion=False):
    """Arma los seis indicadores del período (y los del anterior si `comparar_con_anterior`) para los invernaderos del alcance de `actor`: el
    Agrónomo, los suyos activos; el Gerente, todos (`Invernadero.objects.en_alcance_de`); `invernadero_id` filtra por uno (fuera del alcance:
    `ValidationError`). Es una consulta: no audita (EST-CNS-PRD regla 9)."""
    alcance = [
        InvernaderoDelAlcance(pk, nombre)
        for pk, nombre in Invernadero.objects.en_alcance_de(actor).order_by("nombre_invernadero").values_list("pk", "nombre_invernadero")
    ]
    if invernadero_id is not None and invernadero_id not in {i.pk for i in alcance}:
        raise ValidationError("No tenés acceso a ese invernadero.", code="invernadero_fuera_de_alcance")
    ids = [invernadero_id] if invernadero_id is not None else [i.pk for i in alcance]
    del_anterior = anterior(periodo)
    actual = _bloques(ids, periodo, hoy, solo_produccion)
    previo = _bloques(ids, del_anterior, hoy, solo_produccion) if comparar_con_anterior else None
    return EstadisticasDeProduccion(
        periodo, del_anterior, alcance, invernadero_id, actual, previo, _comparaciones(actual, previo) if previo else {}
    )
