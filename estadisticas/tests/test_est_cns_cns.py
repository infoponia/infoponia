# Pruebas de los servicios de EST-CNS-CNS «Consultar Estadísticas Consolidadas» (EST-02, pasos 1 a 3): el indicador 7 (producción comparando
# invernaderos y la merma en cámara, aparte), el 9 (compras) y el 10 (libro de gestión). Fuente: docs/casos_de_uso/estadisticas/estadisticas.md
# (EST-CNS-CNS, reglas 3 y «Decididas»), D-93 puntos 4 y 7, D-89 punto 4 y D-90 (la valorización de lo recibido y de lo corregido), D-86 y D-102 (las
# lecturas del libro). Cada prueba arma sus datos y calcula el resultado esperado a mano. Las compras se arman con los servicios reales de CMP-04 y
# CMP-06 y después se fijan las fechas de los documentos en la base (los servicios usan el día real de hoy).
#
# API que fijan estas pruebas (`estadisticas/servicios/consolidadas.py`; EST-02 suma `hoy` a la firma de «Cómo se aplica», como EST-01):
#   por_invernadero(periodo, hoy, solo_produccion=False) -> PorInvernadero(filas, dados_de_baja, total)         indicador 7; 9 consultas fijas
#       `filas`: una `FilaDeInvernadero(invernadero_id, nombre, sembradas, cosechadas, merma, ordenes_a_tiempo, costo_por_planta, consumo,
#       alertas_iot)` por invernadero ACTIVO, por nombre; `dados_de_baja`: la misma fila agrupada (id `None`) de los inactivos con actividad en el
#       período, o `None`; `total`: todos los invernaderos (también los inactivos): lo mismo que `estadisticas_de_produccion` del Gerente (EST-01).
#       `merma`, `ordenes_a_tiempo` (porcentajes) y `costo_por_planta` son `None` («—») sin base; `cosechadas` y `costo_por_planta`, `None` sin la
#       cosecha; `alertas_iot` es `None` si ningún invernadero de la fila tiene IoT
#   merma_en_camara(periodo) -> MermaEnCamara(causas, plantas, valor, sin_asiento)                              parte de 4.7; 2 consultas
#   compras(periodo) -> Compras(total, por_proveedor, por_categoria, por_mes)                                   indicador 9; 2 consultas
#   libro(periodo) -> LibroDeGestion(ventas, ingresos, egresos, resultado, ingresos_por_cuenta, costos_por_cuenta)   indicador 10; 2 + 2 por cuenta de resultado

from datetime import date
from decimal import Decimal

from django.test import TestCase

from compras.models import CorreccionRecepcion, Recepcion
from compras.tests.base_correcciones import CorreccionBase
from core.tests.fabricas import crear_gerente
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import CuentaContable, EjercicioContable, MovimientoContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio, ejercicio_abierto
from estadisticas.periodos import Periodo
from estadisticas.servicios import consolidadas, produccion
from estadisticas.servicios.consolidadas import FilaDeCausaDeCamara, FilaDeCuenta, FilaDeMes
from estadisticas.tests.fabricas import (
    DESDE,
    HOY,
    consumo_de,
    dos_invernaderos,
    existencia_de_envase,
    instante_utc,
    lote_sembrado,
    merma_de,
    merma_de_camara,
    orden,
    salida_por_cosecha,
)
from inventario.models import Insumo
from inventario.tests.fabricas import tipo_de_insumo
from iot.tests.fabricas import ConCatalogoIot, sistema
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_alerta
from produccion.models import OrdenTrabajo
from produccion.tests.fabricas import invernadero_con_produccion

T = OrdenTrabajo.Tipo
D = Decimal
PERIODO = Periodo(DESDE, HOY)


def como_est_01(ids, periodo=PERIODO, solo_produccion=False):
    """Lo que las funciones de EST-01 dan para esos invernaderos, en el orden de los campos de `FilaDeInvernadero` desde `sembradas`: la fuente
    de verdad que el indicador 7 no puede contradecir (D-93 punto 4.7: «los indicadores 1 a 5, y 6 si tiene IoT»)."""
    siembra = produccion.sembradas_y_cosechadas(ids, periodo)
    alertas = produccion.alertas_iot(ids, periodo)
    return (
        siembra.sembradas,
        siembra.cosechadas,
        produccion.merma(ids, periodo).porcentaje,
        produccion.ordenes_a_tiempo(ids, periodo, HOY, solo_produccion).porcentaje_a_tiempo,
        produccion.costo_por_planta_cosechada(ids, periodo).costo_por_planta,
        produccion.consumo_de_insumos(ids, periodo).monto_total,
        None if alertas is None else alertas.total,
    )


def est_01_del_gerente():
    """`estadisticas_de_produccion` (EST-01) del Gerente sobre todos los invernaderos, sin comparar: lo que el total del indicador 7 tiene que igualar."""
    return produccion.estadisticas_de_produccion(crear_gerente(), None, PERIODO, False, HOY)


def valores(fila):
    """Los valores de una `FilaDeInvernadero` sin su id ni su nombre."""
    return tuple(fila[2:])


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 7 · Producción comparando invernaderos (D-93 punto 4.7)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsCnsPorInvernaderoServicioTests(ConCatalogoIot, TestCase):
    """Indicador 7: una fila por invernadero activo con los indicadores 1 a 5 (y 6 si tiene IoT), la fila «Dados de baja» y el total."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.lote_n = lote_sembrado(cls.n, 100, date(2026, 11, 5))
        salida_por_cosecha(cls.lote_n, 30, date(2026, 11, 10), "2.0000")
        merma_de(cls.lote_n, 10, "plaga", date(2026, 11, 12))
        cls.lote_s = lote_sembrado(cls.s, 40, date(2026, 11, 6), variedad=cls.s.variedad)
        salida_por_cosecha(cls.lote_s, 10, date(2026, 11, 11), "3.0000")
        merma_de(cls.lote_s, 4, "enfermedad", date(2026, 11, 13))
        sistema(cls.n.invernadero)  # el Norte tiene IoT; el Sur, no
        crear_alerta(cls.n.invernadero, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 5, 15))
        crear_alerta(cls.n.invernadero, "iot_fuera_de_umbral", fecha_hora_alerta=instante_utc(2026, 11, 20, 15))

    def pedir(self, solo_produccion=False):
        """El indicador 7 del período por defecto, con `hoy` = HOY."""
        return consolidadas.por_invernadero(PERIODO, HOY, solo_produccion)

    def dar_de_baja(self, escenario):
        """Pasa el invernadero a «inactivo» (como lo deja la baja lógica)."""
        Invernadero.objects.filter(pk=escenario.invernadero.pk).update(estado_invernadero=Invernadero.Estado.INACTIVO)

    def test_regla_4_7_una_fila_por_invernadero_activo_con_lo_mismo_que_da_est_01(self):
        """D-93 punto 4.7: una fila por invernadero activo, por nombre, con cada indicador igual al de EST-01 para ese invernadero. Norte: 100
        sembradas, 30 cosechadas, merma 10 ÷ 100 = 10,0 %, costo por planta $ 2,00 y 2 alertas del IoT; Sur: sin IoT (`None`)."""
        r = self.pedir()
        self.assertEqual([(f.invernadero_id, f.nombre) for f in r.filas], [(self.n.invernadero.pk, "Invernadero Norte"), (self.s.invernadero.pk, "Invernadero Sur")])
        norte, sur = r.filas
        self.assertEqual(valores(norte), como_est_01([self.n.invernadero.pk]))
        self.assertEqual(valores(sur), como_est_01([self.s.invernadero.pk]))
        self.assertEqual((norte.sembradas, norte.cosechadas, norte.merma, norte.costo_por_planta, norte.alertas_iot), (100, 30, D("10.0"), D("2.00"), 2))
        self.assertIsNone(sur.alertas_iot)
        self.assertIsNone(r.dados_de_baja)

    def test_regla_4_7_el_total_suma_numeradores_y_denominadores_no_promedia_porcentajes(self):
        """D-93 punto 4.7 («la fila del total»): sembradas 140, cosechadas 40, merma 14 ÷ 140 = 10,0 % y costo por planta (30 × 2 + 10 × 3) ÷ 40 = $ 2,25
        (no el promedio de los $ 2,00 y $ 3,00). Coincide con los indicadores de EST-01 sobre los dos invernaderos."""
        r = self.pedir()
        ambos = [self.n.invernadero.pk, self.s.invernadero.pk]
        self.assertEqual(valores(r.total), como_est_01(ambos))
        self.assertEqual((r.total.sembradas, r.total.cosechadas, r.total.merma, r.total.costo_por_planta, r.total.alertas_iot), (140, 40, D("10.0"), D("2.25"), 2))
        self.assertEqual((r.total.invernadero_id, r.total.nombre), (None, "Total"))

    def test_regla_4_7_el_selector_de_ordenes_llega_a_cada_fila_y_al_total(self):
        """D-93 punto 3.3 con 4.7: «Solo de producción» deja afuera la entrega vencida del Norte, en su fila y en el total, igual que en EST-01."""
        orden(self.n.invernadero, T.ENTREGA, date(2026, 11, 15), resolucion=date(2026, 11, 16))
        todas, solo = self.pedir(), self.pedir(solo_produccion=True)
        self.assertNotEqual(todas.filas[0].ordenes_a_tiempo, solo.filas[0].ordenes_a_tiempo)
        self.assertEqual(valores(solo.filas[0]), como_est_01([self.n.invernadero.pk], solo_produccion=True))
        self.assertEqual(valores(solo.total), como_est_01([self.n.invernadero.pk, self.s.invernadero.pk], solo_produccion=True))

    def test_regla_4_7_un_invernadero_dado_de_baja_con_actividad_va_en_su_fila_y_cuenta_en_el_total(self):
        """Diferencia con D-93 punto 4.7 decidida por el estudiante (26/11/2026), por coherencia con EST-01 y para no perder la historia: el Sur
        se da de baja en el período; ya no tiene fila propia, su actividad (40 sembradas, 10 cosechadas, 4 perdidas) va en «Dados de baja» y el
        total sigue siendo el de toda la organización: el mismo que `estadisticas_de_produccion` del Gerente."""
        antes = self.pedir()
        self.dar_de_baja(self.s)
        r = self.pedir()
        self.assertEqual([f.nombre for f in r.filas], ["Invernadero Norte"])
        self.assertEqual((r.dados_de_baja.invernadero_id, r.dados_de_baja.nombre), (None, "Dados de baja"))
        self.assertEqual(valores(r.dados_de_baja), como_est_01([self.s.invernadero.pk]))
        self.assertEqual((r.dados_de_baja.sembradas, r.dados_de_baja.cosechadas), (40, 10))
        self.assertEqual(r.total, antes.total)
        gerente = est_01_del_gerente()
        self.assertEqual(r.total.sembradas, gerente.actual.sembradas_y_cosechadas.sembradas)
        self.assertEqual(r.total.cosechadas, gerente.actual.sembradas_y_cosechadas.cosechadas)
        self.assertEqual(r.total.merma, gerente.actual.merma.porcentaje)
        self.assertEqual(r.total.costo_por_planta, gerente.actual.costo.costo_por_planta)
        self.assertEqual(r.total.consumo, gerente.actual.consumo.monto_total)
        self.assertEqual(r.total.alertas_iot, gerente.actual.alertas_iot.total)

    def test_regla_4_7_un_invernadero_dado_de_baja_sin_actividad_en_el_periodo_no_tiene_fila(self):
        """D-93 punto 4.7 y la decisión del estudiante: sin actividad en el período no hay fila «Dados de baja» (`None`)."""
        self.dar_de_baja(self.s)
        r = consolidadas.por_invernadero(Periodo(date(2026, 9, 1), date(2026, 9, 30)), HOY)
        self.assertIsNone(r.dados_de_baja)

    def test_regla_4_7_los_montos_y_los_porcentajes_son_decimal(self):
        """Convención del proyecto: el dinero y los porcentajes son `Decimal`, nunca `float`."""
        fila = self.pedir().total
        for valor in (fila.merma, fila.ordenes_a_tiempo, fila.costo_por_planta, fila.consumo):
            self.assertIsInstance(valor, Decimal)

    def test_regla_4_7_el_consumo_de_cada_fila_es_el_de_ese_invernadero(self):
        """D-93 punto 3.5 con 4.7: el monto consumido de cada invernadero aparece en su fila y el total es la suma: Norte $ 30,00, Sur $ 12,50."""
        e_n = existencia_de_envase(self.n.invernadero, "Bolsa Norte")
        e_s = existencia_de_envase(self.s.invernadero, "Bolsa Sur")
        entrega_n = orden(self.n.invernadero, T.ENTREGA, date(2026, 11, 14))
        entrega_s = orden(self.s.invernadero, T.ENTREGA, date(2026, 11, 14))
        consumo_de(self.n.invernadero, e_n, "30.00", "3", date(2026, 11, 14), orden_de_entrega=entrega_n)
        consumo_de(self.s.invernadero, e_s, "12.50", "1", date(2026, 11, 14), orden_de_entrega=entrega_s)
        r = self.pedir()
        self.assertEqual((r.filas[0].consumo, r.filas[1].consumo, r.total.consumo), (D("30.00"), D("12.50"), D("42.50")))

    def test_d93_punto_7_consultas_fijas_con_pocos_o_muchos_invernaderos(self):
        """D-93 punto 7: 9 consultas (los invernaderos, siembras con su denominador, cosechas con su costo, mermas, lo que había al inicio, órdenes,
        consumos, el estado del IoT y las alertas), no una por invernadero ni por fila."""
        with self.assertNumQueries(9):
            self.pedir()
        for nombre, sufijo in (("Invernadero Este", "_este"), ("Invernadero Oeste", "_oeste")):
            lote = lote_sembrado(invernadero_con_produccion(nombre, sufijo=sufijo), 20, date(2026, 11, 7))
            merma_de(lote, 1, "plaga", date(2026, 11, 9))
        with self.assertNumQueries(9):
            self.pedir()


# ---------------------------------------------------------------------------------------------------------------------------------
# La merma en cámara, aparte (D-93 punto 4.7, segunda parte)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsCnsMermaEnCamaraServicioTests(PlanDeCuentasMixin, ConCatalogoIot, TestCase):
    """Σ `cant_merma` de partidas en cámara con fecha en el período, por causa, y su valor: el importe de sus asientos (Pérdidas por Mermas contra
    Productos Terminados). Los asientos de la cámara llegan con CON-04c: sin ellos el valor no se puede decir («—», `None`)."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.lote = lote_sembrado(cls.n, 100, date(2026, 10, 10))
        # Cada merma de cámara trae su movimiento `merma_en_camara` con el costo de la partida: $ 2,50 por planta (costo 5 × 2,50 = $ 12,50 y 3 × 2,50 = $ 7,50).
        cls.dano = merma_de_camara(cls.lote, 5, "dano_en_camara", date(2026, 11, 12))
        cls.vencimiento = merma_de_camara(cls.lote, 3, "vencimiento_en_camara", date(2026, 11, 15))
        cls.anterior = merma_de_camara(cls.lote, 2, "dano_en_camara", date(2026, 10, 1))  # fuera del período
        cls.de_lote = merma_de(cls.lote, 7, "plaga", date(2026, 11, 12))  # una merma de lote en pie: no es de cámara

    def asentar(self, merma, importe, ejercicio_del_asiento):
        """El asiento de la merma (Debe Pérdidas por Mermas / Haber Productos Terminados), como lo dejará CON-04c."""
        return asiento_de_prueba(
            ejercicio_del_asiento,
            date(2026, 11, 12),
            [(cuentas.PERDIDAS_POR_MERMAS, DEBE, D(importe)), (cuentas.PRODUCTOS_TERMINADOS, HABER, D(importe))],
            origen=merma,
        )

    def test_regla_4_7_las_plantas_perdidas_en_camara_por_causa_solo_del_periodo(self):
        """D-93 punto 4.7: 5 por daño y 3 por vencimiento en cámara (8 en total, de mayor a menor). No cuenta la del 01/10 ni la de lote en pie."""
        r = consolidadas.merma_en_camara(PERIODO)
        self.assertEqual(
            list(r.causas),
            [FilaDeCausaDeCamara("dano_en_camara", "Daño en cámara", 5), FilaDeCausaDeCamara("vencimiento_en_camara", "Vencimiento en cámara", 3)],
        )
        self.assertEqual(r.plantas, 8)

    def test_regla_4_7_el_valor_es_el_importe_de_sus_asientos(self):
        """D-93 punto 4.7: el valor es lo que sumaron los asientos de esas mermas: $ 12,50 + $ 7,50 = $ 20,00. No suman el asiento de la merma de
        lote en pie ($ 99,00) ni el de la merma de septiembre."""
        ejercicio_del_asiento = ejercicio_abierto(inicio=date(2026, 1, 1))
        self.asentar(self.dano, "12.50", ejercicio_del_asiento)
        self.asentar(self.vencimiento, "7.50", ejercicio_del_asiento)
        self.asentar(self.anterior, "5.00", ejercicio_del_asiento)
        self.asentar(self.de_lote, "99.00", ejercicio_del_asiento)
        r = consolidadas.merma_en_camara(PERIODO)
        self.assertEqual((r.valor, r.sin_asiento), (D("20.00"), False))
        self.assertIsInstance(r.valor, Decimal)

    def test_regla_4_7_sin_los_asientos_de_la_camara_el_valor_no_se_dice(self):
        """Respuesta del estudiante (26/11/2026): si alguna merma de cámara del período no tiene asiento (CON-04c todavía no los crea), el valor
        es `None` («—») y `sin_asiento` es verdadero: un $ 0,00 diría que no se perdió nada."""
        ejercicio_del_asiento = ejercicio_abierto(inicio=date(2026, 1, 1))
        self.asentar(self.dano, "12.50", ejercicio_del_asiento)  # falta el asiento del vencimiento
        r = consolidadas.merma_en_camara(PERIODO)
        self.assertEqual((r.plantas, r.valor, r.sin_asiento), (8, None, True))

    def test_regla_4_7_una_merma_de_camara_sin_costo_no_necesita_asiento(self):
        """H11: un importe de $ 0,00 no genera asiento, así que «—» («falta un asiento que debería existir») no se aplica a una merma de cámara de
        costo cero (partida a $ 0,00 por planta): aporta $ 0,00 y el valor se calcula. Con el asiento de la merma de $ 12,50, el valor es $ 12,50."""
        ejercicio_del_asiento = ejercicio_abierto(inicio=date(2026, 1, 1))
        periodo_corto = Periodo(date(2026, 11, 1), date(2026, 11, 14))
        gratis = merma_de_camara(self.lote, 4, "dano_en_camara", date(2026, 11, 13), costo_unitario="0.0000")
        self.assertIsNotNone(gratis.pk)
        self.asentar(self.dano, "12.50", ejercicio_del_asiento)
        r = consolidadas.merma_en_camara(periodo_corto)
        self.assertEqual((r.plantas, r.valor, r.sin_asiento), (9, D("12.50"), False))

    def test_regla_4_7_solo_costo_cero_sin_asientos_el_valor_es_cero_y_no_hay_guion(self):
        """Caso (a): todas las mermas de cámara del período son de costo cero y no hay asientos: valor $ 0,00 (no «—»), nada pendiente."""
        periodo = Periodo(date(2026, 8, 1), date(2026, 8, 31))
        merma_de_camara(self.lote, 6, "vencimiento_en_camara", date(2026, 8, 10), costo_unitario="0.0000")
        r = consolidadas.merma_en_camara(periodo)
        self.assertEqual((r.plantas, r.valor, r.sin_asiento), (6, D("0.00"), False))

    def test_regla_4_7_con_costo_mayor_que_cero_y_sin_asiento_el_valor_no_se_dice(self):
        """Caso (b): una merma de cámara con costo mayor que cero (3 × $ 2,50) y sin asiento sí fuerza el «—» (`valor` `None`, `sin_asiento`)."""
        periodo = Periodo(date(2026, 8, 1), date(2026, 8, 31))
        merma_de_camara(self.lote, 3, "dano_en_camara", date(2026, 8, 10))
        r = consolidadas.merma_en_camara(periodo)
        self.assertEqual((r.plantas, r.valor, r.sin_asiento), (3, None, True))

    def test_regla_4_7_un_costo_que_redondea_a_cero_centavos_tampoco_necesita_asiento(self):
        """H11 y D-92 punto 5 (el importe se redondea a 2 decimales con ROUND_HALF_UP): 1 planta a $ 0,0040 es $ 0,00 y no tiene asiento; a $ 0,0050
        es $ 0,01 y sí."""
        periodo = Periodo(date(2026, 8, 1), date(2026, 8, 31))
        merma_de_camara(self.lote, 1, "dano_en_camara", date(2026, 8, 10), costo_unitario="0.0040")
        self.assertEqual(consolidadas.merma_en_camara(periodo).sin_asiento, False)
        merma_de_camara(self.lote, 1, "dano_en_camara", date(2026, 8, 11), costo_unitario="0.0050")
        self.assertEqual(consolidadas.merma_en_camara(periodo).sin_asiento, True)

    def test_regla_4_7_sin_mermas_de_camara_en_el_periodo_no_hay_nada_que_valorar(self):
        """Sin mermas de cámara en el período: 0 plantas, valor $ 0,00 y nada pendiente de asentar."""
        r = consolidadas.merma_en_camara(Periodo(date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual((list(r.causas), r.plantas, r.valor, r.sin_asiento), ([], 0, D("0.00"), False))

    def test_d93_punto_7_dos_consultas_con_pocas_o_muchas_mermas(self):
        """D-93 punto 7: 2 consultas (las mermas por causa con las que no tienen asiento, y el importe de los asientos)."""
        with self.assertNumQueries(2):
            consolidadas.merma_en_camara(PERIODO)
        for dia in range(2, 9):
            merma_de_camara(self.lote, 1, "dano_en_camara", date(2026, 11, dia))
        with self.assertNumQueries(2):
            consolidadas.merma_en_camara(PERIODO)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 9 · Compras (D-93 punto 4.9; D-89 punto 4; D-90)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsCnsComprasServicioTests(CorreccionBase):
    """Indicador 9: el valor recibido en el período por proveedor y por categoría de insumo, menos las correcciones del período. Escenario de
    `CorreccionBase` (D-89): A (Semillas del Sur) vende Fertilizante 10 kg a $ 100,00 y Maceta 20 u a $ 200,00; B (Viveros del Este) vende Tomate 8 u a
    $ 80,00. Fertilizante y Maceta son de la categoría «Limpieza» y el Tomate, de «Plantines». Lo que pasa, con sus fechas:

    - R1, 20/10: A entrega 4 kg de Fertilizante ($ 40,00) y los 20 de Maceta ($ 200,00).        (antes del período)
    - C0, 25/10: se corrige 1 kg de la línea de R1 (acumulado 4 → 3): − $ 10,00.                  (antes del período)
    - R2, 10/11: A entrega 6 kg más (acumulado 3 → 9): $ 90,00 − $ 30,00 = $ 60,00.
    - R3, 12/11: B entrega los 8 Tomates: $ 80,00.
    - C1, 22/11: se corrige 2 kg de la línea de R2 (acumulado 9 → 7): − ($ 90,00 − $ 70,00) = − $ 20,00.
    """

    def setUp(self):
        super().setUp()
        Insumo.objects.filter(pk=self.tomate.insumo_id).update(tipo_insumo=tipo_de_insumo("Plantines"))
        self.r1 = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 20)])
        self.c0 = self.corregir(self.ana, self.r1, [(self.detalle_de(self.r1, self.l_fert), 1)])
        self.r2 = self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence)])
        self.r3 = self.recibir_b()
        self.c1 = self.corregir(self.ana, self.r2, [(self.detalle_de(self.r2, self.l_fert), 2)])
        for recepcion, dia in ((self.r1, date(2026, 10, 20)), (self.r2, date(2026, 11, 10)), (self.r3, date(2026, 11, 12))):
            Recepcion.objects.filter(pk=recepcion.pk).update(fecha_recepcion=dia)
        for correccion, dia in ((self.c0, date(2026, 10, 25)), (self.c1, date(2026, 11, 22))):
            CorreccionRecepcion.objects.filter(pk=correccion.pk).update(fecha_correccion=dia)

    def importe_de_asientos(self, periodo):
        """Lo que sumaron los asientos de las recepciones menos los de las correcciones cuyo DOCUMENTO tiene su fecha en el período: la cifra
        contra la que tiene que coincidir el indicador (D-89 punto 4 y D-90 punto 8)."""
        recibidas = Recepcion.objects.filter(fecha_recepcion__range=(periodo.desde, periodo.hasta)).values_list("pk", flat=True)
        corregidas = CorreccionRecepcion.objects.filter(fecha_correccion__range=(periodo.desde, periodo.hasta)).values_list("pk", flat=True)
        proveedores = MovimientoContable.objects.filter(cuenta__codigo_cuenta=cuentas.PROVEEDORES)
        haber = sum((m.importe_movimiento for m in proveedores.filter(tipo_movimiento=HABER, asiento__origen_id__in=list(recibidas))), D("0.00"))
        debe = sum((m.importe_movimiento for m in proveedores.filter(tipo_movimiento=DEBE, asiento__origen_id__in=list(corregidas))), D("0.00"))
        return haber - debe

    def test_regla_4_9_total_por_proveedor_y_por_categoria_del_mes(self):
        """D-93 punto 4.9, noviembre: $ 60,00 + $ 80,00 − $ 20,00 = $ 120,00. Por proveedor: B $ 80,00 y A $ 40,00 (60 − 20); por categoría:
        «Plantines» $ 80,00 y «Limpieza» $ 40,00."""
        r = consolidadas.compras(Periodo(date(2026, 11, 1), date(2026, 11, 26)))
        self.assertEqual(r.total, D("120.00"))
        self.assertEqual(
            [(f.nombre, f.monto) for f in r.por_proveedor], [("Viveros del Este S. R. L.", D("80.00")), ("Semillas del Sur S. A.", D("40.00"))]
        )
        self.assertEqual([(f.nombre, f.monto) for f in r.por_categoria], [("Plantines", D("80.00")), ("Limpieza", D("40.00"))])
        self.assertEqual(r.por_proveedor[0].clave, self.proveedor_b.pk)

    def test_d89_punto_4_y_d90_el_total_coincide_con_los_asientos_de_recepcion_y_correccion(self):
        """«Hecho cuando» de EST-02: lo comprado en el período coincide con los asientos de recepción y de corrección de esas fechas, aunque la línea
        se haya recibido en tres partes y corregido dos veces (D-89 punto 4: el valor sale de la diferencia del acumulado, sin centavos colgados)."""
        for periodo in (
            Periodo(date(2026, 11, 1), date(2026, 11, 26)),
            Periodo(date(2026, 10, 15), date(2026, 11, 26)),
            Periodo(date(2026, 10, 22), date(2026, 11, 26)),
            Periodo(date(2026, 10, 1), date(2026, 10, 31)),
        ):
            with self.subTest(periodo=periodo):
                self.assertEqual(consolidadas.compras(periodo).total, self.importe_de_asientos(periodo))

    def test_d93_punto_4_9_una_correccion_dentro_del_periodo_sobre_una_recepcion_anterior_resta(self):
        """D-93 punto 4.9 (pasada general 7): del 22/10 al 26/11 entra la corrección C0 del 25/10 (− $ 10,00) pero no la recepción R1 del 20/10: total
        − 10 + 60 + 80 − 20 = $ 110,00, y A queda en $ 30,00 (− 10 + 60 − 20)."""
        r = consolidadas.compras(Periodo(date(2026, 10, 22), date(2026, 11, 26)))
        self.assertEqual(r.total, D("110.00"))
        self.assertEqual({f.nombre: f.monto for f in r.por_proveedor}, {"Viveros del Este S. R. L.": D("80.00"), "Semillas del Sur S. A.": D("30.00")})

    def test_d93_punto_4_9_una_correccion_fuera_del_periodo_no_cuenta(self):
        """D-93 punto 4.9: en octubre cuentan R1 ($ 240,00) y C0 (− $ 10,00) pero no lo de noviembre; la corrección C1 del 22/11 queda afuera."""
        r = consolidadas.compras(Periodo(date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(r.total, D("230.00"))
        self.assertEqual([(f.nombre, f.monto) for f in r.por_proveedor], [("Semillas del Sur S. A.", D("230.00"))])

    def test_d93_punto_4_9_el_extremo_del_periodo_esta_incluido(self):
        """EST-CNS-CNS «Decididas» 2: compras por fecha de recepción, con los dos días del extremo incluidos: del 12/11 al 12/11 está R3 ($ 80,00)."""
        self.assertEqual(consolidadas.compras(Periodo(date(2026, 11, 12), date(2026, 11, 12))).total, D("80.00"))

    def test_d93_punto_4_9_por_mes_con_los_meses_del_periodo_aunque_no_tengan_compras(self):
        """Prototipo `stCmp` («Compras por mes»): una barra por mes del período. Del 15/10 al 26/11: octubre $ 230,00 y noviembre $ 120,00; y un mes
        sin compras aparece en cero (del 15/09 al 26/11, septiembre $ 0,00)."""
        r = consolidadas.compras(Periodo(date(2026, 10, 15), date(2026, 11, 26)))
        self.assertEqual(list(r.por_mes), [FilaDeMes(2026, 10, D("230.00")), FilaDeMes(2026, 11, D("120.00"))])
        con_septiembre = consolidadas.compras(Periodo(date(2026, 9, 15), date(2026, 11, 26)))
        self.assertEqual([(f.anio, f.mes, f.monto) for f in con_septiembre.por_mes][0], (2026, 9, D("0.00")))
        self.assertEqual(sum(f.monto for f in con_septiembre.por_mes), con_septiembre.total)

    def test_d93_punto_4_9_sin_recepciones_ni_correcciones_el_total_es_cero(self):
        """Sin recepciones ni correcciones en el período: total $ 0,00 y sin filas."""
        r = consolidadas.compras(Periodo(date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual((r.total, list(r.por_proveedor), list(r.por_categoria)), (D("0.00"), [], []))

    def test_d93_punto_4_9_los_importes_son_decimal_con_dos_decimales(self):
        """D-89 punto 7: todo importe de dinero tiene dos decimales y es `Decimal`."""
        r = consolidadas.compras(Periodo(date(2026, 11, 1), date(2026, 11, 26)))
        for monto in [r.total, *[f.monto for f in r.por_proveedor], *[f.monto for f in r.por_categoria], *[f.monto for f in r.por_mes]]:
            self.assertIsInstance(monto, Decimal)
            self.assertEqual(monto, monto.quantize(D("0.01")))

    def test_d93_punto_7_dos_consultas_con_pocas_o_muchas_recepciones(self):
        """D-93 punto 7: 2 consultas (las líneas recibidas con su proveedor, categoría y lo corregido, y las líneas de las correcciones), no una por
        recepción ni por línea."""
        periodo = Periodo(date(2026, 10, 1), date(2026, 11, 26))
        with self.assertNumQueries(2):
            consolidadas.compras(periodo)
        orden_nueva, proveedor_nuevo = self.otra_pagable(5)
        Recepcion.objects.filter(orden=orden_nueva).update(fecha_recepcion=date(2026, 11, 15))
        with self.assertNumQueries(2):
            r = consolidadas.compras(periodo)
        self.assertEqual(r.total, D("410.00"))  # 230 de octubre + 120 de noviembre + los $ 60,00 de la orden nueva (`otra_pagable`)


# ---------------------------------------------------------------------------------------------------------------------------------
# Indicador 10 · Libro de gestión (D-93 punto 4.10; D-86; D-102)
# ---------------------------------------------------------------------------------------------------------------------------------


class EstCnsCnsLibroServicioTests(PlanDeCuentasMixin, TestCase):
    """Indicador 10: ventas (4.1.01), costos (cada cuenta de resultado negativo) y resultado por FECHA DEL ASIENTO, aunque el período cruce dos
    ejercicios. Ejercicio 1 (cerrado): 01/12/2025 al 30/11/2026. Ejercicio 2 (abierto): desde el 01/12/2026."""

    def setUp(self):
        self.e1 = ejercicio(EjercicioContable.Estado.CERRADO, date(2025, 12, 1))
        self.e2 = ejercicio_abierto(inicio=date(2026, 12, 1))
        # Fuera del período (10/11): no tiene que contar.
        asiento_de_prueba(self.e1, date(2026, 11, 10), [(cuentas.CAJA, DEBE, D("9999.00")), (cuentas.VENTAS, HABER, D("9999.00"))])
        # Dentro, en el ejercicio 1.
        asiento_de_prueba(self.e1, date(2026, 11, 25), [(cuentas.CAJA, DEBE, D("1000.00")), (cuentas.VENTAS, HABER, D("1000.00"))])
        asiento_de_prueba(self.e1, date(2026, 11, 25), [(cuentas.GASTOS_DE_PRODUCCION, DEBE, D("300.00")), (cuentas.CAJA, HABER, D("300.00"))])
        # Dentro, en el ejercicio 2.
        asiento_de_prueba(self.e2, date(2026, 12, 5), [(cuentas.CAJA, DEBE, D("500.00")), (cuentas.VENTAS, HABER, D("500.00"))])
        asiento_de_prueba(self.e2, date(2026, 12, 5), [(cuentas.PERDIDAS_POR_MERMAS, DEBE, D("100.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, D("100.00"))])
        # Una cuenta de resultado negativo con saldo contrario a su naturaleza (D-102 punto 4): − $ 40,00.
        asiento_de_prueba(self.e2, date(2026, 12, 6), [(cuentas.CAJA, DEBE, D("40.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, HABER, D("40.00"))])

    def test_regla_4_10_un_periodo_que_cruza_dos_ejercicios_suma_los_dos(self):
        """D-93 punto 4.10 y «Decididas» 1 (no hay refundición): del 20/11 al 10/12 las ventas son $ 1.000,00 + $ 500,00 = $ 1.500,00; los egresos,
        300 + 100 − 40 = $ 360,00; el resultado, $ 1.140,00. No entra el asiento del 10/11."""
        r = consolidadas.libro(Periodo(date(2026, 11, 20), date(2026, 12, 10)))
        self.assertEqual((r.ventas, r.ingresos, r.egresos, r.resultado), (D("1500.00"), D("1500.00"), D("360.00"), D("1140.00")))

    def test_regla_4_10_los_costos_van_por_cuenta_con_su_signo_y_suman_los_egresos(self):
        """D-93 punto 4.10 («costos: las cuentas de resultado negativo, cada una») y D-102 punto 4: de mayor a menor, y la 5.1.06 con su signo
        contrario (− $ 40,00). La suma de las cuentas es igual a los egresos del libro (`resultado_del_periodo`)."""
        r = consolidadas.libro(Periodo(date(2026, 11, 20), date(2026, 12, 10)))
        self.assertEqual(
            [(f.codigo, f.monto) for f in r.costos_por_cuenta],
            [(cuentas.GASTOS_DE_PRODUCCION, D("300.00")), (cuentas.PERDIDAS_POR_MERMAS, D("100.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, D("-40.00"))],
        )
        self.assertEqual(sum(f.monto for f in r.costos_por_cuenta), r.egresos)
        self.assertEqual(r.costos_por_cuenta[0], FilaDeCuenta(cuentas.GASTOS_DE_PRODUCCION, "Gastos de Producción", D("300.00")))

    def test_regla_4_10_los_ingresos_van_por_cuenta(self):
        """Prototipo `stRtd` («De dónde vienen los ingresos»): una fila por cuenta de resultado positivo con saldo; hoy solo Ventas, $ 1.500,00."""
        r = consolidadas.libro(Periodo(date(2026, 11, 20), date(2026, 12, 10)))
        self.assertEqual([(f.codigo, f.monto) for f in r.ingresos_por_cuenta], [(cuentas.VENTAS, D("1500.00"))])

    def test_regla_4_10_un_periodo_dentro_de_un_solo_ejercicio(self):
        """D-93 punto 4.10: del 20/11 al 30/11 (solo el ejercicio 1): ventas $ 1.000,00, egresos $ 300,00, resultado $ 700,00."""
        r = consolidadas.libro(Periodo(date(2026, 11, 20), date(2026, 11, 30)))
        self.assertEqual((r.ventas, r.egresos, r.resultado), (D("1000.00"), D("300.00"), D("700.00")))

    def test_regla_4_10_sin_movimientos_todo_es_cero_y_sin_filas(self):
        """Sin asientos de resultado en el período: todo en $ 0,00 y sin filas por cuenta."""
        r = consolidadas.libro(Periodo(date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual((r.ventas, r.ingresos, r.egresos, r.resultado), (D("0.00"), D("0.00"), D("0.00"), D("0.00")))
        self.assertEqual((list(r.ingresos_por_cuenta), list(r.costos_por_cuenta)), ([], []))

    def test_regla_4_10_los_importes_son_decimal(self):
        """Convención del proyecto: el dinero es `Decimal`."""
        r = consolidadas.libro(Periodo(date(2026, 11, 20), date(2026, 12, 10)))
        for monto in (r.ventas, r.ingresos, r.egresos, r.resultado, *[f.monto for f in r.costos_por_cuenta]):
            self.assertIsInstance(monto, Decimal)

    def test_d93_punto_7_consultas_fijas_aunque_haya_muchos_asientos(self):
        """D-93 punto 7: las consultas dependen de las cuentas de resultado del plan (fijo, está en el código), no de los asientos: 2 (el nombre de
        las cuentas y `resultado_del_periodo`) más 2 por cuenta (`total_por_cuenta_en_periodo`)."""
        cuentas_de_resultado = CuentaContable.objects.filter(tipo_cuenta__in=(CuentaContable.Tipo.RESULTADO_POSITIVO, CuentaContable.Tipo.RESULTADO_NEGATIVO)).count()
        periodo = Periodo(date(2026, 11, 20), date(2026, 12, 10))
        with self.assertNumQueries(2 + 2 * cuentas_de_resultado):
            consolidadas.libro(periodo)
        for dia in range(1, 9):
            asiento_de_prueba(self.e2, date(2026, 12, dia), [(cuentas.CAJA, DEBE, D("1.00")), (cuentas.VENTAS, HABER, D("1.00"))])
        with self.assertNumQueries(2 + 2 * cuentas_de_resultado):
            consolidadas.libro(periodo)
