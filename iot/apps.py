# Configuración de la app `iot` (nivel 7 de D-37): registra sus tipos de alerta en `maestros` y su entrada del menú de `core`
# (regla A4 de D-37).
from django.apps import AppConfig


class IotConfig(AppConfig):
    """Registra la app `iot` (nivel 7 de D-37: importa hasta `produccion`; ninguna app de nivel menor la importa). En
    ``ready()`` registra los 11 tipos de alerta del IoT (IOT-01, docs/modelo/iot.md) y la entrada «IoT» del menú del Gerente y
    del Agrónomo, justo después de «Producción» (``core.menu.registrar_entrada``)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'iot'
    verbose_name = 'IoT'

    def ready(self):
        """Registra los tipos de alerta y la entrada del menú. Los dos son idempotentes (``ready()`` puede correr más de una vez)."""
        from core.menu import registrar_entrada
        from core.models import Usuario
        from iot.alertas import registrar_tipos_de_iot

        registrar_tipos_de_iot()
        # IOT-01, paso 4: «IoT» lo ven el Gerente y el Agrónomo (los demás roles reciben 403 en todo el módulo).
        registrar_entrada(
            ("IoT", "iot:inicio", "activity"),
            (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO),
            despues_de="Producción",
        )
