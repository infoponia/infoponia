# Pruebas de UI-06, paso 3 (D-109 punto 9, UX-27) en `iot`: «Registrar hardware», enviado vacío, marca el tipo de equipo y también identificador, modelo e insumo, que se ven antes de elegir el
# tipo (antes el servicio cortaba en «Elegí si es un sensor o un actuador» y no marcaba nada más). Quien emite el primer error es el servicio (`hardware.py:366`). La variable o el tipo de
# actuador y la calibración dependen del tipo: quedan como están. Cambiar el tipo (`refrescar`) con los campos vacíos no muestra errores (INV-02).

from core.tests.obligatorios_ui06 import ObligatoriosJuntos
from iot.tests import test_hardware_vistas as t_hardware


class RegistrarHardwareTests(ObligatoriosJuntos, t_hardware.HardwareVistasBase):
    """IOT-ALT-HDW, `hardware/formulario.html`."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.laura)
        self.nuevo = self.url("hardware_nuevo", invernadero=self.norte)

    def enviar(self, vacios, espacios=frozenset()):
        datos = self.post_del_sensor()
        datos.update({campo: ("   " if campo in espacios else "") for campo in vacios})
        return self.client.post(self.nuevo, datos)

    def test_ui06_enviado_vacio_marca_el_tipo_de_equipo_el_identificador_el_modelo_y_el_insumo(self):
        self.comprobar_obligatorios_juntos(self.enviar, ("clase", "identificador", "modelo", "insumo"), espacios=("identificador", "modelo"))

    def test_ui06_cambiar_el_tipo_con_los_campos_vacios_no_muestra_errores(self):
        datos = {"clase": "sensor", "identificador": "", "modelo": "", "insumo": "", "refrescar": "1"}
        self.sin_errores(self.client.post(self.nuevo, datos, HTTP_HX_REQUEST="true"))
