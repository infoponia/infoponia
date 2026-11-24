# Pruebas del recorte de reservas de cámara (COM-04b; docs/patrones/stock_maduro.md, sección 8; regla 6 de 8.9; D-64 punto 7) y de las dos funciones puras de orden de
# `comercial/servicios/camara.py`: `orden_de_recorte` y `orden_de_candidatos` (pruebas de tabla, sin base).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar):
#   - `orden_de_recorte(lineas)`: `lineas` son objetos con `tipo` («cv» o «sum»), `fecha_entrega` y `reserva_id`. Devuelve la lista en el orden en que se recorta: primero las
#     de compra-venta y después las de suministro; dentro de cada grupo, la `fecha_entrega` más lejana primero y, si empatan, la reserva creada más tarde (mayor `reserva_id`).
#   - `orden_de_candidatos(candidatos)`: objetos con `fecha_entrega`, `tipo` («cv» o «sum»), `fecha_realizacion` y `clave` (el id; en un período `(id del detalle, ordinal de la
#     fecha)`). Orden: fecha de entrega; con la misma fecha, primero los períodos y después los detalles de venta; después el contrato realizado antes; por último la menor clave.
#   - `recortar_partida(partida, nueva_disponible) -> Recorte(lineas, reservas_liberadas, por_detalle)`: dentro de la transacción del llamador y con todo bloqueado. Recorta las
#     líneas de la partida de reservas «activas» o «lista para entrega» hasta que lo reservado iguale `nueva_disponible`; la línea queda en 0 (no se borra); una reserva cuyo
#     cubierto total queda en 0 pasa a «liberada». `lineas` = `[(DetalleReserva, recortado)]` en el orden de recorte; `por_detalle` = `[Afectado(objeto, contrato, recortado,
#     fecha_entrega)]`, uno por detalle de venta o período, con `objeto` el `DetalleVenta` o el `Periodo`, sumando lo recortado.

from collections import namedtuple
from datetime import date, timedelta

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import DetalleReserva, ReservaStock
from comercial.servicios import camara
from comercial.servicios.stock_maduro import Periodo
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    escenario_comercial,
    partida,
    reserva,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
LineaDePrueba = namedtuple("LineaDePrueba", "tipo fecha_entrega reserva_id")
CandidatoDePrueba = namedtuple("CandidatoDePrueba", "fecha_entrega tipo fecha_realizacion clave")


class OrdenesPurosTests(TestCase):
    """Funciones puras, sin base."""

    def test_regla_orden_de_recorte_compra_venta_antes_que_suministro(self):
        """Regla 6 de 8.9 y sección 8 del patrón: primero las líneas de compra-venta, después las de suministro, aunque la del suministro sea más lejana."""
        a = LineaDePrueba("sum", date(2026, 12, 30), 1)
        b = LineaDePrueba("cv", date(2026, 12, 1), 2)
        self.assertEqual(camara.orden_de_recorte([a, b]), [b, a])

    def test_regla_orden_de_recorte_la_fecha_mas_lejana_primero(self):
        """Regla 6 de 8.9: dentro de cada grupo, la fecha de entrega más lejana primero."""
        cerca, lejos = LineaDePrueba("cv", date(2026, 12, 1), 1), LineaDePrueba("cv", date(2026, 12, 9), 2)
        self.assertEqual(camara.orden_de_recorte([cerca, lejos]), [lejos, cerca])

    def test_regla_orden_de_recorte_con_la_misma_fecha_la_reserva_mas_reciente_primero(self):
        """Regla 6 de 8.9: si empatan, la reserva creada más tarde (mayor id)."""
        vieja, nueva = LineaDePrueba("sum", date(2026, 12, 1), 3), LineaDePrueba("sum", date(2026, 12, 1), 9)
        self.assertEqual(camara.orden_de_recorte([vieja, nueva]), [nueva, vieja])

    def test_regla_orden_de_candidatos_por_fecha_de_entrega(self):
        """Regla «Orden de prioridad» de PROD-ASG-CAM: primero la fecha de entrega más próxima."""
        a = CandidatoDePrueba(date(2026, 12, 5), "cv", date(2026, 11, 1), (1, 0))
        b = CandidatoDePrueba(date(2026, 12, 2), "cv", date(2026, 11, 9), (2, 0))
        self.assertEqual(camara.orden_de_candidatos([a, b]), [b, a])

    def test_ext_4a_con_la_misma_fecha_primero_los_periodos(self):
        """Extensión 4a de PROD-ASG-CAM: con la misma fecha, primero los períodos de suministro y después los detalles de venta."""
        venta = CandidatoDePrueba(date(2026, 12, 5), "cv", date(2026, 11, 1), (1, 0))
        periodo = CandidatoDePrueba(date(2026, 12, 5), "sum", date(2026, 11, 20), (7, 738000))
        self.assertEqual(camara.orden_de_candidatos([venta, periodo]), [periodo, venta])

    def test_ext_4a_despues_el_contrato_realizado_antes_y_por_ultimo_la_menor_clave(self):
        """Extensión 4a de PROD-ASG-CAM: el contrato con `fecha_realizacion` más antigua; si empatan, el de menor clave."""
        nuevo = CandidatoDePrueba(date(2026, 12, 5), "cv", date(2026, 11, 9), (1, 0))
        viejo = CandidatoDePrueba(date(2026, 12, 5), "cv", date(2026, 11, 1), (5, 0))
        gemelo = CandidatoDePrueba(date(2026, 12, 5), "cv", date(2026, 11, 1), (3, 0))
        self.assertEqual(camara.orden_de_candidatos([nuevo, viejo, gemelo]), [gemelo, viejo, nuevo])


class RecortarPartidaTests(ConDatosDeInventario, TestCase):
    """`recortar_partida`: el recorte con la base."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 200)

    def recortar(self, p, nueva):
        """Corre `recortar_partida` dentro de una transacción (como lo hace el caso de uso)."""
        with transaction.atomic():
            return camara.recortar_partida(p, nueva)

    def venta(self, dias, cantidad=20):
        """Una compra-venta con envío a `dias` días con un detalle de `cantidad`."""
        return detalle(compra_venta(self.e, dias=dias), self.e.variedad, cantidad)

    def test_regla_8_9_6_dentro_del_stock_libre_no_recorta(self):
        """Regla 6 de 8.9: si la nueva disponible alcanza para lo reservado, no se recorta nada."""
        p = partida(self.lote, 50)
        reserva(self.venta(3), [(p, 30)])
        r = self.recortar(p, 40)
        self.assertEqual((r.lineas, r.reservas_liberadas, r.por_detalle), ([], [], []))
        self.assertEqual(DetalleReserva.objects.get(partida=p).cantidad_reservada, 30)

    def test_regla_8_9_6_recorta_primero_la_entrega_mas_lejana_y_deja_viva_la_reserva_parcial(self):
        """Regla 6 de 8.9 y D-64 punto 7: se recorta lo justo empezando por la fecha más lejana; la reserva que conserva producto sigue «lista para entrega»."""
        p = partida(self.lote, 40)
        cerca, lejos = self.venta(3), self.venta(10)
        r_cerca, r_lejos = reserva(cerca, [(p, 20)]), reserva(lejos, [(p, 20)])
        r = self.recortar(p, 30)
        self.assertEqual([(l.reserva_id, n) for l, n in r.lineas], [(r_lejos.pk, 10)])
        self.assertEqual(r.reservas_liberadas, [])
        self.assertEqual(DetalleReserva.objects.get(reserva=r_lejos).cantidad_reservada, 10)
        self.assertEqual(DetalleReserva.objects.get(reserva=r_cerca).cantidad_reservada, 20)
        self.assertEqual(ReservaStock.objects.get(pk=r_lejos.pk).estado_reserva, "lista_para_entrega")
        self.assertEqual([(a.objeto.pk, a.recortado) for a in r.por_detalle], [(lejos.pk, 10)])
        verificar_invariantes_de_reservas()

    def test_regla_8_9_6_a_cero_libera_las_reservas_y_conserva_las_lineas(self):
        """Regla 6 de 8.9 y D-64 punto 7: recortar todo deja las líneas en 0 (se conservan) y las reservas «liberadas»."""
        p = partida(self.lote, 40)
        r1, r2 = reserva(self.venta(3), [(p, 20)]), reserva(self.venta(10), [(p, 20)])
        r = self.recortar(p, 0)
        self.assertEqual(sorted(x.pk for x in r.reservas_liberadas), sorted([r1.pk, r2.pk]))
        self.assertEqual(DetalleReserva.objects.filter(partida=p).count(), 2)
        self.assertEqual(set(DetalleReserva.objects.filter(partida=p).values_list("cantidad_reservada", flat=True)), {0})
        self.assertEqual(set(ReservaStock.objects.filter(pk__in=[r1.pk, r2.pk]).values_list("estado_reserva", flat=True)), {"liberada"})
        verificar_invariantes_de_reservas()

    def test_regla_8_9_6_la_compra_venta_se_recorta_antes_que_el_suministro_aunque_este_mas_lejos(self):
        """Sección 8 del patrón: las líneas de compra-venta primero y después las de suministro."""
        p = partida(self.lote, 40)
        d_cv = self.venta(3)
        d_sum = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20)
        fecha = HOY + timedelta(days=20)
        r_cv, r_sum = reserva(d_cv, [(p, 20)]), reserva_de_periodo(d_sum, fecha, [(p, 20)])
        r = self.recortar(p, 30)
        self.assertEqual([(l.reserva_id, n) for l, n in r.lineas], [(r_cv.pk, 10)])
        self.assertEqual(DetalleReserva.objects.get(reserva=r_sum).cantidad_reservada, 20)
        self.assertEqual(type(r.por_detalle[0].objeto).__name__, "DetalleVenta")

    def test_regla_8_9_6_un_periodo_de_suministro_se_devuelve_como_periodo(self):
        """El período afectado vuelve como `Periodo` (detalle y fecha), para volver a cubrirlo."""
        p = partida(self.lote, 20)
        d_sum = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20)
        fecha = HOY + timedelta(days=5)
        reserva_de_periodo(d_sum, fecha, [(p, 20)])
        r = self.recortar(p, 5)
        afectado = r.por_detalle[0]
        self.assertEqual((afectado.objeto, afectado.recortado, afectado.fecha_entrega), (Periodo(d_sum, fecha), 15, fecha))

    def test_regla_d64_7_la_reserva_con_una_linea_de_lote_sigue_viva_con_la_de_partida_en_cero(self):
        """D-64 punto 7: una reserva con líneas de lote y de cámara no pasa a «liberada» si el lote sigue cubriendo: la línea de partida queda en 0."""
        p = partida(self.lote, 10)
        r = reserva(self.venta(3), [(self.lote, 10), (p, 10)])
        resultado = self.recortar(p, 0)
        self.assertEqual(resultado.reservas_liberadas, [])
        self.assertEqual(ReservaStock.objects.get(pk=r.pk).estado_reserva, "activa")
        self.assertEqual(DetalleReserva.objects.get(reserva=r, partida=p).cantidad_reservada, 0)
        self.assertEqual(DetalleReserva.objects.get(reserva=r, lote=self.lote).cantidad_reservada, 10)

    def test_regla_8_9_6_no_toca_reservas_entregadas_ni_liberadas(self):
        """Solo cuentan las reservas «activas» o «lista para entrega»: una «entregada» o «liberada» no se recorta."""
        p = partida(self.lote, 30)
        entregada = reserva(self.venta(3), [(p, 10)], estado="entregada")
        activa = reserva(self.venta(5), [(p, 10)])
        r = self.recortar(p, 0)
        self.assertEqual([l.reserva_id for l, _ in r.lineas], [activa.pk])
        self.assertEqual(DetalleReserva.objects.get(reserva=entregada).cantidad_reservada, 10)
