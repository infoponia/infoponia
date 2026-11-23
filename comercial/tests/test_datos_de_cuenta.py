# Pruebas de lo que `comercial` registra en ``core.extensiones.registrar_datos_de_cuenta`` (COM-01, paso 4 y paso 6; decisión del
# estudiante del 21/11/2026; regla 3 de USR-CNS-USR y regla 1 de USR-GST-PRF): el «Vehículo» del Transportista, solo para consultar.
# Para un Transportista, ``DatoDeCuenta("Vehículo", «Camioneta AE123CD · 800 kg» o «Sin vehículo», nota)`` con la nota «Se asigna desde
# el vehículo, en Comercial › Vehículos.»; para los demás roles, nada. Esta parte prueba la función; el registro en ``ready()`` y las
# pantallas (ficha de la cuenta y «Mi perfil», después de «Invernadero») se prueban en el paso 6.

from django.test import TestCase

from comercial.servicios import vehiculos
from comercial.tests.fabricas import vehiculo
from core.extensiones import DatoDeCuenta
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_tecnico, crear_transportista, crear_vendedor

NOTA = "Se asigna desde el vehículo, en Comercial › Vehículos."


class DatosDeCuentaDelTransportistaTests(TestCase):
    """``datos_de_cuenta_del_transportista(cuenta) -> list[DatoDeCuenta]``."""

    def test_regla_3_un_transportista_con_vehiculo_ve_su_descripcion_y_la_nota(self):
        """USR-CNS-USR regla 3: «Camioneta AE123CD · 800 kg» y la nota."""
        cuenta = crear_transportista()
        vehiculo(patente="AE123CD", capacidad="800", transportista=cuenta)
        self.assertEqual(
            vehiculos.datos_de_cuenta_del_transportista(cuenta), [DatoDeCuenta("Vehículo", "Camioneta AE123CD · 800 kg", NOTA)]
        )

    def test_regla_3_un_transportista_sin_vehiculo_ve_sin_vehiculo(self):
        """Neutro sin datos: «Sin vehículo» y la nota."""
        self.assertEqual(
            vehiculos.datos_de_cuenta_del_transportista(crear_transportista()), [DatoDeCuenta("Vehículo", "Sin vehículo", NOTA)]
        )

    def test_regla_3_un_vehiculo_inactivo_no_cuenta(self):
        """«Vehículo» (cómo se aplica): un vehículo inactivo no tiene transportista, así que el Transportista queda «Sin vehículo»."""
        cuenta = crear_transportista()
        vehiculo(patente="AE123CD", transportista=cuenta)
        vehiculos.baja_vehiculo(crear_gerente(), cuenta.vehiculo.pk)
        cuenta.refresh_from_db()
        self.assertEqual(vehiculos.datos_de_cuenta_del_transportista(cuenta)[0].valor, "Sin vehículo")

    def test_regla_3_los_demas_roles_no_tienen_el_dato(self):
        """Los demás roles: lista vacía."""
        for cuenta in (crear_gerente(), crear_agronomo(), crear_capataz_activo(), crear_vendedor(), crear_tecnico()):
            with self.subTest(rol=cuenta.rol):
                self.assertEqual(vehiculos.datos_de_cuenta_del_transportista(cuenta), [])

    def test_regla_3_una_consulta_para_el_transportista_y_ninguna_para_los_demas(self):
        """Interfaz: una consulta para el Transportista y ninguna para los otros roles."""
        cuenta = crear_transportista()
        vehiculo(patente="AE123CD", transportista=cuenta)
        agronomo = crear_agronomo()
        with self.assertNumQueries(1):
            vehiculos.datos_de_cuenta_del_transportista(cuenta)
        with self.assertNumQueries(0):
            vehiculos.datos_de_cuenta_del_transportista(agronomo)


# ---- el registrante real y las dos pantallas (paso 6) ----

from django.apps import apps  # noqa: E402
from django.urls import reverse  # noqa: E402

from core import extensiones  # noqa: E402
from maestros.tests.fabricas import ConGeoref, asignar_transportista, crear_invernadero  # noqa: E402


class DatoDeCuentaRegistradoTests(ConGeoref, TestCase):
    """``ComercialConfig.ready()`` registra la función real; la ficha de la cuenta y «Mi perfil» muestran el «Vehículo»."""

    def setUp(self):
        self.cuenta = crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        asignar_transportista(self.cuenta, crear_invernadero("Norte"))
        vehiculo(patente="AE123CD", capacidad="800", transportista=self.cuenta)

    def test_ext_comercial_registra_el_dato_una_sola_vez_y_despues_del_invernadero(self):
        """``registrar_datos_de_cuenta`` es idempotente; el «Vehículo» va después del «Invernadero» de `maestros` (INSTALLED_APPS)."""
        apps.get_app_config("comercial").ready()
        etiquetas = [dato.etiqueta for dato in extensiones.datos_de_cuenta(self.cuenta)]
        self.assertEqual(etiquetas, ["Invernadero", "Vehículo"])

    def test_regla_3_la_ficha_de_la_cuenta_muestra_el_vehiculo_con_la_nota(self):
        """USR-CNS-USR regla 3: «Vehículo: Camioneta AE123CD · 800 kg» y la nota, después de «Invernadero»."""
        self.client.force_login(crear_gerente())
        respuesta = self.client.get(reverse("core:usuario", args=[self.cuenta.pk]))
        self.assertContains(respuesta, "Camioneta AE123CD · 800 kg")
        self.assertContains(respuesta, NOTA)
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("Invernadero"), contenido.index("Vehículo"))

    def test_regla_3_la_ficha_de_un_transportista_sin_vehiculo_dice_sin_vehiculo(self):
        """USR-CNS-USR regla 3: «Sin vehículo»."""
        sin = crear_transportista("sin@infoponia.com", nombre="Sin", apellido="Auto")
        self.client.force_login(crear_gerente())
        self.assertContains(self.client.get(reverse("core:usuario", args=[sin.pk])), "Sin vehículo")

    def test_regla_1_mi_perfil_muestra_el_vehiculo_despues_del_invernadero_sin_la_nota(self):
        """USR-GST-PRF regla 1: «Mi perfil» muestra el vehículo, solo para consultar y sin la nota."""
        self.client.force_login(self.cuenta)
        respuesta = self.client.get(reverse("core:mi_perfil"))
        self.assertContains(respuesta, "Camioneta AE123CD · 800 kg")
        self.assertNotContains(respuesta, NOTA)
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("Invernadero"), contenido.index("Vehículo"))

    def test_regla_3_la_ficha_de_otros_roles_no_muestra_el_vehiculo(self):
        """Solo el Transportista tiene «Vehículo» en su ficha."""
        agronomo = crear_agronomo()
        self.client.force_login(crear_gerente())
        self.assertNotContains(self.client.get(reverse("core:usuario", args=[agronomo.pk])), "Sin vehículo")
