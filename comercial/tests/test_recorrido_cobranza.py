# Recorrido de COM-08a (D-96; `docs/patrones/verificacion_a_mano.md`): una prueba larga con el cliente de Django que hace los pasos de la «Verificación a mano» de punta a punta, como lo haría una persona, por rol y por estado. Complementa
# (no reemplaza) lo que prueban `test_com_reg_cbr`, `test_com_vnc_pag`, `test_reevaluar_mora` y `test_cobranza_vistas`: acá importa que el flujo ENCADENE: el paso diario 30 pone en mora, la alerta lleva a «Registrar cobro», el resumen no
# escribe, el cobro resuelve la alerta y manda el comprobante, el segundo cobro de la misma entrega dice quién la cobró, una aceptación posterior reintegra y no se puede anular, y un Vendedor ajeno no ve nada. Sin navegador: el CSRF, el
# `Origin` y el JavaScript van en el paso de «navegador real» de la «Verificación a mano».
# Fuente: docs/tareas/comercial/COM-08a-cobro-y-mora.md («Verificación a mano»), docs/casos_de_uso/comercial/cobranza.md.

from decimal import Decimal
from html import unescape

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega, PagoCliente, SolicitudRevision
from comercial.tests.base_cobranza import BaseDeCobranza
from comercial.tests.fabricas import discrepancia, entrega_de_suministro
from core.models import Notificacion, RegistroAuditoria
from maestros.tests.fabricas import crear_transportista, crear_vendedor

D = Decimal
HOY = timezone.localdate()


def texto(respuesta):
    return unescape(respuesta.content.decode())


class RecorridoDeCobranzaTests(BaseDeCobranza):
    def ir(self, nombre, *args, usuario, **extra):
        self.client.force_login(usuario)
        return self.client.get(reverse(f"comercial:{nombre}", args=args), **extra)

    def enviar(self, nombre, *args, usuario, datos=None, **extra):
        self.client.force_login(usuario)
        return self.client.post(reverse(f"comercial:{nombre}", args=args), datos or {}, **extra)

    def alertas_activas(self):
        return AlertaComercial.objects.filter(alerta__tipo_alerta="comercial_pago_en_mora", alerta__estado_alerta="activa").count()

    def test_recorrido_de_la_cobranza_de_punta_a_punta(self):
        vendedor, gerente = self.e.vendedor, self.gerente
        ajeno = crear_vendedor(email="otro.vendedor@infoponia.com")

        # ---- Datos (lo que la «Verificación a mano» crea a mano): un suministro con plazo de 10 días y $ 300 por día de atraso, tres entregas concretadas y una cuarta en mora para la alerta. ----
        a = entrega_de_suministro(self.e, self.lote, plazo_pago=10, indemnizacion_pago="300.00", hace_dias=15)  # vence hace 5 días: en mora
        contrato = a.contrato_entrega.suministro
        b = entrega_de_suministro(self.e, self.lote, contrato=contrato, hace_dias=5)  # vence en 5 días: pendiente
        c = entrega_de_suministro(self.e, self.lote, contrato=contrato, hace_dias=3)  # con una discrepancia pendiente
        solicitud = discrepancia(c, minima=12)
        d = entrega_de_suministro(self.e, self.lote, contrato=contrato, hace_dias=14)  # vence hace 4 días: en mora (para la alerta del Gerente)

        # ---- Paso 1 (COM-VNC-PAG): el paso diario 30, a mano; la entrega en mora tiene su alerta, su aviso y su correo; corrido otra vez, no repite nada. ----
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", solo="vencer_pagos")
        self.assertEqual(self.alertas_activas(), 2)  # a y d
        self.assertEqual(len(self.avisos(vendedor, f"{a.codigo} en mora")), 1)
        self.assertEqual([m.to for m in mail.outbox], [[self.e.cliente.email_cliente]] * 2)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", solo="vencer_pagos")
        self.assertEqual((self.alertas_activas(), len(mail.outbox), len(self.avisos(vendedor, "OT-"))), (2, 2, 2))
        mail.outbox.clear()

        # ---- Paso 2 (Vendedor): «Cobranza» muestra al cliente con su total y lo que está en mora; «Registrar cobro» lista las tres/cuatro entregas de la que vence primero a la última y advierte la solicitud pendiente. ----
        html = texto(self.ir("cobranza", usuario=vendedor))
        self.assertIn(self.e.cliente.nombre_visible, html)
        self.assertIn("$ 4.000,00", html)  # a, b, c y d: 4 × $ 1.000
        self.assertIn("$ 2.000,00 en mora", html)
        pantalla = texto(self.ir("cobranza_registrar", usuario=vendedor, QUERY_STRING=f"cliente={self.e.cliente.pk}"))
        orden = [pantalla.index(f'id="entrega-{e.pk}"') for e in (a, d, b, c)]  # por vencimiento: a (hace 5 días), d (hace 4), b (en 5) y c (en 7)
        self.assertEqual(orden, sorted(orden))
        self.assertIn(f"Discrepancia {solicitud.codigo} pendiente", pantalla)
        pedido = {"cliente": str(self.e.cliente.pk), "cliente_fijo": "1", "entrega": [str(a.pk)], "medio_pago": "transferencia"}
        resumen = self.enviar("cobranza_revisar", usuario=vendedor, datos=pedido)
        self.assertIn("5 días · $ 1.500,00", texto(resumen))
        self.assertIn("$ 2.500,00", texto(resumen))
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 0)  # revisar no escribe nada
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            confirmado = self.enviar("cobranza_registrar", usuario=vendedor, datos={**pedido, "accion": "confirmar", "huella": resumen.context["resumen"].huella}, follow=True)
        primero = PagoCliente.objects.get(tipo_pago="suministro")
        self.assertIn(f"{primero.codigo} registrado", texto(confirmado))
        self.assertEqual((primero.monto_pagado, primero.usuario_id), (D("2500.00"), vendedor.pk))
        self.assertEqual((len(mail.outbox), self.alertas_activas()), (1, 1))  # el comprobante salió y la alerta de `a` se resolvió; queda la de `d`
        self.assertIn(f"Pagada · {primero.codigo}", texto(self.ir("suministro", contrato.pk, usuario=vendedor)))
        mail.outbox.clear()

        # ---- Paso 3 (Gerente, desde la alerta): la pantalla abre con la entrega elegida; la cobra; el Vendedor recibe el aviso. ----
        enlace = texto(self.ir("cobranza_registrar", usuario=gerente, QUERY_STRING=f"entrega={d.pk}"))
        self.assertIn(" checked", enlace.split(f'id="entrega-{d.pk}"')[1].split(">")[0])
        pedido_d = {"cliente": str(self.e.cliente.pk), "cliente_fijo": "1", "entrega": [str(d.pk)], "medio_pago": "efectivo"}
        resumen_d = self.enviar("cobranza_revisar", usuario=gerente, datos=pedido_d)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            self.enviar("cobranza_registrar", usuario=gerente, datos={**pedido_d, "accion": "confirmar", "huella": resumen_d.context["resumen"].huella})
        cobro_d = PagoCliente.objects.get(lineas__entrega=d)
        self.assertEqual(len(self.avisos(vendedor, f"{cobro_d.codigo} registrado")), 1)
        self.assertEqual(self.alertas_activas(), 0)

        # ---- Paso 4 (dos pestañas): la segunda sesión cobra la misma entrega y dice quién la cobró, el cobro y la fecha. ----
        pedido_b = {"cliente": str(self.e.cliente.pk), "cliente_fijo": "1", "entrega": [str(b.pk)], "medio_pago": "efectivo"}
        huella_vieja = self.enviar("cobranza_revisar", usuario=gerente, datos=pedido_b).context["resumen"].huella
        with override_settings(CORREO_CONFIGURADO=False):
            self.enviar("cobranza_registrar", usuario=vendedor, datos={**pedido_b, "accion": "confirmar", "huella": huella_vieja})
        segunda = self.enviar("cobranza_registrar", usuario=gerente, datos={**pedido_b, "accion": "confirmar", "huella": huella_vieja})
        pago_b = PagoCliente.objects.get(lineas__entrega=b)
        self.assertEqual(segunda.status_code, 200)
        self.assertIn(f"{b.codigo} ya está pagada: {pago_b.codigo}", texto(segunda))
        self.assertEqual(PagoCliente.objects.filter(tipo_pago="suministro").count(), 3)

        # ---- Paso 5: se cobra `c` (con su discrepancia pendiente); la aceptación posterior pide el medio del reintegro (6a) y después no se puede anular (2c). ----
        pedido_c = {"cliente": str(self.e.cliente.pk), "cliente_fijo": "1", "entrega": [str(c.pk)], "medio_pago": "efectivo"}
        huella_c = self.enviar("cobranza_revisar", usuario=gerente, datos=pedido_c).context["resumen"].huella
        with override_settings(CORREO_CONFIGURADO=False):
            self.enviar("cobranza_registrar", usuario=gerente, datos={**pedido_c, "accion": "confirmar", "huella": huella_c})
        self.assertEqual(entregas_monto(c), D("1000.00"))
        revisar = self.enviar("solicitud_resolver_revisar", solicitud.pk, usuario=gerente, datos={"decision": "aceptar"})
        self.assertIn("La entrega ya está pagada: se reintegran", texto(revisar))
        sin_medio = self.enviar("solicitud_resolver", solicitud.pk, usuario=gerente, datos={"decision": "aceptar", "huella": revisar.context["resumen"].huella})
        self.assertEqual(SolicitudRevision.objects.get(pk=solicitud.pk).estado_solicitud, "pendiente")
        self.assertEqual(sin_medio.status_code, 200)
        with override_settings(CORREO_CONFIGURADO=False):
            self.enviar("solicitud_resolver", solicitud.pk, usuario=gerente, datos={"decision": "aceptar", "medio_reintegro": "transferencia", "huella": revisar.context["resumen"].huella})
        self.assertEqual(SolicitudRevision.objects.get(pk=solicitud.pk).estado_solicitud, "aceptada")
        self.assertEqual(entregas_monto(c), D("1000.00"))  # lo reintegrado no se descontó
        self.assertIn("ya se le reintegró", texto(self.ir("solicitud_anular", solicitud.pk, usuario=gerente)))

        # ---- Paso 6 (roles): otro Vendedor no ve nada y por URL recibe 403; el Transportista, también; la ficha de un cobro propio abre. ----
        self.assertNotIn(self.e.cliente.nombre_visible, texto(self.ir("cobranza", usuario=ajeno)))
        for nombre, args in (("cobro", (primero.pk,)), ("cobro_comprobante", (primero.pk,))):
            self.assertEqual(self.ir(nombre, *args, usuario=ajeno).status_code, 403)
        self.assertEqual(self.enviar("cobranza_revisar", usuario=ajeno, datos=pedido_b).status_code, 403)
        self.assertEqual(self.ir("cobranza", usuario=crear_transportista(email="t3@infoponia.com")).status_code, 403)
        self.assertEqual(self.ir("cobro", primero.pk, usuario=vendedor).status_code, 200)
        self.assertIn(primero.codigo, texto(self.ir("cobranza", usuario=gerente, QUERY_STRING="vista=cobros")))

        # ---- Paso 7 (sin JavaScript): «Calcular total» redibuja la página con el total y no escribe nada; ya está arriba (se cobró con las mismas peticiones, sin HTMX). ----
        # ---- Paso 8: el paso 30, corrido otra vez, no repite nada; auditoría completa. ----
        antes = (Entrega.objects.filter(fecha_aviso_mora__isnull=False).count(), len(mail.outbox), Notificacion.objects.count())
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", solo="vencer_pagos")
        self.assertEqual((Entrega.objects.filter(fecha_aviso_mora__isnull=False).count(), len(mail.outbox), Notificacion.objects.count()), antes)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_cobro").count(), 4)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="vencimiento_pago").count(), 2)


def entregas_monto(entrega):
    """El monto a cobrar de la entrega (después de cobrada no cambia con una aceptación posterior)."""
    from comercial.servicios import entregas

    return entregas.monto_a_cobrar([entrega.pk])[entrega.pk]
