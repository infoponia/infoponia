# Pruebas de `inventario/unidades.py` (INV-01, paso 1): cada unidad con sus decimales, el redondeo y los valores límite.
# Fuente: regla 5 de CMP-ALT-INS y regla 2 de 8.23 (unidad solo enteros; kg, L y m³ hasta 3 decimales; g, mL, m y m² hasta 2).

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.unidades import DECIMALES, Unidad, cuantizar, decimales_de, texto_de_decimales, validar_cantidad

DECIMALES_ESPERADOS = {
    "unidad": 0,
    "kg": 3,
    "g": 2,
    "l": 3,
    "ml": 2,
    "m3": 3,
    "m": 2,
    "m2": 2,
}


class UnidadesTests(SimpleTestCase):
    """Las ocho unidades y sus decimales (regla 5 de CMP-ALT-INS)."""

    def test_regla_cmp_alt_ins_5_son_ocho_unidades_con_sus_decimales(self):
        """CMP-ALT-INS regla 5: la lista fija de ocho y los decimales de cada una."""
        self.assertEqual({u.value: DECIMALES[u] for u in Unidad}, DECIMALES_ESPERADOS)

    def test_regla_cmp_alt_ins_5_las_etiquetas_se_ven_como_el_caso_de_uso(self):
        """CMP-ALT-INS regla 5: se guardan en minúscula (modelo) y se muestran «L», «mL», «m³» y «m²»."""
        self.assertEqual(Unidad.L.label, "L")
        self.assertEqual(Unidad.ML.label, "mL")
        self.assertEqual(Unidad.M3.label, "m³")
        self.assertEqual(Unidad.M2.label, "m²")

    def test_regla_cmp_alt_ins_5_el_texto_de_decimales_se_ofrece_para_cada_unidad(self):
        """Verificación a mano 6: las ocho unidades se ofrecen con el texto de sus decimales."""
        self.assertEqual(texto_de_decimales("unidad"), "solo enteros")
        self.assertEqual(texto_de_decimales("kg"), "admite 3 decimales")
        self.assertEqual(texto_de_decimales("g"), "admite 2 decimales")

    def test_regla_cmp_alt_ins_5_unidad_desconocida_lanza_value_error(self):
        """Una unidad que no está en la lista no tiene decimales."""
        with self.assertRaises(ValueError):
            decimales_de("docena")

    def test_regla_cmp_alt_ins_5_cada_unidad_acepta_su_limite_de_decimales(self):
        """El valor límite: exactamente los decimales que admite la unidad se acepta (y se devuelve cuantizado)."""
        casos = {
            "unidad": ("7", "7"),
            "kg": ("1.234", "1.234"),
            "g": ("1.23", "1.23"),
            "l": ("0.001", "0.001"),
            "ml": ("5.5", "5.50"),
            "m3": ("2", "2.000"),
            "m": ("3.14", "3.14"),
            "m2": ("0.01", "0.01"),
        }
        for unidad, (valor, esperado) in casos.items():
            with self.subTest(unidad=unidad):
                self.assertEqual(validar_cantidad(Decimal(valor), unidad), Decimal(esperado))

    def test_regla_cmp_alt_ins_5_cada_unidad_rechaza_un_decimal_de_mas(self):
        """El valor límite de arriba: un decimal más que los que admite la unidad se rechaza con su código."""
        casos = {"unidad": "1.5", "kg": "1.2345", "g": "1.234", "l": "0.0001", "ml": "1.001", "m3": "1.0001", "m": "1.005", "m2": "0.001"}
        for unidad, valor in casos.items():
            with self.subTest(unidad=unidad):
                with self.assertRaises(ValidationError) as error:
                    validar_cantidad(Decimal(valor), unidad)
                self.assertEqual(error.exception.code, "decimales_de_la_unidad")

    def test_regla_cmp_alt_ins_5_el_mensaje_nombra_la_unidad_y_su_limite(self):
        """El texto de «decimales que admite la unidad» (docs/api/stock.md)."""
        with self.assertRaises(ValidationError) as error:
            validar_cantidad(Decimal("1.5"), "unidad")
        self.assertIn("solo admite cantidades enteras", error.exception.messages[0])
        with self.assertRaises(ValidationError) as error:
            validar_cantidad(Decimal("1.2345"), "kg")
        self.assertIn("hasta 3 decimales", error.exception.messages[0])

    def test_regla_cmp_alt_ins_5_acepta_texto_con_coma(self):
        """Una cantidad escrita por una persona («2,5») se interpreta como 2.5 (nunca como float)."""
        self.assertEqual(validar_cantidad("2,5", "kg"), Decimal("2.500"))

    def test_regla_cmp_alt_ins_5_rechaza_lo_que_no_es_un_numero(self):
        """Texto, vacío e infinitos se rechazan con `cantidad_invalida`."""
        for valor in ["abc", "", "NaN", "Infinity", "1.2.3"]:
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError) as error:
                    validar_cantidad(valor, "kg")
                self.assertEqual(error.exception.code, "cantidad_invalida")

    def test_regla_cmp_alt_ins_5_un_float_se_rechaza_con_type_error(self):
        """CLAUDE.md: nunca `float`; pasar uno es un error de uso, no se redondea en silencio."""
        with self.assertRaises(TypeError):
            validar_cantidad(1.5, "kg")

    def test_regla_cmp_alt_ins_5_no_juzga_el_signo(self):
        """El signo lo decide cada caso de uso: cero y negativos pasan `validar_cantidad` si tienen los decimales justos."""
        self.assertEqual(validar_cantidad(Decimal("0"), "kg"), Decimal("0.000"))
        self.assertEqual(validar_cantidad(Decimal("-2"), "unidad"), Decimal("-2"))

    def test_regla_cmp_alt_ins_5_cuantizar_redondea_mitad_hacia_arriba(self):
        """`cuantizar` es para cantidades calculadas: redondea a los decimales de la unidad (mitad hacia arriba)."""
        self.assertEqual(cuantizar(Decimal("2.5"), "unidad"), Decimal("3"))
        self.assertEqual(cuantizar(Decimal("1.005"), "g"), Decimal("1.01"))
        self.assertEqual(cuantizar(Decimal("1.0004"), "kg"), Decimal("1.000"))
        self.assertEqual(cuantizar(Decimal("1.0005"), "kg"), Decimal("1.001"))

    def test_d36_texto_de_cantidad_y_de_precio_tienen_los_decimales_fijos(self):
        """D-36: `Decimal` va como texto a la auditoría: cantidad con los decimales de la unidad; precio con 2."""
        self.assertEqual(texto_cantidad(Decimal("12.5"), "l"), "12.500")
        self.assertEqual(texto_cantidad(Decimal("12"), "unidad"), "12")
        self.assertEqual(texto_cantidad(Decimal("0.5"), "g"), "0.50")
        self.assertEqual(texto_precio(Decimal("5")), "5.00")
        self.assertEqual(texto_precio(Decimal("5.126")), "5.13")
