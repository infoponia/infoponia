# Filtros de plantilla de «Inventario» (INV-02, paso 8): cantidades con su unidad y coma decimal, pesos, fechas y el estado de un lote.
# Solo dan formato: ninguna regla de negocio vive acá (las reglas son de los servicios). Nunca usan ``float`` (CLAUDE.md, convenciones).

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.utils.html import format_html

from inventario.servicios import alertas_de_stock, stock
from inventario.unidades import Unidad

register = template.Library()


@register.filter
def num(valor, unidad):
    """La cantidad con los decimales de su unidad y sin ceros de más, con coma decimal: ``Decimal("12.500")|num:"l"`` → «12,5»."""
    if valor is None or valor == "":
        return ""
    return alertas_de_stock._numero(Decimal(valor), unidad)


@register.filter
def cant(valor, unidad):
    """La cantidad con su unidad: ``Decimal("12.5")|cant:"l"`` → «12,5 L»."""
    if valor is None or valor == "":
        return ""
    return alertas_de_stock._con_unidad(Decimal(valor), unidad)


@register.filter
def unidad_de(unidad):
    """La etiqueta de una unidad («l» → «L»)."""
    return Unidad(unidad).label


@register.filter
def pesos(valor):
    """Un importe en pesos con 2 decimales, punto de mil y coma decimal: «$ 1.500,00»; un negativo lleva el signo delante."""
    if valor is None or valor == "":
        return ""
    numero = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero, _, decimales = f"{abs(numero):.2f}".partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    signo = "−" if numero < 0 else ""
    return f"{signo}$ {entero},{decimales}"


@register.filter
def fecha(valor):
    """Una fecha como dd/mm/aaaa; vacía si no hay."""
    return valor.strftime("%d/%m/%Y") if valor else ""


@register.filter
def dato(mapa, clave):
    """``mapa[clave]`` o vacío (para leer lo que se escribió y los errores por campo con un nombre armado)."""
    return (mapa or {}).get(clave, "")


def _dias(texto_unico, texto_plural, n):
    return texto_unico if n == 1 else texto_plural.format(n=n)


@register.filter
def estado_del_lote(lote_con_estado):
    """La ficha de estado de un lote (regla 4 de CMP-CNS-IIN): faltante, agotado, sin vencimiento, vencido, «vence en N días» o al día."""
    lote, estado = lote_con_estado.lote, lote_con_estado.estado
    if estado == "faltante":
        return format_html('<span class="status-badge status-danger">Faltante sin lote</span>')
    if estado == "agotado":
        return format_html('<span class="status-badge status-neutral">Agotado</span>')
    if estado == "sin_vencimiento":
        return format_html('<span class="status-badge status-neutral">Sin vencimiento</span>')
    dias = (lote.fecha_vencimiento - stock.hoy()).days if lote.fecha_vencimiento else 0
    if estado == "vencido":
        return format_html('<span class="status-badge status-danger">Vencido hace {}</span>', _dias("1 día", "{n} días", -dias))
    if estado == "por_vencer":
        texto = "vence hoy" if dias == 0 else _dias("vence mañana", "vence en {n} días", dias)
        return format_html('<span class="status-badge status-warn">{}</span>', texto)
    return format_html('<span class="status-badge status-ok">Al día</span>')
