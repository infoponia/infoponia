# Período de las estadísticas (D-93 punto 2; EST-CNS-PRD, regla 2): rango de fechas, atajos, período anterior de igual duración,
# validaciones y comparación contra el anterior. Funciones puras salvo el atajo «ejercicio», que lee el ejercicio abierto.

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from django.core.exceptions import ValidationError

from contabilidad.servicios.ejercicios import ejercicio_abierto

CODIGOS_DE_ATAJO = ("mes", "mes_anterior", "tres_meses", "ejercicio", "personalizado")
# Textos de los atajos, en el orden de la pantalla (los del prototipo, D-93 punto 2).
TEXTOS_DE_ATAJO = {
    "mes": "Este mes",
    "mes_anterior": "Mes anterior",
    "tres_meses": "Últimos 3 meses",
    "ejercicio": "Ejercicio actual",
    "personalizado": "Personalizado",
}
MAXIMO_DE_DIAS = 366


class Periodo(NamedTuple):
    """Un período cerrado: de `desde` a `hasta`, ambos días incluidos."""

    desde: date
    hasta: date

    @property
    def dias(self):
        """La cantidad de días del período, con los dos extremos."""
        return (self.hasta - self.desde).days + 1


class Comparacion(NamedTuple):
    """Un valor frente al del período anterior: la diferencia absoluta y la porcentual (`None` = «—»)."""

    valor: Decimal | None
    anterior: Decimal | None
    diferencia: Decimal | None
    porcentaje: Decimal | None


def periodo_por_defecto(hoy):
    """Del 1 del mes de `hoy` hasta `hoy` (D-93 punto 2)."""
    return Periodo(hoy.replace(day=1), hoy)


def _meses_atras(dia, meses):
    """El mismo día de `meses` meses antes; si ese mes no tiene el día (31/05 → febrero), el último día de ese mes."""
    indice = dia.year * 12 + dia.month - 1 - meses
    anio, mes = divmod(indice, 12)
    mes += 1
    return date(anio, mes, min(dia.day, calendar.monthrange(anio, mes)[1]))


def atajo(codigo, hoy):
    """El `Periodo` de un atajo; «personalizado» devuelve el período por defecto (lo que la pantalla muestra al elegirlo).
    Fuente: D-93 punto 2 (los atajos del prototipo)."""
    if codigo in ("mes", "personalizado"):
        return periodo_por_defecto(hoy)
    if codigo == "mes_anterior":
        fin = hoy.replace(day=1) - timedelta(days=1)
        return Periodo(fin.replace(day=1), fin)
    if codigo == "tres_meses":
        return Periodo(_meses_atras(hoy, 3), hoy)
    if codigo == "ejercicio":
        ejercicio = ejercicio_abierto()
        if ejercicio is None:
            raise ValidationError("No hay un ejercicio abierto.", code="sin_ejercicio_abierto")
        return Periodo(ejercicio.fecha_inicio_ejercicio, hoy)
    raise ValidationError("El período elegido no existe.", code="atajo_desconocido")


def anterior(periodo):
    """Los mismos días inmediatamente antes: `desde − n … desde − 1`, con `n` = los días del período (D-93 punto 2)."""
    return Periodo(periodo.desde - timedelta(days=periodo.dias), periodo.desde - timedelta(days=1))


def validar(desde, hasta, hoy):
    """Devuelve el `Periodo` o lanza `ValidationError` con el mensaje que corresponde (D-93 punto 2; EST-CNS-PRD regla 2)."""
    if desde is None or hasta is None:
        raise ValidationError("Indicá las dos fechas.", code="faltan_fechas")
    if desde > hasta:
        raise ValidationError("La fecha “desde” no puede ser posterior a “hasta”.", code="desde_posterior")
    if hasta > hoy:
        raise ValidationError("El período no puede terminar después de hoy.", code="termina_despues_de_hoy")
    periodo = Periodo(desde, hasta)
    if periodo.dias > MAXIMO_DE_DIAS:
        raise ValidationError("El período no puede ser mayor que un año.", code="mayor_que_un_ano")
    return periodo


def comparar(actual, anterior):
    """La `Comparacion` de `actual` con `anterior` (`Decimal`, entero o `None`): diferencia absoluta y porcentual con un decimal
    (`ROUND_HALF_UP`); sin porcentaje («—») si el anterior es 0, y sin diferencia si falta alguno de los dos valores."""
    valor = None if actual is None else Decimal(str(actual))
    previo = None if anterior is None else Decimal(str(anterior))
    if valor is None or previo is None:
        return Comparacion(valor, previo, None, None)
    diferencia = valor - previo
    porcentaje = None if previo == 0 else (diferencia * 100 / previo).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return Comparacion(valor, previo, diferencia, porcentaje)
