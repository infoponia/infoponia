# Andamiaje compartido por las pruebas de la recepción, del cierre con faltante y de la concurrencia de CMP-04 (no tiene pruebas propias): ``RecepcionBase`` arma el escenario de
# ``EscenarioDeRecepcion`` y los auxiliares para registrar, rechazar y mirar lo que cambió.

from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings

from compras.errores import ErrorDeCompras
from compras.models import (
    AlertaCompras,
    DetalleOrdenCompra,
    DetalleRecepcion,
    DetalleRecepcionMovimiento,
    InconvenienteRecepcion,
    OrdenCompra,
    Recepcion,
    ReclamoProveedor,
)
from compras.tests.fabricas import EscenarioDeRecepcion
from contabilidad.models import AsientoContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.models import RegistroAuditoria
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from maestros.models import Alerta

recepciones = perezoso("compras.servicios.recepciones")
D = Decimal
BAJO_MINIMO = "inv_insumo_bajo_minimo"
TIPO_DE_ALERTA = "compras_recepcion_con_inconvenientes"
DANADA = "mercaderia_danada"


@override_settings(CORREO_CONFIGURADO=True)
class RecepcionBase(PlanDeCuentasMixin, ConDatosDeInventario, EscenarioDeRecepcion, TestCase):
    """Ver ``EscenarioDeRecepcion``: Ana recibe lo de la orden aprobada (A en Norte, B en Norte 2). Los auxiliares arman los datos y ejecutan los correos."""

    def setUp(self):
        self.armar()

    def linea(self, detalle, cantidad=None, vence=None, inconvenientes=(), partes=None):
        """Una ``LineaRecibida``: ``cantidad`` (con su ``vence``) forma una sola parte; ``partes`` pasa varias; sin ninguna, la línea llegó en 0."""
        if partes is None:
            partes = [(D(str(cantidad)), vence)] if cantidad else []
        return recepciones.LineaRecibida(detalle.pk, list(partes), [(t, D(str(c)), d) for t, c, d in inconvenientes])

    def datos(self, lineas, observaciones="", proveedor=None, invernadero=None, orden=None):
        """Los datos de una recepción de A en Norte (o del ``proveedor`` y el ``invernadero`` que se indiquen)."""
        return recepciones.DatosDeRecepcion(
            (orden or self.orden).pk, (proveedor or self.proveedor).pk, (invernadero or self.norte).pk, list(lineas), observaciones
        )

    def registrar(self, actor, lineas, **kwargs):
        """``registrar_recepcion`` con los correos ejecutados; devuelve la ``Recepcion``."""
        with self.captureOnCommitCallbacks(execute=True):
            return recepciones.registrar_recepcion(actor, self.datos(lineas, **kwargs))

    def error(self, actor, lineas, **kwargs):
        """El ``ErrorDeCompras`` que lanza ``registrar_recepcion`` (falla la prueba si no lanza ninguno)."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            with self.captureOnCommitCallbacks(execute=True):
                recepciones.registrar_recepcion(actor, self.datos(lineas, **kwargs))
        return contexto.exception

    def instantanea(self):
        """Lo que no debe cambiar si la recepción se rechaza: todo lo que la recepción crea o modifica, y la auditoría."""
        return (
            Recepcion.objects.count(),
            DetalleRecepcion.objects.count(),
            DetalleRecepcionMovimiento.objects.count(),
            InconvenienteRecepcion.objects.count(),
            ReclamoProveedor.objects.count(),
            AlertaCompras.objects.count(),
            Alerta.objects.count(),
            LoteInsumo.objects.count(),
            MovimientoInsumo.objects.count(),
            AsientoContable.objects.count(),
            RegistroAuditoria.objects.count(),
            tuple(InsumoInvernadero.objects.order_by("id").values_list("cant_transito_insumo", flat=True)),
            tuple(DetalleOrdenCompra.objects.order_by("id").values_list("estado_detalle_orden", flat=True)),
            OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra,
            len(mail.outbox),
        )

    def sin_cambios(self, antes):
        self.assertEqual(self.instantanea(), antes)

    def transito(self, iin):
        return InsumoInvernadero.objects.get(pk=iin.pk).cant_transito_insumo

    def stock_de(self, iin):
        return stock.stock_actual_de([iin.pk])[iin.pk]

    def estado_de(self, detalle):
        return DetalleOrdenCompra.objects.get(pk=detalle.pk).estado_detalle_orden

    def estado_de_la_orden(self):
        return OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra

    def asiento_de(self, recepcion):
        return AsientoContable.objects.get(origen_id=recepcion.pk)

    def movimientos_de(self, asiento):
        """``[(código de cuenta, Debe o Haber, importe)]`` del asiento, en el orden en que se crearon."""
        return [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta").order_by("id")]

    def lotes_nuevos(self, iin):
        return list(LoteInsumo.objects.filter(insumo_invernadero=iin, es_faltante_sin_lote=False).order_by("id"))
