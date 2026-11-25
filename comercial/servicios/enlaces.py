# Enlace del cliente (COM-04c; D-65 y docs/patrones/enlace_del_cliente.md): crear, reemplazar, anular, encontrar por su token, decir si sirve, bloquear,
# enviar el correo y vencer (paso diario 27). El mismo mecanismo que el enlace del proveedor (`compras/servicios/enlaces.py`, D-88). La base guarda SOLO el
# resumen SHA-256 del token (`core/enlaces.py`); el token vive en memoria hasta armar la URL del correo. `crear_enlace` corre dentro de la transacción del caso
# de uso con la venta ya bloqueada; el correo sale en `on_commit` (`core.correo.enviar_correo`, D-54) y el resultado queda en `estado_envio`.
# Orden de bloqueo: el enlace va siempre al final (docs/patrones/bloqueos.md, «Cosecha y cámara»).

import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import transaction

from comercial.models import CompraVenta, DetalleReserva, DetalleVenta, EnlaceCliente, Entrega, ReservaStock
from comercial.servicios.comprobantes import Destinatario
from comercial.servicios.stock_maduro import _cubierto
from core import correo, notificaciones
from core.enlaces import nuevo_token, resumen_de
from core.models import RegistroAuditoria, Usuario
from core.procesos import ResumenDePaso
from inventario.servicios import stock
from maestros.servicios import configuracion

logger = logging.getLogger("infoponia.enlaces")

Estado = EnlaceCliente.Estado
EstadoEnvio = EnlaceCliente.EstadoEnvio
Tipo = EnlaceCliente.Tipo

# La URL pública del portal (`config/urls.py`): `/cliente/<token>/`. Se arma a mano para no depender de las vistas desde este módulo.
RUTA_PUBLICA = "/cliente/{token}/"

# Qué pasa al abrir un enlace (extensiones 2a y 6a de COM-DCD-FLT). Solo `SIRVE` deja decidir; el resto da «Este enlace no se puede usar» con su motivo.
SIRVE = "sirve"
NO_VALIDO = "no_valido"
VENCIDO = "vencido"
USADO = "usado"
REEMPLAZADO = "reemplazado"
ANULADO = "anulado"
VENTA_CANCELADA = "venta_cancelada"
SIN_PENDIENTES = "sin_pendientes"

MOTIVOS = {
    NO_VALIDO: "Este enlace no es válido.",
    VENCIDO: "El plazo para decidir terminó.",
    USADO: "Este enlace ya se usó: la decisión quedó registrada.",
    REEMPLAZADO: "Este enlace fue reemplazado por uno más nuevo.",
    ANULADO: "Este enlace fue anulado.",
    VENTA_CANCELADA: "La compra fue cancelada.",
    SIN_PENDIENTES: "La compra ya no tiene nada pendiente de decisión.",
}

# Los motivos de la confirmación de una entrega (COM-CNF-ENT, extensiones 2a y 6a): inválido, ya usado o vencido (y anulado, que el cliente lee como «ya no se puede usar»).
MOTIVOS_DE_CONFIRMACION = {
    NO_VALIDO: "Este enlace no es válido.",
    VENCIDO: "El plazo para confirmar la entrega terminó.",
    USADO: "Este enlace ya se usó: su respuesta quedó registrada.",
    ANULADO: "Este enlace ya no puede usarse.",
}


def texto_del_motivo(motivo, tipo=None):
    """El texto de `motivo` (una de las constantes de arriba) para el cliente, según el tipo de enlace (`confirmacion_entrega` o, por omisión, el de faltante)."""
    if tipo == Tipo.CONFIRMACION_ENTREGA:
        return MOTIVOS_DE_CONFIRMACION.get(motivo, "Este enlace ya no puede usarse.")
    return MOTIVOS.get(motivo, "Este enlace ya no puede usarse.")


def disponible_de(detalle_ids):
    """`{detalle_id: cantidad disponible}` (regla «Cantidad disponible» de COM-DCD-FLT): la cantidad cubierta de cada detalle, es decir, la suma de lo cubierto por las líneas
    de sus reservas no liberadas (reglas 9 y 10 de 8.8). Una sola consulta."""
    detalle_ids = list(detalle_ids)
    disponible = defaultdict(int)
    filas = (
        DetalleReserva.objects.filter(reserva__detalle_venta_id__in=detalle_ids)
        .exclude(reserva__estado_reserva=ReservaStock.Estado.LIBERADA)
        .values_list("reserva__detalle_venta_id", "cantidad_reservada", "cantidad_cosechada", "lote_id")
    )
    for detalle_id, reservada, cosechada, lote_id in filas:
        disponible[detalle_id] += _cubierto(reservada, cosechada, lote_id)
    return {i: disponible[i] for i in detalle_ids}


def _vendedor_activo(venta):
    """La cuenta activa del Vendedor del contrato (D-60: el actual), o `None`."""
    return Usuario.objects.filter(pk=venta.vendedor_id, is_active=True).first()


def crear_enlace(tipo, cliente, *, compra_venta=None, vence=None, entrega=None):
    """Crea el enlace vigente para `cliente` y registra en `on_commit` el correo con su URL. Devuelve `(enlace, token)`: el token es solo para las pruebas, ningún llamador lo guarda ni lo
    muestra. Corre dentro de la transacción del caso de uso (sin ella, `RuntimeError`).
    - `decision_faltante`: con `compra_venta` (bloqueada) y `vence`; si la venta ya tenía un enlace vigente del mismo tipo, lo pasa a `reemplazado` (regla «Enlace de decisión»).
    - `confirmacion_entrega` (COM-06b, D-68 punto 1): con la `entrega` de suministro concretada, sin `compra_venta` ni `vence` (la vigencia se calcula, `vencimiento_de`). Uno por entrega y sin
      reemplazo: un segundo enlace lo rechaza la base (`IntegrityError`).
    Argumentos que no cuadran con el tipo, o un cliente sin correo (el llamador lo sabe antes): `ValueError`."""
    if transaction.get_autocommit():
        raise RuntimeError("`crear_enlace` corre dentro de la transacción del caso de uso que la llama.")
    if tipo == Tipo.CONFIRMACION_ENTREGA:
        if entrega is None or compra_venta is not None or vence is not None:
            raise ValueError("El enlace de confirmación lleva la entrega, y ni la compra-venta ni el vencimiento (se calcula).")
    elif entrega is not None or compra_venta is None or vence is None:
        raise ValueError("El enlace de decisión de faltante lleva la compra-venta y el vencimiento, y no la entrega.")
    if not cliente.email_cliente:
        raise ValueError("Un cliente sin correo no tiene enlace: lo decide el Vendedor (extensión 1a de COM-DCD-FLT).")
    if tipo == Tipo.DECISION_FALTANTE:
        reemplazar_enlaces_de(compra_venta, tipo)
    token, resumen = nuevo_token()
    enlace = EnlaceCliente.objects.create(tipo=tipo, cliente=cliente, compra_venta=compra_venta, entrega=entrega, token_resumen=resumen, fecha_vencimiento=vence)
    transaction.on_commit(lambda: enviar_enlace(enlace.pk, token))
    return enlace, token


def _vigentes_de(compra_venta, tipo=Tipo.DECISION_FALTANTE):
    """Los enlaces vigentes de la venta, bloqueados (`FOR NO KEY UPDATE`) y en orden de id."""
    return list(
        EnlaceCliente.objects.select_for_update(no_key=True, of=("self",)).filter(compra_venta=compra_venta, tipo=tipo, estado=Estado.VIGENTE).order_by("pk")
    )


def _pasar(enlaces, estado):
    """Cambia el estado de `enlaces` (ya bloqueados) con un solo `UPDATE` y en memoria."""
    EnlaceCliente.objects.filter(pk__in=[e.pk for e in enlaces]).update(estado=estado)
    for e in enlaces:
        e.estado = estado
    return enlaces


def reemplazar_enlaces_de(compra_venta, tipo=Tipo.DECISION_FALTANTE):
    """Pasa a `reemplazado` el enlace vigente de la venta (regla «Enlace de decisión»; también cuando el cliente se quedó sin correo y ya no hay enlace nuevo). Devuelve los reemplazados."""
    return _pasar(_vigentes_de(compra_venta, tipo), Estado.REEMPLAZADO)


def anular_enlaces_de(compra_venta):
    """Pasa a `anulado` los enlaces `vigente` de la venta (PROD-ASG-CAM cuando se queda sin pendientes, COM-DCD-FLT al registrar y, desde COM-05b, COM-CNL-CVT). El `usado` no se
    toca. Los bloquea en orden de id: va dentro de la transacción del caso de uso y después de todo lo demás. Devuelve los anulados."""
    return _pasar(_vigentes_de(compra_venta), Estado.ANULADO)


def enlace_por_token(token):
    """El enlace cuyo resumen es el de `token` (con su venta y cliente), o `None`. Se busca por el resumen: compararlos hace innecesaria una comparación en tiempo constante (D-65 punto 4)."""
    return EnlaceCliente.objects.select_related("compra_venta", "cliente").filter(token_resumen=resumen_de(token)).first()


def enlace_por_id(enlace_id):
    """El enlace con ese id, leído de nuevo (las vistas guardan en la sesión solo el id), o `None`."""
    if not enlace_id:
        return None
    return EnlaceCliente.objects.select_related("compra_venta", "cliente").filter(pk=enlace_id).first()


def vencimiento_de(enlace):
    """El último día en que sirve `enlace` (D-68 punto 8). Faltante: la `fecha_vencimiento` guardada. Confirmación: se **calcula** con el parámetro vigente, `fecha_resolucion_orden` de la entrega
    + `dias_vigencia_enlace_confirmacion` (si el parámetro cambia, cambia la vigencia de los enlaces ya enviados). `None` si la entrega todavía no se concretó."""
    if enlace.tipo != Tipo.CONFIRMACION_ENTREGA:
        return enlace.fecha_vencimiento
    resolucion = Entrega.objects.filter(pk=enlace.entrega_id).values_list("fecha_resolucion_orden", flat=True).first()
    if resolucion is None:
        return None
    return resolucion + timedelta(days=configuracion.obtener().dias_vigencia_enlace_confirmacion)


def _situacion_de_confirmacion(enlace, hoy):
    """`situacion_del_enlace` de una confirmación (COM-CNF-ENT, extensiones 2a y 6a): `usado`, `anulado`, `vencido` (por estado o porque hoy pasó la vigencia calculada) o `sirve`."""
    if enlace.estado == Estado.USADO:
        return USADO
    vence = vencimiento_de(enlace)
    if enlace.estado in (Estado.ANULADO, Estado.REEMPLAZADO) or vence is None:
        return ANULADO
    if enlace.estado == Estado.VENCIDO or hoy > vence:
        return VENCIDO
    return SIRVE


def situacion_del_enlace(enlace, hoy=None):
    """Qué hace el enlace hoy (extensiones 2a y 6a), una de las constantes de arriba; se controla al abrirlo y otra vez al registrar. Sirve si está `vigente`, hoy no pasó de su
    vencimiento (sirve todo ese día) y, en el faltante, la venta sigue «pendiente de decisión del cliente» con algún detalle pendiente; en la confirmación, el vencimiento se calcula."""
    hoy = hoy or stock.hoy()
    if enlace.tipo == Tipo.CONFIRMACION_ENTREGA:
        return _situacion_de_confirmacion(enlace, hoy)
    venta = CompraVenta.objects.get(pk=enlace.compra_venta_id)
    if enlace.estado == Estado.REEMPLAZADO:
        return REEMPLAZADO
    if enlace.estado == Estado.USADO:
        return USADO
    if venta.estado_venta == CompraVenta.Estado.CANCELADA:
        return VENTA_CANCELADA
    if enlace.estado == Estado.ANULADO:
        return ANULADO
    if enlace.estado == Estado.VENCIDO or hoy > enlace.fecha_vencimiento:
        return VENCIDO
    pendientes = DetalleVenta.objects.filter(compra_venta=venta, estado_detalle_venta=DetalleVenta.Estado.PENDIENTE_DECISION).exists()
    if venta.estado_venta != CompraVenta.Estado.PENDIENTE_DECISION or not pendientes:
        return SIN_PENDIENTES
    return SIRVE


def bloquear_enlace(enlace_id):
    """El enlace bloqueado (`FOR NO KEY UPDATE`) y releído, para verificar con la fila bloqueada que siga sirviendo (patrón, sección 5). Dentro de `transaction.atomic()`, siempre al final."""
    return EnlaceCliente.objects.select_for_update(no_key=True, of=("self",)).select_related("compra_venta", "cliente").get(pk=enlace_id)


def _lineas_del_correo(venta):
    """Los detalles pendientes tal como los ve el cliente: variedad, cantidad solicitada y disponible. Sin lotes, partidas ni costos (garantía mínima 4)."""
    detalles = list(venta.detalles.filter(estado_detalle_venta=DetalleVenta.Estado.PENDIENTE_DECISION).select_related("variedad").order_by("variedad_id"))
    disponible = disponible_de([d.pk for d in detalles])
    return [{"variedad": str(d.variedad), "solicitada": d.cant_solicitada_venta, "disponible": disponible[d.pk]} for d in detalles]


def enviar_enlace(enlace_id, token):
    """Envía al cliente el correo con el enlace y deja el resultado en `estado_envio` (`enviado` o `pendiente_envio`). Corre **fuera** de toda transacción (`on_commit`). Si el enlace ya
    no está vigente (otra operación lo anuló entre el commit y el envío) no manda nada. Sin correo del cliente, sin `URL_DEL_SITIO`, sin el correo del sistema configurado o con el envío
    fallido queda `pendiente_envio` y se avisa al Vendedor para que registre él la decisión (D-65 punto 6; no hay reintento automático). Se guarda con un `UPDATE` propio y no se audita."""
    enlace = EnlaceCliente.objects.select_related("cliente", "compra_venta").get(pk=enlace_id)
    if enlace.estado != Estado.VIGENTE:
        return
    if enlace.tipo == Tipo.CONFIRMACION_ENTREGA:
        return _enviar_confirmacion(enlace, token)
    venta, cliente = enlace.compra_venta, enlace.cliente
    enviado = False
    if cliente.email_cliente and settings.URL_DEL_SITIO and correo.correo_configurado():
        enviado = correo.enviar_correo(
            Destinatario(cliente.pk, cliente.email_cliente),
            f"Tu compra {venta.codigo}: hace falta tu decisión",
            "comercial/correos/enlace_faltante.txt",
            {
                "codigo": venta.codigo,
                "cliente": cliente.nombre_visible,
                "url": settings.URL_DEL_SITIO + RUTA_PUBLICA.format(token=token),
                "lineas": _lineas_del_correo(venta),
                "fecha_pactada": venta.fecha_pactada_venta,
                "vence": enlace.fecha_vencimiento,
            },
        )
    EnlaceCliente.objects.filter(pk=enlace.pk).update(estado_envio=EstadoEnvio.ENVIADO if enviado else EstadoEnvio.PENDIENTE_ENVIO)
    if not enviado:
        vendedor = _vendedor_activo(venta)
        if vendedor is not None:
            donde = f" a {cliente.email_cliente}" if cliente.email_cliente else ""
            notificaciones.notificar(
                vendedor,
                f"No se pudo enviar el enlace de {venta.codigo}",
                f"No se pudo enviar el enlace{donde}: registrá vos la decisión del cliente sobre el faltante desde la ficha de la compra.",
            )


def _enviar_confirmacion(enlace, token):
    """El correo único de la concreción de un suministro (postcondición l de COM-CNC-ENT, D-68 punto 1): el comprobante de entrega y el enlace de confirmación, con hasta cuándo sirve. El resultado
    va a `EnlaceCliente.estado_envio` y a `Entrega.estado_aviso_cliente`. Si no sale (sin correo del sistema, sin `URL_DEL_SITIO` o fallo), queda «pendiente de envío» y lo reintenta el paso 50 (15a) con
    `reemitir_enlace`: no se avisa al Vendedor, porque hay reintento. Corre fuera de toda transacción."""
    from comercial.servicios import concrecion  # adentro: `concrecion` importa este módulo

    entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor").get(pk=enlace.entrega_id)
    cliente = enlace.cliente
    enviado = False
    if cliente.email_cliente and settings.URL_DEL_SITIO and correo.correo_configurado():
        contexto = concrecion.contexto_del_comprobante(entrega)
        contexto["url"] = settings.URL_DEL_SITIO + RUTA_PUBLICA.format(token=token)
        contexto["vence"] = vencimiento_de(enlace)
        enviado = correo.enviar_correo(
            Destinatario(cliente.pk, cliente.email_cliente), f"Comprobante de tu entrega {entrega.codigo}: confirmá que la recibiste", "comercial/correos/confirmacion_entrega.txt", contexto
        )
    EnlaceCliente.objects.filter(pk=enlace.pk).update(estado_envio=EstadoEnvio.ENVIADO if enviado else EstadoEnvio.PENDIENTE_ENVIO)
    Entrega.objects.filter(pk=entrega.pk).update(estado_aviso_cliente=Entrega.EstadoDelAviso.ENVIADO if enviado else Entrega.EstadoDelAviso.PENDIENTE_ENVIO)


def reemitir_enlace(enlace):
    """Extensión 15a de COM-CNC-ENT (parte 4 del paso 50): el correo con el enlace no salió y el token no se guarda (D-65), así que no se puede mandar el mismo. Si el enlace de confirmación sigue `vigente`
    y dentro de su vigencia, le pone un **token nuevo** en la misma fila (el viejo, que nunca llegó, deja de servir) y lo manda con `on_commit`. No es un reemplazo: la fila es la misma. Usado, vencido o
    de otro tipo: no hace nada. Devuelve el token (solo para las pruebas) o `None`. Corre fuera de toda transacción; toma solo el lock del enlace."""
    with transaction.atomic():
        actual = bloquear_enlace(enlace.pk)
        if actual.tipo != Tipo.CONFIRMACION_ENTREGA or actual.estado != Estado.VIGENTE or situacion_del_enlace(actual) != SIRVE:
            return None
        token, resumen = nuevo_token()
        EnlaceCliente.objects.filter(pk=actual.pk).update(token_resumen=resumen)
        transaction.on_commit(lambda: enviar_enlace(actual.pk, token))
    return token


def avisar_enlaces_vencidos(hoy):
    """Paso diario 27, «Avisar enlaces vencidos» (D-65 punto 7; regla «Vencimiento sin respuesta»): por cada enlace `vigente` de faltante con `fecha_vencimiento` anterior a `hoy`, en su
    transacción (cuenta del Vendedor → venta → enlace): lo pasa a `vencido`, avisa UNA vez al Vendedor y deja un registro `vencimiento_enlace`. Los detalles siguen pendientes y su stock
    reservado: no hay decisión tácita. Idempotente (un `vencido` no se vuelve a tomar). Un enlace que falla se registra y los demás siguen. Nunca lee la fecha por su cuenta."""
    filas = list(
        EnlaceCliente.objects.filter(tipo=Tipo.DECISION_FALTANTE, estado=Estado.VIGENTE, fecha_vencimiento__lt=hoy)
        .order_by("pk")
        .values_list("pk", "compra_venta__vendedor_id")
    )
    avisados = 0
    for enlace_id, vendedor_id in filas:
        try:
            with transaction.atomic():
                list(Usuario.objects.select_for_update(no_key=True).filter(pk=vendedor_id))
                enlace = EnlaceCliente.objects.get(pk=enlace_id)
                list(CompraVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk=enlace.compra_venta_id))
                enlace = bloquear_enlace(enlace_id)
                if enlace.estado != Estado.VIGENTE or enlace.fecha_vencimiento >= hoy:
                    continue
                venta = enlace.compra_venta
                _pasar([enlace], Estado.VENCIDO)
                vendedor = _vendedor_activo(venta)
                if vendedor is not None:
                    notificaciones.notificar(
                        vendedor,
                        f"Venció el plazo del cliente de {venta.codigo}",
                        f"Venció el plazo del cliente de {venta.codigo} para decidir el faltante: podés registrar la decisión en su nombre.",
                    )
                RegistroAuditoria.objects.registrar(
                    usuario=None,
                    accion=RegistroAuditoria.Accion.VENCIMIENTO_ENLACE,
                    afectados=[venta, enlace],
                    detalle={
                        "cambios": {"estado": {"antes": Estado.VIGENTE.value, "despues": Estado.VENCIDO.value}},
                        "datos": {"fecha_vencimiento_enlace": f"{enlace.fecha_vencimiento:%d/%m/%Y}"},
                    },
                )
                avisados += 1
        except Exception:  # noqa: BLE001 - un enlace que falla no corta el paso (D-56 punto 5)
            logger.exception("Falló el vencimiento del enlace %s", enlace_id)
    return ResumenDePaso(len(filas), avisados, 0, f"{avisados} enlaces vencidos")
