# Pruebas de concurrencia del stock maduro (COM-02, paso 3; docs/patrones/stock_maduro.md, secciones 3 y 6): las cuatro mínimas del patrón.
# El stock libre se calcula DESPUÉS de bloquear los lotes y las partidas, así que la segunda operación ve lo que confirmó la primera (por eso
# la extensión 8a, «recalcular una vez», no hace falta). Las ventas se hacen con retiro (sin Georef: el `flush` de estas pruebas vacía las tablas).
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Todas terminan verificando los invariantes de las
# reservas (`verificar_invariantes_de_reservas`, como cierre de cada prueba). Nunca un error 500: el que pierde recibe un rechazo claro.

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva
from comercial.servicios import compra_ventas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.tests.fabricas import escenario_comercial, partida, segundo_invernadero, verificar_invariantes_de_reservas
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.servicios import variedades
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Alerta, Invernadero
from maestros.servicios import invernaderos
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Cosecha, Lote
from produccion.servicios import mermas
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar


def datos_de_retiro(e, invernadero, cantidad, dias=3):
    """Una compra-venta con retiro de ``cantidad`` plantas de la variedad del escenario."""
    return DatosDeCompraVenta(
        cliente_id=str(e.cliente.pk),
        fecha_pactada=str(timezone.localdate() + timedelta(days=dias)),
        modalidad="retiro",
        invernadero_id=str(invernadero.pk),
        renglones=[Renglon(0, str(e.variedad.pk), str(cantidad), "100")],
    )


@tag("concurrencia")
class StockMaduroConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Cuatro mínimas: dos ventas por el último stock; una venta contra una merma; contra la baja de la variedad; contra la baja del invernadero."""

    def armar(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.gerente = crear_gerente()
        self.addCleanup(verificar_invariantes_de_reservas)

    def vender(self, cantidad, invernadero=None):
        """Una operación que registra una venta con retiro de ``cantidad`` plantas."""
        datos = datos_de_retiro(self.e, invernadero or self.e.invernadero, cantidad)
        return lambda: compra_ventas.registrar_compra_venta(self.e.vendedor, datos)

    def test_regla_dos_ventas_por_el_ultimo_stock_de_un_lote_una_registra_y_la_otra_no_alcanza(self):
        """Patrón, sección 6, y 14a: un lote de 50 y dos ventas por 50. La segunda espera, ve el lote reservado y recibe `stock_insuficiente`
        con el nuevo máximo 0; el lote nunca queda reservado por encima de su stock libre ni queda nada de la segunda."""
        self.armar()
        lote = lote_maduro(self.e, 50)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(50), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(rechazos[0].error_dict["renglon-0-cantidad"][0].message, "Hay 0 plantas disponibles para esa fecha.")
        self.assertEqual(CompraVenta.objects.count(), 1)
        self.assertEqual(Cosecha.objects.count(), 1)
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=lote)), 50)

    def test_regla_dos_ventas_que_caben_las_dos_se_registran(self):
        """Control de la anterior: con stock para las dos, las dos pasan (una detrás de la otra)."""
        self.armar()
        lote_maduro(self.e, 100)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(50), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(CompraVenta.objects.count(), 2)

    def test_regla_una_merma_primero_y_la_venta_ve_el_lote_ya_achicado(self):
        """Patrón, sección 6: la merma (invernadero → variedad → sectores → lote) y la venta (invernadero → variedad → lote) toman lo común en el
        mismo sentido. Con la merma primero (40 de 50), la venta de 30 espera, relee el lote con 10 y recibe `stock_insuficiente` (máximo 10)."""
        self.armar()
        lote = lote_maduro(self.e, 50)
        resultados = correr_a_la_vez(self.vender(30), self.merma(lote, 40), primera="b")
        ventas, mermas_hechas = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(ventas[0]), len(ventas[1]), ventas[2]), (0, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(ventas[1][0]))
        self.assertEqual(ventas[1][0].error_dict["renglon-0-cantidad"][0].message, "Hay 10 plantas disponibles para esa fecha.")
        self.assertEqual((len(mermas_hechas[0]), mermas_hechas[2]), (1, []))
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 10)
        self.assertEqual(CompraVenta.objects.count(), 0)

    def test_regla_una_venta_primero_y_la_merma_que_deja_lo_reservado_a_salvo_se_registra(self):
        """Patrón, sección 6: con la venta primero (30 reservados de 50), la merma de 15 espera, termina y el lote queda con 35: las dos se
        registran y lo reservado (30) sigue cabiendo en el lote. (Cuando la merma deja menos de lo reservado se alerta, regla 15 de 8.8: lo
        prueba `produccion/tests/test_cosecha_en_produccion.py`.)"""
        self.armar()
        lote = lote_maduro(self.e, 50)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(30), self.merma(lote, 15), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 35)
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=lote)), 30)
        self.assertFalse(Alerta.objects.filter(tipo_alerta="produccion_plantas_comprometidas").exists())

    def merma(self, lote, cantidad):
        """Una merma de ``cantidad`` plantas del lote (en su sector de Maduración), como el Capataz."""
        datos = mermas.DatosDeMerma(
            lote_id=lote.pk, cantidades=((self.e.sectores["maduracion"].pk, cantidad),), causa="plaga", cantidad_actual=None, ocupados=None
        )
        return lambda: mermas.registrar_merma(self.e.capataz, datos)

    def con_lote_finalizado_y_partida(self, invernadero_escenario, disponible=100):
        """Un invernadero con un lote finalizado (para no tener lotes activos) y una partida de cámara de ``disponible`` plantas."""
        lote = lote_maduro(invernadero_escenario, 10)
        partida(lote, disponible)
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)

    def test_regla_una_venta_contra_la_baja_de_la_variedad_nunca_deja_una_variedad_inactiva_con_ventas_abiertas(self):
        """Patrón, sección 3, nivel 3 y precondición f de PROD-BAJ-VAR: la variedad se bloquea antes de crear un contrato. Con la venta primero,
        la baja espera y ve `contratos_abiertos` (se rechaza); con la baja primero, la venta ve la variedad inactiva (`variedad_inactiva`)."""
        self.armar()
        self.con_lote_finalizado_y_partida(self.e)
        venta_primero = correr_a_la_vez(
            self.vender(10), lambda: variedades.baja_variedad(self.e.agronomo, self.e.variedad.pk), primera="a"
        )
        venta, baja = separar({"a": venta_primero["a"]}), separar({"b": venta_primero["b"]})
        self.assertEqual((len(venta[0]), venta[2], baja[2]), (1, [], []))
        self.assertEqual(len(baja[1]), 1)
        self.assertIn("Tiene contratos abiertos: 1 compra-venta", str(baja[1][0]))  # COM-03a: el texto ahora dice «contratos abiertos» (antes, «compra-ventas abiertas»)
        self.assertTrue(self.e.variedad.__class__.objects.get(pk=self.e.variedad.pk).activa)

    def test_regla_la_baja_de_la_variedad_primero_rechaza_la_venta_por_variedad_inactiva(self):
        """Control: con la baja primero (sin ventas todavía), la baja se concreta y la venta, que esperaba, se rechaza con `variedad_inactiva`."""
        self.armar()
        self.con_lote_finalizado_y_partida(self.e)
        resultados = correr_a_la_vez(
            self.vender(10), lambda: variedades.baja_variedad(self.e.agronomo, self.e.variedad.pk), primera="b"
        )
        venta, baja = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(baja[0]), baja[2], venta[2]), (1, [], []))
        self.assertEqual(len(venta[1]), 1)
        self.assertIn("variedad_inactiva", codigos_del_rechazo(venta[1][0]))
        self.assertEqual(CompraVenta.objects.count(), 0)

    def test_regla_una_venta_contra_la_baja_del_invernadero_la_baja_primero_rechaza_la_venta(self):
        """Contrato de D-40 (`bloquear_invernadero_activo`): con la baja del invernadero primero, la venta con retiro en él espera, lo ve
        inactivo y se rechaza con `invernadero_no_habilitado`; no queda ninguna reserva. (Que una venta con stock de cámara impida la baja
        llega con COM-04, que registra las partidas como impedimento: ver `docs/disparadores.md`.)"""
        self.armar()
        sur = segundo_invernadero(self.e, nombre="Invernadero Sur", geografia_propia=True)
        self.con_lote_finalizado_y_partida(sur)
        resultados = correr_a_la_vez(
            self.vender(10, sur.invernadero), lambda: invernaderos.baja_invernadero(self.gerente, sur.invernadero.pk), primera="b"
        )
        venta, baja = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual(venta[2], [])
        self.assertEqual(baja[2], [])
        if baja[0]:  # la baja se concretó: la venta no puede haber reservado nada en un invernadero inactivo
            self.assertEqual(len(venta[1]), 1)
            self.assertIn("invernadero_no_habilitado", codigos_del_rechazo(venta[1][0]))
            self.assertEqual(Invernadero.objects.get(pk=sur.invernadero.pk).estado_invernadero, "inactivo")
            self.assertEqual(CompraVenta.objects.count(), 0)
