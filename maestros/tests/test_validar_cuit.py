# Pruebas de ``validar_cuit`` y ``formatear_cuit`` de ``maestros/validadores.py`` (COM-01, paso 2; D-58 punto 4 y
# docs/api/direcciones.md, «CUIT»). El cálculo es el de ``cuitOk`` del prototipo y el de ADM-MOD-ORG.

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from maestros.validadores import formatear_cuit, validar_cuit

MENSAJE = "El CUIT no es válido: revisá los números (11 dígitos, con su dígito verificador)."


class ValidarCuitTests(SimpleTestCase):
    """``validar_cuit(valor) -> str`` (docs/api/direcciones.md, «CUIT»)."""

    def rechaza(self, valor):
        with self.assertRaises(ValidationError) as contexto:
            validar_cuit(valor)
        return contexto.exception

    def test_d58_valido_sin_guiones_devuelve_los_11_digitos(self):
        """D-58 punto 4: un CUIT válido sin guiones se devuelve igual."""
        self.assertEqual(validar_cuit("30712345671"), "30712345671")

    def test_d58_valido_con_guiones_y_espacios_devuelve_solo_digitos(self):
        """D-58 punto 4 (regla 1 de COM-ALT-CLT): se acepta con o sin guiones ni espacios."""
        for escrito in ("30-71234567-1", " 30-71234567-1 ", "30 71234567 1"):
            with self.subTest(escrito=escrito):
                self.assertEqual(validar_cuit(escrito), "30712345671")

    def test_d58_resto_11_da_verificador_0(self):
        """API de direcciones: un resto que da 11 vale 0."""
        self.assertEqual(validar_cuit("30000000090"), "30000000090")

    def test_d58_resto_10_no_es_valido(self):
        """API de direcciones: un verificador que daría 10 no es válido, sea cual sea el último dígito."""
        for ultimo in "0123456789":
            with self.subTest(ultimo=ultimo):
                self.assertEqual(self.rechaza(f"3000000004{ultimo}").code, "cuit_invalido")

    def test_d58_verificador_incorrecto_se_rechaza_con_su_codigo_y_mensaje(self):
        """D-58 punto 4: ``cuit_invalido`` con el mensaje de ADM-MOD-ORG."""
        error = self.rechaza("30-71234567-2")
        self.assertEqual(error.code, "cuit_invalido")
        self.assertEqual(error.messages, [MENSAJE])

    def test_d58_menos_y_mas_de_11_digitos_se_rechazan(self):
        """API de direcciones: si no son 11 dígitos, ``cuit_invalido``."""
        for escrito in ("3071234567", "307123456712", "", "   "):
            with self.subTest(escrito=escrito):
                self.assertEqual(self.rechaza(escrito).code, "cuit_invalido")

    def test_d58_letras_y_otros_signos_se_rechazan(self):
        """API de direcciones: con letras o signos distintos de guion y espacio, ``cuit_invalido``."""
        for escrito in ("30-7123456A-1", "30.71234567.1", "3071234567١"):
            with self.subTest(escrito=escrito):
                self.assertEqual(self.rechaza(escrito).code, "cuit_invalido")

    def test_d58_none_se_rechaza(self):
        """API de direcciones: un valor ausente no es un CUIT."""
        self.assertEqual(self.rechaza(None).code, "cuit_invalido")


class FormatearCuitTests(SimpleTestCase):
    """``formatear_cuit(valor) -> str`` (docs/api/direcciones.md, «CUIT»)."""

    def test_d58_formatea_con_guiones(self):
        """API de direcciones: ``formatear_cuit("30712345671") -> "30-71234567-1"``."""
        self.assertEqual(formatear_cuit("30712345671"), "30-71234567-1")

    def test_d58_un_valor_que_no_son_11_digitos_se_devuelve_igual(self):
        """Defensivo: lo que no tiene 11 dígitos no se toca (no se rompe una pantalla por un dato viejo)."""
        self.assertEqual(formatear_cuit("123"), "123")
        self.assertEqual(formatear_cuit(""), "")
