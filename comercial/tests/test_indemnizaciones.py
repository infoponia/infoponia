# Pruebas de `comercial/servicios/indemnizaciones.py` (COM-07a, paso 2): tablas para cada cálculo, con los ejemplos de las reglas, el redondeo, el tope exacto y un centavo más y la aplicación con
# monto 0, menor, igual y mayor que el monto a cobrar, y con la entrega pagada. Son funciones puras: no tocan la base.
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («Cálculos» y las reglas de COM-EVL-DSC y COM-RSV-QJA), MD-114, MD-115, D-69 puntos 2 y 9.

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from comercial.servicios import indemnizaciones as ind

D = Decimal


class MontoDeDiscrepanciaTests(SimpleTestCase):
    def test_regla_monto_de_la_indemnizacion_ejemplo_de_la_regla(self):
        """COM-EVL-DSC, «Monto de la indemnización»: mínimo 80, 70 entregadas y $50 por planta = 10 × $50 = $500,00."""
        self.assertEqual(ind.monto_de_linea(80, 70, D("50.00")), D("500.00"))

    def test_regla_monto_de_la_indemnizacion_tabla(self):
        """(mínima, entregada, por planta) → monto; nunca negativo y redondeado a centavos con ROUND_HALF_UP."""
        for minima, entregada, por_planta, esperado in [
            (80, 0, "5.00", "400.00"),
            (80, 79, "0.00", "0.00"),
            (80, 79, "9999999.99", "9999999.99"),
            (10, 7, "0.335", "1.01"),  # 3 × 0,335 = 1,005 → 1,01
            (10, 7, "0.333", "1.00"),  # 0,999 → 1,00
            (8, 10, "5.00", "0.00"),  # por encima del mínimo: nunca negativo
        ]:
            with self.subTest(minima=minima, entregada=entregada, por_planta=por_planta):
                self.assertEqual(ind.monto_de_linea(minima, entregada, D(por_planta)), D(esperado))

    def test_regla_el_total_es_la_suma_de_los_montos_de_linea(self):
        """El total de una discrepancia es la suma de sus líneas: (80, 70, $50) + (50, 40, $20) = $500 + $200."""
        montos, total = ind.montos_de_discrepancia([(80, 70, D("50")), (50, 40, D("20"))])
        self.assertEqual((montos, total), ([D("500.00"), D("200.00")], D("700.00")))

    def test_regla_sin_lineas_el_total_es_cero(self):
        """Una lista vacía da total 0,00 (el servicio no la produce: una discrepancia tiene al menos una línea)."""
        self.assertEqual(ind.montos_de_discrepancia([]), ([], D("0.00")))


class RetrasoTests(SimpleTestCase):
    def test_regla_retraso_dias_de_retraso(self):
        """COM-RSV-QJA, «Retraso»: período 10/11, 2 días de tolerancia, entrega 15/11 = 3 días; sin retraso o con retraso negativo, 0."""
        for real, periodo, plazo, esperado in [
            (date(2026, 11, 15), date(2026, 11, 10), 2, 3),
            (date(2026, 11, 12), date(2026, 11, 10), 2, 0),  # justo en el límite
            (date(2026, 11, 13), date(2026, 11, 10), 2, 1),
            (date(2026, 11, 9), date(2026, 11, 10), 0, 0),  # antes del período
            (date(2026, 11, 10), date(2026, 11, 10), 0, 0),
        ]:
            with self.subTest(real=real, plazo=plazo):
                self.assertEqual(ind.dias_de_retraso(real, periodo, plazo), esperado)

    def test_regla_retraso_ejemplo_de_la_regla(self):
        """3 días × $1.000 + 3 días × $500 = $4.500,00 (lechuga y rúcula)."""
        self.assertEqual(ind.monto_por_retraso([(3, D("1000.00")), (3, D("500.00"))]), D("4500.00"))

    def test_regla_retraso_solo_suma_los_detalles_con_dias_mayores_que_cero(self):
        """Un detalle sin días de retraso no suma, aunque tenga indemnización por día."""
        self.assertEqual(ind.monto_por_retraso([(0, D("1000.00")), (2, D("10.50"))]), D("21.00"))
        self.assertEqual(ind.monto_por_retraso([(0, D("1000.00"))]), D("0.00"))
        self.assertEqual(ind.monto_por_retraso([]), D("0.00"))


class TopeManualTests(SimpleTestCase):
    def test_regla_tope_del_monto_manual_ejemplo_de_la_regla(self):
        """70 plantas × $1.200 = $84.000,00."""
        self.assertEqual(ind.tope_manual([D("84000.00")]), D("84000.00"))

    def test_regla_tope_del_monto_manual_suma_los_detalles_de_la_queja(self):
        """El tope es la suma de `monto_pagar` de los detalles de la queja (MD-114), no el total de la entrega."""
        self.assertEqual(ind.tope_manual([D("100.50"), D("200.25")]), D("300.75"))

    def test_regla_tope_del_monto_manual_valores_validos(self):
        """Vacío es 0; con coma o con punto; con 0, 1 o 2 decimales; el tope exacto vale."""
        tope = D("84000.00")
        for texto, esperado in [("", "0.00"), ("   ", "0.00"), (None, "0.00"), ("0", "0.00"), ("1500", "1500.00"), ("1500,5", "1500.50"), ("1500.55", "1500.55"), ("84000", "84000.00"), (" 84000,00 ", "84000.00")]:
            with self.subTest(texto=texto):
                self.assertEqual(ind.monto_manual(texto, tope), D(esperado))

    def test_regla_tope_del_monto_manual_un_centavo_mas_se_rechaza(self):
        """4a.3a: el tope más un centavo supera el tope."""
        with self.assertRaisesMessage(ValueError, "supera el tope"):
            ind.monto_manual("84000,01", D("84000.00"))

    def test_regla_tope_del_monto_manual_invalidos(self):
        """4a.3a: negativo, tres decimales o algo que no es un número se rechazan, cada uno con su mensaje."""
        tope = D("84000.00")
        for texto, mensaje in [("-1", "negativo"), ("-0,01", "negativo"), ("10,123", "dos decimales"), ("10.999", "dos decimales"), ("abc", "número"), ("1,2,3", "número"), ("1e3", "número")]:
            with self.subTest(texto=texto):
                with self.assertRaisesMessage(ValueError, mensaje):
                    ind.monto_manual(texto, tope)


class AplicacionTests(SimpleTestCase):
    def test_regla_aplicacion_con_monto_cero_no_hay_nada_que_aplicar(self):
        """Monto 0: (0, 0), con la entrega pagada o sin pagar."""
        self.assertEqual(ind.aplicacion(D("0"), D("1000"), False), (D("0.00"), D("0.00")))
        self.assertEqual(ind.aplicacion(D("0"), D("1000"), True), (D("0.00"), D("0.00")))

    def test_regla_aplicacion_menor_que_el_monto_a_cobrar_se_descuenta_todo(self):
        """Monto menor que el monto a cobrar: todo se descuenta, nada se reintegra."""
        self.assertEqual(ind.aplicacion(D("500"), D("1000"), False), (D("500.00"), D("0.00")))

    def test_regla_aplicacion_igual_al_monto_a_cobrar_se_descuenta_todo(self):
        """Monto igual al monto a cobrar: se descuenta todo y el monto a cobrar queda en 0."""
        self.assertEqual(ind.aplicacion(D("1000"), D("1000"), False), (D("1000.00"), D("0.00")))

    def test_regla_aplicacion_mayor_que_el_monto_a_cobrar_el_resto_se_reintegra(self):
        """MD-115 (6d): se descuenta el monto a cobrar completo y el resto se reintegra (el monto a cobrar nunca queda negativo)."""
        self.assertEqual(ind.aplicacion(D("1200"), D("1000"), False), (D("1000.00"), D("200.00")))
        self.assertEqual(ind.aplicacion(D("1000.01"), D("1000"), False), (D("1000.00"), D("0.01")))

    def test_regla_aplicacion_con_monto_a_cobrar_cero_todo_se_reintegra(self):
        """Una entrega sin nada por cobrar (ya descontada por otra solicitud): todo se reintegra."""
        self.assertEqual(ind.aplicacion(D("300"), D("0"), False), (D("0.00"), D("300.00")))

    def test_regla_aplicacion_entrega_pagada_se_reintegra_todo(self):
        """6a: con la entrega pagada, `(0, monto)`."""
        self.assertEqual(ind.aplicacion(D("300"), D("0"), True), (D("0.00"), D("300.00")))
        self.assertEqual(ind.aplicacion(D("300"), D("5000"), True), (D("0.00"), D("300.00")))

    def test_regla_aplicacion_siempre_suma_el_monto(self):
        """descontado + reintegrado = monto, para cualquier combinación de la tabla."""
        for monto in ("0", "0.01", "99.99", "1000", "1000.01", "123456.78"):
            for a_cobrar in ("0", "0.01", "500", "1000", "200000"):
                for pagada in (False, True):
                    with self.subTest(monto=monto, a_cobrar=a_cobrar, pagada=pagada):
                        descontado, reintegrado = ind.aplicacion(D(monto), D(a_cobrar), pagada)
                        self.assertEqual(descontado + reintegrado, D(monto).quantize(D("0.01")))
                        self.assertGreaterEqual(descontado, 0)
                        self.assertGreaterEqual(reintegrado, 0)
                        self.assertLessEqual(descontado, D(a_cobrar).quantize(D("0.01")) if not pagada else D("0"))
