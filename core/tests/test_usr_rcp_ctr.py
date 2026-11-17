# Pruebas de USR-RCP-CTR (Recuperar Contraseña) y de los requisitos que cita: SEG-03 y SEG-12
# (docs/casos_de_uso/usuarios.md), más D-33 (configuración del envío de correo) y D-34 (cómo se implementa la
# recuperación). Las de servicio llaman directo a core.servicios (pedir_recuperacion y confirmar_recuperacion); las
# de concurrencia usan dos hilos con core/tests/concurrencia.py. El correo va por mail.outbox (el ejecutor de
# pruebas de Django fuerza el backend locmem): nunca se usan credenciales reales. Cada prueba arma sus propios datos.

import importlib
import re
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings, tag
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core import servicios
from core.forms import FormularioContrasenaNueva
from core.models import GrupoCuentas, RegistroAuditoria, Usuario
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import (
    BACKEND_QUE_FALLA,
    CLAVE,
    afectado,
    agrupar,
    contenido_de_auditoria,
    crear_administrador,
    crear_capataz,
    dar_contrasena_temporal,
    dar_invitacion,
    dar_temporal_vencida,
    sin_csrf,
)

# Cumple SEG-03 y no se parece a los datos de las cuentas de prueba.
NUEVA = "huerta-hidro-2026"
OTRA_NUEVA = "lechuga-nft-2026"

# Mensaje de la contraseña vacía: el de FormularioContrasenaNueva y de cambiar_contrasena.
MENSAJE_CONTRASENA_VACIA = FormularioContrasenaNueva.base_fields["contrasena_nueva"].error_messages["required"]

# Base de los enlaces en las pruebas de servicio: la vista pasa ``request.build_absolute_uri``; acá se simula.
BASE = "https://infoponia.test"
# Enlace del correo: /recuperar-contrasena/<uidb64>/<token>/ (plan de la tarea 08, D-34).
PATRON_ENLACE = re.compile(re.escape(BASE) + r"/recuperar-contrasena/([\w-]+)/([\w-]+)/")


def construir_url(ruta):
    """Hace las veces de ``request.build_absolute_uri``: devuelve la ruta como URL absoluta."""
    return BASE + ruta


def enlace_del_correo(mensaje):
    """``(cuenta_id, token)`` del enlace que trae el cuerpo de un correo de recuperación."""
    encontrado = PATRON_ENLACE.search(mensaje.body)
    if encontrado is None:
        raise AssertionError(f"El correo no trae un enlace de recuperación:\n{mensaje.body}")
    uidb64, token = encontrado.groups()
    return int(force_str(urlsafe_base64_decode(uidb64))), token


@override_settings(CORREO_CONFIGURADO=True)
class UsrRcpCtrServicioTests(TestCase):
    """Reglas, precondiciones y postcondiciones de USR-RCP-CTR en ``pedir_recuperacion`` y
    ``confirmar_recuperacion``. Con el correo configurado salvo en las pruebas de la precondición a."""

    def assertContrasenaSinCambios(self, cuenta, contrasena=CLAVE):
        """La cuenta conserva la contraseña indicada y no se auditó ninguna recuperación."""
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(contrasena))
        self.assertFalse(
            RegistroAuditoria.objects.filter(
                accion=RegistroAuditoria.Accion.RECUPERACION_CONTRASENA
            ).exists()
        )

    def assertEnlaceInvalido(self, cuenta_id, token, nueva=NUEVA):
        """``confirmar_recuperacion`` rechaza el enlace con el código «enlace_invalido» (D-34)."""
        with self.assertRaises(ValidationError) as contexto:
            servicios.confirmar_recuperacion(cuenta_id, token, nueva)
        self.assertIn("enlace_invalido", codigos(contexto.exception))

    # ---- Pedido del enlace ----

    def test_regla_1_envia_un_enlace_a_la_cuenta_activa(self):
        """USR-RCP-CTR regla 1 y SEG-12: a una cuenta activa le llega un correo con un enlace a su nombre, y el
        token del enlace es válido para esa cuenta."""
        capataz = crear_capataz()

        servicios.pedir_recuperacion(capataz.email, construir_url)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [capataz.email])
        cuenta_id, token = enlace_del_correo(mail.outbox[0])
        self.assertEqual(cuenta_id, capataz.pk)
        self.assertTrue(default_token_generator.check_token(capataz, token))

    def test_d34_busca_el_email_sin_distinguir_mayusculas(self):
        """D-34 y SEG-01: el email del pedido se compara sin distinguir mayúsculas (y sin espacios alrededor)."""
        capataz = crear_capataz(email="capataz@infoponia.com")

        servicios.pedir_recuperacion("  CAPATAZ@InfoPonia.com ", construir_url)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [capataz.email])

    def test_regla_2_email_inexistente_no_envia_nada(self):
        """USR-RCP-CTR regla 2 y SEG-12: si no hay cuenta con ese email no se envía nada, y el servicio
        termina igual que cuando la hay (no devuelve nada que la vista pueda distinguir)."""
        crear_capataz()

        resultado = servicios.pedir_recuperacion("nadie@infoponia.com", construir_url)

        self.assertIsNone(resultado)
        self.assertEqual(mail.outbox, [])

    def test_regla_2_cuenta_inactiva_no_recibe_nada(self):
        """USR-RCP-CTR regla 2, precondición b y SEG-12: no se envía nada a una cuenta inactiva."""
        inactiva = crear_capataz(is_active=False)

        resultado = servicios.pedir_recuperacion(inactiva.email, construir_url)

        self.assertIsNone(resultado)
        self.assertEqual(mail.outbox, [])

    def test_d34_administrador_activo_recibe_el_enlace(self):
        """USR-RCP-CTR (actores: todos los roles y el Administrador) y D-34: el Administrador, superusuario sin
        rol (D-10), también recupera su contraseña por correo."""
        administrador = crear_administrador()

        servicios.pedir_recuperacion(administrador.email, construir_url)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(enlace_del_correo(mail.outbox[0])[0], administrador.pk)

    def test_d34_cuenta_con_temporal_vencida_recibe_el_enlace(self):
        """USR-RCP-CTR postcondición b y D-34: una cuenta con contraseña temporal, aunque esté vencida (SEG-04),
        puede pedir el enlace."""
        capataz = crear_capataz()
        dar_temporal_vencida(capataz)

        servicios.pedir_recuperacion(capataz.email, construir_url)

        self.assertEqual(len(mail.outbox), 1)

    def test_d34_el_pedido_no_escribe_en_la_base_ni_audita(self):
        """D-34 y SEG-14: pedir el enlace no escribe nada en la base (solo consulta) ni deja un registro de
        auditoría; lo que se audita es la recuperación, al usar el enlace."""
        capataz = crear_capataz()

        with CaptureQueriesContext(connection) as consultas:
            servicios.pedir_recuperacion(capataz.email, construir_url)

        self.assertEqual(len(mail.outbox), 1)
        escrituras = [
            consulta["sql"]
            for consulta in consultas.captured_queries
            if not consulta["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(escrituras, [])
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_seg12_falla_del_envio_queda_en_el_registro_de_errores_sin_propagarse(self):
        """SEG-12 y D-34: si el envío falla estando configurado, el servicio no propaga el error (la persona
        recibe la misma respuesta) y la falla queda en los registros de errores, con el id de la cuenta y sin el
        enlace (que da acceso a la cuenta)."""
        capataz = crear_capataz()

        with self.assertLogs("core.servicios", level="ERROR") as registros:
            resultado = servicios.pedir_recuperacion(capataz.email, construir_url)

        self.assertIsNone(resultado)
        salida = "\n".join(registros.output)
        self.assertIn(str(capataz.pk), salida)
        self.assertNotIn("recuperar-contrasena", salida)
        self.assertNotIn(BASE, salida)

    def test_seg12_el_correo_es_texto_plano_con_nombre_vencimiento_y_un_solo_uso(self):
        """SEG-12 y D-34: el correo es texto plano y en español; saluda con el nombre, trae el enlace absoluto,
        dice que vence en una hora y que sirve una sola vez, y que si no lo pidió lo ignore."""
        capataz = crear_capataz(first_name="Juana")

        servicios.pedir_recuperacion(capataz.email, construir_url)

        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.content_subtype, "plain")
        self.assertEqual(getattr(mensaje, "alternatives", []), [])
        self.assertIn("contraseña", mensaje.subject.lower())
        self.assertIn("Hola Juana", mensaje.body)
        self.assertRegex(mensaje.body, PATRON_ENLACE)
        self.assertIn("una hora", mensaje.body)
        self.assertIn("una sola vez", mensaje.body)
        self.assertIn("ignorá", mensaje.body.lower())

    @override_settings(CORREO_CONFIGURADO=False)
    def test_pre_a_sin_correo_configurado_no_envia_nada(self):
        """USR-RCP-CTR precondición a, regla 5 y SEG-12: sin el envío de correo configurado el caso de uso no
        está disponible: el servicio lo rechaza con «correo_no_configurado» y no envía nada."""
        capataz = crear_capataz()

        with self.assertRaises(ValidationError) as contexto:
            servicios.pedir_recuperacion(capataz.email, construir_url)

        self.assertIn("correo_no_configurado", codigos(contexto.exception))
        self.assertEqual(mail.outbox, [])

    # ---- Lectura del enlace ----

    def test_d34_cuenta_del_enlace_devuelve_la_cuenta_solo_con_un_enlace_valido(self):
        """D-34 y SEG-12: ``cuenta_del_enlace`` (la lectura que usan las vistas) devuelve la cuenta de un enlace
        válido y ``None`` para uno usado, vencido, alterado, de una cuenta inactiva o con un id ilegible. Es la
        misma regla que ``confirmar_recuperacion`` aplica con la cuenta bloqueada."""
        capataz = crear_capataz()
        uidb64 = urlsafe_base64_encode(force_bytes(capataz.pk))
        token = default_token_generator.make_token(capataz)

        self.assertEqual(servicios.cuenta_del_enlace(uidb64, token).pk, capataz.pk)

        with self.subTest("alterado"):
            alterado = token[:-1] + ("a" if token[-1] != "a" else "b")
            self.assertIsNone(servicios.cuenta_del_enlace(uidb64, alterado))
        with self.subTest("id ilegible"):
            self.assertIsNone(servicios.cuenta_del_enlace("!!!", token))
        with self.subTest("id de otra cuenta"):
            otra = crear_capataz(email="otra@infoponia.com")
            self.assertIsNone(
                servicios.cuenta_del_enlace(urlsafe_base64_encode(force_bytes(otra.pk)), token)
            )
        with self.subTest("vencido"):
            despues = datetime.now() + timedelta(seconds=3601)
            with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=despues):
                self.assertIsNone(servicios.cuenta_del_enlace(uidb64, token))
        with self.subTest("inactiva"):
            Usuario.objects.filter(pk=capataz.pk).update(is_active=False)
            self.assertIsNone(servicios.cuenta_del_enlace(uidb64, token))
            Usuario.objects.filter(pk=capataz.pk).update(is_active=True)
        with self.subTest("usado"):
            servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)
            self.assertIsNone(servicios.cuenta_del_enlace(uidb64, token))

    # ---- Confirmación: la contraseña nueva ----

    def test_post_a_reemplaza_la_contrasena(self):
        """USR-RCP-CTR postcondición a: la contraseña se reemplaza por la que eligió su dueño."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))
        self.assertFalse(capataz.check_password(CLAVE))

    def test_post_b_la_temporal_deja_de_serlo(self):
        """USR-RCP-CTR postcondición b: si la contraseña era temporal, deja de serlo."""
        capataz = crear_capataz()
        dar_contrasena_temporal(capataz)
        token = default_token_generator.make_token(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        capataz.refresh_from_db()
        self.assertIsNone(capataz.fecha_contrasena_temporal)
        self.assertTrue(capataz.check_password(NUEVA))

    def test_post_b_temporal_vencida_puede_recuperar(self):
        """USR-RCP-CTR postcondición b y D-34: una cuenta con la temporal vencida (SEG-04) recupera igual y queda
        sin temporal."""
        capataz = crear_capataz()
        dar_temporal_vencida(capataz)
        token = default_token_generator.make_token(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        capataz.refresh_from_db()
        self.assertIsNone(capataz.fecha_contrasena_temporal)
        self.assertTrue(capataz.check_password(NUEVA))

    def test_post_c_cierra_las_sesiones_abiertas_de_la_cuenta(self):
        """USR-RCP-CTR postcondición c y SEG-12: al usar el enlace se cierran todas las sesiones abiertas con la
        cuenta (mismo mecanismo que el restablecimiento: cambia el resumen de la contraseña)."""
        capataz = crear_capataz()
        sesion = Client()
        sesion.force_login(capataz)
        self.assertEqual(sesion.get(reverse("core:inicio")).status_code, 200)
        capataz.refresh_from_db()  # el inicio de sesión cambió last_login, que firma el token
        token = default_token_generator.make_token(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        respuesta = sesion.get(reverse("core:inicio"))
        self.assertRedirects(
            respuesta,
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:inicio')}",
            fetch_redirect_response=False,
        )


    def test_post_b_recuperar_con_invitacion_pendiente_la_deja_sin_invitacion(self):
        """USR-RCP-CTR postcondición b, SEG-20 y D-35: una cuenta con la invitación pendiente puede recuperar; al
        elegir la contraseña queda sin la invitación (nunca con la invitación y una contraseña a la vez) y la
        auditoría lo dice."""
        capataz = dar_invitacion(crear_capataz())
        token = default_token_generator.make_token(Usuario.objects.get(pk=capataz.pk))

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        capataz = Usuario.objects.get(pk=capataz.pk)
        self.assertTrue(capataz.check_password(NUEVA))
        self.assertIsNone(capataz.fecha_invitacion)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.detalle, {"datos": {"era_temporal": False, "invitacion_pendiente": True}})

    def test_post_d_audita_con_usuario_y_rol_de_la_cuenta_sin_contrasenas(self):
        """USR-RCP-CTR postcondición d, SEG-14 y D-22: un registro con la acción de recuperación; el usuario y
        el rol son los de la cuenta afectada, que es la única afectada; ninguna contraseña ni el token."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.RECUPERACION_CONTRASENA)
        self.assertEqual(registro.usuario_id, capataz.pk)
        self.assertEqual(registro.rol, "capataz")
        self.assertEqual(registro.afectados, [afectado(capataz)])
        self.assertEqual(registro.detalle, {"datos": {"era_temporal": False, "invitacion_pendiente": False}})
        contenido = contenido_de_auditoria(registro)
        for secreto in (NUEVA, CLAVE, token):
            self.assertNotIn(secreto, contenido)

    def test_post_d_administrador_queda_auditado_con_su_rol(self):
        """USR-RCP-CTR postcondición d y D-34: si recupera un Administrador, el registro lleva su cuenta y el rol
        «administrador» (D-10)."""
        administrador = crear_administrador()
        token = default_token_generator.make_token(administrador)

        servicios.confirmar_recuperacion(administrador.pk, token, NUEVA)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.usuario_id, administrador.pk)
        self.assertEqual(registro.rol, "administrador")

    def test_regla_1_el_enlace_sirve_una_sola_vez(self):
        """USR-RCP-CTR regla 1 y SEG-12: un enlace ya usado no vuelve a servir, y no cambia nada."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)
        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        self.assertEnlaceInvalido(capataz.pk, token, OTRA_NUEVA)

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    def test_regla_1_el_enlace_vence_a_la_hora(self):
        """USR-RCP-CTR regla 1 y SEG-12: pasada una hora (3601 s) el enlace venció y no cambia nada."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)
        despues = datetime.now() + timedelta(seconds=3601)

        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=despues):
            self.assertEnlaceInvalido(capataz.pk, token)

        self.assertContrasenaSinCambios(capataz)

    def test_regla_1_el_enlace_sirve_antes_de_la_hora(self):
        """USR-RCP-CTR regla 1 y SEG-12: antes de la hora (3599 s) el enlace todavía sirve."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)
        antes = datetime.now() + timedelta(seconds=3599)

        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=antes):
            servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))

    def test_d34_enlace_alterado_se_rechaza(self):
        """D-34 y SEG-12: un token alterado, uno de otra cuenta o una cuenta que no existe dan «enlace_invalido»."""
        capataz = crear_capataz()
        otra = crear_capataz(email="otra@infoponia.com")
        token = default_token_generator.make_token(capataz)
        token_de_otra = default_token_generator.make_token(otra)

        casos = {
            "token alterado": (capataz.pk, token[:-1] + ("a" if token[-1] != "a" else "b")),
            "token de otra cuenta": (capataz.pk, token_de_otra),
            "cuenta inexistente": (otra.pk + 1000, token),
            "sin cuenta": (None, token),
        }
        for nombre, (cuenta_id, token_del_caso) in casos.items():
            with self.subTest(nombre):
                self.assertEnlaceInvalido(cuenta_id, token_del_caso)

        self.assertContrasenaSinCambios(capataz)
        self.assertContrasenaSinCambios(otra)

    def test_d34_cuenta_que_paso_a_inactiva_rechaza_el_enlace(self):
        """USR-RCP-CTR precondición b y D-34: si la cuenta se dio de baja después de pedir el enlace, el enlace
        ya no sirve."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)
        Usuario.objects.filter(pk=capataz.pk).update(is_active=False)

        self.assertEnlaceInvalido(capataz.pk, token)

        self.assertContrasenaSinCambios(capataz)

    def test_d34_iniciar_sesion_invalida_el_enlace(self):
        """D-34: el token de Django firma también el último inicio de sesión, así que un enlace pedido antes de
        que la cuenta inicie sesión deja de servir (la persona se acordó de la contraseña)."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)
        Client().force_login(capataz)

        self.assertEnlaceInvalido(capataz.pk, token)

        self.assertContrasenaSinCambios(capataz)

    def test_regla_3_no_genera_temporal_y_mantiene_el_grupo(self):
        """USR-RCP-CTR regla 3 y D-17: la recuperación no deja una contraseña temporal y la cuenta sigue en su
        grupo de cuentas vinculadas (a diferencia del restablecimiento, SEG-11)."""
        capataz = crear_capataz()
        otra = crear_capataz(email="otra@infoponia.com")
        grupo = agrupar(capataz, otra)
        token = default_token_generator.make_token(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        capataz.refresh_from_db()
        otra.refresh_from_db()
        self.assertIsNone(capataz.fecha_contrasena_temporal)
        self.assertEqual(capataz.grupo_id, grupo.pk)
        self.assertEqual(otra.grupo_id, grupo.pk)
        self.assertTrue(GrupoCuentas.objects.filter(pk=grupo.pk).exists())

    def test_regla_4_rechaza_la_contrasena_que_no_cumple_la_politica(self):
        """USR-RCP-CTR regla 4 y SEG-03: la contraseña nueva cumple la política (validadores de Django y
        «distinta de la actual»). Si no, el error va en el campo ``contrasena_nueva``, no cambia nada y no se
        audita; el enlace sigue sirviendo para otro intento."""
        capataz = crear_capataz(
            email="maximiliano@infoponia.com", first_name="Maximiliano", last_name="Fernández"
        )
        token = default_token_generator.make_token(capataz)

        casos = {
            "corta": ("hid-26", "password_too_short"),
            "solo números": ("83920174", "password_entirely_numeric"),
            "común": ("password1", "password_too_common"),
            "parecida a los datos": ("maximiliano26", "password_too_similar"),
            "igual a la actual": (CLAVE, "contrasena_igual_a_la_actual"),
            "vacía": ("", "required"),
        }
        for nombre, (contrasena, codigo) in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ValidationError) as contexto:
                    servicios.confirmar_recuperacion(capataz.pk, token, contrasena)
                errores = contexto.exception.error_dict.get("contrasena_nueva", [])
                self.assertIn(codigo, [e.code for e in errores])
                if codigo == "required":
                    # Mismo mensaje que el formulario y que cambiar_contrasena para la contraseña vacía.
                    self.assertEqual([e.message for e in errores], [MENSAJE_CONTRASENA_VACIA])
                self.assertContrasenaSinCambios(capataz)

        servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))

    @override_settings(CORREO_CONFIGURADO=False)
    def test_pre_a_sin_correo_configurado_no_cambia_nada(self):
        """USR-RCP-CTR precondición a y regla 5: sin el envío de correo configurado, un enlace válido tampoco
        sirve; el rechazo lleva «correo_no_configurado» y no cambia nada."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)

        with self.assertRaises(ValidationError) as contexto:
            servicios.confirmar_recuperacion(capataz.pk, token, NUEVA)

        self.assertIn("correo_no_configurado", codigos(contexto.exception))
        self.assertContrasenaSinCambios(capataz)


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=True)
class UsrRcpCtrConcurrenciaTests(TransactionTestCase):
    """Regla 1 de USR-RCP-CTR y SEG-12 con dos pedidos simultáneos: el enlace es de un solo uso también cuando
    llegan dos confirmaciones a la vez (doble clic, o el enlace abierto en dos pestañas). Son
    ``TransactionTestCase`` porque cada operación corre en su propio hilo, con su propia conexión y transacción
    (ver ``core/tests/concurrencia.py``)."""

    def test_d34_dos_confirmaciones_con_el_mismo_enlace_cambian_una_sola_vez(self):
        """USR-RCP-CTR regla 1, SEG-12 y D-34: dos confirmaciones con el mismo enlace y contraseñas distintas.
        ``correr_a_la_vez`` detiene a la primera justo después de ``registrar`` (por defecto): ya bloqueó la cuenta,
        cambió la contraseña y auditó, pero todavía no confirmó. Recién entonces arranca la segunda, que queda
        esperando el bloqueo. Cuando sigue, vuelve a validar el token con la fila releída: la contraseña ya cambió, así que el
        token no vale y se rechaza con «enlace_invalido». Si el token se validara solo antes de bloquear (o solo
        en la vista), las dos pasarían y el enlace no sería de un solo uso: esta prueba falla."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)

        resultados = correr_a_la_vez(
            lambda: servicios.confirmar_recuperacion(capataz.pk, token, NUEVA),
            lambda: servicios.confirmar_recuperacion(capataz.pk, token, OTRA_NUEVA),
            primera="a",
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("enlace_invalido", codigos(rechazos[0]))
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))
        self.assertEqual(
            RegistroAuditoria.objects.filter(
                accion=RegistroAuditoria.Accion.RECUPERACION_CONTRASENA
            ).count(),
            1,
        )


class CorreoConfiguracionTests(TestCase):
    """D-33: cuándo el envío de correo está configurado (SEG-12, precondición a de USR-RCP-CTR) y la
    configuración de SMTP. Las reglas viven en ``config/correo.py``, funciones puras que reciben el entorno, para
    probarlas sin recargar los settings."""

    @staticmethod
    def correo():
        """El módulo ``config.correo``."""
        return importlib.import_module("config.correo")

    def test_d33_sin_credenciales_no_esta_configurado(self):
        """D-33 y SEG-12: sin las dos variables del servidor de correo (o con una sola), no está configurado."""
        correo = self.correo()
        casos = {
            "sin variables": {},
            "solo el usuario": {"EMAIL_HOST_USER": "infoponia.notificaciones@gmail.com"},
            "solo la contraseña": {"EMAIL_HOST_PASSWORD": "x"},
            "vacías": {"EMAIL_HOST_USER": "", "EMAIL_HOST_PASSWORD": ""},
        }
        for nombre, entorno in casos.items():
            for debug in (True, False):
                with self.subTest(nombre, debug=debug):
                    self.assertFalse(correo.correo_configurado(entorno, debug))

    def test_d33_con_credenciales_esta_configurado(self):
        """D-33 y SEG-12: con el usuario y la contraseña de aplicación definidos, está configurado (en
        producción y en desarrollo)."""
        correo = self.correo()
        entorno = {"EMAIL_HOST_USER": "infoponia.notificaciones@gmail.com", "EMAIL_HOST_PASSWORD": "x"}
        for debug in (True, False):
            with self.subTest(debug=debug):
                self.assertTrue(correo.correo_configurado(entorno, debug))
                self.assertFalse(correo.correo_por_consola(entorno, debug))

    def test_d33_consola_solo_con_debug(self):
        """D-33: ``CORREO_CONSOLA=1`` usa el backend de consola y cuenta como configurado solo con DEBUG
        encendido. Con DEBUG apagado se ignora: en producción los enlaces quedarían escritos en los registros."""
        correo = self.correo()
        entorno = {"CORREO_CONSOLA": "1"}

        self.assertTrue(correo.correo_por_consola(entorno, True))
        self.assertTrue(correo.correo_configurado(entorno, True))
        self.assertFalse(correo.correo_por_consola(entorno, False))
        self.assertFalse(correo.correo_configurado(entorno, False))
        self.assertFalse(correo.correo_por_consola({"CORREO_CONSOLA": "0"}, True))

    def test_d33_smtp_de_gmail_con_tls_y_limite_de_espera(self):
        """D-33: Gmail por SMTP en el puerto 587 con TLS, remitente de la cuenta de notificaciones y un límite
        de espera de 10 s (gunicorn corta a los 30 s; un SMTP colgado no puede tirar el worker)."""
        from django.conf import settings

        self.assertEqual(settings.EMAIL_HOST, "smtp.gmail.com")
        self.assertEqual(settings.EMAIL_PORT, 587)
        self.assertTrue(settings.EMAIL_USE_TLS)
        self.assertEqual(settings.EMAIL_TIMEOUT, 10)
        self.assertEqual(settings.DEFAULT_FROM_EMAIL, "InfoPonia <infoponia.notificaciones@gmail.com>")
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)


@override_settings(CORREO_CONFIGURADO=True)
class UsrRcpCtrVistaTests(TestCase):
    """Flujos de USR-RCP-CTR con el cliente de prueba de Django contra las pantallas de pedido, «Revisá tu correo»,
    entrada del enlace, contraseña nueva y enlace no válido (vRecover, vRecoverSent, vReset y vLinkBad del
    prototipo). El correo va por ``mail.outbox``. Cada prueba arma sus propios datos."""

    PATRON_RUTA = re.compile(r"https?://testserver(/recuperar-contrasena/[\w-]+/[\w-]+/)")

    def pedir(self, email, **extra):
        """Envía el formulario de pedido con ``email``."""
        return self.client.post(reverse("core:recuperar_contrasena"), {"email": email}, **extra)

    def ruta_del_enlace(self, mensaje=None):
        """Ruta (sin el dominio) del enlace que trae el último correo enviado."""
        mensaje = mensaje or mail.outbox[-1]
        encontrado = self.PATRON_RUTA.search(mensaje.body)
        self.assertIsNotNone(encontrado, mensaje.body)
        return encontrado.group(1)

    @staticmethod
    def enlace_de(cuenta, token=None, uidb64=None):
        """Ruta del enlace de ``cuenta``, con un token recién generado (o el indicado)."""
        return reverse(
            "core:recuperacion_enlace",
            kwargs={
                "uidb64": uidb64 or urlsafe_base64_encode(force_bytes(cuenta.pk)),
                "token": token or default_token_generator.make_token(cuenta),
            },
        )

    def elegir_url(self, cuenta):
        """URL de la pantalla de la contraseña nueva de ``cuenta`` (sin el token)."""
        return reverse(
            "core:recuperacion_elegir", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(cuenta.pk))}
        )

    def abrir_enlace(self, cuenta, token=None):
        """Abre el enlace de ``cuenta`` con el cliente de la prueba (guarda el token en su sesión)."""
        return self.client.get(self.enlace_de(cuenta, token))

    def elegir(self, cuenta, nueva=NUEVA, repetida=None):
        """Envía el formulario de la contraseña nueva de ``cuenta``."""
        return self.client.post(
            self.elegir_url(cuenta),
            {"contrasena_nueva": nueva, "contrasena_repetida": nueva if repetida is None else repetida},
        )

    def assertEnlaceNoValido(self, respuesta):
        """La respuesta es la pantalla «Enlace no válido», con la opción de pedir otro."""
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "core/recuperar_enlace_invalido.html")
        self.assertContains(respuesta, "Este enlace no es válido o ya venció")
        self.assertContains(respuesta, f'href="{reverse("core:recuperar_contrasena")}"')

    # ---- Flujo principal ----

    def test_flujo_principal_pide_enlace_y_elige_contrasena(self):
        """USR-RCP-CTR, flujo principal: la persona pide el enlace, lo abre desde el correo, elige una contraseña
        nueva y llega al inicio de sesión con un aviso, sin sesión iniciada. Después entra con la nueva."""
        capataz = crear_capataz()

        respuesta = self.pedir(capataz.email)
        self.assertRedirects(respuesta, reverse("core:recuperacion_enviada"))
        self.assertEqual(len(mail.outbox), 1)

        respuesta = self.client.get(self.ruta_del_enlace())
        self.assertRedirects(respuesta, self.elegir_url(capataz), fetch_redirect_response=False)
        respuesta = self.client.get(self.elegir_url(capataz))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "core/recuperar_elegir.html")

        respuesta = self.elegir(capataz)
        self.assertRedirects(respuesta, reverse("core:iniciar_sesion"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        pantalla = self.client.get(reverse("core:iniciar_sesion"))
        self.assertContains(pantalla, "Contraseña actualizada. Ingresá con la nueva contraseña.")

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))
        entrada = self.client.post(
            reverse("core:iniciar_sesion"), {"username": capataz.email, "password": NUEVA}
        )
        self.assertRedirects(entrada, reverse("core:inicio"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)

    def test_regla_2_misma_respuesta_exista_o_no_la_cuenta(self):
        """USR-RCP-CTR regla 2 y SEG-12: el pedido de una cuenta activa, de una inactiva y de un email que no existe
        tiene la misma respuesta (redirección y pantalla), y el correo solo sale para la activa."""
        activa = crear_capataz(email="activa@infoponia.com")
        inactiva = crear_capataz(email="baja@infoponia.com", is_active=False)

        respuestas = {
            "activa": self.pedir(activa.email, follow=True),
            "inactiva": self.pedir(inactiva.email, follow=True),
            "inexistente": self.pedir("nadie@infoponia.com", follow=True),
        }

        base = respuestas["activa"]
        self.assertEqual(base.redirect_chain, [(reverse("core:recuperacion_enviada"), 302)])
        for nombre, respuesta in respuestas.items():
            with self.subTest(nombre):
                self.assertEqual(respuesta.status_code, base.status_code)
                self.assertEqual(respuesta.redirect_chain, base.redirect_chain)
                self.assertEqual(sin_csrf(respuesta.content), sin_csrf(base.content))
        self.assertEqual([m.to for m in mail.outbox], [[activa.email]])

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_seg12_falla_del_envio_da_la_misma_respuesta(self):
        """SEG-12: si el envío falla estando configurado, la persona recibe la misma respuesta que si hubiera
        salido bien (sin un error 500) y la falla queda en los registros de errores."""
        capataz = crear_capataz()

        with self.assertLogs("core.servicios", level="ERROR"):
            respuesta = self.pedir(capataz.email, follow=True)

        self.assertEqual(respuesta.redirect_chain, [(reverse("core:recuperacion_enviada"), 302)])
        self.assertContains(respuesta, "Revisá tu correo")

    def test_d34_pedido_con_email_invalido_muestra_el_error(self):
        """D-34 (vRecover): un email vacío o sin forma de email vuelve al formulario con el mensaje del prototipo y
        no envía nada."""
        casos = {"": "Ingresá tu email.", "no-es-un-email": "Ingresá un email válido, por ejemplo nombre@dominio.com."}
        for email, mensaje in casos.items():
            with self.subTest(email):
                respuesta = self.pedir(email)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, mensaje)
        self.assertEqual(mail.outbox, [])

    # ---- Precondición a y regla 5: el correo no está configurado ----

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_5_con_correo_el_inicio_de_sesion_ofrece_recuperar(self):
        """USR-RCP-CTR regla 5 y SEG-12: con el correo configurado, el inicio de sesión ofrece «¿Olvidaste tu
        contraseña?» con un enlace a la recuperación."""
        respuesta = self.client.get(reverse("core:iniciar_sesion"))

        self.assertContains(respuesta, f'href="{reverse("core:recuperar_contrasena")}"')
        self.assertNotContains(respuesta, "Pedile a quien gestiona tu cuenta")

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_5_sin_correo_el_inicio_de_sesion_no_ofrece_recuperar(self):
        """USR-RCP-CTR regla 5 y SEG-12: sin el correo configurado, el inicio de sesión no ofrece la recuperación:
        solo el aviso de pedirle a quien gestiona la cuenta que la restablezca."""
        respuesta = self.client.get(reverse("core:iniciar_sesion"))

        self.assertNotContains(respuesta, reverse("core:recuperar_contrasena"))
        self.assertContains(respuesta, "Pedile a quien gestiona tu cuenta que la restablezca")

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_5_sin_correo_el_pedido_no_muestra_formulario(self):
        """USR-RCP-CTR regla 5: sin el correo configurado, la URL del pedido muestra que hay que pedirle a quien
        gestiona la cuenta que la restablezca, sin formulario. Un POST tampoco envía nada ni da un error."""
        capataz = crear_capataz()

        for nombre, respuesta in {
            "GET": self.client.get(reverse("core:recuperar_contrasena")),
            "POST": self.pedir(capataz.email),
        }.items():
            with self.subTest(nombre):
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Pedile a quien gestiona tu cuenta que la restablezca")
                self.assertNotContains(respuesta, "<form")
        self.assertEqual(mail.outbox, [])

    @override_settings(CORREO_CONFIGURADO=False)
    def test_regla_5_sin_correo_el_enlace_no_cambia_nada(self):
        """USR-RCP-CTR precondición a: sin el correo configurado, un enlace válido lleva al aviso del pedido y no
        deja elegir la contraseña."""
        capataz = crear_capataz()

        respuesta = self.abrir_enlace(capataz)
        self.assertRedirects(
            respuesta, reverse("core:recuperar_contrasena"), fetch_redirect_response=False
        )
        respuesta = self.elegir(capataz)
        self.assertRedirects(
            respuesta, reverse("core:recuperar_contrasena"), fetch_redirect_response=False
        )

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(CLAVE))

    # ---- Pantallas solo para quien no tiene sesión ----

    def test_d34_con_sesion_iniciada_las_pantallas_redirigen_al_inicio(self):
        """D-34: las pantallas de recuperación son solo para quien no tiene sesión; con sesión iniciada llevan al
        inicio, también con un POST."""
        capataz = crear_capataz()
        self.client.force_login(capataz)
        urls = {
            "pedido": reverse("core:recuperar_contrasena"),
            "enviado": reverse("core:recuperacion_enviada"),
            "enlace": self.enlace_de(capataz),
            "elegir": self.elegir_url(capataz),
        }

        for nombre, url in urls.items():
            with self.subTest(nombre):
                self.assertRedirects(self.client.get(url), reverse("core:inicio"), fetch_redirect_response=False)
        with self.subTest("POST del pedido"):
            respuesta = self.pedir(capataz.email)
            self.assertRedirects(respuesta, reverse("core:inicio"), fetch_redirect_response=False)
        self.assertEqual(mail.outbox, [])

    # ---- El token no queda en la URL del formulario ----

    def test_d34_la_url_del_formulario_no_lleva_el_token(self):
        """D-34: el enlace del correo guarda el token en la sesión y redirige a una URL sin él, para que no quede
        en el historial, en el Referer ni en los registros mientras se escribe la contraseña. La pantalla de la
        contraseña nueva tampoco lo repite."""
        capataz = crear_capataz()
        token = default_token_generator.make_token(capataz)

        respuesta = self.abrir_enlace(capataz, token)

        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn(token, respuesta["Location"])
        pantalla = self.client.get(respuesta["Location"])
        self.assertEqual(pantalla.status_code, 200)
        self.assertNotContains(pantalla, token)

    # ---- Enlace no válido ----

    def test_d34_enlace_invalido_muestra_pedir_otro(self):
        """USR-RCP-CTR regla 1, SEG-12 y D-34: un enlace usado, vencido, alterado, de una cuenta que pasó a inactiva
        o con un id ilegible muestra la misma pantalla de «Enlace no válido», con la opción de pedir otro, y no
        cambia nada. Cubre ``cuenta_del_enlace`` por la vista."""
        pantallas = {}

        def caso(nombre, preparar):
            """Arma una cuenta nueva, prepara el caso y abre el enlace con un cliente nuevo."""
            cuenta = crear_capataz(email=f"{len(pantallas)}@infoponia.com")
            token = default_token_generator.make_token(cuenta)
            url = preparar(cuenta, token)
            with self.subTest(nombre):
                respuesta = Client().get(url or self.enlace_de(cuenta, token))
                self.assertEnlaceNoValido(respuesta)
                cuenta.refresh_from_db()
                self.assertTrue(cuenta.check_password(CLAVE) or nombre == "usado")
                pantallas[nombre] = sin_csrf(respuesta.content)

        caso("usado", lambda cuenta, token: servicios.confirmar_recuperacion(cuenta.pk, token, NUEVA) and None)
        caso(
            "alterado",
            lambda cuenta, token: self.enlace_de(cuenta, token[:-1] + ("a" if token[-1] != "a" else "b")),
        )
        caso("inactiva", lambda cuenta, token: Usuario.objects.filter(pk=cuenta.pk).update(is_active=False) and None)
        caso("id ilegible", lambda cuenta, token: self.enlace_de(cuenta, token, uidb64="!!!"))

        cuenta = crear_capataz(email="vencido@infoponia.com")
        token = default_token_generator.make_token(cuenta)
        despues = datetime.now() + timedelta(seconds=3601)
        with self.subTest("vencido"), mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=despues):
            respuesta = Client().get(self.enlace_de(cuenta, token))
            self.assertEnlaceNoValido(respuesta)
            pantallas["vencido"] = sin_csrf(respuesta.content)

        # Es la misma pantalla para todas las causas: no revela cuál fue.
        self.assertEqual(len(set(pantallas.values())), 1, list(pantallas))

    def test_d34_enlace_que_deja_de_servir_mientras_se_escribe_muestra_enlace_no_valido(self):
        """D-34: si el enlace se usa en otra pestaña, la cuenta se da de baja o la sesión pierde el token mientras
        la persona escribe, al enviar la contraseña se muestra «Enlace no válido» y no cambia nada."""
        casos = {
            "usado en otra pestaña": lambda cuenta, token: servicios.confirmar_recuperacion(cuenta.pk, token, OTRA_NUEVA),
            "cuenta dada de baja": lambda cuenta, token: Usuario.objects.filter(pk=cuenta.pk).update(is_active=False),
            "sin el token en la sesión": lambda cuenta, token: self.client.session.flush(),
        }
        for numero, (nombre, preparar) in enumerate(casos.items()):
            with self.subTest(nombre):
                self.client = Client()
                cuenta = crear_capataz(email=f"escribe{numero}@infoponia.com")
                token = default_token_generator.make_token(cuenta)
                self.abrir_enlace(cuenta, token)
                preparar(cuenta, token)

                respuesta = self.elegir(cuenta)

                self.assertEnlaceNoValido(respuesta)
                cuenta.refresh_from_db()
                self.assertFalse(cuenta.check_password(NUEVA))

    def test_d34_pantalla_de_contrasena_sin_haber_abierto_el_enlace_muestra_enlace_no_valido(self):
        """D-34: abrir directamente la URL de la contraseña nueva, sin haber pasado por el enlace del correo (sin
        token en la sesión), muestra «Enlace no válido»."""
        capataz = crear_capataz()

        respuesta = self.client.get(self.elegir_url(capataz))

        self.assertEnlaceNoValido(respuesta)

    # ---- Enlace absoluto y https ----

    def test_d34_detras_del_proxy_el_enlace_es_https(self):
        """D-34 y SEG-16: el enlace del correo es absoluto; detrás del proxy de Render (``X-Forwarded-Proto: https``,
        ``SECURE_PROXY_SSL_HEADER``) empieza con https, y sin ese encabezado, con http (desarrollo)."""
        capataz = crear_capataz()

        # Como en Render: el proxy manda el encabezado Host (el cliente de prueba no lo manda y Django agregaría
        # el puerto 80 al armar el host) y X-Forwarded-Proto.
        self.pedir(capataz.email, headers={"X-Forwarded-Proto": "https", "Host": "testserver"})
        self.pedir(capataz.email, headers={"Host": "testserver"})

        self.assertIn("https://testserver/recuperar-contrasena/", mail.outbox[0].body)
        self.assertIn("http://testserver/recuperar-contrasena/", mail.outbox[1].body)
        self.assertNotIn("https://", mail.outbox[1].body)

    # ---- Después de elegir la contraseña ----

    def test_d34_no_inicia_sesion_automaticamente(self):
        """D-29 y D-34: al elegir la contraseña nueva no se inicia sesión (tener el correo no alcanza para entrar):
        se lleva al inicio de sesión. Una sesión abierta de la cuenta en otro navegador se cierra (postcondición c)."""
        capataz = crear_capataz()
        otra_sesion = Client()
        otra_sesion.force_login(capataz)
        capataz.refresh_from_db()  # el inicio de sesión cambió last_login, que firma el token
        self.abrir_enlace(capataz)

        self.elegir(capataz)

        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(
            self.client.get(reverse("core:inicio")),
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:inicio')}",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            otra_sesion.get(reverse("core:inicio")),
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:inicio')}",
            fetch_redirect_response=False,
        )

    def test_regla_4_errores_de_politica_en_el_formulario(self):
        """USR-RCP-CTR regla 4 y SEG-03: una contraseña que no cumple la política, o dos que no coinciden, vuelven al
        formulario con el error en el campo, sin cambiar nada; el enlace sigue sirviendo para otro intento."""
        capataz = crear_capataz()
        self.abrir_enlace(capataz)

        sin_politica = self.elegir(capataz, "123")
        self.assertEqual(sin_politica.status_code, 200)
        self.assertTemplateUsed(sin_politica, "core/recuperar_elegir.html")
        self.assertContains(sin_politica, 'id="error-contrasena_nueva"')

        distintas = self.elegir(capataz, NUEVA, repetida=OTRA_NUEVA)
        self.assertContains(distintas, "Las contraseñas no coinciden.")

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

        correcto = self.elegir(capataz)
        self.assertRedirects(correcto, reverse("core:iniciar_sesion"), fetch_redirect_response=False)
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))

    def test_d35_la_pantalla_revisa_tu_correo_sugiere_la_carpeta_de_spam(self):
        """D-35 (lineamiento 11): «Revisá tu correo» sugiere revisar la carpeta de Spam si el correo no llega."""
        respuesta = self.client.get(reverse("core:recuperacion_enviada"))

        self.assertContains(respuesta, "Revisá la carpeta de Spam")

    def test_post_d_la_recuperacion_por_las_pantallas_queda_auditada(self):
        """USR-RCP-CTR postcondición d: la recuperación hecha por las pantallas deja el registro de auditoría con
        la cuenta afectada, y el pedido del enlace no deja ninguno."""
        capataz = crear_capataz()
        self.pedir(capataz.email)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

        self.client.get(self.ruta_del_enlace())
        self.elegir(capataz)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.RECUPERACION_CONTRASENA)
        self.assertEqual(registro.usuario_id, capataz.pk)
