# Configuración de la app `inventario` (nivel 4 de D-37): registra sus tipos de alerta en `maestros` (regla A4 de D-37).
from django.apps import AppConfig


class InventarioConfig(AppConfig):
    """Registra la app `inventario`. En ``ready()`` registra sus cuatro tipos de alerta (INV-01, docs/patrones/stock.md,
    sección 4) en ``maestros.alertas``; los usa INV-02, pero la baja del insumo (CMP-BAJ-INS) ya resuelve «bajo el mínimo».
    También registra la entrada «Inventario» del menú del Agrónomo (``core.menu.registrar_entrada``, regla A4 de D-37), después de «Producción»."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventario'

    def ready(self):
        """Registra los cuatro tipos de alerta de `inventario` (idempotente: ``ready()`` puede correr más de una vez)."""
        from core.menu import registrar_entrada
        from core.models import Usuario
        from inventario.alertas import registrar_tipos_de_stock

        registrar_tipos_de_stock()
        registrar_entrada(("Inventario", "inventario:catalogo", "box"), (Usuario.Rol.AGRONOMO,), despues_de="Producción")
