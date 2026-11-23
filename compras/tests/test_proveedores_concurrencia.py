# Pruebas de concurrencia de los proveedores (CMP-01): dos pedidos a la vez con el mismo CUIT. Fuente: docs/casos_de_uso/compras/proveedores.md
# («Cómo se aplica», «Bloqueos»), docs/patrones/bloqueos.md («compras») y docs/patrones/abm.md, sección 4: la unicidad del CUIT la asegura la
# restricción ``UNIQUE`` de la base (no un bloqueo); el segundo pedido recibe el ``IntegrityError`` traducido al mismo error de campo
# (``cuit_repetido``), nunca un 500. Son ``TransactionTestCase`` con dos hilos y dos conexiones (``core/tests/concurrencia.py``).

from django.test import TransactionTestCase, tag

from compras.models import Proveedor
from compras.tests.fabricas import cuit_valido, datos_de, datos_de_alta, proveedor
from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, perezoso
from maestros.tests.fabricas import asegurar_datos_de_maestros

proveedores = perezoso("compras.servicios.proveedores")
ALTA = RegistroAuditoria.Accion.ALTA_PROVEEDOR
MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_PROVEEDOR


@tag("concurrencia")
class ProveedoresConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Dos pedidos a la vez sobre el mismo CUIT. Es un ``TransactionTestCase``: su ``flush`` vacía los datos que cargan las migraciones, así
    que hereda de ``ConDatosDeInventario`` y los asegura de nuevo en cada prueba."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.gerente = crear_gerente()

    def test_regla_2_dos_altas_con_el_mismo_cuit_crean_un_solo_proveedor(self):
        """CMP-ALT-PRV regla 2 (H14): una gana y la otra recibe ``cuit_repetido`` (la restricción única de la base la respalda), nunca un 500."""
        resultados = correr_a_la_vez(
            lambda: proveedores.alta_proveedor(self.gerente, datos_de_alta(razon_social="Semillas del Sur S. A.")),
            lambda: proveedores.alta_proveedor(self.gerente, datos_de_alta(razon_social="Agro Norte S. R. L.")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cuit_repetido"])
        self.assertEqual(Proveedor.objects.filter(cuit_proveedor=cuit_valido(1)).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ALTA).count(), 1)

    def test_regla_2_dos_altas_con_el_mismo_cuit_escrito_distinto_crean_un_solo_proveedor(self):
        """CMP-ALT-PRV regla 2: con guiones y sin guiones es el mismo CUIT; la segunda alta también recibe ``cuit_repetido``."""
        cuit = cuit_valido(1)
        resultados = correr_a_la_vez(
            lambda: proveedores.alta_proveedor(self.gerente, datos_de_alta(cuit=cuit)),
            lambda: proveedores.alta_proveedor(self.gerente, datos_de_alta(cuit=f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}")),
            primera="b",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cuit_repetido"])
        self.assertEqual(Proveedor.objects.count(), 1)

    def test_regla_1_de_mod_un_alta_y_una_modificacion_al_mismo_cuit_no_lo_duplican(self):
        """CMP-MOD-PRV regla 1 (H14): si una modificación pasa un proveedor a un CUIT que otra alta está usando, una gana y la otra recibe
        ``cuit_repetido``; el CUIT queda en un solo proveedor."""
        existente = proveedor("Agro Norte S. R. L.", n=2)
        resultados = correr_a_la_vez(
            lambda: proveedores.alta_proveedor(self.gerente, datos_de_alta(cuit=cuit_valido(5))),
            lambda: proveedores.modificar_proveedor(self.gerente, existente.pk, datos_de(existente, cuit=cuit_valido(5))),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cuit_repetido"])
        self.assertEqual(Proveedor.objects.filter(cuit_proveedor=cuit_valido(5)).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion__in=(ALTA, MODIFICACION)).count(), 1)

    def test_regla_2_dos_bajas_del_mismo_proveedor_una_sola_se_audita(self):
        """CMP-BAJ-PRV precondición b: con el proveedor bloqueado (``FOR NO KEY UPDATE``), la segunda baja espera, ve al proveedor ya inactivo
        y recibe ``proveedor_inactivo``; la baja se audita una sola vez."""
        existente = proveedor("Semillas del Sur S. A.", n=1)
        resultados = correr_a_la_vez(
            lambda: proveedores.baja_proveedor(self.gerente, existente.pk),
            lambda: proveedores.baja_proveedor(self.gerente, existente.pk),
            primera="a",
        )
        exitos = [r for r in resultados.values() if not isinstance(r, Exception)]
        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertEqual(errores[0].codigo, "proveedor_inactivo")
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA_PROVEEDOR).count(), 1)
