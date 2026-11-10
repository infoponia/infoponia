# Servicios de core: un caso de uso por función, dentro de transaction.atomic(). Por ahora, el cambio
# de contraseña (USR-CMB-CTR). Las vistas solo validan la entrada y llaman acá.

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import RegistroAuditoria, Usuario


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
