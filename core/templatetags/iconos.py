# Etiqueta {% icono "nombre" tamaño %} con los íconos SVG del prototipo (función ic()).

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Trazos tomados de ic() de los prototipos (cuentas y seguridad; producción desde UI-01).
_TRAZOS = {
    "leafmark": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "chev": '<polyline points="6 9 12 15 18 9"/>',
    "out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    "dash": '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/>'
    '<rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>',
    "eye": '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
    "eyeoff": '<path d="M17.9 17.9A10.9 10.9 0 0 1 12 19C5 19 1 12 1 12a18.5 18.5 0 0 1 5.1-5.9M9.9 5.1A10.7 10.7 0 0 1 12 5c7 0 11 7 11 7a18.6 18.6 0 0 1-2.2 3.2M1 1l22 22"/>',
    "x": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "warn": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "back": '<polyline points="15 18 9 12 15 6"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    # MAE-05: el camión de «Logística», copiado de logistica_transportista.html.
    "cart": '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h8.2a2 2 0 0 0 2-1.5L22 7H6"/>',
    "truck": '<path d="M1 4h14v12H1zM15 9h4l3 3v4h-7z"/><circle cx="5.5" cy="18.5" r="2"/><circle cx="18" cy="18.5" r="2"/>',
    # MAE-01: íconos de Producción, copiados del prototipo.
    "leaf": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10zM2 21c0-3 1.9-5.5 6-7"/>',
    "pin": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "wifi": '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r="1" fill="currentColor"/>',
    "pencil": '<path d="M4 20h4L19 9l-4-4L4 16v4z"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    # UI-01 (D-47): el resto de los íconos de ic() del prototipo de producción, para que las tareas de la ronda no toquen core.
    "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>',
    "right": '<polyline points="9 6 15 12 9 18"/>',
    "home": '<path d="M3 10.5 12 3l9 7.5V21H3z"/><path d="M9 21v-6h6v6"/>',
    "gear": '<path d="M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.3a2 2 0 0 1-2 0l-.2-.1a2 2 0 0 0-2.7.7l-.2.4a2 2 0 0 0 .7 2.7l.1.1a2 2 0 0 1 1 1.7v.5a2 2 0 0 1-1 1.7l-.1.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0 0 1 2 0l.4.3a2 2 0 0 1 1 1.7V20a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0 0 1 1-1.7l.4-.3a2 2 0 0 1 2 0l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7-2.7l-.1-.1a2 2 0 0 1-1-1.7v-.5a2 2 0 0 1 1-1.7l.1-.1a2 2 0 0 0 .7-2.7l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.3a2 2 0 0 1-1-1.7V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "ext": '<path d="M14 3h7v7M21 3l-9 9M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
    "box": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    # CMP-01: «Compras» del menú (ic('pkg') del prototipo de compras y contabilidad).
    "pkg": '<path d="m21 8-9-5-9 5v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "tool": '<path d="M14.7 6.3a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3z"/><path d="M14.7 6.3 17 4l3 3-2.3 2.3"/>',
    "sprout": '<path d="M12 21v-9M12 12c0-4-3-6-7-6 0 4 3 6 7 6zM12 15c0-3 2.5-5 6-5 0 3-2.5 5-6 5z"/>',
    "move": '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
    "cut": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
    "drop": '<path d="M12 2.7 6.3 8.4a8 8 0 1 0 11.4 0z"/>',
    "cal": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "minus": '<path d="M5 12h14"/>',
    "dots": '<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
    "addto": '<path d="M3 10.5 12 3l9 7.5V21H3z"/><path d="M12 11v6M9 14h6"/>',
    "off": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    "ret": '<path d="M9 14l-4-4 4-4"/><path d="M5 10h9a5 5 0 0 1 0 10h-3"/>',
    # IOT-01: los íconos del módulo IoT, copiados del objeto ``P`` del prototipo (docs/prototipos/iot/iot.html, línea 203).
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
    '<path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
    "router": '<rect x="2" y="14" width="20" height="8" rx="2"/>'
    '<path d="M6 18h.01M10 18h.01M15 10v4M17.8 7.2a4 4 0 0 0-5.6 0M20.7 4.3a8 8 0 0 0-11.4 0"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z"/>',
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
