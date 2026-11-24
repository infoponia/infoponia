# Verificación VISUAL de «Comercial» → «Contratos» → «Suministros» (COM-03a), con un navegador real (Playwright + Chromium) contra el sistema levantado de verdad en su
# propia base de pruebas. Cubre lo que las pruebas con el cliente de Django no ven: que el JavaScript y el HTMX funcionen (recálculo del formulario, ventana del resumen, opciones
# rápidas de período, campos del ajuste periódico), que no haya errores de consola, que el respaldo sin JavaScript funcione y que en un celular no se desborde. Deja capturas en
# ``INFOPONIA_CAPTURAS`` (o ``infoponia_capturas`` en la carpeta temporal). Se corre aparte: ``INFOPONIA_VISUAL=1 python manage.py test comercial.tests.test_visual_suministros
# --tag visual`` (docs/patrones/verificacion_por_claude.md). Sin Playwright, se saltan.

from datetime import timedelta
from urllib.parse import urlencode

from django.utils import timezone

from comercial.models import Suministro
from comercial.tests.fabricas import detalle_suministro, escenario_comercial, reserva_de_periodo, suministro
from core.tests.fabricas import crear_gerente
from core.tests.visual import ANCHO_DE_CELULAR, PruebaVisual
from inventario.tests.fabricas import asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def iso(dias):
    return str(HOY + timedelta(days=dias))


class SuministrosVisualTests(PruebaVisual):
    """Fuente: docs/casos_de_uso/comercial/suministro.md (COM-PCT-SUM y COM-CNS-SUM, «Pantallas»), D-24, D-29, D-30 y D-61."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_georef()  # el `flush` de cada prueba vacía Georef (docs/patrones/datos_de_migracion.md)
        asegurar_datos_de_maestros()
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 300)
        self.gerente = crear_gerente()

    def consulta_de_pacto(self, **extra):
        """La URL de «Pactar suministro» con todo cargado (la consulta de la pantalla lleva las secciones 1 y 2 y los detalles)."""
        datos = {
            "cliente": self.e.cliente.pk, "duracion": "6", "tolerados": "3", "multa": "50000", "plazo_pago": "15", "indemnizacion_pago": "100",
            "detalle-0-variedad": self.e.variedad.pk, "detalle-0-direccion": self.e.direccion.pk, "detalle-0-cantidad": "150", "detalle-0-periodo": "7",
            "detalle-0-primera_entrega": iso(3), "detalle-0-mecanismo": "fijo", "detalle-0-precio": "1500,50", "detalle-0-plazo_entrega": "1",
            "detalle-0-indemnizacion_retraso": "100", "detalle-0-cantidad_minima": "50", "detalle-0-indemnizacion_faltante": "30",
        }
        datos.update(extra)
        return f"{self.url('comercial:suministro_nuevo')}?{urlencode(datos)}"

    def test_el_vendedor_pacta_un_suministro_con_javascript(self):
        """COM-PCT-SUM: el recálculo con HTMX, el ajuste periódico, la ventana del resumen y la confirmación, con un navegador real."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.e.vendedor)

        # La lista con el selector «Compra-ventas / Suministros».
        pagina.goto(self.url("comercial:contratos") + "?tipo=suministro")
        self.assertTrue(pagina.get_by_role("link", name="Pactar suministro").is_visible())
        self.assertEqual(pagina.locator(".sel-tipo a[aria-current=page]").inner_text(), "Suministros")
        self.capturar(pagina, "suministros_01_lista_vacia")

        # El formulario con todo cargado: calendario, precio y verificación de stock de los períodos de la ventana.
        pagina.goto(self.consulta_de_pacto())
        pagina.wait_for_load_state("networkidle")
        self.assertTrue(pagina.get_by_text("se reserva ahora").first.is_visible())
        self.assertTrue(pagina.get_by_text("Alcanza").first.is_visible())
        self.capturar(pagina, "suministros_02_formulario_completo")

        # El mecanismo de ajuste periódico muestra el porcentaje y los meses (selector con HTMX, sin validar ni mover el scroll).
        self.assertEqual(pagina.locator("#det-0-porcentaje").count(), 0)
        pagina.locator("#det-0-mecanismo").select_option("ajuste_periodico", force=True)
        pagina.wait_for_selector("#det-0-porcentaje")
        self.assertTrue(pagina.locator("#det-0-meses").is_visible())
        pagina.fill("#det-0-porcentaje", "3")
        pagina.fill("#det-0-meses", "2")
        pagina.locator("#det-0-periodo").fill("30")
        pagina.get_by_role("button", name="Actualizar").first.click()
        pagina.wait_for_selector("ul.tramos")  # HTMX devolvió el cuerpo con los tramos de precio
        self.assertTrue(pagina.get_by_text("Desde el").first.is_visible())
        self.capturar(pagina, "suministros_03_ajuste_periodico")

        # Una opción rápida de período («7») carga el valor; un error de cantidad se ve junto a su campo.
        pagina.get_by_role("button", name="Cada 7 días").click()
        pagina.wait_for_function("document.querySelector('#det-0-periodo').value === '7'")
        self.assertEqual(pagina.input_value("#det-0-periodo"), "7")
        pagina.fill("#det-0-cantidad", "500")
        pagina.get_by_role("button", name="Revisar y pactar").click()
        pagina.wait_for_function("document.querySelector('#cuerpo-sum').innerText.includes('plantas disponibles de')")
        self.assertIn("plantas disponibles de", pagina.inner_text("#cuerpo-sum"))
        self.assertEqual(pagina.locator(".ov[data-ventana]").count(), 0)
        self.capturar(pagina, "suministros_04_error_de_stock")
        pagina.fill("#det-0-cantidad", "150")
        pagina.locator("#det-0-mecanismo").select_option("fijo", force=True)
        pagina.wait_for_function("!document.querySelector('#det-0-porcentaje')")

        # La ventana del resumen y «Confirmar suministro».
        pagina.get_by_role("button", name="Revisar y pactar").click()
        pagina.wait_for_selector(".ov[data-ventana]")
        self.assertIn("Resumen del suministro", pagina.inner_text(".modal"))
        self.capturar(pagina, "suministros_05_resumen")
        pagina.locator(".modal").get_by_role("button", name="Confirmar suministro").click()
        pagina.wait_for_url("**/contratos/suministros/*/")
        s = Suministro.objects.get()
        self.assertIn("pactado", pagina.inner_text("body"))
        self.assertIn(s.codigo, pagina.inner_text("h1"))
        self.assertEqual(pagina.get_by_text("Modificar suministro").count(), 0)
        self.capturar(pagina, "suministros_06_ficha")

        # El calendario completo y el comprobante imprimible.
        pagina.get_by_role("link", name="Ver todo el calendario").click()
        pagina.wait_for_load_state("networkidle")
        self.capturar(pagina, "suministros_07_calendario_completo")
        pagina.goto(self.url("comercial:suministro_comprobante", s.pk))
        self.assertIn("Comprobante interno, sin validez fiscal.", pagina.inner_text("body"))
        self.capturar(pagina, "suministros_08_comprobante")
        pagina.goto(self.url("comercial:contratos") + "?tipo=suministro")
        self.capturar(pagina, "suministros_09_lista")
        self.assertSinErroresDeJavaScript()

    def test_la_ficha_muestra_la_situacion_de_cada_periodo_y_el_aviso_de_limite(self):
        """COM-CNS-SUM, reglas 6 y 9: «Pasado», «Reservado», «Sin cobertura completa» y «Fuera de la ventana», con el aviso de límite del contrato."""
        s = suministro(self.e, duracion=6, fecha_realizacion=HOY - timedelta(days=20), tolerados=2, incumplimientos=1)
        d = detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=-15)
        reserva_de_periodo(d, HOY + timedelta(days=6), [(self.lote, 30)])
        reserva_de_periodo(d, HOY + timedelta(days=13), [(self.lote, 10)])
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.e.vendedor)
        pagina.goto(self.url("comercial:suministro", s.pk))
        cuerpo = pagina.inner_text("body")
        for texto in ("Pasado", "Reservado", "Sin cobertura completa · faltan 20", "Fuera de la ventana", "Al contrato le queda un incumplimiento tolerado."):
            self.assertIn(texto, cuerpo)
        self.capturar(pagina, "suministros_10_ficha_con_situaciones")
        self.assertSinErroresDeJavaScript()

    def test_el_gerente_elige_al_vendedor_y_ve_todos_los_suministros(self):
        """COM-PCT-SUM extensión 1a y COM-CNS-SUM regla 1: el Gerente elige al Vendedor responsable y su lista trae todos."""
        propio = suministro(self.e)
        detalle_suministro(propio, self.e.variedad)
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.gerente)
        pagina.goto(self.url("comercial:contratos") + "?tipo=suministro")
        self.assertTrue(pagina.get_by_text(propio.codigo).first.is_visible())
        self.assertTrue(pagina.locator("select[aria-label=Vendedor]").count() >= 1)
        self.capturar(pagina, "suministros_11_lista_del_gerente")
        pagina.goto(self.url("comercial:suministro_nuevo"))
        self.assertTrue(pagina.get_by_text("Vendedor responsable").first.is_visible())
        self.capturar(pagina, "suministros_12_formulario_del_gerente")
        self.assertSinErroresDeJavaScript()

    def test_el_agronomo_no_tiene_acceso(self):
        """Precondición a: el Agrónomo recibe 403 en la lista y en el formulario, y la lista no está en su menú."""
        pagina = self.nueva_pagina()
        self.entrar(pagina, self.e.agronomo)
        self.assertEqual(pagina.goto(self.url("comercial:contratos") + "?tipo=suministro").status, 403)
        self.assertEqual(pagina.goto(self.url("comercial:suministro_nuevo")).status, 403)
        self.errores_de_consola = []  # los 403 dejan un error de recurso en la consola: no es de la página

    def test_en_un_celular_no_se_desborda(self):
        """Interfaz: sin scroll horizontal de la página en un celular, en la lista, el formulario, la ficha y el calendario."""
        s = suministro(self.e, duracion=6)
        detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=3)
        pagina = self.nueva_pagina(viewport=ANCHO_DE_CELULAR)
        self.entrar(pagina, self.e.vendedor)
        direcciones = (
            ("lista", self.url("comercial:contratos") + "?tipo=suministro"),
            ("formulario", self.consulta_de_pacto()),
            ("ficha", self.url("comercial:suministro", s.pk)),
            ("calendario", self.url("comercial:suministro_calendario", s.pk)),
        )
        for nombre, url in direcciones:
            pagina.goto(url)
            pagina.wait_for_load_state("networkidle")
            self.assertSinScrollHorizontal(pagina)
            self.capturar(pagina, f"suministros_celular_{nombre}")
        self.assertSinErroresDeJavaScript()

    def test_sin_javascript_el_pacto_funciona_con_actualizar_y_el_resumen_como_pagina(self):
        """Respaldo sin JavaScript (abm.md, sección 7): «Actualizar» recalcula, «Revisar y pactar» lleva a una página de resumen y «Confirmar» pacta."""
        pagina = self.nueva_pagina(javascript=False)
        self.entrar(pagina, self.e.vendedor)
        pagina.goto(self.consulta_de_pacto())
        self.assertTrue(pagina.get_by_text("se reserva ahora").first.is_visible())
        pagina.get_by_role("button", name="Actualizar").first.click()
        pagina.wait_for_load_state("networkidle")
        self.capturar(pagina, "suministros_sinjs_01_formulario")
        pagina.get_by_role("button", name="Revisar y pactar").click()
        pagina.wait_for_load_state("networkidle")
        self.assertIn("Resumen del suministro", pagina.inner_text("h1"))
        self.capturar(pagina, "suministros_sinjs_02_resumen")
        pagina.get_by_role("button", name="Confirmar suministro").click()
        pagina.wait_for_load_state("networkidle")
        self.assertEqual(Suministro.objects.count(), 1)
        self.assertIn("pactado", pagina.inner_text("body"))
        self.capturar(pagina, "suministros_sinjs_03_ficha")
