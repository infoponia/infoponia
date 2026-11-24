# Recorrido de punta a punta de CMP-03 (orden de compra y pasos diarios): los pasos de la «Verificación a mano» de la tarea, hechos por una prueba con el cliente de Django, en el orden en que los
# haría una persona (docs/patrones/verificacion_a_mano.md, D-96). Cada paso nombra el caso de uso y la regla que verifica. Es una sola prueba larga a propósito: lo que se verifica es que el flujo
# completo encadena bien. La Agrónoma ve sus pedidos vencidos, compara las cotizaciones, elige la de dos proveedores, revisa y genera la orden; el Gerente la ve en su inicio, revisa y la aprueba (el
# tránsito sube, cada proveedor recibe solo sus líneas, la orden impide deshabilitar el insumo y dar de baja al proveedor); otra orden se rechaza con su motivo; y el proceso diario avisa el
# vencimiento, recuerda la validez y cancela solo, sin repetir nada al correrlo dos veces. Arranca desde pedidos ya cotizados (el flujo de CMP-02a lo cubre ``test_recorrido_pedidos.py``). Las reglas
# sueltas las prueban ``test_cmp_gnr_odc.py``, ``test_cmp_apr_odc.py``, ``test_cmp_cns_odc.py``, ``test_pasos_diarios_compras.py`` y ``test_ordenes_vistas.py``. Los correos salen en ``on_commit``: se lo
# reemplaza por una llamada inmediata, como en producción.

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from compras.models import Cotizacion, DetalleOrdenCompra, OrdenCompra, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero
from inventario.servicios import insumos_invernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_invernadero


def en(dias):
    return timezone.localdate() + timedelta(days=dias)


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeOrdenesTests(ConDatosDeInventario, TestCase):
    """Fuente: docs/casos_de_uso/compras/ordenes_de_compra.md (CMP-GNR-ODC, CMP-APR-ODC, CMP-CNS-ODC y los pasos 60 a 62), D-87 puntos 4 y 5, D-89, D-90 (tránsito) y D-36."""

    def setUp(self):
        envio_inmediato = mock.patch.object(transaction, "on_commit", lambda funcion, **kwargs: funcion())
        envio_inmediato.start()
        self.addCleanup(envio_inmediato.stop)
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 10
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.ana = crear_agronomo(email="ana@infoponia.com")
        self.beto = crear_agronomo(email="beto@infoponia.com")
        self.gerente = crear_gerente()
        self.capataz = crear_capataz()
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.norte2 = crear_invernadero("Invernadero Norte 2", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.lechuga = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=0, precio="12.50")
        self.tomate = existencia(insumo("Tomate", unidad="unidad"), self.norte2, minimo=0, precio="10.00")
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.c = proveedor("Hortalizas del Oeste S. A.", n=3, email="hola@oeste.com")

    def pedido_vencido(self, *existencias, dias_vencido=1):
        """Un pedido de Ana de 20 de cada insumo que venció hace ``dias_vencido`` días. Devuelve ``(pedido, [detalles])``."""
        pedido = armar_pedido(self.ana)
        detalles = [detalle_de_pedido(pedido, e, cantidad="20") for e in existencias]
        Pedido.objects.filter(pk=pedido.pk).update(fecha_pedido=en(-7), fecha_limite_cotizaciones=en(-dias_vencido))
        pedido.refresh_from_db()
        return pedido, detalles

    def entrar(self, usuario):
        self.client.logout()
        self.client.force_login(usuario)

    def test_recorrido_de_generar_aprobar_rechazar_y_pasos_diarios(self):
        # ---- Preparación: dos pedidos de Ana ya cotizados (P1 para aprobar, P2 para rechazar) y uno que nadie cotizó (P3) ----
        p1, (lechuga1, tomate1) = self.pedido_vencido(self.lechuga, self.tomate)
        cot_a = cotizacion_de(p1, self.a, [(lechuga1, 20, "240.00", 3), (tomate1, 10, "90.00", 4)])
        cot_b = cotizacion_de(p1, self.b, [(tomate1, 10, "100.00", 5)])
        cot_c = cotizacion_de(p1, self.c, [(lechuga1, 10, "130.00", 2)])
        p2, (lechuga2,) = self.pedido_vencido(self.lechuga)
        cot_a2 = cotizacion_de(p2, self.a, [(lechuga2, 20, "200.00", 2)])
        p3, _ = self.pedido_vencido(self.tomate)

        # ---- 1. CMP-GNR-ODC, paso 2 y D-87 punto 5: el inicio de Ana lista los pedidos que vencieron y los resuelve ----
        self.entrar(self.ana)
        inicio = self.client.get(reverse("core:inicio"))
        self.assertContains(inicio, "Pedidos que vencieron")
        self.assertContains(inicio, 'data-kpi="por-resolver">2<')
        self.assertContains(inicio, reverse("compras:pedido_generar_orden", args=[p1.pk]))

        # ---- 2. Ficha del pedido: el botón es de Ana, no del Gerente ni de Beto (D-30) ----
        ficha_p1 = reverse("compras:pedido_ficha", args=[p1.pk])
        self.assertContains(self.client.get(ficha_p1), "Comparar cotizaciones y generar orden")
        for otro in (self.gerente,):
            self.entrar(otro)
            self.assertNotContains(self.client.get(ficha_p1), "Comparar cotizaciones y generar orden")
        self.entrar(self.beto)
        self.assertEqual(self.client.get(ficha_p1).status_code, 403)
        self.assertEqual(self.client.get(reverse("compras:pedido_generar_orden", args=[p1.pk])).status_code, 403)

        # ---- 3. CMP-GNR-ODC pasos 4 a 9: compara, elige cotizaciones completas y ve la cobertura crecer; nada viene preseleccionado ----
        self.entrar(self.ana)
        generar = reverse("compras:pedido_generar_orden", args=[p1.pk])
        pantalla = self.client.get(generar)
        self.assertNotContains(pantalla, 'name="cotizacion"')
        self.assertContains(pantalla, "el más bajo")
        despues_de_a = self.client.post(generar, {"accion": f"elegir:{cot_a.pk}"})
        self.assertContains(despues_de_a, "Falta 8")  # a los tomates les faltan 8 para el mínimo de 18
        sin_cubrir = self.client.post(generar, {"cotizacion": [cot_a.pk], "accion": "revisar"})
        self.assertEqual(sin_cubrir.templates[0].name, "compras/ordenes/generar.html")  # ext. 8a: no se avanza
        self.assertEqual(OrdenCompra.objects.count(), 0)
        resumen = self.client.post(generar, {"cotizacion": [cot_a.pk, cot_b.pk], "accion": "revisar", "observaciones": "Entregar a la mañana."})
        for esperado in ("430,00", "450,00", "Hortalizas del Oeste S. A.", "Entregar a la mañana."):
            self.assertContains(resumen, esperado)
        self.assertEqual(OrdenCompra.objects.count(), 0)

        # ---- 4. Paso 11 a 13: confirma; la orden queda pendiente, el Gerente recibe la notificación y solo el proveedor descartado un correo ----
        confirmada = self.client.post(generar, {"cotizacion": [cot_a.pk, cot_b.pk], "accion": "confirmar", "observaciones": "Entregar a la mañana."}, follow=True)
        orden = OrdenCompra.objects.get()
        self.assertRedirects(confirmada, reverse("compras:orden_ficha", args=[orden.pk]))
        self.assertContains(confirmada, "pendiente de aprobación")
        self.assertEqual(Pedido.objects.get(pk=p1.pk).estado_pedido, "cerrado")
        self.assertEqual({c.pk: Cotizacion.objects.get(pk=c.pk).estado_cotizacion for c in (cot_a, cot_b, cot_c)}, {cot_a.pk: "seleccionada", cot_b.pk: "seleccionada", cot_c.pk: "descartada"})
        self.assertEqual(Notificacion.objects.filter(destinatario=self.gerente, titulo__contains=str(orden)).count(), 1)
        self.assertEqual([m.to[0] for m in mail.outbox], ["hola@oeste.com"])
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.lechuga.pk).cant_transito_insumo, Decimal("0"))  # el tránsito sube al aprobar
        self.assertContains(self.client.get(ficha_p1), "se generó la orden de compra")  # D-30: el enlace está porque Ana puede abrirla

        # ---- 5. La Agrónoma ya no puede generar de nuevo (11a) y el pedido no admite otra orden ----
        otra_vez = self.client.get(generar, follow=True)
        self.assertRedirects(otra_vez, ficha_p1)
        self.assertContains(otra_vez, "ya no está en cotización")

        # ---- 6. CMP-CNS-ODC y CMP-APR-ODC paso 1 y 2: el Gerente la ve en su inicio y en «Por aprobar»; Ana no ve «Revisar» ----
        mail.outbox.clear()
        resolver = reverse("compras:orden_resolver", args=[orden.pk])
        self.entrar(self.gerente)
        self.assertContains(self.client.get(reverse("core:inicio")), 'data-kpi="por-aprobar">1<')
        self.assertContains(self.client.get(reverse("compras:ordenes"), {"atajo": "por_aprobar"}), resolver)
        self.entrar(self.ana)
        self.assertNotContains(self.client.get(reverse("compras:ordenes")), resolver)
        self.assertEqual(self.client.get(resolver).status_code, 403)
        self.entrar(self.beto)
        self.assertNotContains(self.client.get(reverse("compras:ordenes")), str(orden))  # alcance (regla 1): sin destinos a su cargo
        self.assertEqual(self.client.get(reverse("compras:orden_ficha", args=[orden.pk])).status_code, 403)
        self.entrar(self.capataz)
        self.assertEqual(self.client.get(reverse("compras:ordenes")).status_code, 403)

        # ---- 7. Pasos 4 a 10: el Gerente revisa, ve el resumen de la aprobación y la confirma ----
        self.entrar(self.gerente)
        detalle = self.client.get(resolver)
        for esperado in ("Semillas del Sur S. A.", "Viveros del Este S. R. L.", "Aprobar orden", "Rechazar orden"):
            self.assertContains(detalle, esperado)
        resumen_aprobacion = self.client.post(resolver, {"accion": "revisar_aprobacion"})
        self.assertContains(resumen_aprobacion, "no registra ningún pago")
        self.assertEqual(OrdenCompra.objects.get(pk=orden.pk).estado_orden_compra, "pendiente_aprobacion")
        aprobada = self.client.post(resolver, {"accion": "confirmar_aprobacion"}, follow=True)
        self.assertRedirects(aprobada, reverse("compras:orden_ficha", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual((orden.estado_orden_compra, orden.fecha_resolucion, orden.gerente_id), ("aprobada", en(0), self.gerente.pk))

        # ---- 8. Postcondiciones e a h: fechas de entrega, tránsito por existencia, avisos y un correo por proveedor con solo sus líneas ----
        entregas = {d.detalle_cotizacion.cotizacion.proveedor.pk: d.fecha_entrega_esperada for d in DetalleOrdenCompra.objects.filter(orden=orden, detalle_cotizacion__detalle_pedido=tomate1)}
        self.assertEqual(entregas, {self.a.pk: en(4), self.b.pk: en(5)})
        self.assertEqual((InsumoInvernadero.objects.get(pk=self.lechuga.pk).cant_transito_insumo, InsumoInvernadero.objects.get(pk=self.tomate.pk).cant_transito_insumo), (Decimal("20"), Decimal("20")))
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        cuerpo_a = next(m.body for m in mail.outbox if m.to[0] == "ventas@sur.com")
        self.assertIn("Lechuga", cuerpo_a)
        self.assertNotIn("Viveros del Este", cuerpo_a)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.ana, titulo__contains="aprobada").count(), 1)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente, titulo__contains="aprobada").exists())  # nunca se notifica a quien actuó (H21)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="aprobacion_orden_compra").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_insumo_invernadero").count(), 2)

        # ---- 9. H20 y H22: la orden aprobada sin recibir impide deshabilitar el insumo y dar de baja al proveedor ----
        self.entrar(self.ana)
        with self.assertRaises(ValidationError) as impedimento:
            insumos_invernadero.deshabilitar_insumo(self.ana, self.lechuga.pk)
        self.assertIn("orden_de_compra_aprobada", [e.code for lista in impedimento.exception.error_dict.values() for e in lista])
        self.entrar(self.gerente)
        baja = self.client.post(reverse("compras:proveedor_baja", args=[self.a.pk]), follow=True)
        self.assertContains(baja, "No se puede dar de baja")
        self.assertContains(self.client.get(reverse("compras:proveedor_ficha", args=[self.a.pk])), "Órdenes de compra")

        # ---- 10. Rechazo: el Agrónomo genera la orden de P2, el Gerente exige el motivo y la rechaza ----
        self.entrar(self.ana)
        self.client.post(reverse("compras:pedido_generar_orden", args=[p2.pk]), {"cotizacion": [cot_a2.pk], "accion": "confirmar"})
        orden2 = OrdenCompra.objects.get(pedido=p2)
        self.entrar(self.gerente)
        resolver2 = reverse("compras:orden_resolver", args=[orden2.pk])
        sin_motivo = self.client.post(resolver2, {"accion": "revisar_rechazo", "motivo": ""})
        self.assertContains(sin_motivo, "Contá por qué se rechaza la orden.")
        resumen_rechazo = self.client.post(resolver2, {"accion": "revisar_rechazo", "motivo": "No hay presupuesto este mes."})
        self.assertContains(resumen_rechazo, "no fue seleccionada")
        mail.outbox.clear()
        self.client.post(resolver2, {"accion": "confirmar_rechazo", "motivo": "No hay presupuesto este mes."})
        orden2.refresh_from_db()
        self.assertEqual((orden2.estado_orden_compra, orden2.motivo_rechazo), ("rechazada", "No hay presupuesto este mes."))
        self.assertEqual([m.to[0] for m in mail.outbox], ["ventas@sur.com"])  # el motivo no va en el correo
        self.assertNotIn("No hay presupuesto", mail.outbox[0].body)
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.lechuga.pk).cant_transito_insumo, Decimal("20"))  # el rechazo no toca el tránsito
        self.assertEqual(self.client.post(resolver2, {"accion": "confirmar_aprobacion"}, follow=True).redirect_chain[-1][0], reverse("compras:orden_ficha", args=[orden2.pk]))
        self.entrar(self.ana)
        self.assertContains(self.client.get(reverse("core:inicio")), "Órdenes rechazadas")  # Ana la ve para armar el pedido nuevo

        # ---- 11. Pasos diarios 60 a 62 con una fecha simulada: P3 (nadie cotizó) se cancela; P4 vence su cotización mañana ----
        p4, (lechuga4,) = self.pedido_vencido(self.lechuga)
        cotizacion_de(p4, self.b, [(lechuga4, 20, "250.00", 2)], validez_en_dias=1)
        salida = StringIO()
        call_command("proceso_diario", "--solo", "pedidos_vencidos", stdout=salida)
        self.assertIn("Pedidos vencidos: procesados 2 · creados 1 · resueltos 1", salida.getvalue())  # P3 cancelado, P4 avisado
        self.assertEqual(Pedido.objects.get(pk=p3.pk).causa_cancelacion, "nadie_cotizo")
        self.assertTrue(Pedido.objects.get(pk=p4.pk).aviso_vencimiento_dado)
        call_command("proceso_diario", "--solo", "recordatorio_de_validez", stdout=StringIO())
        self.assertEqual(Pedido.objects.get(pk=p4.pk).recordatorio_validez_para, en(1))
        avisos = Notificacion.objects.count()
        for codigo in ("pedidos_vencidos", "recordatorio_de_validez", "pedidos_sin_cotizacion_elegible"):
            call_command("proceso_diario", "--solo", codigo, stdout=StringIO())
        self.assertEqual(Notificacion.objects.count(), avisos)  # correr de nuevo el mismo día no repite nada
        call_command("proceso_diario", "--fecha", en(3).isoformat(), "--solo", "pedidos_sin_cotizacion_elegible", stdout=StringIO())
        self.assertEqual(Pedido.objects.get(pk=p4.pk).causa_cancelacion, "sin_cotizaciones_elegibles")  # con la fecha simulada, su cotización ya no sirve
