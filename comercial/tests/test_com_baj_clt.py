# Pruebas de COM-BAJ-CLT, Baja Cliente (COM-01, paso 3; docs/casos_de_uso/comercial/clientes.md): solo el Gerente, el cliente
# activo, que la baja no se bloquea, que las direcciones no cambian, lo pendiente (se completa en COM-02, COM-03, COM-06 y COM-08)
# y la auditoría.

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from comercial.models import Cliente
from comercial.servicios import clientes
from comercial.tests.fabricas import cliente, direccion_de_cliente
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_transportista, crear_vendedor


class ComBajCltServicioTests(ConGeoref, TestCase):
    """``baja_cliente(actor, cliente_id)`` y ``pendientes_del_cliente(cliente, actor)``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.cliente = cliente(cuit="30712345671", razon_social="Los Pinos")

    def test_pre_a_solo_el_gerente_activo_da_de_baja(self):
        """Precondición a y MD-47: el Vendedor, los demás roles, una cuenta inactiva o ``None`` reciben ``PermissionDenied``."""
        inactivo = crear_vendedor("inactivo@infoponia.com", activo=False)
        for actor in (crear_vendedor(), crear_agronomo(), crear_transportista(), inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                clientes.baja_cliente(actor, self.cliente.pk)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado_cliente, "activo")

    def test_pre_b_el_cliente_tiene_que_estar_activo(self):
        """Precondición b: uno inactivo se rechaza con ``cliente_inactivo`` y no se audita."""
        inactivo = cliente(cuit="30000000090", activo=False)
        with self.assertRaises(ValidationError) as contexto:
            clientes.baja_cliente(self.gerente, inactivo.pk)
        self.assertEqual([e.code for e in contexto.exception.error_list], ["cliente_inactivo"])
        self.assertFalse(RegistroAuditoria.objects.filter(accion="baja_cliente").exists())

    def test_pre_a_un_cliente_inexistente_da_404(self):
        """D-28: un id inexistente es 404."""
        with self.assertRaises(Http404):
            clientes.baja_cliente(self.gerente, 999999)

    def test_post_a_pasa_a_inactivo_y_sus_direcciones_no_cambian(self):
        """Postcondición a: el cliente pasa a «inactivo»; sus direcciones no cambian."""
        vinculo = direccion_de_cliente(self.cliente)
        devuelto = clientes.baja_cliente(self.gerente, self.cliente.pk)
        self.assertEqual(devuelto.pk, self.cliente.pk)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado_cliente, Cliente.Estado.INACTIVO)
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.direccion.estado_direccion, "activo")
        self.assertEqual(self.cliente.direcciones.count(), 1)

    def test_regla_1_la_baja_no_se_bloquea_y_los_demas_datos_no_cambian(self):
        """Regla 1: la baja no se bloquea nunca; el resto de los datos del cliente queda igual (la baja no borra datos, regla 3)."""
        antes = Cliente.objects.values().get(pk=self.cliente.pk)
        clientes.baja_cliente(self.gerente, self.cliente.pk)
        despues = Cliente.objects.values().get(pk=self.cliente.pk)
        self.assertEqual({**antes, "estado_cliente": "inactivo"}, despues)

    def test_regla_1_pendientes_del_cliente_devuelve_una_lista_vacia_en_com_01(self):
        """Regla 1: lo pendiente (se completa en COM-02, COM-03, COM-06 y COM-08a): en COM-01, ``[]``."""
        self.assertEqual(clientes.pendientes_del_cliente(self.cliente, self.gerente), [])

    def test_post_c_audita_la_baja_con_el_cambio_de_estado(self):
        """Postcondición c y D-36: ``baja_cliente`` con usuario, el cliente afectado y el cambio de estado."""
        clientes.baja_cliente(self.gerente, self.cliente.pk)
        registro = RegistroAuditoria.objects.get(accion="baja_cliente")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual([afectado["id"] for afectado in registro.afectados], [self.cliente.pk])
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
