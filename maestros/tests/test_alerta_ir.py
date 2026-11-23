# Pruebas de la ruta que abre una alerta y redirige a la pantalla de su origen (MAE-02d, paso 4; D-62, primera enmienda y tercera,
# puntos 2 y 3; docs/api/alertas.md, sección 8): ``alertas:ir`` (``/alertas/<id>/ir/``). Los registrantes son falsos.

from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from core.tests.fabricas import CLAVE, crear_administrador, crear_capataz, crear_gerente
from maestros import extensiones
from maestros.extensiones import Enlace
from maestros.models import Alerta
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_alerta, crear_invernadero


class AlertaIrVistaTests(ConGeoref, TestCase):
    """``alerta_ir``: abre la alerta (regla 7 de 8.18) y redirige al ``url`` de su enlace, sin salir nunca del sitio."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.sur = crear_invernadero("Sur", agronomo=self.agronomo)
        self.alerta = crear_alerta(self.sur, "com_falso", para_gerente=True)
        self.ir = reverse("alertas:ir", args=[self.alerta.pk])
        self.detalle = reverse("alertas:detalle", args=[self.alerta.pk])

    def cliente_de(self, cuenta):
        cliente = Client()
        self.assertTrue(cliente.login(email=cuenta.email, password=CLAVE))
        return cliente

    def con_registrante(self, url):
        """Un registrante falso que lleva ``com_falso`` a ``url``."""
        patch = mock.patch.object(extensiones, "_ENLACES", [])
        patch.start()
        self.addCleanup(patch.stop)
        extensiones.registrar_enlace_de_alerta(("com_falso",), lambda usuario, alertas: {a.pk: Enlace(url, "Texto") for a in alertas})

    def lectura(self):
        self.alerta.refresh_from_db()
        return self.alerta.estado_lectura_alerta

    def test_la_ruta_se_llama_alertas_ir_y_cuelga_de_alertas(self):
        """D-62, tercera enmienda, punto 2: ``alertas:ir`` es ``/alertas/<id>/ir/``."""
        self.assertEqual(self.ir, f"/alertas/{self.alerta.pk}/ir/")

    def test_flujo_principal_con_registrante_redirige_a_su_url_y_deja_la_alerta_leida(self):
        """D-62, primera enmienda: abre la alerta (queda «leída») y redirige (302) al ``url`` del registrante."""
        self.con_registrante("/alertas/")

        respuesta = self.cliente_de(self.gerente).get(self.ir)

        self.assertRedirects(respuesta, "/alertas/", fetch_redirect_response=False)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.lectura(), Alerta.Lectura.LEIDA)

    def test_sin_registrante_redirige_al_detalle_y_la_deja_leida(self):
        """D-62, segunda enmienda: el enlace por omisión es el detalle de la alerta."""
        with mock.patch.object(extensiones, "_ENLACES", []):
            respuesta = self.cliente_de(self.gerente).get(self.ir)

        self.assertRedirects(respuesta, self.detalle, fetch_redirect_response=False)
        self.assertEqual(self.lectura(), Alerta.Lectura.LEIDA)

    def test_el_agronomo_destinatario_tambien_la_abre(self):
        """Mismos permisos que el detalle: el Agrónomo activo que recibe la alerta."""
        propia = crear_alerta(self.sur, "com_falso", para_gerente=False, agronomo=self.agronomo)
        self.con_registrante("/alertas/")

        respuesta = self.cliente_de(self.agronomo).get(reverse("alertas:ir", args=[propia.pk]))

        self.assertRedirects(respuesta, "/alertas/", fetch_redirect_response=False)

    def test_una_alerta_inexistente_da_404(self):
        """D-28: ``abrir_alerta`` da 404 si no existe."""
        respuesta = self.cliente_de(self.gerente).get(reverse("alertas:ir", args=[999999]))

        self.assertEqual(respuesta.status_code, 404)

    def test_una_alerta_ajena_da_403_y_no_marca_nada(self):
        """D-28 y D-62, punto 4: el Agrónomo que no la recibe da 403, no se marca y el registrante no se llama."""
        registrante = mock.Mock(return_value={})
        with mock.patch.object(extensiones, "_ENLACES", []):
            extensiones.registrar_enlace_de_alerta(("com_falso",), registrante)
            respuesta = self.cliente_de(self.agronomo).get(self.ir)

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.lectura(), Alerta.Lectura.NO_LEIDA)
        registrante.assert_not_called()

    def test_otros_roles_dan_403_y_no_marcan_nada(self):
        """Mismos permisos que el detalle (decisión 2 de MAE-02c): un Capataz o el Administrador, 403."""
        for cuenta in (crear_capataz(), crear_administrador()):
            with self.subTest(rol=cuenta.__class__.__name__):
                respuesta = self.cliente_de(cuenta).get(self.ir)
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(self.lectura(), Alerta.Lectura.NO_LEIDA)

    def test_sin_sesion_redirige_al_ingreso(self):
        """Toda pantalla exige sesión (D-25)."""
        respuesta = Client().get(self.ir)

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("iniciar-sesion", respuesta["Location"])
        self.assertEqual(self.lectura(), Alerta.Lectura.NO_LEIDA)

    def test_un_url_que_saca_del_sitio_redirige_al_detalle(self):
        """D-62, tercera enmienda, punto 2: ``alertas:ir`` nunca saca del sitio. Un ``url`` vacío, absoluto, de otro esquema o
        relativo al protocolo va al detalle; la alerta queda «leída» igual."""
        for url in ("", "https://ejemplo.com/x", "//ejemplo.com/x", "/\\ejemplo.com", "javascript:alert(1)", "relativa/x"):
            with self.subTest(url=url):
                Alerta.objects.filter(pk=self.alerta.pk).update(estado_lectura_alerta=Alerta.Lectura.NO_LEIDA)
                with mock.patch.object(extensiones, "_ENLACES", []):
                    extensiones.registrar_enlace_de_alerta(
                        ("com_falso",), lambda usuario, alertas, u=url: {a.pk: Enlace(u, "Texto") for a in alertas}
                    )
                    respuesta = self.cliente_de(self.gerente).get(self.ir)
                self.assertRedirects(respuesta, self.detalle, fetch_redirect_response=False)
                self.assertEqual(self.lectura(), Alerta.Lectura.LEIDA)

    def test_head_da_405_y_no_marca_nada(self):
        """Como el detalle: solo GET, porque abrirla cambia la lectura."""
        respuesta = self.cliente_de(self.gerente).head(self.ir)

        self.assertEqual(respuesta.status_code, 405)
        self.assertEqual(self.lectura(), Alerta.Lectura.NO_LEIDA)

    def test_no_se_guarda_en_la_cache_del_navegador(self):
        """Como el detalle: ``never_cache``."""
        respuesta = self.cliente_de(self.gerente).get(self.ir)

        self.assertIn("no-cache", respuesta["Cache-Control"])
        self.assertIn("no-store", respuesta["Cache-Control"])
