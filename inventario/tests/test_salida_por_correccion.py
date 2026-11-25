# Pruebas de ``registrar_salida_por_correccion_de_recepcion`` (CMP-06, paso 1; docs/api/stock.md, «Escritura de compras»; D-90 puntos 1 y 2; regla 1 de 8.19, reglas 11 y 12 de 8.15,
# regla 22 de 8.16 y CMP-COR-RCP, «Cómo se aplica»). La escribe CMP-06 dentro de ``inventario``: es lo único que crea movimientos «salida por corrección de recepción»:
#   stock.registrar_salida_por_correccion_de_recepcion(lote_id, cantidad, *, origen_id) -> MovimientoInsumo
#     - Corre dentro de la transacción de quien llama (con el invernadero ya bloqueado), bloquea la existencia y sus lotes en orden de id y los vuelve a leer. No audita.
#     - Descuenta ``cantidad`` del lote (nunca por debajo de 0: ``ValueError``), crea UN movimiento del tipo nuevo con ``origen = origen_id`` (la ``CorreccionRecepcion``), suma la
#       misma cantidad al tránsito y reevalúa las alertas del insumo.
#     - ``ValueError`` (error de uso de quien llama) si el lote no existe o es el faltante sin lote, si la cantidad no es válida o si supera lo que el lote conserva; no cambia nada.
# Además, la restricción de la base: un movimiento de ese tipo SIN origen se rechaza (la migración reescribe la restricción de tipos y deja el origen obligatorio).

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import RegistroAuditoria
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import stock
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    origen_falso,
    reservas_de_prueba,
    tipo_de_insumo,
    verificar_invariantes,
)
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

D = Decimal
CORRECCION_DE_RECEPCION = MovimientoInsumo.TipoMovimiento.SALIDA_POR_CORRECCION_DE_RECEPCION
INCONSISTENTE = "inv_stock_inconsistente"


class SalidaPorCorreccionDeRecepcionTests(ConDatosDeInventario, TestCase):
    """``registrar_salida_por_correccion_de_recepcion``: lote, movimiento, tránsito, alertas y validaciones. Cada prueba verifica las invariantes del kárdex."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.invernadero, minimo=0, precio="12.50", transito=5)
        self.vence = timezone.localdate() + timedelta(days=90)
        self.lote = lote(self.iin, 10, vence=self.vence)
        self.origen = origen_falso()

    def corregir(self, cantidad, lote_=None):
        return stock.registrar_salida_por_correccion_de_recepcion((lote_ or self.lote).pk, cantidad, origen_id=self.origen.pk)

    def transito(self):
        return InsumoInvernadero.objects.get(pk=self.iin.pk).cant_transito_insumo

    def disponible(self, lote_=None):
        return LoteInsumo.objects.get(pk=(lote_ or self.lote).pk).cantidad_disponible

    def instantanea(self):
        """Lo que no debe cambiar si la corrección se rechaza: lotes, movimientos, tránsito y lo disponible."""
        return (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), self.transito(), self.disponible())

    # --- la salida ---

    def test_flujo_principal_baja_el_lote_y_crea_un_movimiento_del_tipo_nuevo_con_su_origen(self):
        """D-90 puntos 1 y 2 y regla 1 de 8.19: el lote baja en la cantidad corregida y se crea UN movimiento «salida por corrección de recepción» sobre ese lote con ``origen = origen_id``."""
        antes = MovimientoInsumo.objects.count()
        movimiento = self.corregir(D("4"))
        self.assertEqual(MovimientoInsumo.objects.count(), antes + 1)
        self.assertEqual(movimiento.tipo_movimiento, CORRECCION_DE_RECEPCION)
        self.assertEqual((movimiento.lote_insumo_id, movimiento.cantidad, movimiento.origen_id), (self.lote.pk, D("4"), self.origen.pk))
        self.assertIsNone(movimiento.motivo_ajuste)
        self.assertEqual(self.disponible(), D("6"))
        self.assertEqual(stock.stock_actual_de([self.iin.pk])[self.iin.pk], D("6"))
        verificar_invariantes(self.iin)

    def test_regla_22_de_8_16_el_transito_sube_en_lo_corregido(self):
        """Regla 22 de 8.16 y CMP-COR-RCP postcondición b: lo corregido vuelve a estar pendiente de recibir, así que el tránsito sube en la misma cantidad (no genera otro movimiento: regla 1 de 8.19)."""
        self.corregir(D("4"))
        self.assertEqual(self.transito(), D("9"))

    def test_regla_se_puede_corregir_todo_lo_que_conserva_el_lote_y_el_lote_se_conserva_en_cero(self):
        """CMP-COR-RCP, «Solo si el lote conserva la cantidad»: la máxima corregible es lo que conserva; con esa cantidad el lote queda en 0 (un lote en 0 se conserva: docs/patrones/stock.md, sección 2)."""
        self.corregir(D("10"))
        self.assertEqual(self.disponible(), D("0"))
        self.assertTrue(LoteInsumo.objects.filter(pk=self.lote.pk).exists())
        verificar_invariantes(self.iin)

    def test_regla_dos_correcciones_sobre_el_mismo_lote_suman(self):
        """Cada corrección es su propio movimiento y su propio cambio de cantidad: dos llamadas descuentan 3 + 2 y suman 5 al tránsito."""
        self.corregir(D("3"))
        self.corregir(D("2"))
        self.assertEqual(self.disponible(), D("5"))
        self.assertEqual(self.transito(), D("10"))
        self.assertEqual(self.lote.movimientos.filter(tipo_movimiento=CORRECCION_DE_RECEPCION).count(), 2)
        verificar_invariantes(self.iin)

    def test_regla_6_de_8_18_no_cambia_el_precio_de_referencia_ni_audita(self):
        """Regla 6 de 8.18: el precio de referencia no se actualiza. Docs/api/stock.md: la función no audita (lo hace el caso de uso)."""
        antes = RegistroAuditoria.objects.count()
        self.corregir(D("4"))
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.iin.pk).referencia_precio, D("12.50"))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_la_corregida_de_un_lote_no_toca_a_los_otros_lotes_ni_al_faltante(self):
        """Solo baja el lote nombrado: otro lote de la misma existencia y el faltante sin lote quedan como estaban."""
        otro = lote(self.iin, 7)
        sin_lote = faltante(self.iin, 2)
        self.corregir(D("4"))
        self.assertEqual((self.disponible(otro), self.disponible(sin_lote)), (D("7"), D("-2")))
        verificar_invariantes(self.iin)

    # --- validaciones: nada cambia ---

    def rechazado(self, cantidad, lote_=None):
        """Falla si ``corregir(cantidad)`` no lanza ``ValueError`` o si algo cambió en la base."""
        antes = self.instantanea()
        with self.assertRaises(ValueError):
            self.corregir(cantidad, lote_)
        self.assertEqual(self.instantanea(), antes)

    def test_regla_no_se_corrige_mas_de_lo_que_el_lote_conserva(self):
        """CMP-COR-RCP 4a y D-90 punto 4: el lote nunca queda negativo; si se pide más de lo que conserva, ``ValueError`` y no cambia nada."""
        self.rechazado(D("10.001"))
        consumo = lote(self.iin, 3, ingresada=8)  # un lote al que ya se le consumió: conserva 3
        self.rechazado(D("4"), consumo)

    def test_regla_2_de_8_23_las_cantidades_respetan_los_decimales_de_la_unidad(self):
        """Regla 2 de 8.23: la cantidad se valida con los decimales de la unidad (el litro admite tres, la unidad ninguno) y es mayor que cero."""
        self.corregir(D("0.125"))
        self.rechazado(D("0.1255"))
        self.rechazado(D("0"))
        self.rechazado(D("-1"))
        maceta = existencia(insumo("Maceta", unidad="unidad"), self.invernadero, transito=0)
        por_unidad = lote(maceta, 5)
        with self.assertRaises(ValueError):
            stock.registrar_salida_por_correccion_de_recepcion(por_unidad.pk, D("1.5"), origen_id=self.origen.pk)
        self.assertEqual(self.disponible(por_unidad), D("5"))

    def test_regla_el_faltante_sin_lote_no_se_corrige(self):
        """D-90 punto 4: lo que fue a cubrir un faltante sin lote no se puede corregir (ya se consumió): el faltante no es un lote común de esta función (``ValueError``)."""
        sin_lote = faltante(self.iin, 3)
        self.rechazado(D("1"), sin_lote)

    def test_regla_un_lote_que_no_existe_es_un_error_de_uso(self):
        """Un ``lote_id`` que no existe es un error de quien llama (``ValueError``), no un 500: ``compras`` ya verificó con todo bloqueado."""
        antes = self.instantanea()
        with self.assertRaises(ValueError):
            stock.registrar_salida_por_correccion_de_recepcion(self.lote.pk + 9999, D("1"), origen_id=self.origen.pk)
        self.assertEqual(self.instantanea(), antes)

    # --- alertas ---

    def test_regla_11_de_8_15_si_el_stock_baja_de_lo_reservado_se_crea_la_alerta_de_stock_inconsistente(self):
        """Reglas 11 y 12 de 8.15 y CMP-COR-RCP postcondición e: la función reevalúa las alertas; con 10 de stock y 8 reservados, bajar 5 deja el stock vigente (5) por debajo de lo reservado."""
        with reservas_de_prueba(reservado={self.iin.pk: D("8")}):
            self.corregir(D("5"))
        alerta = Alerta.objects.get(tipo_alerta=INCONSISTENTE, clave_estado=f"insumo:{self.iin.pk}")
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)

    def test_regla_12_de_8_15_sin_reservas_que_se_rompan_no_se_crea_la_alerta(self):
        """Regla 12 de 8.15: la reevaluación es idempotente y solo crea la alerta si se rompe la condición; sin reservas, corregir no la crea."""
        self.corregir(D("5"))
        self.assertFalse(Alerta.objects.filter(tipo_alerta=INCONSISTENTE, clave_estado=f"insumo:{self.iin.pk}").exists())

    # --- la restricción de la base ---

    def test_regla_3_de_8_19_un_movimiento_del_tipo_nuevo_sin_origen_se_rechaza(self):
        """Regla 3 de 8.19 (D-52 punto 4) y D-90 punto 2: la restricción reescrita deja el origen **obligatorio** en la salida por corrección de recepción (tiene origen: la corrección)."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovimientoInsumo.objects.create(lote_insumo=self.lote, cantidad=D("1"), tipo_movimiento=CORRECCION_DE_RECEPCION, origen=None)

    def test_regla_8_19_el_tipo_nuevo_cabe_en_la_columna_y_pasa_la_restriccion_de_tipos(self):
        """D-90 punto 2: «salida_por_correccion_de_recepcion» tiene 34 caracteres: la migración sube ``max_length`` a 40 y suma el valor a la restricción de tipos; con origen se guarda."""
        creado = MovimientoInsumo.objects.create(lote_insumo=self.lote, cantidad=D("1"), tipo_movimiento=CORRECCION_DE_RECEPCION, origen=self.origen)
        self.assertEqual(MovimientoInsumo.objects.get(pk=creado.pk).tipo_movimiento, "salida_por_correccion_de_recepcion")
