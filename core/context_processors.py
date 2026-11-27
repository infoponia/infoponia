# Datos del marco con sesión (cabecera, menú lateral, menú de cuenta con las cuentas vinculadas) disponibles en
# toda plantilla, y el estado de la campana (punto y notificaciones sin leer).

from django.urls import reverse

from core import extensiones, identidad
from core.acceso import ADMINISTRADOR, nombre_visible_del_rol, rol_de
from core.menu import ROLES_DE_CAMPO, SIGLAS, menu_de
from core.models import Usuario
from core.notificaciones import estado_de_la_campana
from core.servicios import cuentas_vinculadas


def marco(request):
    """Agrega al contexto el rol visible, la sigla, el menú y el modo campo de la cuenta."""
    # El nombre y el color de la organización se muestran también en las pantallas sin sesión (D-48). La identidad se consulta
    # una sola vez por pedido y se guarda en la solicitud: sin caché de proceso, un cambio rige desde el pedido siguiente.
    if not hasattr(request, "_identidad_de_la_organizacion"):
        request._identidad_de_la_organizacion = extensiones.identidad_registrada()
    registrada = request._identidad_de_la_organizacion
    contexto = {
        "nombre_organizacion": identidad.nombre_de_la_organizacion(registrada),
        "color_principal": identidad.color_principal(registrada),
        "logo_url": identidad.logo_de_la_organizacion(registrada),
    }
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
        for texto, nombre_url, icono in menu_de(rol)
    ]
    return contexto | {
        "rol_visible": nombre_visible_del_rol(usuario),
        "es_administrador": rol == ADMINISTRADOR,
        "sigla": SIGLAS.get(rol, ""),
        "menu": menu,
        "modo_campo": modo_campo,
        "mostrar_menu_lateral": bool(menu) and not modo_campo,
        # SEG-09: las otras cuentas del grupo, para «Cambiar de cuenta» del menú de cuenta. Sin grupo (y para
        # el Administrador, que no tiene vínculos) es [] y no consulta la base.
        "cuentas_vinculadas": cuentas_vinculadas(usuario),
        # NOT-01 (D-42): la campana es de todos los roles menos el Administrador. ``None``: la plantilla no la muestra.
        "campana": estado_de_la_campana(usuario) if rol in tuple(Usuario.Rol) else None,
    }
