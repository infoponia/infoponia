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


@register.simple_tag(takes_context=True)
def cobranza_en_mora(context):
    """El contador rojo de la pestaña «Cobranza» (COM-08a): las entregas de suministro en mora del alcance de quien mira (`None` para los demás roles). Pocas consultas."""
    from comercial.servicios import cobranza
    from inventario.servicios import stock

    solicitud = context.get("request")
    return cobranza.en_mora_para(solicitud.user, stock.hoy()) if solicitud is not None else None


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


# ---- COM-08c: números de las estadísticas. El servicio devuelve `Decimal` sin redondear; se redondea acá, recién para mostrar. ----


@register.filter
def porcentaje(valor):
    """Un porcentaje entero («50 %»), redondeado a lo que corresponde (`ROUND_HALF_UP`); `None` da «—»."""
    from decimal import ROUND_HALF_UP, Decimal

    return "—" if valor is None else f"{Decimal(valor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)} %"


@register.filter
def miles(valor):
    """Un entero con punto de miles («12.500»)."""
    return f"{int(valor):,}".replace(",", ".")


@register.filter
def un_decimal(valor):
    """Un promedio con un decimal y coma («1,5»), `ROUND_HALF_UP`; `None` da «—»."""
    from decimal import ROUND_HALF_UP, Decimal

    return "—" if valor is None else str(Decimal(valor).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)).replace(".", ",")


@register.filter
def ancho_de_barra(monto, maximo):
    """El ancho en % (con punto decimal, para el CSS) de la barra de `monto` frente al mayor (`maximo`); mínimo 2 % si hay monto, para que se vea."""
    from decimal import Decimal

    if not maximo or not monto:
        return "0"
    return f"{max(Decimal(2), Decimal(monto) * 100 / Decimal(maximo)):.1f}"
