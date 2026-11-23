# Pruebas de las pantallas de «Compras» → «Pedidos» (CMP-02a, paso 5): la lista, la ficha y «Nuevo pedido» del Agrónomo, la consulta del Gerente, el inicio del
# Agrónomo y la tarjeta de pedidos de la ficha del proveedor. Fuente: CMP-RLZ-PED y CMP-CNS-PED (docs/casos_de_uso/compras/pedidos.md); prototipo ``tabPed``, ``c_ped``,
# ``c_pednew`` y ``panelAgr``. Las vistas solo orquestan: las reglas ya las prueban ``test_cmp_rlz_ped.py`` y ``test_cmp_cns_ped.py``.
#
# Contrato de «Nuevo pedido» (``compras:pedido_nuevo``; un solo formulario que se vuelve a dibujar con cada acción, sin JavaScript): campos ``detalle_iin`` y
# ``detalle_cantidad`` (listas paralelas: una fila por insumo), ``proveedor`` (lista), ``fecha_limite`` (AAAA-MM-DD), ``filtro`` (``""`` = el propuesto, ``todos`` o el id
# de una categoría), y ``accion``: ``agregar:<iin_id>``, ``quitar:<posición>``, ``filtrar``, ``todos``, ``habilitar`` (con ``hab_invernadero``, ``hab_insumo``,
# ``hab_minimo`` y ``hab_precio``: extensión 3a.1a), ``revisar`` (pasos 5 a 9), ``editar`` (10a: volver a corregir) y ``confirmar`` (paso 10). El contexto trae ``filas``
# (los insumos del pedido) y ``proveedores`` (``[{"proveedor", "marcado", "vende_lo_que_pide"}]``).

from datetime import timedelta
from decimal import Decimal

from unittest import mock

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from compras.models import EnlaceProveedor, InvitacionPedido, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor, tipo_de_insumo
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_capataz, crear_gerente
from inventario.models import InsumoInvernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote
from maestros.tests.fabricas import crear_agronomo_con_invernadero, crear_vendedor


def en(dias):
    return timezone.localdate() + timedelta(days=dias)


class PedidosVistasBase(ConDatosDeInventario, TestCase):
    """Una Agrónoma con un invernadero y dos insumos bajo el mínimo (lechuga por unidad y nutriente en kg), un Gerente y dos proveedores activos."""

    def setUp(self):
        self.ana, self.norte = crear_agronomo_con_invernadero("Invernadero Norte", email="ana@infoponia.com")
        self.gerente = crear_gerente()
        self.categoria = tipo_de_insumo("Semillas y plantines")
        self.lechuga = existencia(insumo("Lechuga", tipo=self.categoria, unidad="unidad", descripcion="Plantín"), self.norte, minimo=20, precio="12.50")
        self.nutriente = existencia(insumo("Nutriente", unidad="kg"), self.norte, minimo=5, precio="100.00")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com", especialidades=[self.categoria])
        self.este = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.lista = reverse("compras:pedidos")
        self.nuevo = reverse("compras:pedido_nuevo")
        self.client.force_login(self.ana)

    def formulario(self, **cambios):
        """Los datos de un pedido válido: 20 lechugas y 3 kg de nutriente, a los dos proveedores, con la fecha límite pasado mañana."""
        datos = {
            "detalle_iin": [self.lechuga.pk, self.nutriente.pk],
            "detalle_cantidad": ["20", "3"],
            "proveedor": [self.sur.pk, self.este.pk],
            "fecha_limite": en(2).isoformat(),
            "filtro": "todos",
            "accion": "revisar",
        }
        datos.update(cambios)
        return datos

    def pedir(self, **cambios):
        """POST a «Nuevo pedido» con los correos enviados antes de que la vista siga (``on_commit``); sigue las redirecciones. En un ``TestCase`` toda la prueba está
        dentro de una transacción y ``on_commit`` nunca corre solo (``captureOnCommitCallbacks`` lo ejecuta al salir, recién después de la redirección): acá se lo
        reemplaza por una llamada inmediata, que es lo que pasa en producción, donde la vista ya encuentra el resultado de cada envío."""
        with mock.patch.object(transaction, "on_commit", lambda funcion, **kwargs: funcion()):
            return self.client.post(self.nuevo, self.formulario(**cambios), follow=True)


class ListaDePedidosVistaTests(PedidosVistasBase):
    """«Compras» → «Pedidos» (``tabPed``)."""

    def setUp(self):
        super().setUp()
        self.pedido = armar_pedido(self.ana, dias_al_limite=3)
        detalle_de_pedido(self.pedido, self.lechuga, cantidad="20")
        invitar(self.pedido, self.sur)

    def test_el_agronomo_ve_sus_pedidos_con_su_monto_y_el_boton_de_nuevo_pedido(self):
        """Regla 3 de CMP-CNS-PED: identificador, fecha límite, monto estimado, proveedores y estado; el Agrónomo hace los pedidos (botón «Nuevo pedido»)."""
        respuesta = self.client.get(self.lista)
        self.assertEqual(respuesta.status_code, 200)
        for texto in (str(self.pedido), "Invernadero Norte", "$ 250,00", "En cotización", "Nuevo pedido", en(3).strftime("%d/%m/%Y")):
            self.assertContains(respuesta, texto)

    def test_el_gerente_ve_todos_en_modo_consulta_y_sin_boton_de_nuevo_pedido(self):
        """Regla 1 de CMP-CNS-PED: el Gerente ve todos los pedidos en solo lectura («Los hace y los cancela el Agrónomo»); ningún botón lleva a un 403 (D-30)."""
        otra, sur = crear_agronomo_con_invernadero("Invernadero Sur", email="otra@infoponia.com")
        ajeno = armar_pedido(otra)
        detalle_de_pedido(ajeno, existencia(insumo("Maíz", unidad="kg"), sur, minimo=1))
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, str(self.pedido))
        self.assertContains(respuesta, str(ajeno))
        self.assertNotContains(respuesta, "Nuevo pedido")
        self.assertContains(respuesta, "modo consulta")

    def test_el_agronomo_no_ve_los_pedidos_de_otro(self):
        """Regla 1: el Agrónomo ve los que él realizó."""
        otra, sur = crear_agronomo_con_invernadero("Invernadero Sur", email="otra@infoponia.com")
        ajeno = armar_pedido(otra)
        detalle_de_pedido(ajeno, existencia(insumo("Maíz", unidad="kg"), sur, minimo=1))
        self.assertNotContains(self.client.get(self.lista), str(ajeno))

    def test_otros_roles_reciben_403_y_sin_sesion_se_pide_iniciar_sesion(self):
        """SEG-13: Capataz y Vendedor no consultan pedidos; sin sesión redirige al inicio de sesión."""
        for cuenta in (crear_capataz(), crear_vendedor()):
            with self.subTest(cuenta=cuenta):
                self.client.force_login(cuenta)
                self.assertEqual(self.client.get(self.lista).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.lista).status_code, 302)

    def test_los_filtros_de_la_lista(self):
        """Regla 2: estado, invernadero de destino, proveedor invitado y rango de fechas (la pantalla pasa los filtros al servicio)."""
        cancelado = armar_pedido(self.ana, estado="cancelado", causa="manual", motivo="Ya no hace falta")
        detalle_de_pedido(cancelado, self.nutriente)
        respuesta = self.client.get(self.lista, {"estado": "cancelado"})
        self.assertContains(respuesta, str(cancelado))
        self.assertNotContains(respuesta, str(self.pedido))
        respuesta = self.client.get(self.lista, {"proveedor": self.sur.pk})
        self.assertContains(respuesta, str(self.pedido))
        self.assertNotContains(respuesta, str(cancelado))
        self.assertNotContains(self.client.get(self.lista, {"desde": en(5).isoformat()}), str(self.pedido))

    def test_un_filtro_mal_formado_no_rompe_la_pantalla(self):
        """Regla 2: un número o una fecha inválidos se ignoran; la lista sale igual."""
        respuesta = self.client.get(self.lista, {"invernadero": "abc", "desde": "no-es-fecha", "estado": "inventado"})
        self.assertEqual(respuesta.status_code, 200)

    def test_regla_3_se_marca_el_pedido_con_la_fecha_limite_vencida(self):
        """Regla 3: «Fecha límite vencida» en el listado, con el aviso de que hay pedidos por resolver (lo resuelve CMP-03)."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(-1))
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "Fecha límite vencida")

    def test_sin_pedidos_se_dice_que_no_hay(self):
        """Estado vacío: un texto que explica, no una tabla vacía."""
        respuesta = self.client.get(self.lista, {"estado": "cerrado"})
        self.assertContains(respuesta, "No hay pedidos con esos filtros")

    def test_las_pestanas_de_compras_son_pedidos_y_proveedores(self):
        """D-87 punto 6: pestañas «Pedidos» y «Proveedores» para el Agrónomo y el Gerente (cada tarea suma la suya)."""
        for cuenta in (self.ana, self.gerente):
            self.client.force_login(cuenta)
            respuesta = self.client.get(self.lista)
            self.assertContains(respuesta, reverse("compras:pedidos"))
            self.assertContains(respuesta, reverse("compras:proveedores"))


class FichaDelPedidoVistaTests(PedidosVistasBase):
    """``VIEWS.c_ped`` del prototipo, sin las acciones de CMP-02b y CMP-03."""

    def setUp(self):
        super().setUp()
        self.pedido = armar_pedido(self.ana, dias_al_limite=3)
        self.d_lechuga = detalle_de_pedido(self.pedido, self.lechuga, cantidad="20")
        detalle_de_pedido(self.pedido, self.nutriente, cantidad="3")
        self.enlace_sur, _ = enlace_de(invitar(self.pedido, self.sur))
        self.enlace_este, _ = enlace_de(invitar(self.pedido, self.este))
        self.url = reverse("compras:pedido_ficha", args=[self.pedido.pk])

    def test_la_ficha_muestra_los_detalles_con_precio_de_referencia_los_invitados_y_las_cotizaciones(self):
        """Reglas 4 a 6: detalles por invernadero con precio de referencia y subtotal, el monto, los invitados (cotizó o no, estado del enlace) y las cotizaciones recibidas, en solo lectura."""
        EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(estado="usado", fecha_uso=timezone.now())
        cotizacion_de(self.pedido, self.sur, [(self.d_lechuga, 20, "250.00", 3)], observaciones="Cajones")
        respuesta = self.client.get(self.url)
        for texto in ("Invernadero Norte", "Lechuga", "$ 12,50", "$ 250,00", "$ 550,00", "Semillas del Sur S. A.", "Viveros del Este S. R. L.",
                      "Cotizó", "No cotizó", "Usado", "Vigente", "Cajones", "3 días"):
            self.assertContains(respuesta, texto)

    def test_se_marca_el_correo_que_no_se_pudo_enviar(self):
        """D-88 punto 6: «No se pudo enviar» junto al invitado cuyo correo falló."""
        EnlaceProveedor.objects.filter(pk=self.enlace_este.pk).update(estado_envio="pendiente_envio")
        self.assertContains(self.client.get(self.url), "No se pudo enviar")

    def test_el_gerente_ve_la_ficha_en_modo_consulta(self):
        """Regla 1: el Gerente ve cualquier pedido y no puede cambiar nada (la ficha no trae acciones)."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Realizado por")
        self.assertNotContains(respuesta, "Cancelar pedido")

    def test_el_pedido_de_otro_agronomo_es_403_y_uno_inexistente_404(self):
        """Regla 1 y D-28: 403 fuera del alcance, 404 si no existe."""
        otra, sur = crear_agronomo_con_invernadero("Invernadero Sur", email="otra@infoponia.com")
        ajeno = armar_pedido(otra)
        detalle_de_pedido(ajeno, existencia(insumo("Maíz", unidad="kg"), sur, minimo=1))
        self.assertEqual(self.client.get(reverse("compras:pedido_ficha", args=[ajeno.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("compras:pedido_ficha", args=[999999])).status_code, 404)

    def test_otros_roles_reciben_403(self):
        """SEG-13."""
        self.client.force_login(crear_capataz())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_un_pedido_cancelado_muestra_el_motivo(self):
        """Regla 4: si está cancelado, el motivo y la fecha de cierre; si fue automática, también lo dice."""
        cancelado = armar_pedido(self.ana, estado="cancelado", causa="nadie_cotizo", motivo="nadie cotizó")
        detalle_de_pedido(cancelado, self.nutriente)
        respuesta = self.client.get(reverse("compras:pedido_ficha", args=[cancelado.pk]))
        self.assertContains(respuesta, "nadie cotizó")
        self.assertContains(respuesta, "Cancelación automática")

    def test_la_ficha_solo_acepta_get(self):
        """La consulta no escribe: un POST da 405."""
        self.assertEqual(self.client.post(self.url).status_code, 405)


@override_settings(CORREO_CONFIGURADO=True)
class NuevoPedidoVistaTests(PedidosVistasBase):
    """CMP-RLZ-PED: ``VIEWS.c_pednew`` del prototipo."""

    def test_paso_2_muestra_los_insumos_bajo_el_minimo_con_su_stock_y_la_cantidad_sugerida(self):
        """Paso 2: el invernadero y el insumo con su unidad, el stock libre, el tránsito, el mínimo y la cantidad sugerida."""
        lote(self.lechuga, 12)
        respuesta = self.client.get(self.nuevo)
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Insumos bajo el mínimo", "Lechuga", "Nutriente", "Invernadero Norte"):
            self.assertContains(respuesta, texto)
        self.assertEqual({f.iin.insumo.nombre_insumo: f.sugerida for f in respuesta.context["bajo_el_minimo"]},
                         {"Lechuga": Decimal("8"), "Nutriente": Decimal("5")})

    def test_ext_2a_sin_insumos_bajo_el_minimo_se_informa_y_se_sigue_con_el_catalogo(self):
        """Extensión 2a: «no hay insumos bajo el mínimo» y el pedido se arma agregando insumos del catálogo (3a)."""
        lote(self.lechuga, 25)
        lote(self.nutriente, 6)
        respuesta = self.client.get(self.nuevo)
        self.assertContains(respuesta, "No hay insumos bajo el mínimo")
        self.assertContains(respuesta, "Nutriente")  # sigue disponible en el selector del catálogo

    def test_ext_1a_pedir_desde_la_alerta_o_el_inicio_incluye_ese_insumo_con_la_cantidad_sugerida(self):
        """Extensión 1a: ``?iin=`` incluye el insumo con su cantidad sugerida; el Agrónomo puede cambiarla, quitarlo o agregar otros."""
        respuesta = self.client.get(self.nuevo, {"iin": self.lechuga.pk})
        self.assertEqual([(f["iin"].pk, f["cantidad"]) for f in respuesta.context["filas"]], [(self.lechuga.pk, "20")])

    def test_el_gerente_y_otros_roles_no_hacen_pedidos(self):
        """Regla «Solo el rol Agrónomo accede a este caso de uso»: 403 para los demás."""
        for cuenta in (self.gerente, crear_capataz(), crear_vendedor()):
            with self.subTest(cuenta=cuenta):
                self.client.force_login(cuenta)
                self.assertEqual(self.client.get(self.nuevo).status_code, 403)
                self.assertEqual(self.client.post(self.nuevo, self.formulario(accion="confirmar")).status_code, 403)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_pasos_3_y_4_agregar_y_quitar_un_insumo_vuelve_a_dibujar_el_formulario_sin_perder_lo_escrito(self):
        """Extensiones 3b: agregar un insumo (con su sugerida) y quitar un detalle; el resto de lo escrito se conserva."""
        respuesta = self.client.post(self.nuevo, {"accion": f"agregar:{self.nutriente.pk}", "fecha_limite": en(4).isoformat(), "proveedor": [self.sur.pk]})
        self.assertEqual([f["iin"].pk for f in respuesta.context["filas"]], [self.nutriente.pk])
        self.assertContains(respuesta, en(4).isoformat())
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk, self.nutriente.pk], "detalle_cantidad": ["20", "3"], "accion": "quitar:0"})
        self.assertEqual([(f["iin"].pk, f["cantidad"]) for f in respuesta.context["filas"]], [(self.nutriente.pk, "3")])

    def test_regla_la_misma_fila_no_se_agrega_dos_veces_desde_la_lista(self):
        """Extensión 4b: agregar un insumo que ya está en el pedido no repite la fila (la cantidad actual queda como estaba)."""
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["7"], "accion": f"agregar:{self.lechuga.pk}"})
        self.assertEqual([(f["iin"].pk, f["cantidad"]) for f in respuesta.context["filas"]], [(self.lechuga.pk, "7")])

    def test_ext_7a_y_7b_el_filtro_propuesto_por_categoria_y_seleccionar_todos(self):
        """Extensiones 7a y 7b (H13, MD-121): el filtro se propone con las categorías de los insumos del pedido; «seleccionar todos» marca solo los de la lista filtrada."""
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["20"], "filtro": "", "accion": "filtrar"})
        por_nombre = {p["proveedor"].nombre_para_mostrar: p for p in respuesta.context["proveedores"]}
        self.assertEqual(list(por_nombre), ["Semillas del Sur S. A."])  # el propuesto: los que venden lo que pide
        self.assertTrue(por_nombre["Semillas del Sur S. A."]["vende_lo_que_pide"])
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["20"], "filtro": "", "accion": "todos"})
        self.assertEqual({p["proveedor"].pk: p["marcado"] for p in respuesta.context["proveedores"]}, {self.sur.pk: True})
        respuesta = self.client.post(self.nuevo, {"detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["20"], "filtro": "todos", "accion": "todos"})
        self.assertEqual({p["proveedor"].pk: p["marcado"] for p in respuesta.context["proveedores"]}, {self.sur.pk: True, self.este.pk: True})

    def test_pasos_6_y_8_la_fecha_limite_propuesta_y_los_proveedores_activos_sin_marcar(self):
        """Pasos 6 y 7 y regla «Proveedores invitables»: se propone la fecha límite; el Sistema no marca ningún proveedor por su cuenta; un inactivo no aparece."""
        proveedor("Inactivo", n=3, activo=False)
        respuesta = self.client.get(self.nuevo, {"iin": self.lechuga.pk})
        self.assertEqual(respuesta.context["fecha_limite"], (timezone.localdate() + timedelta(days=3)).isoformat())
        self.assertFalse(any(p["marcado"] for p in respuesta.context["proveedores"]))
        self.assertNotContains(respuesta, "Inactivo")

    def test_paso_9_revisar_muestra_el_resumen_agrupado_con_el_monto_los_proveedores_y_no_registra_nada(self):
        """Paso 9: detalles por invernadero con precio de referencia y subtotal, el monto, la fecha límite y los proveedores invitados; revisar no escribe."""
        respuesta = self.client.post(self.nuevo, self.formulario())
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Invernadero Norte", "$ 12,50", "$ 250,00", "$ 550,00", en(2).strftime("%d/%m/%Y"), "Semillas del Sur S. A.", "Viveros del Este S. R. L.", "Confirmar pedido"):
            self.assertContains(respuesta, texto)
        self.assertEqual((Pedido.objects.count(), mail.outbox), (0, []))

    def test_ext_4c_el_resumen_advierte_del_insumo_ya_pedido_y_deja_confirmar(self):
        """Extensión 4c: la advertencia nombra al otro pedido, su cantidad y su fecha límite; no impide confirmar."""
        previo = armar_pedido(self.ana, dias_al_limite=4)
        detalle_de_pedido(previo, self.lechuga, cantidad="7")
        respuesta = self.client.post(self.nuevo, self.formulario())
        self.assertContains(respuesta, str(previo))
        self.assertContains(respuesta, "Confirmar pedido")

    def test_extensiones_4a_5a_8a_y_8b_los_errores_vuelven_junto_a_cada_campo_y_se_conserva_lo_escrito(self):
        """Extensiones 4a, 5a, 8a y 8b: cantidad inválida, pedido sin detalles, fecha anterior a mañana y sin proveedores; el formulario conserva lo escrito."""
        respuesta = self.client.post(self.nuevo, self.formulario(detalle_cantidad=["0", "3"], proveedor=[], fecha_limite=timezone.localdate().isoformat()))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="err"')
        for texto in ("al menos a un proveedor", "La fecha límite tiene que ser desde el"):
            self.assertContains(respuesta, texto)
        self.assertEqual([f["cantidad"] for f in respuesta.context["filas"]], ["0", "3"])
        sin_detalles = self.client.post(self.nuevo, {"proveedor": [self.sur.pk], "fecha_limite": en(2).isoformat(), "accion": "revisar"})
        self.assertContains(sin_detalles, "al menos un insumo")
        self.assertEqual(Pedido.objects.count(), 0)

    def test_pasos_10_a_13_confirmar_registra_el_pedido_envia_los_correos_y_lleva_a_su_ficha(self):
        """Pasos 10 a 13: el pedido «en cotización» con sus invitaciones, un correo por proveedor y la ficha con el aviso «Enviamos el pedido»."""
        respuesta = self.pedir(accion="confirmar")
        pedido = Pedido.objects.get()
        self.assertEqual(respuesta.redirect_chain[-1][0], reverse("compras:pedido_ficha", args=[pedido.pk]))
        self.assertContains(respuesta, f"Enviamos el pedido {pedido}")
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        self.assertEqual(pedido.invitaciones.count(), 2)

    def test_ext_12a_si_un_correo_falla_se_avisa_al_agronomo_en_la_pantalla_y_no_en_la_campana(self):
        """Extensión 12a, D-88 punto 6 y H21: el aviso con el proveedor al que no se pudo enviar va en la pantalla del paso 13; no se crea ninguna notificación para quien actuó."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            respuesta = self.pedir(accion="confirmar")
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertContains(respuesta, "No se pudo enviar la invitación a Semillas del Sur S. A.")
        self.assertContains(respuesta, "pedile al Gerente que revise su correo y reenviá la invitación")
        self.assertEqual(Notificacion.objects.filter(destinatario=self.ana).count(), 0)

    def test_ext_11a_si_algo_cambio_entre_el_resumen_y_la_confirmacion_no_se_registra_y_se_informa(self):
        """Extensión 11a: un insumo deshabilitado antes de confirmar; la pantalla informa qué cambió y no es un error 500."""
        InsumoInvernadero.objects.filter(pk=self.nutriente.pk).update(estado_insumo_invernadero="inactivo")
        respuesta = self.pedir(accion="confirmar")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no se puede pedir")
        self.assertEqual((Pedido.objects.count(), mail.outbox), (0, []))

    def test_10a_volver_a_corregir_conserva_los_datos_sin_validar(self):
        """Extensión 10a: «Volver a corregir» vuelve al formulario con lo escrito y sin mostrar errores."""
        respuesta = self.client.post(self.nuevo, self.formulario(accion="editar", detalle_cantidad=["0", "3"]))
        self.assertEqual([f["cantidad"] for f in respuesta.context["filas"]], ["0", "3"])
        self.assertNotContains(respuesta, 'class="err"')

    def test_ext_3a_el_selector_ofrece_los_insumos_habilitados_de_cada_invernadero_a_cargo(self):
        """Extensión 3a: el Agrónomo elige uno de sus invernaderos y busca el insumo en el catálogo: el selector agrupa por invernadero."""
        otro = crear_agronomo_con_invernadero("Invernadero Oeste", email="x@infoponia.com")[1]
        otro.agronomo = self.ana
        otro.save()
        existencia(insumo("Maíz", unidad="kg"), otro, minimo=1)
        respuesta = self.client.get(self.nuevo)
        self.assertContains(respuesta, "Invernadero Oeste")
        self.assertContains(respuesta, "Maíz")

    def test_ext_3a_1a_habilitar_un_insumo_que_no_esta_habilitado_lo_agrega_al_pedido(self):
        """Extensión 3a.1a: «El insumo no está habilitado en el invernadero»: se ofrece habilitarlo (CMP-HAB-IIN) con su mínimo y precio y el caso de uso continúa con el insumo habilitado, que tiene stock cero."""
        sustrato = insumo("Sustrato", unidad="kg")
        respuesta = self.client.post(
            self.nuevo,
            {"accion": "habilitar", "hab_invernadero": self.norte.pk, "hab_insumo": sustrato.pk, "hab_minimo": "5", "hab_precio": "30.00",
             "detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["20"]},
        )
        creada = InsumoInvernadero.objects.get(insumo=sustrato, invernadero=self.norte)
        self.assertEqual((creada.cant_min_insumo, creada.referencia_precio), (Decimal("5"), Decimal("30.00")))
        self.assertEqual([f["iin"].pk for f in respuesta.context["filas"]], [self.lechuga.pk, creada.pk])
        self.assertContains(respuesta, "Sustrato")

    def test_ext_3a_1a_si_los_datos_de_la_habilitacion_no_sirven_se_muestran_sus_errores(self):
        """Extensión 3a.1a: los errores de la habilitación (precio inválido) vuelven junto a sus campos; no se habilita nada ni se pierde el pedido."""
        sustrato = insumo("Sustrato", unidad="kg")
        respuesta = self.client.post(
            self.nuevo,
            {"accion": "habilitar", "hab_invernadero": self.norte.pk, "hab_insumo": sustrato.pk, "hab_minimo": "5", "hab_precio": "0",
             "detalle_iin": [self.lechuga.pk], "detalle_cantidad": ["20"]},
        )
        self.assertContains(respuesta, "precio mayor que 0")
        self.assertFalse(InsumoInvernadero.objects.filter(insumo=sustrato).exists())
        self.assertEqual([f["iin"].pk for f in respuesta.context["filas"]], [self.lechuga.pk])


class InicioYFichaDelProveedorTests(PedidosVistasBase):
    """El Inicio del Agrónomo (``panelAgr``: «Insumos bajo el mínimo» con «Pedir» y «Esperando cotizaciones») y la tarjeta de pedidos de la ficha del proveedor."""

    def test_el_inicio_del_agronomo_ofrece_pedir_los_insumos_bajo_el_minimo(self):
        """``panelAgr``: cantidad de insumos bajo el mínimo y, por cada uno, «Pedir» (extensión 1a: ``?iin=``)."""
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, "Insumos bajo el mínimo")
        self.assertContains(respuesta, f"{self.nuevo}?iin={self.lechuga.pk}")

    def test_el_inicio_cuenta_los_pedidos_esperando_cotizaciones(self):
        """``panelAgr``: «Esperando cotizaciones»: los pedidos «en cotización» con la fecha límite que no venció."""
        pedido = armar_pedido(self.ana)
        detalle_de_pedido(pedido, self.lechuga)
        vencido = armar_pedido(self.ana)
        Pedido.objects.filter(pk=vencido.pk).update(fecha_pedido=en(-8), fecha_limite_cotizaciones=en(-1))
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertContains(respuesta, "Esperando cotizaciones")
        self.assertContains(respuesta, 'data-kpi="esperando">1<')  # solo el que todavía no venció

    def test_el_inicio_del_gerente_no_trae_la_seccion_de_pedidos(self):
        """D-87 punto 5: la sección del Agrónomo es suya; el Gerente suma las suyas en CMP-03 (órdenes por aprobar)."""
        self.client.force_login(self.gerente)
        self.assertNotContains(self.client.get(reverse("core:inicio")), "Insumos bajo el mínimo")

    def test_la_ficha_del_proveedor_lista_sus_pedidos(self):
        """CMP-CNS-PRV regla 4: la tarjeta «Pedidos» de la ficha, con el estado y si cotizó, y un enlace a cada ficha; sin pedidos dice que todavía no hay."""
        ficha = reverse("compras:proveedor_ficha", args=[self.sur.pk])
        self.assertContains(self.client.get(ficha), "Todavía no")
        pedido = armar_pedido(self.ana)
        d = detalle_de_pedido(pedido, self.lechuga)
        invitar(pedido, self.sur)
        cotizacion_de(pedido, self.sur, [(d, 10, "100.00", 2)])
        respuesta = self.client.get(ficha)
        self.assertContains(respuesta, str(pedido))
        self.assertContains(respuesta, reverse("compras:pedido_ficha", args=[pedido.pk]))
        self.assertContains(respuesta, "Cotizó")

    def test_el_cuit_de_un_proveedor_con_pedidos_no_se_edita(self):
        """CMP-MOD-PRV regla 2 con la consulta ya completa (sin ``mock``): el CUIT del proveedor invitado a un pedido queda de solo lectura."""
        self.client.force_login(self.gerente)
        pedido = armar_pedido(self.ana)
        invitar(pedido, self.sur)
        respuesta = self.client.get(reverse("compras:proveedor_editar", args=[self.sur.pk]))
        self.assertTrue(respuesta.context["cuit_fijo"])
