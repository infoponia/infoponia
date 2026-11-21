# Pruebas de la migración de datos `0002_cargar_categorias_del_sistema` de `inventario` (INV-01, paso 1): las cuatro categorías
# del sistema sobre tablas vacías, la idempotencia, que no pisa el nombre y que no se pueden renombrar ni dar de baja desde la
# base. Fuente: regla 1 de 8.23, CMP-ALT-TIN regla 4 y docs/patrones/datos_de_migracion.md («Las categorías del sistema»).
# La migración se prueba sobre tablas vacías y dentro de una prueba (`TestCase`), sin depender del estado de la base.

import importlib

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, tag

from inventario import categorias
from inventario.models import TipoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, insumo

migracion = importlib.import_module("inventario.migrations.0002_cargar_categorias_del_sistema")


def del_sistema():
    return TipoInsumo.objects.filter(es_del_sistema=True)


class CategoriasDelSistemaMigracionTests(ConDatosDeInventario, TestCase):
    """La migración de datos carga las cuatro categorías (regla 4 de CMP-ALT-TIN)."""

    def vaciar(self):
        TipoInsumo.objects.all().delete()

    def test_regla_cmp_alt_tin_4_carga_cuatro_categorias_sobre_tablas_vacias(self):
        """CMP-ALT-TIN regla 4: Semillas, Envases, Repuestos de hardware e Infraestructura, con `codigo` fijo, del sistema,
        sin consumo directo y activas."""
        self.vaciar()
        migracion.cargar(apps, None)
        cargadas = {c.codigo: c for c in del_sistema()}
        self.assertEqual(
            {codigo: c.nombre_tipo_insumo for codigo, c in cargadas.items()},
            {
                "semillas": "Semillas",
                "envases": "Envases",
                "repuestos_de_hardware": "Repuestos de hardware",
                "infraestructura": "Infraestructura",
            },
        )
        for c in cargadas.values():
            self.assertEqual(c.consumo_directo, "no_admite")
            self.assertEqual(c.estado_tipo_insumo, "activo")
            self.assertTrue(c.es_del_sistema)

    def test_regla_cmp_alt_tin_4_son_cuatro_y_no_tres(self):
        """CMP-ALT-TIN regla 4: manda el CU (cuatro), no el prototipo (tres): falta Infraestructura en el prototipo."""
        self.vaciar()
        migracion.cargar(apps, None)
        self.assertEqual(del_sistema().count(), 4)
        self.assertTrue(TipoInsumo.objects.filter(codigo=categorias.INFRAESTRUCTURA).exists())

    def test_regla_cmp_alt_tin_4_no_carga_las_categorias_de_ejemplo_del_prototipo(self):
        """CMP-ALT-TIN («Cómo se aplica»): limpieza, nutrientes y similares las crea la organización: no se cargan."""
        self.vaciar()
        migracion.cargar(apps, None)
        self.assertEqual(TipoInsumo.objects.exclude(es_del_sistema=True).count(), 0)

    def test_regla_cmp_alt_tin_4_las_constantes_coinciden_con_la_migracion(self):
        """Los códigos y nombres de `categorias.py` son los de la migración (una migración no importa código; esta prueba evita
        que se separen)."""
        self.assertEqual(categorias.CATEGORIAS_DEL_SISTEMA, migracion.CATEGORIAS_DEL_SISTEMA)

    def test_regla_cmp_alt_tin_4_es_idempotente(self):
        """Datos de migración: correrla dos veces no duplica."""
        self.vaciar()
        migracion.cargar(apps, None)
        migracion.cargar(apps, None)
        self.assertEqual(del_sistema().count(), 4)

    def test_regla_cmp_alt_tin_4_no_pisa_el_nombre_de_una_fila_existente(self):
        """Datos de migración: el nombre inicial se toma solo al crear (si ya está la fila, no se revierte)."""
        TipoInsumo.objects.filter(codigo="envases").update(consumo_directo="no_admite")  # fila existente, sin cambios
        antes = TipoInsumo.objects.get(codigo="envases").nombre_tipo_insumo
        migracion.cargar(apps, None)
        self.assertEqual(TipoInsumo.objects.get(codigo="envases").nombre_tipo_insumo, antes)

    def test_regla_cmp_alt_tin_4_no_toca_las_categorias_de_la_organizacion(self):
        """Datos de migración: las categorías comunes quedan como están."""
        TipoInsumo.objects.create(nombre_tipo_insumo="Limpieza", consumo_directo="como_gasto")
        migracion.cargar(apps, None)
        self.assertEqual(TipoInsumo.objects.get(nombre_tipo_insumo="Limpieza").consumo_directo, "como_gasto")

    def test_regla_cmp_alt_tin_4_descargar_borra_las_cuatro_si_nadie_las_usa(self):
        """Datos de migración: la vuelta borra las cuatro filas si ningún insumo las usa."""
        migracion.descargar(apps, None)
        self.assertEqual(del_sistema().count(), 0)

    def test_regla_cmp_alt_tin_4_descargar_no_borra_nada_si_un_insumo_las_usa(self):
        """Datos de migración: la vuelta no borra datos de la organización: si un insumo usa una, no se borra ninguna."""
        insumo("Sobres", tipo=TipoInsumo.objects.get(codigo="envases"), unidad="unidad")
        migracion.descargar(apps, None)
        self.assertEqual(del_sistema().count(), 4)

    def test_regla_cmp_mod_tin_3_no_se_pueden_dar_de_baja_desde_la_base(self):
        """CMP-MOD-TIN regla 3: la base impide dar de baja cualquiera de las cuatro."""
        for categoria in del_sistema():
            with self.subTest(codigo=categoria.codigo):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    TipoInsumo.objects.filter(pk=categoria.pk).update(estado_tipo_insumo="inactivo")

    def test_regla_cmp_mod_tin_3_no_se_pueden_renombrar_desde_la_base(self):
        """CMP-MOD-TIN regla 3: la base impide renombrar cualquiera de las cuatro."""
        for categoria in del_sistema():
            with self.subTest(codigo=categoria.codigo):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    TipoInsumo.objects.filter(pk=categoria.pk).update(nombre_tipo_insumo="Otro nombre")

    def test_regla_cmp_alt_tin_4_no_se_puede_crear_otra_del_sistema(self):
        """CMP-ALT-TIN regla 4: desde la base no se agrega una quinta categoría del sistema."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoInsumo.objects.create(
                nombre_tipo_insumo="Fertilizantes",
                consumo_directo="no_admite",
                es_del_sistema=True,
                codigo="fertilizantes",
            )

    def test_regla_cmp_alt_tin_4_las_categorias_existen_tras_migrate(self):
        """Verificación a mano 1: tras `migrate` están las cuatro (la base de pruebas se arma con las migraciones)."""
        self.assertEqual(
            sorted(del_sistema().values_list("codigo", flat=True)),
            ["envases", "infraestructura", "repuestos_de_hardware", "semillas"],
        )


@tag("migracion")
class CategoriasDelSistemaMigracionDeEsquemaTests(TransactionTestCase):
    """La migración de datos aplicada y revertida de punta a punta con ``MigrationExecutor`` (desarma y rearma el esquema de
    la base de pruebas: por eso lleva la etiqueta ``migracion`` y no corre en paralelo)."""

    ANTERIOR = [("inventario", "0001_esquema_inicial")]
    ESTA = [("inventario", "0002_cargar_categorias_del_sistema")]

    def migrar_a(self, destino):
        ejecutor = MigrationExecutor(connection)
        ejecutor.migrate(destino)
        return ejecutor.loader.project_state(destino).apps

    def tearDown(self):
        # Deja la base de pruebas con todas las migraciones aplicadas para las pruebas que siguen.
        ejecutor = MigrationExecutor(connection)
        ejecutor.migrate(ejecutor.loader.graph.leaf_nodes())

    def test_regla_cmp_alt_tin_4_migrar_carga_las_cuatro_y_volver_atras_las_borra(self):
        """CMP-ALT-TIN regla 4 y datos de migración: aplicar la 0002 deja las cuatro categorías; revertirla las borra (ningún
        insumo las usa); aplicarla de nuevo las vuelve a cargar sin duplicar."""
        modelos = self.migrar_a(self.ANTERIOR)
        self.assertEqual(modelos.get_model("inventario", "TipoInsumo").objects.count(), 0)
        modelos = self.migrar_a(self.ESTA)
        self.assertEqual(
            sorted(modelos.get_model("inventario", "TipoInsumo").objects.values_list("codigo", flat=True)),
            ["envases", "infraestructura", "repuestos_de_hardware", "semillas"],
        )
        modelos = self.migrar_a(self.ANTERIOR)
        self.assertEqual(modelos.get_model("inventario", "TipoInsumo").objects.count(), 0)
        modelos = self.migrar_a(self.ESTA)
        self.assertEqual(modelos.get_model("inventario", "TipoInsumo").objects.count(), 4)
