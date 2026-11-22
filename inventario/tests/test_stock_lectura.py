# Pruebas de la lectura de stock de INV-02, paso 1 (docs/patrones/stock.md, secciones 1 y 2; docs/api/stock.md, «Lectura»).
#
# Se prueba (inventario/servicios/stock.py), tomado del módulo dentro de cada prueba:
#   existencias(ids, hoy=None) -> {id: Existencia(actual, vigente, reservado, libre, transito, minimo, bajo_minimo, inconsistente)}
#   disponible_para_planificar(ids, fecha) -> {id: Decimal}      (regla 8 de 8.4: max(0, libre a la fecha))
#   proponer_lotes_fefo(iin_id, cantidad, fecha) -> Propuesta(partes=[(lote_id, cantidad)], resto)
#   ordenes_sin_cobertura(iin_id, hoy=None) -> [OrdenQueReserva]
# Toda cuenta se hace para una fecha ``hoy`` que se pasa: nunca se lee la fecha por cuenta propia.

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from inventario import extensiones
from inventario.extensiones import OrdenQueReserva
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    faltante,
    insumo,
    lote,
    perezoso,
    reservas_de_prueba,
)
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

stock = perezoso("inventario.servicios.stock")
HOY = date(2026, 12, 10)
D = Decimal


class StockLecturaTests(ConDatosDeInventario, TestCase):
    """Cada fórmula de la sección 1 de docs/patrones/stock.md."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.invernadero, minimo=20)

    def leer(self, hoy=HOY):
        return stock.existencias([self.iin.pk], hoy)[self.iin.pk]

    # ---- stock actual y vigente ----

    def test_regla_stock_1_actual_suma_todos_los_lotes_incluido_el_faltante(self):
        """Sección 1: stock actual = Σ cantidad_disponible de todos los lotes, vencidos y faltante incluidos."""
        lote(self.iin, 10, vence=HOY + timedelta(days=30))
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        faltante(self.iin, 3)
        self.assertEqual(self.leer().actual, D("12"))

    def test_regla_stock_1_vigente_excluye_los_lotes_vencidos_y_suma_el_faltante(self):
        """Sección 1: vigente = lotes no vencidos hoy + faltante sin lote (negativo)."""
        lote(self.iin, 10, vence=HOY + timedelta(days=30))
        lote(self.iin, 5, vence=HOY - timedelta(days=1))
        faltante(self.iin, 3)
        self.assertEqual(self.leer().vigente, D("7"))

    def test_regla_stock_1_el_dia_del_vencimiento_el_lote_todavia_es_vigente(self):
        """Regla 4 de CMP-REV-VNC: vencido desde el día siguiente a su fecha; el borde cuenta como vigente."""
        lote(self.iin, 8, vence=HOY)
        self.assertEqual(self.leer(HOY).vigente, D("8"))
        self.assertEqual(self.leer(HOY + timedelta(days=1)).vigente, D("0"))

    def test_regla_stock_1_un_lote_sin_vencimiento_siempre_es_vigente(self):
        """Sección 2: un lote de un insumo que no controla vencimiento nunca vence."""
        sin = insumo("Bolsas", unidad="unidad")
        iin = existencia(sin, self.invernadero)
        lote(iin, 40)
        self.assertEqual(stock.existencias([iin.pk], HOY + timedelta(days=9999))[iin.pk].vigente, D("40"))

    def test_regla_stock_1_sin_lotes_todo_es_cero(self):
        """Una existencia sin lotes da 0 en todo."""
        r = self.leer()
        self.assertEqual((r.actual, r.vigente, r.reservado, r.libre), (D("0"), D("0"), D("0"), D("0")))

    # ---- reservado y libre ----

    def test_regla_stock_1_sin_registrantes_lo_reservado_es_cero(self):
        """Sección 1: sin registrantes de reservas (produccion no existe), reservado = 0."""
        lote(self.iin, 10, vence=HOY + timedelta(days=30))
        self.assertEqual(self.leer().reservado, D("0"))

    def test_regla_stock_1_libre_es_vigente_menos_reservado(self):
        """Sección 1: stock libre = vigente − reservado."""
        lote(self.iin, 10, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk: "4"}):
            r = self.leer()
        self.assertEqual((r.reservado, r.libre), (D("4"), D("6")))

    def test_regla_stock_1_libre_puede_ser_negativo(self):
        """Regla 5 de 8.13: el stock libre puede ser negativo."""
        lote(self.iin, 3, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk: "10"}):
            self.assertEqual(self.leer().libre, D("-7"))

    def test_regla_stock_1_una_reserva_falsa_de_otro_insumo_no_cuenta(self):
        """Un registrante que informa ids ajenos no cambia el resultado de esta existencia."""
        lote(self.iin, 10, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk + 999: "50"}):
            self.assertEqual(self.leer().reservado, D("0"))

    # ---- tránsito, bajo el mínimo e inconsistente ----

    def test_regla_stock_1_transito_es_la_columna_de_la_existencia(self):
        """Sección 1: en tránsito = cant_transito_insumo."""
        iin = existencia(insumo("Otro", unidad="l"), self.invernadero, transito="7")
        self.assertEqual(stock.existencias([iin.pk], HOY)[iin.pk].transito, D("7"))

    def test_regla_stock_1_bajo_el_minimo_si_libre_mas_transito_no_llega(self):
        """Sección 1: bajo el mínimo si mínimo > 0 y libre + tránsito < mínimo."""
        lote(self.iin, 15, vence=HOY + timedelta(days=30))
        self.assertTrue(self.leer().bajo_minimo)

    def test_regla_stock_1_en_el_minimo_exacto_no_esta_bajo_el_minimo(self):
        """El borde: libre == mínimo no es «bajo»."""
        lote(self.iin, 20, vence=HOY + timedelta(days=30))
        self.assertFalse(self.leer().bajo_minimo)

    def test_regla_stock_1_el_transito_cuenta_para_el_minimo(self):
        """Regla 3 de CMP-MOD-IIN: libre + tránsito."""
        iin = existencia(insumo("Con camino", unidad="l"), self.invernadero, minimo=20, transito="10")
        lote(iin, 10)
        self.assertFalse(stock.existencias([iin.pk], HOY)[iin.pk].bajo_minimo)

    def test_regla_stock_1_minimo_cero_nunca_esta_bajo_el_minimo(self):
        """Sección 1: con mínimo 0 no hay alerta de bajo el mínimo."""
        iin = existencia(insumo("Sin minimo", unidad="l"), self.invernadero, minimo=0)
        self.assertFalse(stock.existencias([iin.pk], HOY)[iin.pk].bajo_minimo)

    def test_regla_stock_1_un_lote_vencido_no_cuenta_para_el_minimo(self):
        """Regla 11 de CMP-REV-VNC: un lote vencido deja de contar en el stock libre."""
        lote(self.iin, 25, vence=HOY - timedelta(days=1))
        self.assertTrue(self.leer().bajo_minimo)

    def test_regla_stock_1_inconsistente_si_el_stock_vigente_no_cubre_lo_reservado(self):
        """Sección 1 (y CU, post i): vigente < reservado."""
        lote(self.iin, 3, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk: "5"}):
            self.assertTrue(self.leer().inconsistente)

    def test_regla_stock_1_inconsistente_si_el_stock_vigente_es_negativo(self):
        """Un faltante sin lote deja el vigente negativo."""
        faltante(self.iin, 2)
        self.assertTrue(self.leer().inconsistente)

    def test_regla_stock_1_inconsistente_mide_sin_lotes_vencidos_y_no_el_total(self):
        """Manda el CU (L7): con 10 vencidos y 0 vigente, reservar 5 es inconsistente aunque el total sea 10."""
        lote(self.iin, 10, vence=HOY - timedelta(days=2))
        with reservas_de_prueba(reservado={self.iin.pk: "5"}):
            self.assertTrue(self.leer().inconsistente)

    def test_regla_stock_1_no_es_inconsistente_si_cubre_exacto(self):
        """El borde: vigente == reservado no es inconsistente."""
        lote(self.iin, 5, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk: "5"}):
            self.assertFalse(self.leer().inconsistente)

    # ---- disponible para planificar ----

    def test_regla_8_4_8_planificar_no_cuenta_lo_que_vence_antes_de_la_fecha(self):
        """Regla 8 de 8.4: a la fecha programada no cuentan los lotes que ya estarán vencidos."""
        lote(self.iin, 10, vence=HOY + timedelta(days=5))
        lote(self.iin, 4, vence=HOY + timedelta(days=60))
        antes = stock.disponible_para_planificar([self.iin.pk], HOY + timedelta(days=5))[self.iin.pk]
        despues = stock.disponible_para_planificar([self.iin.pk], HOY + timedelta(days=6))[self.iin.pk]
        self.assertEqual((antes, despues), (D("14"), D("4")))

    def test_regla_8_4_8_planificar_nunca_es_negativo(self):
        """Regla 8 de 8.4: max(0, libre)."""
        lote(self.iin, 2, vence=HOY + timedelta(days=30))
        with reservas_de_prueba(reservado={self.iin.pk: "9"}):
            self.assertEqual(stock.disponible_para_planificar([self.iin.pk], HOY)[self.iin.pk], D("0"))

    def test_regla_8_4_8_planificar_con_fecha_futura_resta_las_reservas(self):
        """Fechas futuras: sigue restando lo reservado."""
        lote(self.iin, 10, vence=HOY + timedelta(days=90))
        with reservas_de_prueba(reservado={self.iin.pk: "3"}):
            self.assertEqual(
                stock.disponible_para_planificar([self.iin.pk], HOY + timedelta(days=30))[self.iin.pk], D("7")
            )

    # ---- FEFO ----

    def test_regla_8_23_3_fefo_toma_primero_el_que_vence_antes(self):
        """Sección 2: orden por fecha de vencimiento ascendente."""
        tarde = lote(self.iin, 10, vence=HOY + timedelta(days=50))
        pronto = lote(self.iin, 10, vence=HOY + timedelta(days=5))
        p = stock.proponer_lotes_fefo(self.iin.pk, D("12"), HOY)
        self.assertEqual(p.partes, [(pronto.pk, D("10")), (tarde.pk, D("2"))])
        self.assertEqual(p.resto, D("0"))

    def test_regla_8_23_3_fefo_no_propone_lotes_vencidos_ni_el_faltante(self):
        """Sección 2: no propone lotes vencidos a `fecha` ni el faltante sin lote."""
        lote(self.iin, 10, vence=HOY - timedelta(days=1))
        faltante(self.iin, 4)
        buen = lote(self.iin, 5, vence=HOY + timedelta(days=9))
        p = stock.proponer_lotes_fefo(self.iin.pk, D("8"), HOY)
        self.assertEqual(p.partes, [(buen.pk, D("5"))])
        self.assertEqual(p.resto, D("3"))

    def test_regla_8_23_3_fefo_el_lote_que_vence_ese_dia_todavia_se_propone(self):
        """El borde del día del vencimiento: todavía puede usarse."""
        l = lote(self.iin, 5, vence=HOY)
        self.assertEqual(stock.proponer_lotes_fefo(self.iin.pk, D("5"), HOY).partes, [(l.pk, D("5"))])
        self.assertEqual(stock.proponer_lotes_fefo(self.iin.pk, D("5"), HOY + timedelta(days=1)).partes, [])

    def test_regla_8_23_3_fefo_sin_vencimiento_va_del_ingresado_antes_al_mas_nuevo(self):
        """Sección 2: sin vencimiento, por fecha de ingreso y por id."""
        iin = existencia(insumo("Bolsas", unidad="unidad"), self.invernadero)
        nuevo = lote(iin, 5, ingreso=HOY)
        viejo = lote(iin, 5, ingreso=HOY - timedelta(days=30))
        p = stock.proponer_lotes_fefo(iin.pk, D("7"), HOY)
        self.assertEqual(p.partes, [(viejo.pk, D("5")), (nuevo.pk, D("2"))])

    def test_regla_8_23_3_fefo_saltea_los_lotes_agotados(self):
        """Un lote en 0 se conserva pero no aporta."""
        lote(self.iin, 0, vence=HOY + timedelta(days=3), ingresada=5)
        buen = lote(self.iin, 4, vence=HOY + timedelta(days=9))
        self.assertEqual(stock.proponer_lotes_fefo(self.iin.pk, D("4"), HOY).partes, [(buen.pk, D("4"))])

    # ---- sin cobertura ----

    def test_regla_stock_1_sin_cobertura_cubre_por_fecha_programada_y_nombra_las_que_no_alcanzan(self):
        """Sección 1: cubre de la más cercana a la más lejana con el stock vigente no negativo."""
        lote(self.iin, 6, vence=HOY + timedelta(days=90))
        cerca = OrdenQueReserva(1, "Siembra 1", D("4"), HOY + timedelta(days=1), "/o/1")
        lejos = OrdenQueReserva(2, "Siembra 2", D("4"), HOY + timedelta(days=9), "/o/2")
        with reservas_de_prueba(reservado={self.iin.pk: "8"}, ordenes={self.iin.pk: [lejos, cerca]}):
            sin = stock.ordenes_sin_cobertura(self.iin.pk, HOY)
        self.assertEqual([o.orden_id for o in sin], [2])

    def test_regla_stock_1_sin_cobertura_con_stock_vigente_negativo_no_cubre_ninguna(self):
        """El stock negativo cubre como 0: todas quedan sin cobertura."""
        faltante(self.iin, 3)
        a = OrdenQueReserva(1, "A", D("1"), HOY, "/o/1")
        b = OrdenQueReserva(2, "B", D("1"), HOY, "/o/2")
        with reservas_de_prueba(reservado={self.iin.pk: "2"}, ordenes={self.iin.pk: [a, b]}):
            self.assertEqual([o.orden_id for o in stock.ordenes_sin_cobertura(self.iin.pk, HOY)], [1, 2])

    def test_regla_stock_1_sin_cobertura_no_cuenta_los_lotes_vencidos(self):
        """Manda el CU: se mide sin lotes vencidos."""
        lote(self.iin, 10, vence=HOY - timedelta(days=1))
        a = OrdenQueReserva(1, "A", D("1"), HOY, "/o/1")
        with reservas_de_prueba(reservado={self.iin.pk: "1"}, ordenes={self.iin.pk: [a]}):
            self.assertEqual([o.orden_id for o in stock.ordenes_sin_cobertura(self.iin.pk, HOY)], [1])

    # ---- consultas ----

    def test_regla_stock_1_una_consulta_por_tabla_sin_importar_cuantas_existencias(self):
        """docs/api/extensiones_de_inventario.md: nada de consultas por fila (lotes + existencias)."""
        ids = []
        for n in range(6):
            iin = existencia(insumo(f"Insumo {n}", unidad="l"), self.invernadero, minimo=5)
            lote(iin, 3)
            lote(iin, 2)
            ids.append(iin.pk)
        # Sin registrante de reservas (el real de `produccion`, PRD-01, suma su propia consulta): lotes + existencias.
        with mock.patch.object(extensiones, "_RESERVAS", []), self.assertNumQueries(2):
            resultado = stock.existencias(ids, HOY)
        self.assertEqual(len(resultado), 6)

    def test_regla_stock_1_planificar_no_hace_consultas_por_fila(self):
        """Lo mismo para `disponible_para_planificar`."""
        ids = []
        for n in range(5):
            iin = existencia(insumo(f"P {n}", unidad="l"), self.invernadero)
            lote(iin, 3)
            ids.append(iin.pk)
        # Sin registrante de reservas (el real de `produccion`, PRD-01, suma su propia consulta): lotes + existencias.
        with mock.patch.object(extensiones, "_RESERVAS", []), self.assertNumQueries(2):
            stock.disponible_para_planificar(ids, HOY)

    def test_regla_stock_1_existencias_de_una_lista_vacia_es_un_diccionario_vacio(self):
        """Sin ids no hay nada que leer."""
        self.assertEqual(stock.existencias([], HOY), {})
