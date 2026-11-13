# Pruebas de USR-CMB-CTR (Cambiar Contraseña) y de los requisitos que cita: SEG-02, SEG-03, SEG-10 y
# SEG-14 (docs/casos_de_uso/usuarios.md), más D-18 y D-22. Las de servicio llaman directo a
# core.servicios.cambiar_contrasena; las de la vista (integración) usan el cliente de prueba contra la
# pantalla «Elegí tu contraseña» (vForced). Cada prueba arma sus propios datos.

import json

from django.contrib.auth.hashers import get_hasher, identify_hasher
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Capataz, RegistroAuditoria
from core.servicios import cambiar_contrasena
from core.tests.fabricas import CLAVE, crear_capataz

# Nombre y apellido largos, para poder probar el parecido con los datos de la cuenta (SEG-03).
MAXIMILIANO = {"first_name": "Maximiliano", "last_name": "Fernández"}
# Cumple SEG-03 y no se parece a los datos de la cuenta de prueba.
NUEVA = "huerta-hidro-2026"


def dar_contrasena_temporal(usuario):
    """Le asigna a la cuenta una contraseña temporal (SEG-04) y devuelve su texto plano."""
    temporal = usuario.asignar_contrasena_temporal()
    usuario.save()
    return temporal


def codigos(error, campo):
    """Códigos de los errores de validación de un campo."""
    return [e.code for e in error.error_dict.get(campo, [])]


class UsrCmbCtrServicioTests(TestCase):
    """Reglas y postcondiciones de USR-CMB-CTR en el servicio ``cambiar_contrasena``."""

    def assertContrasenaSinCambios(self, usuario, contrasena):
        """La cuenta conserva la contraseña indicada."""
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password(contrasena))

    # ---- Reglas del caso de uso ----

    def test_regla_1_sin_temporal_pide_contrasena_actual(self):
        """USR-CMB-CTR regla 1: si la cuenta no tiene temporal, el cambio pide la contraseña actual."""
        capataz = crear_capataz(**MAXIMILIANO)

        with self.assertRaises(ValidationError) as contexto:
            cambiar_contrasena(capataz, NUEVA)

        self.assertIn("contrasena_actual", contexto.exception.message_dict)
        self.assertContrasenaSinCambios(capataz, CLAVE)

    def test_regla_1_rechaza_contrasena_actual_incorrecta(self):
        """USR-CMB-CTR regla 1: la contraseña actual tiene que ser la correcta."""
        capataz = crear_capataz(**MAXIMILIANO)

        with self.assertRaises(ValidationError) as contexto:
            cambiar_contrasena(capataz, NUEVA, contrasena_actual="otra-clave-999")

        self.assertIn("contrasena_actual", contexto.exception.message_dict)
        self.assertContrasenaSinCambios(capataz, CLAVE)

    def test_regla_1_con_temporal_no_pide_contrasena_actual(self):
        """USR-CMB-CTR regla 1 y relación con USR-INI-SES: cuando el caso extiende al inicio de
        sesión (la cuenta tiene temporal), no se pide la contraseña actual."""
        capataz = crear_capataz(**MAXIMILIANO)
        dar_contrasena_temporal(capataz)

        cambiar_contrasena(capataz, NUEVA)

        self.assertContrasenaSinCambios(capataz, NUEVA)

    def test_regla_2_rechaza_contrasena_igual_a_la_actual(self):
        """USR-CMB-CTR regla 2 y SEG-03: la contraseña nueva es distinta de la actual."""
        capataz = crear_capataz(**MAXIMILIANO)

        with self.assertRaises(ValidationError) as contexto:
            cambiar_contrasena(capataz, CLAVE, contrasena_actual=CLAVE)

        self.assertIn(
            "contrasena_igual_a_la_actual", codigos(contexto.exception, "contrasena_nueva")
        )

    def test_regla_2_rechaza_contrasena_igual_a_la_temporal(self):
        """USR-CMB-CTR regla 2, SEG-03 y SEG-04: la contraseña nueva es distinta de la temporal, y
        mientras no se reemplace la cuenta sigue con temporal."""
        capataz = crear_capataz(**MAXIMILIANO)
        temporal = dar_contrasena_temporal(capataz)

        with self.assertRaises(ValidationError) as contexto:
            cambiar_contrasena(capataz, temporal)

        self.assertIn(
            "contrasena_igual_a_la_actual", codigos(contexto.exception, "contrasena_nueva")
        )
        capataz.refresh_from_db()
        self.assertIsNotNone(capataz.fecha_contrasena_temporal)

    # ---- Política de contraseñas (SEG-03) ----

    def assertRechazaPorPolitica(self, nueva, codigo):
        """El cambio a ``nueva`` falla en el campo de la contraseña nueva con el código de Django
        indicado, y la contraseña no cambia."""
        capataz = crear_capataz(**MAXIMILIANO)

        with self.assertRaises(ValidationError) as contexto:
            cambiar_contrasena(capataz, nueva, contrasena_actual=CLAVE)

        self.assertIn(codigo, codigos(contexto.exception, "contrasena_nueva"))
        self.assertContrasenaSinCambios(capataz, CLAVE)

    def test_seg03_rechaza_menos_de_8_caracteres(self):
        """SEG-03: la contraseña nueva tiene al menos 8 caracteres."""
        self.assertRechazaPorPolitica("Hu3rt-a", "password_too_short")

    def test_seg03_rechaza_contrasena_comun(self):
        """SEG-03: la contraseña nueva no está en la lista de contraseñas comunes de Django."""
        self.assertRechazaPorPolitica("password", "password_too_common")

    def test_seg03_rechaza_solo_numerica(self):
        """SEG-03: la contraseña nueva no es solo numérica."""
        self.assertRechazaPorPolitica("4829173650", "password_entirely_numeric")

    def test_seg03_rechaza_contrasena_parecida_a_los_datos_de_la_cuenta(self):
        """SEG-03: la contraseña nueva no se parece al nombre, al apellido ni al email de la cuenta."""
        for dato, nueva in (
            ("nombre", "maximiliano1"),
            ("apellido", "fernandez1"),
            ("email", "capataz2026"),
        ):
            with self.subTest(dato=dato):
                self.assertRechazaPorPolitica(nueva, "password_too_similar")
                Capataz.objects.all().delete()

    # ---- Postcondiciones ----

    def test_post_a_reemplaza_la_contrasena(self):
        """USR-CMB-CTR postcondición a: la contraseña se reemplazó por la nueva."""
        capataz = crear_capataz(**MAXIMILIANO)

        cambiar_contrasena(capataz, NUEVA, contrasena_actual=CLAVE)

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))
        self.assertFalse(capataz.check_password(CLAVE))

    def test_post_b_la_temporal_deja_de_serlo(self):
        """USR-CMB-CTR postcondición b y D-18: si la contraseña era temporal, deja de serlo (la fecha
        de generación queda vacía)."""
        capataz = crear_capataz(**MAXIMILIANO)
        dar_contrasena_temporal(capataz)

        cambiar_contrasena(capataz, NUEVA)

        capataz.refresh_from_db()
        self.assertIsNone(capataz.fecha_contrasena_temporal)

    def test_post_d_crea_registro_de_auditoria(self):
        """USR-CMB-CTR postcondición d, SEG-14 y D-22: queda un registro con la cuenta, su rol, la
        fecha y hora, la cuenta afectada y la acción de cambio de contraseña."""
        capataz = crear_capataz(**MAXIMILIANO)
        antes = timezone.now()

        cambiar_contrasena(capataz, NUEVA, contrasena_actual=CLAVE)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.usuario_id, capataz.pk)
        self.assertEqual(registro.rol, "capataz")
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.CAMBIO_CONTRASENA)
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": capataz.pk}])
        self.assertEqual(registro.detalle, {"era_temporal": False})
        self.assertTrue(antes <= registro.fecha_hora <= timezone.now())

    def test_post_d_la_auditoria_no_guarda_ninguna_contrasena(self):
        """USR-CMB-CTR postcondición d, SEG-02 y SEG-14: el registro no guarda ninguna contraseña,
        ni la temporal, ni la nueva, ni sus resúmenes."""
        capataz = crear_capataz(**MAXIMILIANO)
        temporal = dar_contrasena_temporal(capataz)
        resumen_temporal = capataz.password

        cambiar_contrasena(capataz, NUEVA)

        capataz.refresh_from_db()
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.detalle, {"era_temporal": True})
        contenido = json.dumps(model_to_dict(registro), default=str)
        for secreto in (temporal, NUEVA, resumen_temporal, capataz.password):
            self.assertNotIn(secreto, contenido)

    # ---- Requisitos de seguridad y decisiones ----

    def test_seg02_guarda_la_contrasena_como_resumen(self):
        """SEG-02: la contraseña nueva se guarda solo como resumen con sal, con el algoritmo por
        defecto de Django."""
        capataz = crear_capataz(**MAXIMILIANO)

        cambiar_contrasena(capataz, NUEVA, contrasena_actual=CLAVE)

        capataz.refresh_from_db()
        self.assertNotIn(NUEVA, capataz.password)
        hasher = identify_hasher(capataz.password)
        self.assertEqual(hasher.algorithm, get_hasher("default").algorithm)
        self.assertTrue(hasher.decode(capataz.password)["salt"])

    def test_d22_cambio_fallido_no_deja_registro(self):
        """D-22: el registro se escribe en la misma transacción que el cambio; un cambio rechazado
        no deja registro."""
        capataz = crear_capataz(**MAXIMILIANO)

        with self.assertRaises(ValidationError):
            cambiar_contrasena(capataz, NUEVA, contrasena_actual="otra-clave-999")

        self.assertFalse(RegistroAuditoria.objects.exists())


class UsrCmbCtrVistaTests(TestCase):
    """Flujo principal del cambio forzado por contraseña temporal (pantalla vForced, vista con el cliente)."""

    def entrar_con_temporal(self, email="capataz@infoponia.com", cliente=None):
        """Crea una cuenta con contraseña temporal, se identifica con ella y devuelve (cuenta, temporal)."""
        cliente = cliente or self.client
        capataz = crear_capataz(email=email, **MAXIMILIANO)
        temporal = dar_contrasena_temporal(capataz)
        cliente.post(reverse("core:iniciar_sesion"), {"username": email, "password": temporal})
        return capataz, temporal

    def elegir(self, nueva, repetida=None, cliente=None, **extra):
        """Envía el formulario de elegir contraseña y devuelve la respuesta."""
        cliente = cliente or self.client
        datos = {
            "contrasena_nueva": nueva,
            "contrasena_repetida": nueva if repetida is None else repetida,
            **extra,
        }
        return cliente.post(reverse("core:elegir_contrasena"), datos)

    def test_flujo_principal_reemplaza_la_temporal_y_llega_al_inicio(self):
        """USR-CMB-CTR flujo principal y USR-INI-SES postcondición b: con temporal, la persona ve la
        pantalla de elegir contraseña, la reemplaza por una propia, llega al inicio y después se
        identifica con la nueva. Queda el registro de auditoría."""
        capataz, temporal = self.entrar_con_temporal()

        pantalla = self.client.get(reverse("core:elegir_contrasena"))
        self.assertContains(pantalla, "Elegí tu contraseña")
        self.assertContains(pantalla, "Guardar y continuar")

        respuesta = self.elegir(NUEVA)

        self.assertRedirects(respuesta, reverse("core:inicio"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("core:inicio")), "Operás como")
        capataz.refresh_from_db()
        self.assertFalse(capataz.tiene_contrasena_temporal)
        self.assertTrue(capataz.check_password(NUEVA))
        self.assertEqual(
            RegistroAuditoria.objects.get().accion, RegistroAuditoria.Accion.CAMBIO_CONTRASENA
        )
        # La nueva contraseña sirve para identificarse en otro navegador; la temporal, no.
        otro = Client()
        for clave, entra in ((NUEVA, True), (temporal, False)):
            otro.post(
                reverse("core:iniciar_sesion"), {"username": capataz.email, "password": clave}
            )
            self.assertEqual("_auth_user_id" in otro.session, entra)
            otro.post(reverse("core:cerrar_sesion"))

    def test_post_c_cierra_las_demas_sesiones_y_mantiene_la_actual(self):
        """USR-CMB-CTR postcondición c y SEG-10: al cambiar la contraseña se cierran las demás
        sesiones abiertas con esa cuenta y la actual sigue."""
        capataz, temporal = self.entrar_con_temporal()
        otra_sesion = Client()
        otra_sesion.post(
            reverse("core:iniciar_sesion"), {"username": capataz.email, "password": temporal}
        )
        self.assertIn("_auth_user_id", otra_sesion.session)

        self.elegir(NUEVA)

        # La sesión desde la que se cambió sigue abierta...
        self.assertEqual(self.client.get(reverse("core:inicio")).status_code, 200)
        # ...y la otra ya no: vuelve a pedir identificarse.
        respuesta = otra_sesion.get(reverse("core:inicio"))
        self.assertRedirects(
            respuesta,
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:inicio')}",
            fetch_redirect_response=False,
        )

    def test_flujo_principal_pide_repetir_la_contrasena_nueva(self):
        """USR-CMB-CTR flujo principal (vForced): las dos contraseñas tienen que coincidir; si no, se
        muestra el error y no cambia nada."""
        capataz, temporal = self.entrar_con_temporal()

        respuesta = self.elegir(NUEVA, repetida=NUEVA + "x")

        self.assertContains(respuesta, "Las contraseñas no coinciden.")
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(temporal))
        self.assertTrue(capataz.tiene_contrasena_temporal)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_seg03_muestra_el_error_de_politica_en_el_formulario(self):
        """SEG-03 y vForced: si la contraseña nueva no cumple la política, el error que informa el
        servicio se muestra en el campo y la cuenta sigue con su temporal."""
        capataz, temporal = self.entrar_con_temporal()

        respuesta = self.elegir("abc123")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(
            respuesta.context["form"].has_error("contrasena_nueva", code="password_too_short")
        )
        self.assertContains(respuesta, 'class="err"')
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(temporal))

    def test_regla_3_solo_cambia_la_cuenta_con_sesion(self):
        """USR-CMB-CTR regla 3: cada persona cambia solo la contraseña de su propia cuenta. Aunque el
        pedido traiga el email o el id de otra cuenta, se cambia la de la sesión."""
        propia, _ = self.entrar_con_temporal(email="propia@infoponia.com")
        ajena = crear_capataz(email="ajena@infoponia.com", **MAXIMILIANO)
        temporal_ajena = dar_contrasena_temporal(ajena)

        self.elegir(NUEVA, email=ajena.email, id=ajena.pk, usuario=ajena.pk)

        propia.refresh_from_db()
        ajena.refresh_from_db()
        self.assertTrue(propia.check_password(NUEVA))
        self.assertTrue(ajena.check_password(temporal_ajena))
        self.assertTrue(ajena.tiene_contrasena_temporal)

    def test_flujo_principal_sin_temporal_redirige_al_inicio(self):
        """USR-CMB-CTR relación con USR-INI-SES: la pantalla es solo para cuentas con contraseña
        temporal; una cuenta común que la abre va al inicio (el cambio voluntario es otra pantalla)."""
        crear_capataz(**MAXIMILIANO)
        self.client.post(
            reverse("core:iniciar_sesion"),
            {"username": "capataz@infoponia.com", "password": CLAVE},
        )

        for respuesta in (
            self.client.get(reverse("core:elegir_contrasena")),
            self.elegir(NUEVA),
        ):
            self.assertRedirects(
                respuesta, reverse("core:inicio"), fetch_redirect_response=False
            )
        self.assertFalse(RegistroAuditoria.objects.exists())
