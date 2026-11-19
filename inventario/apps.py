# Configuración de la app `inventario` (nivel 4 de D-37).
from django.apps import AppConfig


class InventarioConfig(AppConfig):
    """Registra la app `inventario`; todavía no tiene modelos ni punto de extensión (D-37, A4)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventario'
