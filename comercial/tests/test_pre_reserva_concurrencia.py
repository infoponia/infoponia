# Pruebas de concurrencia de PROD-PRR-SUM (COM-03b, paso 4; docs/casos_de_uso/produccion/pre_reserva.md, «Concurrencia»): una pre-reserva contra una
# compra-venta por el último stock de un lote, una pre-reserva contra una modificación del mismo contrato (COM-MOD-SUM) y dos corridas del paso
# a la vez. Orden de bloqueos (docs/patrones/stock_maduro.md, sección 3): cuentas → invernaderos → variedades → lotes y partidas → el
# `Suministro` y su detalle. Dos hilos, dos conexiones, el orden fijado con ``primera``. Son ``TransactionTestCase``: sin Georef de la
# migración (el cliente tiene una dirección en la localidad propia que arma `geografia_propia`). Todas terminan verificando los invariantes de
# las reservas y de los suministros. Nunca un error 500: el que pierde recibe un rechazo claro (o, en el paso, deja su alerta).

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import AlertaComercial, CompraVenta, DetalleSuministro, ReservaStock
from comercial.servicios import compra_ventas, suministros
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.tests.fabricas import (
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Alerta, Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar

TIPO = "comercial_periodo_sin_cobertura"


@tag("concurrencia")
class PreReservaConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Las tres de «Concurrencia» de «Cómo se aplica» de PROD-PRR-SUM (y dos corridas sin stock, que no duplican alertas)."""

    def armar(self, cantidad_de_stock=100, cantidad=30, periodo=7):
        """Un contrato con un detalle de ``cantidad`` plantas cada ``periodo`` días (el primero dentro de 3 días) y un lote de
        ``cantidad_de_stock`` (0: ninguno)."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, cantidad_de_stock) if cantidad_de_stock else None
        localidad = Localidad.objects.get(id_georef="99001001").pk
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=localidad).direccion
        self.s = suministro(self.e)
        self.d = detalle_suministro(self.s, self.e.variedad, direccion=self.direccion, cantidad=cantidad, periodo=periodo, primera_en_dias=3)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    def pre_reservar(self):
        """Una operación que corre el paso diario 40 con la fecha de hoy."""
        from comercial.servicios import pre_reserva

        return lambda: pre_reserva.pre_reservar_suministros(timezone.localdate())

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

    def modificar_cantidad(self):
        """Una operación que modifica la cantidad por período del detalle (rige desde el primer período fuera de la ventana)."""
        cambios = suministros.CambiosDeSuministro(
            detalles=[suministros.CambioDeDetalle(detalle_id=self.d.pk, accion="modificar", cantidad="25")]
        )
        huella = suministros.huella_de(type(self.s).objects.get(pk=self.s.pk))
        return lambda: suministros.modificar_suministro(self.e.vendedor, self.s.pk, cambios, huella)

    def reservas_del_suministro(self):
        return ReservaStock.objects.filter(detalle_suministro__isnull=False)

    def test_regla_una_pre_reserva_primero_y_una_venta_por_el_ultimo_stock_gana_la_pre_reserva(self):
        """Concurrencia 1: un lote de 50; el período del suministro pide 50 y una venta pide 50. Con la pre-reserva primero, reserva las 50 y la
        venta, al esperar el lote y releer, recibe `stock_insuficiente`; no queda nada de la venta."""
        self.armar(50, cantidad=50, periodo=300)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pre_reservar(), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("stock_insuficiente", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((self.reservas_del_suministro().count(), CompraVenta.objects.count()), (1, 0))
        self.assertEqual(Alerta.objects.filter(tipo_alerta=TIPO).count(), 0)

    def test_regla_una_venta_primero_y_una_pre_reserva_por_el_ultimo_stock_gana_la_venta(self):
        """Concurrencia 1 en el orden inverso: se registra la venta y la pre-reserva no lanza nada: no reserva (no hay stock) y deja la alerta
        «período sin cobertura completa» con las 50 plantas que faltan, una sola vez."""
        self.armar(50, cantidad=50, periodo=300)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pre_reservar(), self.vender(50), primera="b"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual((self.reservas_del_suministro().count(), CompraVenta.objects.count()), (0, 1))
        (alerta,) = Alerta.objects.filter(tipo_alerta=TIPO)
        self.assertEqual(AlertaComercial.objects.get(alerta=alerta).cantidad_sin_cubrir, 50)

    def comprobar_pre_reserva_y_modificacion(self, primera):
        """Concurrencia 2 («La modificación se serializa con la pre-reserva diaria»): las dos terminan sin error. El sucesor nace fuera de la
        ventana: no tiene reservas, y las reservas de los períodos de la ventana (si ya se hicieron) siguen con el detalle que las reservó.
        Los invariantes cierran la prueba."""
        self.armar(200, cantidad=10, periodo=7)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pre_reservar(), self.modificar_cantidad(), primera=primera))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=self.d)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=sucesor).count(), 0)
        self.assertTrue(all(r.detalle_suministro_id == self.d.pk for r in self.reservas_del_suministro()))

    def test_regla_una_pre_reserva_primero_y_una_modificacion_del_mismo_contrato_se_ponen_en_fila(self):
        """Concurrencia 2 con la pre-reserva primero: la pre-reserva queda detenida con el primer período ya escrito (una transacción por
        período) y la modificación espera el contrato; el primer período queda reservado con el detalle original. El segundo es de otra
        transacción: puede quedar antes o después de la modificación (D-64, punto 8: hasta COM-04a, un detalle finalizado no se retoma)."""
        self.comprobar_pre_reserva_y_modificacion("a")
        self.assertGreaterEqual(self.reservas_del_suministro().count(), 1)

    def test_regla_una_modificacion_primero_y_una_pre_reserva_del_mismo_contrato_se_ponen_en_fila(self):
        """Concurrencia 2 con la modificación primero: el detalle original queda «finalizado» y la pre-reserva, que hasta COM-04a toma solo
        detalles vigentes (decisión del 24/11/2026, D-64 punto 8), relee el contrato y no reserva sus períodos: nunca reserva uno del sucesor
        ni de una fecha que el detalle ya no tiene."""
        self.comprobar_pre_reserva_y_modificacion("b")

    def test_regla_dos_corridas_del_paso_a_la_vez_ningun_periodo_queda_con_mas_reservas_que_su_cantidad(self):
        """Concurrencia 3: dos corridas a la vez; la segunda, al releer después de bloquear, ve la cantidad sin cubrir en 0. Cada uno de los dos
        períodos de la ventana queda con una sola reserva de 30 (nunca 60); entre las dos corridas crean dos reservas en total."""
        self.armar(100, cantidad=30, periodo=7)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pre_reservar(), self.pre_reservar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        fechas = [r.fecha_entrega_reserva for r in self.reservas_del_suministro()]
        self.assertEqual(len(fechas), len(set(fechas)))
        self.assertEqual(self.reservas_del_suministro().count(), 2)
        self.assertEqual(sum(r.creados for r in exitos), 2)

    def test_regla_dos_corridas_sin_stock_dejan_una_sola_alerta_por_periodo(self):
        """Concurrencia 3 con alertas: sin ninguna planta disponible, dos corridas a la vez dejan una alerta por período (la unicidad la garantiza
        el bloqueo del invernadero) y un solo aviso al Vendedor por período."""
        from core.models import Notificacion

        self.armar(0, cantidad=30, periodo=7)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.pre_reservar(), self.pre_reservar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual((Alerta.objects.filter(tipo_alerta=TIPO).count(), AlertaComercial.objects.count()), (2, 2))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo="Período sin cobertura completa").count(), 2)
