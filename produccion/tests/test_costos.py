# Pruebas de `produccion/servicios/costos.py` (PRD-01, paso 3): costo por planta y costo de las plantas perdidas.
# Fuente: docs/patrones/costo_del_lote.md («Costo de las plantas perdidas», «Ejemplos» y «Funciones»), D-50 punto 5 y MD-79.
# `produccion.servicios.costos` se toma del módulo dentro de cada prueba: mientras no exista, falla cada prueba por separado.

from decimal import Decimal

from django.test import SimpleTestCase

from inventario.tests.fabricas import perezoso

costos = perezoso("produccion.servicios.costos")


class FalsoLote:
    """Un lote mínimo (sin base de datos): `cantidad_actual` y `costo_acumulado` son lo único que miran las funciones de costo."""

    def __init__(self, cantidad_actual, costo_acumulado):
        self.cantidad_actual = cantidad_actual
        self.costo_acumulado = Decimal(costo_acumulado)


class CostosTests(SimpleTestCase):
    # ---- Los cuatro ejemplos de la tabla del patrón ----

    def test_d50_ejemplo_1_merma_de_20_de_200_plantas_a_5_por_planta(self):
        """costo_del_lote.md, ejemplo 1: c = 200, K = 1.000,00; merma de 20 → 100,00; quedan 900,00 (5,00 por planta)."""
        lote = FalsoLote(200, "1000.00")
        self.assertEqual(costos.costo_de_la_merma(lote, 20), Decimal("100.00"))
        self.assertEqual(costos.costo_por_planta(FalsoLote(180, "900.00")), Decimal("5.00"))

    def test_d50_ejemplo_2_merma_de_1_de_3_plantas_redondea_half_up(self):
        """Ejemplo 2: c = 3, K = 10,00; merma de 1 → 10 × 1 ÷ 3 = 3,3333… → 3,33; quedan 6,67 y 3,335 → se muestra 3,34."""
        self.assertEqual(costos.costo_de_la_merma(FalsoLote(3, "10.00"), 1), Decimal("3.33"))
        self.assertEqual(costos.costo_por_planta(FalsoLote(2, "6.67")), Decimal("3.34"))  # 3,335 con ROUND_HALF_UP

    def test_d50_ejemplo_3_perder_todo_el_lote_cuesta_el_costo_entero(self):
        """Ejemplo 3: n = c → el costo de la merma es K entero (no se pierde ni sobra un centavo)."""
        self.assertEqual(costos.costo_de_la_merma(FalsoLote(3, "10.00"), 3), Decimal("10.00"))

    def test_d50_ejemplo_4_siembra_sin_costo(self):
        """Ejemplo 4: c = 7, K = 0,00; merma de 2 → 0,00 y el costo por planta es 0,00."""
        self.assertEqual(costos.costo_de_la_merma(FalsoLote(7, "0.00"), 2), Decimal("0.00"))
        self.assertEqual(costos.costo_por_planta(FalsoLote(7, "0.00")), Decimal("0.00"))

    # ---- Casos del patrón ----

    def test_d50_n_igual_a_c_con_costo_10_01_y_3_plantas_no_pierde_un_centavo(self):
        """«Pruebas» del patrón: con K = 10,01 y c = 3, `n = c` da 10,01 exacto (con la fórmula daría 10,01 pero con otros números
        se perdería un centavo: por eso `n = c` se trata aparte)."""
        self.assertEqual(costos.costo_de_la_merma(FalsoLote(3, "10.01"), 3), Decimal("10.01"))

    def test_d50_la_suma_de_las_mermas_parciales_hasta_vaciar_el_lote_es_el_costo_de_la_siembra(self):
        """«Pruebas» del patrón (propiedad): Σ costo_de_la_merma = K inicial cuando se pierde todo, para varios K, c y pasos."""
        for costo, plantas, pasos in (("10.01", 3, [1, 1, 1]), ("100.00", 7, [2, 3, 2]), ("33.33", 9, [4, 4, 1]), ("0.01", 5, [1] * 5)):
            with self.subTest(costo=costo, plantas=plantas):
                lote = FalsoLote(plantas, costo)
                perdido = Decimal("0")
                for n in pasos:
                    parte = costos.costo_de_la_merma(lote, n)
                    perdido += parte
                    lote.cantidad_actual -= n
                    lote.costo_acumulado -= parte
                    self.assertGreaterEqual(lote.costo_acumulado, 0, "el costo nunca es negativo")
                self.assertEqual(lote.cantidad_actual, 0)
                self.assertEqual(perdido, Decimal(costo))
                self.assertEqual(lote.costo_acumulado, Decimal("0.00"), "cantidad_actual = 0 implica costo 0")

    def test_d50_costo_por_planta_sin_plantas_es_none(self):
        """`costo_por_planta` devuelve `None` si la cantidad actual es 0."""
        self.assertIsNone(costos.costo_por_planta(FalsoLote(0, "0.00")))

    def test_d50_merma_invalida_lanza_value_error(self):
        """`0 < n ≤ c`: una merma de 0, negativa o mayor que las plantas del lote es un error de programación."""
        lote = FalsoLote(5, "10.00")
        for n in (0, -1, 6):
            with self.subTest(n=n), self.assertRaises(ValueError):
                costos.costo_de_la_merma(lote, n)

    def test_d50_redondear_monto_usa_round_half_up_a_dos_decimales(self):
        """`redondear_monto`: `quantize(0.01, ROUND_HALF_UP)`; nunca float."""
        self.assertEqual(costos.redondear_monto(Decimal("3.335")), Decimal("3.34"))
        self.assertEqual(costos.redondear_monto(Decimal("2.345")), Decimal("2.35"))
        self.assertEqual(costos.redondear_monto(Decimal("2.344")), Decimal("2.34"))
        self.assertEqual(costos.redondear_monto(Decimal("5")), Decimal("5.00"))
