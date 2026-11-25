# Concreción de entregas de `comercial` (COM-06a): COM-CNC-ENT con el retiro (1a) y la discrepancia de un suministro (14c). Lo que registra la concreción: la cámara (egreso, merma de
# entrega y devolución, con el núcleo de `produccion`, sección 10 de `docs/api/produccion.md`), los envases (cierre de las reservas y consumo), los montos y el vencimiento, el pago
# y el cierre de una compra-venta, el fin del detalle y del suministro y la discrepancia. Todo en UNA transacción y con UN registro de auditoría (D-36). Sin asientos (D-57).
# Fuente: docs/casos_de_uso/comercial/rutas.md («Concretar»), D-68 y docs/patrones/bloqueos.md («Concretar una entrega»).
#
# Bloqueos (`FOR NO KEY UPDATE`): las cuentas (el actor, el Vendedor del contrato y el Agrónomo del invernadero de origen) → el invernadero de origen → las variedades → los lotes de
# origen → las partidas de origen → el contrato → sus detalles → la entrega (`OrdenTrabajo`) → sus reservas de stock con sus `DetalleReserva` → los `InsumoInvernadero` de los envases
# y sus lotes → las reservas de insumo. Con todo tomado se relee y se verifica (14a y la huella). Los avisos van dentro de la transacción (D-42); los correos, con `on_commit` (D-14).

import json
import logging
from collections import defaultdict, namedtuple
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction
from functools import partial

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse

from comercial.models import (
    AlertaComercial,
    CompraVenta,
    Contrato,
    DetalleEntrega,
    DetalleReserva,
    DetalleSuministro,
    DetalleVenta,
    DiscrepanciaEntrega,
    Entrega,
    IntentoFallido,
    LineaDiscrepancia,
    EnlaceCliente,
    PagoCliente,
    ReservaStock,
    Suministro,
    Vehiculo,
)
from comercial.servicios import calendario, enlaces, entregas, rutas, solicitudes
from comercial.servicios import camara as camara_comercial
from comercial.servicios.comprobantes import Destinatario
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario import categorias
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, insumos_invernadero, stock
from maestros.extensiones import Enlace
from maestros.models import Variedad
from maestros.servicios import alertas
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import Lote, OrdenTrabajo, ReservaInsumo, StockCosechado
from produccion.servicios import camara as fisico
from produccion.servicios import consumos, cosechas, mermas

logger = logging.getLogger("infoponia.entregas")

TIPO_DISCREPANCIA = "comercial_discrepancia_entrega"  # EVENTO, GERENTE, ADVERTENCIA, origen SOLICITUD_REVISION (extensión 14c)
LARGO_DE_LA_ALERTA = 200
LARGO_DE_LA_DESCRIPCION = 300
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
CENTAVOS = Decimal("0.01")
A_REALIZAR = OrdenTrabajo.Estado.A_REALIZAR
ENVIO, RETIRO = Entrega.Modalidad.ENVIO, Entrega.Modalidad.RETIRO
TRANSPORTISTA, VENDEDOR, GERENTE = Usuario.Rol.TRANSPORTISTA, Usuario.Rol.VENDEDOR, Usuario.Rol.GERENTE
ACTIVA = ReservaInsumo.Estado.ACTIVA
AVISO = Entrega.EstadoDelAviso
MEDIOS = PagoCliente.Medio.values

# Un origen físico de una línea: una `DetalleReserva` con producto («lote» cosechado o «partida» de cámara). `clave` ordena de forma determinista; `aporte` es lo que aporta a la línea
# (lote: la cosechada que le quedó; partida: la reservada); `fecha_limite` es la de la partida o la de la cosecha más la postcosecha de la variedad; `costo` es el costo por planta del
# origen y `fecha_cosecha`, la de la cosecha de origen (solo en un lote).
Origen = namedtuple("Origen", "clave tipo lote partida fecha_cosecha aporte fecha_limite costo reserva")
Reparto = namedtuple("Reparto", "origen perdida devuelta entregada")
LineaLeida = namedtuple("LineaLeida", "linea detalle variedad planificada origenes reservas")
LineaResuelta = namedtuple("LineaResuelta", "leida llego perdida devuelta entregada precio monto rechazada repartos bajo_el_minimo")
EnvaseResuelto = namedtuple("EnvaseResuelto", "existencia reserva reservada utilizada devuelta exceso consumo")
EnvaseDeclarado = namedtuple("EnvaseDeclarado", "existencia cantidad")
FilaConcretable = namedtuple("FilaConcretable", "entrega codigo cliente destino contenido es_suministro demorada dias_de_retraso")
ResultadoDeDiscrepancia = namedtuple("ResultadoDeDiscrepancia", "discrepancia lineas alerta")


# ---- los datos que carga la persona ----


@dataclass
class DatosDeConcrecion:
    """Lo que la persona indica en los pasos 5 a 11, tal cual llega del formulario (texto): `llego[linea_id]` (por omisión, lo planificado), `acepta[linea_id]` (compra-venta; por omisión,
    acepta), `recibio[linea_id]` (suministro; por omisión, lo que llegó), `descripcion_perdida`, por cada envase reservado `utilizada[iin_id]`, `devuelta[iin_id]` (por omisión, la
    propuesta) y `confirmo_exceso`, `declarado[iin_id]` y `sin_envases` (envasado no planificado, 9a) y `medio_pago`."""

    llego: dict = field(default_factory=dict)
    acepta: dict = field(default_factory=dict)
    recibio: dict = field(default_factory=dict)
    descripcion_perdida: str = ""
    utilizada: dict = field(default_factory=dict)
    devuelta: dict = field(default_factory=dict)
    confirmo_exceso: set = field(default_factory=set)
    declarado: dict = field(default_factory=dict)
    sin_envases: bool = False
    medio_pago: str = ""


def datos_de_concrecion(post):
    """Arma los `DatosDeConcrecion` de un `request.POST` (o un dict): campos `llego_<linea>`, `acepta_<linea>` («0» = rechaza), `recibio_<linea>`, `descripcion_perdida`, `utilizada_<iin>`,
    `devuelta_<iin>`, `confirmo_exceso_<iin>`, `declarado_<iin>`, `sin_envases` y `medio_pago`. Lo que no viene queda con su valor por omisión. No valida."""
    datos = DatosDeConcrecion(descripcion_perdida=(post.get("descripcion_perdida") or "").strip(), sin_envases=bool(post.get("sin_envases")), medio_pago=(post.get("medio_pago") or "").strip())
    for clave in list(post.keys()):
        for prefijo, destino in (("llego_", datos.llego), ("recibio_", datos.recibio), ("utilizada_", datos.utilizada), ("devuelta_", datos.devuelta), ("declarado_", datos.declarado)):
            if clave.startswith(prefijo) and clave[len(prefijo):].isdigit():
                destino[int(clave[len(prefijo):])] = post.get(clave)
        if clave.startswith("acepta_") and clave[7:].isdigit():
            datos.acepta[int(clave[7:])] = post.get(clave) != "0"
        if clave.startswith("confirmo_exceso_") and clave[16:].isdigit() and post.get(clave):
            datos.confirmo_exceso.add(int(clave[16:]))
    return datos


# ---- funciones puras ----


def _redondear(valor):
    """Dos decimales, `ROUND_HALF_UP`."""
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _cuotas(base, aportes, total, claves):
    """Reparte `total` unidades en proporción a `base` (una por origen): la parte entera de cada cuota y, de a una, las que faltan a los de mayor parte decimal; si empatan, al que
    más aporta (`aportes`); si siguen empatados, al de fecha límite más próxima y, por último, al de menor clave (`claves` ya trae `(fecha_limite, clave)`)."""
    n = len(base)
    suma = sum(base)
    if total == 0 or suma == 0:
        return [0] * n
    cuotas = [Fraction(b * total, suma) for b in base]
    enteras = [int(c) for c in cuotas]
    restos = [c - e for c, e in zip(cuotas, enteras)]
    orden = sorted(range(n), key=lambda i: (-restos[i], -aportes[i], claves[i]))
    for i in orden[: total - sum(enteras)]:
        enteras[i] += 1
    return enteras


def repartir(origenes, perdida, devuelta):
    """Regla «Reparto entre orígenes» de COM-CNC-ENT. Primero lo perdido, en proporción a lo que aporta cada origen; después lo devuelto, en proporción a lo que le queda a cada uno. Cada
    origen recibe la parte entera de su cuota y las unidades que faltan se asignan de a una a los de mayor parte decimal (si empatan, al que más aporta; si siguen empatados, al de fecha
    límite más próxima y, por último, al de menor clave). Lo entregado de cada origen es lo que le queda. Con un solo origen no hay reparto. Función pura: no toca la base.
    Devuelve una lista de `Reparto(origen, perdida, devuelta, entregada)` en el mismo orden que `origenes`."""
    origenes = list(origenes)
    if len(origenes) == 1:
        o = origenes[0]
        return [Reparto(o, perdida, devuelta, o.aporte - perdida - devuelta)]
    aportes = [o.aporte for o in origenes]
    claves = [(o.fecha_limite, o.clave) for o in origenes]
    perdidas = _cuotas(aportes, aportes, perdida, claves)
    quedan = [a - p for a, p in zip(aportes, perdidas)]
    devueltas = _cuotas(quedan, aportes, devuelta, claves)
    return [Reparto(o, p, d, o.aporte - p - d) for o, p, d in zip(origenes, perdidas, devueltas)]


def _entero(texto, maximo, por_omision):
    """Un entero entre 0 y `maximo` desde un texto («5b»); `por_omision` si no vino; `None` si no es un número entero en el rango."""
    if texto is None or str(texto).strip() == "":
        return por_omision
    texto = str(texto).strip()
    if not texto.isdigit():
        return None
    valor = int(texto)
    return valor if valor <= maximo else None


def _decimal(texto, por_omision):
    """Una cantidad de envase: un decimal `>= 0` con hasta 3 decimales, desde un texto (coma o punto); `por_omision` si no vino; `None` si no es válida."""
    if texto is None or str(texto).strip() == "":
        return por_omision
    try:
        valor = Decimal(str(texto).strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not valor.is_finite() or valor < 0 or valor.as_tuple().exponent < -3:
        return None
    return valor


def _texto_cantidad(valor):
    return f"{Decimal(valor).normalize():f}".replace(".", ",")


# ---- la lectura de una entrega (sin bloquear: el registro la repite con todo bloqueado) ----


@dataclass
class Lectura:
    """Todo lo que la concreción necesita de una entrega: el contrato (con su venta o suministro), las líneas con sus orígenes, las reservas de insumo activas y los envases que se ofrecen."""

    entrega: object
    contrato: object
    venta: object
    suministro: object
    lineas: list
    reservados: dict
    ofrecidos: dict
    es_ultima: bool
    previas: dict  # detalle de venta → lo aceptado en otras entregas concretadas
    pendientes_otras: set  # detalles de venta con líneas en otras entregas «a realizar»
    hoy: object


def _leer(entrega, hoy):
    """Lee la entrega y su contexto sin bloquear (lo llama el registro con todo ya bloqueado). Una consulta por tabla."""
    entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor", "invernadero__agronomo", "transportista").get(pk=entrega.pk)
    contrato = entrega.contrato_entrega
    venta = CompraVenta.objects.filter(pk=contrato.pk).first()
    suministro = None if venta is not None else Suministro.objects.select_related("clausula_suministrado").get(pk=contrato.pk)
    lineas = list(
        entrega.lineas.select_related("detalle_venta__variedad__cultivo", "detalle_suministro__variedad__cultivo", "detalle_suministro__clausula_suministrante").order_by("pk")
    )
    pares = list(DetalleEntrega.reservas.through.objects.filter(detalleentrega_id__in=[l.pk for l in lineas]).values_list("detalleentrega_id", "reservastock_id"))
    reservas = {r.pk: r for r in ReservaStock.objects.filter(pk__in={r for _, r in pares}).exclude(estado_reserva=ReservaStock.Estado.LIBERADA).select_related("cosecha")}
    por_linea = defaultdict(list)
    for linea_id, reserva_id in pares:
        if reserva_id in reservas:
            por_linea[linea_id].append(reservas[reserva_id])
    drs = list(
        DetalleReserva.objects.filter(reserva_id__in=list(reservas)).select_related("lote__siembra__variedad", "partida__lote__siembra__variedad").order_by("pk")
    )
    cosecha_ids = [r.cosecha_id for r in reservas.values() if r.cosecha_id]
    lote_ids = [d.lote_id for d in drs if d.lote_id]
    costos = cosechas.costo_unitario_de_cosecha(cosecha_ids, lote_ids)
    origenes_de = defaultdict(list)
    for dr in drs:
        reserva = reservas[dr.reserva_id]
        if dr.partida_id:
            aporte = dr.cantidad_reservada
            p = dr.partida
            origen = Origen(("p", p.pk), "partida", p.lote, p, None, aporte, p.fecha_limite, p.costo_unitario_cosechado, reserva)
        else:
            aporte = min(dr.cantidad_cosechada, dr.cantidad_reservada) if dr.cantidad_cosechada is not None else dr.cantidad_reservada
            cosecha = reserva.cosecha
            fecha_cosecha = cosecha.fecha_cosecha if cosecha is not None and cosecha.fecha_cosecha else hoy
            limite = fecha_cosecha + timedelta(days=dr.lote.siembra.variedad.duracion_post_cosecha)
            costo = costos.get((reserva.cosecha_id, dr.lote_id), Decimal("0.0000"))
            origen = Origen(("l", dr.lote_id, reserva.cosecha_id or 0), "lote", dr.lote, None, fecha_cosecha, aporte, limite, costo, reserva)
        if aporte > 0:
            origenes_de[(reserva.pk)].append(origen)
    leidas = []
    for linea in lineas:
        reservas_de_linea = por_linea[linea.pk]
        origenes = [o for r in reservas_de_linea for o in origenes_de[r.pk]]
        detalle = linea.detalle_venta or linea.detalle_suministro
        leidas.append(LineaLeida(linea, detalle, detalle.variedad, sum(o.aporte for o in origenes), origenes, reservas_de_linea))
    reservados = {r.insumo_invernadero_id: r for r in ReservaInsumo.objects.filter(orden_id=entrega.pk, estado=ACTIVA).select_related("insumo_invernadero__insumo").order_by("pk")}
    ofrecidos = {
        i.pk: i for i in insumos_invernadero.habilitados(entrega.invernadero_id) if i.insumo.tipo_insumo.codigo == categorias.ENVASES and i.insumo.activo
    }
    es_ultima, previas, pendientes = True, {}, set()
    if venta is not None:
        es_ultima = not Entrega.objects.filter(contrato_entrega_id=venta.pk, estado_orden=A_REALIZAR).exclude(pk=entrega.pk).exists()
        detalle_ids = [l.detalle_venta_id for l in lineas]
        previas = dict(
            DetalleEntrega.objects.filter(detalle_venta_id__in=detalle_ids, entrega__estado_orden=OrdenTrabajo.Estado.CONCRETADA)
            .exclude(entrega_id=entrega.pk)
            .values("detalle_venta_id")
            .annotate(total=Sum("cant_entregada"))
            .values_list("detalle_venta_id", "total")
        )
        pendientes = set(
            DetalleEntrega.objects.filter(detalle_venta_id__in=detalle_ids, entrega__estado_orden=A_REALIZAR).exclude(entrega_id=entrega.pk).values_list("detalle_venta_id", flat=True)
        )
    return Lectura(entrega, contrato, venta, suministro, leidas, reservados, ofrecidos, es_ultima, previas, pendientes, hoy)


def _huella(lectura):
    """Lo que cuenta para detectar que la entrega cambió entre que se armó el resumen y se confirmó (`cambio_simultaneo`): su estado y transportista, por línea sus reservas no liberadas con sus
    orígenes y cantidades, y las reservas de insumo activas con su cantidad. En un retiro el envasado puede cambiar mientras se carga (`envasado.md`, «Retiro en concreción»)."""
    lineas = [
        [ll.linea.pk, ll.planificada, sorted([r.pk, r.estado_reserva] for r in ll.reservas), sorted([list(o.clave), o.aporte] for o in ll.origenes)] for ll in lectura.lineas
    ]
    envases = sorted([iin_id, str(r.cantidad_reservada)] for iin_id, r in lectura.reservados.items())
    return json.dumps([lectura.entrega.estado_orden, lectura.entrega.transportista_id, lineas, envases])


# ---- la evaluación (pasos 5 a 12): la misma para el resumen y para el registro ----


@dataclass
class ResumenDeConcrecion:
    """El resumen de la concreción (paso 12) con lo propuesto, los errores por campo (`errores[campo] = [(código, mensaje)]`: 5b, 10a, 10b y los de medio de pago), las advertencias (5a, 7a, 8a,
    8b, 9a, 10b y 14c), los montos y la huella. `lectura` se usa para registrar."""

    lectura: object
    lineas: list
    envases: list
    declarados: list
    errores: dict
    advertencias: list
    total: Decimal
    es_ultima: bool
    cobra: bool
    total_a_cobrar: Decimal
    todos_rechazados: bool
    estados_de_detalles: dict  # detalle de venta → ("confirmado"|"rechazado", cantidad) o `None` si no cambia
    vencimiento: object
    huella: str
    sin_envasado: bool
    con_exceso: bool
    hay_diferencias: bool

    @property
    def entrega(self):
        return self.lectura.entrega

    @property
    def es_venta(self):
        return self.lectura.venta is not None

    @property
    def hay_errores(self):
        return bool(self.errores)


def _evaluar(lectura, datos, hoy):
    """Pasos 5 a 12: valida lo que indicó la persona y calcula todo lo que se va a registrar. No escribe."""
    errores = defaultdict(list)
    advertencias = []
    resueltas = []
    es_venta = lectura.venta is not None
    por_detalle = defaultdict(int)
    for ll in lectura.lineas:
        linea, n = ll.linea, ll.planificada
        if n == 0:  # línea quitada (D-66, punto 4): no se pregunta nada
            resueltas.append(LineaResuelta(ll, 0, 0, 0, 0, linea.precio_unitario, Decimal("0.00"), False, [], False))
            continue
        llego = _entero(datos.llego.get(linea.pk), n, n)
        if llego is None:
            errores[f"llego_{linea.pk}"].append(("cantidad_invalida", f"Un número entero entre 0 y {n} (se planificaron {n})."))  # 5b
            llego = n
        perdida = n - llego
        if perdida:
            advertencias.append(f"{ll.variedad}: la diferencia de {perdida} se registrará como pérdida en el traslado (causa «daño en la entrega»).")  # 5a
        rechazada = False
        if es_venta:
            rechazada = not datos.acepta.get(linea.pk, True) or llego == 0
            entregada, devuelta = (0, llego) if rechazada else (llego, 0)
            if rechazada and llego > 0:
                advertencias.append(f"{ll.variedad}: el cliente rechaza lo que llegó. La línea no se cobra, lo que llegó vuelve a la cámara y el detalle quedará rechazado.")  # 7a
            precio = linea.precio_unitario
        else:
            recibio = _entero(datos.recibio.get(linea.pk), llego, llego)
            if recibio is None:
                errores[f"recibio_{linea.pk}"].append(("cantidad_invalida", f"Un número entero entre 0 y {llego} (llegaron {llego})."))
                recibio = llego
            entregada, devuelta = recibio, llego - recibio
            precio = calendario.precio_en(ll.detalle, hoy)  # 3a.2: el precio se recalcula con la fecha real (regla 7 de 8.11)
        bajo = False
        if not es_venta:
            minima = ll.detalle.clausula_suministrante.cantidad_minima
            if entregada < minima:
                bajo = True
                advertencias.append(f"{ll.variedad}: queda por debajo del mínimo pactado ({minima} plantas). Se registrará una discrepancia para que la evalúe el Gerente.")  # 14c
        repartos = repartir(ll.origenes, perdida, devuelta)
        resueltas.append(LineaResuelta(ll, llego, perdida, devuelta, entregada, precio, _redondear(entregada * precio), rechazada, repartos, bajo))
        if es_venta:
            por_detalle[linea.detalle_venta_id] += entregada
    total = sum((r.monto for r in resueltas), Decimal("0.00"))

    estados, cobra, todos_rechazados, total_a_cobrar = {}, False, False, Decimal("0.00")
    if es_venta:
        detalles_de_la_entrega = {ll.detalle.pk: ll.detalle for ll in lectura.lineas if ll.planificada > 0}  # una línea quitada no cuenta
        for detalle_id in detalles_de_la_entrega:
            aceptado = lectura.previas.get(detalle_id, 0) + por_detalle[detalle_id]
            if aceptado > 0:
                estados[detalle_id] = ("confirmado", aceptado)
            elif detalle_id not in lectura.pendientes_otras:
                estados[detalle_id] = ("rechazado", 0)
            else:
                estados[detalle_id] = None
        hay_confirmado = False
        for detalle in DetalleVenta.objects.filter(compra_venta_id=lectura.venta.pk):
            if detalle.pk in estados and estados[detalle.pk] is not None:
                estado, cantidad = estados[detalle.pk]
            else:
                estado, cantidad = detalle.estado_detalle_venta, detalle.cant_entregada_venta or 0
            if estado == DetalleVenta.Estado.CONFIRMADO:
                hay_confirmado = True
                total_a_cobrar += _redondear(cantidad * detalle.precio_unitario_de_venta)
        if lectura.es_ultima:
            cobra = hay_confirmado
            todos_rechazados = not hay_confirmado
            if cobra and datos.medio_pago not in MEDIOS:
                errores["medio_pago"].append(("medio_de_pago_obligatorio", "Elegí el medio de pago con que el cliente pagó el total."))
            if todos_rechazados:
                advertencias.append("Quedaron rechazados todos los detalles de la venta: la venta quedará cancelada, sin cobro.")  # 8b
        else:
            advertencias.append("En esta entrega no se cobra: el total de la venta se cobra en la última entrega.")  # 8a
    vencimiento = None if es_venta else hoy + timedelta(days=lectura.suministro.clausula_suministrado.plazo_pago_dias)

    envases, declarados, con_exceso = _evaluar_envases(lectura, datos, errores, advertencias)
    sin_envasado = not lectura.reservados
    hay_diferencias = any(r.perdida or r.devuelta or r.rechazada for r in resueltas) or any(r.bajo_el_minimo for r in resueltas)
    return ResumenDeConcrecion(
        lectura, resueltas, envases, declarados, dict(errores), advertencias, total, lectura.es_ultima, cobra, total_a_cobrar, todos_rechazados, estados, vencimiento,
        _huella(lectura), sin_envasado, con_exceso, hay_diferencias,
    )


def _evaluar_envases(lectura, datos, errores, advertencias):
    """Pasos 9 y 10 (y 9a, 10a y 10b): con envasado, por cada reserva la utilizada y la devuelta; sin envasado, los envases declarados o «no usé envases». Devuelve `(envases, declarados, con_exceso)`."""
    envases, declarados, con_exceso = [], [], False
    for iin_id, reserva in sorted(lectura.reservados.items()):
        iin = reserva.insumo_invernadero
        nombre = iin.insumo.nombre_insumo
        reservada = reserva.cantidad_reservada
        utilizada = _decimal(datos.utilizada.get(iin_id), reservada)
        if utilizada is None:
            errores[f"utilizada_{iin_id}"].append(("envase_invalido", f"{nombre}: la cantidad utilizada tiene que ser un número desde 0 (reservadas: {_texto_cantidad(reservada)})."))
            utilizada = reservada
        maximo = max(Decimal(0), reservada - utilizada)
        devuelta = _decimal(datos.devuelta.get(iin_id), maximo)
        if devuelta is None or devuelta > maximo:
            errores[f"devuelta_{iin_id}"].append(
                ("envase_invalido", f"{nombre}: la cantidad devuelta tiene que estar entre 0 y {_texto_cantidad(maximo)} (reservadas: {_texto_cantidad(reservada)}).")  # 10a
            )
            devuelta = maximo
        exceso = max(Decimal(0), utilizada - reservada)
        if exceso > 0:
            con_exceso = True
            advertencias.append(f"{nombre}: se usaron {_texto_cantidad(exceso)} más de lo reservado. El exceso se registra como consumo y se avisa al Agrónomo.")  # 10b
            if iin_id not in datos.confirmo_exceso:
                errores[f"utilizada_{iin_id}"].append(("envase_invalido", f"{nombre}: se usaron {_texto_cantidad(exceso)} más de lo reservado. Confirmá la cantidad utilizada."))
        envases.append(EnvaseResuelto(iin, reserva, reservada, utilizada, devuelta, exceso, max(reservada, utilizada) - devuelta))
    if not lectura.reservados:
        advertencias.append("La entrega no tiene envasado planificado. Declará los envases usados; se avisará al Agrónomo.")  # 9a
        for iin_id, texto in sorted(datos.declarado.items()):
            cantidad = _decimal(texto, Decimal(0))
            if iin_id not in lectura.ofrecidos:
                if cantidad is None or cantidad > 0:
                    errores["envases"].append(("envase_invalido", "Uno de los envases declarados no está habilitado en este invernadero."))
                continue
            if cantidad is None:
                errores[f"declarado_{iin_id}"].append(("envase_invalido", "La cantidad declarada tiene que ser un número desde 0."))
            elif cantidad > 0:
                declarados.append(EnvaseDeclarado(lectura.ofrecidos[iin_id], cantidad))
        if declarados and datos.sin_envases:
            errores["envases"].append(("envase_invalido", "No marques «No usé envases» si declaraste alguno."))
        if not declarados and not datos.sin_envases and "envases" not in errores:
            errores["envases"].append(("envase_invalido", "Declará los envases usados o marcá que no se usaron."))
    return envases, declarados, con_exceso


# ---- quién concreta y qué puede concretar ----


def _exigir_concretador(actor):
    """El Transportista (con envío) o el Vendedor (en un retiro), con la cuenta activa. Lee la cuenta de la base. El Gerente, el Agrónomo y el Capataz no concretan."""
    vigente = Usuario.objects.filter(pk=actor.pk).first() if actor is not None else None
    if vigente is None or not vigente.is_active or rol_de(vigente) not in (TRANSPORTISTA, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return vigente


def _entrega_para_concretar(actor, entrega_id):
    """La entrega con lo que necesita la pantalla. 404 si no existe; `PermissionDenied` si no es del alcance del actor: el Transportista solo concreta las suyas con envío, el Vendedor
    solo los retiros de sus contratos (D-28)."""
    actor = _exigir_concretador(actor)
    entrega = get_object_or_404(Entrega.objects.select_related("contrato_entrega__cliente", "invernadero", "transportista"), pk=entrega_id)
    if rol_de(actor) == TRANSPORTISTA:
        propia = entrega.transportista_id == actor.pk and entrega.modalidad_entrega == ENVIO
    else:
        propia = entrega.modalidad_entrega == RETIRO and entrega.contrato_entrega.vendedor_id == actor.pk
    if not propia:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return actor, entrega


def _rechazar(codigo, mensaje, campo="__all__", params=None):
    return ValidationError({campo: [ValidationError(mensaje, code=codigo, params=params)]})


def _exigir_concretable(entrega, actor, hoy):
    """Regla «Entrega concretable» y precondición b: «a realizar», con fecha programada de hoy o anterior; con envío, de este Transportista y con su ruta del día iniciada
    (`ruta_no_iniciada`); en un retiro, del Vendedor del contrato. Si no, `entrega_no_concretable` (14a)."""
    if entrega.estado_orden != A_REALIZAR or entrega.fecha_programada_orden > hoy:
        raise _rechazar("entrega_no_concretable", f"La entrega {entrega.codigo} ya no está a realizar o todavía no se puede concretar.")
    if rol_de(actor) == TRANSPORTISTA:
        if entrega.transportista_id != actor.pk or entrega.modalidad_entrega != ENVIO:
            raise _rechazar("entrega_no_concretable", f"La entrega {entrega.codigo} ya no es tuya.")
        vehiculo = Vehiculo.objects.filter(transportista_id=actor.pk).first()
        if vehiculo is None or not vehiculo.esta_en_ruta(hoy):
            raise _rechazar("ruta_no_iniciada", "Iniciá la ruta del día antes de concretar una entrega.")
    elif entrega.modalidad_entrega != RETIRO or entrega.contrato_entrega.vendedor_id != actor.pk:
        raise _rechazar("entrega_no_concretable", f"La entrega {entrega.codigo} no es un retiro de tus contratos.")


def entregas_concretables(actor, hoy=None):
    """COM-CNC-ENT, paso 2 (y 1a.2): las entregas «a realizar» con fecha programada de hoy o anterior que `actor` puede concretar: las del Transportista (con envío) o los retiros de los contratos del
    Vendedor, las demoradas primero. Cada `FilaConcretable` trae el cliente, el destino, el tipo de contrato, si está demorada y el contenido. Sin consultas por fila."""
    hoy = hoy or stock.hoy()
    actor = _exigir_concretador(actor)
    if rol_de(actor) == TRANSPORTISTA:
        consulta = Entrega.objects.filter(transportista_id=actor.pk, modalidad_entrega=ENVIO)
    else:
        consulta = Entrega.objects.filter(contrato_entrega__vendedor_id=actor.pk, modalidad_entrega=RETIRO)
    lista = list(
        consulta.filter(estado_orden=A_REALIZAR, fecha_programada_orden__lte=hoy)
        .select_related("contrato_entrega__cliente", "invernadero", "direccion_destino__localidad", "direccion_destino__direccionurbana", "direccion_destino__direccionrural")
        .order_by("fecha_programada_orden", "pk")
    )
    contenidos = rutas._contenidos([e.pk for e in lista])
    suministros = set(Suministro.objects.filter(pk__in=[e.contrato_entrega_id for e in lista]).values_list("pk", flat=True))
    return [
        FilaConcretable(
            e, e.codigo, e.contrato_entrega.cliente.nombre_visible, entregas._destino_de_la_fila(e), contenidos[e.pk], e.contrato_entrega_id in suministros,
            e.fecha_programada_orden < hoy, max(0, (hoy - e.fecha_programada_orden).days),
        )
        for e in lista
    ]


def resumen_de_concrecion(actor, entrega_id, datos=None, hoy=None):
    """Pasos 4 a 12 (solo lectura: no escribe ni bloquea). El resumen trae lo propuesto (lo planificado, la devuelta propuesta de cada envase), los errores por campo, las advertencias, los
    montos, si es la última entrega de la venta, el vencimiento (suministro) y la huella. Errores que lanza: `entrega_no_concretable` (14a) y `ruta_no_iniciada`; `PermissionDenied` y 404."""
    hoy = hoy or stock.hoy()
    actor, previa = _entrega_para_concretar(actor, entrega_id)
    _exigir_concretable(previa, actor, hoy)
    return _evaluar(_leer(previa, hoy), datos or DatosDeConcrecion(), hoy)


# ---- el registro (paso 14) ----


def _bloquear(previa, actor, lectura):
    """Toma los bloqueos del encabezado y devuelve la cuenta del actor bloqueada. `lectura` es la que se hizo sin bloquear (dice qué filas tomar)."""
    cuentas = {c for c in (actor.pk, previa.contrato_entrega.vendedor_id, previa.invernadero.agronomo_id) if c}
    por_id = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk")}
    quien = por_id.get(actor.pk)
    if quien is None or not quien.is_active or rol_de(quien) not in (TRANSPORTISTA, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    bloquear_invernadero_activo(previa.invernadero_id)
    return quien, _ids_a_bloquear(lectura)


def _ids_a_bloquear(lectura):
    """Los ids de las filas físicas que toca la concreción, ordenados."""
    origenes = [o for ll in lectura.lineas for o in ll.origenes]
    return {
        "variedades": sorted({ll.variedad.pk for ll in lectura.lineas}),
        "lotes": sorted({o.lote.pk for o in origenes}),
        "partidas": sorted({o.partida.pk for o in origenes if o.partida}),
        "reservas": sorted({r.pk for ll in lectura.lineas for r in ll.reservas}),
    }


def _bloquear_filas(previa, lectura, ids, envases_ids):
    """Del paso «variedades» en adelante, en el orden de `docs/patrones/bloqueos.md` («Concretar una entrega»)."""
    list(Variedad.objects.select_for_update(no_key=True).filter(pk__in=ids["variedades"]).order_by("pk"))  # sin exigir que estén activas: la concreción no puede fallar por eso
    list(Lote.objects.select_for_update(no_key=True).filter(pk__in=ids["lotes"]).order_by("pk"))
    list(StockCosechado.objects.select_for_update(no_key=True).filter(pk__in=ids["partidas"]).order_by("pk"))
    list(Contrato.objects.select_for_update(no_key=True, of=("self",)).filter(pk=lectura.contrato.pk))
    if lectura.venta is not None:
        list(DetalleVenta.objects.select_for_update(no_key=True).filter(compra_venta_id=lectura.venta.pk).order_by("pk"))
    else:
        list(DetalleSuministro.objects.select_for_update(no_key=True).filter(suministro_id=lectura.suministro.pk).order_by("pk"))
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=previa.pk))
    list(ReservaStock.objects.select_for_update(no_key=True).filter(pk__in=ids["reservas"]).order_by("pk"))
    list(DetalleReserva.objects.select_for_update(no_key=True).filter(reserva_id__in=ids["reservas"]).order_by("pk"))
    list(InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=envases_ids).order_by("pk"))
    list(LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero_id__in=envases_ids).order_by("insumo_invernadero_id", "pk"))
    list(ReservaInsumo.objects.select_for_update(no_key=True).filter(orden_id=previa.pk).order_by("pk"))


def concretar_entrega(actor, entrega_id, datos, huella):
    """COM-CNC-ENT, paso 14: concreta la entrega en UNA transacción, con los bloqueos del encabezado y un único registro de auditoría `concrecion_entrega`. Devuelve la `Entrega`.

    Después de bloquear vuelve a leer y verifica: 14a (`entrega_no_concretable`, `ruta_no_iniciada`), la huella (`cambio_simultaneo`: la pantalla vuelve al paso 4) y todos los datos (los
    mismos errores por campo del resumen: `cantidad_invalida`, `envase_invalido` y `medio_de_pago_obligatorio`). Registra, con el núcleo de `produccion` (sección 10 de `docs/api/produccion.md`):
    el egreso de cada partida, las mermas «daño en la entrega» por lote, las devoluciones a la cámara, los consumos de envases (el exceso incluido), y, en `comercial`, las reservas, las líneas,
    la entrega, los detalles, el pago y el estado de la venta, la discrepancia, el fin del detalle y del suministro. Sin asientos (D-57). Los correos salen después de confirmar."""
    actor, previa = _entrega_para_concretar(actor, entrega_id)
    datos = datos or DatosDeConcrecion()
    lectura_previa = _leer(previa, stock.hoy())
    ids = _ids_a_bloquear(lectura_previa)
    envases_ids = sorted(set(lectura_previa.reservados) | (set(datos.declarado) & set(lectura_previa.ofrecidos)))
    with transaction.atomic():
        quien, _ = _bloquear(previa, actor, lectura_previa)
        _bloquear_filas(previa, lectura_previa, ids, envases_ids)
        hoy = stock.hoy()
        entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor", "invernadero__agronomo", "transportista").get(pk=previa.pk)
        _exigir_concretable(entrega, quien, hoy)
        lectura = _leer(entrega, hoy)
        nuevos = _ids_a_bloquear(lectura)
        if any(not set(nuevos[k]) <= set(ids[k]) for k in nuevos) or not set(lectura.reservados) <= set(envases_ids):
            raise _rechazar("cambio_simultaneo", "La entrega cambió mientras cargabas los datos. Mirá cómo quedó y volvé a indicarlos.")
        if _huella(lectura) != huella:
            raise _rechazar("cambio_simultaneo", "La entrega cambió mientras cargabas los datos (se modificó el envasado, las reservas o el producto). Mirá cómo quedó y volvé a indicarlos.")
        resumen = _evaluar(lectura, datos, hoy)
        if resumen.hay_errores:
            raise ValidationError({campo: [ValidationError(mensaje, code=codigo) for codigo, mensaje in lista] for campo, lista in resumen.errores.items()})
        try:
            return _registrar(quien, entrega, lectura, resumen, datos, hoy)
        except ErrorDeProduccion as error:  # p. ej. una partida que ya no tiene lo que se iba a egresar: el producto cambió desde el resumen
            raise _rechazar("cambio_simultaneo", f"La entrega cambió mientras cargabas los datos: {error.mensaje}") from error


def _registrar(quien, entrega, lectura, resumen, datos, hoy):
    """Los pasos del 14, en este orden: cámara y mermas → reservas de stock → líneas y entrega → envases → compra-venta o suministro → avisos y correos → auditoría."""
    contrato = lectura.contrato
    es_venta = lectura.venta is not None
    movimientos, mermas_creadas, partidas_tocadas, partidas_nuevas = [], [], {}, []
    perdidas_por_lote = {}
    # 1 y 2: la cámara y las mermas por lote de origen (R144)
    for lr in resumen.lineas:
        for r in lr.repartos:
            o = r.origen
            lote = o.lote
            perdidas_por_lote.setdefault(lote.pk, [lote, 0])[1] += r.perdida
            if o.tipo == "partida":
                if o.aporte > 0:
                    movimientos.append(fisico.egresar_de_partida(o.partida, o.aporte, entrega))  # lo que salió en el vehículo
                if r.devuelta:
                    resultado = fisico.devolver_a_partida(o.partida, r.devuelta, entrega, hoy)
                    movimientos.append(resultado.movimiento)
                    if resultado.merma is not None:  # `ResultadoMermaDePartida(merma, movimiento)`
                        mermas_creadas.append(resultado.merma.merma)
                        movimientos.append(resultado.merma.movimiento)
                partidas_tocadas[o.partida.pk] = o.partida
            elif r.devuelta:
                nueva = fisico.crear_partida(
                    lote, r.devuelta, StockCosechado.Motivo.RECHAZO_EN_ENTREGA, fecha_cosecha=o.fecha_cosecha, fecha_ingreso=hoy, costo_unitario=o.costo, origen=entrega
                )
                if nueva.fecha_limite < hoy:  # regla «Lo devuelto a la cámara»: si la fecha límite ya pasó, la partida vence
                    resultado = fisico.vencer_partida(nueva, hoy)
                    if resultado is not None:
                        mermas_creadas.append(resultado.merma)
                        movimientos.append(resultado.movimiento)
                partidas_nuevas.append(nueva)
    for lote, cantidad in (perdidas_por_lote[k] for k in sorted(perdidas_por_lote)):
        if cantidad > 0:
            mermas_creadas.append(mermas.aplicar_merma_de_entrega(entrega, lote, cantidad, datos.descripcion_perdida[:LARGO_DE_LA_DESCRIPCION], quien))
    # 3: las reservas de stock (en una compra-venta, las de un detalle rechazado se liberan)
    entregadas, liberadas = [], []
    for ll in lectura.lineas:
        estado_detalle = resumen.estados_de_detalles.get(ll.detalle.pk) if es_venta else None
        rechazado = estado_detalle is not None and estado_detalle[0] == "rechazado"
        (liberadas if rechazado else entregadas).extend(ll.reservas)
    if entregadas:
        ReservaStock.objects.filter(pk__in=[r.pk for r in entregadas]).update(estado_reserva=ReservaStock.Estado.ENTREGADA)
    if liberadas:
        ReservaStock.objects.filter(pk__in=[r.pk for r in liberadas]).update(estado_reserva=ReservaStock.Estado.LIBERADA)
    # 4: las líneas y la entrega
    antes = {lr.leida.linea.pk: (lr.leida.planificada,) for lr in resumen.lineas}
    for lr in resumen.lineas:
        DetalleEntrega.objects.filter(pk=lr.leida.linea.pk).update(
            cant_entregada=lr.entregada, cant_perdida=lr.perdida, cant_devuelta=lr.devuelta, monto_pagar=lr.monto, precio_unitario=lr.precio
        )
    Entrega.objects.filter(pk=entrega.pk).update(
        estado_orden=OrdenTrabajo.Estado.CONCRETADA, fecha_resolucion_orden=hoy, monto_total_entrega=resumen.total, fecha_vencimiento_pago=resumen.vencimiento
    )
    # 5: los envases
    reservas_cerradas, consumos_creados, tocados, declarados_texto = [], [], set(), []
    for e in resumen.envases:
        reservas_cerradas.append(consumos.cerrar_reserva(e.reserva, min(e.utilizada, e.reservada), e.devuelta))
        tocados.add(e.existencia.pk)
        if e.consumo > 0:
            consumos_creados.append(consumos.registrar_consumo_de_orden(entrega, e.existencia, e.consumo, hoy, quien))
        declarados_texto.append(f"{e.existencia.insumo.nombre_insumo}: {_texto_cantidad(e.utilizada)} (reservadas {_texto_cantidad(e.reservada)})")
    for d in resumen.declarados:
        consumos_creados.append(consumos.registrar_consumo_de_orden(entrega, d.existencia, d.cantidad, hoy, quien))
        tocados.add(d.existencia.pk)
        declarados_texto.append(f"{d.existencia.insumo.nombre_insumo}: {_texto_cantidad(d.cantidad)} (declaradas, sin envasado planificado)")
    alertas_de_stock_creadas = []
    for iin_id in sorted(tocados):  # 14b: la alerta «stock inconsistente» la crea `inventario`; no se le avisa al actor
        alertas_de_stock_creadas.extend(alertas_de_stock.reevaluar_alertas_del_insumo(iin_id).creadas)
    # 6: la compra-venta o el suministro
    afectados_extra, pago, discrepancia, finalizados = [], None, None, []
    if es_venta:
        for detalle_id, estado in resumen.estados_de_detalles.items():
            if estado is not None:
                DetalleVenta.objects.filter(pk=detalle_id).update(estado_detalle_venta=estado[0], cant_entregada_venta=estado[1])
                afectados_extra.append(DetalleVenta.objects.get(pk=detalle_id))
        if resumen.cobra:
            pago = PagoCliente.objects.create(
                cliente=contrato.cliente, compra_venta=lectura.venta, medio_pago=datos.medio_pago, fecha_pago=hoy, monto_pagado=resumen.total_a_cobrar
            )
            CompraVenta.objects.filter(pk=lectura.venta.pk).update(estado_venta=CompraVenta.Estado.CONCRETADA, fecha_concrecion_venta=hoy)
        elif resumen.todos_rechazados:
            CompraVenta.objects.filter(pk=lectura.venta.pk).update(estado_venta=CompraVenta.Estado.CANCELADA)  # 8b: no es una cancelación de COM-CNL-CVT (sin los datos de MD-130)
        afectados_extra.append(CompraVenta.objects.get(pk=lectura.venta.pk))
    else:
        bajas = [(lr.leida.linea, lr.entregada, lr.leida.detalle.clausula_suministrante.cantidad_minima) for lr in resumen.lineas if lr.bajo_el_minimo]
        if bajas:
            discrepancia = crear_discrepancia(entrega, bajas)
        finalizados = _finalizar_detalles_y_suministro(entrega, lectura, resumen)
        afectados_extra.extend(finalizados)
    # 7: la cámara después (asignación automática y avisos de «partida por vencer» resueltos)
    avisos_resueltos = []
    for partida in {**partidas_tocadas, **{p.pk: p for p in partidas_nuevas}}.values():
        partida.refresh_from_db()
        if partida.estado_stock_cosechado in (StockCosechado.Estado.AGOTADO, StockCosechado.Estado.VENCIDO):
            resuelta = camara_comercial.resolver_aviso_de_partida(partida)
            if resuelta is not None:
                avisos_resueltos.append(resuelta)
    camara_comercial.programar_asignacion_de_camara(
        [p.pk for p in [*partidas_tocadas.values(), *partidas_nuevas] if p.estado_stock_cosechado == StockCosechado.Estado.DISPONIBLE]
    )
    # 8: los avisos y los correos
    _avisar(quien, entrega, lectura, resumen, discrepancia)
    _programar_comprobante(entrega, lectura, resumen)
    # 9: la auditoría (postcondiciones p y q)
    entrega.refresh_from_db()
    lineas = [lr.leida.linea for lr in resumen.lineas]
    cambios = {
        "estado_orden": {"antes": "a_realizar", "despues": "concretada"},
        "fecha_resolucion_orden": {"antes": None, "despues": f"{hoy:%d/%m/%Y}"},
        "monto_total_entrega": {"antes": None, "despues": f"{resumen.total:.2f}"},
        "cant_entregada": {"antes": [f"{lr.leida.variedad}: sin concretar" for lr in resumen.lineas], "despues": [f"{lr.leida.variedad}: {lr.entregada}" for lr in resumen.lineas]},
        "cant_perdida": {"antes": [f"{lr.leida.variedad}: sin concretar" for lr in resumen.lineas], "despues": [f"{lr.leida.variedad}: {lr.perdida}" for lr in resumen.lineas]},
        "cant_devuelta": {"antes": [f"{lr.leida.variedad}: sin concretar" for lr in resumen.lineas], "despues": [f"{lr.leida.variedad}: {lr.devuelta}" for lr in resumen.lineas]},
        "monto_pagar": {"antes": [f"{lr.leida.variedad}: sin concretar" for lr in resumen.lineas], "despues": [f"{lr.leida.variedad}: {lr.monto:.2f}" for lr in resumen.lineas]},
    }
    if resumen.vencimiento is not None:
        cambios["fecha_vencimiento_pago"] = {"antes": None, "despues": f"{resumen.vencimiento:%d/%m/%Y}"}
    datos_auditoria = {"entrega": referencia(entrega), "contrato": contrato.codigo}
    for clave, lista in (
        ("mermas_creadas", mermas_creadas),
        ("movimientos_creados", movimientos),
        ("partidas_creadas", partidas_nuevas),
        ("consumos_creados", [c.consumo for c in consumos_creados]),
        ("alertas_creadas", [*alertas_de_stock_creadas, *([discrepancia.alerta] if discrepancia and discrepancia.alerta else [])]),
        ("alertas_resueltas", avisos_resueltos),
    ):
        if lista:
            datos_auditoria[clave] = [str(x) for x in lista]
    if declarados_texto:
        datos_auditoria["envases_declarados"] = declarados_texto
    if pago is not None:
        datos_auditoria["pago"] = str(pago)
    if discrepancia is not None:
        datos_auditoria["discrepancia"] = str(discrepancia.discrepancia)
    RegistroAuditoria.objects.registrar(
        usuario=quien,
        accion=RegistroAuditoria.Accion.CONCRECION_ENTREGA,
        afectados=_sin_repetidos(
            [
                entrega, *lineas, *entregadas, *liberadas, *reservas_cerradas, *partidas_tocadas.values(), *partidas_nuevas, *afectados_extra,
                lectura.venta or lectura.suministro, *mermas_creadas, *([pago] if pago else []), *([discrepancia.discrepancia] if discrepancia else []),
            ]
        ),
        detalle={"cambios": cambios, "datos": datos_auditoria},
    )
    return entrega


def _sin_repetidos(objetos):
    """Los mismos objetos, sin repetir (por clase y clave), en el mismo orden: el registro de auditoría no admite el mismo afectado dos veces."""
    vistos, resultado = set(), []
    for objeto in objetos:
        clave = (type(objeto), objeto.pk)
        if clave not in vistos:
            vistos.add(clave)
            resultado.append(objeto)
    return resultado


def _finalizar_detalles_y_suministro(entrega, lectura, resumen):
    """Postcondición n (disparador «Cuando exista Entrega», punto 5): si con esta entrega quedaron concretadas todas las entregas del último período de un detalle, el detalle pasa a «finalizado»
    (con su `fecha_fin_detalle` si no la tenía) y, si todos los detalles del suministro lo están, el suministro también. **Con una rescisión acordada no se toca**: los cierra el paso 35 (decisión del
    estudiante del 25/11/2026: el contrato tiene que terminar «rescindido»). Devuelve los objetos que cambió."""
    suministro = lectura.suministro
    if suministro.estado_suministro != Suministro.Estado.VIGENTE or suministro.motivo_rescision is not None:
        return []
    cambiados = []
    for lr in resumen.lineas:
        linea, detalle = lr.leida.linea, lr.leida.detalle
        if detalle.estado_detalle_suministro != DetalleSuministro.Estado.VIGENTE:
            continue
        fechas = calendario.calendario(detalle)
        if not fechas or linea.fecha_periodo != fechas[-1]:
            continue
        faltan = DetalleEntrega.objects.filter(detalle_suministro_id=detalle.pk, fecha_periodo=fechas[-1], entrega__estado_orden=A_REALIZAR).exclude(entrega_id=entrega.pk).exists()
        if faltan:
            continue
        DetalleSuministro.objects.filter(pk=detalle.pk).update(estado_detalle_suministro=DetalleSuministro.Estado.FINALIZADO, fecha_fin_detalle=detalle.fecha_fin_detalle or fechas[-1])
        cambiados.append(DetalleSuministro.objects.get(pk=detalle.pk))
    if cambiados and not DetalleSuministro.objects.filter(suministro_id=suministro.pk).exclude(estado_detalle_suministro=DetalleSuministro.Estado.FINALIZADO).exists():
        Suministro.objects.filter(pk=suministro.pk).update(estado_suministro=Suministro.Estado.FINALIZADO)
        cambiados.append(Suministro.objects.get(pk=suministro.pk))
    return cambiados


def crear_discrepancia(entrega, lineas):
    """Extensión 14c y regla 12 de 8.13 (D-68, punto 5), dentro de la transacción de la concreción: una `DiscrepanciaEntrega` «pendiente» con una `LineaDiscrepancia` por cada línea que quedó por debajo de
    la cantidad mínima (`lineas` son tuplas `(DetalleEntrega, cantidad entregada, cantidad mínima)`; las dos cantidades se copian), y la alerta de evento `comercial_discrepancia_entrega` para el Gerente
    del invernadero de origen con su `AlertaComercial(solicitud=…)`. Devuelve `ResultadoDeDiscrepancia(discrepancia, lineas, alerta)`; el aviso al Vendedor lo da la concreción."""
    discrepancia = solicitudes.crear_solicitud(DiscrepanciaEntrega, entrega)
    creadas = [
        LineaDiscrepancia.objects.create(discrepancia=discrepancia, detalle_entrega=linea, cantidad_entregada=entregada, cantidad_minima_estipulada=minima)
        for linea, entregada, minima in lineas
    ]
    detalle = "; ".join(f"{e} plantas de {linea.detalle_suministro.variedad}, mínimo {m}" for linea, e, m in lineas)
    texto = f"{entrega.codigo} · {discrepancia.codigo}: {detalle}"
    alerta = alertas.crear_alerta_de_evento(entrega.invernadero_id, TIPO_DISCREPANCIA, texto if len(texto) <= LARGO_DE_LA_ALERTA else texto[: LARGO_DE_LA_ALERTA - 1] + "…")
    if alerta is not None:
        AlertaComercial.objects.create(alerta=alerta, solicitud=discrepancia)
    return ResultadoDeDiscrepancia(discrepancia, creadas, alerta)


def enlaces_de_alertas(usuario, alertas_de_discrepancias):
    """`registrar_enlace_de_alerta` para `comercial_discrepancia_entrega` (D-62; extensión 14c): solo el Gerente la recibe; lleva a la ficha del suministro de la entrega (no hay ficha de una entrega
    sola) hasta COM-07, que lo cambia por la pantalla de la solicitud. Una consulta para toda la lista."""
    alertas_de_discrepancias = list(alertas_de_discrepancias)
    if not alertas_de_discrepancias or rol_de(usuario) != GERENTE:
        return {}
    enlaces = {}
    for vinculo in AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_de_discrepancias], solicitud__isnull=False).select_related("solicitud__entrega"):
        s = vinculo.solicitud
        enlaces[vinculo.alerta_id] = Enlace(reverse("comercial:suministro", args=[s.entrega.contrato_entrega_id]), f"{s.entrega.codigo} · {s.codigo}")
    return enlaces


def intentos_fallidos(entrega_ids):
    """``{id de entrega: [intentos fallidos]}``, del más viejo al más nuevo. Para la ficha de la entrega, COM-ATN-ENR (COM-06b) y COM-RSV-QJA (COM-07). Una consulta."""
    por_entrega = defaultdict(list)
    for intento in IntentoFallido.objects.filter(entrega_id__in=list(entrega_ids)).order_by("fecha_hora", "pk"):
        por_entrega[intento.entrega_id].append(intento)
    return {i: por_entrega[i] for i in entrega_ids}


# ---- los avisos y los correos ----


def _avisar(quien, entrega, lectura, resumen, discrepancia):
    """Postcondición i y 14c.2: al Vendedor del contrato (si no es quien concreta), un aviso con las pérdidas, devoluciones, rechazos y la discrepancia; y al Agrónomo del invernadero de origen,
    si algún envase superó lo reservado o la entrega no tenía envasado planificado (10b.3, 9a.3). Dentro de la transacción (D-42)."""
    contrato = lectura.contrato
    partes = []
    for lr in resumen.lineas:
        piezas = []
        if lr.perdida:
            piezas.append(f"{lr.perdida} perdidas")
        if lr.devuelta:
            piezas.append(f"{lr.devuelta} devueltas")
        if lr.rechazada and lr.llego:
            piezas.append("rechazada por el cliente")
        if piezas:
            partes.append(f"{', '.join(piezas)} ({lr.leida.variedad})")
    vendedor = entregas._usuario_activo(contrato.vendedor_id)
    if vendedor is not None and vendedor.pk != quien.pk and (partes or discrepancia is not None):
        detalle = f"{entrega.codigo} · se concretó con diferencias: " + "; ".join(partes) + "."
        if discrepancia is not None:
            detalle += f" Discrepancia {discrepancia.discrepancia.codigo}: queda por debajo del mínimo pactado, la evalúa el Gerente."
        notificaciones.notificar(vendedor, entregas._acotar(f"Se concretó con diferencias: {entrega.codigo}", entregas.LARGO_DEL_TITULO), entregas._acotar(detalle, entregas.LARGO_DEL_DETALLE))
    agronomo = entregas._usuario_activo(entrega.invernadero.agronomo_id)
    if agronomo is None or agronomo.pk == quien.pk:
        return
    lineas = []
    for e in resumen.envases:
        if e.exceso > 0:
            lineas.append(f"se usaron {_texto_cantidad(e.utilizada)} {e.existencia.insumo.nombre_insumo}, reservadas {_texto_cantidad(e.reservada)} ({_texto_cantidad(e.exceso)} de más)")
    if resumen.sin_envasado:
        usados = ", ".join(f"{_texto_cantidad(d.cantidad)} {d.existencia.insumo.nombre_insumo}" for d in resumen.declarados) or "ningún envase"
        lineas.append(f"se concretó sin envasado planificado: declararon {usados}")
    if lineas:
        notificaciones.notificar(
            agronomo, entregas._acotar(f"Envases de {entrega.codigo}", entregas.LARGO_DEL_TITULO), entregas._acotar(f"{entrega.codigo} · " + "; ".join(lineas) + ".", entregas.LARGO_DEL_DETALLE)
        )


def _programar_comprobante(entrega, lectura, resumen):
    """Paso 15: el comprobante de venta (la última entrega con cobro) o el de entrega (un suministro) sale después de confirmar. Su resultado queda en `Entrega.estado_aviso_cliente` (D-66, punto 12):
    «pendiente de envío» o «sin correo». Una entrega que no manda comprobante deja el campo vacío (para que el paso 50 no reenvíe un correo viejo de la planificación). **Un suministro de un cliente con
    correo manda un solo correo: el comprobante con el enlace de confirmación** (postcondición l, COM-06b): `crear_enlace` lo crea dentro de la transacción y lo envía con `on_commit`; sin correo no hay enlace
    y la entrega queda «no confirmado» (regla «Sin confirmación tácita»)."""
    manda = lectura.venta is None or resumen.cobra
    if not manda:
        estado = None
    else:
        estado = AVISO.SIN_CORREO if not lectura.contrato.cliente.email_cliente else AVISO.PENDIENTE_ENVIO
    Entrega.objects.filter(pk=entrega.pk).update(estado_aviso_cliente=estado)
    if estado == AVISO.PENDIENTE_ENVIO:
        if lectura.venta is None:
            enlaces.crear_enlace(EnlaceCliente.Tipo.CONFIRMACION_ENTREGA, lectura.contrato.cliente, entrega=entrega)  # postcondición l; D-68 punto 1
        else:
            transaction.on_commit(partial(entregas._correr, enviar_comprobante_de_concrecion, entrega.pk))


def contexto_del_comprobante(entrega):
    """Lo que dicen los comprobantes de una entrega concretada (variación de datos 15a): por variedad, lo entregado, el precio y el monto; el total; en una compra-venta el medio de pago y el
    total cobrado; en un suministro el vencimiento del pago. De uso interno, sin validez fiscal. Lo usan el correo y la página para imprimir."""
    contrato = Contrato.objects.select_related("cliente").get(pk=entrega.contrato_entrega_id)
    venta = CompraVenta.objects.filter(pk=contrato.pk).first()
    lineas = [
        {"variedad": str(l.detalle_venta.variedad if l.detalle_venta_id else l.detalle_suministro.variedad), "cantidad": l.cant_entregada, "precio": l.precio_unitario, "monto": l.monto_pagar}
        for l in entrega.lineas.select_related("detalle_venta__variedad__cultivo", "detalle_suministro__variedad__cultivo").order_by("pk")
        if l.cant_entregada
    ]
    pago = PagoCliente.objects.filter(compra_venta_id=contrato.pk, estado_pago=PagoCliente.Estado.VIGENTE).first() if venta is not None else None
    return {
        "codigo": entrega.codigo,
        "contrato": contrato.codigo,
        "cliente": contrato.cliente.nombre_visible,
        "es_venta": venta is not None,
        "fecha": entrega.fecha_resolucion_orden,
        "lineas": lineas,
        "total": entrega.monto_total_entrega,
        "total_cobrado": pago.monto_pagado if pago else None,
        "medio_pago": pago.get_medio_pago_display() if pago else None,
        "vencimiento": entrega.fecha_vencimiento_pago,
        "vendedor": contrato.vendedor,
    }


def enviar_comprobante_de_concrecion(entrega_id):
    """El correo al cliente con el comprobante de venta (compra-venta) o de entrega (suministro **sin enlace**: solo las concretadas antes de COM-06b, que no lo reciben; las demás mandan el comprobante con el
    enlace, `enlaces.enviar_enlace`). Se llama SIEMPRE fuera de una transacción (D-14). Solo sale desde
    «pendiente de envío»: sin el correo del sistema configurado o si el envío falla, queda «pendiente» (lo reintenta el paso 50, 15a); si sale, «enviado». Devuelve `True` si salió."""
    entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor").filter(pk=entrega_id).first()
    if entrega is None or entrega.estado_orden != OrdenTrabajo.Estado.CONCRETADA or entrega.estado_aviso_cliente != AVISO.PENDIENTE_ENVIO:
        return False
    cliente = entrega.contrato_entrega.cliente
    if not cliente.email_cliente or not correo.correo_configurado():
        return False
    contexto = contexto_del_comprobante(entrega)
    plantilla = "comercial/correos/comprobante_de_venta.txt" if contexto["es_venta"] else "comercial/correos/comprobante_de_entrega.txt"
    asunto = f"Comprobante de tu compra {contexto['contrato']}" if contexto["es_venta"] else f"Comprobante de tu entrega {entrega.codigo}"
    salio = correo.enviar_correo(Destinatario(cliente.pk, cliente.email_cliente), asunto, plantilla, contexto)
    if salio:
        Entrega.objects.filter(pk=entrega.pk, estado_aviso_cliente=AVISO.PENDIENTE_ENVIO).update(estado_aviso_cliente=AVISO.ENVIADO)
    return salio
