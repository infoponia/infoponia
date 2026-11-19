# Validadores de campos de maestros. No importan los modelos, para que maestros/models.py pueda usarlos. Mismo estilo que
# core/validadores.py (D-21, teléfono): una función que lanza ValidationError con un mensaje y un ``code``.
# El formato de estos campos no lo define la regla 2 de PROD-ALT-INV: es un hueco del caso de uso, resuelto en D-39.

import re

from django.core.exceptions import ValidationError

# D-39: entero de hasta 4 dígitos y, como máximo, UN decimal, con coma. En el interior las rutas se referencian con
# medios kilómetros. «4», «4,5» y «875,5» valen; «abc», «6,7777» y «4.5» (con punto) no.
_FORMATO_KILOMETRO = re.compile(r"^\d{1,4}(,\d)?$", re.ASCII)

# D-39: «S/N» (sin distinguir mayúsculas) o un texto que empieza con un número («1234», «1234 bis»).
_FORMATO_NUMERO_CALLE = re.compile(r"^(S/N|\d.*)$", re.IGNORECASE | re.ASCII)


def validar_kilometro(valor):
    """Valida el formato del kilómetro de una dirección rural (D-39, regla 2 de PROD-ALT-INV).

    Es un campo de texto: acá solo se controla el formato. Vacío no es un error de formato: que sea obligatorio lo
    controla el servicio, con su propio mensaje.
    """
    valor = (valor or "").strip()
    if valor and not _FORMATO_KILOMETRO.match(valor):
        raise ValidationError(
            "Ingresá el kilómetro como un número de hasta 4 dígitos, con coma y un solo decimal si hace falta, "
            "por ejemplo 4 o 4,5.",
            code="kilometro_formato",
        )


def validar_numero_calle(valor):
    """Valida el formato del número de una dirección urbana (D-39, regla 2 de PROD-ALT-INV): «S/N» o un texto que
    empieza con un número («1234», «1234 bis»). Vacío no es un error de formato (lo controla el servicio)."""
    valor = (valor or "").strip()
    if valor and not _FORMATO_NUMERO_CALLE.match(valor):
        raise ValidationError(
            "Ingresá el número como «S/N» o empezando con un número, por ejemplo 1234 o 1234 bis.",
            code="numero_calle_formato",
        )


def validar_con_contenido(valor):
    """Valida que un texto libre tenga contenido real: al menos una letra o un número (D-39, reglas 1 y 2 de
    PROD-ALT-INV). Rechaza textos de puros símbolos o signos, como «-----------------».

    El texto sigue siendo libre: «12», «RN 12», «Ruta Nacional 12» y el nombre de un camino son válidos, porque no hay un
    formato común que exigir. Vale para el nombre, la calle, la ruta y los opcionales (piso, departamento, barrio,
    referencias y lote). Vacío no es un error: si el campo es obligatorio lo controla el servicio, con su propio mensaje,
    y un opcional vacío no se valida. Cuentan las letras con tilde o ñ y los números de cualquier alfabeto.
    """
    valor = (valor or "").strip()
    if valor and not any(caracter.isalnum() for caracter in valor):
        raise ValidationError(
            "Ingresá un texto con al menos una letra o un número.",
            code="sin_contenido",
        )
