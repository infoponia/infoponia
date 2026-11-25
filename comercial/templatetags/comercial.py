# Filtros de las plantillas de `comercial` (COM-01): el CUIT con guiones y la capacidad de un vehículo con su texto. Solo dan formato.

from django import template

from comercial.servicios.vehiculos import texto_capacidad
from maestros.validadores import formatear_cuit

register = template.Library()


@register.simple_tag(takes_context=True)
def solicitudes_pendientes(context):
    """El contador rojo de la pestaña «Solicitudes de revisión» (COM-CNS-SRV): las solicitudes pendientes, solo para el Gerente (`None` para los demás). Una consulta."""
    from comercial.servicios.solicitudes import pendientes_para

    solicitud = context.get("request")
    return pendientes_para(solicitud.user) if solicitud is not None else None


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


@register.filter
def pesos(valor):
    """Un monto en pesos con dos decimales y coma decimal: «$ 1.500,50» (COM-02; ``None`` da «—»)."""
    from comercial.servicios.compra_ventas import texto_de_pesos

    return "—" if valor is None else texto_de_pesos(valor)
