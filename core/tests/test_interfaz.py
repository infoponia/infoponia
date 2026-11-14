# Pruebas de la interfaz compartida (D-29): marco con sesión, avisos breves, botón secundario y foco de los
# botones. Verifican lo que se puede ver en el HTML y en la hoja de estilos; el temporizador y la cruz de
# los avisos son JavaScript y se prueban a mano. Cada prueba arma sus propios datos.

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.fabricas import crear_gerente


def _luminancia(color):
    """Luminancia relativa de un color ``#rrggbb`` o ``#rgb`` (definición de WCAG 2.x)."""
    if len(color) == 4:  # «#fff» es «#ffffff»
        color = "#" + "".join(c * 2 for c in color[1:])
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineales = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineales[0] + 0.7152 * lineales[1] + 0.0722 * lineales[2]


def _contraste(color_a, color_b):
    """Relación de contraste entre dos colores ``#rrggbb`` (de 1 a 21)."""
    claro, oscuro = sorted((_luminancia(color_a), _luminancia(color_b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


class MarcoVistaTests(TestCase):
    """Marco con sesión y estilos compartidos (D-29): avisos breves, botón secundario y versión de
    los archivos estáticos propios. Verifican lo que se puede ver en el HTML y en la hoja de estilos; el
    temporizador y la cruz de los avisos son JavaScript y se prueban a mano."""

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_d29_marco_trae_la_region_de_avisos_para_lectores_de_pantalla(self):
        """D-29: toda pantalla con sesión trae la región de avisos, vacía y con role="status", para que
        los lectores de pantalla anuncien cada aviso que se le agrega."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(
            respuesta,
            '<div class="avisos" id="avisos" role="status" aria-live="polite"></div>',
            html=True,
        )

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_d29_mensajes_de_exito_y_de_error_traen_respaldo_sin_javascript(self):
        """D-29: los mensajes de Django (éxito y error) quedan en la página como aviso fijo con
        role="status" y su tipo; es el respaldo sin JavaScript, que con JavaScript pasa a ser un aviso breve."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("prueba_mensajes"))

        contenido = respuesta.content.decode()
        exito = re.search(
            r'<div class="alert alert-ok" role="status" data-aviso data-tipo="ok">.*?Todo salió bien\.',
            contenido,
            re.S,
        )
        error = re.search(
            r'<div class="alert alert-danger" role="status" data-aviso data-tipo="error">.*?Algo salió mal\.',
            contenido,
            re.S,
        )
        self.assertIsNotNone(exito, "falta el aviso de éxito")
        self.assertIsNotNone(error, "falta el aviso de error")

    def test_d29_los_errores_de_campo_no_son_avisos(self):
        """D-29: los errores debajo de los campos de un formulario no son avisos breves: siguen siendo un
        mensaje junto al campo (clase «err») y no llevan la marca de aviso."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.post(reverse("core:usuario_nuevo"), {})

        self.assertContains(respuesta, 'class="err"')
        self.assertNotContains(respuesta, "data-aviso")

    def test_d29_estilos_y_scripts_propios_llevan_version(self):
        """D-29: la hoja de estilos y los scripts propios se piden con la fecha del archivo en la URL
        (``?v=``), con y sin sesión: un cambio en ellos llega al navegador sin forzar la recarga."""
        self.client.force_login(crear_gerente())
        con_sesion = self.client.get(reverse("core:inicio")).content.decode()
        self.client.logout()
        sin_sesion = self.client.get(reverse("core:iniciar_sesion")).content.decode()

        for pagina in (con_sesion, sin_sesion):
            for archivo in ("css/infoponia.css", "js/infoponia.js", "js/desplegable.js"):
                self.assertRegex(pagina, rf"core/{re.escape(archivo)}\?v=\d+")

    def test_d29_boton_secundario_cumple_contraste_wcag_aa(self):
        """D-29: el botón secundario (.btn-ghost) usa el verde primario en el borde y el texto, sobre fondo
        blanco, y cumple WCAG AA: texto de al menos 4,5:1 y borde de al menos 3:1, también en el hover."""
        css = (Path(settings.BASE_DIR) / "core/static/core/css/infoponia.css").read_text(encoding="utf-8")
        primario = re.search(r"--primary:(#[0-9a-fA-F]{6})", css).group(1)

        def propiedad(selector, nombre):
            regla = re.search(re.escape(selector) + r"\{([^}]*)\}", css).group(1)
            valor = re.search(rf"(?:^|;){nombre}:([^;]+)", regla).group(1).strip()
            return primario if valor == "var(--primary)" else valor

        self.assertEqual(propiedad(".btn-ghost", "color"), primario)
        self.assertEqual(propiedad(".btn-ghost", "border-color"), primario)
        self.assertEqual(propiedad(".btn-ghost", "background"), "#fff")
        for selector in (".btn-ghost", ".btn-ghost:hover"):
            with self.subTest(selector=selector):
                fondo = propiedad(selector, "background")
                fondo = "#ffffff" if fondo == "#fff" else fondo
                self.assertGreaterEqual(_contraste(propiedad(selector, "color"), fondo), 4.5)
                self.assertGreaterEqual(_contraste(propiedad(selector, "border-color"), fondo), 3.0)


def _css():
    """Texto de la hoja de estilos del sistema."""
    return (Path(settings.BASE_DIR) / "core/static/core/css/infoponia.css").read_text(encoding="utf-8")


def _regla(css, selector):
    """Contenido de la regla ``selector{...}`` de la hoja de estilos (la primera que coincide)."""
    coincidencia = re.search(r"(?<![\w-])" + re.escape(selector) + r"\{([^}]*)\}", css)
    assert coincidencia, f"no hay una regla {selector}"
    return coincidencia.group(1)


class AvisosYFocoEstilosTests(TestCase):
    """Presentación de los avisos breves y foco de los botones (D-29), verificados en la hoja de estilos:
    el comportamiento (10 segundos, cruz, salida animada) es JavaScript y se prueba a mano."""

    def test_d29_avisos_son_una_tarjeta_con_los_colores_del_sistema(self):
        """D-29: el aviso es una tarjeta (fondo --card, borde --border, radio de 6px) con una franja de 4px
        a la izquierda del color de su tipo: --status-ok para éxito y --status-danger para error. Texto en
        --foreground y cruz en --muted-foreground."""
        css = _css()
        toast = _regla(css, ".toast")

        self.assertIn("background:var(--card)", toast)
        self.assertIn("border:1px solid var(--border)", toast)
        self.assertIn("border-left:4px solid var(--color-aviso)", toast)
        self.assertIn("border-radius:6px", toast)
        self.assertIn("color:var(--foreground)", toast)
        self.assertIn("--color-aviso:var(--status-ok)", toast)
        self.assertIn("--color-aviso:var(--status-danger)", _regla(css, ".toast-error"))
        self.assertIn("color:var(--color-aviso)", _regla(css, ".toast-icono"))
        self.assertIn("background:var(--color-aviso)", _regla(css, ".toast-barra"))
        self.assertIn("height:3px", _regla(css, ".toast-barra"))
        self.assertIn("color:var(--muted-foreground)", _regla(css, ".toast-cerrar"))

    def test_d29_avisos_cumplen_contraste_wcag_aa_sobre_la_tarjeta(self):
        """D-29: el texto, la cruz y el ícono de cada tipo cumplen WCAG AA (4,5:1) sobre el fondo de la
        tarjeta, con los valores de los tokens de la hoja de estilos."""
        css = _css()

        def token(nombre):
            return re.search(rf"--{nombre}:(#[0-9a-fA-F]{{3,6}})", css).group(1)

        fondo = token("card")
        for nombre in ("foreground", "muted-foreground", "status-ok", "status-danger"):
            with self.subTest(token=nombre):
                self.assertGreaterEqual(_contraste(token(nombre), fondo), 4.5)

    def test_d29_avisos_van_arriba_a_la_derecha_debajo_del_encabezado(self):
        """D-29: los avisos se apilan hacia abajo arriba a la derecha, debajo del encabezado, con un ancho
        máximo de 380px; en menos de 760px ocupan el ancho con 12px de margen."""
        css = _css()
        avisos = _regla(css, ".avisos")

        self.assertIn("top:calc(var(--header-height) + 10px)", avisos)
        self.assertIn("right:16px", avisos)
        self.assertIn("width:380px", avisos)
        self.assertIn("flex-direction:column", avisos)
        movil = re.search(r"@media\(max-width:760px\)\{\.avisos,\.shell\.field \.avisos\{([^}]*)\}", css)
        self.assertIsNotNone(movil, "falta la regla de menos de 760px")
        for propiedad in ("left:12px", "right:12px", "width:auto"):
            self.assertIn(propiedad, movil.group(1))

    def test_d29_animaciones_de_entrada_salida_y_barra(self):
        """D-29: el aviso entra deslizándose desde la derecha con fundido (250ms, ease-out), sale
        desvaneciéndose hacia la derecha (200ms) y una barra de 3px se achica durante la duración del aviso."""
        css = _css()

        self.assertIn("animation:avisoEntra .25s ease-out", _regla(css, ".toast"))
        self.assertIn("animation:avisoSale .2s", _regla(css, ".toast-saliendo"))
        self.assertIn("animation:avisoBarra var(--duracion-aviso,10s) linear", _regla(css, ".toast-barra"))
        self.assertRegex(css, r"@keyframes avisoEntra\{from\{opacity:0;transform:translateX\(32px\)\}")
        self.assertRegex(css, r"@keyframes avisoSale\{[^@]*to\{opacity:0;transform:translateX\(32px\)\}")
        self.assertRegex(css, r"@keyframes avisoBarra\{from\{transform:scaleX\(1\)\}to\{transform:scaleX\(0\)\}")

    def test_d29_con_reducir_movimiento_los_avisos_no_se_animan(self):
        """D-29: con prefers-reduced-motion no hay desplazamiento ni barra animada: el aviso solo aparece
        y desaparece."""
        css = _css()

        reducido = re.search(r"@media\(prefers-reduced-motion:reduce\)\{(.*?)\}\s*(?:\n|$)", css, re.S).group(1)
        self.assertIn(".toast,.toast-saliendo{animation:none}", reducido)
        self.assertIn(".toast-barra{display:none}", reducido)

    def test_d29_en_pantallas_angostas_los_avisos_van_abajo_sobre_el_pie(self):
        """D-29 (actualizada el 14/11/2026): en menos de 760px los avisos no van arriba, donde taparían el título y
        el comienzo de la página, sino abajo, sobre el pie, apilados hacia arriba (el primero queda junto al borde,
        como en escritorio queda junto al encabezado). Siguen ocupando el ancho con 12px de margen."""
        css = _css()

        movil = re.search(r"@media\(max-width:760px\)\{\.avisos,\.shell\.field \.avisos\{([^}]*)\}", css)
        self.assertIsNotNone(movil, "falta la regla de menos de 760px")
        for propiedad in (
            "left:12px",
            "right:12px",
            "width:auto",
            "top:auto",
            "bottom:calc(var(--footer-height) + 10px)",
            "flex-direction:column-reverse",
        ):
            self.assertIn(propiedad, movil.group(1))

    def test_d29_en_pantallas_angostas_los_avisos_entran_y_salen_por_abajo(self):
        """D-29 (actualizada el 14/11/2026): en menos de 760px el aviso entra deslizándose desde abajo y sale hacia
        abajo. Solo cambia el nombre de la animación: la duración (250ms y 200ms) y la curva son las de siempre, y
        las de escritorio (desde la derecha) quedan como estaban."""
        css = _css()

        self.assertRegex(
            css,
            r"@keyframes avisoEntraAbajo\{from\{opacity:0;transform:translateY\(32px\)\}to\{opacity:1;transform:none\}\}",
        )
        self.assertRegex(
            css,
            r"@keyframes avisoSaleAbajo\{from\{opacity:1;transform:none\}to\{opacity:0;transform:translateY\(32px\)\}\}",
        )
        self.assertIn(
            "@media(max-width:760px){.toast{animation-name:avisoEntraAbajo}"
            ".toast-saliendo{animation-name:avisoSaleAbajo}}",
            css,
        )
        self.assertIn("animation:avisoEntra .25s ease-out", _regla(css, ".toast"))
        self.assertIn("animation:avisoSale .2s", _regla(css, ".toast-saliendo"))

    def test_d29_con_reducir_movimiento_tambien_en_pantallas_angostas_no_se_animan(self):
        """D-29 (actualizada el 14/11/2026): el bloque de «reducir movimiento» viene DESPUÉS del que cambia las
        animaciones en pantallas angostas. Las dos reglas tienen la misma especificidad y gana la última: si el
        orden fuera el inverso, en un celular con «reducir movimiento» los avisos volverían a deslizarse."""
        css = _css()

        angosto = css.index("@media(max-width:760px){.toast{animation-name:avisoEntraAbajo}")
        reducido = css.index("@media(prefers-reduced-motion:reduce)")
        self.assertLess(angosto, reducido)

    def test_d29_todos_los_botones_muestran_el_foco_con_el_verde_primario(self):
        """D-29: al navegar con Tab, todo .btn muestra un borde de foco en el verde primario (:focus-visible),
        separado del botón para que se vea también en el primario y en el peligroso."""
        regla = _regla(_css(), ".btn:focus-visible")

        self.assertIn("outline:2px solid var(--primary)", regla)
        self.assertIn("outline-offset:2px", regla)

    def test_d29_botones_enlace_no_se_subrayan(self):
        """D-29: un botón que es un enlace (<a class="btn">) no se subraya, igual que uno que es <button>."""
        self.assertIn("text-decoration:none", _regla(_css(), ".btn"))
