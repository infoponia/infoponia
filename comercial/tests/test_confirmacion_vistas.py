# Pruebas de las pantallas de COM-CNF-ENT y COM-ATN-ENR (COM-06b, paso 6; docs/casos_de_uso/comercial/confirmacion.md, «Pantallas» y «Lo que completa a otras tareas»): las páginas públicas del cliente
# (`/cliente/<token>/`, `/cliente/enlace/`, `/cliente/enlace/listo/` y «Reenviar acuse», sin cuenta), la pantalla del Gerente «Atender entrega no reconocida» y lo que suman las fichas del suministro y del cliente.
# Las reglas de negocio ya las prueban los servicios (`test_com_cnf_ent.py`, `test_com_atn_enr.py`, `test_enlaces.py`): acá, los permisos (ningún botón lleva a un 403), los encabezados de `/cliente/`, que el token no
# quede en la URL, que el cliente no vea perdidas ni costos y los flujos con HTMX y sin él. El cliente de Django no ve el CSRF real ni el encabezado `Origin`: eso va como paso de «navegador real» en la «Verificación a mano».

from datetime import timedelta
from html import unescape
from unittest import mock

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import EnlaceCliente, Entrega, Queja
from comercial.servicios import atencion, clientes, confirmacion
from comercial.servicios.confirmacion import NO_RECIBI, DatosDeRespuesta
from comercial.tests.fabricas import (
    detalle_suministro,
    discrepancia,
    enlace_de_confirmacion,
    entrega,
    escenario_comercial,
    marcar_concretada,
    reserva_lista,
    suministro,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta
from maestros.servicios import alertas
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()
PORTAL = "/cliente/enlace/"
LISTO = "/cliente/enlace/listo/"


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    """Un suministro con dos detalles (dos variedades), el Vendedor y el Gerente. `nueva()` arma una entrega concretada con su enlace de confirmación; el cliente es un `Client` anónimo aparte."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.gerente = crear_gerente()
        cls.otra_variedad, _ = variedad_con_stock(cls.e, "Rúcula 06b")
        cls.lote = lote_maduro(cls.e, 500)
        cls.lote_otra = lote_maduro(cls.e, 500, variedad=cls.otra_variedad)
        cls.contrato = suministro(cls.e)
        cls.d1 = detalle_suministro(cls.contrato, cls.e.variedad, cantidad=100, minima=50, plazo_entrega=1)
        cls.d2 = detalle_suministro(cls.contrato, cls.otra_variedad, cantidad=60, minima=30, plazo_entrega=30)

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)
        self.anonimo = Client()

    def nueva(self, *, cantidades=None, retraso=0):
        """Una entrega de suministro concretada (directo en la base) con sus dos líneas y su enlace vigente; `retraso` días de retraso en la primera línea. Devuelve `(entrega, enlace, token)`."""
        r1 = reserva_lista(None, self.lote, 100, fecha_entrega=self.d1.fecha_primer_entrega, detalle_suministro=self.d1)
        r2 = reserva_lista(None, self.lote_otra, 60, fecha_entrega=self.d2.fecha_primer_entrega, detalle_suministro=self.d2)
        e = marcar_concretada(entrega(self.contrato, [r1, r2]), cantidades=cantidades)
        if retraso:
            Entrega.objects.filter(pk=e.pk).update(fecha_resolucion_orden=HOY + timedelta(days=3 + 1 + retraso))
            e.refresh_from_db()
        creado, token = enlace_de_confirmacion(e)
        return e, creado, token

    def abrir(self, token, cliente_web=None):
        """Abre el enlace del correo y sigue la redirección: devuelve la página del portal."""
        return (cliente_web or self.anonimo).get(f"/cliente/{token}/", follow=True)

    def lineas(self, e):
        return [l.pk for l in e.lineas.order_by("pk")]


# ---- las páginas públicas del cliente ----


class PortalDeConfirmacionTests(Base):
    def test_regla_abrir_el_enlace_redirige_a_una_url_sin_el_token(self):
        """Patrón del enlace, sección 4: la entrada valida, guarda en la sesión el id y redirige (302) a `/cliente/enlace/`: el token no queda en la URL final ni en la página."""
        _, _, token = self.nueva()
        respuesta = self.anonimo.get(f"/cliente/{token}/")
        self.assertEqual((respuesta.status_code, respuesta["Location"]), (302, PORTAL))
        final = self.abrir(token)
        self.assertEqual(final.redirect_chain, [(PORTAL, 302)])
        self.assertNotIn(token, final.request["PATH_INFO"])
        self.assertNotIn(token, texto(final))

    def test_regla_las_paginas_de_cliente_llevan_los_tres_encabezados(self):
        """Patrón del enlace, sección 4: `Cache-Control: no-store`, `Referrer-Policy: same-origin` y `X-Robots-Tag: noindex` en cada página de `/cliente/`: la entrada, el portal, la pantalla final, «Reenviar acuse» y la de un enlace inválido."""
        e, _, token = self.nueva()
        self.abrir(token)
        paginas = [
            self.anonimo.get(f"/cliente/{token}/"),
            self.anonimo.get(PORTAL),
            self.anonimo.post(PORTAL, {"accion": "revisar", "respuesta": "conforme"}),
            self.anonimo.post(PORTAL, {"accion": "confirmar", "respuesta": "conforme"}, follow=True),
            self.anonimo.get(LISTO),
            self.anonimo.post("/cliente/enlace/listo/reenviar/"),
            Client().get("/cliente/no-existe/"),
            Client().get(PORTAL),
        ]
        for pagina in paginas:
            with self.subTest(url=pagina.request["PATH_INFO"], estado=pagina.status_code):
                self.assertIn("no-store", pagina["Cache-Control"])
                self.assertEqual((pagina["Referrer-Policy"], pagina["X-Robots-Tag"]), ("same-origin", "noindex"))
                self.assertIn("HX-Request", pagina["Vary"])

    def test_ext_2a_un_token_que_no_existe_es_no_valido_sin_mas_datos(self):
        """Extensión 2a: un token inexistente da 404 «Este enlace no es válido», sin datos de ninguna entrega ni del Vendedor; lo mismo `/cliente/enlace/` sin haber abierto un enlace."""
        for ruta in ("/cliente/inventado/", PORTAL, LISTO):
            respuesta = Client().get(ruta)
            self.assertContains(respuesta, "Este enlace no es válido", status_code=404)
            self.assertNotContains(respuesta, self.e.vendedor.email, status_code=404)

    def test_ext_2a_usado_vencido_y_anulado_dicen_el_motivo_y_dan_el_contacto_del_vendedor(self):
        """Extensión 2a: «Este enlace no se puede usar» con el motivo de cada caso (ya usado, vencido, anulado) y el contacto del Vendedor del contrato: nombre, teléfono y correo."""
        textos = {"usado": "ya se usó", "vencido": "El plazo para confirmar la entrega terminó", "anulado": "ya no puede usarse"}
        for estado, esperado in textos.items():
            e, _, _ = self.nueva()
            EnlaceCliente.objects.filter(entrega=e).delete()
            _, token = enlace_de_confirmacion(e, estado=estado)
            pagina = self.abrir(token)
            html = texto(pagina)
            self.assertContains(pagina, "Este enlace no se puede usar")
            self.assertIn(esperado, html)
            self.assertIn(self.e.vendedor.get_full_name(), html)
            self.assertIn(self.e.vendedor.email, html)
            self.assertNotIn(e.codigo, html)  # no muestra datos de la entrega

    def test_ext_2a_la_vigencia_calculada_vence_el_enlace_sin_cambiar_su_estado(self):
        """D-68 punto 8: con la fecha de resolución de hace más de 3 días el enlace «vigente» ya no sirve."""
        e, _, token = self.nueva()
        Entrega.objects.filter(pk=e.pk).update(fecha_resolucion_orden=HOY - timedelta(days=4))
        self.assertContains(self.abrir(token), "El plazo para confirmar la entrega terminó")

    def test_flujo_principal_el_cliente_ve_su_entrega_sin_perdidas_ni_costos_ni_menu(self):
        """Paso 2: el contrato, la fecha real, por producto las plantas entregadas, planificadas y devueltas, el precio y el monto, el total y el vencimiento del pago; nunca las plantas perdidas ni los costos; sin menú ni campana."""
        e, _, token = self.nueva(cantidades=[(80, 15, 5), (60, 0, 0)])
        pagina = self.abrir(token)
        html = texto(pagina)
        self.assertEqual(pagina.status_code, 200)
        for esperado in (e.codigo, self.contrato.codigo, str(self.e.variedad), str(self.otra_variedad), "80 entregadas", "100 planificadas", "5 devueltas", f"{e.fecha_vencimiento_pago:%d/%m/%Y}", "Sí, la recibí y estoy conforme", "Sí, la recibí pero tengo quejas", "No recibí la entrega"):
            self.assertIn(esperado, html)
        self.assertIn("Total de la entrega", html)
        for prohibido in ("perdid", "pérdid", "costo"):
            self.assertNotIn(prohibido, html.lower())
        self.assertNotIn("Cerrar sesión", html)

    def test_regla_la_queja_por_retraso_solo_se_ofrece_con_retraso_y_solo_con_sus_productos(self):
        """Regla «Queja por retraso»: sin retraso la pantalla no ofrece «Retraso»; con retraso lo ofrece, solo con los productos demorados y sus días."""
        _, _, token = self.nueva()
        self.assertNotIn('name="queja_retraso"', texto(self.abrir(token)))
        e, _, token = self.nueva(retraso=2)
        html = texto(self.abrir(token))
        self.assertIn('name="queja_retraso"', html)
        self.assertIn("llegó con 2 días de retraso", html)
        l1, l2 = self.lineas(e)
        retraso = html[html.index('name="queja_retraso"') : html.index('name="queja_otro"')]
        self.assertIn(f'value="{l1}"', retraso)
        self.assertNotIn(f'value="{l2}"', retraso)

    def test_ext_2b_el_producto_con_discrepancia_pendiente_muestra_el_aviso_de_revision(self):
        """Extensión 2b: el detalle de una discrepancia «pendiente de revisión» trae «está siendo revisada»."""
        e, _, token = self.nueva(cantidades=[(10, 0, 90), (10, 0, 50)])
        discrepancia(e, minima=50)
        from comercial.models import LineaDiscrepancia

        LineaDiscrepancia.objects.filter(detalle_entrega=e.lineas.order_by("pk")[1]).delete()
        self.assertContains(self.abrir(token), "por debajo del mínimo pactado y está siendo revisada")

    def test_flujo_principal_confirmar_sin_quejas_sin_javascript(self):
        """Pasos 3 a 8: el formulario (un POST común) lleva al resumen con la advertencia, «Enviar respuesta» registra y redirige a la pantalla final «Gracias. Recibimos su respuesta.»; la entrega queda confirmada y el enlace, usado."""
        e, enlace, token = self.nueva()
        self.abrir(token)
        resumen = self.anonimo.post(PORTAL, {"accion": "revisar", "respuesta": "conforme"})
        self.assertContains(resumen, "Revise su respuesta")
        self.assertContains(resumen, "no podrá volver a usarse")
        self.assertContains(resumen, "Enviar respuesta")
        self.assertEqual(EnlaceCliente.objects.get(pk=enlace.pk).estado, "vigente")  # el resumen no escribe
        enviado = self.anonimo.post(PORTAL, {"accion": "confirmar", "respuesta": "conforme"})
        self.assertRedirects(enviado, LISTO, fetch_redirect_response=False)
        final = self.anonimo.get(LISTO)
        self.assertContains(final, "Gracias. Recibimos su respuesta.")
        self.assertContains(final, "confirmada")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_confirmacion_cliente, "confirmado")
        self.assertEqual(EnlaceCliente.objects.get(pk=enlace.pk).estado, "usado")

    def test_ext_6a_con_el_enlace_usado_el_portal_y_el_enlace_dejan_de_servir(self):
        """Extensión 2a: después de responder, volver al portal con la misma sesión o abrir el enlace da «Este enlace no se puede usar» (ya se usó), sin registrar nada."""
        e, _, token = self.nueva()
        self.abrir(token)
        self.anonimo.post(PORTAL, {"accion": "confirmar", "respuesta": "conforme"})
        self.assertContains(self.anonimo.get(PORTAL), "Este enlace no se puede usar")
        self.assertContains(self.abrir(token, Client()), "ya se usó")
        otra = self.anonimo.post(PORTAL, {"accion": "confirmar", "respuesta": "no_recibi", "motivo_no_recibi": "No llegó."})
        self.assertContains(otra, "ya se usó")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_confirmacion_cliente, "confirmado")

    def test_ext_6a_el_enlace_usado_en_otra_pestana_mientras_completaba_la_respuesta(self):
        """Extensión 6a: si otra pestaña ya registró la respuesta, el envío no registra nada y dice que el enlace ya no puede usarse, con el contacto del Vendedor."""
        e, enlace, token = self.nueva()
        self.abrir(token)
        confirmacion.registrar_respuesta(enlace.pk, DatosDeRespuesta("conforme"))
        enviado = self.anonimo.post(PORTAL, {"accion": "confirmar", "respuesta": "con_quejas", "queja_otro": "1", "lineas_otro": self.lineas(e)[:1], "motivo_otro": "Falta algo."})
        self.assertContains(enviado, "Este enlace no se puede usar")
        self.assertContains(enviado, self.e.vendedor.email)
        self.assertEqual(Queja.objects.count(), 0)

    def test_flujo_principal_dos_quejas_el_resumen_las_lista_y_la_pantalla_final_trae_sus_numeros(self):
        """Extensión 3a: el cliente presenta dos quejas (estado de la mercadería y otro) con sus productos y motivo; el resumen las lista; la pantalla final muestra el número y el tipo de cada una; quedan «pendiente» y cada una con su alerta."""
        e, enlace, token = self.nueva()
        l1, l2 = self.lineas(e)
        self.abrir(token)
        datos = {
            "respuesta": "con_quejas",
            "queja_estado_mercaderia": "1", "lineas_estado_mercaderia": [l1, l2], "motivo_estado_mercaderia": "Llegó golpeado.",
            "queja_otro": "1", "lineas_otro": [l2], "motivo_otro": "Faltó la factura.",
        }
        resumen = self.anonimo.post(PORTAL, {"accion": "revisar", **datos})
        html = texto(resumen)
        for esperado in ("2 quejas", "Estado de la mercadería", "Llegó golpeado.", "Faltó la factura.", str(self.otra_variedad)):
            self.assertIn(esperado, html)
        for nombre, valor in (("queja_otro", "1"), ("respuesta", "con_quejas"), ("motivo_otro", "Faltó la factura.")):  # el resumen guarda lo elegido en campos ocultos
            self.assertIn(f'name="{nombre}" value="{valor}"', html)
        self.assertEqual(Queja.objects.count(), 0)
        self.anonimo.post(PORTAL, {"accion": "confirmar", **datos})
        final = texto(self.anonimo.get(LISTO))
        codigos = list(Queja.objects.order_by("numero").values_list("numero", flat=True))
        self.assertEqual(len(codigos), 2)
        for numero in codigos:
            self.assertIn(f"SR-{numero:04d}", final)
        self.assertIn("registramos 2 quejas", final)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="comercial_queja", estado_alerta="activa").count(), 2)

    def test_ext_3a_4a_4b_y_6a_los_errores_vuelven_al_formulario_con_lo_elegido(self):
        """Extensiones 3a.4a, 3a.4b, 3a.6a y 3b.1a: sin respuesta, sin quejas, sin productos, sin motivo o sin motivo de «no recibí», la misma pantalla vuelve (200) con el error bajo el campo y lo ya elegido; no se registra nada."""
        e, enlace, token = self.nueva()
        l1 = self.lineas(e)[0]
        self.abrir(token)
        casos = (
            ({"respuesta": ""}, "Indicá si recibiste la entrega."),
            ({"respuesta": "con_quejas"}, "Agregá al menos una queja"),
            ({"respuesta": "con_quejas", "queja_otro": "1", "motivo_otro": "Falta algo."}, "Elegí al menos un producto."),
            ({"respuesta": "con_quejas", "queja_otro": "1", "lineas_otro": [l1], "motivo_otro": ""}, "El motivo es obligatorio para este tipo de queja."),
            ({"respuesta": "no_recibi", "motivo_no_recibi": " "}, "el motivo es obligatorio"),
        )
        for datos, esperado in casos:
            pagina = self.anonimo.post(PORTAL, {"accion": "revisar", **datos})
            self.assertEqual(pagina.status_code, 200)
            self.assertIn(esperado, texto(pagina))
            self.assertContains(pagina, "Revisar y enviar")  # sigue siendo el formulario, no el resumen
        con_eleccion = texto(self.anonimo.post(PORTAL, {"accion": "revisar", "respuesta": "con_quejas", "queja_otro": "1", "lineas_otro": [l1], "motivo_otro": ""}))
        self.assertIn(f'value="{l1}" checked', con_eleccion)
        self.assertEqual((Queja.objects.count(), EnlaceCliente.objects.get(pk=enlace.pk).estado), (0, "vigente"))

    def test_ext_4a_cambiar_la_respuesta_vuelve_al_formulario_con_lo_elegido(self):
        """Extensión 4a y 4b: «Cambiar la respuesta» desde el resumen vuelve al formulario con lo que había elegido (las quejas se conservan si vuelve a presentar quejas)."""
        e, _, token = self.nueva()
        l1 = self.lineas(e)[0]
        self.abrir(token)
        pagina = self.anonimo.post(PORTAL, {"accion": "cambiar", "respuesta": "con_quejas", "queja_otro": "1", "lineas_otro": [l1], "motivo_otro": "Falta algo."})
        html = texto(pagina)
        self.assertIn("Revisar y enviar", html)
        self.assertIn("Falta algo.", html)
        self.assertIn('name="queja_otro" value="1" checked', html)

    def test_regla_con_htmx_al_elegir_se_redibuja_solo_el_bloque_que_corresponde_y_no_se_valida(self):
        """D-29: al elegir la respuesta (HTMX) solo vuelve el bloque de quejas o de motivo, sin validar ni registrar nada; sin elegir todavía (sin JavaScript) se muestran los dos."""
        e, enlace, token = self.nueva()
        completo = texto(self.abrir(token))
        self.assertIn('name="queja_otro"', completo)
        self.assertIn('name="motivo_no_recibi"', completo)
        for respuesta, con_quejas, con_motivo in (("conforme", False, False), ("con_quejas", True, False), ("no_recibi", False, True)):
            fragmento = texto(self.anonimo.post(PORTAL, {"accion": "redibujar", "respuesta": respuesta}, **HTMX))
            self.assertNotIn("<html", fragmento)
            self.assertEqual(('name="queja_otro"' in fragmento, 'name="motivo_no_recibi"' in fragmento), (con_quejas, con_motivo), respuesta)
            self.assertNotIn("es obligatorio", fragmento)
        self.assertEqual((Queja.objects.count(), EnlaceCliente.objects.get(pk=enlace.pk).estado), (0, "vigente"))

    def test_flujo_principal_no_recibi_registra_la_alerta_critica_y_la_pantalla_final_lo_dice(self):
        """Extensión 3b: «No recibí la entrega» con motivo: resumen (la entrega no será confirmada), envío y pantalla final con la constancia; la entrega sigue «no confirmado» y el Gerente tiene su alerta crítica."""
        e, _, token = self.nueva()
        self.abrir(token)
        datos = {"respuesta": "no_recibi", "motivo_no_recibi": "No llegó nada a la sucursal."}
        resumen = texto(self.anonimo.post(PORTAL, {"accion": "revisar", **datos}))
        self.assertIn("no recibió", resumen)
        self.assertIn("No llegó nada a la sucursal.", resumen)
        self.anonimo.post(PORTAL, {"accion": "confirmar", **datos})
        self.assertContains(self.anonimo.get(LISTO), "no reconoce la entrega")
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_confirmacion_cliente, "no_confirmado")
        self.assertEqual(Alerta.objects.get(tipo_alerta="comercial_entrega_no_reconocida").nivel_severidad, "critica")

    def test_regla_la_sesion_de_un_enlace_no_abre_otra_entrega_ni_la_pantalla_final_sin_responder(self):
        """Garantía mínima: cada vista vuelve a leer el enlace por el id de la sesión: un id que no existe da «no es válido»; la pantalla final y «Reenviar acuse» solo existen para quien acaba de responder con ese enlace."""
        e, _, token = self.nueva()
        otra, _, _ = self.nueva()
        self.abrir(token)
        self.assertContains(self.anonimo.get(LISTO), "no es válido", status_code=404)
        self.assertContains(self.anonimo.post("/cliente/enlace/listo/reenviar/"), "no es válido", status_code=404)
        sesion = self.anonimo.session
        sesion["enlace_cliente"] = 999999
        sesion.save()
        self.assertContains(self.anonimo.get(PORTAL), "no es válido", status_code=404)
        self.assertNotContains(self.anonimo.get(PORTAL), otra.codigo, status_code=404)

    def test_regla_una_sesion_de_usuario_abierta_en_el_mismo_navegador_no_cambia_nada(self):
        """Patrón del enlace, sección 4: las páginas no leen `request.user`: con el Gerente logueado en el mismo navegador el portal es el mismo, sin menú."""
        _, _, token = self.nueva()
        web = Client()
        web.force_login(self.gerente)
        pagina = self.abrir(token, web)
        self.assertContains(pagina, "Confirme la recepción de su entrega")
        self.assertNotContains(pagina, "Cerrar sesión")
        self.assertNotContains(pagina, self.gerente.email)

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_7a_8a_si_el_acuse_no_salio_la_pantalla_final_lo_dice_y_reenviar_lo_manda(self):
        """Extensiones 7a.3 y 8a: sin el correo del sistema el acuse no sale; la pantalla final avisa que todavía no se envió y ofrece «Reenviar acuse»; con el correo, el reenvío sale al correo registrado y se puede repetir."""
        e, _, token = self.nueva()
        self.abrir(token)
        # Dentro de una transacción de prueba el `on_commit` del acuse nunca corre antes de que la vista guarde la sesión (en producción sí: la vista vuelve ya confirmada): se lo corre al registrarlo.
        with mock.patch("comercial.servicios.confirmacion.transaction.on_commit", side_effect=lambda funcion, using=None, robust=False: funcion()):
            self.anonimo.post(PORTAL, {"accion": "confirmar", "respuesta": "conforme"})
        final = self.anonimo.get(LISTO)
        self.assertContains(final, "El acuse todavía no se envió")
        self.assertContains(final, "Reenviar acuse")
        with override_settings(CORREO_CONFIGURADO=True):
            for _ in range(2):
                reenvio = self.anonimo.post("/cliente/enlace/listo/reenviar/", follow=True)
                self.assertContains(reenvio, "Le reenviamos el acuse a su correo.")
        self.assertEqual([m.to for m in mail.outbox], [[self.e.cliente.email_cliente]] * 2)
        self.assertContains(self.anonimo.get(LISTO), "Reenviar acuse")

    def test_regla_reenviar_acuse_solo_acepta_post(self):
        """«Reenviar acuse» es un POST: un GET no hace nada (405)."""
        self.assertEqual(self.anonimo.get("/cliente/enlace/listo/reenviar/").status_code, 405)


# ---- la pantalla del Gerente ----


class AtenderEntregaNoReconocidaVistaTests(Base):
    def setUp(self):
        super().setUp()
        self.entrega, self.enlace, self.token = self.nueva()
        confirmacion.registrar_respuesta(self.enlace.pk, DatosDeRespuesta(NO_RECIBI, motivo_no_recibi="No llegó nada a la sucursal."))
        self.alerta = Alerta.objects.get(tipo_alerta="comercial_entrega_no_reconocida")
        self.url = reverse("comercial:entrega_no_reconocida", args=[self.entrega.pk])
        self.ficha = reverse("comercial:suministro", args=[self.contrato.pk])

    def test_regla_solo_el_gerente_entra_y_los_demas_reciben_403(self):
        """Las vistas del Gerente con `rol_requerido`: el Vendedor, el Agrónomo y el Transportista reciben 403 en el GET y en el POST; sin sesión, al inicio de sesión. No cambia nada."""
        for cuenta in (self.e.vendedor, self.e.agronomo, crear_vendedor(email="otro@infoponia.com")):
            self.client.force_login(cuenta)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, {"resultado": "llego", "descripcion": "x"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(Alerta.objects.get(pk=self.alerta.pk).estado_alerta, "activa")

    def test_flujo_principal_el_gerente_ve_todo_y_resuelve_la_alerta(self):
        """COM-ATN-ENR: la pantalla muestra lo que dijo el cliente, la entrega con sus cantidades, la confirmación, el cobro y los asientos «Fuera de esta ronda»; «Resolver alerta» resuelve y vuelve a la ficha del suministro con el aviso."""
        self.client.force_login(self.gerente)
        html = texto(self.client.get(self.url))
        for esperado in ("No llegó nada a la sucursal.", self.entrega.codigo, self.contrato.codigo, str(self.e.variedad), "No confirmada", "Sin cobro registrado", "Fuera de esta ronda · contabilidad", "La entrega llegó", "No llegó, producto perdido", "No llegó, producto devuelto", "Resolver alerta"):
            self.assertIn(esperado, html)
        respuesta = self.client.post(self.url, {"resultado": "no_llego_perdido", "descripcion": "Hablé con el cliente: se perdió."}, follow=True)
        self.assertEqual(respuesta.redirect_chain, [(self.ficha, 302)])
        self.assertContains(respuesta, f"La alerta de {self.entrega.codigo} quedó resuelta.")
        self.assertEqual(Alerta.objects.get(pk=self.alerta.pk).estado_alerta, "resuelta")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="atencion_entrega_no_reconocida").count(), 1)

    def test_ext_sin_resultado_o_sin_descripcion_vuelve_con_el_error_y_lo_elegido(self):
        """Los errores del servicio (resultado y descripción obligatorios) vuelven a la pantalla (200) con el mensaje bajo el campo y lo ya elegido; la alerta sigue activa."""
        self.client.force_login(self.gerente)
        sin_resultado = self.client.post(self.url, {"resultado": "", "descripcion": "Algo."})
        self.assertIn("Elegí el resultado de la averiguación.", texto(sin_resultado))
        sin_descripcion = self.client.post(self.url, {"resultado": "no_llego_devuelto", "descripcion": "  "})
        html = texto(sin_descripcion)
        self.assertIn("la descripción es obligatoria", html)
        self.assertIn('value="no_llego_devuelto" checked', html)
        self.assertEqual(Alerta.objects.get(pk=self.alerta.pk).estado_alerta, "activa")

    def test_regla_una_entrega_sin_alerta_activa_vuelve_a_la_ficha_con_el_mensaje(self):
        """Una entrega ya atendida (o sin alerta) no deja usar la pantalla: vuelve a la ficha del suministro con el mensaje (ningún botón lleva a un error)."""
        self.client.force_login(self.gerente)
        self.client.post(self.url, {"resultado": "llego", "descripcion": "El cliente se equivocó."})
        respuesta = self.client.get(self.url, follow=True)
        self.assertEqual(respuesta.redirect_chain, [(self.ficha, 302)])
        self.assertContains(respuesta, "no tiene una alerta de entrega no reconocida para atender.")

    def test_regla_la_ficha_del_suministro_ofrece_atender_solo_al_gerente(self):
        """Regla D-30: el Gerente ve «Entregas que el cliente no reconoce» con «Atender»; el Vendedor del contrato no ve el botón (ni el bloque); resuelta la alerta, el bloque desaparece."""
        self.client.force_login(self.gerente)
        html = texto(self.client.get(self.ficha))
        self.assertIn("Entregas que el cliente no reconoce", html)
        self.assertIn(self.url, html)
        self.client.force_login(self.e.vendedor)
        html = texto(self.client.get(self.ficha))
        self.assertNotIn(self.url, html)
        self.assertNotIn("Entregas que el cliente no reconoce", html)
        self.client.force_login(self.gerente)
        self.client.post(self.url, {"resultado": "llego", "descripcion": "El cliente se equivocó."})
        self.assertNotIn(self.url, texto(self.client.get(self.ficha)))

    def test_regla_los_enlaces_de_las_alertas_llevan_al_gerente_a_donde_se_atienden(self):
        """D-62: la alerta «entrega no reconocida» lleva al Gerente a la pantalla de COM-ATN-ENR; la de una queja, a la ficha de la solicitud (desde COM-07a; antes, a la del suministro); a cualquier otro rol no le devuelve enlace."""
        e2, enlace2, _ = self.nueva()
        confirmacion.registrar_respuesta(enlace2.pk, DatosDeRespuesta("con_quejas", [confirmacion.QuejaPedida("otro", self.lineas(e2)[:1], "Falta algo.")]))
        todas = list(Alerta.objects.select_related("invernadero").order_by("pk"))
        enlaces = alertas.enlaces_de_alertas(self.gerente, todas)
        por_tipo = {a.tipo_alerta: enlaces[a.pk] for a in todas}
        self.assertEqual(por_tipo["comercial_entrega_no_reconocida"].url, self.url)
        self.assertEqual(por_tipo["comercial_queja"].url, reverse("comercial:solicitud", args=[Queja.objects.get().pk]))  # COM-07a: antes, `self.ficha`
        self.assertIn(self.entrega.codigo, por_tipo["comercial_entrega_no_reconocida"].detalle)
        self.assertEqual(atencion.enlaces_de_alertas(self.e.vendedor, todas), {})


# ---- lo que completa a la ficha del suministro y a la del cliente ----


class FichasConQuejasTests(Base):
    def setUp(self):
        super().setUp()
        self.entrega, self.enlace, _ = self.nueva()
        confirmacion.registrar_respuesta(
            self.enlace.pk, DatosDeRespuesta("con_quejas", [confirmacion.QuejaPedida("otro", self.lineas(self.entrega)[:1], "Falta algo.")])
        )
        self.queja = Queja.objects.get()

    def test_regla_la_ficha_del_suministro_muestra_la_confirmacion_y_las_quejas(self):
        """Lo que completa COM-03a: la entrega figura «Confirmada» y la sección «Solicitudes de revisión» (desde COM-07a; antes «Quejas de entrega») trae el número, la entrega, el tipo y el estado."""
        self.client.force_login(self.e.vendedor)
        html = texto(self.client.get(reverse("comercial:suministro", args=[self.contrato.pk])))
        for esperado in ("Confirmada", "Solicitudes de revisión", self.queja.codigo, self.entrega.codigo, "Queja · otro", "Pendiente de revisión"):
            self.assertIn(esperado, html)

    def test_regla_la_ficha_del_cliente_y_su_baja_informan_las_quejas_pendientes(self):
        """Lo que completa COM-01 (regla 1 de COM-BAJ-CLT): la ficha del cliente suma «Quejas pendientes» y la baja las informa (sin bloquearse); resuelta (aquí, aceptada directo en la base), desaparecen."""
        cliente = self.e.cliente
        self.client.force_login(self.gerente)
        html = texto(self.client.get(reverse("comercial:cliente", args=[cliente.pk])))
        self.assertIn("Quejas pendientes", html)
        self.assertIn(self.queja.codigo, html)
        pendientes = clientes.pendientes_del_cliente(cliente, self.gerente)
        self.assertTrue(any(p.startswith("Quejas pendientes: 1") and self.queja.codigo in p for p in pendientes), pendientes)
        Queja.objects.filter(pk=self.queja.pk).update(estado_solicitud="rechazada", fecha_resolucion=HOY, gerente=self.gerente)
        self.assertNotIn("Quejas pendientes", texto(self.client.get(reverse("comercial:cliente", args=[cliente.pk]))))
        self.assertFalse(any(p.startswith("Quejas pendientes") for p in clientes.pendientes_del_cliente(cliente, self.gerente)))

    def test_regla_el_vendedor_solo_ve_las_quejas_de_sus_contratos(self):
        """Alcance (D-28): el Vendedor de otro contrato no ve las quejas del cliente en la baja ni en la ficha."""
        otro = crear_vendedor(email="otro@infoponia.com")
        self.assertEqual(clientes.quejas_pendientes(otro, self.e.cliente), [])
        self.assertEqual(len(clientes.quejas_pendientes(self.e.vendedor, self.e.cliente)), 1)
