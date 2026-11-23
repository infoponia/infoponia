# Revisión periódica del IoT (IOT-04; IOT-ENT-INF, extensión *b; D-71 y D-76; docs/casos_de_uso/iot/entregar_informacion.md, «La revisión periódica»).
# ``revisar(ahora)`` recorre cada sistema IoT ACTIVO, en orden de id y cada uno en su propia transacción, y hace en ese orden los pasos de *b: sensores sin
# actividad, nodo sin comunicación, «no registrado» sin mensajes, resúmenes horarios, fotoperíodo y retención. Después manda los correos (paso 3 de la tarea).
#
# Reglas comunes (D-71, punto 2): recibe ``ahora`` (un ``datetime`` con zona) y nunca lee la hora por su cuenta; es idempotente (dos corridas seguidas con el
# mismo ``ahora`` no cambian nada la segunda vez: cada paso mira los datos y no lo que pasó desde la corrida anterior, D-76); un sistema que falla se informa
# (``logger.exception``) y no frena a los demás. Las horas y los días se cuentan en la zona del proyecto (``timezone.get_current_timezone()``, D-76 punto 4).
#
# Bloqueos (``FOR NO KEY UPDATE``; el orden de la API, docs/api/alertas.md, sección 3): invernadero → sistema → nodo → sensores, en orden de id, releídos.
# Las alertas se crean y se resuelven con ``alertas_iot`` (nunca con ``maestros.servicios.alertas`` directo).

import logging
from collections import namedtuple
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count, F, Max, Min, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from core import correo
from core.models import Gerente, RegistroAuditoria, referencia
from inventario.servicios.variedades import umbral_efectivo
from iot.models import AlertaIot, FotoperiodoDiario, NodoCentral, ResumenHorario, Sensor, SistemaIoT, Telemetria
from iot.servicios import alertas_iot
from iot.textos import numero_legible
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion

logger = logging.getLogger("iot.revision")

DOS_DECIMALES = Decimal("0.01")
TIPO_SIN_ACTIVIDAD = "iot_dispositivo_sin_actividad"
TIPO_NODO_SIN_COMUNICACION = "iot_nodo_sin_comunicacion"
TIPO_NO_REGISTRADO = "iot_dispositivo_no_registrado"
TIPO_FOTOPERIODO = "iot_fotoperiodo_fuera_de_umbral"
HORAS_QUE_SE_RECALCULAN = 3  # la hora en curso y las dos anteriores (D-76, punto 4)
MAXIMO_DE_INTENTOS = 5  # intentos del correo de una alerta crítica (D-71, punto 3)
PLANTILLA_DEL_CORREO = "iot/correo/alerta_critica.txt"
HORA_DE_CIERRE_DEL_DIA = timedelta(hours=1)  # un día D se calcula desde D+1 a la 01:00 (D-76, punto 5)

# Lo que informa la revisión de un sistema: los cinco contadores son enteros (alertas generadas y resueltas, resúmenes horarios creados o cambiados,
# fotoperíodos calculados y lecturas borradas) y ``error`` es ``None`` o el texto del fallo (el sistema que falla no frena a los demás, D-71 punto 2).
ResumenDeSistema = namedtuple(
    "ResumenDeSistema",
    "sistema alertas_generadas alertas_resueltas resumenes fotoperiodos lecturas_borradas error",
    defaults=(0, 0, 0, 0, 0, None),
)
# Lo que informa el envío de los correos de las alertas críticas.
ResumenDeCorreos = namedtuple("ResumenDeCorreos", "enviados fallidos pendientes_sin_servidor", defaults=(0, 0, 0))


class ResumenDeRevision(namedtuple("ResumenDeRevision", "ahora sistemas correos")):
    """Todo lo que hizo una corrida de ``revisar``: la hora usada, un ``ResumenDeSistema`` por sistema activo (en orden de id) y el de los correos."""

    @property
    def hubo_fallos(self):
        """Verdadero si algún sistema falló (el comando termina con código 1)."""
        return any(resumen.error for resumen in self.sistemas)


class _Cambios:
    """Las alertas que generó y resolvió la revisión de un sistema (para el resumen y la auditoría). Llama a ``alertas_iot`` por el módulo, no por el nombre."""

    def __init__(self, invernadero_id, sistema):
        self.invernadero_id, self.sistema = invernadero_id, sistema
        self.generadas, self.resueltas = [], []

    def asegurar(self, tipo, clave, descripcion, hardware=None):
        resultado = alertas_iot.asegurar_alerta_iot(self.invernadero_id, self.sistema, tipo, clave, descripcion, hardware=hardware)
        if resultado.creada:
            self.generadas.append(resultado.alerta)
        return resultado

    def resolver(self, tipo, clave):
        alerta = alertas_iot.resolver_alerta_iot(self.invernadero_id, tipo, clave)
        if alerta is not None:
            self.resueltas.append(alerta)
        return alerta


def revisar(ahora):
    """Hace la revisión periódica con la hora ``ahora`` (un ``datetime`` con zona; uno ingenuo es ``ValueError``) y devuelve un ``ResumenDeRevision``.

    Lee la Configuración Operativa UNA vez por corrida (regla 7b de ADM-MOD-CFG: los parámetros rigen desde la próxima revisión). Cada sistema activo va en su
    transacción; si uno falla, queda en el resumen con su ``error`` y se sigue con los demás. Los correos van después, fuera de toda transacción."""
    if not isinstance(ahora, datetime) or ahora.utcoffset() is None:
        raise ValueError("`ahora` tiene que ser un datetime con zona horaria.")
    config = configuracion.obtener()
    sistemas = list(SistemaIoT.objects.filter(estado_sistema=SistemaIoT.Estado.ACTIVO).order_by("pk").values_list("pk", "invernadero_id"))
    resumenes = []
    for sistema_id, invernadero_id in sistemas:
        try:
            with transaction.atomic():
                resumenes.append(_revisar_sistema(sistema_id, invernadero_id, ahora, config))
        except Exception as error:  # noqa: BLE001 - un sistema roto no frena a los demás (D-71, punto 2)
            logger.exception("Falló la revisión del sistema IoT %s: %r", sistema_id, error)
            resumenes.append(ResumenDeSistema(SistemaIoT.objects.get(pk=sistema_id), error=f"{type(error).__name__}: {error}"))
    return ResumenDeRevision(ahora, resumenes, enviar_correos_pendientes(ahora))


def enviar_correos_pendientes(ahora):
    """Los correos de las alertas críticas (D-71 punto 3, D-76 punto 7), FUERA de toda transacción: cada alerta crítica y activa con ``correo_enviado_en`` nulo e
    ``intentos_correo`` menor que 5 se manda, en orden de id, a ``_destinatarios_de(alerta)`` con ``core.correo.enviar_correo``. Devuelve un ``ResumenDeCorreos`` (cuenta
    ALERTAS: las enviadas, las que no salieron a nadie y, sin servidor de correo, las pendientes).

    Sin servidor (``correo_configurado()`` falso) no se intenta nada ni se cuentan intentos.

    **Reserva antes de enviar** (decisión de IOT-04, aparte de D-76 punto 7, que carga ``correo_enviado_en`` DESPUÉS de enviar): dos revisiones simultáneas no pueden mandar
    el mismo correo dos veces, y un bloqueo de filas no sirve porque hay que enviar fuera de la transacción (D-14). Por eso la alerta se reserva con un ``UPDATE`` condicional
    (``correo_enviado_en`` nulo y alerta activa → ``correo_enviado_en = ahora``) y quien no logra reservar la salta. Si no salió a nadie, un ``finally`` libera la reserva con
    otro ``UPDATE`` condicional a la marca reservada y suma un intento. Costo aceptado: si el proceso muere entre reservar y enviar, ese correo se pierde (no hay duplicados);
    y mientras dura la reserva el panel muestra «Notificada por correo»."""
    pendientes = (
        AlertaIot.objects.filter(
            alerta__nivel_severidad=Alerta.Severidad.CRITICA,
            alerta__estado_alerta=Alerta.Estado.ACTIVA,
            correo_enviado_en__isnull=True,
            intentos_correo__lt=MAXIMO_DE_INTENTOS,
        )
        .select_related("alerta__invernadero", "alerta__agronomo")
        .order_by("alerta_id")
    )
    if not correo.correo_configurado():
        return ResumenDeCorreos(pendientes_sin_servidor=pendientes.count())
    enviados = fallidos = 0
    for vinculo in list(pendientes):
        resultado = _enviar_correo_de(vinculo, ahora)
        if resultado is True:
            enviados += 1
        elif resultado is False:
            fallidos += 1
    return ResumenDeCorreos(enviados, fallidos)


def _destinatarios_de(alerta):
    """Las cuentas a las que va el correo de ``alerta``, según sus campos AL ENVIARSE (D-76 punto 7; así sigue los traspasos de D-41 sin lógica propia): con ``para_gerente``,
    cada Gerente activo con email; si no, el Agrónomo de la alerta si su cuenta está activa y tiene email."""
    if alerta.para_gerente:
        return list(Gerente.objects.filter(is_active=True).exclude(email="").order_by("pk"))
    agronomo = alerta.agronomo
    return [agronomo] if agronomo is not None and agronomo.is_active and agronomo.email else []


def _enviar_correo_de(vinculo, ahora):
    """Manda el correo de UNA alerta crítica. Devuelve ``None`` si otra revisión la reservó antes, ``True`` si salió al menos a un destinatario y ``False`` si no salió a nadie.
    El ``finally`` libera la reserva y suma el intento aunque algo falle; al quinto intento deja un ``logger.error`` con el id de la alerta."""
    alerta = vinculo.alerta
    reservada = AlertaIot.objects.filter(
        pk=vinculo.pk, correo_enviado_en__isnull=True, alerta__estado_alerta=Alerta.Estado.ACTIVA
    ).update(correo_enviado_en=ahora)
    if not reservada:
        return None
    salio = False
    try:
        destinatarios = _destinatarios_de(alerta)
        if not destinatarios:
            logger.warning("La alerta %s no tiene destinatarios para el correo (ninguna cuenta activa con email).", alerta.pk)
        contexto = {
            "tipo": api_alertas.nombre_de_tipo(alerta),
            "invernadero": alerta.invernadero.nombre_invernadero,
            "descripcion": alerta.descripcion_alerta,
            "fecha": timezone.localtime(alerta.fecha_hora_alerta).strftime("%d/%m/%Y %H:%M"),
        }
        asunto = f"Alerta crítica: {contexto['tipo']} · {contexto['invernadero']}"
        for cuenta in destinatarios:
            try:
                salio = bool(correo.enviar_correo(cuenta, asunto, PLANTILLA_DEL_CORREO, contexto)) or salio
            except Exception:  # noqa: BLE001 - una falla con un destinatario no frena a los demás ni a las otras alertas
                logger.exception("Falló el correo de la alerta %s a la cuenta %s.", alerta.pk, cuenta.pk)
    finally:
        if not salio:
            _liberar_reserva(vinculo.pk, ahora)
    return salio


def _liberar_reserva(vinculo_id, marca):
    """Libera la reserva (``correo_enviado_en`` nulo) y suma un intento, solo si la marca sigue siendo la reservada; al quinto intento, ``logger.error``."""
    AlertaIot.objects.filter(pk=vinculo_id, correo_enviado_en=marca).update(correo_enviado_en=None, intentos_correo=F("intentos_correo") + 1)
    vinculo = AlertaIot.objects.get(pk=vinculo_id)
    if vinculo.correo_enviado_en is None and vinculo.intentos_correo >= MAXIMO_DE_INTENTOS:
        logger.error("El correo de la alerta %s no salió en %s intentos: no se vuelve a intentar.", vinculo.alerta_id, MAXIMO_DE_INTENTOS)


def _bloquear_equipos(sistema_id):
    """Bloquea (``FOR NO KEY UPDATE``) el nodo y los sensores no dados de baja del sistema, en orden de id, y los devuelve ya releídos. Va DESPUÉS del invernadero y del sistema: es el orden de la API
    (invernadero → sistema → equipo, docs/api/alertas.md, sección 3); con otro orden, una lectura y una revisión sobre el mismo sensor se cruzan (deadlock). Es una función con nombre para que
    la prueba de concurrencia pueda detener la revisión justo antes de tomar estos bloqueos."""
    nodo = NodoCentral.objects.select_for_update(no_key=True).get(sistema_id=sistema_id)
    sensores = list(
        Sensor.objects.select_for_update(no_key=True, of=("self",))
        .select_related("sector")
        .filter(sistema_id=sistema_id)
        .exclude(estado_hardware="inactivo")
        .order_by("pk")
    )
    return nodo, sensores


def _revisar_sistema(sistema_id, invernadero_id, ahora, config):
    """Los seis pasos de *b para un sistema, ya dentro de su transacción. Si al bloquearlo dejó de estar activo, no hace nada."""
    api_alertas.bloquear_invernadero_para_alertas(invernadero_id)
    sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=sistema_id)
    resumen = ResumenDeSistema(sistema)
    if sistema.estado_sistema != SistemaIoT.Estado.ACTIVO:
        return resumen
    nodo, sensores = _bloquear_equipos(sistema_id)
    cambios = _Cambios(invernadero_id, sistema)
    _sensores_sin_actividad(cambios, sensores, ahora, config)
    _nodo_sin_comunicacion(cambios, nodo, ahora, config)
    _no_registrados_sin_mensajes(cambios, sistema, ahora, config)
    resumenes = _resumenes_horarios(sensores, ahora)
    fotoperiodos = _fotoperiodos(cambios, sensores, ahora, config)
    borradas = _retencion(sistema, ahora, config)
    if cambios.generadas or cambios.resueltas or borradas:
        _auditar(sistema, ahora, cambios, borradas)
    return resumen._replace(
        alertas_generadas=len(cambios.generadas),
        alertas_resueltas=len(cambios.resueltas),
        resumenes=resumenes,
        fotoperiodos=fotoperiodos,
        lecturas_borradas=borradas,
    )


def _desde(momento):
    """«desde las HH:MM del DD/MM», en la hora local (D-76 punto 4: la zona del proyecto)."""
    local = timezone.localtime(momento)
    return f"desde las {local:%H:%M} del {local:%d/%m}"


# ---- *b.1, *b.2 y *b.3: las alertas por tiempo ----


def _sensores_sin_actividad(cambios, sensores, ahora, config):
    """*b.1 (D-76 punto 1): un sensor ACTIVO con ``ultimo_mensaje_en`` no nulo y anterior a ``ahora − minutos_sin_actividad`` genera «dispositivo sin actividad».
    Los «sin confirmar» (nulo) no. La resuelven los mensajes del nodo (IOT-03), no la revisión."""
    limite = ahora - timedelta(minutes=config.minutos_sin_actividad)
    for sensor in sensores:
        if sensor.estado_hardware == "activo" and sensor.ultimo_mensaje_en is not None and sensor.ultimo_mensaje_en < limite:
            descripcion = f"{sensor.identificador_equipo} · sin lecturas {_desde(sensor.ultimo_mensaje_en)}"
            cambios.asegurar(TIPO_SIN_ACTIVIDAD, f"hw:{sensor.pk}", descripcion, hardware=sensor)


def _nodo_sin_comunicacion(cambios, nodo, ahora, config):
    """*b.2 (D-76 punto 2): con ``ultima_comunicacion`` no nula y anterior a ``ahora − minutos_sin_comunicacion``, «nodo sin comunicación» (crítica; sin hardware ni
    telemetría de origen). La resuelve el próximo mensaje aceptado (IOT-03, postcondición a)."""
    limite = ahora - timedelta(minutes=config.minutos_sin_comunicacion)
    if nodo.ultima_comunicacion is not None and nodo.ultima_comunicacion < limite:
        cambios.asegurar(TIPO_NODO_SIN_COMUNICACION, f"nodo:{nodo.pk}", f"{nodo.nombre_nodo} · sin comunicación {_desde(nodo.ultima_comunicacion)}")


def _no_registrados_sin_mensajes(cambios, sistema, ahora, config):
    """*b.3 (D-76 punto 3): la alerta «dispositivo no registrado» cuyo último mensaje rechazado es anterior a ``ahora − minutos_sin_actividad`` pasa a «resuelta»."""
    limite = ahora - timedelta(minutes=config.minutos_sin_actividad)
    vinculos = (
        AlertaIot.objects.filter(
            sistema=sistema,
            alerta__tipo_alerta=TIPO_NO_REGISTRADO,
            alerta__estado_alerta=Alerta.Estado.ACTIVA,
            ultimo_mensaje_en__lt=limite,
        )
        .select_related("alerta")
        .order_by("alerta_id")
    )
    for vinculo in vinculos:
        cambios.resolver(TIPO_NO_REGISTRADO, vinculo.alerta.clave_estado)


# ---- *b.4: resúmenes horarios ----


def _dos(valor):
    """``valor`` con dos decimales, el medio hacia arriba; ``None`` si no hay."""
    return None if valor is None else Decimal(valor).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def _resumenes_horarios(sensores, ahora):
    """*b.4 (D-76 punto 4): por sensor (menos los de nivel) y por hora, mínimo, promedio y máximo de las lecturas VÁLIDAS (nulos si no hubo), cantidad de lecturas (todas)
    y de inválidas. Recalcula siempre la hora en curso y las dos anteriores, y toda hora con lecturas que todavía no tenga resumen. Las lecturas se leen con UNA
    agregación por sensor y hora (``TruncHour``), no con una consulta por hora; la retención las acota. Devuelve cuántos resúmenes creó o cambió."""
    ids = [s.pk for s in sensores if s.tipo_variable_sensor != "nivel_solucion"]
    if not ids:
        return 0
    zona = timezone.get_current_timezone()
    hora_actual = timezone.localtime(ahora).replace(minute=0, second=0, microsecond=0)
    recientes = {hora_actual - timedelta(hours=n) for n in range(HORAS_QUE_SE_RECALCULAN)}
    filas = list(
        Telemetria.objects.filter(sensor_id__in=ids)
        .annotate(hora=TruncHour("medida_en", tzinfo=zona))
        .values("sensor_id", "hora")
        .annotate(
            minimo=Min("valor_medido", filter=Q(valida=True)),
            promedio=Avg("valor_medido", filter=Q(valida=True)),
            maximo=Max("valor_medido", filter=Q(valida=True)),
            cantidad=Count("pk"),
            invalidas=Count("pk", filter=Q(valida=False)),
        )
        .order_by("sensor_id", "hora")
    )
    if not filas:
        return 0
    existentes = {
        (r.sensor_id, r.hora): r for r in ResumenHorario.objects.filter(sensor_id__in=ids, hora__gte=min(f["hora"] for f in filas))
    }
    cambiados = 0
    for fila in filas:
        previo = existentes.get((fila["sensor_id"], fila["hora"]))
        if previo is not None and fila["hora"] not in recientes:
            continue  # una hora vieja que ya tiene resumen no se toca
        valores = {
            "minimo": _dos(fila["minimo"]),
            "promedio": _dos(fila["promedio"]),
            "maximo": _dos(fila["maximo"]),
            "cantidad_lecturas": fila["cantidad"],
            "cantidad_invalidas": fila["invalidas"],
        }
        if previo is not None and all(getattr(previo, campo) == valor for campo, valor in valores.items()):
            continue
        ResumenHorario.objects.update_or_create(sensor_id=fila["sensor_id"], hora=fila["hora"], defaults=valores)
        cambiados += 1
    return cambiados


# ---- *b.5: fotoperíodo ----


def _dia_cerrado_mas_reciente(ahora):
    """El último día local que ya se puede calcular (D-76 punto 5): D se calcula con ``ahora ≥ D+1 a la 01:00``; el día en curso nunca."""
    return (timezone.localtime(ahora) - HORA_DE_CIERRE_DEL_DIA).date() - timedelta(days=1)


def _medianoche(dia):
    """La medianoche local que abre ``dia``."""
    return datetime.combine(dia, time.min, tzinfo=timezone.get_current_timezone())


def _calcular_fotoperiodo(sensor, dia, config):
    """``(horas, incompleto)`` del ``dia`` (D-76 punto 5): se toman las lecturas válidas del día en orden; por cada par consecutivo (a, b) con ``b − a`` dentro de los
    minutos sin actividad, si el valor de ``a`` supera el umbral de luz se suma ``b − a``. El día es ``incompleto`` si no tiene lecturas válidas, si dos seguidas están
    más separadas que ese plazo o si la primera o la última están a más de ese plazo del borde del día."""
    plazo = timedelta(minutes=config.minutos_sin_actividad)
    inicio, fin = _medianoche(dia), _medianoche(dia + timedelta(days=1))
    lecturas = list(
        Telemetria.objects.filter(sensor=sensor, valida=True, medida_en__gte=inicio, medida_en__lt=fin)
        .order_by("medida_en")
        .values_list("medida_en", "valor_medido")
    )
    if not lecturas:
        return Decimal("0.00"), True
    incompleto = lecturas[0][0] - inicio > plazo or fin - lecturas[-1][0] > plazo
    luz = timedelta(0)
    for (antes, valor), (despues, _) in zip(lecturas, lecturas[1:]):
        if despues - antes > plazo:
            incompleto = True
        elif valor > config.lux_umbral_fotoperiodo:
            luz += despues - antes
    return _dos(Decimal(luz.total_seconds()) / 3600), incompleto


def _fotoperiodos(cambios, sensores, ahora, config):
    """*b.5 (D-76 punto 5): para cada sensor de intensidad lumínica no dado de baja, los días cerrados con lecturas y sin ``FotoperiodoDiario``, en orden de fecha
    (también si es incompleto). Si el día es completo, el invernadero tiene umbral efectivo con fotoperíodo, el sensor está activo y su sector no está fuera de
    servicio, se compara (sin histéresis): fuera genera la alerta, dentro la resuelve. Un día incompleto o sin umbral no toca la alerta. Devuelve cuántos calculó."""
    luces = [s for s in sensores if s.tipo_variable_sensor == "intensidad_luz"]
    if not luces:
        return 0
    zona = timezone.get_current_timezone()
    ultimo = _dia_cerrado_mas_reciente(ahora)
    con_lecturas = (
        Telemetria.objects.filter(sensor__in=luces)
        .annotate(dia=TruncDate("medida_en", tzinfo=zona))
        .filter(dia__lte=ultimo)
        .values_list("sensor_id", "dia")
        .order_by()  # sin el orden por omisión del modelo: entraría al DISTINCT
        .distinct()
    )
    calculados = set(FotoperiodoDiario.objects.filter(sensor__in=luces).values_list("sensor_id", "fecha"))
    pendientes = sorted(par for par in con_lecturas if par not in calculados)
    if not pendientes:
        return 0
    por_id = {s.pk: s for s in luces}
    fotoperiodo = None
    if cambios.invernadero_id is not None:
        umbral = umbral_efectivo([cambios.invernadero_id])[cambios.invernadero_id]
        fotoperiodo = umbral.fotoperiodo if umbral is not None else None
    for sensor_id, dia in pendientes:
        sensor = por_id[sensor_id]
        horas, incompleto = _calcular_fotoperiodo(sensor, dia, config)
        FotoperiodoDiario.objects.create(sensor=sensor, fecha=dia, horas=horas, incompleto=incompleto)
        en_sector_fuera = sensor.sector is not None and sensor.sector.estado_sector == "fuera_de_servicio"
        if incompleto or fotoperiodo is None or sensor.estado_hardware != "activo" or en_sector_fuera:
            continue
        clave = f"sensor:{sensor.pk}"
        if horas < fotoperiodo.minimo:
            limite, palabra = fotoperiodo.minimo, "mínimo"
        elif horas > fotoperiodo.maximo:
            limite, palabra = fotoperiodo.maximo, "máximo"
        else:
            cambios.resolver(TIPO_FOTOPERIODO, clave)
            continue
        descripcion = f"{sensor.identificador_equipo} · {numero_legible(horas)} h de luz el {dia:%d/%m} ({palabra} efectivo {numero_legible(limite)} h)"
        cambios.asegurar(TIPO_FOTOPERIODO, clave, descripcion, hardware=sensor)
    return len(pendientes)


# ---- *b.6: retención ----


def _retencion(sistema, ahora, config):
    """*b.6 (D-76 punto 6): borra las lecturas del sistema anteriores a la medianoche local de hoy menos los días de retención, salvo las que tienen un ``AlertaIot`` o
    están en ``ReglaActuacion.telemetrias``. Va DESPUÉS de los resúmenes y los fotoperíodos de la misma corrida, para que nada se borre sin resumir. Los resúmenes y los
    fotoperíodos no se borran nunca. Devuelve cuántas lecturas borró."""
    corte = _medianoche(timezone.localtime(ahora).date() - timedelta(days=config.dias_retencion_telemetria))
    vencidas = Telemetria.objects.filter(
        sensor__sistema=sistema, medida_en__lt=corte, alertas_iot__isnull=True, reglas_que_disparo__isnull=True
    )
    _, por_modelo = vencidas.delete()
    return por_modelo.get("iot.Telemetria", 0)


# ---- auditoría (postcondición z) ----


def _auditar(sistema, ahora, cambios, borradas):
    """Un registro ``revision_periodica_iot`` por sistema y corrida (actor ``None``), solo si generó o resolvió alertas o borró lecturas. Los afectados son las alertas;
    los resúmenes, los fotoperíodos y los correos no se auditan uno por uno. ``ahora`` va como texto: un ``datetime`` no es un valor permitido (D-36)."""
    afectados = list({alerta.pk: alerta for alerta in [*cambios.generadas, *cambios.resueltas]}.values())
    datos = {
        "origen": "revision_periodica",
        "sistema": referencia(sistema),
        "ahora": ahora.isoformat(),
        "alertas_generadas": [referencia(alerta) for alerta in cambios.generadas],
        "alertas_resueltas": [referencia(alerta) for alerta in cambios.resueltas],
        "lecturas_borradas": borradas,
    }
    RegistroAuditoria.objects.registrar(None, RegistroAuditoria.Accion.REVISION_PERIODICA_IOT, afectados, {"datos": datos})
