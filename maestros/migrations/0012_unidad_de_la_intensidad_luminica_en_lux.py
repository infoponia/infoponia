# La unidad de la intensidad lumínica de la variedad es lux (la que mide y compara el IoT), no µmol: solo cambia el texto (verbose_name); no hay cambio de datos, de tipo ni de SQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maestros', '0011_dias_aviso_vencimiento_camara'),
    ]

    operations = [
        migrations.AlterField(
            model_name='variedad',
            name='intensidad_luz_max',
            field=models.DecimalField(decimal_places=2, max_digits=7, verbose_name='intensidad lumínica máxima (lux)'),
        ),
        migrations.AlterField(
            model_name='variedad',
            name='intensidad_luz_min',
            field=models.DecimalField(decimal_places=2, max_digits=7, verbose_name='intensidad lumínica mínima (lux)'),
        ),
    ]
