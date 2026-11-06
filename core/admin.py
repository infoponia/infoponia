# Admin de Usuario y de los seis roles. El Administrador técnico (D-10) da de alta,
# modifica y da de baja al Gerente desde acá; los demás roles quedan registrados para
# cuando existan sus propias pantallas.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Agronomo, Capataz, Gerente, Tecnico, Transportista, Usuario, Vendedor


class UsuarioCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("email", "first_name", "last_name")


class UsuarioChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = "__all__"


class UsuarioAdmin(UserAdmin):
    """Admin de Usuario en general: sin alta (se da de alta desde el admin de cada rol
    concreto, o con `createsuperuser` para un Administrador). `rol` es de solo lectura
    porque no se modifica después de creado (D-11)."""

    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    model = Usuario

    list_display = ("email", "first_name", "last_name", "rol", "is_active", "is_staff")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("rol",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "telefono", "rol")}),
        (
            "Permisos",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )

    def has_add_permission(self, request):
        return False


class RolAdmin(UserAdmin):
    """Admin común a los seis roles: alta, modificación y baja (desactivar) con
    contraseña hasheada. `rol` no aparece como campo porque lo fija `save()` del modelo."""

    form = UsuarioChangeForm
    add_form = UsuarioCreationForm

    list_display = ("email", "first_name", "last_name", "is_active", "is_staff")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "telefono")}),
        (
            "Permisos",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "first_name", "last_name", "password1", "password2")}),
    )


admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Gerente, RolAdmin)
admin.site.register(Agronomo, RolAdmin)
admin.site.register(Capataz, RolAdmin)
admin.site.register(Vendedor, RolAdmin)
admin.site.register(Transportista, RolAdmin)
admin.site.register(Tecnico, RolAdmin)
