# Modelo de usuario propio de InfoPonia: Usuario con email como identificador y seis roles
# con herencia multi-tabla. Decisiones D-01 a D-03, D-05, D-09 a D-11 en docs/decisiones.md.

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UsuarioManager(BaseUserManager):
    """Crea usuarios usando el email en vez de un nombre de usuario (D-03).

    Se usa tanto desde ``Usuario.objects`` como desde el manager de cada rol
    (``Capataz.objects``, etc.): ``self.model`` es la clase concreta desde la que se
    llamó al manager, así que ``Capataz.objects.create_user(...)`` crea un ``Capataz``.
    """

    def create_user(self, email, password=None, **extra_fields):
        """Crea y guarda un usuario con el email dado. Falla sin email (D-03)."""
        if not email:
            raise ValueError("El usuario necesita un email.")
        email = self.normalize_email(email)
        usuario = self.model(email=email, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **extra_fields):
        """Crea un Administrador técnico: superusuario sin rol (D-10)."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields["rol"] = ""
        if extra_fields.get("is_staff") is not True:
            raise ValueError("El Administrador debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El Administrador debe tener is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    """Usuario de InfoPonia: sin username, con email único y un rol fijo (D-01 a D-03).

    Mapeo con el modelo de dominio (D-02): ``first_name``/``last_name``/``email`` son
    nombreX/apellidoX/emailX; ``telefono`` es telefonoX (campo nuevo); ``is_active`` es
    estadoX (activo/inactivo) y, en False, ya impide iniciar sesión.

    El Gerente de "contacto" de cualquier usuario (R002 a R006 del modelo de dominio) no se
    guarda como columna: es el Gerente con ``rol="gerente"`` e ``is_active=True`` (D-09).

    El ``rol`` se fija una sola vez, al crear el usuario (en el ``save()`` de cada subclase de
    rol), y no se modifica después: para cambiar de rol se da de baja a este usuario y se crea
    otro (D-11).
    """

    class Rol(models.TextChoices):
        GERENTE = "gerente", "Gerente"
        AGRONOMO = "agronomo", "Agrónomo"
        CAPATAZ = "capataz", "Capataz"
        VENDEDOR = "vendedor", "Vendedor"
        TRANSPORTISTA = "transportista", "Transportista"
        TECNICO = "tecnico", "Técnico"

    username = None
    email = models.EmailField("email", unique=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    rol = models.CharField(
        "rol",
        max_length=20,
        choices=Rol.choices,
        blank=True,
        default="",
        help_text="Vacío solo para el Administrador técnico (superusuario, D-10).",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        constraints = [
            # D-10: un usuario sin rol debe ser superusuario, y un superusuario no tiene rol.
            models.CheckConstraint(
                condition=Q(rol="", is_superuser=True)
                | (~Q(rol="") & Q(is_superuser=False)),
                name="rol_vacio_solo_para_superusuario",
            ),
            # D-09: a lo sumo un Gerente activo (unicidad parcial: solo compara filas que
            # cumplen la condición, y entre esas filas `rol` vale siempre "gerente").
            models.UniqueConstraint(
                fields=["rol"],
                condition=Q(rol="gerente", is_active=True),
                name="un_solo_gerente_activo",
            ),
        ]

    def __str__(self):
        return self.email


class RolFijoMixin:
    """Fija `self.rol` al valor de la subclase (D-11: el rol no se modifica después).

    Se fija tanto en `__init__` como en `save()`: `__init__` lo necesita `full_clean()`
    (lo llama el admin antes de guardar, y valida contra el estado actual del objeto, no
    contra lo que `save()` haría); `save()` lo necesita por si alguien construye el objeto
    con `Modelo(rol="otra_cosa")` a mano, para que ese valor nunca se guarde en la base.
    """

    ROL = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rol = self.ROL

    def save(self, *args, **kwargs):
        self.rol = self.ROL
        super().save(*args, **kwargs)


class Gerente(RolFijoMixin, Usuario):
    """Gerente: único activo a la vez (D-09); sin asociaciones todavía (D-04)."""

    ROL = Usuario.Rol.GERENTE
    objects = UsuarioManager()

    class Meta:
        verbose_name = "Gerente"
        verbose_name_plural = "Gerentes"

    def clean(self):
        """Respaldo a nivel de formulario de la restricción de la base (D-09).

        El admin de Gerente no muestra el campo `rol` (lo fija este modelo solo), así que un
        `ModelForm` inválido no dispararía la restricción de la base hasta el INSERT/UPDATE,
        y el admin mostraría un error 500 en vez de un error de formulario. `full_clean()` (que
        el admin llama antes de guardar) sí ejecuta este `clean()`.
        """
        super().clean()
        if self.is_active:
            hay_otro_activo = (
                Gerente.objects.filter(is_active=True).exclude(pk=self.pk).exists()
            )
            if hay_otro_activo:
                raise ValidationError("Ya hay un Gerente activo.")


class Agronomo(RolFijoMixin, Usuario):
    """Agrónomo: sin asociaciones todavía (D-04)."""

    ROL = Usuario.Rol.AGRONOMO
    objects = UsuarioManager()

    class Meta:
        verbose_name = "Agrónomo"
        verbose_name_plural = "Agrónomos"


class Capataz(RolFijoMixin, Usuario):
    """Capataz: sin asociaciones todavía (D-04)."""

    ROL = Usuario.Rol.CAPATAZ
    objects = UsuarioManager()

    class Meta:
        verbose_name = "Capataz"
        verbose_name_plural = "Capataces"


class Vendedor(RolFijoMixin, Usuario):
    """Vendedor: sin asociaciones todavía (D-04)."""

    ROL = Usuario.Rol.VENDEDOR
    objects = UsuarioManager()

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"


class Transportista(RolFijoMixin, Usuario):
    """Transportista: sin asociaciones todavía (D-04)."""

    ROL = Usuario.Rol.TRANSPORTISTA
    objects = UsuarioManager()

    class Meta:
        verbose_name = "Transportista"
        verbose_name_plural = "Transportistas"


class Tecnico(RolFijoMixin, Usuario):
    """Técnico: sin asociaciones todavía (D-04)."""

    ROL = Usuario.Rol.TECNICO
    objects = UsuarioManager()

    class Meta:
        verbose_name = "Técnico"
        verbose_name_plural = "Técnicos"
