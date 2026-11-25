# Pruebas de las pantallas de reclamos (CMP-06, paso 4): «Compras» → «Reclamos» (``tabRcl``), la ficha del reclamo (``VIEWS.c_rcl``) con «Emitir reclamo» y «Cerrar reclamo», la tarjeta «Reclamos sin emitir» del Inicio del
# Gerente (``panelGer``) y la tarjeta de reclamos de la ficha del proveedor. Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md (CMP-EMT-RCL reglas 2 y 4 y CMP-CRR-RCL), docs/casos_de_uso/compras/proveedores.md
# (CMP-CNS-PRV regla 4) y D-30 (ningún botón lleva a un 403). Las vistas solo orquestan: las reglas las prueban ``test_cmp_emt_rcl.py`` y ``test_cmp_crr_rcl.py``.

from django.core import mail
from django.urls import reverse

from compras.models import ReclamoProveedor
from compras.tests.base_correcciones import ReclamoBase
from core.tests.fabricas import crear_capataz
from maestros.tests.fabricas import crear_vendedor


class VistasDeReclamoBase(ReclamoBase):
    def setUp(self):
        super().setUp()
        self.lista_url = reverse("compras:reclamos")

    def como(self, usuario):
        self.client.force_login(usuario)

    def url(self, nombre, reclamo):
        return reverse(f"compras:{nombre}", args=[reclamo.pk])


class ReclamosListaTests(VistasDeReclamoBase):
    def test_la_lista_muestra_los_reclamos_con_su_proveedor_la_orden_el_inconveniente_y_el_estado(self):
        """``tabRcl``: una fila por reclamo con el proveedor, la orden, los tipos de inconveniente y el estado; la pestaña «Reclamos» está para el Gerente."""
        _, reclamo = self.recepcion_con_reclamo()
        self.como(self.gerente)
        respuesta = self.client.get(self.lista_url)
        self.assertEqual(respuesta.status_code, 200)
        for texto in (str(reclamo), self.proveedor.nombre_para_mostrar, str(self.orden), "Mercadería dañada", "Sin emitir", self.url("reclamo_ficha", reclamo)):
            self.assertContains(respuesta, texto)
        self.assertContains(self.client.get(reverse("compras:ordenes")), f'href="{self.lista_url}"')

    def test_los_filtros_separan_sin_emitir_emitidos_y_cerrados(self):
        """Los chips «Sin emitir», «Emitidos abiertos» y «Cerrados» filtran; sin reclamos con ese estado se dice."""
        _, reclamo = self.recepcion_con_reclamo()
        self.como(self.gerente)
        self.assertContains(self.client.get(self.lista_url + "?estado=sin_emitir"), str(reclamo))
        self.assertNotContains(self.client.get(self.lista_url + "?estado=emitido_abierto"), str(reclamo))
        self.assertContains(self.client.get(self.lista_url + "?estado=emitido_abierto"), "No hay reclamos con ese estado")
        self.emitir(self.gerente, reclamo)
        self.assertContains(self.client.get(self.lista_url + "?estado=emitido_abierto"), str(reclamo))
        self.cerrar(self.gerente, reclamo)
        self.assertContains(self.client.get(self.lista_url + "?estado=cerrado"), str(reclamo))

    def test_el_agronomo_no_tiene_la_pestana_y_solo_ve_los_de_sus_invernaderos(self):
        """D-30: sin pestaña para el Agrónomo; si entra por la dirección, ve solo los reclamos de sus invernaderos. Beto (Sur) no ve el de Norte. El Contador, el Vendedor y el Capataz, 403."""
        _, reclamo = self.recepcion_con_reclamo()
        self.como(self.ana)
        self.assertNotContains(self.client.get(reverse("compras:ordenes")), f'href="{self.lista_url}"')
        self.assertContains(self.client.get(self.lista_url), str(reclamo))
        self.como(self.beto)
        self.assertNotContains(self.client.get(self.lista_url), str(reclamo))
        for usuario in (self.contador, crear_vendedor(), crear_capataz()):
            with self.subTest(usuario=usuario):
                self.como(usuario)
                self.assertEqual(self.client.get(self.lista_url).status_code, 403)


class ReclamoFichaTests(VistasDeReclamoBase):
    def test_la_ficha_muestra_los_datos_y_cada_inconveniente(self):
        """Regla 2: el proveedor, la orden, la recepción, el invernadero, la emisión y cada inconveniente (tipo, cantidad y descripción)."""
        recepcion, reclamo = self.recepcion_con_reclamo()
        self.como(self.gerente)
        respuesta = self.client.get(self.url("reclamo_ficha", reclamo))
        for texto in (str(reclamo), str(recepcion), str(self.orden), self.proveedor.nombre_para_mostrar, self.norte.nombre_invernadero, "Mercadería dañada", "Cajas rotas", "Sin emitir"):
            self.assertContains(respuesta, texto)

    def test_el_gerente_ve_emitir_con_el_reclamo_sin_emitir_y_cerrar_con_el_emitido(self):
        """D-30: «Emitir reclamo» solo sin emitir; «Cerrar reclamo» solo emitido y abierto; ninguno con el reclamo cerrado; el Agrónomo no ve ninguno."""
        _, reclamo = self.recepcion_con_reclamo()
        ficha = self.url("reclamo_ficha", reclamo)
        self.como(self.gerente)
        respuesta = self.client.get(ficha)
        self.assertContains(respuesta, "Emitir reclamo")
        self.assertNotContains(respuesta, "Cerrar reclamo")
        self.assertContains(respuesta, "no se espera una devolución")
        self.emitir(self.gerente, reclamo)
        respuesta = self.client.get(ficha)
        self.assertContains(respuesta, "Cerrar reclamo")
        self.assertNotContains(respuesta, "Emitir reclamo")
        self.cerrar(self.gerente, reclamo)
        respuesta = self.client.get(ficha)
        self.assertNotContains(respuesta, "Cerrar reclamo")
        self.assertNotContains(respuesta, "Emitir reclamo")
        self.como(self.ana)
        self.assertEqual(self.client.get(ficha).status_code, 200)
        self.assertNotContains(self.client.get(ficha), "Emitir reclamo")

    def test_quien_no_ve_el_reclamo_recibe_403_o_404(self):
        """Otro Agrónomo (sin el invernadero), el Contador, el Vendedor y el Capataz: 403; un reclamo que no existe: 404."""
        _, reclamo = self.recepcion_con_reclamo()
        for usuario in (self.beto, self.contador, crear_vendedor(), crear_capataz()):
            with self.subTest(usuario=usuario):
                self.como(usuario)
                self.assertEqual(self.client.get(self.url("reclamo_ficha", reclamo)).status_code, 403)
        self.como(self.gerente)
        self.assertEqual(self.client.get(reverse("compras:reclamo_ficha", args=[reclamo.pk + 9999])).status_code, 404)


class ReclamoEmitirYCerrarTests(VistasDeReclamoBase):
    def test_emitir_registra_manda_el_correo_y_vuelve_a_la_ficha(self):
        """Emitir por POST: el reclamo queda emitido, sale el correo al proveedor, vuelve a su ficha con el aviso y la alerta del Gerente queda resuelta."""
        _, reclamo = self.recepcion_con_reclamo()
        self.como(self.gerente)
        correos = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(self.url("reclamo_emitir", reclamo))
        self.assertRedirects(respuesta, self.url("reclamo_ficha", reclamo), fetch_redirect_response=False)
        self.assertTrue(ReclamoProveedor.objects.get(pk=reclamo.pk).emitido)
        self.assertEqual(len(mail.outbox), correos + 1)
        ficha = self.client.get(self.url("reclamo_ficha", reclamo))
        self.assertContains(ficha, f"Emitimos el reclamo {reclamo}")
        self.assertContains(ficha, "Cerrar reclamo")

    def test_cerrar_por_post_cierra_y_vuelve_a_la_ficha(self):
        """Cerrar por POST: el reclamo queda cerrado, sin correo."""
        _, reclamo = self.recepcion_con_reclamo()
        self.emitir(self.gerente, reclamo)
        self.como(self.gerente)
        correos = len(mail.outbox)
        respuesta = self.client.post(self.url("reclamo_cerrar", reclamo))
        self.assertRedirects(respuesta, self.url("reclamo_ficha", reclamo), fetch_redirect_response=False)
        self.assertEqual(ReclamoProveedor.objects.get(pk=reclamo.pk).estado_reclamo, "cerrado")
        self.assertEqual(len(mail.outbox), correos)

    def test_un_error_de_negocio_vuelve_a_la_ficha_con_el_aviso(self):
        """Emitir dos veces o cerrar uno sin emitir no rompe: vuelve a la ficha con el aviso y no cambia nada."""
        _, reclamo = self.recepcion_con_reclamo()
        self.como(self.gerente)
        antes = self.instantanea_de_reclamos()
        self.assertRedirects(self.client.post(self.url("reclamo_cerrar", reclamo)), self.url("reclamo_ficha", reclamo), fetch_redirect_response=False)
        self.assertContains(self.client.get(self.url("reclamo_ficha", reclamo)), "todavía no se emitió")
        self.sin_cambios_de_reclamos(antes)
        self.emitir(self.gerente, reclamo)
        self.client.post(self.url("reclamo_emitir", reclamo))
        self.assertContains(self.client.get(self.url("reclamo_ficha", reclamo)), "ya está emitido")

    def test_solo_el_gerente_emite_y_cierra_y_solo_por_post(self):
        """Emitir y cerrar son del Gerente (403 para los demás) y solo por POST (405 con GET)."""
        _, reclamo = self.recepcion_con_reclamo()
        antes = self.instantanea_de_reclamos()
        for usuario in (self.ana, self.contador, crear_vendedor()):
            with self.subTest(usuario=usuario):
                self.como(usuario)
                self.assertEqual(self.client.post(self.url("reclamo_emitir", reclamo)).status_code, 403)
                self.assertEqual(self.client.post(self.url("reclamo_cerrar", reclamo)).status_code, 403)
        self.como(self.gerente)
        self.assertEqual(self.client.get(self.url("reclamo_emitir", reclamo)).status_code, 405)
        self.assertEqual(self.client.get(self.url("reclamo_cerrar", reclamo)).status_code, 405)
        self.sin_cambios_de_reclamos(antes)


class ReclamosEnOtrasPantallasTests(VistasDeReclamoBase):
    def test_el_inicio_del_gerente_cuenta_los_reclamos_sin_emitir_y_los_lista(self):
        """``panelGer``: la tarjeta «Reclamos sin emitir» con la cantidad y la lista «Recepciones con reclamo» con «Emitir»; sin reclamos pendientes, «al día»."""
        self.como(self.gerente)
        self.assertContains(self.client.get(reverse("core:inicio")), "Reclamos sin emitir")
        _, reclamo = self.recepcion_con_reclamo()
        inicio = self.client.get(reverse("core:inicio"))
        self.assertContains(inicio, 'data-kpi="reclamos-sin-emitir">1<')
        self.assertContains(inicio, "Recepciones con reclamo")
        self.assertContains(inicio, self.url("reclamo_ficha", reclamo))
        self.emitir(self.gerente, reclamo)
        inicio = self.client.get(reverse("core:inicio"))
        self.assertContains(inicio, 'data-kpi="reclamos-sin-emitir">0<')
        self.assertNotContains(inicio, "Recepciones con reclamo")

    def test_la_ficha_del_proveedor_muestra_sus_reclamos(self):
        """CMP-CNS-PRV regla 4: la ficha del proveedor trae sus reclamos con el estado; otro proveedor no los ve; el Agrónomo, los de sus invernaderos."""
        _, reclamo = self.recepcion_con_reclamo()
        self.como(self.gerente)
        propia = self.client.get(reverse("compras:proveedor_ficha", args=[self.proveedor.pk]))
        self.assertContains(propia, str(reclamo))
        self.assertContains(propia, "Sin emitir")
        self.assertNotContains(self.client.get(reverse("compras:proveedor_ficha", args=[self.proveedor_b.pk])), str(reclamo))
        self.como(self.beto)
        self.assertNotContains(self.client.get(reverse("compras:proveedor_ficha", args=[self.proveedor.pk])), str(reclamo))
