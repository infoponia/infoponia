# Pruebas de COM-CNS-VEH, Consultar Vehículo (COM-01, paso 4; docs/casos_de_uso/comercial/vehiculos.md): la búsqueda (patente, tipo,
# transportista), los filtros (estado e invernadero del transportista), el orden, la ficha, los transportistas disponibles, los
# botones y que no hay consultas por fila.
#
# ``buscar_vehiculos(actor, texto="", estado="", invernadero_id=None)`` devuelve ``[FilaDeVehiculo(vehiculo, invernadero, en_ruta)]``;
# ``ficha_del_vehiculo(actor, id)``, ``FichaDelVehiculo(vehiculo, transportista, invernadero, en_ruta)``;
# ``transportistas_disponibles(actor, vehiculo=None)``, ``[OpcionDeTransportista(transportista, invernadero)]``;
# ``acciones_permitidas(actor, vehiculo)``, un ``frozenset`` con ``ACCION_MODIFICAR``, ``ACCION_BAJA`` y ``ACCION_REACTIVAR``.

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from comercial.servicios import vehiculos
from comercial.tests.fabricas import vehiculo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import (
    ConGeoref,
    asignar_transportista,
    crear_agronomo,
    crear_invernadero,
    crear_transportista,
    crear_vendedor,
)


class ComCnsVehBusquedaTests(ConGeoref, TestCase):
    """``buscar_vehiculos``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.norte = crear_invernadero("Norte")
        self.sur = crear_invernadero("Sur")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")
        asignar_transportista(self.diego, self.norte)
        asignar_transportista(self.carla, self.sur)
        self.camioneta = vehiculo(patente="AE123CD", tipo="camioneta", transportista=self.diego)
        self.furgon = vehiculo(patente="ABC123", tipo="furgon", transportista=self.carla)
        self.moto = vehiculo(patente="ZZZ999", tipo="moto", activo=False)

    def buscar(self, texto="", estado="", invernadero_id=None, actor=None):
        return [fila.vehiculo.pk for fila in vehiculos.buscar_vehiculos(actor or self.gerente, texto, estado, invernadero_id)]

    def test_regla_1_sin_filtros_trae_todos_ordenados_por_patente(self):
        """Regla 1 y orden: por patente (ABC123, AE123CD, ZZZ999), activos e inactivos."""
        self.assertEqual(self.buscar(), [self.furgon.pk, self.camioneta.pk, self.moto.pk])

    def test_regla_1_busca_por_patente_sin_importar_como_se_escriba(self):
        """Regla 1: por patente, sin mayúsculas, espacios ni guiones."""
        self.assertEqual(self.buscar("ae-123"), [self.camioneta.pk])
        self.assertEqual(self.buscar("abc 123"), [self.furgon.pk])
        self.assertEqual(self.buscar("999"), [self.moto.pk])

    def test_regla_1_busca_por_tipo(self):
        """Regla 1: por tipo (el nombre que se ve: «Camioneta», «Furgón»)."""
        self.assertEqual(self.buscar("camioneta"), [self.camioneta.pk])
        self.assertEqual(self.buscar("furgón"), [self.furgon.pk])
        self.assertEqual(self.buscar("MOTO"), [self.moto.pk])

    def test_regla_1_busca_por_nombre_o_apellido_del_transportista(self):
        """Regla 1: por el nombre del transportista (nombre, apellido o «nombre apellido»)."""
        self.assertEqual(self.buscar("diego"), [self.camioneta.pk])
        self.assertEqual(self.buscar("sosa"), [self.furgon.pk])
        self.assertEqual(self.buscar("Carla Sosa"), [self.furgon.pk])
        self.assertEqual(self.buscar("nadie"), [])

    def test_regla_1_filtra_por_estado(self):
        """Regla 1: filtro por estado (vacío, todos)."""
        self.assertEqual(self.buscar(estado="activo"), [self.furgon.pk, self.camioneta.pk])
        self.assertEqual(self.buscar(estado="inactivo"), [self.moto.pk])

    def test_regla_1_filtra_por_el_invernadero_del_transportista(self):
        """Regla 1: filtro por invernadero (el de su transportista, por ``TransportistaInvernadero``); un vehículo sin
        transportista no tiene invernadero."""
        self.assertEqual(self.buscar(invernadero_id=self.norte.pk), [self.camioneta.pk])
        self.assertEqual(self.buscar(invernadero_id=str(self.sur.pk)), [self.furgon.pk])
        self.assertEqual(self.buscar(invernadero_id="abc"), [self.furgon.pk, self.camioneta.pk, self.moto.pk])

    def test_regla_2_cada_fila_trae_el_invernadero_y_la_situacion(self):
        """Columnas de COM-01: el invernadero del transportista y «en ruta» (MD-118)."""
        en_ruta = vehiculo(patente="ABC999", transportista=crear_transportista("otro@infoponia.com"), en_ruta_hoy=True)
        filas = {fila.vehiculo.pk: fila for fila in vehiculos.buscar_vehiculos(self.gerente)}
        self.assertEqual(filas[self.camioneta.pk].invernadero.pk, self.norte.pk)
        self.assertIsNone(filas[self.moto.pk].invernadero)
        self.assertIsNone(filas[en_ruta.pk].invernadero)  # transportista sin invernadero
        self.assertEqual([filas[pk].en_ruta for pk in (self.camioneta.pk, en_ruta.pk)], [False, True])

    def test_pre_a_solo_el_gerente_consulta(self):
        """Precondición a: el Vendedor, otros roles, una cuenta inactiva o ``None`` reciben ``PermissionDenied``."""
        for actor in (crear_vendedor(), crear_agronomo(), self.diego, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                vehiculos.buscar_vehiculos(actor)

    def test_interfaz_no_hace_consultas_por_fila(self):
        """Interfaz: la lista hace las mismas consultas con tres vehículos que con nueve."""
        self.buscar()  # calienta cachés
        with CaptureQueriesContext(connection) as pocas:
            self.buscar()
        for numero in range(6):
            transportista = crear_transportista(f"t{numero}@infoponia.com")
            asignar_transportista(transportista, self.norte)
            vehiculo(transportista=transportista)
        with self.assertNumQueries(len(pocas.captured_queries)):
            self.buscar()

    def test_post_a_consultar_no_registra_ningun_cambio(self):
        """Postcondición a y SEG-14: las consultas no se auditan."""
        self.buscar("diego")
        self.assertFalse(RegistroAuditoria.objects.exists())


class ComCnsVehFichaTests(ConGeoref, TestCase):
    """``ficha_del_vehiculo``, ``transportistas_disponibles`` y ``acciones_permitidas``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.norte = crear_invernadero("Norte")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        asignar_transportista(self.diego, self.norte)
        self.vehiculo = vehiculo(patente="AE123CD", transportista=self.diego)

    def test_regla_2_la_ficha_muestra_los_datos_el_transportista_y_su_invernadero(self):
        """Regla 2: los datos del vehículo, su transportista y su invernadero, y si está en ruta hoy."""
        ficha = vehiculos.ficha_del_vehiculo(self.gerente, self.vehiculo.pk)
        self.assertEqual(
            (ficha.vehiculo.pk, ficha.transportista.pk, ficha.invernadero.pk, ficha.en_ruta),
            (self.vehiculo.pk, self.diego.pk, self.norte.pk, False),
        )

    def test_regla_2_la_ficha_de_un_vehiculo_en_ruta_y_la_de_uno_sin_transportista(self):
        """Regla 2: «En ruta hoy» (MD-118); sin transportista no hay invernadero."""
        en_ruta = vehiculo(patente="ABC123", transportista=crear_transportista("carla@infoponia.com"), en_ruta_hoy=True)
        sin = vehiculo(patente="ABC999")
        self.assertTrue(vehiculos.ficha_del_vehiculo(self.gerente, en_ruta.pk).en_ruta)
        ficha = vehiculos.ficha_del_vehiculo(self.gerente, sin.pk)
        self.assertEqual((ficha.transportista, ficha.invernadero, ficha.en_ruta), (None, None, False))

    def test_pre_a_solo_el_gerente_y_404_si_no_existe(self):
        """Precondición a y D-28: otros roles, ``PermissionDenied``; un id inexistente, 404."""
        for actor in (crear_vendedor(), crear_agronomo(), self.diego, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                vehiculos.ficha_del_vehiculo(actor, self.vehiculo.pk)
        with self.assertRaises(Http404):
            vehiculos.ficha_del_vehiculo(self.gerente, 999999)

    def test_regla_4_de_alt_los_disponibles_son_los_activos_sin_vehiculo_con_su_invernadero(self):
        """Regla 4 de ALT: solo transportistas activos sin otro vehículo, cada uno con su invernadero (o ninguno)."""
        libre = crear_transportista("libre@infoponia.com", nombre="Luis", apellido="Acosta")
        asignar_transportista(libre, self.norte)
        sin_invernadero = crear_transportista("sin@infoponia.com", nombre="Ana", apellido="Zapata")
        crear_transportista("inactivo@infoponia.com", activo=False)
        crear_agronomo()
        opciones = vehiculos.transportistas_disponibles(self.gerente)
        self.assertEqual([(o.transportista.pk, o.invernadero.pk if o.invernadero else None) for o in opciones],
                         [(libre.pk, self.norte.pk), (sin_invernadero.pk, None)])  # por apellido y nombre

    def test_regla_4_de_alt_en_la_modificacion_se_suma_el_transportista_actual(self):
        """«Transportista» (cómo se aplica): «más el actual, en MOD»."""
        libre = crear_transportista("libre@infoponia.com", nombre="Luis", apellido="Acosta")
        pks = [o.transportista.pk for o in vehiculos.transportistas_disponibles(self.gerente, self.vehiculo)]
        self.assertEqual(sorted(pks), sorted([self.diego.pk, libre.pk]))
        self.assertNotIn(self.diego.pk, [o.transportista.pk for o in vehiculos.transportistas_disponibles(self.gerente)])

    def test_pre_a_los_disponibles_son_solo_para_el_gerente(self):
        """Precondición a: solo el Gerente activo."""
        with self.assertRaises(PermissionDenied):
            vehiculos.transportistas_disponibles(crear_vendedor())

    def test_pre_a_las_acciones_segun_el_estado(self):
        """D-30: activo, «modificar» y «baja»; inactivo, «reactivar» (y no se modifica, regla 4 de MOD); otros roles, ninguna."""
        inactivo = vehiculo(patente="ABC123", activo=False)
        self.assertEqual(vehiculos.acciones_permitidas(self.gerente, self.vehiculo), {vehiculos.ACCION_MODIFICAR, vehiculos.ACCION_BAJA})
        self.assertEqual(vehiculos.acciones_permitidas(self.gerente, inactivo), {vehiculos.ACCION_REACTIVAR})
        for actor in (crear_vendedor(), crear_agronomo(), self.diego, None):
            with self.subTest(actor=actor):
                self.assertEqual(vehiculos.acciones_permitidas(actor, self.vehiculo), set())
