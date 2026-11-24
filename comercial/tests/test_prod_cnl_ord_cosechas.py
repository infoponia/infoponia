# Pruebas de PROD-CNL-ORD para una cosecha (COM-04a, paso 6; docs/casos_de_uso/produccion/cancelar_orden.md, «Cómo se aplica en la ronda «Comercial 1»:
# cosechas»): `comercial/servicios/cosechas.py`, SIN el `on_commit` de PROD-ASG-CAM (postcondición h: COM-04b) y SIN el enlace nuevo de 8c y 8d (COM-04c).
# Una prueba por postcondición (f, g, k, l, m, n) y por extensión (4b, 4c, 6b, 6c, 8a, 8b, 8c, 8d); cosecha sin contrato; con contrato que se vuelve a cubrir
# del todo con cámara, del todo con otro lote (cosecha nueva, sin los lotes excluidos), en parte y nada; período de un suministro; período de un detalle
# finalizado con fecha pendiente; la estimación 6b coincide con lo que después hace el paso 8; motivo vacío y de 301.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/cosechas.py`:
#   - `resumen_de_cancelacion_de_cosecha(actor, cosecha_id) -> ResumenDeCancelacion(cosecha, reserva, lineas, contrato, fecha_entrega, cubierto,
#     ya_pendiente, estimacion, huella)`: `lineas = [(codigo, cantidad)]` (lotes y partidas), `cubierto` lo que la reserva cubre del contrato, `ya_pendiente`
#     si el detalle o su venta esperan la decisión del cliente (6c), `estimacion = Estimacion(cubierto, sin_cubrir, origenes, hace_falta_cosecha)` con
#     `origenes = [(codigo del lote o de la partida, cantidad)]` (6b, solo lectura, con `simular(lotes_excluidos, sin_reservas)`) o `None` sin contrato o con
#     `ya_pendiente`; `huella` = `huella_de(cosecha)` más el estado del detalle y de la venta, leídos al abrir.
#   - `cancelar_cosecha(actor, cosecha_id, motivo, huella) -> CancelacionDeCosecha` y `cancelar_cosecha_incluida(actor, cosecha, motivo, *, recubrir=True,
#     avisar=True) -> CancelacionDeCosecha(cosecha, reserva, lineas, cubierto, asignacion, sin_cubrir, notificar_a)`: `asignacion` es lo que devolvió `asignar`
#     (o `None`), `sin_cubrir` lo que siguió el camino de faltante. `ValidationError` por campo con `motivo_obligatorio`, `motivo_largo` (los de PRD-01),
#     `orden_no_a_realizar` (8a) y `cosecha_cambio` (8b); `PermissionDenied` si no es el Agrónomo a cargo.
# Fuente: PROD-CNL-ORD (Comercial 1: cosechas), D-64 puntos 8 y 13, D-36, D-42 y `docs/patrones/stock_maduro.md` (sección 8).

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleSuministro, DetalleVenta, ReservaStock
from comercial.servicios import cosechas, stock_maduro
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    detalle_suministro,
    escenario_comercial,
    partida_cosechada,
    periodo,
    reserva,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo
from produccion.models import Bitacora, Cosecha, Lote, MovimientoStock, OrdenTrabajo
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def en(dias):
    """La fecha de dentro de ``dias`` días."""
    return HOY + timedelta(days=dias)


def codigos(prueba, llamada, campo=None):
    """Los códigos de los errores de un `ValidationError` que lanza `llamada()` (los de `campo`, o todos)."""
    with prueba.assertRaises(ValidationError) as rechazo:
        llamada()
    return sorted(e.code for clave, lista in rechazo.exception.error_dict.items() if campo in (None, clave) for e in lista)


class Base(ConDatosDeInventario, TestCase):
    """Una cosecha manual con contrato (compra-venta con envío de 50 plantas para dentro de 10 días) que reserva 30 plantas de un lote de 100."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.venta = compra_venta(self.e, dias=10)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=self.detalle, dias=5)
        self.addCleanup(verificar_invariantes_de_reservas)

    def camara(self, cantidad):
        """Una partida de `cantidad` plantas cuyo lote ya está finalizado (no aporta stock en pie: solo la cámara)."""
        lote = lote_maduro(self.e, 1)
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        return partida_cosechada(lote, cantidad)

    def huella(self):
        return cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk).huella

    def cancelar(self, motivo="Se rompió el sistema de riego", actor=None, cosecha=None, huella=None):
        cosecha = cosecha or self.cosecha
        huella = huella or cosechas.resumen_de_cancelacion_de_cosecha(actor or self.e.agronomo, cosecha.pk).huella
        return cosechas.cancelar_cosecha(actor or self.e.agronomo, cosecha.pk, motivo, huella)

    def reserva_de(self, cosecha=None):
        return ReservaStock.objects.get(cosecha=cosecha or self.cosecha)

    def releer(self, modelo, pk):
        return modelo.objects.get(pk=pk)


class ResumenTests(Base):
    def test_ext_4b_sin_contrato_el_resumen_dice_que_el_stock_vuelve_a_estar_libre(self):
        """4b: la reserva con sus lotes y cantidades; sin contrato no hay estimación ni camino de faltante."""
        sin = cosecha_manual(self.e, [(self.lote, 20)], dias=2)
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, sin.pk)
        self.assertEqual((resumen.contrato, resumen.estimacion, resumen.cubierto), (None, None, 0))
        self.assertEqual(resumen.lineas, [(self.lote.codigo, 20)])

    def test_ext_4c_con_contrato_el_resumen_trae_lotes_y_partidas_el_contrato_y_lo_cubierto(self):
        """4c: la reserva con sus lotes y sus partidas, el contrato (código y fecha de entrega) y la cantidad que la reserva cubre."""
        partida = partida_cosechada(self.lote, 10)
        mixta = cosecha_manual(self.e, [(self.lote, 15)], detalle_=detalle(compra_venta(self.e, dias=9), self.e.variedad, 40), dias=3)
        DetalleReserva.objects.create(reserva=self.reserva_de(mixta), partida=partida, cantidad_reservada=10)
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, mixta.pk)
        self.assertEqual(sorted(resumen.lineas), sorted([(self.lote.codigo, 15), (partida.codigo, 10)]))
        self.assertEqual(resumen.cubierto, 25)
        self.assertEqual((resumen.contrato is not None, resumen.fecha_entrega), (True, en(9)))

    def test_ext_6b_la_estimacion_dice_si_se_vuelve_a_cubrir_con_otros_lotes_o_con_camara(self):
        """6b: `simular` con `lotes_excluidos` (los de la cosecha) y `sin_reservas` (la reserva): con otro lote de 100, se cubren los 30; con nada, quedan 30
        sin cubrir; con una partida de 12 y nada más, 12 y faltan 18."""
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk)
        self.assertEqual((resumen.estimacion.cubierto, resumen.estimacion.sin_cubrir), (0, 30))
        otro = lote_maduro(self.e, 100)
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk)
        self.assertEqual((resumen.estimacion.cubierto, resumen.estimacion.sin_cubrir, resumen.estimacion.hace_falta_cosecha), (30, 0, True))
        self.assertEqual(resumen.estimacion.origenes, [(otro.codigo, 30)])

    def test_ext_6b_la_estimacion_con_camara_no_hace_falta_cosechar(self):
        """6b: lo que sale de una partida no necesita una cosecha nueva."""
        partida = self.camara(30)
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk)
        self.assertEqual((resumen.estimacion.cubierto, resumen.estimacion.hace_falta_cosecha, resumen.estimacion.origenes), (30, False, [(partida.codigo, 30)]))

    def test_ext_6c_un_detalle_que_ya_espera_la_decision_del_cliente_no_se_vuelve_a_cubrir(self):
        """6c: con el detalle «pendiente de decisión», el resumen avisa (`ya_pendiente`) y no estima: no se intentará volver a cubrir."""
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="pendiente_decision", fecha_pendiente_decision=en(-2))
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="pendiente_decision")
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk)
        self.assertEqual((resumen.ya_pendiente, resumen.estimacion), (True, None))

    def test_regla_el_resumen_no_escribe_y_solo_lo_ve_el_agronomo_a_cargo(self):
        """El resumen es de lectura (sin auditoría, avisos ni cambios) y `PermissionDenied` para el Gerente, el Capataz y un Agrónomo ajeno."""
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count(), self.releer(Cosecha, self.cosecha.pk).estado_orden), (*antes, "a_realizar"))
        for actor in (crear_gerente(), self.e.capataz, self.e.vendedor, crear_agronomo(email="otro@infoponia.com")):
            with self.assertRaises(PermissionDenied):
                cosechas.resumen_de_cancelacion_de_cosecha(actor, self.cosecha.pk)


class PostcondicionesTests(Base):
    def test_post_f_la_cosecha_queda_cancelada_y_su_reserva_liberada_sin_cantidades_cosechadas(self):
        """f: la orden «cancelada» con la fecha de hoy y el motivo; la reserva «liberada»; las líneas de lote sin cantidad cosechada."""
        self.cancelar("Se rompió el riego")
        c = self.releer(Cosecha, self.cosecha.pk)
        self.assertEqual((c.estado_orden, c.fecha_resolucion_orden, c.motivo_cancelacion), ("cancelada", HOY, "Se rompió el riego"))
        self.assertEqual(self.reserva_de().estado_reserva, "liberada")
        self.assertEqual(list(DetalleReserva.objects.filter(reserva__cosecha=self.cosecha).values_list("cantidad_cosechada", flat=True)), [None])

    def test_post_f_las_lineas_de_partida_quedan_sin_cambios(self):
        """f: las líneas de partida de la reserva liberada se conservan (la reserva liberada ya no cuenta para el stock libre)."""
        partida = partida_cosechada(self.lote, 10)
        DetalleReserva.objects.create(reserva=self.reserva_de(), partida=partida, cantidad_reservada=10)
        self.cancelar()
        self.assertEqual(DetalleReserva.objects.get(partida=partida, reserva__cosecha=self.cosecha).cantidad_reservada, 10)

    def test_post_h_las_lineas_de_camara_que_se_liberan_programan_la_asignacion_de_camara(self):
        """h y D-64 punto 9 (COM-04b): si la reserva liberada tenía líneas de cámara, `transaction.on_commit` corre PROD-ASG-CAM con esas partidas (el stock que apartaba vuelve a
        estar libre)."""
        from unittest import mock

        partida = self.camara(5)
        cosecha = reserva(detalle(compra_venta(self.e, dias=12), self.e.variedad, 20), [(self.lote, 10), (partida, 5)]).cosecha
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar, self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.cancelar(cosecha=cosecha)
        self.assertEqual(len(callbacks), 1)
        asignar.assert_called_once_with([partida.pk])

    def test_post_h_una_cosecha_sin_lineas_de_camara_no_programa_nada(self):
        """h: sin líneas de cámara en la reserva liberada no se programa PROD-ASG-CAM."""
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.cancelar()
        self.assertEqual(callbacks, [])

    def test_post_h_la_cancelacion_incluida_tambien_programa_la_asignacion(self):
        """h: `cancelar_cosecha_incluida` (COM-DCD-FLT, COM-05) usa la misma lógica y programa PROD-ASG-CAM con las partidas de cámara que libera."""
        from unittest import mock
        from django.db import transaction

        partida = self.camara(5)
        cosecha = reserva(detalle(compra_venta(self.e, dias=12), self.e.variedad, 20), [(self.lote, 10), (partida, 5)]).cosecha
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar, self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                cosechas.cancelar_cosecha_incluida(None, cosecha, "Se cancela la venta", recubrir=False, avisar=False)
        asignar.assert_called_once_with([partida.pk])

    def test_post_g_con_contrato_el_detalle_se_vuelve_a_cubrir_sin_los_lotes_de_la_cosecha_cancelada(self):
        """g y 8c: con otro lote, `asignar` reserva los 30 del contrato fuera del lote cancelado y programa una cosecha nueva (automática); el detalle y la
        venta siguen abiertos."""
        otro = lote_maduro(self.e, 100)
        resultado = self.cancelar()
        self.assertEqual((resultado.asignacion.cubierta, resultado.asignacion.sin_cubrir, resultado.sin_cubrir), (30, 0, 0))
        nueva = Cosecha.objects.exclude(pk=self.cosecha.pk).get()
        self.assertEqual(nueva.origen_cosecha, "automatica")
        self.assertEqual(list(DetalleReserva.objects.filter(reserva__cosecha=nueva).values_list("lote_id", "cantidad_reservada")), [(otro.pk, 30)])
        self.assertEqual((self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, self.releer(CompraVenta, self.venta.pk).estado_venta), ("abierto", "abierta"))

    def test_post_g_con_camara_se_cubre_del_todo_sin_cosecha_nueva(self):
        """g: con una partida de 40 en la cámara, el contrato se cubre ahí (reserva «lista para entrega») y no se programa ninguna cosecha."""
        partida = self.camara(40)
        resultado = self.cancelar()
        self.assertEqual((resultado.asignacion.cubierta, resultado.asignacion.sin_cubrir, resultado.asignacion.cosechas), (30, 0, []))
        self.assertEqual(DetalleReserva.objects.get(partida=partida).reserva.estado_reserva, "lista_para_entrega")
        self.assertEqual(Cosecha.objects.count(), 1)

    def test_post_g_cubierto_en_parte_lo_que_falta_sigue_el_camino_de_faltante(self):
        """8c: con solo 12 en cámara, se cubren 12 y los 18 restantes siguen el camino de faltante: el detalle y la venta pasan a «pendiente de decisión del
        cliente» con la fecha de hoy."""
        self.camara(12)
        resultado = self.cancelar()
        self.assertEqual((resultado.asignacion.cubierta, resultado.sin_cubrir), (12, 18))
        detalle_ = self.releer(DetalleVenta, self.detalle.pk)
        self.assertEqual((detalle_.estado_detalle_venta, detalle_.fecha_pendiente_decision), ("pendiente_decision", HOY))
        self.assertEqual(self.releer(CompraVenta, self.venta.pk).estado_venta, "pendiente_decision")

    def test_post_g_sin_nada_para_cubrir_todo_va_al_camino_de_faltante(self):
        """8c con cobertura nula: los 30 quedan sin cubrir."""
        resultado = self.cancelar()
        self.assertEqual((resultado.asignacion.cubierta, resultado.sin_cubrir), (0, 30))
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_ext_8d_un_detalle_que_ya_esperaba_no_llama_a_asignar_y_actualiza_la_fecha(self):
        """6c y 8d: sin `asignar` (aunque haya stock): el camino de faltante con la cantidad liberada y la fecha de pendiente de hoy."""
        lote_maduro(self.e, 100)
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="pendiente_decision", fecha_pendiente_decision=en(-3))
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="pendiente_decision")
        resultado = self.cancelar()
        self.assertEqual((resultado.asignacion, resultado.sin_cubrir), (None, 30))
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).fecha_pendiente_decision, HOY)
        self.assertEqual(Cosecha.objects.count(), 1)

    def test_ext_4b_sin_contrato_no_hay_asignacion_ni_camino_de_faltante(self):
        """Cosecha sin contrato: se cancela y se libera la reserva; nada más (ni `asignar` ni detalle que cambiar)."""
        sin = cosecha_manual(self.e, [(self.lote, 20)], dias=2)
        resultado = self.cancelar(cosecha=sin)
        self.assertEqual((resultado.asignacion, resultado.sin_cubrir, resultado.cubierto), (None, 0, 0))
        self.assertEqual(self.releer(DetalleVenta, self.detalle.pk).estado_detalle_venta, "abierto")

    def test_regla_un_periodo_de_suministro_se_vuelve_a_cubrir_o_queda_con_cantidad_sin_cubrir(self):
        """Período de un suministro: con otro lote se vuelve a cubrir; sin él queda con cantidad sin cubrir y no cambia de estado."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=8)
        c = cosecha_manual(self.e, [(self.lote, 30)], periodo_=periodo(det, en(8)), dias=3)
        resultado = self.cancelar(cosecha=c)
        self.assertEqual((resultado.asignacion.cubierta, resultado.sin_cubrir), (0, 30))
        self.assertEqual(self.releer(DetalleSuministro, det.pk).estado_detalle_suministro, "vigente")
        self.assertEqual(stock_maduro.cantidad_sin_cubrir(periodo(self.releer(DetalleSuministro, det.pk), en(8))), 30)

    def test_regla_d64_8_el_periodo_de_un_detalle_finalizado_con_fecha_pendiente_se_vuelve_a_cubrir(self):
        """D-64 punto 8: cancelar la cosecha de un período de un detalle «finalizado» con fecha ≤ `fecha_fin_detalle` lo vuelve a cubrir igual que a uno vigente."""
        det = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=8, estado="finalizado", fecha_fin_detalle=en(8))
        c = cosecha_manual(self.e, [(self.lote, 30)], periodo_=periodo(det, en(8)), dias=3)
        otro = lote_maduro(self.e, 100)
        resultado = self.cancelar(cosecha=c)
        self.assertEqual((resultado.asignacion.cubierta, resultado.sin_cubrir), (30, 0))
        self.assertEqual(Cosecha.objects.exclude(pk__in=[self.cosecha.pk, c.pk]).get().variedad_id, otro.siembra.variedad_id)

    def test_post_k_se_avisa_al_capataz_con_el_motivo(self):
        """k: «Orden OT-… cancelada» al Capataz con el motivo, el tipo y la fecha de la orden y quién canceló (el texto de `produccion`)."""
        self.cancelar("Plaga en el invernadero")
        aviso = Notificacion.objects.get(destinatario=self.e.capataz)
        self.assertEqual(aviso.titulo, f"Orden {self.cosecha.codigo} cancelada")
        self.assertIn("Motivo: Plaga en el invernadero.", aviso.detalle)

    def test_post_k_sin_capataz_activo_no_se_avisa_a_nadie(self):
        """9a: sin Capataz activo, no se avisa y se cancela igual."""
        type(self.e.capataz).objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.cancelar()
        self.assertFalse(Notificacion.objects.filter(destinatario=self.e.capataz).exists())

    def test_post_l_con_contrato_se_avisa_al_vendedor_con_lo_que_se_cubrio_y_lo_que_no(self):
        """l: «Cosecha OT-… de CV-… cancelada», con lo que se volvió a cubrir y lo que quedó sin cubrir; sin contrato, el Vendedor no recibe nada."""
        self.camara(12)
        self.cancelar()
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertEqual(aviso.titulo, f"Cosecha {self.cosecha.codigo} de {self.venta.codigo} cancelada")
        self.assertIn("12", aviso.detalle)
        self.assertIn("18", aviso.detalle)
        Notificacion.objects.filter(destinatario=self.e.vendedor).delete()
        self.cancelar(cosecha=cosecha_manual(self.e, [(self.lote, 5)], dias=2))
        self.assertFalse(Notificacion.objects.filter(destinatario=self.e.vendedor).exists())

    def test_post_m_y_n_un_registro_de_auditoria_y_sin_bitacora_ni_movimientos_de_stock(self):
        """m, n y la regla «Sin bitácora»: UN registro `cancelacion_orden` con la orden, la reserva y sus líneas, el detalle y la venta; no hay registro de
        bitácora ni movimiento de stock."""
        antes = RegistroAuditoria.objects.count()
        self.cancelar()
        self.assertEqual(RegistroAuditoria.objects.count(), antes + 1)
        registro = RegistroAuditoria.objects.latest("pk")
        self.assertEqual((registro.accion, registro.usuario_id), ("cancelacion_orden", self.e.agronomo.pk))
        textos = [a["texto"] for a in registro.afectados]
        self.assertIn(self.cosecha.codigo, textos)
        self.assertTrue(any(t.startswith("Reserva #") for t in textos) and any(t.startswith("Línea #") for t in textos))
        self.assertTrue(any(self.venta.codigo in t for t in textos))
        self.assertFalse(Bitacora.objects.filter(tipo_evento="cosecha").exists())
        self.assertFalse(MovimientoStock.objects.exists())

    def test_regla_cualquier_cosecha_la_cancela_el_agronomo_a_cargo_incluso_la_automatica(self):
        """Regla 2 de 8.22: el Agrónomo a cargo la cancela de cualquier origen (automática de InfoPonia también)."""
        automatica = cosecha_manual(self.e, [(self.lote, 5)], detalle_=self.detalle, dias=2, origen="automatica")
        self.assertEqual(self.cancelar(cosecha=automatica).cosecha.estado_orden, "cancelada")

    def test_regla_solo_el_agronomo_a_cargo_cancela(self):
        """El Gerente, el Capataz, el Vendedor y un Agrónomo ajeno reciben `PermissionDenied`; no cambia nada."""
        huella = self.huella()
        for actor in (crear_gerente(), self.e.capataz, self.e.vendedor, crear_agronomo(email="otro@infoponia.com")):
            with self.assertRaises(PermissionDenied):
                cosechas.cancelar_cosecha(actor, self.cosecha.pk, "x", huella)
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).estado_orden, "a_realizar")


class ExtensionesTests(Base):
    def test_ext_6a_el_motivo_es_obligatorio_y_de_hasta_300_caracteres(self):
        """Motivo vacío (`motivo_obligatorio`) y de 301 (`motivo_largo`): nada cambia; de 300 se acepta."""
        huella = self.huella()
        self.assertEqual(codigos(self, lambda: self.cancelar("  ", huella=huella), "motivo"), ["motivo_obligatorio"])
        self.assertEqual(codigos(self, lambda: self.cancelar("x" * 301, huella=huella), "motivo"), ["motivo_largo"])
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).estado_orden, "a_realizar")
        self.cancelar("x" * 300, huella=huella)

    def test_ext_8a_una_cosecha_que_ya_no_esta_a_realizar_no_se_cancela(self):
        """8a: `orden_no_a_realizar` con el estado actual (otro la canceló mientras se miraba el resumen)."""
        huella = self.huella()
        OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")
        with self.assertRaises(ValidationError) as rechazo:
            self.cancelar(huella=huella)
        error = next(e for lista in rechazo.exception.error_dict.values() for e in lista)
        self.assertEqual(error.code, "orden_no_a_realizar")
        self.assertIn("cancelada", error.message)

    def test_ext_8b_si_cambiaron_la_reserva_o_el_detalle_desde_el_resumen_no_se_cancela(self):
        """8b: `cosecha_cambio` si cambió la reserva (una línea), la cosecha o el estado del detalle o de la venta entre el resumen y el registro."""
        huella = self.huella()
        DetalleReserva.objects.filter(reserva__cosecha=self.cosecha).update(cantidad_reservada=29)
        self.assertEqual(codigos(self, lambda: self.cancelar(huella=huella)), ["cosecha_cambio"])
        self.assertEqual(self.releer(Cosecha, self.cosecha.pk).estado_orden, "a_realizar")
        DetalleReserva.objects.filter(reserva__cosecha=self.cosecha).update(cantidad_reservada=30)
        huella = self.huella()
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="pendiente_decision")
        self.assertEqual(codigos(self, lambda: self.cancelar(huella=huella)), ["cosecha_cambio"])

    def test_ext_6b_la_estimacion_coincide_con_lo_que_despues_hace_el_paso_8(self):
        """Una prueba compara la estimación del resumen con lo que después reserva `asignar` en el paso 8 (patrón, sección 8): con un lote de 20 y una
        partida de 5, la estimación dice 25 cubiertas y 5 sin cubrir, y la cancelación hace exactamente eso."""
        con_camara = lote_maduro(self.e, 20)
        partida_cosechada(con_camara, 5)
        resumen = cosechas.resumen_de_cancelacion_de_cosecha(self.e.agronomo, self.cosecha.pk)
        resultado = self.cancelar(huella=resumen.huella)
        self.assertEqual((resumen.estimacion.cubierto, resumen.estimacion.sin_cubrir), (resultado.asignacion.cubierta, resultado.sin_cubrir))
        self.assertEqual((resultado.asignacion.cubierta, resultado.sin_cubrir), (25, 5))
