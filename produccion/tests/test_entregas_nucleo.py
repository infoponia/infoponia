# Pruebas de lo que COM-04a deja hecho para la concreción de una entrega (COM-06a): `mermas.aplicar_merma_de_entrega`,
# `consumos.cerrar_reserva` y `consumos.registrar_consumo_de_orden`, con ÓRDENES SUELTAS de tipo `entrega` (`orden_suelta`, D-67 punto 1d).
# Las dos de `camara` de la sección 10 (`egresar_de_partida`, `devolver_a_partida`) están en `test_camara_nucleo.py`.
# Fuente: docs/api/produccion.md (sección 10), D-68 (puntos 2 y 3), COM-CNC-ENT (reglas «Merma de entrega» y «Envases»).

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from decimal import Decimal
from unittest import mock

from django.db import connections
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.errores import ErrorDeProduccion
from produccion.models import Consumo, Lote, Merma, MovimientoStock, ReservaInsumo
from produccion.servicios import consumos, mermas
from produccion.tests.fabricas import insumo_adicional, invernadero_con_produccion, lote_maduro, orden_suelta

HOY = timezone.localdate()


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):  # CON-04a: estos servicios asientan
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.envase = insumo_adicional(cls.e, nombre="Bolsa", stock=100, unidad="unidad", precio="1.50")

    def entrega(self, reservas=()):
        """Una orden suelta de tipo `entrega` del invernadero, con las reservas de insumo pedidas."""
        return orden_suelta(self.e.invernadero, "entrega", reservas=reservas)


class AplicarMermaDeEntregaTests(Base):
    def aplicar(self, orden, lote, cantidad=4, descripcion="", responsable=None):
        """Llama a `aplicar_merma_de_entrega`."""
        return mermas.aplicar_merma_de_entrega(orden, lote, cantidad, descripcion, responsable or self.e.capataz)

    def test_post_e_crea_la_merma_con_orden_lote_de_origen_sin_etapa_ni_sectores(self):
        """COM-CNC-ENT, postcondición e y D-68 punto 3: causa `dano_en_entrega`, la orden, el lote de origen (R144), el invernadero de la
        orden, sin etapa ni sectores, fecha y hora actuales y el responsable."""
        lote, orden = lote_maduro(self.e, 100), self.entrega()
        merma = Merma.objects.get(pk=self.aplicar(orden, lote, 4, "Se golpeó").pk)
        self.assertEqual(
            (merma.causa, merma.orden_id, merma.lote_id, merma.etapa_id, merma.invernadero_id, merma.cant_merma, merma.fecha_bitacora, merma.responsable_id),
            ("dano_en_entrega", orden.pk, lote.pk, None, self.e.invernadero.pk, 4, HOY, self.e.capataz.pk),
        )
        self.assertEqual((merma.tipo_evento, merma.sectores.count()), ("merma", 0))
        self.assertIn("Se golpeó", merma.descripcion_evento)

    def test_regla_no_toca_el_lote_ni_crea_movimiento_de_stock(self):
        """«No libera agujeros, porque el producto ya fue cosechado»: el lote (cantidad, costo, ocupaciones) no cambia y no hay `MovimientoStock`."""
        lote, orden = lote_maduro(self.e, 100), self.entrega()
        antes = list(lote.ocupaciones.values_list("cant_agujeros_ocupados", flat=True))
        self.aplicar(orden, lote)
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado, lote.estado_lote), (100, Decimal("100.00"), "activo"))
        self.assertEqual(list(lote.ocupaciones.values_list("cant_agujeros_ocupados", flat=True)), antes)
        self.assertFalse(MovimientoStock.objects.exists())

    def test_regla_sin_etapa_no_suma_a_la_merma_acumulada(self):
        """Regla 7 de 8.9: sin etapa, no suma a `merma_acumulada`."""
        lote = lote_maduro(self.e, 100)
        self.aplicar(self.entrega(), lote, 50)
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("0.00"))

    def test_ext_una_cantidad_que_no_es_mayor_que_cero_se_rechaza(self):
        """`cantidad_invalida` si `cantidad <= 0`."""
        for cantidad in (0, -1):
            with self.assertRaises(ErrorDeProduccion) as rechazo:
                self.aplicar(self.entrega(), lote_maduro(self.e, 10), cantidad)
            self.assertEqual(rechazo.exception.codigo, "cantidad_invalida")
        self.assertFalse(Merma.objects.exists())

    def test_regla_sin_transaccion_lanza_runtime_error_y_no_audita(self):
        """Contrato de núcleo: sin transacción, `RuntimeError`; con ella, ni auditoría ni aviso."""
        lote, orden = lote_maduro(self.e, 100), self.entrega()
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            self.aplicar(orden, lote)
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        self.aplicar(orden, lote)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))


class CerrarReservaTests(Base):
    """`consumos.cerrar_reserva` ya existe desde PRD-01 (la usa `concretar_siembra`): COM-06a la usa para los envases. D-68 punto 2."""

    def reserva(self, cantidad=10):
        """Una reserva «activa» de `cantidad` envases de una entrega."""
        orden = self.entrega(reservas=[(self.envase, cantidad)])
        return ReservaInsumo.objects.get(orden=orden)

    def test_post_consumida_si_lo_consumido_es_mayor_que_cero_y_cancelada_si_es_cero(self):
        """`consumida` si `reservada − devuelta > 0`; `cancelada` (con utilizada y devuelta cargadas) si no."""
        usada = consumos.cerrar_reserva(self.reserva(10), 8, 2)
        self.assertEqual((usada.estado, usada.cantidad_utilizada, usada.cantidad_devuelta), ("consumida", Decimal("8"), Decimal("2")))
        devuelta = consumos.cerrar_reserva(self.reserva(10), 0, 10)
        self.assertEqual((devuelta.estado, devuelta.cantidad_devuelta), ("cancelada", Decimal("10")))

    def test_ext_la_utilizada_y_la_devuelta_respetan_las_restricciones_de_prd_01(self):
        """`0 <= utilizada <= reservada` y `0 <= devuelta <= reservada − utilizada` (no cambian): si no, `cantidad_invalida`."""
        for utilizada, devuelta in ((11, 0), (-1, 0), (8, 3), (5, -1)):
            with self.subTest(utilizada=utilizada, devuelta=devuelta), self.assertRaises(ErrorDeProduccion) as rechazo:
                consumos.cerrar_reserva(self.reserva(10), utilizada, devuelta)
            self.assertEqual(rechazo.exception.codigo, "cantidad_invalida")

    def test_ext_una_reserva_que_ya_no_esta_activa_se_rechaza(self):
        """`reserva_no_activa`."""
        reserva = consumos.cerrar_reserva(self.reserva(10), 10, 0)
        with self.assertRaises(ErrorDeProduccion) as rechazo:
            consumos.cerrar_reserva(reserva, 1, 0)
        self.assertEqual(rechazo.exception.codigo, "reserva_no_activa")


class RegistrarConsumoDeOrdenTests(Base):
    def registrar(self, orden, cantidad=6, fecha=None, responsable=None, existencia=None):
        """Llama a `registrar_consumo_de_orden`."""
        return consumos.registrar_consumo_de_orden(orden, existencia or self.envase, cantidad, fecha or HOY, responsable or self.e.capataz)

    def test_post_crea_el_consumo_con_la_orden_el_monto_y_sin_lote_etapa_ni_sectores(self):
        """D-68 punto 3: `Consumo` (tipo interno `consumo`) con `orden`, el invernadero de la orden, sin lote, etapa ni sectores,
        `cant_consumo` y `monto_consumo` = cantidad × precio de referencia (6 × 1,50 = 9,00)."""
        orden = self.entrega()
        consumo = Consumo.objects.get(pk=self.registrar(orden, 6).consumo.pk)
        self.assertEqual(
            (consumo.orden_id, consumo.tipo_evento, consumo.invernadero_id, consumo.lote_id, consumo.etapa_id, consumo.siembra_id, consumo.aplicacion_id),
            (orden.pk, "consumo", self.e.invernadero.pk, None, None, None, None),
        )
        self.assertEqual((consumo.cant_consumo, consumo.monto_consumo, consumo.fecha_consumo, consumo.sectores.count()), (Decimal("6"), Decimal("9.00"), HOY, 0))

    def test_regla_el_monto_se_redondea_half_up_a_dos_decimales(self):
        """Redondeo `ROUND_HALF_UP`: 3 × 0,335 con precio 0,335 no entra (el precio tiene 2 decimales): 7 unidades × 1,50 = 10,50."""
        self.assertEqual(self.registrar(self.entrega(), 7).consumo.monto_consumo, Decimal("10.50"))

    def test_post_los_movimientos_salen_fefo_con_el_consumo_como_origen_y_bajan_el_stock(self):
        """Los movimientos: FEFO con `proponer_lotes_fefo` y `registrar_salida_por_consumo(..., origen_id=consumo.id, fecha=fecha)`."""
        orden = self.entrega()
        r = self.registrar(orden, 6)
        self.assertEqual({m.origen_id for m in r.movimientos}, {r.consumo.pk})
        self.assertEqual(sum(m.cantidad for m in r.movimientos), Decimal("6"))
        self.assertTrue(all(m.tipo_movimiento == MovimientoInsumo.TipoMovimiento.SALIDA_POR_CONSUMO for m in r.movimientos))
        self.assertEqual(sum(l.cantidad_disponible for l in LoteInsumo.objects.filter(insumo_invernadero=self.envase)), Decimal("94"))

    def test_regla_no_valida_contra_el_stock_y_lo_que_falta_sale_del_faltante_sin_lote(self):
        """Regla «Envases» de COM-CNC-ENT: el hecho ya ocurrió; si los lotes no alcanzan, la salida va al «faltante sin lote» sin rechazar."""
        r = self.registrar(self.entrega(), 130)
        self.assertEqual(sum(m.cantidad for m in r.movimientos), Decimal("130"))
        self.assertTrue(LoteInsumo.objects.filter(insumo_invernadero=self.envase, es_faltante_sin_lote=True).exists())

    def test_regla_sin_transaccion_lanza_runtime_error_y_no_audita(self):
        """Contrato de núcleo."""
        orden = self.entrega()
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            self.registrar(orden)
        self.assertFalse(Consumo.objects.exists())
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        self.registrar(orden)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))
