# Pre-reserva diaria de los períodos de suministro (PROD-PRR-SUM, COM-03b; docs/casos_de_uso/produccion/pre_reserva.md, «Cómo se aplica»). Es el paso diario 40
# del proceso diario (D-56): `pre_reservar_suministros(hoy)` toma los períodos que entran en la ventana de pre-reserva y todavía tienen cantidad sin cubrir,
# les reserva stock maduro con `asignar` (PROD-ASG-STK) y, si no alcanza, deja la alerta «período sin cobertura completa» (MD-133, D-63) y avisa al Vendedor.
# Aunque su código empieza con PROD, vive en `comercial` porque toca reservas (D-59).
#
# Contrato del paso (D-56, punto 4): nunca lee la fecha por su cuenta (`hoy` llega de afuera: así `--fecha` simula el paso del tiempo), es idempotente
# y trabaja un período por transacción. Una excepción de un período se registra en el log y los demás siguen (extensión *a): al día siguiente el período
# se vuelve a tomar porque sigue con cantidad sin cubrir.
#
# Bloqueos de cada período (docs/patrones/stock_maduro.md, sección 3; ``FOR NO KEY UPDATE``): la cuenta del Vendedor del contrato → sus invernaderos
# activos (`bloquear_invernadero_activo`, por id) → la variedad → los lotes y las partidas candidatos → el `Suministro` y el `DetalleSuministro`. Con todo
# bloqueado se relee que sigan «vigentes», que la fecha siga en el calendario y que la cantidad sin cubrir siga siendo mayor que 0 (otra corrida o una
# modificación pudieron cambiarlas); si no, el período se saltea sin cambios. COM-MOD-SUM bloquea el mismo `Suministro`: se ponen en fila.
# Desde COM-04a (D-64, punto 8) también se toman los períodos de un detalle «finalizado» con fecha hasta su `fecha_fin_detalle`: todavía se deben.

import logging
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from comercial.models import AlertaComercial, DetalleReserva, DetalleSuministro, ReservaStock, Suministro
from comercial.servicios import calendario, stock_maduro
from comercial.servicios.stock_maduro import Periodo
from core import notificaciones
from core.models import Notificacion, RegistroAuditoria, Usuario, rol_de
from core.procesos import ResumenDePaso
from inventario.servicios.variedades import bloquear_variedad
from maestros.extensiones import Enlace
from maestros.models import Alerta, Invernadero
from maestros.servicios import alertas
from maestros.servicios.invernaderos import bloquear_invernadero_activo

logger = logging.getLogger("infoponia.pre_reserva")

TIPO_DE_ALERTA = "comercial_periodo_sin_cobertura"
TITULO_DEL_AVISO = "Período sin cobertura completa"
GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO


def _clave(detalle_id, fecha):
    """La clave de la alerta de estado de un período («una por período», D-63 punto 3)."""
    return f"periodo:{detalle_id}:{fecha.isoformat()}"


def _plantas(cantidad):
    """«120 plantas» / «1 planta»."""
    return f"{cantidad} planta{'s' if cantidad != 1 else ''}"


def _faltan(cantidad):
    """«Faltan 120 plantas» / «Falta 1 planta»."""
    return f"{'Faltan' if cantidad != 1 else 'Falta'} {_plantas(cantidad)}"


def _activas_de(detalle_ids, desde, hasta):
    """Las `AlertaComercial` de período con su alerta ACTIVA, de esos detalles y con fecha entre ``desde`` y ``hasta``."""
    return AlertaComercial.objects.filter(
        alerta__tipo_alerta=TIPO_DE_ALERTA,
        alerta__estado_alerta=Alerta.Estado.ACTIVA,
        detalle_suministro_id__in=detalle_ids,
        fecha_periodo__range=(desde, hasta),
    )


# ---- los períodos a pre-reservar (paso 2) ----


def _periodos_a_pre_reservar(hoy):
    """Regla «Período a pre-reservar»: de un detalle «vigente» (o «finalizado», hasta su fecha de fin: D-64 punto 8) de un suministro «vigente», con fecha entre hoy y hoy + días de pre-reserva (y sin pasar la
    fecha de fin del detalle ni la del contrato: lo cumple el calendario), con cantidad sin cubrir mayor que 0. También los que tienen una alerta activa
    aunque ya estén cubiertos (para resolverla). Ordenados por fecha y, con la misma fecha, por id del detalle (orden de registro)."""
    ventana = calendario.ventana(hoy)
    detalles = list(
        DetalleSuministro.objects.filter(
            estado_detalle_suministro__in=[DetalleSuministro.Estado.VIGENTE, DetalleSuministro.Estado.FINALIZADO],
            suministro__estado_suministro=Suministro.Estado.VIGENTE,
            fecha_primer_entrega__lte=ventana,
            suministro__fecha_fin__gte=hoy,
        )
        .select_related("suministro", "variedad")
        .order_by("pk")
    )
    periodos = [Periodo(d, fecha) for d in detalles for fecha in calendario.calendario(d, desde=hoy, hasta=ventana)]
    if not periodos:
        return []
    sin_cubrir = stock_maduro.sin_cubrir_de_periodos(periodos)
    con_alerta = set(_activas_de({d.pk for d in detalles}, hoy, ventana).values_list("detalle_suministro_id", "fecha_periodo"))
    elegidos = [p for p in periodos if sin_cubrir[p] > 0 or (p.detalle.pk, p.fecha) in con_alerta]
    return sorted(elegidos, key=lambda p: (p.fecha, p.detalle.pk))


# ---- un período, en su transacción ----


def _avisar_sin_invernaderos(detalle, fecha, faltan, cuentas):
    """D-63, punto 4: el Vendedor se quedó sin invernaderos activos, así que no hay dónde colgar la alerta. Se avisa al Vendedor y al Gerente con el mismo
    texto, una sola vez (si ya recibieron ese texto, no se repite: la ejecución es diaria)."""
    detalle_del_aviso = _texto_del_aviso(detalle, fecha, faltan)
    gerente = Usuario.objects.filter(rol=GERENTE, is_active=True).first()
    for cuenta in (cuentas[detalle.suministro.vendedor_id], gerente):
        if cuenta is None:
            continue
        if not Notificacion.objects.filter(destinatario=cuenta, titulo=TITULO_DEL_AVISO, detalle=detalle_del_aviso).exists():
            notificaciones.notificar(cuenta, TITULO_DEL_AVISO, detalle_del_aviso)


def _texto_del_aviso(detalle, fecha, faltan):
    """«SUM-0013: el período del 26/11 de Lechuga Crespa quedó sin cobertura completa. Faltan 120 plantas. InfoPonia vuelve a intentar cada día.»"""
    return (
        f"{detalle.suministro.codigo}: el período del {fecha:%d/%m} de {detalle.variedad} quedó sin cobertura completa. "
        f"{_faltan(faltan)}. InfoPonia vuelve a intentar cada día."
    )


def _pre_reservar_periodo(detalle_id, fecha):
    """Pre-reserva un período (pasos 3 a 5 y extensiones 3a, 3b y 4a) en su transacción. Devuelve ``None`` si no había nada que hacer (otra operación lo
    cubrió, lo cambió o ya no es un período), o un ``SimpleNamespace(reservas, alertas_creadas, alertas_resueltas, sin_cubrir)``."""
    with transaction.atomic():
        previo = DetalleSuministro.objects.select_related("suministro", "variedad").get(pk=detalle_id)
        vendedor_id = previo.suministro.vendedor_id
        cuentas = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk=vendedor_id)}
        habilitados = []
        for pk in Invernadero.objects.filter(vendedor_id=vendedor_id, estado_invernadero=Invernadero.Estado.ACTIVO).order_by("pk").values_list("pk", flat=True):
            try:
                habilitados.append(bloquear_invernadero_activo(pk))
            except ValidationError:
                continue  # se dio de baja mientras tanto
        bloquear_variedad(previo.variedad_id)
        stock_maduro.bloquear_candidatos([previo.variedad_id], [i.pk for i in habilitados])
        Suministro.objects.select_for_update(no_key=True).get(pk=previo.suministro_id)
        detalle = DetalleSuministro.objects.select_for_update(no_key=True, of=("self",)).select_related("suministro", "variedad").get(pk=detalle_id)
        detalle.suministro = Suministro.objects.select_related("cliente").get(pk=detalle.suministro_id)

        # Se relee todo con las filas bloqueadas: si algo cambió, el período se saltea sin cambios.
        vigente = (
            stock_maduro._se_debe(detalle, fecha)
            and detalle.suministro.estado_suministro == Suministro.Estado.VIGENTE
            and bool(calendario.calendario(detalle, desde=fecha, hasta=fecha))
        )
        if not vigente or detalle.suministro.vendedor_id != vendedor_id:
            return None
        periodo = Periodo(detalle, fecha)
        sin_cubrir = stock_maduro.sin_cubrir_de_periodos([periodo])[periodo]
        existente = _activas_de([detalle.pk], fecha, fecha).select_related("alerta").first()
        if sin_cubrir <= 0 and existente is None:
            return None

        reservas, cosechas, creadas, resueltas = [], [], 0, 0
        final = sin_cubrir
        if sin_cubrir > 0 and habilitados:
            resultado = stock_maduro.asignar(None, periodo, sin_cubrir, fecha, "suministro")  # origen InfoPonia (D-27); 3b sale sola
            reservas, cosechas, final = resultado.reservas, resultado.cosechas, resultado.sin_cubrir
        lineas = list(DetalleReserva.objects.filter(reserva__in=reservas).select_related("lote", "partida").order_by("pk"))

        alertas_tocadas, cambio = [], bool(reservas)
        if final > 0:
            if existente is not None:
                if existente.cantidad_sin_cubrir != final:
                    AlertaComercial.objects.filter(pk=existente.pk).update(cantidad_sin_cubrir=final)
                    cambio = True
            else:
                propias = ReservaStock.objects.filter(detalle_suministro=detalle, fecha_entrega_reserva=fecha).exclude(estado_reserva="liberada").order_by("pk").first()
                invernadero_id = propias.invernadero_id if propias is not None else (habilitados[0].pk if habilitados else None)
                alerta = (
                    alertas.asegurar_alerta_de_estado(
                        invernadero_id,
                        TIPO_DE_ALERTA,
                        _clave(detalle.pk, fecha),
                        f"Período sin cobertura completa · {detalle.variedad} · {detalle.suministro.cliente} · {fecha:%d/%m}",
                    )
                    if invernadero_id is not None
                    else None
                )
                if alerta is None:  # sin invernadero activo (D-63, punto 4)
                    _avisar_sin_invernaderos(detalle, fecha, final, {**cuentas})
                else:
                    AlertaComercial.objects.create(alerta=alerta, detalle_suministro=detalle, fecha_periodo=fecha, cantidad_sin_cubrir=final)
                    notificaciones.notificar(cuentas[vendedor_id], TITULO_DEL_AVISO, _texto_del_aviso(detalle, fecha, final))
                    alertas_tocadas.append(alerta)
                    creadas, cambio = 1, True
        elif existente is not None:  # postcondición d: el período quedó cubierto
            alertas.resolver_alerta_de_estado(existente.alerta.invernadero_id, TIPO_DE_ALERTA, _clave(detalle.pk, fecha))
            alertas_tocadas.append(existente.alerta)
            resueltas, cambio = 1, True

        if cambio:  # postcondición f: un registro por período en el que cambió algo (si no, cada día dejaría uno igual)
            RegistroAuditoria.objects.registrar(
                usuario=None,
                accion=RegistroAuditoria.Accion.PRE_RESERVA_PERIODO,
                afectados=[detalle, *reservas, *lineas, *cosechas, *alertas_tocadas],
                detalle={
                    "datos": {
                        "fecha_periodo": f"{fecha:%d/%m/%Y}",
                        "cantidad_sin_cubrir": str(final),
                        "alertas_creadas": str(creadas),
                        "alertas_resueltas": str(resueltas),
                        "reservas": [f"{r} · {r.invernadero} · {r.get_estado_reserva_display().lower()}" for r in reservas],
                        "cosechas": [c.codigo for c in cosechas],
                    }
                },
            )
        return SimpleNamespace(reservas=len(reservas), alertas_creadas=creadas, alertas_resueltas=resueltas, sin_cubrir=final)


def _resolver_vencidas(hoy):
    """Decisión de aplicación: «se resuelve al llegar su fecha». El período del día se intenta por última vez en la corrida de ese día y su alerta sigue
    activa; al empezar la del día siguiente, una consulta resuelve las de fecha anterior a ``hoy``, cada una en su transacción y con su auditoría."""
    resueltas = 0
    vencidas = list(
        AlertaComercial.objects.filter(
            alerta__tipo_alerta=TIPO_DE_ALERTA, alerta__estado_alerta=Alerta.Estado.ACTIVA, detalle_suministro__isnull=False, fecha_periodo__lt=hoy
        )
        .select_related("alerta", "detalle_suministro__suministro", "detalle_suministro__variedad")
        .order_by("pk")
    )
    for vinculo in vencidas:
        try:
            with transaction.atomic():
                resuelta = alertas.resolver_alerta_de_estado(
                    vinculo.alerta.invernadero_id, TIPO_DE_ALERTA, _clave(vinculo.detalle_suministro_id, vinculo.fecha_periodo)
                )
                if resuelta is None:
                    continue
                RegistroAuditoria.objects.registrar(
                    usuario=None,
                    accion=RegistroAuditoria.Accion.PRE_RESERVA_PERIODO,
                    afectados=[vinculo.detalle_suministro, resuelta],
                    detalle={
                        "datos": {
                            "fecha_periodo": f"{vinculo.fecha_periodo:%d/%m/%Y}",
                            "cantidad_sin_cubrir": str(vinculo.cantidad_sin_cubrir),
                            "alertas_creadas": "0",
                            "alertas_resueltas": "1",
                        }
                    },
                )
                resueltas += 1
        except Exception:  # noqa: BLE001 - una alerta que falla no corta el paso (extensión *a)
            logger.exception("No se pudo resolver la alerta vencida del período %s", vinculo.pk)
    return resueltas


def pre_reservar_suministros(hoy):
    """PROD-PRR-SUM, paso diario 40: pre-reserva los períodos que entran en la ventana. ``hoy`` es un ``date`` (nunca se lee la fecha por su cuenta).
    Devuelve ``ResumenDePaso(procesados=períodos intentados, creados=reservas creadas, resueltos=alertas resueltas, detalle=«N períodos siguen sin
    cobertura completa»)``. Idempotente: dos corridas el mismo día no crean nada de más. Un período que falla se registra en el log y los demás siguen."""
    resueltos = _resolver_vencidas(hoy)
    procesados = creados = sin_cobertura = 0
    for periodo in _periodos_a_pre_reservar(hoy):
        try:
            resultado = _pre_reservar_periodo(periodo.detalle.pk, periodo.fecha)
        except Exception:  # noqa: BLE001 - un período roto no puede dejar a los demás sin pre-reservar (extensión *a)
            logger.exception("Falló la pre-reserva del período %s del detalle %s", periodo.fecha, periodo.detalle.pk)
            continue
        if resultado is None:
            continue
        procesados += 1
        creados += resultado.reservas
        resueltos += resultado.alertas_resueltas
        sin_cobertura += 1 if resultado.sin_cubrir > 0 else 0
    return ResumenDePaso(procesados, creados, resueltos, f"{sin_cobertura} períodos siguen sin cobertura completa")


# ---- el enlace de la alerta en la campana (D-62) ----


def enlaces_de_alertas_de_periodo(usuario, alertas_de_periodo):
    """Registrante de ``maestros.extensiones.registrar_enlace_de_alerta`` para ``comercial_periodo_sin_cobertura`` (D-62, puntos 2 y 4): adónde lleva cada alerta
    a ``usuario`` y qué texto va debajo de su título. El Gerente, a la ficha del suministro en su calendario; el Agrónomo, que no abre contratos, a la ficha del
    invernadero de la alerta; para cualquier otro rol, nada (queda el enlace por omisión, que no lleva a un 403). Una consulta para toda la lista."""
    alertas_de_periodo = list(alertas_de_periodo)
    if not alertas_de_periodo or rol_de(usuario) not in (GERENTE, AGRONOMO):
        return {}
    vinculos = {
        v.alerta_id: v
        for v in AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_de_periodo], detalle_suministro__isnull=False).select_related(
            "detalle_suministro"
        )
    }
    enlaces = {}
    for alerta in alertas_de_periodo:
        vinculo = vinculos.get(alerta.pk)
        if vinculo is None:
            continue
        texto = f"{_faltan(vinculo.cantidad_sin_cubrir)} para el {vinculo.fecha_periodo:%d/%m}"
        if rol_de(usuario) == GERENTE:
            url = reverse("comercial:suministro", args=[vinculo.detalle_suministro.suministro_id]) + "#calendario"
        else:
            url = reverse("maestros:invernadero", args=[alerta.invernadero_id])
        enlaces[alerta.pk] = Enlace(url, texto)
    return enlaces
