# Pruebas de USR-MOD-USR (Modificar Usuario) y de lo que cita: precondiciones, reglas 1 a 9,
# postcondiciones a a d, SEG-04 (contraseña temporal), SEG-14 (qué se audita), D-22 (auditoría en la
# misma transacción) y D-28. Las de servicio llaman a core.servicios.modificar_usuario,
# restablecer_contrasena y reactivar_usuario; las de vista (integración) se agregan después de implementar
# los servicios. Cada prueba arma sus propios datos. Los servicios se llaman a través del módulo
# (servicios.x) para que, mientras no existan, cada prueba falle por separado en vez de romper la
# importación del archivo.
#
# Contrato que fijan estas pruebas: los tres servicios reciben (actor, cuenta_id, ...). Una cuenta fuera
# del alcance lanza PermissionDenied; un id inexistente, Http404; una cuenta en el estado equivocado
# (restablecer una inactiva, reactivar una activa), ValidationError con el código «cuenta_inactiva» o
# «cuenta_activa»; los datos inválidos, ValidationError por campo. ``modificar_usuario`` devuelve la
# cuenta; ``restablecer_contrasena`` y ``reactivar_usuario``, la contraseña temporal en texto plano.

import json
from datetime import timedelta
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core import servicios
from core.models import Capataz, Gerente, RegistroAuditoria, Usuario, Vendedor

CLAVE = "clave-segura-123"
MENSAJE_EMAIL_REPETIDO = "Ya existe una cuenta con ese email."


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


def crear_cuenta(clase, email="laura@infoponia.com", activo=True, telefono=""):
    """Crea una cuenta del rol de ``clase`` con la contraseña de prueba."""
    return clase.objects.create_user(
        email=email,
        password=CLAVE,
        first_name="Laura",
        last_name="Benítez",
        telefono=telefono,
        is_active=activo,
    )


def dar_temporal_vencida(cuenta):
    """Le da a la cuenta una contraseña temporal generada hace 8 días (ya venció, SEG-04)."""
    cuenta.asignar_contrasena_temporal()
    cuenta.fecha_contrasena_temporal = timezone.now() - timedelta(days=8)
    cuenta.save()


def datos_validos(cuenta, **cambios):
    """Los datos actuales de la cuenta como si el formulario se enviara sin tocar nada; ``cambios`` pisa."""
    datos = {
        "nombre": cuenta.first_name,
        "apellido": cuenta.last_name,
        "email": cuenta.email,
        "telefono": cuenta.telefono,
    }
    datos.update(cambios)
    return datos


def contenido_de_auditoria(registro):
    """Todo lo que guarda un registro de auditoría, como texto, para buscar contraseñas en él."""
    return json.dumps([registro.afectados, registro.detalle], ensure_ascii=False)


class UsrModUsrServicioTests(TestCase):
    """Reglas, precondiciones y postcondiciones de USR-MOD-USR en los servicios de modificación."""

    def modificar(self, actor, cuenta, **cambios):
        """Llama a ``modificar_usuario`` con los datos actuales de la cuenta, pisados por ``cambios``."""
        return servicios.modificar_usuario(actor, cuenta.pk, **datos_validos(cuenta, **cambios))

    # ---- Precondiciones ----

    def test_pre_a_rechaza_actor_sin_cuenta_activa_de_gerente(self):
        """USR-MOD-USR precondición a: solo modifica una cuenta activa de Gerente (el Administrador
        llega en la tarea 05). Un Capataz o un Gerente dado de baja no pueden, en ninguna de las tres
        operaciones."""
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com")
        gerente_inactivo = crear_gerente(activo=False)
        objetivo = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        inactiva = crear_cuenta(Vendedor, "inactiva@infoponia.com", activo=False)

        for actor in (capataz, gerente_inactivo):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    self.modificar(actor, objetivo, nombre="Otro")
                with self.assertRaises(PermissionDenied):
                    servicios.restablecer_contrasena(actor, objetivo.pk)
                with self.assertRaises(PermissionDenied):
                    servicios.reactivar_usuario(actor, inactiva.pk)
        objetivo.refresh_from_db()
        self.assertEqual(objetivo.first_name, "Laura")
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_pre_b_cuenta_inexistente_da_404(self):
        """USR-MOD-USR precondición b y D-28: un id que no corresponde a ninguna cuenta da 404."""
        gerente = crear_gerente()

        with self.assertRaises(Http404):
            servicios.modificar_usuario(gerente, 999999, "Ana", "Pérez", "ana@infoponia.com", "")
        with self.assertRaises(Http404):
            servicios.restablecer_contrasena(gerente, 999999)
        with self.assertRaises(Http404):
            servicios.reactivar_usuario(gerente, 999999)

    def test_pre_b_modifica_datos_de_cuenta_inactiva_dentro_del_alcance(self):
        """USR-MOD-USR precondición b y prototipo (vUsuario y save-user): para modificar los datos solo se
        exige que la cuenta esté dentro del alcance, no que esté activa (a diferencia de USR-BAJ-USR, que
        sí lo pide). El caso de uso no menciona el estado; el prototipo muestra «Modificar datos» siempre y
        no controla el estado al guardar. Modificar no reactiva la cuenta ni toca su contraseña."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)
        resumen = cuenta.password

        self.modificar(gerente, cuenta, apellido="Gómez", telefono="+54 376 400-1001")

        guardada = Usuario.objects.get(pk=cuenta.pk)
        self.assertEqual(guardada.last_name, "Gómez")
        self.assertEqual(guardada.telefono, "+54 376 400-1001")
        self.assertFalse(guardada.is_active)
        self.assertEqual(guardada.password, resumen)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.MODIFICACION)

    # ---- Reglas del caso de uso ----

    def test_regla_1_rechaza_cuenta_fuera_de_alcance(self):
        """USR-MOD-USR regla 1: el Gerente no modifica, restablece ni reactiva la cuenta de un
        Administrador ni de otro Gerente."""
        gerente = crear_gerente()
        administrador = crear_administrador()
        anterior = crear_gerente(email="anterior@infoponia.com", activo=False)

        for cuenta in (administrador, anterior):
            with self.subTest(cuenta=cuenta.email):
                with self.assertRaises(PermissionDenied):
                    self.modificar(gerente, cuenta, nombre="Otro")
                with self.assertRaises(PermissionDenied):
                    servicios.restablecer_contrasena(gerente, cuenta.pk)
                with self.assertRaises(PermissionDenied):
                    servicios.reactivar_usuario(gerente, cuenta.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_1_gerente_no_modifica_su_propia_cuenta(self):
        """USR-MOD-USR regla 1: el Gerente no modifica la suya ni restablece su contraseña (la cambia
        con USR-CMB-CTR)."""
        gerente = crear_gerente()

        with self.assertRaises(PermissionDenied):
            self.modificar(gerente, gerente, nombre="Otro")
        with self.assertRaises(PermissionDenied):
            servicios.restablecer_contrasena(gerente, gerente.pk)
        gerente.refresh_from_db()
        self.assertEqual(gerente.first_name, "Gabriela")
        self.assertTrue(gerente.check_password(CLAVE))

    def test_regla_2_modificar_no_recibe_rol(self):
        """USR-MOD-USR regla 2 y D-11: el rol no se modifica; el servicio no tiene ese parámetro."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        with self.assertRaises(TypeError):
            servicios.modificar_usuario(
                gerente, cuenta.pk, **datos_validos(cuenta), rol=Usuario.Rol.VENDEDOR
            )
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.rol, Usuario.Rol.CAPATAZ)

    def test_regla_3_cambia_el_email_si_sigue_siendo_unico(self):
        """USR-MOD-USR regla 3 y precondición c: el email se puede cambiar si queda único; se guarda
        en minúsculas y sin espacios (SEG-01)."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        self.modificar(gerente, cuenta, email="  Laura.Nueva@Infoponia.com ")

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.email, "laura.nueva@infoponia.com")

    def test_regla_3_rechaza_email_de_otra_cuenta(self):
        """USR-MOD-USR regla 3 y precondición c: el email nuevo no puede ser el de otra cuenta
        (también con otras mayúsculas, SEG-01), activa o inactiva."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)
        crear_cuenta(Vendedor, "otra@infoponia.com")
        crear_cuenta(Vendedor, "inactiva@infoponia.com", activo=False)

        for email in ("otra@infoponia.com", "OTRA@Infoponia.com", "inactiva@infoponia.com"):
            with self.subTest(email=email):
                with self.assertRaises(ValidationError) as contexto:
                    self.modificar(gerente, cuenta, email=email)
                self.assertEqual(contexto.exception.message_dict["email"], [MENSAJE_EMAIL_REPETIDO])
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.email, "laura@infoponia.com")

    def test_regla_3_conservar_el_propio_email_no_es_repetido(self):
        """USR-MOD-USR regla 3: el email de la propia cuenta no cuenta como repetido (se puede guardar
        el formulario cambiando solo el nombre, o el email con otras mayúsculas)."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        self.modificar(gerente, cuenta, nombre="Lucía", email="LAURA@infoponia.com")

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.first_name, "Lucía")
        self.assertEqual(cuenta.email, "laura@infoponia.com")

    def test_regla_4_restablecer_genera_temporal_nueva(self):
        """USR-MOD-USR regla 4, postcondición b y SEG-04: restablecer genera una contraseña temporal
        (la elige el Sistema, no quien restablece); la contraseña anterior deja de servir."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)
        resumen_anterior = cuenta.password

        temporal = servicios.restablecer_contrasena(gerente, cuenta.pk)

        cuenta.refresh_from_db()
        self.assertEqual(len(temporal), 12)
        self.assertTrue(cuenta.check_password(temporal))
        self.assertFalse(cuenta.check_password(CLAVE))
        self.assertNotEqual(cuenta.password, resumen_anterior)  # cambia el resumen: cierra las sesiones
        self.assertTrue(cuenta.tiene_contrasena_temporal)
        self.assertFalse(cuenta.contrasena_temporal_vencida())
        self.assertTrue(cuenta.is_active)

    def test_regla_4_restablecer_no_recibe_contrasena(self):
        """USR-MOD-USR regla 4: nadie elige la contraseña de otra persona; el servicio solo restablece."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        with self.assertRaises(TypeError):
            servicios.restablecer_contrasena(gerente, cuenta.pk, contrasena="mi-clave-elegida-1")
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(CLAVE))

    def test_seg04_restablecer_renueva_una_temporal_vencida(self):
        """SEG-04: una temporal vencida no sirve para identificarse y quien gestiona la cuenta tiene que
        restablecerla: restablecer una cuenta con temporal vencida le da una vigente."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)
        dar_temporal_vencida(cuenta)
        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).contrasena_temporal_vencida())

        temporal = servicios.restablecer_contrasena(gerente, cuenta.pk)

        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(temporal))
        self.assertFalse(cuenta.contrasena_temporal_vencida())

    def test_regla_6_reactivar_restablece_la_contrasena(self):
        """USR-MOD-USR regla 6 y SEG-11: toda reactivación genera una contraseña temporal nueva; la
        anterior deja de servir."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        temporal = servicios.reactivar_usuario(gerente, cuenta.pk)

        cuenta.refresh_from_db()
        self.assertEqual(len(temporal), 12)
        self.assertTrue(cuenta.check_password(temporal))
        self.assertFalse(cuenta.check_password(CLAVE))
        self.assertTrue(cuenta.tiene_contrasena_temporal)
        self.assertFalse(cuenta.contrasena_temporal_vencida())

    def test_regla_9_rechaza_telefono_invalido(self):
        """USR-MOD-USR regla 9 (la de USR-ALT-USR, D-21 y D-28): letras, un + que no está al comienzo,
        menos de 8 o más de 15 dígitos, o más de 25 caracteres se rechazan; vacío y válidos se aceptan."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        for telefono in ("abc12345678", "376+4001001", "1234567", "1234567890123456", "1 2 3 4 5 6 7 8 9 0 1 2 3 4"):
            with self.subTest(telefono=telefono):
                with self.assertRaises(ValidationError) as contexto:
                    self.modificar(gerente, cuenta, telefono=telefono)
                self.assertIn("telefono", contexto.exception.message_dict)
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.telefono, "")

        self.modificar(gerente, cuenta, telefono="+54 376 400-1001")
        self.modificar(gerente, cuenta, telefono="")

    def test_post_a_exige_nombre_apellido_y_email(self):
        """USR-MOD-USR postcondición a (datos personales indicados) y prototipo (userErr): nombre,
        apellido y email no pueden quedar vacíos; un valor con solo espacios cuenta como vacío."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        for campo in ("nombre", "apellido", "email"):
            for vacio in ("", "   "):
                with self.subTest(campo=campo, valor=vacio):
                    with self.assertRaises(ValidationError) as contexto:
                        self.modificar(gerente, cuenta, **{campo: vacio})
                    self.assertIn(campo, contexto.exception.message_dict)
        cuenta.refresh_from_db()
        self.assertEqual((cuenta.first_name, cuenta.last_name, cuenta.email), ("Laura", "Benítez", "laura@infoponia.com"))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    # ---- Postcondiciones ----

    def test_post_a_actualiza_los_datos_personales(self):
        """USR-MOD-USR postcondición a: se actualizaron nombre, apellido, email y teléfono; el rol, el
        estado y la contraseña no cambian."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)
        resumen = cuenta.password

        devuelta = self.modificar(
            gerente,
            cuenta,
            nombre=" Lucía ",
            apellido=" Gómez ",
            email="lucia@infoponia.com",
            telefono="+54 376 400-1001",
        )

        guardada = Usuario.objects.get(pk=cuenta.pk)
        self.assertEqual(devuelta.pk, cuenta.pk)
        self.assertEqual(guardada.first_name, "Lucía")
        self.assertEqual(guardada.last_name, "Gómez")
        self.assertEqual(guardada.email, "lucia@infoponia.com")
        self.assertEqual(guardada.telefono, "+54 376 400-1001")
        self.assertEqual(guardada.rol, Usuario.Rol.CAPATAZ)
        self.assertTrue(guardada.is_active)
        self.assertEqual(guardada.password, resumen)

    def test_post_c_reactivar_deja_la_cuenta_activa(self):
        """USR-MOD-USR postcondición c: reactivar deja la cuenta en estado «activo»."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        servicios.reactivar_usuario(gerente, cuenta.pk)

        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).is_active)

    def test_post_d_modificacion_audita_los_cambios(self):
        """USR-MOD-USR postcondición d, SEG-14 y D-22: queda un registro de auditoría con quién actuó,
        su rol, la acción, la cuenta y solo los campos que cambiaron, con su valor antes y después."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, telefono="")

        self.modificar(gerente, cuenta, apellido="Gómez", telefono="+54 376 400-1001")

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.MODIFICACION)
        self.assertEqual(registro.usuario_id, gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        self.assertEqual(
            registro.detalle,
            {"apellido": ["Benítez", "Gómez"], "telefono": ["", "+54 376 400-1001"]},
        )

    def test_post_d_restablecer_audita_sin_contrasena(self):
        """USR-MOD-USR postcondición d, SEG-14 y D-22: el restablecimiento se audita y el registro no
        contiene ninguna contraseña (ni la temporal ni el resumen)."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        temporal = servicios.restablecer_contrasena(gerente, cuenta.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.RESTABLECIMIENTO)
        self.assertEqual(registro.usuario_id, gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        cuenta.refresh_from_db()
        contenido = contenido_de_auditoria(registro)
        self.assertNotIn(temporal, contenido)
        self.assertNotIn(cuenta.password, contenido)

    def test_post_d_reactivar_audita_sin_contrasena(self):
        """USR-MOD-USR postcondición d, SEG-14 y D-22: la reactivación se audita con el cambio de
        estado y sin ninguna contraseña."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        temporal = servicios.reactivar_usuario(gerente, cuenta.pk)

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.REACTIVACION)
        self.assertEqual(registro.usuario_id, gerente.pk)
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": cuenta.pk}])
        self.assertEqual(registro.detalle, {"estado": ["inactivo", "activo"]})
        cuenta.refresh_from_db()
        contenido = contenido_de_auditoria(registro)
        self.assertNotIn(temporal, contenido)
        self.assertNotIn(cuenta.password, contenido)

    # ---- Decisiones D-22 y D-28 ----

    def test_d28_sin_cambios_no_guarda_ni_audita(self):
        """D-28: si el formulario se envía sin cambios (también si solo difieren espacios o mayúsculas
        del email), no se guarda nada y no queda un registro de auditoría vacío."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, telefono="+54 376 400-1001")

        self.modificar(gerente, cuenta)
        self.modificar(gerente, cuenta, nombre=" Laura ", email=" LAURA@infoponia.com ")

        self.assertEqual(RegistroAuditoria.objects.count(), 0)
        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).first_name, "Laura")

    def test_d28_restablecer_rechaza_cuenta_inactiva(self):
        """D-28: restablecer solo vale para cuentas activas (una inactiva se reactiva); no cambia nada."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        with self.assertRaises(ValidationError) as contexto:
            servicios.restablecer_contrasena(gerente, cuenta.pk)

        self.assertEqual(contexto.exception.code, "cuenta_inactiva")
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(CLAVE))
        self.assertFalse(cuenta.is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_d28_reactivar_rechaza_cuenta_activa(self):
        """D-28: reactivar solo vale para cuentas inactivas; no restablece la contraseña de una activa."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz)

        with self.assertRaises(ValidationError) as contexto:
            servicios.reactivar_usuario(gerente, cuenta.pk)

        self.assertEqual(contexto.exception.code, "cuenta_activa")
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_d22_si_falla_la_auditoria_no_modifica(self):
        """D-22: la operación y su registro de auditoría se guardan en la misma transacción; si falla
        el registro, no queda ni la modificación, ni la nueva contraseña, ni la reactivación."""
        gerente = crear_gerente()
        activa = crear_cuenta(Capataz)
        inactiva = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False)

        with mock.patch.object(
            RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla simulada")
        ):
            with self.assertRaises(RuntimeError):
                self.modificar(gerente, activa, nombre="Otro")
            with self.assertRaises(RuntimeError):
                servicios.restablecer_contrasena(gerente, activa.pk)
            with self.assertRaises(RuntimeError):
                servicios.reactivar_usuario(gerente, inactiva.pk)

        activa.refresh_from_db()
        inactiva.refresh_from_db()
        self.assertEqual(activa.first_name, "Laura")
        self.assertTrue(activa.check_password(CLAVE))
        self.assertFalse(inactiva.is_active)
        self.assertTrue(inactiva.check_password(CLAVE))


class UsrModUsrVistaTests(TestCase):
    """Flujo principal de USR-MOD-USR en las pantallas (modificar, restablecer y reactivar), con el
    cliente de prueba de Django. Las de dos clientes usan uno por cuenta, como dos navegadores."""

    def entrar_como_gerente(self):
        """Crea un Gerente, abre su sesión en ``self.client`` y lo devuelve."""
        gerente = crear_gerente()
        self.client.force_login(gerente)
        return gerente

    def test_flujo_principal_modifica_los_datos(self):
        """USR-MOD-USR flujo principal y postcondición a: el formulario viene con los datos actuales y el
        rol bloqueado; al guardar, vuelve a la ficha con el aviso «Cambios guardados.» y los datos nuevos."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)
        url = reverse("core:usuario_modificar", args=[cuenta.pk])

        formulario = self.client.get(url)
        respuesta = self.client.post(
            url,
            {"nombre": "Lucía", "apellido": "Gómez", "email": "lucia@infoponia.com", "telefono": "+54 376 400-1001"},
            follow=True,
        )

        self.assertContains(formulario, 'value="Laura"')
        self.assertContains(formulario, 'value="laura@infoponia.com"')
        self.assertContains(formulario, 'id="rol-bloqueado"')
        self.assertRedirects(respuesta, reverse("core:usuario", args=[cuenta.pk]))
        self.assertContains(respuesta, "Cambios guardados.")
        cuenta.refresh_from_db()
        self.assertEqual((cuenta.first_name, cuenta.last_name), ("Lucía", "Gómez"))
        self.assertEqual((cuenta.email, cuenta.telefono), ("lucia@infoponia.com", "+54 376 400-1001"))

    def test_flujo_principal_ficha_ofrece_las_acciones_segun_el_estado(self):
        """USR-MOD-USR y USR-BAJ-USR (vUsuario): una cuenta activa ofrece restablecer y dar de baja; una
        inactiva, reactivar. En las dos se pueden modificar los datos (D-28)."""
        self.entrar_como_gerente()
        activa = crear_cuenta(Capataz)
        inactiva = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False)

        ficha_activa = self.client.get(reverse("core:usuario", args=[activa.pk]))
        ficha_inactiva = self.client.get(reverse("core:usuario", args=[inactiva.pk]))

        for texto in ("Restablecer contraseña", "Dar de baja", "Modificar datos"):
            self.assertContains(ficha_activa, texto)
        self.assertNotContains(ficha_activa, "Reactivar cuenta")
        self.assertContains(ficha_inactiva, "Reactivar cuenta")
        self.assertContains(ficha_inactiva, "Modificar datos")
        for texto in ("Restablecer contraseña", "Dar de baja"):
            self.assertNotContains(ficha_inactiva, texto)

    def test_flujo_principal_abrir_la_confirmacion_no_cambia_nada(self):
        """USR-MOD-USR flujo principal: restablecer y reactivar piden confirmación; abrir la ventana (GET)
        no cambia la contraseña ni el estado ni deja registro de auditoría."""
        self.entrar_como_gerente()
        activa = crear_cuenta(Capataz)
        inactiva = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False)

        restablecer = self.client.get(reverse("core:usuario_restablecer", args=[activa.pk]))
        reactivar = self.client.get(reverse("core:usuario_reactivar", args=[inactiva.pk]))

        self.assertContains(restablecer, "¿Restablecer la contraseña?")
        self.assertContains(reactivar, "¿Reactivar la cuenta?")
        activa.refresh_from_db()
        inactiva.refresh_from_db()
        self.assertTrue(activa.check_password(CLAVE))
        self.assertFalse(inactiva.is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_flujo_principal_confirmacion_con_htmx_devuelve_solo_la_ventana(self):
        """USR-MOD-USR flujo principal: con HTMX la confirmación llega como una ventana (sin la pantalla
        entera) que envía un POST a la misma URL; sin HTMX llega la ficha con la ventana abierta."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)
        url = reverse("core:usuario_restablecer", args=[cuenta.pk])

        parcial = self.client.get(url, headers={"HX-Request": "true"})
        entera = self.client.get(url)

        self.assertContains(parcial, "¿Restablecer la contraseña?")
        self.assertContains(parcial, f'action="{url}"')
        self.assertNotContains(parcial, "<html")
        self.assertContains(entera, "<html")
        self.assertContains(entera, "¿Restablecer la contraseña?")
        self.assertContains(entera, "laura@infoponia.com")  # la ficha queda detrás de la ventana

    def test_flujo_principal_restablece_y_muestra_la_temporal(self):
        """USR-MOD-USR flujo principal, regla 4 y postcondición b: al confirmar, la cuenta tiene una
        temporal nueva, que se le muestra una sola vez a quien la restableció; la ficha posterior no la
        tiene y la respuesta no se guarda en el navegador."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)
        url = reverse("core:usuario_restablecer", args=[cuenta.pk])

        respuesta = self.client.post(url)

        self.assertEqual(respuesta.status_code, 200)
        temporal = respuesta.context["contrasena_temporal"]
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(temporal))
        self.assertContains(respuesta, "Contraseña restablecida")
        self.assertContains(respuesta, temporal)
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertNotContains(self.client.get(reverse("core:usuario", args=[cuenta.pk])), temporal)
        self.assertEqual(RegistroAuditoria.objects.get().accion, RegistroAuditoria.Accion.RESTABLECIMIENTO)

    def test_flujo_principal_reactiva_y_muestra_la_temporal(self):
        """USR-MOD-USR flujo principal, regla 6 y postcondición c: al confirmar, la cuenta queda activa con
        una temporal nueva que se muestra una sola vez; la ficha pasa a ofrecer las acciones de una activa."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        respuesta = self.client.post(reverse("core:usuario_reactivar", args=[cuenta.pk]))

        self.assertEqual(respuesta.status_code, 200)
        temporal = respuesta.context["contrasena_temporal"]
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.is_active)
        self.assertTrue(cuenta.check_password(temporal))
        self.assertContains(respuesta, "Cuenta reactivada")
        self.assertContains(respuesta, temporal)
        self.assertContains(respuesta, "Restablecer contraseña")  # la ficha detrás ya la muestra activa
        self.assertNotContains(self.client.get(reverse("core:usuario", args=[cuenta.pk])), temporal)

    def test_post_b_restablecer_cierra_la_sesion_de_la_cuenta(self):
        """USR-MOD-USR postcondición b y SEG-11: al restablecer la contraseña se cierran las sesiones
        abiertas con esa cuenta. Dos clientes: uno con la sesión de la cuenta y otro con la del Gerente.
        La cuenta queda con una temporal, así que si su sesión siguiera abierta iría a «Elegí tu
        contraseña»: la prueba exige que vaya al inicio de sesión."""
        cuenta = crear_cuenta(Capataz)
        navegador_de_la_cuenta = Client()
        self.assertTrue(navegador_de_la_cuenta.login(email=cuenta.email, password=CLAVE))
        self.assertEqual(navegador_de_la_cuenta.get(reverse("core:inicio")).status_code, 200)
        self.entrar_como_gerente()

        self.client.post(reverse("core:usuario_restablecer", args=[cuenta.pk]))

        respuesta = navegador_de_la_cuenta.get(reverse("core:inicio"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith(reverse("core:iniciar_sesion")))

    def test_post_b_reactivar_deja_la_cuenta_sin_la_sesion_anterior(self):
        """USR-MOD-USR postcondición b y c, SEG-11: la reactivación cambia la contraseña; una sesión que
        quedara abierta de antes de la baja no vuelve a servir. Dos clientes."""
        cuenta = crear_cuenta(Capataz)
        navegador_de_la_cuenta = Client()
        navegador_de_la_cuenta.login(email=cuenta.email, password=CLAVE)
        gerente = self.entrar_como_gerente()
        servicios.baja_usuario(gerente, cuenta.pk)

        self.client.post(reverse("core:usuario_reactivar", args=[cuenta.pk]))

        respuesta = navegador_de_la_cuenta.get(reverse("core:inicio"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith(reverse("core:iniciar_sesion")))

    def test_regla_2_ignora_el_rol_enviado_en_el_formulario(self):
        """USR-MOD-USR regla 2 y D-11: aunque el pedido traiga un ``rol``, el rol no cambia (el formulario
        no tiene ese campo)."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)

        self.client.post(
            reverse("core:usuario_modificar", args=[cuenta.pk]),
            {"nombre": "Lucía", "apellido": "Gómez", "email": "laura@infoponia.com", "rol": "vendedor"},
        )

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.first_name, "Lucía")
        self.assertEqual(cuenta.rol, Usuario.Rol.CAPATAZ)
        self.assertFalse(Vendedor.objects.filter(pk=cuenta.pk).exists())

    def test_regla_3_modificar_muestra_el_error_del_email_repetido(self):
        """USR-MOD-USR regla 3: el email de otra cuenta se rechaza con el error junto al campo, el
        formulario conserva lo escrito y no se guarda nada."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)
        crear_cuenta(Vendedor, "otra@infoponia.com")

        respuesta = self.client.post(
            reverse("core:usuario_modificar", args=[cuenta.pk]),
            {"nombre": "Lucía", "apellido": "Gómez", "email": "otra@infoponia.com"},
        )

        self.assertContains(respuesta, MENSAJE_EMAIL_REPETIDO)
        self.assertContains(respuesta, 'value="Lucía"')
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.first_name, "Laura")

    def test_regla_9_modificar_muestra_el_error_del_telefono(self):
        """USR-MOD-USR regla 9 y D-21: el error del teléfono aparece al confirmar, junto al campo; el
        formulario inicial no muestra errores."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz)
        url = reverse("core:usuario_modificar", args=[cuenta.pk])

        inicial = self.client.get(url)
        respuesta = self.client.post(
            url, {"nombre": "Laura", "apellido": "Benítez", "email": "laura@infoponia.com", "telefono": "12ab"}
        )

        self.assertNotContains(inicial, 'class="err"')
        self.assertContains(respuesta, "El teléfono solo puede tener números")
        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).telefono, "")

    def test_d28_modifica_los_datos_de_una_cuenta_inactiva_y_sigue_inactiva(self):
        """D-28: desde la pantalla se corrigen los datos de una cuenta inactiva y la cuenta sigue inactiva
        (no se reactiva sola)."""
        self.entrar_como_gerente()
        cuenta = crear_cuenta(Capataz, activo=False)

        self.client.post(
            reverse("core:usuario_modificar", args=[cuenta.pk]),
            {"nombre": "Laura", "apellido": "Gómez", "email": "laura@infoponia.com"},
        )

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.last_name, "Gómez")
        self.assertFalse(cuenta.is_active)

    def test_seg13_modificar_fuera_de_alcance_recibe_403(self):
        """SEG-13 y USR-MOD-USR regla 1: modificar, restablecer o reactivar la cuenta de un Administrador
        o de otro Gerente da 403 con el mensaje, tanto al abrir la pantalla como al enviar; un Capataz
        recibe 403 en las tres; nada cambia."""
        self.entrar_como_gerente()
        administrador = crear_administrador()
        anterior = crear_gerente(email="anterior@infoponia.com", activo=False)

        for cuenta in (administrador, anterior):
            for nombre_url in ("usuario_modificar", "usuario_restablecer", "usuario_reactivar"):
                url = reverse(f"core:{nombre_url}", args=[cuenta.pk])
                for metodo in (self.client.get, self.client.post):
                    with self.subTest(cuenta=cuenta.email, url=nombre_url, metodo=metodo.__name__):
                        self.assertContains(
                            metodo(url), "Esa cuenta no está dentro de las que gestionás.", status_code=403
                        )
        administrador.refresh_from_db()
        self.assertTrue(administrador.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

        self.client.force_login(crear_cuenta(Capataz, "capataz@infoponia.com"))
        objetivo = crear_cuenta(Vendedor, "vendedor@infoponia.com")
        for nombre_url in ("usuario_modificar", "usuario_restablecer", "usuario_reactivar"):
            with self.subTest(rol="capataz", url=nombre_url):
                respuesta = self.client.post(reverse(f"core:{nombre_url}", args=[objetivo.pk]))
                self.assertContains(respuesta, "Tu cuenta de Capataz no tiene acceso", status_code=403)
