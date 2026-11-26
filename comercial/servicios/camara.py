# La cámara en `comercial` (COM-04b): PROD-ASG-CAM (asignar el stock libre de una partida a quien lo espera, con su paso diario 25) y PROD-VNC-CAM (vencer las partidas,
# paso diario 20, con el aviso previo «partida por vencer»), más el recorte de reservas que comparte con la merma en cámara (`merma_camara.py`) y la pestaña «Cámara» de la ficha del
# invernadero (docs/casos_de_uso/produccion/camara.md y merma.md, «Cómo se aplica en la ronda «Comercial 1»»; docs/patrones/stock_maduro.md, sección 8; D-64 y D-67 punto 2).
# Aunque sus códigos empiezan con PROD, viven en `comercial` (D-59, regla A3 de D-37): crean o recortan reservas. Lo físico (bajar una partida, la merma, el movimiento) lo escribe el
# núcleo de `produccion` (`produccion.servicios.camara`, docs/api/produccion.md, sección 8).
#
# Cada partida va en su propia transacción. Bloqueos (`FOR NO KEY UPDATE`; docs/patrones/bloqueos.md, «Cosecha y cámara»; siempre este orden): las cuentas (los Vendedores de los
# contratos y el Agrónomo del invernadero) → los invernaderos (el de la partida y los considerados de los contratos, por id) → la variedad → los lotes y las partidas candidatos →
# los contratos y sus detalles → las reservas y sus líneas. Con la partida bloqueada ANTES de leer sus reservas no hace falta la extensión 8a de PROD-ASG-CAM (patrón, sección 3):
# lo que se calcula después de bloquear ya es lo definitivo. El enlace del cliente (`EnlaceCliente`, D-65) iría al final: lo suma COM-04c.
#
# Decisión de aplicación (plan de COM-04b): cuando hay que volver a cubrir lo recortado (merma o vencimiento), primero se da de baja el stock físico de la partida y después se vuelve a
# cubrir con `asignar`: así lo recortado nunca vuelve a salir de la misma partida que se está perdiendo. El resultado de negocio es el mismo que el del caso de uso.
# Fuera de esta tarea: el enlace y el correo del camino de faltante (COM-04c), «sin entrega» de los candidatos, planificar la entrega (paso 9) y las entregas de PROD-VNC-CAM (COM-05 y
# COM-06) y los asientos (D-57).

import logging
from collections import defaultdict, namedtuple
from datetime import timedelta
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.urls import reverse

from comercial.models import AlertaComercial, CompraVenta, DetalleEntrega, DetalleReserva, DetalleSuministro, DetalleVenta, Entrega, ReservaStock, Suministro
from comercial.servicios import asientos_comerciales, calendario, enlaces, entregas, faltantes, stock_maduro
from comercial.servicios.comprobantes import Destinatario
from comercial.servicios.stock_maduro import Periodo, _cubierto
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from core.procesos import ResumenDePaso
from inventario.servicios import stock
from inventario.servicios.variedades import bloquear_variedad
from maestros.extensiones import Enlace
from maestros.models import Variedad
from maestros.servicios import alertas, configuracion
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.extensiones import entradas_de_comercial
from produccion.models import AlertaDeMerma, Merma, MovimientoStock, StockCosechado
from produccion.servicios import camara as fisico

logger = logging.getLogger("infoponia.camara")

TIPO_POR_VENCER = "comercial_partida_por_vencer"  # ESTADO, AGRONOMO_O_GERENTE, ADVERTENCIA, origen STOCK_COSECHADO (D-64 punto 10)
TIPO_EN_ENTREGA_EN_CURSO = "comercial_partida_en_entrega_en_curso"  # ESTADO, GERENTE, CRITICA, origen STOCK_COSECHADO (PROD-VNC-CAM 3b, COM-06a)
TIPO_MERMA_RESERVADA = "comercial_merma_camara_reservada"  # EVENTO, AGRONOMO_O_GERENTE, ADVERTENCIA, origen MERMA (regla 8 de 8.9)
OCUPAN = (ReservaStock.Estado.ACTIVA, ReservaStock.Estado.LISTA_PARA_ENTREGA)  # las reservas que ocupan una partida (regla 10 de 8.6)
LARGO_DE_LA_ALERTA = 200  # `Alerta.descripcion_alerta`
LARGO_DE_LA_NOTIFICACION = 500
DIAS_DE_CERRADAS = 30  # las partidas agotadas o vencidas que muestra la pestaña «Cámara»
GERENTE, AGRONOMO, CAPATAZ, VENDEDOR = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ, Usuario.Rol.VENDEDOR

# `tipo` es «cv» o «sum»; `objeto` el `DetalleVenta` o el `Periodo`; `contrato`, la compra-venta o el suministro; `clave` el desempate por id.
Candidato = namedtuple("Candidato", "tipo objeto contrato fecha_entrega fecha_realizacion clave sin_cubrir")
LineaARecortar = namedtuple("LineaARecortar", "tipo fecha_entrega reserva_id linea")
Afectado = namedtuple("Afectado", "objeto contrato recortado fecha_entrega")
Recorte = namedtuple("Recorte", "lineas reservas_liberadas por_detalle")
Recubierto = namedtuple("Recubierto", "reservas cosechas faltantes detalles enlaces", defaults=((),))  # faltantes: [(código del contrato, plantas sin cubrir)]; enlaces: los del cliente que creó el camino de faltante (COM-04c)
ResultadoDeAsignacion = namedtuple("ResultadoDeAsignacion", "partida reservas detalles_reabiertos ventas_reabiertas reservado")


class _ContratosNuevos(Exception):
    """Al bloquear aparecieron contratos con líneas en la partida que la lectura previa no vio: hay que volver a leer (una vez)."""


def _plantas(cantidad):
    """«1 planta» o «12 plantas»."""
    return f"{cantidad} {'planta' if cantidad == 1 else 'plantas'}"


def _acotar(texto, largo):
    """El texto sin pasar de `largo` caracteres (termina en «…» si se recorta)."""
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _clave_del_aviso(partida_id):
    """La clave de la alerta de estado «partida por vencer» (una por partida, D-64 punto 10)."""
    return f"partida:{partida_id}"


def _exigir_transaccion(nombre):
    """Las funciones de núcleo corren dentro de la transacción del caso de uso que las llama."""
    if transaction.get_autocommit():
        raise RuntimeError(f"`{nombre}` corre dentro de la transacción del caso de uso que la llama.")


# ---- funciones puras de orden ----


def orden_de_recorte(lineas):
    """El orden en que se recortan las líneas de una partida (regla 6 de 8.9; patrón de stock, sección 8): primero las de compra-venta y después las de suministro; dentro de
    cada grupo, la fecha de entrega más lejana primero y, si empatan, la reserva creada más tarde (mayor id). Función pura: `lineas` son objetos con `tipo`, `fecha_entrega` y `reserva_id`."""
    return sorted(lineas, key=lambda l: (0 if l.tipo == "cv" else 1, -l.fecha_entrega.toordinal(), -l.reserva_id))


def orden_de_candidatos(candidatos):
    """El orden de prioridad de PROD-ASG-CAM (regla 17 de 8.8; extensión 4a): la fecha de entrega más próxima; con la misma fecha, primero los períodos de suministro y después
    los detalles de venta; después el contrato realizado antes; por último la menor clave (id, o `(id del detalle, ordinal de la fecha)` en un período). Función pura."""
    return sorted(candidatos, key=lambda c: (c.fecha_entrega, 0 if c.tipo == "sum" else 1, c.fecha_realizacion, c.clave))


# ---- lecturas comunes ----


def _reservado_de(partida_id):
    """Lo reservado de la partida en reservas «activas» o «lista para entrega» (regla 10 de 8.6)."""
    return (
        DetalleReserva.objects.filter(partida_id=partida_id, reserva__estado_reserva__in=OCUPAN).aggregate(total=Coalesce(Sum("cantidad_reservada"), 0))["total"]
    )


def _con_libre(consulta):
    """`consulta` de `StockCosechado` con `reservado` y `libre` (disponible menos lo reservado en una sola consulta)."""
    reservado = Coalesce(Sum("lineas_de_reserva__cantidad_reservada", filter=Q(lineas_de_reserva__reserva__estado_reserva__in=OCUPAN)), 0)
    return consulta.annotate(reservado=reservado).annotate(libre=F("cantidad_disponible_cosechado") - F("reservado"))


def _usuario_activo(usuario_id):
    """La cuenta activa con ese id, o `None`."""
    return Usuario.objects.filter(pk=usuario_id, is_active=True).first() if usuario_id else None


def _bloquear_cuentas(ids):
    """Nivel 1: las cuentas, en una consulta y por id."""
    list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={i for i in ids if i}).order_by("pk"))


def _contratos_con_lineas(partida_id):
    """`(ids de detalles de venta, ids de detalles de suministro)` de las reservas que hoy ocupan la partida. Lectura sin bloquear."""
    filas = DetalleReserva.objects.filter(partida_id=partida_id, reserva__estado_reserva__in=OCUPAN, cantidad_reservada__gt=0).values_list(
        "reserva__detalle_venta_id", "reserva__detalle_suministro_id"
    )
    return {v for v, _ in filas if v}, {s for _, s in filas if s}


def _contratos_de(detalles_de_venta, detalles_de_suministro):
    """Las compra-ventas y los suministros de esos detalles, por id (para saber a quién bloquear y qué invernaderos considerar)."""
    ventas = list(CompraVenta.objects.filter(detalles__in=detalles_de_venta).distinct().order_by("pk"))
    suministros = list(Suministro.objects.filter(detalles__in=detalles_de_suministro).distinct().order_by("pk"))
    return ventas, suministros


def _bloquear_invernaderos(propio_id, contratos, *, activo):
    """Nivel 2: el invernadero de la partida y los considerados de los contratos, por id. El propio con `bloquear_invernadero_activo` si `activo` (la asignación) o, si no, con
    `bloquear_invernadero_para_alertas` (activo o no: el vencimiento y la merma no pueden fallar por una baja, D-64 punto 12); los demás, solo si siguen activos. Devuelve los activos."""
    ids = {propio_id}
    for contrato in contratos:
        ids |= {i.pk for i in stock_maduro.invernaderos_considerados(contrato)}
    activos = []
    for pk in sorted(ids):
        if pk == propio_id and not activo:
            if bloquear_invernadero_para_alertas(pk).activo:
                activos.append(pk)
            continue
        try:
            bloquear_invernadero_activo(pk)
            activos.append(pk)
        except ValidationError:
            if pk == propio_id:
                raise
    return activos


def _bloquear_filas(partida, ventas, suministros, detalles_de_venta, detalles_de_suministro):
    """Niveles 5 y 6: la partida, los contratos y sus detalles, y las reservas con sus líneas (en orden de id)."""
    StockCosechado.objects.select_for_update(no_key=True, of=("self",)).filter(pk=partida.pk).first()
    list(CompraVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=[c.pk for c in ventas]).order_by("pk"))
    list(DetalleVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=detalles_de_venta).order_by("pk"))
    list(Suministro.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=[c.pk for c in suministros]).order_by("pk"))
    list(DetalleSuministro.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=detalles_de_suministro).order_by("pk"))
    reservas = list(
        ReservaStock.objects.select_for_update(no_key=True, of=("self",))
        .filter(pk__in=DetalleReserva.objects.filter(partida=partida).values("reserva_id"), estado_reserva__in=OCUPAN)
        .order_by("pk")
    )
    list(DetalleReserva.objects.select_for_update(no_key=True, of=("self",)).filter(reserva__in=reservas).order_by("pk"))


# ---- el recorte (regla 6 de 8.9) ----


def recortar_partida(partida, nueva_disponible):
    """Recorta las líneas de la partida hasta que lo reservado en reservas «activas» o «lista para entrega» iguale `nueva_disponible` (la que va a quedar después de la
    merma o del vencimiento). Corre dentro de la transacción del llamador y con todo bloqueado; no audita ni notifica. Devuelve `Recorte(lineas, reservas_liberadas,
    por_detalle)`: las líneas recortadas con lo que perdieron, en el orden de recorte; las reservas que quedaron sin cobertura (ahora «liberadas»); y, por detalle de
    venta o período, lo que perdió. La línea recortada queda en 0 y se conserva (D-64 punto 7); una reserva pasa a «liberada» solo si su cubierto total queda en 0."""
    _exigir_transaccion("recortar_partida")
    lineas = list(
        DetalleReserva.objects.filter(partida=partida, reserva__estado_reserva__in=OCUPAN, cantidad_reservada__gt=0).select_related("reserva").order_by("pk")
    )
    exceso = sum(l.cantidad_reservada for l in lineas) - nueva_disponible
    if exceso <= 0:
        return Recorte([], [], [])
    items = [LineaARecortar("cv" if l.reserva.detalle_venta_id else "sum", l.reserva.fecha_entrega_reserva, l.reserva_id, l) for l in lineas]
    recortadas = []
    for item in orden_de_recorte(items):
        if exceso <= 0:
            break
        quitar = min(exceso, item.linea.cantidad_reservada)
        item.linea.cantidad_reservada -= quitar
        DetalleReserva.objects.filter(pk=item.linea.pk).update(cantidad_reservada=item.linea.cantidad_reservada)
        recortadas.append((item, quitar))
        exceso -= quitar
    liberadas = []
    for reserva in ReservaStock.objects.filter(pk__in={i.reserva_id for i, _ in recortadas}).order_by("pk"):
        cubierto = sum(_cubierto(r, c, lote) for r, c, lote in DetalleReserva.objects.filter(reserva=reserva).values_list("cantidad_reservada", "cantidad_cosechada", "lote_id"))
        if cubierto == 0:
            ReservaStock.objects.filter(pk=reserva.pk).update(estado_reserva=ReservaStock.Estado.LIBERADA)
            reserva.estado_reserva = ReservaStock.Estado.LIBERADA
            liberadas.append(reserva)
    return Recorte([(i.linea, n) for i, n in recortadas], liberadas, _por_detalle(recortadas))


def _por_detalle(recortadas):
    """Agrupa lo recortado por detalle de venta o por período (`Afectado`), en el orden de recorte, con los objetos releídos de la base."""
    suma, orden = defaultdict(int), []
    for item, n in recortadas:
        reserva = item.linea.reserva
        clave = ("cv", reserva.detalle_venta_id) if item.tipo == "cv" else ("sum", reserva.detalle_suministro_id, reserva.fecha_entrega_reserva)
        if clave not in suma:
            orden.append(clave)
        suma[clave] += n
    ventas = {d.pk: d for d in DetalleVenta.objects.filter(pk__in=[c[1] for c in orden if c[0] == "cv"]).select_related("compra_venta")}
    suministros = {d.pk: d for d in DetalleSuministro.objects.filter(pk__in=[c[1] for c in orden if c[0] == "sum"]).select_related("suministro", "variedad")}
    afectados = []
    for clave in orden:
        if clave[0] == "cv":
            d = ventas[clave[1]]
            afectados.append(Afectado(d, d.compra_venta, suma[clave], d.compra_venta.fecha_pactada_venta))
        else:
            d = suministros[clave[1]]
            afectados.append(Afectado(Periodo(d, clave[2]), d.suministro, suma[clave], clave[2]))
    return afectados


def _recubrir(afectados, actor):
    """Extensión 3a de PROD-VNC-CAM y 10c de PROD-REG-MRM: por cada detalle o período afectado, intenta volver a cubrir lo recortado y sigue el camino de faltante con lo que no
    se cubre (docs/patrones/stock_maduro.md, sección 8). Un período o un detalle «abierto» de una venta «abierta» se cubre con `asignar`; un detalle «confirmado», con la cantidad
    aceptada como pedida (D-64 punto 13); un detalle o una venta «pendiente de decisión» va directo al camino de faltante (precondición b de PROD-ASG-STK). Con todo bloqueado
    y en la transacción del llamador. Devuelve `Recubierto(reservas, cosechas, faltantes, detalles)`."""
    reservas, cosechas, sin_cubrir_de, detalles, enlaces_nuevos = [], [], [], [], []
    for a in afectados:
        if isinstance(a.objeto, Periodo):
            detalle = DetalleSuministro.objects.select_related("suministro").get(pk=a.objeto.detalle.pk)
            periodo = Periodo(detalle, a.objeto.fecha)
            detalles.append(detalle)
            if stock_maduro._se_debe(detalle, periodo.fecha) and detalle.suministro.estado_suministro == Suministro.Estado.VIGENTE:
                asignacion = stock_maduro.asignar(actor, periodo, a.recortado, periodo.fecha, "suministro")
                reservas += asignacion.reservas
                cosechas += asignacion.cosechas
                sin_cubrir = asignacion.sin_cubrir
            else:
                sin_cubrir = a.recortado
            if sin_cubrir:
                faltantes.seguir_camino_de_faltante(periodo, sin_cubrir, origen=actor)
        else:
            detalle = DetalleVenta.objects.select_related("compra_venta").get(pk=a.objeto.pk)
            detalles.append(detalle)
            venta_abierta = detalle.compra_venta.estado_venta == CompraVenta.Estado.ABIERTA
            confirmado = detalle.estado_detalle_venta == DetalleVenta.Estado.CONFIRMADO and detalle.cant_entregada_venta is not None
            if venta_abierta and (detalle.estado_detalle_venta == DetalleVenta.Estado.ABIERTO or confirmado):
                asignacion = stock_maduro.asignar(
                    actor, detalle, a.recortado, a.fecha_entrega, "compra_venta", confirmado=detalle.estado_detalle_venta == DetalleVenta.Estado.CONFIRMADO
                )
                reservas += asignacion.reservas
                cosechas += asignacion.cosechas
                sin_cubrir = asignacion.sin_cubrir
            else:
                sin_cubrir = a.recortado
            if sin_cubrir:
                camino = faltantes.seguir_camino_de_faltante(detalle, sin_cubrir, origen=actor)
                if camino.enlace is not None:
                    enlaces_nuevos.append(camino.enlace)
        if sin_cubrir:
            sin_cubrir_de.append((a.contrato.codigo, sin_cubrir))
    entregas.programar_para_reservas([r.pk for r in reservas])  # si PROD-ASG-STK volvió a cubrir con stock listo, la entrega se planifica después de confirmar (COM-05a1)
    return Recubierto(reservas, cosechas, sin_cubrir_de, detalles, enlaces_nuevos)


def _avisar_merma_reservada(partida, merma, recubierto, afectados, motivo):
    """Postcondición d (3a.4) de PROD-VNC-CAM y 10c.6 de PROD-REG-MRM: la alerta `comercial_merma_camara_reservada` (enlazada a la merma por `AlertaDeMerma`; para el Agrónomo, o el
    Gerente si no hay) y una notificación al Vendedor de cada contrato afectado, con lo que se perdió, lo que se volvió a cubrir y lo que quedó sin cubrir. Dentro de la transacción (D-42).
    Devuelve la alerta (o `None` si el invernadero está inactivo)."""
    por_contrato = defaultdict(int)
    contratos = {}
    for a in afectados:
        por_contrato[a.contrato.codigo] += a.recortado
        contratos[a.contrato.codigo] = a.contrato
    nombres = " y ".join(por_contrato)
    texto = f"{motivo} {partida.codigo} ({partida.lote.siembra.variedad}) con {_plantas(sum(por_contrato.values()))} reservadas para {nombres}."
    alerta = alertas.crear_alerta_de_evento(partida.lote.invernadero_id, TIPO_MERMA_RESERVADA, _acotar(texto, LARGO_DE_LA_ALERTA))
    if alerta is not None and merma is not None:
        AlertaDeMerma.objects.create(merma=merma, alerta=alerta)
    sin_cubrir = defaultdict(int)
    for codigo, n in recubierto.faltantes:
        sin_cubrir[codigo] += n
    for codigo, perdido in por_contrato.items():
        vendedor = _usuario_activo(contratos[codigo].vendedor_id)
        if vendedor is None:
            continue
        cubierto = perdido - sin_cubrir[codigo]
        detalle = f"{codigo}: {motivo.lower()} {partida.codigo} y se perdieron {_plantas(perdido)} reservadas. Se volvió a cubrir {_plantas(cubierto)}"
        detalle += f"; quedan {_plantas(sin_cubrir[codigo])} sin cubrir." if sin_cubrir[codigo] else "."
        notificaciones.notificar(vendedor, _acotar(f"Cámara: {codigo} perdió producto", 120), _acotar(detalle, LARGO_DE_LA_NOTIFICACION))
    return alerta


def resolver_aviso_de_partida(partida):
    """Pasa a «resuelta» la alerta «partida por vencer» de la partida (postcondición e de PROD-VNC-CAM: cuando se agota por una merma o vence; COM-06 la llama al entregar lo
    último). Devuelve la alerta o `None` si no había una activa. Corre dentro de la transacción del llamador."""
    alertas.resolver_alerta_de_estado(partida.lote.invernadero_id, TIPO_EN_ENTREGA_EN_CURSO, _clave_del_aviso(partida.pk))  # 3b (COM-06a): ya se venció o se agotó
    return alertas.resolver_alerta_de_estado(partida.lote.invernadero_id, TIPO_POR_VENCER, _clave_del_aviso(partida.pk))


# ---- PROD-ASG-CAM ----


def _candidatos(partida, hoy):
    """Paso 3 y regla «Candidato»: los detalles de venta y los períodos de suministro que esperan esta partida, ya con su cantidad sin cubrir y en el orden de prioridad. Una consulta
    por tabla (ventas, sus líneas, detalles de suministro, sus líneas), nunca una por candidato. «Sin detalle de entrega en una entrega no cancelada» se suma en COM-05."""
    invernadero = partida.lote.invernadero
    variedad_id = partida.lote.siembra.variedad_id
    ventas = list(
        DetalleVenta.objects.filter(
            variedad_id=variedad_id,
            estado_detalle_venta__in=(DetalleVenta.Estado.ABIERTO, DetalleVenta.Estado.PENDIENTE_DECISION),
            compra_venta__estado_venta__in=(CompraVenta.Estado.ABIERTA, CompraVenta.Estado.PENDIENTE_DECISION),
            compra_venta__fecha_pactada_venta__lte=partida.fecha_limite,
        )
        .exclude(lineas_de_entrega__entrega__estado_orden__in=entregas.NO_CANCELADAS)  # sin línea en una entrega «a realizar» o «concretada» (COM-05a1)
        .filter(
            Q(compra_venta__modalidad_entrega="retiro", compra_venta__invernadero_retiro_id=invernadero.pk)
            | Q(compra_venta__modalidad_entrega="envio", compra_venta__vendedor_id=invernadero.vendedor_id)
        )
        .select_related("compra_venta__cliente")
        .order_by("pk")
    )
    cubierto = defaultdict(int)
    for detalle_id, reservada, cosechada, lote_id in (
        DetalleReserva.objects.filter(reserva__detalle_venta_id__in=[d.pk for d in ventas])
        .exclude(reserva__estado_reserva=ReservaStock.Estado.LIBERADA)
        .values_list("reserva__detalle_venta_id", "cantidad_reservada", "cantidad_cosechada", "lote_id")
    ):
        cubierto[detalle_id] += _cubierto(reservada, cosechada, lote_id)
    candidatos = []
    for d in ventas:
        sin = max(0, d.cant_solicitada_venta - cubierto[d.pk])
        if sin > 0:
            candidatos.append(Candidato("cv", d, d.compra_venta, d.compra_venta.fecha_pactada_venta, d.compra_venta.fecha_realizacion, (d.pk, 0), sin))
    tope = min(calendario.ventana(hoy), partida.fecha_limite)
    detalles = list(
        DetalleSuministro.objects.filter(
            variedad_id=variedad_id,
            estado_detalle_suministro__in=(DetalleSuministro.Estado.VIGENTE, DetalleSuministro.Estado.FINALIZADO),
            suministro__estado_suministro=Suministro.Estado.VIGENTE,
            suministro__vendedor_id=invernadero.vendedor_id,
            fecha_primer_entrega__lte=tope,
        )
        .select_related("suministro__cliente", "variedad")
        .order_by("pk")
    )
    periodos = [Periodo(d, fecha) for d in detalles for fecha in calendario.calendario(d, hasta=tope)]
    con_entrega = set(  # un período con alguna línea en una entrega «a realizar» o «concretada» ya no es candidato (COM-05a1)
        DetalleEntrega.objects.filter(detalle_suministro_id__in={p.detalle.pk for p in periodos}, entrega__estado_orden__in=entregas.NO_CANCELADAS).values_list("detalle_suministro_id", "fecha_periodo")
    )
    periodos = [p for p in periodos if (p.detalle.pk, p.fecha) not in con_entrega]
    sin_cubrir = stock_maduro.sin_cubrir_de_periodos(periodos)
    for p in periodos:
        if sin_cubrir[p] > 0:
            candidatos.append(
                Candidato("sum", p, p.detalle.suministro, p.fecha, p.detalle.suministro.fecha_realizacion, (p.detalle.pk, p.fecha.toordinal()), sin_cubrir[p])
            )
    return orden_de_candidatos(candidatos)


def _asignable(partida, hoy):
    """Paso 2 y regla «Partida asignable»: «disponible», con fecha límite igual o posterior a hoy y stock libre mayor que cero."""
    return (
        partida.estado_stock_cosechado == StockCosechado.Estado.DISPONIBLE
        and partida.fecha_limite >= hoy
        and partida.cantidad_disponible_cosechado - _reservado_de(partida.pk) > 0
    )


def _correo_de_faltante_cubierto(cliente_id, email, codigo, variedad, cantidad, fecha):
    """Paso 11: el correo al cliente («el faltante quedó cubierto»), después de confirmar. Sin el correo del sistema configurado no se envía (el aviso al Vendedor ya está)."""
    if not correo.correo_configurado():
        return
    correo.enviar_correo(
        Destinatario(cliente_id, email),
        f"Tu pedido {codigo}: el faltante quedó cubierto",
        "comercial/correos/faltante_cubierto.txt",
        {"codigo": codigo, "variedad": variedad, "cantidad": cantidad, "fecha": fecha},
    )


def _asignar_partida(partida_id, hoy):
    """Una partida, en su transacción: pasos 2 a 11 de PROD-ASG-CAM. Devuelve `ResultadoDeAsignacion` o `None` si no había nada que asignar (postcondición i)."""
    previa = StockCosechado.objects.select_related("lote__siembra__variedad", "lote__invernadero").get(pk=partida_id)
    if not _asignable(previa, hoy):
        return None
    candidatos_previos = _candidatos(previa, hoy)
    if not candidatos_previos:
        return None
    with transaction.atomic():
        invernadero = previa.lote.invernadero
        _bloquear_cuentas({invernadero.agronomo_id, invernadero.vendedor_id, *[c.contrato.vendedor_id for c in candidatos_previos]})
        try:
            bloquear_invernadero_activo(invernadero.pk)
            bloquear_variedad(previa.lote.siembra.variedad_id)
        except ValidationError:
            return None  # el invernadero o la variedad se dieron de baja mientras tanto: la partida ya no se asigna
        ventas = [c.contrato for c in candidatos_previos if c.tipo == "cv"]
        suministros = [c.contrato for c in candidatos_previos if c.tipo == "sum"]
        _bloquear_filas(
            previa,
            list({v.pk: v for v in ventas}.values()),
            list({s.pk: s for s in suministros}.values()),
            [c.objeto.pk for c in candidatos_previos if c.tipo == "cv"],
            [c.objeto.detalle.pk for c in candidatos_previos if c.tipo == "sum"],
        )
        partida = StockCosechado.objects.select_related("lote__siembra__variedad", "lote__invernadero__agronomo").get(pk=partida_id)
        if not _asignable(partida, hoy):  # 2a: otra operación la agotó, la tomó o la dio de baja
            return None
        candidatos = _candidatos(partida, hoy)
        libre = partida.cantidad_disponible_cosechado - _reservado_de(partida.pk)
        reservas, lineas, por_contrato = [], [], defaultdict(list)
        reabiertos, ventas_reabiertas, correos = [], {}, []
        for c in candidatos:
            if libre <= 0:
                break
            cuanto = min(libre, c.sin_cubrir)
            reserva = ReservaStock.objects.create(
                **({"detalle_suministro": c.objeto.detalle} if c.tipo == "sum" else {"detalle_venta": c.objeto}),
                invernadero=partida.lote.invernadero,
                fecha_reserva=hoy,
                fecha_entrega_reserva=c.fecha_entrega,
                estado_reserva=ReservaStock.Estado.LISTA_PARA_ENTREGA,
            )
            lineas.append(DetalleReserva.objects.create(reserva=reserva, partida=partida, cantidad_reservada=cuanto))
            reservas.append(reserva)
            libre -= cuanto
            restante = c.sin_cubrir - cuanto
            dejo_de_estar_pendiente = c.tipo == "cv" and restante == 0 and c.objeto.estado_detalle_venta == DetalleVenta.Estado.PENDIENTE_DECISION
            if dejo_de_estar_pendiente:  # paso 7: la fecha de pendiente se conserva como historial
                DetalleVenta.objects.filter(pk=c.objeto.pk).update(estado_detalle_venta=DetalleVenta.Estado.ABIERTO)
                c.objeto.estado_detalle_venta = DetalleVenta.Estado.ABIERTO
                reabiertos.append(c.objeto)
                if c.contrato.cliente.email_cliente:
                    correos.append(
                        (c.contrato.cliente.pk, c.contrato.cliente.email_cliente, c.contrato.codigo, str(c.objeto.variedad), cuanto, c.fecha_entrega)
                    )
            variedad = c.objeto.detalle.variedad if c.tipo == "sum" else c.objeto.variedad
            por_contrato[c.contrato.pk].append((c, cuanto, restante, dejo_de_estar_pendiente, str(variedad)))
        for d in reabiertos:  # 7 y 7b: la venta vuelve a «abierta» si ya no le queda un detalle pendiente
            venta = d.compra_venta
            if venta.pk not in ventas_reabiertas and venta.estado_venta == CompraVenta.Estado.PENDIENTE_DECISION:
                if not DetalleVenta.objects.filter(compra_venta=venta, estado_detalle_venta=DetalleVenta.Estado.PENDIENTE_DECISION).exists():
                    CompraVenta.objects.filter(pk=venta.pk).update(estado_venta=CompraVenta.Estado.ABIERTA)
                    venta.estado_venta = CompraVenta.Estado.ABIERTA
                    ventas_reabiertas[venta.pk] = venta
        reservado = sum(l.cantidad_reservada for l in lineas)
        # Postcondición d: una venta que vuelve a «abierta» ya no tiene detalles pendientes, así que su enlace de decisión deja de servir (`anulado`; D-65 punto 5). Va al final del orden de bloqueo.
        anulados = [e for venta in ventas_reabiertas.values() for e in enlaces.anular_enlaces_de(venta)]
        _avisar_asignacion(partida, por_contrato, libre)
        entregas.programar_para_reservas([r.pk for r in reservas])  # paso 9 y postcondición e: cada venta o período que quedó listo se planifica después de confirmar
        for argumentos in correos:
            transaction.on_commit(partial(_correo_de_faltante_cubierto, *argumentos))
        afectados = [partida, *reservas, *lineas, *reabiertos, *ventas_reabiertas.values(), *anulados]
        datos = {
            "partida": referencia(partida),
            "reservas": [f"{c.contrato.codigo} · {_plantas(n)} · entrega {c.fecha_entrega:%d/%m/%Y}" for items in por_contrato.values() for c, n, *_ in items],
        }
        if reabiertos:
            datos["detalles_reabiertos"] = [f"{d.compra_venta.codigo} · {d.variedad}" for d in reabiertos]
        if ventas_reabiertas:
            datos["ventas_reabiertas"] = [v.codigo for v in ventas_reabiertas.values()]
        if anulados:
            datos["enlaces_anulados"] = [str(e) for e in anulados]
        RegistroAuditoria.objects.registrar(usuario=None, accion=RegistroAuditoria.Accion.ASIGNACION_CAMARA, afectados=afectados, detalle={"datos": datos})
    return ResultadoDeAsignacion(partida, reservas, reabiertos, list(ventas_reabiertas.values()), reservado)


def _avisar_asignacion(partida, por_contrato, libre):
    """Pasos 10 y 11 (10a, 10b, 11a), dentro de la transacción (D-42): al Vendedor de cada contrato, una notificación solo con lo suyo; al Agrónomo del invernadero (si tiene uno
    activo), una por partida con todos los contratos."""
    resumen = []
    for items in por_contrato.values():
        contrato = items[0][0].contrato
        partes = []
        for c, cuanto, restante, dejo, variedad in items:
            parte = f"{variedad}: {_plantas(cuanto)} de la cámara ({partida.codigo}), entrega el {c.fecha_entrega:%d/%m/%Y}."
            if restante:
                parte += f" Sigue sin cubrir: {_plantas(restante)}."
            if dejo:
                tiene_correo = bool(contrato.cliente.email_cliente)
                parte += " El detalle dejó de estar pendiente" + ("; el cliente recibe un correo." if tiene_correo else " y el cliente no tiene correo: avisale vos.")
            partes.append(parte)
            resumen.append(f"{contrato.codigo} ({cuanto}, entrega {c.fecha_entrega:%d/%m/%Y})")
        vendedor = _usuario_activo(contrato.vendedor_id)
        if vendedor is not None:
            notificaciones.notificar(vendedor, f"Stock de cámara para {contrato.codigo}", _acotar(" ".join(partes), LARGO_DE_LA_NOTIFICACION))
    agronomo = partida.lote.invernadero.agronomo
    if agronomo is not None and agronomo.is_active:
        detalle = f"Vence el {partida.fecha_limite:%d/%m/%Y}. Reservada para: {', '.join(resumen)}. Stock libre que le queda: {_plantas(libre)}."
        notificaciones.notificar(agronomo, f"Partida {partida.codigo} asignada", _acotar(detalle, LARGO_DE_LA_NOTIFICACION))


def asignar_camara(partida_ids, hoy=None):
    """PROD-ASG-CAM: asigna el stock libre de cada partida a quien lo espera. Las procesa de a una, de la que vence antes a la que vence después y, si empatan, la de menor id
    (extensión 1a), cada una en su transacción. Una que falla se registra con `logger.exception` y las demás siguen; la recupera el paso diario 25 (extensión *a, D-64 punto 9).
    Devuelve los `ResultadoDeAsignacion` de las partidas en las que se asignó algo. `hoy` es `stock.hoy()` por omisión. NO se llama dentro de una transacción: la dispara
    `programar_asignacion_de_camara` con `on_commit`."""
    hoy = hoy or stock.hoy()
    resultados = []
    for partida_id in StockCosechado.objects.filter(pk__in=list(partida_ids)).order_by("fecha_limite", "pk").values_list("pk", flat=True):
        try:
            resultado = _asignar_partida(partida_id, hoy)
        except Exception:  # noqa: BLE001 - una partida que falla no puede dejar a las demás sin asignar (extensión *a)
            logger.exception("Falló la asignación de cámara de la partida %s", partida_id)
            continue
        if resultado is not None:
            resultados.append(resultado)
    return resultados


def programar_asignacion_de_camara(partida_ids):
    """D-64 punto 9: registra con `transaction.on_commit` la asignación de esas partidas, para que corra en el mismo pedido DESPUÉS de confirmar la transacción de quien la
    dispara (situación 5 de PROD-ASG-CAM). La llaman PROD-CNC-CSC (k) y la cancelación de una cosecha (h). Sin partidas, no programa nada."""
    ids = sorted({i for i in partida_ids if i})
    if ids:
        transaction.on_commit(lambda: asignar_camara(ids))


def reasignar_camara(hoy):
    """Paso diario 25, «Reasignar cámara» (D-64 punto 9): recupera una asignación que falló (garantía mínima 2) corriendo PROD-ASG-CAM sobre toda partida «disponible» con
    `fecha_limite >= hoy` y stock libre mayor que 0. Idempotente: sin candidatos no hace nada. `ResumenDePaso(procesados=partidas con stock libre, creados=reservas creadas,
    resueltos=0, detalle=«N partidas con reservas nuevas»)`."""
    ids = list(
        _con_libre(StockCosechado.objects.filter(estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE, fecha_limite__gte=hoy))
        .filter(libre__gt=0)
        .order_by("fecha_limite", "pk")
        .values_list("pk", flat=True)
    )
    resultados = asignar_camara(ids, hoy)
    return ResumenDePaso(len(ids), sum(len(r.reservas) for r in resultados), 0, f"{len(resultados)} partidas con reservas nuevas")


# ---- PROD-VNC-CAM ----


def _vencer_en_transaccion(partida_id, hoy, previo):
    """Un intento de vencer la partida (todo en una transacción). `previo` son los ids de detalles con líneas que vio la lectura sin bloquear; si al bloquear aparecen otros,
    `_ContratosNuevos`. Devuelve un `SimpleNamespace`-like `(partida, reservado, aviso_resuelto)` o `None` si ya no correspondía vencerla."""
    detalles_de_venta, detalles_de_suministro = previo
    with transaction.atomic():
        p = StockCosechado.objects.select_related("lote__siembra__variedad", "lote__invernadero__agronomo").get(pk=partida_id)
        ventas, suministros = _contratos_de(detalles_de_venta, detalles_de_suministro)
        _bloquear_cuentas({p.lote.invernadero.agronomo_id, *[c.vendedor_id for c in (*ventas, *suministros)]})
        activos = _bloquear_invernaderos(p.lote.invernadero_id, [*ventas, *suministros], activo=False)
        list(Variedad.objects.select_for_update(no_key=True).filter(pk=p.lote.siembra.variedad_id))  # sin exigir que esté activa: el vencimiento no puede fallar
        stock_maduro.bloquear_candidatos([p.lote.siembra.variedad_id], activos)
        _bloquear_filas(p, ventas, suministros, detalles_de_venta, detalles_de_suministro)
        p = StockCosechado.objects.select_related("lote__siembra__variedad", "lote__invernadero__agronomo").get(pk=partida_id)
        if p.estado_stock_cosechado != StockCosechado.Estado.DISPONIBLE or p.fecha_limite >= hoy:
            return None  # otra operación la agotó o la venció: ya no corresponde
        actual = _contratos_con_lineas(partida_id)
        if not (actual[0] <= detalles_de_venta and actual[1] <= detalles_de_suministro):
            raise _ContratosNuevos()
        recorte = recortar_partida(p, 0)
        entregas_afectadas = entregas.entregas_de_reservas([l.reserva_id for l, _ in recorte.lineas])
        resultado = fisico.vencer_partida(p, hoy)  # a y c: primero lo físico; después se vuelve a cubrir (decisión del plan)
        recubierto = _recubrir(recorte.por_detalle, None)
        quita = entregas.quitar_lineas_liberadas(None, entregas_afectadas, "Se venció en cámara el producto reservado.")  # 3a y postcondición d
        merma = resultado.merma if resultado is not None else None
        alerta = None
        if recorte.lineas:
            alerta = _avisar_merma_reservada(p, merma, recubierto, recorte.por_detalle, "Venció la partida")
        aviso = resolver_aviso_de_partida(p)  # e
        # CON-04c (D-92 puntos 3 a 6): el asiento de la merma por vencimiento (postcondición b), DESPUÉS de todos los bloqueos; actor `None` (InfoPonia).
        asiento = asientos_comerciales.asentar_merma_de_partida(None, merma, resultado.movimiento, hoy, hoy) if resultado is not None else None
        afectados = [p, *([merma, resultado.movimiento] if resultado is not None else []), *[l for l, _ in recorte.lineas], *recorte.reservas_liberadas]
        afectados += [asiento] if asiento is not None else []
        afectados += [*recubierto.reservas, *recubierto.cosechas, *recubierto.detalles, *recubierto.enlaces, *[c.entrega for c in quita.cancelaciones]]
        if alerta is not None:
            afectados.append(alerta)
        datos = {"partida": referencia(p), "fecha_limite": f"{p.fecha_limite:%d/%m/%Y}"}
        if asiento is not None:
            datos["asientos"] = [str(asiento)]
        if recorte.lineas:
            datos["lineas_recortadas"] = [f"{a.contrato.codigo}: {a.recortado}" for a in recorte.por_detalle]
            if recorte.reservas_liberadas:
                datos["reservas_liberadas"] = [str(r) for r in recorte.reservas_liberadas]
        if recubierto.reservas:
            datos["recubierto"] = [str(r) for r in recubierto.reservas]
        if quita.lineas_quitadas:
            datos["lineas_quitadas"] = [str(l) for l in quita.lineas_quitadas]
        if quita.cancelaciones:
            datos["entregas_canceladas"] = [str(c.entrega) for c in quita.cancelaciones]
        if recubierto.faltantes:
            datos["sin_cubrir_tras_recorte"] = [f"{codigo}: {n}" for codigo, n in recubierto.faltantes]
        RegistroAuditoria.objects.registrar(usuario=None, accion=RegistroAuditoria.Accion.VENCIMIENTO_PARTIDA, afectados=afectados, detalle={"datos": datos})
        return (p, sum(n for _, n in recorte.lineas), aviso is not None)


def _entregas_en_curso_de(partida_id, hoy):
    """Los códigos de las entregas «a realizar» **en curso** (MD-118) con producto de esta partida en alguna de sus reservas no liberadas. Lectura sin bloquear."""
    reservas = DetalleReserva.objects.filter(partida_id=partida_id, cantidad_reservada__gt=0).exclude(reserva__estado_reserva=ReservaStock.Estado.LIBERADA).values("reserva_id")
    candidatas = Entrega.objects.filter(estado_orden=entregas.A_REALIZAR, lineas__reservas__in=reservas).distinct().order_by("pk")
    return [e.codigo for e in candidatas if entregas.en_curso(e, hoy)]


def _posponer_por_entrega_en_curso(partida_id, hoy):
    """PROD-VNC-CAM, extensión 3b (COM-06a): si la partida vencida tiene producto en una entrega **en curso** (el producto ya salió en el vehículo), hoy no se vence: se deja para la próxima
    ejecución y se asegura la alerta de estado `comercial_partida_en_entrega_en_curso` para el Gerente (crítica, clave `partida:<id>`), que se resuelve cuando la partida se vence o se agota.
    «No debería ocurrir» (este paso corre antes de las rutas). Devuelve `True` si pospuso."""
    codigos = _entregas_en_curso_de(partida_id, hoy)
    if not codigos:
        return False
    with transaction.atomic():
        partida = StockCosechado.objects.select_related("lote").get(pk=partida_id)
        bloquear_invernadero_para_alertas(partida.lote.invernadero_id)
        descripcion = _acotar(f"{partida.codigo} está vencida y tiene producto en {', '.join(codigos)}, que ya salió en ruta: se vence cuando termine.", LARGO_DE_LA_ALERTA)
        alerta = alertas.asegurar_alerta_de_estado(partida.lote.invernadero_id, TIPO_EN_ENTREGA_EN_CURSO, _clave_del_aviso(partida_id), descripcion)
        if alerta is not None:
            AlertaComercial.objects.get_or_create(alerta=alerta, defaults={"partida": partida})
    return True


def _vencer_partida(partida_id, hoy):
    """Pasos 2 y 3 y extensión 3a de PROD-VNC-CAM para una partida. Lee sin bloquear qué contratos tienen líneas en ella, bloquea y relee; si aparecieron contratos nuevos,
    repite la lectura una vez y, si vuelven a cambiar, la deja para la próxima ejecución. Devuelve `(partida, plantas reservadas que perdió, si resolvió el aviso)` o `None`."""
    for _ in range(2):
        previo = _contratos_con_lineas(partida_id)
        try:
            return _vencer_en_transaccion(partida_id, hoy, previo)
        except _ContratosNuevos:
            continue
    logger.warning("La partida %s cambió de contratos mientras se bloqueaba dos veces: queda para la próxima ejecución.", partida_id)
    return None


def _descripcion_del_aviso(partida, libre, hoy):
    """«Lechuga Crespa · P-12: 40 plantas libres vencen el 25/11/2026 (en 2 días)»."""
    dias = (partida.fecha_limite - hoy).days
    cuando = "hoy" if dias == 0 else f"en {dias} {'día' if dias == 1 else 'días'}"
    return _acotar(f"{partida.lote.siembra.variedad} · {partida.codigo}: {_plantas(libre)} libres vencen el {partida.fecha_limite:%d/%m/%Y} ({cuando})", LARGO_DE_LA_ALERTA)


def _avisar_partida(partida_id, hoy, dias):
    """Pasos 4 y 5: el aviso previo de una partida, en su transacción (invernadero → partida). Una sola vez por partida. Devuelve `True` si lo creó."""
    with transaction.atomic():
        previa = StockCosechado.objects.select_related("lote__invernadero").get(pk=partida_id)
        try:
            invernadero = bloquear_invernadero_activo(previa.lote.invernadero_id)
        except ValidationError:
            return False
        StockCosechado.objects.select_for_update(no_key=True, of=("self",)).filter(pk=partida_id).first()
        p = StockCosechado.objects.select_related("lote__siembra__variedad").get(pk=partida_id)
        libre = p.cantidad_disponible_cosechado - _reservado_de(p.pk)
        en_plazo = hoy <= p.fecha_limite <= hoy + timedelta(days=dias)
        if p.estado_stock_cosechado != StockCosechado.Estado.DISPONIBLE or libre <= 0 or not en_plazo or AlertaComercial.objects.filter(partida=p).exists():
            return False
        descripcion = _descripcion_del_aviso(p, libre, hoy)
        alerta = alertas.asegurar_alerta_de_estado(invernadero.pk, TIPO_POR_VENCER, _clave_del_aviso(p.pk), descripcion)
        if alerta is None:
            return False
        AlertaComercial.objects.create(alerta=alerta, partida=p)
        vendedor = _usuario_activo(invernadero.vendedor_id)
        if vendedor is not None:
            notificaciones.notificar(vendedor, "Partida por vencer", descripcion)
        RegistroAuditoria.objects.registrar(
            usuario=None,
            accion=RegistroAuditoria.Accion.AVISO_PARTIDA_POR_VENCER,
            afectados=[p, alerta],
            detalle={"datos": {"partida": referencia(p), "fecha_limite": f"{p.fecha_limite:%d/%m/%Y}", "dias_para_vencer": str((p.fecha_limite - hoy).days)}},
        )
        return True


def _avisar_por_vencer(hoy):
    """Pasos 4 y 5 y extensión 4a: las partidas «disponibles» con stock libre que vencen dentro de `dias_aviso_vencimiento_camara` días y todavía no tuvieron su aviso. Con 0 días,
    ninguna. Cada una en su transacción; una que falla se registra y las demás siguen. Devuelve la cantidad de avisos creados."""
    dias = configuracion.obtener().dias_aviso_vencimiento_camara
    if dias <= 0:
        return 0
    ids = list(
        _con_libre(
            StockCosechado.objects.filter(
                estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE, fecha_limite__gte=hoy, fecha_limite__lte=hoy + timedelta(days=dias)
            )
        )
        .filter(libre__gt=0)
        .exclude(alertas_comerciales__isnull=False)
        .order_by("fecha_limite", "pk")
        .values_list("pk", flat=True)
    )
    creados = 0
    for partida_id in ids:
        try:
            creados += 1 if _avisar_partida(partida_id, hoy, dias) else 0
        except Exception:  # noqa: BLE001 - un aviso que falla no corta el paso (extensión *a)
            logger.exception("Falló el aviso de la partida %s", partida_id)
    return creados


def vencer_partidas_en_camara(hoy):
    """PROD-VNC-CAM, paso diario 20, «Vencer partidas en cámara» (D-56, D-59): da de baja las partidas «disponibles» con fecha límite ANTERIOR a hoy (el día de la fecha límite
    todavía se entrega) y avisa de las que vencen dentro del plazo. Cada partida en su transacción; una que falla se registra con `logger.exception` y las demás siguen (*a):
    al día siguiente se retoma. Idempotente. Nunca lee la fecha por su cuenta. Devuelve `ResumenDePaso(procesados=partidas vencidas, creados=avisos nuevos,
    resueltos=alertas «partida por vencer» resueltas, detalle=«N partidas con producto reservado»)`."""
    vencidas = resueltas = con_reservado = 0
    ids = list(
        StockCosechado.objects.filter(estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE, fecha_limite__lt=hoy).order_by("fecha_limite", "pk").values_list("pk", flat=True)
    )
    for partida_id in ids:
        try:
            if _posponer_por_entrega_en_curso(partida_id, hoy):  # 3b
                continue
            resultado = _vencer_partida(partida_id, hoy)
        except Exception:  # noqa: BLE001 - una partida que falla no puede dejar a las demás sin vencer (extensión *a)
            logger.exception("Falló el vencimiento de la partida %s", partida_id)
            continue
        if resultado is None:
            continue
        _, reservado, aviso_resuelto = resultado
        vencidas += 1
        con_reservado += 1 if reservado else 0
        resueltas += 1 if aviso_resuelto else 0
    avisos = _avisar_por_vencer(hoy)
    return ResumenDePaso(vencidas, avisos, resueltas, f"{con_reservado} partidas con producto reservado")


# ---- la campana (D-62) y la pestaña «Cámara» ----


def enlaces_de_alertas_de_camara(usuario, alertas_de_camara):
    """Registrante de `maestros.extensiones.registrar_enlace_de_alerta` para `comercial_partida_por_vencer` y `comercial_merma_camara_reservada` (D-62; `camara.md`, «Pestaña
    «Cámara»»): las dos llevan a la pestaña «Cámara» del invernadero de la alerta, para el Agrónomo y el Gerente; otro rol, nada (queda el enlace por omisión, que no lleva a un 403).
    Una consulta para toda la lista."""
    alertas_de_camara = list(alertas_de_camara)
    if not alertas_de_camara or rol_de(usuario) not in (GERENTE, AGRONOMO):
        return {}
    vinculos = {
        v.alerta_id: v
        for v in AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_de_camara], partida__isnull=False).select_related("partida")
    }
    enlaces = {}
    for alerta in alertas_de_camara:
        url = reverse("maestros:invernadero", args=[alerta.invernadero_id]) + "?pestana=camara"
        vinculo = vinculos.get(alerta.pk)
        texto = f"{vinculo.partida.codigo} · vence el {vinculo.partida.fecha_limite:%d/%m}" if vinculo else alerta.descripcion_alerta
        enlaces[alerta.pk] = Enlace(url, texto)
    return enlaces


def indicadores_de_camara(invernadero_ids, hoy):
    """Los indicadores de la pestaña «Cámara» y del panel del Agrónomo (`tabCamara` y `secCosecha` del prototipo): partidas disponibles, sus plantas, las plantas libres y las que
    vencen en `dias_aviso_vencimiento_camara` días o menos. Una sola consulta, sin consultas por fila."""
    ids = list(invernadero_ids)
    dias = configuracion.obtener().dias_aviso_vencimiento_camara
    disponibles = libres = por_vencer = plantas = 0
    if ids:
        filas = _con_libre(
            StockCosechado.objects.filter(lote__invernadero_id__in=ids, estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE)
        ).values_list("fecha_limite", "cantidad_disponible_cosechado", "libre")
        for fecha_limite, disponible, libre in filas:
            disponibles += 1
            plantas += disponible
            libres += max(0, libre)
            por_vencer += 1 if fecha_limite <= hoy + timedelta(days=dias) else 0
    return {"disponibles": disponibles, "plantas": plantas, "libres": libres, "por_vencer": por_vencer, "dias_de_aviso": dias}


def _ve_la_camara(actor, invernadero):
    """Quién ve la pestaña «Cámara»: el Gerente, el Agrónomo a cargo, el Capataz asignado y el Vendedor del invernadero (`camara.md`)."""
    if not getattr(actor, "is_active", False):
        return False
    rol = rol_de(actor)
    return (
        rol == GERENTE
        or (rol == AGRONOMO and invernadero.agronomo_id == actor.pk)
        or (rol == CAPATAZ and invernadero.capataz_id == actor.pk)
        or (rol == VENDEDOR and invernadero.vendedor_id == actor.pk)
    )


def filas_de_camara(invernadero_id, hoy, dias):
    """Las filas de la pestaña «Cámara» (`tabCamara`): primero las partidas disponibles por fecha límite; después las agotadas y vencidas de los últimos 30 días (para que la tabla no crezca
    sin fin; las demás quedan en la bitácora y en la auditoría). Dos consultas en total (más una por las mermas de las vencidas): sin consultas por fila."""
    todas = fisico.partidas_del_invernadero([invernadero_id])
    reservado = {
        f["partida_id"]: f["total"]
        for f in DetalleReserva.objects.filter(partida__lote__invernadero_id=invernadero_id, reserva__estado_reserva__in=OCUPAN)
        .values("partida_id")
        .annotate(total=Sum("cantidad_reservada"))
    }
    corte = hoy - timedelta(days=DIAS_DE_CERRADAS)
    abiertas = [p for p in todas if p.estado == StockCosechado.Estado.DISPONIBLE]
    cerradas = sorted((p for p in todas if p.estado != StockCosechado.Estado.DISPONIBLE and p.fecha_limite >= corte), key=lambda p: (p.fecha_limite, p.partida_id), reverse=True)
    perdido = {}
    vencidas = [p.partida_id for p in cerradas if p.estado == StockCosechado.Estado.VENCIDO]
    if vencidas:
        origenes = {m.partida_id: m.origen_id for m in MovimientoStock.objects.filter(partida_id__in=vencidas, tipo_movimiento=MovimientoStock.TipoMovimiento.MERMA_EN_CAMARA)}
        causas = dict(Merma.objects.filter(pk__in=list(origenes.values())).values_list("pk", "causa"))
        cantidades = {m.origen_id: m.cantidad for m in MovimientoStock.objects.filter(partida_id__in=vencidas, tipo_movimiento=MovimientoStock.TipoMovimiento.MERMA_EN_CAMARA)}
        perdido = {pid: cantidades[o] for pid, o in origenes.items() if causas.get(o) == Merma.Causa.VENCIMIENTO_EN_CAMARA}
    filas = []
    for p in [*abiertas, *cerradas]:
        reservado_p = reservado.get(p.partida_id, 0)
        if p.estado == StockCosechado.Estado.DISPONIBLE:
            por_vencer = dias > 0 and (p.fecha_limite - hoy).days <= dias
            estado, clase = (f"Vence el {p.fecha_limite:%d/%m/%Y}", "warn") if por_vencer else ("Disponible", "ok")
        else:
            estado, clase = ("Vencida", "neutral") if p.estado == StockCosechado.Estado.VENCIDO else ("Agotada", "neutral")
        filas.append(
            {
                "codigo": p.codigo,
                "variedad": p.variedad,
                "lote": p.lote_codigo,
                "motivo": StockCosechado.Motivo(p.motivo).label,
                "ingreso": p.fecha_ingreso,
                "limite": p.fecha_limite,
                "disponible": p.disponible,
                "reservado": reservado_p,
                "libre": max(0, p.disponible - reservado_p),
                "estado": estado,
                "clase": clase,
                "cerrada": p.estado != StockCosechado.Estado.DISPONIBLE,
                "merma": perdido.get(p.partida_id),
            }
        )
    return filas


def pestana_de_camara(actor, invernadero):
    """`registrar_pestana_de_invernadero("camara", "Cámara", ...)` (disparador «Cuando exista Lote, OrdenTrabajo o StockCosechado»): el HTML de la cámara del invernadero (`camaraTab`
    y `tabCamara`: tres indicadores y la tabla de partidas con lo reservado), o `None` si `actor` no la ve. Solo consulta; el Agrónomo a cargo además tiene «Registrar merma en cámara»."""
    if not _ve_la_camara(actor, invernadero):
        return None
    hoy = stock.hoy()
    indicadores = indicadores_de_camara([invernadero.pk], hoy)
    url = entradas_de_comercial(actor).merma_en_camara
    puede_registrar = url if (url and rol_de(actor) == AGRONOMO and invernadero.agronomo_id == actor.pk) else None
    return render_to_string(
        "comercial/camara/_pestana.html",
        {
            "filas": filas_de_camara(invernadero.pk, hoy, indicadores["dias_de_aviso"]),
            "indicadores": indicadores,
            "url_de_merma": f"{puede_registrar}?invernadero={invernadero.pk}" if puede_registrar else None,
        },
    )
