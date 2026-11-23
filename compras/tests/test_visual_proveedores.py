# Verificación VISUAL de «Compras» → «Proveedores» (CMP-01), con un navegador real (Playwright + Chromium) contra el sistema levantado de verdad en su propia base de pruebas.
# Cubre lo que las pruebas con el cliente de Django no ven: que el JavaScript funcione (buscador de categorías, campos según el tipo, ventana de la baja con HTMX), que no
# haya errores de consola, que el respaldo sin JavaScript funcione y que en un celular no se desborde. Deja capturas en ``INFOPONIA_CAPTURAS`` (o ``infoponia_capturas`` en la carpeta
# temporal). Se corre aparte: ``INFOPONIA_VISUAL=1 python manage.py test compras.tests.test_visual_proveedores --tag visual`` (docs/patrones/verificacion_por_claude.md). Sin Playwright, se saltan.

from compras.tests.fabricas import cuit_valido, proveedor, tipo_de_insumo
from core.tests.fabricas import crear_gerente
from core.tests.visual import ANCHO_DE_CELULAR, PruebaVisual
from inventario.models import TipoInsumo
from inventario.tests.fabricas import asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_agronomo


class ProveedoresVisualTests(PruebaVisual):
    """Fuente: docs/casos_de_uso/compras/proveedores.md (los cuatro casos de uso), D-24, D-29 y D-30."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.nutrientes = tipo_de_insumo("Nutrientes")
        self.herramientas = tipo_de_insumo("Herramientas")
        self.envases = tipo_de_insumo("Envases de campo")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, telefono="376 400-1001", especialidades=[self.nutrientes])
        self.norte = proveedor("Agro Norte S. R. L.", n=2, activo=False)

    def test_el_gerente_recorre_la_lista_el_alta_y_la_baja(self):
        """CMP-ALT-PRV y CMP-BAJ-PRV: la lista, el alta con el buscador de categorías y los campos según el tipo, y la baja con su ventana, con un navegador real."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.gerente)
        pagina.goto(self.url("compras:proveedores"))
        self.assertTrue(pagina.get_by_role("link", name="Nuevo proveedor").is_visible())
        self.assertTrue(pagina.get_by_text("Semillas del Sur S. A.").first.is_visible())
        self.assertEqual(pagina.get_by_text("Agro Norte S. R. L.").count(), 0)  # solo los activos
        self.capturar(pagina, "compras_01_lista")

        # Alta: los campos según el tipo (con JavaScript se muestra solo lo que corresponde).
        pagina.get_by_role("link", name="Nuevo proveedor").click()
        pagina.wait_for_load_state("networkidle")
        self.assertTrue(pagina.locator("[data-grupo-tipo=juridica]").is_visible())
        self.assertFalse(pagina.locator("[data-grupo-tipo=fisica]").is_visible())
        pagina.locator("input[data-tipo][value=fisica]").check()
        self.assertFalse(pagina.locator("[data-grupo-tipo=juridica]").is_visible())
        self.assertTrue(pagina.locator("[data-grupo-tipo=fisica]").is_visible())
        pagina.locator("input[data-tipo][value=juridica]").check()
        self.assertTrue(pagina.locator("[data-grupo-tipo=juridica]").is_visible())

        # Buscador de categorías: oculta las que no coinciden y no pierde las marcadas.
        buscador = pagina.locator("[data-buscar-categoria]")
        self.assertTrue(buscador.is_visible())
        pagina.locator("label.prv-categoria", has_text="Nutrientes").locator("input").check()
        buscador.fill("herr")
        visibles = [pagina.locator("label.prv-categoria").nth(i).is_visible() for i in range(pagina.locator("label.prv-categoria").count())]
        self.assertEqual(sum(visibles), 1)
        self.assertTrue(pagina.locator("label.prv-categoria", has_text="Herramientas").is_visible())
        pagina.locator("label.prv-categoria", has_text="Herramientas").locator("input").check()
        buscador.fill("zzz")
        self.assertTrue(pagina.locator("[data-sin-resultados]").is_visible())
        buscador.fill("")
        self.assertTrue(pagina.locator("label.prv-categoria", has_text="Nutrientes").locator("input").is_checked())
        pagina.fill("#id_cuit", "20-12345672-7")
        pagina.fill("#id_razon_social", "Vivero del Litoral")
        pagina.fill("#id_email", "ventas@viveroLitoral.com")
        self.capturar(pagina, "compras_02_alta_completa")
        pagina.get_by_role("button", name="Registrar proveedor").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("Registramos a Vivero del Litoral", pagina.inner_text("body"))
        self.assertIn("Nutrientes", pagina.inner_text("body"))
        self.assertIn("Herramientas", pagina.inner_text("body"))
        self.capturar(pagina, "compras_03_ficha_recien_creado")

        # Baja: la ventana se abre con HTMX, sin recargar la página, y confirmar lleva a la lista.
        url_de_la_ficha = pagina.url
        pagina.get_by_role("link", name="Dar de baja").click()
        pagina.wait_for_selector(".ov[data-ventana]")
        self.assertEqual(pagina.url, url_de_la_ficha)
        self.assertIn("¿Dar de baja a Vivero del Litoral?", pagina.inner_text(".modal"))
        self.capturar(pagina, "compras_04_ventana_de_baja")
        pagina.locator(".modal").get_by_role("button", name="Dar de baja").click()
        pagina.wait_for_url("**/compras/proveedores/")
        self.assertIn("Vivero del Litoral quedó inactivo", pagina.inner_text("body"))
        self.assertEqual(pagina.get_by_text("Vivero del Litoral").count() - pagina.get_by_text("quedó inactivo").count(), 0)

        # Reactivar desde el alta: el CUIT de un inactivo ofrece «Reactivar con estos datos».
        pagina.goto(self.url("compras:proveedor_nuevo"))
        pagina.fill("#id_cuit", "20-12345672-7")
        pagina.fill("#id_razon_social", "Vivero del Litoral S. R. L.")
        pagina.fill("#id_email", "nuevo@viverolitoral.com")
        pagina.get_by_role("button", name="Registrar proveedor").click()
        pagina.wait_for_load_state("networkidle")
        self.assertTrue(pagina.get_by_role("button", name="Reactivar con estos datos").is_visible())
        self.assertEqual(pagina.input_value("#id_razon_social"), "Vivero del Litoral S. R. L.")  # conserva lo escrito
        self.capturar(pagina, "compras_05_ofrece_reactivar")
        pagina.get_by_role("button", name="Reactivar con estos datos").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("está activo otra vez", pagina.inner_text("body"))
        self.assertSinErroresDeJavaScript()

    def test_el_alta_vacia_marca_los_errores_por_campo(self):
        """CMP-ALT-PRV regla 1: todos los errores a la vez, junto a cada campo."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.gerente)
        pagina.goto(self.url("compras:proveedor_nuevo"))
        pagina.fill("#id_telefono", "abc")
        pagina.get_by_role("button", name="Registrar proveedor").click()
        pagina.wait_for_load_state("networkidle")
        errores = pagina.locator(".fld .err").all_inner_texts()
        self.assertGreaterEqual(len(errores), 4)  # CUIT, razón social, correo y teléfono
        self.assertTrue(pagina.locator("[data-grupo-tipo=juridica]").is_visible())
        self.capturar(pagina, "compras_06_alta_con_errores")
        self.assertSinErroresDeJavaScript()

    def test_el_agronomo_ve_la_lista_y_la_ficha_sin_botones_de_cambio(self):
        """CMP-CNS-PRV regla 5 y D-30: el Agrónomo solo consulta."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.agronomo)
        pagina.goto(self.url("compras:proveedores"))
        self.assertEqual(pagina.get_by_role("link", name="Nuevo proveedor").count(), 0)
        self.assertEqual(pagina.get_by_role("link", name="Editar").count(), 0)
        self.assertTrue(pagina.get_by_text("Semillas del Sur S. A.").first.is_visible())
        self.capturar(pagina, "compras_07_lista_del_agronomo")
        pagina.goto(self.url("compras:proveedor_ficha", self.sur.pk))
        for texto in ("Editar datos", "Dar de baja", "Reactivar"):
            self.assertEqual(pagina.get_by_text(texto, exact=True).count(), 0)
        self.assertEqual(pagina.goto(self.url("compras:proveedor_nuevo")).status, 403)
        self.errores_de_consola = []  # el 403 de la última dirección deja un error de recurso en la consola: no es de la página

    def test_en_un_celular_no_se_desborda(self):
        """Interfaz: sin scroll horizontal de la página en un celular, en la lista, la ficha y el formulario."""
        pagina = self.nueva_pagina(viewport=ANCHO_DE_CELULAR)
        self.entrar(pagina, self.gerente)
        for nombre, argumentos in (("compras:proveedores", ()), ("compras:proveedor_ficha", (self.sur.pk,)), ("compras:proveedor_nuevo", ())):
            pagina.goto(self.url(nombre, *argumentos))
            self.assertSinScrollHorizontal(pagina)
            self.capturar(pagina, f"compras_celular_{nombre.split(':')[1]}")
        self.assertSinErroresDeJavaScript()

    def test_sin_javascript_la_baja_y_el_alta_siguen_funcionando(self):
        """docs/patrones/abm.md, sección 7: respaldo sin JavaScript. La baja abre la ficha con la ventana; el alta muestra los dos grupos y todas las categorías."""
        pagina = self.nueva_pagina(javascript=False)
        self.entrar(pagina, self.gerente)
        pagina.goto(self.url("compras:proveedor_nuevo"))
        self.assertTrue(pagina.locator("[data-grupo-tipo=juridica]").is_visible())
        self.assertTrue(pagina.locator("[data-grupo-tipo=fisica]").is_visible())
        self.assertEqual(pagina.locator("label.prv-categoria").count(), TipoInsumo.objects.filter(estado_tipo_insumo="activo").count())
        self.assertFalse(pagina.locator("[data-buscar-categoria]").is_visible())  # el buscador necesita JavaScript
        pagina.goto(self.url("compras:proveedor_baja", self.sur.pk))
        self.assertIn("¿Dar de baja a Semillas del Sur S. A.?", pagina.inner_text(".modal"))
        pagina.locator(".modal").get_by_role("button", name="Dar de baja").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("quedó inactivo", pagina.inner_text("body"))
        self.capturar(pagina, "compras_08_sin_javascript_baja")
