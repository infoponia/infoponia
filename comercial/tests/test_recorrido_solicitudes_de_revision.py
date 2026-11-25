# Recorrido de COM-07a (D-96): de punta a punta con el cliente de Django, como lo hace una persona, por rol y por estado. El Gerente entra por el panel de control y la alerta, evalúa una discrepancia (resumen con HTMX y sin JavaScript, confirmar),
# resuelve una queja sin cláusula (monto inválido, monto válido que supera lo que queda a cobrar y pide el medio, advertencia de resolución del contrato), rechaza una queja por retraso (sin y con observaciones), anula una resolución y la vuelve a
# resolver, y mira el historial; el Vendedor ve todo en lectura, sin los botones de escritura. No reemplaza la «Verificación a mano» del estudiante: la complementa. Lo que solo ve un navegador (CSRF real, `Origin`, JavaScript y el
# desplegable propio) queda para el paso de «navegador real» de esa verificación.
# Fuente: docs/casos_de_uso/comercial/solicitudes.md («Pantallas», «Verificación a mano» de la tarea COM-07a), D-30, D-61, D-69.

from decimal import Decimal
from html import unescape

from django.core import mail
from django.test import override_settings
from django.urls import reverse

from comercial.models import Anulacion, Suministro, SolicitudRevision
from comercial.servicios import solicitudes
from comercial.tests.base_solicitudes import BaseDeSolicitudes
from maestros.models import Alerta
from produccion.models import Bitacora

D = Decimal


def texto(respuesta):
    return unescape(respuesta.content.decode())


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeSolicitudesDeRevisionTests(BaseDeSolicitudes):
    def test_recorrido_del_gerente_y_del_vendedor(self):
        """Un suministro con 1 incumplimiento tolerado, una discrepancia, una queja por estado de la mercadería y otra por retraso: el recorrido completo de COM-EVL-DSC, COM-RSV-QJA, COM-ANL-SRV y COM-CNS-SRV."""
        d = self.armar(tolerados=1)  # la discrepancia: $15,00 (3 plantas × $5) sobre $500,00 a cobrar
        q = self.otra(d, tipo="queja")  # la queja por estado de la mercadería de otra entrega del mismo contrato (tope $500,00)
        r = self.armar(tipo="queja", queja_tipo="retraso", entregada=10, retraso=3)  # 3 días × $10 = $30,00 sobre $1.000,00
        g = self.client
        g.force_login(self.gerente)

        # 1. El panel de control y la pestaña muestran las tres pendientes; la alerta lleva a la ficha de la solicitud.
        inicio = texto(g.get(reverse("core:inicio")))
        self.assertIn("quejas y discrepancias a resolver", inicio)
        self.assertIn(reverse("comercial:solicitudes") + "?estado=pendiente", inicio)
        lista = texto(g.get(reverse("comercial:solicitudes") + "?estado=pendiente"))
        for x in (d, q, r):
            self.assertIn(x.solicitud.codigo, lista)
        self.assertIn('status-danger">3<', g.get(reverse("comercial:solicitudes")).content.decode())
        alerta = Alerta.objects.get(vinculo_comercial__solicitud=d.solicitud.pk)
        enlace = solicitudes.enlaces_de_alertas(self.gerente, [alerta])[alerta.pk]
        self.assertEqual(g.get(enlace.url).status_code, 200)

        # 2. La discrepancia: la ficha trae todo para decidir; «Ver resumen» con HTMX; confirmar.
        ficha = texto(g.get(reverse("comercial:solicitud", args=[d.solicitud.pk])))
        for esperado in ("Evaluar la discrepancia", "Mínimo pactado", "$ 15,00", "Ver resumen"):
            self.assertIn(esperado, ficha)
        revisar = reverse("comercial:solicitud_resolver_revisar", args=[d.solicitud.pk])
        parcial = texto(g.post(revisar, {"decision": "aceptar", "observaciones": "Se cargó menos."}, HTTP_HX_REQUEST="true"))
        self.assertIn("el monto a cobrar pasa de $ 500,00 a $ 485,00", parcial)
        self.assertIn("Incumplimientos del contrato", parcial)
        huella = solicitudes.resumen_de_resolucion(self.gerente, d.solicitud.pk, self.datos("aceptar", "Se cargó menos.")).huella
        with self.captureOnCommitCallbacks(execute=True):
            confirmar = g.post(reverse("comercial:solicitud_resolver", args=[d.solicitud.pk]), {"decision": "aceptar", "observaciones": "Se cargó menos.", "huella": huella})
        self.assertEqual(confirmar.status_code, 302)
        resuelta = texto(g.get(confirmar["Location"]))
        for esperado in ("aceptada: indemnización de $ 15,00", "Cuenta como incumplimiento", "Se cargó menos.", "Anular resolución"):
            self.assertIn(esperado, resuelta)
        self.assertEqual(Suministro.objects.get(pk=d.contrato.pk).cantidad_incumplimientos, 1)
        self.assertEqual(Alerta.objects.get(pk=alerta.pk).estado_alerta, "resuelta")
        self.assertEqual(Bitacora.objects.filter(tipo_evento="incumplimiento_de_clausula").count(), 1)
        self.assertEqual(len(mail.outbox), 1)  # el comprobante de indemnización al cliente
        self.assertIn("Comprobante de indemnización", mail.outbox[0].subject)

        # 3. La queja sin cláusula: un monto que supera el tope se rechaza con el tope; uno válido que supera lo que queda a cobrar pide el medio; el contrato supera lo tolerado y lo advierte.
        revisar_q = reverse("comercial:solicitud_resolver_revisar", args=[q.solicitud.pk])
        invalido = texto(g.post(revisar_q, {"decision": "aceptar", "monto": "500,01"}))
        self.assertIn("El monto supera el tope.", invalido)
        self.assertIn("$ 500,00", invalido)
        self.assertNotIn("Confirmar la decisión", invalido)
        valido = texto(g.post(revisar_q, {"decision": "aceptar", "monto": "600"}))
        self.assertIn("El monto supera el tope.", valido)
        al_tope = texto(g.post(revisar_q, {"decision": "aceptar", "monto": "500"}))
        self.assertIn("se superan los incumplimientos tolerados", al_tope)
        self.assertIn("se resolverá", al_tope)
        self.assertIn("Confirmar la decisión", al_tope)
        huella_q = solicitudes.resumen_de_resolucion(self.gerente, q.solicitud.pk, self.datos("aceptar", monto="500")).huella
        with self.captureOnCommitCallbacks(execute=True):
            g.post(reverse("comercial:solicitud_resolver", args=[q.solicitud.pk]), {"decision": "aceptar", "monto": "500", "huella": huella_q})
        sq = SolicitudRevision.objects.get(pk=q.solicitud.pk)
        self.assertEqual((sq.estado_solicitud, sq.monto_indemnizacion, sq.monto_descontado, sq.monto_reintegrado), ("aceptada", D("500.00"), D("500.00"), D("0.00")))
        # Más que los tolerados: desde COM-07b (reemplaza la prueba de COM-07a, que dejaba el contrato «vigente» como estado de paso) la aceptación lo resuelve después del commit, con esta solicitud.
        resuelto = Suministro.objects.get(pk=d.contrato.pk)
        self.assertEqual((resuelto.cantidad_incumplimientos, resuelto.estado_suministro, resuelto.solicitud_resolucion_id), (2, "resuelto", q.solicitud.pk))

        # 4. La queja por retraso: la indemnización es de la cláusula; rechazarla sin observaciones se rechaza; con observaciones, el cliente recibe el aviso.
        ficha_r = texto(g.get(reverse("comercial:solicitud", args=[r.solicitud.pk])))
        for esperado in ("Resolver la queja", "Días de retraso", "$ 30,00", "Sale de la cláusula; no se puede modificar."):
            self.assertIn(esperado, ficha_r)
        self.assertNotIn('name="monto"', ficha_r)
        sin_obs = texto(g.post(reverse("comercial:solicitud_resolver_revisar", args=[r.solicitud.pk]), {"decision": "rechazar"}))
        self.assertIn("Las observaciones son obligatorias al rechazar", sin_obs)
        self.assertNotIn("Confirmar la decisión", sin_obs)
        huella_r = solicitudes.resumen_de_resolucion(self.gerente, r.solicitud.pk, self.datos("rechazar", "El cliente estaba ausente.")).huella
        with self.captureOnCommitCallbacks(execute=True):
            g.post(reverse("comercial:solicitud_resolver", args=[r.solicitud.pk]), {"decision": "rechazar", "observaciones": "El cliente estaba ausente.", "huella": huella_r})
        self.assertEqual(SolicitudRevision.objects.get(pk=r.solicitud.pk).estado_solicitud, "rechazada")
        self.assertTrue(any("no fue reconocida" in m.subject and "El cliente estaba ausente." in m.body for m in mail.outbox))
        self.assertEqual(Suministro.objects.get(pk=r.contrato.pk).cantidad_incumplimientos, 0)

        # 5. Anular la discrepancia: la página dice qué va a pasar; sin motivo se pide; con motivo vuelve a pendiente y se vuelve a resolver; el historial queda.
        anular = reverse("comercial:solicitud_anular", args=[d.solicitud.pk])
        pagina = texto(g.get(anular))
        for esperado in ("2 → 1", "$ 485,00 → $ 500,00", "Fuera de esta ronda"):
            self.assertIn(esperado, pagina)
        huella_a = solicitudes.datos_de_anulacion(self.gerente, d.solicitud.pk).huella
        self.assertIn("el motivo es obligatorio", texto(g.post(anular, {"motivo": "", "huella": huella_a})))
        anulada = g.post(anular, {"motivo": "Me equivoqué al decidir.", "huella": huella_a})
        self.assertEqual(anulada.status_code, 302)
        pendiente = texto(g.get(anulada["Location"]))
        for esperado in ("volvió a pendiente de revisión", "Evaluar la discrepancia", "Historial de resoluciones anuladas", "Me equivoqué al decidir."):
            self.assertIn(esperado, pendiente)
        self.assertEqual((Anulacion.objects.count(), Suministro.objects.get(pk=d.contrato.pk).cantidad_incumplimientos), (1, 1))
        self.assertEqual(Bitacora.objects.filter(tipo_evento="anulacion_de_resolucion").count(), 1)
        # La alerta ya estaba resuelta: no se reabre ni se crea otra; volver a resolver deja la solicitud aceptada de nuevo.
        self.assertEqual(Alerta.objects.filter(vinculo_comercial__solicitud=d.solicitud.pk).count(), 1)
        huella_2 = solicitudes.resumen_de_resolucion(self.gerente, d.solicitud.pk, self.datos("aceptar")).huella
        g.post(reverse("comercial:solicitud_resolver", args=[d.solicitud.pk]), {"decision": "aceptar", "huella": huella_2})
        self.assertEqual(SolicitudRevision.objects.get(pk=d.solicitud.pk).estado_solicitud, "aceptada")

        # 6. Anular la queja con la indemnización descontada en su totalidad sigue siendo posible; con reintegro no (2c): se prueba en test_com_anl_srv.

        # 7. El Vendedor ve todo en lectura, sin ningún botón de escritura (D-30).
        v = self.client
        v.force_login(self.e.vendedor)
        for x in (d, q, r):
            self.assertIn(x.solicitud.codigo, texto(v.get(reverse("comercial:solicitudes"))))
            html = texto(v.get(reverse("comercial:solicitud", args=[x.solicitud.pk])))
            for ausente in ("Ver resumen", "Confirmar la decisión", reverse("comercial:solicitud_anular", args=[x.solicitud.pk]), reverse("comercial:solicitud_resolver_revisar", args=[x.solicitud.pk])):
                self.assertNotIn(ausente, html)
        self.assertNotIn("quejas y discrepancias a resolver", texto(v.get(reverse("core:inicio"))))
        self.assertEqual(v.get(reverse("comercial:solicitud_anular", args=[d.solicitud.pk])).status_code, 403)
        self.assertEqual(v.post(reverse("comercial:solicitud_resolver", args=[d.solicitud.pk]), {"decision": "aceptar"}).status_code, 403)
        suministro_html = texto(v.get(reverse("comercial:suministro", args=[d.contrato.pk])))
        self.assertIn("Solicitudes de revisión", suministro_html)
        self.assertIn(d.solicitud.codigo, suministro_html)
        self.assertIn(q.solicitud.codigo, suministro_html)
