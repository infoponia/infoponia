# Recorrido de COM-05a2 (docs/patrones/verificacion_a_mano.md, D-96): de punta a punta con el cliente de Django, por rol y por estado, lo que la «Verificación a mano» pide al estudiante.
# Una entrega nace de una venta lista (el paso 50 / el disparador la planifica): el Agrónomo recibe «Planificá el envasado», lo ve en su panel y en «Envasado», reserva envases (con el error de
# lo disponible, el resumen y la confirmación), lo modifica (resumen con antes y después, «No hay cambios para registrar.», quitar y volver a agregar) y la entrega se cancela y libera los
# envases; el Gerente y el Vendedor la ven en su panel, en la ficha de la compra-venta y del suministro (con «Entrega planificada» en el calendario) y en los vehículos. Nada de navegador:
# el CSRF, el encabezado `Origin` y el JavaScript van como paso de «navegador real» de la «Verificación a mano».

from datetime import timedelta
from html import unescape

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import Entrega
from comercial.servicios import entregas
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
)
from core.models import Notificacion
from core.tests.fabricas import crear_gerente
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import ReservaInsumo
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def texto(respuesta):
    """El HTML de la respuesta, con las entidades resueltas."""
    return unescape(respuesta.content.decode())


class RecorridoDeEnvasadoYEntregasTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 5000)
        self.gerente = crear_gerente()
        self.t = transportista_con_vehiculo(self.e.invernadero, "800")
        self.bandeja = envase(self.e.invernadero, 30)
        self.addCleanup(verificar_invariantes_de_entregas)

    def ir(self, usuario, url, metodo="get", datos=None):
        self.client.force_login(usuario)
        return getattr(self.client, metodo)(url, datos or {})

    def mensajes(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]

    def activas(self, entrega_):
        return {r.insumo_invernadero_id: r.cantidad_reservada for r in ReservaInsumo.objects.filter(orden_id=entrega_.pk, estado="activa")}

    def test_flujo_principal_la_entrega_se_envasa_se_modifica_y_se_ve_en_el_panel_las_fichas_y_los_vehiculos(self):
        """Verificación a mano, pasos 1 a 5: del aviso «Planificá el envasado» a la carga, el resumen, la modificación y las pantallas compartidas, por rol."""
        agronomo, vendedor = self.e.agronomo, self.e.vendedor
        venta = compra_venta(self.e, dias=3)
        det = detalle(venta, self.e.variedad, 100)
        reserva_lista(det, self.lote, 100)
        (resultado,) = entregas.planificar_venta(venta.pk, HOY)
        e1 = resultado.entrega
        url_lista = reverse("comercial:envasado")
        url_carga = reverse("comercial:envasado_entrega", args=[e1.pk])

        # 1. El Agrónomo tiene el aviso y el indicador «Entregas sin envasado» del panel lleva a «Envasado».
        self.assertTrue(Notificacion.objects.filter(destinatario=agronomo, titulo=f"Planificá el envasado de {e1.codigo}").exists())
        panel = texto(self.ir(agronomo, reverse("core:inicio")))
        self.assertIn("Entregas sin envasado", panel)
        self.assertIn(url_lista, panel)

        # 2. «Envasado»: «Sin planificar». 40 bandejas supera lo disponible; 20 pasan por el resumen y se confirman.
        pagina = texto(self.ir(agronomo, url_lista))
        self.assertIn("Sin planificar", pagina)
        self.assertIn(url_carga, pagina)
        self.assertEqual(self.ir(agronomo, url_carga).status_code, 200)
        base = {"huella": self._huella(e1), "busqueda": ""}
        agregada = texto(self.ir(agronomo, reverse("comercial:envasado_calcular", args=[e1.pk]), "post", {**base, "agregar": self.bandeja.pk, f"nueva_{self.bandeja.pk}": "40"}))
        self.assertIn("Supera lo disponible: quedan 30 unidades", agregada)
        revisada = self.ir(agronomo, reverse("comercial:envasado_revisar", args=[e1.pk]), "post", {**base, f"cantidad_{self.bandeja.pk}": "40"})
        self.assertNotIn("Confirmar envasado", texto(revisada))
        resumen = texto(self.ir(agronomo, reverse("comercial:envasado_revisar", args=[e1.pk]), "post", {**base, f"cantidad_{self.bandeja.pk}": "20"}))
        self.assertIn("Confirmar envasado", resumen)
        self.assertEqual(self.activas(e1), {})  # el resumen no escribe
        confirmada = self.ir(agronomo, url_carga, "post", {**base, f"cantidad_{self.bandeja.pk}": "20"})
        self.assertRedirects(confirmada, url_lista, fetch_redirect_response=False)
        self.assertEqual(self.mensajes(confirmada), [f"Envasado de {e1.codigo} planificado."])
        self.assertEqual(self.activas(e1), {self.bandeja.pk: 20})
        self.assertIn("Planificado", texto(self.ir(agronomo, url_lista)))

        # 3. Modificar: cambia a 25 (el resumen muestra antes y después); sin cambios avisa; quitar y volver a agregar deja una reserva cancelada y una activa.
        base = {"huella": self._huella(e1), "busqueda": ""}
        resumen = texto(self.ir(agronomo, reverse("comercial:envasado_revisar", args=[e1.pk]), "post", {**base, f"cantidad_{self.bandeja.pk}": "25"}))
        self.assertIn("20", resumen)
        self.assertIn("25", resumen)
        self.ir(agronomo, url_carga, "post", {**base, f"cantidad_{self.bandeja.pk}": "25"})
        self.assertEqual(self.activas(e1), {self.bandeja.pk: 25})
        base = {"huella": self._huella(e1), "busqueda": ""}
        sin_cambios = texto(self.ir(agronomo, reverse("comercial:envasado_revisar", args=[e1.pk]), "post", {**base, f"cantidad_{self.bandeja.pk}": "25"}))
        self.assertIn("No hay cambios para registrar.", sin_cambios)
        self.ir(agronomo, url_carga, "post", base)  # quitar todo
        self.assertEqual(self.activas(e1), {})
        base = {"huella": self._huella(e1), "busqueda": ""}
        self.ir(agronomo, url_carga, "post", {**base, f"cantidad_{self.bandeja.pk}": "10"})
        self.assertEqual(self.activas(e1), {self.bandeja.pk: 10})
        self.assertEqual(ReservaInsumo.objects.filter(orden_id=e1.pk).count(), 2)
        self.assertIn("Entregas sin envasado", texto(self.ir(agronomo, reverse("core:inicio"))))

        # 4. El panel del Gerente y del Vendedor, la ficha de la compra-venta y los vehículos.
        for usuario in (self.gerente, vendedor):
            panel = texto(self.ir(usuario, reverse("core:inicio")))
            for esperado in ("Entregas de hoy", "Sin transportista", "Próximas entregas", e1.codigo):
                self.assertIn(esperado, panel)
        ficha = texto(self.ir(vendedor, reverse("comercial:compra_venta", args=[venta.pk])))
        for esperado in (e1.codigo, str(self.e.invernadero), "A realizar", self.t.get_full_name()):
            self.assertIn(esperado, ficha)
        self.assertIn("Entregas a realizar", texto(self.ir(self.gerente, reverse("comercial:vehiculos"))))
        carga = texto(self.ir(self.gerente, reverse("comercial:vehiculo", args=[self.t.vehiculo.pk])))
        self.assertIn("Carga de los próximos días", carga)
        self.assertIn(f"{e1.fecha_programada_orden:%d/%m/%Y}", carga)

        # 5. Los otros roles no entran a «Envasado».
        for usuario in (self.gerente, vendedor, self.e.capataz, self.t):
            self.assertEqual(self.ir(usuario, url_lista).status_code, 403)

    def test_flujo_principal_el_suministro_muestra_entrega_planificada_y_sus_entregas(self):
        """Verificación a mano, paso 3: en la ficha del suministro, «Entrega planificada» en el calendario y la sección de entregas con «No confirmada»."""
        s = suministro(self.e)
        d = detalle_suministro(s, self.e.variedad, cantidad=20, primera_en_dias=3)
        reserva_lista(None, self.lote, 20, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d)
        (resultado,) = entregas.planificar_periodo(d.pk, d.fecha_primer_entrega, HOY)
        ficha = texto(self.ir(self.gerente, reverse("comercial:suministro", args=[s.pk])))
        for esperado in ("Entrega planificada", resultado.entrega.codigo, "No confirmada"):
            self.assertIn(esperado, ficha)

    def test_estado_la_entrega_cancelada_libera_los_envases_y_ya_no_se_envasa(self):
        """Verificación a mano, paso 6: al cancelar la entrega, sus reservas de envases pasan a «cancelada», lo disponible vuelve a 30 y «Envasado» ya no la abre (10a)."""
        venta = compra_venta(self.e, dias=3)
        det = detalle(venta, self.e.variedad, 100)
        reserva_lista(det, self.lote, 100)
        (resultado,) = entregas.planificar_venta(venta.pk, HOY)
        e1 = resultado.entrega
        agronomo = self.e.agronomo
        self.ir(agronomo, reverse("comercial:envasado_entrega", args=[e1.pk]), "post", {"huella": self._huella(e1), f"cantidad_{self.bandeja.pk}": "20"})
        self.assertEqual(self.activas(e1), {self.bandeja.pk: 20})
        self.assertEqual(stock.disponible_para_planificar([self.bandeja.pk], HOY)[self.bandeja.pk], 10)
        entregas.cancelar_entrega_incluida(self.gerente, Entrega.objects.get(pk=e1.pk), "Se perdió en cámara el producto reservado")
        self.assertEqual(self.activas(e1), {})
        self.assertEqual(stock.disponible_para_planificar([self.bandeja.pk], HOY)[self.bandeja.pk], 30)
        respuesta = self.ir(agronomo, reverse("comercial:envasado_entrega", args=[e1.pk]))
        self.assertRedirects(respuesta, reverse("comercial:envasado"), fetch_redirect_response=False)
        self.assertTrue(any("ya no está a realizar" in m for m in self.mensajes(respuesta)))

    def _huella(self, entrega_):
        from comercial.servicios import envasado

        return envasado.huella_de(entrega_.pk)
