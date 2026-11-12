# Formularios de core: inicio de sesión (USR-INI-SES), elegir contraseña nueva (USR-CMB-CTR) y los de
# cuentas del Gerente y del Administrador (USR-CNS-USR, USR-ALT-USR, USR-MOD-USR).

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from core.servicios import clases_de_rol_que_da_de_alta, roles_que_gestiona

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


# ---- Cuentas del Gerente y del Administrador (USR-CNS-USR y USR-ALT-USR) ----


class BuscadorInput(forms.TextInput):
    """Campo de texto de tipo «search» (Django no trae un widget propio para ese tipo)."""

    input_type = "search"


class FormularioFiltroUsuarios(forms.Form):
    """Filtros de la lista de usuarios (USR-CNS-USR regla 2): rol, estado y búsqueda.

    Todo es opcional y no valida nada: el filtrado y la búsqueda los hace
    ``core.servicios.consultar_usuarios``. Los dos desplegables llevan ``data-desplegable``: con
    JavaScript los reemplaza el desplegable propio (D-24); sin JavaScript queda el ``<select>`` nativo.
    Las opciones de rol son las de las cuentas que ``actor`` consulta (regla 1): los cinco roles para el
    Gerente; «Gerente» y «Administrador» para el Administrador (D-16).
    """

    rol = forms.CharField(
        required=False,
        widget=forms.Select(
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

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rol"].widget.choices = [("", "Todos los roles")] + roles_que_gestiona(actor)


class FormularioDatosPersonales(forms.Form):
    """Datos personales de una cuenta, comunes al alta y a la modificación. Solo recoge la entrada.

    Ningún campo es obligatorio acá a propósito: las reglas (regla 7 de obligatorios, regla 9 del
    teléfono, email único, rol permitido) las aplican ``core.servicios.alta_usuario`` y
    ``modificar_usuario``, que son la única fuente, y la vista pasa sus errores a este formulario.
    Los formularios se muestran con ``novalidate``: el teléfono se valida al confirmar, no mientras
    se escribe.
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


class FormularioAltaUsuario(FormularioDatosPersonales):
    """Alta de una cuenta (USR-ALT-USR): los datos personales y el rol.

    Regla 1: las opciones de rol son las que ``actor`` da de alta. El Administrador da de alta solo al
    Gerente (D-16): el campo se muestra con «Gerente», deshabilitado, como el prototipo (vAlta). Un campo
    deshabilitado no toma lo que llega en el pedido, sino su valor inicial, así que un rol enviado a mano
    se ignora. La regla la vuelve a controlar ``alta_usuario``.
    """

    rol = forms.CharField(
        label="Rol",
        required=False,
        widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}),
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        roles = [(rol.value, rol.label) for rol in clases_de_rol_que_da_de_alta(actor)]
        campo = self.fields["rol"]
        if len(roles) == 1:
            campo.widget.choices = roles
            campo.initial = roles[0][0]
            campo.disabled = True
            # El desplegable propio (desplegable.js) no contempla «disabled»: queda el <select> nativo.
            campo.widget.attrs.pop("data-desplegable", None)
        else:
            campo.widget.choices = [("", "Seleccionar…")] + roles


class FormularioModificarUsuario(FormularioDatosPersonales):
    """Modificación de una cuenta (USR-MOD-USR). No tiene campo de rol: el rol no se modifica
    (regla 2, D-11), así que un ``rol`` enviado a mano en el pedido se ignora."""
