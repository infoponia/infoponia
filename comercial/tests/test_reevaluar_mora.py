# Pruebas de `cobranza.reevaluar_mora` de COM-08a (paso 3) y de la prueba mínima del registrante del enlace de la alerta «pago en mora» (`docs/api/alertas.md`, sección 8): cada fila de «Quién la llama» con su
# efecto, la alerta (tipo, destinatario, severidad, clase, clave, descripción), la fecha del primer aviso, el correo al cliente una sola vez, el aviso al Vendedor, el invernadero dado de baja, la alerta nueva
# después de una resolución y el enlace. Los servicios que llaman a `reevaluar_mora` (cobro, anulación de un cobro, aceptar y anular una resolución) se prueban en sus propios archivos.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («La mora»), D-94 puntos 5 y 6, COM-VNC-PAG (reglas 2 a 5 y postcondiciones a a d), MD-122, MD-125, D-69 punto 4, D-62.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `reevaluar_mora(entrega, hoy, avisar_vendedor) -> Alerta | None` (no bloquea ni audita; la llama quien ya bloqueó el invernadero y la entrega);
# `enviar_aviso_de_mora(entrega_id) -> bool` (fuera de una transacción, solo desde `pendiente_envio`); `enlaces_de_alertas(usuario, alertas)` (el registrante del enlace); `TIPO_PAGO_EN_MORA`;
# la alerta lleva `clave_estado = "entrega:<id>"`, `para_gerente`, severidad crítica y un `AlertaComercial(entrega=…)`.

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from comercial.models import Entrega, LineaPago, PagoCliente
from comercial.servicios import cobranza
from comercial.tests.base_cobranza import HOY, BaseDeCobranza
from comercial.tests.fabricas import cobro, discrepancia, discrepancia_aceptada, queja
from maestros.extensiones import Enlace
from maestros.models import Alerta, Invernadero
from maestros.servicios import alertas as servicio_de_alertas


class ReevaluarMoraTests(BaseDeCobranza):
    def reevaluar(self, e, *, avisar=False, hoy=HOY, correo=True):
        """Llama a `reevaluar_mora` con la entrega releída, ejecuta los `on_commit` (con el correo del sistema configurado) y devuelve la alerta."""
        with override_settings(CORREO_CONFIGURADO=correo), self.captureOnCommitCallbacks(execute=True):
            return cobranza.reevaluar_mora(Entrega.objects.get(pk=e.pk), hoy, avisar)

    def entrega(self, e):
        return Entrega.objects.get(pk=e.pk)

    # ---- la alerta ----

    def test_regla_una_entrega_en_mora_asegura_la_alerta_del_gerente(self):
        """D-94 punto 6: tipo `comercial_pago_en_mora`, destinatario Gerente, severidad crítica, `Clase.ESTADO` con clave `entrega:<id>`, en el invernadero de origen, con su `AlertaComercial(entrega)`."""
        e = self.en_mora()
        alerta = self.reevaluar(e)
        self.assertIsInstance(alerta, Alerta)
        self.assertEqual(alerta.tipo_alerta, cobranza.TIPO_PAGO_EN_MORA)
        self.assertEqual(cobranza.TIPO_PAGO_EN_MORA, "comercial_pago_en_mora")
        self.assertEqual((alerta.para_gerente, alerta.agronomo_id, alerta.nivel_severidad, alerta.estado_alerta), (True, None, "critica", "activa"))
        self.assertEqual((alerta.clave_estado, alerta.invernadero_id), (f"entrega:{e.pk}", e.invernadero_id))
        self.assertEqual([v.alerta_id for v in self.alertas_de(e)], [alerta.pk])

    def test_regla_la_descripcion_dice_la_entrega_el_cliente_el_contrato_el_monto_el_vencimiento_y_el_atraso_por_dia(self):
        """D-94 punto 6: «OT-0231 · Pérez SA · SUM-0013 · $ 1.000,00 · venció el 18/11 · $ 300,00 por día de atraso»."""
        e = self.en_mora()
        alerta = self.reevaluar(e)
        contrato = e.contrato_entrega
        esperado = f"{e.codigo} · {self.e.cliente.nombre_visible} · {contrato.codigo} · $ 1.000,00 · venció el {e.fecha_vencimiento_pago:%d/%m} · $ 300,00 por día de atraso"
        self.assertEqual(alerta.descripcion_alerta, esperado)

    def test_post_d_con_una_discrepancia_pendiente_la_alerta_lo_aclara(self):
        """Postcondición d de COM-VNC-PAG: « · Tiene una discrepancia pendiente (SR-…)»."""
        e = self.en_mora()
        solicitud = discrepancia(e)
        alerta = self.reevaluar(e)
        self.assertTrue(alerta.descripcion_alerta.endswith(f" · Tiene una discrepancia pendiente ({solicitud.codigo})"))

    def test_post_d_con_una_queja_pendiente_la_alerta_lo_aclara(self):
        """Postcondición d de COM-VNC-PAG: « · Tiene una queja pendiente (SR-…)»."""
        e = self.en_mora()
        solicitud = queja(e)
        alerta = self.reevaluar(e)
        self.assertTrue(alerta.descripcion_alerta.endswith(f" · Tiene una queja pendiente ({solicitud.codigo})"))

    def test_regla_la_descripcion_no_pasa_del_largo_de_la_alerta(self):
        """La alerta de `maestros` admite 200 caracteres (la API recorta): un cliente de razón social larguísima no rompe nada."""
        e = self.en_mora()
        type(self.e.cliente).objects.filter(pk=self.e.cliente.pk).update(razon_social_cliente="X" * 150)
        alerta = self.reevaluar(e)
        self.assertLessEqual(len(alerta.descripcion_alerta), 200)

    def test_regla_2_dos_veces_es_la_misma_alerta_activa(self):
        """Regla 2 de COM-VNC-PAG: una sola alerta por entrega aunque el proceso se repita (`asegurar_alerta_de_estado` es idempotente)."""
        e = self.en_mora()
        primera = self.reevaluar(e)
        segunda = self.reevaluar(e)
        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(len(self.alertas_de(e)), 1)

    # ---- la fecha del primer aviso y el correo al cliente ----

    def test_regla_5_la_primera_vez_guarda_la_fecha_del_aviso_y_no_la_cambia(self):
        """D-94 punto 5: `fecha_aviso_mora` se carga con `hoy` la primera vez que asegura la alerta y no vuelve a cambiar."""
        e = self.en_mora()
        self.reevaluar(e, hoy=HOY)
        self.reevaluar(e, hoy=self.dentro_de(5))
        self.assertEqual(self.entrega(e).fecha_aviso_mora, HOY)

    def test_regla_3_el_correo_al_cliente_sale_una_sola_vez(self):
        """Regla 3 de COM-VNC-PAG y D-94 punto 5: el correo de mora sale la primera vez; las siguientes, solo la alerta."""
        e = self.en_mora()
        self.reevaluar(e)
        self.reevaluar(e)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual((mail.outbox[0].to, self.entrega(e).estado_aviso_mora), ([self.e.cliente.email_cliente], "enviado"))

    def test_post_c_el_correo_dice_la_entrega_el_monto_el_vencimiento_y_el_atraso_por_dia(self):
        """Postcondición c: la entrega, el monto a cobrar, la fecha de vencimiento y la indemnización por día de atraso del contrato."""
        e = self.en_mora()
        self.reevaluar(e)
        cuerpo = mail.outbox[0].body
        for esperado in (e.codigo, e.contrato_entrega.codigo, "1.000,00", f"{e.fecha_vencimiento_pago:%d/%m/%Y}", "300,00"):
            self.assertIn(esperado, cuerpo)
        self.assertIn(e.codigo, mail.outbox[0].subject)

    def test_post_d_con_una_solicitud_pendiente_el_correo_dice_que_la_empresa_la_esta_revisando(self):
        """Regla 5 de COM-VNC-PAG y postcondición d: si la solicitud se acepta, el monto puede bajar."""
        e = self.en_mora()
        discrepancia(e)
        self.reevaluar(e)
        self.assertIn("revisando", mail.outbox[0].body)
        self.assertIn("puede bajar", mail.outbox[0].body)

    def test_regla_4_sin_el_correo_del_sistema_queda_pendiente_sin_intentar(self):
        """Sin el correo del sistema configurado no se intenta enviar: `pendiente_envio` (lo reintenta el paso 30, parte 2)."""
        e = self.en_mora()
        self.reevaluar(e, correo=False)
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("pendiente_envio", 0))

    def test_regla_4_si_el_correo_falla_queda_pendiente_y_la_alerta_permanece(self):
        """Regla 4: si falla, se reintenta; la alerta y la fecha del aviso quedan."""
        e = self.en_mora()
        with mock.patch("core.correo.enviar_correo", return_value=False):
            alerta = self.reevaluar(e)
        self.assertEqual((self.entrega(e).estado_aviso_mora, self.entrega(e).fecha_aviso_mora), ("pendiente_envio", HOY))
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_regla_4_si_el_cliente_no_tiene_correo_no_se_envia(self):
        """Regla 4: sin correo, `sin_correo` y nada que enviar."""
        e = self.en_mora()
        type(self.e.cliente).objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        self.reevaluar(e)
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("sin_correo", 0))

    def test_regla_4_el_envio_de_un_aviso_solo_sale_desde_pendiente(self):
        """`enviar_aviso_de_mora` no manda de nuevo un correo ya enviado ni uno sin correo; devuelve si salió."""
        e = self.en_mora()
        self.reevaluar(e)
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertFalse(cobranza.enviar_aviso_de_mora(e.pk))
        self.assertEqual(len(mail.outbox), 1)

    def test_regla_4_el_reintento_manda_el_correo_pendiente(self):
        """`enviar_aviso_de_mora` desde `pendiente_envio` manda el correo y lo pasa a `enviado`."""
        e = self.en_mora()
        self.reevaluar(e, correo=False)
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertTrue(cobranza.enviar_aviso_de_mora(e.pk))
        self.assertEqual((self.entrega(e).estado_aviso_mora, len(mail.outbox)), ("enviado", 1))

    # ---- el aviso al Vendedor ----

    def test_post_b_con_avisar_vendedor_el_vendedor_recibe_el_aviso(self):
        """Postcondición b de COM-VNC-PAG: «OT-… en mora» con el cliente, el contrato, el monto, el vencimiento y lo que suma por día; sin enlace (D-42)."""
        e = self.en_mora()
        self.reevaluar(e, avisar=True)
        (aviso,) = self.avisos(self.e.vendedor, f"{e.codigo} en mora")
        esperado = f"{self.e.cliente.nombre_visible} no pagó {e.codigo} ({e.contrato_entrega.codigo}): $ 1.000,00, venció el {e.fecha_vencimiento_pago:%d/%m}. Desde hoy suma $ 300,00 por día de atraso."
        self.assertEqual(aviso.detalle, esperado)

    def test_post_b_el_aviso_del_vendedor_aclara_la_solicitud_pendiente(self):
        """Regla 5: « Tiene una queja pendiente.» al final del aviso."""
        e = self.en_mora()
        queja(e)
        self.reevaluar(e, avisar=True)
        (aviso,) = self.avisos(self.e.vendedor, f"{e.codigo} en mora")
        self.assertTrue(aviso.detalle.endswith(" Tiene una queja pendiente."))

    def test_regla_sin_avisar_vendedor_no_hay_aviso(self):
        """D-94 punto 5: la anulación de un cobro o de una resolución no avisa (su propio aviso ya dice qué entregas quedan en mora)."""
        e = self.en_mora()
        self.reevaluar(e, avisar=False)
        self.assertEqual(self.avisos(self.e.vendedor, f"{e.codigo} en mora"), [])

    def test_regla_un_vendedor_inactivo_no_recibe_el_aviso_ni_rompe_nada(self):
        """El aviso es «si está activo»: el Vendedor inactivo no recibe nada y la alerta se crea igual."""
        e = self.en_mora()
        type(self.e.vendedor).objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        alerta = self.reevaluar(e, avisar=True)
        self.assertIsNotNone(alerta)
        self.assertEqual(self.avisos(self.e.vendedor), [])

    # ---- lo que resuelve ----

    def test_regla_una_entrega_pagada_resuelve_su_alerta(self):
        """Fila `registrar_cobro` de «Quién la llama»: con el cobro hecho, la alerta activa se resuelve y la función devuelve `None`."""
        e = self.en_mora()
        alerta = self.reevaluar(e)
        cobro([e])
        self.assertIsNone(self.reevaluar(e))
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIsNotNone(alerta.fecha_resolucion)

    def test_regla_una_entrega_saldada_resuelve_su_alerta(self):
        """Fila `resolver_solicitud`, MD-125: una aceptación que deja el monto a cobrar en 0 resuelve la alerta."""
        e = self.en_mora()
        alerta = self.reevaluar(e)
        discrepancia_aceptada(e, monto="1000.00", descontado="1000.00")
        self.assertIsNone(self.reevaluar(e))
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")

    def test_regla_una_entrega_pendiente_no_tiene_alerta_ni_aviso(self):
        """Una entrega que todavía no venció: nada que asegurar, ni fecha de aviso ni correo."""
        e = self.concretada()
        self.assertIsNone(self.reevaluar(e, avisar=True))
        self.assertEqual((self.alertas_de(e), self.entrega(e).fecha_aviso_mora, len(mail.outbox), self.avisos(self.e.vendedor)), ([], None, 0, []))

    def test_regla_sin_alerta_previa_resolver_no_falla(self):
        """«Nada si no había»: pagada sin alerta activa devuelve `None` sin error."""
        e = self.concretada()
        cobro([e])
        self.assertIsNone(self.reevaluar(e))

    # ---- la alerta nueva (D-69 punto 4) ----

    def test_regla_si_la_entrega_vuelve_a_estar_en_mora_se_asegura_una_alerta_nueva_sin_correo(self):
        """Filas `anular_cobro` y `anular_resolucion`: la alerta resuelta no se reabre (D-69 punto 4): se asegura otra del mismo tipo y clave, sin correo ni aviso (`fecha_aviso_mora` ya estaba cargada)."""
        e = self.en_mora()
        primera = self.reevaluar(e, avisar=True)
        pago = cobro([e])
        self.reevaluar(e)
        PagoCliente.objects.filter(pk=pago.pk).update(estado_pago="anulado")
        LineaPago.objects.filter(pago=pago).update(vigente=False)
        nueva = self.reevaluar(e, avisar=False)
        self.assertNotEqual(nueva.pk, primera.pk)
        self.assertEqual((len(self.alertas_de(e)), len(self.alertas_de(e, activas=True)), len(self.alertas_de(e, activas=False))), (2, 1, 1))
        self.assertEqual(len(mail.outbox), 1)  # el correo al cliente no se repite (postcondición e de COM-ANL-CBR)
        self.assertEqual(len(self.avisos(self.e.vendedor, f"{e.codigo} en mora")), 1)

    # ---- el invernadero dado de baja ----

    def test_regla_con_el_invernadero_de_baja_no_hay_alerta_pero_el_aviso_y_el_correo_salen(self):
        """D-94 punto 6: la API no crea la alerta (devuelve `None`); el aviso al Vendedor y el correo al cliente salen igual."""
        e = self.en_mora()
        Invernadero.objects.filter(pk=e.invernadero_id).update(estado_invernadero="inactivo")
        self.assertIsNone(self.reevaluar(e, avisar=True))
        self.assertEqual(self.alertas_de(e), [])
        self.assertEqual((self.entrega(e).fecha_aviso_mora, len(mail.outbox)), (HOY, 1))
        self.assertEqual(len(self.avisos(self.e.vendedor, f"{e.codigo} en mora")), 1)


class EnlaceDeLaAlertaTests(BaseDeCobranza):
    """El registrante del enlace (`docs/api/alertas.md`, sección 8): solo el Gerente la recibe; lleva a «Registrar cobro» con la entrega ya elegida (1a de COM-REG-CBR)."""

    def alerta(self, e):
        with override_settings(CORREO_CONFIGURADO=False):
            return cobranza.reevaluar_mora(Entrega.objects.get(pk=e.pk), HOY, False)

    def test_regla_el_gerente_va_a_registrar_el_cobro_con_la_entrega_elegida_y_el_detalle_de_la_mora(self):
        """Regla 3 de COM-VNC-PAG: la pantalla muestra los días de atraso y la indemnización acumulada, calculados al mostrarla: «En mora desde el 19/11 · 3 días · $ 900,00 por atraso»."""
        e = self.en_mora(dias_de_mora=3)
        alerta = Alerta.objects.select_related("invernadero").get(pk=self.alerta(e).pk)
        enlaces = servicio_de_alertas.enlaces_de_alertas(self.gerente, [alerta])
        desde = e.fecha_vencimiento_pago + timedelta(days=1)
        self.assertEqual(
            enlaces[alerta.pk],
            Enlace(f"{reverse('comercial:cobranza_registrar')}?entrega={e.pk}", f"En mora desde el {desde:%d/%m} · 3 días · $ 900,00 por atraso"),
        )

    def test_regla_con_un_solo_dia_de_atraso_dice_un_dia(self):
        """El singular: «1 día»."""
        e = self.en_mora(dias_de_mora=1)
        alerta = Alerta.objects.select_related("invernadero").get(pk=self.alerta(e).pk)
        enlace = servicio_de_alertas.enlaces_de_alertas(self.gerente, [alerta])[alerta.pk]
        self.assertIn(" · 1 día · $ 300,00 por atraso", enlace.detalle)

    def test_regla_el_vendedor_no_recibe_enlace_propio(self):
        """El Gerente es el único destinatario: para otro usuario el registrante no devuelve nada y queda el enlace por omisión (nunca un 403)."""
        e = self.en_mora()
        alerta = Alerta.objects.select_related("invernadero").get(pk=self.alerta(e).pk)
        self.assertEqual(cobranza.enlaces_de_alertas(self.e.vendedor, [alerta]), {})

    def test_regla_sin_alertas_no_consulta_la_base(self):
        """Lista vacía: `{}` sin consultas."""
        with self.assertNumQueries(0):
            self.assertEqual(cobranza.enlaces_de_alertas(self.gerente, []), {})

    def test_regla_una_consulta_por_registrante_igual_con_una_y_con_tres_alertas(self):
        """Sin consultas por alerta: la misma cantidad con una que con tres."""
        una = [Alerta.objects.select_related("invernadero").get(pk=self.alerta(self.en_mora()).pk)]
        with CaptureQueriesContext(connection) as pocas:
            cobranza.enlaces_de_alertas(self.gerente, una)
        mas = una + [Alerta.objects.select_related("invernadero").get(pk=self.alerta(self.en_mora()).pk) for _ in range(2)]
        with CaptureQueriesContext(connection) as muchas:
            resultado = cobranza.enlaces_de_alertas(self.gerente, mas)
        self.assertEqual((len(pocas), len(resultado)), (len(muchas), 3))
