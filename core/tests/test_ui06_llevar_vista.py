# Pruebas de UI-06 (D-109 punto 9, UX-24), lo que es de `core`: el JavaScript que lleva la vista y el foco al resumen o al primer error, y la etiqueta
# {% primer_error %} que decide cuál error se marca. Que cada pantalla marque el elemento correcto lo prueba cada app (`<app>/tests/test_ui06_llevar_vista.py`).
# El comportamiento del salto es JavaScript y se verifica a mano; acá, que el código y su versión estén (como las pruebas `test_d29_` de `test_interfaz.py`).

import re
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.tests.fabricas import crear_gerente


def _js():
    return (Path(settings.BASE_DIR) / "core/static/core/js/infoponia.js").read_text(encoding="utf-8")


class LlevarLaVistaScriptTests(TestCase):
    """UI-06, paso 2: `infoponia.js` busca el primer `[data-llevar-vista]` visible y le lleva la vista y el foco."""

    def test_ui06_el_script_busca_el_elemento_marcado_y_le_lleva_la_vista_y_el_foco(self):
        """D-109 punto 9: `scrollIntoView` al principio del elemento y foco sin volver a desplazar (`preventScroll`)."""
        codigo = _js()
        self.assertIn("[data-llevar-vista]", codigo)
        self.assertIn('scrollIntoView({ block: "start"', codigo)
        self.assertIn("focus({ preventScroll: true })", codigo)

    def test_ui06_con_reducir_movimiento_el_salto_es_inmediato(self):
        """D-109 punto 9: sin desplazamiento animado si la persona pidió reducir el movimiento."""
        codigo = _js()
        self.assertIn("(prefers-reduced-motion: reduce)", codigo)
        self.assertRegex(codigo, r'behavior: reducirMovimiento\.matches \? "auto" : "smooth"')

    def test_ui06_se_corre_al_cargar_y_despues_de_cada_intercambio_de_htmx(self):
        """D-109 punto 9: al cargar la página y en cada `htmx:afterSwap`."""
        bloque = _js().split("Llevar la vista al resumen o al primer error")[1]
        self.assertIn("llevarLaVista();", bloque)
        self.assertIn('document.addEventListener("htmx:afterSwap", llevarLaVista)', bloque)

    def test_ui06_no_le_quita_el_foco_a_una_ventana_abierta(self):
        """Una ventana (`data-ventana`) ya tomó el foco con `abrirVentana`: el resumen que se abre en una ventana no lleva el atributo y, si hay una, no se mueve nada."""
        self.assertIn('document.querySelector("[data-ventana]")', _js().split("Llevar la vista al resumen o al primer error")[1])

    def test_ui06_el_script_sigue_pidiendose_con_su_version(self):
        """D-29 (`static_v`): el script que lleva la vista llega al navegador con la fecha del archivo en la URL, con y sin sesión."""
        self.client.force_login(crear_gerente())
        con_sesion = self.client.get(reverse("core:inicio")).content.decode()
        self.client.logout()
        sin_sesion = self.client.get(reverse("core:iniciar_sesion")).content.decode()
        for pagina in (con_sesion, sin_sesion):
            self.assertRegex(pagina, rf"core/{re.escape('js/infoponia.js')}\?v=\d+")

    def test_ui06_el_codigo_nuevo_es_un_bloque_aparte_y_deja_los_anteriores(self):
        """D-109 punto 2: el código nuevo es una función aparte; los bloques de D-29 (avisos, envíos en curso, errores de HTMX) siguen donde estaban."""
        codigo = _js()
        for marca in ("function mostrarAviso(", "function empezar(form, botonClicado)", 'document.addEventListener("htmx:responseError"', "function cerrar(devolverFoco)"):
            self.assertIn(marca, codigo)


class PrimerErrorTests(SimpleTestCase):
    """UI-06, paso 2: {% primer_error errores "a" "b" as primero %} devuelve la primera clave, en el orden de la pantalla, que tiene un error."""

    def _primero(self, errores, *claves):
        argumentos = " ".join(f'"{c}"' for c in claves)
        plantilla = Template('{% load vista %}{% primer_error errores ' + argumentos + ' as primero %}[{{ primero }}]')
        return plantilla.render(Context({"errores": errores}))

    def test_ui06_devuelve_la_primera_clave_en_el_orden_pedido_y_no_la_del_diccionario(self):
        errores = {"fecha_programada": "Indicá la fecha programada.", "cantidad": "La cantidad es obligatoria."}
        self.assertEqual(self._primero(errores, "general", "cantidad", "fecha_programada"), "[cantidad]")

    def test_ui06_el_aviso_general_va_primero_si_lo_hay(self):
        self.assertEqual(self._primero({"general": "Algo pasó.", "cantidad": "x"}, "general", "cantidad"), "[general]")

    def test_ui06_acepta_listas_de_mensajes_y_las_vacias_no_cuentan(self):
        self.assertEqual(self._primero({"general": [], "sensor": ["Seleccioná un sensor."]}, "general", "sensor"), "[sensor]")

    def test_ui06_una_clave_con_asterisco_es_el_error_de_una_fila(self):
        """El error de una fila tiene el id en la clave (`sector_12`): `"sector_*"` encuentra la que empieza así, y el orden de las demás claves se respeta."""
        errores = {"sector_12": "Entre 0 y 5.", "causa": "Indicá la causa."}
        self.assertEqual(self._primero(errores, "general", "sector_*", "causa"), "[sector_12]")
        self.assertEqual(self._primero(errores, "general", "causa", "sector_*"), "[causa]")
        self.assertEqual(self._primero({"sector_12": ""}, "sector_*"), "[]")

    def test_ui06_sin_errores_o_sin_claves_con_error_devuelve_vacio(self):
        self.assertEqual(self._primero(None, "general", "cantidad"), "[]")
        self.assertEqual(self._primero({}, "general", "cantidad"), "[]")
        self.assertEqual(self._primero({"otra": "x"}, "general", "cantidad"), "[]")


class LlevarVistaEtiquetaTests(SimpleTestCase):
    """UI-06, paso 2: {% llevar_vista primero "a" "b" %} pone `data-llevar-vista tabindex="-1"` solo en el error que es el primero."""

    def _error(self, primero, *claves):
        argumentos = " ".join(f'"{c}"' for c in claves)
        plantilla = Template('{% load vista %}<div class="err"{% llevar_vista primero ' + argumentos + ' %}>x</div>')
        return plantilla.render(Context({"primero": primero}))

    def test_ui06_marca_el_error_que_es_el_primero(self):
        self.assertEqual(self._error("cantidad", "cantidad"), '<div class="err" data-llevar-vista tabindex="-1">x</div>')

    def test_ui06_no_marca_los_demas(self):
        self.assertEqual(self._error("cantidad", "fecha_programada"), '<div class="err">x</div>')

    def test_ui06_sin_primero_no_marca_nada(self):
        self.assertEqual(self._error("", "cantidad"), '<div class="err">x</div>')
        self.assertEqual(self._error(None, "cantidad"), '<div class="err">x</div>')

    def test_ui06_el_error_de_una_fila_se_marca_con_su_clave_prefijo_e_ids(self):
        plantilla = Template('{% load vista %}<div class="err"{% llevar_vista_fila primero "reubicacion" lote sector %}>x</div>')
        marcado = plantilla.render(Context({"primero": "reubicacion_4_9", "lote": 4, "sector": 9}))
        otra_fila = plantilla.render(Context({"primero": "reubicacion_4_9", "lote": 4, "sector": 8}))
        self.assertIn("data-llevar-vista", marcado)
        self.assertNotIn("data-llevar-vista", otra_fila)

    def test_ui06_solo_el_primero_que_se_dibuja_lleva_la_marca(self):
        """`llevar_vista_una_vez`: de varios errores en una misma respuesta, solo el primero en orden de pantalla; también dentro de `for` e `include`."""
        plantilla = Template(
            '{% load vista %}{% for m in a %}<p{% llevar_vista_una_vez %}>{{ m }}</p>{% endfor %}'
            '{% if b %}<p{% llevar_vista_una_vez %}>b</p>{% endif %}<p{% llevar_vista_una_vez %}>c</p>'
        )
        html = plantilla.render(Context({"a": ["uno", "dos"], "b": True}))
        self.assertEqual(html.count("data-llevar-vista"), 1)
        self.assertTrue(html.startswith('<p data-llevar-vista tabindex="-1">uno</p>'))

    def test_ui06_si_el_primero_no_se_dibuja_lo_lleva_el_siguiente(self):
        plantilla = Template('{% load vista %}{% if a %}<p{% llevar_vista_una_vez %}>a</p>{% endif %}<p{% llevar_vista_una_vez %}>b</p>')
        self.assertEqual(plantilla.render(Context({"a": False})), '<p data-llevar-vista tabindex="-1">b</p>')

    def test_ui06_en_una_carga_por_get_no_marca_y_en_la_respuesta_a_un_envio_si(self):
        """La carga inicial (GET) no lleva la vista aunque muestre un aviso; la respuesta a un POST sí, y un GET que no marcó no gasta la «única vez»."""
        from django.test import RequestFactory

        plantilla = Template('{% load vista %}<p{% llevar_vista_una_vez %}>x</p>')
        fabrica = RequestFactory()
        self.assertEqual(plantilla.render(Context({"request": fabrica.get("/")})), "<p>x</p>")
        self.assertIn("data-llevar-vista", plantilla.render(Context({"request": fabrica.post("/")})))

    def test_ui06_cada_respuesta_empieza_de_nuevo(self):
        """El estado es del contexto de cada respuesta: dos dibujos seguidos de la misma plantilla marcan uno cada uno."""
        plantilla = Template('{% load vista %}<p{% llevar_vista_una_vez %}>x</p>')
        for _ in range(2):
            self.assertIn("data-llevar-vista", plantilla.render(Context({})))

    def test_ui06_un_cuadro_con_dos_errores_se_marca_con_cualquiera_de_las_dos_claves(self):
        self.assertIn("data-llevar-vista", self._error("sin_insumos", "general", "sin_insumos"))
