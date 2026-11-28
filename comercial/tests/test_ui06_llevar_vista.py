# Pruebas de UI-06 (D-109 punto 9, UX-24) en `comercial`: cada pantalla con resumen lleva `data-llevar-vista` (y `tabindex="-1"`) en el resumen cuando se muestra y en el
# primer error cuando el envío vuelve con errores, y en ningún otro caso (la carga inicial y el redibujo de un selector, regla de INV-02, no lo traen). Acá, cámara y
# cosechas; `infoponia.js` hace el salto (JavaScript: se verifica a mano). Se usan las `Base` y los datos de las pruebas de vista de cada pantalla.

import re

from django.urls import reverse

from django.test import TestCase

from comercial.tests import test_camara_vistas as t_camara
from comercial.tests import test_recorrido_asignar_transportista_y_cancelar_compra_venta as t_cancelacion
from comercial.tests import test_cobranza_vistas as t_cobranza
from comercial.tests import test_compra_ventas_vistas as t_ventas
from comercial.tests import test_confirmacion_vistas as t_confirmacion
from comercial.tests import test_cosechas_vistas as t_cosechas
from comercial.tests import test_envasado_vistas as t_envasado
from comercial.tests import test_faltantes_vistas as t_faltantes
from comercial.tests import test_rutas_vistas as t_rutas
from comercial.tests import test_solicitudes_vistas as t_solicitudes
from comercial.tests import test_suministros_vistas as t_suministros

HTMX = {"HTTP_HX_REQUEST": "true"}
MARCA = re.compile(r"<[^<>]*\bdata-llevar-vista\b[^<>]*>")


class Marcas:
    """Lo que se mira en el HTML: cuántas etiquetas llevan `data-llevar-vista`, cuál es y qué dice."""

    def marcadas(self, respuesta):
        return MARCA.findall(respuesta.content.decode())

    def una_marca(self, respuesta):
        """Exactamente una etiqueta marcada, con `tabindex="-1"` (sin él no recibe el foco); devuelve la etiqueta de apertura."""
        marcadas = self.marcadas(respuesta)
        self.assertEqual(len(marcadas), 1, marcadas)
        self.assertIn('tabindex="-1"', marcadas[0])
        return marcadas[0]

    def resumen_marcado(self, respuesta, rotulo):
        self.assertIn(f'aria-label="{rotulo}"', self.una_marca(respuesta))

    def error_marcado(self, respuesta, texto):
        """La marca está en un error (no en el resumen) y su texto incluye `texto`."""
        marcada = self.una_marca(respuesta)
        self.assertNotIn('role="region"', marcada)
        encontrado = re.search(r"<[^<>]*\bdata-llevar-vista\b[^<>]*>(.*?)</div>", respuesta.content.decode(), re.S)
        self.assertIn(texto, re.sub(r"<[^>]*>", "", encontrado.group(1)))

    def sin_marcas(self, respuesta):
        self.assertEqual(self.marcadas(respuesta), [])


class MermaEnCamaraTests(Marcas, t_camara.Base):
    """COM-04b, `camara/_merma_formulario.html`."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "partida": self.partida.pk}))
        self.sin_marcas(self.client.post(self.url, {"invernadero": self.e.invernadero.pk, "accion": "actualizar"}, **HTMX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, {**self.datos(), "accion": "calcular"}), "Resumen de la merma en cámara")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {**self.datos(cantidad="999"), "accion": "calcular"})
        self.error_marcado(respuesta, "Ingresá un número entero entre 1 y")


class PlanificarCosechaTests(Marcas, t_cosechas.Base):
    """COM-04a, `cosechas/_planificar_formulario.html`: el resumen llega por recarga completa (`formaction`), no por HTMX."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("comercial:cosecha_planificar")
        self.revisar = reverse("comercial:cosecha_planificar_revisar")

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"invernadero": self.e.invernadero.pk}))
        redibujo = self.client.post(reverse("comercial:cosecha_planificar_calcular"), {"invernadero": str(self.e.invernadero.pk), "modo": "contrato"}, **HTMX)
        self.sin_marcas(redibujo)

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.revisar, self.post_de_planificacion()), "Resumen de la cosecha")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.revisar, self.post_de_planificacion(fecha_programada=""))
        self.error_marcado(respuesta, "Ingresá la fecha programada de la cosecha.")

    def test_ui06_cubrir_un_contrato_sin_elegir_el_detalle_muestra_el_error(self):
        """Pantalla que volvía sin mostrar nada: en modo «cubre un contrato» el servicio rechaza en `variedad` («Elegí la variedad de la cosecha.», `cosechas.py:478`) y la
        plantilla solo dibujaba `errores.detalle`. Ahora el error se ve debajo del detalle y lleva la vista. El texto del servicio no cambia."""
        datos = self.post_de_planificacion(modo="contrato", detalle="")
        datos.pop("variedad")
        respuesta = self.client.post(self.revisar, datos)
        self.assertContains(respuesta, "Elegí la variedad de la cosecha.")
        self.error_marcado(respuesta, "Elegí la variedad de la cosecha.")
        self.assertContains(respuesta, 'id="detalle"')


class ModificarYConcretarCosechaTests(Marcas, t_cosechas.Base):
    """COM-04a y COM-04c: modificar (Agrónomo) y concretar (Capataz), ambas con resumen por recarga completa."""

    def post_de_modificacion(self, **extra):
        """Lo que manda el formulario de modificar (el mismo que `ModificarTests` de `test_cosechas_vistas`): fecha, prioridad, el lote y la huella de lo que se vio."""
        datos = {
            "fecha_programada": t_cosechas.iso(5), "prioridad": "media", "descripcion": "", f"lote_{self.lote.pk}": "30",
            "huella": t_cosechas.cosechas.huella_de(self.cosecha),
        }
        datos.update(extra)
        return datos

    def test_ui06_modificar_la_carga_inicial_no_lleva_la_vista(self):
        self.entrar(self.e.agronomo)
        self.sin_marcas(self.client.get(reverse("comercial:cosecha_modificar", args=[self.cosecha.pk])))

    def test_ui06_modificar_el_primer_error_lleva_la_vista(self):
        self.entrar(self.e.agronomo)
        respuesta = self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[self.cosecha.pk]), self.post_de_modificacion(fecha_programada=""))
        self.error_marcado(respuesta, "Ingresá la fecha programada de la cosecha.")

    def test_ui06_concretar_la_carga_inicial_no_lleva_la_vista(self):
        self.entrar(self.e.capataz)
        self.sin_marcas(self.client.get(reverse("comercial:cosecha_concretar", args=[self.cosecha.pk])))


class PortalDeConfirmacionTests(Marcas, t_confirmacion.Base):
    """COM-CNF-ENT (portal público del cliente, sin cuenta), `cliente/confirmacion.html`: el resumen y los errores llegan por recarga completa."""

    def setUp(self):
        super().setUp()
        _, _, token = self.nueva()
        self.abrir(token)  # abre el enlace: la sesión del cliente anónimo queda con la entrega

    def test_ui06_la_carga_inicial_y_el_redibujo_del_bloque_no_llevan_la_vista(self):
        self.sin_marcas(self.anonimo.get(t_confirmacion.PORTAL))
        redibujo = self.anonimo.post(t_confirmacion.PORTAL, {"accion": "redibujar", "respuesta": "conforme"}, **HTMX)
        self.sin_marcas(redibujo)

    def test_ui06_el_resumen_lleva_la_vista(self):
        respuesta = self.anonimo.post(t_confirmacion.PORTAL, {"accion": "revisar", "respuesta": "conforme"})
        self.resumen_marcado(respuesta, "Resumen de su respuesta")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.anonimo.post(t_confirmacion.PORTAL, {"accion": "revisar"})
        self.error_marcado(respuesta, "Indicá si recibiste la entrega.")


class PortalDeFaltantesTests(Marcas, t_faltantes.Base):
    """COM-DCD-FLT (portal público del cliente), `faltantes/_decision.html`."""

    def setUp(self):
        super().setUp()
        self.abrir()

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.anonimo.get(t_faltantes.PORTAL))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.anonimo.post(t_faltantes.PORTAL, self.formulario("aceptar")), "Resumen de la decisión")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        self.error_marcado(self.anonimo.post(t_faltantes.PORTAL, self.formulario(None)), f"Indicá qué hacés con {self.e.variedad}")


class ResolverSolicitudTests(Marcas, t_solicitudes.BaseDeVistas):
    """COM-EVL-DSC, `solicitudes/_resumen.html`: el resumen llega por HTMX (fragmento) o, sin JavaScript, con la ficha entera; el mismo cuadro lleva los errores."""

    def revisar(self, x, **extra):
        datos = {"decision": "aceptar", **extra}
        return self.enviar("solicitud_resolver_revisar", x.solicitud.pk, datos=datos, **(HTMX if self._htmx else {}))

    _htmx = False

    def test_ui06_la_ficha_sin_resumen_no_lleva_la_vista(self):
        x = self.armar()
        self.sin_marcas(self.ir("solicitud", x.solicitud.pk))

    def test_ui06_el_resumen_lleva_la_vista_sin_javascript(self):
        self.una_marca(self.revisar(self.armar()))

    def test_ui06_el_resumen_lleva_la_vista_con_htmx(self):
        self._htmx = True
        self.una_marca(self.revisar(self.armar()))

    def test_ui06_el_resumen_con_errores_tambien_lleva_una_sola_marca(self):
        self.una_marca(self.revisar(self.armar(), decision=""))


class ConcretarEntregaTests(Marcas, t_rutas.Base):
    """COM-CNC-ENT, `rutas/concretar.html` y `rutas/_resumen.html` (el resumen llega por HTMX o, sin JavaScript, con la página entera)."""

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        x = self.concretable()
        self.sin_marcas(self.get(x.transportista, "entrega_concretar", x.entrega.pk))

    def test_ui06_el_resumen_lleva_la_vista_con_htmx_y_sin_javascript(self):
        x = self.concretable()
        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            with self.subTest(extra=extra):
                respuesta = self.post(x.transportista, "entrega_concretar_calcular", self.formulario(x), x.entrega.pk, **extra)
                self.assertIn("Resumen de la concreción", respuesta.content.decode())
                self.una_marca(respuesta)

    def test_ui06_con_errores_una_sola_marca_en_el_primer_error(self):
        x = self.concretable()
        datos = self.formulario(x, **{f"llego_{self.linea(x).pk}": "99"})
        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            with self.subTest(extra=extra):
                respuesta = self.post(x.transportista, "entrega_concretar_calcular", datos, x.entrega.pk, **extra)
                self.assertNotIn("Resumen de la concreción", respuesta.content.decode())
                self.una_marca(respuesta)


class CobranzaTests(Marcas, t_cobranza.BaseDeVistas):
    """COM-REG-COB: el formulario vuelve a dibujarse por HTMX sin validar; «Revisar y registrar» lleva a otra página (el resumen no lleva marca) y, con un error, vuelve al formulario."""

    def test_ui06_la_carga_inicial_y_el_redibujo_no_llevan_la_vista(self):
        e = self.concretada()
        self.sin_marcas(self.ir("cobranza_registrar"))
        self.sin_marcas(self.enviar("cobranza_registrar", datos=self.pedido([e]), HTTP_HX_REQUEST="true"))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        self.sin_marcas(self.enviar("cobranza_revisar", datos=self.pedido([self.concretada()])))

    def test_ui06_el_error_al_revisar_lleva_la_vista(self):
        respuesta = self.enviar("cobranza_revisar", datos=self.pedido([self.concretada()], medio=""))
        self.error_marcado(respuesta, "Elegí el medio de pago.")


class EnvasadoTests(Marcas, t_envasado.Base):
    """COM-05a2: «Revisar» lleva a otra página (sin marca); un error vuelve a la carga con el primer error marcado."""

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        e1 = self.nueva()
        self.entrar()
        self.sin_marcas(self.client.get(self.url_carga(e1)))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        e1 = self.nueva()
        self.entrar()
        self.sin_marcas(self.client.post(self.url_revisar(e1), self.datos(e1, (self.bandeja, 5))))

    def test_ui06_el_error_al_revisar_lleva_la_vista(self):
        e1 = self.nueva()
        self.entrar()
        self.una_marca(self.client.post(self.url_revisar(e1), self.datos(e1)))


class _ConFormularioConResumenEnVentana(Marcas):
    """Compra-venta y suministros: el formulario se redibuja por HTMX sin validar; el resumen se abre en una ventana (no lleva marca: `abrirVentana` ya maneja el foco);
    con un error la respuesta vuelve al formulario, con la vista en el primer error."""

    def entrar(self):
        self.client.force_login(self.e.vendedor)

    def test_ui06_la_carga_inicial_y_el_redibujo_no_llevan_la_vista(self):
        self.entrar()
        self.sin_marcas(self.client.get(self.url_nueva))
        self.sin_marcas(self.client.post(self.url_calcular, self.datos_validos(), **HTMX))

    def test_ui06_el_resumen_en_ventana_no_lleva_marca(self):
        self.entrar()
        respuesta = self.client.post(self.url_revisar, self.datos_validos(), **HTMX)
        self.assertIn("data-ventana", respuesta.content.decode())
        self.sin_marcas(respuesta)

    def test_ui06_el_error_al_revisar_lleva_la_vista_con_htmx_y_sin_javascript(self):
        self.entrar()
        for extra in ({}, HTMX):
            with self.subTest(extra=extra):
                self.una_marca(self.client.post(self.url_revisar, self.datos_validos(cliente=""), **extra))


class CompraVentaTests(_ConFormularioConResumenEnVentana, t_ventas.BaseDeVistas):
    """COM-REG-CVT, `contratos/_cuerpo.html`."""

    url_nueva = property(lambda self: reverse("comercial:compra_venta_nueva"))
    url_calcular = property(lambda self: reverse("comercial:compra_venta_calcular"))
    url_revisar = property(lambda self: reverse("comercial:compra_venta_revisar"))

    def datos_validos(self, **extra):
        return self.post_de_venta(**extra)


class SuministroTests(_ConFormularioConResumenEnVentana, t_suministros.BaseDeVistas):
    """COM-PCT-SUM, `suministros/_cuerpo.html` y `_detalle.html`."""

    url_nueva = property(lambda self: reverse("comercial:suministro_nuevo"))
    url_calcular = property(lambda self: reverse("comercial:suministro_calcular"))
    url_revisar = property(lambda self: reverse("comercial:suministro_revisar"))

    def datos_validos(self, **extra):
        return self.post_de_pacto(**extra)


class CancelarCompraVentaTests(Marcas, t_cancelacion.PlanDeCuentasMixin, t_cancelacion.ConDatosDeInventario, TestCase):
    """COM-CNL-CVT, `contratos/cancelar.html`: el resumen se abre en una ventana (sin marca: `abrirVentana` maneja el foco); sin motivo, el error lleva la vista."""

    def setUp(self):
        self.e = t_cancelacion.escenario_comercial()
        self.lote = t_cancelacion.lote_maduro(self.e, 5000)
        self.addCleanup(t_cancelacion.verificar_invariantes_de_reservas)
        self.addCleanup(t_cancelacion.verificar_invariantes_de_entregas)
        transportista = t_cancelacion.transportista_con_vehiculo(self.e.invernadero, "800")
        self.v = t_cancelacion.venta_con_todo(self.e, transportista=transportista, con_envases=True)
        self.url = reverse("comercial:compra_venta_cancelar", args=[self.v.venta.pk])
        self.revisar = reverse("comercial:compra_venta_cancelar_revisar", args=[self.v.venta.pk])
        self.huella = t_cancelacion.compra_ventas.datos_de_cancelacion(self.e.vendedor, self.v.venta.pk).huella
        self.client.force_login(self.e.vendedor)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url))

    def test_ui06_el_resumen_en_ventana_no_lleva_marca(self):
        respuesta = self.client.post(self.revisar, {"motivo": "cliente_desistio", "descripcion": "Ya no lo necesita", "huella": self.huella}, **HTMX)
        self.assertIn("data-ventana", respuesta.content.decode())
        self.sin_marcas(respuesta)

    def test_ui06_sin_motivo_el_error_lleva_la_vista_con_htmx_y_sin_javascript(self):
        for extra in ({}, HTMX):
            with self.subTest(extra=extra):
                respuesta = self.client.post(self.revisar, {"huella": self.huella}, **extra)
                self.error_marcado(respuesta, "Elegí el motivo de la cancelación.")


class ModificarSuministroTests(Marcas, t_suministros.BaseDeModificacionEnVistas):
    """COM-MOD-SUM, `suministros/_modificar_cuerpo.html`: el resumen se abre en una ventana (sin marca); un envío rechazado lleva la vista al primer error."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.e.vendedor)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url))

    def test_ui06_el_resumen_en_ventana_no_lleva_marca(self):
        respuesta = self.client.post(self.url + "revisar/", self.cambios(), **HTMX)
        self.assertIn("data-ventana", respuesta.content.decode())
        self.sin_marcas(respuesta)

    def test_ui06_un_envio_sin_cambios_lleva_la_vista_al_error_con_htmx_y_sin_javascript(self):
        for extra in ({}, HTMX):
            with self.subTest(extra=extra):
                sin_cambio = self.cambios(**{f"modificar-{self.d.pk}-cantidad": str(self.d.cantidad_por_periodo)})
                self.una_marca(self.client.post(self.url + "revisar/", sin_cambio, **extra))
