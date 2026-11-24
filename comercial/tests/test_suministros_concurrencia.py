# Pruebas de concurrencia de COM-PCT-SUM (COM-03a, paso 4; docs/casos_de_uso/comercial/suministro.md, «Concurrencia»): un pacto y una
# compra-venta por el último stock de un lote, un pacto contra la baja del cliente y dos pactos del mismo cliente con el mismo par. Orden de
# bloqueos (docs/patrones/stock_maduro.md, sección 3): cuentas → invernaderos → cliente → variedades → lotes y partidas → filas del contrato.
# Dos hilos, dos conexiones, el orden fijado con ``primera``. Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una
# dirección en la localidad propia que arma `geografia_propia`). Todas terminan verificando los invariantes de las reservas y de los
# suministros. Nunca un error 500: el que pierde recibe un rechazo claro.

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Cliente, CompraVenta, ReservaStock, Suministro
from comercial.servicios import clientes, compra_ventas, suministros
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.servicios.suministros import DatosDeSuministro, RenglonDeSuministro
from comercial.tests.fabricas import direccion_de_cliente, escenario_comercial, verificar_invariantes_de_reservas
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar


@tag("concurrencia")
class SuministrosConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Las tres de «Concurrencia» del extracto de COM-PCT-SUM."""

    def armar(self, cantidad_de_stock=50):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.gerente = crear_gerente()
        self.lote = lote_maduro(self.e, cantidad_de_stock)
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.addCleanup(verificar_invariantes_de_reservas)

    def pactar(self, cantidad, actor=None, continuar=False):
        """Una operación que pacta un suministro de ``cantidad`` plantas con un único período dentro de la ventana (el siguiente cae a los 33 días)."""
        hoy = timezone.localdate()
        datos = DatosDeSuministro(
            vendedor_id=str(self.e.vendedor.pk) if actor is not None else "",
            cliente_id=str(self.e.cliente.pk),
            duracion="6",
            tolerados="3",
            multa="1000",
            plazo_pago="15",
            indemnizacion_pago="10",
            renglones=[
                RenglonDeSuministro(
                    indice=0,
                    variedad_id=str(self.e.variedad.pk),
                    direccion_id=str(self.direccion.pk),
                    cantidad=str(cantidad),
                    periodo="30",
                    primera_entrega=str(hoy + timedelta(days=3)),
                    mecanismo="fijo",
                    precio="100",
                    plazo_entrega="1",
                    indemnizacion_retraso="1",
                    cantidad_minima="1",
                    indemnizacion_faltante="1",
                    continuar_superpuesto="1" if continuar else "",
                )
            ],
        )
        return lambda: suministros.pactar_suministro(actor or self.e.vendedor, datos)

    def vender(self, cantidad):
        """Una operación que registra una compra-venta con retiro de ``cantidad`` plantas en el mismo invernadero."""
        datos = DatosDeCompraVenta(
            cliente_id=str(self.e.cliente.pk),
            fecha_pactada=str(timezone.localdate() + timedelta(days=3)),
            modalidad="retiro",
            invernadero_id=str(self.e.invernadero.pk),
            renglones=[Renglon(0, str(self.e.variedad.pk), str(cantidad), "100")],
        )
        return lambda: compra_ventas.registrar_compra_venta(self.e.vendedor, datos)

    def test_regla_un_pacto_y_una_compra_venta_por_el_ultimo_stock_una_se_registra_y_la_otra_recibe_stock_insuficiente(self):
        """Extensión 14a y garantía mínima 3: un lote de 50; un pacto y una venta por 50 (los dos vieron 50). Se registra el primero; el segundo
        espera el lote, relee y recibe `stock_insuficiente` con el nuevo máximo 0; no queda nada de él."""
        self.armar(50)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pactar(50), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((Suministro.objects.count(), CompraVenta.objects.count()), (1, 0))

    def test_regla_una_compra_venta_y_un_pacto_por_el_ultimo_stock_en_el_orden_inverso(self):
        """El mismo choque con la venta primero: se registra la venta y el pacto recibe `stock_insuficiente` (máximo 0); no queda ningún
        suministro ni reserva suya."""
        self.armar(50)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pactar(50), self.vender(50), primera="b"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((Suministro.objects.count(), CompraVenta.objects.count()), (0, 1))
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro__isnull=False).count(), 0)

    def test_regla_un_pacto_primero_y_la_baja_del_cliente_despues_las_dos_terminan(self):
        """Patrón, sección 3, nivel 2b: el pacto toma el cliente antes de crear; la baja (cuenta → cliente) espera y, como la baja no se
        bloquea nunca (regla 1 de COM-BAJ-CLT), termina: queda el suministro y el cliente inactivo."""
        self.armar()
        exitos, rechazos, otros = separar(
            correr_a_la_vez(self.pactar(20), lambda: clientes.baja_cliente(self.gerente, self.e.cliente.pk), primera="a")
        )
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Suministro.objects.count(), 1)
        self.assertEqual(Cliente.objects.get(pk=self.e.cliente.pk).estado_cliente, "inactivo")

    def test_regla_la_baja_del_cliente_primero_rechaza_el_pacto_con_cliente_inactivo(self):
        """Con la baja primero, el pacto espera el cliente, lo relee inactivo y se rechaza con `cliente_inactivo`; no queda nada."""
        self.armar()
        resultados = correr_a_la_vez(self.pactar(20), lambda: clientes.baja_cliente(self.gerente, self.e.cliente.pk), primera="b")
        pacto, baja = separar({"a": resultados["a"]}), separar({"b": resultados["b"]})
        self.assertEqual((len(baja[0]), baja[2], pacto[2], len(pacto[1])), (1, [], [], 1))
        self.assertIn("cliente_inactivo", codigos_del_rechazo(pacto[1][0]))
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_dos_pactos_del_mismo_cliente_con_el_mismo_par_se_registran_los_dos(self):
        """Extensión 9d: la superposición entre contratos no se bloquea (decisión explícita del Vendedor, con la casilla): dos pactos del
        mismo cliente con la misma variedad y dirección (con stock para los dos) se registran, el segundo cuando el primero confirma."""
        self.armar(100)
        exitos, rechazos, otros = separar(
            correr_a_la_vez(self.pactar(30, continuar=True), self.pactar(30, actor=self.gerente, continuar=True), primera="a")
        )
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Suministro.objects.count(), 2)
        self.assertEqual(sorted(s.numero for s in Suministro.objects.all()), sorted(set(s.numero for s in Suministro.objects.all())))
