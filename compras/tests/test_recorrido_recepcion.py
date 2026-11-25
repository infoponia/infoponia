# Recorrido de punta a punta de CMP-04 (recepción de mercadería y cierre con faltante): los pasos de la «Verificación a mano» de la tarea, hechos por una prueba con el cliente de Django en el
# orden en que los haría una persona (docs/patrones/verificacion_a_mano.md, D-96). Es una sola prueba larga a propósito: lo que se verifica es que el flujo completo encadena bien. Orden aprobada
# de dos líneas → el Agrónomo recibe parte con un inconveniente (lote, stock que pasa de tránsito a existencia, asiento, reclamo sin emitir, alerta al Gerente) → recibe el resto de la línea (la
# suma de los asientos es exacta) → cierra con faltante la otra línea (baja el tránsito, sin asiento) → una sobreentrega se rechaza → el Contador ve el asiento en el libro de gestión con el enlace
# a la ficha de la orden. Las reglas sueltas las prueban ``test_cmp_reg_rcp.py``, ``test_cmp_crr_flt.py`` y ``test_recepciones_vistas.py``. Los correos salen en ``on_commit``: se reemplaza por una
# llamada inmediata, como en producción.

from unittest import mock

from django.core import mail
from django.db import transaction
from django.test import override_settings
from django.urls import reverse

from compras.models import DetalleOrdenCompra, Recepcion, ReclamoProveedor
from compras.tests.base_recepciones import BAJO_MINIMO, DANADA, TIPO_DE_ALERTA, D, RecepcionBase
from contabilidad import cuentas
from contabilidad.models import AsientoContable
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria
from core.tests.fabricas import crear_cuenta
from inventario.tests.fabricas import verificar_invariantes
from maestros.models import Alerta
from maestros.servicios import alertas as servicio_de_alertas


@override_settings(CORREO_CONFIGURADO=True)
class RecorridoDeRecepcionTests(RecepcionBase):
    """Fuente: docs/casos_de_uso/compras/recepcion.md (CMP-REG-RCP, CMP-CRR-FLT), docs/casos_de_uso/contabilidad/libro_de_gestion.md («Enlace al origen»), D-86, D-89, D-90 y D-36."""

    def setUp(self):
        envio_inmediato = mock.patch.object(transaction, "on_commit", lambda funcion, **kwargs: funcion())
        envio_inmediato.start()
        self.addCleanup(envio_inmediato.stop)
        super().setUp()
        self.recibir = reverse("compras:recepcion_nueva", args=[self.orden.pk])
        self.cerrar = reverse("compras:cierre_faltante", args=[self.orden.pk])
        self.ficha = reverse("compras:orden_ficha", args=[self.orden.pk])
        self.entrega = {"proveedor": self.proveedor.pk, "invernadero": self.norte.pk}

    def formulario(self, accion, fert=None, observaciones=""):
        """El formulario de A en Norte: ``fert = {"cant", "venc", "inc"}`` para el Fertilizante (la maceta no se recibe)."""
        datos = {**self.entrega, "accion": accion, "observaciones": observaciones}
        for linea in (self.l_fert, self.l_maceta):
            datos[f"lotes_{linea.pk}"], datos[f"incs_{linea.pk}"] = 1, 0
        if fert:
            i = self.l_fert.pk
            datos[f"cant_{i}_0"], datos[f"venc_{i}_0"] = fert["cant"], fert["venc"]
            if "inc" in fert:
                datos[f"incs_{i}"] = 1
                datos.update({f"inc_tipo_{i}_0": fert["inc"][0], f"inc_cant_{i}_0": fert["inc"][1], f"inc_desc_{i}_0": fert["inc"][2]})
        return datos

    def test_recorrido_de_la_recepcion_parcial_el_resto_el_cierre_la_sobreentrega_y_el_libro(self):
        # --- 1. Ana ve su mercadería por recibir (paso 2) y la ficha de la orden (regla 8) ---
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("compras:por_recibir")), "Semillas del Sur S. A.")
        self.assertContains(self.client.get(reverse("core:inicio")), 'data-kpi="por-recibir"')
        self.assertContains(self.client.get(self.ficha), "Registrar recepción")
        self.assertEqual(self.transito(self.fertilizante), D("10"))

        # --- 2. Recepción parcial con un inconveniente: 4 kg de 10, 2 dañados (pasos 5 a 9, 5a, 7f) ---
        resumen = self.client.post(self.recibir, self.formulario("revisar", {"cant": "4", "venc": self.vence.isoformat(), "inc": (DANADA, "2", "Dos bolsas rotas")}))
        self.assertContains(resumen, "Confirmá la recepción")
        self.assertContains(resumen, "reclamo sin emitir")
        self.assertEqual(Recepcion.objects.count(), 0)  # el resumen no escribe
        mail.outbox.clear()
        respuesta = self.client.post(self.recibir, self.formulario("confirmar", {"cant": "4", "venc": self.vence.isoformat(), "inc": (DANADA, "2", "Dos bolsas rotas")}, "Llegó por la tarde."))
        self.assertRedirects(respuesta, self.ficha, fetch_redirect_response=False)
        primera = Recepcion.objects.get()
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("4"), D("6")))  # el stock pasó de tránsito a existencia
        self.assertEqual(self.lotes_nuevos(self.fertilizante)[0].fecha_vencimiento, self.vence)
        asiento_1 = self.asiento_de(primera)
        self.assertEqual(self.movimientos_de(asiento_1), [(cuentas.INSUMOS_EN_STOCK, "D", D("40.00")), (cuentas.PROVEEDORES, "H", D("40.00"))])
        reclamo = ReclamoProveedor.objects.get()
        self.assertEqual((reclamo.gerente, reclamo.fecha_reclamo, reclamo.estado_reclamo), (None, None, "abierto"))
        self.assertEqual([m.to for m in mail.outbox], [[self.proveedor.email_proveedor]])
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")
        ficha = self.client.get(self.ficha)
        self.assertContains(ficha, "Quedó pendiente")  # extensión 11a
        self.assertContains(ficha, f"Reclamo {reclamo} sin emitir")

        # --- 3. El Gerente ve la alerta, que lo lleva a la ficha, y el reclamo sin emitir en la lista ---
        self.client.force_login(self.gerente)
        alerta = Alerta.objects.get(tipo_alerta=TIPO_DE_ALERTA)
        self.assertTrue(alerta.para_gerente and alerta.estado_alerta == "activa" and alerta.estado_lectura_alerta == "no_leida")
        enlaces = servicio_de_alertas.enlaces_de_alertas(self.gerente, Alerta.objects.select_related("invernadero").filter(pk=alerta.pk))
        self.assertEqual(enlaces[alerta.pk].url, self.ficha)
        self.assertEqual(self.client.get(reverse("alertas:detalle", args=[alerta.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("compras:ordenes") + "?atajo=con_reclamo_sin_emitir"), str(self.orden))

        # --- 4. Ana recibe el resto de la línea: el asiento cierra exacto (D-89 punto 4) ---
        self.client.force_login(self.ana)
        self.client.post(self.recibir, self.formulario("confirmar", {"cant": "6", "venc": self.vence.isoformat()}))
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante), self.estado_de(self.l_fert)), (D("10"), D("0"), "completo"))
        asientos = list(AsientoContable.objects.order_by("numero_asiento"))
        importes = [self.movimientos_de(a)[0][2] for a in asientos]
        self.assertEqual((importes, sum(importes)), ([D("40.00"), D("60.00")], self.l_fert.total_linea))

        # --- 5. Cierre con faltante de las macetas (nada llegó): baja el tránsito y no hay asiento (D-90 punto 8) ---
        asientos_antes = AsientoContable.objects.count()
        resumen = self.client.post(self.cerrar, {"accion": "revisar", "linea": [self.l_maceta.pk], f"motivo_{self.l_maceta.pk}": "No las fabrican más."})
        self.assertContains(resumen, "no se deshace")
        self.client.post(self.cerrar, {"accion": "confirmar", "linea": [self.l_maceta.pk], f"motivo_{self.l_maceta.pk}": "No las fabrican más."})
        self.assertEqual((self.estado_de(self.l_maceta), self.transito(self.maceta)), ("cerrado_con_faltante", D("0")))
        self.assertEqual(AsientoContable.objects.count(), asientos_antes)
        self.assertContains(self.client.get(self.ficha), "No las fabrican más.")

        # --- 6. La sobreentrega se rechaza (P3): la línea de fertilizante ya está completa; la de tomates, con 8 pedidos, no admite 9 ---
        respuesta = self.client.post(self.recibir, self.formulario("confirmar", {"cant": "1", "venc": self.vence.isoformat()}))
        self.assertEqual((respuesta.status_code, Recepcion.objects.count()), (302, 2))  # sin líneas pendientes en esa entrega se vuelve a la ficha
        tomate = {**{"proveedor": self.proveedor_b.pk, "invernadero": self.norte2.pk}, "accion": "confirmar", f"lotes_{self.l_tomate.pk}": 1, f"incs_{self.l_tomate.pk}": 0, f"cant_{self.l_tomate.pk}_0": "9", f"venc_{self.l_tomate.pk}_0": ""}
        respuesta = self.client.post(self.recibir, tomate)
        self.assertContains(respuesta, "faltan recibir")
        self.assertEqual(Recepcion.objects.count(), 2)
        self.assertEqual(self.transito(self.tomate), D("8"))

        # --- 7. Se recibe lo de B y la orden queda «recibida con faltante» ---
        tomate[f"cant_{self.l_tomate.pk}_0"] = "8"
        self.client.post(self.recibir, tomate)
        self.assertEqual(self.estado_de_la_orden(), "recibida_con_faltante")

        # --- 8. El Contador ve el asiento en el libro de gestión con el enlace a la ficha de la orden ---
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.client.force_login(contador)
        self.assertEqual(self.client.get(reverse("contabilidad:libro")).status_code, 200)
        pagina = self.client.get(reverse("contabilidad:asiento", args=[asiento_1.ejercicio_id, asiento_1.numero_asiento]))
        self.assertContains(pagina, f"{primera} · {self.orden}")
        self.assertContains(pagina, self.ficha)
        saldos = libro.saldo_por_cuenta(asiento_1.ejercicio_id)
        self.assertEqual((saldos[cuentas.INSUMOS_EN_STOCK].saldo, saldos[cuentas.PROVEEDORES].saldo), (D("180.00"), D("180.00")))  # 100 de fertilizante + 80 de tomates

        # --- 9. La auditoría y los invariantes ---
        acciones = list(RegistroAuditoria.objects.filter(accion__in=["recepcion_mercaderia", "cierre_con_faltante"]).values_list("accion", flat=True))
        self.assertEqual(sorted(acciones), ["cierre_con_faltante", "recepcion_mercaderia", "recepcion_mercaderia", "recepcion_mercaderia"])
        self.assertFalse(DetalleOrdenCompra.objects.filter(orden=self.orden, estado_detalle_orden="pendiente").exists())
        for iin in (self.fertilizante, self.maceta, self.tomate):
            verificar_invariantes(iin)
        verificar_invariantes_contables()
        self.assertFalse(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).exists())
