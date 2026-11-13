# Pruebas de USR-CMB-CTR (Cambiar Contraseña) y de los requisitos que cita: SEG-02, SEG-03, SEG-10 y
# SEG-14 (docs/casos_de_uso/usuarios.md), más D-18 y D-22. Las de servicio llaman directo a
# core.servicios.cambiar_contrasena; las de la vista (integración) usan el cliente de prueba contra la
# pantalla «Elegí tu contraseña» (vForced) y el cambio voluntario de Mi perfil (vPerfil, tarea 06a). Cada
# prueba arma sus propios datos.

import json

from django.contrib.auth.hashers import get_hasher, identify_hasher
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Capataz, GrupoCuentas, RegistroAuditoria, Usuario, Vendedor
from core.servicios import cambiar_contrasena
from core.tests.fabricas import CLAVE, agrupar, crear_administrador, crear_capataz, crear_cuenta

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

    def test_regla_4_las_cuentas_vinculadas_se_mantienen(self):
        """USR-CMB-CTR regla 4 (tarea 06b, D-17): cambiar la propia contraseña no saca a la cuenta de su
        grupo de cuentas vinculadas ni toca a las demás. (Restablecerla, en cambio, sí la saca: SEG-11.)"""
        capataz = crear_capataz(**MAXIMILIANO)
        otra = crear_cuenta(Vendedor, email="vendedor@infoponia.com")
        grupo = agrupar(capataz, otra)

        cambiar_contrasena(capataz, NUEVA, contrasena_actual=CLAVE)

        self.assertEqual(Usuario.objects.get(pk=capataz.pk).grupo_id, grupo.pk)
        self.assertEqual(Usuario.objects.get(pk=otra.pk).grupo_id, grupo.pk)
        self.assertEqual(GrupoCuentas.objects.count(), 1)

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
    """Flujo principal de las dos pantallas del caso de uso, con el cliente: el cambio forzado por contraseña
    temporal (vForced) y el cambio voluntario desde Mi perfil (vPerfil, tarea 06a)."""

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

    # ---- Cambio voluntario desde Mi perfil (USR-CMB-CTR por sí mismo, USR-GST-PRF regla 3; tarea 06a) ----

    def entrar_sin_temporal(self, cuenta=None, cliente=None):
        """Abre una sesión con una cuenta sin contraseña temporal (un Capataz, si no se indica) y la devuelve."""
        cliente = cliente or self.client
        cuenta = cuenta or crear_capataz(**MAXIMILIANO)
        cliente.post(reverse("core:iniciar_sesion"), {"username": cuenta.email, "password": CLAVE})
        return cuenta

    def cambiar(self, actual=CLAVE, nueva=NUEVA, repetida=None, cliente=None, **extra):
        """Envía el formulario «Cambiar contraseña» de Mi perfil y devuelve la respuesta."""
        cliente = cliente or self.client
        datos = {
            "contrasena_actual": actual,
            "contrasena_nueva": nueva,
            "contrasena_repetida": nueva if repetida is None else repetida,
            **extra,
        }
        return cliente.post(reverse("core:cambiar_mi_contrasena"), datos)

    def test_flujo_principal_voluntario_cambia_la_contrasena_y_vuelve_a_mi_perfil(self):
        """USR-CMB-CTR flujo principal (por sí mismo, desde USR-GST-PRF, vPerfil): con la contraseña actual,
        la persona elige una nueva, vuelve a Mi perfil con el aviso (D-29) y queda el registro de auditoría
        (postcondición d)."""
        capataz = self.entrar_sin_temporal()

        respuesta = self.cambiar()

        self.assertRedirects(respuesta, reverse("core:mi_perfil"), fetch_redirect_response=False)
        pantalla = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(pantalla, "Contraseña actualizada.")
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(NUEVA))
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.CAMBIO_CONTRASENA)
        self.assertEqual(registro.detalle, {"era_temporal": False})

    def test_regla_1_voluntario_pide_la_contrasena_actual(self):
        """USR-CMB-CTR regla 1: sin la contraseña actual no se cambia nada y el campo muestra el error."""
        capataz = self.entrar_sin_temporal()

        respuesta = self.cambiar(actual="")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ingresá tu contraseña actual.")
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_1_voluntario_rechaza_contrasena_actual_incorrecta(self):
        """USR-CMB-CTR regla 1: una contraseña actual incorrecta no cambia nada; el error que informa el
        servicio queda en el campo de la contraseña actual."""
        capataz = self.entrar_sin_temporal()

        respuesta = self.cambiar(actual="otra-clave-cualquiera")

        self.assertTrue(
            respuesta.context["form"].has_error("contrasena_actual", code="incorrecta")
        )
        self.assertContains(respuesta, "La contraseña actual no es correcta.")
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_voluntario_rechaza_contrasena_igual_a_la_actual(self):
        """USR-CMB-CTR regla 2 y SEG-03: la contraseña nueva es distinta de la actual."""
        capataz = self.entrar_sin_temporal()

        respuesta = self.cambiar(nueva=CLAVE)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].has_error("contrasena_nueva"))
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_flujo_principal_voluntario_pide_repetir_la_contrasena_nueva(self):
        """USR-CMB-CTR flujo principal (vPerfil): las dos contraseñas nuevas tienen que coincidir; si no, se
        muestra el error y no cambia nada. Las contraseñas escritas no vuelven en la respuesta."""
        capataz = self.entrar_sin_temporal()

        respuesta = self.cambiar(repetida=NUEVA + "x")

        self.assertContains(respuesta, "Las contraseñas no coinciden.")
        self.assertNotContains(respuesta, NUEVA)
        self.assertNotContains(respuesta, CLAVE)
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_post_c_voluntario_cierra_las_demas_sesiones_y_mantiene_la_actual(self):
        """USR-CMB-CTR postcondición c y SEG-10: el cambio voluntario cierra las demás sesiones abiertas con
        esa cuenta y la actual sigue."""
        capataz = self.entrar_sin_temporal()
        otra_sesion = Client()
        self.entrar_sin_temporal(cuenta=capataz, cliente=otra_sesion)

        self.cambiar()

        self.assertEqual(self.client.get(reverse("core:mi_perfil")).status_code, 200)
        respuesta = otra_sesion.get(reverse("core:mi_perfil"))
        self.assertRedirects(
            respuesta,
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:mi_perfil')}",
            fetch_redirect_response=False,
        )

    def test_regla_3_voluntario_cambia_solo_la_cuenta_con_sesion(self):
        """USR-CMB-CTR regla 3: aunque el pedido traiga el email o el id de otra cuenta, se cambia la
        contraseña de la cuenta con sesión."""
        propia = self.entrar_sin_temporal(cuenta=crear_capataz(email="propia@infoponia.com"))
        ajena = crear_capataz(email="ajena@infoponia.com")

        self.cambiar(email=ajena.email, id=ajena.pk, usuario=ajena.pk)

        propia.refresh_from_db()
        ajena.refresh_from_db()
        self.assertTrue(propia.check_password(NUEVA))
        self.assertTrue(ajena.check_password(CLAVE))

    def test_seg04_con_temporal_el_cambio_voluntario_redirige_a_elegir_contrasena(self):
        """SEG-04 y regla 4 de USR-INI-SES: con contraseña temporal no se usa el cambio voluntario (que pide
        la actual): el middleware lleva a «Elegí tu contraseña» y no cambia nada."""
        capataz, temporal = self.entrar_con_temporal()

        respuesta = self.cambiar(actual=temporal)

        self.assertRedirects(
            respuesta, reverse("core:elegir_contrasena"), fetch_redirect_response=False
        )
        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(temporal))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_flujo_principal_voluntario_get_redirige_a_mi_perfil(self):
        """USR-CMB-CTR (vPerfil): el formulario está en Mi perfil; abrir su dirección con GET no cambia nada
        y lleva a Mi perfil."""
        self.entrar_sin_temporal()

        respuesta = self.client.get(reverse("core:cambiar_mi_contrasena"))

        self.assertRedirects(respuesta, reverse("core:mi_perfil"), fetch_redirect_response=False)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d30_el_administrador_cambia_su_contrasena_desde_mi_perfil(self):
        """D-16 y D-30: el Administrador cambia su propia contraseña como cualquier persona (USR-CMB-CTR),
        ya no solo por consola."""
        administrador = self.entrar_sin_temporal(cuenta=crear_administrador())

        respuesta = self.cambiar()

        self.assertRedirects(respuesta, reverse("core:mi_perfil"), fetch_redirect_response=False)
        administrador.refresh_from_db()
        self.assertTrue(administrador.check_password(NUEVA))
        self.assertEqual(RegistroAuditoria.objects.get().rol, "administrador")
