# Pruebas de las reglas de seguridad del despliegue (USR-09a): ``config/seguridad.py``. SEG-16 (transporte seguro:
# HTTPS, cookies seguras y HSTS) y el ``DEBUG`` apagado por defecto (decisión de USR-09a). Son funciones puras que reciben
# el entorno o DEBUG, sin importar Django, para probarlas sin recargar los settings (como ``config/correo.py``). La última
# prueba carga ``config/settings.py`` en un módulo aparte para ver que los aplica. Cada prueba arma sus propios datos.

import importlib
import importlib.util
import os
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

# Valores de producción fijados en USR-09a: HSTS de un día (86400 s), sin subdominios ni preload.
PRODUCCION = {
    "SECURE_SSL_REDIRECT": True,
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "SECURE_HSTS_SECONDS": 86400,
}
# Valores de desarrollo: los de Django por defecto (el desarrollo corre por http).
DESARROLLO = {
    "SECURE_SSL_REDIRECT": False,
    "SESSION_COOKIE_SECURE": False,
    "CSRF_COOKIE_SECURE": False,
    "SECURE_HSTS_SECONDS": 0,
}


def seguridad():
    """El módulo ``config.seguridad``."""
    return importlib.import_module("config.seguridad")


def cargar_settings_con_debug(valor):
    """Carga ``config/settings.py`` en un módulo aparte, con ``DJANGO_DEBUG`` en ``valor``, y lo devuelve.

    No toca la configuración en uso: es un módulo nuevo, solo para leer lo que calcula. Es la misma forma que usa
    ``core/tests/test_admin_django.py``.
    """
    especificacion = importlib.util.spec_from_file_location(
        "config_settings_de_prueba_seguridad", settings.BASE_DIR / "config" / "settings.py"
    )
    modulo = importlib.util.module_from_spec(especificacion)
    with mock.patch.dict(os.environ, {"DJANGO_DEBUG": valor}):
        especificacion.loader.exec_module(modulo)
    return modulo


class UsrDebugPorDefectoTests(SimpleTestCase):
    """Decisión de USR-09a (punto 2 de USR-09): ``DEBUG`` queda apagado si falta ``DJANGO_DEBUG``."""

    def test_usr09a_debug_apagado_sin_variable(self):
        """USR-09a: sin ``DJANGO_DEBUG``, vacía o en «0», ``DEBUG`` queda apagado. Un descuido en el servidor no
        enciende el modo de desarrollo (ni el admin de Django, D-30)."""
        for nombre, entorno in {"sin variable": {}, "vacía": {"DJANGO_DEBUG": ""}, "cero": {"DJANGO_DEBUG": "0"}}.items():
            with self.subTest(nombre):
                self.assertIs(seguridad().debug_encendido(entorno), False)

    def test_usr09a_debug_encendido_solo_con_uno(self):
        """USR-09a: solo ``DJANGO_DEBUG=1`` enciende ``DEBUG``; cualquier otro valor lo deja apagado."""
        self.assertIs(seguridad().debug_encendido({"DJANGO_DEBUG": "1"}), True)
        for valor in ("true", "si", "2", " 1"):
            with self.subTest(valor=valor):
                self.assertIs(seguridad().debug_encendido({"DJANGO_DEBUG": valor}), False)


class Seg16AjustesHttpsTests(SimpleTestCase):
    """SEG-16 y decisión de USR-09a: ``ajustes_https(debug, corriendo_pruebas) -> dict``."""

    def test_seg16_con_debug_apagado_https_cookies_seguras_y_hsts_de_un_dia(self):
        """SEG-16: en producción (DEBUG apagado) se redirige a https, las cookies de sesión y de CSRF son seguras y
        el navegador recibe HSTS de un día (86400 s, USR-09a)."""
        self.assertEqual(seguridad().ajustes_https(False, False), PRODUCCION)

    def test_seg16_con_debug_encendido_nada_de_https(self):
        """USR-09a: con DEBUG encendido (desarrollo, por http) no se redirige, las cookies no son seguras y no hay
        HSTS: son los valores de Django por defecto."""
        self.assertEqual(seguridad().ajustes_https(True, False), DESARROLLO)
        self.assertEqual(seguridad().ajustes_https(True, True), DESARROLLO)

    def test_seg16_en_las_pruebas_no_redirige_pero_si_cookies_y_hsts(self):
        """USR-09a: con ``manage.py test`` y DEBUG apagado (el CI) no se redirige, para que las pruebas con el
        cliente de Django por http no reciban un 301; las cookies seguras y el HSTS se aplican igual."""
        self.assertEqual(seguridad().ajustes_https(False, True), {**PRODUCCION, "SECURE_SSL_REDIRECT": False})

    def test_seg16_hsts_sin_subdominios_ni_preload(self):
        """USR-09a: el HSTS no incluye subdominios ni se ofrece para la lista de precarga, y la función no toca la
        política de Referer (D-88) ni el HttpOnly de las cookies."""
        for debug in (True, False):
            for pruebas in (True, False):
                with self.subTest(debug=debug, pruebas=pruebas):
                    ajustes = seguridad().ajustes_https(debug, pruebas)
                    self.assertEqual(set(ajustes), set(PRODUCCION))

    def test_seg16_settings_aplica_los_ajustes(self):
        """SEG-16 y USR-09a: ``config/settings.py`` aplica lo que calcula ``ajustes_https`` (con ``manage.py test``,
        sin la redirección) y la cookie de sesión sigue sin ser accesible desde scripts (HttpOnly, el valor de
        Django, que no se define)."""
        produccion = cargar_settings_con_debug("0")
        desarrollo = cargar_settings_con_debug("1")

        self.assertIs(produccion.DEBUG, False)
        for nombre, valor in {**PRODUCCION, "SECURE_SSL_REDIRECT": False}.items():
            with self.subTest("producción", ajuste=nombre):
                self.assertEqual(getattr(produccion, nombre), valor)
        self.assertIs(desarrollo.DEBUG, True)
        for nombre, valor in DESARROLLO.items():
            with self.subTest("desarrollo", ajuste=nombre):
                self.assertEqual(getattr(desarrollo, nombre), valor)
        for modulo in (produccion, desarrollo):
            self.assertFalse(hasattr(modulo, "SESSION_COOKIE_HTTPONLY"))
            self.assertFalse(hasattr(modulo, "SECURE_HSTS_INCLUDE_SUBDOMAINS"))
            self.assertFalse(hasattr(modulo, "SECURE_HSTS_PRELOAD"))
        self.assertIs(settings.SESSION_COOKIE_HTTPONLY, True)
