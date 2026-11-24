# Puntos de extensión de `contabilidad` para las apps de nivel mayor (regla A4 de D-37; CON-CNS-LGS, «Enlace al origen»). `contabilidad` es de nivel 2 y no
# puede importar las apps que originan los asientos (A1): cada una registra en `AppConfig.ready()` cómo se enlaza su documento y el libro de gestión
# se lo pregunta sin conocerla. Patrón: Variaciones protegidas con Indirección (Larman), el mismo de `core/extensiones.py` y `maestros/extensiones.py`.
#
# CONTRATO: `registrar_enlace_de_origen(tipo, funcion)` con `funcion(origen) -> (texto, url) | None`, solo lectura (no bloquea ni escribe).
# Es idempotente: `ready()` puede correr más de una vez. Las pruebas reemplazan `_ENLACES_DE_ORIGEN` con `mock.patch.object`.

# {valor de OrigenDocumento.Tipo: [funciones]}. Se prueban en orden de registro; gana la primera que devuelve algo.
_ENLACES_DE_ORIGEN = {}


def registrar_enlace_de_origen(tipo, funcion):
    """Registra ``funcion(origen) -> (texto, url) | None`` para los documentos de ese ``tipo`` (valor de `OrigenDocumento.Tipo`). Idempotente."""
    registradas = _ENLACES_DE_ORIGEN.setdefault(tipo, [])
    if funcion not in registradas:
        registradas.append(funcion)
    return funcion


def enlace_de_origen(origen):
    """``(texto, url)`` del documento de origen para la ficha del asiento: el del primer registrante que responde o, sin registrante (o si
    todos devuelven `None`), solo el texto del tipo («Recepción», «Entrega»…) y ``url=None``."""
    for funcion in list(_ENLACES_DE_ORIGEN.get(origen.tipo, [])):
        respuesta = funcion(origen)
        if respuesta is not None:
            return respuesta
    return origen.get_tipo_display(), None
