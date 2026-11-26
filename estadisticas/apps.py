# Configuración de la app `estadisticas` (nivel 8 de D-37, enmienda de D-93 punto 1).
from django.apps import AppConfig


class EstadisticasConfig(AppConfig):
    """Registra la app `estadisticas`: sin modelos. En ``ready()`` registra la entrada de menú «Estadísticas» del Agrónomo y del Gerente (H28;
    ``core.menu.registrar_entrada``, regla A4 de D-37), después de «Compras». El Capataz, el Técnico, el Vendedor y el Contador no la tienen."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'estadisticas'

    def ready(self):
        """Registra la entrada del menú (idempotente: ``ready()`` puede correr más de una vez)."""
        from core.menu import registrar_entrada
        from core.models import Usuario

        registrar_entrada(("Estadísticas", "estadisticas:produccion", "chart"), (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO), despues_de="Compras")
