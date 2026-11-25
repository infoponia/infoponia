# Servicio de CMP-AUT-PED · Generar Pedidos Automáticos por Stock Bajo (CMP-07; paso 63 del proceso diario). Fuente: docs/casos_de_uso/compras/pedido_automatico.md y D-104.
# Un pedido por invernadero con los insumos bajo el mínimo que no estén ya pedidos, a nombre del Agrónomo a cargo, invitando a los proveedores especializados; se audita como
# InfoPonia (D-22 y D-27) y el alta es la misma de CMP-RLZ-PED (``pedidos._crear_pedido``), así que el pedido automático es un pedido común.
#
# Contrato del paso (D-56 punto 4): ``generar_pedidos_automaticos(hoy) -> ResumenDePaso``; idempotente (los insumos ya pedidos se saltean y los avisos 3a y 5a no se
# repiten el mismo día), nunca lee la fecha por su cuenta y trabaja por invernadero, cada uno en su transacción. Un invernadero que falla se registra con
# ``logger.exception`` y no frena a los demás; al terminar el paso lanza ``RuntimeError`` (D-56 punto 5), como los pasos 60 a 62.
#
# Bloqueos (docs/patrones/bloqueos.md, «compras», el mismo orden que ``registrar_pedido``; siempre ``FOR NO KEY UPDATE``): la cuenta del Agrónomo → el invernadero → los
# ``InsumoInvernadero`` en orden de id → los proveedores en orden de id. Antes de bloquear se lee sin bloquear para saber qué tomar; con todo bloqueado se relee y se repite la
# validación (extensión 5b): si ya no corresponde no se crea nada. Los correos salen en ``on_commit``. ``compras`` no importa de ``comercial`` ni de ``produccion`` (A1 de D-37).

import logging
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import Proveedor
from compras.servicios import pedidos as servicio_de_pedidos
from core import notificaciones
from core.models import Notificacion, Usuario
from core.procesos import ResumenDePaso
from inventario.models import Insumo, InsumoInvernadero
from inventario.servicios import stock
from inventario.unidades import decimales_de
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import bloquear_invernadero_activo

logger = logging.getLogger("infoponia.proceso_diario")

CODIGO = "generar_pedidos_automaticos"
NOMBRE = "Pedidos automáticos por stock bajo"
ORDEN = 63  # D-104 punto 1: después de los pasos 60 a 62 de CMP-03, para no crear un pedido que otro paso va a cancelar el mismo día

# Qué pasó con un invernadero.
CREADO, SIN_PROVEEDORES, SIN_AGRONOMO, NADA = "creado", "sin_proveedores", "sin_agronomo", "nada"


def calcular_cantidad(minimo, libre, transito, margen, unidad):
    """D-104 punto 3: ``mínimo × (1 + margen/100) − (libre + tránsito)``, redondeada hacia arriba a los decimales que admite ``unidad``. Con margen 0 coincide con la
    cantidad sugerida de la pantalla manual. ``libre`` puede ser negativo (reservado mayor que lo vigente): entonces suma."""
    bruta = minimo * (Decimal(100) + Decimal(margen)) / Decimal(100) - (libre + transito)
    return bruta.quantize(Decimal(1).scaleb(-decimales_de(unidad)), rounding=ROUND_CEILING)


def _construir_url(ruta):
    """La URL absoluta del enlace del correo: ``URL_DEL_SITIO`` + la ruta. Sin ``URL_DEL_SITIO`` queda relativa y ``enviar_invitacion`` no la manda (8a)."""
    return settings.URL_DEL_SITIO + ruta


def _candidatos(invernadero_id, hoy):
    """Precondición b y pasos 1 y 2: los ``(InsumoInvernadero, Existencia)`` del invernadero que están habilitados y activos (insumo activo), bajo el mínimo (``bajo_minimo``,
    la condición de la pantalla manual) y que no figuran en otro pedido «en cotización» ni en una orden pendiente de aprobación (``ya_pedido``), en orden de id."""
    iins = list(
        InsumoInvernadero.objects.filter(
            invernadero_id=invernadero_id, estado_insumo_invernadero="activo", insumo__estado_insumo=Insumo.Estado.ACTIVO
        )
        .select_related("insumo", "insumo__tipo_insumo", "invernadero")
        .order_by("id")
    )
    if not iins:
        return []
    ids = [i.pk for i in iins]
    existencias = stock.existencias(ids, hoy)
    ya = servicio_de_pedidos.ya_pedido(ids)
    return [(i, existencias[i.pk]) for i in iins if existencias[i.pk].bajo_minimo and i.pk not in ya]


def _proveedores_con_correo(proveedores):
    """Los proveedores que tienen correo (D-104 punto 5; el correo es obligatorio, pero la base no lo garantiza)."""
    return [p for p in proveedores if p.email_proveedor]


def _gerente():
    return Usuario.objects.filter(rol=Usuario.Rol.GERENTE, is_active=True).first()


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _avisar_una_vez(cuentas, titulo, detalle):
    """Extensiones 3a y 5a: avisa a cada cuenta, salvo a la que ya tiene una notificación con ese título (que lleva la fecha de ``hoy``): una vez por día y por invernadero.
    Sin columna propia (respuesta del estudiante, 25/11/2026). Sin cuentas no hace nada (D-14)."""
    nuevas = [c for c in cuentas if c is not None and not Notificacion.objects.filter(destinatario=c, titulo=titulo).exists()]
    if nuevas:
        notificaciones.notificar_a_varios(nuevas, titulo, detalle)


def _avisar_sin_agronomo(invernadero, cantidad, hoy):
    """Extensión 5a: al Gerente (texto aprobado el 25/11/2026)."""
    _avisar_una_vez(
        [_gerente()],
        f"Pedido automático sin Agrónomo en {invernadero.nombre_invernadero[:60]} ({hoy:%d/%m/%Y})",
        f"Hay {_plural(cantidad, 'insumo', 'insumos')} bajo el mínimo en {invernadero.nombre_invernadero}, pero no tiene un Agrónomo activo a cargo: no se creó el pedido. "
        "Asignale uno para que el paso lo arme.",
    )


def _avisar_sin_proveedores(invernadero, agronomo, cantidad, hoy):
    """Extensión 3a: al Agrónomo del invernadero y al Gerente (texto aprobado el 25/11/2026)."""
    _avisar_una_vez(
        [agronomo, _gerente()],
        f"Sin proveedores para el pedido automático de {invernadero.nombre_invernadero[:60]} ({hoy:%d/%m/%Y})",
        f"Hay {_plural(cantidad, 'insumo', 'insumos')} bajo el mínimo en {invernadero.nombre_invernadero}, pero ningún proveedor activo se especializa en sus categorías. "
        "Pedile al Gerente que revise los proveedores o armá el pedido a mano.",
    )


def _tratar_invernadero(invernadero_id, hoy):
    """Un invernadero (una transacción para lo que escribe). Devuelve ``(resultado, cantidad_de_insumos)`` con ``resultado`` uno de ``CREADO``, ``SIN_PROVEEDORES``,
    ``SIN_AGRONOMO`` o ``NADA`` (nada que pedir, o ya no corresponde tras releer con todo bloqueado: extensiones 1a y 5b)."""
    invernadero = Invernadero.objects.select_related("agronomo").filter(pk=invernadero_id).first()  # sin bloquear: para saber qué tomar
    if invernadero is None or not invernadero.activo:
        return NADA, 0
    candidatos = _candidatos(invernadero_id, hoy)
    if not candidatos:  # extensión 1a
        return NADA, 0
    agronomo = invernadero.agronomo
    if agronomo is None or not agronomo.is_active:  # extensión 5a (se evalúa antes que 3a: sin Agrónomo no hay a quién avisar del resto)
        with transaction.atomic():
            _avisar_sin_agronomo(invernadero, len(candidatos), hoy)
        return SIN_AGRONOMO, len(candidatos)
    categorias = {i.insumo.tipo_insumo_id for i, _ in candidatos}
    if not _proveedores_con_correo(servicio_de_pedidos.proveedores_invitables(categorias)):  # extensión 3a
        with transaction.atomic():
            _avisar_sin_proveedores(invernadero, agronomo, len(candidatos), hoy)
        return SIN_PROVEEDORES, len(candidatos)
    proveedor_ids = sorted(p.pk for p in servicio_de_pedidos.proveedores_invitables(categorias))

    with transaction.atomic():
        # Orden de bloqueos de ``registrar_pedido``: cuenta del Agrónomo → invernadero → insumos → proveedores.
        dueno = Usuario.objects.select_for_update(no_key=True).filter(pk=agronomo.pk).first()
        if dueno is None or not dueno.is_active:
            return NADA, 0
        try:
            invernadero = bloquear_invernadero_activo(invernadero_id)
        except ValidationError:  # el invernadero se dio de baja entre la lectura y el bloqueo (5b)
            return NADA, 0
        if invernadero.agronomo_id != agronomo.pk:  # cambió de Agrónomo: lo trata la próxima corrida con el nuevo (5b)
            return NADA, 0
        leidos = {i.pk for i, _ in candidatos}
        list(InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=leidos).order_by("id").values_list("pk", flat=True))
        candidatos = [par for par in _candidatos(invernadero_id, hoy) if par[0].pk in leidos]  # releído y revalidado con todo bloqueado (5b)
        proveedores = {
            p.pk: p
            for p in Proveedor.objects.select_for_update(no_key=True).filter(pk__in=proveedor_ids).order_by("id")
            if p.activo and p.email_proveedor
        }
        if not candidatos or not proveedores:
            return NADA, 0

        configuracion_operativa = configuracion.obtener()
        margen = configuracion_operativa.porc_margen_pedido_automatico
        fecha = hoy + timedelta(days=configuracion_operativa.dias_limite_cotizacion)
        datos = {
            "detalles": [
                (i.pk, str(calcular_cantidad(e.minimo, e.libre, e.transito, margen, i.insumo.unidad_medida_insumo))) for i, e in candidatos
            ],
            "proveedores": list(proveedores),
            "fecha_limite": fecha,
        }
        iins = {i.pk: i for i, _ in candidatos}
        lineas, invitados, fecha = servicio_de_pedidos._validar(dueno, datos, iins, proveedores, hoy)
        pedido = servicio_de_pedidos._crear_pedido(
            agronomo.pk,
            lineas,
            invitados,
            fecha,
            hoy,
            _construir_url,
            usuario_de_auditoria=None,  # InfoPonia: usuario nulo y rol ``infoponia`` (D-104 punto 4)
            datos_extra={"origen": "automático", "porc_margen_pedido_automatico": margen},
        )
        notificaciones.notificar(
            dueno,
            f"Pedido {pedido} creado automáticamente",
            f"{_plural(len(lineas), 'insumo bajo el mínimo', 'insumos bajo el mínimo')} en {invernadero.nombre_invernadero}. "
            f"Se invitó a {_plural(len(invitados), 'proveedor', 'proveedores')}; la fecha límite de cotizaciones es {fecha:%d/%m/%Y}.",
        )
        return CREADO, len(lineas)


def generar_pedidos_automaticos(hoy):
    """Paso 63 (CMP-AUT-PED, D-104): por cada invernadero activo, en orden de id, arma el pedido de cotización de sus insumos bajo el mínimo y lo envía a los proveedores.
    ``ResumenDePaso(procesados=invernaderos revisados, creados=pedidos creados, resueltos=0, detalle)``. Idempotente. Si un invernadero falla se registra y los demás
    siguen; al terminar lanza ``RuntimeError`` (D-56 punto 5)."""
    ids = list(Invernadero.objects.filter(estado_invernadero="activo").order_by("id").values_list("pk", flat=True))
    procesados = creados = sin_proveedores = sin_agronomo = 0
    fallidos = []
    for invernadero_id in ids:
        try:
            resultado, _ = _tratar_invernadero(invernadero_id, hoy)
        except Exception:  # noqa: BLE001 - un invernadero roto no puede dejar a los demás sin tratar (D-56 punto 5)
            logger.exception("Falló el paso diario «%s» con el invernadero %s", CODIGO, invernadero_id)
            fallidos.append(invernadero_id)
            continue
        procesados += 1
        creados += resultado == CREADO
        sin_proveedores += resultado == SIN_PROVEEDORES
        sin_agronomo += resultado == SIN_AGRONOMO
    if fallidos:
        raise RuntimeError(
            f"El paso «{CODIGO}» falló con {len(fallidos)} invernadero(s) (ids {', '.join(map(str, fallidos))}); los demás se trataron "
            f"({procesados} procesados, {creados} pedidos creados). Se reintentan en la próxima corrida."
        )
    partes = []
    if sin_proveedores:
        partes.append(f"{sin_proveedores} sin proveedores")
    if sin_agronomo:
        partes.append(f"{sin_agronomo} sin Agrónomo")
    return ResumenDePaso(procesados, creados, 0, " · ".join(partes))
