# Pruebas de lo que `comercial` registra en `inventario.extensiones.registrar_impedimento_de_baja_de_variedad` (COM-02; precondición f de
# PROD-BAJ-VAR): el código `contratos_abiertos` («Tiene contratos abiertos: N compra-ventas y M suministros.»; COM-03a le suma los suministros
# vigentes y cambia el texto de COM-02, que decía «Tiene compra-ventas abiertas: N.»: el número que vale 0 se omite y se usa el singular).
# Las tres pruebas mínimas de cada registrante.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from comercial.servicios import registrantes
from comercial.tests.fabricas import compra_venta, detalle, detalle_suministro, direccion_de_cliente, escenario_comercial, suministro
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
        """Prueba mínima 1: «Tiene contratos abiertos: 2 compra-ventas.» con una abierta y una pendiente de decisión; no cuentan la concretada ni
        la cancelada (texto de COM-03a: reemplaza al de COM-02, «Tiene compra-ventas abiertas: 2.»)."""
        for estado in ("abierta", "pendiente_decision", "concretada", "cancelada"):
            detalle(compra_venta(self.e, estado=estado), self.e.variedad, 5)
        impedimentos = registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        self.assertEqual([(i.codigo, i.texto) for i in impedimentos], [("contratos_abiertos", "Tiene contratos abiertos: 2 compra-ventas.")])
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
        self.assertEqual(registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)[0].texto, "Tiene contratos abiertos: 1 compra-venta.")

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
        self.assertIn("Tiene contratos abiertos: 1 compra-venta.", str(contexto.exception))


class ImpedimentoConSuministrosTests(ConDatosDeInventario, TestCase):
    """COM-03a: los suministros vigentes con un detalle vigente de la variedad (`docs/casos_de_uso/comercial/suministro.md`, «Lo que completa…»)."""

    def setUp(self):
        self.e = escenario_comercial()

    def contrato(self, estado="vigente", variedad=None, estado_detalle="vigente", detalles=1):
        """Un suministro con ``detalles`` detalles de la variedad (cada uno a otra dirección del cliente)."""
        s = suministro(self.e, estado=estado)
        for i in range(detalles):
            direccion = self.e.direccion if i == 0 else direccion_de_cliente(self.e.cliente).direccion
            extra = {"fecha_fin_detalle": s.fecha_realizacion} if estado_detalle == "finalizado" else {}
            detalle_suministro(s, variedad or self.e.variedad, direccion=direccion, estado=estado_detalle, **extra)
        return s

    def texto(self):
        (impedimento,) = registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        return impedimento.texto

    def test_ext_con_suministros_vigentes_se_cuentan_junto_a_las_compra_ventas(self):
        """COM-03a: «Tiene contratos abiertos: 2 compra-ventas y 1 suministro.» (con el singular de cada número)."""
        for _ in range(2):
            detalle(compra_venta(self.e), self.e.variedad, 5)
        self.contrato()
        self.assertEqual(self.texto(), "Tiene contratos abiertos: 2 compra-ventas y 1 suministro.")

    def test_ext_solo_suministros_omite_las_compra_ventas_y_usa_el_plural(self):
        """COM-03a: sin compra-ventas, «Tiene contratos abiertos: 1 suministro.» y, con dos, «2 suministros.»; una compra-venta y varios
        suministros: «1 compra-venta y 3 suministros.»."""
        self.contrato()
        self.assertEqual(self.texto(), "Tiene contratos abiertos: 1 suministro.")
        self.contrato()
        self.assertEqual(self.texto(), "Tiene contratos abiertos: 2 suministros.")
        self.contrato()
        detalle(compra_venta(self.e), self.e.variedad, 5)
        self.assertEqual(self.texto(), "Tiene contratos abiertos: 1 compra-venta y 3 suministros.")

    def test_ext_un_suministro_con_dos_detalles_de_la_variedad_cuenta_una_sola_vez(self):
        """Cada suministro cuenta una vez, aunque tenga dos detalles vigentes de la variedad (a distintas direcciones)."""
        self.contrato(detalles=2)
        self.assertEqual(self.texto(), "Tiene contratos abiertos: 1 suministro.")

    def test_ext_no_cuentan_los_suministros_que_no_estan_vigentes_ni_los_detalles_finalizados_ni_otras_variedades(self):
        """Solo los suministros «vigentes» con un detalle «vigente» de esa variedad: no cuentan uno finalizado o resuelto, uno cuyo detalle
        de la variedad está finalizado, ni el de otra variedad."""
        self.contrato(estado="finalizado")
        resuelto = self.contrato()
        type(resuelto).objects.filter(pk=resuelto.pk).update(estado_suministro="resuelto", fecha_resolucion_suministro=resuelto.fecha_realizacion)
        self.contrato(estado_detalle="finalizado")
        otra, _ = variedad_con_stock(self.e, nombre="Otra", habilitar=False)
        self.contrato(variedad=otra)
        self.assertEqual(registrantes.impedimentos_de_baja_de_variedad(self.e.variedad), [])

    def test_ext_sin_consultas_por_fila_con_suministros(self):
        """Prueba mínima 3: la misma cantidad de consultas con un suministro y con tres."""
        self.contrato()
        with CaptureQueriesContext(connection) as con_uno:
            registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        for _ in range(2):
            self.contrato()
        with CaptureQueriesContext(connection) as con_tres:
            registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        self.assertEqual(len(con_uno), len(con_tres))

    def test_punta_a_punta_la_baja_de_la_variedad_se_impide_con_suministros_vigentes(self):
        """PROD-BAJ-VAR, precondición f: `baja_variedad` rechaza una variedad con un suministro vigente (el mensaje del impedimento)."""
        from django.core.exceptions import ValidationError

        self.contrato()
        with self.assertRaises(ValidationError) as contexto:
            variedades.baja_variedad(self.e.agronomo, self.e.variedad.pk)
        self.assertIn("Tiene contratos abiertos: 1 suministro.", str(contexto.exception))
