# Datos de INV-01: las CUATRO categorías del sistema (regla 1 de 8.23 del modelo y CMP-ALT-TIN regla 4; el prototipo muestra
# tres, manda el caso de uso). Siguen docs/patrones/datos_de_migracion.md («Las categorías del sistema de `inventario`»):
# - Los valores van escritos acá: una migración no depende de código que cambia (no importa `inventario.categorias`).
# - `cargar(apps, schema_editor)` es idempotente por `codigo` (`update_or_create`): correrla dos veces no duplica y NO pisa
#   el nombre de una fila que ya existe.
# - `descargar` borra las cuatro filas solo si ningún insumo las usa.
# - Las demás categorías que se ven en el prototipo (limpieza, nutrientes) son datos de ejemplo: no se cargan.

from django.db import migrations

# (código, nombre): código fijo y único; el nombre es solo el valor inicial.
CATEGORIAS_DEL_SISTEMA = (
    ("semillas", "Semillas"),
    ("envases", "Envases"),
    ("repuestos_de_hardware", "Repuestos de hardware"),
    ("infraestructura", "Infraestructura"),
)


def cargar(apps, schema_editor):
    """Crea las cuatro categorías del sistema (activas, `consumo_directo = no_admite`) si faltan. No cambia el nombre de las
    que ya existen."""
    TipoInsumo = apps.get_model("inventario", "TipoInsumo")
    for codigo, nombre in CATEGORIAS_DEL_SISTEMA:
        TipoInsumo.objects.update_or_create(
            codigo=codigo,
            defaults={"es_del_sistema": True, "consumo_directo": "no_admite", "estado_tipo_insumo": "activo"},
            create_defaults={
                "nombre_tipo_insumo": nombre,
                "es_del_sistema": True,
                "consumo_directo": "no_admite",
                "estado_tipo_insumo": "activo",
            },
        )


def descargar(apps, schema_editor):
    """Borra las cuatro filas solo si ningún insumo las usa (no borra datos de la organización)."""
    TipoInsumo = apps.get_model("inventario", "TipoInsumo")
    Insumo = apps.get_model("inventario", "Insumo")
    codigos = [codigo for codigo, _ in CATEGORIAS_DEL_SISTEMA]
    if Insumo.objects.filter(tipo_insumo__codigo__in=codigos).exists():
        return
    TipoInsumo.objects.filter(codigo__in=codigos, es_del_sistema=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0001_esquema_inicial"),
    ]

    operations = [
        migrations.RunPython(cargar, descargar),
    ]
