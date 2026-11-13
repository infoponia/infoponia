# Fábricas y auxiliares compartidos por las pruebas de core/tests/: crean cuentas con la contraseña de
# prueba y arman estados repetidos (administrador dado de baja, contraseña temporal vencida). Tienen una
# sola firma; el archivo de pruebas que verifica un nombre o apellido concretos lo pasa explícito.

from datetime import timedelta

from django.utils import timezone

from core.models import Capataz, Gerente, Usuario

CLAVE = "clave-segura-123"


def crear_gerente(email="gerente@infoponia.com", activo=True, nombre="Gabriela", apellido="Sosa"):
    """Crea un Gerente con la contraseña de prueba. Solo puede haber uno activo (D-09)."""
    return Gerente.objects.create_user(
        email=email, password=CLAVE, first_name=nombre, last_name=apellido, is_active=activo
    )


def crear_administrador(email="admin@infoponia.com", nombre="Adrián", apellido="Mena"):
    """Crea un Administrador técnico: superusuario sin rol (D-10)."""
    return Usuario.objects.create_superuser(
        email=email, password=CLAVE, first_name=nombre, last_name=apellido
    )


def crear_capataz(email="capataz@infoponia.com", **extra):
    """Crea un Capataz activo con la contraseña de prueba. ``extra`` se pasa a ``create_user`` y puede
    pisar el nombre y el apellido (por defecto «Juan Pérez») o cualquier otro campo (por ejemplo ``is_active``)."""
    datos = {"first_name": "Juan", "last_name": "Pérez", **extra}
    return Capataz.objects.create_user(email=email, password=CLAVE, **datos)


def crear_cuenta(
    clase, email="laura@infoponia.com", activo=True, nombre="Nombre", apellido="Apellido", telefono=""
):
    """Crea una cuenta del rol de ``clase`` con la contraseña de prueba."""
    return clase.objects.create_user(
        email=email,
        password=CLAVE,
        first_name=nombre,
        last_name=apellido,
        telefono=telefono,
        is_active=activo,
    )


def administrador_inactivo(email="admin.anterior@infoponia.com"):
    """Crea un Administrador dado de baja."""
    cuenta = crear_administrador(email=email)
    cuenta.is_active = False
    cuenta.save()
    return cuenta


def dar_temporal_vencida(cuenta):
    """Le da a la cuenta una contraseña temporal generada hace 8 días (ya venció, SEG-04)."""
    cuenta.asignar_contrasena_temporal()
    cuenta.fecha_contrasena_temporal = timezone.now() - timedelta(days=8)
    cuenta.save()
