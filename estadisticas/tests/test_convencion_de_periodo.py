# La convención de días del período de COM-08c (`comercial.servicios.estadisticas.filtros_de_estadisticas`) es la de EST-01 y EST-02 (`estadisticas.periodos.validar`, D-93 punto 2): las tres pantallas aceptan
# y rechazan lo mismo. Vive acá y no en `comercial/tests` porque `comercial` (nivel 6) no puede importar de `estadisticas` (nivel 8; regla A1 de D-37, `test_arquitectura`). Fuente: D-93 punto 2, D-94 punto 15.

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from comercial.servicios.estadisticas import filtros_de_estadisticas
from core.tests.fabricas import crear_gerente
from estadisticas import periodos


class ConvencionDePeriodoTests(TestCase):
    def test_d93_punto_2_comercial_acepta_y_rechaza_los_mismos_rangos_que_periodos_validar(self):
        """Los extremos de un rango (un solo día, 365, 366 y 367 días, inicio posterior al fin, fin futuro) los acepta o rechaza igual `periodos.validar` que `filtros_de_estadisticas`."""
        gerente = crear_gerente()
        dia = date(2026, 11, 26)
        casos = [(dia - timedelta(days=n), dia) for n in (0, 1, 364, 365, 366, 400)] + [(dia, dia - timedelta(days=1)), (dia, dia + timedelta(days=1)), (dia - timedelta(days=1), dia + timedelta(days=1))]
        for desde, hasta in casos:
            try:
                periodos.validar(desde, hasta, dia)
                esperado = True
            except ValidationError:
                esperado = False
            try:
                filtros_de_estadisticas(gerente, {"periodo": "rango", "desde": desde.isoformat(), "hasta": hasta.isoformat()}, dia)
                obtenido = True
            except ValidationError:
                obtenido = False
            self.assertEqual(obtenido, esperado, (desde, hasta))
