# Núcleo físico de la cámara (COM-04a, D-64 punto 2; docs/api/produccion.md, secciones 8 y 10): partidas de producto ya cosechado.
# NO son casos de uso: los llaman PROD-CNC-CSC, PROD-REG-MRM (rama de cámara), PROD-VNC-CAM, COM-DCD-FLT y COM-CNC-ENT (en `comercial`) dentro de
# su transacción, con lo suyo ya bloqueado (invernadero con `bloquear_invernadero_activo`, D-40; y la partida). No auditan ni notifican.
# NO recortan reservas: eso lo hace `comercial` antes de llamarlas. Fuente: reglas 29 a 31 de 8.6, reglas 4, 6 y 8 de 8.9, D-64 y D-68.

from collections import namedtuple
from datetime import timedelta

from django.utils import timezone

from produccion.errores import ErrorDeProduccion
from produccion.models import Merma, MovimientoStock, StockCosechado
from produccion.servicios import movimientos
from produccion.servicios.mermas import plantas

Estado = StockCosechado.Estado
Tipo = MovimientoStock.TipoMovimiento
CAUSAS_DE_CAMARA = (Merma.Causa.DANO_EN_CAMARA, Merma.Causa.VENCIMIENTO_EN_CAMARA)

ResultadoMermaDePartida = namedtuple("ResultadoMermaDePartida", "merma movimiento")
# `merma` es un `ResultadoMermaDePartida` si la devolución llegó a una partida vencida; si no, `None`.
ResultadoDevolucion = namedtuple("ResultadoDevolucion", "movimiento merma")
# Una fila de la pestaña «Cámara» (lo reservado lo suma `comercial`).
FilaDePartida = namedtuple(
    "FilaDePartida",
    "partida_id codigo lote_id lote_codigo variedad invernadero_id invernadero fecha_ingreso fecha_limite ingreso disponible estado motivo costo_unitario",
)


def _error(codigo, mensaje, campo=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo)


def _releer(partida):
    """Relee de la base lo que cambia de la partida (el llamador la bloqueó): disponible y estado."""
    partida.refresh_from_db(fields=["cantidad_disponible_cosechado", "estado_stock_cosechado"])


def crear_partida(lote, cantidad, motivo, *, fecha_cosecha, fecha_ingreso, costo_unitario, origen):
    """Crea una partida «disponible» de `cantidad` plantas de `lote` (ingreso = disponible) con su `MovimientoStock` `ingreso_a_camara`.

    - `fecha_limite` = `fecha_cosecha` + la duración postcosecha de la variedad (regla 29 de 8.6: no se reinicia la vida útil).
    - `costo_unitario`: el del movimiento «salida por cosecha» (D-64 punto 3). `origen`: el documento que la origina (la cosecha, el contrato).
    - Quien llama ya bloqueó el invernadero con `bloquear_invernadero_activo` (D-40). Corre en su transacción (sin ella, `RuntimeError`).
    """
    movimientos.exigir_transaccion("crear_partida")
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise _error("cantidad_invalida", "La partida debe tener al menos una planta.", "cantidad")
    partida = StockCosechado.objects.create(
        lote=lote,
        cantidad_ingreso_cosechado=cantidad,
        cantidad_disponible_cosechado=cantidad,
        fecha_ingreso=fecha_ingreso,
        fecha_limite=fecha_cosecha + timedelta(days=lote.siembra.variedad.duracion_post_cosecha),
        motivo_cosechado=motivo,
        costo_unitario_cosechado=costo_unitario,
    )
    movimientos.registrar(Tipo.INGRESO_A_CAMARA, cantidad, costo_unitario, origen, partida=partida, fecha=fecha_ingreso)
    return partida


def _crear_merma_de_camara(partida, cantidad, causa, descripcion, responsable):
    """La `Merma` de cámara (con el lote de origen, sin etapa, de hoy) y su movimiento `merma_en_camara`; NO cambia la partida."""
    hoy = timezone.localdate()
    texto = f"Merma de {plantas(cantidad)} por {Merma.Causa(causa).label.lower()}."
    merma = Merma.objects.create(
        invernadero_id=partida.lote.invernadero_id,
        lote=partida.lote,
        etapa=None,
        tipo_evento="merma",
        fecha_bitacora=hoy,
        hora_bitacora=timezone.localtime().time(),
        responsable=responsable,
        descripcion_evento=f"{texto} {descripcion}"[:500] if descripcion else texto,
        cant_merma=cantidad,
        causa=causa,
    )
    movimiento = movimientos.registrar(
        Tipo.MERMA_EN_CAMARA, cantidad, partida.costo_unitario_cosechado, merma, partida=partida
    )
    return ResultadoMermaDePartida(merma, movimiento)


def aplicar_merma_de_partida(partida, cantidad, causa, descripcion, responsable):
    """Pérdida de `cantidad` plantas de una partida (PROD-REG-MRM 4a, PROD-VNC-CAM): `Merma` (tipo merma) con el lote de origen, SIN etapa, el
    invernadero, fecha y hora actuales (regla 8 de 8.9) y `responsable` (`None` = InfoPonia); baja la disponible (la partida queda «agotado»
    si llega a 0) y crea el movimiento `merma_en_camara` (origen: la merma, costo de la partida). No toca el lote ni su costo.

    `ErrorDeProduccion`: `cantidad_invalida`, `causa_invalida` (solo `dano_en_camara` y `vencimiento_en_camara`), `descripcion_larga` (300) y
    `merma_supera_partida`. NO recorta reservas: eso lo hace `comercial` antes de llamarla. Corre en la transacción de quien llama."""
    movimientos.exigir_transaccion("aplicar_merma_de_partida")
    _releer(partida)
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise _error("cantidad_invalida", "La cantidad perdida debe ser un número entero mayor que cero.", "cantidad")
    if causa not in CAUSAS_DE_CAMARA:
        raise _error("causa_invalida", "Esa causa no corresponde a una partida en cámara.", "causa")
    descripcion = (descripcion or "").strip()
    if len(descripcion) > 300:
        raise _error("descripcion_larga", "La descripción pasa de 300 caracteres.", "descripcion")
    if cantidad > partida.cantidad_disponible_cosechado:
        raise _error(
            "merma_supera_partida",
            f"La partida {partida.codigo} tiene {partida.cantidad_disponible_cosechado} disponibles: no se pueden perder {cantidad}.",
            "cantidad",
        )
    resultado = _crear_merma_de_camara(partida, cantidad, causa, descripcion, responsable)
    _bajar_disponible(partida, cantidad)
    return resultado


def _bajar_disponible(partida, cantidad):
    """Baja la disponible de `partida` en `cantidad` y la deja «agotado» si llega a 0 estando «disponible» (regla 30 de 8.6)."""
    partida.cantidad_disponible_cosechado -= cantidad
    if partida.cantidad_disponible_cosechado == 0 and partida.estado_stock_cosechado == Estado.DISPONIBLE:
        partida.estado_stock_cosechado = Estado.AGOTADO
    StockCosechado.objects.filter(pk=partida.pk).update(
        cantidad_disponible_cosechado=partida.cantidad_disponible_cosechado, estado_stock_cosechado=partida.estado_stock_cosechado
    )


def vencer_partida(partida, hoy):
    """PROD-VNC-CAM: si la disponible es mayor que 0, la pierde con `aplicar_merma_de_partida` (causa `vencimiento_en_camara`, sin responsable);
    la partida queda «vencido» con disponible 0 en todos los casos. Devuelve el `ResultadoMermaDePartida` o `None` si no había nada. `hoy` es la
    fecha con la que el llamador decidió que venció (regla 4 de 8.9: la fecha límite es anterior a hoy); acá no se vuelve a verificar."""
    movimientos.exigir_transaccion("vencer_partida")
    _releer(partida)
    resultado = None
    if partida.cantidad_disponible_cosechado > 0:
        resultado = aplicar_merma_de_partida(
            partida, partida.cantidad_disponible_cosechado, Merma.Causa.VENCIMIENTO_EN_CAMARA, "", None
        )
    partida.cantidad_disponible_cosechado, partida.estado_stock_cosechado = 0, Estado.VENCIDO
    StockCosechado.objects.filter(pk=partida.pk).update(cantidad_disponible_cosechado=0, estado_stock_cosechado=Estado.VENCIDO)
    return resultado


def partidas_del_invernadero(invernadero_ids):
    """Lectura para la pestaña «Cámara»: las partidas de los lotes de esos invernaderos, por fecha límite e id, con la variedad y el lote. Una
    consulta (lista vacía: sin consultar)."""
    ids = list(invernadero_ids)
    if not ids:
        return []
    partidas = (
        StockCosechado.objects.filter(lote__invernadero_id__in=ids)
        .select_related("lote__invernadero", "lote__siembra__variedad__cultivo")
        .order_by("fecha_limite", "pk")
    )
    return [
        FilaDePartida(
            p.pk,
            p.codigo,
            p.lote_id,
            p.lote.codigo,
            str(p.lote.siembra.variedad),
            p.lote.invernadero_id,
            p.lote.invernadero.nombre_invernadero,
            p.fecha_ingreso,
            p.fecha_limite,
            p.cantidad_ingreso_cosechado,
            p.cantidad_disponible_cosechado,
            p.estado_stock_cosechado,
            p.motivo_cosechado,
            p.costo_unitario_cosechado,
        )
        for p in partidas
    ]


# ---- Lo que usa la concreción de una entrega (COM-06a; sección 10) ----


def egresar_de_partida(partida, cantidad, origen):
    """Baja `cantidad` de la disponible (la partida queda «agotado» si llega a 0) y crea el movimiento `egreso_de_camara` (origen: la orden;
    costo de la partida). `ErrorDeProduccion('egreso_supera_partida')` si pasa de la disponible o si la partida está «vencido»; `cantidad_invalida`
    si no es un entero mayor que cero."""
    movimientos.exigir_transaccion("egresar_de_partida")
    _releer(partida)
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise _error("cantidad_invalida", "La cantidad a egresar debe ser un número entero mayor que cero.", "cantidad")
    if partida.estado_stock_cosechado == Estado.VENCIDO or cantidad > partida.cantidad_disponible_cosechado:
        raise _error("egreso_supera_partida", f"La partida {partida.codigo} no tiene {cantidad} plantas disponibles para egresar.", "cantidad")
    _bajar_disponible(partida, cantidad)
    return movimientos.registrar(Tipo.EGRESO_DE_CAMARA, cantidad, partida.costo_unitario_cosechado, origen, partida=partida)


def devolver_a_partida(partida, cantidad, origen, hoy):
    """Regla 29 de 8.6: devuelve `cantidad` plantas a la partida de la que salieron.

    - Vigente (`fecha_limite >= hoy` y no «vencido»): sube la disponible («agotado» vuelve a «disponible»), crea `ingreso_a_camara` (origen: la
      orden) y `merma = None`.
    - Ya venció: el mismo ingreso y enseguida la merma por vencimiento (`vencimiento_en_camara`, sin responsable); la disponible y el estado de
      la partida no cambian («vencido» sigue «vencido» con 0)."""
    movimientos.exigir_transaccion("devolver_a_partida")
    _releer(partida)
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise _error("cantidad_invalida", "La cantidad a devolver debe ser un número entero mayor que cero.", "cantidad")
    ingreso = movimientos.registrar(Tipo.INGRESO_A_CAMARA, cantidad, partida.costo_unitario_cosechado, origen, partida=partida)
    if partida.estado_stock_cosechado == Estado.VENCIDO or partida.fecha_limite < hoy:
        return ResultadoDevolucion(ingreso, _crear_merma_de_camara(partida, cantidad, Merma.Causa.VENCIMIENTO_EN_CAMARA, "", None))
    partida.cantidad_disponible_cosechado += cantidad
    partida.estado_stock_cosechado = Estado.DISPONIBLE
    StockCosechado.objects.filter(pk=partida.pk).update(
        cantidad_disponible_cosechado=partida.cantidad_disponible_cosechado, estado_stock_cosechado=Estado.DISPONIBLE
    )
    return ResultadoDevolucion(ingreso, None)
