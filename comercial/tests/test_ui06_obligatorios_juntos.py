# Pruebas de UI-06, paso 3 (D-109 punto 9, UX-27) en `comercial`: «Entrega no reconocida», enviada vacía, marca el resultado y la descripción a la vez (antes el servicio cortaba en el resultado). La
# descripción se exige con cualquier resultado (`atencion.py:186`), así que es independiente. Textos del servicio; no cambia ninguno. La pantalla no tiene selectores que redibujen: abrirla (GET)
# no muestra errores.

from django.urls import reverse

from comercial.tests import test_confirmacion_vistas as t_confirmacion
from core.tests.obligatorios_ui06 import ObligatoriosJuntos


class EntregaNoReconocidaTests(ObligatoriosJuntos, t_confirmacion.Base):
    """COM-ATN-ENR, `entregas/no_reconocida.html`."""

    def setUp(self):
        super().setUp()
        self.entrega, self.enlace, self.token = self.nueva()
        t_confirmacion.confirmacion.registrar_respuesta(
            self.enlace.pk, t_confirmacion.DatosDeRespuesta(t_confirmacion.NO_RECIBI, motivo_no_recibi="No llegó nada a la sucursal.")
        )
        self.url = reverse("comercial:entrega_no_reconocida", args=[self.entrega.pk])
        self.client.force_login(self.gerente)

    def enviar(self, vacios, espacios=frozenset()):
        datos = {"resultado": "llego", "descripcion": "Llegó al otro local."}
        datos.update({campo: ("   " if campo in espacios else "") for campo in vacios})
        return self.client.post(self.url, datos)

    def test_ui06_enviada_vacia_marca_el_resultado_y_la_descripcion(self):
        # el aviso rojo «El cliente indicó…» es informativo: solo cuentan los errores de campo
        self.comprobar_obligatorios_juntos(self.enviar, ("resultado", "descripcion"), clases=("err",), espacios=("descripcion",))

    def test_ui06_abrir_la_pantalla_no_muestra_errores(self):
        self.sin_errores(self.client.get(self.url), clases=("err",))
