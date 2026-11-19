# Pruebas del punto de extensión del menú lateral (MAE-01b, regla A4 de D-37, D-25): las apps de nivel mayor registran su
# entrada en ``AppConfig.ready()`` con ``core.menu.registrar_entrada`` y el menú se arma con ``core.menu.menu_de``.
# ``core`` no nombra «Producción»: la registra ``maestros``.

from unittest import mock

from django.test import SimpleTestCase

from core import menu
from core.models import Usuario

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
