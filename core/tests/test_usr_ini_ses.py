# Pruebas de USR-INI-SES (Iniciar Sesión) y de los requisitos de seguridad que cita: SEG-01, SEG-04
# (tareas 02 y 03), SEG-05 a SEG-08 y SEG-13 (docs/casos_de_uso/usuarios.md), más D-24 (sin elementos
# del prototipo). No hay función de servicio para el login: las reglas las aplican el backend de
# autenticación, el formulario y el middleware de la contraseña temporal, por eso la clase se llama
# ...ReglasTests. Cada prueba arma sus propios datos y usa el cliente contra las URL, para que cada una
# falle o pase por separado. La migración del email (SEG-01, tarea 03) se prueba en MigracionEmailTests.

import copy
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from core import extensiones
from core.acceso import ADMINISTRADOR, pantalla_accesible_para, rol_requerido
from core.contrasenas import generar_contrasena_temporal
from core.models import Capataz, Usuario
from core.tests.fabricas import (
    CLAVE,
    agrupar,
    crear_administrador,
    crear_capataz,
    crear_gerente,
    dar_contrasena_temporal,
)


# Texto exacto del prototipo (vLogin) para cualquier falla de identificación (SEG-06).
MENSAJE_GENERICO = (
    "No pudimos iniciar sesión. Revisá el email y la contraseña, y volvé a intentarlo."
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

    def test_regla_5_opera_con_la_cuenta_indicada_aunque_tenga_vinculadas(self):
        """USR-INI-SES regla 5 (tarea 06b, D-17): se opera con la cuenta indicada al identificarse, aunque
        tenga cuentas vinculadas; el vínculo no cambia con cuál cuenta se entra."""
        capataz = crear_capataz()
        gerente = crear_gerente()
        agrupar(capataz, gerente)

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


class PantallaAccesibleTests(TestCase):
    """``pantalla_accesible_para`` y las anotaciones de ``rol_requerido`` (SEG-13, D-29): la decisión de a dónde
    volver después de iniciar sesión se toma sin ejecutar la pantalla pedida."""

    def test_seg13_los_roles_de_rol_requerido_sobreviven_a_otros_decoradores(self):
        """SEG-13 (D-29): ``rol_requerido`` anota sus roles en la vista y la anotación sigue visible cuando otro
        decorador (``never_cache``, ``vary_on_headers``) la envuelve por fuera."""

        @never_cache
        @vary_on_headers("HX-Request")
        @rol_requerido(Usuario.Rol.GERENTE)
        def vista(request):
            return None

        self.assertEqual(vista.roles_permitidos, (Usuario.Rol.GERENTE,))

    def test_seg13_las_pantallas_de_usuarios_declaran_gerente_y_administrador(self):
        """SEG-13 (D-29): la lista de usuarios, que protege ``rol_requerido``, declara los roles que el inicio de
        sesión consulta."""
        vista = resolve(reverse("core:usuarios")).func

        self.assertEqual(set(vista.roles_permitidos), {Usuario.Rol.GERENTE, ADMINISTRADOR})

    def test_seg13_pantalla_inexistente_o_sin_roles_se_considera_accesible(self):
        """SEG-13 y USR-INI-SES (D-29): una URL que no resuelve, o una pantalla que no declara roles (Mi perfil),
        no se rechaza: se conserva el comportamiento de siempre y las decide la propia pantalla."""
        capataz = crear_capataz()

        self.assertTrue(pantalla_accesible_para(capataz, "/pantalla-pedida/"))
        self.assertTrue(pantalla_accesible_para(capataz, reverse("core:mi_perfil")))

    def test_seg13_rol_distinto_de_los_declarados_no_es_accesible(self):
        """SEG-13 (D-29): una cuenta cuyo rol no figura en la pantalla pedida no puede abrirla."""
        capataz = crear_capataz()

        self.assertFalse(pantalla_accesible_para(capataz, reverse("core:usuarios")))
        self.assertFalse(pantalla_accesible_para(capataz, reverse("core:usuarios") + "?rol=capataz"))
        self.assertTrue(pantalla_accesible_para(crear_gerente(), reverse("core:usuarios")))


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

    def iniciar_pidiendo(self, cuenta, destino):
        """Envía el formulario de inicio de sesión como llega cuando se pidió ``destino`` con la sesión cerrada."""
        return self.client.post(
            reverse("core:iniciar_sesion") + "?next=" + destino,
            {"username": cuenta.email, "password": CLAVE, "next": destino},
        )

    def test_seg13_next_de_pantalla_de_otro_rol_lleva_al_inicio_de_la_cuenta(self):
        """SEG-13 y USR-INI-SES flujo principal (D-29): si la pantalla pedida no es accesible para la cuenta que
        acaba de entrar (otra persona en el mismo navegador), va a su inicio y no al 403."""
        capataz = crear_capataz()

        respuesta = self.iniciar_pidiendo(capataz, reverse("core:usuarios"))

        # assertRedirects sigue la redirección y exige un 200: el inicio, no la página 403.
        self.assertRedirects(respuesta, reverse("core:inicio"))

    def test_seg13_next_de_pantalla_permitida_se_respeta(self):
        """SEG-13 y USR-INI-SES flujo principal (D-29): si la cuenta sí puede abrir la pantalla pedida, vuelve a ella."""
        for crear in (crear_gerente, crear_administrador):
            with self.subTest(cuenta=crear.__name__):
                respuesta = self.iniciar_pidiendo(crear(), reverse("core:usuarios"))

                self.assertRedirects(respuesta, reverse("core:usuarios"))
                self.client.logout()

    def test_seg13_next_con_consulta_se_evalua_por_la_ruta(self):
        """SEG-13 (D-29): la consulta de la URL pedida (``?rol=capataz``) no cambia la decisión: se evalúa la ruta."""
        capataz = crear_capataz()

        respuesta = self.iniciar_pidiendo(capataz, reverse("core:usuarios") + "?rol=capataz")

        self.assertRedirects(respuesta, reverse("core:inicio"))

    def test_seg13_next_de_otro_sitio_sigue_ignorado(self):
        """SEG-13 (D-29): un ``next`` hacia otro sitio sigue descartándose y la cuenta va a su inicio."""
        gerente = crear_gerente()

        respuesta = self.iniciar_pidiendo(gerente, "//ejemplo.com/")

        self.assertRedirects(respuesta, reverse("core:inicio"))

    def test_seg13_con_sesion_abierta_el_inicio_de_sesion_con_next_inaccesible_lleva_al_inicio(self):
        """SEG-13 (D-29): quien abre el inicio de sesión con la sesión ya abierta y un ``next`` que su cuenta no
        puede abrir va a su inicio (``redirect_authenticated_user`` pasa por la misma decisión)."""
        self.client.force_login(crear_capataz())

        respuesta = self.client.get(reverse("core:iniciar_sesion") + "?next=" + reverse("core:usuarios"))

        self.assertRedirects(respuesta, reverse("core:inicio"))

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


# ---- MAE-02b (D-43): secciones del Inicio registradas por las apps de negocio (regla 5 de PROD-CNS-INV) ----


def plantillas_con(**fuentes):
    """``override_settings`` que suma plantillas en memoria (``nombre.html=«texto»``) a las de las apps, para probar el
    Inicio con una sección falsa sin crear archivos."""
    configuracion = copy.deepcopy(settings.TEMPLATES)
    configuracion[0].pop("APP_DIRS", None)
    configuracion[0]["OPTIONS"]["loaders"] = [
        ("django.template.loaders.locmem.Loader", fuentes),
        "django.template.loaders.app_directories.Loader",
    ]
    return override_settings(TEMPLATES=configuracion)


class InicioExtensionTests(TestCase):
    """D-43, regla A4 de D-37: ``core/extensiones.py`` deja que las apps de negocio sumen secciones al Inicio. Con
    registrantes falsos: ``core`` no conoce ninguna app de negocio."""

    def test_d43_secciones_de_inicio_omite_las_que_devuelven_none(self):
        """D-43: ``secciones_de_inicio`` llama a cada registrante con el usuario, junta las secciones que devuelven y
        omite las ``None``, en el orden de registro."""
        gerente = crear_gerente()
        primera = extensiones.SeccionDeInicio("una.html", {"clave": 1})
        segunda = extensiones.SeccionDeInicio("otra.html", {"clave": 2})
        recibidos = []

        def con_registro(usuario):
            recibidos.append(usuario.pk)
            return primera

        with mock.patch.object(
            extensiones,
            "_SECCIONES_DE_INICIO",
            [lambda usuario: None, con_registro, lambda usuario: segunda],
        ):
            secciones = extensiones.secciones_de_inicio(gerente)

        self.assertEqual(secciones, [primera, segunda])
        self.assertEqual(recibidos, [gerente.pk])

    def test_d43_registrar_dos_veces_la_misma_seccion_no_la_repite(self):
        """D-43: ``registrar_seccion_de_inicio`` es idempotente (``ready()`` puede correr más de una vez)."""

        def seccion(usuario):
            return None

        with mock.patch.object(extensiones, "_SECCIONES_DE_INICIO", []):
            extensiones.registrar_seccion_de_inicio(seccion)
            extensiones.registrar_seccion_de_inicio(seccion)
            registradas = list(extensiones._SECCIONES_DE_INICIO)

        self.assertEqual(registradas, [seccion])

    def test_d43_el_inicio_incluye_las_secciones_registradas(self):
        """D-43 y regla 5 de PROD-CNS-INV: el Inicio incluye la plantilla de cada sección con su contexto. Sin
        registrantes no muestra nada de eso (control en la misma prueba)."""
        self.client.force_login(crear_gerente())
        seccion = extensiones.SeccionDeInicio("seccion_falsa.html", {"nombre": "Invernadero Sur"})

        with plantillas_con(**{"seccion_falsa.html": "<p>SECCION FALSA {{ datos.nombre }}</p>"}):
            with mock.patch.object(extensiones, "_SECCIONES_DE_INICIO", [lambda usuario: seccion]):
                con = self.client.get(reverse("core:inicio"))
            with mock.patch.object(extensiones, "_SECCIONES_DE_INICIO", []):
                sin = self.client.get(reverse("core:inicio"))

        self.assertContains(con, "SECCION FALSA Invernadero Sur")
        self.assertContains(con, "Operás como")
        self.assertNotContains(sin, "SECCION FALSA")
        self.assertContains(sin, "Operás como")
