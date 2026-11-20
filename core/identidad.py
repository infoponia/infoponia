# Identidad de la organización para el marco, las pantallas sin sesión y los correos (D-48). Combina la identidad que
# registró ``maestros`` (punto de extensión de ``core/extensiones.py``) con los valores por defecto: sin registrante, o con
# un nombre vacío, el nombre sale de ``settings.NOMBRE_ORGANIZACION`` (D-25) y no hay color propio (se usa la paleta del
# sistema, D-47).

import re

from django.conf import settings

from core import extensiones

# Un color de la organización solo se escribe en el HTML si cumple esto: va dentro de un <style> y no puede traer nada más.
# Marca de «todavía no se consultó la identidad» (``None`` ya significa «no hay identidad»).
_CONSULTAR = object()

_COLOR_VALIDO = re.compile(r"^#[0-9a-fA-F]{6}\Z")


def nombre_de_la_organizacion(registrada=_CONSULTAR):
    """Nombre de la organización: el de la identidad registrada si no está vacío; si no, ``NOMBRE_ORGANIZACION``.
    ``registrada`` permite reutilizar la identidad ya consultada en el mismo pedido (``None`` = no hay)."""
    registrada = extensiones.identidad_registrada() if registrada is _CONSULTAR else registrada
    nombre = (registrada.nombre or "").strip() if registrada else ""
    return nombre or settings.NOMBRE_ORGANIZACION


def color_principal(registrada=_CONSULTAR):
    """Color principal de la organización (``#RRGGBB``), o ``None`` si no hay o no es válido (se valida otra vez al
    escribirlo, D-48)."""
    registrada = extensiones.identidad_registrada() if registrada is _CONSULTAR else registrada
    color = registrada.color_principal if registrada else None
    return color if isinstance(color, str) and _COLOR_VALIDO.match(color) else None
