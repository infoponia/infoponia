# Pruebas de UI-06 (D-109 punto 9, UX-24) en `produccion`: cada pantalla con resumen lleva `data-llevar-vista` (y `tabindex="-1"`) en el resumen cuando se muestra
# y en el primer error cuando el envío vuelve con errores, y en ningún otro caso: la carga inicial y el redibujo de un selector (accion «actualizar», regla de INV-02)
# no traen el atributo. `infoponia.js` le lleva la vista y el foco (`core/tests/test_ui06_llevar_vista.py`); eso es JavaScript y se verifica a mano.
# Los datos y los POST válidos son los de las pruebas de vista de cada pantalla (se usan sus `Base`).

import re
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from produccion.tests import test_eventos_vistas as t_eventos
from produccion.tests import test_fds_vistas as t_fds
from produccion.tests import test_prod_reg_lte_vistas as t_lte
from produccion.tests import test_produccion_vistas as t_prod
from produccion.tests import test_transicion_vistas as t_trans
from produccion.tests.fabricas import orden_de_siembra
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HX = {"HTTP_HX_REQUEST": "true"}
MARCA = re.compile(r"<[^<>]*\bdata-llevar-vista\b[^<>]*>")


def hoy():
    return timezone.localdate()


class Marcas:
    """Lo que se mira en el HTML: cuántas etiquetas llevan `data-llevar-vista`, cuál es y qué dice."""

    def marcadas(self, respuesta):
        return MARCA.findall(respuesta.content.decode())

    def una_marca(self, respuesta):
        """Exactamente una etiqueta marcada; devuelve esa etiqueta de apertura."""
        marcadas = self.marcadas(respuesta)
        self.assertEqual(len(marcadas), 1, marcadas)
        self.assertIn('tabindex="-1"', marcadas[0])  # sin tabindex el elemento no puede recibir el foco
        return marcadas[0]

    def texto_del_error_marcado(self, respuesta):
        """El texto del error que lleva la marca (`<div class="err"…>texto</div>`), sin etiquetas."""
        html = respuesta.content.decode()
        encontrado = re.search(r"<[^<>]*\bdata-llevar-vista\b[^<>]*>(.*?)</div>", html, re.S)
        self.assertIsNotNone(encontrado)
        return re.sub(r"<[^>]*>", "", encontrado.group(1)).strip()

    def resumen_marcado(self, respuesta, rotulo):
        """La marca está en el resumen (`role="region"` con su rótulo), y no en un error."""
        self.assertIn(f'aria-label="{rotulo}"', self.una_marca(respuesta))

    def error_marcado(self, respuesta, texto):
        """La marca está en un error (no en el resumen) y es el que dice `texto`."""
        marcada = self.una_marca(respuesta)
        self.assertNotIn('role="region"', marcada)
        self.assertIn(texto, self.texto_del_error_marcado(respuesta))

    def sin_marcas(self, respuesta):
        self.assertEqual(self.marcadas(respuesta), [])


class NuevaSiembraTests(Marcas, t_prod.Base):
    """PROD-PNF-SMB, `_nueva_siembra_formulario.html`."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:nueva_siembra")

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        """D-109 punto 9 y regla de INV-02: sin resumen ni errores no hay marca; elegir el invernadero o la variedad (HTMX) solo redibuja campos."""
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk}))
        for datos in ({"invernadero": self.e.invernadero.pk}, {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk}):
            self.sin_marcas(self.client.post(self.url, {**datos, "accion": "actualizar"}, **HX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, {**self.datos_de_siembra(), "accion": "calcular"}), "Resumen de la orden")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {**self.datos_de_siembra(cantidad="0"), "accion": "calcular"})
        self.error_marcado(respuesta, "La cantidad de plantines tiene que ser un número entero mayor que cero.")
        self.assertNotContains(respuesta, "Resumen de la orden")


class LoteExistenteTests(Marcas, t_lte.Base):
    """PROD-REG-LTE, `_lote_existente_formulario.html`."""

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        datos = {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa()}
        self.sin_marcas(self.client.get(self.url, datos))
        self.sin_marcas(self.client.post(self.url, {**datos, "accion": "actualizar"}, **HX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.calcular(), "Resumen del lote")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        self.error_marcado(self.calcular(cantidad="0"), "La cantidad de plantas tiene que ser un número entero mayor que cero.")


class NuevaTransicionTests(Marcas, t_trans.Base):
    """PROD-PNF-TRN, `_nueva_transicion_formulario.html`."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:nueva_transicion")

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"lote": self.lote.pk}))
        self.sin_marcas(self.client.post(self.url, {"accion": "actualizar", "lote": self.lote.pk, "cantidad_vista": "", "fecha_programada": ""}, **HX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, {**self.nueva(), "accion": "calcular"}), "Resumen de la transición")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {**self.nueva(fecha_programada=""), "accion": "calcular"})
        self.error_marcado(respuesta, "Indicá la fecha programada.")


class ConcretarSiembraTests(Marcas, t_prod.Base):
    """PROD-CNC-SMB, `concretar.html` (la pantalla del Capataz en el celular)."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        super().setUp()
        self.orden = orden_de_siembra(self.e, plantines=40)
        self.entrar(self.e.capataz)
        self.url = reverse("produccion:concretar", args=[self.orden.pk])
        self.sector = self.e.sectores["germinacion"].pk

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url))

    def test_ui06_el_resumen_lleva_la_vista(self):
        datos = {"fecha_efectiva": hoy().isoformat(), f"sembrado_{self.sector}": "35", "motivo_diferencia": "Faltó turba", "accion": "calcular"}
        self.resumen_marcado(self.client.post(self.url, datos), "Resumen de la concreción")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {f"sembrado_{self.sector}": "99", "accion": "calcular"})
        self.assertEqual(len(self.marcadas(respuesta)), 1)
        self.assertNotIn('role="region"', self.una_marca(respuesta))


class ConcretarTransicionTests(Marcas, t_trans.Base):
    """PROD-CNC-TRN, `concretar_transicion.html`."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        super().setUp()
        self.orden = t_trans.orden_de_transicion(self.e, self.lote)
        self.url = reverse("produccion:concretar", args=[self.orden.pk])
        self.entrar(self.e.capataz)

    def datos(self, **cambios):
        datos = {"fecha_efectiva": hoy().isoformat(), "cantidad_vista": "50", f"ubicadas_{self.destino.pk}": "", "causa": "", "descripcion": "", "accion": "calcular"}
        datos.update(cambios)
        return datos

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, self.datos()), "Resumen de la concreción")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        """Con plantas sin ubicar el resumen se rechaza pidiendo la causa (extensión 10a): el error lleva la marca y no hay resumen."""
        respuesta = self.client.post(self.url, self.datos(**{f"ubicadas_{self.destino.pk}": "40"}))
        self.assertNotIn('role="region"', self.una_marca(respuesta))


class MermaTests(Marcas, t_eventos.Base):
    """PROD-REG-MRM, `_merma_formulario.html`."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:registrar_merma")

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"invernadero": self.e.invernadero.pk, "lote": self.lote.pk}))
        self.sin_marcas(self.client.post(self.url, {"invernadero": self.e.invernadero.pk, "accion": "actualizar"}, **HX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, {**self.merma(), "accion": "calcular"}), "Resumen de la merma")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {**self.merma(**{f"cant_{self.sector.pk}": "0"}), "accion": "calcular"})
        self.error_marcado(respuesta, "La merma debe ser de al menos una planta.")


class AplicacionTests(Marcas, t_eventos.Base):
    """PROD-REG-APL, `_aplicacion_formulario.html`."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:registrar_aplicacion")

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"invernadero": self.e.invernadero.pk}))
        self.sin_marcas(self.client.post(self.url, {"invernadero": self.e.invernadero.pk, "accion": "actualizar"}, **HX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, {**self.aplicacion(), "accion": "calcular"}), "Resumen de la aplicación")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {**self.aplicacion(**{f"cantidad_{self.abono.pk}": ""}), "accion": "calcular"})
        self.error_marcado(respuesta, "Indicá al menos un insumo.")


class FueraDeServicioTests(Marcas, t_fds.Base):
    """PROD-PNR-FDS, `_fuera_de_servicio_formulario.html`."""

    url = property(lambda self: reverse(t_fds.URL))

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.url))
        self.sin_marcas(self.client.get(self.url, {"sector": self.germ.pk}))
        self.sin_marcas(self.client.post(self.url, {"sector": self.germ.pk, "accion": "actualizar"}, **HX))

    def test_ui06_el_resumen_lleva_la_vista(self):
        self.resumen_marcado(self.client.post(self.url, {**self.datos(), "accion": "calcular"}), "Resumen de la puesta fuera de servicio")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.url, {**self.datos(motivo=""), "accion": "calcular"})
        self.error_marcado(respuesta, "Indicá el motivo.")
