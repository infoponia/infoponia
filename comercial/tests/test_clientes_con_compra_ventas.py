# Pruebas de lo que COM-02 completa en los servicios de clientes de COM-01 (docs/disparadores.md, «Completan el ABM de cliente», punto 1;
# docs/casos_de_uso/comercial/clientes.md, «Para más adelante»): `direcciones_en_uso`, `pendientes_del_cliente`, los contratos de la ficha y
# «Contratos vigentes» de la lista (el Vendedor, solo los suyos) y la corrección de una dirección que usa una venta (regla 4 de COM-MOD-CLT).
# Reemplazan a las pruebas de COM-01 que esperaban «nada» (pedido de COM-01: «Se completa en COM-02»).

from django.test import TestCase

from comercial.servicios import clientes
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    compra_venta,
    datos_de_cliente_de,
    datos_de_direccion,
    detalle,
    direccion_de_cliente,
    escenario_comercial,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Direccion


class ClientesConCompraVentasTests(ConDatosDeInventario, TestCase):
    """Los datos que COM-01 dejaba neutros."""

    def setUp(self):
        self.e = escenario_comercial()
        self.otro = escenario_comercial(sufijo="2")
        self.gerente = crear_gerente()

    def test_regla_4_direcciones_en_uso_cuenta_las_compra_ventas_con_envio_en_cualquier_estado(self):
        """Regla 3 de 8.18 (MD-19) y D-58 punto 5: una dirección usada nunca se modifica ni se borra, aunque la venta esté cancelada."""
        libre = direccion_de_cliente(self.e.cliente, calle="Libre")
        for estado in ("abierta", "cancelada", "concretada"):
            vinculo = direccion_de_cliente(self.e.cliente, calle=f"Usada {estado}")
            compra_venta(self.e, estado=estado, direccion=vinculo.direccion)
        ids = [d.pk for d in clientes.direcciones_activas(self.e.cliente)]
        en_uso = clientes.direcciones_en_uso(ids)
        self.assertEqual(len(en_uso), 3)
        self.assertNotIn(libre.direccion_id, en_uso)
        self.assertEqual(clientes.direcciones_en_uso([]), set())

    def test_regla_4_un_retiro_no_usa_ninguna_direccion(self):
        """Una compra-venta con retiro no tiene dirección de envío: no marca ninguna como usada."""
        compra_venta(self.e, modalidad="retiro")
        self.assertEqual(clientes.direcciones_en_uso([self.e.direccion.pk]), set())

    def test_regla_4_modificar_la_direccion_de_una_venta_crea_otra_y_deja_inactiva_la_anterior(self):
        """Regla 4 de COM-MOD-CLT y D-58 punto 5 (ahora con datos reales, sin simular): corregir una dirección que usa una compra-venta crea una
        nueva con los datos corregidos y la anterior pasa a «inactiva»; la venta sigue apuntando a la anterior."""
        venta = compra_venta(self.e)
        datos = datos_de_cliente_de(
            self.e.cliente, direcciones_corregidas=[(self.e.direccion.pk, datos_de_direccion(calle="Corregida", numero_calle="9"))]
        )
        clientes.modificar_cliente(self.gerente, self.e.cliente.pk, datos)
        self.assertEqual(Direccion.objects.get(pk=self.e.direccion.pk).estado_direccion, "inactivo")
        activas = clientes.direcciones_activas(self.e.cliente)
        self.assertEqual([d.calle for d in activas], ["Corregida"])
        venta.refresh_from_db()
        self.assertEqual(venta.direccion_envio_id, self.e.direccion.pk)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="modificacion_cliente").exists())

    def test_regla_1_pendientes_del_cliente_informa_las_compra_ventas_abiertas_y_pendientes(self):
        """Regla 1 de COM-BAJ-CLT: «Compra-ventas abiertas: 2 (CV-…, CV-…).» con una abierta y una pendiente de decisión; no cuentan las
        concretadas ni las canceladas; las de otro cliente tampoco."""
        a, b = compra_venta(self.e), compra_venta(self.e, estado="pendiente_decision")
        compra_venta(self.e, estado="concretada")
        compra_venta(self.e, estado="cancelada")
        compra_venta(self.otro)
        self.assertEqual(
            clientes.pendientes_del_cliente(self.e.cliente, self.gerente),
            [f"Compra-ventas abiertas: 2 ({a.codigo}, {b.codigo})."],
        )

    def test_regla_2_la_ficha_muestra_las_compra_ventas_del_alcance(self):
        """Regla 2 de COM-CNS-CLT (COM-02): el Vendedor ve solo las suyas; el Gerente, todas; con su monto y de la más reciente a la más antigua."""
        propia = compra_venta(self.e, cliente_=self.e.cliente)
        detalle(propia, self.e.variedad, 10, precio="100.00")
        ajena = compra_venta(self.otro, cliente_=self.e.cliente)
        self.assertEqual([v.pk for v in clientes.contratos_del_cliente(self.gerente, self.e.cliente)], [ajena.pk, propia.pk])
        solo_suyas = clientes.contratos_del_cliente(self.e.vendedor, self.e.cliente)
        self.assertEqual([v.pk for v in solo_suyas], [propia.pk])
        self.assertEqual(str(solo_suyas[0].monto), "1000.00")

    def test_regla_2_contratos_vigentes_de_la_lista_cuenta_abiertas_y_pendientes_del_alcance(self):
        """«Contratos vigentes» de la lista: abiertas y pendientes de decisión, dentro del alcance de quien mira, en una sola consulta."""
        compra_venta(self.e)
        compra_venta(self.e, estado="pendiente_decision")
        compra_venta(self.e, estado="cancelada")
        compra_venta(self.otro, cliente_=self.e.cliente)
        solo = crear_cliente(razon_social="Sin ventas S.A.")
        self.assertEqual(clientes.contratos_vigentes_por_cliente(self.gerente, [self.e.cliente, solo]), {self.e.cliente.pk: 3})
        self.assertEqual(clientes.contratos_vigentes_por_cliente(self.e.vendedor, [self.e.cliente, solo]), {self.e.cliente.pk: 2})
        with self.assertNumQueries(1):
            clientes.contratos_vigentes_por_cliente(self.gerente, [self.e.cliente, solo])
