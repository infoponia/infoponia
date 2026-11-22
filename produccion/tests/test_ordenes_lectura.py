# Pruebas de lectura de órdenes de `produccion/servicios/ordenes.py` (PRD-01, paso 3): `ordenes_del_capataz` (la única unión de las
# órdenes de un Capataz, D-53), la bandeja, la lista del Agrónomo y las cancelables. Solo lectura. Fuente: docs/api/produccion.md
# (secciones 2 y 9), D-53, D-67 punto 1 («Tipos de orden futuros»: filtros con `tipo_orden__in=TIPOS_DE_PRODUCCION`, nunca «todo
# menos X») y docs/modelo/produccion.md (orden de ordenación de órdenes).
#
# Estas pruebas usan órdenes sueltas (`orden_suelta`) de tipo entrega y mantenimiento (y una transición suelta solo para leer): las
# hijas de esos tipos no existen todavía. Cuando existan, las pruebas siguen valiendo sin cambios.

from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo
from produccion.models import OrdenTrabajo
from produccion.servicios import ordenes
from produccion.tests.fabricas import invernadero_con_produccion, orden_de_siembra, orden_suelta

Tipo = OrdenTrabajo.Tipo


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


def ids(filas):
    """Los ids de orden de una lista de filas, en el orden en que vienen."""
    return [fila.orden_id for fila in filas]


class OrdenesDelCapatazTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.otro_capataz = crear_capataz_activo(email="otro.capataz@infoponia.com")

    def test_d53_ordenes_del_capataz_devuelve_solo_las_suyas(self):
        """D-53: `ordenes_del_capataz` recorre las hijas con Capataz y devuelve solo las del Capataz pedido."""
        mia = orden_de_siembra(self.e, plantines=10)
        de_otro = orden_de_siembra(self.e, plantines=10, sector="crecimiento", capataz=self.otro_capataz)
        self.assertEqual(ids(ordenes.ordenes_del_capataz(self.e.capataz)), [mia.pk])
        self.assertEqual(ids(ordenes.ordenes_del_capataz(self.otro_capataz)), [de_otro.pk])

    def test_d53_ordenes_del_capataz_filtra_por_estado(self):
        """`estado=` filtra; sin estado devuelve todas (el traspaso y el aviso de baja usan «a realizar»)."""
        pendiente = orden_de_siembra(self.e, plantines=10)
        cancelada = orden_de_siembra(self.e, plantines=10, sector="crecimiento", estado="cancelada")
        self.assertEqual(ids(ordenes.ordenes_del_capataz(self.e.capataz, estado="a_realizar")), [pendiente.pk])
        self.assertCountEqual(ids(ordenes.ordenes_del_capataz(self.e.capataz)), [pendiente.pk, cancelada.pk])

    def test_d53_la_fila_trae_lo_que_necesitan_la_bandeja_y_el_traspaso(self):
        """La fila ya trae código, tipo (con su texto), estado, fecha, prioridad, invernadero y un resumen: nada de consultas por fila."""
        siembra = orden_de_siembra(self.e, plantines=12, prioridad="alta")
        fila = ordenes.ordenes_del_capataz(self.e.capataz)[0]
        self.assertEqual(fila.orden_id, siembra.pk)
        self.assertEqual(fila.codigo, siembra.codigo)
        self.assertEqual(fila.tipo_orden, Tipo.SIEMBRA)
        self.assertEqual(fila.tipo_texto, "Siembra")
        self.assertEqual(fila.estado_orden, "a_realizar")
        self.assertEqual(fila.prioridad_orden, "alta")
        self.assertEqual(fila.invernadero_id, self.e.invernadero.pk)
        self.assertEqual(fila.invernadero, self.e.invernadero.nombre_invernadero)
        self.assertIn(str(self.e.variedad), fila.resumen)
        self.assertIn("12", fila.resumen)

    def test_d53_ordenes_del_capataz_no_hace_consultas_por_fila(self):
        """D-53: una consulta por tabla hija; la cantidad de consultas no crece con las órdenes."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: ordenes.ordenes_del_capataz(self.e.capataz))
        for i in range(4):
            orden_de_siembra(self.e, plantines=1, sector="crecimiento" if i % 2 else "floracion")
        con_cinco = consultas(lambda: ordenes.ordenes_del_capataz(self.e.capataz))
        self.assertEqual(con_una, con_cinco)


class BandejaTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def test_bandeja_agrupa_en_vencidas_hoy_y_proximas(self):
        """Pantalla «Bandeja»: grupos «vencidas / hoy / próximas» según la fecha programada (docs/casos_de_uso/produccion/siembra.md)."""
        vencida = orden_de_siembra(self.e, plantines=1, dias=-2)
        hoy = orden_de_siembra(self.e, plantines=1, dias=0, sector="crecimiento")
        proxima = orden_de_siembra(self.e, plantines=1, dias=3, sector="floracion")
        bandeja = ordenes.bandeja_del_capataz(self.e.capataz)
        self.assertEqual(ids(bandeja.vencidas), [vencida.pk])
        self.assertEqual(ids(bandeja.hoy), [hoy.pk])
        self.assertEqual(ids(bandeja.proximas), [proxima.pk])

    def test_bandeja_ordena_por_fecha_despues_prioridad_sin_valor_es_media_despues_id(self):
        """docs/modelo/produccion.md: fecha programada (la más antigua primero), después prioridad (alta, media, baja; sin
        prioridad cuenta como media), después `id`."""
        baja = orden_de_siembra(self.e, plantines=1, prioridad="baja")
        sin = orden_de_siembra(self.e, plantines=1, sector="crecimiento")
        alta = orden_de_siembra(self.e, plantines=1, sector="floracion", prioridad="alta")
        media = orden_de_siembra(self.e, plantines=1, sector="fructificacion", prioridad="media")
        antes = orden_de_siembra(self.e, plantines=1, sector="maduracion", dias=-1, prioridad="baja")
        bandeja = ordenes.bandeja_del_capataz(self.e.capataz)
        self.assertEqual(ids(bandeja.vencidas), [antes.pk])
        self.assertEqual(ids(bandeja.hoy), [alta.pk, sin.pk, media.pk, baja.pk])

    def test_bandeja_solo_a_realizar_de_invernaderos_activos(self):
        """La bandeja muestra las órdenes «a realizar»; una concretada o cancelada no. Un invernadero inactivo se excluye."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        orden_de_siembra(self.e, plantines=1, sector="crecimiento", estado="cancelada")
        orden_de_siembra(self.e, plantines=1, sector="floracion", estado="concretada")
        self.assertEqual(ids(ordenes.bandeja_del_capataz(self.e.capataz).hoy), [pendiente.pk])
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        bandeja = ordenes.bandeja_del_capataz(self.e.capataz)
        self.assertEqual(bandeja.vencidas + bandeja.hoy + bandeja.proximas, [])

    def test_bandeja_no_hace_consultas_por_fila(self):
        """La cantidad de consultas de la bandeja no crece con las órdenes."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: ordenes.bandeja_del_capataz(self.e.capataz))
        for i, sector in enumerate(("crecimiento", "floracion", "fructificacion", "maduracion")):
            orden_de_siembra(self.e, plantines=1, sector=sector, dias=i - 1)
        self.assertEqual(con_una, consultas(lambda: ordenes.bandeja_del_capataz(self.e.capataz)))


class ListaDeOrdenesTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.gerente = crear_gerente()

    def test_alcance_agronomo_a_cargo_y_gerente_en_solo_lectura(self):
        """Regla 2 de 8.22: el Agrónomo opera las órdenes de sus invernaderos; el Gerente las ve (solo lectura); otro Agrónomo, un
        Capataz o una cuenta inactiva, ninguna."""
        siembra = orden_de_siembra(self.e, plantines=1)
        filtros = ordenes.FiltrosDeOrdenes()
        self.assertEqual(ids(ordenes.lista_de_ordenes(self.e.agronomo, filtros)), [siembra.pk])
        self.assertEqual(ids(ordenes.lista_de_ordenes(self.gerente, filtros)), [siembra.pk])
        self.assertEqual(ordenes.lista_de_ordenes(crear_agronomo(email="ajeno@infoponia.com"), filtros), [])
        self.assertEqual(ordenes.lista_de_ordenes(crear_capataz(email="capataz.ajeno@infoponia.com"), filtros), [])
        self.assertEqual(ordenes.lista_de_ordenes(None, filtros), [])

    def test_filtros_por_invernadero_y_estado(self):
        """La lista filtra por invernadero y por estado; las «a realizar» van primero."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        cancelada = orden_de_siembra(self.e, plantines=1, sector="crecimiento", estado="cancelada")
        todas = ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes())
        self.assertEqual(ids(todas), [pendiente.pk, cancelada.pk])
        solo_canceladas = ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes(estado="cancelada"))
        self.assertEqual(ids(solo_canceladas), [cancelada.pk])
        otro_invernadero = ordenes.FiltrosDeOrdenes(invernadero_id=self.e.invernadero.pk + 999)
        self.assertEqual(ordenes.lista_de_ordenes(self.e.agronomo, otro_invernadero), [])

    def test_lista_no_hace_consultas_por_fila(self):
        """La cantidad de consultas de la lista no crece con las órdenes."""
        orden_de_siembra(self.e, plantines=1)
        filtros = ordenes.FiltrosDeOrdenes()
        con_una = consultas(lambda: ordenes.lista_de_ordenes(self.e.agronomo, filtros))
        for sector in ("crecimiento", "floracion", "fructificacion", "maduracion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        self.assertEqual(con_una, consultas(lambda: ordenes.lista_de_ordenes(self.e.agronomo, filtros)))


class CancelablesTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def test_cancelables_son_las_a_realizar_de_sus_invernaderos_agrupadas_por_invernadero_y_tipo(self):
        """PROD-CNL-ORD: las órdenes «a realizar» de los invernaderos del Agrónomo, agrupadas por invernadero y tipo."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        orden_de_siembra(self.e, plantines=1, sector="crecimiento", estado="cancelada")
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        orden_de_siembra(otro, plantines=1)
        grupos = ordenes.ordenes_cancelables(self.e.agronomo)
        self.assertEqual(len(grupos), 1)
        self.assertEqual((grupos[0].invernadero_id, grupos[0].tipo_orden), (self.e.invernadero.pk, Tipo.SIEMBRA))
        self.assertEqual(ids(grupos[0].ordenes), [pendiente.pk])

    def test_el_gerente_no_cancela(self):
        """Regla de acceso de PROD-CNL-ORD: el Gerente no tiene esta pantalla (no cancela); no hay nada cancelable para él."""
        orden_de_siembra(self.e, plantines=1)
        self.assertEqual(ordenes.ordenes_cancelables(crear_gerente()), [])


class TiposDeOrdenFuturosTests(ConDatosDeInventario, TestCase):
    """D-67 punto 1: las tres lecturas filtran con la lista de tipos permitidos (`tipo_orden__in`), nunca con «todo menos X»."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def armar(self):
        self.siembra = orden_de_siembra(self.e, plantines=1)
        self.entrega = orden_suelta(self.e.invernadero, Tipo.ENTREGA)
        self.mantenimiento = orden_suelta(self.e.invernadero, Tipo.MANTENIMIENTO)

    def test_d67_una_entrega_y_un_mantenimiento_sueltos_no_aparecen_en_ninguna_lectura(self):
        """D-67 punto 1: con una siembra y dos órdenes sueltas «a realizar» del mismo invernadero (entrega y mantenimiento), la lista
        (también con «Todos los tipos»), las cancelables y las del Capataz devuelven solo la siembra."""
        self.armar()
        self.assertEqual(ids(ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes())), [self.siembra.pk])
        todos_los_tipos = ordenes.FiltrosDeOrdenes(tipo="")
        self.assertEqual(ids(ordenes.lista_de_ordenes(self.e.agronomo, todos_los_tipos)), [self.siembra.pk])
        con_el_tipo_de_otro = ordenes.FiltrosDeOrdenes(tipo=Tipo.ENTREGA)
        self.assertEqual(ordenes.lista_de_ordenes(self.e.agronomo, con_el_tipo_de_otro), [])
        grupos = ordenes.ordenes_cancelables(self.e.agronomo)
        self.assertEqual([i for g in grupos for i in ids(g.ordenes)], [self.siembra.pk])
        self.assertEqual(ids(ordenes.ordenes_del_capataz(self.e.capataz)), [self.siembra.pk])
        self.assertEqual(ids(ordenes.bandeja_del_capataz(self.e.capataz).hoy), [self.siembra.pk])

    def test_d67_las_tres_lecturas_filtran_por_la_constante_y_no_por_todo_menos_x(self):
        """D-67 punto 1: si `TIPOS_DE_PRODUCCION` cambia, las lecturas cambian. Con `(SIEMBRA,)` una transición suelta (que sí está
        en la constante real) deja de aparecer en la lista y en las cancelables; con `(TRANSICION,)` la siembra deja de aparecer en
        las órdenes del Capataz y en la bandeja. (La transición suelta solo se lee: su hija llega con PRD-02.)"""
        siembra = orden_de_siembra(self.e, plantines=1)
        transicion = orden_suelta(self.e.invernadero, Tipo.TRANSICION)
        filtros = ordenes.FiltrosDeOrdenes()
        self.assertIn(transicion.pk, ids(ordenes.lista_de_ordenes(self.e.agronomo, filtros)))
        self.assertIn(transicion.pk, [i for g in ordenes.ordenes_cancelables(self.e.agronomo) for i in ids(g.ordenes)])
        with mock.patch.object(ordenes, "TIPOS_DE_PRODUCCION", (Tipo.SIEMBRA,)):
            self.assertEqual(ids(ordenes.lista_de_ordenes(self.e.agronomo, filtros)), [siembra.pk])
            self.assertEqual([i for g in ordenes.ordenes_cancelables(self.e.agronomo) for i in ids(g.ordenes)], [siembra.pk])
        with mock.patch.object(ordenes, "TIPOS_DE_PRODUCCION", (Tipo.TRANSICION,)):
            self.assertEqual(ordenes.ordenes_del_capataz(self.e.capataz), [])
            self.assertEqual(ordenes.bandeja_del_capataz(self.e.capataz).hoy, [])

    def test_d67_las_constantes_de_tipos_son_las_documentadas(self):
        """docs/api/produccion.md, sección 2: `TIPOS_DE_PRODUCCION = (SIEMBRA, TRANSICION, COSECHA)` y
        `TIPOS_QUE_CANCELA_PRODUCCION = (SIEMBRA, TRANSICION)`."""
        self.assertEqual(ordenes.TIPOS_DE_PRODUCCION, (Tipo.SIEMBRA, Tipo.TRANSICION, Tipo.COSECHA))
        self.assertEqual(ordenes.TIPOS_QUE_CANCELA_PRODUCCION, (Tipo.SIEMBRA, Tipo.TRANSICION))
