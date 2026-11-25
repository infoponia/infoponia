# Pruebas de `produccion/servicios/lotes.py` (PRD-01, paso 3): lectura de lotes, fechas de entrada y de fin de etapa, sectores de
# origen y perfil de un sector. Solo lectura: no escribe ni bloquea. Fuente: docs/api/produccion.md (sección 2), docs/modelo/produccion.md
# («Lo que se calcula de un lote», regla 5 de 8.21; «Lo que se calcula de las ocupaciones») y D-50.
# `produccion.servicios.lotes` se toma del módulo dentro de cada prueba: mientras no exista, falla cada prueba por separado.

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from produccion.models import Lote, OcupacionSector
from produccion.tests.fabricas import (
    invernadero_con_produccion, lote_activo, lote_con_ciclo, lote_de_carga_inicial, orden_de_siembra, orden_de_transicion,
)

lotes = perezoso("produccion.servicios.lotes")


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class LotesLecturaTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def test_regla_8_21_5_en_la_primera_etapa_la_entrada_es_la_fecha_de_siembra(self):
        """Regla 5 de 8.21: en la primera etapa del ciclo, la fecha de entrada es `siembra.fecha_siembra`."""
        lote = lote_activo(self.e)
        lote.siembra.fecha_siembra = timezone.localdate() - timedelta(days=3)
        lote.siembra.save(update_fields=["fecha_siembra"])
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(Lote.objects.get(pk=lote.pk)), timezone.localdate() - timedelta(days=3))

    def test_d50_la_fecha_estimada_de_fin_es_la_entrada_mas_la_duracion_de_la_etapa(self):
        """«Lo que se calcula de un lote»: fecha estimada de fin de la etapa actual = entrada + `duracion_dias` (10 en la fábrica)."""
        lote = lote_activo(self.e)
        self.assertEqual(lotes.fecha_estimada_de_fin_de_etapa(lote), timezone.localdate() + timedelta(days=10))

    def test_regla_8_20_un_lote_en_germinacion_no_entro_a_maduracion(self):
        """Reglas 2 y 3 de 8.20: la fecha de entrada a Maduración y la máxima de cosecha son `None` si el lote no entró (en PRD-01
        ningún lote sale de Germinación: las transiciones llegan con PRD-02)."""
        lote = lote_activo(self.e)
        self.assertIsNone(lotes.fecha_de_entrada_a_maduracion(lote))
        self.assertIsNone(lotes.fecha_maxima_de_cosecha(lote))

    def test_d50_sectores_de_origen_son_las_ocupaciones_con_agujeros_ocupados(self):
        """`sectores_de_origen`: ocupaciones con `cant_agujeros_ocupados > 0` y su sector; una ocupación en 0 no cuenta."""
        lote = lote_activo(self.e, cantidad=30, sector="germinacion")
        vacia = OcupacionSector.objects.create(
            orden=lote.siembra, sector=self.e.sectores["crecimiento"], cant_agujeros_planificados=5, lote=lote, cant_agujeros_ocupados=0
        )
        origen = lotes.sectores_de_origen(lote)
        self.assertEqual([o.sector_id for o in origen], [self.e.sectores["germinacion"].pk])
        self.assertNotIn(vacia.pk, [o.pk for o in origen])

    def test_regla_perfil_del_sector_viene_de_lotes_y_ordenes_a_realizar(self):
        """Ficha «OcupacionSector» (perfil familiar de un sector): el de la variedad de los lotes con ocupaciones vigentes y de las
        órdenes «a realizar» que lo usan; `None` si no tiene ninguno. Una orden cancelada no cuenta."""
        germinacion, crecimiento, floracion = (self.e.sectores[c] for c in ("germinacion", "crecimiento", "floracion"))
        lote_activo(self.e, cantidad=10, sector="germinacion")
        orden_de_siembra(self.e, plantines=5, sector="crecimiento")
        orden_de_siembra(self.e, plantines=5, sector="floracion", estado="cancelada")
        perfiles = lotes.perfil_de_sector([germinacion.pk, crecimiento.pk, floracion.pk, self.e.sectores["maduracion"].pk])
        self.assertEqual(perfiles[germinacion.pk], "hoja_verde")
        self.assertEqual(perfiles[crecimiento.pk], "hoja_verde")
        self.assertIsNone(perfiles[floracion.pk])
        self.assertIsNone(perfiles[self.e.sectores["maduracion"].pk])

    def test_regla_lotes_activos_de_devuelve_solo_los_activos_con_sus_datos(self):
        """`lotes_activos_de`: lotes activos de los invernaderos pedidos con variedad, etapa, cantidad, costo por planta, fecha de
        entrada y fecha estimada de fin. Un lote finalizado no aparece."""
        activo = lote_activo(self.e, cantidad=40, costo="100.00")
        terminado = lote_activo(self.e, cantidad=5, costo="0.00")
        Lote.objects.filter(pk=terminado.pk).update(cantidad_actual=0, estado_lote="finalizado")
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        lote_de_otro = lote_activo(otro)
        filas = lotes.lotes_activos_de([self.e.invernadero.pk])
        self.assertEqual([f.lote_id for f in filas], [activo.pk])
        fila = filas[0]
        self.assertEqual(fila.codigo, activo.codigo)
        self.assertEqual(fila.cantidad_actual, 40)
        self.assertEqual(str(fila.costo_por_planta), "2.50")
        self.assertEqual(fila.variedad_nombre, str(self.e.variedad))
        self.assertEqual(fila.etapa_codigo, "germinacion")
        self.assertEqual(fila.fecha_de_entrada, timezone.localdate())
        self.assertEqual(fila.fecha_estimada_de_fin, timezone.localdate() + timedelta(days=10))
        self.assertEqual([f.lote_id for f in lotes.lotes_activos_de([otro.invernadero.pk])], [lote_de_otro.pk])
        self.assertEqual(lotes.lotes_activos_de([]), [])

    def test_d50_lotes_activos_de_no_hace_consultas_por_fila(self):
        """«Los datos de más de un lote se piden con listas de ids y una consulta por tabla»: la cantidad de consultas no crece con los lotes."""
        lote_activo(self.e)
        con_uno = consultas(lambda: lotes.lotes_activos_de([self.e.invernadero.pk]))
        for _ in range(4):
            lote_activo(self.e)
        con_cinco = consultas(lambda: lotes.lotes_activos_de([self.e.invernadero.pk]))
        self.assertEqual(con_uno, con_cinco)


class LotesDeCargaInicialLecturaTests(ConDatosDeInventario, TestCase):
    """PRD-05, lectura (D-92 punto 12; L3 de «Registrar Lote Existente»): sin transición concretada hacia la etapa actual, la entrada a la etapa
    es la `fecha_bitacora` de la entrada `carga_inicial` del lote, también en la primera etapa (interpretación del estudiante, 25/11/2026)."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.hoy = timezone.localdate()

    def test_post_b_la_entrada_a_la_etapa_actual_es_la_de_la_carga_inicial(self):
        """Un lote cargado en Crecimiento: la entrada es el ingreso cargado, no la fecha de siembra."""
        lote = lote_de_carga_inicial(self.e, etapa="crecimiento", ingreso=self.hoy - timedelta(days=4), siembra=self.hoy - timedelta(days=40))
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(Lote.objects.get(pk=lote.pk)), self.hoy - timedelta(days=4))

    def test_regla_l3_en_la_primera_etapa_manda_el_ingreso_cargado_y_no_la_siembra(self):
        """Lote de carga inicial en Germinación con ingreso distinto de la fecha de siembra: usa el ingreso."""
        lote = lote_de_carga_inicial(self.e, etapa="germinacion", ingreso=self.hoy - timedelta(days=5), siembra=self.hoy - timedelta(days=9))
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(Lote.objects.get(pk=lote.pk)), self.hoy - timedelta(days=5))

    def test_regla_8_21_5_un_lote_normal_en_germinacion_sigue_usando_la_fecha_de_siembra(self):
        """Sin regresión: un lote normal en Germinación toma `siembra.fecha_siembra`."""
        lote = lote_activo(self.e)
        Siembra = lote.siembra.__class__
        Siembra.objects.filter(pk=lote.siembra_id).update(fecha_siembra=self.hoy - timedelta(days=7))
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(Lote.objects.get(pk=lote.pk)), self.hoy - timedelta(days=7))

    def test_post_b_la_entrada_a_maduracion_y_la_fecha_maxima_de_cosecha_salen_de_la_carga_inicial(self):
        """Lote cargado en Maduración: entrada a Maduración = ingreso cargado; fecha máxima = ingreso + `duracion_dias` de Maduración (10)."""
        lote = lote_de_carga_inicial(self.e, etapa="maduracion", ingreso=self.hoy - timedelta(days=3))
        lote = Lote.objects.get(pk=lote.pk)
        self.assertEqual(lotes.fecha_de_entrada_a_maduracion(lote), self.hoy - timedelta(days=3))
        self.assertEqual(lotes.fecha_maxima_de_cosecha(lote), self.hoy - timedelta(days=3) + timedelta(days=10))

    def test_regla_l3_un_lote_cargado_en_otra_etapa_no_entro_a_maduracion(self):
        """Un lote cargado en Crecimiento no tiene fecha de entrada a Maduración."""
        lote = lote_de_carga_inicial(self.e, etapa="crecimiento")
        self.assertIsNone(lotes.fecha_de_entrada_a_maduracion(Lote.objects.get(pk=lote.pk)))

    def test_regla_l3_una_transicion_concretada_hacia_la_etapa_actual_manda_sobre_la_carga_inicial(self):
        """Si el lote ya transicionó hacia la etapa actual, la entrada es la `fecha_transicion` (la carga inicial es de otra etapa)."""
        lote = lote_de_carga_inicial(self.e, etapa="germinacion", ingreso=self.hoy - timedelta(days=30), siembra=self.hoy - timedelta(days=30))
        orden_de_transicion(self.e, lote, estado="concretada", fecha_efectiva=self.hoy - timedelta(days=2), dias=0)
        lote = Lote.objects.get(pk=lote.pk)
        self.assertNotEqual(lote.etapa.tipo_etapa.codigo, "germinacion")
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(lote), self.hoy - timedelta(days=2))

    def test_d50_lotes_activos_de_incluye_la_entrada_de_la_carga_inicial_sin_consultas_por_fila(self):
        """`lotes_activos_de` muestra la entrada cargada y hace las mismas consultas con 1 o con 3 lotes."""
        lote_de_carga_inicial(self.e, etapa="maduracion", ingreso=self.hoy - timedelta(days=6))
        una = consultas(lambda: lotes.lotes_activos_de([self.e.invernadero.pk]))
        lote_de_carga_inicial(self.e, etapa="crecimiento", ingreso=self.hoy - timedelta(days=2))
        lote_de_carga_inicial(self.e, etapa="floracion", ingreso=self.hoy - timedelta(days=1))
        self.assertEqual(consultas(lambda: lotes.lotes_activos_de([self.e.invernadero.pk])), una)
        filas = {f.etapa_codigo: f for f in lotes.lotes_activos_de([self.e.invernadero.pk])}
        self.assertEqual(filas["maduracion"].fecha_de_entrada, self.hoy - timedelta(days=6))
