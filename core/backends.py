# Backend de autenticación por email: compara el email sin distinguir mayúsculas (SEG-01) y rechaza
# la contraseña temporal vencida (SEG-04).

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class BackendEmail(ModelBackend):
    """Identifica a una cuenta por su email, sin distinguir mayúsculas (SEG-01, D-19).

    La base guarda el email en minúsculas y es único sin distinguir mayúsculas, así que el email
    escrito se pasa a minúsculas y coincide con a lo sumo una cuenta. Toda falla devuelve ``None``
    y el formulario muestra el mismo mensaje genérico (SEG-06).
    """

    def authenticate(self, request, email=None, password=None, username=None, **kwargs):
        """Devuelve la cuenta activa que corresponde al email y la contraseña, o None."""
        # AuthenticationForm pasa el email como ``username``; test y código propio, como ``email``.
        email = email if email is not None else username
        if email is None or password is None:
            return None

        modelo = get_user_model()
        # USR-INI-SES regla 2: solo se identifican las cuentas activas.
        usuario = modelo._default_manager.filter(
            email=modelo._default_manager.normalize_email(email), is_active=True
        ).first()
        if usuario is None:
            # Sin cuenta: se hace el mismo trabajo de hash que con una cuenta real, para que el
            # tiempo de respuesta no revele si el email existe (como hace Django).
            modelo().set_password(password)
            return None

        if not (usuario.check_password(password) and self.user_can_authenticate(usuario)):
            return None
        # USR-INI-SES regla 4 y SEG-04: una contraseña temporal vencida no sirve para identificarse.
        if usuario.contrasena_temporal_vencida():
            return None
        return usuario
