# Cobranza de suministros de `comercial` (COM-08a; D-94): los cálculos del cobro (funciones puras), la mora (`reevaluar_mora`, la alerta «pago en mora», su enlace y el aviso al cliente) y el paso diario 30
# (COM-VNC-PAG). El cobro mismo (COM-REG-CBR) se suma en el paso 5 de la tarea.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Cálculos», «La mora», «Paso diario 30»), D-94 puntos 4 a 7, 12 y 13, D-56 punto 4, D-62, D-63, D-42, D-36.
#
# Bloqueos (docs/patrones/bloqueos.md, «Cobranza»; `FOR NO KEY UPDATE`): el paso 30 toma, por entrega y en su transacción, el invernadero de origen (`bloquear_invernadero_para_alertas`: resuelve o asegura
# alertas) y después la entrega (`OrdenTrabajo`). `reevaluar_mora` NO bloquea nada: la llama quien ya tomó el invernadero y la entrega. Los correos salen con `transaction.on_commit` (D-14, D-65).

import json
import logging
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import partial

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse

from comercial.models import AlertaComercial, Anulacion, ClausulaSuministrado, Cliente, Contrato, Entrega, LineaPago, PagoCliente, SolicitudRevision, Suministro
from comercial.servicios import asientos_comerciales, entregas
from comercial.servicios.compra_ventas import FRASE_DEL_MEDIO, texto_de_pesos
from comercial.servicios.comprobantes import Destinatario
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de, texto_de
from core.procesos import ResumenDePaso
from inventario.servicios import stock
from maestros.extensiones import Enlace
from maestros.models import Alerta
from maestros.servicios import alertas
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from produccion.models import OrdenTrabajo

logger = logging.getLogger("infoponia.cobranza")

TIPO_PAGO_EN_MORA = "comercial_pago_en_mora"  # ESTADO, GERENTE, CRITICA, origen ENTREGA (D-94 punto 6; MD-122, MD-139)
CENTAVOS = Decimal("0.01")
AVISO = Entrega.EstadoDelAviso
GERENTE = Usuario.Rol.GERENTE


# ---- cálculos (funciones puras con pruebas de tabla; `cobranza.md`, «Cálculos») ----


def dias_de_atraso(fecha_vencimiento, fecha_pago):
    """Los días entre el vencimiento y el pago: `max(0, fecha_pago − vencimiento)`. El día del vencimiento todavía se paga sin atraso (da 0)."""
    return max(0, (fecha_pago - fecha_vencimiento).days)


def indemnizacion_por_atraso(dias, por_dia):
    """`dias × por_dia`, `ROUND_HALF_UP` a dos decimales; 0 si no hay atraso. `por_dia` es la indemnización por día de la entrega (la de la cláusula vigente al vencer, D-94 punto 12). Siempre `Decimal`."""
    if dias <= 0:
        return Decimal("0.00")
    return (Decimal(dias) * Decimal(por_dia)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def total_del_cobro(lineas):
    """Σ (`monto_a_cobrar` + `indemnizacion`) de ``lineas`` (cada una con esos dos atributos). Siempre `Decimal`, nunca `float`."""
    return sum((linea.monto_a_cobrar + linea.indemnizacion for linea in lineas), Decimal("0.00"))


def por_dia_de(entrega):
    """La indemnización por día de la entrega (D-94 punto 12); si es nula (concretadas antes de COM-08a, solo datos de prueba), la de la cláusula del contrato de hoy."""
    if entrega.indemnizacion_retraso_dia is not None:
        return entrega.indemnizacion_retraso_dia
    clausula = ClausulaSuministrado.objects.filter(suministro_id=entrega.contrato_entrega_id).first()
    return clausula.indemnizacion_retraso_pago if clausula else Decimal("0.00")


# ---- la mora ----


def _correr(funcion, *argumentos):
    """Corre algo de un `on_commit` sin que una falla vuelva a quien lo disparó: el cobro o la mora ya quedaron registrados (el correo se reintenta en el paso 30)."""
    try:
        funcion(*argumentos)
    except Exception:  # noqa: BLE001
        logger.exception("Falló %s%s", funcion.__name__, argumentos)


def _solicitud_pendiente(entrega):
    """La solicitud pendiente más vieja de la entrega (postcondición d de COM-VNC-PAG) o `None`."""
    return SolicitudRevision.objects.filter(entrega_id=entrega.pk, estado_solicitud=SolicitudRevision.Estado.PENDIENTE).order_by("pk").first()


def _texto_de_la_solicitud(solicitud):
    """«discrepancia» o «queja»."""
    return "discrepancia" if solicitud.tipo_solicitud == SolicitudRevision.Tipo.DISCREPANCIA else "queja"


def reevaluar_mora(entrega, hoy, avisar_vendedor):
    """Decide la alerta «pago en mora» de ``entrega`` (D-94 punto 5): la **asegura** si está en mora y la **resuelve** si no (pagada, saldada o, después de una anulación, otra vez pendiente). Devuelve la
    alerta activa o `None`. No bloquea ni audita: la llaman el paso 30, el cobro, la anulación de un cobro y la aceptación o anulación de una resolución, con el invernadero de origen y la entrega ya bloqueados.

    La primera vez que asegura la alerta (`fecha_aviso_mora` nula) carga la fecha y programa el correo al cliente (`on_commit`): el correo sale una sola vez (regla 3 de COM-VNC-PAG). Con ``avisar_vendedor``,
    el aviso al Vendedor del contrato si su cuenta está activa. Con el invernadero dado de baja la API no crea la alerta (`None`) y el aviso y el correo salen igual."""
    estado = entregas.estado_de_pago([entrega.pk], hoy)[entrega.pk]
    clave = f"entrega:{entrega.pk}"
    if estado != "en_mora":
        alertas.resolver_alerta_de_estado(entrega.invernadero_id, TIPO_PAGO_EN_MORA, clave=clave)
        return None
    contrato = Suministro.objects.select_related("cliente").get(pk=entrega.contrato_entrega_id)
    monto = entregas.monto_a_cobrar([entrega.pk])[entrega.pk]
    por_dia = por_dia_de(entrega)
    pendiente = _solicitud_pendiente(entrega)
    descripcion = f"{entrega.codigo} · {contrato.cliente.nombre_visible} · {contrato.codigo} · {texto_de_pesos(monto)} · venció el {entrega.fecha_vencimiento_pago:%d/%m} · {texto_de_pesos(por_dia)} por día de atraso"
    if pendiente is not None:
        descripcion += f" · Tiene una {_texto_de_la_solicitud(pendiente)} pendiente ({pendiente.codigo})"
    alerta = alertas.asegurar_alerta_de_estado(entrega.invernadero_id, TIPO_PAGO_EN_MORA, clave=clave, descripcion=descripcion)
    if alerta is not None:
        AlertaComercial.objects.get_or_create(alerta=alerta, defaults={"entrega_id": entrega.pk})
    if entrega.fecha_aviso_mora is None:
        aviso = AVISO.PENDIENTE_ENVIO if contrato.cliente.email_cliente else AVISO.SIN_CORREO
        Entrega.objects.filter(pk=entrega.pk).update(fecha_aviso_mora=hoy, estado_aviso_mora=aviso)
        entrega.fecha_aviso_mora, entrega.estado_aviso_mora = hoy, aviso
        if aviso == AVISO.PENDIENTE_ENVIO:
            transaction.on_commit(partial(_correr, enviar_aviso_de_mora, entrega.pk))
    if avisar_vendedor:
        vendedor = entregas._usuario_activo(contrato.vendedor_id)
        if vendedor is not None:
            detalle = (
                f"{contrato.cliente.nombre_visible} no pagó {entrega.codigo} ({contrato.codigo}): {texto_de_pesos(monto)}, venció el {entrega.fecha_vencimiento_pago:%d/%m}. "
                f"Desde hoy suma {texto_de_pesos(por_dia)} por día de atraso."
            )
            if pendiente is not None:
                detalle += f" Tiene una {_texto_de_la_solicitud(pendiente)} pendiente."
            notificaciones.notificar(vendedor, entregas._acotar(f"{entrega.codigo} en mora", notificaciones.LARGO_TITULO), entregas._acotar(detalle, notificaciones.LARGO_DETALLE))
    return alerta


def contexto_del_aviso_de_mora(entrega_id):
    """Lo que dice el correo de mora (postcondiciones c y d de COM-VNC-PAG): la entrega, el contrato, el monto a cobrar, el vencimiento, la indemnización por día y, si la hay, la solicitud que revisa la empresa."""
    entrega = Entrega.objects.get(pk=entrega_id)
    contrato = Suministro.objects.select_related("cliente", "vendedor").get(pk=entrega.contrato_entrega_id)
    pendiente = _solicitud_pendiente(entrega)
    return {
        "cliente": contrato.cliente.nombre_visible,
        "entrega": entrega.codigo,
        "fecha_entrega": entrega.fecha_resolucion_orden,
        "contrato": contrato.codigo,
        "monto": entregas.monto_a_cobrar([entrega.pk])[entrega.pk],
        "vencimiento": entrega.fecha_vencimiento_pago,
        "por_dia": por_dia_de(entrega),
        "solicitud": pendiente.codigo if pendiente is not None else "",
        "tipo_de_solicitud": _texto_de_la_solicitud(pendiente) if pendiente is not None else "",
        "vendedor": contrato.vendedor,
    }


def enviar_aviso_de_mora(entrega_id):
    """El correo de mora al cliente (D-94 punto 13; tipo `aviso_mora`). Se llama SIEMPRE fuera de una transacción (D-14). Solo sale desde «pendiente de envío»: sin el correo del sistema o si el envío falla,
    queda «pendiente» (lo reintenta el paso 30); si sale, «enviado». Devuelve `True` si salió."""
    entrega = Entrega.objects.filter(pk=entrega_id).first()
    if entrega is None or entrega.estado_aviso_mora != AVISO.PENDIENTE_ENVIO:
        return False
    cliente = Suministro.objects.select_related("cliente").get(pk=entrega.contrato_entrega_id).cliente
    if not cliente.email_cliente or not correo.correo_configurado():
        return False
    salio = correo.enviar_correo(
        Destinatario(cliente.pk, cliente.email_cliente), f"Pago en mora de la entrega {entrega.codigo}", "comercial/correos/aviso_mora.txt", contexto_del_aviso_de_mora(entrega.pk)
    )
    if salio:
        Entrega.objects.filter(pk=entrega.pk, estado_aviso_mora=AVISO.PENDIENTE_ENVIO).update(estado_aviso_mora=AVISO.ENVIADO)
    return salio


def enlaces_de_alertas(usuario, alertas_de_mora):
    """`registrar_enlace_de_alerta` para `comercial_pago_en_mora` (D-62, sección 8 de `docs/api/alertas.md`; 1a de COM-REG-CBR): solo el Gerente la recibe; lleva a «Registrar cobro» con la entrega ya elegida,
    con el detalle «En mora desde el 19/11 · 4 días · $ 1.200,00 por atraso», calculado al mostrarlo (regla 3 de COM-VNC-PAG). Una consulta para toda la lista."""
    alertas_de_mora = list(alertas_de_mora)
    if not alertas_de_mora or rol_de(usuario) != GERENTE:
        return {}
    hoy = stock.hoy()
    vinculos = list(AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_de_mora], entrega__isnull=False).select_related("entrega"))
    sin_dato = [v.entrega.contrato_entrega_id for v in vinculos if v.entrega.indemnizacion_retraso_dia is None]
    clausulas = {c.suministro_id: c.indemnizacion_retraso_pago for c in ClausulaSuministrado.objects.filter(suministro_id__in=sin_dato)} if sin_dato else {}
    resultado = {}
    for v in vinculos:
        e = v.entrega
        dias = dias_de_atraso(e.fecha_vencimiento_pago, hoy)
        por_dia = e.indemnizacion_retraso_dia if e.indemnizacion_retraso_dia is not None else clausulas.get(e.contrato_entrega_id, Decimal("0.00"))
        desde = e.fecha_vencimiento_pago + timedelta(days=1)  # la mora empieza al día siguiente del vencimiento
        resultado[v.alerta_id] = Enlace(
            f"{reverse('comercial:cobranza_registrar')}?entrega={e.pk}",
            f"En mora desde el {desde:%d/%m} · {dias} {'día' if dias == 1 else 'días'} · {texto_de_pesos(indemnizacion_por_atraso(dias, por_dia))} por atraso",
        )
    return resultado


# ---- el paso diario 30 (COM-VNC-PAG; D-94 punto 7) ----


def _candidatas(hoy):
    """`[(id, invernadero_id)]` de las entregas de suministro concretadas, sin cobro vigente, con monto a cobrar > 0, vencidas (`fecha_vencimiento_pago < hoy`) y sin aviso de mora (reglas 1 y 6)."""
    base = (
        Entrega.objects.filter(estado_orden=OrdenTrabajo.Estado.CONCRETADA, fecha_vencimiento_pago__lt=hoy, fecha_aviso_mora__isnull=True)
        .exclude(lineas_de_pago__vigente=True)
        .order_by("pk")
        .values_list("pk", "invernadero_id")
    )
    candidatas = list(base)
    montos = entregas.monto_a_cobrar([pk for pk, _ in candidatas])
    return [(pk, inv) for pk, inv in candidatas if (montos[pk] or Decimal("0.00")) > 0]


def _vencer(entrega_id, invernadero_id, hoy):
    """Una entrega en su transacción: el invernadero de origen → la entrega; relee (sigue vencida, sin pagar, con monto > 0 y sin aviso); `reevaluar_mora` con el aviso al Vendedor; la auditoría
    `vencimiento_pago` sin usuario (origen InfoPonia). Devuelve `1` si creó la alerta, `0` si no (ya no correspondía o el invernadero está dado de baja)."""
    with transaction.atomic():
        bloquear_invernadero_para_alertas(invernadero_id)
        _bloquear_entrega_del_paso(entrega_id)
        entrega = Entrega.objects.filter(pk=entrega_id).first()
        if entrega is None or entrega.fecha_aviso_mora is not None:
            return 0
        estado = entregas.estado_de_pago([entrega.pk], hoy)[entrega.pk]
        if estado != "en_mora":
            return 0
        alerta = reevaluar_mora(entrega, hoy, True)
        entrega.refresh_from_db()
        RegistroAuditoria.objects.registrar(
            usuario=None,
            accion=RegistroAuditoria.Accion.VENCIMIENTO_PAGO,
            afectados=[entrega] + ([alerta] if alerta is not None else []),
            detalle={
                "cambios": {
                    "fecha_aviso_mora": {"antes": None, "despues": hoy.isoformat()},
                    "estado_aviso_mora": {"antes": None, "despues": entrega.estado_aviso_mora},
                },
                "datos": {
                    "entrega": referencia(entrega),
                    "alerta": referencia(alerta) if alerta is not None else None,
                    "monto_a_cobrar": str(entregas.monto_a_cobrar([entrega.pk])[entrega.pk]),
                    "indemnizacion_por_dia": str(por_dia_de(entrega)),
                },
            },
        )
        return 1 if alerta is not None else 0


def vencer_pagos(hoy):
    """Paso diario 30, «Vencer pagos de suministro» (COM-VNC-PAG; D-94 punto 7). Parte 1: cada entrega que entra en mora, en su transacción (si una falla, `logger.exception` y sigue). Parte 2: los correos
    de mora que quedaron pendientes de entregas que siguen en mora (regla 4), fuera de transacción. Idempotente (reglas 2 y 3): la parte 1 solo toma las que no tienen `fecha_aviso_mora`.
    `ResumenDePaso(procesados=entregas revisadas, creados=alertas creadas, resueltos=0, detalle="N correos de mora pendientes")`."""
    candidatas = _candidatas(hoy)
    creadas = 0
    for entrega_id, invernadero_id in candidatas:
        try:
            creadas += _vencer(entrega_id, invernadero_id, hoy)
        except Exception:  # noqa: BLE001 - una entrega rota no puede frenar a las demás (D-56 punto 4)
            logger.exception("Falló el vencimiento del pago de la entrega %s", entrega_id)
    pendientes = list(Entrega.objects.filter(estado_aviso_mora=AVISO.PENDIENTE_ENVIO).order_by("pk").values_list("pk", flat=True))
    estados = entregas.estado_de_pago(pendientes, hoy)
    todavia = [pk for pk in pendientes if estados[pk] == "en_mora"]
    sin_enviar = 0
    for pk in todavia:
        if not _correr_y_decir(enviar_aviso_de_mora, pk):
            sin_enviar += 1
    return ResumenDePaso(procesados=len(candidatas), creados=creadas, resueltos=0, detalle=f"{sin_enviar} correos de mora pendientes")


def _correr_y_decir(funcion, *argumentos):
    """Como `_correr`, pero devuelve si salió (`False` si falló)."""
    try:
        return funcion(*argumentos)
    except Exception:  # noqa: BLE001
        logger.exception("Falló %s%s", funcion.__name__, argumentos)
        return False


# ---- por cobrar y registrar el cobro (COM-REG-CBR; COM-08a, paso 5) ----

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
VENDEDOR = Usuario.Rol.VENDEDOR
MEDIOS = PagoCliente.Medio.values
POR_PAGINA = 50
TIPO_NO_RECONOCIDA = "comercial_entrega_no_reconocida"  # la alerta de COM-06b (`confirmacion.TIPO_NO_RECONOCIDA`; acá como texto para no importar `confirmacion`)

SolicitudPendiente = namedtuple("SolicitudPendiente", "codigo tipo fecha")
ListaDeCobros = namedtuple("ListaDeCobros", "pagina filas")
FilaDeCobro = namedtuple("FilaDeCobro", "pago_id codigo fecha cliente cliente_id entregas medio monto atraso estado estado_texto")
LineaDeLaFicha = namedtuple("LineaDeLaFicha", "entrega_id codigo contrato_codigo fecha_concrecion vencimiento monto_total monto_cobrado dias_atraso indemnizacion")
FichaDeCobro = namedtuple(
    "FichaDeCobro", "pago codigo cliente fecha medio estado usuario base indemnizacion total lineas aviso puede_reenviar puede_imprimir anulacion cobro_correcto puede_anular puede_registrar_correcto asiento contraasiento"
)


@dataclass
class DatosDeCobro:
    """Lo que carga la persona (pasos 3 a 7 de COM-REG-CBR), tal cual llega del formulario: el cliente, las entregas elegidas y el medio de pago (D-94 punto 8; `anulacion_id` y `usar_fecha_anulada`, de COM-08b)."""

    cliente_id: object = None
    entrega_ids: list = field(default_factory=list)
    medio_pago: str = ""
    anulacion_id: object = None  # COM-08b, 7a de COM-ANL-CBR: la anulación del cobro que este cobro corrige
    usar_fecha_anulada: bool = False  # 7a: la casilla «Usar la fecha del cobro anulado»


@dataclass
class FiltrosDeCobranza:
    """Los filtros de «Entregas que paga» (Lista de tecnología, 4): el contrato y el estado de pago («pendiente» o «en_mora»; vacío = los dos)."""

    contrato_id: object = None
    estado: str = ""


@dataclass
class FiltrosDeCobros:
    """Los filtros de «Cobros registrados»: el estado («vigente» o «anulado») y el cliente."""

    estado: str = ""
    cliente_id: object = None


@dataclass(frozen=True)
class EntregaCobrable:
    """Una entrega de suministro que se puede cobrar, con todo lo que muestra el paso 4 y la indemnización por atraso a la fecha del pago (paso 6)."""

    entrega_id: int
    codigo: str
    contrato_id: int
    contrato_codigo: str
    cliente_id: int
    cliente: str
    fecha_concrecion: object
    invernadero: object
    monto_total: Decimal
    descontado: Decimal
    monto_a_cobrar: Decimal
    vencimiento: object
    estado: str
    dias_de_atraso: int
    indemnizacion: Decimal
    solicitudes_pendientes: tuple
    no_reconocida: bool
    cuando: str = ""  # el vencimiento dicho como el prototipo: «hace 3 días», «hoy», «en 5 días»


@dataclass
class ClienteConDeuda:
    """Un grupo de «Por cobrar» (paso 2): el cliente, la cantidad de entregas sin pagar, cuántas en mora, el total a cobrar, el total en mora y las entregas."""

    cliente_id: int
    cliente: str
    cantidad: int
    en_mora: int
    total: Decimal
    total_en_mora: Decimal
    entregas: list


@dataclass
class ResumenDeCobro:
    """El paso 8: el cliente, las entregas elegidas con su monto a cobrar y su indemnización, los totales, el medio, la fecha del pago (la actual), los errores por campo y la huella (D-94 punto 9). No escribe nada."""

    cliente: object
    lineas: list
    base: Decimal
    indemnizacion: Decimal
    total: Decimal
    medio_pago: str
    fecha_pago: object
    errores: dict
    hay_pendientes: bool
    huella: str
    asiento: list = field(default_factory=list)  # CON-04d: las líneas del asiento que se registrará (decisión (3) del 26/11/2026); vacío si el medio todavía no se eligió

    @property
    def hay_errores(self):
        return bool(self.errores)


def _rechazar(codigo, mensaje, campo="__all__", params=None):
    """Un `ValidationError` con código estable (patrón de `comercial`; el extracto lo llama `ErrorComercial`)."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo, params=params)]})


def _exigir_rol(actor):
    """El Gerente o el Vendedor con la cuenta activa; cualquier otro: `PermissionDenied` (`sin_permiso`)."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) not in (GERENTE, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _fecha(fecha):
    return f"{fecha:%d/%m/%Y}"


def _enumerar(piezas):
    """«a», «a y b», «a, b y c»."""
    piezas = list(piezas)
    return piezas[0] if len(piezas) == 1 else f"{', '.join(piezas[:-1])} y {piezas[-1]}"


def _ya_pagada(entrega, cobro_):
    """10a y 1a1: la entrega ya tiene un cobro vigente: con el cobro, su fecha y quién lo registró."""
    return _rechazar(
        "entrega_ya_pagada",
        f"{entrega.codigo} ya está pagada: {cobro_.codigo}, el {_fecha(cobro_.fecha)}, registrado por {cobro_.quien or 'InfoPonia'}.",
        params={"codigo_entrega": entrega.codigo, "cobro": cobro_.codigo, "fecha": _fecha(cobro_.fecha), "quien": cobro_.quien or "InfoPonia"},
    )


def _armar_filas(lista, hoy, fecha_pago):
    """`EntregaCobrable` de cada entrega de ``lista`` (con `contrato_entrega__cliente` e `invernadero` ya cargados), con una consulta por tabla para toda la lista (requisito especial: 2 segundos): lo
    descontado (solicitudes aceptadas), las solicitudes pendientes y las alertas «entrega no reconocida». Incluye las de monto a cobrar 0: quien llama las filtra."""
    ids = [e.pk for e in lista]
    if not ids:
        return []
    descontado = dict(
        SolicitudRevision.objects.filter(entrega_id__in=ids, estado_solicitud=SolicitudRevision.Estado.ACEPTADA).values("entrega_id").annotate(total=Sum("monto_descontado")).values_list("entrega_id", "total")
    )
    pendientes = {}
    for s in SolicitudRevision.objects.filter(entrega_id__in=ids, estado_solicitud=SolicitudRevision.Estado.PENDIENTE).order_by("pk"):
        pendientes.setdefault(s.entrega_id, []).append(SolicitudPendiente(s.codigo, s.tipo_solicitud, s.fecha_solicitud))
    no_reconocidas = set(
        AlertaComercial.objects.filter(entrega_id__in=ids, alerta__tipo_alerta=TIPO_NO_RECONOCIDA, alerta__estado_alerta="activa").values_list("entrega_id", flat=True)
    )
    sin_dato = {e.contrato_entrega_id for e in lista if e.indemnizacion_retraso_dia is None}
    clausulas = {c.suministro_id: c.indemnizacion_retraso_pago for c in ClausulaSuministrado.objects.filter(suministro_id__in=sin_dato)} if sin_dato else {}
    filas = []
    for e in lista:
        total = e.monto_total_entrega or Decimal("0.00")
        desc = descontado.get(e.pk) or Decimal("0.00")
        a_cobrar = max(Decimal("0.00"), total - desc)
        por_dia = e.indemnizacion_retraso_dia if e.indemnizacion_retraso_dia is not None else clausulas.get(e.contrato_entrega_id, Decimal("0.00"))
        dias = dias_de_atraso(e.fecha_vencimiento_pago, fecha_pago)
        contrato = e.contrato_entrega
        filas.append(
            EntregaCobrable(
                entrega_id=e.pk,
                codigo=e.codigo,
                contrato_id=e.contrato_entrega_id,
                contrato_codigo=contrato.codigo,
                cliente_id=contrato.cliente_id,
                cliente=contrato.cliente.nombre_visible,
                fecha_concrecion=e.fecha_resolucion_orden,
                invernadero=e.invernadero,
                monto_total=total,
                descontado=desc,
                monto_a_cobrar=a_cobrar,
                vencimiento=e.fecha_vencimiento_pago,
                estado=entregas._estado_de_pago(e.fecha_vencimiento_pago, hoy),
                dias_de_atraso=dias,
                indemnizacion=indemnizacion_por_atraso(dias, por_dia),
                solicitudes_pendientes=tuple(pendientes.get(e.pk, ())),
                no_reconocida=e.pk in no_reconocidas,
                cuando=entregas._cuando(e.fecha_vencimiento_pago, hoy, False),
            )
        )
    return filas


def _cobrables(actor, hoy, cliente_id=None, filtros=None, fecha_pago=None):
    """Las entregas cobrables del alcance de ``actor`` (regla «Entrega cobrable»): de suministro, concretadas, sin cobro vigente y con monto a cobrar > 0, de cualquier estado del contrato y de clientes activos o
    no; por vencimiento y código (paso 4)."""
    _exigir_rol(actor)
    base = (
        Entrega.objects.en_alcance_de(actor)
        .filter(estado_orden=OrdenTrabajo.Estado.CONCRETADA, fecha_vencimiento_pago__isnull=False)
        .exclude(lineas_de_pago__vigente=True)
        .select_related("contrato_entrega__cliente", "invernadero")
        .order_by("fecha_vencimiento_pago", "numero")
    )
    if cliente_id is not None:
        base = base.filter(contrato_entrega__cliente_id=cliente_id)
    if filtros is not None and filtros.contrato_id:
        base = base.filter(contrato_entrega_id=filtros.contrato_id)
    filas = [f for f in _armar_filas(list(base), hoy, fecha_pago or hoy) if f.monto_a_cobrar > 0]
    if filtros is not None and filtros.estado in ("pendiente", "en_mora"):
        filas = [f for f in filas if f.estado == filtros.estado]
    return filas


def clientes_con_deuda(actor, hoy):
    """Paso 2 de COM-REG-CBR (`tabCobranza` y `cobGroups`): por cliente, la cantidad de entregas sin pagar, cuántas están en mora, el total a cobrar y el total en mora, con sus entregas; de la A a la Z. El Gerente ve
    todas; el Vendedor, las de sus contratos (D-28); los demás roles, `PermissionDenied`. Sin consultas por fila."""
    grupos = {}
    for fila in _cobrables(actor, hoy):
        g = grupos.setdefault(fila.cliente_id, ClienteConDeuda(fila.cliente_id, fila.cliente, 0, 0, Decimal("0.00"), Decimal("0.00"), []))
        g.cantidad += 1
        g.total += fila.monto_a_cobrar
        if fila.estado == "en_mora":
            g.en_mora += 1
            g.total_en_mora += fila.monto_a_cobrar
        g.entregas.append(fila)
    return sorted(grupos.values(), key=lambda g: (g.cliente.casefold(), g.cliente_id))


def entregas_cobrables(actor, cliente_id, hoy, filtros=None, fecha_pago=None):
    """Pasos 4 y 6 (y 3a): las entregas que el actor puede cobrar a ese cliente, de la fecha de vencimiento más antigua a la más reciente, con la indemnización por atraso a ``fecha_pago`` (por omisión, hoy), las
    solicitudes pendientes y la marca de «no reconocida». Filtros: contrato y estado de pago."""
    return _cobrables(actor, hoy, cliente_id, filtros, fecha_pago)


def cliente_de_la_entrega(actor, entrega_id):
    """1a y 1a1: el cliente de la entrega de la alerta (la pantalla lo deja elegido y con esa entrega marcada). `Http404` si no existe; `PermissionDenied` si es de otro contrato; `entrega_ya_pagada` (con el cobro,
    su fecha y quién lo registró) si ya está pagada; `entrega_no_cobrable` si no es una entrega de suministro concretada."""
    _exigir_rol(actor)
    entrega = get_object_or_404(Entrega.objects.select_related("contrato_entrega"), pk=entrega_id)
    if not Entrega.objects.en_alcance_de(actor).filter(pk=entrega.pk).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    estado = entregas.estado_de_pago([entrega.pk], stock.hoy())[entrega.pk]
    if estado is None:
        raise _rechazar("entrega_no_cobrable", f"{entrega.codigo} no es una entrega de suministro concretada: no se cobra acá.")
    if estado.cobro is not None:
        raise _ya_pagada(entrega, estado.cobro)
    return entrega.contrato_entrega.cliente_id


# ---- el resumen, la huella y el registro (pasos 8 y 10) ----


def _ids_de(datos):
    """Los ids de las entregas elegidas, sin repetir y en orden (un valor que no es número se descarta)."""
    ids = set()
    for valor in datos.entrega_ids or []:
        try:
            ids.add(int(valor))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def _leer_elegidas(actor, cliente_id, ids, hoy, fecha_pago):
    """Lee las entregas elegidas y verifica, en este orden y por entrega: que exista (`entrega_no_cobrable`), que sea del alcance del actor (`PermissionDenied`), del cliente del cobro (`entregas_de_otro_cliente`), de
    suministro y concretada (`entrega_no_cobrable`), que no tenga un cobro vigente (`entrega_ya_pagada`, 10a) y que su monto a cobrar sea mayor que cero (`entrega_no_cobrable`). Devuelve las `EntregaCobrable`."""
    try:
        cliente_id = int(cliente_id)
    except (TypeError, ValueError):
        cliente_id = None
    lista = {e.pk: e for e in Entrega.objects.filter(pk__in=ids).select_related("contrato_entrega__cliente", "invernadero")}
    for entrega_id in ids:
        e = lista.get(entrega_id)
        if e is None:
            raise _rechazar("entrega_no_cobrable", "Una de las entregas elegidas no existe.")
        if rol_de(actor) == VENDEDOR and e.contrato_entrega.vendedor_id != actor.pk:
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        if e.contrato_entrega.cliente_id != cliente_id:
            raise _rechazar("entregas_de_otro_cliente", f"{e.codigo} no es del cliente del cobro: un cobro es de un solo cliente.")
        if e.estado_orden != OrdenTrabajo.Estado.CONCRETADA or e.fecha_vencimiento_pago is None:
            raise _rechazar("entrega_no_cobrable", f"{e.codigo} no es una entrega de suministro concretada: no se cobra acá.")
    estados = entregas.estado_de_pago(ids, hoy)
    for entrega_id in ids:
        if estados[entrega_id].cobro is not None:
            raise _ya_pagada(lista[entrega_id], estados[entrega_id].cobro)
    filas = _armar_filas([lista[i] for i in ids], hoy, fecha_pago)
    for fila in filas:
        if fila.monto_a_cobrar <= 0:
            raise _rechazar("entrega_no_cobrable", f"{fila.codigo} ya está saldada (su monto a cobrar es $ 0,00): no hay nada que cobrar.")
    return filas


def _huella(hoy, filas, fecha_pago=None):
    """D-94 punto 9: por cada entrega, su estado de pago, su monto a cobrar y su indemnización por atraso, más la fecha de hoy (10b: «o cambió la fecha actual») y, en 7a, la fecha del pago."""
    return json.dumps(
        {"hoy": hoy.isoformat(), "fecha_pago": (fecha_pago or hoy).isoformat(), "entregas": {str(f.entrega_id): {"estado": f.estado, "monto": str(f.monto_a_cobrar), "indemnizacion": str(f.indemnizacion), "codigo": f.codigo} for f in filas}},
        sort_keys=True,
    )


def _cambios_de_la_huella(huella_vieja, filas, hoy):
    """10b: qué cambió, por entrega: «OT-0231: monto a cobrar $ 1.000,00 → $ 800,00»; y si cambió el día. Devuelve `(cambios, cambio_la_fecha)`."""
    try:
        vieja = json.loads(huella_vieja)
        anteriores = vieja["entregas"]
        cambio_la_fecha = vieja.get("hoy") != hoy.isoformat()
    except (TypeError, ValueError, KeyError):
        return ["los datos de las entregas"], False
    cambios = []
    for f in filas:
        antes = anteriores.get(str(f.entrega_id))
        if antes is None:
            cambios.append(f"{f.codigo}: no estaba entre las elegidas")
            continue
        if Decimal(antes["monto"]) != f.monto_a_cobrar:
            cambios.append(f"{f.codigo}: monto a cobrar {texto_de_pesos(Decimal(antes['monto']))} → {texto_de_pesos(f.monto_a_cobrar)}")
        if Decimal(antes["indemnizacion"]) != f.indemnizacion:
            cambios.append(f"{f.codigo}: indemnización por atraso {texto_de_pesos(Decimal(antes['indemnizacion']))} → {texto_de_pesos(f.indemnizacion)}")
        if antes["estado"] != f.estado:
            cambios.append(f"{f.codigo}: estado de pago {antes['estado'].replace('_', ' ')} → {f.estado.replace('_', ' ')}")
    return cambios, cambio_la_fecha


def _cobro_cambio(cambios, cambio_la_fecha):
    detalle = list(cambios) + (["la fecha actual"] if cambio_la_fecha else [])
    return _rechazar(
        "cobro_cambio",
        f"Mientras armabas el cobro cambió: {'; '.join(detalle) or 'algo'}. Revisá los montos nuevos y volvé a confirmar.",
        params={"cambios": cambios, "cambio_la_fecha": cambio_la_fecha},
    )


def _fecha_de_pago(actor, datos, hoy, ids):
    """La fecha del pago y la anulación que la justifica: `(hoy, None)` o, en 7a (D-94 punto 10), `(fecha del cobro anulado, anulación)`. Fuera de ese camino, nunca una fecha anterior. Límites de 7a, todos con
    `fecha_no_admitida` salvo el último: solo el Gerente; la anulación existe y es la de un cobro con `cliente_pago_en_fecha`; la fecha no es posterior a hoy; todas las entregas elegidas son del cobro anulado; y la
    anulación se usa una sola vez (`anulacion_ya_usada`). Se llama antes de bloquear y otra vez bajo bloqueo."""
    if not datos.usar_fecha_anulada:
        return hoy, None
    no_admitida = _rechazar("fecha_no_admitida", "La fecha del cobro anulado solo se puede usar desde la anulación de ese cobro, si el cliente pagó ese día y con sus entregas.")
    if rol_de(actor) != GERENTE or not str(datos.anulacion_id or "").isdigit():
        raise no_admitida
    anulacion = Anulacion.objects.select_related("pago_cliente").filter(pk=int(datos.anulacion_id), pago_cliente__isnull=False).first()
    if anulacion is None or not anulacion.cliente_pago_en_fecha:
        raise no_admitida
    if PagoCliente.objects.filter(anulacion_corregida_id=anulacion.pk).exists():
        raise _rechazar("anulacion_ya_usada", "El cobro correcto de esa anulación ya se registró.")
    fecha = anulacion.pago_cliente.fecha_pago
    if fecha > hoy or not set(ids) <= set(anulacion.pago_cliente.lineas.values_list("entrega_id", flat=True)):
        raise no_admitida
    return fecha, anulacion


def resumen_de_cobro(actor, datos, hoy=None):
    """Paso 8 (solo lectura: no escribe ni bloquea; D-94 punto 9): valida lo elegido, calcula la indemnización por atraso de cada entrega y el total y arma la huella. Errores por campo en `errores`
    (`sin_entregas_elegidas` en `entregas` y `medio_de_pago_obligatorio` en `medio_pago`); una entrega que no se puede cobrar lanza `ValidationError` (`entrega_ya_pagada`, `entrega_no_cobrable`,
    `entregas_de_otro_cliente`) o `PermissionDenied`. La fecha del pago es la actual (en 7a, la del cobro anulado: `fecha_no_admitida` y `anulacion_ya_usada`)."""
    _exigir_rol(actor)
    hoy = hoy or stock.hoy()
    ids = _ids_de(datos)
    errores = {}
    if not ids:
        errores["entregas"] = "sin_entregas_elegidas"
    if datos.medio_pago not in MEDIOS:
        errores["medio_pago"] = "medio_de_pago_obligatorio"
    fecha_pago, _ = _fecha_de_pago(actor, datos, hoy, ids)
    lineas = _leer_elegidas(actor, datos.cliente_id, ids, hoy, fecha_pago) if ids else []
    cliente = Cliente.objects.filter(pk=datos.cliente_id).first() if str(datos.cliente_id or "").isdigit() else None
    base = sum((l.monto_a_cobrar for l in lineas), Decimal("0.00"))
    indemnizacion = sum((l.indemnizacion for l in lineas), Decimal("0.00"))
    return ResumenDeCobro(
        cliente=cliente,
        lineas=lineas,
        base=base,
        indemnizacion=indemnizacion,
        total=total_del_cobro(lineas),
        medio_pago=datos.medio_pago if datos.medio_pago in MEDIOS else "",
        fecha_pago=fecha_pago,
        errores=errores,
        hay_pendientes=any(l.solicitudes_pendientes for l in lineas),
        huella=_huella(hoy, lineas, fecha_pago),
        asiento=asientos_comerciales.filas_de(asientos_comerciales.movimientos_previstos_del_cobro(datos.medio_pago, base, indemnizacion)) if lineas and datos.medio_pago in MEDIOS else [],
    )


def _siguiente_numero():
    """El número del próximo cobro, de la secuencia ``comercial_cobro_numero_seq`` (D-94 punto 3, como `solicitudes.siguiente_numero`). Puede haber huecos si una transacción se deshace. Nunca un `max()+1`."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_cobro_numero_seq')")
        return cursor.fetchone()[0]


# Los bloqueos de «Cobranza» (docs/patrones/bloqueos.md; D-94 punto 8), en este orden: las cuentas → los invernaderos de origen → las entregas.


def _bloquear_cuentas(actor, vendedores):
    """El actor y los Vendedores de los contratos, en una consulta y en orden de id. Verifica que el actor siga activo y con su rol **después de bloquear** (`PermissionDenied`). Devuelve la cuenta del actor."""
    cuentas = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, *vendedores}).order_by("pk")}
    quien = cuentas.get(actor.pk)
    if quien is None or not quien.is_active or rol_de(quien) not in (GERENTE, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return quien


def _bloquear_invernaderos(invernadero_ids):
    """Los invernaderos de origen, activos o no, en orden de id (`bloquear_invernadero_para_alertas`: el cobro resuelve alertas)."""
    for invernadero_id in sorted(set(invernadero_ids)):
        bloquear_invernadero_para_alertas(invernadero_id)


def _bloquear_entregas(entrega_ids):
    """Las entregas (`OrdenTrabajo`), en orden de id: una aceptación y un cobro de la misma entrega quedan en fila acá y el segundo ve la huella cambiada."""
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=list(entrega_ids)).order_by("pk"))


def _bloquear_entrega_del_paso(entrega_id):
    """El paso 30 toma, por entrega, su entrega (después del invernadero de origen, que ya tiene)."""
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega_id))


def registrar_cobro(actor, datos, huella, hoy=None):
    """Paso 10 de COM-REG-CBR (y 10a, 10b): registra el cobro en UNA transacción (garantía mínima 1) y devuelve el `PagoCliente`.

    Antes de bloquear valida lo que no depende de las filas (`sin_entregas_elegidas`, `medio_de_pago_obligatorio`). Bloqueos (D-94 punto 8): las cuentas → los invernaderos de origen → las entregas. Después relee y
    verifica (`PermissionDenied`, `entregas_de_otro_cliente`, `entrega_no_cobrable`, `entrega_ya_pagada` y la huella: `cobro_cambio`). Con todo verificado: el pago (con su número de la secuencia), una línea por entrega,
    `reevaluar_mora` de cada una (resuelve su alerta), el aviso a cada Vendedor si cobró el Gerente (D-42), la auditoría `registro_cobro` y, con `on_commit`, el comprobante al cliente. No crea el asiento (D-57)
    ni toca la entrega, el contrato, el contador de incumplimientos ni la bitácora."""
    _exigir_rol(actor)
    hoy = hoy or stock.hoy()
    ids = _ids_de(datos)
    if not ids:
        raise _rechazar("sin_entregas_elegidas", "Elegí al menos una entrega para cobrar.", campo="entregas")
    if datos.medio_pago not in MEDIOS:
        raise _rechazar("medio_de_pago_obligatorio", "Elegí el medio de pago.", campo="medio_pago")
    _fecha_de_pago(actor, datos, hoy, ids)  # 7a: lo que no depende de las filas, antes de bloquear
    previas = list(Entrega.objects.filter(pk__in=ids).values_list("pk", "invernadero_id", "contrato_entrega_id"))
    if len(previas) != len(ids):
        raise _rechazar("entrega_no_cobrable", "Una de las entregas elegidas no existe.")
    vendedores = set(Contrato.objects.filter(pk__in={c for _, _, c in previas}).values_list("vendedor_id", flat=True))
    with transaction.atomic():
        quien = _bloquear_cuentas(actor, vendedores)
        _bloquear_invernaderos([i for _, i, _ in previas])
        _bloquear_entregas(ids)
        fecha_pago, anulacion = _fecha_de_pago(quien, datos, hoy, ids)  # 7a otra vez, bajo bloqueo: la anulación pudo usarse mientras esperaba
        filas = _leer_elegidas(quien, datos.cliente_id, ids, hoy, fecha_pago)
        if _huella(hoy, filas, fecha_pago) != huella:
            cambios, cambio_la_fecha = _cambios_de_la_huella(huella, filas, hoy)
            raise _cobro_cambio(cambios, cambio_la_fecha)
        return _registrar(quien, datos, filas, hoy, fecha_pago, anulacion)


def _registrar(quien, datos, filas, hoy, fecha_pago=None, anulacion=None):
    """Con todo bloqueado y verificado: el pago, las líneas, la mora, los avisos, la auditoría y el comprobante (`on_commit`). ``fecha_pago`` y ``anulacion`` son los de 7a (COM-08b; D-94 punto 10)."""
    fecha_pago = fecha_pago or hoy
    cliente = Cliente.objects.get(pk=int(datos.cliente_id))
    base = sum((f.monto_a_cobrar for f in filas), Decimal("0.00"))
    atraso = sum((f.indemnizacion for f in filas), Decimal("0.00"))
    aviso = PagoCliente.EstadoDelAviso.PENDIENTE_ENVIO if cliente.email_cliente else PagoCliente.EstadoDelAviso.SIN_CORREO
    try:
        with transaction.atomic():  # la unicidad de `anulacion_corregida` respalda al chequeo de `_fecha_de_pago`
            pago = PagoCliente.objects.create(
                tipo_pago=PagoCliente.Tipo.SUMINISTRO, numero=_siguiente_numero(), cliente=cliente, medio_pago=datos.medio_pago, fecha_pago=fecha_pago, monto_pagado=base + atraso,
                estado_pago=PagoCliente.Estado.VIGENTE, usuario=quien, estado_aviso_cliente=aviso, anulacion_corregida=anulacion,
            )
    except IntegrityError as error:
        raise _rechazar("anulacion_ya_usada", "El cobro correcto de esa anulación ya se registró.") from error
    lineas = [
        LineaPago.objects.create(pago=pago, entrega_id=f.entrega_id, monto_cobrado=f.monto_a_cobrar, dias_atraso=f.dias_de_atraso, indemnizacion_atraso=f.indemnizacion, vigente=True) for f in filas
    ]
    ids = [f.entrega_id for f in filas]
    previas = list(Alerta.objects.filter(vinculo_comercial__entrega_id__in=ids, tipo_alerta=TIPO_PAGO_EN_MORA, estado_alerta="activa").order_by("pk"))
    for entrega in Entrega.objects.filter(pk__in=ids).order_by("pk"):
        reevaluar_mora(entrega, hoy, False)  # resuelve su alerta «pago en mora» (postcondición e)
    resueltas = list(Alerta.objects.filter(pk__in=[a.pk for a in previas], estado_alerta="resuelta").order_by("pk"))
    if quien.pk is not None and rol_de(quien) == GERENTE:
        _avisar_a_los_vendedores(pago, cliente, filas)
    asiento = asientos_comerciales.asentar_cobro(quien, pago, lineas, hoy)  # postcondición d (CON-04d): después de todos los bloqueos; el ejercicio va último (D-86)
    RegistroAuditoria.objects.registrar(
        usuario=quien,
        accion=RegistroAuditoria.Accion.REGISTRO_COBRO,
        afectados=[pago, *lineas, *resueltas, *([asiento] if asiento is not None else [])],
        detalle={
            "cambios": {
                "medio_pago": {"antes": None, "despues": pago.medio_pago},
                "fecha_pago": {"antes": None, "despues": fecha_pago.isoformat()},
                "monto_pagado": {"antes": None, "despues": str(pago.monto_pagado)},
                "estado_aviso_cliente": {"antes": None, "despues": aviso},
            },
            "datos": {
                "numero_cobro": pago.codigo,
                "cliente": referencia(cliente),
                "indemnizacion_atraso_total": str(atraso),
                "detalle_de_entregas": [f"{f.codigo}: {f.monto_a_cobrar} + {f.indemnizacion} de atraso ({f.dias_de_atraso} días)" for f in filas],
                "alertas_resueltas": [str(a) for a in resueltas],
                **({"asientos": [str(asiento)]} if asiento is not None else {}),
                **({"anulacion_corregida": referencia(anulacion)} if anulacion is not None else {}),
            },
        },
    )
    if aviso == PagoCliente.EstadoDelAviso.PENDIENTE_ENVIO:
        transaction.on_commit(partial(_correr, enviar_comprobante_de_cobro, pago.pk))
    return pago


def _avisar_a_los_vendedores(pago, cliente, filas):
    """Postcondición f (D-42, dentro de la transacción): «COB-0032 registrado» a cada Vendedor activo de los contratos, con sus entregas, lo que suman y, si lo hubo, el atraso."""
    por_vendedor = {}
    for f in filas:
        por_vendedor.setdefault(Contrato.objects.get(pk=f.contrato_id).vendedor_id, []).append(f)
    medio = FRASE_DEL_MEDIO[pago.medio_pago]
    for vendedor_id, suyas in sorted(por_vendedor.items()):
        vendedor = entregas._usuario_activo(vendedor_id)
        if vendedor is None:
            continue
        por_contrato = {}
        for f in suyas:
            por_contrato.setdefault(f.contrato_codigo, []).append(f.codigo)
        total = sum((f.monto_a_cobrar + f.indemnizacion for f in suyas), Decimal("0.00"))
        atraso = sum((f.indemnizacion for f in suyas), Decimal("0.00"))
        lista = ", ".join(f"{_enumerar(codigos)} ({contrato})" for contrato, codigos in por_contrato.items())
        detalle = f"El Gerente registró el cobro de {cliente.nombre_visible}: {lista}, {texto_de_pesos(total)} {medio}"
        detalle += f", con {texto_de_pesos(atraso)} de atraso." if atraso > 0 else "."
        notificaciones.notificar(vendedor, entregas._acotar(f"{pago.codigo} registrado", notificaciones.LARGO_TITULO), entregas._acotar(detalle, notificaciones.LARGO_DETALLE))


# ---- el comprobante de cobro (D-94 punto 13; 11 y 11a de COM-REG-CBR) ----


def contexto_del_comprobante_de_cobro(pago_id):
    """Lo que dice el comprobante de cobro (Lista de tecnología, 11): el cliente, el código, la fecha y el medio; por entrega, su fecha, el contrato, el monto total, lo descontado, el monto a cobrar, el vencimiento y,
    si hubo atraso, los días y la indemnización; y el total cobrado. De uso interno, sin validez fiscal. Lo usan el correo y la página para imprimir."""
    pago = PagoCliente.objects.select_related("cliente", "usuario").get(pk=pago_id)
    lineas = []
    for l in pago.lineas.select_related("entrega__contrato_entrega").order_by("entrega__numero"):
        e = l.entrega
        lineas.append(
            {
                "entrega": e.codigo,
                "contrato": e.contrato_entrega.codigo,
                "fecha_concrecion": e.fecha_resolucion_orden,
                "monto_total": e.monto_total_entrega,
                "descontado": max(Decimal("0.00"), e.monto_total_entrega - l.monto_cobrado),
                "monto_a_cobrar": l.monto_cobrado,
                "vencimiento": e.fecha_vencimiento_pago,
                "dias_atraso": l.dias_atraso,
                "indemnizacion": l.indemnizacion_atraso,
            }
        )
    return {
        "cliente": pago.cliente.nombre_visible,
        "codigo": pago.codigo,
        "fecha": pago.fecha_pago,
        "medio": pago.get_medio_pago_display(),
        "lineas": lineas,
        "base": sum((l["monto_a_cobrar"] for l in lineas), Decimal("0.00")),
        "indemnizacion": sum((l["indemnizacion"] for l in lineas), Decimal("0.00")),
        "total": pago.monto_pagado,
    }


def enviar_comprobante_de_cobro(pago_id):
    """El correo al cliente con el comprobante de cobro. Se llama SIEMPRE fuera de una transacción (D-14). Solo sale desde «pendiente de envío»: sin el correo del sistema configurado o si el envío falla, queda
    «pendiente» (lo reintenta el paso 50, parte 4); si sale, «enviado». Devuelve `True` si salió."""
    pago = PagoCliente.objects.select_related("cliente").filter(pk=pago_id, tipo_pago=PagoCliente.Tipo.SUMINISTRO).first()
    if pago is None or pago.estado_aviso_cliente != PagoCliente.EstadoDelAviso.PENDIENTE_ENVIO:
        return False
    cliente = pago.cliente
    if not cliente.email_cliente or not correo.correo_configurado():
        return False
    salio = correo.enviar_correo(
        Destinatario(cliente.pk, cliente.email_cliente), f"Comprobante de cobro {pago.codigo}", "comercial/correos/comprobante_de_cobro.txt", contexto_del_comprobante_de_cobro(pago.pk)
    )
    if salio:
        PagoCliente.objects.filter(pk=pago.pk, estado_aviso_cliente=PagoCliente.EstadoDelAviso.PENDIENTE_ENVIO).update(estado_aviso_cliente=PagoCliente.EstadoDelAviso.ENVIADO)
    return salio


def _pago_del_alcance(actor, pago_id):
    """El cobro de suministro del alcance del actor: `Http404` si no existe o es de una compra-venta (su pago se ve en la ficha de la venta); `PermissionDenied` si ninguna de sus entregas es de su alcance."""
    _exigir_rol(actor)
    pago = get_object_or_404(PagoCliente.objects.select_related("cliente", "usuario"), pk=pago_id, tipo_pago=PagoCliente.Tipo.SUMINISTRO)
    if rol_de(actor) == VENDEDOR and not LineaPago.objects.filter(pago_id=pago.pk, entrega__in=Entrega.objects.en_alcance_de(actor)).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return pago


def reenviar_comprobante_de_cobro(actor, pago_id):
    """«Reenviar comprobante» (11a): el Vendedor del contrato o el Gerente, solo si el comprobante está «pendiente de envío». Sin auditoría (no cambia datos de negocio). Devuelve si salió. Errores:
    `comprobante_no_pendiente` y `cliente_sin_correo`. Fuera de una transacción (D-14)."""
    pago = _pago_del_alcance(actor, pago_id)
    if pago.estado_aviso_cliente != PagoCliente.EstadoDelAviso.PENDIENTE_ENVIO:
        raise _rechazar("comprobante_no_pendiente", "El comprobante de este cobro no está pendiente de envío.")
    if not pago.cliente.email_cliente:
        raise _rechazar("cliente_sin_correo", "El cliente no tiene correo: el comprobante se entrega impreso.")
    return enviar_comprobante_de_cobro(pago.pk)


# ---- «Cobros registrados» y la ficha del cobro ----


def _de_suministro_del_alcance(actor):
    """Los pagos de suministro que el actor ve: el Gerente, todos; el Vendedor, los que tienen alguna entrega de sus contratos."""
    _exigir_rol(actor)
    pagos = PagoCliente.objects.filter(tipo_pago=PagoCliente.Tipo.SUMINISTRO)
    if rol_de(actor) == VENDEDOR:
        pagos = pagos.filter(pk__in=LineaPago.objects.filter(entrega__in=Entrega.objects.en_alcance_de(actor)).values("pago_id"))
    return pagos


def cobros_registrados(actor, filtros=None, pagina=1):
    """«Cobros registrados» (prototipo, `tabCobranza`): del más reciente al más viejo, de a 50: el cobro con su fecha, el cliente, las entregas, el medio, el monto con lo que incluye por atraso y el estado.
    Dos consultas para toda la página."""
    pagos = _de_suministro_del_alcance(actor).select_related("cliente").order_by("-fecha_pago", "-numero")
    if filtros is not None and filtros.estado in ("vigente", "anulado"):
        pagos = pagos.filter(estado_pago=filtros.estado)
    if filtros is not None and filtros.cliente_id:
        pagos = pagos.filter(cliente_id=filtros.cliente_id)
    pagina = Paginator(pagos, POR_PAGINA).get_page(pagina)
    lineas = {}
    for l in LineaPago.objects.filter(pago_id__in=[p.pk for p in pagina]).select_related("entrega").order_by("entrega__numero"):
        lineas.setdefault(l.pago_id, []).append(l)
    filas = [
        FilaDeCobro(
            pago_id=p.pk,
            codigo=p.codigo,
            fecha=p.fecha_pago,
            cliente=p.cliente.nombre_visible,
            cliente_id=p.cliente_id,
            entregas=[l.entrega.codigo for l in lineas.get(p.pk, [])],
            medio=p.get_medio_pago_display(),
            monto=p.monto_pagado,
            atraso=sum((l.indemnizacion_atraso for l in lineas.get(p.pk, [])), Decimal("0.00")),
            estado=p.estado_pago,
            estado_texto=p.get_estado_pago_display(),
        )
        for p in pagina
    ]
    return ListaDeCobros(pagina, filas)


def ficha_de_cobro(actor, pago_id):
    """La ficha del cobro (no está en el prototipo): el cobro, sus entregas con lo cobrado y el atraso, y el estado del comprobante con «Reenviar» (pendiente de envío y con correo) o «Imprimir» (sin correo)."""
    pago = _pago_del_alcance(actor, pago_id)
    lineas = [
        LineaDeLaFicha(l.entrega_id, l.entrega.codigo, l.entrega.contrato_entrega.codigo, l.entrega.fecha_resolucion_orden, l.entrega.fecha_vencimiento_pago, l.entrega.monto_total_entrega, l.monto_cobrado, l.dias_atraso, l.indemnizacion_atraso)
        for l in pago.lineas.select_related("entrega__contrato_entrega").order_by("entrega__numero")
    ]
    atraso = sum((l.indemnizacion for l in lineas), Decimal("0.00"))
    es_gerente = rol_de(actor) == GERENTE
    anulacion = Anulacion.objects.select_related("usuario").filter(pago_cliente_id=pago.pk).first()  # COM-08b: la anulación (fecha, Gerente, motivo, si el cliente pagó) y el cobro que la corrigió
    cobro_correcto = PagoCliente.objects.filter(anulacion_corregida_id=anulacion.pk).first() if anulacion is not None else None
    puede_registrar_correcto = False
    if es_gerente and anulacion is not None and cobro_correcto is None:  # paso 7: «Registrar el cobro correcto», mientras queden entregas por cobrar de ese cobro
        puede_registrar_correcto = bool(anulacion_para_registrar(actor, anulacion.pk).entrega_ids)
    return FichaDeCobro(
        pago=pago,
        codigo=pago.codigo,
        cliente=pago.cliente,
        fecha=pago.fecha_pago,
        medio=pago.get_medio_pago_display(),
        estado=pago.estado_pago,
        usuario=texto_de(pago.usuario) if pago.usuario_id else "",
        base=sum((l.monto_cobrado for l in lineas), Decimal("0.00")),
        indemnizacion=atraso,
        total=pago.monto_pagado,
        lineas=lineas,
        aviso=pago.estado_aviso_cliente,
        puede_reenviar=pago.estado_aviso_cliente == PagoCliente.EstadoDelAviso.PENDIENTE_ENVIO and bool(pago.cliente.email_cliente),
        puede_imprimir=pago.estado_aviso_cliente == PagoCliente.EstadoDelAviso.SIN_CORREO,
        anulacion=anulacion,
        cobro_correcto=cobro_correcto,
        puede_anular=es_gerente and pago.estado_pago == PagoCliente.Estado.VIGENTE,
        puede_registrar_correcto=puede_registrar_correcto,
        asiento=asientos_comerciales.asiento_de(pago.pk),  # CON-04d: el asiento del cobro y, si se anuló, su contraasiento (texto, sin enlace)
        contraasiento=asientos_comerciales.asiento_de(anulacion.pk) if anulacion is not None else None,
    )


def datos_de_cobro(post):
    """`DatosDeCobro` desde un `QueryDict` (las claves `cliente`, `entrega` —varias—, `medio_pago` y, en 7a, `anulacion` y `usar_fecha_anulada`)."""
    return DatosDeCobro(
        cliente_id=(post.get("cliente") or "").strip(),
        entrega_ids=post.getlist("entrega"),
        medio_pago=(post.get("medio_pago") or "").strip(),
        anulacion_id=(post.get("anulacion") or "").strip() or None,
        usar_fecha_anulada=bool(post.get("usar_fecha_anulada")),
    )


def reevaluar_mora_con_rastro(entrega_id, hoy):
    """`reevaluar_mora(entrega, hoy, avisar_vendedor=False)` para quien audita lo que hace (la aceptación y la anulación de una resolución, COM-07a completado por COM-08a; MD-125). Devuelve
    `(alertas resueltas, alertas nuevas)` de «pago en mora» de la entrega, para ponerlas entre los afectados. Sin aviso al Vendedor: su propio aviso ya dice qué cambia. No bloquea: la llaman con el invernadero
    y la entrega ya bloqueados."""
    previas = list(Alerta.objects.filter(vinculo_comercial__entrega_id=entrega_id, tipo_alerta=TIPO_PAGO_EN_MORA, estado_alerta="activa").values_list("pk", flat=True))
    reevaluar_mora(Entrega.objects.get(pk=entrega_id), hoy, False)
    resueltas = list(Alerta.objects.filter(pk__in=previas, estado_alerta="resuelta").order_by("pk"))
    nuevas = list(Alerta.objects.filter(vinculo_comercial__entrega_id=entrega_id, tipo_alerta=TIPO_PAGO_EN_MORA, estado_alerta="activa").exclude(pk__in=previas).order_by("pk"))
    return resueltas, nuevas


PanelDeCobranza = namedtuple("PanelDeCobranza", "por_cobrar_total por_cobrar_cantidad en_mora_total en_mora_cantidad sin_confirmar")


def panel_de_cobranza(actor, hoy):
    """El grupo «Cobranza» del panel de control (`secComercial` del prototipo): «Por cobrar» (total y cantidad de entregas de suministro), «En mora» (total y cantidad) y «Sin confirmar por el cliente» (de las que se
    deben; «no afecta el cobro»), dentro del alcance del actor. `None` si no es Gerente ni Vendedor. Pocas consultas, sin consultas por fila."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) not in (GERENTE, VENDEDOR):
        return None
    filas = _cobrables(actor, hoy)
    en_mora = [f for f in filas if f.estado == "en_mora"]
    sin_confirmar = Entrega.objects.filter(pk__in=[f.entrega_id for f in filas], estado_confirmacion_cliente=Entrega.Confirmacion.NO_CONFIRMADO).count()
    return PanelDeCobranza(
        sum((f.monto_a_cobrar for f in filas), Decimal("0.00")), len(filas), sum((f.monto_a_cobrar for f in en_mora), Decimal("0.00")), len(en_mora), sin_confirmar
    )


def en_mora_para(actor, hoy):
    """El contador rojo de la pestaña «Cobranza»: las entregas en mora del alcance del actor (`None` si no es Gerente ni Vendedor)."""
    panel = panel_de_cobranza(actor, hoy)
    return None if panel is None else panel.en_mora_cantidad


# ---- anular un cobro (COM-ANL-CBR; COM-08b; D-94 puntos 5, 10 y 11) ----
# Bloqueos (docs/patrones/bloqueos.md, «Cobranza»): las cuentas (el Gerente y los Vendedores) → los invernaderos de origen → las entregas → el pago y sus líneas. Es el orden de «Registrar un cobro» más el pago.

LARGO_DEL_MOTIVO = 500
EntregaDeAnulacion = namedtuple("EntregaDeAnulacion", "entrega_id codigo contrato_codigo monto_cobrado dias_atraso indemnizacion estado_despues alerta")
DatosDeAnulacionDeCobro = namedtuple("DatosDeAnulacionDeCobro", "pago codigo cliente fecha medio monto indemnizacion entregas contraasiento huella")
AnulacionParaRegistrar = namedtuple("AnulacionParaRegistrar", "anulacion cliente_id entrega_ids usa_fecha fecha")


def _exigir_gerente(actor):
    """Solo el Gerente con la cuenta activa anula un cobro (regla «Quién anula»); cualquier otro: `PermissionDenied` (`sin_permiso`)."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _pago_para_anular(pago_id):
    """El cobro de suministro vigente que se va a anular. `Http404` si no existe; `cobro_de_compra_venta` (1a: va dentro del asiento de la entrega y se corrige con un asiento manual) y `cobro_ya_anulado` (5a)."""
    pago = get_object_or_404(PagoCliente.objects.select_related("cliente"), pk=pago_id)
    if pago.tipo_pago != PagoCliente.Tipo.SUMINISTRO:
        raise _rechazar("cobro_de_compra_venta", "Este cobro es de una compra-venta: va dentro del asiento de la entrega y se corrige con un asiento manual.")
    if pago.estado_pago != PagoCliente.Estado.VIGENTE:
        raise _rechazar("cobro_ya_anulado", f"{pago.codigo} ya está anulado: no hay nada más que anular.")
    return pago


def _lo_que_pasa(pago, hoy):
    """Las líneas del cobro con el estado en que queda cada entrega al anularlo (`pendiente` o `en_mora`, con su vencimiento guardado, MD-132) y si hay que asegurar su alerta."""
    filas = []
    for linea in pago.lineas.select_related("entrega__contrato_entrega").order_by("entrega__numero"):
        e = linea.entrega
        estado = entregas._estado_de_pago(e.fecha_vencimiento_pago, hoy)
        filas.append(
            EntregaDeAnulacion(e.pk, e.codigo, e.contrato_entrega.codigo, linea.monto_cobrado, linea.dias_atraso, linea.indemnizacion_atraso, estado, estado == "en_mora")
        )
    return filas


def _huella_de_anulacion(pago, filas, hoy):
    """Lo que cuenta entre el paso 2 y el 5: el estado del pago, cada línea con su vigencia y el estado en que quedaría la entrega, y la fecha de hoy (puede cambiar el estado en que queda cada entrega)."""
    lineas = [[l.pk, l.vigente] for l in pago.lineas.order_by("pk")]
    return json.dumps({"hoy": hoy.isoformat(), "pago": pago.estado_pago, "lineas": lineas, "despues": {str(f.entrega_id): f.estado_despues for f in filas}}, sort_keys=True)


def datos_de_anulacion_de_cobro(actor, pago_id, hoy=None):
    """Pasos 1 y 2 de COM-ANL-CBR (solo lectura): el cobro (código, cliente, fecha, medio, monto y atraso total), cada entrega con lo cobrado y el estado en que queda (`pendiente` o `en_mora`, y si se le asegura la
    alerta), el contraasiento previsto (sus líneas) y la huella. Solo el Gerente (`PermissionDenied`); `Http404`; `cobro_de_compra_venta` (1a) y `cobro_ya_anulado` (5a)."""
    _exigir_gerente(actor)
    hoy = hoy or stock.hoy()
    pago = _pago_para_anular(pago_id)
    filas = _lo_que_pasa(pago, hoy)
    return DatosDeAnulacionDeCobro(
        pago=pago,
        codigo=pago.codigo,
        cliente=pago.cliente.nombre_visible,
        fecha=pago.fecha_pago,
        medio=pago.get_medio_pago_display(),
        monto=pago.monto_pagado,
        indemnizacion=sum((f.indemnizacion for f in filas), Decimal("0.00")),
        entregas=filas,
        contraasiento=asientos_comerciales.contraasiento_previsto(pago),  # las líneas que se registrarán (o `None` si el cobro no tiene asiento: anterior a CON-04d)
        huella=_huella_de_anulacion(pago, filas, hoy),
    )


def _validar_motivo_de_anulacion(motivo):
    """Paso 3 (3a): el motivo es obligatorio, de 1 a 500 caracteres, sin espacios al borde (`motivo_obligatorio` y `motivo_largo`, en el campo `motivo`). Devuelve el motivo limpio."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise _rechazar("motivo_obligatorio", "Escribí el motivo de la anulación.", campo="motivo")
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise _rechazar("motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.", campo="motivo")
    return motivo


def _bloquear_pago_y_lineas(pago_id):
    """El pago y sus líneas, en orden de id, después de las cuentas, los invernaderos y las entregas (el último paso de los bloqueos de la anulación)."""
    list(PagoCliente.objects.select_for_update(no_key=True, of=("self",)).filter(pk=pago_id))
    list(LineaPago.objects.select_for_update(no_key=True).filter(pago_id=pago_id).order_by("pk"))


def _avisar_la_anulacion(pago, filas, motivo):
    """Paso 6 (D-42, dentro de la transacción): a cada Vendedor activo de los contratos, «COB-0032 anulado» con las entregas suyas que vuelven a estar sin pagar y el motivo."""
    por_vendedor = {}
    for f in filas:
        vendedor_id = Contrato.objects.get(pk=Entrega.objects.get(pk=f.entrega_id).contrato_entrega_id).vendedor_id
        por_vendedor.setdefault(vendedor_id, []).append(f)
    cliente = pago.cliente.nombre_visible
    for vendedor_id, suyas in sorted(por_vendedor.items()):
        vendedor = entregas._usuario_activo(vendedor_id)
        if vendedor is None:
            continue
        lista = _enumerar([f"{f.codigo} ({f.estado_despues.replace('_', ' ')})" for f in suyas])
        verbo = "Vuelven" if len(suyas) > 1 else "Vuelve"
        total = texto_de_pesos(sum((f.monto_cobrado + f.indemnizacion for f in suyas), Decimal("0.00")))
        detalle = f"El Gerente anuló el cobro de {cliente} ({total}). {verbo} a estar sin pagar: {lista}. Motivo: {motivo}"
        notificaciones.notificar(vendedor, entregas._acotar(f"{pago.codigo} anulado", notificaciones.LARGO_TITULO), entregas._acotar(detalle, notificaciones.LARGO_DETALLE))


def anular_cobro(actor, pago_id, motivo, cliente_pago_en_fecha, huella, hoy=None):
    """Paso 5 de COM-ANL-CBR (y 5a): anula el cobro en UNA transacción (garantía mínima: atómica) y devuelve la `Anulacion`.

    Antes de bloquear: solo el Gerente, el cobro de suministro vigente (`cobro_de_compra_venta`, `cobro_ya_anulado`) y el motivo (`motivo_obligatorio`, `motivo_largo`). Bloqueos (D-94 punto 8): las cuentas → los
    invernaderos de origen → las entregas → el pago y sus líneas. Relectura: sigue siendo Gerente activo, el pago sigue vigente (5a) y la huella coincide (`cambio_simultaneo`). Con todo verificado: la `Anulacion`
    (fecha de hoy, motivo, usuario, cobro y `cliente_pago_en_fecha`), el pago a «anulado» y sus líneas a `vigente = False` (no se borra nada, MD-136), `reevaluar_mora` de cada entrega (asegura la alerta si vuelve a
    «en mora»; el correo de mora solo si nunca había salido; sin aviso individual al Vendedor), el aviso a cada Vendedor y la auditoría `anulacion_cobro`. No le escribe al cliente ni crea el contraasiento (D-57)."""
    _exigir_gerente(actor)
    hoy = hoy or stock.hoy()
    _pago_para_anular(pago_id)
    motivo = _validar_motivo_de_anulacion(motivo)
    previas = list(LineaPago.objects.filter(pago_id=pago_id).values_list("entrega_id", "entrega__invernadero_id", "entrega__contrato_entrega_id"))
    vendedores = set(Contrato.objects.filter(pk__in={c for _, _, c in previas}).values_list("vendedor_id", flat=True))
    with transaction.atomic():
        quien = _bloquear_cuentas(actor, vendedores)
        if rol_de(quien) != GERENTE:
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        _bloquear_invernaderos([i for _, i, _ in previas])
        _bloquear_entregas([e for e, _, _ in previas])
        _bloquear_pago_y_lineas(pago_id)
        pago = _pago_para_anular(pago_id)  # 5a: el cobro pudo anularse mientras esperaba
        filas = _lo_que_pasa(pago, hoy)
        if _huella_de_anulacion(pago, filas, hoy) != huella:
            raise _rechazar("cambio_simultaneo", "Mientras mirabas la anulación cambió el cobro o el día. Revisá lo que pasa ahora y volvé a confirmar.")
        return _anular(quien, pago, filas, motivo, bool(cliente_pago_en_fecha), hoy)


def _anular(quien, pago, filas, motivo, cliente_pago_en_fecha, hoy):
    """Con todo bloqueado y verificado: la anulación, los estados, la mora, el aviso y la auditoría."""
    try:
        with transaction.atomic():
            anulacion = Anulacion.objects.create(fecha_anulacion=hoy, motivo_anulacion=motivo, usuario=quien, pago_cliente=pago, cliente_pago_en_fecha=cliente_pago_en_fecha)
    except IntegrityError as error:  # la unicidad del OneToOne respalda a la relectura: dos anulaciones del mismo pago
        raise _rechazar("cobro_ya_anulado", f"{pago.codigo} ya está anulado: no hay nada más que anular.") from error
    lineas = list(pago.lineas.order_by("pk"))
    PagoCliente.objects.filter(pk=pago.pk).update(estado_pago=PagoCliente.Estado.ANULADO)
    LineaPago.objects.filter(pago_id=pago.pk).update(vigente=False)
    nuevas = []
    for f in filas:
        _, creadas = reevaluar_mora_con_rastro(f.entrega_id, hoy)  # d y e: «pendiente» o «en mora»; la alerta nueva si vuelve a estar en mora
        nuevas += creadas
    _avisar_la_anulacion(pago, filas, motivo)
    contraasiento = asientos_comerciales.asentar_anulacion(quien, anulacion, pago, hoy, f"Anulación del cobro {pago.codigo}")  # postcondición c (CON-04d)
    RegistroAuditoria.objects.registrar(
        usuario=quien,
        accion=RegistroAuditoria.Accion.ANULACION_COBRO,
        afectados=[pago, anulacion, *lineas, *nuevas, *([contraasiento] if contraasiento is not None else [])],
        detalle={
            "cambios": {"estado_pago": {"antes": PagoCliente.Estado.VIGENTE, "despues": PagoCliente.Estado.ANULADO}},
            "datos": {
                "motivo_anulacion": motivo,
                "cliente_pago_en_fecha": cliente_pago_en_fecha,
                "cobro_anulado": referencia(pago),
                "entregas_que_vuelven": [f"{f.codigo}: {f.estado_despues}" for f in filas],
                "alertas_creadas": [str(a) for a in nuevas],
                **({"asientos": [str(contraasiento)]} if contraasiento is not None else {}),
            },
        },
    )
    return anulacion


def anulacion_para_registrar(actor, anulacion_id):
    """La pantalla final de la anulación y el GET de «Registrar el cobro correcto» (paso 7 y 7a; D-94 punto 10): el cliente, las entregas del cobro anulado que siguen sin cobrar, si la anulación dice que el cliente pagó
    ese día (`usa_fecha`) y esa fecha (la del cobro anulado). Solo el Gerente (`PermissionDenied`); `Http404` si no es la anulación de un cobro; `anulacion_ya_usada` si su cobro correcto ya se registró."""
    _exigir_gerente(actor)
    anulacion = get_object_or_404(Anulacion.objects.select_related("pago_cliente"), pk=anulacion_id, pago_cliente__isnull=False)
    if PagoCliente.objects.filter(anulacion_corregida_id=anulacion.pk).exists():
        raise _rechazar("anulacion_ya_usada", "El cobro correcto de esa anulación ya se registró.")
    pago = anulacion.pago_cliente
    ids = list(pago.lineas.values_list("entrega_id", flat=True))
    cobradas = set(LineaPago.objects.filter(entrega_id__in=ids, vigente=True).values_list("entrega_id", flat=True))
    return AnulacionParaRegistrar(anulacion, pago.cliente_id, sorted(i for i in ids if i not in cobradas), bool(anulacion.cliente_pago_en_fecha), pago.fecha_pago)
