# Pruebas de COM-EVL-DSC · Evaluar Discrepancia (COM-07a, paso 5): `solicitudes.resumen_de_resolucion`, `resolver_solicitud` y `evaluar_discrepancia` con una discrepancia. Una por postcondición (a a k; la e,
# el asiento, es «Fuera de la ronda»: se prueba que NO se crea), por extensión (1a1, 3a, 5a, 5b, 6a, 6b, 6c, 6d, 7a, 8a, 8b, 9a) y por regla. Los datos salen de `BaseDeSolicitudes.armar`: un suministro de 10 plantas
# por período a $100 (mínimo 8, $5 por planta faltante), con la entrega concretada con 5 plantas: monto a cobrar $500,00 e indemnización $15,00 (3 × $5).
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («COM-EVL-DSC», «Registrar la resolución»), MD-114, MD-115, MD-117, D-57, D-69 puntos 2, 8, 9, 12, 13 y 17. Las pruebas numeran las extensiones (`test_ext_6d_…`).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `resumen_de_resolucion(actor, solicitud_id, datos) -> ResumenDeResolucion` (`monto`, `descontado`, `reintegrado`, `monto_a_cobrar_antes/despues`,
# `incumplimientos_antes/despues`, `resolveria`, `historial`, `errores`, `huella`); `resolver_solicitud(actor, solicitud_id, datos, huella)`; `evaluar_discrepancia`; códigos `decision_obligatoria`,
# `observaciones_obligatorias`, `observaciones_largas`, `monto_no_admitido`, `medio_obligatorio`, `solicitud_no_pendiente`, `solicitud_cambio`; `PermissionDenied` y `Http404`.

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, LineaDiscrepancia, SolicitudRevision, Suministro
from comercial.servicios import solicitudes
from comercial.tests.base_solicitudes import BaseDeSolicitudes, HOY, codigos, poner_estado
from comercial.tests.fabricas import queja_aceptada
from contabilidad.models import AsientoContable
from core.models import Notificacion, RegistroAuditoria, Usuario
from maestros.models import Alerta
from produccion.models import Bitacora

D = Decimal


class ComEvlDscServicioTests(BaseDeSolicitudes):
    def contrato(self, x):
        return Suministro.objects.get(pk=x.contrato.pk)

    def solicitud(self, x):
        return SolicitudRevision.objects.get(pk=x.solicitud.pk)

    # ---- el flujo principal y las postcondiciones ----

    def test_flujo_principal_acepta_la_discrepancia_y_descuenta_la_indemnizacion(self):
        """Pasos 6 a 10: el resumen dice $15,00 (3 × $5), que se descuenta y el monto a cobrar pasa de $500,00 a $485,00; al confirmar, la discrepancia queda aceptada."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        self.assertEqual((resumen.monto, resumen.descontado, resumen.reintegrado), (D("15.00"), D("15.00"), D("0.00")))
        self.assertEqual((resumen.monto_a_cobrar_antes, resumen.monto_a_cobrar_despues), (D("500.00"), D("485.00")))
        self.assertEqual((resumen.incumplimientos_antes, resumen.incumplimientos_despues, resumen.tolerados), (0, 1, 3))
        self.assertFalse(resumen.hay_errores)
        resuelta = self.resolver(x.solicitud, observaciones="Se cargó menos de lo pactado.")
        self.assertEqual(resuelta.estado_solicitud, "aceptada")
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("485.00"))

    def test_post_a_la_discrepancia_queda_aceptada_con_fecha_gerente_y_observaciones(self):
        """Postcondición a: de «pendiente» a «aceptada», con la fecha de resolución de hoy, el Gerente y las observaciones (opcionales al aceptar)."""
        x = self.armar()
        self.resolver(x.solicitud, observaciones="Procede.")
        s = self.solicitud(x)
        self.assertEqual((s.estado_solicitud, s.fecha_resolucion, s.gerente_id, s.observaciones_resolucion), ("aceptada", HOY, self.gerente.pk, "Procede."))
        otra = self.armar()
        self.resolver(otra.solicitud)
        self.assertEqual(self.solicitud(otra).observaciones_resolucion, "")

    def test_post_b_la_alerta_de_la_discrepancia_queda_resuelta(self):
        """Postcondición b: la alerta (una sola por solicitud) queda «resuelta»."""
        x = self.armar()
        alerta = Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk)
        self.assertEqual(alerta.estado_alerta, "activa")
        self.resolver(x.solicitud)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIsNotNone(alerta.fecha_resolucion)

    def test_post_c_se_guarda_el_monto_de_la_indemnizacion_y_el_de_cada_linea(self):
        """Postcondición c: Σ (mínima − entregada) × indemnización por planta de la cláusula; con dos líneas, la suma, y cada línea con su monto."""
        x = self.armar(dos_lineas=True, entregada=6, por_planta="7.50")
        self.resolver(x.solicitud)
        s = self.solicitud(x)
        self.assertEqual(s.monto_indemnizacion, D("30.00"))  # 2 × (8 − 6) × 7,50
        self.assertEqual(sorted(LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).values_list("monto_indemnizacion_linea", flat=True)), [D("15.00"), D("15.00")])
        self.assertEqual((s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (D("30.00"), D("0.00"), None))

    def test_post_d_el_contrato_suma_un_incumplimiento_una_sola_vez_aunque_tenga_varias_lineas(self):
        """Postcondición d: la cantidad de incumplimientos aumenta en uno, no uno por línea."""
        x = self.armar(dos_lineas=True, entregada=6, incumplimientos=1)
        self.resolver(x.solicitud)
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 2)

    def test_post_e_no_se_crea_ningun_asiento_fuera_de_la_ronda(self):
        """Postcondición e y precondición c: «Fuera de esta ronda · contabilidad» (D-57): no se exige ejercicio ni cuentas y no se crea un asiento."""
        x = self.armar()
        self.resolver(x.solicitud)
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_post_f_registra_el_evento_en_la_bitacora_del_invernadero_de_origen(self):
        """Postcondición f: un evento «incumplimiento de cláusula suministrante» en el invernadero de origen, sin lote, etapa ni Capataz, con la descripción de la entrega, la línea y el total."""
        x = self.armar()
        self.resolver(x.solicitud)
        evento = Bitacora.objects.get(tipo_evento="incumplimiento_de_clausula")
        self.assertEqual((evento.invernadero_id, evento.lote_id, evento.etapa_id, evento.responsable_id), (x.entrega.invernadero_id, None, None, self.gerente.pk))
        for texto in (x.solicitud.codigo, "Discrepancia", x.entrega.codigo, x.contrato.codigo, "Retiro en invernadero" if not x.entrega.transportista_id else "Transportista", "5 de 8", "$ 15,00", "Total: $ 15,00"):
            self.assertIn(texto, evento.descripcion_evento)

    def test_post_f_la_descripcion_del_evento_no_pasa_de_500_caracteres(self):
        """Postcondición f: con muchas líneas la descripción se recorta («y N más») y entra en 500."""
        x = self.armar(dos_lineas=True)
        s = solicitudes._hija(solicitudes._solicitud(x.solicitud.pk))
        descripcion = solicitudes._descripcion_del_evento(s, x.entrega, x.contrato, solicitudes._armar_lineas(s, x.entrega)[:1] * 40, D("15.00"))
        self.assertLessEqual(len(descripcion), 500)
        self.assertIn("más", descripcion)
        self.assertTrue(descripcion.endswith("Total: $ 15,00"))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_el_cliente_recibe_el_comprobante_y_el_vendedor_el_aviso(self):
        """Postcondición g: el comprobante de indemnización (uso interno) al cliente, con el monto y cómo se aplicó, y una notificación al Vendedor del contrato."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud)
        (correo,) = mail.outbox
        self.assertEqual(correo.to, [self.e.cliente.email_cliente])
        self.assertIn("Comprobante de indemnización", correo.subject)
        for texto in ("$ 15,00", "sin validez fiscal", x.entrega.codigo, "Descontado de lo que debés por la entrega"):
            self.assertIn(texto, correo.body)
        self.assertEqual(self.solicitud(x).estado_aviso_cliente, "enviado")
        (aviso,) = self.avisos(self.e.vendedor, f"{x.solicitud.codigo} aceptada")
        self.assertIn("$ 15,00", aviso.detalle)
        self.assertIn("1 de 3", aviso.detalle)

    def test_post_h_despues_de_confirmar_se_llama_a_resolver_si_corresponde(self):
        """Postcondición h y D-69 punto 13: después del commit, `resoluciones.resolver_si_corresponde(suministro)`; antes del commit no se llamó."""
        x = self.armar()
        with mock.patch("comercial.servicios.resoluciones.resolver_si_corresponde") as resolver:
            with self.captureOnCommitCallbacks(execute=False) as despues:
                self.resolver(x.solicitud)
            resolver.assert_not_called()
            for callback in despues:
                callback()
        resolver.assert_called_once_with(x.contrato.pk)

    def test_post_j_y_k_un_registro_de_auditoria_con_los_cambios_y_los_afectados(self):
        """Postcondiciones j y k: un registro `evaluacion_discrepancia` con el Gerente; afectados: la solicitud (principal), la alerta, el suministro y el evento de bitácora; los cambios y la entrega en los datos."""
        x = self.armar()
        self.resolver(x.solicitud)
        (registro,) = RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia")
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        modelos = [a["modelo"] for a in registro.afectados]
        self.assertEqual(modelos, ["comercial.discrepanciaentrega", "maestros.alerta", "comercial.suministro", "produccion.bitacora"])
        self.assertEqual(registro.afectados[0]["id"], x.solicitud.pk)
        self.assertEqual(registro.detalle["cambios"]["estado_solicitud"], {"antes": "pendiente", "despues": "aceptada"})
        self.assertEqual(registro.detalle["cambios"]["monto_descontado"], {"antes": None, "despues": "15.00"})
        self.assertEqual((registro.detalle["datos"]["monto_a_cobrar_antes"], registro.detalle["datos"]["monto_a_cobrar_despues"]), ("500.00", "485.00"))

    # ---- extensiones ----

    def test_ext_1a1_y_3a_una_discrepancia_ya_resuelta_informa_la_decision_el_gerente_y_la_fecha(self):
        """Extensiones 1a1 y 3a: una discrepancia que ya no está pendiente se rechaza con `solicitud_no_pendiente` y los datos de la decisión tomada."""
        x = self.armar()
        self.resolver(x.solicitud)
        error = self.rechazo(solicitudes.resumen_de_resolucion, self.gerente, x.solicitud.pk, self.datos())
        self.assertEqual(codigos(error), ["solicitud_no_pendiente"])
        params = error.error_dict["__all__"][0].params
        self.assertEqual((params["decision"], params["fecha"]), ("aceptada", f"{HOY:%d/%m/%Y}"))
        self.assertIn(self.gerente.first_name, params["gerente"])

    def test_ext_5a_rechaza_sin_indemnizacion_ni_cambios_en_el_contrato(self):
        """Extensión 5a e i: rechazada con fecha, Gerente y observaciones; sin monto, sin incumplimiento, sin bitácora; la alerta se resuelve; el Vendedor y el cliente reciben el aviso con las observaciones."""
        x = self.armar()
        resumen = self.resumen(x.solicitud, "rechazar", "Fue por el cliente.")
        self.assertEqual((resumen.monto, resumen.incumplimientos_despues), (None, 0))
        self.assertIn("Rechazada", resumen.textos[0])
        with self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud, "rechazar", "Fue por el cliente.")
        s = self.solicitud(x)
        self.assertEqual((s.estado_solicitud, s.gerente_id, s.observaciones_resolucion, s.monto_indemnizacion, s.monto_descontado, s.monto_reintegrado), ("rechazada", self.gerente.pk, "Fue por el cliente.", None, None, None))
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 0)
        self.assertEqual(Bitacora.objects.filter(tipo_evento="incumplimiento_de_clausula").count(), 0)
        self.assertEqual(Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk).estado_alerta, "resuelta")
        (aviso,) = self.avisos(self.e.vendedor, f"{x.solicitud.codigo} rechazada")
        self.assertIn("Fue por el cliente.", aviso.detalle)
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("500.00"))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_5a_el_cliente_recibe_el_aviso_de_que_no_fue_reconocida_con_las_observaciones(self):
        """Extensión 5a.5: el aviso de rechazo al cliente con las observaciones del Gerente."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud, "rechazar", "No corresponde.")
        (correo,) = mail.outbox
        self.assertIn("no fue reconocida", correo.subject)
        self.assertIn("No corresponde.", correo.body)

    def test_ext_5b_rechazar_sin_observaciones_las_pide(self):
        """Extensión 5b: las observaciones son obligatorias al rechazar (y no se escribe nada)."""
        x = self.armar()
        resumen = self.resumen(x.solicitud, "rechazar", "   ")
        self.assertEqual([c for c, _ in resumen.errores["observaciones"]], ["observaciones_obligatorias"])
        error = self.rechazo(self.resolver, x.solicitud, "rechazar", "")
        self.assertEqual((codigos(error), error.error_dict.keys()), (["observaciones_obligatorias"], {"observaciones"}))
        self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")

    def test_regla_observaciones_largas_y_decision_obligatoria(self):
        """Más de 500 caracteres: `observaciones_largas`; sin decisión: `decision_obligatoria`."""
        x = self.armar()
        self.assertEqual(codigos(self.rechazo(self.resolver, x.solicitud, "aceptar", "x" * 501)), ["observaciones_largas"])
        self.assertEqual(codigos(self.rechazo(self.resolver, x.solicitud, "")), ["decision_obligatoria"])
        self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")

    def test_ext_6a_con_la_entrega_pagada_todo_se_reintegra_con_el_medio_elegido(self):
        """Extensión 6a (D-69 punto 8: `estado_de_pago` simulado): pagada ⇒ descontado 0, reintegrado todo, medio obligatorio; el monto a cobrar no cambia."""
        x = self.armar()
        with mock.patch("comercial.servicios.entregas.estado_de_pago", return_value={x.entrega.pk: "pagada"}):
            resumen = self.resumen(x.solicitud)
            self.assertEqual((resumen.descontado, resumen.reintegrado, resumen.necesita_medio), (D("0.00"), D("15.00"), True))
            self.assertEqual(codigos(self.rechazo(self.resolver, x.solicitud)), ["medio_obligatorio"])
            self.assertEqual(self.resumen(x.solicitud, medio="cheque").errores["medio_reintegro"][0][0], "medio_obligatorio")
            self.resolver(x.solicitud, medio="transferencia")
        s = self.solicitud(x)
        self.assertEqual((s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (D("0.00"), D("15.00"), "transferencia"))
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("500.00"))

    def test_ext_6b_si_se_superan_los_tolerados_el_resumen_lo_advierte_y_se_dispara_la_resolucion(self):
        """Extensión 6b: con 3 tolerados y 3 acumulados, el cuarto incumplimiento supera la tolerancia: el resumen advierte la resolución del contrato y la multa; después del commit se llama a COM-RSV-SUM."""
        x = self.armar(tolerados=3, incumplimientos=3)
        resumen = self.resumen(x.solicitud)
        self.assertTrue(resumen.resolveria)
        self.assertEqual(resumen.multa, D("50000.00"))
        self.assertTrue(any("se resolverá" in t and "$ 50.000,00" in t for t in resumen.textos))
        with mock.patch("comercial.servicios.resoluciones.resolver_si_corresponde") as resolver:
            with self.captureOnCommitCallbacks(execute=True):
                self.resolver(x.solicitud)
        resolver.assert_called_once_with(x.contrato.pk)
        self.assertEqual((self.contrato(x).cantidad_incumplimientos, self.contrato(x).estado_suministro), (4, "vigente"))  # estado de paso: COM-07b lo resuelve

    def test_ext_6b_sin_superar_los_tolerados_no_se_advierte(self):
        """Con 3 tolerados y 2 acumulados, la tercera aceptación no resuelve: sin advertencia."""
        resumen = self.resumen(self.armar(tolerados=3, incumplimientos=2).solicitud)
        self.assertEqual((resumen.resolveria, resumen.historial), (False, False))

    def test_ext_6c_con_el_contrato_finalizado_resuelto_o_rescindido_se_registra_como_historial(self):
        """Extensión 6c: el incumplimiento y la indemnización se registran igual, como historial, sin resolución del contrato."""
        for estado in ("finalizado", "resuelto", "rescindido"):
            with self.subTest(estado=estado):
                x = self.armar(tolerados=0, estado_contrato=estado)
                resumen = self.resumen(x.solicitud)
                self.assertEqual((resumen.historial, resumen.resolveria), (True, False))
                self.assertTrue(any("historial" in t for t in resumen.textos))
                self.resolver(x.solicitud)
                self.assertEqual((self.contrato(x).cantidad_incumplimientos, self.solicitud(x).estado_solicitud), (1, "aceptada"))

    def test_ext_6d_si_la_indemnizacion_supera_el_monto_a_cobrar_el_resto_se_reintegra(self):
        """Extensión 6d (MD-115, D-69 punto 2): $600 contra un monto a cobrar de $500: se descuentan $500, queda en $0 (nunca negativo) y $100 se reintegran con el medio; sin medio se pide."""
        x = self.armar(por_planta="200.00")
        resumen = self.resumen(x.solicitud)
        self.assertEqual((resumen.monto, resumen.descontado, resumen.reintegrado, resumen.monto_a_cobrar_despues), (D("600.00"), D("500.00"), D("100.00"), D("0.00")))
        self.assertEqual(codigos(self.rechazo(self.resolver, x.solicitud)), ["medio_obligatorio"])
        self.resolver(x.solicitud, medio="efectivo")
        s = self.solicitud(x)
        self.assertEqual((s.monto_indemnizacion, s.monto_descontado, s.monto_reintegrado, s.medio_reintegro), (D("600.00"), D("500.00"), D("100.00"), "efectivo"))
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([x.entrega.pk])[x.entrega.pk], D("0.00"))

    def test_ext_7a_el_resumen_no_escribe_y_se_puede_pedir_de_nuevo_con_otra_decision(self):
        """Extensión 7a: el Gerente cambia la decisión o la observación: el resumen no escribe nada y el servicio lo recalcula con los datos nuevos."""
        x = self.armar()
        antes = (SolicitudRevision.objects.filter(estado_solicitud="pendiente").count(), RegistroAuditoria.objects.count(), Notificacion.objects.count())
        self.resumen(x.solicitud)
        otra = self.resumen(x.solicitud, "rechazar", "Mejor no.")
        self.assertEqual((otra.decision, otra.observaciones), ("rechazar", "Mejor no."))
        self.assertEqual((SolicitudRevision.objects.filter(estado_solicitud="pendiente").count(), RegistroAuditoria.objects.count(), Notificacion.objects.count()), antes)

    def test_ext_8a_al_registrar_ya_no_esta_pendiente_no_registra_nada(self):
        """Extensión 8a: otra sesión la resolvió mientras tanto: `solicitud_no_pendiente`, sin cambios ni un segundo incumplimiento ni un segundo registro."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        self.resolver(x.solicitud)
        error = self.rechazo(solicitudes.resolver_solicitud, self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        self.assertEqual(codigos(error), ["solicitud_no_pendiente"])
        self.assertEqual((self.contrato(x).cantidad_incumplimientos, RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia").count()), (1, 1))

    def test_ext_8b_si_cambio_un_dato_de_la_huella_no_registra_y_dice_que_cambio(self):
        """Extensión 8b (D-69 punto 12): cambió el estado de pago, el monto a cobrar, los incumplimientos o el estado del contrato desde el resumen: `solicitud_cambio` con qué cambió, sin registrar nada."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        casos = [
            ("incumplimientos", lambda: Suministro.objects.filter(pk=x.contrato.pk).update(cantidad_incumplimientos=1), "los incumplimientos del contrato"),
            ("estado del contrato", lambda: poner_estado(x.contrato, "finalizado"), "el estado del contrato"),
        ]
        for nombre, cambiar, texto in casos:
            with self.subTest(nombre):
                cambiar()
                error = self.rechazo(solicitudes.resolver_solicitud, self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
                self.assertEqual(codigos(error), ["solicitud_cambio"])
                self.assertIn(texto, error.error_dict["__all__"][0].params["cambios"])
                self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")
                self.assertEqual(RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia").count(), 0)
                Suministro.objects.filter(pk=x.contrato.pk).update(cantidad_incumplimientos=0, estado_suministro="vigente")  # vuelve al estado del resumen (y al invariante del contador)

    def test_ext_8b_un_cobro_o_el_estado_de_pago_cambian_la_huella(self):
        """Extensión 8b: si la entrega se cobra (cambia su estado de pago) entre el resumen y la confirmación, la confirmación se rechaza y el resumen nuevo ve la entrega pagada."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        with mock.patch("comercial.servicios.entregas.estado_de_pago", return_value={x.entrega.pk: "pagada"}):
            error = self.rechazo(solicitudes.resolver_solicitud, self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
            self.assertIn("el estado de pago de la entrega", error.error_dict["__all__"][0].params["cambios"])
            nuevo = self.resumen(x.solicitud)
            self.assertTrue(nuevo.lectura.pagada)
            self.assertNotEqual(nuevo.huella, resumen.huella)

    def test_ext_8b_otra_aceptacion_de_la_misma_entrega_cambia_el_monto_a_cobrar(self):
        """Extensión 8b: otra queja aceptada de la misma entrega mientras tanto (baja el monto a cobrar y sube el contador): `solicitud_cambio` con el monto a cobrar entre lo que cambió."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        queja_aceptada(x.entrega, "otro", monto="50.00")
        error = self.rechazo(solicitudes.resolver_solicitud, self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        self.assertIn("el monto a cobrar de la entrega", error.error_dict["__all__"][0].params["cambios"])

    def test_ext_9a_si_el_correo_falla_la_resolucion_permanece_y_el_aviso_queda_pendiente(self):
        """Extensión 9a (D-69 punto 17): la resolución queda registrada con el aviso «pendiente de envío»; después «Reenviar aviso» lo manda y pasa a «enviado»."""
        x = self.armar()
        with override_settings(CORREO_CONFIGURADO=True), mock.patch("core.correo.enviar_correo", return_value=False):
            with self.captureOnCommitCallbacks(execute=True):
                self.resolver(x.solicitud)
        self.assertEqual((self.solicitud(x).estado_solicitud, self.solicitud(x).estado_aviso_cliente), ("aceptada", "pendiente_envio"))
        self.assertEqual(len(self.avisos(self.e.vendedor, f"{x.solicitud.codigo} aceptada")), 1)
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertTrue(solicitudes.reenviar_aviso(self.gerente, x.solicitud.pk))
        self.assertEqual(self.solicitud(x).estado_aviso_cliente, "enviado")
        self.assertEqual(len(mail.outbox), 1)

    def test_ext_9a_sin_el_correo_del_sistema_el_aviso_queda_pendiente_sin_intentar(self):
        """Sin el correo del sistema configurado (D-35) no se intenta enviar: queda «pendiente de envío» (lo reintenta el paso 50)."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud)
        self.assertEqual((self.solicitud(x).estado_aviso_cliente, len(mail.outbox)), ("pendiente_envio", 0))

    def test_ext_9a_un_cliente_sin_correo_queda_sin_correo_y_la_ficha_ofrece_imprimir(self):
        """Un cliente sin correo (un contrato no vigente cuyo cliente quitó el correo): `sin_correo`, no se intenta nada."""
        x = self.armar()
        type(self.e.cliente).objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            self.resolver(x.solicitud)
        self.assertEqual((self.solicitud(x).estado_aviso_cliente, len(mail.outbox)), ("sin_correo", 0))
        self.assertTrue(solicitudes.ficha_de_solicitud(self.gerente, x.solicitud.pk).puede_imprimir)

    def test_ext_9a_el_vendedor_inactivo_no_recibe_aviso(self):
        """D-42: un Vendedor con la cuenta inactiva no recibe la notificación, y la resolución se registra igual."""
        x = self.armar()
        Usuario.objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        self.resolver(x.solicitud)
        self.assertEqual(self.avisos(self.e.vendedor), [])
        self.assertEqual(self.solicitud(x).estado_solicitud, "aceptada")

    # ---- reglas ----

    def test_regla_decision_total_no_admite_un_monto_en_una_discrepancia(self):
        """Regla «Decisión total»: el Gerente acepta o rechaza; no ajusta el monto (`monto_no_admitido`)."""
        x = self.armar()
        error = self.rechazo(self.resolver, x.solicitud, monto="20")
        self.assertEqual((codigos(error), list(error.error_dict)), (["monto_no_admitido"], ["monto"]))

    def test_regla_el_monto_se_guarda_y_no_cambia_aunque_cambie_despues_la_clausula(self):
        """Regla «Monto de la indemnización»: se calcula y se guarda al aceptar; si después cambia la cláusula, el monto guardado y el de la línea no cambian."""
        x = self.armar()
        self.resolver(x.solicitud)
        x.detalle.clausula_suministrante.__class__.objects.filter(detalle=x.detalle).update(indemnizacion_faltante=D("999.00"))
        s = self.solicitud(x)
        self.assertEqual(s.monto_indemnizacion, D("15.00"))
        self.assertEqual(solicitudes.ficha_de_solicitud(self.gerente, s.pk).lectura.lineas[0].monto, D("15.00"))

    def test_regla_la_indemnizacion_usa_la_clausula_vigente_al_aceptar(self):
        """Regla «Monto de la indemnización»: la indemnización por planta es la de la cláusula **al aceptar**; las cantidades, las que la discrepancia copió al generarse."""
        x = self.armar()
        x.detalle.clausula_suministrante.__class__.objects.filter(detalle=x.detalle).update(indemnizacion_faltante=D("10.00"), cantidad_minima=9)
        self.assertEqual(self.resumen(x.solicitud).monto, D("30.00"))  # 3 (de la copia: 8 − 5) × $10

    def test_regla_solo_se_registra_en_bitacora_y_cuenta_al_aceptar(self):
        """Regla «Bitácora» y «Cantidad de incumplimientos»: una rechazada no suma ni deja evento (y una aceptada sí, una sola vez)."""
        rechazada, aceptada = self.armar(), self.armar()
        self.resolver(rechazada.solicitud, "rechazar", "No.")
        self.resolver(aceptada.solicitud)
        self.assertEqual(Bitacora.objects.filter(tipo_evento="incumplimiento_de_clausula").count(), 1)
        self.assertEqual((self.contrato(rechazada).cantidad_incumplimientos, self.contrato(aceptada).cantidad_incumplimientos), (0, 1))

    def test_regla_dos_discrepancias_del_mismo_contrato_suman_dos_incumplimientos(self):
        """El contador se lleva por solicitud aceptada (no por línea): dos aceptadas del mismo contrato, 2."""
        x = self.armar()
        y = self.otra(x)
        self.resolver(x.solicitud)
        self.resolver(y.solicitud)
        self.assertEqual(self.contrato(x).cantidad_incumplimientos, 2)

    def test_regla_solo_el_gerente_activo_resuelve(self):
        """Precondición a y regla «Solo un Gerente»: el Vendedor, el Transportista y un Gerente dado de baja reciben `PermissionDenied`; la solicitud sigue pendiente."""
        x = self.armar()
        for actor in (self.e.vendedor, self.e.agronomo, self.e.capataz):
            with self.assertRaises(PermissionDenied):
                solicitudes.resumen_de_resolucion(actor, x.solicitud.pk, self.datos())
            with self.assertRaises(PermissionDenied):
                solicitudes.resolver_solicitud(actor, x.solicitud.pk, self.datos(), "")
        resumen = self.resumen(x.solicitud)
        Usuario.objects.filter(pk=self.gerente.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            solicitudes.resolver_solicitud(self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        self.assertEqual(self.solicitud(x).estado_solicitud, "pendiente")

    def test_precondicion_una_solicitud_inexistente_o_de_otro_tipo_es_404(self):
        """Un id que no existe da `Http404`; `evaluar_discrepancia` sobre una queja también."""
        x = self.armar(tipo="queja")
        with self.assertRaises(Http404):
            solicitudes.resumen_de_resolucion(self.gerente, 99999999, self.datos())
        with self.assertRaises(Http404):
            solicitudes.evaluar_discrepancia(self.gerente, x.solicitud.pk, self.datos(), "")

    def test_evaluar_discrepancia_es_un_nombre_fino_de_resolver_solicitud(self):
        """`evaluar_discrepancia` verifica el tipo y llama a `resolver_solicitud`."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        resuelta = solicitudes.evaluar_discrepancia(self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        self.assertEqual((resuelta.estado_solicitud, resuelta.tipo_solicitud), ("aceptada", "discrepancia"))

    def test_garantia_la_evaluacion_es_atomica(self):
        """Garantías mínimas: si algo falla a mitad (acá, el evento de bitácora), no queda ningún cambio: la discrepancia sigue pendiente, sin Gerente, con su alerta sin resolver y sin auditoría."""
        x = self.armar()
        resumen = self.resumen(x.solicitud)
        with mock.patch("comercial.servicios.solicitudes.bitacora.registrar_evento_de_contrato", side_effect=RuntimeError("falló")):
            with self.assertRaises(RuntimeError):
                solicitudes.resolver_solicitud(self.gerente, x.solicitud.pk, self.datos(), resumen.huella)
        s = self.solicitud(x)
        self.assertEqual((s.estado_solicitud, s.gerente_id, s.monto_indemnizacion), ("pendiente", None, None))
        self.assertEqual(Alerta.objects.get(vinculo_comercial__solicitud=x.solicitud.pk).estado_alerta, "activa")
        self.assertEqual((self.contrato(x).cantidad_incumplimientos, RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia").count()), (0, 0))
        self.assertEqual(self.avisos(self.e.vendedor), [])

    def test_regla_una_alerta_ya_resuelta_no_se_toca_al_resolver(self):
        """D-69 punto 4: si la alerta ya estaba resuelta (una solicitud reabierta), no se vuelve a resolver ni aparece entre los afectados."""
        x = self.armar()
        Alerta.objects.filter(vinculo_comercial__solicitud=x.solicitud.pk).update(estado_alerta="resuelta", fecha_resolucion=timezone.now())
        self.resolver(x.solicitud)
        (registro,) = RegistroAuditoria.objects.filter(accion="evaluacion_discrepancia")
        self.assertNotIn("maestros.alerta", [a["modelo"] for a in registro.afectados])
        self.assertEqual(AlertaComercial.objects.filter(solicitud_id=x.solicitud.pk).count(), 1)

    def test_regla_el_monto_a_cobrar_de_la_entrega_resta_lo_descontado(self):
        """Lo que completa a COM-06a (D-69 punto 9): el monto a cobrar es el total menos lo **descontado** de las aceptadas, no la indemnización entera."""
        x = self.armar(por_planta="200.00")
        self.resolver(x.solicitud, medio="efectivo")
        entrega = Entrega.objects.get(pk=x.entrega.pk)
        self.assertEqual(entrega.monto_total_entrega, D("500.00"))
        self.assertEqual(solicitudes.entregas.monto_a_cobrar([entrega.pk])[entrega.pk], D("0.00"))  # $600 de indemnización, solo $500 descontados
