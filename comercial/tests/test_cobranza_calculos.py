# Pruebas de los cálculos de COM-08a (paso 2): funciones puras de `comercial/servicios/cobranza.py`, de tabla: `dias_de_atraso`, `indemnizacion_por_atraso` y `total_del_cobro`.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Cálculos»; regla «Indemnización por atraso en el pago»; «Vencimiento del pago»), MD-124, D-94 punto 12. Dinero siempre `Decimal` (CLAUDE.md).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `dias_de_atraso(fecha_vencimiento, fecha_pago) -> int`; `indemnizacion_por_atraso(dias, por_dia) -> Decimal`;
# `total_del_cobro(lineas) -> Decimal`, donde cada línea tiene `monto_a_cobrar` e `indemnizacion` (la `EntregaCobrable` del paso 5 los tiene; la cobranza.md no dice qué recibe: es una decisión de código).

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from comercial.servicios import cobranza

D = Decimal


class DiasDeAtrasoTests(SimpleTestCase):
    def test_regla_el_dia_del_vencimiento_todavia_se_paga_sin_atraso(self):
        """Regla «Vencimiento del pago»: el día del vencimiento da 0 días de atraso; antes del vencimiento, también 0 (nunca negativo)."""
        tabla = [
            (date(2026, 11, 11), date(2026, 11, 11), 0),  # el día del vencimiento
            (date(2026, 11, 11), date(2026, 11, 10), 0),  # un día antes
            (date(2026, 11, 11), date(2026, 10, 1), 0),  # mucho antes
            (date(2026, 11, 11), date(2026, 11, 12), 1),  # el día siguiente: en mora
            (date(2026, 11, 11), date(2026, 11, 14), 3),  # el ejemplo de la regla
            (date(2026, 12, 25), date(2027, 1, 5), 11),  # cruza el fin de año
            (date(2028, 2, 27), date(2028, 3, 1), 3),  # año bisiesto
        ]
        for vencimiento, pago, esperado in tabla:
            with self.subTest(vencimiento=vencimiento, pago=pago):
                resultado = cobranza.dias_de_atraso(vencimiento, pago)
                self.assertEqual(resultado, esperado)
                self.assertIsInstance(resultado, int)


class IndemnizacionPorAtrasoTests(SimpleTestCase):
    def test_regla_dias_por_lo_pactado_por_dia(self):
        """Regla «Indemnización por atraso en el pago»: días × indemnización por día; el ejemplo de la regla (vence el 11/11, se paga el 14/11, $ 300 por día) da 3 días y $ 900,00."""
        tabla = [
            (3, D("300.00"), D("900.00")),  # el ejemplo de la regla
            (1, D("300.00"), D("300.00")),  # un día
            (0, D("300.00"), D("0.00")),  # sin atraso: 0
            (5, D("0.00"), D("0.00")),  # una cláusula sin indemnización
            (4, D("0.01"), D("0.04")),  # el centavo
            (7, D("33.33"), D("233.31")),  # montos con centavos
            (365, D("9999999.99"), D("3649999996.35")),  # el máximo de la cláusula por un año
        ]
        for dias, por_dia, esperado in tabla:
            with self.subTest(dias=dias, por_dia=por_dia):
                self.assertEqual(cobranza.indemnizacion_por_atraso(dias, por_dia), esperado)

    def test_regla_redondea_a_dos_decimales_half_up(self):
        """`ROUND_HALF_UP` (no el redondeo bancario): 3 × 0,835 = 2,505 → 2,51; 1 × 0,125 → 0,13; 2 × 0,0125 = 0,025 → 0,03."""
        tabla = [(3, D("0.835"), D("2.51")), (1, D("0.125"), D("0.13")), (2, D("0.0125"), D("0.03")), (1, D("0.124"), D("0.12"))]
        for dias, por_dia, esperado in tabla:
            with self.subTest(dias=dias, por_dia=por_dia):
                self.assertEqual(cobranza.indemnizacion_por_atraso(dias, por_dia), esperado)

    def test_regla_siempre_devuelve_un_decimal_de_dos_decimales(self):
        """Nunca `float` (CLAUDE.md): el resultado es un `Decimal` con exactamente dos decimales, también con 0 días."""
        for dias in (0, 1, 3):
            resultado = cobranza.indemnizacion_por_atraso(dias, D("300.00"))
            self.assertIsInstance(resultado, Decimal)
            self.assertEqual(resultado.as_tuple().exponent, -2)


class TotalDelCobroTests(SimpleTestCase):
    def linea(self, monto, indemnizacion):
        return SimpleNamespace(monto_a_cobrar=D(monto), indemnizacion=D(indemnizacion))

    def test_regla_el_total_es_la_suma_de_lo_a_cobrar_y_de_la_indemnizacion(self):
        """Postcondición a de COM-REG-CBR: monto pagado = Σ (monto a cobrar + indemnización por atraso)."""
        tabla = [
            ([("1000.00", "0.00")], D("1000.00")),
            ([("1000.00", "900.00")], D("1900.00")),
            ([("46000.00", "0.00"), ("1000.00", "1200.00")], D("48200.00")),
            ([("0.10", "0.20"), ("0.20", "0.10")], D("0.60")),  # sin errores de coma flotante
        ]
        for lineas, esperado in tabla:
            with self.subTest(lineas=lineas):
                resultado = cobranza.total_del_cobro([self.linea(*l) for l in lineas])
                self.assertEqual(resultado, esperado)
                self.assertIsInstance(resultado, Decimal)

    def test_regla_sin_lineas_el_total_es_cero(self):
        """Una lista vacía suma `Decimal("0.00")` (no `0` ni `float`)."""
        resultado = cobranza.total_del_cobro([])
        self.assertEqual(resultado, D("0.00"))
        self.assertIsInstance(resultado, Decimal)

    def test_regla_acepta_cualquier_iterable(self):
        """Una lista, una tupla o un generador."""
        lineas = [self.linea("10.00", "1.00"), self.linea("20.00", "2.00")]
        self.assertEqual(cobranza.total_del_cobro(tuple(lineas)), D("33.00"))
        self.assertEqual(cobranza.total_del_cobro(l for l in lineas), D("33.00"))
