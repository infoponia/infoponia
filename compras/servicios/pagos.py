# CMP-REG-PAG · Registrar Pago a Proveedor (CMP-05). Fuente: docs/casos_de_uso/compras/pagos.md («Cómo se aplica (código)»), docs/modelo/compras.md («Pago»), D-91 (el pago: cuándo está
# pendiente, la bandeja, el aviso, la fecha, el asiento y quién paga), D-89 puntos 4 y 6 (el monto es Σ ``valor_recibido`` del acumulado final y se guarda), D-85 (``puede_registrar_asientos``),
# D-86 (el asiento va por último y el ejercicio se bloquea al final), D-102 (el asiento automático nunca se rechaza por la fecha; la fecha del pago sí se valida antes con ``automatico=False``).
#
# «Pago pendiente» se CALCULA, no se guarda (D-91 punto 2, D-14): ``pagos_pendientes`` es la consulta única que usan la bandeja, el atajo de la lista de órdenes y la baja del proveedor.
# Una sola ruta de validación sirve al detalle (paso 4), al resumen (paso 6) y al registro (paso 8): ``detalle_del_pago`` → ``resumir_pago`` → ``registrar_pago``.
#
# Orden de bloqueo del pago (docs/patrones/bloqueos.md, «compras»): cuentas → ``OrdenCompra`` → líneas del proveedor → ``Pago`` (la única ``(orden, proveedor)`` es la red) → ejercicio, que
# bloquea la función de asientos AL FINAL.

from collections import defaultdict, namedtuple
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Sum
from django.http import Http404
from django.urls import reverse

from compras.errores import ErrorDeCompras
from compras.models import DetalleOrdenCompra, DetalleRecepcion, InconvenienteRecepcion, OrdenCompra, Pago, Proveedor, Recepcion
from compras.precios import precio_unitario_para_mostrar, valor_recibido
from compras.servicios import enlaces
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import CuentaContable
from contabilidad.servicios import asientos, ejercicios, responsables
from core.correo import correo_configurado, enviar_correo
from core.models import RegistroAuditoria, referencia
from inventario.servicios import stock
from inventario.servicios.formato import texto_precio
from maestros.servicios.invernaderos import _actor_sigue_activo

CERO = Decimal("0.00")
TITULO_DEL_AVISO = "Proveedor para pagar"
Estado = DetalleOrdenCompra.Estado
# Una orden con algo para pagar está al menos «parcialmente recibida» (un proveedor puede estar listo mientras el otro todavía recibe).
ESTADOS_DE_ORDEN_CON_RECEPCION = (OrdenCompra.Estado.PARCIALMENTE_RECIBIDA, OrdenCompra.Estado.RECIBIDA, OrdenCompra.Estado.RECIBIDA_CON_FALTANTE)

PagoPendiente = namedtuple("PagoPendiente", "orden proveedor cantidad_de_lineas monto listo_desde")
LineaDePago = namedtuple("LineaDePago", "detalle insumo pedida recibida total unitario a_pagar estado motivo_cierre no_aceptada")
DetalleDelPago = namedtuple("DetalleDelPago", "orden proveedor lineas monto recepciones listo_desde")
ResumenDePago = namedtuple("ResumenDePago", "detalle medio fecha movimientos ejercicio")


# ---------------------------------------------------------------------------------------------------------------------------------
# La consulta única de lo pendiente y el aviso
# ---------------------------------------------------------------------------------------------------------------------------------


def pagos_pendientes(*, proveedor=None, orden=None):
    """D-91 punto 2: los pares (orden, proveedor) sin ``Pago`` cuyas líneas están todas «completo» o «cerrado con faltante» y con algo recibido en al menos una, del que espera hace más tiempo al más
    reciente (por ``listo_desde``: la mayor fecha entre la última recepción y el último cierre con faltante del par; desempata por orden y proveedor). ``monto`` es Σ ``valor_recibido(línea, recibido)``
    (D-89 punto 4). ``proveedor`` y ``orden`` filtran. Una consulta por tabla, no una por fila."""
    lineas = DetalleOrdenCompra.objects.filter(orden__estado_orden_compra__in=ESTADOS_DE_ORDEN_CON_RECEPCION).annotate(proveedor_pk=F("detalle_cotizacion__cotizacion__proveedor_id"))
    if orden is not None:
        lineas = lineas.filter(orden_id=orden.pk)
    if proveedor is not None:
        lineas = lineas.filter(detalle_cotizacion__cotizacion__proveedor_id=proveedor.pk)
    grupos = defaultdict(list)
    for linea in lineas.order_by("id"):
        grupos[(linea.orden_id, linea.proveedor_pk)].append(linea)
    if not grupos:
        return []
    orden_ids = {o for o, _ in grupos}
    pagados = set(Pago.objects.filter(orden_id__in=orden_ids).values_list("orden_id", "proveedor_id"))
    recibido = {
        fila["detalle_orden_id"]: fila["total"]
        for fila in DetalleRecepcion.objects.filter(detalle_orden__orden_id__in=orden_ids).values("detalle_orden_id").annotate(total=Sum("cantidad_recibida_detalle"))
    }
    ultima_recepcion = {
        (fila["orden_id"], fila["proveedor_id"]): fila["fecha"]
        for fila in Recepcion.objects.filter(orden_id__in=orden_ids).values("orden_id", "proveedor_id").annotate(fecha=Max("fecha_recepcion"))
    }
    listos = []
    for clave, suyas in grupos.items():
        todas_cerradas = all(l.estado_detalle_orden in (Estado.COMPLETO, Estado.CERRADO_CON_FALTANTE) for l in suyas)
        con_algo = any(recibido.get(l.pk, CERO) > 0 for l in suyas)
        if clave in pagados or not todas_cerradas or not con_algo:
            continue
        fechas = [f for f in [ultima_recepcion.get(clave), *(l.fecha_cierre_faltante for l in suyas)] if f is not None]
        monto = sum((valor_recibido(l, recibido.get(l.pk, CERO)) for l in suyas), CERO)
        listos.append((clave, len(suyas), monto, max(fechas)))
    ordenes = {o.pk: o for o in OrdenCompra.objects.filter(pk__in={c[0][0] for c in listos})}
    proveedores = {p.pk: p for p in Proveedor.objects.filter(pk__in={c[0][1] for c in listos})}
    pendientes = [PagoPendiente(ordenes[o], proveedores[p], cantidad, monto, desde) for (o, p), cantidad, monto, desde in listos]
    return sorted(pendientes, key=lambda x: (x.listo_desde, x.orden.pk, x.proveedor.pk))


def avisar_si_quedo_para_pagar(orden, proveedor, *, actor):
    """D-91 punto 3 y H23 punto 2: si el par (orden, proveedor) está para pagar, avisa «Proveedor para pagar» al responsable contable (D-85), sin quien hizo la acción (H21, ``excluir=actor``). La llaman,
    **dentro de la transacción** (D-42), ``registrar_recepcion`` y ``cerrar_con_faltante``: una recepción o un cierre solo pueden dejar listo un par que antes tenía líneas pendientes, así que no hace falta
    comparar con el estado anterior. Devuelve la notificación o ``None`` (par no listo o sin pago, sin responsable, o el responsable es el actor). La del pago no la repite: el par pagado ya no figura."""
    pendientes = pagos_pendientes(orden=orden, proveedor=proveedor)
    if not pendientes:
        return None
    pendiente = pendientes[0]
    detalle = f"{proveedor.nombre_para_mostrar} · {orden}: todo lo suyo quedó recibido o cerrado. Monto a pagar: ${texto_precio(pendiente.monto)}."
    return responsables.notificar_al_responsable_contable(TITULO_DEL_AVISO, detalle, excluir=actor)


# ---------------------------------------------------------------------------------------------------------------------------------
# Pasos 4 y 6: el detalle y el resumen
# ---------------------------------------------------------------------------------------------------------------------------------


def _exigir_responsable(actor):
    """Precondición a y extensión 1a: el Contador activo o, sin Contador activo, el Gerente (``responsables.puede_registrar_asientos``). Con un Contador activo, el Gerente recibe «Lo registra el Contador»."""
    if responsables.puede_registrar_asientos(actor):
        return
    if actor is not None and getattr(actor, "is_active", False) and responsables.contador_activo() is not None and actor.pk != responsables.contador_activo().pk:
        raise PermissionDenied("Lo registra el Contador.")
    raise PermissionDenied("Solo el Contador, o el Gerente si no hay un Contador activo, registra pagos a proveedores.")


def detalle_del_pago(actor, orden_id, proveedor_id):
    """Paso 4: por cada línea del proveedor en la orden, el insumo, lo pedido, lo recibido, el total de la línea, el precio unitario calculado (dos decimales, D-89 punto 7) y el subtotal a pagar; las
    líneas cerradas con faltante con su motivo; lo no aceptado (lo declarado como inconveniente que no es «otro»); las recepciones y el monto total. Solo lectura.

    Errores: ``PermissionDenied`` (1a), ``Http404`` (la orden no existe), ``proveedor_ajeno`` (no es de la orden), ``pago_ya_registrado`` (2a y 8a; ``datos["pago_id"]``) y ``sin_pago_pendiente`` (con líneas
    pendientes o sin nada recibido)."""
    _exigir_responsable(actor)
    orden = OrdenCompra.objects.filter(pk=orden_id).first()
    if orden is None:
        raise Http404("No existe esa orden de compra.")
    proveedor = Proveedor.objects.filter(pk=proveedor_id).first()
    detalles = list(
        DetalleOrdenCompra.objects.filter(orden=orden, detalle_cotizacion__cotizacion__proveedor_id=proveedor_id)
        .select_related("detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo")
        .order_by("id")
    )
    if proveedor is None or not detalles:
        raise ErrorDeCompras("proveedor_ajeno", "Ese proveedor no tiene líneas en la orden.", datos={"orden": orden.pk})
    existente = Pago.objects.filter(orden=orden, proveedor=proveedor).first()
    if existente is not None:
        raise ErrorDeCompras(
            "pago_ya_registrado", f"Ya se registró el pago {existente} a {proveedor.nombre_para_mostrar} por la orden {orden}.", datos={"pago_id": existente.pk, "orden": orden.pk}
        )
    pendientes = pagos_pendientes(orden=orden, proveedor=proveedor)
    if not pendientes:
        raise ErrorDeCompras(
            "sin_pago_pendiente",
            f"{proveedor.nombre_para_mostrar} no tiene un pago pendiente en la orden {orden}: todavía tiene líneas por recibir o no se le recibió nada.",
            datos={"orden": orden.pk},
        )
    ids = [d.pk for d in detalles]
    recibido = {i: CERO for i in ids}
    for fila in DetalleRecepcion.objects.filter(detalle_orden_id__in=ids).values("detalle_orden_id").annotate(total=Sum("cantidad_recibida_detalle")):
        recibido[fila["detalle_orden_id"]] = fila["total"]
    no_aceptada = {i: CERO for i in ids}
    for fila in (
        InconvenienteRecepcion.objects.filter(detalle_recepcion__detalle_orden_id__in=ids)
        .exclude(tipo_inconveniente=InconvenienteRecepcion.Tipo.OTRO)
        .values("detalle_recepcion__detalle_orden_id")
        .annotate(total=Sum("cantidad_afectada"))
    ):
        no_aceptada[fila["detalle_recepcion__detalle_orden_id"]] = fila["total"]
    lineas = [
        LineaDePago(
            d,
            d.detalle_cotizacion.detalle_pedido.insumo_invernadero.insumo,
            d.cantidad_detalle_orden,
            recibido[d.pk],
            d.total_linea,
            precio_unitario_para_mostrar(d),
            valor_recibido(d, recibido[d.pk]),
            d.estado_detalle_orden,
            d.motivo_cierre_faltante,
            no_aceptada[d.pk],
        )
        for d in detalles
    ]
    recepciones = list(Recepcion.objects.filter(orden=orden, proveedor=proveedor).order_by("id"))
    return DetalleDelPago(orden, proveedor, lineas, pendientes[0].monto, recepciones, pendientes[0].listo_desde)


def _cuenta_del_haber(medio):
    """Regla «Medio de pago» (regla 15 de 8.13): el efectivo sale de Caja y los demás medios, de Banco c/c."""
    return cuentas.CAJA if medio == Pago.MedioPago.EFECTIVO else cuentas.BANCO


def resumir_pago(actor, orden_id, proveedor_id, medio, fecha, *, hoy=None):
    """Paso 6: valida el medio (5a: obligatorio, sin preselección), la fecha (5b: ``ejercicio_para(fecha, automatico=False)``, D-91 punto 4) y que existan las cuentas (8b), y calcula el asiento que se
    registrará (Debe Proveedores / Haber Caja o Banco c/c) y el ejercicio donde caerá. No escribe ni bloquea. ``fecha=None`` es hoy; ``hoy`` se recibe para no leer el reloj.

    Los errores de la fecha y de las cuentas son ``ErrorContable`` (``fecha_futura``, ``fecha_en_ejercicio_cerrado``, ``fecha_anterior_al_primer_ejercicio`` con ``campo="fecha"``; ``cuenta_inexistente``)."""
    detalle = detalle_del_pago(actor, orden_id, proveedor_id)
    if not medio:
        raise ErrorDeCompras("medio_obligatorio", "Elegí el medio de pago.", campo="medio_pago")
    if medio not in Pago.MedioPago.values:
        raise ErrorDeCompras("medio_invalido", "Ese medio de pago no existe: elegí efectivo, transferencia, tarjeta de débito o tarjeta de crédito.", campo="medio_pago")
    hoy = hoy or stock.hoy()
    fecha = fecha or hoy
    ejercicio = ejercicios.ejercicio_para(fecha, automatico=False, hoy=hoy)
    haber = _cuenta_del_haber(medio)
    existentes = set(CuentaContable.objects.filter(codigo_cuenta__in=[cuentas.PROVEEDORES, haber]).values_list("codigo_cuenta", flat=True))
    for codigo in (cuentas.PROVEEDORES, haber):
        if codigo not in existentes:
            raise ErrorContable("cuenta_inexistente", f"La cuenta contable {codigo} no existe en el plan de cuentas: no se puede registrar el pago.")
    movimientos = [(cuentas.PROVEEDORES, DEBE, detalle.monto), (haber, HABER, detalle.monto)]
    return ResumenDePago(detalle, medio, fecha, movimientos, ejercicio)


# ---------------------------------------------------------------------------------------------------------------------------------
# Paso 8: registrar
# ---------------------------------------------------------------------------------------------------------------------------------


def registrar_pago(actor, orden_id, proveedor_id, medio, fecha, *, hoy=None):
    """CMP-REG-PAG paso 8: registra el pago y lo devuelve (docs/casos_de_uso/compras/pagos.md). El monto no lo escribe el actor: lo calcula ``detalle_del_pago`` (regla «Monto»).

    En una sola transacción: bloquea la orden y las líneas del proveedor, **vuelve a validar con todo bloqueado** (``resumir_pago``: 8a, 5a, 5b y 8b), crea el ``Pago`` (la restricción única
    ``(orden, proveedor)`` es la red: su ``IntegrityError`` es ``pago_ya_registrado``), pide **por último** el asiento (D-86 punto 2: el ejercicio se bloquea al final, dentro de la función de asientos) y
    audita ``registro_pago_proveedor`` nombrando el asiento. El correo al proveedor sale en ``on_commit``, fuera de la transacción (9a)."""
    _exigir_responsable(actor)
    with transaction.atomic():
        list(OrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(pk=orden_id))
        list(
            DetalleOrdenCompra.objects.select_for_update(no_key=True, of=("self",))
            .filter(orden_id=orden_id, detalle_cotizacion__cotizacion__proveedor_id=proveedor_id)
            .order_by("id")
        )
        _actor_sigue_activo(actor)
        resumen = resumir_pago(actor, orden_id, proveedor_id, medio, fecha, hoy=hoy)
        detalle = resumen.detalle
        try:
            with transaction.atomic():
                pago = Pago.objects.create(
                    orden=detalle.orden, proveedor=detalle.proveedor, fecha_pago=resumen.fecha, medio_pago=resumen.medio, monto_pago=detalle.monto
                )
        except IntegrityError as error:
            existente = Pago.objects.filter(orden=detalle.orden, proveedor=detalle.proveedor).first()
            if existente is None:
                raise
            raise ErrorDeCompras(
                "pago_ya_registrado", f"Ya se registró el pago {existente} a {detalle.proveedor.nombre_para_mostrar}.", datos={"pago_id": existente.pk}
            ) from error
        # Lo último que se hace (D-86 punto 2): el ejercicio se bloquea al final, dentro de la función de asientos.
        asiento = asientos.registrar_asiento_automatico(actor, pago, resumen.fecha, resumen.movimientos)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REGISTRO_PAGO_PROVEEDOR,
            afectados=[pago, detalle.orden, detalle.proveedor],
            detalle={
                "datos": {
                    "asiento": referencia(asiento),
                    "medio_pago": pago.medio_pago,
                    "fecha_pago": pago.fecha_pago.isoformat(),
                    "monto_pago": texto_precio(pago.monto_pago),
                }
            },
        )
        transaction.on_commit(lambda: enviar_pago(pago.pk))
    return pago


def enviar_pago(pago_id):
    """Postcondición d: al proveedor, el monto, el medio de pago, la fecha y la orden. Corre fuera de toda transacción (``on_commit``); sin el correo configurado no sale nada y un fallo no revierte el pago (9a)."""
    if not correo_configurado():
        return
    pago = Pago.objects.select_related("orden", "proveedor").get(pk=pago_id)
    enviar_correo(
        enlaces.Destinatario(pago.proveedor.pk, pago.proveedor.email_proveedor),
        f"Pago registrado · {pago.orden}",
        "compras/correo/pago.txt",
        {
            "proveedor": pago.proveedor.nombre_para_mostrar,
            "orden": str(pago.orden),
            "pago": str(pago),
            "monto": texto_precio(pago.monto_pago),
            "medio": pago.get_medio_pago_display(),
            "fecha": pago.fecha_pago,
        },
    )


def enlace_de_origen(origen):
    """``contabilidad.registrar_enlace_de_origen("pago", …)``: el texto del pago y la ficha de su orden. ``origen`` es el ``OrigenDocumento``; ``None`` si no es un pago."""
    pago = Pago.objects.select_related("orden").filter(pk=origen.pk).first()
    if pago is None:
        return None
    return f"{pago} · {pago.orden}", reverse("compras:orden_ficha", args=[pago.orden_id])
