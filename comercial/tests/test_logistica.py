# Pruebas de lo que `comercial` registra en ``maestros.extensiones.registrar_logistica_de_transportista`` (COM-01, paso 4 y paso 6;
# D-55 y docs/api/extensiones_de_maestros.md, «Transportistas»): para cada Transportista, ``Logistica(vehiculo, en_ruta,
# entregas_a_realizar, url_entregas)`` con el vehículo activo como «Camioneta AE123CD · 800 kg» (o ``None``), si está en ruta hoy, y
# ``0`` y ``None`` en lo que completa COM-05. Una sola consulta para toda la lista. Esta parte prueba la función; el registro en
# ``ready()`` y las pantallas se prueban en el paso 6 (más abajo en este archivo, cuando existen).

from django.test import TestCase

from comercial.servicios import vehiculos
from comercial.tests.fabricas import vehiculo
from maestros.extensiones import Logistica
from maestros.tests.fabricas import crear_transportista


class LogisticaDeTransportistasTests(TestCase):
    """``logistica_de_transportistas(transportistas) -> dict[int, Logistica]``."""

    def setUp(self):
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        self.ana = crear_transportista("ana@infoponia.com", nombre="Ana", apellido="Torres")

    def test_ext_con_datos_el_vehiculo_activo_y_la_situacion(self):
        """Con datos: el vehículo como «Camioneta AE123CD · 800 kg», fuera de ruta, y las entregas en 0 y sin URL (COM-05)."""
        vehiculo(patente="AE123CD", tipo="camioneta", capacidad="800", transportista=self.diego)
        self.assertEqual(
            vehiculos.logistica_de_transportistas([self.diego]),
            {self.diego.pk: Logistica("Camioneta AE123CD · 800 kg", False, 0, None)},
        )

    def test_ext_en_ruta_hoy_se_informa(self):
        """MD-118: ``en_ruta`` solo si la ruta se inició hoy."""
        vehiculo(patente="AE123CD", transportista=self.diego, en_ruta_hoy=True)
        self.assertTrue(vehiculos.logistica_de_transportistas([self.diego])[self.diego.pk].en_ruta)

    def test_ext_neutro_sin_vehiculo_da_vehiculo_none(self):
        """Neutro sin datos: un Transportista sin vehículo tiene ``vehiculo=None`` y no está en ruta; está en el resultado."""
        self.assertEqual(
            vehiculos.logistica_de_transportistas([self.diego]), {self.diego.pk: Logistica(None, False, 0, None)}
        )

    def test_ext_cada_transportista_con_su_vehiculo(self):
        """Con varios: cada uno con el suyo, la capacidad con coma decimal y los sin vehículo en ``None``."""
        vehiculo(patente="AE123CD", tipo="camioneta", capacidad="800", transportista=self.diego)
        vehiculo(patente="ABC123", tipo="furgon", capacidad="1250.5", transportista=self.carla)
        resultado = vehiculos.logistica_de_transportistas([self.diego, self.carla, self.ana])
        self.assertEqual(
            [resultado[t.pk].vehiculo for t in (self.diego, self.carla, self.ana)],
            ["Camioneta AE123CD · 800 kg", "Furgón ABC123 · 1.250,5 kg", None],
        )

    def test_ext_una_lista_vacia_da_un_diccionario_vacio_sin_consultar(self):
        """Interfaz: sin transportistas no se consulta nada."""
        with self.assertNumQueries(0):
            self.assertEqual(vehiculos.logistica_de_transportistas([]), {})

    def test_ext_no_hace_consultas_por_fila(self):
        """Interfaz (API «Transportistas»): una consulta por tabla para toda la lista, con tres transportistas. CAMBIADA en COM-05a1: antes era una sola (los vehículos); ahora son dos,
        porque se suman las entregas «a realizar» de cada uno (otra tabla); nunca una por transportista."""
        vehiculo(patente="AE123CD", transportista=self.diego)
        vehiculo(patente="ABC123", transportista=self.carla, en_ruta_hoy=True)
        with self.assertNumQueries(2):
            vehiculos.logistica_de_transportistas([self.diego, self.carla, self.ana])


# ---- el registrante real y la ficha del invernadero (paso 6) ----

from django.apps import apps  # noqa: E402
from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402

from core.tests.fabricas import crear_gerente  # noqa: E402
from maestros import extensiones  # noqa: E402
from maestros.tests.fabricas import ConGeoref, asignar_transportista, crear_invernadero  # noqa: E402


class LogisticaRegistradaTests(ConGeoref, TestCase):
    """``ComercialConfig.ready()`` registra la función real; la ficha del invernadero muestra las tres columnas."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.norte = crear_invernadero("Norte")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        asignar_transportista(self.diego, self.norte)
        asignar_transportista(self.carla, self.norte)
        self.client.force_login(self.gerente)

    def test_ext_comercial_es_el_unico_registrante_de_la_logistica(self):
        """D-55 y API «Transportistas»: ``comercial`` registra ``logistica_de_transportistas``, una sola vez aunque ``ready()`` corra de nuevo."""
        self.assertEqual(extensiones._LOGISTICA, [vehiculos.logistica_de_transportistas])
        apps.get_app_config("comercial").ready()
        self.assertEqual(extensiones._LOGISTICA, [vehiculos.logistica_de_transportistas])

    def test_ext_la_ficha_del_invernadero_muestra_vehiculo_situacion_y_entregas(self):
        """Regla 3 de PROD-CNS-INV: las tres columnas con el vehículo («Camioneta AE123CD · 800 kg» o «Sin vehículo»), la situación y las
        entregas a realizar (0 hasta COM-05)."""
        vehiculo(patente="AE123CD", capacidad="800", transportista=self.diego)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[self.norte.pk]))
        self.assertContains(respuesta, "Camioneta AE123CD · 800 kg")
        self.assertContains(respuesta, "Sin vehículo")
        self.assertContains(respuesta, "En el invernadero")
        self.assertContains(respuesta, "Entregas a realizar")

    def test_ext_un_vehiculo_en_ruta_se_muestra_en_ruta(self):
        """MD-118: la situación «En ruta» en la ficha del invernadero."""
        vehiculo(patente="AE123CD", transportista=self.diego, en_ruta_hoy=True)
        self.assertContains(self.client.get(reverse("maestros:invernadero", args=[self.norte.pk])), "En ruta")

    def test_ext_la_ficha_no_hace_consultas_por_fila(self):
        """Interfaz: la ficha hace las mismas consultas con dos transportistas con vehículo que con uno solo."""
        url = reverse("maestros:invernadero", args=[self.norte.pk])
        vehiculo(patente="AE123CD", transportista=self.diego)
        self.client.get(url)  # calienta cachés
        with CaptureQueriesContext(connection) as uno:
            self.client.get(url)
        otra = crear_transportista("otra@infoponia.com", nombre="Otra", apellido="Zeta")
        asignar_transportista(otra, self.norte)
        vehiculo(patente="ABC123", transportista=otra)
        vehiculo(patente="ABC124", transportista=self.carla)
        with self.assertNumQueries(len(uno.captured_queries)):
            self.client.get(url)
