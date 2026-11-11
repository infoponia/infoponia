# Datos del marco con sesión (cabecera, menú lateral, menú de cuenta) disponibles en toda plantilla.

from django.conf import settings
from django.urls import reverse

from core.acceso import ADMINISTRADOR, nombre_visible_del_rol, rol_de
from core.menu import MENU_POR_ROL, ROLES_DE_CAMPO, SIGLAS


def marco(request):
    """Agrega al contexto el rol visible, la sigla, el menú y el modo campo de la cuenta."""
    # El nombre de la organización se muestra también en las pantallas sin sesión.
    contexto = {"nombre_organizacion": settings.NOMBRE_ORGANIZACION}
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return contexto

    rol = rol_de(usuario)
    modo_campo = rol in ROLES_DE_CAMPO
    menu = [
        {
            "texto": texto,
            "url": reverse(nombre_url),
            "icono": icono,
            # Una entrada también está activa en sus pantallas internas (por ejemplo, la ficha
            # de un usuario). El inicio es «/», que sería prefijo de todo: solo coincide exacto.
            "activo": request.path == reverse(nombre_url)
            or (reverse(nombre_url) != "/" and request.path.startswith(reverse(nombre_url))),
        }
        for texto, nombre_url, icono in MENU_POR_ROL.get(rol, [])
    ]
    return contexto | {
        "rol_visible": nombre_visible_del_rol(usuario),
        "es_administrador": rol == ADMINISTRADOR,
        "sigla": SIGLAS.get(rol, ""),
        "menu": menu,
        "modo_campo": modo_campo,
        "mostrar_menu_lateral": bool(menu) and not modo_campo,
    }
