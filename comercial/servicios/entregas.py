# Entregas de `comercial` (COM-05a1): los cálculos de una entrega (cantidad planificada, peso, candidatos, selección y agrupamiento), COM-PNF-ENT (la planificación
# automática, inmediata con `transaction.on_commit` y diaria en el paso 50), la «Cancelación de una entrega» de PROD-CNL-ORD (solo incluida, sin pantalla) y lo que `comercial`
# registra para que otras tareas respeten las entregas (la logística de la ficha del invernadero, la baja de un transportista, los vehículos y el cierre de una rescisión).
# Fuente: docs/casos_de_uso/comercial/entregas.md, docs/casos_de_uso/produccion/cancelar_orden.md («Comercial 1: entregas y envasado»), docs/modelo/comercial.md («Entrega»,
# «DetalleEntrega»), D-66 y docs/patrones/bloqueos.md («Entregas y envasado»).
#
# Bloqueos (`FOR NO KEY UPDATE`; el semáforo es el invernadero de origen, D-66 punto 11): las cuentas (el Vendedor, el Agrónomo y todos los transportistas del invernadero, en una
# consulta y por id) → el invernadero → el cliente → el contrato → sus detalles → sus reservas → las entregas con las que podría agruparse y sus reservas de insumo. Todo se
# vuelve a leer ya bloqueado (extensión 8b). Las notificaciones y la alerta se crean dentro de la transacción (D-42); el correo al cliente sale después de confirmar (D-14, D-54).
# Una planificación que falla se registra con `logger.exception` y la retoma el paso 50 (garantía mínima 2).

import logging
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import partial

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Value, When
from django.urls import reverse

from comercial.models import (
    AlertaComercial,
    Cliente,
    CompraVenta,
    Contrato,
    DetalleEntrega,
    DetalleReserva,
    DetalleSuministro,
    DetalleVenta,
    Entrega,
    ReservaStock,
    Suministro,
    Vehiculo,
)
from comercial.servicios import calendario, stock_maduro
from comercial.servicios.comprobantes import Destinatario
from core import correo, notificaciones
from core.extensiones import Asignacion, Efecto
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from core.procesos import ResumenDePaso
from inventario.models import InsumoInvernadero
from inventario.servicios import stock
from maestros.extensiones import Enlace, Impedimento
from maestros.models import Direccion, Invernadero, TransportistaInvernadero
from maestros.servicios import alertas, configuracion
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.models import OrdenTrabajo, ReservaInsumo
from produccion.servicios import ordenes

logger = logging.getLogger("infoponia.entregas")

TIPO_SIN_TRANSPORTISTA = "comercial_entrega_sin_transportista"  # ESTADO, GERENTE, ADVERTENCIA, origen ENTREGA (D-66 punto 10)
LARGO_DE_LA_ALERTA = 200  # `Alerta.descripcion_alerta`
LARGO_DEL_TITULO = notificaciones.LARGO_TITULO
LARGO_DEL_DETALLE = notificaciones.LARGO_DETALLE
CENTAVOS = Decimal("0.01")
GERENTE, VENDEDOR, TRANSPORTISTA = Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR, Usuario.Rol.TRANSPORTISTA
A_REALIZAR = OrdenTrabajo.Estado.A_REALIZAR
NO_CANCELADAS = (OrdenTrabajo.Estado.A_REALIZAR, OrdenTrabajo.Estado.CONCRETADA)
LISTA = ReservaStock.Estado.LISTA_PARA_ENTREGA
ENVIO, RETIRO = Entrega.Modalidad.ENVIO, Entrega.Modalidad.RETIRO
AVISO = Entrega.EstadoDelAviso

# Los motivos por los que un transportista no puede llevar una entrega, en el orden en que se evalúan (regla «Candidato» y paso 6).
M_INACTIVO = "Inactivo"
M_SIN_VEHICULO = "Sin vehículo activo"
M_EN_RUTA = "En ruta"
M_CAPACIDAD = "Capacidad de carga insuficiente"
M_ENTREGAS = "Máximo de entregas diarias"
M_LOCALIDADES = "Máximo de localidades distintas por día"
MOTIVOS = (M_INACTIVO, M_SIN_VEHICULO, M_EN_RUTA, M_CAPACIDAD, M_ENTREGAS, M_LOCALIDADES)
SIN_FLOTA = "sin transportistas activos con vehículo activo"

Candidato = namedtuple("Candidato", "transportista vehiculo entregas_del_dia peso_del_dia localidades_del_dia capacidad_libre motivo")
Origen = namedtuple("Origen", "tipo contrato_id detalle_id fecha")  # tipo: «venta» o «periodo»
LineaNueva = namedtuple("LineaNueva", "detalle fecha_periodo reservas precio")
ResultadoDePlanificacion = namedtuple("ResultadoDePlanificacion", "entrega creada agrupada transportista motivo alerta")
CancelacionDeEntrega = namedtuple("CancelacionDeEntrega", "entrega reservas_de_insumo alerta_resuelta avisados")
QuitaDeLineas = namedtuple("QuitaDeLineas", "lineas_quitadas cancelaciones")


# ---- utilidades ----


def _acotar(texto, largo):
    """`texto` sin pasar de `largo` caracteres (termina en «…» si se recorta)."""
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _redondear(valor):
    """Dos decimales, `ROUND_HALF_UP` (regla «Peso de una entrega»; MD-69)."""
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _kg(peso):
    """«12,40 kg»."""
    return f"{Decimal(peso):.2f}".replace(".", ",") + " kg"


def _cantidad(valor):
    """«20» o «2,5»: una cantidad decimal sin ceros de más."""
    return f"{Decimal(valor).normalize():f}".replace(".", ",")


def _rechazar(codigo, mensaje, campo="__all__"):
    """Un `ValidationError` con código estable (patrón de `comercial`)."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _exigir_transaccion(nombre):
    """Las funciones incluidas corren dentro de la transacción del caso de uso que las llama."""
    if transaction.get_autocommit():
        raise RuntimeError(f"`{nombre}` corre dentro de la transacción del caso de uso que la llama.")


def _clave_de_la_alerta(entrega_id):
    """La clave de la alerta de estado «entrega sin transportista» (una por entrega)."""
    return f"entrega:{entrega_id}"


def _usuario_activo(usuario_id):
    """La cuenta activa con ese id, o `None`."""
    return Usuario.objects.filter(pk=usuario_id, is_active=True).first() if usuario_id else None


def _cliente_de(contrato):
    return contrato.cliente.nombre_visible


# ---- cálculos de una entrega (paso 2; docs/modelo/comercial.md, «Lo que se calcula») ----


def cantidades_planificadas(linea_ids):
    """``{id de línea: cantidad planificada}``: la suma de la cantidad cubierta (regla 9 de 8.8) de las reservas **no liberadas** de cada línea (D-66 punto 4). Una línea con
    todas sus reservas liberadas da 0. Dos consultas para toda la lista."""
    linea_ids = list(linea_ids)
    resultado = {i: 0 for i in linea_ids}
    if not linea_ids:
        return resultado
    pares = list(
        DetalleEntrega.reservas.through.objects.filter(detalleentrega_id__in=linea_ids)
        .exclude(reservastock__estado_reserva=ReservaStock.Estado.LIBERADA)
        .values_list("detalleentrega_id", "reservastock_id")
    )
    cubierto = defaultdict(int)
    for reserva_id, reservada, cosechada, lote_id in DetalleReserva.objects.filter(reserva_id__in={r for _, r in pares}).values_list(
        "reserva_id", "cantidad_reservada", "cantidad_cosechada", "lote_id"
    ):
        cubierto[reserva_id] += stock_maduro._cubierto(reservada, cosechada, lote_id)
    for linea_id, reserva_id in pares:
        resultado[linea_id] += cubierto[reserva_id]
    return resultado


def peso_de_entregas(entrega_ids):
    """``{id de entrega: peso en kg}``: `redondear(Σ cantidad planificada × peso promedio por planta (g) / 1.000, 2)` (regla «Peso de una entrega»; MD-69; D-66 punto 4). La misma
    función para COM-PNF-ENT, COM-ASG-TRP, COM-INI-RUT y los vehículos. Una entrega sin nada planificado pesa 0,00."""
    entrega_ids = list(entrega_ids)
    gramos = {i: Decimal(0) for i in entrega_ids}
    if not entrega_ids:
        return {}
    lineas = list(
        DetalleEntrega.objects.filter(entrega_id__in=entrega_ids).values_list(
            "pk", "entrega_id", "detalle_venta__variedad__peso_promedio_planta", "detalle_suministro__variedad__peso_promedio_planta"
        )
    )
    planificadas = cantidades_planificadas([linea for linea, *_ in lineas])
    for linea_id, entrega_id, de_venta, de_suministro in lineas:
        gramos[entrega_id] += planificadas[linea_id] * (de_venta or de_suministro or 0)
    return {entrega_id: _redondear(total / 1000) for entrega_id, total in gramos.items()}


def en_curso(entrega, hoy):
    """«En curso» (MD-118; regla de PROD-PNF-ENV): con envío, con fecha programada de hoy o anterior y el vehículo de su transportista en ruta."""
    if entrega.transportista_id is None or entrega.fecha_programada_orden > hoy:
        return False
    vehiculo = Vehiculo.objects.filter(transportista_id=entrega.transportista_id).first()
    return vehiculo is not None and vehiculo.esta_en_ruta(hoy)


def atrasada(entrega, hoy):
    """«Atrasada» (MD-139): «a realizar» y con la fecha programada anterior a hoy."""
    return entrega.estado_orden == A_REALIZAR and entrega.fecha_programada_orden < hoy


def candidatos_para(invernadero, fecha, peso, localidad, *, excluir=None, hoy):
    """Pasos 5 a 7 (candidatos y verificaciones): un `Candidato` por cada transportista del invernadero de origen (`TransportistaInvernadero`, D-55), con su `motivo` (el primero que
    falla, en el orden de `MOTIVOS`; `None` si cumple). `invernadero` es el invernadero o su id; `localidad` es el id de la localidad de destino (`None` en un retiro, que no cuenta);
    `excluir` es el transportista (o su id) que no se ofrece (COM-ASG-TRP, el actual). Las entregas del día cuentan «a realizar» y «concretada», no las canceladas. Una consulta
    por tabla, nunca una por transportista."""
    invernadero_id = getattr(invernadero, "pk", invernadero)
    excluir_id = getattr(excluir, "pk", excluir)
    asignados = [
        a
        for a in TransportistaInvernadero.objects.filter(invernadero_id=invernadero_id).select_related("transportista").order_by("transportista_id")
        if a.transportista_id != excluir_id
    ]
    ids = [a.transportista_id for a in asignados]
    vehiculos = {v.transportista_id: v for v in Vehiculo.objects.filter(transportista_id__in=ids)}
    del_dia = defaultdict(list)
    for transportista_id, entrega_id, localidad_id in (
        Entrega.objects.filter(transportista_id__in=ids, fecha_programada_orden=fecha)
        .exclude(estado_orden=OrdenTrabajo.Estado.CANCELADA)
        .order_by("pk")
        .values_list("transportista_id", "pk", "direccion_destino__localidad_id")
    ):
        del_dia[transportista_id].append((entrega_id, localidad_id))
    pesos = peso_de_entregas([e for filas in del_dia.values() for e, _ in filas])
    ajustes = configuracion.obtener()
    candidatos = []
    for asignado in asignados:
        transportista = asignado.transportista
        vehiculo = vehiculos.get(transportista.pk)
        filas = del_dia.get(transportista.pk, [])
        peso_del_dia = sum((pesos[e] for e, _ in filas), Decimal("0"))
        localidades = frozenset(l for _, l in filas if l is not None)
        capacidad = vehiculo.capacidad_carga if vehiculo is not None else Decimal("0")
        if not transportista.is_active:
            motivo = M_INACTIVO
        elif vehiculo is None or not vehiculo.activo:
            motivo = M_SIN_VEHICULO
        elif fecha == hoy and vehiculo.esta_en_ruta(hoy):
            motivo = M_EN_RUTA
        elif peso_del_dia + peso > capacidad:
            motivo = M_CAPACIDAD
        elif len(filas) + 1 > ajustes.cant_maxima_entregas_diarias:
            motivo = M_ENTREGAS
        elif len(localidades | ({localidad} if localidad is not None else set())) > ajustes.cant_max_ciudades_distintas_diarias:
            motivo = M_LOCALIDADES
        else:
            motivo = None
        candidatos.append(Candidato(transportista, vehiculo, len(filas), peso_del_dia, localidades, capacidad - peso_del_dia, motivo))
    return candidatos


def seleccionar(candidatos):
    """Paso 7 y extensión 7a (función pura): entre los que cumplen, el que menos entregas tiene en la fecha; si empatan, el de mayor capacidad libre; si siguen empatados, el de menor
    identificador. `None` si ninguno cumple."""
    cumplen = [c for c in candidatos if c.motivo is None]
    if not cumplen:
        return None
    return min(cumplen, key=lambda c: (c.entregas_del_dia, -c.capacidad_libre, c.transportista.pk))


def motivo_de_alerta(candidatos):
    """Extensión 6a.2 (función pura): sin transportistas, o si todos están «Inactivo» o «Sin vehículo activo», «sin transportistas activos con vehículo activo»; si no, los motivos
    distintos de los que no cumplen, en el orden de la regla, en minúscula y separados por « · »."""
    motivos = {c.motivo for c in candidatos if c.motivo is not None}
    if not motivos or motivos <= {M_INACTIVO, M_SIN_VEHICULO}:
        return SIN_FLOTA
    return " · ".join(m.lower() for m in MOTIVOS if m in motivos)


def _entregas_del_transportista(transportista_id, fecha):
    """Las entregas no canceladas del transportista en la fecha (las cuenta la capacidad y los límites diarios)."""
    return Entrega.objects.filter(transportista_id=transportista_id, fecha_programada_orden=fecha).exclude(estado_orden=OrdenTrabajo.Estado.CANCELADA)


def entrega_para_agrupar(contrato, invernadero, destino, fecha, peso_nuevo, hoy):
    """Extensión 4a (y D-66 punto 7): la entrega del **mismo contrato**, invernadero, destino (`direccion_destino`, o `None` en un retiro) y fecha programada que está «a realizar», sin
    `ReservaInsumo` «activa» (sin envasado planificado) y, si tiene transportista, con lugar para `peso_nuevo` en su vehículo (la entrega ya cuenta en el día: no se suma una entrega
    ni una localidad nuevas) y fuera de ruta si la fecha es hoy. La de menor id si hay varias; `None` si ninguna cumple. `contrato` e `invernadero` pueden ser el objeto o su id."""
    activas = ReservaInsumo.objects.filter(orden_id=OuterRef("pk"), estado=ReservaInsumo.Estado.ACTIVA)
    candidatas = Entrega.objects.filter(
        contrato_entrega_id=getattr(contrato, "pk", contrato),
        invernadero_id=getattr(invernadero, "pk", invernadero),
        fecha_programada_orden=fecha,
        estado_orden=A_REALIZAR,
        **({"direccion_destino_id": destino} if destino is not None else {"direccion_destino__isnull": True}),
    ).exclude(Exists(activas))
    for candidata in candidatas.order_by("pk"):
        if candidata.transportista_id is None:
            return candidata
        vehiculo = Vehiculo.objects.filter(transportista_id=candidata.transportista_id).first()
        if vehiculo is None or (fecha == hoy and vehiculo.esta_en_ruta(hoy)):
            continue
        del_dia = peso_de_entregas(list(_entregas_del_transportista(candidata.transportista_id, fecha).values_list("pk", flat=True)))
        if sum(del_dia.values(), Decimal("0")) + peso_nuevo <= vehiculo.capacidad_carga:
            return candidata
    return None


# ---- qué se planifica (regla «Venta lista para entrega» y «Período listo para entrega») ----


def _origen_de_venta(compra_venta_id):
    return Origen("venta", compra_venta_id, None, None)


def _origen_de_periodo(detalle_suministro_id, fecha):
    suministro_id = DetalleSuministro.objects.filter(pk=detalle_suministro_id).values_list("suministro_id", flat=True).first()
    return Origen("periodo", suministro_id, detalle_suministro_id, fecha)


def _vivas(origen):
    """Las reservas no liberadas del origen (una venta: las de sus detalles «abierto» o «confirmado»; un período: las de ese detalle y esa fecha)."""
    if origen.tipo == "venta":
        reservas = ReservaStock.objects.filter(
            detalle_venta__compra_venta_id=origen.contrato_id, detalle_venta__estado_detalle_venta__in=(DetalleVenta.Estado.ABIERTO, DetalleVenta.Estado.CONFIRMADO)
        )
    else:
        reservas = ReservaStock.objects.filter(detalle_suministro_id=origen.detalle_id, fecha_entrega_reserva=origen.fecha)
    return reservas.exclude(estado_reserva=ReservaStock.Estado.LIBERADA)


def _reservas_a_planificar(origen):
    """Las reservas «lista para entrega» sin línea en una entrega no cancelada, **si** la venta o el período están listos (precondición c); si no, lista vacía. Venta lista: «abierta»,
    ningún detalle «pendiente de decisión» y ninguna reserva «activa». Período listo: suministro «vigente» (también con rescisión acordada), detalle «vigente» o «finalizado» con el
    período por deber (D-64 punto 8) y ninguna reserva «activa». Sin consultas de más: una por condición."""
    if origen.tipo == "venta":
        venta = CompraVenta.objects.filter(pk=origen.contrato_id).first()
        if venta is None or venta.estado_venta != CompraVenta.Estado.ABIERTA:
            return []
        if DetalleVenta.objects.filter(compra_venta_id=venta.pk, estado_detalle_venta=DetalleVenta.Estado.PENDIENTE_DECISION).exists():
            return []
    else:
        detalle = DetalleSuministro.objects.select_related("suministro").filter(pk=origen.detalle_id).first()
        if detalle is None or detalle.suministro.estado_suministro != Suministro.Estado.VIGENTE or not stock_maduro._se_debe(detalle, origen.fecha):
            return []
    vivas = _vivas(origen)
    if vivas.filter(estado_reserva=ReservaStock.Estado.ACTIVA).exists():
        return []
    return list(
        vivas.filter(estado_reserva=LISTA)
        .exclude(lineas_de_entrega__entrega__estado_orden__in=NO_CANCELADAS)
        .select_related("detalle_venta__variedad", "detalle_venta__compra_venta", "detalle_suministro__variedad", "detalle_suministro__suministro")
        .order_by("pk")
    )


def _alcance_de(detalle):
    """`(id del contrato, modalidad, id de la dirección de destino)` que fija un detalle (regla «Alcance de una entrega»): una venta con envío, su dirección de envío; con retiro,
    ninguna; un suministro, siempre con envío a la dirección de su detalle."""
    if isinstance(detalle, DetalleVenta):
        venta = detalle.compra_venta
        return venta.pk, venta.modalidad_entrega, venta.direccion_envio_id if venta.modalidad_entrega == ENVIO else None
    return detalle.suministro_id, ENVIO, detalle.direccion_id


def _precio(detalle, fecha_programada):
    """Precio unitario al planificar: el del detalle de venta, o el del período con la fecha programada (regla 7 de 8.11)."""
    if isinstance(detalle, DetalleVenta):
        return detalle.precio_unitario_de_venta
    return calendario.precio_en(detalle, fecha_programada)


def _lineas_de(reservas, origen, fecha_programada):
    """Las `LineaNueva` de un conjunto de reservas: una por detalle de venta, o la del período."""
    if origen.tipo == "periodo":
        detalle = reservas[0].detalle_suministro
        return [LineaNueva(detalle, origen.fecha, reservas, _precio(detalle, fecha_programada))]
    por_detalle = {}
    for reserva in reservas:
        por_detalle.setdefault(reserva.detalle_venta_id, []).append(reserva)
    return [LineaNueva(rs[0].detalle_venta, None, rs, _precio(rs[0].detalle_venta, fecha_programada)) for rs in por_detalle.values()]


def _peso_de_lineas(lineas):
    """El peso (kg) de lo que llevan estas líneas nuevas, con la misma fórmula que `peso_de_entregas` (cantidad cubierta de sus reservas × gramos por planta / 1.000)."""
    cubierto = defaultdict(int)
    reservas = {r.pk for linea in lineas for r in linea.reservas}
    for reserva_id, reservada, cosechada, lote_id in DetalleReserva.objects.filter(reserva_id__in=reservas).values_list(
        "reserva_id", "cantidad_reservada", "cantidad_cosechada", "lote_id"
    ):
        cubierto[reserva_id] += stock_maduro._cubierto(reservada, cosechada, lote_id)
    gramos = sum(sum(cubierto[r.pk] for r in linea.reservas) * linea.detalle.variedad.peso_promedio_planta for linea in lineas)
    return _redondear(Decimal(gramos) / 1000)


# ---- escribir una entrega (la única función que escribe los datos copiados, D-66 punto 3) ----


def _agregar_lineas(entrega, lineas):
    """Agrega las `LineaNueva` a `entrega`: una línea por detalle (o período); si la entrega ya tiene la línea de ese detalle, le suma las reservas (D-66 punto 7). Rechaza con
    `detalle_fuera_de_alcance` un detalle de otro contrato, otra modalidad u otra dirección (D-66 punto 3, refuerzos). Devuelve `(líneas creadas, líneas ampliadas)`."""
    existentes = {(l.detalle_venta_id, l.detalle_suministro_id, l.fecha_periodo): l for l in entrega.lineas.all()}
    creadas, ampliadas = [], []
    for nueva in lineas:
        if _alcance_de(nueva.detalle) != (entrega.contrato_entrega_id, entrega.modalidad_entrega, entrega.direccion_destino_id):
            raise _rechazar("detalle_fuera_de_alcance", "Ese detalle es de otro contrato, otra modalidad u otra dirección: no entra en esta entrega.")
        de_venta = isinstance(nueva.detalle, DetalleVenta)
        clave = (nueva.detalle.pk, None, None) if de_venta else (None, nueva.detalle.pk, nueva.fecha_periodo)
        existente = existentes.get(clave)
        if existente is not None:
            existente.reservas.add(*nueva.reservas)
            ampliadas.append(existente)
            continue
        linea = DetalleEntrega.objects.create(
            entrega=entrega,
            detalle_venta=nueva.detalle if de_venta else None,
            detalle_suministro=None if de_venta else nueva.detalle,
            fecha_periodo=None if de_venta else nueva.fecha_periodo,
            precio_unitario=nueva.precio,
        )
        linea.reservas.set(nueva.reservas)
        existentes[clave] = linea
        creadas.append(linea)
    return creadas, ampliadas


def _crear_entrega(invernadero, fecha, lineas, transportista, hoy):
    """Crea la `Entrega` «a realizar» con sus líneas. **Es la única función que escribe `contrato_entrega`, `modalidad_entrega` y `direccion_destino`**, que salen del primer detalle
    (regla «Alcance de una entrega»); `_agregar_lineas` rechaza una línea que no coincida. Nace sin Agrónomo (la planificó InfoPonia) y, en un suministro, `no_confirmado`."""
    contrato_id, modalidad, destino = _alcance_de(lineas[0].detalle)
    entrega = Entrega.objects.create(
        tipo_orden=OrdenTrabajo.Tipo.ENTREGA,
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=hoy,
        fecha_programada_orden=fecha,
        invernadero=invernadero,
        agronomo=None,
        contrato_entrega_id=contrato_id,
        modalidad_entrega=modalidad,
        direccion_destino_id=destino,
        transportista=transportista,
        estado_confirmacion_cliente=Entrega.Confirmacion.NO_CONFIRMADO if isinstance(lineas[0].detalle, DetalleSuministro) else None,
    )
    creadas, _ = _agregar_lineas(entrega, lineas)
    return entrega, creadas


def _contenido(entrega):
    """`(partes, total)`: «100 Lechuga Crespa», «40 Rúcula»… con lo planificado de cada línea (las líneas quitadas no se muestran) y el total de plantas."""
    lineas = list(entrega.lineas.select_related("detalle_venta__variedad__cultivo", "detalle_suministro__variedad__cultivo").order_by("pk"))
    planificadas = cantidades_planificadas([l.pk for l in lineas])
    partes, total = [], 0
    for linea in lineas:
        if planificadas[linea.pk] > 0:
            partes.append(f"{planificadas[linea.pk]} {(linea.detalle_venta or linea.detalle_suministro).variedad}")
            total += planificadas[linea.pk]
    return partes, total


def _con_contenido(prefijo, partes, sufijo, total, largo=LARGO_DEL_DETALLE):
    """El texto `prefijo + partes + sufijo`; si pasa de `largo`, se recorta con «…» y se cierra con el total de plantas (regla de «Avisos y textos»)."""
    texto = prefijo + ", ".join(partes) + sufijo
    if len(texto) <= largo:
        return texto
    cierre = f"… ({total} plantas en total)" + sufijo
    visibles = list(partes)
    while visibles and len(prefijo + ", ".join(visibles) + cierre) > largo:
        visibles.pop()
    return prefijo + ", ".join(visibles) + cierre


def _destino_texto(entrega):
    """El destino que dicen los avisos: la dirección con envío; con retiro, «retiro en <invernadero>»."""
    if entrega.modalidad_entrega == ENVIO:
        return str(Direccion.objects.get(pk=entrega.direccion_destino_id))
    return f"retiro en {entrega.invernadero}"


def _avisar_al_vendedor(contrato, titulo, detalle):
    """Una notificación al Vendedor del contrato si su cuenta está activa (si no, nada)."""
    vendedor = _usuario_activo(contrato.vendedor_id)
    if vendedor is not None:
        notificaciones.notificar(vendedor, _acotar(titulo, LARGO_DEL_TITULO), _acotar(detalle, LARGO_DEL_DETALLE))
    return vendedor


def _avisar_envasado_al_agronomo(entrega, contrato, peso):
    """Paso 10 (h) de COM-PNF-ENT («Avisos y textos»): al Agrónomo del invernadero de origen, si su cuenta está activa, «Planificá el envasado de OT-0231». Sin Agrónomo
    activo no se envía (regla «Invernadero sin Agrónomo» de PROD-PNF-ENV: lo verá el que se asigne). El texto nombra la pantalla («Producción › Envasado»), sin enlace (D-42).
    Se avisa por cada entrega nueva y, en el agrupamiento (extensión 4a), con la entrega completa. Dentro de la transacción (D-42)."""
    agronomo = _usuario_activo(Invernadero.objects.filter(pk=entrega.invernadero_id).values_list("agronomo_id", flat=True).first())
    if agronomo is None:
        return None
    partes, total = _contenido(entrega)
    modalidad = "retiro" if entrega.modalidad_entrega == RETIRO else "envío"
    prefijo = f"Entrega del {entrega.fecha_programada_orden:%d/%m} a {_cliente_de(contrato)} ({modalidad}): "
    notificaciones.notificar(
        agronomo,
        _acotar(f"Planificá el envasado de {entrega.codigo}", LARGO_DEL_TITULO),
        _con_contenido(prefijo, partes, f" · {_kg(peso)}. Está en Producción › Envasado.", total),
    )
    return agronomo


def _avisar_nueva_entrega_al_transportista(entrega, contrato, peso):
    """Paso 9 (c) y 1b.4.3: «Nueva entrega para el 26/11»."""
    partes, total = _contenido(entrega)
    prefijo = f"{entrega.codigo} · {_cliente_de(contrato)} · {_destino_texto(entrega)} · {_kg(peso)}: "
    notificaciones.notificar(
        entrega.transportista,
        f"Nueva entrega para el {entrega.fecha_programada_orden:%d/%m}",
        _con_contenido(prefijo, partes, ".", total),
    )


def _aviso_de_retraso(entrega, contrato, prometida):
    """3a.2 (g, j): al Vendedor, que la entrega sale con retraso; en un suministro, con la advertencia de queja o indemnización."""
    detalle = f"La fecha prometida era el {prometida:%d/%m} y sale el {entrega.fecha_programada_orden:%d/%m}."
    if contrato.tipo_contrato == Contrato.Tipo.SUMINISTRO:
        detalle += " Puede haber una queja o una indemnización según la cláusula del suministrante."
    _avisar_al_vendedor(contrato, f"Entrega con retraso: {entrega.codigo}", detalle)


def _descripcion_de_la_alerta(entrega, contrato, motivo):
    """«OT-0231 del 26/11 (Pérez SA) sin transportista: capacidad de carga insuficiente», en 200 caracteres como máximo: se recorta primero el cliente."""
    cliente = _cliente_de(contrato)
    texto = f"{entrega.codigo} del {entrega.fecha_programada_orden:%d/%m} ({{}}) sin transportista: {motivo}"
    sobra = len(texto.format(cliente)) - LARGO_DE_LA_ALERTA
    if sobra > 0:
        cliente = _acotar(cliente, max(1, len(cliente) - sobra))
    return texto.format(cliente)[:LARGO_DE_LA_ALERTA]


def _alerta_sin_transportista(entrega, contrato, motivo):
    """La alerta de estado «entrega sin transportista» para el Gerente (6a.2) con su `AlertaComercial`; `None` si el invernadero está inactivo."""
    alerta = alertas.asegurar_alerta_de_estado(
        entrega.invernadero_id, TIPO_SIN_TRANSPORTISTA, _clave_de_la_alerta(entrega.pk), _descripcion_de_la_alerta(entrega, contrato, motivo)
    )
    if alerta is not None:
        AlertaComercial.objects.get_or_create(alerta=alerta, defaults={"entrega": entrega})
    return alerta


# ---- el correo al cliente (paso 11, 2a.4 y 1b.4.2; D-66 punto 12) ----


def _prometida(entrega):
    """La fecha prometida: la pactada de la venta o la del período más próximo de sus líneas."""
    venta = CompraVenta.objects.filter(pk=entrega.contrato_entrega_id).values_list("fecha_pactada_venta", flat=True).first()
    if venta is not None:
        return venta
    return entrega.lineas.order_by("fecha_periodo").values_list("fecha_periodo", flat=True).first() or entrega.fecha_programada_orden


def _fue_movida(entrega):
    """El «último correo» que corresponde reintentar: el del cambio de fecha si la búsqueda diaria movió la fecha programada (queda posterior a la prometida y a la de creación);
    si no, el de la planificación."""
    return entrega.fecha_programada_orden > entrega.fecha_creacion_orden and entrega.fecha_programada_orden > _prometida(entrega)


def _marcar_aviso_pendiente(entrega, contrato, cambio_de_fecha):
    """Dentro de la transacción: el aviso nace «pendiente de envío» (o «sin correo» si el cliente no tiene) y el envío se programa para después de confirmar."""
    sin_correo = not contrato.cliente.email_cliente
    estado = AVISO.SIN_CORREO if sin_correo else AVISO.PENDIENTE_ENVIO
    Entrega.objects.filter(pk=entrega.pk).update(estado_aviso_cliente=estado)
    entrega.estado_aviso_cliente = estado
    if not sin_correo:
        transaction.on_commit(partial(_correr, enviar_correo_de_entrega, entrega.pk, cambio_de_fecha))


def enviar_correo_de_entrega(entrega_id, cambio_de_fecha=False):
    """El correo al cliente con la fecha, el destino y las variedades y cantidades (sin montos). Se llama SIEMPRE fuera de una transacción (D-14, D-54). Sin el correo del sistema
    configurado o si el envío falla, queda «pendiente de envío» (lo reintenta el paso 50); si sale, «enviado». Devuelve `True` si salió."""
    entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor", "invernadero").filter(pk=entrega_id).first()
    if entrega is None or entrega.estado_orden != A_REALIZAR or entrega.estado_aviso_cliente != AVISO.PENDIENTE_ENVIO:
        return False
    contrato = entrega.contrato_entrega
    if not contrato.cliente.email_cliente or not correo.correo_configurado():
        return False
    partes, _ = _contenido(entrega)
    if entrega.modalidad_entrega == ENVIO:
        destino = str(Direccion.objects.get(pk=entrega.direccion_destino_id))
    else:
        destino = f"Retirala en {entrega.invernadero}, {entrega.invernadero.direccion}"
    asunto = (
        f"Cambió la fecha de tu entrega {entrega.codigo}: ahora es el {entrega.fecha_programada_orden:%d/%m}"
        if cambio_de_fecha
        else f"Tu entrega del {entrega.fecha_programada_orden:%d/%m} ({entrega.codigo})"
    )
    salio = correo.enviar_correo(
        Destinatario(contrato.cliente.pk, contrato.cliente.email_cliente),
        asunto,
        "comercial/correos/entrega_cambio_de_fecha.txt" if cambio_de_fecha else "comercial/correos/entrega_planificada.txt",
        {
            "codigo": entrega.codigo,
            "cliente": contrato.cliente.nombre_visible,
            "fecha": entrega.fecha_programada_orden,
            "destino": destino,
            "retiro": entrega.modalidad_entrega == RETIRO,
            "partes": partes,
            "vendedor": contrato.vendedor,
        },
    )
    if salio:
        Entrega.objects.filter(pk=entrega.pk, estado_aviso_cliente=AVISO.PENDIENTE_ENVIO).update(estado_aviso_cliente=AVISO.ENVIADO)
    return salio


# ---- COM-PNF-ENT inmediato: una transacción por invernadero de origen ----


def _planificar_en_invernadero(origen, invernadero_id, hoy):
    """Pasos 2 a 11 para un invernadero de origen, en su transacción (extensión \\*a). Devuelve el `ResultadoDePlanificacion` o `None` si no había nada que registrar (8b: algo
    cambió) o el invernadero está inactivo."""
    previas = [r for r in _reservas_a_planificar(origen) if r.invernadero_id == invernadero_id]
    if not previas:
        return None
    contrato_previo = Contrato.objects.get(pk=origen.contrato_id)
    agronomo_id = Invernadero.objects.filter(pk=invernadero_id).values_list("agronomo_id", flat=True).first()
    transportistas = list(TransportistaInvernadero.objects.filter(invernadero_id=invernadero_id).values_list("transportista_id", flat=True))
    with transaction.atomic():
        cuentas = {c for c in (contrato_previo.vendedor_id, agronomo_id, *transportistas) if c}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        try:
            invernadero = bloquear_invernadero_activo(invernadero_id)
        except ValidationError:
            return None  # el invernadero se dio de baja mientras tanto: no se planifica nada con origen en él
        list(Cliente.objects.select_for_update(no_key=True).filter(pk=contrato_previo.cliente_id))
        if origen.tipo == "venta":
            list(CompraVenta.objects.select_for_update(no_key=True, of=("self",)).filter(pk=origen.contrato_id))
            list(DetalleVenta.objects.select_for_update(no_key=True).filter(compra_venta_id=origen.contrato_id).order_by("pk"))
        else:
            list(Suministro.objects.select_for_update(no_key=True, of=("self",)).filter(pk=origen.contrato_id))
            list(DetalleSuministro.objects.select_for_update(no_key=True, of=("self",)).filter(suministro_id=origen.contrato_id).order_by("pk"))
        list(ReservaStock.objects.select_for_update(no_key=True).filter(pk__in=_vivas(origen).values("pk")).order_by("pk"))
        agrupables = Entrega.objects.filter(contrato_entrega_id=origen.contrato_id, invernadero_id=invernadero_id, estado_orden=A_REALIZAR)
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=agrupables.values("pk")).order_by("pk"))
        list(ReservaInsumo.objects.select_for_update(no_key=True).filter(orden_id__in=agrupables.values("pk")).order_by("pk"))

        # 8b: con todo bloqueado, se vuelve a leer qué sigue listo y sin línea. Si no queda nada, no se registra esta entrega.
        reservas = [r for r in _reservas_a_planificar(origen) if r.invernadero_id == invernadero_id]
        if not reservas:
            return None
        contrato = Contrato.objects.select_related("cliente", "vendedor").get(pk=origen.contrato_id)
        prometida = origen.fecha if origen.tipo == "periodo" else CompraVenta.objects.get(pk=contrato.pk).fecha_pactada_venta
        fecha = prometida if prometida >= hoy else hoy  # paso 3 y extensión 3a: no hay entregas anticipadas ni con fecha pasada
        lineas = _lineas_de(reservas, origen, fecha)
        contrato_id, modalidad, destino = _alcance_de(lineas[0].detalle)
        peso = _peso_de_lineas(lineas)

        agrupada = entrega_para_agrupar(contrato, invernadero, destino, fecha, peso, hoy)  # extensión 4a (y D-66 punto 7)
        if agrupada is not None:
            return _agregar_a_entrega_existente(agrupada, contrato, lineas, reservas, hoy)

        transportista, candidatos, motivo = None, [], None
        if modalidad == ENVIO:
            localidad = Direccion.objects.filter(pk=destino).values_list("localidad_id", flat=True).first()
            candidatos = candidatos_para(invernadero, fecha, peso, localidad, hoy=hoy)
            elegido = seleccionar(candidatos)
            transportista = elegido.transportista if elegido is not None else None
            motivo = None if elegido is not None else motivo_de_alerta(candidatos)
        entrega, creadas = _crear_entrega(invernadero, fecha, lineas, transportista, hoy)
        alerta = None
        if modalidad == RETIRO:
            partes, total = _contenido(entrega)
            prefijo = f"{_cliente_de(contrato)} retira el {fecha:%d/%m} en {invernadero}: "
            _avisar_al_vendedor(contrato, f"Retiro planificado: {entrega.codigo}", _con_contenido(prefijo, partes, ". Lo concretás vos cuando el cliente venga.", total))
        elif transportista is not None:
            _avisar_nueva_entrega_al_transportista(entrega, contrato, peso)
        else:
            alerta = _alerta_sin_transportista(entrega, contrato, motivo)
            detalle = f"{contrato.codigo} · {_cliente_de(contrato)} · {fecha:%d/%m}. Motivo: {motivo}. InfoPonia vuelve a buscar cada día; el Gerente tiene la alerta."
            _avisar_al_vendedor(contrato, f"Entrega sin transportista: {entrega.codigo}", detalle)
        if prometida < hoy:
            _aviso_de_retraso(entrega, contrato, prometida)
        _avisar_envasado_al_agronomo(entrega, contrato, peso)  # paso 10 (h): COM-05a2
        _marcar_aviso_pendiente(entrega, contrato, cambio_de_fecha=False)
        cantidades = cantidades_planificadas([l.pk for l in creadas])
        datos = {
            "entrega": referencia(entrega),
            "contrato": contrato.codigo,
            "fecha_programada": f"{fecha:%d/%m/%Y}",
            "destino": _destino_texto(entrega),
            "peso": f"{peso:.2f}",
            "lineas_de_entrega": [f"{(l.detalle_venta or l.detalle_suministro).variedad}: {cantidades[l.pk]}" for l in creadas],
        }
        if transportista is not None:
            datos["transportista"] = referencia(transportista)
        elif modalidad == ENVIO:
            datos["motivo_sin_transportista"] = motivo
        if alerta is not None:
            datos["alertas_creadas"] = [referencia(alerta)]
        RegistroAuditoria.objects.registrar(
            usuario=None,
            accion=RegistroAuditoria.Accion.PLANIFICACION_ENTREGA,
            afectados=[entrega, *creadas, *reservas, *([alerta] if alerta is not None else [])],
            detalle={"datos": datos},
        )
        return ResultadoDePlanificacion(entrega, True, False, transportista, motivo, alerta)


def _cantidad_de(reservas):
    """La cantidad cubierta (regla 9 de 8.8) por estas reservas."""
    cubierto = 0
    for reservada, cosechada, lote_id in DetalleReserva.objects.filter(reserva__in=[r.pk for r in reservas]).values_list("cantidad_reservada", "cantidad_cosechada", "lote_id"):
        cubierto += stock_maduro._cubierto(reservada, cosechada, lote_id)
    return cubierto


def _agregar_a_entrega_existente(entrega, contrato, lineas, reservas, hoy):
    """Extensión 4a: las líneas nuevas se agregan a la entrega que cumple las condiciones de agrupamiento, con su auditoría `modificacion_entrega` y el aviso del cambio al
    transportista si lo tiene (f). El correo al cliente sale con la entrega completa."""
    creadas, ampliadas = _agregar_lineas(entrega, lineas)
    nueva = peso_de_entregas([entrega.pk])[entrega.pk]
    partes = [f"{_cantidad_de(l.reservas)} {l.detalle.variedad}" for l in lineas]
    transportista = Usuario.objects.filter(pk=entrega.transportista_id, is_active=True).first()
    if transportista is not None:
        notificaciones.notificar(
            transportista,
            f"Cambió la entrega {entrega.codigo}",
            _acotar(f"Se agregaron {', '.join(partes)} de {contrato.codigo}. Peso nuevo: {_kg(nueva)}.", LARGO_DEL_DETALLE),
        )
    _avisar_envasado_al_agronomo(entrega, contrato, nueva)  # paso 10 (h): con la entrega completa (COM-05a2)
    _marcar_aviso_pendiente(entrega, contrato, cambio_de_fecha=False)
    RegistroAuditoria.objects.registrar(
        usuario=None,
        accion=RegistroAuditoria.Accion.MODIFICACION_ENTREGA,
        afectados=[entrega, *creadas, *ampliadas, *reservas],
        detalle={"datos": {"entrega": referencia(entrega), "contrato": contrato.codigo, "lineas_agregadas": partes, "peso": f"{nueva:.2f}"}},
    )
    return ResultadoDePlanificacion(entrega, False, True, entrega.transportista, None, None)


def _planificar(origen, hoy):
    """Planifica lo listo del origen, una transacción por invernadero de origen. Una excepción en un invernadero se registra y no corta los demás (extensión \\*a)."""
    resultados = []
    for invernadero_id in sorted({r.invernadero_id for r in _reservas_a_planificar(origen)}):
        try:
            resultado = _planificar_en_invernadero(origen, invernadero_id, hoy)
        except Exception:  # noqa: BLE001 - una planificación que falla no puede dejar sin planificar a los demás invernaderos (extensión *a); la retoma el paso 50
            logger.exception("Falló la planificación de la entrega de %s en el invernadero %s", origen, invernadero_id)
            continue
        if resultado is not None:
            resultados.append(resultado)
    return resultados


def planificar_venta(compra_venta_id, hoy=None):
    """COM-PNF-ENT para una compra-venta: vuelve a leer si está lista y planifica una entrega por invernadero de origen. Devuelve los `ResultadoDePlanificacion`. NO se llama dentro
    de una transacción de quien dispara: la dispara `programar_planificacion_de_venta` con `on_commit` (D-66 punto 5)."""
    return _planificar(_origen_de_venta(compra_venta_id), hoy or stock.hoy())


def planificar_periodo(detalle_suministro_id, fecha_periodo, hoy=None):
    """COM-PNF-ENT para un período de un detalle de suministro (extensión 1a). Igual que `planificar_venta`."""
    return _planificar(_origen_de_periodo(detalle_suministro_id, fecha_periodo), hoy or stock.hoy())


def _correr(funcion, *argumentos):
    """Corre una planificación de un `on_commit` sin que una falla vuelva a quien disparó: su operación ya quedó registrada (D-66 punto 5)."""
    try:
        funcion(*argumentos)
    except Exception:  # noqa: BLE001
        logger.exception("Falló la planificación de la entrega disparada por %s%s", funcion.__name__, argumentos)


def programar_planificacion_de_venta(compra_venta_id):
    """D-66 punto 5: registra con `transaction.on_commit` la planificación de la venta, para que corra DESPUÉS de confirmar la transacción de quien la dispara. No hace nada más."""
    transaction.on_commit(partial(_correr, planificar_venta, compra_venta_id))


def programar_planificacion_de_periodo(detalle_suministro_id, fecha_periodo):
    """D-66 punto 5: como `programar_planificacion_de_venta`, para un período de suministro."""
    transaction.on_commit(partial(_correr, planificar_periodo, detalle_suministro_id, fecha_periodo))


def programar_para_reservas(reserva_ids):
    """Programa la planificación de cada venta o período al que pertenecen las reservas «lista para entrega» de `reserva_ids` (las que dejó un caso de uso que las crea o las deja
    listas). Las reservas sin contrato (una cosecha manual) no planifican nada. Si no quedó nada listo, no registra nada; `planificar_*` vuelve a leer igual (8b)."""
    reserva_ids = [r for r in reserva_ids if r]
    if not reserva_ids:
        return
    ventas, periodos = set(), set()
    for venta_id, detalle_id, fecha in ReservaStock.objects.filter(pk__in=reserva_ids, estado_reserva=LISTA).values_list(
        "detalle_venta__compra_venta_id", "detalle_suministro_id", "fecha_entrega_reserva"
    ):
        if venta_id:
            ventas.add(venta_id)
        elif detalle_id:
            periodos.add((detalle_id, fecha))
    for venta_id in sorted(ventas):
        programar_planificacion_de_venta(venta_id)
    for detalle_id, fecha in sorted(periodos):
        programar_planificacion_de_periodo(detalle_id, fecha)


# ---- cancelación de una entrega (PROD-CNL-ORD, «solo desde otro caso de uso») ----


def _aviso_de_cancelacion_al_transportista(entrega, motivo, en_curso_):
    """Al transportista de la entrega: «Se canceló la entrega OT-0231», y si estaba en curso (situación 11), que no la entregue y devuelva el producto y los envases."""
    detalle = motivo.rstrip(".") + "."
    if en_curso_:
        detalle += f" No la entregues: devolvé el producto y los envases a {entrega.invernadero}."
    notificaciones.notificar(entrega.transportista, f"Se canceló la entrega {entrega.codigo}", _acotar(detalle, LARGO_DEL_DETALLE))


def cancelar_entrega_incluida(actor, entrega, motivo):
    """La «Cancelación de una entrega» de PROD-CNL-ORD (solo desde otro caso de uso: PROD-VNC-CAM 3a, PROD-REG-MRM 10c, y después COM-CNL-CVT y COM-RSV-SUM). Como
    `cancelar_cosecha_incluida`: `actor` puede ser `None` (InfoPonia); corre en la transacción del llamador, que ya tiene el invernadero y sus filas (sin ella, `RuntimeError`);
    **no audita**: devuelve `CancelacionDeEntrega(entrega, reservas_de_insumo, alerta_resuelta, avisados)` para el registro del llamador (D-36). No toca las reservas de stock.

    - Motivo vacío: `motivo_obligatorio`. La entrega ya no «a realizar» (la concretó o la canceló otro): `entrega_no_a_realizar`, y el caso de uso base decide cómo sigue (8a).
    - La orden pasa a «cancelada» con `ordenes.cancelar_orden_incluida` (que también cancela sus reservas de insumo, sin consumo); se resuelve la alerta «entrega sin transportista».
    - Avisos dentro de la transacción: al transportista (con «No la entregues…» si está en curso) y al Agrónomo activo si tenía envasado. El aviso al cliente lo manda el caso de uso base."""
    _exigir_transaccion("cancelar_entrega_incluida")
    motivo = (motivo or "").strip()
    if not motivo:
        raise _rechazar("motivo_obligatorio", "Indicá el motivo de la cancelación.", "motivo")
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega.pk))
    actual = Entrega.objects.select_related("invernadero__agronomo", "transportista").get(pk=entrega.pk)
    if actual.estado_orden != A_REALIZAR:
        raise _rechazar("entrega_no_a_realizar", f"La entrega {actual.codigo} ya no está a realizar.")
    en_curso_ = en_curso(actual, stock.hoy())
    cancelacion = ordenes.cancelar_orden_incluida(actor, actual, motivo, avisar=False)
    alerta = alertas.resolver_alerta_de_estado(actual.invernadero_id, TIPO_SIN_TRANSPORTISTA, _clave_de_la_alerta(actual.pk))
    avisados = []
    transportista = actual.transportista
    if transportista is not None and transportista.is_active:
        _aviso_de_cancelacion_al_transportista(actual, actual.motivo_cancelacion, en_curso_)
        avisados.append(transportista)
    activas = list(cancelacion.reservas)
    agronomo = actual.invernadero.agronomo
    if activas and agronomo is not None and agronomo.is_active:
        existencias = {e.pk: e for e in InsumoInvernadero.objects.filter(pk__in=[r.insumo_invernadero_id for r in activas]).select_related("insumo")}
        reservados = ", ".join(f"{_cantidad(r.cantidad_reservada)} {existencias[r.insumo_invernadero_id].insumo.nombre_insumo}" for r in activas)
        notificaciones.notificar(
            agronomo,
            _acotar(f"Se canceló {actual.codigo}, que tenía envases reservados", LARGO_DEL_TITULO),
            _acotar(f"Reservados: {reservados}. Si ya se usaron y no se pueden volver a usar, ajustá el stock.", LARGO_DEL_DETALLE),
        )
        avisados.append(agronomo)
    return CancelacionDeEntrega(actual, activas, alerta, avisados)


def entregas_de_reservas(reserva_ids):
    """Los ids de las entregas «a realizar» que tienen una línea con alguna de estas reservas (las que PROD-VNC-CAM 3a y la merma en cámara 10c recortaron o liberaron)."""
    reserva_ids = list(reserva_ids)
    if not reserva_ids:
        return []
    return sorted(set(Entrega.objects.filter(estado_orden=A_REALIZAR, lineas__reservas__in=reserva_ids).values_list("pk", flat=True)))


def quitar_lineas_liberadas(actor, entrega_ids, motivo):
    """PROD-VNC-CAM 3a y PROD-REG-MRM 10c (D-66 punto 4): después de un recorte, las líneas cuyas reservas quedaron todas liberadas valen 0 y se dan por quitadas (no se borran:
    su cantidad planificada se calcula) y cada entrega «a realizar» con todas sus líneas quitadas está vacía y se cancela con `cancelar_entrega_incluida`, en la misma transacción.
    Bloquea las entregas (después de las reservas) en orden de id. Devuelve `QuitaDeLineas(líneas quitadas, cancelaciones)`; el llamador lo suma a su registro de auditoría."""
    _exigir_transaccion("quitar_lineas_liberadas")
    ids = sorted(set(entrega_ids))
    if not ids:
        return QuitaDeLineas([], [])
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=ids).order_by("pk"))
    del_caso = list(Entrega.objects.filter(pk__in=ids, estado_orden=A_REALIZAR).order_by("pk"))
    lineas = list(DetalleEntrega.objects.filter(entrega_id__in=[e.pk for e in del_caso]).order_by("pk"))
    planificadas = cantidades_planificadas([l.pk for l in lineas])
    quitadas = [l for l in lineas if planificadas[l.pk] == 0]
    cancelaciones = []
    for entrega in del_caso:
        if all(planificadas[l.pk] == 0 for l in lineas if l.entrega_id == entrega.pk):
            cancelaciones.append(cancelar_entrega_incluida(actor, entrega, motivo))
    return QuitaDeLineas(quitadas, cancelaciones)


# ---- el paso diario 50 (disparador 3) ----


def _buscar_transportista(entrega_id, hoy):
    """Partes 2 a 6 de 1b para una entrega con envío, «a realizar» y sin transportista, en su transacción. El resultado es `"asignada"`, `"recordada"`, `"sigue"` o `None` si ya no
    correspondía. Con candidato: lo asigna, pasa la fecha a hoy si había pasado (con el aviso de retraso al Vendedor y el correo al cliente), avisa al transportista y al Vendedor y
    resuelve la alerta. Sin candidato y con la fecha programada de mañana, el único recordatorio al Gerente y al Vendedor. Devuelve `(resultado, resolvió una alerta)`."""
    previa = Entrega.objects.select_related("contrato_entrega").get(pk=entrega_id)
    transportistas = list(TransportistaInvernadero.objects.filter(invernadero_id=previa.invernadero_id).values_list("transportista_id", flat=True))
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={c for c in (previa.contrato_entrega.vendedor_id, *transportistas) if c}).order_by("pk"))
        try:
            invernadero = bloquear_invernadero_activo(previa.invernadero_id)
        except ValidationError:
            return None, False
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega_id))
        entrega = Entrega.objects.select_related("invernadero").get(pk=entrega_id)
        if entrega.estado_orden != A_REALIZAR or entrega.transportista_id is not None or entrega.modalidad_entrega != ENVIO:
            return None, False
        contrato = Contrato.objects.select_related("cliente", "vendedor").get(pk=entrega.contrato_entrega_id)
        programada = entrega.fecha_programada_orden
        fecha = max(programada, hoy)
        peso = peso_de_entregas([entrega.pk])[entrega.pk]
        localidad = Direccion.objects.filter(pk=entrega.direccion_destino_id).values_list("localidad_id", flat=True).first()
        elegido = seleccionar(candidatos_para(invernadero, fecha, peso, localidad, hoy=hoy))
        if elegido is None:
            if programada == hoy + timedelta(days=1) and entrega.recordatorio_para != programada:
                detalle = f"{contrato.codigo} · {_cliente_de(contrato)}. Asignale uno o revisá la flota del invernadero."
                titulo = f"Mañana sale {entrega.codigo} sin transportista"
                notificaciones.notificar_al_gerente(titulo, detalle)
                _avisar_al_vendedor(contrato, titulo, detalle)
                Entrega.objects.filter(pk=entrega.pk).update(recordatorio_para=programada)
                return "recordada", False
            return "sigue", False
        transportista = elegido.transportista
        movida = programada < hoy
        cambios = {"transportista": {"antes": None, "despues": referencia(transportista)}}
        entrega.transportista = transportista
        campos = {"transportista": transportista}
        if movida:
            campos["fecha_programada_orden"] = hoy
            cambios["fecha_programada_orden"] = {"antes": f"{programada:%d/%m/%Y}", "despues": f"{hoy:%d/%m/%Y}"}
        Entrega.objects.filter(pk=entrega.pk).update(**campos)
        entrega.fecha_programada_orden = fecha
        if movida:
            _aviso_de_retraso(entrega, contrato, programada)
            _marcar_aviso_pendiente(entrega, contrato, cambio_de_fecha=True)
        _avisar_nueva_entrega_al_transportista(entrega, contrato, peso)
        _avisar_al_vendedor(contrato, f"{entrega.codigo} ya tiene transportista", f"Lo lleva {transportista.get_full_name()} el {entrega.fecha_programada_orden:%d/%m}.")
        resuelta = alertas.resolver_alerta_de_estado(entrega.invernadero_id, TIPO_SIN_TRANSPORTISTA, _clave_de_la_alerta(entrega.pk))
        datos = {"entrega": referencia(entrega), "contrato": contrato.codigo}
        if resuelta is not None:
            datos["alertas_resueltas"] = [referencia(resuelta)]
        RegistroAuditoria.objects.registrar(
            usuario=None,
            accion=RegistroAuditoria.Accion.ASIGNACION_TRANSPORTISTA,
            afectados=[entrega, transportista, *([resuelta] if resuelta is not None else [])],
            detalle={"cambios": cambios, "datos": datos},
        )
        return "asignada", resuelta is not None


def _avisar_atrasada(entrega_id, hoy):
    """Parte 3 (n, PCU 8): un aviso único al Vendedor y al Gerente por una entrega con envío, «a realizar», con transportista y con la fecha programada vencida; se guarda la fecha
    avisada (`aviso_atrasada_para`): si cambia, el aviso puede volver a salir. No cambia nada más (la reasignación es de una persona). Devuelve `True` si avisó."""
    previa = Entrega.objects.select_related("contrato_entrega").get(pk=entrega_id)
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={c for c in (previa.contrato_entrega.vendedor_id, previa.transportista_id) if c}).order_by("pk"))
        try:
            bloquear_invernadero_activo(previa.invernadero_id)
        except ValidationError:
            return False
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega_id))
        entrega = Entrega.objects.select_related("transportista").get(pk=entrega_id)
        if (
            entrega.estado_orden != A_REALIZAR
            or entrega.transportista_id is None
            or entrega.fecha_programada_orden >= hoy
            or entrega.aviso_atrasada_para == entrega.fecha_programada_orden
        ):
            return False
        contrato = Contrato.objects.select_related("cliente").get(pk=entrega.contrato_entrega_id)
        titulo = f"Entrega atrasada: {entrega.codigo}"
        detalle = f"Era para el {entrega.fecha_programada_orden:%d/%m} con {entrega.transportista.get_full_name()} y sigue a realizar. Reasignala con «Asignar transportista»."
        notificaciones.notificar_al_gerente(titulo, detalle)
        _avisar_al_vendedor(contrato, titulo, detalle)
        Entrega.objects.filter(pk=entrega.pk).update(aviso_atrasada_para=entrega.fecha_programada_orden)
        return True


def _sin_entrega_aun():
    """Las ventas y los períodos con alguna reserva «lista para entrega» sin línea en una entrega no cancelada (la recuperación diaria, parte 1)."""
    listas = ReservaStock.objects.filter(estado_reserva=LISTA).exclude(lineas_de_entrega__entrega__estado_orden__in=NO_CANCELADAS)
    ventas = sorted(set(listas.filter(detalle_venta__compra_venta__estado_venta=CompraVenta.Estado.ABIERTA).values_list("detalle_venta__compra_venta_id", flat=True)))
    periodos = sorted(set(listas.filter(detalle_suministro__isnull=False).values_list("detalle_suministro_id", "fecha_entrega_reserva")))
    return ventas, periodos


def planificar_entregas(hoy):
    """Paso diario 50, «Planificar entregas» (disparador 3 de COM-PNF-ENT; D-66 punto 6), en cuatro partes y en este orden, cada elemento en su transacción (si uno falla se
    registra con `logger.exception` y siguen los demás):
    1. recuperación: lo listo sin entrega (postcondición l; también con la fecha pasada, 3a);
    2. búsqueda de transportista de las entregas con envío «a realizar» sin transportista, de invernaderos activos y **creadas antes de hoy** (postcondiciones j y k);
    3. aviso único de las atrasadas con transportista (postcondición n de PCU 8);
    4. reintento de los correos al cliente «pendientes de envío» (extensión 9-11a).
    Idempotente: dos corridas el mismo día no crean ni avisan nada nuevo. `ResumenDePaso(procesados, creados=entregas creadas, resueltos=alertas resueltas, detalle)`."""
    procesados = creados = resueltos = 0
    tocadas = set()  # las que esta corrida planificó o reasignó: su correo ya está programado con `on_commit` y la parte 4 no lo repite
    ventas, periodos = _sin_entrega_aun()
    for venta_id in ventas:
        procesados += 1
        resultados = planificar_venta(venta_id, hoy)
        tocadas.update(r.entrega.pk for r in resultados)
        creados += sum(1 for r in resultados if r.creada)
    for detalle_id, fecha in periodos:
        procesados += 1
        resultados = planificar_periodo(detalle_id, fecha, hoy)
        tocadas.update(r.entrega.pk for r in resultados)
        creados += sum(1 for r in resultados if r.creada)
    sin_transportista = Entrega.objects.filter(
        estado_orden=A_REALIZAR, modalidad_entrega=ENVIO, transportista__isnull=True, invernadero__estado_invernadero=Invernadero.Estado.ACTIVO, fecha_creacion_orden__lt=hoy
    )
    for entrega_id in list(sin_transportista.order_by("pk").values_list("pk", flat=True)):
        procesados += 1
        try:
            resultado, resuelta = _buscar_transportista(entrega_id, hoy)
        except Exception:  # noqa: BLE001 - una entrega que falla no puede dejar a las demás sin buscar (D-56, punto 5)
            logger.exception("Falló la búsqueda de transportista de la entrega %s", entrega_id)
            continue
        resueltos += 1 if resuelta else 0
        if resultado == "asignada":
            tocadas.add(entrega_id)
    atrasadas = Entrega.objects.filter(
        estado_orden=A_REALIZAR, modalidad_entrega=ENVIO, transportista__isnull=False, fecha_programada_orden__lt=hoy, invernadero__estado_invernadero=Invernadero.Estado.ACTIVO
    ).filter(Q(aviso_atrasada_para__isnull=True) | ~Q(aviso_atrasada_para=F("fecha_programada_orden")))
    for entrega_id in list(atrasadas.order_by("pk").values_list("pk", flat=True)):
        procesados += 1
        try:
            _avisar_atrasada(entrega_id, hoy)
        except Exception:  # noqa: BLE001
            logger.exception("Falló el aviso de la entrega atrasada %s", entrega_id)
    for entrega in list(Entrega.objects.filter(estado_orden=A_REALIZAR, estado_aviso_cliente=AVISO.PENDIENTE_ENVIO).exclude(pk__in=tocadas).order_by("pk")):
        procesados += 1
        try:
            enviar_correo_de_entrega(entrega.pk, _fue_movida(entrega))
        except Exception:  # noqa: BLE001
            logger.exception("Falló el reintento del correo de la entrega %s", entrega.pk)
    siguen = Entrega.objects.filter(estado_orden=A_REALIZAR, modalidad_entrega=ENVIO, transportista__isnull=True).count()
    return ResumenDePaso(procesados, creados, resueltos, f"{siguen} entregas siguen sin transportista")


# ---- lo que `comercial` registra para que otras tareas respeten las entregas (docs/casos_de_uso/comercial/entregas.md, «Lo que completa a otras tareas») ----


def a_realizar_de(transportista_ids):
    """``{id de transportista: [entregas «a realizar»]}``, cada lista por fecha programada e id. Una consulta."""
    por_transportista = defaultdict(list)
    for entrega in Entrega.objects.filter(transportista_id__in=list(transportista_ids), estado_orden=A_REALIZAR).order_by("fecha_programada_orden", "pk"):
        por_transportista[entrega.transportista_id].append(entrega)
    return por_transportista


def url_de_entregas(**filtros):
    """La URL de la lista de entregas con esos filtros (`entrega=<id>`, `transportista=<id>`)."""
    consulta = "&".join(f"{k}={v}" for k, v in filtros.items())
    return reverse("comercial:entregas") + (f"?{consulta}" if consulta else "")


def impedimentos_de_transportista(transportista):
    """`registrar_impedimento_de_transportista` (reglas 9 y 10 de PROD-MOD-INV; punto 2 de «Cuando exista Entrega»): `transportista_con_entregas` si tiene entregas «a realizar»:
    «Tiene N entregas a realizar (la próxima, OT-0231 del 26/11).». `transportista_en_ruta` es de COM-06. Solo lectura."""
    propias = a_realizar_de([transportista.pk]).get(transportista.pk, [])
    if not propias:
        return []
    proxima = propias[0]
    cuantas = f"{len(propias)} entregas a realizar" if len(propias) != 1 else "1 entrega a realizar"
    return [
        Impedimento(
            "transportista_con_entregas",
            f"Tiene {cuantas} (la próxima, {proxima.codigo} del {proxima.fecha_programada_orden:%d/%m}).",
            "Reasignalas a otro transportista con «Asignar transportista» (Comercial › Entregas) y volvé a intentarlo.",
            url_de_entregas(transportista=transportista.pk),
        )
    ]


def asignaciones_de_cuenta(cuenta):
    """`registrar_asignaciones_de_cuenta` (regla 4 de USR-BAJ-USR): «Entregas a realizar: N» de un Transportista. Los demás roles, nada. Solo lectura."""
    if cuenta.rol != TRANSPORTISTA:
        return []
    cantidad = Entrega.objects.filter(transportista_id=cuenta.pk, estado_orden=A_REALIZAR).count()
    if not cantidad:
        return []
    return [Asignacion("Entregas a realizar", cantidad, "Quedan sin transportista, con una alerta para el Gerente, y InfoPonia les busca otro cada día.")]


def efecto_de_baja_de_cuenta(actor, cuenta):
    """`registrar_efecto_de_baja_de_cuenta` (postcondición g de USR-BAJ-USR): las entregas «a realizar» de un Transportista dado de baja quedan **sin transportista**, con la alerta (motivo
    «el transportista fue dado de baja») y la notificación al Vendedor; el paso 50 les busca otro. La cuenta ya está inactiva y bloqueada. Toma los invernaderos de esas entregas (en
    orden de id) y después las entregas (docs/patrones/bloqueos.md). Devuelve un `Efecto` con las entregas y las alertas, y `datos.entregas_sin_transportista` y `alertas_creadas`."""
    if cuenta.rol != TRANSPORTISTA:
        return Efecto([], {})
    ids = list(Entrega.objects.filter(transportista_id=cuenta.pk, estado_orden=A_REALIZAR).values_list("pk", flat=True))
    if not ids:
        return Efecto([], {})
    for invernadero_id in sorted(set(Entrega.objects.filter(pk__in=ids).values_list("invernadero_id", flat=True))):
        bloquear_invernadero_para_alertas(invernadero_id)
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=ids).order_by("pk"))
    afectadas, alertas_creadas = [], []
    for entrega in Entrega.objects.filter(pk__in=ids, transportista_id=cuenta.pk, estado_orden=A_REALIZAR).select_related("contrato_entrega__cliente").order_by("pk"):
        Entrega.objects.filter(pk=entrega.pk).update(transportista=None, aviso_atrasada_para=None)
        entrega.transportista, entrega.aviso_atrasada_para = None, None
        contrato = entrega.contrato_entrega
        alerta = _alerta_sin_transportista(entrega, contrato, "el transportista fue dado de baja")
        detalle = f"{contrato.codigo} · {_cliente_de(contrato)} · {entrega.fecha_programada_orden:%d/%m}. Motivo: el transportista fue dado de baja. InfoPonia vuelve a buscar cada día; el Gerente tiene la alerta."
        _avisar_al_vendedor(contrato, f"Entrega sin transportista: {entrega.codigo}", detalle)
        afectadas.append(entrega)
        if alerta is not None:
            alertas_creadas.append(alerta)
    datos = {"entregas_sin_transportista": [referencia(e) for e in afectadas]}
    if alertas_creadas:
        datos["alertas_creadas"] = [referencia(a) for a in alertas_creadas]
    return Efecto([*afectadas, *alertas_creadas], datos)


def enlaces_de_alertas(usuario, alertas_de_entregas):
    """`registrar_enlace_de_alerta` para `comercial_entrega_sin_transportista` (D-62, puntos 2 y 4; extensión 6a): solo el Gerente la recibe; lleva a la lista de entregas con
    `?entrega=<id>` (COM-05b lo cambia a la pantalla de asignación), con el texto «OT-0231 · 26/11 · Pérez SA». Una consulta para toda la lista."""
    alertas_de_entregas = list(alertas_de_entregas)
    if not alertas_de_entregas or rol_de(usuario) != GERENTE:
        return {}
    enlaces = {}
    for vinculo in AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_de_entregas], entrega__isnull=False).select_related("entrega__contrato_entrega__cliente"):
        entrega = vinculo.entrega
        enlaces[vinculo.alerta_id] = Enlace(
            url_de_entregas(entrega=entrega.pk), f"{entrega.codigo} · {entrega.fecha_programada_orden:%d/%m} · {entrega.contrato_entrega.cliente.nombre_visible}"
        )
    return enlaces


# ---- la lista de entregas de Comercial (el paso 2 de COM-ASG-TRP, sin la asignación; docs/casos_de_uso/comercial/entregas.md, «Pantallas») ----

ESTADOS_DE_LA_LISTA = (
    (OrdenTrabajo.Estado.A_REALIZAR, "A realizar"),
    (OrdenTrabajo.Estado.CONCRETADA, "Concretadas"),
    (OrdenTrabajo.Estado.CANCELADA, "Canceladas"),
    ("", "Todos los estados"),
)
TEXTO_DEL_ESTADO = {"a_realizar": "A realizar", "concretada": "Concretada", "cancelada": "Cancelada"}
POR_PAGINA = 50
SIN_TRANSPORTISTA = "_"  # el valor del filtro «Sin transportista»

FilaDeEntrega = namedtuple(
    "FilaDeEntrega",
    "entrega codigo contrato_codigo url_del_contrato cliente destino contenido fecha cuando atrasada peso transportista sin_transportista es_retiro estado estado_texto",
)
ListaDeEntregas = namedtuple("ListaDeEntregas", "pagina filas invernaderos transportistas hay_filtros")


@dataclass(frozen=True)
class FiltrosDeEntregas:
    """Los filtros de la lista, tomados de la URL: `estado` («A realizar» por omisión; vacío = todos; con `?entrega=` no se filtra por estado salvo que se pida), `invernadero_id`,
    `transportista` (un id o «_» para «Sin transportista») y `entrega_id` (el enlace de la alerta). `pagina` es la que se pidió."""

    estado: str = "a_realizar"
    invernadero_id: str = ""
    transportista: str = ""
    entrega_id: str = ""
    pagina: str = "1"

    @classmethod
    def desde_get(cls, get):
        """Arma los filtros desde `request.GET`; un valor mal formado se ignora (como un filtro vacío)."""
        entrega_id = get.get("entrega", "").strip()
        estado = get.get("estado")
        if estado is None:
            estado = "" if entrega_id.isdigit() else "a_realizar"
        elif estado not in TEXTO_DEL_ESTADO:
            estado = ""
        invernadero = get.get("invernadero", "").strip()
        transportista = get.get("transportista", "").strip()
        return cls(
            estado=estado,
            invernadero_id=invernadero if invernadero.isdigit() else "",
            transportista=transportista if transportista == SIN_TRANSPORTISTA or transportista.isdigit() else "",
            entrega_id=entrega_id if entrega_id.isdigit() else "",
            pagina=get.get("pagina", "1"),
        )

    @property
    def con_filtros(self):
        """True si hay algún filtro distinto del de omisión (para el texto de la lista vacía)."""
        return bool(self.invernadero_id or self.transportista or self.entrega_id or self.estado != "a_realizar")


def _cuando(fecha, hoy, a_realizar):
    """«hoy», «mañana», «en 3 días» o, atrasada, «Atrasada · hace 2 días» (MD-139)."""
    dias = (fecha - hoy).days
    if a_realizar and dias < 0:
        return f"Atrasada · hace {-dias} {'día' if dias == -1 else 'días'}"
    if dias == 0:
        return "hoy"
    if dias == 1:
        return "mañana"
    if dias == -1:
        return "ayer"
    return f"en {dias} días" if dias > 0 else f"hace {-dias} días"


def _destino_de_la_fila(entrega):
    """El destino que muestra la lista: la dirección con envío («San Martín 123, Paraná»); con retiro, «Retiro en Invernadero Sur»."""
    if entrega.modalidad_entrega == RETIRO:
        return f"Retiro en {entrega.invernadero}"
    direccion = entrega.direccion_destino
    hija = direccion.concreta()
    return f"{hija.texto()}, {direccion.localidad.nombre_localidad}" if hija is not direccion else str(direccion)


# ---- COM-05a2: las entregas en el panel de control y en las fichas de los contratos (entregas.md, «Pantallas» y «Lo que completa a otras tareas») ----

FilaDeEntregaDeContrato = namedtuple(
    "FilaDeEntregaDeContrato", "codigo invernadero fecha cuando atrasada estado estado_texto transportista es_retiro confirmacion"
)
EntregasDelPanel = namedtuple("EntregasDelPanel", "a_realizar de_hoy sin_transportista proximas")
ProximaEntrega = namedtuple("ProximaEntrega", "codigo cliente fecha cuando atrasada")


def entregas_del_contrato(contrato_id, hoy):
    """Regla 4 de COM-CNS-CVT y regla 7 de COM-CNS-SUM: las entregas de un contrato (todas, en cualquier estado), por fecha programada e id, con el invernadero de origen, la fecha (con
    «Atrasada» si corresponde, MD-139), el estado, el transportista (o «Retiro») y, en un suministro, su confirmación («No confirmada»). Una consulta, sin consultas por entrega. El alcance
    lo garantiza la ficha que la llama."""
    lista = Entrega.objects.filter(contrato_entrega_id=contrato_id).select_related("invernadero", "transportista").order_by("fecha_programada_orden", "pk")
    filas = []
    for e in lista:
        a_realizar = e.estado_orden == A_REALIZAR
        filas.append(
            FilaDeEntregaDeContrato(
                codigo=e.codigo,
                invernadero=str(e.invernadero),
                fecha=e.fecha_programada_orden,
                cuando=_cuando(e.fecha_programada_orden, hoy, a_realizar) if a_realizar else "",
                atrasada=a_realizar and e.fecha_programada_orden < hoy,
                estado=e.estado_orden,
                estado_texto=TEXTO_DEL_ESTADO[e.estado_orden],
                transportista=e.transportista.get_full_name() if e.transportista_id else "",
                es_retiro=e.modalidad_entrega == RETIRO,
                confirmacion=e.get_estado_confirmacion_cliente_display() if e.estado_confirmacion_cliente else "",
            )
        )
    return filas


def entregas_del_panel(actor, hoy):
    """El grupo «Entregas» del panel del Gerente y del Vendedor, dentro de su alcance: las «a realizar» (`a_realizar`), «Entregas de hoy» (`de_hoy`: con fecha programada ≤ hoy, de hoy o
    atrasadas), «Sin transportista» (`sin_transportista`: con envío) y «Próximas entregas» (`proximas`: las 5 primeras por fecha e id). Dos consultas, sin consultas por entrega."""
    del_alcance = Entrega.objects.en_alcance_de(actor).filter(estado_orden=A_REALIZAR)
    cuentas = del_alcance.aggregate(
        total=Count("pk"),
        de_hoy=Count("pk", filter=Q(fecha_programada_orden__lte=hoy)),
        sin_transportista=Count("pk", filter=Q(modalidad_entrega=ENVIO, transportista__isnull=True)),
    )
    proximas = [
        ProximaEntrega(e.codigo, e.contrato_entrega.cliente.nombre_visible, e.fecha_programada_orden, _cuando(e.fecha_programada_orden, hoy, True), e.fecha_programada_orden < hoy)
        for e in del_alcance.select_related("contrato_entrega__cliente").order_by("fecha_programada_orden", "pk")[:5]
    ]
    return EntregasDelPanel(cuentas["total"], cuentas["de_hoy"], cuentas["sin_transportista"], proximas)


def periodos_con_entrega(periodos):
    """Regla 6 de COM-CNS-SUM: de los ``periodos`` (``[(id del detalle de suministro, fecha)]``), el conjunto de los que tienen una línea con cantidad planificada en una entrega «a
    realizar» («Entrega planificada» en el calendario). Dos consultas para todos los períodos de la página."""
    periodos = set(periodos)
    if not periodos:
        return set()
    lineas = list(
        DetalleEntrega.objects.filter(
            entrega__estado_orden=A_REALIZAR,
            detalle_suministro_id__in={d for d, _ in periodos},
            fecha_periodo__in={f for _, f in periodos},
        ).values_list("pk", "detalle_suministro_id", "fecha_periodo")
    )
    planificadas = cantidades_planificadas([pk for pk, _, _ in lineas])
    return {(d, f) for pk, d, f in lineas if (d, f) in periodos and planificadas[pk] > 0}


def lista_de_entregas(actor, filtros, hoy):
    """La pestaña «Entregas» de Comercial: las entregas del alcance de `actor` (el Gerente, todas; el Vendedor, las de sus contratos; cualquier otro, ninguna) con los filtros, primero las
    de envío «a realizar» sin transportista, después por fecha programada y por id, de a 50. Devuelve `ListaDeEntregas(pagina, filas, invernaderos, transportistas, hay_filtros)`.
    Una consulta por tabla para toda la página (nunca una por fila). No audita."""
    del_alcance = Entrega.objects.en_alcance_de(actor)
    consulta = del_alcance
    if filtros.estado:
        consulta = consulta.filter(estado_orden=filtros.estado)
    if filtros.invernadero_id:
        consulta = consulta.filter(invernadero_id=filtros.invernadero_id)
    if filtros.transportista == SIN_TRANSPORTISTA:
        consulta = consulta.filter(modalidad_entrega=ENVIO, transportista__isnull=True)
    elif filtros.transportista:
        consulta = consulta.filter(transportista_id=filtros.transportista)
    if filtros.entrega_id:
        consulta = consulta.filter(pk=filtros.entrega_id)
    sin_transportista_primero = Case(
        When(modalidad_entrega=ENVIO, transportista__isnull=True, estado_orden=A_REALIZAR, then=Value(0)), default=Value(1), output_field=IntegerField()
    )
    consulta = (
        consulta.select_related(
            "contrato_entrega__cliente", "invernadero", "transportista", "direccion_destino__localidad", "direccion_destino__direccionurbana", "direccion_destino__direccionrural"
        )
        .annotate(_sin_transportista=sin_transportista_primero)
        .order_by("_sin_transportista", "fecha_programada_orden", "pk")
    )
    pagina = Paginator(consulta, POR_PAGINA).get_page(filtros.pagina)
    entregas_de_la_pagina = list(pagina.object_list)
    ids = [e.pk for e in entregas_de_la_pagina]
    pesos = peso_de_entregas(ids)
    lineas = list(DetalleEntrega.objects.filter(entrega_id__in=ids).select_related("detalle_venta__variedad__cultivo", "detalle_suministro__variedad__cultivo").order_by("pk"))
    planificadas = cantidades_planificadas([l.pk for l in lineas])
    contenidos = defaultdict(list)
    for linea in lineas:
        if planificadas[linea.pk] > 0:
            contenidos[linea.entrega_id].append(f"{planificadas[linea.pk]} {(linea.detalle_venta or linea.detalle_suministro).variedad}")
    filas = []
    for e in entregas_de_la_pagina:
        contrato = e.contrato_entrega
        de_venta = contrato.tipo_contrato == Contrato.Tipo.COMPRA_VENTA
        a_realizar = e.estado_orden == A_REALIZAR
        filas.append(
            FilaDeEntrega(
                entrega=e,
                codigo=e.codigo,
                contrato_codigo=contrato.codigo,
                url_del_contrato=reverse("comercial:compra_venta" if de_venta else "comercial:suministro", args=[contrato.pk]),
                cliente=contrato.cliente.nombre_visible,
                destino=_destino_de_la_fila(e),
                contenido=", ".join(contenidos[e.pk]),
                fecha=e.fecha_programada_orden,
                cuando=_cuando(e.fecha_programada_orden, hoy, a_realizar),
                atrasada=a_realizar and e.fecha_programada_orden < hoy,
                peso=pesos[e.pk],
                transportista=e.transportista.get_full_name() if e.transportista_id else "",
                sin_transportista=a_realizar and e.modalidad_entrega == ENVIO and e.transportista_id is None,
                es_retiro=e.modalidad_entrega == RETIRO,
                estado=e.estado_orden,
                estado_texto=TEXTO_DEL_ESTADO[e.estado_orden],
            )
        )
    invernaderos = list(del_alcance.values_list("invernadero_id", "invernadero__nombre_invernadero").distinct().order_by("invernadero__nombre_invernadero"))
    ids_de_invernaderos = [i for i, _ in invernaderos]
    transportistas = [
        (a.transportista_id, a.transportista.get_full_name())
        for a in TransportistaInvernadero.objects.filter(invernadero_id__in=ids_de_invernaderos).select_related("transportista").order_by("transportista__last_name", "transportista__first_name", "pk")
    ]
    return ListaDeEntregas(pagina, filas, invernaderos if len(invernaderos) > 1 else [], transportistas, filtros.con_filtros)
