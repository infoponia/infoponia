# Resolución de un suministro por incumplimientos (COM-RSV-SUM, COM-07b; docs/casos_de_uso/comercial/resolucion.md; D-69 puntos 1, 5, 7, 13, 14 y 15). El actor es InfoPonia (D-27): cuando una
# aceptación (COM-EVL-DSC o COM-RSV-QJA, extensión 6b) deja a un suministro «vigente» con más incumplimientos que los tolerados, el contrato se resuelve sin intervención de nadie. COM-07a dejó
# el punto de entrada (`resolver_si_corresponde`, que las aceptaciones llaman con `transaction.on_commit`); esta tarea lo completa y suma la recuperación diaria (paso 33).
#
# CON-04d (D-92 punto 10): el asiento de la multa (postcondición h, paso 6.4) lo hace `asientos_comerciales.asentar_multa_de_resolucion`; la precondición c y la extensión 5b desaparecen (D-92 punto 2).
#
# Un intento = UNA transacción (la garantía mínima de atomicidad del caso de uso), con el orden de bloqueo de «Resolver un suministro» (docs/patrones/bloqueos.md; el de «Cancelar una
# compra-venta» con el suministro en lugar de la venta; `FOR NO KEY UPDATE`): las cuentas → los invernaderos (`bloquear_invernadero_para_alertas`: activo o no, D-64 punto 12) → el cliente →
# las variedades → los sectores → los lotes y las partidas → el suministro → sus detalles → las cosechas → las reservas y sus líneas → las entregas (y, por `cancelar_orden_incluida`, sus
# insumos y reservas de insumo). Sin enlaces: los de confirmación de las entregas concretadas no cambian. Lo que la lectura previa no vio y aparece al bloquear obliga a repetir UNA vez (6a).
# Las notificaciones van dentro de la transacción (D-42); PROD-ASG-CAM y el aviso de resolución al cliente (correo), después de confirmar (D-14, D-54, D-65).

import logging
from collections import namedtuple
from functools import partial
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, OuterRef, Subquery
from django.http import Http404
from django.urls import reverse

from comercial.models import AlertaComercial, Cliente, Contrato, DetalleReserva, DetalleSuministro, Entrega, ReservaStock, SolicitudRevision, Suministro
from comercial.servicios import asientos_comerciales, comprobantes, entregas, faltantes, stock_maduro
from comercial.servicios.compra_ventas import texto_de_pesos
from contabilidad.servicios import ejercicios
from core import notificaciones
from core.procesos import ResumenDePaso
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import InsumoInvernadero
from inventario.servicios import stock
from maestros.extensiones import Enlace
from maestros.models import Alerta, Invernadero, SectorProduccion, Variedad
from maestros.servicios import alertas
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from produccion.models import Lote, MovimientoStock, OcupacionSector, OrdenTrabajo, StockCosechado

logger = logging.getLogger("infoponia.resoluciones")

TIPO_DE_ALERTA = "comercial_suministro_resuelto"  # D-69 punto 14
TIPO_PERIODO_SIN_COBERTURA = "comercial_periodo_sin_cobertura"  # COM-03b: se resuelve con el contrato (paso 4.6)
MOTIVO_GENERAL = "Resolución del suministro por incumplimientos"  # el texto del caso de uso; cada orden lleva el suyo con el código del contrato (`_motivo`)
LARGO_DE_LA_ALERTA = Alerta._meta.get_field("descripcion_alerta").max_length
A_REALIZAR = OrdenTrabajo.Estado.A_REALIZAR
VIGENTE = Suministro.Estado.VIGENTE

# Lo que devuelve `resolver_suministro` (el extracto: «ResultadoDeResolucion»): el suministro ya resuelto, los detalles resueltos, las cosechas y las entregas canceladas, las reservas
# liberadas, las partidas creadas, las alertas resueltas y la alerta creada (`None` si no hubo invernadero activo, D-63 punto 4).
ResultadoDeResolucion = namedtuple("ResultadoDeResolucion", "suministro detalles cosechas entregas reservas partidas alertas_resueltas alerta")
# Lo que la lectura previa (y la relectura bajo bloqueo) saca del contrato: de ahí salen las filas a bloquear.
_Alcance = namedtuple(
    "_Alcance",
    "suministro detalles reservas lineas cosechas entregas alertas_de_periodo cuentas invernaderos variedades lotes partidas invernadero_de_la_alerta alternativo",
)


class _AlcanceCambio(Exception):
    """Al bloquear apareció algo (una reserva, una cosecha o una entrega de otro invernadero, creada entre la lectura y el bloqueo) que la lectura previa no vio: hay que volver a leer (6a)."""


def _motivo(suministro):
    """El motivo que reciben las órdenes canceladas: «Resolución del suministro SUM-0013 por incumplimientos.» (de 1 a 300)."""
    return f"Resolución del suministro {suministro.codigo} por incumplimientos."


def _supera(suministro):
    """La condición de la resolución (paso 2 y extensión 2b): la cantidad de incumplimientos supera la tolerada."""
    return suministro.cantidad_incumplimientos > suministro.incumplimientos_tolerados


def _solicitud_que_provoco(suministro_id):
    """D-69 punto 5: la solicitud aceptada del contrato con la `fecha_resolucion` más reciente (a igual fecha, la de mayor id): la que llevó el contador por encima de lo tolerado."""
    return (
        SolicitudRevision.objects.filter(entrega__contrato_entrega_id=suministro_id, estado_solicitud=SolicitudRevision.Estado.ACEPTADA)
        .select_related("entrega")
        .order_by("-fecha_resolucion", "-pk")
        .first()
    )


# ---- la lectura (pasos 2 y 3) ----


def _alcance(suministro_id):
    """Pasos 2 y 3, sin bloquear: el suministro; los detalles «vigentes»; sus reservas no liberadas ni entregadas con sus líneas; las cosechas «a realizar» de esas reservas; las entregas «a
    realizar» del contrato (con o sin transportista, con o sin envío); las alertas «período sin cobertura» activas de sus detalles; y de ahí las filas a bloquear (cuentas, invernaderos,
    variedades, lotes y partidas). `None` si el suministro no existe."""
    suministro = Suministro.objects.select_related("cliente", "vendedor").filter(pk=suministro_id).first()
    if suministro is None:
        return None
    detalles = list(DetalleSuministro.objects.filter(suministro=suministro, estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE).select_related("variedad").order_by("pk"))
    reservas = list(
        ReservaStock.objects.filter(detalle_suministro__in=detalles)
        .exclude(estado_reserva__in=[ReservaStock.Estado.LIBERADA, ReservaStock.Estado.ENTREGADA])
        .select_related("cosecha__invernadero", "invernadero__agronomo")
        .order_by("pk")
    )
    lineas = list(DetalleReserva.objects.filter(reserva__in=reservas).select_related("lote__siembra", "partida__lote__siembra").order_by("pk"))
    cosechas_ = [r.cosecha for r in reservas if r.cosecha_id and r.cosecha.estado_orden == A_REALIZAR]
    entregas_ = list(
        Entrega.objects.filter(contrato_entrega_id=suministro.pk, estado_orden=A_REALIZAR).select_related("invernadero__agronomo", "transportista").order_by("pk")
    )
    de_periodo = list(
        AlertaComercial.objects.filter(detalle_suministro__in=detalles, alerta__estado_alerta="activa", alerta__tipo_alerta=TIPO_PERIODO_SIN_COBERTURA).select_related("alerta").order_by("pk")
    )
    # D-63 punto 2: el invernadero de la alerta es el de la primera reserva del primer detalle (de menor id) que tenga alguna; si ninguno tiene, el activo de menor id del Vendedor.
    primera = ReservaStock.objects.filter(detalle_suministro__suministro=suministro).order_by("detalle_suministro_id", "pk").values_list("invernadero_id", flat=True).first()
    del_vendedor = Invernadero.objects.filter(vendedor_id=suministro.vendedor_id, estado_invernadero=Invernadero.Estado.ACTIVO).order_by("pk").values_list("pk", flat=True).first()
    invernaderos = {r.invernadero_id for r in reservas} | {e.invernadero_id for e in entregas_} | {a.alerta.invernadero_id for a in de_periodo}
    invernaderos |= {i for i in (primera, del_vendedor) if i}
    cuentas = {suministro.vendedor_id}
    cuentas |= {c.capataz_id for c in cosechas_} | {e.transportista_id for e in entregas_}
    cuentas |= {i.agronomo_id for i in Invernadero.objects.filter(pk__in=invernaderos)}
    return _Alcance(
        suministro,
        detalles,
        reservas,
        lineas,
        cosechas_,
        entregas_,
        de_periodo,
        {c for c in cuentas if c},
        invernaderos,
        {d.variedad_id for d in detalles} | {c.variedad_id for c in cosechas_} | {l.lote.siembra.variedad_id for l in lineas if l.lote_id},
        {l.lote_id for l in lineas if l.lote_id},
        {l.partida_id for l in lineas if l.partida_id},
        primera,
        del_vendedor,
    )


def _contenido_en(ahora, previo):
    """Verdadero si todo lo que hay ahora ya estaba en la lectura previa (y, por lo tanto, bloqueado)."""
    return all(getattr(ahora, c) <= getattr(previo, c) for c in ("cuentas", "invernaderos", "variedades", "lotes", "partidas")) and all(
        {x.pk for x in getattr(ahora, c)} <= {x.pk for x in getattr(previo, c)} for c in ("reservas", "cosechas", "entregas", "alertas_de_periodo")
    )


def _bloquear(previo):
    """El orden de bloqueo del encabezado (dentro de `transaction.atomic()`)."""
    suministro = previo.suministro
    from comercial.servicios import cosechas  # adentro: `cosechas` y `camara` importan módulos que importan este

    cosechas._bloquear_cuentas(previo.cuentas)
    for pk in sorted(previo.invernaderos):
        bloquear_invernadero_para_alertas(pk)
    list(Cliente.objects.select_for_update(no_key=True).filter(pk=suministro.cliente_id))
    list(Variedad.objects.select_for_update(no_key=True).filter(pk__in=previo.variedades).order_by("pk"))
    sectores = sorted(set(OcupacionSector.objects.filter(lote_id__in=previo.lotes).values_list("sector_id", flat=True)))
    if sectores:
        list(SectorProduccion.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=sectores).order_by("pk"))
    stock_maduro.bloquear_candidatos(sorted(previo.variedades), sorted(previo.invernaderos))
    if previo.lotes:
        list(Lote.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.lotes).order_by("pk"))
    if previo.partidas:
        list(StockCosechado.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=previo.partidas).order_by("pk"))
    list(Suministro.objects.select_for_update(no_key=True, of=("self",)).filter(pk=suministro.pk))
    list(DetalleSuministro.objects.select_for_update(no_key=True, of=("self",)).filter(suministro=suministro).order_by("pk"))
    if previo.cosechas:
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=[c.pk for c in previo.cosechas]).order_by("pk"))
    list(ReservaStock.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=[r.pk for r in previo.reservas]).order_by("pk"))
    list(DetalleReserva.objects.select_for_update(no_key=True, of=("self",)).filter(reserva_id__in=[r.pk for r in previo.reservas]).order_by("pk"))
    if previo.entregas:
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=[e.pk for e in previo.entregas]).order_by("pk"))


# ---- los textos y los avisos ----


def _acotar(texto, largo):
    return entregas._acotar(texto, largo)


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _descripcion_de_la_alerta(suministro, solicitud, cosechas_, entregas_, partidas):
    """«Lista de tecnología», 6, en lo que cabe: `Alerta.descripcion_alerta` admite 200 caracteres (el caso de uso dice 500: va a `docs/temas_abiertos.md`), así que van el contrato, el cliente, los
    incumplimientos, la solicitud, la multa y lo que se deshizo; el Vendedor, los invernaderos y las fechas están en el aviso al Vendedor, el del Agrónomo y la auditoría. «SUM-0013 (Pérez SA)
    resuelto por incumplimientos: 4 de 3 tolerados, por SR-0012. Multa: $ 50.000,00. Se cancelaron 2 cosechas y 1 entrega; 1 partida ingresó a la cámara.»"""
    por = f", por {solicitud.codigo}" if solicitud is not None else ""
    multa = f"Multa: {texto_de_pesos(suministro.multa_resolucion)}." if suministro.multa_resolucion > 0 else "El contrato no prevé multa."
    texto = (
        f"{suministro.codigo} ({suministro.cliente.nombre_visible}) resuelto por incumplimientos: {suministro.cantidad_incumplimientos} de {suministro.incumplimientos_tolerados} tolerados{por}. "
        f"{multa} Se cancelaron {_plural(len(cosechas_), 'cosecha', 'cosechas')} y {_plural(len(entregas_), 'entrega', 'entregas')}; "
        f"{_plural(len(partidas), 'partida ingresó', 'partidas ingresaron')} a la cámara."
    )
    return _acotar(texto, LARGO_DE_LA_ALERTA)


def _avisar_al_vendedor(suministro, entregas_):
    """Paso 9 (l): al Vendedor del contrato, si está activo; con la multa y las entregas canceladas."""
    vendedor = Usuario.objects.filter(pk=suministro.vendedor_id, is_active=True).first()
    if vendedor is None:  # 9a
        return None
    canceladas = ", ".join(f"{e.codigo} ({e.fecha_programada_orden:%d/%m})" for e in entregas_) or "ninguna"
    multa = f"Multa: {texto_de_pesos(suministro.multa_resolucion)}." if suministro.multa_resolucion > 0 else "Sin multa."
    notificaciones.notificar(
        vendedor,
        _acotar(f"{suministro.codigo} resuelto por incumplimientos", notificaciones.LARGO_TITULO),
        _acotar(f"{suministro.cliente.nombre_visible}. {multa} Entregas canceladas: {canceladas}.", notificaciones.LARGO_DETALLE),
    )
    return vendedor


def _avisar_a_los_agronomos(suministro, cosechas_, partidas, cancelaciones):
    """Paso 9 (l): al Agrónomo activo de **cada invernadero afectado**, UNA sola notificación: las cosechas canceladas, las partidas que ingresaron a la cámara (cantidad y fecha límite) y
    los envases que estaban reservados en cada entrega cancelada. Sin Agrónomo activo no se envía (9a: la alerta «invernadero sin Agrónomo activo» ya existe). Devuelve los avisados."""
    por_invernadero = {}

    def fila(invernadero_id):
        return por_invernadero.setdefault(invernadero_id, SimpleNamespace(cosechas=[], partidas=[], envases=[]))

    for c in cosechas_:
        fila(c.invernadero_id).cosechas.append(c.codigo)
    for p in partidas:
        fila(p.lote.invernadero_id).partidas.append(f"{p.cantidad_ingreso_cosechado} plantas de {p.lote.siembra.variedad} (vence el {p.fecha_limite:%d/%m})")
    insumos = {
        i.pk: i
        for i in InsumoInvernadero.objects.filter(pk__in=[r.insumo_invernadero_id for c in cancelaciones for r in c.reservas_de_insumo]).select_related("insumo")
    }
    for c in cancelaciones:
        if c.reservas_de_insumo:
            reservados = ", ".join(f"{r.cantidad_reservada} {insumos[r.insumo_invernadero_id].insumo.nombre_insumo}" for r in c.reservas_de_insumo)
            fila(c.entrega.invernadero_id).envases.append(f"{c.entrega.codigo}: {reservados}")
    avisados = []
    for invernadero in Invernadero.objects.filter(pk__in=por_invernadero).select_related("agronomo").order_by("pk"):
        agronomo = invernadero.agronomo
        if agronomo is None or not agronomo.is_active:  # 9a
            continue
        cambios = por_invernadero[invernadero.pk]
        partes = []
        if cambios.cosechas:
            partes.append(f"Cosechas canceladas: {', '.join(cambios.cosechas)}.")
        if cambios.partidas:
            partes.append(f"Ingresó a la cámara: {'; '.join(cambios.partidas)}.")
        if cambios.envases:
            partes.append(f"Envases que estaban reservados: {'; '.join(cambios.envases)}. Si ya se usaron, ajustá el stock.")
        notificaciones.notificar(
            agronomo,
            _acotar(f"{suministro.codigo} resuelto: cambios en {invernadero}", notificaciones.LARGO_TITULO),
            _acotar(" ".join(partes), notificaciones.LARGO_DETALLE),
        )
        avisados.append(agronomo)
    return avisados


# ---- el caso de uso (pasos 2 a 9) ----


def _descartar(suministro):
    """Extensión 2b y D-69 punto 15: el disparo no corresponde (el contrato ya no supera los tolerados). No cambia nada y deja constancia: un registro sin usuario (InfoPonia) con el
    suministro y los dos números. La extensión 2a (el contrato ya no está «vigente») no deja registro."""
    with transaction.atomic():
        RegistroAuditoria.objects.registrar(
            usuario=None,
            accion=RegistroAuditoria.Accion.RESOLUCION_SUMINISTRO_DESCARTADA,
            afectados=[suministro],
            detalle={
                "datos": {
                    "suministro": referencia(suministro),
                    "cantidad_incumplimientos": suministro.cantidad_incumplimientos,
                    "incumplimientos_tolerados": suministro.incumplimientos_tolerados,
                }
            },
        )


def _crear_la_alerta(alcance, descripcion):
    """Paso 4.7 (i; D-69 punto 14): la alerta «suministro resuelto» para el Gerente con su `AlertaComercial(suministro=…)`, en el invernadero de D-63 punto 2. Si ese invernadero está inactivo
    (`crear_alerta_de_evento` devuelve `None`), el activo de menor id del Vendedor; si tampoco hay, sin alerta: el llamador avisa al Vendedor y al Gerente (D-63 punto 4). Sin Gerente activo la
    alerta se registra igual (6b: queda esperándolo)."""
    for invernadero_id in (alcance.invernadero_de_la_alerta, alcance.alternativo):
        if invernadero_id is None:
            continue
        alerta = alertas.crear_alerta_de_evento(invernadero_id, TIPO_DE_ALERTA, descripcion)
        if alerta is not None:
            AlertaComercial.objects.create(alerta=alerta, suministro=alcance.suministro)
            return alerta
    return None


def _resolver(suministro_id, hoy, previo):
    """Un intento de resolver, todo en una transacción. Devuelve `ResultadoDeResolucion`, o `None` si el contrato ya no corresponde (2a y 2b con los datos de ahora). Si al bloquear aparece algo que
    la lectura previa no vio, `_AlcanceCambio`."""
    with transaction.atomic():
        _bloquear(previo)
        ahora = _alcance(suministro_id)
        suministro = ahora.suministro
        if suministro.estado_suministro != VIGENTE:  # 2a, con el resultado de la primera operación
            return None
        if not _supera(suministro):  # 2b: una anulación llegó antes
            _descartar(suministro)
            return None
        if not _contenido_en(ahora, previo):  # 6a
            raise _AlcanceCambio()

        motivo = _motivo(suministro)
        solicitud = _solicitud_que_provoco(suministro.pk)
        # 4.1 a 4.3, c, d y e: las cosechas «a realizar» (con el aviso al Capataz, sin el del Agrónomo), una partida por cada línea ya cosechada y las reservas «liberadas».
        partidas, cosechas_canceladas, reservas_liberadas, reasignar = faltantes.liberar_reservas(
            ahora.reservas, None, hoy, origen=suministro, motivo_de_la_cosecha=motivo, motivo_de_la_partida=StockCosechado.Motivo.RESOLUCION_DEL_CONTRATO, avisar_agronomo=False
        )
        # 4.4, f y g: las entregas «a realizar», también la que está en curso (3c: «No la entregues…»).
        cancelaciones = [entregas.cancelar_entrega_incluida(None, e, motivo, avisar_agronomo=False) for e in ahora.entregas]
        entregas_canceladas = [c.entrega for c in cancelaciones]
        reservas_de_envases = [r for c in cancelaciones for r in c.reservas_de_insumo]
        alertas_resueltas = [c.alerta_resuelta for c in cancelaciones if c.alerta_resuelta is not None]
        # 4.5, a y b: el contrato y sus detalles «vigentes» (los «finalizados» no cambian; `cantidad_incumplimientos` tampoco; la rescisión acordada queda como estaba y la resolución prevalece).
        Suministro.objects.filter(pk=suministro.pk).update(
            estado_suministro=Suministro.Estado.RESUELTO, fecha_resolucion_suministro=hoy, solicitud_resolucion=solicitud,
            estado_comprobante=Contrato.EstadoDelComprobante.PENDIENTE_ENVIO if suministro.cliente.email_cliente else Contrato.EstadoDelComprobante.PARA_IMPRIMIR,
        )
        DetalleSuministro.objects.filter(pk__in=[d.pk for d in ahora.detalles]).update(estado_detalle_suministro=DetalleSuministro.Estado.RESUELTO)
        # 4.6: las alertas «período sin cobertura» de sus detalles dejan de tener sentido (regla 7 de 8.18).
        for vinculo in ahora.alertas_de_periodo:
            resuelta = alertas.resolver_alerta_de_estado(vinculo.alerta.invernadero_id, TIPO_PERIODO_SIN_COBERTURA, clave=vinculo.alerta.clave_estado)
            if resuelta is not None:
                alertas_resueltas.append(resuelta)
        # 4.7: la alerta «suministro resuelto» para el Gerente.
        descripcion = _descripcion_de_la_alerta(suministro, solicitud, cosechas_canceladas, entregas_canceladas, partidas)
        alerta = _crear_la_alerta(ahora, descripcion)
        # 4.6 bis, h (CON-04d): el asiento de la multa, DESPUÉS de todos los bloqueos de negocio: el ejercicio va último (D-86). Actor `None`: la resolución es de InfoPonia en sus dos caminos.
        asiento = asientos_comerciales.asentar_multa_de_resolucion(Suministro.objects.get(pk=suministro.pk), hoy)
        # 4.9: los avisos (dentro de la transacción, D-42).
        vendedor = _avisar_al_vendedor(suministro, entregas_canceladas)
        if alerta is None:  # D-63 punto 4: sin invernadero activo del Vendedor no hay alerta: se avisa al Vendedor y al Gerente con el mismo texto.
            gerente = Usuario.objects.filter(rol=Usuario.Rol.GERENTE, is_active=True).order_by("pk").first()
            if gerente is not None:
                notificaciones.notificar(gerente, _acotar(f"{suministro.codigo} resuelto por incumplimientos", notificaciones.LARGO_TITULO), _acotar(descripcion, notificaciones.LARGO_DETALLE))
        avisados = _avisar_a_los_agronomos(suministro, cosechas_canceladas, partidas, cancelaciones)
        # 4.8: UN registro de auditoría (D-36).
        _auditar(suministro, hoy, solicitud, ahora, reservas_liberadas, cosechas_canceladas, entregas_canceladas, reservas_de_envases, partidas, alertas_resueltas, alerta, asiento)
        # 5: después de confirmar, PROD-ASG-CAM con lo que ingresó y con lo que se liberó de la cámara, y el aviso de resolución al cliente.
        ids = sorted({p.pk for p in partidas} | set(reasignar))
        if ids:
            from comercial.servicios import camara

            transaction.on_commit(partial(_correr, camara.asignar_camara, ids))
        transaction.on_commit(partial(_correr, _avisar_al_cliente, suministro.pk))
        return ResultadoDeResolucion(
            Suministro.objects.get(pk=suministro.pk), ahora.detalles, cosechas_canceladas, entregas_canceladas, reservas_liberadas, partidas, alertas_resueltas, alerta
        )


def _auditar(suministro, hoy, solicitud, ahora, reservas_liberadas, cosechas_canceladas, entregas_canceladas, reservas_de_envases, partidas, alertas_resueltas, alerta, asiento=None):
    """Paso 4.8 (m): el único registro del caso de uso, sin usuario (InfoPonia, D-27). Afectados: el suministro (principal), los detalles, las reservas liberadas, las cosechas y las entregas
    canceladas con sus reservas de envases, las partidas creadas con su movimiento, las alertas resueltas y la creada. Las funciones incluidas no auditan por su cuenta."""
    movimientos = list(MovimientoStock.objects.filter(partida__in=partidas, tipo_movimiento=MovimientoStock.TipoMovimiento.INGRESO_A_CAMARA).order_by("pk")) if partidas else []
    cambios = {
        "estado_suministro": {"antes": Suministro.Estado.VIGENTE.value, "despues": Suministro.Estado.RESUELTO.value},
        "fecha_resolucion_suministro": {"antes": None, "despues": f"{hoy:%d/%m/%Y}"},
    }
    if solicitud is not None:
        cambios["solicitud_resolucion"] = {"antes": None, "despues": referencia(solicitud)}
    datos = {
        "suministro": referencia(suministro),
        "cantidad_incumplimientos": suministro.cantidad_incumplimientos,
        "incumplimientos_tolerados": suministro.incumplimientos_tolerados,
        "multa_resolucion": str(suministro.multa_resolucion),
        "detalles_resueltos": [f"{d}: vigente → resuelto" for d in ahora.detalles],
    }
    for clave, valores in (
        ("reservas_liberadas", reservas_liberadas),
        ("cosechas_canceladas", cosechas_canceladas),
        ("entregas_canceladas", entregas_canceladas),
        ("reservas_de_envases_canceladas", reservas_de_envases),
        ("partidas_creadas", partidas),
        ("movimientos_creados", movimientos),
        ("alertas_resueltas", alertas_resueltas),
        ("alertas_creadas", [alerta] if alerta is not None else []),
        ("asientos", [asiento] if asiento is not None else []),
    ):
        if valores:
            datos[clave] = [str(v) for v in valores]
    RegistroAuditoria.objects.registrar(
        usuario=None,
        accion=RegistroAuditoria.Accion.RESOLUCION_SUMINISTRO,
        afectados=[
            suministro, *ahora.detalles, *reservas_liberadas, *cosechas_canceladas, *entregas_canceladas, *reservas_de_envases, *partidas, *movimientos, *alertas_resueltas,
            *([alerta] if alerta is not None else []),
            *([asiento] if asiento is not None else []),
        ],
        detalle={"cambios": cambios, "datos": datos},
    )


def _correr(funcion, *argumentos):
    """Corre algo de un `on_commit` sin que una falla lo deshaga: la resolución ya quedó registrada (7a y 8a; garantía mínima de COM-RSV-SUM)."""
    try:
        funcion(*argumentos)
    except Exception:  # noqa: BLE001
        logger.exception("Falló %s%s después de resolver un suministro", getattr(funcion, "__name__", funcion), argumentos)


def _avisar_al_cliente(suministro_id):
    """Postcondición k, DESPUÉS de confirmar (D-14, D-54): el aviso de resolución al cliente, con su multa y las entregas canceladas (`enviar_comprobante(tipo="resolucion")`). Su resultado queda
    en `Contrato.estado_comprobante`; el reintento es «Reenviar comprobante» en la ficha (8a)."""
    comprobantes.enviar_comprobante(Suministro.objects.get(pk=suministro_id), tipo="resolucion")


def resolver_suministro(suministro_id, hoy, *, intento=1):
    """COM-RSV-SUM, pasos 2 a 9 para un suministro: la usan las dos entradas (la aceptación y la recuperación diaria). Devuelve `ResultadoDeResolucion` o `None`.

    - Lectura sin bloquear: el suministro ya no está «vigente» (2a) → `None`, sin registro; no supera los tolerados (2b) → `None` con el registro `resolucion_suministro_descartada`.
    - Con todo bloqueado se relee (6a): si cambió algo que no estaba en la lectura previa, se repite UNA vez (`intento=2`); si vuelve a cambiar, no registra nada y el disparo queda pendiente (lo toma el
      paso 33). Una cosecha o una entrega que se concretó antes de bloquear ya no figura «a realizar»: se conserva.
    - Un error cualquiera deshace todo (extensión *a); lo trata quien llama."""
    previo = _alcance(suministro_id)
    if previo is None or previo.suministro.estado_suministro != VIGENTE:  # 2a
        return None
    if not _supera(previo.suministro):  # 2b
        _descartar(previo.suministro)
        return None
    try:
        return _resolver(suministro_id, hoy, previo)
    except _AlcanceCambio:
        if intento == 1:
            return resolver_suministro(suministro_id, hoy, intento=2)
        logger.warning("La resolución del suministro %s cambió dos veces mientras se bloqueaba: queda pendiente para el paso 33.", suministro_id)
        return None


def resolver_si_corresponde(suministro_id):
    """Disparador 1 de COM-RSV-SUM: lo llaman COM-EVL-DSC y COM-RSV-QJA con `transaction.on_commit` después de CADA aceptación (D-69 punto 13), fuera de su transacción. Corre el caso de uso en
    su propia transacción; si algo falla registra la excepción (`logger.exception`) y devuelve `None`: la aceptación ya quedó (garantía mínima; extensión *a: el paso 33 lo retoma). `None`
    también en 2a. Como se llama con toda aceptación y el caso de uso solo corresponde cuando se superan los tolerados, una aceptación común (sin superarlos) no hace nada ni deja registro:
    el 2b queda para el disparo que llega con el contrato ya sin superarlos (una anulación llegó antes) y para quien llama a `resolver_suministro` directo."""
    try:
        if not Suministro.objects.filter(pk=suministro_id, estado_suministro=VIGENTE, cantidad_incumplimientos__gt=F("incumplimientos_tolerados")).exists():
            return None
        return resolver_suministro(suministro_id, stock.hoy())
    except Exception:  # noqa: BLE001 - la aceptación que lo disparó ya está registrada
        logger.exception("Falló la resolución del suministro %s", suministro_id)
        return None



def datos_de_la_resolucion(suministro):
    """Lo que dice el aviso de resolución al cliente («Lista de tecnología», 8) y la ficha: la fecha, los incumplimientos que la provocaron y los tolerados, la multa, la solicitud que la
    provocó y las entregas canceladas por la resolución (las «canceladas» ese día con el motivo de este caso de uso, con su fecha programada). `None` si el suministro no está «resuelto»."""
    if suministro.estado_suministro != Suministro.Estado.RESUELTO:
        return None
    canceladas = list(
        Entrega.objects.filter(
            contrato_entrega_id=suministro.pk,
            estado_orden=OrdenTrabajo.Estado.CANCELADA,
            fecha_resolucion_orden=suministro.fecha_resolucion_suministro,
            motivo_cancelacion=_motivo(suministro),
        ).order_by("fecha_programada_orden", "pk")
    )
    solicitud = SolicitudRevision.objects.filter(pk=suministro.solicitud_resolucion_id).select_related("entrega").first() if suministro.solicitud_resolucion_id else None
    return SimpleNamespace(
        fecha=suministro.fecha_resolucion_suministro,
        incumplimientos=suministro.cantidad_incumplimientos,
        tolerados=suministro.incumplimientos_tolerados,
        multa=suministro.multa_resolucion,
        asiento=asientos_comerciales.asiento_de(suministro.pk),  # CON-04d: el asiento de la multa (texto, sin enlace), o `None` sin multa o anterior a esta tarea
        solicitud=solicitud,
        entregas_canceladas=canceladas,
    )


# ---- la recuperación diaria (disparador 2 y extensión 1a; paso 33) ----


def _candidatos(hoy=None):
    """Extensión 1a.1: los suministros «vigentes» cuya cantidad de incumplimientos ya supera la tolerada, del que superó la tolerancia antes al que la superó después (1a.3): por la
    `fecha_resolucion` de su solicitud aceptada más reciente y, a igual fecha, por id. Un contrato sin solicitudes aceptadas (un contador cargado a mano) va al final."""
    ultima = (
        SolicitudRevision.objects.filter(entrega__contrato_entrega_id=OuterRef("pk"), estado_solicitud=SolicitudRevision.Estado.ACEPTADA)
        .order_by("-fecha_resolucion", "-pk")
        .values("fecha_resolucion")[:1]
    )
    return list(
        Suministro.objects.filter(estado_suministro=VIGENTE, cantidad_incumplimientos__gt=F("incumplimientos_tolerados"))
        .annotate(desde=Subquery(ultima))
        .order_by(F("desde").asc(nulls_last=True), "pk")
        .values_list("pk", flat=True)
    )


def resolver_suministros_pendientes(hoy):
    """Paso diario 33, «Resolver suministros con incumplimientos superados» (D-56 punto 6, enmendado por D-69 punto 7): recupera el disparo que falló o no llegó a ejecutarse (garantía
    mínima, situación 6). Busca los suministros «vigentes» que ya superan los tolerados y los resuelve de a uno con `resolver_suministro`, cada uno en su propia transacción; si uno falla se
    registra y siguen los demás (D-56 punto 5: el paso no se corta). Sin candidatos no registra nada (1a.2). Idempotente: un segundo pase el mismo día no encuentra nada. Va ANTES de los pasos
    35, 40 y 50, para que un contrato que hay que resolver no reciba reservas ni entregas nuevas ese día.

    Devuelve `ResumenDePaso(procesados=candidatos, creados=0, resueltos=los que se resolvieron, detalle=«N suministros resueltos, N descartados, N con error»)`; «descartados» son los que
    ya no correspondían al leerlos de nuevo (2a o 2b).

    Regla 9 de CON-INI-EJE (CON-05): sin ningún ejercicio contable no procesa nada (la multa asienta) y reintenta al día siguiente."""
    if not ejercicios.contabilidad_iniciada():
        return ejercicios.resumen_de_paso_sin_contabilidad()
    candidatos = _candidatos(hoy)
    resueltos = descartados = fallaron = 0
    for suministro_id in candidatos:
        try:
            if resolver_suministro(suministro_id, hoy) is None:
                descartados += 1
            else:
                resueltos += 1
        except Exception:  # noqa: BLE001 - un contrato que falla no puede dejar a los demás sin resolver (D-56, punto 5)
            fallaron += 1
            logger.exception("Falló la resolución del suministro %s en el paso diario 33", suministro_id)
    return ResumenDePaso(len(candidatos), 0, resueltos, f"{resueltos} suministros resueltos, {descartados} descartados, {fallaron} con error")


# ---- «Dar por atendida», la marca de la lista y el enlace de la alerta (regla «Alerta “suministro resuelto”»; D-69 puntos 14 y 15; MAE-02d) ----

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
GERENTE = Usuario.Rol.GERENTE


def _exigir_gerente(actor):
    """El Gerente con la cuenta activa, leída de la base (una cuenta dada de baja después de cargarse no atiende). Cualquier otro: `PermissionDenied` (`sin_permiso`)."""
    vigente = Usuario.objects.filter(pk=actor.pk).first() if actor is not None and getattr(actor, "pk", None) else None
    if vigente is None or not vigente.is_active or rol_de(vigente) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return vigente


def resolucion_sin_atender(suministro_ids):
    """Los ids, de `suministro_ids`, cuya alerta «suministro resuelto» sigue activa (el Gerente todavía no la dio por atendida): la marca «Resolución sin atender» de la lista y el botón de la ficha.
    Una consulta."""
    ids = list(suministro_ids)
    if not ids:
        return set()
    return set(
        AlertaComercial.objects.filter(suministro_id__in=ids, alerta__tipo_alerta=TIPO_DE_ALERTA, alerta__estado_alerta="activa").values_list("suministro_id", flat=True)
    )


def dar_por_atendida_la_resolucion(actor, suministro_id):
    """«Dar por atendida» (regla «Alerta “suministro resuelto”»): el Gerente da por atendida la alerta cuando pagó la multa y avisó al cliente (el Sistema no lo puede saber: el pago es un asiento manual,
    MD-31). Devuelve la `Alerta` resuelta.

    - Solo el Gerente activo (`PermissionDenied`, `sin_permiso`); un suministro que no existe, `Http404`.
    - Una transacción: bloquea la cuenta del Gerente → el invernadero de la alerta (`bloquear_invernadero_para_alertas`, dentro de `resolver_alerta`) → la alerta; relee que siga activa:
      si ya estaba resuelta (o el contrato nunca tuvo una), `alerta_resuelta` en `__all__`.
    - Un registro de auditoría `atencion_suministro_resuelto` con el suministro y la alerta. Sin notificaciones."""
    _exigir_gerente(actor)
    if not Suministro.objects.filter(pk=suministro_id).exists():
        raise Http404("No existe ese suministro.")
    previo = AlertaComercial.objects.filter(suministro_id=suministro_id, alerta__tipo_alerta=TIPO_DE_ALERTA).order_by("-pk").first()
    ya_resuelta = ValidationError({"__all__": [ValidationError("Esta alerta ya fue atendida.", code="alerta_resuelta")]})
    if previo is None:
        raise ya_resuelta
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk))
        quien = _exigir_gerente(actor)  # después de bloquear: una baja de la cuenta que esperaba, ya está
        resuelta = alertas.resolver_alerta(previo.alerta_id)  # bloquea el invernadero y la alerta; `None` si ya estaba resuelta
        if resuelta is None:
            raise ya_resuelta
        suministro = Suministro.objects.get(pk=suministro_id)
        RegistroAuditoria.objects.registrar(
            usuario=quien,
            accion=RegistroAuditoria.Accion.ATENCION_SUMINISTRO_RESUELTO,
            afectados=[suministro, resuelta],
            detalle={"datos": {"suministro": referencia(suministro), "alerta": referencia(resuelta), "alertas_resueltas": [str(resuelta)]}},
        )
        return resuelta


def enlaces_de_alertas(usuario, alertas_resueltas):
    """`registrar_enlace_de_alerta` para `comercial_suministro_resuelto` (MAE-02d, D-62; D-69 punto 14): solo el Gerente la recibe; lleva a la ficha del suministro, con el detalle
    «SUM-0013 · resuelto · multa $ 50.000,00». Una consulta para toda la lista."""
    alertas_resueltas = list(alertas_resueltas)
    if not alertas_resueltas or rol_de(usuario) != GERENTE:
        return {}
    enlaces = {}
    for vinculo in AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_resueltas], suministro__isnull=False).select_related("suministro"):
        s = vinculo.suministro
        enlaces[vinculo.alerta_id] = Enlace(reverse("comercial:suministro", args=[s.pk]), f"{s.codigo} · resuelto · multa {texto_de_pesos(s.multa_resolucion)}")
    return enlaces
