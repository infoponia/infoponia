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


# MAE-03: los tipos de etapa son un catálogo fijo (solo lectura); los sectores y los cultivos se crean y modifican con
# sus servicios (que aplican las reglas y auditan), así que el admin solo los muestra. La variedad sí se puede crear a
# mano mientras INV-03 no tenga su pantalla (la verificación a mano de MAE-03 lo usa).
from .models import Cultivo, SectorProduccion, TipoEtapa, Variedad  # noqa: E402


@admin.register(TipoEtapa)
class TipoEtapaAdmin(admin.ModelAdmin):
    """Los cinco tipos de etapa con sus perfiles permitidos, sin alta, edición ni baja (MD-52)."""

    list_display = ("puesto_global", "nombre_etapa", "codigo", "perfiles_permitidos")

    def has_add_permission(self, request):
        """El catálogo lo carga la migración."""
        return False

    def has_change_permission(self, request, obj=None):
        """Sus nombres no se cambian: de ellos dependen reglas del modelo."""
        return False

    def has_delete_permission(self, request, obj=None):
        """No se borran."""
        return False


@admin.register(SectorProduccion)
class SectorProduccionAdmin(admin.ModelAdmin):
    """Lista de sectores, solo lectura: los gestiona el Agrónomo con sus pantallas."""

    list_display = ("nombre_sector", "invernadero", "tipo_etapa", "cant_agujeros_total", "estado_sector")
    list_filter = ("estado_sector", "tipo_etapa")

    def has_add_permission(self, request):
        """Los sectores se crean con PROD-ALT-SCT."""
        return False

    def has_change_permission(self, request, obj=None):
        """Se modifican con PROD-MOD-SCT."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Las bajas son lógicas."""
        return False


@admin.register(Cultivo)
class CultivoAdmin(admin.ModelAdmin):
    """Lista de cultivos, solo lectura: los gestiona el Agrónomo con sus pantallas."""

    list_display = ("nombre_cultivo", "estado_cultivo")

    def has_add_permission(self, request):
        """Los cultivos se crean con PROD-ALT-CLT."""
        return False

    def has_change_permission(self, request, obj=None):
        """Se modifican con PROD-MOD-CLT."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Las bajas son lógicas."""
        return False


@admin.register(Variedad)
class VariedadAdmin(admin.ModelAdmin):
    """Variedades con las columnas mínimas de MAE-03: se cargan a mano hasta que INV-03 traiga su pantalla."""

    list_display = ("nombre_variedad", "cultivo", "perfil_familia", "estado_variedad")
    list_filter = ("estado_variedad", "cultivo")


# MAE-04: los dos singletons se modifican con sus servicios (que validan y auditan), así que el admin solo los muestra.
from .models import ConfiguracionOperativa, PerfilOrganizacion  # noqa: E402


class _SoloLectura(admin.ModelAdmin):
    """Un registro único: sin alta, edición ni baja desde el admin."""

    def has_add_permission(self, request):
        """La fila la crea la migración (MD-89)."""
        return False

    def has_change_permission(self, request, obj=None):
        """Se modifica desde la pantalla «Configuración», con auditoría."""
        return False

    def has_delete_permission(self, request, obj=None):
        """No se borra."""
        return False


admin.site.register(ConfiguracionOperativa, _SoloLectura)
admin.site.register(PerfilOrganizacion, _SoloLectura)
