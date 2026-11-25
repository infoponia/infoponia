# Pruebas de COM-CNS-CVT, Consultar Compra-venta (COM-02, paso 5; docs/casos_de_uso/comercial/compra_venta.md): `buscar_compra_ventas` y
# `ficha_de_compra_venta`. Una por regla (numeradas, como el caso de uso): alcance con 403, filtros, monto «estimado» y «final», orden,
# ficha y consultas fijas (sin consultas por fila). No audita (SEG-14).

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta
from comercial.servicios import compra_ventas
from comercial.servicios.compra_ventas import FiltrosDeCompraVentas
from comercial.tests.fabricas import cliente as crear_cliente, compra_venta, detalle, escenario_comercial
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_vendedor

HOY = timezone.localdate()


class ComCnsCvtServicioTests(ConDatosDeInventario, TestCase):
    """`buscar_compra_ventas(actor, filtros, pagina)` y `ficha_de_compra_venta(actor, id)`."""

    def setUp(self):
        self.e = escenario_comercial()
        self.otro = escenario_comercial(sufijo="2")
        self.gerente = crear_gerente()
        self.mia = compra_venta(self.e, dias=2)
        detalle(self.mia, self.e.variedad, 10, precio="100.00")
        self.ajena = compra_venta(self.otro, dias=5)
        detalle(self.ajena, self.otro.variedad, 4, precio="50.00")

    def buscar(self, actor=None, pagina=1, **filtros):
        """Los ids de la página de resultados, en orden."""
        pagina_ = compra_ventas.buscar_compra_ventas(actor or self.gerente, FiltrosDeCompraVentas(**filtros), pagina)
        return [v.pk for v in pagina_.object_list]

    def test_regla_1_el_vendedor_ve_solo_las_suyas_y_el_gerente_todas(self):
        """Regla 1: alcance: el Vendedor ve las compra-ventas de los contratos de los que es Vendedor; el Gerente, todas."""
        self.assertEqual(sorted(self.buscar()), sorted([self.mia.pk, self.ajena.pk]))
        self.assertEqual(self.buscar(self.e.vendedor), [self.mia.pk])
        self.assertEqual(self.buscar(self.otro.vendedor), [self.ajena.pk])

    def test_regla_1_otro_rol_o_cuenta_inactiva_recibe_permission_denied(self):
        """Precondición a: solo un Vendedor o un Gerente con la cuenta activa."""
        inactivo = crear_vendedor(email="inactivo@infoponia.com", activo=False)
        for actor in (self.e.agronomo, inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                compra_ventas.buscar_compra_ventas(actor, FiltrosDeCompraVentas())
            with self.subTest(actor=actor, ficha=True), self.assertRaises(PermissionDenied):
                compra_ventas.ficha_de_compra_venta(actor, self.mia.pk)

    def test_regla_1_una_ficha_fuera_del_alcance_da_403_con_mensaje_y_un_id_inexistente_404(self):
        """Regla 1 y SEG-13: la ficha de la venta de otro Vendedor es `PermissionDenied` (403 con mensaje); un id que no existe, 404."""
        with self.assertRaises(PermissionDenied):
            compra_ventas.ficha_de_compra_venta(self.e.vendedor, self.ajena.pk)
        with self.assertRaises(Http404):
            compra_ventas.ficha_de_compra_venta(self.e.vendedor, 999999)

    def test_regla_2_filtra_por_cliente_y_por_estado(self):
        """Regla 2: filtros por cliente y por estado."""
        otro_cliente = crear_cliente(razon_social="Otro S.A.")
        distinta = compra_venta(self.e, cliente_=otro_cliente, estado="cancelada")
        self.assertEqual(self.buscar(cliente_id=str(otro_cliente.pk)), [distinta.pk])
        self.assertEqual(self.buscar(estado="cancelada"), [distinta.pk])
        self.assertEqual(sorted(self.buscar(estado="abierta")), sorted([self.mia.pk, self.ajena.pk]))
        self.assertEqual(sorted(self.buscar(estado="inventado")), sorted([self.mia.pk, self.ajena.pk, distinta.pk]))

    def test_regla_2_filtra_por_rango_de_fecha_pactada_o_de_realizacion(self):
        """Regla 2: rango de fechas, por la fecha pactada (por defecto) o la de realización."""
        desde, hasta = str(HOY + timedelta(days=1)), str(HOY + timedelta(days=3))
        self.assertEqual(self.buscar(desde=desde, hasta=hasta), [self.mia.pk])
        CompraVenta.objects.filter(pk=self.ajena.pk).update(fecha_realizacion=HOY - timedelta(days=10))
        self.assertEqual(self.buscar(fecha_de="realizacion", hasta=str(HOY - timedelta(days=1))), [self.ajena.pk])
        self.assertEqual(self.buscar(fecha_de="realizacion", desde=str(HOY)), [self.mia.pk])
        self.assertEqual(sorted(self.buscar(desde="basura")), sorted([self.mia.pk, self.ajena.pk]))

    def test_regla_2_el_filtro_de_vendedor_es_solo_del_gerente(self):
        """Regla 2: «solo para el Gerente, Vendedor»: el Vendedor no puede ampliar su alcance con el filtro."""
        self.assertEqual(self.buscar(vendedor_id=str(self.otro.vendedor.pk)), [self.ajena.pk])
        self.assertEqual(self.buscar(self.e.vendedor, vendedor_id=str(self.otro.vendedor.pk)), [self.mia.pk])

    def test_regla_3_orden_por_fecha_de_realizacion_y_numero_descendentes(self):
        """Regla 3: la más reciente primero y, con la misma fecha, el número mayor primero."""
        antigua = compra_venta(self.e)
        CompraVenta.objects.filter(pk=antigua.pk).update(fecha_realizacion=HOY - timedelta(days=3))
        esperado = [v.pk for v in sorted([self.mia, self.ajena], key=lambda v: -v.numero)] + [antigua.pk]
        self.assertEqual(self.buscar(), esperado)

    def test_regla_3_el_monto_es_estimado_si_esta_abierta_y_final_si_esta_concretada_o_cancelada(self):
        """Regla 3 y «Monto»: por detalle, confirmado → entregada × precio; abierto o pendiente → solicitada × precio; rechazado o cancelado → 0.
        «final» si la venta está concretada o cancelada, «estimado» si no."""
        venta = compra_venta(self.e, estado="concretada")
        from produccion.tests.fabricas import variedad_con_stock

        otras = [variedad_con_stock(self.e, nombre=f"V{n}", habilitar=False)[0] for n in range(3)]
        detalle(venta, self.e.variedad, 10, precio="100.00", estado="confirmado")
        DetalleVenta.objects.filter(compra_venta=venta).update(cant_entregada_venta=7)
        detalle(venta, otras[0], 5, precio="20.00", estado="abierto")
        detalle(venta, otras[1], 5, precio="30.00", estado="rechazado")
        detalle(venta, otras[2], 5, precio="40.00", estado="pendiente_decision")
        filas = {v.pk: v for v in compra_ventas.buscar_compra_ventas(self.gerente, FiltrosDeCompraVentas()).object_list}
        self.assertEqual(filas[venta.pk].monto, Decimal("1000.00"))  # 7×100 + 5×20 + 0 + 5×40
        self.assertTrue(filas[venta.pk].monto_es_final)
        self.assertEqual((filas[self.mia.pk].monto, filas[self.mia.pk].monto_es_final), (Decimal("1000.00"), False))

    def test_regla_3_una_venta_sin_detalles_vale_cero(self):
        """El monto de una venta sin detalles es 0 (no `None`)."""
        vacia = compra_venta(self.e)
        filas = {v.pk: v for v in compra_ventas.buscar_compra_ventas(self.gerente, FiltrosDeCompraVentas()).object_list}
        self.assertEqual(filas[vacia.pk].monto, Decimal("0.00"))

    def test_regla_3_la_lista_hace_las_mismas_consultas_con_1_y_con_10_ventas(self):
        """Requisito: sin consultas por fila (cliente, Vendedor y monto vienen en la misma consulta)."""
        def consultas():
            with CaptureQueriesContext(connection) as capturadas:
                list(compra_ventas.buscar_compra_ventas(self.gerente, FiltrosDeCompraVentas()).object_list)
                for v in compra_ventas.buscar_compra_ventas(self.gerente, FiltrosDeCompraVentas()).object_list:
                    str(v.cliente), str(v.vendedor), v.monto
            return len(capturadas)

        con_pocas = consultas()
        for _ in range(10):
            detalle(compra_venta(self.e), self.e.variedad, 3)
        self.assertEqual(consultas(), con_pocas)

    def test_regla_3_la_lista_se_pagina_de_a_50(self):
        """Regla 3: páginas de 50."""
        for _ in range(51):
            compra_venta(self.e)
        pagina = compra_ventas.buscar_compra_ventas(self.gerente, FiltrosDeCompraVentas(), 1)
        self.assertEqual((len(pagina.object_list), pagina.paginator.num_pages), (50, 2))

    def test_regla_4_la_ficha_trae_cliente_vendedor_destino_fechas_y_detalles_con_subtotal(self):
        """Regla 4 (en lo que existe hoy): cliente, Vendedor, modalidad con la dirección, las fechas, cada detalle con su variedad,
        cantidad solicitada y entregada, precio, subtotal y estado, y el estado del comprobante."""
        ficha = compra_ventas.ficha_de_compra_venta(self.e.vendedor, self.mia.pk)
        self.assertEqual((ficha.venta.cliente, ficha.venta.vendedor_id, ficha.monto), (self.e.cliente, self.e.vendedor.pk, Decimal("1000.00")))
        self.assertIn("San Martín 123", ficha.destino)
        (fila,) = ficha.detalles
        self.assertEqual((fila.detalle.variedad, fila.detalle.cant_solicitada_venta, fila.detalle.cant_entregada_venta, fila.subtotal, fila.detalle.estado_detalle_venta), (self.e.variedad, 10, None, Decimal("1000.00"), "abierto"))
        self.assertEqual(ficha.venta.estado_comprobante, "pendiente_envio")

    def test_regla_4_la_ficha_de_un_retiro_dice_el_invernadero_con_su_direccion(self):
        """Regla 4: con retiro, el invernadero de retiro (con su dirección)."""
        venta = compra_venta(self.e, modalidad="retiro", retiro=self.e.invernadero)
        destino = compra_ventas.ficha_de_compra_venta(self.e.vendedor, venta.pk).destino
        self.assertIn(self.e.invernadero.nombre_invernadero, destino)

    def test_regla_5_desde_la_ficha_se_va_al_cliente_y_se_reenvia_solo_un_comprobante_pendiente(self):
        """Regla 5: «Ver cliente» siempre; «Reenviar comprobante» solo con el comprobante pendiente de envío y un cliente con correo; «Cancelar compra-venta» (COM-05b) con la venta
        «abierta» o «pendiente de decisión del cliente», para el Vendedor del contrato y el Gerente."""
        ficha = compra_ventas.ficha_de_compra_venta(self.e.vendedor, self.mia.pk)
        self.assertEqual(ficha.acciones, frozenset({"ver_cliente", "reenviar_comprobante", "cancelar"}))
        CompraVenta.objects.filter(pk=self.mia.pk).update(estado_comprobante="enviado")
        self.assertEqual(compra_ventas.ficha_de_compra_venta(self.e.vendedor, self.mia.pk).acciones, frozenset({"ver_cliente", "cancelar"}))
        CompraVenta.objects.filter(pk=self.mia.pk).update(estado_venta="concretada")
        self.assertEqual(compra_ventas.ficha_de_compra_venta(self.e.vendedor, self.mia.pk).acciones, frozenset({"ver_cliente"}))
        CompraVenta.objects.filter(pk=self.mia.pk).update(estado_venta="pendiente_decision")
        self.assertIn("cancelar", compra_ventas.ficha_de_compra_venta(self.gerente, self.mia.pk).acciones)

    def test_post_a_es_una_consulta_no_modifica_datos_ni_audita(self):
        """Postcondición a: no modifica datos ni registra auditoría."""
        antes = RegistroAuditoria.objects.count()
        compra_ventas.buscar_compra_ventas(self.gerente, FiltrosDeCompraVentas())
        compra_ventas.ficha_de_compra_venta(self.gerente, self.mia.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
