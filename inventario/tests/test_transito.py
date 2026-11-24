# Pruebas de ``sumar_transito`` y ``restar_transito`` (CMP-03, paso 2; docs/api/stock.md, «Escritura de compras»; D-90 puntos 1 y 5; regla 22 de 8.16 y
# regla 1 de 8.19). Las escribe CMP-03 dentro de ``inventario`` porque son las únicas funciones que cambian ``cant_transito_insumo``:
#   stock.sumar_transito(iin_id, cantidad)  -> InsumoInvernadero   (la usa CMP-03 al aprobar una orden)
#   stock.restar_transito(iin_id, cantidad) -> InsumoInvernadero   (la usa CMP-04 al recibir y al cerrar con faltante)
# Contrato: corren dentro de la transacción de quien llama (con el invernadero ya bloqueado), bloquean y vuelven a leer el ``InsumoInvernadero``, validan la
# cantidad con los decimales de la unidad, NO crean movimientos (regla 1 de 8.19: el tránsito no es stock) y NO tocan lotes, alertas ni ``referencia_precio``.

from decimal import Decimal

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, verificar_invariantes
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

BAJO_MINIMO = "inv_insumo_bajo_minimo"


class TransitoTests(ConDatosDeInventario, TestCase):
    """Las dos funciones de tránsito de ``inventario.servicios.stock``."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", unidad="l")
        self.iin = existencia(self.insumo, self.invernadero, minimo=0, precio="12.50")

    def transito(self):
        """El tránsito guardado, releído de la base."""
        return InsumoInvernadero.objects.get(pk=self.iin.pk).cant_transito_insumo

    def sumar(self, cantidad, iin=None):
        with transaction.atomic():
            return stock.sumar_transito((iin or self.iin).pk, cantidad)

    def restar(self, cantidad, iin=None):
        with transaction.atomic():
            return stock.restar_transito((iin or self.iin).pk, cantidad)

    # ---- sumar_transito ----

    def test_regla_22_de_8_16_sumar_aumenta_el_transito_y_devuelve_la_existencia(self):
        """CMP-APR-ODC postcondición f y regla 22 de 8.16: aprobar una orden suma la cantidad al tránsito del ``InsumoInvernadero`` y devuelve la existencia."""
        resultado = self.sumar("12.5")
        self.assertIsInstance(resultado, InsumoInvernadero)
        self.assertEqual(resultado.pk, self.iin.pk)
        self.assertEqual(resultado.cant_transito_insumo, Decimal("12.500"))
        self.assertEqual(self.transito(), Decimal("12.500"))

    def test_post_f_sumar_acumula_sobre_lo_que_ya_estaba_en_transito(self):
        """CMP-APR-ODC postcondición f: varias aprobaciones sobre el mismo insumo y destino suman (no pisan) el tránsito."""
        existente = existencia(insumo("Nutriente B", unidad="l"), self.invernadero, transito="4")
        self.sumar("3", existente)
        self.sumar("2.25", existente)
        self.assertEqual(InsumoInvernadero.objects.get(pk=existente.pk).cant_transito_insumo, Decimal("9.250"))

    def test_regla_1_de_8_19_sumar_no_crea_movimientos_ni_toca_los_lotes(self):
        """Regla 1 de 8.19 y docs/api/stock.md: el tránsito no es stock; sumar no crea ``MovimientoInsumo`` ni cambia lotes."""
        un_lote = lote(self.iin, "10")
        antes = MovimientoInsumo.objects.count()
        self.sumar("5")
        self.assertEqual(MovimientoInsumo.objects.count(), antes)
        self.assertEqual(LoteInsumo.objects.get(pk=un_lote.pk).cantidad_disponible, Decimal("10.000"))
        verificar_invariantes(InsumoInvernadero.objects.get(pk=self.iin.pk))

    def test_regla_6_de_8_18_sumar_no_cambia_el_precio_de_referencia(self):
        """Regla 6 de 8.18 (docs/api/stock.md): las escrituras de compras no cambian ``referencia_precio``."""
        self.sumar("5")
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.iin.pk).referencia_precio, Decimal("12.50"))

    def test_post_d_de_apr_odc_sumar_no_resuelve_la_alerta_de_bajo_el_minimo(self):
        """CMP-APR-ODC postcondición d y regla «Alerta de insumo bajo el mínimo»: aprobar no resuelve la alerta aunque el tránsito alcance el mínimo; se resuelve
        al registrar la recepción (CMP-04). Por eso ``sumar_transito`` no reevalúa las alertas."""
        bajo = existencia(insumo("Nutriente C", unidad="l"), self.invernadero, minimo=10)
        from inventario.servicios import alertas_de_stock

        with transaction.atomic():
            alertas_de_stock.reevaluar_alertas_del_insumo(bajo.pk)
        activas = Alerta.objects.filter(tipo_alerta=BAJO_MINIMO, estado_alerta="activa")
        self.assertEqual(activas.count(), 1)
        self.sumar("50", bajo)
        self.assertEqual(activas.count(), 1)

    def test_regla_2_de_8_23_sumar_valida_los_decimales_de_la_unidad(self):
        """Regla 2 de 8.23 y D-87 punto 7: la cantidad se valida con ``validar_cantidad``; un «unidad» no admite decimales y el tránsito no cambia."""
        por_unidad = existencia(insumo("Macetas", unidad="unidad"), self.invernadero)
        with self.assertRaises(ValueError):
            self.sumar("2.5", por_unidad)
        self.assertEqual(InsumoInvernadero.objects.get(pk=por_unidad.pk).cant_transito_insumo, Decimal("0"))
        self.sumar("3", por_unidad)
        self.assertEqual(InsumoInvernadero.objects.get(pk=por_unidad.pk).cant_transito_insumo, Decimal("3"))

    def test_regla_cantidad_invalida_no_cambia_nada(self):
        """Error de uso de quien llama: una cantidad cero, negativa, no numérica o ``float`` es ``ValueError`` (o ``TypeError`` el ``float``) y no cambia el tránsito."""
        for cantidad in ("0", "-1", "abc", "", None):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ValueError):
                    self.sumar(cantidad)
        with self.assertRaises((ValueError, TypeError)):
            self.sumar(1.5)
        self.assertEqual(self.transito(), Decimal("0"))

    def test_regla_sumar_a_una_existencia_inexistente_falla(self):
        """Error de uso: un ``iin_id`` que no existe no se ignora."""
        with self.assertRaises(InsumoInvernadero.DoesNotExist):
            self.sumar("1", InsumoInvernadero(pk=987654))

    def test_regla_sumar_bloquea_y_vuelve_a_leer_la_existencia(self):
        """Contrato de docs/api/stock.md: bloquea la fila (``FOR NO KEY UPDATE``) y la vuelve a leer, así que suma sobre lo que hay en la base aunque quien llama
        tenga un objeto viejo en memoria."""
        viejo = InsumoInvernadero.objects.get(pk=self.iin.pk)
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_transito_insumo=Decimal("7"))
        with CaptureQueriesContext(connection) as consultas, transaction.atomic():
            stock.sumar_transito(viejo.pk, "1")
        self.assertEqual(self.transito(), Decimal("8.000"))
        self.assertTrue(any("FOR NO KEY UPDATE" in c["sql"] for c in consultas.captured_queries))

    # ---- restar_transito ----

    def test_regla_22_de_8_16_restar_disminuye_el_transito_y_devuelve_la_existencia(self):
        """Regla 22 de 8.16: el tránsito baja con cada recepción y al cerrar con faltante (CMP-04); devuelve la existencia."""
        con_transito = existencia(insumo("Nutriente D", unidad="l"), self.invernadero, transito="10")
        resultado = self.restar("4.5", con_transito)
        self.assertEqual(resultado.pk, con_transito.pk)
        self.assertEqual(resultado.cant_transito_insumo, Decimal("5.500"))
        self.assertEqual(InsumoInvernadero.objects.get(pk=con_transito.pk).cant_transito_insumo, Decimal("5.500"))

    def test_regla_restar_todo_el_transito_lo_deja_en_cero(self):
        """El tránsito puede quedar en cero (una orden recibida por completo)."""
        con_transito = existencia(insumo("Nutriente D", unidad="l"), self.invernadero, transito="10")
        self.restar("10", con_transito)
        self.assertEqual(InsumoInvernadero.objects.get(pk=con_transito.pk).cant_transito_insumo, Decimal("0"))

    def test_regla_restar_nunca_deja_el_transito_negativo(self):
        """docs/api/stock.md y D-90 punto 1: restar más de lo que hay en tránsito es ``ValueError`` y no cambia nada (la restricción de la base es el respaldo)."""
        con_transito = existencia(insumo("Nutriente D", unidad="l"), self.invernadero, transito="10")
        with self.assertRaises(ValueError):
            self.restar("10.001", con_transito)
        self.assertEqual(InsumoInvernadero.objects.get(pk=con_transito.pk).cant_transito_insumo, Decimal("10"))
        with self.assertRaises(ValueError):
            self.restar("1")  # sin nada en tránsito

    def test_regla_1_de_8_19_restar_no_crea_movimientos_ni_toca_los_lotes(self):
        """Regla 1 de 8.19: restar tampoco crea movimientos ni cambia lotes."""
        con_transito = existencia(insumo("Nutriente D", unidad="l"), self.invernadero, transito="10")
        un_lote = lote(con_transito, "6")
        antes = MovimientoInsumo.objects.count()
        self.restar("4", con_transito)
        self.assertEqual(MovimientoInsumo.objects.count(), antes)
        self.assertEqual(LoteInsumo.objects.get(pk=un_lote.pk).cantidad_disponible, Decimal("6.000"))

    def test_regla_2_de_8_23_restar_valida_los_decimales_y_la_cantidad(self):
        """Regla 2 de 8.23: ``restar_transito`` valida igual que ``sumar_transito`` (decimales de la unidad; mayor que cero)."""
        por_unidad = existencia(insumo("Macetas", unidad="unidad"), self.invernadero, transito="5")
        for cantidad in ("1.5", "0", "-2", "abc"):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ValueError):
                    self.restar(cantidad, por_unidad)
        self.assertEqual(InsumoInvernadero.objects.get(pk=por_unidad.pk).cant_transito_insumo, Decimal("5"))

    def test_regla_restar_bloquea_y_vuelve_a_leer_la_existencia(self):
        """Contrato de docs/api/stock.md: bloquea la fila y la vuelve a leer; la comprobación de «no negativo» usa lo releído y no lo que tenía quien llama."""
        con_transito = existencia(insumo("Nutriente D", unidad="l"), self.invernadero, transito="10")
        InsumoInvernadero.objects.filter(pk=con_transito.pk).update(cant_transito_insumo=Decimal("2"))
        with self.assertRaises(ValueError):
            self.restar("5", con_transito)  # el objeto en memoria dice 10, la base dice 2
        with CaptureQueriesContext(connection) as consultas, transaction.atomic():
            stock.restar_transito(con_transito.pk, "2")
        self.assertTrue(any("FOR NO KEY UPDATE" in c["sql"] for c in consultas.captured_queries))
        self.assertEqual(InsumoInvernadero.objects.get(pk=con_transito.pk).cant_transito_insumo, Decimal("0"))

    def test_regla_sumar_y_restar_son_inversas(self):
        """Sumar y después restar la misma cantidad deja el tránsito como estaba."""
        self.sumar("3.333")
        self.restar("3.333")
        self.assertEqual(self.transito(), Decimal("0"))
