# Pruebas de `pasar_a_fuera_de_servicio(sector)` (PRD-04, paso 2; D-51 punto 7; docs/api/extensiones_de_maestros.md, «Lote 5»): cambia el
# estado del sector a «fuera de servicio» y nada más: no audita, no valida el rol, no bloquea. Con un sector que no está activo, ValueError.

from django.test import TestCase

from core.models import RegistroAuditoria
from maestros.models import SectorProduccion
from maestros.servicios import sectores
from maestros.tests.fabricas import ConDatosDeMaestros, crear_agronomo_con_invernadero, crear_sector


class PasarAFueraDeServicioTests(ConDatosDeMaestros, TestCase):
    """La función de `maestros` que usa PROD-PNR-FDS para cambiar el estado."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.sector = crear_sector(self.invernadero, "G-1", "germinacion")

    def test_regla_cambia_el_estado_a_fuera_de_servicio(self):
        """D-51 punto 7: un sector activo queda «fuera de servicio» (en la base y en el objeto recibido)."""
        sectores.pasar_a_fuera_de_servicio(self.sector)
        self.assertEqual(self.sector.estado_sector, SectorProduccion.Estado.FUERA_DE_SERVICIO)
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "fuera_de_servicio")

    def test_regla_no_cambia_nada_mas(self):
        """D-51 punto 7: ni el nombre, ni los agujeros, ni el tipo de etapa; y no audita (lo hace quien la llama)."""
        antes = SectorProduccion.objects.values().get(pk=self.sector.pk)
        sectores.pasar_a_fuera_de_servicio(self.sector)
        despues = SectorProduccion.objects.values().get(pk=self.sector.pk)
        antes.pop("estado_sector")
        despues.pop("estado_sector")
        self.assertEqual(antes, despues)
        self.assertFalse(RegistroAuditoria.objects.filter(accion__in=["modificacion_sector", "fuera_de_servicio_sector"]).exists())

    def test_regla_un_sector_que_no_esta_activo_lanza_value_error_y_no_cambia(self):
        """Docs de la API: con un sector fuera de servicio o inactivo, `ValueError`, sin cambiar el estado."""
        for estado in ("fuera_de_servicio", "inactivo"):
            with self.subTest(estado=estado):
                otro = crear_sector(self.invernadero, f"X-{estado}", "crecimiento", estado=estado)
                with self.assertRaises(ValueError):
                    sectores.pasar_a_fuera_de_servicio(otro)
                otro.refresh_from_db()
                self.assertEqual(otro.estado_sector, estado)
