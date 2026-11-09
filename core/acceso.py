# Control de acceso según el rol (SEG-13). Lo usan las pantallas de todos los módulos.

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

# D-10: el Administrador es un superusuario sin ``rol``; para el control de acceso se lo trata
# como un rol más, que ninguna pantalla de negocio incluye.
ADMINISTRADOR = "administrador"


def rol_de(usuario):
    """Rol con el que opera la cuenta: el ``rol`` del dominio o ``ADMINISTRADOR`` (D-10)."""
    if usuario.is_superuser:
        return ADMINISTRADOR
    return usuario.rol


def nombre_visible_del_rol(usuario):
    """Nombre del rol para mostrar en pantalla y en mensajes («Capataz», «Administrador»)."""
    if usuario.is_superuser:
        return "Administrador"
    return usuario.get_rol_display()


def rol_requerido(*roles):
    """Decorador de vistas: solo deja pasar a las cuentas cuyo rol está en ``roles`` (SEG-13).

    Patrón Decorator: un único punto para verificar el rol en lugar de repetir la verificación
    en cada vista. Si el rol no corresponde, lanza ``PermissionDenied`` (error 403) con un
    mensaje que nombra el rol; ``403.html`` lo muestra.

    Pendiente (segunda mitad de SEG-13): el ámbito por invernadero. Se agrega acá cuando exista
    el modelo ``Invernadero``, para que todas las pantallas lo apliquen igual.
    """

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if rol_de(request.user) not in roles:
                raise PermissionDenied(
                    f"Tu cuenta de {nombre_visible_del_rol(request.user)} "
                    "no tiene acceso a esta pantalla."
                )
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
