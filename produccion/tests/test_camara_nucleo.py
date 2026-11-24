# Pruebas del NÚCLEO de la cámara (COM-04a, paso 1): `produccion/servicios/camara.py`: `crear_partida`, `aplicar_merma_de_partida`,
# `vencer_partida`, `partidas_del_invernadero`, y las dos de la entrega (`egresar_de_partida`, `devolver_a_partida`, sección 10).
# Las llaman PROD-CNC-CSC, PROD-REG-MRM, PROD-VNC-CAM y COM-CNC-ENT (en `comercial`): acá se prueban solas, con partidas de fábrica.
# Fuente: docs/api/produccion.md (secciones 8 y 10), D-64 (puntos 2, 3 y 12), regla 29 de 8.6 y reglas 4 y 8 de 8.9.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import connections
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from produccion.errores import ErrorDeProduccion
from produccion.models import Lote, Merma, MovimientoStock, StockCosechado
from produccion.servicios import mermas
from produccion.tests.fabricas import cosecha, invernadero_con_produccion, lote_maduro, orden_suelta, partida_de

camara = perezoso("produccion.servicios.camara")
HOY = timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def lote(self, cantidad=100):
        """Un lote en Maduración."""
        return lote_maduro(self.e, cantidad)


class CrearPartidaTests(Base):
    def crear(self, lote, cantidad=10, **campos):
        """Llama a `crear_partida` con una cosecha de origen y valores por omisión."""
        valores = dict(fecha_cosecha=HOY, fecha_ingreso=HOY, costo_unitario=Decimal("1.2500"), origen=cosecha(self.e))
        valores.update(campos)
        return camara.crear_partida(lote, cantidad, "excedente_de_cosecha", **valores)

    def test_post_i_crea_la_partida_disponible_con_ingreso_igual_a_disponible_y_su_fecha_limite(self):
        """PROD-CNC-CSC, postcondiciones i y j: estado `disponible`, ingreso = disponible = cantidad, motivo, costo unitario y fecha límite =
        fecha de la cosecha + postcosecha de la variedad (regla 29 de 8.6)."""
        lote = self.lote()
        hace_dos_dias = HOY - timedelta(days=2)
        partida = self.crear(lote, 12, fecha_cosecha=hace_dos_dias)
        partida = StockCosechado.objects.get(pk=partida.pk)
        self.assertEqual(
            (partida.lote_id, partida.cantidad_ingreso_cosechado, partida.cantidad_disponible_cosechado, partida.estado_stock_cosechado),
            (lote.pk, 12, 12, "disponible"),
        )
        self.assertEqual((partida.motivo_cosechado, partida.costo_unitario_cosechado), ("excedente_de_cosecha", Decimal("1.2500")))
        self.assertEqual(partida.fecha_limite, hace_dos_dias + timedelta(days=lote.siembra.variedad.duracion_post_cosecha))
        self.assertEqual(partida.fecha_ingreso, HOY)

    def test_post_i_crea_su_movimiento_ingreso_a_camara_con_el_origen_y_el_costo(self):
        """Postcondición i: `ingreso_a_camara` con la cantidad, la partida, el origen que se pasó y el costo unitario."""
        origen = cosecha(self.e)
        partida = self.crear(self.lote(), 12, origen=origen)
        m = MovimientoStock.objects.get(partida=partida)
        self.assertEqual(
            (m.tipo_movimiento, m.cantidad, m.lote_id, m.origen_id, m.costo_unitario), ("ingreso_a_camara", 12, None, origen.pk, Decimal("1.2500"))
        )

    def test_regla_sin_transaccion_lanza_runtime_error(self):
        """Contrato de núcleo: sin transacción, `RuntimeError` y sin partida."""
        lote, origen = self.lote(), cosecha(self.e)  # armados antes: con `in_atomic_block` en falso las fábricas abrirían su propia transacción
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            camara.crear_partida(lote, 5, 'excedente_de_cosecha', fecha_cosecha=HOY, fecha_ingreso=HOY, costo_unitario=Decimal('1.0000'), origen=origen)
        self.assertFalse(StockCosechado.objects.exists())


class AplicarMermaDePartidaTests(Base):
    def aplicar(self, partida, cantidad, causa="dano_en_camara", descripcion="", responsable=None):
        """Llama a `aplicar_merma_de_partida`."""
        return camara.aplicar_merma_de_partida(partida, cantidad, causa, descripcion, responsable)

    def test_post_merma_de_camara_sin_etapa_con_el_lote_de_origen_y_fecha_de_hoy(self):
        """Regla 8 de 8.9 y PROD-REG-MRM 4a: `Merma` con el lote de origen, SIN etapa, el invernadero, fecha y hora actuales y el responsable
        (`None` = InfoPonia); `descripcion_evento` legible más la descripción."""
        partida = partida_de(self.lote(), 10)
        r = self.aplicar(partida, 4, descripcion="Se cortó el frío", responsable=self.e.capataz)
        merma = Merma.objects.get(pk=r.merma.pk)
        self.assertEqual(
            (merma.lote_id, merma.etapa_id, merma.invernadero_id, merma.responsable_id, merma.cant_merma, merma.causa, merma.fecha_bitacora),
            (partida.lote_id, None, self.e.invernadero.pk, self.e.capataz.pk, 4, "dano_en_camara", HOY),
        )
        self.assertEqual(merma.tipo_evento, "merma")
        self.assertIn("4 plantas", merma.descripcion_evento)
        self.assertIn("Se cortó el frío", merma.descripcion_evento)

    def test_post_baja_la_disponible_y_no_toca_el_lote(self):
        """La partida baja su disponible; el lote (cantidad y costo) no cambia: lo cosechado ya salió de él."""
        lote = self.lote()
        partida = partida_de(lote, 10)
        self.aplicar(partida, 4)
        self.assertEqual(StockCosechado.objects.get(pk=partida.pk).cantidad_disponible_cosechado, 6)
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (100, Decimal("100.00")))

    def test_post_registra_el_movimiento_merma_en_camara_con_la_merma_como_origen(self):
        """Postcondición: `merma_en_camara` sobre la partida, origen = la merma, `costo_unitario` = el de la partida."""
        partida = partida_de(self.lote(), 10, costo="1.7500")
        r = self.aplicar(partida, 4)
        m = MovimientoStock.objects.get(pk=r.movimiento.pk)
        self.assertEqual(
            (m.tipo_movimiento, m.cantidad, m.partida_id, m.lote_id, m.origen_id, m.costo_unitario),
            ("merma_en_camara", 4, partida.pk, None, r.merma.pk, Decimal("1.7500")),
        )

    def test_regla_30_de_8_6_la_partida_queda_agotada_cuando_llega_a_cero(self):
        """Regla 30 de 8.6: `agotado` si la disponible llega a 0."""
        partida = partida_de(self.lote(), 10)
        self.aplicar(partida, 10)
        partida = StockCosechado.objects.get(pk=partida.pk)
        self.assertEqual((partida.cantidad_disponible_cosechado, partida.estado_stock_cosechado), (0, "agotado"))

    def test_ext_la_merma_que_supera_lo_disponible_se_rechaza_sin_cambios(self):
        """`merma_supera_partida` si pasa de la disponible; no escribe nada."""
        partida = partida_de(self.lote(), 10)
        with self.assertRaises(ErrorDeProduccion) as rechazo:
            self.aplicar(partida, 11)
        self.assertEqual(rechazo.exception.codigo, "merma_supera_partida")
        self.assertFalse(Merma.objects.exists())
        self.assertEqual(StockCosechado.objects.get(pk=partida.pk).cantidad_disponible_cosechado, 10)

    def test_regla_la_cantidad_y_la_causa_son_validas(self):
        """Cantidad entera mayor que 0 (`cantidad_invalida`) y causa de cámara (`causa_invalida` con una de lote en pie)."""
        partida = partida_de(self.lote(), 10)
        with self.assertRaises(ErrorDeProduccion) as sin_cantidad:
            self.aplicar(partida, 0)
        self.assertEqual(sin_cantidad.exception.codigo, "cantidad_invalida")
        with self.assertRaises(ErrorDeProduccion) as causa:
            self.aplicar(partida, 1, causa="plaga")
        self.assertEqual(causa.exception.codigo, "causa_invalida")

    def test_regla_la_merma_de_camara_no_suma_a_la_merma_acumulada_del_lote(self):
        """Regla 7 de 8.9 y `merma_acumulada`: cuenta solo las mermas con etapa; la de cámara no."""
        lote = self.lote()
        self.aplicar(partida_de(lote, 10), 10)
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("0.00"))

    def test_regla_sin_transaccion_lanza_runtime_error(self):
        """Contrato de núcleo."""
        partida = partida_de(self.lote(), 10)
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            self.aplicar(partida, 1)


class VencerPartidaTests(Base):
    def test_post_vence_la_partida_con_merma_por_vencimiento_y_responsable_infoponia(self):
        """PROD-VNC-CAM: con disponible > 0, merma `vencimiento_en_camara` de toda la disponible sin responsable; la partida queda `vencido`
        con disponible 0."""
        partida = partida_de(self.lote(), 7, dias_limite=-1)
        r = camara.vencer_partida(partida, HOY)
        self.assertEqual((r.merma.causa, r.merma.cant_merma, r.merma.responsable_id), ("vencimiento_en_camara", 7, None))
        self.assertEqual(r.movimiento.tipo_movimiento, "merma_en_camara")
        partida = StockCosechado.objects.get(pk=partida.pk)
        self.assertEqual((partida.estado_stock_cosechado, partida.cantidad_disponible_cosechado), ("vencido", 0))

    def test_post_una_partida_sin_nada_disponible_pasa_a_vencido_sin_merma(self):
        """Sin disponible no hay nada que perder: devuelve `None` y la partida queda `vencido` igual."""
        partida = partida_de(self.lote(), 0, ingreso=5, estado="agotado", dias_limite=-1)
        self.assertIsNone(camara.vencer_partida(partida, HOY))
        self.assertEqual(StockCosechado.objects.get(pk=partida.pk).estado_stock_cosechado, "vencido")
        self.assertFalse(Merma.objects.exists())


class PartidasDelInvernaderoTests(Base):
    def test_regla_lista_las_partidas_con_lo_que_muestra_la_pestana_camara(self):
        """Lectura para la pestaña «Cámara»: variedad, lote, ingreso, fecha límite, disponible y estado, por fecha límite y id."""
        lote = self.lote()
        tarde, pronto = partida_de(lote, 5, dias_limite=9), partida_de(lote, 8, dias_limite=2)
        filas = camara.partidas_del_invernadero([self.e.invernadero.pk])
        self.assertEqual([f.partida_id for f in filas], [pronto.pk, tarde.pk])
        f = filas[0]
        self.assertEqual(
            (f.lote_id, f.variedad, f.fecha_ingreso, f.fecha_limite, f.disponible, f.estado),
            (lote.pk, str(self.e.variedad), HOY, HOY + timedelta(days=2), 8, "disponible"),
        )

    def test_regla_no_hace_consultas_por_fila(self):
        """Una consulta por tabla: las mismas con 1 y con 3 partidas."""
        lote = self.lote()
        partida_de(lote, 5)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as una:
            camara.partidas_del_invernadero([self.e.invernadero.pk])
        partida_de(lote, 5)
        partida_de(lote, 5)
        with CaptureQueriesContext(connection) as tres:
            camara.partidas_del_invernadero([self.e.invernadero.pk])
        self.assertEqual(len(una), len(tres))

    def test_regla_sin_invernaderos_devuelve_vacio_sin_consultar(self):
        """Una lista vacía da `[]` sin tocar la base."""
        with self.assertNumQueries(0):
            self.assertEqual(camara.partidas_del_invernadero([]), [])


class EgresarYDevolverTests(Base):
    """Sección 10: lo que usa la concreción de una entrega (COM-06a), con una orden suelta de tipo `entrega`."""

    def entrega(self):
        return orden_suelta(self.e.invernadero, "entrega")

    def test_post_egresar_baja_la_disponible_y_registra_el_egreso_de_camara(self):
        """`egresar_de_partida`: baja la disponible y crea `egreso_de_camara` con la orden como origen y el costo de la partida."""
        partida, orden = partida_de(self.lote(), 10, costo="2.5000"), self.entrega()
        m = camara.egresar_de_partida(partida, 4, orden)
        self.assertEqual(
            (m.tipo_movimiento, m.cantidad, m.partida_id, m.origen_id, m.costo_unitario), ("egreso_de_camara", 4, partida.pk, orden.pk, Decimal("2.5000"))
        )
        self.assertEqual(StockCosechado.objects.get(pk=partida.pk).cantidad_disponible_cosechado, 6)

    def test_post_egresar_todo_deja_la_partida_agotada(self):
        """Regla 30 de 8.6: `agotado` al llegar a 0."""
        partida = partida_de(self.lote(), 10)
        camara.egresar_de_partida(partida, 10, self.entrega())
        self.assertEqual(StockCosechado.objects.get(pk=partida.pk).estado_stock_cosechado, "agotado")

    def test_ext_egresar_mas_de_lo_disponible_o_de_una_vencida_se_rechaza(self):
        """`egreso_supera_partida` si pasa de la disponible o si la partida está `vencido`."""
        for partida, cantidad in ((partida_de(self.lote(), 10), 11), (partida_de(self.lote(), 0, ingreso=5, estado="vencido", dias_limite=-1), 1)):
            with self.assertRaises(ErrorDeProduccion) as rechazo:
                camara.egresar_de_partida(partida, cantidad, self.entrega())
            self.assertEqual(rechazo.exception.codigo, "egreso_supera_partida")
        self.assertFalse(MovimientoStock.objects.exists())

    def test_post_devolver_a_una_partida_vigente_sube_la_disponible_sin_merma(self):
        """Regla 29 de 8.6: con `fecha_limite >= hoy` y no vencida, sube la disponible, `ingreso_a_camara` con la orden de origen y sin merma."""
        partida, orden = partida_de(self.lote(), 5, ingreso=10), self.entrega()
        r = camara.devolver_a_partida(partida, 3, orden, HOY)
        self.assertEqual((r.movimiento.tipo_movimiento, r.movimiento.cantidad, r.movimiento.origen_id, r.merma), ("ingreso_a_camara", 3, orden.pk, None))
        self.assertEqual(StockCosechado.objects.get(pk=partida.pk).cantidad_disponible_cosechado, 8)

    def test_post_devolver_a_una_partida_agotada_la_vuelve_a_disponible(self):
        """Una partida `agotado` vuelve a `disponible` con lo devuelto."""
        partida = partida_de(self.lote(), 0, ingreso=10, estado="agotado")
        camara.devolver_a_partida(partida, 3, self.entrega(), HOY)
        partida = StockCosechado.objects.get(pk=partida.pk)
        self.assertEqual((partida.cantidad_disponible_cosechado, partida.estado_stock_cosechado), (3, "disponible"))

    def test_post_devolver_a_una_partida_vencida_hace_ingreso_y_merma_por_vencimiento_y_conserva_el_estado(self):
        """Regla 29 de 8.6: si ya venció, el ingreso y enseguida la merma por vencimiento; `vencido` sigue `vencido` con disponible 0."""
        partida = partida_de(self.lote(), 0, ingreso=10, estado="vencido", dias_limite=-2)
        r = camara.devolver_a_partida(partida, 3, self.entrega(), HOY)
        self.assertEqual((r.movimiento.tipo_movimiento, r.merma.merma.causa, r.merma.merma.cant_merma), ("ingreso_a_camara", "vencimiento_en_camara", 3))
        partida = StockCosechado.objects.get(pk=partida.pk)
        self.assertEqual((partida.estado_stock_cosechado, partida.cantidad_disponible_cosechado), ("vencido", 0))
        self.assertEqual(MovimientoStock.objects.filter(partida=partida).count(), 2)

    def test_regla_estas_funciones_no_auditan_ni_notifican_y_exigen_transaccion(self):
        """Contrato de núcleo: ni auditoría ni aviso; sin transacción, `RuntimeError`."""
        partida, orden = partida_de(self.lote(), 10), self.entrega()
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        camara.egresar_de_partida(partida, 1, orden)
        camara.devolver_a_partida(partida, 1, orden, HOY)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))
        with mock.patch.object(connections["default"], "in_atomic_block", False):
            with self.assertRaises(RuntimeError):
                camara.egresar_de_partida(partida, 1, orden)
            with self.assertRaises(RuntimeError):
                camara.devolver_a_partida(partida, 1, orden, HOY)
