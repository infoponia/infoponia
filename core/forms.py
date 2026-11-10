# Formularios de core: inicio de sesión (USR-INI-SES) y elegir contraseña nueva (USR-CMB-CTR).

from django import forms
from django.contrib.auth.forms import AuthenticationForm

# SEG-06: el mismo mensaje sea cual sea la causa (email inexistente, contraseña incorrecta,
# cuenta inactiva). Texto del prototipo (vLogin).
MENSAJE_FALLA_GENERICO = (
    "No pudimos iniciar sesión. Revisá el email y la contraseña, y volvé a intentarlo."
)


class FormularioInicioSesion(AuthenticationForm):
    """Formulario de inicio de sesión con email y contraseña (USR-INI-SES, SEG-01 y SEG-06).

    No hay función en ``core/servicios.py`` para este caso de uso: iniciar sesión no modifica
    datos y sus reglas las aplican el sistema de autenticación de Django, el backend
    ``core.backends.BackendEmail`` (regla 1, regla 2 y SEG-01) y este formulario (SEG-06).
    La identificación no se audita (regla 6, SEG-14).
    """

    error_messages = {
        "invalid_login": MENSAJE_FALLA_GENERICO,
        "inactive": MENSAJE_FALLA_GENERICO,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].error_messages["required"] = "Ingresá tu email."
        self.fields["password"].error_messages["required"] = "Ingresá tu contraseña."


class FormularioContrasenaNueva(forms.Form):
    """Contraseña nueva y su repetición, para el cambio forzado por contraseña temporal (vForced).

    Solo controla que las dos coincidan. La política de contraseñas (SEG-03) y las demás reglas de
    USR-CMB-CTR las aplica el servicio ``core.servicios.cambiar_contrasena``, y la vista pasa sus
    errores a este formulario.
    """

    contrasena_nueva = forms.CharField(
        label="Contraseña nueva",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Ingresá la contraseña nueva."},
    )
    contrasena_repetida = forms.CharField(
        label="Repetí la contraseña nueva",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Repetí la contraseña nueva."},
    )

    def clean(self):
        """Las dos contraseñas escritas tienen que ser iguales."""
        datos = super().clean()
        nueva = datos.get("contrasena_nueva")
        repetida = datos.get("contrasena_repetida")
        if nueva and repetida and nueva != repetida:
            self.add_error("contrasena_repetida", "Las contraseñas no coinciden.")
        return datos
