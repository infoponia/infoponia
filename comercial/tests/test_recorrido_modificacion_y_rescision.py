# Recorrido de COM-03b (COM-MOD-SUM, COM-RSC-SUM, COM-ANL-RSC y PROD-PRR-SUM; docs/patrones/verificacion_a_mano.md, D-96): una prueba larga con el cliente de Django que hace los pasos de
# punta a punta como una persona, por rol y por estado: el paso diario 40 pre-reserva dos contratos; el Vendedor modifica uno (con el resumen, sin JavaScript) y mira su historial; el
# Agrónomo no entra; el Gerente rescinde el otro, el Vendedor ya no puede tocarlo, el Gerente deja la rescisión sin efecto, la vuelve a registrar y el paso diario 35 lo cierra.
# No reemplaza la «Verificación a mano» del estudiante: no ve el CSRF, el encabezado `Origin` ni el JavaScript (por eso la tarea trae el paso de «navegador real»).

import re
from datetime import timedelta
from html import unescape
from io import StringIO

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import DetalleSuministro, ReservaStock, Suministro
from comercial.tests.fabricas import (
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
HTMX = {"HTTP_HX_REQUEST": "true"}


def iso(dias):
    return str(HOY + timedelta(days=dias))


def avisos(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


def ocultos(respuesta):
    """Los campos ocultos de una respuesta (lo único que viaja de un resumen a su confirmación sin JavaScript)."""
    return {n: unescape(v) for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', respuesta.content.decode())}


class RecorridoDeModificacionYRescisionTests(ConDatosDeInventario, TestCase):
    """Dos suministros de 30 plantas cada 7 días desde dentro de 3 días (períodos a los 3, 10 y 17), uno que se modifica y otro que se rescinde."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.gerente = crear_gerente()
        self.a = suministro(self.e)
        self.da = detalle_suministro(self.a, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=3)
        self.b = suministro(self.e)
        self.db = detalle_suministro(self.b, self.e.variedad, direccion=direccion_de_cliente(self.e.cliente).direccion, cantidad=30, periodo=7, primera_en_dias=3)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_suministros)

    def ficha(self, s):
        return self.client.get(reverse("comercial:suministro", args=[s.pk]))

    def test_recorrido_del_paso_diario_la_modificacion_y_la_rescision(self):
        """Pre-reserva diaria → modificación del Vendedor → historial → rescisión del Gerente → dejar sin efecto → rescindir otra vez → cierre del paso 35."""
        # 1. El paso diario 40 (a mano, D-56) pre-reserva los períodos de la ventana de los dos contratos.
        salida = StringIO()
        call_command("proceso_diario", "--solo", "pre_reservar_suministros", stdout=salida)
        self.assertIn("Pre-reservar suministros: procesados 4 · creados 4 · resueltos 0", salida.getvalue())
        for detalle in (self.da, self.db):
            self.assertEqual(sorted(r.fecha_entrega_reserva for r in ReservaStock.objects.filter(detalle_suministro=detalle)), [HOY + timedelta(days=3), HOY + timedelta(days=10)])

        # 2. El Vendedor modifica A: botones por rol y estado, formulario, resumen (la huella y la propuesta viajan en campos ocultos) y confirmación.
        self.client.force_login(self.e.vendedor)
        ficha = self.ficha(self.a)
        self.assertContains(ficha, "Modificar suministro")
        self.assertContains(ficha, "Reservado")
        for texto in ("Rescindir suministro", "Dejar sin efecto la rescisión", "Ver historial de cambios"):
            self.assertNotContains(ficha, texto)
        url = reverse("comercial:suministro_modificar", args=[self.a.pk])
        pantalla = self.client.get(url)
        self.assertContains(pantalla, f'name="modificar-{self.da.pk}-cantidad" value="30"')
        cambios = {**ocultos(pantalla), f"modificar-{self.da.pk}-accion": "modificar", f"modificar-{self.da.pk}-cantidad": "40", f"modificar-{self.da.pk}-rige_desde": iso(17)}
        resumen = self.client.post(url + "revisar/", cambios)
        self.assertContains(resumen, "cantidad por período: de 30 a 40")
        respuesta = self.client.post(url, {**ocultos(resumen), "confirmar": "1"})
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.a.pk]), fetch_redirect_response=False)
        self.assertEqual(DetalleSuministro.objects.get(pk=self.da.pk).estado_detalle_suministro, "finalizado")
        (sucesor,) = DetalleSuministro.objects.filter(reemplaza_a=self.da)
        self.assertEqual((sucesor.cantidad_por_periodo, sucesor.fecha_primer_entrega), (40, HOY + timedelta(days=17)))
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=self.da).count(), 2)  # lo ya reservado no cambió

        # 3. La ficha muestra el cambio y el historial; el Agrónomo no entra a ninguna pantalla nueva.
        ficha = self.ficha(self.a)
        self.assertContains(ficha, f"Con cambios desde el {(HOY + timedelta(days=17)):%d/%m/%Y}")
        self.assertContains(self.client.get(reverse("comercial:suministro_historial", args=[self.a.pk]), **HTMX), "fin del contrato")
        self.client.force_login(self.e.agronomo)
        for nombre in ("suministro_modificar", "suministro_rescindir", "suministro_dejar_sin_efecto", "suministro_historial"):
            self.assertEqual(self.client.get(reverse(f"comercial:{nombre}", args=[self.a.pk])).status_code, 403, nombre)

        # 4. El Gerente rescinde B: la ventana presenta lo que pasará; sin la casilla no se registra; con ella, sí.
        self.client.force_login(self.gerente)
        ficha = self.ficha(self.b)
        for texto in ("Modificar suministro", "Rescindir suministro"):
            self.assertContains(ficha, texto)
        url_rescindir = reverse("comercial:suministro_rescindir", args=[self.b.pk])
        ventana = self.client.get(url_rescindir, **HTMX)
        self.assertContains(ventana, f"Rescindir {self.b.codigo}")
        pedido = {"motivo": "a_pedido_del_cliente", "descripcion": "", "fecha_acuerdo": iso(-1), "huella": ocultos(ventana)["huella"],
                  "conservado": re.findall(r'name="conservado" value="([^"]+)"', ventana.content.decode())}
        self.assertContains(self.client.post(url_rescindir, pedido), "Confirmá que la rescisión se acordó con el cliente")
        self.assertIsNone(Suministro.objects.get(pk=self.b.pk).motivo_rescision)
        respuesta = self.client.post(url_rescindir, {**pedido, "acuerdo": "1"})
        self.assertRedirects(respuesta, reverse("comercial:suministro", args=[self.b.pk]), fetch_redirect_response=False)
        self.assertTrue(any("Se entrega hasta el" in a for a in avisos(respuesta)))
        ficha = self.ficha(self.b)
        self.assertContains(ficha, "Rescisión acordada el")
        self.assertContains(ficha, "Dejar sin efecto la rescisión")
        self.assertNotContains(ficha, "Modificar suministro")

        # 5. El Vendedor ya no puede tocarlo: sin botones y la pantalla de modificar lo devuelve a la ficha con el motivo.
        self.client.force_login(self.e.vendedor)
        ficha = self.ficha(self.b)
        for texto in ("Modificar suministro", "Rescindir suministro", "Dejar sin efecto la rescisión"):
            self.assertNotContains(ficha, texto)
        volver = self.client.get(reverse("comercial:suministro_modificar", args=[self.b.pk]))
        self.assertIn("Tiene una rescisión acordada: dejala sin efecto para modificarlo.", avisos(volver))

        # 6. El Gerente la deja sin efecto (motivo obligatorio) y el contrato vuelve a poder modificarse.
        self.client.force_login(self.gerente)
        url_anular = reverse("comercial:suministro_dejar_sin_efecto", args=[self.b.pk])
        ventana = self.client.get(url_anular, **HTMX)
        self.assertContains(self.client.post(url_anular, {"motivo": "", "huella": ocultos(ventana)["huella"]}), "Contá por qué se deja sin efecto la rescisión.")
        self.client.post(url_anular, {"motivo": "El cliente decidió seguir", "huella": ocultos(ventana)["huella"]})
        self.assertIsNone(Suministro.objects.get(pk=self.b.pk).motivo_rescision)
        self.assertContains(self.ficha(self.b), "Modificar suministro")

        # 7. La rescinde otra vez y el paso diario 35, el día siguiente a la última entrega, la cierra.
        ventana = self.client.get(url_rescindir, **HTMX)
        pedido = {**pedido, "huella": ocultos(ventana)["huella"], "acuerdo": "1"}
        self.client.post(url_rescindir, pedido)
        call_command("proceso_diario", "--fecha", iso(11), "--solo", "cerrar_rescisiones", stdout=StringIO())
        self.assertEqual(Suministro.objects.get(pk=self.b.pk).estado_suministro, "rescindido")
        ficha = self.ficha(self.b)
        self.assertContains(ficha, "Rescindido por mutuo acuerdo")
        for texto in ("Modificar suministro", "Rescindir suministro", "Dejar sin efecto la rescisión"):
            self.assertNotContains(ficha, texto)
        lista = self.client.get(reverse("comercial:contratos"), {"tipo": "suministro", "estado": "rescindido"})
        self.assertContains(lista, self.b.codigo)
        self.assertNotContains(lista, self.a.codigo)

        # 8. La auditoría de todo el recorrido: un registro por hecho.
        cuenta = {accion: RegistroAuditoria.objects.filter(accion=accion).count() for accion in
                  ("modificacion_suministro", "rescision_suministro", "anulacion_rescision", "cierre_rescision")}
        self.assertEqual(cuenta, {"modificacion_suministro": 1, "rescision_suministro": 2, "anulacion_rescision": 1, "cierre_rescision": 1})
        self.assertGreaterEqual(RegistroAuditoria.objects.filter(accion="pre_reserva_periodo").count(), 4)
