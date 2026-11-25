# Pruebas de lo que COM-04a suma a los modelos de `comercial` (paso 2): la restricción de `ReservaStock` (fecha de entrega nula si y solo si no
# hay detalle), la de `DetalleReserva` (una línea de partida admite 0; una de lote, no), las fábricas `partida_cosechada` y `cosecha_manual` y los
# invariantes nuevos de `verificar_invariantes_de_reservas`. Una prueba por restricción.
# Fuente: docs/modelo/comercial.md («ReservaStock», «DetalleReserva»), D-64 puntos 6 y 7 y la sección 8 de docs/patrones/stock_maduro.md.

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import DetalleReserva, EnlaceCliente, ReservaStock
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    enlace,
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


class RestriccionDeAlertaComercialTests(Base):
    """COM-04b (D-63 punto 1, MD-134): `AlertaComercial.partida` y la restricción «exactamente un origen» reescrita con tres FK."""

    def alerta(self, **vinculo):
        """Una alerta de `maestros` y su `AlertaComercial` con los `vinculo` pedidos."""
        from comercial.models import AlertaComercial
        from maestros.tests.fabricas import crear_alerta

        base = crear_alerta(self.e.invernadero, "comercial_partida_por_vencer")
        return AlertaComercial.objects.create(alerta=base, **vinculo)

    def test_regla_d63_1_una_alerta_con_solo_partida_es_valida(self):
        """D-63 punto 1: la FK `partida` es un origen más (MD-134, «partida por vencer»)."""
        partida = partida_cosechada(self.lote, 5)
        self.assertEqual(self.alerta(partida=partida).partida_id, partida.pk)

    def test_regla_d63_1_una_alerta_sin_ningun_origen_se_rechaza(self):
        """D-63 punto 1: exactamente una FK de origen; ninguna se rechaza."""
        viola(self, lambda: self.alerta())

    def test_regla_d63_1_partida_junto_con_otro_origen_se_rechaza(self):
        """D-63 punto 1: `partida` y `detalle_suministro` (o `suministro`) a la vez se rechazan."""
        from comercial.tests.fabricas import detalle_suministro, suministro

        partida = partida_cosechada(self.lote, 5)
        contrato = suministro(self.e)
        det = detalle_suministro(contrato, self.e.variedad)
        viola(self, lambda: self.alerta(partida=partida, detalle_suministro=det, fecha_periodo=HOY, cantidad_sin_cubrir=1))
        viola(self, lambda: self.alerta(partida=partida, suministro=contrato))


class EnlaceClienteModeloTests(Base):
    """COM-04c, paso 1 (D-65; docs/modelo/comercial.md, «EnlaceCliente»): las restricciones de la base de `EnlaceCliente`."""

    def test_regla_el_token_resumen_es_unico(self):
        """D-65 punto 2: no puede haber dos enlaces con el mismo resumen de token (es el índice por el que se los busca)."""
        existente, _ = enlace(self.venta)
        otra = compra_venta(self.e)
        viola(self, lambda: EnlaceCliente.objects.create(cliente=otra.cliente, compra_venta=otra, token_resumen=existente.token_resumen, fecha_vencimiento=HOY))

    def test_regla_un_solo_vigente_por_venta_y_tipo_pero_un_usado_convive(self):
        """D-65 punto 5: a lo sumo un enlace `vigente` por (venta, tipo); los que ya no están vigentes no cuentan."""
        enlace(self.venta, estado="usado")
        enlace(self.venta, estado="reemplazado")
        enlace(self.venta)  # el único vigente
        viola(self, lambda: enlace(self.venta))

    def test_regla_usado_si_y_solo_si_tiene_fecha_de_uso(self):
        """Modelo, «EnlaceCliente»: `estado = usado` <=> `fecha_uso` no nula."""
        viola(self, lambda: EnlaceCliente.objects.create(cliente=self.venta.cliente, compra_venta=self.venta, token_resumen="a" * 64, estado="usado", fecha_vencimiento=HOY))
        viola(
            self,
            lambda: EnlaceCliente.objects.create(
                cliente=self.venta.cliente, compra_venta=self.venta, token_resumen="b" * 64, estado="anulado", fecha_uso=timezone.now(), fecha_vencimiento=HOY
            ),
        )

    def test_regla_la_decision_de_faltante_exige_la_venta(self):
        """Modelo, «EnlaceCliente»: `tipo = decision_faltante` => `compra_venta` no nula."""
        viola(self, lambda: EnlaceCliente.objects.create(cliente=self.venta.cliente, compra_venta=None, token_resumen="c" * 64, fecha_vencimiento=HOY))

    def test_regla_el_estado_y_el_estado_de_envio_son_de_listas_cerradas(self):
        """D-65 puntos 1 y 6: `estado` y `estado_envio` solo admiten sus valores."""
        viola(self, lambda: EnlaceCliente.objects.create(cliente=self.venta.cliente, compra_venta=self.venta, token_resumen="d" * 64, estado="roto", fecha_vencimiento=HOY))
        viola(self, lambda: EnlaceCliente.objects.create(cliente=self.venta.cliente, compra_venta=self.venta, token_resumen="e" * 64, estado_envio="roto", fecha_vencimiento=HOY))

    def test_regla_la_fabrica_guarda_el_resumen_y_nunca_el_token(self):
        """D-65 punto 2: la fila no contiene el token, solo su SHA-256 de 64 caracteres."""
        creado, token = enlace(self.venta)
        self.assertEqual(len(creado.token_resumen), 64)
        self.assertNotEqual(creado.token_resumen, token)
        self.assertNotIn(token, str(EnlaceCliente.objects.filter(pk=creado.pk).values().first()))
