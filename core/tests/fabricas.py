# Fábricas y auxiliares compartidos por las pruebas de core/tests/: crean cuentas con la contraseña de
# prueba y arman estados repetidos (administrador dado de baja, contraseña temporal, vencida o no, grupo de
# cuentas vinculadas, invitación pendiente) y leen el contenido de un registro de auditoría. También los auxiliares de
# correo que usan varios archivos (backend que falla, URL absoluta de prueba, comparación sin el token CSRF). Tienen una sola firma; el archivo de
# pruebas que verifica un nombre o apellido concretos lo pasa explícito.

import importlib
import json
import re
from datetime import timedelta
from smtplib import SMTPException

from django.core.mail.backends.base import BaseEmailBackend
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


def dar_invitacion(cuenta, hace=None):
    """Le deja a la cuenta una invitación pendiente (SEG-20, D-35): sin contraseña utilizable y con la fecha de la
    invitación, corrida ``hace`` (un ``timedelta``) hacia atrás si se indica. La graba y devuelve la cuenta."""
    cuenta.asignar_invitacion()
    if hace is not None:
        cuenta.fecha_invitacion = timezone.now() - hace
    cuenta.save()
    return cuenta


def token_de_invitacion(cuenta):
    """Token de invitación de la cuenta (D-35). Importa ``core.tokens`` al llamarla, para que mientras no exista
    falle cada prueba por separado y no la importación del archivo."""
    return importlib.import_module("core.tokens").generador_invitacion.make_token(cuenta)


def invitacion_valida(cuenta, token):
    """True si ``token`` es una invitación válida para la cuenta (con su estado actual en la base)."""
    cuenta = Usuario.objects.get(pk=cuenta.pk)
    return importlib.import_module("core.tokens").generador_invitacion.check_token(cuenta, token)


# Base de los enlaces en las pruebas de servicio: la vista pasa ``request.build_absolute_uri``; acá se simula.
BASE = "https://infoponia.test"
PATRON_INVITACION = re.compile(re.escape(BASE) + r"/invitacion/([\w-]+)/([\w-]+)/")


def construir_url(ruta):
    """Hace las veces de ``request.build_absolute_uri``: devuelve la ruta como URL absoluta."""
    return BASE + ruta


def sin_csrf(contenido):
    """El contenido de una respuesta sin el token CSRF, que cambia en cada pedido: sirve para comparar si dos
    pantallas son la misma."""
    return re.sub(rb'"X-CSRFToken": "[^"]*"', b'"X-CSRFToken": ""', contenido)


class BackendQueFalla(BaseEmailBackend):
    """Backend de correo que simula un servidor SMTP caído (SEG-12 y regla 11 de USR-ALT-USR: el envío falla
    estando configurado). Se usa con ``override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)``."""

    def send_messages(self, email_messages):
        raise SMTPException("El servidor de correo no responde.")


BACKEND_QUE_FALLA = "core.tests.fabricas.BackendQueFalla"
