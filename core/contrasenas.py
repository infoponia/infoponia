# Contraseñas: generación de la contraseña temporal (SEG-04, D-18) y validador de "distinta de la
# actual" (SEG-03, USR-CMB-CTR regla 2). No importa los modelos, para que core/models.py pueda usarlo.

import secrets
import string

from django.core.exceptions import ValidationError

LARGO_CONTRASENA_TEMPORAL = 12  # SEG-04

# SEG-04: letras y dígitos sin los caracteres ambiguos 0, O, 1, l, I.
ALFABETO_CONTRASENA_TEMPORAL = "".join(
    caracter
    for caracter in string.ascii_letters + string.digits
    if caracter not in "0O1lI"
)


def generar_contrasena_temporal():
    """Devuelve una contraseña temporal de 12 caracteres aleatorios (SEG-04, D-18).

    Usa ``secrets`` (generador criptográfico) y no ``random``, que es predecible.
    """
    return "".join(
        secrets.choice(ALFABETO_CONTRASENA_TEMPORAL)
        for _ in range(LARGO_CONTRASENA_TEMPORAL)
    )


class DistintaDeLaActualValidator:
    """Validador de contraseñas de Django: la nueva es distinta de la actual (SEG-03).

    Como la contraseña actual de una cuenta con temporal es la temporal, este validador también
    cubre «distinta de la temporal» (USR-CMB-CTR regla 2). Se registra en
    ``AUTH_PASSWORD_VALIDATORS``, junto con los cuatro validadores de Django que cubren el resto
    de SEG-03 (largo, uso común, solo numérica y parecido a los datos de la cuenta).
    """

    CODIGO = "contrasena_igual_a_la_actual"

    def validate(self, password, user=None):
        """Falla si ``password`` es la contraseña vigente de ``user`` (sin usuario guardado, no aplica)."""
        if user is not None and user.pk is not None and user.check_password(password):
            raise ValidationError(self.get_help_text(), code=self.CODIGO)

    def get_help_text(self):
        """Texto del requisito, que Django usa también como mensaje de error."""
        return "Tu contraseña nueva tiene que ser distinta de la actual."
