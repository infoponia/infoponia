# Pruebas del traspaso de compra-ventas al Vendedor nuevo de un invernadero (COM-02, D-60; docs/casos_de_uso/comercial/compra_venta.md,
# «Cambio de Vendedor de un invernadero»): `contar_contratos` y `traspasar_contratos`, registrados en `maestros.extensiones.registrar_traspaso`,
# y la punta a punta con `modificar_invernadero`. Lo que pasa depende de si el saliente conserva otros invernaderos (D-60, punto 2).

from django.test import TestCase

from comercial.models import CompraVenta
from comercial.servicios import registrantes
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    escenario_comercial,
    reserva,
    segundo_invernadero,
    verificar_invariantes_de_reservas,
)
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros import extensiones
from maestros.models import Invernadero
from maestros.servicios import invernaderos
from maestros.tests.fabricas import crear_vendedor
from maestros.tests.test_prod_mod_inv import datos_de
from produccion.tests.fabricas import lote_maduro


class TraspasoDeVendedorTests(ConDatosDeInventario, TestCase):
    """D-60: qué compra-ventas pasan al Vendedor nuevo."""

    def setUp(self):
        self.e = escenario_comercial()
        self.nuevo = crear_vendedor(email="nuevo@infoponia.com")
        self.addCleanup(verificar_invariantes_de_reservas)

    def venta(self, estado="abierta", **extra):
        """Una compra-venta del Vendedor del escenario con su detalle."""
        venta = compra_venta(self.e, estado=estado, **extra)
        detalle(venta, self.e.variedad, 10)
        return venta

    def contar(self, saliente=None, entrante=None):
        """`contar_traspaso` de `maestros` (todos los registrantes) para el rol Vendedor."""
        return extensiones.contar_traspaso(self.e.invernadero, "vendedor", saliente or self.e.vendedor, entrante or self.nuevo)

    def traspasar(self, saliente=None, entrante=None, rol="vendedor"):
        """`traspasar` de `maestros` (todos los registrantes)."""
        return extensiones.traspasar(
            crear_gerente(), self.e.invernadero, rol, saliente or self.e.vendedor, entrante or self.nuevo
        )

    def test_regla_8_21_8_sin_otro_invernadero_pasan_todas_las_abiertas_y_pendientes(self):
        """D-60, punto 2: si el saliente no conserva otro invernadero activo, pasan TODAS sus compra-ventas abiertas o pendientes de
        decisión (no las concretadas ni las canceladas)."""
        abierta, pendiente = self.venta(), self.venta(estado="pendiente_decision")
        concretada, cancelada = self.venta(estado="concretada"), self.venta(estado="cancelada")
        self.assertEqual(self.contar(), [("Compra-ventas abiertas", 2)])
        tocadas = self.traspasar()
        self.assertEqual(sorted(t.pk for t in tocadas), sorted([abierta.pk, pendiente.pk]))
        vendedor = lambda v: CompraVenta.objects.get(pk=v.pk).vendedor_id  # noqa: E731
        self.assertEqual([vendedor(v) for v in (abierta, pendiente)], [self.nuevo.pk] * 2)
        self.assertEqual([vendedor(v) for v in (concretada, cancelada)], [self.e.vendedor.pk] * 2)

    def test_regla_8_21_8_si_conserva_otro_invernadero_pasan_solo_las_atadas_a_este(self):
        """D-60, punto 2: si el saliente conserva otro invernadero activo, pasan solo las atadas a este: un retiro en él, o las que tienen
        todas sus reservas no liberadas en él; las que salen de varios invernaderos o del otro siguen con el saliente."""
        sur = segundo_invernadero(self.e)
        lote_norte, lote_sur = lote_maduro(self.e, 100), lote_maduro(sur, 100)
        con_retiro = self.venta(modalidad="retiro", retiro=self.e.invernadero)
        solo_norte = self.venta()
        reserva(solo_norte.detalles.get(), [(lote_norte, 5)])
        solo_sur = self.venta()
        reserva(solo_sur.detalles.get(), [(lote_sur, 5)])
        de_los_dos = self.venta()
        reserva(de_los_dos.detalles.get(), [(lote_norte, 3)])
        reserva(de_los_dos.detalles.get(), [(lote_sur, 3)])
        con_liberada = self.venta()
        reserva(con_liberada.detalles.get(), [(lote_norte, 4)])
        reserva(con_liberada.detalles.get(), [(lote_sur, 4)], estado="liberada")
        sin_reservas = self.venta()
        self.assertEqual(self.contar(), [("Compra-ventas abiertas", 3)])
        self.traspasar()
        pasaron = set(CompraVenta.objects.filter(vendedor=self.nuevo).values_list("pk", flat=True))
        self.assertEqual(pasaron, {con_retiro.pk, solo_norte.pk, con_liberada.pk})
        quedan = set(CompraVenta.objects.filter(vendedor=self.e.vendedor).values_list("pk", flat=True))
        self.assertEqual(quedan, {solo_sur.pk, de_los_dos.pk, sin_reservas.pk})

    def test_regla_8_21_8_un_invernadero_inactivo_del_saliente_no_cuenta_como_conservado(self):
        """D-60, punto 2: «otro invernadero ACTIVO»: si el otro está inactivo, el saliente no conserva ninguno y pasan todas."""
        sur = segundo_invernadero(self.e)
        Invernadero.objects.filter(pk=sur.invernadero.pk).update(estado_invernadero="inactivo")
        venta = self.venta()
        self.traspasar()
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).vendedor_id, self.nuevo.pk)

    def test_regla_8_21_8_las_reservas_no_se_mueven(self):
        """D-60, punto 3 (regla 8 de 8.21): cambia solo el `vendedor` del contrato; las reservas siguen donde estaban."""
        lote = lote_maduro(self.e, 100)
        venta = self.venta()
        r = reserva(venta.detalles.get(), [(lote, 5)])
        self.traspasar()
        r.refresh_from_db()
        self.assertEqual((r.invernadero_id, r.estado_reserva), (self.e.invernadero.pk, "activa"))

    def test_regla_8_21_8_sin_entrante_o_sin_saliente_o_con_otro_rol_no_pasa_nada(self):
        """D-60, punto 5: la baja de un Vendedor (sin entrante) no reasigna contratos (MD-60); tampoco con otro rol."""
        venta = self.venta()
        gerente = crear_gerente()
        self.assertEqual(registrantes.contar_contratos(self.e.invernadero, "vendedor", self.e.vendedor, None), [])
        self.assertEqual(registrantes.traspasar_contratos(gerente, self.e.invernadero, "vendedor", self.e.vendedor, None), [])
        self.assertEqual(registrantes.traspasar_contratos(gerente, self.e.invernadero, "vendedor", None, self.nuevo), [])
        self.assertEqual(registrantes.contar_contratos(self.e.invernadero, "capataz", self.e.vendedor, self.nuevo), [])
        self.assertEqual(registrantes.traspasar_contratos(gerente, self.e.invernadero, "capataz", self.e.vendedor, self.nuevo), [])
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).vendedor_id, self.e.vendedor.pk)

    def test_regla_8_21_8_las_ventas_de_otro_vendedor_no_se_tocan(self):
        """Solo las del saliente."""
        otro = escenario_comercial(sufijo="2")
        ajena = compra_venta(otro)
        self.venta()
        self.traspasar()
        self.assertEqual(CompraVenta.objects.get(pk=ajena.pk).vendedor_id, otro.vendedor.pk)

    def test_punta_a_punta_modificar_invernadero_avisa_la_cantidad_y_deja_las_ventas_en_su_registro(self):
        """PROD-MOD-INV, D-60 punto 4 y D-36: la ventana avisa «Compra-ventas abiertas: 2»; al confirmar, las dos ventas son del Vendedor
        nuevo y quedan entre los afectados de `modificacion_invernadero`."""
        a, b = self.venta(), self.venta()
        datos = datos_de(self.e.invernadero) | {"vendedor_id": self.nuevo.pk}
        gerente = crear_gerente()
        sin_confirmar = None
        try:
            invernaderos.modificar_invernadero(gerente, self.e.invernadero.pk, **datos)
        except Exception as error:  # el aviso de personal pide confirmar antes de guardar
            sin_confirmar = error
        self.assertIsNotNone(sin_confirmar)
        invernaderos.modificar_invernadero(gerente, self.e.invernadero.pk, **(datos | {"personal_confirmado": True}))
        self.assertEqual(set(CompraVenta.objects.filter(vendedor=self.nuevo).values_list("pk", flat=True)), {a.pk, b.pk})
        registro = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO).latest("id")
        modelos = [(x["modelo"], x["id"]) for x in registro.afectados]
        for venta in (a, b):
            self.assertIn(("comercial.compraventa", venta.pk), modelos)

    def test_ext_el_aviso_de_personal_cuenta_las_compra_ventas_que_recibe_el_vendedor_nuevo(self):
        """PROD-MOD-INV, regla 2 y postcondición c: `contar_traspaso` suma «Compra-ventas abiertas» a lo que recibe el entrante."""
        self.venta(), self.venta()
        self.assertIn(("Compra-ventas abiertas", 2), invernaderos._aviso_de_personal(self.e.invernadero, {"vendedor": (self.e.vendedor, self.nuevo)})[0]["recibe"])
