# Validadores de datos del IoT, funciones puras que no tocan la base (IOT-02). Cada una lanza un ``ValidationError`` con un código estable
# que el servicio junta con los de los demás campos para marcar todos los errores a la vez (docs/patrones/abm.md, sección 2, paso 2).
# Fuentes: docs/casos_de_uso/iot/sistema_iot.md (regla «Datos del nodo central», regla 7 de IOT-MOD-SIS) y docs/modelo/iot.md, «SistemaIoT».

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone

UN_DECIMAL = Decimal("0.1")
LIMITE_DEL_RANGO = Decimal("999.9")  # ``Decimal(4, 1)`` de ``SistemaIoT.temp_solucion_min`` y ``temp_solucion_max`` (docs/modelo/iot.md)


def texto(valor):
    """``valor`` como texto recortado (vacío si es ``None``)."""
    return "" if valor is None else str(valor).strip()


def validar_texto(valor, largo, obligatorio, nombre):
    """Texto recortado de hasta ``largo`` caracteres. Obligatorio (``obligatorio``) o vacío permitido. ``nombre`` es el del dato en el mensaje."""
    recortado = texto(valor)
    if not recortado:
        if obligatorio:
            raise ValidationError(f"Ingresá {nombre}.", code="obligatorio")
        return ""
    if len(recortado) > largo:
        raise ValidationError(f"Usá como máximo {largo} caracteres.", code="demasiado_largo")
    return recortado


def validar_fecha_de_instalacion(valor):
    """La fecha de instalación (regla 9 de IOT-ALT-HDW): obligatoria, y no posterior a hoy. Acepta un ``date`` o el texto ``AAAA-MM-DD`` del
    formulario."""
    if valor is None or texto(valor) == "":
        raise ValidationError("Ingresá la fecha de instalación.", code="obligatorio")
    if isinstance(valor, date):
        fecha = valor
    else:
        try:
            fecha = date.fromisoformat(texto(valor))
        except ValueError:
            raise ValidationError("Ingresá una fecha válida.", code="fecha_invalida") from None
    if fecha > timezone.localdate():
        raise ValidationError("No puede ser posterior a hoy.", code="fecha_futura")
    return fecha


def _un_valor_del_rango(valor):
    """Un extremo del rango como ``Decimal`` con un decimal, o ``None`` si está vacío. Lanza ``rango_invalido`` o ``rango_un_decimal``."""
    recortado = texto(valor).replace(",", ".")
    if not recortado:
        return None
    try:
        numero = Decimal(recortado)
    except InvalidOperation:
        raise ValidationError("Ingresá un número.", code="rango_invalido") from None
    if not numero.is_finite():
        raise ValidationError("Ingresá un número.", code="rango_invalido")
    if numero != numero.quantize(UN_DECIMAL):
        raise ValidationError("Usá como máximo un decimal.", code="rango_un_decimal")
    numero = numero.quantize(UN_DECIMAL)
    if abs(numero) > LIMITE_DEL_RANGO:
        raise ValidationError(f"Usá un valor entre -{LIMITE_DEL_RANGO} y {LIMITE_DEL_RANGO}.", code="rango_invalido")
    return numero


def validar_rango_de_la_solucion(minimo, maximo):
    """Regla 7 de IOT-MOD-SIS y extensión 6a de IOT-REG-SIS: ``(mínimo, máximo)`` en °C, los dos o ninguno, con un decimal y el mínimo
    menor que el máximo. Devuelve ``(None, None)`` si no se indicó. Lanza un ``ValidationError`` con un error por campo
    (``temp_solucion_min`` y ``temp_solucion_max``); los errores de la pareja (incompleto, invertido) van en ``temp_solucion_max``."""
    errores = {}
    valores = {}
    for campo, valor in (("temp_solucion_min", minimo), ("temp_solucion_max", maximo)):
        try:
            valores[campo] = _un_valor_del_rango(valor)
        except ValidationError as error:
            errores[campo] = [error]
    if not errores:
        bajo, alto = valores["temp_solucion_min"], valores["temp_solucion_max"]
        if (bajo is None) != (alto is None):
            errores["temp_solucion_max"] = [
                ValidationError("Completá mínimo y máximo, o dejá los dos vacíos.", code="rango_incompleto")
            ]
        elif bajo is not None and bajo >= alto:
            errores["temp_solucion_max"] = [
                ValidationError("El mínimo tiene que ser menor que el máximo.", code="rango_invertido")
            ]
    if errores:
        raise ValidationError(errores)
    return valores["temp_solucion_min"], valores["temp_solucion_max"]


# ---- hardware (IOT-02, paso 4) ----

IDENTIFICADOR = re.compile(r"^[A-Za-z0-9._/-]{1,64}$")
DOS_DECIMALES = Decimal("0.01")
LIMITE_DE_LA_CALIBRACION = Decimal("9999999.99")  # ``Decimal(9, 2)`` de ``Sensor.valor_calibracion_min`` y ``valor_calibracion_max``


def validar_identificador_equipo(valor):
    """Regla 2 de IOT-ALT-HDW: el código con el que el nodo nombra al equipo. Se recorta y se guarda como se escribió (la comparación es en
    minúsculas): obligatorio, de hasta 64 caracteres entre letras, números, «-», «_», «.» y «/», sin espacios."""
    recortado = texto(valor)
    if not recortado:
        raise ValidationError("Ingresá el identificador del equipo.", code="obligatorio")
    if not IDENTIFICADOR.fullmatch(recortado):
        raise ValidationError("Hasta 64 caracteres sin espacios: letras, números, - _ . /", code="identificador_invalido")
    return recortado


def _un_valor_de_la_calibracion(valor, nombre):
    """Un extremo de la calibración como ``Decimal`` de dos decimales, o ``obligatorio`` si está vacío."""
    recortado = texto(valor).replace(",", ".")
    if not recortado:
        raise ValidationError(f"Ingresá el {nombre}.", code="obligatorio")
    try:
        numero = Decimal(recortado)
    except InvalidOperation:
        raise ValidationError("Ingresá un número.", code="calibracion_invalida") from None
    if not numero.is_finite() or numero != numero.quantize(DOS_DECIMALES) or abs(numero) > LIMITE_DE_LA_CALIBRACION:
        raise ValidationError("Ingresá un número de hasta 7 dígitos y 2 decimales.", code="calibracion_invalida")
    return numero.quantize(DOS_DECIMALES)


def validar_calibracion(minimo, maximo):
    """Regla 5 de IOT-ALT-HDW: ``(mínimo, máximo)`` que el sensor puede medir; los dos obligatorios y el mínimo menor que el máximo. Lanza un
    ``ValidationError`` con un error por campo (``calibracion_min`` y ``calibracion_max``; el de la pareja va en el máximo)."""
    errores, valores = {}, {}
    for campo, valor, nombre in (("calibracion_min", minimo, "mínimo"), ("calibracion_max", maximo, "máximo")):
        try:
            valores[campo] = _un_valor_de_la_calibracion(valor, nombre)
        except ValidationError as error:
            errores[campo] = [error]
    if not errores and valores["calibracion_min"] >= valores["calibracion_max"]:
        errores["calibracion_max"] = [ValidationError("El mínimo tiene que ser menor que el máximo.", code="calibracion_invertida")]
    if errores:
        raise ValidationError(errores)
    return valores["calibracion_min"], valores["calibracion_max"]
