# Servicios del Pedido de cotización (CMP-02a): CMP-RLZ-PED (realizar) y, en el paso 5, CMP-CNS-PED (consultar). Cada caso de uso es una función; el
# registro corre dentro de ``transaction.atomic()`` y audita con el formato de D-36 (docs/patrones/auditoria.md). Casos de uso:
# docs/casos_de_uso/compras/pedidos.md; decisiones D-87, D-88 y D-89; modelo: docs/modelo/compras.md.
#
# Bloqueos (docs/patrones/bloqueos.md, «compras», y docs/patrones/stock.md, sección 5; siempre ``FOR NO KEY UPDATE``): la cuenta de quien actúa →
# los invernaderos de destino en orden de id (``bloquear_invernadero_activo``: el pedido no impide la baja del invernadero, pero el contrato de D-40
# lo pide a todo lo que crea algo sobre él) → los ``InsumoInvernadero`` en orden de id → los proveedores invitados en orden de id. Con todo
# bloqueado y releído se valida de nuevo (extensión 11a) y recién entonces se crea. Los correos salen en ``on_commit`` (fuera de la transacción).
# ``compras`` no importa de ``comercial`` ni de ``produccion`` (A1 de D-37).

from collections import namedtuple
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.models.functions import Lower
from django.http import Http404

from compras.errores import ErrorDeCompras
from compras.models import MOTIVOS_DE_CANCELACION_AUTOMATICA, Cotizacion, DetallePedido, EnlaceProveedor, InvitacionPedido, Pedido, Proveedor
from compras.servicios import avisos, enlaces
from compras.servicios import cotizaciones as servicio_de_cotizaciones
from core import notificaciones
from core.models import Agronomo, RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import Insumo, InsumoInvernadero
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.unidades import validar_cantidad
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _actor_sigue_activo, bloquear_invernadero_activo

DOS_DECIMALES = Decimal("0.01")
LIMITE_DE_CANTIDAD = Decimal(10) ** 11  # DecimalField(14, 3)

# Lo que otro pedido «en cotización» ya pide del mismo insumo en el mismo invernadero (extensión 4c; la parte de «orden pendiente de aprobación»
# la completa CMP-03, que es quien crea la orden).
YaPedido = namedtuple("YaPedido", "pedido_id cantidad fecha_limite")
# Un insumo del Agrónomo para armar el pedido: la existencia, sus cantidades (``stock.Existencia``), la sugerida y si ya está en otro pedido.
FilaPedible = namedtuple("FilaPedible", "iin existencia sugerida ya_pedido")
LineaResumen = namedtuple("LineaResumen", "iin cantidad precio subtotal ya_pedido")
# ``grupos`` es ``[(invernadero, [LineaResumen])]``, uno por invernadero de destino (paso 9).
ResumenPedido = namedtuple("ResumenPedido", "grupos monto fecha_limite proveedores")


# ---- comunes ----


def _exigir_agronomo(actor):
    """Precondición a de CMP-RLZ-PED: ``actor`` es un Agrónomo con la cuenta activa (SEG-13); si no, ``PermissionDenied``."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise PermissionDenied("Solo un Agrónomo activo puede realizar pedidos.")


def _error(campo, mensaje, codigo):
    """Un ``ValidationError`` de un solo campo."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _id_o_none(valor):
    """El valor como entero, o ``None`` si no lo es."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _insumos_del_agronomo(actor):
    """Las existencias pedibles de ``actor``: activas, de un insumo activo, en un invernadero activo a su cargo (regla «Insumo pedible»)."""
    return InsumoInvernadero.objects.filter(
        invernadero__agronomo_id=actor.pk,
        invernadero__estado_invernadero="activo",
        estado_insumo_invernadero="activo",
        insumo__estado_insumo=Insumo.Estado.ACTIVO,
    ).select_related("insumo", "insumo__tipo_insumo", "invernadero")


def ya_pedido(iin_ids):
    """``{iin_id: YaPedido}`` de los insumos que ya figuran en otro pedido «en cotización» (extensión 4c). Una consulta; el pedido más reciente."""
    resultado = {}
    detalles = (
        DetallePedido.objects.filter(insumo_invernadero_id__in=list(iin_ids), pedido__estado_pedido=Pedido.Estado.EN_COTIZACION)
        .select_related("pedido")
        .order_by("-pedido_id")
    )
    for detalle in detalles:
        resultado.setdefault(
            detalle.insumo_invernadero_id,
            YaPedido(detalle.pedido_id, detalle.cantidad_detalle, detalle.pedido.fecha_limite_cotizaciones),
        )
    return resultado


def _filas(iins):
    """Las ``FilaPedible`` de una lista de existencias: el stock, la sugerida ``mínimo − (libre + tránsito)`` (nunca negativa) y si ya se pidió."""
    iins = list(iins)
    ids = [i.pk for i in iins]
    existencias = stock.existencias(ids)
    pedidos = ya_pedido(ids)
    return [
        FilaPedible(
            iin,
            existencias[iin.pk],
            max(Decimal("0"), existencias[iin.pk].minimo - (existencias[iin.pk].libre + existencias[iin.pk].transito)),
            pedidos.get(iin.pk),
        )
        for iin in iins
    ]


# ---- listas para armar el pedido (pasos 2 y 3, extensión 3a) ----


def insumos_bajo_el_minimo(actor):
    """Paso 2: los insumos bajo el mínimo de los invernaderos activos a cargo de ``actor`` (libre + tránsito < mínimo, el mismo criterio que la alerta),
    con su stock, la cantidad sugerida y si ya figuran en otro pedido «en cotización». Una consulta por tabla. No audita ni escribe."""
    _exigir_agronomo(actor)
    iins = _insumos_del_agronomo(actor).order_by(Lower("insumo__nombre_insumo"), "id")
    return [fila for fila in _filas(iins) if fila.existencia.bajo_minimo]


def insumos_pedibles(actor, invernadero_id):
    """Extensión 3a: todos los insumos pedibles de uno de los invernaderos de ``actor`` (los habilitados, no solo los bajo el mínimo), con su stock
    libre, tránsito y mínimo. Un invernadero ajeno da ``PermissionDenied``."""
    _exigir_agronomo(actor)
    if not Invernadero.objects.filter(pk=invernadero_id, agronomo_id=actor.pk).exists():
        raise PermissionDenied("Ese invernadero no está a tu cargo.")
    iins = _insumos_del_agronomo(actor).filter(invernadero_id=invernadero_id).order_by(Lower("insumo__nombre_insumo"), "id")
    return _filas(iins)


def proponer_fecha_limite():
    """Paso 6: hoy + ``dias_limite_cotizacion`` de la configuración operativa (se lee con ``obtener()`` en cada uso)."""
    return stock.hoy() + timedelta(days=configuracion.obtener().dias_limite_cotizacion)


def categorias_del_pedido(iin_ids):
    """Paso 6 (H13, MD-121): los ids de las categorías de los insumos del pedido, con las que se propone filtrar a los proveedores."""
    return set(
        InsumoInvernadero.objects.filter(pk__in=[i for i in (_id_o_none(x) for x in iin_ids) if i is not None]).values_list(
            "insumo__tipo_insumo_id", flat=True
        )
    )


def proveedores_invitables(categoria_ids=None):
    """Pasos 6 y 7a: los proveedores activos (el correo es obligatorio: la extensión 6a quedó obsoleta, P5), por nombre. Con ``categoria_ids``, solo los
    que se especializan en alguna de esas categorías de insumos (MD-121)."""
    consulta = Proveedor.objects.filter(estado_proveedor=Proveedor.Estado.ACTIVO).prefetch_related("especialidades")
    if categoria_ids:
        consulta = consulta.filter(especialidades__in=list(categoria_ids)).distinct()
    return sorted(consulta, key=lambda p: (p.nombre_para_mostrar.lower(), p.pk))


# ---- validación y resumen (pasos 4 a 9) ----


def _validar(actor, datos, iins, proveedores, hoy):
    """Todas las reglas del pedido sobre filas ya leídas (o bloqueadas y releídas): detalles, cantidades, fecha límite y proveedores, con TODOS los
    errores juntos en un ``ValidationError`` por campo. Un invernadero ajeno es ``PermissionDenied``. Devuelve ``(lineas, proveedores_validos,
    fecha_limite)`` con ``lineas = [(iin, cantidad)]`` en el orden recibido."""
    errores = {}

    def agregar(campo, mensaje, codigo):
        errores.setdefault(campo, []).append(ValidationError(mensaje, code=codigo))

    pedidos_detalles = list(datos.get("detalles") or [])
    if not pedidos_detalles:
        agregar("detalles", "El pedido tiene que incluir al menos un insumo.", "sin_detalles")
    lineas, vistos = [], set()
    for crudo_id, crudo_cantidad in pedidos_detalles:
        iin_id = _id_o_none(crudo_id)
        campo = f"insumo_{crudo_id}"
        iin = iins.get(iin_id)
        if iin is None:
            agregar(campo, "Ese insumo no se puede pedir.", "insumo_no_pedible")
            continue
        if iin.invernadero.agronomo_id != actor.pk:
            raise PermissionDenied("Ese invernadero no está a tu cargo.")
        if iin_id in vistos:
            agregar(campo, "Ese insumo ya figura en el pedido para ese invernadero.", "detalle_repetido")
            continue
        vistos.add(iin_id)
        if not (iin.activo and iin.insumo.activo and iin.invernadero.activo):
            agregar(campo, "Ese insumo no se puede pedir: no está activo y habilitado en un invernadero activo.", "insumo_no_pedible")
            continue
        try:
            if isinstance(crudo_cantidad, float):
                raise ValidationError("Ingresá una cantidad válida.", code="cantidad_invalida")
            cantidad = validar_cantidad(crudo_cantidad, iin.insumo.unidad_medida_insumo)
            if cantidad <= 0 or cantidad >= LIMITE_DE_CANTIDAD:
                raise ValidationError("Ingresá una cantidad mayor que cero.", code="cantidad_invalida")
        except ValidationError as error:
            codigo = error.code if error.code in ("cantidad_invalida", "decimales_de_la_unidad") else "cantidad_invalida"
            agregar(f"cantidad_{iin_id}", error.messages[0], codigo)
            continue
        lineas.append((iin, cantidad))

    fecha = datos.get("fecha_limite")
    if not isinstance(fecha, date) or fecha < hoy + timedelta(days=1):
        agregar(
            "fecha_limite",
            f"La fecha límite tiene que ser desde el {(hoy + timedelta(days=1)):%d/%m/%Y}.",
            "fecha_limite_invalida",
        )

    ids = []
    for crudo in datos.get("proveedores") or []:
        valor = _id_o_none(crudo)
        if valor not in ids:
            ids.append(valor)
    if not ids:
        agregar("proveedores", "Tenés que invitar al menos a un proveedor.", "sin_proveedores")
    elegidos = [proveedores.get(i) for i in ids]
    if any(p is None or not p.activo for p in elegidos):
        agregar("proveedores", "Hay un proveedor que no se puede invitar: tiene que estar activo.", "proveedor_no_invitable")
    if errores:
        raise ValidationError(errores)
    return lineas, elegidos, fecha


def _subtotal(cantidad, precio):
    """Cantidad × precio de referencia con dos decimales (``ROUND_HALF_UP``), como ``DetallePedido.subtotal`` (D-89 punto 7)."""
    return (cantidad * precio).quantize(DOS_DECIMALES, ROUND_HALF_UP)


def _leer_iins(datos):
    """Las existencias de los ids pedidos, sin bloquear, con su insumo, categoría e invernadero y su dirección."""
    ids = [i for i in (_id_o_none(par[0]) for par in (datos.get("detalles") or [])) if i is not None]
    return {
        iin.pk: iin
        for iin in InsumoInvernadero.objects.filter(pk__in=ids).select_related("insumo", "insumo__tipo_insumo", "invernadero")
    }


def _leer_proveedores(datos):
    """Los proveedores de los ids pedidos, sin bloquear."""
    ids = [i for i in (_id_o_none(x) for x in (datos.get("proveedores") or [])) if i is not None]
    return {p.pk: p for p in Proveedor.objects.filter(pk__in=ids)}


def resumir_pedido(actor, datos):
    """Pasos 4 a 9: valida el pedido (las mismas reglas que ``registrar_pedido``) y arma el resumen, sin escribir ni bloquear nada.

    ``datos = {"detalles": [(iin_id, cantidad)], "proveedores": [ids], "fecha_limite": fecha}``. Con errores, ``ValidationError`` por campo
    (``detalles``, ``insumo_<id>``, ``cantidad_<id>``, ``fecha_limite``, ``proveedores``). Con la extensión 4c, cada línea trae ``ya_pedido``
    (advierte y deja continuar). Resumen: los detalles agrupados por invernadero con precio de referencia y subtotal, y el monto estimado."""
    _exigir_agronomo(actor)
    iins = _leer_iins(datos)
    lineas, proveedores, fecha = _validar(actor, datos, iins, _leer_proveedores(datos), stock.hoy())
    previos = ya_pedido([iin.pk for iin, _ in lineas])
    grupos = {}
    for iin, cantidad in lineas:
        precio = iin.referencia_precio
        linea = LineaResumen(iin, cantidad, precio, _subtotal(cantidad, precio), previos.get(iin.pk))
        grupos.setdefault(iin.invernadero_id, (iin.invernadero, []))[1].append(linea)
    monto = sum((linea.subtotal for _, ls in grupos.values() for linea in ls), Decimal("0.00"))
    return ResumenPedido(list(grupos.values()), monto, fecha, proveedores)


# ---- registrar (paso 11) ----


def registrar_pedido(actor, datos, construir_url):
    """CMP-RLZ-PED paso 11: registra el pedido «en cotización» con sus detalles (precio de referencia copiado AHORA), las invitaciones y un enlace por
    proveedor, audita ``alta_pedido`` (una sola fila: el pedido, cada detalle y cada invitación como afectados) y deja en ``on_commit`` el correo a
    cada proveedor (``enlaces.crear_enlace``). Devuelve el ``Pedido``.

    - Precondición a: Agrónomo activo (``PermissionDenied``). Los invernaderos de destino tienen que estar a su cargo (``PermissionDenied``) y activos
      (``invernadero_inactivo``).
    - Extensión 11a: con todo bloqueado y releído se vuelve a validar; si algo cambió (un insumo, un invernadero, un proveedor) no se registra nada y
      el ``ValidationError`` dice qué.
    - No toca stock, tránsito, mínimo, reservas, alertas ni contabilidad. Un correo que falla deja el enlace en ``pendiente_envio`` (12a)."""
    _exigir_agronomo(actor)
    leidos = _leer_iins(datos)
    for iin in leidos.values():  # el alcance se verifica ya, sin bloquear, para saber qué invernaderos tomar
        if iin.invernadero.agronomo_id != actor.pk:
            raise PermissionDenied("Ese invernadero no está a tu cargo.")
    ids_de_invernaderos = sorted({iin.invernadero_id for iin in leidos.values()})
    with transaction.atomic():
        Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk).first()
        _actor_sigue_activo(actor)
        for invernadero_id in ids_de_invernaderos:
            invernadero = bloquear_invernadero_activo(invernadero_id)
            if invernadero.agronomo_id != actor.pk:
                raise PermissionDenied("Ese invernadero no está a tu cargo.")
        iins = {
            iin.pk: iin
            for iin in InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",))
            .filter(pk__in=list(leidos))
            .select_related("insumo", "insumo__tipo_insumo", "invernadero")
            .order_by("id")
        }
        ids_de_proveedores = [i for i in (_id_o_none(x) for x in (datos.get("proveedores") or [])) if i is not None]
        proveedores = {
            p.pk: p for p in Proveedor.objects.select_for_update(no_key=True).filter(pk__in=ids_de_proveedores).order_by("id")
        }
        hoy = stock.hoy()
        lineas, invitados, fecha = _validar(actor, datos, iins, proveedores, hoy)

        pedido = Pedido.objects.create(
            agronomo=Agronomo.objects.get(pk=actor.pk), fecha_pedido=hoy, fecha_limite_cotizaciones=fecha
        )
        detalles = [
            DetallePedido.objects.create(
                pedido=pedido, insumo_invernadero=iin, cantidad_detalle=cantidad, precio_unitario_de_pedido=iin.referencia_precio
            )
            for iin, cantidad in lineas
        ]
        invitaciones = [InvitacionPedido.objects.create(pedido=pedido, proveedor=proveedor) for proveedor in invitados]
        for invitacion in invitaciones:
            enlaces.crear_enlace(invitacion, construir_url)

        monto = sum((d.subtotal for d in detalles), Decimal("0.00"))
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_PEDIDO,
            afectados=[pedido, *detalles, *invitaciones],
            detalle={
                "cambios": {
                    "estado": {"antes": None, "despues": pedido.estado_pedido},
                    "fecha_pedido": {"antes": None, "despues": hoy.isoformat()},
                    "fecha_limite_cotizaciones": {"antes": None, "despues": fecha.isoformat()},
                    "monto_estimado": {"antes": None, "despues": texto_precio(monto)},
                },
                "datos": {
                    "detalles": [
                        f"{d}: {texto_cantidad(d.cantidad_detalle, d.insumo_invernadero.insumo.unidad_medida_insumo)} "
                        f"a {texto_precio(d.precio_unitario_de_pedido)}"
                        for d in detalles
                    ],
                    "invitaciones": [referencia(i) for i in invitaciones],
                },
            },
        )
    return pedido


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-CNS-PED · Consultar Pedido (CMP-02a, paso 5). Una consulta: no escribe, no bloquea y no se audita (regla 9, SEG-14). «Reenviar invitación» y
# «Cancelar» son de CMP-02b y «Generar orden», de CMP-03: la ficha todavía no trae acciones. Decisión del estudiante (23/11/2026): la cotización de
# cada proveedor se ve en solo lectura desde que llega (regla 6 de CMP-CNS-PED y prototipo), no recién al terminar el día de la fecha límite.
# ---------------------------------------------------------------------------------------------------------------------------------

# Una fila del listado (regla 3): el pedido, su monto estimado, los invernaderos de destino (nombres), la cantidad de insumos, los proveedores invitados,
# las cotizaciones recibidas y si tiene la fecha límite vencida sin resolver (el panel del Agrónomo los muestra, H16).
FilaDePedido = namedtuple("FilaDePedido", "pedido monto invernaderos insumos invitados cotizaciones por_resolver")
# Un proveedor invitado en la ficha (regla 5): si cotizó, su enlace vigente o el último y el estado con que se lo muestra, y si el correo no salió.
Invitado = namedtuple("Invitado", "invitacion proveedor cotizo enlace estado_del_enlace sin_enviar puede_reenviar")
# Una cotización recibida (regla 6), con sus líneas tal como se muestran (``cotizaciones.lineas_para_mostrar``) y su monto.
CotizacionRecibida = namedtuple("CotizacionRecibida", "cotizacion lineas monto")
FichaDePedido = namedtuple("FichaDePedido", "pedido monto grupos invitados cotizaciones por_resolver automatica puede_cancelar")

ESTADOS_DEL_PEDIDO = {valor for valor, _ in Pedido.Estado.choices}


def _exigir_consulta(actor):
    """Precondición a de CMP-CNS-PED: el actor es un Agrónomo o un Gerente con la cuenta activa (SEG-13); si no, ``PermissionDenied``."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
        raise PermissionDenied("Solo un Gerente o un Agrónomo activos pueden consultar pedidos.")


def _fecha_o_none(valor):
    """Una fecha (``date`` o texto ``AAAA-MM-DD``) o ``None``: un filtro mal formado se ignora."""
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError:
        return None


def _vencido_por_resolver(pedido, hoy):
    """Regla 3: «en cotización» con la fecha límite pasada (el último día todavía se cotiza: D-88 punto 2)."""
    return pedido.en_cotizacion and pedido.fecha_limite_cotizaciones < hoy


def consultar_pedidos(actor, filtros=None):
    """CMP-CNS-PED reglas 1 a 3: los pedidos que ``actor`` ve (el Agrónomo, los suyos; el Gerente, todos), del más reciente al más viejo, con sus filtros.

    ``filtros`` (todos opcionales; uno mal formado se ignora): ``estado``, ``invernadero_id`` (algún detalle va ahí), ``proveedor_id`` (invitado),
    ``desde`` y ``hasta`` (inclusive; fechas o ``AAAA-MM-DD``) sobre la fecha del pedido o, con ``fecha_de="limite"``, sobre la fecha límite, y
    ``agronomo_id`` (solo lo usa el Gerente: el Agrónomo ya ve solo lo suyo). Devuelve ``list[FilaDePedido]`` con una consulta por tabla (no una por fila)."""
    _exigir_consulta(actor)
    filtros = filtros or {}
    consulta = Pedido.objects.en_alcance_de(actor).select_related("agronomo")
    if filtros.get("estado") in ESTADOS_DEL_PEDIDO:
        consulta = consulta.filter(estado_pedido=filtros["estado"])
    invernadero_id = _id_o_none(filtros.get("invernadero_id"))
    if invernadero_id is not None:
        consulta = consulta.filter(pk__in=DetallePedido.objects.filter(insumo_invernadero__invernadero_id=invernadero_id).values("pedido_id"))
    proveedor_id = _id_o_none(filtros.get("proveedor_id"))
    if proveedor_id is not None:
        consulta = consulta.filter(pk__in=InvitacionPedido.objects.filter(proveedor_id=proveedor_id).values("pedido_id"))
    campo = "fecha_limite_cotizaciones" if filtros.get("fecha_de") == "limite" else "fecha_pedido"
    desde, hasta = _fecha_o_none(filtros.get("desde")), _fecha_o_none(filtros.get("hasta"))
    if desde is not None:
        consulta = consulta.filter(**{f"{campo}__gte": desde})
    if hasta is not None:
        consulta = consulta.filter(**{f"{campo}__lte": hasta})
    agronomo_id = _id_o_none(filtros.get("agronomo_id"))
    if rol_de(actor) == Usuario.Rol.GERENTE and agronomo_id is not None:
        consulta = consulta.filter(agronomo_id=agronomo_id)

    lista = list(consulta.order_by("-fecha_pedido", "-id"))
    ids = [p.pk for p in lista]
    detalles = {}
    for pedido_id, invernadero, cantidad, precio in DetallePedido.objects.filter(pedido_id__in=ids).values_list(
        "pedido_id", "insumo_invernadero__invernadero__nombre_invernadero", "cantidad_detalle", "precio_unitario_de_pedido"
    ):
        detalles.setdefault(pedido_id, []).append((invernadero, _subtotal(cantidad, precio)))
    invitados = dict(InvitacionPedido.objects.filter(pedido_id__in=ids).values_list("pedido_id").annotate(n=Count("id")))
    recibidas = dict(Cotizacion.objects.filter(pedido_id__in=ids).values_list("pedido_id").annotate(n=Count("id")))
    hoy = stock.hoy()
    return [
        FilaDePedido(
            pedido=p,
            monto=sum((subtotal for _, subtotal in detalles.get(p.pk, [])), Decimal("0.00")),
            invernaderos=sorted({nombre for nombre, _ in detalles.get(p.pk, [])}),
            insumos=len(detalles.get(p.pk, [])),
            invitados=invitados.get(p.pk, 0),
            cotizaciones=recibidas.get(p.pk, 0),
            por_resolver=_vencido_por_resolver(p, hoy),
        )
        for p in lista
    ]


def _estado_del_enlace(enlace, pedido, hoy):
    """Regla 5: el estado con que se muestra un enlace. Uno ``vigente`` con la fecha límite pasada, o con el pedido ya cerrado, se muestra «vencido»
    aunque el paso diario (CMP-03) todavía no lo haya marcado; con el pedido cancelado, «anulado»."""
    if enlace is None:
        return None
    if enlace.estado != EnlaceProveedor.Estado.VIGENTE:
        return enlace.estado
    if pedido.estado_pedido == Pedido.Estado.CANCELADO:
        return EnlaceProveedor.Estado.ANULADO.value
    if not pedido.en_cotizacion or hoy > pedido.fecha_limite_cotizaciones:
        return EnlaceProveedor.Estado.VENCIDO.value
    return EnlaceProveedor.Estado.VIGENTE.value


def ficha_de_pedido(actor, pedido_id):
    """CMP-CNS-PED reglas 4 a 6: la ficha del pedido. El Agrónomo abre los suyos y el Gerente todos, en solo lectura; uno ajeno es ``PermissionDenied``
    y uno que no existe, ``Http404`` (D-28).

    Trae el pedido (con el Agrónomo que lo realizó y, si está cancelado, su motivo, su fecha de cierre y si fue automática); los detalles **agrupados por
    invernadero de destino** con su precio de referencia y su subtotal, y el monto; cada proveedor invitado (si cotizó y el estado de su enlace); y las
    cotizaciones recibidas con sus líneas, **desde que llegan**."""
    _exigir_consulta(actor)
    pedido = Pedido.objects.select_related("agronomo").filter(pk=pedido_id).first()
    if pedido is None:
        raise Http404("No existe ese pedido.")
    if not Pedido.objects.en_alcance_de(actor).filter(pk=pedido.pk).exists():
        raise PermissionDenied("Ese pedido no es tuyo: solo lo ve el Agrónomo que lo realizó y el Gerente.")
    hoy = stock.hoy()
    detalles = list(
        DetallePedido.objects.filter(pedido=pedido)
        .select_related("insumo_invernadero__insumo", "insumo_invernadero__invernadero")
        .order_by("insumo_invernadero__invernadero__nombre_invernadero", "insumo_invernadero__invernadero_id", "id")
    )
    grupos = {}
    for detalle in detalles:
        invernadero = detalle.insumo_invernadero.invernadero
        grupos.setdefault(invernadero.pk, (invernadero, []))[1].append(detalle)
    recibidas = list(Cotizacion.objects.filter(pedido=pedido).select_related("proveedor").order_by("id"))
    cotizaron = {c.proveedor_id for c in recibidas}
    # Reglas 7 y 8 y D-30: solo el Agrónomo del pedido, con el pedido en cotización (y, para reenviar, hasta la fecha límite: D-88 punto 2).
    es_el_agronomo = rol_de(actor) == Usuario.Rol.AGRONOMO and pedido.agronomo_id == actor.pk
    puede_cancelar = es_el_agronomo and pedido.en_cotizacion
    reenvio_abierto = puede_cancelar and hoy <= pedido.fecha_limite_cotizaciones
    invitados = []
    for invitacion in InvitacionPedido.objects.filter(pedido=pedido).select_related("proveedor").prefetch_related("enlaces").order_by("id"):
        enlace = max(invitacion.enlaces.all(), key=lambda e: e.pk, default=None)
        invitados.append(
            Invitado(
                invitacion,
                invitacion.proveedor,
                invitacion.proveedor_id in cotizaron,
                enlace,
                _estado_del_enlace(enlace, pedido, hoy),
                enlace is not None and enlace.estado == "vigente" and enlace.estado_envio == EnlaceProveedor.EstadoEnvio.PENDIENTE_ENVIO,
                reenvio_abierto and invitacion.proveedor.activo and invitacion.proveedor_id not in cotizaron,
            )
        )
    return FichaDePedido(
        pedido=pedido,
        monto=sum((d.subtotal for d in detalles), Decimal("0.00")),
        grupos=list(grupos.values()),
        invitados=invitados,
        cotizaciones=[CotizacionRecibida(c, servicio_de_cotizaciones.lineas_para_mostrar(c), c.monto_cotizacion) for c in recibidas],
        por_resolver=_vencido_por_resolver(pedido, hoy),
        automatica=pedido.causa_cancelacion not in (None, Pedido.Causa.MANUAL),
        puede_cancelar=puede_cancelar,
    )


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-CNL-PED · Cancelar Pedido (CMP-02b). La manual (``cancelar_pedido``) y las automáticas (``cancelar_pedido_automaticamente``: pasos diarios 60 y 62 de
# CMP-03, y la baja o el traspaso del Agrónomo, MD-62 y H17) usan **la misma función interna**, ``_cancelar``.
#
# Bloqueos (docs/patrones/stock.md, sección 5, punto 8; siempre ``FOR NO KEY UPDATE``): la cuenta de quien actúa → el pedido → sus cotizaciones «propuesta»
# (en orden de id) → sus enlaces vigentes (en orden de id). Cotizar bloquea proveedor → pedido → enlace: el pedido es el mismo punto de espera, así que
# uno de los dos gana y el otro ve el estado nuevo (6a y 11a). Los correos salen en ``on_commit``; las notificaciones, dentro de la transacción (D-42).
# ---------------------------------------------------------------------------------------------------------------------------------

LARGO_DEL_MOTIVO = Pedido._meta.get_field("motivo_cancelacion").max_length
# Resumen de la cancelación (pasos 2 y 4): ``cotizaciones`` es ``[(proveedor, monto)]``; ``descartadas`` y ``enlaces`` son lo que se cambiaría; ``invitados``,
# los proveedores a quienes se avisa.
ResumenDeCancelacion = namedtuple("ResumenDeCancelacion", "pedido motivo cotizaciones descartadas enlaces invitados")


def _motivo_valido(motivo):
    """Extensión 3a y regla «Motivo»: obligatorio, recortado y de hasta 500 caracteres; si no, ``ValidationError`` en el campo ``motivo``."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise _error("motivo", "Contá por qué se cancela el pedido.", "motivo_obligatorio")
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise _error("motivo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.", "motivo_largo")
    return motivo


def _pedido_cancelable_por(actor, pedido_id):
    """Precondiciones a y b de CMP-CNL-PED y regla «Quién cancela»: ``actor`` es un Agrónomo activo y es quien hizo el pedido (``PermissionDenied``); un
    pedido inexistente es ``Http404`` (D-28). Devuelve el pedido leído, sin bloquear."""
    _exigir_agronomo(actor)
    pedido = Pedido.objects.filter(pk=pedido_id).first()
    if pedido is None:
        raise Http404("No existe ese pedido.")
    if pedido.agronomo_id != actor.pk:
        raise PermissionDenied("Solo el Agrónomo que hizo el pedido lo puede cancelar.")
    return pedido


def _exigir_en_cotizacion(pedido):
    """Precondición c y extensión 6a: el pedido sigue «en cotización»; si no, ``ErrorDeCompras`` ``pedido_no_en_cotizacion`` con el estado actual."""
    if not pedido.en_cotizacion:
        raise ErrorDeCompras(
            "pedido_no_en_cotizacion",
            f"El pedido {pedido} ya no está en cotización: está {pedido.get_estado_pedido_display().lower()}.",
            datos={"estado": pedido.estado_pedido},
        )


def resumir_cancelacion(actor, pedido_id, motivo):
    """Pasos 2 y 4 de CMP-CNL-PED: qué se cancela, sin escribir ni bloquear nada. Aplica las mismas precondiciones y el mismo motivo que
    ``cancelar_pedido``. Devuelve un ``ResumenDeCancelacion``: las cotizaciones recibidas con su monto, cuántas se descartan, cuántos enlaces se anulan y
    los proveedores invitados (a todos se les avisa por correo)."""
    pedido = _pedido_cancelable_por(actor, pedido_id)
    motivo = _motivo_valido(motivo)
    _exigir_en_cotizacion(pedido)
    recibidas = list(Cotizacion.objects.filter(pedido=pedido).select_related("proveedor").prefetch_related("lineas").order_by("id"))
    invitados = [i.proveedor for i in InvitacionPedido.objects.filter(pedido=pedido).select_related("proveedor").order_by("id")]
    return ResumenDeCancelacion(
        pedido,
        motivo,
        [(c.proveedor, c.monto_cotizacion) for c in recibidas],
        sum(1 for c in recibidas if c.estado_cotizacion == Cotizacion.Estado.PROPUESTA),
        EnlaceProveedor.objects.filter(invitacion__pedido=pedido, estado=EnlaceProveedor.Estado.VIGENTE).count(),
        invitados,
    )


def _cancelar(pedido_id, causa, motivo, actor):
    """La función interna de la cancelación (CMP-CNL-PED paso 6), dentro de la transacción del llamador. Bloquea el pedido, verifica que siga «en
    cotización» (6a), lo pasa a «cancelado» con la fecha de cierre de hoy, el motivo y la causa, descarta las cotizaciones «propuesta», anula los enlaces
    vigentes, audita ``cancelacion_pedido`` y deja en ``on_commit`` el correo a cada invitado (sin el motivo). La manual audita a ``actor``; la automática
    (causa distinta de ``manual``) audita como InfoPonia (``usuario=None``) y avisa en la campana según H21 (``actor`` es solo a quien no se avisa)."""
    pedido = Pedido.objects.select_for_update(no_key=True, of=("self",)).select_related("agronomo").get(pk=pedido_id)
    _exigir_en_cotizacion(pedido)
    propuestas = list(
        Cotizacion.objects.select_for_update(no_key=True).filter(pedido=pedido, estado_cotizacion=Cotizacion.Estado.PROPUESTA).order_by("id")
    )
    anulados = enlaces.anular_enlaces_de_pedido(pedido)
    Cotizacion.objects.filter(pk__in=[c.pk for c in propuestas]).update(estado_cotizacion=Cotizacion.Estado.DESCARTADA)
    hoy = stock.hoy()
    pedido.estado_pedido = Pedido.Estado.CANCELADO
    pedido.fecha_cierre_pedido = hoy
    pedido.motivo_cancelacion = motivo
    pedido.causa_cancelacion = causa
    pedido.save(update_fields=["estado_pedido", "fecha_cierre_pedido", "motivo_cancelacion", "causa_cancelacion"])
    manual = causa == Pedido.Causa.MANUAL
    RegistroAuditoria.objects.registrar(
        usuario=actor if manual else None,
        accion=RegistroAuditoria.Accion.CANCELACION_PEDIDO,
        afectados=[pedido, *propuestas, *anulados],
        detalle={
            "cambios": {
                "estado": {"antes": Pedido.Estado.EN_COTIZACION.value, "despues": Pedido.Estado.CANCELADO.value},
                "fecha_cierre_pedido": {"antes": None, "despues": hoy.isoformat()},
                "motivo_cancelacion": {"antes": None, "despues": motivo},
                "causa_cancelacion": {"antes": None, "despues": causa},
            },
            "datos": {
                "cotizaciones_descartadas": [referencia(c) for c in propuestas],
                "enlaces_anulados": [referencia(e) for e in anulados],
            },
        },
    )
    if not manual:  # H21 y D-87 punto 3: el Agrónomo activo de cada destino o, si falta, el Gerente; nunca a quien hizo la acción
        destinos = set(DetallePedido.objects.filter(pedido=pedido).values_list("insumo_invernadero__invernadero_id", flat=True))
        agronomo = pedido.agronomo
        notificaciones.notificar_a_varios(
            avisos.destinatarios_por_destino(destinos, excluir=actor),
            f"Pedido {pedido} cancelado",
            f"El pedido {pedido} de {agronomo.get_full_name() or agronomo.email} se canceló solo ({motivo}). "
            "Se avisó por correo a los proveedores invitados.",
        )
    transaction.on_commit(lambda: enlaces.enviar_aviso_de_cancelacion(pedido.pk))
    return pedido


def cancelar_pedido(actor, pedido_id, motivo):
    """CMP-CNL-PED, cancelación manual: el Agrónomo que hizo el pedido lo cancela con un motivo y lo devuelve ya cancelado.

    - Precondiciones a a c, extensiones 3a y 6a: ``_pedido_cancelable_por``, ``_motivo_valido`` y ``_exigir_en_cotizacion`` (esta última, otra vez con el
      pedido bloqueado). Se puede antes o después de la fecha límite, mientras siga «en cotización».
    - Postcondiciones a a e y garantías mínimas: ``_cancelar``; es atómica y no toca stock, tránsito, mínimo, reservas, alertas ni contabilidad.
    - No genera notificación de campana: quien actúa es el único Agrónomo del pedido (H21) y los proveedores se enteran por correo."""
    _pedido_cancelable_por(actor, pedido_id)
    motivo = _motivo_valido(motivo)
    with transaction.atomic():
        Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk).first()
        _actor_sigue_activo(actor)
        return _cancelar(pedido_id, Pedido.Causa.MANUAL, motivo, actor)


def cancelar_pedido_automaticamente(pedido, causa, *, actor=None):
    """Las cancelaciones automáticas de CMP-CNL-PED (regla «Cancelaciones automáticas»): sin flujo y sin actor humano. ``causa`` es una de las cuatro
    automáticas (otra es un error de uso: ``ValueError``); el motivo es su literal fijo (``MOTIVOS_DE_CANCELACION_AUTOMATICA``). ``actor`` es la cuenta que
    dio la baja o hizo el traspaso, solo para no avisarle. Se audita como InfoPonia. Devuelve el pedido cancelado o ``None`` si, releído con el bloqueo, ya no
    estaba «en cotización» (la usan los pasos diarios de CMP-03). Corre dentro de la transacción del llamador si hay una."""
    if causa not in MOTIVOS_DE_CANCELACION_AUTOMATICA:
        raise ValueError(f"{causa!r} no es una causa de cancelación automática.")
    try:
        with transaction.atomic():
            return _cancelar(pedido.pk, causa, MOTIVOS_DE_CANCELACION_AUTOMATICA[causa], actor)
    except ErrorDeCompras as error:
        if error.codigo == "pedido_no_en_cotizacion":
            return None
        raise


# ---- CMP-CNS-PED regla 7 (CMP-02b): «Reenviar invitación» ----


def reenviar_invitacion(actor, invitacion_id, construir_url):
    """Regla 7 de CMP-CNS-PED (H15.1): genera un enlace nuevo para un proveedor invitado que todavía no cotizó, el anterior pasa a «reemplazado» y se le envía el
    correo con el nuevo (en ``on_commit``; si falla, el enlace queda ``pendiente_envio`` y no hay reintento automático: D-88 punto 6). Devuelve el enlace nuevo.

    - Solo el Agrónomo del pedido (``PermissionDenied``); una invitación inexistente es ``Http404``.
    - Con todo bloqueado (cuenta → proveedor → pedido → enlace, como al cotizar) se verifica: pedido en cotización (``pedido_no_en_cotizacion``), hoy ≤ fecha límite
      (``fecha_limite_vencida``: un enlace nuevo nacería vencido, D-88 punto 2), proveedor activo (``proveedor_inactivo``) y sin cotización (``ya_cotizo``).
    - Se audita ``reenvio_invitacion``; los textos de los dos enlaces los distinguen (D-36)."""
    _exigir_agronomo(actor)
    leida = InvitacionPedido.objects.select_related("pedido").filter(pk=invitacion_id).first()
    if leida is None:
        raise Http404("No existe esa invitación.")
    if leida.pedido.agronomo_id != actor.pk:
        raise PermissionDenied("Solo el Agrónomo que hizo el pedido puede reenviar sus invitaciones.")
    with transaction.atomic():
        Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk).first()
        _actor_sigue_activo(actor)
        proveedor = Proveedor.objects.select_for_update(no_key=True).get(pk=leida.proveedor_id)
        pedido = Pedido.objects.select_for_update(no_key=True).get(pk=leida.pedido_id)
        _exigir_en_cotizacion(pedido)
        if stock.hoy() > pedido.fecha_limite_cotizaciones:
            raise ErrorDeCompras(
                "fecha_limite_vencida",
                f"La fecha límite del pedido {pedido} ya pasó: un enlace nuevo no le serviría a {proveedor}.",
            )
        if not proveedor.activo:
            raise ErrorDeCompras("proveedor_inactivo", f"{proveedor} está dado de baja: no se le puede reenviar la invitación.")
        if Cotizacion.objects.filter(pedido=pedido, proveedor=proveedor).exists():
            raise ErrorDeCompras("ya_cotizo", f"{proveedor} ya cotizó este pedido: no hace falta reenviarle la invitación.")
        nuevo, anterior = enlaces.reemplazar_enlace(leida, construir_url)
        datos = {
            "proveedor": referencia(proveedor),
            "pedido": referencia(pedido),
            "enlace_nuevo": {"id": nuevo.pk, "texto": f"Enlace nuevo de {leida.proveedor} en {pedido}"},
        }
        if anterior is not None:
            datos["enlace_anterior"] = {"id": anterior.pk, "texto": f"Enlace anterior (reemplazado) de {leida.proveedor} en {pedido}"}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REENVIO_INVITACION,
            afectados=[pedido, proveedor, leida, *([anterior] if anterior is not None else []), nuevo],
            detalle={"datos": datos},
        )
    return nuevo
