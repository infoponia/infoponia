# Pruebas de concurrencia de los servicios de vehículos (COM-01, paso 4; docs/patrones/bloqueos.md, sección «comercial», y
# docs/casos_de_uso/comercial/vehiculos.md, «Bloqueos»): dos altas con la misma patente, dos vehículos que eligen al mismo
# transportista, un alta contra la baja de la cuenta de ese transportista y baja contra modificación del mismo vehículo. Dos hilos,
# dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``.
#
# Lo que se garantiza: una patente en un solo vehículo y un transportista con un solo vehículo (los respalda la base) y ningún choque
# termina en un error 500: el que pierde recibe un rechazo claro.

from django.test import TransactionTestCase, tag

from comercial.models import Vehiculo
from comercial.servicios import vehiculos
from comercial.tests.fabricas import datos_de_vehiculo, datos_de_vehiculo_de, vehiculo
from core.models import RegistroAuditoria
from core.servicios import baja_usuario
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_transportista


@tag("concurrencia")
class VehiculosConcurrenciaTests(TransactionTestCase):
    """Bloqueos de ``alta_vehiculo``, ``modificar_vehiculo`` y ``baja_vehiculo`` (cuentas, después el vehículo)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")

    def test_regla_1_dos_altas_con_la_misma_patente_crean_un_solo_vehiculo(self):
        """Regla 1 de COM-ALT-VEH: la segunda alta espera a la primera y se rechaza con ``patente_repetida``; la restricción
        única de la base la respalda. Nunca un error 500."""
        resultados = correr_a_la_vez(
            lambda: vehiculos.alta_vehiculo(self.gerente, datos_de_vehiculo()),
            lambda: vehiculos.alta_vehiculo(self.gerente, datos_de_vehiculo(patente="ae-123 cd")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["patente_repetida"])
        self.assertEqual(Vehiculo.objects.count(), 1)

    def test_regla_4_dos_vehiculos_que_eligen_al_mismo_transportista_uno_lo_logra(self):
        """Regla 4 de COM-ALT-VEH y R073: uno lo logra y el otro recibe ``transportista_con_vehiculo`` (la base respalda el
        0..1). Nunca un error 500 y un solo aviso al transportista."""
        resultados = correr_a_la_vez(
            lambda: vehiculos.alta_vehiculo(self.gerente, datos_de_vehiculo(patente="AE123CD", transportista_id=self.diego.pk)),
            lambda: vehiculos.alta_vehiculo(self.gerente, datos_de_vehiculo(patente="ABC123", transportista_id=self.diego.pk)),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["transportista_con_vehiculo"])
        self.assertEqual(Vehiculo.objects.filter(transportista=self.diego).count(), 1)
        self.assertEqual(self.diego.notificaciones.count(), 1)

    def test_regla_4_el_alta_contra_la_baja_de_la_cuenta_del_transportista(self):
        """Regla 4 de COM-ALT-VEH: si la cuenta se da de baja primero, el alta relee su estado ya bloqueada y la rechaza con
        ``transportista_invalido``; nunca queda un vehículo asignado a una cuenta inactiva por una carrera."""
        resultados = correr_a_la_vez(
            lambda: baja_usuario(self.gerente, self.diego.pk),
            lambda: vehiculos.alta_vehiculo(self.gerente, datos_de_vehiculo(transportista_id=self.diego.pk)),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["transportista_invalido"])
        self.assertFalse(Vehiculo.objects.exists())

    def test_pre_b_baja_y_modificacion_del_mismo_vehiculo_a_la_vez(self):
        """Precondición b de MOD y de BAJ: la baja confirma primero y la modificación relee el vehículo ya inactivo: se rechaza con
        ``vehiculo_inactivo``, sin error 500; queda un solo registro de cada acción posible."""
        existente = vehiculo(patente="AE123CD", transportista=self.diego)
        resultados = correr_a_la_vez(
            lambda: vehiculos.baja_vehiculo(self.gerente, existente.pk),
            lambda: vehiculos.modificar_vehiculo(self.gerente, existente.pk, datos_de_vehiculo_de(existente, marca="Fiat")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["vehiculo_inactivo"])
        existente.refresh_from_db()
        self.assertEqual((existente.estado_vehiculo, existente.transportista_id, existente.marca), ("inactivo", None, "Ford"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_vehiculo").count(), 1)

    def test_pre_b_dos_bajas_del_mismo_vehiculo_dan_de_baja_una_sola_vez(self):
        """Precondición b de BAJ: la segunda baja relee el vehículo inactivo y se rechaza; un solo aviso al transportista."""
        existente = vehiculo(patente="AE123CD", transportista=self.diego)
        resultados = correr_a_la_vez(
            lambda: vehiculos.baja_vehiculo(self.gerente, existente.pk),
            lambda: vehiculos.baja_vehiculo(self.gerente, existente.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["vehiculo_inactivo"])
        self.assertEqual(self.diego.notificaciones.count(), 1)
