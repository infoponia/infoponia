# Registro de tipos de alerta (MAE-02a, D-41; regla A4 de D-37). ``maestros`` es de nivel 3 y no conoce las apps altas:
# cada una registra los suyos en ``AppConfig.ready()`` y ``maestros`` registra los cuatro «invernadero sin {rol} activo».
# Patrón: Variaciones protegidas con Indirección (Larman), el mismo de ``maestros/extensiones.py``.
# Contrato completo para quien programa un módulo: docs/api/alertas.md.

from dataclasses import dataclass
from enum import Enum


class Destinatario(str, Enum):
    """A quién va una alerta del tipo (regla 1 de 8.9 y reglas 2, 3 y 4 de 8.22)."""

    # Solo al Gerente (regla 3 de 8.22 y casos de uso: «invernadero sin {rol} activo»).
    GERENTE = "gerente"
    # Al Agrónomo del invernadero y, mientras no haya uno activo, al Gerente (regla 4 de 8.22, MD-61).
    AGRONOMO_O_GERENTE = "agronomo_o_gerente"
    # Al Agrónomo del invernadero y también al Gerente (regla 2 de 8.9: umbral de merma).
    AGRONOMO_Y_GERENTE = "agronomo_y_gerente"


class Clase(str, Enum):
    """Alerta de estado (dura mientras dure la condición; a lo sumo una activa) o de evento (una por hecho)."""

    ESTADO = "estado"
    EVENTO = "evento"


class Origen(str, Enum):
    """Qué clase de una app alta origina la alerta (restricción C5: a lo sumo uno). Lo enlaza la app de origen."""

    HARDWARE = "hardware"
    TELEMETRIA = "telemetria"
    SOLICITUD_REVISION = "solicitud_revision"
    MERMA = "merma"
    # D-62, punto 1 (COM-03b): los orígenes de `comercial` y de la partida de `produccion`. No hay migración: el origen vive en el tipo.
    ENTREGA = "entrega"
    SUMINISTRO = "suministro"
    DETALLE_SUMINISTRO = "detalle_suministro"
    STOCK_COSECHADO = "stock_cosechado"


@dataclass(frozen=True)
class TipoAlerta:
    """Definición de un tipo de alerta. ``codigo`` es único y de hasta 50 caracteres (los ajenos a ``maestros`` llevan
    el prefijo de su app); ``severidad`` es uno de los valores de ``Alerta.Severidad``; ``origen`` es ``None`` si la
    alerta no tiene origen."""

    codigo: str
    nombre: str
    destinatario: Destinatario
    severidad: str
    clase: Clase
    origen: Origen | None = None


# Registro de módulo: lo reemplazan las pruebas con ``mock.patch.dict`` (``tipo_de_alerta_de_prueba``).
_TIPOS = {}


def registrar_tipo_de_alerta(tipo):
    """Registra ``tipo``. Idempotente: registrar dos veces la misma definición no hace nada (``ready()`` puede correr más
    de una vez). Un código repetido con otra definición, o de más de 50 caracteres, lanza ``ValueError``."""
    existente = _TIPOS.get(tipo.codigo)
    if existente is not None:
        if existente != tipo:
            raise ValueError(f"El tipo de alerta «{tipo.codigo}» ya está registrado con otra definición.")
        return
    if len(tipo.codigo) > 50:
        raise ValueError(f"El código «{tipo.codigo}» tiene más de 50 caracteres.")
    _TIPOS[tipo.codigo] = tipo


def tipo_de_alerta(codigo):
    """El ``TipoAlerta`` registrado con ese código; ``ValueError`` si no está registrado."""
    try:
        return _TIPOS[codigo]
    except KeyError:
        raise ValueError(f"El tipo de alerta «{codigo}» no está registrado.") from None


def codigos_con_destinatario(destinatario):
    """Los códigos de los tipos registrados cuyo destinatario es ``destinatario``."""
    return [codigo for codigo, tipo in _TIPOS.items() if tipo.destinatario == destinatario]
