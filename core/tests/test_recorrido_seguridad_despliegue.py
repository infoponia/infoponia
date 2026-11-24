# Recorrido de punta a punta de la seguridad del despliegue (USR-09a, SEG-16) con el cliente de Django (D-96,
# docs/patrones/verificacion_a_mano.md): http redirige a https, por https se inicia sesión, la cookie de sesión es Secure
# y HttpOnly y la respuesta trae HSTS de un día. Usa override_settings con los valores que calcula ``ajustes_https``, para
# dar lo mismo en el CI y con el .env de cada máquina. No ve lo que solo un navegador ve (CSRF con Origin, las
# herramientas F12): eso va como paso de «navegador real» en la «Verificación a mano» de la tarea.

from django.test import TestCase, override_settings
from django.urls import reverse

from config.seguridad import ajustes_https
from core.tests.fabricas import CLAVE, crear_gerente


class RecorridoDeSeguridadDespliegueTests(TestCase):
    """Producción (DEBUG apagado) y desarrollo (DEBUG encendido) vistos por el cliente de Django."""

    @override_settings(**ajustes_https(False, False))
    def test_recorrido_de_produccion_de_punta_a_punta(self):
        crear_gerente()
        ingreso = reverse("core:iniciar_sesion")
        inicio = reverse("core:inicio")

        # SEG-16: por http, una pantalla pública y una privada reciben una redirección permanente a https.
        for ruta in (ingreso, inicio):
            with self.subTest("http redirige", ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 301)
                self.assertEqual(respuesta["Location"], f"https://testserver{ruta}")

        # SEG-16: por https la pantalla pública responde 200 y el navegador recibe HSTS de un día, sin subdominios ni preload.
        publica = self.client.get(ingreso, secure=True)
        self.assertEqual(publica.status_code, 200)
        self.assertEqual(publica["Strict-Transport-Security"], "max-age=86400")

        # SEG-16: se inicia sesión por https y la cookie de sesión es segura y no accesible desde scripts.
        entrada = self.client.post(ingreso, {"username": "gerente@infoponia.com", "password": CLAVE}, secure=True)
        self.assertEqual(entrada.status_code, 302)
        sesion = entrada.cookies["sessionid"]
        self.assertTrue(sesion["secure"])
        self.assertTrue(sesion["httponly"])
        if "csrftoken" in entrada.cookies:
            self.assertTrue(entrada.cookies["csrftoken"]["secure"])

        # Con la sesión abierta, la pantalla privada responde 200 por https y también trae HSTS.
        privada = self.client.get(inicio, secure=True)
        self.assertEqual(privada.status_code, 200)
        self.assertEqual(privada["Strict-Transport-Security"], "max-age=86400")

    @override_settings(**ajustes_https(True, False))
    def test_recorrido_de_desarrollo_sigue_andando_por_http(self):
        # USR-09a: con DEBUG encendido el desarrollo corre por http: sin redirección, sin HSTS y con cookies sin Secure.
        crear_gerente()
        ingreso = reverse("core:iniciar_sesion")

        publica = self.client.get(ingreso)
        self.assertEqual(publica.status_code, 200)
        self.assertNotIn("Strict-Transport-Security", publica)
        entrada = self.client.post(ingreso, {"username": "gerente@infoponia.com", "password": CLAVE})
        self.assertEqual(entrada.status_code, 302)
        self.assertFalse(entrada.cookies["sessionid"]["secure"])
        self.assertTrue(entrada.cookies["sessionid"]["httponly"])
        self.assertEqual(self.client.get(reverse("core:inicio")).status_code, 200)
