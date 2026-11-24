# Pruebas de CMP-GNR-ODC · Generar Orden de Compra (CMP-03, paso 3): ``pedidos_resolubles``, ``comparacion``, ``resumir_orden`` y ``generar_orden`` de
# ``compras/servicios/ordenes.py``. Fuente: docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-GNR-ODC v0.2: precondiciones a y b, garantías mínimas,
# postcondiciones a a h, flujo básico, extensiones *a, *b, 1a, 1a1, 4a, 4b, 4c, 5a, 6a, 6b, 8a, 10a, 11a, 11b, 12a y 12b, y las reglas «Pedido resoluble»,
# «Agrónomo del pedido», «Una orden por pedido», «Cotización elegida completa», «Cobertura mínima de un detalle», «Proveedor inactivo», «Cotización con la
# validez vencida», «Presentación», «Detalles de la orden», «Resolución en una sola operación», «Monto de la orden», «Avisos» y «Cantidad en tránsito»),
# «Actualizaciones de A0 que mandan» (precio unitario calculado, cantidad cotizada) y D-87, D-89 y D-42.
#
# API que fijan estas pruebas (todas dentro de ``compras/servicios/ordenes.py``; el módulo se toma dentro de cada prueba con ``perezoso``):
#   pedidos_resolubles(actor)                     -> list[FilaResoluble(pedido, detalles, cotizaciones, alcanzan)]
#   comparacion(actor, pedido_id)                 -> Comparacion(pedido, cotizaciones, detalles, puede_generar)
#       cotizaciones: list[CotizacionComparada(cotizacion, proveedor, lineas, monto, elegible, motivo)]  (motivo: None, «proveedor_inactivo» o «validez_vencida»)
#       detalles:     list[DetalleComparado(detalle, pedida, minima, referencia, lineas, problema)]       (problema: None, «sin_ofertas» u «ofertas_insuficientes»)
#       lineas de un detalle: list[LineaComparada(cotizacion, proveedor, cantidad, unitario, plazo, elegible)], del unitario más barato al más caro
#   resumir_orden(actor, pedido_id, cotizacion_ids, observaciones="") -> ResumenDeOrden(pedido, proveedores, coberturas, excesos, monto_total, monto_estimado,
#                                                                         diferencia, diferencia_porcentaje, descartadas, observaciones)
#   generar_orden(actor, pedido_id, cotizacion_ids, observaciones="") -> OrdenCompra   (con el atributo ``sin_gerente_activo``)
# Errores: ``PermissionDenied`` (no es el Agrónomo activo del pedido), ``Http404`` (pedido inexistente) y ``ErrorDeCompras`` con estos códigos:
#   pedido_no_en_cotizacion (1a1 y 11a; ``datos``: ``estado`` y, si tiene orden, ``orden_id``), pedido_no_vencido (precondición b),
#   sin_cotizaciones_elegidas, cotizacion_repetida (el mismo id dos veces), cotizacion_invalida (no es una «propuesta» de ese pedido), cotizacion_no_elegible (4b, 4c y 11b; ``datos["afectadas"]``:
#   ``[(cotizacion_id, motivo)]``) y cobertura_insuficiente (4a y 8a; ``datos["faltantes"]``: ``{detalle_id: falta}``).
# Los correos salen en ``on_commit`` (``captureOnCommitCallbacks``); la notificación al Gerente, dentro de la transacción (D-42).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, override_settings
from django.utils import timezone

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, OrdenCompra, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, orden_de, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import ACCIONES_DE_NEGOCIO, Notificacion, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero, MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.models import Alerta
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero

ordenes = perezoso("compras.servicios.ordenes")


@override_settings(CORREO_CONFIGURADO=True)
class GeneracionBase(ConDatosDeInventario, TestCase):
    """Ana (invernadero Norte) hizo un pedido de 20 lechugas (referencia $12,50: $250) y 20 tomates (referencia $10: $200); estimado $450. Venció ayer.
    Tolerancia 10 % (mínimo 18 de cada uno). Tres proveedores: A cotizó 20 lechugas ($240, 3 días) y 10 tomates ($90, 4 días); B, 10 tomates ($100, 5 días);
    C, 10 lechugas ($130, 2 días). Hay un Gerente activo."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.gerente = crear_gerente()
        self.lechuga_iin = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=20, precio="12.50")
        self.tomate_iin = existencia(insumo("Tomate", unidad="unidad"), self.norte, minimo=20, precio="10.00")
        self.poner_tolerancia(10)
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.c = proveedor("Hortalizas del Oeste S. A.", n=3, email="hola@oeste.com")
        self.pedido = armar_pedido(self.ana)
        self.lechuga = detalle_de_pedido(self.pedido, self.lechuga_iin, cantidad="20")
        self.tomate = detalle_de_pedido(self.pedido, self.tomate_iin, cantidad="20")
        self.vencer(self.pedido)
        self.cot_a = cotizacion_de(self.pedido, self.a, [(self.lechuga, 20, "240.00", 3), (self.tomate, 10, "90.00", 4)])
        self.cot_b = cotizacion_de(self.pedido, self.b, [(self.tomate, 10, "100.00", 5)])
        self.cot_c = cotizacion_de(self.pedido, self.c, [(self.lechuga, 10, "130.00", 2)])

    def poner_tolerancia(self, porcentaje):
        """La tolerancia de cobertura de la configuración operativa."""
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = porcentaje
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])

    def vencer(self, pedido):
        """Deja la fecha límite del ``pedido`` en ayer (el día de la fecha límite todavía se cotiza: venció si hoy es posterior)."""
        Pedido.objects.filter(pk=pedido.pk).update(fecha_pedido=self.hoy - timedelta(days=5), fecha_limite_cotizaciones=self.hoy - timedelta(days=1))
        pedido.refresh_from_db()

    def ids(self, *cotizaciones):
        return [c.pk for c in cotizaciones]

    def generar(self, *cotizaciones, actor=None, observaciones="", pedido=None):
        """``generar_orden`` con los correos ejecutados; devuelve la orden."""
        with self.captureOnCommitCallbacks(execute=True):
            return ordenes.generar_orden(actor or self.ana, (pedido or self.pedido).pk, self.ids(*cotizaciones), observaciones)

    def codigo_del_error(self, funcion, *args, **kwargs):
        """El código del ``ErrorDeCompras`` que lanza ``funcion`` (falla la prueba si no lanza ninguno)."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            funcion(*args, **kwargs)
        return contexto.exception

    def sin_cambios(self, cotizaciones=None):
        """Nada se generó: sin orden, pedido «en cotización», cotizaciones «propuesta» (las ``cotizaciones`` indicadas o todas las del pedido), sin
        notificaciones, correos ni auditoría de la generación."""
        self.assertEqual(OrdenCompra.objects.count(), 0)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "en_cotizacion")
        consulta = Cotizacion.objects.filter(pedido=self.pedido) if cotizaciones is None else Cotizacion.objects.filter(pk__in=self.ids(*cotizaciones))
        self.assertEqual(set(consulta.values_list("estado_cotizacion", flat=True)), {"propuesta"})
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="generacion_orden_compra").count(), 0)


class PedidosResolublesTests(GeneracionBase):
    """Pasos 2 y 3 y la regla «Pedido resoluble»: los pedidos del Agrónomo en cotización, con la fecha límite vencida y al menos una cotización propuesta."""

    def test_paso_2_lista_el_pedido_con_sus_detalles_cotizaciones_y_si_alcanzan(self):
        """Paso 2: por pedido, el identificador, la fecha, la fecha límite, la cantidad de detalles, de cotizaciones recibidas y si alcanzan para cubrirlo."""
        (fila,) = ordenes.pedidos_resolubles(self.ana)
        self.assertEqual(fila.pedido, self.pedido)
        self.assertEqual((fila.detalles, fila.cotizaciones), (2, 3))
        self.assertTrue(fila.alcanzan)

    def test_paso_2_dice_cuando_las_cotizaciones_no_alcanzan(self):
        """Paso 2 y regla «Aviso de vencimiento»: «si las cotizaciones recibidas alcanzan para cubrirlo»; con una sola de 10 lechugas no alcanzan."""
        otro = armar_pedido(self.ana)
        detalle = detalle_de_pedido(otro, self.lechuga_iin, cantidad="20")
        self.vencer(otro)
        cotizacion_de(otro, self.c, [(detalle, 10, "130.00", 2)])
        filas = {f.pedido.pk: f for f in ordenes.pedidos_resolubles(self.ana)}
        self.assertFalse(filas[otro.pk].alcanzan)
        self.assertTrue(filas[self.pedido.pk].alcanzan)

    def test_regla_pedido_resoluble_exige_fecha_limite_vencida(self):
        """Regla «Pedido resoluble» y precondición b: el día de la fecha límite todavía se cotiza; recién al día siguiente se puede resolver."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy)
        self.assertEqual(ordenes.pedidos_resolubles(self.ana), [])
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy - timedelta(days=1))
        self.assertEqual(len(ordenes.pedidos_resolubles(self.ana)), 1)

    def test_regla_pedido_resoluble_exige_estar_en_cotizacion(self):
        """Regla «Pedido resoluble»: un pedido cerrado o cancelado no se lista."""
        for estado, causa in (("cerrado", None), ("cancelado", "manual")):
            with self.subTest(estado=estado):
                Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido=estado, causa_cancelacion=causa, motivo_cancelacion="x", fecha_cierre_pedido=self.hoy)
                self.assertEqual(ordenes.pedidos_resolubles(self.ana), [])

    def test_regla_pedido_resoluble_exige_al_menos_una_cotizacion_propuesta(self):
        """Regla «Pedido resoluble»: sin cotizaciones «propuesta» no hay nada que elegir (lo cancela el paso diario 60, «nadie cotizó»)."""
        Cotizacion.objects.filter(pedido=self.pedido).update(estado_cotizacion="descartada")
        self.assertEqual(ordenes.pedidos_resolubles(self.ana), [])

    def test_regla_agronomo_del_pedido_solo_ve_los_suyos(self):
        """Regla «Agrónomo del pedido»: solo el Agrónomo que hizo el pedido lo resuelve; otro Agrónomo no lo ve."""
        beto, _ = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.assertEqual(ordenes.pedidos_resolubles(beto), [])

    def test_precondicion_a_solo_un_agronomo_activo(self):
        """Precondición a: el Gerente, otros roles y una cuenta inactiva no generan órdenes (``PermissionDenied``)."""
        inactiva = crear_agronomo(email="baja@infoponia.com", activo=False)
        for cuenta in (self.gerente, crear_capataz(), crear_administrador(), inactiva, None):
            with self.subTest(cuenta=cuenta):
                with self.assertRaises(PermissionDenied):
                    ordenes.pedidos_resolubles(cuenta)


class ComparacionTests(GeneracionBase):
    """Paso 4 y las reglas «Presentación», «Proveedor inactivo» y «Cotización con la validez vencida»: las dos vistas, solo lectura."""

    def comparar(self, actor=None, pedido=None):
        return ordenes.comparacion(actor or self.ana, (pedido or self.pedido).pk)

    def test_paso_4_presenta_cada_cotizacion_propuesta_con_su_proveedor_y_su_monto(self):
        """Paso 4, primera vista: por cotización, el proveedor, sus líneas y el monto total (Σ de los totales de línea)."""
        comparacion = self.comparar()
        por_proveedor = {c.proveedor: c for c in comparacion.cotizaciones}
        self.assertEqual(set(por_proveedor), {self.a, self.b, self.c})
        self.assertEqual(por_proveedor[self.a].cotizacion, self.cot_a)
        self.assertEqual(por_proveedor[self.a].monto, Decimal("330.00"))
        self.assertEqual(len(por_proveedor[self.a].lineas), 2)
        self.assertTrue(all(c.elegible and c.motivo is None for c in comparacion.cotizaciones))

    def test_paso_4_presenta_por_cada_detalle_pedida_minima_y_referencia(self):
        """Paso 4, segunda vista: por detalle, la cantidad pedida, la mínima a cubrir (con la tolerancia) y el precio de referencia."""
        por_detalle = {d.detalle: d for d in self.comparar().detalles}
        lechuga = por_detalle[self.lechuga]
        self.assertEqual((lechuga.pedida, lechuga.minima, lechuga.referencia), (Decimal("20"), Decimal("18"), Decimal("12.50")))

    def test_regla_presentacion_las_lineas_de_un_detalle_van_del_unitario_mas_barato_al_mas_caro(self):
        """Regla «Presentación» y A0 (MD-125): se ordenan por el precio unitario calculado (total ÷ cantidad cotizada, 4 decimales); A: 240/20 = 12; C: 130/10 = 13."""
        por_detalle = {d.detalle: d for d in self.comparar().detalles}
        lechuga = por_detalle[self.lechuga]
        self.assertEqual([l.proveedor for l in lechuga.lineas], [self.a, self.c])
        self.assertEqual([l.unitario for l in lechuga.lineas], [Decimal("12.0000"), Decimal("13.0000")])
        tomate = por_detalle[self.tomate]
        self.assertEqual([l.proveedor for l in tomate.lineas], [self.a, self.b])  # A: 9,00 · B: 10,00
        self.assertEqual([l.plazo for l in tomate.lineas], [4, 5])
        self.assertEqual([l.cantidad for l in tomate.lineas], [Decimal("10.000"), Decimal("10.000")])

    def test_regla_presentacion_el_sistema_no_preselecciona_ninguna_cotizacion(self):
        """Regla «Presentación»: no hay ninguna cotización elegida de antemano; las cotizaciones siguen «propuesta» y la vista no escribe nada."""
        self.comparar()
        self.assertEqual(set(Cotizacion.objects.values_list("estado_cotizacion", flat=True)), {"propuesta"})
        self.assertEqual(OrdenCompra.objects.count(), 0)

    def test_puede_generar_dice_si_las_elegibles_cubren_todos_los_detalles(self):
        """Pasos 4 y 8: si con todas las elegibles cada detalle alcanza su mínimo, se puede generar."""
        self.assertTrue(self.comparar().puede_generar)

    def test_ext_4a_un_detalle_sin_lineas_se_marca_sin_ofertas_y_no_se_puede_generar(self):
        """Extensión 4a: «sin ofertas»; el pedido no podrá generar una orden (se resuelve con Cancelar Pedido)."""
        Cotizacion.objects.filter(pk__in=[self.cot_a.pk, self.cot_c.pk]).update(estado_cotizacion="descartada")
        # Sin las cotizaciones de A y C solo queda B (10 tomates): la lechuga no tiene ninguna línea.
        comparacion = self.comparar()
        problemas = {d.detalle: d.problema for d in comparacion.detalles}
        self.assertEqual(problemas[self.lechuga], "sin_ofertas")
        self.assertEqual(problemas[self.tomate], "ofertas_insuficientes")
        self.assertFalse(comparacion.puede_generar)

    def test_ext_4a_ofertas_insuficientes_cuando_todas_juntas_no_alcanzan_el_minimo(self):
        """Extensión 4a: la suma de todas las líneas que lo cotizan no alcanza la mínima (B + C: 10 tomates y 10 lechugas, mínimo 18)."""
        Cotizacion.objects.filter(pk=self.cot_a.pk).update(estado_cotizacion="descartada")
        comparacion = self.comparar()
        self.assertEqual({d.problema for d in comparacion.detalles}, {"ofertas_insuficientes"})
        self.assertFalse(comparacion.puede_generar)

    def test_ext_4b_una_cotizacion_de_un_proveedor_inactivo_se_muestra_pero_no_se_puede_elegir(self):
        """Extensión 4b y regla «Proveedor inactivo»: se conserva y se indica «proveedor inactivo»; no es elegible."""
        self.c.estado_proveedor = "inactivo"
        self.c.save(update_fields=["estado_proveedor"])
        por_proveedor = {c.proveedor: c for c in self.comparar().cotizaciones}
        self.assertFalse(por_proveedor[self.c].elegible)
        self.assertEqual(por_proveedor[self.c].motivo, "proveedor_inactivo")
        self.assertTrue(por_proveedor[self.a].elegible)

    def test_ext_4c_una_cotizacion_con_la_validez_vencida_se_muestra_pero_no_se_puede_elegir(self):
        """Extensión 4c y regla «Cotización con la validez vencida»: «validez vencida»; la fecha de validez de hoy todavía sirve, la de ayer no."""
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        Cotizacion.objects.filter(pk=self.cot_c.pk).update(fecha_validez_cotizacion=self.hoy)
        por_proveedor = {c.proveedor: c for c in self.comparar().cotizaciones}
        self.assertEqual((por_proveedor[self.b].elegible, por_proveedor[self.b].motivo), (False, "validez_vencida"))
        self.assertEqual((por_proveedor[self.c].elegible, por_proveedor[self.c].motivo), (True, None))

    def test_ext_4b_y_4c_sin_esa_cotizacion_un_detalle_que_no_alcanza_aplica_la_extension_4a(self):
        """Extensiones 4b y 4c: «si, sin esa cotización, algún detalle no alcanza la cobertura mínima, se aplica la extensión 4a»: A vencida deja la lechuga en
        10 (C) y los tomates en 10 (B), ambos bajo 18."""
        Cotizacion.objects.filter(pk=self.cot_a.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        comparacion = self.comparar()
        self.assertFalse(comparacion.puede_generar)
        self.assertEqual({d.problema for d in comparacion.detalles}, {"ofertas_insuficientes"})

    def test_regla_presentacion_las_lineas_de_una_cotizacion_no_elegible_se_muestran_marcadas(self):
        """Regla «Presentación»: la tabla del detalle muestra las líneas de todas las «propuesta»; las de una no elegible vienen marcadas como no elegibles."""
        self.c.estado_proveedor = "inactivo"
        self.c.save(update_fields=["estado_proveedor"])
        lechuga = {d.detalle: d for d in self.comparar().detalles}[self.lechuga]
        self.assertEqual({l.proveedor: l.elegible for l in lechuga.lineas}, {self.a: True, self.c: False})

    def test_regla_cantidad_cotizada_puede_superar_la_pedida_y_cubre(self):
        """A0 (P2, D-89 punto 3): la cobertura suma la cantidad cotizada aunque supere la pedida; con 30 lechugas cotizadas el detalle está cubierto."""
        otro = armar_pedido(self.ana)
        detalle = detalle_de_pedido(otro, self.lechuga_iin, cantidad="20")
        self.vencer(otro)
        cotizacion_de(otro, self.c, [(detalle, 30, "390.00", 2)])
        comparacion = ordenes.comparacion(self.ana, otro.pk)
        (detalle_comparado,) = comparacion.detalles
        self.assertIsNone(detalle_comparado.problema)
        self.assertTrue(comparacion.puede_generar)

    def test_ext_1a1_un_pedido_que_ya_no_esta_en_cotizacion_informa_su_estado_y_su_orden(self):
        """Extensión 1a1: si el pedido del aviso ya no está «en cotización», se informa su estado y, si tiene orden, su identificador."""
        orden = orden_de(self.pedido, [self.cot_a, self.cot_b])
        error = self.codigo_del_error(self.comparar)
        self.assertEqual(error.codigo, "pedido_no_en_cotizacion")
        self.assertEqual(error.datos["estado"], "cerrado")
        self.assertEqual(error.datos["orden_id"], orden.pk)

    def test_ext_1a1_un_pedido_cancelado_informa_su_estado_sin_orden(self):
        """Extensión 1a1: un pedido cancelado informa el estado y no trae identificador de orden."""
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="cancelado", causa_cancelacion="manual", motivo_cancelacion="x", fecha_cierre_pedido=self.hoy)
        error = self.codigo_del_error(self.comparar)
        self.assertEqual((error.codigo, error.datos["estado"]), ("pedido_no_en_cotizacion", "cancelado"))
        self.assertIsNone(error.datos.get("orden_id"))

    def test_precondicion_b_un_pedido_con_la_fecha_limite_sin_vencer_no_se_resuelve(self):
        """Precondición b: la fecha límite ya venció; mientras se puede cotizar, no se compara ni se genera."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy)
        self.assertEqual(self.codigo_del_error(self.comparar).codigo, "pedido_no_vencido")

    def test_regla_agronomo_del_pedido_otro_agronomo_no_lo_abre_y_uno_inexistente_es_404(self):
        """Regla «Agrónomo del pedido» y requisito especial: solo el Agrónomo que hizo el pedido accede (``PermissionDenied``); un pedido que no existe, 404."""
        beto, _ = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        for cuenta in (beto, self.gerente):
            with self.subTest(cuenta=cuenta):
                with self.assertRaises(PermissionDenied):
                    self.comparar(cuenta)
        with self.assertRaises(Http404):
            ordenes.comparacion(self.ana, 99999)


class ResumenDeLaOrdenTests(GeneracionBase):
    """Paso 9 y las reglas «Monto de la orden», «Cobertura mínima» y extensión 6b: lo que se generaría, sin escribir nada."""

    def resumir(self, *cotizaciones, observaciones=""):
        return ordenes.resumir_orden(self.ana, self.pedido.pk, self.ids(*cotizaciones), observaciones)

    def test_paso_9_agrupa_las_lineas_por_proveedor_con_su_monto(self):
        """Paso 9: por cada proveedor elegido, sus líneas y el monto de ellas."""
        resumen = self.resumir(self.cot_a, self.cot_b)
        por_proveedor = {p.proveedor: p for p in resumen.proveedores}
        self.assertEqual(set(por_proveedor), {self.a, self.b})
        self.assertEqual(por_proveedor[self.a].monto, Decimal("330.00"))
        self.assertEqual(por_proveedor[self.b].monto, Decimal("100.00"))
        self.assertEqual(len(por_proveedor[self.a].lineas), 2)

    def test_regla_monto_de_la_orden_total_estimado_y_diferencia_en_pesos_y_porcentaje(self):
        """Regla «Monto de la orden»: total 430 (240 + 90 + 100), estimado 450 (250 + 200), diferencia −20 y −4,4 % (un decimal)."""
        resumen = self.resumir(self.cot_a, self.cot_b)
        self.assertEqual(resumen.monto_total, Decimal("430.00"))
        self.assertEqual(resumen.monto_estimado, Decimal("450.00"))
        self.assertEqual(resumen.diferencia, Decimal("-20.00"))
        self.assertEqual(resumen.diferencia_porcentaje, Decimal("-4.4"))

    def test_paso_9_muestra_la_cantidad_comprada_frente_a_la_pedida_por_detalle(self):
        """Paso 9: por detalle, lo comprado frente a lo pedido (20 lechugas, 20 tomates)."""
        resumen = self.resumir(self.cot_a, self.cot_b)
        self.assertEqual(resumen.coberturas[self.lechuga.pk].cotizada, Decimal("20.000"))
        self.assertEqual(resumen.coberturas[self.tomate.pk].cotizada, Decimal("20.000"))
        self.assertTrue(all(c.cubierto for c in resumen.coberturas.values()))

    def test_paso_9_indica_las_cotizaciones_que_se_descartaran_y_las_observaciones(self):
        """Paso 9: las cotizaciones «propuesta» no elegidas (se descartarán) y las observaciones."""
        resumen = self.resumir(self.cot_a, self.cot_b, observaciones="  Entregar a la mañana.  ")
        self.assertEqual(resumen.descartadas, [self.cot_c])
        self.assertEqual(resumen.observaciones, "Entregar a la mañana.")

    def test_ext_6b_comprar_de_mas_solo_advierte_e_informa_la_diferencia_de_cada_detalle(self):
        """Extensión 6b: si la suma de un detalle supera lo pedido se advierte la diferencia y se permite. A (20 L, 10 T) + C (10 L) = 30 lechugas: 10 de más."""
        resumen = self.resumir(self.cot_a, self.cot_b, self.cot_c)
        self.assertEqual([(d.pk, sobra) for d, sobra in resumen.excesos], [(self.lechuga.pk, Decimal("10.000"))])

    def test_el_resumen_sin_exceso_no_trae_advertencias(self):
        """Extensión 6b: sin sobrante, ``excesos`` queda vacío."""
        self.assertEqual(self.resumir(self.cot_a, self.cot_b).excesos, [])

    def test_ext_8a_un_detalle_sin_cubrir_se_senala_con_cuanto_le_falta(self):
        """Extensión 8a y regla «Cobertura mínima»: «señala los detalles no cubiertos y cuánto les falta». Solo B: lechuga 18 de falta, tomate 8."""
        error = self.codigo_del_error(ordenes.resumir_orden, self.ana, self.pedido.pk, self.ids(self.cot_b))
        self.assertEqual(error.codigo, "cobertura_insuficiente")
        self.assertEqual(error.datos["faltantes"], {self.lechuga.pk: Decimal("18"), self.tomate.pk: Decimal("8")})

    def test_ext_8_sin_ninguna_cotizacion_elegida_no_hay_orden(self):
        """Paso 8: sin cotizaciones elegidas no hay nada que resumir."""
        self.assertEqual(self.codigo_del_error(ordenes.resumir_orden, self.ana, self.pedido.pk, []).codigo, "sin_cotizaciones_elegidas")

    def test_regla_cotizacion_elegida_completa_una_cotizacion_repetida_se_rechaza(self):
        """Regla «Cotización elegida completa» (paso 6): cada cotización se elige una sola vez; el mismo id dos veces es ``cotizacion_repetida`` y no cuenta
        doble en la cobertura (A dos veces daría 40 lechugas y 20 tomates, pero es una sola cotización)."""
        for funcion in (ordenes.resumir_orden, ordenes.generar_orden):
            with self.subTest(funcion=funcion.__name__):
                error = self.codigo_del_error(funcion, self.ana, self.pedido.pk, [self.cot_a.pk, self.cot_b.pk, self.cot_a.pk])
                self.assertEqual(error.codigo, "cotizacion_repetida")
        self.sin_cambios()

    def test_regla_cotizacion_elegida_completa_una_de_otro_pedido_o_ya_resuelta_es_invalida(self):
        """Regla «Cotización elegida completa»: solo cotizaciones «propuesta» de este pedido; las de otro pedido o las ya descartadas no se eligen."""
        otro = armar_pedido(self.ana)
        detalle = detalle_de_pedido(otro, self.lechuga_iin, cantidad="20")
        ajena = cotizacion_de(otro, self.a, [(detalle, 20, "240.00", 3)])
        Cotizacion.objects.filter(pk=self.cot_c.pk).update(estado_cotizacion="descartada")
        for elegidas in ([self.cot_a, ajena], [self.cot_a, self.cot_c], [self.cot_a, self.cot_b, 99999]):
            with self.subTest(elegidas=elegidas):
                ids = [getattr(c, "pk", c) for c in elegidas]
                self.assertEqual(self.codigo_del_error(ordenes.resumir_orden, self.ana, self.pedido.pk, ids).codigo, "cotizacion_invalida")

    def test_ext_4b_y_4c_una_cotizacion_no_elegible_no_se_puede_elegir(self):
        """Extensiones 4b y 4c: elegir la cotización de un proveedor inactivo o con la validez vencida se rechaza y dice cuál y por qué."""
        self.b.estado_proveedor = "inactivo"
        self.b.save(update_fields=["estado_proveedor"])
        Cotizacion.objects.filter(pk=self.cot_c.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        error = self.codigo_del_error(ordenes.resumir_orden, self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b, self.cot_c))
        self.assertEqual(error.codigo, "cotizacion_no_elegible")
        self.assertEqual(sorted(error.datos["afectadas"]), sorted([(self.cot_b.pk, "proveedor_inactivo"), (self.cot_c.pk, "validez_vencida")]))

    def test_el_resumen_no_escribe_nada(self):
        """Pasos 7 a 9: es solo lectura; no crea orden, no cambia estados, no notifica ni audita."""
        self.resumir(self.cot_a, self.cot_b, observaciones="x")
        self.sin_cambios()

    def test_el_resumen_valida_lo_mismo_que_generar_el_pedido_y_el_actor(self):
        """El resumen aplica las mismas precondiciones: otro Agrónomo (``PermissionDenied``), pedido sin vencer o ya cerrado (``ErrorDeCompras``)."""
        beto, _ = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        with self.assertRaises(PermissionDenied):
            ordenes.resumir_orden(beto, self.pedido.pk, self.ids(self.cot_a, self.cot_b))
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy)
        self.assertEqual(self.codigo_del_error(self.resumir, self.cot_a, self.cot_b).codigo, "pedido_no_vencido")


class CoberturaDeLaReglaTests(GeneracionBase):
    """Los cuatro ejemplos de la regla «Cobertura mínima de un detalle»: se piden 20 lechugas y 20 tomates, tolerancia 10 % (mínimo 18 de cada uno)."""

    def armar(self, a, b):
        """Descarta las cotizaciones del setUp y crea las de dos proveedores nuevos, D y E, con las cantidades ``(lechugas, tomates)`` indicadas
        (``None``: no cotiza ese insumo). Devuelve las dos nuevas."""
        Cotizacion.objects.filter(pedido=self.pedido).update(estado_cotizacion="descartada")
        d, e = proveedor("Vivero D", n=5, email="d@vivero.com"), proveedor("Vivero E", n=6, email="e@vivero.com")
        elegidas = []
        for proveedor_, (lechugas, tomates) in ((d, a), (e, b)):
            lineas = []
            if lechugas is not None:
                lineas.append((self.lechuga, lechugas, "100.00", 2))
            if tomates is not None:
                lineas.append((self.tomate, tomates, "50.00", 2))
            elegidas.append(cotizacion_de(self.pedido, proveedor_, lineas))
        return elegidas

    def test_ejemplo_1_a_20l_10t_mas_b_10t_se_genera(self):
        """Ejemplo 1 de la regla: A (20 L, 10 T) + B (10 T): se genera."""
        orden = self.generar(*self.armar((20, 10), (None, 10)))
        self.assertEqual(orden.pedido, self.pedido)

    def test_ejemplo_2_a_15l_10t_mas_b_10l_10t_se_genera_con_advertencia_de_5_lechugas_de_mas(self):
        """Ejemplo 2 de la regla: A (15 L, 10 T) + B (10 L, 10 T): se genera, con advertencia de 5 lechugas de más."""
        elegidas = self.armar((15, 10), (10, 10))
        resumen = ordenes.resumir_orden(self.ana, self.pedido.pk, self.ids(*elegidas))
        self.assertEqual([(d.pk, sobra) for d, sobra in resumen.excesos], [(self.lechuga.pk, Decimal("5.000"))])
        self.assertEqual(self.generar(*elegidas).detalles.count(), 4)

    def test_ejemplo_3_a_19l_10t_mas_b_10t_se_genera(self):
        """Ejemplo 3 de la regla: A (19 L, 10 T) + B (10 T): se genera (19 ≥ 18)."""
        self.generar(*self.armar((19, 10), (None, 10)))
        self.assertEqual(OrdenCompra.objects.count(), 1)

    def test_ejemplo_4_a_15l_10t_mas_b_10t_no_se_genera(self):
        """Ejemplo 4 de la regla: A (15 L, 10 T) + B (10 T): no se genera; a la lechuga le faltan 3 para el mínimo de 18."""
        elegidas = self.armar((15, 10), (None, 10))
        error = self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(*elegidas))
        self.assertEqual(error.codigo, "cobertura_insuficiente")
        self.assertEqual(error.datos["faltantes"], {self.lechuga.pk: Decimal("3")})
        self.sin_cambios(elegidas)

    def test_regla_la_tolerancia_sale_de_la_configuracion_y_no_de_una_copia(self):
        """Regla «Cobertura mínima»: la tolerancia es un porcentaje de la configuración operativa; con 0 % hay que cubrir 20 y 19 ya no alcanza."""
        elegidas = self.armar((19, 10), (None, 10))
        self.poner_tolerancia(0)
        self.assertEqual(self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(*elegidas)).codigo, "cobertura_insuficiente")


class GenerarOrdenTests(GeneracionBase):
    """Postcondiciones a a h y garantías mínimas del paso 11."""

    def test_flujo_principal_genera_la_orden_con_lineas_de_dos_proveedores(self):
        """Flujo básico (paso 11) y «Hecho cuando»: del pedido sale una orden con líneas de A y de B."""
        orden = self.generar(self.cot_a, self.cot_b, observaciones="Entregar a la mañana.")
        self.assertIsInstance(orden, OrdenCompra)
        self.assertEqual(orden.pedido, self.pedido)
        self.assertEqual(sorted({d.proveedor.pk for d in orden.detalles.all()}), sorted([self.a.pk, self.b.pk]))

    def test_post_a_la_orden_nace_pendiente_con_la_fecha_de_hoy_el_monto_y_las_observaciones(self):
        """Postcondición a: «pendiente de aprobación», fecha de emisión de hoy, monto = Σ cantidad × precio (430) y observaciones; sin Gerente ni resolución."""
        orden = self.generar(self.cot_a, self.cot_b, observaciones="  Entregar a la mañana.  ")
        orden.refresh_from_db()
        self.assertEqual(orden.estado_orden_compra, "pendiente_aprobacion")
        self.assertEqual(orden.fecha_emision, self.hoy)
        self.assertEqual(orden.monto_total, Decimal("430.00"))
        self.assertEqual(orden.observaciones, "Entregar a la mañana.")
        self.assertIsNone(orden.gerente)
        self.assertIsNone(orden.fecha_resolucion)

    def test_post_b_un_detalle_por_linea_elegida_copia_cantidad_cotizada_y_total(self):
        """Postcondición b, regla «Detalles de la orden» y A0: un detalle por cada línea elegida; copia la **cantidad cotizada** y el **total** (no el unitario),
        sin fecha de entrega esperada, asociado a su línea y a su detalle de pedido (R026)."""
        orden = self.generar(self.cot_a, self.cot_b)
        detalles = list(orden.detalles.order_by("detalle_cotizacion_id"))
        self.assertEqual(len(detalles), 3)
        for detalle in detalles:
            linea = detalle.detalle_cotizacion
            self.assertEqual(detalle.cantidad_detalle_orden, linea.cantidad_cotizada)
            self.assertEqual(detalle.total_linea, linea.total_linea)
            self.assertEqual(detalle.detalle_pedido, linea.detalle_pedido)
            self.assertIsNone(detalle.fecha_entrega_esperada)
            self.assertEqual(detalle.estado_detalle_orden, "pendiente")

    def test_post_b_si_el_proveedor_cotizo_de_mas_el_detalle_copia_lo_cotizado(self):
        """Postcondición b y A0 (P2): la línea de la orden copia la cantidad cotizada aunque supere la pedida (A 20 L + C 10 L = 30)."""
        orden = self.generar(self.cot_a, self.cot_b, self.cot_c)
        self.assertEqual(sum(d.cantidad_detalle_orden for d in orden.detalles.filter(detalle_cotizacion__detalle_pedido=self.lechuga)), Decimal("30"))

    def test_post_c_las_elegidas_pasan_a_seleccionada_y_el_resto_a_descartada(self):
        """Postcondición c: cada elegida pasa a «seleccionada» y el resto de las «propuesta» del pedido, a «descartada»."""
        self.generar(self.cot_a, self.cot_b)
        estados = {c.pk: Cotizacion.objects.get(pk=c.pk).estado_cotizacion for c in (self.cot_a, self.cot_b, self.cot_c)}
        self.assertEqual(estados, {self.cot_a.pk: "seleccionada", self.cot_b.pk: "seleccionada", self.cot_c.pk: "descartada"})

    def test_post_c_una_cotizacion_ya_descartada_se_deja_como_esta(self):
        """Postcondición c: solo se descartan las «propuesta»; una ya descartada no cambia ni se audita de nuevo."""
        otro = proveedor("Vivero Norte", n=4, email="norte@vivero.com")
        previa = cotizacion_de(self.pedido, otro, [(self.lechuga, 5, "50.00", 2)], estado="descartada")
        self.generar(self.cot_a, self.cot_b)
        self.assertEqual(Cotizacion.objects.get(pk=previa.pk).estado_cotizacion, "descartada")
        registro = RegistroAuditoria.objects.get(accion="generacion_orden_compra")
        self.assertNotIn(previa.pk, [a["id"] for a in registro.afectados if a["modelo"] == "compras.cotizacion"])

    def test_post_d_el_pedido_pasa_a_cerrado_con_la_fecha_de_hoy(self):
        """Postcondición d: el pedido pasa de «en cotización» a «cerrado», con fecha de cierre de hoy."""
        self.generar(self.cot_a, self.cot_b)
        pedido = Pedido.objects.get(pk=self.pedido.pk)
        self.assertEqual((pedido.estado_pedido, pedido.fecha_cierre_pedido), ("cerrado", self.hoy))

    def test_post_e_se_notifica_al_gerente_la_orden_pendiente(self):
        """Postcondición e y regla «Avisos»: una notificación (no una alerta) al Gerente con el identificador de la orden, el pedido, el monto, la diferencia con
        el estimado y la cantidad de proveedores."""
        orden = self.generar(self.cot_a, self.cot_b)
        notificacion = Notificacion.objects.get(destinatario=self.gerente)
        for texto in (str(orden), str(self.pedido), "430", "20", "2"):
            self.assertIn(texto, f"{notificacion.titulo} {notificacion.detalle}")
        self.assertFalse(orden.sin_gerente_activo)
        self.assertEqual(Alerta.objects.count(), 0)

    def test_ext_12b_sin_gerente_activo_la_orden_queda_pendiente_y_no_hay_notificacion(self):
        """Extensión 12b: sin un Gerente activo la orden queda «pendiente de aprobación» igual, se omite la notificación y el resultado lo informa para el paso 13."""
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])
        orden = self.generar(self.cot_a, self.cot_b)
        self.assertTrue(orden.sin_gerente_activo)
        self.assertEqual(orden.estado_orden_compra, "pendiente_aprobacion")
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_f_cada_proveedor_descartado_recibe_un_correo_y_los_seleccionados_nada(self):
        """Postcondición f y regla «Avisos»: solo C (descartada) recibe el correo; A y B (seleccionadas) no reciben nada todavía."""
        self.generar(self.cot_a, self.cot_b)
        self.assertEqual([m.to[0] for m in mail.outbox], ["hola@oeste.com"])
        self.assertIn(str(self.pedido), mail.outbox[0].subject)

    def test_post_f_el_correo_de_descarte_lleva_pedido_fecha_y_monto_y_no_a_los_otros_proveedores(self):
        """Lista de tecnología 12a: el correo indica el pedido, la fecha de la cotización y su monto; no menciona a los otros proveedores ni sus precios."""
        self.generar(self.cot_a, self.cot_b)
        cuerpo = mail.outbox[0].body
        self.assertIn(str(self.pedido), cuerpo)
        self.assertIn(f"{self.cot_c.fecha_cotizacion:%d/%m/%Y}", cuerpo)
        self.assertRegex(cuerpo, r"130[.,]00")
        self.assertIn("no fue seleccionada", cuerpo)
        for prohibido in ("Semillas del Sur", "Viveros del Este", "240", "100,00", "100.00"):
            self.assertNotIn(prohibido, cuerpo)

    def test_ext_12a_si_el_correo_falla_o_no_esta_configurado_la_orden_permanece(self):
        """Extensión 12a: si no sale un correo de descarte, la orden permanece registrada (el reintento es del envío, no de la orden)."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            orden = self.generar(self.cot_a, self.cot_b)
        self.assertTrue(OrdenCompra.objects.filter(pk=orden.pk).exists())
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado_pedido, "cerrado")

    def test_ext_12a_con_el_correo_sin_configurar_la_orden_permanece_y_no_sale_nada(self):
        """Extensión 12a: sin el correo configurado no sale nada y la orden queda generada."""
        with override_settings(CORREO_CONFIGURADO=False):
            orden = self.generar(self.cot_a, self.cot_b)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(OrdenCompra.objects.filter(pk=orden.pk).exists())

    def test_post_g_y_h_un_registro_de_auditoria_con_el_pedido_las_cotizaciones_la_orden_y_los_detalles(self):
        """Postcondiciones g y h y D-36 («una acción = un registro»): ``generacion_orden_compra``, hecho por Ana, con el cambio de estado del pedido y, entre
        los afectados, el pedido, cada cotización modificada, la orden y cada detalle."""
        orden = self.generar(self.cot_a, self.cot_b)
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.GENERACION_ORDEN_COMPRA)
        self.assertEqual(registro.usuario_id, self.ana.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {("compras.pedido", self.pedido.pk), ("compras.ordencompra", orden.pk)}
        esperados |= {("compras.cotizacion", c.pk) for c in (self.cot_a, self.cot_b, self.cot_c)}
        esperados |= {("compras.detalleordencompra", d.pk) for d in orden.detalles.all()}
        self.assertTrue(esperados <= afectados, esperados - afectados)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "en_cotizacion", "despues": "cerrado"})
        self.assertEqual(registro.detalle["cambios"]["fecha_cierre_pedido"], {"antes": None, "despues": self.hoy.isoformat()})
        datos = registro.detalle["datos"]
        self.assertEqual(datos["orden"], {"id": orden.pk, "texto": str(orden)})
        self.assertEqual({r["id"] for r in datos["cotizaciones_seleccionadas"]}, {self.cot_a.pk, self.cot_b.pk})
        self.assertEqual({r["id"] for r in datos["cotizaciones_descartadas"]}, {self.cot_c.pk})

    def test_regla_una_orden_por_pedido_la_segunda_generacion_se_rechaza(self):
        """Regla «Una orden por pedido»: ya no está «en cotización», así que generar de nuevo es la extensión 11a y no crea una segunda orden."""
        orden = self.generar(self.cot_a, self.cot_b)
        error = self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b))
        self.assertEqual(error.codigo, "pedido_no_en_cotizacion")
        self.assertEqual(error.datos["orden_id"], orden.pk)
        self.assertEqual(OrdenCompra.objects.count(), 1)

    def test_ext_11a_si_el_pedido_se_cancelo_no_se_registra_ningun_cambio_e_informa_el_estado(self):
        """Extensión 11a: al registrar, el pedido ya no está «en cotización» (se canceló en otra sesión): nada cambia y se informa el estado actual."""
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="cancelado", causa_cancelacion="manual", motivo_cancelacion="x", fecha_cierre_pedido=self.hoy)
        error = self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b))
        self.assertEqual((error.codigo, error.datos["estado"]), ("pedido_no_en_cotizacion", "cancelado"))
        self.assertEqual(OrdenCompra.objects.count(), 0)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_ext_11b_si_un_proveedor_elegido_se_dio_de_baja_no_se_registra_nada(self):
        """Extensión 11b: al registrar, el proveedor de una cotización elegida pasó a «inactivo»: nada cambia y se informa cuál quedó afectada y por qué."""
        self.b.estado_proveedor = "inactivo"
        self.b.save(update_fields=["estado_proveedor"])
        error = self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b))
        self.assertEqual((error.codigo, error.datos["afectadas"]), ("cotizacion_no_elegible", [(self.cot_b.pk, "proveedor_inactivo")]))
        self.sin_cambios()

    def test_ext_11b_si_vencio_la_validez_de_una_elegida_no_se_registra_nada(self):
        """Extensión 11b y MD-64: la validez se controla también al registrar; vence a la medianoche de la fecha de validez."""
        Cotizacion.objects.filter(pk=self.cot_a.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        error = self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b))
        self.assertEqual((error.codigo, error.datos["afectadas"]), ("cotizacion_no_elegible", [(self.cot_a.pk, "validez_vencida")]))
        self.sin_cambios()

    def test_ext_8a_la_cobertura_se_verifica_tambien_al_registrar(self):
        """Extensión 8a y paso 8: si lo elegido no cubre todos los detalles, no se genera nada."""
        error = self.codigo_del_error(ordenes.generar_orden, self.ana, self.pedido.pk, self.ids(self.cot_b))
        self.assertEqual(error.codigo, "cobertura_insuficiente")
        self.sin_cambios()

    def test_regla_cotizacion_elegida_completa_se_elige_con_todas_sus_lineas(self):
        """Regla «Cotización elegida completa»: no hay forma de elegir líneas sueltas; las dos líneas de A pasan a la orden."""
        orden = self.generar(self.cot_a, self.cot_b)
        self.assertEqual(orden.detalles.filter(detalle_cotizacion__cotizacion=self.cot_a).count(), 2)

    def test_garantia_no_modifica_stock_transito_alertas_ni_contabilidad(self):
        """Garantías mínimas y regla «Cantidad en tránsito»: generar no cambia el stock, el tránsito ni las alertas; la cantidad en tránsito sube recién al aprobar."""
        antes = list(InsumoInvernadero.objects.order_by("id").values_list("cant_transito_insumo", flat=True))
        movimientos, alertas = MovimientoInsumo.objects.count(), Alerta.objects.count()
        self.generar(self.cot_a, self.cot_b)
        self.assertEqual(list(InsumoInvernadero.objects.order_by("id").values_list("cant_transito_insumo", flat=True)), antes)
        self.assertEqual((MovimientoInsumo.objects.count(), Alerta.objects.count()), (movimientos, alertas))

    def test_garantia_ningun_proveedor_recibe_la_orden_ni_ve_las_cotizaciones_de_los_demas(self):
        """Garantías mínimas: generar no manda la orden a los proveedores elegidos (llega al aprobar)."""
        self.generar(self.cot_a, self.cot_b)
        self.assertNotIn("ventas@sur.com", [m.to[0] for m in mail.outbox])
        self.assertNotIn("info@este.com", [m.to[0] for m in mail.outbox])

    def test_garantia_si_falla_la_auditoria_no_queda_nada_ni_sale_ningun_aviso(self):
        """Garantías mínimas y extensión *b: la generación es atómica; si falla, no hay orden, detalle, notificación, correo ni log parcial, el pedido sigue «en
        cotización» y sus cotizaciones, «propuesta»."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    ordenes.generar_orden(self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b), "")
        self.assertEqual(pendientes, [])
        self.sin_cambios()

    def test_requisito_solo_el_agronomo_del_pedido_genera(self):
        """Requisito especial y regla «Agrónomo del pedido»: otro Agrónomo, el Gerente, otros roles y una cuenta inactiva no generan (``PermissionDenied``, sin cambios)."""
        beto, _ = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        for cuenta in (beto, self.gerente, crear_capataz(), None):
            with self.subTest(cuenta=cuenta):
                with self.assertRaises(PermissionDenied):
                    ordenes.generar_orden(cuenta, self.pedido.pk, self.ids(self.cot_a, self.cot_b), "")
        self.ana.is_active = False
        self.ana.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            ordenes.generar_orden(self.ana, self.pedido.pk, self.ids(self.cot_a, self.cot_b), "")
        self.sin_cambios()

    def test_un_pedido_inexistente_es_404(self):
        """Un pedido que no existe es ``Http404`` (D-28)."""
        with self.assertRaises(Http404):
            ordenes.generar_orden(self.ana, 99999, self.ids(self.cot_a, self.cot_b), "")


class AccionesDeAuditoriaDeOrdenesTests(TestCase):
    """D-87 punto 8 y D-36: las tres acciones nuevas de CMP-03 existen, están clasificadas como de negocio y sus campos tienen nombre visible."""

    def test_las_tres_acciones_existen_y_son_de_negocio(self):
        Accion = RegistroAuditoria.Accion
        nuevas = {Accion.GENERACION_ORDEN_COMPRA, Accion.APROBACION_ORDEN_COMPRA, Accion.RECHAZO_ORDEN_COMPRA}
        self.assertEqual({a.value for a in nuevas}, {"generacion_orden_compra", "aprobacion_orden_compra", "rechazo_orden_compra"})
        self.assertTrue(nuevas <= ACCIONES_DE_NEGOCIO)

    def test_los_datos_de_la_generacion_tienen_nombre_visible(self):
        """D-36: cada clave nueva de ``datos`` o de ``cambios`` tiene su etiqueta (si no, la pantalla muestra la clave tal cual)."""
        for clave in ("orden", "cotizaciones_seleccionadas", "cotizaciones_descartadas", "fecha_cierre_pedido"):
            self.assertIn(clave, RegistroAuditoria.ETIQUETAS)
