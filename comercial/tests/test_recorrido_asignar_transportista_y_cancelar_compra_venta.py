# Recorrido de COM-05b de punta a punta con el cliente de Django (D-96; docs/patrones/verificacion_a_mano.md): lo que haría una persona, por rol y por estado, con las pantallas y los servicios
# reales. El Gerente abre la alerta «entrega sin transportista» desde la campana, ve a Juan sin capacidad, elige a Ana, mira «Cómo queda» y asigna; el Vendedor cambia el transportista de otra
# entrega, una entrega atrasada sale hoy con el aviso de retraso y el correo al cliente, y dos pestañas sobre la misma entrega terminan en «La entrega cambió mientras la mirabas». Después el
# Vendedor cancela una compra-venta con todo (una cosecha, una entrega con envases, lo cosechado y lo de cámara), una «pendiente de decisión» (el enlace del correo deja de servir) y una de un
# cliente sin correo (imprime el comprobante); el Gerente cancela otra y el Vendedor recibe el aviso. No reemplaza la «Verificación a mano» del estudiante: lo que solo un navegador ve (CSRF
# real, `Origin`, JavaScript) va como paso de «navegador real» en el «Cierre» de la tarea.

from datetime import timedelta
from html import unescape

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente, Entrega, ReservaStock
from comercial.servicios import compra_ventas, entregas
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    escenario_comercial,
    reserva_lista,
    transportista_con_vehiculo,
    vehiculo_en_ruta,
    venta_con_todo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import ConfiguracionOperativa
from produccion.models import Cosecha, ReservaInsumo, StockCosechado
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
HTMX = {"HTTP_HX_REQUEST": "true"}


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeAsignarTransportistaYCancelarCompraVentaTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def avisos(self, cuenta):
        return [a.titulo for a in Notificacion.objects.filter(destinatario=cuenta).order_by("pk")]

    def sin_transportista(self, *, fecha=None, cantidad=100):
        """Una entrega «a realizar» sin transportista con su alerta, como la deja COM-PNF-ENT."""
        venta = compra_venta(self.e, dias=3)
        det = detalle(venta, self.e.variedad, cantidad)
        e = entrega(venta, [reserva_lista(det, self.lote, cantidad)], fecha=fecha)
        return venta, e, entregas._alerta_sin_transportista(e, venta, "capacidad de carga insuficiente")

    # ---------------------------------------------------------------- COM-ASG-TRP

    def test_recorrido_de_asignar_y_cambiar_el_transportista(self):
        # Datos: Juan con una camioneta de 5 kg (no alcanza para 15 kg) y Ana con un furgón de 400 kg.
        juan = transportista_con_vehiculo(self.e.invernadero, "5")
        ana = transportista_con_vehiculo(self.e.invernadero, "400")
        ConfiguracionOperativa.objects.update(cant_maxima_entregas_diarias=2, cant_max_ciudades_distintas_diarias=2)
        venta, e, alerta = self.sin_transportista()

        # 1. La campana del Gerente trae la alerta; abrirla lleva directo a «Asignar transportista · OT-…».
        self.entrar(self.gerente)
        self.assertIn("Entrega sin transportista", texto(self.client.get(reverse("alertas:lista"))))
        abrir = self.client.get(reverse("alertas:ir", args=[alerta.pk]))
        self.assertEqual(abrir["Location"], reverse("comercial:entrega_asignar", args=[e.pk]))
        pantalla = texto(self.client.get(abrir["Location"]))
        self.assertIn(f"Asignar transportista · {e.codigo}", pantalla)
        self.assertIn("Capacidad de carga insuficiente", pantalla)  # Juan: no se puede elegir
        self.assertRegex(pantalla, rf'id="t-{juan.pk}" value="{juan.pk}" disabled')

        # 2. Elegir a Ana muestra «Cómo queda» (HTMX) sin escribir; sin JavaScript, «Ver cómo queda» devuelve la página con la tarjeta.
        como = texto(self.client.post(reverse("comercial:entrega_asignar_calcular", args=[e.pk]), {"transportista": ana.pk}, **HTMX))
        self.assertIn("Carga del día", como)
        self.assertIn("de 400,00 kg", como)
        self.assertIn("Entregas del día", como)
        self.assertIn("Cómo queda", texto(self.client.post(reverse("comercial:entrega_asignar_calcular", args=[e.pk]), {"transportista": ana.pk})))
        self.assertIsNone(Entrega.objects.get(pk=e.pk).transportista_id)

        # 3. «Asignar transportista»: la alerta queda resuelta, Ana tiene el aviso y el Vendedor «OT-… ya tiene transportista»; la auditoría lo registra con el Gerente.
        huella = entregas.datos_de_asignacion(self.gerente, e.pk).huella
        respuesta = self.client.post(reverse("comercial:entrega_asignar", args=[e.pk]), {"transportista": ana.pk, "huella": huella}, follow=True)
        self.assertRedirects(respuesta, reverse("comercial:entregas"))
        self.assertIn(f"{e.codigo} asignada a {ana.get_full_name()}.", [m.message for m in respuesta.context["messages"]])
        alerta.refresh_from_db()
        self.assertEqual((Entrega.objects.get(pk=e.pk).transportista_id, alerta.estado_alerta), (ana.pk, "resuelta"))
        self.assertIn(f"Nueva entrega para el {e.fecha_programada_orden:%d/%m}", self.avisos(ana))
        self.assertIn(f"{e.codigo} ya tiene transportista", self.avisos(self.e.vendedor))
        registro = RegistroAuditoria.objects.filter(accion="asignacion_transportista").latest("pk")
        self.assertEqual(registro.usuario_id, self.gerente.pk)

        # 4. El Vendedor, en «Entregas», cambia el transportista de una entrega de Ana para mañana: Ana recibe «Ya no tenés la entrega…».
        otra_venta = compra_venta(self.e, dias=1)
        otra = entrega(otra_venta, [reserva_lista(detalle(otra_venta, self.e.variedad, 20), self.lote, 20)], transportista=ana)
        nuevo = transportista_con_vehiculo(self.e.invernadero, "400")
        self.entrar(self.e.vendedor)
        lista = texto(self.client.get(reverse("comercial:entregas")))
        self.assertIn("Cambiar transportista", lista)
        self.assertNotIn("Asignar transportista", lista)  # la primera ya tiene transportista
        cambio = self.client.get(reverse("comercial:entrega_asignar", args=[otra.pk]))
        self.assertIn(f"Cambiar transportista · {otra.codigo}", texto(cambio))
        self.assertNotIn(f'value="{ana.pk}"', texto(cambio))  # el actual no se ofrece
        huella = entregas.datos_de_asignacion(self.e.vendedor, otra.pk).huella
        self.client.post(reverse("comercial:entrega_asignar", args=[otra.pk]), {"transportista": nuevo.pk, "huella": huella})
        self.assertEqual(Entrega.objects.get(pk=otra.pk).transportista_id, nuevo.pk)
        self.assertIn(f"Ya no tenés la entrega {otra.codigo}", self.avisos(ana))

        # 5. Una entrega de fecha pasada: la pantalla avisa que sale hoy; al asignarla, la fecha pasa a hoy, el Vendedor recibe «Entrega con retraso» y el cliente, el correo con la fecha nueva.
        _, atrasada, _ = self.sin_transportista(fecha=HOY - timedelta(days=2), cantidad=50)
        self.assertIn("La fecha ya pasó: la entrega se reprogramará para hoy", texto(self.client.get(reverse("comercial:entrega_asignar", args=[atrasada.pk]))))
        huella = entregas.datos_de_asignacion(self.e.vendedor, atrasada.pk).huella
        with self.captureOnCommitCallbacks(execute=True):
            hecho = self.client.post(reverse("comercial:entrega_asignar", args=[atrasada.pk]), {"transportista": nuevo.pk, "huella": huella}, follow=True)
        self.assertIn("Se reprogramó para hoy y se avisó el retraso.", " ".join(m.message for m in hecho.context["messages"]))
        self.assertEqual(Entrega.objects.get(pk=atrasada.pk).fecha_programada_orden, HOY)
        self.assertIn(f"Entrega con retraso: {atrasada.codigo}", self.avisos(self.e.vendedor))
        self.assertEqual([m.subject for m in mail.outbox], [f"Cambió la fecha de tu entrega {atrasada.codigo}: ahora es el {HOY:%d/%m}"])

        # 6. Dos pestañas sobre la misma entrega: asigno en una y después en la otra, que ve «La entrega cambió mientras la mirabas».
        _, doble, _ = self.sin_transportista(cantidad=30)
        vieja = entregas.datos_de_asignacion(self.e.vendedor, doble.pk).huella
        self.client.post(reverse("comercial:entrega_asignar", args=[doble.pk]), {"transportista": ana.pk, "huella": vieja})
        segunda = self.client.post(reverse("comercial:entrega_asignar", args=[doble.pk]), {"transportista": nuevo.pk, "huella": vieja}, follow=True)
        self.assertIn("La entrega cambió mientras la mirabas", " ".join(m.message for m in segunda.context["messages"]))
        self.assertEqual(Entrega.objects.get(pk=doble.pk).transportista_id, ana.pk)

        # 7. Por rol: el Agrónomo, el Capataz y el Vendedor de otra venta no entran (403); una entrega en curso no se reasigna.
        for ajeno in (self.e.agronomo, self.e.capataz):
            self.entrar(ajeno)
            self.assertEqual(self.client.get(reverse("comercial:entrega_asignar", args=[e.pk])).status_code, 403)
        venta_hoy = compra_venta(self.e, dias=0)
        en_curso = entrega(venta_hoy, [reserva_lista(detalle(venta_hoy, self.e.variedad, 10), self.lote, 10)], transportista=juan)
        vehiculo_en_ruta(juan)
        self.entrar(self.e.vendedor)
        self.assertIn("ya inició la ruta", texto(self.client.get(reverse("comercial:entrega_asignar", args=[en_curso.pk]))))
        self.assertIn("En curso", texto(self.client.get(reverse("comercial:entregas"))))

    # ---------------------------------------------------------------- COM-CNL-CVT

    def test_recorrido_de_cancelar_una_compra_venta(self):
        transportista = transportista_con_vehiculo(self.e.invernadero, "800")
        v = venta_con_todo(self.e, transportista=transportista, con_envases=True)
        codigo = v.venta.codigo

        # 1. El Vendedor abre la ficha de la venta y toca «Cancelar compra-venta»: la pantalla dice qué se cancela, qué pasa con el producto y pide el motivo.
        self.entrar(self.e.vendedor)
        ficha = texto(self.client.get(reverse("comercial:compra_venta", args=[v.venta.pk])))
        self.assertIn("Cancelar compra-venta", ficha)
        pantalla = texto(self.client.get(reverse("comercial:compra_venta_cancelar", args=[v.venta.pk])))
        self.assertIn("Entra a la cámara: 20 plantas", pantalla)
        self.assertIn(f"Se cancela la cosecha {v.cosecha.codigo}", pantalla)
        self.assertIn(f"Se cancela la entrega {v.entrega.codigo}", pantalla)

        # 2. Sin motivo, el error sale junto a los botones y no pasa nada; con «El cliente desistió» y «Revisar y cancelar» sale el resumen (ventana con HTMX; página sin él) y tampoco escribe.
        huella = compra_ventas.datos_de_cancelacion(self.e.vendedor, v.venta.pk).huella
        url_revisar = reverse("comercial:compra_venta_cancelar_revisar", args=[v.venta.pk])
        self.assertIn("Elegí el motivo de la cancelación.", texto(self.client.post(url_revisar, {"huella": huella})))
        ventana = texto(self.client.post(url_revisar, {"motivo": "cliente_desistio", "descripcion": "Ya no lo necesita", "huella": huella}, **HTMX))
        self.assertIn("data-ventana", ventana)
        self.assertIn("Confirmar cancelación", ventana)
        self.assertIn("La cancelación no se puede deshacer.", texto(self.client.post(url_revisar, {"motivo": "cliente_desistio", "huella": huella})))
        self.assertEqual(CompraVenta.objects.get(pk=v.venta.pk).estado_venta, "abierta")

        # 3. «Confirmar cancelación»: la venta queda cancelada con su motivo y su fecha, la cosecha y la entrega canceladas, lo cosechado en la cámara, las bandejas libres y el cliente con su comprobante.
        with self.captureOnCommitCallbacks(execute=True):
            hecho = self.client.post(reverse("comercial:compra_venta_cancelar", args=[v.venta.pk]), {"motivo": "cliente_desistio", "descripcion": "Ya no lo necesita", "huella": huella}, follow=True)
        mensajes = [m.message for m in hecho.context["messages"]]
        self.assertIn(f"{codigo} cancelada. Se canceló 1 cosecha y 1 entrega; 20 plantas entraron a la cámara.", " ".join(mensajes))
        self.assertIn(f"Se envió el comprobante a {v.venta.cliente.email_cliente}.", " ".join(mensajes))
        ficha = texto(hecho)
        self.assertIn(f"Cancelada el {HOY:%d/%m/%Y}. Motivo: el cliente desistió.", ficha)
        self.assertNotIn("Cancelar compra-venta", ficha)
        venta = CompraVenta.objects.get(pk=v.venta.pk)
        self.assertEqual((venta.estado_venta, venta.motivo_cancelacion_venta, venta.estado_comprobante), ("cancelada", "cliente_desistio", "enviado"))
        self.assertEqual(Cosecha.objects.get(pk=v.cosecha.pk).estado_orden, "cancelada")
        self.assertEqual(Entrega.objects.get(pk=v.entrega.pk).estado_orden, "cancelada")
        self.assertEqual(StockCosechado.objects.get(motivo_cosechado="cancelacion_cliente").cantidad_disponible_cosechado, 20)
        self.assertEqual(list(ReservaInsumo.objects.filter(orden=v.entrega).values_list("estado", flat=True)), ["cancelada"])
        self.assertFalse(ReservaStock.objects.filter(detalle_venta__compra_venta=venta).exclude(estado_reserva="liberada").exists())
        self.assertEqual(
            sorted(DetalleVenta.objects.filter(compra_venta=venta).values_list("estado_detalle_venta", flat=True)), ["cancelado", "cancelado"]
        )
        self.assertEqual([m.subject for m in mail.outbox], [f"Cancelación de tu compra {codigo}"])

        # 4. Avisos: el Capataz y el Agrónomo de la cosecha, el transportista de la entrega; auditoría con el Vendedor.
        self.assertIn(f"Orden {v.cosecha.codigo} cancelada", self.avisos(self.e.capataz))
        self.assertIn(f"Orden {v.cosecha.codigo} cancelada", self.avisos(self.e.agronomo))
        self.assertIn(f"Se canceló la entrega {v.entrega.codigo}", self.avisos(transportista))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_compra_venta").latest("pk").usuario_id, self.e.vendedor.pk)

        # 5. Una venta «pendiente de decisión del cliente»: al cancelarla, el enlace del correo dice «Este enlace no se puede usar».
        p = venta_con_todo(self.e, pendiente=True)
        self.assertEqual(EnlaceCliente.objects.get(pk=p.enlace.pk).estado, "vigente")
        self.assertEqual(Client().get(f"/cliente/{p.token}/", follow=True).status_code, 200)
        huella_p = compra_ventas.datos_de_cancelacion(self.e.vendedor, p.venta.pk).huella
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("comercial:compra_venta_cancelar", args=[p.venta.pk]), {"motivo": "cliente_no_retiro", "huella": huella_p})
        self.assertEqual(EnlaceCliente.objects.get(pk=p.enlace.pk).estado, "anulado")
        self.assertIn("Este enlace no se puede usar", texto(Client().get(f"/cliente/{p.token}/", follow=True)))

        # 6. Un cliente sin correo: al terminar, «El cliente no tiene correo: imprimí el comprobante.» y el botón «Imprimir comprobante»; la página imprimible dice la cancelación.
        s = venta_con_todo(self.e)
        s.venta.cliente.__class__.objects.filter(pk=s.venta.cliente_id).update(email_cliente="")
        huella_s = compra_ventas.datos_de_cancelacion(self.e.vendedor, s.venta.pk).huella
        with self.captureOnCommitCallbacks(execute=True):
            sin_correo = self.client.post(reverse("comercial:compra_venta_cancelar", args=[s.venta.pk]), {"motivo": "otro", "huella": huella_s}, follow=True)
        self.assertIn("El cliente no tiene correo: imprimí el comprobante.", " ".join(m.message for m in sin_correo.context["messages"]))
        self.assertIn("Imprimir comprobante", texto(sin_correo))
        imprimible = texto(self.client.get(reverse("comercial:compra_venta_comprobante", args=[s.venta.pk])))
        self.assertIn(f"Cancelación de la compra {s.venta.codigo}", imprimible)

        # 7. El Gerente cancela otra venta: el Vendedor del contrato recibe «CV-… cancelada».
        g = venta_con_todo(self.e)
        self.entrar(self.gerente)
        huella_g = compra_ventas.datos_de_cancelacion(self.gerente, g.venta.pk).huella
        self.client.post(reverse("comercial:compra_venta_cancelar", args=[g.venta.pk]), {"motivo": "cliente_desistio", "huella": huella_g})
        self.assertIn(f"{g.venta.codigo} cancelada", self.avisos(self.e.vendedor))

        # 8. Una venta ya cancelada no se vuelve a cancelar (la pantalla lo dice) y el Agrónomo no entra (403).
        self.assertIn("ya está cancelada", texto(self.client.get(reverse("comercial:compra_venta_cancelar", args=[g.venta.pk]))))
        self.entrar(self.e.agronomo)
        self.assertEqual(self.client.get(reverse("comercial:compra_venta_cancelar", args=[g.venta.pk])).status_code, 403)
