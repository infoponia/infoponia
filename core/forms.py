# Formularios de core: inicio de sesión (USR-INI-SES), elegir contraseña nueva (USR-CMB-CTR) y los de
# usuarios del Gerente (USR-CNS-USR, USR-ALT-USR).

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from core.models import Usuario
from core.servicios import CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE

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


# ---- Usuarios del Gerente (USR-CNS-USR y USR-ALT-USR) ----

def _roles_del_gerente():
    """Los cinco roles que el Gerente consulta y da de alta (regla 1), como pares (valor, nombre)."""
    return [
        (rol.value, rol.label)
        for rol in Usuario.Rol
        if rol in CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE
    ]


class BuscadorInput(forms.TextInput):
    """Campo de texto de tipo «search» (Django no trae un widget propio para ese tipo)."""

    input_type = "search"


class FormularioFiltroUsuarios(forms.Form):
    """Filtros de la lista de usuarios (USR-CNS-USR regla 2): rol, estado y búsqueda.

    Todo es opcional y no valida nada: el filtrado y la búsqueda los hace
    ``core.servicios.consultar_usuarios``. Los dos desplegables llevan ``data-desplegable``: con
    JavaScript los reemplaza el desplegable propio (D-24); sin JavaScript queda el ``<select>`` nativo.
    """

    rol = forms.CharField(
        required=False,
        widget=forms.Select(
            choices=[("", "Todos los roles")] + _roles_del_gerente(),
            attrs={"class": "field-input", "data-desplegable": "", "aria-label": "Filtrar por rol"},
        ),
    )
    estado = forms.CharField(
        required=False,
        widget=forms.Select(
            choices=[("", "Todos los estados"), ("activo", "Activo"), ("inactivo", "Inactivo")],
            attrs={"class": "field-input", "data-desplegable": "", "aria-label": "Filtrar por estado"},
        ),
    )
    q = forms.CharField(
        required=False,
        widget=BuscadorInput(
            attrs={
                "class": "field-input",
                "placeholder": "Buscar por nombre, apellido o email",
                "aria-label": "Buscar",
                "autocomplete": "off",
                "style": "min-width:260px",
            }
        ),
    )


class FormularioAltaUsuario(forms.Form):
    """Datos del alta de una cuenta (USR-ALT-USR). Solo recoge la entrada y la devuelve limpia.

    Ningún campo es obligatorio acá a propósito: las reglas (regla 7 de obligatorios, regla 9 del
    teléfono, email único, rol permitido) las aplica ``core.servicios.alta_usuario``, que es la
    única fuente, y la vista pasa sus errores a este formulario. El formulario se muestra con
    ``novalidate``: el teléfono se valida al confirmar, no mientras se escribe.
    """

    nombre = forms.CharField(
        label="Nombre",
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "autocomplete": "off"}),
    )
    apellido = forms.CharField(
        label="Apellido",
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "autocomplete": "off"}),
    )
    email = forms.CharField(
        label="Email",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "inputmode": "email",
                "autocomplete": "off",
                "autocapitalize": "off",
            }
        ),
    )
    telefono = forms.CharField(
        label="Teléfono (opcional)",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "field-input", "inputmode": "tel", "autocomplete": "off"}
        ),
    )
    rol = forms.CharField(
        label="Rol",
        required=False,
        widget=forms.Select(
            choices=[("", "Seleccionar…")] + _roles_del_gerente(),
            attrs={"class": "field-input", "data-desplegable": ""},
        ),
    )
