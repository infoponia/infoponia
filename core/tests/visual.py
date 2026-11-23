# Ayuda para la verificación VISUAL de las pantallas (docs/patrones/verificacion_por_claude.md): una clase base que levanta el sistema de verdad
# (``StaticLiveServerTestCase``, con su propia base de pruebas: no toca la base local de desarrollo) y lo maneja con Playwright y Chromium. No es un
# archivo de pruebas: lo importan los ``test_visual_*.py`` de cada app.
#
# Qué da: iniciar sesión por el formulario real, sacar capturas de pantalla (a ``INFOPONIA_CAPTURAS`` o a la carpeta temporal ``infoponia_capturas``),
# y juntar los errores de JavaScript y de consola para que una prueba falle si la pantalla los tiene. Playwright es una dependencia SOLO de desarrollo
# (``requirements-dev.txt``): sin ella (el CI, Render) las clases que heredan de ``PruebaVisual`` se saltan solas. Se corren aparte, con
# ``INFOPONIA_VISUAL=1 python manage.py test <app> --tag visual`` (PowerShell: ``$env:INFOPONIA_VISUAL="1"``). Sin esa variable se saltan: las corridas normales, con ``--parallel``, no las ejecutan.

import os
import tempfile
import unittest
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag
from django.urls import reverse

from core.tests.fabricas import CLAVE

try:  # Playwright es opcional: solo está en requirements-dev.txt
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depende del entorno
    sync_playwright = None

ANCHO_DE_ESCRITORIO = {"width": 1280, "height": 800}
ANCHO_DE_CELULAR = {"width": 390, "height": 844}


def carpeta_de_capturas():
    """La carpeta donde se guardan las capturas: ``INFOPONIA_CAPTURAS`` o ``<temporal>/infoponia_capturas``."""
    carpeta = Path(os.environ.get("INFOPONIA_CAPTURAS") or Path(tempfile.gettempdir()) / "infoponia_capturas")
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


@tag("visual")
@unittest.skipIf(sync_playwright is None, "Playwright no está instalado (pip install -r requirements-dev.txt; python -m playwright install chromium)")
@unittest.skipUnless(os.environ.get("INFOPONIA_VISUAL") == "1", "Las pruebas visuales se corren aparte: INFOPONIA_VISUAL=1 y --tag visual")
class PruebaVisual(StaticLiveServerTestCase):
    """Base de las pruebas visuales: un Chromium por clase y una página nueva por prueba. Como es un ``TransactionTestCase``, su ``flush`` vacía los
    datos que cargan las migraciones: la prueba los vuelve a asegurar en ``setUp`` (docs/patrones/datos_de_migracion.md)."""

    @classmethod
    def setUpClass(cls):
        # El navegador de Playwright corre un bucle de eventos: Django lo toma por «contexto asíncrono» y se negaría a tocar la base.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls._playwright = sync_playwright().start()
        cls._navegador = cls._playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls._navegador.close()
        cls._playwright.stop()
        super().tearDownClass()

    def nueva_pagina(self, viewport=ANCHO_DE_ESCRITORIO, javascript=True):
        """Una página con su propio contexto (sin sesión). Junta en ``self.errores_de_consola`` los errores de JavaScript y de consola."""
        contexto = self._navegador.new_context(viewport=viewport, java_script_enabled=javascript, locale="es-AR")
        self.addCleanup(contexto.close)
        pagina = contexto.new_page()
        self.errores_de_consola = getattr(self, "errores_de_consola", [])
        pagina.on("pageerror", lambda error: self.errores_de_consola.append(f"JavaScript: {error}"))
        pagina.on(
            "console",
            lambda mensaje: self.errores_de_consola.append(f"consola: {mensaje.text}") if mensaje.type == "error" else None,
        )
        return pagina

    def url(self, nombre, *args):
        """La dirección completa (con el servidor de la prueba) de la ruta ``nombre``."""
        return f"{self.live_server_url}{reverse(nombre, args=args)}"

    def entrar(self, pagina, cuenta, clave=CLAVE):
        """Inicia sesión como ``cuenta`` por el formulario real y deja la página en la pantalla a la que lleva el inicio de sesión."""
        pagina.goto(self.url("core:iniciar_sesion"))
        pagina.fill("#id_username", cuenta.email)
        pagina.fill("#id_password", clave)
        pagina.click("form button[type=submit]")
        pagina.wait_for_load_state("networkidle")
        self.assertNotIn("iniciar-sesion", pagina.url, "No se pudo iniciar sesión")

    def capturar(self, pagina, nombre):
        """Guarda una captura de la página entera como ``<carpeta>/<nombre>.png`` y devuelve su ruta."""
        ruta = carpeta_de_capturas() / f"{nombre}.png"
        pagina.screenshot(path=str(ruta), full_page=True)
        return ruta

    def assertSinScrollHorizontal(self, pagina):
        """La página no se desborda a lo ancho (se ve bien en un celular)."""
        ancho = pagina.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        self.assertLessEqual(ancho[0], ancho[1], f"La página se desborda: ancho {ancho[0]} contra ventana {ancho[1]}")

    def assertSinErroresDeJavaScript(self):
        """Ninguna pantalla visitada dejó errores de JavaScript ni de consola."""
        self.assertEqual(getattr(self, "errores_de_consola", []), [])
