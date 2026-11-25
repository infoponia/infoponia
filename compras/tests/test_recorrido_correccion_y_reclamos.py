# Recorrido de CMP-06 (corrección de recepción y reclamos a proveedores) de punta a punta con el cliente de Django, como lo haría una persona, por rol y por estado (D-96, docs/patrones/verificacion_a_mano.md):
# el Agrónomo recibe lo de la orden con un inconveniente; el Gerente ve el reclamo sin emitir en su Inicio y en «Reclamos», lo emite (el proveedor recibe el correo) y lo cierra; el Agrónomo corrige lo que cargó
# de más (formulario, resumen y confirmación) y el proveedor sale de la bandeja de pagos; se vuelve a recibir lo corregido y el Contador paga: la cuenta Proveedores queda en cero, el botón «Corregir» desaparece y
# los demás roles no entran. Lo que el cliente no ve (el token CSRF, el encabezado ``Origin`` y el JavaScript) es el paso de «navegador real» de la «Verificación a mano».

from django.core import mail
from django.urls import reverse

from compras.models import CorreccionRecepcion, ReclamoProveedor
from compras.servicios import pagos as servicio_de_pagos
from compras.tests.base_correcciones import CorreccionBase
from compras.tests.base_recepciones import DANADA, D
from contabilidad import cuentas
from contabilidad.models import AsientoContable
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import verificar_invariantes_contables
from inventario.tests.fabricas import verificar_invariantes
from maestros.models import Alerta


class RecorridoDeCorreccionYReclamosTests(CorreccionBase):
    """El recorrido completo: recibir con inconveniente → emitir y cerrar el reclamo → corregir → recibir de nuevo → pagar."""

    def proveedores_en_el_libro(self):
        return libro.saldo_por_cuenta(self.abierto.pk)[cuentas.PROVEEDORES].saldo

    def test_recorrido_de_punta_a_punta(self):
        ficha_orden = reverse("compras:orden_ficha", args=[self.orden.pk])
        corregir_url = reverse("compras:correccion_nueva", args=[self.orden.pk])

        # 1. Ana recibe 4 de 10 kg de Fertilizante con 2 dañados (nace el reclamo sin emitir y la alerta del Gerente) y, después, lo demás de A.
        primera = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "Cajas rotas")])])
        segunda = self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence), self.linea(self.l_maceta, 20)])
        reclamo = ReclamoProveedor.objects.get()
        self.assertEqual((reclamo.recepcion_id, reclamo.emitido, reclamo.estado_reclamo), (primera.pk, False, "abierto"))
        self.assertEqual(self.proveedores_en_el_libro(), D("300.00"))
        self.assertEqual([p.proveedor.pk for p in servicio_de_pagos.pagos_pendientes()], [self.proveedor.pk])

        # 2. El Gerente: ve el reclamo sin emitir en su Inicio y en «Reclamos», entra a su ficha y lo emite.
        self.client.force_login(self.gerente)
        inicio = self.client.get(reverse("core:inicio"))
        self.assertContains(inicio, 'data-kpi="reclamos-sin-emitir">1<')
        self.assertContains(inicio, str(reclamo))
        lista = self.client.get(reverse("compras:reclamos"))
        self.assertContains(lista, "Mercadería dañada")
        self.assertContains(lista, "Sin emitir")
        ficha_reclamo = reverse("compras:reclamo_ficha", args=[reclamo.pk])
        self.assertContains(self.client.get(ficha_reclamo), "Emitir reclamo")
        correos = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(reverse("compras:reclamo_emitir", args=[reclamo.pk])), ficha_reclamo, fetch_redirect_response=False)
        reclamo.refresh_from_db()
        self.assertEqual((reclamo.gerente_id, reclamo.fecha_reclamo), (self.gerente.pk, self.hoy))
        self.assertEqual(Alerta.objects.get().estado_alerta, "resuelta")
        self.assertEqual(len(mail.outbox), correos + 1)
        self.assertIn("Cajas rotas", mail.outbox[-1].body)
        self.assertContains(self.client.get(reverse("core:inicio")), 'data-kpi="reclamos-sin-emitir">0<')

        # 3. Ana (que solo ve su reclamo, sin botones) corrige lo que cargó de más: 2 kg de la segunda recepción. Formulario → resumen → confirmación.
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(ficha_reclamo), "Cerrar reclamo")
        self.assertContains(self.client.get(ficha_orden), "Corregir una recepción")
        self.assertContains(self.client.get(corregir_url + f"?recepcion={segunda.pk}"), "Se puede descontar")
        d_fert = self.detalle_de(segunda, self.l_fert)
        datos = {"recepcion": segunda.pk, "cant_%d" % d_fert.pk: "2", "observacion": "Se cargó de más"}
        self.assertContains(self.client.post(corregir_url, {**datos, "accion": "revisar"}), "Confirmá la corrección")
        self.assertEqual(CorreccionRecepcion.objects.count(), 0)
        correos = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(corregir_url, {**datos, "accion": "confirmar"}), ficha_orden, fetch_redirect_response=False)
        correccion = CorreccionRecepcion.objects.get()
        self.assertEqual((self.recibido(self.l_fert), self.estado_de(self.l_fert), self.estado_de_la_orden()), (D("8"), "pendiente", "parcialmente_recibida"))
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("8"), D("2")))
        self.assertEqual(self.proveedores_en_el_libro(), D("280.00"))
        self.assertEqual(self.movimientos_de(self.asiento_de_la_correccion(correccion)), [(cuentas.PROVEEDORES, "D", D("20.00")), (cuentas.INSUMOS_EN_STOCK, "H", D("20.00"))])
        self.assertEqual(len(mail.outbox), correos + 1)
        self.assertEqual(mail.outbox[-1].to, ["ventas@sur.com"])
        ficha = self.client.get(ficha_orden)
        self.assertContains(ficha, f"Registramos la corrección {correccion}")
        self.assertContains(ficha, "se corrigieron")
        self.assertEqual(ReclamoProveedor.objects.get().estado_reclamo, "abierto")  # la corrección no toca el reclamo (R3)

        # 4. El proveedor salió de la bandeja de pagos: el Contador no lo ve para pagar.
        self.assertEqual(servicio_de_pagos.pagos_pendientes(), [])
        self.client.force_login(self.contador)
        self.assertNotContains(self.client.get(reverse("compras:pagos")), self.proveedor.nombre_para_mostrar + "</td>")

        # 5. Ana vuelve a recibir los 2 kg que faltan: A vuelve a estar para pagar por $300,00 y el Contador paga.
        self.registrar(self.ana, [self.linea(self.l_fert, 2, self.vence)])
        self.assertEqual([(p.proveedor.pk, p.monto) for p in servicio_de_pagos.pagos_pendientes()], [(self.proveedor.pk, D("300.00"))])
        self.pagar()
        self.assertEqual(self.proveedores_en_el_libro(), D("0.00"))

        # 6. Con el pago hecho ya no se corrige: sin botón, y la pantalla lo explica.
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(ficha_orden), "Corregir una recepción")
        self.assertContains(self.client.get(corregir_url), "No hay recepciones para corregir")

        # 7. El Gerente cierra el reclamo (ya tratado con el proveedor) y no vuelve a poder emitirlo ni cerrarlo.
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(ficha_reclamo), "Cerrar reclamo")
        self.assertRedirects(self.client.post(reverse("compras:reclamo_cerrar", args=[reclamo.pk])), ficha_reclamo, fetch_redirect_response=False)
        self.assertEqual(ReclamoProveedor.objects.get().estado_reclamo, "cerrado")
        ficha = self.client.get(ficha_reclamo)
        self.assertNotContains(ficha, "Cerrar reclamo")
        self.assertNotContains(ficha, "Emitir reclamo")
        self.assertContains(self.client.get(reverse("compras:reclamos") + "?estado=cerrado"), str(reclamo))

        # 8. Los asientos cuadran y el kárdex también; los demás roles no entran.
        self.assertEqual(AsientoContable.objects.count(), 5)  # tres recepciones, la corrección y el pago
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()
        self.client.force_login(self.beto)
        self.assertEqual(self.client.get(corregir_url).status_code, 403)
        self.assertEqual(self.client.get(ficha_reclamo).status_code, 403)
