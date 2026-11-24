# Filtros de las plantillas de `produccion` (PRD-01, paso 8): leer de un diccionario los campos que se arman con un prefijo y un id
# (`sector_12`, `utilizada_7`), que las plantillas de Django no pueden componer.
from django import template

register = template.Library()


@register.filter
def valor(valores, clave):
    """`valores[clave]` o `""`: lo que la persona escribió en un campo (para volver a mostrarlo)."""
    return valores.get(clave, "") if valores else ""


@register.simple_tag
def campo(valores, prefijo, *ids):
    """Lo escrito en el campo `<prefijo>_<id>[_<id>]`, o `""`."""
    return (valores or {}).get("_".join([prefijo, *map(str, ids)]), "")


@register.filter
def de(diccionario, clave):
    """`diccionario[clave]` o `None`: lo que un punto de extensión (acciones o detalle de una cosecha) devolvió para esa orden."""
    return (diccionario or {}).get(clave)


@register.filter
def cantidad(valor_numerico):
    """Una cantidad sin ceros de más: `Decimal('50.000')` → `50`; `None` → `—`."""
    if valor_numerico is None:
        return "—"
    texto = format(valor_numerico.normalize() if hasattr(valor_numerico, "normalize") else valor_numerico, "f")
    return texto


@register.filter
def lotes_de(lotes_por_existencia, existencia_id):
    """Los lotes de insumo con stock de una existencia (`{existencia_id: [LoteInsumo]}`), o una lista vacía."""
    return (lotes_por_existencia or {}).get(existencia_id, [])


PERFILES = {
    "hoja_verde": "hoja verde", "pastura": "pastura", "frutos_grandes": "frutos grandes",
    "frutos_pequenos": "frutos pequeños", "flores": "flores", "hierbas": "hierbas",
}


@register.filter
def perfil_legible(perfil):
    """El perfil familiar de una variedad con su nombre visible (`hoja_verde` → «hoja verde»); `core` y `maestros` no se importan acá."""
    return PERFILES.get(perfil, perfil)
