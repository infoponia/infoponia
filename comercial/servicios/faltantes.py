# El camino de faltante (COM-04a, paso 3; docs/patrones/stock_maduro.md, sección 8; docs/casos_de_uso/comercial/faltante.md, «El camino de faltante») y COM-DCD-FLT · Decidir
# Faltante (COM-04c; D-65). El camino: lo que pasa con un detalle que quedó con cantidad sin cubrir después de intentar cubrirlo con PROD-ASG-STK. Una sola función que usan
# PROD-CNC-CSC (13a), PROD-REG-MRM (10c), PROD-CNL-ORD (8c y 8d) y PROD-VNC-CAM (3a.2a); desde COM-04c crea o reemplaza el enlace del cliente (con su correo en `on_commit`) o, sin
# correo, avisa al Vendedor que registre él la decisión. COM-DCD-FLT: el cliente decide por su enlace (sin cuenta) o el Vendedor por él (extensión 1a).
#
# El camino corre en la transacción del caso de uso que lo llama, con la venta y el detalle ya bloqueados. NO audita (D-36: lo pone el llamador en su registro); la notificación del
# faltante al Vendedor la arma cada caso de uso (los de cada uno son distintos), salvo «registrá vos la decisión» (sin correo), que es de esta función.
# Orden de bloqueo de COM-DCD-FLT (docs/patrones/bloqueos.md, «Cosecha y cámara»; `FOR NO KEY UPDATE`): cuentas → invernaderos (`bloquear_invernadero_para_alertas`: activo o no, D-64
# punto 12) → variedades → sectores → lotes → partidas → venta → detalles → cosechas → reservas y líneas → el enlace, siempre al final.
# Fuente: D-64 puntos 8, 12 y 13; D-65.
# `cosechas` y `camara` importan este módulo; para no formar un ciclo, COM-DCD-FLT los importa dentro de las funciones que los usan.

import logging
from collections import namedtuple
from datetime import timedelta
from decimal import Decimal
from functools import partial
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleVenta, EnlaceCliente, ReservaStock
from comercial.servicios import enlaces, entregas, stock_maduro
from comercial.servicios.comprobantes import Destinatario
from comercial.servicios.stock_maduro import Periodo
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import stock
from maestros.models import Variedad
from maestros.servicios import configuracion
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from produccion.models import Cosecha, Lote, MovimientoStock, OcupacionSector, StockCosechado

logger = logging.getLogger("infoponia.faltantes")

NO_CAMPO = "__all__"  # la clave de los errores que no son de un campo (`NON_FIELD_ERRORS`)
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
CENTAVOS = Decimal("0.01")
ACEPTAR, RECHAZAR = "aceptar", "rechazar"
Estado = DetalleVenta.Estado

# `detalle` es el `DetalleVenta` ya cambiado (o `None` con un período); `venta`, su `CompraVenta` (o `None`); `sin_cubrir`, lo que quedó sin cubrir;
# `ya_pendiente`, si el detalle ya esperaba la decisión del cliente (8d de PROD-CNL-ORD: solo cambió la fecha); `enlace`, el `EnlaceCliente` nuevo (o `None`: período, o cliente sin correo).
CaminoDeFaltante = namedtuple("CaminoDeFaltante", "detalle venta sin_cubrir ya_pendiente enlace", defaults=(None,))

# COM-DCD-FLT. `FilaPendiente.solo_rechazar` es la extensión 2b (disponible 0). `contacto` son los datos del Vendedor para la pantalla de enlace que no sirve (2a).
FilaPendiente = namedtuple("FilaPendiente", "detalle_id variedad solicitada disponible precio subtotal_disponible solo_rechazar")
DatosDeDecision = namedtuple("DatosDeDecision", "venta enlace vence modalidad destino pendientes otros monto_actual contacto")
ResumenDeDecision = namedtuple("ResumenDeDecision", "filas monto_total queda_cancelada")
ResultadoDecision = namedtuple("ResultadoDecision", "venta confirmados rechazados partidas movimientos cosechas_canceladas enlace")


def _error(campo, codigo, mensaje, **params):
    """Levanta un `ValidationError` por campo con su código (y `params` si el llamador los necesita, por ejemplo qué detalles cambiaron)."""
    raise ValidationError({campo: [ValidationError(mensaje, code=codigo, params=params or None)]})


def _vendedor_activo(venta):
    """La cuenta activa del Vendedor del contrato (D-60: el actual), o `None`."""
    return Usuario.objects.filter(pk=venta.vendedor_id, is_active=True).first()


def _enlace_del_camino(venta):
    """El enlace del camino de faltante (D-65 puntos 1, 5 y 6): con correo del cliente, `crear_enlace` (reemplaza el vigente; vence en la `fecha_pendiente_decision` más reciente de los
    detalles pendientes más `dias_vigencia_enlace_faltante`); sin correo, el vigente (si había) pasa a `reemplazado` y se avisa al Vendedor que registre él la decisión."""
    cliente = venta.cliente
    if cliente.email_cliente:
        fechas = DetalleVenta.objects.filter(compra_venta=venta, estado_detalle_venta=Estado.PENDIENTE_DECISION).values_list("fecha_pendiente_decision", flat=True)
        vence = max(f for f in fechas if f) + timedelta(days=configuracion.obtener().dias_vigencia_enlace_faltante)
        enlace, _ = enlaces.crear_enlace(EnlaceCliente.Tipo.DECISION_FALTANTE, cliente, compra_venta=venta, vence=vence)
        return enlace
    enlaces.reemplazar_enlaces_de(venta)
    vendedor = _vendedor_activo(venta)
    if vendedor is not None:
        notificaciones.notificar(
            vendedor,
            f"{venta.codigo}: el cliente no tiene correo",
            f"El cliente de {venta.codigo} no tiene correo: registrá vos su decisión sobre el faltante desde la ficha de la compra («Registrar decisión de faltante»).",
        )
    return None


def seguir_camino_de_faltante(detalle_o_periodo, sin_cubrir, *, origen):
    """Sigue el camino de faltante de `detalle_o_periodo` (un `DetalleVenta` o un `Periodo`) con `sin_cubrir` plantas sin cubrir.

    - `sin_cubrir` es un entero mayor que cero (si no, `ValueError`); `origen` es quien actúa (`Usuario`) o `None` si actúa InfoPonia (D-27). Corre dentro de la transacción del
      llamador (sin ella, `RuntimeError`).
    - **Detalle de compra-venta**: pasa a «pendiente de decisión del cliente» con `fecha_pendiente_decision = hoy`; si ya lo estaba, solo cambia la fecha
      (8d de PROD-CNL-ORD). Un detalle «confirmado» que pierde producto (D-64 punto 13) vuelve a «pendiente» con la fecha de hoy y SIN `cant_entregada_venta`.
      La venta pasa a «pendiente de decisión del cliente» (si ya lo estaba, no cambia). Después, el enlace del cliente (COM-04c, D-65): `_enlace_del_camino`.
    - **Período de un suministro**: no cambia ningún estado ni crea enlace; queda con cantidad sin cubrir y la pre-reserva diaria lo vuelve a intentar mientras su fecha
      esté en la ventana (sección 7 del patrón).
    """
    if transaction.get_autocommit():
        raise RuntimeError("`seguir_camino_de_faltante` corre dentro de la transacción del caso de uso que la llama.")
    if isinstance(sin_cubrir, bool) or not isinstance(sin_cubrir, int) or sin_cubrir <= 0:
        raise ValueError("`sin_cubrir` tiene que ser un entero mayor que cero.")
    if isinstance(detalle_o_periodo, Periodo):
        return CaminoDeFaltante(None, None, sin_cubrir, False, None)
    hoy = stock.hoy()
    pasado = detalle_o_periodo
    detalle = DetalleVenta.objects.get(pk=pasado.pk)  # relee: el llamador lo tiene bloqueado, y su copia en memoria puede ser vieja
    ya_pendiente = detalle.estado_detalle_venta == DetalleVenta.Estado.PENDIENTE_DECISION
    cambios = {"estado_detalle_venta": DetalleVenta.Estado.PENDIENTE_DECISION, "fecha_pendiente_decision": hoy}
    if detalle.estado_detalle_venta == DetalleVenta.Estado.CONFIRMADO:
        cambios["cant_entregada_venta"] = None  # D-64 punto 13: al cliente no le cambian lo que aceptó sin preguntarle
    DetalleVenta.objects.filter(pk=detalle.pk).update(**cambios)
    for campo, valor in cambios.items():
        setattr(detalle, campo, valor)
        setattr(pasado, campo, valor)
    venta = CompraVenta.objects.select_related("cliente").get(pk=detalle.compra_venta_id)
    if venta.estado_venta != CompraVenta.Estado.PENDIENTE_DECISION:
        CompraVenta.objects.filter(pk=venta.pk).update(estado_venta=CompraVenta.Estado.PENDIENTE_DECISION)
        venta.estado_venta = CompraVenta.Estado.PENDIENTE_DECISION
    return CaminoDeFaltante(detalle, venta, sin_cubrir, ya_pendiente, _enlace_del_camino(venta))


# ---- COM-DCD-FLT: lecturas ----


def _pendientes(venta):
    """Los detalles de la venta «pendientes de decisión del cliente», con su variedad, en un orden estable."""
    return list(venta.detalles.filter(estado_detalle_venta=Estado.PENDIENTE_DECISION).select_related("variedad").order_by("variedad_id", "pk"))


def puede_decidir_el_vendedor(venta, hoy=None):
    """Extensión 1a y regla «Quién decide»: la venta espera la decisión y el cliente no tiene correo, o no hay un enlace que sirva (venció, no se pudo enviar o no hay)."""
    hoy = hoy or stock.hoy()
    if venta.estado_venta != CompraVenta.Estado.PENDIENTE_DECISION:
        return False
    if not _pendientes(venta):
        return False
    if not venta.cliente.email_cliente:
        return True
    vigente = venta.enlaces.filter(estado=EnlaceCliente.Estado.VIGENTE, tipo=EnlaceCliente.Tipo.DECISION_FALTANTE).first()
    return vigente is None or vigente.fecha_vencimiento < hoy or vigente.estado_envio == EnlaceCliente.EstadoEnvio.PENDIENTE_ENVIO


def _exigir_vendedor(vendedor, venta=None):
    """Extensión 1a: solo el Vendedor activo del contrato (el Gerente ve la venta, pero no decide)."""
    if not getattr(vendedor, "is_active", False) or rol_de(vendedor) != Usuario.Rol.VENDEDOR or (venta is not None and venta.vendedor_id != vendedor.pk):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _destino(venta):
    """`(modalidad, destino)` para el paso 2: la dirección de envío, o el invernadero de retiro con su dirección."""
    from comercial.servicios import clientes as api_clientes

    if venta.modalidad_entrega == CompraVenta.Modalidad.ENVIO:
        hija = api_clientes.direccion_hija(venta.direccion_envio_id)
        return "Envío a domicilio", (f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else "")
    hija = api_clientes.direccion_hija(venta.invernadero_retiro.direccion_id)
    inv = venta.invernadero_retiro
    return "Retiro en invernadero", (f"{inv.nombre_invernadero} ({hija.texto()})" if hija else inv.nombre_invernadero)


def _contacto(venta):
    """Los datos del Vendedor del contrato para la pantalla de enlace que no sirve (2a): nombre, teléfono y correo de su cuenta."""
    vendedor = Usuario.objects.filter(pk=venta.vendedor_id).first()
    if vendedor is None:
        return SimpleNamespace(nombre="", telefono="", email="")
    return SimpleNamespace(nombre=vendedor.get_full_name() or vendedor.email, telefono=vendedor.telefono, email=vendedor.email)


def contacto_del_vendedor(venta_id):
    """El contacto del Vendedor de esa venta (pantalla «Este enlace no se puede usar», extensiones 2a y 6a)."""
    return _contacto(CompraVenta.objects.get(pk=venta_id))


def _monto(detalles, decisiones, disponible):
    """El monto total de la venta con lo que recibirá cada pendiente (aceptado: la disponible; rechazado: nada) y los demás detalles como están (confirmado: lo entregado; abierto: lo solicitado)."""
    total = Decimal(0)
    for d in detalles:
        if d.estado_detalle_venta == Estado.PENDIENTE_DECISION:
            cantidad = disponible[d.pk] if decisiones.get(d.pk) == ACEPTAR else 0
        elif d.estado_detalle_venta == Estado.CONFIRMADO:
            cantidad = d.cant_entregada_venta or 0
        elif d.estado_detalle_venta == Estado.ABIERTO:
            cantidad = d.cant_solicitada_venta
        else:
            cantidad = 0
        total += Decimal(cantidad) * d.precio_unitario_de_venta
    return total.quantize(CENTAVOS)


def datos_de_decision(enlace=None, *, vendedor=None, venta_id=None, hoy=None):
    """Paso 2 de COM-DCD-FLT: lo que ve quien decide. Con `enlace` (el cliente), verifica que sirva (2a: `ValidationError` `enlace_no_sirve` con el motivo); con `vendedor` y `venta_id`
    (extensión 1a), que sea el Vendedor del contrato y que la venta sea decidible (`venta_no_decidible`). Nada de lotes, partidas, invernaderos de origen ni costos (garantía mínima 4);
    una consulta por tabla. Devuelve `DatosDeDecision`."""
    hoy = hoy or stock.hoy()
    if enlace is not None:
        situacion = enlaces.situacion_del_enlace(enlace, hoy)
        if situacion != enlaces.SIRVE:
            _error(NO_CAMPO, "enlace_no_sirve", enlaces.MOTIVOS[situacion], motivo=situacion)
        venta_id = enlace.compra_venta_id
    venta = CompraVenta.objects.select_related("cliente", "invernadero_retiro").get(pk=venta_id)
    if enlace is None:
        _exigir_vendedor(vendedor, venta)
        if not puede_decidir_el_vendedor(venta, hoy):
            _error(NO_CAMPO, "venta_no_decidible", "Esta compra no espera una decisión que puedas registrar: si el cliente tiene correo y su enlace sirve, la decide él.")
    detalles = list(venta.detalles.select_related("variedad").order_by("variedad_id", "pk"))
    pendientes_ids = [d.pk for d in detalles if d.estado_detalle_venta == Estado.PENDIENTE_DECISION]
    disponible = enlaces.disponible_de(pendientes_ids)
    pendientes = [
        FilaPendiente(
            d.pk, str(d.variedad), d.cant_solicitada_venta, disponible[d.pk], d.precio_unitario_de_venta,
            (Decimal(disponible[d.pk]) * d.precio_unitario_de_venta).quantize(CENTAVOS), disponible[d.pk] == 0,
        )
        for d in detalles
        if d.pk in pendientes_ids
    ]
    otros = [
        SimpleNamespace(
            variedad=str(d.variedad), estado=d.get_estado_detalle_venta_display(), solicitada=d.cant_solicitada_venta, entregada=d.cant_entregada_venta, precio=d.precio_unitario_de_venta
        )
        for d in detalles
        if d.pk not in pendientes_ids
    ]
    modalidad, destino = _destino(venta)
    vence = enlace.fecha_vencimiento if enlace is not None else None
    return DatosDeDecision(venta, enlace, vence, modalidad, destino, pendientes, otros, _monto(detalles, {}, disponible), _contacto(venta))


def estado_del_faltante(venta, actor, hoy=None):
    """Lo que la ficha de la compra-venta muestra de una venta «pendiente de decisión del cliente» (`faltante.md`, «Lo que completa a COM-02»; COM-CNS-CVT, regla 4): los detalles
    pendientes con desde cuándo esperan, hasta cuándo puede decidir el cliente (el vencimiento del enlace vigente), el estado del envío («El correo no se pudo enviar», «El cliente no
    tiene correo», «El enlace venció el …») y si `actor` ve el botón «Registrar decisión de faltante» (solo el Vendedor del contrato y solo si él puede decidir: 1a). `None` si la venta no espera."""
    hoy = hoy or stock.hoy()
    if venta.estado_venta != CompraVenta.Estado.PENDIENTE_DECISION:
        return None
    pendientes = _pendientes(venta)
    if not pendientes:
        return None
    vigente = venta.enlaces.filter(estado=EnlaceCliente.Estado.VIGENTE, tipo=EnlaceCliente.Tipo.DECISION_FALTANTE).first()
    vence, aviso = None, None
    if not venta.cliente.email_cliente:
        aviso = "El cliente no tiene correo: el Vendedor registra la decisión."
    elif vigente is None:
        aviso = "No hay un enlace vigente: el Vendedor registra la decisión."
    elif vigente.estado_envio == EnlaceCliente.EstadoEnvio.PENDIENTE_ENVIO:
        vence, aviso = vigente.fecha_vencimiento, "El correo no se pudo enviar."
    elif vigente.fecha_vencimiento < hoy:
        aviso = f"El enlace venció el {vigente.fecha_vencimiento:%d/%m/%Y} sin respuesta."
    else:
        vence = vigente.fecha_vencimiento
    puede = (
        rol_de(actor) == Usuario.Rol.VENDEDOR and getattr(actor, "is_active", False) and venta.vendedor_id == actor.pk and puede_decidir_el_vendedor(venta, hoy)
    )
    return SimpleNamespace(
        pendientes=[SimpleNamespace(variedad=str(d.variedad), desde=d.fecha_pendiente_decision) for d in pendientes], vence=vence, aviso=aviso, puede_decidir=bool(puede)
    )


def ventas_para_decidir(vendedor, hoy=None):
    """Extensión 1a, pasos 1 y 2: las ventas de los contratos del Vendedor «pendientes de decisión del cliente» cuyo cliente no tiene correo, cuyo enlace no se pudo enviar o cuyo enlace
    venció. Para cada una: el cliente con sus datos de contacto, la fecha pactada, los detalles pendientes y desde qué fecha esperan. Vacía = 1a.2a."""
    hoy = hoy or stock.hoy()
    _exigir_vendedor(vendedor)
    ventas = CompraVenta.objects.filter(vendedor=vendedor, estado_venta=CompraVenta.Estado.PENDIENTE_DECISION).select_related("cliente").order_by("fecha_pactada_venta", "pk")
    filas = []
    for venta in ventas:
        if not puede_decidir_el_vendedor(venta, hoy):
            continue
        pendientes = _pendientes(venta)
        filas.append(SimpleNamespace(venta=venta, cliente=venta.cliente, pendientes=pendientes, desde=min(d.fecha_pendiente_decision for d in pendientes if d.fecha_pendiente_decision)))
    return filas


# ---- COM-DCD-FLT: validar y resumir ----


def _validar_decisiones(pendientes, decisiones, disponible=None):
    """Pasos 3 y 4, extensiones 2b y 4a: una decisión por detalle pendiente (`faltan_decisiones`), cada una «aceptar» o «rechazar» (`decision_invalida`) y, con disponible 0, solo
    «rechazar» (`solo_rechazar`; solo si se pasa `disponible`: al registrar, la forma se verifica antes de la relectura de 6b y esto, después). Errores por campo `decision_<id>`;
    junta todos antes de levantar."""
    errores = {}
    for d in pendientes:
        clave = f"decision_{d.pk}"
        valor = decisiones.get(d.pk)
        if valor is None or valor == "":
            errores[clave] = [ValidationError(f"Indicá qué hacés con {d.variedad}.", code="faltan_decisiones")]
        elif valor not in (ACEPTAR, RECHAZAR):
            errores[clave] = [ValidationError("Elegí una de las dos opciones.", code="decision_invalida")]
        elif valor == ACEPTAR and disponible is not None and disponible[d.pk] == 0:
            errores[clave] = [ValidationError(f"No hay producto disponible de {d.variedad}: solo podés no recibirlo.", code="solo_rechazar")]
    if errores:
        raise ValidationError(errores)


def resumen_de_decision(datos, decisiones):
    """Paso 4: el resumen de la decisión (cantidad que recibirá, subtotal de cada detalle, monto total nuevo y si la compra quedaría cancelada). Valida con `_validar_decisiones`
    (4a y 2b). No escribe nada."""
    venta = datos.venta
    pendientes = [SimpleNamespace(pk=f.detalle_id, variedad=f.variedad) for f in datos.pendientes]
    disponible = {f.detalle_id: f.disponible for f in datos.pendientes}
    _validar_decisiones(pendientes, decisiones, disponible)
    detalles = list(venta.detalles.select_related("variedad").order_by("variedad_id", "pk"))
    filas = []
    for f in datos.pendientes:
        acepta = decisiones[f.detalle_id] == ACEPTAR
        filas.append({"detalle_id": f.detalle_id, "variedad": f.variedad, "acepta": acepta, "cantidad": f.disponible if acepta else 0, "subtotal": f.subtotal_disponible if acepta else Decimal("0.00")})
    decididos = {f.detalle_id: decisiones[f.detalle_id] for f in datos.pendientes}
    quedan = [d for d in detalles if (decididos.get(d.pk) != RECHAZAR if d.pk in decididos else d.estado_detalle_venta not in (Estado.RECHAZADO, Estado.CANCELADO))]
    return ResumenDeDecision(filas, _monto(detalles, decididos, disponible), not quedan)


# ---- COM-DCD-FLT: registrar ----


class _AlcanceCambio(Exception):
    """Al bloquear apareció algo (reservas, cosechas, partidas) que la lectura previa no vio: hay que volver a leer (una vez)."""


def _alcance(venta):
    """Lo que la decisión puede tocar, leído sin bloquear: los detalles pendientes, sus reservas no liberadas con sus líneas y cosechas, y de ahí las cuentas, invernaderos, variedades,
    lotes y partidas que hay que bloquear antes (patrón de bloqueos)."""
    pendientes = _pendientes(venta)
    reservas = list(ReservaStock.objects.filter(detalle_venta__in=pendientes).exclude(estado_reserva=ReservaStock.Estado.LIBERADA).order_by("pk"))
    lineas = list(DetalleReserva.objects.filter(reserva__in=reservas).order_by("pk"))
    cosechas = list(Cosecha.objects.filter(pk__in=[r.cosecha_id for r in reservas if r.cosecha_id]).select_related("invernadero").order_by("pk"))
    cuentas = {venta.vendedor_id} | {c.capataz_id for c in cosechas} | {c.invernadero.agronomo_id for c in cosechas}
    return SimpleNamespace(
        detalles={d.pk for d in pendientes},
        reservas={r.pk for r in reservas},
        cosechas={c.pk for c in cosechas},
        cuentas={c for c in cuentas if c},
        invernaderos={r.invernadero_id for r in reservas},
        variedades={d.variedad_id for d in pendientes},
        lotes={l.lote_id for l in lineas if l.lote_id},
        partidas={l.partida_id for l in lineas if l.partida_id},
    )


def _contenido_en(ahora, previo):
    """Verdadero si todo lo que hay ahora ya estaba en la lectura previa (y, por lo tanto, bloqueado)."""
    return all(getattr(ahora, c) <= getattr(previo, c) for c in ("reservas", "cosechas", "cuentas", "invernaderos", "variedades", "lotes", "partidas"))


def _bloquear(venta, previo, enlace_id, vendedor):
    """El orden de bloqueo de COM-DCD-FLT (ver el encabezado). Dentro de `transaction.atomic()`."""
    from comercial.servicios import cosechas as cosechas_comercial

    cosechas_comercial._bloquear_cuentas({*previo.cuentas, vendedor.pk if vendedor else None})
    if vendedor is not None and not Usuario.objects.filter(pk=vendedor.pk, is_active=True).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)  # quedó inactiva mientras esperaba
    for pk in sorted(previo.invernaderos):
        bloquear_invernadero_para_alertas(pk)
    list(Variedad.objects.select_for_update(no_key=True).filter(pk__in=previo.variedades).order_by("pk"))
    sectores = sorted(set(OcupacionSector.objects.filter(lote_id__in=previo.lotes).values_list("sector_id", flat=True)))
    if sectores:
        from maestros.models import SectorProduccion

        list(SectorProduccion.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=sectores).order_by("pk"))
    stock_maduro.bloquear_candidatos(sorted(previo.variedades), sorted(previo.invernaderos))
    if previo.lotes:
        list(Lote.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.lotes).order_by("pk"))
    if previo.partidas:
        list(StockCosechado.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.partidas).order_by("pk"))
    list(CompraVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk=venta.pk))
    list(DetalleVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.detalles).order_by("pk"))
    if previo.cosechas:
        from produccion.models import OrdenTrabajo

        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.cosechas).order_by("pk"))
    list(ReservaStock.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.reservas).order_by("pk"))
    list(DetalleReserva.objects.select_for_update(no_key=True, of=("self",)).filter(reserva_id__in=previo.reservas).order_by("pk"))
    return enlaces.bloquear_enlace(enlace_id) if enlace_id else None


def liberar_reservas_de_detalle(detalle, venta, vendedor, hoy, *, motivo_de_la_cosecha=None, motivo_de_la_partida=StockCosechado.Motivo.RECHAZO_CANTIDAD_REDUCIDA):
    """Postcondiciones i, j y k para un detalle rechazado (y la cancelación de la venta, COM-CNL-CVT, COM-05b): sus reservas no liberadas pasan a «liberada»; cada cosecha «a realizar» se cancela
    (con el aviso al Capataz y al Agrónomo); por cada línea de lote ya cosechada con cubierto > 0, una partida de `motivo_de_la_partida` (por omisión `rechazo_cantidad_reducida`) con su
    movimiento. `motivo_de_la_cosecha` es el texto que reciben las cosechas canceladas (por omisión, «El cliente rechazó el faltante de CV-…»). Una sola lógica para los dos casos de uso: ninguna
    función nueva duplica la liberación (`cancelar_orden.md`). Devuelve `(partidas, cosechas_canceladas, reservas_liberadas, partidas_para_reasignar)`."""
    reservas = ReservaStock.objects.filter(detalle_venta=detalle).exclude(estado_reserva=ReservaStock.Estado.LIBERADA).select_related("cosecha").order_by("pk")
    return liberar_reservas(
        reservas, vendedor, hoy, origen=venta, motivo_de_la_cosecha=motivo_de_la_cosecha or f"El cliente rechazó el faltante de {venta.codigo}", motivo_de_la_partida=motivo_de_la_partida
    )


def liberar_reservas(reservas, actor, hoy, *, origen, motivo_de_la_cosecha, motivo_de_la_partida, avisar_agronomo=True):
    """La liberación de una lista de reservas (`ReservaStock` con su `cosecha` ya leída), sin importar si son de una compra-venta o de un suministro: la lógica de
    `liberar_reservas_de_detalle`, que la usa para un detalle de venta, y de COM-RSV-SUM (COM-07b, paso 4), que la usa para los detalles de un suministro. `origen` es el documento
    que origina las partidas (la venta o el suministro); `avisar_agronomo=False` deja sin aviso al Agrónomo en las cosechas canceladas (la resolución le manda uno solo por
    invernadero). Devuelve `(partidas, cosechas_canceladas, reservas_liberadas, partidas_para_reasignar)`. Corre en la transacción del llamador, con todo bloqueado."""
    from comercial.servicios import cosechas as cosechas_comercial
    from produccion.models import OrdenTrabajo
    from produccion.servicios import camara as fisico_camara
    from produccion.servicios import cosechas as fisico_cosechas

    partidas, canceladas, liberadas, reasignar = [], [], [], set()
    for reserva in reservas:
        cosecha = reserva.cosecha
        if cosecha is not None and cosecha.estado_orden == OrdenTrabajo.Estado.A_REALIZAR:
            cosechas_comercial.cancelar_cosecha_incluida(actor, cosecha, motivo_de_la_cosecha, recubrir=False, avisar_agronomo=avisar_agronomo)
            canceladas.append(cosecha)
            liberadas.append(reserva)
            continue
        lineas = list(DetalleReserva.objects.filter(reserva=reserva).select_related("lote__siembra__variedad").order_by("pk"))
        costos = fisico_cosechas.costo_unitario_de_cosecha([cosecha.pk] if cosecha else [], [l.lote_id for l in lineas if l.lote_id])
        for linea in lineas:
            if linea.partida_id:
                reasignar.add(linea.partida_id)  # la línea de cámara deja de apartar stock (postcondición l)
            elif linea.lote_id and linea.cantidad_cosechada is not None and cosecha is not None:
                cantidad = min(linea.cantidad_cosechada, linea.cantidad_reservada)
                costo = costos.get((cosecha.pk, linea.lote_id))
                if cantidad > 0 and costo is not None:
                    partidas.append(
                        fisico_camara.crear_partida(
                            linea.lote, cantidad, motivo_de_la_partida,
                            fecha_cosecha=cosecha.fecha_cosecha, fecha_ingreso=hoy, costo_unitario=costo, origen=origen,
                        )
                    )
        ReservaStock.objects.filter(pk=reserva.pk).update(estado_reserva=ReservaStock.Estado.LIBERADA)
        reserva.estado_reserva = ReservaStock.Estado.LIBERADA
        liberadas.append(reserva)
    return partidas, canceladas, liberadas, reasignar


def _texto_de_decision(f):
    """«Lechuga Crespa: aceptó 40 plantas» o «Lechuga Crespa: no la recibirá»."""
    return f"{f['variedad']}: " + (f"aceptó {f['cantidad']} plantas" if f["acepta"] else "no lo recibirá")


def _enviar_acuse(cliente_id, email, contexto):
    """Postcondición e: el acuse al cliente, DESPUÉS de confirmar (fuera de la transacción). Si falla o el correo del sistema no está configurado, la decisión sigue registrada (extensión 8a:
    no hay cola, se anota en el log)."""
    if not correo.correo_configurado():
        logger.warning("No se envió el acuse de %s: el correo del sistema no está configurado.", contexto["codigo"])
        return
    if not correo.enviar_correo(Destinatario(cliente_id, email), f"Tu decisión sobre la compra {contexto['codigo']}", "comercial/correos/acuse_faltante.txt", contexto):
        logger.warning("No se pudo enviar el acuse de %s al cliente %s.", contexto["codigo"], cliente_id)


def _registrar(venta_id, enlace_id, decisiones, vistos, vendedor, previo, hoy):
    """Un intento de registrar (todo en una transacción). Si al bloquear aparece algo que la lectura previa no vio, `_AlcanceCambio`."""
    with transaction.atomic():
        venta = CompraVenta.objects.select_related("cliente").get(pk=venta_id)
        enlace = _bloquear(venta, previo, enlace_id, vendedor)
        venta = CompraVenta.objects.select_related("cliente").get(pk=venta_id)
        # Relectura con todo bloqueado: 6a (el enlace dejó de servir o un detalle ya no está pendiente) y 6b (cambió la cantidad disponible).
        if enlace is not None:
            situacion = enlaces.situacion_del_enlace(enlace, hoy)
            if situacion != enlaces.SIRVE:
                _error(NO_CAMPO, "enlace_no_sirve", enlaces.MOTIVOS[situacion], motivo=situacion)
        else:
            _exigir_vendedor(vendedor, venta)
            if not puede_decidir_el_vendedor(venta, hoy):
                _error(NO_CAMPO, "venta_no_decidible", "Esta compra ya no espera una decisión que puedas registrar.")
        pendientes = _pendientes(venta)
        ids = {d.pk for d in pendientes}
        fuera = sorted(i for i in decisiones if i not in ids)
        if fuera:
            _error(NO_CAMPO, "detalle_ya_no_pendiente", "Algún producto ya no espera tu decisión: revisá la compra.", detalles=fuera)
        if not _contenido_en(_alcance(venta), previo):
            raise _AlcanceCambio()
        _validar_decisiones(pendientes, decisiones)  # 4a: la forma, antes de comparar con lo que vio la pantalla
        disponible = enlaces.disponible_de(ids)
        if vistos is not None:
            cambiaron = {i: disponible[i] for i in sorted(ids) if vistos.get(i) != disponible[i]}
            if cambiaron:
                _error(NO_CAMPO, "disponible_cambio", "La cantidad disponible cambió: revisá lo que ves y volvé a decidir.", disponibles=cambiaron)
        _validar_decisiones(pendientes, decisiones, disponible)

        filas, confirmados, rechazados = [], [], []
        partidas, canceladas, liberadas, reasignar = [], [], [], set()
        for d in pendientes:
            if decisiones[d.pk] == ACEPTAR:  # g y h
                DetalleVenta.objects.filter(pk=d.pk).update(estado_detalle_venta=Estado.CONFIRMADO, cant_entregada_venta=disponible[d.pk])
                confirmados.append(d)
                filas.append({"variedad": str(d.variedad), "acepta": True, "cantidad": disponible[d.pk], "subtotal": (Decimal(disponible[d.pk]) * d.precio_unitario_de_venta).quantize(CENTAVOS)})
            else:  # i, j y k
                DetalleVenta.objects.filter(pk=d.pk).update(estado_detalle_venta=Estado.RECHAZADO)
                rechazados.append(d)
                p, c, r, a = liberar_reservas_de_detalle(d, venta, vendedor, hoy)
                partidas += p
                canceladas += c
                liberadas += r
                reasignar |= a
                filas.append({"variedad": str(d.variedad), "acepta": False, "cantidad": 0, "subtotal": Decimal("0.00")})
        # c: la venta vuelve a «abierta» o, si todos sus detalles quedaron rechazados, pasa a «cancelada» (sin los datos de MD-130, que son de COM-CNL-CVT).
        quedan = venta.detalles.exclude(estado_detalle_venta__in=(Estado.RECHAZADO, Estado.CANCELADO)).exists()
        antes = venta.estado_venta
        despues = CompraVenta.Estado.ABIERTA if quedan else CompraVenta.Estado.CANCELADA
        CompraVenta.objects.filter(pk=venta.pk).update(estado_venta=despues)
        venta.estado_venta = despues
        total = _monto(list(venta.detalles.all()), {}, {})
        # b: el enlace queda usado (con el Vendedor no se marca: 1a); los vigentes que queden (vencido por fecha o sin envío) se anulan.
        if enlace is not None:
            EnlaceCliente.objects.filter(pk=enlace.pk).update(estado=EnlaceCliente.Estado.USADO, fecha_uso=timezone.now())
            enlace.estado = EnlaceCliente.Estado.USADO
        anulados = enlaces.anular_enlaces_de(venta)
        # d: la notificación al Vendedor (salvo en 1a, que decidió él).
        if vendedor is None:
            avisado = _vendedor_activo(venta)
            if avisado is not None:
                notificaciones.notificar(
                    avisado,
                    f"El cliente decidió el faltante de {venta.codigo}",
                    "; ".join(_texto_de_decision(f) for f in filas)[:480] + ".",
                )
        movimientos = list(MovimientoStock.objects.filter(partida__in=partidas, tipo_movimiento=MovimientoStock.TipoMovimiento.INGRESO_A_CAMARA).order_by("pk")) if partidas else []
        # f: UN registro de auditoría con origen «cliente mediante enlace» o, en 1a, el Vendedor.
        reservas = ReservaStock.objects.filter(pk__in=[r.pk for r in liberadas]).order_by("pk")
        afectados = [venta, venta.cliente, *confirmados, *rechazados, *reservas, *canceladas, *partidas, *movimientos, *anulados]
        if enlace is not None:
            afectados.append(enlace)
        datos = {"decisiones": [_texto_de_decision(f) for f in filas]}
        if partidas:
            datos["partidas_creadas"] = [str(p) for p in partidas]
            datos["movimientos_creados"] = [str(m) for m in movimientos]
        if canceladas:
            datos["cosechas_canceladas"] = [str(c) for c in canceladas]
        if enlace is not None:
            datos["enlace"] = str(enlace)
        if anulados:
            datos["enlaces_anulados"] = [str(e) for e in anulados]
        detalle = {"datos": datos}
        if antes != despues:
            detalle["cambios"] = {"estado_venta": {"antes": antes, "despues": despues}}
        RegistroAuditoria.objects.registrar(
            usuario=vendedor, accion=RegistroAuditoria.Accion.DECISION_FALTANTE, afectados=afectados, detalle=detalle,
            **({"rol_externo": "cliente_enlace"} if vendedor is None else {}),
        )
        # l y e, después de confirmar: la asignación de cámara con lo que ingresó o se liberó, y el acuse al cliente (si tiene correo).
        from comercial.servicios import camara as camara_comercial

        camara_comercial.programar_asignacion_de_camara([p.pk for p in partidas] + sorted(reasignar))
        if despues == CompraVenta.Estado.ABIERTA:  # paso 7 y postcondición m (D-66 punto 5): la venta que queda «abierta» y lista se planifica después de confirmar
            entregas.programar_planificacion_de_venta(venta.pk)
        if venta.cliente.email_cliente:
            contexto = {
                "codigo": venta.codigo, "cliente": venta.cliente.nombre_visible, "filas": filas, "cancelada": not quedan, "total": total, "fecha_pactada": venta.fecha_pactada_venta,
            }
            transaction.on_commit(partial(_enviar_acuse, venta.cliente.pk, venta.cliente.email_cliente, contexto))
        return ResultadoDecision(venta, confirmados, rechazados, partidas, movimientos, canceladas, enlace)


def registrar_decision(enlace_id, decisiones, disponibles_vistos, *, vendedor=None, venta_id=None):
    """COM-DCD-FLT, paso 6: registra la decisión del cliente (por su `enlace_id`) o, en la extensión 1a, la del `vendedor` sobre `venta_id` (con `enlace_id=None`). Devuelve `ResultadoDecision`.

    - `decisiones` es `{detalle_id: "aceptar" | "rechazar"}`, una por cada detalle pendiente; `disponibles_vistos`, `{detalle_id: cantidad}` que mostró la pantalla (6b; `None` no controla).
    - Errores (`ValidationError`, `error_dict`): `faltan_decisiones`, `decision_invalida` y `solo_rechazar` por campo `decision_<id>`; `enlace_no_sirve` (2a y 6a, con `params["motivo"]`),
      `detalle_ya_no_pendiente` (6a), `disponible_cambio` (6b, con las cantidades nuevas), `venta_no_decidible` y `cambio_simultaneo` en `__all__`. `PermissionDenied`: quien decide en 1a no es el Vendedor activo del
      contrato (tampoco el Gerente).
    - Todo en UNA transacción, con los bloqueos del encabezado, y todo se vuelve a verificar DESPUÉS de bloquear. El acuse y la asignación de cámara salen con `on_commit`."""
    if (enlace_id is None) == (vendedor is None) or (vendedor is not None and venta_id is None):
        raise ValueError("Con enlace decide el cliente; con `vendedor` hace falta `venta_id` y no hay enlace (extensión 1a).")
    if enlace_id is not None:
        enlace = EnlaceCliente.objects.filter(pk=enlace_id).first()
        if enlace is None:
            _error(NO_CAMPO, "enlace_no_sirve", enlaces.MOTIVOS[enlaces.NO_VALIDO], motivo=enlaces.NO_VALIDO)
        venta_id = enlace.compra_venta_id
    venta = CompraVenta.objects.select_related("cliente").get(pk=venta_id)
    if vendedor is not None:
        _exigir_vendedor(vendedor, venta)
    hoy = stock.hoy()
    for _ in range(2):
        try:
            return _registrar(venta_id, enlace_id, decisiones, disponibles_vistos, vendedor, _alcance(venta), hoy)
        except _AlcanceCambio:
            continue
    _error(NO_CAMPO, "cambio_simultaneo", "La compra cambió mientras se registraba la decisión. Volvé a abrirla.")
