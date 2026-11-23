# Filtros de las plantillas de `comercial` (COM-01): el CUIT con guiones y la capacidad de un vehículo con su texto. Solo dan formato.

from django import template

from comercial.servicios.vehiculos import texto_capacidad
from maestros.validadores import formatear_cuit

register = template.Library()


@register.filter
def cuit(valor):
    """El CUIT como «XX-XXXXXXXX-X» (``maestros.validadores.formatear_cuit``)."""
    return formatear_cuit(valor)


@register.filter
def kg(valor):
    """La capacidad como «800 kg», «800,5 kg» o «1.250,25 kg» (``texto_capacidad``)."""
    return texto_capacidad(valor)


@register.filter
def get_item(diccionario, clave):
    """``diccionario[clave]`` o ``None`` (para mostrar un dato de una tabla calculada aparte, como la cantidad de direcciones)."""
    return diccionario.get(clave)
