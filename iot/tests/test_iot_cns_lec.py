# Pruebas de IOT-CNS-LEC, el servicio del panel de monitoreo (IOT-04, paso 6; docs/casos_de_uso/iot/consultar_lecturas.md, reglas 1 a 8, 10 y 12 y «Servicio», «Situación de un sensor»,
# «Tarjeta de un sensor», «Gráficos», «Actuadores»; D-75 punto 7; D-76). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`). La regla 9 (refresco cada 30 s) y
# la 11 (acciones solo a quien opera) son de la pantalla (paso 7).
#
# Servicio que se prueba: iot/servicios/monitoreo.py, ``panel(actor, invernadero_id, periodo, ahora) -> PanelDeMonitoreo`` (los campos de cada resultado están en el esqueleto).
# Solo lectura: no escribe, no audita, no dispara la revisión y hace una cantidad FIJA de consultas. ``ahora`` es siempre el mismo; ninguna prueba depende de la hora del día.
# El «hace cuánto» es el ``timesince`` de Django, que separa el número y la unidad con un espacio de no separación (`` ``): «10 minutos».
# Umbral efectivo de las pruebas (``variedades_presentes_de_prueba``, docs/api/variedades.md): temperatura 18 a 24 °C, humedad 60 a 80 % HR, luz 200 a 400 lux y fotoperíodo
# de 12 a 16 h; horario de luz de 8 a 18 h.

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.models import AlertaIot, FotoperiodoDiario, Hardware, NodoCentral, ResumenHorario
from iot.tests import fabricas
from maestros.models import PARAMETROS_IOT, Alerta, ConfiguracionOperativa
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero, crear_sector

monitoreo = perezoso("iot.servicios.monitoreo")
alertas_iot = perezoso("iot.servicios.alertas_iot")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")


def local(dia, hora=0, minuto=0):
    """Una hora local de noviembre de 2026."""
    return datetime(2026, 11, dia, hora, minuto, tzinfo=LOCAL)


AHORA = local(23, 12)  # lunes, mediodía: hoy es el 23/11 y ayer, el 22/11
SIN_RANGO = dict(valor_calibracion_min=0, valor_calibracion_max=100000)  # la calibración de un sensor de luz


class IotCnsLecServicioTests(fabricas.ConCatalogoIot, TestCase):
    """`panel`: lo que muestra la pantalla de monitoreo, regla por regla."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.comunicacion_hace(1)  # el nodo está «en línea» salvo que la prueba diga otra cosa

    # ---- ayudas ----

    def comunicacion_hace(self, minutos):
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=None if minutos is None else AHORA - timedelta(minutes=minutos))

    def panel(self, actor=None, invernadero=None, periodo=24, ahora=AHORA):
        return monitoreo.panel(actor or self.laura, (invernadero or self.norte).pk, periodo, ahora)

    def con_umbral(self, *variedades):
        """El umbral efectivo de Norte: el de las variedades dadas (por omisión, una con los rangos de arriba)."""
        variedades = variedades or (variedad_con_semilla(nombre="Crespa"),)
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {v.pk for v in variedades}}))

    def lectura(self, sensor, valor="22", hace=1, **extra):
        """Una lectura de ``sensor`` hace ``hace`` minutos, que además es su último mensaje."""
        momento = AHORA - timedelta(minutes=hace)
        Hardware.objects.filter(pk=sensor.pk).update(ultimo_mensaje_en=momento)
        return fabricas.telemetria(sensor, valor, medida_en=momento, **extra)

    def luz(self, identificador="norte/sectorA/luz", **extra):
        return fabricas.sensor(self.sistema, identificador, "intensidad_luz", **(SIN_RANGO | extra))

    def tarjetas(self, panel):
        """``{id del sensor: TarjetaDeSensor}`` de todos los grupos."""
        return {t.sensor.pk: t for grupo in panel.grupos for t in grupo.tarjetas}

    def tarjeta(self, sensor, **kwargs):
        return self.tarjetas(self.panel(**kwargs))[sensor.pk]

    def situacion(self, sensor, **kwargs):
        return self.tarjeta(sensor, **kwargs).situacion

    def activa(self, tipo, clave, descripcion="alerta", **origen):
        return alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, tipo, clave, descripcion, **origen).alerta

    # ---- regla 1: alcance ----

    def test_regla_1_el_agronomo_consulta_su_invernadero_y_lo_opera(self):
        """Regla 1 (el de IOT-CNS-HDW; MD-98): el Agrónomo consulta los invernaderos a su cargo; el panel dice que lo opera."""
        panel = self.panel(self.laura)
        self.assertEqual(panel.invernadero, self.norte)
        self.assertTrue(panel.opera)

    def test_regla_1_el_gerente_consulta_todos_y_opera_solo_los_sin_agronomo(self):
        """Regla 1 y MD-98: el Gerente consulta todo y opera solo los invernaderos sin Agrónomo activo; con uno activo, el panel es de solo consulta."""
        sur = crear_invernadero("Sur")
        fabricas.sistema(sur)
        self.assertFalse(self.panel(self.gerente).opera)
        self.assertTrue(self.panel(self.gerente, sur).opera)

    def test_regla_1_un_invernadero_fuera_del_alcance_o_inexistente_da_404(self):
        """Regla 1 y D-28: el de otro Agrónomo (o uno que no existe) es `Http404`, sin revelar si existe."""
        ajeno = crear_invernadero("Sur", agronomo=crear_agronomo("sur@infoponia.com"))
        fabricas.sistema(ajeno)
        with self.assertRaises(Http404):
            self.panel(self.laura, ajeno)
        with self.assertRaises(Http404):
            monitoreo.panel(self.laura, 999999, 24, AHORA)

    def test_regla_1_los_otros_roles_reciben_403(self):
        """Precondición a y regla 1: solo el Agrónomo y el Gerente activos; un Capataz (y una cuenta inactiva) es `PermissionDenied`."""
        with self.assertRaises(PermissionDenied):
            self.panel(crear_capataz_activo())

    # ---- precondición b: sin sistema ----

    def test_precondicion_b_un_invernadero_sin_sistema_no_tiene_panel_y_ofrece_registrar_a_quien_opera(self):
        """Precondición b y bloque «Sin sistema»: sin sistema no dado de baja, el panel viene vacío y `puede_registrar` es verdadero solo para quien opera el invernadero
        (el Agrónomo; el Gerente solo si no tiene Agrónomo activo)."""
        con_agronomo = crear_invernadero("Libre", agronomo=self.laura)
        sin_agronomo = crear_invernadero("Sin Agrónomo")
        self.assertIsNone(self.panel(self.laura, con_agronomo).sistema)
        self.assertTrue(self.panel(self.laura, con_agronomo).puede_registrar)
        self.assertFalse(self.panel(self.gerente, con_agronomo).puede_registrar)
        self.assertTrue(self.panel(self.gerente, sin_agronomo).puede_registrar)
        vacio = self.panel(self.laura, con_agronomo)
        self.assertEqual((vacio.grupos, vacio.actuadores, vacio.alertas), ([], [], []))

    def test_precondicion_b_un_sistema_dado_de_baja_cuenta_como_sin_sistema(self):
        """Precondición b: el sistema tiene que estar «activo» o «desconectado»; uno dado de baja (inactivo) no tiene panel."""
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save(update_fields=["estado_sistema"])
        self.assertIsNone(self.panel().sistema)

    # ---- regla 2: el nodo ----

    def test_regla_2_muestra_el_sistema_la_conectividad_el_modo_y_la_ultima_comunicacion(self):
        """Regla 2: del nodo se ven el estado del sistema, su conectividad («en línea» o «sin señal»), su modo y la fecha y hora de su última comunicación."""
        panel = self.panel()
        self.assertEqual(panel.sistema, self.sistema)
        self.assertEqual((panel.conectividad.estado, panel.nodo.modo), ("en_linea", "remoto"))
        self.assertEqual(panel.nodo.ultima_comunicacion, AHORA - timedelta(minutes=1))
        self.assertEqual(panel.avisos, [])
        self.comunicacion_hace(10)
        self.assertEqual(self.panel().conectividad.estado, "sin_senal")

    def test_regla_2_un_sistema_desconectado_lo_avisa_y_muestra_los_ultimos_datos(self):
        """Regla 2: «si el sistema está desconectado, el panel lo avisa y muestra los últimos datos recibidos» (el texto de «Avisos»)."""
        sensor = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        self.lectura(sensor, "22")
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        panel = self.panel()
        self.assertIn(
            monitoreo.Aviso("warn", "Sistema desconectado. InfoPonia no recibe lecturas ni emite comandos hasta que se active; se muestran los últimos datos recibidos."),
            panel.avisos,
        )
        self.assertEqual(self.tarjetas(panel)[sensor.pk].texto_del_valor, "22 °C")

    def test_regla_2_un_nodo_que_nunca_se_comunico_lo_avisa_distinto_que_uno_sin_senal(self):
        """«Avisos»: sin señal, nunca: «El nodo todavía no se comunicó…»; sin señal después de haberse comunicado: «El nodo no se comunica desde {hace cuánto}…»."""
        self.comunicacion_hace(None)
        self.assertEqual(
            self.panel().avisos,
            [monitoreo.Aviso("info", "El nodo todavía no se comunicó. Cargale la dirección de la API y el token; cuando se comunique pasará a «En línea».")],
        )
        self.comunicacion_hace(10)
        self.assertEqual(
            self.panel().avisos, [monitoreo.Aviso("danger", "El nodo no se comunica desde hace 10 minutos. Los valores son los últimos recibidos.")]
        )

    def test_regla_2_el_modo_local_avisa_que_infoponia_no_evalua_reglas_ni_entrega_comandos(self):
        """Regla 2: «si el nodo informa el modo "local", el panel avisa que InfoPonia no evalúa reglas ni entrega comandos hasta que vuelva a "remoto"»."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        self.assertEqual(
            self.panel().avisos,
            [
                monitoreo.Aviso(
                    "warn",
                    "El nodo está operando en modo local. Actúa por su cuenta con su control de seguridad. InfoPonia sigue registrando lecturas y alertas, "
                    "pero no evalúa reglas ni entrega comandos hasta que vuelva a «remoto».",
                )
            ],
        )

    # ---- regla 3: los sensores ----

    def test_regla_3_los_sensores_se_agrupan_por_variable_sin_los_dados_de_baja(self):
        """Regla 3: «los sensores se agrupan por variable», en el orden temperatura, humedad, intensidad lumínica, temperatura de la solución y nivel; solo las variables con
        sensores; sin los dados de baja; cada grupo, sus tarjetas por identificador."""
        fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        fabricas.sensor(self.sistema, "norte/sectorB/temperatura")
        fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        fabricas.sensor(self.sistema, "norte/sectorA/humedad", "humedad")
        fabricas.sensor(self.sistema, "norte/vieja/luz", "intensidad_luz", estado="inactivo", **SIN_RANGO)
        panel = self.panel()
        self.assertEqual([g.variable for g in panel.grupos], ["temperatura", "humedad", "nivel_solucion"])
        self.assertEqual([g.nombre for g in panel.grupos], ["Temperatura", "Humedad", "Nivel de la solución"])
        self.assertEqual([t.sensor.identificador_equipo for t in panel.grupos[0].tarjetas], ["norte/sectorA/temperatura", "norte/sectorB/temperatura"])

    def test_regla_6_el_subtitulo_de_cada_grupo_dice_el_umbral_o_el_rango_que_lo_compara(self):
        """Regla 3 y 6: temperatura, humedad e intensidad lumínica, frente al umbral efectivo (la luz, «se evalúa de 8 a 18 h»); la temperatura de la solución, frente al rango del
        sistema; el nivel no se compara."""
        self.con_umbral()
        fabricas.sensor(self.sistema, "norte/temperatura")
        fabricas.sensor(self.sistema, "norte/humedad", "humedad")
        self.luz()
        fabricas.sensor(self.sistema, "norte/solucion", "temperatura_solucion")
        fabricas.sensor(self.sistema, "norte/nivel", "nivel_solucion")
        self.sistema.temp_solucion_min, self.sistema.temp_solucion_max = Decimal("18.0"), Decimal("24.0")
        self.sistema.save(update_fields=["temp_solucion_min", "temp_solucion_max"])
        subtitulos = {g.variable: g.subtitulo for g in self.panel().grupos}
        self.assertEqual(subtitulos["temperatura"], "Umbral efectivo 18 a 24 °C")
        self.assertEqual(subtitulos["humedad"], "Umbral efectivo 60 a 80 % HR")
        self.assertEqual(subtitulos["intensidad_luz"], "Umbral efectivo 200 a 400 lux · se evalúa de 8 a 18 h")
        self.assertEqual(subtitulos["temperatura_solucion"], "Rango del invernadero 18 a 24 °C")
        self.assertEqual(subtitulos["nivel_solucion"], "")

    def test_regla_6_sin_umbral_ni_rango_el_subtitulo_lo_dice(self):
        """Regla 6 y «Situación de un sensor»: sin umbral efectivo, «Sin umbral efectivo»; sin rango de la solución, «Sin rango definido»."""
        fabricas.sensor(self.sistema, "norte/temperatura")
        fabricas.sensor(self.sistema, "norte/solucion", "temperatura_solucion")
        subtitulos = {g.variable: g.subtitulo for g in self.panel().grupos}
        self.assertEqual((subtitulos["temperatura"], subtitulos["temperatura_solucion"]), ("Sin umbral efectivo", "Sin rango definido"))

    # -- la tabla «Situación de un sensor», fila por fila, en su orden --

    def test_regla_3_fila_1_un_sensor_del_que_nunca_llego_un_mensaje_esta_sin_confirmar(self):
        """Situación, fila 1: `ultimo_mensaje_en` nulo → «Sin confirmar» (gris)."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("sin_confirmar", "Sin confirmar", "neutral"))

    def test_regla_3_fila_2_un_sensor_fuera_de_servicio_lo_dice_en_rojo(self):
        """Situación, fila 2: el sensor está fuera de servicio → «Fuera de servicio» (rojo)."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura", estado="fuera_de_servicio")
        self.lectura(sensor)
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("fuera_de_servicio", "Fuera de servicio", "danger"))

    def test_regla_3_fila_3_con_el_nodo_sin_senal_los_valores_estan_desactualizados(self):
        """Situación, fila 3: el nodo está «sin señal» → «Desactualizado» (amarillo; los valores son los últimos recibidos)."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.lectura(sensor)
        self.comunicacion_hace(10)
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("desactualizado", "Desactualizado", "warn"))

    def test_regla_3_fila_4_con_la_alerta_sin_actividad_dice_cuantos_minutos(self):
        """Situación, fila 4: tiene activa «dispositivo sin actividad» → «Sin actividad · {n} min» (amarillo), con los minutos desde su último mensaje."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.lectura(sensor, hace=30)
        self.activa("iot_dispositivo_sin_actividad", f"hw:{sensor.pk}", hardware=sensor)
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("sin_actividad", "Sin actividad · 30 min", "warn"))

    def test_regla_3_fila_5_una_ultima_lectura_invalida_lo_dice(self):
        """Situación, fila 5 y regla 3 («una lectura fuera del rango de calibración se muestra como lectura inválida»): → «Lectura inválida» (amarillo)."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.lectura(sensor, "999", valida=False)
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("lectura_invalida", "Lectura inválida", "warn"))

    def test_regla_3_fila_6_el_nivel_de_la_solucion_es_normal_o_bajo(self):
        """Situación, fila 6: nivel de la solución → «Nivel bajo» (rojo) o «Normal» (verde)."""
        normal = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        bajo = fabricas.sensor(self.sistema, "norte/tanque2/nivel", "nivel_solucion")
        self.lectura(normal, hace=2)
        self.lectura(bajo, hace=3, estado_nivel_medido="bajo")
        tarjetas = self.tarjetas(self.panel())
        self.assertEqual(tarjetas[normal.pk].situacion, monitoreo.Situacion("normal", "Normal", "ok"))
        self.assertEqual(tarjetas[bajo.pk].situacion, monitoreo.Situacion("nivel_bajo", "Nivel bajo", "danger"))

    def test_regla_3_fila_7_la_luz_fuera_del_horario_de_luz_no_se_compara(self):
        """Situación, fila 7 y regla 3 («las lecturas de intensidad lumínica fuera del horario de luz se muestran sin compararlas»): la última lectura es de las 22:00 → «Fuera del
        horario de luz» (gris), aunque esté fuera del umbral."""
        self.con_umbral()
        luz = self.luz()
        self.lectura(luz, "50000", hace=14 * 60)  # las 22:00 del 22/11
        self.assertEqual(self.situacion(luz), monitoreo.Situacion("fuera_del_horario_de_luz", "Fuera del horario de luz", "neutral"))

    def test_regla_8_un_sensor_ambiental_de_un_sector_fuera_de_servicio_no_se_compara(self):
        """Situación, fila 8 y regla 8 (D-75 punto 7): una variable ambiental en un sector fuera de servicio → «Sector fuera de servicio» (gris, sin comparar), y la tarjeta
        lleva esa marca."""
        self.con_umbral()
        sector = crear_sector(self.norte, estado="fuera_de_servicio")
        sensor = fabricas.sensor(self.sistema, "norte/sectorA/temperatura", sector=sector)
        self.lectura(sensor, "30")
        tarjeta = self.tarjeta(sensor)
        self.assertEqual(tarjeta.situacion, monitoreo.Situacion("sector_fuera_de_servicio", "Sector fuera de servicio", "neutral"))
        self.assertTrue(tarjeta.sector_fuera_de_servicio)

    def test_regla_8_un_sensor_de_la_solucion_en_un_sector_fuera_de_servicio_se_sigue_comparando(self):
        """Regla 8 y D-75 punto 7: la temperatura de la solución es del tanque, no del ambiente: se compara igual (y lleva la marca de sector fuera de servicio)."""
        self.sistema.temp_solucion_min, self.sistema.temp_solucion_max = Decimal("18.0"), Decimal("24.0")
        self.sistema.save(update_fields=["temp_solucion_min", "temp_solucion_max"])
        sector = crear_sector(self.norte, estado="fuera_de_servicio")
        sensor = fabricas.sensor(self.sistema, "norte/tanque1/temp", "temperatura_solucion", sector=sector)
        self.lectura(sensor, "30")
        tarjeta = self.tarjeta(sensor)
        self.assertEqual(tarjeta.situacion.clave, "supera_maximo")
        self.assertTrue(tarjeta.sector_fuera_de_servicio)

    def test_regla_3_fila_9_sin_umbral_o_sin_rango_no_hay_con_que_comparar(self):
        """Situación, fila 9: sin umbral efectivo (variables ambientales) → «Sin umbral efectivo»; sin rango de la solución → «Sin rango definido» (gris)."""
        ambiental = fabricas.sensor(self.sistema, "norte/temperatura")
        solucion = fabricas.sensor(self.sistema, "norte/solucion", "temperatura_solucion")
        self.lectura(ambiental, "22", hace=1)
        self.lectura(solucion, "22", hace=2)
        tarjetas = self.tarjetas(self.panel())
        self.assertEqual(tarjetas[ambiental.pk].situacion, monitoreo.Situacion("sin_umbral", "Sin umbral efectivo", "neutral"))
        self.assertEqual(tarjetas[solucion.pk].situacion, monitoreo.Situacion("sin_rango", "Sin rango definido", "neutral"))

    def test_regla_3_filas_10_y_11_se_compara_la_ultima_lectura_con_el_umbral_actual_sin_histeresis(self):
        """Situación, filas 10 y 11 («es lo que "queda" ahora»): la última lectura contra el umbral actual, SIN histéresis: 24,5 supera el máximo (24), 17,9 queda bajo el
        mínimo (18) y los límites mismos (18 y 24) están «En rango»."""
        self.con_umbral()
        casos = {"24.5": "supera_maximo", "17.9": "bajo_el_minimo", "24": "en_rango", "18": "en_rango", "21": "en_rango"}
        for valor, clave in casos.items():
            with self.subTest(valor=valor):
                sensor = fabricas.sensor(self.sistema, f"norte/t{valor}")
                self.lectura(sensor, valor)
                self.assertEqual(self.situacion(sensor).clave, clave)
        sensor = fabricas.sensor(self.sistema, "norte/t-textos")
        self.lectura(sensor, "24.5")
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("supera_maximo", "Supera el máximo", "danger"))
        self.lectura(sensor, "17", hace=0)
        self.assertEqual(self.situacion(sensor), monitoreo.Situacion("bajo_el_minimo", "Bajo el mínimo", "danger"))

    def test_regla_3_la_primera_condicion_que_corresponde_manda(self):
        """«La primera que corresponda, en este orden»: un sensor sin confirmar Y fuera de servicio dice «Sin confirmar» (fila 1); uno fuera de servicio con la alerta sin
        actividad, «Fuera de servicio» (fila 2); uno desactualizado con lectura inválida, «Desactualizado» (fila 3)."""
        sin_confirmar = fabricas.sensor(self.sistema, "norte/a", estado="fuera_de_servicio")
        fuera = fabricas.sensor(self.sistema, "norte/b", estado="fuera_de_servicio")
        self.lectura(fuera, hace=30)
        self.activa("iot_dispositivo_sin_actividad", f"hw:{fuera.pk}", hardware=fuera)
        desactualizado = fabricas.sensor(self.sistema, "norte/c")
        self.lectura(desactualizado, "999", valida=False)
        self.comunicacion_hace(10)
        tarjetas = self.tarjetas(self.panel())
        self.assertEqual(
            [tarjetas[s.pk].situacion.clave for s in (sin_confirmar, fuera, desactualizado)], ["sin_confirmar", "fuera_de_servicio", "desactualizado"]
        )

    def test_regla_3_sensores_con_problema_cuenta_los_rojos(self):
        """Situación («"Sensores con problema" cuenta los rojos»): supera el máximo, nivel bajo y fuera de servicio cuentan; en rango y sin confirmar no. «de N»: los sensores
        no dados de baja."""
        self.con_umbral()
        supera = fabricas.sensor(self.sistema, "norte/a")
        self.lectura(supera, "30")
        bajo = fabricas.sensor(self.sistema, "norte/b", "nivel_solucion")
        self.lectura(bajo, hace=2, estado_nivel_medido="bajo")
        fuera = fabricas.sensor(self.sistema, "norte/c", estado="fuera_de_servicio")
        self.lectura(fuera, hace=3)
        bien = fabricas.sensor(self.sistema, "norte/d")
        self.lectura(bien, "20", hace=4)
        fabricas.sensor(self.sistema, "norte/e")
        fabricas.sensor(self.sistema, "norte/f", estado="inactivo")
        panel = self.panel()
        self.assertEqual((panel.indicadores.sensores_con_problema, panel.indicadores.sensores), (3, 5))
        self.assertEqual({g.variable: g.con_problema for g in panel.grupos}, {"temperatura": 2, "nivel_solucion": 1})

    # -- la tarjeta de un sensor --

    def test_regla_3_la_tarjeta_muestra_el_ultimo_valor_con_su_unidad_y_hace_cuanto(self):
        """Tarjeta: el último valor con su unidad y «hace N min» («—» si no tiene); el nivel se muestra como «Normal» o «Bajo»."""
        con_lectura = fabricas.sensor(self.sistema, "norte/a")
        sin_lectura = fabricas.sensor(self.sistema, "norte/b")
        self.lectura(con_lectura, "24.5", hace=5)
        tarjetas = self.tarjetas(self.panel())
        self.assertEqual((tarjetas[con_lectura.pk].texto_del_valor, tarjetas[con_lectura.pk].hace), ("24,5 °C", "5 minutos"))
        self.assertEqual((tarjetas[sin_lectura.pk].texto_del_valor, tarjetas[sin_lectura.pk].hace), ("—", ""))

    def test_regla_3_la_luz_muestra_el_fotoperiodo_de_ayer_en_cada_uno_de_sus_estados(self):
        """Regla 3 y «Tarjeta de un sensor»: de cada sensor de luz, el fotoperíodo del último día completo (ayer, 22/11) frente al rango del umbral efectivo: «En rango»,
        «Fuera de rango», «Incompleto», «Sin umbral» y, si no está calculado, «Sin calcular (corre en la revisión periódica)»."""
        luces = {nombre: self.luz(f"norte/{nombre}") for nombre in ("en_rango", "fuera", "incompleto", "sin_calcular")}
        for nombre, horas, incompleto in (("en_rango", "13", False), ("fuera", "10", False), ("incompleto", "10", True)):
            FotoperiodoDiario.objects.create(sensor=luces[nombre], fecha=date(2026, 11, 22), horas=Decimal(horas), incompleto=incompleto)
        FotoperiodoDiario.objects.create(sensor=luces["en_rango"], fecha=date(2026, 11, 21), horas=Decimal("1"))  # no es el de ayer
        self.con_umbral()
        resultado = {n: self.tarjeta(s).fotoperiodo for n, s in luces.items()}
        self.assertEqual(resultado["en_rango"], monitoreo.FotoperiodoDeAyer("en_rango", "Fotoperíodo de ayer: 13 h"))
        self.assertEqual(resultado["fuera"], monitoreo.FotoperiodoDeAyer("fuera_de_rango", "Fotoperíodo de ayer: 10 h"))
        self.assertEqual(resultado["incompleto"], monitoreo.FotoperiodoDeAyer("incompleto", "Fotoperíodo de ayer: 10 h"))
        self.assertEqual(resultado["sin_calcular"], monitoreo.FotoperiodoDeAyer("sin_calcular", "Sin calcular (corre en la revisión periódica)"))

    def test_regla_3_el_fotoperiodo_sin_umbral_efectivo_dice_sin_umbral(self):
        """«Tarjeta»: con el fotoperíodo calculado pero sin umbral efectivo, «Sin umbral»; un sensor que no es de luz no tiene fotoperíodo."""
        luz = self.luz()
        temperatura = fabricas.sensor(self.sistema, "norte/temperatura")
        FotoperiodoDiario.objects.create(sensor=luz, fecha=date(2026, 11, 22), horas=Decimal("10"))
        tarjetas = self.tarjetas(self.panel())
        self.assertEqual(tarjetas[luz.pk].fotoperiodo, monitoreo.FotoperiodoDeAyer("sin_umbral", "Fotoperíodo de ayer: 10 h"))
        self.assertIsNone(tarjetas[temperatura.pk].fotoperiodo)

    # ---- regla 4: gráficos y período ----

    def test_regla_4_hasta_24_horas_se_grafican_las_lecturas_validas_del_periodo_en_orden(self):
        """Regla 4 y «Gráficos»: hasta 24 horas, las lecturas VÁLIDAS del período, en orden (las inválidas y las anteriores al período quedan afuera)."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        for valor, hace, extra in (("20", 30 * 60, {}), ("21", 90, {}), ("22", 40, {}), ("999", 30, {"valida": False}), ("23", 10, {})):
            self.lectura(sensor, valor, hace=hace, **extra)
        self.assertEqual(self.tarjeta(sensor, periodo=24).serie, [Decimal("21"), Decimal("22"), Decimal("23")])
        self.assertEqual(self.tarjeta(sensor, periodo=6).serie, [Decimal("21"), Decimal("22"), Decimal("23")])
        self.assertEqual(self.tarjeta(sensor, periodo=1).serie, [Decimal("22"), Decimal("23")])

    def test_regla_4_siete_y_treinta_dias_usan_los_resumenes_horarios_y_no_las_lecturas(self):
        """Regla 4: los últimos 7 o 30 días se grafican con los resúmenes horarios (mínimo, promedio y máximo de cada hora, en orden), sin las lecturas. Los resúmenes anteriores
        al período no entran; `resumido` lo dice."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.lectura(sensor, "50")
        for hace_horas, minimo, promedio, maximo in ((24 * 20, 1, 2, 3), (24 * 3, 10, 11, 12), (5, 20, 21, 22)):
            ResumenHorario.objects.create(
                sensor=sensor, hora=local(23, 11) - timedelta(hours=hace_horas), minimo=Decimal(minimo), promedio=Decimal(promedio), maximo=Decimal(maximo)
            )
        panel7 = self.panel(periodo=168)
        self.assertTrue(panel7.resumido)
        self.assertEqual(self.tarjetas(panel7)[sensor.pk].serie, [(Decimal("10"), Decimal("11"), Decimal("12")), (Decimal("20"), Decimal("21"), Decimal("22"))])
        panel30 = self.panel(periodo=720)
        self.assertEqual(len(self.tarjetas(panel30)[sensor.pk].serie), 3)
        self.assertFalse(self.panel(periodo=24).resumido)

    def test_regla_4_un_resumen_sin_valores_validos_no_se_grafica(self):
        """«Una hora solo con inválidas deja los tres nulos» (IOT-ENT-INF): ese resumen no tiene qué graficar y se omite."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        ResumenHorario.objects.create(sensor=sensor, hora=local(23, 10), minimo=None, promedio=None, maximo=None, cantidad_lecturas=1, cantidad_invalidas=1)
        self.assertEqual(self.tarjeta(sensor, periodo=168).serie, [])

    def test_regla_4_el_periodo_tiene_que_ser_uno_de_los_cinco(self):
        """Regla 4: la última hora, 6 o 24 horas, 7 o 30 días (1, 6, 24, 168 y 720); otro valor es un error de programación (`ValueError`); la vista lo reemplaza por el recordado."""
        self.assertEqual(list(monitoreo.PERIODOS), [1, 6, 24, 168, 720])
        with self.assertRaises(ValueError):
            self.panel(periodo=12)

    def test_regla_4_la_franja_es_la_del_umbral_o_el_rango_actual_y_sin_umbral_no_hay(self):
        """«Gráficos»: la franja es la del umbral efectivo (o la del rango de la solución) ACTUAL; sin umbral, no hay franja y el SVG no la dibuja."""
        temperatura = fabricas.sensor(self.sistema, "norte/temperatura")
        solucion = fabricas.sensor(self.sistema, "norte/solucion", "temperatura_solucion")
        for sensor in (temperatura, solucion):
            self.lectura(sensor, "21")
        self.sistema.temp_solucion_min, self.sistema.temp_solucion_max = Decimal("19.0"), Decimal("23.0")
        self.sistema.save(update_fields=["temp_solucion_min", "temp_solucion_max"])
        sin_umbral = self.tarjetas(self.panel())
        self.assertEqual((sin_umbral[temperatura.pk].franja, sin_umbral[solucion.pk].franja), (None, (Decimal("19.0"), Decimal("23.0"))))
        self.assertNotIn("grafico-franja", sin_umbral[temperatura.pk].grafico)
        self.assertIn("grafico-franja", sin_umbral[solucion.pk].grafico)
        self.con_umbral()
        con_umbral = self.tarjetas(self.panel())
        self.assertEqual(con_umbral[temperatura.pk].franja, (Decimal("18"), Decimal("24")))
        self.assertIn("grafico-franja", con_umbral[temperatura.pk].grafico)

    def test_regla_4_el_nivel_no_tiene_grafico_y_dice_desde_cuando_informa_bajo(self):
        """Regla 4 («de cada sensor, salvo los de nivel de la solución») y «Tarjeta»: el nivel muestra «Informa "bajo" desde las HH:MM» (desde la lectura que originó la alerta,
        11:30) o «Nivel normal»."""
        bajo = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        normal = fabricas.sensor(self.sistema, "norte/tanque2/nivel", "nivel_solucion")
        origen = self.lectura(bajo, hace=30, estado_nivel_medido="bajo")
        self.lectura(bajo, hace=2, estado_nivel_medido="bajo")
        self.lectura(normal, hace=3)
        self.activa("iot_nivel_solucion_bajo", f"sensor:{bajo.pk}", telemetria=origen)
        tarjetas = self.tarjetas(self.panel())
        self.assertEqual((tarjetas[bajo.pk].grafico, tarjetas[bajo.pk].texto_del_nivel), (None, "Informa «bajo» desde las 11:30"))
        self.assertEqual((tarjetas[normal.pk].grafico, tarjetas[normal.pk].texto_del_nivel), (None, "Nivel normal"))

    def test_regla_4_un_sensor_sin_lecturas_en_el_periodo_dice_sin_lecturas(self):
        """«Gráficos»: «Sin datos en el período, "Sin lecturas en este período"»."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.assertIn("Sin lecturas en este período", self.tarjeta(sensor).grafico)

    # ---- regla 5: actuadores ----

    def test_regla_5_el_actuador_muestra_el_estado_que_informo_el_nodo_desde_cuando_y_si_cambio_en_el_invernadero(self):
        """Regla 5: el estado actual tal como lo informó el nodo, con su fecha y hora («Encendido desde las 11:45»), la marca «cambiado en el invernadero» y la compatibilidad
        con el nodo. Sin estado informado, «Desconocido»."""
        informado = fabricas.actuador(
            self.sistema, identificador="norte/ventilador", estado_informado="encendido", estado_informado_en=AHORA - timedelta(minutes=15),
            cambiado_en_invernadero=True, compatibilidad="compatible", ultimo_mensaje_en=AHORA - timedelta(minutes=15),
        )
        desconocido = fabricas.actuador(self.sistema, identificador="norte/ventana")
        filas = {f.actuador.pk: f for f in self.panel().actuadores}
        self.assertEqual((filas[informado.pk].estado_texto, filas[informado.pk].desde), ("Encendido", AHORA - timedelta(minutes=15)))
        self.assertTrue(filas[informado.pk].cambiado_en_invernadero)
        self.assertEqual(filas[informado.pk].compatibilidad, "Compatible")
        self.assertEqual((filas[desconocido.pk].estado_texto, filas[desconocido.pk].desde), ("Desconocido", None))
        self.assertFalse(filas[desconocido.pk].cambiado_en_invernadero)
        self.assertEqual(filas[desconocido.pk].compatibilidad, "Sin verificar")

    def test_regla_5_la_situacion_del_actuador_en_su_orden(self):
        """«Actuadores», situación en orden: «Fuera de servicio», «Sin confirmar», «Sin actividad» (con la alerta activa), «Configuración incompatible» y «Operativo»."""
        ahora = AHORA - timedelta(minutes=2)
        fuera = fabricas.actuador(self.sistema, identificador="norte/a", estado="fuera_de_servicio", ultimo_mensaje_en=ahora)
        sin_confirmar = fabricas.actuador(self.sistema, identificador="norte/b")
        sin_actividad = fabricas.actuador(self.sistema, identificador="norte/c", ultimo_mensaje_en=ahora)
        self.activa("iot_dispositivo_sin_actividad", f"hw:{sin_actividad.pk}", hardware=sin_actividad)
        incompatible = fabricas.actuador(self.sistema, identificador="norte/d", ultimo_mensaje_en=ahora, compatibilidad="incompatible")
        operativo = fabricas.actuador(self.sistema, identificador="norte/e", ultimo_mensaje_en=ahora, compatibilidad="compatible")
        filas = {f.actuador.pk: f.situacion for f in self.panel().actuadores}
        self.assertEqual(
            [filas[a.pk] for a in (fuera, sin_confirmar, sin_actividad, incompatible, operativo)],
            [
                monitoreo.Situacion("fuera_de_servicio", "Fuera de servicio", "danger"),
                monitoreo.Situacion("sin_confirmar", "Sin confirmar", "warn"),
                monitoreo.Situacion("sin_actividad", "Sin actividad", "warn"),
                monitoreo.Situacion("incompatible", "Configuración incompatible", "warn"),
                monitoreo.Situacion("operativo", "Operativo", "ok"),
            ],
        )

    def test_regla_5_los_indicadores_de_actuadores_cuentan_los_operativos_sobre_los_que_no_estan_dados_de_baja(self):
        """«Indicadores»: «Actuadores operativos» (de N, sin los dados de baja). «Comandos pendientes» no se muestra hasta IOT-05 (D-25: lo que no existe no se muestra)."""
        ahora = AHORA - timedelta(minutes=2)
        fabricas.actuador(self.sistema, identificador="norte/a", ultimo_mensaje_en=ahora)
        fabricas.actuador(self.sistema, identificador="norte/b", estado="fuera_de_servicio", ultimo_mensaje_en=ahora)
        fabricas.actuador(self.sistema, identificador="norte/c")
        fabricas.actuador(self.sistema, identificador="norte/d", estado="inactivo", ultimo_mensaje_en=ahora)
        panel = self.panel()
        self.assertEqual((panel.indicadores.actuadores_operativos, panel.indicadores.actuadores, len(panel.actuadores)), (1, 3, 3))
        self.assertFalse(hasattr(panel.indicadores, "comandos_pendientes"))

    # ---- regla 6: umbral efectivo, rango y parámetros ----

    def test_regla_6_el_umbral_trae_cada_limite_con_la_variedad_que_lo_fija_y_las_que_lo_componen(self):
        """Regla 6: el mínimo y el máximo de cada variable (temperatura ambiente, humedad, intensidad lumínica y fotoperíodo), con la variedad que fija cada límite y las
        variedades que lo componen. Crespa (18 a 24 °C) y Lisa (20 a 30 °C): mínimo 20 de Lisa, máximo 24 de Crespa."""
        self.con_umbral(variedad_con_semilla(nombre="Crespa"), variedad_con_semilla(nombre="Lisa", temp_ambiente_min="20", temp_ambiente_max="30"))
        umbral = self.panel().umbral
        self.assertTrue(umbral.hay)
        self.assertEqual([f.variable for f in umbral.filas], ["temp_ambiente", "humedad", "intensidad_luz", "fotoperiodo"])
        self.assertEqual([f.nombre for f in umbral.filas], ["Temperatura ambiente", "Humedad", "Intensidad lumínica", "Fotoperíodo"])
        temperatura = umbral.filas[0]
        self.assertEqual((temperatura.unidad, temperatura.minimo, temperatura.maximo), ("°C", Decimal("20"), Decimal("24")))
        self.assertEqual((temperatura.lo_limita_minimo, temperatura.lo_limita_maximo), ("Lisa", "Crespa"))
        self.assertEqual(umbral.variedades, ["Crespa", "Lisa"])

    def test_regla_6_sin_lotes_ni_siembras_el_invernadero_no_tiene_umbral_efectivo(self):
        """Regla 6: «si no hay lotes ni siembras, informa que el invernadero no tiene umbral efectivo»."""
        umbral = self.panel().umbral
        self.assertEqual((umbral.hay, umbral.filas, umbral.variedades), (False, [], []))

    def test_regla_6_el_rango_de_la_solucion_del_sistema_se_muestra_si_esta_definido(self):
        """Regla 6: «muestra también el rango de temperatura de la solución del sistema IoT, si está definido»."""
        self.assertIsNone(self.panel().umbral.rango_solucion)
        self.sistema.temp_solucion_min, self.sistema.temp_solucion_max = Decimal("18.0"), Decimal("24.0")
        self.sistema.save(update_fields=["temp_solucion_min", "temp_solucion_max"])
        self.assertEqual(self.panel().umbral.rango_solucion, (Decimal("18.0"), Decimal("24.0")))

    def test_regla_6_los_catorce_parametros_iot_en_solo_lectura_con_su_valor_vigente(self):
        """Regla 6: «en solo lectura, los parámetros IoT de la Configuración Operativa»: los 14, en el orden de MD-112, con el valor vigente (el panel lee la configuración en
        cada uso, regla 7 de ADM-MOD-CFG)."""
        self.assertEqual([p.campo for p in self.panel().parametros], [campo for campo, *_ in PARAMETROS_IOT])
        ConfiguracionOperativa.objects.filter(singleton=1).update(hora_fin_luz=20, histeresis_temperatura=Decimal("1.5"))
        valores = {p.campo: p.valor for p in self.panel().parametros}
        self.assertEqual((valores["hora_fin_luz"], valores["histeresis_temperatura"], valores["minutos_sin_actividad"]), (20, Decimal("1.5"), 5))
        self.assertTrue(all(p.etiqueta for p in self.panel().parametros))

    # ---- regla 7: las alertas activas ----

    def test_regla_7_solo_las_alertas_activas_del_iot_del_invernadero_ordenadas_por_severidad(self):
        """Regla 7: las alertas activas del sistema IoT del invernadero (no las resueltas, ni las de personal, ni las de otro invernadero), de la más urgente a la menos: crítica,
        advertencia, informativa. La severidad es la del tipo."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        informativa = self.activa("iot_dispositivo_no_registrado", "id:otro")
        advertencia = self.activa("iot_dispositivo_sin_actividad", f"hw:{sensor.pk}", hardware=sensor)
        critica = self.activa("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}")
        resuelta = self.activa("iot_lectura_invalida", f"hw:{sensor.pk}", hardware=sensor)
        alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_lectura_invalida", f"hw:{sensor.pk}")
        Alerta.objects.create(invernadero=self.norte, tipo_alerta="sin_capataz", descripcion_alerta="de personal", nivel_severidad="advertencia", agronomo=self.laura)
        panel = self.panel()
        self.assertEqual([f.alerta.pk for f in panel.alertas], [critica.pk, advertencia.pk, informativa.pk])
        self.assertEqual([f.severidad for f in panel.alertas], ["critica", "advertencia", "informativa"])
        self.assertEqual(panel.indicadores.alertas_activas, 3)
        self.assertNotIn(resuelta.pk, [f.alerta.pk for f in panel.alertas])

    def test_regla_7_cada_alerta_trae_su_enlace_y_si_se_notifico_por_correo(self):
        """«Alertas activas» del servicio: el `Enlace` de cada una (`enlaces_de_alertas`, una llamada para toda la lista) y «Notificada por correo» si `correo_enviado_en` no es nulo."""
        enviada = self.activa("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}", "Nodo de prueba · sin comunicación")
        AlertaIot.objects.filter(alerta=enviada).update(correo_enviado_en=AHORA)
        pendiente = self.activa("iot_dispositivo_no_registrado", "id:otro", "otro no registrado")
        filas = {f.alerta.pk: f for f in self.panel().alertas}
        self.assertTrue(filas[enviada.pk].notificada_por_correo)
        self.assertFalse(filas[pendiente.pk].notificada_por_correo)
        self.assertEqual(filas[enviada.pk].enlace.detalle, "Nodo de prueba · sin comunicación")
        self.assertTrue(filas[pendiente.pk].enlace.url)

    def test_regla_7_un_no_registrado_de_un_equipo_dado_de_baja_lo_indica(self):
        """Regla 7: «la alerta "dispositivo no registrado" de un identificador que era de un equipo dado de baja lo indica» (para ofrecer reactivarlo o registrar un reemplazo)."""
        baja = fabricas.sensor(self.sistema, "norte/vieja", estado="inactivo", fecha_baja=date(2026, 11, 20))
        de_baja = self.activa("iot_dispositivo_no_registrado", "id:norte/vieja")
        otro = self.activa("iot_dispositivo_no_registrado", "id:norte/nuevo")
        filas = {f.alerta.pk: f for f in self.panel().alertas}
        self.assertEqual(filas[de_baja.pk].equipo_dado_de_baja.pk, baja.pk)
        self.assertIsNone(filas[otro.pk].equipo_dado_de_baja)

    def test_regla_7_el_gerente_que_no_opera_ve_quien_recibe_las_alertas_del_invernadero(self):
        """Regla 7 y reparto de destinatarios de MAE-02 (R007; docs/api/alertas.md): las alertas del IoT las recibe el Agrónomo activo, y `consultar_alertas` le da al Gerente solo
        las suyas. Para no mostrarle un «0 alertas activas» engañoso, el Gerente que mira sin operar un invernadero con Agrónomo activo ve el aviso «Las alertas de este invernadero las
        recibe {nombre del Agrónomo}; vos las recibís si no tiene un Agrónomo activo.» (el Agrónomo sale del invernadero ya cargado)."""
        self.activa("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}")
        nombre = self.laura.get_full_name() or self.laura.email
        panel = self.panel(self.gerente)
        self.assertEqual(
            panel.aviso_de_alertas, f"Las alertas de este invernadero las recibe {nombre}; vos las recibís si no tiene un Agrónomo activo."
        )
        self.assertEqual(panel.alertas, [])

    def test_regla_7_el_aviso_de_quien_recibe_las_alertas_no_aparece_si_el_actor_las_recibe(self):
        """El aviso es solo para el Gerente que no opera: el Agrónomo (que recibe las alertas) no lo ve; y el Gerente de un invernadero sin Agrónomo, o con uno inactivo, opera
        el IoT, recibe las alertas, las ve y tampoco lo ve."""
        self.activa("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}")
        self.assertIsNone(self.panel(self.laura).aviso_de_alertas)
        sin_agronomo = crear_invernadero("Sin Agrónomo")
        sistema = fabricas.sistema(sin_agronomo)
        alerta = alertas_iot.asegurar_alerta_iot(sin_agronomo.pk, sistema, "iot_dispositivo_no_registrado", "id:otro", "otro").alerta
        panel = self.panel(self.gerente, sin_agronomo)
        self.assertIsNone(panel.aviso_de_alertas)
        self.assertEqual([f.alerta.pk for f in panel.alertas], [alerta.pk])
        inactivo = crear_agronomo("inactivo@infoponia.com")
        con_inactivo = crear_invernadero("Con Inactivo", agronomo=inactivo)
        sistema_inactivo = fabricas.sistema(con_inactivo)
        Usuario.objects.filter(pk=inactivo.pk).update(is_active=False)
        alerta_del_gerente = alertas_iot.asegurar_alerta_iot(con_inactivo.pk, sistema_inactivo, "iot_dispositivo_no_registrado", "id:otro", "otro").alerta
        panel = self.panel(self.gerente, con_inactivo)
        self.assertIsNone(panel.aviso_de_alertas)
        self.assertEqual([f.alerta.pk for f in panel.alertas], [alerta_del_gerente.pk])

    def test_regla_7_el_indicador_de_alertas_activas_coincide_con_la_lista_que_se_muestra(self):
        """Coherencia de «Indicadores» con «Alertas activas»: el número es el de la lista que se muestra a ese actor (las que él recibe), no el de todas las del invernadero: con
        tres alertas del IoT, el Agrónomo ve 3 y el Gerente que no opera ve 0 (y el aviso de arriba), nunca «3» sobre una lista vacía."""
        for i in range(3):
            self.activa("iot_dispositivo_no_registrado", f"id:otro{i}", f"otro{i}")
        del_agronomo, del_gerente = self.panel(self.laura), self.panel(self.gerente)
        self.assertEqual((del_agronomo.indicadores.alertas_activas, len(del_agronomo.alertas)), (3, 3))
        self.assertEqual((del_gerente.indicadores.alertas_activas, len(del_gerente.alertas)), (0, 0))

    # ---- regla 10, regla 12 y cantidad fija de consultas ----

    def test_regla_10_abrir_el_panel_no_dispara_la_revision_periodica(self):
        """Regla 10: «abrir el panel no dispara revisiones»: con un sensor y un nodo que llevan horas sin comunicarse, el panel los muestra pero NO genera las alertas «sin actividad»
        ni «nodo sin comunicación» (las genera `revision_iot`)."""
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.lectura(sensor, hace=600)
        self.comunicacion_hace(600)
        self.panel()
        self.assertFalse(Alerta.objects.exists())

    def test_regla_12_el_panel_no_escribe_ni_audita(self):
        """Regla 12 y postcondición a («la consulta no produce cambios»): ninguna sentencia `INSERT`, `UPDATE` ni `DELETE` y ningún registro de auditoría, en un panel con
        sensores, actuadores, alertas, umbral y resúmenes."""
        self.con_umbral()
        sensor = fabricas.sensor(self.sistema, "norte/temperatura")
        self.lectura(sensor, "30")
        ResumenHorario.objects.create(sensor=sensor, hora=local(23, 10), minimo=Decimal("1"), promedio=Decimal("2"), maximo=Decimal("3"))
        fabricas.actuador(self.sistema, identificador="norte/ventilador")
        self.activa("iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}")
        auditorias = RegistroAuditoria.objects.count()
        for periodo in (24, 168):
            with self.subTest(periodo=periodo):
                with CaptureQueriesContext(connection) as consultas:
                    self.panel(periodo=periodo)
                escrituras = [q["sql"] for q in consultas.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
                self.assertEqual(escrituras, [])
        self.assertEqual(RegistroAuditoria.objects.count(), auditorias)

    def test_regla_12_la_cantidad_de_consultas_es_la_misma_con_uno_y_con_cinco_sensores(self):
        """«Servicio» (cantidad fija de consultas): la misma cantidad con 1 sensor que con 5 (y con más actuadores y alertas): nada de una consulta por sensor, por actuador ni por
        alerta. Dos invernaderos sin Agrónomo (las alertas van al Gerente, que las opera), con el mismo umbral."""
        a, b = crear_invernadero("Uno"), crear_invernadero("Dos")
        sistema_a, sistema_b = fabricas.sistema(a), fabricas.sistema(b)
        variedad = variedad_con_semilla(nombre="Crespa")
        self.enterContext(variedades_presentes_de_prueba({a.pk: {variedad.pk}, b.pk: {variedad.pk}}))
        for sistema in (sistema_a, sistema_b):
            NodoCentral.objects.filter(sistema=sistema).update(ultima_comunicacion=AHORA - timedelta(minutes=1))

        def armar(invernadero, sistema, sensores, actuadores, alertas):
            variables = ["temperatura", "humedad", "intensidad_luz", "temperatura_solucion", "nivel_solucion"]
            creados = []
            for i in range(sensores):
                variable = variables[i % len(variables)]
                extra = SIN_RANGO if variable == "intensidad_luz" else {}
                sensor = fabricas.sensor(sistema, f"{invernadero.nombre_invernadero}/s{i}", variable, **extra)
                momento = AHORA - timedelta(minutes=i + 1)
                Hardware.objects.filter(pk=sensor.pk).update(ultimo_mensaje_en=momento)
                fabricas.telemetria(sensor, "21", medida_en=momento)
                creados.append(sensor)
            for i in range(actuadores):
                fabricas.actuador(sistema, identificador=f"{invernadero.nombre_invernadero}/a{i}", ultimo_mensaje_en=AHORA, estado_informado="encendido", estado_informado_en=AHORA)
            for i in range(alertas):
                alertas_iot.asegurar_alerta_iot(invernadero.pk, sistema, "iot_dispositivo_no_registrado", f"id:{invernadero.nombre_invernadero}{i}", f"otro{i}")

        armar(a, sistema_a, 1, 1, 1)
        armar(b, sistema_b, 5, 3, 4)

        def consultas(invernadero):
            with CaptureQueriesContext(connection) as contexto:
                self.panel(self.gerente, invernadero)
            return len(contexto)

        self.assertEqual(consultas(a), consultas(b))
        self.assertEqual(len(self.panel(self.gerente, b).alertas), 4)
