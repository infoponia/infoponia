# Recorrido de COM-04a de punta a punta con el cliente de Django (D-96; docs/patrones/verificacion_a_mano.md): lo que haría una persona, por rol y por estado, con las
# pantallas y los servicios reales: el Vendedor registra una compra-venta con envío (se programa una cosecha automática), el Agrónomo la ve en la lista, la modifica y planifica
# otra sin contrato, el Capataz concreta las dos desde su bandeja (con plantas perdidas y faltante) y el Agrónomo cancela una cosecha con contrato. No reemplaza la «Verificación a mano»
# del estudiante: lo que solo un navegador ve (CSRF real, `Origin`, JavaScript) va como paso de «navegador real» en el «Cierre» de la tarea.

from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta, DetalleReserva, DetalleVenta, ReservaStock
from comercial.servicios import compra_ventas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.tests.fabricas import escenario_comercial, verificar_invariantes_de_reservas
from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Bitacora, Cosecha, Lote, MovimientoStock, StockCosechado
from produccion.tests.fabricas import lote_maduro

HTMX = {"HTTP_HX_REQUEST": "true"}
HOY = timezone.localdate()


def iso(dias):
    return str(HOY + timedelta(days=dias))


def texto(respuesta):
    from html import unescape

    return unescape(respuesta.content.decode())


class RecorridoDeCosechasTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.sector = self.e.sectores["maduracion"]
        self.addCleanup(verificar_invariantes_de_reservas)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def avisos(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]

    def confirmar(self, vista_revisar, vista_confirmar, argumentos, datos):
        """Los dos pasos de una pantalla sin JavaScript: «Ver resumen» (con su firma) y «Confirmar»."""
        resumen = self.client.post(reverse(vista_revisar, args=argumentos), datos)
        self.assertEqual(resumen.status_code, 200)
        return self.client.post(reverse(vista_confirmar, args=argumentos), {**datos, "firma": resumen.context["firma"]})

    def test_recorrido_de_las_cosechas_por_rol_y_por_estado(self):
        # 1. El Vendedor registra una compra-venta con envío de 100 plantas para dentro de 3 días: se programa una cosecha automática.
        datos = DatosDeCompraVenta(
            cliente_id=str(self.e.cliente.pk), fecha_pactada=iso(3), modalidad="envio", direccion_id=str(self.e.direccion.pk),
            renglones=[Renglon(0, str(self.e.variedad.pk), "100", "100")],
        )
        venta = compra_ventas.registrar_compra_venta(self.e.vendedor, datos)
        automatica = Cosecha.objects.get()
        self.assertEqual(automatica.origen_cosecha, "automatica")

        # 2. El Agrónomo la ve en «Producción» › órdenes con su contrato, el origen «Automática» y sus botones.
        self.entrar(self.e.agronomo)
        lista = texto(self.client.get(reverse("produccion:ordenes") + "?tipo=cosecha"))
        for esperado in (automatica.codigo, venta.codigo, "Automática", "Modificar", "Cancelar", "Planificar cosecha"):
            self.assertIn(esperado, lista)
        # 2a. «Modificar»: fecha posterior a la entrega → advertencia de retraso; antes de la primera admitida → error con esa fecha; un total distinto → no deja terminar.
        url_modificar = reverse("comercial:cosecha_modificar", args=[automatica.pk])
        base = {"fecha_programada": str(automatica.fecha_programada_orden), "prioridad": "media", "descripcion": "", f"lote_{self.lote.pk}": "100"}
        base["huella"] = self.client.get(url_modificar).context["huella"]
        retraso = texto(self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[automatica.pk]), {**base, "fecha_programada": iso(6)}))
        self.assertIn("saldrá con retraso", retraso)
        antes = texto(self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[automatica.pk]), {**base, "fecha_programada": iso(-1)}))
        self.assertIn("anterior a hoy", antes)
        distinto = texto(self.client.post(reverse("comercial:cosecha_modificar_revisar", args=[automatica.pk]), {**base, f"lote_{self.lote.pk}": "90"}))
        self.assertIn("no coincide con el reservado", distinto)
        # 2b. Dejarlo como estaba y cambiar la prioridad: el resumen muestra antes y después y el Capataz tiene la notificación.
        respuesta = self.confirmar("comercial:cosecha_modificar_revisar", "comercial:cosecha_modificar", [automatica.pk], {**base, "prioridad": "alta"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Cosecha.objects.get(pk=automatica.pk).prioridad_orden, "alta")
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.capataz, titulo=f"Cosecha {automatica.codigo} modificada").exists())

        # 3. «Planificar cosecha» sin contrato: 40 plantas del lote. Queda «Manual», «Sin contrato».
        calculo = self.client.post(reverse("comercial:cosecha_planificar_calcular"), {"invernadero": str(self.e.invernadero.pk), "modo": "sin"}, **HTMX)
        self.assertIn(str(self.e.variedad), texto(calculo))
        planificacion = {
            "invernadero": str(self.e.invernadero.pk), "modo": "sin", "variedad": str(self.e.variedad.pk), "fecha_programada": iso(1), "prioridad": "media",
            "descripcion": "", f"lote_{self.lote.pk}": "40",
        }
        self.confirmar("comercial:cosecha_planificar_revisar", "comercial:cosecha_planificar", [], planificacion)
        sin_contrato = Cosecha.objects.get(origen_cosecha="manual")
        self.assertIsNone(ReservaStock.objects.get(cosecha=sin_contrato).detalle_venta_id)
        lista = texto(self.client.get(reverse("produccion:ordenes") + "?tipo=cosecha"))
        self.assertIn("Manual", lista)
        self.assertIn("Sin contrato", lista)

        # 4. El Capataz ve las dos en su bandeja y concreta la automática: propone 100; cosecha 90 y declara 4 perdidas por «Plaga».
        self.entrar(self.e.capataz)
        bandeja = texto(self.client.get(reverse("produccion:bandeja")))
        self.assertIn(automatica.codigo, bandeja)
        self.assertIn(sin_contrato.codigo, bandeja)
        self.assertIn('placeholder="100"', texto(self.client.get(reverse("comercial:cosecha_concretar", args=[automatica.pk]))))
        concrecion = {
            "fecha_efectiva": iso(0), f"cant_{self.lote.pk}_{self.sector.pk}": "90", f"perd_{self.lote.pk}_{self.sector.pk}": "4", f"causa_{self.lote.pk}": "plaga", f"desc_{self.lote.pk}": "",
        }
        resumen = texto(self.client.post(reverse("comercial:cosecha_concretar_revisar", args=[automatica.pk]), concrecion))
        self.assertIn("Faltan 10", resumen)
        self.confirmar("comercial:cosecha_concretar_revisar", "comercial:cosecha_concretar", [automatica.pk], concrecion)
        self.assertEqual(Cosecha.objects.get(pk=automatica.pk).estado_orden, "concretada")
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 300 - 90 - 4)
        # Como el lote tenía más stock libre, se programó una cosecha «Encadenada» para el faltante.
        encadenada = Cosecha.objects.get(origen_cosecha="encadenada")
        self.assertEqual(DetalleReserva.objects.get(reserva__cosecha=encadenada).cantidad_reservada, 10)
        self.assertEqual(DetalleVenta.objects.get(compra_venta=venta).estado_detalle_venta, "abierto")

        # 5. Concreta la sin contrato con 40: en la auditoría queda la concreción y la partida P-… de 40 plantas.
        self.confirmar("comercial:cosecha_concretar_revisar", "comercial:cosecha_concretar", [sin_contrato.pk], {"fecha_efectiva": iso(0)})
        partida = StockCosechado.objects.get(motivo_cosechado="cosecha_del_agronomo")
        self.assertEqual(partida.cantidad_ingreso_cosechado, 40)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="concrecion_cosecha", afectados__contains=[{"modelo": "produccion.stockcosechado", "id": partida.pk, "texto": partida.codigo}]).exists())
        self.assertEqual(Bitacora.objects.filter(tipo_evento="cosecha").count(), 2)
        self.assertEqual(MovimientoStock.objects.filter(tipo_movimiento="ingreso_a_camara").count(), 1)

        # 6. El Agrónomo cancela la encadenada (con contrato): la ventana estima cuánto se vuelve a cubrir sin sus lotes; con el motivo vacío, error.
        self.entrar(self.e.agronomo)
        pagina = self.client.get(reverse("comercial:cosecha_cancelar", args=[encadenada.pk]))
        self.assertIn("Qué pasa con el contrato", texto(pagina))
        huella = pagina.context["resumen"].huella
        vacio = self.client.post(reverse("comercial:cosecha_cancelar", args=[encadenada.pk]), {"motivo": "", "huella": huella})
        self.assertIn("Indicá el motivo", texto(vacio))
        respuesta = self.client.post(reverse("comercial:cosecha_cancelar", args=[encadenada.pk]), {"motivo": "Cambió el pedido", "huella": huella})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Cosecha.objects.get(pk=encadenada.pk).estado_orden, "cancelada")
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_venta, "abierta")

        # 7. Los roles que no tienen estas pantallas no las ven (403) y el Gerente solo mira la lista.
        self.entrar(self.e.vendedor)
        self.assertEqual(self.client.get(reverse("comercial:cosecha_planificar")).status_code, 403)
