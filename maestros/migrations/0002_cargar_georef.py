# Migración de datos: carga la geografía de Georef (provincias, departamentos y localidades) desde los CSV de
# maestros/datos/georef_2026-11-18/ (MD-88, regla 3 de PROD-ALT-INV, D-39 decisión 2).
# No llama a código de la app: corre sobre los modelos históricos y lee los CSV por ruta relativa a este archivo,
# para que dé siempre lo mismo aunque la app cambie después (mismo criterio que la 0008 de core, D-36).

import csv
from pathlib import Path

from django.db import migrations

CARPETA = Path(__file__).resolve().parent.parent / "datos" / "georef_2026-11-18"


def _filas(nombre):
    """Filas de un CSV de la carpeta de datos como diccionarios."""
    with open(CARPETA / nombre, newline="", encoding="utf-8") as archivo:
        return list(csv.DictReader(archivo))


def cargar(apps, schema_editor):
    """Carga las tres tablas, de la provincia a la localidad, respetando las claves foráneas."""
    Provincia = apps.get_model("maestros", "Provincia")
    Departamento = apps.get_model("maestros", "Departamento")
    Localidad = apps.get_model("maestros", "Localidad")
    Provincia.objects.bulk_create(
        [Provincia(id_georef=f["id_georef"], nombre_provincia=f["nombre"]) for f in _filas("provincias.csv")]
    )
    provincias = {p.id_georef: p.pk for p in Provincia.objects.all()}
    Departamento.objects.bulk_create(
        [
            Departamento(
                id_georef=f["id_georef"],
                nombre_departamento=f["nombre"],
                provincia_id=provincias[f["provincia_id_georef"]],
            )
            for f in _filas("departamentos.csv")
        ]
    )
    departamentos = {d.id_georef: d.pk for d in Departamento.objects.all()}
    Localidad.objects.bulk_create(
        [
            Localidad(
                id_georef=f["id_georef"],
                nombre_localidad=f["nombre"],
                departamento_id=departamentos[f["departamento_id_georef"]],
            )
            for f in _filas("localidades.csv")
        ],
        batch_size=1000,
    )


def descargar(apps, schema_editor):
    """Vuelta: borra las tres tablas, de la localidad a la provincia."""
    for modelo in ("Localidad", "Departamento", "Provincia"):
        apps.get_model("maestros", modelo).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("maestros", "0001_initial")]

    operations = [migrations.RunPython(cargar, descargar)]
