# Lecturas del nodo (IOT-03; IOT-ENT-INF pasos 3 a 5 y extensiones 3a a 5g; docs/casos_de_uso/iot/entregar_informacion.md, «Una lectura»; D-74 y D-75).
# ``registrar_lectura`` hace los 11 pasos de «Una lectura» dentro de UNA transacción por lectura. ``contexto_del_mensaje`` calcula UNA vez por pedido los
# parámetros de la Configuración Operativa y el umbral efectivo (una sola función del dominio: ``inventario.servicios.variedades.umbral_efectivo``).
# Bloqueos (``FOR NO KEY UPDATE``): invernadero → sistema (releído) → sensor y, si una regla confirma, los actuadores de las reglas (en orden de id: D-78, punto 11). El disparo
# de las reglas (paso 6, IOT-06) corre en la transacción de la lectura. Todas las funciones reciben ``ahora``: nunca leen la hora por su cuenta.

from collections import namedtuple
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from inventario.servicios.variedades import umbral_efectivo
from iot.models import Actuador, AlertaIot, Comando, Hardware, NodoCentral, RegistroComando, ReglaActuacion, Sensor, SistemaIoT, Telemetria
from iot.servicios import alertas_iot, comandos, reglas
from iot.servicios.auditoria_nodo import auditar_entrega
from iot.textos import valor_legible
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion

TOLERANCIA_FUTURA = timedelta(minutes=5)  # extensión 3d
LARGO_DE_LA_DESCRIPCION = Comando._meta.get_field("descripcion_comando").max_length
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


def _cumple(regla, valor, minimo, maximo, histeresis):
    """D-78, punto 8, «Cuándo se cumple»: si la regla venía «cumplida», sigue cumpliéndose hasta que la lectura se aleja del límite más que la histéresis; si no, se cumple con
    la lectura del otro lado del límite (en «vuelve al rango», a más de la histéresis de cada límite)."""
    venia = regla.ultima_evaluacion == ReglaActuacion.Evaluacion.CUMPLIDA
    if regla.condicion == ReglaActuacion.Condicion.SUPERA_MAXIMO:
        return valor >= maximo - histeresis if venia else valor > maximo
    if regla.condicion == ReglaActuacion.Condicion.BAJA_DEL_MINIMO:
        return valor <= minimo + histeresis if venia else valor < minimo
    return minimo <= valor <= maximo if venia else minimo + histeresis <= valor <= maximo - histeresis


def _motivo_de_ocupado(actuador, accion, valor, ahora):
    """Extensión 6a.1a y regla «Actuador ocupado»: por qué la regla no puede emitir ahora (el actuador tiene un comando pendiente, no está activo, la acción ya no es válida o es
    incompatible con el nodo —``validar_comando``— o no pasó el tiempo mínimo entre comandos de su tipo desde el último comando EJECUTADO, D-78 punto 7), o ``None`` si está libre."""
    if Comando.objects.filter(actuador=actuador, estado_comando=Comando.Estado.PENDIENTE).exists():
        return "El actuador tiene un comando pendiente."
    if actuador.estado_hardware != Actuador.Estado.ACTIVO:
        return "El actuador no está activo."
    errores = comandos.validar_comando(actuador, accion, valor)
    if errores:
        return next(iter(errores.values()))[0].message
    ultimo = Comando.objects.filter(actuador=actuador, estado_comando=Comando.Estado.EJECUTADO).order_by("-resuelto_en").first()
    minimo = actuador.tipo_actuador.tiempo_minimo_entre_comandos
    if ultimo is not None and minimo > 0 and (ahora - ultimo.resuelto_en).total_seconds() < minimo:
        return "No pasó el tiempo mínimo entre comandos del actuador."
    return None


def _descripcion_del_comando(regla):
    """D-78, punto 9: «Regla {id}: cuando {sensor} {condición}, {acción}[ {valor} {unidad}].», hasta 300 caracteres."""
    sensor, accion = regla.sensor, regla.accion
    valor = f" {regla.aplicar_valor} {accion.unidad_valor}" if regla.aplicar_valor is not None else ""
    condicion = reglas.TEXTO_DE_CONDICION[regla.condicion]
    texto = f"Regla {regla.pk}: cuando {sensor.get_tipo_variable_sensor_display()} {sensor.identificador_equipo} {condicion}, {accion.nombre_accion}{valor}."
    return texto[:LARGO_DE_LA_DESCRIPCION]


def _emitir(regla, actuador, telemetria, ahora):
    """Postcondiciones j a l: el comando automático, su registro de bitácora y la lectura en ``regla.telemetrias``. Devuelve ``(comando, registro)`` o ``None`` si la base rechazó el
    pendiente (otra regla o una persona emitió a la vez: el índice único «un pendiente por actuador» respalda al chequeo, y la regla queda ocupada)."""
    try:
        with transaction.atomic():  # punto de guardado: el IntegrityError no rompe la transacción de la lectura
            comando = Comando.objects.create(
                actuador=actuador,
                accion=regla.accion,
                regla=regla,
                agronomo=None,
                emitido_en=ahora,
                estado_comando=Comando.Estado.PENDIENTE,
                valor_comando=regla.aplicar_valor,
                descripcion_comando=_descripcion_del_comando(regla),
                cantidad_intentos=0,
            )
    except IntegrityError as error:
        if "comando_un_pendiente_por_actuador" in str(error):
            return None
        raise
    registro = comandos.registrar_hecho(comando, RegistroComando.Resultado.EMITIDO, ahora, responsable=None, que_paso=f"emitido por la regla RGL-{regla.pk}")
    regla.telemetrias.add(telemetria)
    return comando, registro


def evaluar_reglas_de_la_lectura(contexto, sensor, telemetria, ahora):
    """Paso 6 y extensiones 6a a 6d (D-78, puntos 8 y 9): evalúa, lectura por lectura, las reglas ACTIVAS del sensor, en orden de id, con la histéresis de la variable acotada como en
    D-75 (punto 2), y guarda su última evaluación y su contador (postcondición i). Devuelve los comandos y registros de bitácora creados, para la auditoría de la lectura.

    - 6d: con el nodo en modo «local» no toca nada.
    - 6c: la condición se cumple y falta confirmar: suma uno al contador. 6b: ya se cumplía: no emite. Una lectura que no cumple vuelve el contador a cero.
    - 6a: al completar la confirmación, bloquea los actuadores de esas reglas (en orden de id) y emite si no están ocupados (``_motivo_de_ocupado``). 6a.1a: si lo están, la regla
      queda «no cumplida» con el contador EN la confirmación, para volver a intentarlo con la lectura siguiente sin otra confirmación.
    Se llama solo si la lectura llegó hasta la comparación: válida, reciente, sensor activo, sector en servicio, con umbral (y, en la luz, dentro del horario)."""
    if NodoCentral.objects.filter(sistema_id=contexto.sistema_id, modo=NodoCentral.Modo.LOCAL).exists():  # 6d
        return []
    activas = list(ReglaActuacion.objects.filter(sensor=sensor, estado_regla=ReglaActuacion.Estado.ACTIVA).select_related("accion__comando", "sensor").order_by("pk"))
    if not activas:
        return []
    nombre_umbral, parametro = VARIABLES_DEL_UMBRAL[sensor.tipo_variable_sensor]
    limites = getattr(contexto.umbral, nombre_umbral)
    histeresis = _histeresis(getattr(contexto.config, parametro), limites.minimo, limites.maximo)
    confirmacion = contexto.config.cant_lecturas_confirmacion
    valor = telemetria.valor_medido
    confirmadas = []
    for regla in activas:
        cumple = _cumple(regla, valor, limites.minimo, limites.maximo, histeresis)
        if cumple and regla.ultima_evaluacion == ReglaActuacion.Evaluacion.CUMPLIDA:  # 6b: ya se cumplía
            continue
        regla.ultima_evaluacion = ReglaActuacion.Evaluacion.NO_CUMPLIDA
        regla.contador_confirmacion = regla.contador_confirmacion + 1 if cumple else 0  # 6c, o una lectura que no cumple
        if cumple and regla.contador_confirmacion >= confirmacion:
            confirmadas.append(regla)
    actuadores = {}
    if confirmadas:  # 6a: los actuadores se bloquean en orden de id (D-78, punto 11)
        consulta = Actuador.objects.select_for_update(no_key=True, of=("self",)).select_related("tipo_actuador").filter(pk__in={r.actuador_id for r in confirmadas}).order_by("pk")
        actuadores = {actuador.pk: actuador for actuador in consulta}
    creados = []
    for regla in confirmadas:
        actuador = actuadores[regla.actuador_id]
        emitido = None
        if _motivo_de_ocupado(actuador, regla.accion, regla.aplicar_valor, ahora) is None:
            emitido = _emitir(regla, actuador, telemetria, ahora)
        if emitido is None:  # 6a.1a: ocupada; el contador queda EN la confirmación
            regla.contador_confirmacion = confirmacion
        else:  # postcondiciones j a l y 6a.3
            regla.ultima_evaluacion, regla.contador_confirmacion = ReglaActuacion.Evaluacion.CUMPLIDA, 0
            creados.extend(emitido)
    for regla in activas:
        ReglaActuacion.objects.filter(pk=regla.pk).update(ultima_evaluacion=regla.ultima_evaluacion, contador_confirmacion=regla.contador_confirmacion)
    return creados


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
        self.extras = []  # comandos automáticos y sus registros de bitácora (postcondiciones j y l), para la auditoría de la lectura

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
            # Extensión 5c: las reglas del sensor vuelven a «sin evaluar» con el contador en 0. También con la variable del umbral vacía (D-75, punto 3: «no se compara, igual
            # que en 5c»): hueco de «Reglas de actuación» de entregar_informacion.md, que solo nombra el caso «sin umbral» (decisión del estudiante del 23/11/2026).
            reglas.reiniciar_reglas(list(ReglaActuacion.objects.filter(sensor=sensor, estado_regla=ReglaActuacion.Estado.ACTIVA).values_list("pk", flat=True)))
            return valida, atrasada
        h = _histeresis(getattr(config, parametro), limites.minimo, limites.maximo)
        _comparar(cambios, sensor, telemetria, valor, limites.minimo, limites.maximo, h, "iot_fuera_de_umbral", clave_sensor, "efectivo", sensor.unidad_medida)
        cambios.extras.extend(evaluar_reglas_de_la_lectura(contexto, sensor, telemetria, ahora))  # paso 6 (IOT-06)
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
        if cambios.generadas or cambios.resueltas or cambios.extras:  # paso 11 (los comandos automáticos y su bitácora cuentan: postcondición z)
            auditar_entrega(sistema, "lectura", lectura.identificador, [sensor, *cambios.extras], None, cambios.generadas, cambios.resueltas)
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
