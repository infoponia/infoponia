# Pruebas de la pantalla de monitoreo (IOT-04, paso 7; IOT-CNS-LEC: reglas 1, 9 y 11 y «Ruta y pestaña», «Refresco», «Pantallas»; D-24, D-29, D-30, D-76 punto 8; `.claude/rules/interfaz.md`).
# Integración con el cliente de prueba de Django. Se escribieron ANTES que la vista y las plantillas (en pantallas sin reglas de negocio, las pruebas van después; acá van antes porque
# la vista decide el período, el invernadero y qué se le muestra a cada rol). La lógica del panel está en `test_iot_cns_lec.py`.
#
# Vista (iot/views_monitoreo.py): ``monitoreo`` en ``/iot/monitoreo/`` (``iot:monitoreo``), ``?invernadero=<id>`` y ``?periodo=<1|6|24|168|720>``; solo GET; Agrónomo y Gerente;
# ``never_cache`` y ``vary_on_headers("HX-Request")``. Con ``HX-Request`` devuelve SOLO el fragmento ``<div id="panel">``; sin él, la página entera.
#
# Cómo se evita que el refresco cierre algo abierto (decisión de IOT-04): los selectores (invernadero y período) están FUERA de ``#panel``, así que el refresco no los toca; dentro
# del panel el único elemento plegable es el bloque de parámetros (``<details>``, cerrado de entrada) y el disparador del refresco AUTOMÁTICO tiene la condición
# ``!document.querySelector('#panel details[open]')``: mientras haya algo abierto, no refresca; «Actualizar» sí (lo pide la persona).

import re
from datetime import timedelta
from html import unescape
from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.models import Hardware, NodoCentral, ResumenHorario
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_tecnico, crear_vendedor

alertas_iot = perezoso("iot.servicios.alertas_iot")

HTMX = {"HTTP_HX_REQUEST": "true"}
CARGA = "<script>alert(1)</script>"
CARGA_ESCAPADA = "&lt;script&gt;alert(1)&lt;/script&gt;"
PERIODOS = ["1", "6", "24", "168", "720"]
OPERACION = ("Registrar este equipo", "Reactivar equipo", "Registrar reemplazo", "Registrar Sistema IoT")


def atributos_del_panel(html):
    """Los atributos de la etiqueta de apertura de ``<div id="panel" …>``, como diccionario (con las entidades ya resueltas)."""
    etiqueta = re.search(r'<div\b[^>]*\bid="panel"[^>]*>', html)
    assert etiqueta is not None, "la respuesta no trae <div id=\"panel\">"
    return {nombre: unescape(valor) for nombre, valor in re.findall(r'([\w:-]+)="([^"]*)"', etiqueta.group(0))}


def enlaces(html):
    """Los ``href`` internos (de iot, configuración y alertas) de una respuesta, sin repetir y en orden."""
    todos = [unescape(h) for h in re.findall(r'href="([^"#][^"]*)"', html)]
    vistos = []
    for href in todos:
        if href.startswith(("/iot/", "/configuracion/", "/alertas/")) and href != "/iot/" and href not in vistos:  # «/iot/» es la entrada del menú: redirige
            vistos.append(href)
    return vistos


class MonitoreoVistasBase(fabricas.ConCatalogoIot, TestCase):
    """Laura es la Agrónoma de Norte (con sistema); Libre no tiene Agrónomo (lo opera el Gerente) y tampoco sistema."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.libre = crear_invernadero("Libre")
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=timezone.now())
        self.url = reverse("iot:monitoreo")

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def pagina(self, cuenta=None, htmx=False, **params):
        if cuenta is not None:
            self.entrar(cuenta)
        return self.client.get(self.url, params, **(HTMX if htmx else {}))

    def armar(self, invernadero, sistema):
        """Un escenario completo: sensores (con lectura), un actuador y una alerta de cada clase (nodo, equipo, lectura, no registrado de un equipo dado de baja y otro)."""
        ahora = timezone.now()
        nodo = NodoCentral.objects.get(sistema=sistema)
        temperatura = fabricas.sensor(sistema, f"{invernadero.nombre_invernadero.lower()}/temperatura")
        nivel = fabricas.sensor(sistema, f"{invernadero.nombre_invernadero.lower()}/nivel", "nivel_solucion")
        for sensor in (temperatura, nivel):
            Hardware.objects.filter(pk=sensor.pk).update(ultimo_mensaje_en=ahora - timedelta(minutes=1))
        fabricas.telemetria(temperatura, "22", medida_en=ahora - timedelta(minutes=1))
        bajo = fabricas.telemetria(nivel, medida_en=ahora - timedelta(minutes=2), estado_nivel_medido="bajo")
        actuador = fabricas.actuador(sistema, identificador=f"{invernadero.nombre_invernadero.lower()}/ventilador", ultimo_mensaje_en=ahora, estado_informado="encendido", estado_informado_en=ahora)
        baja = fabricas.sensor(sistema, f"{invernadero.nombre_invernadero.lower()}/vieja", estado="inactivo", fecha_baja=ahora.date())

        def activa(tipo, clave, descripcion, **origen):
            return alertas_iot.asegurar_alerta_iot(invernadero.pk, sistema, tipo, clave, descripcion, **origen).alerta

        return {
            "nodo": activa("iot_nodo_sin_comunicacion", f"nodo:{nodo.pk}", "Nodo sin comunicación"),
            "equipo": activa("iot_dispositivo_sin_actividad", f"hw:{temperatura.pk}", "Temperatura sin actividad", hardware=temperatura),
            "lectura": activa("iot_nivel_solucion_bajo", f"sensor:{nivel.pk}", "Nivel bajo", telemetria=bajo),
            "de_baja": activa("iot_dispositivo_no_registrado", f"id:{baja.identificador_equipo}", "El nodo envió una lectura de una vieja"),
            "otro": activa("iot_dispositivo_no_registrado", "id:otro/nuevo", "El nodo envió una lectura de otro"),
            "sensores": (temperatura, nivel),
            "actuador": actuador,
            "baja": baja,
        }

    def seguir(self, cuenta, html):
        """Sigue con el cliente cada enlace interno del panel y verifica 200 (ningún botón lleva a un 403, D-30). Devuelve los enlaces seguidos."""
        self.entrar(cuenta)
        seguidos = enlaces(html)
        for href in seguidos:
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200, href)
        return seguidos


class AccesoAMonitoreoVistaTests(MonitoreoVistasBase):
    """Regla 1, precondición a y D-28: quién llega a la pantalla y a qué invernaderos."""

    def test_regla_1_sin_sesion_pide_iniciar_sesion_y_los_otros_roles_reciben_403(self):
        """SEG-13 (precondición a): sin sesión, a iniciar sesión; el Capataz, el Técnico, el Vendedor y el Administrador, 403 (en la página y en el fragmento)."""
        self.assertRedirects(self.client.get(self.url), f"{reverse('core:iniciar_sesion')}?next={self.url}", fetch_redirect_response=False)
        for crear in (crear_capataz, crear_tecnico, crear_vendedor, crear_administrador):
            with self.subTest(rol=crear.__name__):
                cuenta = crear()
                self.assertEqual(self.pagina(cuenta).status_code, 403)
                self.assertEqual(self.pagina(cuenta, htmx=True).status_code, 403)

    def test_regla_1_el_agronomo_y_el_gerente_llegan(self):
        """Regla 1: el Agrónomo y el Gerente activos ven la pantalla (200)."""
        for cuenta in (self.laura, self.gerente):
            with self.subTest(cuenta=cuenta.email):
                self.assertEqual(self.pagina(cuenta).status_code, 200)

    def test_regla_1_un_invernadero_fuera_del_alcance_da_404(self):
        """Regla 1 y D-28: el Agrónomo que pide el invernadero de otro Agrónomo recibe 404 (sin revelar si existe)."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo("ajeno@infoponia.com"))
        fabricas.sistema(ajeno)
        self.assertEqual(self.pagina(self.laura, invernadero=ajeno.pk).status_code, 404)
        self.assertEqual(self.pagina(self.laura, htmx=True, invernadero=ajeno.pk).status_code, 404)
        self.assertEqual(self.pagina(self.gerente, invernadero=ajeno.pk).status_code, 200)

    def test_regla_1_un_invernadero_no_numerico_o_inexistente_da_404_y_uno_vacio_usa_el_recordado(self):
        """Robustez: `?invernadero=` que no es un número, es negativo o no existe es 404 (nunca un 500); vacío, se toma el recordado o el primero del alcance."""
        for valor in ("abc", "-1", "0", "999999", "1e3", "1.5", "NaN", "' OR 1=1"):
            with self.subTest(invernadero=valor):
                self.assertEqual(self.pagina(self.gerente, invernadero=valor).status_code, 404)
        respuesta = self.pagina(self.gerente, invernadero="")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["elegido"], self.libre)  # el primero por nombre de los que consulta: «Libre» < «Norte»

    def test_regla_1_la_pantalla_solo_acepta_get(self):
        """SEG-14: la consulta no cambia nada: un POST, un PUT o un DELETE es 405."""
        self.entrar(self.laura)
        for metodo in (self.client.post, self.client.put, self.client.delete):
            with self.subTest(metodo=metodo.__name__):
                self.assertEqual(metodo(self.url).status_code, 405)

    def test_regla_1_sin_invernaderos_en_el_alcance_la_pantalla_lo_dice(self):
        """Robustez: un Agrónomo sin invernaderos a cargo ve la pantalla con «No hay invernaderos para mostrar» (200), no un error."""
        sin_nada = crear_agronomo("sin@infoponia.com")
        respuesta = self.pagina(sin_nada)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No hay invernaderos para mostrar")


class PeriodoDeMonitoreoVistaTests(MonitoreoVistasBase):
    """Regla 4 y «Ruta y pestaña»: el período se pide por `?periodo=`, se recuerda en la sesión (`iot_periodo`) y por omisión es 24."""

    def test_regla_4_el_periodo_por_omision_es_24(self):
        """«Por omisión, `24`, como el prototipo.»"""
        self.assertEqual(self.pagina(self.laura).context["panel"].periodo, 24)

    def test_regla_4_el_periodo_pedido_rige_y_se_recuerda_en_la_sesion(self):
        """«El período se recuerda en la sesión (`iot_periodo`)»: pedido el de 7 días, la visita siguiente sin `?periodo=` (y el refresco) lo conserva."""
        self.assertEqual(self.pagina(self.laura, periodo="168").context["panel"].periodo, 168)
        self.assertEqual(self.client.session["iot_periodo"], 168)
        self.assertEqual(self.pagina().context["panel"].periodo, 168)
        self.assertEqual(self.pagina(periodo="1").context["panel"].periodo, 1)

    def test_regla_4_un_periodo_invalido_o_no_numerico_usa_el_recordado_o_24_y_no_da_500(self):
        """Robustez: `?periodo=` con algo que no es uno de los cinco (otro número, texto, vacío, decimal, negativo) se ignora: se usa el recordado o, si no hay, 24. Nunca un 500, con y
        sin HTMX, y no pisa el período recordado."""
        for valor in ("12", "abc", "", "24.5", "-24", "999999999999999999999", "1e3", "0", " 24 "):
            with self.subTest(sin_recordado=valor):
                self.client.logout()
                respuesta = self.pagina(self.laura, periodo=valor)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context["panel"].periodo, 24)
        self.pagina(self.laura, periodo="720")
        for valor in ("12", "abc", "", "24.5"):
            for htmx in (False, True):
                with self.subTest(recordado=valor, htmx=htmx):
                    respuesta = self.pagina(periodo=valor, htmx=htmx)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(respuesta.context["panel"].periodo, 720)
        self.assertEqual(self.client.session["iot_periodo"], 720)

    def test_regla_4_siete_dias_dice_que_grafica_los_resumenes_horarios(self):
        """Regla 4: con más de 24 horas, el texto «Más de 24 horas: se grafica el promedio de cada hora (línea) y su mínimo y máximo (franja), con los resúmenes horarios.»; con 24, no."""
        texto = "Más de 24 horas: se grafica el promedio de cada hora (línea) y su mínimo y máximo (franja), con los resúmenes horarios."
        self.assertContains(self.pagina(self.laura, periodo="168"), texto)
        self.assertContains(self.pagina(periodo="720"), texto)
        self.assertNotContains(self.pagina(periodo="24"), texto)

    def test_regla_4_los_dos_periodos_largos_grafican_con_los_resumenes_y_no_con_las_lecturas(self):
        """Regla 4 de punta a punta: con un sensor con lecturas y un resumen de hace 3 días, el de 24 horas dibuja la línea con punto (lecturas) y el de 7 días, la envolvente."""
        self.armar(self.norte, self.sistema)
        temperatura = fabricas.sensor(self.sistema, "norte/extra")
        fabricas.telemetria(temperatura, "21", medida_en=timezone.now())
        ResumenHorario.objects.create(sensor=temperatura, hora=timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=3), minimo=19, promedio=20, maximo=21)
        self.assertContains(self.pagina(self.laura, periodo="24"), "grafico-ultimo")
        respuesta = self.pagina(periodo="168")
        self.assertContains(respuesta, "grafico-envolvente")


class RefrescoDeMonitoreoVistaTests(MonitoreoVistasBase):
    """Regla 9 y «Refresco»: el panel se pide de nuevo con HTMX cada 30 s; el pedido lleva el período y el invernadero; sin JavaScript es la misma página."""

    def test_regla_9_el_pedido_htmx_devuelve_solo_el_fragmento_del_panel(self):
        """«El cuerpo del panel (`<div id="panel">`) se pide de nuevo con HTMX»: con `HX-Request` la respuesta es solo el fragmento (sin `<html>`, sin la barra de contexto ni las pestañas);
        sin él, la página entera, que también trae el panel."""
        completa = self.pagina(self.laura).content.decode()
        fragmento = self.pagina(htmx=True).content.decode()
        self.assertIn("<html", completa)
        self.assertIn('class="ctxbar"', completa)
        self.assertIn('role="tablist"', completa)
        self.assertTrue(fragmento.lstrip().startswith("<div"))
        for ajeno in ("<html", "<head", "ctxbar", "tablist", "<h1"):
            self.assertNotIn(ajeno, fragmento)
        self.assertEqual(fragmento.count('id="panel"'), 1)
        self.assertEqual(completa.count('id="panel"'), 1)

    def test_regla_9_el_hx_get_lleva_el_periodo_y_el_invernadero_y_se_reemplaza_a_si_mismo(self):
        """«`hx-get` a la misma URL con `hx-trigger="every 30s [document.visibilityState === 'visible']"` y `hx-swap="outerHTML"`»: el `hx-get` apunta a `/iot/monitoreo/` con `invernadero` y
        `periodo` (los de lo que se está viendo, también en el fragmento que vuelve) y el disparador tiene la condición de pestaña visible."""
        self.pagina(self.laura, periodo="168")
        for htmx in (False, True):
            with self.subTest(htmx=htmx):
                atributos = atributos_del_panel(self.pagina(htmx=htmx).content.decode())
                destino = urlparse(atributos["hx-get"])
                self.assertEqual(destino.path, self.url)
                self.assertEqual(parse_qs(destino.query), {"invernadero": [str(self.norte.pk)], "periodo": ["168"]})
                self.assertEqual(atributos["hx-swap"], "outerHTML")
                self.assertIn("every 30s", atributos["hx-trigger"])

    def test_regla_9_el_hx_trigger_tiene_cada_30_segundos_la_pestana_visible_y_que_no_haya_nada_abierto(self):
        """«`hx-trigger="every 30s […]"`» con la condición de pestaña visible (`document.visibilityState`) y la de que no haya un `<details>` abierto en el panel (`details[open]`). Se prueba por
        partes y no como texto exacto: lo que importa es que estén las tres, en la misma condición, y no cómo se escribió."""
        for htmx in (False, True):
            with self.subTest(htmx=htmx):
                trigger = atributos_del_panel(self.pagina(self.laura, htmx=htmx).content.decode())["hx-trigger"]
                self.assertRegex(trigger, r"^every 30s\s*\[")
                condicion = trigger[trigger.index("["):]
                self.assertIn("visibilityState", condicion)
                self.assertIn("visible", condicion)
                self.assertIn("details[open]", condicion)
                self.assertIn("!", condicion.split("details[open]")[0][-40:])  # la condición pide que NO haya uno abierto

    def test_regla_9_el_fragmento_trae_su_propio_hx_get_hx_trigger_y_hx_swap_y_el_refresco_sigue(self):
        """Si el fragmento no repitiera sus atributos, el refresco se detendría después del primer reemplazo (el `outerHTML` reemplaza el div que los tenía). Se encadenan tres
        refrescos como lo haría el navegador: cada respuesta HTMX trae un `#panel` con `hx-get`, `hx-trigger` y `hx-swap="outerHTML"`, y el `hx-get` de uno sirve para pedir el siguiente."""
        self.pagina(self.laura, periodo="6")
        atributos = atributos_del_panel(self.pagina().content.decode())
        pedido = atributos["hx-get"]
        for vuelta in range(3):
            with self.subTest(vuelta=vuelta):
                respuesta = self.client.get(pedido, **HTMX)
                self.assertEqual(respuesta.status_code, 200)
                siguiente = atributos_del_panel(respuesta.content.decode())
                self.assertEqual(siguiente["hx-swap"], "outerHTML")
                self.assertIn("every 30s", siguiente["hx-trigger"])
                self.assertEqual(parse_qs(urlparse(siguiente["hx-get"]).query), {"invernadero": [str(self.norte.pk)], "periodo": ["6"]})
                pedido = siguiente["hx-get"]

    def test_regla_9_un_pedido_htmx_sin_sesion_recibe_la_redireccion_al_inicio_de_sesion_y_no_el_panel(self):
        """Sin sesión (por ejemplo, la pestaña abierta cuando venció): el proyecto NO tiene un patrón para esto (solo para la contraseña temporal, que sí usa `HX-Redirect`): manda el
        `LoginRequiredMiddleware` de Django, igual que en todas las pantallas. Lo que se prueba es lo que sí importa: no se filtra ningún dato del panel y no hay un 500. Que HTMX meta la
        pantalla de inicio de sesión dentro del panel queda anotado en `temas_abiertos.md`."""
        respuesta = self.client.get(self.url, {"invernadero": self.norte.pk}, **HTMX)
        self.assertRedirects(respuesta, f"{reverse('core:iniciar_sesion')}?next={self.url}%3Finvernadero%3D{self.norte.pk}", fetch_redirect_response=False)
        self.assertNotIn(b'id="panel"', respuesta.content)

    def test_regla_9_un_pedido_htmx_con_contrasena_temporal_se_redirige_con_hx_redirect(self):
        """El patrón que el proyecto sí tiene (`ContrasenaTemporalMiddleware`, SEG-04): una cuenta con contraseña temporal que pide el panel con HTMX recibe 200 con `HX-Redirect` a
        elegir la contraseña (y no un 302, que HTMX metería dentro del panel)."""
        from core.tests.fabricas import dar_contrasena_temporal

        dar_contrasena_temporal(self.laura)
        self.entrar(self.laura)
        respuesta = self.client.get(self.url, **HTMX)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["HX-Redirect"], reverse("core:elegir_contrasena"))
        self.assertNotIn(b'id="panel"', respuesta.content)

    def test_regla_9_la_respuesta_no_se_guarda_y_varia_por_hx_request(self):
        """`never_cache` y `vary_on_headers("HX-Request")` (como las demás pantallas con fragmento): el navegador no guarda ni la página ni el fragmento, y una caché no confunde uno con el otro."""
        for htmx in (False, True):
            with self.subTest(htmx=htmx):
                respuesta = self.pagina(self.laura, htmx=htmx)
                cache = respuesta["Cache-Control"]
                self.assertTrue("no-store" in cache or "max-age=0" in cache, cache)
                self.assertIn("no-cache", cache)
                self.assertIn("HX-Request", respuesta["Vary"])

    def test_regla_9_el_refresco_no_toca_ni_cierra_los_selectores_ni_lo_que_la_persona_abrio(self):
        """El refresco automático no tiene que cerrar un desplegable ni un `<details>` abierto: (1) los selectores (invernadero y período) están FUERA de `#panel`, así que el
        reemplazo no los toca y el fragmento no los trae; (2) dentro del panel solo hay un `<details>` (los parámetros), cerrado de entrada, y nunca viene un `<details open>`;
        (3) mientras haya uno abierto, el disparador no refresca: su condición es `!document.querySelector('#panel details[open]')`."""
        completa = self.pagina(self.laura).content.decode()
        panel = completa[completa.index('id="panel"'):]
        antes = completa[: completa.index('id="panel"')]
        self.assertIn('name="periodo"', antes)
        self.assertIn('name="invernadero"', antes)
        self.assertNotIn('name="periodo"', panel)
        fragmento = self.pagina(htmx=True).content.decode()
        for selector in ('name="periodo"', "data-desplegable", "<select"):
            self.assertNotIn(selector, fragmento)
        self.assertNotRegex(completa, r"<details[^>]*\bopen\b")
        self.assertEqual(len(re.findall(r"<details\b", fragmento)), 1)
        self.assertIn("details[open]", atributos_del_panel(fragmento)["hx-trigger"])

    def test_regla_9_el_boton_actualizar_pide_lo_mismo_a_mano_y_sin_javascript_recarga(self):
        """«"Actualizar" hace lo mismo a mano»: un enlace «Actualizar» con el mismo `hx-get` que el panel (período e invernadero), `hx-target="#panel"` y `hx-swap="outerHTML"`; sin
        JavaScript es un enlace a la misma página (recargar)."""
        html = self.pagina(self.laura, periodo="6").content.decode()
        boton = re.search(r"<a\b[^>]*>\s*(?:<svg.*?</svg>)?\s*Actualizar\s*</a>", html, re.S)
        self.assertIsNotNone(boton)
        atributos = {n: unescape(v) for n, v in re.findall(r'([\w:-]+)="([^"]*)"', boton.group(0))}
        esperado = atributos_del_panel(html)["hx-get"]
        self.assertEqual((atributos["href"], atributos["hx-get"]), (esperado, esperado))
        self.assertEqual((atributos["hx-target"], atributos["hx-swap"]), ("#panel", "outerHTML"))

    def test_regla_9_abrir_o_refrescar_el_panel_no_escribe_nada(self):
        """Regla 9 y 10: pedir la pantalla (completa o fragmento) no genera alertas, no audita y no toca ninguna fila."""
        from core.models import RegistroAuditoria

        self.armar(self.norte, self.sistema)
        alertas, auditorias = Alerta.objects.count(), RegistroAuditoria.objects.count()
        for htmx in (False, True):
            self.pagina(self.laura, htmx=htmx)
        self.assertEqual((Alerta.objects.count(), RegistroAuditoria.objects.count()), (alertas, auditorias))


class SinJavaScriptMonitoreoVistaTests(MonitoreoVistasBase):
    """«Sin JavaScript, la pantalla es la misma página completa: se actualiza recargándola»; el selector de período es un formulario GET (el `<select>` nativo es el respaldo del desplegable propio, D-24)."""

    def formulario_del_periodo(self, html):
        formulario = re.search(r'<form\b[^>]*\bid="form-periodo"[^>]*>(.*?)</form>', html, re.S)
        self.assertIsNotNone(formulario, "falta el formulario del período (id=form-periodo)")
        return formulario.group(0)

    def test_regla_4_el_selector_de_periodo_es_un_formulario_get_con_su_boton(self):
        """D-24 y regla 4: formulario con `method="get"` a la misma ruta, `<select name="periodo">` con los cinco períodos (el actual, `selected`), el invernadero en un campo oculto, el
        desplegable propio (`data-desplegable`) que lo envía al cambiar y un botón que envía sin JavaScript."""
        html = self.pagina(self.laura, periodo="168").content.decode()
        formulario = self.formulario_del_periodo(html)
        self.assertRegex(formulario, r'method="get"')
        self.assertIn(f'action="{self.url}"', formulario)
        self.assertEqual(re.findall(r'<option value="(\d+)"', formulario), PERIODOS)
        self.assertRegex(formulario, r'<option value="168"[^>]*\bselected\b')
        self.assertEqual(len(re.findall(r"\bselected\b", formulario)), 1)
        self.assertIn("data-desplegable", formulario)
        self.assertIn("data-enviar-al-cambiar", formulario)
        self.assertRegex(formulario, rf'<input[^>]*type="hidden"[^>]*name="invernadero"[^>]*value="{self.norte.pk}"')
        self.assertRegex(formulario, r'<button[^>]*type="submit"')

    def test_regla_4_enviar_el_formulario_sin_javascript_muestra_el_periodo_elegido(self):
        """El envío del formulario (lo que haría el navegador sin JavaScript): un GET con los campos del formulario devuelve la página entera con ese período."""
        html = self.pagina(self.laura).content.decode()
        self.formulario_del_periodo(html)
        for periodo in PERIODOS:
            with self.subTest(periodo=periodo):
                respuesta = self.client.get(self.url, {"invernadero": self.norte.pk, "periodo": periodo})
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "<html")
                self.assertRegex(self.formulario_del_periodo(respuesta.content.decode()), rf'<option value="{periodo}"[^>]*\bselected\b')

    def test_regla_9_con_htmx_el_formulario_reemplaza_el_panel_sin_recargar(self):
        """Con JavaScript, el formulario pide el panel con HTMX (`hx-get` a la misma ruta, `hx-target="#panel"`, `hx-swap="outerHTML"`); sin él, es el GET de arriba."""
        formulario = self.formulario_del_periodo(self.pagina(self.laura).content.decode())
        etiqueta = re.match(r"<form\b[^>]*>", formulario).group(0)
        atributos = dict(re.findall(r'([\w:-]+)="([^"]*)"', etiqueta))
        self.assertEqual((atributos["hx-get"], atributos["hx-target"], atributos["hx-swap"]), (self.url, "#panel", "outerHTML"))

    def test_regla_9_la_pagina_entera_trae_todos_los_bloques_del_panel(self):
        """Sin JavaScript se ve entero: nodo, indicadores, alertas, sensores, actuadores, umbral y parámetros están en la respuesta de servidor (nada se carga después)."""
        self.armar(self.norte, self.sistema)
        html = self.pagina(self.laura).content.decode()
        for bloque in ("Sensores con problema", "Alertas activas", "Actuadores operativos", "Sensores", "Actuadores", "Umbral efectivo", "Parámetros IoT"):
            self.assertIn(bloque, html)


class EscapeDeMonitoreoVistaTests(MonitoreoVistasBase):
    """D-76 punto 8 (seguridad): lo que escribió una persona o llegó del nodo sale escapado, en la página y en el fragmento."""

    def test_un_nombre_con_una_etiqueta_de_script_sale_escapado_en_la_pagina_y_en_el_fragmento(self):
        """El nombre del nodo, el del sector, el de la variedad que compone el umbral, el del tipo de actuador y la descripción de una alerta con `<script>` salen como texto (`&lt;script&gt;`); y
        el nombre del invernadero, en la barra de contexto."""
        hostil = crear_invernadero(CARGA, agronomo=self.laura)
        sistema = fabricas.sistema(hostil)
        NodoCentral.objects.filter(sistema=sistema).update(nombre_nodo=CARGA, ultima_comunicacion=timezone.now())
        sector = crear_sector(hostil, nombre=CARGA)
        sensor = fabricas.sensor(sistema, "hostil/temperatura", sector=sector)
        Hardware.objects.filter(pk=sensor.pk).update(ultimo_mensaje_en=timezone.now())
        fabricas.telemetria(sensor, "22", medida_en=timezone.now())
        fabricas.actuador(sistema, tipo=fabricas.tipo_actuador(nombre=CARGA), identificador="hostil/actuador")
        alertas_iot.asegurar_alerta_iot(hostil.pk, sistema, "iot_dispositivo_no_registrado", "id:x", CARGA)
        self.enterContext(variedades_presentes_de_prueba({hostil.pk: {variedad_con_semilla(nombre=CARGA).pk}}))
        for htmx in (False, True):
            with self.subTest(htmx=htmx):
                contenido = self.pagina(self.laura, htmx=htmx, invernadero=hostil.pk).content.decode()
                self.assertNotIn(CARGA, contenido)
                self.assertGreaterEqual(contenido.count(CARGA_ESCAPADA), 5 if not htmx else 4)


class AccionesDeMonitoreoVistaTests(MonitoreoVistasBase):
    """Regla 11, D-30 y «Pantallas»: cada enlace y botón del panel, seguido con el cliente para cada rol, da 200; quien solo consulta no ve acciones de operación."""

    def test_regla_11_el_agronomo_que_opera_ve_las_acciones_y_todos_los_enlaces_dan_200(self):
        """Regla 11: el Agrónomo que opera Norte ve las acciones de las alertas de «dispositivo no registrado» («Registrar este equipo»; de un equipo dado de baja, «Reactivar equipo» y
        «Registrar reemplazo»); todos los enlaces del panel (pestañas, fichas, altas) dan 200."""
        escenario = self.armar(self.norte, self.sistema)
        html = self.pagina(self.laura).content.decode()
        for texto in ("Registrar este equipo", "Reactivar equipo", "Registrar reemplazo", "Ver equipo"):
            self.assertIn(texto, html)
        seguidos = self.seguir(self.laura, html)
        self.assertIn(f"{reverse('iot:hardware_ficha', args=[escenario['actuador'].pk])}?invernadero={self.norte.pk}", seguidos)
        self.assertIn(f"{reverse('iot:hardware_ficha', args=[escenario['baja'].pk])}?invernadero={self.norte.pk}", seguidos)
        self.assertTrue(any(h.startswith(reverse("iot:hardware_nuevo")) and "identificador=" in h for h in seguidos))

    def test_regla_11_el_gerente_que_opera_un_invernadero_sin_agronomo_tiene_las_mismas_acciones(self):
        """MD-98: el Gerente opera los invernaderos sin Agrónomo activo: ve las acciones de operación y todos sus enlaces dan 200."""
        sistema = fabricas.sistema(self.libre)
        NodoCentral.objects.filter(sistema=sistema).update(ultima_comunicacion=timezone.now())
        self.armar(self.libre, sistema)
        html = self.pagina(self.gerente, invernadero=self.libre.pk).content.decode()
        for texto in ("Registrar este equipo", "Reactivar equipo", "Registrar reemplazo"):
            self.assertIn(texto, html)
        self.seguir(self.gerente, html)

    def test_regla_11_el_gerente_que_solo_consulta_no_ve_acciones_de_operacion_y_sus_enlaces_dan_200(self):
        """Regla 11 («quien solo consulta no tiene acciones») y D-30: el Gerente que mira Norte (con Agrónomo) no ve «Registrar este equipo», «Reactivar equipo», «Registrar reemplazo» ni
        «Registrar Sistema IoT», ni enlaces al alta o al registro; lo que sí ve (las fichas, las pestañas, «Modificar parámetros») da 200. Las alertas se marcan también para el Gerente
        para que haya filas de «no registrado» que mirar."""
        self.armar(self.norte, self.sistema)
        Alerta.objects.filter(tipo_alerta="iot_dispositivo_no_registrado").update(para_gerente=True)
        html = self.pagina(self.gerente, invernadero=self.norte.pk).content.decode()
        self.assertIn("El nodo envió una lectura de otro", html)
        for texto in OPERACION:
            self.assertNotIn(texto, html)
        seguidos = self.seguir(self.gerente, html)
        for ruta in (reverse("iot:hardware_nuevo"), reverse("iot:sistema_registrar")):
            self.assertFalse([h for h in seguidos if h.startswith(ruta)], ruta)
        self.assertIn(reverse("configuracion:pantalla"), [h.split("?")[0] for h in seguidos])

    def test_regla_11_registrar_sistema_iot_solo_lo_ve_quien_opera_un_invernadero_sin_sistema(self):
        """Precondición b: «Registrar Sistema IoT» (enlace al registro del invernadero) solo a quien opera: el Gerente en «Libre» (sin Agrónomo), sí; el Gerente que mira un invernadero con
        Agrónomo y sin sistema, no; el Agrónomo en el suyo, sí. Los que lo ven, lo siguen y reciben 200."""
        propio = crear_invernadero("Propio", agronomo=self.laura)
        registro = lambda inv: f"{reverse('iot:sistema_registrar')}?invernadero={inv.pk}"
        for cuenta, invernadero, ve in ((self.gerente, self.libre, True), (self.gerente, propio, False), (self.laura, propio, True)):
            with self.subTest(cuenta=cuenta.email, invernadero=invernadero.nombre_invernadero):
                html = self.pagina(cuenta, invernadero=invernadero.pk).content.decode()
                self.assertIn(f"{invernadero.nombre_invernadero} no tiene Sistema IoT", html)
                self.assertEqual("Registrar Sistema IoT" in html, ve)
                self.assertEqual(registro(invernadero) in enlaces(html), ve)
                if ve:
                    self.assertEqual(self.client.get(registro(invernadero)).status_code, 200)

    def test_regla_6_el_agronomo_ve_los_parametros_sin_modificar_parametros_y_el_gerente_con_el_enlace(self):
        """D-76 punto 9: los 14 parámetros IoT se ven en el panel, en un bloque plegable de solo lectura; «Modificar parámetros» (a Configuración operativa) solo se le ofrece al Gerente (la
        pantalla es suya: al Agrónomo le daría 403)."""
        del_agronomo = self.pagina(self.laura).content.decode()
        del_gerente = self.pagina(self.gerente, invernadero=self.norte.pk).content.decode()
        for html in (del_agronomo, del_gerente):
            self.assertIn("Parámetros IoT", html)
            self.assertIn("Minutos sin actividad", html)
            self.assertEqual(len(re.findall(r"<details\b", html)), 1)
        self.assertNotIn("Modificar parámetros", del_agronomo)
        self.assertNotIn(reverse("configuracion:pantalla"), enlaces(del_agronomo))
        self.assertIn("Modificar parámetros", del_gerente)
        self.assertIn(reverse("configuracion:pantalla"), [h.split("?")[0] for h in enlaces(del_gerente)])

    def test_regla_7_el_gerente_que_no_opera_ve_el_aviso_de_quien_recibe_las_alertas(self):
        """Decisión de la pausa 2: el texto «Las alertas de este invernadero las recibe {Agrónomo}; vos las recibís si no tiene un Agrónomo activo.» se ve en el bloque de alertas del Gerente que
        no opera; el Agrónomo no lo ve."""
        nombre = self.laura.get_full_name() or self.laura.email
        texto = f"Las alertas de este invernadero las recibe {nombre}; vos las recibís si no tiene un Agrónomo activo."
        self.assertContains(self.pagina(self.gerente, invernadero=self.norte.pk), texto)
        self.assertNotContains(self.pagina(self.laura), texto)

    def test_regla_7_la_alerta_notificada_por_correo_lo_dice(self):
        """Regla 7: «Notificada por correo» en la fila de la alerta si `correo_enviado_en` no es nulo."""
        escenario = self.armar(self.norte, self.sistema)
        self.assertNotContains(self.pagina(self.laura), "Notificada por correo")
        from iot.models import AlertaIot

        AlertaIot.objects.filter(alerta=escenario["nodo"]).update(correo_enviado_en=timezone.now())
        self.assertContains(self.pagina(self.laura), "Notificada por correo")


class PestanaDeMonitoreoVistaTests(MonitoreoVistasBase):
    """«Ruta y pestaña»: «Monitoreo» es la primera pestaña del módulo y está activa en esta pantalla."""

    def test_monitoreo_es_la_primera_pestana_y_esta_activa(self):
        """La pestaña «Monitoreo» es la primera (como `NAV` del prototipo), con `aria-selected="true"` en esta pantalla y enlace a `/iot/monitoreo/` con el invernadero elegido; las demás
        siguen (Comandos, que suma IOT-05, Hardware, Sistema IoT, Tipos de actuador)."""
        html = self.pagina(self.laura).content.decode()
        pestanas = re.findall(r'<a class="tab"[^>]*>([^<]+)</a>', html)
        self.assertEqual(pestanas, ["Monitoreo", "Comandos", "Hardware", "Sistema IoT", "Tipos de actuador"])
        primera = re.search(r'<a class="tab"[^>]*>Monitoreo</a>', html).group(0)
        self.assertIn('aria-selected="true"', primera)
        self.assertIn(f"{self.url}?invernadero={self.norte.pk}", unescape(primera))

    def test_las_otras_pantallas_del_modulo_tambien_traen_la_pestana_monitoreo_sin_estar_activa(self):
        """Las pestañas son compartidas (`_pestanas.html`): desde «Hardware», «Monitoreo» aparece primero y sin `aria-selected`."""
        self.entrar(self.laura)
        html = self.client.get(reverse("iot:hardware"), {"invernadero": self.norte.pk}).content.decode()
        self.assertEqual(re.findall(r'<a class="tab"[^>]*>([^<]+)</a>', html)[0], "Monitoreo")
        self.assertNotIn('aria-selected="true"', re.search(r'<a class="tab"[^>]*>Monitoreo</a>', html).group(0))

    def test_inicio_del_modulo_redirige_a_monitoreo(self):
        """«Desde IOT-04, `/iot/` redirige a «Monitoreo» (IOT-02 la llevaba a «Sistema IoT»)»; lo prueban también, con su `assertRedirects`, las pruebas de sistema y de tipos."""
        self.entrar(self.laura)
        self.assertRedirects(self.client.get(reverse("iot:inicio")), reverse("iot:monitoreo"), fetch_redirect_response=False)
