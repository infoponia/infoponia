# Configuración de la app `contabilidad` (nivel 2 de D-37).
from django.apps import AppConfig


class ContabilidadConfig(AppConfig):
    """Registra la app `contabilidad`; tiene solo `OrigenDocumento` (D-52) y ningún punto de extensión (D-37, A4)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contabilidad'
