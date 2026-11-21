# Servicio de ConfiguracionOperativa (MAE-04, ADM-MOD-CFG). Cada caso de uso es una función dentro de ``transaction.atomic()``
# y audita con el formato de D-36 (docs/patrones/auditoria.md). Fuente: docs/casos_de_uso/maestros/configuracion.md.
#
# Singleton (MD-89, docs/patrones/datos_de_migracion.md): ``obtener`` crea la fila si faltara (red de seguridad). Quien use un
# parámetro lo lee con ``obtener()`` en cada uso y nunca lo guarda en una constante de módulo (regla 7: el cambio rige hacia
# adelante). Bloqueo (docs/patrones/bloqueos.md): ``FOR NO KEY UPDATE`` sobre la fila, releída después de bloquear; todo lo
# que se valida y se compara se hace contra lo leído después de bloquear (dos pedidos a la vez: gana el último).

import re
from collections import namedtuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models import RegistroAuditoria, Usuario, rol_de
from maestros.models import PARAMETROS_DE_CONFIGURACION, ConfiguracionOperativa
from maestros.servicios.invernaderos import _actor_sigue_activo

# La configuración guardada y las advertencias que no bloquean (regla 5 de ADM-MOD-CFG).
Resultado = namedtuple("Resultado", "configuracion advertencias")

MAXIMO_DE_LA_COLUMNA = 2_147_483_647  # el de la columna entera de la base
MENSAJE_HORIZONTE = (
    "El horizonte de cosecha es menor que la pre-reserva de suministros: algunas reservas van a caer fuera del horizonte."
)
_PARAMETROS = {campo: (minimo, maximo) for campo, _, _, minimo, maximo in PARAMETROS_DE_CONFIGURACION}
_ENTERO = re.compile(r"^-?\d+$", re.ASCII)


def obtener():
    """La fila única; si faltara (por ejemplo, una base vaciada) la crea con los valores iniciales, de forma segura ante
    pedidos simultáneos (``get_or_create`` sobre ``singleton=1``). Es una red de seguridad, no el camino normal."""
    return ConfiguracionOperativa.objects.get_or_create(singleton=1)[0]


def advertencias_de(valores):
    """Las advertencias de un conjunto de valores ``{campo: entero}`` (regla 5 de ADM-MOD-CFG): si el horizonte de cosecha
    queda menor que la pre-reserva, algunas reservas caerán fuera del horizonte. No bloquea."""
    if valores["dias_horizonte_cosecha"] < valores["dias_pre_reserva_suministro"]:
        return [MENSAJE_HORIZONTE]
    return []


def _exigir_gerente(actor):
    """Precondición a: ``actor`` es un Gerente con la cuenta activa (SEG-13, regla 1)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede modificar la configuración operativa.")


def _como_entero(valor):
    """``(entero, None)`` si ``valor`` es un entero (o un texto de un entero); si no, ``(None, ValidationError)``."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None, ValidationError("Ingresá un valor.", code="obligatorio")
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        return None, ValidationError("Ingresá un número entero.", code="no_entero")
    if isinstance(valor, str):
        if not _ENTERO.match(valor.strip()):
            return None, ValidationError("Ingresá un número entero.", code="no_entero")
        valor = int(valor.strip())
    return valor, None


def _error_de_dominio(campo, valor):
    """El error de ``valor`` contra el dominio de ``campo`` (regla 3), o ``None``."""
    minimo, maximo = _PARAMETROS[campo]
    if valor < minimo:
        return ValidationError(f"El mínimo es {minimo}.", code="minimo")
    tope = MAXIMO_DE_LA_COLUMNA if maximo is None else maximo
    if valor > tope:
        return ValidationError(f"El máximo es {tope}.", code="maximo")
    return None


def modificar_configuracion(actor, **valores):
    """ADM-MOD-CFG: modifica los parámetros indicados (``campo=valor``; lo que no se indica queda como está) y devuelve un
    ``Resultado`` con la configuración y las advertencias.

    - Precondición a y regla 1: Gerente activo (``PermissionDenied``); la fila ya existe, no se crea ni se elimina.
    - Regla 3: enteros obligatorios dentro de su dominio. Regla 4: la anticipación de cosecha del suministro no supera la
      pre-reserva (error del campo de la anticipación). Regla 6: todo o nada, con todos los errores juntos, un error por
      campo. Regla 5: el horizonte menor que la pre-reserva es una advertencia que no bloquea.
    - D-28: sin cambios no se escribe ni se audita. Postcondición b (D-36): ``modificacion_configuracion`` con el antes y el
      después de cada parámetro que cambió.
    - Un campo desconocido es un error de programación (``TypeError``), no un dato de la persona.
    """
    desconocidos = set(valores) - set(_PARAMETROS)
    if desconocidos:
        raise TypeError(f"Parámetros desconocidos: {', '.join(sorted(desconocidos))}.")
    _exigir_gerente(actor)
    with transaction.atomic():
        obtener()  # red de seguridad: si faltara la fila, hay algo que bloquear
        fila = ConfiguracionOperativa.objects.select_for_update(no_key=True).get(singleton=1)  # releída ya bloqueada
        _actor_sigue_activo(actor)

        errores, nuevos = {}, {}
        for campo, valor in valores.items():
            entero, error = _como_entero(valor)
            error = error or _error_de_dominio(campo, entero)
            if error:
                errores[campo] = [error]
            else:
                nuevos[campo] = entero
        vigentes = {campo: getattr(fila, campo) for campo in _PARAMETROS} | nuevos
        antic, pre = "dias_anticipacion_cosecha_suministro", "dias_pre_reserva_suministro"
        if antic not in errores and pre not in errores and vigentes[antic] > vigentes[pre]:
            errores[antic] = [ValidationError("No puede superar la pre-reserva de suministros.", code="supera_pre_reserva")]
        if errores:
            raise ValidationError(errores)

        cambios = {
            campo: {"antes": getattr(fila, campo), "despues": valor}
            for campo, valor in nuevos.items()
            if getattr(fila, campo) != valor
        }
        if cambios:
            for campo in cambios:
                setattr(fila, campo, nuevos[campo])
            fila.save(update_fields=list(cambios))
            RegistroAuditoria.objects.registrar(
                usuario=actor,
                accion=RegistroAuditoria.Accion.MODIFICACION_CONFIGURACION,
                afectados=[fila],
                detalle={"cambios": cambios},
            )
        return Resultado(fila, advertencias_de(vigentes))
