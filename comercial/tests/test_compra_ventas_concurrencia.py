# Pruebas de concurrencia de COM-REG-CVT (COM-02, paso 4; docs/casos_de_uso/comercial/compra_venta.md, «Concurrencia»): dos ventas por el último
# stock de un lote, una venta contra la baja del cliente y una venta contra el cambio de Vendedor del invernadero (D-60). Orden de bloqueos
# (docs/patrones/stock_maduro.md, sección 3): cuentas → invernaderos → cliente → variedades → lotes y partidas. Dos hilos, dos conexiones, el
# orden fijado con ``primera``. Son ``TransactionTestCase``: sin Georef (las ventas son con retiro). Todas terminan verificando los
# invariantes de las reservas. Nunca un error 500: el que pierde recibe un rechazo claro.

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Cliente, CompraVenta
from comercial.servicios import clientes, compra_ventas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.tests.fabricas import escenario_comercial, verificar_invariantes_de_reservas
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.servicios import invernaderos
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_vendedor
from maestros.tests.test_prod_mod_inv import datos_de
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar


@tag("concurrencia")
class CompraVentasConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Las tres de «Concurrencia» del extracto de COM-REG-CVT."""

    def armar(self, cantidad_de_stock=50):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.gerente = crear_gerente()
        self.lote = lote_maduro(self.e, cantidad_de_stock)
        self.addCleanup(verificar_invariantes_de_reservas)

    def vender(self, cantidad, actor=None):
        """Una operación que registra una venta con retiro de ``cantidad`` plantas en el invernadero del escenario."""
        datos = DatosDeCompraVenta(
            vendedor_id=str(self.e.vendedor.pk) if actor is not None else "",
            cliente_id=str(self.e.cliente.pk),
            fecha_pactada=str(timezone.localdate() + timedelta(days=3)),
            modalidad="retiro",
            invernadero_id=str(self.e.invernadero.pk),
            renglones=[Renglon(0, str(self.e.variedad.pk), str(cantidad), "100")],
        )
        return lambda: compra_ventas.registrar_compra_venta(actor or self.e.vendedor, datos)

    def test_regla_dos_ventas_por_el_ultimo_stock_de_un_lote_una_registra_y_la_otra_recibe_stock_insuficiente_con_maximo_cero(self):
        """Extensión 14a y garantía mínima 3: un lote de 50 y dos ventas por 50 (las dos vieron 50). Una registra; la otra espera, relee y
        recibe `stock_insuficiente` con el nuevo máximo 0; no queda nada de la segunda (venta, reservas, cosecha ni auditoría)."""
        self.armar(50)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(50), self.vender(50, actor=self.gerente), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(rechazos[0].error_dict["renglon-0-cantidad"][0].message, "Hay 0 plantas disponibles para esa fecha.")
        self.assertEqual(CompraVenta.objects.count(), 1)

    def test_regla_una_venta_primero_y_la_baja_del_cliente_despues_las_dos_terminan(self):
        """Patrón, sección 3, nivel 2b: la venta toma el cliente antes de crear; la baja (cuenta → cliente) espera, y como la baja no se bloquea
        nunca (regla 1 de COM-BAJ-CLT) termina: queda la venta y el cliente inactivo."""
        self.armar()
        exitos, rechazos, otros = separar(
            correr_a_la_vez(self.vender(20), lambda: clientes.baja_cliente(self.gerente, self.e.cliente.pk), primera="a")
        )
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(CompraVenta.objects.count(), 1)
        self.assertEqual(Cliente.objects.get(pk=self.e.cliente.pk).estado_cliente, "inactivo")

    def test_regla_la_baja_del_cliente_primero_rechaza_la_venta_con_cliente_inactivo(self):
        """Paso 14 y bloqueos: con la baja primero, la venta espera el cliente, lo relee inactivo y se rechaza con `cliente_inactivo` («El cliente
        se dio de baja mientras cargabas la venta.»); no queda nada."""
        self.armar()
        resultados = correr_a_la_vez(self.vender(20), lambda: clientes.baja_cliente(self.gerente, self.e.cliente.pk), primera="b")
        venta, baja = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(baja[0]), baja[2], venta[2], len(venta[1])), (1, [], [], 1))
        self.assertIn("cliente_inactivo", codigos_del_rechazo(venta[1][0]))
        self.assertEqual(CompraVenta.objects.count(), 0)

    def cambiar_vendedor(self, nuevo):
        """Una operación que cambia el Vendedor del invernadero (PROD-MOD-INV, D-60), confirmando el aviso de personal."""
        datos = datos_de(self.e.invernadero) | {"vendedor_id": nuevo.pk, "personal_confirmado": True}
        return lambda: invernaderos.modificar_invernadero(self.gerente, self.e.invernadero.pk, **datos)

    def test_regla_una_venta_primero_y_el_cambio_de_vendedor_la_pasa_al_vendedor_nuevo(self):
        """D-60 y patrón, sección 3: la venta se registra con el invernadero bloqueado; el cambio de Vendedor espera, la encuentra abierta y la
        pasa al Vendedor nuevo (las reservas no se mueven). Nunca una venta del Vendedor anterior creada en medio del traspaso."""
        self.armar()
        nuevo = crear_vendedor(email="nuevo@infoponia.com")
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(20), self.cambiar_vendedor(nuevo), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        (venta,) = CompraVenta.objects.all()
        self.assertEqual(venta.vendedor_id, nuevo.pk)

    def test_regla_el_cambio_de_vendedor_primero_rechaza_la_venta_con_retiro_en_ese_invernadero(self):
        """D-60: con el cambio primero, la venta (del Vendedor anterior) espera el invernadero, lo relee de otro Vendedor y se rechaza con
        `invernadero_no_habilitado`; no queda nada."""
        self.armar()
        nuevo = crear_vendedor(email="nuevo@infoponia.com")
        resultados = correr_a_la_vez(self.vender(20), self.cambiar_vendedor(nuevo), primera="b")
        venta, cambio = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(cambio[0]), cambio[2], venta[2], len(venta[1])), (1, [], [], 1))
        self.assertIn("invernadero_no_habilitado", codigos_del_rechazo(venta[1][0]))
        self.assertEqual(CompraVenta.objects.count(), 0)
