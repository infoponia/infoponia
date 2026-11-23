# Pruebas de concurrencia de la API del nodo (IOT-03, paso 7; docs/casos_de_uso/iot/entregar_informacion.md, «Bloqueos y concurrencia»; D-74, punto 6; D-82).
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py; docs/patrones/bloqueos.md). Cada operación llama al servicio que usa la
# vista (la vista solo traduce). ``TransactionTestCase``: su ``flush`` vacía todas las tablas, así que cada prueba vuelve a asegurar los datos en ``setUp``.
#
# Lo que garantiza cada protección: el bloqueo del invernadero (una alerta activa por tipo y clave, una sola «no registrado» por identificador) y el índice único
# `(sensor, medida_en)` (una lectura por instante, aunque la verificación previa no la vea).

import importlib
from datetime import datetime, timezone
from decimal import Decimal

from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.api.traduccion import LecturaRecibida
from iot.models import Sensor, Telemetria
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero_con_geografia_propia

lecturas = perezoso("iot.servicios.lecturas")
modulo_lecturas = importlib.import_module("iot.servicios.lecturas")  # el real: un parche sobre el proxy no llega al módulo
hardware = perezoso("iot.servicios.hardware")

AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)
MEDIDA = "2026-11-21T17:04:30+00:00"


@tag("concurrencia")
class ApiConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Mensajes simultáneos del nodo: ni lecturas ni alertas duplicadas, y sin deadlock ni 500 contra una modificación del sensor."""

    def setUp(self):
        fabricas.asegurar_datos_de_iot()
        from maestros.tests.fabricas import asegurar_datos_de_maestros

        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.temp = fabricas.sensor(self.sistema, "norte/temp")
        self.nivel = fabricas.sensor(self.sistema, "norte/nivel", "nivel_solucion")
        self.contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
        self.n = 0

    def registrar(self, identificador, valor, medida_en=MEDIDA):
        """Una operación para ``correr_a_la_vez``: UNA lectura con su propia transacción, como en un pedido."""
        lectura = LecturaRecibida(self.n, identificador, identificador, valor, medida_en)
        self.n += 1
        return lambda: lecturas.registrar_lectura(self.contexto, lectura, AHORA)

    def alertas(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta="activa")

    def test_d74_6_dos_pedidos_con_la_misma_lectura_una_aceptada_y_la_otra_duplicada(self):
        """D-74, punto 6: la primera queda detenida antes de buscar la repetida (con el invernadero y el sistema bloqueados); la otra espera, la ve ya guardada y es
        `duplicada`: una sola telemetría."""
        resultados = correr_a_la_vez(
            self.registrar("norte/temp", Decimal("24")),
            self.registrar("norte/temp", Decimal("24")),
            primera="a",
            detener_antes_de=(modulo_lecturas, "_ya_existe_la_lectura"),
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []))
        self.assertEqual(sorted(r.resultado for r in exitos), ["aceptada", "duplicada"])
        self.assertEqual(Telemetria.objects.filter(sensor=self.temp).count(), 1)

    def test_regla_alertas_dos_lecturas_a_la_vez_que_generan_la_misma_alerta_crean_una_sola(self):
        """Garantía: nunca dos alertas activas del mismo tipo para el mismo sensor, con mensajes simultáneos: una lectura del nivel «bajo» y otra a la vez (otro
        instante) generan una sola «nivel de solución bajo»."""
        resultados = correr_a_la_vez(
            self.registrar("norte/nivel", "bajo", "2026-11-21T17:04:30+00:00"),
            self.registrar("norte/nivel", "bajo", "2026-11-21T17:04:40+00:00"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual({r.resultado for r in exitos}, {"aceptada"})
        self.assertEqual(self.alertas("iot_nivel_solucion_bajo").count(), 1)
        self.assertEqual(Telemetria.objects.filter(sensor=self.nivel).count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="entrega_informacion_iot").count(), 1)

    def test_regla_alertas_dos_rechazos_a_la_vez_del_mismo_identificador_desconocido_crean_una_sola_alerta(self):
        """Garantía: una sola alerta «dispositivo no registrado» por identificador y sistema, aun con mensajes simultáneos (también con otras mayúsculas)."""
        resultados = correr_a_la_vez(
            self.registrar("norte/co2", Decimal("450")), self.registrar("NORTE/CO2", Decimal("460"), "2026-11-21T17:04:40+00:00"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual({r.motivo for r in exitos}, {"equipo_no_registrado"})
        self.assertEqual(self.alertas("iot_dispositivo_no_registrado").count(), 1)

    def test_regla_hardware_una_lectura_mientras_se_modifica_el_sensor_no_da_deadlock_ni_500(self):
        """IOT-MOD-HDW y la API toman invernadero → sistema → equipo en el mismo orden: la modificación (detenida con sus bloqueos tomados) y una lectura a la vez
        terminan las dos, sin deadlock ni error."""
        datos = fabricas.datos_de_equipo_guardado(Sensor.objects.get(pk=self.temp.pk), modelo="DHT22 nuevo")
        resultados = correr_a_la_vez(
            lambda: hardware.modificar_hardware(self.laura, self.temp.pk, datos), self.registrar("norte/temp", Decimal("24")), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(Telemetria.objects.filter(sensor=self.temp).count(), 1)
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.modelo_hardware, "DHT22 nuevo")

    def test_regla_hardware_una_lectura_que_audita_mientras_se_modifica_el_sensor_tampoco_se_traba(self):
        """El otro orden: la lectura (inválida, genera su alerta y la audita) queda detenida con sus bloqueos y la modificación espera; no hay deadlock."""
        datos = fabricas.datos_de_equipo_guardado(Sensor.objects.get(pk=self.temp.pk), modelo="DHT22 nuevo")
        resultados = correr_a_la_vez(
            self.registrar("norte/temp", Decimal("999")), lambda: hardware.modificar_hardware(self.laura, self.temp.pk, datos), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(self.alertas("iot_lectura_invalida").count(), 1)
