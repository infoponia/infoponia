# Pruebas de la identidad de la organización registrada por ``maestros`` (MAE-04, D-48): el perfil guardado cambia el nombre
# y el color del marco, de las pantallas sin sesión y de los correos de ``core``; sin perfil, o con el nombre vacío, manda
# ``NOMBRE_ORGANIZACION``. Aquí NO se reemplaza el punto de extensión: es el registro real de ``MaestrosConfig.ready()``.

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core import extensiones, servicios
from core.tests.fabricas import CLAVE, VaciaImagenesMixin, archivo_de_imagen, crear_gerente
from maestros.models import PerfilOrganizacion
from maestros.servicios import perfil
from maestros.tests.fabricas import ConDatosDeMaestros


class IdentidadDeLaOrganizacionTests(ConDatosDeMaestros, TestCase):
    """D-48: cambiar el perfil cambia lo que ``core`` muestra."""

    def setUp(self):
        self.gerente = crear_gerente()

    def paginas(self):
        """El HTML de una pantalla sin sesión y de otra con sesión."""
        self.client.logout()  # la pantalla de inicio de sesión redirige si ya hay sesión
        sin_sesion = self.client.get(reverse("core:iniciar_sesion")).content.decode()
        self.client.login(username="gerente@infoponia.com", password=CLAVE)
        con_sesion = self.client.get(reverse("core:inicio")).content.decode()
        return sin_sesion, con_sesion

    def test_d48_maestros_registra_su_identidad_al_iniciar(self):
        """D-48: ``MaestrosConfig.ready()`` registra ``perfil.identidad`` en el punto de extensión de ``core``."""
        self.assertIn(perfil.identidad, extensiones._IDENTIDAD)

    @override_settings(NOMBRE_ORGANIZACION="Nombre por defecto")
    def test_d48_el_nombre_del_perfil_cambia_el_contexto_y_las_pantallas(self):
        """D-48 y ADM-MOD-ORG regla 6: al cambiar el nombre del perfil cambia ``nombre_organizacion`` del contexto, con y sin
        sesión, desde el pedido siguiente; con ``NOMBRE_ORGANIZACION`` distinto, el perfil gana."""
        perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero Los Álamos")
        for html in self.paginas():
            self.assertIn("Vivero Los Álamos", html)
            self.assertNotIn("Nombre por defecto", html)
        self.assertEqual(self.client.get(reverse("core:inicio")).context["nombre_organizacion"], "Vivero Los Álamos")

    @override_settings(NOMBRE_ORGANIZACION="Nombre por defecto")
    def test_d48_el_nombre_del_perfil_aparece_en_un_correo_de_core(self):
        """D-48: el correo de ``core`` (``_enviar_correo``) escribe el nombre del perfil guardado."""
        perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero Los Álamos")
        servicios._enviar_correo(
            self.gerente, "Asunto", "core/correos/recuperar_contrasena.txt", {"nombre": "Gabriela", "enlace": "https://x/y"}
        )
        self.assertIn("Vivero Los Álamos", mail.outbox[0].body)
        self.assertNotIn("Nombre por defecto", mail.outbox[0].body)

    def test_d48_un_color_valido_escribe_las_tres_variables_con_y_sin_sesion(self):
        """D-48: con el color 1 cargado, el marco escribe ``--primary``, ``--primary-dark`` y ``--primary-soft``."""
        perfil.modificar_perfil(self.gerente, color_primario="#2e7d32")
        for html in self.paginas():
            self.assertIn("--primary:#2E7D32", html)
            self.assertIn("--primary-dark:", html)
            self.assertIn("--primary-soft:", html)

    def test_d48_sin_colores_no_escribe_nada(self):
        """D-48 y ADM-MOD-ORG regla 5: sin color 1 el marco no escribe el ``<style>`` de color (paleta del sistema), y borrar
        el color vuelve a la paleta."""
        perfil.modificar_perfil(self.gerente, color_primario="#2E7D32")
        perfil.modificar_perfil(self.gerente, color_primario="")
        for html in self.paginas():
            self.assertNotIn("--primary-dark:", html)

    def test_d48_el_color_secundario_no_tine_el_sistema(self):
        """D-48: solo el primer color es el principal; los otros no escriben variables."""
        perfil.modificar_perfil(self.gerente, color_primario="#2E7D32", color_secundario="#AABBCC")
        for html in self.paginas():
            self.assertNotIn("#AABBCC", html)

    @override_settings(NOMBRE_ORGANIZACION="Nombre por defecto")
    def test_d48_sin_fila_o_con_nombre_vacio_se_usa_nombre_organizacion(self):
        """D-48: sin perfil (o con el nombre vacío) el nombre sale de ``NOMBRE_ORGANIZACION``."""
        PerfilOrganizacion.objects.update(nombre_organizacion="")
        for html in self.paginas():
            self.assertIn("Nombre por defecto", html)
        PerfilOrganizacion.objects.all().delete()
        for html in self.paginas():
            self.assertIn("Nombre por defecto", html)


class LogoEnElMarcoTests(VaciaImagenesMixin, ConDatosDeMaestros, TestCase):
    """D-106 puntos 14 y 15: el logo guardado reemplaza al ícono en el encabezado y en las pantallas sin sesión; sin logo, el ícono.
    Aquí NO se reemplaza el punto de extensión: es el registro real de ``MaestrosConfig.ready()``."""

    def setUp(self):
        super().setUp()
        self.gerente = crear_gerente()

    def paginas(self):
        """El HTML de una pantalla sin sesión y de otra con sesión."""
        self.client.logout()
        sin_sesion = self.client.get(reverse("core:iniciar_sesion")).content.decode()
        self.client.login(username="gerente@infoponia.com", password=CLAVE)
        con_sesion = self.client.get(reverse("core:inicio")).content.decode()
        return sin_sesion, con_sesion

    def test_d106_sin_logo_el_marco_muestra_el_icono(self):
        """D-106 punto 14: sin logo, el cuadro ``.logo`` lleva el ícono ``leafmark`` de siempre, con y sin sesión."""
        for html in self.paginas():
            self.assertIn('<div class="logo"><svg', html)
            self.assertNotIn("logo-imagen", html)

    def test_d106_con_logo_el_marco_muestra_la_imagen_en_lugar_del_icono(self):
        """D-106 punto 14: con logo, el encabezado y la pantalla de inicio de sesión muestran la imagen y no el ícono."""
        perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("l.png", tamano=(300, 100)))
        url = PerfilOrganizacion.objects.get().logo.url
        for html in self.paginas():
            self.assertIn(f'<div class="logo logo-imagen"><img src="{url}" alt="" decoding="async"></div>', html)
            self.assertNotIn('<div class="logo"><svg', html)

    def test_d106_la_identidad_de_la_organizacion_trae_la_url_del_logo(self):
        """D-106 punto 15: el contexto del marco trae ``logo_url``, que sale de la identidad registrada por ``maestros``."""
        self.assertIsNone(self.client.get(reverse("core:iniciar_sesion")).context["logo_url"])
        perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("l.png"))
        self.assertEqual(
            self.client.get(reverse("core:iniciar_sesion")).context["logo_url"], PerfilOrganizacion.objects.get().logo.url
        )

    def test_d106_al_quitar_el_logo_el_marco_vuelve_al_icono_desde_el_pedido_siguiente(self):
        """D-48 y D-106 punto 14: sin caché de proceso, quitar el logo se ve en el pedido siguiente."""
        perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("l.png"))
        with self.captureOnCommitCallbacks(execute=True):
            perfil.modificar_perfil(self.gerente, quitar_logo=True)
        for html in self.paginas():
            self.assertNotIn("logo-imagen", html)

    def test_d106_los_correos_siguen_con_el_nombre_y_sin_imagen(self):
        """D-106 punto 14: el logo no va en los correos (la URL firmada vence a la hora): el cuerpo no menciona la imagen."""
        perfil.modificar_perfil(self.gerente, logo=archivo_de_imagen("l.png"))
        servicios._enviar_correo(
            self.gerente, "Asunto", "core/correos/recuperar_contrasena.txt", {"nombre": "Gabriela", "enlace": "https://x/y"}
        )
        cuerpo = mail.outbox[0].body
        self.assertNotIn("logos/", cuerpo)
        self.assertNotIn("<img", cuerpo)
