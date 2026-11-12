# Filtros de plantilla de las pantallas de cuentas (USR-CNS-USR y USR-ALT-USR).

from django import template

from core.acceso import nombre_visible_del_rol

register = template.Library()


@register.filter
def rol_visible(cuenta):
    """Nombre del rol de ``cuenta`` para mostrar: «Capataz», «Gerente» o «Administrador».

    ``get_rol_display`` no sirve para el Administrador, que no tiene ``rol`` (D-10): daría un texto vacío.
    """
    return nombre_visible_del_rol(cuenta)
