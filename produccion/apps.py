# Configuración de la app `produccion` (nivel 5 de D-37).
from django.apps import AppConfig


class ProduccionConfig(AppConfig):
    """Registra la app `produccion`; todavía no tiene modelos ni punto de extensión (D-37, A4)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'produccion'
