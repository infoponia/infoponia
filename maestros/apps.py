# Configuración de la app `maestros` (nivel 3 de D-37).
from django.apps import AppConfig


class MaestrosConfig(AppConfig):
    """Registra la app `maestros`; todavía no tiene modelos ni punto de extensión (D-37, A4)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'maestros'
