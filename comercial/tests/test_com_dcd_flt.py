# Pruebas de COM-DCD-FLT · Decidir Faltante (COM-04c, paso 4; docs/casos_de_uso/comercial/faltante.md; D-65, D-64 puntos 12 y 13): `comercial/servicios/faltantes.py`. Una prueba por
# postcondición (a a l) y por extensión (*a, *b, 1a, 1a.2a, 2a, 2b, 3a, 3b, 4a, 4b, 6a, 6b, 8a). Las pantallas están en `test_faltantes_vistas.py`; el flujo de punta a punta, en
# `test_recorrido_faltantes.py`; los choques de concurrencia, abajo (`ComDcdFltConcurrenciaTests`).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de dar por buena la implementación):
#   - `datos_de_decision(enlace=None, *, vendedor=None, venta_id=None) -> DatosDeDecision(venta, enlace, vence, modalidad, destino, pendientes, otros, monto_actual, contacto)`; cada
#     pendiente es `FilaPendiente(detalle_id, variedad, solicitada, disponible, precio, subtotal_disponible, solo_rechazar)`. Con un enlace que no sirve: `ValidationError` `enlace_no_sirve`.
#   - `resumen_de_decision(datos, decisiones) -> ResumenDeDecision(filas, monto_total, queda_cancelada)`; `decisiones = {detalle_id: "aceptar" | "rechazar"}`.
#   - `registrar_decision(enlace_id, decisiones, disponibles_vistos, *, vendedor=None, venta_id=None) -> ResultadoDecision(venta, confirmados, rechazados, partidas, movimientos,
#     cosechas_canceladas, enlace)`. Errores por campo `decision_<id>`: `faltan_decisiones`, `decision_invalida`, `solo_rechazar`; en `__all__`: `enlace_no_sirve` (con `params["motivo"]`),
#     `detalle_ya_no_pendiente`, `disponible_cambio` (con las cantidades nuevas), `venta_no_decidible`, `cambio_simultaneo`. `PermissionDenied` si en 1a no es el Vendedor activo del contrato.
#   - `ventas_para_decidir(vendedor) -> [SimpleNamespace(venta, cliente, pendientes, desde)]` y `puede_decidir_el_vendedor(venta, hoy=None) -> bool`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase, override_settings, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleVenta, EnlaceCliente, ReservaStock
from comercial.servicios import camara, faltantes, merma_camara
from comercial.servicios.merma_camara import DatosDeMermaEnCamara
from comercial.tests.fabricas import (
    cliente,
    compra_venta,
    cosecha_manual,
    detalle,
    enlace as un_enlace,
    escenario_comercial,
    partida,
    reserva,
    verificar_invariantes_de_reservas,
)
from core.models import ROL_CLIENTE_ENLACE, Notificacion, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_variedad
from produccion.models import Bitacora, Cosecha, Lote, MovimientoStock, StockCosechado
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar

HOY = timezone.localdate()
ACEPTAR, RECHAZAR = "aceptar", "rechazar"


def codigos(error):
    """Los códigos de un `ValidationError` con `error_dict`."""
    return [e.code for errores in error.error_dict.values() for e in errores]


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, su Agrónomo y su Capataz, un lote de 300 y una venta con retiro... con envío, «pendiente de decisión del cliente» (50 pedidos, 30 cubiertos por
    una partida de cámara) y su enlace vigente."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.venta, self.detalle, self.enlace, self.token = self.nueva(cubierto=30)

    def nueva(self, cubierto=30, solicitada=50, cliente_=None, con_enlace=True):
        """Una venta «pendiente de decisión» con un detalle pendiente de `solicitada` (a $10), cubierto con una partida de cámara de `cubierto`. Devuelve `(venta, detalle, enlace, token)`."""
        venta = compra_venta(self.e, estado="pendiente_decision", cliente_=cliente_)
        d = detalle(venta, self.e.variedad, solicitada, precio="10.00", estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=d.pk).update(fecha_pendiente_decision=HOY)
        if cubierto:
            reserva(d, [(partida(self.lote, cubierto), cubierto)])
        enlace, token = un_enlace(venta, cliente_=cliente_) if con_enlace and (cliente_ is None or cliente_.email_cliente) else (None, None)
        return venta, d, enlace, token

    def decidir(self, decision=ACEPTAR, *, d=None, enlace=None, vistos=None, extra=None):
        """El cliente decide por su enlace."""
        d = d or self.detalle
        decisiones = {d.pk: decision, **(extra or {})}
        return faltantes.registrar_decision((enlace or self.enlace).pk, decisiones, vistos if vistos is not None else {d.pk: 30})

    def con_cosecha_concretada(self, d, reservada=20, cosechada=15, costo="2.5000", dias_atras=2):
        """Una reserva de `d` con una cosecha ya concretada (hace `dias_atras` días) que cosechó `cosechada` de las `reservada` del lote y su salida por cosecha."""
        r = reserva(d, [(self.lote, reservada)])
        Bitacora.objects.create(  # invariante de COM-04a: toda cosecha concretada tiene su registro de bitácora por lote
            invernadero=self.e.invernadero, lote=self.lote, etapa=self.lote.etapa, tipo_evento="cosecha", cosecha=r.cosecha,
            fecha_bitacora=HOY, hora_bitacora=timezone.localtime().time(),
        )
        Cosecha.objects.filter(pk=r.cosecha_id).update(estado_orden="concretada", fecha_resolucion_orden=HOY, fecha_cosecha=HOY - timedelta(days=dias_atras))
        DetalleReserva.objects.filter(reserva=r).update(cantidad_cosechada=cosechada)
        ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="lista_para_entrega")
        MovimientoStock.objects.create(origen_id=r.cosecha_id, lote=self.lote, tipo_movimiento="salida_por_cosecha", cantidad=cosechada, costo_unitario=Decimal(costo))
        return r


class ComDcdFltServicioTests(Base):
    # ---- flujo principal y postcondiciones ----

    def test_flujo_principal_el_cliente_acepta_la_cantidad_disponible(self):
        """Pasos 1 a 9: el cliente abre el enlace, ve la cantidad disponible, acepta y el detalle queda «confirmado» con esa cantidad; la venta vuelve a «abierta»."""
        datos = faltantes.datos_de_decision(self.enlace)
        self.assertEqual([(f.solicitada, f.disponible, f.solo_rechazar) for f in datos.pendientes], [(50, 30, False)])
        resumen = faltantes.resumen_de_decision(datos, {self.detalle.pk: ACEPTAR})
        self.assertEqual((resumen.monto_total, resumen.queda_cancelada), (Decimal("300.00"), False))
        resultado = self.decidir()
        self.detalle.refresh_from_db()
        self.venta.refresh_from_db()
        self.assertEqual((self.detalle.estado_detalle_venta, self.detalle.cant_entregada_venta, self.venta.estado_venta), ("confirmado", 30, "abierta"))
        self.assertEqual([d.pk for d in resultado.confirmados], [self.detalle.pk])

    def test_post_a_todos_los_detalles_pendientes_quedan_decididos_3b(self):
        """Postcondición a y extensión 3b: con dos detalles pendientes se decide cada uno en un solo envío: uno «confirmado» y el otro «rechazado»."""
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        segundo = detalle(self.venta, otra, 20, precio="5.00", estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=segundo.pk).update(fecha_pendiente_decision=HOY)
        self.decidir(vistos={self.detalle.pk: 30, segundo.pk: 0}, extra={segundo.pk: RECHAZAR})
        self.detalle.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual((self.detalle.estado_detalle_venta, segundo.estado_detalle_venta), ("confirmado", "rechazado"))
        self.assertFalse(DetalleVenta.objects.filter(compra_venta=self.venta, estado_detalle_venta="pendiente_decision").exists())

    def test_post_b_el_enlace_queda_usado_y_no_admite_otro_envio(self):
        """Postcondición b y garantía mínima 2: el enlace pasa a `usado` con su fecha de uso; un segundo envío es `enlace_no_sirve` (motivo `usado`) y no cambia nada."""
        self.decidir()
        self.enlace.refresh_from_db()
        self.assertEqual(self.enlace.estado, "usado")
        self.assertIsNotNone(self.enlace.fecha_uso)
        with self.assertRaises(ValidationError) as error:
            self.decidir()
        self.assertEqual(codigos(error.exception), ["enlace_no_sirve"])
        self.assertEqual(error.exception.error_dict["__all__"][0].params["motivo"], "usado")

    def test_post_c_la_venta_pasa_a_abierta_si_queda_un_detalle_no_rechazado_y_a_cancelada_si_no(self):
        """Postcondición c: «abierta» con al menos un detalle no rechazado; «cancelada» si todos quedaron rechazados (sin los datos de MD-130)."""
        venta, d, enlace, _ = self.nueva()
        resultado = faltantes.registrar_decision(enlace.pk, {d.pk: RECHAZAR}, {d.pk: 30})
        venta.refresh_from_db()
        self.assertEqual(venta.estado_venta, "cancelada")
        self.assertEqual(resultado.venta.estado_venta, "cancelada")

    def test_post_d_se_notifica_al_vendedor_la_decision_de_cada_detalle(self):
        """Postcondición d: una notificación al Vendedor del contrato con la decisión de cada detalle."""
        self.decidir()
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor)
        self.assertEqual(aviso.titulo, f"El cliente decidió el faltante de {self.venta.codigo}")
        self.assertIn(str(self.e.variedad), aviso.detalle)
        self.assertIn("aceptó 30 plantas", aviso.detalle)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_e_el_acuse_al_cliente_sale_despues_de_confirmar_con_la_decision_y_el_monto(self):
        """Postcondición e y 8a: el acuse (decisión de cada detalle, cantidad, subtotal y monto total) se envía con `on_commit`, nunca antes."""
        with mock.patch("core.correo.enviar_correo", return_value=True) as envio:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.decidir()
            self.assertEqual(envio.call_count, 0)
            for callback in callbacks:  # recién ahora salen los correos, con el parche todavía activo
                callback()
        destinatario, asunto, plantilla, contexto = envio.call_args.args
        self.assertEqual((destinatario.email, plantilla), (self.venta.cliente.email_cliente, "comercial/correos/acuse_faltante.txt"))
        self.assertEqual((contexto["filas"][0]["cantidad"], contexto["filas"][0]["subtotal"], contexto["total"]), (30, Decimal("300.00"), Decimal("300.00")))

    def test_post_f_un_registro_de_auditoria_con_origen_cliente_mediante_enlace(self):
        """Postcondición f y D-65 punto 8: UN registro `decision_faltante`, sin usuario y con el rol «cliente_enlace»; la venta, el cliente y el enlace en `afectados`."""
        self.decidir()
        registro = RegistroAuditoria.objects.get(accion="decision_faltante")
        self.assertEqual((registro.usuario, registro.rol), (None, ROL_CLIENTE_ENLACE))
        modelos = {a["modelo"] for a in registro.afectados}
        self.assertTrue({"comercial.compraventa", "comercial.cliente", "comercial.enlacecliente", "comercial.detalleventa"} <= modelos)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="decision_faltante").count(), 1)

    def test_post_g_h_lo_aceptado_queda_confirmado_con_la_disponible_y_sus_reservas_no_cambian(self):
        """Postcondiciones g y h: «confirmado» con `cant_entregada_venta` = la disponible; sus reservas no cambian y el detalle ya no tiene cantidad sin cubrir."""
        antes = list(DetalleReserva.objects.filter(reserva__detalle_venta=self.detalle).values_list("cantidad_reservada", "reserva__estado_reserva"))
        self.decidir()
        despues = list(DetalleReserva.objects.filter(reserva__detalle_venta=self.detalle).values_list("cantidad_reservada", "reserva__estado_reserva"))
        self.assertEqual(antes, despues)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cant_solicitada_venta, 50)  # la solicitada no se modifica (regla 20 de 8.6)

    def test_post_i_lo_rechazado_queda_rechazado_y_sus_reservas_pasan_a_liberada(self):
        """Postcondición i: el detalle «rechazado» y sus reservas no liberadas, «liberada»."""
        self.decidir(RECHAZAR)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "rechazado")
        self.assertEqual(set(ReservaStock.objects.filter(detalle_venta=self.detalle).values_list("estado_reserva", flat=True)), {"liberada"})

    def test_post_j_la_cosecha_a_realizar_se_cancela_y_se_avisa_al_capataz_y_al_agronomo(self):
        """Postcondición j: la cosecha «a realizar» de las reservas rechazadas pasa a «cancelada» con la fecha de hoy; aviso al Capataz y al Agrónomo del invernadero."""
        venta, d, enlace, _ = self.nueva(cubierto=0)
        r = reserva(d, [(self.lote, 20)])
        faltantes.registrar_decision(enlace.pk, {d.pk: RECHAZAR}, {d.pk: 20})
        cosecha = Cosecha.objects.get(pk=r.cosecha_id)
        self.assertEqual((cosecha.estado_orden, cosecha.fecha_resolucion_orden), ("cancelada", HOY))
        self.assertIn(venta.codigo, cosecha.motivo_cancelacion)
        titulo = f"Orden {cosecha.codigo} cancelada"
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.capataz, titulo=titulo).exists())
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.agronomo, titulo=titulo).exists())
        self.assertEqual(ReservaStock.objects.get(pk=r.pk).estado_reserva, "liberada")

    def test_post_k_cada_linea_ya_cosechada_vuelve_a_la_camara_como_partida_de_rechazo(self):
        """Postcondición k: una partida «disponible» por línea cosechada, motivo `rechazo_cantidad_reducida`, cantidad = min(cosechada, reservada), costo de la salida por cosecha,
        ingreso hoy y fecha límite = la de la cosecha + la postcosecha de la variedad; con su movimiento `ingreso_a_camara` originado en la compra-venta."""
        venta, d, enlace, _ = self.nueva(cubierto=0)
        self.con_cosecha_concretada(d, reservada=20, cosechada=15, costo="2.5000", dias_atras=2)
        resultado = faltantes.registrar_decision(enlace.pk, {d.pk: RECHAZAR}, {d.pk: 15})
        (nueva,) = resultado.partidas
        self.assertEqual(
            (nueva.estado_stock_cosechado, nueva.motivo_cosechado, nueva.cantidad_ingreso_cosechado, nueva.cantidad_disponible_cosechado, nueva.costo_unitario_cosechado, nueva.fecha_ingreso),
            ("disponible", "rechazo_cantidad_reducida", 15, 15, Decimal("2.5000"), HOY),
        )
        postcosecha = self.lote.siembra.variedad.duracion_post_cosecha
        self.assertEqual(nueva.fecha_limite, HOY - timedelta(days=2) + timedelta(days=postcosecha))  # no se reinicia la vida útil (regla 29 de 8.6)
        movimiento = MovimientoStock.objects.get(partida=nueva)
        self.assertEqual((movimiento.tipo_movimiento, movimiento.origen_id, movimiento.cantidad), ("ingreso_a_camara", venta.pk, 15))
        self.assertEqual([m.pk for m in resultado.movimientos], [movimiento.pk])

    def test_post_k_un_rechazo_con_la_cosecha_a_realizar_no_crea_partidas(self):
        """Lo que no se cosechó no vuelve a la cámara: se cancela la cosecha y no hay partida."""
        venta, d, enlace, _ = self.nueva(cubierto=0)
        reserva(d, [(self.lote, 20)])
        antes = StockCosechado.objects.count()
        resultado = faltantes.registrar_decision(enlace.pk, {d.pk: RECHAZAR}, {d.pk: 20})
        self.assertEqual((resultado.partidas, StockCosechado.objects.count()), ([], antes))

    def test_post_l_se_programa_la_asignacion_de_camara_despues_de_confirmar(self):
        """Postcondición l: lo que ingresó a la cámara y las líneas de cámara liberadas disparan PROD-ASG-CAM con `on_commit` (con las partidas de las dos)."""
        venta, d, enlace, _ = self.nueva(cubierto=0)
        self.con_cosecha_concretada(d, reservada=20, cosechada=15)
        reserva(d, [(propia := partida(self.lote, 5), 5)])
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar, self.captureOnCommitCallbacks(execute=True):
            resultado = faltantes.registrar_decision(enlace.pk, {d.pk: RECHAZAR}, {d.pk: 20})
        ids = sorted([resultado.partidas[0].pk, propia.pk])
        asignar.assert_called_once_with(ids)

    # ---- extensiones ----

    def test_ext_asterisco_a_abandonar_antes_de_confirmar_no_registra_nada(self):
        """Extensión *a: ver los datos y el resumen no escribe nada: el enlace sigue vigente y nada cambia."""
        auditoria = RegistroAuditoria.objects.count()
        datos = faltantes.datos_de_decision(self.enlace)
        faltantes.resumen_de_decision(datos, {self.detalle.pk: RECHAZAR})
        self.enlace.refresh_from_db()
        self.detalle.refresh_from_db()
        self.assertEqual((self.enlace.estado, self.detalle.estado_detalle_venta, RegistroAuditoria.objects.count()), ("vigente", "pendiente_decision", auditoria))

    def test_ext_asterisco_b_si_el_registro_falla_se_revierte_todo(self):
        """Extensión *b y garantías mínimas: si algo falla a mitad, no queda ningún cambio, ni aviso ni auditoría parcial; el enlace puede volver a usarse."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.decidir(RECHAZAR)
        self.enlace.refresh_from_db()
        self.detalle.refresh_from_db()
        self.assertEqual((self.enlace.estado, self.detalle.estado_detalle_venta), ("vigente", "pendiente_decision"))
        self.assertEqual(set(ReservaStock.objects.filter(detalle_venta=self.detalle).values_list("estado_reserva", flat=True)), {"lista_para_entrega"})
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_ext_1a_el_vendedor_decide_por_el_cliente_sin_correo(self):
        """Extensión 1a: el cliente sin correo no tiene enlace; el Vendedor decide: sin verificar ni marcar el enlace, sin notificarse a sí mismo, con su usuario en la auditoría y sin acuse."""
        sin_correo = cliente(email="")
        venta, d, _, _ = self.nueva(cliente_=sin_correo, con_enlace=False)
        with self.captureOnCommitCallbacks(execute=True), mock.patch("core.correo.enviar_correo") as envio:
            faltantes.registrar_decision(None, {d.pk: ACEPTAR}, {d.pk: 30}, vendedor=self.e.vendedor, venta_id=venta.pk)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "confirmado")
        # COM-05a1: la venta que queda «abierta» y lista programa su entrega y el Vendedor recibe su aviso de planificación; lo que no debe haber es un aviso de falta de correo ni un correo al cliente.
        titulos = list(Notificacion.objects.filter(destinatario=self.e.vendedor).values_list("titulo", flat=True))
        self.assertEqual(envio.call_count, 0)
        self.assertTrue(all(t.startswith(("Entrega sin transportista", "Retiro planificado")) for t in titulos), titulos)
        registro = RegistroAuditoria.objects.get(accion="decision_faltante")
        self.assertEqual((registro.usuario_id, registro.rol), (self.e.vendedor.pk, "vendedor"))

    def test_ext_1a_con_el_enlace_vencido_el_vendedor_decide_y_el_enlace_vencido_se_anula(self):
        """Extensión 1a (el enlace venció sin respuesta): el Vendedor decide y el enlace que quedaba vigente pasa a `anulado`; el acuse sale porque el cliente tiene correo."""
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(fecha_vencimiento=HOY - timedelta(days=1))
        self.assertTrue(faltantes.puede_decidir_el_vendedor(self.venta))
        faltantes.registrar_decision(None, {self.detalle.pk: ACEPTAR}, {self.detalle.pk: 30}, vendedor=self.e.vendedor, venta_id=self.venta.pk)
        self.enlace.refresh_from_db()
        self.assertEqual(self.enlace.estado, "anulado")

    def test_ext_1a_con_el_correo_sin_enviar_el_vendedor_tambien_puede(self):
        """D-65 punto 6: un enlace `pendiente_envio` (el correo no salió) habilita al Vendedor aunque el plazo siga corriendo."""
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(estado_envio="pendiente_envio")
        self.assertTrue(faltantes.puede_decidir_el_vendedor(self.venta))

    def test_ext_1a_si_el_cliente_todavia_puede_decidir_el_vendedor_no_puede(self):
        """Regla «Quién decide»: con correo y un enlace que sirve, decide el cliente; el Vendedor recibe `venta_no_decidible` y no cambia nada."""
        with self.assertRaises(ValidationError) as error:
            faltantes.registrar_decision(None, {self.detalle.pk: ACEPTAR}, {self.detalle.pk: 30}, vendedor=self.e.vendedor, venta_id=self.venta.pk)
        self.assertEqual(codigos(error.exception), ["venta_no_decidible"])
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "pendiente_decision")

    def test_ext_1a_el_gerente_no_registra_la_decision(self):
        """Regla «Quién decide»: solo el Vendedor del contrato (el Gerente ve la venta, no el botón): `PermissionDenied`; tampoco el de otro contrato."""
        sin_correo = cliente(email="")
        venta, d, _, _ = self.nueva(cliente_=sin_correo, con_enlace=False)
        gerente = crear_gerente()
        with self.assertRaises(PermissionDenied):
            faltantes.registrar_decision(None, {d.pk: ACEPTAR}, {d.pk: 30}, vendedor=gerente, venta_id=venta.pk)
        with self.assertRaises(PermissionDenied):
            faltantes.ventas_para_decidir(gerente)

    def test_ext_1a_2_las_ventas_que_el_vendedor_puede_decidir_y_1a_2a_sin_ninguna(self):
        """Extensiones 1a.2 y 1a.2a: la lista trae las ventas del Vendedor sin correo o con el enlace vencido (con el cliente, lo pendiente y desde cuándo); con enlace vigente, vacía."""
        self.assertEqual(faltantes.ventas_para_decidir(self.e.vendedor), [])  # 1a.2a: el enlace del cliente sirve
        sin_correo = cliente(email="", telefono="1144445555")
        venta, _, _, _ = self.nueva(cliente_=sin_correo, con_enlace=False)
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(fecha_vencimiento=HOY - timedelta(days=1))
        filas = faltantes.ventas_para_decidir(self.e.vendedor)
        self.assertEqual(sorted(f.venta.pk for f in filas), sorted([venta.pk, self.venta.pk]))
        propia = next(f for f in filas if f.venta.pk == venta.pk)
        self.assertEqual((propia.cliente.telefono_cliente, propia.desde, len(propia.pendientes)), ("1144445555", HOY, 1))

    def test_ext_2a_el_enlace_que_no_sirve_da_el_motivo(self):
        """Extensión 2a: usado, vencido, reemplazado, anulado, venta cancelada o sin detalles pendientes: `enlace_no_sirve` con el motivo y el contacto del Vendedor disponible."""
        for estado, motivo in (("usado", "usado"), ("vencido", "vencido"), ("reemplazado", "reemplazado"), ("anulado", "anulado")):
            with self.subTest(estado=estado):
                venta, d, enlace, _ = self.nueva()
                EnlaceCliente.objects.filter(pk=enlace.pk).update(estado=estado, fecha_uso=timezone.now() if estado == "usado" else None)
                enlace.refresh_from_db()
                with self.assertRaises(ValidationError) as error:
                    faltantes.datos_de_decision(enlace)
                self.assertEqual(error.exception.error_dict["__all__"][0].params["motivo"], motivo)
        contacto = faltantes.contacto_del_vendedor(self.venta.pk)
        self.assertEqual(contacto.email, self.e.vendedor.email)

    def test_ext_2a_con_la_venta_cancelada_o_sin_pendientes_el_enlace_no_sirve(self):
        """Extensión 2a: la venta cancelada y la venta sin detalles pendientes."""
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="cancelada")
        with self.assertRaises(ValidationError) as error:
            faltantes.datos_de_decision(self.enlace)
        self.assertEqual(error.exception.error_dict["__all__"][0].params["motivo"], "venta_cancelada")
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="pendiente_decision")
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="abierto")
        with self.assertRaises(ValidationError) as error:
            faltantes.datos_de_decision(self.enlace)
        self.assertEqual(error.exception.error_dict["__all__"][0].params["motivo"], "sin_pendientes")

    def test_ext_2b_con_disponible_cero_solo_se_puede_rechazar(self):
        """Extensión 2b: la fila lo marca (`solo_rechazar`) y aceptar da `solo_rechazar` por campo; rechazar funciona."""
        venta, d, enlace, _ = self.nueva(cubierto=0)
        datos = faltantes.datos_de_decision(enlace)
        self.assertEqual([(f.disponible, f.solo_rechazar) for f in datos.pendientes], [(0, True)])
        with self.assertRaises(ValidationError) as error:
            faltantes.registrar_decision(enlace.pk, {d.pk: ACEPTAR}, {d.pk: 0})
        self.assertEqual(codigos(error.exception), ["solo_rechazar"])
        faltantes.registrar_decision(enlace.pk, {d.pk: RECHAZAR}, {d.pk: 0})
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "rechazado")

    def test_ext_3a_el_resumen_de_un_rechazo_dice_que_la_compra_queda_cancelada(self):
        """Extensión 3a: el resumen de rechazar todo muestra $ 0 y que la compra quedará cancelada; con otro detalle abierto, no."""
        resumen = faltantes.resumen_de_decision(faltantes.datos_de_decision(self.enlace), {self.detalle.pk: RECHAZAR})
        self.assertEqual((resumen.queda_cancelada, resumen.monto_total), (True, Decimal("0.00")))
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        detalle(self.venta, otra, 10, precio="5.00", estado="abierto")
        resumen = faltantes.resumen_de_decision(faltantes.datos_de_decision(self.enlace), {self.detalle.pk: RECHAZAR})
        self.assertEqual((resumen.queda_cancelada, resumen.monto_total), (False, Decimal("50.00")))

    def test_ext_3b_el_resumen_de_varios_detalles_suma_los_aceptados_y_los_no_pendientes(self):
        """Extensión 3b: el monto total nuevo suma lo aceptado (con la disponible) y lo no pendiente (con lo solicitado o lo entregado)."""
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        detalle(self.venta, otra, 10, precio="5.00", estado="abierto")
        resumen = faltantes.resumen_de_decision(faltantes.datos_de_decision(self.enlace), {self.detalle.pk: ACEPTAR})
        self.assertEqual(resumen.monto_total, Decimal("350.00"))  # 30 × 10 + 10 × 5
        self.assertEqual([(f["variedad"], f["cantidad"]) for f in resumen.filas], [(str(self.e.variedad), 30)])

    def test_ext_4a_faltan_decisiones_de_algun_detalle(self):
        """Extensión 4a: sin elegir en algún detalle, `faltan_decisiones` por campo, tanto en el resumen como al registrar."""
        with self.assertRaises(ValidationError) as error:
            faltantes.resumen_de_decision(faltantes.datos_de_decision(self.enlace), {})
        self.assertEqual(list(error.exception.error_dict), [f"decision_{self.detalle.pk}"])
        self.assertEqual(codigos(error.exception), ["faltan_decisiones"])
        with self.assertRaises(ValidationError) as error:
            faltantes.registrar_decision(self.enlace.pk, {}, {})
        self.assertEqual(codigos(error.exception), ["faltan_decisiones"])
        with self.assertRaises(ValidationError) as error:
            self.decidir("quizas")
        self.assertEqual(codigos(error.exception), ["decision_invalida"])

    def test_ext_4b_cambiar_la_decision_antes_de_confirmar_no_guarda_nada(self):
        """Extensión 4b: se puede pedir el resumen de una decisión y después el de otra; recién registrar escribe, y con la última elegida."""
        datos = faltantes.datos_de_decision(self.enlace)
        primero = faltantes.resumen_de_decision(datos, {self.detalle.pk: RECHAZAR})
        segundo = faltantes.resumen_de_decision(datos, {self.detalle.pk: ACEPTAR})
        self.assertEqual((primero.queda_cancelada, segundo.queda_cancelada), (True, False))
        self.decidir(ACEPTAR)
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "confirmado")

    def test_ext_6a_el_enlace_dejo_de_servir_al_registrar(self):
        """Extensión 6a: el enlace venció o lo reemplazó uno más nuevo mientras el cliente decidía: no registra nada y dice por qué."""
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(fecha_vencimiento=HOY - timedelta(days=1))
        with self.assertRaises(ValidationError) as error:
            self.decidir()
        self.assertEqual((codigos(error.exception), error.exception.error_dict["__all__"][0].params["motivo"]), (["enlace_no_sirve"], "vencido"))
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "pendiente_decision")

    def test_ext_6a_un_detalle_ya_no_esta_pendiente(self):
        """Extensión 6a: la cámara cubrió un detalle (pasó a «abierto») mientras el cliente decidía y la venta sigue con otro pendiente: `detalle_ya_no_pendiente` con cuál."""
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        segundo = detalle(self.venta, otra, 10, estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=segundo.pk).update(fecha_pendiente_decision=HOY)
        DetalleVenta.objects.filter(pk=segundo.pk).update(estado_detalle_venta="abierto")
        with self.assertRaises(ValidationError) as error:
            self.decidir(extra={segundo.pk: RECHAZAR}, vistos={self.detalle.pk: 30, segundo.pk: 0})
        self.assertEqual(codigos(error.exception), ["detalle_ya_no_pendiente"])
        self.assertEqual(error.exception.error_dict["__all__"][0].params["detalles"], [segundo.pk])

    def test_ext_6b_la_cantidad_disponible_cambio_al_registrar(self):
        """Extensión 6b: una merma en cámara bajó lo cubierto de 30 a 20 mientras el cliente miraba: no registra y trae la cantidad nueva; después puede volver a decidir."""
        DetalleReserva.objects.filter(reserva__detalle_venta=self.detalle).update(cantidad_reservada=20)
        with self.assertRaises(ValidationError) as error:
            self.decidir()
        self.assertEqual(codigos(error.exception), ["disponible_cambio"])
        self.assertEqual(error.exception.error_dict["__all__"][0].params["disponibles"], {self.detalle.pk: 20})
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "pendiente_decision")
        self.decidir(vistos={self.detalle.pk: 20})
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.cant_entregada_venta, 20)

    def test_ext_8a_si_el_acuse_falla_la_decision_sigue_registrada(self):
        """Extensión 8a: un acuse que no sale no revierte nada (no hay cola: queda en el log)."""
        with override_settings(CORREO_CONFIGURADO=True), mock.patch("core.correo.enviar_correo", return_value=False), self.captureOnCommitCallbacks(execute=True):
            self.decidir()
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "confirmado")

    def test_regla_el_cliente_dado_de_baja_decide_igual(self):
        """Regla 2 de 8.18: su venta sigue su curso y puede decidir."""
        from comercial.models import Cliente

        Cliente.objects.filter(pk=self.venta.cliente_id).update(estado_cliente="inactivo")
        self.decidir()
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.estado_detalle_venta, "confirmado")

    def test_regla_el_vendedor_es_el_actual_del_contrato(self):
        """D-60: si el contrato pasó a otro Vendedor, decide (y recibe el aviso) el actual; el anterior recibe `PermissionDenied`."""
        from maestros.tests.fabricas import crear_vendedor

        nuevo = crear_vendedor(email="nuevo.vendedor@infoponia.com")
        sin_correo = cliente(email="")
        venta, d, _, _ = self.nueva(cliente_=sin_correo, con_enlace=False)
        CompraVenta.objects.filter(pk=venta.pk).update(vendedor=nuevo)
        with self.assertRaises(PermissionDenied):
            faltantes.registrar_decision(None, {d.pk: ACEPTAR}, {d.pk: 30}, vendedor=self.e.vendedor, venta_id=venta.pk)
        faltantes.registrar_decision(None, {d.pk: ACEPTAR}, {d.pk: 30}, vendedor=nuevo, venta_id=venta.pk)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "confirmado")

    def test_regla_el_cliente_no_ve_lotes_partidas_invernaderos_ni_costos(self):
        """Garantía mínima 4: los datos del paso 2 no traen nada de dónde sale el producto ni cuánto cuesta."""
        datos = faltantes.datos_de_decision(self.enlace)
        texto = repr(datos)
        for prohibido in (self.lote.codigo, self.e.invernadero.nombre_invernadero, "costo"):
            self.assertNotIn(prohibido, texto)


# ---- concurrencia ----


@tag("concurrencia")
class ComDcdFltConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Dos hilos, dos conexiones, el orden fijado con `primera`. La decisión bloquea (cuentas → invernaderos → variedades → lotes y partidas → venta y detalles → cosechas → reservas → enlace)
    en el mismo orden que PROD-ASG-CAM, la merma en cámara y la cancelación de una cosecha, así que la segunda espera a la primera y ve lo que confirmó."""

    def armar(self, cubierto=30):
        """Un invernadero sin geografía, una partida de cámara y una venta con retiro «pendiente de decisión» que la usa, con su enlace."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 100)
        self.venta = compra_venta(self.e, modalidad="retiro", retiro=self.e.invernadero, estado="pendiente_decision")
        self.detalle = detalle(self.venta, self.e.variedad, 50, precio="10.00", estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(fecha_pendiente_decision=HOY)
        self.partida = partida(self.lote, 40) if cubierto else None
        if cubierto:
            reserva(self.detalle, [(self.partida, cubierto)])
        Lote.objects.filter(pk=self.lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)  # sin stock en pie: lo recortado no se vuelve a cubrir
        self.enlace, _ = un_enlace(self.venta)
        self.addCleanup(verificar_invariantes_de_reservas)

    def decidir(self, decision=ACEPTAR, vistos=30):
        return lambda: faltantes.registrar_decision(self.enlace.pk, {self.detalle.pk: decision}, {self.detalle.pk: vistos})

    def test_regla_dos_envios_del_mismo_enlace_registran_uno_solo(self):
        """D-65 punto 4 y garantía mínima 2: dos pestañas envían a la vez; la segunda espera el enlace, lo ve `usado` y no registra nada."""
        self.armar()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.decidir(), self.decidir(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("enlace_no_sirve", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="decision_faltante").count(), 1)
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).cant_entregada_venta, 30)

    def test_regla_la_decision_contra_la_asignacion_de_camara_que_cubre_el_mismo_detalle(self):
        """Requisito especial (concurrencia): con PROD-ASG-CAM primero, el detalle queda cubierto («abierto», su enlace `anulado`) y la decisión recibe `enlace_no_sirve`."""
        self.armar(30)
        otra = partida(self.lote, 20)
        exitos, rechazos, otros = separar(
            correr_a_la_vez(lambda: camara.asignar_camara([otra.pk], HOY), self.decidir(), primera="a")
        )
        self.assertEqual((len(rechazos), otros), (1, []))
        self.assertIn("enlace_no_sirve", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "abierto")
        self.assertEqual(EnlaceCliente.objects.get(pk=self.enlace.pk).estado, "anulado")

    def test_regla_la_decision_primero_y_la_asignacion_de_camara_no_toca_lo_confirmado(self):
        """Con la decisión primero, el detalle queda «confirmado» (sin cantidad sin cubrir): la asignación que llega después no le reserva más."""
        self.armar(30)
        otra = partida(self.lote, 20)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.decidir(), lambda: camara.asignar_camara([otra.pk], HOY), primera="a"))
        self.assertEqual((len(rechazos), otros), (0, []))
        detalle_ = DetalleVenta.objects.get(pk=self.detalle.pk)
        self.assertEqual((detalle_.estado_detalle_venta, detalle_.cant_entregada_venta), ("confirmado", 30))
        self.assertEqual(sum(DetalleReserva.objects.filter(reserva__detalle_venta=self.detalle).values_list("cantidad_reservada", flat=True)), 30)

    def test_regla_la_decision_contra_una_merma_en_camara_sobre_las_mismas_reservas(self):
        """Merma en cámara contra la decisión del cliente: con la decisión primero (acepta 30), la merma de 35 recorta lo confirmado y el detalle vuelve a «pendiente» sin cantidad
        aceptada (D-64 punto 13); con la merma primero, el camino de faltante reemplaza el enlace y la decisión recibe `enlace_no_sirve`."""
        self.armar(30)
        merma = lambda: merma_camara.registrar_merma_en_camara(self.e.agronomo, DatosDeMermaEnCamara(self.partida.pk, 35, "dano_en_camara"))
        exitos, rechazos, otros = separar(correr_a_la_vez(self.decidir(), merma, primera="a"))
        self.assertEqual((len(rechazos), otros), (0, []))
        detalle_ = DetalleVenta.objects.get(pk=self.detalle.pk)
        self.assertEqual((detalle_.estado_detalle_venta, detalle_.cant_entregada_venta), ("pendiente_decision", None))

    def test_regla_la_merma_en_camara_primero_y_la_decision_recibe_el_enlace_reemplazado(self):
        """El orden inverso del anterior: la merma gana, el camino de faltante deja un enlace nuevo y el viejo queda `reemplazado`."""
        self.armar(30)
        merma = lambda: merma_camara.registrar_merma_en_camara(self.e.agronomo, DatosDeMermaEnCamara(self.partida.pk, 35, "dano_en_camara"))
        exitos, rechazos, otros = separar(correr_a_la_vez(merma, self.decidir(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("enlace_no_sirve", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(EnlaceCliente.objects.get(pk=self.enlace.pk).estado, "reemplazado")


class PlanificacionDeLaEntregaTests(Base):
    """COM-05a1: el paso 7 y la postcondición m de COM-DCD-FLT (planificar la entrega de la venta que queda «abierta» y lista), con `on_commit`."""

    def test_ext_7_la_venta_que_queda_abierta_y_lista_programa_su_entrega_despues_de_confirmar(self):
        """Paso 7: la decisión que deja la venta «abierta» con todas sus reservas «lista para entrega» (la cámara que la cubría) dispara COM-PNF-ENT después de confirmar."""
        from comercial.models import Entrega

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.decidir()
            self.assertEqual(Entrega.objects.count(), 0)
        for callback in callbacks:
            callback()
        entrega = Entrega.objects.get()
        self.assertEqual(entrega.contrato_entrega_id, self.venta.pk)
