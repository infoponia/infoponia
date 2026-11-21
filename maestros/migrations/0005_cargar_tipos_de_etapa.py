# Migración de datos de MAE-03: carga el catálogo fijo de cinco tipos de etapa (MD-52, docs/modelo/maestros.md,
# «Tipo de etapa»). Los valores van escritos acá y no se importan del modelo: una migración no depende de código que
# cambia (docs/patrones/datos_de_migracion.md, «Singletons y catálogos fijos»). ``cargar`` es idempotente por ``codigo``
# y no llama a código de la app; ``descargar`` borra los cinco tipos solo si nada los referencia.

from django.db import migrations

# Los seis perfiles familiares (valores de ``Variedad.perfil_familia``).
TODOS = ["hoja_verde", "pastura", "frutos_grandes", "frutos_pequenos", "flores", "hierbas"]

# (codigo, nombre_etapa, puesto_global, perfiles_permitidos)
TIPOS_DE_ETAPA = [
    ("germinacion", "Germinación", 1, TODOS),
    ("crecimiento", "Crecimiento", 2, TODOS),
    ("floracion", "Floración", 3, ["frutos_grandes", "frutos_pequenos", "flores"]),
    ("fructificacion", "Fructificación", 4, ["frutos_grandes", "frutos_pequenos"]),
    ("maduracion", "Maduración", 5, TODOS),
]


def cargar(apps, schema_editor):
    """Crea o actualiza los cinco tipos de etapa por su ``codigo``: correrla dos veces no duplica."""
    TipoEtapa = apps.get_model("maestros", "TipoEtapa")
    for codigo, nombre, puesto, perfiles in TIPOS_DE_ETAPA:
        TipoEtapa.objects.update_or_create(
            codigo=codigo,
            defaults={"nombre_etapa": nombre, "puesto_global": puesto, "perfiles_permitidos": list(perfiles)},
        )


def descargar(apps, schema_editor):
    """Inversa: borra los cinco tipos solo si ningún sector ni etapa los usa (no destruye datos del usuario)."""
    TipoEtapa = apps.get_model("maestros", "TipoEtapa")
    SectorProduccion = apps.get_model("maestros", "SectorProduccion")
    EtapaProductiva = apps.get_model("maestros", "EtapaProductiva")
    if SectorProduccion.objects.exists() or EtapaProductiva.objects.exists():
        return
    TipoEtapa.objects.filter(codigo__in=[t[0] for t in TIPOS_DE_ETAPA]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("maestros", "0004_sectores_y_cultivos"),
    ]

    operations = [
        migrations.RunPython(cargar, descargar),
    ]
