# Servicios de core: un caso de uso por función, dentro de transaction.atomic(). Hoy: el cambio de
# contraseña (USR-CMB-CTR) y la gestión de usuarios del Gerente (USR-CNS-USR y USR-ALT-USR). Las vistas
# solo validan la entrada y llaman acá.

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404

from core.models import (
    Agronomo,
    Capataz,
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

# Regla 1 de USR-ALT-USR: los roles que da de alta el Gerente, con la clase de cada uno. El Gerente
# (D-09) y el Administrador (SEG-17) no están: no se dan de alta desde las pantallas del Gerente.
CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE = {
    Usuario.Rol.AGRONOMO: Agronomo,
    Usuario.Rol.CAPATAZ: Capataz,
    Usuario.Rol.VENDEDOR: Vendedor,
    Usuario.Rol.TRANSPORTISTA: Transportista,
    Usuario.Rol.TECNICO: Tecnico,
}


def _exigir_gerente_activo(actor):
    """Precondición a de los casos de uso de usuarios: el actor es una cuenta activa de Gerente.

    Pendiente, tarea 05: también el Administrador (D-16). Se rechaza con ``PermissionDenied`` (SEG-13).
    """
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Tu cuenta no tiene acceso a la gestión de usuarios.")


def cambiar_contrasena(usuario, contrasena_nueva, contrasena_actual=None):
    """USR-CMB-CTR: la persona reemplaza la contraseña de su propia cuenta por una nueva.

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

    - Regla 1: solo las cuentas de ``en_alcance_de`` (Agrónomo, Capataz, Vendedor, Transportista
      y Técnico para el Gerente).
    - Regla 2: ``rol`` y ``estado`` (``"activo"`` o ``"inactivo"``) filtran; ``busqueda`` separa
      palabras y exige que la cuenta coincida con todas, cada una en nombre, apellido o email, sin
      distinguir mayúsculas.
    - Regla 4 y SEG-14: la consulta no se audita ni cambia nada.

    Devuelve un QuerySet perezoso de solo lectura: no abre ``transaction.atomic()`` porque no
    escribe y una sola consulta ya es consistente en sí misma.
    """
    _exigir_gerente_activo(actor)
    cuentas = Usuario.objects.en_alcance_de(actor)
    if rol:
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
    sobre una cuenta.
    """
    _exigir_gerente_activo(actor)
    cuenta = Usuario.objects.filter(pk=cuenta_id).first()
    if cuenta is None:
        raise Http404("No existe esa cuenta.")
    if not Usuario.objects.en_alcance_de(actor).filter(pk=cuenta.pk).exists():
        raise PermissionDenied(MENSAJE_FUERA_DE_ALCANCE)
    return cuenta


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


def alta_usuario(actor, rol, nombre, apellido, email, telefono=""):
    """USR-ALT-USR: da de alta una cuenta con la contraseña temporal que genera el Sistema.

    Devuelve ``(cuenta, contrasena_temporal)``; la temporal se muestra una sola vez a quien hizo el
    alta (postcondición c) y no se guarda en ningún lado. No recibe contraseña: nadie elige la de
    otra persona (regla 4, SEG-04).

    - Precondición a: ``actor`` es un Gerente activo. Precondición b y regla 3: email único sin
      distinguir mayúsculas (SEG-01).
    - Regla 1: solo los cinco roles de ``CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE``.
    - Regla 7: nombre, apellido, email y rol obligatorios; el teléfono es opcional.
    - Regla 8: el email de una cuenta inactiva no crea otra (ver ``_error_de_email_repetido``).
    - Regla 9 y D-21/D-28: formato y largo del teléfono.
    - Postcondiciones a y e (SEG-14, D-22): la cuenta y su registro de auditoría, sin contraseñas,
      se guardan en la misma transacción.

    Pendiente, tarea 05: el Administrador da de alta al Gerente (regla 1, regla 2 y precondición c).
    Pendiente: invernadero del Transportista (R155) y aviso al nuevo Gerente (postcondición d).

    Falla con ``ValidationError`` por campo y no crea nada.
    """
    _exigir_gerente_activo(actor)

    nombre = (nombre or "").strip()
    apellido = (apellido or "").strip()
    email = Usuario.objects.normalize_email(email)
    telefono = (telefono or "").strip()
    rol = (str(rol) if rol else "").strip()

    errores = {}
    # Regla 7: obligatorios.
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
    # Regla 1: solo los cinco roles; Gerente y Administrador no se dan de alta acá.
    if not rol:
        errores["rol"] = [ValidationError("Elegí el rol.", code="required")]
    elif rol not in CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE:
        errores["rol"] = [ValidationError("Ese rol no se puede dar de alta acá.", code="rol_invalido")]
    # Regla 9, D-21 y D-28.
    try:
        validar_telefono(telefono)
    except ValidationError as error:
        errores["telefono"] = error.error_list

    with transaction.atomic():
        if "email" not in errores and Usuario.objects.filter(email=email).exists():
            errores["email"] = [_error_de_email_repetido(actor, email)]
        if errores:
            raise ValidationError(errores)

        cuenta = CLASES_DE_ROL_QUE_DA_DE_ALTA_EL_GERENTE[rol](
            email=email, first_name=nombre, last_name=apellido, telefono=telefono, is_active=True
        )
        # Regla 4, SEG-04 y D-18: la temporal la genera el modelo; acá solo se guarda.
        contrasena_temporal = cuenta.asignar_contrasena_temporal()
        try:
            # Savepoint: si dos altas simultáneas usan el mismo email, la base rechaza la segunda
            # y se informa como email repetido en vez de un error 500.
            with transaction.atomic():
                cuenta.save()
        except IntegrityError:
            raise ValidationError(
                {"email": [ValidationError(MENSAJE_EMAIL_REPETIDO, code="email_repetido")]}
            )

        # Postcondición e, SEG-14 y D-22: sin ninguna contraseña en el detalle.
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA,
            afectados=[cuenta],
            detalle={"rol": rol, "email": email, "nombre": nombre, "apellido": apellido},
        )
    return cuenta, contrasena_temporal
