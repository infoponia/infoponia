# Pruebas de compras/precios.py (CMP-02a, paso 2): cómo se calcula el precio unitario derivado, el total desde un unitario y el valor de
# lo recibido de una línea. Fuente: D-89 (puntos 1, 2, 4 y 7) y docs/casos_de_uso/compras/pedidos.md (CMP-ENV-COT, «Precio»). Son funciones
# puras, sin base. El módulo se toma dentro de cada prueba (``perezoso``), así que mientras no existe falla cada prueba por separado.

from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from inventario.tests.fabricas import perezoso

precios = perezoso("compras.precios")


def linea_de_cotizacion(cantidad, total):
    """Una línea con la forma de ``DetalleCotizacion`` (``cantidad_cotizada`` y ``total_linea``), sin tocar la base."""
    return SimpleNamespace(cantidad_cotizada=Decimal(str(cantidad)), total_linea=Decimal(str(total)))


def linea_de_orden(cantidad, total):
    """Una línea con la forma de ``DetalleOrdenCompra`` (``cantidad_detalle_orden`` y ``total_linea``; la crea CMP-03)."""
    return SimpleNamespace(cantidad_detalle_orden=Decimal(str(cantidad)), total_linea=Decimal(str(total)))


class PrecioUnitarioTests(SimpleTestCase):
    """D-89 punto 1: el unitario no se guarda; se deriva con cuatro decimales y ``ROUND_HALF_UP``."""

    def test_d89_el_unitario_es_el_total_dividido_la_cantidad_con_cuatro_decimales(self):
        """D-89 punto 1: ``precio_unitario = (total_linea / cantidad)`` cuantizado a ``0,0001``."""
        for cantidad, total, esperado in (
            ("3", "100.00", "33.3333"),
            ("3", "1.00", "0.3333"),
            ("8", "1.00", "0.1250"),
            ("2.5", "10.00", "4.0000"),
            ("1", "199.99", "199.9900"),
        ):
            with self.subTest(cantidad=cantidad, total=total):
                self.assertEqual(precios.precio_unitario(linea_de_cotizacion(cantidad, total)), Decimal(esperado))

    def test_d89_redondea_hacia_arriba_en_la_mitad(self):
        """D-89 punto 1: ``ROUND_HALF_UP``: 2/3 da 0,6667 y 0,00005 (la mitad exacta del cuarto decimal) sube."""
        self.assertEqual(precios.precio_unitario(linea_de_cotizacion("3", "2.00")), Decimal("0.6667"))
        self.assertEqual(precios.precio_unitario(linea_de_cotizacion("200", "0.01")), Decimal("0.0001"))  # 0,00005 → 0,0001

    def test_d89_sirve_para_una_linea_de_cotizacion_y_para_una_de_orden(self):
        """D-89 punto 1: una sola función para las pantallas y los servicios, de la cotización y de la orden de compra (CMP-03)."""
        self.assertEqual(precios.precio_unitario(linea_de_cotizacion("3", "100.00")), Decimal("33.3333"))
        self.assertEqual(precios.precio_unitario(linea_de_orden("3", "100.00")), Decimal("33.3333"))

    def test_d89_una_cantidad_cero_o_negativa_es_un_error_de_uso(self):
        """D-89: la cantidad de una línea es mayor que cero (la base lo garantiza); dividir por cero no se tolera en silencio."""
        for cantidad in ("0", "-1"):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ValueError):
                    precios.precio_unitario(linea_de_cotizacion(cantidad, "10.00"))

    def test_d89_punto_7_el_unitario_se_muestra_con_dos_decimales(self):
        """D-89 punto 7: en pantallas, correos y comprobantes el unitario derivado se muestra con dos decimales (``ROUND_HALF_UP``)."""
        for cantidad, total, esperado in (("3", "100.00", "33.33"), ("3", "2.00", "0.67"), ("8", "1.00", "0.13"), ("4", "10.00", "2.50")):
            with self.subTest(cantidad=cantidad, total=total):
                self.assertEqual(precios.precio_unitario_para_mostrar(linea_de_cotizacion(cantidad, total)), Decimal(esperado))

    def test_d89_punto_7_cuando_el_redondeo_no_cierra_manda_el_total_guardado(self):
        """D-89 punto 7: si unitario (a dos decimales) × cantidad no da el total, la pantalla muestra el total guardado, que es el que manda."""
        cierra = linea_de_cotizacion("4", "10.00")  # 2,50 × 4 = 10,00
        no_cierra = linea_de_cotizacion("3", "100.00")  # 33,33 × 3 = 99,99 ≠ 100,00
        self.assertTrue(precios.unitario_cierra_con_el_total(cierra))
        self.assertFalse(precios.unitario_cierra_con_el_total(no_cierra))


class TotalDesdeUnitarioTests(SimpleTestCase):
    """D-89 punto 2: el proveedor puede cargar el unitario; el total se calcula y se redondea a dos decimales."""

    def test_d89_total_es_unitario_por_cantidad_con_dos_decimales(self):
        """D-89 punto 2 y regla «Subtotal» de CMP-ENV-COT: ``total = unitario × cantidad``, ``ROUND_HALF_UP`` a dos decimales."""
        for unitario, cantidad, esperado in (
            ("33.33", "3", "99.99"),
            ("0.33", "10", "3.30"),
            ("2.50", "2.5", "6.25"),
            ("0.01", "0.5", "0.01"),  # 0,005 → 0,01: la mitad sube
            ("12.35", "1.001", "12.36"),  # 12,36235 → 12,36
        ):
            with self.subTest(unitario=unitario, cantidad=cantidad):
                self.assertEqual(precios.total_desde_unitario(Decimal(unitario), Decimal(cantidad)), Decimal(esperado))

    def test_d89_el_total_siempre_tiene_dos_decimales(self):
        """D-89 punto 7: todo importe de dinero tiene dos decimales, siempre."""
        total = precios.total_desde_unitario(Decimal("5"), Decimal("2"))
        self.assertEqual(total, Decimal("10.00"))
        self.assertEqual(total.as_tuple().exponent, -2)

    def test_d89_los_importes_son_decimal_y_no_float(self):
        """CLAUDE.md, «Convenciones»: dinero siempre con ``Decimal``; un ``float`` es un error de uso."""
        with self.assertRaises(TypeError):
            precios.total_desde_unitario(2.5, Decimal("2"))


class ValorRecibidoTests(SimpleTestCase):
    """D-89 punto 4: ``valor_recibido(linea, recibido)``: el total si se recibió todo; si no, ``round(recibido × unitario, 2)``."""

    def test_d89_si_se_recibio_todo_el_valor_es_el_total_guardado(self):
        """D-89 punto 4: ``recibido == cantidad`` ⇒ ``total_linea`` exacto, sin diferencias de redondeo."""
        linea = linea_de_orden("3", "100.00")
        self.assertEqual(precios.valor_recibido(linea, Decimal("3")), Decimal("100.00"))

    def test_d89_si_se_recibio_una_parte_el_valor_es_lo_recibido_por_el_unitario(self):
        """D-89 punto 4: ``round(recibido × precio_unitario, 2)`` con el unitario de cuatro decimales."""
        linea = linea_de_orden("3", "100.00")
        self.assertEqual(precios.valor_recibido(linea, Decimal("1")), Decimal("33.33"))
        self.assertEqual(precios.valor_recibido(linea, Decimal("2")), Decimal("66.67"))
        self.assertEqual(precios.valor_recibido(linea, Decimal("0")), Decimal("0.00"))

    def test_d89_tres_recepciones_parciales_suman_exactamente_el_total(self):
        """D-89 punto 4: el asiento de cada recepción es ``valor(acumulado después) − valor(acumulado antes)``; las tres diferencias
        suman el total de la línea, sin un centavo colgado en Proveedores."""
        linea = linea_de_orden("3", "100.00")
        acumulados = [Decimal("0"), Decimal("1"), Decimal("2"), Decimal("3")]
        valores = [precios.valor_recibido(linea, a) for a in acumulados]
        diferencias = [despues - antes for antes, despues in zip(valores, valores[1:])]
        self.assertEqual(diferencias, [Decimal("33.33"), Decimal("33.34"), Decimal("33.33")])
        self.assertEqual(sum(diferencias), Decimal("100.00"))

    def test_d89_lo_recibido_no_puede_superar_lo_de_la_linea_ni_ser_negativo(self):
        """Regla 6 de 8.20: la recepción no supera lo pendiente; la función no inventa un valor para una cantidad imposible."""
        linea = linea_de_orden("3", "100.00")
        for recibido in ("3.001", "-1"):
            with self.subTest(recibido=recibido):
                with self.assertRaises(ValueError):
                    precios.valor_recibido(linea, Decimal(recibido))
