# Pruebas de las vistas de la cobranza (COM-08a, paso 8; docs/casos_de_uso/comercial/cobranza.md, «Pantallas» y «Pruebas»): permisos (el Vendedor solo sus contratos, los demás roles 403, ningún botón lleva a un 403), la pestaña «Cobranza»
# («Por cobrar» y «Cobros registrados») con su contador, «Registrar cobro» (con el cliente de la URL, desde la alerta y 1a1), el cuerpo con HTMX y sin JavaScript, el resumen (`revisar/` no escribe), confirmar (ya pagada, cambió el monto,
# éxito), la ficha del cobro, el comprobante, «Reenviar comprobante», el enlace de la alerta (con la prueba mínima del registrante en `test_reevaluar_mora`), el grupo «Cobranza» del panel y las fichas del suministro y del cliente.
# Verifican en el HTML que los botones y enlaces de acción aparecen **solo** para el rol y el estado que corresponden (D-30). Solo el cliente de Django: lo que ve un navegador (CSRF, `Origin`, JavaScript) va en la «Verificación a mano».
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Pantallas», «Pruebas»), D-30, D-47, D-61, D-94, `.claude/rules/interfaz.md`.

from decimal import Decimal
from html import unescape
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.urls import reverse

from comercial.models import PagoCliente
from comercial.servicios import cobranza, registrantes
from comercial.tests.base_cobranza import HOY, BaseDeCobranza
from comercial.tests.fabricas import cobro, compra_venta, detalle, discrepancia, entrega_concretada, reserva_lista
from maestros.tests.fabricas import crear_transportista, crear_vendedor

D = Decimal


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class BaseDeVistas(BaseDeCobranza):
    def ir(self, nombre, *args, usuario=None, **extra):
        self.client.force_login(usuario or self.gerente)
        return self.client.get(reverse(f"comercial:{nombre}", args=args), **extra)

    def enviar(self, nombre, *args, datos=None, usuario=None, **extra):
        self.client.force_login(usuario or self.gerente)
        return self.client.post(reverse(f"comercial:{nombre}", args=args), datos or {}, **extra)

    def pedido(self, entregas_, medio="transferencia", **extra):
        """Lo que manda el formulario: el cliente, las entregas elegidas y el medio."""
        return {"cliente": str(self.e.cliente.pk), "entrega": [str(e.pk) for e in entregas_], "medio_pago": medio, "cliente_fijo": "1", **extra}


class PermisosTests(BaseDeVistas):
    def test_los_demas_roles_y_los_anonimos_no_entran(self):
        """El Agrónomo, el Capataz y el Transportista reciben 403 en todas las pantallas; un anónimo, la pantalla de ingreso."""
        pago = cobro([self.concretada()])
        for rol in (self.e.agronomo, self.e.capataz, crear_transportista(email="t2@infoponia.com")):
            for nombre, args in (("cobranza", ()), ("cobranza_registrar", ()), ("cobro", (pago.pk,)), ("cobro_comprobante", (pago.pk,))):
                self.assertEqual(self.ir(nombre, *args, usuario=rol).status_code, 403, (rol, nombre))
            self.assertEqual(self.enviar("cobranza_revisar", datos=self.pedido([]), usuario=rol).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("comercial:cobranza")).status_code, 302)

    def test_el_vendedor_ve_solo_sus_contratos_y_el_ajeno_recibe_403_por_url(self):
        """El Vendedor abre la pestaña y ve sus entregas; la ficha del cobro de un contrato ajeno y registrar una entrega ajena son 403."""
        self.concretada()  # sin cobrar: el Vendedor la ve
        pago = cobro([self.concretada()])
        ajeno = crear_vendedor(email="ajeno5@infoponia.com")
        self.assertEqual(self.ir("cobranza", usuario=self.e.vendedor).status_code, 200)
        self.assertIn(self.e.cliente.nombre_visible, texto(self.ir("cobranza", usuario=self.e.vendedor)))
        otra = self.concretada()
        self.assertNotIn(otra.codigo, texto(self.ir("cobranza", usuario=ajeno)))
        self.assertEqual(self.ir("cobro", pago.pk, usuario=ajeno).status_code, 403)
        self.assertEqual(self.ir("cobranza_registrar", usuario=ajeno, QUERY_STRING=f"entrega={otra.pk}").status_code, 403)
        self.assertEqual(self.enviar("cobranza_revisar", datos=self.pedido([otra]), usuario=ajeno).status_code, 403)
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 1)

    def test_un_cobro_de_compra_venta_es_404(self):
        """Su pago se ve en la ficha de la venta."""
        venta = compra_venta(self.e, dias=0)
        entrega_concretada(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], con_pago=True)
        self.assertEqual(self.ir("cobro", venta.pagos.get().pk).status_code, 404)


class PestanaTests(BaseDeVistas):
    def test_por_cobrar_agrupa_por_cliente_con_los_totales_y_el_enlace_a_registrar(self):
        """`tabCobranza` y `cobGroups`: el grupo con el total y lo que está en mora; «Registrar cobro» lleva con el cliente elegido; el texto explicativo y el de los grupos."""
        mora, pendiente = self.en_mora(dias_de_mora=4), self.concretada()
        html = texto(self.ir("cobranza"))
        for esperado in (self.e.cliente.nombre_visible, mora.codigo, pendiente.codigo, "$ 2.000,00", "$ 1.000,00 en mora", "En mora · 4 días", "Pendiente", "hace 4 días",
                         "Las entregas de suministro se cobran después de entregarlas", "las entregas van de la que vence primero a la última", f"?cliente={self.e.cliente.pk}"):
            self.assertIn(esperado, html)
        self.assertNotIn("Anular", html)  # «Anular» es de COM-08b

    def test_sin_deuda_la_pestana_lo_dice(self):
        """Estado vacío."""
        self.assertIn("No hay entregas por cobrar", texto(self.ir("cobranza")))

    def test_cobros_registrados_lista_el_cobro_con_su_monto_y_el_atraso(self):
        """La subpestaña «Cobros registrados»: el cobro con su fecha, el cliente, las entregas, el medio, el monto con «incluye $ … por atraso» y el estado; con un enlace a su ficha."""
        e = self.en_mora(dias_de_mora=2)
        pago = cobro([e], usuario=self.gerente)
        html = texto(self.ir("cobranza", QUERY_STRING="vista=cobros"))
        for esperado in (pago.codigo, e.codigo, "Efectivo", "$ 1.600,00", "incluye $ 600,00 por atraso", "Vigente", reverse("comercial:cobro", args=[pago.pk])):
            self.assertIn(esperado, html)
        self.assertNotIn("Anular", html)

    def test_el_contador_rojo_de_la_pestana_cuenta_las_entregas_en_mora(self):
        """La pestaña «Cobranza» muestra cuántas entregas están en mora (solo si hay)."""
        self.concretada()
        self.assertNotIn("status-danger\">1<", texto(self.ir("cobranza")))
        self.en_mora()
        self.assertIn('status-danger">1<', texto(self.ir("cobranza")))


class RegistrarTests(BaseDeVistas):
    def test_la_pantalla_con_el_cliente_muestra_las_entregas_y_los_textos(self):
        """Con `?cliente=` el cliente queda fijo y aparecen «Entregas que paga» con las entregas del cliente, el atraso de cada una, el resumen y los textos explicativos; «Pago» no aparece hasta elegir una entrega."""
        e = self.en_mora(dias_de_mora=3)
        html = texto(self.ir("cobranza_registrar", QUERY_STRING=f"cliente={self.e.cliente.pk}"))
        for esperado in ("Se registra el cobro de este cliente.", "Entregas que paga", e.codigo, "3 días de atraso · $ 900,00", "Cada entrega se paga completa", "Días de atraso × lo pactado por día", "Fuera de esta ronda · contabilidad", "Calcular total"):
            self.assertIn(esperado, html)
        self.assertNotIn("Medio de pago", html)

    def test_con_una_entrega_elegida_aparece_el_pago_y_el_total(self):
        """«Pago» aparece después de elegir una entrega; «Calcular total» (sin JavaScript) redibuja la página con el total y sin escribir nada."""
        e = self.en_mora(dias_de_mora=3)
        respuesta = self.enviar("cobranza_registrar", datos={**self.pedido([e], medio=""), "accion": "calcular"})
        html = texto(respuesta)
        self.assertIn("Medio de pago", html)
        self.assertIn("$ 1.900,00", html)
        self.assertIn("Uno por cobro. El efectivo va a Caja; los demás, a Banco.", html)
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 0)

    def test_con_htmx_solo_viene_el_cuerpo_y_sin_validar(self):
        """Marcar una entrega redibuja el cuerpo (sin la página entera ni errores, aunque falte el medio); los desplegables y las casillas llevan `hx-swap="innerHTML show:none"` y `data-sin-envio-en-curso`."""
        e = self.en_mora()
        respuesta = self.enviar("cobranza_registrar", datos=self.pedido([e], medio=""), HTTP_HX_REQUEST="true")
        html = texto(respuesta)
        self.assertNotIn("<html", html)
        self.assertNotIn("Elegí el medio de pago.", html)
        self.assertIn('hx-swap="innerHTML show:none"', html)
        self.assertIn("data-sin-envio-en-curso", html)

    def test_desde_la_alerta_la_pantalla_abre_con_la_entrega_elegida_y_el_cliente_fijo(self):
        """1a: `?entrega=` deja el cliente de esa entrega y la entrega marcada; el Gerente la cobra con el enlace de la alerta."""
        e = self.en_mora()
        html = texto(self.ir("cobranza_registrar", QUERY_STRING=f"entrega={e.pk}"))
        self.assertIn(f'value="{e.pk}" id="entrega-{e.pk}"', html.replace('"\n', '"'))
        self.assertIn("Se registra el cobro de este cliente.", html)
        self.assertIn(" checked", html.split(f'id="entrega-{e.pk}"')[1].split(">")[0])

    def test_ext_1a1_si_la_entrega_de_la_alerta_ya_esta_pagada_informa_y_termina(self):
        """1a1: vuelve a «Cobranza» con el aviso: el cobro, su fecha y quién lo registró; no abre la pantalla."""
        e = self.en_mora()
        pago = cobro([e], usuario=self.gerente)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("comercial:cobranza_registrar"), {"entrega": e.pk}, follow=True)
        html = texto(respuesta)
        self.assertEqual(respuesta.redirect_chain[0][0], reverse("comercial:cobranza"))
        self.assertIn(pago.codigo, html)
        self.assertIn(f"{HOY:%d/%m/%Y}", html)

    def test_revisar_muestra_el_resumen_y_no_escribe_nada(self):
        """Paso 8: el cliente, las entregas con su monto y su indemnización, el total, el medio y la fecha (la actual); con «Confirmar cobro»; ningún pago, línea ni auditoría."""
        e = self.en_mora(dias_de_mora=5)
        respuesta = self.enviar("cobranza_revisar", datos=self.pedido([e]))
        html = texto(respuesta)
        for esperado in ("Revisá el cobro", e.codigo, "$ 1.000,00", "5 días · $ 1.500,00", "$ 2.500,00", "Transferencia", f"{HOY:%d/%m/%Y}", "Fuera de esta ronda · contabilidad", "Confirmar cobro", 'name="huella"'):
            self.assertIn(esperado, html)
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 0)

    def test_revisar_sin_medio_o_sin_entregas_vuelve_con_el_error_junto_al_campo(self):
        """5a y el medio: el error vuelve a la pantalla (no al resumen) y «Revisar y registrar» no confirma nada."""
        e = self.concretada()
        sin_medio = texto(self.enviar("cobranza_revisar", datos=self.pedido([e], medio="")))
        self.assertIn("Elegí el medio de pago.", sin_medio)
        self.assertNotIn("Confirmar cobro", sin_medio)
        sin_entregas = texto(self.enviar("cobranza_revisar", datos=self.pedido([])))
        self.assertIn("Elegí al menos una entrega.", sin_entregas)

    def test_confirmar_registra_el_cobro_y_lleva_a_su_ficha_con_el_aviso(self):
        """Pasos 10 a 12: registra, manda el comprobante (con `on_commit`) y vuelve a la ficha del cobro con «COB-… registrado»."""
        e = self.en_mora(dias_de_mora=2)
        self.client.force_login(self.e.vendedor)
        datos = self.pedido([e])
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            huella = self.client.post(reverse("comercial:cobranza_revisar"), datos).context["resumen"].huella
            respuesta = self.client.post(reverse("comercial:cobranza_registrar"), {**datos, "accion": "confirmar", "huella": huella}, follow=True)
        pago = PagoCliente.objects.get(tipo_pago="suministro")
        self.assertEqual(respuesta.redirect_chain[-1][0], reverse("comercial:cobro", args=[pago.pk]))
        html = texto(respuesta)
        self.assertIn(f"{pago.codigo} registrado", html)
        self.assertIn("$ 1.600,00", html)
        self.assertEqual((len(mail.outbox), pago.usuario_id), (1, self.e.vendedor.pk))

    def test_ext_10a_si_ya_se_cobro_vuelve_al_paso_4_con_lo_que_paso(self):
        """10a: otra sesión cobró la entrega: vuelve a la pantalla con el cobro, su fecha y quién lo registró, sin la entrega ya cobrada entre las elegibles."""
        e, otra = self.concretada(), self.concretada()
        self.client.force_login(self.gerente)
        datos = self.pedido([e, otra])
        huella = self.client.post(reverse("comercial:cobranza_revisar"), datos).context["resumen"].huella
        previo = cobro([e], usuario=self.e.vendedor)
        respuesta = self.client.post(reverse("comercial:cobranza_registrar"), {**datos, "accion": "confirmar", "huella": huella})
        html = texto(respuesta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(f"{e.codigo} ya está pagada: {previo.codigo}", html)
        self.assertNotIn(f'id="entrega-{e.pk}"', html)
        self.assertIn(f'id="entrega-{otra.pk}"', html)
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 1)

    def test_ext_10b_si_cambio_el_monto_vuelve_al_paso_6_con_los_montos_nuevos(self):
        """10b: se aceptó una discrepancia mientras tanto: vuelve a la pantalla con el aviso del monto anterior y el nuevo y con la entrega todavía elegida; nada registrado."""
        e = self.concretada()
        self.client.force_login(self.gerente)
        datos = self.pedido([e])
        huella = self.client.post(reverse("comercial:cobranza_revisar"), datos).context["resumen"].huella
        from comercial.tests.fabricas import discrepancia_aceptada

        discrepancia_aceptada(e, monto="200.00", descontado="200.00")
        respuesta = self.client.post(reverse("comercial:cobranza_registrar"), {**datos, "accion": "confirmar", "huella": huella})
        html = texto(respuesta)
        self.assertIn("monto a cobrar $ 1.000,00 → $ 800,00", html)
        self.assertIn(f'id="entrega-{e.pk}"', html)
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 0)

    def test_ext_3a_la_pantalla_advierte_la_solicitud_pendiente(self):
        """3a: la advertencia de reintegro y la marca de la solicitud pendiente con su número y fecha."""
        e = self.concretada()
        solicitud = discrepancia(e, minima=12)
        html = texto(self.enviar("cobranza_registrar", datos={**self.pedido([e]), "accion": "calcular"}))
        self.assertIn("Si se acepta después del cobro, la indemnización ya no se descuenta: se reintegra al cliente.", html)
        self.assertIn(f"Discrepancia {solicitud.codigo} pendiente", html)

    def test_un_cliente_no_elegible_no_abre_la_pantalla_de_otro(self):
        """El cliente se elige de la lista de los que tienen deuda: con un id cualquiera, la pantalla queda sin entregas."""
        html = texto(self.ir("cobranza_registrar", QUERY_STRING="cliente=99999"))
        self.assertNotIn("Entregas que paga", html)


class FichaYComprobanteTests(BaseDeVistas):
    def test_la_ficha_muestra_el_cobro_las_entregas_y_el_estado_del_comprobante(self):
        """La ficha: el cobro, sus entregas con lo cobrado y el atraso, quién lo registró; con el comprobante pendiente, «Reenviar comprobante»; sin correo, «Imprimir comprobante»."""
        e = self.en_mora(dias_de_mora=2)
        pago = cobro([e], usuario=self.gerente, aviso="pendiente_envio")
        html = texto(self.ir("cobro", pago.pk))
        for esperado in (pago.codigo, e.codigo, "$ 1.600,00", "2 días · $ 600,00", self.gerente.email, "Pendiente de envío", "Reenviar comprobante", reverse("comercial:cobro_reenviar_comprobante", args=[pago.pk])):
            self.assertIn(esperado, html)
        self.assertNotIn("Imprimir comprobante", html)
        sin = texto(self.ir("cobro", cobro([self.concretada()], aviso="sin_correo").pk))
        self.assertIn("Imprimir comprobante", sin)
        self.assertNotIn("Reenviar comprobante", sin)
        enviado = texto(self.ir("cobro", cobro([self.concretada()], aviso="enviado").pk))
        self.assertNotIn("Reenviar comprobante", enviado)
        self.assertNotIn("Imprimir comprobante", enviado)

    def test_reenviar_comprobante_manda_el_correo_y_vuelve_a_la_ficha(self):
        """11a: «Reenviar comprobante» (POST) manda el correo y vuelve a la ficha con el resultado; un GET no es válido (405)."""
        pago = cobro([self.concretada()], aviso="pendiente_envio")
        self.assertEqual(self.ir("cobro_reenviar_comprobante", pago.pk).status_code, 405)
        with override_settings(CORREO_CONFIGURADO=True):
            respuesta = self.enviar("cobro_reenviar_comprobante", pago.pk, follow=True)
        self.assertEqual(respuesta.redirect_chain[-1][0], reverse("comercial:cobro", args=[pago.pk]))
        self.assertIn("Se envió el comprobante al cliente.", texto(respuesta))
        self.assertEqual(len(mail.outbox), 1)

    def test_reenviar_sin_estar_pendiente_avisa_y_no_manda(self):
        """Un comprobante ya enviado: el mensaje de error y ningún correo."""
        pago = cobro([self.concretada()], aviso="enviado")
        with override_settings(CORREO_CONFIGURADO=True):
            respuesta = self.enviar("cobro_reenviar_comprobante", pago.pk, follow=True)
        self.assertIn("no está pendiente de envío", texto(respuesta))
        self.assertEqual(len(mail.outbox), 0)

    def test_el_comprobante_imprimible_dice_que_es_interno_y_sin_validez_fiscal(self):
        """El comprobante para imprimir: el cobro, sus entregas, el total y el pie «Comprobante interno, sin validez fiscal.»."""
        e = self.en_mora(dias_de_mora=2)
        pago = cobro([e], aviso="sin_correo")
        html = texto(self.ir("cobro_comprobante", pago.pk))
        for esperado in (pago.codigo, e.codigo, "$ 1.600,00", "Comprobante interno, sin validez fiscal.", "Imprimir comprobante"):
            self.assertIn(esperado, html)
        self.assertEqual(self.ir("cobro_comprobante", pago.pk, usuario=crear_vendedor(email="ajeno6@infoponia.com")).status_code, 403)


class PanelYFichasTests(BaseDeVistas):
    def test_el_panel_suma_el_grupo_cobranza_con_tres_indicadores(self):
        """`secComercial`: «Por cobrar» (total y cantidad), «En mora» (total y cantidad) y «Sin confirmar por el cliente», que llevan a la pestaña; el Vendedor, solo los suyos."""
        self.en_mora(), self.concretada()
        for usuario in (self.gerente, self.e.vendedor):
            html = texto(self._panel(usuario))
            for esperado in ("Cobranza", "Por cobrar", "$ 2.000,00", "2 entregas de suministro", "En mora", "$ 1.000,00", "1 entrega", "Sin confirmar por el cliente", "no afecta el cobro", reverse("comercial:cobranza")):
                self.assertIn(esperado, html, usuario)

    def _panel(self, usuario):
        self.client.force_login(usuario)
        return self.client.get("/")

    def test_el_panel_de_otro_vendedor_no_cuenta_lo_ajeno(self):
        """Alcance: un Vendedor sin contratos ve el grupo en cero."""
        self.en_mora()
        ajeno = crear_vendedor(email="ajeno7@infoponia.com")
        seccion = registrantes.seccion_de_entregas(ajeno)
        self.assertEqual(seccion.contexto["entregas"]["cobranza"].por_cobrar_cantidad, 0)

    def test_la_ficha_del_suministro_dice_el_estado_de_pago_y_ofrece_registrar_cobro(self):
        """Regla 7 y 10 de COM-CNS-SUM: «En mora · N días» / «Pagada · COB-…» y «Registrar cobro» solo con entregas sin pagar."""
        e = self.en_mora(dias_de_mora=5)
        html = texto(self.ir("suministro", e.contrato_entrega_id))
        self.assertIn("En mora · 5 días", html)
        self.assertIn("Registrar cobro", html)
        pago = cobro([e])
        html = texto(self.ir("suministro", e.contrato_entrega_id))
        self.assertIn(f"Pagada · {pago.codigo}", html)
        self.assertNotIn("Registrar cobro", html)

    def test_la_ficha_del_cliente_suma_el_estado_de_pago_y_registrar_cobro(self):
        """«Completan el ABM de cliente», punto 4: las entregas sin cobrar con «En mora · N días» y el botón «Registrar cobro»; con todo cobrado, la tarjeta no aparece."""
        e = self.en_mora(dias_de_mora=4)
        html = texto(self.ir("cliente", self.e.cliente.pk))
        self.assertIn("En mora · 4 días", html)
        self.assertIn(f"{reverse('comercial:cobranza_registrar')}?cliente={self.e.cliente.pk}", html)
        cobro([e])
        self.assertNotIn("Entregas sin cobrar", texto(self.ir("cliente", self.e.cliente.pk)))

    def test_la_ficha_de_la_solicitud_muestra_el_cobro_de_la_entrega(self):
        """La ficha de la solicitud: «Pagada · COB-…» con la fecha y quién cobró."""
        e = self.concretada()
        solicitud = discrepancia(e, minima=12)
        pago = cobro([e], usuario=self.gerente)
        html = texto(self.ir("solicitud", solicitud.pk))
        self.assertIn(f"Pagada · {pago.codigo}", html)
        self.assertIn(f"Cobrada el {HOY:%d/%m/%Y}", html)
