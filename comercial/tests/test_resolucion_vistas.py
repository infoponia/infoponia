# Pruebas de la resolución en la ficha y en la lista del suministro y de «Dar por atendida» (COM-07b; docs/casos_de_uso/comercial/resolucion.md, «La resolución en la ficha y en la lista del suministro»
# y «Pruebas»): la ficha y la lista de un suministro resuelto, «Dar por atendida» con y sin JavaScript, el enlace de la alerta en la campana y los permisos (solo el Gerente ve el botón; el Vendedor ve
# el aviso). Con el cliente de prueba de Django, por rol y por estado. Lo que solo un navegador ve (el CSRF real, el foco, el aviso breve) va en la «Verificación a mano».
# Fuente: D-69 (puntos 14 y 15), D-30 (ningún botón lleva a un 403), D-61, COM-CNS-SUM (reglas 4 y 10), MAE-02d; `.claude/rules/interfaz.md`.

from datetime import timedelta
from types import SimpleNamespace

from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, ReservaStock, Suministro
from comercial.servicios import resoluciones
from comercial.tests.fabricas import (
    detalle_suministro,
    entrega,
    escenario_comercial,
    marcar_concretada,
    queja_aceptada,
    reserva_lista,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_resolucion,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.extensiones import enlaces_registrados
from maestros.models import Alerta
from produccion.tests.fabricas import lote_maduro
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


class ResolucionVistasTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un suministro resuelto por incumplimientos (con el caso de uso, no a mano) con una entrega cancelada, su Gerente y su Vendedor."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        for verificar in (verificar_invariantes_de_reservas, verificar_invariantes_de_solicitudes, verificar_invariantes_de_resolucion):
            self.addCleanup(verificar)

    def resuelto(self, *, multa="50000.00"):
        """Un suministro con 3 tolerados y 4 quejas aceptadas, con una entrega «a realizar» que la resolución cancela. Lo resuelve `resolver_suministro` (con sus avisos y su alerta)."""
        contrato = suministro(self.e, tolerados=3, multa=multa)
        d = detalle_suministro(contrato, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=-40, minima=10)
        quejas = []
        for i in range(4):
            fecha = HOY - timedelta(days=40 - 7 * i)
            r = reserva_lista(None, self.lote, 5, fecha_entrega=fecha, detalle_suministro=d)
            concretada = marcar_concretada(entrega(contrato, [r], fecha=fecha), cantidades=[(5, 0, 0)])
            ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="entregada")
            quejas.append(queja_aceptada(concretada, "otro", monto="0.00"))
        r = reserva_lista(None, self.lote, 30, fecha_entrega=HOY + timedelta(days=2), detalle_suministro=d)
        pendiente = entrega(contrato, [r])
        with self.captureOnCommitCallbacks(execute=True):
            resoluciones.resolver_suministro(contrato.pk, HOY)
        return SimpleNamespace(contrato=contrato, detalle=d, quejas=quejas, entrega=pendiente, alerta=Alerta.objects.get(tipo_alerta="comercial_suministro_resuelto"))

    def ficha(self, x, usuario):
        self.client.force_login(usuario)
        return self.client.get(reverse("comercial:suministro", args=[x.contrato.pk]))

    def lista(self, usuario):
        self.client.force_login(usuario)
        return self.client.get(reverse("comercial:contratos"), {"tipo": "suministro"})

    def atender(self, x, usuario):
        self.client.force_login(usuario)
        return self.client.post(reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk]))

    def mensajes(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]

    # ---- la ficha ----

    def test_regla_la_ficha_del_gerente_muestra_la_resolucion_con_la_solicitud_la_multa_y_dar_por_atendida(self):
        """Regla «Ficha»: «Resuelto por incumplimientos el dd/mm/aaaa: 4 de 3 tolerados, por SR-… Multa: $ 50.000,00. Las entregas concretadas se siguen cobrando.», con el enlace a la solicitud y la multa con su asiento (CON-04d);
        el Gerente ve el botón «Dar por atendida» con su texto."""
        x = self.resuelto()
        respuesta = self.ficha(x, self.gerente)
        self.assertEqual(respuesta.status_code, 200)
        for esperado in (
            f"Resuelto por incumplimientos el {HOY:%d/%m/%Y}", "4 de 3", x.quejas[-1].codigo, "$ 50.000,00", "Asiento N.º 1", "Las entregas concretadas se siguen cobrando",
            f"Entregas canceladas: <span class=\"mono\">{x.entrega.codigo}</span>", "Dar por atendida", "Usalo cuando hayas pagado la multa y avisado al cliente. La alerta deja de figurar entre tus pendientes.",
        ):
            self.assertContains(respuesta, esperado)
        self.assertContains(respuesta, reverse("comercial:solicitud", args=[x.quejas[-1].pk]))
        self.assertContains(respuesta, reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk]))
        self.assertContains(respuesta, "Resuelto")  # la insignia del estado

    def test_regla_la_ficha_del_vendedor_muestra_el_aviso_pero_no_el_boton(self):
        """D-30 y regla 10: el Vendedor del contrato ve la resolución y no el botón (que lo llevaría a un 403)."""
        x = self.resuelto()
        respuesta = self.ficha(x, self.e.vendedor)
        self.assertContains(respuesta, "Resuelto por incumplimientos el")
        self.assertNotContains(respuesta, "Dar por atendida")
        self.assertNotContains(respuesta, reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk]))

    def test_regla_un_contrato_resuelto_no_ofrece_modificar_ni_rescindir(self):
        """Regla 10 de COM-CNS-SUM: un suministro resuelto no ofrece «Modificar» ni «Rescindir» (solo «vigente»)."""
        x = self.resuelto()
        respuesta = self.ficha(x, self.gerente)
        self.assertNotContains(respuesta, "Modificar suministro")
        self.assertNotContains(respuesta, "Rescindir suministro")

    def test_regla_con_multa_cero_la_ficha_dice_que_no_hay_multa(self):
        """Extensión 5a: sin multa pactada, la ficha informa que el contrato no prevé multa."""
        x = self.resuelto(multa="0.00")
        self.assertContains(self.ficha(x, self.gerente), "El contrato no prevé multa.")

    def test_regla_un_suministro_vigente_no_muestra_resolucion_ni_boton(self):
        """Un contrato «vigente» no tiene aviso de resolución ni «Dar por atendida»."""
        contrato = suministro(self.e)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("comercial:suministro", args=[contrato.pk]))
        self.assertNotContains(respuesta, "Resuelto por incumplimientos")
        self.assertNotContains(respuesta, "Dar por atendida")

    # ---- la lista ----

    def test_regla_la_lista_marca_para_el_gerente_la_resolucion_sin_atender_y_la_marca_desaparece_al_atenderla(self):
        """Regla «Lista»: el Gerente ve «Resolución sin atender» mientras la alerta esté activa; el Vendedor no la ve; al dar por atendida, desaparece."""
        x = self.resuelto()
        self.assertContains(self.lista(self.gerente), "Resolución sin atender")
        self.assertNotContains(self.lista(self.e.vendedor), "Resolución sin atender")
        self.assertEqual(self.atender(x, self.gerente).status_code, 302)
        respuesta = self.lista(self.gerente)
        self.assertNotContains(respuesta, "Resolución sin atender")
        self.assertContains(respuesta, "Resuelto")

    # ---- «Dar por atendida» ----

    def test_post_dar_por_atendida_resuelve_la_alerta_audita_y_vuelve_a_la_ficha_sin_el_boton(self):
        """Regla «Dar por atendida»: un POST del Gerente resuelve la alerta (con su fecha), deja el registro `atencion_suministro_resuelto` con el suministro y la alerta, avisa y vuelve a la ficha, donde ya no está el botón."""
        x = self.resuelto()
        respuesta = self.atender(x, self.gerente)
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[x.contrato.pk]))
        x.alerta.refresh_from_db()
        self.assertEqual(x.alerta.estado_alerta, "resuelta")
        self.assertIsNotNone(x.alerta.fecha_resolucion)
        (registro,) = RegistroAuditoria.objects.filter(accion="atencion_suministro_resuelto")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual({a["modelo"] for a in registro.afectados}, {"comercial.suministro", "maestros.alerta"})
        self.assertEqual(registro.detalle["datos"]["suministro"]["id"], x.contrato.pk)
        self.assertIn("quedó atendida", " ".join(self.mensajes(respuesta)))
        self.assertNotContains(self.client.get(respuesta.url), "Dar por atendida")

    def test_ext_dar_por_atendida_dos_veces_la_segunda_vuelve_con_el_mensaje_y_sin_otro_registro(self):
        """Código `alerta_resuelta`: una alerta ya atendida no se vuelve a atender; no es un error 500: vuelve a la ficha con el mensaje y no deja otro registro."""
        x = self.resuelto()
        self.atender(x, self.gerente)
        segunda = self.atender(x, self.gerente)
        self.assertEqual(segunda.status_code, 302)
        self.assertIn("ya fue atendida", " ".join(self.mensajes(segunda)))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="atencion_suministro_resuelto").count(), 1)

    def test_regla_solo_el_gerente_puede_dar_por_atendida(self):
        """`sin_permiso`: el Vendedor (aun el del contrato) recibe 403, el servicio también lo rechaza, y la alerta sigue activa."""
        from django.core.exceptions import PermissionDenied

        x = self.resuelto()
        self.assertEqual(self.atender(x, self.e.vendedor).status_code, 403)
        with self.assertRaises(PermissionDenied):
            resoluciones.dar_por_atendida_la_resolucion(self.e.vendedor, x.contrato.pk)
        x.alerta.refresh_from_db()
        self.assertEqual(x.alerta.estado_alerta, "activa")

    def test_regla_dar_por_atendida_es_un_post(self):
        """Un GET no cambia nada (405): la alerta sigue activa."""
        x = self.resuelto()
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("comercial:suministro_dar_por_atendida", args=[x.contrato.pk])).status_code, 405)
        x.alerta.refresh_from_db()
        self.assertEqual(x.alerta.estado_alerta, "activa")

    def test_regla_un_suministro_que_no_existe_da_404(self):
        """Un id que no existe: 404, no un error sin traducir."""
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.post(reverse("comercial:suministro_dar_por_atendida", args=[999999])).status_code, 404)

    def test_regla_sin_javascript_el_boton_es_un_formulario_post_con_su_csrf_y_sin_htmx(self):
        """`.claude/rules/interfaz.md` y la regla «Pantallas»: sin JavaScript, «Dar por atendida» es un formulario con su botón (POST), con la confirmación en la misma página; ni HTMX ni validaciones al tipear."""
        x = self.resuelto()
        html = self.ficha(x, self.gerente).content.decode()
        tarjeta = html[html.index('id="atender-resolucion"'):]
        tarjeta = tarjeta[: tarjeta.index("</form>")]
        self.assertIn('method="post"', tarjeta)
        self.assertIn("csrfmiddlewaretoken", tarjeta)
        self.assertIn('type="submit"', tarjeta)
        self.assertNotIn("hx-", tarjeta)

    # ---- el enlace de la alerta en la campana ----

    def test_regla_el_enlace_de_la_alerta_lleva_al_gerente_a_la_ficha_del_suministro(self):
        """MAE-02d: la alerta «suministro resuelto» lleva al Gerente a la ficha del suministro con el detalle «SUM-… · resuelto · multa $ 50.000,00»; el Vendedor no recibe enlace (no la ve)."""
        x = self.resuelto()
        enlaces = resoluciones.enlaces_de_alertas(self.gerente, [x.alerta])
        self.assertEqual(enlaces[x.alerta.pk].url, reverse("comercial:suministro", args=[x.contrato.pk]))
        self.assertEqual(enlaces[x.alerta.pk].detalle, f"{x.contrato.codigo} · resuelto · multa $ 50.000,00")
        self.assertEqual(resoluciones.enlaces_de_alertas(self.e.vendedor, [x.alerta]), {})
        self.assertEqual(resoluciones.enlaces_de_alertas(self.gerente, []), {})

    def test_regla_el_enlace_esta_registrado_para_el_tipo(self):
        """`ComercialConfig.ready()` registra la función de enlaces para `comercial_suministro_resuelto` (MAE-02d)."""
        self.assertIn(((resoluciones.TIPO_DE_ALERTA,), resoluciones.enlaces_de_alertas), enlaces_registrados())

    def test_regla_la_campana_del_gerente_muestra_la_alerta_con_su_enlace(self):
        """De punta a punta: la alerta llega a la campana del Gerente, con el enlace a la ficha del suministro."""
        x = self.resuelto()
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("core:campana")).content.decode()
        self.assertIn("resuelto por incumplimientos", html)
        self.assertIn(f"SUM-{x.contrato.numero:04d} · resuelto · multa $ 50.000,00", html)
        ir = self.client.get(reverse("alertas:ir", args=[x.alerta.pk]))  # el clic en la campana: lleva a la ficha del suministro
        self.assertRedirects(ir, reverse("comercial:suministro", args=[x.contrato.pk]), fetch_redirect_response=False)

    def test_ext_8a_reenviar_comprobante_de_un_suministro_resuelto_reenvia_el_aviso_de_resolucion(self):
        """Extensión 8a: con el aviso de resolución «pendiente de envío» (el correo no salió), «Reenviar comprobante» de la ficha manda el aviso de resolución (no el comprobante de registro) y lo deja «enviado»."""
        x = self.resuelto()
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_comprobante, "pendiente_envio")  # las pruebas arrancan sin correo configurado
        self.assertContains(self.ficha(x, self.gerente), "Reenviar comprobante")
        with override_settings(CORREO_CONFIGURADO=True):  # ahora el correo del sistema está configurado
            respuesta = self.client.post(reverse("comercial:suministro_reenviar_comprobante", args=[x.contrato.pk]))
        self.assertEqual(respuesta.status_code, 302)
        (correo,) = [m for m in mail.outbox if m.subject == f"Resolución de tu suministro {x.contrato.codigo}"]
        self.assertIn("4 de 3", correo.body)
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_comprobante, "enviado")

    # ---- CON-04d · paso 6, decisión (3) del 26/11/2026 ----

    def test_tarea_con04d_la_ficha_muestra_el_asiento_de_la_multa_sin_enlace_a_quien_ya_ve_el_importe(self):
        """La multa de la ficha ya no dice «fuera de esta ronda»: muestra «Asiento N.º 1» con Debe Indemnizaciones por Resolución de Contratos / Haber Indemnizaciones a Pagar, como texto. La ve el Gerente y el Vendedor del
        contrato (que ya ven la multa); el Agrónomo y el Contador no entran a la ficha (403) y no ven nada."""
        from contabilidad.tests.fabricas import verificar_invariantes_contables  # noqa: F401

        x = self.resuelto()
        for actor in (self.gerente, self.e.vendedor):
            respuesta = self.ficha(x, actor)
            for esperado in ("Asiento N.º 1", "Indemnizaciones por Resolución de Contratos", "Indemnizaciones a Pagar", "$ 50.000,00"):
                self.assertContains(respuesta, esperado)
            self.assertNotContains(respuesta, "fuera de esta ronda")
            self.assertNotRegex(respuesta.content.decode(), r"<a [^>]*>[^<]*Asiento N")
        self.assertEqual(self.ficha(x, self.e.agronomo).status_code, 403)

    def test_tarea_con04d_sin_multa_la_ficha_dice_que_el_contrato_no_preve_multa_y_no_muestra_asiento(self):
        x = self.resuelto(multa="0.00")
        respuesta = self.ficha(x, self.gerente)
        self.assertContains(respuesta, "El contrato no prevé multa.")
        self.assertNotContains(respuesta, "Asiento N.º")
