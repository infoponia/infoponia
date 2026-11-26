# Pruebas de la pantalla «Estadísticas» de producción (EST-01, paso 4): acceso por rol, filtro por GET, comparación, selector de órdenes,
# enlaces y menú. Fuente: EST-CNS-PRD reglas 1, 2, 5, 7 y 9 (docs/casos_de_uso/estadisticas/estadisticas.md) y D-93 puntos 2, 5 y 6.
# El día de «hoy» se fija en `HOY` (26/11/2026) con un `patch` de `timezone.localdate`, así las pruebas no dependen del día en que corren.

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from contabilidad.tests.fabricas import ejercicio_abierto
from core.menu import menu_de
from core.models import Contador, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_cuenta, crear_gerente
from estadisticas.servicios import produccion
from estadisticas.tests.fabricas import HOY, dos_invernaderos, lote_sembrado, merma_de, orden
from iot.tests.fabricas import ConCatalogoIot, sistema
from maestros.tests.fabricas import crear_agronomo, crear_tecnico, crear_vendedor
from produccion.models import OrdenTrabajo

URL = reverse("estadisticas:produccion")
Rol = Usuario.Rol


class EstCnsPrdVistaTests(ConCatalogoIot, TestCase):
    """La pantalla «Estadísticas»: el Agrónomo y el Gerente la ven; los demás reciben 403."""

    @classmethod
    def setUpTestData(cls):
        cls.n, cls.s = dos_invernaderos()
        cls.gerente = crear_gerente()
        lote = lote_sembrado(cls.n, 100, date(2026, 11, 5))
        merma_de(lote, 5, "plaga", date(2026, 11, 8))
        lote_sembrado(cls.n, 60, date(2026, 10, 10))  # del período anterior
        lote_sembrado(cls.s, 40, date(2026, 11, 6))
        orden(cls.n.invernadero, OrdenTrabajo.Tipo.ENTREGA, date(2026, 11, 15), resolucion=date(2026, 11, 16))  # vencida

    def setUp(self):
        parche = mock.patch("estadisticas.views.timezone.localdate", return_value=HOY)
        parche.start()
        self.addCleanup(parche.stop)

    def ver(self, cuenta, **parametros):
        """Abre la pantalla como `cuenta` con los parámetros GET."""
        self.client.force_login(cuenta)
        return self.client.get(URL, parametros)

    # ---- Acceso (regla 7) ----

    def test_regla_acceso_capataz_tecnico_vendedor_y_contador_reciben_403(self):
        """EST-CNS-PRD regla 7 (y la 9 de H28): el Capataz y el Técnico no tienen acceso; tampoco el Vendedor ni el Contador (D-85 punto 6)."""
        cuentas = {
            "capataz": self.n.capataz,
            "tecnico": crear_tecnico(),
            "vendedor": crear_vendedor(),
            "contador": crear_cuenta(Contador, email="contador@infoponia.com"),
        }
        for nombre, cuenta in cuentas.items():
            with self.subTest(rol=nombre):
                self.assertEqual(self.ver(cuenta).status_code, 403)

    def test_regla_acceso_sin_sesion_pide_iniciar_sesion(self):
        """Toda pantalla exige sesión (D-25): sin cuenta, redirige al ingreso."""
        self.assertEqual(self.client.get(URL).status_code, 302)

    def test_regla_acceso_agronomo_y_gerente_entran(self):
        """EST-CNS-PRD regla 1: el Agrónomo y el Gerente consultan las estadísticas."""
        self.assertEqual(self.ver(self.n.agronomo).status_code, 200)
        self.assertEqual(self.ver(self.gerente).status_code, 200)

    def test_regla_menu_la_entrada_es_del_agronomo_y_del_gerente(self):
        """EST-CNS-PRD regla 9 (H28): la entrada «Estadísticas» del menú es del Agrónomo y del Gerente; el resto de los roles no la tiene."""
        for rol, debe in ((Rol.AGRONOMO, True), (Rol.GERENTE, True), (Rol.VENDEDOR, False), (Rol.CONTADOR, False), (Rol.CAPATAZ, False), (Rol.TECNICO, False)):
            with self.subTest(rol=rol):
                self.assertEqual(("Estadísticas", "estadisticas:produccion", "chart") in menu_de(rol), debe)

    def test_regla_menu_se_ve_en_el_marco_del_agronomo(self):
        """H28: el enlace del menú lleva a la pantalla."""
        self.assertContains(self.ver(self.n.agronomo), f'href="{URL}"')

    def test_regla_9_la_consulta_no_audita(self):
        """EST-CNS-PRD regla 9 y SEG-14: una consulta no registra auditoría."""
        antes = RegistroAuditoria.objects.count()
        self.ver(self.gerente, periodo="tres_meses")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_9_solo_se_consulta_con_get(self):
        """EST-CNS-PRD regla 9: es una consulta, no recibe envíos POST."""
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.post(URL, {}).status_code, 405)

    # ---- Alcance (regla 1) ----

    def test_regla_1_el_agronomo_ve_solo_lo_suyo_y_sin_selector(self):
        """EST-CNS-PRD regla 1: el Agrónomo ve sus invernaderos: 100 sembradas (no las 40 del Sur) y, con uno solo, sin selector de invernadero."""
        respuesta = self.ver(self.n.agronomo)
        self.assertEqual(respuesta.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 100)
        self.assertNotContains(respuesta, "Invernadero Sur")
        self.assertNotContains(respuesta, 'name="invernadero" data-desplegable')

    def test_regla_1_el_gerente_ve_todos_y_filtra_por_invernadero(self):
        """EST-CNS-PRD regla 1: el Gerente ve el consolidado (140) con un selector de invernadero y puede filtrar por uno (Sur: 40)."""
        todos = self.ver(self.gerente)
        self.assertEqual(todos.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 140)
        self.assertContains(todos, "Invernadero Sur")
        sur = self.ver(self.gerente, invernadero=self.s.invernadero.pk)
        self.assertEqual(sur.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 40)

    def test_regla_1_un_invernadero_ajeno_muestra_el_error_y_ningun_dato(self):
        """EST-CNS-PRD regla 1: pedir por URL el invernadero de otro Agrónomo muestra un aviso, no sus datos (ni un 500)."""
        respuesta = self.ver(self.n.agronomo, invernadero=self.s.invernadero.pk)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No tenés acceso a ese invernadero.")
        self.assertIsNone(respuesta.context["resultado"])

    def test_regla_1_un_invernadero_que_no_es_un_numero_se_ignora(self):
        """Robustez: un `invernadero` escrito a mano que no es un número se trata como «todos»."""
        self.assertEqual(self.ver(self.gerente, invernadero="abc").status_code, 200)

    def test_regla_1_sin_invernaderos_a_cargo_avisa(self):
        """D-61 punto 2 (estado vacío): un Agrónomo sin invernaderos a cargo ve el aviso en lugar de las tarjetas."""
        respuesta = self.ver(crear_agronomo(email="sin.invernaderos@infoponia.com"))
        self.assertContains(respuesta, "No tenés invernaderos para consultar")

    # ---- Período y filtros (regla 2) ----

    def test_regla_2_por_defecto_es_el_mes_actual_hasta_hoy_con_comparacion(self):
        """EST-CNS-PRD regla 2 y D-93 punto 2: por defecto, del 1 del mes a hoy y comparado con el período anterior de igual duración."""
        respuesta = self.ver(self.n.agronomo)
        self.assertContains(respuesta, "01/11/2026 al 26/11/2026")
        self.assertContains(respuesta, "se compara con 06/10/2026 al 31/10/2026")

    def test_regla_2_los_atajos_calculan_su_periodo(self):
        """D-93 punto 2: «Mes anterior» y «Últimos 3 meses» (mismo día de tres meses atrás)."""
        self.assertContains(self.ver(self.gerente, periodo="mes_anterior"), "01/10/2026 al 31/10/2026")
        self.assertContains(self.ver(self.gerente, periodo="tres_meses"), "26/08/2026 al 26/11/2026")

    def test_regla_2_ejercicio_actual_va_del_inicio_del_ejercicio_abierto_a_hoy(self):
        """D-93 punto 2: «Ejercicio actual» desde el inicio del ejercicio abierto."""
        ejercicio_abierto(inicio=date(2026, 3, 1))
        self.assertContains(self.ver(self.gerente, periodo="ejercicio"), "01/03/2026 al 26/11/2026")

    def test_regla_2_ejercicio_actual_sin_ejercicio_abierto_avisa(self):
        """D-61 punto 2: sin ejercicio abierto el atajo muestra «No hay un ejercicio abierto.»"""
        self.assertContains(self.ver(self.gerente, periodo="ejercicio"), "No hay un ejercicio abierto.")

    def test_regla_2_un_rango_a_mano_se_aplica(self):
        """EST-CNS-PRD regla 2: «se puede elegir otro mes o un rango»: del 05/11 al 12/11 solo cuenta la siembra del 05/11 (100)."""
        respuesta = self.ver(self.n.agronomo, periodo="personalizado", desde="2026-11-05", hasta="2026-11-12")
        self.assertContains(respuesta, "05/11/2026 al 12/11/2026")
        self.assertEqual(respuesta.context["resultado"].actual.sembradas_y_cosechadas.sembradas, 100)
        self.assertContains(respuesta, 'name="desde"')

    def test_regla_2_personalizado_sin_fechas_ofrece_el_periodo_por_defecto(self):
        """D-61 punto 2: al elegir «Personalizado» (todavía sin fechas) se ven los campos con el período por defecto para cambiarlos."""
        respuesta = self.ver(self.gerente, periodo="personalizado")
        self.assertContains(respuesta, 'value="2026-11-01"')
        self.assertContains(respuesta, 'value="2026-11-26"')

    def test_regla_2_un_rango_de_mas_de_un_ano_da_un_mensaje_claro_y_ningun_dato(self):
        """D-93 punto 2: «El período no puede ser mayor que un año.», sin tarjetas."""
        respuesta = self.ver(self.gerente, periodo="personalizado", desde="2025-01-01", hasta="2026-11-26")
        self.assertContains(respuesta, "El período no puede ser mayor que un año.")
        self.assertNotContains(respuesta, "Plantas sembradas")

    def test_regla_2_las_fechas_invalidas_se_rechazan_con_su_mensaje(self):
        """D-93 punto 2: «desde» posterior a «hasta», un período que termina después de hoy y una fecha que falta."""
        casos = (
            ({"desde": "2026-11-10", "hasta": "2026-11-05"}, "La fecha “desde” no puede ser posterior a “hasta”."),
            ({"desde": "2026-11-01", "hasta": "2026-11-27"}, "El período no puede terminar después de hoy."),
            ({"desde": "2026-11-01", "hasta": "no-es-fecha"}, "Indicá las dos fechas."),
        )
        for datos, mensaje in casos:
            with self.subTest(mensaje=mensaje):
                self.assertContains(self.ver(self.gerente, periodo="personalizado", **datos), mensaje)

    def test_regla_2_el_formulario_es_un_get_que_se_puede_compartir(self):
        """D-93 punto 2 («Cómo se aplica»): el formulario del período es un GET: la URL se puede compartir y volver a abrir (y funciona sin JavaScript)."""
        self.assertContains(self.ver(self.gerente), 'method="get"')

    # ---- Comparación ----

    def test_regla_2_sin_enviar_el_formulario_la_comparacion_viene_prendida_y_con_diferencias(self):
        """EST-CNS-PRD regla 2: «se compara con el período anterior»: sembradas 100 contra 60 es ▲ 40 (66,7 %)."""
        respuesta = self.ver(self.n.agronomo)
        self.assertContains(respuesta, "▲ 40 (66,7 %) frente al período anterior")
        self.assertContains(respuesta, "checked")

    def test_regla_2_con_la_comparacion_apagada_no_hay_diferencias_ni_periodo_anterior(self):
        """EST-CNS-PRD regla 2: con el formulario enviado y la casilla sin tildar no se compara."""
        respuesta = self.ver(self.n.agronomo, enviado="1", periodo="mes")
        self.assertNotContains(respuesta, "frente al período anterior")
        self.assertNotContains(respuesta, "se compara con")
        self.assertIsNone(respuesta.context["resultado"].previo)

    def test_regla_2_con_la_casilla_tildada_se_compara(self):
        """EST-CNS-PRD regla 2: con la casilla tildada se compara."""
        respuesta = self.ver(self.n.agronomo, enviado="1", periodo="mes", comparar="on")
        self.assertContains(respuesta, "se compara con 06/10/2026 al 31/10/2026")

    # ---- Selector de órdenes (D-93 punto 3.3) ----

    def test_d93_punto_3_3_todas_cuenta_la_entrega_y_solo_de_produccion_no(self):
        """D-93 punto 3.3: con «Todas» entra la entrega vencida; con «Solo de producción» no, y el botón queda marcado."""
        todas = self.ver(self.n.agronomo, ordenes="todas")
        self.assertContains(todas, "<td>Entrega</td>")
        solo = self.ver(self.n.agronomo, ordenes="produccion")
        self.assertNotContains(solo, "<td>Entrega</td>")
        self.assertContains(solo, '<td>Siembra</td>')
        self.assertContains(solo, 'value="produccion" aria-pressed="true"')

    def test_d93_punto_3_3_el_boton_apretado_gana_sobre_el_valor_escondido(self):
        """La pantalla manda el valor actual escondido y el botón apretado después: el último valor del GET es el que vale."""
        respuesta = self.ver(self.n.agronomo, ordenes=["todas", "produccion"])
        self.assertEqual(respuesta.context["filtro"]["ordenes"], "produccion")

    # ---- Bloques que se muestran o no ----

    def test_regla_4_6_sin_iot_el_bloque_de_alertas_no_se_muestra(self):
        """EST-CNS-PRD regla 4.6: «solo si el invernadero tiene un sistema IoT. Si no, no se muestra»."""
        self.assertNotContains(self.ver(self.n.agronomo), "Alertas del IoT")

    def test_regla_4_6_con_iot_el_bloque_de_alertas_se_muestra(self):
        """EST-CNS-PRD regla 4.6: con IoT, el bloque aparece (aunque no haya alertas)."""
        sistema(self.n.invernadero)
        self.assertContains(self.ver(self.n.agronomo), "Alertas del IoT")

    def test_d93_punto_5_sin_cosecha_disponible_lo_dice(self):
        """D-93 punto 5: sin la fuente de la cosecha, el lugar de los indicadores 1 (cosechadas) y 4 dice «Disponible cuando exista la cosecha»."""
        with mock.patch.object(produccion, "cosecha_disponible", return_value=False):
            respuesta = self.ver(self.n.agronomo)
        self.assertContains(respuesta, "Disponible cuando exista la cosecha")
        self.assertContains(respuesta, "Plantas sembradas")

    def test_d61_un_periodo_sin_actividad_lo_dice(self):
        """D-61 punto 2 (estado vacío): un período sin nada muestra «No hay actividad en este período», no tarjetas en cero."""
        respuesta = self.ver(self.n.agronomo, periodo="personalizado", desde="2026-01-01", hasta="2026-01-31")
        self.assertContains(respuesta, "No hay actividad en este período")

    # ---- Enlaces (regla 5, D-93 punto 6) ----

    def test_regla_5_el_agronomo_con_un_invernadero_tiene_los_enlaces_con_su_invernadero_y_el_periodo(self):
        """EST-CNS-PRD regla 5 / D-93 punto 6: bitácora y mermas con el mismo invernadero y el mismo período (la bitácora filtra por fechas),
        órdenes con el invernadero (no filtran por fechas), insumos con el invernadero."""
        respuesta = self.ver(self.n.agronomo)
        pk = self.n.invernadero.pk
        enlaces = respuesta.context["enlaces"]
        self.assertEqual(enlaces["bitacora"], f"{reverse('produccion:bitacora')}?invernadero={pk}&desde=2026-11-01&hasta=2026-11-26")
        self.assertEqual(enlaces["bitacora_merma"], f"{reverse('produccion:bitacora')}?invernadero={pk}&tipo=merma&desde=2026-11-01&hasta=2026-11-26")
        self.assertEqual(enlaces["ordenes"], f"{reverse('produccion:ordenes')}?invernadero={pk}")
        self.assertEqual(enlaces["insumos"], f"{reverse('inventario:existencias')}?invernadero={pk}")
        self.assertContains(respuesta, "Ver las mermas")

    def test_regla_5_el_consolidado_de_varios_invernaderos_no_enlaza_a_lo_que_se_mira_de_a_uno(self):
        """EST-CNS-PRD regla 5: la bitácora y los insumos se miran de un invernadero por vez: con el consolidado del Gerente (dos invernaderos)
        no hay enlace a ellos; el de las órdenes sí, sin invernadero."""
        enlaces = self.ver(self.gerente).context["enlaces"]
        self.assertNotIn("bitacora", enlaces)
        self.assertNotIn("insumos", enlaces)
        self.assertEqual(enlaces["ordenes"], reverse("produccion:ordenes"))

    def test_regla_5_el_gerente_no_recibe_el_enlace_a_insumos_que_le_daria_403(self):
        """D-30: ningún botón lleva a un 403. El inventario es del Agrónomo a cargo: el Gerente, aun con un invernadero elegido, no lo recibe."""
        enlaces = self.ver(self.gerente, invernadero=self.s.invernadero.pk).context["enlaces"]
        self.assertIn("bitacora", enlaces)
        self.assertNotIn("insumos", enlaces)

    def test_regla_5_los_enlaces_llevan_a_pantallas_que_la_cuenta_puede_abrir(self):
        """D-30: cada enlace que se muestra abre (no da 403) para el Agrónomo y para el Gerente."""
        for cuenta, parametros in ((self.n.agronomo, {}), (self.gerente, {"invernadero": self.n.invernadero.pk})):
            enlaces = self.ver(cuenta, **parametros).context["enlaces"]
            for nombre, enlace in enlaces.items():
                with self.subTest(cuenta=str(cuenta), enlace=nombre):
                    self.client.force_login(cuenta)
                    self.assertNotEqual(self.client.get(enlace).status_code, 403)
