# Recorrido de la demo (DAT-01, paso 4; ``docs/patrones/verificacion_a_mano.md``): carga con el candado sustituido y entra con el cliente de
# Django, por rol, con la contraseña de la variable (sin pasar por ningún cambio de contraseña temporal). No reemplaza la «Verificación a
# mano» ni el navegador real: el cliente de Django no ve el CSRF ni el JavaScript. La contraseña se inventa en cada corrida.

import secrets

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from demo import carga
from inventario.tests.fabricas import ConDatosDeInventario

BASE = "ejemplo"


class RecorridoDeDemoTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-01 paso 4: las cuentas de la demo entran con la contraseña de la variable y ven lo que cargó el comando."""

    @classmethod
    def setUpTestData(cls):
        cls.contrasena = secrets.token_urlsafe(12)
        carga.cargar(carga.Contexto(hoy=timezone.localdate(), base=BASE, contrasena=cls.contrasena))

    def _entrar(self, clave):
        """Inicia sesión por la pantalla, con el correo y la contraseña de la variable; devuelve la respuesta del POST."""
        self.client.logout()
        return self.client.post(
            reverse("core:iniciar_sesion"), {"username": f"{BASE}+{clave}@gmail.com", "password": self.contrasena}
        )

    def test_dat_01_recorrido_cada_rol_entra_sin_cambiar_la_contrasena_y_ve_lo_suyo(self):
        """Por rol: entra (redirige, no vuelve a la pantalla de ingreso ni a un cambio de contraseña) y abre su pantalla principal."""
        pantallas = {
            "gerente1": ("maestros:invernaderos", ["Norte", "Sur"]),
            "agronomo1": ("inventario:existencias", ["Solución nutritiva A"]),
            "vendedor1": ("comercial:clientes", ["Súper Del Parque", "Marta Villalba"]),
            "contador1": ("contabilidad:libro", []),
        }
        for clave, (nombre_url, textos) in pantallas.items():
            with self.subTest(cuenta=clave):
                respuesta = self._entrar(clave)
                self.assertEqual(respuesta.status_code, 302, clave)
                self.assertNotIn("contrasena", respuesta.headers["Location"].lower(), clave)
                pantalla = self.client.get(reverse(nombre_url))
                self.assertEqual(pantalla.status_code, 200, clave)
                for texto in textos:
                    self.assertContains(pantalla, texto)

    def test_dat_01_recorrido_una_contrasena_equivocada_no_entra(self):
        """La contraseña de la variable es la única que sirve."""
        self.client.logout()
        respuesta = self.client.post(
            reverse("core:iniciar_sesion"), {"username": f"{BASE}+gerente1@gmail.com", "password": secrets.token_urlsafe(12)}
        )
        self.assertEqual(respuesta.status_code, 200)
