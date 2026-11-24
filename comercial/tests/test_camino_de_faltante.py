# Pruebas del camino de faltante (COM-04a, paso 3; docs/patrones/stock_maduro.md, sección 8; docs/casos_de_uso/comercial/faltante.md, «El camino de
# faltante»): `comercial/servicios/faltantes.py`, `seguir_camino_de_faltante`. La usan PROD-CNC-CSC (13a), PROD-REG-MRM (10c), PROD-CNL-ORD (8c y 8d) y
# PROD-VNC-CAM (3a.2a); acá se prueba sola, sin enlace ni correo (los suma COM-04c en esta misma función).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar):
#   - `seguir_camino_de_faltante(detalle_o_periodo, sin_cubrir, *, origen) -> CaminoDeFaltante(detalle, venta, sin_cubrir, ya_pendiente)`.
#     `detalle_o_periodo` es un `DetalleVenta` o un `Periodo`; `sin_cubrir` es un entero mayor que cero (si no, `ValueError`); `origen` es quien actúa
#     (`Usuario`) o `None` si actúa InfoPonia (D-27: lo usará COM-04c para el enlace). Corre en la transacción del llamador (sin ella,
#     `RuntimeError`), con la venta y el detalle ya bloqueados; NO audita ni notifica: el caso de uso que lo llama arma su texto al Vendedor.
#   - Detalle de compra-venta: pasa a «pendiente de decisión del cliente» con `fecha_pendiente_decision = hoy`; si ya lo estaba, solo cambia la
#     fecha (8d de PROD-CNL-ORD: el plazo se cuenta desde la fecha más reciente) y `ya_pendiente = True`. La venta pasa a «pendiente de decisión del
#     cliente» (si ya lo estaba, no cambia).
#   - Detalle «confirmado» que pierde producto (D-64 punto 13): vuelve a «pendiente de decisión del cliente» con `fecha_pendiente_decision = hoy` y
#     `cant_entregada_venta` vacía; la venta también.
#   - Período de un suministro: no cambia ningún estado; queda con cantidad sin cubrir (la pre-reserva diaria lo vuelve a intentar).
# Fuente: D-64 puntos 8 y 13 y PROD-CNC-CSC (extensión 13a, regla «Faltante»).

from datetime import timedelta

from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente
from comercial.servicios import faltantes
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    enlace as un_enlace,
    escenario_comercial,
    periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario

HOY = timezone.localdate()
Estado = DetalleVenta.Estado


class Base(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.venta = compra_venta(self.e)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.addCleanup(verificar_invariantes_de_reservas)

    def seguir(self, detalle_=None, sin_cubrir=10):
        """Llama al camino de faltante (los tests de Django ya corren dentro de una transacción) y recarga la venta y el detalle."""
        resultado = faltantes.seguir_camino_de_faltante(detalle_ or self.detalle, sin_cubrir, origen=self.e.vendedor)
        self.detalle.refresh_from_db()
        self.venta.refresh_from_db()
        return resultado


class CompraVentaTests(Base):
    def test_regla_un_detalle_abierto_pasa_a_pendiente_de_decision_con_la_fecha_de_hoy_y_la_venta_tambien(self):
        """Camino de faltante: detalle y venta a «pendiente de decisión del cliente», `fecha_pendiente_decision = hoy`."""
        resultado = self.seguir()
        self.assertEqual((self.detalle.estado_detalle_venta, self.detalle.fecha_pendiente_decision), (Estado.PENDIENTE_DECISION, HOY))
        self.assertEqual(self.venta.estado_venta, CompraVenta.Estado.PENDIENTE_DECISION)
        self.assertEqual((resultado.detalle.pk, resultado.venta.pk, resultado.sin_cubrir, resultado.ya_pendiente), (self.detalle.pk, self.venta.pk, 10, False))

    def test_ext_8d_un_detalle_que_ya_esperaba_solo_cambia_la_fecha_de_pendiente(self):
        """PROD-CNL-ORD 8d: si el detalle ya estaba pendiente, solo se actualiza la fecha (el plazo se cuenta desde la más reciente)."""
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(
            estado_detalle_venta=Estado.PENDIENTE_DECISION, fecha_pendiente_decision=HOY - timedelta(days=3)
        )
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="pendiente_decision")
        resultado = self.seguir()
        self.assertEqual((self.detalle.estado_detalle_venta, self.detalle.fecha_pendiente_decision), (Estado.PENDIENTE_DECISION, HOY))
        self.assertEqual(self.venta.estado_venta, "pendiente_decision")
        self.assertTrue(resultado.ya_pendiente)

    def test_regla_d64_13_un_detalle_confirmado_vuelve_a_pendiente_sin_cantidad_entregada(self):
        """D-64 punto 13: el confirmado que pierde producto vuelve a «pendiente de decisión del cliente», con la fecha de hoy y SIN `cant_entregada_venta`;
        la venta también (al cliente no le cambian lo que aceptó sin preguntarle)."""
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta=Estado.CONFIRMADO, cant_entregada_venta=30)
        self.seguir(sin_cubrir=5)
        self.assertEqual((self.detalle.estado_detalle_venta, self.detalle.fecha_pendiente_decision), (Estado.PENDIENTE_DECISION, HOY))
        self.assertIsNone(self.detalle.cant_entregada_venta)
        self.assertEqual(self.venta.estado_venta, CompraVenta.Estado.PENDIENTE_DECISION)

    def test_regla_los_otros_detalles_de_la_venta_no_cambian(self):
        """Solo el detalle que quedó sin cubrir cambia de estado; otro detalle abierto de la misma venta sigue «abierto»."""
        from maestros.tests.fabricas import crear_variedad  # una segunda variedad para el segundo detalle

        segunda = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        otro = detalle(self.venta, segunda, 5)
        self.seguir()
        otro.refresh_from_db()
        self.assertEqual(otro.estado_detalle_venta, Estado.ABIERTO)


class EnlaceDelCaminoTests(Base):
    """COM-04c (D-65 puntos 1, 5 y 6): el camino de faltante crea o reemplaza el enlace del cliente y, sin correo, avisa al Vendedor."""

    def test_regla_con_correo_crea_el_enlace_vigente_que_vence_con_la_vigencia_configurada(self):
        """Regla «Enlace de decisión»: un enlace `vigente` de la venta que vence en la `fecha_pendiente_decision` más reciente + `dias_vigencia_enlace_faltante` (2 de fábrica)."""
        resultado = self.seguir()
        creado = EnlaceCliente.objects.get(compra_venta=self.venta)
        self.assertEqual(resultado.enlace.pk, creado.pk)
        self.assertEqual((creado.estado, creado.tipo, creado.cliente_id, creado.fecha_vencimiento), ("vigente", "decision_faltante", self.venta.cliente_id, HOY + timedelta(days=2)))

    def test_regla_el_vencimiento_cuenta_desde_la_fecha_de_pendiente_mas_reciente(self):
        """8d de PROD-CNL-ORD y la regla «Enlace de decisión»: con otro detalle que esperaba desde hace 3 días y la vigencia en 5, vence a los 5 días de la fecha MÁS RECIENTE."""
        from maestros.models import ConfiguracionOperativa
        from maestros.tests.fabricas import crear_variedad

        ConfiguracionOperativa.objects.filter(singleton=1).update(dias_vigencia_enlace_faltante=5)
        viejo = detalle(self.venta, crear_variedad(self.e.variedad.cultivo, nombre="Otra"), 5, estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=viejo.pk).update(fecha_pendiente_decision=HOY - timedelta(days=3))
        self.seguir()
        self.assertEqual(EnlaceCliente.objects.get(compra_venta=self.venta).fecha_vencimiento, HOY + timedelta(days=5))

    def test_regla_reemplaza_al_enlace_vigente_de_la_venta(self):
        """8d y D-65 punto 5: un faltante nuevo (otro detalle o más producto perdido) reemplaza el enlace vigente: el viejo, `reemplazado`; uno solo vigente."""
        viejo, _ = un_enlace(self.venta)
        self.seguir()
        viejo.refresh_from_db()
        self.assertEqual(viejo.estado, "reemplazado")
        self.assertEqual(EnlaceCliente.objects.filter(compra_venta=self.venta, estado="vigente").count(), 1)

    @override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
    def test_regla_el_correo_sale_con_on_commit_con_las_cantidades_y_la_url(self):
        """D-65 punto 6: el correo no sale dentro de la transacción; con `on_commit` lleva la URL con el token, la cantidad solicitada y la disponible; el envío queda anotado."""
        with mock.patch("core.correo.enviar_correo", return_value=True) as envio:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.seguir()
            self.assertEqual((envio.call_count, len(callbacks)), (0, 1))
            callbacks[0]()  # recién ahora sale el correo, con el parche todavía activo
        contexto = envio.call_args.args[3]
        self.assertTrue(contexto["url"].startswith("https://sitio.test/cliente/"))
        self.assertEqual(contexto["lineas"], [{"variedad": str(self.e.variedad), "solicitada": 50, "disponible": 0}])
        self.assertEqual(EnlaceCliente.objects.get(compra_venta=self.venta).estado_envio, "enviado")

    def test_regla_un_periodo_de_suministro_no_crea_enlace(self):
        """El período de un suministro no cambia de estado ni tiene enlace (la pre-reserva diaria lo vuelve a intentar)."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=3)
        resultado = faltantes.seguir_camino_de_faltante(periodo(det, HOY + timedelta(days=3)), 12, origen=None)
        self.assertEqual((resultado.enlace, EnlaceCliente.objects.count()), (None, 0))


class SinCorreoDelClienteTests(Base):
    def setUp(self):
        self.e = escenario_comercial(email_del_cliente="")
        self.venta = compra_venta(self.e)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.addCleanup(verificar_invariantes_de_reservas)

    def test_regla_sin_correo_no_hay_enlace_y_el_vigente_pasa_a_reemplazado(self):
        """D-65 punto 1 y patrón, sección 2: el cliente sin correo no tiene enlace; el que hubiera pasa a `reemplazado`."""
        viejo, _ = un_enlace(self.venta)
        resultado = self.seguir()
        viejo.refresh_from_db()
        self.assertEqual((resultado.enlace, viejo.estado, EnlaceCliente.objects.filter(estado="vigente").count()), (None, "reemplazado", 0))

    def test_regla_sin_correo_se_avisa_al_vendedor_que_registre_la_decision(self):
        """Regla del camino de faltante: «El cliente de CV-… no tiene correo: registrá vos su decisión sobre el faltante.»"""
        self.seguir()
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertIn(self.venta.codigo, aviso.titulo)
        self.assertIn("no tiene correo: registrá vos su decisión", aviso.detalle)


class PeriodoTests(Base):
    def test_regla_un_periodo_no_cambia_ningun_estado_y_queda_con_cantidad_sin_cubrir(self):
        """Período de suministro: no cambia de estado (ni el detalle ni el suministro); la cantidad sin cubrir se queda para la pre-reserva diaria."""
        sum_ = suministro(self.e)
        det = detalle_suministro(sum_, self.e.variedad, cantidad=30, primera_en_dias=3)
        resultado = faltantes.seguir_camino_de_faltante(periodo(det, HOY + timedelta(days=3)), 12, origen=None)
        det.refresh_from_db()
        sum_.refresh_from_db()
        self.assertEqual((det.estado_detalle_suministro, sum_.estado_suministro), ("vigente", "vigente"))
        self.assertEqual((resultado.venta, resultado.sin_cubrir, resultado.ya_pendiente), (None, 12, False))


class ContratoDeLaFuncionTests(Base):
    def test_regla_una_cantidad_que_no_es_mayor_que_cero_lanza_value_error(self):
        """Solo se sigue el camino con algo sin cubrir: 0, negativo o no entero es un error de programación (`ValueError`)."""
        for valor in (0, -3, 2.5):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                faltantes.seguir_camino_de_faltante(self.detalle, valor, origen=None)

    def test_regla_sin_transaccion_lanza_runtime_error(self):
        """Corre en la transacción del caso de uso que la llama."""
        from unittest import mock

        from django.db import transaction

        with mock.patch.object(transaction, "get_autocommit", return_value=True), self.assertRaises(RuntimeError):
            faltantes.seguir_camino_de_faltante(self.detalle, 5, origen=None)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, Estado.ABIERTO)

    def test_regla_no_audita_ni_notifica(self):
        """La notificación al Vendedor la arma cada caso de uso (cada uno tiene su texto); esta función no audita (D-36) ni avisa."""
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        self.seguir()
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))
