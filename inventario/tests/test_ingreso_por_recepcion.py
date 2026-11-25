# Pruebas de ``registrar_ingreso_por_recepcion`` y ``lotes_de_ingreso`` (CMP-04, paso 2; docs/api/stock.md, «Escritura de compras»; D-90 punto 1; regla 4 de 8.23,
# regla 1 de 8.19, regla 22 de 8.16, reglas 4 y 6 de 8.18 y CMP-REG-RCP, «Cómo se aplica»). Las escribe CMP-04 dentro de ``inventario``: son las únicas funciones
# que crean lotes y movimientos de ingreso por recepción (regla 1 de 8.19):
#   stock.registrar_ingreso_por_recepcion(iin_id, partes, *, origen_id, fecha=None) -> list[MovimientoInsumo]
#     - ``partes = [(cantidad, vencimiento | None)]``. Corre dentro de la transacción de quien llama (con el invernadero ya bloqueado), bloquea la existencia y
#       sus lotes en orden de id y los vuelve a leer. No audita.
#     - Cubre primero el FALTANTE SIN LOTE (lo deja como mucho en 0), crea un lote nuevo por cada parte con lo que sobra, un movimiento «ingreso por
#       recepción» por lote tocado (el faltante incluido) con ``origen = origen_id`` y resta el tránsito por el total. Después reevalúa las alertas.
#     - El vencimiento es obligatorio si el insumo lo controla y nunca pasado; ``ValueError`` si algo es inválido, sin cambiar nada.
#   stock.lotes_de_ingreso(movimiento_ids) -> list[(LoteInsumo, Decimal)]: lectura; los lotes que esos movimientos crearon (sin el faltante) y lo ingresado.

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.models import RegistroAuditoria
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import alertas_de_stock, stock
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    origen_falso,
    tipo_de_insumo,
    verificar_invariantes,
)
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

D = Decimal
INGRESO = MovimientoInsumo.TipoMovimiento.INGRESO_POR_RECEPCION
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class IngresoPorRecepcionTests(ConDatosDeInventario, TestCase):
    """``registrar_ingreso_por_recepcion``: lotes, faltante, tránsito, movimientos y validaciones. Cada prueba verifica las invariantes del kárdex."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.invernadero, minimo=0, precio="12.50", transito=20)
        self.origen = origen_falso()
        self.hoy = timezone.localdate()
        self.vence = self.hoy + timedelta(days=90)

    def ingresar(self, partes, fecha=None, iin=None):
        return stock.registrar_ingreso_por_recepcion((iin or self.iin).pk, partes, origen_id=self.origen.pk, fecha=fecha)

    def transito(self):
        return InsumoInvernadero.objects.get(pk=self.iin.pk).cant_transito_insumo

    def instantanea(self):
        """Lo que no debe cambiar si el ingreso se rechaza: lotes, movimientos, tránsito y precio de referencia."""
        return (
            LoteInsumo.objects.count(),
            MovimientoInsumo.objects.count(),
            self.transito(),
            InsumoInvernadero.objects.get(pk=self.iin.pk).referencia_precio,
        )

    # --- el ingreso ---

    def test_flujo_principal_crea_un_lote_y_un_movimiento_de_ingreso(self):
        """D-90 punto 1 y regla 1 de 8.19: una parte forma un lote nuevo (ingresada = disponible, ingreso hoy, con su vencimiento) y UN movimiento «ingreso por recepción» con ``origen = origen_id``."""
        movimientos = self.ingresar([(D("10"), self.vence)])
        self.assertEqual(len(movimientos), 1)
        movimiento = movimientos[0]
        self.assertEqual(movimiento.tipo_movimiento, INGRESO)
        self.assertEqual(movimiento.cantidad, D("10"))
        self.assertEqual(movimiento.origen_id, self.origen.pk)
        creado = movimiento.lote_insumo
        self.assertFalse(creado.es_faltante_sin_lote)
        self.assertEqual((creado.cantidad_ingresada, creado.cantidad_disponible), (D("10"), D("10")))
        self.assertEqual((creado.fecha_ingreso, creado.fecha_vencimiento), (self.hoy, self.vence))
        self.assertEqual(creado.insumo_invernadero_id, self.iin.pk)
        verificar_invariantes(self.iin)

    def test_regla_22_de_8_16_el_stock_sube_y_el_transito_baja_en_lo_recibido(self):
        """Regla 22 de 8.16 y CMP-REG-RCP postcondición c: el stock actual (suma de lotes) sube y el tránsito baja en la cantidad recibida."""
        self.ingresar([(D("10"), self.vence)])
        self.assertEqual(stock.stock_actual_de([self.iin.pk])[self.iin.pk], D("10"))
        self.assertEqual(self.transito(), D("10"))

    def test_regla_4_de_8_23_cubre_primero_el_faltante_sin_lote_y_el_resto_forma_un_lote(self):
        """Regla 4 de 8.23 y CMP-REG-RCP, «Lotes de la recepción»: el faltante sin lote se cubre primero (queda en 0) con su propio movimiento, y lo que sobra forma el lote nuevo.
        Los movimientos salen en el orden en que se tocaron los lotes: primero el faltante."""
        sin_lote = faltante(self.iin, 4)
        movimientos = self.ingresar([(D("10"), self.vence)])
        self.assertEqual([m.lote_insumo_id for m in movimientos][0], sin_lote.pk)
        self.assertEqual([m.cantidad for m in movimientos], [D("4"), D("6")])
        sin_lote.refresh_from_db()
        self.assertEqual(sin_lote.cantidad_disponible, D("0"))
        nuevo = movimientos[1].lote_insumo
        self.assertEqual((nuevo.cantidad_ingresada, nuevo.cantidad_disponible), (D("6"), D("6")))
        self.assertTrue(all(m.tipo_movimiento == INGRESO and m.origen_id == self.origen.pk for m in movimientos))
        self.assertEqual(stock.stock_actual_de([self.iin.pk])[self.iin.pk], D("6"))
        self.assertEqual(self.transito(), D("10"))
        verificar_invariantes(self.iin)

    def test_regla_4_de_8_23_si_lo_recibido_no_alcanza_para_el_faltante_no_se_crea_lote(self):
        """Regla 4 de 8.23: el faltante queda en lo que reste (nunca positivo) y, si lo recibido se va entero a cubrirlo, no se crea ningún lote ni más movimientos que el del faltante."""
        sin_lote = faltante(self.iin, 15)
        cantidad_de_lotes = LoteInsumo.objects.filter(insumo_invernadero=self.iin).count()
        movimientos = self.ingresar([(D("10"), self.vence)])
        self.assertEqual([(m.lote_insumo_id, m.cantidad) for m in movimientos], [(sin_lote.pk, D("10"))])
        sin_lote.refresh_from_db()
        self.assertEqual(sin_lote.cantidad_disponible, D("-5"))
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=self.iin).count(), cantidad_de_lotes)
        self.assertEqual(self.transito(), D("10"))
        verificar_invariantes(self.iin)

    def test_regla_4_de_8_23_varias_partes_forman_un_lote_cada_una_con_su_vencimiento(self):
        """D-90 punto 1: un lote nuevo por cada parte, con su vencimiento; un movimiento por lote y el tránsito baja por el total."""
        otra = self.hoy + timedelta(days=30)
        movimientos = self.ingresar([(D("3"), otra), (D("7"), self.vence)])
        self.assertEqual([m.cantidad for m in movimientos], [D("3"), D("7")])
        self.assertEqual([m.lote_insumo.fecha_vencimiento for m in movimientos], [otra, self.vence])
        self.assertEqual(len({m.lote_insumo_id for m in movimientos}), 2)
        self.assertEqual(self.transito(), D("10"))
        verificar_invariantes(self.iin)

    def test_regla_4_de_8_23_el_faltante_se_cubre_con_las_primeras_partes_y_el_resto_forma_lotes(self):
        """Regla 4 de 8.23: el faltante (5) absorbe la primera parte entera (3) y 2 de la segunda; el lote nuevo es solo la segunda parte con lo que sobra (5) y su vencimiento."""
        sin_lote = faltante(self.iin, 5)
        primera = self.hoy + timedelta(days=30)
        movimientos = self.ingresar([(D("3"), primera), (D("7"), self.vence)])
        self.assertEqual([(m.lote_insumo_id == sin_lote.pk, m.cantidad) for m in movimientos], [(True, D("5")), (False, D("5"))])
        self.assertEqual(movimientos[1].lote_insumo.fecha_vencimiento, self.vence)
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=self.iin, es_faltante_sin_lote=False).count(), 1)
        self.assertEqual(self.transito(), D("10"))
        verificar_invariantes(self.iin)

    def test_regla_un_insumo_que_no_controla_vencimiento_ingresa_sin_fecha(self):
        """D-90 punto 1: el vencimiento solo es obligatorio si el insumo lo controla; si no, el lote queda sin fecha de vencimiento."""
        sin_vencimiento = existencia(insumo("Maceta", unidad="unidad"), self.invernadero, transito=5)
        movimientos = self.ingresar([(D("5"), None)], iin=sin_vencimiento)
        self.assertIsNone(movimientos[0].lote_insumo.fecha_vencimiento)
        self.assertEqual(InsumoInvernadero.objects.get(pk=sin_vencimiento.pk).cant_transito_insumo, D("0"))
        verificar_invariantes(sin_vencimiento)

    def test_regla_la_fecha_del_ingreso_es_la_que_se_pasa(self):
        """``fecha`` (opcional): fecha del movimiento y del ingreso del lote; sin ella, la de hoy."""
        ayer = self.hoy - timedelta(days=1)
        movimiento = self.ingresar([(D("2"), self.vence)], fecha=ayer)[0]
        self.assertEqual(timezone.localtime(movimiento.fecha).date(), ayer)
        self.assertEqual(movimiento.lote_insumo.fecha_ingreso, ayer)

    def test_regla_6_de_8_18_no_cambia_el_precio_de_referencia_ni_audita(self):
        """Regla 6 de 8.18: el precio de referencia no se actualiza al recibir. Docs/api/stock.md: la función no audita (lo hace el caso de uso)."""
        antes = RegistroAuditoria.objects.count()
        self.ingresar([(D("10"), self.vence)])
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.iin.pk).referencia_precio, D("12.50"))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    # --- validaciones: nada cambia ---

    def rechazado(self, partes, error=ValueError):
        """Falla si ``ingresar(partes)`` no lanza ``error`` o si algo cambió en la base."""
        antes = self.instantanea()
        with self.assertRaises(error):
            self.ingresar(partes)
        self.assertEqual(self.instantanea(), antes)

    def test_regla_el_vencimiento_es_obligatorio_si_el_insumo_lo_controla(self):
        """D-90 punto 1: un insumo que controla vencimiento no ingresa sin fecha (``ValueError``, no cambia nada)."""
        self.rechazado([(D("5"), None)])

    def test_regla_extension_5e_nunca_ingresa_un_lote_ya_vencido(self):
        """Extensión 5e y docs/api/stock.md: una fecha pasada es un inconveniente («vencido»), no un ingreso: ``ValueError``. Un lote vence desde el día siguiente: el día de la fecha todavía sirve."""
        self.rechazado([(D("5"), self.hoy - timedelta(days=1))])
        self.ingresar([(D("5"), self.hoy)])
        self.assertEqual(self.transito(), D("15"))

    def test_regla_un_insumo_que_no_controla_vencimiento_no_acepta_una_fecha(self):
        """Un vencimiento para un insumo que no lo controla es un error de quien llama (``ValueError``): ese lote nunca vence."""
        sin_vencimiento = existencia(insumo("Maceta", unidad="unidad"), self.invernadero, transito=5)
        with self.assertRaises(ValueError):
            self.ingresar([(D("5"), self.vence)], iin=sin_vencimiento)
        self.assertEqual(InsumoInvernadero.objects.get(pk=sin_vencimiento.pk).cant_transito_insumo, D("5"))

    def test_regla_2_de_8_23_las_cantidades_respetan_los_decimales_de_la_unidad(self):
        """Regla 2 de 8.23: la cantidad se valida con los decimales de la unidad (el litro admite tres, la unidad ninguno) y es mayor que cero."""
        self.ingresar([(D("0.125"), self.vence)])
        self.rechazado([(D("0.1255"), self.vence)])
        self.rechazado([(D("0"), self.vence)])
        self.rechazado([(D("-1"), self.vence)])
        por_unidad = existencia(insumo("Maceta", unidad="unidad"), self.invernadero, transito=5)
        with self.assertRaises(ValueError):
            self.ingresar([(D("1.5"), None)], iin=por_unidad)

    def test_regla_sin_partes_no_hay_ingreso(self):
        """Una recepción sin nada que ingresar no llama a esta función (el servicio de compras no la invoca con cantidad 0): sin partes, ``ValueError``."""
        self.rechazado([])

    def test_regla_22_de_8_16_no_se_ingresa_mas_de_lo_que_hay_en_transito(self):
        """Regla 22 de 8.16 y D-90 punto 1: el tránsito nunca queda negativo; si lo recibido lo supera, ``ValueError`` y no se crea nada."""
        self.rechazado([(D("21"), self.vence)])

    # --- alertas ---

    def test_regla_12_de_8_15_recibir_resuelve_la_alerta_de_bajo_el_minimo_si_deja_de_estarlo(self):
        """Reglas 11 y 12 de 8.15 y CMP-REG-RCP postcondición g: al aprobar la orden la alerta sigue activa (recordatorio); al recibir se reevalúa y, con libre + tránsito ≥ mínimo, se resuelve."""
        iin = existencia(insumo("Fertilizante", unidad="l"), self.invernadero, minimo=30, transito=0)
        alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk)
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO, clave_estado=f"insumo:{iin.pk}")
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)
        InsumoInvernadero.objects.filter(pk=iin.pk).update(cant_transito_insumo=30)  # la aprobación de la orden sube el tránsito sin reevaluar
        self.ingresar([(D("10"), None)], iin=iin)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.RESUELTA)
        self.assertIsNotNone(alerta.fecha_resolucion)

    def test_regla_12_de_8_15_si_sigue_bajo_el_minimo_la_alerta_sigue_activa(self):
        """Regla 12 de 8.15: «las demás siguieron activas»: si el insumo sigue bajo el mínimo (libre + tránsito < mínimo), la alerta no se toca ni se duplica."""
        iin = existencia(insumo("Fertilizante", unidad="l"), self.invernadero, minimo=50, transito=0)
        alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk)
        InsumoInvernadero.objects.filter(pk=iin.pk).update(cant_transito_insumo=30)
        self.ingresar([(D("10"), None)], iin=iin)
        alertas = Alerta.objects.filter(tipo_alerta=BAJO_MINIMO, clave_estado=f"insumo:{iin.pk}")
        self.assertEqual([a.estado_alerta for a in alertas], [Alerta.Estado.ACTIVA])


class LotesDeIngresoTests(ConDatosDeInventario, TestCase):
    """``lotes_de_ingreso``: de los movimientos de una recepción, los lotes que creó y cuánto ingresó en cada uno (sin el faltante sin lote)."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", unidad="l", controla_vencimiento=True), self.invernadero, transito=30)
        self.origen = origen_falso()
        self.vence = timezone.localdate() + timedelta(days=60)

    def test_d90_punto_4_devuelve_los_lotes_creados_sin_el_faltante_y_lo_ingresado_en_cada_uno(self):
        """D-90 punto 4: «el lote creado por esa recepción» son los lotes de los movimientos que no son el faltante sin lote; sale cada uno con lo ingresado, en el orden de los movimientos."""
        faltante(self.iin, 4)
        movimientos = stock.registrar_ingreso_por_recepcion(
            self.iin.pk, [(D("10"), self.vence), (D("5"), self.vence + timedelta(days=1))], origen_id=self.origen.pk
        )
        resultado = stock.lotes_de_ingreso([m.pk for m in movimientos])
        self.assertEqual([(l.pk, cantidad) for l, cantidad in resultado], [(movimientos[1].lote_insumo_id, D("6")), (movimientos[2].lote_insumo_id, D("5"))])
        self.assertTrue(all(not l.es_faltante_sin_lote for l, _ in resultado))

    def test_d90_punto_4_solo_cuenta_los_ingresos_por_recepcion(self):
        """Los movimientos de otro tipo (un ajuste, un consumo) no son «lotes de ingreso» aunque se pasen sus ids; sin ids, lista vacía."""
        ajuste = lote(self.iin, 5)  # crea su movimiento de ajuste positivo
        ids = list(ajuste.movimientos.values_list("pk", flat=True))
        self.assertEqual(stock.lotes_de_ingreso(ids), [])
        self.assertEqual(stock.lotes_de_ingreso([]), [])

    def test_regla_lotes_de_ingreso_es_de_lectura_no_cambia_nada(self):
        """Docs/api/stock.md: ``lotes_de_ingreso`` es de lectura: no crea ni modifica lotes ni movimientos."""
        movimientos = stock.registrar_ingreso_por_recepcion(self.iin.pk, [(D("5"), self.vence)], origen_id=self.origen.pk)
        antes = (LoteInsumo.objects.count(), MovimientoInsumo.objects.count())
        stock.lotes_de_ingreso([m.pk for m in movimientos])
        self.assertEqual((LoteInsumo.objects.count(), MovimientoInsumo.objects.count()), antes)
