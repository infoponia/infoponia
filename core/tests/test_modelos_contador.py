# Pruebas del modelo Contador (USR-11, D-85 puntos 1 y 2): la restricción de un solo activo, el respaldo de formulario,
# el rol fijo y que el rol nuevo lo reconozcan la auditoría y la lista de roles operativos.

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import ROLES_OPERATIVOS, Contador, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_cuenta


class ModeloContadorTests(TestCase):
    """D-85: el rol Contador, único activo a la vez."""

    def test_d85_la_restriccion_rechaza_un_segundo_contador_activo(self):
        """D-85 punto 2: la base rechaza un segundo Contador activo y deja uno inactivo."""
        crear_cuenta(Contador, email="c1@infoponia.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                crear_cuenta(Contador, email="c2@infoponia.com")

        inactivo = crear_cuenta(Contador, email="c3@infoponia.com", activo=False)
        self.assertIsNotNone(inactivo.pk)

    def test_d85_clean_rechaza_segundo_activo_y_deja_inactivo(self):
        """D-85 punto 2: ``full_clean`` rechaza un segundo Contador activo (respaldo de formulario)."""
        crear_cuenta(Contador, email="c1@infoponia.com")

        segundo = Contador(email="c2@infoponia.com", first_name="C", last_name="D", is_active=True)
        segundo.set_password("clave12345")
        with self.assertRaises(ValidationError):
            segundo.full_clean()

        inactivo = Contador(email="c3@infoponia.com", first_name="E", last_name="F", is_active=False)
        inactivo.set_password("clave12345")
        inactivo.full_clean()

    def test_d85_el_rol_queda_fijo(self):
        """D-85 punto 1 y D-11: el rol se fija al guardar, aunque se lo intente pisar."""
        cuenta = Contador(email="c1@infoponia.com", first_name="A", last_name="B", rol="capataz")
        cuenta.set_password("clave12345")
        cuenta.save()

        self.assertEqual(Usuario.objects.get(pk=cuenta.pk).rol, Usuario.Rol.CONTADOR)

    def test_d85_roles_operativos_y_auditoria_lo_incluyen(self):
        """D-85 punto 1 y D-36: el Contador es un rol operativo y la auditoría lo muestra con su nombre."""
        self.assertIn("contador", ROLES_OPERATIVOS)
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["rol"]["contador"], "Contador")
