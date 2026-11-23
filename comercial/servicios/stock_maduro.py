# Stock maduro, reservas y cosechas automáticas (COM-02): PROD-ASG-STK, Asignar Stock Maduro (docs/casos_de_uso/produccion/stock_maduro.md y
# docs/patrones/stock_maduro.md; D-59). Aunque su código empieza con PROD, vive en `comercial` (regla A3 de D-37): crea reservas, que son de
# `comercial`. Lo reutilizan sin cambiarlo COM-03, COM-04 y COM-05.
#
# Funciones: `disponible` (solo lectura, para las pantallas), `asignar` (el caso de uso, dentro de la transacción del caso de uso base),
# `cantidad_sin_cubrir` (regla 10 de 8.8), `reservado_de_lotes` y `detalle_de_cosechas` (los registrantes de `produccion.extensiones`) y
# `repartir`, la función pura que decide qué se toma de cada partida y de cada lote (la sección 7 del patrón la reutiliza).
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

from comercial.models import DetalleReserva, DetalleVenta, ReservaStock
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
    visible de la compra-venta de la reserva (o ``None``); los lotes, ``(lote_id, cantidad_reservada, cantidad_cosechada)`` en orden de id de
    lote. Dos consultas, sin consultas por cosecha."""
    ids = list(cosecha_ids)
    if not ids:
        return {}
    detalle = {i: DetalleDeCosecha(None, None, []) for i in ids}
    reservas = ReservaStock.objects.filter(cosecha_id__in=ids).values(
        "pk", "cosecha_id", "fecha_entrega_reserva", "detalle_venta__compra_venta__numero"
    )
    por_reserva = {}
    for fila in reservas:
        numero = fila["detalle_venta__compra_venta__numero"]
        detalle[fila["cosecha_id"]] = DetalleDeCosecha(
            f"CV-{numero:04d}" if numero is not None else None, fila["fecha_entrega_reserva"], []
        )
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


def cantidad_sin_cubrir(detalle):
    """Regla 10 de 8.8: la cantidad pedida menos la cubierta por las líneas de sus reservas no liberadas. La cantidad cubierta de una línea
    (regla 9 de 8.8): de lote sin cosechar, la reservada; de lote cosechado, ``min(cosechada, reservada)``; de partida, la reservada. Un
    detalle confirmado, rechazado o cancelado no tiene. Nunca menor que 0."""
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
    cubierto = sum(min(cosechada, reservada) if lote_id and cosechada is not None else reservada for reservada, cosechada, lote_id in lineas)
    return max(0, detalle.cant_solicitada_venta - cubierto)


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


def _fechas_programadas(variedad_ids, fecha_entrega, parametro):
    """``{variedad_id: fecha programada por defecto}`` de una cosecha automática: ``max(hoy, entrega − anticipación efectiva)`` con la
    anticipación efectiva ``min(parámetro, postcosecha de la variedad)`` (regla 3 de 8.11). El parámetro se lee una vez."""
    hoy = stock.hoy()
    dias = getattr(configuracion.obtener(), PARAMETROS[parametro])
    postcosecha = dict(Variedad.objects.filter(pk__in=variedad_ids).values_list("pk", "duracion_post_cosecha"))
    return {v: max(hoy, fecha_entrega - timedelta(days=min(dias, postcosecha.get(v, dias)))) for v in variedad_ids}


def _leer(variedad_ids, invernadero_ids, fecha_entrega, parametro, lotes_excluidos=()):
    """Los candidatos a ser tomados, **en el orden de asignación** de cada variedad, con su stock libre. Solo lee (no bloquea). Una consulta
    por tabla: nunca una por lote ni por variedad. ``sin_capataz`` son los invernaderos considerados sin Capataz activo que tenían lotes
    que podían asignarse (extensión 5a)."""
    variedad_ids = list(dict.fromkeys(variedad_ids))
    invernadero_ids = list(dict.fromkeys(invernadero_ids))
    candidatos = {v: [] for v in variedad_ids}
    libres, sin_capataz = {}, set()
    if not variedad_ids or not invernadero_ids:
        return Lectura(candidatos, libres, sin_capataz, {})
    programadas = _fechas_programadas(variedad_ids, fecha_entrega, parametro)
    con_capataz = set(
        Invernadero.objects.filter(pk__in=invernadero_ids, capataz__is_active=True).values_list("pk", flat=True)
    )

    # Partidas elegibles: «disponible», con fecha límite igual o posterior a la entrega y stock libre mayor que cero. Primero, por vencimiento.
    partidas = list(
        StockCosechado.objects.filter(
            estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE,
            lote__invernadero_id__in=invernadero_ids,
            lote__siembra__variedad_id__in=variedad_ids,
            fecha_limite__gte=fecha_entrega,
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
    for p in partidas:
        libre = p.cantidad_disponible_cosechado - reservado_partidas.get(p.pk, 0)
        if libre > 0:
            clave = ("partida", p.pk)
            libres[clave] = libre
            candidatos[p.lote.siembra.variedad_id].append(Candidato(clave, "partida", p, p.lote.invernadero_id, libre))

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
    if lotes:
        reservado = reservado_de_lotes([lote.pk for lote in lotes])
        entradas = api_lotes.entradas_a_la_etapa(lotes, ciclos.etapas_de({lote.siembra.variedad_id for lote in lotes}))
        elegibles = defaultdict(list)
        for lote in lotes:
            libre, entrada = lote.cantidad_actual - reservado.get(lote.pk, 0), entradas.get(lote.pk)
            variedad_id = lote.siembra.variedad_id
            if libre <= 0 or entrada is None:
                continue
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
    return Lectura(candidatos, libres, sin_capataz, programadas)


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


# ---- PROD-ASG-STK ----


def invernaderos_considerados(compra_venta):
    """Pasos 3, 3a y 3b: con retiro, solo el invernadero de retiro; con envío (y en un suministro), los invernaderos del Vendedor del
    contrato (R115, R097, R151). Siempre **activos** (regla 4 de PROD-BAJ-INV: un invernadero inactivo no aparece en las asignaciones).
    Con el Capataz y el Agrónomo cargados, en orden de id."""
    consulta = Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO).select_related("agronomo", "capataz")
    if compra_venta.modalidad_entrega == compra_venta.Modalidad.RETIRO:
        consulta = consulta.filter(pk=compra_venta.invernadero_retiro_id)
    else:
        consulta = consulta.filter(vendedor_id=compra_venta.vendedor_id)
    return list(consulta.order_by("pk"))


def _verificar(detalle, cantidad, fecha_entrega, parametro):
    """Precondiciones a, b y c (las garantiza el caso de uso base; si no se cumplen es un error de programación): ``RuntimeError`` sin
    transacción y ``ValueError`` con un detalle que no se puede cubrir, una cantidad que no es un entero mayor que cero o una fecha o un
    parámetro inválidos. Devuelve el detalle releído con su compra-venta y su variedad."""
    if transaction.get_autocommit():
        raise RuntimeError("`asignar` corre dentro de la transacción del caso de uso base (precondición a de PROD-ASG-STK).")
    if not isinstance(detalle, DetalleVenta):
        raise ValueError("Hasta COM-03, `asignar` solo cubre un detalle de venta.")
    if parametro not in PARAMETROS:
        raise ValueError(f"`parametro` tiene que ser uno de {sorted(PARAMETROS)}.")
    if not isinstance(fecha_entrega, date) or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
        raise ValueError("Hace falta una fecha de entrega y una cantidad entera mayor que cero (precondición c).")
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
    a_reservar = min(cantidad, cantidad_sin_cubrir(detalle))
    if a_reservar <= 0:
        return Asignacion(0, 0, [], [])
    considerados = invernaderos_considerados(detalle.compra_venta)
    ids = [i.pk for i in considerados]
    variedad_id = detalle.variedad_id
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
            detalle_venta=detalle,
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
        _notificar(cosecha, invernadero, detalle, lotes_tomados)
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


def _notificar(cosecha, invernadero, detalle, lotes_tomados):
    """Una notificación por cosecha al Capataz y otra al Agrónomo del invernadero (si tiene uno activo); este último con el contrato, la
    fecha de entrega y que puede modificarla o cancelarla. Sin reintento: no hay cola de envíos (D-42; «Notificaciones» de temas_abiertos)."""
    titulo = f"Nueva cosecha {cosecha.codigo}"
    variedad = detalle.variedad
    sufijo = (
        f" Para {detalle.compra_venta.codigo}, entrega el {detalle.compra_venta.fecha_pactada_venta:%d/%m/%Y}."
        " Podés modificarla o cancelarla desde Órdenes de trabajo."
    )
    capataz = invernadero.capataz
    if capataz is not None and capataz.is_active:
        notificaciones.notificar(capataz, titulo, _texto_de_cosecha(cosecha, invernadero, variedad, lotes_tomados))
    agronomo = invernadero.agronomo
    if agronomo is not None and agronomo.is_active:
        notificaciones.notificar(agronomo, titulo, _texto_de_cosecha(cosecha, invernadero, variedad, lotes_tomados, sufijo))
