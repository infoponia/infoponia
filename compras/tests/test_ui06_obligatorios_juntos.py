# Pruebas de UI-06, paso 3 (D-109 punto 9, UX-27) en `compras`: el bloque «Habilitar insumo» de «Nuevo pedido» (extensión 3a.1a), enviado vacío, marca invernadero, insumo, mínimo y precio a la vez
# (antes la vista solo marcaba los dos primeros, porque no llama al servicio hasta que están elegidos). Textos del servicio; no cambia ninguno. Los botones que solo redibujan el formulario
# («Filtrar», «Agregar»…) con el bloque vacío no muestran errores (INV-02).

from django.urls import reverse

from compras.tests import test_pedidos_vistas as t_pedidos
from core.tests.obligatorios_ui06 import ObligatoriosJuntos
from inventario.tests.fabricas import insumo


class HabilitarEnNuevoPedidoTests(ObligatoriosJuntos, t_pedidos.PedidosVistasBase):
    """CMP-REG-PED, extensión 3a.1a, `pedidos/nuevo.html`."""

    def setUp(self):
        super().setUp()
        self.sustrato = insumo("Sustrato", unidad="kg")  # sin habilitar en el invernadero
        self.url = reverse("compras:pedido_nuevo")

    def enviar(self, vacios, espacios=frozenset()):
        datos = {"accion": "habilitar", "hab_invernadero": self.norte.pk, "hab_insumo": self.sustrato.pk, "hab_minimo": "5", "hab_precio": "30.00"}
        datos.update({campo: ("   " if campo in espacios else "") for campo in vacios})
        return self.client.post(self.url, datos)

    def test_ui06_el_bloque_habilitar_enviado_vacio_marca_los_cuatro_campos(self):
        self.comprobar_obligatorios_juntos(
            self.enviar, ("hab_invernadero", "hab_insumo", "hab_minimo", "hab_precio"), espacios=("hab_minimo", "hab_precio")
        )

    def test_ui06_un_boton_que_solo_redibuja_con_el_bloque_vacio_no_muestra_errores(self):
        datos = self.formulario(accion="filtrar") | {"hab_invernadero": "", "hab_insumo": "", "hab_minimo": "", "hab_precio": ""}
        self.sin_errores(self.client.post(self.url, datos))
