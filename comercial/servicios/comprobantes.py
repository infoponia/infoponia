# Comprobante de un contrato (COM-02; paso 16 y extensiones 16a y 16b de COM-REG-CVT). Una sola función para los dos tipos de contrato
# (COM-03 suma la plantilla del suministro). Se llama SIEMPRE fuera de una transacción (D-14, D-54): un servidor SMTP lento no puede
# mantener bloqueos tomados. El resultado queda en `Contrato.estado_comprobante`; no hay reintento automático (no hay cola de envíos,
# `docs/temas_abiertos.md`, «Notificaciones»): el reintento es manual, con «Reenviar comprobante» en la ficha.

from collections import namedtuple

from django.core.exceptions import PermissionDenied, ValidationError

from comercial.models import CompraVenta, Contrato
from core import correo, notificaciones
from core.models import Usuario, rol_de

Estado = Contrato.EstadoDelComprobante

# `enviar_correo` espera una cuenta (`.pk` y `.email`): al cliente, que no tiene cuenta, se le pasa esto. El registro de la falla dirá
# «cuenta N» con el id del cliente (anotado en `docs/temas_abiertos.md`, «Correo a quien no tiene cuenta»).
Destinatario = namedtuple("Destinatario", "pk email")

PLANTILLAS = {Contrato.Tipo.COMPRA_VENTA: "comercial/correos/comprobante_compra_venta.txt"}


def contexto_del_comprobante(venta):
    """Lo que dice el comprobante de una compra-venta (variación de datos 16a): detalles, cantidades, precios, monto estimado, fecha
    pactada y modalidad (dirección de envío, o invernadero de retiro con su dirección). Lo usan el correo y la página imprimible."""
    from comercial.servicios import compra_ventas

    return compra_ventas.datos_del_comprobante(venta)


def enviar_comprobante(contrato):
    """Envía el comprobante al cliente y devuelve el ``estado_comprobante`` en el que queda el contrato.

    - Cliente sin correo (16b): ``para_imprimir``; no se envía nada.
    - Con correo pero sin el correo del sistema configurado, o si el envío falla (16a): ``pendiente_envio``; la venta permanece registrada.
    - Salió: ``enviado``, con un único ``UPDATE`` (atómico). Solo pasa a «enviado» desde «pendiente de envío».
    Hay que llamarla fuera de una transacción.
    """
    contrato = Contrato.objects.select_related("cliente").get(pk=contrato.pk)
    cliente = contrato.cliente
    if not cliente.email_cliente:
        Contrato.objects.filter(pk=contrato.pk).update(estado_comprobante=Estado.PARA_IMPRIMIR)
        return Estado.PARA_IMPRIMIR
    if not correo.correo_configurado():
        Contrato.objects.filter(pk=contrato.pk).update(estado_comprobante=Estado.PENDIENTE_ENVIO)
        return Estado.PENDIENTE_ENVIO
    venta = CompraVenta.objects.get(pk=contrato.pk)
    salio = correo.enviar_correo(
        Destinatario(cliente.pk, cliente.email_cliente),
        f"Comprobante de tu compra {venta.codigo}",
        PLANTILLAS[contrato.tipo_contrato],
        contexto_del_comprobante(venta),
    )
    nuevo = Estado.ENVIADO if salio else Estado.PENDIENTE_ENVIO
    Contrato.objects.filter(pk=contrato.pk).update(estado_comprobante=nuevo)
    return nuevo


def avisar_comprobante_pendiente(actor, contrato):
    """Extensión 16a: si registró el Gerente, el Vendedor responsable recibe «El comprobante de CV-… quedó pendiente de envío.»."""
    if actor is not None and actor.pk != contrato.vendedor_id:
        notificaciones.notificar(
            Usuario.objects.get(pk=contrato.vendedor_id),
            "Comprobante pendiente de envío",
            f"El comprobante de {contrato.codigo} quedó pendiente de envío.",
        )


def reenviar_comprobante(actor, contrato_id):
    """«Reenviar comprobante» (16a): lo pueden hacer el Vendedor responsable y el Gerente, solo si el comprobante está «pendiente de
    envío». Sin auditoría (no cambia datos de negocio). Devuelve el estado en el que queda. Errores: ``comprobante_no_pendiente`` y
    ``cliente_sin_correo``. Fuera de una transacción (D-14)."""
    contrato = Contrato.objects.select_related("cliente").filter(pk=contrato_id).first()
    if (
        actor is None
        or not actor.is_active
        or contrato is None
        or not Contrato.objects.en_alcance_de(actor).filter(pk=contrato_id).exists()
    ):
        raise PermissionDenied("Tu cuenta no tiene acceso a esta acción.")
    if rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR):
        raise PermissionDenied("Tu cuenta no tiene acceso a esta acción.")
    if contrato.estado_comprobante != Estado.PENDIENTE_ENVIO:
        raise ValidationError("El comprobante no está pendiente de envío.", code="comprobante_no_pendiente")
    if not contrato.cliente.email_cliente:
        raise ValidationError("El cliente no tiene correo: el comprobante se entrega impreso.", code="cliente_sin_correo")
    return enviar_comprobante(contrato)
