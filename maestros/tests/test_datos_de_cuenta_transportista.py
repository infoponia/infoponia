# Pruebas de lo que `maestros` registra en ``core.extensiones.registrar_datos_de_cuenta`` (MAE-05, paso 7; D-55, punto 2;
# regla 3 de USR-CNS-USR y regla 1 de USR-GST-PRF): el «Invernadero» del Transportista, solo para consultar. Para un
# Transportista, ``DatoDeCuenta("Invernadero", nombre o "Sin invernadero", nota)`` con la nota «Se asigna desde la ficha del
# invernadero, en “Logística”.»; para los demás roles, nada. Se registra en ``MaestrosConfig.ready()``: acá se prueba el
# registrante real (``core.extensiones.datos_de_cuenta``) y las dos pantallas que lo muestran.

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import extensiones
from core.extensiones import DatoDeCuenta, datos_de_cuenta
from core.tests.fabricas import crear_cuenta, crear_gerente
from maestros.servicios import transportistas
from maestros.tests.fabricas import (
    ConGeoref,
    asignar_transportista,
    crear_agronomo,
    crear_capataz_activo,
    crear_invernadero,
    crear_tecnico,
    crear_transportista,
    crear_vendedor,
)

NOTA = "Se asigna desde la ficha del invernadero, en “Logística”."


class DatosDeCuentaDelTransportistaTests(ConGeoref, TestCase):
    """El registrante de `maestros`. Desde COM-01 `comercial` registra además el «Vehículo» del Transportista: estas pruebas son del
    registrante de `maestros` solo, así que se aíslan con una lista que lo tiene a él únicamente (lo que prueban no cambia)."""

    def setUp(self):
        self.enterContext(mock.patch.object(extensiones, "_DATOS_DE_CUENTA", [transportistas.datos_de_cuenta]))

    def test_regla_3_un_transportista_con_invernadero_ve_su_nombre(self):
        """USR-CNS-USR regla 3: el Transportista con invernadero muestra «Invernadero» con su nombre y la nota."""
        cuenta = crear_transportista()
        asignar_transportista(cuenta, crear_invernadero("Norte"))

        self.assertEqual(datos_de_cuenta(cuenta), [DatoDeCuenta("Invernadero", "Norte", NOTA)])

    def test_regla_3_un_transportista_sin_invernadero_ve_sin_invernadero(self):
        """USR-CNS-USR regla 3 y D-55 (punto 1): «Sin invernadero» si no tiene; es válido."""
        self.assertEqual(datos_de_cuenta(crear_transportista()), [DatoDeCuenta("Invernadero", "Sin invernadero", NOTA)])

    def test_regla_3_un_transportista_inactivo_conserva_su_invernadero(self):
        """D-55 (punto 8): la fila queda como historial al dar de baja la cuenta, y se sigue viendo."""
        cuenta = crear_transportista(activo=False)
        asignar_transportista(cuenta, crear_invernadero("Norte"))
        self.assertEqual(datos_de_cuenta(cuenta), [DatoDeCuenta("Invernadero", "Norte", NOTA)])

    def test_regla_3_los_demas_roles_no_tienen_el_dato(self):
        """D-55, punto 2: para los demás roles, nada."""
        gerente = crear_gerente()
        for cuenta in (gerente, crear_agronomo(), crear_capataz_activo(), crear_vendedor(), crear_tecnico()):
            with self.subTest(rol=cuenta.rol):
                self.assertEqual(datos_de_cuenta(cuenta), [])

    def test_regla_3_el_dato_se_arma_con_una_sola_consulta_y_los_demas_roles_con_ninguna(self):
        """Interfaz: el invernadero se lee de un tirón (con ``select_related``); otros roles no consultan nada."""
        cuenta = crear_transportista()
        asignar_transportista(cuenta, crear_invernadero("Norte"))
        agronomo = crear_agronomo()

        with self.assertNumQueries(1):
            datos_de_cuenta(cuenta)
        with self.assertNumQueries(0):
            datos_de_cuenta(agronomo)


class DatoDeCuentaEnLasPantallasTests(ConGeoref, TestCase):
    """La ficha de la cuenta (con la nota) y Mi perfil (sin la nota) con el registrante real."""

    def test_regla_3_la_ficha_de_la_cuenta_muestra_el_invernadero_con_la_nota(self):
        """USR-CNS-USR regla 3: el Gerente ve el invernadero del Transportista y la nota."""
        cuenta = crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        asignar_transportista(cuenta, crear_invernadero("Norte"))
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("core:usuario", args=[cuenta.pk]))

        self.assertContains(respuesta, "Invernadero")
        self.assertContains(respuesta, "Norte")
        self.assertContains(respuesta, NOTA)

    def test_regla_3_la_ficha_de_un_transportista_sin_invernadero_dice_sin_invernadero(self):
        """USR-CNS-USR regla 3: «Sin invernadero» y la nota."""
        cuenta = crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("core:usuario", args=[cuenta.pk]))

        self.assertContains(respuesta, "Sin invernadero")
        self.assertContains(respuesta, NOTA)

    def test_regla_3_la_ficha_de_otros_roles_no_muestra_el_dato(self):
        """USR-CNS-USR regla 3: solo el Transportista tiene «Invernadero» en su ficha."""
        agronomo = crear_agronomo()
        crear_invernadero("Norte", agronomo=agronomo)
        self.client.force_login(crear_gerente())

        respuesta = self.client.get(reverse("core:usuario", args=[agronomo.pk]))

        self.assertNotContains(respuesta, "Sin invernadero")
        self.assertNotContains(respuesta, NOTA)

    def test_regla_1_mi_perfil_del_transportista_muestra_su_invernadero_sin_la_nota(self):
        """USR-GST-PRF regla 1: Mi perfil muestra el invernadero (solo para consultar), sin la nota."""
        cuenta = crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera")
        asignar_transportista(cuenta, crear_invernadero("Norte"))
        self.client.force_login(cuenta)

        respuesta = self.client.get(reverse("core:mi_perfil"))

        self.assertContains(respuesta, "Invernadero")
        self.assertContains(respuesta, "Norte")
        self.assertNotContains(respuesta, NOTA)

    def test_regla_1_mi_perfil_de_un_transportista_sin_invernadero_dice_sin_invernadero(self):
        """USR-GST-PRF regla 1: «Sin invernadero» si no tiene."""
        self.client.force_login(crear_transportista("marcos@infoponia.com", nombre="Marcos", apellido="Vera"))

        respuesta = self.client.get(reverse("core:mi_perfil"))

        self.assertContains(respuesta, "Sin invernadero")
        self.assertNotContains(respuesta, NOTA)

    def test_regla_1_mi_perfil_de_otros_roles_no_muestra_el_dato(self):
        """USR-GST-PRF regla 1: solo el Transportista tiene «Invernadero» en Mi perfil."""
        self.client.force_login(crear_agronomo())
        respuesta = self.client.get(reverse("core:mi_perfil"))
        self.assertNotContains(respuesta, "Sin invernadero")

    def test_d55_el_alta_de_la_cuenta_no_pide_invernadero_para_el_transportista(self):
        """USR-ALT-USR regla 5 y D-55: el alta no pide invernadero para ningún rol, tampoco el Transportista."""
        self.client.force_login(crear_gerente())
        respuesta = self.client.get(reverse("core:usuario_nuevo"))
        self.assertNotContains(respuesta, 'name="invernadero')
