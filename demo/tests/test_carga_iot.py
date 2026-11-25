# Pruebas de la sección 14 de ``docs/demo/datos_de_la_demo.md`` (DAT-02, paso 3): el sistema IoT de Norte con su nodo, 5 sensores, 2
# actuadores y 2 reglas. La prueba clave es la última: dos lecturas de 35 °C encienden el ventilador, que es lo que la defensa muestra en vivo.
# Los secretos de las pruebas se inventan en cada corrida; el token del sistema no se muestra ni se guarda en ninguna parte.

import secrets
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from demo import carga
from inventario.servicios.variedades import umbral_efectivo
from inventario.tests.fabricas import ConDatosDeInventario
from iot.api.traduccion import LecturaRecibida
from iot.models import Actuador, Comando, NodoCentral, ReglaActuacion, Sensor, SistemaIoT
from iot.servicios import lecturas
from maestros.models import Invernadero

BASE = "ejemplo"


class CargaDelIotTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-02 paso 3: el IoT de Norte queda listo para que Node-RED mande lecturas y el ventilador se encienda."""

    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.contexto = carga.Contexto(hoy=cls.hoy, base=BASE, contrasena=secrets.token_urlsafe(12))
        cls.lineas = carga.cargar(cls.contexto)

    def _norte(self):
        return Invernadero.objects.get(nombre_invernadero="Norte")

    def _sistema(self):
        return SistemaIoT.objects.get(invernadero=self._norte())

    def test_dat_02_la_seccion_14_se_carga_sin_saltearse_y_sin_el_token_en_la_salida(self):
        """La línea de la sección 14 dice qué se cargó y no trae ningún token."""
        linea = next(l for l in self.lineas if l.startswith("Cargado: 14."))
        self.assertIn("sin token a la vista", linea)

    def test_dat_02_los_siete_identificadores_exactos(self):
        """Sección 14: los 5 sensores y los 2 actuadores, con los identificadores del flujo de Node-RED."""
        sistema = self._sistema()
        sensores = set(Sensor.objects.filter(sistema=sistema).values_list("identificador_equipo", flat=True))
        actuadores = set(Actuador.objects.filter(sistema=sistema).values_list("identificador_equipo", flat=True))
        self.assertEqual(
            sensores,
            {
                "norte/sectorA/temperatura",
                "norte/sectorA/humedad",
                "norte/sectorA/luz",
                "norte/tanque1/temp-solucion",
                "norte/tanque1/nivel",
            },
        )
        self.assertEqual(actuadores, {"norte/sectorA/ventilador", "norte/sectorA/ventana"})

    def test_dat_02_un_nodo_sin_identificador_y_el_rango_de_la_solucion(self):
        """Sección 14: el nodo lo crea el registro del sistema (una sola vez, sin identificador); la solución va de 18,0 a 24,0 °C."""
        sistema = self._sistema()
        self.assertEqual(NodoCentral.objects.filter(sistema=sistema).count(), 1)
        self.assertEqual(sistema.estado_sistema, SistemaIoT.Estado.ACTIVO)
        self.assertEqual((sistema.temp_solucion_min, sistema.temp_solucion_max), (Decimal("18.0"), Decimal("24.0")))

    def test_dat_02_el_token_queda_generado_pero_nunca_en_claro(self):
        """El servicio genera el token siempre; la carga solo guarda su resumen (hash) y la fecha, nunca el token."""
        sistema = self._sistema()
        self.assertIsNotNone(sistema.token_resumen)
        self.assertIsNotNone(sistema.token_generado_en)
        self.assertFalse(any("token" in l.lower() and sistema.token_resumen in l for l in self.lineas))

    def test_dat_02_los_equipos_estan_en_su_sector_y_el_actuador_lleva_su_nombre_en_la_descripcion(self):
        """Sección 14: los de sectorA en Maduración N1; los del tanque sin sector; «Ventilador sector A» en la descripción."""
        sistema = self._sistema()
        for sensor in Sensor.objects.filter(sistema=sistema):
            esperado = None if "tanque" in sensor.identificador_equipo else "Maduración N1"
            self.assertEqual(sensor.sector.nombre_sector if sensor.sector else None, esperado, sensor.identificador_equipo)
        ventilador = Actuador.objects.get(sistema=sistema, identificador_equipo="norte/sectorA/ventilador")
        self.assertEqual(ventilador.descripcion_actuador, "Ventilador sector A")
        self.assertEqual(ventilador.tipo_actuador.nombre_actuador, "Ventilador")

    def test_dat_02_el_umbral_efectivo_de_norte_es_16_a_27_grados_y_60_a_85_por_ciento(self):
        """Sección 6 y 14: con Criolla (LN-1) y Morada (LN-2) presentes, la intersección da 16–27 °C y 60–85 %."""
        umbral = umbral_efectivo([self._norte().pk])[self._norte().pk]
        self.assertEqual((umbral.temp_ambiente.minimo, umbral.temp_ambiente.maximo), (Decimal("16"), Decimal("27")))
        self.assertEqual((umbral.humedad.minimo, umbral.humedad.maximo), (Decimal("60"), Decimal("85")))

    def test_dat_02_dos_reglas_sobre_la_temperatura_del_sector_a(self):
        """Sección 14: supera_maximo → Encender y vuelve_al_rango → Apagar, las dos sobre el ventilador."""
        reglas = {(r.condicion, r.accion.nombre_accion) for r in ReglaActuacion.objects.filter(sensor__sistema=self._sistema())}
        self.assertEqual(reglas, {("supera_maximo", "Encender"), ("vuelve_al_rango", "Apagar")})

    def test_dat_02_dos_lecturas_de_35_grados_encienden_el_ventilador(self):
        """PRUEBA CLAVE de la escena en vivo: con cant_lecturas_confirmacion = 2, la segunda lectura de 35 °C (por encima del máximo 27)
        emite el comando «Encender» del ventilador; con la primera todavía no."""
        sistema = self._sistema()
        sensor = Sensor.objects.get(sistema=sistema, identificador_equipo="norte/sectorA/temperatura")
        ventilador = Actuador.objects.get(sistema=sistema, identificador_equipo="norte/sectorA/ventilador")
        base = timezone.now()
        self.assertFalse(Comando.objects.filter(actuador=ventilador).exists())
        for n in (1, 2):
            ahora = base + timedelta(seconds=10 * n)
            contexto = lecturas.contexto_del_mensaje(sistema, ahora)
            recibida = LecturaRecibida(
                n, sensor.identificador_equipo, sensor.identificador_equipo, Decimal("35"), (ahora - timedelta(seconds=5)).isoformat()
            )
            resultado = lecturas.registrar_lectura(contexto, recibida, ahora)
            self.assertEqual(resultado.resultado, "aceptada", resultado)
            esperados = 0 if n == 1 else 1
            self.assertEqual(Comando.objects.filter(actuador=ventilador).count(), esperados, f"después de la lectura {n}")
        comando = Comando.objects.get(actuador=ventilador)
        self.assertEqual(comando.accion.nombre_accion, "Encender")
        self.assertEqual(comando.estado_comando, "pendiente")

    def test_dat_02_una_lectura_normal_de_24_grados_no_emite_nada(self):
        """Lo que manda el simulador (24 ± 1,5 °C) está adentro del umbral: no dispara ni el ventilador ni una alerta de temperatura."""
        sistema = self._sistema()
        sensor = Sensor.objects.get(sistema=sistema, identificador_equipo="norte/sectorA/temperatura")
        ahora = timezone.now() + timedelta(seconds=10)
        recibida = LecturaRecibida(
            1, sensor.identificador_equipo, sensor.identificador_equipo, Decimal("24"), (ahora - timedelta(seconds=5)).isoformat()
        )
        lecturas.registrar_lectura(lecturas.contexto_del_mensaje(sistema, ahora), recibida, ahora)
        self.assertFalse(Comando.objects.exists())
