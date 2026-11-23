# Pruebas de lo que `comercial` registra en `inventario.extensiones.registrar_impedimento_de_baja_de_variedad` (COM-02; precondición f de
# PROD-BAJ-VAR): el código `contratos_abiertos` («Tiene compra-ventas abiertas: N.»). Las tres pruebas mínimas de cada registrante.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from comercial.servicios import registrantes
from comercial.tests.fabricas import compra_venta, detalle, escenario_comercial
from inventario import extensiones
from inventario.servicios import variedades
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import variedad_con_stock


class ImpedimentoDeVariedadTests(ConDatosDeInventario, TestCase):
    """`contratos_abiertos`: compra-ventas abiertas o pendientes de decisión con un detalle abierto de la variedad."""

    def setUp(self):
        self.e = escenario_comercial()

    def codigos(self, variedad=None):
        """Los códigos de los impedimentos de `comercial` para la variedad (por el punto de extensión de `inventario`, junto con los demás)."""
        return [i.codigo for i in extensiones.impedimentos_de_baja_de_variedad(variedad or self.e.variedad)]

    def test_ext_con_datos_cuenta_las_compra_ventas_abiertas_y_pendientes(self):
        """Prueba mínima 1: «Tiene compra-ventas abiertas: 2.» con una abierta y una pendiente de decisión; no cuentan la concretada ni la cancelada."""
        for estado in ("abierta", "pendiente_decision", "concretada", "cancelada"):
            detalle(compra_venta(self.e, estado=estado), self.e.variedad, 5)
        impedimentos = registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        self.assertEqual([(i.codigo, i.texto) for i in impedimentos], [("contratos_abiertos", "Tiene compra-ventas abiertas: 2.")])
        self.assertIn("contratos_abiertos", self.codigos())

    def test_ext_neutro_una_variedad_sin_compra_ventas_no_tiene_impedimento(self):
        """Prueba mínima 2: sin compra-ventas abiertas de esa variedad, ninguno (otra variedad vendida no cuenta)."""
        otra, _ = variedad_con_stock(self.e, nombre="Otra", habilitar=False)
        detalle(compra_venta(self.e), otra, 5)
        self.assertEqual(registrantes.impedimentos_de_baja_de_variedad(self.e.variedad), [])
        self.assertNotIn("contratos_abiertos", self.codigos())

    def test_ext_una_compra_venta_con_dos_detalles_de_la_variedad_cuenta_una_sola_vez(self):
        """Cada compra-venta cuenta una vez (una variedad por venta, pero la cuenta no repite filas)."""
        venta = compra_venta(self.e)
        detalle(venta, self.e.variedad, 5)
        self.assertEqual(registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)[0].texto, "Tiene compra-ventas abiertas: 1.")

    def test_ext_sin_consultas_por_fila(self):
        """Prueba mínima 3: la misma cantidad de consultas con una venta y con tres."""
        detalle(compra_venta(self.e), self.e.variedad, 5)
        with CaptureQueriesContext(connection) as con_una:
            registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        for _ in range(2):
            detalle(compra_venta(self.e), self.e.variedad, 5)
        with CaptureQueriesContext(connection) as con_tres:
            registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        self.assertEqual(len(con_una), len(con_tres))

    def test_punta_a_punta_la_baja_de_la_variedad_se_impide_con_compra_ventas_abiertas(self):
        """PROD-BAJ-VAR, precondición f: `baja_variedad` rechaza una variedad con compra-ventas abiertas (el mensaje del impedimento)."""
        from django.core.exceptions import ValidationError

        detalle(compra_venta(self.e), self.e.variedad, 5)
        with self.assertRaises(ValidationError) as contexto:
            variedades.baja_variedad(self.e.agronomo, self.e.variedad.pk)
        self.assertIn("Tiene compra-ventas abiertas: 1.", str(contexto.exception))
