# Pruebas del modelo TransportistaInvernadero (MAE-05, paso 1; D-55, docs/modelo/maestros.md): la base de datos garantiza
# el 0..1 (un Transportista, una sola fila), nada se borra con una fila de por medio, y Invernadero.transportistas()
# los ordena por apellido y nombre en una sola consulta.

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from maestros.models import TransportistaInvernadero
from maestros.tests.fabricas import ConGeoref, asignar_transportista, crear_invernadero, crear_transportista


class TransportistaInvernaderoModeloTests(ConGeoref, TestCase):
    """El modelo que guarda R155 (D-55, punto 3)."""

    def test_d55_un_transportista_no_puede_tener_dos_filas(self):
        """D-55, punto 3: el OneToOne hace que la base rechace una segunda fila del mismo Transportista."""
        norte = crear_invernadero("Norte")
        sur = crear_invernadero("Sur")
        transportista = crear_transportista()
        asignar_transportista(transportista, norte)

        with self.assertRaises(IntegrityError), transaction.atomic():
            asignar_transportista(transportista, sur)

        self.assertEqual(TransportistaInvernadero.objects.count(), 1)

    def test_d55_un_invernadero_con_fila_no_se_borra(self):
        """D-55, punto 3: la FK al invernadero es PROTECT."""
        norte = crear_invernadero("Norte")
        asignar_transportista(crear_transportista(), norte)

        with self.assertRaises(ProtectedError):
            norte.delete()

    def test_d55_una_cuenta_con_fila_no_se_borra(self):
        """D-55, punto 3: la FK a la cuenta del Transportista es PROTECT."""
        transportista = crear_transportista()
        asignar_transportista(transportista, crear_invernadero("Norte"))

        with self.assertRaises(ProtectedError):
            transportista.delete()

    def test_d55_desde_no_tiene_valor_por_defecto(self):
        """D-55, punto 3 y modelo: ``desde`` lo fija el servicio; sin valor, la base rechaza la fila."""
        campo = TransportistaInvernadero._meta.get_field("desde")
        self.assertFalse(campo.has_default())
        self.assertFalse(campo.null)

    def test_str_nombra_al_transportista_y_al_invernadero(self):
        """Modelo: ``__str__`` sirve para leer la auditoría y el admin."""
        fila = asignar_transportista(crear_transportista(nombre="Diego", apellido="Ferreyra"), crear_invernadero("Norte"))
        self.assertEqual(str(fila), "Diego Ferreyra · Norte")

    def test_regla_3_de_cns_inv_transportistas_ordena_por_apellido_y_nombre_sin_mayusculas(self):
        """PROD-CNS-INV regla 3: ``Invernadero.transportistas()`` devuelve solo los vinculados, por apellido y nombre sin
        distinguir mayúsculas, y en una sola consulta."""
        norte = crear_invernadero("Norte")
        sur = crear_invernadero("Sur")
        zeta = crear_transportista("z@infoponia.com", nombre="Ana", apellido="zapata")
        alfa = crear_transportista("a@infoponia.com", nombre="Luis", apellido="Alvarez")
        beta = crear_transportista("b@infoponia.com", nombre="beto", apellido="Alvarez")
        ajeno = crear_transportista("o@infoponia.com", nombre="Otro", apellido="Ajeno")
        crear_transportista("s@infoponia.com", nombre="Sin", apellido="Invernadero")
        for t in (zeta, alfa, beta):
            asignar_transportista(t, norte)
        asignar_transportista(ajeno, sur)

        with self.assertNumQueries(1):
            lista = norte.transportistas()
            nombres = [t.invernadero_asignado.desde is not None and t.pk for t in lista]

        self.assertEqual([t.pk for t in lista], [beta.pk, alfa.pk, zeta.pk])
        self.assertEqual(len(nombres), 3)
