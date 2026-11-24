# Pruebas de lo que COM-02 completa en los servicios de clientes de COM-01 (docs/disparadores.md, «Completan el ABM de cliente», punto 1;
# docs/casos_de_uso/comercial/clientes.md, «Para más adelante»): `direcciones_en_uso`, `pendientes_del_cliente`, los contratos de la ficha y
# «Contratos vigentes» de la lista (el Vendedor, solo los suyos) y la corrección de una dirección que usa una venta (regla 4 de COM-MOD-CLT).
# Reemplazan a las pruebas de COM-01 que esperaban «nada» (pedido de COM-01: «Se completa en COM-02»).
# COM-03a suma los suministros a las mismas funciones (`docs/disparadores.md`, «Completan el ABM de cliente», punto 2): `direcciones_en_uso`,
# `impide_quitar_el_correo`, `pendientes_del_cliente`, `contratos_del_cliente` y `contratos_vigentes_por_cliente`.

from django.test import TestCase

from comercial.servicios import clientes
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    compra_venta,
    datos_de_cliente_de,
    datos_de_direccion,
    detalle,
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    suministro,
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
        # COM-03a: ahora son dos consultas (compra-ventas y suministros), no una por cliente: las pruebas de COM-02 esperaban 1.
        with self.assertNumQueries(2):
            clientes.contratos_vigentes_por_cliente(self.gerente, [self.e.cliente, solo])


class ClientesConSuministrosTests(ConDatosDeInventario, TestCase):
    """COM-03a: lo que suman los suministros a las funciones de clientes."""

    def setUp(self):
        self.e = escenario_comercial()
        self.otro = escenario_comercial(sufijo="2")
        self.gerente = crear_gerente()

    def contrato(self, escenario=None, cliente_=None, estado="vigente", direccion=None, estado_detalle="vigente"):
        """Un suministro del cliente con un detalle a la ``direccion`` (por defecto, la del escenario)."""
        e = escenario or self.e
        s = suministro(e, cliente_=cliente_ or self.e.cliente, estado=estado)
        extra = {"fecha_fin_detalle": s.fecha_realizacion} if estado_detalle == "finalizado" else {}
        detalle_suministro(s, e.variedad, direccion=direccion or self.e.direccion, estado=estado_detalle, **extra)
        return s

    def test_regla_3_direcciones_en_uso_cuenta_los_detalles_de_suministro_en_cualquier_estado(self):
        """Regla 3 de 8.18 (MD-19): una dirección que usa un detalle de suministro, finalizado o no, nunca se modifica ni se borra."""
        libre = direccion_de_cliente(self.e.cliente, calle="Libre")
        usadas = {}
        for estado_detalle in ("vigente", "finalizado"):
            vinculo = direccion_de_cliente(self.e.cliente, calle=f"Usada {estado_detalle}")
            self.contrato(direccion=vinculo.direccion, estado_detalle=estado_detalle)
            usadas[estado_detalle] = vinculo.direccion_id
        ids = [d.pk for d in clientes.direcciones_activas(self.e.cliente)]
        en_uso = clientes.direcciones_en_uso(ids)
        self.assertEqual(en_uso, set(usadas.values()))
        self.assertNotIn(libre.direccion_id, en_uso)

    def test_regla_3_direcciones_en_uso_junta_las_de_compra_ventas_y_las_de_suministros(self):
        """Una compra-venta con envío y un detalle de suministro: las dos direcciones están en uso, en una sola respuesta."""
        de_venta = direccion_de_cliente(self.e.cliente, calle="De venta")
        de_suministro = direccion_de_cliente(self.e.cliente, calle="De suministro")
        compra_venta(self.e, direccion=de_venta.direccion)
        self.contrato(direccion=de_suministro.direccion)
        self.assertEqual(clientes.direcciones_en_uso([de_venta.direccion_id, de_suministro.direccion_id]), {de_venta.direccion_id, de_suministro.direccion_id})

    def test_regla_3_modificar_la_direccion_de_un_suministro_crea_otra_y_deja_inactiva_la_anterior(self):
        """Regla 4 de COM-MOD-CLT (con datos reales): corregir una dirección que usa un detalle de suministro crea una nueva y la anterior
        pasa a «inactiva»; el detalle sigue apuntando a la anterior."""
        s = self.contrato()
        datos = datos_de_cliente_de(
            self.e.cliente, direcciones_corregidas=[(self.e.direccion.pk, datos_de_direccion(calle="Corregida", numero_calle="9"))]
        )
        clientes.modificar_cliente(self.gerente, self.e.cliente.pk, datos)
        self.assertEqual(Direccion.objects.get(pk=self.e.direccion.pk).estado_direccion, "inactivo")
        self.assertEqual([d.calle for d in clientes.direcciones_activas(self.e.cliente)], ["Corregida"])
        self.assertEqual(s.detalles.get().direccion_id, self.e.direccion.pk)

    def test_regla_3_impide_quitar_el_correo_si_hay_un_suministro_vigente(self):
        """Regla 3 de COM-MOD-CLT: solo un suministro «vigente» del cliente impide quitarle el correo (no un finalizado, resuelto o rescindido,
        ni el de otro cliente)."""
        self.assertIs(clientes.impide_quitar_el_correo(self.e.cliente), False)
        self.contrato(estado="finalizado")
        otro_cliente = crear_cliente(razon_social="Otro S.A.", email="otro@ejemplo.com")
        self.contrato(cliente_=otro_cliente)
        self.assertIs(clientes.impide_quitar_el_correo(self.e.cliente), False)
        self.contrato()
        self.assertIs(clientes.impide_quitar_el_correo(self.e.cliente), True)

    def test_regla_1_pendientes_del_cliente_informa_primero_los_suministros_vigentes(self):
        """Regla 1 de COM-BAJ-CLT: «Suministros vigentes: 2 (SUM-…, SUM-…).» antes de las compra-ventas abiertas; no cuentan los finalizados
        ni los de otro cliente."""
        a, b = self.contrato(), self.contrato(direccion=direccion_de_cliente(self.e.cliente).direccion)
        self.contrato(estado="finalizado")
        self.contrato(cliente_=crear_cliente(razon_social="Otro S.A.", email="otro@ejemplo.com"))
        venta = compra_venta(self.e)
        self.assertEqual(
            clientes.pendientes_del_cliente(self.e.cliente, self.gerente),
            [f"Suministros vigentes: 2 ({a.codigo}, {b.codigo}).", f"Compra-ventas abiertas: 1 ({venta.codigo})."],
        )

    def test_regla_2_la_ficha_muestra_los_suministros_del_alcance_junto_a_las_compra_ventas(self):
        """Regla 2 de COM-CNS-CLT: la lista de contratos suma los suministros, mezclados con las compra-ventas de la más reciente a la más
        antigua; el Vendedor ve solo los suyos."""
        venta = compra_venta(self.e)
        propio = self.contrato()
        ajeno = self.contrato(escenario=self.otro)
        todos = clientes.contratos_del_cliente(self.gerente, self.e.cliente)
        self.assertEqual([c.pk for c in todos], [ajeno.pk, propio.pk, venta.pk])
        self.assertEqual([c.tipo_contrato for c in todos], ["suministro", "suministro", "compra_venta"])
        solo_suyos = clientes.contratos_del_cliente(self.e.vendedor, self.e.cliente)
        self.assertEqual([c.pk for c in solo_suyos], [propio.pk, venta.pk])

    def test_regla_2_contratos_vigentes_de_la_lista_suma_los_suministros_vigentes_del_alcance(self):
        """«Contratos vigentes» de la lista: compra-ventas abiertas o pendientes más suministros vigentes, dentro del alcance; en consultas
        fijas (una por clase)."""
        compra_venta(self.e)
        self.contrato()
        self.contrato(estado="finalizado")
        self.contrato(escenario=self.otro)
        solo = crear_cliente(razon_social="Sin contratos S.A.")
        self.assertEqual(clientes.contratos_vigentes_por_cliente(self.gerente, [self.e.cliente, solo]), {self.e.cliente.pk: 3})
        self.assertEqual(clientes.contratos_vigentes_por_cliente(self.e.vendedor, [self.e.cliente, solo]), {self.e.cliente.pk: 2})
        with self.assertNumQueries(2):
            clientes.contratos_vigentes_por_cliente(self.gerente, [self.e.cliente, solo])
