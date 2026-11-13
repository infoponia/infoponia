# Pruebas de SEG-18 (el panel de administración de Django está deshabilitado en producción) y de D-16 y
# D-30 (queda encendido solo en desarrollo, atado a DEBUG). Cada prueba arma sus propios datos y fija el valor
# de ``ADMIN_DJANGO_HABILITADO`` con ``override_settings``: ese valor se calcula al arrancar y las rutas se
# arman al importar ``config.urls``, así que hay que volver a importarlo después de cambiarlo (y otra vez,
# con el valor real, al terminar la prueba, para no dejar rutas ajenas a las demás pruebas).

import importlib
import importlib.util
import os
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, clear_url_caches, reverse

import config.urls
from core.models import Usuario

CLAVE = "clave-segura-123"


def crear_administrador(email="admin@infoponia.com"):
    """Crea un Administrador técnico: superusuario sin rol (D-10)."""
    return Usuario.objects.create_superuser(
        email=email, password=CLAVE, first_name="Adrián", last_name="Mena"
    )


def recargar_urls():
    """Vuelve a armar las rutas del proyecto con el valor actual de ``ADMIN_DJANGO_HABILITADO``."""
    importlib.reload(config.urls)
    clear_url_caches()


def cargar_settings_con_debug(valor):
    """Carga ``config/settings.py`` en un módulo aparte, con ``DJANGO_DEBUG`` en ``valor``, y lo devuelve.

    No toca la configuración en uso: es un módulo nuevo, solo para leer lo que calcula.
    """
    especificacion = importlib.util.spec_from_file_location(
        "config_settings_de_prueba", settings.BASE_DIR / "config" / "settings.py"
    )
    modulo = importlib.util.module_from_spec(especificacion)
    with mock.patch.dict(os.environ, {"DJANGO_DEBUG": valor}):
        especificacion.loader.exec_module(modulo)
    return modulo


class Seg18AdminDjangoTests(TestCase):
    """SEG-18 y D-30: el admin de Django responde solo en desarrollo; en producción no existe."""

    def fijar_admin(self, habilitado):
        """Fija ``ADMIN_DJANGO_HABILITADO`` y vuelve a armar las rutas; todo se deshace al terminar."""
        # Los cleanups corren al revés: primero se deshace el ajuste y recién después se recargan las rutas.
        self.addCleanup(recargar_urls)
        ajuste = override_settings(ADMIN_DJANGO_HABILITADO=habilitado)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        recargar_urls()

    def test_seg18_admin_deshabilitado_responde_404(self):
        """SEG-18 y D-16: con el admin apagado (producción), /admin/ no existe: 404 sin sesión y también
        para un Administrador con la sesión abierta; no hay ruta que resolver, y las pantallas propias
        siguen funcionando."""
        self.fijar_admin(False)

        sin_sesion = self.client.get("/admin/")
        sin_sesion_login = self.client.get("/admin/login/")
        self.client.force_login(crear_administrador())
        con_sesion = self.client.get("/admin/")
        con_sesion_usuarios = self.client.get("/admin/core/usuario/")

        for respuesta in (sin_sesion, sin_sesion_login, con_sesion, con_sesion_usuarios):
            self.assertEqual(respuesta.status_code, 404)
        with self.assertRaises(NoReverseMatch):
            reverse("admin:index")
        self.assertEqual(self.client.get(reverse("core:usuarios")).status_code, 200)

    def test_seg18_admin_habilitado_responde_en_desarrollo(self):
        """D-16 y D-30: con el admin encendido (desarrollo), /admin/ existe: sin sesión lleva al ingreso del
        admin y un Administrador entra al panel."""
        self.fijar_admin(True)

        sin_sesion = self.client.get("/admin/")
        self.client.force_login(crear_administrador())
        con_sesion = self.client.get("/admin/")

        self.assertEqual(sin_sesion.status_code, 302)
        self.assertTrue(sin_sesion["Location"].startswith("/admin/login/"))
        self.assertEqual(con_sesion.status_code, 200)
        self.assertEqual(reverse("admin:index"), "/admin/")

    def test_seg18_el_admin_se_enciende_solo_con_debug(self):
        """SEG-18 y D-30: ``ADMIN_DJANGO_HABILITADO`` sale de ``DJANGO_DEBUG`` y de nada más: con
        ``DJANGO_DEBUG=0`` (producción y CI) queda apagado y con ``DJANGO_DEBUG=1`` (desarrollo), encendido;
        no hay una variable propia que pueda dejarlo encendido en producción por error."""
        produccion = cargar_settings_con_debug("0")
        desarrollo = cargar_settings_con_debug("1")

        self.assertIs(produccion.DEBUG, False)
        self.assertIs(produccion.ADMIN_DJANGO_HABILITADO, False)
        self.assertIs(desarrollo.DEBUG, True)
        self.assertIs(desarrollo.ADMIN_DJANGO_HABILITADO, True)
        with mock.patch.dict(os.environ, {"DJANGO_DEBUG": "0", "DJANGO_ADMIN_HABILITADO": "1"}):
            otra_variable = cargar_settings_con_debug("0")
        self.assertIs(otra_variable.ADMIN_DJANGO_HABILITADO, False)
