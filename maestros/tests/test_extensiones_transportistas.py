# Pruebas de los puntos de extensión de transportistas de `maestros` (MAE-05, paso 2; D-55 y
# docs/api/extensiones_de_maestros.md, «Transportistas»). Sin registrantes dan su resultado neutro; con registrantes falsos
# se juntan todos, y la logística admite uno solo.

from unittest import mock

from django.test import SimpleTestCase

from maestros import extensiones
from maestros.extensiones import Impedimento, Logistica


class ImpedimentosDeTransportistaTests(SimpleTestCase):
    """``registrar_impedimento_de_transportista`` e ``impedimentos_de_transportista``."""

    def test_ext_transportistas_sin_registrantes_no_hay_impedimentos(self):
        """API «Transportistas»: sin registrantes, lista vacía (no se bloquea nada)."""
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_TRANSPORTISTA", []):
            self.assertEqual(extensiones.impedimentos_de_transportista(object()), [])

    def test_ext_transportistas_junta_los_impedimentos_de_todos_los_registrantes(self):
        """API «Transportistas»: se juntan todos, sin quedarse con el primero (reglas 9 y 10 de PROD-MOD-INV)."""
        en_ruta = Impedimento("transportista_en_ruta", "Está en ruta.", "Esperá a que finalice.")
        con_entregas = Impedimento("transportista_con_entregas", "Tiene 2 entregas.", "Reasignalas.")
        recibido = []

        def uno(transportista):
            recibido.append(transportista)
            return [en_ruta]

        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_TRANSPORTISTA", []):
            extensiones.registrar_impedimento_de_transportista(uno)
            extensiones.registrar_impedimento_de_transportista(lambda t: [con_entregas])
            marca = object()
            self.assertEqual(extensiones.impedimentos_de_transportista(marca), [en_ruta, con_entregas])
        self.assertEqual(recibido, [marca])


class LogisticaDeTransportistaTests(SimpleTestCase):
    """``registrar_logistica_de_transportista`` y ``logistica_de``."""

    def test_ext_transportistas_sin_registrante_la_logistica_es_none(self):
        """API «Transportistas»: sin registrante, ``None``: «Logística» no muestra las columnas de `comercial`."""
        with mock.patch.object(extensiones, "_LOGISTICA", []):
            self.assertIsNone(extensiones.logistica_de([object()]))

    def test_ext_transportistas_con_registrante_devuelve_su_diccionario_en_una_sola_llamada(self):
        """API «Transportistas»: una sola llamada para toda la lista (sin consultas por fila)."""
        llamadas = []
        esperado = {1: Logistica("Camioneta AE123CD · 800 kg", False, 0, "/entregas/1/"), 2: Logistica(None, True, 3, None)}

        def registrante(transportistas):
            llamadas.append(list(transportistas))
            return esperado

        with mock.patch.object(extensiones, "_LOGISTICA", []):
            extensiones.registrar_logistica_de_transportista(registrante)
            self.assertEqual(extensiones.logistica_de(["a", "b"]), esperado)
        self.assertEqual(llamadas, [["a", "b"]])

    def test_ext_transportistas_un_segundo_registrante_de_logistica_lanza_runtime_error(self):
        """API «Transportistas»: admite un solo registrante; una segunda llamada lanza ``RuntimeError``."""
        with mock.patch.object(extensiones, "_LOGISTICA", []):
            extensiones.registrar_logistica_de_transportista(lambda ts: {})
            with self.assertRaises(RuntimeError):
                extensiones.registrar_logistica_de_transportista(lambda ts: {})
