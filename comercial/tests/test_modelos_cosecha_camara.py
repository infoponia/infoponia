# Pruebas de lo que COM-04a suma a los modelos de `comercial` (paso 2): la restricción de `ReservaStock` (fecha de entrega nula si y solo si no
# hay detalle), la de `DetalleReserva` (una línea de partida admite 0; una de lote, no), las fábricas `partida_cosechada` y `cosecha_manual` y los
# invariantes nuevos de `verificar_invariantes_de_reservas`. Una prueba por restricción.
# Fuente: docs/modelo/comercial.md («ReservaStock», «DetalleReserva»), D-64 puntos 6 y 7 y la sección 8 de docs/patrones/stock_maduro.md.

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import DetalleReserva, ReservaStock
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    escenario_comercial,
    partida_cosechada,
    reserva,
    verificar_invariantes_de_reservas,
)
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Bitacora, MovimientoStock
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 100)
        cls.venta = compra_venta(cls.e)
        cls.detalle = detalle(cls.venta, cls.e.variedad, 50)


class RestriccionesDeReservaTests(Base):
    def crear(self, **campos):
        """Una `ReservaStock` con lo mínimo y los `campos` pisados."""
        valores = dict(invernadero=self.e.invernadero, estado_reserva="activa")
        valores.update(campos)
        return ReservaStock.objects.create(**valores)

    def test_regla_d64_6_la_reserva_sin_detalle_no_tiene_fecha_de_entrega(self):
        """D-64 punto 6: `fecha_entrega_reserva` nula ⇔ sin `detalle_venta` ni `detalle_suministro`: la de una cosecha sin contrato se guarda sin
        fecha; con fecha y sin detalle, se rechaza."""
        self.crear()
        viola(self, lambda: self.crear(fecha_entrega_reserva=HOY))

    def test_regla_d64_6_la_reserva_con_detalle_tiene_fecha_de_entrega(self):
        """D-64 punto 6: con `detalle_venta`, la fecha de entrega es obligatoria."""
        viola(self, lambda: self.crear(detalle_venta=self.detalle))
        self.assertEqual(self.crear(detalle_venta=self.detalle, fecha_entrega_reserva=HOY).fecha_entrega_reserva, HOY)


class RestriccionesDeLineaTests(Base):
    def test_regla_d64_7_una_linea_de_partida_admite_cero_y_una_de_lote_no(self):
        """D-64 punto 7: `cantidad_reservada >= 1`, salvo una línea de partida, que admite 0 (el recorte de la merma en cámara)."""
        partida = partida_cosechada(self.lote, 5)
        r = reserva(self.detalle, [(partida, 5)])
        linea = r.lineas.get()
        DetalleReserva.objects.filter(pk=linea.pk).update(cantidad_reservada=0)
        self.assertEqual(DetalleReserva.objects.get(pk=linea.pk).cantidad_reservada, 0)
        viola(self, lambda: DetalleReserva.objects.create(reserva=r, lote=self.lote, cantidad_reservada=0))


class FabricasTests(Base):
    def test_regla_cosecha_manual_con_y_sin_contrato(self):
        """`cosecha_manual`: una cosecha `manual` del Agrónomo con su reserva «activa»; con detalle lleva su fecha de entrega, sin contrato no."""
        con = cosecha_manual(self.e, [(self.lote, 20)], detalle_=self.detalle)
        sin = cosecha_manual(self.e, [(self.lote, 10)])
        self.assertEqual((con.origen_cosecha, con.agronomo_id, con.reserva.detalle_venta_id), ("manual", self.e.agronomo.pk, self.detalle.pk))
        self.assertEqual(con.reserva.fecha_entrega_reserva, self.venta.fecha_pactada_venta)
        self.assertEqual((sin.reserva.detalle_venta_id, sin.reserva.fecha_entrega_reserva), (None, None))
        verificar_invariantes_de_reservas()

    def test_regla_partida_cosechada_trae_su_ingreso_a_camara(self):
        """Invariante: toda partida nace con su movimiento `ingreso_a_camara` (cantidad y costo de la partida)."""
        partida = partida_cosechada(self.lote, 7, costo="2.5000")
        m = MovimientoStock.objects.get(partida=partida)
        self.assertEqual((m.tipo_movimiento, m.cantidad, str(m.costo_unitario)), ("ingreso_a_camara", 7, "2.5000"))


class InvariantesTests(Base):
    def test_regla_los_invariantes_nuevos_detectan_lo_que_corresponde(self):
        """Sección 8 del patrón de stock: una partida sin su ingreso, una reserva sin contrato de una cosecha automática, una concretada sin
        bitácora ni cantidad cosechada y una «lista para entrega» con una línea de lote sin cosechar rompen `verificar_invariantes_de_reservas`."""
        verificar_invariantes_de_reservas()
        partida = partida_cosechada(self.lote, 5)
        MovimientoStock.objects.filter(partida=partida).delete()
        with self.assertRaisesMessage(AssertionError, "sin su ingreso a cámara"):
            verificar_invariantes_de_reservas()
        partida.delete()
        automatica = cosecha_manual(self.e, [(self.lote, 10)], origen="automatica")
        with self.assertRaisesMessage(AssertionError, "sin ser de una cosecha manual"):
            verificar_invariantes_de_reservas()
        automatica.reserva.lineas.all().delete()
        automatica.reserva.delete()
        automatica.delete()
        concretada = cosecha_manual(self.e, [(self.lote, 10)], detalle_=self.detalle)
        concretada.estado_orden, concretada.fecha_resolucion_orden = "concretada", HOY
        concretada.save()
        with self.assertRaisesMessage(AssertionError, "sin cantidad cosechada"):
            verificar_invariantes_de_reservas()
        concretada.reserva.estado_reserva = "lista_para_entrega"
        concretada.reserva.save()
        with self.assertRaisesMessage(AssertionError, "sin cosechar"):
            verificar_invariantes_de_reservas()
        concretada.reserva.lineas.update(cantidad_cosechada=10)
        Bitacora.objects.create(
            invernadero=self.e.invernadero, lote=self.lote, etapa=self.lote.etapa, tipo_evento="cosecha", cosecha=concretada,
            fecha_bitacora=HOY, hora_bitacora=timezone.localtime().time(),
        )
        verificar_invariantes_de_reservas()
