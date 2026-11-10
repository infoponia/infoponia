# Migración del email (SEG-01, D-19, D-25): pasa los emails existentes a minúsculas y agrega la
# unicidad sin distinguir mayúsculas. Antes de tocar nada detecta los emails repetidos y, si los hay,
# falla con un mensaje claro: no borra ni cambia ninguna cuenta. Como PostgreSQL ejecuta la migración
# en una sola transacción, si falla no queda aplicado ningún cambio.

import django.db.models.functions.text
from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower, Trim


def emails_a_minusculas(apps, schema_editor):
    """Falla si hay emails repetidos sin distinguir mayúsculas; si no, los pasa a minúsculas."""
    Usuario = apps.get_model("core", "Usuario")

    repetidos = (
        Usuario.objects.annotate(email_normalizado=Lower(Trim("email")))
        .values("email_normalizado")
        .annotate(cantidad=Count("id"))
        .filter(cantidad__gt=1)
        .order_by("email_normalizado")
    )
    if repetidos:
        detalle = []
        for repetido in repetidos:
            ids = list(
                Usuario.objects.annotate(email_normalizado=Lower(Trim("email")))
                .filter(email_normalizado=repetido["email_normalizado"])
                .order_by("id")
                .values_list("id", flat=True)
            )
            detalle.append(
                f"  - {repetido['email_normalizado']} (cuentas con id {', '.join(map(str, ids))})"
            )
        raise RuntimeError(
            "No se puede aplicar la migración del email (SEG-01): hay cuentas cuyo email es el mismo "
            "si no se distinguen mayúsculas ni espacios en los extremos:\n"
            + "\n".join(detalle)
            + "\nNo se modificó ningún dato. Resolvelo a mano (por ejemplo, corregí o dá de baja una "
            "de las cuentas de cada grupo) y volvé a ejecutar migrate."
        )

    Usuario.objects.update(email=Lower(Trim("email")))


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('core', '0003_contrasena_temporal_y_auditoria'),
    ]

    operations = [
        # Volver atrás no puede recuperar las mayúsculas originales, y los emails en minúsculas
        # siguen siendo válidos: por eso la reversa no hace nada.
        migrations.RunPython(emails_a_minusculas, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='usuario',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('email'), name='email_unico_sin_mayusculas', violation_error_code='email_repetido', violation_error_message='Ya existe una cuenta con ese email.'),
        ),
    ]
