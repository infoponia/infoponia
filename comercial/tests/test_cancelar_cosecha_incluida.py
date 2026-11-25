# Pruebas de `cancelar_cosecha_incluida` (COM-04a, paso 6; docs/casos_de_uso/produccion/cancelar_orden.md, «Comercial 1: cosechas», última decisión de aplicación):
# la cancelación de una cosecha como parte de otro caso de uso (COM-DCD-FLT en COM-04c; COM-CNL-CVT y las entregas desde COM-05), igual que
# `produccion.ordenes.cancelar_orden_incluida`. El contrato de `cancelar_cosecha_incluida` está en `test_prod_cnl_ord_cosechas.py`. Fuente: D-36, D-42 y D-64.

from django.core.exceptions import ValidationError
from django.db import transaction

from comercial.models import DetalleVenta
from comercial.servicios import cosechas
from comercial.tests.fabricas import cosecha_manual
from comercial.tests.test_prod_cnl_ord_cosechas import Base
from core.models import Notificacion, RegistroAuditoria
from produccion.models import Cosecha, OrdenTrabajo
from produccion.tests.fabricas import lote_maduro

from django.utils import timezone

HOY = timezone.localdate()


class CancelarCosechaIncluidaTests(Base):
    """`cancelar_cosecha_incluida(actor, cosecha, motivo, *, recubrir=True, avisar=True)`: la usan COM-DCD-FLT (COM-04c) y, desde COM-05, COM-CNL-CVT y la
    cancelación de entregas. Ninguna función nueva que cancele cosechas duplica esta lógica."""

    def incluida(self, actor=None, **extra):
        with transaction.atomic():
            return cosechas.cancelar_cosecha_incluida(actor, self.releer(Cosecha, self.cosecha.pk), "Cancelada por la venta", **extra)

    def test_regla_con_actor_none_cancela_libera_y_devuelve_lo_afectado_sin_auditar(self):
        """Actúa InfoPonia (`actor=None`): cancela, libera la reserva y devuelve la cosecha, la reserva y lo creado, sin auditar (lo hace el llamador)."""
        antes = RegistroAuditoria.objects.count()
        resultado = self.incluida()
        self.assertEqual((resultado.cosecha.estado_orden, resultado.reserva.estado_reserva), ("cancelada", "liberada"))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).motivo_cancelacion, "Cancelada por la venta")

    def test_regla_con_recubrir_falso_no_llama_a_asignar_ni_al_camino_de_faltante(self):
        """COM-DCD-FLT: el detalle se rechazó; con `recubrir=False`, aunque haya stock, no se reserva nada ni cambia el detalle."""
        lote_maduro(self.e, 100)
        resultado = self.incluida(recubrir=False)
        self.assertEqual((resultado.asignacion, resultado.sin_cubrir), (None, 0))
        self.assertEqual(Cosecha.objects.count(), 1)
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, "abierto")

    def test_regla_con_recubrir_vuelve_a_cubrir_como_la_cancelacion_del_agronomo(self):
        """Con `recubrir=True` (por omisión), el mismo recubrimiento que `cancelar_cosecha`."""
        lote_maduro(self.e, 100)
        resultado = self.incluida()
        self.assertEqual(resultado.asignacion.cubierta, 30)

    def test_regla_con_avisar_se_avisa_al_capataz_y_al_agronomo_y_sin_avisar_a_nadie(self):
        """Postcondición j de COM-DCD-FLT: con `avisar=True`, el Capataz y el Agrónomo del invernadero reciben el aviso con el motivo; con `False`, nadie."""
        self.incluida(avisar=False)
        self.assertFalse(Notificacion.objects.exists())
        otra = cosecha_manual(self.e, [(self.lote, 5)], dias=2)
        with transaction.atomic():
            cosechas.cancelar_cosecha_incluida(None, self.releer(Cosecha, otra.pk), "Otro motivo", avisar=True)
        self.assertEqual(
            {n.destinatario_id for n in Notificacion.objects.all()}, {self.e.capataz.pk, self.e.agronomo.pk}
        )

    def test_regla_con_avisar_agronomo_falso_solo_se_avisa_al_capataz(self):
        """COM-RSV-SUM, paso 4.1 (COM-07b): con `avisar=True` y `avisar_agronomo=False` solo el Capataz recibe el aviso (el Agrónomo recibe uno solo por invernadero, armado por la
        resolución). Por omisión (`True`) el aviso a los dos no cambia."""
        self.incluida(avisar=True, avisar_agronomo=False)
        self.assertEqual({n.destinatario_id for n in Notificacion.objects.all()}, {self.e.capataz.pk})

    def test_regla_con_avisar_falso_el_argumento_avisar_agronomo_no_avisa_a_nadie(self):
        """`avisar=False` manda sobre `avisar_agronomo`: nadie recibe el aviso aunque el segundo valga `True`."""
        self.incluida(avisar=False, avisar_agronomo=True)
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_no_abre_una_transaccion_propia(self):
        """Corre en la transacción de su llamador: sin ella, `RuntimeError` y la cosecha sigue «a realizar»."""
        from unittest import mock

        with mock.patch.object(transaction, "get_autocommit", return_value=True), self.assertRaises(RuntimeError):
            cosechas.cancelar_cosecha_incluida(None, self.releer(Cosecha, self.cosecha.pk), "x")
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).estado_orden, "a_realizar")

    def test_regla_una_cosecha_que_ya_no_esta_a_realizar_se_rechaza(self):
        """Solo cancela cosechas «a realizar»: si no, `orden_no_a_realizar`."""
        OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        with self.assertRaises(ValidationError) as rechazo:
            self.incluida()
        self.assertEqual(next(e for lista in rechazo.exception.error_dict.values() for e in lista).code, "orden_no_a_realizar")

    def test_regla_el_motivo_largo_se_recorta_como_cancelar_orden_incluida(self):
        """Mismo contrato que `produccion.ordenes.cancelar_orden_incluida`: el motivo ya armado se recorta a 300 con «…» (no lanza `motivo_largo`)."""
        with transaction.atomic():
            cosechas.cancelar_cosecha_incluida(None, self.releer(Cosecha, self.cosecha.pk), "m" * 400, recubrir=False, avisar=False)
        motivo = self.releer(Cosecha, self.cosecha.pk).motivo_cancelacion
        self.assertEqual((len(motivo), motivo[-1]), (300, "…"))


class CancelarCosechaIncluidaDesdeCompraVentaTests(Base):
    """Desde COM-CNL-CVT (COM-05b): la cosecha de una venta que se cancela se cancela con `recubrir=False` y el aviso al Capataz y al Agrónomo, con el motivo de la venta."""

    def test_regla_la_cancelacion_de_la_venta_cancela_la_cosecha_sin_recubrir_y_avisa(self):
        """El detalle se cancela con la venta: no hay nada que volver a cubrir (aunque haya stock) y el Capataz y el Agrónomo reciben el aviso con el motivo."""
        from comercial.servicios import compra_ventas
        from comercial.servicios.compra_ventas import DatosDeCancelacionDeVenta

        lote_maduro(self.e, 100)
        venta = self.detalle.compra_venta
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, venta.pk)
        compra_ventas.cancelar_compra_venta(self.e.vendedor, venta.pk, DatosDeCancelacionDeVenta("cliente_no_retiro"), datos.huella)
        cosecha = self.releer(Cosecha, self.cosecha.pk)
        self.assertEqual((cosecha.estado_orden, cosecha.motivo_cancelacion), ("cancelada", f"Se canceló la compra-venta {venta.codigo}: el cliente no retiró."))
        self.assertEqual(Cosecha.objects.count(), 1)  # sin cosecha nueva
        self.assertEqual({n.destinatario_id for n in Notificacion.objects.all()}, {self.e.capataz.pk, self.e.agronomo.pk})
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, "cancelado")
