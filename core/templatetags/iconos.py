# Etiqueta {% icono "nombre" tamaño %} con los íconos SVG del prototipo (función ic()).

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Trazos tomados de ic() en docs/prototipos/cuentas_y_seguridad.html. Solo los que se usan.
_TRAZOS = {
    "leafmark": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "chev": '<polyline points="6 9 12 15 18 9"/>',
    "out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    "dash": '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/>'
    '<rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>',
    "eye": '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
    "eyeoff": '<path d="M17.9 17.9A10.9 10.9 0 0 1 12 19C5 19 1 12 1 12a18.5 18.5 0 0 1 5.1-5.9M9.9 5.1A10.7 10.7 0 0 1 12 5c7 0 11 7 11 7a18.6 18.6 0 0 1-2.2 3.2M1 1l22 22"/>',
    "x": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
}


@register.simple_tag
def icono(nombre, tamano=16):
    """Devuelve el SVG del ícono ``nombre``.

    ``mark_safe`` es seguro acá: los trazos son constantes de este archivo y el tamaño se
    convierte a entero, así que nada que escriba una persona llega al HTML.
    """
    trazos = _TRAZOS[nombre]
    tamano = int(tamano)
    return mark_safe(
        f'<svg width="{tamano}" height="{tamano}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{trazos}</svg>'
    )
