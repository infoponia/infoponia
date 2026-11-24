# Fechas, calendario y precios de un detalle de suministro (COM-03a, paso 2; docs/casos_de_uso/comercial/suministro.md, «Fechas y precios»).
# Funciones puras: no escriben ni bloquean; las usan pactar, la ficha, la pre-reserva y COM-MOD-SUM. Solo `ventana` lee la configuración.
# Las fechas en meses se calculan con `calendar` de la biblioteca estándar (sin dependencias nuevas).

import calendar as _calendar
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from maestros.servicios import configuracion

CENTAVOS = Decimal("0.01")


def sumar_meses(fecha, n):
    """El mismo día del mes, ``n`` meses después; si ese día no existe, el último de ese mes (31/01 + 1 = 28/02 o 29/02). Es la regla
    «Fecha de fin». No es ``fecha + 30 × n``."""
    indice = fecha.month - 1 + n
    anio, mes = fecha.year + indice // 12, indice % 12 + 1
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, _calendar.monthrange(anio, mes)[1]))


def meses_transcurridos(desde, hasta):
    """El mayor ``n`` tal que ``sumar_meses(desde, n) <= hasta`` (meses calendario completos); 0 si ``hasta`` no supera a ``desde``.
    Con ``desde`` el 22/10: el 21/12 da 1 y el 22/12 da 2."""
    if hasta <= desde:
        return 0
    n = (hasta.year - desde.year) * 12 + hasta.month - desde.month
    while n > 0 and sumar_meses(desde, n) > hasta:
        n -= 1
    return n


def _fin_del_calendario(detalle):
    """La menor entre la fecha de fin del detalle (si tiene) y la del contrato."""
    fin = detalle.suministro.fecha_fin
    if detalle.fecha_fin_detalle is not None:
        fin = min(fin, detalle.fecha_fin_detalle)
    return fin


def calendario(detalle, desde=None, hasta=None):
    """Las fechas ``fecha_primer_entrega + k × periodo`` (k = 0, 1, 2…) hasta ``fecha_fin_detalle`` o la fecha de fin del contrato (la
    menor), ambas incluidas. Con ``desde`` y/o ``hasta``, solo ese tramo (extremos incluidos), **sin generar los anteriores**."""
    paso = timedelta(days=detalle.periodo_entrega_dias)
    primera = detalle.fecha_primer_entrega
    fin = _fin_del_calendario(detalle)
    if hasta is not None:
        fin = min(fin, hasta)
    k = 0
    if desde is not None and desde > primera:
        k = -(-(desde - primera).days // detalle.periodo_entrega_dias)  # división hacia arriba
    fecha = primera + k * paso
    fechas = []
    while fecha <= fin:
        fechas.append(fecha)
        fecha += paso
    return fechas


def precio_en(detalle, fecha):
    """Regla 7 de 8.11: con mecanismo fijo, el precio inicial; con ajuste periódico, ``inicial × (1 + porcentaje / 100) ^ ajustes`` con
    ``ajustes = meses_transcurridos(fecha_base_ajuste, fecha) // meses_ajuste``. ``Decimal``, ``ROUND_HALF_UP`` a 2 decimales y siempre
    desde el precio inicial (los redondeos no se acumulan)."""
    inicial = detalle.precio_unitario_suministro
    if detalle.mecanismo_precio != "ajuste_periodico":
        return Decimal(inicial).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    ajustes = meses_transcurridos(detalle.fecha_base_ajuste, fecha) // detalle.meses_ajuste
    factor = (1 + Decimal(detalle.porcentaje_ajuste) / 100) ** ajustes
    return (Decimal(inicial) * factor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def tramos_de_precio(detalle):
    """``[(fecha, precio)]``: un tramo por cada precio distinto del calendario, que arranca en la primera fecha del calendario con ese
    precio («Desde el dd/mm: $ 1.030,00», extensión 8b). Con precio fijo, un solo tramo; sin fechas, vacío."""
    tramos = []
    for fecha in calendario(detalle):
        precio = precio_en(detalle, fecha)
        if not tramos or tramos[-1][1] != precio:
            tramos.append((fecha, precio))
    return tramos


def ventana(hoy):
    """Último día de la ventana de pre-reserva: ``hoy + dias_pre_reserva_suministro`` (configuración operativa). Un período cae dentro si
    ``hoy <= fecha <= ventana(hoy)``."""
    return hoy + timedelta(days=configuracion.obtener().dias_pre_reserva_suministro)


def rige_desde(detalle, hoy):
    """«Desde cuándo rige» un cambio (COM-MOD-SUM, paso 4): el primer período del calendario **posterior** a ``ventana(hoy)``, o ``None``
    si el detalle termina dentro de la ventana."""
    limite = ventana(hoy)
    desde = limite + timedelta(days=1)
    fechas = calendario(detalle, desde=desde)
    return fechas[0] if fechas else None
