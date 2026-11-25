# Pruebas de la sección 12 de ``docs/demo/datos_de_la_demo.md`` (DAT-02, paso 1): los tres lotes existentes cargados con PRD-05
# (``registrar_lote_existente``). Cargan UNA vez (``setUpTestData``) con el candado sustituido (se llama a ``carga.cargar`` directo).
# Los secretos de las pruebas se inventan en cada corrida.

import secrets
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from contabilidad.tests.fabricas import PlanDeCuentasMixin
from demo import carga
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Lote, OcupacionSector, Siembra
from produccion.servicios import lotes as servicios_lotes

BASE = "ejemplo"


class CargaDeLotesExistentesTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-02 paso 1: LN-1, LN-2 y LS-1, cada uno en su etapa, su sector y su fecha de entrada, con su fecha máxima de cosecha."""

    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.contexto = carga.Contexto(hoy=cls.hoy, base=BASE, contrasena=secrets.token_urlsafe(12))
        cls.lineas = carga.cargar(cls.contexto)

    def _lote(self, clave):
        return Lote.objects.get(pk=self.contexto.lotes[clave].pk)

    def test_dat_02_la_seccion_12_se_carga_sin_saltearse(self):
        """DAT-02 paso 0: PRD-05 está en el repo, así que la sección 12 se carga."""
        self.assertTrue(any(l.startswith("Cargado: 12. Lotes existentes") for l in self.lineas), self.lineas)

    def test_dat_02_tres_lotes_cada_uno_en_su_etapa_con_sus_plantas(self):
        """Sección 12: LN-1 en Maduración (300), LN-2 en Crecimiento (200) y LS-1 en Maduración (150)."""
        esperado = {
            "LN-1": ("Norte", "Criolla", "maduracion", 300),
            "LN-2": ("Norte", "Morada", "crecimiento", 200),
            "LS-1": ("Sur", "Genovesa", "maduracion", 150),
        }
        self.assertEqual(Lote.objects.count(), 3)
        for clave, (invernadero, variedad, etapa, plantas) in esperado.items():
            lote = self._lote(clave)
            self.assertEqual(
                (lote.invernadero.nombre_invernadero, lote.siembra.variedad.nombre_variedad, lote.etapa.tipo_etapa.codigo, lote.cantidad_actual),
                (invernadero, variedad, etapa, plantas),
                clave,
            )
            self.assertEqual(lote.cantidad_inicial, plantas, clave)

    def test_dat_02_cada_lote_ocupa_su_sector_con_todas_sus_plantas(self):
        """Sección 12: Maduración N1 (300), Crecimiento N1 (200) y Maduración S1 (150)."""
        esperado = {"LN-1": ("Maduración N1", 300), "LN-2": ("Crecimiento N1", 200), "LS-1": ("Maduración S1", 150)}
        for clave, (sector, plantas) in esperado.items():
            ocupaciones = list(OcupacionSector.objects.filter(lote=self._lote(clave)).select_related("sector"))
            self.assertEqual([o.sector.nombre_sector for o in ocupaciones], [sector], clave)

    def test_dat_02_las_fechas_de_siembra_son_las_de_la_tabla_y_la_orden_lleva_hoy(self):
        """Sección 12 y D-103: la fecha de siembra indicada va en la siembra; la orden se crea, programa y resuelve en hoy."""
        esperado = {"LN-1": 32, "LN-2": 29, "LS-1": 39}
        for clave, dias in esperado.items():
            siembra = Siembra.objects.get(lote=self._lote(clave))
            self.assertEqual(siembra.fecha_siembra, self.hoy - timedelta(days=dias), clave)
            self.assertEqual(siembra.tipo_siembra, Siembra.TipoSiembra.CARGA_INICIAL, clave)
            self.assertEqual(siembra.fecha_creacion_orden, self.hoy, clave)
            self.assertEqual(siembra.fecha_programada_orden, self.hoy, clave)

    def test_dat_02_la_entrada_a_maduracion_de_ln1_y_ls1_es_la_de_la_tabla(self):
        """Sección 12: LN-1 entró a Maduración en HOY−2 y LS-1 en HOY−4."""
        self.assertEqual(servicios_lotes.fecha_de_entrada_a_maduracion(self._lote("LN-1")), self.hoy - timedelta(days=2))
        self.assertEqual(servicios_lotes.fecha_de_entrada_a_maduracion(self._lote("LS-1")), self.hoy - timedelta(days=4))

    def test_dat_02_la_entrada_de_ln2_a_crecimiento_es_hoy_menos_19(self):
        """Sección 12: LN-2 está en Crecimiento desde HOY−19 (duración 20: le falta un día)."""
        lote = self._lote("LN-2")
        self.assertEqual(servicios_lotes.fecha_de_entrada_a_la_etapa(lote), self.hoy - timedelta(days=19))
        self.assertIsNone(servicios_lotes.fecha_de_entrada_a_maduracion(lote))

    def test_dat_02_la_fecha_maxima_de_cosecha_de_ln1_es_hoy_mas_12_y_la_de_ls1_hoy_mas_6(self):
        """Sección 12: LN-1 (entrada HOY−2 + 14) y LS-1 (entrada HOY−4 + 10)."""
        self.assertEqual(servicios_lotes.fecha_maxima_de_cosecha(self._lote("LN-1")), self.hoy + timedelta(days=12))
        self.assertEqual(servicios_lotes.fecha_maxima_de_cosecha(self._lote("LS-1")), self.hoy + timedelta(days=6))

    def test_dat_02_el_costo_de_cada_lote_es_el_de_la_tabla(self):
        """Sección 12: costo estimado 45000,00, 24000,00 y 18000,00."""
        self.assertEqual(self._lote("LN-1").costo_acumulado, Decimal("45000.00"))
        self.assertEqual(self._lote("LN-2").costo_acumulado, Decimal("24000.00"))
        self.assertEqual(self._lote("LS-1").costo_acumulado, Decimal("18000.00"))
