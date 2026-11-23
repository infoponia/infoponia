# Datos para la verificación a mano (CLAUDE.md, «Datos para la verificación a mano»; docs/patrones/datos_de_verificacion.md).
# ``core`` guarda el REGISTRO de cargadores y la guarda de «solo la base local»; cada app registra el suyo en su
# ``AppConfig.ready()`` (regla A4 de D-37), con el mismo patrón que ``core/procesos.py`` (D-56): una lista de módulo que las
# pruebas reemplazan con ``mock.patch.object`` y un registro idempotente. El comando ``cargar_datos_de_verificacion`` los corre.
#
# CONTRATO de un cargador: ``funcion(contrasena) -> ResumenDeCarga``. Es idempotente (correrlo dos veces no duplica nada) y carga
# SOLO llamando a los servicios de las apps, nunca con inserciones directas, para que queden la auditoría y las reglas como en una
# pantalla real. No borra nada y no toca al Administrador. Nunca imprime ni devuelve la contraseña ni un token.

import os
from collections import namedtuple

from django.conf import settings

# Un cargador registrado: su código (el de ``--solo``), su nombre, su orden y su función.
Cargador = namedtuple("Cargador", "codigo nombre orden funcion")
# Lo que informa un cargador: ``creado`` (lo que cargó en esta corrida), ``cuentas`` («correo · rol») y ``pendiente`` (lo que tiene que
# hacer una persona antes de la corrida siguiente).
ResumenDeCarga = namedtuple("ResumenDeCarga", "creado cuentas pendiente", defaults=((), (), ()))

# Lista de módulo: las pruebas la reemplazan con ``mock.patch.object``.
_CARGADORES = []

# Los hosts que cuentan como «la base local».
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1")


class BaseNoLocal(RuntimeError):
    """El comando se niega a correr: no es una base local de desarrollo."""


def registrar_cargador(codigo, nombre, orden, funcion):
    """Registra un cargador y lo devuelve. Idempotente: un registro idéntico no se duplica. ``RuntimeError`` si el ``codigo`` o el
    ``orden`` ya los usa otro."""
    nuevo = Cargador(codigo, nombre, orden, funcion)
    for existente in _CARGADORES:
        if existente.codigo == codigo:
            if existente == nuevo:
                return existente
            raise RuntimeError(f"El cargador «{codigo}» ya está registrado con otro nombre, otro orden u otra función.")
        if existente.orden == orden:
            raise RuntimeError(f"El orden {orden} ya lo usa el cargador «{existente.codigo}»: no puede usarlo «{codigo}».")
    _CARGADORES.append(nuevo)
    return nuevo


def cargadores():
    """Los cargadores registrados, ordenados por ``orden``."""
    return sorted(_CARGADORES, key=lambda cargador: cargador.orden)


def _variables_de_render():
    """Las variables de entorno que delatan a Render. Su documentación («Default environment variables») dice que ``RENDER`` vale
    siempre ``true`` y que las demás empiezan con ``RENDER_``; ``IS_PULL_REQUEST`` también es de Render y no lleva el prefijo."""
    return sorted(
        nombre for nombre in os.environ if nombre == "RENDER" or nombre.startswith("RENDER_") or nombre == "IS_PULL_REQUEST"
    )


def exigir_base_local():
    """Se niega (``BaseNoLocal``) si ``DEBUG`` está apagado, si la base no es localhost o si hay variables de Render. Se llama ANTES de
    leer o escribir nada. Los mensajes no incluyen la cadena de conexión ni ningún secreto."""
    if not settings.DEBUG:
        raise BaseNoLocal("DEBUG está apagado: este comando solo corre en desarrollo.")
    host = (settings.DATABASES["default"].get("HOST") or "").strip().lower()
    if host not in HOSTS_LOCALES:
        raise BaseNoLocal("La base de datos no es local (localhost): este comando solo corre contra la base de desarrollo.")
    de_render = _variables_de_render()
    if de_render:
        raise BaseNoLocal(f"Hay variables de Render en el entorno ({', '.join(de_render)}): este comando no corre en Render.")


def cargar_datos(contrasena, solo=None):
    """Corre la guarda y después los cargadores en orden; devuelve ``[(Cargador, ResumenDeCarga | None, error | None)]``. Si un cargador
    falla, se informa y los demás siguen. ``solo`` es un código; si no existe, ``ValueError`` con los válidos."""
    exigir_base_local()
    pasos = cargadores()
    if solo is not None:
        pasos = [paso for paso in pasos if paso.codigo == solo]
        if not pasos:
            validos = ", ".join(paso.codigo for paso in cargadores()) or "(ninguno)"
            raise ValueError(f"No hay un cargador «{solo}». Los que hay: {validos}.")
    resultados = []
    for paso in pasos:
        try:
            resultados.append((paso, paso.funcion(contrasena), None))
        except Exception as error:  # un cargador que falla no deja sin correr a los demás
            resultados.append((paso, None, error))
    return resultados
