# Pruebas de COM-VNC-PAG · Vencer Pagos de Suministro (COM-08a, paso 4): `cobranza.vencer_pagos(hoy)`, el paso diario 30. Una por regla (1 a 10; la 7 y la 8, como lo que NO hace) y por postcondición (a a e), dos
# ejecuciones el mismo día y al día siguiente (nada se repite), una entrega pagada, una saldada, una de compra-venta y una con vencimiento hoy (no entran), un contrato resuelto o finalizado (entra), el invernadero
# dado de baja, el cliente sin correo, el reintento del correo, una entrega que falla sin frenar a las demás y el paso 30 en `pasos_diarios()` entre el 27 y el 33.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («COM-VNC-PAG», «Paso diario 30»), D-94 puntos 5 a 7, D-56 punto 4 (idempotente; una transacción por unidad; `hoy` como parámetro), MD-122, MD-125, MD-132, MD-139.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `vencer_pagos(hoy) -> ResumenDePaso(procesados, creados, resueltos, detalle)`, con `procesados` = entregas que entraron en la revisión (parte 1),
# `creados` = alertas creadas, `resueltos` = 0 y `detalle` = «N correos de mora pendientes» (los que siguen pendientes después del reintento de la parte 2); el paso se registra con el código `vencer_pagos`
# y el orden 30; el logger de las fallas es `infoponia.cobranza`; la auditoría `vencimiento_pago` va sin usuario, con la entrega y la alerta como afectados.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from comercial.models import Entrega, LineaPago, PagoCliente, Suministro
from comercial.servicios import cobranza
from comercial.tests.base_cobranza import HOY, BaseDeCobranza
from comercial.tests.base_solicitudes import poner_estado
from comercial.tests.fabricas import (
    cobro,
    compra_venta,
    detalle,
    discrepancia,
    detalle_suministro,
    discrepancia_aceptada,
    entrega,
    entrega_concretada,
    queja,
    reserva_lista,
    suministro,
)
from core.models import RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from maestros.models import Alerta, Invernadero

D = Decimal


class ComVncPagServicioTests(BaseDeCobranza):
    def correr(self, hoy=HOY, correo=True):
        """Corre el paso 30 con el correo del sistema configurado y ejecuta los `on_commit` (los correos de mora salen después de confirmar)."""
        with override_settings(CORREO_CONFIGURADO=correo), self.captureOnCommitCallbacks(execute=True):
            return cobranza.vencer_pagos(hoy)

    def entrega(self, e):
        return Entrega.objects.get(pk=e.pk)

    # ---- regla 1: qué entra ----

    def test_regla_1_una_entrega_vencida_sin_pagar_entra(self):
        """Regla 1: suministro concretado, sin pagar, con monto a cobrar > 0 y `fecha_vencimiento_pago < hoy`: genera su alerta y queda avisada."""
        e = self.en_mora()
        resumen = self.correr()
        self.assertEqual(len(self.alertas_de(e, activas=True)), 1)
        self.assertEqual(self.entrega(e).fecha_aviso_mora, HOY)
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 1, 0))

    def test_regla_1_el_dia_del_vencimiento_todavia_se_puede_pagar_sin_atraso(self):
        """Regla 1: la entrega con vencimiento hoy no entra; al día siguiente, sí."""
        e = self.concretada(plazo_pago=10, hace_dias=10)  # vence hoy
        self.assertEqual(e.fecha_vencimiento_pago, HOY)
        self.correr(HOY)
        self.assertEqual((self.alertas_de(e), self.entrega(e).fecha_aviso_mora), ([], None))
        self.correr(self.dentro_de(1))
        self.assertEqual(len(self.alertas_de(e, activas=True)), 1)
        self.assertEqual(self.entrega(e).fecha_aviso_mora, self.dentro_de(1))

    def test_regla_1_una_entrega_pagada_no_entra(self):
        """No entran las entregas con un cobro vigente."""
        e = self.en_mora()
        cobro([e])
        resumen = self.correr()
        self.assertEqual((self.alertas_de(e), self.entrega(e).fecha_aviso_mora, resumen.procesados), ([], None, 0))

    def test_regla_1_una_entrega_saldada_no_entra(self):
        """MD-125: con el monto a cobrar en 0 la entrega está saldada: no genera alerta «pago en mora»."""
        e = self.en_mora()
        discrepancia_aceptada(e, monto="1000.00", descontado="1000.00")
        self.correr()
        self.assertEqual((self.alertas_de(e), self.entrega(e).fecha_aviso_mora), ([], None))

    def test_regla_6_una_entrega_de_compra_venta_no_entra(self):
        """Regla 6: las entregas de compra-venta no tienen vencimiento del pago ni mora."""
        venta = compra_venta(self.e, dias=0)
        reserva = reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)
        de_venta = entrega_concretada(venta, [reserva], con_pago=True)
        resumen = self.correr()
        self.assertEqual((self.alertas_de(de_venta), resumen.procesados), ([], 0))

    def test_regla_6_un_contrato_resuelto_o_finalizado_entra_porque_la_deuda_sigue(self):
        """Regla 6: sí entran las entregas de contratos finalizados o resueltos."""
        for estado in ("resuelto", "finalizado"):
            with self.subTest(estado=estado):
                e = self.en_mora()
                poner_estado(Suministro.objects.get(pk=e.contrato_entrega_id), estado)
                self.correr()
                self.assertEqual(len(self.alertas_de(e, activas=True)), 1)

    def test_regla_6_una_entrega_a_realizar_no_entra(self):
        """Solo las concretadas tienen vencimiento: una entrega de suministro «a realizar» no entra."""
        contrato = suministro(self.e)
        d = detalle_suministro(contrato, self.e.variedad, cantidad=10, primera_en_dias=0)
        a_realizar = entrega(contrato, [reserva_lista(None, self.lote, 10, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d)])
        resumen = self.correr(self.dentro_de(60))
        self.assertEqual((self.alertas_de(a_realizar), resumen.procesados), ([], 0))

    # ---- reglas 2 y 3: una sola vez ----

    def test_regla_2_una_sola_alerta_por_entrega_aunque_el_proceso_se_repita(self):
        """Regla 2: dos corridas el mismo día dejan una sola alerta activa por entrega."""
        e = self.en_mora()
        self.correr()
        self.correr()
        self.assertEqual(len(self.alertas_de(e)), 1)

    def test_regla_3_ni_la_alerta_ni_el_aviso_ni_el_correo_se_repiten(self):
        """Regla 3, también al día siguiente: la alerta sigue activa hasta el cobro; el aviso al Vendedor y el correo al cliente salen una sola vez; la segunda corrida no revisa nada."""
        e = self.en_mora()
        self.correr()
        segunda = self.correr()
        tercera = self.correr(self.dentro_de(1))
        self.assertEqual((segunda.procesados, segunda.creados, tercera.procesados, tercera.creados), (0, 0, 0, 0))
        self.assertEqual((len(self.alertas_de(e, activas=True)), len(mail.outbox), len(self.avisos(self.e.vendedor, f"{e.codigo} en mora"))), (1, 1, 1))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="vencimiento_pago").count(), 1)
        self.assertEqual(self.entrega(e).fecha_aviso_mora, HOY)

    def test_regla_3_la_alerta_activa_se_ve_con_los_dias_de_atraso_calculados_al_mostrarla(self):
        """Regla 3: la alerta no se reescribe cada día: sus días de atraso y su indemnización se calculan al mostrarla (el enlace). La descripción guardada es la del primer día."""
        e = self.en_mora()
        self.correr()
        antes = self.alertas_de(e)[0].alerta.descripcion_alerta
        self.correr(self.dentro_de(4))
        self.assertEqual(self.alertas_de(e)[0].alerta.descripcion_alerta, antes)

    # ---- postcondiciones ----

    def test_post_a_la_alerta_es_del_gerente_y_trae_el_cliente_el_contrato_el_monto_el_vencimiento_y_el_atraso_por_dia(self):
        """Postcondición a: alerta «pago en mora» para el Gerente, asociada a la entrega, con los datos pedidos."""
        e = self.en_mora()
        self.correr()
        (vinculo,) = self.alertas_de(e)
        alerta = vinculo.alerta
        self.assertEqual((alerta.tipo_alerta, alerta.para_gerente, alerta.nivel_severidad), ("comercial_pago_en_mora", True, "critica"))
        for esperado in (self.e.cliente.nombre_visible, e.contrato_entrega.codigo, "$ 1.000,00", f"{e.fecha_vencimiento_pago:%d/%m}", "$ 300,00 por día de atraso"):
            self.assertIn(esperado, alerta.descripcion_alerta)

    def test_post_b_se_notifica_al_vendedor_del_contrato(self):
        """Postcondición b: el Vendedor del contrato recibe el aviso «OT-… en mora»."""
        e = self.en_mora()
        self.correr()
        self.assertEqual(len(self.avisos(self.e.vendedor, f"{e.codigo} en mora")), 1)

    def test_post_c_el_cliente_recibe_un_correo_una_sola_vez(self):
        """Postcondición c: el correo con la entrega, el monto, el vencimiento y la indemnización por día, al correo del cliente."""
        e = self.en_mora()
        self.correr()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.e.cliente.email_cliente])
        for esperado in (e.codigo, "1.000,00", "300,00"):
            self.assertIn(esperado, mail.outbox[0].body)
        self.assertEqual(self.entrega(e).estado_aviso_mora, "enviado")

    def test_post_d_con_una_queja_o_una_discrepancia_pendiente_la_alerta_y_el_correo_lo_aclaran(self):
        """Postcondición d y regla 5: vence igual y lo dice la alerta y el correo."""
        for hacer, texto in ((discrepancia, "discrepancia"), (queja, "queja")):
            with self.subTest(texto=texto):
                mail.outbox.clear()
                e = self.en_mora()
                solicitud = hacer(e)
                self.correr()
                self.assertIn(f"Tiene una {texto} pendiente ({solicitud.codigo})", self.alertas_de(e)[0].alerta.descripcion_alerta)
                self.assertIn("revisando", mail.outbox[0].body)

    def test_post_e_la_auditoria_la_escribe_infoponia_con_la_entrega_y_la_alerta(self):
        """Postcondición e y D-27: UN registro `vencimiento_pago` por entrega, sin usuario (origen InfoPonia), con la entrega y la alerta como afectados."""
        e = self.en_mora()
        self.correr()
        registro = RegistroAuditoria.objects.get(accion="vencimiento_pago")
        alerta = self.alertas_de(e)[0].alerta
        self.assertIsNone(registro.usuario_id)
        self.assertEqual(registro.rol, "infoponia")
        self.assertTrue(any(a["id"] == e.pk and a["texto"] == e.codigo for a in registro.afectados))
        self.assertTrue(any(a["id"] == alerta.pk for a in registro.afectados))
        self.assertEqual(registro.detalle["cambios"]["fecha_aviso_mora"]["despues"], HOY.isoformat())
        self.assertEqual((registro.detalle["datos"]["entrega"]["id"], registro.detalle["datos"]["alerta"]["id"]), (e.pk, alerta.pk))

    # ---- reglas 4 y 5: el correo ----

    def test_regla_4_si_el_correo_falla_se_reintenta_en_la_corrida_siguiente(self):
        """Regla 4 (parte 2 del paso): el primer intento falla (`pendiente_envio`); el paso siguiente lo reintenta y pasa a `enviado`, una sola vez; el aviso y la alerta no se repiten."""
        e = self.en_mora()
        with mock.patch("core.correo.enviar_correo", return_value=False):
            primera = self.correr()
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox), primera.detalle), ("pendiente_envio", 0, "1 correos de mora pendientes"))
        segunda = self.correr(self.dentro_de(1))
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox), segunda.detalle), ("enviado", 1, "0 correos de mora pendientes"))
        self.assertEqual((len(self.alertas_de(e)), len(self.avisos(self.e.vendedor, f"{e.codigo} en mora"))), (1, 1))

    def test_regla_4_sin_el_correo_del_sistema_queda_pendiente_y_se_envia_cuando_se_configura(self):
        """Sin el correo configurado no se intenta; cuando se configura, el paso lo manda."""
        e = self.en_mora()
        self.correr(correo=False)
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("pendiente_envio", 0))
        self.correr(self.dentro_de(1), correo=True)
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("enviado", 1))

    def test_regla_4_el_reintento_no_toca_las_entregas_que_ya_se_cobraron(self):
        """El reintento es de «las entregas todavía en mora»: una que se cobró mientras tanto no recibe el correo."""
        e = self.en_mora()
        self.correr(correo=False)
        cobro([e])
        self.correr(self.dentro_de(1))
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("pendiente_envio", 0))

    def test_regla_4_si_el_cliente_no_tiene_correo_no_se_envia(self):
        """Regla 4: sin correo, `sin_correo` y nada que enviar; la alerta y el aviso al Vendedor salen igual."""
        e = self.en_mora()
        type(self.e.cliente).objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        self.correr()
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("sin_correo", 0))
        self.assertEqual((len(self.alertas_de(e, activas=True)), len(self.avisos(self.e.vendedor, f"{e.codigo} en mora"))), (1, 1))

    # ---- reglas 7, 8 y 10 ----

    def test_regla_7_y_8_el_paso_no_calcula_ni_registra_la_indemnizacion_ni_toca_el_cobro(self):
        """Reglas 7 y 8 (como lo que no hace): ni cobros ni líneas de pago, y la indemnización por día de la entrega no cambia; la calcula COM-REG-CBR al cobrar."""
        e = self.en_mora()
        self.correr()
        self.assertEqual((PagoCliente.objects.filter(tipo_pago="suministro").count(), LineaPago.objects.count()), (0, 0))
        self.assertEqual(self.entrega(e).indemnizacion_retraso_dia, D("300.00"))

    def test_regla_10_la_fecha_es_el_parametro_y_no_se_lee_dentro(self):
        """Regla 10 y D-56 punto 4: `hoy` es un parámetro: con otro día, una entrega pendiente entra y su fecha de aviso es ese día."""
        e = self.concretada(plazo_pago=10)
        fecha = e.fecha_vencimiento_pago + timedelta(days=2)
        self.correr(HOY)
        self.assertIsNone(self.entrega(e).fecha_aviso_mora)
        self.correr(fecha)
        self.assertEqual(self.entrega(e).fecha_aviso_mora, fecha)

    # ---- el invernadero de baja ----

    def test_regla_con_el_invernadero_de_baja_no_hay_alerta_pero_si_aviso_y_correo(self):
        """D-94 punto 6: la API no crea la alerta; el aviso al Vendedor y el correo al cliente salen igual, y la entrega queda avisada (no se repite mañana)."""
        e = self.en_mora()
        Invernadero.objects.filter(pk=e.invernadero_id).update(estado_invernadero="inactivo")
        self.correr()
        self.assertEqual(self.alertas_de(e), [])
        self.assertEqual((len(self.avisos(self.e.vendedor, f"{e.codigo} en mora")), len(mail.outbox), self.entrega(e).fecha_aviso_mora), (1, 1, HOY))
        self.correr(self.dentro_de(1))
        self.assertEqual((len(self.avisos(self.e.vendedor, f"{e.codigo} en mora")), len(mail.outbox)), (1, 1))

    # ---- una transacción por entrega ----

    def test_regla_si_una_entrega_falla_las_demas_siguen_y_la_que_fallo_no_deja_nada(self):
        """D-56 punto 4: cada entrega en su transacción; si una falla se registra con `logger.exception` y las demás siguen; lo de la que falló se deshace (ni alerta ni fecha de aviso)."""
        primera, segunda = self.en_mora(), self.en_mora()
        original = cobranza.reevaluar_mora

        def falla_la_primera(entrega_, hoy, avisar):
            if entrega_.pk == primera.pk:
                original(entrega_, hoy, avisar)  # alcanza a escribir antes de fallar
                raise RuntimeError("falla de prueba")
            return original(entrega_, hoy, avisar)

        with mock.patch.object(cobranza, "reevaluar_mora", side_effect=falla_la_primera), self.assertLogs("infoponia.cobranza", "ERROR"):
            resumen = self.correr()
        self.assertEqual((self.alertas_de(primera), self.entrega(primera).fecha_aviso_mora), ([], None))
        self.assertEqual(len(self.alertas_de(segunda, activas=True)), 1)
        self.assertEqual((resumen.procesados, resumen.creados, len(mail.outbox)), (2, 1, 1))  # el correo de la que falló se deshizo con su transacción
        # La que falló se reintenta en la próxima corrida (sigue sin `fecha_aviso_mora`).
        self.correr(self.dentro_de(1))
        self.assertEqual(len(self.alertas_de(primera, activas=True)), 1)

    def test_regla_si_falla_la_auditoria_se_deshace_todo_lo_de_esa_entrega(self):
        """Garantía de atomicidad: sin su registro de auditoría no queda la alerta ni la fecha de aviso."""
        e = self.en_mora()
        with mock.patch("comercial.servicios.cobranza.RegistroAuditoria.objects.registrar", side_effect=RuntimeError("falla")), self.assertLogs("infoponia.cobranza", "ERROR"):
            self.correr()
        self.assertEqual((self.alertas_de(e), self.entrega(e).fecha_aviso_mora, len(mail.outbox), Alerta.objects.filter(tipo_alerta="comercial_pago_en_mora").count()), ([], None, 0, 0))

    # ---- el paso en el proceso diario ----

    def test_regla_9_el_paso_esta_registrado_con_el_orden_30_entre_el_27_y_el_33(self):
        """Regla 9 y D-56 punto 6: `vencer_pagos`, «Vencer pagos de suministro», orden 30, después del 27 y antes del 33."""
        pasos = pasos_diarios()
        codigos = [p.codigo for p in pasos]
        paso = next(p for p in pasos if p.codigo == "vencer_pagos")
        self.assertEqual((paso.orden, paso.nombre), (30, "Vencer pagos de suministro"))
        self.assertLess(codigos.index("avisar_enlaces_vencidos"), codigos.index("vencer_pagos"))
        self.assertLess(codigos.index("vencer_pagos"), codigos.index("resolver_suministros"))

    def test_regla_el_comando_proceso_diario_solo_vencer_pagos_corre_el_paso(self):
        """`python manage.py proceso_diario --solo vencer_pagos --fecha AAAA-MM-DD` (la verificación a mano) pone en mora la entrega y, corrido otra vez, no repite nada."""
        e = self.en_mora()
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", solo="vencer_pagos", fecha=HOY.isoformat())
            call_command("proceso_diario", solo="vencer_pagos", fecha=HOY.isoformat())
        self.assertEqual((len(self.alertas_de(e)), len(mail.outbox)), (1, 1))

    def test_regla_el_resumen_es_un_resumen_de_paso(self):
        """`ResumenDePaso` de `core/procesos.py` (el contrato de D-56)."""
        self.assertIsInstance(self.correr(), ResumenDePaso)
