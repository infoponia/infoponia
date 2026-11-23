# API pública de direcciones de `maestros` (D-58; contrato en docs/api/direcciones.md). Es lo que antes eran funciones privadas
# de ``invernaderos.py``: validar los datos de una dirección, crearla, corregirla en el lugar, pasarla a inactiva y borrarla.
# Estas funciones NO auditan, NO validan el rol y NO notifican (eso es del caso de uso que las llama) y corren dentro de la
# transacción de quien llama. Las usan los invernaderos (D-39) y los clientes de `comercial` (COM-ALT-CLT, regla 6).

import re
from collections import namedtuple

from django.core.exceptions import ValidationError

from maestros.models import Direccion, DireccionRural, DireccionUrbana, Localidad
from maestros.validadores import validar_con_contenido, validar_kilometro, validar_numero_calle

TIPOS_DE_DIRECCION = ("urbana", "rural")

# Lo que devuelve ``validar_direccion``: la zona («urbana» o «rural»), la ``Localidad`` y los ``campos`` ya limpios.
DireccionValidada = namedtuple("DireccionValidada", "zona localidad campos")

# Largo máximo de cada texto (D-39, decisión 6): los de las columnas, para rechazarlo con un error de campo y no con un 500.
LARGOS = {
    "calle": DireccionUrbana._meta.get_field("calle").max_length,
    "numero_calle": DireccionUrbana._meta.get_field("numero_calle").max_length,
    "piso": DireccionUrbana._meta.get_field("piso").max_length,
    "departamento_unidad": DireccionUrbana._meta.get_field("departamento").max_length,
    "barrio": DireccionUrbana._meta.get_field("barrio").max_length,
    "referencias": DireccionUrbana._meta.get_field("referencias").max_length,
    "ruta": DireccionRural._meta.get_field("ruta").max_length,
    "kilometro": DireccionRural._meta.get_field("kilometro").max_length,
    "lote_rural": DireccionRural._meta.get_field("lote").max_length,
}

# Validador de formato o de contenido de cada campo que lo tiene (D-39): el mismo que usa el campo del modelo.
FORMATOS = {
    "numero_calle": validar_numero_calle,
    "kilometro": validar_kilometro,
    "calle": validar_con_contenido,
    "ruta": validar_con_contenido,
    "piso": validar_con_contenido,
    "departamento_unidad": validar_con_contenido,
    "barrio": validar_con_contenido,
    "referencias": validar_con_contenido,
    "lote_rural": validar_con_contenido,
}

# Nombre del atributo del modelo de cada dato cuyo nombre en el servicio es otro (D-39).
ATRIBUTO_DE_LA_DIRECCION = {"departamento_unidad": "departamento", "lote_rural": "lote"}

_CAMPOS_URBANA = ("calle", "numero_calle", "piso", "departamento_unidad", "barrio", "referencias")
_CAMPOS_RURAL = ("ruta", "kilometro", "lote_rural")


def _error(mensaje, codigo):
    """Un error de campo con su código."""
    return [ValidationError(mensaje, code=codigo)]


def _entero_o_none(valor):
    """``valor`` como entero, o ``None`` si falta o no es un número (un id mal formado cuenta como no elegido)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _largo_excedido(campo, texto):
    """Error de campo si ``texto`` supera el largo máximo de ``campo``; si no, ``None``."""
    if len(texto) > LARGOS[campo]:
        return _error(f"Usá como máximo {LARGOS[campo]} caracteres.", "demasiado_largo")
    return None


def _limpiar_direccion(tipo, datos, errores):
    """Regla 2 de PROD-ALT-INV: valida y recorta los datos de la dirección del tipo elegido, y descarta los del otro.
    Devuelve ``{campo: texto}`` solo con los datos del tipo, o ``{}`` si el tipo no es válido."""
    if tipo not in TIPOS_DE_DIRECCION:
        errores["tipo_direccion"] = _error("Elegí si la dirección es urbana o rural.", "tipo_invalido")
        return {}
    if tipo == "urbana":
        obligatorios = {"calle": "Ingresá la calle.", "numero_calle": "Ingresá el número."}
        opcionales = ("piso", "departamento_unidad", "barrio", "referencias")
    else:
        obligatorios = {"ruta": "Ingresá la ruta o el camino.", "kilometro": "Ingresá el kilómetro."}
        opcionales = ("lote_rural",)
    limpios = {}
    for campo in (*obligatorios, *opcionales):
        limpios[campo] = (datos.get(campo) or "").strip()
    for campo, mensaje in obligatorios.items():
        if not limpios[campo]:
            errores[campo] = _error(mensaje, "obligatorio")
    # Formato (D-39): solo de lo que se escribió; vacío ya quedó como «obligatorio».
    for campo, validador in FORMATOS.items():
        if campo in limpios and limpios[campo] and campo not in errores:
            try:
                validador(limpios[campo])
            except ValidationError as error:
                errores[campo] = error.error_list
    for campo, texto in limpios.items():
        if campo not in errores and (error := _largo_excedido(campo, texto)):
            errores[campo] = error
    return limpios


def _buscar_localidad(localidad_id, errores):
    """Regla 3 de PROD-ALT-INV: la localidad es una de las precargadas de Georef (MD-88)."""
    localidad = (
        Localidad.objects.select_related("departamento__provincia").filter(pk=_entero_o_none(localidad_id)).first()
    )
    if localidad is None:
        errores["localidad"] = _error("Elegí la localidad de la lista.", "localidad_invalida")
    return localidad


def validar_direccion(datos):
    """Valida los datos de una dirección sin tocar la base (salvo para leer la localidad) y junta todos los errores.
    ``datos`` lleva ``tipo_direccion``, ``localidad`` (id) y los campos del tipo (docs/api/direcciones.md, «Datos de una
    dirección»); ``provincia`` y ``departamento`` se ignoran. Devuelve ``DireccionValidada(zona, localidad, campos)`` o lanza
    ``ValidationError`` con un error por campo (``error_dict``)."""
    errores = {}
    tipo = datos.get("tipo_direccion")
    campos = _limpiar_direccion(tipo, datos, errores)
    localidad = _buscar_localidad(datos.get("localidad"), errores)
    if errores:
        raise ValidationError(errores)
    return DireccionValidada(tipo, localidad, campos)


def crear_direccion(validada):
    """Crea la dirección (urbana o rural) activa y devuelve la hija. ``departamento_unidad`` y ``lote_rural`` evitan chocar con
    otras entidades del glosario (D-39)."""
    campos = validada.campos
    if validada.zona == "urbana":
        return DireccionUrbana.objects.create(
            localidad=validada.localidad,
            calle=campos["calle"],
            numero_calle=campos["numero_calle"],
            piso=campos["piso"],
            departamento=campos["departamento_unidad"],
            barrio=campos["barrio"],
            referencias=campos["referencias"],
        )
    return DireccionRural.objects.create(
        localidad=validada.localidad, ruta=campos["ruta"], kilometro=campos["kilometro"], lote=campos["lote_rural"]
    )


def corregir_direccion(hija, validada):
    """Corrige EN EL LUGAR una dirección de la misma zona (urbana con urbana, rural con rural). Con otra zona lanza
    ``ValueError``: el cambio de zona es otra dirección (docs/api/direcciones.md, «Cambio de zona»). Quien llama decide antes
    que la dirección no está en uso."""
    if validada.zona != hija.ZONA:
        raise ValueError("El cambio de zona es otra dirección: se crea la nueva y se borra la anterior.")
    hija.localidad = validada.localidad
    for campo, valor in validada.campos.items():
        setattr(hija, ATRIBUTO_DE_LA_DIRECCION.get(campo, campo), valor)
    hija.save()
    return hija


def inactivar_direccion(direccion):
    """``estado_direccion = inactivo``. No hace nada si ya lo estaba. Acepta la ``Direccion`` base o una hija."""
    if direccion.estado_direccion != Direccion.Estado.INACTIVO:
        direccion.estado_direccion = Direccion.Estado.INACTIVO
        direccion.save(update_fields=["estado_direccion"])


def borrar_direccion(direccion):
    """Borra la hija y su ``Direccion``. Lanza ``ProtectedError`` si algo la referencia (por eso quien llama borra antes su
    vínculo)."""
    direccion.delete()


def datos_de_la_direccion(hija):
    """Los datos de una dirección (urbana o rural) con los nombres del servicio y ``None`` en los que están vacíos."""
    campos = _CAMPOS_URBANA if hija.ZONA == "urbana" else _CAMPOS_RURAL
    return {campo: getattr(hija, ATRIBUTO_DE_LA_DIRECCION.get(campo, campo)) or None for campo in campos}


def _normalizado(texto):
    """Sin distinguir mayúsculas y con los espacios recortados y unificados (D-58 punto 6)."""
    return re.sub(r"\s+", " ", (texto or "").strip()).lower()


def clave_de_ubicacion(hija):
    """La clave de «dirección idéntica» (D-58 punto 6): la zona, la localidad y los datos de ubicación normalizados (calle,
    número, piso y departamento; o ruta, kilómetro y lote). El barrio y las referencias no cuentan: describen, no ubican."""
    campos = ("calle", "numero_calle", "piso", "departamento_unidad") if hija.ZONA == "urbana" else _CAMPOS_RURAL
    datos = datos_de_la_direccion(hija)
    return (hija.ZONA, hija.localidad_id, *(_normalizado(datos[campo]) for campo in campos))
