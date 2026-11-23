# Pruebas del Inicio del Agrónomo (PRD-04, paso 6; D-51 punto 10, D-43): `inicio.indicadores_del_agronomo(actor, invernadero_ids)` y su sección
# registrada con `registrar_seccion_de_inicio`. No es un caso de uso: es una sección de inicio con indicadores del prototipo (`VIEWS.inicio`).
#
# CONTRATO que fijan estas pruebas (se anota en el Cierre y en temas_abiertos.md):
#   indicadores_del_agronomo(actor, invernadero_ids) -> IndicadoresDelAgronomo(lotes_activos, plantas_en_pie, ordenes_a_realizar, ordenes_vencidas,
#       agujeros_ocupados, agujeros_totales, porcentaje_de_ocupacion, insumos_por_vencer, sin_invernaderos)
#     - Solo cuenta los invernaderos ACTIVOS a cargo del actor que figuran en `invernadero_ids`; los demás se ignoran (el Agrónomo ve solo los suyos).
#       Un actor que no es Agrónomo recibe `sin_permiso`.
#     - Lotes activos y sus plantas; órdenes «a realizar» de siembra y transición (`TIPOS_DE_PRODUCCION`) y cuántas están vencidas (fecha programada
#       anterior a hoy); ocupación = agujeros ocupados ÷ agujeros totales de los sectores ACTIVOS (los fuera de servicio no cuentan: sus agujeros no se
#       ofrecen), en porcentaje entero redondeado; insumos por vencer = alertas ACTIVAS `inv_insumo_por_vencer` destinadas al actor
#       (`Alerta.objects.para(actor)`) en esos invernaderos. No hay función nueva en `inventario`.
#     - Una consulta por indicador (no por invernadero): la cantidad de consultas no depende de cuántos invernaderos haya.
#   seccion_de_inicio_del_agronomo(usuario) -> SeccionDeInicio | None (plantilla `produccion/_inicio_agronomo.html`, contexto con `indicadores`).
#     Sin invernaderos a cargo, la sección dice cómo empezar. La del Capataz sigue como estaba.

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.tests.fabricas import crear_gerente
from inventario.alertas import INSUMO_POR_VENCER, INSUMO_VENCIDO
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero, SectorProduccion
from maestros.tests.fabricas import crear_agronomo, crear_alerta, crear_invernadero, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.servicios import inicio, registrantes
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo, orden_de_siembra, orden_suelta


class BaseDeInicio(ConDatosDeInventario, TestCase):
    """Un invernadero con un sector por etapa, de 100 agujeros cada uno (500 en total), a cargo de su Agrónomo."""

    def setUp(self):
        self.e = invernadero_con_produccion()
        self.hoy = timezone.localdate()

    def indicadores(self, ids=None, actor=None):
        """Los indicadores del Agrónomo del escenario (o de `actor`) para `ids` (por omisión, su invernadero)."""
        ids = [self.e.invernadero.pk] if ids is None else ids
        return inicio.indicadores_del_agronomo(actor or self.e.agronomo, ids)


class IndicadoresTests(BaseDeInicio):
    """Cada indicador y quién los ve."""

    def test_ext_lotes_activos_cuenta_los_lotes_y_sus_plantas_y_no_los_finalizados(self):
        """Lotes activos y plantas en pie: solo los lotes «activos»."""
        lote_activo(self.e, cantidad=30)
        lote_activo(self.e, cantidad=12)
        terminado = lote_activo(self.e, cantidad=5, costo="0.00")
        type(terminado).objects.filter(pk=terminado.pk).update(cantidad_actual=0, estado_lote="finalizado")
        resultado = self.indicadores()
        self.assertEqual((resultado.lotes_activos, resultado.plantas_en_pie), (2, 42))

    def test_ext_ordenes_vencidas_son_las_a_realizar_con_fecha_anterior_a_hoy_sobre_el_total_a_realizar(self):
        """Órdenes «a realizar» y cuántas vencidas (fecha programada anterior a hoy); no cuentan las concretadas ni las canceladas, ni las
        entregas o mantenimientos (no son órdenes del Agrónomo en las pantallas de `produccion`)."""
        orden_de_siembra(self.e, plantines=1, dias=-2, con_reserva=False)
        orden_de_siembra(self.e, plantines=1, dias=0, sector="crecimiento", con_reserva=False)
        orden_de_siembra(self.e, plantines=1, dias=3, sector="floracion", con_reserva=False)
        orden_de_siembra(self.e, plantines=1, dias=-5, sector="fructificacion", estado="cancelada", con_reserva=False)
        orden_de_siembra(self.e, plantines=1, dias=-5, sector="maduracion", estado="concretada", con_reserva=False)
        orden_suelta(self.e.invernadero, "entrega")
        resultado = self.indicadores()
        self.assertEqual((resultado.ordenes_vencidas, resultado.ordenes_a_realizar), (1, 3))

    def test_ext_ocupacion_son_los_agujeros_ocupados_sobre_el_total_de_los_sectores_activos(self):
        """Ocupación: agujeros ocupados ÷ totales de los sectores activos, en porcentaje entero redondeado. Un sector fuera de servicio no
        suma sus agujeros ni los de su lote; uno dado de baja tampoco."""
        lote_activo(self.e, cantidad=100)
        resultado = self.indicadores()
        self.assertEqual((resultado.agujeros_ocupados, resultado.agujeros_totales, resultado.porcentaje_de_ocupacion), (100, 500, 20))
        crear_sector(self.e.invernadero, "Fuera", "germinacion", 300, "fuera_de_servicio")
        crear_sector(self.e.invernadero, "De baja", "germinacion", 300, "inactivo")
        self.assertEqual(self.indicadores().agujeros_totales, 500)

    def test_ext_ocupacion_redondea_al_entero_mas_cercano(self):
        """Ocupación: 1 ÷ 3 es 33 %; 2 ÷ 3 es 67 %."""
        SectorProduccion.objects.filter(invernadero=self.e.invernadero).exclude(pk=self.e.sectores["germinacion"].pk).update(estado_sector="inactivo")
        SectorProduccion.objects.filter(pk=self.e.sectores["germinacion"].pk).update(cant_agujeros_total=3)
        lote_activo(self.e, cantidad=1)
        self.assertEqual(self.indicadores().porcentaje_de_ocupacion, 33)
        lote_activo(self.e, cantidad=1)
        self.assertEqual(self.indicadores().porcentaje_de_ocupacion, 67)

    def test_ext_sin_agujeros_la_ocupacion_es_cero_sin_dividir_por_cero(self):
        """Un invernadero sin sectores activos: 0 agujeros y 0 %."""
        invernadero = crear_invernadero("Sin sectores", agronomo=self.e.agronomo)
        resultado = self.indicadores([invernadero.pk])
        self.assertEqual((resultado.agujeros_totales, resultado.porcentaje_de_ocupacion), (0, 0))
        self.assertFalse(resultado.sin_invernaderos)

    def test_ext_insumos_por_vencer_son_las_alertas_activas_del_tipo_destinadas_al_actor(self):
        """Insumos por vencer: alertas ACTIVAS `inv_insumo_por_vencer` del actor (`Alerta.objects.para(actor)`); no cuentan las resueltas, las
        de vencidos ni las de otro tipo ni las de otro Agrónomo."""
        inv, yo = self.e.invernadero, self.e.agronomo
        crear_alerta(inv, INSUMO_POR_VENCER, para_gerente=False, agronomo=yo, clave_estado="a")
        crear_alerta(inv, INSUMO_POR_VENCER, para_gerente=False, agronomo=yo, clave_estado="b")
        crear_alerta(inv, INSUMO_POR_VENCER, para_gerente=False, agronomo=yo, resuelta=True, clave_estado="c")
        crear_alerta(inv, INSUMO_VENCIDO, para_gerente=False, agronomo=yo, clave_estado="d")
        crear_alerta(inv, "inv_insumo_bajo_minimo", para_gerente=False, agronomo=yo, clave_estado="e")
        otro = crear_agronomo(email="otro@infoponia.com")
        crear_alerta(inv, INSUMO_POR_VENCER, para_gerente=False, agronomo=otro, clave_estado="f")
        crear_alerta(inv, INSUMO_POR_VENCER, para_gerente=True, agronomo=None, clave_estado="g")  # solo del Gerente
        self.assertEqual(self.indicadores().insumos_por_vencer, 2)

    def test_regla_el_agronomo_ve_solo_sus_invernaderos_y_activos(self):
        """Alcance: un invernadero de otro Agrónomo o dado de baja no suma, aunque su id venga en la lista."""
        ajeno = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="2")
        lote_activo(ajeno, cantidad=50)
        lote_activo(self.e, cantidad=10)
        propio_inactivo = crear_invernadero("Inactivo", agronomo=self.e.agronomo, activo=False)
        resultado = self.indicadores([self.e.invernadero.pk, ajeno.invernadero.pk, propio_inactivo.pk])
        self.assertEqual((resultado.lotes_activos, resultado.plantas_en_pie), (1, 10))

    def test_regla_un_actor_que_no_es_agronomo_recibe_sin_permiso(self):
        """Solo el Agrónomo activo: el Capataz y el Gerente no (el Gerente tiene su propio inicio)."""
        for actor in (self.e.capataz, crear_gerente(), None):
            with self.subTest(actor=actor), self.assertRaises(ErrorDeProduccion) as contexto:
                inicio.indicadores_del_agronomo(actor, [self.e.invernadero.pk])
            self.assertEqual(contexto.exception.codigo, "sin_permiso")

    def test_ext_sin_invernaderos_los_indicadores_quedan_en_cero_y_lo_avisan(self):
        """Sin invernaderos a cargo (lista vacía o ninguno suyo): todo en cero y `sin_invernaderos`."""
        for ids in ([], [999999]):
            resultado = self.indicadores(ids)
            self.assertTrue(resultado.sin_invernaderos)
            self.assertEqual(
                (resultado.lotes_activos, resultado.plantas_en_pie, resultado.ordenes_a_realizar, resultado.ordenes_vencidas, resultado.insumos_por_vencer),
                (0, 0, 0, 0, 0),
            )

    def test_la_cantidad_de_consultas_no_depende_de_los_invernaderos_ni_de_los_datos(self):
        """Una consulta por indicador, no por invernadero: con uno o con tres invernaderos llenos, las mismas consultas."""
        lote_activo(self.e, cantidad=10)
        with CaptureQueriesContext(connection) as pocas:
            self.indicadores()
        ids = [self.e.invernadero.pk]
        for numero in range(2):
            otro = crear_invernadero(f"Otro {numero}", agronomo=self.e.agronomo)
            crear_sector(otro, f"S{numero}", "germinacion", 10)
            ids.append(otro.pk)
        orden_de_siembra(self.e, plantines=1, con_reserva=False)
        crear_alerta(self.e.invernadero, INSUMO_POR_VENCER, para_gerente=False, agronomo=self.e.agronomo, clave_estado="x")
        with CaptureQueriesContext(connection) as muchas:
            self.indicadores(ids)
        self.assertEqual(len(pocas), len(muchas))
        self.assertLessEqual(len(muchas), 7)


class SeccionDeInicioTests(BaseDeInicio):
    """La sección registrada con `registrar_seccion_de_inicio` y la pantalla de Inicio."""

    def test_ext_la_seccion_esta_registrada_una_sola_vez(self):
        """`ready()` registra la sección del Agrónomo (el registro es idempotente)."""
        from django.apps import apps

        from core import extensiones

        apps.get_app_config("produccion").ready()
        self.assertEqual(extensiones._SECCIONES_DE_INICIO.count(registrantes.seccion_de_inicio_del_agronomo), 1)

    def test_ext_solo_el_agronomo_activo_recibe_su_seccion(self):
        """La sección del Agrónomo es `None` para el Capataz, el Gerente y una cuenta inactiva; la del Capataz sigue siendo suya."""
        self.assertIsNotNone(registrantes.seccion_de_inicio_del_agronomo(self.e.agronomo))
        for usuario in (self.e.capataz, crear_gerente()):
            self.assertIsNone(registrantes.seccion_de_inicio_del_agronomo(usuario))
        self.assertIsNone(registrantes.seccion_de_inicio(self.e.agronomo))
        self.assertIsNotNone(registrantes.seccion_de_inicio(self.e.capataz))

    def test_ext_el_inicio_del_agronomo_muestra_sus_indicadores_y_enlaza_a_las_pantallas_de_origen(self):
        """Pantalla de Inicio: lotes activos, órdenes vencidas, ocupación e insumos por vencer, con sus enlaces; todo escapado."""
        lote_activo(self.e, cantidad=100)
        orden_de_siembra(self.e, plantines=1, dias=-1, sector="crecimiento", con_reserva=False)
        crear_alerta(self.e.invernadero, INSUMO_POR_VENCER, para_gerente=False, agronomo=self.e.agronomo, clave_estado="x")
        self.client.force_login(self.e.agronomo)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Lotes activos", "Órdenes vencidas", "Ocupación", "Insumos por vencer", "20", "de 1 a realizar"):
            self.assertContains(respuesta, texto)
        self.assertContains(respuesta, reverse("produccion:ordenes"))

    def test_ext_sin_invernaderos_la_seccion_dice_como_empezar(self):
        """Sin invernaderos a cargo, la sección explica cómo empezar y no muestra indicadores en cero."""
        solo = crear_agronomo(email="solo@infoponia.com")
        self.client.force_login(solo)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, "no tenés ningún invernadero a cargo")
        self.assertNotContains(respuesta, "Lotes activos")

    def test_ext_el_nombre_del_invernadero_y_el_texto_se_escapan(self):
        """Escape de HTML: un nombre de invernadero con marcado no se interpreta."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(nombre_invernadero="<b>Norte</b>")
        self.client.force_login(self.e.agronomo)
        self.assertNotContains(self.client.get(reverse("core:inicio")), "<b>Norte</b>")

    def test_ext_la_seccion_no_hace_consultas_por_invernadero(self):
        """El Inicio no hace más consultas con más invernaderos."""
        self.client.force_login(self.e.agronomo)
        self.client.get(reverse("core:inicio"))
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(reverse("core:inicio"))
        for numero in range(3):
            otro = crear_invernadero(f"Otro {numero}", agronomo=self.e.agronomo)
            crear_sector(otro, f"S{numero}", "germinacion", 10)
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(reverse("core:inicio"))
        self.assertEqual(len(pocas), len(muchas))
