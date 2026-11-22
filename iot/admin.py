# Admin de solo lectura de los modelos de `iot` (IOT-01). Existe solo en desarrollo: lo apagan las rutas, no el registro
# (SEG-18 y D-30). Los datos del IoT los crean y cambian los servicios, que aplican las reglas: el admin solo sirve para mirarlos.

from django.contrib import admin

from iot import models


class SoloLecturaAdmin(admin.ModelAdmin):
    """Lista y ficha sin alta, edición ni baja."""

    def has_add_permission(self, request):
        """Nada se crea a mano."""
        return False

    def has_change_permission(self, request, obj=None):
        """Nada se modifica a mano."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Nada se borra a mano."""
        return False


for _modelo in (
    models.Capacidad,
    models.ComandoCatalogo,
    models.TipoActuador,
    models.Accion,
    models.SistemaIoT,
    models.NodoCentral,
    models.Sensor,
    models.Actuador,
    models.EquipoAnunciado,
    models.Telemetria,
    models.ResumenHorario,
    models.FotoperiodoDiario,
    models.ReglaActuacion,
    models.Comando,
    models.AlertaIot,
):
    admin.site.register(_modelo, SoloLecturaAdmin)
