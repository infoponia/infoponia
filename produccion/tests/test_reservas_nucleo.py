# Pruebas del núcleo de reservas de insumo de `produccion` (COM-05a2, paso 1): `reservas.reservar`, `cambiar_cantidad` y `cancelar`.
# Corren en la transacción de quien las llama (sin ella, `RuntimeError`), no auditan ni notifican, no validan contra el stock y devuelven la reserva.
# Fuente: docs/api/produccion.md, sección 9 («Lo que suma COM-05a2»); D-66 punto 8; docs/casos_de_uso/produccion/envasado.md (postcondiciones a y b).

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.errores import ErrorDeProduccion
from produccion.models import OrdenTrabajo, ReservaInsumo
from produccion.servicios import reservas
from produccion.tests.fabricas import invernadero_con_produccion, orden_suelta

Tipo = OrdenTrabajo.Tipo
HOY = timezone.localdate()


class ReservasNucleoTests(ConDatosDeInventario, TestCase):
    """Las tres funciones de núcleo, cada una con su efecto y cada error. Usan órdenes sueltas de entrega (D-67 punto 1d)."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.iin = cls.e.existencia_semilla

    def setUp(self):
        self.orden = orden_suelta(self.e.invernadero, Tipo.ENTREGA)

    # ---- reservar ----

    def test_post_a_reservar_crea_una_reserva_activa_con_cantidad_y_fecha(self):
        """Postcondición a de PROD-PNF-ENV: «activa», con la cantidad y la fecha de reserva indicadas, utilizada y devuelta vacías."""
        fecha = HOY - timedelta(days=2)
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, Decimal("12.5"), fecha)
        reserva.refresh_from_db()
        self.assertEqual(reserva.orden_id, self.orden.pk)
        self.assertEqual(reserva.insumo_invernadero_id, self.iin.pk)
        self.assertEqual(reserva.estado, ReservaInsumo.Estado.ACTIVA)
        self.assertEqual(reserva.cantidad_reservada, Decimal("12.5"))
        self.assertEqual(reserva.fecha_reserva, fecha)
        self.assertIsNone(reserva.cantidad_utilizada)
        self.assertIsNone(reserva.cantidad_devuelta)

    def test_regla_reservar_rechaza_un_insumo_que_la_orden_ya_tiene_activo(self):
        """API sección 9: `reserva_duplicada` si la orden ya tiene una activa de ese insumo (antes de insertar, sin IntegrityError)."""
        with transaction.atomic():
            reservas.reservar(self.orden, self.iin, 5, HOY)
        with self.assertRaises(ErrorDeProduccion) as ctx, transaction.atomic():
            reservas.reservar(self.orden, self.iin, 3, HOY)
        self.assertEqual(ctx.exception.codigo, "reserva_duplicada")
        self.assertEqual(ReservaInsumo.objects.filter(orden=self.orden).count(), 1)

    def test_regla_reservar_otra_vez_un_insumo_cancelado_crea_una_reserva_nueva(self):
        """D-66 punto 8: un envase quitado (reserva «cancelada») puede volver a agregarse: dos filas, una cancelada y una activa."""
        with transaction.atomic():
            primera = reservas.reservar(self.orden, self.iin, 5, HOY)
            reservas.cancelar(primera)
            segunda = reservas.reservar(self.orden, self.iin, 7, HOY)
        self.assertNotEqual(primera.pk, segunda.pk)
        estados = sorted(ReservaInsumo.objects.filter(orden=self.orden).values_list("estado", flat=True))
        self.assertEqual(estados, ["activa", "cancelada"])

    def test_regla_reservar_rechaza_una_orden_que_no_esta_a_realizar(self):
        """API sección 9: `orden_no_pendiente` si la orden está concretada o cancelada."""
        for estado in ("concretada", "cancelada"):
            orden = orden_suelta(self.e.invernadero, Tipo.ENTREGA, estado=estado)
            with self.assertRaises(ErrorDeProduccion) as ctx, transaction.atomic():
                reservas.reservar(orden, self.iin, 1, HOY)
            self.assertEqual(ctx.exception.codigo, "orden_no_pendiente", estado)

    def test_regla_reservar_no_valida_contra_el_stock(self):
        """API sección 9: no validan contra el stock (lo hace el caso de uso, después de bloquear): se puede reservar más de lo que hay."""
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 999999, HOY)
        self.assertEqual(reserva.cantidad_reservada, Decimal("999999"))

    def test_regla_reservar_sin_transaccion_lanza_runtime_error(self):
        """API sección 9: sin la transacción del llamador, `RuntimeError`. Se simula el autocommit: `TestCase` ya envuelve todo en una."""
        from unittest import mock

        with mock.patch("produccion.servicios.movimientos.connection") as conexion:
            conexion.in_atomic_block = False
            for llamada in (
                lambda: reservas.reservar(self.orden, self.iin, 1, HOY),
                lambda: reservas.cambiar_cantidad(ReservaInsumo(), 1),
                lambda: reservas.cancelar(ReservaInsumo()),
            ):
                with self.assertRaises(RuntimeError):
                    llamada()
        self.assertFalse(ReservaInsumo.objects.filter(orden=self.orden).exists())

    # ---- cambiar_cantidad ----

    def test_post_b_cambiar_cantidad_conserva_la_fecha_de_reserva(self):
        """Postcondición b de PROD-PNF-ENV: la reserva queda con la nueva cantidad reservada y conserva su fecha de reserva."""
        fecha = HOY - timedelta(days=3)
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 10, fecha)
            devuelta = reservas.cambiar_cantidad(reserva, Decimal("4"))
        devuelta.refresh_from_db()
        self.assertEqual(devuelta.pk, reserva.pk)
        self.assertEqual(devuelta.cantidad_reservada, Decimal("4"))
        self.assertEqual(devuelta.fecha_reserva, fecha)
        self.assertEqual(devuelta.estado, ReservaInsumo.Estado.ACTIVA)

    def test_regla_cambiar_cantidad_rechaza_una_reserva_que_no_esta_activa(self):
        """API sección 9: `reserva_no_activa` si la reserva está cancelada o consumida."""
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 10, HOY)
            reservas.cancelar(reserva)
        with self.assertRaises(ErrorDeProduccion) as ctx, transaction.atomic():
            reservas.cambiar_cantidad(reserva, 3)
        self.assertEqual(ctx.exception.codigo, "reserva_no_activa")

    # ---- cancelar ----

    def test_post_b_cancelar_pasa_la_reserva_a_cancelada_sin_cantidades(self):
        """Postcondición b de PROD-PNF-ENV: un envase quitado deja su reserva «cancelada» con utilizada y devuelta nulas."""
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 10, HOY)
            devuelta = reservas.cancelar(reserva)
        devuelta.refresh_from_db()
        self.assertEqual(devuelta.estado, ReservaInsumo.Estado.CANCELADA)
        self.assertIsNone(devuelta.cantidad_utilizada)
        self.assertIsNone(devuelta.cantidad_devuelta)
        self.assertEqual(devuelta.cantidad_reservada, Decimal("10"))

    def test_regla_cancelar_rechaza_una_reserva_que_no_esta_activa(self):
        """API sección 9: `reserva_no_activa` si la reserva ya está cancelada."""
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 10, HOY)
            reservas.cancelar(reserva)
        with self.assertRaises(ErrorDeProduccion) as ctx, transaction.atomic():
            reservas.cancelar(reserva)
        self.assertEqual(ctx.exception.codigo, "reserva_no_activa")

    def test_regla_cancelar_libera_el_stock_libre(self):
        """Postcondición c de PROD-PNF-ENV: lo reservado resta del stock libre mientras la reserva está activa; al cancelarla, vuelve."""
        from inventario.servicios import stock

        libre_antes = stock.existencias([self.iin.pk], HOY)[self.iin.pk].libre
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 10, HOY)
        self.assertEqual(stock.existencias([self.iin.pk], HOY)[self.iin.pk].libre, libre_antes - 10)
        with transaction.atomic():
            reservas.cancelar(reserva)
        self.assertEqual(stock.existencias([self.iin.pk], HOY)[self.iin.pk].libre, libre_antes)

    # ---- lo que no hacen ----

    def test_regla_las_funciones_de_nucleo_no_auditan_ni_notifican(self):
        """API sección 9: no auditan ni notifican; devuelven lo que crearon o cambiaron para el registro del caso de uso."""
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        with transaction.atomic():
            reserva = reservas.reservar(self.orden, self.iin, 10, HOY)
            reservas.cambiar_cantidad(reserva, 6)
            reservas.cancelar(reserva)
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)
        self.assertEqual(Notificacion.objects.count(), avisos)
