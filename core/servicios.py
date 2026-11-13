# Servicios de core: un caso de uso por función, dentro de transaction.atomic(). Hoy: el cambio de
# contraseña (USR-CMB-CTR), lo que necesita Mi perfil (USR-GST-PRF) y la gestión de cuentas del Gerente y
# del Administrador (USR-CNS-USR, USR-ALT-USR, USR-MOD-USR y USR-BAJ-USR), con los invariantes de SEG-15.
# Las vistas solo validan la entrada y llaman acá.

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404

from core.models import (
    ADMINISTRADOR,
    Agronomo,
    Capataz,
    Gerente,
    RegistroAuditoria,
    Tecnico,
    Transportista,
    Usuario,
    Vendedor,
    rol_de,
)
from core.validadores import validar_telefono

MENSAJE_EMAIL_REPETIDO = "Ya existe una cuenta con ese email."
MENSAJE_FUERA_DE_ALCANCE = "Esa cuenta no está dentro de las que gestionás."
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a la gestión de usuarios."

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


def _exigir_actor_activo(actor, roles):
    """Precondición a de los casos de uso de cuentas: ``actor`` es una cuenta activa con un rol de
    ``roles``. Se rechaza con ``PermissionDenied`` (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in roles:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


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
    """
    list(Usuario.objects.select_for_update().filter(rol=Usuario.Rol.GERENTE).order_by("pk"))


def _bloquear_administradores_activos():
    """SEG-15 y precondición c de USR-BAJ-USR: bloquea todas las filas de Administradores activos, en orden
    de id.

    Lo usa la baja de un Administrador. Una segunda baja simultánea espera acá hasta que la primera
    confirme; cuando sigue, PostgreSQL vuelve a evaluar el filtro sobre las filas bloqueadas, así que la
    cuenta que la primera dio de baja ya no figura, y la cuenta de los que quedan es la real. A diferencia
    del Gerente, no hay una restricción de la base que respalde esta regla (compara varias filas): el
    bloqueo es lo único que la garantiza. El orden fijo evita que dos operaciones se esperen mutuamente.
    """
    list(
        Usuario.objects.select_for_update()
        .filter(is_superuser=True, is_active=True)
        .order_by("pk")
    )


def _bloquear_grupo_de_baja(cuenta):
    """Bloqueo previo de la baja: si la cuenta es de un Administrador, bloquea a todos los activos (SEG-15)."""
    if cuenta.is_superuser:
        _bloquear_administradores_activos()


def _bloquear_grupo_de_reactivacion(cuenta):
    """Bloqueo previo de la reactivación: si la cuenta es de un Gerente, bloquea todas las filas de Gerente
    (regla 5, D-09, SEG-15). Reactivar un Administrador no puede romper ningún invariante."""
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
    Regla 4 (las cuentas vinculadas se mantienen): no aplica hasta que existan las cuentas
    vinculadas (USR-VNC-CTA); este servicio no toca el grupo de cuentas.

    Falla con ``ValidationError`` por campo (``contrasena_actual``, ``contrasena_nueva``) y no
    cambia nada. Si sale bien, deja la instancia ``usuario`` con la contraseña nueva y sin
    temporal (la vista la necesita para conservar la sesión actual, SEG-10) y la devuelve.
    Cerrar las demás sesiones (postcondición c, SEG-10) no requiere código acá: la sesión guarda un
    hash de la contraseña y, al cambiarla, las demás sesiones dejan de ser válidas.
    """
    with transaction.atomic():
        # Se bloquea la fila para que dos cambios simultáneos no se pisen y para decidir el modo
        # con el estado real de la cuenta.
        cuenta = Usuario.objects.select_for_update().get(pk=usuario.pk)
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
            detalle={"era_temporal": era_temporal},
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


def alta_usuario(actor, rol, nombre, apellido, email, telefono=""):
    """USR-ALT-USR: da de alta una cuenta con la contraseña temporal que genera el Sistema.

    Devuelve ``(cuenta, contrasena_temporal)``; la temporal se muestra una sola vez a quien hizo el
    alta (postcondición c) y no se guarda en ningún lado. No recibe contraseña: nadie elige la de
    otra persona (regla 4, SEG-04).

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
    - Postcondiciones a y e (SEG-14, D-22): la cuenta y su registro de auditoría, sin contraseñas,
      se guardan en la misma transacción.

    Pendiente: invernadero del Transportista (R155) y aviso al nuevo Gerente (postcondición d).

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
        # Regla 4, SEG-04 y D-18: la temporal la genera el modelo; acá solo se guarda.
        contrasena_temporal = cuenta.asignar_contrasena_temporal()
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

        # Postcondición e, SEG-14 y D-22: sin ninguna contraseña en el detalle.
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA,
            afectados=[cuenta],
            detalle={"rol": rol, "email": email, "nombre": nombre, "apellido": apellido},
        )
    return cuenta, contrasena_temporal


def _bloquear_cuenta_en_alcance(actor, cuenta_id, bloqueo_previo=None):
    """Cuenta ``cuenta_id`` bloqueada para modificarla, si está dentro del alcance de ``actor``.

    Precondición a (``actor`` es un Gerente o un Administrador activos, D-16) y regla 1 de USR-MOD-USR y
    USR-BAJ-USR. Un id inexistente da ``Http404`` y una cuenta fuera del alcance, ``PermissionDenied``
    (D-28), igual que ``obtener_cuenta``. ``select_for_update()`` (CLAUDE.md) evita que dos operaciones
    simultáneas sobre la misma cuenta se pisen; hay que llamarla dentro de ``transaction.atomic()``.

    Orden de los bloqueos (SEG-15, D-30): primero el grupo de filas que cuida un invariante
    (``bloqueo_previo(cuenta)``: todos los Gerentes, o todos los Administradores activos, en orden de id) y
    recién después la cuenta. Si cada operación bloqueara primero su cuenta y después el grupo, dos
    operaciones sobre cuentas distintas podrían esperarse mutuamente (deadlock). Para saber a qué grupo
    pertenece la cuenta se la lee antes sin bloquear: el rol no cambia (D-11) y el alcance depende solo de
    él. Después de bloquear, se verifica de nuevo que ``actor`` siga activo y se vuelve a leer la cuenta,
    ya bloqueada, con su estado real.
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
    return Usuario.objects.select_for_update().get(pk=cuenta.pk)


def modificar_usuario(actor, cuenta_id, nombre, apellido, email, telefono=""):
    """USR-MOD-USR: actualiza los datos personales de una cuenta y devuelve la cuenta.

    - Precondición a y regla 1: ``actor`` es un Gerente activo y la cuenta está dentro de su alcance.
      Para modificar los datos no se exige que la cuenta esté activa: el caso de uso solo pide el
      alcance y el prototipo (vUsuario, save-user) lo permite.
    - Regla 2 y D-11: no recibe ``rol``; el rol no se modifica.
    - Precondición c y regla 3: el email nuevo no puede ser el de otra cuenta (SEG-01); el de la propia
      cuenta no cuenta como repetido. Cambiarlo no afecta las cuentas vinculadas (tarea 06).
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

        # Solo los campos que cambiaron, como {campo: [antes, después]} para la auditoría.
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
                cambios[clave] = [antes, despues]
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
            detalle=cambios,
        )
    return cuenta


def restablecer_contrasena(actor, cuenta_id):
    """USR-MOD-USR: genera una contraseña temporal nueva para una cuenta activa y la devuelve.

    - Regla 4, SEG-04 y D-18: la genera el Sistema (no recibe contraseña, nadie elige la de otra
      persona), vence a los 7 días y se muestra una sola vez a quien la restablece.
    - Postcondición b y SEG-11: al cambiar el resumen de la contraseña, las sesiones abiertas con la
      cuenta dejan de ser válidas (Django compara ese resumen en cada pedido).
    - Regla 1: el Gerente no restablece su propia contraseña (no está en su alcance).
    - Regla 4: tampoco el Administrador, que sí tiene su cuenta en su alcance: la cambia con USR-CMB-CTR.
      Se rechaza con el código «propia_cuenta».
    - D-28: solo para cuentas activas; una inactiva se reactiva.
    - Postcondición d, SEG-14 y D-22: auditoría sin contraseñas, en la misma transacción.

    Pendiente, tarea 06 (postcondición b y SEG-11): sacar la cuenta de su grupo de cuentas vinculadas.
    """
    with transaction.atomic():
        cuenta = _bloquear_cuenta_en_alcance(actor, cuenta_id)
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
        temporal = cuenta.asignar_contrasena_temporal()
        cuenta.save(update_fields=["password", "fecha_contrasena_temporal"])
        # Tarea 06: acá la cuenta sale de su grupo de cuentas vinculadas (SEG-11).
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.RESTABLECIMIENTO,
            afectados=[cuenta],
        )
    return temporal


def reactivar_usuario(actor, cuenta_id):
    """USR-MOD-USR: reactiva una cuenta inactiva con una contraseña temporal nueva, que devuelve.

    - Postcondición c y regla 6: la cuenta queda activa y su contraseña se restablece como en
      ``restablecer_contrasena`` (SEG-04, SEG-11).
    - D-28: solo para cuentas inactivas.
    - Regla 5, D-09 y SEG-15: solo se reactiva un Gerente si no hay otro activo. Se bloquean todas las
      filas de Gerente (antes que la cuenta) y después se busca al Gerente activo en una consulta aparte;
      el rechazo lleva el código «gerente_activo». La restricción ``un_solo_gerente_activo`` queda de
      respaldo: su ``IntegrityError`` se traduce igual, y uno que no se pueda identificar da el código
      «no_se_pudo_reactivar». Nunca un error 500.
    - Postcondición d, SEG-14 y D-22: auditoría con el cambio de estado, sin contraseñas.

    Pendiente, tarea 06: sacar la cuenta de su grupo de cuentas vinculadas.
    """
    with transaction.atomic():
        cuenta = _bloquear_cuenta_en_alcance(
            actor, cuenta_id, bloqueo_previo=_bloquear_grupo_de_reactivacion
        )
        if cuenta.is_active:
            raise ValidationError("La cuenta ya está activa.", code="cuenta_activa")
        if cuenta.rol == Usuario.Rol.GERENTE:
            activo = _gerente_activo()
            if activo is not None:
                raise _error_gerente_activo(activo, reactivando=True)
        cuenta.is_active = True
        temporal = cuenta.asignar_contrasena_temporal()
        try:
            # Savepoint: si una operación simultánea ganó de mano, la base rechaza esta reactivación y
            # se informa el motivo en vez de un error 500.
            with transaction.atomic():
                cuenta.save(update_fields=["is_active", "password", "fecha_contrasena_temporal"])
        except IntegrityError as error:
            if _nombre_de_restriccion(error) == RESTRICCION_UN_SOLO_GERENTE_ACTIVO:
                raise _error_gerente_activo(reactivando=True) from error
            raise ValidationError(
                "No se pudo reactivar la cuenta. Volvé a intentarlo.", code="no_se_pudo_reactivar"
            ) from error
        # Tarea 06: acá la cuenta sale de su grupo de cuentas vinculadas (SEG-11).
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION,
            afectados=[cuenta],
            detalle={"estado": ["inactivo", "activo"]},
        )
    return temporal


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

    Pendiente: postcondiciones c, e, f y g y regla 4 (pendientes, invernaderos, pedidos y entregas);
    tarea 06: regla 2 (la baja no afecta a las cuentas vinculadas; hoy no hay grupos que afectar).
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
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA,
            afectados=[cuenta],
            detalle={"estado": ["activo", "inactivo"]},
        )
    return cuenta
