# Pruebas de la identidad de la organización (D-48, UI-01): ``core/identidad.py`` y el punto de extensión
# ``registrar_identidad_de_la_organizacion`` de ``core/extensiones.py``. Sin registrante, todo se ve como antes (nombre de
# ``NOMBRE_ORGANIZACION``, paleta del sistema); con uno, el nombre y el color principal salen de su ``Identidad``. El color
# solo se escribe en el marco si cumple ``#RRGGBB``. Cada prueba arma sus propios datos.

from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core import extensiones, identidad, servicios
from core.extensiones import Identidad
from core.tests.fabricas import CLAVE, crear_gerente


def _registrante(nombre="Vivero Los Álamos", color="#336699"):
    """Registrante falso de la identidad: devuelve siempre la misma ``Identidad``."""
    return lambda: Identidad(nombre, color)


class IdentidadTests(TestCase):
    """D-48: nombre y color de la organización, con el valor por defecto de D-25 y D-47."""

    @override_settings(NOMBRE_ORGANIZACION="Vivero por defecto")
    def test_d48_sin_registrante_usa_nombre_organizacion(self):
        """D-48: sin registrante, el nombre sale de ``settings.NOMBRE_ORGANIZACION`` y no hay color."""
        with mock.patch.object(extensiones, "_IDENTIDAD", []):
            self.assertEqual(identidad.nombre_de_la_organizacion(), "Vivero por defecto")
            self.assertIsNone(identidad.color_principal())

    def test_d48_con_registrante_usa_su_nombre_y_su_color(self):
        """D-48: con un registrante, la identidad registrada manda sobre la configuración."""
        with mock.patch.object(extensiones, "_IDENTIDAD", [_registrante()]):
            self.assertEqual(identidad.nombre_de_la_organizacion(), "Vivero Los Álamos")
            self.assertEqual(identidad.color_principal(), "#336699")

    @override_settings(NOMBRE_ORGANIZACION="Vivero por defecto")
    def test_d48_nombre_vacio_o_sin_identidad_cae_al_valor_por_defecto(self):
        """D-48: un nombre vacío, o un registrante que devuelve ``None``, cae en ``NOMBRE_ORGANIZACION``."""
        for registrante in (_registrante(nombre="   "), _registrante(nombre=""), lambda: None):
            with self.subTest(registrante=registrante), mock.patch.object(extensiones, "_IDENTIDAD", [registrante]):
                self.assertEqual(identidad.nombre_de_la_organizacion(), "Vivero por defecto")

    def test_d48_color_invalido_no_se_usa(self):
        """D-48: el color solo vale si cumple ``^#[0-9a-fA-F]{6}$``; cualquier otra cosa se ignora."""
        for color in ("rojo", "#12345", "#1234567", "336699", "#33669g", "red;}</style><script>", "", None):
            with self.subTest(color=color), mock.patch.object(extensiones, "_IDENTIDAD", [_registrante(color=color)]):
                self.assertIsNone(identidad.color_principal())

    def test_d48_registrar_es_idempotente(self):
        """D-43/D-48: registrar dos veces la misma función no la repite (``ready()`` puede correr más de una vez)."""
        funcion = _registrante()
        with mock.patch.object(extensiones, "_IDENTIDAD", []):
            extensiones.registrar_identidad_de_la_organizacion(funcion)
            extensiones.registrar_identidad_de_la_organizacion(funcion)
            self.assertEqual(extensiones._IDENTIDAD, [funcion])
            self.assertEqual(extensiones.identidad_registrada(), Identidad("Vivero Los Álamos", "#336699"))


class IdentidadEnElMarcoTests(TestCase):
    """D-48: el marco muestra el nombre y escribe el color, con y sin sesión."""

    def _paginas(self):
        """Devuelve el HTML de una pantalla sin sesión y de otra con sesión."""
        sin_sesion = self.client.get(reverse("core:iniciar_sesion")).content.decode()
        self.client.login(username="gerente@infoponia.com", password=CLAVE)
        con_sesion = self.client.get(reverse("core:inicio")).content.decode()
        return sin_sesion, con_sesion

    def setUp(self):
        crear_gerente()

    def test_d48_color_valido_se_escribe_con_y_sin_sesion(self):
        """D-48: con un color ``#RRGGBB`` el marco escribe ``--primary``, ``--primary-dark`` y ``--primary-soft``."""
        with mock.patch.object(extensiones, "_IDENTIDAD", [_registrante()]):
            for html in self._paginas():
                self.assertIn("--primary:#336699", html)
                self.assertIn("--primary-dark:", html)
                self.assertIn("--primary-soft:", html)
                self.assertIn("Vivero Los Álamos", html)

    def test_d48_color_invalido_no_se_escribe(self):
        """D-48: un color que no cumple ``#RRGGBB`` no se escribe: la pantalla queda con la paleta del sistema."""
        with mock.patch.object(extensiones, "_IDENTIDAD", [_registrante(color="javascript:alert(1)")]):
            for html in self._paginas():
                self.assertNotIn("--primary:", html.split("</head>")[0].split("infoponia.css")[1])
                self.assertNotIn("javascript:alert", html)

    def test_d48_sin_registrante_no_escribe_estilo_de_color(self):
        """D-48: sin registrante el HTML es el de siempre, sin ``<style>`` de color."""
        with mock.patch.object(extensiones, "_IDENTIDAD", []):
            for html in self._paginas():
                self.assertNotIn("--primary-dark:", html)

    def test_d48_una_sola_consulta_por_pedido(self):
        """D-48: el procesador de contexto consulta la identidad una vez por pedido (no usa caché de proceso)."""
        llamadas = []

        def registrante():
            llamadas.append(1)
            return Identidad("Vivero Los Álamos", "#336699")

        self.client.login(username="gerente@infoponia.com", password=CLAVE)
        with mock.patch.object(extensiones, "_IDENTIDAD", [registrante]):
            self.client.get(reverse("core:inicio"))
            self.assertEqual(len(llamadas), 1)
            self.client.get(reverse("core:inicio"))
            self.assertEqual(len(llamadas), 2)


class IdentidadEnElCorreoTests(TestCase):
    """D-48: los correos usan el nombre de la organización registrado."""

    def test_d48_el_correo_usa_el_nombre_registrado(self):
        """D-48: ``_enviar_correo`` escribe el nombre de la identidad registrada, no el de la configuración."""
        cuenta = crear_gerente()
        with mock.patch.object(extensiones, "_IDENTIDAD", [_registrante()]):
            servicios._enviar_correo(
                cuenta, "Asunto", "core/correos/recuperar_contrasena.txt", {"nombre": "Gabriela", "enlace": "https://x/y"}
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Vivero Los Álamos", mail.outbox[0].body)
