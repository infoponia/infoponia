# Enlace del proveedor (CMP-02a; D-88 y docs/patrones/enlace_del_proveedor.md): crear, encontrar por su token, decir si sirve, bloquear y enviar.
# Es el mismo mecanismo que el enlace del cliente (D-65). La base guarda SOLO el resumen SHA-256 del token (``core/enlaces.py``); el token vive en
# memoria hasta armar la URL del correo. El enlace NO guarda fecha de vencimiento: vence al terminar el día de la fecha límite del pedido, que se
# lee del pedido al abrir y al registrar. ``crear_enlace`` corre dentro de la transacción del caso de uso; el correo sale en ``on_commit``
# (``core.correo.enviar_correo``, D-54). Lo de CMP-02b (anular, reemplazar y avisar la cancelación) se suma en este mismo archivo.

from collections import namedtuple

from django.db import transaction

from compras.models import DetallePedido, EnlaceProveedor
from core.correo import correo_configurado, enviar_correo
from core.enlaces import nuevo_token, resumen_de
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad
from inventario.unidades import Unidad

Estado = EnlaceProveedor.Estado
EstadoEnvio = EnlaceProveedor.EstadoEnvio

# La URL pública del portal (``config/urls.py``): ``/proveedor/<token>/``. Se arma a mano para no depender de las vistas desde este módulo.
RUTA_PUBLICA = "/proveedor/{token}/"

# Qué pasa al abrir un enlace (extensiones 2a y 2b de CMP-ENV-COT; D-88 puntos 2 y 3). Solo ``SIRVE`` deja cotizar y ``SOLO_LECTURA`` muestra la
# cotización ya enviada; el resto da la pantalla «Este enlace no se puede usar» con su motivo, sin datos del pedido.
SIRVE = "sirve"
SOLO_LECTURA = "solo_lectura"
VENCIDO = "vencido"
PEDIDO_CANCELADO = "pedido_cancelado"
PEDIDO_CERRADO = "pedido_cerrado"
PROVEEDOR_INACTIVO = "proveedor_inactivo"
REEMPLAZADO = "reemplazado"
ANULADO = "anulado"

# ``enviar_correo`` necesita ``pk`` y ``email`` de quien recibe: el proveedor no es una cuenta.
Destinatario = namedtuple("Destinatario", "pk email")


def crear_enlace(invitacion, construir_url):
    """Crea el enlace vigente de ``invitacion`` y registra en ``on_commit`` el correo con su URL. Devuelve ``(enlace, token)``: el token es solo
    para las pruebas, ningún llamador lo guarda ni lo muestra. Corre dentro de la transacción del caso de uso: si se revierte, no sale el correo.
    ``construir_url(ruta)`` arma la URL absoluta (la vista pasa ``request.build_absolute_uri``). A lo sumo un enlace vigente por invitación: otro
    es un error de uso (``ValueError``); para reemplazarlo existe «Reenviar invitación» (CMP-02b)."""
    if EnlaceProveedor.objects.filter(invitacion=invitacion, estado=Estado.VIGENTE).exists():
        raise ValueError("La invitación ya tiene un enlace vigente: para cambiarlo se reenvía la invitación.")
    token, resumen = nuevo_token()
    enlace = EnlaceProveedor.objects.create(invitacion=invitacion, token_resumen=resumen)
    url = construir_url(RUTA_PUBLICA.format(token=token))
    transaction.on_commit(lambda: enviar_invitacion(enlace.pk, url))
    return enlace, token


def enlace_por_token(token):
    """El enlace cuyo resumen es el de ``token`` (con su invitación, pedido y proveedor), o ``None`` si no existe. Se busca por el resumen:
    compararlos hace innecesaria una comparación en tiempo constante (D-65 punto 4)."""
    return (
        EnlaceProveedor.objects.select_related("invitacion__pedido", "invitacion__proveedor")
        .filter(token_resumen=resumen_de(token))
        .first()
    )


def enlace_por_id(enlace_id):
    """El enlace con ese id (con su invitación, pedido y proveedor) leído de nuevo, o ``None``: así lo usan las vistas del portal, que guardan en la
    sesión solo el id y vuelven a leer el enlace en cada pedido (patrón, sección 3)."""
    return EnlaceProveedor.objects.select_related("invitacion__pedido", "invitacion__proveedor").filter(pk=enlace_id).first()


def situacion_del_enlace(enlace, hoy=None):
    """Qué hace el enlace hoy (D-88 puntos 2 y 3), una de las constantes de arriba. Se controla al abrirlo y otra vez al registrar.

    - Un enlace ``reemplazado`` o con el pedido cancelado nunca muestra nada; uno ``anulado`` (el proveedor pasó a inactivo) tampoco.
    - Con el enlace ``usado``, el proveedor ve su cotización en solo lectura hasta el final del día de la fecha límite (H15.2); después, nada. La
      cotización de un proveedor que pasó a inactivo se mantiene (regla «Proveedor que pasa a inactivo»).
    - Vigente: sirve hasta el final del día de la fecha límite, si el pedido sigue «en cotización» y el proveedor está activo."""
    hoy = hoy or stock.hoy()
    pedido = enlace.invitacion.pedido
    if enlace.estado == Estado.REEMPLAZADO:
        return REEMPLAZADO
    if pedido.estado_pedido == pedido.Estado.CANCELADO:
        return PEDIDO_CANCELADO
    if enlace.estado == Estado.ANULADO:
        return ANULADO
    if enlace.estado == Estado.USADO:
        return SOLO_LECTURA if hoy <= pedido.fecha_limite_cotizaciones else VENCIDO
    if enlace.estado == Estado.VENCIDO:
        return VENCIDO
    if not pedido.en_cotizacion:
        return PEDIDO_CERRADO
    if not enlace.invitacion.proveedor.activo:
        return PROVEEDOR_INACTIVO
    return VENCIDO if hoy > pedido.fecha_limite_cotizaciones else SIRVE


def bloquear_enlace(enlace_id):
    """El enlace bloqueado (``FOR NO KEY UPDATE``) y releído, para verificar con la fila bloqueada que siga sirviendo (docs/patrones/
    enlace_del_cliente.md, sección 5). Dentro de ``transaction.atomic()``, después de bloquear el proveedor y el pedido (D-88 punto 7)."""
    return (
        EnlaceProveedor.objects.select_for_update(no_key=True, of=("self",))
        .select_related("invitacion__pedido", "invitacion__proveedor")
        .get(pk=enlace_id)
    )


def _lineas_del_correo(pedido):
    """Los detalles del pedido tal como los ve el proveedor: insumo (nombre, descripción, unidad), cantidad e invernadero con su dirección.
    **Sin el precio de referencia ni el monto** (garantía mínima de CMP-RLZ-PED)."""
    detalles = DetallePedido.objects.filter(pedido=pedido).select_related(
        "insumo_invernadero__insumo", "insumo_invernadero__invernadero__direccion"
    )
    lineas = []
    for detalle in detalles:
        insumo = detalle.insumo_invernadero.insumo
        invernadero = detalle.insumo_invernadero.invernadero
        lineas.append(
            {
                "insumo": insumo.nombre_insumo,
                "descripcion": insumo.descripcion_insumo,
                "unidad": Unidad(insumo.unidad_medida_insumo).label,
                "cantidad": texto_cantidad(detalle.cantidad_detalle, insumo.unidad_medida_insumo),
                "invernadero": invernadero.nombre_invernadero,
                "direccion": str(invernadero.direccion),
            }
        )
    return lineas


def enviar_invitacion(enlace_id, url):
    """Envía al proveedor el correo con ``url`` y deja el resultado en ``estado_envio`` (``enviado`` o ``pendiente_envio``). Corre **fuera** de
    toda transacción (``on_commit``). Si el enlace ya no está vigente (otra operación lo anuló entre el commit y el envío) no manda nada. Sin
    el correo configurado o con el envío fallido queda ``pendiente_envio``: no hay reintento automático, el reintento es «Reenviar
    invitación» (D-88 punto 6, CMP-02b). El resultado se guarda con un ``UPDATE`` propio y no se audita: no es un dato del dominio."""
    enlace = EnlaceProveedor.objects.select_related("invitacion__pedido", "invitacion__proveedor").get(pk=enlace_id)
    if enlace.estado != Estado.VIGENTE:
        return
    pedido, proveedor = enlace.invitacion.pedido, enlace.invitacion.proveedor
    enviado = False
    if correo_configurado():
        contexto = {
            "pedido": str(pedido),
            "proveedor": proveedor.nombre_para_mostrar,
            "url": url,
            "lineas": _lineas_del_correo(pedido),
            "fecha_limite": pedido.fecha_limite_cotizaciones,
        }
        enviado = enviar_correo(
            Destinatario(proveedor.pk, proveedor.email_proveedor),
            f"Pedido de cotización {pedido}",
            "compras/correo/invitacion.txt",
            contexto,
        )
    EnlaceProveedor.objects.filter(pk=enlace_id).update(estado_envio=EstadoEnvio.ENVIADO if enviado else EstadoEnvio.PENDIENTE_ENVIO)


# ---- CMP-02b: anular y avisar la cancelación ----


def anular_enlaces_de_pedido(pedido):
    """Pasa a ``anulado`` los enlaces ``vigente`` de ``pedido`` (postcondición c de CMP-CNL-PED; D-88 punto 2) y los devuelve. Los ``usado`` no se
    tocan: son de quien ya cotizó. Los bloquea (``FOR NO KEY UPDATE``) en orden de id, así que va dentro de la transacción del caso de uso y
    después del pedido y de sus cotizaciones (docs/patrones/stock.md, sección 5, punto 8)."""
    vigentes = list(
        EnlaceProveedor.objects.select_for_update(no_key=True, of=("self",))
        .filter(invitacion__pedido=pedido, estado=Estado.VIGENTE)
        .order_by("id")
    )
    EnlaceProveedor.objects.filter(pk__in=[e.pk for e in vigentes]).update(estado=Estado.ANULADO)
    for enlace in vigentes:
        enlace.estado = Estado.ANULADO
    return vigentes


def enviar_aviso_de_cancelacion(pedido_id):
    """Postcondición d de CMP-CNL-PED: avisa por correo a todos los proveedores invitados, hayan cotizado o no, que el pedido se canceló. El correo
    lleva el pedido y las fechas, **sin el motivo** ni los otros proveedores ni precios. Corre **fuera** de toda transacción (``on_commit``); un
    correo que falla no revierte nada (extensión 7a) y se registra en el log de ``core.correo``. Sin el correo configurado no sale nada."""
    if not correo_configurado():
        return
    from compras.models import Pedido

    pedido = Pedido.objects.get(pk=pedido_id)
    for invitacion in pedido.invitaciones.select_related("proveedor").order_by("id"):
        proveedor = invitacion.proveedor
        enviar_correo(
            Destinatario(proveedor.pk, proveedor.email_proveedor),
            f"Pedido de cotización {pedido} cancelado",
            "compras/correo/cancelacion.txt",
            {
                "pedido": str(pedido),
                "proveedor": proveedor.nombre_para_mostrar,
                "fecha_pedido": pedido.fecha_pedido,
                "fecha_cierre": pedido.fecha_cierre_pedido,
            },
        )


def anular_enlaces_de_proveedor(proveedor):
    """Regla 3 de CMP-BAJ-PRV (H22): al dar de baja a ``proveedor``, sus enlaces ``vigente`` de pedidos «en cotización» pasan a ``anulado`` (dejan de servir,
    D-88 punto 2) y se devuelven. Los ``usado`` y los de pedidos que ya no están en cotización no se tocan; tampoco su cotización. Los bloquea
    (``FOR NO KEY UPDATE``) en orden de id, después del proveedor (que ya bloqueó la baja): cotizar bloquea proveedor → pedido → enlace."""
    from compras.models import Pedido

    vigentes = list(
        EnlaceProveedor.objects.select_for_update(no_key=True, of=("self",))
        .filter(invitacion__proveedor=proveedor, invitacion__pedido__estado_pedido=Pedido.Estado.EN_COTIZACION, estado=Estado.VIGENTE)
        .order_by("id")
    )
    EnlaceProveedor.objects.filter(pk__in=[e.pk for e in vigentes]).update(estado=Estado.ANULADO)
    for enlace in vigentes:
        enlace.estado = Estado.ANULADO
    return vigentes


def reemplazar_enlace(invitacion, construir_url):
    """«Reenviar invitación» (regla 7 de CMP-CNS-PED, H15.1): el enlace vigente de ``invitacion`` pasa a ``reemplazado`` (se bloquea antes) y se crea uno
    nuevo, cuyo correo sale en ``on_commit`` (``crear_enlace``). Devuelve ``(enlace_nuevo, enlace_anterior)``; el anterior es ``None`` si la invitación no
    tenía ninguno vigente (por ejemplo, tras la baja y la reactivación del proveedor). Va dentro de la transacción del caso de uso, con el proveedor y el
    pedido ya bloqueados (D-88 punto 7)."""
    anterior = (
        EnlaceProveedor.objects.select_for_update(no_key=True, of=("self",)).filter(invitacion=invitacion, estado=Estado.VIGENTE).first()
    )
    if anterior is not None:
        anterior.estado = Estado.REEMPLAZADO
        anterior.save(update_fields=["estado"])
    nuevo, _ = crear_enlace(invitacion, construir_url)
    return nuevo, anterior
