# Recorrido de COM-04c de punta a punta con el cliente de Django (D-96; docs/patrones/verificacion_a_mano.md): lo que haría una persona, por rol y por estado, con las pantallas y los
# servicios reales. Una partida de cámara que vence deja sin cubrir a tres ventas (paso diario 20): la del cliente con correo recibe el enlace por correo, la del cliente sin correo avisa al
# Vendedor y la tercera queda esperando. El cliente abre el enlace, no ve su token en la URL, elige «No recibir», revisa el resumen y confirma; reabrir el enlace dice que no se puede usar. El
# Vendedor decide por el cliente sin correo desde la ficha. El paso diario 27 avisa el enlace que venció sin respuesta, una sola vez, y el Vendedor decide también esa venta. No reemplaza la
# «Verificación a mano» del estudiante: lo que solo un navegador ve (CSRF real, `Origin`, JavaScript) va como paso de «navegador real» en el «Cierre» de la tarea.

import re
from datetime import timedelta
from html import unescape
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente
from comercial.tests.fabricas import cliente, compra_venta, detalle, escenario_comercial, partida, reserva, verificar_invariantes_de_reservas
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Lote, StockCosechado
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
PORTAL = "/cliente/enlace/"


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


@override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
class RecorridoDeFaltantesTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.addCleanup(verificar_invariantes_de_reservas)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def proceso(self, *argumentos):
        """`python manage.py proceso_diario ...` con los `on_commit` ejecutados (la prueba entera vive dentro de una transacción): devuelve lo que imprime."""
        salida = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", *argumentos, stdout=salida)
        return salida.getvalue()

    def venta_que_espera(self, partida_, cliente_=None):
        """Una venta abierta de 20 plantas reservadas de `partida_`."""
        d = detalle(compra_venta(self.e, cliente_=cliente_), self.e.variedad, 20, precio="10.00")
        reserva(d, [(partida_, 20)])
        return d

    def test_recorrido_del_faltante_y_el_enlace_del_cliente(self):
        # 1. Tres ventas reservan de una partida que vence ayer (A y C: clientes con correo; B: cliente sin correo) y el lote no tiene más stock para volver a cubrirlas.
        vencida = partida(self.lote, 60, fecha_limite=HOY - timedelta(days=1))
        sin_correo = cliente(email="", telefono="1144445555", razon_social="Verdulería Sin Correo S.A.")
        a = self.venta_que_espera(vencida)
        b = self.venta_que_espera(vencida, sin_correo)
        c = self.venta_que_espera(vencida, cliente(email="otro@ejemplo.com", razon_social="Otra Verdulería S.R.L."))
        Lote.objects.filter(pk=self.lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)

        # 2. El paso diario 20 vence la partida: las tres ventas pasan a «pendiente de decisión»; a A y a C les sale el correo con el enlace, a B no (el Vendedor recibe el aviso).
        self.assertIn("avisar_enlaces_vencidos", self.proceso("--listar"))
        with mock.patch("core.correo.enviar_correo", return_value=True) as envio:
            self.proceso("--solo", "vencer_partidas_en_camara")
        for d in (a, b, c):
            d.refresh_from_db()
            self.assertEqual((d.estado_detalle_venta, d.compra_venta.estado_venta), ("pendiente_decision", "pendiente_decision"))
        self.assertEqual(StockCosechado.objects.get(pk=vencida.pk).estado_stock_cosechado, "vencido")
        urls = {call.args[3]["codigo"]: call.args[3]["url"] for call in envio.call_args_list if call.args[2] == "comercial/correos/enlace_faltante.txt"}
        self.assertEqual(set(urls), {a.compra_venta.codigo, c.compra_venta.codigo})
        self.assertFalse(EnlaceCliente.objects.filter(compra_venta=b.compra_venta).exists())
        self.assertTrue(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo=f"{b.compra_venta.codigo}: el cliente no tiene correo").exists())
        self.assertEqual(set(EnlaceCliente.objects.values_list("estado_envio", flat=True)), {"enviado"})

        # 3. El Vendedor ve en la ficha de A lo pendiente y hasta cuándo puede decidir el cliente, sin botón (el cliente puede decidir); en la de B, el botón.
        self.entrar(self.e.vendedor)
        ficha_a = texto(self.client.get(reverse("comercial:compra_venta", args=[a.compra_venta.pk])))
        self.assertIn("Pendiente de decisión del cliente", ficha_a)
        self.assertIn(f"{HOY + timedelta(days=2):%d/%m/%Y}", ficha_a)
        self.assertNotIn("Registrar decisión de faltante", ficha_a)
        self.assertIn("Registrar decisión de faltante", texto(self.client.get(reverse("comercial:compra_venta", args=[b.compra_venta.pk]))))

        # 4. El cliente de A abre el enlace del correo desde un navegador sin sesión: la URL cambia y no muestra el token; la página no tiene menú.
        cliente_web = Client()
        token = re.search(r"/cliente/([^/]+)/$", urls[a.compra_venta.codigo]).group(1)
        pagina = cliente_web.get(f"/cliente/{token}/", follow=True)
        self.assertEqual(pagina.redirect_chain, [(PORTAL, 302)])
        self.assertNotIn(token, pagina.request["PATH_INFO"] + texto(pagina))
        self.assertNotIn("Cerrar sesión", texto(pagina))
        self.assertIn(f"Faltante en su compra {a.compra_venta.codigo}", texto(pagina))

        # 5. Ya no hay producto disponible (el recorte dejó la reserva en 0): solo se ofrece «No recibir». Sin elegir, el error sale junto al producto; después elige, revisa y confirma.
        self.assertIn("solo se puede no recibirlo", texto(pagina))
        sin_elegir = cliente_web.post(PORTAL, {"accion": "revisar", f"disponible_{a.pk}": "0"})
        self.assertIn(f"Indicá qué hacés con {self.e.variedad}", texto(sin_elegir))
        elegido = {f"decision_{a.pk}": "rechazar", f"disponible_{a.pk}": "0"}
        resumen = texto(cliente_web.post(PORTAL, {"accion": "revisar", **elegido}))
        self.assertIn("La compra quedará cancelada", resumen)
        self.assertIn("La decisión no podrá modificarse", resumen)
        with mock.patch("core.correo.enviar_correo", return_value=True) as acuse:
            with self.captureOnCommitCallbacks(execute=True):
                hecha = cliente_web.post(PORTAL, {"accion": "confirmar", **elegido})
        self.assertEqual(hecha["Location"], PORTAL + "listo/")
        self.assertIn("Gracias. Recibimos su decisión.", texto(cliente_web.get(PORTAL + "listo/")))
        self.assertEqual(acuse.call_args.args[2], "comercial/correos/acuse_faltante.txt")
        a.compra_venta.refresh_from_db()
        a.refresh_from_db()
        self.assertEqual((a.compra_venta.estado_venta, a.estado_detalle_venta), ("cancelada", "rechazado"))

        # 6. Volver a abrir el enlace: «Este enlace no se puede usar», con el contacto del Vendedor y sin datos de la venta. La auditoría dice «Cliente (mediante enlace)».
        reabierto = texto(Client().get(f"/cliente/{token}/"))
        self.assertIn("Este enlace no se puede usar", reabierto)
        self.assertIn(self.e.vendedor.email, reabierto)
        self.assertNotIn(a.compra_venta.codigo, reabierto)
        registro = RegistroAuditoria.objects.get(accion="decision_faltante")
        self.assertEqual((registro.usuario, registro.rol), (None, "cliente_enlace"))
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["rol"][registro.rol], "Cliente (mediante enlace)")

        # 7. El Vendedor ve «Faltantes para decidir (1)» (la venta B), la abre desde la lista y decide por el cliente sin correo: resumen, confirmar y aviso breve.
        self.assertIn("Faltantes para decidir (1)", texto(self.client.get(reverse("comercial:contratos"))))
        lista = texto(self.client.get(reverse("comercial:faltantes")))
        self.assertIn(b.compra_venta.codigo, lista)
        self.assertIn("1144445555", lista)
        self.assertNotIn(c.compra_venta.codigo, lista)  # C tiene enlace vigente: la decide el cliente
        url = reverse("comercial:faltante_decidir", args=[b.compra_venta.pk])
        datos_b = {f"decision_{b.pk}": "rechazar", f"disponible_{b.pk}": "0"}
        self.assertIn("La compra quedará cancelada", texto(self.client.post(url, {"accion": "revisar", **datos_b})))
        hecha = self.client.post(url, {"accion": "confirmar", **datos_b}, follow=True)
        self.assertIn(f"Registraste la decisión del cliente sobre el faltante de {b.compra_venta.codigo}.", texto(hecha))
        self.assertEqual(CompraVenta.objects.get(pk=b.compra_venta.pk).estado_venta, "cancelada")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="decision_faltante", usuario=self.e.vendedor).count(), 1)

        # 8. Roles sin permiso: el Gerente ve la ficha de C sin el botón y recibe 403 por la dirección escrita a mano; el Agrónomo y el Capataz, 403 en la lista.
        self.entrar(crear_gerente())
        self.assertNotIn("Registrar decisión de faltante", texto(self.client.get(reverse("comercial:compra_venta", args=[c.compra_venta.pk]))))
        self.assertEqual(self.client.get(reverse("comercial:faltante_decidir", args=[c.compra_venta.pk])).status_code, 403)
        for cuenta in (self.e.agronomo, self.e.capataz):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(reverse("comercial:faltantes")).status_code, 403)

        # 9. Paso diario 27: C no respondió. Con la fecha del día siguiente al vencimiento, el Vendedor recibe UN aviso; correrlo otra vez no lo repite.
        vence = EnlaceCliente.objects.get(compra_venta=c.compra_venta, estado="vigente").fecha_vencimiento
        salida = self.proceso("--solo", "avisar_enlaces_vencidos", "--fecha", str(vence + timedelta(days=1)))
        self.assertIn("Avisar enlaces vencidos: procesados 1 · creados 1", salida)
        titulo = f"Venció el plazo del cliente de {c.compra_venta.codigo}"
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo=titulo).count(), 1)
        self.proceso("--solo", "avisar_enlaces_vencidos", "--fecha", str(vence + timedelta(days=1)))
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.vendedor, titulo=titulo).count(), 1)
        self.assertEqual(EnlaceCliente.objects.get(compra_venta=c.compra_venta).estado, "vencido")
        self.assertEqual(DetalleVenta.objects.get(pk=c.pk).estado_detalle_venta, "pendiente_decision")  # sin decisión tácita

        # 10. Con el enlace vencido, el Vendedor ya puede decidir C: aparece en la lista y la decide.
        self.entrar(self.e.vendedor)
        self.assertIn(c.compra_venta.codigo, texto(self.client.get(reverse("comercial:faltantes"))))
        url = reverse("comercial:faltante_decidir", args=[c.compra_venta.pk])
        datos_c = {f"decision_{c.pk}": "rechazar", f"disponible_{c.pk}": "0"}
        self.client.post(url, {"accion": "confirmar", **datos_c})
        self.assertEqual(CompraVenta.objects.get(pk=c.compra_venta.pk).estado_venta, "cancelada")
        self.assertIn("No hay ventas de tus contratos", texto(self.client.get(reverse("comercial:faltantes"))))
