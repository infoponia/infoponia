# Pruebas de las pantallas de la recepción y del cierre con faltante (CMP-04, paso 6): «Por recibir» (``tabRec``), «Registrar recepción» (``VIEWS.c_rcp``), «Cerrar con faltante»
# (``VIEWS.c_flt``), la sección «Recepciones» y las acciones de la ficha de la orden (``VIEWS.c_odc``; CMP-CNS-ODC reglas 6 y 8), los atajos de la lista, la tarjeta del inicio del Agrónomo
# (``panelAgr``) y el enlace del asiento a la ficha de la orden en el libro de gestión. Fuente: docs/casos_de_uso/compras/recepcion.md y docs/casos_de_uso/contabilidad/libro_de_gestion.md
# («Enlace al origen»). Las vistas solo orquestan: las reglas las prueban ``test_cmp_reg_rcp.py`` y ``test_cmp_crr_flt.py``.
#
# Contrato de «Registrar recepción» (``compras:recepcion_nueva``, ``?proveedor=&invernadero=``; un solo formulario que se vuelve a dibujar con cada acción, sin JavaScript): por línea
# ``lotes_<id>`` (cuántas filas de lote), ``cant_<id>_<k>`` y ``venc_<id>_<k>``; ``incs_<id>``, ``inc_tipo_<id>_<k>``, ``inc_cant_<id>_<k>`` e ``inc_desc_<id>_<k>``; ``observaciones`` y ``accion``:
# ``revisar`` (paso 7), ``confirmar`` (paso 9), ``editar``, ``mas_lote:<id>`` y ``mas_inc:<id>``. Contrato de «Cerrar con faltante» (``compras:cierre_faltante``): ``linea`` (ids elegidos),
# ``motivo_<id>`` y ``accion`` = ``revisar``, ``confirmar`` o ``editar``.

from django.core import mail
from django.urls import reverse

from compras.models import DetalleOrdenCompra, InconvenienteRecepcion, Recepcion, ReclamoProveedor
from compras.tests.base_recepciones import DANADA, D, RecepcionBase
from contabilidad.models import AsientoContable
from contabilidad.tests.fabricas import verificar_invariantes_contables
from core.models import Contador
from core.tests.fabricas import crear_cuenta
from inventario.models import LoteInsumo
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas


class VistasDeRecepcionBase(RecepcionBase):
    """Las URLs y los auxiliares para enviar los formularios."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        super().setUp()
        self.ficha_url = reverse("compras:orden_ficha", args=[self.orden.pk])
        self.recibir_url = reverse("compras:recepcion_nueva", args=[self.orden.pk])
        self.entrega_a = f"?proveedor={self.proveedor.pk}&invernadero={self.norte.pk}"
        self.cerrar_url = reverse("compras:cierre_faltante", args=[self.orden.pk])

    def como(self, usuario):
        self.client.force_login(usuario)

    def recibir_post(self, accion, lineas=None, observaciones="", extra=None):
        """El formulario de A en Norte con ``lineas = {detalle: {"cant": …, "venc": …, "inc": (tipo, cant, desc)}}``."""
        datos = {"proveedor": self.proveedor.pk, "invernadero": self.norte.pk, "observaciones": observaciones, "accion": accion}
        for detalle in (self.l_fert, self.l_maceta):
            datos[f"lotes_{detalle.pk}"] = 1
            datos[f"incs_{detalle.pk}"] = 0
        for detalle, campos in (lineas or {}).items():
            i = detalle.pk
            datos[f"cant_{i}_0"] = campos.get("cant", "")
            datos[f"venc_{i}_0"] = campos.get("venc", "")
            if "inc" in campos:
                tipo, cantidad, descripcion = campos["inc"]
                datos[f"incs_{i}"] = 1
                datos.update({f"inc_tipo_{i}_0": tipo, f"inc_cant_{i}_0": cantidad, f"inc_desc_{i}_0": descripcion})
        datos.update(extra or {})
        return self.client.post(self.recibir_url, datos)

    def cierre_post(self, accion, lineas, extra=None):
        """``lineas = {detalle: motivo}``: se tildan todas las que se pasen."""
        datos = {"accion": accion, "linea": [d.pk for d in lineas]}
        datos.update({f"motivo_{d.pk}": motivo for d, motivo in lineas.items()})
        datos.update(extra or {})
        return self.client.post(self.cerrar_url, datos)


class PorRecibirVistaTests(VistasDeRecepcionBase):
    """«Compras» → «Por recibir» (paso 2, ``tabRec``)."""

    def test_paso_2_el_agronomo_ve_sus_entregas_con_el_boton_de_registrar(self):
        """Paso 2: la lista de entregas pendientes de Ana, con el proveedor, el invernadero, las líneas y el botón que lleva al formulario de esa entrega."""
        self.como(self.ana)
        respuesta = self.client.get(reverse("compras:por_recibir"))
        self.assertContains(respuesta, "Semillas del Sur S. A.")
        self.assertContains(respuesta, "Viveros del Este S. R. L.")
        self.assertContains(respuesta, f"{self.recibir_url}?proveedor={self.proveedor.pk}&amp;invernadero={self.norte.pk}")
        self.assertContains(respuesta, 'aria-selected="true">Por recibir')

    def test_ext_1a_el_gerente_ve_todo_y_un_agronomo_sin_destinos_el_estado_vacio(self):
        """Extensión 1a: el Gerente ve todas las entregas; Beto, sin destinos en esta orden, ve el estado vacío (no una lista ajena)."""
        self.como(self.gerente)
        self.assertContains(self.client.get(reverse("compras:por_recibir")), "Semillas del Sur S. A.")
        self.como(self.beto)
        respuesta = self.client.get(reverse("compras:por_recibir"))
        self.assertContains(respuesta, "No hay mercadería pendiente de recibir")
        self.assertNotContains(respuesta, "Semillas del Sur S. A.")

    def test_ext_4a1_una_entrega_con_todo_el_destino_inactivo_no_ofrece_el_boton(self):
        """Extensión 4a1: si todo el destino está inactivo, se dice y no se ofrece «Registrar recepción» (D-30)."""
        from maestros.models import Invernadero

        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="inactivo")
        self.como(self.ana)
        respuesta = self.client.get(reverse("compras:por_recibir"))
        self.assertContains(respuesta, "Destino inactivo")
        self.assertNotContains(respuesta, f"proveedor={self.proveedor_b.pk}&amp;invernadero={self.norte2.pk}")

    def test_regla_otros_roles_no_entran_y_el_contador_no_ve_la_pestana(self):
        """Solo el Agrónomo y el Gerente: otros roles reciben 403; el Contador ve las órdenes sin la pestaña «Por recibir» (solo lectura)."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.como(contador)
        self.assertEqual(self.client.get(reverse("compras:por_recibir")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("compras:ordenes")), "Por recibir</a>")


class RegistrarRecepcionVistaTests(VistasDeRecepcionBase):
    """«Registrar recepción» (pasos 3 a 11, ``VIEWS.c_rcp``)."""

    def test_paso_4_el_formulario_muestra_las_lineas_con_lo_pedido_y_lo_que_falta(self):
        """Paso 4: cada línea con su insumo, lo pedido y lo que falta, el campo de cantidad y, solo si el insumo controla el vencimiento, el de fecha (si no, «No vence»)."""
        self.como(self.ana)
        respuesta = self.client.get(self.recibir_url + self.entrega_a)
        self.assertContains(respuesta, "Fertilizante")
        self.assertContains(respuesta, "Maceta")
        self.assertContains(respuesta, f'name="cant_{self.l_fert.pk}_0"')
        self.assertContains(respuesta, f'name="venc_{self.l_fert.pk}_0"')
        self.assertNotContains(respuesta, f'name="venc_{self.l_maceta.pk}_0"')
        self.assertContains(respuesta, "No vence")
        self.assertNotContains(respuesta, "Tomate")  # es de otro proveedor y otro invernadero

    def test_regla_quien_registra_otro_agronomo_es_403_y_una_orden_inexistente_404(self):
        """Regla «Quién registra»: Beto no registra la recepción de Norte (403, sin botón en ningún lado); una orden inexistente, 404; el Contador, 403."""
        self.como(self.beto)
        self.assertEqual(self.client.get(self.recibir_url + self.entrega_a).status_code, 403)
        self.como(self.ana)
        self.assertEqual(self.client.get(reverse("compras:recepcion_nueva", args=[999999])).status_code, 404)
        self.como(crear_cuenta(Contador, email="contador@infoponia.com"))
        self.assertEqual(self.client.get(self.recibir_url).status_code, 403)

    def test_paso_7_ver_resumen_muestra_lo_que_pasara_y_no_registra_nada(self):
        """Paso 7: el resumen dice lo que ingresa, el estado de la orden y el monto del asiento, aclara que no registra pagos y NO escribe nada."""
        self.como(self.ana)
        respuesta = self.recibir_post("revisar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        self.assertContains(respuesta, "Confirmá la recepción")
        self.assertContains(respuesta, "no registra ningún pago")
        self.assertContains(respuesta, "$ 40,00")
        self.assertContains(respuesta, "Parcialmente recibida")
        self.assertContains(respuesta, 'value="confirmar"')
        self.assertEqual((Recepcion.objects.count(), LoteInsumo.objects.count(), AsientoContable.objects.count()), (0, 0, 0))

    def test_paso_9_confirmar_registra_la_recepcion_y_lleva_a_la_ficha(self):
        """Paso 9 y 11: «Confirmar» registra (recepción, lote, asiento) y lleva a la ficha de la orden con el aviso de lo registrado; la coma decimal se acepta."""
        self.como(self.ana)
        respuesta = self.recibir_post("confirmar", {self.l_fert: {"cant": "4,5", "venc": self.vence.isoformat()}}, observaciones="Llegó temprano.", extra={})
        self.assertRedirects(respuesta, self.ficha_url, fetch_redirect_response=False)
        recepcion = Recepcion.objects.get()
        self.assertEqual((recepcion.agronomo_id, recepcion.observaciones_recepcion), (self.ana.pk, "Llegó temprano."))
        self.assertEqual(self.stock_de(self.fertilizante), D("4.5"))
        self.assertEqual(AsientoContable.objects.get().origen_id, recepcion.pk)
        verificar_invariantes_contables()
        pagina = self.client.get(self.ficha_url)
        self.assertContains(pagina, f"Registramos la recepción {recepcion}")
        self.assertContains(pagina, "Recepciones")
        self.assertContains(pagina, f"vence el {self.vence:%d/%m/%Y}")

    def test_ext_11a_si_quedaron_lineas_pendientes_se_ofrece_cerrarlas_con_faltante(self):
        """Extensión 11a: al terminar, la pantalla informa lo que quedó pendiente de la recepción y ofrece «Cerrar con faltante» (con ?recepcion=, extensión 2a de CMP-CRR-FLT)."""
        self.como(self.ana)
        self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        pagina = self.client.get(self.ficha_url)
        recepcion = Recepcion.objects.get()
        self.assertContains(pagina, "Quedó pendiente")
        self.assertContains(pagina, f"{self.cerrar_url}?recepcion={recepcion.pk}")

    def test_ext_7a_un_error_de_negocio_vuelve_al_formulario_con_lo_escrito(self):
        """Extensiones 7a y 7b: una cantidad que supera lo que falta vuelve al formulario con el mensaje y lo que se había escrito, sin registrar nada."""
        self.como(self.ana)
        respuesta = self.recibir_post("confirmar", {self.l_fert: {"cant": "11", "venc": self.vence.isoformat()}})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "faltan recibir")
        self.assertContains(respuesta, 'value="11"')
        self.assertEqual(Recepcion.objects.count(), 0)

    def test_ext_7b_un_numero_o_una_fecha_ilegibles_se_senalan_sin_llamar_al_servicio(self):
        """Extensión 7b: «abc» como cantidad o una fecha mal escrita se señalan en la línea; no se registra nada."""
        self.como(self.ana)
        respuesta = self.recibir_post("revisar", {self.l_fert: {"cant": "abc", "venc": self.vence.isoformat()}})
        self.assertContains(respuesta, "Escribí la cantidad recibida como un número")
        self.assertEqual(Recepcion.objects.count(), 0)

    def test_ext_7d_una_recepcion_sin_ninguna_linea_se_rechaza(self):
        """Extensión 7d: sin cantidad en ninguna línea, «La recepción tiene que incluir al menos una línea»."""
        self.como(self.ana)
        respuesta = self.recibir_post("revisar")
        self.assertContains(respuesta, "al menos una línea")

    def test_paso_5_agregar_otro_lote_suma_una_fila_y_agregar_inconveniente_suma_otra(self):
        """Paso 5: «Agregar otro lote» (una cantidad por cada fecha distinta) y «Agregar un inconveniente» vuelven a dibujar el formulario con una fila más, sin registrar nada."""
        self.como(self.ana)
        respuesta = self.recibir_post("mas_lote:%d" % self.l_fert.pk)
        self.assertContains(respuesta, f'name="cant_{self.l_fert.pk}_1"')
        self.assertContains(respuesta, 'value="2"')
        respuesta = self.recibir_post("mas_inc:%d" % self.l_fert.pk)
        self.assertContains(respuesta, f'name="inc_tipo_{self.l_fert.pk}_0"')
        self.assertEqual(Recepcion.objects.count(), 0)

    def test_post_k_un_inconveniente_genera_el_reclamo_sin_emitir_y_aparece_en_la_ficha_y_en_el_atajo(self):
        """Postcondiciones i a k (7f): con un inconveniente se crea el reclamo sin emitir y la alerta; la ficha lo muestra («Reclamo … sin emitir»), la lista de órdenes lo marca y el atajo «Con reclamo
        sin emitir» lo encuentra."""
        self.como(self.ana)
        self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat(), "inc": (DANADA, "2", "Cajas rotas")}})
        reclamo = ReclamoProveedor.objects.get()
        self.assertEqual(InconvenienteRecepcion.objects.count(), 1)
        pagina = self.client.get(self.ficha_url)
        self.assertContains(pagina, f"Reclamo {reclamo} sin emitir")
        self.assertContains(pagina, "Cajas rotas")
        lista = self.client.get(reverse("compras:ordenes") + "?atajo=con_reclamo_sin_emitir")
        self.assertContains(lista, "Reclamo sin emitir")
        self.assertContains(lista, str(self.orden))

    def test_regla_la_ficha_dice_quien_registro_la_recepcion_el_gerente_cuando_no_hay_agronomo(self):
        """Regla 6 de CMP-CNS-ODC: quién la registró (el Agrónomo o, sin Agrónomo, el Gerente)."""
        self.como(self.gerente)
        self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        self.assertContains(self.client.get(self.ficha_url), "la registró el Gerente")

    def test_ext_9b_si_el_destino_se_vuelve_inactivo_al_registrar_se_vuelve_a_la_ficha(self):
        """Extensión 9b: si el destino pasó a inactivo al registrar, no se registra nada y se vuelve a la ficha con el motivo."""
        from maestros.models import Invernadero

        self.como(self.ana)
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        respuesta = self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        self.assertRedirects(respuesta, self.ficha_url, fetch_redirect_response=False)
        self.assertEqual(Recepcion.objects.count(), 0)

    def test_regla_el_correo_al_proveedor_sale_al_registrar(self):
        """Postcondición h: el proveedor recibe un correo al confirmar la recepción (los correos están configurados en esta clase)."""
        self.como(self.ana)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        self.assertEqual([m.to for m in mail.outbox], [[self.proveedor.email_proveedor]])


class FichaYListaDeRecepcionTests(VistasDeRecepcionBase):
    """CMP-CNS-ODC reglas 2, 6 y 8: lo que la ficha y la lista suman con CMP-04, y el inicio del Agrónomo."""

    def test_regla_8_las_acciones_de_la_ficha_segun_quien_mira(self):
        """Regla 8 y D-30: Ana y el Gerente ven «Registrar recepción» y «Cerrar con faltante» en una orden aprobada; el Contador (solo lectura) no ve ninguna; Beto recibe 403 (sin botones)."""
        for usuario in (self.ana, self.gerente):
            self.como(usuario)
            pagina = self.client.get(self.ficha_url)
            self.assertContains(pagina, "Registrar recepción")
            self.assertContains(pagina, "Cerrar con faltante")
        self.como(crear_cuenta(Contador, email="contador@infoponia.com"))
        pagina = self.client.get(self.ficha_url)
        self.assertNotContains(pagina, "Registrar recepción")
        self.assertNotContains(pagina, "Cerrar con faltante")
        self.como(self.beto)
        self.assertEqual(self.client.get(self.ficha_url).status_code, 403)

    def test_regla_8_sin_lineas_pendientes_la_ficha_no_ofrece_recibir_ni_cerrar(self):
        """Regla 8: con todas las líneas completas no hay nada que recibir ni cerrar; los botones no se muestran."""
        DetalleOrdenCompra.objects.filter(orden=self.orden).update(estado_detalle_orden="completo")
        self.como(self.ana)
        pagina = self.client.get(self.ficha_url)
        self.assertNotContains(pagina, "Registrar recepción")
        self.assertNotContains(pagina, "Cerrar con faltante")

    def test_regla_5_la_ficha_muestra_lo_recibido_y_lo_que_falta_de_cada_linea(self):
        """Regla 5 de CMP-CNS-ODC: la columna «Recibida» y «Falta» de la ficha usan lo recibido de verdad (ya no 0)."""
        self.como(self.ana)
        self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        ficha = self.client.get(self.ficha_url).context["ficha"]
        linea = next(l for g in ficha.grupos for l in g.lineas if l.detalle.pk == self.l_fert.pk)
        self.assertEqual((linea.recibida, linea.pendiente), (D("4"), D("6")))

    def test_regla_2_el_atajo_por_recibir_y_las_marcas_de_la_lista(self):
        """Regla 2: el atajo «Por recibir» trae las órdenes con mercadería pendiente (con su contador) y deja de traerla cuando todo está completo."""
        self.como(self.ana)
        lista = self.client.get(reverse("compras:ordenes") + "?atajo=por_recibir")
        self.assertContains(lista, str(self.orden))
        self.assertContains(lista, "Por recibir")
        DetalleOrdenCompra.objects.filter(orden=self.orden).update(estado_detalle_orden="completo")
        self.assertNotContains(self.client.get(reverse("compras:ordenes") + "?atajo=por_recibir"), f"/ordenes/{self.orden.pk}/")

    def test_panelAgr_el_inicio_del_agronomo_muestra_la_mercaderia_por_recibir(self):
        """``panelAgr`` («Por recibir»): el inicio de Ana lista las entregas con su botón «Recibir»; el del Gerente no la tiene."""
        self.como(self.ana)
        pagina = self.client.get(reverse("core:inicio"))
        self.assertContains(pagina, 'data-kpi="por-recibir"')
        self.assertContains(pagina, "Recibir<span")
        self.como(self.gerente)
        self.assertNotContains(self.client.get(reverse("core:inicio")), 'data-kpi="por-recibir"')

    def test_enlace_el_asiento_de_la_recepcion_lleva_a_la_ficha_de_la_orden_en_el_libro_de_gestion(self):
        """Enlace asiento → documento (D-87 punto 5 y libro de gestión, «Enlace al origen»): la ficha del asiento de una recepción muestra «Recepción RCP-… · OC-…» con el enlace a la ficha de la orden."""
        self.como(self.ana)
        self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        asiento = AsientoContable.objects.get()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.como(contador)
        pagina = self.client.get(reverse("contabilidad:asiento", args=[asiento.ejercicio_id, asiento.numero_asiento]))
        self.assertContains(pagina, f"{Recepcion.objects.get()} · {self.orden}")
        self.assertContains(pagina, self.ficha_url)


class CierreConFaltanteVistaTests(VistasDeRecepcionBase):
    """«Cerrar con faltante» (pasos 1 a 8, ``VIEWS.c_flt``)."""

    def test_paso_2_la_lista_ofrece_las_lineas_pendientes_con_su_casilla_y_su_motivo(self):
        """Paso 2: cada línea pendiente de la orden con su casilla, lo pedido, lo recibido, lo que falta y un campo de motivo propio; avisa que el cierre no se deshace."""
        self.como(self.ana)
        respuesta = self.client.get(self.cerrar_url)
        for detalle in (self.l_fert, self.l_maceta, self.l_tomate):
            self.assertContains(respuesta, f'name="motivo_{detalle.pk}"')
        self.assertContains(respuesta, "no se puede volver a abrir")

    def test_ext_2a_desde_una_recepcion_solo_se_ofrecen_sus_lineas_pendientes(self):
        """Extensión 2a: con ``?recepcion=`` solo las líneas pendientes de esa recepción."""
        self.como(self.ana)
        self.recibir_post("confirmar", {self.l_fert: {"cant": "4", "venc": self.vence.isoformat()}})
        respuesta = self.client.get(f"{self.cerrar_url}?recepcion={Recepcion.objects.get().pk}")
        self.assertContains(respuesta, f'name="motivo_{self.l_fert.pk}"')
        self.assertNotContains(respuesta, f'name="motivo_{self.l_maceta.pk}"')

    def test_paso_5_el_resumen_dice_lo_que_cambia_y_no_cierra_nada(self):
        """Paso 5: el resumen con la cantidad faltante, el tránsito, el estado de la orden y que el cierre no se deshace; no escribe."""
        self.como(self.ana)
        respuesta = self.cierre_post("revisar", {self.l_maceta: "No lo fabrican más."})
        self.assertContains(respuesta, "no se deshace")
        self.assertContains(respuesta, "Confirmar cierre")
        self.assertContains(respuesta, "No lo fabrican más.")
        self.assertEqual(DetalleOrdenCompra.objects.get(pk=self.l_maceta.pk).estado_detalle_orden, "pendiente")

    def test_paso_7_confirmar_cierra_la_linea_y_la_ficha_la_muestra_con_su_motivo(self):
        """Paso 7 y 8: «Confirmar cierre» cierra la línea, baja el tránsito y lleva a la ficha, que la muestra «Cerrado con faltante» con el motivo."""
        self.como(self.ana)
        respuesta = self.cierre_post("confirmar", {self.l_maceta: "No lo fabrican más."})
        self.assertRedirects(respuesta, self.ficha_url)
        self.assertEqual(self.transito(self.maceta), D("0"))
        pagina = self.client.get(self.ficha_url)
        self.assertContains(pagina, "Cerrado con faltante")
        self.assertContains(pagina, "No lo fabrican más.")
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_ext_4a_sin_motivo_o_sin_lineas_vuelve_a_la_lista_con_el_error(self):
        """Extensión 4a y paso 3: una línea sin motivo, o ninguna línea tildada, vuelve a la lista con el mensaje y lo elegido; no cierra nada."""
        self.como(self.ana)
        respuesta = self.cierre_post("confirmar", {self.l_maceta: ""})
        self.assertContains(respuesta, "Contá por qué")
        self.assertContains(respuesta, f'value="{self.l_maceta.pk}" checked')
        self.assertContains(self.cierre_post("revisar", {}), "Elegí al menos una línea")
        self.assertEqual(DetalleOrdenCompra.objects.filter(estado_detalle_orden="cerrado_con_faltante").count(), 0)

    def test_regla_solo_los_destinos_a_cargo_y_sin_lineas_pendientes_no_hay_pantalla(self):
        """Beto, sin destinos en la orden, recibe 403 (D-28), igual que el Contador; sin líneas pendientes se vuelve a la ficha con el aviso."""
        self.como(self.beto)
        self.assertEqual(self.client.get(self.cerrar_url).status_code, 403)
        self.como(crear_cuenta(Contador, email="contador@infoponia.com"))
        self.assertEqual(self.client.get(self.cerrar_url).status_code, 403)
        DetalleOrdenCompra.objects.filter(orden=self.orden).update(estado_detalle_orden="completo")
        self.como(self.ana)
        self.assertRedirects(self.client.get(self.cerrar_url), self.ficha_url)
