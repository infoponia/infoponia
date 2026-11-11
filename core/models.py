# Modelos de core: Usuario con email como identificador y seis roles con herencia multi-tabla, y el
# registro de auditoría. Decisiones D-01 a D-03, D-05, D-09 a D-11, D-18, D-19 y D-22 en
# docs/decisiones.md.

from datetime import timedelta

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.contrasenas import generar_contrasena_temporal
from core.validadores import validar_telefono

# D-10: el Administrador es un superusuario sin ``rol``; para el control de acceso y la auditoría se
# lo trata como un rol más. Viven acá y no en core/acceso.py para que los modelos no importen
# acceso.py (que importa los modelos): la dependencia va en un solo sentido, acceso -> models.
ADMINISTRADOR = "administrador"
# D-22: rol que se guarda en la auditoría cuando la acción la hace InfoPonia y no una cuenta.
ROL_INFOPONIA = "infoponia"

# SEG-04, D-18: la contraseña temporal vence a los 7 días de generada.
VIGENCIA_CONTRASENA_TEMPORAL = timedelta(days=7)


def rol_de(usuario):
    """Rol con el que opera la cuenta: el ``rol`` del dominio o ``ADMINISTRADOR`` (D-10)."""
    if usuario.is_superuser:
        return ADMINISTRADOR
    return usuario.rol


class UsuarioQuerySet(models.QuerySet):
    """QuerySet de cuentas con el alcance por usuario en un único lugar (CLAUDE.md, arquitectura)."""

    def en_alcance_de(self, actor):
        """Cuentas que ``actor`` puede consultar y gestionar (regla 1 de USR-CNS-USR, USR-ALT-USR,
        USR-MOD-USR y USR-BAJ-USR).

        El Gerente gestiona las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico; no
        la suya, ni otros Gerentes, ni Administradores. Cualquier otro actor (también uno inactivo)
        no gestiona ninguna.

        Pendiente, tarea 05 (D-16): el Administrador gestiona la cuenta del Gerente y las de los
        Administradores, incluida la suya; esa rama se agrega acá.
        """
        if (
            actor is None
            or not getattr(actor, "is_active", False)
            or rol_de(actor) != Usuario.Rol.GERENTE
        ):
            return self.none()
        return self.exclude(is_superuser=True).exclude(rol=Usuario.Rol.GERENTE)


class UsuarioManager(BaseUserManager.from_queryset(UsuarioQuerySet)):
    """Crea usuarios usando el email en vez de un nombre de usuario (D-03).

    Se usa tanto desde ``Usuario.objects`` como desde el manager de cada rol
    (``Capataz.objects``, etc.): ``self.model`` es la clase concreta desde la que se
    llamó al manager, así que ``Capataz.objects.create_user(...)`` crea un ``Capataz``.

    El email se guarda siempre en minúsculas y sin espacios (SEG-01, D-19).
    """

    @classmethod
    def normalize_email(cls, email):
        """Email en minúsculas y sin espacios en los extremos (SEG-01).

        Django, por defecto, solo pasa a minúsculas el dominio (lo que sigue a la última «@»);
        SEG-01 pide guardar el email entero en minúsculas.
        """
        return (email or "").strip().lower()

    def get_by_natural_key(self, email):
        """Busca la cuenta por email sin distinguir mayúsculas (lo usa, por ejemplo, ``createsuperuser``)."""
        return self.get(email=self.normalize_email(email))

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

    El email se guarda en minúsculas (``save()`` y ``clean()``) y es único sin distinguir
    mayúsculas (SEG-01, D-19). ``fecha_contrasena_temporal`` guarda cuándo se generó la
    contraseña temporal de la cuenta, y está vacía si la contraseña no es temporal (D-18).
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
    # D-15 (tipo), D-21 (formato) y D-28 (largo de 25, reemplaza el 20 de D-15). El validador
    # controla también el largo, con un mensaje que nombra el límite.
    telefono = models.CharField(
        "teléfono", max_length=25, blank=True, validators=[validar_telefono]
    )
    rol = models.CharField(
        "rol",
        max_length=20,
        choices=Rol.choices,
        blank=True,
        default="",
        help_text="Vacío solo para el Administrador técnico (superusuario, D-10).",
    )
    # D-18, SEG-04: fecha y hora de generación de la contraseña temporal; nula si la contraseña no
    # es temporal. No es editable: la fija el sistema (``asignar_contrasena_temporal``) y la borra
    # el cambio de contraseña (USR-CMB-CTR).
    fecha_contrasena_temporal = models.DateTimeField(
        "fecha de generación de la contraseña temporal",
        null=True,
        blank=True,
        editable=False,
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
            # SEG-01, D-19: el email es único sin distinguir mayúsculas. Se mantiene también
            # ``unique=True`` en el campo: Django exige un campo único para USERNAME_FIELD y no
            # cuenta una restricción con expresión. El código y el mensaje son los que informa
            # ``full_clean()`` (los formularios) cuando el email ya existe.
            models.UniqueConstraint(
                Lower("email"),
                name="email_unico_sin_mayusculas",
                violation_error_code="email_repetido",
                violation_error_message="Ya existe una cuenta con ese email.",
            ),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        """Guarda la cuenta con el email en minúsculas (SEG-01), aunque se lo haya asignado a mano."""
        self.email = type(self).objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def unique_error_message(self, model_class, unique_check):
        """Mensaje en español cuando el email ya existe (SEG-01).

        ``full_clean()`` normaliza el email a minúsculas en ``clean()`` antes de comprobar la
        unicidad, así que un email repetido con otras mayúsculas lo detecta la unicidad del campo
        (error en la clave ``email``, código ``unique``) y no la restricción
        ``email_unico_sin_mayusculas``, que queda como garantía de la base.
        """
        if unique_check == ("email",):
            return ValidationError("Ya existe una cuenta con ese email.", code="unique")
        return super().unique_error_message(model_class, unique_check)

    @property
    def tiene_contrasena_temporal(self):
        """True si la contraseña de la cuenta es temporal (D-18, SEG-04)."""
        return self.fecha_contrasena_temporal is not None

    def contrasena_temporal_vencida(self, ahora=None):
        """True si la contraseña es temporal y ya cumplió su vigencia de 7 días (SEG-04, D-18).

        A los 7 días exactos de generada ya está vencida. Sin contraseña temporal devuelve False.
        """
        if not self.tiene_contrasena_temporal:
            return False
        ahora = ahora or timezone.now()
        return ahora >= self.fecha_contrasena_temporal + VIGENCIA_CONTRASENA_TEMPORAL

    def asignar_contrasena_temporal(self):
        """Pone una contraseña temporal nueva en la cuenta y devuelve su texto plano (SEG-04, D-18).

        Guarda el resumen de la contraseña y la fecha de generación en la instancia, pero no
        la graba: la graba el servicio que la llama (alta, restablecimiento o reactivación), dentro
        de su transacción. El texto plano se muestra una sola vez a quien gestiona la cuenta.
        """
        temporal = generar_contrasena_temporal()
        self.set_password(temporal)
        self.fecha_contrasena_temporal = timezone.now()
        return temporal


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


class RegistroAuditoriaInmutableError(Exception):
    """Se intentó modificar o borrar un registro de auditoría, al que solo se agregan filas (D-22)."""


class RegistroAuditoriaQuerySet(models.QuerySet):
    """QuerySet que no permite modificar ni borrar en bloque (D-22)."""

    def update(self, **kwargs):
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se modifica (D-22).")

    def bulk_update(self, objs, fields, batch_size=None):
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se modifica (D-22).")

    def delete(self):
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se borra (D-22).")


class RegistroAuditoriaManager(models.Manager.from_queryset(RegistroAuditoriaQuerySet)):
    """Manager del registro de auditoría: la única vía de alta es ``registrar`` (D-22)."""

    # SEG-02 y SEG-14: ninguna contraseña queda en la auditoría. Se rechaza todo detalle cuya clave
    # nombre una contraseña, para que un descuido al escribir un servicio no la guarde.
    FRAGMENTOS_PROHIBIDOS = ("contrase", "password")

    def registrar(self, usuario, accion, afectados, detalle=None):
        """Agrega un registro de auditoría y lo devuelve (D-22).

        Se llama desde el servicio del caso de uso, dentro de su ``transaction.atomic()``, para que
        no quede una operación sin su registro ni un registro de una operación que se deshizo.

        - ``usuario``: la cuenta que actuó, o ``None`` si la acción la hace InfoPonia (el rol que
          se guarda es entonces ``ROL_INFOPONIA``). Se guarda el rol que tiene en este momento.
        - ``accion``: un valor de ``RegistroAuditoria.Accion`` (lista cerrada de SEG-14).
        - ``afectados``: las cuentas u objetos afectados; cada uno, una instancia de modelo
          (las cuentas siempre se anotan como ``core.usuario``).
        - ``detalle``: diccionario con los cambios. Sin contraseñas (SEG-02, SEG-14).
        """
        if accion not in RegistroAuditoria.Accion.values:
            raise ValueError(f"Acción de auditoría desconocida: {accion!r} (lista cerrada, SEG-14).")
        detalle = {} if detalle is None else detalle
        self._rechazar_contrasenas(detalle)
        return self.create(
            usuario=usuario,
            rol=ROL_INFOPONIA if usuario is None else rol_de(usuario),
            accion=accion,
            afectados=[self._identificar(objeto) for objeto in afectados],
            detalle=detalle,
        )

    @staticmethod
    def _identificar(objeto):
        """``{"modelo": ..., "id": ...}`` de un objeto afectado. Una cuenta es siempre ``core.usuario``,
        sea cual sea su rol, para poder buscar todos los registros de una cuenta por su id."""
        modelo = Usuario if isinstance(objeto, Usuario) else type(objeto)
        return {"modelo": modelo._meta.label_lower, "id": objeto.pk}

    @classmethod
    def _rechazar_contrasenas(cls, valor):
        """Falla si alguna clave del detalle (a cualquier profundidad) nombra una contraseña."""
        if isinstance(valor, dict):
            for clave, contenido in valor.items():
                if any(f in str(clave).lower() for f in cls.FRAGMENTOS_PROHIBIDOS):
                    raise ValueError(
                        f"El detalle de auditoría no puede incluir contraseñas (clave {clave!r}; "
                        "SEG-02 y SEG-14)."
                    )
                cls._rechazar_contrasenas(contenido)
        elif isinstance(valor, (list, tuple)):
            for contenido in valor:
                cls._rechazar_contrasenas(contenido)


class RegistroAuditoria(models.Model):
    """Registro de auditoría: a esta tabla solo se agregan filas (D-22, SEG-14).

    Guarda quién actuó (``usuario``, nulo si fue InfoPonia) y con qué rol en ese momento, cuándo,
    qué acción, qué cuentas u objetos afectó y el detalle de los cambios. Nunca guarda contraseñas.
    Se escribe con ``RegistroAuditoria.objects.registrar(...)`` desde el servicio del caso de uso,
    dentro de la misma transacción. Una fila guardada no se modifica ni se borra.
    """

    class Accion(models.TextChoices):
        """Lista cerrada de acciones auditadas (SEG-14)."""

        ALTA = "alta", "Alta de cuenta"
        MODIFICACION = "modificacion", "Modificación de cuenta"
        BAJA = "baja", "Baja de cuenta"
        REACTIVACION = "reactivacion", "Reactivación de cuenta"
        RESTABLECIMIENTO = "restablecimiento", "Restablecimiento de cuenta"
        CAMBIO_CONTRASENA = "cambio_contrasena", "Cambio de contraseña"
        RECUPERACION_CONTRASENA = "recuperacion_contrasena", "Recuperación de contraseña"
        VINCULACION = "vinculacion", "Vinculación de cuentas"
        DESVINCULACION = "desvinculacion", "Desvinculación de cuentas"

    # PROTECT: las cuentas no se borran (se dan de baja), y si alguien lo intentara no puede
    # llevarse el registro con ella. Nulo: acción de InfoPonia (D-22, por ejemplo MD-62).
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="cuenta que actuó",
    )
    rol = models.CharField("rol en ese momento", max_length=20)
    fecha_hora = models.DateTimeField("fecha y hora", default=timezone.now, editable=False)
    accion = models.CharField("acción", max_length=30, choices=Accion.choices)
    afectados = models.JSONField(
        "cuentas u objetos afectados",
        default=list,
        help_text='Lista de {"modelo": "core.usuario", "id": 7}.',
    )
    detalle = models.JSONField("detalle de los cambios", default=dict)

    objects = RegistroAuditoriaManager()

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} · {self.rol} · {self.get_accion_display()}"

    def save(self, *args, **kwargs):
        """Solo permite agregar: guardar una fila que ya existe falla (D-22)."""
        if not self._state.adding:
            raise RegistroAuditoriaInmutableError("El registro de auditoría no se modifica (D-22).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Un registro de auditoría no se borra (D-22)."""
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se borra (D-22).")
