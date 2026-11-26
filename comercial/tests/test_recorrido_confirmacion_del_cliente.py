# Recorrido de COM-06b de punta a punta con el cliente de Django (D-96; docs/patrones/verificacion_a_mano.md): lo que haría una persona, por rol y por estado, con las pantallas y los servicios reales. Sigue los
# pasos de la «Verificación a mano» de la tarea: el Transportista concreta dos entregas de suministro (llega un solo correo por entrega, con el comprobante y el enlace); el cliente, sin cuenta, abre el primer enlace
# (la URL deja de tener el token), ve su entrega sin perdidas ni costos, prueba los errores del formulario y presenta dos quejas (el acuse trae sus números); el Gerente tiene dos alertas y el Vendedor, dos avisos;
# el enlace no sirve dos veces; con el segundo el cliente dice que no la recibió y el Gerente, desde la ficha del suministro, atiende la entrega («No llegó, producto perdido»); un enlace vencido por el parámetro
# no sirve. Todo con formularios comunes (sin JavaScript) y con los correos y avisos reales.
# No reemplaza la «Verificación a mano» del estudiante: lo que solo un navegador ve (CSRF real, `Origin`, JavaScript, el ancho de un celular) va como paso de «navegador real» en el «Cierre» de la tarea.

import re
from datetime import timedelta
from html import unescape

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, EnlaceCliente, Entrega, Queja
from comercial.tests.fabricas import (
    detalle_suministro,
    enlace_de_confirmacion,
    entrega,
    escenario_comercial,
    marcar_concretada,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta, ConfiguracionOperativa
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
PORTAL = "/cliente/enlace/"
LISTO = "/cliente/enlace/listo/"


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


def huella_de(respuesta):
    """La huella del resumen que la pantalla manda en un campo oculto."""
    html = respuesta.content.decode()  # crudo: la huella es JSON y la plantilla escapa sus comillas (&quot;)
    i = html.index('name="huella" value="') + len('name="huella" value="')
    return unescape(html[i : html.index('"', i)])


@override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
class RecorridoDeConfirmacionDelClienteTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        self.cliente_web = Client()  # el cliente: sin cuenta, otro navegador
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    def entrega_de_suministro(self, cantidad=100):
        """Una entrega de un suministro nuevo del cliente, para hoy y con el transportista (mínimo 50, plazo de pago de 15 días)."""
        contrato = suministro(self.e, plazo_pago=15)
        det = detalle_suministro(contrato, self.e.variedad, cantidad=cantidad, minima=50, primera_en_dias=0)
        reserva = reserva_lista(None, self.lote, cantidad, fecha_entrega=det.fecha_primer_entrega, detalle_suministro=det)
        return contrato, entrega(contrato, [reserva], transportista=self.t, fecha=HOY)

    def concretar(self, e):
        """El Transportista concreta con la pantalla (resumen y confirmación) y con los correos que salen al confirmar. Devuelve el correo del comprobante."""
        self.client.force_login(self.t)
        linea = e.lineas.get().pk
        datos = {f"llego_{linea}": "100", f"recibio_{linea}": "100", "sin_envases": "1"}
        resumen = self.client.post(reverse("comercial:entrega_concretar_calcular", args=[e.pk]), datos)
        antes = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("comercial:entrega_concretar", args=[e.pk]), {**datos, "huella": huella_de(resumen)})
        nuevos = [m for m in mail.outbox[antes:] if m.subject.startswith("Comprobante de tu entrega")]
        self.assertEqual(len(nuevos), 1, "un solo correo por entrega: el comprobante con el enlace")
        return nuevos[0]

    def test_recorrido_de_la_concrecion_a_la_atencion_de_la_entrega_no_reconocida(self):
        # ---- datos de la «Verificación a mano»: dos suministros del mismo cliente, con una entrega de hoy cada uno, con el mismo transportista y la ruta iniciada ----
        contrato_a, e_a = self.entrega_de_suministro()
        contrato_b, e_b = self.entrega_de_suministro()
        self.client.force_login(self.t)
        pagina = self.client.get(reverse("comercial:ruta_iniciar"))
        self.client.post(reverse("comercial:ruta_iniciar"), {"huella": huella_de(pagina)})

        # ---- 1. el Transportista concreta las dos: llega un solo correo por entrega, con el comprobante y el enlace ----
        correo_a, correo_b = self.concretar(e_a), self.concretar(e_b)
        patron = re.compile(r"https://sitio\.test/cliente/([\w-]+)/")
        token_a, token_b = patron.search(correo_a.body).group(1), patron.search(correo_b.body).group(1)
        self.assertNotEqual(token_a, token_b)
        for correo, e in ((correo_a, e_a), (correo_b, e_b)):
            self.assertEqual(correo.to, [self.e.cliente.email_cliente])
            self.assertIn("Vence el pago", correo.body)
            self.assertIn(f"{HOY + timedelta(days=3):%d/%m/%Y}", correo.body)  # hasta cuándo sirve el enlace: 3 días desde la concreción
            enlace = EnlaceCliente.objects.get(entrega=e.pk)
            self.assertEqual((enlace.estado, enlace.estado_envio, enlace.fecha_vencimiento), ("vigente", "enviado", None))
            self.assertEqual(Entrega.objects.get(pk=e.pk).estado_confirmacion_cliente, "no_confirmado")

        # ---- 2. el cliente abre el primer enlace: la URL deja de tener el token; ve cantidades, precio, monto, total y vencimiento, y no las perdidas ----
        abierta = self.cliente_web.get(f"/cliente/{token_a}/", follow=True)
        self.assertEqual(abierta.redirect_chain, [(PORTAL, 302)])
        self.assertNotIn(token_a, abierta.request["PATH_INFO"])
        html = texto(abierta)
        for esperado in (e_a.codigo, contrato_a.codigo, str(self.e.variedad), "100 entregadas", "Total de la entrega", f"{Entrega.objects.get(pk=e_a.pk).fecha_vencimiento_pago:%d/%m/%Y}"):
            self.assertIn(esperado, html)
        for prohibido in ("perdid", "pérdid", "costo"):
            self.assertNotIn(prohibido, html.lower())
        self.assertNotIn('name="queja_retraso"', html)  # llegó a tiempo: no hay retraso para quejarse
        self.assertIn('name="queja_estado_mercaderia"', html)

        # ---- 3. «Recibí pero tengo quejas»: una de «Estado de la mercadería» sin motivo da error; con motivo, junto con una de «Otro», se envían ----
        linea = e_a.lineas.get().pk
        sin_motivo = self.cliente_web.post(PORTAL, {"accion": "revisar", "respuesta": "con_quejas", "queja_estado_mercaderia": "1", "lineas_estado_mercaderia": [linea], "motivo_estado_mercaderia": ""})
        self.assertIn("El motivo es obligatorio para este tipo de queja.", texto(sin_motivo))
        datos = {
            "respuesta": "con_quejas",
            "queja_estado_mercaderia": "1", "lineas_estado_mercaderia": [linea], "motivo_estado_mercaderia": "Llegó con las hojas golpeadas.",
            "queja_otro": "1", "lineas_otro": [linea], "motivo_otro": "Faltó el remito.",
        }
        resumen = texto(self.cliente_web.post(PORTAL, {"accion": "revisar", **datos}))
        self.assertIn("presenta 2 quejas", resumen)
        self.assertEqual(Queja.objects.count(), 0)  # el resumen no registra nada
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            enviado = self.cliente_web.post(PORTAL, {"accion": "confirmar", **datos})
        self.assertRedirects(enviado, LISTO, fetch_redirect_response=False)
        quejas = list(Queja.objects.order_by("numero"))
        self.assertEqual([(q.tipo_queja, q.estado_solicitud) for q in quejas], [("estado_mercaderia", "pendiente"), ("otro", "pendiente")])
        final = texto(self.cliente_web.get(LISTO))
        self.assertIn("Gracias. Recibimos su respuesta.", final)
        for q in quejas:
            self.assertIn(q.codigo, final)
        (acuse,) = mail.outbox
        self.assertEqual(acuse.to, [self.e.cliente.email_cliente])
        for q in quejas:
            self.assertIn(f"{q.codigo}: {q.get_tipo_queja_display()}", acuse.body)
        self.assertEqual(Entrega.objects.get(pk=e_a.pk).estado_confirmacion_cliente, "confirmado")

        # ---- el Gerente tiene dos alertas (con el enlace a la ficha del suministro) y el Vendedor, dos avisos ----
        alertas_de_quejas = Alerta.objects.filter(tipo_alerta="comercial_queja", estado_alerta="activa")
        self.assertEqual((alertas_de_quejas.count(), {a.para_gerente for a in alertas_de_quejas}), (2, {True}))
        self.assertEqual(AlertaComercial.objects.filter(solicitud__in=quejas).count(), 2)
        avisos = [n for n in Notificacion.objects.filter(destinatario=self.e.vendedor).order_by("pk") if "queja" in n.detalle.lower()]
        self.assertEqual(len(avisos), 2)
        self.assertIn(quejas[0].codigo, avisos[0].detalle)

        # ---- 4. volver a abrir el enlace: «ya no se puede usar», con el contacto del Vendedor ----
        otra = self.cliente_web.get(f"/cliente/{token_a}/", follow=True)
        self.assertContains(otra, "Este enlace no se puede usar")
        self.assertContains(otra, "ya se usó")
        self.assertContains(otra, self.e.vendedor.email)

        # ---- 5. con la otra entrega: «No recibí la entrega» con motivo: alerta crítica para el Gerente ----
        otro_navegador = Client()
        otro_navegador.get(f"/cliente/{token_b}/", follow=True)
        sin_motivo = otro_navegador.post(PORTAL, {"accion": "revisar", "respuesta": "no_recibi", "motivo_no_recibi": ""})
        self.assertIn("el motivo es obligatorio", texto(sin_motivo))
        datos = {"respuesta": "no_recibi", "motivo_no_recibi": "No llegó nada a la sucursal de Santo Tomé."}
        self.assertIn("no recibió", texto(otro_navegador.post(PORTAL, {"accion": "revisar", **datos})))
        otro_navegador.post(PORTAL, {"accion": "confirmar", **datos})
        self.assertContains(otro_navegador.get(LISTO), "no reconoce la entrega")
        self.assertEqual(Entrega.objects.get(pk=e_b.pk).estado_confirmacion_cliente, "no_confirmado")
        critica = Alerta.objects.get(tipo_alerta="comercial_entrega_no_reconocida")
        self.assertEqual((critica.nivel_severidad, critica.estado_alerta), ("critica", "activa"))

        # ---- el Gerente, desde la ficha del suministro: «Atender»; el Vendedor no ve el botón ni entra a la pantalla ----
        ficha_b = reverse("comercial:suministro", args=[contrato_b.pk])
        url_b = reverse("comercial:entrega_no_reconocida", args=[e_b.pk])
        self.client.force_login(self.e.vendedor)
        self.assertNotIn(url_b, texto(self.client.get(ficha_b)))
        self.assertEqual(self.client.get(url_b).status_code, 403)
        self.client.force_login(self.gerente)
        self.assertIn(url_b, texto(self.client.get(ficha_b)))
        pantalla = texto(self.client.get(url_b))
        for esperado in ("No llegó nada a la sucursal de Santo Tomé.", e_b.codigo, "Asiento N.º", "Sin cobro registrado", "100"):
            self.assertIn(esperado, pantalla)
        resuelta = self.client.post(url_b, {"resultado": "no_llego_perdido", "descripcion": "Hablé con el cliente y con el chofer: se perdió."}, follow=True)
        self.assertEqual(resuelta.redirect_chain, [(ficha_b, 302)])
        critica.refresh_from_db()
        self.assertEqual(critica.estado_alerta, "resuelta")
        self.assertEqual(AlertaComercial.objects.get(alerta=critica).resultado_averiguacion, "no_llego_perdido")
        self.assertFalse(any("no llegó al cliente (producto perdido)" in n.detalle for n in Notificacion.objects.filter(destinatario=self.e.vendedor)))  # CON-04d (D-85 punto 8): el Vendedor ya no recibe este aviso; sin Contador, el Gerente que atiende tampoco (H21)
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=["respuesta_cliente_entrega", "atencion_entrega_no_reconocida"]).count(), 3)

        # ---- la ficha del cliente informa las quejas pendientes ----
        self.assertIn("Quejas pendientes", texto(self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk]))))

        # ---- 6. el parámetro de vigencia: una entrega con el enlace sin usar de hace más días de los que dice el parámetro deja de servir ----
        contrato_c, e_c = self.entrega_de_suministro()
        marcar_concretada(e_c)
        Entrega.objects.filter(pk=e_c.pk).update(fecha_resolucion_orden=HOY - timedelta(days=2))
        _, token_c = enlace_de_confirmacion(e_c)
        self.assertContains(Client().get(f"/cliente/{token_c}/", follow=True), "Confirme la recepción de su entrega")  # con 3 días de vigencia, todavía sirve
        configuracion = ConfiguracionOperativa.objects.get_or_create(singleton=1)[0]
        configuracion.dias_vigencia_enlace_confirmacion = 1
        configuracion.save()
        vencido = Client().get(f"/cliente/{token_c}/", follow=True)
        self.assertContains(vencido, "El plazo para confirmar la entrega terminó")
