# Cargador de datos de verificación del IoT (IOT-03; docs/patrones/datos_de_verificacion.md; CLAUDE.md, «Datos para la verificación a mano»).
# Lo registra ``IotConfig.ready()`` en ``core.verificacion`` (regla A4 de D-37) y lo corre ``manage.py cargar_datos_de_verificacion``.
#
# El Capataz (``capataz@prueba3.local``) NO es de adorno: ``planificar_siembra`` exige un Capataz activo en el invernadero para dar la orden (PROD-PNF-SMB, extensión 3a), y sin la
# siembra «a realizar» no hay umbral efectivo (no se podría verificar «Fuera de umbral efectivo»).
# PRIMERA CORRIDA: deja la base como la necesita la verificación de la API del nodo, SIEMPRE llamando a los servicios de las apps (nunca
# con inserciones directas: así quedan la auditoría y las reglas como en una pantalla real):
#   - cuentas ``agronomo@prueba3.local`` y ``capataz@prueba3.local`` (las prueba1 y prueba2 son de ``maestros``) (la contraseña es la que se pasa al comando);
#   - el invernadero «Norte», con ese Agrónomo y ese Capataz y SIN Técnico, con «Sector A»;
#   - un insumo de «Repuestos de hardware» (el que piden los equipos);
#   - una variedad con su semilla habilitada y con stock, y una siembra «a realizar»: eso da umbral efectivo (PROD-PNF-SMB), para poder
#     verificar «Fuera de umbral efectivo».
# SEGUNDA CORRIDA (después de registrar a mano el sistema IoT de «Norte» por la pantalla): carga el rango de la solución (18,0 a 24,0 °C)
# y los equipos de ``docs/api/nodo/node-red/README.md``, sección 4, punto 2. El sistema IoT NO se carga acá y el token nunca pasa por este
# archivo: se muestra una sola vez en la pantalla (D-70).
# IOT-04 suma, para su verificación a mano (docs/tareas/iot/IOT-04-revision-panel-y-configuracion.md):
#   - el invernadero «Sur», SIN Agrónomo y SIN sistema IoT: el Gerente lo opera y ve «Registrar Sistema IoT» (el Gerente que mira «Norte», que tiene Agrónomo, solo consulta);
#   - en la segunda corrida, las lecturas de AYER y de ANTEAYER de la temperatura y la luz de «Norte», una cada 5 minutos y de día entero (``registrar_lectura``, el servicio de la API, con su ``ahora`` simulado):
#     dan el gráfico de 7 días con resúmenes y, con la primera revisión, el fotoperíodo de ayer (10 h, dentro del rango del umbral). Las de ayer terminan a las 23:55, así que el nodo queda «sin señal» y los
#     sensores «sin actividad» hasta que Node-RED mande: no se carga ninguna comunicación del nodo (evita una alerta crítica y un correo antes de empezar).
# No borra nada. Idempotente: lo que ya existe se reutiliza. ``temp-vieja`` (un sensor dado de baja) lo suma IOT-06, que trae la baja.

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from core import verificacion
from core.verificacion import ErrorDeCarga
from core.models import Agronomo, Capataz, Gerente, Usuario
from core.servicios import ACCESO_TEMPORAL, alta_usuario, cambiar_contrasena
from inventario.categorias import REPUESTOS_DE_HARDWARE
from inventario.models import Insumo, InsumoInvernadero, TipoInsumo
from inventario.servicios import ajustes
from inventario.servicios import insumos as servicio_insumos
from inventario.servicios import insumos_invernadero
from inventario.servicios.variedades import DatosDeVariedad, alta_variedad
from iot.api.traduccion import LecturaRecibida
from iot.models import Actuador, Hardware, NodoCentral, Sensor, SistemaIoT, Telemetria, TipoActuador
from iot.servicios import lecturas as servicio_lecturas
from iot.servicios import hardware as servicio_hardware
from iot.servicios import sistemas as servicio_sistemas
from maestros.models import Cultivo, Invernadero, Localidad, SectorProduccion, TipoEtapa, Variedad
from maestros.servicios import cultivos as servicio_cultivos
from maestros.servicios import invernaderos as servicio_invernaderos
from maestros.servicios import sectores as servicio_sectores
from produccion.models import OrdenTrabajo, Siembra
from produccion.servicios import siembras

CODIGO = "iot"
NOMBRE_DEL_INVERNADERO = "Norte"
NOMBRE_DEL_SECTOR = "Sector A"
NOMBRE_DEL_SECTOR_DE_MADURACION = "Sector B"  # la siembra pide un sector por cada etapa de la variedad (Germinación y Maduración)
NOMBRE_DEL_CULTIVO = "Lechuga"
NOMBRE_DE_LA_VARIEDAD = "Crespa"
NOMBRE_DEL_REPUESTO = "Repuesto de sensor"
NOMBRE_DEL_INVERNADERO_SIN_AGRONOMO = "Sur"
PASO_EN_MINUTOS = 5  # una lectura cada 5 minutos: el máximo que no marca «incompleto» el fotoperíodo (minutos sin actividad = 5)
DIAS_DE_TEMPERATURA = 2  # ayer y anteayer; la luz, solo ayer (para el fotoperíodo)
CUENTAS = (("agronomo", "Agrónomo"), ("capataz", "Capataz"))  # (rol, nombre) de las cuentas <rol>@prueba1.local
SUFIJO = "prueba3.local"  # prueba1 y prueba2 son de ``maestros`` (MAE-02d): cada cargador usa su propio número de cuenta

# Rango de la temperatura de la solución del escenario de los ejemplos (docs/api/nodo/ejemplos/README.md, «Escenario»).
RANGO_DE_LA_SOLUCION = ("18.0", "24.0")

# Los equipos de ``docs/api/nodo/node-red/README.md``, sección 4, punto 2 (los mismos del escenario de los ejemplos): (identificador, variable,
# calibración mínima, calibración máxima) de los sensores y (identificador, nombre del tipo de actuador) de los actuadores. Los sensores de
# «Sector A» van con el sector; los del tanque, «General».
SENSORES = (
    ("norte/sectorA/temperatura", "temperatura", "-10", "60", True),
    ("norte/sectorA/humedad", "humedad", "0", "100", True),
    ("norte/sectorA/luz", "intensidad_luz", "0", "100000", True),
    ("norte/tanque1/temp-solucion", "temperatura_solucion", "0", "50", False),
    ("norte/tanque1/nivel", "nivel_solucion", "", "", False),
)
ACTUADORES = (
    ("norte/sectorA/ventilador", "Ventilador"),
    ("norte/sectorA/ventana", "Ventana"),
)


def _gerente_activo():
    """El Gerente activo, que da de alta cuentas e invernaderos. Sin Gerente no se puede cargar nada: se lo dice."""
    gerente = Gerente.objects.filter(is_active=True).first()
    if gerente is None:
        raise ErrorDeCarga("No hay un Gerente activo: creá uno antes de cargar los datos de verificación.")
    return gerente


def _cuenta(gerente, rol, nombre, contrasena, creado, cuentas):
    """La cuenta ``<rol>@prueba1.local``: se reutiliza si existe; si no, se da de alta con ``alta_usuario`` y se le pone la contraseña de quien
    trabaja con ``cambiar_contrasena`` (la temporal se descarta: nunca se muestra)."""
    email = f"{rol}@{SUFIJO}"
    cuenta = Usuario.objects.filter(email__iexact=email).first()
    if cuenta is None:
        cuenta, resultado = alta_usuario(gerente, rol, nombre, "de prueba", email, acceso=ACCESO_TEMPORAL)
        cambiar_contrasena(cuenta, contrasena)
        creado.append(f"Cuenta {email} ({nombre}).")
    cuentas.append(f"{email} · {nombre}")
    return cuenta


def _tipo_de_etapa(codigo):
    """El tipo de etapa del catálogo con ese código."""
    return TipoEtapa.objects.get(codigo=codigo)


def _invernadero(gerente, agronomo, capataz, creado):
    """«Norte», con Agrónomo y Capataz y sin Técnico (``alta_invernadero``). Si ya existe, se reutiliza."""
    invernadero = Invernadero.objects.filter(nombre_invernadero__iexact=NOMBRE_DEL_INVERNADERO).first()
    if invernadero is None:
        localidad = Localidad.objects.filter(nombre_localidad="Garupá").first() or Localidad.objects.first()
        invernadero = servicio_invernaderos.alta_invernadero(
            gerente,
            NOMBRE_DEL_INVERNADERO,
            tipo_direccion="urbana",
            localidad_id=localidad.pk,
            calle="Calle 1",
            numero_calle="100",
            agronomo_id=agronomo.pk,
            capataz_id=capataz.pk,
        )
        creado.append(f"Invernadero «{NOMBRE_DEL_INVERNADERO}» (Agrónomo y Capataz de prueba, sin Técnico).")
    return invernadero


def _sector(agronomo, invernadero, creado):
    """«Sector A» (germinación) y «Sector B» (maduración), de 100 agujeros cada uno (``alta_sector``). Devuelve el primero."""
    sector = SectorProduccion.objects.filter(invernadero=invernadero, nombre_sector__iexact=NOMBRE_DEL_SECTOR).first()
    if sector is None:
        sector = servicio_sectores.alta_sector(
            agronomo,
            invernadero.pk,
            nombre=NOMBRE_DEL_SECTOR,
            tipo_etapa_id=_tipo_de_etapa("germinacion").pk,
            cant_agujeros_total=100,
        )
        creado.append(f"«{NOMBRE_DEL_SECTOR}» en «{NOMBRE_DEL_INVERNADERO}».")
    if not SectorProduccion.objects.filter(invernadero=invernadero, nombre_sector__iexact=NOMBRE_DEL_SECTOR_DE_MADURACION).exists():
        servicio_sectores.alta_sector(
            agronomo,
            invernadero.pk,
            nombre=NOMBRE_DEL_SECTOR_DE_MADURACION,
            tipo_etapa_id=_tipo_de_etapa("maduracion").pk,
            cant_agujeros_total=100,
        )
        creado.append(f"«{NOMBRE_DEL_SECTOR_DE_MADURACION}» (maduración) en «{NOMBRE_DEL_INVERNADERO}».")
    return sector


def _insumo_de_repuesto(agronomo, creado):
    """Un insumo de «Repuestos de hardware» (``alta_insumo``): el que piden los equipos al registrarse (regla 8 de IOT-ALT-HDW)."""
    insumo = Insumo.objects.filter(nombre_insumo__iexact=NOMBRE_DEL_REPUESTO).first()
    if insumo is None:
        tipo = TipoInsumo.objects.get(codigo=REPUESTOS_DE_HARDWARE)
        insumo = servicio_insumos.alta_insumo(agronomo, nombre=NOMBRE_DEL_REPUESTO, tipo_insumo_id=tipo.pk, unidad="unidad")
        creado.append(f"Insumo «{NOMBRE_DEL_REPUESTO}» (Repuestos de hardware).")
    return insumo


def _variedad(agronomo, creado):
    """Cultivo y variedad con su ciclo, sus rangos y su semilla (``alta_cultivo`` y ``alta_variedad``). Los rangos dan el umbral efectivo:
    temperatura 18 a 26 °C, humedad 60 a 80 % HR, luz 10.000 a 30.000 lux y fotoperíodo de 8 a 14 h."""
    cultivo = Cultivo.objects.filter(nombre_cultivo__iexact=NOMBRE_DEL_CULTIVO).first()
    if cultivo is None:
        cultivo = servicio_cultivos.alta_cultivo(agronomo, nombre=NOMBRE_DEL_CULTIVO)
        creado.append(f"Cultivo «{NOMBRE_DEL_CULTIVO}».")
    variedad = Variedad.objects.filter(cultivo=cultivo, nombre_variedad__iexact=NOMBRE_DE_LA_VARIEDAD).first()
    if variedad is None:
        variedad = alta_variedad(
            agronomo,
            cultivo.pk,
            DatosDeVariedad(
                nombre=NOMBRE_DE_LA_VARIEDAD,
                perfil_familia="hoja_verde",
                etapas=(("germinacion", "7"), ("maduracion", "21")),
                temp_ambiente_min="18",
                temp_ambiente_max="26",
                humedad_min="60",
                humedad_max="80",
                intensidad_luz_min="10000",
                intensidad_luz_max="30000",
                fotoperiodo_min="8",
                fotoperiodo_max="14",
                duracion_post_cosecha="5",
                peso_promedio_planta="150",
            ),
        )
        creado.append(f"Variedad «{NOMBRE_DEL_CULTIVO} {NOMBRE_DE_LA_VARIEDAD}» con su semilla.")
    return variedad


def _semilla_con_stock(agronomo, invernadero, variedad, creado):
    """Habilita la semilla de la variedad en «Norte» (``habilitar_insumo``) y le carga stock con un ajuste de «carga inicial»
    (``calcular_ajuste`` y ``confirmar_ajuste``). Devuelve el ``InsumoInvernadero``."""
    semilla = variedad.semilla
    existencia = InsumoInvernadero.objects.filter(insumo_id=semilla.pk, invernadero=invernadero).first()
    if existencia is None:
        existencia = insumos_invernadero.habilitar_insumo(agronomo, semilla.pk, invernadero.pk, "10", "2.00")
        creado.append(f"Semilla «{semilla.nombre_insumo}» habilitada en «{NOMBRE_DEL_INVERNADERO}».")
    if not existencia.lotes.exists():
        entrada = {"cantidad": "1000", "vencimiento": (timezone.localdate() + timedelta(days=365)).isoformat()}
        resumen = ajustes.calcular_ajuste(agronomo, invernadero.pk, semilla.pk, ajustes.CARGA_INICIAL, entrada)
        ajustes.confirmar_ajuste(agronomo, invernadero.pk, semilla.pk, ajustes.CARGA_INICIAL, entrada, resumen.huella)
        creado.append("Stock de 1.000 semillas (carga inicial).")
    return existencia


def _siembra_a_realizar(agronomo, invernadero, sector, variedad, creado):
    """Una siembra «a realizar» (``planificar_siembra``): da variedades presentes y, con ellas, el umbral efectivo del invernadero."""
    if Siembra.objects.filter(invernadero=invernadero, estado_orden=OrdenTrabajo.Estado.A_REALIZAR).exists():
        return
    siembras.planificar_siembra(
        agronomo,
        siembras.DatosDeSiembra(
            invernadero_id=invernadero.pk,
            variedad_id=variedad.pk,
            cantidad=50,
            fecha_programada=timezone.localdate() + timedelta(days=1),
            distribucion=((sector.pk, 50),),
        ),
    )
    creado.append("Siembra «a realizar» de 50 plantines (da el umbral efectivo de «Norte»).")


def _equipos(agronomo, sistema, sector, creado):
    """La segunda corrida: el rango de la solución y los equipos del flujo de Node-RED, con ``modificar_sistema_iot`` y ``alta_hardware``."""
    nodo = NodoCentral.objects.get(sistema=sistema)
    if sistema.temp_solucion_min is None:
        servicio_sistemas.modificar_sistema_iot(
            agronomo,
            sistema.pk,
            servicio_sistemas.DatosDeSistema(
                nombre=nodo.nombre_nodo,
                modelo=nodo.modelo_hardware,
                numero_serie=nodo.numero_serie,
                temp_min=RANGO_DE_LA_SOLUCION[0],
                temp_max=RANGO_DE_LA_SOLUCION[1],
            ),
        )
        creado.append(f"Rango de la solución {RANGO_DE_LA_SOLUCION[0]} a {RANGO_DE_LA_SOLUCION[1]} °C.")
    en_uso = {
        identificador.lower()
        for identificador in Hardware.objects.filter(sistema=sistema).exclude(estado_hardware="inactivo").values_list(
            "identificador_equipo", flat=True
        )
        if identificador
    }
    repuesto = Insumo.objects.get(nombre_insumo__iexact=NOMBRE_DEL_REPUESTO)
    hoy = timezone.localdate()
    for identificador, variable, minimo, maximo, en_el_sector in SENSORES:
        if identificador.lower() in en_uso:
            continue
        servicio_hardware.alta_hardware(
            agronomo,
            sistema.pk,
            servicio_hardware.DatosDeEquipo(
                clase="sensor",
                identificador=identificador,
                modelo="Sensor simulado",
                fecha_instalacion=hoy,
                insumo_id=repuesto.pk,
                sector_id=sector.pk if en_el_sector else None,
                variable=variable,
                calibracion_min=minimo,
                calibracion_max=maximo,
            ),
        )
        creado.append(f"Sensor {identificador}.")
    for identificador, tipo in ACTUADORES:
        if identificador.lower() in en_uso:
            continue
        servicio_hardware.alta_hardware(
            agronomo,
            sistema.pk,
            servicio_hardware.DatosDeEquipo(
                clase="actuador",
                identificador=identificador,
                modelo="Actuador simulado",
                fecha_instalacion=hoy,
                insumo_id=repuesto.pk,
                sector_id=sector.pk,
                tipo_actuador_id=TipoActuador.objects.get(nombre_actuador=tipo).pk,
            ),
        )
        creado.append(f"Actuador {identificador} ({tipo}).")


def _invernadero_sin_agronomo(gerente, creado):
    """«Sur» (IOT-04): sin Agrónomo y sin sistema IoT, para que el Gerente lo opere y vea «Registrar Sistema IoT» (``alta_invernadero``). Si ya existe, se reutiliza."""
    invernadero = Invernadero.objects.filter(nombre_invernadero__iexact=NOMBRE_DEL_INVERNADERO_SIN_AGRONOMO).first()
    if invernadero is None:
        localidad = Localidad.objects.filter(nombre_localidad="Garupá").first() or Localidad.objects.first()
        invernadero = servicio_invernaderos.alta_invernadero(
            gerente,
            NOMBRE_DEL_INVERNADERO_SIN_AGRONOMO,
            tipo_direccion="urbana",
            localidad_id=localidad.pk,
            calle="Calle 2",
            numero_calle="200",
        )
        creado.append(f"Invernadero «{NOMBRE_DEL_INVERNADERO_SIN_AGRONOMO}» (sin Agrónomo y sin sistema IoT: lo opera el Gerente).")
    return invernadero


def _valor_de_la_lectura(sensor, minuto_del_dia):
    """Una temperatura de 20 a 23 °C (dentro del umbral efectivo) o, en la luz, 15.000 lux de 8 a 18 h y 100 lux el resto (de noche no se compara)."""
    if sensor.tipo_variable_sensor == "intensidad_luz":
        return Decimal(15000 if 8 * 60 <= minuto_del_dia < 18 * 60 else 100)
    return Decimal(20 + (minuto_del_dia // PASO_EN_MINUTOS) % 4)


def _lecturas_de_los_dias(sistema, creado):
    """Las lecturas de ayer (temperatura y luz) y de anteayer (temperatura) de «Norte»: un día entero, una cada ``PASO_EN_MINUTOS`` minutos, por el servicio de la API de IOT-03 con su ``ahora`` simulado (10 s
    después de cada medición, así nunca está atrasada ni es futura). Si el día ya tiene lecturas (de una corrida anterior o reales de Node-RED), solo se completan los instantes que faltan."""
    zona = timezone.get_current_timezone()
    hoy = timezone.localdate()
    contexto = servicio_lecturas.contexto_del_mensaje(sistema, timezone.now())
    por_cargar = [
        (sensor, hoy - timedelta(days=atras))
        for atras in range(1, DIAS_DE_TEMPERATURA + 1)
        for sensor in Sensor.objects.filter(sistema=sistema, estado_hardware="activo", tipo_variable_sensor__in=["temperatura", "intensidad_luz"]).order_by("pk")
        if atras == 1 or sensor.tipo_variable_sensor == "temperatura"
    ]
    for sensor, dia in sorted(por_cargar, key=lambda par: (par[1], par[0].pk)):  # en orden cronológico: el último mensaje de cada sensor queda en la última lectura
        inicio = datetime.combine(dia, time.min, tzinfo=zona)
        existentes = set(Telemetria.objects.filter(sensor=sensor, medida_en__gte=inicio, medida_en__lt=inicio + timedelta(days=1)).values_list("medida_en", flat=True))
        cargadas = 0
        for minuto in range(0, 24 * 60, PASO_EN_MINUTOS):
            medida = inicio + timedelta(minutes=minuto)
            if medida in existentes:
                continue  # completa el día: lo que ya hay (una corrida anterior o lecturas reales de Node-RED) no se repite
            lectura = LecturaRecibida(cargadas, sensor.identificador_equipo, sensor.identificador_equipo, _valor_de_la_lectura(sensor, minuto), medida.isoformat())
            resultado = servicio_lecturas.registrar_lectura(contexto, lectura, medida + timedelta(seconds=10))
            if resultado.resultado != "aceptada":
                raise ErrorDeCarga(f"La lectura de {sensor.identificador_equipo} del {dia:%d/%m} a las {medida:%H:%M} no se aceptó: {resultado.motivo}.")
            cargadas += 1
        if cargadas:
            creado.append(f"{cargadas} lecturas de {sensor.identificador_equipo} del {dia:%d/%m}.")


def cargar(contrasena):
    """El cargador del IoT: ver el encabezado del archivo. Devuelve un ``ResumenDeCarga``. Nunca imprime ni devuelve la contraseña ni un token."""
    creado, cuentas, pendiente = [], [], []
    gerente = _gerente_activo()
    invernadero = Invernadero.objects.filter(nombre_invernadero__iexact=NOMBRE_DEL_INVERNADERO).first()
    if invernadero is not None and invernadero.agronomo_id is not None:
        # «Norte» ya existe (de una corrida anterior o armado a mano): se sigue con SU Agrónomo, sin crear cuentas nuevas.
        agronomo = Agronomo.objects.get(pk=invernadero.agronomo_id)
        cuentas.append(f"{agronomo.email} · Agrónomo (el de «{NOMBRE_DEL_INVERNADERO}»)")
    else:
        agronomo_usuario = _cuenta(gerente, "agronomo", "Agrónomo", contrasena, creado, cuentas)
        capataz_usuario = _cuenta(gerente, "capataz", "Capataz", contrasena, creado, cuentas)
        agronomo = Agronomo.objects.get(pk=agronomo_usuario.pk)
        capataz = Capataz.objects.get(pk=capataz_usuario.pk)
        invernadero = _invernadero(gerente, agronomo, capataz, creado)
    sector = _sector(agronomo, invernadero, creado)
    _insumo_de_repuesto(agronomo, creado)
    variedad = _variedad(agronomo, creado)
    _semilla_con_stock(agronomo, invernadero, variedad, creado)
    _siembra_a_realizar(agronomo, invernadero, sector, variedad, creado)

    sistema = SistemaIoT.objects.filter(invernadero=invernadero).exclude(estado_sistema="inactivo").first()
    if sistema is None:
        pendiente.append(
            f"Entrá como {agronomo.email}, registrá el sistema IoT de «{NOMBRE_DEL_INVERNADERO}» en IoT · Sistema IoT (copiá el token: se "
            "muestra una sola vez) y volvé a correr este comando: carga el rango de la solución y los equipos."
        )
    else:
        _equipos(agronomo, sistema, sector, creado)
        _lecturas_de_los_dias(sistema, creado)
    _invernadero_sin_agronomo(gerente, creado)
    return verificacion.ResumenDeCarga(creado=tuple(creado), cuentas=tuple(cuentas), pendiente=tuple(pendiente))
