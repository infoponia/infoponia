# Pruebas de las pantallas de COM-DCD-FLT (COM-04c, paso 5; docs/casos_de_uso/comercial/faltante.md, «Pantallas» y «Lo que completa a COM-02»; D-65 punto 3): las páginas públicas del
# cliente (`/cliente/<token>/`, `/cliente/enlace/` y `/cliente/enlace/listo/`, sin cuenta), «Faltantes para decidir» y «Registrar decisión de faltante» del Vendedor (extensión 1a), la
# ficha de la compra-venta con lo pendiente y el enlace de la lista de contratos. Las reglas de negocio ya las prueban los servicios (`test_com_dcd_flt.py`, `test_enlaces.py`): acá,
# los permisos (ningún botón lleva a un 403), los encabezados de `/cliente/`, que el token no quede en la URL y los flujos con HTMX y sin él. El cliente de Django no ve el CSRF real ni
# el encabezado `Origin`: eso va como paso de «navegador real» en la «Verificación a mano».

from datetime import timedelta
from html import unescape

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente
from comercial.tests.fabricas import cliente, compra_venta, detalle, enlace as un_enlace, escenario_comercial, partida, reserva, verificar_invariantes_de_reservas
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_vendedor
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()
PORTAL = "/cliente/enlace/"
LISTO = "/cliente/enlace/listo/"


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class Base(ConDatosDeInventario, TestCase):
    """Una venta «pendiente de decisión» (50 pedidos, 30 cubiertos con una partida de cámara) de un cliente con correo y su enlace; el cliente es un `Client` anónimo aparte."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.venta, self.detalle, self.enlace, self.token = self.nueva()
        self.anonimo = Client()

    def nueva(self, cubierto=30, con_correo=True, vendedor=None):
        """`(venta, detalle, enlace, token)` de una venta pendiente; sin correo no hay enlace."""
        cliente_ = None if con_correo else cliente(email="", telefono="1144445555")
        venta = compra_venta(self.e, estado="pendiente_decision", cliente_=cliente_, vendedor=vendedor)
        d = detalle(venta, self.e.variedad, 50, precio="10.00", estado="pendiente_decision")
        DetalleVenta.objects.filter(pk=d.pk).update(fecha_pendiente_decision=HOY)
        if cubierto:
            reserva(d, [(partida(self.lote, cubierto), cubierto)])
        enlace, token = un_enlace(venta) if con_correo else (None, None)
        return venta, d, enlace, token

    def abrir(self, cliente_web=None):
        """Abre el enlace del correo y sigue la redirección: devuelve la página del portal."""
        return (cliente_web or self.anonimo).get(f"/cliente/{self.token}/", follow=True)

    def avisos(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]

    def formulario(self, decision, *, accion="revisar", disponible=30, d=None):
        d = d or self.detalle
        datos = {"accion": accion, f"disponible_{d.pk}": str(disponible)}
        if decision is not None:
            datos[f"decision_{d.pk}"] = decision
        return datos


class PortalDelClienteTests(Base):
    def test_regla_abrir_el_enlace_redirige_a_una_url_sin_el_token(self):
        """D-65 punto 3: la entrada valida, guarda en la sesión el id y redirige (302) a `/cliente/enlace/`: el token no queda en la URL final ni en el `Referer`."""
        respuesta = self.anonimo.get(f"/cliente/{self.token}/")
        self.assertEqual((respuesta.status_code, respuesta["Location"]), (302, PORTAL))
        final = self.abrir()
        self.assertEqual(final.redirect_chain, [(PORTAL, 302)])
        self.assertNotIn(self.token, final.request["PATH_INFO"])
        self.assertNotIn(self.token, texto(final))

    def test_flujo_principal_el_cliente_ve_la_venta_y_su_faltante_sin_menu_ni_datos_internos(self):
        """Paso 2 y garantía mínima 4: la venta, la fecha pactada, la cantidad solicitada y la disponible, el precio y hasta cuándo puede decidir; sin menú, ni lotes, partidas ni costos."""
        pagina = texto(self.abrir())
        for esperado in (self.venta.codigo, "Faltante en su compra", "Solicitó", "50 plantas", "30 plantas", "Recibir las 30 plantas disponibles", f"No recibir {self.e.variedad}", "Ver resumen"):
            self.assertIn(esperado, pagina)
        self.assertIn(f"{self.enlace.fecha_vencimiento:%d/%m/%Y}", pagina)
        for prohibido in ("Cerrar sesión", self.lote.codigo, self.e.invernadero.nombre_invernadero, "costo"):
            self.assertNotIn(prohibido, pagina)
        self.assertNotIn('name="decision_', pagina.replace(f'name="decision_{self.detalle.pk}"', ""))  # ninguna opción elegida de antemano
        self.assertNotIn("checked", pagina)

    def test_regla_cada_pagina_del_portal_lleva_los_tres_encabezados(self):
        """Patrón, sección 8: `Cache-Control: no-store`, `Referrer-Policy: same-origin` (D-65 corregida) y `X-Robots-Tag: noindex` en la entrada, el formulario, el resumen, «gracias», el
        enlace que no sirve y el que no es válido."""
        respuestas = [
            self.anonimo.get(f"/cliente/{self.token}/"),
            self.anonimo.get(PORTAL),
            self.anonimo.post(PORTAL, self.formulario("rechazar")),
            self.anonimo.post(PORTAL, self.formulario("rechazar", accion="confirmar")),
            self.anonimo.get(LISTO),
            self.anonimo.get(f"/cliente/{self.token}/"),  # ya usado: «no se puede usar»
            Client().get("/cliente/no-existe/"),  # «no es válido»
            Client().get(PORTAL),  # sin sesión
        ]
        for respuesta in respuestas:
            with self.subTest(url=respuesta.request["PATH_INFO"], estado=respuesta.status_code):
                self.assertIn("no-store", respuesta["Cache-Control"])
                self.assertEqual((respuesta["Referrer-Policy"], respuesta["X-Robots-Tag"]), ("same-origin", "noindex"))
                self.assertIn("HX-Request", respuesta["Vary"])

    def test_ext_2a_un_token_que_no_existe_es_no_valido_y_uno_que_no_sirve_da_el_motivo_y_el_contacto(self):
        """Extensión 2a: «Este enlace no es válido» (404) sin más datos; un enlace usado, vencido, reemplazado o anulado, el motivo y el contacto del Vendedor."""
        respuesta = self.anonimo.get("/cliente/no-existe/")
        self.assertEqual(respuesta.status_code, 404)
        self.assertContains(respuesta, "Este enlace no es válido", status_code=404)
        for estado, frase in (("usado", "ya se usó"), ("vencido", "plazo para decidir terminó"), ("reemplazado", "reemplazado por uno más nuevo"), ("anulado", "fue anulado")):
            with self.subTest(estado=estado):
                venta, d, enlace, token = self.nueva()
                EnlaceCliente.objects.filter(pk=enlace.pk).update(estado=estado, fecha_uso=timezone.now() if estado == "usado" else None)
                pagina = texto(self.anonimo.get(f"/cliente/{token}/"))
                self.assertIn("Este enlace no se puede usar", pagina)
                self.assertIn(frase, pagina)
                self.assertIn(self.e.vendedor.email, pagina)
                self.assertNotIn(venta.codigo, pagina)  # nunca datos de la venta

    def test_regla_el_dia_del_vencimiento_todavia_sirve(self):
        """D-65 punto 4: el último día todavía se puede decidir."""
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(fecha_vencimiento=HOY)
        self.assertEqual(self.anonimo.get(f"/cliente/{self.token}/")["Location"], PORTAL)

    def test_regla_la_sesion_de_un_enlace_no_abre_otra_venta(self):
        """Patrón, sección 8: cambiar el id de la sesión a mano da «enlace no válido»; el de un enlace que ya no sirve, «no se puede usar»."""
        sesion = self.anonimo.session
        sesion["enlace_cliente"] = 999999
        sesion.save()
        self.assertEqual(self.anonimo.get(PORTAL).status_code, 404)
        otra, _, otro_enlace, _ = self.nueva()
        EnlaceCliente.objects.filter(pk=otro_enlace.pk).update(estado="anulado")
        sesion["enlace_cliente"] = otro_enlace.pk
        sesion.save()
        pagina = texto(self.anonimo.get(PORTAL))
        self.assertIn("Este enlace no se puede usar", pagina)
        self.assertNotIn(otra.codigo, pagina)

    def test_regla_una_sesion_de_usuario_abierta_en_el_mismo_navegador_no_cambia_nada(self):
        """Patrón, sección 4, punto 3: las páginas no leen `request.user`: con un Gerente logueado en el mismo navegador se ven igual (sin su nombre ni el menú)."""
        gerente = crear_gerente()
        self.anonimo.force_login(gerente)
        pagina = texto(self.abrir())
        self.assertIn("Faltante en su compra", pagina)
        self.assertNotIn(gerente.email, pagina)
        self.assertNotIn("Cerrar sesión", pagina)

    def test_ext_2b_con_disponible_cero_solo_se_ofrece_no_recibir(self):
        """Extensión 2b: sin producto disponible no hay opción de recibir, solo de no recibir."""
        _, d, enlace, token = self.nueva(cubierto=0)
        pagina = texto(self.anonimo.get(f"/cliente/{token}/", follow=True))
        self.assertIn("solo se puede no recibirlo", pagina)
        self.assertNotIn("Recibir las", pagina)
        self.assertIn(f"No recibir {self.e.variedad}", pagina)

    def test_ext_4a_sin_elegir_vuelve_con_el_error_junto_al_producto(self):
        """Extensión 4a: «Ver resumen» sin elegir da el error por campo y no registra nada."""
        self.abrir()
        respuesta = self.anonimo.post(PORTAL, self.formulario(None))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(f"Indicá qué hacés con {self.e.variedad}", texto(respuesta))
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_flujo_principal_resumen_confirmacion_y_gracias_sin_javascript(self):
        """Pasos 3 a 9, con dos páginas y un POST: el resumen (advertencia y monto), «Cambiar» vuelve con lo elegido (4b), confirmar registra y lleva a «Gracias»; reabrir el enlace da «ya se usó»."""
        self.abrir()
        resumen = texto(self.anonimo.post(PORTAL, self.formulario("aceptar")))
        for esperado in ("Revise su decisión", "La decisión no podrá modificarse", "Acepta la cantidad disponible", "$ 300", "Confirmar decisión"):
            self.assertIn(esperado, resumen)
        volver = texto(self.anonimo.post(PORTAL, self.formulario("aceptar", accion="cambiar")))
        self.assertIn('value="aceptar" checked', volver)
        confirmada = self.anonimo.post(PORTAL, self.formulario("aceptar", accion="confirmar"))
        self.assertEqual((confirmada.status_code, confirmada["Location"]), (302, LISTO))
        gracias = texto(self.anonimo.get(LISTO))
        self.assertIn("Gracias. Recibimos su decisión.", gracias)
        self.assertIn("recibirá <b>30 plantas</b>", gracias)
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).cant_entregada_venta, 30)
        self.assertEqual(self.anonimo.get(LISTO).status_code, 200)  # recargar la página no falla
        self.assertIn("ya se usó", texto(self.anonimo.get(f"/cliente/{self.token}/")))

    def test_flujo_principal_con_htmx_responde_lo_mismo(self):
        """Los pedidos con `HX-Request` reciben la misma página completa (el respaldo sin JavaScript es el camino); la respuesta varía por ese encabezado."""
        self.abrir()
        respuesta = self.anonimo.post(PORTAL, self.formulario("rechazar"), **HTMX)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("La compra quedará cancelada", texto(respuesta))
        self.assertIn("HX-Request", respuesta["Vary"])

    def test_ext_6b_si_la_cantidad_cambio_antes_de_ver_el_resumen_avisa_y_pide_volver_a_elegir(self):
        """Extensión 6b: la pantalla mostró 99 y hoy es 30: no pasa al resumen, avisa y vuelve al formulario con la cantidad nueva."""
        self.abrir()
        respuesta = self.anonimo.post(PORTAL, self.formulario("aceptar", disponible=99))
        pagina = texto(respuesta)
        self.assertIn("La cantidad disponible cambió", pagina)
        self.assertIn("Recibir las 30 plantas disponibles", pagina)
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_ext_6a_si_el_enlace_vence_mientras_decide_termina_con_el_contacto(self):
        """Extensión 6a: el enlace venció mientras decidía: no registra nada y muestra el contacto del Vendedor."""
        self.abrir()
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(fecha_vencimiento=HOY - timedelta(days=1))
        pagina = texto(self.anonimo.post(PORTAL, self.formulario("rechazar", accion="confirmar")))
        self.assertIn("Este enlace no se puede usar", pagina)
        self.assertIn(self.e.vendedor.email, pagina)
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_regla_gracias_solo_para_quien_acaba_de_decidir(self):
        """Sin una decisión hecha con ese enlace en la sesión, `/cliente/enlace/listo/` no muestra nada."""
        self.abrir()
        self.assertEqual(self.anonimo.get(LISTO).status_code, 404)


class PantallasDelVendedorTests(Base):
    def setUp(self):
        super().setUp()
        self.sin_correo, self.d_sin, _, _ = self.nueva(con_correo=False)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def test_regla_permisos_solo_el_vendedor_ve_y_decide(self):
        """Extensión 1a: «Faltantes para decidir» y «Registrar decisión» son solo del Vendedor; el Gerente, el Agrónomo y el Capataz reciben 403 (y no ven el botón), un Vendedor ajeno también."""
        urls = [reverse("comercial:faltantes"), reverse("comercial:faltante_decidir", args=[self.sin_correo.pk])]
        ajeno = crear_vendedor(email="ajeno@infoponia.com")
        for cuenta in (crear_gerente(), self.e.agronomo, self.e.capataz, ajeno):
            self.entrar(cuenta)
            for url in urls:
                with self.subTest(cuenta=cuenta.rol, url=url):
                    respuesta = self.client.get(url)
                    if url == urls[0] and cuenta is ajeno:
                        self.assertEqual(respuesta.status_code, 200)  # la lista es suya (vacía): no tiene ventas
                    else:
                        self.assertEqual(respuesta.status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(urls[0]).status_code, 302)  # sin sesión: al ingreso

    def test_ext_1a_2_la_lista_trae_la_venta_sin_correo_con_el_contacto_del_cliente(self):
        """Extensiones 1a.1 y 1a.2: la venta del cliente sin correo, con su contacto, la fecha pactada, lo pendiente y desde cuándo; la del cliente con enlace vigente no está."""
        self.entrar(self.e.vendedor)
        pagina = texto(self.client.get(reverse("comercial:faltantes")))
        self.assertIn(self.sin_correo.codigo, pagina)
        self.assertIn("1144445555", pagina)
        self.assertIn(f"{HOY:%d/%m/%Y}", pagina)
        self.assertNotIn(self.venta.codigo, pagina)

    def test_ext_1a_2a_sin_ventas_para_decidir_lo_dice(self):
        """Extensión 1a.2a: «No hay ventas de tus contratos esperando una decisión que puedas registrar.»"""
        DetalleVenta.objects.filter(pk=self.d_sin.pk).update(estado_detalle_venta="abierto")
        CompraVenta.objects.filter(pk=self.sin_correo.pk).update(estado_venta="abierta")
        self.entrar(self.e.vendedor)
        self.assertIn("No hay ventas de tus contratos esperando una decisión que puedas registrar", texto(self.client.get(reverse("comercial:faltantes"))))

    def test_regla_la_lista_de_contratos_ofrece_el_enlace_con_la_cantidad_solo_al_vendedor(self):
        """El Vendedor ve «Faltantes para decidir (1)» en Contratos; el Gerente no (no puede decidir: el enlace no lo llevaría a un 403)."""
        self.entrar(self.e.vendedor)
        self.assertIn("Faltantes para decidir (1)", texto(self.client.get(reverse("comercial:contratos"))))
        self.entrar(crear_gerente())
        self.assertNotIn("Faltantes para decidir", texto(self.client.get(reverse("comercial:contratos"))))

    def test_regla_la_ficha_muestra_lo_pendiente_y_el_boton_solo_cuando_el_vendedor_puede(self):
        """`faltante.md`, «Lo que completa a COM-02»: la ficha dice «Pendiente de decisión del cliente», desde cuándo, hasta cuándo puede decidir y el estado del envío; «Registrar decisión de
        faltante» solo para el Vendedor del contrato y solo sin enlace que sirva; el Gerente ve el bloque pero no el botón. Ningún botón lleva a un 403."""
        con_enlace = reverse("comercial:compra_venta", args=[self.venta.pk])
        sin_enlace = reverse("comercial:compra_venta", args=[self.sin_correo.pk])
        self.entrar(self.e.vendedor)
        pagina = texto(self.client.get(con_enlace))
        self.assertIn("Pendiente de decisión del cliente", pagina)
        self.assertIn(f"hasta el <b>{self.enlace.fecha_vencimiento:%d/%m/%Y}</b>", pagina)
        self.assertNotIn("Registrar decisión de faltante", pagina)
        pagina = texto(self.client.get(sin_enlace))
        self.assertIn("El cliente no tiene correo", pagina)
        self.assertIn("Registrar decisión de faltante", pagina)
        self.assertEqual(self.client.get(reverse("comercial:faltante_decidir", args=[self.sin_correo.pk])).status_code, 200)
        EnlaceCliente.objects.filter(pk=self.enlace.pk).update(estado_envio="pendiente_envio")
        pagina = texto(self.client.get(con_enlace))
        self.assertIn("El correo no se pudo enviar", pagina)
        self.assertIn("Registrar decisión de faltante", pagina)
        self.entrar(crear_gerente())
        pagina = texto(self.client.get(sin_enlace))
        self.assertIn("Pendiente de decisión del cliente", pagina)
        self.assertNotIn("Registrar decisión de faltante", pagina)

    def test_flujo_principal_el_vendedor_decide_por_el_cliente_con_resumen_y_aviso(self):
        """Extensión 1a, con y sin HTMX: formulario → resumen → registrar, con el aviso breve y la vuelta a la ficha; la auditoría lleva al Vendedor."""
        self.entrar(self.e.vendedor)
        url = reverse("comercial:faltante_decidir", args=[self.sin_correo.pk])
        formulario = self.client.get(url)
        self.assertContains(formulario, "Registrar decisión de faltante")
        self.assertIn("en nombre de", texto(formulario))
        self.assertIn("1144445555", texto(formulario))
        resumen = self.client.post(url, self.formulario("rechazar", d=self.d_sin), **HTMX)
        self.assertIn("La compra quedará cancelada", texto(resumen))
        hecha = self.client.post(url, self.formulario("rechazar", accion="confirmar", d=self.d_sin))
        self.assertEqual((hecha.status_code, hecha["Location"]), (302, reverse("comercial:compra_venta", args=[self.sin_correo.pk])))
        self.assertIn(f"Registraste la decisión del cliente sobre el faltante de {self.sin_correo.codigo}.", self.avisos(hecha))
        self.assertEqual(CompraVenta.objects.get(pk=self.sin_correo.pk).estado_venta, "cancelada")
        registro = RegistroAuditoria.objects.get(accion="decision_faltante")
        self.assertEqual((registro.usuario_id, registro.rol), (self.e.vendedor.pk, "vendedor"))

    def test_ext_1a_una_venta_que_el_cliente_todavia_puede_decidir_vuelve_a_la_ficha_con_aviso(self):
        """Regla «Quién decide»: con correo y enlace vigente decide el cliente; la pantalla del Vendedor avisa y vuelve a la ficha (nada se registra)."""
        self.entrar(self.e.vendedor)
        respuesta = self.client.get(reverse("comercial:faltante_decidir", args=[self.venta.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(self.avisos(respuesta))
        self.assertEqual(DetalleVenta.objects.get(pk=self.detalle.pk).estado_detalle_venta, "pendiente_decision")

    def test_regla_otro_vendedor_no_decide_una_venta_ajena(self):
        """SEG-13: la venta de otro Vendedor da 403 (también por POST)."""
        self.entrar(crear_vendedor(email="otro@infoponia.com"))
        url = reverse("comercial:faltante_decidir", args=[self.sin_correo.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.formulario("rechazar", accion="confirmar", d=self.d_sin)).status_code, 403)
        self.assertEqual(DetalleVenta.objects.get(pk=self.d_sin.pk).estado_detalle_venta, "pendiente_decision")
