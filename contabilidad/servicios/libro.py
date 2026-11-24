# Libro de gestión, solo lectura (D-84 punto 8): saldos, movimientos por cuenta y totales por período, calculados con consultas agregadas sobre
# `MovimientoContable` (los saldos no se guardan). No escribe, no bloquea y no audita. Las cuentas de resultado empiezan en cero en cada
# ejercicio; las patrimoniales arrastran lo acumulado de los ejercicios de fecha de inicio menor. Sin refundición (H2.3).
from collections import namedtuple
from decimal import Decimal

from django.db.models import Q, Sum

from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import CuentaContable, EjercicioContable, MovimientoContable

Tipo = CuentaContable.Tipo
CERO = Decimal("0.00")
# Saldo normal: deudor (Debe − Haber) en activo y resultado negativo; acreedor (Haber − Debe) en el resto (H7).
DEUDORAS = (Tipo.ACTIVO, Tipo.RESULTADO_NEGATIVO)
PATRIMONIALES = (Tipo.ACTIVO, Tipo.PASIVO, Tipo.PATRIMONIO_NETO)

Saldo = namedtuple("Saldo", "debe haber saldo_inicial saldo contrario")
MovimientoConSaldo = namedtuple("MovimientoConSaldo", "movimiento saldo")
Resultado = namedtuple("Resultado", "ingresos egresos resultado")


def _con_saldo_segun_naturaleza(tipo_cuenta, debe, haber):
    """Debe − Haber en una cuenta deudora, Haber − Debe en una acreedora (con su signo)."""
    return debe - haber if tipo_cuenta in DEUDORAS else haber - debe


def _sumas(movimientos):
    """`(debe, haber)` de un queryset de movimientos, en una sola consulta; cero si no hay."""
    sumas = movimientos.aggregate(
        debe=Sum("importe_movimiento", filter=Q(tipo_movimiento=DEBE)),
        haber=Sum("importe_movimiento", filter=Q(tipo_movimiento=HABER)),
    )
    return sumas["debe"] or CERO, sumas["haber"] or CERO


def _cuenta(codigo):
    try:
        return CuentaContable.objects.get(codigo_cuenta=codigo)
    except CuentaContable.DoesNotExist:
        raise ErrorContable("cuenta_inexistente", f"La cuenta contable {codigo} no existe en el plan de cuentas.") from None


def saldo_por_cuenta(ejercicio_id):
    """`{codigo_cuenta: Saldo(debe, haber, saldo_inicial, saldo, contrario)}` de las cuentas del plan en ese ejercicio (D-84 punto 8).

    `debe` y `haber` son los del ejercicio; `saldo_inicial` es el arrastre de los ejercicios anteriores (solo cuentas patrimoniales; cero
    en las de resultado); `saldo` es `saldo_inicial` más lo del ejercicio según la naturaleza de la cuenta; `contrario` marca un saldo
    contrario a su naturaleza (por ejemplo, 5.1.06 acreedora).
    """
    ejercicio = EjercicioContable.objects.get(pk=ejercicio_id)
    cuentas = list(CuentaContable.objects.all())
    del_ejercicio = {}
    for cuenta_id, tipo, total in (
        MovimientoContable.objects.filter(asiento__ejercicio_id=ejercicio_id)
        .values("cuenta_id", "tipo_movimiento")
        .annotate(total=Sum("importe_movimiento"))
        .values_list("cuenta_id", "tipo_movimiento", "total")
    ):
        del_ejercicio[(cuenta_id, tipo)] = total
    previos = {}
    for cuenta_id, tipo, total in (
        MovimientoContable.objects.filter(
            asiento__ejercicio__fecha_inicio_ejercicio__lt=ejercicio.fecha_inicio_ejercicio,
            cuenta__tipo_cuenta__in=PATRIMONIALES,
        )
        .values("cuenta_id", "tipo_movimiento")
        .annotate(total=Sum("importe_movimiento"))
        .values_list("cuenta_id", "tipo_movimiento", "total")
    ):
        previos[(cuenta_id, tipo)] = total
    saldos = {}
    for cuenta in cuentas:
        debe = del_ejercicio.get((cuenta.pk, DEBE), CERO)
        haber = del_ejercicio.get((cuenta.pk, HABER), CERO)
        inicial = _con_saldo_segun_naturaleza(
            cuenta.tipo_cuenta, previos.get((cuenta.pk, DEBE), CERO), previos.get((cuenta.pk, HABER), CERO)
        )
        saldo = inicial + _con_saldo_segun_naturaleza(cuenta.tipo_cuenta, debe, haber)
        saldos[cuenta.codigo_cuenta] = Saldo(debe, haber, inicial, saldo, saldo < 0)
    return saldos


def movimientos_de_cuenta(codigo, ejercicio_id):
    """Los movimientos de la cuenta en el ejercicio, con su saldo acumulado, para la vista por cuenta (lista de `MovimientoConSaldo`).

    Orden: fecha del asiento, número de asiento e id (el número indica orden de registro, no de fecha, H8). El saldo acumulado parte
    del saldo inicial (cero en las cuentas de resultado) y sigue la naturaleza de la cuenta. Cada movimiento trae su asiento.
    """
    cuenta = _cuenta(codigo)
    ejercicio = EjercicioContable.objects.get(pk=ejercicio_id)
    saldo = CERO
    if cuenta.tipo_cuenta in PATRIMONIALES:
        saldo = _con_saldo_segun_naturaleza(
            cuenta.tipo_cuenta,
            *_sumas(
                MovimientoContable.objects.filter(
                    cuenta=cuenta, asiento__ejercicio__fecha_inicio_ejercicio__lt=ejercicio.fecha_inicio_ejercicio
                )
            ),
        )
    filas = []
    movimientos = (
        MovimientoContable.objects.filter(cuenta=cuenta, asiento__ejercicio_id=ejercicio_id)
        .select_related("asiento", "cuenta")
        .order_by("asiento__fecha_asiento", "asiento__numero_asiento", "id")
    )
    for movimiento in movimientos:
        importe = movimiento.importe_movimiento
        a_favor = (movimiento.tipo_movimiento == DEBE) == (cuenta.tipo_cuenta in DEUDORAS)
        saldo = saldo + importe if a_favor else saldo - importe
        filas.append(MovimientoConSaldo(movimiento, saldo))
    return filas


def resultado_del_periodo(desde, hasta):
    """`Resultado(ingresos, egresos, resultado)` entre dos fechas inclusivas, por FECHA DEL ASIENTO aunque el período cruce dos
    ejercicios (lo usa Estadísticas, EST-02). Ingresos: cuentas de resultado positivo (Haber − Debe); egresos: de resultado negativo
    (Debe − Haber); resultado: ingresos − egresos."""
    acumulado = {}
    for tipo_cuenta, tipo, total in (
        MovimientoContable.objects.filter(
            asiento__fecha_asiento__gte=desde,
            asiento__fecha_asiento__lte=hasta,
            cuenta__tipo_cuenta__in=(Tipo.RESULTADO_POSITIVO, Tipo.RESULTADO_NEGATIVO),
        )
        .values("cuenta__tipo_cuenta", "tipo_movimiento")
        .annotate(total=Sum("importe_movimiento"))
        .values_list("cuenta__tipo_cuenta", "tipo_movimiento", "total")
    ):
        acumulado[(tipo_cuenta, tipo)] = total
    ingresos = _con_saldo_segun_naturaleza(
        Tipo.RESULTADO_POSITIVO,
        acumulado.get((Tipo.RESULTADO_POSITIVO, DEBE), CERO),
        acumulado.get((Tipo.RESULTADO_POSITIVO, HABER), CERO),
    )
    egresos = _con_saldo_segun_naturaleza(
        Tipo.RESULTADO_NEGATIVO,
        acumulado.get((Tipo.RESULTADO_NEGATIVO, DEBE), CERO),
        acumulado.get((Tipo.RESULTADO_NEGATIVO, HABER), CERO),
    )
    return Resultado(ingresos, egresos, ingresos - egresos)


def total_por_cuenta_en_periodo(codigo, desde, hasta, *, tipo=None):
    """Suma de los movimientos de una cuenta entre dos fechas inclusivas, por fecha del asiento (decisión de CON-02).

    Con `tipo` «D» o «H», la suma de los importes de ese lado. Con `tipo=None`, el saldo según la naturaleza de la cuenta (Debe − Haber
    en una deudora, Haber − Debe en una acreedora), con su signo aunque quede negativo. Otro `tipo` lanza `tipo_de_movimiento_invalido`.
    """
    if tipo not in (None, DEBE, HABER):
        raise ErrorContable(
            "tipo_de_movimiento_invalido", f"El tipo de movimiento {tipo!r} no es válido: usá «D» (Debe) o «H» (Haber)."
        )
    cuenta = _cuenta(codigo)
    debe, haber = _sumas(
        MovimientoContable.objects.filter(
            cuenta=cuenta, asiento__fecha_asiento__gte=desde, asiento__fecha_asiento__lte=hasta
        )
    )
    if tipo == DEBE:
        return debe
    if tipo == HABER:
        return haber
    return _con_saldo_segun_naturaleza(cuenta.tipo_cuenta, debe, haber)
