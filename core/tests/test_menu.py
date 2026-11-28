# Pruebas del punto de extensión del menú lateral (MAE-01b, regla A4 de D-37, D-25): las apps de nivel mayor registran su
# entrada en ``AppConfig.ready()`` con ``core.menu.registrar_entrada`` y el menú se arma con ``core.menu.menu_de``.
# ``core`` no nombra «Producción»: la registra ``maestros``.
# UI-05 (UX-07; D-109 punto 4): el botón «Menú» del celular despliega las mismas entradas que el menú lateral.

import re
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core import menu
from core.models import Agronomo, Capataz, Contador, Gerente, Tecnico, Transportista, Usuario, Vendedor
from core.tests.fabricas import crear_administrador, crear_cuenta

ROL = Usuario.Rol
NUEVA = ("Cosecha", "core:inicio", "dash")


class MenuExtensionTests(SimpleTestCase):
    """``registrar_entrada`` y ``menu_de`` (D-37, regla A4; D-25: el menú muestra solo lo que existe)."""

    def registradas(self, contenido=None):
        """Reemplaza las entradas registradas por las de la prueba, para no depender de las apps instaladas."""
        return mock.patch.object(menu, "_ENTRADAS_DE_APPS", {} if contenido is None else contenido)

    def test_d37_core_no_nombra_las_entradas_de_las_apps_de_negocio(self):
        """D-37, regla A1: ``core`` (nivel 1) no puede nombrar una URL de ``maestros``; el menú fijo de ``core`` no la tiene."""
        textos = [texto for entradas in menu.MENU_POR_ROL.values() for texto, _, _ in entradas]
        self.assertNotIn("Producción", textos)

    def test_d37_una_entrada_registrada_va_despues_de_la_indicada(self):
        """D-37, regla A4: la app registra su entrada y el menú la pone después de la que se indica."""
        with self.registradas():
            menu.registrar_entrada(NUEVA, [ROL.GERENTE], despues_de="Panel de control")
            textos = [texto for texto, _, _ in menu.menu_de(ROL.GERENTE)]
        self.assertEqual(textos, ["Panel de control", "Cosecha", "Usuarios y seguridad", "Auditoría"])

    def test_d37_sin_despues_de_o_con_uno_que_no_esta_va_al_final(self):
        """D-37, regla A4: sin ``despues_de``, o con un texto que no figura, la entrada va al final."""
        with self.registradas():
            menu.registrar_entrada(NUEVA, [ROL.AGRONOMO])
            self.assertEqual(menu.menu_de(ROL.AGRONOMO)[-1], NUEVA)
        with self.registradas():
            menu.registrar_entrada(NUEVA, [ROL.AGRONOMO], despues_de="No existe")
            self.assertEqual(menu.menu_de(ROL.AGRONOMO)[-1], NUEVA)

    def test_d37_registrar_dos_veces_la_misma_entrada_no_la_repite(self):
        """D-37, regla A4: ``ready()`` puede volver a correr; la misma entrada para el mismo rol no se repite."""
        with self.registradas():
            menu.registrar_entrada(NUEVA, [ROL.GERENTE])
            menu.registrar_entrada(NUEVA, [ROL.GERENTE])
            self.assertEqual(menu.menu_de(ROL.GERENTE).count(NUEVA), 1)

    def test_d37_solo_la_ven_los_roles_indicados_y_no_se_pisa_el_menu_fijo(self):
        """D-37, regla A4: un rol sin la entrada no la ve, y registrar no modifica ``MENU_POR_ROL``."""
        fijo = {rol: list(entradas) for rol, entradas in menu.MENU_POR_ROL.items()}
        with self.registradas():
            menu.registrar_entrada(NUEVA, [ROL.GERENTE])
            self.assertNotIn(NUEVA, menu.menu_de(ROL.VENDEDOR))
            self.assertIn(NUEVA, menu.menu_de(ROL.GERENTE))
        self.assertEqual(menu.MENU_POR_ROL, fijo)

    def test_d37_maestros_registra_produccion_para_el_gerente_y_el_agronomo(self):
        """MAE-01 y D-37, regla A4: con las apps instaladas, el Gerente y el Agrónomo ven «Producción» justo después del
        «Panel de control»; el Vendedor no."""
        for rol in (ROL.GERENTE, ROL.AGRONOMO):
            with self.subTest(rol=rol):
                textos = [texto for texto, _, _ in menu.menu_de(rol)]
                self.assertEqual(textos[:2], ["Panel de control", "Producción"])
        self.assertNotIn("Producción", [texto for texto, _, _ in menu.menu_de(ROL.VENDEDOR)])


def _entradas(html, apertura, cierre):
    """``[(texto, href, aria-current)]`` de los enlaces que hay entre ``apertura`` y ``cierre`` en ``html``."""
    inicio = html.index(apertura)
    tramo = html[inicio : html.index(cierre, inicio)]
    entradas = []
    for atributos, interior in re.findall(r"<a ([^>]*)>(.*?)</a>", tramo, flags=re.S):
        texto = " ".join(re.sub(r"<[^>]+>", " ", interior).split())
        href = re.search(r'href="([^"]*)"', atributos).group(1)
        actual = re.search(r'aria-current="([^"]*)"', atributos)
        entradas.append((texto, href, actual.group(1) if actual else None))
    return entradas


class MenuDelCelularTests(TestCase):
    """UI-05 paso 1 (UX-07; D-109 punto 4): en menos de 760 px, el botón «Menú» (un ``<details>``) despliega las mismas entradas
    del menú lateral, con la activa marcada. Que se vea como botón y se cierre con Esc se mira a mano."""

    PANEL = '<nav class="menu-celular-panel"'

    def abrir(self, cuenta, ruta="core:mi_perfil"):
        """Entra con ``cuenta`` y devuelve el HTML de ``ruta`` (por defecto «Mi perfil», que tienen todos los roles)."""
        self.client.force_login(cuenta)
        respuesta = self.client.get(reverse(ruta))
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.content.decode()

    def test_ui05_el_menu_del_celular_trae_las_mismas_entradas_que_el_lateral_para_cada_rol(self):
        """D-109 punto 4: «Menú» reutiliza ``core/menu.py`` (la misma lista, en el mismo orden); no hay una segunda lista."""
        cuentas = {
            Usuario.Rol.GERENTE: crear_cuenta(Gerente, "ger@infoponia.com"),
            Usuario.Rol.AGRONOMO: crear_cuenta(Agronomo, "agr@infoponia.com"),
            Usuario.Rol.VENDEDOR: crear_cuenta(Vendedor, "ven@infoponia.com"),
            Usuario.Rol.CONTADOR: crear_cuenta(Contador, "con@infoponia.com"),
        }
        for rol, cuenta in cuentas.items():
            with self.subTest(rol=rol):
                html = self.abrir(cuenta)
                celular = _entradas(html, self.PANEL, "</nav>")
                lateral = _entradas(html, '<aside class="side">', "</aside>")
                self.assertEqual(celular, lateral)
                self.assertEqual([texto for texto, _, _ in celular], [texto for texto, _, _ in menu.menu_de(rol)])
                self.assertIn('<summary class="btn btn-ghost">', html)
                self.assertIn("<span>Menú</span>", html)

    def test_ui05_el_administrador_tambien_tiene_el_menu_del_celular(self):
        """D-109 punto 4: el Administrador (Cuentas y Auditoría) tiene menú lateral, así que también tiene «Menú»."""
        html = self.abrir(crear_administrador())
        celular = _entradas(html, self.PANEL, "</nav>")
        self.assertEqual(celular, _entradas(html, '<aside class="side">', "</aside>"))
        self.assertEqual([texto for texto, _, _ in celular], ["Cuentas", "Auditoría"])

    def test_ui05_la_entrada_activa_se_marca_igual_en_los_dos_menus(self):
        """D-109 punto 4: en «Usuarios y seguridad», las dos listas marcan esa entrada con ``aria-current="page"`` y ninguna otra."""
        html = self.abrir(crear_cuenta(Gerente, "ger@infoponia.com"), ruta="core:usuarios")
        for tramo in (self.PANEL, '<aside class="side">'):
            with self.subTest(tramo=tramo):
                entradas = _entradas(html, tramo, "</nav>" if tramo == self.PANEL else "</aside>")
                activas = [texto for texto, _, actual in entradas if actual == "page"]
                self.assertEqual(activas, ["Usuarios y seguridad"])

    def test_ui05_el_modo_campo_no_muestra_el_menu_del_celular(self):
        """D-25 y D-109 punto 4: Capataz, Técnico y Transportista no tienen menú lateral ni «Menú»; su marco no cambia."""
        for clase in (Capataz, Tecnico, Transportista):
            with self.subTest(rol=clase.__name__):
                html = self.abrir(crear_cuenta(clase, f"{clase.__name__.lower()}@infoponia.com"))
                self.assertNotIn("data-menu-celular", html)
                self.assertNotIn("menu-celular", html)
                self.assertNotIn('<aside class="side">', html)
                self.assertIn('class="shell field"', html)

    def test_ui05_ninguna_plantilla_usa_la_fila_mnav(self):
        """D-109 punto 4 y UI-05, paso 1: la fila de fichas ``.mnav`` salió del marco; el menú del celular es ``.menu-celular``."""
        html = self.abrir(crear_cuenta(Gerente, "ger@infoponia.com"))
        self.assertNotIn("mnav", html)
