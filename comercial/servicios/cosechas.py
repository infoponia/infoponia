# Cosechas (COM-04a): PROD-PNF-CSC (planificar), PROD-MOD-CSC (modificar), PROD-CNC-CSC (concretar) y la rama de cosechas de PROD-CNL-ORD (cancelar)
# (docs/casos_de_uso/produccion/cosecha.md y cancelar_orden.md, «Cómo se aplica en la ronda «Comercial 1»»). Aunque sus códigos empiezan con PROD, viven en
# `comercial` (D-59, regla A3 de D-37): crean o cambian reservas. Lo físico (bajar un lote, crear una partida, registrar un movimiento) lo escriben las
# funciones de núcleo de `produccion` (`produccion.servicios.cosechas`, `camara` y `mermas`; docs/api/produccion.md, sección 8): este archivo decide qué
# pasa con las reservas, los contratos y los avisos.
#
# Estructura de cada caso de uso: una lectura que NO escribe ni bloquea (`datos_de_…`, `verificar_…`, `resumen_de_…`) y la función que escribe. La
# que escribe repite TODA la verificación después de bloquear (extensiones 15b de PROD-PNF-CSC, 10a y 10b de PROD-MOD-CSC, 13b y 13c de PROD-CNC-CSC, 8a y
# 8b de PROD-CNL-ORD): lo que leyó sin bloquear solo dice qué filas bloquear.
#
# Bloqueos (`FOR NO KEY UPDATE`; docs/patrones/bloqueos.md, sección `comercial`, «Cosecha y cámara»; siempre este orden):
#   1. las cuentas que se leen o se avisan (en una consulta, por id) →
#   2. los invernaderos (el de la cosecha y los considerados del contrato, por id; `bloquear_invernadero_activo`) →
#   3. la variedad →
#   4. los sectores de los lotes (por id) →
#   5. los lotes y después las partidas candidatos (por id) →
#   6. el contrato y su detalle →
#   7. la cosecha (`OrdenTrabajo`: la fila que pone en fila a todas las operaciones sobre esa reserva) →
#   8. su reserva y sus líneas.
# El enlace del cliente (`EnlaceCliente`, D-65) iría siempre al final: lo suma COM-04c. Una cosecha que se concreta y otra operación sobre su reserva se
# ponen en fila en el paso 7.
#
# La asignación automática de cámara de las partidas que nacen (PROD-ASG-CAM, postcondición k) y de las líneas de cámara que se liberan (h) se programa con
# `camara_comercial.programar_asignacion_de_camara` (`transaction.on_commit`, D-64 punto 9; COM-04b). Fuera de esta tarea: el enlace y el correo del cliente en el camino
# de faltante (COM-04c), planificar la entrega (postcondición n: COM-05) y los asientos (D-57).

import json
from collections import namedtuple
from dataclasses import dataclass
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404

from comercial.models import CompraVenta, DetalleReserva, DetalleSuministro, DetalleVenta, ReservaStock, Suministro
from comercial.servicios import asientos_comerciales, calendario, entregas, faltantes, stock_maduro
from comercial.servicios import camara as camara_comercial  # PROD-ASG-CAM (COM-04b); `camara` es el núcleo físico de `produccion`
from comercial.servicios.stock_maduro import Periodo
from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import ciclos, stock
from inventario.servicios.variedades import bloquear_variedad
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.models import Cosecha, Lote, Merma, MovimientoStock, OcupacionSector, OrdenTrabajo, StockCosechado
from produccion.servicios import asientos_de_produccion, camara, mermas, ordenes, transiciones
from produccion.servicios import cosechas as fisico
from produccion.servicios import lotes as api_lotes

AGRONOMO, CAPATAZ = Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ
PRIORIDADES = ("alta", "media", "baja")
LARGO_DE_LA_DESCRIPCION = 500
LARGO_DEL_MOTIVO = 300
NO_CAMPO = "__all__"
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
Estado = OrdenTrabajo.Estado

# ---- tipos que devuelven las lecturas ----

InvernaderoParaCosechar = namedtuple("InvernaderoParaCosechar", "invernadero capataz motivo")  # motivo: None, "sin_capataz" o "sin_stock_maduro"
DetalleCubrible = namedtuple("DetalleCubrible", "clave tipo contrato cliente variedad variedad_id sin_cubrir fecha_entrega")
LoteCosechable = namedtuple("LoteCosechable", "lote_id codigo libre fecha_maxima dias_de_exceso")
VerificacionDeCosecha = namedtuple("VerificacionDeCosecha", "errores advertencias total_asignado sin_cubrir")
FilaDeCosecha = namedtuple("FilaDeCosecha", "cosecha_id codigo variedad invernadero fecha_programada prioridad cantidad_reservada origen contrato fecha_entrega")
LineaDeLote = namedtuple("LineaDeLote", "lote_id codigo reservada libre fecha_maxima")
FichaDeModificacion = namedtuple("FichaDeModificacion", "cosecha lineas lotes contrato fecha_entrega primera_fecha ultima_fecha huella")
VerificacionDeModificacion = namedtuple("VerificacionDeModificacion", "errores advertencias cambios total_asignado total_reservado")
SectorAConcretar = namedtuple("SectorAConcretar", "sector_id nombre ocupados propuesta")
LoteAConcretar = namedtuple("LoteAConcretar", "lote_id codigo reservada sectores")
FichaDeConcrecion = namedtuple("FichaDeConcrecion", "cosecha contrato fecha_entrega hoy lotes")
FilaDeLoteConcretado = namedtuple("FilaDeLoteConcretado", "lote_id codigo reservada cosechada excedente no_cosechadas perdidas quedan_libres")
ResumenDeConcrecion = namedtuple("ResumenDeConcrecion", "errores lotes total_reservado total_cosechado destino")
ResultadoConcrecion = namedtuple("ResultadoConcrecion", "cosecha reserva partidas mermas asignacion faltante")
Estimacion = namedtuple("Estimacion", "cubierto sin_cubrir origenes hace_falta_cosecha")
ResumenDeCancelacion = namedtuple("ResumenDeCancelacion", "cosecha reserva lineas contrato fecha_entrega cubierto ya_pendiente estimacion huella")
CancelacionDeCosecha = namedtuple("CancelacionDeCosecha", "cosecha reserva lineas cubierto asignacion sin_cubrir notificar_a enlaces", defaults=((),))
# El contrato que cubre una cosecha: `tipo` es "cv" o "sum"; `detalle` el `DetalleVenta` o el `DetalleSuministro`; `contrato` la compra-venta o el suministro;
# `fecha_entrega` la pactada o la del período; `periodo` el `Periodo` (solo en un suministro).
Contrato = namedtuple("Contrato", "tipo detalle contrato fecha_entrega periodo")
_Elegible = namedtuple("_Elegible", "lote libre maxima")  # un lote cosechable con lo que le queda libre y su fecha máxima de cosecha


@dataclass(frozen=True)
class DatosDeCosecha:
    """Lo que carga el Agrónomo al planificar (PROD-PNF-CSC). `clave_de_detalle` es `""` (sin contrato, 4a) o la de `clave_de_detalle(...)`; sin contrato,
    `variedad_id` es obligatoria. `lotes` es `((lote_id, cantidad), …)`."""

    invernadero_id: int
    clave_de_detalle: str = ""
    variedad_id: int | None = None
    fecha_programada: date | None = None
    prioridad: str = "media"
    descripcion: str = ""
    lotes: tuple = ()


@dataclass(frozen=True)
class DatosDeModificacion:
    """Lo que carga el Agrónomo al modificar (PROD-MOD-CSC). Los cuatro últimos campos son lo que la pantalla NO ofrece (5c): si llegan y difieren de lo
    guardado, `no_modificable`."""

    fecha_programada: date | None = None
    prioridad: str = "media"
    descripcion: str = ""
    lotes: tuple = ()
    variedad_id: int | None = None
    invernadero_id: int | None = None
    clave_de_detalle: str | None = None
    cantidad_total: int | None = None


@dataclass(frozen=True)
class DatosDeConcrecion:
    """Lo que carga el Capataz al concretar (PROD-CNC-CSC): `fecha_efectiva` (`None` = hoy), `cantidades` y `perdidas` como `((lote_id, sector_id,
    plantas), …)` (lo que no figura toma la propuesta y 0 perdidas) y `causas` como `((lote_id, causa, descripcion), …)`."""

    fecha_efectiva: date | None = None
    cantidades: tuple = ()
    perdidas: tuple = ()
    causas: tuple = ()


# ---- ayudas ----


def _rechazar(errores):
    """`ValidationError` con un error por campo y su código: `errores` es `{campo: [(codigo, mensaje)]}`."""
    raise ValidationError({campo: [ValidationError(mensaje, code=codigo) for codigo, mensaje in lista] for campo, lista in errores.items()})


def _error(campo, codigo, mensaje):
    """Un `ValidationError` de un solo campo."""
    _rechazar({campo: [(codigo, mensaje)]})


def _plantas(cantidad):
    """«1 planta» o «12 plantas»."""
    return f"{cantidad} {'planta' if cantidad == 1 else 'plantas'}"


def _dias(cantidad):
    """«1 día» o «4 días»."""
    return f"{cantidad} {'día' if cantidad == 1 else 'días'}"


def _acotar(texto, largo):
    """El texto sin pasar de `largo` caracteres (termina en «…» si se recorta)."""
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _fecha(valor):
    """«dd/mm/aaaa»."""
    return f"{valor:%d/%m/%Y}"


def _entero(valor):
    """True si `valor` es un entero (no booleano)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def _exigir_cuenta(actor, rol):
    """La cuenta es de `rol` y está activa (se lee de la base: pudo darse de baja mientras tanto); si no, `PermissionDenied`."""
    if actor is None or rol_de(actor) != rol or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _invernadero_del_agronomo(actor, invernadero_id):
    """El invernadero del Agrónomo `actor` (a su cargo), activo o no; `PermissionDenied` si no lo es y `Http404` si no existe. No bloquea."""
    _exigir_cuenta(actor, AGRONOMO)
    invernadero = Invernadero.objects.select_related("capataz", "agronomo", "vendedor").filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if invernadero.agronomo_id != actor.pk:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return invernadero


def _cosecha_del_agronomo(actor, cosecha_id):
    """La cosecha (con su invernadero) de un invernadero a cargo del Agrónomo `actor`. `PermissionDenied` si no, `Http404` si no existe. No bloquea."""
    _exigir_cuenta(actor, AGRONOMO)
    cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").filter(pk=cosecha_id).first()
    if cosecha is None:
        raise Http404("No existe esa cosecha.")
    if cosecha.invernadero.agronomo_id != actor.pk:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return cosecha


def _cosecha_del_capataz(actor, cosecha_id):
    """La cosecha cuyo Capataz asignado es `actor` (con la cuenta activa). `PermissionDenied` si no, `Http404` si no existe. No bloquea."""
    _exigir_cuenta(actor, CAPATAZ)
    cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").filter(pk=cosecha_id).first()
    if cosecha is None:
        raise Http404("No existe esa cosecha.")
    if cosecha.capataz_id != actor.pk:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return cosecha


def _exigir_a_realizar(cosecha, codigo="orden_no_a_realizar"):
    """La cosecha sigue «a realizar» (se relee de la base); si no, `ValidationError` con `codigo` y el estado actual (13b, 8a y 10a)."""
    estado = OrdenTrabajo.objects.filter(pk=cosecha.pk).values_list("estado_orden", flat=True).first()
    if estado != Estado.A_REALIZAR:
        _error(NO_CAMPO, codigo, f"La cosecha {cosecha.codigo} ya no está «a realizar»: su estado actual es «{Estado(estado).label}».")


# ---- el contrato de una cosecha ----


def clave_de_detalle(detalle_o_periodo):
    """La clave de lo que cubre una cosecha: «cv:<id del detalle>» o «sum:<id del detalle>:<aaaa-mm-dd>» (un período)."""
    if isinstance(detalle_o_periodo, Periodo):
        return f"sum:{detalle_o_periodo.detalle.pk}:{detalle_o_periodo.fecha.isoformat()}"
    return f"cv:{detalle_o_periodo.pk}"


def _contrato_de_clave(clave):
    """El `Contrato` de una clave, o `None` si no tiene la forma de `clave_de_detalle` o el detalle no existe."""
    try:
        partes = (clave or "").split(":")
        if partes[0] == "cv" and len(partes) == 2:
            detalle = DetalleVenta.objects.select_related("compra_venta__cliente", "variedad").filter(pk=int(partes[1])).first()
            return None if detalle is None else Contrato("cv", detalle, detalle.compra_venta, detalle.compra_venta.fecha_pactada_venta, None)
        if partes[0] == "sum" and len(partes) == 3:
            detalle = DetalleSuministro.objects.select_related("suministro__cliente", "variedad").filter(pk=int(partes[1])).first()
            fecha = date.fromisoformat(partes[2])
            return None if detalle is None else Contrato("sum", detalle, detalle.suministro, fecha, Periodo(detalle, fecha))
    except ValueError:
        return None
    return None


def _contrato_de_reserva(reserva):
    """El `Contrato` al que apunta la reserva, o `None` si no tiene detalle (cosecha sin contrato)."""
    if reserva.detalle_venta_id:
        detalle = DetalleVenta.objects.select_related("compra_venta__cliente", "variedad").get(pk=reserva.detalle_venta_id)
        return Contrato("cv", detalle, detalle.compra_venta, reserva.fecha_entrega_reserva, None)
    if reserva.detalle_suministro_id:
        detalle = DetalleSuministro.objects.select_related("suministro__cliente", "variedad").get(pk=reserva.detalle_suministro_id)
        return Contrato("sum", detalle, detalle.suministro, reserva.fecha_entrega_reserva, Periodo(detalle, reserva.fecha_entrega_reserva))
    return None


def _clave_de(contrato):
    """La clave de un `Contrato` (`""` sin contrato)."""
    if contrato is None:
        return ""
    return clave_de_detalle(contrato.periodo if contrato.tipo == "sum" else contrato.detalle)


def _sin_cubrir_de(contrato):
    """La cantidad sin cubrir del detalle (o del período) de un `Contrato` (regla 10 de 8.8)."""
    return stock_maduro.cantidad_sin_cubrir(contrato.periodo if contrato.tipo == "sum" else contrato.detalle)


def _parametro(contrato):
    """El parámetro de anticipación de `asignar`."""
    return "suministro" if contrato.tipo == "sum" else "compra_venta"


def _es_cubrible(contrato, invernadero, hoy, horizonte):
    """Regla «Detalle cubrible»: compra-venta, un detalle «abierto» de una venta «abierta» (con retiro, solo desde el invernadero de retiro; con envío,
    solo si el Vendedor del contrato es el del invernadero); suministro, un período de un detalle que se debe (D-64 punto 8) de un suministro «vigente»
    con el mismo Vendedor, dentro del horizonte de planificación y del calendario. En los dos, con cantidad sin cubrir mayor que cero."""
    if contrato is None:
        return False
    if contrato.tipo == "cv":
        venta = contrato.contrato
        if contrato.detalle.estado_detalle_venta != DetalleVenta.Estado.ABIERTO or venta.estado_venta != CompraVenta.Estado.ABIERTA:
            return False
        if venta.modalidad_entrega == CompraVenta.Modalidad.RETIRO:
            if venta.invernadero_retiro_id != invernadero.pk:
                return False
        elif invernadero.vendedor_id is None or venta.vendedor_id != invernadero.vendedor_id:
            return False
        return _sin_cubrir_de(contrato) > 0
    suministro, fecha = contrato.contrato, contrato.fecha_entrega
    if suministro.estado_suministro != Suministro.Estado.VIGENTE or invernadero.vendedor_id is None or suministro.vendedor_id != invernadero.vendedor_id:
        return False
    if not stock_maduro._se_debe(contrato.detalle, fecha) or not (hoy <= fecha <= hoy + timedelta(days=horizonte)):
        return False
    if not calendario.calendario(contrato.detalle, desde=fecha, hasta=fecha):
        return False
    return _sin_cubrir_de(contrato) > 0


# ---- los lotes cosechables ----


def _elegibles(invernadero_id, variedad_id=None, reserva_propia_id=None):
    """Los lotes activos del invernadero (y de la variedad, si se pide) que están en Maduración con plantas, por id, con lo que les queda libre y su
    fecha máxima de cosecha (regla 3 de 8.20). El stock libre es la cantidad actual menos lo reservado en reservas «activas» (regla «Stock libre»); con
    `reserva_propia_id`, esa reserva no cuenta: el stock libre SUMA lo que ya reserva la cosecha que se modifica o concreta. Una consulta por tabla."""
    consulta = Lote.objects.filter(
        invernadero_id=invernadero_id, estado_lote=Lote.Estado.ACTIVO, etapa__tipo_etapa__codigo=ciclos.MADURACION, cantidad_actual__gt=0
    )
    if variedad_id is not None:
        consulta = consulta.filter(siembra__variedad_id=variedad_id)
    lotes = list(consulta.select_related("siembra", "etapa").order_by("pk"))
    if not lotes:
        return []
    reservado = stock_maduro.reservado_de_lotes([l.pk for l in lotes], excluyendo_reservas=[reserva_propia_id] if reserva_propia_id else ())
    entradas = api_lotes.entradas_a_la_etapa(lotes, ciclos.etapas_de({l.siembra.variedad_id for l in lotes}))
    elegibles = []
    for lote in lotes:
        entrada = entradas.get(lote.pk)
        maxima = None if entrada is None else entrada + timedelta(days=lote.etapa.duracion_estimada_dias)
        elegibles.append(_Elegible(lote, max(0, lote.cantidad_actual - reservado.get(lote.pk, 0)), maxima))
    return elegibles


def lotes_cosechables(invernadero_id, variedad_id, fecha_programada):
    """Paso 9 y regla «Lote cosechable»: los lotes activos del invernadero y de la variedad, en Maduración y con stock libre mayor que cero, con ese
    stock y su fecha máxima de cosecha; `dias_de_exceso` es cuánto la supera `fecha_programada` (días corridos; 0 si no, 11c). Solo lectura."""
    filas = []
    for e in _elegibles(invernadero_id, variedad_id):
        if e.libre > 0:
            exceso = max(0, (fecha_programada - e.maxima).days) if e.maxima and fecha_programada else 0
            filas.append(LoteCosechable(e.lote.pk, e.lote.codigo, e.libre, e.maxima, exceso))
    return filas


# ---- PROD-PNF-CSC: lecturas (pasos 2 a 6) ----


def invernaderos_para_cosechar(actor):
    """Paso 2 (3a y 3b): los invernaderos activos a cargo del Agrónomo, cada uno con su Capataz y el motivo por el que no puede recibir una cosecha
    (`sin_capataz`: sin Capataz activo asignado; `sin_stock_maduro`: sin lotes cosechables con stock libre) o `None`. `PermissionDenied` para quien no
    es un Agrónomo activo (el Gerente no planifica)."""
    _exigir_cuenta(actor, AGRONOMO)
    filas = []
    for inv in Invernadero.objects.select_related("capataz").filter(agronomo_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO).order_by("nombre_invernadero", "pk"):
        if inv.capataz_id is None or not inv.capataz.is_active:
            motivo = "sin_capataz"
        elif not any(e.libre > 0 for e in _elegibles(inv.pk)):
            motivo = "sin_stock_maduro"
        else:
            motivo = None
        filas.append(InvernaderoParaCosechar(inv, inv.capataz if inv.capataz_id else None, motivo))
    return filas


def detalles_cubribles(actor, invernadero_id, busqueda=""):
    """Paso 4 y regla «Detalle cubrible»: los detalles de compra-venta y los períodos de suministro que se pueden cubrir desde ese invernadero, con su
    cantidad sin cubrir, ordenados por fecha de entrega (con la misma fecha, las compra-ventas antes que los períodos y después el código del contrato).
    `busqueda` filtra por cliente o variedad (5a). Solo lectura; una consulta para todos los períodos."""
    invernadero = _invernadero_del_agronomo(actor, invernadero_id)
    hoy, horizonte = stock.hoy(), configuracion.obtener().dias_horizonte_cosecha
    filas = []
    ventas = DetalleVenta.objects.filter(
        estado_detalle_venta=DetalleVenta.Estado.ABIERTO, compra_venta__estado_venta=CompraVenta.Estado.ABIERTA
    ).select_related("compra_venta__cliente", "variedad")
    for detalle in ventas.order_by("pk"):
        contrato = Contrato("cv", detalle, detalle.compra_venta, detalle.compra_venta.fecha_pactada_venta, None)
        if _es_cubrible(contrato, invernadero, hoy, horizonte):
            filas.append((contrato, _sin_cubrir_de(contrato)))
    detalles = list(
        DetalleSuministro.objects.filter(
            estado_detalle_suministro__in=[DetalleSuministro.Estado.VIGENTE, DetalleSuministro.Estado.FINALIZADO],
            suministro__estado_suministro=Suministro.Estado.VIGENTE,
            suministro__vendedor_id=invernadero.vendedor_id,
            fecha_primer_entrega__lte=hoy + timedelta(days=horizonte),
        )
        .select_related("suministro__cliente", "variedad")
        .order_by("pk")
    ) if invernadero.vendedor_id else []
    periodos = [Periodo(d, f) for d in detalles for f in calendario.calendario(d, desde=hoy, hasta=hoy + timedelta(days=horizonte))]
    sin_cubrir = stock_maduro.sin_cubrir_de_periodos(periodos)
    for p in periodos:
        if sin_cubrir[p] > 0:
            filas.append((Contrato("sum", p.detalle, p.detalle.suministro, p.fecha, p), sin_cubrir[p]))
    texto = (busqueda or "").strip().lower()
    resultado = []
    for contrato, pendiente in filas:
        cliente, variedad = str(contrato.contrato.cliente), str(contrato.detalle.variedad)
        if texto and texto not in cliente.lower() and texto not in variedad.lower():
            continue
        resultado.append(
            DetalleCubrible(
                _clave_de(contrato), "compra_venta" if contrato.tipo == "cv" else "suministro", contrato.contrato.codigo, cliente, variedad,
                contrato.detalle.variedad_id, pendiente, contrato.fecha_entrega,
            )
        )
    return sorted(resultado, key=lambda f: (f.fecha_entrega, f.tipo != "compra_venta", f.contrato))


def variedades_sin_contrato(actor, invernadero_id):
    """Extensión 4a: las variedades que tienen lotes activos en Maduración con stock libre en el invernadero, `[(variedad_id, nombre)]`."""
    invernadero = _invernadero_del_agronomo(actor, invernadero_id)
    vistas = {}
    for e in _elegibles(invernadero.pk):
        if e.libre > 0:
            vistas.setdefault(e.lote.siembra.variedad_id, str(e.lote.siembra.variedad))
    return sorted(vistas.items(), key=lambda par: par[1])


# ---- PROD-PNF-CSC: la verificación (pasos 6 a 14) ----

_Evaluacion = namedtuple("_Evaluacion", "errores advertencias total sin_cubrir invernadero contrato variedad_id lineas")


def _mensaje_de_retraso(contrato, fecha):
    """Extensión 8c y 6c: el aviso de que la entrega saldrá con retraso (con la posible queja o indemnización si es un suministro)."""
    texto = f"La cosecha del {_fecha(fecha)} es posterior a la fecha de entrega ({_fecha(contrato.fecha_entrega)}): la entrega saldrá con retraso."
    if contrato.tipo == "sum":
        texto += " Además, el retraso puede originar una queja o una indemnización según la cláusula del contrato."
    return texto


def _primera_fecha(contrato, variedad, hoy):
    """La primera fecha programada admitida: la entrega menos la duración postcosecha (nunca antes de hoy)."""
    return max(hoy, contrato.fecha_entrega - timedelta(days=variedad.duracion_post_cosecha))


def _verificar_fecha(errores, advertencias, fecha, contrato, variedad, hoy):
    """Pasos 7 y 8 de PROD-PNF-CSC y 6a a 6c de PROD-MOD-CSC: fecha pasada, producto que vence antes de la entrega (bloquea) y retraso (advierte)."""
    if fecha is None:
        errores.setdefault("fecha_programada", []).append(("fecha_obligatoria", "Ingresá la fecha programada de la cosecha."))
    elif fecha < hoy:
        errores.setdefault("fecha_programada", []).append(("fecha_pasada", "La fecha programada no puede ser anterior a hoy."))
    elif contrato is not None:
        primera = _primera_fecha(contrato, variedad, hoy)
        if fecha < primera:
            errores.setdefault("fecha_programada", []).append(
                (
                    "vence_antes_de_la_entrega",
                    f"El producto perdería su aptitud comercial antes de la entrega ({_fecha(contrato.fecha_entrega)}): la primera fecha programada admitida es {_fecha(primera)}.",
                )
            )
        elif fecha > contrato.fecha_entrega:
            advertencias.append(("retraso", _mensaje_de_retraso(contrato, fecha)))


def _advertir_fecha_maxima(advertencias, fecha, lotes):
    """Extensión 11c y 6d: cada lote cuya fecha máxima de cosecha es anterior a la fecha programada, con los días de exceso (no bloquea)."""
    for lote, maxima in lotes:
        if fecha is not None and maxima is not None and fecha > maxima:
            advertencias.append(
                (
                    "fecha_maxima",
                    f"El lote {lote.codigo} se cosecharía {_dias((fecha - maxima).days)} después de su fecha máxima de cosecha ({_fecha(maxima)}).",
                )
            )


def _verificar_datos_de_la_orden(errores, prioridad, descripcion):
    """La prioridad (alta, media o baja) y la descripción (hasta 500)."""
    if prioridad not in PRIORIDADES:
        errores.setdefault("prioridad", []).append(("prioridad_invalida", "La prioridad es alta, media o baja."))
    if len((descripcion or "").strip()) > LARGO_DE_LA_DESCRIPCION:
        errores.setdefault("descripcion", []).append(("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres."))


def _evaluar_planificacion(datos, hoy, horizonte):
    """Todas las verificaciones de PROD-PNF-CSC contra lo que hay en la base AHORA (la repite `planificar_cosecha` después de bloquear, 15b). Devuelve
    `_Evaluacion`. `Http404` si el invernadero no existe."""
    errores, advertencias = {}, []
    invernadero = Invernadero.objects.select_related("capataz", "agronomo", "vendedor").filter(pk=datos.invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if not invernadero.activo:
        errores.setdefault("invernadero", []).append(("invernadero_inactivo", "El invernadero está dado de baja: no admite cosechas nuevas."))
    elif invernadero.capataz_id is None or not invernadero.capataz.is_active:
        errores.setdefault("invernadero", []).append(("sin_capataz", "No hay un Capataz activo asignado a ese invernadero que pueda recibir la orden."))
    elif not any(e.libre > 0 for e in _elegibles(invernadero.pk)):
        errores.setdefault("invernadero", []).append(("sin_stock_maduro", "No hay stock maduro libre para cosechar en ese invernadero."))
    contrato, variedad_id, sin_cubrir = None, datos.variedad_id, None
    if datos.clave_de_detalle:
        contrato = _contrato_de_clave(datos.clave_de_detalle)
        if not _es_cubrible(contrato, invernadero, hoy, horizonte):
            errores.setdefault("detalle", []).append(("detalle_no_cubrible", "Ese detalle ya no se puede cubrir desde este invernadero."))
            contrato = None
        else:
            variedad_id, sin_cubrir = contrato.detalle.variedad_id, _sin_cubrir_de(contrato)
    elif variedad_id is None:
        errores.setdefault("variedad", []).append(("variedad_obligatoria", "Elegí la variedad de la cosecha."))
    elegibles = {e.lote.pk: e for e in _elegibles(invernadero.pk, variedad_id)} if variedad_id is not None else {}
    if contrato is not None and not any(e.libre > 0 for e in elegibles.values()):
        errores.setdefault("detalle", []).append(("sin_stock_maduro", "Ese detalle no puede cubrirse desde este invernadero: no tiene lotes maduros de su variedad con stock libre."))
    variedad = contrato.detalle.variedad if contrato is not None else None
    if variedad is None and variedad_id is not None:
        variedad = next((e.lote.siembra.variedad for e in elegibles.values()), None)
    if contrato is not None:
        _verificar_fecha(errores, advertencias, datos.fecha_programada, contrato, variedad, hoy)
    else:
        _verificar_fecha(errores, advertencias, datos.fecha_programada, None, None, hoy)
    _verificar_datos_de_la_orden(errores, datos.prioridad, datos.descripcion)
    total, vistos, lineas = 0, set(), []
    if not datos.lotes:
        errores.setdefault("lotes", []).append(("sin_lotes", "La orden debe incluir al menos un lote con al menos una planta."))
    for lote_id, cantidad in datos.lotes:
        campo = f"lote_{lote_id}"
        if not _entero(cantidad) or cantidad < 1:
            errores.setdefault(campo, []).append(("cantidad_invalida", "La cantidad a cosechar debe ser un número entero mayor que cero."))
            continue
        if lote_id in vistos:
            errores.setdefault(campo, []).append(("lote_repetido", "Ese lote ya está asignado: cambiá su cantidad en lugar de repetirlo."))
            continue
        vistos.add(lote_id)
        elegible = elegibles.get(lote_id)
        if elegible is None:
            errores.setdefault(campo, []).append(("lote_no_cosechable", "Ese lote no es cosechable: tiene que estar activo, en Maduración, del invernadero y de la variedad."))
            continue
        if cantidad > elegible.libre:
            errores.setdefault(campo, []).append(("supera_stock_libre", f"El lote {elegible.lote.codigo} tiene {_plantas(elegible.libre)} libres: no se pueden cosechar {cantidad}."))
            continue
        total += cantidad
        lineas.append((elegible, cantidad))
    if sin_cubrir is not None and total > sin_cubrir:
        errores.setdefault("lotes", []).append(("supera_sin_cubrir", f"El detalle tiene {_plantas(sin_cubrir)} sin cubrir: el total no puede pasar de esa cantidad."))
    _advertir_fecha_maxima(advertencias, datos.fecha_programada, [(e.lote, e.maxima) for e, _ in lineas])
    pendiente = None if sin_cubrir is None else max(0, sin_cubrir - total)
    if pendiente and total:
        advertencias.append(("queda_sin_cubrir", f"El detalle quedará con {_plantas(pendiente)} sin cubrir, que podrán cubrirse con otra cosecha."))
    return _Evaluacion(errores, advertencias, total, pendiente, invernadero, contrato, variedad_id, lineas)


def verificar_cosecha(actor, datos):
    """El recálculo de la pantalla y el resumen de PROD-PNF-CSC (pasos 3 a 13): `VerificacionDeCosecha(errores, advertencias, total_asignado,
    sin_cubrir)`. **No escribe ni bloquea.** `errores` es `{campo: [(codigo, mensaje)]}` y `advertencias`, `[(codigo, mensaje)]`."""
    _invernadero_del_agronomo(actor, datos.invernadero_id)
    evaluacion = _evaluar_planificacion(datos, stock.hoy(), configuracion.obtener().dias_horizonte_cosecha)
    return VerificacionDeCosecha(evaluacion.errores, evaluacion.advertencias, evaluacion.total, evaluacion.sin_cubrir)


# ---- los bloqueos ----


def _bloquear_cuentas(ids):
    """Nivel 1: las cuentas, en una consulta y por id."""
    list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={i for i in ids if i}).order_by("pk"))


def _bloquear_invernaderos(propio_id, contrato):
    """Nivel 2: el invernadero de la cosecha (que debe seguir activo) y los considerados del contrato (para `asignar`), por id."""
    ids = {propio_id}
    if contrato is not None:
        ids |= {i.pk for i in stock_maduro.invernaderos_considerados(contrato.contrato)}
    for pk in sorted(ids):
        if pk == propio_id:
            bloquear_invernadero_activo(pk)
        else:
            try:
                bloquear_invernadero_activo(pk)
            except ValidationError:
                continue  # se dio de baja mientras tanto: ya no es candidato
    return sorted(ids)


def _bloquear_sectores_y_lotes(variedad_id, invernadero_ids, lote_ids):
    """Niveles 4 y 5: los sectores de las ocupaciones de los lotes (por id), después los lotes y las partidas candidatos (por id)."""
    lote_ids = sorted(set(lote_ids))
    sector_ids = sorted(set(OcupacionSector.objects.filter(lote_id__in=lote_ids).values_list("sector_id", flat=True)))
    if sector_ids:
        list(SectorProduccion.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=sector_ids).order_by("pk"))
    stock_maduro.bloquear_candidatos([variedad_id], invernadero_ids)
    if lote_ids:
        list(Lote.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=lote_ids).order_by("pk"))


def _bloquear_contrato(contrato):
    """Nivel 6: el contrato y su detalle."""
    if contrato is None:
        return
    if contrato.tipo == "cv":
        list(CompraVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk=contrato.contrato.pk))
        list(DetalleVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk=contrato.detalle.pk))
    else:
        list(Suministro.objects.select_for_update(no_key=True, of=("self",)).filter(pk=contrato.contrato.pk))
        list(DetalleSuministro.objects.select_for_update(no_key=True, of=("self",)).filter(pk=contrato.detalle.pk))


def _bloquear_cosecha(cosecha_id):
    """Niveles 7 y 8: la fila de la cosecha (`OrdenTrabajo`), su reserva y sus líneas."""
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=cosecha_id))
    reservas = list(ReservaStock.objects.select_for_update(no_key=True).filter(cosecha_id=cosecha_id))
    list(DetalleReserva.objects.select_for_update(no_key=True).filter(reserva__in=reservas).order_by("pk"))


def _lineas_de(reserva):
    """Las líneas de la reserva con su lote o su partida, por id."""
    return list(DetalleReserva.objects.filter(reserva=reserva).select_related("lote__siembra", "lote__etapa", "partida").order_by("pk"))


# ---- PROD-PNF-CSC: planificar (paso 15) ----


def _duplicada(actor, datos, hoy):
    """Extensión 15a: otra cosecha «a realizar» con los mismos valores en todos sus atributos (sin el identificador, con la fecha de creación de hoy) y las
    mismas líneas; devuelve la existente o `None`."""
    contrato = _contrato_de_clave(datos.clave_de_detalle) if datos.clave_de_detalle else None
    propias = sorted((lote_id, cantidad) for lote_id, cantidad in datos.lotes)
    variedad_id = contrato.detalle.variedad_id if contrato is not None else datos.variedad_id
    candidatas = Cosecha.objects.filter(
        estado_orden=Estado.A_REALIZAR,
        invernadero_id=datos.invernadero_id,
        variedad_id=variedad_id,
        fecha_programada_orden=datos.fecha_programada,
        prioridad_orden=datos.prioridad,
        descripcion_orden=(datos.descripcion or "").strip(),
        agronomo_id=actor.pk,
        fecha_creacion_orden=hoy,
    ).order_by("pk")
    for otra in candidatas:
        reserva = ReservaStock.objects.filter(cosecha=otra).first()
        if reserva is None:
            continue
        mismo_contrato = (reserva.detalle_venta_id, reserva.detalle_suministro_id, reserva.fecha_entrega_reserva) == (
            (contrato.detalle.pk, None, contrato.fecha_entrega) if contrato is not None and contrato.tipo == "cv"
            else (None, contrato.detalle.pk, contrato.fecha_entrega) if contrato is not None
            else (None, None, None)
        )
        existentes = sorted(DetalleReserva.objects.filter(reserva=reserva, lote__isnull=False).values_list("lote_id", "cantidad_reservada"))
        if mismo_contrato and existentes == propias:
            return otra
    return None


def planificar_cosecha(actor, datos):
    """PROD-PNF-CSC: planifica una cosecha manual y la devuelve (pasos 14 a 17).

    - Precondiciones a y b: Agrónomo activo con el invernadero a su cargo (`PermissionDenied`). El Gerente no planifica.
    - Extensiones 3a, 3b, 6a, 8a, 8b, 11a, 11b, 12b, 15a y 15b: `ValidationError` por campo con su código (ver `verificar_cosecha`), repetidas DESPUÉS de
      bloquear (cuentas → invernadero → variedad → sectores → lotes y partidas → contrato y detalle): si algo cambió desde que se verificó, no se
      registra nada.
    - Postcondiciones a a f: la `Cosecha` «a realizar» (`origen_cosecha = manual`, el Agrónomo, el Capataz del invernadero y el número de la secuencia),
      su `ReservaStock` «activa» (con contrato, el detalle y la fecha de entrega; sin contrato, ninguno de los dos, D-64 punto 6) y una línea por lote.
    - Postcondiciones g y h (D-42, dentro de la transacción): al Capataz «Nueva cosecha OT-…» y, con contrato, al Vendedor «Cosecha planificada para …».
    - Postcondiciones i y j y D-36: UN registro `planificacion_cosecha`.
    """
    invernadero = _invernadero_del_agronomo(actor, datos.invernadero_id)
    hoy, horizonte = stock.hoy(), configuracion.obtener().dias_horizonte_cosecha
    previo = _evaluar_planificacion(datos, hoy, horizonte)
    variedad_id = previo.variedad_id
    if variedad_id is None:  # sin variedad no hay qué bloquear: el error por campo ya está en la evaluación
        _rechazar(previo.errores)
    with transaction.atomic():
        _bloquear_cuentas({actor.pk, invernadero.capataz_id, previo.contrato.contrato.vendedor_id if previo.contrato else None})
        ids = _bloquear_invernaderos(invernadero.pk, previo.contrato)
        bloquear_variedad(variedad_id)
        _bloquear_sectores_y_lotes(variedad_id, ids, [lote_id for lote_id, _ in datos.lotes if _entero(lote_id)])
        _bloquear_contrato(previo.contrato)
        existente = _duplicada(actor, datos, hoy)  # 15a: antes que lo demás (una repetida también supera lo sin cubrir)
        if existente is not None:
            _error(NO_CAMPO, "cosecha_duplicada", f"Ya existe una cosecha igual a esta: {existente.codigo}. Corregí algún dato o cancelá.")
        evaluacion = _evaluar_planificacion(datos, hoy, horizonte)  # 15b: todo de nuevo, con lo bloqueado
        if evaluacion.errores:
            _rechazar(evaluacion.errores)
        invernadero, contrato = evaluacion.invernadero, evaluacion.contrato
        cosecha = Cosecha.objects.create(
            tipo_orden=OrdenTrabajo.Tipo.COSECHA,
            numero=ordenes.siguiente_numero(),
            fecha_creacion_orden=hoy,
            fecha_programada_orden=datos.fecha_programada,
            prioridad_orden=datos.prioridad,
            descripcion_orden=(datos.descripcion or "").strip(),
            agronomo_id=actor.pk,
            invernadero=invernadero,
            capataz_id=invernadero.capataz_id,
            variedad_id=variedad_id,
            origen_cosecha=Cosecha.OrigenCosecha.MANUAL,
        )
        reserva = ReservaStock.objects.create(
            detalle_venta=contrato.detalle if contrato is not None and contrato.tipo == "cv" else None,
            detalle_suministro=contrato.detalle if contrato is not None and contrato.tipo == "sum" else None,
            invernadero=invernadero,
            fecha_reserva=hoy,
            fecha_entrega_reserva=contrato.fecha_entrega if contrato is not None else None,
            estado_reserva=ReservaStock.Estado.ACTIVA,
            cosecha=cosecha,
        )
        lineas = [DetalleReserva.objects.create(reserva=reserva, lote=e.lote, cantidad_reservada=cantidad) for e, cantidad in evaluacion.lineas]
        variedad = str(evaluacion.lineas[0][0].lote.siembra.variedad)
        quien = actor.get_full_name() or actor.email
        notificaciones.notificar(
            invernadero.capataz,
            f"Nueva cosecha {cosecha.codigo}",
            _acotar(f"{variedad}: {_plantas(evaluacion.total)} para el {_fecha(cosecha.fecha_programada_orden)} en {invernadero.nombre_invernadero}. Planificó {quien}.", 500),
        )
        if contrato is not None:
            vendedor = Usuario.objects.filter(pk=contrato.contrato.vendedor_id, is_active=True).first()
            if vendedor is not None:
                notificaciones.notificar(
                    vendedor,
                    f"Cosecha planificada para {contrato.contrato.codigo}",
                    _acotar(
                        f"{_plantas(evaluacion.total)} de {variedad} para el {_fecha(cosecha.fecha_programada_orden)}. "
                        f"El detalle queda con {_plantas(evaluacion.sin_cubrir)} sin cubrir.",
                        500,
                    ),
                )
        datos_de_auditoria = {
            "invernadero": referencia(invernadero),
            "variedad": variedad,
            "fecha_programada": _fecha(cosecha.fecha_programada_orden),
            "origen_cosecha": cosecha.origen_cosecha,
            "lotes": [f"{l.lote.codigo}: {l.cantidad_reservada}" for l in lineas],
        }
        afectados = [cosecha, reserva, *lineas]
        if contrato is not None:
            datos_de_auditoria["contrato"] = referencia(contrato.detalle)
            afectados.append(contrato.detalle)
        RegistroAuditoria.objects.registrar(usuario=actor, accion=RegistroAuditoria.Accion.PLANIFICACION_COSECHA, afectados=afectados, detalle={"datos": datos_de_auditoria})
    return cosecha


# ---- PROD-MOD-CSC: modificar ----


def _lineas_de_lote(reserva):
    """Las líneas de lote de la reserva, por id."""
    return [l for l in _lineas_de(reserva) if l.lote_id]


def huella_de(cosecha):
    """Un texto estable con el estado, la fecha programada, la prioridad, la descripción y las líneas (lote y cantidad) de la cosecha: cambia si cambia
    cualquiera de esos datos. Se lee al abrir la cosecha y se compara al registrar (10a: la cosecha cambió mientras se editaba). Lee de la base."""
    datos = Cosecha.objects.filter(pk=cosecha.pk).values_list("estado_orden", "fecha_programada_orden", "prioridad_orden", "descripcion_orden").get()
    reserva = ReservaStock.objects.filter(cosecha_id=cosecha.pk).first()
    lineas = [] if reserva is None else sorted(DetalleReserva.objects.filter(reserva=reserva, lote__isnull=False).values_list("lote_id", "cantidad_reservada"))
    return json.dumps([list(datos), lineas], default=str)


def cosechas_modificables(actor):
    """Paso 2 de PROD-MOD-CSC: las cosechas «a realizar» de los invernaderos del Agrónomo, de cualquier origen, por fecha programada, con su contrato y
    fecha de entrega. Solo lectura; dos consultas para los contratos y las líneas (sin consultas por cosecha)."""
    _exigir_cuenta(actor, AGRONOMO)
    lista = list(
        Cosecha.objects.filter(estado_orden=Estado.A_REALIZAR, invernadero__in=Invernadero.objects.en_alcance_de(actor))
        .select_related("invernadero", "variedad")
        .order_by("fecha_programada_orden", "pk")
    )
    detalle = stock_maduro.detalle_de_cosechas([c.pk for c in lista])
    filas = []
    for c in lista:
        d = detalle[c.pk]
        filas.append(
            FilaDeCosecha(
                c.pk, c.codigo, str(c.variedad), c.invernadero.nombre_invernadero, c.fecha_programada_orden, c.prioridad_orden,
                sum(reservada for _, reservada, _ in d.lotes), Cosecha.OrigenCosecha(c.origen_cosecha).label, d.contrato, d.fecha_entrega,
            )
        )
    return filas


def datos_de_modificacion(actor, cosecha_id):
    """Pasos 3 y 4 (y 2a): la cosecha con sus líneas (cantidad reservada, stock libre —que incluye lo que ya reserva esta cosecha— y fecha máxima de
    cada lote), los lotes cosechables, el contrato y, con contrato, la fecha de entrega y la primera y la última fecha programada admitidas. Trae la
    huella para el paso 10. Solo lectura."""
    cosecha = _cosecha_del_agronomo(actor, cosecha_id)
    _exigir_a_realizar(cosecha, "cosecha_resuelta")
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    contrato = _contrato_de_reserva(reserva)
    elegibles = {e.lote.pk: e for e in _elegibles(cosecha.invernadero_id, cosecha.variedad_id, reserva.pk)}
    lineas = [
        LineaDeLote(l.lote_id, l.lote.codigo, l.cantidad_reservada, elegibles[l.lote_id].libre if l.lote_id in elegibles else 0, elegibles[l.lote_id].maxima if l.lote_id in elegibles else None)
        for l in _lineas_de_lote(reserva)
    ]
    lotes = [
        LoteCosechable(e.lote.pk, e.lote.codigo, e.libre, e.maxima, 0) for e in elegibles.values() if e.libre > 0
    ]
    primera = ultima = None
    if contrato is not None:
        primera, ultima = _primera_fecha(contrato, cosecha.variedad, stock.hoy()), contrato.fecha_entrega
    return FichaDeModificacion(cosecha, lineas, lotes, contrato.contrato.codigo if contrato else None, contrato.fecha_entrega if contrato else None, primera, ultima, huella_de(cosecha))


def _evaluar_modificacion(cosecha, reserva, contrato, datos, hoy):
    """Todas las verificaciones de PROD-MOD-CSC (extensiones 5a a 7a y 10b) contra lo que hay en la base AHORA. Devuelve `VerificacionDeModificacion`."""
    errores, advertencias, cambios = {}, [], []
    lineas = _lineas_de_lote(reserva)
    total_reservado = sum(l.cantidad_reservada for l in lineas)
    # 5c: lo que la pantalla no ofrece.
    no_se_cambia = (
        ("variedad_id", datos.variedad_id, cosecha.variedad_id, "la variedad"),
        ("invernadero_id", datos.invernadero_id, cosecha.invernadero_id, "el invernadero"),
        ("clave_de_detalle", datos.clave_de_detalle, _clave_de(contrato), "el contrato"),
        ("cantidad_total", datos.cantidad_total, total_reservado, "la cantidad total"),
    )
    for campo, enviado, guardado, que in no_se_cambia:
        if enviado is not None and enviado != guardado:
            errores.setdefault(campo, []).append(("no_modificable", f"No se puede cambiar {que}: cancelá la orden y planificá otra (PROD-CNL-ORD)."))
    _verificar_fecha(errores, advertencias, datos.fecha_programada, contrato, cosecha.variedad, hoy)
    _verificar_datos_de_la_orden(errores, datos.prioridad, datos.descripcion)
    elegibles = {e.lote.pk: e for e in _elegibles(cosecha.invernadero_id, cosecha.variedad_id, reserva.pk)}
    total, vistos, nuevas = 0, set(), []
    if not datos.lotes:
        errores.setdefault("lotes", []).append(("sin_lotes", "La orden debe incluir al menos un lote con al menos una planta."))
    for lote_id, cantidad in datos.lotes:
        campo = f"lote_{lote_id}"
        if not _entero(cantidad) or cantidad < 1:
            errores.setdefault(campo, []).append(("cantidad_invalida", "La cantidad debe ser un número entero mayor que cero."))
            continue
        if lote_id in vistos:
            errores.setdefault(campo, []).append(("lote_repetido", "Ese lote ya está asignado."))
            continue
        vistos.add(lote_id)
        total += cantidad
        elegible = elegibles.get(lote_id)
        if elegible is None:
            errores.setdefault(campo, []).append(("lote_no_cosechable", "Ese lote no es cosechable: tiene que estar activo, en Maduración, del invernadero y de la variedad."))
        elif cantidad > elegible.libre:
            errores.setdefault(campo, []).append(
                ("supera_stock_libre", f"El lote {elegible.lote.codigo} admite como máximo {_plantas(elegible.libre)} (su stock libre más lo que ya reserva esta cosecha).")
            )
        else:
            nuevas.append((elegible, cantidad))
    if datos.lotes and total != total_reservado:
        errores.setdefault("lotes", []).append(
            ("total_distinto", f"El total asignado ({total}) no coincide con el reservado ({total_reservado}): hasta que coincidan no se puede terminar.")
        )
    if sum(e.libre for e in elegibles.values()) < total_reservado:
        advertencias.append(
            ("lotes_no_alcanzan", "Los lotes de la variedad ya no alcanzan para cubrir lo reservado: para reducir la cantidad hay que cancelar la orden (PROD-CNL-ORD); lo que quede sin cubrir se cubre con una cosecha nueva.")
        )
    _advertir_fecha_maxima(advertencias, datos.fecha_programada, [(e.lote, e.maxima) for e, _ in nuevas])
    if datos.fecha_programada != cosecha.fecha_programada_orden:
        cambios.append(("fecha_programada", _fecha(cosecha.fecha_programada_orden), _fecha(datos.fecha_programada) if datos.fecha_programada else ""))
    if datos.prioridad != cosecha.prioridad_orden:
        cambios.append(("prioridad", cosecha.prioridad_orden, datos.prioridad))
    if (datos.descripcion or "").strip() != cosecha.descripcion_orden:
        cambios.append(("descripcion", cosecha.descripcion_orden, (datos.descripcion or "").strip()))
    antes = sorted((l.lote_id, l.cantidad_reservada) for l in lineas)
    despues = sorted((lote_id, cantidad) for lote_id, cantidad in datos.lotes if _entero(lote_id) and _entero(cantidad))
    if antes != despues:
        por_codigo = {l.lote_id: l.lote.codigo for l in lineas} | {e.lote.pk: e.lote.codigo for e in elegibles.values()}
        texto = lambda pares: ", ".join(f"{por_codigo.get(i, f'L-{i}')}: {n}" for i, n in pares)  # noqa: E731
        cambios.append(("lotes", texto(antes), texto(despues)))
    if not cambios and not errores:
        errores.setdefault(NO_CAMPO, []).append(("sin_cambios", "No indicaste ningún cambio."))
    return VerificacionDeModificacion(errores, advertencias, cambios, total, total_reservado)


def verificar_modificacion(actor, cosecha_id, datos):
    """Pasos 6 y 8: cómo queda la cosecha y cada cambio con su valor anterior y el nuevo (`cambios = [(campo, antes, despues)]`). **No escribe ni bloquea.**"""
    cosecha = _cosecha_del_agronomo(actor, cosecha_id)
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    return _evaluar_modificacion(cosecha, reserva, _contrato_de_reserva(reserva), datos, stock.hoy())


def modificar_cosecha(actor, cosecha_id, datos, huella):
    """PROD-MOD-CSC: modifica la fecha, la prioridad, la descripción y el reparto entre lotes de una cosecha «a realizar» y la devuelve (pasos 9 a 12).

    - Precondición a: el Agrónomo a cargo del invernadero (`PermissionDenied`). Extensiones 5c, 6a a 6c, 7a, 5b.4a, 5b.4b: `ValidationError` por campo
      (`no_modificable`, `fecha_pasada`, `vence_antes_de_la_entrega`, `sin_cambios`, `total_distinto`, `supera_stock_libre`).
    - Paso 10, en UNA transacción con los bloqueos del encabezado (con la fila de la cosecha antes que su reserva): se relee, y si la cosecha ya no está «a
      realizar», `cosecha_resuelta` (10a); si su `huella` cambió, `cosecha_cambio`; si un lote ya no tiene stock libre, `supera_stock_libre` (10b).
    - Postcondiciones a a c: las líneas de los lotes quitados se BORRAN (una línea de una reserva «activa» no tiene historia: queda en la auditoría), se
      cambian las de los lotes que siguen y se crean las de los agregados; el total reservado y la fecha de entrega de la reserva no cambian.
    - Postcondiciones d y e: aviso al Capataz «Cosecha OT-… modificada» y, si la fecha nueva atrasa la entrega, al Vendedor «Cosecha de … con retraso».
    - Postcondición f y D-36: UN registro `modificacion_cosecha` con cada cambio (valor anterior y nuevo).
    """
    cosecha = _cosecha_del_agronomo(actor, cosecha_id)
    hoy = stock.hoy()
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    previo = _contrato_de_reserva(reserva)
    lote_ids = {l.lote_id for l in _lineas_de_lote(reserva)} | {i for i, _ in datos.lotes if _entero(i)}
    with transaction.atomic():
        _bloquear_cuentas({actor.pk, cosecha.capataz_id, previo.contrato.vendedor_id if previo else None})
        ids = _bloquear_invernaderos(cosecha.invernadero_id, None)
        bloquear_variedad(cosecha.variedad_id)
        _bloquear_sectores_y_lotes(cosecha.variedad_id, ids, lote_ids)
        _bloquear_contrato(previo)
        _bloquear_cosecha(cosecha.pk)
        cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").get(pk=cosecha_id)
        _exigir_a_realizar(cosecha, "cosecha_resuelta")  # 10a
        if huella_de(cosecha) != huella:
            _error(NO_CAMPO, "cosecha_cambio", "Mientras modificabas, la cosecha cambió. Volvé a abrirla para ver cómo quedó.")
        reserva = ReservaStock.objects.get(cosecha=cosecha)
        verificacion = _evaluar_modificacion(cosecha, reserva, _contrato_de_reserva(reserva), datos, hoy)
        if verificacion.errores:
            _rechazar(verificacion.errores)
        contrato = _contrato_de_reserva(reserva)
        actuales = {l.lote_id: l for l in _lineas_de_lote(reserva)}
        nuevas = dict(datos.lotes)
        borradas = [f"{l.lote.codigo}: {l.cantidad_reservada}" for i, l in actuales.items() if i not in nuevas]
        for i, linea in actuales.items():
            if i not in nuevas:
                linea.delete()
            elif linea.cantidad_reservada != nuevas[i]:
                linea.cantidad_reservada = nuevas[i]
                linea.save(update_fields=["cantidad_reservada"])
        for lote_id, cantidad in nuevas.items():
            if lote_id not in actuales:
                DetalleReserva.objects.create(reserva=reserva, lote_id=lote_id, cantidad_reservada=cantidad)
        antes = {"fecha_programada_orden": cosecha.fecha_programada_orden, "prioridad_orden": cosecha.prioridad_orden, "descripcion_orden": cosecha.descripcion_orden}
        OrdenTrabajo.objects.filter(pk=cosecha.pk).update(
            fecha_programada_orden=datos.fecha_programada, prioridad_orden=datos.prioridad, descripcion_orden=(datos.descripcion or "").strip()
        )
        cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").get(pk=cosecha.pk)
        lineas = _lineas_de_lote(reserva)
        resumen = "; ".join(f"{campo}: {antes_} → {despues}" for campo, antes_, despues in verificacion.cambios)
        if cosecha.capataz.is_active:
            notificaciones.notificar(cosecha.capataz, f"Cosecha {cosecha.codigo} modificada", _acotar(f"El Agrónomo cambió: {resumen}.", 500))
        retraso = contrato is not None and datos.fecha_programada != antes["fecha_programada_orden"] and datos.fecha_programada > contrato.fecha_entrega
        if retraso:
            vendedor = Usuario.objects.filter(pk=contrato.contrato.vendedor_id, is_active=True).first()
            if vendedor is not None:
                notificaciones.notificar(vendedor, f"Cosecha de {contrato.contrato.codigo} con retraso", _acotar(_mensaje_de_retraso(contrato, datos.fecha_programada), 500))
        cambios = {}
        for campo, valor_antes in antes.items():
            nuevo = getattr(cosecha, campo)
            if nuevo != valor_antes:
                cambios[campo] = {"antes": _fecha(valor_antes) if isinstance(valor_antes, date) else valor_antes, "despues": _fecha(nuevo) if isinstance(nuevo, date) else nuevo}
        for campo, antes_, despues in verificacion.cambios:
            if campo == "lotes":
                cambios["lotes"] = {"antes": antes_, "despues": despues}
        detalle = {"cambios": cambios}
        if borradas:
            detalle["datos"] = {"lineas_borradas": borradas}
        RegistroAuditoria.objects.registrar(usuario=actor, accion=RegistroAuditoria.Accion.MODIFICACION_COSECHA, afectados=[cosecha, reserva, *lineas], detalle=detalle)
    return cosecha


# ---- PROD-CNC-CSC: concretar ----


def propuesta_por_sector(cantidad, ocupados):
    """Lista de tecnología 7a de PROD-CNC-CSC (función pura): reparte `cantidad` entre los sectores `[(sector_id, agujeros ocupados)]` en proporción a lo
    que el lote ocupa en cada uno, por resto mayor; con empate, el sector con más agujeros ocupados y después el primero. Devuelve `{sector_id: plantas}`."""
    ocupados = list(ocupados)
    partes = transiciones.repartir_proporcional(cantidad, [n for _, n in ocupados])
    return {sector_id: parte for (sector_id, _), parte in zip(ocupados, partes)}


def _ocupados_de(lote):
    """`{sector_id: (agujeros ocupados por el lote, nombre del sector)}` por id de sector (ocupaciones vigentes: con agujeros ocupados)."""
    resultado = {}
    for o in api_lotes.sectores_de_origen(lote):
        n, nombre = resultado.get(o.sector_id, (0, o.sector.nombre_sector))
        resultado[o.sector_id] = (n + o.cant_agujeros_ocupados, nombre)
    return dict(sorted(resultado.items()))


def datos_de_concrecion(actor, cosecha_id):
    """Pasos 2 a 4 de PROD-CNC-CSC: la cosecha con su contrato y su fecha de entrega y, por lote, lo reservado y sus sectores con los agujeros que ocupa y
    la cantidad propuesta (la reservada repartida por resto mayor). Solo el Capataz asignado. Solo lectura."""
    cosecha = _cosecha_del_capataz(actor, cosecha_id)
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    contrato = _contrato_de_reserva(reserva)
    lotes = []
    for linea in _lineas_de_lote(reserva):
        ocupados = _ocupados_de(linea.lote)
        propuesta = propuesta_por_sector(linea.cantidad_reservada, [(s, n) for s, (n, _) in ocupados.items()])
        lotes.append(LoteAConcretar(linea.lote_id, linea.lote.codigo, linea.cantidad_reservada, [SectorAConcretar(s, nombre, n, propuesta[s]) for s, (n, nombre) in ocupados.items()]))
    return FichaDeConcrecion(cosecha, contrato.contrato.codigo if contrato else None, contrato.fecha_entrega if contrato else None, stock.hoy(), lotes)


_Plan = namedtuple("_Plan", "linea lote por_sector perdidas causa descripcion cosechada excedente no_cosechadas total_perdidas")


def _evaluar_concrecion(cosecha, reserva, datos, hoy):
    """Todas las verificaciones de PROD-CNC-CSC contra lo que hay en la base AHORA (6a, 6b, 8a, 8b, 10a.3a y 10a.3b). Devuelve `(errores, planes)`."""
    errores = {}
    fecha = datos.fecha_efectiva or hoy
    if fecha > hoy:
        errores.setdefault("fecha_efectiva", []).append(("fecha_futura", "La fecha efectiva no puede ser posterior a hoy."))
    elif fecha < cosecha.fecha_creacion_orden:
        errores.setdefault("fecha_efectiva", []).append(
            ("fecha_antes_de_creacion", f"La fecha efectiva no puede ser anterior a la fecha de creación de la orden ({_fecha(cosecha.fecha_creacion_orden)}).")
        )
    cantidades = {(l, s): n for l, s, n in datos.cantidades}
    perdidas = {(l, s): n for l, s, n in datos.perdidas}
    causas = {l: (c, d) for l, c, d in datos.causas}
    planes = []
    for linea in _lineas_de_lote(reserva):
        lote, reservada = linea.lote, linea.cantidad_reservada
        ocupados = _ocupados_de(lote)
        propuesta = propuesta_por_sector(reservada, [(s, n) for s, (n, _) in ocupados.items()])
        por_sector = {}
        for sector_id, (n, nombre) in ocupados.items():
            q = cantidades.get((lote.pk, sector_id), propuesta[sector_id])
            campo = f"cantidad_{lote.pk}_{sector_id}"
            if not _entero(q) or q < 0:
                errores.setdefault(campo, []).append(("cantidad_invalida", "Las plantas cosechadas deben ser un número entero, cero o más."))
                q = 0
            elif q > n:
                errores.setdefault(campo, []).append(("supera_sector", f"El lote {lote.codigo} ocupa {n} agujeros en {nombre}: no se pueden cosechar {q}."))
            por_sector[sector_id] = q
        for (lote_id, sector_id), q in cantidades.items():
            if lote_id == lote.pk and sector_id not in ocupados and q:
                errores.setdefault(f"cantidad_{lote_id}_{sector_id}", []).append(("supera_sector", f"El lote {lote.codigo} no ocupa agujeros en ese sector."))
        cosechada = sum(por_sector.values())
        # Máximo (regla «Cantidad cosechada válida»): lo reservado en esta línea más el stock libre del lote (su cantidad actual menos todo lo reservado,
        # esta reserva incluida): es decir, la cantidad actual menos lo que reservan las OTRAS órdenes.
        libre = max(0, lote.cantidad_actual - stock_maduro.reservado_de_lotes([lote.pk]).get(lote.pk, 0))
        maximo = reservada + libre
        if cosechada > maximo:
            errores.setdefault(f"lote_{lote.pk}", []).append(
                ("supera_maximo", f"Del lote {lote.codigo} se pueden cosechar como máximo {_plantas(maximo)} sin tomar plantas reservadas por otras órdenes.")
            )
        perdidas_del_lote = {s: perdidas.get((lote.pk, s), 0) for s in ocupados}
        total_perdidas = sum(n for n in perdidas_del_lote.values() if _entero(n) and n > 0)
        no_cosechadas = max(0, reservada - cosechada)
        if total_perdidas > no_cosechadas:
            errores.setdefault(f"perdidas_{lote.pk}", []).append(
                ("supera_no_cosechadas", f"Las plantas perdidas no pueden superar las que no se cosecharon ({no_cosechadas}).")
            )
        for sector_id, n in perdidas_del_lote.items():
            if _entero(n) and n > ocupados[sector_id][0] - por_sector.get(sector_id, 0):
                errores.setdefault(f"perdidas_{lote.pk}_{sector_id}", []).append(
                    ("supera_sector", f"En {ocupados[sector_id][1]} quedan {ocupados[sector_id][0] - por_sector.get(sector_id, 0)} plantas del lote después de cosechar: no se pueden perder {n}.")
                )
        causa, descripcion = causas.get(lote.pk, ("", ""))
        if total_perdidas:
            if not causa:
                errores.setdefault(f"causa_{lote.pk}", []).append(("causa_obligatoria", "Indicá la causa de las plantas perdidas."))
            elif causa not in Merma.CAUSAS_EN_PIE or causa == Merma.Causa.DESCARTE_POR_SELECCION:
                errores.setdefault(f"causa_{lote.pk}", []).append(("causa_invalida", "Esa causa no corresponde a plantas perdidas en la cosecha."))
            elif len((descripcion or "").strip()) > 300:
                errores.setdefault(f"causa_{lote.pk}", []).append(("descripcion_larga", "La descripción pasa de 300 caracteres."))
        planes.append(_Plan(linea, lote, por_sector, perdidas_del_lote, causa, (descripcion or "").strip(), cosechada, max(0, cosechada - reservada), no_cosechadas, total_perdidas))
    return errores, planes


def _resumen(planes, con_contrato, errores):
    """El `ResumenDeConcrecion` de los planes (paso 11 de PROD-CNC-CSC)."""
    filas = [
        FilaDeLoteConcretado(p.lote.pk, p.lote.codigo, p.linea.cantidad_reservada, p.cosechada, p.excedente, p.no_cosechadas, p.total_perdidas, max(0, p.no_cosechadas - p.total_perdidas))
        for p in planes
    ]
    destino = []
    if not con_contrato:
        destino.append(f"Todo lo cosechado ({_plantas(sum(f.cosechada for f in filas))}) ingresa a la cámara.")
    else:
        destino.extend(f"El excedente de {f.codigo} ({_plantas(f.excedente)}) ingresa a la cámara." for f in filas if f.excedente)
        faltante = sum(f.reservada - min(f.cosechada, f.reservada) for f in filas)
        if faltante:
            destino.append(f"Faltan {_plantas(faltante)} para cubrir el contrato: se intentará cubrirlas con otro stock maduro.")
    return ResumenDeConcrecion(errores, filas, sum(f.reservada for f in filas), sum(f.cosechada for f in filas), destino)


def verificar_concrecion(actor, cosecha_id, datos):
    """Pasos 6 a 11 de PROD-CNC-CSC: las verificaciones y el resumen (por lote, lo reservado, lo cosechado, el excedente, lo no cosechado, lo perdido y lo
    que queda libre; el total y el destino de lo cosechado). **No escribe ni bloquea.** `errores` es `{campo: [(codigo, mensaje)]}`."""
    cosecha = _cosecha_del_capataz(actor, cosecha_id)
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    errores, planes = _evaluar_concrecion(cosecha, reserva, datos, stock.hoy())
    return _resumen(planes, _contrato_de_reserva(reserva) is not None, errores)


def concretar_cosecha(actor, cosecha_id, datos):
    """PROD-CNC-CSC: concreta la cosecha y devuelve `ResultadoConcrecion(cosecha, reserva, partidas, mermas, asignacion, faltante)` (pasos 12 a 15).

    - Precondiciones a y b y regla «Quién»: el Capataz activo asignado a la cosecha (`PermissionDenied`). Extensiones 6a, 6b, 8a, 8b, 10a.3a, 10a.3b, 13b y
      13c: `ValidationError` por campo (`fecha_futura`, `fecha_antes_de_creacion`, `supera_sector`, `supera_maximo`, `supera_no_cosechadas`,
      `causa_obligatoria`, `orden_no_a_realizar`), repetidas DESPUÉS de bloquear.
    - Registro (paso 13), en UNA transacción y en este orden: por cada lote `cosechas.cosechar_lote` (a, b, c, d, e, g); por cada lote con plantas
      perdidas `mermas.aplicar_merma` (m); `cosechas.concretar_orden` (a); la reserva (h: con contrato «lista para entrega», salvo cubierto 0, que la
      «libera»; sin contrato, «liberada»); las partidas (i y j, con el costo de la salida del lote); con contrato y faltante (13a, regla «Faltante»),
      `stock_maduro.asignar(..., origen_cosecha="encadenada")` y lo no cubierto por el camino de faltante (l). Sin el `on_commit` de PROD-ASG-CAM
      (k) la programa con `on_commit`; el enlace del cliente es de COM-04c y la postcondición n (planificar la entrega), de COM-05. Asientos (CON-04c): ver más abajo.
    - Postcondiciones o a r y D-36: aviso al Agrónomo y, con faltante o excedente, al Vendedor; UN registro `concrecion_cosecha`.
    """
    cosecha = _cosecha_del_capataz(actor, cosecha_id)
    hoy = stock.hoy()
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    previo = _contrato_de_reserva(reserva)
    _exigir_a_realizar(cosecha)
    with transaction.atomic():
        _bloquear_cuentas({actor.pk, cosecha.invernadero.agronomo_id, previo.contrato.vendedor_id if previo else None})
        ids = _bloquear_invernaderos(cosecha.invernadero_id, previo)
        bloquear_variedad(cosecha.variedad_id)
        _bloquear_sectores_y_lotes(cosecha.variedad_id, ids, [l.lote_id for l in _lineas_de_lote(reserva)])
        _bloquear_contrato(previo)
        _bloquear_cosecha(cosecha.pk)
        cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").get(pk=cosecha_id)
        _exigir_a_realizar(cosecha)  # 13b
        reserva = ReservaStock.objects.get(cosecha=cosecha)
        errores, planes = _evaluar_concrecion(cosecha, reserva, datos, hoy)  # 13c y todo lo demás, con lo bloqueado
        if errores:
            _rechazar(errores)
        contrato = _contrato_de_reserva(reserva)
        fecha = datos.fecha_efectiva or hoy
        antes_de_lotes = {p.lote.pk: (p.lote.cantidad_actual, p.lote.costo_acumulado) for p in planes}
        ocupaciones_antes = {o.pk: o.cant_agujeros_ocupados for o in OcupacionSector.objects.filter(lote__in=[p.lote for p in planes])}
        resultados, mermas_hechas, partidas, costos_de_mermas = {}, [], [], {}
        for p in planes:
            resultados[p.lote.pk] = fisico.cosechar_lote(cosecha, p.lote, p.por_sector, fecha, actor)
            DetalleReserva.objects.filter(pk=p.linea.pk).update(cantidad_cosechada=p.cosechada)
            p.linea.cantidad_cosechada = p.cosechada
        for p in planes:
            if p.total_perdidas:
                por_sector = {s: n for s, n in p.perdidas.items() if n}
                resultado_de_merma = mermas.aplicar_merma(p.lote, p.total_perdidas, p.causa, p.descripcion, hoy, actor, por_sector=por_sector, sector_ids=list(por_sector))
                mermas_hechas.append(resultado_de_merma.merma)
                costos_de_mermas[resultado_de_merma.merma.pk] = resultado_de_merma.costo
        fisico.concretar_orden(cosecha, fecha)
        todas = _lineas_de(reserva)
        cubierto = sum(min(l.cantidad_cosechada, l.cantidad_reservada) if l.lote_id else l.cantidad_reservada for l in todas)
        con_contrato = contrato is not None
        reserva.estado_reserva = ReservaStock.Estado.LISTA_PARA_ENTREGA if con_contrato and cubierto > 0 else ReservaStock.Estado.LIBERADA
        ReservaStock.objects.filter(pk=reserva.pk).update(estado_reserva=reserva.estado_reserva)
        for p in planes:
            r = resultados[p.lote.pk]
            cantidad = p.excedente if con_contrato else p.cosechada
            if cantidad > 0:
                motivo = StockCosechado.Motivo.EXCEDENTE_DE_COSECHA if con_contrato else StockCosechado.Motivo.COSECHA_DEL_AGRONOMO
                partidas.append(
                    camara.crear_partida(p.lote, cantidad, motivo, fecha_cosecha=fecha, fecha_ingreso=fecha, costo_unitario=r.costo_unitario, origen=cosecha)
                )
        camara_comercial.programar_asignacion_de_camara([p.pk for p in partidas])  # k (D-64 punto 9): corre después de confirmar; el paso 25 la recupera si falla
        faltante = sum(p.linea.cantidad_reservada - min(p.cosechada, p.linea.cantidad_reservada) for p in planes) if con_contrato else 0
        asignacion, sin_cubrir, enlace_nuevo = None, 0, None
        if faltante:
            detalle_actual = contrato.detalle.__class__.objects.get(pk=contrato.detalle.pk)
            puede = (
                detalle_actual.estado_detalle_venta == DetalleVenta.Estado.ABIERTO and contrato.contrato.__class__.objects.get(pk=contrato.contrato.pk).estado_venta == CompraVenta.Estado.ABIERTA
                if contrato.tipo == "cv"
                else stock_maduro._se_debe(detalle_actual, contrato.fecha_entrega) and Suministro.objects.get(pk=contrato.contrato.pk).estado_suministro == Suministro.Estado.VIGENTE
            )
            if puede:
                asignacion = stock_maduro.asignar(
                    actor, contrato.periodo if contrato.tipo == "sum" else detalle_actual, faltante, contrato.fecha_entrega, _parametro(contrato),
                    origen_cosecha=Cosecha.OrigenCosecha.ENCADENADA,
                )
                sin_cubrir = asignacion.sin_cubrir
            else:
                sin_cubrir = faltante
            if sin_cubrir:
                camino = faltantes.seguir_camino_de_faltante(contrato.periodo if contrato.tipo == "sum" else detalle_actual, sin_cubrir, origen=actor)
                enlace_nuevo = camino.enlace  # COM-04c: el enlace del cliente va a la auditoría de quien lo crea
        entregas.programar_para_reservas([reserva.pk, *(r.pk for r in (asignacion.reservas if asignacion is not None else []))])  # n (D-66 punto 5): si la reserva quedó lista, con ella la venta o el período
        # CON-04c (D-92 puntos 3 a 6): los asientos, DESPUÉS de todos los bloqueos de negocio (el ejercicio se bloquea al final, D-86). Postcondición f: uno por cada
        # movimiento «salida por cosecha», con la fecha efectiva; extensión 10a (decisión del 26/11/2026): uno por cada merma de lote, con la fecha de la merma.
        asientos_creados = asientos_de_produccion.referencias_de(
            [asientos_comerciales.asentar_salida_por_cosecha(actor, r.movimiento, fecha, hoy) for r in resultados.values() if r.movimiento is not None]
            + [asientos_de_produccion.asentar_merma(actor, m, costos_de_mermas[m.pk], hoy, hoy) for m in mermas_hechas]
        )
        reservado_total = sum(p.linea.cantidad_reservada for p in planes)
        cosechado_total = sum(p.cosechada for p in planes)
        perdido_total = sum(p.total_perdidas for p in planes)
        _avisar_concrecion(cosecha, contrato, planes, faltante, asignacion, sin_cubrir, sum(p.excedente for p in planes) if con_contrato else 0)
        afectados = [cosecha, reserva, *todas, *[p.lote for p in planes]]
        afectados += list(OcupacionSector.objects.filter(lote__in=[p.lote for p in planes]).order_by("pk"))
        afectados += [r.movimiento for r in resultados.values() if r.movimiento is not None] + [r.bitacora for r in resultados.values()] + partidas
        afectados += [m for m in mermas_hechas]
        afectados += list(
            MovimientoStock.objects.filter(origen_id__in=[cosecha.pk] + [m.pk for m in mermas_hechas])
            .exclude(pk__in=[r.movimiento.pk for r in resultados.values() if r.movimiento is not None])
            .order_by("pk")
        )
        afectados += asientos_creados
        if asignacion is not None:
            afectados += [*asignacion.reservas, *asignacion.cosechas]
        if contrato is not None:
            afectados.append(contrato.detalle)
        if enlace_nuevo is not None:
            afectados.append(enlace_nuevo)
        cambios = {
            "estado": {"antes": Estado.A_REALIZAR.value, "despues": Estado.CONCRETADA.value},
            "fecha_resolucion_orden": {"antes": None, "despues": _fecha(hoy)},
            "fecha_cosecha": {"antes": None, "despues": _fecha(fecha)},
        }
        datos_de_auditoria = {
            "reservado": reservado_total,
            "cosechado": cosechado_total,
            "perdido": perdido_total,
            "faltante": faltante,
            "lotes": [f"{p.lote.codigo}: {antes_de_lotes[p.lote.pk][0]} → {p.lote.cantidad_actual}" for p in planes],
            "agujeros_ocupados": [
                f"{o}: {ocupaciones_antes[o.pk]} → {o.cant_agujeros_ocupados}" for o in OcupacionSector.objects.filter(lote__in=[p.lote for p in planes]).order_by("pk") if ocupaciones_antes[o.pk] != o.cant_agujeros_ocupados
            ],
            "reserva": reserva.estado_reserva,
            "asientos": [str(a) for a in asientos_creados],
        }
        RegistroAuditoria.objects.registrar(
            usuario=actor, accion=RegistroAuditoria.Accion.CONCRECION_COSECHA, afectados=afectados, detalle={"cambios": cambios, "datos": datos_de_auditoria}
        )
    return ResultadoConcrecion(cosecha, reserva, partidas, mermas_hechas, asignacion, faltante)


def _avisar_concrecion(cosecha, contrato, planes, faltante, asignacion, sin_cubrir, excedente):
    """Postcondición o (paso 14): al Agrónomo del invernadero, lo reservado, lo cosechado y lo perdido de cada lote; con contrato y faltante o excedente,
    también al Vendedor. Dentro de la transacción (D-42)."""
    agronomo = cosecha.invernadero.agronomo
    if agronomo is not None and agronomo.is_active:
        por_lote = "; ".join(f"{p.lote.codigo}: reservadas {p.linea.cantidad_reservada}, cosechadas {p.cosechada}, perdidas {p.total_perdidas}" for p in planes)
        detalle = f"{cosecha.variedad}. {por_lote}."
        if len(detalle) > 500:
            detalle = f"{cosecha.variedad}. Reservadas {sum(p.linea.cantidad_reservada for p in planes)}, cosechadas {sum(p.cosechada for p in planes)}, perdidas {sum(p.total_perdidas for p in planes)}: ver la cosecha."
        notificaciones.notificar(agronomo, f"Cosecha {cosecha.codigo} concretada", _acotar(detalle, 500))
    if contrato is None or not (faltante or excedente):
        return
    vendedor = Usuario.objects.filter(pk=contrato.contrato.vendedor_id, is_active=True).first()
    if vendedor is None:
        return
    partes = []
    if faltante:
        partes.append(f"Faltaron {faltante}.")
        if asignacion is not None and asignacion.cubierta:
            partes.append(f"Se volvieron a reservar {asignacion.cubierta}.")
        if sin_cubrir:
            partes.append(
                f"Quedan {sin_cubrir} sin cubrir; el cliente recibe un enlace para decidir." if contrato.tipo == "cv" else f"Quedan {sin_cubrir} sin cubrir: el período sale con lo disponible."
            )
    if excedente:
        partes.append(f"Sobraron {excedente}: ingresan a la cámara.")
    titulo = f"Cosecha de {contrato.contrato.codigo}: " + (f"faltaron {faltante}" if faltante else f"sobraron {excedente}")
    notificaciones.notificar(vendedor, _acotar(titulo, 120), _acotar(f"{cosecha.codigo}. " + " ".join(partes), 500))


# ---- PROD-CNL-ORD: cancelar una cosecha ----


def _huella_de_cancelacion(cosecha_id):
    """Lo que cuenta para detectar que algo cambió entre el resumen y el registro (8b): la cosecha (`huella_de`), el estado de la reserva y de sus líneas
    y el estado del detalle y de la venta."""
    reserva = ReservaStock.objects.filter(cosecha_id=cosecha_id).first()
    lineas = (
        []
        if reserva is None
        else sorted(
            DetalleReserva.objects.filter(reserva=reserva).values_list("lote_id", "partida_id", "cantidad_reservada", "cantidad_cosechada"),
            key=lambda t: tuple(-1 if x is None else x for x in t),
        )
    )
    contrato = _contrato_de_reserva(reserva) if reserva is not None else None
    estados = None
    if contrato is not None:
        detalle = contrato.detalle.__class__.objects.get(pk=contrato.detalle.pk)
        estados = [
            getattr(detalle, "estado_detalle_venta", None) or getattr(detalle, "estado_detalle_suministro", None),
            contrato.contrato.__class__.objects.values_list("estado_venta" if contrato.tipo == "cv" else "estado_suministro", flat=True).get(pk=contrato.contrato.pk),
        ]
    return json.dumps([huella_de(Cosecha(pk=cosecha_id)), reserva.estado_reserva if reserva else None, lineas, estados], default=str)


def _cubierto_de(lineas):
    """La cantidad que cubren las líneas (regla 9 de 8.8): de lote sin cosechar, la reservada; de lote cosechado, `min(cosechada, reservada)`; de partida, la reservada."""
    return sum(min(l.cantidad_cosechada, l.cantidad_reservada) if l.lote_id and l.cantidad_cosechada is not None else l.cantidad_reservada for l in lineas)


def _ya_pendiente(contrato):
    """6c y 8d: el detalle o su venta ya esperan la decisión del cliente."""
    if contrato is None or contrato.tipo != "cv":
        return False
    detalle = DetalleVenta.objects.get(pk=contrato.detalle.pk)
    venta = CompraVenta.objects.get(pk=contrato.contrato.pk)
    return DetalleVenta.Estado.PENDIENTE_DECISION in (detalle.estado_detalle_venta,) or venta.estado_venta == CompraVenta.Estado.PENDIENTE_DECISION


def resumen_de_cancelacion_de_cosecha(actor, cosecha_id):
    """Pasos 4 y 6 de PROD-CNL-ORD para una cosecha: la reserva con sus lotes y sus partidas, el contrato y lo que cubre (4b y 4c) y la estimación de cuánto se
    vuelve a cubrir sin sus lotes (6b: `simular`-`estimar` con `lotes_excluidos` y `sin_reservas`), o el aviso de que el detalle ya espera la decisión
    del cliente (6c, `ya_pendiente`). **No escribe ni bloquea.** Solo el Agrónomo a cargo."""
    cosecha = _cosecha_del_agronomo(actor, cosecha_id)
    _exigir_a_realizar(cosecha)
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    contrato = _contrato_de_reserva(reserva)
    lineas = _lineas_de(reserva)
    cubierto = _cubierto_de(lineas) if contrato is not None else 0
    ya = _ya_pendiente(contrato)
    estimacion = None
    if contrato is not None and not ya and cubierto > 0 and _es_recubrible(contrato):
        considerados = [i.pk for i in stock_maduro.invernaderos_considerados(contrato.contrato)]
        e = stock_maduro.estimar(
            cosecha.variedad_id, considerados, contrato.fecha_entrega, cubierto, _parametro(contrato),
            lotes_excluidos=[l.lote_id for l in lineas if l.lote_id], sin_reservas=[reserva],
        )
        origenes = [(c.origen.codigo, cuanto) for c, cuanto in e.origenes]
        estimacion = Estimacion(e.cubierta, e.sin_cubrir, origenes, any(c.tipo == "lote" for c, _ in e.origenes))
    return ResumenDeCancelacion(
        cosecha, reserva, [((l.lote or l.partida).codigo, l.cantidad_reservada) for l in lineas],
        contrato.contrato.codigo if contrato else None, contrato.fecha_entrega if contrato else None, cubierto, ya, estimacion, _huella_de_cancelacion(cosecha.pk),
    )


def _es_recubrible(contrato):
    """8c: el detalle se puede volver a cubrir con `asignar` (compra-venta: detalle «abierto» de venta «abierta»; suministro: un período que se debe de un
    suministro «vigente»)."""
    if contrato.tipo == "cv":
        detalle = DetalleVenta.objects.get(pk=contrato.detalle.pk)
        venta = CompraVenta.objects.get(pk=contrato.contrato.pk)
        return detalle.estado_detalle_venta == DetalleVenta.Estado.ABIERTO and venta.estado_venta == CompraVenta.Estado.ABIERTA
    detalle = DetalleSuministro.objects.get(pk=contrato.detalle.pk)
    return stock_maduro._se_debe(detalle, contrato.fecha_entrega) and Suministro.objects.get(pk=contrato.contrato.pk).estado_suministro == Suministro.Estado.VIGENTE


def _motivo_valido(motivo):
    """Paso 5 y extensión 6a: el motivo es obligatorio (sin espacios al borde) y de hasta 300 caracteres."""
    motivo = (motivo or "").strip()
    if not motivo:
        _error("motivo", "motivo_obligatorio", "Indicá el motivo de la cancelación.")
    if len(motivo) > LARGO_DEL_MOTIVO:
        _error("motivo", "motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.")
    return motivo


def _cancelar_en_transaccion(actor, cosecha, motivo, *, recubrir):
    """Postcondiciones f y g y extensiones 8c y 8d, dentro de la transacción y con todo bloqueado: cancela la cosecha (`ordenes.marcar_cancelada`), libera su
    reserva y, con contrato y `recubrir`, vuelve a cubrir lo que cubría con `asignar` (sin los lotes de la cosecha) y sigue el camino de faltante con lo que
    no se cubre. No audita ni notifica. Devuelve `CancelacionDeCosecha`."""
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    contrato = _contrato_de_reserva(reserva)
    lineas = _lineas_de(reserva)
    cubierto = _cubierto_de(lineas) if contrato is not None else 0
    lotes_de_la_cosecha = [l.lote_id for l in lineas if l.lote_id]
    ordenes.marcar_cancelada(cosecha, motivo)
    DetalleReserva.objects.filter(reserva=reserva, lote__isnull=False).update(cantidad_cosechada=None)
    ReservaStock.objects.filter(pk=reserva.pk).update(estado_reserva=ReservaStock.Estado.LIBERADA)
    reserva.estado_reserva = ReservaStock.Estado.LIBERADA
    camara_comercial.programar_asignacion_de_camara([l.partida_id for l in lineas if l.partida_id])  # h (D-64 punto 9): el stock de cámara que apartaba vuelve a estar libre
    asignacion, sin_cubrir, enlaces_nuevos = None, 0, []
    if contrato is not None and recubrir and cubierto > 0:
        if _ya_pendiente(contrato):  # 6c y 8d: no se intenta volver a cubrir; la cantidad se suma al faltante
            sin_cubrir = cubierto
        elif _es_recubrible(contrato):  # 8c
            asignacion = stock_maduro.asignar(
                actor, contrato.periodo if contrato.tipo == "sum" else DetalleVenta.objects.get(pk=contrato.detalle.pk), cubierto, contrato.fecha_entrega,
                _parametro(contrato), lotes_excluidos=lotes_de_la_cosecha,
            )
            sin_cubrir = asignacion.sin_cubrir
        else:
            sin_cubrir = cubierto
        if sin_cubrir:
            camino = faltantes.seguir_camino_de_faltante(contrato.periodo if contrato.tipo == "sum" else DetalleVenta.objects.get(pk=contrato.detalle.pk), sin_cubrir, origen=actor)
            if camino.enlace is not None:
                enlaces_nuevos.append(camino.enlace)
    if asignacion is not None:
        entregas.programar_para_reservas([r.pk for r in asignacion.reservas])  # i: lo que PROD-ASG-STK volvió a cubrir con stock listo se planifica después de confirmar
    return CancelacionDeCosecha(cosecha, reserva, lineas, cubierto, asignacion, sin_cubrir, [], enlaces_nuevos)


def _aviso_de_cancelacion(cosecha, motivo, actor, cuentas):
    """El aviso de la cancelación (el texto de `produccion`, postcondición k) a cada cuenta activa de `cuentas` (sin repetir ni avisar a quien actúa)."""
    titulo, detalle = ordenes.texto_de_cancelacion(cosecha, motivo, actor)
    activas = [c for c in cuentas if c is not None and c.is_active]
    notificaciones.notificar_a_varios(activas, titulo, detalle, excluir=actor)
    return activas


def cancelar_cosecha(actor, cosecha_id, motivo, huella):
    """PROD-CNL-ORD para una cosecha: la cancela y devuelve `CancelacionDeCosecha` (pasos 5 a 9).

    - Precondición a y regla 2 de 8.22: el Agrónomo activo a cargo del invernadero (`PermissionDenied`), de cualquier origen de la cosecha. Extensión 6a:
      motivo obligatorio y de hasta 300 (`motivo_obligatorio`, `motivo_largo`).
    - Paso 8, en UNA transacción con los bloqueos del encabezado: se relee y se verifica que la cosecha siga «a realizar» (8a, `orden_no_a_realizar`) y que
      no hayan cambiado la cosecha, su reserva ni el estado del detalle y de la venta desde el resumen (8b, `cosecha_cambio`).
    - Postcondiciones f y g (extensiones 8c y 8d): ver `_cancelar_en_transaccion`. El `on_commit` de PROD-ASG-CAM (h) lo programa `_cancelar_en_transaccion`; el enlace del cliente
      es de COM-04c. Sin bitácora ni movimientos de stock (regla del CU).
    - Postcondiciones k y l (D-42): aviso al Capataz con el motivo y, con contrato, al Vendedor con lo que se volvió a cubrir y lo que quedó sin cubrir.
    - Postcondiciones m y n y D-36: UN registro `cancelacion_orden`.
    """
    cosecha = _cosecha_del_agronomo(actor, cosecha_id)
    motivo = _motivo_valido(motivo)
    reserva = ReservaStock.objects.get(cosecha=cosecha)
    previo = _contrato_de_reserva(reserva)
    with transaction.atomic():
        _bloquear_cuentas({actor.pk, cosecha.capataz_id, previo.contrato.vendedor_id if previo else None})
        ids = _bloquear_invernaderos(cosecha.invernadero_id, previo)
        bloquear_variedad(cosecha.variedad_id)
        _bloquear_sectores_y_lotes(cosecha.variedad_id, ids, [l.lote_id for l in _lineas_de(reserva) if l.lote_id])
        _bloquear_contrato(previo)
        _bloquear_cosecha(cosecha.pk)
        cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").get(pk=cosecha_id)
        _exigir_a_realizar(cosecha)  # 8a
        if _huella_de_cancelacion(cosecha.pk) != huella:
            _error(NO_CAMPO, "cosecha_cambio", "Mientras mirabas el resumen, la cosecha o su contrato cambiaron. Volvé a abrir la cancelación.")
        resultado = _cancelar_en_transaccion(actor, cosecha, motivo, recubrir=True)
        contrato = _contrato_de_reserva(resultado.reserva)
        avisados = _aviso_de_cancelacion(cosecha, motivo, actor, [cosecha.capataz])
        if contrato is not None:
            vendedor = Usuario.objects.filter(pk=contrato.contrato.vendedor_id, is_active=True).first()
            if vendedor is not None and vendedor.pk != actor.pk:
                cubierta = resultado.asignacion.cubierta if resultado.asignacion else 0
                notificaciones.notificar(
                    vendedor,
                    _acotar(f"Cosecha {cosecha.codigo} de {contrato.contrato.codigo} cancelada", 120),
                    _acotar(f"Se volvieron a cubrir {_plantas(cubierta)} y quedaron {_plantas(resultado.sin_cubrir)} sin cubrir.", 500),
                )
        afectados = [cosecha, resultado.reserva, *resultado.lineas]
        if contrato is not None:
            afectados += [contrato.detalle, contrato.contrato]
        if resultado.asignacion is not None:
            afectados += [*resultado.asignacion.reservas, *resultado.asignacion.cosechas]
        afectados += resultado.enlaces
        cambios = {
            "estado": {"antes": Estado.A_REALIZAR.value, "despues": Estado.CANCELADA.value},
            "fecha_resolucion_orden": {"antes": None, "despues": _fecha(stock.hoy())},
            "motivo_cancelacion": {"antes": None, "despues": motivo},
        }
        datos_de_auditoria = {"cubierto": resultado.cubierto, "sin_cubrir": resultado.sin_cubrir}
        RegistroAuditoria.objects.registrar(usuario=actor, accion=RegistroAuditoria.Accion.CANCELACION_ORDEN, afectados=afectados, detalle={"cambios": cambios, "datos": datos_de_auditoria})
    return resultado._replace(notificar_a=avisados)


def cancelar_cosecha_incluida(actor, cosecha, motivo, *, recubrir=True, avisar=True, avisar_agronomo=True):
    """PROD-CNL-ORD como parte de otro caso de uso (COM-DCD-FLT, COM-04c; COM-CNL-CVT y la cancelación de entregas, desde COM-05), igual que
    `produccion.ordenes.cancelar_orden_incluida`: `actor` puede ser `None` (InfoPonia); corre en la transacción del llamador, que ya tiene los bloqueos del
    encabezado (sin ella, `RuntimeError`); **no audita**: devuelve la cosecha, la reserva y lo creado para el registro del llamador.

    - El motivo ya viene armado; si pasa de 300, se recorta con «…» (no lanza `motivo_largo`); vacío, `motivo_obligatorio`.
    - Cancela solo cosechas «a realizar» (`orden_no_a_realizar`).
    - Con `recubrir=False` no llama a `asignar` ni al camino de faltante (COM-DCD-FLT: el detalle se rechazó).
    - Con `avisar=True`, el aviso al Capataz y al Agrónomo del invernadero (postcondición j de COM-DCD-FLT). El aviso al Vendedor lo arma el llamador.
    - `avisar_agronomo=False` (COM-07b, paso 4.1 de COM-RSV-SUM; situación 9) omite solo el aviso al Agrónomo: la resolución le manda UNA notificación por invernadero. Por omisión
      `True`, para que COM-DCD-FLT y COM-CNL-CVT no cambien. Con `avisar=False` no se avisa a nadie.
    """
    if transaction.get_autocommit():
        raise RuntimeError("`cancelar_cosecha_incluida` corre dentro de la transacción del caso de uso que la llama.")
    motivo = (motivo or "").strip()
    if not motivo:
        _error("motivo", "motivo_obligatorio", "Indicá el motivo de la cancelación.")
    if len(motivo) > LARGO_DEL_MOTIVO:
        motivo = motivo[: LARGO_DEL_MOTIVO - 1] + "…"
    _bloquear_cosecha(cosecha.pk)
    cosecha = Cosecha.objects.select_related("invernadero", "capataz", "variedad").get(pk=cosecha.pk)
    _exigir_a_realizar(cosecha)
    resultado = _cancelar_en_transaccion(actor, cosecha, motivo, recubrir=recubrir)
    cuentas = [cosecha.capataz, cosecha.invernadero.agronomo] if avisar_agronomo else [cosecha.capataz]
    avisados = _aviso_de_cancelacion(cosecha, motivo, actor, cuentas) if avisar else []
    return resultado._replace(notificar_a=avisados)
