# CMP-COR-RCP · Corregir Recepción (CMP-06). Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md («Cómo se aplica (código)»), docs/modelo/compras.md («CorreccionRecepcion»), D-89 punto 4 (el asiento
# inverso es la diferencia de valor acumulado de cada línea), D-90 (puntos 1 a 5: la función de `inventario`, el tipo de movimiento nuevo, los vínculos, «el lote creado por esa recepción» y el
# orden de bloqueo), D-91 (la bandeja se calcula: corregir nunca avisa, solo saca al proveedor), D-86 (el asiento va por último y el ejercicio se bloquea al final) y D-88 punto 6 (sin reintentos de correo).
# Una sola ruta de validación sirve a la lista (pasos 2 a 4), al resumen (paso 7) y al registro (paso 9): ``_planificar`` calcula qué pasaría; ``registrar_correccion`` lo aplica con todo bloqueado y releído.
#
# Orden de bloqueo (D-90 punto 5, siempre ``no_key``): invernadero → ``Insumo`` → ``InsumoInvernadero`` → lotes → ``OrdenCompra`` → líneas de la orden → ``DetalleRecepcion`` → (ejercicio, dentro de la
# función de asientos, al final). La corrección lee sin bloquear para saber qué tomar, bloquea y vuelve a leer (la lista de lo máximo corregible se calcula de nuevo con todo bloqueado).

from collections import defaultdict, namedtuple
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from django.urls import reverse

from compras.errores import ErrorDeCompras
from compras.models import (
    CorreccionRecepcion,
    DetalleCorreccionRecepcion,
    DetalleOrdenCompra,
    DetalleRecepcion,
    DetalleRecepcionMovimiento,
    Pago,
    Recepcion,
)
from compras.precios import valor_recibido
from compras.servicios import enlaces
from compras.servicios import recepciones as rcp
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.servicios import asientos
from core.correo import correo_configurado, enviar_correo
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import InsumoInvernadero
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.unidades import Unidad, validar_cantidad
from maestros.servicios.invernaderos import _actor_sigue_activo

CERO = Decimal("0")
INCONSISTENTE = "inv_stock_inconsistente"
Estado = DetalleOrdenCompra.Estado
MOTIVO_CERRADA = "cerrada_con_faltante"
MOTIVO_SIN_STOCK = "sin_stock_en_el_lote"

LineaCorregible = namedtuple("LineaCorregible", "detalle_recepcion insumo recibida lotes maxima motivo_bloqueo")
RecepcionCorregible = namedtuple("RecepcionCorregible", "recepcion orden proveedor invernadero lineas")
LineaCorregida = namedtuple(
    "LineaCorregida", "detalle_recepcion cantidad recibida_antes recibida_despues lotes stock_antes stock_despues transito_antes transito_despues estado_despues"
)
ResumenDeCorreccion = namedtuple("ResumenDeCorreccion", "recepcion lineas estado_orden monto_asiento alertas_que_se_reactivan avisa_al_proveedor")


# ---------------------------------------------------------------------------------------------------------------------------------
# Lo común: qué se puede corregir de cada línea
# ---------------------------------------------------------------------------------------------------------------------------------


def _recepcion(recepcion_id):
    """La recepción con lo que hace falta para decidir, o ``Http404``."""
    recepcion = Recepcion.objects.select_related("orden", "proveedor", "invernadero").filter(pk=recepcion_id).first()
    if recepcion is None:
        raise Http404("No existe esa recepción.")
    return recepcion


def _pago_de(recepcion):
    """El ``Pago`` del proveedor de la recepción en esa orden, o ``None`` (precondición c: el pago se calcula sobre lo recibido, regla 13 de 8.20)."""
    return Pago.objects.filter(orden_id=recepcion.orden_id, proveedor_id=recepcion.proveedor_id).first()


def _exigir_sin_pago(recepcion):
    """Precondición c y extensión 9a: ``pago_registrado`` si el par (orden, proveedor) ya tiene su pago."""
    pago = _pago_de(recepcion)
    if pago is not None:
        raise ErrorDeCompras(
            "pago_registrado",
            f"A {recepcion.proveedor.nombre_para_mostrar} ya se le pagó la orden {recepcion.orden} ({pago}): una recepción solo se corrige antes del pago.",
            datos={"pago_id": pago.pk, "orden": recepcion.orden_id},
        )


def _lineas_de(recepcion):
    """``list[LineaCorregible]`` de todas las líneas de la recepción (también las que llegaron en 0, con máxima 0), con lo que hay AHORA en la base. Máxima de cada línea (D-90 punto 4):
    Σ ``min(lo que el lote conserva, lo que esta recepción ingresó en él − lo ya corregido de ese lote)``; el faltante sin lote no cuenta (ya se consumió)."""
    detalles = list(
        DetalleRecepcion.objects.filter(recepcion=recepcion)
        .select_related(
            "detalle_orden__detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo",
            "detalle_orden__detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero",
        )
        .order_by("id")
    )
    movimientos = defaultdict(list)
    for detalle_id, movimiento_id in DetalleRecepcionMovimiento.objects.filter(detalle_recepcion__in=detalles).order_by("id").values_list("detalle_recepcion_id", "movimiento_id"):
        movimientos[detalle_id].append(movimiento_id)
    corregido = defaultdict(lambda: CERO)
    for fila in DetalleCorreccionRecepcion.objects.filter(detalle_recepcion__in=detalles).values("detalle_recepcion_id", "movimiento__lote_insumo_id").annotate(total=Sum("cantidad_corregida")):
        corregido[(fila["detalle_recepcion_id"], fila["movimiento__lote_insumo_id"])] = fila["total"]
    lineas = []
    for d in detalles:
        lotes, maxima = [], CERO
        for lote, ingresado in stock.lotes_de_ingreso(movimientos[d.pk]):
            corregible = max(CERO, min(lote.cantidad_disponible, ingresado - corregido[(d.pk, lote.pk)]))
            lotes.append((lote, corregible))
            maxima += corregible
        if d.detalle_orden.estado_detalle_orden == Estado.CERRADO_CON_FALTANTE:
            motivo = MOTIVO_CERRADA
        elif maxima == 0:
            motivo = MOTIVO_SIN_STOCK
        else:
            motivo = None
        lineas.append(LineaCorregible(d, rcp._existencia(d.detalle_orden).insumo, d.cantidad_recibida_detalle, lotes, maxima, motivo))
    return lineas


# ---------------------------------------------------------------------------------------------------------------------------------
# Pasos 2 a 4: lo que hay para corregir
# ---------------------------------------------------------------------------------------------------------------------------------


def recepciones_corregibles(actor, orden_id=None):
    """Pasos 2 y 3: las recepciones de los invernaderos a cargo del Agrónomo (todas, si es el Gerente) cuyo proveedor todavía no tiene pago en esa orden y que tienen alguna línea con algo recibido, de la
    más antigua a la más reciente. Cada una trae su orden, su proveedor, su invernadero y sus líneas recibidas. ``orden_id`` filtra por orden (se llega desde la ficha de la orden). Solo lectura."""
    rcp._exigir_quien_recibe(actor)
    consulta = Recepcion.objects.select_related("orden", "proveedor", "invernadero").order_by("id")
    if orden_id is not None:
        consulta = consulta.filter(orden_id=orden_id)
    if rol_de(actor) == Usuario.Rol.AGRONOMO:
        consulta = consulta.filter(invernadero__agronomo_id=actor.pk)
    recepciones = list(consulta)
    pagados = set(Pago.objects.filter(orden_id__in={r.orden_id for r in recepciones}).values_list("orden_id", "proveedor_id"))
    resultado = []
    for recepcion in recepciones:
        if (recepcion.orden_id, recepcion.proveedor_id) in pagados:
            continue
        lineas = [l for l in _lineas_de(recepcion) if l.recibida > 0]
        if lineas:
            resultado.append(RecepcionCorregible(recepcion, recepcion.orden, recepcion.proveedor, recepcion.invernadero, lineas))
    return resultado


def lineas_corregibles(actor, recepcion_id):
    """Paso 4: las líneas de la recepción con cantidad recibida mayor que cero: el insumo, lo recibido, los lotes que creó con lo que cada uno permite corregir, la máxima corregible y, si no se puede
    corregir, el ``motivo_bloqueo`` («cerrada_con_faltante», 4b, o «sin_stock_en_el_lote», 4a). Errores: ``PermissionDenied``, ``Http404`` y ``pago_registrado``. Solo lectura."""
    rcp._exigir_quien_recibe(actor)
    recepcion = _recepcion(recepcion_id)
    rcp._exigir_a_cargo(actor, [recepcion.invernadero_id])
    _exigir_sin_pago(recepcion)
    return [l for l in _lineas_de(recepcion) if l.recibida > 0]


# ---------------------------------------------------------------------------------------------------------------------------------
# Pasos 5 a 7: validar y calcular qué pasaría
# ---------------------------------------------------------------------------------------------------------------------------------


def _planificar(actor, recepcion_id, lineas):
    """Valida la corrección contra lo que hay AHORA en la base y calcula qué pasaría; no escribe ni bloquea. Errores en el orden del caso de uso: permisos, recepción, alcance, pago (c), sin líneas (5b),
    línea repetida, línea ajena, línea cerrada con faltante (4b) y, por línea, cantidad inválida y supera lo corregible (5a, 4a y 9a)."""
    rcp._exigir_quien_recibe(actor)
    recepcion = _recepcion(recepcion_id)
    rcp._exigir_a_cargo(actor, [recepcion.invernadero_id])
    _exigir_sin_pago(recepcion)
    lineas = list(lineas)
    if not lineas:
        raise ErrorDeCompras("sin_lineas", "La corrección tiene que incluir al menos una línea con la cantidad a descontar.")
    ids = [i for i, _ in lineas]
    repetidas = sorted({i for i in ids if ids.count(i) > 1})
    if repetidas:
        raise ErrorDeCompras("linea_repetida", "Una línea no puede aparecer dos veces en la misma corrección.", datos={"lineas": repetidas})
    por_id = {l.detalle_recepcion.pk: l for l in _lineas_de(recepcion)}
    ajenas = [i for i in ids if i not in por_id]
    if ajenas:
        raise ErrorDeCompras("linea_ajena", "Hay líneas que no son de esa recepción.", datos={"lineas": ajenas})
    cerradas = [i for i in ids if por_id[i].motivo_bloqueo == MOTIVO_CERRADA]
    if cerradas:
        raise ErrorDeCompras(
            "linea_cerrada_con_faltante", "Una línea cerrada con faltante no se corrige.", datos={"linea": cerradas[0], "lineas": cerradas}
        )
    detalles = rcp._detalles_de(recepcion.orden_id)
    detalle_de_orden = {d.pk: d for d in detalles}
    acumulado = rcp._recibido_de([d.pk for d in detalles])
    planes = []
    for detalle_recepcion_id, cantidad in lineas:
        linea = por_id[detalle_recepcion_id]
        detalle = detalle_de_orden[linea.detalle_recepcion.detalle_orden_id]
        existencia = rcp._existencia(detalle)
        unidad = existencia.insumo.unidad_medida_insumo
        try:
            cantidad = validar_cantidad(cantidad, unidad)
        except (ValidationError, TypeError, ArithmeticError) as error:
            raise ErrorDeCompras(
                "cantidad_invalida", f"La cantidad de {existencia.insumo.nombre_insumo} tiene que ser un número con los decimales que admite la unidad.", campo="cantidad", datos={"linea": detalle_recepcion_id}
            ) from error
        if cantidad <= 0:
            raise ErrorDeCompras("cantidad_invalida", "La cantidad tiene que ser mayor que cero.", campo="cantidad", datos={"linea": detalle_recepcion_id})
        if cantidad > linea.maxima:
            raise ErrorDeCompras(
                "supera_lo_corregible",
                f"De {existencia.insumo.nombre_insumo} se pueden descontar como máximo {texto_cantidad(linea.maxima, unidad)}."
                + (" Lo restante se resuelve con un ajuste de stock." if linea.maxima < linea.recibida else ""),
                campo="cantidad",
                datos={"linea": detalle_recepcion_id, "maxima": linea.maxima},
            )
        # D-90 punto 4: se descuenta lote por lote, del más nuevo al más viejo.
        partes, por_descontar = [], cantidad
        for lote, corregible in sorted(linea.lotes, key=lambda par: par[0].pk, reverse=True):
            tomado = min(corregible, por_descontar)
            if tomado > 0:
                partes.append((lote, tomado))
                por_descontar -= tomado
        antes = acumulado[detalle.pk]
        planes.append(
            SimpleNamespace(
                detalle_recepcion=linea.detalle_recepcion,
                detalle=detalle,
                existencia=existencia,
                unidad=unidad,
                cantidad=cantidad,
                partes=partes,
                acumulado_antes=antes,
                valor=valor_recibido(detalle, antes) - valor_recibido(detalle, antes - cantidad),
            )
        )
    estados = {d.pk: d.estado_detalle_orden for d in detalles}
    for p in planes:
        if estados[p.detalle.pk] == Estado.COMPLETO:
            estados[p.detalle.pk] = Estado.PENDIENTE
    orden = recepcion.orden
    return SimpleNamespace(
        recepcion=recepcion,
        orden=orden,
        planes=planes,
        estados=estados,
        estado_orden=rcp._estado_de_la_orden(estados.values(), orden.estado_orden_compra, True),
        monto=sum((p.valor for p in planes), Decimal("0.00")),
    )


def resumir_correccion(actor, recepcion_id, lineas):
    """Paso 7: por línea, la nueva cantidad recibida, los lotes de los que se descuenta, cómo cambian el stock y el tránsito y el estado en que queda; el estado de la orden, el monto del asiento inverso, las
    alertas que se reactivarán (solo «stock inconsistente»: el tránsito sube lo que baja el stock, así que «bajo el mínimo» no cambia) y que se avisará al proveedor. Mismas validaciones que
    ``registrar_correccion``; no escribe."""
    plan = _planificar(actor, recepcion_id, lineas)
    ids = [p.existencia.pk for p in plan.planes]
    stock_actual = stock.stock_actual_de(ids)
    existencias = stock.existencias(ids)
    resultado, alertas = [], []
    for p in plan.planes:
        e = existencias[p.existencia.pk]
        resultado.append(
            LineaCorregida(
                p.detalle_recepcion,
                p.cantidad,
                p.detalle_recepcion.cantidad_recibida_detalle,
                p.detalle_recepcion.cantidad_recibida_detalle - p.cantidad,
                p.partes,
                stock_actual[p.existencia.pk],
                stock_actual[p.existencia.pk] - p.cantidad,
                e.transito,
                e.transito + p.cantidad,
                plan.estados[p.detalle.pk],
            )
        )
        if not e.inconsistente and e.vigente - p.cantidad < e.reservado:
            alertas.append((INCONSISTENTE, p.existencia))
    return ResumenDeCorreccion(plan.recepcion, resultado, plan.estado_orden, plan.monto, alertas, True)


# ---------------------------------------------------------------------------------------------------------------------------------
# Paso 9: registrar
# ---------------------------------------------------------------------------------------------------------------------------------


def _auditar_existencia(actor, existencia, unidad, transito, stock_, orden, correccion):
    """D-87 punto 8: una ``modificacion_insumo_invernadero`` con el tránsito y el stock antes y después. ``transito`` y ``stock_`` son ``(antes, después)``."""
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO,
        afectados=[existencia, existencia.invernadero],
        detalle={
            "cambios": {
                "transito": {"antes": texto_cantidad(transito[0], unidad), "despues": texto_cantidad(transito[1], unidad)},
                "stock": {"antes": texto_cantidad(stock_[0], unidad), "despues": texto_cantidad(stock_[1], unidad)},
            },
            "datos": {"orden": referencia(orden), "correccion": referencia(correccion)},
        },
    )


def registrar_correccion(actor, recepcion_id, lineas, observacion=""):
    """CMP-COR-RCP paso 9: registra la corrección y la devuelve (docs/casos_de_uso/compras/correccion_y_reclamos.md). ``lineas = [(detalle_recepcion_id, cantidad)]``.

    Lee sin bloquear para saber qué tomar, bloquea en el orden de D-90 punto 5 y **vuelve a validar** con todo bloqueado (9a: el pago, el lote). Crea la corrección (un ``OrigenDocumento``); por cada línea
    descuenta lote por lote del más nuevo al más viejo (``stock.registrar_salida_por_correccion_de_recepcion``, que sube el tránsito y reevalúa las alertas) con su ``DetalleCorreccionRecepcion``, baja la
    cantidad recibida, vuelve la línea de la orden a «pendiente» y recalcula la orden; y **por último** pide el asiento inverso (Debe Proveedores / Haber Insumos en Stock por la diferencia del valor
    acumulado de cada línea, D-89 punto 4). No toca inconvenientes ni reclamos (R3) y no avisa a la bandeja de pagos: el proveedor sale solo porque la bandeja se calcula (D-91 punto 3). Audita todo
    en la misma transacción; el correo al proveedor sale en ``on_commit``."""
    previo = _planificar(actor, recepcion_id, lineas)
    existencias = [p.existencia for p in previo.planes]
    with transaction.atomic():
        rcp._bloquear(
            {e.invernadero_id for e in existencias} | {previo.recepcion.invernadero_id}, {e.insumo_id for e in existencias}, {e.pk for e in existencias}, previo.orden.pk
        )
        list(DetalleRecepcion.objects.select_for_update(no_key=True, of=("self",)).filter(recepcion_id=previo.recepcion.pk).order_by("id"))
        _actor_sigue_activo(actor)
        plan = _planificar(actor, recepcion_id, lineas)
        hoy = stock.hoy()
        estado_antes = plan.orden.estado_orden_compra

        correccion = CorreccionRecepcion.objects.create(
            recepcion_corregida=plan.recepcion,
            fecha_correccion=hoy,
            observacion=(observacion or "").strip(),
            agronomo_id=actor.pk if rol_de(actor) == Usuario.Rol.AGRONOMO else None,
        )
        movimientos, vueltas_a_pendiente = [], []
        for p in plan.planes:
            stock_antes = stock.stock_actual_de([p.existencia.pk])[p.existencia.pk]
            transito_antes = InsumoInvernadero.objects.get(pk=p.existencia.pk).cant_transito_insumo
            for lote, cantidad in p.partes:
                movimiento = stock.registrar_salida_por_correccion_de_recepcion(lote.pk, cantidad, origen_id=correccion.pk)
                DetalleCorreccionRecepcion.objects.create(correccion=correccion, detalle_recepcion=p.detalle_recepcion, cantidad_corregida=cantidad, movimiento=movimiento)
                movimientos.append(movimiento)
            p.detalle_recepcion.cantidad_recibida_detalle -= p.cantidad
            p.detalle_recepcion.save(update_fields=["cantidad_recibida_detalle"])
            if p.detalle.estado_detalle_orden == Estado.COMPLETO:
                p.detalle.estado_detalle_orden = Estado.PENDIENTE
                p.detalle.save(update_fields=["estado_detalle_orden"])
                vueltas_a_pendiente.append(p.detalle)
            _auditar_existencia(actor, p.existencia, p.unidad, (transito_antes, transito_antes + p.cantidad), (stock_antes, stock_antes - p.cantidad), plan.orden, correccion)
        if plan.estado_orden != estado_antes:
            plan.orden.estado_orden_compra = plan.estado_orden
            plan.orden.save(update_fields=["estado_orden_compra"])

        # Lo último que se hace (D-86 punto 2): el ejercicio se bloquea al final, dentro de la función de asientos.
        asiento = asientos.registrar_asiento_automatico(
            actor, correccion, hoy, [(cuentas.PROVEEDORES, DEBE, plan.monto), (cuentas.INSUMOS_EN_STOCK, HABER, plan.monto)]
        )

        datos = {"movimientos": [referencia(m) for m in movimientos], "lineas_que_vuelven_a_pendiente": [referencia(d) for d in vueltas_a_pendiente]}
        if asiento is not None:
            datos["asiento"] = referencia(asiento)
            datos["monto_del_asiento"] = texto_precio(plan.monto)
        if correccion.observacion:
            datos["observacion"] = correccion.observacion
        detalle_de_auditoria = {"datos": datos}
        if plan.estado_orden != estado_antes:
            detalle_de_auditoria["cambios"] = {"estado": {"antes": estado_antes, "despues": plan.estado_orden}}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.CORRECCION_RECEPCION,
            afectados=[correccion, *[p.detalle_recepcion for p in plan.planes], *[p.detalle for p in plan.planes], plan.orden],
            detalle=detalle_de_auditoria,
        )
        transaction.on_commit(lambda: enviar_correccion(correccion.pk))
    return correccion


# ---------------------------------------------------------------------------------------------------------------------------------
# Correo al proveedor (postcondición g): fuera de la transacción, y un fallo no revierte nada (extensión 10a, D-88 punto 6)
# ---------------------------------------------------------------------------------------------------------------------------------


def enviar_correccion(correccion_id):
    """Postcondición g y lista de tecnología 10: al proveedor, la orden, la recepción corregida y su fecha, por línea el insumo y la cantidad corregida, y lo que sigue pendiente de sus líneas. No
    menciona a otros proveedores. Corre fuera de toda transacción (``on_commit``); sin el correo configurado no sale nada y no se reintenta."""
    if not correo_configurado():
        return
    correccion = CorreccionRecepcion.objects.select_related("recepcion_corregida__orden", "recepcion_corregida__proveedor", "recepcion_corregida__invernadero").get(pk=correccion_id)
    recepcion = correccion.recepcion_corregida
    corregido = defaultdict(lambda: CERO)
    for fila in DetalleCorreccionRecepcion.objects.filter(correccion=correccion).select_related("detalle_recepcion__detalle_orden"):
        corregido[fila.detalle_recepcion.detalle_orden_id] += fila.cantidad_corregida
    detalles = rcp._detalles_de(recepcion.orden_id)
    lineas = []
    for d in detalles:
        if d.pk in corregido:
            insumo = rcp._existencia(d).insumo
            lineas.append({"insumo": insumo.nombre_insumo, "unidad": Unidad(insumo.unidad_medida_insumo).label, "corregida": texto_cantidad(corregido[d.pk], insumo.unidad_medida_insumo)})
    propias = [d for d in detalles if d.detalle_cotizacion.cotizacion.proveedor_id == recepcion.proveedor_id and d.estado_detalle_orden == Estado.PENDIENTE]
    recibido = rcp._recibido_de([d.pk for d in propias])
    pendientes = [
        {
            "insumo": rcp._existencia(d).insumo.nombre_insumo,
            "unidad": Unidad(rcp._existencia(d).insumo.unidad_medida_insumo).label,
            "falta": texto_cantidad(d.cantidad_detalle_orden - recibido[d.pk], rcp._existencia(d).insumo.unidad_medida_insumo),
            "invernadero": rcp._existencia(d).invernadero.nombre_invernadero,
        }
        for d in propias
    ]
    enviar_correo(
        enlaces.Destinatario(recepcion.proveedor.pk, recepcion.proveedor.email_proveedor),
        f"Corrección de recepción · {recepcion.orden}",
        "compras/correo/correccion.txt",
        {
            "proveedor": recepcion.proveedor.nombre_para_mostrar,
            "orden": str(recepcion.orden),
            "recepcion": str(recepcion),
            "correccion": str(correccion),
            "fecha": recepcion.fecha_recepcion,
            "invernadero": recepcion.invernadero.nombre_invernadero,
            "observacion": correccion.observacion,
            "lineas": lineas,
            "pendientes": pendientes,
        },
    )


# ---------------------------------------------------------------------------------------------------------------------------------
# Registrante de `ready()` (regla A4 de D-37)
# ---------------------------------------------------------------------------------------------------------------------------------


def enlace_de_origen(origen):
    """``contabilidad.registrar_enlace_de_origen("correccion_de_recepcion", …)``: el texto de la corrección y la ficha de su orden. ``origen`` es el ``OrigenDocumento``; ``None`` si no es una corrección."""
    correccion = CorreccionRecepcion.objects.select_related("recepcion_corregida__orden").filter(pk=origen.pk).first()
    if correccion is None:
        return None
    orden = correccion.recepcion_corregida.orden
    return f"{correccion} · {orden}", reverse("compras:orden_ficha", args=[orden.pk])
