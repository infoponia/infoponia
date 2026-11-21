# Categorías del sistema de `inventario` (INV-01; regla 1 de 8.23 del modelo de dominio y CMP-ALT-TIN regla 4). Son cuatro y las
# crea la migración de datos ``cargar_categorias_del_sistema``. TODA regla que dependa de una categoría la busca por ``codigo``
# con estas constantes, nunca por el nombre (el nombre es lo que ve la persona; el código no cambia).

SEMILLAS = "semillas"
ENVASES = "envases"
REPUESTOS_DE_HARDWARE = "repuestos_de_hardware"
INFRAESTRUCTURA = "infraestructura"

# (código, nombre) de las cuatro, en el orden en que se muestran. La migración copia estos valores (no los importa).
CATEGORIAS_DEL_SISTEMA = (
    (SEMILLAS, "Semillas"),
    (ENVASES, "Envases"),
    (REPUESTOS_DE_HARDWARE, "Repuestos de hardware"),
    (INFRAESTRUCTURA, "Infraestructura"),
)


def es_semilla(insumo):
    """Un insumo «es una semilla» si su categoría es la del sistema ``semillas`` (docs/modelo/inventario.md, «Insumo»).
    ``inventario`` lo decide por la categoría y no depende del modelo ``Semilla`` (lo crea INV-03)."""
    return insumo.tipo_insumo.codigo == SEMILLAS
