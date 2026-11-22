# Pruebas de los puntos de extensión de la cuenta de `core` (MAE-05, paso 2; D-55 y docs/api/extensiones_de_maestros.md,
# «Transportistas»): impedimentos de la baja de una cuenta y datos de solo lectura de la cuenta. Idempotentes como los demás
# de core/extensiones.py; sin registrantes dan lista vacía.

from unittest import mock

from django.test import SimpleTestCase

from core import extensiones
from core.extensiones import DatoDeCuenta, ImpedimentoDeCuenta


class ImpedimentosDeBajaDeCuentaTests(SimpleTestCase):
    """``registrar_impedimento_de_baja_de_cuenta`` e ``impedimentos_de_baja_de_cuenta``."""

    def test_ext_cuenta_sin_registrantes_no_hay_impedimentos(self):
        """API «Transportistas»: sin registrantes, ninguno."""
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_BAJA_DE_CUENTA", []):
            self.assertEqual(extensiones.impedimentos_de_baja_de_cuenta(object()), [])

    def test_ext_cuenta_junta_los_impedimentos_de_todos_en_orden_de_registro(self):
        """API «Transportistas»: se juntan todos."""
        a = ImpedimentoDeCuenta("transportista_en_ruta", "Está en ruta.", "Esperá a que finalice la ruta.")
        b = ImpedimentoDeCuenta("otro", "Otro.", "Resolvelo.")
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_BAJA_DE_CUENTA", []):
            extensiones.registrar_impedimento_de_baja_de_cuenta(lambda cuenta: [a])
            extensiones.registrar_impedimento_de_baja_de_cuenta(lambda cuenta: [b])
            self.assertEqual(extensiones.impedimentos_de_baja_de_cuenta(object()), [a, b])

    def test_ext_cuenta_registrar_el_mismo_impedimento_dos_veces_no_lo_duplica(self):
        """core/extensiones.py: ``ready()`` puede correr más de una vez, así que cada registro es idempotente."""
        funcion = lambda cuenta: [ImpedimentoDeCuenta("x", "x", "x")]  # noqa: E731
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_BAJA_DE_CUENTA", []):
            extensiones.registrar_impedimento_de_baja_de_cuenta(funcion)
            extensiones.registrar_impedimento_de_baja_de_cuenta(funcion)
            self.assertEqual(len(extensiones.impedimentos_de_baja_de_cuenta(object())), 1)


class DatosDeCuentaTests(SimpleTestCase):
    """``registrar_datos_de_cuenta`` y ``datos_de_cuenta``."""

    def test_ext_cuenta_sin_registrantes_no_hay_datos(self):
        """API «Transportistas»: sin registrantes, lista vacía."""
        with mock.patch.object(extensiones, "_DATOS_DE_CUENTA", []):
            self.assertEqual(extensiones.datos_de_cuenta(object()), [])

    def test_ext_cuenta_junta_los_datos_de_todos_en_orden_de_registro(self):
        """API «Transportistas»: se juntan los datos de todos los registrantes."""
        uno = DatoDeCuenta("Invernadero", "Norte", "")
        dos = DatoDeCuenta("Otro", "Valor", "Nota")
        with mock.patch.object(extensiones, "_DATOS_DE_CUENTA", []):
            extensiones.registrar_datos_de_cuenta(lambda cuenta: [uno])
            extensiones.registrar_datos_de_cuenta(lambda cuenta: [dos])
            self.assertEqual(extensiones.datos_de_cuenta(object()), [uno, dos])

    def test_ext_cuenta_registrar_los_mismos_datos_dos_veces_no_los_duplica(self):
        """core/extensiones.py: cada registro es idempotente."""
        funcion = lambda cuenta: [DatoDeCuenta("a", "b", "")]  # noqa: E731
        with mock.patch.object(extensiones, "_DATOS_DE_CUENTA", []):
            extensiones.registrar_datos_de_cuenta(funcion)
            extensiones.registrar_datos_de_cuenta(funcion)
            self.assertEqual(len(extensiones.datos_de_cuenta(object())), 1)
