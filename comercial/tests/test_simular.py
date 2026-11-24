# Pruebas de `stock_maduro.simular` y `simular_varias` (COM-03a, paso 3; docs/patrones/stock_maduro.md, sección 7): la verificación acumulada
# por variedad de COM-PCT-SUM (9e) y de COM-MOD-SUM (5b.3). Solo lectura, sin bloquear. Cada período se verifica contra lo que dejan libre
# los anteriores del mismo contrato y de la misma variedad. Una prueba compara `simular` con lo que después reserva `asignar`.

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import ReservaStock
from comercial.servicios import stock_maduro
from comercial.tests.fabricas import (
    detalle_suministro,
    escenario_comercial,
    partida,
    periodo,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.servicios import configuracion
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def dias(n):
    """La fecha de dentro de ``n`` días."""
    return HOY + timedelta(days=n)


class SimularTests(ConDatosDeInventario, TestCase):
    """`simular(variedad_id, invernadero_ids, pedidos, parametro) -> [Cobertura(fecha, cantidad, disponible)]`: ``disponible`` es el stock
    maduro libre que le queda a ese pedido **después de los anteriores**; ``cubierta`` es ``min(cantidad, disponible)``."""

    def setUp(self):
        self.e = escenario_comercial()
        self.ids = [self.e.invernadero.pk]
        self.variedad = self.e.variedad.pk
        configuracion.obtener()  # carga la configuración una vez: las pruebas de consultas no la cuentan
        self.addCleanup(verificar_invariantes_de_reservas)

    def simular(self, pedidos, variedad=None, ids=None):
        return stock_maduro.simular(variedad or self.variedad, ids or self.ids, pedidos, "suministro")

    def test_regla_cada_pedido_se_verifica_contra_lo_que_dejan_libre_los_anteriores(self):
        """9e de COM-PCT-SUM y patrón sección 7: con 15 plantas de stock y dos períodos de 10, el primero ve 15 y el segundo, 5."""
        lote_maduro(self.e, 15)
        cobertura = self.simular([(dias(3), 10), (dias(10), 10)])
        self.assertEqual([c.disponible for c in cobertura], [15, 5])
        self.assertEqual([c.cubierta for c in cobertura], [10, 5])

    def test_ext_9e_con_stock_para_uno_solo_de_dos_periodos_el_segundo_da_su_disponible_real(self):
        """Dos períodos de 7 días con 14 de ventana y stock para uno solo: el segundo da su disponible real (0), no el stock total."""
        lote_maduro(self.e, 10)
        cobertura = self.simular([(dias(3), 10), (dias(10), 10)])
        self.assertEqual([c.disponible for c in cobertura], [10, 0])
        self.assertEqual([c.fecha for c in cobertura], [dias(3), dias(10)])
        self.assertEqual([c.cantidad for c in cobertura], [10, 10])

    def test_regla_el_orden_de_asignacion_toma_primero_las_partidas_y_despues_los_lotes(self):
        """Regla 7 de 8.6: partidas por vencimiento y después lotes; el total acumulado es la suma de lo elegible."""
        lote = lote_maduro(self.e, 10)
        partida(lote, disponible=4, fecha_limite=dias(30))
        cobertura = self.simular([(dias(3), 8), (dias(10), 8)])
        self.assertEqual([c.disponible for c in cobertura], [14, 6])

    def test_regla_una_partida_que_vence_antes_de_la_fecha_del_periodo_no_cuenta_para_ese_periodo(self):
        """Regla «Partida elegible»: `fecha_limite >= fecha de entrega`. Cada período mira sus propios candidatos."""
        partida(lote_maduro(self.e, 1), disponible=10, fecha_limite=dias(5))
        cobertura = self.simular([(dias(3), 10), (dias(10), 10)])
        self.assertEqual([c.disponible for c in cobertura], [11, 1])
        self.assertEqual(cobertura[1].cubierta, 1)

    def test_regla_sin_stock_ningun_periodo_se_cubre(self):
        """Sin lotes ni partidas, todos los períodos dan disponible 0."""
        cobertura = self.simular([(dias(3), 10), (dias(10), 10)])
        self.assertEqual([(c.disponible, c.cubierta) for c in cobertura], [(0, 0), (0, 0)])

    def test_regla_ningun_periodo_tiene_mas_cubierto_que_su_cantidad(self):
        """Invariante de la sección 7: ``cubierta <= cantidad`` aun con stock de sobra."""
        lote_maduro(self.e, 500)
        for c in self.simular([(dias(3), 10), (dias(10), 30)]):
            self.assertLessEqual(c.cubierta, c.cantidad)

    def test_regla_lo_reservado_por_otros_contratos_ya_no_esta_libre(self):
        """El stock libre descuenta las reservas existentes (de cualquier contrato): una reserva de 6 deja 4 para el primer período."""
        lote = lote_maduro(self.e, 10)
        suelto = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=6, primera_en_dias=3)
        reserva_de_periodo(suelto, dias(3), [(lote, 6)])
        self.assertEqual(self.simular([(dias(3), 10)])[0].disponible, 4)

    def test_regla_los_pedidos_tienen_que_venir_en_orden_de_fecha(self):
        """Patrón, sección 7: ``pedidos`` en orden de fecha (la acumulación depende del orden); si no, `ValueError`."""
        with self.assertRaises(ValueError):
            self.simular([(dias(10), 10), (dias(3), 10)])

    def test_regla_sin_pedidos_no_consulta_y_devuelve_una_lista_vacia(self):
        """Sin pedidos, `[]` sin tocar la base."""
        with self.assertNumQueries(0):
            self.assertEqual(self.simular([]), [])

    def test_regla_simular_no_escribe_nada(self):
        """Solo lectura: no crea reservas ni cosechas."""
        lote_maduro(self.e, 100)
        self.simular([(dias(3), 10), (dias(10), 10)])
        self.assertEqual((ReservaStock.objects.count(), Cosecha.objects.count()), (0, 0))

    def test_regla_varias_variedades_se_simulan_por_separado_en_un_solo_calculo(self):
        """`simular_varias({variedad_id: pedidos})`: el acumulado es por variedad. Una variedad sin stock da 0 y no resta a la otra."""
        lote_maduro(self.e, 15)
        sin_stock = 10**6  # una variedad sin lotes ni partidas
        resultado = stock_maduro.simular_varias(
            {self.variedad: [(dias(3), 10), (dias(10), 10)], sin_stock: [(dias(3), 5)]}, self.ids, "suministro"
        )
        self.assertEqual([c.disponible for c in resultado[self.variedad]], [15, 5])
        self.assertEqual([c.disponible for c in resultado[sin_stock]], [0])
        self.assertEqual(self.simular([(dias(3), 10)]), resultado[self.variedad][:1])

    def test_regla_requisito_la_cantidad_de_consultas_no_crece_con_los_pedidos_ni_las_variedades(self):
        """Requisito «no más de 1 segundo» (`assertNumQueries` igual con 1 y con 4 períodos, y con 1 y con 2 variedades)."""
        lote_maduro(self.e, 100)
        cuatro = [(dias(3 + 7 * k), 10) for k in range(4)]
        with CaptureQueriesContext(connection) as con_uno:
            self.simular(cuatro[:1])
        with CaptureQueriesContext(connection) as con_cuatro:
            self.simular(cuatro)
        with CaptureQueriesContext(connection) as con_dos_variedades:
            stock_maduro.simular_varias({self.variedad: cuatro, 10**6: cuatro[:2]}, self.ids, "suministro")
        self.assertEqual(len(con_uno), len(con_cuatro))
        self.assertEqual(len(con_uno), len(con_dos_variedades))

    def test_regla_simular_y_asignar_coinciden_con_los_mismos_datos(self):
        """Patrón, sección 7: lo que `simular` dice que se cubre es lo que después reserva `asignar` en el mismo orden (período por período)."""
        lote = lote_maduro(self.e, 14)
        partida(lote, disponible=5, fecha_limite=dias(8))
        s = suministro(self.e, duracion=6)
        d = detalle_suministro(s, self.e.variedad, cantidad=10, periodo=7, primera_en_dias=3)
        fechas = [dias(3), dias(10)]
        simulado = self.simular([(f, 10) for f in fechas])
        reservado = []
        for f in fechas:
            reservado.append(stock_maduro.asignar(self.e.vendedor, periodo(d, f), 10, f, "suministro").cubierta)
        self.assertEqual(reservado, [c.cubierta for c in simulado])
        self.assertEqual(reservado, [10, 9])


class SimularConLotesExcluidosYSinReservasTests(ConDatosDeInventario, TestCase):
    """COM-04a (sección 8 del patrón de stock): `simular(..., lotes_excluidos=(), sin_reservas=())` para la estimación de PROD-CNL-ORD (6b): no
    considera esos lotes y cuenta como libre lo que reservan esas reservas (las de la cosecha que se cancelaría)."""

    def setUp(self):
        self.e = escenario_comercial()
        self.ids = [self.e.invernadero.pk]
        configuracion.obtener()
        self.addCleanup(verificar_invariantes_de_reservas)

    def simular(self, pedidos, **extra):
        return stock_maduro.simular(self.e.variedad.pk, self.ids, pedidos, "suministro", **extra)

    def test_regla_los_lotes_excluidos_no_aportan_stock(self):
        """Con dos lotes de 10 y uno excluido, el pedido de 15 ve solo 10."""
        a, b = lote_maduro(self.e, 10), lote_maduro(self.e, 10)
        self.assertEqual(self.simular([(dias(3), 15)])[0].disponible, 20)
        self.assertEqual(self.simular([(dias(3), 15)], lotes_excluidos=[a.pk])[0].disponible, 10)

    def test_regla_las_reservas_indicadas_cuentan_como_libres(self):
        """Un lote de 20 con 20 reservados por la cosecha que se cancelaría: sin `sin_reservas` no queda nada; con ella, queda todo."""
        lote = lote_maduro(self.e, 20)
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20, primera_en_dias=3)
        reserva_ = reserva_de_periodo(det, dias(3), [(lote, 20)])
        self.assertEqual(self.simular([(dias(3), 10)])[0].disponible, 0)
        self.assertEqual(self.simular([(dias(3), 10)], sin_reservas=[reserva_])[0].disponible, 20)

    def test_regla_las_partidas_de_la_reserva_liberada_pueden_volver_a_usarse(self):
        """Una reserva «lista para entrega» que ocupa una partida de 12: con `sin_reservas`, la partida vuelve a estar libre."""
        lote = lote_maduro(self.e, 1)
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=12, primera_en_dias=3)
        reserva_ = reserva_de_periodo(det, dias(3), [(partida(lote, 12), 12)])
        self.assertEqual(self.simular([(dias(3), 12)])[0].disponible, 1)
        self.assertEqual(self.simular([(dias(3), 12)], sin_reservas=[reserva_])[0].disponible, 13)

    def test_regla_la_estimacion_coincide_con_lo_que_despues_reserva_asignar(self):
        """Una prueba compara la estimación con lo que después reserva `asignar` (patrón, sección 8): se excluye un lote, se libera la reserva y
        lo que `simular` dice que se cubre es lo que `asignar` reserva."""
        excluido, bueno = lote_maduro(self.e, 10), lote_maduro(self.e, 8)
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=3)
        cobertura = self.simular([(dias(3), 30)], lotes_excluidos=[excluido.pk])[0]
        resultado = stock_maduro.asignar(None, periodo(det, dias(3)), 30, dias(3), "suministro", lotes_excluidos=[excluido.pk])
        self.assertEqual(cobertura.cubierta, resultado.cubierta)
        self.assertEqual(resultado.cubierta, 8)

    def test_regla_sin_los_argumentos_nuevos_todo_sigue_igual(self):
        """Compatibilidad: sin `lotes_excluidos` ni `sin_reservas`, la simulación es la de COM-03a."""
        lote_maduro(self.e, 15)
        self.assertEqual([c.disponible for c in self.simular([(dias(3), 10), (dias(10), 10)])], [15, 5])
