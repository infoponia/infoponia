# Puntos de extensión de `produccion` (COM-02, D-59 punto 3; contrato en docs/api/extensiones_de_produccion.md). `produccion` (nivel 5)
# le pregunta a `comercial` (nivel 6) lo que no puede importar (regla A1 de D-37): las reservas de stock son de `comercial`. Los registra
# `comercial` en `ComercialConfig.ready()` (regla A4). Mismo estilo que `maestros/extensiones.py`: una lista privada por punto, una función
# `registrar_…` que agrega y una función que la usa `produccion`. Sin registrante, cada punto da su resultado neutro.

from collections import namedtuple

from django.core.exceptions import ImproperlyConfigured

# `contrato` es el código visible (`CV-0044`) o `None` en una cosecha sin contrato (COM-04); `lotes` es una lista de
# `(lote_id, cantidad_reservada, cantidad_cosechada)` en orden de id de lote (`cantidad_cosechada` es `None` hasta concretar).
DetalleDeCosecha = namedtuple("DetalleDeCosecha", "contrato fecha_entrega lotes")

# COM-04a (D-64 punto 11): qué botones de `comercial` muestran las pantallas de `produccion`. Cada campo es una URL o `None`.
AccionesDeCosecha = namedtuple("AccionesDeCosecha", "concretar modificar cancelar")
# `planificar_cosecha`: URL o `None`; `merma_en_camara`: URL o `None`. COM-05a2 suma `envasado` con valor por defecto (D-66).
EntradasDeComercial = namedtuple("EntradasDeComercial", "planificar_cosecha merma_en_camara")

_RESERVADO_DE_LOTE = []
_DETALLE_DE_COSECHA = []
_ACCIONES_DE_COSECHA = []
_ENTRADAS_DE_COMERCIAL = []


def registrar_reservado_de_lote(funcion):
    """Registra ``funcion(lote_ids) -> dict[int, int]``: por lote, las plantas reservadas en líneas de reservas «activas» (regla 9 de 8.6).
    Un lote sin reservas puede faltar. A lo sumo un registrante: un segundo lanza ``ImproperlyConfigured``. Corre dentro de la transacción de
    quien llama, con el lote ya bloqueado: el registrante no bloquea."""
    if _RESERVADO_DE_LOTE and funcion not in _RESERVADO_DE_LOTE:
        raise ImproperlyConfigured("`registrar_reservado_de_lote` admite un solo registrante.")
    if funcion not in _RESERVADO_DE_LOTE:
        _RESERVADO_DE_LOTE.append(funcion)
    return funcion


def reservado_de_lotes(lote_ids):
    """``{lote_id: plantas reservadas}`` con TODAS las claves pedidas (0 por defecto). Sin registrante, todo en 0; con una lista vacía,
    ``{}`` sin consultar la base."""
    ids = list(lote_ids)
    if not ids:
        return {}
    reservado = {}
    for funcion in list(_RESERVADO_DE_LOTE):
        reservado = funcion(ids)
    return {i: reservado.get(i, 0) for i in ids}


def registrar_detalle_de_cosecha(funcion):
    """Registra ``funcion(cosecha_ids) -> dict[int, DetalleDeCosecha]``. A lo sumo un registrante. Lo usan desde COM-04 la bandeja del
    Capataz, la lista de órdenes del Agrónomo y el aviso de baja de la cuenta del Capataz; COM-02 lo usa en la alerta de plantas
    comprometidas (condición 1 de la regla 15 de 8.8)."""
    if _DETALLE_DE_COSECHA and funcion not in _DETALLE_DE_COSECHA:
        raise ImproperlyConfigured("`registrar_detalle_de_cosecha` admite un solo registrante.")
    if funcion not in _DETALLE_DE_COSECHA:
        _DETALLE_DE_COSECHA.append(funcion)
    return funcion


def detalle_de_cosechas(cosecha_ids):
    """``{cosecha_id: DetalleDeCosecha}`` de las cosechas pedidas. Sin registrante o con una lista vacía, ``{}`` (sin consultar la base)."""
    ids = list(cosecha_ids)
    if not ids:
        return {}
    detalle = {}
    for funcion in list(_DETALLE_DE_COSECHA):
        detalle = funcion(ids)
    return detalle


def registrar_acciones_de_cosecha(funcion):
    """Registra ``funcion(usuario, cosecha_ids) -> dict[int, AccionesDeCosecha]`` (COM-04a, D-64 punto 11): `concretar` solo para el Capataz
    asignado; `modificar` y `cancelar`, solo para el Agrónomo a cargo; todas `None` si la cosecha ya no está «a realizar». Nunca una URL a un 403.
    A lo sumo un registrante (`comercial`): un segundo lanza ``ImproperlyConfigured``."""
    if _ACCIONES_DE_COSECHA and funcion not in _ACCIONES_DE_COSECHA:
        raise ImproperlyConfigured("`registrar_acciones_de_cosecha` admite un solo registrante.")
    if funcion not in _ACCIONES_DE_COSECHA:
        _ACCIONES_DE_COSECHA.append(funcion)
    return funcion


def acciones_de_cosechas(usuario, cosecha_ids):
    """``{cosecha_id: AccionesDeCosecha}`` de las cosechas pedidas. Sin registrante o con una lista vacía, ``{}`` (sin consultar la base): la
    pantalla no muestra botones."""
    ids = list(cosecha_ids)
    if not ids:
        return {}
    acciones = {}
    for funcion in list(_ACCIONES_DE_COSECHA):
        acciones = funcion(usuario, ids)
    return acciones


def registrar_entradas_de_comercial(funcion):
    """Registra ``funcion(usuario) -> EntradasDeComercial`` (COM-04a, D-64 punto 11): el botón «Planificar cosecha» y la entrada «Pérdida en
    cámara» de la merma. A lo sumo un registrante (`comercial`): un segundo lanza ``ImproperlyConfigured``."""
    if _ENTRADAS_DE_COMERCIAL and funcion not in _ENTRADAS_DE_COMERCIAL:
        raise ImproperlyConfigured("`registrar_entradas_de_comercial` admite un solo registrante.")
    if funcion not in _ENTRADAS_DE_COMERCIAL:
        _ENTRADAS_DE_COMERCIAL.append(funcion)
    return funcion


def entradas_de_comercial(usuario):
    """Las entradas de `comercial` para `usuario`; sin registrante, ninguna (todas `None`)."""
    entradas = EntradasDeComercial(None, None)
    for funcion in list(_ENTRADAS_DE_COMERCIAL):
        entradas = funcion(usuario)
    return entradas
