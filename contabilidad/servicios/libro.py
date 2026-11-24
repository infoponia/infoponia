# Libro de gestión, solo lectura (D-84 punto 8): saldos, movimientos por cuenta y totales por período, calculados con consultas agregadas sobre
# `MovimientoContable` (los saldos no se guardan). No escribe, no bloquea y no audita. Las cuentas de resultado empiezan en cero en cada
# ejercicio; las patrimoniales arrastran lo acumulado de los ejercicios de fecha de inicio menor. Sin refundición (H2.3).
from collections import namedtuple
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q, Sum
from django.http import Http404

from contabilidad import extensiones
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable, MovimientoContable
from core.models import RegistroAuditoria, Usuario, rol_de

Tipo = CuentaContable.Tipo
CERO = Decimal("0.00")
# Saldo normal: deudor (Debe − Haber) en activo y resultado negativo; acreedor (Haber − Debe) en el resto (H7).
DEUDORAS = (Tipo.ACTIVO, Tipo.RESULTADO_NEGATIVO)
PATRIMONIALES = (Tipo.ACTIVO, Tipo.PASIVO, Tipo.PATRIMONIO_NETO)

Saldo = namedtuple("Saldo", "debe haber saldo_inicial saldo contrario")
MovimientoConSaldo = namedtuple("MovimientoConSaldo", "movimiento saldo")
Resultado = namedtuple("Resultado", "ingresos egresos resultado")
# Una página de la vista por cuenta (100 movimientos por página, «Paginación» de CON-CNS-LGS) y la ficha de un asiento.
PaginaDeMovimientos = namedtuple("PaginaDeMovimientos", "filas numero total_paginas cantidad saldo_inicial saldo_final")
FichaDeAsiento = namedtuple(
    "FichaDeAsiento", "asiento movimientos total origen_texto origen_url registrado_por anula anulado_por"
)

POR_PAGINA_ASIENTOS = 50
POR_PAGINA_MOVIMIENTOS = 100
TIPOS_DE_ASIENTO = ("automatico", "manual", "contraasiento")


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


def _saldo_inicial_de_cuenta(cuenta, ejercicio):
    """Lo que arrastra la cuenta al empezar el ejercicio: el saldo de los ejercicios anteriores si es patrimonial; cero si es de resultado (regla 4)."""
    if cuenta.tipo_cuenta not in PATRIMONIALES:
        return CERO
    return _con_saldo_segun_naturaleza(
        cuenta.tipo_cuenta,
        *_sumas(
            MovimientoContable.objects.filter(
                cuenta=cuenta, asiento__ejercicio__fecha_inicio_ejercicio__lt=ejercicio.fecha_inicio_ejercicio
            )
        ),
    )


def movimientos_de_cuenta(codigo, ejercicio_id):
    """Los movimientos de la cuenta en el ejercicio, con su saldo acumulado, para la vista por cuenta (lista de `MovimientoConSaldo`).

    Orden: fecha del asiento, número de asiento e id (el número indica orden de registro, no de fecha, H8). El saldo acumulado parte
    del saldo inicial (cero en las cuentas de resultado) y sigue la naturaleza de la cuenta. Cada movimiento trae su asiento.
    """
    cuenta = _cuenta(codigo)
    ejercicio = EjercicioContable.objects.get(pk=ejercicio_id)
    saldo = _saldo_inicial_de_cuenta(cuenta, ejercicio)
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


# --- CON-CNS-LGS: lo que consulta la pantalla (CON-03a) ---------------------------------------------------------------------------------------------


def _exigir_consulta(actor):
    """Precondición a de CON-CNS-LGS: cuenta activa de Contador o de Gerente; si no, `PermissionDenied` (regla 1, X3)."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) not in (Usuario.Rol.CONTADOR, Usuario.Rol.GERENTE):
        raise PermissionDenied("Solo el Contador y el Gerente consultan el libro de gestión.")


def listar_asientos(
    actor, ejercicio_id=None, desde=None, hasta=None, tipo=None, origen_tipo=None, cuenta=None, anulados=None, texto=""
):
    """Vista cronológica (regla 2 de CON-CNS-LGS): `QuerySet` de asientos ordenado por `(fecha_asiento, numero_asiento)`.

    El ejercicio por defecto es el abierto (sin abierto ni elegido, no hay asientos). `desde` y `hasta` son inclusivos; `tipo` es `automatico`,
    `manual` o `contraasiento` (otro valor es un error de programación: `ValueError`); `origen_tipo` es un valor de `OrigenDocumento.Tipo`;
    `cuenta`, un código de cuenta; `anulados`, `True`/`False`/`None`; `texto` busca en la descripción, en el número exacto y en el identificador del
    origen. No escribe ni audita (regla 9, SEG-14). Trae movimientos, cuentas, origen y ejercicio de una vez: sin consultas por fila.
    """
    _exigir_consulta(actor)
    if tipo not in (None, "") and tipo not in TIPOS_DE_ASIENTO:
        raise ValueError(f"Tipo de asiento desconocido: {tipo!r} (usá {', '.join(TIPOS_DE_ASIENTO)}).")
    if ejercicio_id in (None, ""):
        abierto = EjercicioContable.objects.filter(estado_ejercicio=EjercicioContable.Estado.ABIERTO).first()
        if abierto is None:
            return AsientoContable.objects.none()
        ejercicio_id = abierto.pk
    asientos = AsientoContable.objects.filter(ejercicio_id=ejercicio_id)
    if desde:
        asientos = asientos.filter(fecha_asiento__gte=desde)
    if hasta:
        asientos = asientos.filter(fecha_asiento__lte=hasta)
    if tipo == "automatico":
        asientos = asientos.filter(origen__isnull=False)
    elif tipo == "manual":
        asientos = asientos.filter(origen__isnull=True, anula__isnull=True)
    elif tipo == "contraasiento":
        asientos = asientos.filter(anula__isnull=False)
    if origen_tipo:
        asientos = asientos.filter(origen__tipo=origen_tipo)
    if cuenta:
        asientos = asientos.filter(
            Exists(MovimientoContable.objects.filter(asiento=OuterRef("pk"), cuenta__codigo_cuenta=cuenta))
        )
    if anulados is not None:
        asientos = asientos.filter(contraasiento__isnull=not anulados)
    texto = (texto or "").strip()
    if texto:
        condicion = Q(descripcion_asiento__icontains=texto)
        if texto.isdigit():
            condicion |= Q(numero_asiento=int(texto)) | Q(origen_id=int(texto))
        asientos = asientos.filter(condicion)
    return (
        asientos.select_related("origen", "ejercicio", "contraasiento")
        .prefetch_related("movimientos__cuenta")
        .order_by("fecha_asiento", "numero_asiento")
    )


def ficha_de_asiento(actor, ejercicio_id, numero):
    """Ficha del asiento (regla 5): movimientos, total, origen con su enlace, quién lo registró y el asiento que anula o que lo anuló.

    «Quién registró» (regla 16 de 8.20): el manual y el contraasiento guardan el usuario solo en la auditoría (`alta_asiento_contable`); un
    automático no lo muestra. Un asiento que no existe en ese ejercicio es 404.
    """
    _exigir_consulta(actor)
    try:
        asiento = AsientoContable.objects.select_related(
            "origen", "ejercicio", "anula__ejercicio", "contraasiento__ejercicio"
        ).get(ejercicio_id=ejercicio_id, numero_asiento=numero)
    except AsientoContable.DoesNotExist:
        raise Http404("No existe ese asiento.") from None
    movimientos = list(asiento.movimientos.select_related("cuenta").order_by("id"))
    total = sum((m.importe_movimiento for m in movimientos if m.tipo_movimiento == DEBE), CERO)
    origen_texto = origen_url = None
    if asiento.origen is not None:
        origen_texto, origen_url = extensiones.enlace_de_origen(asiento.origen)
    registrado_por = None
    if asiento.origen_id is None:
        registro = (
            RegistroAuditoria.objects.filter(
                accion=RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE,
                afectados__contains=[{"modelo": "contabilidad.asientocontable", "id": asiento.pk}],
            )
            .select_related("usuario")
            .order_by("id")
            .first()
        )
        registrado_por = registro.usuario if registro else None
    anulado_por = asiento.contraasiento if hasattr(asiento, "contraasiento") else None
    return FichaDeAsiento(asiento, movimientos, total, origen_texto, origen_url, registrado_por, asiento.anula, anulado_por)


def pagina_de_movimientos_de_cuenta(codigo, ejercicio_id, pagina=1, por_pagina=POR_PAGINA_MOVIMIENTOS):
    """Una página de la vista por cuenta (regla 3 y «Paginación»): los movimientos con su saldo acumulado.

    El saldo de la primera fila es el saldo inicial más lo de esa cuenta que quedó antes (una suma agregada: no recorre las páginas anteriores).
    Una página fuera de rango muestra la última; un valor que no es número, la primera.
    """
    cuenta = _cuenta(codigo)
    ejercicio = EjercicioContable.objects.get(pk=ejercicio_id)
    inicial = _saldo_inicial_de_cuenta(cuenta, ejercicio)
    del_ejercicio = (
        MovimientoContable.objects.filter(cuenta=cuenta, asiento__ejercicio_id=ejercicio_id)
        .select_related("asiento", "cuenta")
        .order_by("asiento__fecha_asiento", "asiento__numero_asiento", "id")
    )
    paginador = Paginator(del_ejercicio, por_pagina)
    try:
        numero = int(pagina)
    except (TypeError, ValueError):
        numero = 1
    objeto = paginador.get_page(numero)
    saldo = inicial
    del_modelo = list(objeto)
    if del_modelo:
        primero = del_modelo[0]
        fecha, num = primero.asiento.fecha_asiento, primero.asiento.numero_asiento
        antes = del_ejercicio.filter(
            Q(asiento__fecha_asiento__lt=fecha)
            | Q(asiento__fecha_asiento=fecha, asiento__numero_asiento__lt=num)
            | Q(asiento__fecha_asiento=fecha, asiento__numero_asiento=num, id__lt=primero.pk)
        )
        saldo += _con_saldo_segun_naturaleza(cuenta.tipo_cuenta, *_sumas(antes))
    filas = []
    for movimiento in del_modelo:
        a_favor = (movimiento.tipo_movimiento == DEBE) == (cuenta.tipo_cuenta in DEUDORAS)
        saldo = saldo + movimiento.importe_movimiento if a_favor else saldo - movimiento.importe_movimiento
        filas.append(MovimientoConSaldo(movimiento, saldo))
    final = inicial + _con_saldo_segun_naturaleza(cuenta.tipo_cuenta, *_sumas(del_ejercicio))
    return PaginaDeMovimientos(filas, objeto.number, paginador.num_pages, paginador.count, inicial, final)


def total_de_los_asientos(asientos):
    """Total del Debe (igual al del Haber en cada asiento) de TODOS los asientos de un `QuerySet` de `listar_asientos`, aunque la pantalla muestre
    una sola página: una consulta agregada, para el pie «Totales» de la vista cronológica."""
    suma = MovimientoContable.objects.filter(asiento__in=asientos.order_by().values("pk"), tipo_movimiento=DEBE).aggregate(
        total=Sum("importe_movimiento")
    )
    return suma["total"] or CERO
