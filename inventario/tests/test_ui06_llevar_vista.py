# Pruebas de UI-06 (D-109 punto 9, UX-24) en `inventario`: «Ajustar stock» (el resumen llega por HTMX, `#ajuste-vivo`) y «Nueva variedad» (el resumen es otra página: no lleva marca;
# con errores, el aviso general). Cada pantalla marca el resumen o el primer error al volver de un envío y en ningún otro caso. Se usan las bases y los datos de las pruebas de vista.

from django.urls import reverse

from core.tests.marcas_ui06 import Marcas
from inventario.tests import test_ajuste_vistas as t_ajuste
from inventario.tests import test_variedades_vistas as t_variedades

HX = {"HTTP_HX_REQUEST": "true"}


class AjusteDeStockTests(Marcas, t_ajuste.AjusteVistaBase):
    """CMP-AJT-STK, `ajuste/_formulario.html`."""

    def carga(self, **campos):
        return self.datos("carga_inicial", cantidad="30", vencimiento=t_ajuste.en(40).isoformat(), **campos)

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(self.ruta))
        self.sin_marcas(self.client.get(self.ruta, {"invernadero": self.invernadero.pk, "insumo": self.nutriente.pk, "motivo": "carga_inicial"}))
        self.sin_marcas(self.client.post(self.ruta, self.datos("carga_inicial", accion="actualizar"), **HX))

    def test_ui06_el_resumen_lleva_la_vista_con_htmx_y_sin_javascript(self):
        for extra in ({}, HX):
            with self.subTest(extra=extra):
                respuesta = self.client.post(self.ruta, self.carga(), **extra)
                self.assertIn("Qué se va a registrar", respuesta.content.decode())
                self.assertIn("card recap", self.una_marca(respuesta))

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.ruta, self.datos("carga_inicial", cantidad="", vencimiento=t_ajuste.en(40).isoformat()), **HX)
        self.assertNotIn("Qué se va a registrar", respuesta.content.decode())
        self.una_marca(respuesta)
        self.assertIn("cantidad", self.texto_marcado(respuesta).lower())


class NuevaVariedadTests(Marcas, t_variedades.VistasDeVariedadesBase):
    """PROD-ALT-VAR, `variedades/formulario.html`: «Revisar resumen» lleva a otra página (sin marca); un error vuelve al formulario con el aviso general marcado."""

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url_nueva()))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.enviar(self.url_nueva(), t_variedades.datos_validos(), "revisar")
        self.assertContains(respuesta, "Resumen de la nueva variedad")
        self.sin_marcas(respuesta)

    def test_ui06_el_error_lleva_la_vista_en_el_aviso_general(self):
        respuesta = self.enviar(self.url_nueva(), t_variedades.datos_validos(nombre=""), "revisar")
        self.una_marca(respuesta)
        self.assertEqual(self.texto_marcado(respuesta), "Revisá los campos marcados.")
