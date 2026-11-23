# Pruebas del cargador de datos de verificación del IoT (`iot/verificacion.py`; CLAUDE.md, «Datos para la verificación a mano»):
# la primera corrida deja «Norte» con umbral efectivo, la segunda carga los equipos del flujo de Node-RED cuando el sistema IoT ya se
# registró por la pantalla, nunca duplica y no pasa la contraseña ni un token por la salida ni por la auditoría.

from django.test import TestCase

from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_administrador, crear_gerente
from inventario.servicios.variedades import umbral_efectivo
from core.verificacion import ErrorDeCarga
from iot import verificacion as cargador
from iot.models import Actuador, Hardware, Sensor, SistemaIoT
from iot.tests import fabricas
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero

CLAVE = "Prueba-98765x"


class IotVerificacionTests(fabricas.ConCatalogoIot, TestCase):
    """`iot.verificacion.cargar`: usa los servicios de las apps y es idempotente."""

    def setUp(self):
        self.gerente = crear_gerente()

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
