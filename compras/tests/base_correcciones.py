# Andamiaje compartido por las pruebas de la corrección de recepciones y de los reclamos de CMP-06 (no tiene pruebas propias): ``CorreccionBase`` agrega, sobre el escenario de ``PagosBase``
# (la orden aprobada de Ana con A en Norte y B en Norte 2, el Contador y un ejercicio abierto), los auxiliares para corregir, rechazar y mirar lo que cambió.
#
# Montos del escenario (D-89): Fertilizante 10 kg a $100,00 (control de vencimiento), Maceta 20 u a $200,00 (A) y Tomate 8 u a $80,00 (B).

from django.core import mail

from compras.errores import ErrorDeCompras
from compras.models import AlertaCompras, CorreccionRecepcion, DetalleCorreccionRecepcion, DetalleRecepcion, Pago, ReclamoProveedor
from compras.tests.base_pagos import D, PagosBase
from contabilidad.models import MovimientoContable
from inventario.models import LoteInsumo
from core.models import RegistroAuditoria
from inventario.tests.fabricas import perezoso
from maestros.models import Alerta

correcciones = perezoso("compras.servicios.correcciones")
reclamos = perezoso("compras.servicios.reclamos")


class CorreccionBase(PagosBase):
    """Ver el encabezado del archivo. ``corregir`` llama a ``registrar_correccion`` con los correos ejecutados; ``lineas`` es ``[(DetalleRecepcion | id, cantidad)]``."""

    def pares(self, lineas):
        return [(getattr(d, "pk", d), D(str(c))) for d, c in lineas]

    def corregir(self, actor, recepcion, lineas, observacion=""):
        """``registrar_correccion`` con los correos ejecutados; devuelve la ``CorreccionRecepcion``."""
        with self.captureOnCommitCallbacks(execute=True):
            return correcciones.registrar_correccion(actor, recepcion.pk, self.pares(lineas), observacion)

    def error_de_correccion(self, actor, recepcion, lineas, observacion="", clase=ErrorDeCompras):
        """La excepción de ``clase`` que lanza ``registrar_correccion`` (falla la prueba si no lanza ninguna)."""
        with self.assertRaises(clase) as contexto:
            with self.captureOnCommitCallbacks(execute=True):
                correcciones.registrar_correccion(actor, recepcion.pk, self.pares(lineas), observacion)
        return contexto.exception

    def detalle_de(self, recepcion, detalle_orden):
        """El ``DetalleRecepcion`` de la línea ``detalle_orden`` en esa recepción."""
        return DetalleRecepcion.objects.get(recepcion=recepcion, detalle_orden=detalle_orden)

    def recibido(self, detalle_orden):
        """Σ lo que ingresó de la línea en todas las recepciones (lo que ven la ficha y el pago)."""
        return sum((d.cantidad_recibida_detalle for d in DetalleRecepcion.objects.filter(detalle_orden=detalle_orden)), D("0"))

    def disponible(self, lote):
        return LoteInsumo.objects.get(pk=lote.pk).cantidad_disponible

    def instantanea_de_correcciones(self):
        """Lo que no debe cambiar si la corrección se rechaza o falla: todo lo de la recepción (``instantanea``), las correcciones, lo recibido y lo disponible de cada lote."""
        return (
            self.instantanea(),
            CorreccionRecepcion.objects.count(),
            DetalleCorreccionRecepcion.objects.count(),
            tuple(DetalleRecepcion.objects.order_by("id").values_list("cantidad_recibida_detalle", flat=True)),
            tuple(LoteInsumo.objects.order_by("id").values_list("cantidad_disponible", flat=True)),
            Pago.objects.count(),
        )

    def sin_cambios_de_correcciones(self, antes):
        self.assertEqual(self.instantanea_de_correcciones(), antes)

    def asiento_de_la_correccion(self, correccion):
        from contabilidad.models import AsientoContable

        return AsientoContable.objects.get(origen_id=correccion.pk)

    def saldo_de_proveedores(self):
        """Haber − Debe de la cuenta Proveedores en todos los asientos (lo que se le debe, en total)."""
        from contabilidad import cuentas

        total = D("0.00")
        for m in MovimientoContable.objects.filter(cuenta__codigo_cuenta=cuentas.PROVEEDORES):
            total += m.importe_movimiento if m.tipo_movimiento == "H" else -m.importe_movimiento
        return total

    def correos_nuevos(self, antes):
        return mail.outbox[antes:]


DANADA = "mercaderia_danada"


class ReclamoBase(CorreccionBase):
    """Sobre ``CorreccionBase``: ``recepcion_con_reclamo`` recibe 4 kg de Fertilizante con 2 dañados (dos inconvenientes si se pide) y deja el reclamo **sin emitir** que CMP-04 genera, con su alerta del Gerente."""

    def recepcion_con_reclamo(self, descripcion="Cajas rotas"):
        """Devuelve ``(recepción, reclamo)``: el reclamo nace abierto y sin emitir."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, descripcion)])])
        return recepcion, ReclamoProveedor.objects.get(recepcion=recepcion)

    def alerta_de(self, reclamo):
        return Alerta.objects.get(pk=AlertaCompras.objects.get(reclamo=reclamo).alerta_id)

    def emitir(self, actor, reclamo):
        """``emitir_reclamo`` con los correos ejecutados; devuelve el reclamo."""
        with self.captureOnCommitCallbacks(execute=True):
            return reclamos.emitir_reclamo(actor, reclamo.pk)

    def cerrar(self, actor, reclamo):
        """``cerrar_reclamo``; devuelve el reclamo."""
        with self.captureOnCommitCallbacks(execute=True):
            return reclamos.cerrar_reclamo(actor, reclamo.pk)

    def error_de_reclamo(self, funcion, actor, reclamo, clase=ErrorDeCompras):
        """La excepción de ``clase`` que lanza ``reclamos.<funcion>`` (``"emitir_reclamo"`` o ``"cerrar_reclamo"``)."""
        with self.assertRaises(clase) as contexto:
            with self.captureOnCommitCallbacks(execute=True):
                getattr(reclamos, funcion)(actor, reclamo.pk)
        return contexto.exception

    def instantanea_de_reclamos(self):
        """Lo que no debe cambiar si la emisión o el cierre se rechazan o fallan: los reclamos, las alertas, la auditoría, el stock, los pagos y los correos."""
        return (
            tuple(ReclamoProveedor.objects.order_by("id").values_list("gerente_id", "fecha_reclamo", "estado_reclamo")),
            tuple(Alerta.objects.order_by("id").values_list("estado_alerta", flat=True)),
            RegistroAuditoria.objects.count(),
            len(mail.outbox),
            self.instantanea(),
        )

    def sin_cambios_de_reclamos(self, antes):
        self.assertEqual(self.instantanea_de_reclamos(), antes)
