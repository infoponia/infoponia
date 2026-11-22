# Reevaluación de las alertas de stock de un insumo (INV-02; docs/patrones/stock.md, sección 4; docs/api/alertas.md; D-41).
# UN SOLO PUNTO: ``reevaluar_alertas_del_insumo`` lo llaman, dentro de su transacción, todos los servicios que cambian stock, mínimo,
# estado o reservas. Hace tres cosas idempotentes: «stock inconsistente», «bajo el mínimo» y resolver las alertas de vencimiento de los
# lotes agotados. Las de vencimiento las CREA solo CMP-REV-VNC. No audita: devuelve lo creado y lo resuelto para los ``datos`` del
# registro de quien llama (``alertas_creadas`` y ``alertas_resueltas``). El invernadero queda bloqueado (``bloquear_invernadero_para_alertas``,
# reentrante: quien llama ya lo bloqueó). Con un invernadero inactivo la API no crea nada (post e de PROD-BAJ-INV).

from collections import namedtuple
from decimal import Decimal

from django.http import Http404

from inventario import alertas as tipos
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.servicios import stock
from inventario.unidades import Unidad, cuantizar
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas

# Lo que hizo la reevaluación: listas de ``Alerta``.
Reevaluacion = namedtuple("Reevaluacion", "creadas resueltas")


def _numero(valor, unidad):
    """La cantidad para una descripción: con coma decimal y sin ceros de más («12,5»)."""
    texto = str(cuantizar(valor, unidad))
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _con_unidad(valor, unidad):
    return f"{_numero(valor, unidad)} {Unidad(unidad).label}"


def descripcion_de_vencimiento(insumo, lote):
    """Regla 5 de 8.23: identifica insumo, lote, cantidad disponible y fecha, por ejemplo
    «Nutriente A · lote 7 · 12,5 L disponibles · vence el 02/12/2026». La usa CMP-REV-VNC."""
    unidad = insumo.unidad_medida_insumo
    return (
        f"{insumo.nombre_insumo} · lote {lote.pk} · {_con_unidad(lote.cantidad_disponible, unidad)} disponibles · "
        f"vence el {lote.fecha_vencimiento.strftime('%d/%m/%Y')}"
    )


def descripcion_de_bajo_minimo(insumo, existencia):
    """«<insumo> bajo el mínimo · stock libre X, mínimo Y» (texto del prototipo)."""
    unidad = insumo.unidad_medida_insumo
    return (
        f"{insumo.nombre_insumo} bajo el mínimo · stock libre {_con_unidad(existencia.libre, unidad)}, "
        f"mínimo {_con_unidad(existencia.minimo, unidad)}"
    )


def descripcion_de_inconsistencia(insumo, existencia, ordenes):
    """Identifica el insumo, el stock y lo reservado, y las órdenes que quedaron sin cobertura (sección 4)."""
    unidad = insumo.unidad_medida_insumo
    texto = (
        f"{insumo.nombre_insumo}: stock sin lotes vencidos {_con_unidad(existencia.vigente, unidad)}, "
        f"reservado {_con_unidad(existencia.reservado, unidad)}"
    )
    if ordenes:
        texto += ". Sin cobertura: " + ", ".join(orden.texto for orden in ordenes)
    return texto + "."


def _asegurar(iin, tipo, descripcion, creadas):
    """Asegura la alerta de estado ``insumo:<id>`` y, si la creó ahora, la suma a ``creadas``."""
    clave = f"insumo:{iin.pk}"
    ya = Alerta.objects.filter(
        invernadero_id=iin.invernadero_id, tipo_alerta=tipo, clave_estado=clave, estado_alerta=Alerta.Estado.ACTIVA
    ).exists()
    alerta = api_alertas.asegurar_alerta_de_estado(iin.invernadero_id, tipo, clave=clave, descripcion=descripcion)
    if alerta is not None and not ya:
        creadas.append(alerta)


def _resolver(iin, tipo, resueltas, clave=None):
    alerta = api_alertas.resolver_alerta_de_estado(iin.invernadero_id, tipo, clave=clave or f"insumo:{iin.pk}")
    if alerta is not None:
        resueltas.append(alerta)


def reevaluar_alertas_del_insumo(iin_id, hoy=None):
    """Deja las alertas del ``InsumoInvernadero`` ``iin_id`` como pide su estado a la fecha ``hoy`` y devuelve ``Reevaluacion(creadas,
    resueltas)``.

    1. ``inv_stock_inconsistente``: la asegura si el stock vigente es menor que lo reservado (incluye el vigente negativo) y la resuelve
       si no (postcondiciones h e i de CMP-AJT-STK).
    2. ``inv_insumo_bajo_minimo``: la asegura si está bajo el mínimo y la existencia y el insumo del catálogo están activos; la resuelve
       si no, o si la existencia o el insumo pasaron a inactivos (la semilla dada de baja con su variedad conserva su existencia activa).
    3. Resuelve las ``inv_insumo_por_vencer`` e ``inv_insumo_vencido`` de los lotes cuya cantidad disponible llegó a 0.
    """
    iin = InsumoInvernadero.objects.select_related("insumo").filter(pk=iin_id).first()
    if iin is None:
        raise Http404("No existe ese insumo en el invernadero.")
    api_alertas.bloquear_invernadero_para_alertas(iin.invernadero_id)
    if hoy is None:
        hoy = stock.hoy()
    existencia = stock.existencias([iin.pk], hoy)[iin.pk]
    creadas, resueltas = [], []
    # 1. Stock inconsistente.
    if iin.activo and existencia.inconsistente:
        ordenes = stock.ordenes_sin_cobertura(iin.pk, hoy)
        _asegurar(iin, tipos.STOCK_INCONSISTENTE, descripcion_de_inconsistencia(iin.insumo, existencia, ordenes), creadas)
    else:
        _resolver(iin, tipos.STOCK_INCONSISTENTE, resueltas)
    # 2. Bajo el mínimo.
    if iin.activo and iin.insumo.activo and existencia.bajo_minimo:
        _asegurar(iin, tipos.INSUMO_BAJO_MINIMO, descripcion_de_bajo_minimo(iin.insumo, existencia), creadas)
    else:
        _resolver(iin, tipos.INSUMO_BAJO_MINIMO, resueltas)
    # 3. Alertas de vencimiento de los lotes agotados.
    agotados = {
        f"lote:{pk}"
        for pk in LoteInsumo.objects.filter(
            insumo_invernadero=iin, es_faltante_sin_lote=False, cantidad_disponible=0
        ).values_list("pk", flat=True)
    }
    if agotados:
        pendientes = Alerta.objects.filter(
            invernadero_id=iin.invernadero_id,
            tipo_alerta__in=[tipos.INSUMO_POR_VENCER, tipos.INSUMO_VENCIDO],
            clave_estado__in=agotados,
            estado_alerta=Alerta.Estado.ACTIVA,
        ).order_by("id")
        for alerta in list(pendientes):
            _resolver(iin, alerta.tipo_alerta, resueltas, clave=alerta.clave_estado)
    return Reevaluacion(creadas, resueltas)
