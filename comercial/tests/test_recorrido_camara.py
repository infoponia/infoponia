# Recorrido de COM-04b de punta a punta con el cliente de Django (D-96; docs/patrones/verificacion_a_mano.md): lo que haría una persona, por rol y por estado, con las pantallas y
# los servicios reales: el Capataz concreta una cosecha sin contrato (la partida entra a la cámara), el Agrónomo la ve en la pestaña «Cámara», el paso diario 25 la asigna a quien la
# espera y avisa, el Capataz registra una merma en cámara que supera el stock libre (el resumen dice qué contrato pierde producto), el Agrónomo recibe el aviso «partida por vencer» con
# `proceso_diario --fecha` y, pasada la fecha límite, la partida vence con su merma; correr la misma fecha otra vez no duplica nada. No reemplaza la «Verificación a mano» del estudiante:
# lo que solo un navegador ve (CSRF real, `Origin`, JavaScript) va como paso de «navegador real» en el «Cierre» de la tarea.

from datetime import timedelta
from html import unescape
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import DetalleReserva, ReservaStock
from comercial.tests.fabricas import compra_venta, cosecha_manual, detalle, escenario_comercial, partida, verificar_invariantes_de_reservas
from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta
from produccion.models import Merma, StockCosechado
from produccion.tests.fabricas import lote_maduro
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

HOY = timezone.localdate()


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class RecorridoDeCamaraTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.sector = self.e.sectores["maduracion"]
        self.addCleanup(verificar_invariantes_de_reservas)

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def proceso(self, *argumentos):
        """`python manage.py proceso_diario ...`: devuelve lo que imprime."""
        salida = StringIO()
        call_command("proceso_diario", *argumentos, stdout=salida)
        return salida.getvalue()

    def test_recorrido_de_la_camara_por_rol_y_por_estado(self):
        # 1. El Capataz concreta una cosecha sin contrato de 40 plantas: la partida entra a la cámara (el `on_commit` de PROD-ASG-CAM se programa; nadie la espera todavía).
        sin_contrato = cosecha_manual(self.e, [(self.lote, 40)], dias=0)
        self.entrar(self.e.capataz)
        concrecion = {"fecha_efectiva": str(HOY)}
        resumen = self.client.post(reverse("comercial:cosecha_concretar_revisar", args=[sin_contrato.pk]), concrecion)
        with self.captureOnCommitCallbacks(execute=False) as programados:
            self.client.post(reverse("comercial:cosecha_concretar", args=[sin_contrato.pk]), {**concrecion, "firma": resumen.context["firma"]})
        self.assertEqual(len(programados), 1)
        p = StockCosechado.objects.get(motivo_cosechado="cosecha_del_agronomo")
        self.assertEqual((p.cantidad_disponible_cosechado, p.fecha_limite), (40, HOY + timedelta(days=self.e.variedad.duracion_post_cosecha)))

        # 2. El Agrónomo ve la partida en la pestaña «Cámara» de su invernadero: 40 disponibles, 0 reservadas, 40 libres.
        self.entrar(self.e.agronomo)
        ficha = reverse("maestros:invernadero", args=[self.e.invernadero.pk]) + "?pestana=camara"
        pagina = texto(self.client.get(ficha))
        self.assertIn(p.codigo, pagina)
        self.assertIn("Cosecha planificada por el Agrónomo", pagina)

        # 3. Una venta con envío de 25 plantas esperaba stock (lo que dejó COM-04a sin asignar): `proceso_diario --solo reasignar_camara` (paso 25) la asigna a la partida y avisa.
        espera = detalle(compra_venta(self.e, dias=2), self.e.variedad, 25)
        self.assertIn("Reasignar cámara", self.proceso("--listar"))
        self.proceso("--solo", "reasignar_camara")
        self.assertEqual(DetalleReserva.objects.get(reserva__detalle_venta=espera).partida_id, p.pk)
        self.assertEqual(ReservaStock.objects.get(detalle_venta=espera).estado_reserva, "lista_para_entrega")
        self.assertTrue(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk, titulo=f"Stock de cámara para {espera.compra_venta.codigo}").exists())
        self.assertTrue(Notificacion.objects.filter(destinatario_id=self.e.agronomo.pk, titulo=f"Partida {p.codigo} asignada").exists())
        self.assertTrue(RegistroAuditoria.objects.filter(accion="asignacion_camara", usuario__isnull=True).exists())
        pagina = texto(self.client.get(ficha))
        self.assertRegex(pagina, rf"(?s){p.codigo}.*?<td class=\"right\">40</td>\s*<td class=\"right\">25</td>\s*<td class=\"right\"><b>15</b></td>")
        self.proceso("--solo", "reasignar_camara")  # idempotente: nada nuevo
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=espera).count(), 1)

        # 4. El Capataz, desde «Registrar merma», elige «Pérdida en cámara»: pierde 30 de la partida (más que los 15 libres). El resumen dice qué contrato pierde producto.
        self.entrar(self.e.capataz)
        merma = texto(self.client.get(reverse("produccion:registrar_merma"), {"invernadero": str(self.e.invernadero.pk)}))
        self.assertIn("Pérdida en cámara", merma)
        datos = {"invernadero": str(self.e.invernadero.pk), "partida": str(p.pk), "cantidad": "30", "causa": "dano_en_camara", "descripcion": "Se cayó la bandeja"}
        resumen = self.client.post(reverse("comercial:merma_camara"), {**datos, "accion": "calcular"})
        self.assertIn(espera.compra_venta.codigo, texto(resumen))
        self.assertIn("estos contratos pierden producto", texto(resumen))
        self.assertEqual(Merma.objects.count(), 0)
        respuesta = self.client.post(reverse("comercial:merma_camara"), {**datos, "accion": "confirmar", "firma": resumen.context["firma"], "visto_disponible": "40"})
        self.assertRedirects(respuesta, reverse("produccion:bandeja"), fetch_redirect_response=False)
        p.refresh_from_db()
        self.assertEqual(p.cantidad_disponible_cosechado, 10)
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida=p, reserva__estado_reserva__in=("activa", "lista_para_entrega"))), 10)
        # Lo recortado (15) se volvió a cubrir con el lote en pie (cosecha nueva) y el Agrónomo recibió la alerta de merma con producto reservado.
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(lote=self.lote, reserva__detalle_venta=espera)), 15)
        self.assertTrue(Alerta.objects.filter(tipo_alerta="comercial_merma_camara_reservada", agronomo_id=self.e.agronomo.pk).exists())

        # 5. Una segunda partida de 12 plantas vence dentro de 5 días: dos días antes, `proceso_diario --fecha` avisa «Partida por vencer» al Agrónomo y al Vendedor.
        segunda = partida(self.lote, 12, fecha_limite=HOY + timedelta(days=5))
        self.proceso("--fecha", str(HOY + timedelta(days=3)))
        aviso = Alerta.objects.get(tipo_alerta="comercial_partida_por_vencer", clave_estado=f"partida:{segunda.pk}")
        self.assertEqual((aviso.estado_alerta, aviso.agronomo_id), ("activa", self.e.agronomo.pk))
        self.assertTrue(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk, titulo="Partida por vencer").exists())
        self.entrar(self.e.agronomo)
        self.assertIn(segunda.codigo, texto(self.client.get(reverse("alertas:lista"))))
        avisos = Alerta.objects.filter(tipo_alerta="comercial_partida_por_vencer").count()
        self.proceso("--fecha", str(HOY + timedelta(days=3)))  # la misma fecha otra vez: nada nuevo
        self.assertEqual(Alerta.objects.filter(tipo_alerta="comercial_partida_por_vencer").count(), avisos)

        # 6. Pasada la fecha límite, la partida queda «Vencida» con su merma por vencimiento y el aviso se resuelve; correr la misma fecha otra vez no duplica nada.
        self.proceso("--fecha", str(HOY + timedelta(days=6)))
        segunda.refresh_from_db()
        aviso.refresh_from_db()
        self.assertEqual((segunda.estado_stock_cosechado, segunda.cantidad_disponible_cosechado, aviso.estado_alerta), ("vencido", 0, "resuelta"))
        merma_vencimiento = Merma.objects.get(causa="vencimiento_en_camara", lote=self.lote)
        self.assertEqual(merma_vencimiento.cant_merma, 12)
        mermas = Merma.objects.count()
        self.proceso("--fecha", str(HOY + timedelta(days=6)))
        self.assertEqual(Merma.objects.count(), mermas)
        self.assertIn("Vencida", texto(self.client.get(reverse("maestros:invernadero", args=[self.e.invernadero.pk]) + "?pestana=camara")))
