# Unidades de medida de los insumos (INV-01; regla 5 de CMP-ALT-INS y regla 2 de 8.23 del modelo de dominio): lista fija en
# el código, sin tabla ni migración de datos (confirmado el 19/11/2026). ``validar_cantidad`` es la ÚNICA función que decide si
# una cantidad es válida para un insumo (la usan INV-01, INV-02 y, después, producción y compras). Nunca ``float``.

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models

# Toda cantidad de inventario se guarda con 3 decimales en la base (docs/modelo/inventario.md, «Convenciones»).
DECIMALES_DE_LA_BASE = 3


class Unidad(models.TextChoices):
    """Las ocho unidades de medida. El valor es el código que se guarda; la etiqueta, lo que se muestra (D: «l» y «ml» en
    minúscula en la base, como el modelo; se muestran «L» y «mL»)."""

    UNIDAD = "unidad", "unidad"
    KG = "kg", "kg"
    G = "g", "g"
    L = "l", "L"
    ML = "ml", "mL"
    M3 = "m3", "m³"
    M = "m", "m"
    M2 = "m2", "m²"


# Decimales que admite cada unidad (regla 5 de CMP-ALT-INS): unidad solo enteros; kg, L y m³ hasta 3; g, mL, m y m² hasta 2.
DECIMALES = {
    Unidad.UNIDAD: 0,
    Unidad.KG: 3,
    Unidad.G: 2,
    Unidad.L: 3,
    Unidad.ML: 2,
    Unidad.M3: 3,
    Unidad.M: 2,
    Unidad.M2: 2,
}


def decimales_de(unidad):
    """Cuántos decimales admite ``unidad`` (un valor de ``Unidad`` o su código); ``ValueError`` si no existe."""
    try:
        return DECIMALES[Unidad(unidad)]
    except ValueError:
        raise ValueError(f"La unidad «{unidad}» no existe.") from None


def texto_de_decimales(unidad):
    """El texto de «decimales que admite» de una unidad, para las listas de elección: «(solo enteros)» o «(admite 3 decimales)»."""
    cantidad = decimales_de(unidad)
    if cantidad == 0:
        return "solo enteros"
    return f"admite {cantidad} decimal" if cantidad == 1 else f"admite {cantidad} decimales"


def _como_decimal(valor):
    """``valor`` como ``Decimal`` (un ``float`` se rechaza: nunca se mezcla con dinero ni con cantidades)."""
    if isinstance(valor, float) or isinstance(valor, bool):
        raise TypeError("Una cantidad no puede ser float ni bool: usá Decimal o texto.")
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValidationError("Ingresá una cantidad válida.", code="cantidad_invalida") from None


def cuantizar(valor, unidad):
    """``valor`` redondeado (mitad hacia arriba) a los decimales de ``unidad``. Para cantidades que se CALCULAN; las que
    ingresa una persona pasan por ``validar_cantidad``, que no redondea sino que rechaza."""
    paso = Decimal(1).scaleb(-decimales_de(unidad))
    return _como_decimal(valor).quantize(paso, rounding=ROUND_HALF_UP)


def validar_cantidad(valor, unidad):
    """La cantidad como ``Decimal`` cuantizado a los decimales de la unidad, o ``ValidationError``.

    Rechaza lo que no es un número finito y lo que tiene más decimales que los que admite la unidad (no redondea en silencio:
    la persona tiene que ver el límite). No comprueba el signo: cada caso de uso decide si admite cero o negativos.
    """
    numero = _como_decimal(valor)
    if not numero.is_finite():
        raise ValidationError("Ingresá una cantidad válida.", code="cantidad_invalida")
    permitidos = decimales_de(unidad)
    if numero != cuantizar(numero, unidad):
        etiqueta = Unidad(unidad).label
        mensaje = (
            f"La unidad {etiqueta} solo admite cantidades enteras."
            if permitidos == 0
            else f"La unidad {etiqueta} admite hasta {permitidos} decimal{'es' if permitidos > 1 else ''}."
        )
        raise ValidationError(mensaje, code="decimales_de_la_unidad")
    return cuantizar(numero, unidad)
