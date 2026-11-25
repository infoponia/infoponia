# CMP-REG-RCP · Registrar Recepción de Mercadería y CMP-CRR-FLT · Cerrar Detalle con Faltante (CMP-04). Fuente: docs/casos_de_uso/compras/recepcion.md («Cómo se aplica (código)»), docs/modelo/compras.md,
# D-86 (el asiento va por último y el ejercicio se bloquea al final), D-87 punto 5 (la alerta del Gerente), D-89 punto 4 (el asiento como diferencia de valor acumulado), D-90 (lo que escribe
# `inventario`, vínculos, orden de bloqueo, sobreentrega bloqueada y tipos de inconveniente). Una sola ruta de validación sirve al resumen (sin bloquear ni escribir) y al registro (con todo bloqueado y
# releído): ``_planificar`` y ``_planificar_cierre`` calculan qué pasaría; ``registrar_recepcion`` y ``cerrar_con_faltante`` lo aplican.
#
# Orden de bloqueo (D-90 punto 5, siempre ``no_key``): invernadero → ``Insumo`` → ``InsumoInvernadero`` → lotes → ``OrdenCompra`` → líneas de la orden → (ejercicio, dentro de la función de asientos, al final).

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
    AlertaCompras,
    DetalleOrdenCompra,
    DetalleRecepcion,
    DetalleRecepcionMovimiento,
    InconvenienteRecepcion,
    OrdenCompra,
    Proveedor,
    Recepcion,
    ReclamoProveedor,
)
from compras.precios import valor_recibido
from compras.servicios import enlaces, pagos
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.servicios import asientos
from core.correo import correo_configurado, enviar_correo
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, stock
from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.unidades import Unidad, validar_cantidad
from maestros.extensiones import Enlace
from maestros.models import Alerta, Invernadero
from maestros.servicios import alertas as servicio_de_alertas
from maestros.servicios.invernaderos import _actor_sigue_activo

CERO = Decimal("0")
TIPO_DE_ALERTA = "compras_recepcion_con_inconvenientes"
BAJO_MINIMO = "inv_insumo_bajo_minimo"
ESTADOS_RECIBIBLES = (OrdenCompra.Estado.APROBADA, OrdenCompra.Estado.PARCIALMENTE_RECIBIDA)
Estado = DetalleOrdenCompra.Estado

DatosDeRecepcion = namedtuple("DatosDeRecepcion", "orden_id proveedor_id invernadero_id lineas observaciones", defaults=("",))
LineaRecibida = namedtuple("LineaRecibida", "detalle_orden_id partes inconvenientes", defaults=((),))
EntregaPendiente = namedtuple("EntregaPendiente", "orden proveedor invernadero lineas entrega_esperada atraso_dias bloqueada")
LineaARecibir = namedtuple("LineaARecibir", "detalle insumo existencia pedida recibida falta entrega_esperada atraso_dias motivo_bloqueo")
LineaResumida = namedtuple(
    "LineaResumida", "detalle ingresa cubre_faltante lotes stock_antes stock_despues transito_antes transito_despues estado_despues inconvenientes"
)
ResumenDeRecepcion = namedtuple(
    "ResumenDeRecepcion", "orden proveedor invernadero lineas estado_orden monto_asiento alertas_que_se_resuelven inconvenientes crea_reclamo"
)
LineaPorCerrar = namedtuple("LineaPorCerrar", "orden detalle proveedor invernadero insumo pedida recibida falta entrega_esperada atraso_dias")
LineaCerrada = namedtuple("LineaCerrada", "detalle falta transito_antes transito_despues motivo")
ResumenDeCierre = namedtuple("ResumenDeCierre", "lineas estados_de_ordenes proveedores alertas_que_se_activan")

INVERNADERO_INACTIVO = "invernadero_inactivo"
INSUMO_INACTIVO = "insumo_inactivo"
TIPOS_DE_INCONVENIENTE = InconvenienteRecepcion.Tipo.values


# ---------------------------------------------------------------------------------------------------------------------------------
# Lo común: quién, qué se lee y cómo se calculan los estados
# ---------------------------------------------------------------------------------------------------------------------------------


def _exigir_quien_recibe(actor):
    """Regla «Quién registra» (1a): el Agrónomo o el Gerente con la cuenta activa; si no, ``PermissionDenied``."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
        raise PermissionDenied("Solo el Agrónomo a cargo del invernadero de destino o el Gerente pueden registrar recepciones.")


def _exigir_a_cargo(actor, invernadero_ids):
    """El Gerente recibe en cualquier invernadero; el Agrónomo, solo en los que tiene a cargo (``PermissionDenied``)."""
    ids = set(invernadero_ids)
    if rol_de(actor) == Usuario.Rol.GERENTE:
        return
    a_cargo = set(Invernadero.objects.filter(pk__in=ids, agronomo_id=actor.pk).values_list("pk", flat=True))
    if ids - a_cargo:
        raise PermissionDenied("Ese invernadero no está a tu cargo: solo lo recibe su Agrónomo o el Gerente.")


def _detalles_de(orden_id):
    """Todas las líneas de la orden, en orden de id, con lo que hace falta para decidir sin más consultas."""
    return list(
        DetalleOrdenCompra.objects.filter(orden_id=orden_id)
        .select_related(
            "detalle_cotizacion__cotizacion__proveedor",
            "detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo",
            "detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero",
        )
        .order_by("id")
    )


def _existencia(detalle):
    return detalle.detalle_cotizacion.detalle_pedido.insumo_invernadero


def _recibido_de(detalle_ids):
    """``{detalle_orden_id: Decimal}``: lo que ingresó de cada línea (Σ ``cantidad_recibida_detalle``; derivado, regla de ``/cantidadRecibida``)."""
    sumas = {i: CERO for i in detalle_ids}
    for fila in (
        DetalleRecepcion.objects.filter(detalle_orden_id__in=list(detalle_ids)).values("detalle_orden_id").annotate(total=Sum("cantidad_recibida_detalle"))
    ):
        sumas[fila["detalle_orden_id"]] = fila["total"]
    return sumas


def recibido_por_linea(detalle_ids):
    """``{detalle_orden_id: Decimal}``: lo recibido de cada línea (la ficha de la orden y la lista de líneas lo muestran)."""
    return _recibido_de(detalle_ids)


def _motivo_de_destino_inactivo(detalle):
    """Extensión 4a: ``invernadero_inactivo``, ``insumo_inactivo`` o ``None`` si la línea se puede recibir."""
    existencia = _existencia(detalle)
    if not existencia.invernadero.activo:
        return INVERNADERO_INACTIVO
    if not existencia.activo:
        return INSUMO_INACTIVO
    return None


def _atraso(detalle, hoy):
    """Regla «Retraso» (regla 23 de 8.16): los días de atraso de una línea pendiente con la entrega esperada vencida; 0 si no."""
    entrega = detalle.fecha_entrega_esperada
    return (hoy - entrega).days if entrega is not None and entrega < hoy else 0


def _estado_de_la_orden(estados, actual, hubo_recepcion):
    """Regla 24 de 8.16: ``estados`` son los de todas las líneas después de la operación. Todas completas o cerradas: «recibida con faltante» si alguna está cerrada, «recibida» si no. Si no,
    «parcialmente recibida» con la primera recepción (aunque no haya ingresado nada) y, si no hubo recepción (un cierre), el estado que tenía."""
    valores = list(estados)
    if all(e in (Estado.COMPLETO, Estado.CERRADO_CON_FALTANTE) for e in valores):
        return OrdenCompra.Estado.RECIBIDA_CON_FALTANTE if Estado.CERRADO_CON_FALTANTE in valores else OrdenCompra.Estado.RECIBIDA
    return OrdenCompra.Estado.PARCIALMENTE_RECIBIDA if hubo_recepcion else actual


def _bajo_el_minimo(minimo, libre, transito):
    """Regla de «bajo el mínimo» (sección 1 de docs/patrones/stock.md): mínimo > 0 y libre + tránsito < mínimo."""
    return minimo > 0 and libre + transito < minimo


def _alerta_de_bajo_minimo_activa(existencia):
    return Alerta.objects.filter(
        invernadero_id=existencia.invernadero_id, tipo_alerta=BAJO_MINIMO, clave_estado=f"insumo:{existencia.pk}", estado_alerta=Alerta.Estado.ACTIVA
    ).first()


# ---------------------------------------------------------------------------------------------------------------------------------
# Pasos 2 y 4: lo que hay para recibir
# ---------------------------------------------------------------------------------------------------------------------------------


def _lineas_pendientes(actor, orden_id=None):
    """Las líneas «pendiente» de las órdenes recibibles que ``actor`` puede recibir (el Agrónomo, las de sus invernaderos; el Gerente, todas), en orden de orden, proveedor, invernadero y id."""
    consulta = DetalleOrdenCompra.objects.filter(estado_detalle_orden=Estado.PENDIENTE, orden__estado_orden_compra__in=ESTADOS_RECIBIBLES)
    if orden_id is not None:
        consulta = consulta.filter(orden_id=orden_id)
    if rol_de(actor) == Usuario.Rol.AGRONOMO:
        consulta = consulta.filter(detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero__agronomo_id=actor.pk)
    consulta = consulta.select_related(
        "orden",
        "detalle_cotizacion__cotizacion__proveedor",
        "detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo",
        "detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero",
    )
    return sorted(
        consulta,
        key=lambda d: (d.orden_id, d.detalle_cotizacion.cotizacion.proveedor_id, _existencia(d).invernadero_id, d.pk),
    )


def entregas_pendientes(actor):
    """Paso 2: las entregas pendientes de los invernaderos a cargo del Agrónomo (o de todos, si es el Gerente), agrupadas por orden, proveedor e invernadero, de la fecha de entrega esperada más próxima
    a la más lejana. Cada una trae la orden, las líneas pendientes, la entrega más próxima, los días de atraso (el mayor) y si está ``bloqueada`` (todas sus líneas con el destino inactivo, 4a1)."""
    _exigir_quien_recibe(actor)
    hoy = stock.hoy()
    grupos = defaultdict(list)
    for detalle in _lineas_pendientes(actor):
        grupos[(detalle.orden_id, detalle.detalle_cotizacion.cotizacion.proveedor_id, _existencia(detalle).invernadero_id)].append(detalle)
    entregas = []
    for lineas in grupos.values():
        primera = lineas[0]
        fechas = [d.fecha_entrega_esperada for d in lineas if d.fecha_entrega_esperada is not None]
        entregas.append(
            EntregaPendiente(
                primera.orden,
                primera.detalle_cotizacion.cotizacion.proveedor,
                _existencia(primera).invernadero,
                lineas,
                min(fechas) if fechas else None,
                max(_atraso(d, hoy) for d in lineas),
                all(_motivo_de_destino_inactivo(d) is not None for d in lineas),
            )
        )
    return sorted(entregas, key=lambda e: (e.entrega_esperada is None, e.entrega_esperada, e.orden.pk, e.proveedor.pk, e.invernadero.pk))


def lineas_a_recibir(actor, orden_id, proveedor_id, invernadero_id):
    """Paso 4: las líneas pendientes de esa orden para ese proveedor e invernadero: el insumo, lo pedido, lo ya recibido, lo que falta, la entrega esperada, los días de atraso y, si el destino está
    inactivo, el ``motivo_bloqueo`` (4a: se lista pero no se le puede indicar cantidad). ``Http404`` si la orden no existe; ``PermissionDenied`` si el invernadero no está a cargo."""
    _exigir_quien_recibe(actor)
    if not OrdenCompra.objects.filter(pk=orden_id).exists():
        raise Http404("No existe esa orden de compra.")
    _exigir_a_cargo(actor, [invernadero_id])
    hoy = stock.hoy()
    pendientes = [
        d
        for d in _lineas_pendientes(actor, orden_id)
        if d.detalle_cotizacion.cotizacion.proveedor_id == int(proveedor_id) and _existencia(d).invernadero_id == int(invernadero_id)
    ]
    recibido = _recibido_de([d.pk for d in pendientes])
    return [
        LineaARecibir(
            d,
            _existencia(d).insumo,
            _existencia(d),
            d.cantidad_detalle_orden,
            recibido[d.pk],
            d.cantidad_detalle_orden - recibido[d.pk],
            d.fecha_entrega_esperada,
            _atraso(d, hoy),
            _motivo_de_destino_inactivo(d),
        )
        for d in pendientes
    ]


# ---------------------------------------------------------------------------------------------------------------------------------
# Pasos 5 a 7: validar y calcular qué pasaría
# ---------------------------------------------------------------------------------------------------------------------------------


def _cantidad(valor, unidad, detalle_id):
    """Extensión 7b: la cantidad mayor que cero y con los decimales de la unidad; si no, ``cantidad_invalida``."""
    try:
        cantidad = validar_cantidad(valor, unidad)
    except ValidationError as error:
        raise ErrorDeCompras("cantidad_invalida", error.messages[0], datos={"linea": detalle_id}) from error
    if cantidad <= 0:
        raise ErrorDeCompras("cantidad_invalida", "La cantidad tiene que ser mayor que cero.", datos={"linea": detalle_id})
    return cantidad


def _partes_de(linea, detalle, existencia, hoy):
    """Las partes ``[(cantidad, vencimiento)]`` de una línea, validadas: cantidades (7b) y vencimientos (obligatorio si el insumo lo controla; nunca pasado, 5e; ausente si no lo controla)."""
    insumo, partes = existencia.insumo, []
    for cantidad, vencimiento in linea.partes:
        cantidad = _cantidad(cantidad, insumo.unidad_medida_insumo, detalle.pk)
        if insumo.controla_vencimiento:
            if vencimiento is None:
                raise ErrorDeCompras("vencimiento_obligatorio", f"{insumo.nombre_insumo} controla el vencimiento: indicá la fecha de cada lote.", datos={"linea": detalle.pk})
            if vencimiento < hoy:
                raise ErrorDeCompras(
                    "vencimiento_pasado",
                    f"Lo de {insumo.nombre_insumo} que ya está vencido no ingresa al stock: declaralo como inconveniente.",
                    datos={"linea": detalle.pk},
                )
        elif vencimiento is not None:
            raise ErrorDeCompras("vencimiento_no_aplica", f"{insumo.nombre_insumo} no controla el vencimiento.", datos={"linea": detalle.pk})
        partes.append((cantidad, vencimiento))
    return partes


def _inconvenientes_de(linea, detalle, unidad):
    """Los inconvenientes ``[(tipo, cantidad, descripción)]`` de una línea, validados (7e y 5d): tipo conocido, cantidad mayor que cero, descripción obligatoria en «otro» y uno por tipo."""
    vistos, resultado = set(), []
    for tipo, cantidad, descripcion in linea.inconvenientes:
        descripcion = (descripcion or "").strip()
        try:
            cantidad = validar_cantidad(cantidad, unidad)
        except ValidationError:
            cantidad = CERO
        if tipo not in TIPOS_DE_INCONVENIENTE or cantidad <= 0 or (tipo == InconvenienteRecepcion.Tipo.OTRO and not descripcion):
            raise ErrorDeCompras(
                "inconveniente_incompleto",
                "Un inconveniente necesita su tipo y una cantidad afectada mayor que cero; el tipo «otro» pide además contar qué pasó.",
                datos={"linea": detalle.pk},
            )
        if tipo in vistos:
            raise ErrorDeCompras("inconveniente_repetido", "Una línea tiene a lo sumo un inconveniente de cada tipo.", datos={"linea": detalle.pk})
        vistos.add(tipo)
        resultado.append((tipo, cantidad, descripcion))
    return resultado


def _distribuir(partes, deuda):
    """Cómo reparte ``registrar_ingreso_por_recepcion`` lo recibido: ``(cubierto, [(cantidad, vencimiento)])``: el faltante sin lote absorbe las primeras partes y el resto forma los lotes nuevos."""
    por_cubrir, nuevos = deuda, []
    for cantidad, vencimiento in partes:
        para_el_faltante = min(por_cubrir, cantidad)
        por_cubrir -= para_el_faltante
        if cantidad > para_el_faltante:
            nuevos.append((cantidad - para_el_faltante, vencimiento))
    return deuda - por_cubrir, nuevos


def _planificar(actor, datos):
    """Valida la recepción contra lo que hay AHORA en la base y calcula qué pasaría; no escribe ni bloquea. Quien registra la usa dos veces: sin bloquear (para saber qué tomar) y con todo bloqueado
    (la verificación que vale, 9a y 9b). Los errores salen en el orden del caso de uso: permisos, orden, líneas ajenas, destinos inactivos, líneas ya no pendientes y, por línea, cantidades,
    vencimientos, sobreentrega, líneas en 0 e inconvenientes."""
    _exigir_quien_recibe(actor)
    orden = OrdenCompra.objects.filter(pk=datos.orden_id).first()
    if orden is None:
        raise Http404("No existe esa orden de compra.")
    _exigir_a_cargo(actor, [datos.invernadero_id])
    lineas = list(datos.lineas)
    if not lineas:
        raise ErrorDeCompras("sin_lineas", "La recepción tiene que incluir al menos una línea.")
    if orden.estado_orden_compra not in ESTADOS_RECIBIBLES:
        raise ErrorDeCompras(
            "orden_no_recibible",
            f"La orden {orden} está {orden.get_estado_orden_compra_display().lower()}: solo se recibe una orden aprobada o parcialmente recibida.",
            datos={"estado": orden.estado_orden_compra},
        )
    proveedor = Proveedor.objects.filter(pk=datos.proveedor_id).first()
    invernadero = Invernadero.objects.filter(pk=datos.invernadero_id).first()
    detalles = _detalles_de(orden.pk)
    por_id = {d.pk: d for d in detalles}
    ids = [l.detalle_orden_id for l in lineas]
    if len(set(ids)) != len(ids):
        raise ErrorDeCompras("linea_repetida", "Una línea de la orden no puede aparecer dos veces en la misma recepción.", datos={"lineas": sorted({i for i in ids if ids.count(i) > 1})})
    ajenas = [
        i
        for i in ids
        if i not in por_id
        or proveedor is None
        or invernadero is None
        or por_id[i].detalle_cotizacion.cotizacion.proveedor_id != proveedor.pk
        or _existencia(por_id[i]).invernadero_id != invernadero.pk
    ]
    if ajenas:
        raise ErrorDeCompras(
            "linea_ajena", "Una recepción es de una sola orden, un proveedor y un invernadero: hay líneas que no corresponden.", datos={"lineas": ajenas}
        )
    inactivas = [(i, motivo) for i in ids if (motivo := _motivo_de_destino_inactivo(por_id[i])) is not None]
    if inactivas:
        raise ErrorDeCompras(
            "destino_inactivo", "Hay mercadería para un invernadero o un insumo inactivo: primero hay que reactivarlo.", datos={"lineas": inactivas}
        )
    recibido = _recibido_de([d.pk for d in detalles])
    ya_cerradas = [i for i in ids if por_id[i].estado_detalle_orden != Estado.PENDIENTE]
    if ya_cerradas:
        raise ErrorDeCompras(
            "linea_no_pendiente",
            "Una de las líneas ya no está pendiente (se recibió o se cerró con faltante en otra sesión).",
            datos={"linea": ya_cerradas[0], "lineas": ya_cerradas},
        )

    hoy = stock.hoy()
    planes = []
    for linea in lineas:
        detalle = por_id[linea.detalle_orden_id]
        existencia = _existencia(detalle)
        unidad = existencia.insumo.unidad_medida_insumo
        falta = detalle.cantidad_detalle_orden - recibido[detalle.pk]
        partes = _partes_de(linea, detalle, existencia, hoy)
        ingresa = sum((c for c, _ in partes), CERO)
        if ingresa > falta:
            raise ErrorDeCompras(
                "supera_lo_pendiente",
                f"De {existencia.insumo.nombre_insumo} faltan recibir {texto_cantidad(falta, unidad)}: el excedente no se ingresa (anotalo en las observaciones).",
                campo="cantidad",
                datos={"linea": detalle.pk, "pendiente": falta},
            )
        inconvenientes = _inconvenientes_de(linea, detalle, unidad)
        if ingresa == 0 and not any(t != InconvenienteRecepcion.Tipo.OTRO for t, _, _ in inconvenientes):
            raise ErrorDeCompras(
                "linea_en_cero_sin_inconveniente",
                "Una línea en 0 solo se registra si todo lo que llegó estaba dañado, vencido, no conforme o distinto: declará el inconveniente o sacá la línea.",
                datos={"linea": detalle.pk},
            )
        acumulado_antes = recibido[detalle.pk]
        planes.append(
            SimpleNamespace(
                detalle=detalle,
                existencia=existencia,
                unidad=unidad,
                partes=partes,
                ingresa=ingresa,
                inconvenientes=inconvenientes,
                acumulado_antes=acumulado_antes,
                completa=acumulado_antes + ingresa == detalle.cantidad_detalle_orden,
                valor=valor_recibido(detalle, acumulado_antes + ingresa) - valor_recibido(detalle, acumulado_antes),
            )
        )
    estados = {d.pk: d.estado_detalle_orden for d in detalles}
    for plan in planes:
        if plan.completa:
            estados[plan.detalle.pk] = Estado.COMPLETO
    return SimpleNamespace(
        orden=orden,
        proveedor=proveedor,
        invernadero=invernadero,
        planes=planes,
        estado_orden=_estado_de_la_orden(estados.values(), orden.estado_orden_compra, True),
        monto=sum((p.valor for p in planes), Decimal("0.00")),
    )


def resumir_recepcion(actor, datos):
    """Paso 7: por línea, lo que ingresa al stock, los lotes nuevos (después de cubrir el faltante sin lote), cómo cambian el stock y el tránsito y el estado en que queda; el estado de la orden, el monto del
    asiento, las alertas de bajo el mínimo que se resolverán y los inconvenientes (con el reclamo sin emitir que se generará). Las mismas validaciones que ``registrar_recepcion``; no escribe."""
    plan = _planificar(actor, datos)
    ids = [p.existencia.pk for p in plan.planes]
    stock_actual = stock.stock_actual_de(ids)
    existencias = stock.existencias(ids)
    lineas, alertas, todos = [], [], []
    for p in plan.planes:
        lotes_actuales = LoteInsumo.objects.filter(insumo_invernadero=p.existencia, es_faltante_sin_lote=True, cantidad_disponible__lt=0).first()
        deuda = -lotes_actuales.cantidad_disponible if lotes_actuales else CERO
        cubierto, nuevos = _distribuir(p.partes, deuda)
        e = existencias[p.existencia.pk]
        lineas.append(
            LineaResumida(
                p.detalle,
                p.ingresa,
                cubierto,
                nuevos,
                stock_actual[p.existencia.pk],
                stock_actual[p.existencia.pk] + p.ingresa,
                e.transito,
                e.transito - p.ingresa,
                Estado.COMPLETO if p.completa else Estado.PENDIENTE,
                p.inconvenientes,
            )
        )
        todos.extend(p.inconvenientes)
        activa = _alerta_de_bajo_minimo_activa(p.existencia)
        if p.ingresa > 0 and activa is not None and not _bajo_el_minimo(e.minimo, e.libre + p.ingresa, e.transito - p.ingresa):
            alertas.append(activa)
    return ResumenDeRecepcion(plan.orden, plan.proveedor, plan.invernadero, lineas, plan.estado_orden, plan.monto, alertas, todos, bool(todos))


# ---------------------------------------------------------------------------------------------------------------------------------
# Paso 9: registrar
# ---------------------------------------------------------------------------------------------------------------------------------


def _bloquear(invernadero_ids, insumo_ids, existencia_ids, orden_id):
    """El orden de bloqueo de D-90 punto 5 (siempre ``no_key``): invernadero → ``Insumo`` → ``InsumoInvernadero`` → lotes → orden → líneas de la orden. El ejercicio lo bloquea la función de asientos, al final."""
    list(Invernadero.objects.select_for_update(no_key=True).filter(pk__in=sorted(invernadero_ids)).order_by("id"))
    list(Insumo.objects.select_for_update(no_key=True).filter(pk__in=sorted(insumo_ids)).order_by("id"))
    list(InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=sorted(existencia_ids)).order_by("id"))
    list(LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero_id__in=sorted(existencia_ids)).order_by("insumo_invernadero_id", "id"))
    list(OrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(pk=orden_id))
    list(DetalleOrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(orden_id=orden_id).order_by("id"))


def _auditar_existencia(actor, existencia, unidad, transito, stock_, orden, recepcion=None):
    """D-87 punto 8: una ``modificacion_insumo_invernadero`` con el tránsito (y el stock, si cambió) antes y después. ``transito`` y ``stock_`` son ``(antes, después)``."""
    cambios = {"transito": {"antes": texto_cantidad(transito[0], unidad), "despues": texto_cantidad(transito[1], unidad)}}
    if stock_ is not None:
        cambios["stock"] = {"antes": texto_cantidad(stock_[0], unidad), "despues": texto_cantidad(stock_[1], unidad)}
    datos = {"orden": referencia(orden)}
    if recepcion is not None:
        datos["recepcion"] = referencia(recepcion)
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO,
        afectados=[existencia, existencia.invernadero],
        detalle={"cambios": cambios, "datos": datos},
    )


def _descripcion_de_la_alerta(recepcion, proveedor, invernadero, reclamo, inconvenientes):
    """Lista de tecnología 7f: la recepción, el proveedor, el invernadero, el reclamo sin emitir y la cantidad de inconvenientes por tipo."""
    por_tipo = defaultdict(int)
    for tipo, _, _ in inconvenientes:
        por_tipo[InconvenienteRecepcion.Tipo(tipo).label.lower()] += 1
    cantidades = ", ".join(f"{n} {tipo}" for tipo, n in por_tipo.items())
    return (
        f"{recepcion} de {proveedor.nombre_para_mostrar} en {invernadero.nombre_invernadero}: reclamo {reclamo} sin emitir. "
        f"{len(inconvenientes)} inconveniente{'s' if len(inconvenientes) != 1 else ''} ({cantidades})."
    )


def registrar_recepcion(actor, datos):
    """CMP-REG-RCP paso 9: registra la recepción y la devuelve (docs/casos_de_uso/compras/recepcion.md).

    Lee sin bloquear para saber qué tomar, bloquea en el orden de D-90 punto 5 y **vuelve a validar** con todo bloqueado (9a y 9b). Crea la recepción (un ``OrigenDocumento``) y sus líneas; por cada línea
    con cantidad mayor que cero ingresa el stock (``stock.registrar_ingreso_por_recepcion``, que cubre primero el faltante sin lote, y resuelve las alertas) y vincula cada movimiento; actualiza los estados
    de las líneas y de la orden; si hay inconvenientes, crea el reclamo sin emitir, la alerta del Gerente y su ``AlertaCompras``; y **por último** pide el asiento (Debe Insumos en Stock / Haber Proveedores,
    por la diferencia del valor acumulado de cada línea: D-89 punto 4). Audita todo en la misma transacción; el correo al proveedor sale en ``on_commit``."""
    previo = _planificar(actor, datos)
    existencias = [p.existencia for p in previo.planes]
    with transaction.atomic():
        _bloquear(
            {e.invernadero_id for e in existencias} | {datos.invernadero_id},
            {e.insumo_id for e in existencias},
            {e.pk for e in existencias},
            previo.orden.pk,
        )
        _actor_sigue_activo(actor)
        plan = _planificar(actor, datos)
        hoy = stock.hoy()
        estado_antes = plan.orden.estado_orden_compra

        recepcion = Recepcion.objects.create(
            fecha_recepcion=hoy,
            observaciones_recepcion=(datos.observaciones or "").strip(),
            orden=plan.orden,
            agronomo_id=actor.pk if rol_de(actor) == Usuario.Rol.AGRONOMO else None,
            proveedor=plan.proveedor,
            invernadero=plan.invernadero,
        )
        detalles_de_recepcion, movimientos, lotes_nuevos, completas = [], [], [], []
        for p in plan.planes:
            detalle_de_recepcion = DetalleRecepcion.objects.create(recepcion=recepcion, detalle_orden=p.detalle, cantidad_recibida_detalle=p.ingresa)
            detalles_de_recepcion.append(detalle_de_recepcion)
            if p.ingresa > 0:
                stock_antes = stock.stock_actual_de([p.existencia.pk])[p.existencia.pk]
                transito_antes = InsumoInvernadero.objects.get(pk=p.existencia.pk).cant_transito_insumo
                creados = stock.registrar_ingreso_por_recepcion(p.existencia.pk, p.partes, origen_id=recepcion.pk)
                for movimiento in creados:
                    DetalleRecepcionMovimiento.objects.create(detalle_recepcion=detalle_de_recepcion, movimiento=movimiento)
                    if not movimiento.lote_insumo.es_faltante_sin_lote:
                        lotes_nuevos.append(movimiento.lote_insumo)
                movimientos.extend(creados)
                _auditar_existencia(
                    actor,
                    p.existencia,
                    p.unidad,
                    (transito_antes, transito_antes - p.ingresa),
                    (stock_antes, stock_antes + p.ingresa),
                    plan.orden,
                    recepcion,
                )
            if p.completa:
                p.detalle.estado_detalle_orden = Estado.COMPLETO
                p.detalle.save(update_fields=["estado_detalle_orden"])
                completas.append(p.detalle)
        if plan.estado_orden != estado_antes:
            plan.orden.estado_orden_compra = plan.estado_orden
            plan.orden.save(update_fields=["estado_orden_compra"])

        inconvenientes, reclamo, alerta = [], None, None
        con_inconvenientes = [(dr, p.inconvenientes) for dr, p in zip(detalles_de_recepcion, plan.planes) if p.inconvenientes]
        if con_inconvenientes:
            reclamo = ReclamoProveedor.objects.create(proveedor=plan.proveedor, recepcion=recepcion)
            todos = []
            for detalle_de_recepcion, lista in con_inconvenientes:
                for tipo, cantidad, descripcion in lista:
                    inconvenientes.append(
                        InconvenienteRecepcion.objects.create(
                            detalle_recepcion=detalle_de_recepcion, reclamo=reclamo, tipo_inconveniente=tipo, cantidad_afectada=cantidad, descripcion_inconveniente=descripcion
                        )
                    )
                    todos.append((tipo, cantidad, descripcion))
            alerta = servicio_de_alertas.crear_alerta_de_evento(
                plan.invernadero.pk, TIPO_DE_ALERTA, _descripcion_de_la_alerta(recepcion, plan.proveedor, plan.invernadero, reclamo, todos)
            )
            if alerta is not None:
                AlertaCompras.objects.create(alerta=alerta, reclamo=reclamo)

        # Lo último que se hace (D-86 punto 2): el ejercicio se bloquea al final, dentro de la función de asientos.
        asiento = asientos.registrar_asiento_automatico(
            actor, recepcion, hoy, [(cuentas.INSUMOS_EN_STOCK, DEBE, plan.monto), (cuentas.PROVEEDORES, HABER, plan.monto)]
        )

        datos_de_auditoria = {"movimientos": [referencia(m) for m in movimientos], "lotes_nuevos": [referencia(l) for l in lotes_nuevos], "lineas_completas": [referencia(d) for d in completas]}
        if inconvenientes:
            datos_de_auditoria["inconvenientes"] = [f"{i.detalle_recepcion.detalle_orden}: {i} ({texto_cantidad(i.cantidad_afectada, _existencia(i.detalle_recepcion.detalle_orden).insumo.unidad_medida_insumo)})" for i in inconvenientes]
            datos_de_auditoria["reclamo"] = referencia(reclamo)
            if alerta is not None:
                datos_de_auditoria["alertas_creadas"] = [referencia(alerta)]
        if asiento is not None:
            datos_de_auditoria["asiento"] = referencia(asiento)
            datos_de_auditoria["monto_del_asiento"] = texto_precio(plan.monto)
        cambios = {}
        if plan.estado_orden != estado_antes:
            cambios["estado"] = {"antes": estado_antes, "despues": plan.estado_orden}
        detalle_de_auditoria = {"datos": datos_de_auditoria}
        if cambios:
            detalle_de_auditoria["cambios"] = cambios
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.RECEPCION_MERCADERIA,
            afectados=[recepcion, *detalles_de_recepcion, *[p.detalle for p in plan.planes], plan.orden, *inconvenientes, *([reclamo] if reclamo else [])],
            detalle=detalle_de_auditoria,
        )
        # CMP-05 (D-91 punto 3): si el proveedor quedó para pagar, aviso al responsable contable (D-42: dentro de la transacción, sin quien registra).
        pagos.avisar_si_quedo_para_pagar(plan.orden, plan.proveedor, actor=actor)
        transaction.on_commit(lambda: enviar_recepcion(recepcion.pk))
    return recepcion


# ---------------------------------------------------------------------------------------------------------------------------------
# Correos al proveedor (postcondición h de la recepción y R1 del cierre): fuera de la transacción, y un fallo no revierte nada
# ---------------------------------------------------------------------------------------------------------------------------------


def _correo_del_proveedor(proveedor):
    return enlaces.Destinatario(proveedor.pk, proveedor.email_proveedor)


def enviar_recepcion(recepcion_id):
    """Postcondición h y lista de tecnología 10: al proveedor, la orden y la fecha, el invernadero de destino y, por línea, lo recibido y lo que tuvo inconveniente; las líneas que siguen pendientes con lo
    que falta. No menciona a los otros proveedores. Corre fuera de toda transacción (``on_commit``); sin el correo configurado no sale nada."""
    if not correo_configurado():
        return
    recepcion = Recepcion.objects.select_related("orden", "proveedor", "invernadero").get(pk=recepcion_id)
    lineas = []
    for d in DetalleRecepcion.objects.filter(recepcion=recepcion).select_related("detalle_orden").order_by("id"):
        insumo = _existencia(d.detalle_orden).insumo
        unidad = insumo.unidad_medida_insumo
        lineas.append(
            {
                "insumo": insumo.nombre_insumo,
                "unidad": Unidad(unidad).label,
                "recibida": texto_cantidad(d.cantidad_recibida_detalle, unidad),
                "inconvenientes": [
                    {"tipo": i.get_tipo_inconveniente_display(), "cantidad": texto_cantidad(i.cantidad_afectada, unidad), "descripcion": i.descripcion_inconveniente}
                    for i in d.inconvenientes.order_by("id")
                ],
            }
        )
    propias = [d for d in _detalles_de(recepcion.orden_id) if d.detalle_cotizacion.cotizacion.proveedor_id == recepcion.proveedor_id and d.estado_detalle_orden == Estado.PENDIENTE]
    recibido = _recibido_de([d.pk for d in propias])
    pendientes = [
        {
            "insumo": _existencia(d).insumo.nombre_insumo,
            "unidad": Unidad(_existencia(d).insumo.unidad_medida_insumo).label,
            "falta": texto_cantidad(d.cantidad_detalle_orden - recibido[d.pk], _existencia(d).insumo.unidad_medida_insumo),
            "invernadero": _existencia(d).invernadero.nombre_invernadero,
        }
        for d in propias
    ]
    enviar_correo(
        _correo_del_proveedor(recepcion.proveedor),
        f"Recepción de mercadería · {recepcion.orden}",
        "compras/correo/recepcion.txt",
        {
            "proveedor": recepcion.proveedor.nombre_para_mostrar,
            "orden": str(recepcion.orden),
            "recepcion": str(recepcion),
            "fecha": recepcion.fecha_recepcion,
            "invernadero": recepcion.invernadero.nombre_invernadero,
            "lineas": lineas,
            "pendientes": pendientes,
        },
    )


def enviar_cierre(proveedor_id, lineas):
    """R1 y postcondición f del cierre: al proveedor, que no se espera el resto de las líneas cerradas. ``lineas = [(detalle_orden_id, faltante)]``. Fuera de la transacción (``on_commit``)."""
    if not correo_configurado():
        return
    proveedor = Proveedor.objects.get(pk=proveedor_id)
    detalles = {d.pk: d for d in DetalleOrdenCompra.objects.filter(pk__in=[i for i, _ in lineas]).select_related("orden")}
    por_orden = defaultdict(list)
    for detalle_id, faltante in lineas:
        detalle = detalles[detalle_id]
        existencia = _existencia(_detalle_completo(detalle_id))
        unidad = existencia.insumo.unidad_medida_insumo
        por_orden[detalle.orden].append(
            {"insumo": existencia.insumo.nombre_insumo, "unidad": Unidad(unidad).label, "faltante": texto_cantidad(faltante, unidad), "invernadero": existencia.invernadero.nombre_invernadero}
        )
    for orden, lista in por_orden.items():
        enviar_correo(
            _correo_del_proveedor(proveedor),
            f"Líneas cerradas con faltante · {orden}",
            "compras/correo/cierre_faltante.txt",
            {"proveedor": proveedor.nombre_para_mostrar, "orden": str(orden), "lineas": lista},
        )


def _detalle_completo(detalle_id):
    return DetalleOrdenCompra.objects.select_related(
        "detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo", "detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero"
    ).get(pk=detalle_id)


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-CRR-FLT · Cerrar Detalle con Faltante
# ---------------------------------------------------------------------------------------------------------------------------------


def lineas_pendientes_de_cierre(actor, orden_id=None, recepcion_id=None):
    """Paso 2: las líneas pendientes de las órdenes de los invernaderos del Agrónomo (todas, si es el Gerente), agrupadas por orden, proveedor e invernadero: insumo, pedida, recibida, lo que falta, la entrega
    esperada y sus días de atraso. Con ``orden_id`` (se llega desde la ficha de la orden) solo esa orden; con ``recepcion_id`` (extensión 2a, desde el aviso de recepción parcial) solo las líneas de esa
    recepción que siguen pendientes."""
    _exigir_quien_recibe(actor)
    hoy = stock.hoy()
    lineas = _lineas_pendientes(actor, orden_id)
    if recepcion_id is not None:
        de_la_recepcion = set(DetalleRecepcion.objects.filter(recepcion_id=recepcion_id).values_list("detalle_orden_id", flat=True))
        lineas = [d for d in lineas if d.pk in de_la_recepcion]
    recibido = _recibido_de([d.pk for d in lineas])
    return [
        LineaPorCerrar(
            d.orden,
            d,
            d.detalle_cotizacion.cotizacion.proveedor,
            _existencia(d).invernadero,
            _existencia(d).insumo,
            d.cantidad_detalle_orden,
            recibido[d.pk],
            d.cantidad_detalle_orden - recibido[d.pk],
            d.fecha_entrega_esperada,
            _atraso(d, hoy),
        )
        for d in lineas
    ]


def _planificar_cierre(actor, lineas):
    """Valida el cierre contra lo que hay AHORA y calcula qué pasaría; no escribe ni bloquea. Orden de los errores: permisos, sin líneas, línea repetida, motivo obligatorio (4a), que cada línea
    sea de un invernadero a cargo del actor (``PermissionDenied``) y, por último, línea que no existe o ya no pendiente (7a)."""
    _exigir_quien_recibe(actor)
    lineas = [(i, (m or "").strip()) for i, m in lineas]
    if not lineas:
        raise ErrorDeCompras("sin_lineas", "Elegí al menos una línea para cerrar con faltante.")
    ids = [i for i, _ in lineas]
    repetidas = sorted({i for i in ids if ids.count(i) > 1})
    if repetidas:
        raise ErrorDeCompras("linea_repetida", "Una línea no puede aparecer dos veces en el mismo cierre.", datos={"lineas": repetidas})
    sin_motivo = [i for i, motivo in lineas if not motivo]
    if sin_motivo:
        raise ErrorDeCompras("motivo_obligatorio", "Contá por qué no va a llegar lo que falta de cada línea.", campo="motivo", datos={"lineas": sin_motivo})
    detalles = {
        d.pk: d
        for d in DetalleOrdenCompra.objects.filter(pk__in=ids).select_related(
            "orden",
            "detalle_cotizacion__cotizacion__proveedor",
            "detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo",
            "detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero",
        )
    }
    _exigir_a_cargo(actor, {_existencia(d).invernadero_id for d in detalles.values()})
    no_pendientes = [i for i in ids if i not in detalles or detalles[i].estado_detalle_orden != Estado.PENDIENTE or detalles[i].orden.estado_orden_compra not in ESTADOS_RECIBIBLES]
    if no_pendientes:
        raise ErrorDeCompras(
            "linea_no_pendiente",
            "Alguna de las líneas ya no está pendiente (se recibió o se cerró en otra sesión): no se cerró ninguna.",
            datos={"lineas": no_pendientes},
        )
    recibido = _recibido_de(ids)
    motivos = dict(lineas)
    return detalles, ids, motivos, recibido


def _efectos_del_cierre(detalles, ids, motivos, recibido):
    """Qué pasa con cada línea, cada existencia, cada orden y cada proveedor si se cierran ``ids``: ``(lineas, por_existencia, estados_de_ordenes, proveedores)``."""
    lineas, por_existencia = [], {}
    for i in sorted(ids):
        d = detalles[i]
        existencia = _existencia(d)
        falta = d.cantidad_detalle_orden - recibido[i]
        transito = por_existencia.get(existencia.pk, [existencia, existencia.cant_transito_insumo, existencia.cant_transito_insumo])
        antes = transito[2]
        transito[2] = antes - falta
        por_existencia[existencia.pk] = transito
        lineas.append(LineaCerrada(d, falta, antes, antes - falta, motivos[i]))
    estados, proveedores = {}, {}
    for orden in {detalles[i].orden for i in ids}:
        todas = _detalles_de(orden.pk)
        recibido_total = _recibido_de([d.pk for d in todas])
        despues = {d.pk: (Estado.CERRADO_CON_FALTANTE if d.pk in ids else d.estado_detalle_orden) for d in todas}
        estados[orden.pk] = _estado_de_la_orden(despues.values(), orden.estado_orden_compra, False)
        for proveedor in {detalles[i].detalle_cotizacion.cotizacion.proveedor for i in ids if detalles[i].orden_id == orden.pk}:
            suyas = [d for d in todas if d.detalle_cotizacion.cotizacion.proveedor_id == proveedor.pk]
            todas_cerradas = all(despues[d.pk] in (Estado.COMPLETO, Estado.CERRADO_CON_FALTANTE) for d in suyas)
            proveedores[(orden.pk, proveedor.pk)] = (proveedor, todas_cerradas and any(recibido_total[d.pk] > 0 for d in suyas))
    return lineas, por_existencia, estados, list(proveedores.values())


def resumir_cierre(actor, lineas):
    """Paso 5: por línea, la cantidad faltante y cómo cambia el tránsito; el estado en que quedará cada orden; si cada proveedor queda para pagar (todas sus líneas completas o cerradas y algo recibido: la
    bandeja y el aviso son de CMP-05) o sin pago; y las existencias que pasarán a estar bajo el mínimo. Mismas validaciones que el cierre; no escribe."""
    detalles, ids, motivos, recibido = _planificar_cierre(actor, lineas)
    cerradas, por_existencia, estados, proveedores = _efectos_del_cierre(detalles, ids, motivos, recibido)
    ids_de_existencias = list(por_existencia)
    existencias = stock.existencias(ids_de_existencias)
    activan = []
    for iin_id, (existencia, _, despues) in sorted(por_existencia.items()):
        e = existencias[iin_id]
        if not _bajo_el_minimo(e.minimo, e.libre, e.transito) and _bajo_el_minimo(e.minimo, e.libre, despues):
            activan.append(existencia)
    return ResumenDeCierre(cerradas, estados, proveedores, activan)


def cerrar_con_faltante(actor, lineas):
    """CMP-CRR-FLT paso 7: cierra las líneas pendientes con su motivo y devuelve las líneas cerradas. ``lineas = [(detalle_orden_id, motivo)]``.

    Lee sin bloquear, bloquea en el mismo orden que la recepción (invernadero → insumo → existencia → lotes → orden → líneas) y vuelve a validar con todo bloqueado (7a). Pasa cada línea a «cerrada con
    faltante» (con el motivo y la fecha de hoy), baja el tránsito de cada existencia en lo que faltaba (``stock.restar_transito``), reevalúa las alertas, actualiza el estado de cada orden y audita. **No asienta**
    (D-90 punto 8: la deuda nació al recibir). El correo al proveedor sale en ``on_commit`` (R1)."""
    detalles_previos, ids, _, _ = _planificar_cierre(actor, lineas)
    existencias = {_existencia(d) for d in detalles_previos.values()}
    ordenes = sorted({d.orden_id for d in detalles_previos.values()})
    with transaction.atomic():
        for orden_id in ordenes:
            if orden_id == ordenes[0]:
                _bloquear({e.invernadero_id for e in existencias}, {e.insumo_id for e in existencias}, {e.pk for e in existencias}, orden_id)
            else:
                list(OrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(pk=orden_id))
                list(DetalleOrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(orden_id=orden_id).order_by("id"))
        _actor_sigue_activo(actor)
        detalles, ids, motivos, recibido = _planificar_cierre(actor, lineas)
        hoy = stock.hoy()
        cerradas, por_existencia, estados, _proveedores = _efectos_del_cierre(detalles, ids, motivos, recibido)

        for linea in cerradas:
            linea.detalle.estado_detalle_orden = Estado.CERRADO_CON_FALTANTE
            linea.detalle.motivo_cierre_faltante = linea.motivo
            linea.detalle.fecha_cierre_faltante = hoy
            linea.detalle.save(update_fields=["estado_detalle_orden", "motivo_cierre_faltante", "fecha_cierre_faltante"])
        por_orden = defaultdict(list)
        for linea in cerradas:
            por_orden[linea.detalle.orden].append(linea)
        orden_de_existencia = {_existencia(l.detalle).pk: l.detalle.orden for l in cerradas}
        for iin_id, (existencia, antes, despues) in sorted(por_existencia.items()):
            stock.restar_transito(iin_id, antes - despues)
            alertas_de_stock.reevaluar_alertas_del_insumo(iin_id)
            _auditar_existencia(actor, existencia, existencia.insumo.unidad_medida_insumo, (antes, despues), None, orden_de_existencia[iin_id])
        for orden in sorted(por_orden, key=lambda o: o.pk):
            estado_antes = orden.estado_orden_compra
            propias = por_orden[orden]
            cambios = {}
            if estados[orden.pk] != estado_antes:
                orden.estado_orden_compra = estados[orden.pk]
                orden.save(update_fields=["estado_orden_compra"])
                cambios["estado"] = {"antes": estado_antes, "despues": estados[orden.pk]}
            detalle = {
                "datos": {
                    "lineas_cerradas": [referencia(l.detalle) for l in propias],
                    "motivos_de_cierre": [f"{l.detalle}: {l.motivo}" for l in propias],
                }
            }
            if cambios:
                detalle["cambios"] = cambios
            RegistroAuditoria.objects.registrar(
                usuario=actor, accion=RegistroAuditoria.Accion.CIERRE_CON_FALTANTE, afectados=[orden, *[l.detalle for l in propias]], detalle=detalle
            )
        # CMP-05 (D-91 punto 3): cada proveedor que quedó para pagar con este cierre (todas sus líneas completas o cerradas y algo recibido) avisa al responsable contable, sin quien cierra.
        pares = {(l.detalle.orden, l.detalle.detalle_cotizacion.cotizacion.proveedor) for l in cerradas}
        for orden, proveedor in sorted(pares, key=lambda par: (par[0].pk, par[1].pk)):
            pagos.avisar_si_quedo_para_pagar(orden, proveedor, actor=actor)
        por_proveedor = defaultdict(list)
        for linea in cerradas:
            por_proveedor[linea.detalle.detalle_cotizacion.cotizacion.proveedor_id].append((linea.detalle.pk, linea.falta))
        for proveedor_id, lista in sorted(por_proveedor.items()):
            transaction.on_commit(lambda proveedor_id=proveedor_id, lista=lista: enviar_cierre(proveedor_id, lista))
    return [l.detalle for l in cerradas]


# ---------------------------------------------------------------------------------------------------------------------------------
# Registrantes de `ready()` (regla A4 de D-37)
# ---------------------------------------------------------------------------------------------------------------------------------


def enlace_de_origen(origen):
    """``contabilidad.registrar_enlace_de_origen("recepcion", …)``: el texto de la recepción y la ficha de su orden. ``origen`` es el ``OrigenDocumento``; ``None`` si no es una recepción."""
    recepcion = Recepcion.objects.select_related("orden").filter(pk=origen.pk).first()
    if recepcion is None:
        return None
    return f"{recepcion} · {recepcion.orden}", reverse("compras:orden_ficha", args=[recepcion.orden_id])


def enlaces_de_alertas(usuario, alertas):
    """``maestros.registrar_enlace_de_alerta`` para ``compras_recepcion_con_inconvenientes`` (D-87 punto 5): la alerta del Gerente lleva a la ficha de la orden de la recepción. Una consulta; para otro rol, nada."""
    alertas = list(alertas)
    if not alertas or rol_de(usuario) != Usuario.Rol.GERENTE:
        return {}
    vinculos = {
        v.alerta_id: v for v in AlertaCompras.objects.filter(alerta_id__in=[a.pk for a in alertas]).select_related("reclamo__recepcion__orden")
    }
    resultado = {}
    for alerta in alertas:
        vinculo = vinculos.get(alerta.pk)
        if vinculo is not None:
            recepcion = vinculo.reclamo.recepcion
            resultado[alerta.pk] = Enlace(reverse("compras:orden_ficha", args=[recepcion.orden_id]), f"{recepcion} · {recepcion.orden}")
    return resultado
