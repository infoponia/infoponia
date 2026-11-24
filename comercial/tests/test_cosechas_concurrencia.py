# Pruebas de concurrencia de las cosechas (COM-04a, pasos 4 y 5; docs/patrones/bloqueos.md, sección `comercial`, «Cosecha y cámara», y
# docs/patrones/stock_maduro.md, sección 3): dos planificaciones por el último stock de un lote; una planificación contra una compra-venta; modificar contra
# concretar; concretar contra cancelar; dos concreciones de la misma orden; concretar contra una venta que toma el stock libre del lote. Dos hilos, dos
# conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Cada una termina verificando los invariantes de las reservas. Nunca un error 500:
# el que pierde recibe un rechazo claro (`ValidationError`). Las ventas se hacen con retiro (sin Georef: el `flush` de estas pruebas vacía las tablas).
# El bloqueo que las ordena: cuentas → invernaderos → variedades → sectores → lotes → partidas → contrato → detalles → la cosecha (`OrdenTrabajo`) →
# su reserva y sus líneas.

from datetime import timedelta

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva
from comercial.servicios import compra_ventas, cosechas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.servicios.cosechas import DatosDeCosecha, DatosDeConcrecion, DatosDeModificacion
from comercial.tests.fabricas import compra_venta, cosecha_manual, detalle, escenario_comercial, verificar_invariantes_de_reservas
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Cosecha, Lote, MovimientoStock
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar

HOY = timezone.localdate()


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


@tag("concurrencia")
class CosechasConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, plantas=100, reservadas=30):
        """El escenario sin Georef, un lote de `plantas` y una cosecha con contrato (venta con retiro de 50) que reserva `reservadas`."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, plantas)
        self.sector = self.e.sectores["maduracion"]
        self.venta = compra_venta(self.e, dias=10, modalidad="retiro", retiro=self.e.invernadero)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, reservadas)], detalle_=self.detalle, dias=5) if reservadas else None
        self.addCleanup(verificar_invariantes_de_reservas)

    # ---- las operaciones ----

    def planificar(self, plantas, dias=5):
        """Planifica, como el Agrónomo, una cosecha SIN contrato de `plantas` del lote."""
        datos = DatosDeCosecha(
            invernadero_id=self.e.invernadero.pk, variedad_id=self.e.variedad.pk, fecha_programada=en(dias), prioridad="media", lotes=((self.lote.pk, plantas),)
        )
        return lambda: cosechas.planificar_cosecha(self.e.agronomo, datos)

    def vender(self, cantidad):
        """Registra, como el Vendedor, una compra-venta con retiro de `cantidad` plantas."""
        datos = DatosDeCompraVenta(
            cliente_id=str(self.e.cliente.pk),
            fecha_pactada=str(en(3)),
            modalidad="retiro",
            invernadero_id=str(self.e.invernadero.pk),
            renglones=[Renglon(0, str(self.e.variedad.pk), str(cantidad), "100")],
        )
        return lambda: compra_ventas.registrar_compra_venta(self.e.vendedor, datos)

    def concretar(self, plantas):
        """Concreta la cosecha, como su Capataz, cosechando `plantas` del lote."""
        datos = DatosDeConcrecion(cantidades=((self.lote.pk, self.sector.pk, plantas),))
        return lambda: cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)

    def modificar(self, huella, **cambios):
        """Modifica la cosecha, como el Agrónomo (con la huella que leyó al abrirla)."""
        valores = dict(fecha_programada=en(5), prioridad="media", descripcion="", lotes=((self.lote.pk, 30),))
        valores.update(cambios)
        datos = DatosDeModificacion(**valores)
        return lambda: cosechas.modificar_cosecha(self.e.agronomo, self.cosecha.pk, datos, huella)

    def cancelar(self, huella):
        """Cancela la cosecha, como el Agrónomo."""
        return lambda: cosechas.cancelar_cosecha(self.e.agronomo, self.cosecha.pk, "Se cancela", huella)

    def releer(self):
        return Cosecha.objects.get(pk=self.cosecha.pk)

    # ---- planificar ----

    def test_regla_dos_planificaciones_por_el_ultimo_stock_de_un_lote_una_registra_y_la_otra_no_alcanza(self):
        """PROD-PNF-CSC, concurrencia: un lote de 30 y dos planificaciones de 30 (sin contrato). La segunda espera al lote, relee el stock libre (0) y recibe
        `supera_stock_libre` (15b); el lote nunca queda reservado por encima de su stock libre."""
        self.armar(plantas=30, reservadas=0)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.planificar(30, 5), self.planificar(30, 6), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("supera_stock_libre", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Cosecha.objects.count(), 1)
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=self.lote)), 30)

    def test_regla_una_planificacion_contra_una_compra_venta_por_el_mismo_stock(self):
        """Una planificación de 50 y una venta de 50 sobre un lote de 50: gana la que toma el lote primero, la otra recibe su rechazo (`supera_stock_libre` o
        `stock_insuficiente`); no queda nada reservado de más."""
        self.armar(plantas=50, reservadas=0)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.planificar(50), self.vender(50), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertTrue({"supera_stock_libre", "stock_insuficiente"} & set(codigos_del_rechazo(rechazos[0])))
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=self.lote)), 50)

    # ---- modificar contra concretar ----

    def test_regla_concretar_primero_y_la_modificacion_ve_la_cosecha_resuelta(self):
        """PROD-MOD-CSC 10a: con la concreción primero, la modificación espera la fila de la cosecha, la relee «concretada» y recibe `cosecha_resuelta`: no
        cambia nada de lo concretado."""
        self.armar()
        huella = cosechas.huella_de(self.releer())
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(30), self.modificar(huella, prioridad="alta"), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("cosecha_resuelta", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((self.releer().estado_orden, self.releer().prioridad_orden), ("concretada", "media"))
        self.assertEqual(MovimientoStock.objects.filter(tipo_movimiento="salida_por_cosecha").count(), 1)

    def test_regla_modificar_primero_y_la_concrecion_toma_lo_modificado(self):
        """Con la modificación primero (cambia el lote al otro de 40), la concreción espera, relee las líneas nuevas y las concreta: las dos se registran."""
        self.armar()
        otro = lote_maduro(self.e, 40)
        huella = cosechas.huella_de(self.releer())
        datos = DatosDeConcrecion(cantidades=((otro.pk, self.sector.pk, 30),))
        concretar_el_otro = lambda: cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)  # noqa: E731
        exitos, rechazos, otros = separar(correr_a_la_vez(self.modificar(huella, lotes=((otro.pk, 30),)), concretar_el_otro, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Lote.objects.get(pk=otro.pk).cantidad_actual, 10)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 100)

    # ---- concretar contra cancelar y contra sí misma ----

    def test_regla_concretar_contra_cancelar_gana_el_primero_y_el_otro_ve_el_estado_actual(self):
        """PROD-CNC-CSC 13b y PROD-CNL-ORD 8a: con la concreción primero, la cancelación recibe `orden_no_a_realizar`; con la cancelación primero, la
        concreción. Nunca las dos."""
        self.armar()
        huella = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(30), self.cancelar(huella), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(self.releer().estado_orden, "concretada")

    def test_regla_cancelar_primero_y_la_concrecion_se_rechaza(self):
        """El orden inverso: la cancelación gana y la concreción recibe `orden_no_a_realizar`; no hay movimientos de stock."""
        self.armar()
        huella = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(huella), self.concretar(30), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(self.releer().estado_orden, "cancelada")
        self.assertFalse(MovimientoStock.objects.filter(tipo_movimiento="salida_por_cosecha").exists())

    def test_regla_dos_concreciones_de_la_misma_orden_una_sola_se_registra(self):
        """«Una orden de cosecha se concreta una única vez»: la segunda espera, relee y recibe `orden_no_a_realizar`; el lote baja una sola vez."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(30), self.concretar(30), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 70)

    # ---- concretar contra una venta ----

    def test_regla_una_venta_que_toma_el_stock_libre_primero_y_la_concrecion_ve_el_nuevo_maximo(self):
        """13c: lote de 100, 30 reservados por la cosecha. Con la venta de 70 primero, el máximo de la concreción baja a 30 (+0 libre): cosechar 100 recibe
        `supera_maximo`; la venta queda registrada."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.vender(70), self.concretar(100), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("supera_maximo", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(CompraVenta.objects.exclude(pk=self.venta.pk).count(), 1)
        self.assertEqual(self.releer().estado_orden, "a_realizar")

    def test_regla_una_concrecion_primero_deja_el_excedente_en_la_camara_y_la_venta_lo_toma(self):
        """El orden inverso: con la concreción primero (cosecha 100 de 100 reservadas 30, máximo 100), lo que sobra (70) ingresa a la cámara; la venta espera,
        relee y se cubre con esa partida: las dos se registran y el lote queda sin plantas."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(100), self.vender(70), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(self.releer().estado_orden, "concretada")
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida__isnull=False)), 70)
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 0)
