# Pruebas de PROD-ASG-STK, Asignar Stock Maduro (COM-02, paso 3; docs/casos_de_uso/produccion/stock_maduro.md y
# docs/patrones/stock_maduro.md): `disponible`, `asignar`, `cantidad_sin_cubrir`, `reservado_de_lotes` y `repartir`. Una prueba por regla de
# negocio, por postcondición y por extensión. Todas las que escriben reservas verifican al final los invariantes del patrón (sección 6).
# La concurrencia (extensión 8a, resuelta bloqueando antes de calcular) está en `test_stock_maduro_concurrencia.py`.

from datetime import timedelta
from unittest import mock

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import DetalleReserva, DetalleVenta, ReservaStock
from comercial.servicios import stock_maduro
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    escenario_comercial,
    partida,
    reserva,
    segundo_invernadero,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta, ConfiguracionOperativa, Invernadero
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion
from produccion.models import Cosecha, Lote
from produccion.servicios import lotes as api_lotes
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def dias(n):
    """La fecha de dentro de ``n`` días (``n`` negativo: de hace ``-n``)."""
    return HOY + timedelta(days=n)


class BaseDeAsignacion(ConDatosDeInventario, TestCase):
    """Un escenario con un invernadero con Capataz y Vendedor, y una compra-venta pactada para dentro de 3 días con un detalle de 30."""

    PEDIDO = 30  # lo que pide el detalle de la prueba

    def setUp(self):
        self.e = escenario_comercial()
        self.venta = compra_venta(self.e, dias=3)
        self.detalle = detalle(self.venta, self.e.variedad, cantidad=self.PEDIDO)
        self.addCleanup(verificar_invariantes_de_reservas)

    def asignar(self, cantidad=30, fecha=None, parametro="compra_venta", detalle_=None, **extra):
        """PROD-ASG-STK dentro de la transacción del caso de uso base (acá, la de la prueba)."""
        return stock_maduro.asignar(
            self.e.vendedor, detalle_ or self.detalle, cantidad, fecha or self.venta.fecha_pactada_venta, parametro, **extra
        )

    def configurar(self, **valores):
        """Pisa parámetros de la configuración operativa (anticipación de cosecha)."""
        configuracion.obtener()
        ConfiguracionOperativa.objects.filter(singleton=1).update(**valores)


class CantidadSinCubrirTests(BaseDeAsignacion):
    """Regla «Cantidad a reservar» y regla 10 de 8.8 (`cantidad_sin_cubrir`)."""

    def test_regla_cantidad_sin_cubrir_es_lo_pedido_menos_lo_cubierto_de_las_reservas_no_liberadas(self):
        """Regla 10 de 8.8: pedido − Σ cubierto de las líneas de las reservas NO liberadas."""
        lote = lote_maduro(self.e, 100)
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), 30)
        reserva(self.detalle, [(lote, 20)])
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), 10)
        reserva(self.detalle, [(lote, 5)], estado="liberada")
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), 10)

    def test_regla_cantidad_cubierta_de_una_linea_de_lote_cosechado_es_el_minimo_con_lo_cosechado(self):
        """Regla 9 de 8.8: lote sin cosechar, la reservada; cosechado, `min(cosechada, reservada)`; partida, la reservada."""
        lote = lote_maduro(self.e, 100)
        r = reserva(self.detalle, [(lote, 20)])
        DetalleReserva.objects.filter(reserva=r).update(cantidad_cosechada=15)
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), 15)
        DetalleReserva.objects.filter(reserva=r).update(cantidad_cosechada=25)
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), 10)

    def test_regla_un_detalle_confirmado_rechazado_o_cancelado_no_tiene_cantidad_sin_cubrir(self):
        """Regla 10 de 8.8: un detalle confirmado, rechazado o cancelado no tiene; uno pendiente de decisión, sí."""
        for estado, esperado in (("confirmado", 0), ("rechazado", 0), ("cancelado", 0), ("pendiente_decision", 30), ("abierto", 30)):
            with self.subTest(estado=estado):
                DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta=estado)
                self.detalle.refresh_from_db()
                self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), esperado)

    def test_regla_la_cantidad_reservada_es_la_menor_entre_la_indicada_y_la_sin_cubrir(self):
        """Regla «Cantidad a reservar» (paso 2): nunca se reserva más que lo sin cubrir del detalle."""
        lote = lote_maduro(self.e, 100)
        reserva(self.detalle, [(lote, 20)])
        resultado = self.asignar(cantidad=30)
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (10, 0))
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(self.detalle), 0)

    def test_ext_2a_sin_cantidad_sin_cubrir_no_crea_nada(self):
        """Extensión 2a: un detalle sin cantidad sin cubrir devuelve cubierta 0 y sin cubrir 0, sin crear nada."""
        lote = lote_maduro(self.e, 100)
        reserva(self.detalle, [(lote, 30)])
        antes = (ReservaStock.objects.count(), Cosecha.objects.count())
        resultado = self.asignar()
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir, resultado.reservas, resultado.cosechas), (0, 0, [], []))
        self.assertEqual((ReservaStock.objects.count(), Cosecha.objects.count()), antes)


class PreCondicionesTests(BaseDeAsignacion):
    """Precondiciones a, b y c (las verifica `asignar` igual: lanza `ValueError`/`RuntimeError`, errores de programación del base)."""

    def test_pre_a_sin_transaccion_lanza_runtime_error(self):
        """Precondición a y «Ejecución»: sin transacción del caso de uso base en curso, `RuntimeError` (se detecta con `get_autocommit`)."""
        with mock.patch("comercial.servicios.stock_maduro.transaction.get_autocommit", return_value=True):
            with self.assertRaises(RuntimeError):
                self.asignar()

    def test_pre_b_un_detalle_que_no_esta_abierto_lanza_value_error(self):
        """Precondición b: el detalle tiene que ser un detalle «abierto» (o pendiente de decisión) de una venta «abierta»."""
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="confirmado")
        with self.assertRaises(ValueError):
            self.asignar()

    def test_pre_b_una_venta_que_no_esta_abierta_lanza_value_error(self):
        """Precondición b: la compra-venta tiene que estar «abierta»."""
        for estado in ("concretada", "cancelada"):
            with self.subTest(estado=estado):
                type(self.venta).objects.filter(pk=self.venta.pk).update(estado_venta=estado)
                with self.assertRaises(ValueError):
                    self.asignar()

    def test_pre_c_cantidad_no_positiva_o_fecha_invalida_lanza_value_error(self):
        """Precondición c: la fecha de entrega y una cantidad mayor que cero."""
        for cantidad in (0, -3):
            with self.subTest(cantidad=cantidad), self.assertRaises(ValueError):
                self.asignar(cantidad=cantidad)
        with self.assertRaises(ValueError):
            self.asignar(fecha=None, parametro="otro")

    def test_pre_b_un_objeto_que_no_es_un_detalle_de_venta_lanza_value_error(self):
        """Hasta COM-03 el detalle es un `DetalleVenta`."""
        with self.assertRaises(ValueError):
            self.asignar(detalle_=self.venta)


class InvernaderosConsideradosTests(BaseDeAsignacion):
    """Pasos 3: regla «Invernaderos considerados» y extensiones 3a y 3b."""

    def test_regla_en_un_envio_se_consideran_los_invernaderos_activos_del_vendedor(self):
        """Regla «Invernaderos considerados»: con envío, los invernaderos activos del Vendedor del contrato (R115)."""
        sur = segundo_invernadero(self.e)
        lote_maduro(self.e, 10)
        lote_maduro(sur, 10)
        resultado = self.asignar(cantidad=20)
        self.assertEqual(resultado.cubierta, 20)
        self.assertEqual({r.invernadero_id for r in resultado.reservas}, {self.e.invernadero.pk, sur.invernadero.pk})

    def test_regla_el_stock_de_otro_vendedor_no_se_considera(self):
        """Regla «Invernaderos considerados»: el invernadero de otro Vendedor no cuenta."""
        otro = escenario_comercial(sufijo="2")
        lote_maduro(otro, 100, variedad=self.e.variedad)
        resultado = self.asignar()
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (0, 30))

    def test_regla_un_invernadero_inactivo_nunca_se_considera(self):
        """Regla «Invernaderos considerados» (regla 4 de PROD-BAJ-INV): un inactivo no aparece en las asignaciones."""
        sur = segundo_invernadero(self.e)
        lote_maduro(sur, 100)
        Invernadero.objects.filter(pk=sur.invernadero.pk).update(estado_invernadero="inactivo")
        resultado = self.asignar()
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (0, 30))

    def test_ext_3a_con_retiro_solo_el_invernadero_de_retiro(self):
        """Extensión 3a: una compra-venta con retiro considera solo el invernadero de retiro."""
        sur = segundo_invernadero(self.e)
        lote_maduro(self.e, 100)
        lote_maduro(sur, 100)
        venta = compra_venta(self.e, modalidad="retiro", retiro=sur.invernadero)
        d = detalle(venta, self.e.variedad, cantidad=30)
        resultado = self.asignar(detalle_=d, fecha=venta.fecha_pactada_venta)
        self.assertEqual([r.invernadero_id for r in resultado.reservas], [sur.invernadero.pk])
        self.assertEqual(resultado.cubierta, 30)

    def test_ext_3a_un_retiro_en_un_invernadero_inactivo_no_cubre_nada(self):
        """Extensión 3a y regla 4 de PROD-BAJ-INV: si el invernadero de retiro está inactivo, no hay con qué cubrir."""
        lote_maduro(self.e, 100)
        venta = compra_venta(self.e, modalidad="retiro")
        d = detalle(venta, self.e.variedad, cantidad=30)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(self.asignar(detalle_=d, fecha=venta.fecha_pactada_venta).sin_cubrir, 30)

    def test_ext_3b_con_parametro_de_suministro_se_usa_su_anticipacion(self):
        """Extensión 3b (el detalle de suministro lo prueba COM-03): con `parametro="suministro"` la cosecha se programa con
        `dias_anticipacion_cosecha_suministro` (3 por defecto), en vez de la de compra-venta (1)."""
        lote_maduro(self.e, 100)
        fecha = dias(10)
        resultado = self.asignar(fecha=fecha, parametro="suministro")
        self.assertEqual(resultado.cosechas[0].fecha_programada_orden, fecha - timedelta(days=3))
        otra = self.asignar(fecha=fecha, parametro="compra_venta", cantidad=0 + 1, detalle_=detalle(compra_venta(self.e, dias=10), self.e.variedad, 5))
        self.assertEqual(otra.cosechas[0].fecha_programada_orden, fecha - timedelta(days=1))


class ElegibilidadTests(BaseDeAsignacion):
    """Reglas «Partida elegible» y «Lote elegible» (reglas 7, 9 y 11 de 8.6; regla 3 de 8.20)."""

    def test_regla_partida_elegible_solo_disponible_vigente_con_stock_libre_de_la_variedad_y_del_invernadero(self):
        """Regla «Partida elegible»: «disponible», con fecha límite igual o posterior a la entrega y stock libre > 0."""
        lote = lote_maduro(self.e, 50)
        buena = partida(lote, 10, fecha_limite=self.venta.fecha_pactada_venta)  # el día de la fecha límite todavía se entrega
        partida(lote, 10, fecha_limite=self.venta.fecha_pactada_venta - timedelta(days=1))  # vence antes de la entrega
        partida(lote, 10, estado="vencido")
        partida(lote, 0)  # agotada
        llena = partida(lote, 8)
        reserva(self.detalle, [(llena, 8)])
        resultado = self.asignar(cantidad=30)
        lineas = DetalleReserva.objects.filter(reserva__in=resultado.reservas)
        self.assertEqual([(l.partida_id, l.cantidad_reservada) for l in lineas.filter(partida__isnull=False)], [(buena.pk, 10)])

    def test_regla_una_partida_de_otra_variedad_o_de_otro_vendedor_no_se_considera(self):
        """Regla «Partida elegible»: de la variedad y de un invernadero considerado."""
        otro = escenario_comercial(sufijo="2")
        partida(lote_maduro(otro, 50), 40)
        self.assertEqual(self.asignar().cubierta, 0)

    def test_regla_partida_libre_resta_lo_reservado_en_reservas_activas_y_listas(self):
        """Regla «Stock libre» (regla 10 de 8.6): disponible − Σ reservado en reservas activas o listas para entrega; las liberadas no restan."""
        lote = lote_maduro(self.e, 50)
        p = partida(lote, 20)
        otro = detalle(compra_venta(self.e, dias=5), self.e.variedad, cantidad=8)
        reserva(otro, [(p, 8)], estado="lista_para_entrega")
        reserva(otro, [(p, 4)], estado="liberada")
        resultado = self.asignar()
        self.assertEqual(
            sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(reserva__in=resultado.reservas, partida=p)), 12
        )

    def test_regla_lote_elegible_solo_activo_en_maduracion_con_stock_libre(self):
        """Regla «Lote elegible»: «activo», de la variedad, en la etapa Maduración, con stock libre > 0."""
        from produccion.tests.fabricas import lote_con_ciclo

        lote_con_ciclo(self.e, cantidad=40, etapa="crecimiento")  # todavía no maduró
        lleno = lote_maduro(self.e, 15)
        reserva(self.detalle, [(lleno, 15)])
        elegible = lote_maduro(self.e, 12)
        resultado = self.asignar(cantidad=15)
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (12, 3))
        self.assertEqual(
            list(DetalleReserva.objects.filter(reserva__in=resultado.reservas).values_list("lote_id", flat=True)), [elegible.pk]
        )

    def test_regla_lote_finalizado_no_es_elegible(self):
        """Regla «Lote elegible»: un lote «finalizado» no cuenta."""
        lote = lote_maduro(self.e, 20)
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        self.assertEqual(self.asignar().cubierta, 0)

    def test_regla_8_20_3_un_lote_cuya_fecha_maxima_es_anterior_a_la_programada_no_es_elegible(self):
        """Regla 3 de 8.20 (ejemplos): el lote entró hace 5 días a una Maduración de 10, su fecha máxima de cosecha es dentro de 5 días.
        Con anticipación 1: entrega en 6 días → programada en 5 → elegible; entrega en 7 → programada en 6 → no."""
        lote = lote_maduro(self.e, 50, entrada=dias(-5))
        self.assertEqual(api_lotes.fecha_maxima_de_cosecha(lote), dias(5))
        self.assertEqual(self.asignar(fecha=dias(6), cantidad=10).cubierta, 10)
        self.assertEqual(self.asignar(fecha=dias(7), cantidad=10, detalle_=detalle(compra_venta(self.e, dias=7), self.e.variedad, 10)).cubierta, 0)

    def test_regla_8_11_3_anticipacion_efectiva_menor_por_la_postcosecha(self):
        """Regla 3 de 8.11: la anticipación efectiva es `min(parámetro, postcosecha de la variedad)`. Con parámetro 5 y postcosecha 2, es 2:
        una entrega en 10 días programa la cosecha en 8; con postcosecha 7 (efectiva 5), en 5."""
        lote_maduro(self.e, 100)
        self.configurar(dias_anticipacion_cosecha_compra_venta=5)
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(duracion_post_cosecha=2)
        self.assertEqual(self.asignar(fecha=dias(10), cantidad=10).cosechas[0].fecha_programada_orden, dias(8))
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(duracion_post_cosecha=7)
        otro = detalle(compra_venta(self.e, dias=10), self.e.variedad, 10)
        self.assertEqual(self.asignar(fecha=dias(10), cantidad=10, detalle_=otro).cosechas[0].fecha_programada_orden, dias(5))

    def test_regla_8_11_3_la_fecha_programada_nunca_es_anterior_a_hoy(self):
        """Regla 3 de 8.11: `max(hoy, entrega − anticipación)`: una entrega hoy programa la cosecha hoy."""
        lote_maduro(self.e, 100)
        cosecha = self.asignar(fecha=HOY, cantidad=10).cosechas[0]
        self.assertEqual((cosecha.fecha_programada_orden, cosecha.fecha_creacion_orden), (HOY, HOY))

    def test_regla_la_fecha_maxima_de_cada_lote_coincide_con_la_de_produccion(self):
        """Los lotes elegibles se deciden con la misma fecha máxima que `produccion.servicios.lotes.fecha_maxima_de_cosecha`
        (INV/PRD-02): la que usa `comercial` no se calcula a mano."""
        lotes = [lote_maduro(self.e, 10, entrada=dias(-n)) for n in (0, 4, 9)]
        for lote in lotes:
            lote.refresh_from_db()
        disponible = stock_maduro.disponible([self.e.variedad.pk], [self.e.invernadero.pk], dias(5), "compra_venta")
        # Entrega en 5 días, anticipación 1 ⇒ programada en 4: la máxima de los lotes es hoy+10, hoy+6 y hoy+1 ⇒ el tercero no entra.
        self.assertEqual([api_lotes.fecha_maxima_de_cosecha(l) for l in lotes], [dias(10), dias(6), dias(1)])
        self.assertEqual(disponible[self.e.variedad.pk].lotes, 20)


class OrdenDeAsignacionTests(BaseDeAsignacion):
    """Regla «Orden de asignación» (regla 7 de 8.6; regla 2 de 8.20)."""

    PEDIDO = 100

    def lineas(self, resultado):
        """`[(lote_id, partida_id, cantidad)]` de las líneas de las reservas, en orden de creación."""
        return [
            (l.lote_id, l.partida_id, l.cantidad_reservada)
            for l in DetalleReserva.objects.filter(reserva__in=resultado.reservas).order_by("pk")
        ]

    def test_regla_primero_las_partidas_por_vencimiento_y_despues_los_lotes(self):
        """Primero las partidas, de la que vence antes a la que vence después (y `id`); después los lotes."""
        base = lote_maduro(self.e, 100)
        tarde = partida(base, 10, fecha_limite=dias(20))
        pronto = partida(base, 10, fecha_limite=dias(10))
        resultado = self.asignar(cantidad=25)
        self.assertEqual(self.lineas(resultado), [(None, pronto.pk, 10), (None, tarde.pk, 10), (base.pk, None, 5)])

    def test_regla_los_lotes_por_fecha_de_entrada_a_maduracion_y_despues_por_menor_stock_libre(self):
        """Los lotes, del que entró antes en Maduración al que entró después y, como desempate, el de menor stock libre."""
        nuevo = lote_maduro(self.e, 10, entrada=dias(-1))
        viejo_grande = lote_maduro(self.e, 40, entrada=dias(-3))
        viejo_chico = lote_maduro(self.e, 6, entrada=dias(-3))
        resultado = self.asignar(cantidad=50)
        self.assertEqual(
            self.lineas(resultado), [(viejo_chico.pk, None, 6), (viejo_grande.pk, None, 40), (nuevo.pk, None, 4)]
        )

    def test_regla_el_orden_se_aplica_igual_con_varios_invernaderos(self):
        """Se aplica igual aunque el stock termine saliendo de varios invernaderos: el lote más antiguo, esté donde esté."""
        sur = segundo_invernadero(self.e)
        norte = lote_maduro(self.e, 10, entrada=dias(-1))
        del_sur = lote_maduro(sur, 10, entrada=dias(-4))
        resultado = self.asignar(cantidad=15)
        self.assertEqual(sorted(self.lineas(resultado)), sorted([(del_sur.pk, None, 10), (norte.pk, None, 5)]))  # primero el más antiguo, esté donde esté
        self.assertEqual(sorted(r.invernadero_id for r in resultado.reservas), sorted([self.e.invernadero.pk, sur.invernadero.pk]))


class ReservasYCosechasTests(BaseDeAsignacion):
    """Postcondiciones a a g y reglas «Una reserva por invernadero», «Una cosecha por reserva con lotes» y «Estado inicial»."""

    def test_post_a_b_c_d_una_reserva_activa_con_su_cosecha_para_cada_invernadero_con_lotes(self):
        """Postcondiciones a, b, c y d: una reserva por invernadero, con una línea por origen (sin cantidad cosechada), «activa» si tiene
        un lote, y una cosecha «a realizar» con la variedad, el invernadero, el Capataz, la fecha de hoy, la programada y prioridad media."""
        lote = lote_maduro(self.e, 100)
        p = partida(lote, 10)
        resultado = self.asignar(cantidad=30)
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (30, 0))
        (reserva_,) = resultado.reservas
        self.assertEqual(
            (reserva_.detalle_venta_id, reserva_.invernadero_id, reserva_.fecha_entrega_reserva, reserva_.fecha_reserva, reserva_.estado_reserva),
            (self.detalle.pk, self.e.invernadero.pk, self.venta.fecha_pactada_venta, HOY, "activa"),
        )
        lineas = list(reserva_.lineas.order_by("pk"))
        self.assertEqual([(l.partida_id, l.lote_id, l.cantidad_reservada, l.cantidad_cosechada) for l in lineas], [(p.pk, None, 10, None), (None, lote.pk, 20, None)])
        (cosecha,) = resultado.cosechas
        self.assertEqual(reserva_.cosecha_id, cosecha.pk)
        self.assertEqual(
            (cosecha.estado_orden, cosecha.tipo_orden, cosecha.variedad_id, cosecha.invernadero_id, cosecha.capataz_id, cosecha.agronomo_id),
            ("a_realizar", "cosecha", self.e.variedad.pk, self.e.invernadero.pk, self.e.capataz.pk, None),
        )
        self.assertEqual((cosecha.prioridad_orden, cosecha.fecha_creacion_orden, cosecha.fecha_programada_orden), ("media", HOY, dias(2)))
        self.assertRegex(cosecha.codigo, r"^OT-\d{4}$")

    def test_post_e_la_cantidad_total_reservada_es_la_menor_entre_lo_pedido_y_el_stock_libre(self):
        """Postcondición e: lo reservado es `min(cantidad, stock maduro libre)`."""
        lote_maduro(self.e, 18)
        self.assertEqual(sum(l.cantidad_reservada for r in self.asignar().reservas for l in r.lineas.all()), 18)

    def test_post_c_una_reserva_solo_de_camara_queda_lista_para_entrega_sin_cosecha(self):
        """Extensión 4a y postcondición c: las partidas cubren todo ⇒ «lista para entrega», sin orden de cosecha y sin avisos."""
        lote = lote_maduro(self.e, 100)
        partida(lote, 40)
        resultado = self.asignar(cantidad=30)
        self.assertEqual([r.estado_reserva for r in resultado.reservas], ["lista_para_entrega"])
        self.assertEqual((resultado.cosechas, Cosecha.objects.count(), Notificacion.objects.count()), ([], 0, 0))
        self.assertIsNone(resultado.reservas[0].cosecha_id)
        self.assertEqual(resultado.cubierta, 30)

    def test_ext_5b_el_stock_de_varios_invernaderos_crea_una_reserva_y_una_cosecha_por_invernadero(self):
        """Extensión 5b: una reserva por invernadero, cada una con su cosecha y el Capataz de ese invernadero."""
        sur = segundo_invernadero(self.e)
        lote_maduro(self.e, 10)
        lote_maduro(sur, 20)
        resultado = self.asignar(cantidad=30)
        self.assertEqual(len(resultado.reservas), 2)
        self.assertEqual(len(resultado.cosechas), 2)
        capataces = {c.invernadero_id: c.capataz_id for c in resultado.cosechas}
        self.assertEqual(capataces, {self.e.invernadero.pk: self.e.capataz.pk, sur.invernadero.pk: sur.capataz.pk})
        self.assertEqual({r.cosecha_id for r in resultado.reservas}, {c.pk for c in resultado.cosechas})
        self.assertEqual(len({c.numero for c in resultado.cosechas}), 2)

    def test_regla_8_8_2_una_cosecha_abarca_varios_lotes_de_un_solo_invernadero(self):
        """Regla «Una cosecha por reserva con lotes»: una sola cosecha con uno o varios lotes del mismo invernadero."""
        a = lote_maduro(self.e, 10, entrada=dias(-2))
        b = lote_maduro(self.e, 10, entrada=dias(-1))
        resultado = self.asignar(cantidad=15)
        self.assertEqual(len(resultado.cosechas), 1)
        self.assertEqual(sorted(l.lote_id for l in resultado.reservas[0].lineas.all()), sorted([a.pk, b.pk]))

    def test_regla_reservar_no_descuenta_stock(self):
        """Regla «Sin descuento de stock» (regla 14 de 8.8): no cambia la cantidad del lote ni la disponible de la partida."""
        lote = lote_maduro(self.e, 50)
        p = partida(lote, 10)
        self.asignar(cantidad=30)
        lote.refresh_from_db()
        p.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, p.cantidad_disponible_cosechado), (50, 10))

    def test_regla_no_cambia_el_estado_del_detalle_ni_de_la_venta_ni_audita(self):
        """Garantía mínima: no cambia el estado del detalle ni del contrato, no planifica entregas; no audita por su cuenta (D-36)."""
        lote_maduro(self.e, 50)
        self.asignar()
        self.detalle.refresh_from_db()
        self.venta.refresh_from_db()
        self.assertEqual((self.detalle.estado_detalle_venta, self.venta.estado_venta), ("abierto", "abierta"))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_ext_5c_cobertura_parcial_reserva_todo_lo_disponible_y_devuelve_lo_que_falta(self):
        """Extensión 5c: reserva todo lo disponible y devuelve la cantidad cubierta y la que quedó sin cubrir."""
        lote_maduro(self.e, 12)
        resultado = self.asignar(cantidad=30)
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (12, 18))

    def test_ext_5d_sin_stock_no_crea_nada_y_devuelve_todo_como_sin_cubrir(self):
        """Extensión 5d: sin stock maduro libre no crea reservas ni cosechas; cubierta 0 y toda la cantidad sin cubrir."""
        resultado = self.asignar(cantidad=30)
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir, resultado.reservas, resultado.cosechas), (0, 30, [], []))
        self.assertEqual((ReservaStock.objects.count(), Cosecha.objects.count()), (0, 0))

    def test_regla_lotes_excluidos_no_se_consideran(self):
        """Parámetro `lotes_excluidos` (PCU 7; lo usa PROD-CNL-ORD en COM-04): esos lotes no se consideran."""
        excluido = lote_maduro(self.e, 100, entrada=dias(-5))
        otro = lote_maduro(self.e, 100, entrada=dias(-1))
        resultado = self.asignar(cantidad=10, lotes_excluidos=[excluido.pk])
        self.assertEqual([l.lote_id for l in resultado.reservas[0].lineas.all()], [otro.pk])

    def test_regla_dos_asignaciones_seguidas_ven_lo_que_reservo_la_primera(self):
        """Regla «Stock libre»: la segunda asignación calcula sobre lo que dejó la primera (sin sobreasignar)."""
        lote_maduro(self.e, 25)
        otra = detalle(compra_venta(self.e, dias=4), self.e.variedad, cantidad=30)
        primera = self.asignar(cantidad=30)
        segunda = self.asignar(cantidad=30, detalle_=otra, fecha=otra.compra_venta.fecha_pactada_venta)
        self.assertEqual((primera.cubierta, segunda.cubierta, segunda.sin_cubrir), (25, 0, 30))


class CapatazActivoTests(BaseDeAsignacion):
    """Extensión 5a: un invernadero considerado sin Capataz activo (la alerta es la `sin_capataz` de `maestros`, D-41)."""

    def sin_capataz(self):
        """Un segundo invernadero del mismo Vendedor SIN Capataz, con un lote en Maduración de 40."""
        sur = segundo_invernadero(self.e, con_capataz=False)
        return sur, lote_maduro(sur, 40)

    def alertas(self, invernadero):
        """Las alertas `sin_capataz` activas del invernadero."""
        return Alerta.objects.filter(invernadero=invernadero, tipo_alerta="sin_capataz", estado_alerta="activa")

    def test_ext_5a_los_lotes_de_un_invernadero_sin_capataz_no_se_asignan_pero_sus_partidas_si(self):
        """Extensión 5a: no se consideran los lotes de ese invernadero; sus partidas de cámara sí."""
        sur, lote = self.sin_capataz()
        p = partida(lote, 7)
        resultado = self.asignar(cantidad=30)
        self.assertEqual((resultado.cubierta, resultado.sin_cubrir), (7, 23))
        self.assertEqual(
            [(l.partida_id, l.lote_id) for r in resultado.reservas for l in r.lineas.all()], [(p.pk, None)]
        )
        self.assertEqual(resultado.reservas[0].estado_reserva, "lista_para_entrega")

    def test_ext_5a_genera_la_alerta_si_faltaba_y_no_la_duplica_si_ya_estaba_activa(self):
        """Extensión 5a: si el invernadero tenía lotes que podían asignarse y no hay alerta activa, se genera (para el Gerente); si ya hay una,
        no se crea otra."""
        sur, _ = self.sin_capataz()
        self.assertEqual(self.alertas(sur.invernadero).count(), 0)
        self.asignar(cantidad=10)
        (alerta,) = self.alertas(sur.invernadero)
        self.assertTrue(alerta.para_gerente)
        self.asignar(cantidad=10, detalle_=detalle(compra_venta(self.e, dias=4), self.e.variedad, 10))
        self.assertEqual(self.alertas(sur.invernadero).count(), 1)

    def test_ext_5a_sin_lotes_que_pudieran_asignarse_no_genera_alerta(self):
        """Extensión 5a: sin lotes asignables en ese invernadero (no hay, o no entran por fecha), no se genera alerta."""
        sur = segundo_invernadero(self.e, con_capataz=False)
        self.asignar(cantidad=10)
        self.assertEqual(self.alertas(sur.invernadero).count(), 0)
        lote_maduro(sur, 40, entrada=dias(-30))  # su fecha máxima de cosecha ya pasó: no podría asignarse
        self.asignar(cantidad=10)
        self.assertEqual(self.alertas(sur.invernadero).count(), 0)

    def test_ext_5a_un_capataz_con_la_cuenta_inactiva_cuenta_como_sin_capataz(self):
        """Regla 5a (R149): Capataz activo = asignado y con la cuenta activa."""
        sur = segundo_invernadero(self.e)
        lote_maduro(sur, 40)
        type(sur.capataz).objects.filter(pk=sur.capataz.pk).update(is_active=False)
        self.assertEqual(self.asignar(cantidad=10).cubierta, 0)
        self.assertEqual(self.alertas(sur.invernadero).count(), 1)

    def test_ext_9a_la_alerta_permanece_si_el_caso_de_uso_base_se_revierte(self):
        """Garantía mínima y extensión 9a: la alerta ya existía antes de la venta (la mantiene `maestros`), así que sigue activa aunque el
        caso de uso base se revierta."""
        sur, _ = self.sin_capataz()
        api_alertas.asegurar_alerta_de_estado(sur.invernadero.pk, "sin_capataz")
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.asignar(cantidad=10)
            raise RuntimeError("el caso de uso base se revierte")
        self.assertEqual(self.alertas(sur.invernadero).count(), 1)


class NotificacionesTests(BaseDeAsignacion):
    """Postcondición h, paso 10 y extensión 10a: las notificaciones (dentro de la transacción del base, D-42; sin reintento)."""

    def test_post_h_cada_cosecha_se_notifica_al_capataz_y_al_agronomo_con_sus_textos(self):
        """Postcondición h: al Capataz (variedad, invernadero, lotes con cantidad y fecha programada) y al Agrónomo, además del contrato, la
        fecha de entrega y que puede modificarla o cancelarla."""
        lote = lote_maduro(self.e, 100)
        resultado = self.asignar(cantidad=30)
        cosecha = resultado.cosechas[0]
        capataz = Notificacion.objects.get(destinatario=self.e.capataz)
        agronomo = Notificacion.objects.get(destinatario=self.e.agronomo)
        self.assertEqual(capataz.titulo, f"Nueva cosecha {cosecha.codigo}")
        esperado = (
            f"Nueva cosecha {cosecha.codigo}: {self.e.variedad}, {self.e.invernadero.nombre_invernadero}. "
            f"Lotes: {lote.codigo} (30 plantas). Fecha programada: {cosecha.fecha_programada_orden:%d/%m/%Y}."
        )
        self.assertEqual(capataz.detalle, esperado)
        self.assertEqual(
            agronomo.detalle,
            f"{esperado} Para {self.venta.codigo}, entrega el {self.venta.fecha_pactada_venta:%d/%m/%Y}. "
            "Podés modificarla o cancelarla desde Órdenes de trabajo.",
        )
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_post_h_sin_agronomo_activo_se_notifica_solo_al_capataz(self):
        """Paso 10 («al Agrónomo del invernadero, si hay uno activo»)."""
        lote_maduro(self.e, 100)
        type(self.e.agronomo).objects.filter(pk=self.e.agronomo.pk).update(is_active=False)
        self.asignar(cantidad=30)
        self.assertEqual(list(Notificacion.objects.values_list("destinatario_id", flat=True)), [self.e.capataz.pk])

    def test_ext_9a_si_el_caso_de_uso_base_se_revierte_no_queda_ninguna_notificacion(self):
        """Extensión 9a: «no queda nada de lo creado por este caso de uso y no se envía ningún aviso» (D-42: las notificaciones van dentro
        de la transacción)."""
        lote_maduro(self.e, 100)
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.asignar(cantidad=30)
            raise RuntimeError("el caso de uso base se revierte")
        self.assertEqual((Notificacion.objects.count(), ReservaStock.objects.count(), Cosecha.objects.count()), (0, 0, 0))

    def test_regla_la_notificacion_larga_se_acorta_a_500_caracteres(self):
        """El detalle de una notificación no pasa de 500: con muchos lotes se acorta con «…» (sin fallar)."""
        for n in range(40):
            lote_maduro(self.e, 1, entrada=dias(-(n % 9)))
        self.asignar(cantidad=40)
        self.assertTrue(all(len(n.detalle) <= 500 for n in Notificacion.objects.all()))
        self.assertEqual(Notificacion.objects.count(), 2)


class DisponibleTests(BaseDeAsignacion):
    """`disponible`: solo lectura, sin bloquear, con consultas fijas (pasos 8, 10 y 14 de COM-REG-CVT)."""

    PEDIDO = 1000

    def consultas(self, variedad_ids):
        """Cuántas consultas hace `disponible` para esas variedades."""
        with CaptureQueriesContext(connection) as capturadas:
            stock_maduro.disponible(variedad_ids, [self.e.invernadero.pk], dias(3), "compra_venta")
        return len(capturadas)

    def test_regla_disponible_suma_lotes_y_partidas_por_variedad(self):
        """Regla «Stock maduro libre disponible»: Σ stock libre de los lotes elegibles + Σ de las partidas elegibles, por variedad."""
        lote = lote_maduro(self.e, 30)
        partida(lote, 12)
        reserva(self.detalle, [(lote, 10)])
        resultado = stock_maduro.disponible([self.e.variedad.pk], [self.e.invernadero.pk], dias(3), "compra_venta")
        self.assertEqual(tuple(resultado[self.e.variedad.pk]), (32, 20, 12))

    def test_regla_disponible_incluye_todas_las_variedades_pedidas_aunque_no_tengan_stock(self):
        """Toda variedad pedida figura (con 0)."""
        resultado = stock_maduro.disponible([self.e.variedad.pk, 999999], [self.e.invernadero.pk], dias(3), "compra_venta")
        self.assertEqual(tuple(resultado[self.e.variedad.pk]), (0, 0, 0))
        self.assertEqual(tuple(resultado[999999]), (0, 0, 0))

    def test_regla_disponible_no_cuenta_los_lotes_de_un_invernadero_sin_capataz_activo(self):
        """Regla «Stock maduro libre disponible»: tampoco cuentan los lotes de un invernadero sin Capataz activo (pero sí sus partidas)."""
        sur = segundo_invernadero(self.e, con_capataz=False)
        lote = lote_maduro(sur, 30)
        partida(lote, 5)
        resultado = stock_maduro.disponible(
            [self.e.variedad.pk], [self.e.invernadero.pk, sur.invernadero.pk], dias(3), "compra_venta"
        )
        self.assertEqual(tuple(resultado[self.e.variedad.pk]), (5, 0, 5))

    def test_regla_disponible_no_hace_consultas_por_lote_ni_por_variedad(self):
        """Requisito «no más de 1 segundo»: una consulta por tabla, nunca una por lote ni por variedad."""
        lote_maduro(self.e, 10)
        una = self.consultas([self.e.variedad.pk])
        for n in range(4):
            lote_maduro(self.e, 10, entrada=dias(-n))
        otras = [self.e.variedad.pk, 999999, 999998]
        self.assertEqual(self.consultas(otras), una)

    def test_regla_disponible_no_escribe_ni_bloquea(self):
        """Solo lectura: no crea nada y funciona fuera de una transacción de negocio (no usa `select_for_update`)."""
        lote_maduro(self.e, 10)
        with CaptureQueriesContext(connection) as capturadas:
            stock_maduro.disponible([self.e.variedad.pk], [self.e.invernadero.pk], dias(3), "compra_venta")
        sql = " ".join(q["sql"].upper() for q in capturadas)
        self.assertNotIn("FOR NO KEY UPDATE", sql)
        self.assertNotIn("INSERT", sql)

    def test_regla_disponible_coincide_con_lo_que_despues_reserva_asignar(self):
        """Lo que `disponible` dice que hay es lo que `asignar` reserva (con la misma fecha y los mismos invernaderos)."""
        lote_maduro(self.e, 30)
        partida(lote_maduro(self.e, 10, entrada=dias(-1)), 12)
        total = stock_maduro.disponible([self.e.variedad.pk], [self.e.invernadero.pk], dias(3), "compra_venta")[self.e.variedad.pk].total
        self.assertEqual(self.asignar(cantidad=1000).cubierta, total)


class RepartirTests(BaseDeAsignacion):
    """`repartir`: la función pura del reparto (la reutiliza COM-03, sección 7 del patrón)."""

    def test_regla_repartir_toma_en_orden_hasta_cubrir(self):
        """Toma de cada candidato, en el orden dado, lo que tenga libre, hasta cubrir la cantidad."""
        tomado, sin_cubrir = stock_maduro.repartir(["a", "b", "c"], {"a": 5, "b": 10, "c": 7}, 12)
        self.assertEqual((tomado, sin_cubrir), ([("a", 5), ("b", 7)], 0))

    def test_regla_repartir_devuelve_lo_que_no_pudo_cubrir(self):
        """Cobertura parcial: reparte todo lo libre y devuelve lo que falta."""
        self.assertEqual(stock_maduro.repartir(["a", "b"], {"a": 5, "b": 3}, 12), ([("a", 5), ("b", 3)], 4))

    def test_regla_repartir_ignora_los_candidatos_sin_libre(self):
        """Un candidato sin stock libre no aparece en lo tomado."""
        self.assertEqual(stock_maduro.repartir(["a", "b"], {"a": 0, "b": 3}, 2), ([("b", 2)], 0))

    def test_regla_repartir_no_lee_la_base(self):
        """Es pura: no hace consultas."""
        with self.assertNumQueries(0):
            stock_maduro.repartir(["a"], {"a": 1}, 1)


class ReservadoDeLotesTests(BaseDeAsignacion):
    """`reservado_de_lotes`: lo que registra `comercial` en `produccion.extensiones` (API de extensiones de `produccion`, sección 5)."""

    def test_ext_con_datos_suma_las_reservas_activas_y_no_las_liberadas_ni_las_de_camara(self):
        """Prueba mínima 1: un lote con dos reservas activas y una liberada devuelve la suma de las activas."""
        lote = lote_maduro(self.e, 100)
        reserva(self.detalle, [(lote, 10)])
        reserva(self.detalle, [(lote, 5)])
        reserva(self.detalle, [(lote, 7)], estado="liberada")
        self.assertEqual(stock_maduro.reservado_de_lotes([lote.pk]), {lote.pk: 15})

    def test_ext_neutro_un_lote_sin_reservas_da_cero_y_una_lista_vacia_no_consulta(self):
        """Prueba mínima 2: un lote sin reservas da 0 (o falta); una lista vacía da `{}` sin consultar la base."""
        lote = lote_maduro(self.e, 100)
        self.assertEqual(stock_maduro.reservado_de_lotes([lote.pk]).get(lote.pk, 0), 0)
        with self.assertNumQueries(0):
            self.assertEqual(stock_maduro.reservado_de_lotes([]), {})

    def test_ext_sin_consultas_por_fila(self):
        """Prueba mínima 3: con tres lotes, las mismas consultas que con uno."""
        lotes = [lote_maduro(self.e, 100) for _ in range(3)]
        with CaptureQueriesContext(connection) as con_uno:
            stock_maduro.reservado_de_lotes([lotes[0].pk])
        with CaptureQueriesContext(connection) as con_tres:
            stock_maduro.reservado_de_lotes([l.pk for l in lotes])
        self.assertEqual(len(con_uno), len(con_tres))
