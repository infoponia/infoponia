# Pruebas de las pantallas de «Compras» → «Órdenes» (CMP-03, paso 6): la lista y la ficha de la orden (CMP-CNS-ODC), «Comparar cotizaciones y generar orden» del Agrónomo
# (CMP-GNR-ODC), «Revisar y decidir» del Gerente (CMP-APR-ODC), las secciones del inicio, el botón y el aviso de la ficha del pedido, la tarjeta de órdenes de la ficha del proveedor
# y lo que sumó CMP-03 en otras partes (la advertencia 4c, la URL del impedimento de la orden y el contador de pendientes del Gerente). Fuente:
# docs/casos_de_uso/compras/ordenes_de_compra.md; prototipo ``tabOdc``, ``c_odc``, ``c_gen``, ``c_apr``, ``panelAgr`` y ``panelGer``. Las vistas solo orquestan: las reglas ya las
# prueban ``test_cmp_gnr_odc.py``, ``test_cmp_apr_odc.py`` y ``test_cmp_cns_odc.py``.
#
# Contrato de «Generar» (``compras:pedido_generar_orden``; un solo formulario que se vuelve a dibujar con cada acción, sin JavaScript): ``cotizacion`` (lista de ids elegidos),
# ``observaciones`` y ``accion``: ``elegir:<id>``, ``quitar:<id>``, ``revisar`` (paso 9), ``editar`` (10a) y ``confirmar`` (paso 11).
# Contrato de «Resolver» (``compras:orden_resolver``): ``accion`` = ``revisar_aprobacion``, ``confirmar_aprobacion``, ``revisar_rechazo`` (con ``motivo``), ``confirmar_rechazo`` o ``editar``.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from compras.models import Cotizacion, OrdenCompra, Pedido
from compras.servicios import ordenes as servicio_de_ordenes
from compras.servicios import pedidos as servicio_de_pedidos
from compras.servicios import proveedores as servicio_de_proveedores
from compras.servicios import registrantes
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, orden_de, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core import extensiones
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo_con_invernadero, crear_invernadero, crear_vendedor


@override_settings(CORREO_CONFIGURADO=True)
class OrdenesVistasBase(ConDatosDeInventario, TestCase):
    """Ana (Norte y Norte 2), Beto (Sur), un Gerente y un pedido de Ana que venció ayer: 20 lechugas en Norte y 20 tomates en Norte 2, tolerancia 10 %. Cotizan A (20 lechugas
    $240 y 10 tomates $90), B (10 tomates $100) y C (10 lechugas $130); con A y B se cubre. ``orden`` no existe todavía: ``generada()`` la arma."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.norte2 = crear_invernadero("Norte 2", agronomo=self.ana)
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 10
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.lechuga_iin = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=0, precio="12.50")
        self.tomate_iin = existencia(insumo("Tomate", unidad="unidad"), self.norte2, minimo=0, precio="10.00")
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.c = proveedor("Hortalizas del Oeste S. A.", n=3, email="hola@oeste.com")
        self.pedido = armar_pedido(self.ana)
        self.lechuga = detalle_de_pedido(self.pedido, self.lechuga_iin, cantidad="20")
        self.tomate = detalle_de_pedido(self.pedido, self.tomate_iin, cantidad="20")
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=self.hoy - timedelta(days=5), fecha_limite_cotizaciones=self.hoy - timedelta(days=1))
        self.pedido.refresh_from_db()
        self.cot_a = cotizacion_de(self.pedido, self.a, [(self.lechuga, 20, "240.00", 3), (self.tomate, 10, "90.00", 4)])
        self.cot_b = cotizacion_de(self.pedido, self.b, [(self.tomate, 10, "100.00", 5)])
        self.cot_c = cotizacion_de(self.pedido, self.c, [(self.lechuga, 10, "130.00", 2)])
        self.generar_url = reverse("compras:pedido_generar_orden", args=[self.pedido.pk])
        self.lista_url = reverse("compras:ordenes")

    def generada(self, estado="pendiente_aprobacion", **extra):
        """La orden del pedido con las cotizaciones de A y B (la C queda descartada)."""
        orden = orden_de(self.pedido, [self.cot_a, self.cot_b], estado=estado, gerente=self.gerente, motivo="No hay presupuesto." if estado == "rechazada" else "", **extra)
        Cotizacion.objects.filter(pk=self.cot_c.pk).update(estado_cotizacion="descartada")
        return orden

    def ficha_url(self, orden):
        return reverse("compras:orden_ficha", args=[orden.pk])

    def resolver_url(self, orden):
        return reverse("compras:orden_resolver", args=[orden.pk])

    def generar(self, usuario=None, **datos):
        self.client.force_login(usuario or self.ana)
        return self.client.post(self.generar_url, datos, follow=True)

    def resolver(self, orden, usuario=None, **datos):
        self.client.force_login(usuario or self.gerente)
        return self.client.post(self.resolver_url(orden), datos, follow=True)


class ListaDeOrdenesVistaTests(OrdenesVistasBase):
    """«Compras» → «Órdenes» (CMP-CNS-ODC regla 3, ``tabOdc``)."""

    def test_el_agronomo_y_el_gerente_la_ven_y_los_demas_roles_no(self):
        for usuario in (self.ana, self.gerente):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.lista_url).status_code, 200)
        for usuario in (crear_capataz(), crear_vendedor()):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.lista_url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.lista_url).status_code, 302)

    def test_la_lista_muestra_la_orden_con_su_pedido_sus_proveedores_el_monto_y_el_estado(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.lista_url)
        for esperado in (str(orden), str(self.pedido), "Semillas del Sur S. A.", "Viveros del Este S. R. L.", "Pendiente de aprobación"):
            self.assertContains(respuesta, esperado)
        self.assertContains(respuesta, 'href="%s"' % self.ficha_url(orden))

    def test_regla_8_el_gerente_ve_revisar_en_las_pendientes_y_el_agronomo_no(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.lista_url), self.resolver_url(orden))
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(self.lista_url), self.resolver_url(orden))

    def test_regla_1_el_agronomo_solo_ve_las_ordenes_de_sus_destinos(self):
        orden = self.generada()
        self.client.force_login(self.beto)
        self.assertNotContains(self.client.get(self.lista_url), str(orden))
        self.assertContains(self.client.get(self.lista_url), "No hay órdenes")

    def test_regla_2_el_atajo_por_aprobar_y_los_filtros_se_aplican(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.lista_url, {"atajo": "por_aprobar"}), str(orden))
        self.assertNotContains(self.client.get(self.lista_url, {"estado": "rechazada"}), str(orden))
        self.assertContains(self.client.get(self.lista_url, {"proveedor": self.a.pk}), str(orden))
        self.assertNotContains(self.client.get(self.lista_url, {"proveedor": self.c.pk}), str(orden))

    def test_el_atajo_por_aprobar_cuenta_las_pendientes(self):
        self.generada()
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.lista_url), "Por aprobar <b>1</b>")

    def test_la_pestana_ordenes_esta_en_las_pantallas_de_compras(self):
        self.client.force_login(self.ana)
        for url in (self.lista_url, reverse("compras:pedidos"), reverse("compras:proveedores")):
            self.assertContains(self.client.get(url), self.lista_url)

    def test_la_marca_de_lineas_atrasadas_se_muestra(self):
        orden = self.generada(estado="aprobada")
        orden.detalles.update(fecha_entrega_esperada=self.hoy - timedelta(days=2))
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.lista_url), "3 líneas atrasadas")


class FichaDeOrdenVistaTests(OrdenesVistasBase):
    """Ficha de la orden (CMP-CNS-ODC reglas 4, 5 y 8, ``VIEWS.c_odc``)."""

    def test_la_ficha_muestra_el_pedido_el_monto_y_las_lineas_por_proveedor_y_destino(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.ficha_url(orden))
        for esperado in (str(orden), str(self.pedido), "Semillas del Sur S. A.", "Viveros del Este S. R. L.", "Lechuga", "Tomate", "Norte 2", "430,00"):
            self.assertContains(respuesta, esperado)
        self.assertNotContains(respuesta, "Hortalizas del Oeste")  # su cotización se descartó al generar

    def test_el_gerente_ve_revisar_y_decidir_solo_si_esta_pendiente(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(self.ficha_url(orden)), self.resolver_url(orden))
        OrdenCompra.objects.filter(pk=orden.pk).update(estado_orden_compra="aprobada", gerente=self.gerente, fecha_resolucion=self.hoy)
        self.assertNotContains(self.client.get(self.ficha_url(orden)), self.resolver_url(orden))

    def test_el_agronomo_nunca_ve_revisar_y_decidir(self):
        orden = self.generada()
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.ficha_url(orden))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.resolver_url(orden))

    def test_una_orden_rechazada_muestra_el_motivo_y_quien_la_resolvio(self):
        orden = self.generada("rechazada")
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.ficha_url(orden))
        self.assertContains(respuesta, "No hay presupuesto.")
        self.assertContains(respuesta, "Gabriela Sosa")

    def test_una_orden_ajena_es_403_y_una_inexistente_404(self):
        orden = self.generada()
        self.client.force_login(self.beto)
        self.assertEqual(self.client.get(self.ficha_url(orden)).status_code, 403)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("compras:orden_ficha", args=[99999])).status_code, 404)

    def test_solo_aceptan_get(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.post(self.ficha_url(orden)).status_code, 405)
        self.assertEqual(self.client.post(self.lista_url).status_code, 405)


class GenerarOrdenVistaTests(OrdenesVistasBase):
    """«Comparar cotizaciones y generar orden» (CMP-GNR-ODC, ``VIEWS.c_gen``)."""

    def test_regla_presentacion_muestra_las_dos_vistas_y_no_preselecciona_nada(self):
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.generar_url)
        self.assertEqual(respuesta.status_code, 200)
        for esperado in ("Por insumo", "Por cotización", "Semillas del Sur S. A.", "Viveros del Este S. R. L.", "Hortalizas del Oeste S. A.", "el más bajo"):
            self.assertContains(respuesta, esperado)
        self.assertNotContains(respuesta, 'name="cotizacion"')
        self.assertEqual(respuesta.context["eleccion"].elegidas, [])

    def test_solo_el_agronomo_del_pedido_la_abre(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(self.generar_url).status_code, 403)
        self.client.force_login(self.beto)
        self.assertEqual(self.client.get(self.generar_url).status_code, 403)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(reverse("compras:pedido_generar_orden", args=[99999])).status_code, 404)

    def test_ext_1a1_un_pedido_que_ya_no_esta_en_cotizacion_vuelve_a_su_ficha_con_el_motivo(self):
        orden = self.generada()
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.generar_url, follow=True)
        self.assertRedirects(respuesta, reverse("compras:pedido_ficha", args=[self.pedido.pk]))
        self.assertContains(respuesta, "ya no está en cotización")
        self.assertContains(respuesta, self.ficha_url(orden))

    def test_precondicion_b_un_pedido_sin_vencer_vuelve_a_su_ficha(self):
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy)
        self.client.force_login(self.ana)
        self.assertRedirects(self.client.get(self.generar_url), reverse("compras:pedido_ficha", args=[self.pedido.pk]), fetch_redirect_response=False)

    def test_pasos_5_y_6_elegir_agrega_la_cotizacion_completa_y_actualiza_la_cobertura(self):
        respuesta = self.generar(accion=f"elegir:{self.cot_a.pk}")
        self.assertContains(respuesta, f'name="cotizacion" value="{self.cot_a.pk}"')
        eleccion = respuesta.context["eleccion"]
        self.assertEqual([c.cotizacion.pk for c in eleccion.elegidas], [self.cot_a.pk])
        self.assertEqual(eleccion.monto, Decimal("330.00"))
        self.assertFalse(eleccion.cubierto)  # a los tomates les faltan 8
        self.assertContains(respuesta, "Falta 8")

    def test_ext_6a_quitar_saca_la_cotizacion_y_conserva_las_demas(self):
        respuesta = self.generar(cotizacion=[self.cot_a.pk, self.cot_b.pk], accion=f"quitar:{self.cot_a.pk}")
        self.assertEqual([c.cotizacion.pk for c in respuesta.context["eleccion"].elegidas], [self.cot_b.pk])

    def test_paso_8_con_lo_elegido_cubierto_se_puede_revisar_y_sin_cubrir_no(self):
        sin_cubrir = self.generar(cotizacion=[self.cot_a.pk], accion="revisar")
        self.assertEqual(sin_cubrir.templates[0].name, "compras/ordenes/generar.html")
        self.assertContains(sin_cubrir, "no alcanzan la cantidad mínima")  # ext. 8a: dice que no alcanza
        self.assertContains(sin_cubrir, "disabled")  # el botón «Revisar la orden» no se ofrece habilitado
        self.assertEqual(OrdenCompra.objects.count(), 0)

    def test_paso_9_el_resumen_trae_el_total_la_diferencia_y_lo_que_se_descarta(self):
        respuesta = self.generar(cotizacion=[self.cot_a.pk, self.cot_b.pk], accion="revisar", observaciones="Entregar a la mañana.")
        self.assertEqual(respuesta.templates[0].name, "compras/ordenes/generar_resumen.html")
        for esperado in ("430,00", "450,00", "Hortalizas del Oeste S. A.", "Entregar a la mañana.", "pendiente de aprobación del Gerente"):
            self.assertContains(respuesta, esperado)
        self.assertEqual(OrdenCompra.objects.count(), 0)  # revisar no genera nada

    def test_ext_10a_volver_a_corregir_devuelve_la_eleccion_sin_generar_nada(self):
        respuesta = self.generar(cotizacion=[self.cot_a.pk, self.cot_b.pk], accion="editar", observaciones="Hola")
        self.assertEqual(respuesta.templates[0].name, "compras/ordenes/generar.html")
        self.assertEqual(len(respuesta.context["elegidas_ids"]), 2)
        self.assertContains(respuesta, "Hola")
        self.assertEqual(OrdenCompra.objects.count(), 0)

    def test_paso_11_confirmar_genera_la_orden_y_lleva_a_su_ficha(self):
        respuesta = self.generar(cotizacion=[self.cot_a.pk, self.cot_b.pk], accion="confirmar", observaciones="Entregar a la mañana.")
        orden = OrdenCompra.objects.get()
        self.assertRedirects(respuesta, self.ficha_url(orden))
        self.assertContains(respuesta, "Quedó pendiente de aprobación del Gerente")
        self.assertEqual((orden.estado_orden_compra, orden.observaciones), ("pendiente_aprobacion", "Entregar a la mañana."))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="generacion_orden_compra").count(), 1)

    def test_ext_12b_sin_gerente_activo_el_mensaje_final_lo_dice(self):
        self.gerente.is_active = False
        self.gerente.save(update_fields=["is_active"])
        respuesta = self.generar(cotizacion=[self.cot_a.pk, self.cot_b.pk], accion="confirmar")
        self.assertContains(respuesta, "No hay un Gerente activo")

    def test_ext_4b_y_4c_una_cotizacion_no_elegible_se_muestra_marcada_y_sin_boton(self):
        self.c.estado_proveedor = "inactivo"
        self.c.save(update_fields=["estado_proveedor"])
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.generar_url)
        self.assertContains(respuesta, "Proveedor inactivo")
        self.assertContains(respuesta, "Validez vencida")
        for cotizacion in (self.cot_b, self.cot_c):
            self.assertNotContains(respuesta, f'value="elegir:{cotizacion.pk}"')
        self.assertContains(respuesta, f'value="elegir:{self.cot_a.pk}"')

    def test_ext_4a_si_no_alcanza_ni_con_todo_lo_elegible_lo_dice_y_ofrece_cancelar_el_pedido(self):
        self.cot_a.estado_cotizacion = "descartada"
        Cotizacion.objects.filter(pk=self.cot_a.pk).update(estado_cotizacion="descartada")
        self.client.force_login(self.ana)
        respuesta = self.client.get(self.generar_url)
        self.assertContains(respuesta, "no podrá generar una orden")
        self.assertContains(respuesta, reverse("compras:pedido_cancelar", args=[self.pedido.pk]))
        self.assertContains(respuesta, "Ofertas insuficientes")

    def test_ext_11a_si_el_pedido_se_cancelo_mientras_tanto_vuelve_a_su_ficha(self):
        self.client.force_login(self.ana)
        self.client.get(self.generar_url)
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="cancelado", causa_cancelacion="manual", motivo_cancelacion="x", fecha_cierre_pedido=self.hoy)
        respuesta = self.client.post(self.generar_url, {"cotizacion": [self.cot_a.pk, self.cot_b.pk], "accion": "confirmar"}, follow=True)
        self.assertRedirects(respuesta, reverse("compras:pedido_ficha", args=[self.pedido.pk]))
        self.assertEqual(OrdenCompra.objects.count(), 0)

    def test_ext_11b_si_un_proveedor_se_dio_de_baja_se_vuelve_a_la_eleccion_sin_esa_cotizacion(self):
        self.client.force_login(self.ana)
        self.client.get(self.generar_url)
        self.b.estado_proveedor = "inactivo"
        self.b.save(update_fields=["estado_proveedor"])
        respuesta = self.client.post(self.generar_url, {"cotizacion": [self.cot_a.pk, self.cot_b.pk], "accion": "confirmar"}, follow=True)
        self.assertEqual(respuesta.templates[0].name, "compras/ordenes/generar.html")
        self.assertEqual([c.cotizacion.pk for c in respuesta.context["eleccion"].elegidas], [self.cot_a.pk])
        self.assertEqual(OrdenCompra.objects.count(), 0)

    def test_ext_6b_comprar_de_mas_solo_advierte(self):
        respuesta = self.generar(accion=f"elegir:{self.cot_c.pk}", cotizacion=[self.cot_a.pk, self.cot_b.pk])
        self.assertContains(respuesta, "Se compra más de lo pedido de Lechuga")
        self.assertTrue(respuesta.context["eleccion"].cubierto)

    def test_el_formulario_exige_el_token_csrf(self):
        from django.test import Client

        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.ana)
        self.assertEqual(cliente.post(self.generar_url, {"accion": "confirmar", "cotizacion": [self.cot_a.pk, self.cot_b.pk]}).status_code, 403)
        self.assertEqual(OrdenCompra.objects.count(), 0)


class ResolverOrdenVistaTests(OrdenesVistasBase):
    """«Revisar y decidir» (CMP-APR-ODC, ``VIEWS.c_apr``)."""

    def setUp(self):
        super().setUp()
        self.orden = self.generada()

    def test_solo_el_gerente_la_abre(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(self.resolver_url(self.orden)).status_code, 200)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(self.resolver_url(self.orden)).status_code, 403)

    def test_paso_4_muestra_lo_que_el_gerente_necesita_para_decidir(self):
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.resolver_url(self.orden))
        for esperado in (str(self.pedido), "Semillas del Sur S. A.", "Viveros del Este S. R. L.", "430,00", "450,00", "Aprobar orden", "Rechazar orden"):
            self.assertContains(respuesta, esperado)

    def test_pasos_5_y_6_aprobar_lleva_al_resumen_y_no_cambia_nada(self):
        respuesta = self.resolver(self.orden, accion="revisar_aprobacion")
        self.assertEqual(respuesta.templates[0].name, "compras/ordenes/resumen_aprobacion.html")
        self.assertContains(respuesta, "no registra ningún pago")
        self.assertContains(respuesta, "Cantidad en tránsito")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "pendiente_aprobacion")

    def test_pasos_7_a_10_confirmar_aprueba_sube_el_transito_y_lleva_a_la_ficha(self):
        respuesta = self.resolver(self.orden, accion="confirmar_aprobacion")
        self.assertRedirects(respuesta, self.ficha_url(self.orden))
        self.assertContains(respuesta, "aprobada")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "aprobada")
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.lechuga_iin.pk).cant_transito_insumo, Decimal("20"))

    def test_ext_5b_rechazar_sin_motivo_vuelve_a_pedirlo(self):
        respuesta = self.resolver(self.orden, accion="revisar_rechazo", motivo="   ")
        self.assertEqual(respuesta.templates[0].name, "compras/ordenes/resolver.html")
        self.assertContains(respuesta, "Contá por qué se rechaza la orden.")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "pendiente_aprobacion")

    def test_ext_5a_3_rechazar_con_motivo_muestra_el_resumen_y_confirmar_rechaza(self):
        resumen = self.resolver(self.orden, accion="revisar_rechazo", motivo="No hay presupuesto.")
        self.assertEqual(resumen.templates[0].name, "compras/ordenes/resumen_rechazo.html")
        for esperado in ("No hay presupuesto.", "no fue seleccionada", "ventas@sur.com", "info@este.com"):
            self.assertContains(resumen, esperado)
        confirmado = self.resolver(self.orden, accion="confirmar_rechazo", motivo="No hay presupuesto.")
        self.assertRedirects(confirmado, self.ficha_url(self.orden))
        orden = OrdenCompra.objects.get(pk=self.orden.pk)
        self.assertEqual((orden.estado_orden_compra, orden.motivo_rechazo), ("rechazada", "No hay presupuesto."))

    def test_ext_5a_4a_volver_a_corregir_conserva_el_motivo_sin_rechazar(self):
        respuesta = self.resolver(self.orden, accion="editar", motivo="Quiero cambiar esto")
        self.assertContains(respuesta, "Quiero cambiar esto")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "pendiente_aprobacion")

    def test_ext_4a_con_un_destino_inactivo_no_se_ofrece_aprobar_y_se_dice_por_que(self):
        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="inactivo")
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.resolver_url(self.orden))
        self.assertContains(respuesta, "No se puede aprobar esta orden")
        self.assertContains(respuesta, "el invernadero está inactivo")
        self.assertNotContains(respuesta, "Aprobar orden")
        self.assertContains(respuesta, "Rechazar orden")

    def test_p1_con_una_cotizacion_vencida_se_propone_el_motivo_del_rechazo_y_no_se_ofrece_aprobar(self):
        vencio = self.hoy - timedelta(days=1)
        Cotizacion.objects.filter(pk=self.cot_b.pk).update(fecha_validez_cotizacion=vencio)
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.resolver_url(self.orden))
        self.assertNotContains(respuesta, "Aprobar orden")
        self.assertContains(respuesta, f"La cotización de Viveros del Este S. R. L. venció el {vencio:%d/%m/%Y}.")
        self.assertContains(respuesta, "Lo propuso el Sistema")

    def test_ext_8b_si_al_confirmar_la_aprobacion_ya_no_se_puede_se_vuelve_al_paso_4(self):
        self.client.force_login(self.gerente)
        self.client.get(self.resolver_url(self.orden))
        Cotizacion.objects.filter(pk=self.cot_a.pk).update(fecha_validez_cotizacion=self.hoy - timedelta(days=1))
        respuesta = self.client.post(self.resolver_url(self.orden), {"accion": "confirmar_aprobacion"}, follow=True)
        self.assertRedirects(respuesta, self.resolver_url(self.orden))
        self.assertContains(respuesta, "No se puede aprobar")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "pendiente_aprobacion")

    def test_ext_1a1_y_8a_una_orden_ya_resuelta_informa_la_decision_y_vuelve_a_la_ficha(self):
        self.resolver(self.orden, accion="confirmar_aprobacion")
        for accion in ("revisar_aprobacion", "confirmar_aprobacion", "confirmar_rechazo"):
            with self.subTest(accion=accion):
                respuesta = self.resolver(self.orden, accion=accion, motivo="Otro")
                self.assertRedirects(respuesta, self.ficha_url(self.orden))
                self.assertContains(respuesta, "ya no está pendiente")
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "aprobada")
        self.client.force_login(self.gerente)
        self.assertRedirects(self.client.get(self.resolver_url(self.orden)), self.ficha_url(self.orden), fetch_redirect_response=False)

    def test_el_formulario_exige_el_token_csrf(self):
        from django.test import Client

        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.gerente)
        self.assertEqual(cliente.post(self.resolver_url(self.orden), {"accion": "confirmar_aprobacion"}).status_code, 403)
        self.assertEqual(OrdenCompra.objects.get(pk=self.orden.pk).estado_orden_compra, "pendiente_aprobacion")


class InicioYFichasVistaTests(OrdenesVistasBase):
    """Las secciones del inicio (D-87 punto 5), la ficha del pedido y la del proveedor."""

    def test_el_inicio_del_agronomo_lista_los_pedidos_que_vencieron_con_resolver(self):
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, "Pedidos que vencieron")
        self.assertContains(respuesta, 'data-kpi="por-resolver">1<')
        self.assertContains(respuesta, self.generar_url)

    def test_el_inicio_del_agronomo_sin_pedidos_vencidos_no_lista_nada_y_lo_dice(self):
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy + timedelta(days=2), fecha_pedido=self.hoy)
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertNotContains(respuesta, "Pedidos que vencieron")
        self.assertContains(respuesta, 'data-kpi="por-resolver">0<')

    def test_el_inicio_del_agronomo_lista_las_ordenes_rechazadas_de_los_ultimos_dias(self):
        orden = self.generada("rechazada")
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, "Órdenes rechazadas")
        self.assertContains(respuesta, str(orden))
        OrdenCompra.objects.filter(pk=orden.pk).update(fecha_resolucion=self.hoy - timedelta(days=8))
        self.assertNotContains(self.client.get(reverse("core:inicio")), "Órdenes rechazadas")

    def test_el_inicio_del_gerente_lista_las_ordenes_por_aprobar_con_revisar(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, "Órdenes pendientes de aprobación")
        self.assertContains(respuesta, 'data-kpi="por-aprobar">1<')
        self.assertContains(respuesta, self.resolver_url(orden))

    def test_el_inicio_del_gerente_sin_ordenes_pendientes_dice_que_no_hay(self):
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, 'data-kpi="por-aprobar">0<')
        self.assertNotContains(respuesta, "Órdenes pendientes de aprobación")

    def test_la_ficha_del_pedido_ofrece_generar_la_orden_solo_al_agronomo_del_pedido_ya_vencido_con_cotizaciones(self):
        ficha = reverse("compras:pedido_ficha", args=[self.pedido.pk])
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(ficha), "Comparar cotizaciones y generar orden")
        self.assertContains(self.client.get(ficha), self.generar_url)
        self.client.force_login(self.gerente)
        self.assertNotContains(self.client.get(ficha), self.generar_url)
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_limite_cotizaciones=self.hoy)  # el último día todavía se cotiza
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(ficha), self.generar_url)

    def test_la_ficha_del_pedido_sin_cotizaciones_no_ofrece_generar(self):
        Cotizacion.objects.filter(pedido=self.pedido).update(estado_cotizacion="descartada")
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(reverse("compras:pedido_ficha", args=[self.pedido.pk])), self.generar_url)

    def test_la_ficha_del_pedido_cerrado_enlaza_la_orden_que_se_genero(self):
        orden = self.generada()
        ficha = reverse("compras:pedido_ficha", args=[self.pedido.pk])
        for usuario in (self.ana, self.gerente):
            self.client.force_login(usuario)
            respuesta = self.client.get(ficha)
            self.assertContains(respuesta, "se generó la orden de compra")
            self.assertContains(respuesta, self.ficha_url(orden))
            self.assertNotContains(respuesta, self.generar_url)

    def test_d30_la_ficha_del_pedido_no_enlaza_una_orden_que_quien_mira_no_puede_abrir(self):
        orden = self.generada()
        Invernadero.objects.filter(pk__in=[self.norte.pk, self.norte2.pk]).update(agronomo=self.beto)  # Ana ya no tiene los destinos
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("compras:pedido_ficha", args=[self.pedido.pk]))
        self.assertNotContains(respuesta, self.ficha_url(orden))

    def test_la_ficha_del_proveedor_lista_sus_ordenes_con_el_monto_de_sus_lineas(self):
        orden = self.generada()
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("compras:proveedor_ficha", args=[self.a.pk]))
        self.assertContains(respuesta, "Órdenes de compra")
        self.assertContains(respuesta, self.ficha_url(orden))
        self.assertContains(respuesta, "330,00")
        sin_ordenes = self.client.get(reverse("compras:proveedor_ficha", args=[self.c.pk]))
        self.assertNotContains(sin_ordenes, self.ficha_url(orden))
        self.assertContains(sin_ordenes, "Todavía no se le compró")

    def test_la_ficha_del_proveedor_respeta_el_alcance_de_quien_mira(self):
        orden = self.generada()
        self.client.force_login(self.beto)
        self.assertNotContains(self.client.get(reverse("compras:proveedor_ficha", args=[self.a.pk])), self.ficha_url(orden))


class LoQueSumaCmp03EnOtrasPartesTests(OrdenesVistasBase):
    """La advertencia 4c, la URL del impedimento de la orden y el contador de pendientes del Gerente."""

    def test_ext_4c_nuevo_pedido_advierte_que_el_insumo_tiene_una_orden_pendiente_de_aprobacion(self):
        self.generada()
        existencia_ = InsumoInvernadero.objects.get(pk=self.lechuga_iin.pk)
        InsumoInvernadero.objects.filter(pk=existencia_.pk).update(cant_min_insumo=Decimal("50"))
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("compras:pedido_nuevo"), {"iin": existencia_.pk})
        self.assertContains(respuesta, "su orden de compra está pendiente de aprobación")
        self.assertNotContains(respuesta, "con cotizaciones hasta el")

    def test_h20_el_impedimento_de_la_orden_enlaza_a_su_ficha(self):
        orden = self.generada()
        (impedimento,) = registrantes.impedimento_de_deshabilitacion(self.lechuga_iin)
        self.assertEqual((impedimento.codigo, impedimento.url), ("orden_de_compra_aprobada", self.ficha_url(orden)))

    def test_d42_el_contador_de_pendientes_del_gerente_cuenta_las_ordenes_por_aprobar(self):
        self.assertNotIn("Órdenes de compra por aprobar", [d for d, _ in extensiones.contadores_de_pendientes()])
        self.generada()
        self.assertIn(("Órdenes de compra por aprobar", 1), extensiones.contadores_de_pendientes())
        self.assertEqual(servicio_de_ordenes.pendientes_de_aprobacion(), [("Órdenes de compra por aprobar", 1)])

    def test_la_ficha_del_pedido_trae_la_orden_y_si_se_puede_generar(self):
        ficha = servicio_de_pedidos.ficha_de_pedido(self.ana, self.pedido.pk)
        self.assertEqual((ficha.orden, ficha.puede_generar), (None, True))
        orden = self.generada()
        ficha = servicio_de_pedidos.ficha_de_pedido(self.ana, self.pedido.pk)
        self.assertEqual((ficha.orden, ficha.puede_generar), (orden, False))
        self.assertFalse(servicio_de_pedidos.ficha_de_pedido(self.gerente, self.pedido.pk).puede_generar)

    def test_ordenes_del_proveedor_respeta_el_alcance_y_suma_solo_sus_lineas(self):
        orden = self.generada()
        (fila,) = servicio_de_proveedores.ordenes_del_proveedor(self.gerente, self.a)
        self.assertEqual((fila.orden, fila.monto), (orden, Decimal("330.00")))
        self.assertEqual(servicio_de_proveedores.ordenes_del_proveedor(self.beto, self.a), [])
        self.assertEqual([f.orden for f in servicio_de_proveedores.ordenes_del_proveedor(self.ana, self.b)], [orden])


class CoberturaDeLaEleccionTests(OrdenesVistasBase):
    """``cobertura_de_la_eleccion``: función pura sobre la comparación (pasos 5 y 6, extensiones 6a y 6b)."""

    def eleccion(self, *cotizaciones):
        comparacion = servicio_de_ordenes.comparacion(self.ana, self.pedido.pk)
        return servicio_de_ordenes.cobertura_de_la_eleccion(comparacion, [c.pk for c in cotizaciones])

    def test_sin_elegir_nada_no_esta_cubierto_y_el_monto_es_cero(self):
        eleccion = self.eleccion()
        self.assertEqual((eleccion.elegidas, eleccion.monto, eleccion.proveedores, eleccion.cubierto), ([], Decimal("0.00"), 0, False))
        self.assertTrue(all(c.elegida == 0 and not c.cubierto for c in eleccion.coberturas))

    def test_cada_detalle_suma_lo_cotizado_por_lo_elegido_y_dice_cuanto_falta(self):
        eleccion = self.eleccion(self.cot_a)
        por_detalle = {c.detalle.pk: c for c in eleccion.coberturas}
        self.assertEqual((por_detalle[self.lechuga.pk].elegida, por_detalle[self.lechuga.pk].cubierto), (Decimal("20"), True))
        self.assertEqual((por_detalle[self.tomate.pk].elegida, por_detalle[self.tomate.pk].falta, por_detalle[self.tomate.pk].cubierto), (Decimal("10"), Decimal("8"), False))
        self.assertFalse(eleccion.cubierto)

    def test_con_todo_cubierto_se_puede_generar_y_se_cuenta_proveedores_y_monto(self):
        eleccion = self.eleccion(self.cot_a, self.cot_b)
        self.assertEqual((eleccion.cubierto, eleccion.proveedores, eleccion.monto), (True, 2, Decimal("430.00")))

    def test_ext_6b_lo_que_supera_lo_pedido_se_informa_como_sobra(self):
        eleccion = self.eleccion(self.cot_a, self.cot_b, self.cot_c)
        por_detalle = {c.detalle.pk: c for c in eleccion.coberturas}
        self.assertEqual((por_detalle[self.lechuga.pk].sobra, por_detalle[self.tomate.pk].sobra), (Decimal("10"), Decimal("0")))

    def test_los_ids_repetidos_invalidos_o_no_elegibles_se_ignoran(self):
        self.b.estado_proveedor = "inactivo"
        self.b.save(update_fields=["estado_proveedor"])
        comparacion = servicio_de_ordenes.comparacion(self.ana, self.pedido.pk)
        eleccion = servicio_de_ordenes.cobertura_de_la_eleccion(comparacion, [self.cot_a.pk, self.cot_a.pk, "abc", 99999, self.cot_b.pk, None])
        self.assertEqual([c.cotizacion.pk for c in eleccion.elegidas], [self.cot_a.pk])

    def test_no_consulta_la_base(self):
        comparacion = servicio_de_ordenes.comparacion(self.ana, self.pedido.pk)
        with self.assertNumQueries(0):
            servicio_de_ordenes.cobertura_de_la_eleccion(comparacion, [self.cot_a.pk, self.cot_b.pk])



class ContadorVistasTests(OrdenesVistasBase):
    """El Contador (USR-11, D-85) ve «Compras» solo con las órdenes, en solo lectura (D-87 punto 6; CMP-CNS-ODC regla 1). Ningún botón ni enlace le lleva a un 403 (D-30)."""

    def setUp(self):
        super().setUp()
        from core.models import Contador
        from core.tests.fabricas import crear_cuenta

        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.orden = self.generada()
        self.client.force_login(self.contador)

    def test_ve_la_lista_y_la_ficha_de_cualquier_orden(self):
        respuesta = self.client.get(self.lista_url)
        self.assertContains(respuesta, str(self.orden))
        self.assertContains(self.client.get(self.ficha_url(self.orden)), "Semillas del Sur S. A.")

    def test_no_tiene_botones_de_revisar_ni_de_decidir(self):
        for url in (self.lista_url, self.ficha_url(self.orden)):
            self.assertNotContains(self.client.get(url), self.resolver_url(self.orden))

    def test_ningun_enlace_lleva_a_un_403_ni_a_pedidos_ni_a_proveedores(self):
        pedido = reverse("compras:pedido_ficha", args=[self.pedido.pk])
        for url in (self.lista_url, self.ficha_url(self.orden)):
            respuesta = self.client.get(url)
            self.assertNotContains(respuesta, f'href="{pedido}"')
            self.assertNotContains(respuesta, reverse("compras:pedidos"))
            self.assertNotContains(respuesta, reverse("compras:proveedores"))

    def test_solo_tiene_la_pestana_ordenes_y_el_menu_apunta_a_ordenes(self):
        respuesta = self.client.get(self.lista_url)
        self.assertContains(respuesta, 'role="tab"', count=1)
        self.assertContains(respuesta, f'href="{self.lista_url}"')

    def test_los_filtros_de_la_lista_ofrecen_proveedores_e_invernaderos(self):
        respuesta = self.client.get(self.lista_url)
        self.assertContains(respuesta, "Viveros del Este S. R. L.")
        self.assertContains(respuesta, "Norte 2")
        self.assertNotContains(respuesta, "Todos los Agrónomos")

    def test_lo_demas_de_compras_le_da_403(self):
        for url in (
            reverse("compras:pedidos"),
            reverse("compras:pedido_ficha", args=[self.pedido.pk]),
            reverse("compras:proveedores"),
            reverse("compras:proveedor_ficha", args=[self.a.pk]),
            self.generar_url,
            self.resolver_url(self.orden),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_el_inicio_del_contador_no_trae_secciones_de_compras(self):
        self.assertNotContains(self.client.get(reverse("core:inicio")), "Órdenes pendientes de aprobación")
