# Pruebas de arquitectura de `estadisticas` (EST-01): es una app de nivel 8, sin modelos ni migraciones, y ninguna app de nivel menor
# importa de ella. Fuente: D-93 punto 1 (enmienda de D-37) y la regla A1 de D-37.

import re
from pathlib import Path

from django.apps import apps
from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]
# Las apps de niveles 1 a 7 (D-37). `demo` es de nivel 9 (solo el comando `cargar_demo`) y puede importar de cualquiera.
APPS_DE_MENOR_NIVEL = ("core", "contabilidad", "maestros", "inventario", "produccion", "comercial", "compras", "iot")
# `from estadisticas…` / `import estadisticas…` al principio de una línea, o `import_module("estadisticas…")`.
IMPORTA_DE_ESTADISTICAS = re.compile(
    r"^\s*(?:from\s+estadisticas(?:\.|\s)|import\s+estadisticas\b)|import_module\(\s*[\"']estadisticas\b", re.MULTILINE
)


class ArquitecturaDeEstadisticasTests(SimpleTestCase):
    """La app `estadisticas` lee a las demás y ninguna la lee a ella."""

    def test_d93_punto_1_ninguna_app_de_menor_nivel_importa_de_estadisticas(self):
        """D-93 punto 1 y regla A1 de D-37: una app solo importa de apps de nivel menor; `estadisticas` es la de nivel 8."""
        infractores = []
        for app in APPS_DE_MENOR_NIVEL:
            for archivo in (RAIZ / app).rglob("*.py"):
                if IMPORTA_DE_ESTADISTICAS.search(archivo.read_text(encoding="utf-8")):
                    infractores.append(str(archivo.relative_to(RAIZ)))
        self.assertEqual(infractores, [])

    def test_d93_punto_1_la_app_no_tiene_modelos(self):
        """D-93 punto 1: sin modelos; todo se calcula al consultar (D-14: no se guardan datos derivados)."""
        self.assertEqual(list(apps.get_app_config("estadisticas").get_models()), [])

    def test_d93_punto_1_la_app_no_tiene_migraciones(self):
        """D-93 punto 1: sin migraciones."""
        self.assertFalse((RAIZ / "estadisticas" / "migrations").exists())

    def test_d93_punto_1_esta_instalada_despues_de_iot(self):
        """D-93 punto 1: `'estadisticas'` va en `INSTALLED_APPS` después de `'iot'` (nivel 8)."""
        from django.conf import settings

        instaladas = list(settings.INSTALLED_APPS)
        self.assertGreater(instaladas.index("estadisticas"), instaladas.index("iot"))
