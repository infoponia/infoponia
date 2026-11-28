# Etiqueta {% primer_error %}: dice cuál es el primer error que se ve en la pantalla, para marcarlo con ``data-llevar-vista`` (UI-06, D-109 punto 9).

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def llevar_vista(primero, *claves):
    """Los atributos que `infoponia.js` busca, `data-llevar-vista tabindex="-1"`, si ``primero`` (lo que devolvió `primer_error`) es una de
    ``claves``; si no, nada. Se pone dentro de la etiqueta del error: ``<div class="err"{% llevar_vista primero "cantidad" %}>``. Una clave puede
    ir en más de una ``claves`` cuando un mismo cuadro muestra dos errores distintos (el aviso general y otro que no tiene campo)."""
    return mark_safe(' data-llevar-vista tabindex="-1"') if primero and primero in claves else ""


_YA_LLEVADA = "_ui06_llevar_vista_usada"


@register.simple_tag(takes_context=True)
def llevar_vista_una_vez(context):
    """Los mismos atributos, pero solo la PRIMERA vez que se usa en la página que se dibuja: el primer error (o el resumen) que aparece en pantalla.
    Sirve donde los errores no están en un único diccionario con claves fijas (los portales por enlace, las filas anidadas, un resumen que llega por
    HTMX) y `primer_error` no puede saber el orden. Se pone en cada error y en el resumen: ``<div class="err"{% llevar_vista_una_vez %}>``. El orden
    de dibujo es el orden de la pantalla, así que sale exactamente una marca. El estado queda en el contexto de esa respuesta (cada respuesta se
    dibuja con el suyo) y lo comparten los `{% include %}` sin `only`.

    Solo marca en la respuesta a un envío (POST): la carga inicial de una pantalla no lleva la vista ni el foco aunque ya muestre un aviso propio
    (por ejemplo, «Concretar entrega» abre diciendo que falta el medio de pago). Sin `request` en el contexto (una plantilla dibujada a mano) marca."""
    request = context.get("request")
    if request is not None and request.method != "POST":
        return ""
    estado = context.dicts[0]  # el nivel más bajo del contexto: lo ven todos los `{% for %}`, `{% if %}` e `{% include %}` de la respuesta
    if estado.get(_YA_LLEVADA):
        return ""
    estado[_YA_LLEVADA] = True
    return mark_safe(' data-llevar-vista tabindex="-1"')


@register.simple_tag
def llevar_vista_fila(primero, prefijo, *ids):
    """Lo mismo que `llevar_vista` para el error de una fila, cuya clave es ``<prefijo>_<id>[_<id>]`` (la misma que arma la etiqueta `campo` de
    `produccion` y la que usan las vistas): ``<div class="err"{% llevar_vista_fila primero "sector" s.sector_id %}>``."""
    return mark_safe(' data-llevar-vista tabindex="-1"') if primero and primero == "_".join([prefijo, *map(str, ids)]) else ""


@register.simple_tag
def primer_error(errores, *claves):
    """La primera de ``claves`` que tiene un error en ``errores``, o ``""`` si ninguna lo tiene.

    ``errores`` es lo que reciben las plantillas de formulario: un diccionario ``{campo: mensaje}``, ``{campo: [mensajes]}`` o los errores de
    un ``Form`` de Django; también puede ser ``None``. ``claves`` va en el orden en que los errores se ven en la pantalla (el aviso general
    primero, después cada campo de arriba abajo). Así la plantilla marca exactamente un error con ``data-llevar-vista``, el primero que
    la persona ve, sin que la vista tenga que saberlo:
    ``{% primer_error errores "general" "cantidad" "fecha_programada" as primero %}`` y, en cada error, ``{% llevar_vista primero "cantidad" %}``.

    Una clave que termina en ``*`` (``"sector_*"``) es el error de una fila, cuya clave lleva el id (``sector_12``): vale el primer error del diccionario
    que empieza con ese prefijo. Entre varias filas con error no se conoce el orden en pantalla; el servicio rechaza de a una fila por vez.
    """
    if not errores:
        return ""
    for clave in claves:
        if clave.endswith("*"):
            prefijo = clave[:-1]
            for encontrada, error in errores.items():
                if error and encontrada.startswith(prefijo):
                    return encontrada
        elif errores.get(clave):
            return clave
    return ""
