# Módulo de imágenes de InfoPonia (USR-07, D-106 puntos 5 a 8): valida, procesa y guarda la foto de perfil (cuadrada, 256 px) y el
# logo de la organización (sin recortar, 512 px). Es el único lugar que abre una imagen subida (la parte de seguridad no se
# repite): tope de 5 MB antes de abrirla, formato real (JPG, PNG o WebP; ni GIF ni SVG), límite propio de píxeles, orientación EXIF
# corregida, recorte cuadrado elegido por la persona (o central), y salida en WebP sin metadatos, con nombre aleatorio (uuid4). Vive en ``core`` (nivel 1, D-37): ``maestros`` lo usa.

import logging
import math
import re
import uuid
import warnings
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# D-106 punto 5: tope del archivo subido, que se verifica antes de abrir la imagen con Pillow.
TAMANO_MAXIMO = 5 * 1024 * 1024
# Precisión de D-106 (límite propio): más estricto que el de Pillow (unos 89 millones). Un archivo liviano puede declarar
# dimensiones enormes y ocupar mucha memoria al decodificarlo; se decide con la cabecera, antes de decodificar.
LIMITE_DE_PIXELES = 40_000_000
# D-106 punto 5: solo estos formatos (el real, no el de la extensión). Un GIF o un SVG no entran.
FORMATOS_ADMITIDOS = ("JPEG", "PNG", "WEBP")
CALIDAD_WEBP = 85

MENSAJE_PESADA = "La imagen pesa más de 5 MB. Elegí una más liviana."
MENSAJE_NO_VALIDA = "No se pudo abrir ese archivo como imagen. Probá con una foto en formato JPG, PNG o WebP."
MENSAJE_FORMATO = "Solo se aceptan imágenes JPG, PNG o WebP."
MENSAJE_ENORME = "La imagen tiene demasiados píxeles. Elegí una más chica."
# Editor de encuadre de la foto (USR-07, precisión de D-106): mínimo del recorte elegido y mensajes de sus errores.
LADO_MINIMO_DEL_RECORTE = 64
MENSAJE_IMAGEN_CHICA = "La foto es demasiado chica: tiene que medir al menos {lado} px de lado."
MENSAJE_RECORTE_INCOMPLETO = "Faltan datos del encuadre. Volvé a encuadrar la foto."
MENSAJE_RECORTE_NO_NUMERICO = "Los datos del encuadre no son números enteros. Volvé a encuadrar la foto."
MENSAJE_RECORTE_CHICO = "El encuadre es demasiado chico. Acercate menos a la foto."
MENSAJE_RECORTE_AFUERA = "El encuadre tiene que quedar adentro de la imagen. Volvé a encuadrar la foto."
MENSAJE_RECORTE_MAYOR = "El encuadre es más grande que la imagen. Volvé a encuadrar la foto."


def _error(mensaje, codigo):
    """Un ``ValidationError`` con ``mensaje`` y ``codigo``."""
    return ValidationError(mensaje, code=codigo)


def _leer(archivo):
    """Bytes del archivo subido, rechazando el que pesa más de 5 MB sin leerlo entero (D-106 punto 5)."""
    tamano = getattr(archivo, "size", None)
    if tamano is not None and tamano > TAMANO_MAXIMO:
        raise _error(MENSAJE_PESADA, "imagen_pesada")
    datos = archivo.read(TAMANO_MAXIMO + 1)  # nunca más que el tope + 1 byte, para detectar el exceso
    if len(datos) > TAMANO_MAXIMO:
        raise _error(MENSAJE_PESADA, "imagen_pesada")
    return datos


def _verificar(datos):
    """Comprueba que ``datos`` sea una imagen real de un formato admitido y de tamaño razonable.

    Devuelve ``(formato, (ancho, alto), orientacion)``: ``orientacion`` es la etiqueta EXIF (1 a 8) cuando se puede leer de la
    cabecera sin decodificar (JPEG y WebP) y ``None`` si no (por ejemplo, PNG: su ``eXIf`` viene después de los píxeles).
    Pillow solo lee la cabecera al abrir: el formato y las dimensiones se miran antes de decodificar nada. Los avisos de
    «bomba de descompresión» de Pillow se tratan como errores (se mantiene su protección, D-106 punto 5).
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(datos)) as imagen:
                formato = imagen.format
                if formato not in FORMATOS_ADMITIDOS:
                    raise _error(MENSAJE_FORMATO, "imagen_formato")
                ancho, alto = imagen.size
                if ancho * alto > LIMITE_DE_PIXELES:
                    raise _error(MENSAJE_ENORME, "imagen_enorme")
                orientacion = None
                if formato in ("JPEG", "WEBP"):
                    orientacion = imagen.getexif().get(0x0112, 1)
                imagen.verify()  # detecta archivos dañados; después hay que volver a abrirla
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise _error(MENSAJE_ENORME, "imagen_enorme")
    except Exception:  # cualquier cosa que Pillow no pueda leer (texto, SVG, imagen cortada…) no es una imagen
        raise _error(MENSAJE_NO_VALIDA, "imagen_no_valida")
    return formato, (ancho, alto), orientacion


def _tamano_orientado(tamano, orientacion):
    """Tamaño de la imagen tal como la ve la persona: con ancho y alto intercambiados si la orientación EXIF es de 5 a 8
    (giro de 90°). ``None`` si la orientación no se pudo leer de la cabecera."""
    if orientacion is None:
        return None
    ancho, alto = tamano
    return (alto, ancho) if orientacion in (5, 6, 7, 8) else (ancho, alto)


def _decodificar(datos, formato, lado_maximo, reduccion=None):
    """La imagen ya cargada, con la orientación EXIF corregida (D-106 punto 6), en RGB o RGBA.

    En un JPEG se usa ``draft``: el decodificador entrega la imagen a escala reducida (1/2, 1/4, 1/8) sin pasar por el tamaño
    completo. ``reduccion`` es el tamaño mínimo que se le pide (por defecto, ``lado_maximo`` en los dos lados); con recorte
    elegido, las coordenadas se escalan después de forma explícita con la proporción real (``_caja_del_recorte``).
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            imagen = Image.open(BytesIO(datos))
            if formato == "JPEG":
                imagen.draft("RGB", reduccion or (lado_maximo, lado_maximo))
            imagen.load()
            imagen = ImageOps.exif_transpose(imagen)  # antes de recortar o achicar: las fotos de celular vienen giradas
            con_alfa = imagen.mode in ("RGBA", "LA", "PA") or (imagen.mode == "P" and "transparency" in imagen.info)
            return imagen.convert("RGBA" if con_alfa else "RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise _error(MENSAJE_ENORME, "imagen_enorme")
    except Exception:
        raise _error(MENSAJE_NO_VALIDA, "imagen_no_valida")


def _entero(valor):
    """``valor`` como entero si es un entero o un texto de dígitos (con signo), y ``None`` si no lo es. Un ``bool``, un número con
    decimales o un texto con espacios en el medio no valen."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and re.fullmatch(r"-?\d+", valor.strip()):
        return int(valor.strip())
    return None


def _normalizar_recorte(recorte):
    """``(x, y, lado)`` como enteros; ``None`` si no se pidió recorte (los tres vacíos: recorte central); o ``ValidationError``
    (``recorte_incompleto`` o ``recorte_no_numerico``). Un valor ``None`` o un texto vacío cuenta como ausente."""
    if recorte is None:
        return None
    ausentes = [valor is None or (isinstance(valor, str) and not valor.strip()) for valor in recorte]
    if all(ausentes):
        return None
    if any(ausentes):
        raise _error(MENSAJE_RECORTE_INCOMPLETO, "recorte_incompleto")
    enteros = [_entero(valor) for valor in recorte]
    if None in enteros:
        raise _error(MENSAJE_RECORTE_NO_NUMERICO, "recorte_no_numerico")
    return tuple(enteros)


def _comprobar_tamano(tamano, lado_minimo, recorte):
    """Controles que dependen del tamaño de la imagen ya orientada: el lado mínimo de la foto (``imagen_chica``) y que el recorte
    elegido entre completo (``recorte_chico``, ``recorte_negativo``, ``recorte_mayor_que_la_imagen`` y ``recorte_fuera_de_la_imagen``)."""
    ancho, alto = tamano
    if lado_minimo and min(ancho, alto) < lado_minimo:
        raise _error(MENSAJE_IMAGEN_CHICA.format(lado=lado_minimo), "imagen_chica")
    if recorte is None:
        return
    x, y, lado = recorte
    if lado < LADO_MINIMO_DEL_RECORTE:
        raise _error(MENSAJE_RECORTE_CHICO, "recorte_chico")
    if x < 0 or y < 0:
        raise _error(MENSAJE_RECORTE_AFUERA, "recorte_negativo")
    if lado > min(ancho, alto):
        raise _error(MENSAJE_RECORTE_MAYOR, "recorte_mayor_que_la_imagen")
    if x + lado > ancho or y + lado > alto:
        raise _error(MENSAJE_RECORTE_AFUERA, "recorte_fuera_de_la_imagen")


def _caja_del_recorte(recorte, original, actual):
    """Caja ``(izquierda, arriba, derecha, abajo)`` del recorte sobre la imagen decodificada de tamaño ``actual``. ``original`` es el
    tamaño de la imagen ya orientada sobre el que la persona eligió ``recorte``. Si ``draft`` la redujo, las coordenadas se escalan
    de forma explícita con la proporción real y se ajustan para que el cuadrado quede adentro."""
    x, y, lado = recorte
    razon_x, razon_y = actual[0] / original[0], actual[1] / original[1]
    izquierda, arriba = int(x * razon_x), int(y * razon_y)
    lado_reducido = max(1, round(lado * (razon_x + razon_y) / 2))
    lado_reducido = min(lado_reducido, actual[0] - izquierda, actual[1] - arriba)
    return izquierda, arriba, izquierda + lado_reducido, arriba + lado_reducido


def procesar(archivo, lado_maximo, recortar_en_cuadrado=False, recorte=None, lado_minimo=None):
    """Valida ``archivo`` y devuelve los bytes de la imagen lista para guardar (WebP, sin metadatos).

    - ``lado_maximo``: lado mayor de la salida. Nunca se agranda (precisión de D-106; D-20 dice «la achica»).
    - ``recortar_en_cuadrado``: la foto se recorta en cuadrado y se achica hasta ``lado_maximo``; el logo no se recorta y
      conserva su proporción (D-106 punto 11).
    - ``recorte``: ``(x, y, lado)`` del cuadrado que eligió la persona, en píxeles de la imagen **ya con la orientación EXIF
      aplicada** (la que ve el navegador). Los valores pueden llegar como texto. Sin recorte (``None`` o los tres vacíos), el
      recorte es central. Solo vale con ``recortar_en_cuadrado``.
    - ``lado_minimo``: si se indica, el lado corto de la imagen tiene que medir al menos eso (``imagen_chica``).
    Falla con ``ValidationError``: ``imagen_pesada``, ``imagen_no_valida``, ``imagen_formato``, ``imagen_enorme``, ``imagen_chica``,
    ``recorte_incompleto``, ``recorte_no_numerico``, ``recorte_negativo``, ``recorte_chico``, ``recorte_mayor_que_la_imagen`` y
    ``recorte_fuera_de_la_imagen``. Nada se guarda: guardar es de ``guardar``.
    """
    if recorte is not None and not recortar_en_cuadrado:
        raise ValueError("Un recorte elegido solo vale para la imagen que se recorta en cuadrado.")
    datos = _leer(archivo)
    formato, tamano_de_cabecera, orientacion = _verificar(datos)
    recorte = _normalizar_recorte(recorte)

    # Con la orientación leída de la cabecera (JPEG y WebP) se controla todo antes de decodificar. Si no (PNG), se controla
    # después, con la imagen ya orientada; el límite de píxeles ya se decidió con la cabecera.
    original = _tamano_orientado(tamano_de_cabecera, orientacion)
    if original is not None:
        _comprobar_tamano(original, lado_minimo, recorte)

    reduccion = None
    if recorte is not None and formato == "JPEG":
        # Que el lado del recorte, ya reducido, siga midiendo al menos lo que va a medir la salida.
        proporcion = min(1, lado_maximo / recorte[2])
        reduccion = (math.ceil(tamano_de_cabecera[0] * proporcion), math.ceil(tamano_de_cabecera[1] * proporcion))
    imagen = _decodificar(datos, formato, lado_maximo, reduccion)
    if original is None:
        original = imagen.size
        _comprobar_tamano(original, lado_minimo, recorte)

    if recortar_en_cuadrado:
        if recorte is not None:
            caja = _caja_del_recorte(recorte, original, imagen.size)
        else:
            ancho, alto = imagen.size
            lado = min(ancho, alto)
            izquierda, arriba = (ancho - lado) // 2, (alto - lado) // 2
            caja = (izquierda, arriba, izquierda + lado, arriba + lado)
        imagen = imagen.crop(caja)
    imagen.thumbnail((lado_maximo, lado_maximo), Image.LANCZOS)  # achica manteniendo la proporción; no agranda
    # Imagen nueva a partir de los píxeles: no arrastra EXIF, perfil de color ni ningún otro dato de la original (D-106 punto 6).
    limpia = Image.frombytes(imagen.mode, imagen.size, imagen.tobytes())
    salida = BytesIO()
    limpia.save(salida, "WEBP", quality=CALIDAD_WEBP)
    return salida.getvalue()


def guardar(contenido, carpeta):
    """Guarda ``contenido`` en ``<carpeta>/<uuid4>.webp`` (D-106 punto 7) y devuelve el nombre con el que quedó guardado."""
    return default_storage.save(f"{carpeta}/{uuid.uuid4()}.webp", ContentFile(contenido))


def borrar(nombre):
    """Borra el archivo ``nombre``. Un nombre vacío o un archivo que ya no está no es un error; si el almacenamiento falla se
    registra y se sigue: el archivo queda huérfano, pero no se deshace una operación ya confirmada."""
    if not nombre:
        return
    try:
        default_storage.delete(nombre)
    except Exception:
        logger.exception("No se pudo borrar el archivo %s del almacenamiento.", nombre)


def borrar_al_confirmar(nombre):
    """Borra ``nombre`` después de confirmada la transacción en curso (D-106 punto 7). Si la transacción se deshace, no se borra."""
    if nombre:
        transaction.on_commit(lambda: borrar(nombre))
