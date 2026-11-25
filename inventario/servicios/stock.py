# Lectura del stock (INV-01 e INV-02; docs/patrones/stock.md, secciones 1 y 2, y docs/api/stock.md, «Lectura»). Una sola función hace
# cada cuenta: ninguna pantalla ni otro servicio la repite. Todo se calcula para una fecha ``hoy`` que se pasa (la del invernadero:
# ``hoy()``); estas funciones no escriben ni bloquean. Una consulta por tabla para toda la lista de ids, nunca una por fila.
#
# Un lote está VENCIDO desde el día siguiente a su fecha de vencimiento (regla 4 de CMP-REV-VNC): el día de la fecha todavía se usa.
# «Sin cobertura» y «stock inconsistente» miden el stock SIN lotes vencidos (manda el CU, L7; docs/patrones/stock.md, sección 1).
# ``inventario.extensiones`` importa este módulo (stock_actual_de), así que acá se importa adentro de cada función (sin ciclo).

from collections import defaultdict, namedtuple
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.unidades import validar_cantidad  # noqa: F401 - se reexporta: docs/api/stock.md

CERO = Decimal("0")

# Las cantidades de un ``InsumoInvernadero`` (sección 1 de docs/patrones/stock.md).
Existencia = namedtuple("Existencia", "actual vigente reservado libre transito minimo bajo_minimo inconsistente")
# Lotes propuestos por FEFO: ``partes`` es ``[(lote_id, cantidad)]`` y ``resto`` lo que ningún lote cubre.
Propuesta = namedtuple("Propuesta", "partes resto")


def hoy():
    """La fecha de hoy en la zona del sistema (``America/Argentina/Buenos_Aires``): ``timezone.localdate()``. Usala siempre
    que necesites «hoy»: nada de ``date.today()``."""
    return timezone.localdate()


def esta_vencido(lote, fecha):
    """True si ``lote`` está vencido en ``fecha``: su vencimiento es anterior a ella. Sin fecha de vencimiento (o el faltante sin
    lote) nunca vence."""
    return lote.fecha_vencimiento is not None and lote.fecha_vencimiento < fecha


def stock_actual_de(iin_ids):
    """``{id: Decimal}``: el stock actual (``/cantActualInsumo``) de cada ``InsumoInvernadero``: la suma de la
    ``cantidad_disponible`` de TODOS sus lotes, incluido el faltante sin lote (puede ser negativo; regla 3 de 8.23). No se
    guarda: se calcula. Una sola consulta para toda la lista; lo que no tiene lotes da 0."""
    ids = list(iin_ids)
    stock = defaultdict(lambda: CERO)
    filas = (
        LoteInsumo.objects.filter(insumo_invernadero_id__in=ids)
        .values("insumo_invernadero_id")
        .annotate(total=Sum("cantidad_disponible"))
    )
    for fila in filas:
        stock[fila["insumo_invernadero_id"]] = fila["total"]
    return {i: stock[i] for i in ids}


def existencias(ids, hoy=None):
    """``{id: Existencia}`` de cada ``InsumoInvernadero`` de ``ids`` a la fecha ``hoy`` (por omisión, la de hoy).

    - actual: Σ de todos los lotes (faltante incluido). vigente: los lotes no vencidos a ``hoy`` más el faltante.
    - reservado: lo que informan los registrantes de reservas (0 sin ellos). libre: vigente − reservado (puede ser negativo).
    - bajo_minimo: mínimo > 0 y libre + tránsito < mínimo. inconsistente: vigente < reservado.
    Dos consultas (lotes y existencias) más una llamada por registrante de reservas, sin importar cuántos ids haya."""
    from inventario import extensiones

    ids = list(ids)
    if not ids:
        return {}
    if hoy is None:
        hoy = globals()["hoy"]()
    vigentes = Q(fecha_vencimiento__isnull=True) | Q(fecha_vencimiento__gte=hoy)
    sumas = {
        fila["insumo_invernadero_id"]: (fila["actual"], fila["vigente"])
        for fila in LoteInsumo.objects.filter(insumo_invernadero_id__in=ids)
        .values("insumo_invernadero_id")
        .annotate(actual=Sum("cantidad_disponible"), vigente=Sum("cantidad_disponible", filter=vigentes))
    }
    propias = {
        fila["id"]: fila
        for fila in InsumoInvernadero.objects.filter(pk__in=ids).values("id", "cant_min_insumo", "cant_transito_insumo")
    }
    reservado = extensiones.reservado_de(ids)
    resultado = {}
    for i in ids:
        actual, vigente = sumas.get(i, (CERO, CERO))
        vigente = vigente or CERO
        minimo = propias[i]["cant_min_insumo"]
        transito = propias[i]["cant_transito_insumo"]
        libre = vigente - reservado[i]
        resultado[i] = Existencia(
            actual=actual,
            vigente=vigente,
            reservado=reservado[i],
            libre=libre,
            transito=transito,
            minimo=minimo,
            bajo_minimo=minimo > 0 and libre + transito < minimo,
            inconsistente=vigente < reservado[i],
        )
    return resultado


def disponible_para_planificar(ids, fecha):
    """``{id: Decimal}``: ``max(0, libre a la fecha)``. No cuenta los lotes que ya estarán vencidos en ``fecha`` (regla 8 de 8.4)."""
    return {i: max(CERO, e.libre) for i, e in existencias(ids, fecha).items()}


def proponer_lotes_fefo(iin_id, cantidad, fecha):
    """FEFO (sección 2): ordena por vencimiento ascendente (los que no vencen, al final, del ingresado antes al más nuevo y por id).
    No propone lotes vencidos a ``fecha``, agotados ni el faltante sin lote. Devuelve ``Propuesta(partes, resto)``."""
    lotes = list(
        LoteInsumo.objects.filter(
            Q(fecha_vencimiento__isnull=True) | Q(fecha_vencimiento__gte=fecha),
            insumo_invernadero_id=iin_id,
            es_faltante_sin_lote=False,
            cantidad_disponible__gt=0,
        )
    )
    lotes.sort(key=lambda l: (l.fecha_vencimiento is None, l.fecha_vencimiento or fecha, l.fecha_ingreso, l.pk))
    falta = Decimal(cantidad)
    partes = []
    for lote in lotes:
        if falta <= 0:
            break
        tomado = min(falta, lote.cantidad_disponible)
        partes.append((lote.pk, tomado))
        falta -= tomado
    return Propuesta(partes, max(falta, CERO))


def ordenes_sin_cobertura(iin_id, hoy=None, vigente=None):
    """Las ``OrdenQueReserva`` que el stock vigente no cubre, de la más cercana a la más lejana (por id si empatan): se cubren en
    ese orden con el stock vigente que no sea negativo, y las que no alcanzan se devuelven (sección 1, «Sin cobertura»).
    ``vigente`` (opcional) es un stock vigente HIPOTÉTICO (el que quedaría tras un ajuste, extensión 12b de CMP-AJT-STK); sin él,
    se lee el real."""
    from inventario import extensiones

    if vigente is None:
        vigente = existencias([iin_id], hoy)[iin_id].vigente
    cubierto = max(CERO, vigente)
    acumulado = CERO
    sin_cobertura = []
    for orden in extensiones.ordenes_que_reservan([iin_id])[iin_id]:
        acumulado += Decimal(str(orden.cantidad))
        if acumulado > cubierto:
            sin_cobertura.append(orden)
    return sin_cobertura


# ---- escritura: salida por consumo (sección 3 de docs/patrones/stock.md) ----


def _partes_validadas(partes, unidad):
    """``{lote_id: Decimal}`` con las partes sumadas por lote (un cambio de cantidad = un movimiento, regla 1 de 8.19). Cada cantidad
    se valida con los decimales de la unidad del insumo y tiene que ser mayor que cero: si no, ``ValueError`` (es un error de uso de
    quien llama, no de la persona)."""
    juntas = {}
    for lote_id, cantidad in partes:
        try:
            cantidad = validar_cantidad(cantidad, unidad)
        except ValidationError as error:
            raise ValueError(f"Cantidad inválida para el lote {lote_id}: {error.messages[0]}") from error
        if cantidad <= 0:
            raise ValueError(f"La cantidad del lote {lote_id} tiene que ser mayor que cero.")
        juntas[lote_id] = juntas.get(lote_id, CERO) + cantidad
    return juntas


def registrar_salida_por_consumo(iin_id, partes, *, origen_id, fecha=None):
    """Descuenta un consumo de los lotes de un ``InsumoInvernadero`` y devuelve los ``MovimientoInsumo`` creados (docs/api/stock.md).

    La llama `produccion` dentro de su transacción, con el invernadero ya bloqueado (contrato de D-40); no audita (lo hace quien llama).
    - ``partes``: ``[(lote_id, cantidad)]``. Cada cantidad se valida con los decimales de la unidad y es mayor que cero; los lotes son
      lotes comunes de esta existencia (``ValueError`` si no, sin cambiar nada). Un lote repetido se suma.
    - ``origen_id`` (obligatorio, D-52 punto 5): el id del ``OrigenDocumento`` (el Consumo) que origina cada movimiento.
    - ``fecha`` (opcional, D-50 punto 7): la fecha de los movimientos, con la hora actual; sin ella, hoy.
    - Bloquea la existencia y después TODOS sus lotes, en orden de id, y los vuelve a leer (sección 5): así dos consumos o un consumo y
      un ajuste simultáneos no dejan un lote negativo ni descuentan dos veces lo mismo.
    - Crea UN movimiento «salida por consumo» por lote que cambia. Lo que un lote no cubre, o lo que ningún lote cubre, NO bloquea
      (regla 5 de 8.13): sale del faltante sin lote, que se crea con la primera salida que lo necesita (sin cantidad ingresada,
      ingreso ni vencimiento; regla 4 de 8.23) o crece si ya existe, con su propio movimiento.
    - Al final reevalúa las alertas del insumo (stock inconsistente, bajo el mínimo, vencimiento de los lotes agotados).
    """
    from inventario.servicios import alertas_de_stock  # adentro: alertas_de_stock importa este módulo

    existencia = (
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).select_related("insumo").get(pk=iin_id)
    )
    por_lote = _partes_validadas(partes, existencia.insumo.unidad_medida_insumo)
    lotes = {
        l.pk: l
        for l in LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero=existencia).order_by("id")
    }
    for lote_id in por_lote:
        if lote_id not in lotes or lotes[lote_id].es_faltante_sin_lote:
            raise ValueError(f"El lote {lote_id} no es un lote común de esta existencia.")
    ahora = timezone.now()
    if fecha is not None:  # la fecha efectiva con la hora de la operación (D-50 punto 7)
        ahora = timezone.make_aware(datetime.combine(fecha, timezone.localtime(ahora).time()))

    movimientos = []

    def salida(lote, cantidad):
        movimientos.append(
            MovimientoInsumo.objects.create(
                lote_insumo=lote,
                fecha=ahora,
                cantidad=cantidad,
                tipo_movimiento=MovimientoInsumo.TipoMovimiento.SALIDA_POR_CONSUMO,
                origen_id=origen_id,
            )
        )

    falta = CERO
    for lote_id in sorted(por_lote):
        lote = lotes[lote_id]
        tomado = min(por_lote[lote_id], lote.cantidad_disponible)
        falta += por_lote[lote_id] - tomado
        if tomado > 0:
            lote.cantidad_disponible -= tomado
            lote.save(update_fields=["cantidad_disponible"])
            salida(lote, tomado)
    if falta > 0:
        sin_lote = next((l for l in lotes.values() if l.es_faltante_sin_lote), None)
        if sin_lote is None:
            sin_lote = LoteInsumo.objects.create(
                insumo_invernadero=existencia, cantidad_disponible=CERO, es_faltante_sin_lote=True
            )
        sin_lote.cantidad_disponible -= falta
        sin_lote.save(update_fields=["cantidad_disponible"])
        salida(sin_lote, falta)
    alertas_de_stock.reevaluar_alertas_del_insumo(existencia.pk)
    return movimientos


# ---- escritura de compras: cantidad en tránsito (D-90 punto 1; docs/api/stock.md, «Escritura de compras»; regla 22 de 8.16) ----
# El tránsito es lo que se pidió y todavía no llegó: NO es stock (regla 1 de 8.19), así que no crea movimientos, no toca lotes ni ``referencia_precio``
# (regla 6 de 8.18) y no reevalúa alertas: aprobar una orden no resuelve «bajo el mínimo», se resuelve al recibir (CMP-APR-ODC postcondición d).
# Corren dentro de la transacción de quien llama, con el invernadero ya bloqueado; bloquean la existencia y la vuelven a leer. No auditan.


def _cantidad_de_transito(valor, unidad):
    """``valor`` validado con los decimales de la unidad y mayor que cero. Es un error de uso de quien llama (``ValueError``; un ``float``, ``TypeError``)."""
    try:
        cantidad = validar_cantidad(valor, unidad)
    except ValidationError as error:
        raise ValueError(f"Cantidad de tránsito inválida: {error.messages[0]}") from error
    if cantidad <= 0:
        raise ValueError("La cantidad de tránsito tiene que ser mayor que cero.")
    return cantidad


def _cambiar_transito(iin_id, cantidad, signo):
    """Bloquea y relee el ``InsumoInvernadero``, valida ``cantidad`` y le suma ``signo × cantidad`` al tránsito (nunca queda negativo: ``ValueError``)."""
    existencia = (
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).select_related("insumo").get(pk=iin_id)
    )
    cantidad = _cantidad_de_transito(cantidad, existencia.insumo.unidad_medida_insumo)
    nuevo = existencia.cant_transito_insumo + signo * cantidad
    if nuevo < 0:
        raise ValueError(f"No se puede restar {cantidad} del tránsito: solo hay {existencia.cant_transito_insumo} en tránsito.")
    existencia.cant_transito_insumo = nuevo
    existencia.save(update_fields=["cant_transito_insumo"])
    return existencia


def sumar_transito(iin_id, cantidad):
    """Suma ``cantidad`` a ``cant_transito_insumo`` del ``InsumoInvernadero`` ``iin_id`` y lo devuelve (la usa CMP-03 al aprobar una orden)."""
    return _cambiar_transito(iin_id, cantidad, 1)


def restar_transito(iin_id, cantidad):
    """Resta ``cantidad`` del tránsito y devuelve el ``InsumoInvernadero`` (la usa CMP-04 al recibir y al cerrar con faltante). ``ValueError`` si quedaría negativo."""
    return _cambiar_transito(iin_id, cantidad, -1)


# ---- escritura de compras: ingreso por recepción (D-90 punto 1; docs/api/stock.md, «Escritura de compras»; regla 4 de 8.23, regla 1 de 8.19, regla 22 de 8.16) ----
# Es lo único que crea lotes y movimientos de «ingreso por recepción» (regla 1 de 8.19: solo `inventario` toca lotes y movimientos). Corre dentro de la transacción de quien
# llama (`compras`), con el invernadero ya bloqueado; bloquea la existencia y sus lotes en orden de id, los vuelve a leer y NO audita (lo hace el caso de uso).


def _partes_de_ingreso(partes, insumo, hoy_):
    """``[(Decimal, date | None)]`` con las partes de un ingreso validadas, o ``ValueError`` (error de uso de quien llama, no de la persona): al menos una parte; cada cantidad con
    los decimales de la unidad y mayor que cero; el vencimiento obligatorio y nunca pasado si el insumo lo controla (un lote vence desde el día siguiente a su fecha, así que hoy
    sirve) y ausente si no lo controla."""
    partes = list(partes)
    if not partes:
        raise ValueError("Un ingreso por recepción necesita al menos una parte.")
    validadas = []
    for cantidad, vencimiento in partes:
        try:
            cantidad = validar_cantidad(cantidad, insumo.unidad_medida_insumo)
        except ValidationError as error:
            raise ValueError(f"Cantidad inválida para el ingreso: {error.messages[0]}") from error
        if cantidad <= 0:
            raise ValueError("La cantidad de cada parte tiene que ser mayor que cero.")
        if insumo.controla_vencimiento:
            if vencimiento is None:
                raise ValueError(f"{insumo.nombre_insumo} controla el vencimiento: cada parte necesita su fecha.")
            if vencimiento < hoy_:
                raise ValueError("Un lote ya vencido no ingresa al stock: es un inconveniente de la recepción.")
        elif vencimiento is not None:
            raise ValueError(f"{insumo.nombre_insumo} no controla el vencimiento: la parte no lleva fecha.")
        validadas.append((cantidad, vencimiento))
    return validadas


def registrar_ingreso_por_recepcion(iin_id, partes, *, origen_id, fecha=None):
    """Ingresa al stock lo recibido de una línea y devuelve los ``MovimientoInsumo`` creados, en el orden en que tocó los lotes (docs/api/stock.md).

    - ``partes``: ``[(cantidad, vencimiento | None)]``; ``origen_id`` (obligatorio, D-52): el id de la ``Recepcion`` que origina cada movimiento; ``fecha`` (opcional): la del movimiento
      y la de ingreso de los lotes nuevos, con la hora actual; sin ella, hoy.
    - Valida todo antes de escribir y resta el tránsito por el total antes de crear nada: si algo falla (``ValueError``, también un tránsito que quedaría negativo), no cambia nada.
    - Cubre primero el **faltante sin lote** (regla 4 de 8.23; lo deja como mucho en 0) con las primeras partes, en orden, y crea un lote nuevo por cada parte con lo que sobra, con su
      vencimiento. Un movimiento «ingreso por recepción» por lote tocado, el faltante incluido (regla 1 de 8.19).
    - No cambia ``referencia_precio`` (regla 6 de 8.18). Al final reevalúa las alertas del insumo: la de «bajo el mínimo» se resuelve si ya no corresponde (regla 12 de 8.15)."""
    from inventario.servicios import alertas_de_stock  # adentro: alertas_de_stock importa este módulo

    existencia = (
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).select_related("insumo").get(pk=iin_id)
    )
    hoy_ = hoy()
    validadas = _partes_de_ingreso(partes, existencia.insumo, hoy_)
    _cambiar_transito(existencia.pk, sum((cantidad for cantidad, _ in validadas), CERO), -1)  # ValueError si no hay tanto en tránsito: antes de escribir
    lotes = list(LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero=existencia).order_by("id"))
    sin_lote = next((l for l in lotes if l.es_faltante_sin_lote), None)
    deuda = -sin_lote.cantidad_disponible if sin_lote is not None and sin_lote.cantidad_disponible < 0 else CERO

    por_cubrir, nuevos = deuda, []
    for cantidad, vencimiento in validadas:  # el faltante absorbe las primeras partes; lo que sobra de cada una forma su lote
        para_el_faltante = min(por_cubrir, cantidad)
        por_cubrir -= para_el_faltante
        if cantidad > para_el_faltante:
            nuevos.append((cantidad - para_el_faltante, vencimiento))
    cubierto = deuda - por_cubrir

    ahora = timezone.now()
    if fecha is not None:
        ahora = timezone.make_aware(datetime.combine(fecha, timezone.localtime(ahora).time()))
    movimientos = []

    def ingreso(lote, cantidad):
        movimientos.append(
            MovimientoInsumo.objects.create(
                lote_insumo=lote,
                fecha=ahora,
                cantidad=cantidad,
                tipo_movimiento=MovimientoInsumo.TipoMovimiento.INGRESO_POR_RECEPCION,
                origen_id=origen_id,
            )
        )

    if cubierto > 0:
        sin_lote.cantidad_disponible += cubierto
        sin_lote.save(update_fields=["cantidad_disponible"])
        ingreso(sin_lote, cubierto)
    for cantidad, vencimiento in nuevos:
        nuevo = LoteInsumo.objects.create(
            insumo_invernadero=existencia,
            cantidad_ingresada=cantidad,
            cantidad_disponible=cantidad,
            fecha_ingreso=fecha or hoy_,
            fecha_vencimiento=vencimiento,
        )
        ingreso(nuevo, cantidad)
    alertas_de_stock.reevaluar_alertas_del_insumo(existencia.pk)
    return movimientos


def lotes_de_ingreso(movimiento_ids):
    """``[(LoteInsumo, Decimal)]``: de los movimientos de ingreso por recepción de ``movimiento_ids``, los lotes que crearon (**sin** el faltante sin lote) y lo ingresado en cada uno, en el
    orden de los movimientos (D-90 punto 4: «el lote creado por esa recepción»; lo usa CMP-06 para «lo máximo corregible»). Lectura: no bloquea ni escribe."""
    movimientos = (
        MovimientoInsumo.objects.filter(
            pk__in=list(movimiento_ids),
            tipo_movimiento=MovimientoInsumo.TipoMovimiento.INGRESO_POR_RECEPCION,
            lote_insumo__es_faltante_sin_lote=False,
        )
        .select_related("lote_insumo")
        .order_by("id")
    )
    return [(m.lote_insumo, m.cantidad) for m in movimientos]


# ---- escritura de compras: salida por corrección de recepción (CMP-06; D-90 puntos 1 y 2; docs/api/stock.md, «Escritura de compras»; regla 1 de 8.19, regla 22 de 8.16) ----
# La única función que crea movimientos «salida por corrección de recepción»: baja un lote creado por una recepción y devuelve esa cantidad al tránsito (lo corregido vuelve a estar pendiente de
# recibir). Corre dentro de la transacción de quien llama (`compras`), con el invernadero ya bloqueado; bloquea la existencia y sus lotes en orden de id, los vuelve a leer y NO audita.


def registrar_salida_por_correccion_de_recepcion(lote_id, cantidad, *, origen_id):
    """Descuenta ``cantidad`` de un lote creado por una recepción y devuelve el ``MovimientoInsumo`` «salida por corrección de recepción» (docs/api/stock.md).

    - ``lote_id``: un lote común (no el faltante sin lote); ``cantidad``: con los decimales de la unidad, mayor que cero y **no mayor que lo que el lote conserva** (el lote nunca queda en
      negativo); ``origen_id`` (obligatorio, D-90 punto 2): el id de la ``CorreccionRecepcion`` que origina el movimiento. Todo error es ``ValueError`` (error de uso de quien llama: ``compras``
      ya verificó con todo bloqueado) y se valida **antes** de escribir, así que no cambia nada.
    - Crea UN movimiento (regla 1 de 8.19), suma ``cantidad`` al tránsito de la existencia (``cant_transito_insumo``, regla 22 de 8.16: esa mercadería vuelve a estar pendiente) y reevalúa las
      alertas del insumo (reglas 11 y 12 de 8.15: pueden reactivarse «bajo el mínimo» o «stock inconsistente»). No cambia ``referencia_precio`` (regla 6 de 8.18)."""
    from inventario.servicios import alertas_de_stock  # adentro: alertas_de_stock importa este módulo

    previo = LoteInsumo.objects.filter(pk=lote_id).values_list("insumo_invernadero_id", flat=True).first()
    if previo is None:
        raise ValueError(f"El lote {lote_id} no existe.")
    existencia = InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).select_related("insumo").get(pk=previo)
    lotes = {l.pk: l for l in LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero=existencia).order_by("id")}  # todos, en orden de id, y releídos
    lote = lotes.get(lote_id)
    if lote is None or lote.es_faltante_sin_lote:
        raise ValueError(f"El lote {lote_id} no es un lote común de esta existencia.")
    try:
        cantidad = validar_cantidad(cantidad, existencia.insumo.unidad_medida_insumo)
    except ValidationError as error:
        raise ValueError(f"Cantidad inválida para la corrección: {error.messages[0]}") from error
    if cantidad <= 0:
        raise ValueError("La cantidad de la corrección tiene que ser mayor que cero.")
    if cantidad > lote.cantidad_disponible:
        raise ValueError(f"El lote {lote_id} solo conserva {lote.cantidad_disponible}: no se pueden descontar {cantidad}.")
    lote.cantidad_disponible -= cantidad
    lote.save(update_fields=["cantidad_disponible"])
    movimiento = MovimientoInsumo.objects.create(
        lote_insumo=lote,
        cantidad=cantidad,
        tipo_movimiento=MovimientoInsumo.TipoMovimiento.SALIDA_POR_CORRECCION_DE_RECEPCION,
        origen_id=origen_id,
    )
    _cambiar_transito(existencia.pk, cantidad, 1)
    alertas_de_stock.reevaluar_alertas_del_insumo(existencia.pk)
    return movimiento
