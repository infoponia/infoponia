# Pruebas de USR-INI-SES (Iniciar Sesión) y de los requisitos de seguridad que cita: SEG-01, SEG-04
# (tareas 02 y 03), SEG-05 a SEG-08 y SEG-13 (docs/casos_de_uso/usuarios.md), más D-24 (sin elementos
# del prototipo). No hay función de servicio para el login: las reglas las aplican el backend de
# autenticación, el formulario y el middleware de la contraseña temporal, por eso la clase se llama
# ...ReglasTests. Cada prueba arma sus propios datos y usa el cliente contra las URL, para que cada una
# falle o pase por separado. La migración del email (SEG-01, tarea 03) se prueba en MigracionEmailTests.

import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.contrasenas import generar_contrasena_temporal
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


def dar_contrasena_temporal(usuario, generada_hace=None):
    """Le asigna a la cuenta una contraseña temporal (SEG-04) y devuelve su texto plano.

    Con ``generada_hace`` se corre la fecha de generación hacia atrás, para probar el vencimiento.
    """
    temporal = usuario.asignar_contrasena_temporal()
    if generada_hace is not None:
        usuario.fecha_contrasena_temporal = timezone.now() - generada_hace
    usuario.save()
    return temporal


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
        """USR-INI-SES regla 1 y SEG-01: una cuenta dada de alta escribiendo el email con mayúsculas
        (que desde la tarea 03 se guarda en minúsculas) se identifica escribiéndolo en minúsculas."""
        capataz = crear_capataz(email="Ana.Perez@infoponia.com")

        self.iniciar_sesion("ana.perez@infoponia.com")

        self.assertEqual(self.id_en_sesion(), str(capataz.pk))

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

    def test_regla_4_con_temporal_solo_accede_a_elegir_contrasena(self):
        """USR-INI-SES regla 4, SEG-04 y D-18: con contraseña temporal, la persona se identifica pero
        cualquier otra pantalla (el inicio, el admin de Django) la lleva a elegir su contraseña."""
        capataz = crear_capataz()
        temporal = dar_contrasena_temporal(capataz)
        elegir = reverse("core:elegir_contrasena")

        respuesta = self.client.post(
            reverse("core:iniciar_sesion"),
            {"username": "capataz@infoponia.com", "password": temporal},
            follow=True,
        )

        self.assertEqual(self.id_en_sesion(), str(capataz.pk))
        self.assertRedirects(respuesta, elegir)
        # Otra pantalla cualquiera, que existe en todo entorno (el admin de Django no existe con DEBUG
        # apagado, como en el CI y en producción: SEG-18).
        for url in (reverse("core:inicio"), reverse("core:usuarios")):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), elegir, fetch_redirect_response=False
                )
        self.assertEqual(self.client.get(elegir).status_code, 200)

    def test_regla_4_con_temporal_puede_cerrar_sesion(self):
        """USR-INI-SES regla 4 y SEG-08: con contraseña temporal, cerrar sesión no está bloqueado."""
        capataz = crear_capataz()
        dar_contrasena_temporal(capataz)
        self.client.force_login(capataz)

        respuesta = self.client.post(reverse("core:cerrar_sesion"))

        self.assertRedirects(
            respuesta, reverse("core:iniciar_sesion"), fetch_redirect_response=False
        )
        self.assertIsNone(self.id_en_sesion())

    def test_regla_4_con_temporal_htmx_recibe_hx_redirect(self):
        """USR-INI-SES regla 4 y SEG-04: un pedido de HTMX con temporal recibe la cabecera
        HX-Redirect (y no un 302, que el navegador seguiría solo y HTMX metería la pantalla de elegir
        contraseña dentro del fragmento)."""
        capataz = crear_capataz()
        dar_contrasena_temporal(capataz)
        self.client.force_login(capataz)

        respuesta = self.client.get(reverse("core:inicio"), HTTP_HX_REQUEST="true")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["HX-Redirect"], reverse("core:elegir_contrasena"))

    def test_regla_4_temporal_vencida_no_identifica_y_muestra_mensaje_generico(self):
        """USR-INI-SES regla 4, SEG-04, SEG-06 y D-18: a los 7 días de generada, la contraseña
        temporal ya no sirve para identificarse, y la falla muestra el mensaje genérico."""
        for dias in (7, 30):
            with self.subTest(dias=dias):
                email = f"capataz{dias}@infoponia.com"
                capataz = crear_capataz(email=email)
                temporal = dar_contrasena_temporal(capataz, generada_hace=timedelta(days=dias))

                respuesta = self.iniciar_sesion(email, temporal)

                self.assertEqual(respuesta.status_code, 200)
                self.assertIsNone(self.id_en_sesion())
                self.assertEqual(
                    list(respuesta.context["form"].non_field_errors()), [MENSAJE_GENERICO]
                )

    # ---- Requisitos de seguridad ----

    def test_seg01_guarda_email_en_minusculas(self):
        """SEG-01 y D-19: el email se guarda en minúsculas y sin espacios, al crear la cuenta y al
        cambiarlo después."""
        capataz = crear_capataz(email="  Ana.Perez@InfoPonia.COM ")
        capataz.refresh_from_db()
        self.assertEqual(capataz.email, "ana.perez@infoponia.com")

        capataz.email = "Juan.Perez@InfoPonia.com"
        capataz.save()
        capataz.refresh_from_db()
        self.assertEqual(capataz.email, "juan.perez@infoponia.com")

    def test_seg01_rechaza_email_repetido_con_otras_mayusculas(self):
        """SEG-01 y D-19: el email es único sin distinguir mayúsculas. La base lo rechaza aunque se
        esquive la normalización del modelo (por ejemplo, con ``update()``)."""
        crear_capataz(email="ana@infoponia.com")
        otra = crear_capataz(email="otra@infoponia.com")

        with self.subTest("alta con el mismo email en mayúsculas"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                crear_capataz(email="ANA@infoponia.com")

        with self.subTest("update() que esquiva save()"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Usuario.objects.filter(pk=otra.pk).update(email="Ana@infoponia.com")

    def test_seg01_validacion_informa_email_repetido_con_otras_mayusculas(self):
        """SEG-01: la validación del modelo (la que usan los formularios) informa el email repetido
        con otras mayúsculas como error del campo ``email`` (código ``unique``) con un mensaje
        propio, en vez de dejarlo llegar a la base, y no informa ningún otro error. Se verifica por
        la clave del error, que es el email: ``clean()`` normaliza a minúsculas antes de comprobar
        la unicidad, así que es la unicidad del campo, y no la restricción
        ``email_unico_sin_mayusculas``, la que lo detecta (la restricción garantiza lo mismo en la
        base: ver ``test_seg01_rechaza_email_repetido_con_otras_mayusculas``)."""
        crear_capataz(email="ana@infoponia.com")
        nueva = Capataz(email="ANA@infoponia.com", first_name="Ana", last_name="Gómez")
        nueva.set_password(CLAVE)

        with self.assertRaises(ValidationError) as contexto:
            nueva.full_clean()

        errores = contexto.exception.error_dict
        self.assertEqual(list(errores), ["email"])
        self.assertEqual([e.code for e in errores["email"]], ["unique"])
        self.assertEqual(errores["email"][0].message, "Ya existe una cuenta con ese email.")

    def test_seg04_temporal_sirve_antes_de_los_7_dias(self):
        """SEG-04 y D-18: antes de cumplir 7 días, la contraseña temporal sirve para identificarse."""
        capataz = crear_capataz()
        temporal = dar_contrasena_temporal(
            capataz, generada_hace=timedelta(days=7) - timedelta(hours=1)
        )

        self.iniciar_sesion("capataz@infoponia.com", temporal)

        self.assertEqual(self.id_en_sesion(), str(capataz.pk))

    def test_seg04_genera_12_caracteres_sin_ambiguos(self):
        """SEG-04 y D-18: la temporal tiene 12 caracteres aleatorios, letras y dígitos, sin los
        ambiguos 0, O, 1, l, I."""
        generadas = [generar_contrasena_temporal() for _ in range(300)]

        for temporal in generadas:
            self.assertEqual(len(temporal), 12)
            self.assertTrue(temporal.isascii() and temporal.isalnum(), temporal)
            self.assertFalse(set(temporal) & set("0O1lI"), temporal)
        # Aleatorias: 300 generadas no se repiten.
        self.assertEqual(len(set(generadas)), len(generadas))

    def test_seg04_asignar_temporal_guarda_la_fecha_de_generacion(self):
        """SEG-04 y D-18: asignar una temporal la deja como contraseña de la cuenta y guarda la
        fecha y hora de generación; sin temporal, la fecha queda vacía."""
        capataz = crear_capataz()
        self.assertIsNone(capataz.fecha_contrasena_temporal)
        antes = timezone.now()

        temporal = capataz.asignar_contrasena_temporal()
        capataz.save()

        capataz.refresh_from_db()
        self.assertTrue(capataz.check_password(temporal))
        self.assertTrue(antes <= capataz.fecha_contrasena_temporal <= timezone.now())

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
    def test_seg13_pagina_403_enlaza_al_inicio_de_la_cuenta(self):
        """SEG-13: la página 403 trae un enlace «Volver al inicio» a la pantalla de inicio de la cuenta
        (la misma a la que se llega al iniciar sesión, que muestra el inicio según el rol)."""
        for cuenta in (crear_capataz(), crear_administrador()):
            with self.subTest(rol=cuenta.rol or "administrador"):
                self.client.force_login(cuenta)

                respuesta = self.client.get(reverse("prueba_solo_gerente"))

                self.assertContains(
                    respuesta,
                    f'<a class="btn btn-ghost" href="{reverse("core:inicio")}">Volver al inicio</a>',
                    status_code=403,
                    html=True,
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

    def test_post_a_administrador_entra_a_cuentas(self):
        """USR-INI-SES postcondición a, D-16 y D-30 (prototipo, enter()): al identificarse, el
        Administrador llega a «Cuentas», con el menú lateral «Administración» y su única entrada
        «Cuentas»; sin rol operativo, sin «Panel de control» ni «Módulos». El menú de cuenta dice
        «Administrador de cuentas»."""
        administrador = crear_administrador()

        respuesta = self.client.post(
            reverse("core:iniciar_sesion"),
            {"username": administrador.email, "password": CLAVE},
            follow=True,
        )

        self.assertRedirects(respuesta, reverse("core:usuarios"))
        self.assertContains(respuesta, '<aside class="side">')
        self.assertContains(respuesta, '<div class="side-label">Administración</div>')
        self.assertContains(respuesta, "<span>Cuentas</span>")
        self.assertNotContains(respuesta, "Panel de control")
        self.assertNotContains(respuesta, "Módulos")
        self.assertContains(respuesta, "Administrador de cuentas")

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


class MigracionEmailTests(TransactionTestCase):
    """SEG-01, D-19 y D-25: la migración que pasa los emails existentes a minúsculas.

    Es ``TransactionTestCase`` porque mueve el esquema de la base de prueba: vuelve a la migración
    anterior, carga cuentas con el modelo de ese momento (que todavía acepta emails que solo difieren
    en mayúsculas) y aplica la migración del email. ``tearDown`` deja la base en la última migración
    para las pruebas que siguen.
    """

    ANTERIOR = [("core", "0003_contrasena_temporal_y_auditoria")]
    MIGRACION_EMAIL = [("core", "0004_email_en_minusculas")]
    RESTRICCION = "email_unico_sin_mayusculas"

    def setUp(self):
        """Lleva la base a la migración anterior a la del email."""
        executor = MigrationExecutor(connection)
        executor.migrate(self.ANTERIOR)
        self.Usuario = executor.loader.project_state(self.ANTERIOR).apps.get_model(
            "core", "Usuario"
        )

    def tearDown(self):
        """Borra las cuentas cargadas (con duplicados la migración no avanzaría) y vuelve a la última
        migración."""
        self.Usuario.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def crear(self, email):
        """Crea una cuenta de Capataz con el modelo histórico y devuelve su id."""
        return self.Usuario.objects.create(
            email=email, password="x", first_name="Ana", last_name="Gómez", rol="capataz"
        ).pk

    def migrar_email(self):
        """Aplica la migración del email con un ejecutor nuevo (lee el estado actual de la base)."""
        executor = MigrationExecutor(connection)
        executor.migrate(self.MIGRACION_EMAIL)

    def restricciones(self):
        """Nombres de las restricciones e índices de la tabla de usuarios."""
        with connection.cursor() as cursor:
            return connection.introspection.get_constraints(cursor, "core_usuario").keys()

    def emails(self):
        """Emails guardados, ordenados por id."""
        return list(self.Usuario.objects.order_by("pk").values_list("email", flat=True))

    def test_seg01_migracion_falla_con_emails_duplicados_sin_cambiar_datos(self):
        """SEG-01 y D-25: si hay emails que solo difieren en mayúsculas, la migración falla con un
        mensaje que nombra el email y los id de las cuentas, sin borrar ni cambiar ningún dato."""
        id_1 = self.crear("Ana@infoponia.com")
        id_2 = self.crear("ana@InfoPonia.com ")
        self.crear("Pedro@infoponia.com")
        antes = self.emails()

        with self.assertRaises(RuntimeError) as contexto:
            self.migrar_email()

        mensaje = str(contexto.exception)
        self.assertIn("ana@infoponia.com", mensaje)
        self.assertIn(str(id_1), mensaje)
        self.assertIn(str(id_2), mensaje)
        self.assertEqual(self.emails(), antes)
        self.assertNotIn(self.RESTRICCION, self.restricciones())

    def test_seg01_migracion_pasa_los_emails_a_minusculas(self):
        """SEG-01 y D-19: sin duplicados, la migración pasa los emails existentes a minúsculas y sin
        espacios, y agrega la unicidad sin distinguir mayúsculas."""
        self.crear("Ana@InfoPonia.COM")
        self.crear(" pedro@infoponia.com ")
        self.crear("luis@infoponia.com")

        self.migrar_email()

        self.assertEqual(
            self.emails(),
            ["ana@infoponia.com", "pedro@infoponia.com", "luis@infoponia.com"],
        )
        self.assertIn(self.RESTRICCION, self.restricciones())


def _luminancia(color):
    """Luminancia relativa de un color ``#rrggbb`` o ``#rgb`` (definición de WCAG 2.x)."""
    if len(color) == 4:  # «#fff» es «#ffffff»
        color = "#" + "".join(c * 2 for c in color[1:])
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineales = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineales[0] + 0.7152 * lineales[1] + 0.0722 * lineales[2]


def _contraste(color_a, color_b):
    """Relación de contraste entre dos colores ``#rrggbb`` (de 1 a 21)."""
    claro, oscuro = sorted((_luminancia(color_a), _luminancia(color_b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


class MarcoVistaTests(TestCase):
    """Marco con sesión y estilos compartidos (D-29): avisos breves, botón secundario y versión de
    los archivos estáticos propios. Verifican lo que se puede ver en el HTML y en la hoja de estilos; el
    temporizador y la cruz de los avisos son JavaScript y se prueban a mano."""

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_d29_marco_trae_la_region_de_avisos_para_lectores_de_pantalla(self):
        """D-29: toda pantalla con sesión trae la región de avisos, vacía y con role="status", para que
        los lectores de pantalla anuncien cada aviso que se le agrega."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("core:inicio"))

        self.assertContains(
            respuesta,
            '<div class="avisos" id="avisos" role="status" aria-live="polite"></div>',
            html=True,
        )

    @override_settings(ROOT_URLCONF="core.tests.urls_prueba_acceso")
    def test_d29_mensajes_de_exito_y_de_error_traen_respaldo_sin_javascript(self):
        """D-29: los mensajes de Django (éxito y error) quedan en la página como aviso fijo con
        role="status" y su tipo; es el respaldo sin JavaScript, que con JavaScript pasa a ser un aviso breve."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("prueba_mensajes"))

        contenido = respuesta.content.decode()
        exito = re.search(
            r'<div class="alert alert-ok" role="status" data-aviso data-tipo="ok">.*?Todo salió bien\.',
            contenido,
            re.S,
        )
        error = re.search(
            r'<div class="alert alert-danger" role="status" data-aviso data-tipo="error">.*?Algo salió mal\.',
            contenido,
            re.S,
        )
        self.assertIsNotNone(exito, "falta el aviso de éxito")
        self.assertIsNotNone(error, "falta el aviso de error")

    def test_d29_los_errores_de_campo_no_son_avisos(self):
        """D-29: los errores debajo de los campos de un formulario no son avisos breves: siguen siendo un
        mensaje junto al campo (clase «err») y no llevan la marca de aviso."""
        self.client.force_login(crear_gerente())

        respuesta = self.client.post(reverse("core:usuario_nuevo"), {})

        self.assertContains(respuesta, 'class="err"')
        self.assertNotContains(respuesta, "data-aviso")

    def test_d29_estilos_y_scripts_propios_llevan_version(self):
        """D-29: la hoja de estilos y los scripts propios se piden con la fecha del archivo en la URL
        (``?v=``), con y sin sesión: un cambio en ellos llega al navegador sin forzar la recarga."""
        self.client.force_login(crear_gerente())
        con_sesion = self.client.get(reverse("core:inicio")).content.decode()
        self.client.logout()
        sin_sesion = self.client.get(reverse("core:iniciar_sesion")).content.decode()

        for pagina in (con_sesion, sin_sesion):
            for archivo in ("css/infoponia.css", "js/infoponia.js", "js/desplegable.js"):
                self.assertRegex(pagina, rf"core/{re.escape(archivo)}\?v=\d+")

    def test_d29_boton_secundario_cumple_contraste_wcag_aa(self):
        """D-29: el botón secundario (.btn-ghost) usa el verde primario en el borde y el texto, sobre fondo
        blanco, y cumple WCAG AA: texto de al menos 4,5:1 y borde de al menos 3:1, también en el hover."""
        css = (Path(settings.BASE_DIR) / "core/static/core/css/infoponia.css").read_text(encoding="utf-8")
        primario = re.search(r"--primary:(#[0-9a-fA-F]{6})", css).group(1)

        def propiedad(selector, nombre):
            regla = re.search(re.escape(selector) + r"\{([^}]*)\}", css).group(1)
            valor = re.search(rf"(?:^|;){nombre}:([^;]+)", regla).group(1).strip()
            return primario if valor == "var(--primary)" else valor

        self.assertEqual(propiedad(".btn-ghost", "color"), primario)
        self.assertEqual(propiedad(".btn-ghost", "border-color"), primario)
        self.assertEqual(propiedad(".btn-ghost", "background"), "#fff")
        for selector in (".btn-ghost", ".btn-ghost:hover"):
            with self.subTest(selector=selector):
                fondo = propiedad(selector, "background")
                fondo = "#ffffff" if fondo == "#fff" else fondo
                self.assertGreaterEqual(_contraste(propiedad(selector, "color"), fondo), 4.5)
                self.assertGreaterEqual(_contraste(propiedad(selector, "border-color"), fondo), 3.0)


def _css():
    """Texto de la hoja de estilos del sistema."""
    return (Path(settings.BASE_DIR) / "core/static/core/css/infoponia.css").read_text(encoding="utf-8")


def _regla(css, selector):
    """Contenido de la regla ``selector{...}`` de la hoja de estilos (la primera que coincide)."""
    coincidencia = re.search(r"(?<![\w-])" + re.escape(selector) + r"\{([^}]*)\}", css)
    assert coincidencia, f"no hay una regla {selector}"
    return coincidencia.group(1)


class AvisosYFocoEstilosTests(TestCase):
    """Presentación de los avisos breves y foco de los botones (D-29), verificados en la hoja de estilos:
    el comportamiento (10 segundos, cruz, salida animada) es JavaScript y se prueba a mano."""

    def test_d29_avisos_son_una_tarjeta_con_los_colores_del_sistema(self):
        """D-29: el aviso es una tarjeta (fondo --card, borde --border, radio de 6px) con una franja de 4px
        a la izquierda del color de su tipo: --status-ok para éxito y --status-danger para error. Texto en
        --foreground y cruz en --muted-foreground."""
        css = _css()
        toast = _regla(css, ".toast")

        self.assertIn("background:var(--card)", toast)
        self.assertIn("border:1px solid var(--border)", toast)
        self.assertIn("border-left:4px solid var(--color-aviso)", toast)
        self.assertIn("border-radius:6px", toast)
        self.assertIn("color:var(--foreground)", toast)
        self.assertIn("--color-aviso:var(--status-ok)", toast)
        self.assertIn("--color-aviso:var(--status-danger)", _regla(css, ".toast-error"))
        self.assertIn("color:var(--color-aviso)", _regla(css, ".toast-icono"))
        self.assertIn("background:var(--color-aviso)", _regla(css, ".toast-barra"))
        self.assertIn("height:3px", _regla(css, ".toast-barra"))
        self.assertIn("color:var(--muted-foreground)", _regla(css, ".toast-cerrar"))

    def test_d29_avisos_cumplen_contraste_wcag_aa_sobre_la_tarjeta(self):
        """D-29: el texto, la cruz y el ícono de cada tipo cumplen WCAG AA (4,5:1) sobre el fondo de la
        tarjeta, con los valores de los tokens de la hoja de estilos."""
        css = _css()

        def token(nombre):
            return re.search(rf"--{nombre}:(#[0-9a-fA-F]{{3,6}})", css).group(1)

        fondo = token("card")
        for nombre in ("foreground", "muted-foreground", "status-ok", "status-danger"):
            with self.subTest(token=nombre):
                self.assertGreaterEqual(_contraste(token(nombre), fondo), 4.5)

    def test_d29_avisos_van_arriba_a_la_derecha_debajo_del_encabezado(self):
        """D-29: los avisos se apilan hacia abajo arriba a la derecha, debajo del encabezado, con un ancho
        máximo de 380px; en menos de 760px ocupan el ancho con 12px de margen."""
        css = _css()
        avisos = _regla(css, ".avisos")

        self.assertIn("top:calc(var(--header-height) + 10px)", avisos)
        self.assertIn("right:16px", avisos)
        self.assertIn("width:380px", avisos)
        self.assertIn("flex-direction:column", avisos)
        movil = re.search(r"@media\(max-width:760px\)\{\.avisos,\.shell\.field \.avisos\{([^}]*)\}", css)
        self.assertIsNotNone(movil, "falta la regla de menos de 760px")
        for propiedad in ("left:12px", "right:12px", "width:auto"):
            self.assertIn(propiedad, movil.group(1))

    def test_d29_animaciones_de_entrada_salida_y_barra(self):
        """D-29: el aviso entra deslizándose desde la derecha con fundido (250ms, ease-out), sale
        desvaneciéndose hacia la derecha (200ms) y una barra de 3px se achica durante la duración del aviso."""
        css = _css()

        self.assertIn("animation:avisoEntra .25s ease-out", _regla(css, ".toast"))
        self.assertIn("animation:avisoSale .2s", _regla(css, ".toast-saliendo"))
        self.assertIn("animation:avisoBarra var(--duracion-aviso,10s) linear", _regla(css, ".toast-barra"))
        self.assertRegex(css, r"@keyframes avisoEntra\{from\{opacity:0;transform:translateX\(32px\)\}")
        self.assertRegex(css, r"@keyframes avisoSale\{[^@]*to\{opacity:0;transform:translateX\(32px\)\}")
        self.assertRegex(css, r"@keyframes avisoBarra\{from\{transform:scaleX\(1\)\}to\{transform:scaleX\(0\)\}")

    def test_d29_con_reducir_movimiento_los_avisos_no_se_animan(self):
        """D-29: con prefers-reduced-motion no hay desplazamiento ni barra animada: el aviso solo aparece
        y desaparece."""
        css = _css()

        reducido = re.search(r"@media\(prefers-reduced-motion:reduce\)\{(.*?)\}\s*(?:\n|$)", css, re.S).group(1)
        self.assertIn(".toast,.toast-saliendo{animation:none}", reducido)
        self.assertIn(".toast-barra{display:none}", reducido)

    def test_d29_todos_los_botones_muestran_el_foco_con_el_verde_primario(self):
        """D-29: al navegar con Tab, todo .btn muestra un borde de foco en el verde primario (:focus-visible),
        separado del botón para que se vea también en el primario y en el peligroso."""
        regla = _regla(_css(), ".btn:focus-visible")

        self.assertIn("outline:2px solid var(--primary)", regla)
        self.assertIn("outline-offset:2px", regla)

    def test_d29_botones_enlace_no_se_subrayan(self):
        """D-29: un botón que es un enlace (<a class="btn">) no se subraya, igual que uno que es <button>."""
        self.assertIn("text-decoration:none", _regla(_css(), ".btn"))
