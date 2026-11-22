# Datos de IOT-01: el catálogo de capacidades (IOT-ALT-TAC, regla 7; docs/modelo/iot.md, «Catálogo de capacidades», MD-103): tres
# capacidades y seis comandos. Sigue docs/patrones/datos_de_migracion.md:
# - Los valores van escritos acá: una migración no depende de código que cambia (no importa `iot.catalogo`).
# - `cargar(apps, schema_editor)` es idempotente por `codigo` (`update_or_create`): correrla dos veces no duplica ni pisa el
#   nombre de una fila que ya existe.
# - `descargar` borra las filas solo si ninguna acción las usa (no borra datos de la organización).

from django.db import DEFAULT_DB_ALIAS, migrations

# (código, nombre) de las capacidades, y (código, capacidad, lleva valor) de los comandos.
CAPACIDADES = (
    ("encendido", "Encendido"),
    ("nivel", "Nivel"),
    ("posicion", "Posición"),
)
COMANDOS = (
    ("ENCENDER", "encendido", False),
    ("APAGAR", "encendido", False),
    ("FIJAR_NIVEL", "nivel", True),
    ("ABRIR", "posicion", False),
    ("CERRAR", "posicion", False),
    ("FIJAR_POSICION", "posicion", True),
)


def cargar(apps, schema_editor):
    """Crea las tres capacidades y los seis comandos si faltan. No cambia el nombre de las capacidades que ya existen."""
    Capacidad = apps.get_model("iot", "Capacidad")
    ComandoCatalogo = apps.get_model("iot", "ComandoCatalogo")
    for codigo, nombre in CAPACIDADES:
        Capacidad.objects.update_or_create(codigo=codigo, create_defaults={"nombre": nombre})
    for codigo, capacidad, lleva_valor in COMANDOS:
        ComandoCatalogo.objects.update_or_create(
            codigo=codigo,
            defaults={"capacidad": Capacidad.objects.get(codigo=capacidad), "lleva_valor": lleva_valor},
        )


def descargar(apps, schema_editor):
    """Borra los comandos y las capacidades solo si ninguna acción ni equipo anunciado usa un comando."""
    Capacidad = apps.get_model("iot", "Capacidad")
    ComandoCatalogo = apps.get_model("iot", "ComandoCatalogo")
    Accion = apps.get_model("iot", "Accion")
    EquipoAnunciado = apps.get_model("iot", "EquipoAnunciado")
    if Accion.objects.exists() or EquipoAnunciado.comandos.through.objects.exists():
        return
    # ``_raw_delete`` es API PRIVADA de Django. Se usa porque ``.delete()`` dispara el recolector de cascadas, que con modelos históricos
    # mezcla versiones del modelo (ValueError al bajar todas las migraciones, por la tabla intermedia de ``EquipoAnunciado.comandos``).
    # Es seguro: arriba se verificó que nada usa estas filas y, si se escapara alguna, las FK ``PROTECT`` harían fallar el DELETE.
    # Orden: primero los comandos (hijos) y después las capacidades (padres).
    alias = schema_editor.connection.alias if schema_editor else DEFAULT_DB_ALIAS
    ComandoCatalogo.objects.filter(codigo__in=[codigo for codigo, *_ in COMANDOS])._raw_delete(alias)
    Capacidad.objects.filter(codigo__in=[codigo for codigo, _ in CAPACIDADES])._raw_delete(alias)


class Migration(migrations.Migration):

    dependencies = [
        ("iot", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar, descargar),
    ]
