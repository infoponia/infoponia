# Pruebas de UI-06, paso 3 (D-109 punto 9, UX-27) en `produccion`: enviados vacíos, los formularios marcan todos los campos obligatorios que no dependen de otros, cada uno con el
# texto del servicio, y la vista va al primero. Lo que depende de otro valor (la distribución que tiene que sumar la cantidad) sigue esperando a que ese valor sea válido. Redibujar
# un selector (accion «actualizar») con los campos vacíos no muestra ningún error (INV-02). No cambia ningún servicio.

from django.urls import reverse

from core.tests.obligatorios_ui06 import ObligatoriosJuntos, textos_de_error
from produccion.tests import test_eventos_vistas as t_eventos
from produccion.tests import test_prod_reg_lte_vistas as t_lte
from produccion.tests import test_produccion_vistas as t_prod

HX = {"HTTP_HX_REQUEST": "true"}


def _valor(campo, espacios):
    return "   " if campo in espacios else ""


class NuevaSiembraTests(ObligatoriosJuntos, t_prod.Base):
    """PROD-PNF-SMB (caso conocido de UX-27): Plantines y Fecha programada a la vez."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:nueva_siembra")

    def enviar(self, vacios, espacios=frozenset()):
        datos = {**self.datos_de_siembra(), "accion": "calcular"}
        datos.update({campo: _valor(campo, espacios) for campo in vacios})
        return self.client.post(self.url, datos)

    def test_ui06_enviada_vacia_marca_plantines_y_fecha_a_la_vez(self):
        self.comprobar_obligatorios_juntos(self.enviar, ("cantidad", "fecha_programada"), espacios=("cantidad", "fecha_programada"))

    def test_ui06_un_selector_con_los_campos_vacios_no_muestra_errores(self):
        datos = {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "accion": "actualizar", "cantidad": "", "fecha_programada": ""}
        self.sin_errores(self.client.post(self.url, datos, **HX))

    def test_ui06_con_la_cantidad_valida_y_la_distribucion_mal_sigue_el_error_de_la_distribucion(self):
        """Lo que depende de otro valor no se adelanta: con la cantidad válida y los sectores sin repartir, el error es el de la distribución de hoy y no se agrega ninguno de más."""
        sector = self.e.sectores["germinacion"].pk
        respuesta = self.client.post(self.url, {**self.datos_de_siembra(cantidad="30", **{f"sector_{sector}": "10"}), "accion": "calcular"})
        self.assertEqual(len(textos_de_error(respuesta)), 1)
        self.assertIn("La distribución tiene que sumar 30", textos_de_error(respuesta)[0])


class LoteExistenteTests(ObligatoriosJuntos, t_lte.Base):
    """PROD-REG-LTE: cantidad y las dos fechas."""

    CAMPOS = ("cantidad", "fecha_siembra", "fecha_ingreso_etapa")

    def enviar(self, vacios, espacios=frozenset()):
        return self.calcular(**{campo: _valor(campo, espacios) for campo in vacios})

    def test_ui06_enviado_vacio_marca_la_cantidad_y_las_dos_fechas(self):
        self.comprobar_obligatorios_juntos(self.enviar, self.CAMPOS, espacios=self.CAMPOS)

    def test_ui06_un_selector_con_los_campos_vacios_no_muestra_errores(self):
        datos = {"invernadero": self.e.invernadero.pk, "variedad": self.e.variedad.pk, "etapa": self.etapa(), "accion": "actualizar", "cantidad": "", "fecha_siembra": "", "fecha_ingreso_etapa": ""}
        self.sin_errores(self.client.post(self.url, datos, **HX))

    def test_ui06_con_la_cantidad_valida_y_la_distribucion_mal_sigue_el_error_de_la_distribucion(self):
        respuesta = self.calcular(**{f"sector_{self.e.sectores['maduracion'].pk}": "10"})
        self.assertEqual(len(textos_de_error(respuesta)), 1)


class MermaTests(ObligatoriosJuntos, t_eventos.Base):
    """PROD-REG-MRM: plantas perdidas y causa."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:registrar_merma")

    def enviar(self, vacios, espacios=frozenset()):
        datos = {**self.merma(), "accion": "calcular"}
        if "cantidad" in vacios:
            datos[f"cant_{self.sector.pk}"] = _valor("cantidad", espacios)
        if "causa" in vacios:
            datos["causa"] = ""  # es una lista: no se escribe con espacios
        return self.client.post(self.url, datos)

    def test_ui06_enviada_vacia_marca_la_cantidad_y_la_causa(self):
        self.comprobar_obligatorios_juntos(self.enviar, ("cantidad", "causa"), espacios=("cantidad",))

    def test_ui06_un_selector_con_los_campos_vacios_no_muestra_errores(self):
        datos = {"invernadero": self.e.invernadero.pk, "lote": self.lote.pk, "accion": "actualizar", "causa": "", f"cant_{self.sector.pk}": ""}
        self.sin_errores(self.client.post(self.url, datos, **HX))


class AplicacionTests(ObligatoriosJuntos, t_eventos.Base):
    """PROD-REG-APL: el alcance (sectores) y al menos un insumo. «Al menos un insumo» sale de las líneas que la vista ya armó (`not lineas`): no repite ninguna regla del servicio."""

    def setUp(self):
        super().setUp()
        self.entrar(self.e.agronomo)
        self.url = reverse("produccion:registrar_aplicacion")

    def enviar(self, vacios, espacios=frozenset()):
        datos = {**self.aplicacion(), "accion": "calcular"}
        if "sector_ids" in vacios:
            datos["alcance"] = "sectores"  # «sectores» sin marcar ninguno
        if "insumos" in vacios:
            datos[f"cantidad_{self.abono.pk}"] = _valor("insumos", espacios)
        return self.client.post(self.url, datos)

    def test_ui06_enviada_vacia_marca_el_alcance_y_los_insumos(self):
        self.comprobar_obligatorios_juntos(self.enviar, ("sector_ids", "insumos"), espacios=("insumos",))

    def test_ui06_un_selector_con_los_campos_vacios_no_muestra_errores(self):
        datos = {"invernadero": self.e.invernadero.pk, "accion": "actualizar", "alcance": "sectores", f"cantidad_{self.abono.pk}": ""}
        self.sin_errores(self.client.post(self.url, datos, **HX))
