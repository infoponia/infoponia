# Doble candado de ``cargar_demo`` (punto 4 de la decisión de la demo, hoy ``docs/decisiones/D-01-demo.md``). El comando se niega a correr,
# sin escribir nada, salvo que la variable ``INFOPONIA_DEMO`` valga ``1`` y la base conectada se llame exactamente ``infoponia_demo``.
# También se niega si la base ya tiene cuentas con rol (la carga es para una base recién migrada) o si faltan los secretos, que solo
# salen de variables de entorno y nunca se escriben ni se imprimen.

import os

from django.core.management.base import CommandError
from django.db import connection

from core.models import Usuario

VARIABLE_DEL_CANDADO = "INFOPONIA_DEMO"
VARIABLE_DE_LA_CONTRASENA = "INFOPONIA_DEMO_CONTRASENA"
VARIABLE_DEL_CORREO = "INFOPONIA_DEMO_CORREO"
BASE_DE_LA_DEMO = "infoponia_demo"


def nombre_de_la_base():
    """El nombre de la base conectada. Función propia para que las pruebas puedan sustituirla."""
    return connection.settings_dict["NAME"]


def verificar_candado():
    """Los dos candados, y nada más: ``INFOPONIA_DEMO`` vale ``1`` y la base se llama ``infoponia_demo``. Lo usan los comandos de solo lectura
    (``estado_demo``) y, además de otras condiciones, ``cargar_demo``. Solo lee: nunca escribe."""
    if os.environ.get(VARIABLE_DEL_CANDADO) != "1":
        raise CommandError(f"{VARIABLE_DEL_CANDADO} no vale 1: la demo está bloqueada y no se escribió nada.")
    if nombre_de_la_base() != BASE_DE_LA_DEMO:
        raise CommandError(f"La base conectada no se llama «{BASE_DE_LA_DEMO}»: la demo está bloqueada y no se escribió nada.")


def verificar_que_se_puede_cargar():
    """Lanza ``CommandError`` si no se cumplen todas las condiciones de la CARGA; si no, no hace nada. Solo lee: nunca escribe.

    Orden: primero los dos candados (``verificar_candado``), después el estado de la base y al final los secretos.
    """
    verificar_candado()
    # El Administrador (superusuario) no tiene rol: las cuentas con rol son las del dominio (Gerente, Agrónomo, etc.).
    if Usuario.objects.exclude(rol="").exists():
        raise CommandError("La base ya tiene cuentas con rol: la carga es para una base recién migrada y no mezcla datos.")
    for variable in (VARIABLE_DE_LA_CONTRASENA, VARIABLE_DEL_CORREO):
        if not os.environ.get(variable):
            raise CommandError(f"Falta la variable de entorno {variable}: no se escribió nada.")
