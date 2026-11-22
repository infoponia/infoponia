# INV-03, paso 1 (D-49): completa `Variedad` con los cuatro rangos ambientales, la postcosecha y el peso en gramos, y agrega la
# restricción única del nombre por cultivo y las de dominio. Solo esquema: ninguna migración de datos.
#
# Las columnas son obligatorias y no hay un valor razonable para inventarles a variedades que ya existan, así que, si la tabla
# trae filas (cargadas a mano desde /admin/ durante la verificación de MAE-03), un RunPython previo las rechaza con un mensaje
# claro; con la tabla vacía, las columnas se agregan con un valor por única vez (``preserve_default=False``).

from django.db import migrations, models
import django.db.models.functions.text


def rechazar_variedades_cargadas_a_mano(apps, schema_editor):
    """Falla con un mensaje claro si hay variedades de prueba: no se les inventan rangos (INV-03, paso 1)."""
    cantidad = apps.get_model("maestros", "Variedad").objects.count()
    if cantidad:
        raise RuntimeError(
            f"Hay {cantidad} variedades de prueba cargadas a mano: borralas desde /admin/ antes de migrar"
        )


def nada(apps, schema_editor):
    """La vuelta no hace nada: el chequeo solo protege la ida."""


def _rango(nombre, etiqueta):
    return migrations.AddField(
        model_name="variedad",
        name=nombre,
        field=models.DecimalField(decimal_places=2, default=0, max_digits=7, verbose_name=etiqueta),
        preserve_default=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("maestros", "0008_transportista_invernadero"),
    ]

    operations = [
        migrations.RunPython(rechazar_variedades_cargadas_a_mano, nada),
        _rango("temp_ambiente_min", "temperatura mínima (°C)"),
        _rango("temp_ambiente_max", "temperatura máxima (°C)"),
        _rango("humedad_min", "humedad mínima (%)"),
        _rango("humedad_max", "humedad máxima (%)"),
        _rango("intensidad_luz_min", "intensidad lumínica mínima (µmol)"),
        _rango("intensidad_luz_max", "intensidad lumínica máxima (µmol)"),
        _rango("fotoperiodo_min", "fotoperíodo mínimo (h/día)"),
        _rango("fotoperiodo_max", "fotoperíodo máximo (h/día)"),
        migrations.AddField(
            model_name="variedad",
            name="duracion_post_cosecha",
            field=models.PositiveIntegerField(default=1, verbose_name="duración postcosecha (días)"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="variedad",
            name="peso_promedio_planta",
            field=models.PositiveIntegerField(default=1, verbose_name="peso promedio por planta (g)"),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("nombre_variedad"), models.F("cultivo"), name="variedad_nombre_unico_por_cultivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("temp_ambiente_min__lte", models.F("temp_ambiente_max"))), name="variedad_temp_min_max"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("humedad_min__lte", models.F("humedad_max"))), name="variedad_humedad_min_max"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("intensidad_luz_min__lte", models.F("intensidad_luz_max"))), name="variedad_luz_min_max"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("fotoperiodo_min__lte", models.F("fotoperiodo_max"))), name="variedad_fotoperiodo_min_max"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("humedad_max__lte", 100), ("humedad_min__gte", 0)), name="variedad_humedad_0_a_100"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("fotoperiodo_max__lte", 24), ("fotoperiodo_min__gte", 0)), name="variedad_fotoperiodo_0_a_24"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("duracion_post_cosecha__gte", 1), ("duracion_post_cosecha__lte", 60)), name="variedad_postcosecha_1_a_60"),
        ),
        migrations.AddConstraint(
            model_name="variedad",
            constraint=models.CheckConstraint(condition=models.Q(("peso_promedio_planta__gt", 0)), name="variedad_peso_mayor_que_cero"),
        ),
    ]
