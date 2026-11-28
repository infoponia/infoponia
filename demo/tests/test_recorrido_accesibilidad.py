# Recorrido de la accesibilidad de UI-03 (D-109 punto 8; ``docs/patrones/verificacion_a_mano.md``): con los datos de la demo (como
# `test_recorrido_demo.py`), entra con cada rol a las pantallas que la tarea tocó y comprueba, como lo oiría un lector de pantalla, el
# encabezado «Acciones» (UX-09), la vista activa con `aria-current` (UX-10), las etiquetas de los campos (UX-11) y Nuevo invernadero sin
# ubicación con los tres campos marcados (UX-12). No reemplaza la «Verificación a mano»: el cliente de Django no ve el CSS, el lector de
# pantalla ni el JavaScript (el desplegable propio). La contraseña se inventa en cada corrida.

import re
import secrets

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from demo import carga
from demo.tests.test_red_de_pantallas import (
    CONTROLES_DE_ACCESIBILIDAD,
    problemas_de_accesibilidad,
)
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Cultivo, Localidad
from produccion.models import Cosecha

BASE = "ejemplo"
ERROR_DE_LOCALIDAD = "Elegí la localidad de la lista."


def etiqueta_de_apertura(html, etiqueta, nombre):
    """La etiqueta de apertura (``<select …>``, ``<input …>``) del campo ``name="nombre"``, o ``None``."""
    coincidencia = re.search(rf'<{etiqueta}\b[^>]*\bname="{re.escape(nombre)}"[^>]*>', html)
    return coincidencia.group(0) if coincidencia else None


def id_de(etiqueta):
    """El ``id`` de una etiqueta de apertura."""
    return re.search(r'\bid="([^"]+)"', etiqueta).group(1)


class RecorridoDeAccesibilidadTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """UI-03 paso 6: el recorrido por rol de las pantallas que cambió la tarea, con los datos de la demo."""

    @classmethod
    def setUpTestData(cls):
        cls.contrasena = secrets.token_urlsafe(12)
        carga.cargar(carga.Contexto(hoy=timezone.localdate(), base=BASE, contrasena=cls.contrasena))

    def entrar(self, clave):
        """Inicia sesión por la pantalla con la cuenta ``clave`` de la demo."""
        self.client.logout()
        respuesta = self.client.post(
            reverse("core:iniciar_sesion"), {"username": f"{BASE}+{clave}@gmail.com", "password": self.contrasena}
        )
        self.assertEqual(respuesta.status_code, 302, clave)

    def abrir(self, url):
        """GET de ``url``: 200, y la página pasa los cuatro controles de accesibilidad de la red. Devuelve el HTML."""
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200, url)
        html = respuesta.content.decode()
        self.assert_sin_problemas(html, url)
        return html

    def assert_sin_problemas(self, html, donde):
        """Ningún problema de los cuatro controles de UI-03 en ``html``."""
        problemas = problemas_de_accesibilidad(html)
        for control in CONTROLES_DE_ACCESIBILIDAD:
            self.assertEqual(problemas[control], [], f"{donde} · {control}")

    def chips(self, html, prefijo):
        """``{texto: aria-current}`` de los enlaces ``.chip`` cuyo ``href`` empieza con ``prefijo``; también afirma que ninguno lleva
        ``aria-pressed``."""
        resultado = {}
        for apertura, texto in re.findall(r'(<a class="chip"[^>]*>)(.*?)</a>', html, flags=re.S):
            href = re.search(r'href="([^"]*)"', apertura).group(1)
            if not href.startswith(prefijo):
                continue
            self.assertNotIn("aria-pressed", apertura)
            actual = re.search(r'aria-current="([^"]*)"', apertura)
            # El texto sin el contador (<b>3</b>): «Por aprobar», «Todas».
            visible = " ".join(re.sub(r"<b>.*?</b>|<[^>]+>", "", texto).split())
            resultado[visible] = actual.group(1) if actual else None
        return resultado

    def test_ui03_recorrido_de_las_pantallas_tocadas_por_rol(self):
        """D-109 punto 8 (UX-09, UX-10, UX-11 y UX-12), de punta a punta, como lo recorre una persona con un lector de pantalla."""
        # Gerente · Cuentas (UX-09): la columna de las acciones tiene «Acciones», solo para lectores.
        self.entrar("gerente1")
        html = self.abrir(reverse("core:usuarios"))
        self.assertIn('<th><span class="sr">Acciones</span></th>', html)

        # Gerente · Compras · Órdenes (UX-10): solo el atajo activo lleva aria-current="page"; los demás, nada.
        html = self.abrir(reverse("compras:ordenes") + "?atajo=por_aprobar")
        atajos = self.chips(html, reverse("compras:ordenes"))
        self.assertEqual(
            atajos,
            {"Todas": None, "Por aprobar": "page", "Por recibir": None, "Con reclamo sin emitir": None, "Con pago pendiente": None},
        )
        # Sin atajo, el activo es «Todas».
        html = self.abrir(reverse("compras:ordenes"))
        self.assertEqual(self.chips(html, reverse("compras:ordenes"))["Todas"], "page")

        # Gerente · Compras · Reclamos (UX-10): «Sin emitir» activo.
        html = self.abrir(reverse("compras:reclamos") + "?estado=sin_emitir")
        reclamos = self.chips(html, reverse("compras:reclamos"))
        self.assertEqual(reclamos, {"Todos": None, "Sin emitir": "page", "Emitidos abiertos": None, "Cerrados": None})

        # Vendedor · Cobranza (UX-10): son pestañas (role="tab"): el activo lleva aria-selected="true", sin aria-pressed.
        self.entrar("vendedor1")
        html = self.abrir(reverse("comercial:cobranza") + "?vista=cobros")
        self.assertRegex(html, r'role="tab" href="[^"]*\?vista=cobros" aria-selected="true">Cobros registrados</a>')
        self.assertRegex(html, r'role="tab" href="[^"]*" aria-selected="false">Por cobrar</a>')

        # Contador · Libro diario (UX-09 y UX-10): «Cronológica» activa y la columna del medio con su nombre para lectores.
        self.entrar("contador1")
        html = self.abrir(reverse("contabilidad:libro"))
        vistas = self.chips(html, reverse("contabilidad:libro") + "?vista=")  # solo los atajos del libro (el menú del celular ya no son fichas `.chip`, UI-05)
        self.assertEqual(vistas, {"Cronológica": "page", "Por cuenta": None})
        self.assertIn('<th>Cuenta</th><th><span class="sr">Descripción</span></th>', html)

        # Agrónomo · Nueva variedad (UX-11): cada duración de etapa tiene su <label for>, que el lector lee.
        self.entrar("agronomo1")
        cultivo = Cultivo.objects.order_by("pk").first()
        html = self.abrir(reverse("variedades:variedad_nueva", args=[cultivo.pk]))
        duraciones = re.findall(r'<input\b[^>]*\bname="(duracion_(?!post)[a-z_]+)"[^>]*>', html)
        self.assertGreaterEqual(len(duraciones), 2)  # Germinación y Maduración, por lo menos
        for nombre in duraciones:
            identificador = id_de(etiqueta_de_apertura(html, "input", nombre))
            self.assertRegex(html, rf'<label class="sr" for="{identificador}">Duración estimada de [^<]+ en días</label>')

        # Capataz · Mi perfil (UX-11): los dos campos de archivo tienen su aria-label (el botón de la cámara no se ve en computadora).
        self.entrar("capataz1")
        html = self.abrir(reverse("core:mi_perfil"))
        self.assertIn('aria-label="Tomar foto de perfil con la cámara"', etiqueta_de_apertura(html, "input", "foto_camara"))
        self.assertIn('aria-label="Elegir foto de perfil"', etiqueta_de_apertura(html, "input", "foto"))

        # Capataz · Concretar cosecha (UX-11): plantas perdidas, causa y descripción de cada lote tienen su <label for>. Ya la tenían
        # en main (diferencia con la revisión, anotada en el «Cierre»); el recorrido lo deja asegurado.
        cosecha = (
            Cosecha.objects.filter(capataz__email=f"{BASE}+capataz1@gmail.com", estado_orden="a_realizar").order_by("pk").first()
        )
        self.assertIsNotNone(cosecha, "La demo no tiene una cosecha «a realizar» del capataz1.")
        html = self.abrir(reverse("comercial:cosecha_concretar", args=[cosecha.pk]))
        etiquetas_for = set(re.findall(r'<label\b[^>]*\bfor="([^"]+)"', html))
        for prefijo, etiqueta in (("perd_", "input"), ("causa_", "select"), ("desc_", "input")):
            nombres = re.findall(rf'<{etiqueta}\b[^>]*\bname="({prefijo}[\d_]+)"', html)
            self.assertTrue(nombres, prefijo)
            for nombre in nombres:
                self.assertIn(id_de(etiqueta_de_apertura(html, etiqueta, nombre)), etiquetas_for, nombre)

        # Gerente · Nuevo invernadero (UX-12). Al abrirlo, nada marcado.
        self.entrar("gerente1")
        url = reverse("maestros:invernadero_nuevo")
        html = self.abrir(url)
        self.assertNotIn('aria-invalid="true"', html)
        self.assertNotIn("fld-invalido", html)

        # Sin ubicación: el error va en Localidad (el texto de siempre, una sola vez) y se marcan los tres campos.
        respuesta = self.client.post(url, {"nombre": "Invernadero de prueba"})
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        self.assert_sin_problemas(html, "Nuevo invernadero sin ubicación")
        self.assertEqual(html.count(ERROR_DE_LOCALIDAD), 1)
        for campo in ("provincia", "departamento", "localidad"):
            self.assertIn('aria-invalid="true"', etiqueta_de_apertura(html, "select", campo), campo)
        self.assertEqual(html.count('class="fld fld-invalido"'), 2)  # Provincia y Departamento; Localidad se marca por su error

        # Con la provincia elegida: Provincia deja de estar marcada; Departamento y Localidad siguen.
        localidad = Localidad.objects.select_related("departamento").order_by("pk").first()
        datos = {"nombre": "Invernadero de prueba", "provincia": localidad.departamento.provincia_id}
        html = self.client.post(url, datos).content.decode()
        self.assertNotIn("aria-invalid", etiqueta_de_apertura(html, "select", "provincia"))
        self.assertIn('aria-invalid="true"', etiqueta_de_apertura(html, "select", "departamento"))
        self.assertIn('aria-invalid="true"', etiqueta_de_apertura(html, "select", "localidad"))
        self.assertEqual(html.count('class="fld fld-invalido"'), 1)

        # Con la ubicación completa (y sin nombre, para que no se guarde): ninguno de los tres se marca.
        datos = {"nombre": "", "provincia": localidad.departamento.provincia_id, "departamento": localidad.departamento_id,
                 "localidad": localidad.pk}
        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        self.assertNotIn(ERROR_DE_LOCALIDAD, html)
        for campo in ("provincia", "departamento", "localidad"):
            self.assertNotIn("aria-invalid", etiqueta_de_apertura(html, "select", campo), campo)
        self.assertNotIn("fld-invalido", html)
