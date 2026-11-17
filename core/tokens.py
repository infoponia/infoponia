# Token del enlace de invitación (SEG-20, D-35). Es un generador propio, distinto del de recuperación de contraseña
# de Django (``default_token_generator``, D-34): otra «sal» (un token de un tipo no sirve para el otro), otro plazo
# (7 días, el de la contraseña temporal, sin tocar PASSWORD_RESET_TIMEOUT, que es la hora de la recuperación) y la
# fecha de la invitación dentro de la firma (cada invitación nueva anula la anterior).

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int

from core.models import VIGENCIA_CONTRASENA_TEMPORAL


class GeneradorInvitacion(PasswordResetTokenGenerator):
    """Genera y verifica el token del enlace de invitación (SEG-20, D-35).

    Hereda de ``PasswordResetTokenGenerator`` la firma (HMAC con ``SECRET_KEY`` y sus claves anteriores) y la forma
    del token (marca de tiempo y firma). Cambia tres cosas:

    - ``key_salt`` propio: el mismo usuario y la misma hora dan otra firma que en la recuperación, así que un token de
      recuperación no sirve como invitación ni al revés.
    - ``_make_hash_value`` suma la fecha de la invitación: reenviar la invitación (restablecer el acceso con otra) o
      dejar de tenerla (aceptarla, recuperar la contraseña o recibir una temporal) anula los enlaces anteriores.
      Elegir una contraseña también los anula por el resumen de la contraseña, que Django ya firma.
    - ``check_token`` vence a los 7 días (``VIGENCIA_CONTRASENA_TEMPORAL``) en lugar de ``PASSWORD_RESET_TIMEOUT``.
    """

    key_salt = "core.tokens.GeneradorInvitacion"

    def _make_hash_value(self, user, timestamp):
        """Lo que firma Django (id, resumen de la contraseña, último inicio de sesión, marca de tiempo y email) más
        la fecha de la invitación pendiente."""
        fecha = "" if user.fecha_invitacion is None else user.fecha_invitacion.replace(microsecond=0, tzinfo=None)
        return f"{super()._make_hash_value(user, timestamp)}{fecha}"

    def check_token(self, user, token):
        """True si ``token`` es una invitación válida para ``user`` y no pasaron 7 días desde que se generó.

        Es la ``check_token`` de Django 5.2 (django/contrib/auth/tokens.py) con un único cambio: el plazo. Django
        compara contra ``settings.PASSWORD_RESET_TIMEOUT`` y no ofrece otro gancho, así que la única forma de tener
        un plazo propio sin cambiar el de la recuperación es repetir el método. Si se actualiza Django, hay que
        revisarlo: lo cubren las pruebas de 7 días ± 1 s y la de los tokens cruzados (test_usr_alt_usr.py).
        """
        if not (user and token):
            return False
        try:
            marca_b36, _ = token.split("-")
            marca = base36_to_int(marca_b36)
        except ValueError:
            return False

        # La firma tiene que corresponder a esta cuenta y a esta marca de tiempo, con la clave actual o una anterior.
        for clave in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, marca, clave), token):
                break
        else:
            return False

        # El único cambio respecto de Django: el plazo de la invitación (SEG-20: 7 días).
        if (self._num_seconds(self._now()) - marca) > VIGENCIA_CONTRASENA_TEMPORAL.total_seconds():
            return False
        return True


generador_invitacion = GeneradorInvitacion()
