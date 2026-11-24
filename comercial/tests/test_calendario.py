# Pruebas de `comercial/servicios/calendario.py` (COM-03a, paso 2): las funciones puras de fechas, calendario y precios de un detalle de
# suministro (docs/casos_de_uso/comercial/suministro.md, «Fechas y precios» y las reglas «Fecha de fin», «Calendario de entregas» y
# «Precio de cada entrega»). De tabla: los ejemplos del caso de uso. Las puras usan dobles simples (sin base de datos).

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from comercial.servicios import calendario
from comercial.tests.fabricas import detalle_suministro, escenario_comercial, suministro
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.servicios import configuracion


def doble(
    primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2027, 5, 24), fin_detalle=None, mecanismo="fijo", precio="1000.00",
    porcentaje=None, meses=None, base=date(2026, 11, 22),
):
    """Un detalle de suministro de mentira, con lo que lee `calendario`: sin base de datos."""
    return SimpleNamespace(
        fecha_primer_entrega=primera,
        periodo_entrega_dias=periodo,
        fecha_fin_detalle=fin_detalle,
        suministro=SimpleNamespace(fecha_fin=fin_contrato),
        mecanismo_precio=mecanismo,
        precio_unitario_suministro=Decimal(precio),
        porcentaje_ajuste=Decimal(porcentaje) if porcentaje is not None else None,
        meses_ajuste=meses,
        fecha_base_ajuste=base,
    )


class SumarMesesTests(SimpleTestCase):
    """Regla «Fecha de fin»: el mismo día del mes, N meses después; si no existe, el último día de ese mes."""

    def test_regla_fecha_de_fin_31_de_enero_mas_un_mes_en_anio_comun(self):
        """31/01/2027 + 1 mes = 28/02/2027."""
        self.assertEqual(calendario.sumar_meses(date(2027, 1, 31), 1), date(2027, 2, 28))

    def test_regla_fecha_de_fin_31_de_enero_mas_un_mes_en_anio_bisiesto(self):
        """31/01/2028 + 1 mes = 29/02/2028."""
        self.assertEqual(calendario.sumar_meses(date(2028, 1, 31), 1), date(2028, 2, 29))

    def test_regla_fecha_de_fin_30_de_noviembre_mas_tres_meses(self):
        """30/11/2026 + 3 meses = 28/02/2027 (febrero no tiene día 30)."""
        self.assertEqual(calendario.sumar_meses(date(2026, 11, 30), 3), date(2027, 2, 28))

    def test_regla_fecha_de_fin_31_de_diciembre_mas_dos_meses(self):
        """31/12/2026 + 2 meses = 28/02/2027."""
        self.assertEqual(calendario.sumar_meses(date(2026, 12, 31), 2), date(2027, 2, 28))

    def test_regla_fecha_de_fin_no_es_fecha_mas_30_por_meses(self):
        """«Lo que difiere del prototipo», fila 2: no es `fecha + 30 × n`. 22/11/2026 + 6 meses = 22/05/2027 (y no el 21/05)."""
        self.assertEqual(calendario.sumar_meses(date(2026, 11, 22), 6), date(2027, 5, 22))
        self.assertNotEqual(calendario.sumar_meses(date(2026, 11, 22), 6), date(2026, 11, 22) + timedelta(days=180))

    def test_regla_fecha_de_fin_cruza_el_anio_y_admite_120_meses(self):
        """Un mes de diciembre más uno cruza el año; 120 meses son 10 años exactos."""
        self.assertEqual(calendario.sumar_meses(date(2026, 12, 15), 1), date(2027, 1, 15))
        self.assertEqual(calendario.sumar_meses(date(2026, 11, 22), 120), date(2036, 11, 22))

    def test_regla_fecha_de_fin_con_cero_meses_es_la_misma_fecha(self):
        """`sumar_meses(f, 0) == f` (lo usa `meses_transcurridos`)."""
        self.assertEqual(calendario.sumar_meses(date(2026, 2, 28), 0), date(2026, 2, 28))


class MesesTranscurridosTests(SimpleTestCase):
    """Regla «Precio de cada entrega»: meses calendario completos desde la fecha base."""

    def test_regla_precio_con_fecha_22_10_el_21_12_cuenta_un_mes(self):
        """Ejemplo del caso de uso: realización 22/10, el 21/12 cuenta 1 mes."""
        self.assertEqual(calendario.meses_transcurridos(date(2026, 10, 22), date(2026, 12, 21)), 1)

    def test_regla_precio_con_fecha_22_10_el_22_12_cuenta_dos_meses(self):
        """Ejemplo del caso de uso: el 22/12 cuenta 2 meses."""
        self.assertEqual(calendario.meses_transcurridos(date(2026, 10, 22), date(2026, 12, 22)), 2)

    def test_regla_precio_el_mismo_dia_cuenta_cero_y_antes_de_la_base_tambien(self):
        """El día de la base son 0 meses; una fecha anterior no da negativos (0)."""
        self.assertEqual(calendario.meses_transcurridos(date(2026, 10, 22), date(2026, 10, 22)), 0)
        self.assertEqual(calendario.meses_transcurridos(date(2026, 10, 22), date(2026, 10, 1)), 0)

    def test_regla_precio_desde_el_31_de_enero_el_28_de_febrero_ya_cuenta_un_mes(self):
        """Es el mayor `n` con `sumar_meses(desde, n) <= hasta`: 31/01 + 1 mes = 28/02."""
        self.assertEqual(calendario.meses_transcurridos(date(2027, 1, 31), date(2027, 2, 28)), 1)
        self.assertEqual(calendario.meses_transcurridos(date(2027, 1, 31), date(2027, 2, 27)), 0)


class PrecioEnTests(SimpleTestCase):
    """Regla 7 de 8.11 y «Precio de cada entrega»: `Decimal`, `ROUND_HALF_UP`, siempre desde el precio inicial."""

    def test_regla_precio_fijo_es_siempre_el_inicial(self):
        """Mecanismo fijo: el precio inicial en cualquier fecha."""
        d = doble(precio="1500.00")
        for fecha in (date(2026, 11, 22), date(2027, 3, 1)):
            self.assertEqual(calendario.precio_en(d, fecha), Decimal("1500.00"))

    def test_regla_precio_ejemplo_1000_al_3_por_ciento_cada_2_meses(self):
        """Ejemplo del caso de uso: $1.000, 3 %, cada 2 meses vale 1.000 los meses 0 y 1, 1.030 los 2 y 3 y 1.060,90 los 4 y 5."""
        d = doble(mecanismo="ajuste_periodico", porcentaje="3.00", meses=2, base=date(2026, 1, 10))
        esperado = {0: "1000.00", 1: "1000.00", 2: "1030.00", 3: "1030.00", 4: "1060.90", 5: "1060.90"}
        for mes, precio in esperado.items():
            with self.subTest(mes=mes):
                self.assertEqual(calendario.precio_en(d, calendario.sumar_meses(date(2026, 1, 10), mes)), Decimal(precio))

    def test_regla_precio_el_redondeo_no_se_acumula(self):
        """«Los redondeos no se acumulan»: $0,99 al 1,5 % cada mes, a los 4 meses, se calcula desde el inicial (0,99 × 1,015⁴ = 1,0507… →
        1,05); redondeando paso a paso daría 1,06."""
        d = doble(mecanismo="ajuste_periodico", porcentaje="1.50", meses=1, precio="0.99", base=date(2026, 1, 1))
        self.assertEqual(calendario.precio_en(d, date(2026, 5, 1)), Decimal("1.05"))

    def test_regla_precio_redondea_la_mitad_hacia_arriba(self):
        """`ROUND_HALF_UP` a 2 decimales: 10,00 × 1,005 = 10,05 exacto; 0,50 × 1,01 = 0,505 → 0,51 (con half-even daría 0,50)."""
        d = doble(mecanismo="ajuste_periodico", porcentaje="1.00", meses=1, precio="0.50", base=date(2026, 1, 1))
        self.assertEqual(calendario.precio_en(d, date(2026, 2, 1)), Decimal("0.51"))

    def test_regla_precio_el_resultado_es_decimal_con_dos_decimales(self):
        """El resultado es un `Decimal` cuantizado a centavos (nunca `float`)."""
        d = doble(mecanismo="ajuste_periodico", porcentaje="3.00", meses=2, base=date(2026, 1, 10))
        precio = calendario.precio_en(d, date(2026, 3, 10))
        self.assertIsInstance(precio, Decimal)
        self.assertEqual(precio.as_tuple().exponent, -2)

    def test_regla_precio_antes_de_la_fecha_base_es_el_inicial(self):
        """Una fecha anterior a la base cuenta 0 meses: el precio inicial."""
        d = doble(mecanismo="ajuste_periodico", porcentaje="3.00", meses=2, base=date(2026, 6, 1))
        self.assertEqual(calendario.precio_en(d, date(2026, 5, 1)), Decimal("1000.00"))


class CalendarioTests(SimpleTestCase):
    """Regla «Calendario de entregas»: `fecha_primer_entrega + k × periodo` mientras no supere el fin."""

    def test_regla_calendario_arranca_en_la_primera_entrega_y_avanza_por_periodo(self):
        """Las fechas son la primera más k veces el período."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2026, 12, 15))
        self.assertEqual(
            calendario.calendario(d), [date(2026, 11, 24), date(2026, 12, 1), date(2026, 12, 8), date(2026, 12, 15)]
        )

    def test_regla_calendario_incluye_la_fecha_igual_al_fin_del_contrato(self):
        """«Mientras no superen la fecha de fin»: la que coincide con el fin entra; la siguiente no."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2026, 12, 8))
        self.assertEqual(calendario.calendario(d)[-1], date(2026, 12, 8))
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2026, 12, 7))
        self.assertEqual(calendario.calendario(d)[-1], date(2026, 12, 1))

    def test_regla_calendario_con_fecha_de_fin_del_detalle_corta_antes_que_el_contrato(self):
        """MD-131: con `fecha_fin_detalle` (la del último período que se entrega), el calendario no la supera."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2027, 5, 24), fin_detalle=date(2026, 12, 8))
        self.assertEqual(calendario.calendario(d), [date(2026, 11, 24), date(2026, 12, 1), date(2026, 12, 8)])

    def test_regla_calendario_usa_la_menor_de_las_dos_fechas_de_fin(self):
        """Si la fecha de fin del detalle es posterior a la del contrato, manda la del contrato."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2026, 12, 1), fin_detalle=date(2027, 1, 1))
        self.assertEqual(calendario.calendario(d), [date(2026, 11, 24), date(2026, 12, 1)])

    def test_regla_calendario_con_primera_entrega_posterior_al_fin_es_vacio(self):
        """Un detalle sin períodos (la primera entrega ya supera el fin) tiene un calendario vacío."""
        d = doble(primera=date(2027, 1, 1), fin_contrato=date(2026, 12, 1))
        self.assertEqual(calendario.calendario(d), [])

    def test_regla_calendario_de_un_tramo_no_genera_los_anteriores_y_es_igual_al_completo_recortado(self):
        """Con `desde` y `hasta`, solo ese tramo (ambos extremos incluidos); coincide con el calendario completo recortado."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2027, 5, 24))
        completo = calendario.calendario(d)
        tramo = calendario.calendario(d, desde=date(2026, 12, 8), hasta=date(2027, 1, 5))
        self.assertEqual(tramo, [f for f in completo if date(2026, 12, 8) <= f <= date(2027, 1, 5)])
        self.assertEqual(tramo[0], date(2026, 12, 8))
        self.assertEqual(tramo[-1], date(2027, 1, 5))

    def test_regla_calendario_de_un_tramo_con_solo_desde_o_solo_hasta(self):
        """`desde` sin `hasta` llega hasta el fin; `hasta` sin `desde` arranca en la primera entrega."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2026, 12, 22))
        self.assertEqual(calendario.calendario(d, desde=date(2026, 12, 10)), [date(2026, 12, 15), date(2026, 12, 22)])
        self.assertEqual(calendario.calendario(d, hasta=date(2026, 12, 1)), [date(2026, 11, 24), date(2026, 12, 1)])

    def test_regla_calendario_de_un_tramo_antes_de_la_primera_entrega_es_vacio(self):
        """Un tramo que termina antes de la primera entrega no tiene fechas."""
        d = doble(primera=date(2026, 11, 24))
        self.assertEqual(calendario.calendario(d, desde=date(2026, 10, 1), hasta=date(2026, 11, 1)), [])

    def test_regla_calendario_de_un_tramo_lejano_no_recorre_todo_el_calendario(self):
        """«Sin generar los anteriores»: un período de 1 día en 120 meses tiene ~3.650 fechas; el tramo de una semana, 7."""
        d = doble(primera=date(2026, 11, 24), periodo=1, fin_contrato=date(2036, 11, 24))
        self.assertEqual(len(calendario.calendario(d, desde=date(2030, 1, 1), hasta=date(2030, 1, 7))), 7)


class TramosDePrecioTests(SimpleTestCase):
    """Paso 9 y extensión 8b: «Desde el dd/mm: $ 1.030,00» por cada cambio de precio del calendario."""

    def test_regla_tramos_con_precio_fijo_hay_uno_solo(self):
        """Mecanismo fijo: un tramo, desde la primera fecha, al precio inicial."""
        d = doble(primera=date(2026, 11, 24), periodo=7, fin_contrato=date(2027, 1, 24), precio="1500.00")
        self.assertEqual(calendario.tramos_de_precio(d), [(date(2026, 11, 24), Decimal("1500.00"))])

    def test_regla_tramos_con_ajuste_periodico_hay_uno_por_cada_precio_distinto(self):
        """Ejemplo del caso de uso: 1.000 hasta el mes 1, 1.030 desde el mes 2, 1.060,90 desde el mes 4; cada tramo arranca en la primera
        fecha del calendario con ese precio."""
        d = doble(
            primera=date(2026, 1, 10), periodo=30, fin_contrato=date(2026, 6, 30), mecanismo="ajuste_periodico", porcentaje="3.00", meses=2,
            base=date(2026, 1, 10),
        )
        tramos = calendario.tramos_de_precio(d)
        self.assertEqual([p for _, p in tramos], [Decimal("1000.00"), Decimal("1030.00"), Decimal("1060.90")])
        self.assertEqual(tramos[0][0], date(2026, 1, 10))
        self.assertEqual(tramos[1][0], date(2026, 3, 11))  # la primera fecha del calendario con 2 meses cumplidos
        self.assertEqual(tramos[2][0], date(2026, 5, 10))

    def test_regla_tramos_de_un_calendario_vacio_es_vacio(self):
        """Sin fechas no hay tramos."""
        self.assertEqual(calendario.tramos_de_precio(doble(primera=date(2027, 1, 1), fin_contrato=date(2026, 12, 1))), [])


class RigeDesdeYVentanaTests(ConDatosDeInventario, TestCase):
    """`ventana(hoy)` y `rige_desde(detalle, hoy)` (suministro.md, «COM-MOD-SUM», paso 4: la leen COM-03b y la ficha)."""

    def setUp(self):
        self.e = escenario_comercial()
        self.hoy = timezone.localdate()

    def test_regla_ventana_es_hoy_mas_los_dias_de_pre_reserva_de_la_configuracion(self):
        """Regla «Ventana de pre-reserva»: `hoy + dias_pre_reserva_suministro` (14 por defecto)."""
        dias = configuracion.obtener().dias_pre_reserva_suministro
        self.assertEqual(calendario.ventana(self.hoy), self.hoy + timedelta(days=dias))
        self.assertEqual(calendario.ventana(date(2026, 11, 22)), date(2026, 11, 22) + timedelta(days=dias))

    def test_regla_rige_desde_es_el_primer_periodo_posterior_a_la_ventana(self):
        """El primer período del calendario **posterior** a `hoy + días de pre-reserva` (uno que cae justo en el último día de la
        ventana todavía está dentro)."""
        s = suministro(self.e, duracion=12)
        d = detalle_suministro(s, self.e.variedad, periodo=7, primera_en_dias=3)
        ventana = calendario.ventana(self.hoy)
        esperado = next(f for f in calendario.calendario(d) if f > ventana)
        self.assertEqual(calendario.rige_desde(d, self.hoy), esperado)

    def test_regla_rige_desde_un_periodo_en_el_ultimo_dia_de_la_ventana_no_cuenta(self):
        """Un período que cae exactamente en `ventana(hoy)` está dentro de la ventana: rige desde el siguiente."""
        s = suministro(self.e, duracion=12)
        dias = configuracion.obtener().dias_pre_reserva_suministro
        d = detalle_suministro(s, self.e.variedad, periodo=7, primera_en_dias=dias)
        self.assertEqual(calendario.rige_desde(d, self.hoy), self.hoy + timedelta(days=dias + 7))

    def test_regla_rige_desde_sin_periodos_posteriores_a_la_ventana_es_none(self):
        """Si el detalle termina dentro de la ventana, no hay desde cuándo: `None` («Todos sus períodos ya están dentro de la ventana»)."""
        s = suministro(self.e, duracion=1)
        d = detalle_suministro(s, self.e.variedad, periodo=7, primera_en_dias=3, fecha_fin_detalle=self.hoy + timedelta(days=10))
        self.assertIsNone(calendario.rige_desde(d, self.hoy))


class FechaBaseDeAjusteTests(ConDatosDeInventario, TestCase):
    """«`fecha_base_ajuste`» (decisión de aplicación validada el 21/11/2026): la realización en un detalle pactado; la primera entrega en
    un sucesor o un agregado (los crea COM-03b: acá, con un sucesor de fábrica)."""

    def setUp(self):
        self.e = escenario_comercial()
        self.hoy = timezone.localdate()

    def test_regla_el_detalle_pactado_cuenta_los_meses_desde_la_realizacion(self):
        """Pactado: `fecha_base_ajuste` = fecha de realización del contrato."""
        s = suministro(self.e, duracion=12)
        d = detalle_suministro(s, self.e.variedad, mecanismo="ajuste_periodico", porcentaje="3.00", meses=2, primera_en_dias=3)
        self.assertEqual(d.fecha_base_ajuste, s.fecha_realizacion)
        despues = calendario.sumar_meses(s.fecha_realizacion, 2)
        self.assertEqual(calendario.precio_en(d, despues), (d.precio_unitario_suministro * Decimal("1.03")).quantize(Decimal("0.01")))

    def test_regla_el_sucesor_cuenta_los_meses_desde_su_primera_entrega(self):
        """Sucesor (regla «Precio con ajuste periódico en el detalle nuevo»): los meses se cuentan desde su primera entrega, no desde la
        realización del contrato, así que su primer período vale el precio inicial aunque el contrato lleve meses."""
        s = suministro(self.e, duracion=12, fecha_realizacion=self.hoy - timedelta(days=200))
        viejo = detalle_suministro(s, self.e.variedad, estado="finalizado", fecha_fin_detalle=self.hoy - timedelta(days=1))
        sucesor = detalle_suministro(
            s, self.e.variedad, mecanismo="ajuste_periodico", porcentaje="3.00", meses=2, primera_en_dias=20, reemplaza_a=viejo,
            fecha_base_ajuste=self.hoy + timedelta(days=20), precio="1000.00",
        )
        self.assertEqual(calendario.precio_en(sucesor, sucesor.fecha_primer_entrega), Decimal("1000.00"))
        dos_meses = calendario.sumar_meses(sucesor.fecha_primer_entrega, 2)
        self.assertEqual(calendario.precio_en(sucesor, dos_meses), Decimal("1030.00"))
