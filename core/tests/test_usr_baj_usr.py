# Pruebas de USR-BAJ-USR (Baja Usuario) y de lo que cita: precondiciones a y b, regla 1, postcondiciones
# a y d, SEG-14 (qué se audita), D-22 (auditoría en la misma transacción) y D-28. Las de servicio llaman a
# core.servicios.baja_usuario; las de vista (integración) se agregan después de implementar el servicio.
# Cada prueba arma sus propios datos. El servicio se llama a través del módulo (servicios.x) para que,
# mientras no exista, cada prueba falle por separado en vez de romper la importación del archivo.
#
# Contrato que fijan estas pruebas: baja_usuario(actor, cuenta_id). Una cuenta fuera del alcance lanza
# PermissionDenied; un id inexistente, Http404; una cuenta ya inactiva, ValidationError con el código
# «cuenta_inactiva». Tarea 05b (D-16, SEG-15): dar de baja a un Administrador cuando no queda otro activo
# lanza ValidationError con el código «ultimo_administrador».
#
# Fuera de estas pruebas, por no existir todavía lo que las motiva (ver «Lo que queda para más adelante»
# de docs/casos_de_uso/usuarios.md): postcondiciones c, e, f y g y regla 4 (pendientes, invernaderos,
# pedidos y entregas); regla 2 (cuentas vinculadas, tarea 06).

import json
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from core import servicios
from core.models import ADMINISTRADOR, Capataz, Gerente, RegistroAuditoria, Usuario, Vendedor
from core.tests.concurrencia import codigos, correr_a_la_vez, separar

CLAVE = "clave-segura-123"


def crear_gerente(email="gerente@infoponia.com", activo=True):
    """Crea un Gerente con la contraseña de prueba. Solo puede haber uno activo (D-09)."""
    return Gerente.objects.create_user(
        email=email, password=CLAVE, first_name="Gabriela", last_name="Sosa", is_active=activo
    )


def crear_administrador(email="admin@infoponia.com"):
    """Crea un Administrador técnico: superusuario sin rol (D-10)."""
    return Usuario.objects.create_superuser(
        email=email, password=CLAVE, first_name="Adrián", last_name="Mena"
    )


def crear_cuenta(clase, email="laura@infoponia.com", activo=True):
    """Crea una cuenta del rol de ``clase`` con la contraseña de prueba."""
    return clase.objects.create_user(
        email=email, password=CLAVE, first_name="Laura", last_name="Benítez", is_active=activo
    )


class UsrBajUsrServicioTests(TestCase):
    """Reglas, precondiciones y postcondiciones de USR-BAJ-USR en el servicio ``baja_usuario``."""

    # ---- Precondiciones ----

    def test_pre_a_rechaza_actor_sin_cuenta_activa_de_gerente(self):
        """USR-BAJ-USR precondición a: da de baja una cuenta activa de Gerente o de Administrador (las
        del Administrador están más abajo). Un Capataz o un Gerente dado de baja no pueden."""
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")
        gerente_inactivo = crear_gerente(activo=False)
        objetivo = crear_cuenta(Vendedor, "vendedor@infoponia.com")

        for actor in (capataz, gerente_inactivo):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    servicios.baja_usuario(actor, objetivo.pk)
        self.assertTrue(Usuario.objects.get(pk=objetivo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_pre_b_rechaza_cuenta_inactiva(self):
        """USR-BAJ-USR precondición b: la cuenta tiene que estar activa; dar de baja una inactiva se
        rechaza y no deja registro de auditoría."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        with self.assertRaises(ValidationError) as contexto:
            servicios.baja_usuario(gerente, cuenta.pk)

        self.assertEqual(contexto.exception.code, "cuenta_inactiva")
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_pre_b_cuenta_inexistente_da_404(self):
        """USR-BAJ-USR precondición b y D-28: un id que no corresponde a ninguna cuenta da 404."""
        gerente = crear_gerente()

        with self.assertRaises(Http404):
            servicios.baja_usuario(gerente, 999999)

    # ---- Reglas del caso de uso ----

    def test_regla_1_rechaza_cuenta_fuera_de_alcance(self):
        """USR-BAJ-USR regla 1 (el alcance de USR-MOD-USR): el Gerente no da de baja la cuenta de un
        Administrador ni de otro Gerente; ninguna cambia."""
        gerente = crear_gerente()
        administrador = crear_administrador()
        otro_gerente = Gerente.objects.create_user(
            email="otro@infoponia.com", password=CLAVE, first_name="Otro", last_name="Gerente", is_active=False
        )

        for cuenta in (administrador, otro_gerente):
            with self.subTest(cuenta=cuenta.email):
                with self.assertRaises(PermissionDenied):
                    servicios.baja_usuario(gerente, cuenta.pk)
        administrador.refresh_from_db()
        self.assertTrue(administrador.is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_1_gerente_no_se_da_de_baja(self):
        """USR-BAJ-USR regla 1: el Gerente no se da de baja a sí mismo (lo hace el Administrador)."""
        gerente = crear_gerente()

        with self.assertRaises(PermissionDenied):
            servicios.baja_usuario(gerente, gerente.pk)

        self.assertTrue(Usuario.objects.get(pk=gerente.pk).is_active)

    # ---- Postcondiciones ----

    def test_post_a_deja_la_cuenta_inactiva(self):
        """USR-BAJ-USR postcondición a: la cuenta queda «inactiva» (baja lógica): no se borra, conserva
        su rol, sus datos y su contraseña, y ya no puede identificarse (regla 2 de USR-INI-SES)."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        servicios.baja_usuario(gerente, cuenta.pk)

        guardada = Usuario.objects.get(pk=cuenta.pk)
        self.assertFalse(guardada.is_active)
        self.assertEqual(guardada.rol, Usuario.Rol.CAPATAZ)
        self.assertEqual(guardada.email, "laura@infoponia.com")
        self.assertTrue(guardada.check_password(CLAVE))
        # Una cuenta inactiva ya no puede iniciar sesión: ``authenticate`` la rechaza (regla 2 de
        # USR-INI-SES). Cortar una sesión que ya estaba abierta (postcondición b) lo hace ``get_user``, y
        # eso lo cubre la prueba de vista con dos clientes.
        self.assertFalse(self.client.login(email="laura@infoponia.com", password=CLAVE))

    def test_post_d_audita_el_cambio_de_estado(self):
        """USR-BAJ-USR postcondición d, SEG-14 y D-22: queda un registro de auditoría con quién actuó,
        su rol, la acción, la cuenta y el cambio de estado; sin contraseñas."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        servicios.baja_usuario(gerente, cuenta.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.BAJA)
        self.assertEqual(registro.usuario_id, gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        self.assertEqual(registro.detalle, {"estado": ["activo", "inactivo"]})
        contenido = json.dumps([registro.afectados, registro.detalle])
        self.assertNotIn(cuenta.password, contenido)

    # ---- Decisión D-22 ----

    def test_d22_si_falla_la_auditoria_no_da_de_baja(self):
        """D-22: la baja y su registro de auditoría se guardan en la misma transacción; si falla el
        registro, la cuenta sigue activa."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        with mock.patch.object(
            RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla simulada")
        ):
            with self.assertRaises(RuntimeError):
                servicios.baja_usuario(gerente, cuenta.pk)

        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).is_active)


    # ---- El Administrador (tarea 05b, D-16 y SEG-15) ----

    def test_pre_a_rechaza_administrador_inactivo(self):
        """USR-BAJ-USR precondición a: un Administrador dado de baja no da de baja a nadie; no cambia
        nada ni se audita."""
        crear_administrador()
        inactivo = crear_administrador(email="admin.anterior@infoponia.com")
        inactivo.is_active = False
        inactivo.save()
        gerente = crear_gerente()

        with self.assertRaises(PermissionDenied):
            servicios.baja_usuario(inactivo, gerente.pk)

        self.assertTrue(Usuario.objects.get(pk=gerente.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_pre_c_rechaza_baja_del_ultimo_administrador_activo(self):
        """USR-BAJ-USR precondición c y regla 1, y SEG-15: el único Administrador activo no puede darse de
        baja (siempre queda al menos uno); el error lleva el código «ultimo_administrador», la cuenta
        sigue activa y no se audita nada."""
        administrador = crear_administrador()

        with self.assertRaises(ValidationError) as contexto:
            servicios.baja_usuario(administrador, administrador.pk)

        self.assertEqual(contexto.exception.code, "ultimo_administrador")
        self.assertIn("último Administrador", contexto.exception.messages[0])
        self.assertTrue(Usuario.objects.get(pk=administrador.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_pre_c_administradores_inactivos_no_cuentan(self):
        """USR-BAJ-USR precondición c y SEG-15: «queda al menos otro Administrador activo» cuenta solo los
        activos; con otro Administrador dado de baja, el único activo no puede darse de baja."""
        administrador = crear_administrador()
        inactivo = crear_administrador(email="admin.anterior@infoponia.com")
        inactivo.is_active = False
        inactivo.save()

        with self.assertRaises(ValidationError) as contexto:
            servicios.baja_usuario(administrador, administrador.pk)

        self.assertEqual(contexto.exception.code, "ultimo_administrador")
        self.assertTrue(Usuario.objects.get(pk=administrador.pk).is_active)

    def test_regla_1_administrador_se_da_de_baja_si_no_es_el_ultimo(self):
        """USR-BAJ-USR regla 1, postcondiciones a y d, y D-16: el Administrador puede darse de baja a sí
        mismo si queda otro Administrador activo; la baja se audita con su rol y el cambio de estado."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")

        servicios.baja_usuario(administrador, administrador.pk)

        self.assertFalse(Usuario.objects.get(pk=administrador.pk).is_active)
        self.assertTrue(Usuario.objects.get(pk=otro_administrador.pk).is_active)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.BAJA)
        self.assertEqual(registro.usuario_id, administrador.pk)
        self.assertEqual(registro.rol, ADMINISTRADOR)
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": administrador.pk}])
        self.assertEqual(registro.detalle, {"estado": ["activo", "inactivo"]})

    def test_regla_1_administrador_da_de_baja_a_otro_administrador(self):
        """USR-BAJ-USR regla 1 y D-16: el Administrador da de baja a otro Administrador; queda él, activo."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")

        servicios.baja_usuario(administrador, otro_administrador.pk)

        self.assertFalse(Usuario.objects.get(pk=otro_administrador.pk).is_active)
        self.assertTrue(Usuario.objects.get(pk=administrador.pk).is_active)

    def test_regla_1_administrador_da_de_baja_al_gerente(self):
        """USR-BAJ-USR regla 1, regla 3 y D-16: el Administrador da de baja la cuenta del Gerente (no se
        bloquea por sus pendientes); la cuenta se conserva inactiva y se audita con el rol del
        Administrador. Dar de baja al Gerente no depende de cuántos Administradores haya."""
        administrador = crear_administrador()
        gerente = crear_gerente()

        servicios.baja_usuario(administrador, gerente.pk)

        guardado = Usuario.objects.get(pk=gerente.pk)
        self.assertFalse(guardado.is_active)
        self.assertEqual(guardado.rol, Usuario.Rol.GERENTE)
        self.assertEqual(RegistroAuditoria.objects.get().rol, ADMINISTRADOR)

    def test_regla_1_administrador_no_da_de_baja_otros_roles(self):
        """USR-BAJ-USR regla 1 y D-16: las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico
        las gestiona el Gerente; para el Administrador están fuera del alcance."""
        administrador = crear_administrador()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")

        with self.assertRaises(PermissionDenied):
            servicios.baja_usuario(administrador, capataz.pk)

        self.assertTrue(Usuario.objects.get(pk=capataz.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)


class UsrBajUsrVistaTests(TestCase):
    """Flujo principal de USR-BAJ-USR en las pantallas, con el cliente de prueba de Django. La de
    sesión usa dos clientes, como dos navegadores."""

    def entrar_como_gerente(self):
        """Crea un Gerente, abre su sesión en ``self.client`` y lo devuelve."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        return gerente

    def test_flujo_principal_confirma_y_da_de_baja(self):
        """USR-BAJ-USR flujo principal y postcondiciones a y d: la baja pide confirmación (abrirla no
        cambia nada); al confirmar, la cuenta queda inactiva, se vuelve a la ficha con el aviso y la ficha
        pasa a ofrecer reactivar."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)
        url = reverse("core:usuario_baja", args=[cuenta.pk])

        confirmacion = self.client.get(url, headers={"HX-Request": "true"})
        self.assertContains(confirmacion, "¿Dar de baja esta cuenta?")
        self.assertNotContains(confirmacion, "<html")
        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).is_active)

        respuesta = self.client.post(url, follow=True)

        self.assertRedirects(respuesta, reverse("core:usuario", args=[cuenta.pk]))
        self.assertContains(respuesta, "Se dio de baja la cuenta de Laura Benítez.")
        self.assertContains(respuesta, "Reactivar cuenta")
        self.assertFalse(Usuario.objects.get(pk=cuenta.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.get().accion, RegistroAuditoria.Accion.BAJA)

    def test_post_b_la_cuenta_dada_de_baja_pierde_la_sesion(self):
        """USR-BAJ-USR postcondición b: al dar de baja una cuenta se cierran sus sesiones abiertas: con la
        cuenta ya inactiva, el pedido siguiente de su navegador va al inicio de sesión. Dos clientes: uno
        con la sesión de la cuenta y otro con la del Gerente."""
        cuenta = crear_cuenta(Capataz)
        navegador_de_la_cuenta = Client()
        self.assertTrue(navegador_de_la_cuenta.login(email=cuenta.email, password=CLAVE))
        self.assertEqual(navegador_de_la_cuenta.get(reverse("core:inicio")).status_code, 200)
        self.entrar_como_gerente()

        self.client.post(reverse("core:usuario_baja", args=[cuenta.pk]))

        respuesta = navegador_de_la_cuenta.get(reverse("core:inicio"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith(reverse("core:iniciar_sesion")))

    def test_pre_b_baja_de_cuenta_ya_inactiva_muestra_el_motivo(self):
        """USR-BAJ-USR precondición b: si la cuenta ya está inactiva (por ejemplo, otra persona la dio de
        baja mientras la ventana estaba abierta), la ventana vuelve a mostrarse con el motivo y no queda
        un segundo registro de auditoría."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        respuesta = self.client.post(reverse("core:usuario_baja", args=[cuenta.pk]))

        self.assertContains(respuesta, "La cuenta ya está inactiva.")
        self.assertContains(respuesta, "¿Dar de baja esta cuenta?")
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_seg13_baja_fuera_de_alcance_recibe_403(self):
        """SEG-13 y USR-BAJ-USR regla 1: dar de baja a un Administrador, a otro Gerente o a uno mismo da
        403 con el mensaje, al abrir la ventana y al confirmar; un Capataz recibe 403. Nada cambia."""
        gerente = self.entrar_como_gerente()
        administrador = crear_administrador()

        for cuenta in (administrador, gerente):
            url = reverse("core:usuario_baja", args=[cuenta.pk])
            for metodo in (self.client.get, self.client.post):
                with self.subTest(cuenta=cuenta.email, metodo=metodo.__name__):
                    self.assertContains(
                        metodo(url), "Esa cuenta no está dentro de las que gestionás.", status_code=403
                    )
        self.assertTrue(Usuario.objects.get(pk=administrador.pk).is_active)
        self.assertTrue(Usuario.objects.get(pk=gerente.pk).is_active)

        self.client.force_login(crear_cuenta(Capataz, "capataz@infoponia.com"))
        objetivo = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        respuesta = self.client.post(reverse("core:usuario_baja", args=[objetivo.pk]))
        self.assertContains(respuesta, "Tu cuenta de Capataz no tiene acceso", status_code=403)
        self.assertTrue(Usuario.objects.get(pk=objetivo.pk).is_active)

    # ---- El Administrador (tarea 05b, D-16 y SEG-15) ----

    def test_flujo_principal_administrador_da_de_baja_a_otro_administrador(self):
        """USR-BAJ-USR flujo principal, regla 1, postcondiciones a y d: el Administrador da de baja a otro
        Administrador: la baja pide confirmación, vuelve a la ficha con el aviso y la ficha pasa a ofrecer
        reactivar; queda auditada con su rol."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        self.client.force_login(administrador)
        url = reverse("core:usuario_baja", args=[otro_administrador.pk])

        confirmacion = self.client.get(url, headers={"HX-Request": "true"})
        respuesta = self.client.post(url, follow=True)

        self.assertContains(confirmacion, "¿Dar de baja esta cuenta?")
        self.assertContains(confirmacion, "(Administrador)")
        self.assertNotContains(confirmacion, "Es tu propia cuenta")
        self.assertRedirects(respuesta, reverse("core:usuario", args=[otro_administrador.pk]))
        self.assertContains(respuesta, "Se dio de baja la cuenta de Adrián Mena.")
        self.assertContains(respuesta, "Reactivar cuenta")
        self.assertFalse(Usuario.objects.get(pk=otro_administrador.pk).is_active)
        self.assertTrue(Usuario.objects.get(pk=administrador.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.get().rol, ADMINISTRADOR)

    def test_post_b_administrador_que_se_da_de_baja_sale_de_su_sesion(self):
        """USR-BAJ-USR regla 1 y postcondición b (D-30): si el Administrador se da de baja a sí mismo (hay
        otro activo), la ventana lo avisa («Es tu propia cuenta»); al confirmar, se cierra su sesión y
        vuelve al inicio de sesión con «Tu cuenta se dio de baja y se cerró la sesión.»; ya no entra a
        ninguna pantalla. El otro Administrador sigue activo."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        self.client.force_login(administrador)
        url = reverse("core:usuario_baja", args=[administrador.pk])

        confirmacion = self.client.get(url)
        respuesta = self.client.post(url, follow=True)

        self.assertContains(confirmacion, "Es tu propia cuenta")
        self.assertRedirects(respuesta, reverse("core:iniciar_sesion"))
        self.assertContains(respuesta, "Tu cuenta se dio de baja y se cerró la sesión.")
        self.assertFalse(Usuario.objects.get(pk=administrador.pk).is_active)
        self.assertTrue(Usuario.objects.get(pk=otro_administrador.pk).is_active)
        sin_sesion = self.client.get(reverse("core:usuarios"))
        self.assertEqual(sin_sesion.status_code, 302)
        self.assertTrue(sin_sesion["Location"].startswith(reverse("core:iniciar_sesion")))

    def test_pre_c_ultimo_administrador_muestra_el_motivo(self):
        """USR-BAJ-USR precondición c y SEG-15 (D-30): el único Administrador activo no ofrece «Dar de baja»
        en su ficha; si igual envía el pedido a mano, la ventana muestra «es el último Administrador
        activo», la cuenta sigue activa, la sesión sigue abierta y no se audita nada."""
        administrador = crear_administrador()
        self.client.force_login(administrador)
        url = reverse("core:usuario_baja", args=[administrador.pk])

        ficha = self.client.get(reverse("core:usuario", args=[administrador.pk]))
        respuesta = self.client.post(url)

        self.assertNotContains(ficha, "Dar de baja")
        self.assertContains(respuesta, "No se puede dar de baja: es el último Administrador activo.")
        self.assertContains(respuesta, "¿Dar de baja esta cuenta?")
        self.assertTrue(Usuario.objects.get(pk=administrador.pk).is_active)
        self.assertEqual(self.client.get(reverse("core:usuarios")).status_code, 200)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)


class UsrBajUsrConcurrenciaTests(TransactionTestCase):
    """SEG-15 en ``baja_usuario``: dos bajas simultáneas de Administradores dejan al menos uno activo, y
    la segunda recibe un rechazo con mensaje, no un error 500 ni un deadlock. Son ``TransactionTestCase``
    porque cada operación corre en su propio hilo, con su propia conexión y transacción (ver
    ``core/tests/concurrencia.py``). Dos escenarios: cada Administrador se da de baja a sí mismo (la
    segunda llega al conteo y se rechaza por ser el último) y, con tres, dos se dan de baja entre sí (la
    segunda se rechaza porque su actor ya cayó)."""

    def test_seg15_bajas_simultaneas_dejan_un_administrador_activo(self):
        """SEG-15, precondición c de USR-BAJ-USR y D-16: con dos Administradores activos, cada uno se da de
        baja a sí mismo a la vez. Se bloquean todos los Administradores activos antes de contarlos: la
        segunda baja espera, ve que la primera ya confirmó y se rechaza con «ultimo_administrador» (su
        actor sigue activo, así que llega hasta el conteo). Para los Administradores no hay una
        restricción de la base que respalde la regla (compara varias filas): si falta el bloqueo, las dos
        bajas pasan y no queda ningún Administrador activo, así que esta prueba falla."""
        primero = crear_administrador()
        segundo = crear_administrador(email="admin2@infoponia.com")

        resultados = correr_a_la_vez(
            lambda: servicios.baja_usuario(primero, primero.pk),
            lambda: servicios.baja_usuario(segundo, segundo.pk),
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("ultimo_administrador", codigos(rechazos[0]))
        self.assertEqual(Usuario.objects.filter(is_superuser=True, is_active=True).count(), 1)
        self.assertEqual(
            RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA).count(), 1
        )

    def test_seg15_actor_dado_de_baja_mientras_esperaba_el_bloqueo_no_actua(self):
        """SEG-15 y precondición a de USR-BAJ-USR: con tres Administradores, dos se dan de baja entre sí a
        la vez. La primera baja que confirma deja inactivo al actor de la otra, que esperaba el bloqueo;
        al seguir, la segunda vuelve a verificar que su actor siga activo (su fila estaba entre las
        bloqueadas) y se rechaza con ``PermissionDenied`` sin cambiar nada. Quedan activos el que ganó y el
        tercero. Sin esa segunda verificación, la baja de quien ya estaba inactivo también pasa. Se prueba
        el cruce simétrico: con A->B y B->C el resultado depende de quién llegue primero y las dos bajas
        pueden ser válidas (B actuó antes de caer)."""
        primero = crear_administrador()
        segundo = crear_administrador(email="admin2@infoponia.com")
        tercero = crear_administrador(email="admin3@infoponia.com")

        resultados = correr_a_la_vez(
            lambda: servicios.baja_usuario(primero, segundo.pk),
            lambda: servicios.baja_usuario(segundo, primero.pk),
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(len(exitos), 1)
        self.assertEqual(rechazos, [])
        self.assertEqual(len(otros), 1, "la otra baja se rechaza porque su actor ya no está activo")
        self.assertIsInstance(otros[0], PermissionDenied)
        activos = set(
            Usuario.objects.filter(is_superuser=True, is_active=True).values_list("pk", flat=True)
        )
        self.assertEqual(len(activos), 2)
        self.assertIn(tercero.pk, activos)
        self.assertEqual(
            RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA).count(), 1
        )
