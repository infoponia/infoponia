# Pruebas de COM-ANL-RSC, Dejar sin Efecto la Rescisión (COM-03b, paso 5; docs/casos_de_uso/comercial/suministro.md, «COM-ANL-RSC» y «COM-RSC-SUM y COM-ANL-RSC»): una prueba por
# regla y postcondición. La rescisión que se anula la registra `rescindir_suministro` (`test_com_rsc_sum.py`, que también trae la base de estas pruebas).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/suministros.py`:
#   - `dejar_sin_efecto_rescision(actor, suministro_id, motivo, huella) -> Suministro`: ``motivo`` es el texto libre de la regla 1 y ``huella`` la de `huella_de`
#     leída al abrir la ventana (regla 2). Solo el Gerente (`PermissionDenied`).
#   - Errores: `ValidationError` por campo. Campos: `motivo` y `__all__`. Códigos: `motivo_obligatorio` (en blanco), `motivo_largo` (más de 500), `contrato_cambio` (no
#     vigente o huella distinta), `sin_rescision` (vigente sin rescisión acordada) y `rescision_cerrada` (hoy es posterior a la fecha de la última entrega).
#   - Postcondición a: los seis campos de la rescisión vuelven a nulo/vacío (la historia queda en la auditoría) y cada detalle VIGENTE vuelve a `fecha_fin_detalle = None`;
#     los finalizados no se tocan.
#   - Constancia: `enviar_comprobante(contrato, tipo="anulacion_rescision")` (asunto «Rescisión sin efecto de tu suministro SUM-…»); aviso al Vendedor «Rescisión sin
#     efecto» / «El Gerente dejó sin efecto la rescisión de SUM-… ({cliente}). El contrato sigue como estaba.».
#   - Auditoría: acción `anulacion_rescision`; `datos`: `motivo_anulacion` (el texto), `motivo_rescision`, `descripcion_rescision`, `fecha_acuerdo_rescision` y
#     `fecha_ultima_entrega_rescision` de la rescisión que quedó sin efecto y `detalles` (la fecha de fin que tenía cada detalle).

from datetime import timedelta
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.utils import timezone

from comercial.models import Cliente, DetalleSuministro, ReservaStock, Suministro
from comercial.servicios import comprobantes, suministros
from comercial.tests import test_com_rsc_sum as rsc
from comercial.tests.fabricas import partida
from core.models import Notificacion, RegistroAuditoria

HOY = timezone.localdate()
CORREO = rsc.CORREO
en, iso, codigos_de = rsc.en, rsc.iso, rsc.codigos_de


class BaseDeAnulacion(rsc.BaseDeRescision):
    """El contrato de la rescisión, ya rescindido por el Gerente (la última entrega conservada es la del día 10)."""

    def setUp(self):
        super().setUp()
        self.rescindir(self.pedido(motivo="otro", descripcion="Cierra el vivero"))

    def huella(self):
        return suministros.huella_de(self.recargado(self.s))

    def anular(self, motivo="El cliente decidió seguir", actor=None, **forzar):
        """Deja sin efecto la rescisión como ``actor`` (por defecto, el Gerente) con la huella de ahora."""
        return suministros.dejar_sin_efecto_rescision(actor or self.gerente, self.s.pk, motivo, forzar.get("huella", self.huella()))

    def rechazo(self, motivo="El cliente decidió seguir", actor=None, **forzar):
        with self.assertRaises(ValidationError) as contexto:
            self.anular(motivo, actor, **forzar)
        return contexto.exception


class ComAnlRscServicioTests(BaseDeAnulacion):
    """Postcondiciones y reglas de COM-ANL-RSC."""

    def test_post_a_el_suministro_vuelve_a_no_tener_rescision_y_los_detalles_vigentes_a_no_tener_fecha_de_fin(self):
        """Postcondición a: los seis campos de la rescisión quedan nulos/vacíos y cada detalle vigente sin `fecha_fin_detalle`: vuelven a regir todos sus períodos
        hasta la fecha de fin del contrato. Sigue «vigente»."""
        otro = self.otro_detalle(periodo=20, primera_en_dias=5)
        self.assertEqual(self.recargado(self.d).fecha_fin_detalle, en(10))  # (precondición: la rescisión de setUp ya fijó las fechas)
        s = self.recargado(self.s)
        self.assertTrue(s.tiene_rescision_acordada)
        self.anular()
        s = self.recargado(self.s)
        self.assertEqual(
            (s.estado_suministro, s.motivo_rescision, s.descripcion_rescision, s.fecha_acuerdo_rescision, s.fecha_registro_rescision,
             s.fecha_ultima_entrega_rescision, s.fecha_rescision),
            ("vigente", None, "", None, None, None, None),
        )
        self.assertFalse(s.tiene_rescision_acordada)
        self.assertIsNone(self.recargado(self.d).fecha_fin_detalle)
        self.assertEqual(self.recargado(self.d).estado_detalle_suministro, "vigente")
        self.assertEqual(self.recargado(otro).estado_detalle_suministro, "vigente")

    def test_post_a_un_detalle_finalizado_antes_conserva_su_fecha_de_fin(self):
        """Postcondición a: solo los detalles vigentes; un detalle finalizado por una modificación anterior no se toca."""
        finalizado = self.otro_detalle(primera_en_dias=4, estado="finalizado", fecha_fin_detalle=en(11))
        self.anular()
        self.assertEqual(self.recargado(finalizado).fecha_fin_detalle, en(11))

    def test_post_a_ni_la_multa_ni_los_incumplimientos_cambian(self):
        """La rescisión no tocó la multa ni los incumplimientos y dejarla sin efecto tampoco."""
        antes = self.recargado(self.s)
        self.anular()
        despues = self.recargado(self.s)
        self.assertEqual(
            (despues.multa_resolucion, despues.cantidad_incumplimientos, despues.incumplimientos_tolerados),
            (antes.multa_resolucion, antes.cantidad_incumplimientos, antes.incumplimientos_tolerados),
        )

    def test_post_b_la_proxima_pre_reserva_toma_los_periodos_que_entraron_en_la_ventana(self):
        """Postcondición b: no pre-reserva en el momento; la próxima ejecución diaria toma los períodos que entraron en la ventana desde la rescisión (acá,
        el del día 17, que entra a los 3 días; cubierto con una partida de cámara)."""
        from comercial.servicios import pre_reserva

        partida(self.lote, disponible=100, fecha_limite=en(60))
        antes = ReservaStock.objects.filter(detalle_suministro=self.d).count()
        self.anular()
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=self.d).count(), antes)  # no reserva en el momento
        pre_reserva.pre_reservar_suministros(en(3))
        self.assertIn(en(17), {r.fecha_entrega_reserva for r in ReservaStock.objects.filter(detalle_suministro=self.d)})

    def test_regla_se_puede_anular_hasta_el_dia_de_la_ultima_entrega_inclusive(self):
        """Precondición b: la fecha actual no es posterior a la de la última entrega conservada: el mismo día 10 todavía se puede."""
        with self.hoy_mas(10):
            self.anular()
        self.assertIsNone(self.recargado(self.s).motivo_rescision)

    def test_regla_2_pasada_la_ultima_entrega_no_se_registra_nada(self):
        """Regla 2: después de la última entrega conservada (día 11), `rescision_cerrada`; no cambia nada."""
        with self.hoy_mas(11):
            error = self.rechazo()
        self.assertEqual(codigos_de(error, "__all__"), ["rescision_cerrada"])
        self.assertTrue(self.recargado(self.s).tiene_rescision_acordada)
        self.assertEqual(self.recargado(self.d).fecha_fin_detalle, en(10))

    def test_regla_2_si_el_contrato_ya_se_cerro_como_rescindido_es_contrato_cambio(self):
        """Regla 2: el cierre del paso 35 ya lo pasó a «rescindido» (con la huella de antes): `contrato_cambio`."""
        huella = self.huella()
        suministros.cerrar_rescisiones(en(11))
        error = self.rechazo(huella=huella)
        self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])
        self.assertEqual(self.recargado(self.s).estado_suministro, "rescindido")

    def test_regla_2_si_la_huella_cambio_no_se_registra_nada(self):
        """Regla 2: otra operación cambió el contrato después de abrir la ventana: `contrato_cambio`."""
        huella = self.huella()
        Suministro.objects.filter(pk=self.s.pk).update(incumplimientos_tolerados=9)
        error = self.rechazo(huella=huella)
        self.assertEqual(codigos_de(error, "__all__"), ["contrato_cambio"])
        self.assertTrue(self.recargado(self.s).tiene_rescision_acordada)

    def test_regla_2_un_contrato_sin_rescision_acordada_no_se_puede_dejar_sin_efecto(self):
        """Regla 2: vigente pero sin rescisión (ya la anuló otro): `sin_rescision`."""
        self.anular()
        error = self.rechazo(huella=suministros.huella_de(self.recargado(self.s)))
        self.assertEqual(codigos_de(error, "__all__"), ["sin_rescision"])

    def test_regla_1_el_motivo_es_obligatorio_y_de_hasta_500_caracteres(self):
        """Regla 1: motivo obligatorio, en texto libre (en blanco no vale); no pasa de 500 caracteres. No se registra nada."""
        self.assertEqual(codigos_de(self.rechazo(motivo=""), "motivo"), ["motivo_obligatorio"])
        self.assertEqual(codigos_de(self.rechazo(motivo="   "), "motivo"), ["motivo_obligatorio"])
        self.assertEqual(codigos_de(self.rechazo(motivo="x" * 501), "motivo"), ["motivo_largo"])
        self.assertTrue(self.recargado(self.s).tiene_rescision_acordada)
        self.anular(motivo="x" * 500)
        self.assertFalse(self.recargado(self.s).tiene_rescision_acordada)

    def test_regla_solo_el_gerente(self):
        """Actor principal: el Gerente. El Vendedor del contrato y otros roles reciben `PermissionDenied`."""
        for actor in (self.e.vendedor, self.e.agronomo):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.anular(actor=actor)
        self.assertTrue(self.recargado(self.s).tiene_rescision_acordada)

    def test_regla_despues_de_dejarla_sin_efecto_se_puede_volver_a_rescindir_y_modificar(self):
        """Dejar sin efecto devuelve el contrato a «vigente» sin rescisión: se puede modificar (COM-MOD-SUM) y volver a rescindir."""
        self.anular()
        suministros.modificar_suministro(self.e.vendedor, self.s.pk, suministros.CambiosDeSuministro(tolerados="5"), self.huella())
        self.assertEqual(self.recargado(self.s).incumplimientos_tolerados, 5)
        self.rescindir(self.pedido(descripcion="otra vez"))
        self.assertEqual(self.recargado(self.s).descripcion_rescision, "otra vez")


class EfectosTests(BaseDeAnulacion):
    """Postcondiciones c y d: constancia, aviso y auditoría."""

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_c_la_constancia_sale_al_cliente(self):
        """Postcondición c: se le envía al cliente la constancia (asunto «Rescisión sin efecto de tu suministro SUM-…»), fuera de la transacción."""
        with mock.patch(CORREO, return_value=True) as simulado:
            s = self.anular()
        cuenta, asunto, plantilla, contexto = simulado.call_args.args
        self.assertEqual((cuenta.email, asunto), (self.e.cliente.email_cliente, f"Rescisión sin efecto de tu suministro {s.codigo}"))
        self.assertEqual((plantilla, contexto["tipo"]), ("comercial/correos/comprobante_suministro.txt", "anulacion_rescision"))
        self.assertEqual(self.recargado(self.s).estado_comprobante, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_4_si_la_constancia_no_se_puede_enviar_queda_pendiente_de_envio(self):
        """Regla 4: como en COM-RSC-SUM 7a: pendiente de envío, con el aviso al Vendedor."""
        with mock.patch(CORREO, return_value=False):
            s = self.anular()
        self.assertEqual(self.recargado(self.s).estado_comprobante, "pendiente_envio")
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo="Comprobante pendiente de envío", detalle__contains=s.codigo).exists())

    def test_regla_4_un_cliente_sin_correo_deja_la_constancia_para_imprimir(self):
        """Regla 4: como en COM-RSC-SUM 7b: «para imprimir»."""
        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        self.anular()
        self.assertEqual(self.recargado(self.s).estado_comprobante, "para_imprimir")

    def test_post_c_se_notifica_al_vendedor(self):
        """Postcondición c: «El Gerente dejó sin efecto la rescisión de SUM-… ({cliente}). El contrato sigue como estaba.»"""
        s = self.anular()
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Rescisión sin efecto")
        self.assertEqual(aviso.detalle, f"El Gerente dejó sin efecto la rescisión de {s.codigo} ({self.e.cliente}). El contrato sigue como estaba.")

    def test_post_d_un_registro_de_auditoria_con_el_motivo_y_los_datos_de_la_rescision_que_quedo_sin_efecto(self):
        """Postcondición d y D-36: UN registro `anulacion_rescision` del Gerente con el suministro (primero) y sus detalles entre los afectados; en `datos`, el
        motivo de la anulación y los de la rescisión que quedó sin efecto."""
        s = self.anular(motivo="Siguen con el contrato")
        (registro,) = RegistroAuditoria.objects.filter(accion="anulacion_rescision")
        self.assertEqual((registro.usuario_id, registro.afectados[0]["texto"]), (self.gerente.pk, s.codigo))
        self.assertIn(("comercial.detallesuministro", self.d.pk), {(a["modelo"], a["id"]) for a in registro.afectados})
        datos = registro.detalle["datos"]
        self.assertEqual(
            (datos["motivo_anulacion"], datos["motivo_rescision"], datos["descripcion_rescision"], datos["fecha_ultima_entrega_rescision"]),
            ("Siguen con el contrato", "otro", "Cierra el vivero", f"{en(10):%d/%m/%Y}"),
        )
        self.assertTrue(any(f"{en(10):%d/%m/%Y}" in linea for linea in datos["detalles"]))

    def test_regla_una_anulacion_rechazada_no_deja_auditoria_ni_avisos_ni_correo(self):
        """Garantía mínima: rechazada, no queda registro, aviso ni correo."""
        avisos = Notificacion.objects.count()
        with override_settings(CORREO_CONFIGURADO=True), mock.patch(CORREO) as enviar:
            self.rechazo(motivo="")
        enviar.assert_not_called()
        self.assertEqual((RegistroAuditoria.objects.filter(accion="anulacion_rescision").count(), Notificacion.objects.count()), (0, avisos))

    def test_regla_si_la_auditoria_falla_la_rescision_sigue_en_pie(self):
        """Todo en una transacción: si falla, la rescisión queda como estaba."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla de prueba")), self.assertRaises(RuntimeError):
            self.anular()
        self.assertTrue(self.recargado(self.s).tiene_rescision_acordada)
        self.assertEqual(self.recargado(self.d).fecha_fin_detalle, en(10))
