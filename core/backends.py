# Backend de autenticación por email: compara el email sin distinguir mayúsculas (SEG-01).

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class BackendEmail(ModelBackend):
    """Identifica a una cuenta por su email, sin distinguir mayúsculas (SEG-01, D-19).

    Hasta la tarea 03 la base todavía guarda el email tal como se escribió y su unicidad
    distingue mayúsculas, así que pueden existir ``Ana@x.com`` y ``ana@x.com``. Si el email
    escrito coincide con más de una cuenta activa es ambiguo: no se identifica ninguna y la
    falla es la genérica de siempre (SEG-06). No se toca ``Usuario`` en esta tarea.
    """

    def authenticate(self, request, email=None, password=None, username=None, **kwargs):
        """Devuelve la cuenta activa que corresponde al email y la contraseña, o None."""
        # AuthenticationForm pasa el email como ``username``; test y código propio, como ``email``.
        email = email if email is not None else username
        if email is None or password is None:
            return None

        modelo = get_user_model()
        # USR-INI-SES regla 2: solo se identifican las cuentas activas.
        candidatas = list(
            modelo._default_manager.filter(email__iexact=email.strip(), is_active=True)[:2]
        )
        if len(candidatas) == 1:
            usuario = candidatas[0]
            if usuario.check_password(password) and self.user_can_authenticate(usuario):
                return usuario
        else:
            # Sin cuenta, o ambigua: se hace el mismo trabajo de hash que con una cuenta real,
            # para que el tiempo de respuesta no revele si el email existe (como hace Django).
            modelo().set_password(password)
        return None
