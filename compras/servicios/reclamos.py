# CMP-EMT-RCL · Emitir Reclamo a Proveedor y CMP-CRR-RCL · Cerrar Reclamo a Proveedor (CMP-06), más la lectura de reclamos. Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md («Cómo se aplica
# (código)» y los dos casos de uso de alto nivel), docs/modelo/compras.md («ReclamoProveedor» y «AlertaCompras»), D-87 punto 5 (la alerta del Gerente y su vínculo), D-88 punto 6 (sin reintentos de correo)
# y D-36 (auditoría). CMP-04 crea el reclamo «abierto» y sin emitir junto con la recepción; acá el Gerente lo emite (con el correo al proveedor) y después lo cierra. Un reclamo cerrado no se reabre.
#
# Orden de bloqueo (docs/patrones/bloqueos.md, «compras»): invernadero de la recepción (``bloquear_invernadero_para_alertas``: activo o no, porque se resuelve una alerta) → ``ReclamoProveedor`` → la alerta.
# El cierre toma el mismo invernadero, así que una emisión y un cierre del mismo reclamo quedan en fila.

from collections import defaultdict, namedtuple

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404

from compras.errores import ErrorDeCompras
from compras.models import AlertaCompras, InconvenienteRecepcion, ReclamoProveedor
from compras.servicios import enlaces
from compras.servicios import recepciones as rcp
from core.correo import correo_configurado, enviar_correo
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad
from inventario.unidades import Unidad
from maestros.servicios import alertas as servicio_de_alertas
from maestros.servicios.invernaderos import _actor_sigue_activo

ACCION_EMITIR = "emitir"
ACCION_CERRAR = "cerrar"
FILTROS_DE_ESTADO = ("sin_emitir", "emitido_abierto", "cerrado")

FilaDeReclamo = namedtuple("FilaDeReclamo", "reclamo recepcion orden proveedor invernadero inconvenientes")
FichaDeReclamo = namedtuple("FichaDeReclamo", "reclamo recepcion orden proveedor invernadero inconvenientes acciones")


def _exigir_gerente(actor):
    """Precondición a de CMP-EMT-RCL y CMP-CRR-RCL: solo el Gerente con la cuenta activa (``PermissionDenied``)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo el Gerente emite y cierra los reclamos a proveedores.")


def _exigir_lectura(actor):
    """Quien ve los reclamos: el Gerente (todos) y el Agrónomo (los de sus invernaderos), ambos activos; si no, ``PermissionDenied``."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
        raise PermissionDenied("Solo el Gerente y el Agrónomo a cargo ven los reclamos a proveedores.")


def _con_inconvenientes(reclamos):
    """``{reclamo_id: [InconvenienteRecepcion]}`` de todos esos reclamos en una consulta, con su insumo y su invernadero para mostrar."""
    resultado = defaultdict(list)
    for i in (
        InconvenienteRecepcion.objects.filter(reclamo__in=reclamos)
        .select_related("detalle_recepcion__detalle_orden__detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo")
        .order_by("id")
    ):
        resultado[i.reclamo_id].append(i)
    return resultado


def reclamos(actor, filtros=None):
    """Los reclamos que ``actor`` ve, del más reciente al más antiguo. ``filtros["estado"]``: ``sin_emitir``, ``emitido_abierto`` o ``cerrado`` (otro valor se ignora); ``filtros["proveedor_id"]``: solo los de ese proveedor. Cada fila trae la recepción, la
    orden, el proveedor, el invernadero y los inconvenientes. Una consulta por tabla. Solo lectura."""
    _exigir_lectura(actor)
    consulta = ReclamoProveedor.objects.select_related("recepcion__orden", "recepcion__invernadero", "proveedor").order_by("-id")
    if rol_de(actor) == Usuario.Rol.AGRONOMO:
        consulta = consulta.filter(recepcion__invernadero__agronomo_id=actor.pk)
    proveedor_id = (filtros or {}).get("proveedor_id")
    if proveedor_id not in (None, ""):  # la ficha del proveedor (regla 4 de CMP-CNS-PRV) pide solo los suyos
        consulta = consulta.filter(proveedor_id=proveedor_id)
    estado = (filtros or {}).get("estado")
    if estado == "sin_emitir":
        consulta = consulta.filter(gerente__isnull=True)
    elif estado == "emitido_abierto":
        consulta = consulta.filter(gerente__isnull=False, estado_reclamo=ReclamoProveedor.Estado.ABIERTO)
    elif estado == "cerrado":
        consulta = consulta.filter(estado_reclamo=ReclamoProveedor.Estado.CERRADO)
    lista = list(consulta)
    inconvenientes = _con_inconvenientes(lista)
    return [FilaDeReclamo(r, r.recepcion, r.recepcion.orden, r.proveedor, r.recepcion.invernadero, inconvenientes[r.pk]) for r in lista]


def ficha_de_reclamo(actor, reclamo_id):
    """Regla 2 de CMP-EMT-RCL: el reclamo con la recepción, la orden, el proveedor, el invernadero y cada inconveniente (tipo, cantidad afectada y descripción), y las ``acciones`` que ``actor`` puede hacer
    (D-30: ningún botón lleva a un 403): «emitir» el Gerente con el reclamo sin emitir y «cerrar» el Gerente con el reclamo emitido y abierto. ``Http404`` si no existe; ``PermissionDenied`` fuera del alcance."""
    _exigir_lectura(actor)
    reclamo = ReclamoProveedor.objects.select_related("recepcion__orden", "recepcion__invernadero", "proveedor").filter(pk=reclamo_id).first()
    if reclamo is None:
        raise Http404("No existe ese reclamo.")
    if rol_de(actor) == Usuario.Rol.AGRONOMO and reclamo.recepcion.invernadero.agronomo_id != actor.pk:
        raise PermissionDenied("Ese reclamo no es de un invernadero a tu cargo.")
    acciones = set()
    if rol_de(actor) == Usuario.Rol.GERENTE:
        if not reclamo.emitido:
            acciones.add(ACCION_EMITIR)
        elif reclamo.estado_reclamo == ReclamoProveedor.Estado.ABIERTO:
            acciones.add(ACCION_CERRAR)
    recepcion = reclamo.recepcion
    return FichaDeReclamo(reclamo, recepcion, recepcion.orden, reclamo.proveedor, recepcion.invernadero, _con_inconvenientes([reclamo])[reclamo.pk], frozenset(acciones))


def _bloquear(reclamo_id):
    """Lee sin bloquear el invernadero de la recepción, lo bloquea (activo o no) y después bloquea y relee el reclamo. ``Http404`` si no existe."""
    previo = ReclamoProveedor.objects.select_related("recepcion").filter(pk=reclamo_id).first()
    if previo is None:
        raise Http404("No existe ese reclamo.")
    servicio_de_alertas.bloquear_invernadero_para_alertas(previo.recepcion.invernadero_id)
    return ReclamoProveedor.objects.select_for_update(no_key=True, of=("self",)).select_related("recepcion__orden", "proveedor").get(pk=reclamo_id)


def emitir_reclamo(actor, reclamo_id):
    """CMP-EMT-RCL: el Gerente deja emitido un reclamo «abierto» sin emitir y lo devuelve. Con el invernadero y el reclamo bloqueados vuelve a verificar que siga sin emitir (``reclamo_ya_emitido``),
    guarda el Gerente y la fecha de hoy (R008: emitido ⇔ tiene Gerente y fecha), resuelve la alerta «recepción con inconvenientes» por su ``AlertaCompras``, audita ``emision_reclamo`` y manda el correo al
    proveedor en ``on_commit`` (R1: emitir es avisarle; no hay reintento si falla, D-88 punto 6). No toca el stock, las líneas ni el pago (regla 3)."""
    _exigir_gerente(actor)
    with transaction.atomic():
        reclamo = _bloquear(reclamo_id)
        _actor_sigue_activo(actor)
        if reclamo.emitido:
            raise ErrorDeCompras("reclamo_ya_emitido", f"El reclamo {reclamo} ya está emitido.", datos={"reclamo": reclamo.pk})
        hoy = stock.hoy()
        reclamo.gerente_id = actor.pk
        reclamo.fecha_reclamo = hoy
        reclamo.save(update_fields=["gerente", "fecha_reclamo"])
        resueltas = []
        for vinculo in AlertaCompras.objects.filter(reclamo=reclamo).select_related("alerta").order_by("id"):
            alerta = servicio_de_alertas.resolver_alerta(vinculo.alerta_id)
            if alerta is not None:
                resueltas.append(alerta)
        datos = {"recepcion": referencia(reclamo.recepcion), "proveedor": referencia(reclamo.proveedor)}
        if resueltas:
            datos["alertas_resueltas"] = [referencia(a) for a in resueltas]
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.EMISION_RECLAMO,
            afectados=[reclamo, reclamo.recepcion, reclamo.proveedor],
            detalle={"cambios": {"gerente": {"antes": None, "despues": referencia(actor)}, "fecha_reclamo": {"antes": None, "despues": hoy.isoformat()}}, "datos": datos},
        )
        transaction.on_commit(lambda: enviar_reclamo(reclamo.pk))
    return reclamo


def cerrar_reclamo(actor, reclamo_id):
    """CMP-CRR-RCL: el Gerente cierra un reclamo emitido y abierto y lo devuelve. Solo se cierra un reclamo emitido (``reclamo_sin_emitir``, regla 1) y un reclamo cerrado no se reabre ni se vuelve a
    cerrar (``reclamo_ya_cerrado``, regla 2). Audita ``cierre_reclamo`` con el cambio de estado. No cambia el stock, las líneas ni el pago, y no manda correo (regla 3)."""
    _exigir_gerente(actor)
    with transaction.atomic():
        reclamo = _bloquear(reclamo_id)
        _actor_sigue_activo(actor)
        if reclamo.estado_reclamo == ReclamoProveedor.Estado.CERRADO:
            raise ErrorDeCompras("reclamo_ya_cerrado", f"El reclamo {reclamo} ya está cerrado.", datos={"reclamo": reclamo.pk})
        if not reclamo.emitido:
            raise ErrorDeCompras("reclamo_sin_emitir", f"El reclamo {reclamo} todavía no se emitió: solo se cierra uno emitido.", datos={"reclamo": reclamo.pk})
        reclamo.estado_reclamo = ReclamoProveedor.Estado.CERRADO
        reclamo.save(update_fields=["estado_reclamo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.CIERRE_RECLAMO,
            afectados=[reclamo, reclamo.recepcion, reclamo.proveedor],
            detalle={"cambios": {"estado_reclamo": {"antes": ReclamoProveedor.Estado.ABIERTO, "despues": ReclamoProveedor.Estado.CERRADO}}},
        )
    return reclamo


def enviar_reclamo(reclamo_id):
    """Postcondición c de CMP-EMT-RCL: al proveedor (y solo a él), el reclamo con la recepción, la orden, el invernadero y cada inconveniente (insumo, tipo, cantidad afectada y descripción). Corre fuera de
    toda transacción (``on_commit``); sin el correo configurado no sale nada y un fallo no revierte la emisión."""
    if not correo_configurado():
        return
    reclamo = ReclamoProveedor.objects.select_related("recepcion__orden", "recepcion__invernadero", "proveedor").get(pk=reclamo_id)
    recepcion = reclamo.recepcion
    lineas = []
    for i in _con_inconvenientes([reclamo])[reclamo.pk]:
        insumo = rcp._existencia(i.detalle_recepcion.detalle_orden).insumo
        lineas.append(
            {
                "insumo": insumo.nombre_insumo,
                "unidad": Unidad(insumo.unidad_medida_insumo).label,
                "tipo": i.get_tipo_inconveniente_display(),
                "cantidad": texto_cantidad(i.cantidad_afectada, insumo.unidad_medida_insumo),
                "descripcion": i.descripcion_inconveniente,
            }
        )
    enviar_correo(
        enlaces.Destinatario(reclamo.proveedor.pk, reclamo.proveedor.email_proveedor),
        f"Reclamo {reclamo} · {recepcion.orden}",
        "compras/correo/reclamo.txt",
        {
            "proveedor": reclamo.proveedor.nombre_para_mostrar,
            "reclamo": str(reclamo),
            "orden": str(recepcion.orden),
            "recepcion": str(recepcion),
            "fecha": recepcion.fecha_recepcion,
            "invernadero": recepcion.invernadero.nombre_invernadero,
            "inconvenientes": lineas,
        },
    )
