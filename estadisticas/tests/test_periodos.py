# Pruebas del período de las estadísticas (EST-01, paso 1): por defecto, atajos, período anterior, validaciones, años bisiestos y la
# comparación contra el anterior. Fuente: D-93 punto 2 y EST-CNS-PRD, regla 2 (docs/casos_de_uso/estadisticas/estadisticas.md).

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from contabilidad.tests.fabricas import ejercicio_abierto
from estadisticas import periodos
from estadisticas.periodos import Comparacion, Periodo

HOY = date(2026, 11, 26)


def mensaje_de(llamada):
    """El mensaje del `ValidationError` que lanza `llamada` (la prueba falla si no lanza ninguno)."""
    try:
        llamada()
    except ValidationError as error:
        return error.messages[0]
    raise AssertionError("no lanzó ValidationError")


class PeriodosTests(SimpleTestCase):
    """Período por defecto, atajos, anterior y validaciones (no tocan la base)."""

    # ---- Por defecto y atajos ----

    def test_d93_por_defecto_es_del_primero_del_mes_a_hoy(self):
        """D-93 punto 2: por defecto, del 1 del mes actual a hoy."""
        self.assertEqual(periodos.periodo_por_defecto(HOY), Periodo(date(2026, 11, 1), HOY))

    def test_d93_por_defecto_el_dia_uno_es_un_periodo_de_un_dia(self):
        """D-93 punto 2: el día 1 del mes el período por defecto es ese solo día."""
        self.assertEqual(periodos.periodo_por_defecto(date(2026, 11, 1)), Periodo(date(2026, 11, 1), date(2026, 11, 1)))

    def test_d93_atajo_mes_es_el_periodo_por_defecto(self):
        """D-93 punto 2: «Este mes» es del 1 del mes a hoy."""
        self.assertEqual(periodos.atajo("mes", HOY), Periodo(date(2026, 11, 1), HOY))

    def test_d93_atajo_mes_anterior_es_el_mes_completo(self):
        """D-93 punto 2: «Mes anterior» va del 1 al último día del mes anterior."""
        self.assertEqual(periodos.atajo("mes_anterior", HOY), Periodo(date(2026, 10, 1), date(2026, 10, 31)))

    def test_d93_atajo_mes_anterior_en_enero_es_diciembre_del_ano_anterior(self):
        """D-93 punto 2: el mes anterior de enero es diciembre del año anterior."""
        self.assertEqual(periodos.atajo("mes_anterior", date(2027, 1, 15)), Periodo(date(2026, 12, 1), date(2026, 12, 31)))

    def test_d93_atajo_mes_anterior_en_marzo_bisiesto_termina_el_29_de_febrero(self):
        """D-93 punto 2 (año bisiesto): el mes anterior de marzo de 2028 termina el 29 de febrero."""
        self.assertEqual(periodos.atajo("mes_anterior", date(2028, 3, 10)), Periodo(date(2028, 2, 1), date(2028, 2, 29)))

    def test_d93_atajo_mes_anterior_en_marzo_comun_termina_el_28_de_febrero(self):
        """D-93 punto 2 (año común): el mes anterior de marzo de 2027 termina el 28 de febrero."""
        self.assertEqual(periodos.atajo("mes_anterior", date(2027, 3, 10)), Periodo(date(2027, 2, 1), date(2027, 2, 28)))

    def test_d93_atajo_tres_meses_es_el_mismo_dia_de_tres_meses_atras(self):
        """D-93 punto 2: «Últimos 3 meses» desde el mismo día de tres meses atrás hasta hoy."""
        self.assertEqual(periodos.atajo("tres_meses", HOY), Periodo(date(2026, 8, 26), HOY))

    def test_d93_atajo_tres_meses_cruza_el_cambio_de_ano(self):
        """D-93 punto 2: tres meses antes del 15/01/2027 es el 15/10/2026."""
        self.assertEqual(periodos.atajo("tres_meses", date(2027, 1, 15)), Periodo(date(2026, 10, 15), date(2027, 1, 15)))

    def test_d93_atajo_tres_meses_sin_ese_dia_toma_el_ultimo_del_mes_comun(self):
        """D-93 punto 2: el 31/05/2026 no tiene «31 de febrero»: desde el último día de febrero (28/02/2026)."""
        self.assertEqual(periodos.atajo("tres_meses", date(2026, 5, 31)), Periodo(date(2026, 2, 28), date(2026, 5, 31)))

    def test_d93_atajo_tres_meses_sin_ese_dia_toma_el_ultimo_del_mes_bisiesto(self):
        """D-93 punto 2 (año bisiesto): el 31/05/2028 → desde el 29/02/2028."""
        self.assertEqual(periodos.atajo("tres_meses", date(2028, 5, 31)), Periodo(date(2028, 2, 29), date(2028, 5, 31)))

    def test_d93_atajo_personalizado_ofrece_el_periodo_por_defecto(self):
        """D-61 punto 2: al elegir «Personalizado» la pantalla muestra las fechas del período por defecto para que se cambien."""
        self.assertEqual(periodos.atajo("personalizado", HOY), Periodo(date(2026, 11, 1), HOY))

    def test_d93_atajo_desconocido_se_rechaza(self):
        """D-93 punto 2: solo hay cinco atajos; otro código es un error de validación."""
        with self.assertRaises(ValidationError):
            periodos.atajo("ayer", HOY)

    # ---- Período anterior ----

    def test_d93_anterior_son_los_mismos_dias_inmediatamente_antes(self):
        """D-93 punto 2: período anterior = `desde − n … desde − 1`, con n = días del período (01/11 al 26/11 son 26 días)."""
        self.assertEqual(periodos.anterior(Periodo(date(2026, 11, 1), HOY)), Periodo(date(2026, 10, 6), date(2026, 10, 31)))

    def test_d93_anterior_de_un_dia_es_el_dia_anterior(self):
        """D-93 punto 2: n = 1 → el día inmediatamente anterior."""
        dia = date(2026, 11, 1)
        self.assertEqual(periodos.anterior(Periodo(dia, dia)), Periodo(date(2026, 10, 31), date(2026, 10, 31)))

    def test_d93_anterior_tiene_la_misma_duracion(self):
        """D-93 punto 2: el período anterior dura lo mismo (31 días de octubre → 31 días antes)."""
        actual = Periodo(date(2026, 10, 1), date(2026, 10, 31))
        previo = periodos.anterior(actual)
        self.assertEqual(previo.dias, actual.dias)
        self.assertEqual(previo, Periodo(date(2026, 8, 31), date(2026, 9, 30)))

    def test_d93_anterior_cruza_un_febrero_bisiesto(self):
        """D-93 punto 2 (año bisiesto): 01/03/2028 al 10/03/2028 (10 días) → 20/02/2028 al 29/02/2028."""
        self.assertEqual(
            periodos.anterior(Periodo(date(2028, 3, 1), date(2028, 3, 10))), Periodo(date(2028, 2, 20), date(2028, 2, 29))
        )

    def test_d93_dias_cuenta_los_dos_extremos(self):
        """D-93 punto 2: un período de 01/11 a 26/11 tiene 26 días."""
        self.assertEqual(Periodo(date(2026, 11, 1), HOY).dias, 26)

    # ---- Validaciones ----

    def test_d93_validar_acepta_un_rango_valido(self):
        """D-93 punto 2: desde ≤ hasta ≤ hoy y hasta 366 días es válido."""
        self.assertEqual(periodos.validar(date(2026, 10, 1), date(2026, 10, 31), HOY), Periodo(date(2026, 10, 1), date(2026, 10, 31)))

    def test_d93_validar_acepta_hasta_igual_a_hoy(self):
        """D-93 punto 2: «hasta ≤ hoy»: hoy mismo vale."""
        self.assertEqual(periodos.validar(HOY, HOY, HOY), Periodo(HOY, HOY))

    def test_d93_validar_rechaza_desde_posterior_a_hasta(self):
        """EST-CNS-PRD / D-93 punto 2: mensaje «La fecha “desde” no puede ser posterior a “hasta”.»"""
        self.assertEqual(
            mensaje_de(lambda: periodos.validar(date(2026, 11, 10), date(2026, 11, 5), HOY)),
            "La fecha “desde” no puede ser posterior a “hasta”.",
        )

    def test_d93_validar_rechaza_un_periodo_que_termina_despues_de_hoy(self):
        """D-93 punto 2: mensaje «El período no puede terminar después de hoy.»"""
        self.assertEqual(
            mensaje_de(lambda: periodos.validar(date(2026, 11, 1), date(2026, 11, 27), HOY)),
            "El período no puede terminar después de hoy.",
        )

    def test_d93_validar_acepta_366_dias(self):
        """D-93 punto 2: «como mucho 366 días»: del 27/11/2025 al 26/11/2026 son 365; del 26/11/2025 son 366 y valen."""
        self.assertEqual(periodos.validar(date(2025, 11, 26), HOY, HOY).dias, 366)

    def test_d93_validar_rechaza_367_dias(self):
        """D-93 punto 2: mensaje «El período no puede ser mayor que un año.» desde el día 367."""
        self.assertEqual(
            mensaje_de(lambda: periodos.validar(date(2025, 11, 25), HOY, HOY)), "El período no puede ser mayor que un año."
        )

    def test_d93_validar_acepta_un_ano_bisiesto_de_366_dias(self):
        """D-93 punto 2 (año bisiesto): del 01/01/2028 al 31/12/2028 son 366 días y valen."""
        self.assertEqual(periodos.validar(date(2028, 1, 1), date(2028, 12, 31), date(2029, 1, 5)).dias, 366)

    def test_d61_validar_pide_las_dos_fechas(self):
        """D-61 punto 2 (texto que falta): sin una de las fechas, «Indicá las dos fechas.»"""
        self.assertEqual(mensaje_de(lambda: periodos.validar(None, HOY, HOY)), "Indicá las dos fechas.")
        self.assertEqual(mensaje_de(lambda: periodos.validar(HOY, None, HOY)), "Indicá las dos fechas.")

    # ---- Comparación con el período anterior ----

    def test_d93_comparar_da_diferencia_absoluta_y_porcentual(self):
        """D-93 punto 2: diferencia absoluta y porcentual contra el anterior (120 contra 100: +20, +20,0 %)."""
        self.assertEqual(
            periodos.comparar(Decimal("120"), Decimal("100")),
            Comparacion(Decimal("120"), Decimal("100"), Decimal("20"), Decimal("20.0")),
        )

    def test_d93_comparar_una_baja_es_negativa(self):
        """D-93 punto 2: 75 contra 100 es −25 y −25,0 %."""
        resultado = periodos.comparar(75, 100)
        self.assertEqual((resultado.diferencia, resultado.porcentaje), (Decimal("-25"), Decimal("-25.0")))

    def test_d93_comparar_con_anterior_cero_no_da_porcentaje(self):
        """D-93 punto 2: «—» si el anterior es 0: sin porcentaje, pero sí la diferencia."""
        resultado = periodos.comparar(Decimal("40"), Decimal("0"))
        self.assertEqual((resultado.diferencia, resultado.porcentaje), (Decimal("40"), None))

    def test_d93_comparar_sin_anterior_no_da_diferencia_ni_porcentaje(self):
        """D-93 punto 2: sin valor anterior (`None`, p. ej. un costo sin cosechas) no hay con qué comparar."""
        resultado = periodos.comparar(Decimal("40"), None)
        self.assertEqual((resultado.valor, resultado.anterior, resultado.diferencia, resultado.porcentaje), (Decimal("40"), None, None, None))

    def test_d93_comparar_sin_valor_actual_no_da_diferencia_ni_porcentaje(self):
        """D-93 punto 2: sin valor actual tampoco se compara."""
        resultado = periodos.comparar(None, Decimal("40"))
        self.assertEqual((resultado.diferencia, resultado.porcentaje), (None, None))

    def test_d93_comparar_con_decimales_redondea_el_porcentaje_a_un_decimal(self):
        """D-93 punto 2: 10,00 contra 3,00 → +7,00 y +233,3 % (ROUND_HALF_UP, un decimal); sin `float`."""
        resultado = periodos.comparar(Decimal("10.00"), Decimal("3.00"))
        self.assertEqual((resultado.diferencia, resultado.porcentaje), (Decimal("7.00"), Decimal("233.3")))
        self.assertIsInstance(resultado.porcentaje, Decimal)

    def test_d93_comparar_redondea_la_mitad_hacia_arriba(self):
        """D-93 punto 2: 1,05 contra 1,00 es +5,0 %; 1,0025 contra 1,0000 es +0,25 % → 0,3 (mitad hacia arriba)."""
        self.assertEqual(periodos.comparar(Decimal("1.0025"), Decimal("1.0000")).porcentaje, Decimal("0.3"))

    def test_d93_comparar_acepta_enteros(self):
        """D-93 punto 2: las cantidades de plantas son enteros; el resultado sigue siendo `Decimal`."""
        resultado = periodos.comparar(150, 100)
        self.assertEqual((resultado.valor, resultado.diferencia, resultado.porcentaje), (Decimal("150"), Decimal("50"), Decimal("50.0")))


class PeriodosConEjercicioTests(TestCase):
    """El atajo «Ejercicio actual» lee el ejercicio abierto (D-93 punto 2)."""

    def test_d93_atajo_ejercicio_va_del_inicio_del_ejercicio_abierto_a_hoy(self):
        """D-93 punto 2: «Ejercicio actual» = desde el inicio del ejercicio abierto hasta hoy."""
        ejercicio_abierto(inicio=date(2026, 3, 1))
        self.assertEqual(periodos.atajo("ejercicio", HOY), Periodo(date(2026, 3, 1), HOY))

    def test_d93_atajo_ejercicio_sin_ejercicio_abierto_se_rechaza(self):
        """D-61 punto 2 (estado que falta): sin ejercicio abierto, «No hay un ejercicio abierto.»"""
        self.assertEqual(mensaje_de(lambda: periodos.atajo("ejercicio", HOY)), "No hay un ejercicio abierto.")

    def test_d93_atajo_ejercicio_mayor_a_un_ano_no_se_corta(self):
        """D-93 punto 2: el atajo devuelve el rango tal cual; la validación de un año la hace `validar`, no el atajo."""
        ejercicio_abierto(inicio=date(2025, 1, 1), cierre=date(2025, 12, 31))
        self.assertEqual(periodos.atajo("ejercicio", HOY).desde, date(2025, 1, 1))
