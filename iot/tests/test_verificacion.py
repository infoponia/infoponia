# Pruebas del cargador de datos de verificación del IoT (`iot/verificacion.py`; CLAUDE.md, «Datos para la verificación a mano»):
# la primera corrida deja «Norte» con umbral efectivo, la segunda carga los equipos del flujo de Node-RED cuando el sistema IoT ya se
# registró por la pantalla, nunca duplica y no pasa la contraseña ni un token por la salida ni por la auditoría.

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_administrador, crear_gerente
from inventario.servicios.variedades import umbral_efectivo
from core.verificacion import ErrorDeCarga
from iot import verificacion as cargador
from iot.models import Actuador, FotoperiodoDiario, Hardware, NodoCentral, Sensor, SistemaIoT, Telemetria
from iot.tests import fabricas
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero

CLAVE = "Prueba-98765x"


class IotVerificacionTests(fabricas.ConCatalogoIot, TestCase):
    """`iot.verificacion.cargar`: usa los servicios de las apps y es idempotente."""

    def setUp(self):
        self.gerente = crear_gerente()
        # Las lecturas de los días de IOT-04 son una cada 5 minutos (288 por día y sensor, por el servicio de la API): para que las pruebas no tarden, una por hora; la prueba del fotoperíodo usa el paso real.
        self.enterContext(mock.patch.object(cargador, "PASO_EN_MINUTOS", 60))

    def test_d_verificacion_primera_corrida_deja_norte_con_umbral_efectivo(self):
        """Primera corrida: cuentas de prueba, «Norte» con Agrónomo y Capataz y sin Técnico, y una siembra «a realizar» que da umbral efectivo."""
        resumen = cargador.cargar(CLAVE)
        norte = Invernadero.objects.get(nombre_invernadero="Norte")
        self.assertEqual(norte.agronomo.email, "agronomo@prueba3.local")
        self.assertEqual(norte.capataz.email, "capataz@prueba3.local")
        self.assertIsNone(norte.tecnico_id)
        self.assertTrue(Usuario.objects.get(email="agronomo@prueba3.local").check_password(CLAVE))
        self.assertIsNotNone(umbral_efectivo([norte.pk])[norte.pk])
        self.assertEqual(Hardware.objects.count(), 0)
        self.assertIn("agronomo@prueba3.local · Agrónomo", resumen.cuentas)

    def test_d_verificacion_sin_sistema_pide_registrarlo_por_pantalla(self):
        """Sin sistema IoT, el cargador no lo crea (el token se ve una sola vez en la pantalla) y lo dice como pendiente."""
        resumen = cargador.cargar(CLAVE)
        self.assertEqual(SistemaIoT.objects.count(), 0)
        self.assertEqual(len(resumen.pendiente), 1)
        self.assertIn("registrá el sistema IoT", resumen.pendiente[0])

    def test_d_verificacion_segunda_corrida_carga_los_equipos_del_flujo(self):
        """Con el sistema registrado: el rango de la solución 18,0 a 24,0 y los siete equipos de node-red/README.md, sección 4; ni `temp-vieja`."""
        cargador.cargar(CLAVE)
        norte = Invernadero.objects.get(nombre_invernadero="Norte")
        sistema = fabricas.sistema(norte)
        resumen = cargador.cargar(CLAVE)
        sistema.refresh_from_db()
        self.assertEqual((str(sistema.temp_solucion_min), str(sistema.temp_solucion_max)), ("18.0", "24.0"))
        self.assertEqual(
            sorted(Hardware.objects.filter(sistema=sistema).exclude(clase="nodo").values_list("identificador_equipo", flat=True)),
            sorted(
                [
                    "norte/sectorA/temperatura",
                    "norte/sectorA/humedad",
                    "norte/sectorA/luz",
                    "norte/tanque1/temp-solucion",
                    "norte/tanque1/nivel",
                    "norte/sectorA/ventilador",
                    "norte/sectorA/ventana",
                ]
            ),
        )
        self.assertEqual(Sensor.objects.filter(sistema=sistema).count(), 5)
        self.assertEqual(Actuador.objects.filter(sistema=sistema).count(), 2)
        self.assertEqual(resumen.pendiente, ())

    def test_d_verificacion_es_idempotente(self):
        """Correrlo otra vez no duplica cuentas, invernaderos, equipos ni siembras: la corrida repetida no crea nada."""
        cargador.cargar(CLAVE)
        fabricas.sistema(Invernadero.objects.get(nombre_invernadero="Norte"))
        cargador.cargar(CLAVE)
        cuentas, equipos = Usuario.objects.count(), Hardware.objects.count()
        resumen = cargador.cargar(CLAVE)
        self.assertEqual(resumen.creado, ())
        self.assertEqual((Usuario.objects.count(), Hardware.objects.count()), (cuentas, equipos))
        self.assertEqual(Invernadero.objects.filter(nombre_invernadero="Norte").count(), 1)

    def test_d_verificacion_no_toca_al_administrador_ni_deja_la_contrasena_en_la_auditoria(self):
        """El Administrador queda igual y ni la contraseña ni su resumen aparecen en un registro de auditoría."""
        administrador = crear_administrador()
        antes = administrador.password
        cargador.cargar(CLAVE)
        administrador.refresh_from_db()
        self.assertEqual(administrador.password, antes)
        self.assertFalse(any(CLAVE in str(registro.detalle) for registro in RegistroAuditoria.objects.all()))

    def test_d_verificacion_si_norte_ya_existe_sigue_con_su_agronomo_y_no_crea_cuentas(self):
        """Idempotencia ante un «Norte» armado antes (con otro Agrónomo): se usa el suyo, sin crear las cuentas de prueba3 ni tocar nada ajeno."""
        agronomo = crear_agronomo("otra@infoponia.com")
        crear_invernadero("Norte", agronomo=agronomo, capataz=crear_capataz_activo("cap@infoponia.com"))
        cuentas = Usuario.objects.count()
        resumen = cargador.cargar(CLAVE)
        self.assertEqual(Usuario.objects.count(), cuentas)
        self.assertFalse(Usuario.objects.filter(email__endswith="@prueba3.local").exists())
        self.assertEqual(Invernadero.objects.filter(nombre_invernadero="Norte").count(), 1)
        self.assertIn("otra@infoponia.com", resumen.cuentas[0])

    def test_d_verificacion_sin_gerente_frena_y_lo_dice(self):
        """Sin un Gerente activo no hay quien dé de alta las cuentas: se frena con un mensaje claro."""
        self.gerente.delete()
        with self.assertRaisesMessage(ErrorDeCarga, "No hay un Gerente activo"):
            cargador.cargar(CLAVE)


class IotVerificacionDeIot04Tests(fabricas.ConCatalogoIot, TestCase):
    """Lo que suma IOT-04 al cargador: el invernadero «Sur» sin Agrónomo ni sistema y las lecturas de ayer y de anteayer de «Norte»."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.enterContext(mock.patch.object(cargador, "PASO_EN_MINUTOS", 60))

    def con_el_sistema_registrado(self):
        cargador.cargar(CLAVE)
        sistema = fabricas.sistema(Invernadero.objects.get(nombre_invernadero="Norte"))
        cargador.cargar(CLAVE)
        return sistema

    def test_d_verificacion_sur_no_tiene_agronomo_ni_sistema_y_lo_opera_el_gerente(self):
        """«Sur»: sin Agrónomo y sin sistema IoT (el Gerente lo opera y ve «Registrar Sistema IoT»); «Norte», con Agrónomo, queda de solo consulta para el Gerente. Se crea en la primera corrida."""
        from iot.alcance import invernaderos_que_opera

        cargador.cargar(CLAVE)
        sur = Invernadero.objects.get(nombre_invernadero="Sur")
        self.assertIsNone(sur.agronomo_id)
        self.assertFalse(SistemaIoT.objects.filter(invernadero=sur).exists())
        operados = set(invernaderos_que_opera(self.gerente).values_list("nombre_invernadero", flat=True))
        self.assertEqual(operados, {"Sur"})

    def test_d_verificacion_las_lecturas_de_ayer_y_de_anteayer_no_se_cargan_sin_el_sistema(self):
        """Sin el sistema IoT registrado (primera corrida) no hay sensores ni lecturas: el cargador pide registrarlo por la pantalla."""
        cargador.cargar(CLAVE)
        self.assertEqual(Telemetria.objects.count(), 0)

    def test_d_verificacion_carga_un_dia_entero_de_la_temperatura_de_ayer_y_anteayer_y_de_la_luz_de_ayer(self):
        """Segunda corrida: ayer y anteayer de la temperatura y ayer de la luz, de las 00:00 a las 23:00 (una por hora en la prueba), nada de hoy ni de los demás sensores. El último mensaje de cada sensor
        es el de su última lectura (ayer) y el nodo sigue sin comunicación (nada de alerta crítica ni de correo antes de empezar). Los valores están dentro del umbral efectivo."""
        sistema = self.con_el_sistema_registrado()
        hoy = timezone.localdate()
        zona = timezone.get_current_timezone()

        def del_dia(sensor, dia):
            inicio = datetime.combine(dia, time.min, tzinfo=zona)
            return Telemetria.objects.filter(sensor=sensor, medida_en__gte=inicio, medida_en__lt=inicio + timedelta(days=1))

        temperatura = Sensor.objects.get(identificador_equipo="norte/sectorA/temperatura")
        luz = Sensor.objects.get(identificador_equipo="norte/sectorA/luz")
        self.assertEqual([del_dia(temperatura, hoy - timedelta(days=n)).count() for n in (1, 2)], [24, 24])
        self.assertEqual([del_dia(luz, hoy - timedelta(days=n)).count() for n in (1, 2)], [24, 0])
        self.assertEqual(del_dia(temperatura, hoy).count() + del_dia(luz, hoy).count(), 0)
        self.assertEqual(Telemetria.objects.exclude(sensor__in=[temperatura, luz]).count(), 0)
        self.assertEqual(set(Telemetria.objects.filter(sensor=temperatura).values_list("valor_medido", flat=True)) - {Decimal(v) for v in (20, 21, 22, 23)}, set())
        temperatura.refresh_from_db()
        self.assertEqual(temperatura.ultimo_mensaje_en, Telemetria.objects.filter(sensor=temperatura).order_by("-medida_en").first().medida_en + timedelta(seconds=10))
        self.assertIsNone(NodoCentral.objects.get(sistema=sistema).ultima_comunicacion)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="entrega_informacion_iot").count(), 0)  # ninguna lectura generó una alerta

    def test_d_verificacion_las_lecturas_se_cargan_una_sola_vez(self):
        """Idempotencia: la corrida repetida no vuelve a cargar un día que ya tiene lecturas."""
        self.con_el_sistema_registrado()
        lecturas = Telemetria.objects.count()
        resumen = cargador.cargar(CLAVE)
        self.assertEqual((Telemetria.objects.count(), resumen.creado), (lecturas, ()))

    def test_d_verificacion_con_el_paso_real_la_revision_calcula_el_fotoperiodo_de_ayer_en_10_horas(self):
        """Con una lectura cada 5 minutos (el paso real), el día de ayer queda completo: la primera revisión calcula su fotoperíodo, 10,00 h de luz (8 a 18 h con 15.000 lux), sin marcarlo incompleto y dentro
        del rango del umbral (8 a 14 h): el panel dice «Fotoperíodo de ayer: 10 h» y «En rango». La hora de la revisión es el mediodía de hoy (no depende de la hora del día)."""
        from iot.servicios import revision

        cargador.cargar(CLAVE)
        fabricas.sistema(Invernadero.objects.get(nombre_invernadero="Norte"))
        with mock.patch.object(cargador, "PASO_EN_MINUTOS", 5), mock.patch.object(cargador, "DIAS_DE_TEMPERATURA", 1):
            cargador.cargar(CLAVE)
        hoy_al_mediodia = datetime.combine(timezone.localdate(), time(12), tzinfo=timezone.get_current_timezone())
        revision.revisar(hoy_al_mediodia)
        luz = Sensor.objects.get(identificador_equipo="norte/sectorA/luz")
        fotoperiodo = FotoperiodoDiario.objects.get(sensor=luz, fecha=timezone.localdate() - timedelta(days=1))
        self.assertEqual((fotoperiodo.horas, fotoperiodo.incompleto), (Decimal("10.00"), False))
