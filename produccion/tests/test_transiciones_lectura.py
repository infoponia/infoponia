# Pruebas de la LECTURA de PRD-02 (paso 2): `lotes_trasladables`, las fechas de entrada a la etapa, a Maduración y máxima de cosecha,
# `fecha_minima_de_transicion` y lo que suma `TransicionEtapa` a la bandeja, la lista, el traspaso del Capataz, las asignaciones de
# cuenta y los registrantes de sectores y de variedades. Solo lectura: no escriben ni bloquean. Fuente: docs/casos_de_uso/produccion/
# transicion.md («Reglas de negocio» de PNF-TRN y CNC-TRN), docs/api/produccion.md (secciones 2 y 3), regla 5 de 8.21, reglas 1 a 3 de
# 8.20, D-53 y docs/disparadores.md («Cuando exista TransicionEtapa»).

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_capataz_activo
from produccion.models import Bitacora, Lote, OrdenTrabajo, TransicionEtapa
from produccion.servicios import lotes, ordenes, registrantes, transiciones
from produccion.tests.fabricas import invernadero_con_produccion, lote_con_ciclo, orden_de_siembra, orden_de_transicion

HOY = timezone.localdate()


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


def por_lote(filas, lote):
    """La fila de `lotes_trasladables` de `lote`."""
    return next(f for f in filas if f.lote_id == lote.pk)


class LotesTrasladablesTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def test_regla_lote_trasladable_activo_con_plantas_en_etapa_intermedia_sin_otra_transicion(self):
        """PNF-TRN, «Lote trasladable»: un lote activo, con plantas, que no está en la última etapa y no tiene transición «a
        realizar» se puede elegir; la fila trae lo que pide el paso 2 (etapa actual y siguiente, fechas, cantidad, sectores)."""
        lote = lote_con_ciclo(self.e, cantidad=30, etapa="crecimiento", dias_en_etapa=4)
        fila = por_lote(transiciones.lotes_trasladables(self.e.agronomo), lote)
        self.assertTrue(fila.trasladable)
        self.assertIsNone(fila.motivo)
        self.assertEqual((fila.etapa_codigo, fila.etapa_siguiente_codigo), ("crecimiento", "floracion"))
        self.assertEqual(fila.cantidad_actual, 30)
        self.assertEqual(fila.fecha_de_entrada, HOY - timedelta(days=4))
        self.assertEqual(fila.fecha_estimada_de_fin, HOY + timedelta(days=6))  # 10 días de etapa en la fábrica
        self.assertEqual(fila.sectores, [(self.e.sectores["crecimiento"].pk, "Sector crecimiento", 30)])
        self.assertEqual((fila.codigo, fila.invernadero, fila.perfil_familia), (lote.codigo, "Invernadero Norte", "hoja_verde"))

    def test_regla_lote_en_la_ultima_etapa_no_es_trasladable(self):
        """PNF-TRN, «Lote trasladable»: la última etapa del ciclo es la de mayor `puesto_global`; ahí no hay transición."""
        lote = lote_con_ciclo(self.e, etapa="maduracion")
        fila = por_lote(transiciones.lotes_trasladables(self.e.agronomo), lote)
        self.assertFalse(fila.trasladable)
        self.assertEqual(fila.motivo, "ultima_etapa")
        self.assertIsNone(fila.etapa_siguiente_id)

    def test_regla_etapa_destino_la_siguiente_por_puesto_global_del_ciclo_de_la_variedad(self):
        """Regla 1 de 8.20: la etapa destino es la siguiente del ciclo de la variedad, no del catálogo: con un ciclo sin Floración ni
        Fructificación, desde Crecimiento se va a Maduración."""
        e = invernadero_con_produccion(nombre="Invernadero Corto", sufijo="c", etapas=("germinacion", "crecimiento", "maduracion"))
        lote = lote_con_ciclo(e)
        fila = por_lote(transiciones.lotes_trasladables(e.agronomo), lote)
        self.assertEqual((fila.etapa_siguiente_codigo, fila.etapa_siguiente_dias), ("maduracion", 10))

    def test_ext_3a_lote_con_otra_transicion_a_realizar_no_se_puede_elegir_y_dice_cual(self):
        """Extensión 3a: no permite la selección e informa el identificador y la fecha programada de esa orden."""
        lote = lote_con_ciclo(self.e)
        orden = orden_de_transicion(self.e, lote, dias=3)
        fila = por_lote(transiciones.lotes_trasladables(self.e.agronomo), lote)
        self.assertFalse(fila.trasladable)
        self.assertEqual(fila.motivo, "transicion_a_realizar")
        self.assertEqual(fila.transicion_pendiente, (orden.codigo, HOY + timedelta(days=3)))

    def test_regla_una_transicion_concretada_o_cancelada_no_impide_otra(self):
        """Regla 4 de 8.21: solo cuenta la transición «a realizar»."""
        lote = lote_con_ciclo(self.e)
        orden_de_transicion(self.e, lote, estado="cancelada")
        self.assertTrue(por_lote(transiciones.lotes_trasladables(self.e.agronomo), lote).trasladable)

    def test_ext_3b_invernadero_sin_capataz_activo_no_se_puede_elegir(self):
        """Extensión 3b: sin un Capataz activo que reciba la orden, el lote no se puede elegir y se dice por qué."""
        lote = lote_con_ciclo(self.e)
        self.e.capataz.is_active = False
        self.e.capataz.save(update_fields=["is_active"])
        fila = por_lote(transiciones.lotes_trasladables(self.e.agronomo), lote)
        self.assertEqual((fila.trasladable, fila.motivo), (False, "sin_capataz"))

    def test_regla_solo_invernaderos_activos_y_a_cargo_del_agronomo(self):
        """PNF-TRN, «Lote trasladable»: de un invernadero activo a cargo del Agrónomo. Uno inactivo, uno ajeno o un lote finalizado
        no aparecen; otros roles no ven nada."""
        propio = lote_con_ciclo(self.e)
        ajeno = lote_con_ciclo(invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2"))
        finalizado = lote_con_ciclo(self.e, cantidad=10)
        Lote.objects.filter(pk=finalizado.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        ids = [f.lote_id for f in transiciones.lotes_trasladables(self.e.agronomo)]
        self.assertEqual(ids, [propio.pk])
        self.assertNotIn(ajeno.pk, ids)
        self.assertEqual(transiciones.lotes_trasladables(self.e.capataz), [])
        self.assertEqual(transiciones.lotes_trasladables(None), [])
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(transiciones.lotes_trasladables(self.e.agronomo), [])

    def test_regla_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con los lotes."""
        lote_con_ciclo(self.e, cantidad=5)
        con_uno = consultas(lambda: transiciones.lotes_trasladables(self.e.agronomo))
        for _ in range(3):
            otro = lote_con_ciclo(self.e, cantidad=5, etapa="floracion")
            orden_de_transicion(self.e, otro)
        self.assertEqual(con_uno, consultas(lambda: transiciones.lotes_trasladables(self.e.agronomo)))


class FechasDeLoteTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion(etapas=("germinacion", "crecimiento", "maduracion"))

    def test_regla_8_21_5_la_entrada_a_una_etapa_intermedia_es_la_fecha_efectiva_de_la_transicion_concretada(self):
        """Regla 5 de 8.21: si no es la primera etapa, la `fecha_transicion` de la transición concretada cuyo destino es la etapa
        actual, que puede ser anterior a la creación de la orden."""
        lote = lote_con_ciclo(self.e, etapa="crecimiento", dias_en_etapa=7)
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(lote), HOY - timedelta(days=7))
        self.assertEqual(lotes.fecha_estimada_de_fin_de_etapa(lote), HOY + timedelta(days=3))

    def test_regla_8_21_5_con_dos_transiciones_concretadas_vale_la_de_la_etapa_actual(self):
        """Regla 5 de 8.21: de las transiciones concretadas del lote, la que tuvo la etapa actual como destino."""
        lote = lote_con_ciclo(self.e, etapa="maduracion", dias_en_etapa=2)
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(lote), HOY - timedelta(days=2))

    def test_regla_8_21_5_primera_etapa_sigue_siendo_la_fecha_de_siembra(self):
        """Regla 5 de 8.21: en la primera etapa, la fecha de siembra (sin transiciones)."""
        lote = lote_con_ciclo(self.e, etapa="germinacion")
        self.assertEqual(lotes.fecha_de_entrada_a_la_etapa(lote), HOY)

    def test_regla_8_20_2_y_3_entrada_a_maduracion_y_fecha_maxima_de_cosecha(self):
        """Reglas 2 y 3 de 8.20: la entrada a Maduración es la `fecha_transicion` de la transición con ese destino y la fecha
        máxima de cosecha es esa entrada más la duración de Maduración (10 días en la fábrica)."""
        lote = lote_con_ciclo(self.e, etapa="maduracion", dias_en_etapa=4)
        self.assertEqual(lotes.fecha_de_entrada_a_maduracion(lote), HOY - timedelta(days=4))
        self.assertEqual(lotes.fecha_maxima_de_cosecha(lote), HOY + timedelta(days=6))

    def test_regla_8_20_2_un_lote_que_no_entro_a_maduracion_da_none(self):
        """Reglas 2 y 3 de 8.20: sin transición concretada a Maduración (ni siquiera planificada), `None`."""
        lote = lote_con_ciclo(self.e, etapa="crecimiento")
        orden_de_transicion(self.e, lote)  # «a realizar»: todavía no entró
        self.assertIsNone(lotes.fecha_de_entrada_a_maduracion(lote))
        self.assertIsNone(lotes.fecha_maxima_de_cosecha(lote))

    def test_regla_8_20_2_un_ciclo_sin_maduracion_da_none(self):
        """Un ciclo sin etapa de Maduración nunca entra: `None`, sin error."""
        e = invernadero_con_produccion(nombre="Sin Maduración", sufijo="s", etapas=("germinacion", "crecimiento", "floracion"))
        self.assertIsNone(lotes.fecha_maxima_de_cosecha(lote_con_ciclo(e, etapa="floracion")))

    def test_d50_lotes_activos_trae_la_entrada_y_el_fin_de_las_etapas_posteriores_a_la_primera(self):
        """`lotes_activos_de` ya no da `None` fuera de la primera etapa (disparador «Cuando exista TransicionEtapa», punto 1)."""
        lote = lote_con_ciclo(self.e, etapa="crecimiento", dias_en_etapa=7)
        fila = next(f for f in lotes.lotes_activos_de([self.e.invernadero.pk]) if f.lote_id == lote.pk)
        self.assertEqual(fila.fecha_de_entrada, HOY - timedelta(days=7))
        self.assertEqual(fila.fecha_estimada_de_fin, HOY + timedelta(days=3))

    def test_d50_lotes_activos_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con los lotes (la fecha de entrada sale de una sola consulta de transiciones)."""
        lote_con_ciclo(self.e, cantidad=5)
        con_uno = consultas(lambda: lotes.lotes_activos_de([self.e.invernadero.pk]))
        for _ in range(3):
            lote_con_ciclo(self.e, cantidad=5, etapa="maduracion")
        self.assertEqual(con_uno, consultas(lambda: lotes.lotes_activos_de([self.e.invernadero.pk])))


class FechaMinimaTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def bitacora(self, lote, fecha, etapa=None):
        return Bitacora.objects.create(
            invernadero=lote.invernadero, lote=lote, etapa=etapa or lote.etapa, tipo_evento="merma", fecha_bitacora=fecha,
            hora_bitacora=timezone.localtime().time(),
        )

    def test_regla_fecha_minima_sin_bitacora_es_la_entrada_a_la_etapa(self):
        """CNC-TRN, «Fecha mínima»: sin registros de bitácora del lote en la etapa, la fecha de entrada."""
        lote = lote_con_ciclo(self.e, dias_en_etapa=5)
        self.assertEqual(transiciones.fecha_minima_de_transicion(lote), HOY - timedelta(days=5))

    def test_regla_fecha_minima_con_bitacora_posterior_es_la_del_ultimo_registro(self):
        """CNC-TRN, «Fecha mínima»: la mayor entre la entrada y el último registro de bitácora del lote en esa etapa."""
        lote = lote_con_ciclo(self.e, dias_en_etapa=5)
        self.bitacora(lote, HOY - timedelta(days=3))
        self.bitacora(lote, HOY - timedelta(days=1))
        self.bitacora(lote, HOY - timedelta(days=2))
        self.assertEqual(transiciones.fecha_minima_de_transicion(lote), HOY - timedelta(days=1))

    def test_regla_fecha_minima_ignora_la_bitacora_de_otra_etapa_o_anterior_a_la_entrada(self):
        """Solo cuentan los registros asociados a la etapa actual; uno de la etapa anterior no mueve la fecha mínima, y la entrada
        gana si es posterior al registro."""
        lote = lote_con_ciclo(self.e, dias_en_etapa=2)
        anterior = lote.transiciones.get(etapa_destino=lote.etapa).etapa_destino.ciclo.etapas.get(tipo_etapa__codigo="germinacion")
        self.bitacora(lote, HOY - timedelta(days=1), etapa=anterior)
        self.assertEqual(transiciones.fecha_minima_de_transicion(lote), HOY - timedelta(days=2))
        self.bitacora(lote, HOY - timedelta(days=9))
        self.assertEqual(transiciones.fecha_minima_de_transicion(lote), HOY - timedelta(days=2))


class TransicionEnLasListasTests(ConDatosDeInventario, TestCase):
    """D-53 y disparador «Cuando exista TransicionEtapa», punto 2: la transición está en la bandeja, la lista, el traspaso y las
    asignaciones de cuenta."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def test_d53_ordenes_del_capataz_suma_las_transiciones_con_su_resumen(self):
        """D-53: `ordenes_del_capataz` recorre `Siembra` y `TransicionEtapa`; el resumen nombra el lote y la etapa destino."""
        lote = lote_con_ciclo(self.e)
        siembra = orden_de_siembra(self.e, plantines=5, dias=2)
        transicion = orden_de_transicion(self.e, lote, dias=1)
        filas = ordenes.ordenes_del_capataz(self.e.capataz, estado="a_realizar")
        self.assertEqual([f.orden_id for f in filas], [transicion.pk, siembra.pk])  # por fecha programada
        fila = filas[0]
        self.assertEqual((fila.tipo_orden, fila.tipo_texto, fila.capataz_id), ("transicion", "Transición de etapa", self.e.capataz.pk))
        self.assertIn(lote.codigo, fila.resumen)
        self.assertIn("Floración", fila.resumen)

    def test_d53_la_bandeja_y_la_lista_incluyen_las_transiciones(self):
        """La bandeja del Capataz y la lista del Agrónomo muestran la transición «a realizar»."""
        lote = lote_con_ciclo(self.e)
        transicion = orden_de_transicion(self.e, lote)
        bandeja = ordenes.bandeja_del_capataz(self.e.capataz)
        self.assertEqual([f.orden_id for f in bandeja.hoy], [transicion.pk])
        lista = ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes())
        self.assertIn(transicion.pk, [f.orden_id for f in lista])
        self.assertIn(transicion.pk, [f.orden_id for g in ordenes.ordenes_cancelables(self.e.agronomo) for f in g.ordenes])

    def test_d53_ordenes_del_capataz_no_hace_consultas_por_fila_con_transiciones(self):
        """D-53: la cantidad de consultas no crece con las transiciones."""
        lote = lote_con_ciclo(self.e)
        orden_de_transicion(self.e, lote)
        con_una = consultas(lambda: ordenes.ordenes_del_capataz(self.e.capataz))
        for _ in range(3):
            orden_de_transicion(self.e, lote)
        self.assertEqual(con_una, consultas(lambda: ordenes.ordenes_del_capataz(self.e.capataz)))
        self.assertEqual(consultas(lambda: ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes())),
                         consultas(lambda: ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes())))

    def test_d53_el_traspaso_pasa_tambien_las_transiciones_a_realizar(self):
        """Regla 3 de 8.22 y D-53: `traspasar` actualiza `capataz` en cada tabla hija, también `TransicionEtapa`, solo las «a
        realizar», y devuelve lo que tocó; `contar` las cuenta."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        lote = lote_con_ciclo(self.e)
        pendiente = orden_de_transicion(self.e, lote)
        cancelada = orden_de_transicion(self.e, lote, estado="cancelada")
        self.assertEqual(registrantes.contar_traspaso(self.e.invernadero, "capataz", self.e.capataz, nuevo), [("órdenes de trabajo a realizar", 1)])
        tocadas = registrantes.traspasar_ordenes(self.e.agronomo, self.e.invernadero, "capataz", self.e.capataz, nuevo)
        self.assertEqual([t.pk for t in tocadas], [pendiente.pk])
        self.assertEqual(TransicionEtapa.objects.get(pk=pendiente.pk).capataz, nuevo)
        self.assertEqual(TransicionEtapa.objects.get(pk=cancelada.pk).capataz, self.e.capataz)

    def test_d53_las_asignaciones_de_cuenta_cuentan_las_transiciones(self):
        """Regla 4 de USR-BAJ-USR: las órdenes «a realizar» del Capataz incluyen las transiciones."""
        lote = lote_con_ciclo(self.e)
        orden_de_transicion(self.e, lote)
        orden_de_siembra(self.e, plantines=1)
        asignaciones = registrantes.asignaciones_de_cuenta(self.e.capataz)
        self.assertEqual([(a.texto, a.cantidad) for a in asignaciones], [("Órdenes de trabajo a realizar", 2)])

    def test_d50_el_detalle_de_una_transicion_trae_su_hija_y_sus_ocupaciones(self):
        """`detalle_de_orden` encuentra la hija `TransicionEtapa` (con lote y etapa destino) y sus ocupaciones; el Capataz asignado
        la ve."""
        lote = lote_con_ciclo(self.e)
        transicion = orden_de_transicion(self.e, lote)
        detalle = ordenes.detalle_de_orden(self.e.capataz, transicion.pk)
        self.assertIsInstance(detalle.hija, TransicionEtapa)
        self.assertEqual([o.sector_id for o in detalle.ocupaciones], [self.e.sectores["floracion"].pk])
        self.assertTrue(ordenes.detalle_de_orden(self.e.agronomo, transicion.pk).puede_cancelar)


class TransicionEnLosRegistrantesTests(ConDatosDeInventario, TestCase):
    """Lo que informa `produccion` a `maestros` e `inventario` ahora que hay transiciones (disparador, punto 2)."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def test_ext_las_transiciones_a_realizar_comprometen_agujeros_y_cuentan_en_el_contenido_del_sector(self):
        """D-50 punto 4: los agujeros comprometidos del sector destino son los planificados por la transición «a realizar»; el
        contenido del sector la nombra con su orden."""
        lote = lote_con_ciclo(self.e, cantidad=30)
        transicion = orden_de_transicion(self.e, lote)
        sector = self.e.sectores["floracion"]
        self.assertEqual(registrantes.agujeros_de_sector([sector.pk]), {sector.pk: (0, 30)})
        contenido = registrantes.contenido_de_sectores([sector])[sector.pk]
        self.assertEqual([c.texto for c in contenido], [f"{transicion.codigo} · Transición de etapa"])
        self.assertEqual([i.codigo for i in registrantes.impedimentos_de_baja_de_sector(sector)], ["agujeros_comprometidos"])

    def test_ext_el_perfil_del_sector_destino_es_el_de_la_variedad_del_lote_con_transicion_a_realizar(self):
        """PNF-TRN, «Compatibilidad por perfil familiar»: un sector con una transición «a realizar» hacia él tiene el perfil de la
        variedad de ese lote; una vez cancelada, vuelve a estar libre."""
        lote = lote_con_ciclo(self.e)
        transicion = orden_de_transicion(self.e, lote)
        sector = self.e.sectores["floracion"]
        self.assertEqual(lotes.perfil_de_sector([sector.pk]), {sector.pk: "hoja_verde"})
        OrdenTrabajo.objects.filter(pk=transicion.pk).update(
            estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x"
        )
        self.assertEqual(lotes.perfil_de_sector([sector.pk]), {sector.pk: None})

    def test_ext_aviso_de_cambio_de_tipo_incluye_las_transiciones_a_realizar_hacia_ese_tipo(self):
        """Regla 4 de PROD-MOD-SCT: una transición «a realizar» cuyo destino es de ese tipo de etapa se avisa."""
        lote = lote_con_ciclo(self.e)
        transicion = orden_de_transicion(self.e, lote)
        tipo = self.e.sectores["floracion"].tipo_etapa
        textos = [a.texto for a in registrantes.avisos_de_cambio_de_tipo(self.e.invernadero, tipo)]
        self.assertTrue(any(transicion.codigo in t and "transición a realizar" in t for t in textos), textos)

    def test_ext_uso_de_variedad_cuenta_las_transiciones_a_realizar_de_sus_lotes(self):
        """Disparador «Cuando exista PRD-01» (variedades): las órdenes «a realizar» de una variedad incluyen las transiciones de sus
        lotes; sin ellas, el resultado neutro."""
        lote = lote_con_ciclo(self.e)
        variedad = self.e.variedad
        self.assertEqual(registrantes.uso_de_variedad([variedad.pk])[variedad.pk].ordenes_a_realizar, 0)
        orden_de_transicion(self.e, lote)
        orden_de_siembra(self.e, plantines=1)
        uso = registrantes.uso_de_variedad([variedad.pk])[variedad.pk]
        self.assertEqual((uso.ordenes_a_realizar, uso.lotes_activos), (2, 1))
        self.assertEqual(registrantes.uso_de_variedad([]), {})

    def test_ext_el_traspaso_y_el_uso_no_hacen_consultas_por_fila(self):
        """Las dos consultas de transiciones son una por tabla: la cantidad no crece con las órdenes."""
        lote = lote_con_ciclo(self.e)
        orden_de_transicion(self.e, lote)
        con_una = consultas(lambda: registrantes.uso_de_variedad([self.e.variedad.pk]))
        for _ in range(3):
            orden_de_transicion(self.e, lote)
        self.assertEqual(con_una, consultas(lambda: registrantes.uso_de_variedad([self.e.variedad.pk])))
