# Pruebas de la vista de «Estadísticas» de Comercial y de «Resultados del mes en curso» del panel (COM-08c; docs/casos_de_uso/comercial/estadisticas.md, «Pantallas» y «Pruebas»): permisos (los demás roles 403),
# los filtros en la URL (mes, rango, invernadero, Vendedor), los errores de filtro sin números, el cuerpo con HTMX y sin JavaScript, los textos explicativos, los enlaces de la regla 10 con su filtro y el panel
# del Vendedor (sí) y del Gerente (no). Solo el cliente de Django: lo que ve un navegador (CSRF, JavaScript) va en la «Verificación a mano».
# Fuente: docs/casos_de_uso/comercial/estadisticas.md («Pantallas», «Pruebas»), D-30, D-47, D-61, D-94, `.claude/rules/interfaz.md`.

from datetime import timedelta
from html import unescape

from django.urls import reverse

from comercial.tests.fabricas import discrepancia_aceptada, segundo_invernadero
from comercial.tests.test_com_cns_est import HACE_UN_MES, HOY, PERIODO_ANTERIOR, BaseDeEstadisticas
from maestros.tests.fabricas import crear_transportista
from produccion.tests.fabricas import lote_maduro
import re


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class VistaDeEstadisticasTests(BaseDeEstadisticas):
    def ir(self, usuario=None, **get):
        self.client.force_login(usuario or self.gerente)
        return self.client.get(reverse("comercial:estadisticas"), get)

    def test_los_demas_roles_y_los_anonimos_no_entran(self):
        """El Agrónomo, el Capataz y el Transportista reciben 403; un anónimo, la pantalla de ingreso."""
        for rol in (self.e.agronomo, self.e.capataz, crear_transportista(email="t3@infoponia.com")):
            self.assertEqual(self.ir(rol).status_code, 403, rol)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("comercial:estadisticas")).status_code, 302)

    def test_el_vendedor_ve_los_indicadores_del_mes_solo_de_sus_contratos(self):
        """Flujo principal: el Vendedor abre la pestaña y ve sus números del mes, con las cuatro tarjetas y los seis indicadores; lo ajeno no aparece."""
        self.venta(cantidad=10, precio="100.00")
        self.del_otro_vendedor(cantidad=77, precio="100.00")
        respuesta = self.ir(self.e.vendedor)
        self.assertEqual(respuesta.status_code, 200)
        html = texto(respuesta)
        for esperado in ("Estadísticas", "Ventas", "$ 1.000,00", "1 entrega concretada", "Entregas a tiempo", "100 %", "Indemnizado", "Cobranza en mora", "Ventas por variedad", "Entregas a tiempo y con retraso",
                         "Incumplimientos aceptados", "Cobranza a la fecha", "Faltantes y rechazos de compra-venta", "Clientes con más compras", "Intentos de entrega fallidos"):
            self.assertIn(esperado, html)
        self.assertNotIn("$ 7.700,00", html)
        self.assertNotIn(self.otro_cliente.nombre_visible, html)
        self.assertNotIn('name="vendedor"', html)  # el Vendedor no filtra por Vendedor

    def test_el_gerente_ve_todo_y_filtra_por_vendedor(self):
        """El Gerente ve lo de todos y tiene el desplegable de Vendedor; filtrando, solo lo del elegido."""
        self.venta(cantidad=10, precio="100.00")
        self.del_otro_vendedor(cantidad=20, precio="100.00")
        todo = texto(self.ir(self.gerente))
        self.assertIn("$ 3.000,00", todo)
        self.assertIn('name="vendedor"', todo)
        solo = texto(self.ir(self.gerente, vendedor=self.otro_vendedor.pk))
        self.assertIn("$ 2.000,00", solo)
        self.assertNotIn("$ 3.000,00", solo)

    def test_cambiar_de_mes_el_rango_y_el_invernadero_cambia_los_numeros(self):
        """Hecho cuando: cambiar el mes, el rango y el invernadero cambia los números; los filtros elegidos quedan seleccionados."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        self.venta(cantidad=10, precio="100.00")  # este mes, Norte
        self.venta(cantidad=20, precio="100.00", hace=HACE_UN_MES, lote=lote_maduro(sur, 5000))  # el mes anterior, Sur
        self.assertIn("$ 1.000,00", texto(self.ir(self.e.vendedor)))
        anterior = texto(self.ir(self.e.vendedor, periodo=PERIODO_ANTERIOR))
        self.assertIn("$ 2.000,00", anterior)
        self.assertIn(f'<option value="{PERIODO_ANTERIOR}" selected>', anterior)
        rango = texto(self.ir(self.e.vendedor, periodo="rango", desde=(HOY - timedelta(days=HACE_UN_MES + 2)).isoformat(), hasta=HOY.isoformat()))
        self.assertIn("$ 3.000,00", rango)
        self.assertIn('<option value="rango" selected>', rango)
        solo_sur = texto(self.ir(self.e.vendedor, periodo="rango", desde=(HOY - timedelta(days=HACE_UN_MES + 2)).isoformat(), hasta=HOY.isoformat(), invernadero=sur.invernadero.pk))
        self.assertIn("$ 2.000,00", solo_sur)
        self.assertNotIn("$ 3.000,00", solo_sur)

    def test_un_filtro_invalido_muestra_el_motivo_y_ningun_numero(self):
        """Un rango de más de un año, un fin futuro o un invernadero ajeno no muestran números: dicen qué corregir (`periodo_invalido`, `invernadero_fuera_de_alcance`)."""
        self.venta(cantidad=10, precio="100.00")
        largo = {"periodo": "rango", "desde": (HOY.replace(year=HOY.year - 2)).isoformat(), "hasta": HOY.isoformat()}
        for get in (largo, {"periodo": "2999-01"}, {"invernadero": "99999999"}):
            respuesta = self.ir(self.e.vendedor, **get)
            self.assertEqual(respuesta.status_code, 200, get)
            html = texto(respuesta)
            self.assertIn("Corregí el filtro para ver las estadísticas.", html)
            self.assertNotIn("$ 1.000,00", html)
        self.assertIn("El período no puede ser mayor que un año.", texto(self.ir(self.e.vendedor, **largo)))
        self.assertIn("Ver estadísticas", texto(self.ir(self.e.vendedor, **largo)))  # y los filtros siguen ahí para corregirlos

    def test_el_vendedor_que_manda_vendedor_por_la_url_ve_el_motivo(self):
        """`vendedor_no_admitido`: el Vendedor no filtra por Vendedor; la pantalla lo dice."""
        html = texto(self.ir(self.e.vendedor, vendedor=self.otro_vendedor.pk))
        self.assertIn("Corregí el filtro para ver las estadísticas.", html)

    def test_con_htmx_devuelve_solo_el_cuerpo_y_sin_javascript_la_pagina_entera(self):
        """Con HTMX se redibuja solo el cuerpo (sin menú ni filtros); sin JavaScript, la página completa con el formulario GET y «Ver estadísticas»."""
        self.venta()
        self.client.force_login(self.e.vendedor)
        parcial = texto(self.client.get(reverse("comercial:estadisticas"), HTTP_HX_REQUEST="true"))
        self.assertIn("Ventas por variedad", parcial)
        self.assertNotIn("<form", parcial)
        self.assertNotIn("<html", parcial)
        entera = texto(self.client.get(reverse("comercial:estadisticas")))
        self.assertIn('<form class="filters est-filtros" method="get"', entera)
        self.assertIn("Ver estadísticas", entera)
        self.assertIn('name="desde"', entera)  # sin JavaScript, el rango está siempre a la vista

    def test_los_textos_explicativos_y_las_barras_con_su_monto_escrito(self):
        """Textos explicativos siempre, y las barras de «Ventas por variedad» son HTML y CSS con el monto en texto (no solo el color)."""
        self.venta(cantidad=10, precio="100.00")
        html = texto(self.ir(self.e.vendedor))
        for esperado in (
            "Las ventas se cuentan cuando se concreta la entrega y no descuentan indemnizaciones. La cobranza es la situación de hoy.",
            "A tiempo es en la fecha prometida al cliente o antes (la pactada o la del período), aunque la entrega se haya reprogramado.",
            "Quejas y discrepancias que el Gerente aceptó en el período. Las anuladas no cuentan.",
            "Productos de compra-venta que no se pudieron entregar completos o que el cliente no aceptó.",
            'class="hbar"',
            "En mora hasta 30 días",
        ):
            self.assertIn(esperado, html)
        self.assertIn("100.0%", html)  # la barra de la única variedad ocupa todo el ancho
        self.assertNotIn("Vencida", html)  # MD-139: «en mora»

    def test_sin_datos_dice_que_no_hay_ventas(self):
        """Estado vacío: «Sin ventas en el período.» en las variedades y en los clientes, y los totales en cero."""
        html = texto(self.ir(self.e.vendedor))
        self.assertEqual(html.count("Sin ventas en el período."), 2)
        self.assertIn("$ 0,00", html)

    def test_la_pestana_estadisticas_esta_en_comercial_y_no_en_el_menu(self):
        """Estadísticas es una pestaña de Comercial (la última), no una entrada del menú lateral."""
        html = texto(self.ir(self.e.vendedor))
        self.assertIn(f'href="{reverse("comercial:estadisticas")}" aria-selected="true">Estadísticas', html)
        self.assertNotIn(f'<a class="nav-item" href="{reverse("comercial:estadisticas")}"', html)
        self.assertIn(f'href="{reverse("comercial:estadisticas")}" aria-selected="false">Estadísticas', texto(self.client.get(reverse("comercial:entregas"))))

    def test_regla_10_los_enlaces_de_cada_indicador_llevan_el_filtro(self):
        """Regla 10: cada indicador lleva a su consulta con el mismo filtro; esas consultas existen y responden con el filtro puesto."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        self.venta(cantidad=10, precio="100.00")
        discrepancia_aceptada(self.suministro(), monto="100.00", con_alerta=False)
        html = texto(self.ir(self.gerente, vendedor=self.e.vendedor.pk, invernadero=sur.invernadero.pk))
        contratos = reverse("comercial:contratos")
        for enlace in (
            f'href="{contratos}?vendedor={self.e.vendedor.pk}"',
            f'href="{contratos}?tipo=suministro&vendedor={self.e.vendedor.pk}"',
            f'href="{reverse("comercial:entregas")}?estado=concretada&invernadero={sur.invernadero.pk}"',
            f'href="{reverse("comercial:solicitudes")}?estado=aceptada&vendedor={self.e.vendedor.pk}"',
            f'href="{reverse("comercial:cobranza")}"',
        ):
            self.assertIn(enlace, html)
        con_cliente = texto(self.ir(self.gerente))
        self.assertIn(f'href="{contratos}?cliente={self.e.cliente.pk}"', con_cliente)
        for url in (f"{contratos}?vendedor={self.e.vendedor.pk}", f"{contratos}?tipo=suministro&vendedor={self.e.vendedor.pk}", f"{reverse('comercial:entregas')}?estado=concretada", f"{reverse('comercial:solicitudes')}?estado=aceptada", reverse("comercial:cobranza")):
            self.assertEqual(self.client.get(url, follow=True).status_code, 200, url)

    def test_ningun_enlace_lleva_a_un_403(self):
        """D-30: el Vendedor ve las pestañas y enlaces que puede abrir: todos los enlaces de la pantalla responden 200 para él."""
        self.venta()
        self.suministro()
        html = texto(self.ir(self.e.vendedor))

        enlaces = {h for h in re.findall(r'href="(/comercial/[^"#]*)"', html)}
        self.assertTrue(enlaces)
        for url in enlaces:
            self.assertEqual(self.client.get(url, follow=True).status_code, 200, url)


class PanelDeResultadosTests(BaseDeEstadisticas):
    def panel(self, usuario):
        self.client.force_login(usuario)
        return texto(self.client.get("/"))

    def test_el_panel_del_vendedor_muestra_resultados_del_mes_en_curso_con_el_enlace(self):
        """Hecho cuando: el panel del Vendedor muestra «Resultados del mes en curso» (ventas, entregas a tiempo e indemnizado) con el enlace a Estadísticas."""
        self.venta(cantidad=10, precio="100.00", pactada=-1)  # con retraso
        discrepancia_aceptada(self.suministro(), monto="250.00", descontado="250.00", con_alerta=False)
        html = self.panel(self.e.vendedor)
        for esperado in ("(mes en curso)", "Resultados de ", "Ventas", "$ 2.000,00", "2 entregas concretadas en el mes", "Entregas a tiempo", "50 %", "1 con retraso", "Indemnizado", "$ 250,00",
                         "Para otros meses, vea Comercial ›", reverse("comercial:estadisticas")):
            self.assertIn(esperado, html)

    def test_el_panel_del_gerente_no_tiene_resultados_del_mes(self):
        """Hecho cuando: el panel del Gerente no muestra «Resultados del mes en curso»."""
        self.venta()
        html = self.panel(self.gerente)
        self.assertNotIn("(mes en curso)", html)
        self.assertNotIn("Para otros meses, vea Comercial", html)

    def test_los_resultados_del_panel_son_solo_de_los_contratos_del_vendedor(self):
        """El Vendedor sin contratos ve el grupo en cero, no lo del otro Vendedor."""
        self.del_otro_vendedor(cantidad=50, precio="100.00")
        html = self.panel(self.e.vendedor)
        self.assertIn("(mes en curso)", html)
        self.assertNotIn("$ 5.000,00", html)
        self.assertIn("$ 0,00", html)

    def test_el_panel_va_entre_el_grupo_de_entregas_y_el_de_cobranza(self):
        """Posición: «Resultados del mes en curso» queda después de «Entregas» y antes de «Cobranza» (plan de la ronda, sección 5)."""
        self.venta()
        self.suministro()
        html = self.panel(self.e.vendedor)
        self.assertLess(html.index("Entregas"), html.index("(mes en curso)"))
        self.assertLess(html.index("(mes en curso)"), html.index("Por cobrar"))
