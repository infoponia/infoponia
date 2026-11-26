# Presentación de las estadísticas (EST-01): convierte una `Comparacion` (D-93 punto 2) en el texto y el color de la diferencia contra el
# período anterior, y arma las barras de CSS de los gráficos (sin bibliotecas de gráficos). Solo formatea: no calcula ningún indicador.

from decimal import Decimal

from django.utils.formats import number_format


def delta(comparacion, *, mejor_si_sube=True, decimales=0, unidad="", con_porcentaje=True):
    """El texto y la clase de color de una `Comparacion`, o `None` si no hay valor actual que comparar.

    Con el período anterior sin dato o en 0 dice «sin datos antes» (como el prototipo: no hay con qué comparar). `mejor_si_sube` decide si una
    suba es buena (verde) o mala (rojo): para la merma o los costos, no. `unidad` va después del número («pts», «$»).
    """
    if comparacion is None or comparacion.valor is None:
        return None
    if comparacion.anterior is None or comparacion.anterior == 0:
        return {"texto": "sin datos antes", "clase": ""}
    if comparacion.diferencia == 0:
        return {"texto": "igual que antes", "clase": ""}
    sube = comparacion.diferencia > 0
    buena = sube == mejor_si_sube
    cuanto = number_format(abs(comparacion.diferencia), decimal_pos=decimales, use_l10n=True, force_grouping=True)
    texto = f"{'▲' if sube else '▼'} {cuanto}{(' ' + unidad) if unidad else ''}"
    if con_porcentaje and comparacion.porcentaje is not None:
        texto += f" ({number_format(abs(comparacion.porcentaje), decimal_pos=1, use_l10n=True)} %)"
    return {"texto": f"{texto} frente al período anterior", "clase": "up" if buena else "dn"}


def barras(filas, valor):
    """Las `filas` con el ancho (0 a 100) de su barra, relativo a la mayor: lista de `(fila, ancho)`. `valor(fila)` es lo que mide la barra."""
    filas = list(filas)
    mayor = max((Decimal(valor(f)) for f in filas), default=Decimal(0))
    return [(f, int(Decimal(valor(f)) * 100 / mayor) if mayor else 0) for f in filas]
