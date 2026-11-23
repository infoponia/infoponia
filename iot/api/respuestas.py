# Las respuestas JSON de la API del nodo (docs/api/nodo/mensajes.md, sección 0, y respuestas_y_errores.md, sección 3). Toda respuesta trae
# ``version`` y ``servidor_en`` (la hora de InfoPonia al recibir el pedido, en UTC con ``Z``: el nodo la usa para comprobar su reloj). Los errores
# traen ``error`` y ``detalle`` y, en ``mensaje_mal_formado``, ``campo`` e ``indice``. Nada de esto lleva el token.

from datetime import timezone as zona

from django.http import JsonResponse

VERSION = "v1"


def _servidor_en(ahora):
    """La hora de InfoPonia en UTC con ``Z`` y sin fracciones: ``2026-11-21T17:05:00Z``."""
    return ahora.astimezone(zona.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(cuerpo, codigo_http, encabezados=None):
    """Una ``JsonResponse`` con los textos sin escapar (las «» y las tildes tal cual, como en los ejemplos del contrato)."""
    respuesta = JsonResponse(cuerpo, status=codigo_http, json_dumps_params={"ensure_ascii": False})
    for nombre, valor in (encabezados or {}).items():
        respuesta[nombre] = valor
    return respuesta


def respuesta_ok(datos, ahora, codigo_http=200):
    """Una respuesta 200 con ``version`` y ``servidor_en`` primero y después ``datos`` (un ``dict``)."""
    return _json({"version": VERSION, "servidor_en": _servidor_en(ahora)} | datos, codigo_http)


def respuesta_error(codigo_http, error, ahora, detalle, *, encabezados=None, **extra):
    """Una respuesta que no es 200: ``error`` (el código del contrato), ``detalle`` (para la persona que configura el nodo) y ``extra`` (``campo``,
    ``indice``). Las 401 suman ``WWW-Authenticate: Bearer``; el resto de los encabezados (``Allow`` de la 405, ``Retry-After`` de la 429) los pasa
    quien llama en ``encabezados``."""
    cuerpo = {"version": VERSION, "servidor_en": _servidor_en(ahora), "error": error, "detalle": detalle} | extra
    cabeceras = dict(encabezados or {})
    if codigo_http == 401:
        cabeceras["WWW-Authenticate"] = "Bearer"
    return _json(cuerpo, codigo_http, cabeceras)
