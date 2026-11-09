# Pruebas de USR-INI-SES (Iniciar Sesión) y de los requisitos de seguridad que cita la tarea 02:
# SEG-01, SEG-05 a SEG-08 y SEG-13 (docs/casos_de_uso/usuarios.md), más D-24 (sin elementos del
# prototipo). No hay función de servicio para el login: las reglas las aplican el backend de
# autenticación y el formulario, por eso la clase se llama ...ReglasTests. Cada prueba arma sus propios
# datos y usa el cliente contra las URL, para que cada una falle o pase por separado.

from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Capataz, Gerente, Usuario

CLAVE = "clave-segura-123"

# Texto exacto del prototipo (vLogin) para cualquier falla de identificación (SEG-06).
MENSAJE_GENERICO = (
    "No pudimos iniciar sesión. Revisá el email y la contraseña, y volvé a intentarlo."
)


def crear_capataz(email="capataz@infoponia.com", **extra):
    """Crea un Capataz activo con la contraseña de prueba."""
    return Capataz.objects.create_user(
        email=email, password=CLAVE, first_name="Juan", last_name="Pérez", **extra
    )


def crear_gerente(email="gerente@infoponia.com"):
    """Crea el Gerente activo con la contraseña de prueba."""
    return Gerente.objects.create_user(
        email=email, password=CLAVE, first_name="Flora", last_name="Mora"
    )


def crear_administrador(email="admin@infoponia.com"):
    """Crea un Administrador (superusuario sin rol, D-10) con la contraseña de prueba."""
    return Usuario.objects.create_superuser(
        email=email, password=CLAVE, first_name="Nora", last_name="Correa"
    )


class UsrIniSesReglasTests(TestCase):
    """Reglas de USR-INI-SES y requisitos SEG-01, SEG-05 a SEG-08 y SEG-13."""

    def iniciar_sesion(self, email, clave=CLAVE):
        """Envía el formulario de inicio de sesión y devuelve la respuesta."""
        return self.client.post(
            reverse("core:iniciar_sesion"), {"username": email, "password": clave}
        )

    def id_en_sesion(self):
        """Devuelve el id de la cuenta identificada en la sesión, o None."""
        return self.client.session.get("_auth_user_id")

    # ---- Reglas del caso de uso ----

    def test_regla_1_identifica_con_email_y_contrasena(self):
        """USR-INI-SES regla 1 y SEG-01: la persona se identifica con el email y la contraseña."""
        capataz = crear_capataz()

        respuesta = self.iniciar_sesion("capataz@infoponia.com")

        self.assertRedirects(
            respuesta, reverse("core:inicio"), fetch_redirect_response=False
        )
        self.assertEqual(self.id_en_sesion(), str(capataz.pk))

    def test_regla_1_compara_email_sin_distinguir_mayusculas(self):
        """USR-INI-SES regla 1, SEG-01 y D-19: el email se compara sin distinguir mayúsculas."""
        capataz = crear_capataz(email="ana@infoponia.com")

        self.iniciar_sesion("  Ana@InfoPonia.COM ")

        self.assertEqual(self.id_en_sesion(), str(capataz.pk))

    def test_regla_1_email_guardado_con_mayusculas_se_identifica(self):
        """USR-INI-SES regla 1 y SEG-01: una cuenta guardada con mayúsculas (antes de la tarea 03,
        que normaliza al guardar) se identifica escribiendo el email en minúsculas."""
        capataz = crear_capataz(email="Ana.Perez@infoponia.com")

        self.iniciar_sesion("ana.perez@infoponia.com")

        self.assertEqual(self.id_en_sesion(), str(capataz.pk))

    def test_regla_1_dos_cuentas_que_difieren_en_mayusculas_no_se_identifican(self):
        """USR-INI-SES regla 1, SEG-01 y SEG-06: si dos cuentas activas solo difieren en las
        mayúsculas del email (posible hasta que la tarea 03 agregue la unicidad sin distinguir
        mayúsculas), el email es ambiguo: no se identifica ninguna y se muestra el mensaje genérico."""
        crear_capataz(email="Ana@infoponia.com")
        crear_capataz(email="ana@infoponia.com")

        for email in ("Ana@infoponia.com", "ana@infoponia.com"):
            with self.subTest(email=email):
                respuesta = self.iniciar_sesion(email)

                self.assertEqual(respuesta.status_code, 200)
                self.assertIsNone(self.id_en_sesion())
                self.assertEqual(
                    list(respuesta.context["form"].non_field_errors()), [MENSAJE_GENERICO]
                )

    def test_regla_2_cuenta_inactiva_no_se_identifica(self):
        """USR-INI-SES regla 2: solo se identifican las cuentas activas."""
        crear_capataz(is_active=False)

        respuesta = self.iniciar_sesion("capataz@infoponia.com")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(self.id_en_sesion())

    def test_regla_3_toda_falla_muestra_el_mismo_mensaje_generico(self):
        """USR-INI-SES regla 3 y SEG-06: email inexistente, contraseña incorrecta y cuenta inactiva
        muestran el mismo mensaje, que no revela qué dato falló."""
        crear_capataz(email="activa@infoponia.com")
        crear_capataz(email="baja@infoponia.com", is_active=False)
        casos = [
            ("email inexistente", "nadie@infoponia.com", CLAVE),
            ("contraseña incorrecta", "activa@infoponia.com", "otra-clave-999"),
            ("cuenta inactiva", "baja@infoponia.com", CLAVE),
        ]

        for causa, email, clave in casos:
            with self.subTest(causa=causa):
                respuesta = self.iniciar_sesion(email, clave)

                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(
                    list(respuesta.context["form"].non_field_errors()), [MENSAJE_GENERICO]
                )
                self.assertContains(respuesta, MENSAJE_GENERICO, count=1)
                self.assertNotContains(respuesta, "inactiv")

    # ---- Requisitos de seguridad ----

    def test_seg05_no_bloquea_la_cuenta_tras_intentos_fallidos(self):
        """SEG-05: no hay límite de intentos ni bloqueo; tras 10 fallas, la clave correcta entra."""
        capataz = crear_capataz()
        for _ in range(10):
            self.iniciar_sesion("capataz@infoponia.com", "clave-equivocada")

        self.iniciar_sesion("capataz@infoponia.com")

        self.assertEqual(self.id_en_sesion(), str(capataz.pk))

    def test_seg07_la_sesion_vence_al_cerrar_el_navegador(self):
        """SEG-07 y D-19: la sesión dura mientras el navegador esté abierto (cookie sin vencimiento)."""
        crear_capataz()

        self.iniciar_sesion("capataz@infoponia.com")

        self.assertTrue(self.client.session.get_expire_at_browser_close())
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie["expires"], "")
        self.assertEqual(cookie["max-age"], "")

    def test_seg08_cerrar_sesion_invalida_la_sesion_en_el_servidor(self):
        """SEG-08: cerrar sesión la invalida en el servidor, no solo en el navegador."""
        crear_capataz()
        self.iniciar_sesion("capataz@infoponia.com")
        clave_sesion = self.client.session.session_key

        self.client.post(reverse("core:cerrar_sesion"))

        self.assertFalse(Session.objects.filter(session_key=clave_sesion).exists())
        respuesta = self.client.get(reverse("core:inicio"))
        self.assertEqual(respuesta.status_code, 302)

    def test_seg08_cerrar_sesion_no_acepta_get(self):
        """SEG-08: cerrar sesión solo por POST, para que un enlace de otro sitio no cierre la sesión."""
        crear_capataz()
        self.iniciar_sesion("capataz@infoponia.com")

        respuesta = self.client.get(reverse("core:cerrar_sesion"))

        self.assertEqual(respuesta.status_code, 405)
        self.assertIsNotNone(self.id_en_sesion())

    def test_seg13_sin_sesion_redirige_a_iniciar_sesion(self):
        """SEG-13: sin sesión, las pantallas redirigen al inicio de sesión."""
        respuesta = self.client.get(reverse("core:inicio"))

        self.assertRedirects(
            respuesta,
            f"{reverse('core:iniciar_sesion')}?next={reverse('core:inicio')}",
            fetch_redirect_response=False,
        )

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_seg13_rol_no_autorizado_recibe_403_con_mensaje(self):
        """SEG-13: si la pantalla no corresponde al rol, 403 con un mensaje que nombra el rol."""
        self.client.force_login(crear_capataz())

        respuesta = self.client.get(reverse("prueba_solo_gerente"))

        self.assertContains(
            respuesta,
            "Tu cuenta de Capataz no tiene acceso a esta pantalla.",
            status_code=403,
        )

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_seg13_rol_autorizado_accede(self):
        """SEG-13: el rol al que corresponde la pantalla accede."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("prueba_solo_gerente"))

        self.assertContains(respuesta, "Pantalla del Gerente")

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_seg13_administrador_no_accede_a_pantalla_de_un_rol(self):
        """SEG-13, D-10 y D-16: el Administrador no tiene rol de negocio y no entra a sus pantallas."""
        self.client.force_login(crear_administrador())

        respuesta = self.client.get(reverse("prueba_solo_gerente"))

        self.assertContains(
            respuesta,
            "Tu cuenta de Administrador no tiene acceso a esta pantalla.",
            status_code=403,
        )

    @override_settings(WHITENOISE_USE_FINDERS=True, WHITENOISE_AUTOREFRESH=True)
    def test_seg13_estaticos_se_sirven_sin_sesion(self):
        """SEG-13 (exención necesaria): los estilos se sirven sin sesión; si no, la pantalla de
        inicio de sesión se vería sin estilos."""
        respuesta = self.client.get("/" + settings.STATIC_URL.strip("/") + "/core/css/infoponia.css")

        # 200 (y no 302 al login) prueba que LoginRequiredMiddleware no intercepta los estáticos.
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta["Content-Type"].startswith("text/css"))

    # ---- Decisiones ----

    def test_d24_inicio_de_sesion_sin_elementos_del_prototipo(self):
        """D-24 y usuarios.md, «Elementos del prototipo que no van en el sistema»: el inicio de
        sesión solo tiene el formulario de email y contraseña."""
        respuesta = self.client.get(reverse("core:iniciar_sesion"))

        self.assertContains(respuesta, 'name="username"')
        self.assertContains(respuesta, 'name="password"')
        for texto in (
            "Solo prototipo",
            "cuentas de prueba",
            "Simular",
            'data-act="fill"',
            'class="proto"',
        ):
            with self.subTest(texto=texto):
                self.assertNotContains(respuesta, texto)


class UsrIniSesVistaTests(TestCase):
    """Flujo principal de USR-INI-SES y lo que cada rol ve en su inicio (vista con el cliente de prueba)."""

    def entrar(self, usuario):
        """Se identifica con el formulario real y devuelve la página de inicio."""
        self.client.post(
            reverse("core:iniciar_sesion"), {"username": usuario.email, "password": CLAVE}
        )
        return self.client.get(reverse("core:inicio"))

    def test_flujo_principal_inicia_sesion_y_llega_al_inicio(self):
        """USR-INI-SES flujo principal y postcondición a: tras identificarse, el inicio indica el
        rol y la cuenta con la que se opera."""
        capataz = crear_capataz(email="juan@infoponia.com")

        respuesta = self.client.post(
            reverse("core:iniciar_sesion"),
            {"username": "juan@infoponia.com", "password": CLAVE},
            follow=True,
        )

        self.assertRedirects(respuesta, reverse("core:inicio"))
        self.assertContains(respuesta, "Operás como")
        self.assertContains(respuesta, "<b style=\"color:var(--foreground)\">Capataz</b>")
        self.assertContains(respuesta, capataz.email)

    def test_flujo_principal_vuelve_a_la_pantalla_pedida(self):
        """USR-INI-SES flujo principal y SEG-13: si la persona venía de otra pantalla, vuelve a ella."""
        crear_gerente()

        respuesta = self.client.post(
            reverse("core:iniciar_sesion") + "?next=/pantalla-pedida/",
            {"username": "gerente@infoponia.com", "password": CLAVE, "next": "/pantalla-pedida/"},
        )

        self.assertRedirects(respuesta, "/pantalla-pedida/", fetch_redirect_response=False)

    def test_post_a_gerente_ve_menu_lateral_con_panel_de_control(self):
        """USR-INI-SES postcondición a: el Gerente opera con los permisos de su rol (menú lateral)."""
        respuesta = self.entrar(crear_gerente())

        self.assertContains(respuesta, '<aside class="side">')
        self.assertContains(respuesta, "Panel de control")
        self.assertContains(respuesta, "Operás como Gerente")

    def test_post_a_capataz_ve_marco_de_campo_sin_menu_lateral(self):
        """USR-INI-SES postcondición a y prototipo (FIELD): el Capataz usa el marco de celular."""
        respuesta = self.entrar(crear_capataz())

        self.assertContains(respuesta, 'class="shell field"')
        self.assertNotContains(respuesta, '<aside class="side">')
        self.assertNotContains(respuesta, "sincronizado")

    def test_post_a_administrador_opera_sin_rol_operativo(self):
        """USR-INI-SES objetivo y D-16: el Administrador opera con la administración de cuentas,
        sin rol operativo ni menú de módulos."""
        respuesta = self.entrar(crear_administrador())

        self.assertContains(respuesta, "Administrador de cuentas")
        self.assertNotContains(respuesta, '<aside class="side">')
        self.assertContains(respuesta, "Operás como")

    def test_seg08_el_menu_de_cuenta_ofrece_cerrar_sesion_por_post(self):
        """SEG-08: el menú de cuenta tiene «Cerrar sesión» como formulario POST con CSRF."""
        respuesta = self.entrar(crear_gerente())

        self.assertContains(respuesta, f'action="{reverse("core:cerrar_sesion")}"')
        self.assertContains(respuesta, "Cerrar sesión")
        self.assertContains(respuesta, "csrfmiddlewaretoken")

    def test_d24_htmx_y_fuentes_se_sirven_desde_el_repo(self):
        """D-24: HTMX y las fuentes salen del repo, sin CDN ni servidores externos."""
        for url in (reverse("core:iniciar_sesion"),):
            with self.subTest(url=url):
                respuesta = self.client.get(url)

                self.assertContains(respuesta, "/static/core/vendor/htmx-2.0.11.min.js")
                for externo in ("unpkg", "cdn", "fonts.googleapis", "https://", "http://"):
                    self.assertNotContains(respuesta, externo)

    @override_settings(NOMBRE_ORGANIZACION="Vivero Los Álamos")
    def test_d24_el_marco_muestra_el_nombre_de_organizacion_configurado(self):
        """D-24 («Jardín Botánico» es dato del prototipo): el nombre del marco sale de la
        configuración NOMBRE_ORGANIZACION, con y sin sesión."""
        sin_sesion = self.client.get(reverse("core:iniciar_sesion"))
        con_sesion = self.entrar(crear_gerente())

        for respuesta in (sin_sesion, con_sesion):
            self.assertContains(respuesta, "Vivero Los Álamos")
            self.assertNotContains(respuesta, "Jardín Botánico")
