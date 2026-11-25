# Recorrido de CMP-05 (pago a proveedores) de punta a punta con el cliente de Django, como lo haría una persona, por rol y por estado (D-96, docs/patrones/verificacion_a_mano.md): el Agrónomo recibe lo de
# la orden; el Contador ve el aviso, el Inicio y la bandeja, registra el pago por transferencia (resumen y confirmación) y la cuenta Proveedores de ese proveedor da cero; el Gerente mira en solo lectura
# mientras hay Contador y, sin Contador, paga en efectivo; una orden cerrada con faltante se paga por lo recibido; la baja del proveedor se bloquea hasta pagar; y los demás roles no entran. Lo que
# el cliente no ve (el token CSRF, el encabezado ``Origin`` y el JavaScript) es el paso de «navegador real» de la «Verificación a mano».

from decimal import Decimal

from django.core import mail
from django.urls import reverse

from compras.models import Pago
from compras.servicios import recepciones
from compras.tests.base_pagos import PagosBase
from contabilidad import cuentas
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import verificar_invariantes_contables
from core.models import Notificacion
from maestros.tests.fabricas import crear_vendedor

D = Decimal


class RecorridoDePagosTests(PagosBase):
    """El recorrido completo: recibir → avisar → pagar → cero en Proveedores → baja del proveedor."""

    def pagar_por_pantalla(self, orden, proveedor, medio, fecha=None):
        """Los pasos 3 a 10 como los hace una persona: abre el formulario, ve el resumen y confirma. Devuelve la respuesta del resumen."""
        url = reverse("compras:pago_nuevo", args=[orden.pk, proveedor.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        datos = {"medio_pago": medio, "fecha": (fecha or self.hoy).isoformat()}
        resumen = self.client.post(url, {**datos, "accion": "revisar"})
        self.assertContains(resumen, "Confirmá el pago")
        with self.captureOnCommitCallbacks(execute=True):
            confirmacion = self.client.post(url, {**datos, "accion": "confirmar"})
        self.assertRedirects(confirmacion, reverse("compras:pagos"), fetch_redirect_response=False)
        return resumen

    def proveedores_en_el_libro(self):
        return libro.saldo_por_cuenta(self.abierto.pk)[cuentas.PROVEEDORES].saldo

    def test_recorrido_de_punta_a_punta(self):
        # 1. El Agrónomo recibe todo lo de A y, por separado, parte de lo de B. Nadie paga todavía.
        self.recibir_a()
        self.assertEqual(self.proveedores_en_el_libro(), D("300.00"))

        # 2. El Contador: ve el aviso «Proveedor para pagar», la sección del Inicio y «Pagos a proveedores» en el menú.
        self.client.force_login(self.contador)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.contador, titulo="Proveedor para pagar").count(), 1)
        inicio = self.client.get(reverse("core:inicio"))
        self.assertContains(inicio, "Pagos a proveedores pendientes")
        self.assertContains(inicio, self.proveedor.nombre_para_mostrar)
        self.assertContains(inicio, 'href="' + reverse("compras:pagos") + '"')

        # 3. La bandeja lo muestra con su monto y la orden; entra por «Registrar pago» y lo paga por transferencia.
        bandeja = self.client.get(reverse("compras:pagos"))
        self.assertContains(bandeja, "300,00")
        self.assertNotContains(bandeja, self.proveedor_b.nombre_para_mostrar)  # B todavía tiene todo por recibir
        correos_antes = len(mail.outbox)
        resumen = self.pagar_por_pantalla(self.orden, self.proveedor, "transferencia")
        self.assertContains(resumen, "Haber Banco c/c")

        # 4. El pago quedó con su asiento (Banco), el proveedor recibió el correo y la cuenta Proveedores de A da cero.
        pago = Pago.objects.get()
        self.assertEqual((pago.monto_pago, pago.medio_pago, pago.fecha_pago), (D("300.00"), "transferencia", self.hoy))
        self.assertEqual(self.movimientos_de(self.asiento_del_pago(pago)), [(cuentas.PROVEEDORES, "D", D("300.00")), (cuentas.BANCO, "H", D("300.00"))])
        self.assertEqual(self.proveedores_en_el_libro(), D("0.00"))
        self.assertEqual([m.to for m in mail.outbox[correos_antes:]], [["ventas@sur.com"]])
        self.assertContains(self.client.get(reverse("compras:pagos")), "No hay proveedores para pagar")

        # 5. Un segundo pago de lo mismo se rechaza: lleva a la ficha, que muestra el pago ya registrado.
        repetido = self.client.get(reverse("compras:pago_nuevo", args=[self.orden.pk, self.proveedor.pk]))
        self.assertRedirects(repetido, reverse("compras:orden_ficha", args=[self.orden.pk]), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("compras:orden_ficha", args=[self.orden.pk])), f"PAG-{pago.pk:04d}")

        # 6. B recibe lo suyo: con un Contador activo el Gerente ve la bandeja pero no puede registrar (sin botón y 403).
        self.recibir_b()
        self.client.force_login(self.gerente)
        solo_lectura = self.client.get(reverse("compras:pagos"))
        self.assertContains(solo_lectura, self.proveedor_b.nombre_para_mostrar)
        self.assertNotContains(solo_lectura, "Registrar pago")
        url_de_b = reverse("compras:pago_nuevo", args=[self.orden.pk, self.proveedor_b.pk])
        self.assertEqual(self.client.get(url_de_b).status_code, 403)

        # 7. La baja de B queda bloqueada por el pago pendiente, con el enlace a la orden.
        ventana = self.client.get(reverse("compras:proveedor_baja", args=[self.proveedor_b.pk]))
        self.assertContains(ventana, "Tiene un pago pendiente de la orden de compra")
        self.assertContains(ventana, reverse("compras:orden_ficha", args=[self.orden.pk]))

        # 8. Se da de baja al Contador: ahora el Gerente es el responsable y paga a B en efectivo.
        self.sin_contador()
        self.assertContains(self.client.get(reverse("core:inicio")), "Pagos a proveedores pendientes")
        self.pagar_por_pantalla(self.orden, self.proveedor_b, "efectivo")
        pago_b = Pago.objects.get(proveedor=self.proveedor_b)
        self.assertEqual((pago_b.monto_pago, self.movimientos_de(self.asiento_del_pago(pago_b))[1][0]), (D("80.00"), cuentas.CAJA))
        self.assertEqual(self.proveedores_en_el_libro(), D("0.00"))

        # 9. Pagada la orden, B se puede dar de baja.
        baja = self.client.post(reverse("compras:proveedor_baja", args=[self.proveedor_b.pk]))
        self.assertEqual(baja.status_code, 302)
        self.proveedor_b.refresh_from_db()
        self.assertEqual(self.proveedor_b.estado_proveedor, "inactivo")

        # 10. Los demás roles no entran a los pagos.
        for usuario in (self.ana, crear_vendedor()):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse("compras:pagos")).status_code, 403)

        verificar_invariantes_contables()

    def test_recorrido_de_una_orden_cerrada_con_faltante_se_paga_por_lo_recibido(self):
        """Otra orden (6 unidades a $60,00): llegan 2, el resto se cierra con faltante y el Contador paga $20,00 con tarjeta de crédito, a Banco; Proveedores de esa orden da cero."""
        orden, linea, _ = self.otra_orden(self.ana, self.norte, "Sustrato", cantidad=6, total="60.00", n=5)
        proveedor = linea.proveedor
        self.registrar(self.ana, [self.linea(linea, 2)], orden=orden, proveedor=proveedor)
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(linea.pk, "No repone.")])
        self.client.force_login(self.contador)
        formulario = self.client.get(reverse("compras:pago_nuevo", args=[orden.pk, proveedor.pk]))
        self.assertContains(formulario, "Cerrada con faltante")
        self.assertContains(formulario, "20,00")
        self.pagar_por_pantalla(orden, proveedor, "tarjeta_credito")
        pago = Pago.objects.get(orden=orden)
        self.assertEqual(pago.monto_pago, D("20.00"))
        self.assertEqual(self.movimientos_de(self.asiento_del_pago(pago)), [(cuentas.PROVEEDORES, "D", D("20.00")), (cuentas.BANCO, "H", D("20.00"))])
        self.assertEqual(self.proveedores_en_el_libro(), D("0.00"))
        verificar_invariantes_contables()
