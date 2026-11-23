# Pruebas de compras/servicios/cobertura.py (CMP-02a, paso 2): la cobertura de un pedido con un conjunto de cotizaciones y la tolerancia.
# Fuente: CMP-ENV-COT («Pedido cubierto», regla 14 de 8.16), CMP-GNR-ODC («Cobertura mínima de un detalle», con sus cuatro ejemplos:
# 20 lechugas y 20 tomates, tolerancia del 10 %, mínimo 18 de cada uno) y D-89 punto 3. Lo usan el aviso de «pedido cubierto» (esta tarea)
# y CMP-03. Solo lee: no bloquea ni escribe. El módulo se toma dentro de cada prueba, así que mientras no existe falla cada una.

from decimal import Decimal

from django.test import TestCase

from compras.tests.fabricas import cotizacion_de, detalle_de_pedido
from compras.tests.fabricas import pedido as armar_pedido
from compras.tests.fabricas import proveedor
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo_con_invernadero

cobertura_de = perezoso("compras.servicios.cobertura")


class CoberturaTests(ConDatosDeInventario, TestCase):
    """Se piden 20 lechugas y 20 tomates (en un invernadero del Agrónomo) y se cotiza con distintos proveedores."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.pedido = armar_pedido(self.agronomo)
        self.lechuga = detalle_de_pedido(
            self.pedido, existencia(insumo("Lechuga", unidad="unidad"), self.invernadero, minimo=20), cantidad="20"
        )
        self.tomate = detalle_de_pedido(
            self.pedido, existencia(insumo("Tomate", unidad="unidad"), self.invernadero, minimo=20), cantidad="20"
        )
        self.a, self.b = proveedor(n=1), proveedor("Verdulería B", n=2, email="b@verduleria.com")
        self.poner_tolerancia(10)

    def poner_tolerancia(self, porcentaje):
        """La tolerancia de cobertura de la configuración operativa (``porc_tolerancia_cobertura_pedido``)."""
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = porcentaje
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])

    def cotizar(self, proveedor_, lechugas=None, tomates=None):
        """Una cotización de ``proveedor_`` con las cantidades que se indiquen (las líneas que no se indican no se cotizan)."""
        lineas = []
        if lechugas is not None:
            lineas.append((self.lechuga, lechugas, "10.00", 2))
        if tomates is not None:
            lineas.append((self.tomate, tomates, "10.00", 2))
        return cotizacion_de(self.pedido, proveedor_, lineas)

    def calcular(self, *cotizaciones, **kwargs):
        """``cobertura(pedido, cotizaciones)`` del servicio."""
        return cobertura_de.cobertura(self.pedido, list(cotizaciones), **kwargs)

    # ---- Los cuatro ejemplos de la regla (CMP-GNR-ODC) ----

    def test_regla_14_ejemplo_1_a_20_l_10_t_mas_b_10_t_cubre(self):
        """Regla «Cobertura mínima» (ejemplo 1): A (20 L, 10 T) + B (10 T): los dos detalles llegan al mínimo de 18 (20 y 20)."""
        resultado = self.calcular(self.cotizar(self.a, 20, 10), self.cotizar(self.b, None, 10))
        self.assertTrue(cobertura_de.esta_cubierto(resultado))
        self.assertEqual(resultado[self.lechuga.pk].cotizada, Decimal("20"))
        self.assertEqual(resultado[self.tomate.pk].cotizada, Decimal("20"))
        self.assertEqual(resultado[self.lechuga.pk].minima, Decimal("18"))

    def test_regla_14_ejemplo_2_cubre_con_sobrante_de_5_lechugas(self):
        """Regla «Cobertura mínima» (ejemplo 2): A (15 L, 10 T) + B (10 L, 10 T): cubre y sobran 5 lechugas (advertencia en CMP-03)."""
        resultado = self.calcular(self.cotizar(self.a, 15, 10), self.cotizar(self.b, 10, 10))
        self.assertTrue(cobertura_de.esta_cubierto(resultado))
        self.assertEqual(resultado[self.lechuga.pk].sobra, Decimal("5"))
        self.assertEqual(resultado[self.tomate.pk].sobra, Decimal("0"))

    def test_regla_14_ejemplo_3_19_lechugas_alcanzan_por_la_tolerancia(self):
        """Regla «Cobertura mínima» (ejemplo 3): A (19 L, 10 T) + B (10 T): 19 ≥ 18, cubre aunque falte una lechuga para las 20."""
        resultado = self.calcular(self.cotizar(self.a, 19, 10), self.cotizar(self.b, None, 10))
        self.assertTrue(cobertura_de.esta_cubierto(resultado))
        self.assertEqual(resultado[self.lechuga.pk].sobra, Decimal("0"))

    def test_regla_14_ejemplo_4_15_lechugas_no_alcanzan(self):
        """Regla «Cobertura mínima» (ejemplo 4): A (15 L, 10 T) + B (10 T): 15 < 18, no cubre; faltan 3 lechugas para el mínimo."""
        resultado = self.calcular(self.cotizar(self.a, 15, 10), self.cotizar(self.b, None, 10))
        self.assertFalse(cobertura_de.esta_cubierto(resultado))
        self.assertFalse(resultado[self.lechuga.pk].cubierto)
        self.assertTrue(resultado[self.tomate.pk].cubierto)
        self.assertEqual(resultado[self.lechuga.pk].falta, Decimal("3"))

    # ---- Otras reglas de la cobertura ----

    def test_regla_cobertura_tiene_una_entrada_por_cada_detalle_del_pedido(self):
        """CMP-ENV-COT «Pedido cubierto»: ``dict[detalle_id, Cobertura]``; un detalle sin líneas figura con 0 cotizado y no cubierto."""
        resultado = self.calcular(self.cotizar(self.a, 20, None))
        self.assertEqual(set(resultado), {self.lechuga.pk, self.tomate.pk})
        self.assertEqual(resultado[self.tomate.pk].cotizada, Decimal("0"))
        self.assertFalse(resultado[self.tomate.pk].cubierto)
        self.assertEqual(resultado[self.tomate.pk].falta, Decimal("18"))

    def test_regla_sin_cotizaciones_no_cubre_nada(self):
        """CMP-ENV-COT «Pedido cubierto»: sin cotizaciones recibidas, ningún detalle está cubierto (con tolerancia menor que 100 %)."""
        resultado = self.calcular()
        self.assertFalse(cobertura_de.esta_cubierto(resultado))
        self.assertEqual({c.cotizada for c in resultado.values()}, {Decimal("0")})

    def test_d89_punto_3_la_cantidad_cotizada_puede_superar_la_pedida_y_cuenta_completa(self):
        """D-89 punto 3 (P2): la cobertura suma la cantidad **cotizada**, aunque supere la pedida; la pantalla muestra la diferencia."""
        resultado = self.calcular(self.cotizar(self.a, 30, 20))
        self.assertTrue(cobertura_de.esta_cubierto(resultado))
        self.assertEqual(resultado[self.lechuga.pk].cotizada, Decimal("30"))
        self.assertEqual(resultado[self.lechuga.pk].sobra, Decimal("10"))

    def test_regla_solo_cuentan_las_cotizaciones_que_se_pasan(self):
        """CMP-GNR-ODC: la cobertura es de las cotizaciones **elegidas**; una cotización del pedido que no se pasa no suma."""
        elegida = self.cotizar(self.a, 10, 10)
        self.cotizar(self.b, 20, 20)  # existe pero no se pasa
        resultado = self.calcular(elegida)
        self.assertEqual(resultado[self.lechuga.pk].cotizada, Decimal("10"))
        self.assertFalse(cobertura_de.esta_cubierto(resultado))

    def test_regla_tolerancia_cero_exige_la_cantidad_pedida(self):
        """Regla 14 de 8.16 con ``porcToleranciaCoberturaPedido = 0`` (el valor inicial): el mínimo es la cantidad pedida."""
        self.poner_tolerancia(0)
        resultado = self.calcular(self.cotizar(self.a, 19, 20))
        self.assertEqual(resultado[self.lechuga.pk].minima, Decimal("20"))
        self.assertFalse(resultado[self.lechuga.pk].cubierto)
        self.assertTrue(resultado[self.tomate.pk].cubierto)

    def test_regla_la_tolerancia_se_lee_de_la_configuracion_en_cada_uso(self):
        """MAE-04 regla 7 y CMP-ENV-COT: el parámetro se lee con ``obtener()`` en cada uso; un cambio rige hacia adelante, sin copia."""
        cotizaciones = [self.cotizar(self.a, 15, 20)]
        self.poner_tolerancia(25)  # mínimo 15
        self.assertTrue(cobertura_de.esta_cubierto(self.calcular(*cotizaciones)))
        self.poner_tolerancia(10)  # mínimo 18
        self.assertFalse(cobertura_de.esta_cubierto(self.calcular(*cotizaciones)))

    def test_regla_la_tolerancia_se_puede_pasar_para_comparar_antes_y_despues_con_el_mismo_valor(self):
        """CMP-ENV-COT «Pedido cubierto» (D-88 punto 7): el registro lee la tolerancia una vez y calcula antes y después con ella."""
        resultado = self.calcular(self.cotizar(self.a, 15, 20), tolerancia=25)
        self.assertEqual(resultado[self.lechuga.pk].minima, Decimal("15"))
        self.assertTrue(cobertura_de.esta_cubierto(resultado))

    def test_regla_el_minimo_es_exacto_con_las_cantidades_decimales_de_la_unidad(self):
        """Regla 2 de 8.23 (decimales según la unidad): el mínimo ``pedida × (1 − tolerancia)`` no se redondea a dos decimales."""
        agua = detalle_de_pedido(
            self.pedido, existencia(insumo("Solución nutritiva", unidad="kg"), self.invernadero, minimo=1), cantidad="1.234"
        )
        self.poner_tolerancia(10)
        resultado = cobertura_de.cobertura(self.pedido, [])
        self.assertEqual(resultado[agua.pk].minima, Decimal("1.1106"))
