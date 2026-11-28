# Pruebas de UI-06, paso 3 (D-109 punto 9, UX-27) en `inventario`: «Habilitar insumo», enviada vacía, marca los cuatro obligatorios a la vez (antes la vista solo marcaba el insumo y el invernadero,
# porque no llama al servicio hasta que están elegidos). Los textos de mínimo y precio son los del servicio (`insumos_invernadero.py`). Es una ventana: `abrirVentana` maneja el foco y por eso
# no lleva `data-llevar-vista`. Abrirla con los campos vacíos no muestra errores. No cambia ningún servicio.

from django.urls import reverse

from core.tests.obligatorios_ui06 import ObligatoriosJuntos
from inventario.tests import test_existencias_vistas as t_existencias

HX = {"HTTP_HX_REQUEST": "true"}


class HabilitarInsumoTests(ObligatoriosJuntos, t_existencias.ExistenciasBase):
    """CMP-HAB-IIN, `existencias/_ventana_habilitar.html`."""

    def enviar(self, vacios, espacios=frozenset()):
        datos = {"insumo": self.nutriente.pk, "invernadero": self.invernadero.pk, "cant_min": "5", "referencia_precio": "10"}
        datos.update({campo: ("   " if campo in espacios else "") for campo in vacios})
        return self.client.post(reverse("inventario:habilitar"), datos, **HX)

    def test_ui06_enviada_vacia_marca_insumo_invernadero_minimo_y_precio(self):
        self.comprobar_obligatorios_juntos(
            self.enviar, ("insumo", "invernadero", "cant_min", "referencia_precio"), espacios=("cant_min", "referencia_precio"), con_marca=False
        )

    def test_ui06_abrir_la_ventana_con_los_campos_vacios_no_muestra_errores(self):
        """No hay selector que redibuje: lo más cercano es abrirla (GET), con o sin el insumo ya elegido."""
        self.sin_errores(self.client.get(reverse("inventario:habilitar"), **HX))
        self.sin_errores(self.client.get(reverse("inventario:habilitar"), {"insumo": self.nutriente.pk}, **HX))
