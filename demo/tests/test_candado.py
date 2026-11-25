# Pruebas del doble candado de ``cargar_demo`` (DAT-01, paso 1; punto 4 de la decisión de la demo). Un caso por condición, y cada uno
# verifica que NO se escribió nada. Los secretos de las pruebas se generan al vuelo: ninguna contraseña queda escrita en el archivo.

import os
import secrets
import subprocess
import sys
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from core.models import Capataz, RegistroAuditoria, Usuario
from demo import candado
from maestros.models import Invernadero


def _entorno_valido():
    """Las tres variables en orden; la contraseña se inventa en cada corrida."""
    return {
        candado.VARIABLE_DEL_CANDADO: "1",
        candado.VARIABLE_DE_LA_CONTRASENA: secrets.token_urlsafe(12),
        candado.VARIABLE_DEL_CORREO: "ejemplo",
    }


class CandadoDeCargarDemoTests(TestCase):
    """Decisión de la demo, punto 4: el comando se niega a correr, sin escribir nada, si falla cualquier condición."""

    def _entorno(self, **cambios):
        """Pone las variables válidas con ``cambios`` encima; un valor ``None`` quita la variable. Se restauran solas al terminar."""
        parche = patch.dict(os.environ, {k: v for k, v in {**_entorno_valido(), **cambios}.items() if v is not None})
        parche.start()
        self.addCleanup(parche.stop)
        for variable, valor in cambios.items():
            if valor is None:
                os.environ.pop(variable, None)

    def _base(self, nombre):
        """Sustituye ``nombre_de_la_base`` (para eso es una función propia)."""
        parche = patch.object(candado, "nombre_de_la_base", return_value=nombre)
        parche.start()
        self.addCleanup(parche.stop)

    def _nada_escrito(self):
        self.assertFalse(Usuario.objects.exclude(rol="").exists())
        self.assertFalse(Invernadero.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def _cargar_y_fallar(self, fragmento):
        with self.assertRaises(CommandError) as capturado:
            call_command("cargar_demo", stdout=StringIO())
        self.assertIn(fragmento, str(capturado.exception))
        self._nada_escrito()

    def test_dat_01_sin_infoponia_demo_no_escribe_nada(self):
        """Decisión de la demo, punto 4: sin ``INFOPONIA_DEMO=1`` el comando se niega."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno(INFOPONIA_DEMO=None)
        self._cargar_y_fallar("INFOPONIA_DEMO")

    def test_dat_01_infoponia_demo_distinto_de_uno_no_escribe_nada(self):
        """Decisión de la demo, punto 4: solo el valor exacto ``1`` abre el candado."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno(INFOPONIA_DEMO="true")
        self._cargar_y_fallar("INFOPONIA_DEMO")

    def test_dat_01_con_otra_base_no_escribe_nada(self):
        """Decisión de la demo, punto 4: la base conectada tiene que llamarse exactamente ``infoponia_demo``."""
        self._base("infoponia")
        self._entorno()
        self._cargar_y_fallar("infoponia_demo")

    def test_dat_01_el_nombre_de_la_base_es_exacto(self):
        """Decisión de la demo, punto 4: «exactamente»: ni un prefijo ni un sufijo."""
        self._base("test_infoponia_demo")
        self._entorno()
        self._cargar_y_fallar("infoponia_demo")

    def test_dat_01_con_cuentas_con_rol_no_escribe_nada(self):
        """Decisión de la demo, punto 4: la carga es para una base recién migrada; con una cuenta con rol no mezcla datos."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno()
        Capataz.objects.create_user(
            email="existente@example.com", password=secrets.token_urlsafe(12), first_name="Ex", last_name="Istente"
        )
        with self.assertRaises(CommandError) as capturado:
            call_command("cargar_demo", stdout=StringIO())
        self.assertIn("cuentas con rol", str(capturado.exception))
        self.assertEqual(Usuario.objects.exclude(rol="").count(), 1)  # solo la que ya estaba
        self.assertFalse(Invernadero.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_dat_01_un_administrador_no_cuenta_como_cuenta_con_rol(self):
        """Decisión de la demo, punto 4: el Administrador (superusuario, sin rol) no impide la carga: el candado pasa."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno()
        Usuario.objects.create_superuser(email="admin@example.com", password=secrets.token_urlsafe(12))
        candado.verificar_que_se_puede_cargar()  # no lanza

    def test_dat_01_sin_contrasena_no_escribe_nada(self):
        """Decisión de la demo, punto 6: sin ``INFOPONIA_DEMO_CONTRASENA`` no se carga."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno(INFOPONIA_DEMO_CONTRASENA=None)
        self._cargar_y_fallar("INFOPONIA_DEMO_CONTRASENA")

    def test_dat_01_sin_correo_no_escribe_nada(self):
        """Decisión de la demo, punto 6: sin ``INFOPONIA_DEMO_CORREO`` no se carga."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno(INFOPONIA_DEMO_CORREO=None)
        self._cargar_y_fallar("INFOPONIA_DEMO_CORREO")

    def test_dat_01_con_todo_en_orden_el_candado_pasa(self):
        """Decisión de la demo, punto 4: con la variable, la base correcta, sin cuentas y con los secretos, no lanza."""
        self._base(candado.BASE_DE_LA_DEMO)
        self._entorno()
        candado.verificar_que_se_puede_cargar()

    def test_dat_01_el_mensaje_de_error_no_incluye_los_secretos(self):
        """Decisión de la demo, punto 6: ni la contraseña ni la base de los correos aparecen en un mensaje de error."""
        self._base("infoponia")
        self._entorno()
        contrasena = os.environ[candado.VARIABLE_DE_LA_CONTRASENA]
        with self.assertRaises(CommandError) as capturado:
            call_command("cargar_demo", stdout=StringIO())
        self.assertNotIn(contrasena, str(capturado.exception))
        self.assertNotIn(os.environ[candado.VARIABLE_DEL_CORREO], str(capturado.exception))


class AppDemoCondicionadaTests(SimpleTestCase):
    """Decisión de la demo, punto 5: la app ``demo`` solo se instala con ``INFOPONIA_DEMO=1`` o durante las pruebas."""

    def _demo_esta_instalada(self, infoponia_demo):
        """Importa ``config.settings`` en un proceso aparte (``sys.argv`` sin «test») y dice si ``demo`` quedó en ``INSTALLED_APPS``."""
        entorno = {**os.environ, "DJANGO_DEBUG": "1"}
        if infoponia_demo is None:
            entorno.pop("INFOPONIA_DEMO", None)
        else:
            entorno["INFOPONIA_DEMO"] = infoponia_demo
        resultado = subprocess.run(
            [sys.executable, "-c", "import config.settings as s; print('demo' in s.INSTALLED_APPS)"],
            cwd=settings.BASE_DIR,
            env=entorno,
            capture_output=True,
            text=True,
            check=True,
        )
        return resultado.stdout.strip() == "True"

    def test_dat_01_sin_la_variable_la_app_no_se_instala_fuera_de_las_pruebas(self):
        self.assertFalse(self._demo_esta_instalada(None))

    def test_dat_01_con_la_variable_en_cero_la_app_no_se_instala(self):
        self.assertFalse(self._demo_esta_instalada("0"))

    def test_dat_01_con_la_variable_en_uno_la_app_se_instala(self):
        self.assertTrue(self._demo_esta_instalada("1"))

    def test_dat_01_durante_las_pruebas_la_app_esta_instalada(self):
        self.assertIn("demo", settings.INSTALLED_APPS)
