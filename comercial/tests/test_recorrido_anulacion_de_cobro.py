# Recorrido de COM-08b (D-96; `docs/patrones/verificacion_a_mano.md`): una prueba larga con el cliente de Django que hace los pasos de la «Verificación a mano» de punta a punta, como lo haría una persona, por rol y por estado.
# No reemplaza lo que prueban `test_com_anl_cbr`, `test_com_reg_cbr`, `test_com_cnl_cvt` y `test_cobranza_vistas`: acá importa que el flujo ENCADENE: el Gerente anula un cobro de dos entregas (una en mora y otra pendiente, la primera
# vez que se avisa la mora), el Vendedor no ve «Anular» ni entra por URL, un cobro de compra-venta no se anula desde acá, el cobro correcto con la fecha original se usa una sola vez, sin la casilla es un cobro común, las
# entregas anuladas liberan la anulación de una solicitud (2b) y, al final, la cancelación de una compra-venta con una entrega concretada cobra lo entregado y deja la venta «concretada» con el cobro en el comprobante.
# Sin navegador: el CSRF, el `Origin` y el JavaScript van en el paso de «navegador real» de la «Verificación a mano».
# Fuente: docs/tareas/comercial/COM-08b-anular-cobro-y-cobro-al-cancelar.md («Verificación a mano»), docs/casos_de_uso/comercial/cobranza.md («Anular un cobro»), compra_venta.md («La extensión 6a (COM-08b)»).

from datetime import timedelta
from decimal import Decimal
from html import unescape

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Anulacion, CompraVenta, Entrega, PagoCliente
from comercial.servicios import concrecion
from comercial.servicios.compra_ventas import texto_de_pesos
from comercial.tests.base_cobranza import BaseDeCobranza
from comercial.tests.fabricas import (
    cobro,
    compra_venta,
    detalle,
    discrepancia_aceptada,
    entrega,
    entrega_de_suministro,
    pago_de_compra_venta,
    reserva_lista,
)
from core.models import RegistroAuditoria
from maestros.tests.fabricas import crear_vendedor
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

D = Decimal
HOY = timezone.localdate()


def texto(respuesta):
    return unescape(respuesta.content.decode())


class RecorridoDeAnulacionDeCobroTests(BaseDeCobranza):
    def ir(self, nombre, *args, usuario, **extra):
        self.client.force_login(usuario)
        return self.client.get(reverse(f"comercial:{nombre}", args=args), **extra)

    def enviar(self, nombre, *args, usuario, datos=None, **extra):
        self.client.force_login(usuario)
        return self.client.post(reverse(f"comercial:{nombre}", args=args), datos or {}, **extra)

    def cobrar(self, entregas_, *, usuario, medio="transferencia"):
        """Un cobro por las pantallas (resumen y confirmación), como lo hace una persona."""
        pedido = {"cliente": str(self.e.cliente.pk), "cliente_fijo": "1", "entrega": [str(e.pk) for e in entregas_], "medio_pago": medio}
        huella = self.enviar("cobranza_revisar", usuario=usuario, datos=pedido).context["resumen"].huella
        self.enviar("cobranza_registrar", usuario=usuario, datos={**pedido, "accion": "confirmar", "huella": huella})
        return PagoCliente.objects.filter(tipo_pago="suministro", lineas__entrega=entregas_[0]).order_by("-pk").first()

    def anular(self, pago, *, motivo, cliente_pago, usuario=None):
        """La anulación por las pantallas: abre «Anular», escribe el motivo, marca (o no) la casilla y confirma."""
        usuario = usuario or self.gerente
        huella = self.ir("cobro_anular", pago.pk, usuario=usuario).context["datos"].huella
        datos = {"huella": huella, "motivo": motivo, **({"cliente_pago_en_fecha": "1"} if cliente_pago else {})}
        return self.enviar("cobro_anular", pago.pk, usuario=usuario, datos=datos, follow=True)

    def alertas_activas(self, entrega_):
        return AlertaComercial.objects.filter(entrega=entrega_, alerta__tipo_alerta="comercial_pago_en_mora", alerta__estado_alerta="activa").count()

    def test_recorrido_de_la_anulacion_de_un_cobro_y_del_cobro_al_cancelar_de_punta_a_punta(self):
        vendedor, gerente = self.e.vendedor, self.gerente
        ajeno = crear_vendedor(email="otro.vendedor2@infoponia.com")

        # ---- Datos (lo que la «Verificación a mano» crea a mano): un suministro con plazo de 10 días y $ 300 por día de atraso; `a` vencida hace 5 días (en mora) y `b` que vence en 5 (pendiente). ----
        a = entrega_de_suministro(self.e, self.lote, plazo_pago=10, indemnizacion_pago="300.00", hace_dias=15)
        contrato = a.contrato_entrega.suministro
        b = entrega_de_suministro(self.e, self.lote, contrato=contrato, hace_dias=5)

        # ---- Paso 1 (Gerente): cobra las dos entregas con transferencia ($ 1.000 + $ 1.000 + 5 × $ 300). El paso 30 no había corrido: `a` nunca fue avisada. ----
        primero = self.cobrar([a, b], usuario=gerente)
        self.assertEqual((primero.monto_pagado, primero.estado_pago), (D("3500.00"), "vigente"))
        self.assertEqual((Entrega.objects.get(pk=a.pk).fecha_aviso_mora, self.alertas_activas(a)), (None, 0))

        # ---- Paso 2 (roles): el Vendedor del contrato no ve «Anular» (lista y ficha) y por URL recibe 403; otro Vendedor y los demás roles, también. ----
        anular_url = reverse("comercial:cobro_anular", args=[primero.pk])
        self.assertNotIn(anular_url, texto(self.ir("cobranza", usuario=vendedor, QUERY_STRING="vista=cobros")))
        self.assertNotIn(anular_url, texto(self.ir("cobro", primero.pk, usuario=vendedor)))
        for usuario in (vendedor, ajeno, self.e.agronomo, self.e.capataz):
            self.assertEqual(self.ir("cobro_anular", primero.pk, usuario=usuario).status_code, 403, usuario)
            self.assertEqual(self.enviar("cobro_anular", primero.pk, usuario=usuario, datos={"motivo": "x", "huella": "x"}).status_code, 403, usuario)
        self.assertEqual(PagoCliente.objects.get(pk=primero.pk).estado_pago, "vigente")

        # ---- Paso 3 (cobro de compra-venta): no tiene «Anular»; por URL, el mensaje «se corrige con un asiento manual»; no se anula nada. ----
        venta_pagada = compra_venta(self.e, dias=0)
        pago_venta = pago_de_compra_venta(venta_pagada)
        self.assertIn("asiento manual", texto(self.ir("cobro_anular", pago_venta.pk, usuario=gerente, follow=True)))
        self.assertEqual(PagoCliente.objects.get(pk=pago_venta.pk).estado_pago, "vigente")

        # ---- Paso 4 (Gerente): la pantalla dice qué entrega vuelve a «en mora» y cuál a «pendiente»; sin motivo, error junto al campo. ----
        self.assertIn(anular_url, texto(self.ir("cobranza", usuario=gerente, QUERY_STRING="vista=cobros")))
        pantalla = texto(self.ir("cobro_anular", primero.pk, usuario=gerente))
        self.assertIn(f"{a.codigo}", pantalla)
        self.assertIn("vuelve a «en mora»", pantalla)
        self.assertIn("vuelve a «pendiente»", pantalla)
        self.assertIn("Fuera de esta ronda · contabilidad", pantalla)
        huella = self.ir("cobro_anular", primero.pk, usuario=gerente).context["datos"].huella
        sin_motivo = self.enviar("cobro_anular", primero.pk, usuario=gerente, datos={"huella": huella, "motivo": "", "cliente_pago_en_fecha": "1"})
        self.assertIn("Escribí el motivo de la anulación.", texto(sin_motivo))
        self.assertEqual(PagoCliente.objects.get(pk=primero.pk).estado_pago, "vigente")

        # ---- Paso 5: anula con motivo y «el cliente pagó en esa fecha»: queda anulado con su historia; vuelve la alerta de `a` y sale su PRIMER correo de mora; el Vendedor recibe un solo aviso; `b` queda pendiente. ----
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            ficha = self.anular(primero, motivo="Cargué la transferencia con el cliente equivocado.", cliente_pago=True)
        primero.refresh_from_db()
        anulacion = Anulacion.objects.get(pago_cliente=primero)
        html = texto(ficha)
        self.assertEqual(primero.estado_pago, "anulado")
        for esperado in (f"{primero.codigo} anulado", "Anulación", "Cargué la transferencia con el cliente equivocado.", "Todavía no se registró.", "Registrar el cobro correcto"):
            self.assertIn(esperado, html)
        self.assertNotIn(anular_url, html)  # un cobro anulado no vuelve a ofrecer «Anular»
        self.assertEqual((self.alertas_activas(a), self.alertas_activas(b), Entrega.objects.get(pk=a.pk).fecha_aviso_mora), (1, 0, HOY))
        self.assertEqual([m.subject for m in mail.outbox], [f"Pago en mora de la entrega {a.codigo}"])  # el cliente no recibe otro correo por la anulación
        (aviso,) = self.avisos(vendedor, f"{primero.codigo} anulado")
        self.assertIn(f"{a.codigo} (en mora)", aviso.detalle)
        self.assertIn(f"{b.codigo} (pendiente)", aviso.detalle)
        self.assertEqual(self.avisos(vendedor, f"{a.codigo} en mora"), [])
        mail.outbox.clear()
        self.assertIn(f"{primero.codigo}", texto(self.ir("cobranza", usuario=gerente, QUERY_STRING="vista=cobros&estado=anulado")))

        # ---- Paso 6 (cobro correcto con la fecha original, 7a): el cobro anulado es de hace 2 días; se usa su fecha; la indemnización es la de ese día; se usa una sola vez. ----
        d = self.en_mora(dias_de_mora=5)  # concretada hace 15 días: vence hace 5
        original = cobro([d], usuario=gerente, fecha=HOY - timedelta(days=2))  # 3 días de atraso: $ 900
        self.anular(original, motivo="El medio estaba mal cargado.", cliente_pago=True)
        anulacion_d = Anulacion.objects.get(pago_cliente=original)
        url = reverse("comercial:cobranza_registrar") + f"?anulacion={anulacion_d.pk}"
        pantalla = texto(self.client.get(url))
        self.assertIn("Usar la fecha del cobro anulado", pantalla)
        self.assertIn(f"{HOY - timedelta(days=2):%d/%m/%Y}", pantalla)
        pedido = {"cliente": str(self.e.cliente.pk), "cliente_fijo": "1", "entrega": [str(d.pk)], "medio_pago": "efectivo", "anulacion": str(anulacion_d.pk), "usar_fecha_anulada": "1"}
        resumen = self.enviar("cobranza_revisar", usuario=gerente, datos=pedido)
        self.assertEqual((resumen.context["resumen"].indemnizacion, resumen.context["resumen"].fecha_pago), (D("900.00"), HOY - timedelta(days=2)))
        with override_settings(CORREO_CONFIGURADO=False):
            self.enviar("cobranza_registrar", usuario=gerente, datos={**pedido, "accion": "confirmar", "huella": resumen.context["resumen"].huella})
        correcto = PagoCliente.objects.get(anulacion_corregida=anulacion_d)
        self.assertEqual((correcto.fecha_pago, correcto.monto_pagado), (HOY - timedelta(days=2), D("1900.00")))
        self.assertIn("ya se registró", texto(self.client.get(url, follow=True)))
        self.assertEqual(self.alertas_activas(d), 0)

        # ---- Paso 7 (sin la casilla): se anula otro cobro sin marcar «el cliente pagó»; el cobro nuevo es común, con la fecha de hoy y sin `anulacion_corregida`. ----
        e = self.en_mora(dias_de_mora=3)
        otro = self.cobrar([e], usuario=gerente)
        self.anular(otro, motivo="El cliente no había pagado todavía.", cliente_pago=False)
        sin_casilla = texto(self.client.get(reverse("comercial:cobranza_registrar") + f"?anulacion={Anulacion.objects.get(pago_cliente=otro).pk}"))
        self.assertNotIn("Usar la fecha del cobro anulado", sin_casilla)
        nuevo = self.cobrar([e], usuario=gerente, medio="efectivo")
        self.assertEqual((nuevo.fecha_pago, nuevo.anulacion_corregida_id, nuevo.estado_pago), (HOY, None, "vigente"))

        # ---- Paso 8 (lo que la anulación libera): una solicitud aceptada con descuento de una entrega cobrada no se podía anular («Primero anulá el cobro»); con el cobro anulado, sí. ----
        f = entrega_de_suministro(self.e, self.lote, contrato=contrato, hace_dias=2)
        solicitud = discrepancia_aceptada(f, monto="200.00", descontado="200.00")
        cobro_f = self.cobrar([f], usuario=gerente)
        self.assertIn("Primero anulá el cobro", texto(self.ir("solicitud_anular", solicitud.pk, usuario=gerente)))
        self.anular(cobro_f, motivo="Había que cobrar sin el descuento.", cliente_pago=False)
        self.assertNotIn("Primero anulá el cobro", texto(self.ir("solicitud_anular", solicitud.pk, usuario=gerente)))

        # ---- Paso 9 (cancelar con cobro, 6a): una venta de retiro con dos entregas; la primera se concreta de verdad; al cancelar, la pantalla pide el medio, el resumen no escribe y la confirmación cobra lo entregado. ----
        otra, _ = variedad_con_stock(self.e, "Otra variedad recorrido")
        lote_b = lote_maduro(self.e, 500, variedad=otra)
        venta = compra_venta(self.e, dias=0, modalidad="retiro", retiro=self.e.invernadero)
        d1, d2 = detalle(venta, self.e.variedad, 50), detalle(venta, otra, 30)
        e1 = entrega(venta, [reserva_lista(d1, self.lote, 50)], fecha=HOY)
        e2 = entrega(venta, [reserva_lista(d2, lote_b, 30)], fecha=HOY)
        datos = concrecion.DatosDeConcrecion(sin_envases=True, medio_pago="efectivo")
        concrecion.concretar_entrega(vendedor, e1.pk, datos, concrecion.resumen_de_concrecion(vendedor, e1.pk, datos).huella)
        cancelar = reverse("comercial:compra_venta_cancelar", args=[venta.pk])
        revisar = reverse("comercial:compra_venta_cancelar_revisar", args=[venta.pk])
        pantalla = texto(self.ir("compra_venta_cancelar", venta.pk, usuario=vendedor))
        self.assertIn("3 · Cobro de lo entregado", pantalla)
        huella = self.ir("compra_venta_cancelar", venta.pk, usuario=vendedor).context["datos"].huella
        sin_medio = self.client.post(revisar, {"huella": huella, "motivo": "cliente_desistio", "descripcion": ""})
        self.assertIn("Elegí el medio de pago con que el cliente paga lo entregado.", texto(sin_medio))
        pedido = {"huella": huella, "motivo": "cliente_desistio", "descripcion": "No lo necesita más", "medio_pago": "tarjeta_debito"}
        resumen = self.client.post(revisar, pedido)
        self.assertIn("Concretada (se cobra lo entregado)", texto(resumen))
        self.assertEqual((CompraVenta.objects.get(pk=venta.pk).estado_venta, PagoCliente.objects.filter(compra_venta=venta).count()), ("abierta", 0))
        with override_settings(CORREO_CONFIGURADO=True):
            cancelada = self.client.post(cancelar, pedido, follow=True)
        pago = PagoCliente.objects.get(compra_venta=venta)
        self.assertEqual((CompraVenta.objects.get(pk=venta.pk).estado_venta, Entrega.objects.get(pk=e2.pk).estado_orden), ("concretada", "cancelada"))
        self.assertEqual((pago.tipo_pago, pago.medio_pago, pago.estado_pago, pago.usuario_id), ("compra_venta", "tarjeta_debito", "vigente", vendedor.pk))
        self.assertIn(f"Se cobró lo entregado ({texto_de_pesos(pago.monto_pagado)}, tarjeta de débito)", texto(cancelada))
        comprobante = texto(self.ir("compra_venta_comprobante", venta.pk, usuario=vendedor))
        self.assertIn("Cobro de lo entregado", comprobante)
        self.assertIn(texto_de_pesos(pago.monto_pagado), comprobante)
        self.assertIn("Cobro de lo entregado", mail.outbox[-1].body)

        # ---- Paso 10 (auditoría): una por cada anulación, con el Gerente; y la cancelación con el pago entre los afectados. ----
        self.assertEqual(RegistroAuditoria.objects.filter(accion="anulacion_cobro").count(), 4)
        cancelacion = RegistroAuditoria.objects.get(accion="cancelacion_compra_venta")
        self.assertTrue(any(x["modelo"] == "comercial.pagocliente" and x["id"] == pago.pk for x in cancelacion.afectados))
