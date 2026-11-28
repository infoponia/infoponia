# Filtros de plantilla para dibujar campos de formulario: marcar como inválido un campo que no tiene un error propio
# (UI-03, UX-12; D-109 punto 8).

from django import template

register = template.Library()


@register.filter
def marcado_invalido(campo):
    """Dibuja el widget de ``campo`` (un ``BoundField``) con ``aria-invalid="true"``, sin cambiar sus demás atributos.

    Sirve para los campos de un grupo que se marcan junto con el campo que tiene el error: en Nuevo invernadero, cuando falta
    la ubicación, el error va en Localidad y también se marcan Provincia y Departamento si están vacíos (UX-12, D-109 punto 8).
    Los campos con un error propio no lo necesitan: Django ya les pone ``aria-invalid``."""
    return campo.as_widget(attrs={"aria-invalid": "true"})
