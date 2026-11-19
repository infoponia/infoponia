# Configuración de la app `maestros` (nivel 3 de D-37): registra su entrada del menú de `core` (regla A4 de D-37).
from django.apps import AppConfig


class MaestrosConfig(AppConfig):
    """Registra la app `maestros`. En ``ready()`` agrega «Producción» (la lista de invernaderos, MAE-01) al menú del
    Gerente y del Agrónomo, cada uno con su alcance (regla 1 de PROD-CNS-INV), después de «Panel de control»: ``core`` no
    puede importar `maestros`, así que la entrada se registra en su punto de extensión (``core.menu.registrar_entrada``).
    `maestros` tiene sus propios puntos de extensión en ``maestros/extensiones.py``."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'maestros'

    def ready(self):
        """Registra la entrada «Producción» en el menú de `core`."""
        from core.menu import registrar_entrada
        from core.models import Usuario

        registrar_entrada(
            ("Producción", "maestros:invernaderos", "leaf"),
            (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO),
            despues_de="Panel de control",
        )
