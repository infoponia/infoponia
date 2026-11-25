# Pruebas de las pantallas del pago a proveedores (CMP-05, paso 4): «Pagos a proveedores» (bandeja y registrados), el formulario con su resumen, la entrada del menú, la sección del Inicio del
# responsable contable, la sección «Pagos» de la ficha de la orden, el atajo «Con pago pendiente» de la lista de órdenes y la columna «Pago» de la ficha del proveedor. Fuente:
# docs/casos_de_uso/compras/pagos.md (flujo básico pasos 1 a 10; extensiones 1a, 2a, 5a, 5b y 8a), D-91 puntos 2 y 6, D-87 punto 6, D-30 (ningún botón lleva a un 403), CMP-CNS-ODC reglas 2, 3, 7 y 8
# y CMP-CNS-PRV regla 4. Con el cliente de Django: el CSRF y el JavaScript los cubre el paso de «navegador real» de la «Verificación a mano».

from datetime import timedelta

from django.core import mail
from django.urls import reverse

from compras.models import Pago
from compras.servicios import ordenes as servicio_de_ordenes
from compras.tests.base_pagos import PagosBase
from core.menu import menu_de
from core.models import Usuario
from maestros.tests.fabricas import crear_vendedor


class PagosVistasBase(PagosBase):
    """Las URLs y los auxiliares de las pantallas."""

    def setUp(self):
        super().setUp()
        self.lista = reverse("compras:pagos")

    def formulario(self, proveedor=None, orden=None):
        return reverse("compras:pago_nuevo", args=[(orden or self.orden).pk, (proveedor or self.proveedor).pk])

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def enviar(self, accion, medio="transferencia", fecha=None, proveedor=None, orden=None, **extra):
        datos = {"accion": accion, "fecha": (fecha or self.hoy).isoformat(), **extra}
        if medio is not None:
            datos["medio_pago"] = medio
        return self.client.post(self.formulario(proveedor, orden), datos)


class MenuYBandejaTests(PagosVistasBase):
    """Paso 1 y 2, regla 1a y D-87 punto 6: quién entra y qué ve."""

    def test_d87_la_entrada_del_menu_es_del_contador_y_del_gerente_y_va_despues_de_contabilidad(self):
        """D-87 punto 6: «Pagos a proveedores» la registra `compras` junto a «Contabilidad» para quien puede registrar o mirar pagos; el Agrónomo y el Vendedor no la tienen."""
        for rol in (Usuario.Rol.CONTADOR, Usuario.Rol.GERENTE):
            with self.subTest(rol=rol):
                textos = [texto for texto, _, _ in menu_de(rol)]
                self.assertIn("Pagos a proveedores", textos)
                self.assertEqual(textos.index("Pagos a proveedores"), textos.index("Contabilidad") + 1)
        for rol in (Usuario.Rol.AGRONOMO, Usuario.Rol.VENDEDOR):
            self.assertNotIn("Pagos a proveedores", [texto for texto, _, _ in menu_de(rol)])

    def test_paso_2_el_contador_ve_el_pago_pendiente_con_su_monto_y_el_boton_para_registrarlo(self):
        """Paso 2: proveedor, orden, listo desde, líneas y monto; con «Registrar pago»."""
        self.recibir_a()
        self.entrar(self.contador)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, self.proveedor.nombre_para_mostrar)
        self.assertContains(respuesta, str(self.orden))
        self.assertContains(respuesta, "300,00")
        self.assertContains(respuesta, f'href="{self.formulario()}"')
        self.assertContains(respuesta, "Registrar pago")

    def test_ext_2a_sin_pagos_pendientes_la_bandeja_lo_informa(self):
        """Extensión 2a: «el Sistema informa que no hay proveedores para pagar»."""
        self.entrar(self.contador)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, "No hay proveedores para pagar")
        self.assertContains(respuesta, "Todavía no se registró ningún pago")

    def test_la_bandeja_lista_tambien_los_pagos_registrados(self):
        """Los pagos registrados: fecha, pago, proveedor, orden, medio y monto; el par pagado ya no figura entre los pendientes."""
        self.recibir_a()
        pago = self.pagar(medio="efectivo")
        self.entrar(self.contador)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, f"PAG-{pago.pk:04d}")
        self.assertContains(respuesta, "Efectivo")
        self.assertContains(respuesta, "No hay proveedores para pagar")
        self.assertNotContains(respuesta, f'href="{self.formulario()}"')

    def test_ext_1a_el_gerente_con_contador_activo_ve_la_bandeja_sin_botones(self):
        """D-91 punto 6 y D-30: el Gerente con un Contador activo la mira en solo lectura: ningún botón ni enlace lleva al formulario (que sería un 403)."""
        self.recibir_a()
        self.entrar(self.gerente)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, self.proveedor.nombre_para_mostrar)
        self.assertContains(respuesta, "Los pagos los registra el Contador")
        self.assertNotContains(respuesta, "Registrar pago")
        self.assertNotContains(respuesta, self.formulario())

    def test_ext_1a_el_gerente_sin_contador_activo_ve_el_boton(self):
        self.recibir_a()
        self.sin_contador()
        self.entrar(self.gerente)
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, f'href="{self.formulario()}"')
        self.assertNotContains(respuesta, "Los pagos los registra el Contador")

    def test_pre_a_los_demas_roles_no_entran(self):
        """Precondición a: el Agrónomo y el Vendedor reciben 403 en la bandeja y en el formulario; sin sesión, al inicio de sesión."""
        self.recibir_a()
        for usuario in (self.ana, crear_vendedor()):
            with self.subTest(usuario=usuario):
                self.entrar(usuario)
                self.assertEqual(self.client.get(self.lista).status_code, 403)
                self.assertEqual(self.client.get(self.formulario()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.lista).status_code, 302)

    def test_ext_1a_el_gerente_con_contador_activo_no_abre_el_formulario(self):
        """Extensión 1a.3: con un Contador activo el Gerente recibe 403 en el formulario y el POST no registra nada."""
        self.recibir_a()
        self.entrar(self.gerente)
        self.assertEqual(self.client.get(self.formulario()).status_code, 403)
        self.assertEqual(self.enviar("confirmar").status_code, 403)
        self.assertEqual(Pago.objects.count(), 0)


class FormularioDelPagoTests(PagosVistasBase):
    """Pasos 3 a 10: el detalle, el medio sin preselección, el resumen y la confirmación."""

    def setUp(self):
        super().setUp()
        self.recibir_a()
        self.entrar(self.contador)

    def test_paso_4_el_formulario_muestra_el_detalle_el_medio_sin_preseleccion_y_la_fecha_de_hoy(self):
        """Pasos 4 y 5 y extensión 5a (H23): el detalle por línea y el monto; los cuatro medios y **ninguno elegido**; la fecha, hoy. No hay campo de comprobante (el modelo no lo tiene)."""
        respuesta = self.client.get(self.formulario())
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Fertilizante", "Maceta", "300,00", "Efectivo", "Transferencia", "Tarjeta de débito", "Tarjeta de crédito"):
            self.assertContains(respuesta, texto)
        self.assertNotContains(respuesta, "checked")
        self.assertContains(respuesta, f'value="{self.hoy.isoformat()}"')
        self.assertNotContains(respuesta, "comprobante")

    def test_ext_5a_sin_elegir_el_medio_se_pide_y_no_se_registra_nada(self):
        """Extensión 5a: «Elegí el medio de pago.»; tanto en «Ver resumen» como en «Confirmar»."""
        for accion in ("revisar", "confirmar"):
            with self.subTest(accion=accion):
                respuesta = self.enviar(accion, medio=None)
                self.assertContains(respuesta, "Elegí el medio de pago.")
        self.assertEqual(Pago.objects.count(), 0)

    def test_paso_6_el_resumen_dice_el_monto_el_medio_y_el_asiento_sin_registrar_nada(self):
        """Paso 6: monto, medio, fecha y el asiento (Debe Proveedores / Haber Banco c/c); no escribe."""
        respuesta = self.enviar("revisar", medio="transferencia")
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Confirmá el pago", "300,00", "Debe Proveedores", "Haber Banco c/c", "no se anula"):
            self.assertContains(respuesta, texto)
        self.assertEqual(Pago.objects.count(), 0)
        efectivo = self.enviar("revisar", medio="efectivo")
        self.assertContains(efectivo, "Haber Caja")

    def test_paso_7_a_10_confirmar_registra_el_pago_y_vuelve_a_la_bandeja_con_el_aviso_del_asiento(self):
        """Pasos 7 a 10: el pago queda registrado, el proveedor recibe el correo y el Contador ve el aviso con el asiento generado; vuelve a la bandeja, ya sin ese proveedor."""
        antes = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.enviar("confirmar", medio="transferencia")
        self.assertRedirects(respuesta, self.lista, fetch_redirect_response=False)
        pago = Pago.objects.get()
        self.assertEqual((pago.monto_pago, pago.medio_pago), (300, "transferencia"))
        seguimiento = self.client.get(self.lista)
        self.assertContains(seguimiento, f"Registramos el pago PAG-{pago.pk:04d}")
        self.assertContains(seguimiento, "Asiento N.º")
        self.assertContains(seguimiento, "No hay proveedores para pagar")
        self.assertEqual(len(mail.outbox), antes + 1)

    def test_ext_5b_una_fecha_futura_vuelve_al_formulario_con_el_motivo(self):
        """Extensión 5b: la fecha posterior a hoy se rechaza con un mensaje que explica el motivo; el formulario conserva el medio."""
        manana = self.hoy + timedelta(days=1)
        for accion in ("revisar", "confirmar"):
            with self.subTest(accion=accion):
                respuesta = self.enviar(accion, fecha=manana)
                self.assertContains(respuesta, "no admite un asiento")
                self.assertContains(respuesta, 'value="transferencia" checked')
        self.assertEqual(Pago.objects.count(), 0)

    def test_ext_5b_una_fecha_mal_escrita_se_rechaza(self):
        respuesta = self.client.post(self.formulario(), {"accion": "revisar", "medio_pago": "efectivo", "fecha": "no es una fecha"})
        self.assertContains(respuesta, "Escribí la fecha como una fecha válida.")

    def test_el_boton_cambiar_vuelve_al_formulario_con_lo_elegido(self):
        respuesta = self.enviar("editar", medio="tarjeta_credito")
        self.assertContains(respuesta, 'value="tarjeta_credito" checked')

    def test_ext_8a_un_par_ya_pagado_lleva_a_la_ficha_de_la_orden_con_el_aviso(self):
        """Extensión 8a: otro usuario ya lo registró: se informa y se muestra cuál (la ficha de la orden); no se registra nada nuevo."""
        pago = self.pagar()
        for respuesta in (self.client.get(self.formulario()), self.enviar("confirmar")):
            self.assertRedirects(respuesta, reverse("compras:orden_ficha", args=[self.orden.pk]), fetch_redirect_response=False)
        seguimiento = self.client.get(reverse("compras:orden_ficha", args=[self.orden.pk]))
        self.assertContains(seguimiento, f"PAG-{pago.pk:04d}")
        self.assertEqual(Pago.objects.count(), 1)

    def test_pre_b_un_proveedor_que_todavia_tiene_lineas_pendientes_lleva_a_la_ficha(self):
        """Precondición b: B no está listo: se informa y se lleva a la ficha de la orden."""
        respuesta = self.client.get(self.formulario(self.proveedor_b))
        self.assertRedirects(respuesta, reverse("compras:orden_ficha", args=[self.orden.pk]), fetch_redirect_response=False)

    def test_un_proveedor_ajeno_o_una_orden_inexistente_dan_404(self):
        from compras.tests.fabricas import proveedor as crear_proveedor

        self.assertEqual(self.client.get(self.formulario(crear_proveedor("Ajeno S. A.", n=9))).status_code, 404)
        self.assertEqual(self.client.get(reverse("compras:pago_nuevo", args=[999999, self.proveedor.pk])).status_code, 404)

    def test_el_gerente_sin_contador_registra_y_queda_en_la_auditoria(self):
        """Extensión 1a: sin Contador activo el Gerente registra el pago desde las mismas pantallas."""
        self.sin_contador()
        self.entrar(self.gerente)
        self.assertRedirects(self.enviar("confirmar", medio="efectivo"), self.lista)
        self.assertEqual(Pago.objects.get().medio_pago, "efectivo")


class InicioFichaYListaTests(PagosVistasBase):
    """La sección del Inicio, la ficha de la orden, el atajo de la lista y la ficha del proveedor."""

    def inicio(self):
        return self.client.get(reverse("core:inicio"))

    def test_la_seccion_del_inicio_la_ve_el_contador_con_un_boton_para_pagar(self):
        """D-91 punto 6 (H23): «Pagos a proveedores pendientes» en el Inicio del Contador, con «Pagar»."""
        self.recibir_a()
        self.entrar(self.contador)
        respuesta = self.inicio()
        self.assertContains(respuesta, "Pagos a proveedores pendientes")
        self.assertContains(respuesta, self.proveedor.nombre_para_mostrar)
        self.assertContains(respuesta, f'href="{self.formulario()}"')

    def test_la_seccion_del_inicio_del_gerente_solo_aparece_sin_contador_activo(self):
        """D-85 punto 5: el Gerente con un Contador activo no la ve; sin Contador activo, sí."""
        self.recibir_a()
        self.entrar(self.gerente)
        self.assertNotContains(self.inicio(), "Pagos a proveedores pendientes")
        self.sin_contador()
        self.assertContains(self.inicio(), "Pagos a proveedores pendientes")

    def test_la_seccion_del_inicio_sin_pagos_dice_que_esta_al_dia(self):
        self.entrar(self.contador)
        self.assertContains(self.inicio(), "No hay pagos pendientes.")

    def test_el_agronomo_no_ve_la_seccion_de_pagos(self):
        self.recibir_a()
        self.entrar(self.ana)
        self.assertNotContains(self.inicio(), "Pagos a proveedores pendientes")

    def test_regla_7_de_cmp_cns_odc_la_ficha_muestra_el_pago_pendiente_el_pagado_y_el_que_no_esta_listo(self):
        """Regla 7: por proveedor, el pago o que está pendiente. A está pendiente (con «Registrar pago» para el Contador); B, todavía sin estar para pagar; y pagado A, se ve su pago."""
        self.recibir_a()
        self.entrar(self.contador)
        ficha = reverse("compras:orden_ficha", args=[self.orden.pk])
        respuesta = self.client.get(ficha)
        self.assertContains(respuesta, "Pendiente de pago")
        self.assertContains(respuesta, "Todavía no está para pagar")
        self.assertContains(respuesta, f'href="{self.formulario()}"')
        self.assertNotContains(respuesta, f'href="{self.formulario(self.proveedor_b)}"')
        pago = self.pagar()
        respuesta = self.client.get(ficha)
        self.assertContains(respuesta, "Pagado")
        self.assertContains(respuesta, f"PAG-{pago.pk:04d}")
        self.assertNotContains(respuesta, f'href="{self.formulario()}"')

    def test_regla_8_de_cmp_cns_odc_el_boton_registrar_pago_solo_lo_ve_quien_puede_registrar(self):
        """Regla 8 y D-30: el Gerente con Contador activo y el Agrónomo ven el estado del pago pero no el botón."""
        self.recibir_a()
        ficha = reverse("compras:orden_ficha", args=[self.orden.pk])
        for usuario in (self.gerente, self.ana):
            with self.subTest(usuario=usuario):
                self.entrar(usuario)
                respuesta = self.client.get(ficha)
                self.assertContains(respuesta, "Pendiente de pago")
                self.assertNotContains(respuesta, self.formulario())
        self.sin_contador()
        self.entrar(self.gerente)
        self.assertContains(self.client.get(ficha), f'href="{self.formulario()}"')

    def test_una_orden_sin_recepciones_no_tiene_seccion_de_pagos(self):
        self.entrar(self.contador)
        self.assertNotContains(self.client.get(reverse("compras:orden_ficha", args=[self.orden.pk])), 'id="pagos"')

    def test_regla_2_el_atajo_con_pago_pendiente_trae_las_ordenes_con_un_proveedor_para_pagar(self):
        """Regla 2 de CMP-CNS-ODC: «con pago pendiente». Una orden con A para pagar entra; otra sin nada recibido, no; y pagado A, sale."""
        self.otra_orden(self.ana, self.norte, "Sustrato", n=5)  # otra orden aprobada sin nada recibido: no está para pagar
        self.recibir_a()
        for actor in (self.contador, self.gerente):
            filas = servicio_de_ordenes.consultar_ordenes(actor, {"atajo": "con_pago_pendiente"})
            self.assertEqual([f.orden.pk for f in filas], [self.orden.pk])
            self.assertEqual(filas[0].pagos_pendientes, 1)
        self.pagar()
        self.assertEqual(servicio_de_ordenes.consultar_ordenes(self.contador, {"atajo": "con_pago_pendiente"}), [])

    def test_regla_3_la_lista_marca_las_ordenes_con_pago_pendiente_y_ofrece_el_atajo(self):
        """Regla 3: la marca «Pago pendiente» en la fila y el atajo «Con pago pendiente» con su cantidad."""
        self.recibir_a()
        self.entrar(self.contador)
        respuesta = self.client.get(reverse("compras:ordenes"))
        self.assertContains(respuesta, "Pago pendiente")
        self.assertContains(respuesta, "Con pago pendiente")
        filtrada = self.client.get(reverse("compras:ordenes") + "?atajo=con_pago_pendiente")
        self.assertContains(filtrada, str(self.orden))
        self.pagar()
        self.assertNotContains(self.client.get(reverse("compras:ordenes")), 'status-info">Pago pendiente')

    def test_regla_4_de_cmp_cns_prv_la_ficha_del_proveedor_muestra_el_pago_de_cada_orden(self):
        """Regla 4: la tarjeta «Órdenes de compra» de la ficha suma la columna «Pago»: pendiente y, después, pagado con su fecha, medio y monto."""
        self.recibir_a()
        self.recibir_b()
        self.entrar(self.gerente)
        ficha = reverse("compras:proveedor_ficha", args=[self.proveedor.pk])
        self.assertContains(self.client.get(ficha), "Pendiente de pago")
        self.pagar(medio="tarjeta_debito")
        respuesta = self.client.get(ficha)
        self.assertContains(respuesta, "Pagado")
        self.assertContains(respuesta, "Tarjeta de débito")

    def test_pre_d_la_ventana_de_baja_del_proveedor_explica_el_pago_pendiente_y_enlaza_la_orden(self):
        """CMP-BAJ-PRV precondición d y regla 2: la ventana no ofrece confirmar y dice qué lo impide y cómo resolverlo, con el enlace a la orden."""
        self.recibir_a()
        self.recibir_b()
        self.entrar(self.gerente)
        respuesta = self.client.get(reverse("compras:proveedor_baja", args=[self.proveedor.pk]))
        self.assertContains(respuesta, "Tiene un pago pendiente de la orden de compra")
        self.assertContains(respuesta, reverse("compras:orden_ficha", args=[self.orden.pk]))
        self.assertContains(respuesta, "Ver la orden")
