# Recorrido de punta a punta de CMP-02b (cancelar un pedido, reenviar una invitación y lo que cancela solo): los pasos de la «Verificación a mano» de la tarea, hechos por una prueba con el cliente
# de Django, en el orden en que los haría una persona (docs/patrones/verificacion_a_mano.md, D-96). Cada paso nombra el caso de uso y la regla que verifica. Es una sola prueba larga a propósito:
# lo que se verifica es que el flujo completo encadena bien (la Agrónoma reenvía una invitación y el proveedor del enlace viejo ya no puede entrar; cancela un pedido con una cotización y todos los
# enlaces dejan de servir; el Gerente cambia a la Agrónoma de un invernadero y se cancelan sus pedidos; da de baja su cuenta y se cancelan los demás; un pedido en curso impide deshabilitar el
# insumo y dar de baja el invernadero; y la baja de un proveedor anula sus enlaces). Las reglas sueltas las prueban ``test_cmp_cnl_ped.py``, ``test_cmp_cns_ped.py``,
# ``test_registrantes_de_pedidos.py``, ``test_cmp_baj_prv.py`` y ``test_pedidos_vistas.py``. Los correos salen en ``on_commit``: se lo reemplaza por una llamada inmediata, como en producción.

import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from compras.models import Cotizacion, EnlaceProveedor, Pedido
from compras.tests.fabricas import proveedor
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo
from maestros.models import Departamento, Provincia
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, localidad

HX = {"HTTP_HX_REQUEST": "true"}
PORTAL = "/proveedor/enlace/"


def en(dias):
    return timezone.localdate() + timedelta(days=dias)


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeCancelarYReenviarTests(ConDatosDeInventario, TestCase):
    """Fuente: docs/casos_de_uso/compras/pedidos.md (CMP-CNL-PED y la regla 7 de CMP-CNS-PED), proveedores.md (CMP-BAJ-PRV regla 3), D-87 punto 5, D-88 y D-36."""

    def setUp(self):
        envio_inmediato = mock.patch.object(transaction, "on_commit", lambda funcion, **kwargs: funcion())
        envio_inmediato.start()
        self.addCleanup(envio_inmediato.stop)
        self.ana = crear_agronomo(email="ana@infoponia.com")
        self.nuevo = crear_agronomo(email="nuevo@infoponia.com")
        self.otra = crear_agronomo(email="otra@infoponia.com")
        self.gerente = crear_gerente()
        self.capataz = crear_capataz()
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.norte2 = crear_invernadero("Invernadero Norte 2", agronomo=self.ana)
        self.este = crear_invernadero("Invernadero Este", agronomo=self.otra)
        self.lechuga = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=20, precio="12.50")
        self.nutriente = existencia(insumo("Nutriente", unidad="kg"), self.norte2, minimo=5, precio="100.00")
        self.tomate = existencia(insumo("Tomate", unidad="kg"), self.este, minimo=5, precio="30.00")
        self.pepino = existencia(insumo("Pepino", unidad="kg"), self.este, minimo=5, precio="25.00")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.viveros = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.nuevo_pedido = reverse("compras:pedido_nuevo")

    # ---- ayudas ----

    def hacer_pedido(self, agronomo, lineas, proveedores=None):
        """Un pedido de ``agronomo`` por la pantalla «Nuevo pedido» (``lineas = [(existencia, cantidad)]``); devuelve el ``Pedido`` y los enlaces ``{correo: ruta}`` de sus correos."""
        self.client.force_login(agronomo)
        antes = len(mail.outbox)
        proveedores = proveedores or [self.sur, self.viveros]
        datos = {
            "detalle_iin": [e.pk for e, _ in lineas],
            "detalle_cantidad": [c for _, c in lineas],
            "proveedor": [p.pk for p in proveedores],
            "fecha_limite": en(3).isoformat(),
            "filtro": "todos",
            "accion": "confirmar",
        }
        respuesta = self.client.post(self.nuevo_pedido, datos, follow=True)
        pedido = Pedido.objects.order_by("-id").first()
        self.assertRedirects(respuesta, reverse("compras:pedido_ficha", args=[pedido.pk]))
        enlaces = {m.to[0]: re.search(r"https?://[^/]+(/proveedor/[\w-]+/)", m.body).group(1) for m in mail.outbox[antes:]}
        return pedido, enlaces

    def cotizar(self, ruta, pedido):
        """El proveedor (sin cuenta) abre su enlace y envía su cotización hasta el final; devuelve su navegador."""
        navegador = Client()
        self.assertRedirects(navegador.get(ruta), PORTAL, fetch_redirect_response=False)
        datos = {"accion": "enviar", "modo": "total", "validez": en(8).isoformat(), "observaciones": ""}
        for detalle in pedido.detalles.all():
            datos.update({f"cantidad_{detalle.pk}": "20", f"precio_{detalle.pk}": "250.00", f"plazo_{detalle.pk}": "3"})
        self.assertContains(navegador.post(PORTAL, datos, follow=True), "Recibimos su cotización")
        return navegador

    def estado(self, objeto):
        objeto.refresh_from_db()
        return getattr(objeto, "estado_pedido", None) or getattr(objeto, "estado", None)

    def test_recorrido_completo_de_cancelar_reenviar_y_lo_que_cancela_solo(self):
        # Paso 1 · CMP-RLZ-PED: la Agrónoma hace un pedido (P1, Norte) e invita a dos proveedores; cada uno recibe su enlace.
        p1, enlaces = self.hacer_pedido(self.ana, [(self.lechuga, "20")])
        self.assertEqual(sorted(enlaces), ["info@este.com", "ventas@sur.com"])
        ficha1 = reverse("compras:pedido_ficha", args=[p1.pk])
        invitacion_sur = p1.invitaciones.get(proveedor=self.sur)
        invitacion_este = p1.invitaciones.get(proveedor=self.viveros)

        # Paso 2 · CMP-CNS-PED, reglas 7 y 8 y D-30: la ficha ofrece «Cancelar pedido» y «Reenviar invitación» a cada invitado que no cotizó.
        ficha = self.client.get(ficha1)
        self.assertContains(ficha, reverse("compras:pedido_cancelar", args=[p1.pk]))
        for invitacion in (invitacion_sur, invitacion_este):
            self.assertContains(ficha, reverse("compras:invitacion_reenviar", args=[invitacion.pk]))

        # Paso 3 · Regla 7 (H15.1): «Reenviar invitación» a Semillas del Sur. La ventana pide confirmar y no cambia nada; confirmar manda un correo con un enlace nuevo.
        reenviar = reverse("compras:invitacion_reenviar", args=[invitacion_sur.pk])
        ventana = self.client.get(reenviar, **HX)
        self.assertContains(ventana, "Reenviar invitación a Semillas del Sur S. A.")
        self.assertContains(ventana, "ventas@sur.com")
        self.assertEqual(invitacion_sur.enlaces.count(), 1)
        antes = len(mail.outbox)
        respuesta = self.client.post(reenviar, follow=True)
        self.assertContains(respuesta, "Enviamos la invitación nueva a Semillas del Sur S. A.")
        self.assertEqual([m.to for m in mail.outbox[antes:]], [["ventas@sur.com"]])
        enlace_nuevo_sur = re.search(r"https?://[^/]+(/proveedor/[\w-]+/)", mail.outbox[-1].body).group(1)
        self.assertNotEqual(enlace_nuevo_sur, enlaces["ventas@sur.com"])
        self.assertEqual(invitacion_sur.enlaces.filter(estado="vigente").count(), 1)
        self.assertEqual(self.auditoria("reenvio_invitacion").count(), 1)

        # Paso 4 · D-88 punto 2: con el enlace viejo el proveedor ya no entra («reemplazado», sin datos del pedido); el nuevo sí.
        viejo = Client().get(enlaces["ventas@sur.com"])
        self.assertContains(viejo, "Este enlace no se puede usar")
        self.assertContains(viejo, "fue reemplazado por uno más nuevo")
        self.assertNotContains(viejo, "Lechuga")
        self.assertRedirects(Client().get(enlace_nuevo_sur), PORTAL, fetch_redirect_response=False)

        # Paso 5 · Regla 7: Viveros del Este cotiza; ya no se le puede reenviar (ni se ofrece el botón), y el Gerente ve la ficha sin acciones ni acceso a las pantallas de cambio.
        self.cotizar(enlaces["info@este.com"], p1)
        self.client.force_login(self.ana)
        ficha = self.client.get(ficha1)
        self.assertNotContains(ficha, reverse("compras:invitacion_reenviar", args=[invitacion_este.pk]))
        self.assertRedirects(self.client.get(reverse("compras:invitacion_reenviar", args=[invitacion_este.pk]), follow=True), ficha1)
        self.client.force_login(self.gerente)
        ficha_del_gerente = self.client.get(ficha1)
        self.assertNotContains(ficha_del_gerente, reverse("compras:pedido_cancelar", args=[p1.pk]))
        self.assertNotContains(ficha_del_gerente, "Reenviar invitación")
        self.assertEqual(self.client.get(reverse("compras:pedido_cancelar", args=[p1.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("compras:invitacion_reenviar", args=[invitacion_sur.pk])).status_code, 403)
        # …y ni otra Agrónoma ni el Capataz.
        for cuenta in (self.otra, self.capataz):
            self.client.force_login(cuenta)
            self.assertEqual(self.client.get(reverse("compras:pedido_cancelar", args=[p1.pk])).status_code, 403)

        # Paso 6 · CMP-CNL-PED: la Agrónoma cancela P1. El formulario no cancela nada; sin motivo, error junto al campo; con motivo, el resumen cuenta qué se descarta y a quién se avisa.
        self.client.force_login(self.ana)
        cancelar = reverse("compras:pedido_cancelar", args=[p1.pk])
        self.assertContains(self.client.get(cancelar), "no se puede deshacer")
        self.assertContains(self.client.post(cancelar, {"accion": "revisar", "motivo": "  "}), "Contá por qué se cancela el pedido.")
        resumen = self.client.post(cancelar, {"accion": "revisar", "motivo": "Ya no hace falta."})
        self.assertContains(resumen, "Confirmá la cancelación del pedido")
        self.assertEqual((resumen.context["resumen"].descartadas, resumen.context["resumen"].enlaces), (1, 1))
        self.assertContains(self.client.post(cancelar, {"accion": "editar", "motivo": "Ya no hace falta."}), "Ya no hace falta.")
        self.assertEqual(self.estado(p1), "en_cotizacion")
        antes = len(mail.outbox)
        confirmada = self.client.post(cancelar, {"accion": "confirmar", "motivo": "Ya no hace falta."}, follow=True)
        self.assertRedirects(confirmada, ficha1)
        self.assertContains(confirmada, f"Pedido {p1} cancelado.")
        self.assertContains(confirmada, "Motivo de la cancelación:")
        self.assertNotContains(confirmada, cancelar)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox[antes:]), ["info@este.com", "ventas@sur.com"])
        self.assertTrue(all("Ya no hace falta." not in m.body for m in mail.outbox[antes:]))
        self.assertEqual(Cotizacion.objects.get(pedido=p1).estado_cotizacion, "descartada")
        self.assertEqual(EnlaceProveedor.objects.get(invitacion=invitacion_sur, estado="anulado").estado, "anulado")

        # Paso 7 · D-88 punto 2 y extensión 6a: ningún enlace de P1 sirve más; no se puede cancelar dos veces ni reenviar; la auditoría tiene la cancelación del Agrónomo.
        for ruta in (enlace_nuevo_sur, enlaces["info@este.com"]):
            self.assertContains(Client().get(ruta), "El pedido fue cancelado.")
        self.assertRedirects(self.client.get(cancelar, follow=True), ficha1)
        self.assertRedirects(self.client.get(reverse("compras:invitacion_reenviar", args=[invitacion_sur.pk]), follow=True), ficha1)
        registro = self.auditoria("cancelacion_pedido").get()
        self.assertEqual((registro.usuario_id, registro.rol, registro.detalle["cambios"]["causa_cancelacion"]["despues"]), (self.ana.pk, "agronomo", "manual"))
        self.assertFalse(Notificacion.objects.filter(titulo__contains="cancelado").exists())  # la cancelación manual no avisa en la campana (H21); el «cubierto» de P1 es de CMP-02a

        # Paso 8 · MD-62 y H17: P2 va a Norte y a Norte 2, y P3 solo a Norte 2. El Gerente cambia a la Agrónoma de Norte: la ventana avisa que se cancela 1 pedido (P2) y no guarda hasta confirmar.
        p2, _ = self.hacer_pedido(self.ana, [(self.lechuga, "20"), (self.nutriente, "3")])
        p3, _ = self.hacer_pedido(self.ana, [(self.nutriente, "3")])
        self.client.force_login(self.gerente)
        modificar = reverse("maestros:invernadero_modificar", args=[self.norte.pk])
        misiones = Provincia.objects.get(nombre_provincia="Misiones")
        capital = Departamento.objects.get(nombre_departamento="Capital", provincia=misiones)
        formulario = {
            "nombre": "Invernadero Norte",
            "tipo_direccion": "urbana",
            "provincia": misiones.pk,
            "departamento": capital.pk,
            "localidad": localidad().pk,
            "calle": "Calle 122",
            "numero_calle": "3310",
            "agronomo": self.nuevo.pk,
        }
        ventana = self.client.post(modificar, formulario)
        self.assertContains(ventana, "Confirmá el cambio de personal")
        self.assertContains(ventana, "Se cancela 1 pedido de cotización en curso")
        self.assertNotContains(ventana, "Recibe 1")  # nadie «recibe» pedidos que se cancelan
        self.assertEqual((self.estado(p2), self.estado(p3)), ("en_cotizacion", "en_cotizacion"))
        self.client.post(modificar, {**formulario, "personal_confirmado": "1"})
        p2.refresh_from_db()
        self.assertEqual((p2.estado_pedido, p2.causa_cancelacion, p2.motivo_cancelacion), ("cancelado", "agronomo_sin_invernadero", "Agrónomo sin el invernadero de destino"))
        self.assertEqual(self.estado(p3), "en_cotizacion")  # solo iba a Norte 2, que Ana conserva
        modificacion = self.auditoria("modificacion_invernadero").get()
        self.assertIn(p2.pk, [a["id"] for a in modificacion.afectados if a["modelo"] == "compras.pedido"])
        # H21: se avisa a quien corresponde (la Agrónoma de Norte 2 y la nueva de Norte), nunca al Gerente que hizo el cambio.
        avisados = set(Notificacion.objects.filter(titulo__contains=str(p2)).values_list("destinatario_id", flat=True))
        self.assertEqual(avisados, {self.ana.pk, self.nuevo.pk})

        # Paso 9 · MD-62 y regla 4 de USR-BAJ-USR: la ventana de baja de la cuenta de Ana dice cuántos pedidos se cancelan; al confirmar se cancela P3 y la baja deja el pedido en su registro.
        baja = reverse("core:usuario_baja", args=[self.ana.pk])
        ventana = self.client.get(baja, **HX)
        self.assertContains(ventana, "Pedidos de cotización en curso")
        self.assertContains(ventana, "Es 1: se cancelan solos")
        self.client.post(baja)
        p3.refresh_from_db()
        self.assertEqual((p3.estado_pedido, p3.causa_cancelacion), ("cancelado", "agronomo_inactivo"))
        registro_de_baja = self.auditoria("baja").get()
        self.assertEqual([r["id"] for r in registro_de_baja.detalle["datos"]["pedidos_cancelados"]], [p3.pk])
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente, titulo__contains=str(p3)).exists())

        # Paso 10 · H20: «Otra» hace dos pedidos (P4 y P5) en Este; con P4 en curso no puede deshabilitar el tomate: la ventana lo dice con un enlace al pedido y el POST no cambia nada.
        p4, _ = self.hacer_pedido(self.otra, [(self.tomate, "10")])
        p5, enlaces5 = self.hacer_pedido(self.otra, [(self.pepino, "10")])
        deshabilitar = reverse("inventario:existencia_deshabilitar", args=[self.tomate.pk])
        ventana = self.client.get(deshabilitar, **HX)
        self.assertContains(ventana, f"Está en el pedido {p4}")
        self.assertContains(ventana, reverse("compras:pedido_ficha", args=[p4.pk]))
        self.client.post(deshabilitar)
        self.tomate.refresh_from_db()
        self.assertEqual(self.tomate.estado_insumo_invernadero, "activo")
        # El Gerente tampoco puede dar de baja el invernadero Este: la ventana trae el mismo enlace.
        self.client.force_login(self.gerente)
        ventana = self.client.get(reverse("maestros:invernadero_baja", args=[self.este.pk]), **HX)
        self.assertContains(ventana, f"Está en el pedido {p4}")
        self.assertContains(ventana, "Ver detalle")
        # Cancelado P4 por «Otra», el tomate se deshabilita (el pepino sigue con P5 en curso).
        self.client.force_login(self.otra)
        self.client.post(reverse("compras:pedido_cancelar", args=[p4.pk]), {"accion": "confirmar", "motivo": "Cambió el plan."})
        self.client.post(deshabilitar)
        self.tomate.refresh_from_db()
        self.assertEqual(self.tomate.estado_insumo_invernadero, "inactivo")
        self.pepino.refresh_from_db()
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.pepino.pk).estado_insumo_invernadero, "activo")

        # Paso 11 · CMP-BAJ-PRV regla 3 (H22): el Gerente da de baja a Semillas del Sur. Su enlace de P5 pasa a «anulado» y deja de servir; el de Viveros sigue sirviendo; P5 sigue en cotización.
        self.client.force_login(self.gerente)
        baja_proveedor = reverse("compras:proveedor_baja", args=[self.sur.pk])
        self.assertContains(self.client.get(baja_proveedor, **HX), "dejan de servir")
        self.client.post(baja_proveedor)
        self.assertEqual(self.estado(p5), "en_cotizacion")
        self.assertContains(Client().get(enlaces5["ventas@sur.com"]), "Este enlace fue anulado.")
        self.assertRedirects(Client().get(enlaces5["info@este.com"]), PORTAL, fetch_redirect_response=False)
        registro = self.auditoria("baja_proveedor").get()
        self.assertEqual(len(registro.detalle["datos"]["enlaces_anulados"]), 1)

        # Paso 12 · D-88 y D-36: nada del token ni de su resumen quedó en el registro de auditoría.
        for registro in RegistroAuditoria.objects.filter(accion__in=["cancelacion_pedido", "reenvio_invitacion", "baja_proveedor"]):
            for enlace in EnlaceProveedor.objects.all():
                self.assertNotIn(enlace.token_resumen, str(registro.detalle) + str(registro.afectados))

    def auditoria(self, accion):
        return RegistroAuditoria.objects.filter(accion=accion)
