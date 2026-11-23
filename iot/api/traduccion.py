# Traducción del JSON del nodo a objetos simples (docs/casos_de_uso/iot/entregar_informacion.md, «La API»; docs/api/nodo/mensajes.md y
# respuestas_y_errores.md, secciones 3 y 4b). Verifica SOLO la FORMA: la envoltura de cada mensaje (claves exactas, lista), cada elemento (objeto,
# campos conocidos, ``identificador`` con la forma de la regla 2 de IOT-ALT-HDW, ``valor`` o ``estado`` presente) y el anuncio entero (clase,
# comandos del catálogo, sin repetir identificadores ni comandos, un sensor sin ``comandos``). Las fechas, los valores y el equipo los verifican los
# servicios, porque dependen del sensor. No consulta la base (la lógica no depende del transporte, D-70 punto 4).
#
# Los textos de ``detalle`` son los de la sección 4b del contrato: ``{campo}: {razón}.`` de un mensaje y ``No tiene la forma del contrato: {razón}.``
# de un elemento. Un campo que el contrato no define se rechaza (D-74, punto 7): en un elemento de una lista, ese elemento (``mal_formada``); en el
# objeto de arriba, el mensaje entero (400 ``mensaje_mal_formado``).

import json
from collections import namedtuple
from decimal import Decimal

from iot import catalogo
from iot.validadores import IDENTIFICADOR

# Lo que el servicio recibe de cada mensaje. ``identificador_enviado`` es el que mandó el nodo, tal cual (va en la respuesta); ``identificador`` es el
# mismo recortado, con la forma ya verificada (el servicio lo compara en minúsculas).
LecturaRecibida = namedtuple("LecturaRecibida", "indice identificador_enviado identificador valor medida_en")
EstadoRecibido = namedtuple("EstadoRecibido", "indice identificador_enviado identificador estado informado_en")
EquipoRecibido = namedtuple("EquipoRecibido", "identificador clase comandos")
# Un elemento de una lista que no tiene la forma del contrato: la vista lo responde ``rechazada``/``rechazado`` con este motivo y detalle.
ElementoMalFormado = namedtuple("ElementoMalFormado", "indice identificador_enviado motivo detalle")

CAMPOS_DE_LECTURA = {"identificador", "valor", "medida_en"}
CAMPOS_DE_ESTADO = {"identificador", "estado", "informado_en"}
CAMPOS_DE_EQUIPO = {"identificador", "clase", "comandos"}
CLASES_DE_EQUIPO = ("sensor", "actuador")
MODOS = ("remoto", "local")
# Los códigos del catálogo de comandos (docs/api/nodo/README.md, sección 9): parte del contrato, no se consulta la base.
COMANDOS_DEL_CATALOGO = tuple(catalogo.ESTADO_QUE_DEJA)


class JsonInvalido(Exception):
    """El cuerpo no es un objeto JSON válido en UTF-8 (verificación 9 del contrato: 400 ``json_invalido``)."""


class MensajeMalFormado(Exception):
    """El mensaje entero no tiene la forma del contrato (verificación 10: 400 ``mensaje_mal_formado``). ``campo`` es el del primer error; ``indice``
    solo va si el error es de un elemento del anuncio."""

    def __init__(self, campo, razon, indice=None):
        self.campo = campo
        self.razon = razon
        self.indice = indice
        self.detalle = f"{campo}: {razon}."
        super().__init__(self.detalle)


def _constante_invalida(texto):
    """``NaN``, ``Infinity`` y ``-Infinity`` no son JSON válido (D-74, punto 7)."""
    raise ValueError(f"constante no admitida: {texto}")


def leer_objeto(cuerpo):
    """Verificación 9: ``cuerpo`` (bytes) es JSON válido en UTF-8 y es un objeto. Los decimales se leen como ``Decimal`` (nunca pasan por ``float``) y
    ``NaN`` e ``Infinity`` se rechazan. Lanza ``JsonInvalido``."""
    try:
        objeto = json.loads(cuerpo.decode("utf-8"), parse_float=Decimal, parse_constant=_constante_invalida)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise JsonInvalido("El cuerpo no es un objeto JSON válido en UTF-8.") from None
    if not isinstance(objeto, dict):
        raise JsonInvalido("El cuerpo no es un objeto JSON válido en UTF-8.")
    return objeto


def _verificar_claves(objeto, permitidas, obligatorias, prefijo=""):
    """Verificación 10 de la envoltura: ninguna clave que el contrato no defina (``no existe en este mensaje``) y todas las obligatorias (``falta``)."""
    for clave in objeto:
        if clave not in permitidas:
            raise MensajeMalFormado(f"{prefijo}{clave}", "no existe en este mensaje")
    for clave in obligatorias:
        if clave not in objeto:
            raise MensajeMalFormado(f"{prefijo}{clave}", "falta")


def _lista_de(objeto, clave):
    """La lista ``clave`` de la envoltura, que tiene que ser exactamente la única clave del objeto."""
    _verificar_claves(objeto, {clave}, (clave,))
    lista = objeto[clave]
    if not isinstance(lista, list):
        raise MensajeMalFormado(clave, "tiene que ser una lista")
    return lista


def lista_de_lecturas(objeto):
    """Envoltura de ``POST lecturas``: la lista de ``lecturas``."""
    return _lista_de(objeto, "lecturas")


def lista_de_estados(objeto):
    """Envoltura de ``POST estados``: la lista de ``estados``."""
    return _lista_de(objeto, "estados")


def lista_de_equipos(objeto):
    """Envoltura de ``POST anuncio``: la lista de ``equipos``."""
    return _lista_de(objeto, "equipos")


def traducir_modo(objeto):
    """Envoltura de ``POST modo``: ``{"modo": "remoto" | "local"}``. Otro valor es 400 ``mensaje_mal_formado``. Devuelve el modo."""
    _verificar_claves(objeto, {"modo"}, ("modo",))
    if objeto["modo"] not in MODOS or not isinstance(objeto["modo"], str):
        raise MensajeMalFormado("modo", "tiene que ser «remoto» o «local»")
    return objeto["modo"]


def _identificador_valido(texto):
    """``True`` si ``texto`` (recortado) tiene la forma de la regla 2 de IOT-ALT-HDW: hasta 64 caracteres entre letras, números, ``-``, ``_``, ``.`` y ``/``."""
    return isinstance(texto, str) and IDENTIFICADOR.fullmatch(texto.strip()) is not None


def _identificador_enviado(elemento):
    """El identificador tal cual lo mandó el nodo si es texto; ``None`` si no vino o no era texto (como pide la respuesta)."""
    enviado = elemento.get("identificador") if isinstance(elemento, dict) else None
    return enviado if isinstance(enviado, str) else None


def _mal_formada(indice, elemento, razon):
    """Un ``ElementoMalFormado`` con el texto «No tiene la forma del contrato: {razón}.» (respuestas_y_errores.md, sección 4b)."""
    return ElementoMalFormado(indice, _identificador_enviado(elemento), "mal_formada", f"No tiene la forma del contrato: {razon}.")


def _traducir_elemento(indice, elemento, campos, obligatorio, armar):
    """La verificación de forma de un elemento de lecturas o de estados. Orden: es un objeto, no trae campos desconocidos, trae ``identificador``
    con su forma y trae ``obligatorio`` (``valor`` o ``estado``). Devuelve lo que arma ``armar`` o un ``ElementoMalFormado``."""
    if not isinstance(elemento, dict):
        return _mal_formada(indice, elemento, "no es un objeto")
    for clave in elemento:
        if clave not in campos:
            return _mal_formada(indice, elemento, f"el campo «{clave}» no existe")
    if "identificador" not in elemento:
        return _mal_formada(indice, elemento, "falta «identificador»")
    if not _identificador_valido(elemento["identificador"]):
        return _mal_formada(indice, elemento, "el identificador tiene más de 64 caracteres o caracteres no permitidos")
    if obligatorio not in elemento:
        return _mal_formada(indice, elemento, f"falta «{obligatorio}»")
    return armar(indice, elemento)


def traducir_lecturas(lista):
    """Cada elemento de ``lecturas`` como ``LecturaRecibida`` o ``ElementoMalFormado``, en el mismo orden y con su ``indice`` (desde 0)."""

    def armar(indice, elemento):
        enviado = elemento["identificador"]
        return LecturaRecibida(indice, enviado, enviado.strip(), elemento["valor"], elemento.get("medida_en"))

    return [_traducir_elemento(i, e, CAMPOS_DE_LECTURA, "valor", armar) for i, e in enumerate(lista)]


def traducir_estados(lista):
    """Cada elemento de ``estados`` como ``EstadoRecibido`` o ``ElementoMalFormado``, en el mismo orden y con su ``indice`` (desde 0)."""

    def armar(indice, elemento):
        enviado = elemento["identificador"]
        return EstadoRecibido(indice, enviado, enviado.strip(), elemento["estado"], elemento.get("informado_en"))

    return [_traducir_elemento(i, e, CAMPOS_DE_ESTADO, "estado", armar) for i, e in enumerate(lista)]


def traducir_anuncio(lista):
    """Los equipos del anuncio como ``EquipoRecibido``. Se procesa ENTERO O NADA: el primer error de cualquier equipo (clase desconocida, comando fuera
    del catálogo, identificador repetido o mal formado, un sensor con ``comandos``) rechaza el mensaje con 400 ``mensaje_mal_formado``, con el
    ``indice`` y el ``campo`` (``equipos[<i>].<campo>``). Lanza ``MensajeMalFormado``."""
    equipos, vistos = [], set()
    for indice, equipo in enumerate(lista):
        base = f"equipos[{indice}]"

        def error(campo, razon, base=base, indice=indice):
            return MensajeMalFormado(f"{base}.{campo}" if campo else base, razon, indice)

        if not isinstance(equipo, dict):
            raise error("", "tiene que ser un objeto")
        for clave in equipo:
            if clave not in CAMPOS_DE_EQUIPO:
                raise error(clave, "no existe en este mensaje")
        if "identificador" not in equipo:
            raise error("identificador", "falta")
        if not _identificador_valido(equipo["identificador"]):
            raise error("identificador", "el identificador tiene más de 64 caracteres o caracteres no permitidos")
        identificador = equipo["identificador"].strip()
        if identificador.lower() in vistos:
            raise error("identificador", f"el identificador «{identificador}» se repite en el anuncio")
        vistos.add(identificador.lower())
        if "clase" not in equipo:
            raise error("clase", "falta")
        if equipo["clase"] not in CLASES_DE_EQUIPO or not isinstance(equipo["clase"], str):
            raise error("clase", "tiene que ser «sensor» o «actuador»")
        if equipo["clase"] == "sensor":
            if "comandos" in equipo:
                raise error("comandos", "un sensor no lleva comandos")
            equipos.append(EquipoRecibido(identificador, "sensor", ()))
            continue
        if "comandos" not in equipo:
            raise error("comandos", "falta")
        if not isinstance(equipo["comandos"], list):
            raise error("comandos", "tiene que ser una lista")
        comandos = []
        for comando in equipo["comandos"]:
            if comando not in COMANDOS_DEL_CATALOGO or not isinstance(comando, str):
                raise error("comandos", f"«{comando}» no está en el catálogo de comandos")
            if comando in comandos:
                raise error("comandos", f"el comando «{comando}» se repite")
            comandos.append(comando)
        equipos.append(EquipoRecibido(identificador, "actuador", tuple(comandos)))
    return equipos
