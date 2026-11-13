# Filtros de plantilla de las pantallas de cuentas (USR-CNS-USR, USR-ALT-USR y cuentas vinculadas).

from django import template

from core.acceso import nombre_visible_del_rol, rol_de
from core.menu import SIGLAS

register = template.Library()


@register.filter
def sigla(cuenta):
    """Sigla del rol de ``cuenta`` para su avatar («AGR», «ADM»), como en el prototipo (SHORT)."""
    return SIGLAS.get(rol_de(cuenta), "")


@register.filter
def rol_visible(cuenta):
    """Nombre del rol de ``cuenta`` para mostrar: «Capataz», «Gerente» o «Administrador».

    ``get_rol_display`` no sirve para el Administrador, que no tiene ``rol`` (D-10): daría un texto vacío.
    """
    return nombre_visible_del_rol(cuenta)
