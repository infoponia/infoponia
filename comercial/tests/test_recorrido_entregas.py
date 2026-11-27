# Recorrido de COM-05a1 de punta a punta con el cliente de Django (D-96; `docs/patrones/verificacion_a_mano.md`): como una persona, por rol y por estado. El Vendedor registra una
# compra-venta que sale de cámara y la entrega se planifica sola (con transportista, avisos y correo pendiente); sin flota la entrega queda sin transportista y la campana del Gerente lo
# dice y lleva a la lista; el paso 50 (`proceso_diario`) le consigue transportista y resuelve la alerta; la baja de la cuenta del transportista y el vencimiento en cámara cambian la entrega;
# y la ficha del invernadero › «Logística» lleva a la lista. No reemplaza la «Verificación a mano»: el cliente de Django no ve el CSRF, el encabezado `Origin` ni el JavaScript.

from datetime import timedelta
from html import unescape
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega
from comercial.servicios import camara, compra_ventas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.tests.fabricas import (
    escenario_comercial,
    partida_cosechada,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion
from core.servicios import baja_usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


def texto(respuesta):
    return unescape(respuesta.content.decode())


class RecorridoDeEntregasTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.gerente = crear_gerente()
        self.camioneta = transportista_con_vehiculo(self.e.invernadero, "800")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def registrar(self, cantidad="30", dias=3):
        """El Vendedor registra una compra-venta con envío (con la cámara llena, sale toda de cámara) y se ejecutan los `on_commit`."""
        datos = DatosDeCompraVenta(
            vendedor_id="",
            cliente_id=str(self.e.cliente.pk),
            fecha_pactada=(HOY + timedelta(days=dias)).isoformat(),
            modalidad="envio",
            direccion_id=str(self.e.direccion.pk),
            invernadero_id="",
            renglones=[Renglon(0, str(self.e.variedad.pk), cantidad, "1500,50")],
        )
        with self.captureOnCommitCallbacks(execute=True):
            return compra_ventas.registrar_compra_venta(self.e.vendedor, datos)

    def lista(self, usuario, consulta=""):
        self.client.force_login(usuario)
        return self.client.get(reverse("comercial:entregas") + consulta)

    def test_recorrido_de_la_planificacion_al_vencimiento_en_camara(self):
        """Del registro de la venta a la entrega cancelada por un vencimiento, por rol y por estado."""
        # 1. La venta sale toda de cámara: la entrega se planifica sola, con el transportista, y el Vendedor la ve en «Comercial › Entregas».
        partida = partida_cosechada(self.lote, 50)
        venta = self.registrar()
        entrega = Entrega.objects.get()
        self.assertEqual((entrega.contrato_entrega_id, entrega.transportista_id, entrega.estado_orden), (venta.pk, self.camioneta.pk, "a_realizar"))
        self.assertIn(f"Nueva entrega para el {entrega.fecha_programada_orden:%d/%m}", Notificacion.objects.filter(destinatario=self.camioneta).values_list("titulo", flat=True))
        for usuario in (self.e.vendedor, self.gerente):
            pagina = texto(self.lista(usuario))
            self.assertIn(entrega.codigo, pagina)
            self.assertIn(self.camioneta.get_full_name(), pagina)
            self.assertIn("4,50 kg", pagina)  # 30 plantas × 150 g
        for usuario in (self.e.agronomo, self.e.capataz):
            self.assertEqual(self.lista(usuario).status_code, 403)

        # 2. La ficha del invernadero › «Logística» ya cuenta la entrega del transportista y la lista filtrada por él (el enlace de «Ver sus entregas») la muestra.
        self.client.force_login(self.gerente)
        ficha = self.client.get(reverse("maestros:invernadero", args=[self.e.invernadero.pk]))
        self.assertIn("Logística", texto(ficha))
        self.assertIn(entrega.codigo, texto(self.lista(self.gerente, f"?transportista={self.camioneta.pk}")))

        # 3. Sin flota la entrega nace sin transportista: la campana del Gerente lo dice y su enlace lleva a esa fila.
        self.camioneta.invernadero_asignado.delete()
        segunda = self.registrar("10", dias=4)
        sin = Entrega.objects.get(contrato_entrega_id=segunda.pk)
        alerta = AlertaComercial.objects.get(entrega=sin).alerta
        self.assertEqual((sin.transportista_id, alerta.estado_alerta), (None, "activa"))
        self.assertIn("sin transportistas activos con vehículo activo", alerta.descripcion_alerta)
        self.client.force_login(self.gerente)
        self.assertIn("Entrega sin transportista", texto(self.client.get(reverse("alertas:lista"))))
        abrir = self.client.get(reverse("alertas:ir", args=[alerta.pk]))
        self.assertEqual(abrir.status_code, 302)
        self.assertIn(f"/comercial/entregas/{sin.pk}/asignar/", abrir["Location"])  # COM-05b, extensión 1b: la alerta lleva a la asignación
        fila = self.client.get(abrir["Location"])
        self.assertIn(sin.codigo, texto(fila))
        self.assertIn("Asignar transportista", texto(fila))

        # 4. Llega un transportista: el paso 50 (el comando del cron) se lo asigna, resuelve la alerta y avisa; una segunda corrida no hace nada.
        nuevo = transportista_con_vehiculo(self.e.invernadero, "800")
        Entrega.objects.filter(pk=sin.pk).update(fecha_creacion_orden=HOY - timedelta(days=1))
        salida = StringIO()
        call_command("proceso_diario", "--solo", "planificar_entregas", stdout=salida)
        sin.refresh_from_db()
        alerta.refresh_from_db()
        self.assertEqual((sin.transportista_id, alerta.estado_alerta), (nuevo.pk, "resuelta"))
        self.assertIn(f"{sin.codigo} ya tiene transportista", Notificacion.objects.filter(destinatario=self.e.vendedor).values_list("titulo", flat=True))
        avisos = Notificacion.objects.count()
        call_command("proceso_diario", "--solo", "planificar_entregas", stdout=StringIO())
        self.assertEqual(Notificacion.objects.count(), avisos)

        # 5. La baja de la cuenta del transportista deja su entrega sin transportista, con la alerta, y el paso 50 le busca otro.
        baja_usuario(self.gerente, nuevo.pk)
        sin.refresh_from_db()
        self.assertIsNone(sin.transportista_id)
        self.assertEqual(AlertaComercial.objects.filter(entrega=sin).latest("pk").alerta.estado_alerta, "activa")  # la de la baja es una alerta nueva: la primera se resolvió al asignar

        # 6. La partida vence en cámara: la primera entrega se queda sin producto y se cancela; el transportista y la lista lo reflejan.
        camara.vencer_partidas_en_camara(HOY + timedelta(days=31))
        entrega.refresh_from_db()
        self.assertEqual((entrega.estado_orden, entrega.motivo_cancelacion), ("cancelada", "Se venció en cámara el producto reservado."))
        self.assertNotIn(entrega.codigo, texto(self.lista(self.gerente)))
        self.assertIn(entrega.codigo, texto(self.lista(self.gerente, "?estado=cancelada")))
        self.assertTrue(partida.pk)
