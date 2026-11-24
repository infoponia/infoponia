# Pruebas de concurrencia de CMP-GNR-ODC y CMP-APR-ODC (CMP-03, paso 4). Fuente: «Requisitos especiales» de los dos casos de uso («El control de
# concurrencia impide que un pedido genere dos órdenes, y que se genere la orden de un pedido mientras se lo cancela»; «impide que una orden se resuelva dos
# veces; impide que dos aprobaciones simultáneas de órdenes con el mismo insumo en el mismo invernadero pierdan un aumento de la cantidad en tránsito; impide
# que se apruebe una orden mientras se da de baja un invernadero o un insumo de destino»), la tabla «Pruebas» de «Cómo se aplica (código)», regla «Proveedor
# inactivo» de CMP-APR-ODC (H22), D-90 punto 5 y docs/patrones/bloqueos.md («compras»). Son ``TransactionTestCase`` con dos hilos y dos conexiones
# (``core/tests/concurrencia.py``); ``primera`` se detiene al auditar, con todos sus bloqueos tomados y sin confirmar, y recién entonces arranca la otra.
#
# Qué demuestra cada una (y qué se rompe al invertir el orden de bloqueo o quitarlo):
#   - dos generaciones del mismo pedido: una sola orden; la otra ve el pedido «cerrado» (11a). El respaldo es el ``OneToOne`` y el bloqueo del pedido.
#   - generar contra cancelar: la cancelación automática (que no toma la cuenta del Agrónomo) y la generación comparten el bloqueo del pedido; gana una y la
#     otra ve el estado nuevo (6a de CMP-CNL-PED, 11a de CMP-GNR-ODC). Sin el bloqueo del pedido, la generación pisaría la cancelación.
#   - dos aprobaciones sobre el mismo insumo y destino: el tránsito suma las dos (no se pierde un aumento). Sin el bloqueo de la existencia, la segunda
#     escribiría el valor leído antes de que la primera confirmara.
#   - generar contra la baja del proveedor: se bloquean los proveedores elegidos antes que el pedido. Sin ese bloqueo, la baja (que ve «sin órdenes») y la
#     generación (que ve «proveedor activo») pasan las dos y queda una orden con un proveedor inactivo.
#   - aprobar contra la baja del proveedor y contra la baja del invernadero: como una orden pendiente ya es un impedimento (H20 y H22), la baja se rechaza
#     siempre; las pruebas dejan escrito el invariante «nunca una orden aprobada con un proveedor o un destino dado de baja».

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TransactionTestCase, tag
from django.utils import timezone

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, OrdenCompra, Pedido, Proveedor
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, orden_de, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.models import InsumoInvernadero
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, existencia, insumo, perezoso
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef, crear_agronomo_con_invernadero

ordenes = perezoso("compras.servicios.ordenes")
pedidos_de_compras = perezoso("compras.servicios.pedidos")
proveedores_de_compras = perezoso("compras.servicios.proveedores")
invernaderos = perezoso("maestros.servicios.invernaderos")


@tag("concurrencia")
class OrdenesConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Ana con su invernadero Norte y un Gerente. Dos pedidos vencidos de lechuga (20 y 10, tolerancia 0): P1 con dos cotizaciones que lo cubren cada una (de A y
    de B, 20) y P2 con una (de A, 10). ``TransactionTestCase``: su ``flush`` vacía los datos de las migraciones, así que se aseguran de nuevo en cada prueba."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 0
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.hoy = timezone.localdate()
        self.gerente = crear_gerente()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte")
        self.lechuga_iin = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=0, precio="10.00")
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.pedido, self.detalle = self.pedido_vencido(20)
        self.cot_a = cotizacion_de(self.pedido, self.a, [(self.detalle, 20, "200.00", 3)])
        self.cot_b = cotizacion_de(self.pedido, self.b, [(self.detalle, 20, "180.00", 4)])
        self.pedido2, self.detalle2 = self.pedido_vencido(10)
        self.cot_a2 = cotizacion_de(self.pedido2, self.a, [(self.detalle2, 10, "100.00", 2)])

    def pedido_vencido(self, cantidad):
        """Un pedido de Ana, vencido ayer, con un detalle de lechuga en Norte."""
        pedido = armar_pedido(self.ana)
        detalle = detalle_de_pedido(pedido, self.lechuga_iin, cantidad=str(cantidad))
        Pedido.objects.filter(pk=pedido.pk).update(fecha_pedido=self.hoy - timedelta(days=5), fecha_limite_cotizaciones=self.hoy - timedelta(days=1))
        return pedido, detalle

    def generar(self, pedido, *cotizaciones):
        return lambda: ordenes.generar_orden(self.ana, pedido.pk, [c.pk for c in cotizaciones], "")

    def aprobar(self, orden):
        return lambda: ordenes.aprobar_orden(self.gerente, orden.pk)

    def transito(self):
        return InsumoInvernadero.objects.get(pk=self.lechuga_iin.pk).cant_transito_insumo

    def partir(self, resultados):
        """``(éxitos, errores)`` de lo que devolvió ``correr_a_la_vez``."""
        exitos = [r for r in resultados.values() if not isinstance(r, Exception)]
        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        return exitos, errores

    # ---- generar ----

    def test_requisito_dos_generaciones_del_mismo_pedido_crean_una_sola_orden(self):
        """CMP-GNR-ODC «Requisitos especiales»: dos sesiones generan la orden del mismo pedido; la segunda espera, ve el pedido «cerrado» y recibe
        ``pedido_no_en_cotizacion`` con la orden de la primera; nunca un 500 ni dos órdenes."""
        resultados = correr_a_la_vez(self.generar(self.pedido, self.cot_a), self.generar(self.pedido, self.cot_b), primera="a")
        exitos, errores = self.partir(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual((errores[0].codigo, errores[0].datos["orden_id"]), ("pedido_no_en_cotizacion", exitos[0].pk))
        self.assertEqual(OrdenCompra.objects.filter(pedido=self.pedido).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="generacion_orden_compra").count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.gerente).count(), 1)

    def test_requisito_generar_mientras_se_cancela_gana_la_generacion(self):
        """CMP-GNR-ODC «Requisitos especiales»: la generación llega primero (con el pedido bloqueado); la cancelación automática espera, ve el pedido «cerrado»
        y no cancela nada (devuelve ``None``)."""
        causa = "sin_cotizaciones_elegibles"
        resultados = correr_a_la_vez(
            self.generar(self.pedido, self.cot_a), lambda: pedidos_de_compras.cancelar_pedido_automaticamente(self.pedido, causa), primera="a"
        )
        self.assertIsInstance(resultados["a"], OrdenCompra)
        self.assertIsNone(resultados["b"])
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "cerrado")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 0)

    def test_requisito_cancelar_mientras_se_genera_gana_la_cancelacion(self):
        """CMP-GNR-ODC «Requisitos especiales»: la cancelación llega primero; la generación espera, ve el pedido «cancelado» y recibe ``pedido_no_en_cotizacion``
        (extensión 11a): no se genera una orden de un pedido cancelado."""
        causa = "sin_cotizaciones_elegibles"
        resultados = correr_a_la_vez(
            lambda: pedidos_de_compras.cancelar_pedido_automaticamente(self.pedido, causa), self.generar(self.pedido, self.cot_a), primera="a"
        )
        self.assertEqual(resultados["a"].estado_pedido, "cancelado")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual((resultados["b"].codigo, resultados["b"].datos["estado"]), ("pedido_no_en_cotizacion", "cancelado"))
        self.assertEqual(OrdenCompra.objects.count(), 0)

    def test_h22_generar_contra_la_baja_del_proveedor_gana_la_generacion(self):
        """Regla «Proveedor inactivo» y H22: la generación llega primero y bloquea al proveedor elegido; la baja espera, y al releer ve la orden «pendiente de
        aprobación» (``orden_no_terminada``): ``baja_con_impedimentos``. Nunca queda una orden con un proveedor inactivo."""
        resultados = correr_a_la_vez(
            self.generar(self.pedido, self.cot_a), lambda: proveedores_de_compras.baja_proveedor(self.gerente, self.a.pk), primera="a"
        )
        self.assertIsInstance(resultados["a"], OrdenCompra)
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "baja_con_impedimentos")
        self.assertEqual([i.codigo for i in resultados["b"].datos["impedimentos"]], ["orden_no_terminada"])
        self.assertEqual(Proveedor.objects.get(pk=self.a.pk).estado_proveedor, "activo")

    def test_h22_generar_contra_la_baja_del_proveedor_gana_la_baja(self):
        """Extensión 11b: la baja llega primero; la generación espera, ve al proveedor «inactivo» y no genera nada (``cotizacion_no_elegible``)."""
        resultados = correr_a_la_vez(
            lambda: proveedores_de_compras.baja_proveedor(self.gerente, self.a.pk), self.generar(self.pedido, self.cot_a), primera="a"
        )
        self.assertEqual(resultados["a"].estado_proveedor, "inactivo")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual((resultados["b"].codigo, resultados["b"].datos["afectadas"]), ("cotizacion_no_elegible", [(self.cot_a.pk, "proveedor_inactivo")]))
        self.assertEqual(OrdenCompra.objects.count(), 0)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "en_cotizacion")

    # ---- aprobar ----

    def test_requisito_dos_aprobaciones_del_mismo_insumo_y_destino_suman_el_transito(self):
        """CMP-APR-ODC «Requisitos especiales»: dos órdenes (20 y 10 lechugas en Norte) se aprueban a la vez; la segunda espera la existencia bloqueada y suma
        sobre lo que dejó la primera: el tránsito es 30, no 10 ni 20 (no se pierde un aumento)."""
        o1 = orden_de(self.pedido, [self.cot_a])
        o2 = orden_de(self.pedido2, [self.cot_a2])
        resultados = correr_a_la_vez(self.aprobar(o1), self.aprobar(o2), primera="a")
        self.assertEqual([r.estado_orden_compra for r in resultados.values()], ["aprobada", "aprobada"])
        self.assertEqual(self.transito(), Decimal("30"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="aprobacion_orden_compra").count(), 2)

    def test_requisito_dos_aprobaciones_de_la_misma_orden_aprueban_una_sola_vez(self):
        """CMP-APR-ODC «Requisitos especiales» (primera función): la misma orden desde dos sesiones; la segunda ve la orden «aprobada» (``orden_no_pendiente``) y
        el tránsito sube una sola vez."""
        orden = orden_de(self.pedido, [self.cot_a])
        resultados = correr_a_la_vez(self.aprobar(orden), self.aprobar(orden), primera="a")
        exitos, errores = self.partir(resultados)
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertEqual((errores[0].codigo, errores[0].datos["estado"]), ("orden_no_pendiente", "aprobada"))
        self.assertEqual(self.transito(), Decimal("20"))

    def test_requisito_aprobar_y_rechazar_la_misma_orden_a_la_vez_resuelve_una_sola_vez(self):
        """CMP-APR-ODC «Requisitos especiales»: aprobar y rechazar a la vez; gana la primera y la otra recibe ``orden_no_pendiente``. Sin tránsito si ganó el rechazo."""
        orden = orden_de(self.pedido, [self.cot_a])
        resultados = correr_a_la_vez(lambda: ordenes.rechazar_orden(self.gerente, orden.pk, "No hay presupuesto."), self.aprobar(orden), primera="a")
        self.assertEqual(resultados["a"].estado_orden_compra, "rechazada")
        self.assertEqual(resultados["b"].codigo, "orden_no_pendiente")
        self.assertEqual(self.transito(), Decimal("0"))

    def test_h22_aprobar_contra_la_baja_del_proveedor_la_baja_se_rechaza(self):
        """H22 y «Requisitos especiales»: una orden pendiente (o aprobada) ya es un impedimento de la baja del proveedor; con la aprobación a medio hacer la baja
        espera y, al releer, se rechaza con ``baja_con_impedimentos``. Nunca queda una orden aprobada con su proveedor inactivo."""
        orden = orden_de(self.pedido, [self.cot_a])
        resultados = correr_a_la_vez(self.aprobar(orden), lambda: proveedores_de_compras.baja_proveedor(self.gerente, self.a.pk), primera="a")
        self.assertEqual(resultados["a"].estado_orden_compra, "aprobada")
        self.assertEqual((resultados["b"].codigo, [i.codigo for i in resultados["b"].datos["impedimentos"]]), ("baja_con_impedimentos", ["orden_no_terminada"]))
        self.assertEqual(Proveedor.objects.get(pk=self.a.pk).estado_proveedor, "activo")

    def test_requisito_aprobar_contra_la_baja_del_invernadero_la_baja_se_rechaza(self):
        """«Requisitos especiales» y H20: una orden no terminada con una línea al insumo (``orden_de_compra_aprobada``) impide la baja del invernadero; con la
        aprobación a medio hacer la baja se rechaza. Nunca queda una orden aprobada con su destino inactivo."""
        orden = orden_de(self.pedido, [self.cot_a])
        resultados = correr_a_la_vez(self.aprobar(orden), lambda: invernaderos.baja_invernadero(self.gerente, self.norte.pk), primera="a")
        self.assertEqual(resultados["a"].estado_orden_compra, "aprobada")
        self.assertIsInstance(resultados["b"], ValidationError)
        self.assertIn("orden_de_compra_aprobada", [e.code for lista in resultados["b"].error_dict.values() for e in lista])
        self.assertEqual(Invernadero.objects.get(pk=self.norte.pk).estado_invernadero, "activo")
        self.assertEqual(Cotizacion.objects.get(pk=self.cot_a.pk).estado_cotizacion, "seleccionada")
