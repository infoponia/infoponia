# Pruebas del envío de correo público de core (USR-10, D-54): ``core/correo.py``. ``enviar_correo`` manda texto plano y
# devuelve True; si el servidor falla devuelve False y deja en los registros el id de la cuenta, nunca el cuerpo.
# ``correo_configurado`` lee ``settings.CORREO_CONFIGURADO`` en cada llamada (D-33). ``_enviar_correo`` de
# ``core/servicios.py`` delega en la pública. Cada prueba arma sus propios datos.

from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from core import extensiones, servicios
from core.correo import correo_configurado, enviar_correo
from core.extensiones import Identidad
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_gerente

PLANTILLA = "core/correos/recuperar_contrasena.txt"
ENLACE = "https://infoponia.test/recuperar-contrasena/abc/TOKEN-SECRETO-123/"


class EnviarCorreoTests(TestCase):
    """D-54, punto 1: ``enviar_correo(cuenta, asunto, plantilla, contexto) -> bool``."""

    @override_settings(DEFAULT_FROM_EMAIL="Vivero de prueba <remitente@prueba.test>")
    def test_d54_enviar_correo_sale_y_devuelve_true(self):
        """D-54 (punto 1) y D-33: sale un solo correo en texto plano a la cuenta, con el asunto, el remitente de la
        configuración y el cuerpo de la plantilla; devuelve True."""
        cuenta = crear_gerente()

        salio = enviar_correo(cuenta, "Asunto de prueba", PLANTILLA, {"nombre": "Gabriela", "enlace": ENLACE})

        self.assertIs(salio, True)
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [cuenta.email])
        self.assertEqual(mensaje.subject, "Asunto de prueba")
        self.assertEqual(mensaje.from_email, "Vivero de prueba <remitente@prueba.test>")
        self.assertEqual(mensaje.content_subtype, "plain")
        self.assertEqual(getattr(mensaje, "alternatives", []), [])
        self.assertIn("Hola Gabriela", mensaje.body)
        self.assertIn(ENLACE, mensaje.body)

    def test_d54_el_contexto_recibe_nombre_organizacion(self):
        """D-48 y D-54: la plantilla recibe ``nombre_organizacion`` (la identidad registrada) sin que quien llama lo
        pase en su contexto."""
        cuenta = crear_gerente()
        identidad_registrada = lambda: Identidad("Vivero Los Álamos", "#336699")  # noqa: E731

        with mock.patch.object(extensiones, "_IDENTIDAD", [identidad_registrada]):
            enviar_correo(cuenta, "Asunto", PLANTILLA, {"nombre": "Gabriela", "enlace": ENLACE})

        self.assertIn("Vivero Los Álamos", mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_d54_falla_del_servidor_devuelve_false_y_registra_el_id_sin_el_cuerpo(self):
        """D-54 (punto 1) y SEG-12: si el servidor falla, devuelve False sin propagar el error y deja un registro de
        error con el id de la cuenta, sin el enlace ni el cuerpo (el enlace da acceso a la cuenta)."""
        cuenta = crear_gerente()

        with self.assertLogs("core.correo", level="ERROR") as registros:
            salio = enviar_correo(cuenta, "Asunto", PLANTILLA, {"nombre": "Gabriela", "enlace": ENLACE})

        self.assertIs(salio, False)
        salida = "\n".join(registros.output)
        self.assertIn(str(cuenta.pk), salida)
        self.assertNotIn("TOKEN-SECRETO-123", salida)
        self.assertNotIn("Hola Gabriela", salida)


class CorreoConfiguradoTests(TestCase):
    """D-54 (punto 1) y D-33: ``correo_configurado() -> bool``."""

    def test_d54_correo_configurado_sigue_al_ajuste_en_cada_llamada(self):
        """D-33 y D-54: lee ``settings.CORREO_CONFIGURADO`` en cada llamada, no una copia: cambiar el ajuste cambia la
        respuesta sin recargar nada."""
        with override_settings(CORREO_CONFIGURADO=True):
            self.assertIs(correo_configurado(), True)
        with override_settings(CORREO_CONFIGURADO=False):
            self.assertIs(correo_configurado(), False)


class EnviarCorreoPrivadoTests(TestCase):
    """D-54, punto 2: ``_enviar_correo`` de ``core/servicios.py`` delega en la pública."""

    def test_d54_enviar_correo_privado_delega_en_el_publico(self):
        """D-54 (punto 2): ``servicios._enviar_correo`` llama una vez a ``core.correo.enviar_correo`` con los mismos
        cuatro argumentos y devuelve lo que ella devuelve."""
        cuenta = crear_gerente()
        contexto = {"nombre": "Gabriela", "enlace": ENLACE}

        with mock.patch("core.correo.enviar_correo", return_value=False) as publica:
            resultado = servicios._enviar_correo(cuenta, "Asunto", PLANTILLA, contexto)

        self.assertIs(resultado, False)
        publica.assert_called_once_with(cuenta, "Asunto", PLANTILLA, contexto)
