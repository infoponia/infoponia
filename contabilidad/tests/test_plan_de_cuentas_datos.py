# Pruebas del plan de cuentas (CON-02 paso 2, D-84 punto 7, MD-118): la migración de datos 0005, las constantes y las descripciones del
# código, y la consulta `plan.arbol()` / `plan.cuenta()`. La migración se prueba sobre tablas vacías dentro de un `TestCase` (patrón de
# `docs/patrones/datos_de_migracion.md`): no desarma el esquema, así que no lleva la etiqueta `migracion`.
import importlib

from django.apps import apps
from django.test import TestCase

from contabilidad import cuentas
from contabilidad.models import CuentaContable
from contabilidad.servicios import plan
from contabilidad.tests.fabricas import PlanDeCuentasMixin

MIGRACION = importlib.import_module("contabilidad.migrations.0005_plan_de_cuentas")

# El plan aprobado de `docs/modelo/contabilidad.md` (MD-118; H5, H6, H7 y la 2.1.02 de MD-123), escrito acá a propósito: así la
# prueba compara la migración contra el documento y no contra sí misma.
PLAN_APROBADO = {
    "1.1.01": ("Caja", "activo"),
    "1.1.02": ("Banco c/c", "activo"),
    "1.1.03": ("Deudores por Ventas", "activo"),
    "1.1.04": ("Insumos en Stock", "activo"),
    "1.1.05": ("Productos en Proceso", "activo"),
    "1.1.06": ("Productos Terminados", "activo"),
    "2.1.01": ("Proveedores", "pasivo"),
    "2.1.02": ("Indemnizaciones a Pagar", "pasivo"),
    "3.1.01": ("Capital Inicial", "patrimonio_neto"),
    "4.1.01": ("Ventas", "resultado_positivo"),
    "4.1.02": ("Indemnizaciones por Atraso en el Pago", "resultado_positivo"),
    "4.1.03": ("Otros Ingresos", "resultado_positivo"),
    "5.1.01": ("Costo de Producción Vendida", "resultado_negativo"),
    "5.1.02": ("Pérdidas por Mermas", "resultado_negativo"),
    "5.1.03": ("Gastos de Producción", "resultado_negativo"),
    "5.1.04": ("Indemnizaciones por Incumplimiento a Cliente", "resultado_negativo"),
    "5.1.05": ("Indemnizaciones por Resolución de Contratos", "resultado_negativo"),
    "5.1.06": ("Diferencias de Inventario de Insumos", "resultado_negativo"),
    "5.1.07": ("Gastos Generales", "resultado_negativo"),
}


class PlanDeCuentasMigracionTests(TestCase):
    """La migración de datos 0005 (D-84 punto 7): carga, idempotencia e inversa. Parte de tablas vacías."""

    def setUp(self):
        CuentaContable.objects.all().delete()  # el queryset de cuentas no es inmutable; la transacción de la prueba lo deshace

    def _cuentas(self):
        return {c.codigo_cuenta: (c.nombre_cuenta, c.tipo_cuenta) for c in CuentaContable.objects.all()}

    def test_d84_la_migracion_carga_las_19_cuentas_del_plan_aprobado(self):
        """D-84 punto 7: la migración carga las 19 cuentas (las 18 de H5/H6/H7 más la 2.1.02), idénticas a `docs/modelo/contabilidad.md`."""
        MIGRACION.cargar(apps, None)

        self.assertEqual(CuentaContable.objects.count(), 19)
        self.assertEqual(self._cuentas(), PLAN_APROBADO)

    def test_d84_la_migracion_es_idempotente(self):
        """D-84 punto 7: `update_or_create` por código; correrla dos veces no duplica."""
        MIGRACION.cargar(apps, None)
        MIGRACION.cargar(apps, None)

        self.assertEqual(CuentaContable.objects.count(), 19)
        self.assertEqual(self._cuentas(), PLAN_APROBADO)

    def test_d84_la_migracion_repone_el_nombre_y_el_tipo_de_una_cuenta_existente(self):
        """D-84 punto 7: `update_or_create` por `codigo_cuenta` deja la cuenta como el plan aprobado, sin duplicarla."""
        CuentaContable.objects.create(codigo_cuenta="1.1.01", nombre_cuenta="Caja vieja", tipo_cuenta="pasivo")
        MIGRACION.cargar(apps, None)

        self.assertEqual(self._cuentas(), PLAN_APROBADO)

    def test_d84_la_inversa_no_hace_nada(self):
        """D-84 punto 7: la inversa no hace nada (las cuentas pueden tener movimientos)."""
        MIGRACION.cargar(apps, None)
        MIGRACION.descargar(apps, None)

        self.assertEqual(CuentaContable.objects.count(), 19)

    def test_d84_la_migracion_depende_de_la_de_esquema(self):
        """CON-02: la 0005 (datos) corre después de la 0004 (esquema)."""
        self.assertEqual(MIGRACION.Migration.dependencies, [("contabilidad", "0004_nucleo_contable")])


class PlanDeCuentasConstantesTests(PlanDeCuentasMixin, TestCase):
    """Las constantes y descripciones de `contabilidad/cuentas.py` contra el plan cargado (D-84 punto 7, regla 3 de CON-CNS-PCT)."""

    def test_d84_el_plan_cargado_por_la_migracion_tiene_19_cuentas(self):
        """D-84 punto 7: con la base de pruebas lista (migración y mixin), están las 19 cuentas del plan aprobado."""
        self.assertEqual(CuentaContable.objects.count(), 19)

    def test_d84_las_constantes_son_las_19_cuentas_del_plan(self):
        """D-84 punto 7: una constante por cuenta, cada una con el código del plan aprobado y sin repetidos."""
        self.assertEqual(len(cuentas.TODAS), 19)
        self.assertEqual(set(cuentas.TODAS), set(PLAN_APROBADO))
        self.assertEqual(cuentas.CAJA, "1.1.01")
        self.assertEqual(cuentas.PROVEEDORES, "2.1.01")
        self.assertEqual(cuentas.INDEMNIZACIONES_A_PAGAR, "2.1.02")
        self.assertEqual(cuentas.GASTOS_GENERALES, "5.1.07")

    def test_d84_las_constantes_coinciden_con_los_valores_de_la_migracion(self):
        """D-84 punto 7: los valores escritos en la migración y las constantes del código no se separan."""
        self.assertEqual({codigo for codigo, _, _ in MIGRACION.CUENTAS}, set(cuentas.TODAS))
        self.assertEqual({codigo: (nombre, tipo) for codigo, nombre, tipo in MIGRACION.CUENTAS}, PLAN_APROBADO)

    def test_regla_3_cada_cuenta_tiene_su_descripcion(self):
        """Regla 3 de CON-CNS-PCT: cada cuenta del plan tiene su texto de «para qué se usa y qué casos de uso la mueven»."""
        self.assertEqual(set(cuentas.DESCRIPCION_DE_CUENTA), set(PLAN_APROBADO))
        for codigo in PLAN_APROBADO:
            self.assertTrue(cuentas.DESCRIPCION_DE_CUENTA[codigo].strip(), codigo)

    def test_d84_debe_y_haber_valen_lo_que_los_movimientos(self):
        """docs/api/asientos.md, «Constantes»: `DEBE` y `HABER` se importan de `constantes` y de `cuentas`, y valen `"D"` y `"H"`."""
        from contabilidad.constantes import DEBE, HABER
        from contabilidad.models import MovimientoContable

        self.assertEqual((DEBE, HABER), ("D", "H"))
        self.assertEqual((cuentas.DEBE, cuentas.HABER), (DEBE, HABER))
        self.assertEqual((MovimientoContable.Tipo.DEBE, MovimientoContable.Tipo.HABER), (DEBE, HABER))


class PlanDeCuentasConsultaTests(PlanDeCuentasMixin, TestCase):
    """`plan.arbol()` y `plan.cuenta()` (D-84 punto 7; regla 2 de CON-CNS-PCT)."""

    def test_regla_2_el_arbol_es_completo_y_ordenado(self):
        """Regla 2 de CON-CNS-PCT: árbol por rubro y subrubro, con los cinco rubros y las 19 cuentas ordenadas por código."""
        arbol = plan.arbol()

        self.assertEqual([r.codigo for r in arbol], ["1", "2", "3", "4", "5"])
        self.assertEqual([r.nombre for r in arbol], ["Activo", "Pasivo", "Patrimonio neto", "Ingresos", "Egresos"])
        self.assertEqual(
            [(s.codigo, s.nombre) for r in arbol for s in r.subrubros],
            [
                ("1.1", "Activo corriente"),
                ("2.1", "Pasivo corriente"),
                ("3.1", "Capital"),
                ("4.1", "Ingresos operativos"),
                ("5.1", "Egresos operativos"),
            ],
        )
        codigos = [c.codigo_cuenta for r in arbol for s in r.subrubros for c in s.cuentas]
        self.assertEqual(codigos, sorted(PLAN_APROBADO))

    def test_regla_2_cada_cuenta_cuelga_de_su_subrubro(self):
        """Regla 2 de CON-CNS-PCT: las cuentas de cada subrubro empiezan con su código."""
        for rubro in plan.arbol():
            for subrubro in rubro.subrubros:
                self.assertTrue(subrubro.cuentas)
                for cuenta in subrubro.cuentas:
                    self.assertTrue(cuenta.codigo_cuenta.startswith(subrubro.codigo + "."), cuenta.codigo_cuenta)

    def test_regla_6_el_arbol_se_arma_con_una_sola_consulta(self):
        """Regla 6 y «sin consultas por fila» (plan_de_cuentas.md): armar el árbol cuesta una consulta, no una por cuenta."""
        with self.assertNumQueries(1):
            plan.arbol()

    def test_regla_2_cuenta_devuelve_la_cuenta_por_su_codigo(self):
        """`plan.cuenta(codigo)` devuelve la `CuentaContable`; un código que no existe lanza `DoesNotExist`."""
        caja = plan.cuenta(cuentas.CAJA)
        self.assertEqual((caja.nombre_cuenta, caja.tipo_cuenta), ("Caja", CuentaContable.Tipo.ACTIVO))
        with self.assertRaises(CuentaContable.DoesNotExist):
            plan.cuenta("9.9.99")
