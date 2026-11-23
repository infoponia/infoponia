# Panel de monitoreo del IoT (IOT-04; IOT-CNS-LEC; docs/casos_de_uso/iot/consultar_lecturas.md, «Servicio», «Situación de un sensor», «Tarjeta de un sensor», «Gráficos»,
# «Actuadores»). ``panel(actor, invernadero_id, periodo, ahora)`` arma todo lo que muestra la pantalla; lo usan la vista completa y el fragmento que se refresca solo.
#
# SOLO LECTURA (reglas 10 y 12): no escribe, no audita y no dispara la revisión periódica. Y con una cantidad FIJA de consultas: la misma con 1 sensor que con 10
# (nada de una consulta por sensor, actuador o alerta; las series de todos los sensores salen de UNA consulta y el umbral, con los nombres de sus variedades, de dos).
# Todas las funciones reciben ``ahora``: nunca leen la hora por su cuenta.

from collections import defaultdict, namedtuple
from datetime import timedelta

from django.http import Http404
from django.utils import timezone
from django.utils.timesince import timesince

from core.models import Usuario, rol_de
from inventario.servicios.variedades import umbral_efectivo
from iot.alcance import invernaderos_que_consulta, invernaderos_que_opera
from iot.alertas import CODIGOS_DE_ALERTAS_IOT
from iot.graficos import grafico_de_sensor
from iot.models import Actuador, AlertaIot, FotoperiodoDiario, NodoCentral, ResumenHorario, Sensor, SistemaIoT, Telemetria
from iot.servicios.alertas_iot import TIPO_NO_REGISTRADO, bajas_por_identificador
from iot.servicios.sistemas import ESTADOS_VIGENTES, _exigir_operador, conectividad
from iot.textos import estado_legible, lectura_legible, numero_legible
from maestros.forms import GRUPOS_IOT
from maestros.models import PARAMETROS_IOT, Alerta, Variedad
from maestros.servicios import configuracion
from maestros.servicios.alertas import consultar_alertas, enlaces_de_alertas

# El período del selector, en horas: de la última hora a los últimos 30 días. Hasta 24 horas se grafican las lecturas; más, los resúmenes horarios (regla 4).
PERIODOS = {1: "Última hora", 6: "Últimas 6 horas", 24: "Últimas 24 horas", 168: "Últimos 7 días", 720: "Últimos 30 días"}
PERIODO_POR_OMISION = 24

Aviso = namedtuple("Aviso", "tono texto")  # tono: info, warn o danger
Situacion = namedtuple("Situacion", "clave texto tono")  # tono: neutral, ok, warn o danger
Indicadores = namedtuple("Indicadores", "sensores_con_problema sensores alertas_activas actuadores_operativos actuadores")
FilaDeAlerta = namedtuple("FilaDeAlerta", "alerta severidad nombre_tipo enlace notificada_por_correo equipo_dado_de_baja")
FotoperiodoDeAyer = namedtuple("FotoperiodoDeAyer", "estado texto")  # estado: sin_calcular, incompleto, sin_umbral, en_rango o fuera_de_rango
TarjetaDeSensor = namedtuple(
    "TarjetaDeSensor",
    "sensor situacion ultima_lectura texto_del_valor hace sector_fuera_de_servicio serie franja grafico texto_del_nivel fotoperiodo",
)
GrupoDeSensores = namedtuple("GrupoDeSensores", "variable nombre subtitulo tarjetas con_problema")
FilaDeActuador = namedtuple("FilaDeActuador", "actuador estado_texto desde cambiado_en_invernadero situacion compatibilidad")
FilaDeUmbral = namedtuple("FilaDeUmbral", "variable nombre unidad minimo maximo lo_limita_minimo lo_limita_maximo")
UmbralDelPanel = namedtuple("UmbralDelPanel", "hay filas variedades rango_solucion")
ParametroDelPanel = namedtuple("ParametroDelPanel", "campo etiqueta valor")
PanelDeMonitoreo = namedtuple(
    "PanelDeMonitoreo",
    "invernadero periodo resumido sistema nodo conectividad avisos indicadores alertas aviso_de_alertas grupos actuadores umbral parametros opera puede_registrar",
)

# La etiqueta de cada parámetro IoT: la de la sección «Módulo IoT» de la configuración (una sola fuente, ``maestros.forms.GRUPOS_IOT``).
ETIQUETAS_IOT = {campo: etiqueta for _, parametros in GRUPOS_IOT for campo, etiqueta, _ in parametros}

# Los sensores se agrupan por variable en este orden (prototipo, ``VARS``).
ORDEN_DE_VARIABLES = ("temperatura", "humedad", "intensidad_luz", "temperatura_solucion", "nivel_solucion")
# Variable del sensor → variable del umbral efectivo (las que se comparan con él; regla 3).
VARIABLE_DEL_UMBRAL = {"temperatura": "temp_ambiente", "humedad": "humedad", "intensidad_luz": "intensidad_luz"}
# Las filas del bloque «Umbral efectivo» (regla 6): (variable del umbral, nombre, unidad).
FILAS_DEL_UMBRAL = (
    ("temp_ambiente", "Temperatura ambiente", "°C"),
    ("humedad", "Humedad", "% HR"),
    ("intensidad_luz", "Intensidad lumínica", "lux"),
    ("fotoperiodo", "Fotoperíodo", "h"),
)
TIPO_SIN_ACTIVIDAD = "iot_dispositivo_sin_actividad"
TIPO_NIVEL_BAJO = "iot_nivel_solucion_bajo"
TEXTO_DESCONECTADO = "Sistema desconectado. InfoPonia no recibe lecturas ni emite comandos hasta que se active; se muestran los últimos datos recibidos."
TEXTO_NUNCA = "El nodo todavía no se comunicó. Cargale la dirección de la API y el token; cuando se comunique pasará a «En línea»."
TEXTO_LOCAL = (
    "El nodo está operando en modo local. Actúa por su cuenta con su control de seguridad. InfoPonia sigue registrando lecturas y alertas, "
    "pero no evalúa reglas ni entrega comandos hasta que vuelva a «remoto»."
)


class _Contexto:
    """Lo que comparten las tarjetas y las filas: los datos ya leídos (una consulta cada uno) y los parámetros del panel."""

    def __init__(self, **datos):
        self.__dict__.update(datos)


def _panel_sin_sistema(invernadero, periodo, opera):
    """Precondición b: sin un sistema no dado de baja, el panel viene vacío y solo ofrece «Registrar Sistema IoT» a quien opera el invernadero."""
    return PanelDeMonitoreo(
        invernadero=invernadero, periodo=periodo, resumido=periodo > 24, sistema=None, nodo=None, conectividad=None, avisos=[],
        indicadores=Indicadores(0, 0, 0, 0, 0), alertas=[], aviso_de_alertas=None, grupos=[], actuadores=[],
        umbral=UmbralDelPanel(False, [], [], None), parametros=[], opera=opera, puede_registrar=opera,
    )


def panel(actor, invernadero_id, periodo, ahora):
    """El panel de monitoreo del invernadero ``invernadero_id`` para ``actor`` (Agrónomo o Gerente activos: otro rol, ``PermissionDenied``; un invernadero fuera de su alcance
    de consulta o inexistente, ``Http404``, regla 1). ``periodo`` es una de las claves de ``PERIODOS`` (si no, ``ValueError``)."""
    if periodo not in PERIODOS:
        raise ValueError(f"Período desconocido: {periodo!r}. Los válidos son {', '.join(str(p) for p in PERIODOS)}.")
    _exigir_operador(actor)
    invernadero = invernaderos_que_consulta(actor).select_related("agronomo").filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    opera = invernaderos_que_opera(actor).filter(pk=invernadero.pk).exists()
    sistema = SistemaIoT.objects.filter(invernadero=invernadero, estado_sistema__in=ESTADOS_VIGENTES).first()
    if sistema is None:
        return _panel_sin_sistema(invernadero, periodo, opera)

    config = configuracion.obtener()
    nodo = NodoCentral.objects.get(sistema=sistema)
    conect = conectividad(nodo, ahora)
    sensores = list(Sensor.objects.filter(sistema=sistema).exclude(estado_hardware="inactivo").select_related("sector").order_by("identificador_equipo", "pk"))
    actuadores = list(Actuador.objects.filter(sistema=sistema).exclude(estado_hardware="inactivo").order_by("identificador_equipo", "pk"))
    activos = list(AlertaIot.objects.filter(sistema=sistema, alerta__estado_alerta=Alerta.Estado.ACTIVA).select_related("alerta", "telemetria"))
    umbral = umbral_efectivo([invernadero.pk])[invernadero.pk]
    nombres_de_variedades = (
        dict(Variedad.objects.filter(pk__in=umbral.variedad_ids).values_list("pk", "nombre_variedad")) if umbral is not None else {}
    )
    resumido = periodo > 24
    ayer = timezone.localtime(ahora).date() - timedelta(days=1)
    ctx = _Contexto(
        ahora=ahora, config=config, conectividad=conect, umbral=umbral, sistema=sistema, periodo=periodo, resumido=resumido,
        ultimas={t.sensor_id: t for t in Telemetria.objects.filter(sensor__sistema=sistema).order_by("sensor_id", "-medida_en", "-id").distinct("sensor_id")},
        sin_actividad={v.hardware_id for v in activos if v.alerta.tipo_alerta == TIPO_SIN_ACTIVIDAD},
        nivel_bajo_desde={v.telemetria.sensor_id: v.telemetria.medida_en for v in activos if v.alerta.tipo_alerta == TIPO_NIVEL_BAJO and v.telemetria is not None},
        series=_series(sistema, periodo, ahora),
        fotoperiodos={f.sensor_id: f for f in FotoperiodoDiario.objects.filter(sensor__sistema=sistema, fecha=ayer)},
    )
    grupos = _grupos(sensores, ctx)
    filas_de_actuadores = [_fila_de_actuador(a, ctx) for a in actuadores]
    alertas = _alertas(actor, invernadero, sistema, activos)
    operativos = sum(1 for f in filas_de_actuadores if f.situacion.clave == "operativo")
    return PanelDeMonitoreo(
        invernadero=invernadero,
        periodo=periodo,
        resumido=resumido,
        sistema=sistema,
        nodo=nodo,
        conectividad=conect,
        avisos=_avisos(sistema, nodo, conect, ahora),
        indicadores=Indicadores(sum(g.con_problema for g in grupos), len(sensores), len(alertas), operativos, len(actuadores)),
        alertas=alertas,
        aviso_de_alertas=_aviso_de_alertas(actor, invernadero, opera),
        grupos=grupos,
        actuadores=filas_de_actuadores,
        umbral=_umbral(umbral, nombres_de_variedades, sistema),
        parametros=[ParametroDelPanel(campo, ETIQUETAS_IOT.get(campo, etiqueta), getattr(config, campo)) for campo, etiqueta, *_ in PARAMETROS_IOT],
        opera=opera,
        puede_registrar=False,
    )


# ---- regla 2: el nodo ----


def _avisos(sistema, nodo, conect, ahora):
    """Los avisos del encabezado del nodo (regla 2): sistema desconectado, nodo sin señal (nunca o desde hace cuánto) y modo local."""
    avisos = []
    if sistema.estado_sistema == SistemaIoT.Estado.DESCONECTADO:
        avisos.append(Aviso("warn", TEXTO_DESCONECTADO))
    if conect.estado == "sin_senal":
        if nodo.ultima_comunicacion is None:
            avisos.append(Aviso("info", TEXTO_NUNCA))
        else:
            avisos.append(Aviso("danger", f"El nodo no se comunica desde hace {timesince(nodo.ultima_comunicacion, ahora)}. Los valores son los últimos recibidos."))
    if nodo.modo == NodoCentral.Modo.LOCAL:
        avisos.append(Aviso("warn", TEXTO_LOCAL))
    return avisos


# ---- regla 3 y 4: los sensores ----


def _series(sistema, periodo, ahora):
    """``{id del sensor: serie}`` de TODOS los sensores del sistema con UNA consulta (regla 4): hasta 24 horas, los valores de las lecturas VÁLIDAS del período en orden; 7 y 30
    días, ``(mínimo, promedio, máximo)`` de cada resumen horario (sin los de una hora solo con inválidas, que no tienen qué graficar)."""
    desde = ahora - timedelta(hours=periodo)
    series = defaultdict(list)
    if periodo > 24:
        filas = (
            ResumenHorario.objects.filter(sensor__sistema=sistema, hora__gte=desde, promedio__isnull=False)
            .order_by("sensor_id", "hora")
            .values_list("sensor_id", "minimo", "promedio", "maximo")
        )
        for sensor_id, minimo, promedio, maximo in filas:
            series[sensor_id].append((minimo, promedio, maximo))
    else:
        filas = (
            Telemetria.objects.filter(sensor__sistema=sistema, valida=True, medida_en__gte=desde)
            .order_by("sensor_id", "medida_en", "id")
            .values_list("sensor_id", "valor_medido")
        )
        for sensor_id, valor in filas:
            series[sensor_id].append(valor)
    return series


def _limites_para(variable, ctx):
    """``(mínimo, máximo)`` con que se compara una VARIABLE: el umbral efectivo (temperatura, humedad y luz) o el rango de la solución; ``None`` si no hay (o es el nivel)."""
    if variable in VARIABLE_DEL_UMBRAL:
        limites = getattr(ctx.umbral, VARIABLE_DEL_UMBRAL[variable]) if ctx.umbral is not None else None
        return (limites.minimo, limites.maximo) if limites is not None else None
    if variable == "temperatura_solucion" and ctx.sistema.temp_solucion_min is not None:
        return ctx.sistema.temp_solucion_min, ctx.sistema.temp_solucion_max
    return None


def _en_sector_fuera_de_servicio(sensor):
    return sensor.sector is not None and sensor.sector.estado_sector == "fuera_de_servicio"


def _situacion_de(sensor, ultima, limites, ctx):
    """La «Situación de un sensor» (regla 3 y 8; prototipo ``sensorState``): la PRIMERA condición que corresponda, en el orden de «Situación de un sensor»."""
    variable = sensor.tipo_variable_sensor
    if sensor.ultimo_mensaje_en is None:
        return Situacion("sin_confirmar", "Sin confirmar", "neutral")
    if sensor.estado_hardware == "fuera_de_servicio":
        return Situacion("fuera_de_servicio", "Fuera de servicio", "danger")
    if ctx.conectividad.estado == "sin_senal":
        return Situacion("desactualizado", "Desactualizado", "warn")
    if sensor.pk in ctx.sin_actividad:
        minutos = int((ctx.ahora - sensor.ultimo_mensaje_en).total_seconds() // 60)
        return Situacion("sin_actividad", f"Sin actividad · {minutos} min", "warn")
    if ultima is None:
        return Situacion("sin_lecturas", "Sin lecturas", "neutral")  # el mensaje existe pero la retención ya borró las lecturas
    if ultima.valida is False:
        return Situacion("lectura_invalida", "Lectura inválida", "warn")
    if variable == "nivel_solucion":
        if ultima.estado_nivel_medido == Telemetria.EstadoNivel.BAJO:
            return Situacion("nivel_bajo", "Nivel bajo", "danger")
        return Situacion("normal", "Normal", "ok")
    if variable == "intensidad_luz":
        hora = timezone.localtime(ultima.medida_en).hour
        if hora < ctx.config.hora_inicio_luz or hora >= ctx.config.hora_fin_luz:
            return Situacion("fuera_del_horario_de_luz", "Fuera del horario de luz", "neutral")
    if variable != "temperatura_solucion" and _en_sector_fuera_de_servicio(sensor):  # regla 8 y D-75 punto 7: la solución se sigue comparando
        return Situacion("sector_fuera_de_servicio", "Sector fuera de servicio", "neutral")
    if limites is None:
        return Situacion("sin_rango", "Sin rango definido", "neutral") if variable == "temperatura_solucion" else Situacion("sin_umbral", "Sin umbral efectivo", "neutral")
    if ultima.valor_medido > limites[1]:
        return Situacion("supera_maximo", "Supera el máximo", "danger")
    if ultima.valor_medido < limites[0]:
        return Situacion("bajo_el_minimo", "Bajo el mínimo", "danger")
    return Situacion("en_rango", "En rango", "ok")


def _fotoperiodo_de_ayer(sensor, ctx):
    """El fotoperíodo del último día completo de un sensor de luz frente al rango del umbral efectivo (regla 3); ``None`` si no es de luz."""
    if sensor.tipo_variable_sensor != "intensidad_luz":
        return None
    calculado = ctx.fotoperiodos.get(sensor.pk)
    if calculado is None:
        return FotoperiodoDeAyer("sin_calcular", "Sin calcular (corre en la revisión periódica)")
    texto = f"Fotoperíodo de ayer: {numero_legible(calculado.horas)} h"
    if calculado.incompleto:
        return FotoperiodoDeAyer("incompleto", texto)
    rango = ctx.umbral.fotoperiodo if ctx.umbral is not None else None
    if rango is None:
        return FotoperiodoDeAyer("sin_umbral", texto)
    return FotoperiodoDeAyer("en_rango" if rango.minimo <= calculado.horas <= rango.maximo else "fuera_de_rango", texto)


def _tarjeta(sensor, ctx):
    """La tarjeta de un sensor (regla 3, 4 y 8; «Tarjeta de un sensor»): su situación, su último valor, su gráfico y, en la luz, el fotoperíodo de ayer."""
    ultima = ctx.ultimas.get(sensor.pk)
    limites = _limites_para(sensor.tipo_variable_sensor, ctx)
    situacion = _situacion_de(sensor, ultima, limites, ctx)
    nivel = sensor.tipo_variable_sensor == "nivel_solucion"
    serie = ctx.series.get(sensor.pk, [])
    texto_del_nivel = ""
    if nivel:
        if ultima is None:
            texto_del_nivel = "Todavía no informó datos"
        elif ultima.estado_nivel_medido == Telemetria.EstadoNivel.BAJO:
            desde = ctx.nivel_bajo_desde.get(sensor.pk, ultima.medida_en)
            texto_del_nivel = f"Informa «bajo» desde las {timezone.localtime(desde):%H:%M}"
        else:
            texto_del_nivel = "Nivel normal"
    return TarjetaDeSensor(
        sensor=sensor,
        situacion=situacion,
        ultima_lectura=ultima,
        texto_del_valor=lectura_legible(ultima) if ultima is not None else "—",
        hace=timesince(ultima.medida_en, ctx.ahora) if ultima is not None else "",
        sector_fuera_de_servicio=_en_sector_fuera_de_servicio(sensor),
        serie=[] if nivel else serie,
        franja=limites,
        grafico=None if nivel else grafico_de_sensor(serie, limites, ctx.resumido, f"{sensor.identificador_equipo} · {PERIODOS[ctx.periodo]}"),
        texto_del_nivel=texto_del_nivel,
        fotoperiodo=_fotoperiodo_de_ayer(sensor, ctx),
    )


def _subtitulo(variable, ctx):
    """Lo que dice la cabecera de un grupo: el umbral efectivo (y el horario de luz), el rango de la solución o nada (el nivel no se compara)."""
    if variable == "nivel_solucion":
        return ""
    limites = _limites_para(variable, ctx)
    if variable == "temperatura_solucion":
        return f"Rango del invernadero {numero_legible(limites[0])} a {numero_legible(limites[1])} °C" if limites else "Sin rango definido"
    if limites is None:
        return "Sin umbral efectivo"
    unidad = Sensor.UNIDADES[variable]
    texto = f"Umbral efectivo {numero_legible(limites[0])} a {numero_legible(limites[1])} {unidad}"
    if variable == "intensidad_luz":
        texto += f" · se evalúa de {ctx.config.hora_inicio_luz} a {ctx.config.hora_fin_luz} h"
    return texto


def _grupos(sensores, ctx):
    """Los sensores agrupados por variable, en el orden fijo y solo las variables que tienen sensores (regla 3)."""
    nombres = dict(Sensor.Variable.choices)
    grupos = []
    for variable in ORDEN_DE_VARIABLES:
        tarjetas = [_tarjeta(s, ctx) for s in sensores if s.tipo_variable_sensor == variable]
        if tarjetas:
            con_problema = sum(1 for t in tarjetas if t.situacion.tono == "danger")
            grupos.append(GrupoDeSensores(variable, nombres[variable], _subtitulo(variable, ctx), tarjetas, con_problema))
    return grupos


# ---- regla 5: los actuadores ----


def _fila_de_actuador(actuador, ctx):
    """La fila de un actuador (regla 5; prototipo ``actState`` y ``estInf``): su estado informado, su situación (en orden) y su compatibilidad."""
    if actuador.estado_hardware == "fuera_de_servicio":
        situacion = Situacion("fuera_de_servicio", "Fuera de servicio", "danger")
    elif actuador.ultimo_mensaje_en is None:
        situacion = Situacion("sin_confirmar", "Sin confirmar", "warn")
    elif actuador.pk in ctx.sin_actividad:
        situacion = Situacion("sin_actividad", "Sin actividad", "warn")
    elif actuador.compatibilidad == Actuador.Compatibilidad.INCOMPATIBLE:
        situacion = Situacion("incompatible", "Configuración incompatible", "warn")
    else:
        situacion = Situacion("operativo", "Operativo", "ok")
    return FilaDeActuador(
        actuador=actuador,
        estado_texto=estado_legible(actuador.estado_informado) or "Desconocido",
        desde=actuador.estado_informado_en if actuador.estado_informado else None,
        cambiado_en_invernadero=actuador.cambiado_en_invernadero,
        situacion=situacion,
        compatibilidad=actuador.get_compatibilidad_display(),
    )


# ---- regla 6: umbral efectivo y parámetros ----


def _umbral(umbral, nombres, sistema):
    """El bloque «Umbral efectivo» (regla 6): cada límite con la variedad que lo fija, las variedades que lo componen y el rango de la solución, si está definido."""
    rango = (sistema.temp_solucion_min, sistema.temp_solucion_max) if sistema.temp_solucion_min is not None else None
    if umbral is None:
        return UmbralDelPanel(False, [], [], rango)
    filas = []
    for variable, nombre, unidad in FILAS_DEL_UMBRAL:
        limites = getattr(umbral, variable)
        if limites is None:
            filas.append(FilaDeUmbral(variable, nombre, unidad, None, None, None, None))
        else:
            filas.append(
                FilaDeUmbral(
                    variable, nombre, unidad, limites.minimo, limites.maximo,
                    nombres.get(limites.variedad_minimo_id), nombres.get(limites.variedad_maximo_id),
                )
            )
    return UmbralDelPanel(True, filas, sorted(nombres.values()), rango)


# ---- regla 7: las alertas activas ----


def _alertas(actor, invernadero, sistema, activos):
    """Las alertas activas del IoT del invernadero que ``actor`` recibe (``consultar_alertas`` con ``tipos``, ya ordenadas por severidad) con su enlace (una llamada para toda
    la lista), si se notificó por correo y, en «dispositivo no registrado», el equipo dado de baja que tenía el identificador."""
    alertas = consultar_alertas(actor, invernadero_id=invernadero.pk, tipos=CODIGOS_DE_ALERTAS_IOT)
    enlaces = enlaces_de_alertas(actor, alertas)
    correos = {v.alerta_id: v.correo_enviado_en for v in activos}
    identificadores = {a.pk: a.clave_estado.removeprefix("id:") for a in alertas if a.tipo_alerta == TIPO_NO_REGISTRADO}
    bajas = bajas_por_identificador({sistema.pk}, identificadores.values())
    return [
        FilaDeAlerta(
            alerta=alerta,
            severidad=alerta.severidad,
            nombre_tipo=alerta.nombre_tipo,
            enlace=enlaces[alerta.pk],
            notificada_por_correo=correos.get(alerta.pk) is not None,
            equipo_dado_de_baja=bajas.get((sistema.pk, identificadores[alerta.pk].lower())) if alerta.pk in identificadores else None,
        )
        for alerta in alertas
    ]


def _aviso_de_alertas(actor, invernadero, opera):
    """Decisión de IOT-04 (pausa 2): las alertas del IoT las recibe el Agrónomo activo (MAE-02, R007) y `consultar_alertas` le da al Gerente solo las suyas. Para no mostrarle
    un «0 alertas activas» engañoso, al Gerente que no opera el invernadero (tiene un Agrónomo activo) se le dice quién las recibe. El Agrónomo sale del invernadero ya cargado."""
    agronomo = invernadero.agronomo
    if opera or rol_de(actor) != Usuario.Rol.GERENTE or agronomo is None or not agronomo.is_active:
        return None
    nombre = agronomo.get_full_name() or agronomo.email
    return f"Las alertas de este invernadero las recibe {nombre}; vos las recibís si no tiene un Agrónomo activo."
