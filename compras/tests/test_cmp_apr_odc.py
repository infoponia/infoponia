# Pruebas de CMP-APR-ODC · Aprobar Orden de Compra (CMP-03, paso 4): ``ordenes_por_aprobar``, ``detalle_para_resolver``, ``resumir_aprobacion``,
# ``aprobar_orden``, ``resumir_rechazo``, ``rechazar_orden`` y ``motivo_propuesto`` de ``compras/servicios/ordenes.py``. Fuente:
# docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-APR-ODC v0.4: precondiciones a y b, garantías mínimas, postcondiciones a a m, flujo básico, extensiones
# *a, *b, 1a1, 4a, 4b, 5a, 5b, 8a, 8b y 9a, y las reglas «Orden resoluble», «El Gerente no elige», «Decisión total», «Estados de la orden», «Estado del pedido»,
# «Destino inactivo», «Proveedor inactivo», «Rechazo», «Pago diferido», «Fecha de entrega esperada», «Cantidad en tránsito», «Alerta de insumo bajo el mínimo»,
# «Avisos» y «Cotización vencida»), «Actualizaciones de A0 que mandan» (P1, H21, H22) y el cambio del punto 6 (H21), D-42, D-87 y D-90.
#
# API que fijan estas pruebas (todas dentro de ``compras/servicios/ordenes.py``; el módulo se toma dentro de cada prueba con ``perezoso``). Todas piden un
# Gerente activo (``PermissionDenied`` si no) y una orden que exista (``Http404``):
#   ordenes_por_aprobar(actor)            -> list[FilaPorAprobar(orden, pedido, agronomo, proveedores, monto)]   de la más antigua a la más reciente
#   detalle_para_resolver(actor, orden_id) -> DetalleParaResolver(orden, pedido, agronomo, proveedores, por_detalle, monto_total, monto_estimado, diferencia,
#                                              diferencia_porcentaje, lineas_afectadas, cotizaciones_afectadas, puede_aprobar, motivo_propuesto)
#       proveedores: list[ProveedorDeOrden(proveedor, cotizacion, lineas, monto)] (``lineas`` son detalles de la orden); por_detalle: list[(detalle_pedido,
#       pedida, comprada)]; lineas_afectadas: [(detalle_orden_id, «invernadero_inactivo» | «insumo_inactivo»)]; cotizaciones_afectadas: [(cotizacion_id,
#       «proveedor_inactivo» | «validez_vencida»)].
#   resumir_aprobacion(actor, orden_id)    -> ResumenDeAprobacion(orden, entregas, transito, proveedores)   entregas: [(detalle_orden, fecha)]; transito:
#                                              [(insumo_invernadero, antes, suma, despues)]. Solo lectura; mismas precondiciones que ``aprobar_orden``.
#   aprobar_orden(actor, orden_id)         -> OrdenCompra
#   resumir_rechazo(actor, orden_id, motivo) -> ResumenDeRechazo(orden, motivo, descartadas, proveedores)   solo lectura
#   rechazar_orden(actor, orden_id, motivo) -> OrdenCompra
#   motivo_propuesto(orden)                -> str   el motivo que el Sistema propone al rechazar (P1); vacío si ninguna cotización quedó afectada
# Errores de negocio (``ErrorDeCompras``): orden_no_pendiente (1a1, 8a y 5a.5a; ``datos``: ``estado``, ``gerente`` (texto), ``fecha_resolucion``,
# ``motivo_rechazo``), destino_inactivo (4a y 8b; ``datos["lineas"]``) y cotizacion_no_elegible (4b, 8b y P1; ``datos["afectadas"]``). El motivo vacío es un
# ``ValidationError`` del campo ``motivo`` con el código ``motivo_obligatorio`` (5b).
# Las notificaciones se crean dentro de la transacción (D-42) y los correos salen en ``on_commit`` (``captureOnCommitCallbacks``).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.test import TestCase, override_settings
from django.utils import timezone

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, DetalleOrdenCompra, OrdenCompra, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, orden_de, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion, RegistroAuditoria, Usuario
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import alertas_de_stock
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.models import Alerta, Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero, crear_invernadero

ordenes = perezoso("compras.servicios.ordenes")

MOTIVO = "No hay presupuesto este mes."


@override_settings(CORREO_CONFIGURADO=True)
class AprobacionBase(ConDatosDeInventario, TestCase):
    """Ana (invernaderos Norte y Norte 2), Beto (Sur), un Gerente y un pedido de Ana: 20 lechugas en Norte (referencia $12,50) y 20 tomates en Norte 2
    (referencia $10); estimado $450. Orden «pendiente de aprobación» con dos proveedores: A, 12 lechugas ($120, 3 días) y 20 tomates ($200, 4 días); B,
    10 lechugas ($100, 5 días). Total $420; las lechugas suman 22 y los tomates 20."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.norte2 = crear_invernadero("Norte 2", agronomo=self.ana)
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        self.lechuga_iin = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=0, precio="12.50")
        self.tomate_iin = existencia(insumo("Tomate", unidad="unidad"), self.norte2, minimo=0, precio="10.00")
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.c = proveedor("Hortalizas del Oeste S. A.", n=3, email="hola@oeste.com")
        self.pedido = armar_pedido(self.ana)
        self.lechuga = detalle_de_pedido(self.pedido, self.lechuga_iin, cantidad="20")
        self.tomate = detalle_de_pedido(self.pedido, self.tomate_iin, cantidad="20")
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=self.hoy - timedelta(days=5), fecha_limite_cotizaciones=self.hoy - timedelta(days=1))
        self.cot_a = cotizacion_de(self.pedido, self.a, [(self.lechuga, 12, "120.00", 3), (self.tomate, 20, "200.00", 4)])
        self.cot_b = cotizacion_de(self.pedido, self.b, [(self.lechuga, 10, "100.00", 5)])
        self.cot_c = cotizacion_de(self.pedido, self.c, [(self.lechuga, 5, "70.00", 2)])  # la que se descartó al generar
        self.orden = orden_de(self.pedido, [self.cot_a, self.cot_b])
        Cotizacion.objects.filter(pk=self.cot_c.pk).update(estado_cotizacion="descartada")
        self.linea = {  # el detalle de la orden de cada línea: ``("A", "lechuga")``...
            ("A", "lechuga"): self.detalle_de(self.cot_a, self.lechuga),
            ("A", "tomate"): self.detalle_de(self.cot_a, self.tomate),
            ("B", "lechuga"): self.detalle_de(self.cot_b, self.lechuga),
        }

    def detalle_de(self, cotizacion, detalle_pedido):
        return DetalleOrdenCompra.objects.get(orden=self.orden, detalle_cotizacion__cotizacion=cotizacion, detalle_cotizacion__detalle_pedido=detalle_pedido)

    def transito(self, iin):
        return InsumoInvernadero.objects.get(pk=iin.pk).cant_transito_insumo

    def aprobar(self, actor=None, orden=None):
        """``aprobar_orden`` con los correos ejecutados; devuelve la orden."""
        with self.captureOnCommitCallbacks(execute=True):
            return ordenes.aprobar_orden(actor or self.gerente, (orden or self.orden).pk)

    def rechazar(self, motivo=MOTIVO, actor=None, orden=None):
        """``rechazar_orden`` con los correos ejecutados; devuelve la orden."""
        with self.captureOnCommitCallbacks(execute=True):
            return ordenes.rechazar_orden(actor or self.gerente, (orden or self.orden).pk, motivo)

    def error(self, funcion, *args, **kwargs):
        """El ``ErrorDeCompras`` que lanza ``funcion`` (falla la prueba si no lanza ninguno)."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            funcion(*args, **kwargs)
        return contexto.exception

    def sin_cambios(self):
        """Nada se resolvió: la orden sigue «pendiente de aprobación», sin Gerente ni fecha de resolución; sus cotizaciones, «seleccionada»; sin entrega
        esperada, tránsito, notificaciones, correos ni auditoría."""
        orden = OrdenCompra.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden_compra, orden.gerente_id, orden.fecha_resolucion), ("pendiente_aprobacion", None, None))
        self.assertEqual(set(Cotizacion.objects.filter(pk__in=[self.cot_a.pk, self.cot_b.pk]).values_list("estado_cotizacion", flat=True)), {"seleccionada"})
        self.assertEqual(set(orden.detalles.values_list("fecha_entrega_esperada", flat=True)), {None})
        self.assertEqual((self.transito(self.lechuga_iin), self.transito(self.tomate_iin)), (Decimal("0"), Decimal("0")))
        self.assertEqual((Notificacion.objects.count(), len(mail.outbox)), (0, 0))
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=["aprobacion_orden_compra", "rechazo_orden_compra", "modificacion_insumo_invernadero"]).count(), 0)

    def poner_inactivo(self, objeto, campo="estado_insumo_invernadero"):
        type(objeto).objects.filter(pk=objeto.pk).update(**{campo: "inactivo"})


class PrecondicionesYAlcanceTests(AprobacionBase):
    """Precondición a y requisito especial: solo el Gerente activo; y la orden tiene que existir."""

    def test_precondicion_a_solo_un_gerente_activo_accede(self):
        """Precondición a y «Requisitos especiales»: el Agrónomo (aunque sea el del pedido), otros roles, una cuenta inactiva y ``None`` reciben ``PermissionDenied``."""
        inactivo = crear_gerente(email="otro.gerente@infoponia.com", activo=False)
        for cuenta in (self.ana, crear_capataz(), crear_administrador(), inactivo, None):
            for funcion, args in (
                (ordenes.ordenes_por_aprobar, ()),
                (ordenes.detalle_para_resolver, (self.orden.pk,)),
                (ordenes.resumir_aprobacion, (self.orden.pk,)),
                (ordenes.aprobar_orden, (self.orden.pk,)),
                (ordenes.resumir_rechazo, (self.orden.pk, MOTIVO)),
                (ordenes.rechazar_orden, (self.orden.pk, MOTIVO)),
            ):
                with self.subTest(cuenta=cuenta, funcion=funcion.__name__):
                    with self.assertRaises(PermissionDenied):
                        funcion(cuenta, *args)
        self.sin_cambios()

    def test_una_orden_inexistente_es_404(self):
        """D-28: una orden que no existe es ``Http404``."""
        for funcion, args in (
            (ordenes.detalle_para_resolver, (99999,)),
            (ordenes.resumir_aprobacion, (99999,)),
            (ordenes.aprobar_orden, (99999,)),
            (ordenes.rechazar_orden, (99999, MOTIVO)),
        ):
            with self.subTest(funcion=funcion.__name__):
                with self.assertRaises(Http404):
                    funcion(self.gerente, *args)


class OrdenesPorAprobarTests(AprobacionBase):
    """Paso 2 y regla «Orden resoluble»: las órdenes «pendiente de aprobación», de la más antigua a la más reciente."""

    def test_paso_2_lista_la_orden_con_su_pedido_su_agronomo_sus_proveedores_y_su_monto(self):
        (fila,) = ordenes.ordenes_por_aprobar(self.gerente)
        self.assertEqual((fila.orden, fila.pedido, fila.agronomo.pk), (self.orden, self.pedido, self.ana.pk))
        self.assertEqual((fila.proveedores, fila.monto), (2, Decimal("420.00")))

    def test_paso_2_van_de_la_mas_antigua_a_la_mas_reciente(self):
        """Paso 2: orden por fecha de emisión y, si empatan, por identificador."""
        otro = armar_pedido(self.ana)
        detalle = detalle_de_pedido(otro, self.lechuga_iin, cantidad="5")
        reciente = orden_de(otro, [cotizacion_de(otro, self.a, [(detalle, 5, "50.00", 2)])])
        OrdenCompra.objects.filter(pk=self.orden.pk).update(fecha_emision=self.hoy - timedelta(days=2))
        self.assertEqual([f.orden for f in ordenes.ordenes_por_aprobar(self.gerente)], [self.orden, reciente])

    def test_regla_orden_resoluble_solo_las_pendientes(self):
        """Regla «Orden resoluble»: una orden aprobada, rechazada o ya en recepción no se lista."""
        for estado in ("aprobada", "rechazada", "parcialmente_recibida", "recibida", "recibida_con_faltante"):
            with self.subTest(estado=estado):
                OrdenCompra.objects.filter(pk=self.orden.pk).update(
                    estado_orden_compra=estado, gerente=self.gerente, fecha_resolucion=self.hoy, motivo_rechazo=MOTIVO if estado == "rechazada" else ""
                )
                self.assertEqual(ordenes.ordenes_por_aprobar(self.gerente), [])


class DetalleParaResolverTests(AprobacionBase):
    """Paso 4: la información para decidir; y las extensiones 1a1, 4a y 4b que dicen qué impide aprobar."""

    def test_paso_4_trae_el_pedido_el_agronomo_las_observaciones_y_el_monto_frente_al_estimado(self):
        OrdenCompra.objects.filter(pk=self.orden.pk).update(observaciones="Entregar a la mañana.")
        detalle = ordenes.detalle_para_resolver(self.gerente, self.orden.pk)
        self.assertEqual((detalle.pedido, detalle.agronomo.pk, detalle.orden.observaciones), (self.pedido, self.ana.pk, "Entregar a la mañana."))
        self.assertEqual((detalle.monto_total, detalle.monto_estimado, detalle.diferencia, detalle.diferencia_porcentaje), (Decimal("420.00"), Decimal("450.00"), Decimal("-30.00"), Decimal("-6.7")))

    def test_paso_4_agrupa_las_lineas_por_proveedor_con_su_monto(self):
        """Paso 4: por proveedor, sus líneas de la orden y el monto de ellas (A: 120 + 200)."""
        por_proveedor = {p.proveedor: p for p in ordenes.detalle_para_resolver(self.gerente, self.orden.pk).proveedores}
        self.assertEqual(set(por_proveedor), {self.a, self.b})
        self.assertEqual(por_proveedor[self.a].monto, Decimal("320.00"))
        self.assertEqual(sorted(l.pk for l in por_proveedor[self.a].lineas), sorted([self.linea[("A", "lechuga")].pk, self.linea[("A", "tomate")].pk]))

    def test_paso_4_por_detalle_la_cantidad_comprada_frente_a_la_pedida(self):
        """Paso 4: lechugas 22 de 20 (A 12 + B 10) y tomates 20 de 20."""
        filas = {d.pk: (pedida, comprada) for d, pedida, comprada in ordenes.detalle_para_resolver(self.gerente, self.orden.pk).por_detalle}
        self.assertEqual(filas, {self.lechuga.pk: (Decimal("20"), Decimal("22")), self.tomate.pk: (Decimal("20"), Decimal("20"))})

    def test_sin_problemas_se_puede_aprobar_y_no_hay_motivo_propuesto(self):
        detalle = ordenes.detalle_para_resolver(self.gerente, self.orden.pk)
        self.assertTrue(detalle.puede_aprobar)
        self.assertEqual((detalle.lineas_afectadas, detalle.cotizaciones_afectadas, detalle.motivo_propuesto), ([], [], ""))

    def test_ext_4a_un_invernadero_inactivo_se_senala_y_no_se_puede_aprobar(self):
        """Extensión 4a: «invernadero inactivo» en cada línea de ese destino (Norte 2: los tomates de A)."""
        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="inactivo")
        detalle = ordenes.detalle_para_resolver(self.gerente, self.orden.pk)
        self.assertFalse(detalle.puede_aprobar)
        self.assertEqual(detalle.lineas_afectadas, [(self.linea[("A", "tomate")].pk, "invernadero_inactivo")])

    def test_ext_4a_un_insumo_inactivo_en_su_invernadero_se_senala_y_no_se_puede_aprobar(self):
        """Extensión 4a: «insumo inactivo en el invernadero» en las líneas de ese ``InsumoInvernadero`` (las dos de lechuga)."""
        self.poner_inactivo(self.lechuga_iin)
        detalle = ordenes.detalle_para_resolver(self.gerente, self.orden.pk)
        self.assertFalse(detalle.puede_aprobar)
        self.assertEqual(sorted(detalle.lineas_afectadas), sorted([(self.linea[("A", "lechuga")].pk, "insumo_inactivo"), (self.linea[("B", "lechuga")].pk, "insumo_inactivo")]))

    def test_ext_4b_una_cotizacion_vencida_se_senala_y_no_se_puede_aprobar(self):
        """Extensión 4b y regla «Cotización vencida»: «validez vencida»; la de hoy todavía sirve."""
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        Cotizacion.objects.filter(pk=self.cot_a.pk).update(fecha_validez_cotizacion=self.hoy)
        detalle = ordenes.detalle_para_resolver(self.gerente, self.orden.pk)
        self.assertFalse(detalle.puede_aprobar)
        self.assertEqual(detalle.cotizaciones_afectadas, [(self.cot_b.pk, "validez_vencida")])

    def test_p1_un_proveedor_inactivo_se_senala_y_no_se_puede_aprobar(self):
        """P1 de A0: si al aprobar una cotización elegida tiene el proveedor inactivo, solo se puede rechazar."""
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        detalle = ordenes.detalle_para_resolver(self.gerente, self.orden.pk)
        self.assertEqual((detalle.puede_aprobar, detalle.cotizaciones_afectadas), (False, [(self.cot_a.pk, "proveedor_inactivo")]))

    def test_p1_el_motivo_propuesto_nombra_cada_cotizacion_afectada(self):
        """P1: «La cotización de {proveedor} venció el {fecha}» o «{proveedor} está inactivo»; el Gerente lo puede editar."""
        vencio = self.hoy - timedelta(days=1)
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=vencio)
        self.assertEqual(ordenes.motivo_propuesto(self.orden), f"La cotización de Viveros del Este S. R. L. venció el {vencio:%d/%m/%Y}.")
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        self.assertEqual(
            ordenes.motivo_propuesto(self.orden),
            f"Semillas del Sur S. A. está inactivo. La cotización de Viveros del Este S. R. L. venció el {vencio:%d/%m/%Y}.",
        )
        self.assertEqual(ordenes.detalle_para_resolver(self.gerente, self.orden.pk).motivo_propuesto, ordenes.motivo_propuesto(self.orden))

    def test_ext_1a1_una_orden_ya_resuelta_informa_la_decision_el_gerente_y_la_fecha(self):
        """Extensión 1a1: «la decisión tomada, el Gerente que la tomó, la fecha de resolución y, si fue rechazada, el motivo»."""
        self.rechazar()
        error = self.error(ordenes.detalle_para_resolver, self.gerente, self.orden.pk)
        self.assertEqual(error.codigo, "orden_no_pendiente")
        self.assertEqual(error.datos["estado"], "rechazada")
        self.assertIn("Gabriela", error.datos["gerente"])
        self.assertEqual((error.datos["fecha_resolucion"], error.datos["motivo_rechazo"]), (self.hoy, MOTIVO))


class ResumenDeLaAprobacionTests(AprobacionBase):
    """Paso 6: lo que pasaría al aprobar, sin escribir nada."""

    def test_paso_6_la_fecha_de_entrega_de_cada_linea_es_hoy_mas_su_plazo(self):
        resumen = ordenes.resumir_aprobacion(self.gerente, self.orden.pk)
        self.assertEqual({d.pk: fecha for d, fecha in resumen.entregas}, {
            self.linea[("A", "lechuga")].pk: self.hoy + timedelta(days=3),
            self.linea[("A", "tomate")].pk: self.hoy + timedelta(days=4),
            self.linea[("B", "lechuga")].pk: self.hoy + timedelta(days=5),
        })

    def test_paso_6_como_subira_el_transito_de_cada_insumo_en_cada_invernadero(self):
        """Paso 6 y postcondición f: por ``InsumoInvernadero``, el tránsito de antes, lo que suma (la suma de sus líneas, de todos los proveedores) y el de después."""
        InsumoInvernadero.objects.filter(pk=self.lechuga_iin.pk).update(cant_transito_insumo=Decimal("5"))
        resumen = ordenes.resumir_aprobacion(self.gerente, self.orden.pk)
        self.assertEqual({iin.pk: (antes, suma, despues) for iin, antes, suma, despues in resumen.transito}, {
            self.lechuga_iin.pk: (Decimal("5"), Decimal("22"), Decimal("27")),
            self.tomate_iin.pk: (Decimal("0"), Decimal("20"), Decimal("20")),
        })

    def test_paso_6_cada_proveedor_recibira_solo_sus_lineas(self):
        resumen = ordenes.resumir_aprobacion(self.gerente, self.orden.pk)
        self.assertEqual({p.proveedor: len(p.lineas) for p in resumen.proveedores}, {self.a: 2, self.b: 1})

    def test_el_resumen_no_escribe_nada(self):
        ordenes.resumir_aprobacion(self.gerente, self.orden.pk)
        self.sin_cambios()

    def test_el_resumen_aplica_las_mismas_precondiciones_que_aprobar(self):
        """Pasos 4 a 6: una orden con un destino inactivo, con una cotización no elegible o ya resuelta no se resume para aprobar."""
        self.poner_inactivo(self.tomate_iin)
        self.assertEqual(self.error(ordenes.resumir_aprobacion, self.gerente, self.orden.pk).codigo, "destino_inactivo")
        InsumoInvernadero.objects.filter(pk=self.tomate_iin.pk).update(estado_insumo_invernadero="activo")
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        self.assertEqual(self.error(ordenes.resumir_aprobacion, self.gerente, self.orden.pk).codigo, "cotizacion_no_elegible")
        self.aprobar_forzado()
        self.assertEqual(self.error(ordenes.resumir_aprobacion, self.gerente, self.orden.pk).codigo, "orden_no_pendiente")

    def aprobar_forzado(self):
        """Deja la orden aprobada directo en la base (para probar lo que pasa con una ya resuelta)."""
        OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra="aprobada", gerente=self.gerente, fecha_resolucion=self.hoy)


class AprobarOrdenTests(AprobacionBase):
    """Postcondiciones a a h y m y las garantías mínimas del paso 8."""

    def test_flujo_principal_aprueba_la_orden_y_sube_el_transito(self):
        """«Hecho cuando»: el Gerente aprueba y el tránsito de cada insumo sube en ese invernadero."""
        orden = self.aprobar()
        self.assertEqual(orden.pk, self.orden.pk)
        self.assertEqual((self.transito(self.lechuga_iin), self.transito(self.tomate_iin)), (Decimal("22"), Decimal("20")))

    def test_post_a_la_orden_queda_aprobada_con_la_fecha_de_hoy_y_el_gerente(self):
        """Postcondición a y regla «Orden resoluble» (R011): «aprobada», fecha de resolución de hoy y asociada al Gerente que la resolvió."""
        self.aprobar()
        orden = OrdenCompra.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden_compra, orden.fecha_resolucion, orden.gerente_id), ("aprobada", self.hoy, self.gerente.pk))
        self.assertEqual(orden.motivo_rechazo, "")

    def test_post_b_el_pedido_sigue_cerrado_y_las_cotizaciones_seleccionadas(self):
        """Postcondiciones b y g y regla «Estado del pedido»: el pedido sigue «cerrado» y las cotizaciones de la orden siguen «seleccionada»."""
        self.aprobar()
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "cerrado")
        self.assertEqual(set(Cotizacion.objects.filter(pk__in=[self.cot_a.pk, self.cot_b.pk]).values_list("estado_cotizacion", flat=True)), {"seleccionada"})
        self.assertEqual(Cotizacion.objects.get(pk=self.cot_c.pk).estado_cotizacion, "descartada")

    def test_post_e_la_fecha_de_entrega_esperada_es_la_de_resolucion_mas_el_plazo_de_la_linea(self):
        """Postcondición e y regla «Fecha de entrega esperada»: hoy + el plazo de la línea de cotización de cada detalle (3, 4 y 5 días)."""
        self.aprobar()
        fechas = {clave: DetalleOrdenCompra.objects.get(pk=detalle.pk).fecha_entrega_esperada for clave, detalle in self.linea.items()}
        self.assertEqual(fechas, {
            ("A", "lechuga"): self.hoy + timedelta(days=3),
            ("A", "tomate"): self.hoy + timedelta(days=4),
            ("B", "lechuga"): self.hoy + timedelta(days=5),
        })

    def test_post_f_el_transito_suma_las_lineas_de_distintos_proveedores_que_cubren_un_mismo_detalle(self):
        """Postcondición f y regla «Cantidad en tránsito»: las lechugas de A (12) y de B (10) suman 22 en el mismo ``InsumoInvernadero``; suma sobre lo que ya había."""
        InsumoInvernadero.objects.filter(pk=self.lechuga_iin.pk).update(cant_transito_insumo=Decimal("5"))
        self.aprobar()
        self.assertEqual(self.transito(self.lechuga_iin), Decimal("27"))

    def test_post_d_aprobar_no_resuelve_la_alerta_de_insumo_bajo_el_minimo(self):
        """Postcondición d y regla «Alerta de insumo bajo el mínimo»: la alerta sigue activa aunque el tránsito alcance el mínimo; se resuelve al recibir."""
        InsumoInvernadero.objects.filter(pk=self.lechuga_iin.pk).update(cant_min_insumo=Decimal("20"))
        with transaction.atomic():
            alertas_de_stock.reevaluar_alertas_del_insumo(self.lechuga_iin.pk)
        activas = Alerta.objects.filter(tipo_alerta="inv_insumo_bajo_minimo", estado_alerta="activa")
        self.assertEqual(activas.count(), 1)
        self.aprobar()
        self.assertEqual(activas.count(), 1)

    def test_garantia_no_cambia_el_stock_actual_ni_las_reservas(self):
        """Garantías: aprobar no modifica el stock actual ni las reservas (solo el tránsito): sin movimientos nuevos ni lotes tocados."""
        movimientos, lotes = MovimientoInsumo.objects.count(), LoteInsumo.objects.count()
        self.aprobar()
        self.assertEqual((MovimientoInsumo.objects.count(), LoteInsumo.objects.count()), (movimientos, lotes))

    def test_post_c_se_notifica_al_agronomo_la_aprobacion_y_no_al_gerente_que_la_resolvio(self):
        """Postcondición c, regla «Avisos» y H21: al Agrónomo activo de los destinos, con el identificador de la orden, el pedido, la decisión, el monto y las
        fechas de entrega esperadas. Nunca a quien actuó."""
        self.aprobar()
        notificacion = Notificacion.objects.get(destinatario=self.ana)
        texto = f"{notificacion.titulo} {notificacion.detalle}"
        for esperado in (str(self.orden), str(self.pedido), "aprobada", "420", f"{self.hoy + timedelta(days=3):%d/%m/%Y}", f"{self.hoy + timedelta(days=5):%d/%m/%Y}"):
            self.assertIn(esperado, texto)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente).exists())

    def test_h21_con_destinos_de_dos_agronomos_avisa_a_los_dos(self):
        """H21 regla 1: cada Agrónomo activo de los invernaderos de destino (Norte 2 pasó a Beto)."""
        Invernadero.objects.filter(pk=self.norte2.pk).update(agronomo=self.beto)
        self.aprobar()
        self.assertEqual(set(Notificacion.objects.values_list("destinatario_id", flat=True)), {self.ana.pk, self.beto.pk})

    def test_h21_un_destino_sin_agronomo_activo_va_al_gerente_salvo_que_el_gerente_sea_quien_actuo(self):
        """H21 reglas 2 y 3: el destino sin Agrónomo activo se avisa al Gerente, pero «nunca se notifica a quien hizo la acción»: como el Gerente aprobó, solo
        recibe Ana por el otro destino. Con los dos destinos sin Agrónomo activo no hay a quién avisar y no falla."""
        Invernadero.objects.filter(pk=self.norte2.pk).update(agronomo=None)
        self.aprobar()
        self.assertEqual(set(Notificacion.objects.values_list("destinatario_id", flat=True)), {self.ana.pk})
        antes = Notificacion.objects.count()
        OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra="pendiente_aprobacion", gerente=None, fecha_resolucion=None)
        Usuario.objects.filter(pk=self.ana.pk).update(is_active=False)
        self.aprobar()
        self.assertEqual(Notificacion.objects.count(), antes)

    def test_post_h_cada_proveedor_recibe_un_correo_con_solo_sus_lineas(self):
        """Postcondición h y lista de tecnología 9a: orden, líneas (insumo, cantidad, precio y subtotal), invernadero con su dirección, fecha de entrega esperada de
        cada línea y total de sus líneas; sin los otros proveedores ni sus líneas."""
        self.aprobar()
        por_destino = {m.to[0]: m for m in mail.outbox}
        self.assertEqual(set(por_destino), {"ventas@sur.com", "info@este.com"})
        sur, este = por_destino["ventas@sur.com"].body, por_destino["info@este.com"].body
        for esperado in (str(self.orden), "Lechuga", "Tomate", "Norte", str(self.norte.direccion), f"{self.hoy + timedelta(days=3):%d/%m/%Y}", f"{self.hoy + timedelta(days=4):%d/%m/%Y}"):
            self.assertIn(esperado, sur)
        for importe in ("120", "200", "320"):
            self.assertRegex(sur, importe + r"[.,]00")
        for ajeno in ("Viveros del Este", f"{self.hoy + timedelta(days=5):%d/%m/%Y}", "420"):
            self.assertNotIn(ajeno, sur)
        self.assertIn("Lechuga", este)
        self.assertRegex(este, r"100[.,]00")
        for ajeno in ("Semillas del Sur", "Tomate", "320", "420", f"{self.hoy + timedelta(days=3):%d/%m/%Y}"):
            self.assertNotIn(ajeno, este)
        for correo in mail.outbox:
            self.assertIn(str(self.orden), correo.subject)

    def test_ext_9a_si_el_correo_falla_o_no_esta_configurado_la_aprobacion_permanece(self):
        """Extensión 9a: si no sale la notificación o un correo, la aprobación permanece registrada."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            self.aprobar()
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "aprobada")
        self.assertEqual(self.transito(self.lechuga_iin), Decimal("22"))
        OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra="pendiente_aprobacion", gerente=None, fecha_resolucion=None)
        InsumoInvernadero.objects.filter(pk=self.lechuga_iin.pk).update(cant_transito_insumo=Decimal("0"))
        mail.outbox.clear()
        with override_settings(CORREO_CONFIGURADO=False):
            self.aprobar()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "aprobada")

    def test_post_m_un_registro_por_la_orden_y_uno_por_cada_insumo_invernadero_modificado(self):
        """Postcondición m y D-36: ``aprobacion_orden_compra`` con la orden y sus detalles entre los afectados, hecho por el Gerente; y una
        ``modificacion_insumo_invernadero`` por cada ``InsumoInvernadero`` con el tránsito antes y después."""
        InsumoInvernadero.objects.filter(pk=self.lechuga_iin.pk).update(cant_transito_insumo=Decimal("5"))
        self.aprobar()
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.APROBACION_ORDEN_COMPRA)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertTrue(({("compras.ordencompra", self.orden.pk)} | {("compras.detalleordencompra", d.pk) for d in self.linea.values()}) <= afectados)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "pendiente_aprobacion", "despues": "aprobada"})
        self.assertEqual(registro.detalle["cambios"]["fecha_resolucion"], {"antes": None, "despues": self.hoy.isoformat()})
        modificaciones = RegistroAuditoria.objects.filter(accion="modificacion_insumo_invernadero")
        self.assertEqual(modificaciones.count(), 2)
        por_iin = {a["id"]: m.detalle["cambios"]["transito"] for m in modificaciones for a in m.afectados if a["modelo"] == "inventario.insumoinvernadero"}
        self.assertEqual({k: (Decimal(v["antes"]), Decimal(v["despues"])) for k, v in por_iin.items()}, {
            self.lechuga_iin.pk: (Decimal("5"), Decimal("27")),
            self.tomate_iin.pk: (Decimal("0"), Decimal("20")),
        })

    def test_regla_pago_diferido_aprobar_no_registra_pagos_ni_asientos(self):
        """Regla «Pago diferido» y D-91: aprobar no genera asiento contable (la orden no asienta). Compras no tiene pagos todavía; solo se comprueba que no hay
        más registros de auditoría que los de la aprobación."""
        antes = set(RegistroAuditoria.objects.values_list("accion", flat=True))
        self.aprobar()
        nuevas = set(RegistroAuditoria.objects.values_list("accion", flat=True)) - antes
        self.assertEqual(nuevas, {"aprobacion_orden_compra", "modificacion_insumo_invernadero"})

    def test_regla_estados_de_la_orden_una_orden_resuelta_no_vuelve_a_resolverse(self):
        """Regla «Estados de la orden» y extensión 8a: aprobar una orden ya aprobada (o rechazada) no cambia nada; el tránsito no se suma dos veces."""
        self.aprobar()
        error = self.error(ordenes.aprobar_orden, self.gerente, self.orden.pk)
        self.assertEqual((error.codigo, error.datos["estado"]), ("orden_no_pendiente", "aprobada"))
        self.assertEqual(self.transito(self.lechuga_iin), Decimal("22"))
        self.assertEqual(error.datos["fecha_resolucion"], self.hoy)
        self.assertEqual(self.error(ordenes.rechazar_orden, self.gerente, self.orden.pk, MOTIVO).codigo, "orden_no_pendiente")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "aprobada")

    def test_ext_4a_y_8b_con_un_destino_inactivo_no_se_aprueba_y_no_cambia_nada(self):
        """Extensiones 4a y 8b y regla «Destino inactivo»: invernadero inactivo o insumo inactivo en su invernadero; se informa qué líneas y por qué."""
        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="inactivo")
        error = self.error(ordenes.aprobar_orden, self.gerente, self.orden.pk)
        self.assertEqual((error.codigo, error.datos["lineas"]), ("destino_inactivo", [(self.linea[("A", "tomate")].pk, "invernadero_inactivo")]))
        self.sin_cambios()
        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="activo")
        self.poner_inactivo(self.lechuga_iin)
        self.assertEqual(self.error(ordenes.aprobar_orden, self.gerente, self.orden.pk).codigo, "destino_inactivo")
        self.sin_cambios()

    def test_ext_4b_y_8b_con_una_cotizacion_vencida_o_un_proveedor_inactivo_no_se_aprueba(self):
        """Extensiones 4b y 8b, regla «Cotización vencida» y P1: la validez se controla también al registrar; solo se puede rechazar."""
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        error = self.error(ordenes.aprobar_orden, self.gerente, self.orden.pk)
        self.assertEqual((error.codigo, error.datos["afectadas"]), ("cotizacion_no_elegible", [(self.cot_b.pk, "validez_vencida")]))
        self.sin_cambios()
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy)
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        error = self.error(ordenes.aprobar_orden, self.gerente, self.orden.pk)
        self.assertEqual((error.codigo, error.datos["afectadas"]), ("cotizacion_no_elegible", [(self.cot_a.pk, "proveedor_inactivo")]))
        self.sin_cambios()

    def test_regla_decision_total_la_orden_no_se_modifica(self):
        """Regla «Decisión total» y garantías: aprobar no cambia líneas, cantidades, precios ni proveedores (solo la fecha de entrega esperada)."""
        antes = list(DetalleOrdenCompra.objects.order_by("id").values_list("detalle_cotizacion_id", "cantidad_detalle_orden", "total_linea"))
        self.aprobar()
        self.assertEqual(list(DetalleOrdenCompra.objects.order_by("id").values_list("detalle_cotizacion_id", "cantidad_detalle_orden", "total_linea")), antes)

    def test_garantia_si_falla_la_auditoria_no_queda_nada_ni_sale_ningun_aviso(self):
        """Garantías mínimas y extensión *b: la resolución es atómica; si falla, la orden sigue pendiente, sin Gerente ni fecha, sin entregas esperadas, sin
        tránsito, sin notificación, correo ni log parcial."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    ordenes.aprobar_orden(self.gerente, self.orden.pk)
        self.assertEqual(pendientes, [])
        self.sin_cambios()


class RechazarOrdenTests(AprobacionBase):
    """Extensiones 5a y 5b, postcondiciones i a l y la regla «Rechazo»."""

    def test_ext_5b_el_motivo_es_obligatorio_y_no_cambia_nada(self):
        """Extensión 5b y regla «Rechazo»: sin motivo (o solo espacios) se rechaza con ``motivo_obligatorio`` en el campo ``motivo``."""
        for motivo in ("", "   ", None):
            with self.subTest(motivo=motivo):
                with self.assertRaises(ValidationError) as contexto:
                    ordenes.rechazar_orden(self.gerente, self.orden.pk, motivo)
                self.assertEqual(contexto.exception.error_dict["motivo"][0].code, "motivo_obligatorio")
        self.sin_cambios()

    def test_post_a_e_i_queda_rechazada_con_el_motivo_el_gerente_y_la_fecha(self):
        """Postcondiciones a e i: «rechazada», fecha de resolución de hoy, Gerente y motivo (recortado)."""
        self.rechazar("  " + MOTIVO + "  ")
        orden = OrdenCompra.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden_compra, orden.fecha_resolucion, orden.gerente_id, orden.motivo_rechazo), ("rechazada", self.hoy, self.gerente.pk, MOTIVO))

    def test_post_j_las_cotizaciones_seleccionadas_pasan_a_descartada_y_el_pedido_sigue_cerrado(self):
        """Postcondición j y regla «Estado del pedido»: las seleccionadas de la orden pasan a «descartada»; el pedido sigue «cerrado»."""
        self.rechazar()
        self.assertEqual(set(Cotizacion.objects.filter(pedido=self.pedido).values_list("estado_cotizacion", flat=True)), {"descartada"})
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "cerrado")

    def test_post_l_no_cambia_el_transito_ni_la_fecha_de_entrega_esperada(self):
        """Postcondición l: rechazar no toca el tránsito ni las fechas de entrega."""
        self.rechazar()
        self.assertEqual((self.transito(self.lechuga_iin), self.transito(self.tomate_iin)), (Decimal("0"), Decimal("0")))
        self.assertEqual(set(DetalleOrdenCompra.objects.values_list("fecha_entrega_esperada", flat=True)), {None})

    def test_post_k_cada_proveedor_de_la_orden_recibe_el_aviso_de_que_no_fue_seleccionada(self):
        """Postcondición k y regla «Rechazo»: un correo a cada proveedor de la orden (A y B; no a C, que ya fue avisado al generar). Indica el pedido, la fecha
        de su cotización y su monto; **no** el motivo ni a los otros proveedores."""
        self.rechazar()
        por_destino = {m.to[0]: m.body for m in mail.outbox}
        self.assertEqual(set(por_destino), {"ventas@sur.com", "info@este.com"})
        for cuerpo in por_destino.values():
            self.assertIn(str(self.pedido), cuerpo)
            self.assertIn("no fue seleccionada", cuerpo)
            self.assertNotIn(MOTIVO, cuerpo)
        self.assertRegex(por_destino["ventas@sur.com"], r"320[.,]00")
        self.assertNotIn("Viveros del Este", por_destino["ventas@sur.com"])
        self.assertNotIn("Semillas del Sur", por_destino["info@este.com"])

    def test_post_c_se_notifica_al_agronomo_el_rechazo_con_su_motivo(self):
        """Postcondición c y regla «Avisos»: la notificación al Agrónomo indica la orden, el pedido, la decisión, el monto y el motivo."""
        self.rechazar()
        notificacion = Notificacion.objects.get(destinatario=self.ana)
        texto = f"{notificacion.titulo} {notificacion.detalle}"
        for esperado in (str(self.orden), str(self.pedido), "rechazada", "420", MOTIVO):
            self.assertIn(esperado, texto)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente).exists())

    def test_ext_4a_y_4b_con_un_destino_inactivo_o_una_cotizacion_vencida_se_puede_rechazar(self):
        """Extensiones 4a y 4b: «el Gerente rechaza la orden o abandona»: rechazar siempre se puede, aunque la aprobación esté bloqueada."""
        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="inactivo")
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        self.rechazar(motivo=ordenes.motivo_propuesto(self.orden))
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "rechazada")

    def test_p1_el_motivo_propuesto_es_valido_como_motivo_del_rechazo(self):
        """P1: el motivo propuesto se puede usar tal cual (no vacío) cuando una cotización venció."""
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        self.rechazar(motivo=ordenes.motivo_propuesto(self.orden))
        self.assertTrue(OrdenCompra.objects.get(pk=self.orden.pk).motivo_rechazo.startswith("La cotización de Viveros del Este"))

    def test_post_m_un_registro_de_auditoria_con_la_orden_y_sus_cotizaciones_sin_tocar_el_stock(self):
        """Postcondición m: ``rechazo_orden_compra`` con la orden y cada cotización modificada entre los afectados y el cambio de estado y el motivo; no hay
        ``modificacion_insumo_invernadero`` (no cambia el tránsito)."""
        self.rechazar()
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.RECHAZO_ORDEN_COMPRA)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertTrue({("compras.ordencompra", self.orden.pk), ("compras.cotizacion", self.cot_a.pk), ("compras.cotizacion", self.cot_b.pk)} <= afectados)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "pendiente_aprobacion", "despues": "rechazada"})
        self.assertEqual(registro.detalle["cambios"]["motivo_rechazo"], {"antes": None, "despues": MOTIVO})
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_insumo_invernadero").exists())

    def test_ext_5a_5a_la_orden_ya_resuelta_no_se_rechaza(self):
        """Extensión 5a.5a (se aplica la 8a): si al registrar la orden ya no está pendiente se informa la decisión tomada y no se cambia nada."""
        self.rechazar()
        error = self.error(ordenes.rechazar_orden, self.gerente, self.orden.pk, "Otro motivo")
        self.assertEqual((error.codigo, error.datos["estado"], error.datos["motivo_rechazo"]), ("orden_no_pendiente", "rechazada", MOTIVO))
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).motivo_rechazo, MOTIVO)

    def test_regla_rechazo_una_orden_rechazada_no_se_reabre_y_el_pedido_no_admite_otra_orden(self):
        """Regla «Rechazo» y «Una orden por pedido»: una orden rechazada no se reabre; el pedido sigue «cerrado» y lo no comprado se resuelve con un pedido nuevo."""
        self.rechazar()
        self.assertEqual(self.error(ordenes.aprobar_orden, self.gerente, self.orden.pk).codigo, "orden_no_pendiente")
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "cerrado")

    def test_paso_5a_3_el_resumen_del_rechazo_dice_que_se_descarta_y_a_quien_se_avisa(self):
        """Extensión 5a.3: el motivo, las cotizaciones que pasarán a «descartada» y los proveedores a los que se les avisará; no escribe nada."""
        resumen = ordenes.resumir_rechazo(self.gerente, self.orden.pk, "  " + MOTIVO + " ")
        self.assertEqual(resumen.motivo, MOTIVO)
        self.assertEqual(sorted(c.pk for c in resumen.descartadas), sorted([self.cot_a.pk, self.cot_b.pk]))
        self.assertEqual(sorted(p.pk for p in resumen.proveedores), sorted([self.a.pk, self.b.pk]))
        self.sin_cambios()

    def test_paso_5a_3_el_resumen_exige_el_motivo_y_una_orden_pendiente(self):
        with self.assertRaises(ValidationError):
            ordenes.resumir_rechazo(self.gerente, self.orden.pk, "")
        self.rechazar()
        self.assertEqual(self.error(ordenes.resumir_rechazo, self.gerente, self.orden.pk, MOTIVO).codigo, "orden_no_pendiente")

    def test_garantia_si_falla_la_auditoria_el_rechazo_no_deja_nada(self):
        """Garantías mínimas: el rechazo es atómico; si falla, la orden sigue pendiente y no sale ningún aviso."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    ordenes.rechazar_orden(self.gerente, self.orden.pk, MOTIVO)
        self.assertEqual(pendientes, [])
        self.sin_cambios()
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).motivo_rechazo, "")
