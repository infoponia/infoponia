# Filtros de plantilla de `compras` (CMP-04): el nombre visible de un tipo de inconveniente de recepción (el código viaja en los datos, el nombre se muestra).
from django import template

from compras.models import InconvenienteRecepcion

register = template.Library()


@register.filter
def tipo_de_inconveniente(codigo):
    """«mercaderia_danada» → «Mercadería dañada»; un código desconocido se muestra tal cual."""
    try:
        return InconvenienteRecepcion.Tipo(codigo).label
    except ValueError:
        return codigo
