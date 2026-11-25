# Asientos automáticos de los casos de uso de producción (CON-04a; D-92 puntos 2 a 6 y 9, D-86, `docs/api/asientos.md`).
# Cada caso de uso (siembra, transición, merma, aplicación de insumos y fuera de servicio) llama a estas funciones DENTRO de su transacción, con todos
# sus bloqueos de negocio ya tomados y después de crear el documento de origen: `registrar_asiento_automatico` bloquea el ejercicio AL FINAL
# (`docs/patrones/asientos.md`, sección 2). Devuelven el `AsientoContable` o `None` si el importe es cero (H11): quien llama sigue sin error.
# Los importes salen de lo que el código ya guarda (`Consumo.monto_consumo`, el costo que devuelve `aplicar_merma`), a dos decimales con ROUND_HALF_UP
# (D-92 punto 5). La fecha es la del hecho (D-92 punto 4). `aplicar_merma` NO asienta (D-92, «alternativas»): el asiento va en quien sabe de dónde salió.
from decimal import Decimal

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.servicios import asientos
from produccion.models import Consumo, Merma
from produccion.servicios import costos

LARGO_DE_LA_DESCRIPCION = 300  # `AsientoContable.descripcion_asiento`


def asentar_consumo(actor, consumo, a_lotes, fecha, hoy):
    """Un asiento por consumo (R012; PROD-CNC-SMB postcondición j y PROD-REG-APL postcondición f; D-92 punto 6), originado en el consumo y por su
    `monto_consumo`: Debe «Productos en Proceso» si el costo se imputó a lotes (`a_lotes`) o «Gastos de Producción» si va a gasto / Haber «Insumos en
    Stock». La descripción es la legible del consumo. `None` si el monto es $0,00 (H11)."""
    importe = costos.redondear_monto(Decimal(consumo.monto_consumo))
    debe = cuentas.PRODUCTOS_EN_PROCESO if a_lotes else cuentas.GASTOS_DE_PRODUCCION
    return asientos.registrar_asiento_automatico(
        actor,
        consumo,
        fecha,
        [(debe, DEBE, importe), (cuentas.INSUMOS_EN_STOCK, HABER, importe)],
        descripcion=consumo.descripcion_evento[:LARGO_DE_LA_DESCRIPCION],
        hoy=hoy,
    )


def asentar_merma(actor, merma, costo, fecha, hoy):
    """Un asiento por merma de un lote en pie (PROD-REG-MRM post. e, PROD-CNC-TRN con merma y PROD-PNR-FDS; D-92 puntos 4 a 6), originado en la merma:
    Debe «Pérdidas por Mermas» / Haber «Productos en Proceso» por `costo`, el costo de las plantas perdidas que devolvió `aplicar_merma`
    (`ResultadoMerma.costo`). `fecha` es la del hecho. La descripción es la legible de la merma. `None` si el costo es $0,00 (H11)."""
    importe = costos.redondear_monto(Decimal(costo))
    return asientos.registrar_asiento_automatico(
        actor,
        merma,
        fecha,
        [(cuentas.PERDIDAS_POR_MERMAS, DEBE, importe), (cuentas.PRODUCTOS_EN_PROCESO, HABER, importe)],
        descripcion=merma.descripcion_evento[:LARGO_DE_LA_DESCRIPCION],
        hoy=hoy,
    )


def referencias_de(creados):
    """Los asientos que existen de una lista que puede traer `None` (los de importe cero)."""
    return [a for a in creados if a is not None]


def enlace_de_origen(origen):
    """Punto de extensión de `contabilidad` (`registrar_enlace_de_origen("bitacora", …)`, docs/api/asientos.md): el texto que la ficha del asiento muestra
    para su origen, un consumo (de una siembra o de una aplicación) o una merma. SIN dirección: las pantallas de producción (la ficha de la orden, la
    bitácora) no las abre el Contador, que es quien lee el libro, y D-30 no admite un enlace que lleve a un error. `None` si la bitácora no es ninguna de las
    dos (la ficha cae en el texto del tipo). Solo lectura."""
    consumo = Consumo.objects.select_related("aplicacion").filter(pk=origen.pk).first()
    if consumo is not None:
        if consumo.aplicacion_id is not None:
            return f"Consumo · {consumo.descripcion_evento} ({consumo.fecha_bitacora:%d/%m/%Y})", None
        return f"Consumo · {consumo.descripcion_evento}", None
    merma = Merma.objects.select_related("lote").filter(pk=origen.pk).first()
    if merma is not None:
        lote = f"del lote {merma.lote.codigo} " if merma.lote_id else ""
        return f"Merma {lote}· {merma.descripcion_evento}", None
    return None
