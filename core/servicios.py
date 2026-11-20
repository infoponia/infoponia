# Servicios de core: un caso de uso por función, dentro de transaction.atomic(). Hoy: el cambio de
# contraseña (USR-CMB-CTR), lo que necesita Mi perfil (USR-GST-PRF), la gestión de cuentas del Gerente y
# del Administrador (USR-CNS-USR, USR-ALT-USR, USR-MOD-USR y USR-BAJ-USR), con los invariantes de SEG-15, y
# las cuentas vinculadas (USR-VNC-CTA y SEG-09), la recuperación de contraseña por correo (USR-RCP-CTR y SEG-12) y la
# invitación por correo como forma de primer acceso (SEG-20, D-35) y la consulta del registro de auditoría
# (AUD-CNS-REG, D-36).
# Las vistas solo validan la entrada y llaman acá.

import logging
from collections import namedtuple
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core import extensiones, notificaciones
from core.identidad import nombre_de_la_organizacion
from core.models import (
    ADMINISTRADOR,
    MODELO_CUENTA,
    Agronomo,
    Capataz,
    Gerente,
    GrupoCuentas,
    RegistroAuditoria,
    Tecnico,
    Transportista,
    Usuario,
    Vendedor,
    referencia_a_grupo,
    rol_de,
)
from core.tokens import generador_invitacion
from core.validadores import validar_telefono

logger = logging.getLogger(__name__)

MENSAJE_EMAIL_REPETIDO = "Ya existe una cuenta con ese email."
MENSAJE_FUERA_DE_ALCANCE = "Esa cuenta no está dentro de las que gestionás."
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a la gestión de usuarios."
# Consultar el registro de auditoría (AUD-CNS-REG, D-36).
MENSAJE_SIN_ACCESO_A_AUDITORIA = "Tu cuenta no tiene acceso a la auditoría."
MENSAJE_REGISTRO_FUERA_DE_ALCANCE = "Ese registro de auditoría no está dentro de los que podés consultar."

# Cuentas vinculadas (USR-VNC-CTA, tarea 06b). Los textos de vincular son los del prototipo (modalHtml 'link'
# y link-do).
MENSAJE_SIN_VINCULOS = "Tu cuenta no puede vincular cuentas."
MENSAJE_NO_SE_PUDO_VINCULAR = (
    "No pudimos vincular la cuenta. Revisá el email y la contraseña, y volvé a intentarlo."
)
MENSAJE_MISMA_CUENTA = "No podés vincular una cuenta consigo misma."
MENSAJE_YA_VINCULADA = "Esa cuenta ya está vinculada a la tuya."
MENSAJE_CAMBIO_SIMULTANEO = "Las cuentas cambiaron mientras hacías esto. Volvé a intentarlo."
MENSAJE_FUERA_DEL_GRUPO = "Esa cuenta no está en tu grupo de cuentas vinculadas."
MENSAJE_CUENTA_NO_DISPONIBLE = "No se puede pasar a esa cuenta ahora: no está disponible."

# Forma de primer acceso de una cuenta al darla de alta, restablecerla o reactivarla (regla 4 de USR-ALT-USR y de
# USR-MOD-USR, SEG-04, SEG-20, D-35): una invitación por correo o una contraseña temporal.
ACCESO_INVITACION = "invitacion"
ACCESO_TEMPORAL = "temporal"
FORMAS_DE_ACCESO = (ACCESO_INVITACION, ACCESO_TEMPORAL)
# Lo que devuelven el alta, el restablecimiento y la reactivación sobre el acceso: la forma elegida, la contraseña
# temporal (solo si se eligió; se muestra una vez y no se guarda) y si la invitación salió (regla 11: si falló, la
# vista se lo avisa a quien gestiona la cuenta).
ResultadoAcceso = namedtuple("ResultadoAcceso", "forma contrasena_temporal invitacion_enviada")

# D-09 y SEG-15: nombre de la restricción de la base que impide un segundo Gerente activo (core/models.py).
RESTRICCION_UN_SOLO_GERENTE_ACTIVO = "un_solo_gerente_activo"

# Regla 1 de USR-ALT-USR: los roles que da de alta el Gerente, con la clase de cada uno. El Gerente
# (D-09) y el Administrador (SEG-17) no están: no se dan de alta desde las pantallas del Gerente.
CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE = {
    Usuario.Rol.AGRONOMO: Agronomo,
    Usuario.Rol.CAPATAZ: Capataz,
    Usuario.Rol.VENDEDOR: Vendedor,
    Usuario.Rol.TRANSPORTISTA: Transportista,
    Usuario.Rol.TECNICO: Tecnico,
}

# Regla 1 de USR-ALT-USR y D-16: el Administrador da de alta solo la cuenta del Gerente. Los
# Administradores no se dan de alta desde el Sistema (SEG-17).
CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_ADMINISTRADOR = {Usuario.Rol.GERENTE: Gerente}


def _exigir_actor_activo(actor, roles, mensaje=MENSAJE_SIN_ACCESO):
    """Precondición a de los casos de uso de cuentas: ``actor`` es una cuenta activa con un rol de
    ``roles``. Se rechaza con ``PermissionDenied`` (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in roles:
        raise PermissionDenied(mensaje)


def _exigir_gestor_activo(actor):
    """Precondición a de USR-CNS-USR y USR-ALT-USR: cuenta activa de Gerente o de Administrador (D-16)."""
    _exigir_actor_activo(actor, (Usuario.Rol.GERENTE, ADMINISTRADOR))


def _exigir_actor_sigue_activo(actor):
    """SEG-15 y precondición a: ``actor`` sigue activo ahora, después de esperar los bloqueos.

    ``actor`` es la cuenta que cargó el pedido: pudo quedar inactiva mientras esta operación esperaba el
    bloqueo de otra (por ejemplo, con tres Administradores, A da de baja a B mientras B da de baja a C).
    Es una consulta nueva, posterior al bloqueo, así que ve lo que la otra operación confirmó. Si ya no
    está activo, ``PermissionDenied`` y no cambia nada (SEG-13).
    """
    if not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def clases_de_rol_que_da_de_alta(actor):
    """Roles que ``actor`` da de alta, con la clase de cada uno (regla 1 de USR-ALT-USR, D-16)."""
    if rol_de(actor) == ADMINISTRADOR:
        return CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_ADMINISTRADOR
    return CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE


def roles_que_gestiona(actor):
    """Roles de las cuentas que ``actor`` consulta, como pares (valor, nombre) para el filtro de la lista
    (reglas 1 y 2 de USR-CNS-USR). El Administrador no es un valor de ``rol`` (D-10): se filtra con
    ``ADMINISTRADOR``."""
    if rol_de(actor) == ADMINISTRADOR:
        return [(Usuario.Rol.GERENTE.value, Usuario.Rol.GERENTE.label), (ADMINISTRADOR, "Administrador")]
    return [
        (rol.value, rol.label) for rol in Usuario.Rol if rol in CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE
    ]


def _bloquear_gerentes():
    """SEG-15 y D-09: bloquea todas las filas de Gerente, activas o no, en orden de id.

    Lo usan las operaciones que pueden dejar un Gerente activo (el alta y, en la 05b, la reactivación).
    Una segunda operación simultánea espera acá hasta que la primera confirme; la consulta que viene
    después (otra sentencia) ya ve lo que la primera confirmó. Se bloquean todas, sin filtrar por
    ``is_active``: la fila que la otra operación está activando puede figurar como inactiva. El orden
    fijo evita que dos operaciones se esperen mutuamente (deadlock). Si no hay ninguna fila de Gerente
    (el primer alta), no hay nada que bloquear: la cubre la restricción ``un_solo_gerente_activo``.
    ``FOR NO KEY UPDATE`` y no ``FOR UPDATE`` (D-32): el Gerente es quien actúa en otras operaciones y la clave
    foránea de su auditoría pide ``FOR KEY SHARE`` sobre su fila al confirmar; ``FOR UPDATE`` chocaría con eso.
    """
    list(
        Usuario.objects.select_for_update(no_key=True)
        .filter(rol=Usuario.Rol.GERENTE)
        .order_by("pk")
    )


def _bloquear_administradores_activos():
    """SEG-15 y precondición c de USR-BAJ-USR: bloquea todas las filas de Administradores activos, en orden
    de id.

    Lo usa la baja de un Administrador. Una segunda baja simultánea espera acá hasta que la primera
    confirme; cuando sigue, PostgreSQL vuelve a evaluar el filtro sobre las filas bloqueadas, así que la
    cuenta que la primera dio de baja ya no figura, y la cuenta de los que quedan es la real. A diferencia
    del Gerente, no hay una restricción de la base que respalde esta regla (compara varias filas): el
    bloqueo es lo único que la garantiza. El orden fijo evita que dos operaciones se esperen mutuamente.
    ``FOR NO KEY UPDATE`` y no ``FOR UPDATE`` (D-32): los Administradores son quienes actúan en otras
    operaciones, y la clave foránea de su auditoría pide ``FOR KEY SHARE`` sobre su fila al confirmar.
    """
    list(
        Usuario.objects.select_for_update(no_key=True)
        .filter(is_superuser=True, is_active=True)
        .order_by("pk")
    )


def _bloquear_grupo_de_baja(cuenta):
    """Bloqueo previo de la baja: si la cuenta es de un Administrador, bloquea a todos los activos (SEG-15)."""
    if cuenta.is_superuser:
        _bloquear_administradores_activos()


def _bloquear_grupos(grupos_ids):
    """D-17 y D-30: bloquea las filas de ``GrupoCuentas`` indicadas, en orden de id.

    Todas las operaciones que cambian quién está en un grupo (vincular, desvincular, restablecer y reactivar)
    toman este bloqueo PRIMERO, antes que el de los invariantes y que el de las cuentas. Dos operaciones
    sobre el mismo grupo se esperan acá; el orden fijo evita que dos operaciones sobre dos grupos se esperen
    mutuamente (deadlock). ``FOR NO KEY UPDATE`` (``no_key=True``) y no ``FOR UPDATE``: al insertar el
    registro de auditoría, la clave foránea hacia quien actúa toma un bloqueo ``FOR KEY SHARE`` sobre su fila;
    ``FOR UPDATE`` choca con ese bloqueo y ``FOR NO KEY UPDATE`` no, porque no modifica la clave (D-32). Entre
    estas operaciones sigue habiendo exclusión mutua: ``FOR NO KEY UPDATE`` choca consigo mismo.
    """
    if grupos_ids:
        list(
            GrupoCuentas.objects.select_for_update(no_key=True)
            .filter(pk__in=grupos_ids)
            .order_by("pk")
        )


def _bloquear_grupo_de_cuenta(cuenta):
    """Bloquea el grupo de ``cuenta`` (el que se leyó antes de bloquear), si tiene uno (D-17)."""
    if cuenta.grupo_id is not None:
        _bloquear_grupos([cuenta.grupo_id])


def _bloquear_grupo_de_restablecimiento(cuenta):
    """Bloqueo previo del restablecimiento: el grupo de la cuenta, porque la cuenta sale de él (SEG-11)."""
    _bloquear_grupo_de_cuenta(cuenta)


def _bloquear_grupo_de_reactivacion(cuenta):
    """Bloqueo previo de la reactivación: primero el grupo de la cuenta, porque sale de él (SEG-11), y después,
    si la cuenta es de un Gerente, todas las filas de Gerente (regla 5, D-09, SEG-15). Reactivar un
    Administrador no puede romper ningún invariante. Orden de D-30 ampliado: grupo de cuentas, invariantes,
    cuenta."""
    _bloquear_grupo_de_cuenta(cuenta)
    if cuenta.rol == Usuario.Rol.GERENTE:
        _bloquear_gerentes()


def _nombre_de_restriccion(error):
    """Nombre de la restricción de la base que violó un ``IntegrityError``, o ``None`` si no se puede leer.

    Django envuelve el error de psycopg y lo deja en ``__cause__``; psycopg 3 trae el nombre en
    ``diag.constraint_name``. Si falta cualquiera de los dos, devuelve ``None`` y quien llama informa un
    error conocido, nunca un 500 (D-30).
    """
    diagnostico = getattr(error.__cause__, "diag", None)
    return getattr(diagnostico, "constraint_name", None)


def _gerente_activo():
    """El Gerente activo, o ``None`` (D-09). Es una consulta aparte, posterior a ``_bloquear_gerentes``:
    al ser otra sentencia, ve lo que una operación simultánea confirmó mientras esta esperaba el bloqueo."""
    return Usuario.objects.filter(rol=Usuario.Rol.GERENTE, is_active=True).first()


def _error_gerente_activo(activo=None, reactivando=False):
    """Error de la regla 2 de USR-ALT-USR (alta) o de la regla 5 de USR-MOD-USR (``reactivando``): ya hay
    un Gerente activo (D-09).

    Nombra al Gerente activo, como el prototipo (vAlta y react-do). Sin ``activo`` (cuando el rechazo vino
    de la restricción de la base) lo busca: la otra operación ya confirmó, así que lo encuentra.
    """
    activo = activo or _gerente_activo()
    quien = f": {activo.get_full_name()}" if activo else ""
    if reactivando:
        return ValidationError(
            f"No se puede reactivar: ya hay un Gerente activo{quien}. Dalo de baja primero.",
            code="gerente_activo",
        )
    return ValidationError(
        f"Ya hay un Gerente activo{quien}. Solo puede haber uno a la vez: para dar de alta a otro, "
        "primero dá de baja al actual desde su ficha.",
        code="gerente_activo",
    )


def cambiar_contrasena(usuario, contrasena_nueva, contrasena_actual=None):
    """USR-CMB-CTR: la persona reemplaza la contraseña de su propia cuenta por una nueva.

    Lo usan las dos pantallas del caso de uso: «Elegí tu contraseña» (cuando extiende a USR-INI-SES) y el
    cambio voluntario desde Mi perfil (USR-GST-PRF regla 3, tarea 06a).
    El modo lo decide el estado de la cuenta, no quien llama: si la cuenta tiene contraseña temporal
    el caso extiende a USR-INI-SES y no pide la contraseña actual; si no, la pide (regla 1).
    Regla 3: se cambia solo la contraseña de ``usuario``; este servicio no recibe ni busca otra
    cuenta, así que ninguna pantalla puede usarlo para cambiar la de una ajena.
    Regla 4 (las cuentas vinculadas se mantienen, D-17): este servicio no toca el grupo de cuentas.
    (Restablecer la contraseña de la cuenta, en cambio, sí la saca del grupo: SEG-11.)

    Falla con ``ValidationError`` por campo (``contrasena_actual``, ``contrasena_nueva``) y no
    cambia nada. Si sale bien, deja la instancia ``usuario`` con la contraseña nueva y sin
    temporal (la vista la necesita para conservar la sesión actual, SEG-10) y la devuelve.
    Cerrar las demás sesiones (postcondición c, SEG-10) no requiere código acá: la sesión guarda un
    hash de la contraseña y, al cambiarla, las demás sesiones dejan de ser válidas.
    """
    with transaction.atomic():
        # Se bloquea la fila para que dos cambios simultáneos no se pisen y para decidir el modo
        # con el estado real de la cuenta. FOR NO KEY UPDATE (D-32): no choca con el FOR KEY SHARE que
        # pide la auditoría de otra operación en la que esta cuenta es quien actúa.
        cuenta = Usuario.objects.select_for_update(no_key=True).get(pk=usuario.pk)
        era_temporal = cuenta.tiene_contrasena_temporal

        errores = {}
        if not era_temporal:
            # USR-CMB-CTR regla 1.
            if not contrasena_actual:
                errores["contrasena_actual"] = [
                    ValidationError("Ingresá tu contraseña actual.", code="required")
                ]
            elif not cuenta.check_password(contrasena_actual):
                errores["contrasena_actual"] = [
                    ValidationError("La contraseña actual no es correcta.", code="incorrecta")
                ]

        # USR-CMB-CTR regla 2 y SEG-03: política de contraseñas, incluida «distinta de la actual».
        if not contrasena_nueva:
            errores["contrasena_nueva"] = [
                ValidationError("Ingresá la contraseña nueva.", code="required")
            ]
        else:
            try:
                validate_password(contrasena_nueva, cuenta)
            except ValidationError as error:
                errores["contrasena_nueva"] = error.error_list

        if errores:
            raise ValidationError(errores)

        # Postcondiciones a y b: contraseña reemplazada y, si era temporal, deja de serlo.
        cuenta.set_password(contrasena_nueva)
        cuenta.fecha_contrasena_temporal = None
        cuenta.save(update_fields=["password", "fecha_contrasena_temporal"])

        # Postcondición d, SEG-14 y D-22: en la misma transacción, sin ninguna contraseña.
        RegistroAuditoria.objects.registrar(
            usuario=cuenta,
            accion=RegistroAuditoria.Accion.CAMBIO_CONTRASENA,
            afectados=[cuenta],
            detalle={"datos": {"era_temporal": era_temporal}},  # D-36
        )

    usuario.password = cuenta.password
    usuario.fecha_contrasena_temporal = None
    return usuario


def consultar_usuarios(actor, rol=None, estado=None, busqueda=""):
    """USR-CNS-USR: cuentas dentro del alcance de ``actor``, filtradas y buscadas (reglas 1 y 2).

    - Precondición a: ``actor`` es un Gerente o un Administrador activos (D-16).
    - Regla 1: solo las cuentas de ``en_alcance_de`` (Agrónomo, Capataz, Vendedor, Transportista
      y Técnico para el Gerente; Gerentes y Administradores para el Administrador).
    - Regla 2: ``rol`` y ``estado`` (``"activo"`` o ``"inactivo"``) filtran; ``busqueda`` separa
      palabras y exige que la cuenta coincida con todas, cada una en nombre, apellido o email, sin
      distinguir mayúsculas. ``rol=ADMINISTRADOR`` filtra los superusuarios, que no tienen ``rol`` (D-10).
    - Regla 4 y SEG-14: la consulta no se audita ni cambia nada.

    Devuelve un QuerySet perezoso de solo lectura: no abre ``transaction.atomic()`` porque no
    escribe y una sola consulta ya es consistente en sí misma.
    """
    _exigir_gestor_activo(actor)
    cuentas = Usuario.objects.en_alcance_de(actor)
    if rol == ADMINISTRADOR:
        cuentas = cuentas.filter(is_superuser=True)
    elif rol:
        cuentas = cuentas.filter(rol=rol)
    if estado == "activo":
        cuentas = cuentas.filter(is_active=True)
    elif estado == "inactivo":
        cuentas = cuentas.filter(is_active=False)
    for palabra in (busqueda or "").split():
        cuentas = cuentas.filter(
            Q(first_name__icontains=palabra)
            | Q(last_name__icontains=palabra)
            | Q(email__icontains=palabra)
        )
    return cuentas.order_by("last_name", "first_name", "email")


def obtener_cuenta(actor, cuenta_id):
    """Cuenta ``cuenta_id`` si está dentro del alcance de ``actor`` (regla 1 de USR-CNS-USR, D-28).

    Un id que no existe da ``Http404``; una cuenta que existe pero está fuera del alcance da
    ``PermissionDenied`` con mensaje (SEG-13). Lo usan la ficha y, en la tarea 04b, las acciones
    sobre una cuenta. Precondición a: Gerente o Administrador activos (D-16).
    """
    _exigir_gestor_activo(actor)
    cuenta = Usuario.objects.filter(pk=cuenta_id).first()
    if cuenta is None:
        raise Http404("No existe esa cuenta.")
    if not Usuario.objects.en_alcance_de(actor).filter(pk=cuenta.pk).exists():
        raise PermissionDenied(MENSAJE_FUERA_DE_ALCANCE)
    return cuenta


def acciones_permitidas(actor, cuenta):
    """Acciones que ``actor`` puede hacer hoy sobre ``cuenta``: un subconjunto de ``{"modificar",
    "restablecer", "reactivar", "baja"}``. La ficha y el aviso de la regla 8 del alta muestran solo estos
    botones, para que nadie llegue por un botón a un error 403 (D-30).

    - USR-MOD-USR y USR-BAJ-USR: sobre una cuenta de su alcance (regla 1), el Gerente y el Administrador
      modifican los datos (también de una inactiva, D-28); restablecen y dan de baja una activa; reactivan
      una inactiva (D-28).
    - Regla 4 de USR-MOD-USR: nadie restablece su propia contraseña (el Administrador es el único que
      tiene su propia cuenta en su alcance).
    - Precondición c de USR-BAJ-USR y SEG-15: no se ofrece la baja de un Administrador si no queda otro
      Administrador activo (el caso real es la propia cuenta del único Administrador activo).
    - Regla 5 de USR-MOD-USR: «reactivar» se ofrece para cualquier cuenta inactiva; si es un Gerente y ya
      hay otro activo, el rechazo se explica al confirmar (D-30), no es un 403.

    No consulta ni cambia nada más que el alcance y los Administradores activos.
    """
    if actor is None or not actor.is_active:
        return frozenset()
    if rol_de(actor) not in (Usuario.Rol.GERENTE, ADMINISTRADOR):
        return frozenset()
    if not Usuario.objects.en_alcance_de(actor).filter(pk=cuenta.pk).exists():
        return frozenset()
    if not cuenta.is_active:
        return frozenset({"modificar", "reactivar"})
    acciones = {"modificar", "restablecer", "baja"}
    if cuenta.pk == actor.pk:
        acciones.discard("restablecer")  # regla 4
    if cuenta.is_superuser and not _hay_otro_administrador_activo(cuenta):
        acciones.discard("baja")  # precondición c
    return frozenset(acciones)


def _hay_otro_administrador_activo(cuenta):
    """True si hay un Administrador activo distinto de ``cuenta`` (precondición c de USR-BAJ-USR)."""
    return Usuario.objects.filter(is_superuser=True, is_active=True).exclude(pk=cuenta.pk).exists()


# ---- AUD-CNS-REG: consultar el registro de auditoría (D-36) ----

# Valor de «cuenta que actuó» para los registros que hizo InfoPonia, sin una cuenta detrás (regla 3).
ACTUO_INFOPONIA = "infoponia"


def _exigir_consulta_de_auditoria(actor):
    """Precondición a de AUD-CNS-REG: ``actor`` es una cuenta activa de Gerente o de Administrador (SEG-13)."""
    _exigir_actor_activo(actor, (Usuario.Rol.GERENTE, ADMINISTRADOR), MENSAJE_SIN_ACCESO_A_AUDITORIA)


def puede_ver_auditoria_de(actor, cuenta):
    """True si ``actor`` puede abrir la auditoría de ``cuenta`` (regla 7 de AUD-CNS-REG): la ficha muestra «Ver
    auditoría» solo entonces, para que ningún enlace lleve a un 403 (D-30). Es lo mismo que ``_cuenta_filtrable``
    permite: el Administrador, cualquier cuenta; el Gerente, todas menos las de Administrador (D-36)."""
    if actor is None or not actor.is_active:
        return False
    rol = rol_de(actor)
    if rol == ADMINISTRADOR:
        return True
    return rol == Usuario.Rol.GERENTE and not cuenta.is_superuser


def cuentas_filtrables_para_auditoria(actor):
    """Cuentas que ``actor`` puede elegir en los filtros de la auditoría (regla 2 de AUD-CNS-REG, D-36): las mismas por
    las que ``consultar_auditoria`` no da 403. Las desplegables de la pantalla las ofrecen todas, ordenadas por
    apellido. Precondición a: Gerente o Administrador activos."""
    _exigir_consulta_de_auditoria(actor)
    cuentas = Usuario.objects.all()
    if rol_de(actor) != ADMINISTRADOR:
        cuentas = cuentas.exclude(is_superuser=True)
    return cuentas.order_by("last_name", "first_name", "email")


def _cuenta_filtrable(actor, cuenta_id):
    """La cuenta por la que ``actor`` quiere filtrar la auditoría (regla 2 de AUD-CNS-REG, D-28 y D-36). Un id que
    no existe da ``Http404``; el Gerente que filtra por una cuenta de Administrador recibe ``PermissionDenied``
    (nunca aparece en un registro que él pueda ver). El Gerente sí puede filtrar por su cuenta y por las de Gerentes
    anteriores: aparecen en registros que ve (por ejemplo, el Gerente anterior que modificó a un Capataz).
    Los otros filtros se siguen limitando a lo visible (regla 1)."""
    cuenta = Usuario.objects.filter(pk=cuenta_id).first()
    if cuenta is None:
        raise Http404("No existe esa cuenta.")
    if not puede_ver_auditoria_de(actor, cuenta):
        raise PermissionDenied(MENSAJE_FUERA_DE_ALCANCE)
    return cuenta


def _el_dia_empieza(dia):
    """Fecha y hora del comienzo de ``dia`` en la zona horaria del sistema (``TIME_ZONE``)."""
    return timezone.make_aware(datetime.combine(dia, time.min))


def consultar_auditoria(
    actor, desde=None, hasta=None, quien_actuo=None, accion=None, afectado_id=None, cuenta_id=None
):
    """AUD-CNS-REG: registros de auditoría que ``actor`` puede ver, filtrados y del más reciente al más viejo.

    - Precondición a y SEG-13: ``actor`` es un Gerente o un Administrador activos; si no, ``PermissionDenied``.
    - Regla 1: solo los de ``RegistroAuditoria.objects.visibles_para(actor)``, el único lugar del alcance.
    - Regla 2: los filtros se combinan. ``desde`` y ``hasta`` son fechas, inclusive, en la zona horaria del sistema
      (se consulta ``>= desde 00:00`` y ``< hasta + 1 día 00:00``, que puede usar el índice de la fecha).
      ``quien_actuo`` es el id de la cuenta que actuó, o ``ACTUO_INFOPONIA`` para los registros sin cuenta.
      ``accion`` es un valor de ``RegistroAuditoria.Accion``. ``afectado_id`` es el id de una cuenta afectada
      (``contains`` sobre jsonb, que usa el índice GIN). ``cuenta_id`` es una cuenta que actuó o fue afectada: es el
      filtro de la ficha (regla 7).
    - Una cuenta que no existe da ``Http404``; una fuera del alcance del Gerente, ``PermissionDenied`` (D-28, D-36).
    - Regla 6, SEG-14 y postcondición a: no escribe ni audita; no abre ``transaction.atomic()`` porque solo lee.

    Devuelve un QuerySet perezoso con ``usuario`` ya cargado.
    """
    _exigir_consulta_de_auditoria(actor)
    registros = RegistroAuditoria.objects.visibles_para(actor).select_related("usuario")
    if desde is not None:
        registros = registros.filter(fecha_hora__gte=_el_dia_empieza(desde))
    if hasta is not None:
        registros = registros.filter(fecha_hora__lt=_el_dia_empieza(hasta + timedelta(days=1)))
    if quien_actuo == ACTUO_INFOPONIA:
        registros = registros.filter(usuario__isnull=True)
    elif quien_actuo is not None:
        registros = registros.filter(usuario_id=_cuenta_filtrable(actor, quien_actuo).pk)
    if accion:
        registros = registros.filter(accion=accion)
    if afectado_id is not None:
        cuenta = _cuenta_filtrable(actor, afectado_id)
        registros = registros.filter(afectados__contains=[{"modelo": MODELO_CUENTA, "id": cuenta.pk}])
    if cuenta_id is not None:
        cuenta = _cuenta_filtrable(actor, cuenta_id)
        registros = registros.filter(
            Q(usuario_id=cuenta.pk) | Q(afectados__contains=[{"modelo": MODELO_CUENTA, "id": cuenta.pk}])
        )
    return registros.order_by("-fecha_hora", "-id")


def obtener_registro(actor, registro_id):
    """Un registro de auditoría si está dentro de los que ``actor`` puede ver (regla 1 de AUD-CNS-REG, D-28).

    Un id que no existe da ``Http404``; uno que existe pero está fuera del alcance, ``PermissionDenied`` con
    mensaje (SEG-13). Precondición a: Gerente o Administrador activos. No audita (regla 6).
    """
    _exigir_consulta_de_auditoria(actor)
    visibles = RegistroAuditoria.objects.visibles_para(actor).select_related("usuario")
    registro = visibles.filter(pk=registro_id).first()
    if registro is None:
        if not RegistroAuditoria.objects.filter(pk=registro_id).exists():
            raise Http404("No existe ese registro de auditoría.")
        raise PermissionDenied(MENSAJE_REGISTRO_FUERA_DE_ALCANCE)
    return registro


def gerente_activo_que_impide_reactivar(cuenta):
    """El Gerente activo si ``cuenta`` es un Gerente inactivo y ya hay otro activo (regla 5 de USR-MOD-USR,
    D-09); si no, ``None``. La ventana de «Reactivar cuenta» lo usa para mostrar el motivo sin pedir
    confirmación (D-30). No bloquea nada: la regla la vuelve a controlar ``reactivar_usuario`` con el
    bloqueo de SEG-15."""
    if cuenta.is_active or cuenta.rol != Usuario.Rol.GERENTE:
        return None
    return _gerente_activo()


def quien_gestiona(cuenta):
    """A quién le pide la persona que corrija los datos de ``cuenta`` (regla 2 de USR-GST-PRF), como texto
    para «Para corregir estos datos, pedíselo …» de Mi perfil: «al Administrador» para el Gerente; «al Gerente
    (<nombre>)» para los demás roles, o «al Gerente» si no hay uno activo (D-13). ``None`` para el
    Administrador, que modifica sus propios datos (D-16). El prototipo dice «a el»; acá va la contracción.

    Sigue el alcance de ``en_alcance_de``: el Administrador gestiona al Gerente y el Gerente a los demás roles.
    No bloquea ni cambia nada (regla 4 de USR-GST-PRF: la consulta no se audita).
    """
    rol = rol_de(cuenta)
    if rol == ADMINISTRADOR:
        return None
    if rol == Usuario.Rol.GERENTE:
        return "al Administrador"
    activo = _gerente_activo()
    return f"al Gerente ({activo.get_full_name()})" if activo else "al Gerente"


def gerente_activo_que_impide_el_alta(actor):
    """El Gerente activo si ``actor`` es un Administrador que no puede dar de alta otro (regla 2 de
    USR-ALT-USR, D-09); si no, ``None``. La pantalla de alta lo usa para avisar antes de completar el
    formulario y deshabilitar «Dar de alta» (prototipo vAlta). No bloquea nada: la regla la vuelve a
    controlar ``alta_usuario`` con el bloqueo de SEG-15."""
    if rol_de(actor) != ADMINISTRADOR:
        return None
    return _gerente_activo()


def _error_de_email_repetido(actor, email):
    """Error del email ya usado por otra cuenta (regla 3 de USR-ALT-USR).

    Regla 8: si la cuenta es inactiva y está dentro del alcance de ``actor``, el error lleva el
    código ``email_de_cuenta_inactiva`` y la cuenta en ``params`` para ofrecer reactivarla. Si no
    está en su alcance (D-28), el mensaje es el genérico: no se revela que está inactiva.
    """
    cuenta = Usuario.objects.filter(email=email).first()
    if (
        cuenta is not None
        and not cuenta.is_active
        and Usuario.objects.en_alcance_de(actor).filter(pk=cuenta.pk).exists()
    ):
        return ValidationError(
            "Ese email pertenece a una cuenta inactiva. No se da de alta otra: reactivala.",
            code="email_de_cuenta_inactiva",
            params={"cuenta": cuenta},
        )
    return ValidationError(MENSAJE_EMAIL_REPETIDO, code="email_repetido")


def _limpiar_datos_personales(nombre, apellido, email, telefono):
    """Limpia y valida los datos personales de una cuenta; los comparten el alta y la modificación.

    Devuelve ``(nombre, apellido, email, telefono, errores)``: los valores sin espacios en los
    extremos y el email en minúsculas (SEG-01), y un dict ``{campo: [ValidationError]}`` con lo que
    no cumple. Regla 7 de USR-ALT-USR: nombre, apellido y email obligatorios, teléfono opcional.
    Regla 9 de USR-ALT-USR (y de USR-MOD-USR), D-21 y D-28: formato y largo del teléfono. La
    unicidad del email no se controla acá: necesita la base y el bloqueo de la transacción.
    """
    nombre = (nombre or "").strip()
    apellido = (apellido or "").strip()
    email = Usuario.objects.normalize_email(email)
    telefono = (telefono or "").strip()

    errores = {}
    if not nombre:
        errores["nombre"] = [ValidationError("Ingresá el nombre.", code="required")]
    if not apellido:
        errores["apellido"] = [ValidationError("Ingresá el apellido.", code="required")]
    if not email:
        errores["email"] = [ValidationError("Ingresá el email.", code="required")]
    else:
        try:
            validate_email(email)
        except ValidationError:
            errores["email"] = [
                ValidationError(
                    "Ingresá un email válido, por ejemplo nombre@dominio.com.", code="invalid"
                )
            ]
    try:
        validar_telefono(telefono)
    except ValidationError as error:
        errores["telefono"] = error.error_list
    return nombre, apellido, email, telefono, errores


# Aviso al nuevo Gerente (postcondición d de USR-ALT-USR; NOT-01, D-42). El texto se arma acá y no en ``core.notificaciones``
# (D-42): con los nombres de las cosas, no con ids.
TITULO_PENDIENTES_DEL_GERENTE = "Pendientes que esperan al Gerente"


def _detalle_de_pendientes(total, detalle):
    """El detalle del aviso de resumen al nuevo Gerente: «Tiene 3 pendientes. Alertas activas para el Gerente: 3.», o
    «No tiene pendientes.» si la suma es 0 (D-14, D-42). ``total`` y ``detalle`` son lo que da
    ``core.notificaciones.pendientes_del_gerente``."""
    if total == 0:
        return "No tiene pendientes."
    cantidad = f"Tiene {total} pendiente{'' if total == 1 else 's'}."
    return " ".join([cantidad, *(f"{descripcion}: {n}." for descripcion, n in detalle)])


def alta_usuario(
    actor, rol, nombre, apellido, email, telefono="", acceso=ACCESO_TEMPORAL, construir_url=None
):
    """USR-ALT-USR: da de alta una cuenta con la forma de primer acceso que elige quien la da de alta.

    Devuelve ``(cuenta, ResultadoAcceso)``. No recibe contraseña: nadie elige la de otra persona (regla 4, SEG-04,
    SEG-20).

    - Regla 4 (D-35): ``acceso`` es una invitación por correo (``ACCESO_INVITACION``: la cuenta queda sin
      contraseña hasta que la persona la elija, postcondición a) o una contraseña temporal (``ACCESO_TEMPORAL``:
      se muestra una sola vez a quien hizo el alta y no se guarda en ningún lado, postcondición c). Sin indicarla,
      la temporal: las vistas siempre la pasan explícita.
    - Regla 10: sin el correo configurado, la invitación se rechaza en el campo ``acceso``.
    - Postcondición c y regla 11 (D-35, D-14): la invitación se envía DESPUÉS de confirmar la transacción; si el
      envío falla, la cuenta queda creada con la invitación pendiente y ``invitacion_enviada`` es False.
      ``construir_url`` arma la URL absoluta del enlace (la vista pasa ``request.build_absolute_uri``).

    - Precondición a: ``actor`` es un Gerente o un Administrador activos (D-16). Precondición b y
      regla 3: email único sin distinguir mayúsculas (SEG-01).
    - Regla 1: el Gerente da de alta los cinco roles de ``CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE``; el
      Administrador, solo al Gerente (D-16). Nadie da de alta Administradores (SEG-17).
    - Regla 2, precondición c, D-09 y SEG-15: con un Gerente activo no se da de alta otro. Se bloquean
      las filas de Gerente y después se consulta si hay uno activo; el rechazo es un error general
      (``NON_FIELD_ERRORS``, código ``gerente_activo``).
    - Regla 7: nombre, apellido, email y rol obligatorios; el teléfono es opcional.
    - Regla 8: el email de una cuenta inactiva no crea otra (ver ``_error_de_email_repetido``).
    - Regla 9 y D-21/D-28: formato y largo del teléfono.
    - Postcondiciones a y e (SEG-14, D-22): la cuenta y su registro de auditoría, con la forma de acceso y sin
      contraseñas ni el token, se guardan en la misma transacción.
    - Postcondición d, D-14 y D-42 (NOT-01): si el rol es Gerente, una única notificación al Gerente recién creado, con la
      cantidad de pendientes que esperan una resolución del Gerente (``notificaciones.pendientes_del_gerente``), en la
      misma transacción: si el alta falla, no queda. El destinatario es la cuenta nueva, que ya es el Gerente activo
      (D-09): la omisión «sin Gerente activo» de D-14 solo se da en ``notificar_al_gerente``, no acá. No se audita.

    Pendiente: invernadero del Transportista (R155).

    Falla con ``ValidationError`` por campo y no crea nada.
    """
    _exigir_gestor_activo(actor)
    clases = clases_de_rol_que_da_de_alta(actor)

    nombre, apellido, email, telefono, errores = _limpiar_datos_personales(
        nombre, apellido, email, telefono
    )
    rol = (str(rol) if rol else "").strip()
    # Regla 1: solo los roles que da de alta este actor; los Administradores, nunca.
    if not rol:
        errores["rol"] = [ValidationError("Elegí el rol.", code="required")]
    elif rol not in clases:
        errores["rol"] = [ValidationError("Ese rol no se puede dar de alta acá.", code="rol_invalido")]
    # Regla 4 y regla 10: la forma de acceso, junto con los demás errores.
    errores_de_acceso = _errores_de_forma_de_acceso(acceso)
    if errores_de_acceso:
        errores["acceso"] = errores_de_acceso

    with transaction.atomic():
        if rol == Usuario.Rol.GERENTE and "rol" not in errores:
            # Regla 2 y SEG-15: primero el bloqueo, después la consulta (ver ``_bloquear_gerentes``).
            _bloquear_gerentes()
            activo = _gerente_activo()
            if activo is not None:
                errores[NON_FIELD_ERRORS] = [_error_gerente_activo(activo)]
        if "email" not in errores and Usuario.objects.filter(email=email).exists():
            errores["email"] = [_error_de_email_repetido(actor, email)]
        if errores:
            raise ValidationError(errores)

        cuenta = clases[rol](
            email=email, first_name=nombre, last_name=apellido, telefono=telefono, is_active=True
        )
        # Regla 4, SEG-04, SEG-20, D-18 y D-35: la temporal o la invitación las prepara el modelo; acá se guardan.
        contrasena_temporal = _preparar_acceso(cuenta, acceso)
        try:
            # Savepoint: si una operación simultánea ganó de mano, la base rechaza esta alta y se informa
            # el motivo en vez de un error 500. Sin Gerentes previos no hay filas que bloquear y el
            # segundo Gerente lo frena la restricción ``un_solo_gerente_activo`` (SEG-15).
            with transaction.atomic():
                cuenta.save()
        except IntegrityError as error:
            if _nombre_de_restriccion(error) == RESTRICCION_UN_SOLO_GERENTE_ACTIVO:
                raise ValidationError({NON_FIELD_ERRORS: [_error_gerente_activo()]}) from error
            # El email repetido, o una restricción que no se pudo identificar (D-30): nunca un 500.
            raise ValidationError(
                {"email": [ValidationError(MENSAJE_EMAIL_REPETIDO, code="email_repetido")]}
            ) from error

        # Postcondición e, SEG-14, D-22 y D-36: sin ninguna contraseña en el detalle. En un alta, todo dato cargado
        # es un cambio con «antes» nulo (el teléfono, solo si se cargó); la forma de acceso es contexto.
        datos_del_alta = {"rol": str(rol), "nombre": nombre, "apellido": apellido, "email": email}
        if telefono:
            datos_del_alta["telefono"] = telefono
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA,
            afectados=[cuenta],
            detalle={
                "cambios": {campo: {"antes": None, "despues": valor} for campo, valor in datos_del_alta.items()},
                "datos": {"acceso": acceso},
            },
        )
        # Postcondición d (NOT-01, D-42): el aviso de resumen al nuevo Gerente, dentro de la transacción y sin auditarlo.
        if rol == Usuario.Rol.GERENTE:
            notificaciones.notificar(
                cuenta, TITULO_PENDIENTES_DEL_GERENTE, _detalle_de_pendientes(*notificaciones.pendientes_del_gerente())
            )
    # Fuera de la transacción (D-14): la cuenta ya está confirmada.
    return cuenta, _resultado_acceso(cuenta, acceso, contrasena_temporal, construir_url)


def _error_general(mensaje, codigo):
    """Un ``ValidationError`` general (``NON_FIELD_ERRORS``) con ``mensaje`` y ``codigo``."""
    return ValidationError({NON_FIELD_ERRORS: [ValidationError(mensaje, code=codigo)]})


def _error_cambio_simultaneo():
    """Error de una operación que se encontró con que el grupo de una cuenta cambió mientras esperaba un
    bloqueo (D-17, D-32). Es un rechazo con mensaje y no un reintento, para no tomar bloqueos fuera de orden."""
    return _error_general(MENSAJE_CAMBIO_SIMULTANEO, "cambio_simultaneo")


def _bloquear_cuenta_en_alcance(actor, cuenta_id, bloqueo_previo=None, cuida_grupo=False):
    """Cuenta ``cuenta_id`` bloqueada para modificarla, si está dentro del alcance de ``actor``.

    Precondición a (``actor`` es un Gerente o un Administrador activos, D-16) y regla 1 de USR-MOD-USR y
    USR-BAJ-USR. Un id inexistente da ``Http404`` y una cuenta fuera del alcance, ``PermissionDenied``
    (D-28), igual que ``obtener_cuenta``. ``select_for_update(no_key=True)`` (CLAUDE.md, D-32) evita que dos
    operaciones simultáneas sobre la misma cuenta se pisen; hay que llamarla dentro de
    ``transaction.atomic()``. Es ``FOR NO KEY UPDATE`` y no ``FOR UPDATE`` porque la cuenta puede ser quien
    actúa en otra operación al mismo tiempo (el Gerente que se restablece mientras modifica su cuenta vinculada,
    o dos Administradores que se modifican entre sí): la clave foránea de esa auditoría pide ``FOR KEY SHARE``
    sobre su fila al confirmar, y ``FOR UPDATE`` haría que cada operación espere a la otra (deadlock).

    Orden de los bloqueos (SEG-15, D-30): primero el grupo de filas que cuida un invariante
    (``bloqueo_previo(cuenta)``: todos los Gerentes, o todos los Administradores activos, en orden de id) y
    recién después la cuenta. Si cada operación bloqueara primero su cuenta y después el grupo, dos
    operaciones sobre cuentas distintas podrían esperarse mutuamente (deadlock). Para saber a qué grupo
    pertenece la cuenta se la lee antes sin bloquear: el rol no cambia (D-11) y el alcance depende solo de
    él. Después de bloquear, se verifica de nuevo que ``actor`` siga activo y se vuelve a leer la cuenta,
    ya bloqueada, con su estado real.

    ``cuida_grupo`` (restablecer y reactivar, que sacan la cuenta de su grupo, SEG-11): el bloqueo previo
    tomó el grupo que se leyó antes de bloquear; si al releer la cuenta su grupo es otro (una vinculación
    terminó en el intervalo), el grupo que se tiene bloqueado no es el que corresponde y la operación se
    rechaza con «cambio_simultaneo». Modificar y dar de baja no cuidan el grupo: no lo cambian.
    """
    _exigir_gestor_activo(actor)
    cuenta = Usuario.objects.filter(pk=cuenta_id).first()
    if cuenta is None:
        raise Http404("No existe esa cuenta.")
    if not Usuario.objects.en_alcance_de(actor).filter(pk=cuenta.pk).exists():
        raise PermissionDenied(MENSAJE_FUERA_DE_ALCANCE)
    if bloqueo_previo is not None:
        bloqueo_previo(cuenta)
    _exigir_actor_sigue_activo(actor)
    bloqueada = Usuario.objects.select_for_update(no_key=True).get(pk=cuenta.pk)
    if cuida_grupo and bloqueada.grupo_id != cuenta.grupo_id:
        raise _error_cambio_simultaneo()
    return bloqueada


def modificar_usuario(actor, cuenta_id, nombre, apellido, email, telefono=""):
    """USR-MOD-USR: actualiza los datos personales de una cuenta y devuelve la cuenta.

    - Precondición a y regla 1: ``actor`` es un Gerente activo y la cuenta está dentro de su alcance.
      Para modificar los datos no se exige que la cuenta esté activa: el caso de uso solo pide el
      alcance y el prototipo (vUsuario, save-user) lo permite.
    - Regla 2 y D-11: no recibe ``rol``; el rol no se modifica.
    - Precondición c y regla 3: el email nuevo no puede ser el de otra cuenta (SEG-01); el de la propia
      cuenta no cuenta como repetido. Cambiarlo no afecta las cuentas vinculadas (regla 3, D-17): no toca
      el grupo.
    - Regla 9, D-21 y D-28: formato y largo del teléfono. Postcondición a: datos actualizados.
    - Postcondición d, SEG-14 y D-22: un registro de auditoría con los campos que cambiaron, antes y
      después, en la misma transacción. D-28: si no cambió nada, no se guarda ni se audita.

    Pendiente: el invernadero del Transportista (postcondición a) cuando exista el invernadero.
    Falla con ``ValidationError`` por campo y no cambia nada.
    """
    with transaction.atomic():
        cuenta = _bloquear_cuenta_en_alcance(actor, cuenta_id)
        nombre, apellido, email, telefono, errores = _limpiar_datos_personales(
            nombre, apellido, email, telefono
        )
        if (
            "email" not in errores
            and Usuario.objects.filter(email=email).exclude(pk=cuenta.pk).exists()
        ):
            errores["email"] = [ValidationError(MENSAJE_EMAIL_REPETIDO, code="email_repetido")]
        if errores:
            raise ValidationError(errores)

        # Solo los campos que cambiaron, como {campo: {antes, despues}} para la auditoría (D-36).
        nuevos = {
            "nombre": ("first_name", nombre),
            "apellido": ("last_name", apellido),
            "email": ("email", email),
            "telefono": ("telefono", telefono),
        }
        cambios = {}
        for clave, (campo, despues) in nuevos.items():
            antes = getattr(cuenta, campo)
            if antes != despues:
                cambios[clave] = {"antes": antes, "despues": despues}
                setattr(cuenta, campo, despues)
        if not cambios:
            return cuenta  # D-28

        try:
            # Savepoint: dos cambios simultáneos al mismo email los rechaza la base; se informa como
            # email repetido en vez de un error 500.
            with transaction.atomic():
                cuenta.save(update_fields=[nuevos[clave][0] for clave in cambios])
        except IntegrityError:
            raise ValidationError(
                {"email": [ValidationError(MENSAJE_EMAIL_REPETIDO, code="email_repetido")]}
            )
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION,
            afectados=[cuenta],
            detalle={"cambios": cambios},
        )
    return cuenta


# Resultado de sacar una cuenta de su grupo: el grupo del que salió, si el grupo se disolvió (quedaba una sola
# cuenta) y las otras cuentas afectadas (la que quedaba sola, si se disolvió).
SalidaDelGrupo = namedtuple("SalidaDelGrupo", "grupo_id disuelto otras_afectadas")


def _sacar_del_grupo(cuenta, otras=None):
    """Saca a ``cuenta`` de su grupo de cuentas vinculadas; si el grupo queda con una sola cuenta, lo disuelve
    (postcondición b de USR-VNC-CTA, SEG-11, D-17). Devuelve una ``SalidaDelGrupo``, o ``None`` si la cuenta
    no tenía grupo.

    Lo usan desvincular, restablecer y reactivar. Hay que llamarlo dentro de ``transaction.atomic()`` y con
    el grupo de la cuenta ya bloqueado (``_bloquear_grupos``): mientras se lo tiene, ninguna otra operación
    suma ni saca cuentas del grupo, así que la cuenta de las que quedan es la real. ``otras`` son las demás
    cuentas del grupo, si quien llama ya las bloqueó (desvincular); si no, se las bloquea acá en orden de id
    antes de escribirlas.
    """
    grupo_id = cuenta.grupo_id
    if grupo_id is None:
        return None
    if otras is None:
        otras = list(
            Usuario.objects.select_for_update(no_key=True)
            .filter(grupo_id=grupo_id)
            .exclude(pk=cuenta.pk)
            .order_by("pk")
        )
    Usuario.objects.filter(pk=cuenta.pk).update(grupo=None)
    cuenta.grupo = None
    disuelto = len(otras) < 2
    if disuelto:
        Usuario.objects.filter(pk__in=[otra.pk for otra in otras]).update(grupo=None)
        GrupoCuentas.objects.filter(pk=grupo_id).delete()
    return SalidaDelGrupo(grupo_id, disuelto, otras if disuelto else [])


def _auditar_con_salida_del_grupo(actor, accion, cuenta, salida, cambios=None, datos=None, otros_afectados=()):
    """Registra ``accion`` sobre ``cuenta`` con los ``cambios`` y los ``datos`` indicados (D-36) y, si salió de un
    grupo (SEG-11), lo deja en el registro: la salida es un cambio de la cuenta, ``grupo`` de la referencia al
    grupo a nulo, y, si el grupo se disolvió, la cuenta que quedaba sola figura también entre las afectadas. Sin
    grupo, el registro es el de siempre. ``otros_afectados`` son las instancias que suman los puntos de extensión de
    ``core/extensiones.py`` (D-43). Nunca contraseñas (D-22)."""
    cambios = dict(cambios or {})
    afectados = [cuenta]
    if salida is not None:
        cambios["grupo"] = {"antes": referencia_a_grupo(salida.grupo_id), "despues": None}
        afectados += salida.otras_afectadas
    afectados += list(otros_afectados)
    detalle = {}
    if cambios:
        detalle["cambios"] = cambios
    if datos:
        detalle["datos"] = datos
    RegistroAuditoria.objects.registrar(
        usuario=actor, accion=accion, afectados=afectados, detalle=detalle
    )


def restablecer_contrasena(actor, cuenta_id, acceso=ACCESO_TEMPORAL, construir_url=None):
    """USR-MOD-USR: restablece el acceso de una cuenta activa y devuelve un ``ResultadoAcceso``.

    - Regla 4, SEG-04, SEG-20 y D-35: con una invitación por correo (la cuenta queda sin contraseña hasta que la
      persona la elija) o con una contraseña temporal que genera el Sistema (no recibe contraseña, nadie elige la
      de otra persona), que vence a los 7 días y se muestra una sola vez a quien la restablece. Las mismas reglas
      que el alta: sin el correo configurado se rechaza la invitación (regla 10 de USR-ALT-USR) y, si el envío
      falla, el acceso se restablece igual (regla 11). Restablecer con otra invitación es reenviarla (regla 11 de
      USR-MOD-USR): el enlace anterior deja de servir. La invitación se envía después de confirmar (D-14).
    - Postcondición b y SEG-11: al cambiar el resumen de la contraseña, las sesiones abiertas con la
      cuenta dejan de ser válidas (Django compara ese resumen en cada pedido).
    - Regla 1: el Gerente no restablece su propia contraseña (no está en su alcance).
    - Regla 4: tampoco el Administrador, que sí tiene su cuenta en su alcance: la cambia con USR-CMB-CTR.
      Se rechaza con el código «propia_cuenta».
    - D-28: solo para cuentas activas; una inactiva se reactiva.
    - Postcondición d, SEG-14 y D-22: auditoría sin contraseñas, en la misma transacción.
    - Postcondición b y SEG-11 (tarea 06b, D-17): la cuenta sale de su grupo de cuentas vinculadas; si el grupo
      queda con una sola cuenta, se disuelve. Se bloquea el grupo antes que la cuenta (``cuida_grupo``); si su
      grupo cambió en el intervalo, «cambio_simultaneo». La auditoría suma el cambio ``grupo`` (D-36).
    """
    _exigir_forma_de_acceso(acceso)
    with transaction.atomic():
        cuenta = _bloquear_cuenta_en_alcance(
            actor,
            cuenta_id,
            bloqueo_previo=_bloquear_grupo_de_restablecimiento,
            cuida_grupo=True,
        )
        if cuenta.pk == actor.pk:
            raise ValidationError(
                "No se restablece tu propia contraseña: la cambiás vos con «Cambiar contraseña».",
                code="propia_cuenta",
            )
        if not cuenta.is_active:
            raise ValidationError(
                "La cuenta está inactiva: reactivala para generarle una contraseña temporal.",
                code="cuenta_inactiva",
            )
        temporal = _preparar_acceso(cuenta, acceso)
        cuenta.save(update_fields=["password", "fecha_contrasena_temporal", "fecha_invitacion"])
        # Postcondición b de USR-MOD-USR y SEG-11: la cuenta sale de su grupo de cuentas vinculadas.
        salida = _sacar_del_grupo(cuenta)
        _auditar_con_salida_del_grupo(
            actor, RegistroAuditoria.Accion.RESTABLECIMIENTO, cuenta, salida, datos={"acceso": acceso}
        )
    return _resultado_acceso(cuenta, acceso, temporal, construir_url)


def reactivar_usuario(actor, cuenta_id, acceso=ACCESO_TEMPORAL, construir_url=None):
    """USR-MOD-USR: reactiva una cuenta inactiva y restablece su acceso; devuelve un ``ResultadoAcceso``.

    - Postcondición c y regla 6: la cuenta queda activa y su acceso se restablece como en
      ``restablecer_contrasena``, con una invitación o una contraseña temporal (SEG-04, SEG-11, SEG-20, D-35).
    - D-28: solo para cuentas inactivas.
    - Regla 5, D-09 y SEG-15: solo se reactiva un Gerente si no hay otro activo. Se bloquean todas las
      filas de Gerente (antes que la cuenta) y después se busca al Gerente activo en una consulta aparte;
      el rechazo lleva el código «gerente_activo». La restricción ``un_solo_gerente_activo`` queda de
      respaldo: su ``IntegrityError`` se traduce igual, y uno que no se pueda identificar da el código
      «no_se_pudo_reactivar». Nunca un error 500.
    - Postcondición d, SEG-14 y D-22: auditoría con el cambio de estado, sin contraseñas.
    - Postcondición c de USR-MOD-USR y SEG-11 (tarea 06b, D-17): como el restablecimiento, la cuenta sale de su
      grupo de cuentas vinculadas (la baja no la había sacado: regla 2 de USR-BAJ-USR). Orden de los
      bloqueos: el grupo de cuentas, después las filas de Gerente, después la cuenta.
    - D8 y D-43 (MAE-02b): después de eso, ``core.extensiones.aplicar_efectos_de_reactivacion_de_cuenta``. Las apps de
      negocio resuelven y traspasan lo suyo (maestros: la alerta «sin {rol}» y, si es un Agrónomo, D4 de D-41). Sus
      afectados y sus ``datos`` van a la auditoría.
    """
    _exigir_forma_de_acceso(acceso)
    with transaction.atomic():
        cuenta = _bloquear_cuenta_en_alcance(
            actor,
            cuenta_id,
            bloqueo_previo=_bloquear_grupo_de_reactivacion,
            cuida_grupo=True,
        )
        if cuenta.is_active:
            raise ValidationError("La cuenta ya está activa.", code="cuenta_activa")
        if cuenta.rol == Usuario.Rol.GERENTE:
            activo = _gerente_activo()
            if activo is not None:
                raise _error_gerente_activo(activo, reactivando=True)
        cuenta.is_active = True
        temporal = _preparar_acceso(cuenta, acceso)
        try:
            # Savepoint: si una operación simultánea ganó de mano, la base rechaza esta reactivación y
            # se informa el motivo en vez de un error 500.
            with transaction.atomic():
                cuenta.save(
                    update_fields=["is_active", "password", "fecha_contrasena_temporal", "fecha_invitacion"]
                )
        except IntegrityError as error:
            if _nombre_de_restriccion(error) == RESTRICCION_UN_SOLO_GERENTE_ACTIVO:
                raise _error_gerente_activo(reactivando=True) from error
            raise ValidationError(
                "No se pudo reactivar la cuenta. Volvé a intentarlo.", code="no_se_pudo_reactivar"
            ) from error
        # Postcondición c de USR-MOD-USR y SEG-11: la cuenta sale de su grupo de cuentas vinculadas.
        salida = _sacar_del_grupo(cuenta)
        # D-43 y D8: lo que suman las apps de negocio (en maestros, las alertas de los invernaderos a cargo). Corre después
        # de bloquear las cuentas y de sacar a esta de su grupo, y antes de auditar.
        efecto = extensiones.aplicar_efectos_de_reactivacion_de_cuenta(actor, cuenta)
        _auditar_con_salida_del_grupo(
            actor,
            RegistroAuditoria.Accion.REACTIVACION,
            cuenta,
            salida,
            cambios={"estado": {"antes": "inactivo", "despues": "activo"}},
            datos={"acceso": acceso, **efecto.datos},
            otros_afectados=efecto.afectados,
        )
    return _resultado_acceso(cuenta, acceso, temporal, construir_url)


def baja_usuario(actor, cuenta_id):
    """USR-BAJ-USR: da de baja lógica una cuenta activa (la deja inactiva, sin borrarla).

    - Precondiciones a y b y regla 1: ``actor`` es un Gerente activo y la cuenta está activa y dentro
      de su alcance (el Gerente no se da de baja a sí mismo).
    - Postcondición a: la cuenta queda inactiva. Postcondición b: con ``is_active`` en False,
      ``get_user`` de Django deja de devolver la cuenta, así que sus sesiones abiertas se pierden
      en el pedido siguiente.
    - Regla 1, D-16: el Administrador da de baja la cuenta del Gerente y las de los Administradores,
      incluida la suya.
    - Precondición c y SEG-15: si la cuenta es de un Administrador, tiene que quedar al menos otro activo.
      Se bloquean todos los Administradores activos (antes que la cuenta), se verifica que ``actor``
      siga activo y se cuentan los que quedan en una consulta aparte; si no queda ninguno, el rechazo
      lleva el código «ultimo_administrador». No hay restricción de la base que lo respalde: el bloqueo es
      lo único que lo garantiza.
    - Postcondición d, SEG-14 y D-22: auditoría con el cambio de estado, en la misma transacción.

    - Regla 2 (tarea 06b, D-17): la baja no afecta a las cuentas vinculadas; la cuenta sigue en su grupo,
      aunque nadie pueda pasar a ella mientras esté inactiva (SEG-09). Este servicio no toca el grupo.

    - Postcondición e y regla 4, MD-61 y D-43 (MAE-02b): después de guardar la cuenta inactiva y antes de auditar,
      ``core.extensiones.aplicar_efectos_de_baja_de_cuenta`` (maestros: la alerta «sin {rol}» de cada invernadero a
      cargo y, si es un Agrónomo, sus alertas pasan al Gerente). Corre con la cuenta ya bloqueada: orden cuenta →
      invernaderos → alertas (D-40). Los afectados y los ``datos`` que suma van a la auditoría. La regla 4 informa lo
      asignado en la ventana (``core.extensiones.asignaciones_de_cuenta``).

    - Postcondición c y regla 3 (NOT-01, D-42): los pendientes del Gerente que quedan esperando los muestra la ventana de baja
      (``core.views._gestionar_cuenta``, con ``notificaciones.pendientes_del_gerente``); no es una notificación y la baja
      no se bloquea por ellos.

    Pendiente: postcondiciones f y g (pedidos y entregas) y lo de la regla 4 que no sea de
    invernaderos (órdenes, contratos, entregas y pedidos).
    """
    with transaction.atomic():
        cuenta = _bloquear_cuenta_en_alcance(actor, cuenta_id, bloqueo_previo=_bloquear_grupo_de_baja)
        if not cuenta.is_active:
            raise ValidationError("La cuenta ya está inactiva.", code="cuenta_inactiva")
        if cuenta.is_superuser and not _hay_otro_administrador_activo(cuenta):
            raise ValidationError(
                "No se puede dar de baja: es el último Administrador activo.",
                code="ultimo_administrador",
            )
        cuenta.is_active = False
        cuenta.save(update_fields=["is_active"])
        efecto = extensiones.aplicar_efectos_de_baja_de_cuenta(actor, cuenta)
        detalle = {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}}
        if efecto.datos:
            detalle["datos"] = efecto.datos
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA,
            afectados=[cuenta, *efecto.afectados],
            detalle=detalle,
        )
    return cuenta


# ---- Cuentas vinculadas (USR-VNC-CTA y SEG-09, tarea 06b) ----
# El dueño de una cuenta la agrupa con las suyas en un grupo (D-17). Orden de los bloqueos de todas las
# operaciones que cambian quién está en un grupo (ampliación de D-30): 1) las filas de ``GrupoCuentas``, en
# orden de id; 2) los invariantes, si corresponde; 3) que quien actúa siga activo; 4) las cuentas, en orden
# de id. Después de bloquear se vuelve a leer el estado y, si cambió lo que importa, la operación se rechaza
# («cambio_simultaneo») en vez de reintentar: reintentar tomaría bloqueos fuera de orden.


def _exigir_titular_activo(actor):
    """Precondición a de USR-VNC-CTA: ``actor`` es una cuenta activa con un rol del dominio. El Administrador
    no tiene vínculos (regla 5): ``PermissionDenied`` (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in tuple(Usuario.Rol):
        raise PermissionDenied(MENSAJE_SIN_VINCULOS)


def _es_vinculable(cuenta):
    """Reglas 4 y 5 de USR-VNC-CTA y SEG-09: la cuenta está activa, no tiene contraseña temporal (vencida o
    no) y no es de un Administrador. Es lo que se exige para vincularla y para pasar a ella."""
    return cuenta.is_active and not cuenta.tiene_contrasena_temporal and not cuenta.is_superuser


def _bloquear_para_vincular(actor, grupos_ids, cuentas_ids):
    """Los bloqueos de ``vincular_cuenta``, en el orden de D-30 ampliado: los grupos (``grupos_ids``), que
    ``actor`` siga activo y las cuentas (``cuentas_ids``) en orden de id.

    Es una función aparte para que la prueba de «la contraseña cambió entre la verificación y el bloqueo»
    pueda ejecutar un cambio justo antes de bloquear (ver el encabezado de ``test_usr_vnc_cta.py``).
    """
    _bloquear_grupos(grupos_ids)
    _exigir_actor_sigue_activo(actor)
    list(
        Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas_ids).order_by("pk")
    )


def _unir_cuentas(propia, otra):
    """Deja a ``propia`` y ``otra`` en un mismo grupo (postcondición a de USR-VNC-CTA, regla 3). Devuelve
    ``(grupo_id, grupo_unido, afectados)``: el grupo en el que quedan, el grupo que se absorbió (o ``None``) y
    las cuentas que cambiaron de grupo o se vincularon.

    Sin grupos, se crea uno con las dos. Si solo una tiene grupo, la otra se suma. Si cada una tiene el suyo,
    los dos se unen en el de menor id y el otro se borra. Hay que llamarlo con los grupos y las cuentas ya
    bloqueados, dentro de ``transaction.atomic()``.
    """
    propio, ajeno = propia.grupo_id, otra.grupo_id
    if propio is None and ajeno is None:
        grupo = GrupoCuentas.objects.create()
        Usuario.objects.filter(pk__in=[propia.pk, otra.pk]).update(grupo=grupo)
        return grupo.pk, None, [propia, otra]
    if ajeno is None:
        Usuario.objects.filter(pk=otra.pk).update(grupo_id=propio)
        return propio, None, [propia, otra]
    if propio is None:
        Usuario.objects.filter(pk=propia.pk).update(grupo_id=ajeno)
        return ajeno, None, [propia, otra]
    conservado, absorbido = sorted((propio, ajeno))
    movidas = list(
        Usuario.objects.select_for_update(no_key=True).filter(grupo_id=absorbido).order_by("pk")
    )
    Usuario.objects.filter(grupo_id=absorbido).update(grupo_id=conservado)
    GrupoCuentas.objects.filter(pk=absorbido).delete()
    afectados = [propia, otra] + [c for c in movidas if c.pk not in (propia.pk, otra.pk)]
    return conservado, absorbido, afectados


def vincular_cuenta(actor, email, contrasena):
    """USR-VNC-CTA: vincula la cuenta de ``actor`` con otra, cuyo email y contraseña conoce. Devuelve la otra
    cuenta.

    - Precondición a y regla 5: ``actor`` es una cuenta activa con rol del dominio; el Administrador no
      vincula (``PermissionDenied``, SEG-13).
    - Regla 1: se pide el email y la contraseña de la otra cuenta (error por campo si falta alguno).
    - Reglas 4 y 7: la otra cuenta no es la propia («misma_cuenta») ni ya está en el grupo del actor
      («ya_vinculada»); esos dos mensajes solo se dan para la cuenta propia y las de su grupo, que la persona
      ya conoce: no revelan nada de una cuenta ajena. Una cuenta inexistente, con la contraseña incorrecta,
      inactiva, con contraseña temporal (vencida o no) o de Administrador recibe el mismo mensaje genérico
      («no_se_pudo_vincular», SEG-06), con el mismo cálculo de contraseña exista o no la cuenta (como
      ``BackendEmail``).
    - Reglas 2 y 3 y postcondición a: las cuentas quedan en un mismo grupo (``_unir_cuentas``).
    - Postcondición c, SEG-14 y D-22: auditoría en la misma transacción, sin contraseñas.

    Orden de las verificaciones (D-32). Antes de bloquear: lo anterior, incluida la contraseña de la otra
    cuenta, que se verifica fuera de todo bloqueo porque calcular su resumen es lento; se guarda el resumen
    leído en ese momento. Después de bloquear, con todo releído: (a) la otra cuenta sigue siendo vinculable y
    su resumen de contraseña es el mismo (si su dueño la cambió en el intervalo, la contraseña indicada ya no
    es la de la cuenta) → «no_se_pudo_vincular»; (b) recién entonces, si cambió el grupo de alguna de las dos
    cuentas → «cambio_simultaneo». (a) va antes que (b) porque un restablecimiento que disuelve el grupo de la
    otra cuenta también le cambia el grupo, y ahí corresponde el mensaje genérico.
    """
    _exigir_titular_activo(actor)
    email = Usuario.objects.normalize_email(email)
    contrasena = contrasena or ""
    errores = {}
    if not email:
        errores["email"] = [
            ValidationError("Ingresá el email de la otra cuenta.", code="required")
        ]
    if not contrasena:
        errores["contrasena"] = [
            ValidationError("Ingresá la contraseña de la otra cuenta.", code="required")
        ]
    if errores:
        raise ValidationError(errores)

    # Se leen las dos cuentas de la base: la instancia de ``actor`` viene de la sesión y puede estar vieja.
    propia = Usuario.objects.get(pk=actor.pk)
    otra = Usuario.objects.filter(email=email).first()
    if otra is not None:
        if otra.pk == propia.pk:
            raise _error_general(MENSAJE_MISMA_CUENTA, "misma_cuenta")
        if propia.grupo_id is not None and otra.grupo_id == propia.grupo_id:
            raise _error_general(MENSAJE_YA_VINCULADA, "ya_vinculada")

    if otra is None:
        # Mismo trabajo de resumen que con una cuenta real, para que el tiempo de respuesta no revele si el
        # email existe (como BackendEmail).
        Usuario().set_password(contrasena)
        raise _error_general(MENSAJE_NO_SE_PUDO_VINCULAR, "no_se_pudo_vincular")
    contrasena_correcta = otra.check_password(contrasena)
    if not contrasena_correcta or not _es_vinculable(otra):
        raise _error_general(MENSAJE_NO_SE_PUDO_VINCULAR, "no_se_pudo_vincular")
    # Después de check_password, que puede actualizar el resumen si el algoritmo quedó viejo: se compara con
    # el que quedó guardado.
    resumen = otra.password

    grupos = sorted({g for g in (propia.grupo_id, otra.grupo_id) if g is not None})
    with transaction.atomic():
        _bloquear_para_vincular(actor, grupos, [propia.pk, otra.pk])
        propia_ahora = Usuario.objects.get(pk=propia.pk)
        otra_ahora = Usuario.objects.get(pk=otra.pk)
        if not _es_vinculable(otra_ahora) or otra_ahora.password != resumen:
            raise _error_general(MENSAJE_NO_SE_PUDO_VINCULAR, "no_se_pudo_vincular")
        if propia_ahora.grupo_id != propia.grupo_id or otra_ahora.grupo_id != otra.grupo_id:
            raise _error_cambio_simultaneo()
        try:
            # Savepoint: si la base rechaza la escritura (un grupo que ya no existe), se informa como cambio
            # simultáneo en vez de un error 500.
            with transaction.atomic():
                grupo_id, grupo_unido, afectados = _unir_cuentas(propia_ahora, otra_ahora)
        except IntegrityError as error:
            raise _error_cambio_simultaneo() from error
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.VINCULACION,
            afectados=afectados,
            detalle={
                "datos": {
                    "grupo": referencia_a_grupo(grupo_id),
                    "grupo_unido": None if grupo_unido is None else referencia_a_grupo(grupo_unido),
                }
            },
        )
    otra_ahora.grupo_id = grupo_id
    return otra_ahora


def _bloquear_para_desvincular(actor, grupo_id):
    """Los bloqueos de ``desvincular_cuenta``: el grupo, que ``actor`` siga activo y todas las cuentas del
    grupo, en orden de id. Devuelve esas cuentas, ya bloqueadas. Mientras se tiene el bloqueo del grupo,
    ninguna otra operación suma ni saca cuentas, así que la lista es la real."""
    _bloquear_grupos([grupo_id])
    _exigir_actor_sigue_activo(actor)
    return list(
        Usuario.objects.select_for_update(no_key=True).filter(grupo_id=grupo_id).order_by("pk")
    )


def desvincular_cuenta(actor, cuenta_id):
    """USR-VNC-CTA: saca del grupo de ``actor`` la cuenta ``cuenta_id``. Devuelve esa cuenta.

    - Precondición a y regla 5: ``actor`` es una cuenta activa con rol del dominio.
    - Precondición c: la cuenta es del mismo grupo que ``actor``. Una cuenta de otro grupo, una sin grupo o
      un id que no existe dan la misma respuesta (``PermissionDenied``): si no, desde Mi perfil cualquier
      cuenta podría probar ids para averiguar cuáles existen (D-32).
    - Regla 8 (D-32, «Salir del grupo»): puede ser cualquier cuenta del grupo, también una inactiva y la
      propia cuenta de ``actor``.
    - Postcondición b: si el grupo queda con una sola cuenta, el grupo deja de existir (``_sacar_del_grupo``).
    - Postcondición c, SEG-14 y D-22: auditoría en la misma transacción, con las cuentas afectadas.

    Si el grupo cambió entre la lectura y el bloqueo y la cuenta o ``actor`` ya no están en él,
    «cambio_simultaneo».
    """
    _exigir_titular_activo(actor)
    propia = Usuario.objects.get(pk=actor.pk)
    objetivo = Usuario.objects.filter(pk=cuenta_id).first()
    if propia.grupo_id is None or objetivo is None or objetivo.grupo_id != propia.grupo_id:
        raise PermissionDenied(MENSAJE_FUERA_DEL_GRUPO)
    grupo_id = propia.grupo_id

    with transaction.atomic():
        miembros = _bloquear_para_desvincular(actor, grupo_id)
        ids = {m.pk for m in miembros}
        if propia.pk not in ids or objetivo.pk not in ids:
            raise _error_cambio_simultaneo()
        saliente = next(m for m in miembros if m.pk == objetivo.pk)
        salida = _sacar_del_grupo(saliente, [m for m in miembros if m.pk != saliente.pk])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.DESVINCULACION,
            afectados=[saliente, *salida.otras_afectadas],
            detalle={"datos": {"grupo": referencia_a_grupo(grupo_id), "disuelto": salida.disuelto}},
        )
    return saliente


def cuenta_para_cambiar(actor, cuenta_id):
    """SEG-09: devuelve la cuenta a la que ``actor`` puede pasar sin volver a identificarse; la vista hace
    ``login()`` con ella.

    - Tiene que ser otra cuenta del grupo de ``actor``. Una de otro grupo, una sin grupo, la propia o un id
      que no existe dan ``PermissionDenied``, igual que al desvincular (D-32).
    - Antes de cambiar se verifica que siga activa y sin contraseña temporal, y que no sea de
      Administrador: si no, «cuenta_no_disponible». La baja no saca la cuenta del grupo (regla 2 de
      USR-BAJ-USR) y puede darse después de abrir el menú; con una temporal, la pantalla «Elegí tu
      contraseña» no pide la actual, así que quien pasara podría elegir la contraseña de una cuenta que
      alguien restableció para recuperarla (SEG-11 la saca del grupo; esto es el respaldo).
    - Regla del cambio de sesión: no bloquea nada. ``login()`` guarda el resumen de contraseña de la cuenta
      que se devuelve; si después se la restablece o se la da de baja, Django cierra esa sesión.
    - SEG-14: el cambio de cuenta no se audita.
    """
    _exigir_titular_activo(actor)
    propia = Usuario.objects.get(pk=actor.pk)
    destino = Usuario.objects.filter(pk=cuenta_id).first()
    if (
        propia.grupo_id is None
        or destino is None
        or destino.pk == propia.pk
        or destino.grupo_id != propia.grupo_id
    ):
        raise PermissionDenied(MENSAJE_FUERA_DEL_GRUPO)
    if not _es_vinculable(destino):
        raise _error_general(MENSAJE_CUENTA_NO_DISPONIBLE, "cuenta_no_disponible")
    return destino


def cuentas_vinculadas(cuenta, actor=None):
    """Las OTRAS cuentas del grupo de ``cuenta``, como lista ordenada (por rol, apellido, nombre y email), para
    Mi perfil, el menú de cuenta y la ficha de quien gestiona (USR-GST-PRF regla 1, USR-CNS-USR regla 3, USR-MOD-USR
    regla 7). Es de solo lectura (SEG-14).

    Una cuenta sin grupo (también la de un Administrador, regla 5) devuelve ``[]`` sin consultar la base: el menú
    de cuenta lo pregunta en cada pantalla. Cada cuenta lleva:

    - ``se_puede_pasar``: SEG-09, activa, sin contraseña temporal y no Administrador (``_es_vinculable``). Las
      pantallas ofrecen «Cambiar» solo donde ``cuenta_para_cambiar`` lo aceptaría.
    - ``en_alcance``, solo si se indica ``actor`` (quien gestiona la cuenta que se mira): si la cuenta está
      dentro de lo que ``actor`` gestiona (``UsuarioQuerySet.en_alcance_de``, D-28). La ficha enlaza a la ficha
      de la cuenta vinculada solo si lo está; si no, mostrar el enlace llevaría a un 403.
    """
    if cuenta.grupo_id is None:
        return []
    otras = list(
        Usuario.objects.filter(grupo_id=cuenta.grupo_id)
        .exclude(pk=cuenta.pk)
        .order_by("rol", "last_name", "first_name", "email")
    )
    for otra in otras:
        otra.se_puede_pasar = _es_vinculable(otra)
    if actor is not None:
        en_alcance = set(
            Usuario.objects.en_alcance_de(actor)
            .filter(pk__in=[otra.pk for otra in otras])
            .values_list("pk", flat=True)
        )
        for otra in otras:
            otra.en_alcance = otra.pk in en_alcance
    return otras


def obtener_cuenta_del_grupo(actor, cuenta_id):
    """La cuenta ``cuenta_id`` si es la propia cuenta de ``actor`` o una de su grupo (precondición c y regla 8
    de USR-VNC-CTA); la ventana de desvincular y de «Salir del grupo» la usa para mostrar de qué cuenta se
    trata. Cualquier otra, una sin grupo o un id que no existe, ``PermissionDenied`` con la misma respuesta:
    desde Mi perfil cualquier cuenta podría probar ids para averiguar cuáles existen (D-32). Es de solo
    lectura: no bloquea ni audita.
    """
    _exigir_titular_activo(actor)
    propia = Usuario.objects.get(pk=actor.pk)
    if cuenta_id == propia.pk:
        return propia
    cuenta = Usuario.objects.filter(pk=cuenta_id).first()
    if propia.grupo_id is None or cuenta is None or cuenta.grupo_id != propia.grupo_id:
        raise PermissionDenied(MENSAJE_FUERA_DEL_GRUPO)
    return cuenta


# ---- Recuperar contraseña por correo (USR-RCP-CTR y SEG-12, tarea 08, D-33 y D-34) ----
# Se apoya en el generador de tokens de Django (``default_token_generator``): firma el id, el resumen de la contraseña,
# el último inicio de sesión y la hora, y vence a los ``PASSWORD_RESET_TIMEOUT`` segundos (3600). Como firma el
# resumen de la contraseña, el enlace deja de servir en cuanto se usa. La lógica de negocio y la auditoría están
# acá; las vistas solo guardan el token en la sesión y renderizan.

MENSAJE_CORREO_NO_CONFIGURADO = (
    "La recuperación por correo no está disponible. Pedile a quien gestiona tu cuenta que la restablezca."
)
MENSAJE_ENLACE_INVALIDO = "Este enlace no es válido o ya venció. Pedí uno nuevo para elegir una contraseña."
ASUNTO_RECUPERACION = "Recuperá tu contraseña de InfoPonia"


def _exigir_correo_configurado():
    """Precondición a de USR-RCP-CTR y regla 5 (SEG-12): sin el envío de correo configurado el caso de uso no está
    disponible. Lee ``settings.CORREO_CONFIGURADO`` en cada llamada (única fuente de verdad, D-33)."""
    if not settings.CORREO_CONFIGURADO:
        raise ValidationError(MENSAJE_CORREO_NO_CONFIGURADO, code="correo_no_configurado")


def _error_enlace_invalido():
    """Error de un enlace usado, vencido, alterado o de una cuenta que ya no puede recuperar (D-34): siempre el
    mismo, para no revelar cuál fue la causa."""
    return ValidationError(MENSAJE_ENLACE_INVALIDO, code="enlace_invalido")


def _enviar_correo(cuenta, asunto, plantilla, contexto):
    """Envía a ``cuenta`` un correo en texto plano con ``plantilla`` y devuelve True si salió (D-33, D-35).

    Si el envío falla, la falla queda en los registros de errores (``logger.exception``) con el id de la cuenta y
    nunca con el contenido del correo, que lleva un enlace que da acceso a la cuenta (SEG-12, regla 11 de
    USR-ALT-USR); devuelve False y quien llama decide qué ver la persona. Se llama siempre fuera de una transacción:
    un servidor SMTP lento (hasta ``EMAIL_TIMEOUT``) no puede mantener bloqueos tomados (D-14).
    """
    cuerpo = render_to_string(plantilla, {**contexto, "nombre_organizacion": nombre_de_la_organizacion()})
    try:
        send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, [cuenta.email])
    except Exception:
        logger.exception("No se pudo enviar el correo «%s» a la cuenta %s.", asunto, cuenta.pk)
        return False
    return True


def _ruta_del_enlace(nombre_url, cuenta, generador):
    """Ruta (sin dominio) de un enlace con el id de la cuenta y un token de ``generador``. La ruta existe en un solo
    lugar, core/urls.py; la base absoluta la pone quien llama (``construir_url``)."""
    return reverse(
        nombre_url,
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(cuenta.pk)),
            "token": generador.make_token(cuenta),
        },
    )


def pedir_recuperacion(email, construir_url):
    """USR-RCP-CTR: envía a ``email`` un enlace para elegir una contraseña nueva, si hay una cuenta activa con él.

    - Precondición a y regla 5: sin el correo configurado, ``ValidationError`` («correo_no_configurado»).
    - Regla 2 y SEG-12: no devuelve nada, y no hace nada distinto exista o no la cuenta, así que quien llama no
      puede distinguir los casos. Una cuenta inactiva no recibe nada. El email se compara sin distinguir
      mayúsculas (SEG-01). Pueden recuperar las cuentas activas de cualquier rol y los Administradores (D-34),
      también las que tienen una invitación pendiente (SEG-20: el resultado es el mismo que aceptarla).
    - Regla 1: el enlace lleva el id de la cuenta y un token de un solo uso que vence a la hora.
    - SEG-12: si el envío falla, la persona recibe la misma respuesta y la falla queda en los registros de errores
      (``_enviar_correo``), sin el enlace.
    - ``construir_url(ruta)`` convierte la ruta en una URL absoluta (la vista pasa ``request.build_absolute_uri``,
      que da https detrás del proxy de Render); así el servicio no depende del pedido.

    No usa ``transaction.atomic()`` a propósito: no escribe nada en la base ni audita (solo lee y envía), y el envío
    por SMTP no debe hacerse con una transacción abierta (D-14: las notificaciones van fuera de la transacción).
    """
    _exigir_correo_configurado()
    cuenta = Usuario.objects.filter(email__iexact=(email or "").strip(), is_active=True).first()
    if cuenta is None:
        return None
    enlace = construir_url(_ruta_del_enlace("core:recuperacion_enlace", cuenta, default_token_generator))
    _enviar_correo(
        cuenta,
        ASUNTO_RECUPERACION,
        "core/correos/recuperar_contrasena.txt",
        {"nombre": cuenta.first_name, "enlace": enlace},
    )
    return None


def _cuenta_del_token(uidb64, token, generador, exige_invitacion):
    """La cuenta activa de ``uidb64`` si ``token`` es válido para ella con ``generador`` (y, si
    ``exige_invitacion``, si tiene la invitación pendiente); si no, ``None``. Lectura sin bloqueo."""
    try:
        cuenta_id = int(force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        return None
    cuenta = Usuario.objects.filter(pk=cuenta_id, is_active=True).first()
    if cuenta is None or not _enlace_vigente(cuenta, token, generador, exige_invitacion):
        return None
    return cuenta


def _enlace_vigente(cuenta, token, generador, exige_invitacion):
    """True si ``cuenta`` está activa, el token es válido con ``generador`` y, si ``exige_invitacion``, la cuenta
    todavía tiene la invitación pendiente. Es la regla del enlace de un solo uso (D-34, D-35)."""
    if not cuenta.is_active or not generador.check_token(cuenta, token):
        return False
    return cuenta.tiene_invitacion_pendiente or not exige_invitacion


def cuenta_del_enlace(uidb64, token):
    """La cuenta a la que pertenece un enlace de recuperación válido, o ``None`` (D-34).

    Es una lectura, sin bloqueo, para que la vista decida si muestra el formulario o la pantalla de enlace no
    válido. ``None`` si el id no se puede decodificar, la cuenta no existe o está inactiva, o el token no es válido
    (usado, vencido o alterado). No decide el cambio: ``confirmar_recuperacion`` vuelve a validar todo con la cuenta
    bloqueada.
    """
    return _cuenta_del_token(uidb64, token, default_token_generator, exige_invitacion=False)


def cuenta_de_la_invitacion(uidb64, token):
    """La cuenta a la que pertenece un enlace de invitación válido, o ``None`` (SEG-20, D-35). Como
    ``cuenta_del_enlace``, con el generador de la invitación y exigiendo que la invitación siga pendiente."""
    return _cuenta_del_token(uidb64, token, generador_invitacion, exige_invitacion=True)


def _elegir_contrasena_con_enlace(cuenta_id, token, contrasena_nueva, generador, accion, exige_invitacion):
    """La persona elige su contraseña con un enlace de un solo uso que recibió por correo (D-34, D-35). La usan la
    recuperación (USR-RCP-CTR) y la aceptación de la invitación (SEG-20), para que la regla delicada esté en un
    solo lugar.

    - Dentro de ``transaction.atomic()``: se bloquea la cuenta (``FOR NO KEY UPDATE``, D-32) y DESPUÉS de bloquear
      se vuelve a validar el enlace (``_enlace_vigente``). Validar solo antes, o solo en la vista, no alcanza: dos
      pedidos simultáneos con el mismo enlace pasarían los dos; el segundo, que esperó el bloqueo, relee la cuenta
      con el resumen de contraseña nuevo y el token ya no vale («enlace_invalido»).
    - SEG-03: la vacía con el mismo mensaje que ``cambiar_contrasena`` y el formulario; el resto con
      ``validate_password`` (incluida «distinta de la actual»). Los errores van en ``contrasena_nueva``.
    - Guarda la contraseña y deja sin contraseña temporal y sin invitación pendiente (una cuenta nunca tiene las dos
      fechas, D-35). Al cambiar el resumen, Django cierra todas las sesiones de la cuenta. No toca el grupo de
      cuentas vinculadas.
    - Auditoría en la misma transacción con ``accion``; usuario y rol, los de la cuenta afectada (D-22). El detalle
      dice si la contraseña era temporal y si había una invitación pendiente; nunca contraseñas ni el token.
    """
    with transaction.atomic():
        cuenta = (
            Usuario.objects.select_for_update(no_key=True).filter(pk=cuenta_id).first()
            if cuenta_id is not None
            else None
        )
        # Después de bloquear: con la fila releída, el token y el estado de la cuenta son los reales.
        if cuenta is None or not _enlace_vigente(cuenta, token, generador, exige_invitacion):
            raise _error_enlace_invalido()

        if not contrasena_nueva:
            raise ValidationError(
                {"contrasena_nueva": [ValidationError("Ingresá la contraseña nueva.", code="required")]}
            )
        try:
            validate_password(contrasena_nueva, cuenta)
        except ValidationError as error:
            raise ValidationError({"contrasena_nueva": error.error_list}) from error

        detalle = {
            "datos": {
                "era_temporal": cuenta.tiene_contrasena_temporal,
                "invitacion_pendiente": cuenta.tiene_invitacion_pendiente,
            }
        }
        cuenta.set_password(contrasena_nueva)
        cuenta.fecha_contrasena_temporal = None
        cuenta.fecha_invitacion = None
        cuenta.save(update_fields=["password", "fecha_contrasena_temporal", "fecha_invitacion"])
        RegistroAuditoria.objects.registrar(
            usuario=cuenta, accion=accion, afectados=[cuenta], detalle=detalle
        )
    return cuenta


def confirmar_recuperacion(cuenta_id, token, contrasena_nueva):
    """USR-RCP-CTR: la persona elige una contraseña nueva con el enlace de recuperación que recibió por correo.

    - Precondición a y regla 5: sin el correo configurado, ``ValidationError`` («correo_no_configurado»).
    - Regla 1 y SEG-12: enlace de un solo uso, revalidado después de bloquear la cuenta; un enlace usado, vencido,
      alterado o de una cuenta inactiva da «enlace_invalido» (D-34).
    - Regla 4 y SEG-03: política de contraseñas.
    - Postcondiciones a, b y c: contraseña nueva, sin temporal (aunque estuviera vencida) y sin invitación pendiente
      (SEG-20), con las sesiones cerradas. Regla 3: no genera temporal ni toca las cuentas vinculadas.
    - Postcondición d: auditoría con la cuenta afectada. Todo esto lo hace ``_elegir_contrasena_con_enlace``.
    """
    _exigir_correo_configurado()
    return _elegir_contrasena_con_enlace(
        cuenta_id,
        token,
        contrasena_nueva,
        default_token_generator,
        RegistroAuditoria.Accion.RECUPERACION_CONTRASENA,
        exige_invitacion=False,
    )


def confirmar_invitacion(cuenta_id, token, contrasena_nueva):
    """SEG-20: la persona elige su contraseña con el enlace de la invitación y empieza a usar el Sistema (D-35).

    Mismo patrón que la recuperación (``_elegir_contrasena_con_enlace``): enlace de un solo uso revalidado después
    de bloquear la cuenta, que además tiene que seguir con la invitación pendiente; vence a los 7 días
    (``core/tokens.py``); SEG-03; la contraseña elegida no queda temporal; auditoría «aceptacion_invitacion» con la
    cuenta afectada. No exige el correo configurado: aceptar no envía nada, así que una invitación ya enviada se
    puede aceptar aunque el correo deje de estar configurado.
    """
    return _elegir_contrasena_con_enlace(
        cuenta_id,
        token,
        contrasena_nueva,
        generador_invitacion,
        RegistroAuditoria.Accion.ACEPTACION_INVITACION,
        exige_invitacion=True,
    )


# ---- Forma de primer acceso: invitación por correo o contraseña temporal (SEG-04, SEG-20, tarea 08b, D-35) ----

ASUNTO_INVITACION = "Te invitamos a InfoPonia"
MENSAJE_ACCESO_INVALIDO = "Elegí cómo va a acceder la persona: con una invitación por correo o con una contraseña temporal."
MENSAJE_INVITACION_NO_DISPONIBLE = (
    "La invitación por correo no está disponible: el envío de correo no está configurado. "
    "Elegí la contraseña temporal."
)


def acceso_del_pedido(valor):
    """El valor del campo ``acceso`` de un pedido, listo para pasarlo al servicio (D-35).

    Sin el correo configurado la pantalla no ofrece elegir (solo la contraseña temporal), así que un pedido sin
    el campo es la temporal. Con el correo configurado el campo es obligatorio: vacío se pasa tal cual y el servicio
    lo rechaza («acceso_invalido»). Un valor presente (por ejemplo, «invitacion» enviado a mano sin el correo
    configurado) se pasa también tal cual: lo juzga el servicio, no esta función.
    """
    valor = (valor or "").strip()
    if not valor and not settings.CORREO_CONFIGURADO:
        return ACCESO_TEMPORAL
    return valor


def _errores_de_forma_de_acceso(acceso):
    """Errores del campo ``acceso`` (regla 4 y regla 10 de USR-ALT-USR, D-35), o una lista vacía.

    Una forma que no es invitación ni temporal da «acceso_invalido». La invitación sin el correo configurado da
    «correo_no_configurado»: el servidor la rechaza aunque llegue en el pedido, porque la pantalla no la ofrece.
    """
    if acceso not in FORMAS_DE_ACCESO:
        return [ValidationError(MENSAJE_ACCESO_INVALIDO, code="acceso_invalido")]
    if acceso == ACCESO_INVITACION and not settings.CORREO_CONFIGURADO:
        return [ValidationError(MENSAJE_INVITACION_NO_DISPONIBLE, code="correo_no_configurado")]
    return []


def _exigir_forma_de_acceso(acceso):
    """Rechaza la forma de acceso con ``ValidationError`` en el campo ``acceso`` si no es válida (antes de bloquear
    nada: no hace falta mirar la cuenta para saberlo)."""
    errores = _errores_de_forma_de_acceso(acceso)
    if errores:
        raise ValidationError({"acceso": errores})


def _preparar_acceso(cuenta, acceso):
    """Deja en la instancia ``cuenta`` el acceso elegido, sin grabarlo, y devuelve la contraseña temporal o ``None``.

    Con la invitación, la cuenta queda sin contraseña utilizable (la anterior deja de servir y sus sesiones se
    cierran) y sin temporal; con la temporal, sin invitación pendiente. Nunca las dos (D-35)."""
    if acceso == ACCESO_INVITACION:
        cuenta.asignar_invitacion()
        return None
    return cuenta.asignar_contrasena_temporal()


def _resultado_acceso(cuenta, acceso, contrasena_temporal, construir_url):
    """Arma el ``ResultadoAcceso`` y, con la invitación, la envía. Se llama DESPUÉS de confirmar la transacción
    (D-14, D-35): el correo nunca sale para una cuenta que después se deshizo, y un servidor SMTP lento no mantiene
    bloqueos tomados."""
    enviada = False
    if acceso == ACCESO_INVITACION:
        enviada = _enviar_invitacion(cuenta, construir_url)
    return ResultadoAcceso(acceso, contrasena_temporal, enviada)


def _enviar_invitacion(cuenta, construir_url):
    """Envía la invitación a la cuenta (SEG-20, postcondición c de USR-ALT-USR) y devuelve True si salió.

    El correo saluda con el nombre, dice que se le creó una cuenta con su rol, trae el enlace y dice que vence en 7
    días, que sirve una sola vez y que, si no la esperaba, lo ignore. Si falla, regla 11: queda en los registros de
    errores sin el enlace y devuelve False.
    """
    # Se lee de la base para firmar con la fecha de la invitación tal como quedó guardada.
    cuenta = Usuario.objects.get(pk=cuenta.pk)
    enlace = construir_url(_ruta_del_enlace("core:invitacion_enlace", cuenta, generador_invitacion))
    return _enviar_correo(
        cuenta,
        ASUNTO_INVITACION,
        "core/correos/invitacion.txt",
        {"nombre": cuenta.first_name, "rol": _rol_para_el_correo(cuenta), "enlace": enlace},
    )


def _rol_para_el_correo(cuenta):
    """El rol de la cuenta como lo lee la persona: «Administrador» para el Administrador (D-10), el nombre del rol
    para los demás."""
    if cuenta.is_superuser:
        return "Administrador"
    return Usuario.Rol(cuenta.rol).label
