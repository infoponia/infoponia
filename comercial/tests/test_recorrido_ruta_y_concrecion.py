# Recorrido de COM-06a de punta a punta con el cliente de Django (D-96; docs/patrones/verificacion_a_mano.md): lo que haría una persona, por rol y por estado, con las pantallas y los servicios reales. Sigue los
# pasos de la «Verificación a mano» de la tarea: el Transportista ve su ruta (una compra-venta con envasado, un suministro y otra venta), la inicia, y con el Vendedor se comprueba que la entrega ya no se
# reasigna; concreta la venta (5 perdidas y un envase de más) y el suministro (80 recibidas: discrepancia para el Gerente), registra un intento fallido, intenta finalizar con una pendiente y finaliza;
# el Vendedor concreta un retiro con transferencia; el Gerente no puede quitar ni dar de baja a un transportista en ruta. Todo con formularios comunes (sin JavaScript) y con los correos y avisos reales.
# No reemplaza la «Verificación a mano» del estudiante: lo que solo un navegador ve (CSRF real, `Origin`, JavaScript, el ancho de un celular) va como paso de «navegador real» en el «Cierre» de la tarea.

from datetime import timedelta
from decimal import Decimal
from html import unescape

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, CompraVenta, DiscrepanciaEntrega, Entrega, IntentoFallido, PagoCliente, Vehiculo
from comercial.servicios import entregas, rutas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    entrega,
    envase,
    escenario_comercial,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_solicitudes,
)
from core.models import Notificacion, RegistroAuditoria
from core.servicios import baja_usuario
from core.tests.fabricas import crear_gerente
from inventario.models import LoteInsumo
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta
from maestros.servicios import transportistas as servicio_de_transportistas
from produccion.models import Consumo, Merma
from produccion.tests.fabricas import lote_maduro, reservar

HOY = timezone.localdate()
HTMX = {"HTTP_HX_REQUEST": "true"}


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


def huella_de(respuesta):
    """La huella del resumen que la pantalla manda en un campo oculto."""
    html = respuesta.content.decode()  # crudo: la huella es JSON y la plantilla escapa sus comillas (&quot;)
    i = html.index('name="huella" value="') + len('name="huella" value="')
    return unescape(html[i : html.index('"', i)])


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeRutaYConcrecionTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def avisos(self, cuenta):
        return [a.titulo for a in Notificacion.objects.filter(destinatario=cuenta).order_by("pk")]

    def concretar(self, entrega_, datos, **extra):
        """Los dos pasos de la pantalla: «Ver resumen» (con o sin HTMX) y «Confirmar entrega», con los correos que salen al confirmar."""
        resumen = self.client.post(reverse("comercial:entrega_concretar_calcular", args=[entrega_.pk]), datos, **extra)
        self.assertContains(resumen, "Confirmar entrega")
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("comercial:entrega_concretar", args=[entrega_.pk]), {**datos, "huella": huella_de(resumen)})

    def test_recorrido_de_la_ruta_a_la_concrecion_el_intento_fallido_y_el_retiro(self):
        # ---- datos de la «Verificación a mano»: una venta con envasado, un suministro con mínimo 100 y otra venta, las tres para hoy y del mismo transportista ----
        venta = compra_venta(self.e, dias=0)
        det_venta = detalle(venta, self.e.variedad, 50)
        e_venta = entrega(venta, [reserva_lista(det_venta, self.lote, 50)], transportista=self.t, fecha=HOY)
        bandeja = envase(self.e.invernadero, stock=30)
        reservar(e_venta, bandeja, 10)
        sum_ = suministro(self.e, plazo_pago=15)
        det_sum = detalle_suministro(sum_, self.e.variedad, cantidad=100, minima=100, primera_en_dias=0)
        e_sum = entrega(sum_, [reserva_lista(None, self.lote, 100, fecha_entrega=det_sum.fecha_primer_entrega, detalle_suministro=det_sum)], transportista=self.t, fecha=HOY)
        otra = compra_venta(self.e, dias=0)
        e_otra = entrega(otra, [reserva_lista(detalle(otra, self.e.variedad, 10), self.lote, 10)], transportista=self.t, fecha=HOY)

        # ---- 1. Mi ruta: las tres entregas, el peso y la capacidad; sin «Concretar» hasta iniciar ----
        self.entrar(self.t)
        html = texto(self.client.get(reverse("comercial:ruta")))
        for e in (e_venta, e_sum, e_otra):
            self.assertIn(e.codigo, html)
        self.assertIn("800", html)
        self.assertNotIn(reverse("comercial:entrega_concretar", args=[e_venta.pk]), html)
        pagina = self.client.get(reverse("comercial:ruta_iniciar"))
        self.assertContains(pagina, "Iniciar ruta")
        self.assertRedirects(self.client.post(reverse("comercial:ruta_iniciar"), {"huella": huella_de(pagina)}), reverse("comercial:ruta"))
        html = texto(self.client.get(reverse("comercial:ruta")))
        for e in (e_venta, e_sum, e_otra):
            self.assertIn(reverse("comercial:entrega_concretar", args=[e.pk]), html)
            self.assertIn(reverse("comercial:entrega_intento_fallido", args=[e.pk]), html)
        # con el Vendedor: cambiarle el transportista a una no deja («en curso»)
        self.entrar(self.e.vendedor)
        self.assertContains(self.client.get(reverse("comercial:entrega_asignar", args=[e_venta.pk])), "ya inició la ruta")

        # ---- 7. con la ruta iniciada, el Gerente no puede quitar al transportista del invernadero ni darle de baja la cuenta ----
        with self.assertRaises(ValidationError):
            servicio_de_transportistas.quitar_transportista(self.gerente, self.e.invernadero.pk, self.t.pk)
        with self.assertRaises(ValidationError) as c:
            baja_usuario(self.gerente, self.t.pk)
        self.assertEqual([e.code for e in c.exception.error_list], ["transportista_en_ruta"])

        # ---- 2. concretar la compra-venta: 5 perdidas, el resto aceptado, un envase de más ----
        self.entrar(self.t)
        linea = e_venta.lineas.get().pk
        datos = {f"llego_{linea}": "45", f"acepta_{linea}": "1", f"utilizada_{bandeja.pk}": "11", f"confirmo_exceso_{bandeja.pk}": "1", "medio_pago": "efectivo", "descripcion_perdida": "Se cayó una bandeja"}
        resumen = self.client.post(reverse("comercial:entrega_concretar_calcular", args=[e_venta.pk]), datos)
        for esperado in ("5", "1 de más", "4.500,00", "efectivo"):
            self.assertIn(esperado, texto(resumen))
        respuesta = self.concretar(e_venta, datos)
        self.assertRedirects(respuesta, reverse("comercial:entrega_comprobante", args=[e_venta.pk]))
        self.assertEqual(Entrega.objects.get(pk=e_venta.pk).estado_orden, "concretada")
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_venta, "concretada")
        self.assertEqual(PagoCliente.objects.get(compra_venta=venta).monto_pagado, Decimal("4500.00"))
        self.assertEqual(Merma.objects.get().cant_merma, 5)
        self.assertEqual(Consumo.objects.get().cant_consumo, Decimal("11"))
        self.assertEqual(sum(LoteInsumo.objects.filter(insumo_invernadero=bandeja).values_list("cantidad_disponible", flat=True)), Decimal("19"))
        self.assertTrue(any("1 de más" in n.detalle for n in Notificacion.objects.filter(destinatario=self.e.agronomo)))
        self.assertIn(f"Se concretó con diferencias: {e_venta.codigo}", self.avisos(self.e.vendedor))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Comprobante de tu compra", mail.outbox[0].subject)
        comprobante = texto(self.client.get(reverse("comercial:entrega_comprobante", args=[e_venta.pk])))
        self.assertIn("Imprimir comprobante", comprobante)
        self.assertIn("Total cobrado", comprobante)

        # ---- 3. concretar el suministro con 80 recibidas: discrepancia para el Gerente, su alerta y el comprobante sin enlace ----
        linea = e_sum.lineas.get().pk
        datos = {f"llego_{linea}": "100", f"recibio_{linea}": "80", "sin_envases": "1"}
        self.concretar(e_sum, datos, **HTMX)  # con HTMX el resumen es solo un fragmento
        discrepancia = DiscrepanciaEntrega.objects.get()
        self.assertEqual((discrepancia.estado_solicitud, discrepancia.lineas.get().cantidad_entregada), ("pendiente", 80))
        self.assertEqual(Entrega.objects.get(pk=e_sum.pk).fecha_vencimiento_pago, HOY + timedelta(days=15))
        self.assertEqual(Alerta.objects.get(tipo_alerta="comercial_discrepancia_entrega").estado_alerta, "activa")
        self.assertEqual(AlertaComercial.objects.filter(solicitud=discrepancia).count(), 1)
        # Los 80 recibidos devuelven 20 plantas a la cámara y PROD-ASG-CAM las asigna al período siguiente del suministro, que se planifica solo (su propio correo de «Tu entrega del …»):
        # por eso se busca el comprobante por su asunto y no por la cantidad de correos.
        comprobantes = [m for m in mail.outbox if m.subject.startswith("Comprobante de tu entrega")]
        self.assertEqual(len(comprobantes), 1)
        self.assertNotIn("http", comprobantes[0].body)
        self.assertIn("Vence el pago", comprobantes[0].body)
        self.entrar(self.e.vendedor)
        ficha = texto(self.client.get(reverse("comercial:suministro", args=[sum_.pk])))
        self.assertIn(discrepancia.codigo, ficha)
        self.assertIn(f"{HOY + timedelta(days=15):%d/%m/%Y}", ficha)
        self.assertIn("Entregado", ficha)

        # ---- 5. finalizar con una pendiente no deja y ofrece concretar o el intento fallido; ----
        self.entrar(self.t)
        pantalla = texto(self.client.get(reverse("comercial:ruta_finalizar")))
        self.assertIn(reverse("comercial:entrega_intento_fallido", args=[e_otra.pk]), pantalla)
        self.assertRedirects(self.client.post(reverse("comercial:ruta_finalizar")), reverse("comercial:ruta_finalizar"), fetch_redirect_response=False)
        self.assertTrue(Vehiculo.objects.get(transportista=self.t).esta_en_ruta(HOY))
        # ---- 4. intento fallido de la otra: pasa a mañana sin transportista y se avisa al Vendedor y al cliente ----
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(
                self.client.post(reverse("comercial:entrega_intento_fallido", args=[e_otra.pk]), {"motivo": "cliente_ausente", "descripcion": "Nadie atendió"}), reverse("comercial:ruta")
            )
        e = Entrega.objects.get(pk=e_otra.pk)
        self.assertEqual((e.fecha_programada_orden, e.transportista_id), (HOY + timedelta(days=1), None))
        self.assertEqual(IntentoFallido.objects.get().motivo, "cliente_ausente")
        self.assertIn(f"No se pudo entregar {e_otra.codigo}", self.avisos(self.e.vendedor))
        avisos_de_intento = [m for m in mail.outbox if m.subject.startswith("No pudimos entregar tu pedido")]
        self.assertEqual(len(avisos_de_intento), 1)
        self.assertIn("cliente ausente", avisos_de_intento[0].body)
        # sin pendientes, finaliza
        self.assertRedirects(self.client.post(reverse("comercial:ruta_finalizar")), reverse("comercial:ruta"))
        self.assertFalse(Vehiculo.objects.get(transportista=self.t).esta_en_ruta(HOY))
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=["inicio_ruta", "fin_ruta", "concrecion_entrega", "intento_fallido_entrega"]).count(), 5)

        # ---- 6. el Vendedor concreta un retiro desde «Entregas» con cobro por transferencia ----
        retiro = compra_venta(self.e, dias=0, modalidad="retiro")
        e_retiro = entrega(retiro, [reserva_lista(detalle(retiro, self.e.variedad, 20), self.lote, 20)], fecha=HOY)
        self.entrar(self.e.vendedor)
        self.assertContains(self.client.get(reverse("comercial:entregas")), reverse("comercial:entrega_concretar", args=[e_retiro.pk]))
        linea = e_retiro.lineas.get().pk
        self.concretar(e_retiro, {f"llego_{linea}": "20", f"acepta_{linea}": "1", "sin_envases": "1", "medio_pago": "transferencia"})
        self.assertEqual(PagoCliente.objects.get(compra_venta=retiro).medio_pago, "transferencia")
        self.assertEqual(CompraVenta.objects.get(pk=retiro.pk).estado_venta, "concretada")

        # ---- roles: ni el Gerente ni el Agrónomo ven «Concretar» ni lo pueden abrir ----
        self.entrar(self.gerente)
        self.assertEqual(self.client.get(reverse("comercial:entrega_concretar", args=[e_otra.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("comercial:entregas")), "Concretar retiro")
        # la ficha del cliente informa lo que se debe y la discrepancia
        ficha = texto(self.client.get(reverse("comercial:cliente", args=[self.e.cliente.pk])))
        self.assertIn("Entregas sin cobrar", ficha)
        self.assertIn(discrepancia.codigo, ficha)
        # ---- al terminar, nada quedó a medias ----
        self.assertEqual(entregas.estado_de_pago([e_sum.pk], HOY)[e_sum.pk], "pendiente")
        self.assertEqual(rutas.ruta_del_dia(self.t).cantidad, 0)
