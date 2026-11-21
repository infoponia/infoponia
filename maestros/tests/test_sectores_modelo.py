# Pruebas de los modelos de MAE-03 (paso 1): las restricciones de la base de sectores, cultivos, variedades, ciclos y
# etapas, ``Invernadero.tiene_sectores`` y la migración de datos de los cinco tipos de etapa (docs/modelo/maestros.md,
# «Tipo de etapa», «SectorProduccion» y «Cultivo»; MD-52, MD-74, MD-71).

import importlib

from django.apps import apps
from django.db import DataError, IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from maestros.models import Cultivo, EtapaProductiva, SectorProduccion, TipoEtapa
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    crear_ciclo,
    crear_cultivo,
    crear_invernadero,
    crear_sector,
    crear_variedad,
    tipo_etapa,
)

TODOS = ["hoja_verde", "pastura", "frutos_grandes", "frutos_pequenos", "flores", "hierbas"]

# Los cinco tipos tal como los fija la ficha «Tipo de etapa» de docs/modelo/maestros.md (MD-52).
TIPOS_DE_LA_FICHA = {
    "germinacion": ("Germinación", 1, TODOS),
    "crecimiento": ("Crecimiento", 2, TODOS),
    "floracion": ("Floración", 3, ["frutos_grandes", "frutos_pequenos", "flores"]),
    "fructificacion": ("Fructificación", 4, ["frutos_grandes", "frutos_pequenos"]),
    "maduracion": ("Maduración", 5, TODOS),
}


class SectoresModeloTests(ConDatosDeMaestros, TestCase):
    """Restricciones de la base de los modelos de MAE-03."""

    def setUp(self):
        self.invernadero = crear_invernadero("Inv Uno")

    def test_regla_2_alt_sct_nombre_unico_en_el_invernadero_sin_distinguir_mayusculas(self):
        """PROD-ALT-SCT regla 2 / modelo (D-36 y D-30): único (invernadero, lower(nombre_sector))."""
        crear_sector(self.invernadero, "C-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_sector(self.invernadero, "c-1")

    def test_regla_2_alt_sct_el_nombre_repetido_cuenta_tambien_entre_los_inactivos(self):
        """PROD-ALT-SCT regla 2: se cuentan también los sectores dados de baja."""
        crear_sector(self.invernadero, "C-1", estado="inactivo")
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_sector(self.invernadero, "C-1")

    def test_regla_2_alt_sct_dos_invernaderos_pueden_repetir_el_nombre(self):
        """PROD-ALT-SCT regla 2: dos invernaderos pueden tener sectores con el mismo nombre."""
        crear_sector(self.invernadero, "C-1")
        otro = crear_invernadero("Inv Dos")
        crear_sector(otro, "C-1")
        self.assertEqual(SectorProduccion.objects.filter(nombre_sector="C-1").count(), 2)

    def test_regla_4_alt_sct_los_agujeros_deben_ser_mayores_que_cero(self):
        """PROD-ALT-SCT regla 4: cant_agujeros_total > 0 (restricción de la base)."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_sector(self.invernadero, "C-0", agujeros=0)

    def test_modelo_el_estado_del_sector_debe_ser_uno_de_los_tres(self):
        """docs/modelo/maestros.md, «SectorProduccion»: estado_sector en activo, fuera de servicio o inactivo."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_sector(self.invernadero, "C-9", estado="roto")
        crear_sector(self.invernadero, "C-2", estado="fuera_de_servicio")

    def test_modelo_el_invernadero_con_sectores_no_se_puede_borrar(self):
        """Todas las claves foráneas están protegidas (paso 1 de MAE-03)."""
        crear_sector(self.invernadero, "C-1")
        with self.assertRaises(ProtectedError):
            self.invernadero.delete()

    def test_modelo_el_tipo_de_etapa_usado_por_un_sector_no_se_puede_borrar(self):
        """R092: la clave foránea tipo_etapa está protegida."""
        crear_sector(self.invernadero, "C-1")
        with self.assertRaises(ProtectedError):
            tipo_etapa("germinacion").delete()

    def test_regla_2_alt_clt_nombre_de_cultivo_unico_sin_distinguir_mayusculas(self):
        """PROD-ALT-CLT regla 2: único lower(nombre_cultivo), activos o inactivos."""
        crear_cultivo("Lechuga", activo=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_cultivo("LECHUGA")

    def test_modelo_el_nombre_del_cultivo_admite_40_caracteres_y_no_41(self):
        """Modelo «Cultivo»: nombre_cultivo de hasta 40 caracteres (límite de esta ronda)."""
        crear_cultivo("a" * 40)
        with self.assertRaises(DataError), transaction.atomic():
            crear_cultivo("b" * 41)

    def test_modelo_el_estado_del_cultivo_debe_ser_activo_o_inactivo(self):
        """Modelo «Cultivo»: estado_cultivo en sus dos valores."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cultivo.objects.create(nombre_cultivo="Acelga", estado_cultivo="roto")

    def test_modelo_el_perfil_de_la_variedad_debe_ser_uno_de_los_seis(self):
        """Modelo «Variedad»: perfil_familia en la lista fija de seis perfiles."""
        cultivo = crear_cultivo()
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_variedad(cultivo, "Rara", perfil="inventado")
        crear_variedad(cultivo, "Crespa", perfil="hoja_verde")

    def test_modelo_el_estado_de_la_variedad_debe_ser_activo_o_inactivo(self):
        """Modelo «Variedad»: estado_variedad en sus dos valores."""
        cultivo = crear_cultivo()
        variedad = crear_variedad(cultivo)
        variedad.estado_variedad = "roto"
        with self.assertRaises(IntegrityError), transaction.atomic():
            variedad.save()

    def test_modelo_el_cultivo_con_variedades_no_se_puede_borrar(self):
        """R074: la clave foránea cultivo de Variedad está protegida."""
        cultivo = crear_cultivo()
        crear_variedad(cultivo)
        with self.assertRaises(ProtectedError):
            cultivo.delete()

    def test_modelo_una_etapa_por_tipo_en_cada_ciclo(self):
        """Modelo «EtapaProductiva»: restricción única (ciclo, tipo_etapa)."""
        ciclo = crear_ciclo(crear_variedad(crear_cultivo()))
        with self.assertRaises(IntegrityError), transaction.atomic():
            EtapaProductiva.objects.create(ciclo=ciclo, tipo_etapa=tipo_etapa("germinacion"), duracion_estimada_dias=5)

    def test_modelo_la_duracion_de_la_etapa_debe_ser_mayor_que_cero(self):
        """Modelo «EtapaProductiva»: duracion_estimada_dias > 0 (restricción de la base)."""
        ciclo = crear_ciclo(crear_variedad(crear_cultivo()))
        with self.assertRaises(IntegrityError), transaction.atomic():
            EtapaProductiva.objects.create(ciclo=ciclo, tipo_etapa=tipo_etapa("floracion"), duracion_estimada_dias=0)

    def test_modelo_cada_variedad_tiene_un_unico_ciclo(self):
        """R091: el ciclo es uno a uno con su variedad."""
        variedad = crear_variedad(crear_cultivo())
        crear_ciclo(variedad)
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_ciclo(variedad)

    def test_modelo_codigo_y_puesto_global_de_los_tipos_son_unicos(self):
        """Modelo «TipoEtapa»: codigo y puesto_global únicos."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoEtapa.objects.create(codigo="germinacion", nombre_etapa="Otra", puesto_global=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoEtapa.objects.create(codigo="nueva", nombre_etapa="Nueva", puesto_global=1)

    def test_modelo_el_puesto_global_va_de_1_a_5(self):
        """Modelo «TipoEtapa»: puesto_global de 1 a 5."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoEtapa.objects.create(codigo="nueva", nombre_etapa="Nueva", puesto_global=6)


class TieneSectoresTests(ConDatosDeMaestros, TestCase):
    """Invernadero.tiene_sectores (postcondición b de PROD-ALT-SCT, regla 3 de PROD-CNS-INV)."""

    def test_post_b_sin_sectores_es_falso(self):
        """PROD-ALT-SCT post b: un invernadero sin sectores muestra la marca «sin sectores»."""
        self.assertFalse(crear_invernadero("Inv Uno").tiene_sectores())

    def test_post_b_con_un_sector_activo_es_verdadero(self):
        """PROD-ALT-SCT post b: con un sector activo la marca desaparece."""
        invernadero = crear_invernadero("Inv Uno")
        crear_sector(invernadero)
        self.assertTrue(invernadero.tiene_sectores())

    def test_post_b_un_sector_fuera_de_servicio_cuenta(self):
        """Decisión de aplicación de sectores.md: cuentan los activos o fuera de servicio."""
        invernadero = crear_invernadero("Inv Uno")
        crear_sector(invernadero, estado="fuera_de_servicio")
        self.assertTrue(invernadero.tiene_sectores())

    def test_post_b_solo_con_sectores_dados_de_baja_es_falso(self):
        """Decisión de aplicación de sectores.md: los inactivos no cuentan."""
        invernadero = crear_invernadero("Inv Uno")
        crear_sector(invernadero, estado="inactivo")
        self.assertFalse(invernadero.tiene_sectores())

    def test_post_b_no_cuenta_los_sectores_de_otro_invernadero(self):
        """Los sectores son de su invernadero."""
        invernadero = crear_invernadero("Inv Uno")
        crear_sector(crear_invernadero("Inv Dos"))
        self.assertFalse(invernadero.tiene_sectores())


class CargarTiposDeEtapaTests(ConDatosDeMaestros, TestCase):
    """La migración de datos 0005_cargar_tipos_de_etapa (docs/patrones/datos_de_migracion.md)."""

    def setUp(self):
        self.migracion = importlib.import_module("maestros.migrations.0005_cargar_tipos_de_etapa")

    def test_ficha_los_cinco_tipos_cargados_coinciden_con_la_ficha(self):
        """docs/modelo/maestros.md, «Tipo de etapa» (MD-52): nombre, puesto y perfiles de cada tipo."""
        self.assertEqual(TipoEtapa.objects.count(), 5)
        for codigo, (nombre, puesto, perfiles) in TIPOS_DE_LA_FICHA.items():
            tipo = TipoEtapa.objects.get(codigo=codigo)
            self.assertEqual((tipo.nombre_etapa, tipo.puesto_global, tipo.perfiles_permitidos), (nombre, puesto, perfiles))

    def test_migracion_carga_sobre_tablas_vacias_y_descarga(self):
        """Se vacía la tabla, se llama a cargar, se cuentan las filas y se llama a descargar."""
        TipoEtapa.objects.all().delete()
        self.migracion.cargar(apps, None)
        self.assertEqual(TipoEtapa.objects.count(), 5)
        self.migracion.descargar(apps, None)
        self.assertEqual(TipoEtapa.objects.count(), 0)
        self.migracion.cargar(apps, None)  # deja la base como estaba

    def test_migracion_es_idempotente(self):
        """Correr cargar dos veces no duplica los tipos."""
        self.migracion.cargar(apps, None)
        self.migracion.cargar(apps, None)
        self.assertEqual(TipoEtapa.objects.count(), 5)

    def test_migracion_descargar_no_borra_si_un_sector_usa_un_tipo(self):
        """descargar no destruye datos del usuario: con sectores, no borra nada."""
        crear_sector(crear_invernadero("Inv Uno"))
        self.migracion.descargar(apps, None)
        self.assertEqual(TipoEtapa.objects.count(), 5)

    def test_migracion_los_valores_de_la_migracion_son_los_de_la_ficha(self):
        """Los valores escritos en la migración son los de la ficha (no se separan)."""
        de_la_migracion = {c: (n, p, list(perf)) for c, n, p, perf in self.migracion.TIPOS_DE_ETAPA}
        self.assertEqual(de_la_migracion, TIPOS_DE_LA_FICHA)
