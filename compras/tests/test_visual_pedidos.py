# Verificación VISUAL de «Compras» → «Pedidos» y del portal del proveedor (CMP-02a), con un navegador real (Playwright + Chromium) contra el sistema levantado de verdad en su propia base de pruebas.
# Cubre lo que las pruebas con el cliente de Django no ven: que el formulario de «Nuevo pedido» y el portal se vean bien y funcionen (el botón que dispara Enter, el rótulo del precio que cambia con
# JavaScript y el respaldo sin él), que no haya errores de consola y que en un celular no se desborde. Deja capturas en ``INFOPONIA_CAPTURAS`` (o ``infoponia_capturas`` en la carpeta temporal), que se
# miran a ojo. Se corre aparte: ``INFOPONIA_VISUAL=1 python manage.py test compras.tests.test_visual_pedidos --tag visual`` (docs/patrones/verificacion_por_claude.md). Sin Playwright, se saltan.

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from compras.models import EnlaceProveedor
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor, tipo_de_insumo
from compras.tests.fabricas import pedido as armar_pedido
from core.tests.fabricas import crear_gerente
from core.tests.visual import ANCHO_DE_CELULAR, PruebaVisual
from inventario.tests.fabricas import asegurar_datos_de_inventario, existencia, insumo, lote
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef, crear_agronomo, crear_invernadero


@override_settings(CORREO_CONFIGURADO=True)
class PedidosVisualTests(PruebaVisual):
    """Fuente: docs/casos_de_uso/compras/pedidos.md (CMP-RLZ-PED, CMP-ENV-COT y CMP-CNS-PED), D-24, D-29, D-30 y interfaz.md."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        self.gerente = crear_gerente()
        self.ana = crear_agronomo()
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        semillas = tipo_de_insumo("Semillas y plantines")
        self.lechuga = existencia(insumo("Lechuga", tipo=semillas, unidad="unidad", descripcion="Plantín"), self.norte, minimo=20, precio="12.50")
        lote(self.lechuga, 5)
        self.nutriente = existencia(insumo("Nutriente", unidad="kg"), self.norte, minimo=5, precio="100.00")
        lote(self.nutriente, 2)
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com", especialidades=[semillas])
        self.este = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        # Un pedido ya hecho con un invitado que cotizó y otro que no, para la ficha y el portal.
        self.pedido = armar_pedido(self.ana, dias_al_limite=3)
        self.d_lechuga = detalle_de_pedido(self.pedido, self.lechuga, cantidad="20")
        self.d_nutriente = detalle_de_pedido(self.pedido, self.nutriente, cantidad="3")
        self.enlace_sur, self.token_sur = enlace_de(invitar(self.pedido, self.sur), envio="enviado")
        self.enlace_este, self.token_este = enlace_de(invitar(self.pedido, self.este), envio="enviado")

    def assertSinTarjetasCortadas(self, pagina):
        """Ninguna tarjeta ni sección se sale del ancho de la ventana (un contenido ancho puede hacer scroll adentro de su propio contenedor y dejar la página «sin scroll horizontal»
        con el borde derecho cortado: lo vio la captura de la ficha en un celular)."""
        mayor = pagina.evaluate("() => Math.max(0, ...[...document.querySelectorAll('.card, .sec')].map(e => e.getBoundingClientRect().right))")
        self.assertLessEqual(mayor, pagina.evaluate("() => window.innerWidth"), "Hay una tarjeta que se sale del ancho de la pantalla")

    def abrir_portal(self, pagina, token):
        pagina.goto(f"{self.live_server_url}/proveedor/{token}/")
        pagina.wait_for_load_state("networkidle")

    def test_el_agronomo_arma_un_pedido_lo_revisa_y_lo_confirma(self):
        """CMP-RLZ-PED pasos 2 a 13: bajo el mínimo → agregar → cantidad → proveedores → fecha → resumen → confirmar; Enter dispara «Revisar» y no «Agregar»."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.ana)
        pagina.goto(self.url("compras:pedidos"))
        self.capturar(pagina, "pedidos_01_lista")
        pagina.get_by_role("link", name="Nuevo pedido").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("Insumos bajo el mínimo", pagina.inner_text("body"))
        self.capturar(pagina, "pedidos_02_nuevo_vacio")

        pagina.locator("button[value='agregar:%d']" % self.lechuga.pk).click()
        pagina.wait_for_load_state("networkidle")
        pagina.locator("button[value='agregar:%d']" % self.nutriente.pk).click()
        pagina.wait_for_load_state("networkidle")
        cantidades = pagina.locator("input[name=detalle_cantidad]")
        self.assertEqual(cantidades.count(), 2)
        self.assertEqual(cantidades.nth(0).input_value(), "15")  # la sugerida
        # El primer botón del formulario es «Revisar»: Enter en un campo no agrega ni quita nada.
        cantidades.nth(1).fill("3")
        pagina.locator("label.prv-categoria", has_text="Semillas del Sur").locator("input").check()
        self.capturar(pagina, "pedidos_03_nuevo_armado")
        cantidades.nth(1).press("Enter")
        pagina.wait_for_load_state("networkidle")
        self.assertIn("Revisá el pedido", pagina.inner_text("body"))
        self.assertIn("Confirmar pedido", pagina.inner_text("body"))
        self.capturar(pagina, "pedidos_04_resumen")

        pagina.get_by_role("button", name="Confirmar pedido").click()
        pagina.wait_for_load_state("networkidle")
        self.assertRegex(pagina.url, r"/compras/pedidos/\d+/$")
        self.assertIn("Enviamos el pedido", pagina.inner_text("body"))
        self.capturar(pagina, "pedidos_05_ficha_recien_hecho")
        self.assertSinErroresDeJavaScript()

    def test_los_errores_del_pedido_aparecen_junto_a_cada_campo(self):
        """CMP-RLZ-PED 4a, 8a y 8b: errores por campo, con lo escrito conservado."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.ana)
        pagina.goto(self.url("compras:pedido_nuevo") + f"?iin={self.lechuga.pk}")
        pagina.fill("input[name=detalle_cantidad]", "0")
        pagina.fill("#fecha_limite", timezone.localdate().isoformat())
        pagina.get_by_role("button", name="Revisar pedido").click()
        pagina.wait_for_load_state("networkidle")
        self.assertGreaterEqual(pagina.locator(".err").count(), 3)
        self.assertEqual(pagina.input_value("input[name=detalle_cantidad]"), "0")
        self.capturar(pagina, "pedidos_06_nuevo_con_errores")
        self.assertSinErroresDeJavaScript()

    def test_el_agronomo_habilita_un_insumo_desde_el_pedido(self):
        """CMP-RLZ-PED 3a.1a: la ventana «Habilitarlo» se abre sola con errores y deja el insumo en el pedido."""
        insumo("Sustrato", unidad="kg")
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.ana)
        pagina.goto(self.url("compras:pedido_nuevo"))
        pagina.locator("details.ped-habilitar summary").click()
        self.assertTrue(pagina.locator("#hab_minimo").is_visible())
        self.capturar(pagina, "pedidos_07_habilitar_abierto")

    def test_la_lista_y_la_ficha_del_gerente_no_traen_botones_de_cambio(self):
        """CMP-CNS-PED: el Gerente consulta en modo consulta; la ficha muestra la cotización recibida en solo lectura."""
        cotizacion_de(self.pedido, self.sur, [(self.d_lechuga, 20, "250.00", 3), (self.d_nutriente, 3, "120.30", 2)], observaciones="Entrega en cajones")
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.gerente)
        pagina.goto(self.url("compras:pedidos"))
        self.assertEqual(pagina.get_by_role("link", name="Nuevo pedido").count(), 0)
        self.assertIn("modo consulta", pagina.inner_text("body"))
        self.capturar(pagina, "pedidos_08_lista_del_gerente")
        pagina.goto(self.url("compras:pedido_ficha", self.pedido.pk))
        self.assertIn("Cotizaciones recibidas", pagina.inner_text("body"))
        self.assertEqual(pagina.get_by_role("button", name="Cancelar pedido").count(), 0)
        self.capturar(pagina, "pedidos_09_ficha_del_gerente")
        self.assertSinErroresDeJavaScript()

    def test_el_proveedor_cotiza_en_el_portal_y_el_rotulo_del_precio_sigue_la_eleccion(self):
        """CMP-ENV-COT: abrir, elegir cómo carga el precio (JavaScript cambia el rótulo), revisar, enviar y ver la cotización en solo lectura."""
        pagina = self.nueva_pagina()
        self.abrir_portal(pagina, self.token_sur)
        self.assertNotIn(self.token_sur, pagina.url)
        self.assertTrue(pagina.get_by_text("Pedido de cotización").first.is_visible())
        self.assertNotIn("12,50", pagina.inner_text("body"))
        self.capturar(pagina, "portal_01_formulario")
        etiqueta = pagina.locator("[data-etiqueta-precio]").first
        self.assertIn("Precio total", etiqueta.inner_text())
        pagina.locator("input[name=modo][value=unitario]").check()
        self.assertIn("Precio unitario", etiqueta.inner_text())
        pagina.locator("input[name=modo][value=total]").check()
        pagina.fill(f"#cantidad_{self.d_lechuga.pk}", "20")
        pagina.fill(f"#precio_{self.d_lechuga.pk}", "250")
        pagina.fill(f"#plazo_{self.d_lechuga.pk}", "3")
        pagina.get_by_role("button", name="Revisar y enviar").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("una sola vez", pagina.inner_text("body"))
        self.capturar(pagina, "portal_02_resumen")
        pagina.get_by_role("button", name="Enviar cotización").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("Recibimos su cotización", pagina.inner_text("body"))
        self.assertIn("Ya envió su cotización", pagina.inner_text("body"))
        self.capturar(pagina, "portal_03_enviada")
        self.assertSinErroresDeJavaScript()

    def test_el_portal_muestra_los_errores_y_no_sirve_con_el_enlace_vencido(self):
        """CMP-ENV-COT 6a a 9a y 2a: errores junto a cada campo; un enlace vencido da la pantalla con el motivo y sin datos."""
        pagina = self.nueva_pagina()
        self.abrir_portal(pagina, self.token_sur)
        pagina.fill(f"#cantidad_{self.d_lechuga.pk}", "0")
        pagina.get_by_role("button", name="Revisar y enviar").click()
        pagina.wait_for_load_state("networkidle")
        self.assertGreaterEqual(pagina.locator(".err").count(), 2)
        self.capturar(pagina, "portal_04_errores")
        self.pedido.__class__.objects.filter(pk=self.pedido.pk).update(fecha_pedido=timezone.localdate() - timedelta(days=8), fecha_limite_cotizaciones=timezone.localdate() - timedelta(days=1))
        otra = self.nueva_pagina()
        self.abrir_portal(otra, self.token_este)
        self.assertIn("Este enlace no se puede usar", otra.inner_text("body"))
        self.assertNotIn("Lechuga", otra.inner_text("body"))
        self.capturar(otra, "portal_05_vencido")
        token_malo = self.nueva_pagina()
        token_malo.goto(f"{self.live_server_url}/proveedor/no-existe/")
        self.assertIn("Este enlace no es válido", token_malo.inner_text("body"))

    def test_en_un_celular_no_se_desborda(self):
        """Interfaz: sin scroll horizontal en un celular, en la lista, la ficha, «Nuevo pedido» y el portal (formulario, resumen y solo lectura)."""
        cotizacion_de(self.pedido, self.sur, [(self.d_lechuga, 20, "250.00", 3)])
        pagina = self.nueva_pagina(viewport=ANCHO_DE_CELULAR)
        self.entrar(pagina, self.ana)
        for nombre, argumentos in (("compras:pedidos", ()), ("compras:pedido_ficha", (self.pedido.pk,)), ("compras:pedido_nuevo", ())):
            pagina.goto(self.url(nombre, *argumentos))
            self.assertSinScrollHorizontal(pagina)
            self.assertSinTarjetasCortadas(pagina)
            self.capturar(pagina, f"pedidos_celular_{nombre.split(':')[1]}")
        portal = self.nueva_pagina(viewport=ANCHO_DE_CELULAR)
        self.abrir_portal(portal, self.token_este)
        self.assertSinScrollHorizontal(portal)
        self.assertSinTarjetasCortadas(portal)
        self.capturar(portal, "portal_celular_formulario")
        portal.fill(f"#cantidad_{self.d_lechuga.pk}", "20")
        portal.fill(f"#precio_{self.d_lechuga.pk}", "250")
        portal.fill(f"#plazo_{self.d_lechuga.pk}", "3")
        portal.get_by_role("button", name="Revisar y enviar").click()
        portal.wait_for_load_state("networkidle")
        self.assertSinScrollHorizontal(portal)
        self.assertSinTarjetasCortadas(portal)
        self.capturar(portal, "portal_celular_resumen")
        EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(estado="usado", fecha_uso=timezone.now())  # el proveedor ya cotizó: el enlace queda «usado»
        solo_lectura = self.nueva_pagina(viewport=ANCHO_DE_CELULAR)
        self.abrir_portal(solo_lectura, self.token_sur)
        self.assertIn("Ya envió su cotización", solo_lectura.inner_text("body"))
        self.assertSinScrollHorizontal(solo_lectura)
        self.assertSinTarjetasCortadas(solo_lectura)
        self.capturar(solo_lectura, "portal_celular_solo_lectura")
        self.assertSinErroresDeJavaScript()

    def test_sin_javascript_el_pedido_y_el_portal_siguen_funcionando(self):
        """Respaldo sin JavaScript: «Nuevo pedido» se arma con sus botones y el portal envía la cotización."""
        pagina = self.nueva_pagina(javascript=False)
        self.entrar(pagina, self.ana)
        pagina.goto(self.url("compras:pedido_nuevo") + f"?iin={self.lechuga.pk}")
        pagina.locator("label.prv-categoria", has_text="Semillas del Sur").locator("input").check()
        pagina.get_by_role("button", name="Revisar pedido").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("Confirmar pedido", pagina.inner_text("body"))
        self.capturar(pagina, "pedidos_10_sin_javascript_resumen")
        portal = self.nueva_pagina(javascript=False)
        self.abrir_portal(portal, self.token_este)
        portal.fill(f"#cantidad_{self.d_lechuga.pk}", "20")
        portal.fill(f"#precio_{self.d_lechuga.pk}", "250")
        portal.fill(f"#plazo_{self.d_lechuga.pk}", "3")
        portal.get_by_role("button", name="Revisar y enviar").click()
        portal.wait_for_load_state("networkidle")
        portal.get_by_role("button", name="Enviar cotización").click()
        portal.wait_for_load_state("networkidle")
        self.assertIn("Ya envió su cotización", portal.inner_text("body"))
        self.capturar(portal, "portal_06_sin_javascript_enviada")
