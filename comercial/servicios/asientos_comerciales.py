# Asientos automáticos de los casos de uso de `comercial` con stock (CON-04c; D-92 puntos 2 a 6 y 9, D-86, `docs/api/asientos.md`).
# Cada caso de uso (cosecha, merma en cámara, vencimiento y entrega) llama a estas funciones DENTRO de su transacción, con todos sus bloqueos de negocio
# ya tomados y después de crear el documento de origen: `registrar_asiento_automatico` bloquea el ejercicio AL FINAL (`docs/patrones/asientos.md`, sección 2).
# Devuelven el `AsientoContable` o `None` si el importe es cero (H11). Importes a dos decimales con ROUND_HALF_UP (D-92 punto 5); la fecha es la del hecho
# (D-92 punto 4). La merma de un lote en pie reutiliza `produccion.servicios.asientos_de_produccion.asentar_merma` (CON-04a).
from decimal import Decimal

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from comercial.models import Entrega
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
