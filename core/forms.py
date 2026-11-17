# Formularios de core: inicio de sesión (USR-INI-SES), elegir contraseña nueva y cambio voluntario desde
# Mi perfil (USR-CMB-CTR) y los de
# cuentas del Gerente y del Administrador (USR-CNS-USR, USR-ALT-USR, USR-MOD-USR).

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from django.conf import settings

from core.acceso import nombre_visible_del_rol
from core.models import RegistroAuditoria
from core.servicios import (
    ACCESO_INVITACION,
    ACTUO_INFOPONIA,
    acceso_del_pedido,
    clases_de_rol_que_da_de_alta,
    cuentas_filtrables_para_auditoria,
    roles_que_gestiona,
)

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


class FormularioPedirRecuperacion(forms.Form):
    """Email de la cuenta cuya contraseña se olvidó (USR-RCP-CTR, vRecover del prototipo).

    Solo controla que haya un email con forma de email. Si hay una cuenta con él lo decide el servicio
    ``pedir_recuperacion``, y la respuesta es la misma exista o no (regla 2, SEG-12).
    """

    email = forms.EmailField(
        label="Email",
        error_messages={
            "required": "Ingresá tu email.",
            "invalid": "Ingresá un email válido, por ejemplo nombre@dominio.com.",
        },
    )


class FormularioCambioContrasena(FormularioContrasenaNueva):
    """Cambio voluntario de contraseña desde Mi perfil (USR-CMB-CTR por sí mismo, USR-GST-PRF regla 3).

    Agrega la contraseña actual (regla 1 de USR-CMB-CTR). Es obligatoria acá, con el mismo mensaje que el
    servicio, para que un envío vacío muestre todos los errores juntos (como pwChangeErr del prototipo),
    igual que la contraseña nueva de ``FormularioContrasenaNueva``. Si es correcta lo decide el servicio
    ``cambiar_contrasena``, que vuelve a pedirla; la vista pasa sus errores a este formulario.
    """

    contrasena_actual = forms.CharField(
        label="Contraseña actual",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        error_messages={"required": "Ingresá tu contraseña actual."},
    )

    field_order = ["contrasena_actual", "contrasena_nueva", "contrasena_repetida"]


class FormularioVincularCuenta(forms.Form):
    """Email y contraseña de la otra cuenta, para vincularla (USR-VNC-CTA regla 1, modalHtml 'link').

    Ningún campo es obligatorio acá a propósito: las reglas (los dos datos presentes, la contraseña correcta,
    que la cuenta sea vinculable) las aplica ``core.servicios.vincular_cuenta``, que es la única fuente, y la
    vista pasa sus errores a este formulario. La contraseña nunca vuelve escrita en el campo.
    """

    email = forms.CharField(
        label="Email de la otra cuenta",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "inputmode": "email",
                "autocomplete": "off",
                "autocapitalize": "off",
                "data-foco-inicial": "",
            }
        ),
    )
    contrasena = forms.CharField(
        label="Contraseña de la otra cuenta",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}),
    )


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


class FormularioFiltroAuditoria(forms.Form):
    """Filtros de la lista de auditoría (AUD-CNS-REG regla 2): rango de fechas, cuenta que actuó, acción y cuenta
    afectada, más ``cuenta`` (oculto), que es el filtro de la ficha (regla 7): «actuó o fue afectada».

    Solo valida la forma de lo que llega (fechas, números, que «desde» no sea posterior a «hasta»). Qué registros ve
    cada uno y si puede filtrar por una cuenta lo decide ``core.servicios.consultar_auditoria`` (403 o 404, D-28):
    por eso las cuentas no se validan contra la lista. Los desplegables llevan ``data-desplegable`` (D-24).
    """

    MENSAJE_CUENTA = "Elegí una cuenta de la lista."

    desde = forms.DateField(
        required=False,
        label="Desde",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "field-input"}),
        error_messages={"invalid": "Ingresá una fecha «desde» válida."},
    )
    hasta = forms.DateField(
        required=False,
        label="Hasta",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "field-input"}),
        error_messages={"invalid": "Ingresá una fecha «hasta» válida."},
    )
    actuo = forms.CharField(
        required=False,
        widget=forms.Select(
            attrs={"class": "field-input", "data-desplegable": "", "aria-label": "Filtrar por la cuenta que actuó"}
        ),
    )
    accion = forms.CharField(
        required=False,
        widget=forms.Select(
            attrs={"class": "field-input", "data-desplegable": "", "aria-label": "Filtrar por acción"}
        ),
    )
    afectada = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.Select(
            attrs={"class": "field-input", "data-desplegable": "", "aria-label": "Filtrar por la cuenta afectada"}
        ),
        error_messages={"invalid": MENSAJE_CUENTA, "min_value": MENSAJE_CUENTA},
    )
    cuenta = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput,
        error_messages={"invalid": MENSAJE_CUENTA, "min_value": MENSAJE_CUENTA},
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        cuentas = [
            (str(cuenta.pk), f"{cuenta.get_full_name() or cuenta.email} ({nombre_visible_del_rol(cuenta)})")
            for cuenta in cuentas_filtrables_para_auditoria(actor)
        ]
        self.fields["actuo"].widget.choices = [
            ("", "Cualquier cuenta que actuó"),
            (ACTUO_INFOPONIA, "InfoPonia (el Sistema)"),
        ] + cuentas
        self.fields["afectada"].widget.choices = [("", "Cualquier cuenta afectada")] + cuentas
        self.fields["accion"].widget.choices = [("", "Todas las acciones")] + list(RegistroAuditoria.Accion.choices)

    def clean_actuo(self):
        """La cuenta que actuó es el id de una cuenta o «infoponia»; cualquier otra cosa no es una cuenta."""
        valor = (self.cleaned_data["actuo"] or "").strip()
        if valor and valor != ACTUO_INFOPONIA and not (valor.isascii() and valor.isdigit() and int(valor) > 0):
            raise forms.ValidationError(self.MENSAJE_CUENTA)
        return valor

    def clean(self):
        """Un rango de fechas al revés no es válido (lo informa y la lista sale vacía)."""
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            self.add_error("desde", "La fecha «desde» es posterior a la fecha «hasta».")
        return datos


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
    """Alta de una cuenta (USR-ALT-USR): los datos personales, el rol y la forma de primer acceso.

    Regla 1: las opciones de rol son las que ``actor`` da de alta. El Administrador da de alta solo al
    Gerente (D-16): el campo se muestra con «Gerente», deshabilitado, como el prototipo (vAlta). Un campo
    deshabilitado no toma lo que llega en el pedido, sino su valor inicial, así que un rol enviado a mano
    se ignora. La regla la vuelve a controlar ``alta_usuario``.

    ``acceso`` (regla 4, D-35): cómo obtiene la persona su primer acceso. Con el correo configurado la pantalla
    ofrece la invitación (marcada por defecto) y la contraseña temporal; sin él, solo la temporal y el campo no
    viaja. El valor se pasa tal cual al servicio, que rechaza una invitación sin el correo configurado (regla 10).
    """

    rol = forms.CharField(
        label="Rol",
        required=False,
        widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}),
    )

    acceso = forms.CharField(required=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.correo_configurado = settings.CORREO_CONFIGURADO
        self.fields["acceso"].initial = ACCESO_INVITACION if self.correo_configurado else ""
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

    def clean_acceso(self):
        """Sin el correo configurado la pantalla no ofrece elegir: un pedido sin el campo es la temporal."""
        return acceso_del_pedido(self.cleaned_data.get("acceso"))


class FormularioModificarUsuario(FormularioDatosPersonales):
    """Modificación de una cuenta (USR-MOD-USR). No tiene campo de rol: el rol no se modifica
    (regla 2, D-11), así que un ``rol`` enviado a mano en el pedido se ignora."""
