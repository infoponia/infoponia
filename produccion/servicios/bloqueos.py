# Ayuda común de los servicios de `produccion` para tomar los bloqueos de las otras apps (docs/patrones/bloqueos.md, sección `produccion`).
# `maestros` e `inventario` rechazan con `ValidationError`; los servicios de `produccion` rechazan con `ErrorDeProduccion` (docs/api/
# produccion.md, sección 1): esta función traduce una a la otra. El orden de los bloqueos lo decide cada servicio.

from django.core.exceptions import ValidationError

from produccion.errores import ErrorDeProduccion


def traducir(funcion, *argumentos, equivalencias=None):
    """Llama a un bloqueo de `maestros` o de `inventario` y traduce su `ValidationError` a `ErrorDeProduccion` con el código equivalente
    (`equivalencias`: `{código de la otra app: (código propio, campo)}`). Cualquier otro rechazo es un `cambio_simultaneo`."""
    try:
        return funcion(*argumentos)
    except ValidationError as error:
        codigo = getattr(error, "code", None) or next(
            (e.code for lista in getattr(error, "error_dict", {}).values() for e in lista), None
        )
        propio, campo = (equivalencias or {}).get(codigo, ("cambio_simultaneo", None))
        raise ErrorDeProduccion(propio, "; ".join(error.messages), campo) from error
