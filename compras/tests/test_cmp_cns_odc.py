# Pruebas de CMP-GNR-ODC · Consultar Orden de Compra (CMP-03, paso 6): ``consultar_ordenes`` y ``ficha_de_orden`` de ``compras/servicios/ordenes.py``. Fuente:
# docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-CNS-ODC v0.1: precondición a, postcondición a y las reglas 1 a 10), «Actualizaciones de A0 que mandan»
# (el Contador ve todas en solo lectura: entra con USR-11, todavía no existe), «Cómo se aplica (código)» y D-36 (la consulta no se audita, SEG-14).
# CMP-03 crea la consulta; CMP-04 (recepciones, líneas recibidas, «por recibir»), CMP-05 (pagos, «con pago pendiente») y CMP-06 (reclamos, «con reclamo sin emitir») suman
# sus secciones y atajos. Hasta entonces lo recibido es 0 y lo pendiente, toda la cantidad.
#
# API que fijan estas pruebas (``compras/servicios/ordenes.py``; el módulo se toma dentro de cada prueba con ``perezoso``). Las dos piden un Agrónomo o un Gerente activos
# (``PermissionDenied`` si no):
#   consultar_ordenes(actor, filtros=None) -> list[FilaDeOrden(orden, pedido, agronomo, proveedores, monto, lineas_atrasadas)]   (de la más reciente a la más antigua)
#       filtros (todos opcionales; uno mal formado se ignora): ``estado``, ``proveedor_id``, ``invernadero_id`` (alguna línea va ahí), ``desde`` y ``hasta`` (inclusive, sobre la
#       fecha de emisión; fechas o ``AAAA-MM-DD``), ``agronomo_id`` (solo lo usa el Gerente) y ``atajo`` («por_aprobar»; los demás atajos los suman CMP-04 a 06).
#   ficha_de_orden(actor, orden_id) -> FichaDeOrden(orden, pedido, agronomo, gerente, proveedores, grupos, monto_total, monto_estimado, diferencia,
#                                        diferencia_porcentaje, lineas_atrasadas, acciones)
#       grupos: list[GrupoDeLineas(proveedor, invernadero, lineas)] (uno por proveedor e invernadero de destino);
#       lineas: list[LineaDeOrden(detalle, insumo, cantidad, recibida, pendiente, unitario, total, entrega, atraso_dias, estado, motivo_cierre)];
#       acciones: ``frozenset`` de lo que ``actor`` puede hacer desde la ficha según su rol y el estado de la orden (CMP-03: «resolver», solo el Gerente y solo si está pendiente).
#   Una orden fuera del alcance es ``PermissionDenied``; una que no existe, ``Http404`` (D-28).

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from compras.models import DetalleOrdenCompra, OrdenCompra
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, orden_de, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Contador, RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero, crear_invernadero, crear_vendedor

ordenes = perezoso("compras.servicios.ordenes")


class ConsultaBase(ConDatosDeInventario, TestCase):
    """Ana (Norte y Norte 2), Beto (Sur) y un Gerente. Tres órdenes:
    - ``orden1`` de Ana, «pendiente de aprobación», emitida hace 3 días: A (12 lechugas $120 en Norte, 3 días; 20 tomates $200 en Norte 2, 4 días) y B (10 lechugas $100, 5 días).
    - ``orden2`` de Beto, «aprobada» hoy con entrega esperada hace 2 días (atrasada), emitida hace 2 días: C, 5 lechugas $50 en Sur.
    - ``orden3`` de Ana, «rechazada» (motivo «No hay presupuesto.»), emitida hace 1 día: B, 3 lechugas $30 en Norte."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.norte2 = crear_invernadero("Norte 2", agronomo=self.ana)
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        lechuga = insumo("Lechuga", unidad="unidad")
        self.lechuga_norte = existencia(lechuga, self.norte, minimo=0, precio="12.50")
        self.tomate_norte2 = existencia(insumo("Tomate", unidad="unidad"), self.norte2, minimo=0, precio="10.00")
        self.lechuga_sur = existencia(lechuga, self.sur, minimo=0, precio="11.00")
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.c = proveedor("Hortalizas del Oeste S. A.", n=3, email="hola@oeste.com")

        pedido1 = armar_pedido(self.ana)
        lechuga1, tomate1 = detalle_de_pedido(pedido1, self.lechuga_norte, cantidad="20"), detalle_de_pedido(pedido1, self.tomate_norte2, cantidad="20")
        self.orden1 = orden_de(
            pedido1,
            [cotizacion_de(pedido1, self.a, [(lechuga1, 12, "120.00", 3), (tomate1, 20, "200.00", 4)]), cotizacion_de(pedido1, self.b, [(lechuga1, 10, "100.00", 5)])],
        )
        pedido2 = armar_pedido(self.beto)
        detalle2 = detalle_de_pedido(pedido2, self.lechuga_sur, cantidad="5")
        self.orden2 = orden_de(pedido2, [cotizacion_de(pedido2, self.c, [(detalle2, 5, "50.00", 2)])], estado="aprobada", gerente=self.gerente)
        DetalleOrdenCompra.objects.filter(orden=self.orden2).update(fecha_entrega_esperada=self.hoy - timedelta(days=2))
        pedido3 = armar_pedido(self.ana)
        detalle3 = detalle_de_pedido(pedido3, self.lechuga_norte, cantidad="3")
        self.orden3 = orden_de(pedido3, [cotizacion_de(pedido3, self.b, [(detalle3, 3, "30.00", 2)])], estado="rechazada", gerente=self.gerente, motivo="No hay presupuesto.")
        for orden, dias in ((self.orden1, 3), (self.orden2, 2), (self.orden3, 1)):
            OrdenCompra.objects.filter(pk=orden.pk).update(fecha_emision=self.hoy - timedelta(days=dias))
            orden.refresh_from_db()

    def ids(self, filas):
        return [f.orden.pk for f in filas]

    def consultar(self, actor=None, **filtros):
        return ordenes.consultar_ordenes(actor or self.gerente, filtros)


class AlcanceDeLaConsultaTests(ConsultaBase):
    """Regla 1 y precondición a: el Agrónomo ve las órdenes con destino a su cargo; el Gerente, todas; nadie más (el Contador entra con USR-11)."""

    def test_regla_1_el_agronomo_ve_las_ordenes_con_algun_destino_a_su_cargo(self):
        self.assertEqual(set(self.ids(ordenes.consultar_ordenes(self.ana))), {self.orden1.pk, self.orden3.pk})
        self.assertEqual(set(self.ids(ordenes.consultar_ordenes(self.beto))), {self.orden2.pk})

    def test_regla_1_el_gerente_ve_todas(self):
        self.assertEqual(set(self.ids(self.consultar())), {self.orden1.pk, self.orden2.pk, self.orden3.pk})

    def test_regla_1_una_orden_con_destinos_de_dos_agronomos_la_ven_los_dos(self):
        """Basta un destino a su cargo: pasar Norte 2 a Beto hace que vea también la orden 1, sin duplicarla."""
        self.norte2.agronomo = self.beto
        self.norte2.save(update_fields=["agronomo"])
        self.assertEqual(sorted(self.ids(ordenes.consultar_ordenes(self.beto))), sorted([self.orden1.pk, self.orden2.pk]))
        self.assertEqual(self.ids(ordenes.consultar_ordenes(self.ana)).count(self.orden1.pk), 1)

    def test_precondicion_a_solo_un_agronomo_o_un_gerente_activos(self):
        """Precondición a: otros roles, cuentas inactivas y ``None`` reciben ``PermissionDenied`` (en la lista y en la ficha)."""
        inactiva = crear_agronomo(email="baja@infoponia.com", activo=False)
        for cuenta in (crear_capataz(), crear_vendedor(), crear_administrador(), inactiva, None):
            with self.subTest(cuenta=cuenta):
                with self.assertRaises(PermissionDenied):
                    ordenes.consultar_ordenes(cuenta)
                with self.assertRaises(PermissionDenied):
                    ordenes.ficha_de_orden(cuenta, self.orden1.pk)

    def test_regla_10_la_consulta_no_audita_ni_escribe(self):
        """Regla 10 y postcondición a: «la consulta no se audita» (SEG-14); no cambia ninguna orden."""
        antes = (RegistroAuditoria.objects.count(), list(OrdenCompra.objects.order_by("id").values_list("estado_orden_compra", "fecha_resolucion")))
        self.consultar()
        ordenes.ficha_de_orden(self.gerente, self.orden1.pk)
        self.assertEqual((RegistroAuditoria.objects.count(), list(OrdenCompra.objects.order_by("id").values_list("estado_orden_compra", "fecha_resolucion"))), antes)


class ListadoDeOrdenesTests(ConsultaBase):
    """Regla 3: identificador, pedido de origen, fecha, monto, proveedores, estado y marcas."""

    def test_regla_3_de_la_mas_reciente_a_la_mas_antigua(self):
        self.assertEqual(self.ids(self.consultar()), [self.orden3.pk, self.orden2.pk, self.orden1.pk])

    def test_regla_3_cada_fila_trae_el_pedido_el_agronomo_los_proveedores_y_el_monto(self):
        fila = {f.orden.pk: f for f in self.consultar()}[self.orden1.pk]
        self.assertEqual((fila.pedido, fila.agronomo.pk, fila.monto), (self.orden1.pedido, self.ana.pk, Decimal("420.00")))
        self.assertEqual(sorted(p.pk for p in fila.proveedores), sorted([self.a.pk, self.b.pk]))

    def test_regla_3_la_marca_de_lineas_atrasadas_cuenta_las_aprobadas_con_la_entrega_vencida(self):
        """Regla 3: «marcas de líneas atrasadas». La orden 2 está aprobada y su entrega esperada pasó hace 2 días; las pendientes de aprobación no tienen fecha."""
        filas = {f.orden.pk: f for f in self.consultar()}
        self.assertEqual((filas[self.orden2.pk].lineas_atrasadas, filas[self.orden1.pk].lineas_atrasadas, filas[self.orden3.pk].lineas_atrasadas), (1, 0, 0))

    def test_regla_3_una_linea_con_la_entrega_de_hoy_o_futura_no_esta_atrasada(self):
        DetalleOrdenCompra.objects.filter(orden=self.orden2).update(fecha_entrega_esperada=self.hoy)
        self.assertEqual({f.orden.pk: f for f in self.consultar()}[self.orden2.pk].lineas_atrasadas, 0)

    def test_sin_consultas_por_fila(self):
        """La misma cantidad de consultas con 1 o con más órdenes."""
        with CaptureQueriesContext(connection) as con_tres:
            self.consultar()
        for _ in range(3):
            pedido = armar_pedido(self.ana)
            detalle = detalle_de_pedido(pedido, self.lechuga_norte, cantidad="2")
            orden_de(pedido, [cotizacion_de(pedido, self.c, [(detalle, 2, "20.00", 2)])])
        with CaptureQueriesContext(connection) as con_seis:
            self.consultar()
        self.assertEqual(len(con_seis), len(con_tres))


class FiltrosDeLaConsultaTests(ConsultaBase):
    """Regla 2: estado, proveedor, invernadero de destino, rango de fechas, Agrónomo del pedido (solo el Gerente) y el atajo «por aprobar»."""

    def test_regla_2_por_estado(self):
        self.assertEqual(self.ids(self.consultar(estado="aprobada")), [self.orden2.pk])
        self.assertEqual(self.ids(self.consultar(estado="pendiente_aprobacion")), [self.orden1.pk])
        self.assertEqual(self.ids(self.consultar(estado="rechazada")), [self.orden3.pk])
        self.assertEqual(self.consultar(estado="recibida"), [])

    def test_regla_2_por_proveedor(self):
        self.assertEqual(sorted(self.ids(self.consultar(proveedor_id=self.b.pk))), sorted([self.orden1.pk, self.orden3.pk]))
        self.assertEqual(self.ids(self.consultar(proveedor_id=self.c.pk)), [self.orden2.pk])

    def test_regla_2_por_invernadero_de_destino(self):
        self.assertEqual(sorted(self.ids(self.consultar(invernadero_id=self.norte.pk))), sorted([self.orden1.pk, self.orden3.pk]))
        self.assertEqual(self.ids(self.consultar(invernadero_id=self.norte2.pk)), [self.orden1.pk])
        self.assertEqual(self.ids(self.consultar(invernadero_id=self.sur.pk)), [self.orden2.pk])

    def test_regla_2_por_rango_de_fechas_inclusive(self):
        """Sobre la fecha de emisión (hace 3, 2 y 1 día); los extremos entran. Se aceptan fechas y textos ``AAAA-MM-DD``."""
        desde, hasta = self.hoy - timedelta(days=2), self.hoy - timedelta(days=1)
        self.assertEqual(sorted(self.ids(self.consultar(desde=desde, hasta=hasta))), sorted([self.orden2.pk, self.orden3.pk]))
        self.assertEqual(self.ids(self.consultar(desde=desde.isoformat(), hasta=desde.isoformat())), [self.orden2.pk])
        self.assertEqual(self.ids(self.consultar(hasta=(self.hoy - timedelta(days=3)).isoformat())), [self.orden1.pk])

    def test_regla_2_por_agronomo_del_pedido_solo_para_el_gerente(self):
        """Regla 2: «para el Gerente, Agrónomo del pedido». El Agrónomo ya ve solo lo suyo: ese filtro no le amplía ni le cambia el alcance."""
        self.assertEqual(sorted(self.ids(self.consultar(agronomo_id=self.ana.pk))), sorted([self.orden1.pk, self.orden3.pk]))
        self.assertEqual(self.ids(self.consultar(agronomo_id=self.beto.pk)), [self.orden2.pk])
        self.assertEqual(set(self.ids(ordenes.consultar_ordenes(self.ana, {"agronomo_id": self.beto.pk}))), {self.orden1.pk, self.orden3.pk})

    def test_regla_2_el_atajo_por_aprobar_trae_las_pendientes_de_aprobacion(self):
        self.assertEqual(self.ids(self.consultar(atajo="por_aprobar")), [self.orden1.pk])

    def test_regla_2_un_atajo_de_otra_tarea_o_desconocido_se_ignora(self):
        """«Con pago pendiente» lo suma CMP-05; hasta entonces, y un atajo desconocido, se ignoran como un filtro mal formado (no filtran). CMP-04 sumó «por recibir» y «con reclamo sin emitir»."""
        for atajo in ("con_pago_pendiente", "otro"):
            with self.subTest(atajo=atajo):
                self.assertEqual(len(self.consultar(atajo=atajo)), 3)

    def test_regla_2_el_atajo_por_recibir_trae_las_aprobadas_con_lineas_pendientes(self):
        """CMP-04 y regla 2: «por recibir» son las órdenes aprobadas o parcialmente recibidas con alguna línea pendiente (la aprobada de la prueba; ni la pendiente de aprobación ni la rechazada)."""
        self.assertEqual(self.ids(self.consultar(atajo="por_recibir")), [self.orden2.pk])

    def test_regla_2_el_atajo_con_reclamo_sin_emitir_no_trae_ordenes_sin_reclamos(self):
        """CMP-04 y regla 2: «con reclamo sin emitir» trae solo las órdenes con una recepción cuyo reclamo no se emitió; sin reclamos, ninguna. (Con reclamos lo prueban las pruebas de la recepción.)"""
        self.assertEqual(self.consultar(atajo="con_reclamo_sin_emitir"), [])

    def test_regla_2_los_filtros_se_combinan(self):
        self.assertEqual(self.ids(self.consultar(proveedor_id=self.b.pk, estado="rechazada")), [self.orden3.pk])
        self.assertEqual(self.consultar(proveedor_id=self.c.pk, estado="rechazada"), [])

    def test_regla_2_un_filtro_mal_formado_se_ignora(self):
        """Mal formado (estado inexistente, ids que no son números, fechas imposibles): no filtra ni falla, como en la consulta de pedidos."""
        self.assertEqual(len(self.consultar(estado="inventado", proveedor_id="abc", invernadero_id="", desde="2026-13-45", hasta="ayer", agronomo_id="x")), 3)

    def test_regla_2_los_filtros_nunca_amplian_el_alcance(self):
        """El Agrónomo que filtra por el proveedor de la orden de otro Agrónomo no la ve."""
        self.assertEqual(self.ids(ordenes.consultar_ordenes(self.beto, {"proveedor_id": self.b.pk})), [])


class FichaDeOrdenTests(ConsultaBase):
    """Reglas 4 y 5 y la acción de la regla 8."""

    def ficha(self, orden=None, actor=None):
        return ordenes.ficha_de_orden(actor or self.gerente, (orden or self.orden1).pk)

    def test_regla_4_trae_el_pedido_de_origen_su_agronomo_el_monto_y_el_estado(self):
        ficha = self.ficha()
        self.assertEqual((ficha.orden, ficha.pedido, ficha.agronomo.pk), (self.orden1, self.orden1.pedido, self.ana.pk))
        self.assertEqual((ficha.monto_total, ficha.monto_estimado, ficha.diferencia, ficha.diferencia_porcentaje), (Decimal("420.00"), Decimal("450.00"), Decimal("-30.00"), Decimal("-6.7")))
        self.assertEqual(ficha.orden.estado_orden_compra, "pendiente_aprobacion")
        self.assertIsNone(ficha.gerente)

    def test_regla_4_una_orden_resuelta_trae_el_gerente_la_fecha_las_observaciones_y_el_motivo_del_rechazo(self):
        OrdenCompra.objects.filter(pk=self.orden3.pk).update(observaciones="Entregar a la mañana.")
        rechazada = self.ficha(self.orden3)
        self.assertEqual((rechazada.gerente.pk, rechazada.orden.fecha_resolucion, rechazada.orden.motivo_rechazo, rechazada.orden.observaciones), (self.gerente.pk, self.hoy, "No hay presupuesto.", "Entregar a la mañana."))
        aprobada = self.ficha(self.orden2)
        self.assertEqual((aprobada.gerente.pk, aprobada.orden.fecha_resolucion, aprobada.orden.motivo_rechazo), (self.gerente.pk, self.hoy, ""))

    def test_regla_5_las_lineas_van_agrupadas_por_proveedor_e_invernadero_de_destino(self):
        """Regla 5: «por cada proveedor e invernadero de destino, las líneas»: A en Norte (lechuga), A en Norte 2 (tomate) y B en Norte (lechuga)."""
        grupos = {(g.proveedor.pk, g.invernadero.pk): g for g in self.ficha().grupos}
        self.assertEqual(set(grupos), {(self.a.pk, self.norte.pk), (self.a.pk, self.norte2.pk), (self.b.pk, self.norte.pk)})
        self.assertEqual([l.insumo.nombre_insumo for l in grupos[(self.a.pk, self.norte2.pk)].lineas], ["Tomate"])

    def test_regla_5_cada_linea_trae_cantidad_recibida_pendiente_precio_total_y_estado(self):
        """Regla 5: insumo, cantidad (pedida a ese proveedor), recibida y pendiente (hasta CMP-04, 0 y toda la cantidad), precio unitario derivado con dos decimales (D-89),
        el total guardado y el estado (pendiente, completo o cerrado con faltante, con su motivo)."""
        linea = {(g.proveedor.pk, g.invernadero.pk): g for g in self.ficha().grupos}[(self.a.pk, self.norte.pk)].lineas[0]
        self.assertEqual((linea.cantidad, linea.recibida, linea.pendiente), (Decimal("12"), Decimal("0"), Decimal("12")))
        self.assertEqual((linea.unitario, linea.total, linea.estado, linea.motivo_cierre), (Decimal("10.00"), Decimal("120.00"), "pendiente", ""))
        self.assertIsInstance(linea.detalle, DetalleOrdenCompra)

    def test_regla_5_una_linea_cerrada_con_faltante_trae_su_motivo(self):
        DetalleOrdenCompra.objects.filter(orden=self.orden2).update(estado_detalle_orden="cerrado_con_faltante", motivo_cierre_faltante="No llegó.", fecha_cierre_faltante=self.hoy)
        linea = self.ficha(self.orden2).grupos[0].lineas[0]
        self.assertEqual((linea.estado, linea.motivo_cierre), ("cerrado_con_faltante", "No llegó."))

    def test_regla_5_la_fecha_de_entrega_esperada_trae_los_dias_de_atraso(self):
        """Regla 5: «fecha de entrega esperada (con los días de atraso si corresponde)»: la orden 2 está atrasada 2 días; una pendiente de aprobación no tiene fecha ni atraso."""
        atrasada = self.ficha(self.orden2).grupos[0].lineas[0]
        self.assertEqual((atrasada.entrega, atrasada.atraso_dias), (self.hoy - timedelta(days=2), 2))
        sin_fecha = self.ficha().grupos[0].lineas[0]
        self.assertEqual((sin_fecha.entrega, sin_fecha.atraso_dias), (None, 0))
        self.assertEqual((self.ficha(self.orden2).lineas_atrasadas, self.ficha().lineas_atrasadas), (1, 0))

    def test_regla_5_una_linea_que_ya_no_esta_pendiente_no_se_marca_atrasada(self):
        """Una línea completa o cerrada con faltante ya no se espera: no cuenta como atrasada."""
        DetalleOrdenCompra.objects.filter(orden=self.orden2).update(estado_detalle_orden="completo")
        ficha = self.ficha(self.orden2)
        self.assertEqual((ficha.lineas_atrasadas, ficha.grupos[0].lineas[0].atraso_dias), (0, 0))

    def test_regla_4_la_ficha_trae_cada_proveedor_con_sus_lineas_y_su_monto(self):
        por_proveedor = {p.proveedor: p for p in self.ficha().proveedores}
        self.assertEqual((por_proveedor[self.a].monto, por_proveedor[self.b].monto), (Decimal("320.00"), Decimal("100.00")))

    def test_regla_8_el_gerente_puede_resolver_una_orden_pendiente(self):
        """Regla 8: «Aprobar Orden de Compra (CMP-APR-ODC, solo el Gerente, si está pendiente de aprobación)»; en CMP-03 la acción es «resolver» (revisar y decidir)."""
        self.assertEqual(self.ficha().acciones, frozenset({"resolver"}))

    def test_regla_8_sin_accion_si_la_orden_ya_se_resolvio_o_quien_mira_no_es_el_gerente(self):
        """Ningún botón lleva a un 403 (D-30): una orden aprobada o rechazada, o quien mira es el Agrónomo, no tienen acción de resolver. La aprobada, vista por el Gerente, ofrece lo de CMP-04
        (recibir y cerrar con faltante, regla 8); la rechazada, nada."""
        self.assertEqual(self.ficha(self.orden2).acciones, frozenset({"recibir", "cerrar"}))
        self.assertEqual(self.ficha(self.orden3).acciones, frozenset())
        self.assertEqual(self.ficha(self.orden1, self.ana).acciones, frozenset())

    def test_regla_1_el_agronomo_abre_la_ficha_de_sus_ordenes_y_no_la_de_otros(self):
        """Regla 1: el Agrónomo con un destino a su cargo la abre; otro Agrónomo recibe ``PermissionDenied``; una orden que no existe, ``Http404``."""
        self.assertEqual(self.ficha(self.orden1, self.ana).orden, self.orden1)
        with self.assertRaises(PermissionDenied):
            self.ficha(self.orden1, self.beto)
        with self.assertRaises(Http404):
            ordenes.ficha_de_orden(self.gerente, 99999)

    def test_regla_5_el_gerente_ve_las_lineas_de_todos_y_el_agronomo_tambien_las_de_su_orden(self):
        """Regla 5: la ficha trae todas las líneas de la orden, no solo las de los destinos del Agrónomo que la mira."""
        self.norte2.agronomo = self.beto
        self.norte2.save(update_fields=["agronomo"])
        lineas_de_ana = sum(len(g.lineas) for g in self.ficha(self.orden1, self.ana).grupos)
        self.assertEqual(lineas_de_ana, 3)

    def test_sin_consultas_por_linea(self):
        """La ficha hace la misma cantidad de consultas con 3 que con más líneas."""
        with CaptureQueriesContext(connection) as con_tres:
            self.ficha()
        pedido = armar_pedido(self.ana)
        detalles = [detalle_de_pedido(pedido, e, cantidad="5") for e in (self.lechuga_norte, self.tomate_norte2)]
        grande = orden_de(pedido, [cotizacion_de(pedido, self.c, [(d, 5, "50.00", 2) for d in detalles])])
        with CaptureQueriesContext(connection) as con_mas:
            self.ficha(grande)
        self.assertEqual(len(con_mas), len(con_tres))



class ContadorConsultaServicioTests(ConsultaBase):
    """El Contador (USR-11, D-85) consulta **todas** las órdenes **en solo lectura**, para seguir los pagos (CMP-CNS-ODC precondición a y regla 1; «Actualizaciones de A0 que
    mandan»; D-87 punto 6). No genera, no aprueba ni rechaza (CMP-GNR-ODC y CMP-APR-ODC son del Agrónomo y del Gerente) y no ve «acciones» en la ficha."""

    def setUp(self):
        super().setUp()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def test_regla_1_el_contador_ve_todas_las_ordenes(self):
        """Regla 1: «El Contador ve todas, en solo lectura»: las órdenes de todos los Agrónomos, en cualquier estado."""
        self.assertEqual(set(OrdenCompra.objects.en_alcance_de(self.contador)), {self.orden1, self.orden2, self.orden3})
        self.assertEqual(set(self.ids(ordenes.consultar_ordenes(self.contador))), {self.orden1.pk, self.orden2.pk, self.orden3.pk})

    def test_regla_3_el_listado_del_contador_trae_lo_mismo_que_el_del_gerente(self):
        self.assertEqual(self.ids(ordenes.consultar_ordenes(self.contador)), self.ids(self.consultar()))

    def test_regla_2_el_contador_filtra_por_estado_proveedor_invernadero_fechas_y_atajo(self):
        """Regla 2: los mismos filtros que el Gerente (menos el Agrónomo del pedido)."""
        self.assertEqual(self.ids(ordenes.consultar_ordenes(self.contador, {"estado": "aprobada"})), [self.orden2.pk])
        self.assertEqual(sorted(self.ids(ordenes.consultar_ordenes(self.contador, {"proveedor_id": self.b.pk}))), sorted([self.orden1.pk, self.orden3.pk]))
        self.assertEqual(self.ids(ordenes.consultar_ordenes(self.contador, {"invernadero_id": self.sur.pk})), [self.orden2.pk])
        self.assertEqual(self.ids(ordenes.consultar_ordenes(self.contador, {"atajo": "por_aprobar"})), [self.orden1.pk])

    def test_regla_2_el_filtro_por_agronomo_del_pedido_es_solo_del_gerente(self):
        """Regla 2: «para el Gerente, Agrónomo del pedido»: para el Contador no filtra (ve todas)."""
        self.assertEqual(len(ordenes.consultar_ordenes(self.contador, {"agronomo_id": self.beto.pk})), 3)

    def test_regla_4_el_contador_abre_la_ficha_de_cualquier_orden(self):
        for orden in (self.orden1, self.orden2, self.orden3):
            with self.subTest(orden=str(orden)):
                self.assertEqual(ordenes.ficha_de_orden(self.contador, orden.pk).orden, orden)

    def test_regla_8_el_contador_no_tiene_acciones_en_la_ficha(self):
        """Regla 8 y D-30: solo lectura; ni siquiera «Revisar y decidir» en una orden pendiente."""
        self.assertEqual(ordenes.ficha_de_orden(self.contador, self.orden1.pk).acciones, frozenset())

    def test_precondicion_a_un_contador_inactivo_no_consulta(self):
        inactivo = crear_cuenta(Contador, email="baja@infoponia.com", activo=False)
        with self.assertRaises(PermissionDenied):
            ordenes.consultar_ordenes(inactivo)
        with self.assertRaises(PermissionDenied):
            ordenes.ficha_de_orden(inactivo, self.orden1.pk)

    def test_el_contador_no_genera_ni_aprueba_ni_rechaza(self):
        """El Contador solo consulta: generar es del Agrónomo del pedido; aprobar y rechazar, del Gerente (``PermissionDenied``, sin cambiar nada)."""
        with self.assertRaises(PermissionDenied):
            ordenes.pedidos_resolubles(self.contador)
        with self.assertRaises(PermissionDenied):
            ordenes.generar_orden(self.contador, self.orden1.pedido_id, [], "")
        for funcion, args in (
            (ordenes.ordenes_por_aprobar, ()),
            (ordenes.detalle_para_resolver, (self.orden1.pk,)),
            (ordenes.aprobar_orden, (self.orden1.pk,)),
            (ordenes.rechazar_orden, (self.orden1.pk, "No.")),
        ):
            with self.subTest(funcion=funcion.__name__):
                with self.assertRaises(PermissionDenied):
                    funcion(self.contador, *args)
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden1.pk).estado_orden_compra, "pendiente_aprobacion")

    def test_la_consulta_del_contador_no_audita_ni_escribe(self):
        """Regla 10: «la consulta no se audita» (SEG-14)."""
        antes = RegistroAuditoria.objects.count()
        ordenes.consultar_ordenes(self.contador)
        ordenes.ficha_de_orden(self.contador, self.orden1.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_el_contador_no_abre_los_proveedores_ni_sus_ordenes_desde_la_ficha(self):
        """La tarjeta de órdenes de la ficha del proveedor no es del Contador: CMP-CNS-PRV regla 1 (la ficha del proveedor sigue siendo de
        Gerente y Agrónomo); el Contador consulta las órdenes desde «Órdenes»."""
        from compras.servicios import proveedores

        with self.assertRaises(PermissionDenied):
            proveedores.ordenes_del_proveedor(self.contador, self.a)
