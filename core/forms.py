# Formularios de core. Por ahora, solo el de inicio de sesión (USR-INI-SES).

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
