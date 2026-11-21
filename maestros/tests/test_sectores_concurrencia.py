# Pruebas de concurrencia de los servicios de sector (MAE-03; docs/patrones/bloqueos.md, D-30, D-32 y D-40): dos altas con el
# mismo nombre, la modificación del total contra una reserva simulada y la baja del invernadero contra el alta de un sector.
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``: su
# ``flush`` vacía todas las tablas al terminar, incluidos los cinco tipos de etapa y Georef, así que la clase hereda de
# ``ConDatosDeMaestros`` (los recarga antes de la clase) y cada prueba los vuelve a asegurar en ``setUp``
# (docs/patrones/datos_de_migracion.md). El invernadero se crea con geografía propia, no con Georef.

from types import SimpleNamespace

from django.db import transaction
from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from maestros import extensiones
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios import invernaderos, sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    asegurar_datos_de_maestros,
    crear_agronomo,
    crear_invernadero_con_geografia_propia,
    crear_sector,
    tipo_etapa,
)
from unittest import mock

# Punto de parada que usa ``detener_antes_de`` para frenar a la primera operación justo antes de terminar.
pausa = SimpleNamespace(punto=lambda: None)


@tag("concurrencia")
class SectoresConcurrenciaTests(ConDatosDeMaestros, TransactionTestCase):
    """Bloqueos de ``alta_sector``, ``modificar_sector`` y de la baja del invernadero (orden invernadero -> sector)."""

    def setUp(self):
        asegurar_datos_de_maestros()  # el flush de la prueba anterior vació los tipos de etapa
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero A", agronomo=self.agronomo)

    def alta(self, nombre="C-1"):
        return lambda: sectores.alta_sector(
            self.agronomo,
            self.invernadero.pk,
            nombre=nombre,
            tipo_etapa_id=tipo_etapa("germinacion").pk,
            cant_agujeros_total=100,
        )

    def test_pre_c_dos_altas_con_el_mismo_nombre_crean_un_solo_sector(self):
        """PROD-ALT-SCT regla 2 / D-40: la segunda alta espera el bloqueo del invernadero, ve el sector de la primera y se
        rechaza con ``nombre_repetido``. Sin el bloqueo (y sin la restricción de la base) las dos pasarían."""
        resultados = correr_a_la_vez(self.alta(), self.alta("c-1"), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(SectorProduccion.objects.count(), 1)

    def test_regla_1_la_modificacion_del_total_espera_a_quien_reserva_agujeros(self):
        """PROD-MOD-SCT regla 1 y contrato de ``bloquear_sectores`` (docs/api/extensiones_de_maestros.md): quien reserva
        bloquea el invernadero y el sector antes de reservar; la modificación espera, ve la reserva y rechaza bajar el total
        por debajo de lo reservado. Sin los bloqueos de la modificación leería 0 reservados y bajaría el total."""
        sector = crear_sector(self.invernadero, "C-1", "germinacion", 100)
        reservados = {}

        def reservar():
            with transaction.atomic():
                bloquear_invernadero_activo(self.invernadero.pk)
                sectores.bloquear_sectores(self.invernadero.pk, [sector.pk])
                pausa.punto()  # acá se detiene: la reserva todavía no se confirmó
                reservados[sector.pk] = 80

        def bajar_el_total():
            return sectores.modificar_sector(
                self.agronomo,
                sector.pk,
                nombre="C-1",
                tipo_etapa_id=sector.tipo_etapa_id,
                cant_agujeros_total=50,
            )

        with mock.patch.object(extensiones, "_AGUJEROS", [lambda ids: {i: (reservados.get(i, 0), 0) for i in ids}]):
            resultados = correr_a_la_vez(reservar, bajar_el_total, primera="a", detener_antes_de=(pausa, "punto"))
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (0 + 1, 1, []))  # la reserva sale bien; la baja del total, no
        self.assertEqual(codigos(rechazos[0]), ["por_debajo_del_minimo"])
        sector.refresh_from_db()
        self.assertEqual(sector.cant_agujeros_total, 100)

    def test_post_f_la_baja_del_invernadero_espera_al_alta_de_un_sector_y_lo_da_de_baja(self):
        """PROD-BAJ-INV postcondición f y D-40: el alta va primera y la baja del invernadero espera su bloqueo; cuando sigue,
        ve el sector nuevo y lo pasa a inactivo con su log. Sin el bloqueo del invernadero en el alta, el sector quedaría
        activo en un invernadero inactivo."""
        gerente = crear_gerente()
        resultados = correr_a_la_vez(
            self.alta(), lambda: invernaderos.baja_invernadero(gerente, self.invernadero.pk), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        sector = SectorProduccion.objects.get()
        self.assertEqual(sector.estado_sector, "inactivo")
        self.assertEqual(
            RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA_SECTOR).count(), 1
        )
        self.assertFalse(Invernadero.objects.get(pk=self.invernadero.pk).activo)

    def test_pre_b_el_alta_espera_a_la_baja_del_invernadero_y_se_rechaza(self):
        """PROD-ALT-SCT precondición b y D-40: la baja va primera y el alta espera; cuando sigue, el invernadero está
        inactivo y no crea nada (``invernadero_inactivo``)."""
        gerente = crear_gerente()
        resultados = correr_a_la_vez(
            lambda: invernaderos.baja_invernadero(gerente, self.invernadero.pk), self.alta(), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        self.assertFalse(SectorProduccion.objects.exists())
