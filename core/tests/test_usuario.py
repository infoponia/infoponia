# Pruebas del modelo de usuario propio (D-01 a D-03, D-09 a D-11). Cada prueba arma sus
# propios datos, como pide CLAUDE.md.

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.admin import UsuarioAdmin
from core.models import Capataz, Gerente, Usuario


class UsuarioTests(TestCase):
    def test_d01_crear_capataz_asigna_rol_y_tablas(self):
        """D-01: crear un Capataz asigna el rol y crea las filas de Usuario y Capataz (docs/decisiones.md)."""
        capataz = Capataz.objects.create_user(
            email="capataz@infoponia.com",
            password="clave12345",
            first_name="Juan",
            last_name="Perez",
        )

        self.assertEqual(capataz.rol, Usuario.Rol.CAPATAZ)
        self.assertTrue(Usuario.objects.filter(pk=capataz.pk).exists())
        self.assertTrue(Capataz.objects.filter(pk=capataz.pk).exists())

    def test_d02_usuario_inactivo_no_autentica(self):
        """D-02: un usuario inactivo no puede autenticarse (docs/decisiones.md)."""
        Capataz.objects.create_user(
            email="inactivo@infoponia.com",
            password="clave12345",
            first_name="A",
            last_name="B",
            is_active=False,
        )

        self.assertIsNone(authenticate(email="inactivo@infoponia.com", password="clave12345"))

    def test_d03_email_unico_rechaza_duplicado(self):
        """D-03: el email es único; un segundo usuario con el mismo email falla (docs/decisiones.md)."""
        Capataz.objects.create_user(
            email="dup@infoponia.com", password="clave12345", first_name="A", last_name="B"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Capataz.objects.create_user(
                    email="dup@infoponia.com",
                    password="clave12345",
                    first_name="C",
                    last_name="D",
                )

    def test_d03_create_user_sin_email_falla(self):
        """D-03: el email es obligatorio; create_user sin email falla (docs/decisiones.md)."""
        with self.assertRaises(ValueError):
            Usuario.objects.create_user(email="", password="clave12345")

    def test_d09_un_solo_gerente_activo(self):
        """D-09: un solo Gerente activo (docs/decisiones.md)."""
        Gerente.objects.create_user(
            email="gerente1@infoponia.com",
            password="clave12345",
            first_name="A",
            last_name="B",
            is_active=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Gerente.objects.create_user(
                    email="gerente2@infoponia.com",
                    password="clave12345",
                    first_name="C",
                    last_name="D",
                    is_active=True,
                )

        gerente_inactivo = Gerente.objects.create_user(
            email="gerente3@infoponia.com",
            password="clave12345",
            first_name="E",
            last_name="F",
            is_active=False,
        )
        self.assertIsNotNone(gerente_inactivo.pk)

    def test_d09_gerente_clean_rechaza_segundo_activo(self):
        """D-09: un solo Gerente activo; full_clean rechaza un segundo Gerente activo (docs/decisiones.md)."""
        Gerente.objects.create_user(
            email="g1@infoponia.com",
            password="clave12345",
            first_name="A",
            last_name="B",
            is_active=True,
        )

        segundo_activo = Gerente(email="g2@infoponia.com", first_name="C", last_name="D", is_active=True)
        segundo_activo.set_password("clave12345")
        with self.assertRaises(ValidationError):
            segundo_activo.full_clean()

        segundo_inactivo = Gerente(email="g3@infoponia.com", first_name="E", last_name="F", is_active=False)
        segundo_inactivo.set_password("clave12345")
        segundo_inactivo.full_clean()

    def test_d10_create_superuser_es_administrador_sin_rol(self):
        """D-10: create_superuser crea un Administrador sin rol de negocio (docs/decisiones.md)."""
        admin = Usuario.objects.create_superuser(
            email="admin@infoponia.com",
            password="clave12345",
            first_name="Admin",
            last_name="Tecnico",
        )

        self.assertEqual(admin.rol, "")
        self.assertTrue(admin.is_superuser)
        self.assertIsNotNone(authenticate(email="admin@infoponia.com", password="clave12345"))

    def test_d10_usuario_sin_rol_no_se_guarda(self):
        """D-10: un usuario sin rol y sin ser superusuario no puede guardarse (docs/decisiones.md)."""
        usuario = Usuario(email="sinrol@infoponia.com", first_name="A", last_name="B", rol="")
        usuario.set_password("clave12345")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                usuario.save()

    def test_d10_gerente_no_es_staff(self):
        """D-10: un Gerente normal (no Administrador) no es staff (docs/decisiones.md)."""
        gerente = Gerente.objects.create_user(
            email="gerentestaff@infoponia.com",
            password="clave12345",
            first_name="A",
            last_name="B",
        )

        self.assertFalse(gerente.is_staff)

    def test_d11_rol_no_se_modifica_desde_el_admin(self):
        """D-11: el rol no se modifica desde el admin (docs/decisiones.md)."""
        self.assertIn("rol", UsuarioAdmin.readonly_fields)
