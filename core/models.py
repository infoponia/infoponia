# Modelos de core: Usuario con email como identificador y seis roles con herencia multi-tabla, el grupo de
# cuentas vinculadas, el registro de auditoría y las notificaciones. Decisiones D-01 a D-03, D-05, D-09 a D-11, D-17,
# D-18, D-19, D-22, D-35, D-36 y D-42 (docs/decisiones/).

from datetime import timedelta

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.indexes import GinIndex
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
# D-65 punto 8 y D-88 punto 5: roles «externos» que se guardan en la auditoría cuando actúa alguien sin cuenta que entró por un
# enlace (el cliente que decide un faltante, el proveedor que cotiza). Los crea la primera tarea que los necesita (CMP-02a);
# la otra (COM-04c) solo usa su constante.
ROL_CLIENTE_ENLACE = "cliente_enlace"
ROL_PROVEEDOR_ENLACE = "proveedor_enlace"
ROLES_EXTERNOS = (ROL_CLIENTE_ENLACE, ROL_PROVEEDOR_ENLACE)

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

        - El Gerente gestiona las cuentas de Agrónomo, Capataz, Vendedor, Transportista y Técnico; no
          la suya, ni otros Gerentes, ni Administradores (D-28).
        - El Administrador gestiona las cuentas de Gerente (la activa y las anteriores) y las de los
          Administradores, incluida la suya (D-16, tarea 05).
        - Cualquier otro actor (también uno inactivo) no gestiona ninguna.
        """
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        rol = rol_de(actor)
        if rol == Usuario.Rol.GERENTE:
            return self.exclude(is_superuser=True).exclude(rol=Usuario.Rol.GERENTE)
        if rol == ADMINISTRADOR:
            return self.filter(Q(is_superuser=True) | Q(rol=Usuario.Rol.GERENTE))
        return self.none()


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


class GrupoCuentas(models.Model):
    """Grupo de cuentas vinculadas de una misma persona (D-17, USR-VNC-CTA).

    No tiene datos propios: es el conjunto de las cuentas que apuntan a él con ``Usuario.grupo``. Un grupo
    con una sola cuenta no existe: el servicio lo borra cuando una desvinculación lo deja así (postcondición b
    de USR-VNC-CTA). Los grupos los crean, unen y borran los servicios de ``core/servicios.py``, nunca a mano.
    """

    class Meta:
        verbose_name = "Grupo de cuentas vinculadas"
        verbose_name_plural = "Grupos de cuentas vinculadas"

    @staticmethod
    def texto_de(grupo_id):
        """Texto de un grupo a partir de su id. Sirve aunque el grupo ya no exista: la auditoría guarda la
        referencia de un grupo que se disolvió (D-36)."""
        return f"Grupo {grupo_id}"

    def __str__(self):
        return self.texto_de(self.pk)


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

    ``grupo`` agrupa las cuentas vinculadas de una misma persona (D-17): es opcional y, mientras tenga cuentas,
    el grupo no se borra (``PROTECT``). Las cuentas de Administrador no tienen grupo (regla 5 de USR-VNC-CTA).
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
    # D-35, SEG-20: fecha y hora en que se envió la invitación pendiente; nula si la cuenta no tiene una. Mientras
    # está pendiente, la contraseña no es utilizable (la persona todavía no eligió la suya). La fija el sistema
    # (``asignar_invitacion``) y la borra elegir una contraseña: aceptar la invitación, recuperarla o recibir una
    # temporal. Nunca convive con ``fecha_contrasena_temporal`` (restricción ``invitacion_o_temporal``).
    fecha_invitacion = models.DateTimeField(
        "fecha de envío de la invitación",
        null=True,
        blank=True,
        editable=False,
    )

    # D-17: grupo de cuentas vinculadas; opcional. PROTECT: un grupo no se borra mientras tenga cuentas (el
    # servicio las saca antes de borrarlo).
    grupo = models.ForeignKey(
        GrupoCuentas,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cuentas",
        verbose_name="grupo de cuentas vinculadas",
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
            # Regla 5 de USR-VNC-CTA y D-17: las cuentas de Administrador no se vinculan. Respaldo de la
            # base: la regla la controla ``vincular_cuenta``.
            models.CheckConstraint(
                condition=Q(grupo__isnull=True) | Q(is_superuser=False),
                name="administrador_sin_grupo",
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
            # D-35: una cuenta nunca tiene a la vez una invitación pendiente y una contraseña temporal. Respaldo de la
            # base: los servicios la cuidan con ``asignar_invitacion`` y ``asignar_contrasena_temporal``.
            models.CheckConstraint(
                condition=Q(fecha_invitacion__isnull=True) | Q(fecha_contrasena_temporal__isnull=True),
                name="invitacion_o_temporal",
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
        # D-35: si tenía una invitación pendiente, deja de tenerla (nunca las dos a la vez).
        self.fecha_invitacion = None
        return temporal

    @property
    def tiene_invitacion_pendiente(self):
        """True si la cuenta tiene una invitación pendiente: la persona todavía no eligió su contraseña (SEG-20)."""
        return self.fecha_invitacion is not None

    def invitacion_vencida(self, ahora=None):
        """True si la invitación está pendiente y ya cumplió su vigencia de 7 días (SEG-20, D-35), el mismo plazo
        que la contraseña temporal: a los 7 días exactos ya está vencida. Sin invitación devuelve False."""
        if not self.tiene_invitacion_pendiente:
            return False
        ahora = ahora or timezone.now()
        return ahora >= self.fecha_invitacion + VIGENCIA_CONTRASENA_TEMPORAL

    def asignar_invitacion(self):
        """Deja la cuenta con una invitación pendiente (SEG-20, D-35): sin contraseña utilizable (la anterior deja
        de servir y las sesiones abiertas se cierran, porque cambia el resumen), con la fecha de la invitación y
        sin contraseña temporal. No la graba: la graba el servicio que la llama (alta, restablecimiento o
        reactivación), dentro de su transacción. El enlace lo arma y lo envía el servicio, después de confirmar."""
        self.set_unusable_password()
        self.fecha_invitacion = timezone.now()
        self.fecha_contrasena_temporal = None


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


# D-36: roles de las cuentas operativas (todas las del dominio menos el Gerente). El Gerente ve los registros de
# cuentas en los que actuó o fue afectada una de ellas (regla 1 de AUD-CNS-REG, MD-58). El rol de una cuenta no
# cambia (MD-55), así que el rol que se guarda en la auditoría sirve para filtrar.
ROLES_OPERATIVOS = tuple(rol for rol in Usuario.Rol.values if rol != Usuario.Rol.GERENTE)

MODELO_CUENTA = "core.usuario"


def texto_de(objeto):
    """Texto con el que la auditoría recuerda a ``objeto`` en el momento del cambio (D-36): de una cuenta,
    «Nombre Apellido (email)» o solo el email si no tiene nombre; de cualquier otro objeto, su ``str``."""
    if isinstance(objeto, Usuario):
        nombre = f"{objeto.first_name} {objeto.last_name}".strip()
        return f"{nombre} ({objeto.email})" if nombre else objeto.email
    return str(objeto)


def referencia(objeto):
    """Referencia a otro objeto dentro del detalle de la auditoría (D-36): ``{"id", "texto"}``. El texto es lo que
    se veía en ese momento, para que el registro siga mostrando lo que era aunque el objeto cambie después.
    Los servicios la usan para todo dato que apunte a una cuenta, un grupo y, más adelante, a un invernadero,
    un insumo, etc."""
    return {"id": objeto.pk, "texto": texto_de(objeto)}


def referencia_a_grupo(grupo_id):
    """Referencia a un grupo de cuentas vinculadas a partir de su id (D-36). Sirve aunque el grupo ya no exista:
    la desvinculación que lo disuelve y la salida del grupo auditan un grupo que acaba de borrarse."""
    return {"id": grupo_id, "texto": GrupoCuentas.texto_de(grupo_id)}


class RegistroAuditoriaQuerySet(models.QuerySet):
    """QuerySet que no permite modificar ni borrar en bloque (D-22) y que tiene el alcance de la consulta."""

    def update(self, **kwargs):
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se modifica (D-22).")

    def bulk_update(self, objs, fields, batch_size=None):
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se modifica (D-22).")

    def delete(self):
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se borra (D-22).")

    def visibles_para(self, actor):
        """Registros que ``actor`` puede consultar (regla 1 de AUD-CNS-REG). Es el único lugar del alcance.

        - Administrador activo: todos.
        - Gerente activo: los registros de los módulos de negocio (los de una acción que no está en
          ``ACCIONES_DE_CUENTAS``) y los de cuentas en los que actuó, o fue afectada, una cuenta de rol operativo
          (MD-58). No ve los que solo involucran a Administradores o a Gerentes (la cuenta del Gerente, la actual
          y las anteriores). Un registro es «de cuentas» por su acción, no por sus afectados: así una acción
          nueva de un módulo de negocio queda visible sin tocar esto, aunque solo afecte a la cuenta del Gerente.
        - Cualquier otro actor, o una cuenta inactiva: ninguno.

        Los afectados se buscan con ``contains`` sobre jsonb (``@>``), que usa el índice GIN de la tabla (D-36).
        """
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        rol = rol_de(actor)
        if rol == ADMINISTRADOR:
            return self.all()
        if rol != Usuario.Rol.GERENTE:
            return self.none()
        condicion = ~Q(accion__in=list(ACCIONES_DE_CUENTAS)) | Q(rol__in=ROLES_OPERATIVOS)
        for rol_operativo in ROLES_OPERATIVOS:
            condicion |= Q(afectados__contains=[{"modelo": MODELO_CUENTA, "rol": rol_operativo}])
        return self.filter(condicion)


class RegistroAuditoriaManager(models.Manager.from_queryset(RegistroAuditoriaQuerySet)):
    """Manager del registro de auditoría: la única vía de alta es ``registrar`` (D-22)."""

    # SEG-02 y SEG-14: ninguna contraseña queda en la auditoría. Se rechaza todo detalle cuya clave
    # nombre una contraseña, para que un descuido al escribir un servicio no la guarde.
    FRAGMENTOS_PROHIBIDOS = ("contrase", "password")

    def registrar(self, usuario, accion, afectados, detalle=None, *, rol_externo=None):
        """Agrega un registro de auditoría y lo devuelve (D-22).

        Se llama desde el servicio del caso de uso, dentro de su ``transaction.atomic()``, para que
        no quede una operación sin su registro ni un registro de una operación que se deshizo.

        - ``usuario``: la cuenta que actuó, o ``None`` si la acción la hace InfoPonia (el rol que
          se guarda es entonces ``ROL_INFOPONIA``). Se guarda el rol que tiene en este momento.
        - ``rol_externo`` (D-65 punto 8, D-88 punto 5): solo con ``usuario=None``, ``ROL_CLIENTE_ENLACE`` o
          ``ROL_PROVEEDOR_ENLACE``. El rol que se guarda es ese y no ``ROL_INFOPONIA``: la auditoría distingue lo que
          hace el Sistema de lo que hizo una persona sin cuenta que entró por un enlace. Quién fue (el cliente o el
          proveedor) y sobre qué va en ``afectados``.
        - ``accion``: un valor de ``RegistroAuditoria.Accion`` (lista cerrada de SEG-14).
        - ``afectados``: las cuentas u objetos afectados; cada uno, una instancia de modelo. Se guardan como
          ``{"modelo", "id", "texto"}`` y, las cuentas (siempre ``core.usuario``), también con su ``"rol"`` (D-36).
        - ``detalle``: en el formato obligatorio de D-36, con dos claves opcionales. ``"cambios"``:
          ``{campo: {"antes": valor, "despues": valor}}`` para todo dato que cambió (en un alta, ``antes`` es
          ``None``). ``"datos"``: ``{clave: valor}`` para el contexto que no tiene antes y después. Una referencia a
          otro objeto es ``referencia(objeto)``. Cualquier otra forma falla con ``ValueError``, igual que una
          contraseña (SEG-02, SEG-14).
        """
        if accion not in RegistroAuditoria.Accion.values:
            raise ValueError(f"Acción de auditoría desconocida: {accion!r} (lista cerrada, SEG-14).")
        if rol_externo is not None and (usuario is not None or rol_externo not in ROLES_EXTERNOS):
            raise ValueError(
                "rol_externo solo se usa sin cuenta (usuario=None) y es ROL_CLIENTE_ENLACE o ROL_PROVEEDOR_ENLACE "
                f"(D-65 punto 8, D-88 punto 5); llegó usuario={usuario!r} y rol_externo={rol_externo!r}."
            )
        detalle = {} if detalle is None else detalle
        self._rechazar_contrasenas(detalle)
        self._validar_formato(detalle)
        if usuario is not None:
            rol = rol_de(usuario)
        else:
            rol = rol_externo or ROL_INFOPONIA
        return self.create(
            usuario=usuario,
            rol=rol,
            accion=accion,
            afectados=[self._identificar(objeto) for objeto in afectados],
            detalle=detalle,
        )

    @staticmethod
    def _identificar(objeto):
        """Cómo se guarda un objeto afectado (D-36): ``{"modelo", "id", "texto"}`` y, si es una cuenta, también
        ``"rol"``. Una cuenta es siempre ``core.usuario``, sea cual sea su rol, para poder buscar todos los
        registros de una cuenta por su id; su rol es ``rol_de`` («administrador» para el Administrador)."""
        if isinstance(objeto, Usuario):
            return {
                "modelo": MODELO_CUENTA,
                "id": objeto.pk,
                "texto": texto_de(objeto),
                "rol": rol_de(objeto),
            }
        return {"modelo": type(objeto)._meta.label_lower, "id": objeto.pk, "texto": texto_de(objeto)}

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

    @classmethod
    def _validar_formato(cls, detalle):
        """D-36: el detalle solo tiene las claves ``cambios`` y ``datos``; cada cambio es exactamente
        ``{"antes", "despues"}`` y con valores distintos (lo que hace obligatorio el valor anterior); todo
        diccionario dentro de un valor es una referencia ``{"id", "texto"}``. Falla con ``ValueError``."""
        if not isinstance(detalle, dict):
            raise ValueError("El detalle de auditoría tiene que ser un diccionario (D-36).")
        sobrantes = set(detalle) - {"cambios", "datos"}
        if sobrantes:
            raise ValueError(
                "El detalle de auditoría solo admite las claves 'cambios' y 'datos' (D-36); "
                f"sobra {sorted(sobrantes)}."
            )
        cambios = detalle.get("cambios", {})
        if not isinstance(cambios, dict):
            raise ValueError("'cambios' tiene que ser un diccionario {campo: {antes, despues}} (D-36).")
        for campo, cambio in cambios.items():
            if not isinstance(cambio, dict) or set(cambio) != {"antes", "despues"}:
                raise ValueError(
                    f"El cambio de {campo!r} tiene que ser exactamente {{'antes': ..., 'despues': ...}} (D-36)."
                )
            antes, despues = cambio["antes"], cambio["despues"]
            if antes == despues and type(antes) is type(despues):
                raise ValueError(f"El cambio de {campo!r} no cambió nada: 'antes' es igual a 'despues' (D-36).")
            cls._validar_valor(antes, campo)
            cls._validar_valor(despues, campo)
        datos = detalle.get("datos", {})
        if not isinstance(datos, dict):
            raise ValueError("'datos' tiene que ser un diccionario {clave: valor} (D-36).")
        for clave, valor in datos.items():
            cls._validar_valor(valor, clave)

    @classmethod
    def _validar_valor(cls, valor, donde):
        """Un valor del detalle: nulo, booleano, número, texto, una referencia ``{"id", "texto"}`` o una lista
        de esos. Cualquier otro diccionario se rechaza: una referencia mal formada no se descubriría hasta
        mostrar el registro."""
        if valor is None or isinstance(valor, (bool, int, float, str)):
            return
        if isinstance(valor, (list, tuple)):
            for elemento in valor:
                cls._validar_valor(elemento, donde)
            return
        if isinstance(valor, dict):
            if set(valor) == {"id", "texto"} and isinstance(valor["texto"], str):
                return
            raise ValueError(f"Un diccionario en {donde!r} tiene que ser una referencia {{'id', 'texto'}} (D-36).")
        raise ValueError(f"El valor de {donde!r} no se puede guardar en la auditoría (D-36): {valor!r}.")


class RegistroAuditoria(models.Model):
    """Registro de auditoría: a esta tabla solo se agregan filas (D-22, SEG-14).

    Guarda quién actuó (``usuario``, nulo si fue InfoPonia) y con qué rol en ese momento, cuándo,
    qué acción, qué cuentas u objetos afectó y el detalle de los cambios. Nunca guarda contraseñas.
    Se escribe con ``RegistroAuditoria.objects.registrar(...)`` desde el servicio del caso de uso,
    dentro de la misma transacción. Una fila guardada no se modifica ni se borra.
    El detalle tiene un formato obligatorio (D-36): ``cambios`` con antes y después, y ``datos`` de contexto.
    """

    class Accion(models.TextChoices):
        """Lista cerrada de acciones auditadas (SEG-14). Cada acción nueva tiene que estar clasificada en
        ``ACCIONES_DE_CUENTAS`` o en ``ACCIONES_DE_NEGOCIO`` (D-36): de eso depende qué ve el Gerente."""

        ALTA = "alta", "Alta de cuenta"
        MODIFICACION = "modificacion", "Modificación de cuenta"
        BAJA = "baja", "Baja de cuenta"
        REACTIVACION = "reactivacion", "Reactivación de cuenta"
        RESTABLECIMIENTO = "restablecimiento", "Restablecimiento de cuenta"
        CAMBIO_CONTRASENA = "cambio_contrasena", "Cambio de contraseña"
        RECUPERACION_CONTRASENA = "recuperacion_contrasena", "Recuperación de contraseña"
        ACEPTACION_INVITACION = "aceptacion_invitacion", "Aceptación de invitación"
        VINCULACION = "vinculacion", "Vinculación de cuentas"
        DESVINCULACION = "desvinculacion", "Desvinculación de cuentas"
        # Invernadero (MAE-01, D-39 decisión 4): <acción>_<entidad>, para no chocar con las de cuentas.
        ALTA_INVERNADERO = "alta_invernadero", "Alta de invernadero"
        MODIFICACION_INVERNADERO = "modificacion_invernadero", "Modificación de invernadero"
        BAJA_INVERNADERO = "baja_invernadero", "Baja de invernadero"
        REACTIVACION_INVERNADERO = "reactivacion_invernadero", "Reactivación de invernadero"
        # Sector y cultivo (MAE-03, D-36): <acción>_<entidad>.
        ALTA_SECTOR = "alta_sector", "Alta de sector"
        MODIFICACION_SECTOR = "modificacion_sector", "Modificación de sector"
        BAJA_SECTOR = "baja_sector", "Baja de sector"
        REACTIVACION_SECTOR = "reactivacion_sector", "Reactivación de sector"
        ALTA_CULTIVO = "alta_cultivo", "Alta de cultivo"
        MODIFICACION_CULTIVO = "modificacion_cultivo", "Modificación de cultivo"
        BAJA_CULTIVO = "baja_cultivo", "Baja de cultivo"
        REACTIVACION_CULTIVO = "reactivacion_cultivo", "Reactivación de cultivo"
        # Configuración operativa y perfil de la organización (MAE-04, D-36): son registros únicos, solo se modifican.
        MODIFICACION_CONFIGURACION = "modificacion_configuracion", "Modificación de la configuración operativa"
        MODIFICACION_PERFIL = "modificacion_perfil", "Modificación del perfil de la organización"
        # Inventario (INV-01, D-36): categorías de insumos, insumos del catálogo y su baja en cada invernadero.
        ALTA_TIPO_INSUMO = "alta_tipo_insumo", "Alta de categoría de insumos"
        MODIFICACION_TIPO_INSUMO = "modificacion_tipo_insumo", "Modificación de categoría de insumos"
        BAJA_TIPO_INSUMO = "baja_tipo_insumo", "Baja de categoría de insumos"
        REACTIVACION_TIPO_INSUMO = "reactivacion_tipo_insumo", "Reactivación de categoría de insumos"
        ALTA_INSUMO = "alta_insumo", "Alta de insumo"
        MODIFICACION_INSUMO = "modificacion_insumo", "Modificación de insumo"
        BAJA_INSUMO = "baja_insumo", "Baja de insumo"
        REACTIVACION_INSUMO = "reactivacion_insumo", "Reactivación de insumo"
        BAJA_INSUMO_INVERNADERO = "baja_insumo_invernadero", "Baja de insumo en un invernadero"
        # Insumos en el invernadero, ajuste de stock y vencimientos (INV-02, D-36).
        HABILITACION_INSUMO_INVERNADERO = "habilitacion_insumo_invernadero", "Habilitación de insumo en un invernadero"
        MODIFICACION_INSUMO_INVERNADERO = "modificacion_insumo_invernadero", "Modificación de insumo en un invernadero"
        AJUSTE_STOCK = "ajuste_stock", "Ajuste de stock de insumo"
        ALERTA_DE_VENCIMIENTO = "alerta_de_vencimiento", "Alerta de vencimiento de insumo"
        # Variedades y su semilla (INV-03, D-36 y D-49): <acción>_<entidad>. El renombre de la semilla por su CULTIVO es aparte.
        ALTA_VARIEDAD = "alta_variedad", "Alta de variedad"
        MODIFICACION_VARIEDAD = "modificacion_variedad", "Modificación de variedad"
        BAJA_VARIEDAD = "baja_variedad", "Baja de variedad"
        REACTIVACION_VARIEDAD = "reactivacion_variedad", "Reactivación de variedad"
        MODIFICACION_SEMILLA = "modificacion_semilla", "Modificación de semilla"

        # Siembra y cancelación de órdenes (PRD-01, D-36). Las de transición, merma, aplicación, evento y fuera de servicio las
        # crean PRD-02 a PRD-04. El traspaso de órdenes al Capataz nuevo NO tiene acción propia: sus afectados van en
        # ``modificacion_invernadero`` (un registro por caso de uso).
        PLANIFICACION_SIEMBRA = "planificacion_siembra", "Planificación de siembra"
        CONCRECION_SIEMBRA = "concrecion_siembra", "Concreción de siembra"
        CANCELACION_ORDEN = "cancelacion_orden", "Cancelación de orden de trabajo"
        # Transición de etapa y merma (PRD-02, D-36): la merma de una transición va DENTRO de `concrecion_transicion`;
        # `registro_merma` como acción propia la usa PRD-03 (Registrar Merma).
        PLANIFICACION_TRANSICION = "planificacion_transicion", "Planificación de transición"
        CONCRECION_TRANSICION = "concrecion_transicion", "Concreción de transición"
        REGISTRO_MERMA = "registro_merma", "Registro de merma"
        # Aplicación de insumos y otro evento (PRD-03, D-51 punto 9): un registro por caso de uso.
        REGISTRO_APLICACION = "registro_aplicacion", "Registro de aplicación de insumos"
        REGISTRO_EVENTO = "registro_evento", "Registro de evento"
        # Sector fuera de servicio (PRD-04, D-51 punto 9): un solo registro por caso de uso, con todo lo tocado como afectado.
        FUERA_DE_SERVICIO_SECTOR = "fuera_de_servicio_sector", "Sector puesto fuera de servicio"
        # Tipos de actuador del IoT (IOT-01, D-36): <acción>_<entidad>. La reactivación se audita aparte de la modificación.
        ALTA_TIPO_ACTUADOR = "alta_tipo_actuador", "Alta de tipo de actuador"
        MODIFICACION_TIPO_ACTUADOR = "modificacion_tipo_actuador", "Modificación de tipo de actuador"
        REACTIVACION_TIPO_ACTUADOR = "reactivacion_tipo_actuador", "Reactivación de tipo de actuador"
        BAJA_TIPO_ACTUADOR = "baja_tipo_actuador", "Baja de tipo de actuador"
        # Sistema IoT y hardware (IOT-02, D-36). Nunca llevan el token ni su resumen (D-70). La baja y la desactivación son de IOT-06.
        ALTA_SISTEMA_IOT = "alta_sistema_iot", "Alta de sistema IoT"
        MODIFICACION_SISTEMA_IOT = "modificacion_sistema_iot", "Modificación de sistema IoT"
        REGENERACION_TOKEN_IOT = "regeneracion_token_iot", "Regeneración del token del nodo"
        ALTA_HARDWARE = "alta_hardware", "Alta de hardware"
        MODIFICACION_HARDWARE = "modificacion_hardware", "Modificación de hardware"
        REACTIVACION_HARDWARE = "reactivacion_hardware", "Reactivación de hardware"
        # Lo que el nodo central entrega por la API del IoT (IOT-03, postcondición z de IOT-ENT-INF): lecturas, estados, modo y anuncio. Actor ``None``
        # (InfoPonia, como los procesos de D-56). Nunca lleva el token (D-70).
        ENTREGA_INFORMACION_IOT = "entrega_informacion_iot", "Entrega de información del nodo (IoT)"
        # La revisión periódica del IoT (IOT-04, postcondición z de IOT-ENT-INF; D-71): un registro por sistema y por corrida, solo si generó o
        # resolvió alertas o borró lecturas. Actor ``None`` (InfoPonia).
        REVISION_PERIODICA_IOT = "revision_periodica_iot", "Revisión periódica del IoT"
        # Comandos del IoT (IOT-05, D-36): emitir y cancelar los hace una persona; resolver (retiro y resultado del nodo) lo hace InfoPonia por el nodo
        # central (actor ``None``, origen «nodo_central», postcondición q de IOT-RSV-CMD).
        EMISION_COMANDO = "emision_comando", "Emisión de comando"
        CANCELACION_COMANDO = "cancelacion_comando", "Cancelación de comando"
        RESOLUCION_COMANDO_IOT = "resolucion_comando_iot", "Resolución de comando (IoT)"
        # Clientes y vehículos (COM-01, D-36): <acción>_<entidad>. La reactivación se audita aparte de la modificación.
        ALTA_CLIENTE = "alta_cliente", "Alta de cliente"
        MODIFICACION_CLIENTE = "modificacion_cliente", "Modificación de cliente"
        BAJA_CLIENTE = "baja_cliente", "Baja de cliente"
        REACTIVACION_CLIENTE = "reactivacion_cliente", "Reactivación de cliente"
        ALTA_VEHICULO = "alta_vehiculo", "Alta de vehículo"
        MODIFICACION_VEHICULO = "modificacion_vehiculo", "Modificación de vehículo"
        BAJA_VEHICULO = "baja_vehiculo", "Baja de vehículo"
        REACTIVACION_VEHICULO = "reactivacion_vehiculo", "Reactivación de vehículo"
        # Compra-ventas (COM-02): un solo registro con la venta, sus detalles, reservas, líneas y cosechas (D-36).
        REGISTRO_COMPRA_VENTA = "registro_compra_venta", "Registro de compra-venta"
        # Suministros (COM-03a): un solo registro con el suministro, sus cláusulas, detalles, reservas, líneas y cosechas (D-36).
        PACTO_SUMINISTRO = "pacto_suministro", "Pacto de suministro"
        # Proveedores (CMP-01, D-87 punto 8): <acción>_<entidad>. La reactivación se audita aparte de la modificación.
        ALTA_PROVEEDOR = "alta_proveedor", "Alta de proveedor"
        MODIFICACION_PROVEEDOR = "modificacion_proveedor", "Modificación de proveedor"
        BAJA_PROVEEDOR = "baja_proveedor", "Baja de proveedor"
        REACTIVACION_PROVEEDOR = "reactivacion_proveedor", "Reactivación de proveedor"
        # Pedidos de cotización y cotizaciones (CMP-02a, D-87 punto 8): <acción>_<entidad>. La cotización la registra un proveedor
        # sin cuenta, con ``rol_externo`` (D-88 punto 5). Cancelar y reenviar son de CMP-02b.
        ALTA_PEDIDO = "alta_pedido", "Alta de pedido de cotización"
        ALTA_COTIZACION = "alta_cotizacion", "Alta de cotización"

    # D-36: nombre visible de cada campo de «cambios» y de cada clave de «datos». El orden de este diccionario
    # es el orden en que se muestran las filas (jsonb no conserva el orden de las claves); lo que no figura va
    # al final, con su clave tal cual.
    ETIQUETAS = {
        "acceso": "Forma de acceso",
        "era_temporal": "La contraseña era temporal",
        "invitacion_pendiente": "Tenía una invitación pendiente",
        "rol": "Rol",
        "nombre": "Nombre",
        "apellido": "Apellido",
        "email": "Email",
        "estado": "Estado",
        "telefono": "Teléfono",
        "grupo": "Grupo de cuentas vinculadas",
        "grupo_unido": "Grupo que se unió",
        "disuelto": "El grupo se disolvió",
        # Invernadero (MAE-01, D-39): el orden es el de la pantalla. «nombre» y «estado» ya existen.
        "tipo_direccion": "Tipo de dirección",
        "localidad": "Localidad",
        "calle": "Calle",
        "numero_calle": "Número",
        "piso": "Piso",
        "departamento_unidad": "Departamento (unidad)",
        "barrio": "Barrio",
        "referencias": "Referencias",
        "ruta": "Ruta o camino",
        "kilometro": "Kilómetro",
        "lote_rural": "Lote",
        "agronomo": "Agrónomo",
        "capataz": "Capataz",
        "vendedor": "Vendedor",
        "tecnico": "Técnico",
        # Alertas (MAE-02a, D-41): listas de referencias en los datos del caso de uso que las crea, resuelve o traspasa.
        "alertas_creadas": "Alertas creadas",
        "alertas_resueltas": "Alertas resueltas",
        "alertas_traspasadas": "Alertas traspasadas",
        # Sectores y cultivos (MAE-03): «nombre» y «estado» ya existen.
        "tipo_etapa": "Tipo de etapa",
        "cant_agujeros_total": "Agujeros totales",
        "invernadero": "Invernadero",
        "semillas_renombradas": "Semillas renombradas",
        # Inventario (INV-01): el orden es el de la pantalla. «nombre» y «estado» ya existen; «categoria» es una referencia.
        "descripcion": "Descripción",
        "categoria": "Categoría",
        "unidad_medida": "Unidad de medida",
        "controla_vencimiento": "Controla vencimiento",
        "consumo_directo": "Consumo directo",
        # Insumos en el invernadero y ajuste de stock (INV-02): cantidades y precios van como texto (D-36).
        "insumo": "Insumo",
        "cant_min_insumo": "Stock mínimo",
        "referencia_precio": "Precio de referencia",
        "stock": "Stock",
        "motivo_ajuste": "Motivo del ajuste",
        "descripcion_ajuste": "Descripción del ajuste",
        "lotes": "Lotes modificados",
        "lotes_nuevos": "Lotes nuevos",
        "movimientos": "Movimientos creados",
        # Variedades y su semilla (INV-03): rangos y duraciones van como texto (D-36); «etapas» es una lista de textos
        # («Germinación: 5 días»); «cultivo» y «nombre_semilla» son contexto. «nombre» y «estado» ya existen.
        "cultivo": "Cultivo",
        "perfil_familia": "Perfil familiar",
        "etapas": "Etapas",
        "temp_ambiente_min": "Temperatura ambiente mínima (°C)",
        "temp_ambiente_max": "Temperatura ambiente máxima (°C)",
        "humedad_min": "Humedad mínima (%)",
        "humedad_max": "Humedad máxima (%)",
        "intensidad_luz_min": "Intensidad lumínica mínima (µmol)",
        "intensidad_luz_max": "Intensidad lumínica máxima (µmol)",
        "fotoperiodo_min": "Fotoperíodo mínimo (h/día)",
        "fotoperiodo_max": "Fotoperíodo máximo (h/día)",
        "duracion_post_cosecha": "Duración postcosecha (días)",
        "peso_promedio_planta": "Peso promedio por planta (g)",
        "nombre_semilla": "Nombre de la semilla",
        # Órdenes de siembra y su cancelación (PRD-01, D-36 y D-50 punto 4): cantidades y fechas van como texto. «Agujeros
        # comprometidos» y «agujeros ocupados» son los cambios de cada sector (antes → después, como texto). «invernadero»,
        # «capataz», «estado», «lotes», «movimientos» y «alertas_resueltas» ya existen.
        "variedad": "Variedad",
        "cant_plantines_siembra": "Plantines planificados",
        "cantidad_sembrada": "Plantines sembrados",
        "fecha_programada_orden": "Fecha programada",
        "fecha_siembra": "Fecha de siembra",
        "prioridad_orden": "Prioridad",
        "descripcion_orden": "Descripción de la orden",
        "motivo_cancelacion": "Motivo de la cancelación",
        "motivo_diferencia_siembra": "Motivo de la diferencia",
        "agujeros_comprometidos": "Agujeros comprometidos",
        "agujeros_ocupados": "Agujeros ocupados",
        "orden": "Orden",
        "lote": "Lote",
        "ocupaciones": "Ocupaciones",
        "reservas": "Reservas",
        "sectores": "Sectores",
        "insumos_invernadero": "Insumos del invernadero",
        "lotes_de_insumo": "Lotes de insumo",
        "consumos": "Consumos",
        "bitacoras": "Registros de bitácora",
        # Transición de etapa y merma (PRD-02): fechas y cantidades van como texto. «lote», «orden», «ocupaciones», «sectores»,
        # «bitacoras», «agujeros_comprometidos», «agujeros_ocupados» y «alertas_creadas» ya existen.
        "etapa": "Etapa",
        "etapa_destino": "Etapa destino",
        "cantidad_actual": "Plantas del lote",
        "cantidad_transferida": "Plantas trasladadas",
        "fecha_resolucion_orden": "Fecha de resolución",
        "fecha_transicion": "Fecha efectiva de la transición",
        "costo_acumulado": "Costo acumulado del lote",
        "merma": "Merma",
        "cantidad_merma": "Plantas perdidas",
        "causa_merma": "Causa de la merma",
        # Aplicación de insumos y otro evento (PRD-03): montos y cantidades van como texto. «invernadero», «sectores», «consumos»,
        # «bitacoras», «lotes_de_insumo», «lote», «costo_acumulado», «alertas_creadas» y «movimientos» ya existen.
        "aplicacion": "Aplicación de insumos",
        "evento": "Evento",
        "alcance": "Alcance",
        "imputaciones": "Imputaciones de costo",
        "descripcion_evento": "Descripción",
        "monto_consumo": "Valor del consumo",
        "cantidad_consumida": "Cantidad usada",
        "faltante_sin_lote": "Faltante sin lote",
        # Tipos de actuador (IOT-01): listas de referencias a sus acciones en los datos del caso de uso («nombre» y «estado» ya existen).
        "tiempo_minimo_entre_comandos": "Tiempo mínimo entre comandos (s)",
        # Sistema IoT (IOT-02): el nodo central y el rango de la solución. «invernadero» ya existe.
        "nodo": "Nodo central",
        "nombre_nodo": "Nombre del nodo",
        "numero_serie": "Número de serie",
        "temp_solucion_min": "Temperatura mínima de la solución (°C)",
        "temp_solucion_max": "Temperatura máxima de la solución (°C)",
        "rango_de_la_solucion": "Rango de temperatura de la solución",
        # Hardware (IOT-02): sensores y actuadores. «estado», «insumo» y «invernadero» ya existen.
        "clase": "Tipo de equipo",
        "identificador_equipo": "Identificador del equipo",
        "tipo_variable_sensor": "Variable que mide",
        "nombre_sensor": "Nombre del sensor",
        "tipo_actuador": "Tipo de actuador",
        "descripcion_actuador": "Descripción del actuador",
        "modelo_hardware": "Modelo",
        "fecha_instalacion": "Fecha de instalación",
        "sector": "Sector",
        "valor_calibracion_min": "Calibración mínima",
        "valor_calibracion_max": "Calibración máxima",
        "desde": "Estaba",
        "acciones_creadas": "Acciones creadas",
        "acciones_modificadas": "Acciones modificadas",
        "acciones_desactivadas": "Acciones desactivadas",
        "acciones_borradas": "Acciones borradas",
        # Lo que entrega el nodo (IOT-03) y la revisión periódica (IOT-04): «sistema» es una referencia; «ahora», la hora usada (texto ISO).
        "origen": "Origen",
        "sistema": "Sistema IoT",
        "mensaje": "Mensaje del nodo",
        "identificador": "Identificador",
        "ahora": "Hora de la revisión",
        "alertas_generadas": "Alertas generadas",
        "lecturas_borradas": "Lecturas borradas",
        # Configuración operativa (MAE-04): el orden es el de la pantalla.
        "porc_merma_maxima": "Merma máxima tolerada por lote (%)",
        "dias_horizonte_cosecha": "Horizonte de planificación de cosecha (días)",
        "dias_aviso_vencimiento": "Aviso de vencimiento de insumos (días antes)",
        "dias_pre_reserva_suministro": "Pre-reserva de suministros (días)",
        "dias_anticipacion_cosecha_compra_venta": "Anticipación de cosecha: compra-venta (días)",
        "dias_anticipacion_cosecha_suministro": "Anticipación de cosecha: suministro (días)",
        "dias_vigencia_enlace_confirmacion": "Vigencia del enlace de confirmación (días)",
        "dias_vigencia_enlace_faltante": "Vigencia del enlace de decisión ante un faltante (días)",
        "dias_limite_cotizacion": "Días límite para cotizar",
        "dias_validez_cotizacion": "Validez de las cotizaciones (días)",
        "porc_tolerancia_cobertura_pedido": "Tolerancia de cobertura del pedido (%)",
        "cant_maxima_entregas_diarias": "Máximo de entregas diarias por transportista",
        "cant_max_ciudades_distintas_diarias": "Máximo de localidades distintas por día",
        # Módulo IoT de la configuración operativa (IOT-04; docs/casos_de_uso/maestros/configuracion.md, sección «Módulo IoT»).
        "cant_reintentos_comando": "Reintentos de un comando",
        "segundos_intervalo_reintento": "Intervalo entre intentos (s)",
        "hora_inicio_luz": "Horario de luz: inicio (h)",
        "hora_fin_luz": "Horario de luz: fin (h)",
        "lux_umbral_fotoperiodo": "Umbral de luz para el fotoperíodo (lux)",
        "minutos_sin_actividad": "Minutos sin actividad",
        "minutos_sin_comunicacion": "Minutos sin comunicación",
        "minutos_antiguedad_lectura": "Antigüedad máxima de una lectura (min)",
        "cant_lecturas_confirmacion": "Lecturas de confirmación",
        "histeresis_temperatura": "Histéresis de temperatura (°C)",
        "histeresis_humedad": "Histéresis de humedad (% HR)",
        "histeresis_luz": "Histéresis de intensidad lumínica (lux)",
        "histeresis_temp_solucion": "Histéresis de temperatura de la solución (°C)",
        "dias_retencion_telemetria": "Días de retención de lecturas",
        # Perfil de la organización (MAE-04).
        "nombre_organizacion": "Nombre de la organización",
        "cuit_organizacion": "CUIT",
        "telefono_organizacion": "Teléfono de la organización",
        "email_organizacion": "Email de la organización",
        "direccion_organizacion": "Dirección de la organización",
        "color_primario": "Color 1 (principal)",
        "color_secundario": "Color 2",
        "color_terciario": "Color 3",
        "color_cuaternario": "Color 4",
        # Clientes y vehículos (COM-01): «nombre», «apellido», «telefono», «email», «estado» y «localidad» ya existen.
        "tipo_cliente": "Tipo de cliente",
        "cuit": "CUIT",
        "razon_social": "Razón social",
        "direcciones_creadas": "Direcciones creadas",
        "direcciones_corregidas": "Direcciones corregidas",
        "direcciones_reemplazadas": "Direcciones reemplazadas",
        "direcciones_desactivadas": "Direcciones desactivadas",
        "direcciones_borradas": "Direcciones borradas",
        "patente": "Patente",
        "tipo_vehiculo": "Tipo de vehículo",
        "marca": "Marca",
        "modelo": "Modelo",
        "capacidad_carga": "Capacidad de carga (kg)",
        "transportista": "Transportista",
        # Compra-ventas (COM-02): las claves de `datos` del registro («vendedor» ya existe).
        "compra_venta": "Compra-venta",
        "cliente": "Cliente",
        "fecha_realizacion": "Fecha de realización",
        "fecha_pactada_venta": "Fecha pactada",
        "modalidad_entrega": "Modalidad de entrega",
        "direccion_envio": "Dirección de envío",
        "invernadero_retiro": "Invernadero de retiro",
        "estado_venta": "Estado de la venta",
        "monto_estimado": "Monto estimado",
        "detalles": "Detalles",
        "reservas": "Reservas",
        "lineas": "Líneas de reserva",
        "cosechas": "Cosechas",
        # Suministros (COM-03a): las claves de `datos` del registro «pacto_suministro» (las demás ya existen).
        "suministro": "Suministro",
        "duracion_meses": "Duración (meses)",
        "fecha_fin": "Fecha de fin",
        "estado_suministro": "Estado del suministro",
        "incumplimientos_tolerados": "Incumplimientos tolerados",
        "multa_resolucion": "Multa por resolución",
        "clausula_suministrado": "Cláusula del suministrado",
        "periodos_reservados": "Períodos reservados",
        # Proveedores (CMP-01): «nombre», «apellido», «email», «telefono» y «estado» ya existen y conservan su lugar; las nuevas van al final.
        # Diferencia con «Límites» de la tarea (que decía solo las acciones): docs/patrones/auditoria.md pide sumarlas; aprobado por el estudiante.
        "tipo_proveedor": "Tipo de proveedor",
        "especialidades": "Categorías de insumos",
        # Comandos del IoT (IOT-05): lo que audita emitir, cancelar y resolver un comando. «mensaje» e «identificador» ya existen.
        "actuador": "Actuador",
        "accion": "Acción",
        "valor": "Valor",
        "estado_comando": "Estado del comando",
        "resultado_comando": "Resultado del comando",
        "estado_informado": "Estado informado por el nodo",
        "estado_hardware": "Estado del equipo",
        "compatibilidad": "Compatibilidad con el nodo",
        "hechos": "Qué pasó con los comandos",
        # Pedidos y cotizaciones (CMP-02a): cantidades, importes y fechas van como texto (D-36). «estado», «invernadero»,
        # «insumo» y «agronomo» ya existen, y también «monto_estimado», «detalles» y «lineas» (los de la compra-venta de COM-02): no se repiten, porque en
        # un diccionario la clave de más abajo pisa a la de arriba y cambiaría el texto de aquellas pantallas. Las líneas de la cotización llevan su clave propia.
        "pedido": "Pedido",
        "proveedor": "Proveedor",
        "fecha_pedido": "Fecha del pedido",
        "fecha_limite_cotizaciones": "Fecha límite de cotizaciones",
        "invitaciones": "Proveedores invitados",
        "cotizacion": "Cotización",
        "fecha_validez_cotizacion": "Válida hasta",
        "observaciones_cotizacion": "Observaciones del proveedor",
        "monto_cotizacion": "Monto de la cotización",
        "lineas_cotizadas": "Líneas de la cotización",
        "pedido_cubierto": "El pedido quedó cubierto",
    }
    # D-36: nombre visible de los valores con lista cerrada, por campo. Lo que no figura se muestra tal cual.
    VALORES_VISIBLES = {
        # D-65 punto 8 y D-88 punto 5: los roles externos (sin cuenta) se muestran con su origen.
        "rol": {
            **dict(Usuario.Rol.choices),
            ADMINISTRADOR: "Administrador",
            ROL_CLIENTE_ENLACE: "Cliente (mediante enlace)",
            ROL_PROVEEDOR_ENLACE: "Proveedor (mediante enlace)",
        },
        # MAE-03: «fuera de servicio» es un estado de los sectores (permiso explícito del estudiante, 20/11/2026).
        "estado": {
            "activo": "Activo",
            "inactivo": "Inactivo",
            "fuera_de_servicio": "Fuera de servicio",
            # CMP-02a: estados del pedido de cotización (`core` no importa `compras`, A1 de D-37).
            "en_cotizacion": "En cotización",
            "cerrado": "Cerrado",
            "cancelado": "Cancelado",
        },
        "acceso": {"invitacion": "Invitación por correo", "temporal": "Contraseña temporal"},
        # IOT-02: de qué estado vuelve a activarse un equipo (``reactivacion_hardware``).
        "desde": {"fuera_de_servicio": "Fuera de servicio", "inactivo": "Dado de baja"},
        "clase": {"sensor": "Sensor", "actuador": "Actuador"},
        # CMP-01: `core` no importa `compras` (A1 de D-37), así que la lista cerrada se repite acá.
        "tipo_proveedor": {"juridica": "Persona jurídica", "fisica": "Persona física"},
        "tipo_direccion": {"urbana": "Urbana", "rural": "Rural"},
        # PRD-01: la prioridad de la orden (opcional; sin valor cuenta como media).
        "prioridad_orden": {"alta": "Alta", "media": "Media", "baja": "Baja"},
        # INV-01: `core` no importa `inventario` (A1 de D-37), así que las listas cerradas se repiten acá.
        "consumo_directo": {
            "no_admite": "No admite",
            "como_gasto": "Como gasto",
            "como_costo_de_los_lotes": "Como costo de los lotes",
        },
        # INV-03: los seis perfiles familiares (`core` no importa `maestros`, A1 de D-37).
        "perfil_familia": {
            "hoja_verde": "Hoja verde",
            "pastura": "Pastura",
            "frutos_grandes": "Frutos grandes",
            "frutos_pequenos": "Frutos pequeños",
            "flores": "Flores",
            "hierbas": "Hierbas",
        },
        "motivo_ajuste": {
            "recuento_fisico": "Recuento físico",
            "rotura_o_perdida": "Rotura o pérdida",
            "carga_inicial": "Carga inicial",
            "vencimiento": "Vencimiento",
            "correccion_entre_lotes": "Corrección entre lotes",
            "otro": "Otro",
        },
        "unidad_medida": {
            "unidad": "unidad",
            "kg": "kg",
            "g": "g",
            "l": "L",
            "ml": "mL",
            "m3": "m³",
            "m": "m",
            "m2": "m²",
        },
        # COM-01: las listas cerradas de cliente y vehículo (`core` no importa `comercial`, A1 de D-37).
        "tipo_cliente": {"juridica": "Persona jurídica", "fisica": "Persona física"},
        "tipo_vehiculo": {
            "camioneta": "Camioneta",
            "furgon": "Furgón",
            "camion": "Camión",
            "utilitario": "Utilitario",
            "moto": "Moto",
        },
        # COM-02: las listas cerradas de la compra-venta y de la reserva (`core` no importa `comercial`).
        "modalidad_entrega": {"retiro": "Retiro en invernadero", "envio": "Envío a domicilio"},
        "estado_venta": {
            "abierta": "Abierta",
            "pendiente_decision": "Pendiente de decisión del cliente",
            "concretada": "Concretada",
            "cancelada": "Cancelada",
        },
        # COM-03a: las listas cerradas del suministro y de su detalle (`core` no importa `comercial`).
        "estado_suministro": {"vigente": "Vigente", "finalizado": "Finalizado", "resuelto": "Resuelto", "rescindido": "Rescindido"},
        "mecanismo_precio": {"fijo": "Fijo", "ajuste_periodico": "Ajuste periódico"},
        "estado_detalle_suministro": {"vigente": "Vigente", "finalizado": "Finalizado", "resuelto": "Resuelto"},
        "estado_reserva": {
            "activa": "Activa",
            "lista_para_entrega": "Lista para entrega",
            "entregada": "Entregada",
            "liberada": "Liberada",
        },
    }
    SIN_VALOR = "—"

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
    # D-39: 50 caracteres (eran 30) para que ningún nombre «<acción>_<entidad>» futuro quede corto.
    accion = models.CharField("acción", max_length=50, choices=Accion.choices)
    afectados = models.JSONField(
        "cuentas u objetos afectados",
        default=list,
        help_text='Lista de {"modelo": "core.usuario", "id": 7, "texto": "...", "rol": "capataz"}.',
    )
    detalle = models.JSONField("detalle de los cambios", default=dict)

    objects = RegistroAuditoriaManager()

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-fecha_hora", "-id"]
        # D-36: la tabla solo crece. El GIN con ``jsonb_path_ops`` sirve a ``@>`` (``afectados__contains``), que usan el
        # alcance del Gerente y el filtro por cuenta afectada, y es más chico y rápido que el ``jsonb_ops`` por
        # defecto; alcanza porque no se usa otro operador. El btree sirve al orden de cada página (del más reciente
        # al más viejo) y al rango de fechas. El filtro por la cuenta que actuó ya tiene el índice de su clave foránea.
        indexes = [
            GinIndex(fields=["afectados"], opclasses=["jsonb_path_ops"], name="auditoria_afectados_gin"),
            models.Index(fields=["-fecha_hora", "-id"], name="auditoria_fecha_idx"),
        ]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} · {self.rol} · {self.get_accion_display()}"

    @classmethod
    def _en_orden(cls, claves):
        """``claves`` en el orden de ``ETIQUETAS``; las que no figuran, al final y en su orden."""
        conocidas = list(cls.ETIQUETAS)
        return sorted(claves, key=lambda c: conocidas.index(c) if c in conocidas else len(conocidas))

    @classmethod
    def _valor_visible(cls, campo, valor):
        """Un valor del detalle como texto: nulo como «—», un booleano como «Sí» o «No», una referencia con
        su texto guardado, una lista con sus elementos separados por comas y los valores con lista cerrada con su
        nombre visible."""
        if valor is None:
            return cls.SIN_VALOR
        if isinstance(valor, bool):
            return "Sí" if valor else "No"
        if isinstance(valor, dict):
            return valor["texto"]
        if isinstance(valor, (list, tuple)):
            return ", ".join(cls._valor_visible(campo, elemento) for elemento in valor)
        return cls.VALORES_VISIBLES.get(campo, {}).get(valor, str(valor))

    def rol_visible(self):
        """Nombre visible del rol que tenía quien actuó en ese momento («Capataz», «Administrador»)."""
        return self.VALORES_VISIBLES["rol"].get(self.rol, self.rol)

    def es_de_actor_externo(self):
        """True si lo hizo una persona sin cuenta que entró por un enlace (D-65 punto 8, D-88 punto 5): la pantalla muestra
        «Proveedor (mediante enlace)» y no «InfoPonia»."""
        return self.usuario_id is None and self.rol in ROLES_EXTERNOS

    def afectados_visibles(self):
        """Los afectados como ``(texto, rol visible o None)``, con el texto que tenían en el momento del cambio
        (regla 3 de AUD-CNS-REG). El rol solo lo tienen las cuentas."""
        return [
            (
                afectado.get("texto") or f"{afectado['modelo']} {afectado['id']}",
                self.VALORES_VISIBLES["rol"].get(afectado["rol"], afectado["rol"]) if afectado.get("rol") else None,
            )
            for afectado in self.afectados
        ]

    def filas_de_cambios(self):
        """Los cambios del detalle como filas ``(campo, antes, despues)`` en texto, para la tabla Campo / Antes /
        Después (regla 3 de AUD-CNS-REG)."""
        cambios = self.detalle.get("cambios", {})
        return [
            (
                self.ETIQUETAS.get(campo, campo),
                self._valor_visible(campo, cambios[campo]["antes"]),
                self._valor_visible(campo, cambios[campo]["despues"]),
            )
            for campo in self._en_orden(cambios)
        ]

    def filas_de_datos(self):
        """Los datos de contexto del detalle como filas ``(dato, valor)`` en texto."""
        datos = self.detalle.get("datos", {})
        return [
            (self.ETIQUETAS.get(clave, clave), self._valor_visible(clave, datos[clave]))
            for clave in self._en_orden(datos)
        ]

    def save(self, *args, **kwargs):
        """Solo permite agregar: guardar una fila que ya existe falla (D-22)."""
        if not self._state.adding:
            raise RegistroAuditoriaInmutableError("El registro de auditoría no se modifica (D-22).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Un registro de auditoría no se borra (D-22)."""
        raise RegistroAuditoriaInmutableError("El registro de auditoría no se borra (D-22).")


# D-36: cada acción de ``RegistroAuditoria.Accion`` se clasifica en uno de estos dos conjuntos, y en uno solo (lo
# exige una prueba). ``visibles_para`` decide por ``ACCIONES_DE_CUENTAS``: lo que no está ahí es de un módulo de
# negocio y el Gerente lo ve sin importar a quién afecte. Agregar una acción obliga a clasificarla.
ACCIONES_DE_CUENTAS = frozenset(
    {
        RegistroAuditoria.Accion.ALTA,
        RegistroAuditoria.Accion.MODIFICACION,
        RegistroAuditoria.Accion.BAJA,
        RegistroAuditoria.Accion.REACTIVACION,
        RegistroAuditoria.Accion.RESTABLECIMIENTO,
        RegistroAuditoria.Accion.CAMBIO_CONTRASENA,
        RegistroAuditoria.Accion.RECUPERACION_CONTRASENA,
        RegistroAuditoria.Accion.ACEPTACION_INVITACION,
        RegistroAuditoria.Accion.VINCULACION,
        RegistroAuditoria.Accion.DESVINCULACION,
    }
)
# Las acciones de los módulos de negocio se agregan acá cuando existen (MAE-01: invernadero).
ACCIONES_DE_NEGOCIO = frozenset(
    {
        RegistroAuditoria.Accion.ALTA_INVERNADERO,
        RegistroAuditoria.Accion.MODIFICACION_INVERNADERO,
        RegistroAuditoria.Accion.BAJA_INVERNADERO,
        RegistroAuditoria.Accion.REACTIVACION_INVERNADERO,
        RegistroAuditoria.Accion.ALTA_SECTOR,
        RegistroAuditoria.Accion.MODIFICACION_SECTOR,
        RegistroAuditoria.Accion.BAJA_SECTOR,
        RegistroAuditoria.Accion.REACTIVACION_SECTOR,
        RegistroAuditoria.Accion.ALTA_CULTIVO,
        RegistroAuditoria.Accion.MODIFICACION_CULTIVO,
        RegistroAuditoria.Accion.BAJA_CULTIVO,
        RegistroAuditoria.Accion.REACTIVACION_CULTIVO,
        RegistroAuditoria.Accion.MODIFICACION_CONFIGURACION,
        RegistroAuditoria.Accion.MODIFICACION_PERFIL,
        RegistroAuditoria.Accion.ALTA_TIPO_INSUMO,
        RegistroAuditoria.Accion.MODIFICACION_TIPO_INSUMO,
        RegistroAuditoria.Accion.BAJA_TIPO_INSUMO,
        RegistroAuditoria.Accion.REACTIVACION_TIPO_INSUMO,
        RegistroAuditoria.Accion.ALTA_INSUMO,
        RegistroAuditoria.Accion.MODIFICACION_INSUMO,
        RegistroAuditoria.Accion.BAJA_INSUMO,
        RegistroAuditoria.Accion.REACTIVACION_INSUMO,
        RegistroAuditoria.Accion.BAJA_INSUMO_INVERNADERO,
        RegistroAuditoria.Accion.HABILITACION_INSUMO_INVERNADERO,
        RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO,
        RegistroAuditoria.Accion.AJUSTE_STOCK,
        RegistroAuditoria.Accion.ALTA_VARIEDAD,
        RegistroAuditoria.Accion.MODIFICACION_VARIEDAD,
        RegistroAuditoria.Accion.BAJA_VARIEDAD,
        RegistroAuditoria.Accion.REACTIVACION_VARIEDAD,
        RegistroAuditoria.Accion.MODIFICACION_SEMILLA,
        RegistroAuditoria.Accion.ALERTA_DE_VENCIMIENTO,
        RegistroAuditoria.Accion.PLANIFICACION_SIEMBRA,
        RegistroAuditoria.Accion.CONCRECION_SIEMBRA,
        RegistroAuditoria.Accion.CANCELACION_ORDEN,
        RegistroAuditoria.Accion.PLANIFICACION_TRANSICION,
        RegistroAuditoria.Accion.CONCRECION_TRANSICION,
        RegistroAuditoria.Accion.REGISTRO_MERMA,
        RegistroAuditoria.Accion.REGISTRO_APLICACION,
        RegistroAuditoria.Accion.REGISTRO_EVENTO,
        RegistroAuditoria.Accion.FUERA_DE_SERVICIO_SECTOR,
        RegistroAuditoria.Accion.ALTA_TIPO_ACTUADOR,
        RegistroAuditoria.Accion.MODIFICACION_TIPO_ACTUADOR,
        RegistroAuditoria.Accion.REACTIVACION_TIPO_ACTUADOR,
        RegistroAuditoria.Accion.BAJA_TIPO_ACTUADOR,
        RegistroAuditoria.Accion.ALTA_SISTEMA_IOT,
        RegistroAuditoria.Accion.MODIFICACION_SISTEMA_IOT,
        RegistroAuditoria.Accion.REGENERACION_TOKEN_IOT,
        RegistroAuditoria.Accion.ALTA_HARDWARE,
        RegistroAuditoria.Accion.MODIFICACION_HARDWARE,
        RegistroAuditoria.Accion.REACTIVACION_HARDWARE,
        RegistroAuditoria.Accion.ENTREGA_INFORMACION_IOT,
        RegistroAuditoria.Accion.REVISION_PERIODICA_IOT,
        RegistroAuditoria.Accion.EMISION_COMANDO,
        RegistroAuditoria.Accion.CANCELACION_COMANDO,
        RegistroAuditoria.Accion.RESOLUCION_COMANDO_IOT,
        RegistroAuditoria.Accion.ALTA_CLIENTE,
        RegistroAuditoria.Accion.MODIFICACION_CLIENTE,
        RegistroAuditoria.Accion.BAJA_CLIENTE,
        RegistroAuditoria.Accion.REACTIVACION_CLIENTE,
        RegistroAuditoria.Accion.ALTA_VEHICULO,
        RegistroAuditoria.Accion.MODIFICACION_VEHICULO,
        RegistroAuditoria.Accion.BAJA_VEHICULO,
        RegistroAuditoria.Accion.REACTIVACION_VEHICULO,
        RegistroAuditoria.Accion.REGISTRO_COMPRA_VENTA,
        RegistroAuditoria.Accion.PACTO_SUMINISTRO,
        RegistroAuditoria.Accion.ALTA_PROVEEDOR,
        RegistroAuditoria.Accion.MODIFICACION_PROVEEDOR,
        RegistroAuditoria.Accion.BAJA_PROVEEDOR,
        RegistroAuditoria.Accion.REACTIVACION_PROVEEDOR,
        RegistroAuditoria.Accion.ALTA_PEDIDO,
        RegistroAuditoria.Accion.ALTA_COTIZACION,
    }
)


class Notificacion(models.Model):
    """Aviso de texto para una cuenta, dentro del Sistema (D-42; API en docs/api/notificaciones.md).

    No es un concepto del negocio (D-38): no tiene estado, severidad, origen ni enlace a otras filas. Se crea con las
    funciones de ``core.notificaciones``, dentro de la transacción del caso de uso que la dispara. No se borra nunca (la
    cuenta tampoco, ``PROTECT``) y no se audita (D-42): es el efecto de una acción que ya se audita (D-36).
    """

    destinatario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="notificaciones")
    titulo = models.CharField("título", max_length=120)
    detalle = models.CharField(max_length=500)
    fecha_hora = models.DateTimeField("fecha y hora", default=timezone.now, editable=False)
    leida = models.BooleanField("leída", default=False)

    class Meta:
        # D-42: de la más reciente a la más antigua; ``-id`` desempata las creadas en el mismo instante.
        ordering = ["-fecha_hora", "-id"]
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        indexes = [models.Index(fields=["destinatario", "fecha_hora"], name="notif_dest_fecha")]

    def __str__(self):
        """El título: es lo que se ve de la notificación en el panel de la campana."""
        return self.titulo
