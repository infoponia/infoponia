# Pruebas de concurrencia de COM-PCT-SUM (COM-03a, paso 4; docs/casos_de_uso/comercial/suministro.md, «Concurrencia»): un pacto y una
# compra-venta por el último stock de un lote, un pacto contra la baja del cliente y dos pactos del mismo cliente con el mismo par. Orden de
# bloqueos (docs/patrones/stock_maduro.md, sección 3): cuentas → invernaderos → cliente → variedades → lotes y partidas → filas del contrato.
# Dos hilos, dos conexiones, el orden fijado con ``primera``. Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una
# dirección en la localidad propia que arma `geografia_propia`). Todas terminan verificando los invariantes de las reservas y de los
# suministros. Nunca un error 500: el que pierde recibe un rechazo claro.

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Cliente, CompraVenta, DetalleSuministro, ReservaStock, Suministro
from comercial.servicios import clientes, compra_ventas, suministros
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.servicios.suministros import DatosDeSuministro, RenglonDeSuministro
from comercial.tests.fabricas import (
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    partida,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import RegistroAuditoria
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


@tag("concurrencia")
class ModificacionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Las de «Concurrencia» de COM-MOD-SUM (COM-03b, paso 3): dos modificaciones del mismo contrato (la segunda recibe `contrato_cambio`) y una
    modificación con un detalle nuevo contra una compra-venta por el último stock. Orden de bloqueos: cuentas → invernaderos → cliente →
    variedades → lotes y partidas → `Suministro` y detalles (`docs/patrones/stock_maduro.md`, sección 3). La de una modificación contra la
    pre-reserva del mismo contrato va en el paso 4 (`test_pre_reserva_concurrencia.py`), cuando exista el paso diario 40."""

    def armar(self, cantidad_de_stock=50):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.gerente = crear_gerente()
        self.lote = lote_maduro(self.e, cantidad_de_stock)
        localidad = Localidad.objects.get(id_georef="99001001").pk
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=localidad).direccion
        self.otra_direccion = direccion_de_cliente(self.e.cliente, localidad_id=localidad).direccion
        self.s = suministro(self.e)
        self.d = detalle_suministro(self.s, self.e.variedad, direccion=self.direccion, cantidad=1, periodo=30, primera_en_dias=40)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    def huella(self):
        return suministros.huella_de(Suministro.objects.get(pk=self.s.pk))

    def modificar_tolerados(self, valor, huella, actor=None):
        """Una operación que cambia los incumplimientos tolerados con la ``huella`` que vio al abrir la pantalla."""
        cambios = suministros.CambiosDeSuministro(tolerados=str(valor))
        return lambda: suministros.modificar_suministro(actor or self.e.vendedor, self.s.pk, cambios, huella)

    def agregar_detalle(self, cantidad, huella):
        """Una operación que agrega un detalle de ``cantidad`` plantas con un único período dentro de la ventana (el siguiente cae a los 35 días)."""
        hoy = timezone.localdate()
        nuevo = RenglonDeSuministro(
            indice=0, variedad_id=str(self.e.variedad.pk), direccion_id=str(self.otra_direccion.pk), cantidad=str(cantidad), periodo="30",
            primera_entrega=str(hoy + timedelta(days=5)), mecanismo="fijo", precio="100", plazo_entrega="1", indemnizacion_retraso="1",
            cantidad_minima="1", indemnizacion_faltante="1",
        )
        cambios = suministros.CambiosDeSuministro(nuevos=[nuevo])
        return lambda: suministros.modificar_suministro(self.e.vendedor, self.s.pk, cambios, huella)

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

    def test_regla_dos_modificaciones_del_mismo_contrato_la_segunda_recibe_contrato_cambio(self):
        """Requisito especial (10b): dos modificaciones con la misma huella; se ponen en fila por el `Suministro`. La primera se registra; la
        segunda, al volver a leer, ve otra huella y recibe `contrato_cambio` sin registrar nada. Nunca un error 500."""
        self.armar()
        huella = self.huella()
        exitos, rechazos, otros = separar(
            correr_a_la_vez(self.modificar_tolerados(5, huella), self.modificar_tolerados(6, huella, actor=self.gerente), primera="a")
        )
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("contrato_cambio", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Suministro.objects.get(pk=self.s.pk).incumplimientos_tolerados, 5)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_suministro").count(), 1)

    def test_regla_dos_modificaciones_en_el_orden_inverso_gana_la_otra(self):
        """El mismo choque con la otra primero: gana la segunda operación y la primera recibe `contrato_cambio`."""
        self.armar()
        huella = self.huella()
        exitos, rechazos, otros = separar(
            correr_a_la_vez(self.modificar_tolerados(5, huella), self.modificar_tolerados(6, huella, actor=self.gerente), primera="b")
        )
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("contrato_cambio", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Suministro.objects.get(pk=self.s.pk).incumplimientos_tolerados, 6)

    def test_regla_una_modificacion_con_detalle_nuevo_y_una_compra_venta_por_el_ultimo_stock(self):
        """Extensión 5b.3 y paso 10: un lote de 50; un detalle nuevo de 50 en la ventana y una venta por 50 (los dos vieron 50). Gana el primero;
        el otro espera el lote, relee y recibe `stock_insuficiente`; no queda nada de él."""
        self.armar(50)
        huella = self.huella()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.agregar_detalle(50, huella), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((DetalleSuministro.objects.filter(suministro=self.s).count(), CompraVenta.objects.count()), (2, 0))

    def test_regla_una_compra_venta_y_una_modificacion_con_detalle_nuevo_en_el_orden_inverso(self):
        """El mismo choque con la venta primero: se registra la venta y la modificación recibe `stock_insuficiente`; el contrato queda como estaba
        y no hay reservas suyas."""
        self.armar(50)
        huella = self.huella()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.agregar_detalle(50, huella), self.vender(50), primera="b"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((DetalleSuministro.objects.filter(suministro=self.s).count(), CompraVenta.objects.count()), (1, 1))
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro__isnull=False).count(), 0)


@tag("concurrencia")
class RescisionConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Las de «Concurrencia» de COM-RSC-SUM y COM-ANL-RSC (COM-03b, paso 5): una rescisión contra la pre-reserva del mismo contrato y contra una modificación, y
    el cierre diario contra dejar sin efecto la rescisión. «El paso 6 se serializa con la pre-reserva diaria, COM-MOD-SUM, COM-RSV-SUM y otras operaciones sobre el
    mismo contrato»: todas toman las cuentas y después el `Suministro`; el que llega segundo espera y relee. Nunca un error 500."""

    def armar(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.gerente = crear_gerente()
        self.lote = lote_maduro(self.e, 200)
        localidad = Localidad.objects.get(id_georef="99001001").pk
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=localidad).direccion
        self.s = suministro(self.e)
        self.d = detalle_suministro(self.s, self.e.variedad, direccion=self.direccion, cantidad=10, periodo=7, primera_en_dias=3)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    def rescindir(self):
        """Una operación que rescinde el contrato con lo que vio la ventana (leída antes, en este hilo)."""
        lectura = suministros.datos_de_rescision(self.gerente, self.s.pk)
        pedido = suministros.PedidoDeRescision(
            motivo="a_pedido_del_cliente", descripcion="", fecha_acuerdo=str(timezone.localdate()), acuerdo="1"
        )
        return lambda: suministros.rescindir_suministro(self.gerente, self.s.pk, pedido, lectura.huella, lectura.conservados)

    def pre_reservar(self, dias=0):
        """Una operación que corre el paso diario 40 con la fecha de hoy + ``dias``."""
        from comercial.servicios import pre_reserva

        return lambda: pre_reserva.pre_reservar_suministros(timezone.localdate() + timedelta(days=dias))

    def modificar_cantidad(self):
        """Una operación que modifica la cantidad por período del detalle con la huella de ahora."""
        cambios = suministros.CambiosDeSuministro(
            detalles=[suministros.CambioDeDetalle(detalle_id=self.d.pk, accion="modificar", cantidad="25")]
        )
        huella = suministros.huella_de(Suministro.objects.get(pk=self.s.pk))
        return lambda: suministros.modificar_suministro(self.e.vendedor, self.s.pk, cambios, huella)

    def anular(self):
        """Una operación que deja sin efecto la rescisión con la huella de ahora."""
        huella = suministros.huella_de(Suministro.objects.get(pk=self.s.pk))
        return lambda: suministros.dejar_sin_efecto_rescision(self.gerente, self.s.pk, "Siguen con el contrato", huella)

    def cerrar(self):
        """Una operación que corre el cierre diario (paso 35) el día siguiente a la última entrega conservada."""
        return lambda: suministros.cerrar_rescisiones(timezone.localdate() + timedelta(days=11))

    def fechas_reservadas(self):
        return sorted({r.fecha_entrega_reserva for r in ReservaStock.objects.filter(detalle_suministro=self.d)})

    def test_regla_una_rescision_primero_y_una_pre_reserva_posterior_no_reserva_lo_que_la_rescision_dejo_afuera(self):
        """Concurrencia 1 con la rescisión primero: la pre-reserva de dentro de 7 días (ventana hasta el día 21) seleccionó los períodos de los días 10 y 17
        antes de que la rescisión confirmara; al esperar el contrato y releerlo, ve la fecha de fin del detalle (día 10) y no reserva el del día 17."""
        self.armar()
        hoy = timezone.localdate()
        partida(self.lote, disponible=100, fecha_limite=hoy + timedelta(days=60))
        exitos, rechazos, otros = separar(correr_a_la_vez(self.rescindir(), self.pre_reservar(7), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Suministro.objects.get(pk=self.s.pk).fecha_ultima_entrega_rescision, hoy + timedelta(days=10))
        self.assertEqual(self.fechas_reservadas(), [hoy + timedelta(days=10)])

    def test_regla_una_pre_reserva_primero_y_una_rescision_se_ponen_en_fila(self):
        """Concurrencia 1 con la pre-reserva primero: la pre-reserva deja escrito su primer período (una transacción por período) y la rescisión espera la cuenta
        del Vendedor; las dos terminan, el período ya reservado queda y no hay reservas fuera del calendario (los invariantes lo verifican)."""
        self.armar()
        hoy = timezone.localdate()
        partida(self.lote, disponible=100, fecha_limite=hoy + timedelta(days=60))
        exitos, rechazos, otros = separar(correr_a_la_vez(self.rescindir(), self.pre_reservar(7), primera="b"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertIn(hoy + timedelta(days=10), self.fechas_reservadas())
        self.assertIsNotNone(Suministro.objects.get(pk=self.s.pk).motivo_rescision)

    def test_regla_una_rescision_primero_y_una_modificacion_recibe_rescision_acordada(self):
        """Concurrencia 2 con la rescisión primero: la modificación espera el contrato, lo relee con la rescisión acordada y recibe `rescision_acordada` (la
        resolución por mutuo acuerdo gana); no cambia ningún detalle."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.rescindir(), self.modificar_cantidad(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("rescision_acordada", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(DetalleSuministro.objects.filter(suministro=self.s).count(), 1)

    def test_regla_una_modificacion_primero_y_una_rescision_recibe_contrato_cambio(self):
        """Concurrencia 2 con la modificación primero: la rescisión (con la huella de antes) espera, ve otros detalles vigentes y recibe `contrato_cambio`; no
        queda ninguna rescisión y la ventana se vuelve a abrir."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.rescindir(), self.modificar_cantidad(), primera="b"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("contrato_cambio", codigos_del_rechazo(rechazos[0]))
        self.assertIsNone(Suministro.objects.get(pk=self.s.pk).motivo_rescision)

    def test_regla_el_cierre_primero_y_dejar_sin_efecto_recibe_contrato_cambio(self):
        """COM-ANL-RSC, regla 3: «se serializa con el cierre de la rescisión del mismo contrato». Con el cierre primero, el contrato pasa a «rescindido» y
        dejar sin efecto la rescisión, al releerlo, recibe `contrato_cambio`."""
        self.armar()
        suministros.rescindir_suministro(self.gerente, self.s.pk, suministros.PedidoDeRescision("a_pedido_del_cliente", "", str(timezone.localdate()), "1"), None, None)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cerrar(), self.anular(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("contrato_cambio", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Suministro.objects.get(pk=self.s.pk).estado_suministro, "rescindido")

    def test_regla_dejar_sin_efecto_primero_y_el_cierre_no_cierra_nada(self):
        """Con dejar sin efecto primero, el contrato vuelve a no tener rescisión y el cierre, al releerlo, no lo cierra (sigue «vigente»)."""
        self.armar()
        suministros.rescindir_suministro(self.gerente, self.s.pk, suministros.PedidoDeRescision("a_pedido_del_cliente", "", str(timezone.localdate()), "1"), None, None)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cerrar(), self.anular(), primera="b"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Suministro.objects.get(pk=self.s.pk).estado_suministro, "vigente")
        self.assertIsNone(Suministro.objects.get(pk=self.s.pk).motivo_rescision)
