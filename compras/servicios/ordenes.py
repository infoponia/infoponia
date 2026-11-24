# Servicios de la orden de compra (CMP-03): CMP-GNR-ODC (generar), CMP-APR-ODC (aprobar y rechazar, paso 4) y CMP-CNS-ODC (consultar, paso 6). Cada caso de
# uso es una función; el registro corre dentro de ``transaction.atomic()`` y audita con el formato de D-36 (docs/patrones/auditoria.md). Casos de uso:
# docs/casos_de_uso/compras/ordenes_de_compra.md; decisiones D-87, D-89 y D-90; modelo: docs/modelo/compras.md.
#
# Bloqueos de CMP-GNR-ODC (docs/patrones/bloqueos.md, «compras», y docs/patrones/stock.md, sección 5, punto 8; siempre ``FOR NO KEY UPDATE``): la cuenta
# de quien actúa → los proveedores de las cotizaciones elegidas en orden de id → el pedido → sus cotizaciones «propuesta» en orden de id. Con todo bloqueado
# y releído se valida de nuevo (extensiones 8a, 11a y 11b) y recién entonces se crea. La notificación al Gerente se crea dentro de la transacción (D-42);
# los correos de descarte salen en ``on_commit``, fuera de ella. ``compras`` no importa de ``comercial`` ni de ``produccion`` (A1 de D-37).

from collections import namedtuple
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import Http404

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, DetalleCotizacion, DetalleOrdenCompra, DetallePedido, OrdenCompra, Pedido, Proveedor
from compras.precios import precio_unitario, precio_unitario_para_mostrar
from compras.servicios import avisos, enlaces
from compras.servicios import cobertura as servicio_de_cobertura
from core import notificaciones
from core.correo import correo_configurado, enviar_correo
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import InsumoInvernadero
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.unidades import Unidad
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _actor_sigue_activo

UN_DECIMAL = Decimal("0.1")
CIEN = Decimal("100")

# Por qué una cotización no se puede elegir (extensiones 4b y 4c): el proveedor está «inactivo» o la fecha de validez ya pasó.
PROVEEDOR_INACTIVO = "proveedor_inactivo"
VALIDEZ_VENCIDA = "validez_vencida"

# Un pedido que el Agrónomo puede resolver (paso 2): cuántos detalles tiene, cuántas cotizaciones recibió y si alcanzan para cubrirlo.
FilaResoluble = namedtuple("FilaResoluble", "pedido detalles cotizaciones alcanzan")
# Paso 4, primera vista: una cotización «propuesta» con su proveedor, sus líneas, su monto y si se puede elegir (``motivo`` si no).
CotizacionComparada = namedtuple("CotizacionComparada", "cotizacion proveedor lineas monto elegible motivo")
# Paso 4, segunda vista: una línea de la tabla de un detalle, con el unitario calculado (D-89) y si su cotización se puede elegir.
# ``mas_bajo`` marca la primera línea elegible de la tabla (el unitario más bajo que se puede elegir).
# ``sobra`` es lo que esa línea ofrece por encima de lo pedido (P2: la cantidad cotizada puede superar la pedida).
LineaComparada = namedtuple("LineaComparada", "cotizacion proveedor cantidad unitario plazo elegible mas_bajo sobra", defaults=(False, Decimal("0")))
# ``problema`` es ``None``, «sin_ofertas» u «ofertas_insuficientes» (extensión 4a), calculado con las cotizaciones elegibles.
DetalleComparado = namedtuple("DetalleComparado", "detalle pedida minima referencia lineas problema")
Comparacion = namedtuple("Comparacion", "pedido cotizaciones detalles puede_generar")
# Paso 9: ``excesos`` es ``[(detalle_pedido, sobra)]`` (extensión 6b); ``coberturas`` es ``{detalle_id: Cobertura}``.
ProveedorDeOrden = namedtuple("ProveedorDeOrden", "proveedor cotizacion lineas monto")
ResumenDeOrden = namedtuple(
    "ResumenDeOrden",
    "pedido proveedores coberturas excesos monto_total monto_estimado diferencia diferencia_porcentaje descartadas observaciones por_detalle",
    defaults=([],),
)


# ---- comunes ----


def _exigir_agronomo(actor):
    """Precondición a de CMP-GNR-ODC: ``actor`` es un Agrónomo con la cuenta activa (SEG-13); si no, ``PermissionDenied``."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise PermissionDenied("Solo un Agrónomo activo puede generar órdenes de compra.")


def _pedido_del_agronomo(actor, pedido_id):
    """El pedido leído sin bloquear. Regla «Agrónomo del pedido»: solo quien lo hizo accede (``PermissionDenied``); uno inexistente es ``Http404`` (D-28)."""
    _exigir_agronomo(actor)
    pedido = Pedido.objects.filter(pk=pedido_id).first()
    if pedido is None:
        raise Http404("No existe ese pedido.")
    if pedido.agronomo_id != actor.pk:
        raise PermissionDenied("Ese pedido no es tuyo: solo lo resuelve el Agrónomo que lo realizó.")
    return pedido


def _exigir_resoluble(pedido, hoy):
    """Extensiones 1a1 y 11a y precondición b: el pedido sigue «en cotización» y su fecha límite ya venció (el último día todavía se cotiza: D-88 punto 2).
    Si no está en cotización, ``ErrorDeCompras`` ``pedido_no_en_cotizacion`` con el estado y, si tiene orden, su id en ``datos``."""
    if not pedido.en_cotizacion:
        orden_id = OrdenCompra.objects.filter(pedido=pedido).values_list("pk", flat=True).first()
        raise ErrorDeCompras(
            "pedido_no_en_cotizacion",
            f"El pedido {pedido} ya no está en cotización: está {pedido.get_estado_pedido_display().lower()}."
            + (f" Su orden de compra es la {OrdenCompra(pk=orden_id)}." if orden_id else ""),
            datos={"estado": pedido.estado_pedido, "orden_id": orden_id},
        )
    if pedido.fecha_limite_cotizaciones >= hoy:
        raise ErrorDeCompras(
            "pedido_no_vencido",
            f"El pedido {pedido} todavía admite cotizaciones hasta el {pedido.fecha_limite_cotizaciones:%d/%m/%Y}: se resuelve desde el día siguiente.",
        )


def motivo_no_elegible(cotizacion, hoy):
    """Reglas «Proveedor inactivo» y «Cotización con la validez vencida»: ``None`` si se puede elegir; si no, «proveedor_inactivo» o «validez_vencida»
    (en ese orden). La validez de hoy todavía sirve. La cotización trae su proveedor cargado (``select_related``)."""
    if not cotizacion.proveedor.activo:
        return PROVEEDOR_INACTIVO
    if cotizacion.fecha_validez_cotizacion < hoy:
        return VALIDEZ_VENCIDA
    return None


def _propuestas(pedido):
    """Las cotizaciones «propuesta» del pedido, con su proveedor y sus líneas, en orden de id (consulta sin bloquear)."""
    return list(
        Cotizacion.objects.filter(pedido=pedido, estado_cotizacion=Cotizacion.Estado.PROPUESTA)
        .select_related("proveedor")
        .prefetch_related("lineas")
        .order_by("id")
    )


# ---- CMP-GNR-ODC paso 2: pedidos por resolver ----


def pedidos_resolubles(actor):
    """Pasos 2 y 3 y regla «Pedido resoluble»: los pedidos de ``actor`` «en cotización», con la fecha límite vencida y al menos una cotización «propuesta», del
    que venció antes al que venció después. Por cada uno, cuántos detalles tiene, cuántas cotizaciones recibió y si **alcanzan** para cubrirlo (con todas las
    «propuesta»). Solo lectura."""
    _exigir_agronomo(actor)
    hoy = stock.hoy()
    candidatos = Pedido.objects.filter(
        agronomo_id=actor.pk, estado_pedido=Pedido.Estado.EN_COTIZACION, fecha_limite_cotizaciones__lt=hoy
    ).order_by("fecha_limite_cotizaciones", "id")
    tolerancia = configuracion.obtener().porc_tolerancia_cobertura_pedido
    filas = []
    for pedido in candidatos:
        propuestas = _propuestas(pedido)
        if not propuestas:
            continue
        alcanzan = servicio_de_cobertura.esta_cubierto(servicio_de_cobertura.cobertura(pedido, propuestas, tolerancia=tolerancia))
        filas.append(FilaResoluble(pedido, DetallePedido.objects.filter(pedido=pedido).count(), len(propuestas), alcanzan))
    return filas


# ---- CMP-GNR-ODC paso 4: las dos vistas ----


def comparacion(actor, pedido_id):
    """Paso 4 y reglas «Presentación», «Proveedor inactivo» y «Cotización con la validez vencida»: las cotizaciones «propuesta» del pedido y, por detalle, la
    tabla de líneas del unitario más barato al más caro (D-89). **No preselecciona nada.** ``puede_generar`` dice si, con las cotizaciones elegibles, todos los
    detalles alcanzan la cobertura mínima (extensión 4a). Pedido ajeno: ``PermissionDenied``; inexistente: ``Http404``; ya resuelto o sin vencer:
    ``ErrorDeCompras``. Solo lectura."""
    pedido = _pedido_del_agronomo(actor, pedido_id)
    hoy = stock.hoy()
    _exigir_resoluble(pedido, hoy)
    propuestas = _propuestas(pedido)
    motivos = {c.pk: motivo_no_elegible(c, hoy) for c in propuestas}
    elegibles = [c for c in propuestas if motivos[c.pk] is None]
    coberturas = servicio_de_cobertura.cobertura(pedido, elegibles)
    cotizaciones = [CotizacionComparada(c, c.proveedor, list(c.lineas.all()), c.monto_cotizacion, motivos[c.pk] is None, motivos[c.pk]) for c in propuestas]
    detalles = []
    for detalle in DetallePedido.objects.filter(pedido=pedido).select_related("insumo_invernadero__insumo", "insumo_invernadero__invernadero").order_by("id"):
        lineas = sorted(
            (
                (precio_unitario(linea), linea.pk, LineaComparada(c, c.proveedor, linea.cantidad_cotizada, precio_unitario(linea), linea.plazo_entrega_dias, motivos[c.pk] is None, False, max(Decimal("0"), linea.cantidad_cotizada - detalle.cantidad_detalle)))
                for c in propuestas
                for linea in c.lineas.all()
                if linea.detalle_pedido_id == detalle.pk
            ),
            key=lambda t: (t[0], t[1]),
        )
        ordenadas = [t[2] for t in lineas]
        primera_elegible = next((i for i, l in enumerate(ordenadas) if l.elegible), None)
        if primera_elegible is not None:
            ordenadas[primera_elegible] = ordenadas[primera_elegible]._replace(mas_bajo=True)
        cob = coberturas[detalle.pk]
        hay_elegibles = any(t[2].elegible for t in lineas)
        problema = None if cob.cubierto else ("ofertas_insuficientes" if hay_elegibles else "sin_ofertas")
        detalles.append(DetalleComparado(detalle, cob.pedida, cob.minima, detalle.precio_unitario_de_pedido, ordenadas, problema))
    return Comparacion(pedido, cotizaciones, detalles, servicio_de_cobertura.esta_cubierto(coberturas))


# ---- selección: las mismas reglas para resumir y para registrar ----


def _ids_de_la_seleccion(cotizacion_ids):
    """La selección como lista de enteros. Vacía: ``sin_cotizaciones_elegidas`` (paso 8); un id repetido: ``cotizacion_repetida`` (cada cotización se elige una
    sola vez, regla «Cotización elegida completa»); uno que no es un número: ``cotizacion_invalida``."""
    ids = []
    for valor in cotizacion_ids or []:
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            raise ErrorDeCompras("cotizacion_invalida", "Una de las cotizaciones elegidas no es válida.", campo="cotizaciones") from None
    if not ids:
        raise ErrorDeCompras("sin_cotizaciones_elegidas", "Elegí al menos una cotización.", campo="cotizaciones")
    if len(set(ids)) != len(ids):
        raise ErrorDeCompras("cotizacion_repetida", "Una cotización se elige una sola vez.", campo="cotizaciones")
    return ids


def _evaluar_seleccion(pedido, ids, propuestas, hoy):
    """Verifica la selección con las ``propuestas`` ya leídas: cada elegida es una «propuesta» de este pedido (``cotizacion_invalida``), se puede elegir (4b, 4c y
    11b: ``cotizacion_no_elegible``, con ``datos["afectadas"] = [(cotizacion_id, motivo)]``) y con todas juntas cada detalle alcanza la cobertura mínima
    (4a y 8a: ``cobertura_insuficiente``, con ``datos["faltantes"] = {detalle_id: falta}``). Devuelve ``(elegidas, coberturas)``; las elegidas en orden de id."""
    por_id = {c.pk: c for c in propuestas}
    if any(i not in por_id for i in ids):
        raise ErrorDeCompras("cotizacion_invalida", "Una de las cotizaciones elegidas no es una cotización propuesta de este pedido.", campo="cotizaciones")
    elegidas = sorted((por_id[i] for i in ids), key=lambda c: c.pk)
    afectadas = [(c.pk, motivo_no_elegible(c, hoy)) for c in elegidas]
    afectadas = [(cotizacion_id, motivo) for cotizacion_id, motivo in afectadas if motivo is not None]
    if afectadas:
        por_cotizacion = {c.pk: c for c in elegidas}
        texto = "; ".join(
            f"la cotización de {por_cotizacion[i].proveedor} ({'proveedor inactivo' if m == PROVEEDOR_INACTIVO else 'validez vencida'})" for i, m in afectadas
        )
        raise ErrorDeCompras("cotizacion_no_elegible", f"No se puede elegir: {texto}.", campo="cotizaciones", datos={"afectadas": afectadas})
    coberturas = servicio_de_cobertura.cobertura(pedido, elegidas)
    faltantes = {detalle_id: c.falta for detalle_id, c in coberturas.items() if not c.cubierto}
    if faltantes:
        raise ErrorDeCompras("cobertura_insuficiente", "Con lo elegido hay detalles que no alcanzan la cantidad mínima.", datos={"faltantes": faltantes})
    return elegidas, coberturas


def _monto_estimado(pedido):
    """El monto estimado del pedido: Σ cantidad × precio de referencia copiado (cada subtotal a 2 decimales)."""
    return sum((d.subtotal for d in DetallePedido.objects.filter(pedido=pedido)), Decimal("0.00"))


def _diferencia(total, estimado):
    """``(diferencia en pesos, diferencia en porcentaje con un decimal)`` entre el total de la orden y el estimado del pedido (regla «Monto de la orden»)."""
    diferencia = total - estimado
    porcentaje = (diferencia / estimado * CIEN).quantize(UN_DECIMAL, ROUND_HALF_UP) if estimado else Decimal("0.0")
    return diferencia, porcentaje


def resumir_orden(actor, pedido_id, cotizacion_ids, observaciones=""):
    """Pasos 7 a 9: lo que se generaría con las cotizaciones elegidas, **sin escribir ni bloquear nada**. Aplica las mismas precondiciones y reglas que
    ``generar_orden``. Por proveedor elegido, sus líneas y su monto; por detalle, lo comprado frente a lo pedido; los excesos (extensión 6b, solo
    advertencia); el total de la orden, el estimado del pedido y la diferencia en pesos y en porcentaje; las cotizaciones que se descartarán; y las
    observaciones recortadas."""
    pedido = _pedido_del_agronomo(actor, pedido_id)
    hoy = stock.hoy()
    _exigir_resoluble(pedido, hoy)
    ids = _ids_de_la_seleccion(cotizacion_ids)
    propuestas = _propuestas(pedido)
    elegidas, coberturas = _evaluar_seleccion(pedido, ids, propuestas, hoy)
    total = sum((c.monto_cotizacion for c in elegidas), Decimal("0.00"))
    estimado = _monto_estimado(pedido)
    diferencia, porcentaje = _diferencia(total, estimado)
    detalles = {d.pk: d for d in DetallePedido.objects.filter(pedido=pedido).select_related("insumo_invernadero__insumo", "insumo_invernadero__invernadero")}
    return ResumenDeOrden(
        pedido=pedido,
        proveedores=[ProveedorDeOrden(c.proveedor, c, list(c.lineas.all()), c.monto_cotizacion) for c in elegidas],
        coberturas=coberturas,
        excesos=[(detalles[i], c.sobra) for i, c in coberturas.items() if c.sobra > 0],
        monto_total=total,
        monto_estimado=estimado,
        diferencia=diferencia,
        diferencia_porcentaje=porcentaje,
        descartadas=[c for c in propuestas if c.pk not in ids],
        observaciones=(observaciones or "").strip(),
        por_detalle=[(detalles[i], c.pedida, c.cotizada) for i, c in coberturas.items()],
    )


# ---- CMP-GNR-ODC paso 11: generar ----


def _texto_de_la_notificacion(orden, pedido, agronomo, proveedores, total, diferencia, porcentaje):
    """El texto de la notificación al Gerente (lista de tecnología 12b): identificador de la orden, pedido, monto total, diferencia con el estimado y
    cantidad de proveedores. Con nombres y no con ids (D-42)."""
    cuantos = f"{proveedores} proveedor" if proveedores == 1 else f"{proveedores} proveedores"
    signo = "+" if diferencia > 0 else ""
    texto = (
        f"{agronomo.get_full_name() or agronomo.email} generó la orden {orden} del pedido {pedido}: {cuantos}, total ${texto_precio(total)}, "
        f"{signo}${texto_precio(diferencia)} ({signo}{porcentaje} %) frente al estimado."
    )
    return texto if len(texto) <= notificaciones.LARGO_DETALLE else texto[: notificaciones.LARGO_DETALLE - 1] + "…"


def enviar_descartes(cotizacion_ids):
    """Postcondición f: avisa por correo a cada proveedor cuya cotización se descartó que no fue seleccionada. El correo indica el pedido, la fecha de la
    cotización y su monto; **no** menciona a los otros proveedores ni sus precios (lista de tecnología 12a). Corre **fuera** de toda transacción
    (``on_commit``); un correo que falla no revierte nada (extensión 12a) y se registra en el log de ``core.correo``. Sin el correo configurado no sale
    nada. La usa también el rechazo de la orden (CMP-APR-ODC, 5a.6)."""
    if not correo_configurado():
        return
    for cotizacion in Cotizacion.objects.filter(pk__in=cotizacion_ids).select_related("proveedor", "pedido").prefetch_related("lineas").order_by("id"):
        proveedor = cotizacion.proveedor
        enviar_correo(
            enlaces.Destinatario(proveedor.pk, proveedor.email_proveedor),
            f"Su cotización del pedido {cotizacion.pedido} no fue seleccionada",
            "compras/correo/descarte.txt",
            {
                "pedido": str(cotizacion.pedido),
                "proveedor": proveedor.nombre_para_mostrar,
                "fecha_cotizacion": cotizacion.fecha_cotizacion,
                "monto": cotizacion.monto_cotizacion,
            },
        )


def generar_orden(actor, pedido_id, cotizacion_ids, observaciones=""):
    """CMP-GNR-ODC paso 11: genera la orden «pendiente de aprobación» con las cotizaciones elegidas y la devuelve.

    - Precondiciones y extensiones: el actor es el Agrónomo activo del pedido; el pedido sigue «en cotización» con la fecha límite vencida (11a); cada elegida
      es una «propuesta» del pedido, su proveedor está activo y su validez no venció (11b); y los detalles quedan todos cubiertos (8a). Con todo bloqueado y
      releído; si algo falla, ``ErrorDeCompras`` y no se registra nada.
    - Postcondiciones a a d: la orden (un detalle por línea, que copia la cantidad **cotizada** y el **total**), las elegidas «seleccionada», el resto de las
      «propuesta» «descartada» y el pedido «cerrado» con la fecha de hoy. Una sola operación.
    - Postcondiciones g y h: un registro ``generacion_orden_compra`` (D-36: una acción, un registro).
    - Postcondición e: notificación al Gerente, dentro de la transacción (D-42). Sin Gerente activo se omite y la orden devuelta trae
      ``sin_gerente_activo = True`` (12b). Postcondición f: correo de descarte en ``on_commit``.
    - No toca el stock, la cantidad en tránsito ni la contabilidad."""
    pedido = _pedido_del_agronomo(actor, pedido_id)
    ids = _ids_de_la_seleccion(cotizacion_ids)
    hoy = stock.hoy()
    # Qué proveedores bloquear: se leen sin bloquear (el proveedor de una cotización no cambia) y se vuelve a leer todo con el bloqueo.
    proveedor_ids = sorted(set(Cotizacion.objects.filter(pk__in=ids, pedido_id=pedido.pk).values_list("proveedor_id", flat=True)))
    with transaction.atomic():
        Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk).first()
        _actor_sigue_activo(actor)
        list(Proveedor.objects.select_for_update(no_key=True).filter(pk__in=proveedor_ids).order_by("id"))
        pedido = Pedido.objects.select_for_update(no_key=True, of=("self",)).select_related("agronomo").get(pk=pedido.pk)
        _exigir_resoluble(pedido, hoy)
        list(Cotizacion.objects.select_for_update(no_key=True, of=("self",)).filter(pedido=pedido, estado_cotizacion="propuesta").order_by("id"))
        propuestas = _propuestas(pedido)  # releídas con los bloqueos tomados (con su proveedor y su estado reales)
        elegidas, _ = _evaluar_seleccion(pedido, ids, propuestas, hoy)
        descartadas = [c for c in propuestas if c.pk not in ids]

        try:
            with transaction.atomic():  # respaldo de «una orden por pedido»: el ``OneToOne`` (regla 13 de 8.16)
                orden = OrdenCompra.objects.create(pedido=pedido, fecha_emision=hoy, observaciones=(observaciones or "").strip())
        except IntegrityError as error:
            raise ErrorDeCompras("pedido_no_en_cotizacion", f"El pedido {pedido} ya tiene su orden de compra.") from error
        detalles = [
            DetalleOrdenCompra.objects.create(
                orden=orden, detalle_cotizacion=linea, cantidad_detalle_orden=linea.cantidad_cotizada, total_linea=linea.total_linea
            )
            for cotizacion in elegidas
            for linea in DetalleCotizacion.objects.filter(cotizacion=cotizacion).order_by("id")
        ]
        Cotizacion.objects.filter(pk__in=[c.pk for c in elegidas]).update(estado_cotizacion=Cotizacion.Estado.SELECCIONADA)
        Cotizacion.objects.filter(pk__in=[c.pk for c in descartadas]).update(estado_cotizacion=Cotizacion.Estado.DESCARTADA)
        pedido.estado_pedido = Pedido.Estado.CERRADO
        pedido.fecha_cierre_pedido = hoy
        pedido.save(update_fields=["estado_pedido", "fecha_cierre_pedido"])

        total = sum((d.total_linea for d in detalles), Decimal("0.00"))
        diferencia, porcentaje = _diferencia(total, _monto_estimado(pedido))
        datos = {
            "orden": referencia(orden),
            "monto_total": texto_precio(total),
            "cotizaciones_seleccionadas": [referencia(c) for c in elegidas],
            "cotizaciones_descartadas": [referencia(c) for c in descartadas],
        }
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.GENERACION_ORDEN_COMPRA,
            afectados=[pedido, orden, *elegidas, *descartadas, *detalles],
            detalle={
                "cambios": {
                    "estado": {"antes": Pedido.Estado.EN_COTIZACION.value, "despues": Pedido.Estado.CERRADO.value},
                    "fecha_cierre_pedido": {"antes": None, "despues": hoy.isoformat()},
                },
                "datos": {clave: valor for clave, valor in datos.items() if valor},
            },
        )
        notificacion = notificaciones.notificar_al_gerente(
            f"Orden {orden} pendiente de aprobación",
            _texto_de_la_notificacion(orden, pedido, pedido.agronomo, len(elegidas), total, diferencia, porcentaje),
        )
        orden.sin_gerente_activo = notificacion is None  # 12b: el mensaje final (paso 13) lo dice
        descartadas_ids = [c.pk for c in descartadas]
        if descartadas_ids:
            transaction.on_commit(lambda: enviar_descartes(descartadas_ids))
    return orden



# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-APR-ODC · Aprobar Orden de Compra (y rechazarla). Fuente: docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-APR-ODC v0.4 con P1, H21 y H22).
#
# Bloqueos (docs/patrones/stock.md, sección 5, punto 8; siempre ``FOR NO KEY UPDATE``). Aprobar: los invernaderos de destino en orden de id → los
# ``InsumoInvernadero`` de destino en orden de id → los proveedores de la orden en orden de id → la orden → sus detalles en orden de id; y recién entonces se
# verifica que quien actúa siga activo y se vuelve a leer todo. Rechazar: las cotizaciones de la orden en orden de id → la orden → sus detalles. **No se bloquea
# la cuenta del Gerente**: con un solo Gerente activo (D-09) bloquearla serializaría todas las resoluciones por ahí y escondería los bloqueos de las filas; se
# comprueba que siga activo después de tomar los demás (docs/patrones/bloqueos.md, «Cómo se bloquea», punto 3). El tránsito lo suma
# ``stock.sumar_transito``, que bloquea y vuelve a leer la existencia. Las notificaciones se crean dentro de la transacción (D-42) y los correos salen en
# ``on_commit``.
# ---------------------------------------------------------------------------------------------------------------------------------

FilaPorAprobar = namedtuple("FilaPorAprobar", "orden pedido agronomo proveedores monto")
DetalleParaResolver = namedtuple(
    "DetalleParaResolver",
    "orden pedido agronomo proveedores por_detalle monto_total monto_estimado diferencia diferencia_porcentaje "
    "lineas_afectadas cotizaciones_afectadas puede_aprobar motivo_propuesto",
)
ResumenDeAprobacion = namedtuple("ResumenDeAprobacion", "orden entregas transito proveedores")
ResumenDeRechazo = namedtuple("ResumenDeRechazo", "orden motivo descartadas proveedores")

INVERNADERO_INACTIVO = "invernadero_inactivo"
INSUMO_INACTIVO = "insumo_inactivo"


def _exigir_gerente(actor):
    """Precondición a de CMP-APR-ODC y requisito especial: ``actor`` es un Gerente con la cuenta activa (SEG-13); si no, ``PermissionDenied``."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede resolver órdenes de compra.")


def _orden_leida(actor, orden_id):
    """La orden leída sin bloquear (con su pedido, su Agrónomo y su Gerente). ``Http404`` si no existe (D-28)."""
    _exigir_gerente(actor)
    orden = OrdenCompra.objects.select_related("pedido__agronomo", "gerente").filter(pk=orden_id).first()
    if orden is None:
        raise Http404("No existe esa orden de compra.")
    return orden


def _exigir_pendiente(orden):
    """Extensiones 1a1, 8a y 5a.5a y regla «Orden resoluble»: la orden sigue «pendiente de aprobación». Si no, ``ErrorDeCompras`` ``orden_no_pendiente`` con la
    decisión tomada, el Gerente que la tomó, la fecha de resolución y, si fue rechazada, el motivo."""
    if orden.pendiente:
        return
    gerente = orden.gerente
    nombre = (gerente.get_full_name() or gerente.email) if gerente is not None else None
    raise ErrorDeCompras(
        "orden_no_pendiente",
        f"La orden {orden} ya no está pendiente: está {orden.get_estado_orden_compra_display().lower()}"
        + (f", resuelta por {nombre} el {orden.fecha_resolucion:%d/%m/%Y}." if nombre and orden.fecha_resolucion else "."),
        datos={"estado": orden.estado_orden_compra, "gerente": nombre, "fecha_resolucion": orden.fecha_resolucion, "motivo_rechazo": orden.motivo_rechazo},
    )


def _detalles_de(orden):
    """Los detalles de la orden en orden de id, con su línea, su cotización, su proveedor y su destino cargados (una consulta)."""
    return list(
        DetalleOrdenCompra.objects.filter(orden=orden)
        .select_related(
            "detalle_cotizacion__cotizacion__proveedor",
            "detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo",
            "detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero__direccion",
        )
        .order_by("id")
    )


def _existencia_de(detalle):
    """El ``InsumoInvernadero`` de destino de un detalle de la orden."""
    return detalle.detalle_cotizacion.detalle_pedido.insumo_invernadero


def _cotizacion_de(detalle):
    """La cotización de un detalle de la orden."""
    return detalle.detalle_cotizacion.cotizacion


def _lineas_con_destino_inactivo(detalles):
    """Extensión 4a y regla «Destino inactivo»: ``[(detalle_orden_id, motivo)]`` de las líneas de un invernadero «inactivo» o de un insumo «inactivo» en su
    invernadero."""
    afectadas = []
    for detalle in detalles:
        existencia = _existencia_de(detalle)
        if not existencia.invernadero.activo:
            afectadas.append((detalle.pk, INVERNADERO_INACTIVO))
        elif not existencia.activo:
            afectadas.append((detalle.pk, INSUMO_INACTIVO))
    return afectadas


def _cotizaciones_no_elegibles(detalles, hoy):
    """Extensión 4b, regla «Cotización vencida» y P1: ``[(cotizacion_id, motivo)]`` de las cotizaciones de la orden con la validez vencida o el proveedor inactivo."""
    por_id = {_cotizacion_de(d).pk: _cotizacion_de(d) for d in detalles}
    return [(i, motivo_no_elegible(c, hoy)) for i, c in sorted(por_id.items()) if motivo_no_elegible(c, hoy) is not None]


def _motivo_propuesto_de(detalles, hoy):
    """P1: «La cotización de {proveedor} venció el {fecha}.» o «{proveedor} está inactivo.» por cada cotización afectada, juntas con un espacio."""
    por_id = {_cotizacion_de(d).pk: _cotizacion_de(d) for d in detalles}
    frases = []
    for cotizacion_id, motivo in _cotizaciones_no_elegibles(detalles, hoy):
        cotizacion = por_id[cotizacion_id]
        if motivo == PROVEEDOR_INACTIVO:
            frases.append(f"{cotizacion.proveedor} está inactivo.")
        else:
            frases.append(f"La cotización de {cotizacion.proveedor} venció el {cotizacion.fecha_validez_cotizacion:%d/%m/%Y}.")
    return " ".join(frases)


def motivo_propuesto(orden):
    """P1 de A0: el motivo que el Sistema propone al rechazar una orden con cotizaciones vencidas o de proveedores inactivos (el Gerente lo puede editar). Vacío si
    ninguna cotización quedó afectada. Solo lectura."""
    return _motivo_propuesto_de(_detalles_de(orden), stock.hoy())


def _exigir_aprobable(detalles, hoy):
    """Extensiones 4a, 4b, 8b y P1: si algún destino está inactivo (``destino_inactivo``, ``datos["lineas"]``) o alguna cotización venció o es de un proveedor
    inactivo (``cotizacion_no_elegible``, ``datos["afectadas"]``), la orden no se puede aprobar (solo rechazar)."""
    lineas = _lineas_con_destino_inactivo(detalles)
    if lineas:
        raise ErrorDeCompras(
            "destino_inactivo",
            "La orden no se puede aprobar: hay líneas de un invernadero o de un insumo inactivo. Solo se puede rechazar.",
            datos={"lineas": lineas},
        )
    afectadas = _cotizaciones_no_elegibles(detalles, hoy)
    if afectadas:
        raise ErrorDeCompras(
            "cotizacion_no_elegible",
            "La orden no se puede aprobar: " + _motivo_propuesto_de(detalles, hoy) + " Solo se puede rechazar.",
            datos={"afectadas": afectadas},
        )


def _proveedores_de_la_orden(detalles):
    """``[ProveedorDeOrden]`` en orden de cotización: por proveedor, su cotización, sus líneas de la orden y el monto de ellas."""
    grupos = {}
    for detalle in detalles:
        grupos.setdefault(_cotizacion_de(detalle).pk, []).append(detalle)
    resultado = []
    for lineas in (grupos[i] for i in sorted(grupos)):
        cotizacion = _cotizacion_de(lineas[0])
        resultado.append(ProveedorDeOrden(cotizacion.proveedor, cotizacion, lineas, sum((l.total_linea for l in lineas), Decimal("0.00"))))
    return resultado


def _transito_a_sumar(detalles):
    """``{iin_id: (existencia, suma)}``: lo que sube el tránsito de cada ``InsumoInvernadero`` (la suma de todos sus detalles, de todos los proveedores)."""
    sumas = {}
    for detalle in detalles:
        existencia = _existencia_de(detalle)
        actual = sumas.get(existencia.pk, (existencia, Decimal("0")))
        sumas[existencia.pk] = (existencia, actual[1] + detalle.cantidad_detalle_orden)
    return sumas


def ordenes_por_aprobar(actor):
    """Pasos 2 y 3 y regla «Orden resoluble»: las órdenes «pendiente de aprobación», de la más antigua a la más reciente, con el pedido, el Agrónomo que lo
    realizó, la cantidad de proveedores y el monto total. Solo lectura."""
    _exigir_gerente(actor)
    consulta = (
        OrdenCompra.objects.filter(estado_orden_compra=OrdenCompra.Estado.PENDIENTE_APROBACION)
        .select_related("pedido__agronomo")
        .con_monto()
        .annotate(cantidad_de_proveedores=Count("detalles__detalle_cotizacion__cotizacion__proveedor", distinct=True))
        .order_by("fecha_emision", "id")
    )
    return [FilaPorAprobar(o, o.pedido, o.pedido.agronomo, o.cantidad_de_proveedores, o.monto_orden) for o in consulta]


def detalle_para_resolver(actor, orden_id):
    """Paso 4: lo que el Gerente necesita para decidir: el pedido, su Agrónomo y las observaciones; por proveedor, sus líneas y su monto; por detalle del pedido, lo
    comprado frente a lo pedido; y el total frente al estimado. Marca lo que impide aprobar (4a: ``lineas_afectadas``; 4b y P1: ``cotizaciones_afectadas``) y trae
    el motivo propuesto para rechazar. Una orden que ya no está pendiente es ``orden_no_pendiente`` (1a1). Solo lectura."""
    orden = _orden_leida(actor, orden_id)
    _exigir_pendiente(orden)
    hoy = stock.hoy()
    detalles = _detalles_de(orden)
    comprado = {}
    for detalle in detalles:
        comprado[detalle.detalle_cotizacion.detalle_pedido_id] = comprado.get(detalle.detalle_cotizacion.detalle_pedido_id, Decimal("0")) + detalle.cantidad_detalle_orden
    por_detalle = [
        (d, d.cantidad_detalle, comprado.get(d.pk, Decimal("0")))
        for d in DetallePedido.objects.filter(pedido=orden.pedido).select_related("insumo_invernadero__insumo", "insumo_invernadero__invernadero").order_by("id")
    ]
    total = sum((d.total_linea for d in detalles), Decimal("0.00"))
    estimado = _monto_estimado(orden.pedido)
    diferencia, porcentaje = _diferencia(total, estimado)
    lineas_afectadas = _lineas_con_destino_inactivo(detalles)
    cotizaciones_afectadas = _cotizaciones_no_elegibles(detalles, hoy)
    return DetalleParaResolver(
        orden=orden,
        pedido=orden.pedido,
        agronomo=orden.pedido.agronomo,
        proveedores=_proveedores_de_la_orden(detalles),
        por_detalle=por_detalle,
        monto_total=total,
        monto_estimado=estimado,
        diferencia=diferencia,
        diferencia_porcentaje=porcentaje,
        lineas_afectadas=lineas_afectadas,
        cotizaciones_afectadas=cotizaciones_afectadas,
        puede_aprobar=not lineas_afectadas and not cotizaciones_afectadas,
        motivo_propuesto=_motivo_propuesto_de(detalles, hoy),
    )


def resumir_aprobacion(actor, orden_id):
    """Paso 6: la fecha de entrega esperada de cada línea (hoy + su plazo), cómo subirá el tránsito de cada ``InsumoInvernadero`` (antes, lo que suma y después) y lo
    que recibirá cada proveedor. Aplica las mismas precondiciones que ``aprobar_orden`` y no escribe nada."""
    orden = _orden_leida(actor, orden_id)
    _exigir_pendiente(orden)
    hoy = stock.hoy()
    detalles = _detalles_de(orden)
    _exigir_aprobable(detalles, hoy)
    transito = [(existencia, existencia.cant_transito_insumo, suma, existencia.cant_transito_insumo + suma) for existencia, suma in _transito_a_sumar(detalles).values()]
    return ResumenDeAprobacion(
        orden,
        [(d, hoy + timedelta(days=d.detalle_cotizacion.plazo_entrega_dias)) for d in detalles],
        sorted(transito, key=lambda fila: fila[0].pk),
        _proveedores_de_la_orden(detalles),
    )


def _texto_de_entregas(entregas):
    """Las fechas de entrega esperadas distintas, de la más cercana a la más lejana, como «dd/mm/aaaa»."""
    return ", ".join(f"{fecha:%d/%m/%Y}" for fecha in sorted(set(entregas)))


def _avisar_al_agronomo(actor, orden, destinos, titulo, texto):
    """H21: la notificación a cada Agrónomo activo de los invernaderos de destino y, por cada destino sin Agrónomo activo, al Gerente; nunca a ``actor``. Dentro
    de la transacción (D-42). El texto se recorta al largo permitido."""
    if len(texto) > notificaciones.LARGO_DETALLE:
        texto = texto[: notificaciones.LARGO_DETALLE - 1] + "…"
    notificaciones.notificar_a_varios(avisos.destinatarios_por_destino(destinos, excluir=actor), titulo, texto)


def enviar_aprobacion(orden_id):
    """Postcondición h y lista de tecnología 9a: a cada proveedor de la orden, un correo con **solo sus líneas** (insumo, cantidad, precio y subtotal), el invernadero
    de destino con su dirección, la fecha de entrega esperada de cada línea y el total de sus líneas. No menciona a los otros proveedores ni sus líneas. Corre
    **fuera** de toda transacción (``on_commit``); un correo que falla no revierte nada (extensión 9a). Sin el correo configurado no sale nada."""
    if not correo_configurado():
        return
    orden = OrdenCompra.objects.get(pk=orden_id)
    for proveedor_ in _proveedores_de_la_orden(_detalles_de(orden)):
        lineas = []
        for detalle in proveedor_.lineas:
            existencia = _existencia_de(detalle)
            insumo = existencia.insumo
            lineas.append(
                {
                    "insumo": insumo.nombre_insumo,
                    "cantidad": detalle.cantidad_detalle_orden,
                    "unidad": Unidad(insumo.unidad_medida_insumo).label,
                    "unidad_medida": insumo.unidad_medida_insumo,
                    "unitario": precio_unitario_para_mostrar(detalle),
                    "total": detalle.total_linea,
                    "invernadero": existencia.invernadero.nombre_invernadero,
                    "direccion": str(existencia.invernadero.direccion),
                    "entrega": detalle.fecha_entrega_esperada,
                }
            )
        enviar_correo(
            enlaces.Destinatario(proveedor_.proveedor.pk, proveedor_.proveedor.email_proveedor),
            f"Orden de compra {orden}",
            "compras/correo/aprobacion.txt",
            {"orden": str(orden), "proveedor": proveedor_.proveedor.nombre_para_mostrar, "lineas": lineas, "total": proveedor_.monto},
        )


def aprobar_orden(actor, orden_id):
    """CMP-APR-ODC paso 8: aprueba la orden pendiente y la devuelve.

    - Precondiciones y extensiones: ``actor`` es un Gerente activo; la orden sigue «pendiente de aprobación» (8a); ningún destino está inactivo (4a y 8b) y
      ninguna cotización venció ni es de un proveedor inactivo (4b, 8b y P1). Con todo bloqueado y releído; si algo falla, ``ErrorDeCompras`` y no cambia nada.
    - Postcondiciones a, e y f: «aprobada» con la fecha de hoy y el Gerente; la fecha de entrega esperada de cada línea (hoy + su plazo); el tránsito de cada
      ``InsumoInvernadero`` sube la **suma** de sus líneas (``stock.sumar_transito``). El pedido, las cotizaciones, el stock actual y las alertas no cambian.
    - Postcondición m: ``aprobacion_orden_compra`` y una ``modificacion_insumo_invernadero`` por cada existencia (con el tránsito antes y después).
    - Postcondiciones c y h: notificación al Agrónomo según H21 (dentro de la transacción) y un correo a cada proveedor con sus líneas (``on_commit``).
    - No registra pagos ni asientos (D-91)."""
    orden = _orden_leida(actor, orden_id)
    previos = _detalles_de(orden)
    invernadero_ids = sorted({_existencia_de(d).invernadero_id for d in previos})
    existencia_ids = sorted({_existencia_de(d).pk for d in previos})
    proveedor_ids = sorted({_cotizacion_de(d).proveedor_id for d in previos})
    with transaction.atomic():
        list(Invernadero.objects.select_for_update(no_key=True).filter(pk__in=invernadero_ids).order_by("id"))
        list(InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=existencia_ids).order_by("id"))
        list(Proveedor.objects.select_for_update(no_key=True).filter(pk__in=proveedor_ids).order_by("id"))
        orden = OrdenCompra.objects.select_for_update(no_key=True, of=("self",)).select_related("pedido__agronomo", "gerente").get(pk=orden.pk)
        list(DetalleOrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(orden=orden).order_by("id"))
        _actor_sigue_activo(actor)
        _exigir_pendiente(orden)
        hoy = stock.hoy()
        detalles = _detalles_de(orden)
        _exigir_aprobable(detalles, hoy)

        orden.estado_orden_compra = OrdenCompra.Estado.APROBADA
        orden.fecha_resolucion = hoy
        orden.gerente_id = actor.pk
        orden.save(update_fields=["estado_orden_compra", "fecha_resolucion", "gerente"])
        for detalle in detalles:
            detalle.fecha_entrega_esperada = hoy + timedelta(days=detalle.detalle_cotizacion.plazo_entrega_dias)
            detalle.save(update_fields=["fecha_entrega_esperada"])
        total = sum((d.total_linea for d in detalles), Decimal("0.00"))
        # El tránsito sube primero y la auditoría de la orden va al final: el registro de la orden es lo último que se escribe antes de confirmar.
        for existencia_id, (existencia, suma) in sorted(_transito_a_sumar(detalles).items()):
            antes = InsumoInvernadero.objects.get(pk=existencia_id).cant_transito_insumo
            despues = stock.sumar_transito(existencia_id, suma).cant_transito_insumo
            unidad = existencia.insumo.unidad_medida_insumo
            RegistroAuditoria.objects.registrar(
                usuario=actor,
                accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO,
                afectados=[existencia, existencia.invernadero],
                detalle={"cambios": {"transito": {"antes": texto_cantidad(antes, unidad), "despues": texto_cantidad(despues, unidad)}}, "datos": {"orden": referencia(orden)}},
            )
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.APROBACION_ORDEN_COMPRA,
            afectados=[orden, *detalles],
            detalle={
                "cambios": {
                    "estado": {"antes": OrdenCompra.Estado.PENDIENTE_APROBACION.value, "despues": OrdenCompra.Estado.APROBADA.value},
                    "fecha_resolucion": {"antes": None, "despues": hoy.isoformat()},
                    "gerente": {"antes": None, "despues": referencia(actor)},
                },
                "datos": {"monto_total": texto_precio(total)},
            },
        )
        destinos = {_existencia_de(d).invernadero_id for d in detalles}
        _avisar_al_agronomo(
            actor,
            orden,
            destinos,
            f"Orden {orden} aprobada",
            f"El Gerente aprobó la orden {orden} del pedido {orden.pedido}: total ${texto_precio(total)}. "
            f"Entregas esperadas: {_texto_de_entregas(d.fecha_entrega_esperada for d in detalles)}.",
        )
        transaction.on_commit(lambda: enviar_aprobacion(orden.pk))
    return orden


def _motivo_del_rechazo(motivo):
    """Extensión 5b y regla «Rechazo»: el motivo es obligatorio (texto libre, recortado); si no, ``ValidationError`` del campo ``motivo`` (``motivo_obligatorio``)."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError({"motivo": [ValidationError("Contá por qué se rechaza la orden.", code="motivo_obligatorio")]})
    return motivo


def resumir_rechazo(actor, orden_id, motivo):
    """Extensión 5a.3: el motivo, las cotizaciones que pasarán a «descartada» y los proveedores a los que se les avisará. Mismas precondiciones que
    ``rechazar_orden``; no escribe nada."""
    orden = _orden_leida(actor, orden_id)
    motivo = _motivo_del_rechazo(motivo)
    _exigir_pendiente(orden)
    proveedores = _proveedores_de_la_orden(_detalles_de(orden))
    return ResumenDeRechazo(orden, motivo, [p.cotizacion for p in proveedores], [p.proveedor for p in proveedores])


def rechazar_orden(actor, orden_id, motivo):
    """CMP-APR-ODC extensión 5a.5: rechaza la orden pendiente con un motivo obligatorio y la devuelve.

    - Quedan «rechazada» (fecha de hoy, Gerente y motivo), las cotizaciones seleccionadas de la orden pasan a «descartada» y el pedido sigue «cerrado». No cambia
      el tránsito ni las entregas esperadas. Siempre se puede rechazar, aunque la aprobación esté bloqueada (4a y 4b).
    - Postcondición m: ``rechazo_orden_compra``. Postcondiciones c y k: notificación al Agrónomo con el motivo (H21, dentro de la transacción) y, en
      ``on_commit``, un correo a cada proveedor de la orden que le informa que su cotización no fue seleccionada (sin el motivo)."""
    orden = _orden_leida(actor, orden_id)
    motivo = _motivo_del_rechazo(motivo)
    cotizacion_ids = sorted({_cotizacion_de(d).pk for d in _detalles_de(orden)})
    with transaction.atomic():
        list(Cotizacion.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=cotizacion_ids).order_by("id"))
        orden = OrdenCompra.objects.select_for_update(no_key=True, of=("self",)).select_related("pedido__agronomo", "gerente").get(pk=orden.pk)
        list(DetalleOrdenCompra.objects.select_for_update(no_key=True, of=("self",)).filter(orden=orden).order_by("id"))
        _actor_sigue_activo(actor)
        _exigir_pendiente(orden)
        hoy = stock.hoy()
        detalles = _detalles_de(orden)
        cotizaciones = sorted({_cotizacion_de(d).pk: _cotizacion_de(d) for d in detalles}.values(), key=lambda c: c.pk)
        total = sum((d.total_linea for d in detalles), Decimal("0.00"))

        orden.estado_orden_compra = OrdenCompra.Estado.RECHAZADA
        orden.fecha_resolucion = hoy
        orden.gerente_id = actor.pk
        orden.motivo_rechazo = motivo
        orden.save(update_fields=["estado_orden_compra", "fecha_resolucion", "gerente", "motivo_rechazo"])
        Cotizacion.objects.filter(pk__in=[c.pk for c in cotizaciones]).update(estado_cotizacion=Cotizacion.Estado.DESCARTADA)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.RECHAZO_ORDEN_COMPRA,
            afectados=[orden, *cotizaciones],
            detalle={
                "cambios": {
                    "estado": {"antes": OrdenCompra.Estado.PENDIENTE_APROBACION.value, "despues": OrdenCompra.Estado.RECHAZADA.value},
                    "fecha_resolucion": {"antes": None, "despues": hoy.isoformat()},
                    "gerente": {"antes": None, "despues": referencia(actor)},
                    "motivo_rechazo": {"antes": None, "despues": motivo},
                },
                "datos": {"cotizaciones_descartadas": [referencia(c) for c in cotizaciones]},
            },
        )
        destinos = {_existencia_de(d).invernadero_id for d in detalles}
        _avisar_al_agronomo(
            actor,
            orden,
            destinos,
            f"Orden {orden} rechazada",
            f"El Gerente rechazó la orden {orden} del pedido {orden.pedido} (total ${texto_precio(total)}). Motivo: {motivo}",
        )
        transaction.on_commit(lambda: enviar_descartes([c.pk for c in cotizaciones]))
    return orden


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-CNS-ODC · Consultar Orden de Compra (CMP-03 la crea; CMP-04, CMP-05 y CMP-06 suman las secciones de recepciones, pagos y reclamos y los atajos «por recibir»,
# «con pago pendiente» y «con reclamo sin emitir»). Fuente: docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-CNS-ODC v0.1, reglas 1 a 10). Solo lectura: no
# bloquea, no escribe y no audita (regla 10, SEG-14). El alcance está en ``OrdenCompra.objects.en_alcance_de``; el Contador (solo lectura) entra con USR-11.
# ---------------------------------------------------------------------------------------------------------------------------------

# Regla 3: una fila del listado. ``proveedores`` son los ``Proveedor`` de la orden; ``lineas_atrasadas`` cuenta las líneas pendientes con la entrega esperada vencida.
FilaDeOrden = namedtuple("FilaDeOrden", "orden pedido agronomo proveedores monto lineas_atrasadas")
# Regla 5: una línea de la ficha. Hasta CMP-04, ``recibida`` es 0 y ``pendiente`` toda la cantidad. ``unitario`` es el derivado con dos decimales (D-89 punto 7).
LineaDeOrden = namedtuple("LineaDeOrden", "detalle insumo cantidad recibida pendiente unitario total entrega atraso_dias estado motivo_cierre")
GrupoDeLineas = namedtuple("GrupoDeLineas", "proveedor invernadero lineas")
FichaDeOrden = namedtuple(
    "FichaDeOrden",
    "orden pedido agronomo gerente proveedores grupos monto_total monto_estimado diferencia diferencia_porcentaje lineas_atrasadas acciones",
)

ACCION_RESOLVER = "resolver"
ATAJO_POR_APROBAR = "por_aprobar"


def _exigir_consulta(actor):
    """Precondición a de CMP-CNS-ODC: ``actor`` es un Agrónomo o un Gerente con la cuenta activa (SEG-13); si no, ``PermissionDenied``. El Contador se suma con USR-11."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO, Usuario.Rol.CONTADOR):
        raise PermissionDenied("Solo un Agrónomo, un Gerente o el Contador activos pueden consultar órdenes de compra.")


def _entero_o_none(valor):
    """``valor`` como entero, o ``None`` si no lo es (un filtro mal formado se ignora)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _fecha_o_none(valor):
    """``valor`` como fecha (un ``date`` o un texto ``AAAA-MM-DD``), o ``None`` si no lo es."""
    if hasattr(valor, "isoformat") and not isinstance(valor, str):
        return valor
    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError:
        return None


def _atraso_de(detalle, hoy):
    """Regla 5: los días de atraso de una línea **pendiente** con la entrega esperada vencida; 0 si no corresponde."""
    entrega = detalle.fecha_entrega_esperada
    if entrega is not None and entrega < hoy and detalle.estado_detalle_orden == DetalleOrdenCompra.Estado.PENDIENTE:
        return (hoy - entrega).days
    return 0


def consultar_ordenes(actor, filtros=None):
    """CMP-CNS-ODC reglas 1 a 3: las órdenes que ``actor`` ve (el Agrónomo, las que tienen algún destino a su cargo; el Gerente, todas), de la más reciente a la más
    antigua, con sus filtros. ``filtros`` (todos opcionales; uno mal formado se ignora): ``estado``, ``proveedor_id``, ``invernadero_id`` (alguna línea va ahí), ``desde`` y
    ``hasta`` (inclusive, sobre la fecha de emisión; fechas o ``AAAA-MM-DD``), ``agronomo_id`` (solo lo usa el Gerente: el Agrónomo ya ve lo suyo) y ``atajo``
    («por_aprobar»; los demás atajos los suman CMP-04 a CMP-06). Devuelve ``list[FilaDeOrden]`` con una consulta por tabla (no una por fila). No audita."""
    _exigir_consulta(actor)
    filtros = filtros or {}
    consulta = OrdenCompra.objects.en_alcance_de(actor).select_related("pedido__agronomo").con_monto()
    estado = filtros.get("estado")
    if filtros.get("atajo") == ATAJO_POR_APROBAR:
        estado = OrdenCompra.Estado.PENDIENTE_APROBACION
    if estado in OrdenCompra.Estado.values:
        consulta = consulta.filter(estado_orden_compra=estado)
    proveedor_id = _entero_o_none(filtros.get("proveedor_id"))
    if proveedor_id is not None:
        consulta = consulta.filter(
            pk__in=DetalleOrdenCompra.objects.filter(detalle_cotizacion__cotizacion__proveedor_id=proveedor_id).values("orden_id")
        )
    invernadero_id = _entero_o_none(filtros.get("invernadero_id"))
    if invernadero_id is not None:
        consulta = consulta.filter(
            pk__in=DetalleOrdenCompra.objects.filter(
                detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero_id=invernadero_id
            ).values("orden_id")
        )
    desde, hasta = _fecha_o_none(filtros.get("desde")), _fecha_o_none(filtros.get("hasta"))
    if desde is not None:
        consulta = consulta.filter(fecha_emision__gte=desde)
    if hasta is not None:
        consulta = consulta.filter(fecha_emision__lte=hasta)
    agronomo_id = _entero_o_none(filtros.get("agronomo_id"))
    if rol_de(actor) == Usuario.Rol.GERENTE and agronomo_id is not None:
        consulta = consulta.filter(pedido__agronomo_id=agronomo_id)

    lista = list(consulta.order_by("-fecha_emision", "-id"))
    ids = [o.pk for o in lista]
    hoy = stock.hoy()
    proveedor_de = {}
    atrasadas = {}
    for orden_id, proveedor_id_, estado_, entrega in DetalleOrdenCompra.objects.filter(orden_id__in=ids).values_list(
        "orden_id", "detalle_cotizacion__cotizacion__proveedor_id", "estado_detalle_orden", "fecha_entrega_esperada"
    ):
        proveedor_de.setdefault(orden_id, set()).add(proveedor_id_)
        if estado_ == DetalleOrdenCompra.Estado.PENDIENTE and entrega is not None and entrega < hoy:
            atrasadas[orden_id] = atrasadas.get(orden_id, 0) + 1
    proveedores = {p.pk: p for p in Proveedor.objects.filter(pk__in={i for s in proveedor_de.values() for i in s})}
    return [
        FilaDeOrden(o, o.pedido, o.pedido.agronomo, sorted((proveedores[i] for i in proveedor_de.get(o.pk, ())), key=lambda p: p.pk), o.monto_orden, atrasadas.get(o.pk, 0))
        for o in lista
    ]


def ficha_de_orden(actor, orden_id):
    """CMP-CNS-ODC reglas 4, 5 y 8: la ficha de la orden. El Agrónomo abre las que tienen algún destino a su cargo y el Gerente todas; una fuera del alcance es
    ``PermissionDenied`` y una que no existe, ``Http404`` (D-28).

    Trae el pedido de origen y su Agrónomo, el monto frente al estimado, el estado y, si se resolvió, el Gerente, la fecha, las observaciones y el motivo del rechazo; las
    líneas **agrupadas por proveedor e invernadero de destino** (cantidad, recibida, pendiente, precio, entrega esperada con sus días de atraso, estado y motivo del cierre) y
    las ``acciones`` que ``actor`` puede hacer desde ahí (CMP-03: ``resolver``, solo el Gerente y solo si está pendiente de aprobación; ningún botón lleva a un 403, D-30).
    Las recepciones, los pagos y los reclamos los suman CMP-04 a CMP-06. No audita."""
    _exigir_consulta(actor)
    orden = OrdenCompra.objects.select_related("pedido__agronomo", "gerente").filter(pk=orden_id).first()
    if orden is None:
        raise Http404("No existe esa orden de compra.")
    if not OrdenCompra.objects.en_alcance_de(actor).filter(pk=orden.pk).exists():
        raise PermissionDenied("Esa orden no tiene destinos a tu cargo: solo la ven el Agrónomo de un destino y el Gerente.")
    hoy = stock.hoy()
    detalles = _detalles_de(orden)
    grupos = {}
    for detalle in detalles:
        existencia = _existencia_de(detalle)
        recibida = Decimal("0")  # lo recibido es de CMP-04
        grupo = grupos.setdefault((_cotizacion_de(detalle).proveedor_id, existencia.invernadero_id), GrupoDeLineas(_cotizacion_de(detalle).proveedor, existencia.invernadero, []))
        grupo.lineas.append(
            LineaDeOrden(
                detalle,
                existencia.insumo,
                detalle.cantidad_detalle_orden,
                recibida,
                detalle.cantidad_detalle_orden - recibida,
                precio_unitario_para_mostrar(detalle),
                detalle.total_linea,
                detalle.fecha_entrega_esperada,
                _atraso_de(detalle, hoy),
                detalle.estado_detalle_orden,
                detalle.motivo_cierre_faltante,
            )
        )
    total = sum((d.total_linea for d in detalles), Decimal("0.00"))
    estimado = _monto_estimado(orden.pedido)
    diferencia, porcentaje = _diferencia(total, estimado)
    puede_resolver = rol_de(actor) == Usuario.Rol.GERENTE and orden.pendiente
    return FichaDeOrden(
        orden=orden,
        pedido=orden.pedido,
        agronomo=orden.pedido.agronomo,
        gerente=orden.gerente,
        proveedores=_proveedores_de_la_orden(detalles),
        grupos=[grupos[clave] for clave in sorted(grupos)],
        monto_total=total,
        monto_estimado=estimado,
        diferencia=diferencia,
        diferencia_porcentaje=porcentaje,
        lineas_atrasadas=sum(1 for g in grupos.values() for l in g.lineas if l.atraso_dias > 0),
        acciones=frozenset({ACCION_RESOLVER}) if puede_resolver else frozenset(),
    )


def pendientes_de_aprobacion():
    """``core.registrar_contador_de_pendientes`` (D-14 y D-42): lo que en compras espera una resolución del Gerente, como ``[(descripción, cantidad)]``; sin nada, lista vacía.
    Lo suman la ventana de baja del Gerente y la notificación a quien queda a cargo. Una consulta."""
    cantidad = OrdenCompra.objects.filter(estado_orden_compra=OrdenCompra.Estado.PENDIENTE_APROBACION).count()
    return [("Órdenes de compra por aprobar", cantidad)] if cantidad else []


# ---- CMP-GNR-ODC pasos 5 y 6: la cobertura de lo elegido hasta ahora (para el panel de la pantalla) ----

CoberturaElegida = namedtuple("CoberturaElegida", "detalle pedida minima elegida cubierto sobra falta")
EleccionActual = namedtuple("EleccionActual", "coberturas elegidas monto proveedores cubierto")


def cobertura_de_la_eleccion(comparacion_, cotizacion_ids):
    """Pasos 5 y 6 y extensiones 6a y 6b: con la ``Comparacion`` ya armada (sin consultar la base) y las cotizaciones elegidas hasta ahora, por detalle cuánto se compraría frente a lo
    pedido y al mínimo, si queda cubierto, cuánto sobra o falta; y el monto y la cantidad de proveedores elegidos. Ignora los ids que no son de una cotización elegible de la comparación
    (la pantalla no los ofrece). ``cubierto`` es verdadero solo si hay alguna elegida y todos los detalles quedan cubiertos. Función pura: no escribe ni lee."""
    elegibles = {c.cotizacion.pk: c for c in comparacion_.cotizaciones if c.elegible}
    ids = []
    for valor in cotizacion_ids or []:
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    elegidas = [elegibles[i] for i in dict.fromkeys(ids) if i in elegibles]
    ids_elegidos = {c.cotizacion.pk for c in elegidas}
    coberturas = []
    for detalle in comparacion_.detalles:
        suma = sum((l.cantidad for l in detalle.lineas if l.cotizacion.pk in ids_elegidos), Decimal("0"))
        coberturas.append(
            CoberturaElegida(
                detalle.detalle,
                detalle.pedida,
                detalle.minima,
                suma,
                suma >= detalle.minima,
                max(Decimal("0"), suma - detalle.pedida),
                max(Decimal("0"), detalle.minima - suma),
            )
        )
    return EleccionActual(
        coberturas,
        elegidas,
        sum((c.monto for c in elegidas), Decimal("0.00")),
        len({c.proveedor.pk for c in elegidas}),
        bool(elegidas) and all(c.cubierto for c in coberturas),
    )
