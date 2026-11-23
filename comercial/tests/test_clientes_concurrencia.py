# Pruebas de concurrencia de los servicios de clientes (COM-01, paso 3; docs/patrones/bloqueos.md, sección «comercial», y
# docs/casos_de_uso/comercial/clientes.md, «Bloqueos»): dos altas con el mismo CUIT, baja y modificación a la vez del mismo cliente
# y dos bajas a la vez. Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son
# ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar, así que no usan Georef (sin direcciones).
#
# Lo que se garantiza: nunca dos clientes con el mismo CUIT (lo respalda la base) y ningún choque termina en un error 500: el que
# pierde recibe un rechazo claro.

from django.test import TransactionTestCase, tag

from comercial.models import Cliente
from comercial.servicios import clientes
from comercial.tests.fabricas import cliente, datos_de_cliente, datos_de_cliente_de
from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import crear_vendedor


@tag("concurrencia")
class ClientesConcurrenciaTests(TransactionTestCase):
    """Bloqueos de ``alta_cliente``, ``modificar_cliente`` y ``baja_cliente`` (cuentas, después el cliente)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.vendedor = crear_vendedor()
        self.otro_vendedor = crear_vendedor("otro@infoponia.com")

    def test_regla_1_dos_altas_con_el_mismo_cuit_crean_un_solo_cliente(self):
        """Regla 1 de COM-ALT-CLT y MD-48: la segunda alta recibe el mismo error de campo del CUIT repetido, con el id del cliente
        creado por la primera; la restricción única de la base la respalda (sin ella, las dos pasarían). Nunca un error 500."""
        resultados = correr_a_la_vez(
            lambda: clientes.alta_cliente(self.vendedor, datos_de_cliente()),
            lambda: clientes.alta_cliente(self.otro_vendedor, datos_de_cliente(cuit="30712345671")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cuit_de_cliente_activo"])
        self.assertEqual(rechazos[0].error_dict["cuit"][0].params["cliente_id"], exitos[0].pk)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_cliente").count(), 1)

    def test_regla_1_dos_altas_con_cuit_distinto_crean_dos_clientes(self):
        """Control de la prueba anterior: con CUIT distinto, las dos pasan."""
        resultados = correr_a_la_vez(
            lambda: clientes.alta_cliente(self.vendedor, datos_de_cliente()),
            lambda: clientes.alta_cliente(self.otro_vendedor, datos_de_cliente(cuit="30000000090")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))

    def test_regla_2_baja_y_modificacion_a_la_vez_terminan_las_dos_sin_error(self):
        """Cómo se aplica, «Bloqueos»: la modificación espera a la baja (o al revés), relee el cliente y termina: un cliente inactivo
        se puede modificar (regla 2 de MOD). Quedan los dos registros y el cliente inactivo, con el teléfono nuevo."""
        existente = cliente(cuit="30712345671", razon_social="Los Pinos")
        resultados = correr_a_la_vez(
            lambda: clientes.baja_cliente(self.gerente, existente.pk),
            lambda: clientes.modificar_cliente(
                self.vendedor, existente.pk, datos_de_cliente_de(existente, telefono="+54 376 400-1001")
            ),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        existente.refresh_from_db()
        self.assertEqual((existente.estado_cliente, existente.telefono_cliente), ("inactivo", "+54 376 400-1001"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=["baja_cliente", "modificacion_cliente"]).count(), 2)

    def test_regla_2_modificacion_primero_y_baja_despues_tambien_terminan_las_dos(self):
        """El mismo choque en el otro orden: la modificación frena después de escribir y la baja espera."""
        existente = cliente(cuit="30712345671", razon_social="Los Pinos")
        resultados = correr_a_la_vez(
            lambda: clientes.modificar_cliente(
                self.vendedor, existente.pk, datos_de_cliente_de(existente, telefono="+54 376 400-1001")
            ),
            lambda: clientes.baja_cliente(self.gerente, existente.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        existente.refresh_from_db()
        self.assertEqual((existente.estado_cliente, existente.telefono_cliente), ("inactivo", "+54 376 400-1001"))

    def test_pre_b_dos_bajas_a_la_vez_dan_de_baja_una_sola_vez(self):
        """Precondición b de BAJ: la segunda baja relee el cliente ya inactivo y se rechaza con ``cliente_inactivo``; un solo registro."""
        existente = cliente(cuit="30712345671")
        resultados = correr_a_la_vez(
            lambda: clientes.baja_cliente(self.gerente, existente.pk),
            lambda: clientes.baja_cliente(self.gerente, existente.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cliente_inactivo"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_cliente").count(), 1)
