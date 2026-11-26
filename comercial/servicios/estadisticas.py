# COM-CNS-EST · Consultar Estadísticas Comerciales (COM-08c; docs/casos_de_uso/comercial/estadisticas.md; D-94, puntos 1 y 15).
# SOLO LECTURA: ninguna función de este módulo escribe ni audita (postcondición a). `filtros_de_estadisticas` valida y normaliza lo que llega de la URL; `estadisticas` calcula los ocho
# indicadores de un período; `resultados_del_mes` es lo que muestra el panel del Vendedor. EST-03 (app `estadisticas`, nivel 8) llama a las dos primeras con un período cualquiera.
#
# Convención del período: la misma que `estadisticas/periodos.py` (EST-01 y EST-02; D-93 punto 2): días inclusivos, `desde <= hasta`, `hasta <= hoy` y un máximo de 366 días. `comercial` (nivel 6) no
# puede importar de `estadisticas` (nivel 8, regla A1 de D-37): la convención se repite acá y una prueba de `estadisticas` (`test_convencion_de_periodo.py`) compara los límites de las dos.
# Rendimiento: una consulta agregada por indicador (`values().annotate()`), con los filtros en la base; nunca una consulta por fila.

import calendar
import re
from collections import namedtuple
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, DateField, DecimalField, DurationField, Exists, ExpressionWrapper, F, Min, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.urls import reverse

from comercial.models import Cliente, CompraVenta, Contrato, DetalleEntrega, DetalleVenta, Entrega, IntentoFallido, ReservaStock, SolicitudRevision
from core.models import Usuario, Vendedor, rol_de
from maestros.models import Invernadero, Variedad
from produccion.models import OrdenTrabajo

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
GERENTE, VENDEDOR = Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR
MAXIMO_DE_DIAS = 366  # D-94 punto 15; igual que `estadisticas.periodos.MAXIMO_DE_DIAS`
CONCRETADA = OrdenTrabajo.Estado.CONCRETADA
CERO = Decimal("0.00")
MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
MONEDA = DecimalField(max_digits=14, decimal_places=2)
UN_DIA = timedelta(days=1)

# ---- Tipos que devuelven las funciones (las pruebas leen estos campos) ----

VentaDeVariedad = namedtuple("VentaDeVariedad", "variedad plantas monto")
Ventas = namedtuple("Ventas", "total entregas plantas variedades")
Puntualidad = namedtuple("Puntualidad", "total a_tiempo con_retraso porcentaje_a_tiempo porcentaje_con_retraso promedio_de_retraso intentos_fallidos")
Incumplimientos = namedtuple("Incumplimientos", "cantidad quejas discrepancias descuentos pagos_en_dinero total")
Cobranza = namedtuple("Cobranza", "pendiente_total pendiente_cantidad en_mora_total en_mora_cantidad hasta_30 de_31_a_60 mas_de_60")
Faltantes = namedtuple("Faltantes", "con_faltante rechazados_por_cantidad rechazados_al_recibir cancelados")
ClienteConMasCompras = namedtuple("ClienteConMasCompras", "cliente_id nombre entregas monto porcentaje url_compra_ventas url_suministros")
Enlaces = namedtuple("Enlaces", "compra_ventas suministros entregas solicitudes cobranza faltantes")
Estadisticas = namedtuple("Estadisticas", "filtros ventas puntualidad incumplimientos cobranza faltantes clientes enlaces")
ResultadosDelMes = namedtuple("ResultadosDelMes", "desde hasta ventas puntualidad incumplimientos")


@dataclass(frozen=True)
class FiltrosDeEstadisticas:
    """Los filtros normalizados (reglas 1, 2 y 11): el período (`desde` y `hasta`, inclusivos), `periodo` («AAAA-MM» o «rango»), el invernadero y, solo para el Gerente, el Vendedor, más las opciones
    de los desplegables: `meses` `((«AAAA-MM», texto), ...)`, `invernaderos` y `vendedores` `((id, nombre), ...)`. EST-03 puede armar uno con solo `desde` y `hasta`."""

    desde: date
    hasta: date
    periodo: str = ""
    invernadero_id: int | None = None
    vendedor_id: int | None = None
    meses: tuple = ()
    invernaderos: tuple = ()
    vendedores: tuple = ()


def _rechazar(codigo, mensaje, campo="__all__"):
    """Un `ValidationError` con código estable (patrón de `comercial`; el extracto lo llama `ErrorComercial`)."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _exigir_actor(actor):
    """Regla 1 y precondición a: un Vendedor o un Gerente con la cuenta activa; cualquier otro, `PermissionDenied` (`sin_permiso`)."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) not in (GERENTE, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


# ---- Filtros (reglas 1, 2 y 11) ----


def _texto_del_mes(anio, mes, hasta_hoy):
    return f"{MESES[mes - 1]} de {anio}" + (" (hasta hoy)" if hasta_hoy else "")


def _meses_ofrecidos(hoy, pedido):
    """El mes de `hoy` y los doce anteriores, del más nuevo al más viejo; el `pedido` (un «AAAA-MM») se suma al final si es más viejo."""
    meses = []
    for atras in range(13):
        indice = hoy.year * 12 + hoy.month - 1 - atras
        anio, mes = divmod(indice, 12)
        meses.append((f"{anio}-{mes + 1:02d}", _texto_del_mes(anio, mes + 1, atras == 0)))
    if pedido and pedido not in [valor for valor, _ in meses]:
        meses.append((pedido, _texto_del_mes(int(pedido[:4]), int(pedido[5:]), False)))
    return tuple(meses)


def _fecha(texto, campo):
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise _rechazar("periodo_invalido", "Escribí las fechas con el formato día/mes/año.", campo) from None


def _periodo(get, hoy):
    """`(desde, hasta, periodo)` según la URL: un mes («2026-10»), un rango (`periodo=rango` o solo `desde`/`hasta`) o, por omisión, el mes de `hoy` hasta `hoy`."""
    elegido = (get.get("periodo") or "").strip()
    desde_texto, hasta_texto = (get.get("desde") or "").strip(), (get.get("hasta") or "").strip()
    if not elegido and not (desde_texto or hasta_texto):
        return hoy.replace(day=1), hoy, f"{hoy.year}-{hoy.month:02d}"
    if elegido and elegido != "rango":
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", elegido):
            raise _rechazar("periodo_invalido", "El período elegido no existe.", "periodo")
        anio, mes = int(elegido[:4]), int(elegido[5:])
        primero = date(anio, mes, 1)
        if primero > hoy:
            raise _rechazar("periodo_invalido", "El período no puede terminar después de hoy.", "periodo")
        return primero, min(date(anio, mes, calendar.monthrange(anio, mes)[1]), hoy), elegido
    if not (desde_texto and hasta_texto):
        raise _rechazar("periodo_invalido", "Indicá las dos fechas.", "periodo")
    desde, hasta = _fecha(desde_texto, "periodo"), _fecha(hasta_texto, "periodo")
    if desde > hasta:
        raise _rechazar("periodo_invalido", "La fecha “desde” no puede ser posterior a “hasta”.", "periodo")
    if hasta > hoy:
        raise _rechazar("periodo_invalido", "El período no puede terminar después de hoy.", "periodo")
    if (hasta - desde).days + 1 > MAXIMO_DE_DIAS:
        raise _rechazar("periodo_invalido", "El período no puede ser mayor que un año.", "periodo")
    return desde, hasta, "rango"


def _invernaderos_del_alcance(actor):
    """`[(id, nombre)]` por nombre: el Gerente, todos; el Vendedor, sus invernaderos activos y los de cualquier estado donde tuvo entregas o reservas de sus contratos (una consulta)."""
    if rol_de(actor) == GERENTE:
        consulta = Invernadero.objects.all()
    else:
        de_entregas = Entrega.objects.en_alcance_de(actor).values("invernadero_id")
        de_reservas = ReservaStock.objects.filter(Q(detalle_venta__compra_venta__vendedor_id=actor.pk) | Q(detalle_suministro__suministro__vendedor_id=actor.pk)).values("invernadero_id")
        consulta = Invernadero.objects.filter(
            Q(vendedor_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO) | Q(pk__in=de_entregas) | Q(pk__in=de_reservas)
        )
    return list(consulta.order_by("nombre_invernadero", "pk").values_list("pk", "nombre_invernadero"))


def _vendedores_con_contratos():
    """`[(id, nombre)]` de todo Vendedor con algún contrato, activo o no (una consulta)."""
    vendedores = Vendedor.objects.filter(contratos__isnull=False).distinct().order_by("last_name", "first_name", "pk")
    return [(v.pk, v.get_full_name()) for v in vendedores]


def _entero(texto):
    texto = (texto or "").strip() if not isinstance(texto, int) else str(texto)
    return int(texto) if texto.isdigit() else None


def filtros_de_estadisticas(actor, get, hoy):
    """Reglas 1, 2 y 11: valida y normaliza el período, el invernadero y el Vendedor. `PermissionDenied` (`sin_permiso`) si no es un Vendedor o un Gerente activo; `ValidationError` con
    `periodo_invalido`, `invernadero_fuera_de_alcance` o `vendedor_no_admitido`. Lectura pura; `hoy` lo pone quien llama (la fecha en la zona del sistema, regla 11)."""
    _exigir_actor(actor)
    desde, hasta, periodo = _periodo(get, hoy)
    invernaderos = _invernaderos_del_alcance(actor)
    pedido = (get.get("invernadero") or "").strip()
    invernadero_id = None
    if pedido:
        invernadero_id = _entero(pedido)
        if invernadero_id not in [pk for pk, _ in invernaderos]:
            raise _rechazar("invernadero_fuera_de_alcance", "Elegí uno de tus invernaderos.", "invernadero")
    pedido = (get.get("vendedor") or "").strip()
    vendedores, vendedor_id = (), None
    if rol_de(actor) == GERENTE:
        vendedores = tuple(_vendedores_con_contratos())
    if pedido:
        vendedor_id = _entero(pedido)
        if rol_de(actor) != GERENTE or vendedor_id not in [pk for pk, _ in vendedores]:
            raise _rechazar("vendedor_no_admitido", "Elegí uno de los Vendedores de la lista.", "vendedor")
    pedido_de_mes = periodo if re.fullmatch(r"\d{4}-\d{2}", periodo) else ""
    return FiltrosDeEstadisticas(desde, hasta, periodo, invernadero_id, vendedor_id, _meses_ofrecidos(hoy, pedido_de_mes), tuple(invernaderos), vendedores)


def _verificar_alcance(actor, filtros):
    """`estadisticas` no se fía de los filtros que recibe (EST-03 puede armar los suyos): el Vendedor no filtra por Vendedor; el invernadero y el Vendedor tienen que estar en el alcance."""
    if filtros.vendedor_id is not None:
        if rol_de(actor) != GERENTE or not Contrato.objects.filter(vendedor_id=filtros.vendedor_id).exists():
            raise _rechazar("vendedor_no_admitido", "Elegí uno de los Vendedores de la lista.", "vendedor")
    if filtros.invernadero_id is not None:
        if rol_de(actor) == GERENTE:
            esta = Invernadero.objects.filter(pk=filtros.invernadero_id).exists()
        else:
            esta = filtros.invernadero_id in [pk for pk, _ in _invernaderos_del_alcance(actor)]
        if not esta:
            raise _rechazar("invernadero_fuera_de_alcance", "Elegí uno de tus invernaderos.", "invernadero")


# ---- Las consultas base ----


def _entregas(actor, filtros):
    """Las entregas del alcance de `actor` (regla 1), del invernadero de origen y del Vendedor pedidos (D-94 punto 15)."""
    consulta = Entrega.objects.en_alcance_de(actor)
    if filtros.invernadero_id is not None:
        consulta = consulta.filter(invernadero_id=filtros.invernadero_id)
    if filtros.vendedor_id is not None and rol_de(actor) == GERENTE:
        consulta = consulta.filter(contrato_entrega__vendedor_id=filtros.vendedor_id)
    return consulta


def _concretadas(actor, filtros):
    """Las entregas concretadas con `fecha_resolucion_orden` dentro del período: la base de los indicadores 3, 4, 7 (rechazos al recibir) y 8."""
    return _entregas(actor, filtros).filter(estado_orden=CONCRETADA, fecha_resolucion_orden__range=(filtros.desde, filtros.hasta))


def _porcentaje(parte, total):
    return None if not total else Decimal(parte) * 100 / Decimal(total)


# ---- Un indicador por función (`(actor, filtros)`; la cobranza, además, `hoy`) ----


def _ventas(actor, filtros):
    """Indicador 3 (regla 3): Σ `cant_entregada` y Σ `monto_pagar` de las líneas de las entregas concretadas en el período, de compra-ventas y de suministros, por variedad, de mayor a menor monto.
    No descuenta indemnizaciones. Una línea entregada en 0 (rechazada al recibir) no es una venta: va al indicador 7. Tres consultas."""
    base = _concretadas(actor, filtros)
    filas = list(
        DetalleEntrega.objects.filter(entrega_id__in=base.values("pk"), cant_entregada__gt=0)
        .annotate(variedad_id_=Coalesce("detalle_venta__variedad_id", "detalle_suministro__variedad_id"))
        .values("variedad_id_")
        .annotate(plantas=Sum("cant_entregada"), monto=Sum("monto_pagar"))
        .order_by("-monto", "variedad_id_")
    )
    variedades = Variedad.objects.select_related("cultivo").in_bulk([f["variedad_id_"] for f in filas]) if filas else {}
    por_variedad = tuple(VentaDeVariedad(str(variedades[f["variedad_id_"]]), f["plantas"], f["monto"]) for f in filas)
    return Ventas(sum((v.monto for v in por_variedad), CERO), base.count(), sum(v.plantas for v in por_variedad), por_variedad)


def _puntualidad(actor, filtros):
    """Indicador 4 (regla 4): de las entregas concretadas en el período, a tiempo = concretada en la fecha prometida o antes (la pactada de la venta; en un suministro, la menor `fecha_periodo` de sus líneas,
    no la programada, que pudo reprogramarse) y con retraso las demás; porcentajes y promedio de días sin redondear; y los intentos fallidos del período (en la zona horaria del sistema, regla 11). Dos consultas."""
    menor_periodo = DetalleEntrega.objects.filter(entrega_id=OuterRef("pk"), fecha_periodo__isnull=False).values("entrega_id").annotate(m=Min("fecha_periodo")).values("m")
    prometida = Coalesce(F("contrato_entrega__compraventa__fecha_pactada_venta"), Subquery(menor_periodo), output_field=DateField())
    tarde = Q(fecha_resolucion_orden__gt=F("prometida"))
    cuenta = _concretadas(actor, filtros).annotate(prometida=prometida).aggregate(
        total=Count("pk"),
        con_retraso=Count("pk", filter=tarde),
        atraso=Sum(ExpressionWrapper(F("fecha_resolucion_orden") - F("prometida"), output_field=DurationField()), filter=tarde),
    )
    total, con_retraso = cuenta["total"], cuenta["con_retraso"]
    a_tiempo = total - con_retraso
    promedio = Decimal(cuenta["atraso"].days) / Decimal(con_retraso) if con_retraso else None
    intentos = IntentoFallido.objects.filter(entrega_id__in=_entregas(actor, filtros).values("pk"), fecha_hora__date__range=(filtros.desde, filtros.hasta)).count()
    return Puntualidad(total, a_tiempo, con_retraso, _porcentaje(a_tiempo, total), _porcentaje(con_retraso, total), promedio, intentos)


def _incumplimientos(actor, filtros):
    """Indicador 5 (regla 5): las solicitudes hoy «aceptada» con `fecha_resolucion` en el período (una resolución anulada volvió a «pendiente» y no cuenta; si se aceptó otra vez, cuenta con la fecha nueva),
    por tipo, con Σ `monto_descontado` y Σ `monto_reintegrado`. Una consulta."""
    datos = SolicitudRevision.objects.filter(
        entrega_id__in=_entregas(actor, filtros).values("pk"), estado_solicitud=SolicitudRevision.Estado.ACEPTADA, fecha_resolucion__range=(filtros.desde, filtros.hasta)
    ).aggregate(
        cantidad=Count("pk"),
        quejas=Count("pk", filter=Q(tipo_solicitud=SolicitudRevision.Tipo.QUEJA)),
        discrepancias=Count("pk", filter=Q(tipo_solicitud=SolicitudRevision.Tipo.DISCREPANCIA)),
        descuentos=Sum("monto_descontado"),
        pagos=Sum("monto_reintegrado"),
    )
    descuentos, pagos = datos["descuentos"] or CERO, datos["pagos"] or CERO
    return Incumplimientos(datos["cantidad"], datos["quejas"], datos["discrepancias"], descuentos, pagos, descuentos + pagos)


def _cobranza(actor, filtros, hoy):
    """Indicador 6 (regla 6): foto a `hoy`, sin período. El monto a cobrar (total menos lo descontado por solicitudes aceptadas, MD-115) de las entregas de suministro concretadas sin un cobro vigente (un cobro
    anulado no cuenta como pago, MD-136), pendientes (vencen hoy o después) y en mora (MD-139), y las en mora por antigüedad: 1 a 30, 31 a 60 y más de 60 días. Una consulta."""
    descontado = SolicitudRevision.objects.filter(entrega_id=OuterRef("pk"), estado_solicitud=SolicitudRevision.Estado.ACEPTADA).values("entrega_id").annotate(t=Sum("monto_descontado")).values("t")
    cero = Value(CERO, output_field=MONEDA)
    por_cobrar = (
        _entregas(actor, filtros)
        .filter(estado_orden=CONCRETADA, fecha_vencimiento_pago__isnull=False)
        .exclude(lineas_de_pago__vigente=True)
        .annotate(a_cobrar=Greatest(F("monto_total_entrega") - Coalesce(Subquery(descontado, output_field=MONEDA), cero), cero, output_field=MONEDA))
        .filter(a_cobrar__gt=0)
    )
    vence = "fecha_vencimiento_pago"
    pendiente, en_mora = Q(**{f"{vence}__gte": hoy}), Q(**{f"{vence}__lt": hoy})
    hasta_30 = en_mora & Q(**{f"{vence}__gte": hoy - 30 * UN_DIA})
    de_31_a_60 = Q(**{f"{vence}__lt": hoy - 30 * UN_DIA, f"{vence}__gte": hoy - 60 * UN_DIA})
    mas_de_60 = Q(**{f"{vence}__lt": hoy - 60 * UN_DIA})
    datos = por_cobrar.aggregate(
        pendiente_total=Sum("a_cobrar", filter=pendiente), pendiente_cantidad=Count("pk", filter=pendiente),
        en_mora_total=Sum("a_cobrar", filter=en_mora), en_mora_cantidad=Count("pk", filter=en_mora),
        hasta_30=Sum("a_cobrar", filter=hasta_30), de_31_a_60=Sum("a_cobrar", filter=de_31_a_60), mas_de_60=Sum("a_cobrar", filter=mas_de_60),
    )
    return Cobranza(*(datos[campo] if campo.endswith("cantidad") else (datos[campo] or CERO) for campo in Cobranza._fields))


def _faltantes(actor, filtros):
    """Indicador 7 (regla 7; D-94 punto 15), cuatro consultas. Con faltante: `fecha_pendiente_decision` en el período. Rechazados por cantidad reducida: de esos, los que hoy están «rechazado» y no tienen una línea
    en una entrega concretada. Rechazados al recibir: líneas de venta con `cant_entregada = 0` en entregas concretadas en el período. Cancelados: detalles «cancelado» de ventas con `fecha_cancelacion_venta` en el
    período. El invernadero de un detalle es el de sus reservas: con reservas en dos invernaderos, cuenta en los dos filtros y una vez sin filtro."""
    ventas = CompraVenta.objects.en_alcance_de(actor)
    if filtros.vendedor_id is not None and rol_de(actor) == GERENTE:
        ventas = ventas.filter(vendedor_id=filtros.vendedor_id)
    detalles = DetalleVenta.objects.filter(compra_venta__in=ventas)
    if filtros.invernadero_id is not None:
        detalles = detalles.filter(Exists(ReservaStock.objects.filter(detalle_venta=OuterRef("pk"), invernadero_id=filtros.invernadero_id)))
    periodo = (filtros.desde, filtros.hasta)
    con_faltante = detalles.filter(fecha_pendiente_decision__range=periodo)
    entregado = Exists(DetalleEntrega.objects.filter(detalle_venta=OuterRef("pk"), entrega__estado_orden=CONCRETADA))
    return Faltantes(
        con_faltante.count(),
        con_faltante.filter(estado_detalle_venta=DetalleVenta.Estado.RECHAZADO).filter(~entregado).count(),
        DetalleEntrega.objects.filter(entrega_id__in=_concretadas(actor, filtros).values("pk"), detalle_venta__isnull=False, cant_entregada=0).count(),
        detalles.filter(estado_detalle_venta=DetalleVenta.Estado.CANCELADO, compra_venta__fecha_cancelacion_venta__range=periodo).count(),
    )


def _contratos(vendedor_id=None, cliente_id=None, suministros=False):
    """La URL de la lista de contratos (compra-ventas o, con `?tipo=suministro`, suministros) con el cliente y el Vendedor."""
    consulta = (["tipo=suministro"] if suministros else []) + ([f"cliente={cliente_id}"] if cliente_id else []) + ([f"vendedor={vendedor_id}"] if vendedor_id else [])
    return reverse("comercial:contratos") + (f"?{'&'.join(consulta)}" if consulta else "")


def _clientes(actor, filtros):
    """Indicador 8 (regla 8): los diez clientes con más ventas del período (el mismo cálculo del indicador 3), con la cantidad de entregas y el porcentaje sobre el total; monto descendente y, a igualdad,
    por nombre. Dos consultas."""
    filas = list(
        DetalleEntrega.objects.filter(entrega_id__in=_concretadas(actor, filtros).values("pk"), cant_entregada__gt=0)
        .values("entrega__contrato_entrega__cliente_id")
        .annotate(monto=Sum("monto_pagar"), entregas=Count("entrega_id", distinct=True))
    )
    if not filas:
        return ()
    clientes = Cliente.objects.in_bulk([f["entrega__contrato_entrega__cliente_id"] for f in filas])
    total = sum((f["monto"] for f in filas), CERO)
    orden = sorted(filas, key=lambda f: (-f["monto"], clientes[f["entrega__contrato_entrega__cliente_id"]].nombre_visible.casefold(), f["entrega__contrato_entrega__cliente_id"]))
    return tuple(
        ClienteConMasCompras(
            cliente_id=f["entrega__contrato_entrega__cliente_id"],
            nombre=clientes[f["entrega__contrato_entrega__cliente_id"]].nombre_visible,
            entregas=f["entregas"],
            monto=f["monto"],
            porcentaje=_porcentaje(f["monto"], total),
            url_compra_ventas=_contratos(filtros.vendedor_id, f["entrega__contrato_entrega__cliente_id"]),
            url_suministros=_contratos(filtros.vendedor_id, f["entrega__contrato_entrega__cliente_id"], True),
        )
        for f in orden[:10]
    )


def _enlaces(filtros):
    """Regla 10: de cada indicador a su consulta con el mismo filtro. Las pantallas de destino no admiten rango (filtran por otra fecha) ni el invernadero de las ventas: llevan los filtros que admiten."""
    entregas = reverse("comercial:entregas") + "?estado=concretada" + (f"&invernadero={filtros.invernadero_id}" if filtros.invernadero_id else "")
    solicitudes = reverse("comercial:solicitudes") + "?estado=aceptada" + (f"&vendedor={filtros.vendedor_id}" if filtros.vendedor_id else "")
    return Enlaces(_contratos(filtros.vendedor_id), _contratos(filtros.vendedor_id, suministros=True), entregas, solicitudes, reverse("comercial:cobranza"), _contratos(filtros.vendedor_id))


# ---- Las funciones públicas ----


def estadisticas(actor, filtros, hoy):
    """Reglas 3 a 8 y 10: los ocho indicadores del período de `filtros`, con los enlaces de cada uno. Acepta cualquier `desde`/`hasta` (los límites de la pantalla son de `filtros_de_estadisticas`); vuelve a
    verificar el alcance (rol, invernadero, Vendedor). Lectura pura: ninguna escritura, ninguna auditoría (postcondición a)."""
    _exigir_actor(actor)
    _verificar_alcance(actor, filtros)
    return Estadisticas(
        filtros, _ventas(actor, filtros), _puntualidad(actor, filtros), _incumplimientos(actor, filtros), _cobranza(actor, filtros, hoy), _faltantes(actor, filtros), _clientes(actor, filtros), _enlaces(filtros)
    )


def resultados_del_mes(actor, hoy):
    """Reglas 3, 4 y 5 del mes en curso (del 1 a `hoy`) para el panel del Vendedor: ventas, entregas a tiempo e indemnizado, con las mismas funciones internas que `estadisticas`."""
    _exigir_actor(actor)
    filtros = FiltrosDeEstadisticas(hoy.replace(day=1), hoy, f"{hoy.year}-{hoy.month:02d}")
    return ResultadosDelMes(filtros.desde, filtros.hasta, _ventas(actor, filtros), _puntualidad(actor, filtros), _incumplimientos(actor, filtros))
