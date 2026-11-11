# Validadores de campos de core. No importa los modelos, para que core/models.py pueda usarlos.

import re

from django.core.exceptions import ValidationError

LARGO_MAXIMO_TELEFONO = 25  # D-28 (reemplaza el max_length=20 de D-15)
DIGITOS_MINIMOS_TELEFONO = 8  # D-21
DIGITOS_MAXIMOS_TELEFONO = 15  # D-21: máximo de un número internacional

# D-21: solo dígitos, espacios y los símbolos + - ( ), con el + solo al comienzo.
_FORMATO_TELEFONO = re.compile(r"^\+?[\d\s\-()]+$")


def validar_telefono(valor):
    """Valida el formato del teléfono, si se indicó (D-21, USR-ALT-USR regla 9, D-28).

    Textos de los mensajes tomados de ``telErr`` del prototipo. Devuelve un único error: si el
    teléfono es demasiado largo, no se siguen revisando las demás condiciones, así el formulario
    no muestra el mismo problema dos veces. El largo se controla acá y no solo con el
    ``max_length`` del campo, para que el mensaje nombre el límite y la regla del formulario y la
    columna coincidan.
    """
    valor = (valor or "").strip()
    if not valor:
        return  # el teléfono es opcional (regla 7)
    if len(valor) > LARGO_MAXIMO_TELEFONO:
        raise ValidationError(
            f"El teléfono tiene como máximo {LARGO_MAXIMO_TELEFONO} caracteres.",
            code="telefono_largo",
        )
    if not _FORMATO_TELEFONO.match(valor):
        raise ValidationError(
            "El teléfono solo puede tener números, espacios y los símbolos + - ( ). "
            "El + va solo al comienzo.",
            code="telefono_formato",
        )
    digitos = sum(c.isdigit() for c in valor)
    if not DIGITOS_MINIMOS_TELEFONO <= digitos <= DIGITOS_MAXIMOS_TELEFONO:
        raise ValidationError(
            f"Ingresá un teléfono con entre {DIGITOS_MINIMOS_TELEFONO} y "
            f"{DIGITOS_MAXIMOS_TELEFONO} dígitos, por ejemplo +54 376 400-1001.",
            code="telefono_digitos",
        )
