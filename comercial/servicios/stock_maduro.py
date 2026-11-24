# Stock maduro, reservas y cosechas automáticas (COM-02): PROD-ASG-STK, Asignar Stock Maduro (docs/casos_de_uso/produccion/stock_maduro.md y
# docs/patrones/stock_maduro.md; D-59). Aunque su código empieza con PROD, vive en `comercial` (regla A3 de D-37): crea reservas, que son de
# `comercial`. Lo reutilizan sin cambiarlo COM-03, COM-04 y COM-05.
#
# Funciones: `disponible` (solo lectura, para las pantallas), `asignar` (el caso de uso, dentro de la transacción del caso de uso base),
# `cantidad_sin_cubrir` (regla 10 de 8.8), `reservado_de_lotes` y `detalle_de_cosechas` (los registrantes de `produccion.extensiones`) y
# `repartir`, la función pura que decide qué se toma de cada partida y de cada lote (la sección 7 del patrón la reutiliza).
#
# COM-03a (sección 7 del patrón) suma los **períodos** de un detalle de suministro: `Periodo`, `asignar` y `cantidad_sin_cubrir` con un
# `Periodo`, `sin_cubrir_de_periodos` (una consulta para muchos) y la verificación acumulada de COM-PCT-SUM 9e: `simular` y
# `simular_varias` (solo lectura, sin bloquear), que usan el mismo `repartir` que `asignar`. Para no hacer una consulta por período, la
# lectura de candidatos (`_leer_varias`) trae una vez las partidas, los lotes y lo reservado, y arma los candidatos de cada fecha en memoria.
#
# Bloqueos (docs/patrones/stock_maduro.md, sección 3; siempre ``FOR NO KEY UPDATE``): el caso de uso base ya tomó las cuentas, los
# invernaderos considerados, el cliente y las variedades; `asignar` toma (o confirma, es reentrante) los lotes y las partidas candidatos, en
# orden de id, ANTES de leer sus reservas. Así dos asignaciones sobre la misma variedad se ponen en fila y la segunda ve lo que confirmó la
# primera: la extensión 8a («recalcular una vez») no hace falta con este diseño.
# `asignar` no audita (D-36): devuelve lo creado y el caso de uso base lo pone en su único registro.

from collections import defaultdict, namedtuple
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum

from comercial.models import DetalleReserva, DetalleSuministro, DetalleVenta, ReservaStock, Suministro
from comercial.servicios import calendario
from core import notificaciones
from inventario.servicios import ciclos, stock
from maestros.models import Invernadero, Variedad
from maestros.servicios import alertas, configuracion
from produccion.extensiones import DetalleDeCosecha
from produccion.models import Cosecha, Lote, OrdenTrabajo, StockCosechado
from produccion.servicios import lotes as api_lotes
from produccion.servicios import ordenes

# Cuánto es «hoy» lo da `inventario.servicios.stock.hoy()`; nunca `date.today()`.
Disponible = namedtuple("Disponible", "total lotes partidas")  # plantas libres de lotes elegibles y de partidas elegibles
Asignacion = namedtuple("Asignacion", "cubierta sin_cubrir reservas cosechas")
# Un candidato a ser tomado: `clave` es ("partida", id) o ("lote", id); `origen` es el `StockCosechado` o el `Lote`.
Candidato = namedtuple("Candidato", "clave tipo origen invernadero_id libre")
Lectura = namedtuple("Lectura", "candidatos libres sin_capataz programadas")
# Un período es un par (detalle de suministro, fecha del calendario del detalle): no es una clase (docs/modelo/comercial.md).
Periodo = namedtuple("Periodo", "detalle fecha")


class Cobertura(namedtuple("Cobertura", "fecha cantidad disponible")):
    """Lo que `simular` dice de un pedido: lo que se pidió y el stock maduro libre que le queda **después de los pedidos anteriores**.
    Lo que se cubre es la menor de las dos (``cubierta``)."""

    __slots__ = ()

    @property
    def cubierta(self):
        """La parte del pedido que se cubre: ``min(cantidad, disponible)``."""
        return min(self.cantidad, self.disponible)


# Qué parámetro de configuración da la anticipación de la cosecha según quién reserva (regla 3 de 8.11).
PARAMETROS = {
    "compra_venta": "dias_anticipacion_cosecha_compra_venta",
    "suministro": "dias_anticipacion_cosecha_suministro",
}
# Estados de reserva que ocupan stock: un lote, solo las «activas» (todavía no se cosechó); una partida, también las «listas para entrega».
RESERVAS_QUE_OCUPAN_LOTE = ("activa",)
RESERVAS_QUE_OCUPAN_PARTIDA = ("activa", "lista_para_entrega")
LARGO_DE_LA_NOTIFICACION = 500  # `core.Notificacion.detalle`


def _plantas(cantidad):
    """«1 planta» o «12 plantas»."""
    return f"{cantidad} {'planta' if cantidad == 1 else 'plantas'}"


# ---- lo que `comercial` registra en `produccion.extensiones` ----


def reservado_de_lotes(lote_ids):
    """``{lote_id: plantas}`` reservadas en líneas de reservas «activas» (regla 9 de 8.6): el registrante de
    `produccion.extensiones.registrar_reservado_de_lote`. Un lote sin reservas falta. Una consulta; con una lista vacía, ``{}`` sin consultar.
    No bloquea: lo llama quien ya bloqueó el lote."""
    ids = list(lote_ids)
    if not ids:
        return {}
    filas = (
        DetalleReserva.objects.filter(lote_id__in=ids, reserva__estado_reserva__in=RESERVAS_QUE_OCUPAN_LOTE)
        .values("lote_id")
        .annotate(total=Sum("cantidad_reservada"))
    )
    return {fila["lote_id"]: fila["total"] for fila in filas}


def detalle_de_cosechas(cosecha_ids):
    """``{cosecha_id: DetalleDeCosecha}``: el registrante de `produccion.extensiones.registrar_detalle_de_cosecha`. El contrato es el código
    visible de la compra-venta o del suministro de la reserva (o ``None``); los lotes, ``(lote_id, cantidad_reservada,
    cantidad_cosechada)`` en orden de id de lote. Dos consultas, sin consultas por cosecha."""
    ids = list(cosecha_ids)
    if not ids:
        return {}
    detalle = {i: DetalleDeCosecha(None, None, []) for i in ids}
    reservas = ReservaStock.objects.filter(cosecha_id__in=ids).values(
        "pk",
        "cosecha_id",
        "fecha_entrega_reserva",
        "detalle_venta__compra_venta__numero",
        "detalle_suministro__suministro__numero",
    )
    por_reserva = {}
    for fila in reservas:
        numero_cv = fila["detalle_venta__compra_venta__numero"]
        numero_sum = fila["detalle_suministro__suministro__numero"]
        codigo = f"CV-{numero_cv:04d}" if numero_cv is not None else (f"SUM-{numero_sum:04d}" if numero_sum is not None else None)
        detalle[fila["cosecha_id"]] = DetalleDeCosecha(codigo, fila["fecha_entrega_reserva"], [])
        por_reserva[fila["pk"]] = fila["cosecha_id"]
    lineas = (
        DetalleReserva.objects.filter(reserva_id__in=list(por_reserva), lote__isnull=False)
        .order_by("lote_id", "pk")
        .values_list("reserva_id", "lote_id", "cantidad_reservada", "cantidad_cosechada")
    )
    for reserva_id, lote_id, reservada, cosechada in lineas:
        detalle[por_reserva[reserva_id]].lotes.append((lote_id, reservada, cosechada))
    return detalle


# ---- cantidad sin cubrir (regla 10 de 8.8) ----


def _cubierto(cantidad_reservada, cantidad_cosechada, lote_id):
    """Regla 9 de 8.8: de lote cosechado, ``min(cosechada, reservada)``; de lote sin cosechar, la reservada; de partida, la reservada."""
    return min(cantidad_cosechada, cantidad_reservada) if lote_id and cantidad_cosechada is not None else cantidad_reservada


def cantidad_sin_cubrir(detalle):
    """Regla 10 de 8.8: la cantidad pedida menos la cubierta por las líneas de sus reservas no liberadas. La cantidad cubierta de una línea
    (regla 9 de 8.8): de lote sin cosechar, la reservada; de lote cosechado, ``min(cosechada, reservada)``; de partida, la reservada. Un
    detalle confirmado, rechazado o cancelado no tiene. Nunca menor que 0. Con un ``Periodo``, lo de ese período (``sin_cubrir_de_periodos``)."""
    if isinstance(detalle, Periodo):
        return sin_cubrir_de_periodos([detalle])[detalle]
    if detalle.estado_detalle_venta in (
        DetalleVenta.Estado.CONFIRMADO,
        DetalleVenta.Estado.RECHAZADO,
        DetalleVenta.Estado.CANCELADO,
    ):
        return 0
    lineas = (
        DetalleReserva.objects.filter(reserva__detalle_venta_id=detalle.pk)
        .exclude(reserva__estado_reserva=ReservaStock.Estado.LIBERADA)
        .values_list("cantidad_reservada", "cantidad_cosechada", "lote_id")
    )
    cubierto = sum(_cubierto(reservada, cosechada, lote_id) for reservada, cosechada, lote_id in lineas)
    return max(0, detalle.cant_solicitada_venta - cubierto)


def sin_cubrir_de_periodos(periodos):
    """``{Periodo: cantidad sin cubrir}`` de muchos períodos con **una** consulta (regla 10 de 8.8, MD-126): ``cantidad_por_periodo`` menos
    lo cubierto por las líneas de las reservas **no liberadas** del detalle con esa ``fecha_entrega_reserva``. Tiene cantidad sin cubrir un
    período de un detalle «vigente»; los demás (finalizado, resuelto) no tienen (el finalizado con fecha hasta su fin lo suma COM-04, D-64
    punto 8). Nunca menor que 0. Una lista vacía da ``{}`` sin consultar."""
    periodos = list(periodos)
    if not periodos:
        return {}
    cubierto = defaultdict(int)
    filas = (
        DetalleReserva.objects.filter(reserva__detalle_suministro_id__in={p.detalle.pk for p in periodos})
        .exclude(reserva__estado_reserva=ReservaStock.Estado.LIBERADA)
        .values_list("reserva__detalle_suministro_id", "reserva__fecha_entrega_reserva", "cantidad_reservada", "cantidad_cosechada", "lote_id")
    )
    for detalle_id, fecha, reservada, cosechada, lote_id in filas:
        cubierto[(detalle_id, fecha)] += _cubierto(reservada, cosechada, lote_id)
    resultado = {}
    for p in periodos:
        if p.detalle.estado_detalle_suministro != DetalleSuministro.Estado.VIGENTE:
            resultado[p] = 0
        else:
            resultado[p] = max(0, p.detalle.cantidad_por_periodo - cubierto[(p.detalle.pk, p.fecha)])
    return resultado


# ---- el reparto (función pura) ----


def repartir(candidatos, libre, cantidad):
    """``(tomado, sin_cubrir)``: de los ``candidatos`` (claves, **ya en el orden de asignación**) toma de cada uno lo que tenga en ``libre``
    (``{clave: stock libre}``) hasta cubrir ``cantidad``. ``tomado`` es ``[(clave, cantidad)]``; ``sin_cubrir``, lo que no se pudo cubrir.
    No lee la base: la usan `asignar` y, desde COM-03, la simulación de la verificación acumulada (sección 7 del patrón)."""
    tomado, falta = [], cantidad
    for clave in candidatos:
        if falta <= 0:
            break
        disponible = libre.get(clave, 0)
        if disponible <= 0:
            continue
        pedido = min(disponible, falta)
        tomado.append((clave, pedido))
        falta -= pedido
    return tomado, falta


# ---- lectura de los candidatos ----


def bloquear_candidatos(variedad_ids, invernadero_ids):
    """Nivel 4 del orden de bloqueos (patrón, sección 3): los lotes activos y después las partidas disponibles de esas variedades en esos
    invernaderos, cada grupo en orden de id (``FOR NO KEY UPDATE``). Hay que llamarla dentro de ``transaction.atomic()``, con el invernadero
    y la variedad ya bloqueados. Es reentrante: bloquear lo ya bloqueado por la misma transacción no espera."""
    variedad_ids, invernadero_ids = list(variedad_ids), list(invernadero_ids)
    if not variedad_ids or not invernadero_ids:
        return
    list(
        Lote.objects.select_for_update(no_key=True, of=("self",))
        .filter(estado_lote=Lote.Estado.ACTIVO, invernadero_id__in=invernadero_ids, siembra__variedad_id__in=variedad_ids)
        .order_by("pk")
    )
    list(
        StockCosechado.objects.select_for_update(no_key=True, of=("self",))
        .filter(
            estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE,
            lote__invernadero_id__in=invernadero_ids,
            lote__siembra__variedad_id__in=variedad_ids,
        )
        .order_by("pk")
    )


def _anticipacion(variedad_ids, parametro):
    """``(hoy, días del parámetro, {variedad_id: postcosecha})``: lo que hace falta para la fecha programada por defecto de una cosecha
    automática. El parámetro y las postcosechas se leen **una vez**, aunque después se calculen muchas fechas."""
    hoy = stock.hoy()
    dias = getattr(configuracion.obtener(), PARAMETROS[parametro])
    postcosecha = dict(Variedad.objects.filter(pk__in=variedad_ids).values_list("pk", "duracion_post_cosecha"))
    return hoy, dias, postcosecha


def _programadas(anticipacion, variedad_ids, fecha_entrega):
    """``{variedad_id: fecha programada por defecto}`` de una cosecha automática: ``max(hoy, entrega − anticipación efectiva)`` con la
    anticipación efectiva ``min(parámetro, postcosecha de la variedad)`` (regla 3 de 8.11)."""
    hoy, dias, postcosecha = anticipacion
    return {v: max(hoy, fecha_entrega - timedelta(days=min(dias, postcosecha.get(v, dias)))) for v in variedad_ids}


def _leer_varias(variedad_ids, invernadero_ids, fechas, parametro, lotes_excluidos=()):
    """``{fecha: Lectura}``: los candidatos a ser tomados para cada fecha de entrega, **en el orden de asignación** de cada variedad, con su
    stock libre. Solo lee (no bloquea). **Una consulta por tabla**, nunca una por lote, por variedad ni por fecha: las partidas se traen
    con la fecha límite más temprana de las pedidas y cada fecha filtra en memoria (el stock libre no depende de la fecha). ``sin_capataz``
    son los invernaderos considerados sin Capataz activo que tenían lotes que podían asignarse a esa fecha (extensión 5a)."""
    variedad_ids = list(dict.fromkeys(variedad_ids))
    invernadero_ids = list(dict.fromkeys(invernadero_ids))
    fechas = sorted(set(fechas))
    if not variedad_ids or not invernadero_ids or not fechas:
        return {f: Lectura({v: [] for v in variedad_ids}, {}, set(), {}) for f in fechas}
    anticipacion = _anticipacion(variedad_ids, parametro)
    con_capataz = set(
        Invernadero.objects.filter(pk__in=invernadero_ids, capataz__is_active=True).values_list("pk", flat=True)
    )

    # Partidas elegibles: «disponible», con fecha límite igual o posterior a la entrega y stock libre mayor que cero. Primero, por vencimiento.
    partidas = list(
        StockCosechado.objects.filter(
            estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE,
            lote__invernadero_id__in=invernadero_ids,
            lote__siembra__variedad_id__in=variedad_ids,
            fecha_limite__gte=fechas[0],
            cantidad_disponible_cosechado__gt=0,
        )
        .select_related("lote__siembra")
        .order_by("fecha_limite", "pk")
    )
    reservado_partidas = {}
    if partidas:
        filas = (
            DetalleReserva.objects.filter(
                partida_id__in=[p.pk for p in partidas], reserva__estado_reserva__in=RESERVAS_QUE_OCUPAN_PARTIDA
            )
            .values("partida_id")
            .annotate(total=Sum("cantidad_reservada"))
        )
        reservado_partidas = {f["partida_id"]: f["total"] for f in filas}
    partidas_libres = [(p, p.cantidad_disponible_cosechado - reservado_partidas.get(p.pk, 0)) for p in partidas]
    partidas_libres = [(p, libre) for p, libre in partidas_libres if libre > 0]

    # Lotes elegibles: «activo», en Maduración, con stock libre y cuya fecha máxima de cosecha no es anterior a la fecha programada de su
    # cosecha. La entrada a Maduración y la fecha máxima salen de `produccion` (nunca a mano): para un lote que ya está en Maduración, la
    # entrada a su etapa actual es la entrada a Maduración (regla 5 de 8.21 = regla 2 de 8.20) y la duración, la de su etapa.
    lotes = list(
        Lote.objects.filter(
            estado_lote=Lote.Estado.ACTIVO,
            invernadero_id__in=invernadero_ids,
            siembra__variedad_id__in=variedad_ids,
            etapa__tipo_etapa__codigo=ciclos.MADURACION,
            cantidad_actual__gt=0,
        )
        .exclude(pk__in=list(lotes_excluidos))
        .select_related("siembra", "etapa")
        .order_by("pk")
    )
    lotes_libres = []  # (lote, libre, entrada a Maduración)
    if lotes:
        reservado = reservado_de_lotes([lote.pk for lote in lotes])
        entradas = api_lotes.entradas_a_la_etapa(lotes, ciclos.etapas_de({lote.siembra.variedad_id for lote in lotes}))
        for lote in lotes:
            libre, entrada = lote.cantidad_actual - reservado.get(lote.pk, 0), entradas.get(lote.pk)
            if libre > 0 and entrada is not None:
                lotes_libres.append((lote, libre, entrada))

    lecturas = {}
    for fecha in fechas:
        programadas = _programadas(anticipacion, variedad_ids, fecha)
        candidatos = {v: [] for v in variedad_ids}
        libres, sin_capataz = {}, set()
        for p, libre in partidas_libres:
            if p.fecha_limite >= fecha:
                clave = ("partida", p.pk)
                libres[clave] = libre
                candidatos[p.lote.siembra.variedad_id].append(Candidato(clave, "partida", p, p.lote.invernadero_id, libre))
        elegibles = defaultdict(list)
        for lote, libre, entrada in lotes_libres:
            variedad_id = lote.siembra.variedad_id
            if entrada + timedelta(days=lote.etapa.duracion_estimada_dias) < programadas[variedad_id]:
                continue  # regla 11 de 8.6 y regla 3 de 8.20: llegaría tarde a cosecharse
            if lote.invernadero_id not in con_capataz:
                sin_capataz.add(lote.invernadero_id)  # extensión 5a: sus lotes no se consideran
                continue
            clave = ("lote", lote.pk)
            libres[clave] = libre
            elegibles[variedad_id].append((entrada, libre, lote.pk, Candidato(clave, "lote", lote, lote.invernadero_id, libre)))
        for variedad_id, lista in elegibles.items():
            # Del que entró antes en Maduración al que entró después y, como desempate, el de menor stock libre (y `id`).
            candidatos[variedad_id].extend(c for *_, c in sorted(lista, key=lambda t: t[:3]))
        lecturas[fecha] = Lectura(candidatos, libres, sin_capataz, programadas)
    return lecturas


def _leer(variedad_ids, invernadero_ids, fecha_entrega, parametro, lotes_excluidos=()):
    """`_leer_varias` para una sola fecha de entrega (`asignar` y `disponible`)."""
    return _leer_varias(variedad_ids, invernadero_ids, [fecha_entrega], parametro, lotes_excluidos)[fecha_entrega]


def disponible(variedad_ids, invernadero_ids, fecha_entrega, parametro):
    """``{variedad_id: Disponible(total, lotes, partidas)}``: el stock maduro libre de cada variedad para ``fecha_entrega`` en esos
    invernaderos (regla «Stock maduro libre disponible»: pasos 8, 10 y 14 de COM-REG-CVT). **Solo lectura, sin bloquear.** Toda variedad
    pedida figura (con 0). ``parametro`` es ``"compra_venta"`` o ``"suministro"``. Una consulta por tabla, nunca una por lote."""
    if parametro not in PARAMETROS:
        raise ValueError(f"`parametro` tiene que ser uno de {sorted(PARAMETROS)}.")
    lectura = _leer(variedad_ids, invernadero_ids, fecha_entrega, parametro)
    resultado = {}
    for variedad_id, lista in lectura.candidatos.items():
        lotes = sum(c.libre for c in lista if c.tipo == "lote")
        partidas = sum(c.libre for c in lista if c.tipo == "partida")
        resultado[variedad_id] = Disponible(lotes + partidas, lotes, partidas)
    return resultado


# ---- la simulación (verificación acumulada por variedad, COM-PCT-SUM 9e) ----


def simular_varias(pedidos_por_variedad, invernadero_ids, parametro):
    """``{variedad_id: [Cobertura]}``: la verificación acumulada de COM-PCT-SUM (9e) y COM-MOD-SUM (5b.3) para muchas variedades de una vez.
    ``pedidos_por_variedad`` es ``{variedad_id: [(fecha, cantidad), …]}`` con los pedidos **en orden de fecha** (si no, ``ValueError``).
    Cada pedido se reparte con el mismo `repartir` que usa `asignar`, y lo que toma se descuenta en memoria del stock libre antes de seguir
    con el siguiente: cada período se verifica contra lo que dejan libre los anteriores **de la misma variedad**. **Solo lectura, sin
    bloquear**; una consulta por tabla, igual con 1 que con muchos pedidos y variedades. Sin pedidos, ``{}`` por variedad sin consultar."""
    if parametro not in PARAMETROS:
        raise ValueError(f"`parametro` tiene que ser uno de {sorted(PARAMETROS)}.")
    for variedad_id, pedidos in pedidos_por_variedad.items():
        fechas = [fecha for fecha, _ in pedidos]
        if fechas != sorted(fechas):
            raise ValueError("Los pedidos tienen que venir en orden de fecha.")
    resultado = {variedad_id: [] for variedad_id in pedidos_por_variedad}
    fechas = {fecha for pedidos in pedidos_por_variedad.values() for fecha, _ in pedidos}
    if not fechas:
        return resultado
    lecturas = _leer_varias(list(pedidos_por_variedad), invernadero_ids, fechas, parametro)
    restante = {}  # el stock libre que va quedando; las claves son de una sola variedad (un lote o una partida es de una variedad)
    for lectura in lecturas.values():
        restante.update(lectura.libres)
    for variedad_id, pedidos in pedidos_por_variedad.items():
        for fecha, cantidad in pedidos:
            claves = [c.clave for c in lecturas[fecha].candidatos[variedad_id]]
            libre = {clave: restante[clave] for clave in claves}
            tomado, _ = repartir(claves, libre, cantidad)
            for clave, cuanto in tomado:
                restante[clave] -= cuanto
            resultado[variedad_id].append(Cobertura(fecha, cantidad, sum(libre.values())))
    return resultado


def simular(variedad_id, invernadero_ids, pedidos, parametro):
    """``[Cobertura(fecha, cantidad, disponible)]`` de los ``pedidos`` de **una** variedad, en orden de fecha (`simular_varias`)."""
    return simular_varias({variedad_id: list(pedidos)}, invernadero_ids, parametro)[variedad_id]


# ---- PROD-ASG-STK ----


def invernaderos_considerados(contrato):
    """Pasos 3, 3a y 3b: con retiro, solo el invernadero de retiro; con envío (y en un suministro), los invernaderos del Vendedor del
    contrato (R115, R097, R151). Siempre **activos** (regla 4 de PROD-BAJ-INV: un invernadero inactivo no aparece en las asignaciones).
    Con el Capataz y el Agrónomo cargados, en orden de id. ``contrato`` es una compra-venta o un suministro (este no tiene retiro)."""
    consulta = Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO).select_related("agronomo", "capataz")
    if getattr(contrato, "modalidad_entrega", None) == "retiro":
        consulta = consulta.filter(pk=contrato.invernadero_retiro_id)
    else:
        consulta = consulta.filter(vendedor_id=contrato.vendedor_id)
    return list(consulta.order_by("pk"))


def _verificar(detalle, cantidad, fecha_entrega, parametro):
    """Precondiciones a, b y c (las garantiza el caso de uso base; si no se cumplen es un error de programación): ``RuntimeError`` sin
    transacción y ``ValueError`` con un detalle que no se puede cubrir, una cantidad que no es un entero mayor que cero o una fecha o un
    parámetro inválidos. ``detalle`` es un ``DetalleVenta`` «abierto» de una venta «abierta» o un ``Periodo`` de un detalle y un suministro
    «vigentes» cuya fecha es del calendario del detalle (con ``parametro="suministro"``). Devuelve el detalle (o el período) releído."""
    if transaction.get_autocommit():
        raise RuntimeError("`asignar` corre dentro de la transacción del caso de uso base (precondición a de PROD-ASG-STK).")
    if not isinstance(detalle, (DetalleVenta, Periodo)):
        raise ValueError("`asignar` cubre un detalle de venta o un período de un detalle de suministro.")
    if parametro not in PARAMETROS:
        raise ValueError(f"`parametro` tiene que ser uno de {sorted(PARAMETROS)}.")
    if not isinstance(fecha_entrega, date) or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
        raise ValueError("Hace falta una fecha de entrega y una cantidad entera mayor que cero (precondición c).")
    if isinstance(detalle, Periodo):
        if parametro != "suministro":
            raise ValueError("Con un período, `parametro` es siempre «suministro» (sección 7 del patrón).")
        releido = DetalleSuministro.objects.select_related("suministro", "variedad").get(pk=detalle.detalle.pk)
        if (
            releido.estado_detalle_suministro != DetalleSuministro.Estado.VIGENTE
            or releido.suministro.estado_suministro != Suministro.Estado.VIGENTE
        ):
            raise ValueError("El detalle y el suministro tienen que estar «vigentes» (precondición b).")
        if fecha_entrega != detalle.fecha or not calendario.calendario(releido, desde=fecha_entrega, hasta=fecha_entrega):
            raise ValueError("La fecha no es un período del calendario del detalle (precondición b).")
        return Periodo(releido, fecha_entrega)
    detalle = DetalleVenta.objects.select_related("compra_venta", "variedad").get(pk=detalle.pk)
    if (
        detalle.estado_detalle_venta != DetalleVenta.Estado.ABIERTO
        or detalle.compra_venta.estado_venta != detalle.compra_venta.Estado.ABIERTA
    ):
        raise ValueError("El detalle tiene que ser un detalle «abierto» de una venta «abierta» (precondición b).")
    return detalle


def asignar(origen, detalle, cantidad, fecha_entrega, parametro, *, lotes_excluidos=()):
    """PROD-ASG-STK: reserva stock maduro para ``detalle`` y programa las cosechas necesarias. Devuelve
    ``Asignacion(cubierta, sin_cubrir, reservas, cosechas)``.

    - ``origen`` es la cuenta que actúa (Vendedor o Gerente) o ``None`` si actúa InfoPonia (D-27). Corre dentro de la transacción del caso de
      uso base (sin ella, ``RuntimeError``), con las cuentas, los invernaderos, el cliente y las variedades ya bloqueados.
    - ``detalle`` es un ``DetalleVenta`` o un ``Periodo`` (desde COM-03): con un período, cada reserva lleva ``detalle_suministro`` y
      ``fecha_entrega_reserva`` = la fecha del período, y los invernaderos considerados son los del Vendedor **actual** del suministro.
    - Paso 2 y extensión 2a: reserva la menor entre ``cantidad`` y la cantidad sin cubrir del detalle; sin nada sin cubrir, no crea nada.
    - Pasos 3 a 5 y extensiones 3a, 3b, 5a, 5c y 5d: los invernaderos considerados, las partidas por vencimiento y los lotes por entrada a
      Maduración (reglas 7, 9 a 11 de 8.6; 2 y 3 de 8.20); los lotes de un invernadero sin Capataz activo no se consideran y, si podían
      asignarse, queda la alerta «sin Capataz» (`maestros`, D-41). ``lotes_excluidos``: lotes que no se consideran (PCU 7, lo usa COM-04).
    - Pasos 6 y 7 y extensiones 4a y 5b: una reserva por invernadero (regla 1 de 8.8), «lista para entrega» si todo es de cámara y «activa»
      si tiene un lote; esta con su cosecha «a realizar», con la prioridad media y el Capataz del invernadero (reglas 2 de 8.8 y 3 de 8.11).
    - Paso 10: dentro de la transacción (D-42) una notificación por cosecha al Capataz y otra al Agrónomo del invernadero, si hay uno activo.
    - No cambia la cantidad de ningún lote ni de ninguna partida (regla 14 de 8.8), ni el estado del detalle ni de la venta, y no audita.
    """
    detalle = _verificar(detalle, cantidad, fecha_entrega, parametro)
    es_periodo = isinstance(detalle, Periodo)
    detalle_de_contrato = detalle.detalle if es_periodo else detalle
    contrato = detalle_de_contrato.suministro if es_periodo else detalle_de_contrato.compra_venta
    a_reservar = min(cantidad, cantidad_sin_cubrir(detalle))
    if a_reservar <= 0:
        return Asignacion(0, 0, [], [])
    considerados = invernaderos_considerados(contrato)
    ids = [i.pk for i in considerados]
    variedad_id = detalle_de_contrato.variedad_id
    bloquear_candidatos([variedad_id], ids)  # antes de leer las reservas: así se ve lo que confirmaron las demás
    lectura = _leer([variedad_id], ids, fecha_entrega, parametro, lotes_excluidos)
    for invernadero_id in sorted(lectura.sin_capataz):
        alertas.asegurar_alerta_de_estado(invernadero_id, "sin_capataz")
    candidatos = lectura.candidatos[variedad_id]
    tomado, _ = repartir([c.clave for c in candidatos], lectura.libres, a_reservar)
    por_clave = {c.clave: c for c in candidatos}
    por_invernadero = defaultdict(list)
    for clave, cuanto in tomado:
        por_invernadero[por_clave[clave].invernadero_id].append((por_clave[clave], cuanto))

    hoy = stock.hoy()
    reservas, cosechas, pendientes_de_aviso = [], [], []
    por_id = {i.pk: i for i in considerados}
    for invernadero_id in sorted(por_invernadero):
        items, invernadero = por_invernadero[invernadero_id], por_id[invernadero_id]
        hay_lote = any(c.tipo == "lote" for c, _ in items)
        cosecha = None
        if hay_lote:
            cosecha = Cosecha.objects.create(
                tipo_orden=OrdenTrabajo.Tipo.COSECHA,
                numero=ordenes.siguiente_numero(),
                fecha_creacion_orden=hoy,
                fecha_programada_orden=lectura.programadas[variedad_id],
                prioridad_orden=OrdenTrabajo.Prioridad.MEDIA,
                agronomo=None,  # la planificó InfoPonia (R046)
                invernadero=invernadero,
                capataz_id=invernadero.capataz_id,
                variedad_id=variedad_id,
            )
            cosechas.append(cosecha)
        reserva = ReservaStock.objects.create(
            **({"detalle_suministro": detalle_de_contrato} if es_periodo else {"detalle_venta": detalle_de_contrato}),
            invernadero=invernadero,
            fecha_reserva=hoy,
            fecha_entrega_reserva=fecha_entrega,
            estado_reserva=ReservaStock.Estado.ACTIVA if hay_lote else ReservaStock.Estado.LISTA_PARA_ENTREGA,
            cosecha=cosecha,
        )
        DetalleReserva.objects.bulk_create(
            [
                DetalleReserva(reserva=reserva, cantidad_reservada=cuanto, **({"lote": c.origen} if c.tipo == "lote" else {"partida": c.origen}))
                for c, cuanto in items
            ]
        )
        reservas.append(reserva)
        if cosecha is not None:
            pendientes_de_aviso.append((cosecha, invernadero, [(c.origen, cuanto) for c, cuanto in items if c.tipo == "lote"]))

    for cosecha, invernadero, lotes_tomados in pendientes_de_aviso:
        _notificar(cosecha, invernadero, detalle_de_contrato.variedad, contrato, fecha_entrega, lotes_tomados)
    cubierta = sum(cuanto for _, cuanto in tomado)
    return Asignacion(cubierta, a_reservar - cubierta, reservas, cosechas)


# ---- notificaciones (paso 10; textos del extracto, «Cómo se aplica», punto 9) ----


def _texto_de_cosecha(cosecha, invernadero, variedad, lotes_tomados, sufijo=""):
    """«Nueva cosecha OT-…: {variedad}, {invernadero}. Lotes: L-… (N plantas), … Fecha programada: dd/mm/aaaa.» más ``sufijo``. Si pasa de
    los 500 caracteres de una notificación, se acorta la lista de lotes con «…» (el resto del texto no se recorta)."""
    lotes = [f"{lote.codigo} ({_plantas(cuanto)})" for lote, cuanto in lotes_tomados]

    def armar(cantidad):
        lista = ", ".join(lotes[:cantidad]) + (", …" if cantidad < len(lotes) else "")
        return (
            f"Nueva cosecha {cosecha.codigo}: {variedad}, {invernadero.nombre_invernadero}. Lotes: {lista}. "
            f"Fecha programada: {cosecha.fecha_programada_orden:%d/%m/%Y}.{sufijo}"
        )

    for cantidad in range(len(lotes), 0, -1):
        texto = armar(cantidad)
        if len(texto) <= LARGO_DE_LA_NOTIFICACION:
            return texto
    return armar(1)[:LARGO_DE_LA_NOTIFICACION]


def _notificar(cosecha, invernadero, variedad, contrato, fecha_entrega, lotes_tomados):
    """Una notificación por cosecha al Capataz y otra al Agrónomo del invernadero (si tiene uno activo); este último con el contrato (una
    compra-venta o un suministro), la fecha de entrega y que puede modificarla o cancelarla. Sin reintento: no hay cola de envíos (D-42;
    «Notificaciones» de temas_abiertos)."""
    titulo = f"Nueva cosecha {cosecha.codigo}"
    sufijo = (
        f" Para {contrato.codigo}, entrega el {fecha_entrega:%d/%m/%Y}."
        " Podés modificarla o cancelarla desde Órdenes de trabajo."
    )
    capataz = invernadero.capataz
    if capataz is not None and capataz.is_active:
        notificaciones.notificar(capataz, titulo, _texto_de_cosecha(cosecha, invernadero, variedad, lotes_tomados))
    agronomo = invernadero.agronomo
    if agronomo is not None and agronomo.is_active:
        notificaciones.notificar(agronomo, titulo, _texto_de_cosecha(cosecha, invernadero, variedad, lotes_tomados, sufijo))
