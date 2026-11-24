# Pruebas de concurrencia de la cancelación de una cosecha (COM-04a, paso 6; docs/casos_de_uso/produccion/cancelar_orden.md, «Comercial 1: cosechas»,
# «Pruebas»): cancelar contra concretar la misma cosecha, contra modificarla y (COM-04c) contra la decisión del cliente sobre el mismo detalle. Dos hilos, dos conexiones, el orden fijado con ``primera``. La cancelación toma, en el orden de
# `docs/patrones/bloqueos.md` («Cosecha y cámara»), las cuentas → el invernadero → las variedades → los sectores → los lotes y las partidas → el contrato y su
# detalle → la cosecha → su reserva y sus líneas; la fila de la cosecha pone en fila a las demás operaciones sobre esa reserva.

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleVenta, EnlaceCliente, ReservaStock
from comercial.servicios import cosechas, faltantes
from comercial.servicios.cosechas import DatosDeConcrecion, DatosDeModificacion
from comercial.tests.fabricas import compra_venta, cosecha_manual, detalle, enlace as un_enlace, escenario_comercial, verificar_invariantes_de_reservas
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Cosecha, Lote
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar

HOY = timezone.localdate()


@tag("concurrencia")
class CancelarCosechaConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self):
        """El escenario sin Georef, un lote de 100 y una cosecha con contrato (venta con retiro de 50) que reserva 30."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 100)
        self.venta = compra_venta(self.e, dias=10, modalidad="retiro", retiro=self.e.invernadero)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=self.detalle, dias=5)
        self.huella = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella
        self.addCleanup(verificar_invariantes_de_reservas)

    def cancelar(self):
        return lambda: cosechas.cancelar_cosecha(self.e.agronomo, self.cosecha.pk, "Se cancela", self.huella)

    def concretar(self):
        datos = DatosDeConcrecion(cantidades=((self.lote.pk, self.e.sectores["maduracion"].pk, 30),))
        return lambda: cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)

    def modificar(self):
        datos = DatosDeModificacion(fecha_programada=HOY + timedelta(days=5), prioridad="alta", descripcion="", lotes=((self.lote.pk, 30),))
        return lambda: cosechas.modificar_cosecha(self.e.agronomo, self.cosecha.pk, datos, cosechas.huella_de(Cosecha.objects.get(pk=self.cosecha.pk)))

    def pendiente_con_enlace(self):
        """El detalle de la cosecha pasa a «pendiente de decisión» (la cosecha reserva 30 de 50) con el enlace del cliente; la huella se toma después."""
        self.armar()
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="pendiente_decision", fecha_pendiente_decision=HOY)
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="pendiente_decision")
        self.enlace, _ = un_enlace(self.venta)
        self.huella = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella

    def rechazar(self):
        return lambda: faltantes.registrar_decision(self.enlace.pk, {self.detalle.pk: "rechazar"}, {self.detalle.pk: 30})

    def test_regla_cancelar_contra_la_decision_del_cliente_gana_la_decision_y_la_cosecha_ya_no_esta_a_realizar(self):
        """COM-DCD-FLT, requisito especial: con la decisión (rechazar) primero, cancela la cosecha; la cancelación del Agrónomo recibe `orden_no_a_realizar` (8a) y la cosecha queda cancelada UNA vez."""
        self.pendiente_con_enlace()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.rechazar(), self.cancelar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "cancelada")
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "rechazado")

    def test_regla_cancelar_primero_y_la_decision_del_cliente_recibe_el_enlace_reemplazado(self):
        """Con la cancelación primero, el detalle (que ya esperaba) sigue el camino de faltante (8d) con un enlace nuevo; la decisión sobre el viejo recibe `enlace_no_sirve`."""
        self.pendiente_con_enlace()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.rechazar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("enlace_no_sirve", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(EnlaceCliente.objects.get(pk=self.enlace.pk).estado, "reemplazado")
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_regla_cancelar_contra_concretar_gana_el_primero_y_la_reserva_queda_coherente(self):
        """8a: con la cancelación primero, la concreción recibe `orden_no_a_realizar` y el lote no se toca; la reserva queda «liberada» y sin cosechado."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.concretar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 100)
        self.assertEqual(ReservaStock.objects.get(cosecha=self.cosecha).estado_reserva, "liberada")
        self.assertEqual(list(DetalleReserva.objects.values_list("cantidad_cosechada", flat=True)), [None])

    def test_regla_cancelar_contra_modificar_la_misma_cosecha(self):
        """Con la modificación primero, la cancelación ve la huella cambiada y recibe `cosecha_cambio` (8b): quien cancela vuelve a mirar el resumen; con
        la cancelación primero, la modificación recibe `cosecha_resuelta` (10a). En los dos casos queda una sola operación registrada."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.modificar(), self.cancelar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("cosecha_cambio", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "a_realizar")

    def test_regla_cancelar_primero_y_la_modificacion_ve_la_cosecha_resuelta(self):
        """El orden inverso: la cancelación gana; la modificación recibe `cosecha_resuelta`."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.modificar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("cosecha_resuelta", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).estado_orden, "cancelada")
