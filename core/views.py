# Vistas de core: inicio de sesión, cierre de sesión, elegir contraseña (cambio forzado por contraseña
# temporal), inicio de cada cuenta y usuarios del Gerente. Solo orquestan: validan la entrada, llaman al
# servicio y renderizan.

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.forms import (
    FormularioAltaUsuario,
    FormularioContrasenaNueva,
    FormularioFiltroUsuarios,
    FormularioInicioSesion,
)
from core.middleware import permitido_con_contrasena_temporal
from core.models import Usuario
from core.servicios import alta_usuario, cambiar_contrasena, consultar_usuarios, obtener_cuenta


class IniciarSesionView(LoginView):
    """Pantalla de inicio de sesión (USR-INI-SES, SEG-01). Exenta del login obligatorio por Django.

    Una cuenta que ya tiene sesión es llevada directamente a su inicio.
    """

    template_name = "core/iniciar_sesion.html"
    authentication_form = FormularioInicioSesion
    redirect_authenticated_user = True


# SEG-08: Django vacía la sesión en el servidor, no solo la cookie, y solo acepta POST.
# Se exime del login obligatorio para que una sesión ya vencida pueda cerrarse sin rebotar, y
# del bloqueo por contraseña temporal para que quien la tiene pueda salir (regla 4 de USR-INI-SES).
cerrar_sesion = permitido_con_contrasena_temporal(login_not_required(LogoutView.as_view()))


@permitido_con_contrasena_temporal
def elegir_contrasena(request):
    """Pantalla «Elegí tu contraseña» (vForced): USR-CMB-CTR cuando extiende a USR-INI-SES.

    Solo para cuentas con contraseña temporal (las demás van al inicio). Cambia siempre la
    contraseña de ``request.user`` (regla 3): la cuenta no viaja en la URL ni en el formulario.
    """
    if not request.user.tiene_contrasena_temporal:
        return redirect("core:inicio")

    if request.method == "POST":
        form = FormularioContrasenaNueva(request.POST)
        if form.is_valid():
            try:
                cambiar_contrasena(request.user, form.cleaned_data["contrasena_nueva"])
            except ValidationError as error:
                for campo, errores in error.error_dict.items():
                    for e in errores:
                        # Un error de un campo que este formulario no tiene (por ejemplo, la
                        # contraseña actual, si la temporal se reemplazó en otra pestaña) va general.
                        form.add_error(campo if campo in form.fields else None, e)
            else:
                # SEG-10: el cambio invalida las demás sesiones de la cuenta; esta se mantiene.
                update_session_auth_hash(request, request.user)
                return redirect("core:inicio")
    else:
        form = FormularioContrasenaNueva()
    return render(request, "core/elegir_contrasena.html", {"form": form})


def inicio(request):
    """Inicio de la cuenta: indica con qué rol opera (USR-INI-SES postcondición a, vHome).

    El contenido del panel de cada rol llega con los módulos de negocio.
    """
    return render(request, "core/inicio.html")


# ---- Usuarios del Gerente (USR-CNS-USR y USR-ALT-USR, tarea 04a) ----
# Pendiente, tarea 05: el Administrador usa estas mismas pantallas con su propio alcance (D-16); se
# suma ``ADMINISTRADOR`` a ``rol_requerido`` cuando ``en_alcance_de`` tenga su rama.


@rol_requerido(Usuario.Rol.GERENTE)
@vary_on_headers("HX-Request")
def usuarios(request):
    """Lista de usuarios con filtros y búsqueda (USR-CNS-USR, vUsuarios).

    Un pedido de HTMX (los filtros) recibe solo la tabla; los demás, la pantalla entera. Un pedido
    de restauración del historial de HTMX necesita la pantalla entera.
    """
    form = FormularioFiltroUsuarios(request.GET)
    form.is_valid()  # todos los campos son opcionales: siempre hay cleaned_data
    cuentas = consultar_usuarios(
        request.user,
        rol=form.cleaned_data["rol"],
        estado=form.cleaned_data["estado"],
        busqueda=form.cleaned_data["q"],
    )
    parcial = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )
    plantilla = "core/usuarios/_tabla_usuarios.html" if parcial else "core/usuarios/lista.html"
    return render(request, plantilla, {"form": form, "cuentas": cuentas})


@rol_requerido(Usuario.Rol.GERENTE)
def usuario_ficha(request, cuenta_id):
    """Ficha de una cuenta (USR-CNS-USR, vUsuario). Fuera del alcance da 403; un id inexistente, 404."""
    cuenta = obtener_cuenta(request.user, cuenta_id)
    return render(request, "core/usuarios/ficha.html", {"cuenta": cuenta})


@rol_requerido(Usuario.Rol.GERENTE)
@never_cache
def usuario_nuevo(request):
    """Alta de una cuenta (USR-ALT-USR, vAlta y vAltaOk).

    La contraseña temporal solo viaja en la respuesta del POST: no se guarda en la sesión ni en la
    base, y ``never_cache`` evita que el navegador la conserve para el botón «Atrás». Límite
    conocido (D-28): recargar «Cuenta creada» reenvía el formulario y da el error de email repetido.
    """
    cuenta_inactiva = None
    if request.method == "POST":
        form = FormularioAltaUsuario(request.POST)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        try:
            cuenta, contrasena_temporal = alta_usuario(request.user, **form.cleaned_data)
        except ValidationError as error:
            for campo, errores in error.error_dict.items():
                for e in errores:
                    if e.code == "email_de_cuenta_inactiva":
                        # Regla 8: en vez de un error del campo, se ofrece reactivar esa cuenta.
                        cuenta_inactiva = e.params["cuenta"]
                        continue
                    form.add_error(campo if campo in form.fields else None, e)
        else:
            return render(
                request,
                "core/usuarios/alta_ok.html",
                {"cuenta": cuenta, "contrasena_temporal": contrasena_temporal},
            )
    else:
        form = FormularioAltaUsuario()
    return render(
        request, "core/usuarios/alta.html", {"form": form, "cuenta_inactiva": cuenta_inactiva}
    )
