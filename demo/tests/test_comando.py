# Pruebas del comando ``cargar_demo`` completo (DAT-01, paso 3): con el candado sustituido, la salida trae una línea por sección y la lista de
# cuentas (rol y correo), nunca la contraseña; y una segunda corrida se niega porque la base ya no está recién migrada.
# Los secretos de las pruebas se inventan en cada corrida.

import os
import secrets
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.models import Usuario
from demo import candado
from inventario.tests.fabricas import ConDatosDeInventario


class ComandoCargarDemoTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-01 pasos 1 y 3: el comando entero, con el candado abierto solo para la prueba."""

    def setUp(self):
        self.contrasena = secrets.token_urlsafe(12)
        entorno = patch.dict(
            os.environ,
            {
                candado.VARIABLE_DEL_CANDADO: "1",
                candado.VARIABLE_DE_LA_CONTRASENA: self.contrasena,
                candado.VARIABLE_DEL_CORREO: "ejemplo",
            },
        )
        base = patch.object(candado, "nombre_de_la_base", return_value=candado.BASE_DE_LA_DEMO)
        for parche in (entorno, base):
            parche.start()
            self.addCleanup(parche.stop)

    def _correr(self):
        salida = StringIO()
        call_command("cargar_demo", stdout=salida)
        return salida.getvalue()

    def test_dat_01_la_salida_tiene_una_linea_por_seccion_y_las_cuentas_sin_la_contrasena(self):
        """Paso 3: «Cargado: …» por sección, la lista de cuentas con rol y correo, y el aviso final; nunca la contraseña."""
        salida = self._correr()
        self.assertEqual(salida.count("Cargado: "), 14)
        self.assertNotIn("Salteado", salida)
        self.assertIn("Gerente: ejemplo+gerente1@gmail.com", salida)
        self.assertIn("Contador: ejemplo+contador1@gmail.com", salida)
        self.assertIn("Ahora corré estado_demo para ver si las escenas del guion están listas", salida)
        self.assertNotIn(self.contrasena, salida)

    def test_dat_01_una_segunda_corrida_se_niega_y_no_agrega_nada(self):
        """Decisión de la demo, punto 4: con cuentas con rol, la carga no mezcla datos."""
        self._correr()
        cuentas = Usuario.objects.exclude(rol="").count()
        with self.assertRaises(CommandError):
            self._correr()
        self.assertEqual(Usuario.objects.exclude(rol="").count(), cuentas)
