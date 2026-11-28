# Pruebas de UI-06 (D-109 punto 9, UX-24) en `contabilidad`: «Registrar asiento» lleva a una página de resumen (sin marca); un envío con errores vuelve con el primer error marcado y la
# carga inicial no lleva nada. Se usan la base y los datos de las pruebas de vista de asientos.

from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from contabilidad.tests import test_asientos_vistas as t_asientos
from contabilidad.tests import test_libro_vistas as t_libro
from contabilidad.tests import test_recorrido_iniciar_ejercicio as t_inicio
from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.tests.marcas_ui06 import Marcas


class RegistrarAsientoTests(Marcas, t_asientos.VistaDeAsientosBase):
    """CON-REG-ASI, `asiento_nuevo.html` y `_asiento_formulario.html`."""

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.get(self.contador, t_asientos.NUEVO))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.post(self.contador, t_asientos.NUEVO, t_asientos._form(accion="revisar"))
        self.assertContains(respuesta, "Revisar el asiento")
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.post(self.contador, t_asientos.NUEVO, t_asientos._form(descripcion="", accion="revisar"))
        self.una_marca(respuesta)
        self.assertIn("descripción", self.texto_marcado(respuesta).lower())


class ContraasientoTests(Marcas, t_asientos.VistaDeAsientosBase):
    """CON-CTR-ASI, `contraasiento.html`: el resumen es otra página (sin marca); un error lleva la vista al primer error."""

    def setUp(self):
        super().setUp()
        self.original = t_asientos.asiento_de_prueba(self.abierto, t_asientos.datetime.date(2027, 2, 1), t_asientos.MOVIMIENTOS, descripcion="Pago de la luz")
        self.url = reverse("contabilidad:contraasiento", args=[self.abierto.pk, self.original.numero_asiento])

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.get(self.contador, self.url))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.post(self.contador, self.url, {"fecha": "2027-03-10", "motivo": "Importe de más", "accion": "revisar"})
        self.assertEqual(respuesta.status_code, 200)
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.post(self.contador, self.url, {"fecha": "2027-03-10", "motivo": "", "accion": "revisar"})
        self.una_marca(respuesta)
        self.assertIn("motivo", self.texto_marcado(respuesta).lower())


class IniciarEjercicioTests(Marcas, PlanDeCuentasMixin, TestCase):
    """CON-INI-EJE, `iniciar.html` y `_iniciar_formulario.html`: el resumen es la página entera (sin marca); un error lleva la vista al primer error."""

    def setUp(self):
        cache.clear()
        mock.patch("django.utils.timezone.localdate", return_value=t_inicio.HOY).start()
        self.addCleanup(mock.patch.stopall)
        self.contador = t_inicio.crear_cuenta(t_inicio.Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.client.force_login(self.contador)

    def test_ui06_la_carga_inicial_y_calcular_el_cierre_no_llevan_la_vista(self):
        self.sin_marcas(self.client.get(t_inicio.INICIAR))
        self.sin_marcas(self.client.post(t_inicio.INICIAR, {**t_inicio._apertura(), "accion": "calcular"}, **t_inicio.HTMX))

    def test_ui06_el_resumen_es_otra_pagina_y_no_lleva_marca(self):
        respuesta = self.client.post(t_inicio.INICIAR, {**t_inicio._apertura(), "accion": "revisar"})
        self.assertContains(respuesta, "Revisá el inicio")
        self.sin_marcas(respuesta)

    def test_ui06_el_primer_error_lleva_la_vista(self):
        respuesta = self.client.post(t_inicio.INICIAR, {**t_inicio._apertura(fecha_inicio=""), "accion": "revisar"})
        self.una_marca(respuesta)


class CerrarEjercicioTests(Marcas, t_libro.VistaBase):
    """CON-CRR-EJE, `cierre.html`: la página es el resumen (sin marca); enviar sin confirmar lleva la vista al error."""

    def setUp(self):
        super().setUp()
        self.abierto.delete()
        self.cerrado.delete()
        self.en_cierre = t_libro.ejercicio(t_libro.Estado.EN_CIERRE, t_libro.datetime.date(2026, 1, 1))
        self.url = reverse("contabilidad:cierre", args=[self.en_cierre.pk])
        self.client.force_login(self.contador)

    def test_ui06_la_carga_inicial_no_lleva_la_vista(self):
        self.sin_marcas(self.client.get(self.url))

    def test_ui06_enviar_sin_confirmar_lleva_la_vista_al_error(self):
        respuesta = self.client.post(self.url, {})
        self.una_marca(respuesta)
        self.assertIn("Confirmá que revisaste el libro", self.texto_marcado(respuesta))
