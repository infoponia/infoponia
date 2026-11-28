# Pruebas de la interfaz compartida (D-29): marco con sesión, avisos breves, botón secundario y foco de los
# botones. Verifican lo que se puede ver en el HTML y en la hoja de estilos; el temporizador y la cruz de
# los avisos son JavaScript y se prueban a mano. Cada prueba arma sus propios datos.

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.tests.fabricas import (
    agrupar,
    crear_capataz,
    crear_gerente,
    dar_contrasena_temporal,
    dar_invitacion,
    token_de_invitacion,
)


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

    def test_ui02_el_pie_dice_en_linea_en_la_oficina_y_en_el_modo_campo(self):
        """UI-02 (UX-21): el pie dice «En línea» en el marco de oficina (Gerente) y en el de campo (Capataz); «Sistema operativo» se leía
        como Windows o Android."""
        for cuenta in (crear_gerente(), crear_capataz(email="capataz-pie@infoponia.com")):
            with self.subTest(rol=cuenta.rol):
                self.client.force_login(cuenta)
                pie = re.search(r'<footer class="bot">(.*?)</footer>', self.client.get(reverse("core:inicio")).content.decode(), re.S)
                self.assertIsNotNone(pie)
                self.assertIn("En línea", pie.group(1))
                self.assertNotIn("Sistema operativo", pie.group(1))

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


class MarcoEnElCelularTests(TestCase):
    """UI-02 (UX-01; D-109 punto 4): el marco no se ensancha más que la ventana en el celular. Una columna `1fr` no baja del ancho
    mínimo de su contenido (la fila de módulos del celular suma unos 430 px); `minmax(0,1fr)` sí. Se verifica en la hoja de estilos;
    que la pantalla mida 360 px se mira a mano."""

    def test_ui02_las_columnas_del_marco_usan_minmax_en_escritorio_celular_y_modo_campo(self):
        """D-109 punto 4: la columna del contenido y del encabezado usa `minmax(0,1fr)` en escritorio (con el menú lateral), en el celular,
        en el modo campo y en el marco sin menú lateral."""
        css = _css()
        esperadas = {
            ".shell": "grid-template-columns:var(--sidebar-width) minmax(0,1fr)",
            ".shell.field": "grid-template-columns:minmax(0,1fr)",
            ".shell.sin-lateral": "grid-template-columns:minmax(0,1fr)",
            ".shell:not(.field)": "grid-template-columns:minmax(0,1fr)",
        }
        for selector, columnas in esperadas.items():
            with self.subTest(selector=selector):
                self.assertIn(columnas, _regla(css, selector))
        celular = re.search(r"@media\(max-width:760px\)\{\s*\.shell:not\(\.field\)\{([^}]*)\}", css)
        self.assertIsNotNone(celular, "la regla del celular tiene que estar dentro del bloque de menos de 760px")
        self.assertIn("minmax(0,1fr)", celular.group(1))

    def test_ui02_las_fichas_del_menu_del_celular_no_se_encogen(self):
        """D-109 punto 4: la fila de módulos del celular (`.mnav`) se desplaza dentro de su lugar: sus fichas no se encogen ni parten
        el texto, y la fila tiene desplazamiento horizontal."""
        css = _css()
        ficha = _regla(css, ".mnav .chip")
        self.assertIn("flex-shrink:0", ficha)
        self.assertIn("white-space:nowrap", ficha)
        reglas_de_la_fila = re.findall(r"(?<![\w-])\.mnav\{([^}]*)\}", css)  # la base y las del bloque de menos de 760px
        self.assertTrue(any("overflow-x:auto" in regla for regla in reglas_de_la_fila), reglas_de_la_fila)


def _mezcla(color, porcentaje, otro):
    """``color-mix(in srgb, color porcentaje%, otro)`` de CSS, canal por canal, como ``#rrggbb``."""
    a, b = (c.lstrip("#") for c in (color, otro))
    if len(b) == 3:
        b = "".join(ch * 2 for ch in b)
    p = porcentaje / 100
    return "#" + "".join(f"{round(int(a[i:i + 2], 16) * p + int(b[i:i + 2], 16) * (1 - p)):02x}" for i in (0, 2, 4))


class ContrasteTests(TestCase):
    """UI-02 (UX-03; D-109 punto 5): todo texto cumple WCAG 1.4.3 (4,5:1). Con la misma función de contraste que
    `test_d29_boton_secundario_cumple_contraste_wcag_aa`."""

    def test_ui02_faint_cumple_contraste_sobre_los_cuatro_fondos(self):
        """D-109 punto 5: `--faint` cumple 4,5:1 sobre el blanco de las tarjetas, `--subtle`, `--background` y `--primary-soft`."""
        css = _css()
        faint = re.search(r"--faint:(#[0-9a-fA-F]{6})", css).group(1)
        for fondo in ("#ffffff", "#f9fafb", "#f5f6f8", "#eaf5ee"):
            with self.subTest(fondo=fondo):
                self.assertGreaterEqual(_contraste(faint, fondo), 4.5)

    def test_ui02_el_texto_del_ciclo_no_es_blanco_y_cumple_contraste_en_cada_etapa(self):
        """D-109 punto 5: sobre los colores de etapa no va texto blanco chico. El tramo del ciclo usa texto oscuro sobre el fondo claro (como
        `.etapa`) y cumple 4,5:1 con cada color de etapa (`--e-ger`, `--e-cre`, `--e-flo`, `--e-fru`, `--e-mad`)."""
        css = _css()
        tramo = _regla(css, ".ciclo span")
        self.assertNotIn("color:#fff", tramo)
        fondo = re.search(r"background:color-mix\(in srgb,var\(--c\) (\d+)%,(#fff)\)", tramo)
        texto = re.search(r"(?:^|;)color:color-mix\(in srgb,var\(--c\) (\d+)%,(#000)\)", tramo)
        self.assertIsNotNone(fondo, tramo)
        self.assertIsNotNone(texto, tramo)
        etapas = dict(re.findall(r"--(e-[a-z]{3}):(#[0-9a-fA-F]{6})", css))
        self.assertEqual(len(etapas), 5)
        for nombre, color in etapas.items():
            with self.subTest(etapa=nombre):
                self.assertGreaterEqual(
                    _contraste(_mezcla(color, int(texto.group(1)), texto.group(2)), _mezcla(color, int(fondo.group(1)), fondo.group(2))),
                    4.5,
                )


def _plantillas_de_todas_las_apps():
    """Las plantillas ``.html`` de todas las apps del proyecto (``<app>/templates/``)."""
    return sorted(Path(settings.BASE_DIR).glob("*/templates/**/*.html"))


class EnlacesPestanasYVolverTests(TestCase):
    """UI-02 (UX-05 y UX-08; D-109 punto 6): estilo base de los enlaces, pestañas que son enlaces y la flecha de «volver»."""

    def test_ui02_todo_volver_usa_el_icono_back_y_nunca_chev(self):
        """D-109 punto 6: todo enlace «volver» (``<a class="back">``) de cualquier app usa el ícono ``back`` (flecha a la izquierda), nunca
        ``chev`` (flecha hacia abajo) ni un carácter suelto («‹»)."""
        volver = []
        for plantilla in _plantillas_de_todas_las_apps():
            for enlace in re.findall(r'<a class="back"[^>]*>.*?</a>', plantilla.read_text(encoding="utf-8"), re.S):
                volver.append((plantilla.relative_to(settings.BASE_DIR).as_posix(), enlace))
        self.assertGreater(len(volver), 50)  # que la prueba no pase sin revisar nada
        mal = [f"{archivo}: {enlace[:100]}" for archivo, enlace in volver if '{% icono "back"' not in enlace or "chev" in enlace]
        self.assertEqual(mal, [], "«Volver» sin el ícono back:\n" + "\n".join(mal))

    def test_ui02_la_regla_de_las_pestanas_enlace_vive_solo_en_infoponia_css(self):
        """D-109 punto 6: ``a.tab`` (sin subrayado, con foco visible) está una sola vez, en ``infoponia.css``, y en ningún CSS de app."""
        self.assertIn("text-decoration:none", _regla(_css(), "a.tab"))
        self.assertIn("outline:2px solid var(--primary)", _regla(_css(), "a.tab:focus-visible"))
        hoja_comun = Path(settings.BASE_DIR) / "core/static/core/css/infoponia.css"
        con_la_regla = []
        for hoja in Path(settings.BASE_DIR).glob("*/static/**/*.css"):
            if hoja.resolve() == hoja_comun.resolve():
                continue
            sin_comentarios = re.sub(r"/\*.*?\*/", "", hoja.read_text(encoding="utf-8"), flags=re.S)
            if re.search(r"(?<![\w-])a\.tab\b", sin_comentarios):
                con_la_regla.append(hoja.relative_to(settings.BASE_DIR).as_posix())
        self.assertEqual(con_la_regla, [])

    def test_ui02_los_enlaces_del_contenido_van_en_el_verde_primario_sin_tocar_botones_ni_menus(self):
        """D-109 punto 6: hay un estilo base para los enlaces del contenido, en ``--primary`` y subrayado. Va dentro de ``:where()`` (pesa como
        un ``a`` suelto, así cualquier regla con clase sigue mandando) y deja afuera los enlaces con forma de botón, ficha, pestaña o menú."""
        css = _css()
        base = re.search(r"^:where\(main\) a:where\(:not\(([^)]*)\)\)\{([^}]*)\}", css, re.M)
        self.assertIsNotNone(base, "falta el estilo base de los enlaces del contenido")
        excluidas = set(base.group(1).split(","))
        self.assertTrue({".btn", ".chip", ".tab", ".nav-item", ".rowlink", ".gh", ".back", ".kpi", ".opt"} <= excluidas, excluidas)
        self.assertIn("color:var(--primary)", base.group(2))
        self.assertIn("text-decoration:underline", base.group(2))
        self.assertIn("text-decoration:none", _regla(css, "a.kpi,a.opt"))


class PlantillasTests(TestCase):
    """Reglas de escritura de las plantillas de ``core/templates``."""

    def test_plantillas_los_comentarios_de_una_linea_cierran_en_la_misma_linea(self):
        """Django: ``{# ... #}`` solo comenta una línea. Si el ``{#`` abre en una línea y cierra en otra, Django no lo
        toma como comentario y el texto se ve en la pantalla (o en el correo). Los comentarios de varias líneas
        van entre ``{% comment %}`` y ``{% endcomment %}``. Revisa todas las plantillas (.html y .txt)."""
        raiz = Path(settings.BASE_DIR) / "core" / "templates"
        plantillas = [*raiz.rglob("*.html"), *raiz.rglob("*.txt")]
        self.assertGreater(len(plantillas), 0)  # que la prueba no pase sin revisar nada

        abiertos_sin_cerrar = []
        for plantilla in plantillas:
            texto = plantilla.read_text(encoding="utf-8")
            for numero, linea in enumerate(texto.splitlines(), start=1):
                resto = linea
                while "{#" in resto:
                    apertura = resto.index("{#")
                    cierre = resto.find("#}", apertura + 2)
                    if cierre < 0:
                        abiertos_sin_cerrar.append(
                            f"{plantilla.relative_to(raiz)}:{numero}: {linea.strip()[:80]}"
                        )
                        break
                    resto = resto[cierre + 2 :]

        self.assertEqual(
            abiertos_sin_cerrar,
            [],
            "Hay '{#' que no cierra con '#}' en la misma línea: usá {% comment %}...{% endcomment %}.",
        )


class EnviosEnCursoTests(TestCase):
    """Envíos en curso (D-29): lo que se puede verificar en el HTML del servidor y en la hoja de estilos. El
    comportamiento del botón (indicador, doble envío, restauración) y el aviso de error de HTMX son JavaScript y
    se prueban a mano. Cada prueba arma sus propios datos."""

    def paginas_con_formularios_post(self):
        """HTML de las pantallas y ventanas que tienen formularios POST, de cada rol que las ve."""
        paginas = {}
        HTMX = {"HX-Request": "true"}

        paginas["iniciar_sesion"] = self.client.get(reverse("core:iniciar_sesion")).content.decode()

        # Recuperar contraseña (USR-RCP-CTR, tarea 08): el pedido y la contraseña nueva, con el correo configurado.
        with override_settings(CORREO_CONFIGURADO=True):
            paginas["recuperar_contrasena"] = self.client.get(
                reverse("core:recuperar_contrasena")
            ).content.decode()
            olvidada = crear_capataz(email="olvidada@infoponia.com")
            uidb64 = urlsafe_base64_encode(force_bytes(olvidada.pk))
            anonimo = Client()
            anonimo.get(
                reverse(
                    "core:recuperacion_enlace",
                    kwargs={"uidb64": uidb64, "token": default_token_generator.make_token(olvidada)},
                )
            )
            paginas["recuperar_elegir"] = anonimo.get(
                reverse("core:recuperacion_elegir", kwargs={"uidb64": uidb64})
            ).content.decode()

        # Aceptar la invitación (SEG-20, tarea 08b): «Elegí tu contraseña para empezar a usar InfoPonia».
        invitada = dar_invitacion(crear_capataz(email="invitada@infoponia.com"))
        uidb64_invitada = urlsafe_base64_encode(force_bytes(invitada.pk))
        otro_anonimo = Client()
        otro_anonimo.get(
            reverse(
                "core:invitacion_enlace",
                kwargs={"uidb64": uidb64_invitada, "token": token_de_invitacion(invitada)},
            )
        )
        paginas["invitacion_elegir"] = otro_anonimo.get(
            reverse("core:invitacion_elegir", kwargs={"uidb64": uidb64_invitada})
        ).content.decode()

        nueva = crear_capataz(email="nueva@infoponia.com")
        dar_contrasena_temporal(nueva)
        self.client.force_login(nueva)
        paginas["elegir_contrasena"] = self.client.get(reverse("core:elegir_contrasena")).content.decode()

        gerente = crear_gerente()
        activa = crear_capataz(email="activa@infoponia.com")
        inactiva = crear_capataz(email="baja@infoponia.com", is_active=False)
        self.client.force_login(gerente)
        paginas["inicio_gerente"] = self.client.get(reverse("core:inicio")).content.decode()
        paginas["alta"] = self.client.get(reverse("core:usuario_nuevo")).content.decode()
        paginas["modificar"] = self.client.get(reverse("core:usuario_modificar", args=[activa.pk])).content.decode()
        paginas["restablecer"] = self.client.get(
            reverse("core:usuario_restablecer", args=[activa.pk]), headers=HTMX
        ).content.decode()
        paginas["baja"] = self.client.get(
            reverse("core:usuario_baja", args=[activa.pk]), headers=HTMX
        ).content.decode()
        paginas["reactivar"] = self.client.get(
            reverse("core:usuario_reactivar", args=[inactiva.pk]), headers=HTMX
        ).content.decode()

        # Alta, restablecer y reactivar con el correo configurado: el radio de la forma de acceso (D-35).
        with override_settings(CORREO_CONFIGURADO=True):
            paginas["alta_con_correo"] = self.client.get(reverse("core:usuario_nuevo")).content.decode()
            paginas["restablecer_con_correo"] = self.client.get(
                reverse("core:usuario_restablecer", args=[activa.pk]), headers=HTMX
            ).content.decode()
            paginas["reactivar_con_correo"] = self.client.get(
                reverse("core:usuario_reactivar", args=[inactiva.pk]), headers=HTMX
            ).content.decode()

        uno = crear_capataz(email="uno@infoponia.com")
        otro = crear_capataz(email="otro@infoponia.com")
        agrupar(uno, otro)
        self.client.force_login(uno)
        paginas["mi_perfil"] = self.client.get(reverse("core:mi_perfil")).content.decode()
        paginas["menu_de_cuenta"] = self.client.get(reverse("core:inicio")).content.decode()
        paginas["vincular"] = self.client.get(reverse("core:vincular_cuenta"), headers=HTMX).content.decode()
        paginas["desvincular"] = self.client.get(
            reverse("core:desvincular_cuenta", args=[otro.pk]), headers=HTMX
        ).content.decode()
        return paginas

    @staticmethod
    def botones_de_envio_post(html):
        """Lista de ``(atributos, texto)`` de los botones de envío de los formularios POST de ``html``. Los
        atributos son los del formulario seguidos de los del botón: el verbo ``data-enviando`` puede ir en
        cualquiera de los dos."""
        botones = []
        for formulario in re.finditer(r"<form\b([^>]*)>(.*?)</form>", html, re.S):
            if not re.search(r'method="post"', formulario.group(1), re.I):
                continue
            for boton in re.finditer(r"<button\b([^>]*)>(.*?)</button>", formulario.group(2), re.S):
                if 'type="submit"' in boton.group(1) or "type=" not in boton.group(1):
                    atributos = formulario.group(1) + " " + boton.group(1)
                    texto = re.sub(r"<[^>]+>", "", boton.group(2)).strip()
                    botones.append((atributos, texto))
        return botones

    def test_d29_las_pantallas_de_la_tarea_08_y_08b_tienen_su_formulario_de_envio(self):
        """D-29: las pantallas de recuperación e invitación (SEG-12, SEG-20) y las del alta, el restablecimiento y la
        reactivación con la forma de acceso (D-35) están entre las revisadas por las pruebas de envíos en curso:
        cada una trae al menos un botón de envío de un formulario POST (no una pantalla de error o de aviso)."""
        paginas = self.paginas_con_formularios_post()
        for nombre in (
            "recuperar_contrasena",
            "recuperar_elegir",
            "invitacion_elegir",
            "alta_con_correo",
            "restablecer_con_correo",
            "reactivar_con_correo",
        ):
            with self.subTest(nombre):
                self.assertTrue(self.botones_de_envio_post(paginas[nombre]), nombre)
        # El radio de la forma de acceso solo aparece con el correo configurado.
        self.assertIn('name="acceso"', paginas["alta_con_correo"])
        self.assertNotIn('name="acceso"', paginas["alta"])

    def test_d29_el_html_del_servidor_trae_los_botones_de_envio_sin_cambios(self):
        """D-29: sin JavaScript el formulario funciona como siempre. El botón de envío llega del servidor
        habilitado, visible y con su texto: el indicador y el estado «enviando» los agrega solo el script."""
        total = 0
        for nombre, html in self.paginas_con_formularios_post().items():
            for atributos, texto in self.botones_de_envio_post(html):
                total += 1
                with self.subTest(pagina=nombre, boton=texto):
                    self.assertNotIn("disabled", atributos)
                    self.assertNotIn("hidden", atributos)
                    self.assertNotIn("enviando", atributos.replace("data-enviando", ""))
                    self.assertTrue(texto)
                    self.assertNotIn("giro", html)
        self.assertGreaterEqual(total, 12, "las pantallas de la prueba dejaron de traer formularios POST")

    def test_d29_los_botones_con_otro_verbo_traen_el_texto_de_la_accion_en_curso(self):
        """D-29: «Guardando…» es el texto por defecto de los botones «Guardar…»; todo otro botón de envío de un
        formulario POST declara su verbo en ``data-enviando`` (por ejemplo «Ingresando…»), terminado en «…»."""
        for nombre, html in self.paginas_con_formularios_post().items():
            for atributos, texto in self.botones_de_envio_post(html):
                if texto.startswith("Guardar"):
                    continue
                with self.subTest(pagina=nombre, boton=texto):
                    self.assertRegex(atributos, r'data-enviando="[^"]+…"')

    def test_d29_el_limite_de_espera_de_htmx_es_de_30_segundos_con_y_sin_sesion(self):
        """D-29: toda pantalla trae la configuración de HTMX con 30 s de límite; sin ella HTMX no corta nunca un
        pedido sin respuesta y el aviso de error no llegaría."""
        etiqueta = '<meta name="htmx-config" content=\'{"timeout": 30000}\'>'
        sin_sesion = self.client.get(reverse("core:iniciar_sesion"))
        self.client.force_login(crear_gerente())
        con_sesion = self.client.get(reverse("core:inicio"))

        self.assertContains(sin_sesion, etiqueta)
        self.assertContains(con_sesion, etiqueta)

    def test_d29_infoponia_js_rehabilita_el_boton_aunque_el_fragmento_reemplace_al_elemento_del_pedido(self):
        """D-29 (corrección de IOT-01): si la respuesta de HTMX reemplaza el elemento que hizo el pedido, ``htmx:afterRequest`` ya no
        burbujea hasta ``document`` y el botón de envío quedaba deshabilitado hasta el límite de 30 s. El fin del pedido se escucha
        también en el propio elemento. Y un pedido que solo redibuja el formulario lo marca con ``data-sin-envio-en-curso``. El
        comportamiento es JavaScript y se verifica a mano; acá, que el código esté."""
        with open("core/static/core/js/infoponia.js", encoding="utf-8") as archivo:
            codigo = archivo.read()
        self.assertIn('elemento.addEventListener("htmx:afterRequest"', codigo)
        self.assertIn("data-sin-envio-en-curso", codigo)

    def test_d29_el_indicador_gira_y_con_reducir_movimiento_queda_quieto(self):
        """D-29: el indicador de envío en curso es un anillo con un tramo de color que gira; con
        prefers-reduced-motion no se anima. El bloque de «reducir movimiento» va después de la regla base: con la
        misma especificidad, gana la última."""
        css = _css()

        regla = _regla(css, ".giro")
        self.assertIn("border-top-color:transparent", regla)
        self.assertIn("border-radius:50%", regla)
        self.assertIn("animation:giro", regla)
        self.assertIn("@keyframes giro{to{transform:rotate(360deg)}}", css)
        reducido = "@media(prefers-reduced-motion:reduce){.giro{animation:none}}"
        self.assertIn(reducido, css)
        self.assertLess(css.index(".giro{"), css.index(reducido))

    def test_d29_el_boton_enviando_muestra_el_cursor_de_espera(self):
        """D-29: mientras el botón está deshabilitado por un envío en curso, el cursor indica espera (y no el
        «no permitido» de los botones deshabilitados, que tiene menos especificidad)."""
        self.assertIn("cursor:progress", _regla(_css(), "button.enviando:disabled"))
