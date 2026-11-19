# Admin de Alerta, de solo lectura (MAE-02a, D-41). Existe solo en desarrollo: lo apagan las rutas, no el registro
# (SEG-18 y D-30: con DEBUG apagado no se registra ninguna ruta de /admin/). Las alertas las crean y resuelven los
# servicios de maestros (maestros/servicios/alertas.py), que aplican sus reglas; el admin solo sirve para mirarlas.

from django.contrib import admin

from .models import Alerta


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    """Lista y ficha de alertas sin alta, edición ni baja (regla 7 de 8.18: los estados cambian solo por los servicios)."""

    list_display = (
        "invernadero",
        "tipo_alerta",
        "descripcion_alerta",
        "estado_alerta",
        "estado_lectura_alerta",
        "fecha_hora_alerta",
        "fecha_resolucion",
        "para_gerente",
        "agronomo",
    )
    list_filter = ("estado_alerta", "invernadero")

    def has_add_permission(self, request):
        """Las alertas no se crean a mano."""
        return False

    def has_change_permission(self, request, obj=None):
        """Las alertas no se modifican a mano."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Las alertas no se borran a mano."""
        return False
