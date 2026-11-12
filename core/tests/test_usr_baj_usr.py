# Pruebas de USR-BAJ-USR (Baja Usuario) y de lo que cita: precondiciones a y b, regla 1, postcondiciones
# a y d, SEG-14 (qué se audita), D-22 (auditoría en la misma transacción) y D-28. Las de servicio llaman a
# core.servicios.baja_usuario; las de vista (integración) se agregan después de implementar el servicio.
# Cada prueba arma sus propios datos. El servicio se llama a través del módulo (servicios.x) para que,
# mientras no exista, cada prueba falle por separado en vez de romper la importación del archivo.
#
# Contrato que fijan estas pruebas: baja_usuario(actor, cuenta_id). Una cuenta fuera del alcance lanza
# PermissionDenied; un id inexistente, Http404; una cuenta ya inactiva, ValidationError con el código
# «cuenta_inactiva».
#
# Fuera de estas pruebas, por no existir todavía lo que las motiva (ver «Lo que queda para más adelante»
# de docs/casos_de_uso/usuarios.md): postcondiciones c, e, f y g y regla 4 (pendientes, invernaderos,
# pedidos y entregas); precondición c y SEG-15 (último Administrador, tarea 05); regla 2 (cuentas
# vinculadas, tarea 06).

import json
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import Client, TestCase
from django.urls import reverse

from core import servicios
from core.models import Capataz, Gerente, RegistroAuditoria, Usuario, Vendedor

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
        """USR-BAJ-USR precondición a: solo da de baja una cuenta activa de Gerente (el Administrador
        llega en la tarea 05). Un Capataz o un Gerente dado de baja no pueden."""
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
