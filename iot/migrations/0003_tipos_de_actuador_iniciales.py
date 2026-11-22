# Datos de IOT-01: los seis tipos de actuador iniciales con sus acciones (IOT-ALT-TAC, regla 5; docs/modelo/iot.md, «TipoActuador»).
# Todos activos y con 60 segundos entre comandos. Se aplica DESPUÉS del catálogo (0002) y no se audita (los datos de arranque no
# son una acción de nadie). Sigue docs/patrones/datos_de_migracion.md:
# - Idempotente: si ya existe un tipo con ese nombre (sin distinguir mayúsculas), no hace nada con él (ni con sus acciones).
# - `descargar` borra solo los tipos iniciales que ningún actuador usa y cuyas acciones ningún comando ni regla usa.

from django.db import DEFAULT_DB_ALIAS, migrations
from django.db.models.functions import Lower

# (nombre del tipo, [(acción, comando, mínimo, máximo, unidad)]); mínimo, máximo y unidad son None si el comando no lleva valor.
TIPOS_INICIALES = (
    ("Ventilador", [("Encender", "ENCENDER", None, None, None), ("Apagar", "APAGAR", None, None, None), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")]),
    ("Bomba", [("Encender", "ENCENDER", None, None, None), ("Apagar", "APAGAR", None, None, None)]),
    ("Luminaria", [("Encender", "ENCENDER", None, None, None), ("Apagar", "APAGAR", None, None, None)]),
    ("Calefactor", [("Encender", "ENCENDER", None, None, None), ("Apagar", "APAGAR", None, None, None)]),
    ("Ventana", [("Abrir", "ABRIR", None, None, None), ("Cerrar", "CERRAR", None, None, None), ("Fijar posición", "FIJAR_POSICION", 0, 100, "%")]),
    ("Media sombra", [("Abrir", "ABRIR", None, None, None), ("Cerrar", "CERRAR", None, None, None), ("Fijar posición", "FIJAR_POSICION", 0, 100, "%")]),
)
TIEMPO_MINIMO_INICIAL = 60


def cargar(apps, schema_editor):
    """Crea los seis tipos con sus acciones si no existe ya un tipo con ese nombre."""
    TipoActuador = apps.get_model("iot", "TipoActuador")
    Accion = apps.get_model("iot", "Accion")
    ComandoCatalogo = apps.get_model("iot", "ComandoCatalogo")
    for nombre, acciones in TIPOS_INICIALES:
        if TipoActuador.objects.annotate(_minuscula=Lower("nombre_actuador")).filter(_minuscula=nombre.lower()).exists():
            continue
        tipo = TipoActuador.objects.create(
            nombre_actuador=nombre, tiempo_minimo_entre_comandos=TIEMPO_MINIMO_INICIAL, estado="activo"
        )
        for nombre_accion, comando, minimo, maximo, unidad in acciones:
            Accion.objects.create(
                tipo_actuador=tipo,
                nombre_accion=nombre_accion,
                comando=ComandoCatalogo.objects.get(codigo=comando),
                valor_minimo=minimo,
                valor_maximo=maximo,
                unidad_valor=unidad,
                estado="activa",
            )


def descargar(apps, schema_editor):
    """Borra los tipos iniciales (y sus acciones) solo si ningún actuador, comando ni regla los usa."""
    TipoActuador = apps.get_model("iot", "TipoActuador")
    Accion = apps.get_model("iot", "Accion")
    nombres = [nombre.lower() for nombre, _ in TIPOS_INICIALES]
    alias = schema_editor.connection.alias if schema_editor else DEFAULT_DB_ALIAS
    for tipo in TipoActuador.objects.annotate(_minuscula=Lower("nombre_actuador")).filter(_minuscula__in=nombres):
        acciones = Accion.objects.filter(tipo_actuador=tipo)
        if tipo.actuadores.exists() or any(a.comandos.exists() or a.reglas.exists() or a.actuadores_incompatibles.exists() for a in acciones):
            continue
        # ``_raw_delete`` es API PRIVADA de Django. Se usa porque ``.delete()`` dispara el recolector de cascadas, que con modelos históricos
        # mezcla versiones del modelo (ValueError al bajar todas las migraciones). Es seguro: arriba se verificó que nada usa estas filas y,
        # si se escapara alguna, las FK ``PROTECT`` harían fallar el DELETE. Orden: primero las acciones (hijas) y después el tipo (padre).
        acciones._raw_delete(alias)
        TipoActuador.objects.filter(pk=tipo.pk)._raw_delete(alias)


class Migration(migrations.Migration):

    dependencies = [
        ("iot", "0002_catalogo_de_capacidades"),
    ]

    operations = [
        migrations.RunPython(cargar, descargar),
    ]
