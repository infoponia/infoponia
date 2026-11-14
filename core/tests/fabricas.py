# Fábricas y auxiliares compartidos por las pruebas de core/tests/: crean cuentas con la contraseña de
# prueba y arman estados repetidos (administrador dado de baja, contraseña temporal, vencida o no, grupo de
# cuentas vinculadas) y leen el contenido de un registro de auditoría. Tienen una sola firma; el archivo de
# pruebas que verifica un nombre o apellido concretos lo pasa explícito.

import json
from datetime import timedelta

from django.utils import timezone

from core.models import Capataz, Gerente, GrupoCuentas, Usuario

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


def agrupar(*cuentas):
    """Arma un grupo de cuentas vinculadas con ``cuentas`` (D-17) y lo devuelve.

    Escribe directo en la base, sin pasar por ``vincular_cuenta``: las pruebas que necesitan partir de un
    grupo armado no dependen del servicio que verifican otras pruebas. Deja la instancia de cada cuenta con
    su ``grupo`` asignado.
    """
    grupo = GrupoCuentas.objects.create()
    Usuario.objects.filter(pk__in=[cuenta.pk for cuenta in cuentas]).update(grupo=grupo)
    for cuenta in cuentas:
        cuenta.grupo = grupo
    return grupo


def administrador_inactivo(email="admin.anterior@infoponia.com"):
    """Crea un Administrador dado de baja."""
    cuenta = crear_administrador(email=email)
    cuenta.is_active = False
    cuenta.save()
    return cuenta


def dar_contrasena_temporal(usuario, generada_hace=None):
    """Le asigna a la cuenta una contraseña temporal (SEG-04), la guarda y devuelve su texto plano.

    Con ``generada_hace`` (un ``timedelta``) se corre la fecha de generación hacia atrás, para probar el
    vencimiento: a los 7 días ya venció. CAMBIA la contraseña de la cuenta por la temporal; para marcarla como
    temporal sin cambiar la contraseña, ``poner_temporal``.
    """
    temporal = usuario.asignar_contrasena_temporal()
    if generada_hace is not None:
        usuario.fecha_contrasena_temporal = timezone.now() - generada_hace
    usuario.save()
    return temporal


def dar_temporal_vencida(cuenta):
    """Le da a la cuenta una contraseña temporal generada hace 8 días (ya venció, SEG-04)."""
    dar_contrasena_temporal(cuenta, generada_hace=timedelta(days=8))


def poner_temporal(cuenta, hace=timedelta(0)):
    """Marca la contraseña de la cuenta como temporal, generada ``hace`` tiempo, SIN cambiarla: sigue siendo
    ``CLAVE``. Así la contraseña es correcta y lo único que puede hacer fallar al servicio es la temporal.
    Escribe directo en la base y no toca la instancia ``cuenta``. Para una temporal real, con su propio texto,
    ``dar_contrasena_temporal``."""
    Usuario.objects.filter(pk=cuenta.pk).update(fecha_contrasena_temporal=timezone.now() - hace)


def contenido_de_auditoria(registro):
    """Todo lo que guarda un registro de auditoría (cuentas afectadas y detalle), como texto, para buscar
    contraseñas en él (SEG-02, SEG-14)."""
    return json.dumps([registro.afectados, registro.detalle], ensure_ascii=False)
