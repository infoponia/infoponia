# Pruebas de UI-06 (D-109 punto 9, UX-24) en `iot`: «Emitir comando» (el resumen llega con la página entera; los selectores redibujan sin validar) y «Registrar sistema IoT» (el resumen es
# otra página: no lleva marca; con errores, el primer error). Se usan las bases y los datos de las pruebas de vista.

from django.urls import reverse

from core.tests.marcas_ui06 import Marcas
from iot.tests import test_comandos_vistas as t_comandos
from iot.tests import test_sistemas_vistas as t_sistemas


class EmitirComandoTests(Marcas, t_comandos.ComandosVistasBase):
    """IOT-EMT-CMD, `comandos/_emision.html`."""

    def test_ui06_la_carga_inicial_y_el_redibujo_de_un_selector_no_llevan_la_vista(self):
        self.sin_marcas(self.pagina())
        self.sin_marcas(self.pagina(actuador=self.actuador.pk))
        self.sin_marcas(self.paso("refrescar", accion=self.velocidad, htmx=True))

    def test_ui06_el_resumen_lleva_la_vista(self):
        respuesta = self.paso("resumen")
        self.assertIn("Resumen del comando", respuesta.content.decode())
        self.una_marca(respuesta)
        self.assertEqual(self.texto_marcado(respuesta), "Resumen del comando")

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.paso("resumen", accion=self.velocidad, valor="")
        self.assertNotIn("Resumen del comando", respuesta.content.decode())
        self.una_marca(respuesta)


class RegistrarSistemaTests(Marcas, t_sistemas.SistemaVistasBase):
    """IOT-REG-SIS, `sistema/formulario.html`: «Revisar» lleva a otra página (sin marca); un error vuelve al formulario con el primer error marcado."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.laura)
        self.registrar = reverse("iot:sistema_registrar")

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url("sistema_registrar", invernadero=self.norte)))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.client.post(self.registrar, self.post_del_registro(revisar="1"))
        self.assertContains(respuesta, "Revisá el registro")
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(self.registrar, self.post_del_registro(revisar="1", nombre=""))
        self.una_marca(respuesta)
        self.assertIn("nombre", self.texto_marcado(respuesta).lower())
