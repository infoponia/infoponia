# Pruebas del registro de los cuatro tipos de alerta de `inventario` (INV-01, paso 2; docs/patrones/stock.md, sección 4 y
# docs/api/alertas.md, «Registrar tus tipos»).

from django.test import SimpleTestCase

from inventario import alertas as alertas_de_inventario
from maestros.alertas import Clase, Destinatario, TipoAlerta, registrar_tipo_de_alerta, tipo_de_alerta
from maestros.models import Alerta

CODIGOS = ["inv_stock_inconsistente", "inv_insumo_bajo_minimo", "inv_insumo_por_vencer", "inv_insumo_vencido"]


class TiposDeAlertaDeInventarioTests(SimpleTestCase):
    """Los tipos se registran al arrancar la app (``InventarioConfig.ready``)."""

    def test_regla_stock_4_los_cuatro_tipos_estan_registrados(self):
        """docs/patrones/stock.md sección 4: los cuatro códigos están registrados al arrancar."""
        for codigo in CODIGOS:
            with self.subTest(codigo=codigo):
                self.assertEqual(tipo_de_alerta(codigo).codigo, codigo)

    def test_regla_stock_4_todos_son_de_estado_y_van_al_agronomo_o_al_gerente(self):
        """Sección 4: clase `ESTADO` y destinatario `AGRONOMO_O_GERENTE` (D-41), sin origen."""
        for codigo in CODIGOS:
            with self.subTest(codigo=codigo):
                tipo = tipo_de_alerta(codigo)
                self.assertEqual(tipo.clase, Clase.ESTADO)
                self.assertEqual(tipo.destinatario, Destinatario.AGRONOMO_O_GERENTE)
                self.assertIsNone(tipo.origen)

    def test_regla_stock_4_severidades_como_el_prototipo(self):
        """Sección 4: inconsistente y vencido, críticas; bajo el mínimo y por vencer, advertencias."""
        self.assertEqual(tipo_de_alerta("inv_stock_inconsistente").severidad, Alerta.Severidad.CRITICA)
        self.assertEqual(tipo_de_alerta("inv_insumo_vencido").severidad, Alerta.Severidad.CRITICA)
        self.assertEqual(tipo_de_alerta("inv_insumo_bajo_minimo").severidad, Alerta.Severidad.ADVERTENCIA)
        self.assertEqual(tipo_de_alerta("inv_insumo_por_vencer").severidad, Alerta.Severidad.ADVERTENCIA)

    def test_regla_stock_4_los_codigos_tienen_a_lo_sumo_50_caracteres(self):
        """docs/api/alertas.md: el código es único y de hasta 50 caracteres, con el prefijo de la app."""
        for codigo in CODIGOS:
            self.assertLessEqual(len(codigo), 50)
            self.assertTrue(codigo.startswith("inv_"))

    def test_regla_stock_4_registrar_dos_veces_el_mismo_valor_no_falla(self):
        """docs/api/alertas.md: registrar dos veces la misma definición es idempotente (``ready()`` puede correr dos veces)."""
        alertas_de_inventario.registrar_tipos_de_stock()
        alertas_de_inventario.registrar_tipos_de_stock()
        self.assertEqual(tipo_de_alerta("inv_insumo_vencido").nombre, "Insumo vencido")

    def test_regla_stock_4_otra_definicion_del_mismo_codigo_lanza_value_error(self):
        """docs/api/alertas.md: un código repetido con OTRA definición lanza ``ValueError``."""
        otra = TipoAlerta("inv_insumo_vencido", "Otro", Destinatario.GERENTE, Alerta.Severidad.INFORMATIVA, Clase.EVENTO)
        with self.assertRaises(ValueError):
            registrar_tipo_de_alerta(otra)
