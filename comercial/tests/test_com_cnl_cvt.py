# Pruebas de COM-CNL-CVT · Cancelar Compra-venta (COM-05b): `ComCnlCvtServicioTests` (las reglas, las postcondiciones a a i y las extensiones 1a, 4a, 6a, 6b, 8a, 8b y 9a de `datos_de_cancelacion`,
# `resumen_de_cancelacion_de_venta` y `cancelar_compra_venta`, con la cancelación de las cosechas y las entregas de PROD-CNL-ORD) y, abajo, `ComCnlCvtVistaTests`. Cada prueba verifica al final los
# invariantes de las reservas y de las entregas. Fuente: docs/casos_de_uso/comercial/compra_venta.md («COM-CNL-CVT», «Cómo se aplica en la ronda «Comercial 1»: COM-CNL-CVT»),
# docs/casos_de_uso/produccion/cancelar_orden.md («la compra-venta cancelada»), D-65, D-66 y D-67 (puntos 3 y 4).

import re
from datetime import timedelta
from decimal import Decimal
from html import unescape
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta, DetalleEntrega, DetalleVenta, Entrega, EnlaceCliente, PagoCliente, ReservaStock
from comercial.servicios import compra_ventas, concrecion, cosechas, entregas
from comercial.servicios.cosechas import DatosDeConcrecion
from comercial.servicios.compra_ventas import DatosDeCancelacionDeVenta, texto_de_pesos
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    escenario_comercial,
    iniciar_ruta_de,
    marcar_concretada,
    reserva_lista,
    segundo_invernadero,
    transportista_con_vehiculo,
    vehiculo_en_ruta,
    venta_con_todo,
    verificar_invariantes_de_cobros,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core import correo
from core.models import Notificacion, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from produccion.models import Cosecha, MovimientoStock, ReservaInsumo, StockCosechado
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

HOY = timezone.localdate()
MOTIVO = "Se canceló la compra-venta {codigo}: el cliente desistió."


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, su Agrónomo, su Capataz y un transportista de 800 kg, y un Gerente."""

    def setUp(self):
        self.e = escenario_comercial()
        self.gerente = crear_gerente()
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def todo(self, **opciones):
        """Una venta con todo (`venta_con_todo`) con su entrega asignada al transportista."""
        opciones.setdefault("transportista", self.t)
        return venta_con_todo(self.e, **opciones)

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta).order_by("pk"))

    def titulos(self, cuenta):
        return [a.titulo for a in self.avisos(cuenta)]

    def cancelar(self, actor, v, motivo="cliente_desistio", descripcion="", *, huella=None):
        """Abre la cancelación y confirma (los dos pasos, como la pantalla)."""
        datos = compra_ventas.datos_de_cancelacion(actor, v.venta.pk)
        return compra_ventas.cancelar_compra_venta(actor, v.venta.pk, DatosDeCancelacionDeVenta(motivo, descripcion), huella or datos.huella)

    def estado_de(self, modelo, objeto):
        return modelo.objects.get(pk=objeto.pk)


class ComCnlCvtServicioTests(Base):
    # ---- flujo principal y postcondiciones ----

    def test_flujo_principal_cancela_la_venta_con_todo_lo_que_tenia(self):
        """Pasos 1 a 10: el Vendedor abre la cancelación, elige el motivo y confirma; la venta queda «cancelada» con su motivo y su fecha, y todo lo suyo, deshecho."""
        v = self.todo()
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        self.assertIsNone(datos.bloqueo)
        resultado = self.cancelar(self.e.vendedor, v, "cliente_desistio", "No lo necesita")
        venta = CompraVenta.objects.get(pk=v.venta.pk)
        self.assertEqual(resultado.pk, venta.pk)
        self.assertEqual((venta.estado_venta, venta.motivo_cancelacion_venta, venta.descripcion_cancelacion, venta.fecha_cancelacion_venta), ("cancelada", "cliente_desistio", "No lo necesita", HOY))

    def test_post_a_los_detalles_sin_entregar_pasan_a_cancelado_y_el_rechazado_no_cambia(self):
        """Postcondición a y D-67 punto 4: «abierto», «pendiente de decisión» y «confirmado» sin línea en una entrega concretada pasan a «cancelado»; el «rechazado» no cambia."""
        v = self.todo()
        DetalleVenta.objects.filter(pk=v.cosechado.pk).update(estado_detalle_venta="confirmado", cant_entregada_venta=30)  # aceptó un faltante: confirmado, todavía sin entregar
        otra, _ = variedad_con_stock(self.e, "Tercera")
        rechazado = detalle(v.venta, otra, 5, estado="rechazado")
        self.cancelar(self.e.vendedor, v)
        self.assertEqual(self.estado_de(DetalleVenta, v.abierto).estado_detalle_venta, "cancelado")
        self.assertEqual(self.estado_de(DetalleVenta, v.cosechado).estado_detalle_venta, "cancelado")
        self.assertEqual(self.estado_de(DetalleVenta, rechazado).estado_detalle_venta, "rechazado")

    def test_regla_detalles_afectados_el_pendiente_de_decision_tambien_se_cancela(self):
        """Regla «Detalles afectados»: el detalle «pendiente de decisión del cliente» de una venta pendiente se cancela."""
        v = self.todo(pendiente=True)
        self.cancelar(self.e.vendedor, v)
        self.assertEqual(self.estado_de(DetalleVenta, v.abierto).estado_detalle_venta, "cancelado")

    def test_post_b_las_reservas_quedan_liberadas_y_el_stock_vuelve_a_estar_libre(self):
        """Postcondición b: las tres reservas «liberadas»; el lote sin cosechar y la partida de cámara dejan de estar reservados (el stock libre es un derivado)."""
        from comercial.servicios import stock_maduro

        v = self.todo()
        self.assertEqual(stock_maduro.reservado_de_lotes([v.lote_a.pk]).get(v.lote_a.pk, 0), 40)
        self.cancelar(self.e.vendedor, v)
        for r in (v.reserva_abierta, v.reserva_cosechada, v.reserva_de_camara):
            self.assertEqual(self.estado_de(ReservaStock, r).estado_reserva, "liberada")
        self.assertEqual(stock_maduro.reservado_de_lotes([v.lote_a.pk]).get(v.lote_a.pk, 0), 0)

    def test_post_c_lo_cosechado_entra_a_la_camara_con_la_vida_util_de_su_cosecha_y_su_costo(self):
        """Postcondición c y regla 29 de 8.6: una partida `cancelacion_cliente` con min(cosechada, reservada), `fecha_limite` = fecha de cosecha + duración postcosecha, el costo de la salida por
        cosecha, `fecha_ingreso` hoy y su movimiento «ingreso a cámara» con la venta como origen. Solo la línea de lote ya cosechada: la de cámara y la sin cosechar no crean nada."""
        v = self.todo()
        antes = StockCosechado.objects.count()
        self.cancelar(self.e.vendedor, v)
        nuevas = StockCosechado.objects.filter(motivo_cosechado="cancelacion_cliente")
        self.assertEqual((nuevas.count(), StockCosechado.objects.count()), (1, antes + 1))
        p = nuevas.get()
        cosecha = Cosecha.objects.get(pk=v.reserva_cosechada.cosecha_id)
        self.assertEqual((p.lote_id, p.cantidad_ingreso_cosechado, p.cantidad_disponible_cosechado, p.fecha_ingreso), (v.lote_b.pk, 20, 20, HOY))
        self.assertEqual(p.fecha_limite, cosecha.fecha_cosecha + timedelta(days=v.variedad_b.duracion_post_cosecha))
        self.assertEqual(p.costo_unitario_cosechado, Decimal("2.5000"))
        movimiento = MovimientoStock.objects.get(partida=p, tipo_movimiento="ingreso_a_camara")
        self.assertEqual((movimiento.cantidad, movimiento.origen_id), (20, v.venta.pk))

    def test_post_c_la_partida_nueva_y_la_liberada_de_la_camara_se_asignan_despues_de_confirmar(self):
        """Postcondición c y paso 8.8: PROD-ASG-CAM corre en un `on_commit` con la partida nueva y la de la línea de cámara liberada, para que vaya a quien la espera."""
        v = self.todo()
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar, self.captureOnCommitCallbacks(execute=True):
            self.cancelar(self.e.vendedor, v)
        asignar.assert_called_once()
        ids = set(asignar.call_args.args[0])
        self.assertEqual(ids, {StockCosechado.objects.get(motivo_cosechado="cancelacion_cliente").pk, v.partida.pk})

    def test_post_d_se_cancelan_la_cosecha_y_la_entrega_pendientes_con_su_motivo_y_sus_envases(self):
        """Postcondición d (PROD-CNL-ORD): la cosecha «a realizar» y la entrega «a realizar» quedan «canceladas» con el motivo de la venta; los envases reservados, cancelados sin consumo."""
        v = self.todo(con_envases=True)
        self.cancelar(self.e.vendedor, v)
        motivo = MOTIVO.format(codigo=v.venta.codigo)
        cosecha, entrega_ = self.estado_de(Cosecha, v.cosecha), self.estado_de(Entrega, v.entrega)
        self.assertEqual((cosecha.estado_orden, cosecha.motivo_cancelacion, cosecha.fecha_resolucion_orden), ("cancelada", motivo, HOY))
        self.assertEqual((entrega_.estado_orden, entrega_.motivo_cancelacion, entrega_.fecha_resolucion_orden), ("cancelada", motivo, HOY))
        self.assertEqual(list(ReservaInsumo.objects.filter(orden=entrega_).values_list("estado", flat=True)), ["cancelada"])

    def test_post_d_la_alerta_de_entrega_sin_transportista_se_resuelve(self):
        """Postcondición d: la alerta «entrega sin transportista» de la entrega cancelada queda resuelta."""
        v = self.todo(transportista=None)
        alerta = entregas._alerta_sin_transportista(v.entrega, v.venta, "capacidad de carga insuficiente")
        self.cancelar(self.e.vendedor, v)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")

    def test_post_d_avisa_al_capataz_y_al_agronomo_de_la_cosecha_y_al_transportista_de_la_entrega(self):
        """Postcondición d y D-42: el Capataz y el Agrónomo reciben «Orden OT-… cancelada» de la cosecha; el transportista, «Se canceló la entrega OT-…»; con envases, el Agrónomo suma el aviso de los envases."""
        v = self.todo(con_envases=True)
        self.cancelar(self.e.vendedor, v)
        self.assertEqual(self.titulos(self.e.capataz), [f"Orden {v.cosecha.codigo} cancelada"])
        self.assertEqual(self.titulos(self.e.agronomo), [f"Orden {v.cosecha.codigo} cancelada", f"Se canceló {v.entrega.codigo}, que tenía envases reservados"])
        self.assertEqual(self.titulos(self.t), [f"Se canceló la entrega {v.entrega.codigo}"])
        self.assertIn(MOTIVO.format(codigo=v.venta.codigo).rstrip("."), self.avisos(self.t)[0].detalle)

    def test_post_e_el_enlace_de_decision_de_una_venta_pendiente_queda_anulado(self):
        """Postcondición e (D-65): el enlace vigente de la venta «pendiente de decisión del cliente» pasa a «anulado»."""
        v = self.todo(pendiente=True)
        self.assertEqual(v.enlace.estado, "vigente")
        self.cancelar(self.e.vendedor, v)
        self.assertEqual(self.estado_de(EnlaceCliente, v.enlace).estado, "anulado")

    def test_post_f_el_motivo_otro_con_descripcion_opcional_y_la_fecha_de_hoy(self):
        """Postcondición f y MD-130: con «otro» la descripción sigue siendo opcional; la fecha de cancelación es hoy."""
        v = self.todo()
        self.cancelar(self.e.vendedor, v, "otro", "")
        venta = CompraVenta.objects.get(pk=v.venta.pk)
        self.assertEqual((venta.motivo_cancelacion_venta, venta.descripcion_cancelacion, venta.fecha_cancelacion_venta), ("otro", "", HOY))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_el_comprobante_de_cancelacion_sale_despues_de_confirmar(self):
        """Postcondición g y paso 9: el correo con el comprobante sale después de la transacción (D-14, D-54); el comprobante queda «enviado»."""
        v = self.todo()
        with self.captureOnCommitCallbacks(execute=True):
            self.cancelar(self.e.vendedor, v)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [v.venta.cliente.email_cliente])
        self.assertEqual(mail.outbox[0].subject, f"Cancelación de tu compra {v.venta.codigo}")
        self.assertIn("El cliente desistió", mail.outbox[0].body)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_comprobante, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_9a_si_el_correo_falla_la_cancelacion_sigue_registrada_y_el_comprobante_queda_pendiente(self):
        """Extensión 9a: la cancelación permanece; el comprobante queda «pendiente de envío» (se reenvía desde la ficha) y, si canceló el Gerente, el Vendedor recibe el aviso."""
        v = self.todo()
        with mock.patch.object(correo, "enviar_correo", return_value=False), self.captureOnCommitCallbacks(execute=True):
            self.cancelar(self.gerente, v)
        venta = CompraVenta.objects.get(pk=v.venta.pk)
        self.assertEqual((venta.estado_venta, venta.estado_comprobante), ("cancelada", "pendiente_envio"))
        self.assertIn("Comprobante pendiente de envío", self.titulos(self.e.vendedor))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_un_cliente_sin_correo_no_recibe_nada_y_el_comprobante_queda_para_imprimir(self):
        """Postcondición g y regla 18 de 8.20: sin correo no se intenta enviar; el comprobante queda «para imprimir»."""
        v = self.todo()
        v.venta.cliente.__class__.objects.filter(pk=v.venta.cliente_id).update(email_cliente="")
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        self.assertEqual(datos.comprobante, None)
        with self.captureOnCommitCallbacks(execute=True):
            self.cancelar(self.e.vendedor, v)
        self.assertEqual((mail.outbox, CompraVenta.objects.get(pk=v.venta.pk).estado_comprobante), ([], "para_imprimir"))

    def test_post_h_si_cancela_el_gerente_se_avisa_al_vendedor_y_si_cancela_el_vendedor_no(self):
        """Postcondición h y extensión 1a: el Gerente cancela y el Vendedor recibe «CV-… cancelada» con el motivo; si cancela el propio Vendedor, no se avisa a sí mismo."""
        v = self.todo()
        self.cancelar(self.gerente, v, "cliente_no_retiro")
        avisos = [a for a in self.avisos(self.e.vendedor) if a.titulo == f"{v.venta.codigo} cancelada"]
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].detalle, f"El Gerente canceló la venta de {v.venta.cliente.nombre_visible}. Motivo: el cliente no retiró.")
        w = self.todo()
        self.cancelar(self.e.vendedor, w)
        self.assertEqual(self.titulos(self.e.vendedor).count(f"{w.venta.codigo} cancelada"), 0)

    def test_post_i_registra_una_auditoria_con_el_motivo_los_estados_y_lo_deshecho(self):
        """Postcondición i y D-36: UN registro `cancelacion_compra_venta` con el actor y su rol; la venta, los detalles, las reservas, las partidas, las cosechas y las entregas en los afectados;
        `cambios` con el estado y los datos de la cancelación."""
        v = self.todo()
        antes = RegistroAuditoria.objects.filter(accion="cancelacion_compra_venta").count()
        self.cancelar(self.e.vendedor, v, "otro", "Cambió de proveedor")
        registros = RegistroAuditoria.objects.filter(accion="cancelacion_compra_venta")
        self.assertEqual(registros.count(), antes + 1)
        registro = registros.latest("pk")
        self.assertEqual(registro.usuario_id, self.e.vendedor.pk)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado_venta"], {"antes": "abierta", "despues": "cancelada"})
        self.assertEqual(cambios["motivo_cancelacion_venta"]["despues"], "otro")
        self.assertEqual(cambios["descripcion_cancelacion"]["despues"], "Cambió de proveedor")
        self.assertEqual(cambios["fecha_cancelacion_venta"]["despues"], f"{HOY:%d/%m/%Y}")
        modelos = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertIn(("comercial.compraventa", v.venta.pk), {(m.lower(), i) for m, i in modelos})
        for clave in ("detalles_cancelados", "cosechas_canceladas", "entregas_canceladas", "partidas_creadas"):
            self.assertTrue(registro.detalle["datos"][clave], clave)

    # ---- reglas ----

    def test_regla_quien_cancela_el_vendedor_del_contrato_o_el_gerente(self):
        """Paso 1 y extensión 1a: el Vendedor de otro contrato, el Agrónomo y el Transportista reciben `PermissionDenied`; el Vendedor inactivo no entra y su venta la cancela el Gerente."""
        v = self.todo()
        for actor in (crear_vendedor(email="ajeno@infoponia.com"), crear_agronomo(email="otro@infoponia.com"), self.t):
            with self.assertRaises(PermissionDenied):
                compra_ventas.datos_de_cancelacion(actor, v.venta.pk)
            with self.assertRaises(PermissionDenied):
                compra_ventas.cancelar_compra_venta(actor, v.venta.pk, DatosDeCancelacionDeVenta("otro"), "x")
        Usuario.objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        self.cancelar(self.gerente, v)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "cancelada")

    def test_regla_una_venta_inexistente_es_un_404(self):
        """Un id que no existe es un 404."""
        from django.http import Http404

        with self.assertRaises(Http404):
            compra_ventas.datos_de_cancelacion(self.gerente, 999999)

    def test_regla_venta_cancelable_una_concretada_o_cancelada_no_se_cancela(self):
        """Precondición b: solo «abierta» o «pendiente de decisión»; una «concretada» o «cancelada» rechaza con `venta_no_cancelable` y la pantalla lo dice."""
        for estado in ("concretada", "cancelada"):
            venta = compra_venta(self.e, estado=estado)
            detalle(venta, self.e.variedad, 5, estado="confirmado")
            datos = compra_ventas.datos_de_cancelacion(self.gerente, venta.pk)
            self.assertIsNotNone(datos.bloqueo, estado)
            with self.assertRaises(ValidationError) as c:
                compra_ventas.cancelar_compra_venta(self.gerente, venta.pk, DatosDeCancelacionDeVenta("otro"), datos.huella)
            self.assertEqual(codigos(c.exception), ["venta_no_cancelable"], estado)

    def test_regla_motivo_obligatorio_de_su_lista_y_descripcion_de_hasta_300(self):
        """Paso 5: sin motivo, `motivo_obligatorio`; uno fuera de la lista, `motivo_invalido`; una descripción de 301, `descripcion_larga`; de 300 (con espacios al borde) se acepta recortada."""
        v = self.todo()
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        casos = (("", "", "motivo_obligatorio"), ("porque_si", "", "motivo_invalido"), ("otro", "x" * 301, "descripcion_larga"))
        for motivo, descripcion, codigo in casos:
            with self.assertRaises(ValidationError) as c:
                compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta(motivo, descripcion), datos.huella)
            self.assertEqual(codigos(c.exception), [codigo])
            with self.assertRaises(ValidationError):
                compra_ventas.resumen_de_cancelacion_de_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta(motivo, descripcion))
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")
        self.cancelar(self.e.vendedor, v, "otro", "  " + "x" * 300 + "  ")
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).descripcion_cancelacion, "x" * 300)

    def test_regla_sin_cancelacion_automatica_el_paso_50_no_vuelve_a_planificar_nada_de_la_venta(self):
        """Regla «Venta que nunca se retira» y «Venta lista» de COM-PNF-ENT: después de cancelar, la recuperación diaria no crea entregas de la venta cancelada."""
        v = self.todo()
        self.cancelar(self.e.vendedor, v)
        antes = Entrega.objects.count()
        entregas.planificar_entregas(HOY)
        self.assertEqual(Entrega.objects.count(), antes)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "cancelada")

    def test_regla_datos_de_cancelacion_separa_lo_que_vuelve_a_los_lotes_a_las_partidas_y_a_la_camara(self):
        """Paso 4: cada detalle con su efecto; las reservas en tres grupos (lotes sin cosechar, partidas de cámara y lo ya cosechado que ingresa a la cámara con su fecha límite); las cosechas y
        las entregas que se cancelan (con su transportista y si tienen envases); el destino del comprobante."""
        v = self.todo(con_envases=True)
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        self.assertEqual([d.efecto for d in datos.detalles], ["Se cancela", "Se cancela"])
        self.assertEqual([(g.cantidad) for g in datos.a_lotes], [40])
        self.assertEqual([(g.cantidad) for g in datos.a_partidas], [10])
        self.assertEqual([(g.cantidad) for g in datos.a_camara], [20])
        self.assertIsNotNone(datos.a_camara[0].fecha_limite)
        self.assertEqual([c.codigo for c in datos.cosechas], [v.cosecha.codigo])
        self.assertEqual([(e.codigo, e.transportista, e.con_envases) for e in datos.entregas], [(v.entrega.codigo, self.t.get_full_name(), True)])
        self.assertEqual((datos.en_curso, datos.concretadas, datos.comprobante), ([], [], v.venta.cliente.email_cliente))

    def test_regla_el_resumen_trae_el_motivo_y_el_estado_final_y_no_escribe(self):
        """Pasos 6 y 7: el resumen valida igual que la confirmación, dice el motivo y que la venta queda «Cancelada», y no escribe nada."""
        v = self.todo()
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        resumen = compra_ventas.resumen_de_cancelacion_de_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("cliente_no_retiro", "Nunca vino"))
        self.assertEqual((resumen.motivo_texto, resumen.descripcion, resumen.estado_final), ("El cliente no retiró", "Nunca vino", "Cancelada"))
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")

    def test_regla_un_cliente_dado_de_baja_tambien_cancela(self):
        """Regla 2 de 8.18: el cliente dado de baja puede cancelar (no se verifica que siga activo)."""
        v = self.todo()
        v.venta.cliente.__class__.objects.filter(pk=v.venta.cliente_id).update(estado_cliente="inactivo")
        self.cancelar(self.e.vendedor, v)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "cancelada")

    def test_regla_un_invernadero_dado_de_baja_con_una_partida_de_la_venta_igual_se_cancela(self):
        """D-64 punto 12: el producto existe aunque el invernadero se haya dado de baja; los invernaderos se toman con `bloquear_invernadero_para_alertas` (activo o no)."""
        v = self.todo(transportista=None)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.cancelar(self.gerente, v)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "cancelada")
        self.assertEqual(StockCosechado.objects.filter(motivo_cosechado="cancelacion_cliente").count(), 1)

    def test_ext_6b_una_entrega_de_retiro_se_cancela_igual_sin_transportista_que_avisar(self):
        """Extensión 6b: la entrega de retiro «a realizar» se cancela como una con envío; no hay transportista al que avisar."""
        lote = lote_maduro(self.e, 300)
        venta = compra_venta(self.e, modalidad="retiro")
        det = detalle(venta, self.e.variedad, 50)
        e = entrega(venta, [reserva_lista(det, lote, 50)])
        self.cancelar(self.e.vendedor, type("V", (), {"venta": venta})())
        self.assertEqual((self.estado_de(Entrega, e).estado_orden, Notificacion.objects.filter(titulo__startswith="Se canceló la entrega").count()), ("cancelada", 0))

    def test_ext_1a_una_venta_de_dos_invernaderos_cancela_las_dos_entregas(self):
        """Una venta con entregas de dos invernaderos: se cancelan las dos y se toman los dos invernaderos."""
        v = self.todo()
        otro = segundo_invernadero(self.e)
        tercera, _ = variedad_con_stock(otro, "Tercera")
        lote = lote_maduro(otro, 100, variedad=tercera)
        det = detalle(v.venta, tercera, 10)
        segunda = entrega(v.venta, [reserva_lista(det, lote, 10)])
        self.cancelar(self.e.vendedor, v)
        self.assertEqual({self.estado_de(Entrega, v.entrega).estado_orden, self.estado_de(Entrega, segunda).estado_orden}, {"cancelada"})
        self.assertEqual(self.estado_de(DetalleVenta, det).estado_detalle_venta, "cancelado")

    # ---- extensiones 4a, 6a, 8a y 8b ----

    def test_ext_4a_con_una_entrega_en_curso_no_se_puede_cancelar(self):
        """Extensión 4a: con el vehículo del transportista en ruta y fecha de hoy o anterior, la pantalla avisa y no deja seguir; el servicio rechaza con `entrega_en_curso` y no cambia nada."""
        v = self.todo(dias=0)
        iniciar_ruta_de(self.t)  # COM-06a: la ruta se inicia de verdad (antes, `vehiculo_en_ruta`)
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        self.assertEqual([e.codigo for e in datos.en_curso], [v.entrega.codigo])
        self.assertIn("No se puede cancelar mientras el producto está en viaje", datos.bloqueo)
        self.assertIn(self.t.get_full_name(), datos.bloqueo)
        with self.assertRaises(ValidationError) as c:
            compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("otro"), datos.huella)
        self.assertEqual(codigos(c.exception), ["entrega_en_curso"])
        self.assertEqual((CompraVenta.objects.get(pk=v.venta.pk).estado_venta, self.estado_de(Entrega, v.entrega).estado_orden), ("abierta", "a_realizar"))

    def test_ext_6a_con_una_entrega_concretada_ya_no_se_rechaza_pide_el_medio_de_pago_para_cobrar_lo_entregado(self):
        """Extensión 6a (COM-08b; D-94 punto 14). REEMPLAZA a `test_ext_6a_con_una_entrega_concretada_se_rechaza_con_venta_con_entregas_concretadas` (COM-05b), que esperaba el rechazo `venta_con_entregas_concretadas`:
        ese código ya no existe. Con una entrega concretada armada con la fábrica, `datos_de_cancelacion` la lista, calcula el monto a cobrar de lo entregado y **no** bloquea; confirmar sin el medio de pago se
        rechaza con `medio_de_pago_obligatorio` (6a.2) y no cambia nada."""
        v = self.todo()
        marcar_concretada(v.entrega)  # COM-06a: una concretada con sus cantidades y su monto (antes, solo el estado)
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        self.assertEqual([e.codigo for e in datos.concretadas], [v.entrega.codigo])
        self.assertIsNone(datos.bloqueo)
        self.assertGreater(datos.cobro.total, Decimal("0.00"))
        with self.assertRaises(ValidationError) as c:
            compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("otro"), datos.huella)
        self.assertEqual(codigos(c.exception), ["medio_de_pago_obligatorio"])
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")
        self.assertEqual(PagoCliente.objects.count(), 0)

    def test_ext_8a_si_la_venta_cambio_de_estado_no_se_registra_nada(self):
        """Extensión 8a: la venta cambió de estado mientras se miraba el resumen: se informa y no se cambia nada."""
        v = self.todo()
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        CompraVenta.objects.filter(pk=v.venta.pk).update(estado_venta="pendiente_decision")
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        with self.assertRaises(ValidationError) as c:
            compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("otro"), datos.huella)
        self.assertEqual(codigos(c.exception), ["venta_cambio"])
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertEqual(self.estado_de(Entrega, v.entrega).estado_orden, "a_realizar")

    def test_ext_8a_cada_causa_una_entrega_se_cancelo_o_se_concreto_o_paso_a_estar_en_curso(self):
        """Extensión 8a: otra operación canceló o concretó la entrega, o la dejó en curso, entre el resumen y la confirmación: no se registra nada."""
        for causa in ("cancelada", "concretada", "en_curso"):
            v = self.todo(dias=0)
            datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
            if causa == "en_curso":
                vehiculo_en_ruta(self.t)
            else:
                Entrega.objects.filter(pk=v.entrega.pk).update(estado_orden=causa, fecha_resolucion_orden=HOY, **({"motivo_cancelacion": "x"} if causa == "cancelada" else {}))
            with self.assertRaises(ValidationError) as c:
                compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("otro"), datos.huella)
            self.assertIn(codigos(c.exception)[0], ("venta_cambio", "entrega_en_curso", "venta_con_entregas_concretadas"), causa)
            self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta", causa)
            if causa == "en_curso":
                from comercial.models import Vehiculo

                Vehiculo.objects.filter(transportista=self.t).update(en_ruta=False, fecha_inicio_ruta=None)
            CompraVenta.objects.filter(pk=v.venta.pk).update(estado_venta="cancelada")  # para que la siguiente vuelta empiece de cero
            Entrega.objects.filter(pk=v.entrega.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")

    def test_ext_8b_si_una_cosecha_se_concreto_en_otra_operacion_vuelve_al_paso_4(self):
        """Extensión 8b: una orden de cosecha se concretó mientras se miraba el resumen: no se registra nada y la huella nueva ya lo trae como ingreso a la cámara."""
        v = self.todo()
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk)
        # La otra operación concreta la cosecha de verdad (con su bitácora y lo cosechado), no con un `update` que dejaría los invariantes rotos.
        cosechas.concretar_cosecha(self.e.capataz, v.cosecha.pk, DatosDeConcrecion(cantidades=((v.lote_a.pk, self.e.sectores["maduracion"].pk, 40),)))
        with self.assertRaises(ValidationError) as c:
            compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("otro"), datos.huella)
        self.assertEqual(codigos(c.exception), ["venta_cambio"])
        self.assertEqual((CompraVenta.objects.get(pk=v.venta.pk).estado_venta, StockCosechado.objects.filter(motivo_cosechado="cancelacion_cliente").count()), ("abierta", 0))
        self.assertNotEqual(compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk).huella, datos.huella)


# ---- las pantallas (COM-CNL-CVT, «Pantallas» y «Pruebas»: `ComCnlCvtVistaTests`) ----

HTMX = {"HTTP_HX_REQUEST": "true"}


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class ComCnlCvtVistaTests(Base):
    def url(self, v, nombre="cancelar"):
        return reverse(f"comercial:compra_venta_{nombre}", args=[v.venta.pk])

    def ir(self, usuario, v, nombre="cancelar", metodo="get", datos=None, **extra):
        self.client.force_login(usuario)
        return getattr(self.client, metodo)(self.url(v, nombre), datos or {}, **extra)

    def mensajes(self, respuesta):
        return [m.message for m in respuesta.context["messages"]] if respuesta.context else []

    def huella(self, v):
        return compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk).huella

    # ---- permisos y botones ----

    def test_regla_permisos_el_vendedor_del_contrato_y_el_gerente_entran_y_los_demas_reciben_403(self):
        """SEG-13 y D-28: el Vendedor de otro contrato, el Agrónomo, el Capataz y el Transportista no entran a ninguna de las tres pantallas ni a la confirmación; un id inexistente, 404."""
        v = self.todo()
        self.assertEqual(self.ir(self.e.vendedor, v).status_code, 200)
        self.assertEqual(self.ir(self.gerente, v).status_code, 200)
        for ajeno in (crear_vendedor(email="ajeno@infoponia.com"), self.e.agronomo, self.e.capataz, self.t):
            self.assertEqual(self.ir(ajeno, v).status_code, 403, ajeno.rol)
            self.assertEqual(self.ir(ajeno, v, "cancelar", "post", {"motivo": "otro", "huella": "x"}).status_code, 403, ajeno.rol)
            self.assertEqual(self.ir(ajeno, v, "cancelar_revisar", "post", {"motivo": "otro"}).status_code, 403, ajeno.rol)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("comercial:compra_venta_cancelar", args=[999999])).status_code, 404)

    def test_regla_la_ficha_ofrece_el_boton_solo_con_la_venta_abierta_o_pendiente_y_ningun_boton_lleva_a_un_403(self):
        """Regla 5 de COM-CNS-CVT: «Cancelar compra-venta» para el Vendedor del contrato y el Gerente con la venta «abierta» o «pendiente»; no en una cancelada; y ningún botón de la ficha da 403."""
        v = self.todo()
        self.client.force_login(self.e.vendedor)
        ficha = self.client.get(reverse("comercial:compra_venta", args=[v.venta.pk]))
        self.assertContains(ficha, "Cancelar compra-venta")
        self.assertContains(ficha, self.url(v))
        for url in re.findall(r'href="(/comercial/[^"]*)"', ficha.content.decode()):
            self.assertNotEqual(self.client.get(url).status_code, 403, url)
        CompraVenta.objects.filter(pk=v.venta.pk).update(estado_venta="pendiente_decision")
        self.assertContains(self.client.get(reverse("comercial:compra_venta", args=[v.venta.pk])), "Cancelar compra-venta")
        self.cancelar(self.e.vendedor, v)  # cancelada de verdad (con sus cosechas y entregas), no con un `update` que dejaría los invariantes rotos
        self.assertNotContains(self.client.get(reverse("comercial:compra_venta", args=[v.venta.pk])), "Cancelar compra-venta")

    # ---- la pantalla ----

    def test_flujo_principal_la_pantalla_dice_que_se_cancela_que_pasa_con_el_producto_y_pide_el_motivo(self):
        """Pasos 2 a 5: el texto explicativo, «Qué se cancela» (cada detalle con su efecto), «Qué pasa con el producto» (lo que vuelve a los lotes, a las partidas, lo que entra a la cámara con su fecha
        límite, las cosechas y las entregas) y «Motivo» con los tres botones de opción y la descripción opcional."""
        v = self.todo(con_envases=True)
        html = texto(self.ir(self.e.vendedor, v))
        for esperado in (
            f"Cancelar {v.venta.codigo}",
            "Cancelar libera todo lo reservado para esta venta: lo ya cosechado entra a la cámara y queda disponible para otros contratos. Las cosechas y las entregas pendientes se cancelan y se avisa a quienes las tenían.",
            "Qué se cancela", "Se cancela", "Qué pasa con el producto", f"Vuelve al lote {v.lote_a.codigo}", "Entra a la cámara: 20 plantas", "con fecha límite",
            f"Se cancela la cosecha {v.cosecha.codigo}", f"Se cancela la entrega {v.entrega.codigo}", "se cancelan sus envases reservados",
            "El cliente desistió", "El cliente no retiró", "Otro", "Descripción", "Revisar y cancelar", "Se enviará el comprobante a",
        ):
            self.assertIn(esperado, html)
        self.assertEqual(len(re.findall(r'type="radio" name="motivo"', html)), 3)

    def test_ext_4a_con_una_entrega_en_curso_avisa_y_no_deja_seguir(self):
        """Extensión 4a: «No se puede cancelar mientras el producto está en viaje: OT-… salió hoy con …» y sin botón de revisar."""
        v = self.todo(dias=0)
        vehiculo_en_ruta(self.t)
        html = texto(self.ir(self.e.vendedor, v))
        self.assertIn(f"No se puede cancelar mientras el producto está en viaje: {v.entrega.codigo} salió hoy con {self.t.get_full_name()}.", html)
        self.assertNotIn("Revisar y cancelar", html)

    def test_regla_un_cliente_sin_correo_avisa_que_hay_que_imprimir_el_comprobante(self):
        """Regla 18 de 8.20: en el resumen del costado, «El cliente no tiene correo: vas a tener que imprimir el comprobante.»"""
        v = self.todo()
        v.venta.cliente.__class__.objects.filter(pk=v.venta.cliente_id).update(email_cliente="")
        self.assertIn("El cliente no tiene correo: vas a tener que imprimir el comprobante.", texto(self.ir(self.e.vendedor, v)))

    # ---- revisar (pasos 6 y 7) ----

    def test_flujo_principal_revisar_sin_javascript_es_una_pagina_con_el_resumen_y_no_escribe(self):
        """Sin JavaScript el resumen es una página con la advertencia «La cancelación no se puede deshacer.» y «Confirmar cancelación»; no cambia nada."""
        v = self.todo()
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        respuesta = self.ir(self.e.vendedor, v, "cancelar_revisar", "post", {"motivo": "cliente_desistio", "descripcion": "No lo necesita", "huella": self.huella(v)})
        html = texto(respuesta)
        self.assertIn("<html", html)
        for esperado in ("Resumen de la cancelación", "El cliente desistió: No lo necesita", "Cancelada", "La cancelación no se puede deshacer.", "Confirmar cancelación"):
            self.assertIn(esperado, html)
        self.assertEqual(((RegistroAuditoria.objects.count(), Notificacion.objects.count()), CompraVenta.objects.get(pk=v.venta.pk).estado_venta), (antes, "abierta"))

    def test_flujo_principal_revisar_con_htmx_devuelve_solo_la_ventana(self):
        """Con HTMX llega solo la ventana del resumen (sobre la pantalla), con «Confirmar cancelación» y «Volver»."""
        v = self.todo()
        html = texto(self.ir(self.e.vendedor, v, "cancelar_revisar", "post", {"motivo": "otro", "huella": self.huella(v)}, **HTMX))
        self.assertNotIn("<html", html)
        self.assertIn("data-ventana", html)
        self.assertIn("Confirmar cancelación", html)

    def test_regla_revisar_sin_motivo_vuelve_a_la_pantalla_con_el_error_del_campo(self):
        """Paso 5: sin motivo, «Elegí el motivo de la cancelación.» bajo los botones y la venta sin tocar; con una descripción de 301, el error de la descripción."""
        v = self.todo()
        html = texto(self.ir(self.e.vendedor, v, "cancelar_revisar", "post", {"huella": self.huella(v)}))
        self.assertIn("Elegí el motivo de la cancelación.", html)
        html = texto(self.ir(self.e.vendedor, v, "cancelar_revisar", "post", {"motivo": "otro", "descripcion": "x" * 301, "huella": self.huella(v)}))
        self.assertIn("La descripción pasa de 300 caracteres.", html)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")

    # ---- confirmar (paso 8) ----

    def test_flujo_principal_confirmar_cancela_y_avisa_lo_que_se_deshizo(self):
        """Paso 10: «CV-… cancelada. Se canceló 1 cosecha y 1 entrega; 20 plantas entraron a la cámara.» más el comprobante (sin el correo del sistema: «No se pudo enviar…»); la ficha muestra los datos."""
        v = self.todo()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.ir(self.e.vendedor, v, "cancelar", "post", {"motivo": "cliente_desistio", "descripcion": "No lo necesita", "huella": self.huella(v)}, follow=True)
        self.assertRedirects(respuesta, reverse("comercial:compra_venta", args=[v.venta.pk]))
        mensajes = self.mensajes(respuesta)
        self.assertIn(f"{v.venta.codigo} cancelada. Se canceló 1 cosecha y 1 entrega; 20 plantas entraron a la cámara.", mensajes)
        html = texto(respuesta)
        for esperado in ("Cancelación", f"Cancelada el {HOY:%d/%m/%Y}. Motivo: el cliente desistió.", "No lo necesita", "Cancelada"):
            self.assertIn(esperado, html)
        self.assertNotContains(respuesta, "Cancelar compra-venta")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_con_el_correo_configurado_el_aviso_dice_a_quien_se_envio_el_comprobante(self):
        """Postcondición g: «… Se envió el comprobante a <correo>.» y el correo sale."""
        v = self.todo()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.ir(self.e.vendedor, v, "cancelar", "post", {"motivo": "otro", "huella": self.huella(v)}, follow=True)
        self.assertTrue(any(f"Se envió el comprobante a {v.venta.cliente.email_cliente}." in m for m in self.mensajes(respuesta)))
        self.assertEqual(len(mail.outbox), 1)

    def test_post_g_un_cliente_sin_correo_ofrece_imprimir_el_comprobante_en_la_ficha(self):
        """Regla 18 de 8.20 y paso 10: «El cliente no tiene correo: imprimí el comprobante.» y, en la ficha, el botón «Imprimir comprobante»."""
        v = self.todo()
        v.venta.cliente.__class__.objects.filter(pk=v.venta.cliente_id).update(email_cliente="")
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.ir(self.e.vendedor, v, "cancelar", "post", {"motivo": "otro", "huella": self.huella(v)}, follow=True)
        self.assertTrue(any("El cliente no tiene correo: imprimí el comprobante." in m for m in self.mensajes(respuesta)))
        self.assertContains(respuesta, "Imprimir comprobante")

    def test_regla_confirmar_sin_motivo_vuelve_a_la_pantalla_y_no_cancela(self):
        """Sin motivo, el POST no cancela: vuelve a la pantalla con el error."""
        v = self.todo()
        respuesta = self.ir(self.e.vendedor, v, "cancelar", "post", {"huella": self.huella(v)})
        self.assertContains(respuesta, "Elegí el motivo de la cancelación.")
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")

    def test_ext_8a_si_la_venta_cambio_vuelve_al_paso_4_con_el_mensaje(self):
        """Extensión 8a: «La compra-venta cambió mientras mirabas el resumen…»: se vuelve a la pantalla de cancelación con los datos nuevos y no se registra nada."""
        v = self.todo()
        huella = self.huella(v)
        Entrega.objects.filter(pk=v.entrega.pk).update(transportista=self.t)
        Entrega.objects.filter(pk=v.entrega.pk).update(fecha_programada_orden=HOY + timedelta(days=9))
        respuesta = self.ir(self.e.vendedor, v, "cancelar", "post", {"motivo": "otro", "huella": huella}, follow=True)
        self.assertRedirects(respuesta, reverse("comercial:compra_venta_cancelar", args=[v.venta.pk]))
        self.assertTrue(any("La compra-venta cambió mientras mirabas el resumen" in m for m in self.mensajes(respuesta)))
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")

    def test_ext_8a_una_venta_que_ya_no_se_puede_cancelar_vuelve_a_la_ficha(self):
        """Una venta que otro cerró mientras tanto: el mensaje y la ficha (no hay nada que corregir)."""
        v = self.todo()
        huella = self.huella(v)
        self.cancelar(self.gerente, v)  # otro la cancela mientras tanto (de verdad: con sus cosechas y entregas)
        respuesta = self.ir(self.e.vendedor, v, "cancelar", "post", {"motivo": "otro", "huella": huella}, follow=True)
        self.assertRedirects(respuesta, reverse("comercial:compra_venta", args=[v.venta.pk]))
        self.assertTrue(any("ya está cancelada" in m for m in self.mensajes(respuesta)))

    def test_regla_sin_javascript_volver_deja_la_pantalla_con_lo_elegido(self):
        """El resumen sin JavaScript tiene «Volver»: deja la pantalla de cancelación con el motivo y la descripción elegidos, sin cancelar."""
        v = self.todo()
        html = texto(self.ir(self.e.vendedor, v, "cancelar", "post", {"volver": "1", "motivo": "cliente_no_retiro", "descripcion": "Nunca vino", "huella": self.huella(v)}))
        self.assertRegex(html, r'name="motivo" value="cliente_no_retiro" checked')
        self.assertIn("Nunca vino", html)
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")

    # ---- el comprobante ----

    def test_regla_el_comprobante_imprimible_de_una_venta_cancelada_dice_el_motivo_y_lo_que_se_cancelo(self):
        """Paso 9: la página imprimible dice «Cancelación de la compra…», el motivo, lo que se canceló y «Comprobante interno, sin validez fiscal.» (sin el monto estimado ni «El pago se realiza al recibir»)."""
        v = self.todo()
        self.cancelar(self.e.vendedor, v, "cliente_no_retiro", "Nunca vino")
        self.client.force_login(self.e.vendedor)
        html = texto(self.client.get(reverse("comercial:compra_venta_comprobante", args=[v.venta.pk])))
        for esperado in (f"Cancelación de la compra {v.venta.codigo}", "El cliente no retiró", "Nunca vino", "Lo que se canceló", str(v.abierto.variedad), "Comprobante interno, sin validez fiscal."):
            self.assertIn(esperado, html)
        self.assertNotIn("Monto estimado", html)
        self.assertNotIn("El pago se realiza al recibir", html)


class ComCnlCvtConEntregaConcretadaRealTests(Base):
    """COM-06a (`rutas.md`, «Lo que completa a otras tareas», fila COM-05b): las pruebas de 6a y de D-67 punto 4 con una entrega **concretada de verdad** (con `concrecion.concretar_entrega`), no armada con la fábrica."""

    def venta_con_una_entrega_concretada(self, fecha_de_la_segunda=HOY):
        """Una venta con dos detalles (dos variedades) y dos entregas del mismo transportista (la primera de hoy y la segunda de ``fecha_de_la_segunda``, hoy por omisión), con la ruta iniciada; se concreta la
        primera (no es la última de la venta: no se cobra). Con la segunda de hoy, queda «en curso» (4a); COM-08b la pone de mañana para poder cancelar la venta (6a).
        Devuelve `(venta, detalle_entregado, detalle_pendiente, entrega_concretada, entrega_pendiente)`."""
        otra, _ = variedad_con_stock(self.e, "Otra variedad")
        lote_a, lote_b = lote_maduro(self.e, 500), lote_maduro(self.e, 500, variedad=otra)
        venta = compra_venta(self.e, dias=0)
        entregado, pendiente = detalle(venta, self.e.variedad, 50), detalle(venta, otra, 30)
        e1 = entrega(venta, [reserva_lista(entregado, lote_a, 50)], transportista=self.t, fecha=HOY)
        e2 = entrega(venta, [reserva_lista(pendiente, lote_b, 30)], transportista=self.t, fecha=fecha_de_la_segunda)
        iniciar_ruta_de(self.t)
        datos = concrecion.DatosDeConcrecion(sin_envases=True)
        resumen = concrecion.resumen_de_concrecion(self.t, e1.pk, datos)
        concrecion.concretar_entrega(self.t, e1.pk, datos, resumen.huella)
        return venta, entregado, pendiente, e1, e2

    # ---- extensión 6a (COM-08b; D-94 punto 14): REEMPLAZA a `test_ext_6a_con_una_entrega_concretada_real_el_servicio_sigue_rechazando_hasta_la_cobranza` (COM-06a), que esperaba el rechazo
    # `venta_con_entregas_concretadas` («hasta la cobranza»). Con COM-08b la cancelación cobra lo entregado y la venta queda «concretada». ----

    def monto_de(self, entrega_):
        """Σ `monto_pagar` de las líneas de ``entrega_`` (lo que registró la entrega, regla 32 de 8.6)."""
        return sum((l.monto_pagar for l in DetalleEntrega.objects.filter(entrega=entrega_)), Decimal("0.00"))

    def cancelar_con_cobro(self, actor, venta, medio="efectivo", motivo="cliente_desistio", descripcion=""):
        datos = compra_ventas.datos_de_cancelacion(actor, venta.pk)
        return compra_ventas.cancelar_compra_venta(actor, venta.pk, DatosDeCancelacionDeVenta(motivo, descripcion, medio), datos.huella)

    def test_ext_6a_con_una_entrega_concretada_real_se_cancela_lo_pendiente_y_se_cobra_lo_entregado(self):
        """Extensión 6a y postcondición f: con una entrega concretada de verdad, `datos_de_cancelacion` la lista con el monto a cobrar de lo entregado (Σ `monto_pagar`) y no bloquea; al confirmar con el medio de
        pago, la venta queda «concretada» con `fecha_concrecion_venta` y los datos de la cancelación, la entrega pendiente y su detalle se cancelan y el detalle ya entregado no cambia."""
        venta, entregado, pendiente, e1, e2 = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, venta.pk)
        self.assertEqual(([e.codigo for e in datos.concretadas], datos.bloqueo), ([e1.codigo], None))
        self.assertEqual(datos.cobro.total, self.monto_de(e1))
        self.assertGreater(datos.cobro.total, Decimal("0.00"))
        self.assertEqual([(f.codigo, f.fecha, f.monto) for f in datos.cobro.entregas], [(e1.codigo, HOY, self.monto_de(e1))])
        self.cancelar_con_cobro(self.e.vendedor, venta, "efectivo", "cliente_no_retiro", "Se fue de viaje.")
        v = CompraVenta.objects.get(pk=venta.pk)
        self.assertEqual((v.estado_venta, v.fecha_concrecion_venta, v.motivo_cancelacion_venta, v.descripcion_cancelacion, v.fecha_cancelacion_venta), ("concretada", HOY, "cliente_no_retiro", "Se fue de viaje.", HOY))
        self.assertEqual(self.estado_de(Entrega, e2).estado_orden, "cancelada")
        self.assertEqual(self.estado_de(Entrega, e1).estado_orden, "concretada")
        self.assertEqual((self.estado_de(DetalleVenta, entregado).estado_detalle_venta, self.estado_de(DetalleVenta, pendiente).estado_detalle_venta), ("confirmado", "cancelado"))

    def test_post_f_el_cobro_es_un_pago_de_compra_venta_por_lo_entregado_con_el_medio_elegido(self):
        """Postcondición f y D-94 punto 14: un `PagoCliente` de tipo `compra_venta` de la venta y su cliente, con el medio, la fecha de hoy, el monto = Σ `monto_pagar` de las entregas concretadas, «vigente», el usuario que
        canceló, sin número ni líneas de pago; y la venta concretada tiene exactamente un pago vigente (invariante de COM-06a)."""
        venta, _, _, e1, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        self.cancelar_con_cobro(self.e.vendedor, venta, "transferencia")
        pago = PagoCliente.objects.get()
        self.assertEqual(
            (pago.tipo_pago, pago.compra_venta_id, pago.cliente_id, pago.medio_pago, pago.fecha_pago, pago.monto_pagado, pago.estado_pago, pago.usuario_id, pago.numero),
            ("compra_venta", venta.pk, venta.cliente_id, "transferencia", HOY, self.monto_de(e1), "vigente", self.e.vendedor.pk, None),
        )
        self.assertEqual(pago.lineas.count(), 0)
        self.assertEqual(PagoCliente.objects.filter(compra_venta=venta, estado_pago="vigente").count(), 1)
        verificar_invariantes_de_cobros()

    def test_regla_cobro_de_lo_entregado_cada_medio_de_la_lista_se_admite(self):
        """Regla «Medio de pago» (regla 15 de 8.13): los cuatro medios de `PagoCliente.medio_pago` valen."""
        for medio in ("efectivo", "transferencia", "tarjeta_debito", "tarjeta_credito"):
            venta, _, _, _, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
            self.cancelar_con_cobro(self.e.vendedor, venta, medio)
            self.assertEqual(PagoCliente.objects.get(compra_venta=venta).medio_pago, medio)

    def test_ext_6a_el_medio_de_pago_es_obligatorio_con_entregas_concretadas(self):
        """6a.2: sin medio (o con uno que no es de la lista) se rechaza `medio_de_pago_obligatorio` y no cambia nada (ni la venta, ni los detalles, ni la entrega pendiente, ni el pago)."""
        venta, entregado, pendiente, e1, e2 = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        huella = compra_ventas.datos_de_cancelacion(self.e.vendedor, venta.pk).huella
        for medio in ("", "cheque"):
            with self.assertRaises(ValidationError) as c:
                compra_ventas.cancelar_compra_venta(self.e.vendedor, venta.pk, DatosDeCancelacionDeVenta("otro", "", medio), huella)
            self.assertEqual(codigos(c.exception), ["medio_de_pago_obligatorio"])
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_venta, "abierta")
        self.assertEqual((self.estado_de(Entrega, e2).estado_orden, self.estado_de(DetalleVenta, pendiente).estado_detalle_venta), ("a_realizar", "abierto"))
        self.assertEqual(PagoCliente.objects.count(), 0)

    def test_ext_6a_sin_entregas_concretadas_el_medio_de_pago_no_se_admite(self):
        """6a.2: sin entregas concretadas no hay nada que cobrar: un medio de pago se rechaza con `medio_no_admitido` y la venta no se cancela."""
        v = self.todo()
        huella = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk).huella
        with self.assertRaises(ValidationError) as c:
            compra_ventas.cancelar_compra_venta(self.e.vendedor, v.venta.pk, DatosDeCancelacionDeVenta("otro", "", "efectivo"), huella)
        self.assertEqual(codigos(c.exception), ["medio_no_admitido"])
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")
        self.assertIsNone(compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk).cobro)

    def test_ext_6a_sin_entregas_concretadas_la_venta_sigue_quedando_cancelada_y_sin_pago(self):
        """Lo que no cambia: sin entregas concretadas la venta queda «cancelada» y no se crea ningún pago (regla «Asientos»: sin cobro, sin pago)."""
        v = self.todo()
        self.cancelar(self.e.vendedor, v)
        self.assertEqual((CompraVenta.objects.get(pk=v.venta.pk).estado_venta, PagoCliente.objects.count()), ("cancelada", 0))

    def test_ext_6a_el_resumen_muestra_el_cobro_y_el_estado_final_concretada(self):
        """Paso 6 con 6a: el resumen dice «Concretada (se cobra lo entregado)» y trae el cobro con el medio; sin medio, se rechaza con `medio_de_pago_obligatorio` (la misma validación que la confirmación)."""
        venta, _, _, e1, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        resumen = compra_ventas.resumen_de_cancelacion_de_venta(self.e.vendedor, venta.pk, DatosDeCancelacionDeVenta("otro", "", "efectivo"))
        self.assertEqual((resumen.estado_final, resumen.datos.cobro.total), ("Concretada (se cobra lo entregado)", self.monto_de(e1)))
        with self.assertRaises(ValidationError) as c:
            compra_ventas.resumen_de_cancelacion_de_venta(self.e.vendedor, venta.pk, DatosDeCancelacionDeVenta("otro"))
        self.assertEqual(codigos(c.exception), ["medio_de_pago_obligatorio"])

    def test_ext_6a_la_cancelacion_no_toca_la_entrega_concretada_ni_su_monto(self):
        """Lo entregado no se deshace: la entrega concretada conserva su estado, su monto total y su fecha de resolución."""
        venta, _, _, e1, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        antes = Entrega.objects.filter(pk=e1.pk).values("estado_orden", "monto_total_entrega", "fecha_resolucion_orden").get()
        self.cancelar_con_cobro(self.e.vendedor, venta)
        self.assertEqual(Entrega.objects.filter(pk=e1.pk).values("estado_orden", "monto_total_entrega", "fecha_resolucion_orden").get(), antes)

    def test_ext_6a_si_cancela_el_gerente_el_aviso_al_vendedor_dice_lo_que_se_cobro(self):
        """Postcondición h con 6a (aviso): «CV-… cancelada» al Vendedor, con «Se cobró lo entregado: $ … en efectivo.»; el Gerente no se avisa a sí mismo."""
        venta, _, _, e1, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        self.cancelar_con_cobro(self.gerente, venta, "efectivo")
        (aviso,) = [a for a in self.avisos(self.e.vendedor) if a.titulo == f"{venta.codigo} cancelada"]
        self.assertIn(f"Se cobró lo entregado: {texto_de_pesos(self.monto_de(e1))} en efectivo.", aviso.detalle)
        self.assertEqual(self.avisos(self.gerente), [])

    def test_ext_6a_la_auditoria_incluye_el_pago_y_el_paso_de_la_venta_a_concretada(self):
        """Postcondición i con 6a (D-36): el pago entre los afectados y `cambios.estado_venta` de «abierta» a «concretada» con la fecha de concreción; el monto, en `datos`."""
        venta, _, _, e1, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        self.cancelar_con_cobro(self.e.vendedor, venta, "transferencia")
        pago = PagoCliente.objects.get()
        registro = RegistroAuditoria.objects.get(accion="cancelacion_compra_venta")
        self.assertTrue(any(a["modelo"] == "comercial.pagocliente" and a["id"] == pago.pk for a in registro.afectados))
        self.assertEqual(registro.detalle["cambios"]["estado_venta"], {"antes": "abierta", "despues": "concretada"})
        self.assertEqual(registro.detalle["cambios"]["fecha_concrecion_venta"]["despues"], f"{HOY:%d/%m/%Y}")
        self.assertIn(str(self.monto_de(e1)), registro.detalle["datos"]["pago_de_lo_entregado"])

    def test_ext_6a_el_comprobante_de_cancelacion_muestra_el_cobro_de_lo_entregado(self):
        """Postcondición g con 6a: el comprobante (el correo y la página imprimible, `datos_del_comprobante`) tiene la sección «Cobro de lo entregado»: cada entrega con su monto, el total y el medio."""
        venta, _, _, e1, _ = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        with override_settings(CORREO_CONFIGURADO=True):
            self.cancelar_con_cobro(self.e.vendedor, venta, "tarjeta_debito")
        cobro = compra_ventas.datos_del_comprobante(CompraVenta.objects.get(pk=venta.pk))["cancelacion"].cobro
        self.assertEqual((cobro.total, cobro.medio, [(f.codigo, f.monto) for f in cobro.entregas]), (self.monto_de(e1), "Tarjeta de débito", [(e1.codigo, self.monto_de(e1))]))
        (correo_enviado,) = mail.outbox
        self.assertIn("Cobro de lo entregado", correo_enviado.body)
        self.assertIn(texto_de_pesos(self.monto_de(e1)), correo_enviado.body)
        self.assertIn("Tarjeta de débito", correo_enviado.body)

    def test_ext_6a_un_comprobante_sin_cobro_no_tiene_la_seccion(self):
        """Sin entregas concretadas el comprobante de cancelación sigue como antes: sin sección de cobro."""
        v = self.todo()
        with override_settings(CORREO_CONFIGURADO=True):
            self.cancelar(self.e.vendedor, v)
        self.assertIsNone(compra_ventas.datos_del_comprobante(CompraVenta.objects.get(pk=v.venta.pk))["cancelacion"].cobro)
        self.assertNotIn("Cobro de lo entregado", mail.outbox[0].body)

    def test_ext_8a_una_entrega_que_se_concreta_mientras_tanto_cambia_el_monto_a_cobrar_y_no_se_registra_nada(self):
        """Extensión 8a con 6a (la huella suma la lista de entregas concretadas y su monto): si la otra entrega se concreta entre el resumen y la confirmación, `venta_cambio` (o `venta_no_cancelable`, si esa
        concreción cerró la venta): no se cobra el monto viejo ni se cancela nada."""
        venta, _, pendiente, e1, e2 = self.venta_con_una_entrega_concretada(fecha_de_la_segunda=HOY + timedelta(days=1))
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, venta.pk)
        marcar_concretada(e2)
        antes = (RegistroAuditoria.objects.count(), Notificacion.objects.count())
        with self.assertRaises(ValidationError) as c:
            compra_ventas.cancelar_compra_venta(self.e.vendedor, venta.pk, DatosDeCancelacionDeVenta("otro", "", "efectivo"), datos.huella)
        self.assertEqual(codigos(c.exception), ["venta_cambio"])
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)
        self.assertEqual((PagoCliente.objects.count(), CompraVenta.objects.get(pk=venta.pk).estado_venta), (0, "abierta"))

    def test_d67_4_los_detalles_a_cancelar_son_los_que_no_tienen_linea_en_una_entrega_concretada(self):
        """D-67 punto 4 con datos reales: el detalle confirmado y ya entregado (con línea en una entrega concretada) no se cancela; el que sigue sin entregar sí."""
        venta, entregado, pendiente, e1, e2 = self.venta_con_una_entrega_concretada()
        self.assertEqual(self.estado_de(DetalleVenta, entregado).estado_detalle_venta, "confirmado")
        alcance = compra_ventas._alcance_de_cancelacion(CompraVenta.objects.get(pk=venta.pk), HOY)
        self.assertEqual([d.pk for d in alcance.detalles], [pendiente.pk])
        self.assertEqual([e.pk for e in alcance.concretadas], [e1.pk])
        self.assertEqual([e.pk for e in alcance.a_realizar], [e2.pk])
