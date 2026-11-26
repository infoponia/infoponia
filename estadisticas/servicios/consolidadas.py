# Estadísticas consolidadas del Gerente (EST-CNS-CNS, EST-02; D-93 punto 4): una función por indicador, todas de solo lectura y con un número fijo
# de consultas agregadas por bloque (D-93 punto 7), más `estadisticas_consolidadas`, que arma la pestaña elegida. Dinero y porcentajes en `Decimal`.
# Indicador 7 («producción comparando invernaderos») reutiliza los filtros de EST-01 (`produccion._…`); el 8 (comerciales, EST-03) llama a `comercial` (H25).
# Diferencia con D-93 punto 4.7 (decidida por el estudiante, 26/11/2026): además de una fila por invernadero activo hay una fila «Dados de baja» y el
# total es el de toda la organización (igual al de EST-01 para el Gerente); así no se pierde la historia de un invernadero dado de baja en el período.

from collections import namedtuple
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Count, DecimalField, Exists, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum

from comercial.servicios import estadisticas as estadisticas_comerciales
from compras.models import DetalleCorreccionRecepcion, DetalleOrdenCompra, DetalleRecepcion
from compras.precios import valor_recibido
from contabilidad import cuentas
from contabilidad.constantes import DEBE
from contabilidad.models import CuentaContable, MovimientoContable
from contabilidad.servicios import libro as servicio_del_libro
from core.models import Usuario, rol_de
from estadisticas import periodos
from estadisticas.servicios import produccion
from estadisticas.servicios.produccion import CAUSAS_DE_CAMARA, DOS_DECIMALES, _porcentaje
from maestros import extensiones
from maestros.models import Invernadero
from produccion.models import Merma, MovimientoStock, Siembra

CERO = Decimal("0.00")

# ---- Lo que devuelve cada indicador ----

# 7. Una fila por invernadero activo, la fila agrupada de los dados de baja con actividad y el total. `merma`, `ordenes_a_tiempo` y `costo_por_planta` son
# `None` («—») sin base; `cosechadas` y `costo_por_planta`, `None` sin la cosecha (D-93 punto 5); `alertas_iot`, `None` si ningún invernadero de la fila tiene IoT.
FilaDeInvernadero = namedtuple("FilaDeInvernadero", "invernadero_id nombre sembradas cosechadas merma ordenes_a_tiempo costo_por_planta consumo alertas_iot")
PorInvernadero = namedtuple("PorInvernadero", "filas dados_de_baja total")
# La merma en cámara, aparte. `valor` es `None` («—») si a alguna merma que debería tener asiento (costo mayor que cero) todavía le falta (`sin_asiento`).
FilaDeCausaDeCamara = namedtuple("FilaDeCausaDeCamara", "causa texto plantas")
MermaEnCamara = namedtuple("MermaEnCamara", "causas plantas valor sin_asiento")
# 9. Compras del período: total, por proveedor y por categoría (`clave` es el id) y por mes.
FilaDeCompra = namedtuple("FilaDeCompra", "clave nombre monto")
FilaDeMes = namedtuple("FilaDeMes", "anio mes monto")
Compras = namedtuple("Compras", "total por_proveedor por_categoria por_mes")
# 10. Libro de gestión: ventas, ingresos, egresos y resultado, y el detalle por cuenta de resultado con saldo.
FilaDeCuenta = namedtuple("FilaDeCuenta", "codigo nombre monto")
LibroDeGestion = namedtuple("LibroDeGestion", "ventas ingresos egresos resultado ingresos_por_cuenta costos_por_cuenta")

def _exigir_gerente(actor):
    """Regla 1 de EST-CNS-CNS: solo el Gerente activo (el Contador tiene el libro; el Vendedor, sus estadísticas comerciales). `PermissionDenied` si no."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo el Gerente consulta las estadísticas consolidadas.")


PESTANAS = ("resumen", "produccion", "comercial", "compras", "resultados")
# Lo que arma `estadisticas_consolidadas`. Solo se llenan los indicadores que la pestaña muestra; `previo` es el mismo armado del período anterior.
Consolidadas = namedtuple("Consolidadas", "pestana periodo anterior actual previo comparaciones")
Bloques = namedtuple("Bloques", "por_invernadero merma_en_camara comerciales compras libro")


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 7 · Producción comparando invernaderos
# ---------------------------------------------------------------------------------------------------------------------------------


def _sumas_por_invernadero(ids, periodo, hoy, solo_produccion):
    """Lo que cada indicador suma por invernadero, en 8 o 9 consultas fijas (la cosecha y el IoT las ahorran si no hay). Los porcentajes se
    calculan después sobre las sumas (numeradores y denominadores), nunca promediando porcentajes."""
    sumas = {i: dict(sembradas=0, cargas=0, cosechadas=0, costo=Decimal("0"), perdidas=0, al_inicio=0, a_tiempo=0, vencidas=0, consumo=Decimal("0"), alertas=0) for i in ids}
    for f in (
        produccion._lotes_sembrados_en(ids, periodo)
        .values("invernadero_id")
        .annotate(
            normales=Sum("cantidad_inicial", filter=Q(siembra__tipo_siembra=Siembra.TipoSiembra.NORMAL)),
            cargas=Sum("cantidad_inicial", filter=Q(siembra__tipo_siembra=Siembra.TipoSiembra.CARGA_INICIAL)),
        )
        .order_by()
    ):
        sumas[f["invernadero_id"]]["sembradas"] = f["normales"] or 0
        sumas[f["invernadero_id"]]["cargas"] = f["cargas"] or 0
    if produccion.cosecha_disponible():
        for f in (
            produccion._cosechas_del_periodo(ids, periodo)
            .values("lote__invernadero_id")
            .annotate(plantas=Sum("cantidad"), costo=Sum(produccion._costo_de_la_cosecha()))
            .order_by()
        ):
            sumas[f["lote__invernadero_id"]]["cosechadas"] = f["plantas"]
            sumas[f["lote__invernadero_id"]]["costo"] = f["costo"]
    for f in produccion._mermas_de_lotes(ids, periodo).values("invernadero_id").annotate(plantas=Sum("cant_merma")).order_by():
        sumas[f["invernadero_id"]]["perdidas"] = f["plantas"]
    for invernadero_id, plantas in produccion._plantas_al_inicio(ids, periodo, por_invernadero=True).items():
        sumas[invernadero_id]["al_inicio"] = plantas
    a_tiempo, vencida = produccion._condiciones_de_ordenes(hoy)
    for f in (
        produccion._ordenes_del_periodo(ids, periodo, solo_produccion)
        .values("invernadero_id")
        .annotate(a_tiempo=Count("pk", filter=a_tiempo), vencidas=Count("pk", filter=vencida))
        .order_by()
    ):
        sumas[f["invernadero_id"]]["a_tiempo"] = f["a_tiempo"]
        sumas[f["invernadero_id"]]["vencidas"] = f["vencidas"]
    for f in produccion._consumos_del_periodo(ids, periodo).values("invernadero_id").annotate(monto=Sum("monto_consumo")).order_by():
        sumas[f["invernadero_id"]]["consumo"] = f["monto"]
    estados = extensiones.estados_iot(ids)  # una sola llamada para todos (una consulta)
    con_iot = [i for i in ids if i in estados]
    if con_iot:
        for f in produccion._alertas_del_periodo(con_iot, periodo).values("invernadero_id").annotate(cantidad=Count("pk")).order_by():
            sumas[f["invernadero_id"]]["alertas"] = f["cantidad"]
    return sumas, set(con_iot)


SUMAS_DE_DINERO = ("costo", "consumo")


def _sumar(grupo, sumas):
    """Suma, clave por clave, lo de los invernaderos del grupo (los importes en `Decimal`, lo demás entero)."""
    return {clave: sum((sumas[i][clave] for i in grupo), Decimal("0") if clave in SUMAS_DE_DINERO else 0) for clave in sumas[grupo[0]]}


def _fila(invernadero_id, nombre, grupo, sumas, con_iot, hay_cosecha):
    """La `FilaDeInvernadero` de un grupo de invernaderos (uno, los dados de baja o todos): suma sus numeradores y denominadores y recién ahí calcula
    los porcentajes y el costo por planta."""
    t = _sumar(grupo, sumas)
    por_planta = (t["costo"] / t["cosechadas"]).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP) if hay_cosecha and t["cosechadas"] else None
    return FilaDeInvernadero(
        invernadero_id,
        nombre,
        t["sembradas"],
        t["cosechadas"] if hay_cosecha else None,
        _porcentaje(t["perdidas"], t["al_inicio"] + t["sembradas"] + t["cargas"]),
        _porcentaje(t["a_tiempo"], t["a_tiempo"] + t["vencidas"]),
        por_planta,
        t["consumo"],
        t["alertas"] if any(i in con_iot for i in grupo) else None,
    )


def _hubo_actividad(grupo, sumas):
    """Si los invernaderos del grupo hicieron algo en el período: sembraron (también cargas iniciales), cosecharon, perdieron plantas, tuvieron órdenes,
    consumieron o alertaron. Lo que había «al inicio» no es actividad del período."""
    t = _sumar(grupo, sumas)
    return any((t["sembradas"], t["cargas"], t["cosechadas"], t["perdidas"], t["a_tiempo"], t["vencidas"], t["consumo"], t["alertas"]))


def por_invernadero(periodo, hoy, solo_produccion=False):
    """Indicador 7 (D-93 punto 4.7): una fila por invernadero activo con los indicadores 1 a 5 (y el 6 si tiene IoT), una fila «Dados de baja» con los
    inactivos que tuvieron actividad en el período (si no, `None`) y el total de todos, activos e inactivos (igual al de EST-01 para el Gerente).
    9 consultas fijas (el alcance y 8 de los indicadores), no una por invernadero."""
    todos = list(Invernadero.objects.order_by("nombre_invernadero").values_list("pk", "nombre_invernadero", "estado_invernadero"))
    ids = [pk for pk, _, _ in todos]
    hay_cosecha = produccion.cosecha_disponible()
    if not ids:
        return PorInvernadero([], None, FilaDeInvernadero(None, "Total", 0, 0 if hay_cosecha else None, None, None, None, Decimal("0"), None))
    sumas, con_iot = _sumas_por_invernadero(ids, periodo, hoy, solo_produccion)
    activos = [(pk, nombre) for pk, nombre, estado in todos if estado == Invernadero.Estado.ACTIVO]
    inactivos = [pk for pk, _, estado in todos if estado != Invernadero.Estado.ACTIVO]
    filas = [_fila(pk, nombre, [pk], sumas, con_iot, hay_cosecha) for pk, nombre in activos]
    de_baja = _fila(None, "Dados de baja", inactivos, sumas, con_iot, hay_cosecha) if inactivos and _hubo_actividad(inactivos, sumas) else None
    return PorInvernadero(filas, de_baja, _fila(None, "Total", ids, sumas, con_iot, hay_cosecha))


def merma_en_camara(periodo):
    """La merma en cámara, aparte (D-93 punto 4.7): plantas perdidas de partidas en cámara con fecha en el período, por causa, y su valor: lo que sumaron los
    asientos de esas mermas en «Pérdidas por Mermas» (Debe). `valor` es `None` («—») si a alguna merma que debería tener asiento (su costo, cantidad × costo
    por planta de la partida, redondeado a centavos es mayor que cero: H11) todavía le falta: la parte contable de la cámara llega con CON-04c. Una merma de
    costo cero aporta $ 0,00 y no fuerza el «—». 2 consultas."""
    mermas = Merma.objects.filter(causa__in=CAUSAS_DE_CAMARA, fecha_bitacora__range=(periodo.desde, periodo.hasta))
    con_costo = Exists(
        MovimientoStock.objects.filter(origen_id=OuterRef("pk"), tipo_movimiento=MovimientoStock.TipoMovimiento.MERMA_EN_CAMARA)
        .annotate(costo=ExpressionWrapper(F("cantidad") * F("costo_unitario"), output_field=DecimalField(max_digits=24, decimal_places=4)))
        .filter(costo__gte=Decimal("0.005"))
    )
    por_causa = (
        mermas.annotate(con_costo=con_costo)
        .values("causa")
        .annotate(plantas=Sum("cant_merma"), pendientes=Count("pk", filter=Q(con_costo=True, asiento_contable__isnull=True)))
        .order_by()
    )
    filas = sorted(((f["causa"], f["plantas"], f["pendientes"]) for f in por_causa), key=lambda f: (-f[1], f[0]))
    importe = MovimientoContable.objects.filter(
        cuenta__codigo_cuenta=cuentas.PERDIDAS_POR_MERMAS, tipo_movimiento=DEBE, asiento__origen_id__in=Subquery(mermas.values("pk"))
    ).aggregate(total=Sum("importe_movimiento"))["total"]
    sin_asiento = any(pendientes for _, _, pendientes in filas)
    return MermaEnCamara(
        [FilaDeCausaDeCamara(causa, Merma.Causa(causa).label, plantas) for causa, plantas, _ in filas],
        sum(plantas for _, plantas, _ in filas),
        None if sin_asiento else (importe or CERO),
        sin_asiento,
    )


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 8 · Comerciales (EST-03)
# ---------------------------------------------------------------------------------------------------------------------------------


def comerciales(actor, periodo, hoy):
    """Indicador 8 (EST-CNS-CNS regla 3.2; D-93 puntos 2 y 4.8): los de COM-CNS-EST para el período, de todos los invernaderos y todos los Vendedores.
    NO recalcula nada (H25): arma los filtros con `filtros_de_estadisticas` (rango del período, sin invernadero ni Vendedor) y devuelve lo que da
    `estadisticas` de `comercial`. Solo el Gerente activo (regla 1 de EST-CNS-CNS; el Vendedor ve lo suyo en Comercial). Lectura pura, sin auditoría."""
    _exigir_gerente(actor)
    filtros = estadisticas_comerciales.filtros_de_estadisticas(actor, {"periodo": "rango", "desde": periodo.desde.isoformat(), "hasta": periodo.hasta.isoformat()}, hoy)
    return estadisticas_comerciales.estadisticas(actor, filtros, hoy)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 9 · Compras
# ---------------------------------------------------------------------------------------------------------------------------------


def _meses_del_periodo(periodo):
    """Los `(año, mes)` que toca el período, de `desde` a `hasta`."""
    anio, mes = periodo.desde.year, periodo.desde.month
    meses = []
    while (anio, mes) <= (periodo.hasta.year, periodo.hasta.month):
        meses.append((anio, mes))
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return meses


def compras(periodo):
    """Indicador 9 (D-93 punto 4.9; EST-CNS-CNS «Decididas» 2): el valor recibido en el período, por proveedor, por categoría de insumo y por mes: Σ de lo
    que sumaron las recepciones con `fecha_recepcion` en el período menos las correcciones con `fecha_correccion` en él.

    El asiento de una recepción es uno solo por el total, así que no sirve para repartir por proveedor ni por categoría: se reconstruye la historia de cada
    línea de la orden (recepciones y correcciones en el orden en que se hicieron, que es el de su id) y cada hecho vale lo que da `valor_recibido` con lo
    acumulado después menos lo acumulado antes (D-89 punto 4, D-90 punto 8): el mismo importe de su asiento. 2 consultas."""
    rango = (periodo.desde, periodo.hasta)
    tocadas = DetalleOrdenCompra.objects.filter(
        Q(detalles_de_recepcion__recepcion__fecha_recepcion__range=rango) | Q(detalles_de_recepcion__correcciones__correccion__fecha_correccion__range=rango)
    ).values("pk")
    recibidas = list(
        DetalleRecepcion.objects.filter(detalle_orden_id__in=tocadas).select_related(
            "recepcion",
            "detalle_orden__detalle_cotizacion__cotizacion__proveedor",
            "detalle_orden__detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo__tipo_insumo",
        )
    )
    corregidas = {}  # (corrección, detalle de recepción) -> (fecha, cantidad)
    for f in (
        DetalleCorreccionRecepcion.objects.filter(detalle_recepcion__detalle_orden_id__in=tocadas)
        .values("correccion_id", "correccion__fecha_correccion", "detalle_recepcion_id")
        .annotate(cantidad=Sum("cantidad_corregida"))
        .order_by()
    ):
        corregidas[(f["correccion_id"], f["detalle_recepcion_id"])] = (f["correccion__fecha_correccion"], f["cantidad"])
    por_recibida = {}  # detalle de recepción -> lo corregido después
    for (_, detalle_recepcion_id), (_, cantidad) in corregidas.items():
        por_recibida[detalle_recepcion_id] = por_recibida.get(detalle_recepcion_id, Decimal("0")) + cantidad
    eventos = {}  # línea de la orden -> [(id del documento, fecha, variación de lo recibido, DetalleRecepcion)]
    for dr in recibidas:
        original = dr.cantidad_recibida_detalle + por_recibida.get(dr.pk, Decimal("0"))
        eventos.setdefault(dr.detalle_orden_id, []).append((dr.recepcion_id, dr.recepcion.fecha_recepcion, original, dr))
    por_detalle_de_recepcion = {dr.pk: dr for dr in recibidas}
    for (correccion_id, detalle_recepcion_id), (fecha, cantidad) in corregidas.items():
        dr = por_detalle_de_recepcion[detalle_recepcion_id]
        eventos[dr.detalle_orden_id].append((correccion_id, fecha, -cantidad, dr))
    total = Decimal("0")
    por_proveedor, por_categoria, por_mes = {}, {}, {}
    for lista in eventos.values():
        acumulado = Decimal("0")
        for _, fecha, variacion, dr in sorted(lista, key=lambda e: e[0]):
            linea = dr.detalle_orden
            valor = valor_recibido(linea, acumulado + variacion) - valor_recibido(linea, acumulado)
            acumulado += variacion
            if not (periodo.desde <= fecha <= periodo.hasta) or valor == 0:
                continue
            proveedor = linea.detalle_cotizacion.cotizacion.proveedor
            categoria = linea.detalle_cotizacion.detalle_pedido.insumo_invernadero.insumo.tipo_insumo
            total += valor
            clave = (proveedor.pk, proveedor.nombre_para_mostrar)
            por_proveedor[clave] = por_proveedor.get(clave, Decimal("0")) + valor
            clave = (categoria.pk, categoria.nombre_tipo_insumo)
            por_categoria[clave] = por_categoria.get(clave, Decimal("0")) + valor
            por_mes[(fecha.year, fecha.month)] = por_mes.get((fecha.year, fecha.month), Decimal("0")) + valor

    def ordenadas(diccionario):
        filas = [FilaDeCompra(clave, nombre, monto.quantize(DOS_DECIMALES)) for (clave, nombre), monto in diccionario.items() if monto != 0]
        return sorted(filas, key=lambda f: (-f.monto, f.nombre))

    return Compras(
        total.quantize(DOS_DECIMALES),
        ordenadas(por_proveedor),
        ordenadas(por_categoria),
        [FilaDeMes(anio, mes, por_mes.get((anio, mes), Decimal("0")).quantize(DOS_DECIMALES)) for anio, mes in _meses_del_periodo(periodo)],
    )


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 10 · Libro de gestión
# ---------------------------------------------------------------------------------------------------------------------------------


def libro(periodo):
    """Indicador 10 (D-93 punto 4.10): ventas (4.1.01), ingresos, egresos (los costos, una fila por cuenta de resultado negativo con su signo, D-102 punto 4)
    y resultado, por FECHA DEL ASIENTO aunque el período cruce dos ejercicios (EST-CNS-CNS «Decididas» 1). Usa `resultado_del_periodo` y
    `total_por_cuenta_en_periodo` del libro (D-86): 2 consultas más 2 por cada cuenta de resultado del plan (que es fijo)."""
    de_resultado = list(
        CuentaContable.objects.filter(tipo_cuenta__in=(CuentaContable.Tipo.RESULTADO_POSITIVO, CuentaContable.Tipo.RESULTADO_NEGATIVO))
        .order_by("codigo_cuenta")
        .values_list("codigo_cuenta", "nombre_cuenta", "tipo_cuenta")
    )
    resultado = servicio_del_libro.resultado_del_periodo(periodo.desde, periodo.hasta)
    ingresos, costos, ventas = [], [], CERO
    for codigo, nombre, tipo in de_resultado:
        monto = servicio_del_libro.total_por_cuenta_en_periodo(codigo, periodo.desde, periodo.hasta)
        if codigo == cuentas.VENTAS:
            ventas = monto
        if monto != 0:
            (ingresos if tipo == CuentaContable.Tipo.RESULTADO_POSITIVO else costos).append(FilaDeCuenta(codigo, nombre, monto))
    por_monto = lambda f: (-f.monto, f.codigo)  # noqa: E731 - de mayor a menor, y por código si empatan
    return LibroDeGestion(ventas, resultado.ingresos, resultado.egresos, resultado.resultado, sorted(ingresos, key=por_monto), sorted(costos, key=por_monto))


# ---------------------------------------------------------------------------------------------------------------------------------
# El armado de una pestaña
# ---------------------------------------------------------------------------------------------------------------------------------


def _bloques(actor, pestana, periodo, hoy, solo_produccion):
    """Solo los indicadores que muestra la pestaña (los demás quedan en `None` y no se calculan): el Resumen toma un dato de cada uno."""
    resumen = pestana == "resumen"
    return Bloques(
        por_invernadero(periodo, hoy, solo_produccion) if pestana == "produccion" or resumen else None,
        merma_en_camara(periodo) if pestana == "produccion" else None,
        comerciales(actor, periodo, hoy) if pestana == "comercial" else None,
        compras(periodo) if pestana == "compras" or resumen else None,
        libro(periodo) if pestana == "resultados" or resumen else None,
    )


def _comparaciones(pestana, actual, previo):
    """Una `Comparacion` por cifra que la pestaña compara con el período anterior (D-93 punto 2). Los costos y la merma mejoran si bajan: lo decide la vista."""
    c = periodos.comparar
    if pestana == "resumen":
        return {
            "ventas": c(actual.libro.ventas, previo.libro.ventas),
            "compras": c(actual.compras.total, previo.compras.total),
            "resultado": c(actual.libro.resultado, previo.libro.resultado),
            "cosechadas": c(actual.por_invernadero.total.cosechadas, previo.por_invernadero.total.cosechadas),
        }
    if pestana == "produccion":
        a, p = actual.por_invernadero.total, previo.por_invernadero.total
        comparaciones = {
            "sembradas": c(a.sembradas, p.sembradas),
            "cosechadas": c(a.cosechadas, p.cosechadas),
            "merma": c(a.merma, p.merma),
            "ordenes_a_tiempo": c(a.ordenes_a_tiempo, p.ordenes_a_tiempo),
            "costo_por_planta": c(a.costo_por_planta, p.costo_por_planta),
            "consumo": c(a.consumo, p.consumo),
        }
        if a.alertas_iot is not None and p.alertas_iot is not None:
            comparaciones["alertas_iot"] = c(a.alertas_iot, p.alertas_iot)
        return comparaciones
    if pestana == "comercial":
        # Decisión del estudiante (26/11/2026): se comparan los totales; la cobranza es una foto a hoy (igual en los dos períodos) y las filas por
        # variedad y por cliente no se comparan.
        a, p = actual.comerciales, previo.comerciales
        return {
            "ventas_monto": c(a.ventas.total, p.ventas.total),
            "ventas_entregas": c(a.ventas.entregas, p.ventas.entregas),
            "ventas_plantas": c(a.ventas.plantas, p.ventas.plantas),
            "a_tiempo": c(a.puntualidad.porcentaje_a_tiempo, p.puntualidad.porcentaje_a_tiempo),
            "promedio_de_retraso": c(a.puntualidad.promedio_de_retraso, p.puntualidad.promedio_de_retraso),
            "intentos_fallidos": c(a.puntualidad.intentos_fallidos, p.puntualidad.intentos_fallidos),
            "incumplimientos": c(a.incumplimientos.cantidad, p.incumplimientos.cantidad),
            "indemnizado": c(a.incumplimientos.total, p.incumplimientos.total),
            "con_faltante": c(a.faltantes.con_faltante, p.faltantes.con_faltante),
            "rechazados_por_cantidad": c(a.faltantes.rechazados_por_cantidad, p.faltantes.rechazados_por_cantidad),
            "rechazados_al_recibir": c(a.faltantes.rechazados_al_recibir, p.faltantes.rechazados_al_recibir),
            "cancelados": c(a.faltantes.cancelados, p.faltantes.cancelados),
        }
    if pestana == "compras":
        return {"compras": c(actual.compras.total, previo.compras.total)}
    return {
        "ingresos": c(actual.libro.ingresos, previo.libro.ingresos),
        "egresos": c(actual.libro.egresos, previo.libro.egresos),
        "resultado": c(actual.libro.resultado, previo.libro.resultado),
    }


def estadisticas_consolidadas(actor, pestana, periodo, comparar, hoy, solo_produccion=False):
    """Arma la pestaña `pestana` (`PESTANAS`) del período y, con `comparar`, la del período anterior de igual duración. Solo el Gerente activo
    (EST-CNS-CNS regla 1; `PermissionDenied`: el Contador tiene el libro y el Vendedor, sus estadísticas comerciales). Es una consulta: no audita (regla 7)."""
    _exigir_gerente(actor)
    if pestana not in PESTANAS:
        raise ValueError(f"Pestaña desconocida: {pestana!r} (usá {', '.join(PESTANAS)}).")
    del_anterior = periodos.anterior(periodo)
    actual = _bloques(actor, pestana, periodo, hoy, solo_produccion)
    previo = _bloques(actor, pestana, del_anterior, hoy, solo_produccion) if comparar else None
    return Consolidadas(pestana, periodo, del_anterior, actual, previo, _comparaciones(pestana, actual, previo) if previo else {})
