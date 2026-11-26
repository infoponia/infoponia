# Pruebas de los servicios de EST-CNS-PRD «Consultar Estadísticas de Producción» (EST-01, pasos 2 y 3): un caso por indicador, con datos
# armados a mano y el resultado esperado calculado en la prueba. Fuente: docs/casos_de_uso/estadisticas/estadisticas.md (EST-CNS-PRD) y
# D-93 punto 3 (las fórmulas), 5 («sin datos todavía») y 7 (consultas fijas). La merma lee la fecha de siembra de cada lote
# (`Siembra.fecha_siembra`) y no `fecha_resolucion_orden`: D-93 punto 3.2 + D-103 (respuesta del estudiante, 26/11/2026).

from datetime import date, time
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from core.tests.fabricas import crear_gerente
from estadisticas import periodos
from estadisticas.periodos import Comparacion, Periodo
from estadisticas.servicios import produccion
from estadisticas.servicios.produccion import (
    AlertasIot,
    FilaDeAlertas,
    FilaDeCategoria,
    FilaDeCausa,
    FilaDeInsumo,
    FilaDeOrdenes,
    FilaDeVariedad,
)
from estadisticas.tests.fabricas import (
    DESDE,
    HOY,
    aplicacion_de,
    consumo_de,
    dos_invernaderos,
    existencia_de,
    existencia_de_envase,
    insumo_adicional,
    instante_utc,
    lote_cargado,
    lote_sembrado,
    merma_de,
    nombre_de,
    orden,
    otra_variedad,
    salida_por_cosecha,
)
from inventario.tests.fabricas import categoria_del_sistema
from inventario.unidades import Unidad
from iot.tests.fabricas import ConCatalogoIot, sistema
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_alerta
from produccion.models import Lote, OrdenTrabajo
from produccion.servicios.ordenes import TIPOS_DE_PRODUCCION

T = OrdenTrabajo.Tipo
PERIODO = Periodo(DESDE, HOY)


def ids_de(*escenarios):
    """Los ids de los invernaderos de los escenarios, como los recibe cada indicador."""
    return [e.invernadero.pk for e in escenarios]


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 1 · Plantas sembradas y cosechadas (D-93 punto 3.1; paso 2 la parte de sembradas, paso 3 la de cosechadas)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdSembradasYCosechadasServicioTests(ConCatalogoIot, TestCase):
    """Indicador 1: sembradas (Σ `Lote.cantidad_inicial` de las siembras normales con `fecha_siembra` en el período) y cosechadas (Σ salidas
    por cosecha del período), por variedad."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.v1 = cls.n.variedad
        cls.v2 = otra_variedad(cls.n, "Rúcula")

    def indicador(self, *escenarios):
        """El indicador 1 del período por defecto para los invernaderos de los escenarios."""
        return produccion.sembradas_y_cosechadas(ids_de(*escenarios), PERIODO)

    def test_regla_indicador_1_sembradas_suma_la_cantidad_inicial_de_las_siembras_del_periodo_por_variedad(self):
        """D-93 punto 3.1: sembradas = Σ `cantidad_inicial` de las siembras normales concretadas con `fecha_siembra` en el período, por
        variedad. Cuentan el primer y el último día del período; no el día anterior ni el posterior."""
        lote_sembrado(self.n, 100, date(2026, 11, 5))
        lote_sembrado(self.n, 50, HOY)  # el último día vale
        lote_sembrado(self.n, 30, date(2026, 11, 10), variedad=self.v2)
        lote_sembrado(self.n, 25, DESDE)  # el primer día vale
        lote_sembrado(self.n, 70, date(2026, 10, 31))  # el día anterior: no
        lote_sembrado(self.n, 20, date(2026, 11, 27))  # el día posterior: no
        resultado = self.indicador(self.n)
        self.assertEqual(
            list(resultado.filas),
            [
                FilaDeVariedad(self.v1.pk, nombre_de(self.v1), 175, 0),
                FilaDeVariedad(self.v2.pk, nombre_de(self.v2), 30, 0),
            ],
        )
        self.assertEqual((resultado.sembradas, resultado.cosechadas, resultado.cosecha_disponible), (205, 0, True))

    def test_d92_punto_12_la_carga_inicial_no_es_una_siembra_del_periodo(self):
        """D-93 punto 3.1 y D-92 punto 12: la carga inicial (PRD-05) no es una siembra del período, aunque su `fecha_siembra` caiga adentro."""
        lote_cargado(self.n, 80, date(2026, 11, 10))
        resultado = self.indicador(self.n)
        self.assertEqual(list(resultado.filas), [])
        self.assertEqual(resultado.sembradas, 0)

    def test_d93_punto_3_1_sembradas_usa_la_cantidad_inicial_y_no_la_actual(self):
        """D-93 punto 3.1: se suma `Lote.cantidad_inicial`; una merma posterior que baja `cantidad_actual` no la cambia."""
        lote = lote_sembrado(self.n, 100, date(2026, 11, 5))
        Lote.objects.filter(pk=lote.pk).update(cantidad_actual=60)
        self.assertEqual(self.indicador(self.n).sembradas, 100)

    def test_d93_punto_3_1_sembradas_mira_fecha_siembra_y_no_la_fecha_de_resolucion(self):
        """D-93 punto 3.1 + D-103: una siembra sembrada el 30/10 y concretada en el sistema el 02/11 no es del período de noviembre."""
        lote_sembrado(self.n, 120, date(2026, 10, 30), resolucion=date(2026, 11, 2))
        self.assertEqual(self.indicador(self.n).sembradas, 0)

    def test_regla_indicador_1_cosechadas_suma_las_salidas_por_cosecha_del_periodo_por_variedad(self):
        """D-93 punto 3.1: cosechadas = Σ plantas de las salidas por cosecha con su fecha (local) en el período, por variedad. Cuentan desde
        las 00:00 del primer día hasta las 23:59 del último; no la salida del día anterior, ni una salida por merma."""
        a = lote_sembrado(self.n, 200, date(2026, 10, 1))
        b = lote_sembrado(self.n, 100, date(2026, 10, 15), variedad=self.v2)
        salida_por_cosecha(a, 40, date(2026, 11, 10))
        salida_por_cosecha(a, 7, DESDE, hora=time(0, 0))
        salida_por_cosecha(a, 20, HOY, hora=time(23, 59))
        salida_por_cosecha(a, 15, date(2026, 10, 31), hora=time(23, 59))  # el día anterior: no
        salida_por_cosecha(b, 25, date(2026, 11, 12))
        salida_por_cosecha(a, 9, date(2026, 11, 12), tipo="salida_por_merma")  # no es una cosecha
        resultado = self.indicador(self.n)
        self.assertEqual(
            list(resultado.filas),
            [
                FilaDeVariedad(self.v1.pk, nombre_de(self.v1), 0, 67),
                FilaDeVariedad(self.v2.pk, nombre_de(self.v2), 0, 25),
            ],
        )
        self.assertEqual((resultado.sembradas, resultado.cosechadas), (0, 92))

    def test_d93_punto_5_sin_cosecha_disponible_las_cosechadas_quedan_sin_dato_y_las_sembradas_siguen(self):
        """D-93 punto 5: si falta la fuente de la cosecha, «Cosechadas» no se muestra (None) y «Sembradas» sigue funcionando."""
        lote_sembrado(self.n, 100, date(2026, 11, 5))
        with mock.patch.object(produccion, "cosecha_disponible", return_value=False):
            resultado = self.indicador(self.n)
        self.assertEqual(list(resultado.filas), [FilaDeVariedad(self.v1.pk, nombre_de(self.v1), 100, None)])
        self.assertEqual((resultado.sembradas, resultado.cosechadas, resultado.cosecha_disponible), (100, None, False))

    def test_regla_alcance_solo_cuenta_los_invernaderos_pedidos(self):
        """EST-CNS-PRD regla 1: el indicador mira solo los invernaderos que recibe; no mezcla el de otra persona."""
        lote_sembrado(self.n, 100, date(2026, 11, 5))
        lote_sembrado(self.s, 40, date(2026, 11, 6), variedad=self.s.variedad)
        self.assertEqual(self.indicador(self.n).sembradas, 100)
        self.assertEqual(self.indicador(self.s).sembradas, 40)
        self.assertEqual(self.indicador(self.n, self.s).sembradas, 140)

    def test_d93_punto_7_dos_consultas_con_pocas_o_muchas_filas(self):
        """D-93 punto 7: el bloque hace 2 consultas (siembras y cosechas), sin importar cuántas variedades o lotes haya."""
        ids = ids_de(self.n)
        with self.assertNumQueries(2):
            produccion.sembradas_y_cosechadas(ids, PERIODO)
        v3 = otra_variedad(self.n, "Espinaca")
        for variedad in (self.v1, self.v2, v3):
            lote = lote_sembrado(self.n, 10, date(2026, 11, 5), variedad=variedad)
            lote_sembrado(self.n, 10, date(2026, 11, 6), variedad=variedad)
            salida_por_cosecha(lote, 4, date(2026, 11, 7))
        with self.assertNumQueries(2):
            resultado = produccion.sembradas_y_cosechadas(ids, PERIODO)
        self.assertEqual(len(resultado.filas), 3)


class EstCnsPrdCosechaDisponibleServicioTests(SimpleTestCase):
    """`cosecha_disponible()`: el `disponible()` de los indicadores que leen la cosecha (D-93 punto 5)."""

    def test_d93_punto_5_con_produccion_instalada_la_cosecha_esta_disponible(self):
        """D-93 punto 5: `produccion` está en `INSTALLED_APPS` y tiene `MovimientoStock`: disponible."""
        self.assertTrue(produccion.cosecha_disponible())

    def test_d93_punto_5_sin_la_app_instalada_no_esta_disponible(self):
        """D-93 punto 5: la función pregunta si la app está instalada."""
        with mock.patch.object(apps, "is_installed", return_value=False):
            self.assertFalse(produccion.cosecha_disponible())

    def test_d93_punto_5_sin_el_modelo_no_esta_disponible(self):
        """D-93 punto 5: …y si el modelo existe, sin `try/except` sobre consultas."""
        with mock.patch.dict(apps.all_models["produccion"], clear=True):
            self.assertFalse(produccion.cosecha_disponible())


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 2 · Merma (D-93 punto 3.2)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdMermaServicioTests(ConCatalogoIot, TestCase):
    """Indicador 2: plantas perdidas en el período ÷ (plantas en producción al inicio + sembradas en el período) × 100, y el reparto por causa.
    «Al inicio» = por cada lote con `fecha_siembra` anterior a «desde» (también los de carga inicial): `cantidad_inicial` − sus mermas
    anteriores − sus plantas cosechadas anteriores, sin bajar de 0."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()

    def indicador(self, *escenarios):
        """La merma del período por defecto para los invernaderos de los escenarios."""
        return produccion.merma(ids_de(*escenarios), PERIODO)

    def armar_el_caso_base(self):
        """Dos lotes: uno sembrado antes (200 plantas, 20 perdidas antes del período) y otro sembrado en el período (100 plantas)."""
        l1 = lote_sembrado(self.n, 200, date(2026, 10, 10))
        merma_de(l1, 20, "plaga", date(2026, 10, 20))  # antes del período: baja lo «al inicio»
        merma_de(l1, 18, "plaga", date(2026, 11, 5))
        merma_de(l1, 9, "enfermedad", date(2026, 11, 20))
        l2 = lote_sembrado(self.n, 100, date(2026, 11, 8))
        merma_de(l2, 3, "plaga", date(2026, 11, 15))
        return l1, l2

    def test_regla_indicador_2_porcentaje_sobre_lo_que_habia_al_inicio_mas_lo_sembrado(self):
        """D-93 punto 3.2: perdidas 30 (18 + 9 + 3) ÷ (180 al inicio + 100 sembradas) × 100 = 10,7 %; reparto por causa en plantas y % del total perdido."""
        self.armar_el_caso_base()
        r = self.indicador(self.n)
        self.assertEqual((r.perdidas, r.al_inicio, r.sembradas_en_el_periodo, r.denominador), (30, 180, 100, 280))
        self.assertEqual(r.porcentaje, Decimal("10.7"))
        self.assertEqual(
            list(r.por_causa),
            [FilaDeCausa("plaga", "Plaga", 21, Decimal("70.0")), FilaDeCausa("enfermedad", "Enfermedad", 9, Decimal("30.0"))],
        )

    def test_d93_punto_3_2_las_mermas_de_partidas_en_camara_no_cuentan(self):
        """D-93 punto 3.2: no entran las mermas de partidas en cámara (producto ya cosechado): daño y vencimiento en cámara."""
        l1, _ = self.armar_el_caso_base()
        merma_de(l1, 50, "dano_en_camara", date(2026, 11, 12))
        merma_de(l1, 5, "vencimiento_en_camara", date(2026, 11, 14))
        r = self.indicador(self.n)
        self.assertEqual((r.perdidas, r.denominador), (30, 280))
        self.assertEqual([f.causa for f in r.por_causa], ["plaga", "enfermedad"])

    def test_d93_punto_3_2_el_dano_en_la_entrega_si_cuenta(self):
        """D-93 punto 3.2: la merma de «daño en la entrega» es una merma de lote y sí cuenta."""
        l1, _ = self.armar_el_caso_base()
        entrega = orden(self.n.invernadero, T.ENTREGA, date(2026, 11, 12))
        merma_de(l1, 4, "dano_en_entrega", date(2026, 11, 12), orden_de_entrega=entrega)
        r = self.indicador(self.n)
        self.assertEqual(r.perdidas, 34)
        self.assertIn(("dano_en_entrega", 4), [(f.causa, f.plantas) for f in r.por_causa])

    def test_d93_punto_3_2_las_mermas_de_camara_anteriores_tampoco_bajan_lo_que_habia_al_inicio(self):
        """D-93 punto 3.2: «al inicio» descuenta las mermas del lote, no las de cámara."""
        lote = lote_sembrado(self.n, 100, date(2026, 10, 1))
        merma_de(lote, 30, "dano_en_camara", date(2026, 10, 20))
        self.assertEqual(self.indicador(self.n).al_inicio, 100)

    def test_d93_punto_3_2_el_reparto_por_causa_va_de_mayor_a_menor_y_suma_cien(self):
        """D-93 punto 3.2: el reparto por causa (plantas y % del total perdido) va de la causa con más plantas a la que tiene menos."""
        lote = lote_sembrado(self.n, 1000, date(2026, 10, 1))
        merma_de(lote, 1, "otra", date(2026, 11, 3))
        merma_de(lote, 2, "plaga", date(2026, 11, 3))
        merma_de(lote, 1, "enfermedad", date(2026, 11, 3))
        r = self.indicador(self.n)
        self.assertEqual([(f.causa, f.plantas, f.porcentaje) for f in r.por_causa][0], ("plaga", 2, Decimal("50.0")))
        self.assertEqual(sum(f.plantas for f in r.por_causa), 4)

    def test_caso_1_carga_inicial_anterior_al_periodo_y_registrada_adentro_cuenta_al_inicio_y_no_pasa_de_100(self):
        """D-93 punto 3.2 + D-103 (decisión del estudiante, 26/11/2026): un lote existente sembrado el 01/09 y registrado el 05/11 (su orden
        queda resuelta ese día) cuenta en «al inicio» por su `fecha_siembra`; si pierde todo en el período el porcentaje es 100 %, no más."""
        lote = lote_cargado(self.n, 50, date(2026, 9, 1))
        OrdenTrabajo.objects.filter(pk=lote.siembra_id).update(fecha_resolucion_orden=date(2026, 11, 5))
        merma_de(lote, 50, "plaga", date(2026, 11, 10))
        r = self.indicador(self.n)
        self.assertEqual((r.perdidas, r.al_inicio, r.denominador), (50, 50, 50))
        self.assertEqual(r.porcentaje, Decimal("100.0"))
        self.assertLessEqual(r.porcentaje, Decimal("100"))

    def test_caso_2_carga_inicial_con_fecha_dentro_del_periodo_suma_al_denominador_pero_no_a_sembradas(self):
        """D-93 punto 3.2 + D-92 punto 12 (decisión del estudiante): la carga inicial con `fecha_siembra` dentro del período suma al denominador
        (no se pierden plantas sin base) pero NO al indicador «Sembradas»."""
        lote = lote_cargado(self.n, 80, date(2026, 11, 10))
        merma_de(lote, 8, "plaga", date(2026, 11, 12))
        r = self.indicador(self.n)
        self.assertEqual((r.al_inicio, r.sembradas_en_el_periodo, r.denominador), (0, 80, 80))
        self.assertEqual(r.porcentaje, Decimal("10.0"))
        sembradas = produccion.sembradas_y_cosechadas(ids_de(self.n), PERIODO)
        self.assertEqual((sembradas.sembradas, list(sembradas.filas)), (0, []))

    def test_caso_3_siembra_normal_concretada_en_el_periodo_con_fecha_efectiva_anterior_cuenta_al_inicio(self):
        """D-93 punto 3.2 + D-103 (decisión del estudiante): una siembra concretada el 02/11 con fecha efectiva 30/10 cuenta «al inicio» del
        período que empieza el 01/11, y no en «Sembradas»."""
        lote = lote_sembrado(self.n, 120, date(2026, 10, 30), resolucion=date(2026, 11, 2))
        merma_de(lote, 12, "plaga", date(2026, 11, 10))
        r = self.indicador(self.n)
        self.assertEqual((r.al_inicio, r.sembradas_en_el_periodo, r.denominador), (120, 0, 120))
        self.assertEqual(r.porcentaje, Decimal("10.0"))
        self.assertEqual(produccion.sembradas_y_cosechadas(ids_de(self.n), PERIODO).sembradas, 0)

    def armar_el_caso_de_mermas_y_cosechas_previas(self):
        """Dos lotes sembrados antes del período, con mermas y cosechas anteriores a «desde» (y una merma y una cosecha en el primer día)."""
        a = lote_sembrado(self.n, 500, date(2026, 9, 1))
        merma_de(a, 40, "plaga", date(2026, 9, 20))
        merma_de(a, 60, "enfermedad", date(2026, 10, 31))  # el último día antes del período: se descuenta
        salida_por_cosecha(a, 300, date(2026, 10, 31), hora=time(23, 59))  # también
        salida_por_cosecha(a, 50, DESDE, hora=time(0, 0))  # las 00:00 del primer día ya son del período: no se descuenta
        merma_de(a, 10, "plaga", DESDE)  # una merma del primer día: del período, no «previa»
        b = lote_sembrado(self.n, 100, date(2026, 9, 5))
        merma_de(b, 70, "plaga", date(2026, 10, 1))
        salida_por_cosecha(b, 50, date(2026, 10, 2))

    def test_caso_4_las_mermas_y_las_cosechas_anteriores_se_descuentan_y_si_queda_negativo_vale_cero(self):
        """D-93 punto 3.2 (decisión del estudiante): lote A = 500 − 40 − 60 − 300 = 100; lote B = 100 − 70 − 50 = −20 → 0. «Al inicio» = 100."""
        self.armar_el_caso_de_mermas_y_cosechas_previas()
        r = self.indicador(self.n)
        self.assertEqual((r.perdidas, r.al_inicio, r.denominador), (10, 100, 100))
        self.assertEqual(r.porcentaje, Decimal("10.0"))

    def test_d93_punto_5_sin_cosecha_disponible_las_cosechas_no_se_descuentan_de_lo_que_habia_al_inicio(self):
        """D-93 punto 5: sin la fuente de la cosecha no se restan plantas cosechadas: A = 500 − 100 = 400; B = max(0, 100 − 70) = 30."""
        self.armar_el_caso_de_mermas_y_cosechas_previas()
        with mock.patch.object(produccion, "cosecha_disponible", return_value=False):
            r = self.indicador(self.n)
        self.assertEqual(r.al_inicio, 430)

    def test_d93_punto_3_2_un_lote_sembrado_despues_del_periodo_no_cuenta_en_el_denominador(self):
        """D-93 punto 3.2: solo cuentan los lotes sembrados antes de «desde» o dentro del período."""
        lote_sembrado(self.n, 100, date(2026, 11, 27))
        r = self.indicador(self.n)
        self.assertEqual((r.al_inicio, r.sembradas_en_el_periodo, r.denominador), (0, 0, 0))

    def test_d93_punto_3_2_con_denominador_cero_el_porcentaje_no_se_calcula(self):
        """D-93 punto 3.2: «con denominador 0, —» (`None`), también si hay perdidas (un dato inconsistente no rompe la pantalla)."""
        vacio = self.indicador(self.n)
        self.assertEqual((vacio.perdidas, vacio.denominador, vacio.porcentaje, list(vacio.por_causa)), (0, 0, None, []))
        lote = lote_sembrado(self.n, 10, date(2026, 11, 27))
        merma_de(lote, 5, "plaga", date(2026, 11, 20))
        r = self.indicador(self.n)
        self.assertEqual((r.perdidas, r.denominador, r.porcentaje), (5, 0, None))

    def test_regla_alcance_no_mezcla_otros_invernaderos(self):
        """EST-CNS-PRD regla 1: una merma de otro invernadero no entra en el cálculo."""
        self.armar_el_caso_base()
        lote = lote_sembrado(self.s, 100, date(2026, 10, 1), variedad=self.s.variedad)
        merma_de(lote, 40, "plaga", date(2026, 11, 3))
        self.assertEqual(self.indicador(self.n).perdidas, 30)
        self.assertEqual(self.indicador(self.s).perdidas, 40)
        self.assertEqual(self.indicador(self.n, self.s).perdidas, 70)

    def test_d93_punto_7_tres_consultas_con_pocas_o_muchas_filas(self):
        """D-93 punto 7: el bloque hace 3 consultas (perdidas por causa, lo que había al inicio y lo sembrado), no una por lote."""
        ids = ids_de(self.n)
        with self.assertNumQueries(3):
            produccion.merma(ids, PERIODO)
        self.armar_el_caso_base()
        self.armar_el_caso_de_mermas_y_cosechas_previas()
        with self.assertNumQueries(3):
            produccion.merma(ids, PERIODO)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 3 · Órdenes a tiempo frente a vencidas (D-93 punto 3.3)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdOrdenesServicioTests(ConCatalogoIot, TestCase):
    """Indicador 3: las órdenes con `fecha_programada_orden` en el período, sin las canceladas, a tiempo o vencidas."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        inv = cls.n.invernadero
        orden(inv, T.SIEMBRA, date(2026, 11, 5))  # concretada el día programado: a tiempo
        orden(inv, T.SIEMBRA, date(2026, 11, 6), resolucion=date(2026, 11, 4))  # concretada antes: a tiempo
        orden(inv, T.SIEMBRA, date(2026, 11, 5), resolucion=date(2026, 11, 7))  # concretada después: vencida
        orden(inv, T.SIEMBRA, date(2026, 11, 10), estado="a_realizar")  # programada pasada y sin hacer: vencida
        orden(inv, T.SIEMBRA, HOY, estado="a_realizar")  # programada para hoy: todavía no vence, no cuenta
        orden(inv, T.SIEMBRA, date(2026, 11, 10), estado="cancelada")  # cancelada: no cuenta
        orden(inv, T.SIEMBRA, date(2026, 10, 31))  # fuera del período
        orden(inv, T.COSECHA, date(2026, 11, 12))  # a tiempo
        orden(inv, T.ENTREGA, date(2026, 11, 15), resolucion=date(2026, 11, 16))  # vencida
        orden(inv, T.MANTENIMIENTO, date(2026, 11, 20))  # a tiempo

    def indicador(self, *escenarios, hoy=HOY, solo_produccion=False, periodo=PERIODO):
        """El indicador 3 del período por defecto para los invernaderos de los escenarios."""
        return produccion.ordenes_a_tiempo(ids_de(*escenarios), periodo, hoy, solo_produccion=solo_produccion)

    def test_regla_indicador_3_todas_las_ordenes_a_tiempo_y_vencidas_con_su_desglose_por_tipo(self):
        """D-93 punto 3.3 («Todas»): siembra 2 a tiempo y 2 vencidas; cosecha 1 a tiempo; entrega 1 vencida; mantenimiento 1 a tiempo. Total 4 a
        tiempo y 3 vencidas de 7: 57,1 % y 42,9 %. Las canceladas, las «a realizar» de hoy y las de fuera del período no cuentan."""
        r = self.indicador(self.n)
        self.assertEqual(
            list(r.filas),
            [
                FilaDeOrdenes("siembra", "Siembra", 2, 2, 4, Decimal("50.0")),
                FilaDeOrdenes("cosecha", "Cosecha", 1, 0, 1, Decimal("100.0")),
                FilaDeOrdenes("entrega", "Entrega", 0, 1, 1, Decimal("0.0")),
                FilaDeOrdenes("mantenimiento", "Mantenimiento técnico", 1, 0, 1, Decimal("100.0")),
            ],
        )
        self.assertEqual((r.a_tiempo, r.vencidas, r.total), (4, 3, 7))
        self.assertEqual((r.porcentaje_a_tiempo, r.porcentaje_vencidas), (Decimal("57.1"), Decimal("42.9")))

    def test_d93_punto_3_3_solo_de_produccion_deja_siembra_transicion_y_cosecha(self):
        """D-93 punto 3.3 (selector «Solo de producción», decisión de Ezequiel): entrega y mantenimiento quedan afuera: 3 a tiempo y 2 vencidas de 5."""
        r = self.indicador(self.n, solo_produccion=True)
        self.assertEqual([f.tipo for f in r.filas], ["siembra", "cosecha"])
        self.assertEqual((r.a_tiempo, r.vencidas, r.total), (3, 2, 5))
        self.assertEqual((r.porcentaje_a_tiempo, r.porcentaje_vencidas), (Decimal("60.0"), Decimal("40.0")))

    def test_d93_punto_3_3_solo_de_produccion_usa_los_tipos_de_produccion_de_prd_01(self):
        """D-67 punto 1 / D-93 punto 3.3: «de producción» son los de `TIPOS_DE_PRODUCCION` (siembra, transición y cosecha)."""
        self.assertEqual(set(TIPOS_DE_PRODUCCION), {T.SIEMBRA, T.TRANSICION, T.COSECHA})
        orden(self.n.invernadero, T.TRANSICION, date(2026, 11, 8))
        self.assertIn("transicion", [f.tipo for f in self.indicador(self.n, solo_produccion=True).filas])

    def test_d93_punto_3_3_una_orden_a_realizar_vence_solo_si_su_fecha_es_anterior_a_hoy(self):
        """D-93 punto 3.3: «vencida» = «a realizar» con `fecha_programada_orden < hoy`: con hoy = 10/11, la del 10/11 todavía no vence y la del 09/11 sí."""
        inv = self.s.invernadero
        orden(inv, T.SIEMBRA, date(2026, 11, 9), estado="a_realizar")
        orden(inv, T.SIEMBRA, date(2026, 11, 10), estado="a_realizar")
        r = self.indicador(self.s, hoy=date(2026, 11, 10), periodo=Periodo(DESDE, date(2026, 11, 10)))
        self.assertEqual((r.a_tiempo, r.vencidas, r.total), (0, 1, 1))

    def test_d93_punto_3_3_sin_ordenes_no_hay_porcentajes(self):
        """D-93 punto 3.3: sin órdenes en el período no hay con qué calcular un porcentaje (`None`)."""
        r = self.indicador(self.s)
        self.assertEqual((list(r.filas), r.total, r.porcentaje_a_tiempo, r.porcentaje_vencidas), ([], 0, None, None))

    def test_regla_alcance_solo_cuenta_los_invernaderos_pedidos(self):
        """EST-CNS-PRD regla 1: las órdenes de otro invernadero no entran; el consolidado las suma."""
        orden(self.s.invernadero, T.SIEMBRA, date(2026, 11, 9))
        self.assertEqual(self.indicador(self.n).total, 7)
        self.assertEqual(self.indicador(self.s).total, 1)
        self.assertEqual(self.indicador(self.n, self.s).total, 8)

    def test_d93_punto_7_una_consulta_con_pocas_o_muchas_filas(self):
        """D-93 punto 7: el bloque hace 1 consulta, sin importar cuántas órdenes ni tipos haya."""
        with self.assertNumQueries(1):
            self.indicador(self.s)
        with self.assertNumQueries(1):
            self.indicador(self.n)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 4 · Costo promedio por planta cosechada (D-93 punto 3.4; paso 3)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdCostoPorPlantaServicioTests(ConCatalogoIot, TestCase):
    """Indicador 4: Σ costo de las salidas por cosecha del período ÷ Σ plantas cosechadas, a 2 decimales."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.lote = lote_sembrado(cls.n, 500, date(2026, 10, 1))

    def indicador(self, *escenarios):
        """El indicador 4 del período por defecto para los invernaderos de los escenarios."""
        return produccion.costo_por_planta_cosechada(ids_de(*escenarios), PERIODO)

    def test_regla_indicador_4_costo_de_las_salidas_por_cosecha_sobre_las_plantas_cosechadas(self):
        """D-93 punto 3.4: 40 plantas a 2,5000 ($ 100,00) + 60 a 3,0000 ($ 180,00) = $ 280,00 ÷ 100 plantas = $ 2,80."""
        salida_por_cosecha(self.lote, 40, date(2026, 11, 10), "2.5000")
        salida_por_cosecha(self.lote, 60, date(2026, 11, 20), "3.0000")
        r = self.indicador(self.n)
        self.assertEqual((r.disponible, r.plantas, r.costo, r.costo_por_planta), (True, 100, Decimal("280.0000"), Decimal("2.80")))

    def test_d93_punto_3_4_redondea_a_dos_decimales_con_la_mitad_hacia_arriba(self):
        """D-93 punto 3.4 y convención de dinero: 8 plantas a 2,6750 = $ 21,40 ÷ 8 = 2,675 → $ 2,68 (ROUND_HALF_UP); `Decimal`, nunca `float`."""
        salida_por_cosecha(self.lote, 8, date(2026, 11, 10), "2.6750")
        r = self.indicador(self.n)
        self.assertEqual(r.costo_por_planta, Decimal("2.68"))
        self.assertIsInstance(r.costo_por_planta, Decimal)

    def test_d93_punto_3_4_no_cuenta_otras_fechas_ni_otros_movimientos(self):
        """D-93 punto 3.4: solo las salidas por cosecha del período; ni la del día anterior ni una salida por merma."""
        salida_por_cosecha(self.lote, 10, date(2026, 11, 10), "2.0000")
        salida_por_cosecha(self.lote, 99, date(2026, 10, 31), "9.0000", hora=time(23, 59))
        salida_por_cosecha(self.lote, 99, date(2026, 11, 11), "9.0000", tipo="salida_por_merma")
        r = self.indicador(self.n)
        self.assertEqual((r.plantas, r.costo, r.costo_por_planta), (10, Decimal("20.0000"), Decimal("2.00")))

    def test_d93_punto_3_4_sin_cosechas_no_hay_costo_por_planta(self):
        """D-93 punto 3.4: sin plantas cosechadas no se divide: «—» (`None`)."""
        r = self.indicador(self.n)
        self.assertEqual((r.disponible, r.plantas, r.costo, r.costo_por_planta), (True, 0, Decimal("0"), None))

    def test_d93_punto_5_sin_cosecha_disponible_el_indicador_no_se_muestra(self):
        """D-93 punto 5: sin la fuente de la cosecha el indicador queda «no disponible» y sin valores."""
        with mock.patch.object(produccion, "cosecha_disponible", return_value=False):
            r = self.indicador(self.n)
        self.assertEqual((r.disponible, r.plantas, r.costo, r.costo_por_planta), (False, None, None, None))

    def test_regla_alcance_solo_cuenta_los_invernaderos_pedidos(self):
        """EST-CNS-PRD regla 1: el costo de las cosechas de otro invernadero no se mezcla."""
        salida_por_cosecha(self.lote, 10, date(2026, 11, 10), "2.0000")
        lote_sur = lote_sembrado(self.s, 100, date(2026, 10, 1), variedad=self.s.variedad)
        salida_por_cosecha(lote_sur, 10, date(2026, 11, 10), "4.0000")
        self.assertEqual(self.indicador(self.n).costo_por_planta, Decimal("2.00"))
        self.assertEqual(self.indicador(self.s).costo_por_planta, Decimal("4.00"))
        self.assertEqual(self.indicador(self.n, self.s).costo_por_planta, Decimal("3.00"))

    def test_d93_punto_7_una_consulta_con_pocas_o_muchas_filas(self):
        """D-93 punto 7: el bloque hace 1 consulta, sin importar cuántas salidas haya."""
        with self.assertNumQueries(1):
            self.indicador(self.n)
        for dia in range(2, 12):
            salida_por_cosecha(self.lote, 1, date(2026, 11, dia), "1.0000")
        with self.assertNumQueries(1):
            self.indicador(self.n)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 5 · Consumo de insumos (D-93 punto 3.5)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdConsumoServicioTests(ConCatalogoIot, TestCase):
    """Indicador 5: los consumos con su fecha en el período (siembra, aplicación y envases de entregas): monto por categoría y cantidad por insumo."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        inv = cls.n.invernadero
        cls.nitrato = insumo_adicional(cls.n, "Nitrato", stock=0, unidad="kg")
        cls.hipoclorito = insumo_adicional(cls.n, "Hipoclorito", stock=0, unidad="l")
        cls.envase = existencia_de_envase(inv)
        lote = lote_sembrado(cls.n, 100, date(2026, 11, 5))
        consumo_de(inv, cls.n.existencia_semilla, "200.00", "100.000", date(2026, 11, 5), siembra=lote.siembra)
        aplicacion = aplicacion_de(inv, date(2026, 11, 10))
        consumo_de(inv, cls.nitrato, "10.00", "2.500", date(2026, 11, 10), aplicacion=aplicacion)
        consumo_de(inv, cls.nitrato, "5.00", "1.250", date(2026, 11, 12), aplicacion=aplicacion)
        consumo_de(inv, cls.hipoclorito, "3.00", "0.500", date(2026, 11, 15), aplicacion=aplicacion)
        consumo_de(inv, cls.envase, "60.00", "40.000", date(2026, 11, 20), orden_de_entrega=orden(inv, T.ENTREGA, date(2026, 11, 20)))
        consumo_de(inv, cls.nitrato, "999.00", "9.000", date(2026, 10, 31), aplicacion=aplicacion)  # fuera del período

    def indicador(self, *escenarios):
        """El indicador 5 del período por defecto para los invernaderos de los escenarios."""
        return produccion.consumo_de_insumos(ids_de(*escenarios), PERIODO)

    def fila(self, existencia, cantidad, monto):
        """La fila esperada de un insumo (con el texto de su unidad)."""
        insumo = existencia.insumo
        return FilaDeInsumo(
            insumo.pk, insumo.nombre_insumo, insumo.unidad_medida_insumo, Unidad(insumo.unidad_medida_insumo).label,
            Decimal(cantidad), Decimal(monto),
        )

    def test_regla_indicador_5_monto_por_categoria_y_cantidad_por_insumo_con_su_unidad(self):
        """D-93 punto 3.5: monto por categoría (con el total) y cantidad por insumo con su unidad dentro de su categoría; las cantidades de
        insumos distintos no se suman (kg de nitrato y L de hipoclorito son filas distintas de «Fertilizantes»). Entran los consumos de siembra,
        de aplicación y de los envases de una entrega; no el de fuera del período. Categorías e insumos, por nombre."""
        r = self.indicador(self.n)
        semillas = categoria_del_sistema("semillas")
        envases = categoria_del_sistema("envases")
        fertilizantes = self.nitrato.insumo.tipo_insumo
        esperadas = sorted(
            [
                FilaDeCategoria(envases.pk, envases.nombre_tipo_insumo, Decimal("60.00"), [self.fila(self.envase, "40", "60.00")]),
                FilaDeCategoria(
                    fertilizantes.pk,
                    fertilizantes.nombre_tipo_insumo,
                    Decimal("18.00"),
                    [self.fila(self.hipoclorito, "0.500", "3.00"), self.fila(self.nitrato, "3.750", "15.00")],
                ),
                FilaDeCategoria(
                    semillas.pk, semillas.nombre_tipo_insumo, Decimal("200.00"), [self.fila(self.n.existencia_semilla, "100", "200.00")]
                ),
            ],
            key=lambda c: c.nombre,
        )
        self.assertEqual(list(r.categorias), esperadas)
        self.assertEqual(r.monto_total, Decimal("278.00"))

    def test_d93_punto_3_5_el_mismo_insumo_de_dos_invernaderos_se_suma(self):
        """D-93 punto 3.5: el insumo es del catálogo (compartido): consumir el mismo en dos invernaderos suma su cantidad y su monto."""
        del_sur = existencia_de(self.s.invernadero, self.nitrato.insumo)
        consumo_de(
            self.s.invernadero, del_sur, "4.00", "1.000", date(2026, 11, 11), aplicacion=aplicacion_de(self.s.invernadero, date(2026, 11, 11))
        )
        solo_norte = {f.nombre: f for c in self.indicador(self.n).categorias for f in c.insumos}
        ambos = {f.nombre: f for c in self.indicador(self.n, self.s).categorias for f in c.insumos}
        self.assertEqual((solo_norte["Nitrato"].cantidad, solo_norte["Nitrato"].monto), (Decimal("3.750"), Decimal("15.00")))
        self.assertEqual((ambos["Nitrato"].cantidad, ambos["Nitrato"].monto), (Decimal("4.750"), Decimal("19.00")))
        self.assertEqual(self.indicador(self.n, self.s).monto_total, Decimal("282.00"))

    def test_regla_alcance_otro_invernadero_sin_consumos_no_aporta(self):
        """EST-CNS-PRD regla 1: sin consumos no hay categorías ni total."""
        r = self.indicador(self.s)
        self.assertEqual((list(r.categorias), r.monto_total), ([], Decimal("0")))

    def test_d93_punto_3_5_los_montos_son_decimal(self):
        """Convención de dinero: montos y cantidades son `Decimal`, nunca `float`."""
        r = self.indicador(self.n)
        self.assertIsInstance(r.monto_total, Decimal)
        self.assertIsInstance(r.categorias[0].monto, Decimal)
        self.assertIsInstance(r.categorias[0].insumos[0].cantidad, Decimal)

    def test_d93_punto_7_una_consulta_con_pocas_o_muchas_filas(self):
        """D-93 punto 7: el bloque hace 1 consulta, sin importar cuántos consumos, insumos o categorías haya."""
        with self.assertNumQueries(1):
            self.indicador(self.s)
        with self.assertNumQueries(1):
            self.indicador(self.n)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 6 · Alertas del IoT (D-93 punto 3.6)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdAlertasIotServicioTests(ConCatalogoIot, TestCase):
    """Indicador 6: alertas del IoT del período por tipo, solo de los invernaderos que tienen un sistema IoT."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        sistema(cls.n.invernadero)  # el Norte tiene IoT; el Sur, no
        inv = cls.n.invernadero
        crear_alerta(inv, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 5, 15))
        crear_alerta(inv, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 20, 15))
        crear_alerta(inv, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 8, 15), resuelta=True)  # resuelta: igual cuenta
        crear_alerta(inv, "iot_dispositivo_en_falla", fecha_hora_alerta=instante_utc(2026, 11, 27, 1))  # 22:00 del 26/11 local: último día
        crear_alerta(inv, "iot_dispositivo_en_falla", fecha_hora_alerta=instante_utc(2026, 11, 1, 2))  # 23:00 del 31/10 local: fuera
        crear_alerta(inv, "prueba_evento", fecha_hora_alerta=instante_utc(2026, 11, 10, 15))  # no es un tipo del IoT
        crear_alerta(cls.s.invernadero, "iot_lectura_invalida", fecha_hora_alerta=instante_utc(2026, 11, 10, 15))  # el Sur no tiene IoT

    def indicador(self, *escenarios):
        """El indicador 6 del período por defecto para los invernaderos de los escenarios."""
        return produccion.alertas_iot(ids_de(*escenarios), PERIODO)

    def test_regla_indicador_6_cantidad_por_tipo_de_los_invernaderos_con_iot(self):
        """D-93 punto 3.6: `Alerta` de un tipo de `TIPOS_DE_ALERTA_DE_IOT` con `fecha_hora_alerta` en el período (día local), por tipo y de mayor
        a menor, de los invernaderos con IoT: 3 «Fuera de umbral efectivo» (una resuelta) y 1 «Dispositivo en falla». Quedan afuera la de
        las 23:00 del 31/10 local, la de un tipo que no es del IoT y la del invernadero sin IoT."""
        r = self.indicador(self.n, self.s)
        self.assertEqual(
            r,
            AlertasIot(
                [FilaDeAlertas("iot_fuera_de_umbral", "Fuera de umbral efectivo", 3), FilaDeAlertas("iot_dispositivo_en_falla", "Dispositivo en falla", 1)],
                4,
            ),
        )

    def test_regla_indicador_6_sin_iot_en_el_alcance_el_bloque_no_se_muestra(self):
        """EST-CNS-PRD regla 4.6: «solo si el invernadero tiene un sistema IoT; si no, no se muestra» (`None`)."""
        self.assertIsNone(self.indicador(self.s))
        self.assertIsNone(produccion.alertas_iot([], PERIODO))

    def test_regla_indicador_6_con_iot_y_sin_alertas_muestra_cero(self):
        """EST-CNS-PRD regla 4.6: un invernadero con IoT y sin alertas en el período muestra el bloque, vacío."""
        r = produccion.alertas_iot(ids_de(self.n), Periodo(date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual((list(r.filas), r.total), ([], 0))

    def test_d93_punto_7_dos_consultas_con_pocas_o_muchas_filas(self):
        """D-93 punto 7: 2 consultas (el estado del IoT de los invernaderos y las alertas), no una por invernadero ni por alerta."""
        with self.assertNumQueries(2):
            self.indicador(self.n, self.s)
        for dia in range(2, 12):
            crear_alerta(self.n.invernadero, "iot_nodo_sin_comunicacion", fecha_hora_alerta=instante_utc(2026, 11, dia, 15))
        with self.assertNumQueries(2):
            self.indicador(self.n, self.s)


# ---------------------------------------------------------------------------------------------------------------------------------
# El armado completo: alcance por rol, comparación y consultas (EST-CNS-PRD reglas 1 y 2; D-93 puntos 2 y 7)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsPrdEstadisticasServicioTests(ConCatalogoIot, TestCase):
    """`estadisticas_de_produccion`: arma los seis indicadores con el alcance del actor y, si se pide, los del período anterior."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.gerente = crear_gerente()
        lote_sembrado(cls.n, 100, date(2026, 11, 5))
        lote_sembrado(cls.s, 40, date(2026, 11, 6), variedad=cls.s.variedad)
        lote_sembrado(cls.n, 60, date(2026, 10, 10))  # del período anterior (06/10 al 31/10)

    def pedir(self, actor, invernadero_id=None, comparar=False, solo_produccion=False):
        """Las estadísticas del período por defecto, con `hoy` = HOY."""
        return produccion.estadisticas_de_produccion(actor, invernadero_id, PERIODO, comparar, HOY, solo_produccion=solo_produccion)

    def test_regla_alcance_el_agronomo_ve_solo_sus_invernaderos(self):
        """EST-CNS-PRD regla 1: el Agrónomo ve los invernaderos que tiene a cargo. Norte: 100 sembradas; no ve las del Sur."""
        r = self.pedir(self.n.agronomo)
        self.assertEqual([(i.pk, i.nombre) for i in r.invernaderos], [(self.n.invernadero.pk, "Invernadero Norte")])
        self.assertEqual(r.actual.sembradas_y_cosechadas.sembradas, 100)

    def test_regla_alcance_el_gerente_ve_todos_y_puede_filtrar_por_uno(self):
        """EST-CNS-PRD regla 1: el Gerente ve todos (consolidado 140) y puede filtrar por invernadero (Sur: 40)."""
        todos = self.pedir(self.gerente)
        self.assertEqual([i.nombre for i in todos.invernaderos], ["Invernadero Norte", "Invernadero Sur"])
        self.assertEqual((todos.invernadero_id, todos.actual.sembradas_y_cosechadas.sembradas), (None, 140))
        sur = self.pedir(self.gerente, self.s.invernadero.pk)
        self.assertEqual((sur.invernadero_id, sur.actual.sembradas_y_cosechadas.sembradas), (self.s.invernadero.pk, 40))

    def test_regla_alcance_un_agronomo_con_dos_invernaderos_los_ve_y_uno_inactivo_se_oculta(self):
        """EST-CNS-PRD regla 1 y `Invernadero.objects.en_alcance_de`: el Agrónomo ve sus invernaderos activos."""
        Invernadero.objects.filter(pk=self.s.invernadero.pk).update(agronomo=self.n.agronomo)
        self.assertEqual(self.pedir(self.n.agronomo).actual.sembradas_y_cosechadas.sembradas, 140)
        Invernadero.objects.filter(pk=self.s.invernadero.pk).update(estado_invernadero="inactivo")
        r = self.pedir(self.n.agronomo)
        self.assertEqual([i.nombre for i in r.invernaderos], ["Invernadero Norte"])
        self.assertEqual(r.actual.sembradas_y_cosechadas.sembradas, 100)

    def test_regla_alcance_un_invernadero_ajeno_es_un_error_de_validacion(self):
        """EST-CNS-PRD regla 1: pedir el invernadero de otro Agrónomo es un `ValidationError` (código `invernadero_fuera_de_alcance`)."""
        with self.assertRaises(ValidationError) as contexto:
            self.pedir(self.n.agronomo, self.s.invernadero.pk)
        self.assertEqual(contexto.exception.code, "invernadero_fuera_de_alcance")

    def test_regla_alcance_un_rol_sin_acceso_no_tiene_invernaderos(self):
        """EST-CNS-PRD regla 7: el Capataz no tiene acceso; el servicio no le arma nada (la vista responde 403 antes)."""
        r = self.pedir(self.n.capataz)
        self.assertEqual(list(r.invernaderos), [])
        self.assertEqual(r.actual.sembradas_y_cosechadas.sembradas, 0)

    def test_regla_filtros_sin_comparar_no_trae_el_periodo_anterior(self):
        """EST-CNS-PRD regla 2: con la comparación apagada solo se arma el período actual; el anterior se informa igual (06/10 al 31/10)."""
        r = self.pedir(self.gerente, comparar=False)
        self.assertEqual((r.periodo, r.anterior), (PERIODO, Periodo(date(2026, 10, 6), date(2026, 10, 31))))
        self.assertEqual((r.previo, r.comparaciones), (None, {}))

    def test_regla_filtros_comparar_trae_el_periodo_anterior_y_la_comparacion_de_cada_indicador(self):
        """EST-CNS-PRD regla 2 y D-93 punto 2: se compara con el período anterior de igual duración. Sembradas: 100 contra 60 = +40, +66,7 %."""
        r = self.pedir(self.n.agronomo, comparar=True)
        self.assertEqual(r.previo.sembradas_y_cosechadas.sembradas, 60)
        self.assertEqual(r.comparaciones["sembradas"], Comparacion(Decimal(100), Decimal(60), Decimal(40), Decimal("66.7")))
        self.assertEqual(
            set(r.comparaciones), {"sembradas", "cosechadas", "merma", "ordenes_a_tiempo", "costo_por_planta", "consumo"}
        )
        self.assertEqual(r.comparaciones["costo_por_planta"], periodos.comparar(None, None))

    def test_regla_alertas_iot_con_iot_se_muestran_y_se_comparan(self):
        """EST-CNS-PRD regla 4.6: con un invernadero con IoT en el alcance el bloque existe y se compara; sin IoT, no hay bloque ni comparación."""
        sin_iot = self.pedir(self.n.agronomo, comparar=True)
        self.assertIsNone(sin_iot.actual.alertas_iot)
        self.assertNotIn("alertas_iot", sin_iot.comparaciones)
        sistema(self.n.invernadero)
        crear_alerta(self.n.invernadero, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 5, 15))
        con_iot = self.pedir(self.n.agronomo, comparar=True)
        self.assertEqual(con_iot.actual.alertas_iot.total, 1)
        self.assertEqual(con_iot.comparaciones["alertas_iot"], Comparacion(Decimal(1), Decimal(0), Decimal(1), None))

    def test_d93_punto_3_3_el_selector_de_ordenes_llega_hasta_el_indicador(self):
        """D-93 punto 3.3: «Solo de producción» deja afuera la entrega vencida; «Todas» la cuenta. El Norte tiene además la orden de la siembra del
        05/11 (a tiempo, la de su lote de 100 plantas): 2 órdenes en «Todas» y 1 en «Solo de producción»."""
        orden(self.n.invernadero, T.ENTREGA, date(2026, 11, 15), resolucion=date(2026, 11, 16))
        todas = self.pedir(self.n.agronomo)
        solo = self.pedir(self.n.agronomo, solo_produccion=True)
        self.assertEqual((todas.actual.ordenes.total, solo.actual.ordenes.total), (2, 1))
        self.assertEqual((todas.actual.ordenes.vencidas, solo.actual.ordenes.vencidas), (1, 0))

    def test_d93_punto_7_consultas_fijas_con_y_sin_comparacion(self):
        """D-93 punto 7: el armado completo hace 11 consultas (el alcance + 2 + 3 + 1 + 1 + 1 + 2) y 21 con la comparación (el alcance + el
        doble de los indicadores), con o sin datos."""
        sistema(self.n.invernadero)
        with self.assertNumQueries(11):
            self.pedir(self.n.agronomo)
        with self.assertNumQueries(21):
            self.pedir(self.n.agronomo, comparar=True)
        for dia in range(2, 8):
            lote = lote_sembrado(self.n, 10, date(2026, 11, dia))
            salida_por_cosecha(lote, 3, date(2026, 11, dia))
            merma_de(lote, 1, "plaga", date(2026, 11, dia))
            orden(self.n.invernadero, T.SIEMBRA, date(2026, 11, dia))
            crear_alerta(self.n.invernadero, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, dia, 15))
        with self.assertNumQueries(11):
            self.pedir(self.n.agronomo)
        with self.assertNumQueries(21):
            self.pedir(self.n.agronomo, comparar=True)
