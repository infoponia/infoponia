# Pruebas de CMP-CNS-PED · Consultar Pedido (CMP-02a, paso 5): ``consultar_pedidos`` y ``ficha_de_pedido`` de ``compras/servicios/pedidos.py``. Fuente: docs/casos_de_uso/
# compras/pedidos.md (CMP-CNS-PED v0.1, reglas 1 a 9). «Reenviar invitación» (regla 7) y «Cancelar» (regla 8) son de CMP-02b y «Generar orden», de CMP-03: acá la
# ficha no trae acciones. Decisión del estudiante (23/11/2026): la cotización se ve en solo lectura **desde que llega** (regla 6 y prototipo), no recién al terminar
# el día de la fecha límite como dice «Cómo se aplica». El módulo se toma dentro de cada prueba (``perezoso``).

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from compras.models import EnlaceProveedor, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero, crear_invernadero, crear_vendedor

pedidos = perezoso("compras.servicios.pedidos")
proveedores = perezoso("compras.servicios.proveedores")


def en(dias):
    return timezone.localdate() + timedelta(days=dias)


class ConsultaBase(ConDatosDeInventario, TestCase):
    """Dos Agrónomos, cada uno con su invernadero y su pedido; el primero invita a dos proveedores y uno cotiza."""

    def setUp(self):
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        self.lechuga_norte = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=20, precio="12.50")
        self.nutriente_norte = existencia(insumo("Nutriente", unidad="kg"), self.norte, minimo=5, precio="100.00")
        self.lechuga_sur = existencia(self.lechuga_norte.insumo, self.sur, minimo=10, precio="11.00")
        self.sur_prv = proveedor("Semillas del Sur S. A.", n=1)
        self.este_prv = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        # El pedido de Ana (a Norte): 20 lechugas y 3 kg de nutriente, con dos invitados.
        self.pedido = armar_pedido(self.ana, dias_al_limite=3)
        self.d_lechuga = detalle_de_pedido(self.pedido, self.lechuga_norte, cantidad="20")
        self.d_nutriente = detalle_de_pedido(self.pedido, self.nutriente_norte, cantidad="3")
        self.inv_sur, _ = enlace_de(invitar(self.pedido, self.sur_prv))
        self.inv_este, _ = enlace_de(invitar(self.pedido, self.este_prv))
        # El pedido de Beto (a Sur).
        self.ajeno = armar_pedido(self.beto, dias_al_limite=5)
        detalle_de_pedido(self.ajeno, self.lechuga_sur, cantidad="10")
        invitar(self.ajeno, self.sur_prv)

    def ids(self, filas):
        return [f.pedido.pk for f in filas]


class AlcanceDeLaConsultaTests(ConsultaBase):
    """Regla 1 de CMP-CNS-PED y SEG-13."""

    def test_regla_1_el_agronomo_ve_los_pedidos_que_el_realizo(self):
        """Regla 1: el Agrónomo ve solo los suyos."""
        self.assertEqual(self.ids(pedidos.consultar_pedidos(self.ana)), [self.pedido.pk])
        self.assertEqual(self.ids(pedidos.consultar_pedidos(self.beto)), [self.ajeno.pk])

    def test_regla_1_el_gerente_ve_todos_los_pedidos(self):
        """Regla 1: el Gerente ve todos, en solo lectura."""
        self.assertEqual(sorted(self.ids(pedidos.consultar_pedidos(self.gerente))), sorted([self.pedido.pk, self.ajeno.pk]))

    def test_regla_1_nadie_mas_consulta_pedidos(self):
        """Regla 1 y SEG-13: otros roles y las cuentas inactivas reciben ``PermissionDenied``."""
        for actor in (crear_capataz(), crear_vendedor(), crear_administrador(), crear_agronomo(email="baja@infoponia.com", activo=False), crear_gerente(email="g2@infoponia.com", activo=False)):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    pedidos.consultar_pedidos(actor)
                with self.assertRaises(PermissionDenied):
                    pedidos.ficha_de_pedido(actor, self.pedido.pk)

    def test_regla_9_consultar_no_audita(self):
        """Regla 9 y SEG-14: el resto de la consulta no se audita."""
        antes = RegistroAuditoria.objects.count()
        pedidos.consultar_pedidos(self.gerente)
        pedidos.ficha_de_pedido(self.ana, self.pedido.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)


class ListadoDePedidosTests(ConsultaBase):
    """Regla 3: el listado."""

    def test_regla_3_cada_fila_trae_monto_proveedores_invitados_y_cotizaciones_recibidas(self):
        """Regla 3: identificador, fechas, monto estimado (Σ cantidad × precio de referencia), cantidad de proveedores invitados y de cotizaciones recibidas, y estado."""
        cotizacion_de(self.pedido, self.sur_prv, [(self.d_lechuga, 20, "250.00", 3)])
        fila = pedidos.consultar_pedidos(self.ana)[0]
        self.assertEqual(fila.pedido.pk, self.pedido.pk)
        self.assertEqual(fila.monto, Decimal("550.00"))  # 20 × 12,50 + 3 × 100,00
        self.assertEqual((fila.invitados, fila.cotizaciones), (2, 1))
        self.assertEqual(fila.pedido.estado_pedido, "en_cotizacion")
        self.assertEqual(fila.invernaderos, ["Norte"])
        self.assertEqual(fila.insumos, 2)

    def test_regla_3_se_marca_el_pedido_con_la_fecha_limite_vencida_por_resolver(self):
        """Regla 3: se marcan los pedidos «en cotización» con la fecha límite vencida (CMP-03 los resuelve); no los cancelados ni los cerrados."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(-1))
        cancelado = armar_pedido(self.ana, estado="cancelado", causa="nadie_cotizo")
        Pedido.objects.filter(pk=cancelado.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(-1))
        por_pedido = {f.pedido.pk: f.por_resolver for f in pedidos.consultar_pedidos(self.ana)}
        self.assertEqual(por_pedido, {self.pedido.pk: True, cancelado.pk: False})

    def test_regla_3_un_pedido_que_vence_hoy_todavia_no_esta_vencido(self):
        """D-88 punto 2: el último día todavía se cotiza; el pedido vence al terminar el día de la fecha límite."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(0))
        self.assertFalse(pedidos.consultar_pedidos(self.ana)[0].por_resolver)

    def test_regla_3_del_mas_reciente_al_mas_viejo(self):
        """Regla 3: el listado va del pedido más reciente al más viejo (por fecha y, si empatan, por id)."""
        viejo = armar_pedido(self.ana)
        Pedido.objects.filter(pk=viejo.pk).update(fecha_pedido=en(-10))
        nuevo = armar_pedido(self.ana)
        self.assertEqual(self.ids(pedidos.consultar_pedidos(self.ana)), [nuevo.pk, self.pedido.pk, viejo.pk])

    def test_regla_3_la_cantidad_de_consultas_no_depende_de_la_cantidad_de_pedidos(self):
        """Eficiencia: una consulta por tabla, no una por fila."""
        with CaptureQueriesContext(connection) as uno:
            pedidos.consultar_pedidos(self.ana)
        for _ in range(5):
            otro = armar_pedido(self.ana)
            detalle_de_pedido(otro, self.lechuga_norte)
            invitar(otro, self.este_prv)
        with CaptureQueriesContext(connection) as varios:
            filas = pedidos.consultar_pedidos(self.ana)
        self.assertEqual(len(filas), 6)
        self.assertEqual(len(varios), len(uno))


class FiltrosDelListadoTests(ConsultaBase):
    """Regla 2: los filtros se combinan."""

    def setUp(self):
        super().setUp()
        self.cancelado = armar_pedido(self.ana, estado="cancelado", causa="manual", motivo="Ya no hace falta")
        detalle_de_pedido(self.cancelado, self.lechuga_norte)
        invitar(self.cancelado, self.este_prv)
        Pedido.objects.filter(pk=self.cancelado.pk).update(fecha_pedido=en(-20), fecha_limite_cotizaciones=en(-15))

    def filtrar(self, actor=None, **filtros):
        return self.ids(pedidos.consultar_pedidos(actor or self.ana, filtros))

    def test_regla_2_por_estado(self):
        """Regla 2: estado (en cotización, cerrado, cancelado)."""
        self.assertEqual(self.filtrar(estado="cancelado"), [self.cancelado.pk])
        self.assertEqual(self.filtrar(estado="en_cotizacion"), [self.pedido.pk])
        self.assertEqual(self.filtrar(estado="cerrado"), [])

    def test_regla_2_por_invernadero_de_destino(self):
        """Regla 2: invernadero de destino (algún detalle va ahí)."""
        otro = crear_invernadero("Otro", agronomo=self.ana)
        self.assertEqual(sorted(self.filtrar(invernadero_id=self.norte.pk)), sorted([self.pedido.pk, self.cancelado.pk]))
        self.assertEqual(self.filtrar(invernadero_id=otro.pk), [])

    def test_regla_2_por_proveedor_invitado(self):
        """Regla 2: proveedor invitado."""
        self.assertEqual(sorted(self.filtrar(proveedor_id=self.este_prv.pk)), sorted([self.pedido.pk, self.cancelado.pk]))
        self.assertEqual(self.filtrar(proveedor_id=self.sur_prv.pk), [self.pedido.pk])

    def test_regla_2_por_rango_de_fechas_del_pedido_o_de_la_fecha_limite(self):
        """Regla 2: rango de fechas, de pedido (por omisión) o de la fecha límite; los extremos se incluyen."""
        self.assertEqual(self.filtrar(desde=en(-1)), [self.pedido.pk])
        self.assertEqual(self.filtrar(hasta=en(-19)), [self.cancelado.pk])
        self.assertEqual(self.filtrar(desde=en(-20), hasta=en(-20)), [self.cancelado.pk])
        self.assertEqual(self.filtrar(fecha_de="limite", desde=en(2), hasta=en(4)), [self.pedido.pk])
        self.assertEqual(self.filtrar(fecha_de="limite", hasta=en(-15)), [self.cancelado.pk])

    def test_regla_2_solo_el_gerente_filtra_por_agronomo(self):
        """Regla 2: «solo para el Gerente, Agrónomo». Un Agrónomo no ve los de otro aunque lo pida."""
        self.assertEqual(sorted(self.filtrar(self.gerente, agronomo_id=self.ana.pk)), sorted([self.pedido.pk, self.cancelado.pk]))
        self.assertEqual(self.filtrar(self.gerente, agronomo_id=self.beto.pk), [self.ajeno.pk])
        self.assertEqual(self.filtrar(self.ana, agronomo_id=self.beto.pk).count(self.ajeno.pk), 0)

    def test_regla_2_los_filtros_se_combinan_y_uno_mal_formado_se_ignora(self):
        """Regla 2: se combinan; un valor que no es un número o una fecha no rompe la lista (se ignora)."""
        self.assertEqual(self.filtrar(estado="cancelado", proveedor_id=self.sur_prv.pk), [])
        self.assertEqual(self.filtrar(estado="en_cotizacion", proveedor_id=self.este_prv.pk, invernadero_id=self.norte.pk), [self.pedido.pk])
        self.assertEqual(sorted(self.filtrar(invernadero_id="abc", desde="no-es-fecha", estado="")), sorted([self.pedido.pk, self.cancelado.pk]))


class FichaDelPedidoTests(ConsultaBase):
    """Reglas 4 a 6: la ficha."""

    def test_regla_1_la_ficha_de_un_pedido_ajeno_es_403_y_la_de_uno_inexistente_404(self):
        """Regla 1 y D-28: el Agrónomo no abre el pedido de otro (``PermissionDenied``); un id que no existe es ``Http404``; el Gerente abre cualquiera."""
        with self.assertRaises(PermissionDenied):
            pedidos.ficha_de_pedido(self.ana, self.ajeno.pk)
        with self.assertRaises(Http404):
            pedidos.ficha_de_pedido(self.ana, 999999)
        self.assertEqual(pedidos.ficha_de_pedido(self.gerente, self.ajeno.pk).pedido.pk, self.ajeno.pk)

    def test_regla_4_el_pedido_con_sus_detalles_agrupados_por_invernadero_y_su_monto(self):
        """Regla 4: el Agrónomo que lo realizó; los detalles agrupados por invernadero de destino con insumo, cantidad, unidad, precio de referencia y subtotal; el monto estimado."""
        segundo = crear_invernadero("Otro", agronomo=self.ana)
        en_otro = existencia(self.lechuga_norte.insumo, segundo, minimo=10, precio="11.00")
        detalle_de_pedido(self.pedido, en_otro, cantidad="5")
        ficha = pedidos.ficha_de_pedido(self.ana, self.pedido.pk)
        self.assertEqual(ficha.pedido.agronomo_id, self.ana.pk)
        self.assertEqual(ficha.monto, Decimal("605.00"))  # 250,00 + 300,00 + 55,00
        self.assertEqual([(inv.nombre_invernadero, [(d.pk, d.subtotal) for d in detalles]) for inv, detalles in ficha.grupos],
                         [("Norte", [(self.d_lechuga.pk, Decimal("250.00")), (self.d_nutriente.pk, Decimal("300.00"))]),
                          ("Otro", [(en_otro_detalle_id(self.pedido, en_otro), Decimal("55.00"))])])

    def test_regla_4_un_pedido_cancelado_muestra_el_motivo_la_fecha_de_cierre_y_si_fue_automatica(self):
        """Regla 4: si está cancelado, el motivo, la fecha de cierre y si fue automática (la causa)."""
        automatico = armar_pedido(self.ana, estado="cancelado", causa="nadie_cotizo", motivo="nadie cotizó")
        manual = armar_pedido(self.ana, estado="cancelado", causa="manual", motivo="Ya no hace falta")
        a, m = pedidos.ficha_de_pedido(self.ana, automatico.pk), pedidos.ficha_de_pedido(self.ana, manual.pk)
        self.assertEqual((a.pedido.causa_cancelacion, a.automatica), ("nadie_cotizo", True))
        self.assertEqual((m.pedido.causa_cancelacion, m.automatica, m.pedido.motivo_cancelacion), ("manual", False, "Ya no hace falta"))
        self.assertEqual(m.pedido.fecha_cierre_pedido, timezone.localdate())
        self.assertFalse(pedidos.ficha_de_pedido(self.ana, self.pedido.pk).automatica)

    def test_regla_5_por_cada_invitado_si_cotizo_y_el_estado_de_su_enlace(self):
        """Regla 5: por cada proveedor invitado, si cotizó o no y el estado de su enlace (vigente, usado, vencido, anulado, reemplazado)."""
        EnlaceProveedor.objects.filter(pk=self.inv_sur.pk).update(estado="usado", fecha_uso=timezone.now())
        cotizacion_de(self.pedido, self.sur_prv, [(self.d_lechuga, 20, "250.00", 3)])
        invitados = {i.proveedor.pk: i for i in pedidos.ficha_de_pedido(self.ana, self.pedido.pk).invitados}
        self.assertEqual((invitados[self.sur_prv.pk].cotizo, invitados[self.sur_prv.pk].estado_del_enlace), (True, "usado"))
        self.assertEqual((invitados[self.este_prv.pk].cotizo, invitados[self.este_prv.pk].estado_del_enlace), (False, "vigente"))

    def test_regla_5_los_estados_del_enlace_vencido_anulado_y_reemplazado(self):
        """Regla 5: un enlace vigente con la fecha límite pasada se ve «vencido» aunque el paso diario todavía no lo haya marcado; los anulados y reemplazados, como tales."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(-1))
        EnlaceProveedor.objects.filter(pk=self.inv_este.pk).update(estado="anulado")
        invitados = {i.proveedor.pk: i for i in pedidos.ficha_de_pedido(self.ana, self.pedido.pk).invitados}
        self.assertEqual(invitados[self.sur_prv.pk].estado_del_enlace, "vencido")
        self.assertEqual(invitados[self.este_prv.pk].estado_del_enlace, "anulado")
        EnlaceProveedor.objects.filter(pk=self.inv_este.pk).update(estado="reemplazado")
        invitados = {i.proveedor.pk: i for i in pedidos.ficha_de_pedido(self.ana, self.pedido.pk).invitados}
        self.assertEqual(invitados[self.este_prv.pk].estado_del_enlace, "reemplazado")

    def test_regla_5_se_marca_el_envio_que_fallo(self):
        """D-88 punto 6: el enlace con el correo que no salió se marca («No se pudo enviar»); el que salió o todavía no se intentó, no."""
        EnlaceProveedor.objects.filter(pk=self.inv_sur.pk).update(estado_envio="pendiente_envio")
        EnlaceProveedor.objects.filter(pk=self.inv_este.pk).update(estado_envio="enviado")
        invitados = {i.proveedor.pk: i for i in pedidos.ficha_de_pedido(self.ana, self.pedido.pk).invitados}
        self.assertEqual((invitados[self.sur_prv.pk].sin_enviar, invitados[self.este_prv.pk].sin_enviar), (True, False))

    def test_regla_6_la_cotizacion_se_ve_en_solo_lectura_desde_que_llega(self):
        """Regla 6 y prototipo (decisión del estudiante, 23/11/2026): la cotización enviada por cada proveedor se ve en solo lectura desde que llega, con sus líneas y su monto, también para el Gerente."""
        cotizacion = cotizacion_de(self.pedido, self.sur_prv, [(self.d_lechuga, 20, "250.00", 3), (self.d_nutriente, 3, "120.30", 2)], observaciones="Cajones")
        for actor in (self.ana, self.gerente):
            with self.subTest(actor=actor):
                ficha = pedidos.ficha_de_pedido(actor, self.pedido.pk)
                self.assertEqual([c.cotizacion.pk for c in ficha.cotizaciones], [cotizacion.pk])
                vista = ficha.cotizaciones[0]
                self.assertEqual(vista.monto, Decimal("370.30"))
                self.assertEqual([(l.insumo, l.total, l.plazo) for l in vista.lineas], [("Lechuga", Decimal("250.00"), 3), ("Nutriente", Decimal("120.30"), 2)])
                self.assertEqual(vista.cotizacion.observaciones_cotizacion, "Cajones")

    def test_regla_6_sin_cotizaciones_la_lista_esta_vacia(self):
        """Regla 6: sin cotizaciones recibidas no hay nada que mostrar."""
        self.assertEqual(pedidos.ficha_de_pedido(self.ana, self.pedido.pk).cotizaciones, [])

    def test_regla_3_la_ficha_marca_el_pedido_vencido_por_resolver(self):
        """Regla 3: «por resolver» también en la ficha."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(-1))
        self.assertTrue(pedidos.ficha_de_pedido(self.ana, self.pedido.pk).por_resolver)


def en_otro_detalle_id(pedido, existencia_):
    """El id del detalle del ``pedido`` para la ``existencia_`` (para armar el resultado esperado)."""
    return pedido.detalles.get(insumo_invernadero=existencia_).pk


class ProveedorConPedidosTests(ConsultaBase):
    """Lo que CMP-01 dejó vacío para esta tarea (disparadores: «CMP-02a, CMP-02b, CMP-03 y CMP-05»)."""

    def test_regla_2_de_mod_un_proveedor_invitado_a_un_pedido_tiene_pedidos(self):
        """CMP-MOD-PRV regla 2: ``tiene_pedidos_u_ordenes`` es verdadero con una invitación (el CUIT deja de modificarse); falso sin ninguna."""
        self.assertTrue(proveedores.tiene_pedidos_u_ordenes(self.sur_prv))
        self.assertFalse(proveedores.tiene_pedidos_u_ordenes(proveedor("Sin pedidos", n=9)))

    def test_regla_2_de_mod_un_proveedor_con_cotizaciones_tiene_pedidos(self):
        """CMP-MOD-PRV regla 2: también con una cotización (aunque la invitación ya no figure)."""
        sin_invitacion = proveedor("Con cotización", n=8)
        cotizacion_de(self.pedido, sin_invitacion, [])
        self.assertTrue(proveedores.tiene_pedidos_u_ordenes(sin_invitacion))

    def test_regla_4_de_cns_prv_los_pedidos_de_un_proveedor_segun_el_alcance_de_quien_mira(self):
        """CMP-CNS-PRV regla 4: la ficha del proveedor lista sus pedidos (a los que lo invitaron); el Agrónomo ve solo los suyos, el Gerente todos."""
        cotizacion_de(self.pedido, self.sur_prv, [(self.d_lechuga, 20, "250.00", 3)])
        de_ana = proveedores.pedidos_del_proveedor(self.ana, self.sur_prv)
        self.assertEqual([(f.pedido.pk, f.cotizo) for f in de_ana], [(self.pedido.pk, True)])
        todos = proveedores.pedidos_del_proveedor(self.gerente, self.sur_prv)
        self.assertEqual(sorted(f.pedido.pk for f in todos), sorted([self.pedido.pk, self.ajeno.pk]))
        self.assertEqual({f.pedido.pk: f.cotizo for f in todos}[self.ajeno.pk], False)
