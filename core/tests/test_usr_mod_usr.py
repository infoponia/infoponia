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
# Tarea 05b (D-16, D-30): el Administrador usa los mismos servicios con su alcance. Restablecer su propia
# contraseña lanza ValidationError con el código «propia_cuenta» (regla 4); reactivar un Gerente con otro
# activo, «gerente_activo» (regla 5); si la base rechaza la reactivación por una restricción que no se
# puede identificar, ValidationError con el código «no_se_pudo_reactivar» (nunca un error 500).
# Tarea 06b (D-17, SEG-11): restablecer y reactivar sacan la cuenta de su grupo de cuentas vinculadas, y el
# registro de auditoría agrega ``sale_del_grupo`` (id del grupo) solo si la cuenta estaba en uno; si el
# grupo se disolvió, la cuenta que quedaba sola figura también entre las afectadas.

from unittest import mock

from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import Http404
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from core import servicios
from core.models import (
    ADMINISTRADOR,
    Capataz,
    Gerente,
    GrupoCuentas,
    RegistroAuditoria,
    Usuario,
    Vendedor,
)
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import (
    CLAVE,
    agrupar,
    contenido_de_auditoria,
    crear_administrador,
    crear_cuenta,
    crear_gerente,
    dar_temporal_vencida,
)

# Estas pruebas verifican «Laura Benítez» como nombre de la cuenta: se pasa explícito a crear_cuenta.
LAURA = {"nombre": "Laura", "apellido": "Benítez"}
MENSAJE_EMAIL_REPETIDO = "Ya existe una cuenta con ese email."


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


class UsrModUsrServicioTests(TestCase):
    """Reglas, precondiciones y postcondiciones de USR-MOD-USR en los servicios de modificación."""

    def modificar(self, actor, cuenta, **cambios):
        """Llama a ``modificar_usuario`` con los datos actuales de la cuenta, pisados por ``cambios``."""
        return servicios.modificar_usuario(actor, cuenta.pk, **datos_validos(cuenta, **cambios))

    # ---- Precondiciones ----

    def test_pre_a_rechaza_actor_sin_cuenta_activa_de_gerente(self):
        """USR-MOD-USR precondición a: modifica una cuenta activa de Gerente o de Administrador (las del
        Administrador están más abajo). Un Capataz o un Gerente dado de baja no pueden, en ninguna de las
        tres operaciones."""
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com", **LAURA)
        gerente_inactivo = crear_gerente(activo=False)
        objetivo = crear_cuenta(Vendedor, "vendedor@infoponia.com", **LAURA)
        inactiva = crear_cuenta(Vendedor, "inactiva@infoponia.com", activo=False, **LAURA)

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
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)
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
        cuenta = crear_cuenta(Capataz, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)

        self.modificar(gerente, cuenta, email="  Laura.Nueva@Infoponia.com ")

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.email, "laura.nueva@infoponia.com")

    def test_regla_3_rechaza_email_de_otra_cuenta(self):
        """USR-MOD-USR regla 3 y precondición c: el email nuevo no puede ser el de otra cuenta
        (también con otras mayúsculas, SEG-01), activa o inactiva."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, **LAURA)
        crear_cuenta(Vendedor, "otra@infoponia.com", **LAURA)
        crear_cuenta(Vendedor, "inactiva@infoponia.com", activo=False, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)

        self.modificar(gerente, cuenta, nombre="Lucía", email="LAURA@infoponia.com")

        cuenta.refresh_from_db()
        self.assertEqual(cuenta.first_name, "Lucía")
        self.assertEqual(cuenta.email, "laura@infoponia.com")

    def test_regla_4_restablecer_genera_temporal_nueva(self):
        """USR-MOD-USR regla 4, postcondición b y SEG-04: restablecer genera una contraseña temporal
        (la elige el Sistema, no quien restablece); la contraseña anterior deja de servir."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, **LAURA)

        with self.assertRaises(TypeError):
            servicios.restablecer_contrasena(gerente, cuenta.pk, contrasena="mi-clave-elegida-1")
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password(CLAVE))

    def test_seg04_restablecer_renueva_una_temporal_vencida(self):
        """SEG-04: una temporal vencida no sirve para identificarse y quien gestiona la cuenta tiene que
        restablecerla: restablecer una cuenta con temporal vencida le da una vigente."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)

        servicios.reactivar_usuario(gerente, cuenta.pk)

        self.assertTrue(Usuario.objects.get(pk=cuenta.pk).is_active)

    def test_post_d_modificacion_audita_los_cambios(self):
        """USR-MOD-USR postcondición d, SEG-14 y D-22: queda un registro de auditoría con quién actuó,
        su rol, la acción, la cuenta y solo los campos que cambiaron, con su valor antes y después."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, telefono="", **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)

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
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)

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

    # ---- Cuentas vinculadas (tarea 06b): SEG-11, postcondición b y regla 3 ----

    def test_seg11_restablecer_saca_la_cuenta_de_su_grupo(self):
        """USR-MOD-USR postcondición b y SEG-11: al restablecer la contraseña, la cuenta sale de su grupo de
        cuentas vinculadas (la persona perdió el control: su dueño la recupera con la temporal). Las demás
        cuentas del grupo siguen juntas."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, **LAURA)
        otra = crear_cuenta(Vendedor, "otra@infoponia.com", **LAURA)
        tercera = crear_cuenta(Vendedor, "tercera@infoponia.com", **LAURA)
        grupo = agrupar(cuenta, otra, tercera)

        servicios.restablecer_contrasena(gerente, cuenta.pk)

        self.assertIsNone(Usuario.objects.get(pk=cuenta.pk).grupo_id)
        self.assertEqual(Usuario.objects.get(pk=otra.pk).grupo_id, grupo.pk)
        self.assertEqual(Usuario.objects.get(pk=tercera.pk).grupo_id, grupo.pk)

    def test_seg11_reactivar_saca_la_cuenta_de_su_grupo(self):
        """USR-MOD-USR postcondición c y SEG-11: la reactivación restablece la contraseña como en la
        postcondición b, así que la cuenta también sale de su grupo (la baja no la había sacado: regla 2 de
        USR-BAJ-USR). Las demás siguen juntas."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)
        otra = crear_cuenta(Vendedor, "otra@infoponia.com", **LAURA)
        tercera = crear_cuenta(Vendedor, "tercera@infoponia.com", **LAURA)
        grupo = agrupar(cuenta, otra, tercera)

        servicios.reactivar_usuario(gerente, cuenta.pk)

        self.assertIsNone(Usuario.objects.get(pk=cuenta.pk).grupo_id)
        self.assertEqual(Usuario.objects.get(pk=otra.pk).grupo_id, grupo.pk)
        self.assertEqual(Usuario.objects.get(pk=tercera.pk).grupo_id, grupo.pk)

    def test_seg11_restablecer_disuelve_un_grupo_de_dos(self):
        """USR-MOD-USR postcondición b, SEG-11 y postcondición b de USR-VNC-CTA: si el grupo queda con una
        sola cuenta, el grupo deja de existir y esa cuenta queda sin grupo."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, **LAURA)
        otra = crear_cuenta(Vendedor, "otra@infoponia.com", **LAURA)
        agrupar(cuenta, otra)

        servicios.restablecer_contrasena(gerente, cuenta.pk)

        self.assertIsNone(Usuario.objects.get(pk=cuenta.pk).grupo_id)
        self.assertIsNone(Usuario.objects.get(pk=otra.pk).grupo_id)
        self.assertFalse(GrupoCuentas.objects.exists())

    def test_post_d_la_auditoria_registra_la_salida_del_grupo(self):
        """USR-MOD-USR postcondición d y SEG-14: si la cuenta estaba en un grupo, el registro lo indica
        (``sale_del_grupo``) para el restablecimiento y para la reactivación. Si el grupo se disolvió, la
        cuenta que quedaba sola figura también entre las afectadas. Sin grupo, el registro no cambia."""
        gerente = crear_gerente()
        restablecida = crear_cuenta(Capataz, "restablecida@infoponia.com", **LAURA)
        companera_1 = crear_cuenta(Vendedor, "c1@infoponia.com", **LAURA)
        companera_2 = crear_cuenta(Vendedor, "c2@infoponia.com", **LAURA)
        reactivada = crear_cuenta(Capataz, "reactivada@infoponia.com", activo=False, **LAURA)
        sola = crear_cuenta(Vendedor, "sola@infoponia.com", **LAURA)
        grupo_de_tres = agrupar(restablecida, companera_1, companera_2)
        grupo_de_dos = agrupar(reactivada, sola)

        servicios.restablecer_contrasena(gerente, restablecida.pk)
        servicios.reactivar_usuario(gerente, reactivada.pk)

        restablecimiento = RegistroAuditoria.objects.get(
            accion=RegistroAuditoria.Accion.RESTABLECIMIENTO
        )
        self.assertEqual(restablecimiento.afectados, [{"modelo": "core.usuario", "id": restablecida.pk}])
        self.assertEqual(restablecimiento.detalle, {"sale_del_grupo": grupo_de_tres.pk})
        reactivacion = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.REACTIVACION)
        self.assertEqual(
            {a["id"] for a in reactivacion.afectados}, {reactivada.pk, sola.pk}
        )
        self.assertEqual(
            reactivacion.detalle,
            {"estado": ["inactivo", "activo"], "sale_del_grupo": grupo_de_dos.pk},
        )

    def test_regla_3_cambiar_el_email_no_afecta_las_cuentas_vinculadas(self):
        """USR-MOD-USR regla 3: cambiar el email no afecta las cuentas vinculadas; la cuenta sigue en su
        grupo, con las mismas compañeras."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, **LAURA)
        otra = crear_cuenta(Vendedor, "otra@infoponia.com", **LAURA)
        grupo = agrupar(cuenta, otra)

        self.modificar(gerente, cuenta, email="nuevo@infoponia.com")

        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).email, "nuevo@infoponia.com")
        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).grupo_id, grupo.pk)
        self.assertEqual(Usuario.objects.get(pk=otra.pk).grupo_id, grupo.pk)

    # ---- Decisiones D-22 y D-28 ----

    def test_d28_sin_cambios_no_guarda_ni_audita(self):
        """D-28: si el formulario se envía sin cambios (también si solo difieren espacios o mayúsculas
        del email), no se guarda nada y no queda un registro de auditoría vacío."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, telefono="+54 376 400-1001", **LAURA)

        self.modificar(gerente, cuenta)
        self.modificar(gerente, cuenta, nombre=" Laura ", email=" LAURA@infoponia.com ")

        self.assertEqual(RegistroAuditoria.objects.count(), 0)
        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).first_name, "Laura")

    def test_d28_restablecer_rechaza_cuenta_inactiva(self):
        """D-28: restablecer solo vale para cuentas activas (una inactiva se reactiva); no cambia nada."""
        gerente = crear_gerente()
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)

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
        activa = crear_cuenta(Capataz, **LAURA)
        inactiva = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False, **LAURA)

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


    # ---- El Administrador (tarea 05b, D-16) ----

    def test_pre_a_rechaza_administrador_inactivo(self):
        """USR-MOD-USR precondición a: un Administrador dado de baja no modifica, no restablece ni
        reactiva; no cambia nada ni se audita."""
        crear_administrador()
        inactivo = crear_administrador(email="admin.anterior@infoponia.com")
        inactivo.is_active = False
        inactivo.save()
        gerente = crear_gerente()
        gerente_inactivo = crear_gerente(email="gerente.anterior@infoponia.com", activo=False)

        with self.assertRaises(PermissionDenied):
            self.modificar(inactivo, gerente, nombre="Otro")
        with self.assertRaises(PermissionDenied):
            servicios.restablecer_contrasena(inactivo, gerente.pk)
        with self.assertRaises(PermissionDenied):
            servicios.reactivar_usuario(inactivo, gerente_inactivo.pk)

        gerente.refresh_from_db()
        self.assertEqual(gerente.first_name, "Gabriela")
        self.assertFalse(Usuario.objects.get(pk=gerente_inactivo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_1_administrador_modifica_gerente_y_administradores_incluida_la_suya(self):
        """USR-MOD-USR regla 1, postcondiciones a y d, y D-16: el Administrador modifica los datos de la
        cuenta del Gerente, la de otro Administrador y la suya; cada modificación queda auditada con su
        rol («administrador»)."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        gerente = crear_gerente()

        for cuenta in (gerente, otro_administrador, administrador):
            with self.subTest(cuenta=cuenta.email):
                self.modificar(administrador, cuenta, nombre="Nuevo")
                self.assertEqual(Usuario.objects.get(pk=cuenta.pk).first_name, "Nuevo")

        registros = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION)
        self.assertEqual(registros.count(), 3)
        self.assertEqual({r.rol for r in registros}, {ADMINISTRADOR})
        self.assertEqual({r.usuario_id for r in registros}, {administrador.pk})

    def test_regla_1_administrador_no_modifica_otros_roles(self):
        """USR-MOD-USR regla 1 y D-16: las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico
        las gestiona el Gerente; para el Administrador están fuera del alcance en las tres operaciones."""
        administrador = crear_administrador()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com", **LAURA)
        vendedor_inactivo = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False, **LAURA)

        with self.assertRaises(PermissionDenied):
            self.modificar(administrador, capataz, nombre="Otro")
        with self.assertRaises(PermissionDenied):
            servicios.restablecer_contrasena(administrador, capataz.pk)
        with self.assertRaises(PermissionDenied):
            servicios.reactivar_usuario(administrador, vendedor_inactivo.pk)

        capataz.refresh_from_db()
        self.assertEqual(capataz.first_name, "Laura")
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertFalse(Usuario.objects.get(pk=vendedor_inactivo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_4_administrador_no_restablece_su_propia_contrasena(self):
        """USR-MOD-USR regla 4: para su propia cuenta, el Administrador usa USR-CMB-CTR; restablecerla se
        rechaza (código «propia_cuenta») aunque haya otro Administrador, y la contraseña no cambia."""
        administrador = crear_administrador()
        crear_administrador(email="admin2@infoponia.com")

        with self.assertRaises(ValidationError) as contexto:
            servicios.restablecer_contrasena(administrador, administrador.pk)

        self.assertEqual(contexto.exception.code, "propia_cuenta")
        administrador.refresh_from_db()
        self.assertTrue(administrador.check_password(CLAVE))
        self.assertFalse(administrador.tiene_contrasena_temporal)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_4_administrador_restablece_la_de_otro_administrador_y_la_del_gerente(self):
        """USR-MOD-USR regla 4, postcondiciones b y d, SEG-04 y D-16: el Administrador restablece la
        contraseña de la cuenta del Gerente y de otro Administrador; la temporal vale, la anterior deja
        de valer y la auditoría no guarda contraseñas."""
        administrador = crear_administrador()
        otro_administrador = crear_administrador(email="admin2@infoponia.com")
        gerente = crear_gerente()

        for cuenta in (gerente, otro_administrador):
            with self.subTest(cuenta=cuenta.email):
                temporal = servicios.restablecer_contrasena(administrador, cuenta.pk)
                guardada = Usuario.objects.get(pk=cuenta.pk)
                self.assertTrue(guardada.check_password(temporal))
                self.assertFalse(guardada.check_password(CLAVE))
                self.assertTrue(guardada.tiene_contrasena_temporal)

        registros = RegistroAuditoria.objects.filter(
            accion=RegistroAuditoria.Accion.RESTABLECIMIENTO
        )
        self.assertEqual(registros.count(), 2)
        self.assertEqual({r.rol for r in registros}, {ADMINISTRADOR})
        for registro in registros:
            cuenta = Usuario.objects.get(pk=registro.afectados[0]["id"])
            self.assertNotIn(cuenta.password, contenido_de_auditoria(registro))

    def test_regla_1_administrador_reactiva_a_otro_administrador(self):
        """USR-MOD-USR regla 1, regla 6 y D-16: el Administrador reactiva la cuenta de un Administrador
        dado de baja, aunque haya un Gerente activo (la regla 5 es solo del Gerente); queda activa con una
        contraseña temporal nueva."""
        administrador = crear_administrador()
        inactivo = crear_administrador(email="admin2@infoponia.com")
        inactivo.is_active = False
        inactivo.save()
        crear_gerente()

        temporal = servicios.reactivar_usuario(administrador, inactivo.pk)

        guardada = Usuario.objects.get(pk=inactivo.pk)
        self.assertTrue(guardada.is_active)
        self.assertTrue(guardada.check_password(temporal))
        self.assertTrue(guardada.tiene_contrasena_temporal)

    def test_regla_5_rechaza_reactivar_gerente_con_otro_activo(self):
        """USR-MOD-USR regla 5 y D-09: no se reactiva un Gerente si hay otro activo; el error lleva el
        código «gerente_activo» y explica que hay que dar de baja al actual. La cuenta sigue inactiva, su
        contraseña no cambia y no se audita nada."""
        administrador = crear_administrador()
        crear_gerente()
        inactivo = crear_gerente(email="gerente.anterior@infoponia.com", activo=False)
        clave_anterior = inactivo.password

        with self.assertRaises(ValidationError) as contexto:
            servicios.reactivar_usuario(administrador, inactivo.pk)

        self.assertEqual(contexto.exception.code, "gerente_activo")
        self.assertIn("reactivar", contexto.exception.messages[0])
        inactivo.refresh_from_db()
        self.assertFalse(inactivo.is_active)
        self.assertEqual(inactivo.password, clave_anterior)
        self.assertEqual(Gerente.objects.filter(is_active=True).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_5_reactiva_gerente_sin_otro_activo(self):
        """USR-MOD-USR regla 5, regla 6, postcondiciones c y d: sin otro Gerente activo, el Administrador
        reactiva la cuenta del Gerente; queda activa con una temporal nueva y la reactivación se audita
        con su rol («administrador») y el cambio de estado."""
        administrador = crear_administrador()
        inactivo = crear_gerente(activo=False)

        temporal = servicios.reactivar_usuario(administrador, inactivo.pk)

        guardada = Usuario.objects.get(pk=inactivo.pk)
        self.assertTrue(guardada.is_active)
        self.assertTrue(guardada.check_password(temporal))
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, RegistroAuditoria.Accion.REACTIVACION)
        self.assertEqual(registro.rol, ADMINISTRADOR)
        self.assertEqual(registro.afectados, [{"modelo": "core.usuario", "id": inactivo.pk}])
        self.assertEqual(registro.detalle, {"estado": ["inactivo", "activo"]})

    def test_regla_5_integrity_error_de_un_solo_gerente_activo_da_gerente_activo(self):
        """USR-MOD-USR regla 5 y SEG-15 (D-30): si la base rechaza la reactivación por la restricción
        ``un_solo_gerente_activo`` (otra operación ganó de mano), se informa como «gerente_activo»; nunca
        llega un ``IntegrityError`` a la pantalla (sería un error 500)."""
        administrador = crear_administrador()
        inactivo = crear_gerente(activo=False)
        error = IntegrityError("falla simulada")
        error.__cause__ = Exception("error del driver")
        error.__cause__.diag = SimpleNamespace(constraint_name="un_solo_gerente_activo")

        with mock.patch.object(Usuario, "save", side_effect=error):
            with self.assertRaises(ValidationError) as contexto:
                servicios.reactivar_usuario(administrador, inactivo.pk)

        self.assertEqual(contexto.exception.code, "gerente_activo")
        self.assertIs(contexto.exception.__cause__, error)
        self.assertFalse(Usuario.objects.get(pk=inactivo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_regla_5_integrity_error_sin_nombre_de_restriccion_da_error_de_validacion(self):
        """USR-MOD-USR regla 5 y SEG-15 (D-30): si la base rechaza la reactivación y no se puede leer qué
        restricción falló (sin causa, sin ``diag`` o sin nombre), se informa un ``ValidationError``
        genérico (código «no_se_pudo_reactivar»); nunca llega un ``IntegrityError`` (error 500)."""
        administrador = crear_administrador()
        inactivo = crear_gerente(activo=False)
        sin_causa = IntegrityError("falla simulada")
        sin_diag = IntegrityError("falla simulada")
        sin_diag.__cause__ = Exception("error del driver sin diag")
        sin_nombre = IntegrityError("falla simulada")
        sin_nombre.__cause__ = Exception("error del driver sin nombre de restricción")
        sin_nombre.__cause__.diag = SimpleNamespace(constraint_name=None)

        casos = (("sin causa", sin_causa), ("sin diag", sin_diag), ("sin nombre", sin_nombre))
        for nombre, error in casos:
            with self.subTest(caso=nombre):
                with mock.patch.object(Usuario, "save", side_effect=error):
                    with self.assertRaises(ValidationError) as contexto:
                        servicios.reactivar_usuario(administrador, inactivo.pk)
                self.assertEqual(contexto.exception.code, "no_se_pudo_reactivar")
                self.assertFalse(Usuario.objects.get(pk=inactivo.pk).is_active)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)


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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        activa = crear_cuenta(Capataz, **LAURA)
        inactiva = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False, **LAURA)

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
        activa = crear_cuenta(Capataz, **LAURA)
        inactiva = crear_cuenta(Vendedor, "vendedor@infoponia.com", activo=False, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)
        crear_cuenta(Vendedor, "otra@infoponia.com", **LAURA)

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
        cuenta = crear_cuenta(Capataz, **LAURA)
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
        cuenta = crear_cuenta(Capataz, activo=False, **LAURA)

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

        self.client.force_login(crear_cuenta(Capataz, "capataz@infoponia.com", **LAURA))
        objetivo = crear_cuenta(Vendedor, "vendedor@infoponia.com", **LAURA)
        for nombre_url in ("usuario_modificar", "usuario_restablecer", "usuario_reactivar"):
            with self.subTest(rol="capataz", url=nombre_url):
                respuesta = self.client.post(reverse(f"core:{nombre_url}", args=[objetivo.pk]))
                self.assertContains(respuesta, "Tu cuenta de Capataz no tiene acceso", status_code=403)

    # ---- El Administrador (tarea 05b, D-16 y D-30) ----

    def entrar_como_administrador(self):
        """Crea un Administrador, abre su sesión en ``self.client`` y lo devuelve."""
        administrador = crear_administrador()
        self.client.force_login(administrador)
        return administrador

    def test_flujo_principal_administrador_modifica_sus_propios_datos(self):
        """USR-MOD-USR flujo principal, regla 1, postcondiciones a y d, y D-16: el Administrador corrige sus
        propios datos desde la ficha: el formulario muestra el rol «Administrador» bloqueado; al guardar,
        vuelve a su ficha con el aviso, sin tocar su contraseña, y queda auditado con su rol."""
        administrador = self.entrar_como_administrador()
        url = reverse("core:usuario_modificar", args=[administrador.pk])

        formulario = self.client.get(url)
        respuesta = self.client.post(
            url,
            {"nombre": "Adriana", "apellido": "Mena", "email": "admin@infoponia.com", "telefono": ""},
            follow=True,
        )

        self.assertContains(formulario, 'value="Administrador"')
        self.assertRedirects(respuesta, reverse("core:usuario", args=[administrador.pk]))
        self.assertContains(respuesta, "Cambios guardados.")
        self.assertContains(respuesta, "(vos)")
        administrador.refresh_from_db()
        self.assertEqual(administrador.first_name, "Adriana")
        self.assertTrue(administrador.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.get().rol, ADMINISTRADOR)

    def test_flujo_principal_administrador_restablece_la_contrasena_del_gerente(self):
        """USR-MOD-USR flujo principal, regla 4 y postcondición b: el Administrador restablece la
        contraseña del Gerente; la ventana le muestra la temporal una sola vez."""
        self.entrar_como_administrador()
        gerente = crear_gerente()

        respuesta = self.client.post(reverse("core:usuario_restablecer", args=[gerente.pk]))

        temporal = respuesta.context["contrasena_temporal"]
        gerente.refresh_from_db()
        self.assertTrue(gerente.check_password(temporal))
        self.assertContains(respuesta, "Contraseña restablecida")
        self.assertContains(respuesta, "(Gerente)")

    def test_regla_4_administrador_no_restablece_su_propia_contrasena_desde_la_pantalla(self):
        """USR-MOD-USR regla 4 y D-30: la ficha propia no ofrece «Restablecer contraseña»; si igual se envía
        el pedido a mano, el servicio lo rechaza, la ventana muestra el motivo y la contraseña no cambia."""
        administrador = self.entrar_como_administrador()
        crear_administrador(email="admin2@infoponia.com")

        ficha = self.client.get(reverse("core:usuario", args=[administrador.pk]))
        envio = self.client.post(reverse("core:usuario_restablecer", args=[administrador.pk]))

        self.assertNotContains(ficha, "Restablecer contraseña")
        self.assertContains(envio, "No se restablece tu propia contraseña")
        self.assertNotIn("contrasena_temporal", envio.context)
        administrador.refresh_from_db()
        self.assertTrue(administrador.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_flujo_principal_administrador_reactiva_al_gerente_si_no_hay_otro_activo(self):
        """USR-MOD-USR flujo principal, regla 5 y regla 6: sin otro Gerente activo, la ventana pide
        confirmar; al confirmar, el Gerente queda activo y se muestra su contraseña temporal."""
        self.entrar_como_administrador()
        inactivo = crear_gerente(activo=False)
        url = reverse("core:usuario_reactivar", args=[inactivo.pk])

        confirmacion = self.client.get(url, headers={"HX-Request": "true"})
        respuesta = self.client.post(url)

        self.assertContains(confirmacion, "¿Reactivar la cuenta?")
        self.assertContains(confirmacion, f'action="{url}"')
        temporal = respuesta.context["contrasena_temporal"]
        inactivo.refresh_from_db()
        self.assertTrue(inactivo.is_active)
        self.assertTrue(inactivo.check_password(temporal))
        self.assertContains(respuesta, "Cuenta reactivada")

    def test_regla_5_reactivar_gerente_con_otro_activo_no_ofrece_confirmar(self):
        """USR-MOD-USR regla 5, D-09 y D-30: con otro Gerente activo, «Reactivar cuenta» se ofrece en la
        ficha, pero la ventana no ofrece confirmar: muestra el motivo, con «Ver a <nombre>» (ficha del
        Gerente activo) y «Cerrar». Vale para el pedido de HTMX y para la página completa. Un POST manual
        lo rechaza el servicio, vuelve a mostrar lo mismo y no cambia nada."""
        self.entrar_como_administrador()
        activo = crear_gerente()
        inactivo = Gerente.objects.create_user(
            email="anterior@infoponia.com",
            password=CLAVE,
            first_name="Mariano",
            last_name="Paz",
            is_active=False,
        )
        url = reverse("core:usuario_reactivar", args=[inactivo.pk])

        ficha = self.client.get(reverse("core:usuario", args=[inactivo.pk]))
        respuestas = {
            "htmx": self.client.get(url, headers={"HX-Request": "true"}),
            "pagina": self.client.get(url),
            "envio manual": self.client.post(url),
        }

        self.assertContains(ficha, "Reactivar cuenta")
        for nombre, respuesta in respuestas.items():
            with self.subTest(pedido=nombre):
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "No se puede reactivar la cuenta")
                self.assertContains(respuesta, "ya hay un Gerente activo, <b>Gabriela Sosa</b>")
                self.assertContains(
                    respuesta,
                    f'<a class="btn btn-primary" href="{reverse("core:usuario", args=[activo.pk])}">'
                    "Ver a Gabriela Sosa</a>",
                    html=True,
                )
                self.assertContains(respuesta, ">Cerrar</a>")
                self.assertNotContains(respuesta, "¿Reactivar la cuenta?")
                self.assertNotContains(respuesta, f'action="{url}"')
        inactivo.refresh_from_db()
        self.assertFalse(inactivo.is_active)
        self.assertTrue(inactivo.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_seg13_administrador_recibe_403_en_las_acciones_sobre_un_capataz(self):
        """SEG-13, USR-MOD-USR regla 1 y D-16: modificar, restablecer, reactivar o dar de baja la cuenta de
        un Capataz está fuera del alcance del Administrador: 403 con el mensaje, y nada cambia."""
        self.entrar_como_administrador()
        capataz = crear_cuenta(Capataz, "capataz@infoponia.com", **LAURA)

        for nombre in ("usuario_modificar", "usuario_restablecer", "usuario_reactivar", "usuario_baja"):
            for metodo in (self.client.get, self.client.post):
                with self.subTest(pantalla=nombre, metodo=metodo.__name__):
                    respuesta = metodo(reverse(f"core:{nombre}", args=[capataz.pk]))
                    self.assertContains(
                        respuesta, "Esa cuenta no está dentro de las que gestionás.", status_code=403
                    )
        capataz.refresh_from_db()
        self.assertTrue(capataz.is_active)
        self.assertTrue(capataz.check_password(CLAVE))
        self.assertEqual(RegistroAuditoria.objects.count(), 0)


class UsrModUsrConcurrenciaTests(TransactionTestCase):
    """SEG-15 en ``reactivar_usuario``: dos reactivaciones simultáneas de Gerentes distintos dejan un solo
    Gerente activo y la segunda recibe un rechazo con mensaje, no un error 500 ni un deadlock. Son
    ``TransactionTestCase`` porque cada operación corre en su propio hilo, con su propia conexión y
    transacción (ver ``core/tests/concurrencia.py``)."""

    def test_seg15_reactivaciones_simultaneas_dejan_un_solo_gerente_activo(self):
        """SEG-15, regla 5 de USR-MOD-USR y D-09: dos Administradores reactivan, a la vez, a dos Gerentes
        anteriores distintos. Se bloquean todas las filas de Gerente antes de mirar si hay uno activo: la
        segunda espera, ve al Gerente que acaba de reactivar la primera y se rechaza con «gerente_activo».
        Camino del bloqueo: el rechazo sale de esa verificación (``__cause__`` vacío), no de traducir la
        restricción de la base; sin el bloqueo, esta prueba falla. Un deadlock (bloquear la cuenta antes
        que el grupo) llegaría como excepción sin traducir y también la hace fallar."""
        primero = crear_administrador()
        segundo = crear_administrador(email="admin2@infoponia.com")
        gerente_1 = crear_gerente(email="gerente1@infoponia.com", activo=False)
        gerente_2 = crear_gerente(email="gerente2@infoponia.com", activo=False)

        resultados = correr_a_la_vez(
            lambda: servicios.reactivar_usuario(primero, gerente_1.pk),
            lambda: servicios.reactivar_usuario(segundo, gerente_2.pk),
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], "ninguna operación puede terminar con un error sin traducir")
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("gerente_activo", codigos(rechazos[0]))
        self.assertIsNone(rechazos[0].__cause__)
        self.assertEqual(Gerente.objects.filter(is_active=True).count(), 1)
        self.assertEqual(
            RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.REACTIVACION).count(), 1
        )
