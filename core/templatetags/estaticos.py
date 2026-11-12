# Etiqueta {% static_v "ruta" %}: la URL de un archivo estático propio con su fecha de modificación como versión.

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(ruta):
    """URL del archivo estático ``ruta`` con ``?v=<fecha de modificación>``.

    El servidor de desarrollo (``runserver``) sirve los estáticos con ``Last-Modified`` pero sin
    ``Cache-Control``, y los navegadores guardan esos archivos por un tiempo proporcional a su antigüedad
    sin volver a pedirlos: un cambio en la hoja de estilos o en el JavaScript no llegaba hasta forzar la
    recarga. Con la fecha en la URL, cada cambio del archivo es una URL nueva y el navegador la pide.
    Si el archivo no se encuentra, devuelve la URL sin versión.
    """
    url = static(ruta)
    archivo = finders.find(ruta)
    if not archivo:
        return url
    return f"{url}?v={int(os.path.getmtime(archivo))}"
