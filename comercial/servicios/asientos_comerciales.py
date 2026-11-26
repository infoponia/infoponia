# Asientos automáticos de los casos de uso de `comercial` con stock (CON-04c; D-92 puntos 2 a 6 y 9, D-86, `docs/api/asientos.md`).
# Cada caso de uso (cosecha, merma en cámara, vencimiento y entrega) llama a estas funciones DENTRO de su transacción, con todos sus bloqueos de negocio
# ya tomados y después de crear el documento de origen: `registrar_asiento_automatico` bloquea el ejercicio AL FINAL (`docs/patrones/asientos.md`, sección 2).
# Devuelven el `AsientoContable` o `None` si el importe es cero (H11). Importes a dos decimales con ROUND_HALF_UP (D-92 punto 5); la fecha es la del hecho
# (D-92 punto 4). La merma de un lote en pie reutiliza `produccion.servicios.asientos_de_produccion.asentar_merma` (CON-04a).
from decimal import Decimal

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from comercial.models import Anulacion, Entrega
from contabilidad.models import AsientoContable
from contabilidad.servicios import asientos
from produccion.models import MovimientoStock, OrdenTrabajo
from produccion.servicios import costos

LARGO_DE_LA_DESCRIPCION = 300  # `AsientoContable.descripcion_asiento`


def asentar_salida_por_cosecha(actor, movimiento, fecha, hoy):
    """PROD-CNC-CSC postcondición f (regla 1 de «Contabilidad» de 8.9): un asiento por cada `MovimientoStock` «salida por cosecha», originado en el
    movimiento: Debe «Productos Terminados» / Haber «Productos en Proceso» por `cantidad × costo_unitario` (el costo por planta de antes de la cosecha).
    `fecha` es la efectiva de la cosecha. `None` si el importe es $0,00 (H11)."""
    importe = costos.redondear_monto(Decimal(movimiento.cantidad) * Decimal(movimiento.costo_unitario))
    return asientos.registrar_asiento_automatico(
        actor,
        movimiento,
        fecha,
        [(cuentas.PRODUCTOS_TERMINADOS, DEBE, importe), (cuentas.PRODUCTOS_EN_PROCESO, HABER, importe)],
        descripcion=f"Salida por cosecha: {movimiento.cantidad} plantas"[:LARGO_DE_LA_DESCRIPCION],
        hoy=hoy,
    )


def asentar_merma_de_partida(actor, merma, movimiento, fecha, hoy):
    """Un asiento por merma de una partida en cámara (PROD-REG-MRM postcondición i, PROD-VNC-CAM postcondición b, y la merma por vencimiento de una devolución
    en COM-CNC-ENT; regla 33 de 8.6), originado en la merma: Debe «Pérdidas por Mermas» / Haber «Productos Terminados» por `cantidad perdida × costo unitario
    de la partida` (el del `movimiento` «merma en cámara»). `fecha` es la del hecho. `None` si el importe es $0,00 (H11)."""
    importe = costos.redondear_monto(Decimal(merma.cant_merma) * Decimal(movimiento.costo_unitario))
    return asientos.registrar_asiento_automatico(
        actor,
        merma,
        fecha,
        [(cuentas.PERDIDAS_POR_MERMAS, DEBE, importe), (cuentas.PRODUCTOS_TERMINADOS, HABER, importe)],
        descripcion=merma.descripcion_evento[:LARGO_DE_LA_DESCRIPCION],
        hoy=hoy,
    )


def asentar_merma_de_entrega(actor, merma, costo, hoy):
    """COM-CNC-ENT postcondición e: un asiento por cada merma «daño en la entrega», originado en la merma: Debe «Pérdidas por Mermas» / Haber «Productos Terminados» por
    `costo`, la suma de lo perdido de cada origen por el costo de ese origen (sin promedios; regla «Costo de lo entregado, perdido o devuelto»). Fecha: la de la resolución
    (hoy). `None` si el costo es $0,00 (H11)."""
    importe = costos.redondear_monto(Decimal(costo))
    return asientos.registrar_asiento_automatico(
        actor,
        merma,
        hoy,
        [(cuentas.PERDIDAS_POR_MERMAS, DEBE, importe), (cuentas.PRODUCTOS_TERMINADOS, HABER, importe)],
        descripcion=merma.descripcion_evento[:LARGO_DE_LA_DESCRIPCION],
        hoy=hoy,
    )


def asentar_consumo_de_envase(actor, consumo, hoy):
    """COM-CNC-ENT postcondición g: un asiento por cada consumo de envase, originado en el consumo: Debe «Costo de Producción Vendida» / Haber «Insumos en Stock» por su
    `monto_consumo` (el exceso incluido, D-68 punto 2). Fecha: la de la resolución (hoy). `None` si el monto es $0,00 (H11)."""
    importe = costos.redondear_monto(Decimal(consumo.monto_consumo))
    return asientos.registrar_asiento_automatico(
        actor,
        consumo,
        hoy,
        [(cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, importe), (cuentas.INSUMOS_EN_STOCK, HABER, importe)],
        descripcion=consumo.descripcion_evento[:LARGO_DE_LA_DESCRIPCION],
        hoy=hoy,
    )


def _deudores_ya_asentados(entrega):
    """Σ `monto_total_entrega` de las entregas concretadas de la misma compra-venta, antes de esta, que TIENEN asiento (registraron su venta contra Deudores por Ventas). Las
    anteriores a CON-04c no lo tienen (D-92 punto 1, sin asientos hacia atrás): su venta no está en Deudores y se reconoce en Ventas con la última (decisión del 26/11/2026)."""
    previas = Entrega.objects.filter(contrato_entrega_id=entrega.contrato_entrega_id, estado_orden=OrdenTrabajo.Estado.CONCRETADA).exclude(pk=entrega.pk)
    con_asiento = AsientoContable.objects.filter(origen_id__in=previas.values("pk")).values("origen_id")
    return sum((e.monto_total_entrega or Decimal("0.00") for e in previas.filter(pk__in=con_asiento)), Decimal("0.00"))


def asentar_entrega(actor, entrega, hoy, *, es_venta, es_ultima, cobra, medio_pago, monto, total_a_cobrar, costo):
    """COM-CNC-ENT postcondición h: UN asiento compuesto, originado en la entrega (R012). Fecha: la de la resolución (hoy).
    - Suministro: Debe «Deudores por Ventas» / Haber «Ventas» por `monto`, el monto total de la entrega.
    - Compra-venta, regla «Venta registrada por entrega»: si no es la última, Debe Deudores / Haber Ventas por `monto`; la última, si cobra, Debe «Caja» (efectivo) o «Banco c/c»
      (los demás medios) por `total_a_cobrar` / Haber Ventas por lo que falta reconocer (lo suyo más lo de las anteriores sin asiento) y Haber Deudores por lo que las anteriores con
      asiento dejaron ahí, de modo que Deudores nunca quede con saldo contrario (decisión del estudiante del 26/11/2026; la fila (h) de la tarea decía otra cosa).
    - Siempre, si hubo costo entregado: Debe «Costo de Producción Vendida» / Haber «Productos Terminados» por `costo` (Σ entregado × costo de cada origen).
    `None` si no hubo venta ni cobro ni costo (H11)."""
    movimientos = []
    if not es_venta or not es_ultima:
        movimientos += [(cuentas.DEUDORES_POR_VENTAS, DEBE, monto), (cuentas.VENTAS, HABER, monto)]
    elif cobra:
        en_deudores = _deudores_ya_asentados(entrega)
        caja_o_banco = cuentas.CAJA if medio_pago == "efectivo" else cuentas.BANCO
        movimientos += [(caja_o_banco, DEBE, total_a_cobrar), (cuentas.VENTAS, HABER, total_a_cobrar - en_deudores), (cuentas.DEUDORES_POR_VENTAS, HABER, en_deudores)]
    costo = costos.redondear_monto(Decimal(costo))
    movimientos += [(cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, costo), (cuentas.PRODUCTOS_TERMINADOS, HABER, costo)]
    return asientos.registrar_asiento_automatico(
        actor, entrega, hoy, [(c, t, costos.redondear_monto(Decimal(i))) for c, t, i in movimientos], descripcion=f"Entrega {entrega.codigo}", hoy=hoy
    )


# ---- el texto de origen de un asiento en el libro (punto de extensión de `contabilidad`, docs/api/asientos.md) ----
# SIN dirección: las pantallas de cosecha y de entrega no las abre el Contador, que es quien lee el libro, y D-30 no admite un enlace que lleve a un error
# (el mismo criterio que CON-04a). Solo lectura: no bloquea ni escribe. `None` si el documento no es de los que asientan: la ficha cae en el texto del tipo.


def enlace_de_movimiento_de_stock(origen):
    """`registrar_enlace_de_origen("movimiento_de_stock", …)`: «Salida por cosecha · OT-0051, lote L-12, 40 plantas» para el movimiento de una cosecha; `None` para los
    demás tipos de movimiento (ninguno otro origina un asiento)."""
    movimiento = MovimientoStock.objects.select_related("lote").filter(pk=origen.pk).first()
    if movimiento is None or movimiento.tipo_movimiento != MovimientoStock.TipoMovimiento.SALIDA_POR_COSECHA:
        return None
    cosecha = OrdenTrabajo.objects.filter(pk=movimiento.origen_id).first()
    lote = f", lote {movimiento.lote.codigo}" if movimiento.lote_id else ""
    return f"Salida por cosecha · {cosecha.codigo if cosecha else 'cosecha'}{lote}, {movimiento.cantidad} plantas", None


def enlace_de_orden_de_trabajo(origen):
    """`registrar_enlace_de_origen("orden_de_trabajo", …)`: «Entrega OT-0231 · CV-0044, <cliente>» para una entrega (el origen de su asiento compuesto); `None` si la orden no
    es una entrega (la siembra, la transición y la cosecha tienen su propio texto o ninguno)."""
    entrega = Entrega.objects.select_related("contrato_entrega__cliente").filter(pk=origen.pk).first()
    if entrega is None:
        return None
    contrato = entrega.contrato_entrega
    return f"Entrega {entrega.codigo} · {contrato.codigo}, {contrato.cliente}", None


# ---- CON-04d: cobros, anulaciones (dinero sin stock). Mismos criterios: dentro de la transacción del caso de uso, DESPUÉS de sus bloqueos de negocio (el ejercicio va último, D-86). ----


def _caja_o_banco(medio_pago):
    """Regla 15 de 8.13: el efectivo se imputa a Caja y los demás medios a Banco c/c."""
    return cuentas.CAJA if medio_pago == "efectivo" else cuentas.BANCO


def movimientos_previstos_del_cobro(medio_pago, cobrado, atraso):
    """Los movimientos del asiento del cobro a partir de los totales (el resumen de COM-REG-CBR muestra el asiento ANTES de que exista el pago): Debe Caja o Banco c/c por lo cobrado más el atraso / Haber Deudores
    por Ventas por lo cobrado / Haber Indemnizaciones por Atraso en el Pago por el atraso. Función pura."""
    cobrado, atraso = Decimal(cobrado), Decimal(atraso)
    return [(_caja_o_banco(medio_pago), DEBE, cobrado + atraso), (cuentas.DEUDORES_POR_VENTAS, HABER, cobrado), (cuentas.INDEMNIZACIONES_POR_ATRASO, HABER, atraso)]


def movimientos_de_cobro(pago, lineas):
    """COM-REG-CBR postcondición d (D-92 puntos 5 y 6; reglas 9 y 10 de 8.11): los movimientos del asiento compuesto del cobro de un suministro. Debe Caja o Banco c/c por `monto_pagado` /
    Haber «Deudores por Ventas» por Σ `monto_cobrado` / Haber «Indemnizaciones por Atraso en el Pago» por Σ `indemnizacion_atraso` (se omite si es 0). Función pura."""
    cobrado = sum((Decimal(l.monto_cobrado) for l in lineas), Decimal("0.00"))
    atraso = sum((Decimal(l.indemnizacion_atraso) for l in lineas), Decimal("0.00"))
    return [(c, t, Decimal(pago.monto_pagado) if t == DEBE else i) for c, t, i in movimientos_previstos_del_cobro(pago.medio_pago, cobrado, atraso)]


def asentar_cobro(actor, pago, lineas, hoy):
    """COM-REG-CBR postcondición d: UN asiento compuesto originado en el `PagoCliente` (R012), con la `fecha_pago` como fecha del hecho (D-92 punto 4; en 7a es la del cobro anulado,
    decisión del estudiante del 26/11/2026; si cae en un ejercicio cerrado, D-102). Sin transición para Deudores por Ventas (decisión del 26/11/2026)."""
    return asientos.registrar_asiento_automatico(
        actor, pago, pago.fecha_pago, [(c, t, costos.redondear_monto(i)) for c, t, i in movimientos_de_cobro(pago, lineas)], descripcion=f"Cobro {pago.codigo}", hoy=hoy
    )


def movimientos_previstos_del_cobro_de_venta(medio_pago, monto):
    """Los movimientos del asiento del cobro de lo entregado al cancelar una compra-venta (6a): Debe Caja o Banco c/c / Haber Deudores por Ventas por el `monto`. Función pura (el resumen los muestra antes del pago)."""
    monto = Decimal(monto)
    return [(_caja_o_banco(medio_pago), DEBE, monto), (cuentas.DEUDORES_POR_VENTAS, HABER, monto)]


def asentar_cobro_de_compra_venta(actor, pago, hoy):
    """COM-CNL-CVT extensión 6a (D-94 punto 14): el pago de compra-venta por lo entregado, originado en el `PagoCliente`: Debe Caja o Banco c/c / Haber «Deudores por Ventas» por `monto_pagado`
    (cada entrega ya registró su venta contra Deudores, CON-04c). Fecha: hoy."""
    importe = costos.redondear_monto(Decimal(pago.monto_pagado))
    return asientos.registrar_asiento_automatico(
        actor, pago, pago.fecha_pago, [(c, t, costos.redondear_monto(i)) for c, t, i in movimientos_previstos_del_cobro_de_venta(pago.medio_pago, importe)], descripcion="Cobro de lo entregado al cancelar la compra-venta", hoy=hoy
    )


def movimientos_invertidos_de(origen):
    """Los movimientos del asiento de `origen` con el Debe y el Haber invertidos, o `None` si ese documento no tiene asiento (anterior a la tarea que lo reabrió, D-92 punto 1). Función pura de lectura."""
    original = AsientoContable.objects.filter(origen_id=origen.pk).first()
    if original is None:
        return None
    return [(m.cuenta.codigo_cuenta, HABER if m.tipo_movimiento == DEBE else DEBE, m.importe_movimiento) for m in original.movimientos.select_related("cuenta").order_by("pk")]


def ya_contraasentado(anulacion, origen_anulado):  # `anulacion=None`: ¿alguna anulación de ese documento ya tiene contraasiento?
    """`True` si OTRA `Anulacion` del mismo documento (solicitud o cobro) ya tiene su contraasiento: el asiento original ya se revirtió y no puede revertirse dos veces. Pasa cuando una solicitud aceptada se anula, se
    vuelve a aceptar sin asiento (el origen ya tenía el suyo, R012; decisión del estudiante del 26/11/2026) y se anula otra vez."""
    previas = Anulacion.objects.filter(solicitud_id=origen_anulado.pk) | Anulacion.objects.filter(pago_cliente_id=origen_anulado.pk)
    if anulacion is not None:
        previas = previas.exclude(pk=anulacion.pk)
    return AsientoContable.objects.filter(origen_id__in=previas.values("pk")).exists()


def asentar_anulacion(actor, anulacion, origen_anulado, hoy, descripcion):
    """Contraasiento de una `Anulacion` (COM-ANL-CBR postcondición c, COM-ANL-SRV postcondición c; D-92 punto 6; regla «Contraasiento»): los movimientos del asiento original invertidos, con la `Anulacion` como
    origen y la fecha de hoy (si el ejercicio del original está cerrado, va al abierto: D-102). NO usa `contraasentar` (es del Contador, CON-03b). `None` si el original no tiene asiento (D-92 punto 1) o su importe es 0."""
    if ya_contraasentado(anulacion, origen_anulado):
        return None  # ya se revirtió: una segunda reversión dejaría el asiento al revés
    movimientos = movimientos_invertidos_de(origen_anulado)
    if movimientos is None:
        return None
    return asientos.registrar_asiento_automatico(actor, anulacion, hoy, movimientos, descripcion=descripcion[:LARGO_DE_LA_DESCRIPCION], hoy=hoy)


def movimientos_de_indemnizacion(monto, descontado, reintegrado, medio_reintegro):
    """COM-EVL-DSC y COM-RSV-QJA postcondición e (D-92 puntos 5 y 6; regla 15 de 8.13): Debe «Indemnizaciones por Incumplimiento a Cliente» por el `monto` / Haber «Deudores por Ventas» por lo descontado del
    monto a cobrar / Haber Caja (efectivo) o Banco c/c (transferencia) por lo reintegrado. Sin pagar es todo Deudores; con la entrega ya cobrada, todo Caja o Banco; con ambos, el asiento compuesto (6d). Función pura."""
    return [
        (cuentas.INDEMNIZACIONES_POR_INCUMPLIMIENTO, DEBE, Decimal(monto)),
        (cuentas.DEUDORES_POR_VENTAS, HABER, Decimal(descontado)),
        (_caja_o_banco(medio_reintegro), HABER, Decimal(reintegrado)),
    ]


def asentar_indemnizacion(actor, solicitud, monto, descontado, reintegrado, medio_reintegro, hoy):
    """Un asiento por solicitud aceptada (R012), originado en la `SolicitudRevision`, con la fecha de la resolución (hoy). `None` si el monto es $0,00 (H11)."""
    return asientos.registrar_asiento_automatico(
        actor,
        solicitud,
        hoy,
        [(c, t, costos.redondear_monto(i)) for c, t, i in movimientos_de_indemnizacion(monto, descontado, reintegrado, medio_reintegro)],
        descripcion=f"Indemnización aceptada de {solicitud.codigo}",
        hoy=hoy,
    )


def asentar_multa_de_resolucion(suministro, hoy):
    """COM-RSV-SUM postcondición h (D-92 puntos 6 y 10; MD-123): un asiento originado en el `Suministro` (R012), con el actor `None` (InfoPonia, D-27: la resolución corre sola, sea por el paso diario 33 o por el disparo
    posterior a la aceptación de una solicitud) y la fecha de la resolución (hoy): Debe «Indemnizaciones por Resolución de Contratos» / Haber «Indemnizaciones a Pagar» (2.1.02) por `multa_resolucion`. Su pago no tiene caso
    de uso: lo registra el Contador con un asiento manual. `None` si la multa es $0,00 (H11, extensión 5a)."""
    importe = costos.redondear_monto(Decimal(suministro.multa_resolucion))
    return asientos.registrar_asiento_automatico(
        None,
        suministro,
        hoy,
        [(cuentas.INDEMNIZACIONES_POR_RESOLUCION, DEBE, importe), (cuentas.INDEMNIZACIONES_A_PAGAR, HABER, importe)],
        descripcion=f"Multa por resolución de {suministro.codigo}",
        hoy=hoy,
    )


# ---- CON-04d · paso 6: cómo se muestra un asiento en las pantallas de `comercial` (decisión (3) del estudiante del 26/11/2026) ----
# Texto sin dirección (D-30): el Contador es quien lee el libro; acá solo se muestran las líneas a quienes ya ven los importes de la pantalla. Solo lectura: no bloquea ni escribe.

from types import SimpleNamespace  # noqa: E402

from contabilidad.models import CuentaContable  # noqa: E402


def filas_de(movimientos):
    """Las líneas de un asiento (ya hecho o previsto) para mostrarlas: `[SimpleNamespace(cuenta, tipo, importe)]` con el nombre de la cuenta (una consulta) y «Debe» o «Haber». Omite los importes en cero (H11)."""
    nombres = dict(CuentaContable.objects.filter(codigo_cuenta__in={m[0] for m in movimientos}).values_list("codigo_cuenta", "nombre_cuenta"))
    return [
        SimpleNamespace(cuenta=nombres.get(codigo, codigo), tipo="Debe" if tipo == DEBE else "Haber", importe=Decimal(importe))
        for codigo, tipo, importe in movimientos
        if Decimal(importe) > 0
    ]


def asiento_de(origen_id):
    """El asiento ya registrado de un documento de origen, para una ficha: `SimpleNamespace(numero, fecha, filas)` o `None` si no tiene (anterior a su tarea, D-92 punto 1, o de importe 0)."""
    asiento = AsientoContable.objects.filter(origen_id=origen_id).first()
    if asiento is None:
        return None
    movimientos = [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta").order_by("pk")]
    return SimpleNamespace(numero=asiento.numero_asiento, fecha=asiento.fecha_asiento, filas=filas_de(movimientos))


def contraasiento_previsto(origen):
    """Las líneas del contraasiento que se registraría al anular `origen`: las del asiento original invertidas, o `None` si el original no tiene asiento (no habrá contraasiento)."""
    if ya_contraasentado(None, origen):
        return None
    movimientos = movimientos_invertidos_de(origen)
    return None if movimientos is None else filas_de(movimientos)


# ---- CON-04d: el texto de origen de estos asientos en el libro (punto de extensión de `contabilidad`; SIN dirección, D-30) ----


def enlace_de_pago_cliente(origen):
    """`registrar_enlace_de_origen("pago_cliente", …)`: «Cobro COB-0032 · Pérez SA» para un cobro de suministro; «Cobro de lo entregado · CV-0044, Pérez SA» para el de una compra-venta cancelada. `None` si no es un pago de cliente."""
    from comercial.models import PagoCliente

    pago = PagoCliente.objects.select_related("cliente", "compra_venta").filter(pk=origen.pk).first()
    if pago is None:
        return None
    if pago.compra_venta_id is not None:
        return f"Cobro de lo entregado · {pago.compra_venta.codigo}, {pago.cliente}", None
    return f"Cobro {pago.codigo} · {pago.cliente}", None


def enlace_de_solicitud_revision(origen):
    """`registrar_enlace_de_origen("solicitud_revision", …)`: «Indemnización de la queja SR-0012 · OT-0231, Pérez SA» (o «de la discrepancia»). `None` si no es una solicitud."""
    from comercial.models import SolicitudRevision

    solicitud = SolicitudRevision.objects.select_related("entrega__contrato_entrega__cliente").filter(pk=origen.pk).first()
    if solicitud is None:
        return None
    tipo = "discrepancia" if solicitud.tipo_solicitud == SolicitudRevision.Tipo.DISCREPANCIA else "queja"
    entrega = solicitud.entrega
    return f"Indemnización de la {tipo} {solicitud.codigo} · {entrega.codigo}, {entrega.contrato_entrega.cliente}", None


def enlace_de_anulacion(origen):
    """`registrar_enlace_de_origen("anulacion", …)`: «Anulación del cobro COB-0032» o «Anulación de la resolución de SR-0012». `None` si no es una anulación de comercial."""
    anulacion = Anulacion.objects.select_related("pago_cliente", "solicitud").filter(pk=origen.pk).first()
    if anulacion is None:
        return None
    if anulacion.pago_cliente_id is not None:
        return f"Anulación del cobro {anulacion.pago_cliente.codigo}", None
    return f"Anulación de la resolución de {anulacion.solicitud.codigo}", None


def enlace_de_contrato(origen):
    """`registrar_enlace_de_origen("contrato", …)`: «Multa por la resolución de SUM-0013 · Pérez SA» para el asiento de la multa. `None` si el contrato no es un suministro."""
    from comercial.models import Suministro

    suministro = Suministro.objects.select_related("cliente").filter(pk=origen.pk).first()
    if suministro is None:
        return None
    return f"Multa por la resolución de {suministro.codigo} · {suministro.cliente}", None
