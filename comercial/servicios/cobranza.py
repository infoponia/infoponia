# Cobranza de suministros de `comercial` (COM-08a; D-94): los cálculos del cobro (funciones puras), la mora (`reevaluar_mora`, la alerta «pago en mora», su enlace y el aviso al cliente) y el paso diario 30
# (COM-VNC-PAG). El cobro mismo (COM-REG-CBR) se suma en el paso 5 de la tarea.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Cálculos», «La mora», «Paso diario 30»), D-94 puntos 4 a 7, 12 y 13, D-56 punto 4, D-62, D-63, D-42, D-36.
#
# Bloqueos (docs/patrones/bloqueos.md, «Cobranza»; `FOR NO KEY UPDATE`): el paso 30 toma, por entrega y en su transacción, el invernadero de origen (`bloquear_invernadero_para_alertas`: resuelve o asegura
# alertas) y después la entrega (`OrdenTrabajo`). `reevaluar_mora` NO bloquea nada: la llama quien ya tomó el invernadero y la entrega. Los correos salen con `transaction.on_commit` (D-14, D-65).

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import partial

from django.db import transaction
from django.urls import reverse

from comercial.models import AlertaComercial, ClausulaSuministrado, Entrega, SolicitudRevision, Suministro
from comercial.servicios import entregas
from comercial.servicios.compra_ventas import texto_de_pesos
from comercial.servicios.comprobantes import Destinatario
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from core.procesos import ResumenDePaso
from inventario.servicios import stock
from maestros.extensiones import Enlace
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
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega_id))
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
