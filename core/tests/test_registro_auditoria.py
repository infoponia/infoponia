# Pruebas del registro de auditoría (D-22): se usa desde los servicios de todos los casos de uso que
# auditan (SEG-14), así que sus reglas propias se prueban acá, aparte de cada caso de uso. Cada prueba
# arma sus propios datos.

from django.test import TestCase

from core.models import (
    Capataz,
    RegistroAuditoria,
    RegistroAuditoriaInmutableError,
    Usuario,
)

CLAVE = "clave-segura-123"


def crear_capataz(email="capataz@infoponia.com"):
    """Crea un Capataz activo con la contraseña de prueba."""
    return Capataz.objects.create_user(
        email=email, password=CLAVE, first_name="Juan", last_name="Pérez"
    )


def crear_administrador(email="admin@infoponia.com"):
    """Crea un Administrador (superusuario sin rol, D-10)."""
    return Usuario.objects.create_superuser(
        email=email, password=CLAVE, first_name="Nora", last_name="Correa"
    )


def registrar(usuario, afectados, detalle=None):
    """Registra una modificación de cuenta de ejemplo y devuelve el registro."""
    return RegistroAuditoria.objects.registrar(
        usuario=usuario,
        accion=RegistroAuditoria.Accion.MODIFICACION,
        afectados=afectados,
        detalle=detalle if detalle is not None else {"telefono": ["", "1155554444"]},
    )


class RegistroAuditoriaTests(TestCase):
    """Reglas del registro de auditoría (D-22, SEG-02 y SEG-14)."""

    def test_d22_guarda_el_rol_del_momento(self):
        """D-22 y D-10: el registro guarda la cuenta que actuó y el rol con el que operaba en ese
        momento; el Administrador queda como «administrador»."""
        capataz = crear_capataz()
        administrador = crear_administrador()

        for usuario, rol in ((capataz, "capataz"), (administrador, "administrador")):
            with self.subTest(rol=rol):
                registro = registrar(usuario, afectados=[capataz])

                registro.refresh_from_db()
                self.assertEqual(registro.usuario_id, usuario.pk)
                self.assertEqual(registro.rol, rol)
                self.assertEqual(registro.accion, RegistroAuditoria.Accion.MODIFICACION)
                self.assertIsNotNone(registro.fecha_hora)

    def test_d22_identifica_las_cuentas_afectadas_como_usuario(self):
        """D-22: guarda el identificador de cada cuenta afectada. Una cuenta se anota siempre como
        «core.usuario», aunque se pase la instancia del rol (Capataz), para poder buscar todos los
        registros de una cuenta por su id."""
        capataz = crear_capataz()
        otra = crear_capataz(email="otra@infoponia.com")
        usuario_base = Usuario.objects.get(pk=otra.pk)

        registro = registrar(capataz, afectados=[capataz, usuario_base])

        registro.refresh_from_db()
        self.assertEqual(
            registro.afectados,
            [
                {"modelo": "core.usuario", "id": capataz.pk},
                {"modelo": "core.usuario", "id": otra.pk},
            ],
        )

    def test_d22_accion_de_infoponia_sin_usuario_guarda_rol_infoponia(self):
        """D-22 (por ejemplo, MD-62): una acción que hace InfoPonia, sin una cuenta que actúe, se
        registra sin usuario y con el rol «infoponia»."""
        capataz = crear_capataz()

        registro = registrar(None, afectados=[capataz])

        registro.refresh_from_db()
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.rol, "infoponia")

    def test_d22_registro_no_se_modifica(self):
        """D-22: al registro solo se le agregan filas; una fila guardada no se modifica, ni desde la
        instancia ni con ``update()``."""
        capataz = crear_capataz()
        registro = registrar(capataz, afectados=[capataz])

        with self.subTest("save() de una fila existente"):
            registro.detalle = {"telefono": ["", "otro"]}
            with self.assertRaises(RegistroAuditoriaInmutableError):
                registro.save()

        with self.subTest("update() del queryset"):
            with self.assertRaises(RegistroAuditoriaInmutableError):
                RegistroAuditoria.objects.filter(pk=registro.pk).update(rol="gerente")

        registro.refresh_from_db()
        self.assertEqual(registro.detalle, {"telefono": ["", "1155554444"]})
        self.assertEqual(registro.rol, "capataz")

    def test_d22_registro_no_se_borra(self):
        """D-22: una fila del registro no se borra, ni desde la instancia ni desde el queryset."""
        capataz = crear_capataz()
        registro = registrar(capataz, afectados=[capataz])

        with self.subTest("delete() de la instancia"):
            with self.assertRaises(RegistroAuditoriaInmutableError):
                registro.delete()

        with self.subTest("delete() del queryset"):
            with self.assertRaises(RegistroAuditoriaInmutableError):
                RegistroAuditoria.objects.all().delete()

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())

    def test_d22_rechaza_detalle_con_contrasenas(self):
        """D-22, SEG-02 y SEG-14: ninguna contraseña queda en la auditoría. Un detalle con una clave
        que nombra una contraseña se rechaza y no se crea el registro."""
        capataz = crear_capataz()

        for clave in ("contrasena", "contrasena_nueva", "password", "Password_hash"):
            with self.subTest(clave=clave):
                with self.assertRaises(ValueError):
                    registrar(capataz, afectados=[capataz], detalle={clave: "algo"})

        self.assertFalse(RegistroAuditoria.objects.exists())
