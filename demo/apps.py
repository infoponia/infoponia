# Configuración de la app ``demo`` (nivel 9 de D-37, decisión de la demo de la defensa; hoy ``docs/decisiones/D-01-demo.md``).
# Solo tiene el comando ``cargar_demo``: no tiene modelos ni migraciones. Se instala únicamente con ``INFOPONIA_DEMO=1`` o durante
# las pruebas (``config/settings.py``), así que en producción el comando ni siquiera existe.

from django.apps import AppConfig


class DemoConfig(AppConfig):
    """App de la demo. Puede importar de todas las apps; ninguna importa de ella (D-37, nivel 9)."""

    name = "demo"
    default_auto_field = "django.db.models.BigAutoField"
