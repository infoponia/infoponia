# Recorrido del menú y las tablas del celular de UI-05 (D-109 punto 4; ``docs/patrones/verificacion_a_mano.md``): con los datos de la demo
# (como `test_recorrido_accesibilidad.py`), entra con cada rol y comprueba, en el HTML, lo que el cliente de Django puede ver: que el
# botón «Menú» trae las mismas entradas que el menú lateral y que cada una abre (UX-07), y que las listas elegidas se marcan como
# `.tabla-apilable` con su `data-rotulo` en cada celda (UX-02), mientras el libro de Contabilidad sigue como tabla con desplazamiento.
# No reemplaza la «Verificación a mano»: el cliente no ve el CSS, el ancho de la ventana ni el JavaScript (Esc y clic afuera). La
# contraseña se inventa en cada corrida.

import re
import secrets

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from demo import carga
from demo.tests.test_red_de_pantallas import CELDA_SIN_ROTULO, TABLAS_APILABLES, problemas_de_accesibilidad
from inventario.tests.fabricas import ConDatosDeInventario

BASE = "ejemplo"
PANEL = '<nav class="menu-celular-panel"'


def entradas_del_menu(html, apertura, cierre):
    """``[(texto, href, aria-current)]`` de los enlaces entre ``apertura`` y ``cierre`` en ``html``."""
    inicio = html.index(apertura)
    tramo = html[inicio : html.index(cierre, inicio)]
    entradas = []
    for atributos, interior in re.findall(r"<a ([^>]*)>(.*?)</a>", tramo, flags=re.S):
        texto = " ".join(re.sub(r"<[^>]+>", " ", interior).split())
        href = re.search(r'href="([^"]*)"', atributos).group(1)
        actual = re.search(r'aria-current="([^"]*)"', atributos)
        entradas.append((texto, href, actual.group(1) if actual else None))
    return entradas


class RecorridoDelCelularTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """UI-05 paso 3: el recorrido por rol del menú y las tablas del celular, con los datos de la demo."""

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

    def abrir(self, url, seguir=False):
        """GET de ``url`` con 200 (con ``seguir``, después de las redirecciones: «Monitoreo de IoT» lleva a su primera pestaña). Devuelve el HTML."""
        respuesta = self.client.get(url, follow=seguir)
        self.assertEqual(respuesta.status_code, 200, url)
        return respuesta.content.decode()

    def recorrer_el_menu(self, clave):
        """Con la cuenta ``clave``: «Menú» trae las mismas entradas que el menú lateral, y cada una abre (200) y se ve activa en su
        pantalla, tanto en «Menú» como en el lateral. Devuelve los textos de las entradas."""
        self.entrar(clave)
        inicio = self.abrir(reverse("core:inicio"))
        celular = entradas_del_menu(inicio, PANEL, "</nav>")
        lateral = entradas_del_menu(inicio, '<aside class="side">', "</aside>")
        self.assertEqual(celular, lateral, clave)
        self.assertGreaterEqual(len(celular), 2, clave)
        for texto, href, _ in celular:
            pantalla = self.abrir(href, seguir=True)
            # Una entrada también está activa en sus pantallas internas, por prefijo de la URL (`core.context_processors.marco`): en
            # «Bitácora» están activas «Producción» y «Bitácora». Lo que importa acá es que «Menú» y el lateral marquen lo mismo.
            marcadas = {}
            for tramo, cierre in ((PANEL, "</nav>"), ('<aside class="side">', "</aside>")):
                marcadas[tramo] = [t for t, _, actual in entradas_del_menu(pantalla, tramo, cierre) if actual == "page"]
                self.assertIn(texto, marcadas[tramo], f"{clave} · {href}")
            self.assertEqual(marcadas[PANEL], marcadas['<aside class="side">'], f"{clave} · {href}")
        return [texto for texto, _, _ in celular]

    def tablas(self, html):
        """``(hay_tabla_apilable, celdas_sin_rotulo)`` de una página, con el mismo lector que la red de pantallas."""
        problemas = problemas_de_accesibilidad(html)
        return bool(problemas[TABLAS_APILABLES]), problemas[CELDA_SIN_ROTULO]

    def test_ui05_recorrido_del_menu_y_las_tablas_del_celular_por_rol(self):
        """D-109 punto 4 (UX-07 y UX-02), de punta a punta: el menú del celular y las listas como tarjetas, rol por rol."""
        # Gerente y Agrónomo (UX-07): llegan a cualquier módulo desde «Menú», que es la misma lista del lateral.
        gerente = self.recorrer_el_menu("gerente1")
        self.assertIn("Contabilidad", gerente)
        self.assertGreaterEqual(len(gerente), 10)
        agronomo = self.recorrer_el_menu("agronomo1")
        self.assertIn("Producción", agronomo)

        # Gerente · Cuentas y Compras (UX-02): las tablas de lista son tarjetas en el celular, con el rótulo en cada celda. La demo no
        # trae pedidos ni órdenes: esas dos listas muestran su estado vacío y no tienen tabla.
        self.entrar("gerente1")
        for url in (reverse("core:usuarios"), reverse("compras:proveedores")):
            html = self.abrir(url)
            apilable, sin_rotulo = self.tablas(html)
            self.assertTrue(apilable, url)
            self.assertEqual(sin_rotulo, [], url)
            self.assertIn('<td data-rotulo="', html, url)
        for url in (reverse("compras:ordenes"), reverse("compras:pedidos")):
            self.assertEqual(self.tablas(self.abrir(url))[1], [], url)
        # El rótulo de cada celda es el de su columna: en Cuentas, «Nombre», «Rol» y «Estado»; la de acciones no lleva.
        cuentas = self.abrir(reverse("core:usuarios"))
        self.assertRegex(
            cuentas, r'(?s)<td data-rotulo="Nombre">.*?<td data-rotulo="Rol">.*?<td data-rotulo="Estado">.*?<td style="text-align:right">'
        )

        # Vendedor (UX-02): Clientes, Contratos, Entregas, Cobranza y Solicitudes se leen como tarjetas (las vacías, con su fila de aviso).
        self.recorrer_el_menu("vendedor1")
        for url in (
            reverse("comercial:clientes"),
            reverse("comercial:contratos"),
            reverse("comercial:entregas"),
            reverse("comercial:cobranza") + "?vista=cobros",
            reverse("comercial:solicitudes"),
        ):
            html = self.abrir(url)
            apilable, sin_rotulo = self.tablas(html)
            self.assertTrue(apilable, url)
            self.assertEqual(sin_rotulo, [], url)
            self.assertIn('class="data-table tabla-apilable"', html, url)
        clientes = self.abrir(reverse("comercial:clientes"))
        for rotulo in ("Cliente", "CUIT", "Contacto", "Direcciones", "Contratos vigentes", "Estado"):
            self.assertIn(f'data-rotulo="{rotulo}"', clientes)

        # Contador (UX-02): el libro (filas de asiento y de movimiento) queda como tabla con desplazamiento, sin tarjetas; Ejercicios sí.
        self.recorrer_el_menu("contador1")
        libro = self.abrir(reverse("contabilidad:libro"))
        self.assertFalse(self.tablas(libro)[0])
        self.assertNotIn("tabla-apilable", libro)
        self.assertIn('<div class="tablewrap">', libro)
        apilable, sin_rotulo = self.tablas(self.abrir(reverse("contabilidad:ejercicios")))
        self.assertTrue(apilable)
        self.assertEqual(sin_rotulo, [])

    def test_ui05_el_modo_campo_no_cambia(self):
        """D-25 y D-109 punto 4: Capataz, Técnico y Transportista siguen sin menú lateral y sin «Menú», y siguen en su marco angosto."""
        for clave in ("capataz1", "tecnico1", "transportista1"):
            with self.subTest(clave=clave):
                self.entrar(clave)
                inicio = self.client.get(reverse("core:inicio"), follow=True)
                self.assertEqual(inicio.status_code, 200)
                html = inicio.content.decode()
                self.assertNotIn("menu-celular", html)
                self.assertNotIn('<aside class="side">', html)
                self.assertIn('class="shell field"', html)
