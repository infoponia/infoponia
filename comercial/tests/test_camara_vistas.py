# Pruebas de las pantallas de la cámara (COM-04b, paso 6; docs/casos_de_uso/produccion/camara.md, «Pestaña «Cámara»», «Configuración» y «Pantallas»; merma.md, «Pantallas»):
# la pestaña «Cámara» de la ficha del invernadero (quién la ve), «Registrar merma en cámara» con HTMX y sin él, la opción «Pérdida en cámara» de la merma de PRD-03, los indicadores del
# panel del Agrónomo y la opción en la merma de PRD-03 (el parámetro de «Configuración» se prueba en `maestros/tests/test_configuracion_vistas.py`). Las reglas de negocio ya las prueban los servicios (`test_prod_asg_cam.py`, `test_prod_vnc_cam.py`,
# `test_prod_reg_mrm_camara.py`): acá, los permisos (ningún botón lleva a un 403), el flujo y lo que muestra cada pantalla.

import re
from datetime import timedelta
from html import unescape

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.servicios import camara
from comercial.tests.fabricas import compra_venta, detalle, escenario_comercial, partida, reserva, verificar_invariantes_de_reservas
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo
from produccion.models import Merma
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con Agrónomo, Capataz y Vendedor, un lote de 300 en Maduración y una partida de 50 plantas con 20 reservadas para una venta con envío."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.partida = partida(self.lote, 50, fecha_limite=HOY + timedelta(days=2))
        self.venta = detalle(compra_venta(self.e, dias=2), self.e.variedad, 20)
        reserva(self.venta, [(self.partida, 20)])
        self.url_ficha = reverse("maestros:invernadero", args=[self.e.invernadero.pk])
        self.url = reverse("comercial:merma_camara")
        self.addCleanup(verificar_invariantes_de_reservas)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def avisos(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]

    def datos(self, **extra):
        """Lo que manda el formulario: el invernadero, la partida, 10 plantas y la causa."""
        base = {"invernadero": str(self.e.invernadero.pk), "partida": str(self.partida.pk), "cantidad": "10", "causa": "dano_en_camara", "descripcion": ""}
        base.update(extra)
        return base


class PestanaDeCamaraTests(Base):
    def test_regla_la_pestana_la_ven_el_gerente_y_el_agronomo_a_cargo(self):
        """`camara.md`, «Pestaña «Cámara»»: la ven el Gerente y el Agrónomo a cargo (el Capataz y el Vendedor, por `pestana_de_camara`, aunque la ficha del invernadero es de
        Gerente y Agrónomo: ver `docs/temas_abiertos.md`); un Agrónomo ajeno no la ve."""
        for cuenta in (crear_gerente(), self.e.agronomo):
            with self.subTest(cuenta=cuenta):
                self.entrar(cuenta)
                respuesta = self.client.get(self.url_ficha + "?pestana=camara")
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, 'aria-selected="true"')
                self.assertIn(self.partida.codigo, texto(respuesta))
        self.entrar(crear_agronomo(email="ajeno@infoponia.com"))
        self.assertEqual(self.client.get(self.url_ficha + "?pestana=camara").status_code, 403)

    def test_regla_el_registrante_decide_por_rol_incluidos_el_capataz_y_el_vendedor(self):
        """`pestana_de_camara`: el Gerente, el Agrónomo a cargo, el Capataz asignado y el Vendedor del invernadero; cualquier otro, `None`."""
        inv = self.e.invernadero
        for cuenta in (crear_gerente(), self.e.agronomo, self.e.capataz, self.e.vendedor):
            with self.subTest(cuenta=cuenta):
                self.assertIsNotNone(camara.pestana_de_camara(cuenta, inv))
        for otra in (crear_agronomo(email="otro@infoponia.com"), crear_capataz_activo(email="otro.capataz@infoponia.com")):
            with self.subTest(otra=otra):
                self.assertIsNone(camara.pestana_de_camara(otra, inv))

    def test_regla_muestra_los_indicadores_y_la_tabla_con_lo_reservado(self):
        """`tabCamara`: tres indicadores (disponibles, plantas libres y por vencer) y la tabla con disponible, reservado y libre de cada partida, con el aviso «Vence el …»."""
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(self.url_ficha + "?pestana=camara"))
        self.assertIn("Partidas disponibles", pagina)
        self.assertIn("Por vencer", pagina)
        fila = re.search(rf"{self.partida.codigo}.*?</tr>", pagina, re.S).group(0)
        self.assertIn("Vence el", fila)
        self.assertRegex(fila, r"<td class=\"right\">50</td>\s*<td class=\"right\">20</td>\s*<td class=\"right\"><b>30</b></td>")

    def test_regla_ordena_las_disponibles_primero_y_limita_las_cerradas_a_los_ultimos_30_dias(self):
        """D-61 (`tabCamara` del prototipo mostraba todo sin orden): disponibles primero, por fecha límite; después las agotadas y vencidas de los últimos 30 días; las más viejas no."""
        vieja = partida(self.lote, 0, estado="vencido", fecha_limite=HOY - timedelta(days=45))
        reciente = partida(self.lote, 0, estado="agotado", fecha_limite=HOY - timedelta(days=5))
        antes = partida(self.lote, 10, fecha_limite=HOY + timedelta(days=1))
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(self.url_ficha + "?pestana=camara"))
        self.assertNotIn(vieja.codigo + "<", pagina)
        orden = [pagina.index(p.codigo) for p in (antes, self.partida, reciente)]
        self.assertEqual(orden, sorted(orden))

    def test_regla_el_boton_de_la_merma_es_solo_del_agronomo_a_cargo(self):
        """Nunca un botón a un 403: «Registrar merma en cámara» lo ve el Agrónomo a cargo; el Gerente solo consulta."""
        self.entrar(self.e.agronomo)
        self.assertIn(f"{self.url}?invernadero={self.e.invernadero.pk}", texto(self.client.get(self.url_ficha + "?pestana=camara")))
        self.entrar(crear_gerente())
        self.assertNotIn("Registrar merma en cámara", texto(self.client.get(self.url_ficha + "?pestana=camara")))

    def test_regla_sin_partidas_la_pestana_dice_que_no_hay_producto(self):
        """Estado vacío (D-61): un invernadero sin partidas lo dice."""
        otro = escenario_comercial(sufijo="2")
        self.entrar(otro.agronomo)
        self.assertIn("No hay producto en la cámara", texto(self.client.get(reverse("maestros:invernadero", args=[otro.invernadero.pk]) + "?pestana=camara")))


class MermaEnCamaraVistaTests(Base):
    def test_regla_solo_el_agronomo_y_el_capataz_asignados_entran(self):
        """Quién: el Agrónomo a cargo y el Capataz asignado. El Gerente y el Vendedor reciben 403; sin cuenta, al inicio de sesión."""
        for cuenta in (crear_gerente(), self.e.vendedor):
            with self.subTest(cuenta=cuenta):
                self.entrar(cuenta)
                self.assertEqual(self.client.get(self.url).status_code, 403)
        for cuenta in (self.e.agronomo, self.e.capataz):
            with self.subTest(cuenta=cuenta):
                self.entrar(cuenta)
                self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_flujo_principal_ver_resumen_y_confirmar_registra_la_merma(self):
        """Pasos 4a a 10: «Ver resumen» no escribe y muestra el resumen con su firma; «Confirmar» registra la merma y vuelve a la pestaña «Cámara» con un aviso."""
        self.entrar(self.e.agronomo)
        resumen = self.client.post(self.url, {**self.datos(), "accion": "calcular"})
        self.assertEqual(resumen.status_code, 200)
        self.assertEqual(Merma.objects.count(), 0)
        self.assertContains(resumen, "Confirmar merma")
        respuesta = self.client.post(self.url, {**self.datos(), "accion": "confirmar", "firma": resumen.context["firma"], "visto_disponible": "50"})
        self.assertRedirects(respuesta, self.url_ficha + "?pestana=camara", fetch_redirect_response=False)
        self.assertIn("La merma quedó registrada", self.avisos(respuesta)[0])
        self.assertEqual(Merma.objects.get().cant_merma, 10)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="registro_merma", usuario_id=self.e.agronomo.pk).exists())

    def test_flujo_principal_el_capataz_vuelve_a_su_bandeja(self):
        """El Capataz no tiene la ficha del invernadero: tras registrar, vuelve a su bandeja."""
        self.entrar(self.e.capataz)
        resumen = self.client.post(self.url, {**self.datos(), "accion": "calcular"})
        respuesta = self.client.post(self.url, {**self.datos(), "accion": "confirmar", "firma": resumen.context["firma"]})
        self.assertRedirects(respuesta, reverse("produccion:bandeja"), fetch_redirect_response=False)

    def test_ext_9_si_la_perdida_supera_el_stock_libre_el_resumen_dice_que_contratos_pierden_producto(self):
        """Paso 9 (10c): con 50 disponibles y 20 reservados, perder 40 supera el stock libre (30): el resumen nombra el contrato que pierde 10 plantas."""
        self.entrar(self.e.agronomo)
        resumen = self.client.post(self.url, {**self.datos(cantidad="40"), "accion": "calcular"})
        pagina = texto(resumen)
        self.assertIn("estos contratos pierden producto", pagina)
        self.assertIn(self.venta.compra_venta.codigo, pagina)
        self.assertEqual(resumen.context["resumen"].recortes, [(self.venta.compra_venta.codigo, 10)])

    def test_regla_confirmar_con_un_dato_cambiado_vuelve_a_mostrar_el_resumen_sin_escribir(self):
        """Si la persona cambia un dato después de ver el resumen, «Confirmar» no escribe: avisa y muestra el resumen de nuevo."""
        self.entrar(self.e.agronomo)
        resumen = self.client.post(self.url, {**self.datos(), "accion": "calcular"})
        respuesta = self.client.post(self.url, {**self.datos(cantidad="11"), "accion": "confirmar", "firma": resumen.context["firma"]})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cambiaste un dato después de ver el resumen")
        self.assertEqual(Merma.objects.count(), 0)

    def test_ext_4a_4a_los_errores_salen_por_campo(self):
        """Extensiones 4a.4a y 4a.4b: la cantidad inválida y la causa obligatoria se muestran debajo de su campo y no se escribe nada."""
        self.entrar(self.e.agronomo)
        respuesta = self.client.post(self.url, {**self.datos(cantidad="99", causa=""), "accion": "calcular"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.context["errores"]), {"cantidad", "causa"})
        self.assertIn("entre 1 y 50", respuesta.context["errores"]["cantidad"])
        self.assertEqual(Merma.objects.count(), 0)

    def test_ext_10d_si_la_disponible_cambio_desde_el_resumen_avisa_y_no_escribe(self):
        """Extensión 10d: la disponible que la persona vio ya no es la vigente: `cambio_simultaneo` con un aviso en el campo; no se escribe nada."""
        self.entrar(self.e.agronomo)
        resumen = self.client.post(self.url, {**self.datos(), "accion": "calcular"})
        respuesta = self.client.post(self.url, {**self.datos(), "accion": "confirmar", "firma": resumen.context["firma"], "visto_disponible": "60"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("cambió mientras mirabas el resumen", respuesta.context["errores"]["cantidad"])
        self.assertEqual(Merma.objects.count(), 0)

    def test_regla_con_htmx_solo_se_redibuja_el_formulario_y_sin_validar(self):
        """HTMX (`interfaz.md`): cambiar el invernadero o la partida redibuja solo el formulario («actualizar»), sin errores ni resumen; sin HTMX es la página completa."""
        self.entrar(self.e.agronomo)
        parcial = self.client.post(self.url, {"invernadero": str(self.e.invernadero.pk), "accion": "actualizar"}, **HTMX)
        self.assertTemplateUsed(parcial, "comercial/camara/_merma_formulario.html")
        self.assertTemplateNotUsed(parcial, "comercial/camara/merma.html")
        self.assertEqual((parcial.context["errores"], parcial.context["resumen"]), ({}, None))
        self.assertContains(parcial, self.partida.codigo)
        completa = self.client.post(self.url, {"invernadero": str(self.e.invernadero.pk), "accion": "actualizar"})
        self.assertTemplateUsed(completa, "comercial/camara/merma.html")
        self.assertContains(completa, "<noscript>")  # el respaldo sin JavaScript

    def test_regla_un_invernadero_ajeno_se_ignora(self):
        """Un invernadero que no es del actor no se elige: el formulario vuelve al paso 1 sin partidas ni datos de otro."""
        otro = escenario_comercial(sufijo="2")
        self.entrar(self.e.agronomo)
        respuesta = self.client.get(self.url, {"invernadero": str(otro.invernadero.pk)})
        self.assertEqual((respuesta.context["invernadero_id"], respuesta.context["partidas"]), (None, []))

    def test_regla_sin_partidas_el_formulario_lo_informa(self):
        """Extensión 4b y estado vacío: un Agrónomo sin partidas en sus invernaderos ve el aviso en lugar de una lista."""
        otro = escenario_comercial(sufijo="2")
        self.entrar(otro.agronomo)
        self.assertIn("Ninguno de tus invernaderos tiene partidas", texto(self.client.get(self.url)))


class EntradaEnLaMermaDeProduccionTests(Base):
    def test_regla_la_merma_de_produccion_ofrece_perdida_en_camara_si_hay_partidas(self):
        """Extensión 4a (D-64 punto 11): la pantalla de PRD-03 ofrece «Pérdida en cámara» con el invernadero ya elegido; sin partidas (o sin registrante) no aparece."""
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(reverse("produccion:registrar_merma"), {"invernadero": str(self.e.invernadero.pk)}))
        self.assertIn(f"{self.url}?invernadero={self.e.invernadero.pk}", pagina)
        self.assertIn("Pérdida en cámara", pagina)
        otro = escenario_comercial(sufijo="2")
        self.entrar(otro.agronomo)
        self.assertNotIn("Pérdida en cámara", texto(self.client.get(reverse("produccion:registrar_merma"))))

    def test_regla_el_capataz_tambien_la_ve_y_nadie_ve_un_boton_a_un_403(self):
        """El Capataz asignado la ve; las entradas son `None` para el Gerente y el Vendedor (que no llegan a la pantalla)."""
        from produccion.extensiones import entradas_de_comercial

        self.assertEqual(entradas_de_comercial(self.e.capataz).merma_en_camara, self.url)
        for otro in (crear_gerente(), self.e.vendedor):
            self.assertIsNone(entradas_de_comercial(otro).merma_en_camara)


class PanelDelAgronomoTests(Base):
    def test_regla_el_panel_suma_partidas_por_vencer_y_plantas_libres(self):
        """`secCosecha`: el grupo «Cosechas y cámara» del Inicio del Agrónomo trae las partidas por vencer (dentro del aviso de 3 días) y las plantas libres en cámara."""
        from comercial.servicios.registrantes import seccion_de_cosechas

        camara_datos = seccion_de_cosechas(self.e.agronomo).contexto["cosechas"]["camara"]
        self.assertEqual((camara_datos["por_vencer"], camara_datos["libres"]), (1, 30))
        self.entrar(self.e.agronomo)
        pagina = texto(self.client.get(reverse("core:inicio")))
        self.assertIn("Cosechas y cámara", pagina)
        self.assertIn("Partidas por vencer", pagina)
