# Pruebas de la pestaña «Entregas» de Comercial (COM-05a1, paso 8; docs/casos_de_uso/comercial/entregas.md, «Pantallas»): permisos (el Gerente ve todas, el Vendedor solo las de sus contratos,
# el Agrónomo y el Capataz reciben 403), los filtros (estado, invernadero, transportista y «Sin transportista»), el orden, los parámetros `?entrega=` (la alerta) y `?transportista=` (la
# ficha del invernadero › «Logística»), el respaldo sin JavaScript (formulario GET con «Filtrar») y el fragmento de HTMX, y que la columna de Logística lleva a esta lista. Solo «Ver contrato»
# (D-25). El cliente de Django no ve el CSRF ni el JavaScript: eso va como paso de «navegador real» en la «Verificación a mano».

from datetime import timedelta
from html import unescape

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import Entrega
from comercial.servicios import entregas, vehiculos
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    escenario_comercial,
    reserva_lista,
    segundo_invernadero,
    suministro,
    detalle_suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_vendedor
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()
URL = "comercial:entregas"


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        self.addCleanup(verificar_invariantes_de_entregas)

    def nueva(self, cantidad=100, dias=3, transportista=None, vendedor=None, **opciones):
        venta = compra_venta(self.e, dias=dias, vendedor=vendedor, modalidad=opciones.pop("modalidad", "envio"))
        det = detalle(venta, self.e.variedad, cantidad)
        return venta, entrega(venta, [reserva_lista(det, self.lote, cantidad)], transportista=transportista, **opciones)

    def ver(self, usuario, consulta="", **extra):
        self.client.force_login(usuario)
        return self.client.get(reverse(URL) + consulta, **extra)

    def codigos_en(self, respuesta):
        html = texto(respuesta)
        return sorted(c for c in {e.codigo for e in Entrega.objects.all()} if c in html)


class PermisosTests(Base):
    def test_regla_el_gerente_ve_todas_y_el_vendedor_solo_las_de_sus_contratos(self):
        """Alcance (D-28): el Gerente, todas; el Vendedor, solo las de sus contratos."""
        _, mia = self.nueva(transportista=self.t)
        otro = crear_vendedor(email="otro@infoponia.com")
        _, ajena = self.nueva(transportista=self.t, vendedor=otro)
        self.assertEqual(self.codigos_en(self.ver(self.gerente)), sorted([mia.codigo, ajena.codigo]))
        self.assertEqual(self.codigos_en(self.ver(self.e.vendedor)), [mia.codigo])

    def test_regla_el_agronomo_el_capataz_y_el_transportista_reciben_403(self):
        """SEG-13: solo el Gerente y el Vendedor (el Agrónomo y el Capataz tienen su propio envasado); el Transportista, tampoco."""
        for usuario in (self.e.agronomo, self.e.capataz, self.t):
            with self.subTest(usuario=usuario.rol):
                self.assertEqual(self.ver(usuario).status_code, 403)

    def test_regla_sin_sesion_redirige_al_ingreso_y_solo_acepta_get(self):
        """Toda pantalla exige sesión (`LoginRequiredMiddleware`) y la lista no recibe POST (405)."""
        self.client.logout()
        self.assertEqual(self.client.get(reverse(URL)).status_code, 302)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.post(reverse(URL)).status_code, 405)

    def test_regla_la_pestana_aparece_en_comercial_para_los_dos_roles(self):
        """La pestaña «Entregas» está después de «Contratos» para el Gerente y el Vendedor."""
        for usuario in (self.gerente, self.e.vendedor):
            html = texto(self.ver(usuario))
            self.assertLess(html.index(">Contratos<"), html.index(">Entregas<"))


class FiltrosYOrdenTests(Base):
    def test_regla_por_omision_muestra_solo_las_a_realizar(self):
        """Filtro de estado: «A realizar» por omisión; «Concretadas», «Canceladas» y «Todos los estados» (vacío) lo cambian."""
        _, a = self.nueva(transportista=self.t)
        _, c = self.nueva(transportista=self.t, estado="concretada")
        _, x = self.nueva(transportista=self.t, estado="cancelada")
        self.assertEqual(self.codigos_en(self.ver(self.gerente)), [a.codigo])
        self.assertEqual(self.codigos_en(self.ver(self.gerente, "?estado=concretada")), [c.codigo])
        self.assertEqual(self.codigos_en(self.ver(self.gerente, "?estado=cancelada")), [x.codigo])
        self.assertEqual(self.codigos_en(self.ver(self.gerente, "?estado=")), sorted([a.codigo, c.codigo, x.codigo]))

    def test_regla_el_orden_es_sin_transportista_primero_despues_fecha_e_id(self):
        """Orden: primero las de envío sin transportista, después fecha programada, después id."""
        _, tarde = self.nueva(transportista=self.t, dias=6)
        _, sin = self.nueva(dias=9)
        _, pronto = self.nueva(transportista=self.t, dias=2)
        html = texto(self.ver(self.gerente))
        self.assertEqual(sorted([sin.codigo, pronto.codigo, tarde.codigo], key=html.index), [sin.codigo, pronto.codigo, tarde.codigo])

    def test_regla_el_filtro_de_transportista_incluye_sin_transportista(self):
        """Filtro de transportista por id y «Sin transportista» (`_`): un retiro no cuenta como sin transportista."""
        otro = transportista_con_vehiculo(self.e.invernadero, "800")
        _, con = self.nueva(transportista=self.t)
        _, de_otro = self.nueva(transportista=otro)
        _, sin = self.nueva()
        _, retiro = self.nueva(modalidad="retiro")
        self.assertEqual(self.codigos_en(self.ver(self.gerente, f"?transportista={self.t.pk}")), [con.codigo])
        self.assertEqual(self.codigos_en(self.ver(self.gerente, "?transportista=_")), [sin.codigo])
        self.assertEqual(self.codigos_en(self.ver(self.gerente, "?transportista=")), sorted([con.codigo, de_otro.codigo, sin.codigo, retiro.codigo]))

    def test_regla_el_filtro_de_invernadero_solo_aparece_con_mas_de_uno(self):
        """«Invernadero (si el actor tiene más de uno en sus contratos)»: con uno solo no hay selector; con dos, sí, y filtra."""
        _, norte = self.nueva(transportista=self.t)
        self.assertNotIn('name="invernadero"', texto(self.ver(self.gerente)))
        sur = segundo_invernadero(self.e)
        transportista_con_vehiculo(sur.invernadero, "800")
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 10)
        en_sur = entrega(venta, [reserva_lista(det, lote_maduro(sur, 100), 10)])
        respuesta = self.ver(self.gerente)
        self.assertIn('name="invernadero"', texto(respuesta))
        self.assertEqual(self.codigos_en(self.ver(self.gerente, f"?invernadero={sur.invernadero.pk}")), [en_sur.codigo])
        self.assertEqual(self.codigos_en(self.ver(self.gerente, f"?invernadero={self.e.invernadero.pk}")), [norte.codigo])

    def test_regla_los_valores_mal_formados_se_ignoran(self):
        """Un id que no es número, un estado desconocido o una página inexistente no dan error: se ignoran."""
        _, a = self.nueva(transportista=self.t)
        self.assertEqual(self.ver(self.gerente, "?invernadero=abc&transportista=x&entrega=zz&pagina=999").status_code, 200)
        self.assertEqual(self.codigos_en(self.ver(self.gerente, "?estado=inventado")), [a.codigo])


class ParametrosTests(Base):
    def test_ext_d62_entrega_filtra_esa_fila_aunque_no_este_a_realizar(self):
        """`?entrega=<id>` (la alerta): muestra solo esa entrega, en cualquier estado (no aplica el «A realizar» por omisión)."""
        _, otra = self.nueva(transportista=self.t)
        _, cancelada = self.nueva(transportista=self.t, estado="cancelada")
        self.assertEqual(self.codigos_en(self.ver(self.gerente, f"?entrega={cancelada.pk}")), [cancelada.codigo])

    def test_ext_d62_el_enlace_de_la_alerta_lleva_a_la_fila_y_no_a_un_403(self):
        """El enlace de la campana del Gerente abre la lista en esa entrega."""
        venta, e = self.nueva()
        alerta = entregas._alerta_sin_transportista(e, venta, "capacidad de carga insuficiente")
        url = entregas.enlaces_de_alertas(self.gerente, [alerta])[alerta.pk].url
        self.client.force_login(self.gerente)
        respuesta = self.client.get(url)
        self.assertEqual((respuesta.status_code, self.codigos_en(respuesta)), (200, [e.codigo]))

    def test_regla_logistica_su_columna_lleva_a_la_lista_filtrada_por_transportista(self):
        """`url_entregas` de «Logística» (`?transportista=<id>`) abre la lista con las «a realizar» de ese transportista."""
        _, mia = self.nueva(transportista=self.t)
        otro = transportista_con_vehiculo(self.e.invernadero, "800")
        self.nueva(transportista=otro)
        url = vehiculos.logistica_de_transportistas([self.t])[self.t.pk].url_entregas
        self.client.force_login(self.gerente)
        self.assertEqual(self.codigos_en(self.client.get(url)), [mia.codigo])


class ContenidoTests(Base):
    def test_regla_las_columnas_dicen_destino_contenido_peso_fecha_y_estado(self):
        """Columnas: entrega y contrato, cliente y destino con el contenido, fecha («mañana»), peso, transportista y estado; solo «Ver contrato»."""
        venta, e = self.nueva(100, dias=1, transportista=self.t)
        html = texto(self.ver(self.gerente))
        for esperado in (e.codigo, venta.codigo, venta.cliente.nombre_visible, "100 ", "mañana", "15,00 kg", self.t.get_full_name(), "A realizar", "Ver contrato"):
            self.assertIn(esperado, html)
        self.assertIn(reverse("comercial:compra_venta", args=[venta.pk]), html)
        for ausente in ("Asignar transportista", "Cambiar transportista", "Concretar retiro", "Vencida"):
            self.assertNotIn(ausente, html)

    def test_regla_una_entrega_atrasada_se_marca_atrasada_en_rojo(self):
        """MD-139: «Atrasada · hace 2 días» (nunca «vencida»), en la clase de peligro."""
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 10)
        entrega(venta, [reserva_lista(det, self.lote, 10)], fecha=HOY - timedelta(days=2), transportista=self.t)
        html = texto(self.ver(self.gerente))
        self.assertIn("Atrasada · hace 2 días", html)
        self.assertIn('class="sub2 danger-t"', html)

    def test_regla_un_retiro_dice_no_corresponde_y_sin_transportista_va_en_rojo(self):
        """Transportista: «No corresponde» en un retiro; «Sin transportista» destacado en un envío sin transportista; el destino de un retiro es el invernadero."""
        _, retiro = self.nueva(modalidad="retiro")
        _, sin = self.nueva()
        html = texto(self.ver(self.gerente))
        self.assertIn("No corresponde", html)
        self.assertIn("Retiro en " + str(self.e.invernadero), html)
        self.assertIn('status-badge status-danger">Sin transportista', html)

    def test_regla_una_entrega_de_suministro_lleva_a_la_ficha_del_suministro(self):
        """«Ver contrato» de una entrega de suministro abre el suministro."""
        s = suministro(self.e)
        d = detalle_suministro(s, self.e.variedad, cantidad=20, primera_en_dias=3)
        entrega(s, [reserva_lista(None, self.lote, 20, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d)], transportista=self.t)
        self.assertIn(reverse("comercial:suministro", args=[s.pk]), texto(self.ver(self.gerente)))

    def test_regla_sin_entregas_el_vacio_se_explica(self):
        """Vacío: con filtros, «No hay entregas con estos filtros.»; sin filtros, el motivo."""
        self.assertIn("No hay entregas a realizar.", texto(self.ver(self.gerente)))
        self.assertIn("No hay entregas con estos filtros.", texto(self.ver(self.gerente, "?estado=cancelada")))

    def test_regla_el_texto_explicativo_esta_arriba(self):
        """Texto explicativo de `tabEntregas`."""
        self.assertIn("InfoPonia planifica las entregas solo, cuando todo el producto de una venta o de un período está listo.", texto(self.ver(self.gerente)))

    def test_regla_una_pagina_no_hace_consultas_por_fila(self):
        """Una consulta por tabla para toda la página: con 6 entregas más no suben las consultas."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.nueva(transportista=self.t)
        self.ver(self.gerente)
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(reverse(URL))
        for _ in range(6):
            self.nueva(transportista=self.t)
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(reverse(URL))
        self.assertEqual(len(pocas), len(muchas))

    def test_regla_se_pagina_de_a_50(self):
        """Páginas de 50 con «Siguiente» que conserva los filtros."""
        for _ in range(51):
            self.nueva(cantidad=1)
        html = texto(self.ver(self.gerente, "?estado=a_realizar"))
        self.assertIn("Página 1 de 2", html)
        self.assertIn("estado=a_realizar&pagina=2", html)
        self.assertIn("Página 2 de 2", texto(self.ver(self.gerente, "?estado=a_realizar&pagina=2")))


class RespaldoSinJavaScriptYHtmxTests(Base):
    def test_regla_sin_javascript_el_formulario_es_un_get_con_filtrar(self):
        """Respaldo: el formulario es un GET común con el botón «Filtrar» (sin JavaScript funciona igual)."""
        html = texto(self.ver(self.gerente))
        self.assertIn('method="get"', html)
        self.assertIn(">Filtrar<", html)

    def test_regla_con_htmx_devuelve_solo_la_tabla(self):
        """Con `HX-Request` devuelve el fragmento de la tabla (no la página entera) y varía por ese encabezado."""
        _, e = self.nueva(transportista=self.t)
        respuesta = self.ver(self.gerente, **HTMX)
        html = texto(respuesta)
        self.assertIn(e.codigo, html)
        self.assertNotIn("<html", html)
        self.assertIn("HX-Request", respuesta.headers["Vary"])
        self.assertIn("no-cache", respuesta.headers["Cache-Control"])
