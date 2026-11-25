# Pruebas de los modelos de COM-02 (docs/modelo/comercial.md: Contrato, CompraVenta, DetalleVenta, ReservaStock y DetalleReserva): una
# prueba por restricción de la base (la viola y no la viola), el código `CV-0001`, la secuencia y el alcance por rol.

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import CompraVenta, Contrato, DetalleReserva, DetalleVenta, ReservaStock
from comercial.servicios import compra_ventas
from comercial.tests.fabricas import compra_venta, detalle, escenario_comercial, partida, reserva, verificar_invariantes_de_reservas
from contabilidad.models import OrigenDocumento
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from core.tests.fabricas import crear_gerente
from produccion.tests.fabricas import lote_maduro


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class ModelosDeContratosTests(ConDatosDeInventario, TestCase):
    """Restricciones de la base de las cinco clases."""

    def setUp(self):
        self.e = escenario_comercial()
        self.venta = compra_venta(self.e)
        self.detalle = detalle(self.venta, self.e.variedad, cantidad=10)

    # ---- Contrato y CompraVenta ----

    def test_regla_el_contrato_es_hijo_de_origen_documento_con_su_tipo_y_su_codigo(self):
        """Ficha de Contrato (D-52): hija directa de `OrigenDocumento` con `tipo = contrato`; el código visible es `CV-{numero:04d}`."""
        self.assertEqual(OrigenDocumento.objects.get(pk=self.venta.pk).tipo, "contrato")
        self.assertEqual(self.venta.codigo, f"CV-{self.venta.numero:04d}")
        self.assertEqual(str(self.venta), self.venta.codigo)
        self.assertEqual(Contrato.objects.get(pk=self.venta.pk).tipo_contrato, "compra_venta")

    def test_regla_el_numero_sale_de_la_secuencia_y_el_primero_es_cv_0001(self):
        """Ficha de Contrato: el número lo asigna la secuencia `comercial_compraventa_numero_seq`; `CV-0001` es el primero (puede haber
        huecos si una transacción se deshace)."""
        with connection.cursor() as cursor:
            cursor.execute("ALTER SEQUENCE comercial_compraventa_numero_seq RESTART WITH 1")
        self.assertEqual(CompraVenta(tipo_contrato="compra_venta", numero=1).codigo, "CV-0001")
        self.assertEqual(CompraVenta(tipo_contrato="suministro", numero=3).codigo, "SUM-0003")
        self.assertEqual(compra_ventas.siguiente_numero(), 1)
        self.assertEqual(compra_ventas.siguiente_numero(), 2)

    def test_regla_numero_unico_por_tipo(self):
        """Ficha de Contrato: `UniqueConstraint(tipo_contrato, numero)`."""
        otra = compra_venta(self.e)
        viola(self, lambda: Contrato.objects.filter(pk=self.venta.pk).update(numero=otra.numero))

    def test_regla_tipo_y_comprobante_dentro_de_su_lista(self):
        """Ficha de Contrato: `tipo_contrato` y `estado_comprobante` dentro de sus listas."""
        viola(self, lambda: Contrato.objects.filter(pk=self.venta.pk).update(tipo_contrato="otro"))
        viola(self, lambda: Contrato.objects.filter(pk=self.venta.pk).update(estado_comprobante="roto"))
        Contrato.objects.filter(pk=self.venta.pk).update(estado_comprobante="enviado")

    def test_regla_estado_de_la_venta_dentro_de_su_lista(self):
        """Ficha de CompraVenta: `estado_venta` en (abierta, pendiente_decision, concretada, cancelada)."""
        viola(self, lambda: CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="rota"))

    def test_regla_envio_exige_direccion_y_sin_invernadero(self):
        """Ficha de CompraVenta: envío ⇒ dirección no nula e invernadero nulo."""
        viola(self, lambda: CompraVenta.objects.filter(pk=self.venta.pk).update(direccion_envio=None))
        viola(self, lambda: CompraVenta.objects.filter(pk=self.venta.pk).update(invernadero_retiro=self.e.invernadero))

    def test_regla_retiro_exige_invernadero_y_sin_direccion(self):
        """Ficha de CompraVenta: retiro ⇒ invernadero no nulo y dirección nula."""
        retiro = compra_venta(self.e, modalidad="retiro")
        self.assertEqual((retiro.direccion_envio_id, retiro.invernadero_retiro_id), (None, self.e.invernadero.pk))
        viola(self, lambda: CompraVenta.objects.filter(pk=retiro.pk).update(invernadero_retiro=None))
        viola(self, lambda: CompraVenta.objects.filter(pk=retiro.pk).update(direccion_envio=self.e.direccion))

    # ---- DetalleVenta ----

    def test_regla_una_variedad_por_venta(self):
        """Regla 2 de 8.11 y ficha de DetalleVenta: `UniqueConstraint(compra_venta, variedad)`."""
        viola(self, lambda: detalle(self.venta, self.e.variedad, cantidad=1))

    def test_regla_cantidad_solicitada_al_menos_uno(self):
        """Ficha de DetalleVenta: `cant_solicitada_venta >= 1`."""
        otra = compra_venta(self.e)
        viola(self, lambda: detalle(otra, self.e.variedad, cantidad=0))
        detalle(otra, self.e.variedad, cantidad=1)

    def test_regla_precio_mayor_que_cero(self):
        """Ficha de DetalleVenta: `precio_unitario_de_venta > 0`."""
        otra = compra_venta(self.e)
        viola(self, lambda: detalle(otra, self.e.variedad, precio="0.00"))
        viola(self, lambda: detalle(otra, self.e.variedad, precio="-1.00"))
        self.assertEqual(detalle(otra, self.e.variedad, precio="0.01").precio_unitario_de_venta, Decimal("0.01"))

    def test_regla_cantidad_entregada_nula_o_no_negativa_y_estado_en_su_lista(self):
        """Ficha de DetalleVenta: `cant_entregada_venta` nula o `>= 0`; estado dentro de su lista."""
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(cant_entregada_venta=0)
        viola(self, lambda: DetalleVenta.objects.filter(pk=self.detalle.pk).update(cant_entregada_venta=-1))
        viola(self, lambda: DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="roto"))
        self.assertEqual(self.detalle.estado_detalle_venta, "abierto")
        self.assertEqual(str(self.detalle), f"{self.venta.codigo} · {self.e.variedad}")

    # ---- ReservaStock y DetalleReserva ----

    def test_regla_estado_de_la_reserva_dentro_de_su_lista(self):
        """Ficha de ReservaStock: `estado_reserva` en (activa, lista_para_entrega, entregada, liberada)."""
        lote = lote_maduro(self.e, 20)
        r = reserva(self.detalle, [(lote, 5)])
        viola(self, lambda: ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="rota"))

    def test_regla_c1_la_linea_es_de_un_lote_o_de_una_partida_nunca_de_los_dos_ni_de_ninguno(self):
        """C1: exactamente uno de `lote` y `partida`."""
        lote = lote_maduro(self.e, 20)
        r = reserva(self.detalle, [(lote, 5)])
        p = partida(lote, 10)
        viola(self, lambda: DetalleReserva.objects.create(reserva=r, lote=lote, partida=p, cantidad_reservada=1))
        viola(self, lambda: DetalleReserva.objects.create(reserva=r, cantidad_reservada=1))
        DetalleReserva.objects.create(reserva=r, partida=p, cantidad_reservada=1)

    def test_regla_la_linea_de_lote_reserva_al_menos_uno_y_la_de_partida_admite_cero(self):
        """D-64 punto 7 (COM-02 ya la crea así): `cantidad_reservada >= 1`, salvo en una línea de partida, que admite 0."""
        lote = lote_maduro(self.e, 20)
        r = reserva(self.detalle, [(lote, 5)])
        p = partida(lote, 10)
        viola(self, lambda: DetalleReserva.objects.create(reserva=r, lote=lote, cantidad_reservada=0))
        DetalleReserva.objects.create(reserva=r, partida=p, cantidad_reservada=0)

    def test_regla_cantidad_cosechada_de_una_partida_es_nula(self):
        """Ficha de DetalleReserva: con `partida`, `cantidad_cosechada` nula; en un lote, nula o `>= 0` (el 0 es lo que rindió)."""
        lote = lote_maduro(self.e, 20)
        r = reserva(self.detalle, [(lote, 5)])
        p = partida(lote, 10)
        viola(self, lambda: DetalleReserva.objects.create(reserva=r, partida=p, cantidad_reservada=1, cantidad_cosechada=0))
        DetalleReserva.objects.create(reserva=r, lote=lote, cantidad_reservada=1, cantidad_cosechada=0)

    def test_regla_una_cosecha_tiene_a_lo_sumo_una_reserva(self):
        """R087: `ReservaStock.cosecha` es un `OneToOneField`: la base garantiza una sola reserva por cosecha."""
        lote = lote_maduro(self.e, 20)
        r = reserva(self.detalle, [(lote, 5)])
        viola(self, lambda: ReservaStock.objects.create(
            invernadero=self.e.invernadero, estado_reserva="activa", cosecha=r.cosecha, detalle_venta=self.detalle
        ))

    def test_regla_una_reserva_sin_detalle_ni_fecha_de_entrega_es_valida_en_la_base(self):
        """D-64 punto 6: `fecha_entrega_reserva` y `detalle_venta` pueden ser nulos (la reserva de una cosecha sin contrato, COM-04)."""
        lote = lote_maduro(self.e, 20)
        r = ReservaStock.objects.create(invernadero=self.e.invernadero, estado_reserva="activa")
        DetalleReserva.objects.create(reserva=r, lote=lote, cantidad_reservada=1)
        self.assertIsNone(r.fecha_entrega_reserva)


class AlcanceDeContratosTests(ConDatosDeInventario, TestCase):
    """`ContratoQuerySet.en_alcance_de(actor)`: un único lugar para el alcance (D-28)."""

    def setUp(self):
        self.e = escenario_comercial()
        self.otro = escenario_comercial(sufijo="2")
        self.mia = compra_venta(self.e)
        self.ajena = compra_venta(self.otro, cliente_=self.e.cliente)

    def pks(self, actor):
        """Los ids de los contratos que ve `actor`."""
        return set(Contrato.objects.en_alcance_de(actor).values_list("pk", flat=True))

    def test_regla_el_gerente_ve_todos_y_el_vendedor_solo_los_suyos(self):
        """Ficha de Contrato, «Alcance»: el Gerente activo ve todos; el Vendedor activo, solo aquellos de los que es `vendedor`."""
        self.assertEqual(self.pks(crear_gerente()), {self.mia.pk, self.ajena.pk})
        self.assertEqual(self.pks(self.e.vendedor), {self.mia.pk})
        self.assertEqual(self.pks(self.otro.vendedor), {self.ajena.pk})

    def test_regla_cualquier_otro_rol_o_una_cuenta_inactiva_no_ve_ninguno(self):
        """Ficha de Contrato, «Alcance»: cualquier otro rol (y una cuenta inactiva o `None`), ninguno."""
        inactivo = crear_vendedor(email="inactivo@infoponia.com", activo=False)
        for actor in (crear_agronomo(email="agro@infoponia.com"), inactivo, None):
            with self.subTest(actor=actor):
                self.assertEqual(self.pks(actor), set())

    def test_regla_el_alcance_tambien_vale_para_la_compra_venta(self):
        """`CompraVenta.objects` hereda el alcance del contrato."""
        self.assertEqual(set(CompraVenta.objects.en_alcance_de(self.e.vendedor).values_list("pk", flat=True)), {self.mia.pk})


class CompraVentaCancelacionModeloTests(ConDatosDeInventario, TestCase):
    """COM-05b, MD-130 (docs/modelo/comercial.md, «CompraVenta»): los tres datos de la cancelación y sus restricciones de la base."""

    def setUp(self):
        self.e = escenario_comercial()
        self.venta = compra_venta(self.e)

    def _actualizar(self, **campos):
        return lambda: CompraVenta.objects.filter(pk=self.venta.pk).update(**campos)

    def test_regla_md130_una_venta_nueva_nace_sin_datos_de_cancelacion(self):
        """MD-130: motivo y fecha nulos y descripción vacía en toda venta que no se canceló con COM-CNL-CVT."""
        self.assertIsNone(self.venta.motivo_cancelacion_venta)
        self.assertIsNone(self.venta.fecha_cancelacion_venta)
        self.assertEqual(self.venta.descripcion_cancelacion, "")

    def test_regla_md130_la_lista_de_motivos_es_cerrada(self):
        """MD-130: `cliente_desistio`, `cliente_no_retiro` y `otro`; cualquier otro valor lo rechaza la base."""
        hoy = timezone.localdate()
        self.assertEqual(
            [valor for valor, _ in CompraVenta.MotivoCancelacion.choices], ["cliente_desistio", "cliente_no_retiro", "otro"]
        )
        viola(self, self._actualizar(estado_venta="cancelada", motivo_cancelacion_venta="porque_si", fecha_cancelacion_venta=hoy))
        for motivo in ("cliente_desistio", "cliente_no_retiro", "otro"):
            CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="cancelada", motivo_cancelacion_venta=motivo, fecha_cancelacion_venta=hoy)

    def test_regla_md130_motivo_y_fecha_van_juntos(self):
        """MD-130: `motivo_cancelacion_venta` no nulo ⇔ `fecha_cancelacion_venta` no nula."""
        hoy = timezone.localdate()
        viola(self, self._actualizar(estado_venta="cancelada", motivo_cancelacion_venta="otro", fecha_cancelacion_venta=None))
        viola(self, self._actualizar(estado_venta="cancelada", motivo_cancelacion_venta=None, fecha_cancelacion_venta=hoy))
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="cancelada", motivo_cancelacion_venta="otro", fecha_cancelacion_venta=hoy)

    def test_regla_md130_el_motivo_solo_con_venta_cancelada_o_concretada(self):
        """MD-130: motivo no nulo ⇒ `estado_venta` en (`cancelada`, `concretada`) (la segunda, cuando COM-08b cobre lo entregado)."""
        hoy = timezone.localdate()
        for estado in ("abierta", "pendiente_decision"):
            viola(self, self._actualizar(estado_venta=estado, motivo_cancelacion_venta="cliente_desistio", fecha_cancelacion_venta=hoy))
        for estado in ("cancelada", "concretada"):
            CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta=estado, motivo_cancelacion_venta="cliente_desistio", fecha_cancelacion_venta=hoy)

    def test_regla_md130_la_descripcion_exige_motivo(self):
        """MD-130: `descripcion_cancelacion` no vacía ⇒ motivo no nulo."""
        hoy = timezone.localdate()
        viola(self, self._actualizar(descripcion_cancelacion="Se arrepintió"))
        CompraVenta.objects.filter(pk=self.venta.pk).update(
            estado_venta="cancelada", motivo_cancelacion_venta="otro", fecha_cancelacion_venta=hoy, descripcion_cancelacion="Se arrepintió"
        )

    def test_regla_md130_una_venta_cancelada_por_faltante_sin_motivo_no_viola_ninguna(self):
        """MD-130 y COM-DCD-FLT: una venta que queda «cancelada» porque el cliente rechazó todo no lleva motivo, fecha ni descripción."""
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="cancelada")
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado_venta, "cancelada")
        self.assertIsNone(self.venta.motivo_cancelacion_venta)

    def test_regla_md130_el_detalle_admite_el_estado_cancelado(self):
        """MD-130: `estado_detalle_venta = cancelado` (ya existe desde COM-02): la base lo admite y sigue rechazando uno fuera de la lista."""
        d = detalle(self.venta, self.e.variedad, cantidad=5)
        DetalleVenta.objects.filter(pk=d.pk).update(estado_detalle_venta="cancelado")
        viola(self, lambda: DetalleVenta.objects.filter(pk=d.pk).update(estado_detalle_venta="anulado"))
