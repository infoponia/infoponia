# Pruebas del gráfico SVG de un sensor (IOT-04, paso 6; docs/casos_de_uso/iot/consultar_lecturas.md, «Gráficos»; regla 4 de IOT-CNS-LEC; D-76 punto 8). Se escribieron ANTES que
# la función (`.claude/rules/pruebas.md`). Es una función pura, probada sin base (como ``spark`` del prototipo):
#
#   iot/graficos.py: grafico_de_sensor(serie, franja, resumido, etiqueta="") -> str
#       serie:    hasta 24 horas, una lista de valores (las lecturas válidas, en orden); 7 y 30 días (``resumido``), una lista de ``(mínimo, promedio, máximo)`` por hora.
#       franja:   ``(mínimo, máximo)`` del umbral efectivo o del rango de la solución, o ``None`` (sin umbral no hay franja).
#       etiqueta: el texto del ``aria-label`` (variable y período), que se escapa.
# El SVG mide 360 × 96; sus elementos se marcan con clases (``grafico-linea``, ``grafico-franja``, ``grafico-envolvente``, ``grafico-ultimo``) para estas pruebas y el CSS.

from decimal import Decimal

from django.test import SimpleTestCase

from inventario.tests.fabricas import perezoso

graficos = perezoso("iot.graficos")

LECTURAS = [Decimal(v) for v in ("20.0", "21.5", "22.0", "23.5", "22.5")]
RESUMEN = [(Decimal("19"), Decimal("20"), Decimal("21")), (Decimal("20"), Decimal("22"), Decimal("23")), (Decimal("21"), Decimal("23"), Decimal("25"))]
FRANJA = (Decimal("18"), Decimal("24"))


class GraficosTests(SimpleTestCase):
    """`grafico_de_sensor`: el SVG con y sin franja, resumido y no, vacío, y que escapa el texto."""

    def test_regla_4_un_svg_de_360_por_96_con_su_rol_y_su_aria_label(self):
        """Regla 4 y «Gráficos»: SVG de 360 × 96 con `role="img"` y un `aria-label` con la variable y el período."""
        svg = graficos.grafico_de_sensor(LECTURAS, FRANJA, False, "Temperatura · Últimas 24 horas")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn('viewBox="0 0 360 96"', svg)
        self.assertIn('role="img"', svg)
        self.assertIn('aria-label="Temperatura · Últimas 24 horas"', svg)

    def test_regla_4_con_franja_dibuja_la_banda_y_sus_dos_valores_a_la_derecha(self):
        """«Gráficos»: la franja del umbral efectivo o del rango, con sus dos valores a la derecha (en el formato del sistema: coma decimal, sin ceros de más)."""
        svg = graficos.grafico_de_sensor(LECTURAS, (Decimal("18.5"), Decimal("24.0")), False, "T")
        self.assertIn("grafico-franja", svg)
        self.assertIn(">18,5<", svg)
        self.assertIn(">24<", svg)

    def test_regla_4_sin_franja_no_hay_banda_ni_valores(self):
        """«Gráficos»: «La franja es la del umbral o el rango actual. Sin umbral, no hay franja»."""
        svg = graficos.grafico_de_sensor(LECTURAS, None, False, "T")
        self.assertNotIn("grafico-franja", svg)
        self.assertIn("<polyline", svg)

    def test_regla_4_las_lecturas_se_dibujan_con_una_linea_y_un_punto_en_el_ultimo_valor(self):
        """«Gráficos»: hasta 24 horas, la línea de la serie y un punto en el último valor (una línea con un punto por lectura, sin envolvente)."""
        svg = graficos.grafico_de_sensor(LECTURAS, FRANJA, False, "T")
        self.assertEqual(svg.count("<polyline"), 1)
        self.assertEqual(len(svg.split("<polyline")[1].split('points="')[1].split('"')[0].split()), len(LECTURAS))
        self.assertEqual(svg.count("<circle"), 1)
        self.assertNotIn("grafico-envolvente", svg)

    def test_regla_4_resumido_dibuja_el_promedio_y_la_envolvente_de_minimo_a_maximo_sin_punto(self):
        """«Gráficos» (7 y 30 días): la línea es el promedio de cada hora y la franja sombreada va del mínimo al máximo; sin el punto del último valor."""
        svg = graficos.grafico_de_sensor(RESUMEN, FRANJA, True, "T")
        self.assertEqual(svg.count("<polyline"), 1)
        self.assertEqual(svg.count("<polygon"), 1)
        self.assertIn("grafico-envolvente", svg)
        self.assertNotIn("<circle", svg)

    def test_regla_4_el_ultimo_valor_fuera_de_la_franja_se_dibuja_en_color_de_peligro(self):
        """Como `spark` del prototipo: la línea y el punto van en el verde primario si el último valor está dentro de la franja y en el color de peligro si está fuera."""
        dentro = graficos.grafico_de_sensor(LECTURAS, FRANJA, False, "T")
        fuera = graficos.grafico_de_sensor(LECTURAS + [Decimal("30")], FRANJA, False, "T")
        self.assertIn("var(--primary)", dentro)
        self.assertNotIn("var(--status-danger)", dentro)
        self.assertIn("var(--status-danger)", fuera)

    def test_regla_4_sin_datos_dice_sin_lecturas_en_este_periodo(self):
        """«Gráficos»: «Sin datos en el período, "Sin lecturas en este período"»: sin línea ni punto."""
        for serie, resumido in (([], False), ([], True)):
            with self.subTest(resumido=resumido):
                html = graficos.grafico_de_sensor(serie, FRANJA, resumido, "T")
                self.assertIn("Sin lecturas en este período", html)
                self.assertNotIn("<polyline", html)
                self.assertNotIn("<circle", html)

    def test_regla_4_un_solo_punto_y_una_serie_constante_no_rompen(self):
        """Robustez: con un único valor o con todos iguales (rango cero, y sin franja) no hay división por cero; se dibuja igual."""
        for serie in ([Decimal("22")], [Decimal("22")] * 4):
            with self.subTest(serie=len(serie)):
                svg = graficos.grafico_de_sensor(serie, None, False, "T")
                self.assertIn("<polyline", svg)
                self.assertNotIn("nan", svg.lower())
                self.assertNotIn("inf", svg.lower())

    def test_regla_4_el_texto_se_escapa(self):
        """D-76 punto 8 (seguridad): la etiqueta va escapada; un `<script>` en el nombre de una variable o de un período no entra al SVG."""
        svg = graficos.grafico_de_sensor(LECTURAS, FRANJA, False, '<script>alert("x")</script>')
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_regla_4_es_una_funcion_pura(self):
        """«Función pura, probada sin base»: la misma entrada da el mismo SVG (sin hora, sin azar)."""
        self.assertEqual(
            graficos.grafico_de_sensor(LECTURAS, FRANJA, False, "T"), graficos.grafico_de_sensor(list(LECTURAS), FRANJA, False, "T")
        )
        self.assertNotEqual(graficos.grafico_de_sensor(LECTURAS, FRANJA, False, "T"), "")
