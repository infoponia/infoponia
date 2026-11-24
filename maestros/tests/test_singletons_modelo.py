# Pruebas de los dos singletons de MAE-04 (MD-89): una sola fila cada uno, valores iniciales, dominios en la base y la
# migración de datos 0007 sobre tablas vacías, que además coincide con los ``default`` del modelo.

import importlib

from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, tag

from maestros.models import PARAMETROS_DE_CONFIGURACION, ConfiguracionOperativa, PerfilOrganizacion
from maestros.tests.fabricas import ConDatosDeMaestros, asegurar_datos_de_maestros

MIGRACION = importlib.import_module("maestros.migrations.0007_cargar_configuracion_y_perfil")


class SingletonsModeloTests(ConDatosDeMaestros, TestCase):
    """MD-89: la base garantiza una sola fila de cada singleton."""

    def test_md89_la_migracion_deja_una_sola_fila_de_cada_una(self):
        """MD-89: hay exactamente una fila de configuración y una de perfil."""
        self.assertEqual(ConfiguracionOperativa.objects.count(), 1)
        self.assertEqual(PerfilOrganizacion.objects.count(), 1)

    def test_md89_una_segunda_fila_se_rechaza_en_la_base(self):
        """MD-89: otra fila con ``singleton=1`` viola la unicidad; con otro valor, viola el CheckConstraint."""
        for modelo, extra in ((ConfiguracionOperativa, {}), (PerfilOrganizacion, {"nombre_organizacion": "X"})):
            for singleton in (1, 2):
                with self.subTest(modelo=modelo.__name__, singleton=singleton):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        modelo.objects.create(singleton=singleton, **extra)
        self.assertEqual(ConfiguracionOperativa.objects.count(), 1)
        self.assertEqual(PerfilOrganizacion.objects.count(), 1)

    def test_regla_2_valores_iniciales_de_la_configuracion(self):
        """ADM-MOD-CFG regla 2: los valores iniciales de la ficha."""
        c = ConfiguracionOperativa.objects.get()
        esperados = {
            "porc_merma_maxima": 15, "dias_horizonte_cosecha": 30, "dias_aviso_vencimiento": 15,
            "dias_pre_reserva_suministro": 14, "dias_anticipacion_cosecha_compra_venta": 1,
            "dias_anticipacion_cosecha_suministro": 3, "dias_vigencia_enlace_confirmacion": 3,
            "dias_vigencia_enlace_faltante": 2, "dias_limite_cotizacion": 3, "dias_validez_cotizacion": 7,
            "porc_tolerancia_cobertura_pedido": 0, "cant_maxima_entregas_diarias": 10,
            "cant_max_ciudades_distintas_diarias": 3, "dias_aviso_vencimiento_camara": 3,
        }
        for campo, valor in esperados.items():
            with self.subTest(campo=campo):
                self.assertEqual(getattr(c, campo), valor)

    def test_d48_el_perfil_inicial_toma_el_nombre_de_la_variable_y_nada_mas(self):
        """D-48 y MD-89: el nombre inicial sale de NOMBRE_ORGANIZACION; lo demás está vacío."""
        p = PerfilOrganizacion.objects.get()
        self.assertEqual(p.nombre_organizacion, settings.NOMBRE_ORGANIZACION)
        for campo in ("cuit_organizacion", "telefono_organizacion", "email_organizacion", "direccion_organizacion",
                      "color_primario", "color_secundario", "color_terciario", "color_cuaternario"):
            with self.subTest(campo=campo):
                self.assertEqual(getattr(p, campo), "")

    def test_regla_3_los_dominios_los_garantiza_la_base(self):
        """ADM-MOD-CFG regla 3: un valor fuera de dominio se rechaza en la base, aunque se salte el servicio."""
        fuera = {"porc_merma_maxima": (0, 101), "porc_tolerancia_cobertura_pedido": (-1, 101)}
        for campo, _, _, minimo, maximo in PARAMETROS_DE_CONFIGURACION:
            valores = list(fuera.get(campo, (minimo - 1,)))
            for valor in valores:
                with self.subTest(campo=campo, valor=valor):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        ConfiguracionOperativa.objects.filter(singleton=1).update(**{campo: valor})
            # Los extremos del dominio sí valen.
            ConfiguracionOperativa.objects.filter(singleton=1).update(**{campo: minimo})

    def test_regla_3_el_modelo_y_el_dominio_declarado_coinciden_con_los_default(self):
        """Los ``default`` del modelo son los valores iniciales de la ficha (la lista de parámetros del modelo)."""
        for campo, _, inicial, _, _ in PARAMETROS_DE_CONFIGURACION:
            with self.subTest(campo=campo):
                self.assertEqual(ConfiguracionOperativa._meta.get_field(campo).default, inicial)


@tag("migracion")
class MigracionConfiguracionYPerfilTests(TransactionTestCase):
    """La migración 0007 sobre tablas vacías: crea, es idempotente, no pisa lo cambiado y coincide con el modelo."""

    def setUp(self):
        ConfiguracionOperativa.objects.all().delete()
        PerfilOrganizacion.objects.all().delete()

    def tearDown(self):
        # Un TransactionTestCase deja la base vacía: se vuelven a cargar las filas para las clases que siguen.
        asegurar_datos_de_maestros()

    def test_md89_cargar_crea_una_fila_de_cada_una(self):
        """MD-89: ``cargar`` sobre tablas vacías crea las dos filas; el nombre sale de NOMBRE_ORGANIZACION."""
        MIGRACION.cargar(apps, None)
        self.assertEqual(ConfiguracionOperativa.objects.count(), 1)
        self.assertEqual(PerfilOrganizacion.objects.get().nombre_organizacion, settings.NOMBRE_ORGANIZACION)

    def test_md89_cargar_dos_veces_no_duplica_ni_pisa_lo_cambiado(self):
        """Idempotente: una segunda ejecución no duplica ni revierte lo que el Gerente cambió (ni el nombre)."""
        MIGRACION.cargar(apps, None)
        ConfiguracionOperativa.objects.update(porc_merma_maxima=40)
        PerfilOrganizacion.objects.update(nombre_organizacion="Vivero Los Álamos")

        MIGRACION.cargar(apps, None)

        self.assertEqual(ConfiguracionOperativa.objects.count(), 1)
        self.assertEqual(ConfiguracionOperativa.objects.get().porc_merma_maxima, 40)
        self.assertEqual(PerfilOrganizacion.objects.get().nombre_organizacion, "Vivero Los Álamos")

    def test_md89_descargar_no_borra_los_datos(self):
        """``descargar`` no hace nada: no destruye datos de la organización."""
        MIGRACION.cargar(apps, None)
        MIGRACION.descargar(apps, None)
        self.assertEqual(ConfiguracionOperativa.objects.count(), 1)
        self.assertEqual(PerfilOrganizacion.objects.count(), 1)

    def test_md89_los_valores_de_la_migracion_coinciden_con_los_default_del_modelo(self):
        """Los valores escritos en la migración y los ``default`` del modelo no se separan."""
        for campo, valor in MIGRACION.VALORES_INICIALES_CONFIGURACION.items():
            with self.subTest(campo=campo):
                self.assertEqual(ConfiguracionOperativa._meta.get_field(campo).default, valor)
        self.assertEqual(
            set(MIGRACION.VALORES_INICIALES_CONFIGURACION), {c for c, *_ in PARAMETROS_DE_CONFIGURACION}
        )
