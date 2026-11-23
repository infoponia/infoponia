# Admin de `produccion`, de solo lectura (COM-02, como el de las demás apps): las cosechas y las partidas se crean y cambian solo con los
# servicios, que aplican sus reglas. Existe solo en desarrollo: lo apagan las rutas, no el registro (SEG-18 y D-30).

from django.contrib import admin

from .models import Cosecha, StockCosechado


class SoloLectura(admin.ModelAdmin):
    """Lista y ficha sin alta, edición ni baja."""

    def has_add_permission(self, request):
        """No se crean a mano."""
        return False

    def has_change_permission(self, request, obj=None):
        """No se modifican a mano."""
        return False

    def has_delete_permission(self, request, obj=None):
        """No se borran a mano."""
        return False


@admin.register(Cosecha)
class CosechaAdmin(SoloLectura):
    """Cosechas: número, invernadero, variedad, estado y fecha programada."""

    list_display = ("numero", "invernadero", "variedad", "estado_orden", "fecha_programada_orden")
    list_filter = ("estado_orden",)


@admin.register(StockCosechado)
class StockCosechadoAdmin(SoloLectura):
    """Partidas de cámara: lote, disponible, fecha límite y estado."""

    list_display = ("id", "lote", "cantidad_disponible_cosechado", "fecha_limite", "estado_stock_cosechado")
    list_filter = ("estado_stock_cosechado",)
