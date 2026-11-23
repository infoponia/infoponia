# Lecturas del nodo (IOT-03; IOT-ENT-INF pasos 3 a 5 y extensiones 3a a 5g; docs/casos_de_uso/iot/entregar_informacion.md, «Una lectura»; D-74 y D-75).
# ``registrar_lectura`` hace los 11 pasos de «Una lectura» dentro de UNA transacción por lectura. ``contexto_del_mensaje`` calcula UNA vez por pedido los
# parámetros de la Configuración Operativa y el umbral efectivo (una sola función del dominio: ``inventario.servicios.variedades.umbral_efectivo``).
# Bloqueos (``FOR NO KEY UPDATE``): invernadero → sistema (releído) → sensor. Todas las funciones reciben ``ahora``: nunca leen la hora por su cuenta.

from collections import namedtuple
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from inventario.servicios.variedades import umbral_efectivo
from iot.models import AlertaIot, Hardware, Sensor, SistemaIoT, Telemetria
from iot.servicios import alertas_iot
from iot.servicios.auditoria_nodo import auditar_entrega
from iot.textos import valor_legible
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion

TOLERANCIA_FUTURA = timedelta(minutes=5)  # extensión 3d
LIMITE_DEL_VALOR = Decimal("9999999.99")  # D-74, punto 7
DOS_DECIMALES = Decimal("0.01")
# Variable del sensor -> variable del umbral efectivo y parámetro de histéresis de la Configuración Operativa.
VARIABLES_DEL_UMBRAL = {
    "temperatura": ("temp_ambiente", "histeresis_temperatura"),
    "humedad": ("humedad", "histeresis_humedad"),
    "intensidad_luz": ("intensidad_luz", "histeresis_luz"),
}

ContextoDeLecturas = namedtuple("ContextoDeLecturas", "sistema_id invernadero_id config umbral")
ResultadoDeLectura = namedtuple("ResultadoDeLectura", "resultado valida atrasada motivo detalle", defaults=(None, None, None, ""))


def contexto_del_mensaje(sistema, ahora):
    """Lo que comparten todas las lecturas de un pedido: los parámetros de la Configuración Operativa y el umbral efectivo del invernadero (``None`` si no
    tiene variedades presentes, extensión 5c). Se calcula una sola vez por pedido."""
    umbral = umbral_efectivo([sistema.invernadero_id])[sistema.invernadero_id]
    return ContextoDeLecturas(sistema.pk, sistema.invernadero_id, configuracion.obtener(), umbral)


def tiene_lecturas(sensor):
    """Regla 3 de IOT-MOD-HDW: el sensor ya tiene lecturas."""
    return Telemetria.objects.filter(sensor_id=sensor.pk).exists()


def evaluar_reglas_de_la_lectura(contexto, sensor, telemetria):
    """Paso 6 y extensiones 6a a 6d: evalúa las reglas de actuación del sensor con esta lectura. **Se completa en IOT-06**: hasta entonces no hace nada."""
    return None


def _ya_existe_la_lectura(sensor, medida_en):
    """D-74, punto 6: ya hay una lectura de ese sensor con esa ``medida_en`` (el índice único de la base respalda)."""
    return Telemetria.objects.filter(sensor_id=sensor.pk, medida_en=medida_en).exists()


def _rechazo(motivo, detalle):
    return ResultadoDeLectura("rechazada", None, None, motivo, detalle)


def _valor_recibido(valor):
    """El valor recibido tal como se muestra en «dispositivo no registrado»."""
    return valor_legible(valor) if isinstance(valor, (int, Decimal)) and not isinstance(valor, bool) else str(valor)


def _fecha(medida_en, ahora):
    """Paso 3 (extensiones 3d y 3e; D-74 punto 5): ``(fecha, None)`` o ``(None, ResultadoDeLectura rechazado)``."""
    if medida_en is None:
        return ahora, None
    if not isinstance(medida_en, str):
        return None, _rechazo("fecha_invalida", "La fecha tiene que ser un texto ISO 8601 con zona horaria.")
    try:
        fecha = datetime.fromisoformat(medida_en)
    except ValueError:
        fecha = None
    if fecha is None or fecha.tzinfo is None:
        return None, _rechazo("fecha_invalida", f"«{medida_en}» no es una fecha ISO 8601 con zona horaria.")
    if fecha > ahora + TOLERANCIA_FUTURA:
        return None, _rechazo("fecha_futura", f"La fecha {medida_en} es más de 5 minutos posterior a la hora de InfoPonia.")
    return fecha, None


def _valor(sensor, valor):
    """Paso 4 (extensión 4c; D-74 punto 7): ``(valor normalizado, None)`` o ``(None, rechazo)``. El nivel admite «normal» o «bajo»; lo demás, un número."""
    if sensor.tipo_variable_sensor == "nivel_solucion":
        if isinstance(valor, str) and valor in ("normal", "bajo"):
            return valor, None
        return None, _rechazo("valor_invalido", "El nivel de la solución solo admite «normal» o «bajo».")
    if isinstance(valor, bool) or not isinstance(valor, (int, Decimal)):
        return None, _rechazo("valor_invalido", "El valor tiene que ser un número.")
    numero = Decimal(valor).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
    if abs(numero) > LIMITE_DEL_VALOR:
        return None, _rechazo("valor_invalido", "El valor pasa del máximo admitido (9.999.999,99).")
    return numero, None


def _equipo_de(sistema_id, identificador):
    """Paso 2: el equipo NO dado de baja del sistema con ese identificador (sin distinguir mayúsculas), o ``None``; y si no hay, si lo hubo dado de baja."""
    del_sistema = Hardware.objects.filter(sistema_id=sistema_id).annotate(_minuscula=Lower("identificador_equipo")).filter(_minuscula=identificador.lower())
    vigente = del_sistema.exclude(estado_hardware="inactivo").first()
    return vigente, vigente is None and del_sistema.filter(estado_hardware="inactivo").exists()


def _histeresis(valor_configurado, minimo, maximo):
    """D-75, punto 2: la menor entre la histéresis y la mitad del ancho del rango."""
    return min(Decimal(str(valor_configurado)), (maximo - minimo) / 2)


class _Cambios:
    """Las alertas generadas y resueltas por una lectura (para la auditoría)."""

    def __init__(self, invernadero_id, sistema):
        self.invernadero_id, self.sistema = invernadero_id, sistema
        self.generadas, self.resueltas = [], []

    def asegurar(self, tipo, clave, descripcion, hardware=None, telemetria=None):
        resultado = alertas_iot.asegurar_alerta_iot(self.invernadero_id, self.sistema, tipo, clave, descripcion, hardware, telemetria)
        if resultado.creada:
            self.generadas.append(resultado.alerta)
        return resultado

    def resolver(self, tipo, clave):
        alerta = alertas_iot.resolver_alerta_iot(self.invernadero_id, tipo, clave)
        if alerta is not None:
            self.resueltas.append(alerta)
        return alerta


def _comparar(cambios, sensor, telemetria, valor, minimo, maximo, histeresis, tipo, clave, rotulo, unidad):
    """Compara ``valor`` con ``[minimo, maximo]``: fuera genera la alerta, dentro y a más de la histéresis de cada límite la resuelve; en la franja, la deja."""
    if valor > maximo or valor < minimo:
        limite, palabra = (maximo, "máximo") if valor > maximo else (minimo, "mínimo")
        descripcion = f"{sensor.identificador_equipo} · {valor_legible(valor, unidad)} ({palabra} {rotulo} {valor_legible(limite, unidad)})"
        cambios.asegurar(tipo, clave, descripcion, telemetria=telemetria)
    elif minimo + histeresis <= valor <= maximo - histeresis:
        cambios.resolver(tipo, clave)


def _despues_de_guardar(contexto, sistema, sensor, telemetria, valor, medida_en, ahora, cambios):
    """Pasos 7 a 10: lo que pasa con una lectura ya guardada. Devuelve ``(valida, atrasada)``."""
    config = contexto.config
    nivel = sensor.tipo_variable_sensor == "nivel_solucion"
    valida = None if nivel else sensor.valor_calibracion_min <= valor <= sensor.valor_calibracion_max
    atrasada = medida_en < ahora - timedelta(minutes=config.minutos_antiguedad_lectura)
    if atrasada or sensor.estado_hardware == "fuera_de_servicio":  # extensiones 3f y 3c
        return valida, atrasada
    clave_hw, clave_sensor = f"hw:{sensor.pk}", f"sensor:{sensor.pk}"
    if valida is False:  # extensión 4a
        minimo, maximo = valor_legible(sensor.valor_calibracion_min), valor_legible(sensor.valor_calibracion_max)
        descripcion = f"{sensor.identificador_equipo} · {valor_legible(valor, sensor.unidad_medida)}, fuera de la calibración ({minimo} a {maximo})"
        cambios.asegurar("iot_lectura_invalida", clave_hw, descripcion, hardware=sensor)
        return valida, atrasada
    cambios.resolver("iot_lectura_invalida", clave_hw)  # extensión 4b
    variable = sensor.tipo_variable_sensor
    if nivel:  # extensión 5g
        if valor == "bajo":
            cambios.asegurar("iot_nivel_solucion_bajo", clave_sensor, f"{sensor.identificador_equipo} · informa «bajo»", telemetria=telemetria)
        else:
            cambios.resolver("iot_nivel_solucion_bajo", clave_sensor)
    elif variable == "temperatura_solucion":  # extensión 5f: se compara con el rango del sistema; no admite reglas
        if sistema.temp_solucion_min is not None:
            minimo, maximo = sistema.temp_solucion_min, sistema.temp_solucion_max
            h = _histeresis(config.histeresis_temp_solucion, minimo, maximo)
            _comparar(cambios, sensor, telemetria, valor, minimo, maximo, h, "iot_solucion_fuera_de_rango", clave_sensor, "de la solución", sensor.unidad_medida)
    else:  # temperatura, humedad e intensidad lumínica (extensiones 5a a 5e)
        if variable == "intensidad_luz":
            hora = timezone.localtime(medida_en).hour
            if hora < config.hora_inicio_luz or hora >= config.hora_fin_luz:  # 5e
                return valida, atrasada
        if sensor.sector is not None and sensor.sector.estado_sector == "fuera_de_servicio":  # 5d, D-75 punto 7
            return valida, atrasada
        nombre_umbral, parametro = VARIABLES_DEL_UMBRAL[variable]
        limites = getattr(contexto.umbral, nombre_umbral) if contexto.umbral is not None else None
        if limites is None:  # 5c y D-75 puntos 3 y 4
            cambios.resolver("iot_fuera_de_umbral", clave_sensor)
            return valida, atrasada
        h = _histeresis(getattr(config, parametro), limites.minimo, limites.maximo)
        _comparar(cambios, sensor, telemetria, valor, limites.minimo, limites.maximo, h, "iot_fuera_de_umbral", clave_sensor, "efectivo", sensor.unidad_medida)
        evaluar_reglas_de_la_lectura(contexto, sensor, telemetria)  # paso 6 (IOT-06)
    return valida, atrasada


def registrar_lectura(contexto, lectura, ahora):
    """Los 11 pasos de «Una lectura» para ``lectura`` (una ``LecturaRecibida``) en su propia transacción. Devuelve un ``ResultadoDeLectura``: ``aceptada`` (con
    ``valida`` y ``atrasada``), ``duplicada`` o ``rechazada`` con su ``motivo`` y ``detalle``."""
    with transaction.atomic():
        api_alertas.bloquear_invernadero_para_alertas(contexto.invernadero_id)
        sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=contexto.sistema_id)
        if sistema.estado_sistema != SistemaIoT.Estado.ACTIVO:  # paso 1
            return _rechazo("sistema_desconectado", "El sistema IoT se desconectó mientras se procesaba el pedido.")
        cambios = _Cambios(contexto.invernadero_id, sistema)
        equipo, era_de_baja = _equipo_de(sistema.pk, lectura.identificador)
        if equipo is None:  # paso 2, extensión 3a y postcondición t
            return _no_registrado(cambios, sistema, lectura, era_de_baja, ahora)
        if equipo.clase != "sensor":  # extensión 3b
            return _rechazo("no_es_sensor", f"«{lectura.identificador_enviado}» es un actuador: las lecturas son solo de sensores.")
        sensor = Sensor.objects.select_for_update(no_key=True, of=("self",)).select_related("sector").get(pk=equipo.pk)
        medida_en, rechazo = _fecha(lectura.medida_en, ahora)  # paso 3
        if rechazo:
            return rechazo
        valor, rechazo = _valor(sensor, lectura.valor)  # paso 4
        if rechazo:
            return rechazo
        if _ya_existe_la_lectura(sensor, medida_en):  # paso 5
            return ResultadoDeLectura("duplicada")
        nivel = sensor.tipo_variable_sensor == "nivel_solucion"
        try:
            with transaction.atomic():  # punto de guardado: el IntegrityError no rompe la transacción
                telemetria = Telemetria.objects.create(
                    sensor=sensor,
                    medida_en=medida_en,
                    valor_medido=None if nivel else valor,
                    estado_nivel_medido=valor if nivel else None,
                    unidad_medida_telemetria=None if nivel else sensor.unidad_medida,
                    valida=None if nivel else sensor.valor_calibracion_min <= valor <= sensor.valor_calibracion_max,
                )
        except IntegrityError:
            return ResultadoDeLectura("duplicada")
        Hardware.objects.filter(pk=sensor.pk).update(ultimo_mensaje_en=ahora)  # paso 6
        cambios.resolver("iot_dispositivo_sin_actividad", f"hw:{sensor.pk}")
        valida, atrasada = _despues_de_guardar(contexto, sistema, sensor, telemetria, valor, medida_en, ahora, cambios)
        if cambios.generadas or cambios.resueltas:  # paso 11
            auditar_entrega(sistema, "lectura", lectura.identificador, [sensor], None, cambios.generadas, cambios.resueltas)
        return ResultadoDeLectura("aceptada", valida, atrasada)


def _no_registrado(cambios, sistema, lectura, era_de_baja, ahora):
    """Extensión 3a y postcondición t: rechaza la lectura y genera (o encuentra) la alerta «dispositivo no registrado» de ese identificador, sin hardware ni
    telemetría, y anota el último mensaje rechazado (D-76, punto 3)."""
    descripcion = f"El nodo envió una lectura de «{lectura.identificador}» ({_valor_recibido(lectura.valor)}), que no está registrado."
    resultado = cambios.asegurar("iot_dispositivo_no_registrado", f"id:{lectura.identificador.lower()}", descripcion)
    if resultado.alerta is not None:
        AlertaIot.objects.filter(alerta=resultado.alerta).update(ultimo_mensaje_en=ahora)
    if cambios.generadas:
        auditar_entrega(sistema, "lectura", lectura.identificador, [], None, cambios.generadas, [])
    if era_de_baja:
        return _rechazo("equipo_dado_de_baja", f"«{lectura.identificador_enviado}» era de un equipo dado de baja de este sistema IoT.")
    return _rechazo("equipo_no_registrado", f"«{lectura.identificador_enviado}» no es un equipo registrado de este sistema IoT.")
