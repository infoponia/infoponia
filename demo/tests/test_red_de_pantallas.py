# Red de pantallas (UI-02; D-109 punto 3; `.claude/rules/interfaz.md`, «Revisión de interfaz»). Carga UNA vez los datos de la demo (como
# `test_recorrido_demo.py`), entra con cada una de las diez cuentas y recorre sus pantallas siguiendo los enlaces internos desde «/» (hasta
# 120 por cuenta); después pide cada ruta GET sin parámetros que el recorrido no visitó. Para cada pantalla comprueba que (a) no da 500,
# (b) da el código de la línea de base `demo/tests/datos/pantallas_esperadas.json` y (c) su texto visible no tiene códigos internos
# (tareas, casos de uso, decisiones, rondas). Los códigos de documento del negocio («OT-0004», «SUM-0001», «COB-0001») están permitidos.
#
# La red solo ve lo que la demo muestra con GET: los textos que salen después de un POST los cubre el escaneo de fuentes del final de este
# archivo (plantillas, `messages.*` de las vistas y las cadenas de servicios y vistas), con los mismos patrones.
#
# Línea de base: se genera con `RED_PANTALLAS_ESCRIBIR=1` y nunca se regenera sin revisar la diferencia (en el «Cierre» de la tarea va
# cuántas líneas cambiaron y por qué). Las rutas se guardan normalizadas (la ruta del resolvedor, con `<int:pk>`, y en la consulta los
# dígitos como «N»), porque los `pk` cambian entre corridas con `--keepdb` y las fechas cambian cada día.
#
# UI-03 (D-109 punto 8) suma cuatro controles de accesibilidad que leen el HTML de cada pantalla: toda `<th>` con texto, ningún `<a>`
# con `aria-pressed`, todo campo con etiqueta y títulos sin saltos de nivel después del `h1` (`_LectorDeAccesibilidad`).
#
# Variables de entorno para revisar la red (no cambian lo que la prueba exige):
# - `RED_PANTALLAS_ESCRIBIR=1`: escribe la línea de base con lo que ve.
# - `RED_PANTALLAS_DIAS=N`: corre la carga y el recorrido con «hoy» corrido N días (todo el sistema toma la fecha de
#   `django.utils.timezone`), para comprobar que la línea de base no depende del día en que corre.
# - `RED_PANTALLAS_TOPE=N`: otro tope de pantallas por cuenta para la fase de enlaces (por defecto, 120).
# - `RED_PANTALLAS_INFORME=<archivo>`: escribe en ese archivo un informe JSON con cada visita, su fase, de qué pantalla y enlace
#   salió, las cuentas que llegaron al tope y el tiempo.

import ast
import json
import os
import re
import secrets
import sys
import time
from collections import deque, namedtuple
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.apps import apps
from django.conf import settings
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.signals import got_request_exception
from django.db import transaction
from django.test import Client, SimpleTestCase, TestCase
from django.urls import Resolver404, URLResolver, get_resolver, resolve, reverse
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from demo import carga
from inventario.tests.fabricas import ConDatosDeInventario

BASE = "ejemplo"
# La tarea proponía 120; con la campana contada una sola vez (ver `clave_de_recorrido`) el recorrido completo de la demo son unas 2.000
# pantallas (la cuenta más grande, el Gerente, unas 620) y tarda unos 65 s. Con 1.000 ninguna cuenta llega al tope y la cobertura no
# depende del orden de los enlaces; si una cuenta llega, la prueba lo avisa (decisión del estudiante al revisar el paso 1, 27/11/2026).
TOPE_DEL_RECORRIDO = int(os.environ.get("RED_PANTALLAS_TOPE") or 1000)
DIAS_DE_CORRIMIENTO = int(os.environ.get("RED_PANTALLAS_DIAS") or 0)
LINEA_DE_BASE = Path(__file__).parent / "datos" / "pantallas_esperadas.json"
EXCLUIDAS = ("/admin/", "/api/", "/static/", "/media/")
EXCLUIDAS_EN_CUALQUIER_PARTE = ("cerrar-sesion", "cambiar-de-cuenta")

# Patrones de códigos internos (D-109 punto 7; UI-02, paso 1). Los códigos de documento de cuatro dígitos no coinciden con ninguno.
# Los cuatro primeros son los de la tarea; los demás los sumó el estudiante al revisar el paso 1 (27/11/2026).
PATRONES_PROHIBIDOS = (
    re.compile(r"\b(USR|AUD|MAE|INV|PRD|PROD|CMP|COM|IOT|CON|UI|DOC|DIA|EST|SEG|NOT|DAT|ADM)-\d{2}[a-z]?\b"),  # tareas
    re.compile(r"\b[A-Z]{3,4}-[A-Z]{3}-[A-Z]{3}\b"),  # códigos de caso de uso («COM-REG-CBR»)
    re.compile(r"\bD-\d{2,3}\b"),  # decisiones
    re.compile(r"\brondas?\b", re.IGNORECASE),
    re.compile(r"\bMD-\d{2,3}\b"),  # decisiones del modelo de dominio
    re.compile(r"\bUX-\d{2}\b"),  # hallazgos de la revisión de interfaz
    re.compile(r"\bCU-\d{2,3}\b"),  # casos de uso originales
    re.compile(r"\breglas? \d+[a-z]? de\b", re.IGNORECASE),  # «regla 9 de 8.13», «regla 3 de CON-CNS-PCT»
)

# Una pantalla pedida: la cuenta, la ruta, su código, el texto visible (solo en 200 con HTML), la excepción si dio 500, la fase
# («enlace» o «ruta suelta») y de dónde salió: lista de (pantalla de origen, enlace tal como estaba escrito).
Visita = namedtuple("Visita", "cuenta ruta codigo texto error fase origenes accesibilidad")


def codigos_internos(texto):
    """Lista de los códigos internos que aparecen en ``texto`` (sin repetir, en orden de aparición)."""
    encontrados = []
    for patron in PATRONES_PROHIBIDOS:
        for coincidencia in patron.finditer(texto):
            if coincidencia.group(0) not in encontrados:
                encontrados.append(coincidencia.group(0))
    return encontrados


class _LectorDeHtml(HTMLParser):
    """Junta el texto visible de una página (sin comentarios, ``<script>`` ni ``<style>``; con ``placeholder``, ``title``, ``alt`` y
    ``aria-label``) y los ``href`` de sus enlaces."""

    ATRIBUTOS_DE_TEXTO = ("placeholder", "title", "alt", "aria-label")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.textos = []
        self.enlaces = []
        self._oculto = 0  # profundidad dentro de <script> o <style>

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta in ("script", "style"):
            self._oculto += 1
        for nombre, valor in atributos:
            if valor and nombre in self.ATRIBUTOS_DE_TEXTO:
                self.textos.append(valor)
            if etiqueta == "a" and nombre == "href" and valor:
                self.enlaces.append(valor)

    def handle_endtag(self, etiqueta):
        if etiqueta in ("script", "style") and self._oculto:
            self._oculto -= 1

    def handle_data(self, datos):
        if not self._oculto:
            self.textos.append(datos)


def leer_html(html):
    """``(texto visible, enlaces)`` de una página."""
    lector = _LectorDeHtml()
    lector.feed(html)
    lector.close()
    return " ".join(lector.textos), lector.enlaces


# ---- controles de accesibilidad (UI-03; D-109 punto 8) ----

TH_SIN_TEXTO = "th sin texto"
ENLACE_CON_ARIA_PRESSED = "enlace con aria-pressed"
CAMPO_SIN_ETIQUETA = "campo sin etiqueta"
SALTO_DE_TITULO = "salto de título"
CONTROLES_DE_ACCESIBILIDAD = (TH_SIN_TEXTO, ENLACE_CON_ARIA_PRESSED, CAMPO_SIN_ETIQUETA, SALTO_DE_TITULO)

# Los `input` que no son campos para escribir o elegir: no necesitan etiqueta (UI-03, paso 1).
TIPOS_DE_INPUT_SIN_ETIQUETA = ("hidden", "submit", "button", "reset", "image")
TITULOS = ("h1", "h2", "h3", "h4", "h5", "h6")


def _sin_digitos(texto):
    """``texto`` con los números como «N»: los `id`, los `name` con `pk` y los contadores cambian entre corridas. Los niveles de
    título («h1 → h3») se conservan."""
    return re.sub(r"(?<!\bh)\d+", "N", " ".join(texto.split()))


class _LectorDeAccesibilidad(HTMLParser):
    """Lee una página y junta lo que miran los cuatro controles de UI-03 (D-109 punto 8): las filas con algún ``<th>`` sin texto,
    los ``<a>`` con ``aria-pressed``, los campos (``input`` que no sea de `TIPOS_DE_INPUT_SIN_ETIQUETA`, ``select``, ``textarea``,
    salvo los que tienen ``aria-hidden="true"``) sin etiqueta asociada y los títulos que saltan niveles después del primer ``h1``. Lee el HTML, no el CSS: una etiqueta con
    ``display:none`` cuenta como etiqueta."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problemas = {control: [] for control in CONTROLES_DE_ACCESIBILIDAD}
        self._oculto = 0  # dentro de <script> o <style>
        # Encabezados de la fila actual: [texto, tiene_aria_label] por cada <th>; el <th> abierto es el último.
        self._fila = []
        self._en_th = 0
        # Enlace abierto con aria-pressed: su texto se junta hasta cerrarlo.
        self._enlace = None
        # Campos y etiquetas: se resuelven al cerrar, porque la <label for> puede venir antes o después del campo.
        self._campos = []
        self._etiquetas_for = set()
        self._en_label = 0
        # Títulos: (nivel, texto) en orden; el abierto es el último.
        self._titulos = []
        self._en_titulo = False

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        if etiqueta in ("script", "style"):
            self._oculto += 1
        elif etiqueta == "tr":
            self._fila = []
        elif etiqueta == "th":
            self._fila.append(["", bool((atributos.get("aria-label") or "").strip())])
            self._en_th += 1
        elif etiqueta == "a" and "aria-pressed" in atributos:
            self._enlace = {"href": atributos.get("href") or "", "texto": ""}
        elif etiqueta == "label":
            self._en_label += 1
            if atributos.get("for"):
                self._etiquetas_for.add(atributos["for"])
        elif etiqueta in ("input", "select", "textarea"):
            tipo = (atributos.get("type") or "text").lower() if etiqueta == "input" else etiqueta
            # Un campo con aria-hidden="true" no llega al lector de pantalla (el `username` oculto para el administrador de
            # contraseñas de Mi perfil y de elegir contraseña): no necesita etiqueta.
            if tipo not in TIPOS_DE_INPUT_SIN_ETIQUETA and atributos.get("aria-hidden") != "true":
                self._campos.append(
                    {
                        "descripcion": f"{etiqueta}{'' if etiqueta != 'input' else '[' + tipo + ']'} "
                        f"name={atributos.get('name') or '—'} id={atributos.get('id') or '—'}",
                        "id": atributos.get("id"),
                        "etiquetado": self._en_label > 0
                        or bool((atributos.get("aria-label") or "").strip())
                        or bool((atributos.get("aria-labelledby") or "").strip()),
                    }
                )
        elif etiqueta in TITULOS:
            self._titulos.append([int(etiqueta[1]), ""])
            self._en_titulo = True

    def handle_endtag(self, etiqueta):
        if etiqueta in ("script", "style") and self._oculto:
            self._oculto -= 1
        elif etiqueta == "th" and self._en_th:
            self._en_th -= 1
        elif etiqueta == "tr":
            self._cerrar_fila()
        elif etiqueta == "a" and self._enlace is not None:
            self.problemas[ENLACE_CON_ARIA_PRESSED].append(
                f"«{' '.join(self._enlace['texto'].split())}» → {self._enlace['href']}"
            )
            self._enlace = None
        elif etiqueta == "label" and self._en_label:
            self._en_label -= 1
        elif etiqueta in TITULOS:
            self._en_titulo = False

    def handle_data(self, datos):
        if self._oculto:
            return
        if self._en_th and self._fila:
            self._fila[-1][0] += datos
        if self._enlace is not None:
            self._enlace["texto"] += datos
        if self._en_titulo and self._titulos:
            self._titulos[-1][1] += datos

    def _cerrar_fila(self):
        """Si la fila tiene algún ``<th>`` sin texto ni ``aria-label``, la anota con sus encabezados («∅» el vacío)."""
        if any(not texto.strip() and not aria for texto, aria in self._fila):
            encabezados = " | ".join(" ".join(texto.split()) or ("(aria-label)" if aria else "∅") for texto, aria in self._fila)
            self.problemas[TH_SIN_TEXTO].append(encabezados)
        self._fila = []

    def close(self):
        super().close()
        self._cerrar_fila()
        for campo in self._campos:
            if not campo["etiquetado"] and not (campo["id"] and campo["id"] in self._etiquetas_for):
                self.problemas[CAMPO_SIN_ETIQUETA].append(campo["descripcion"])
        anterior = None
        for nivel, texto in self._titulos:
            if anterior is None:
                if nivel == 1:
                    anterior = 1  # los títulos de antes del primer h1 (el marco) no cuentan
                continue
            if nivel > anterior + 1:
                self.problemas[SALTO_DE_TITULO].append(f"h{anterior} → h{nivel} «{' '.join(texto.split())}»")
            anterior = nivel


def problemas_de_accesibilidad(html):
    """``{control: [problemas]}`` de una página, con los números de cada problema como «N» y sin repetir."""
    lector = _LectorDeAccesibilidad()
    lector.feed(html)
    lector.close()
    return {control: sorted({_sin_digitos(p) for p in problemas}) for control, problemas in lector.problemas.items()}


def ruta_interna(href):
    """La ruta y la consulta de un enlace interno (``/…`` o ``http://testserver/…``), sin el fragmento; ``None`` si no es interno o si
    está excluido."""
    partes = urlsplit(href)
    if partes.scheme and partes.netloc != "testserver":
        return None
    if not partes.scheme and (partes.netloc or not partes.path.startswith("/")):
        return None  # «//otro.sitio/…», relativos, «mailto:», «#…»
    ruta = partes.path + (f"?{partes.query}" if partes.query else "")
    if ruta.startswith(EXCLUIDAS) or any(parte in ruta for parte in EXCLUIDAS_EN_CUALQUIER_PARTE):
        return None
    return ruta


def _consulta_sin_rutas(consulta):
    """Los pares de la consulta, ordenados y sin repetir, con «*» en los valores que son una ruta (``next=/compras/``): la campana de cada
    pantalla lleva la pantalla actual en ``next``, y sin esto cada página daría una campana «nueva» que se come el tope del recorrido."""
    return sorted(
        {(clave, "*" if valor.startswith("/") else valor) for clave, valor in parse_qsl(consulta, keep_blank_values=True)}
    )


def clave_de_recorrido(ruta):
    """Qué cuenta como la misma pantalla en el recorrido: la misma ruta y la misma consulta, salvo los valores que son una ruta."""
    partes = urlsplit(ruta)
    return partes.path + (f"?{urlencode(_consulta_sin_rutas(partes.query))}" if partes.query else "")


def ruta_normalizada(ruta):
    """La ruta como la escribe el resolvedor (``/produccion/invernaderos/<int:pk>/``) y la consulta ordenada, con los dígitos de los
    valores como «N» y «*» en los valores que son una ruta. Si la ruta no resuelve, sus dígitos pasan a «N»."""
    partes = urlsplit(ruta)
    try:
        camino = "/" + resolve(partes.path).route
    except Resolver404:
        camino = re.sub(r"\d+", "N", partes.path)
    if not partes.query:
        return camino
    pares = sorted({(clave, re.sub(r"\d+", "N", valor)) for clave, valor in _consulta_sin_rutas(partes.query)})
    return f"{camino}?{urlencode(pares)}"


def rutas_sin_parametros():
    """Las rutas del proyecto que no llevan parámetros, con «/» adelante, sin las excluidas."""
    rutas = []

    def recorrer(patrones, prefijo):
        for patron in patrones:
            texto = prefijo + str(patron.pattern)
            if isinstance(patron, URLResolver):
                recorrer(patron.url_patterns, texto)
            elif "<" not in texto and not re.search(r"[\^$()\[\]*+?\\]", texto):
                rutas.append("/" + texto)

    recorrer(get_resolver().url_patterns, "")
    return sorted({r for r in rutas if ruta_interna(r) is not None})


class RedDePantallasTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """UI-02 paso 1 (D-109 punto 3): la red de pantallas con los datos de la demo y las diez cuentas."""

    @classmethod
    def setUpTestData(cls):
        inicio = time.monotonic()
        ahora_real = timezone.now
        with mock.patch("django.utils.timezone.now", lambda: ahora_real() + timedelta(days=DIAS_DE_CORRIMIENTO)):
            contrasena = secrets.token_urlsafe(12)
            carga.cargar(carga.Contexto(hoy=timezone.localdate(), base=BASE, contrasena=contrasena))
            cls.visitas, cls.problemas_de_ingreso, cls.cuentas_en_el_tope = cls._recorrer(contrasena)
        if os.environ.get("RED_PANTALLAS_ESCRIBIR") == "1":
            cls._escribir_linea_de_base(cls.visitas)
        if os.environ.get("RED_PANTALLAS_INFORME"):
            cls._escribir_informe(Path(os.environ["RED_PANTALLAS_INFORME"]), time.monotonic() - inicio)

    # ---- el recorrido ----

    @classmethod
    def _recorrer(cls, contrasena):
        """Recorre las pantallas de cada cuenta. Devuelve ``(visitas, problemas_de_ingreso, cuentas_que_llegaron_al_tope)``."""
        visitas, problemas, en_el_tope = [], [], []
        excepciones = []

        def anotar_excepcion(sender, request=None, **kwargs):
            excepciones.append(repr(sys.exc_info()[1])[:300])

        got_request_exception.connect(anotar_excepcion)
        try:
            todas = rutas_sin_parametros()
            for clave, *_ in carga.CUENTAS:
                cliente = Client(raise_request_exception=False)
                ingreso = cliente.post(
                    reverse("core:iniciar_sesion"), {"username": f"{BASE}+{clave}@gmail.com", "password": contrasena}
                )
                if ingreso.status_code != 302:
                    problemas.append(f"{clave}: no pudo iniciar sesión (código {ingreso.status_code})")
                    continue
                sesion = cliente.cookies[settings.SESSION_COOKIE_NAME].value
                visitadas = set()  # claves de recorrido ya pedidas
                pendientes = deque(["/"])
                origenes = {"/": []}  # clave de recorrido -> [(pantalla de origen, enlace escrito)]; está encolada si tiene entrada

                def pedir(ruta, fase):
                    """Un GET aislado: la sesión de siempre, sin avisos pendientes, y todo lo que la vista escriba se deshace."""
                    cliente.cookies[settings.SESSION_COOKIE_NAME] = sesion
                    cliente.cookies.pop(CookieStorage.cookie_name, None)
                    excepciones.clear()
                    with transaction.atomic():
                        respuesta = cliente.get(ruta)
                        transaction.set_rollback(True)
                    visitadas.add(clave_de_recorrido(ruta))
                    texto, enlaces, accesibilidad = None, [], None
                    tipo = respuesta.get("Content-Type", "")
                    if respuesta.status_code == 200 and tipo.startswith("text/html"):
                        html = respuesta.content.decode(respuesta.charset or "utf-8", errors="replace")
                        texto, enlaces = leer_html(html)
                        accesibilidad = problemas_de_accesibilidad(html)
                    elif 300 <= respuesta.status_code < 400 and respuesta.get("Location"):
                        enlaces = [respuesta["Location"]]
                    visitas.append(
                        Visita(
                            clave, ruta, respuesta.status_code, texto, excepciones[0] if excepciones else None, fase,
                            list(origenes.get(clave_de_recorrido(ruta), [])), accesibilidad,
                        )
                    )
                    return enlaces

                while pendientes and len(visitadas) < TOPE_DEL_RECORRIDO:
                    ruta = pendientes.popleft()
                    for enlace in pedir(ruta, "enlace"):
                        interna = ruta_interna(enlace)
                        if not interna:
                            continue
                        clave_interna = clave_de_recorrido(interna)
                        if clave_interna not in origenes:
                            origenes[clave_interna] = []
                            pendientes.append(interna)  # se pide la primera forma concreta que apareció
                        origenes[clave_interna].append((ruta, enlace))
                if pendientes:
                    en_el_tope.append(clave)
                for ruta in todas:
                    if clave_de_recorrido(ruta) not in visitadas:
                        pedir(ruta, "ruta suelta")
        finally:
            got_request_exception.disconnect(anotar_excepcion)
        return visitas, problemas, en_el_tope

    @staticmethod
    def _triples(visitas):
        """El conjunto de ``(cuenta, ruta normalizada, código)`` de las visitas."""
        return {(v.cuenta, ruta_normalizada(v.ruta), v.codigo) for v in visitas}

    @classmethod
    def _escribir_informe(cls, archivo, segundos):
        """El informe de `RED_PANTALLAS_INFORME`: cada visita (sin el texto), las cuentas que llegaron al tope y el tiempo."""
        visitas = [
            {"cuenta": v.cuenta, "ruta": v.ruta, "normalizada": ruta_normalizada(v.ruta), "codigo": v.codigo, "fase": v.fase, "origenes": v.origenes}
            for v in cls.visitas
        ]
        informe = {
            "dias_de_corrimiento": DIAS_DE_CORRIMIENTO,
            "tope": TOPE_DEL_RECORRIDO,
            "segundos": round(segundos, 1),
            "cuentas_en_el_tope": cls.cuentas_en_el_tope,
            "visitas": visitas,
        }
        archivo.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def _escribir_linea_de_base(cls, visitas):
        """Escribe la línea de base (una línea por pantalla, ordenada) para que la diferencia se lea en el PR."""
        LINEA_DE_BASE.parent.mkdir(parents=True, exist_ok=True)
        lineas = [json.dumps(list(t), ensure_ascii=False) for t in sorted(cls._triples(visitas))]
        LINEA_DE_BASE.write_text("[\n" + ",\n".join(lineas) + "\n]\n", encoding="utf-8")

    # ---- las comprobaciones ----

    def test_ui02_cada_cuenta_entra_y_recorre_sus_pantallas(self):
        """D-109 punto 3: las diez cuentas de la demo entran y la red pide más de una pantalla por cuenta (que no pase sin revisar nada)."""
        self.assertEqual(self.problemas_de_ingreso, [])
        por_cuenta = {}
        for visita in self.visitas:
            por_cuenta[visita.cuenta] = por_cuenta.get(visita.cuenta, 0) + 1
        self.assertEqual(set(por_cuenta), {clave for clave, *_ in carga.CUENTAS})
        self.assertTrue(all(n > 1 for n in por_cuenta.values()), por_cuenta)
        # Si una cuenta llega al tope, qué pantallas con id se ven depende del orden de los enlaces: hay que subirlo.
        self.assertEqual(self.cuentas_en_el_tope, [], f"Llegaron al tope de {TOPE_DEL_RECORRIDO} pantallas: subilo.")

    def test_ui02_ninguna_pantalla_da_500(self):
        """D-109 punto 3 (a): ninguna pantalla de ninguna cuenta responde 500."""
        errores = [f"{v.cuenta} · {v.ruta} · {v.error}" for v in self.visitas if v.codigo >= 500]
        self.assertEqual(errores, [], "Pantallas con error del servidor:\n" + "\n".join(errores))

    def test_ui02_cada_pantalla_da_el_codigo_de_la_linea_de_base(self):
        """D-109 punto 3 (b): cada pantalla da el código que guarda `pantallas_esperadas.json`. Falla si aparece una pantalla o un código
        nuevo, y si desaparece una ruta sin parámetros (esas se piden siempre). Si una tarea cambia una pantalla a propósito, regenera el
        JSON con `RED_PANTALLAS_ESCRIBIR=1` y explica la diferencia en su «Cierre»."""
        self.assertTrue(LINEA_DE_BASE.exists(), "Falta la línea de base: corré esta prueba con RED_PANTALLAS_ESCRIBIR=1.")
        esperadas = {tuple(t) for t in json.loads(LINEA_DE_BASE.read_text(encoding="utf-8"))}
        observadas = self._triples(self.visitas)
        nuevas = sorted(observadas - esperadas)
        faltan = sorted(t for t in esperadas - observadas if "<" not in t[1] and "?" not in t[1])
        mensaje = []
        if nuevas:
            mensaje.append("No están en la línea de base:\n" + "\n".join(f"{c} · {r} · {n}" for c, r, n in nuevas))
        if faltan:
            mensaje.append("Están en la línea de base y no se vieron:\n" + "\n".join(f"{c} · {r} · {n}" for c, r, n in faltan))
        self.assertEqual(mensaje, [], "\n".join(mensaje))

    def test_ui02_ninguna_pantalla_muestra_codigos_internos(self):
        """D-109 puntos 3 y 7: el texto visible de las pantallas (con `placeholder`, `title`, `alt` y `aria-label`) no nombra tareas, casos
        de uso, decisiones ni rondas."""
        hallazgos = {}
        for v in self.visitas:
            if v.texto:
                for codigo_interno in codigos_internos(v.texto):
                    hallazgos.setdefault((ruta_normalizada(v.ruta), codigo_interno), set()).add(v.cuenta)
        lineas = [f"{', '.join(sorted(cuentas))} · {ruta} · {codigo}" for (ruta, codigo), cuentas in sorted(hallazgos.items())]
        self.assertEqual(lineas, [], "Códigos internos a la vista:\n" + "\n".join(lineas))

    # ---- accesibilidad (UI-03; D-109 punto 8) ----

    def _inventario_de(self, control):
        """Las líneas «cuentas · ruta · problema» de un control de accesibilidad, agrupadas por ruta normalizada y problema."""
        hallazgos = {}
        paginas = 0
        for v in self.visitas:
            if v.accesibilidad is None:
                continue
            paginas += 1
            for problema in v.accesibilidad[control]:
                hallazgos.setdefault((ruta_normalizada(v.ruta), problema), set()).add(v.cuenta)
        self.assertGreater(paginas, 100)  # que el control no pase sin revisar nada
        return [f"{', '.join(sorted(cuentas))} · {ruta} · {problema}" for (ruta, problema), cuentas in sorted(hallazgos.items())]

    def test_ui03_toda_th_tiene_texto(self):
        """D-109 punto 8 (UX-09): todo encabezado de tabla tiene texto, visible o solo para lectores de pantalla («Acciones»)."""
        lineas = self._inventario_de(TH_SIN_TEXTO)
        self.assertEqual(lineas, [], "Filas de encabezado con un <th> sin texto (∅):\n" + "\n".join(lineas))

    def test_ui03_ningun_enlace_tiene_aria_pressed(self):
        """D-109 punto 8 (UX-10): la vista activa se marca con `aria-current="page"` (o `aria-selected` con `role="tab"`); `aria-pressed`
        solo vale en un botón."""
        lineas = self._inventario_de(ENLACE_CON_ARIA_PRESSED)
        self.assertEqual(lineas, [], "Enlaces con aria-pressed:\n" + "\n".join(lineas))

    def test_ui03_todo_campo_tiene_etiqueta(self):
        """D-109 punto 8 (UX-11): todo campo visible tiene una etiqueta asociada (`<label for>`, una `<label>` que lo envuelve,
        `aria-label` o `aria-labelledby`)."""
        lineas = self._inventario_de(CAMPO_SIN_ETIQUETA)
        self.assertEqual(lineas, [], "Campos sin etiqueta:\n" + "\n".join(lineas))

    def test_ui03_los_titulos_no_saltan_niveles(self):
        """D-109 punto 8 (UX-15): después del `h1`, ningún título salta un nivel (`h1` → `h3` sin `h2` en el medio)."""
        lineas = self._inventario_de(SALTO_DE_TITULO)
        self.assertEqual(lineas, [], "Títulos que saltan niveles:\n" + "\n".join(lineas))


class ControlesDeAccesibilidadTests(SimpleTestCase):
    """UI-03 paso 1: cada control de accesibilidad de la red detecta su caso y deja pasar el correcto (con HTML de ejemplo)."""

    def test_ui03_th_vacio_se_detecta_y_el_de_solo_lectores_pasa(self):
        """UX-09: `<th></th>` es un problema; `<th><span class="sr">Acciones</span></th>` y `<th aria-label="…">` no."""
        self.assertEqual(
            problemas_de_accesibilidad("<table><tr><th>Código</th><th></th></tr></table>")[TH_SIN_TEXTO], ["Código | ∅"]
        )
        bien = '<table><tr><th>Código</th><th><span class="sr">Acciones</span></th><th aria-label="Ficha"></th></tr></table>'
        self.assertEqual(problemas_de_accesibilidad(bien)[TH_SIN_TEXTO], [])

    def test_ui03_aria_pressed_en_enlace_se_detecta_y_en_boton_pasa(self):
        """UX-10: `aria-pressed` en un `<a>` es un problema; en un `<button>`, no."""
        html = '<a class="chip" href="/x/?a=1" aria-pressed="true">Todas</a><button aria-pressed="true">Todas</button>'
        self.assertEqual(problemas_de_accesibilidad(html)[ENLACE_CON_ARIA_PRESSED], ["«Todas» → /x/?a=N"])
        self.assertEqual(problemas_de_accesibilidad('<a href="/x/" aria-current="page">Todas</a>')[ENLACE_CON_ARIA_PRESSED], [])

    def test_ui03_campo_sin_etiqueta_se_detecta_y_las_cuatro_formas_pasan(self):
        """UX-11: un campo sin etiqueta es un problema; `<label for>` (antes o después), `<label>` que envuelve, `aria-label` y
        `aria-labelledby` lo resuelven. Los `hidden`, los botones y los campos con `aria-hidden="true"` no necesitan etiqueta."""
        mal = '<input name="dias_3" id="id_dias_3"><select name="causa"></select><textarea name="d"></textarea>'
        self.assertEqual(
            problemas_de_accesibilidad(mal)[CAMPO_SIN_ETIQUETA],
            ["input[text] name=dias_N id=id_dias_N", "select name=causa id=—", "textarea name=d id=—"],
        )
        bien = (
            '<label for="a">A</label><input id="a" name="a"><input id="b" name="b"><label class="sr" for="b">B</label>'
            '<label>C <input name="c" type="checkbox"></label><select aria-label="D" name="d"></select>'
            '<span id="e-t">E</span><textarea aria-labelledby="e-t" name="e"></textarea>'
            '<input type="hidden" name="f"><input type="submit" value="Guardar"><input type="button" value="x">'
            '<input class="sr" name="username" autocomplete="username" tabindex="-1" aria-hidden="true">'
        )
        self.assertEqual(problemas_de_accesibilidad(bien)[CAMPO_SIN_ETIQUETA], [])

    def test_ui03_salto_de_titulo_se_detecta_y_la_escalera_pasa(self):
        """UX-15: después del `h1`, un `h3` sin `h2` es un salto; volver a subir (h3 → h2) no lo es, y lo de antes del `h1` no cuenta."""
        self.assertEqual(
            problemas_de_accesibilidad("<h3>Marco</h3><h1>Ficha</h1><h3>Datos</h3>")[SALTO_DE_TITULO], ["h1 → h3 «Datos»"]
        )
        self.assertEqual(
            problemas_de_accesibilidad("<h3>Marco</h3><h1>Ficha</h1><h2>A</h2><h3>B</h3><h2>C</h2><h3>D</h3>")[SALTO_DE_TITULO], []
        )


def _apps_propias():
    """Las apps del proyecto (las que están dentro de BASE_DIR)."""
    base = Path(settings.BASE_DIR).resolve()
    propias = []
    for config in apps.get_app_configs():
        ruta = Path(config.path).resolve()
        if base in ruta.parents and ".venv" not in ruta.parts:
            propias.append(ruta)
    return propias


def _texto_de_plantilla(texto):
    """Lo que una plantilla puede mostrar: sin comentarios de Django ni HTML, sin ``<script>`` ni ``<style>`` y sin etiquetas ``{% %}``."""
    texto = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", texto, flags=re.S)
    texto = re.sub(r"\{#.*?#\}", "", texto)
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    texto = re.sub(r"<(script|style)\b.*?</\1>", "", texto, flags=re.S | re.I)
    return re.sub(r"\{%.*?%\}", "", texto, flags=re.S)


def _llamadas_a_messages(codigo):
    """``(línea, texto)`` de cada llamada ``messages.success|info|warning|error(…)`` de un archivo de Python, hasta cerrar su paréntesis,
    sin los comentarios ``#``."""
    llamadas = []
    for coincidencia in re.finditer(r"messages\.(success|info|warning|error)\(", codigo):
        fin, profundidad = coincidencia.end(), 1
        while profundidad and fin < len(codigo):
            profundidad += {"(": 1, ")": -1}.get(codigo[fin], 0)
            fin += 1
        fragmento = re.sub(r"(?m)#[^\n\"']*$", "", codigo[coincidencia.start() : fin])
        llamadas.append((codigo.count("\n", 0, coincidencia.start()) + 1, fragmento))
    return llamadas


# Excepciones cuyo texto no llega a la pantalla: se lanzan por un error de programación (quien llama pasó un argumento que no
# corresponde), no por algo que hizo la persona, y ninguna vista muestra su mensaje (las dos vistas que las atrapan, en
# `compras/views_recepciones.py`, responden 404). Sus textos pueden citar reglas y decisiones.
EXCEPCIONES_QUE_NO_SE_MUESTRAN = (
    "ValueError",  # argumento con un valor imposible («`asignar` cubre un detalle de venta o un período…»)
    "RuntimeError",  # uso fuera de lugar («`asignar` corre dentro de la transacción del caso de uso base…»)
    "TypeError",  # tipo equivocado («Una cantidad no puede ser float ni bool…»)
)


def _cadenas_visibles(codigo):
    """``(línea, texto)`` de cada cadena de un archivo de Python que puede llegar a la pantalla: sin docstrings ni las cadenas que van
    dentro de un ``raise`` de `EXCEPCIONES_QUE_NO_SE_MUESTRAN`. Los comentarios no son cadenas: el árbol de sintaxis no los tiene."""
    arbol = ast.parse(codigo)
    excluidas = set()
    for nodo in ast.walk(arbol):
        cuerpo = getattr(nodo, "body", None)
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and cuerpo:
            primero = cuerpo[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                excluidas.add(id(primero.value))  # docstring
        if (
            isinstance(nodo, ast.Raise)
            and isinstance(nodo.exc, ast.Call)
            and isinstance(nodo.exc.func, ast.Name)
            and nodo.exc.func.id in EXCEPCIONES_QUE_NO_SE_MUESTRAN
        ):
            excluidas |= {id(hijo) for hijo in ast.walk(nodo.exc)}
    return [
        (nodo.lineno, nodo.value)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in excluidas
    ]


def _servicios_y_vistas():
    """Los archivos de servicios (``servicios.py`` y el paquete ``servicios/``) y de vistas (``views*.py``) de cada app."""
    archivos = []
    for app in _apps_propias():
        archivos += [*app.glob("servicios.py"), *app.glob("servicios/**/*.py"), *app.glob("views*.py"), *app.glob("views/**/*.py")]
    return [a for a in archivos if "tests" not in a.parts]


class EscaneoDeFuentesTests(SimpleTestCase):
    """UI-02 paso 1 (D-109 punto 7): los textos que la red no ve (los que salen después de un POST o con datos que la demo no tiene) se
    buscan en las fuentes, con los mismos patrones."""

    def test_ui02_las_plantillas_no_tienen_codigos_internos(self):
        """Plantillas `.html` y `.txt` de todas las apps (pantallas y correos), sin comentarios ni etiquetas `{% %}`."""
        plantillas = [p for app in _apps_propias() for p in (*app.glob("templates/**/*.html"), *app.glob("templates/**/*.txt"))]
        self.assertGreater(len(plantillas), 100)  # que la prueba no pase sin revisar nada
        hallazgos = []
        base = Path(settings.BASE_DIR).resolve()
        for plantilla in plantillas:
            for numero, linea in enumerate(_texto_de_plantilla(plantilla.read_text(encoding="utf-8")).splitlines(), start=1):
                for codigo in codigos_internos(linea):
                    hallazgos.append(f"{plantilla.resolve().relative_to(base).as_posix()} · {codigo} · {linea.strip()[:120]}")
        self.assertEqual(hallazgos, [], "Códigos internos en plantillas:\n" + "\n".join(hallazgos))

    def test_ui03_ninguna_plantilla_tiene_un_enlace_con_aria_pressed(self):
        """D-109 punto 8 (UX-10): ningún `<a>` de ninguna plantilla lleva `aria-pressed` (solo vale en un botón). La red no llega con GET a
        todas las pantallas (Recepción y Corrección de Compras, por ejemplo): por eso se buscan también en las fuentes. Lo pidió el
        estudiante al revisar el paso 1 de UI-03 (27/11/2026)."""
        plantillas = [p for app in _apps_propias() for p in app.glob("templates/**/*.html")]
        self.assertGreater(len(plantillas), 100)  # que la prueba no pase sin revisar nada
        base = Path(settings.BASE_DIR).resolve()
        hallazgos = []
        for plantilla in plantillas:
            texto = plantilla.read_text(encoding="utf-8")
            for etiqueta in re.finditer(r"<a\b[^>]*>", texto):
                if re.search(r"\baria-pressed\b", etiqueta.group(0)):
                    linea = texto.count("\n", 0, etiqueta.start()) + 1
                    hallazgos.append(f"{plantilla.resolve().relative_to(base).as_posix()}:{linea} · {etiqueta.group(0)[:120]}")
        self.assertEqual(hallazgos, [], "Enlaces con aria-pressed en plantillas:\n" + "\n".join(hallazgos))

    def test_ui02_los_mensajes_de_las_vistas_no_tienen_codigos_internos(self):
        """Los avisos `messages.success/info/warning/error(…)` de los archivos de Python de las apps (sin pruebas ni migraciones)."""
        base = Path(settings.BASE_DIR).resolve()
        archivos = [
            p for app in _apps_propias() for p in app.rglob("*.py") if "tests" not in p.parts and "migrations" not in p.parts
        ]
        hallazgos, llamadas = [], 0
        for archivo in archivos:
            for linea, texto in _llamadas_a_messages(archivo.read_text(encoding="utf-8")):
                llamadas += 1
                for codigo in codigos_internos(texto):
                    hallazgos.append(f"{archivo.resolve().relative_to(base).as_posix()}:{linea} · {codigo} · {' '.join(texto.split())[:160]}")
        self.assertGreater(llamadas, 20)  # que la prueba no pase sin revisar nada
        self.assertEqual(hallazgos, [], "Códigos internos en avisos:\n" + "\n".join(hallazgos))

    def test_ui02_los_textos_de_servicios_y_vistas_no_tienen_codigos_internos(self):
        """Las cadenas de los servicios y de las vistas (sin docstrings ni los errores de programación de
        `EXCEPCIONES_QUE_NO_SE_MUESTRAN`): los errores de campo, las advertencias y las asignaciones que arman los servicios llegan a la
        pantalla sin pasar por una plantilla ni por `messages`. Lo pidió el estudiante al revisar el paso 1 (27/11/2026)."""
        base = Path(settings.BASE_DIR).resolve()
        archivos = _servicios_y_vistas()
        self.assertGreater(len(archivos), 100)  # que la prueba no pase sin revisar nada
        hallazgos = []
        for archivo in archivos:
            for linea, texto in _cadenas_visibles(archivo.read_text(encoding="utf-8")):
                for codigo in codigos_internos(texto):
                    hallazgos.append(f"{archivo.resolve().relative_to(base).as_posix()}:{linea} · {codigo} · {texto[:160]}")
        self.assertEqual(hallazgos, [], "Códigos internos en textos de servicios y vistas:\n" + "\n".join(hallazgos))
