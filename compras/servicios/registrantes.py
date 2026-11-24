# Lo que `compras` registra en los puntos de extensión de otras apps por sus pedidos (CMP-02b; A4 de D-37, D-87 punto 5, docs/api/extensiones_de_maestros.md y
# docs/api/extensiones_de_inventario.md). Los registra ``ComprasConfig.ready()``:
#   - ``core``: ``efecto_de_baja_de_cuenta`` (la baja de un Agrónomo cancela sus pedidos «en cotización», MD-62 y H17) y ``asignaciones_de_cuenta`` (la ventana de
#     baja dice cuántos pedidos se cancelarán, regla 4 de USR-BAJ-USR).
#   - ``maestros``: el traspaso del rol ``agronomo`` (``contar_traspaso``, ``aviso_de_traspaso`` y ``traspasar_pedidos``): cancelan los pedidos del saliente con algún
#     detalle a ese invernadero.
#   - ``inventario``: ``impedimento_de_deshabilitacion`` (H20: un pedido «en cotización» impide deshabilitar el insumo, código ``pedido_en_curso``).
# Todo corre dentro de la transacción del servicio que llama, después de sus bloqueos de cuentas e invernaderos; los pedidos que cancela los bloquea en orden de
# id (``pedidos.cancelar_pedido_automaticamente``). Las lecturas hacen una consulta para toda la lista, nunca una por fila.

from django.urls import reverse

from compras.models import DetallePedido, Pedido
from compras.servicios import pedidos
from core.extensiones import Asignacion, Efecto
from core.models import Usuario, referencia, rol_de
from maestros.extensiones import Impedimento

ROL_AGRONOMO = "agronomo"  # el atributo del invernadero (``Invernadero.ROLES``)


def _en_cotizacion_de(agronomo_id):
    """Los pedidos «en cotización» de un Agrónomo (consulta, sin evaluar)."""
    return Pedido.objects.filter(agronomo_id=agronomo_id, estado_pedido=Pedido.Estado.EN_COTIZACION)


def _con_destino(consulta, invernadero):
    """``consulta`` limitada a los pedidos con algún detalle a ``invernadero`` (una subconsulta: no repite pedidos y se puede bloquear)."""
    return consulta.filter(pk__in=DetallePedido.objects.filter(insumo_invernadero__invernadero=invernadero).values("pedido_id"))


def _cancelar_todos(consulta, causa, actor):
    """Bloquea los pedidos de ``consulta`` en orden de id y cancela cada uno con ``causa``. Devuelve los pedidos cancelados; salta el que, releído con el
    bloqueo, ya no estaba «en cotización»."""
    cancelados = []
    for pedido in list(consulta.select_for_update(no_key=True, of=("self",)).order_by("id")):
        cancelado = pedidos.cancelar_pedido_automaticamente(pedido, causa, actor=actor)
        if cancelado is not None:
            cancelados.append(cancelado)
    return cancelados


# ---- core: baja de la cuenta ----


def efecto_de_baja_de_cuenta(actor, cuenta):
    """`core.registrar_efecto_de_baja_de_cuenta` (MD-62, regla 5 de 8.22, H17): cancela con la causa ``agronomo_inactivo`` los pedidos «en cotización» de la
    cuenta que se da de baja, si es un Agrónomo. Devuelve el ``Efecto``: los pedidos como afectados y ``datos.pedidos_cancelados`` para la auditoría de la baja.
    Se avisa a los destinatarios de H21 (nunca a ``actor``) y a los proveedores invitados, por correo."""
    if rol_de(cuenta) != Usuario.Rol.AGRONOMO:
        return Efecto([], {})
    cancelados = _cancelar_todos(_en_cotizacion_de(cuenta.pk), Pedido.Causa.AGRONOMO_INACTIVO, actor)
    if not cancelados:
        return Efecto([], {})
    return Efecto(cancelados, {"pedidos_cancelados": [referencia(p) for p in cancelados]})


def asignaciones_de_cuenta(cuenta):
    """`core.registrar_asignaciones_de_cuenta` (regla 4 de USR-BAJ-USR): los pedidos «en cotización» de un Agrónomo, y qué pasará con ellos. Solo lectura."""
    if rol_de(cuenta) != Usuario.Rol.AGRONOMO:
        return []
    cantidad = _en_cotizacion_de(cuenta.pk).count()
    if not cantidad:
        return []
    # La ventana de baja de ``core`` muestra ``texto`` y ``que_pasa`` pero no ``cantidad``: el número va también en el texto de lo que pasa.
    cuantos = "Es 1" if cantidad == 1 else f"Son {cantidad}"
    return [
        Asignacion(
            "Pedidos de cotización en curso",
            cantidad,
            f"{cuantos}: se cancelan solos al confirmar la baja y se avisa por correo a los proveedores invitados.",
        )
    ]


# ---- maestros: traspaso del Agrónomo ----


def contar_traspaso(invernadero, rol, saliente, entrante):
    """`maestros.registrar_traspaso`, ``contar``: siempre vacío. Los pedidos del saliente no pasan al entrante: se cancelan, y eso lo dice ``aviso_de_traspaso``
    (si se informaran acá, la ventana y la notificación dirían que el Agrónomo entrante «recibe» pedidos que ya no existen)."""
    return []


def aviso_de_traspaso(invernadero, rol, saliente, entrante):
    """`maestros.registrar_aviso_de_traspaso`: lo que se cancela al cambiar al Agrónomo del invernadero (regla 2 de PROD-MOD-INV), con o sin entrante. Solo
    lectura; una sola consulta. Vacío para otro rol, sin saliente o sin pedidos con destino a ese invernadero."""
    if rol != ROL_AGRONOMO or saliente is None:
        return []
    cantidad = _con_destino(_en_cotizacion_de(saliente.pk), invernadero).count()
    if not cantidad:
        return []
    nombre = saliente.get_full_name() or saliente.email
    if cantidad == 1:
        cuantos = "Se cancela 1 pedido de cotización en curso"
    else:
        cuantos = f"Se cancelan {cantidad} pedidos de cotización en curso"
    return [f"{cuantos} de {nombre} con destino a este invernadero. Se avisa por correo a los proveedores invitados."]


def traspasar_pedidos(actor, invernadero, rol, saliente, entrante):
    """`maestros.registrar_traspaso`, ``traspasar`` (MD-62, H17): cancela con la causa ``agronomo_sin_invernadero`` los pedidos «en cotización» del Agrónomo
    saliente con algún detalle a ``invernadero`` (el pedido entero, aunque tenga otros destinos). Devuelve los pedidos cancelados, que ``modificar_invernadero``
    deja entre los afectados de su registro (D-36, D-60 punto 4). Corre con el invernadero ya guardado y bloqueado; bloquea los pedidos en orden de id."""
    if rol != ROL_AGRONOMO or saliente is None:
        return []
    return _cancelar_todos(_con_destino(_en_cotizacion_de(saliente.pk), invernadero), Pedido.Causa.AGRONOMO_SIN_INVERNADERO, actor)


# ---- inventario: deshabilitar el insumo (H20) ----


def impedimento_de_deshabilitacion(insumo_invernadero):
    """`inventario.registrar_impedimento_de_deshabilitacion` (H20, D-87 punto 5): un impedimento ``pedido_en_curso`` por cada pedido «en cotización» que pide ese
    ``InsumoInvernadero``, con el enlace a su ficha. No se cancela solo. Solo lectura; una sola consulta."""
    en_curso = Pedido.objects.filter(
        estado_pedido=Pedido.Estado.EN_COTIZACION,
        pk__in=DetallePedido.objects.filter(insumo_invernadero=insumo_invernadero).values("pedido_id"),
    ).order_by("id")
    return [
        Impedimento(
            "pedido_en_curso",
            f"Está en el pedido {pedido}, en cotización hasta el {pedido.fecha_limite_cotizaciones:%d/%m}.",
            "Esperá a que se cierre o que el Agrónomo que lo hizo lo cancele.",
            reverse("compras:pedido_ficha", args=[pedido.pk]),
        )
        for pedido in en_curso
    ]
