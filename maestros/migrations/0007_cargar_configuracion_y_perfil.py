# Migración de datos de MAE-04: crea la fila única de ``ConfiguracionOperativa`` y la de ``PerfilOrganizacion`` (MD-89,
# docs/patrones/datos_de_migracion.md, «Singletons y catálogos fijos»). Los valores van escritos acá y no se importan del
# modelo: una migración no depende de código que cambia (una prueba compara estos valores con los ``default`` del modelo).
# ``cargar`` es idempotente (``update_or_create`` por ``singleton=1``) y no pisa lo que el Gerente ya cambió: solo crea. El
# nombre del perfil sale de ``settings.NOMBRE_ORGANIZACION`` y solo se escribe al crear la fila (D-48).

from django.conf import settings
from django.db import migrations

# Valores iniciales de la ronda 22 (regla 2 de ADM-MOD-CFG; MD-89 y MD-93).
VALORES_INICIALES_CONFIGURACION = {
    "porc_merma_maxima": 15,
    "dias_horizonte_cosecha": 30,
    "dias_aviso_vencimiento": 15,
    "dias_pre_reserva_suministro": 14,
    "dias_anticipacion_cosecha_compra_venta": 1,
    "dias_anticipacion_cosecha_suministro": 3,
    "dias_vigencia_enlace_confirmacion": 3,
    "dias_vigencia_enlace_faltante": 2,
    "dias_limite_cotizacion": 3,
    "dias_validez_cotizacion": 7,
    "porc_tolerancia_cobertura_pedido": 0,
    "cant_maxima_entregas_diarias": 10,
    "cant_max_ciudades_distintas_diarias": 3,
}


def cargar(apps, schema_editor):
    """Crea cada fila única si falta; si ya existe, no cambia nada (``defaults`` solo rige al crear)."""
    ConfiguracionOperativa = apps.get_model("maestros", "ConfiguracionOperativa")
    PerfilOrganizacion = apps.get_model("maestros", "PerfilOrganizacion")
    ConfiguracionOperativa.objects.get_or_create(singleton=1, defaults=VALORES_INICIALES_CONFIGURACION)
    PerfilOrganizacion.objects.get_or_create(singleton=1, defaults={"nombre_organizacion": settings.NOMBRE_ORGANIZACION})


def descargar(apps, schema_editor):
    """Inversa: no hace nada. Las filas son datos de la organización y la tabla se elimina con la migración de esquema."""


class Migration(migrations.Migration):

    dependencies = [
        ("maestros", "0006_configuracion_y_perfil"),
    ]

    operations = [
        migrations.RunPython(cargar, descargar),
    ]
