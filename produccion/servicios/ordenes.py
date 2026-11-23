# Servicios de órdenes de trabajo de `produccion` (PRD-01): constantes de tipos, número de orden, lectura y cancelación.
# Este archivo tiene las constantes, el número, la LECTURA (paso 3) y la CANCELACIÓN (paso 7, al final).
# Fuente: docs/api/produccion.md (secciones 1, 2 y 9), D-53 y D-67 punto 1.
#
# Todos los filtros por tipo usan `tipo_orden__in` con una LISTA de tipos permitidos, nunca «todo menos X» (D-67 punto 1): un tipo
# nuevo no aparece en las pantallas de `produccion` hasta que alguien lo agregue a propósito. Se filtra por `tipo_orden` y no por
# `tipo`, que es el discriminador heredado de `OrigenDocumento` (ver el encabezado de `produccion/models.py`).

from collections import namedtuple
from dataclasses import dataclass

from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.models import Insumo, InsumoInvernadero
from inventario.servicios import alertas_de_stock, stock, variedades
from maestros.models import Invernadero
from maestros.servicios import sectores as api_sectores
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import Cosecha, Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra, TransicionEtapa
from produccion.servicios.bloqueos import traducir

Tipo = OrdenTrabajo.Tipo
Estado = OrdenTrabajo.Estado

# D-67 punto 1: las órdenes que muestran las pantallas de `produccion` (lista, cancelables, bandeja). Las listas filtran con
# `tipo_orden__in` sobre esta constante, NUNCA con «todo menos X»: un tipo nuevo no aparece hasta que alguien lo agregue a propósito.
TIPOS_DE_PRODUCCION = (Tipo.SIEMBRA, Tipo.TRANSICION, Tipo.COSECHA)
# Las que acepta `cancelar_orden` (la del Agrónomo). La cosecha se cancela con `comercial.cancelar_cosecha` (D-64).
TIPOS_QUE_CANCELA_PRODUCCION = (Tipo.SIEMBRA, Tipo.TRANSICION)

# Las tablas hijas que tienen Capataz (`ConCapataz`, D-53). PRD-02 suma `TransicionEtapa` y COM-02, `Cosecha` (D-59).
_HIJAS_CON_CAPATAZ = [Siembra, TransicionEtapa, Cosecha]
# Lo que cada hija trae cargado para armar sus filas sin consultas por fila: la variedad de una siembra y, en una transición, la
# del lote (su variedad sale de `lote.siembra`) y la etapa destino.
_RELACIONES = {
    Siembra: ("variedad__cultivo",),
    TransicionEtapa: ("lote__siembra__variedad__cultivo", "etapa_destino__tipo_etapa"),
    Cosecha: ("variedad__cultivo",),
}

# Una orden tal como la muestran la lista, la bandeja y los avisos: ya con todo lo que necesitan (sin consultas por fila).
FilaDeOrden = namedtuple(
    "FilaDeOrden",
    "orden_id numero codigo tipo_orden tipo_texto estado_orden fecha_programada_orden prioridad_orden "
    "invernadero_id invernadero capataz_id resumen",
)
# La bandeja del Capataz: «vencidas», «hoy» y «próximas», cada una ya ordenada.
Bandeja = namedtuple("Bandeja", "vencidas hoy proximas")
# Un grupo de «Cancelar orden»: las órdenes «a realizar» de un invernadero y un tipo.
GrupoDeOrdenes = namedtuple("GrupoDeOrdenes", "invernadero_id invernadero tipo_orden tipo_texto ordenes")


@dataclass(frozen=True)
class FiltrosDeOrdenes:
    """Filtros de la lista de órdenes; `None` o vacío = sin filtrar (el «Todos los tipos» de la pantalla es `tipo=""`)."""

    invernadero_id: int | None = None
    tipo: str | None = None
    estado: str | None = None


def siguiente_numero():
    """El número de la próxima orden, de la secuencia `produccion_orden_numero_seq` (D-52 punto 3). Puede haber huecos si una
    transacción se deshace. Dos llamadas seguidas dan números distintos y crecientes."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('produccion_orden_numero_seq')")
        return cursor.fetchone()[0]


# ---- Lectura ----


def _rango_de_prioridad(prioridad):
    """Alta, media y baja; sin prioridad cuenta como media (MD-73)."""
    return {"alta": 0, "media": 1, "baja": 2}.get(prioridad, 1)


def _clave_de_bandeja(fila):
    """Orden de la bandeja y de las «a realizar»: fecha programada, después prioridad, después id (docs/modelo/produccion.md)."""
    return (fila.fecha_programada_orden, _rango_de_prioridad(fila.prioridad_orden), fila.orden_id)


def _resumen_de(hija):
    """El texto corto de lo que hace la orden («Lechuga Crespa · 50 plantines»); vacío si su hija no se conoce."""
    if isinstance(hija, Siembra):
        return f"{hija.variedad} · {hija.cant_plantines_siembra} plantines"
    if isinstance(hija, TransicionEtapa):
        return f"{hija.lote.codigo} · {hija.lote.siembra.variedad} → {hija.etapa_destino.tipo_etapa.nombre_etapa}"
    if isinstance(hija, Cosecha):
        return f"{hija.variedad} · cosecha"
    return ""


def _fila(orden, hija=None, capataz_id=None):
    """Arma la fila de una orden con su invernadero ya cargado (`select_related`) y, si se conoce, su hija para el resumen."""
    return FilaDeOrden(
        orden_id=orden.pk,
        numero=orden.numero,
        codigo=orden.codigo,
        tipo_orden=orden.tipo_orden,
        tipo_texto=Tipo(orden.tipo_orden).label,
        estado_orden=orden.estado_orden,
        fecha_programada_orden=orden.fecha_programada_orden,
        prioridad_orden=orden.prioridad_orden,
        invernadero_id=orden.invernadero_id,
        invernadero=orden.invernadero.nombre_invernadero,
        capataz_id=capataz_id,
        resumen=_resumen_de(hija),
    )


def _filas_de_ordenes(ordenes):
    """Filas de una lista de `OrdenTrabajo` (con `invernadero` cargado): una consulta por tabla hija para los resúmenes."""
    ordenes = list(ordenes)
    ids = [orden.pk for orden in ordenes]
    hijas = {}
    for clase in _HIJAS_CON_CAPATAZ:
        if ids:
            hijas.update({h.pk: h for h in clase.objects.filter(pk__in=ids).select_related(*_RELACIONES[clase])})
    return [_fila(orden, hijas.get(orden.pk), getattr(hijas.get(orden.pk), "capataz_id", None)) for orden in ordenes]


def _ordenes_del_capataz(capataz, estado, solo_invernaderos_activos, sin_cosechas=False):
    """La unión de las hijas con Capataz, filtrada por `TIPOS_DE_PRODUCCION`; una consulta por tabla hija. Con `sin_cosechas` (la bandeja),
    no consulta la tabla de cosechas: hasta COM-04a la bandeja no las muestra."""
    filas = []
    for clase in _HIJAS_CON_CAPATAZ:
        if sin_cosechas and clase is Cosecha:  # hasta COM-04a
            continue
        consulta = clase.objects.filter(capataz_id=capataz.pk, tipo_orden__in=list(TIPOS_DE_PRODUCCION))
        if estado:
            consulta = consulta.filter(estado_orden=estado)
        if solo_invernaderos_activos:
            consulta = consulta.filter(invernadero__estado_invernadero=Invernadero.Estado.ACTIVO)
        for hija in consulta.select_related("invernadero", *_RELACIONES[clase]):
            filas.append(_fila(hija, hija, hija.capataz_id))
    return sorted(filas, key=_clave_de_bandeja)


def ordenes_del_capataz(capataz, *, estado=None):
    """LA única unión de las órdenes de un Capataz (D-53): la usan la bandeja, el traspaso y el aviso de baja de cuenta; nadie más
    la arma. Recorre las hijas con Capataz, solo de los tipos de `TIPOS_DE_PRODUCCION`, con `estado` si se pide, ordenadas como la
    bandeja. Una consulta por tabla hija: sin consultas por fila."""
    return _ordenes_del_capataz(capataz, estado, solo_invernaderos_activos=False)


def bandeja_del_capataz(capataz):
    """Las órdenes «a realizar» del Capataz en invernaderos activos, ordenadas por fecha programada, prioridad e id, en los grupos
    «vencidas» (antes de hoy), «hoy» y «próximas» (después de hoy)."""
    hoy = timezone.localdate()
    filas = _ordenes_del_capataz(capataz, Estado.A_REALIZAR, solo_invernaderos_activos=True, sin_cosechas=True)  # cosechas: hasta COM-04a
    return Bandeja(
        vencidas=[f for f in filas if f.fecha_programada_orden < hoy],
        hoy=[f for f in filas if f.fecha_programada_orden == hoy],
        proximas=[f for f in filas if f.fecha_programada_orden > hoy],
    )


def lista_de_ordenes(actor, filtros):
    """Las órdenes visibles para `actor` (el Agrónomo, de sus invernaderos; el Gerente, de todos, en solo lectura; cualquier otro,
    ninguna), solo de los tipos de `TIPOS_DE_PRODUCCION`. Las «a realizar» van primero, en el orden de la bandeja; el resto, de la
    más reciente a la más antigua."""
    ordenes = OrdenTrabajo.objects.filter(
        invernadero__in=Invernadero.objects.en_alcance_de(actor), tipo_orden__in=list(TIPOS_DE_PRODUCCION)
    ).exclude(tipo_orden=Tipo.COSECHA)  # hasta COM-04a: la lista del Agrónomo todavía no muestra cosechas
    if filtros.invernadero_id:
        ordenes = ordenes.filter(invernadero_id=filtros.invernadero_id)
    if filtros.tipo:
        ordenes = ordenes.filter(tipo_orden=filtros.tipo)
    if filtros.estado:
        ordenes = ordenes.filter(estado_orden=filtros.estado)
    filas = _filas_de_ordenes(ordenes.select_related("invernadero"))
    pendientes = sorted((f for f in filas if f.estado_orden == Estado.A_REALIZAR), key=_clave_de_bandeja)
    historial = sorted((f for f in filas if f.estado_orden != Estado.A_REALIZAR), key=lambda f: (f.fecha_programada_orden, f.orden_id), reverse=True)
    return pendientes + historial


def ordenes_cancelables(actor):
    """Las órdenes «a realizar» de los invernaderos del Agrónomo `actor`, agrupadas por invernadero y tipo. Solo de los tipos que
    muestra `produccion` Y que `cancelar_orden` acepta (`TIPOS_DE_PRODUCCION` y `TIPOS_QUE_CANCELA_PRODUCCION`): una cosecha se
    cancela desde `comercial`. El Gerente no cancela: para él no hay nada."""
    if actor is None or not getattr(actor, "is_active", False) or rol_de(actor) != Usuario.Rol.AGRONOMO:
        return []
    tipos = [t for t in TIPOS_DE_PRODUCCION if t in TIPOS_QUE_CANCELA_PRODUCCION]
    ordenes = OrdenTrabajo.objects.filter(
        invernadero__in=Invernadero.objects.en_alcance_de(actor), tipo_orden__in=tipos, estado_orden=Estado.A_REALIZAR
    ).select_related("invernadero")
    grupos = {}
    for fila in sorted(_filas_de_ordenes(ordenes), key=_clave_de_bandeja):
        clave = (fila.invernadero, fila.invernadero_id, fila.tipo_orden)
        grupos.setdefault(clave, []).append(fila)
    return [
        GrupoDeOrdenes(invernadero_id, nombre, tipo, Tipo(tipo).label, filas)
        for (nombre, invernadero_id, tipo), filas in sorted(grupos.items())
    ]


# ---- PROD-CNL-ORD · Cancelar Orden (paso 7) ----
# - `resumen_de_cancelacion`: el detalle del paso 4 y el resumen del paso 6 (lo que libera). No escribe ni bloquea.
# - `cancelar_orden`: la cancelación del Agrónomo; SOLO `TIPOS_QUE_CANCELA_PRODUCCION` (D-67 punto 1): con otro tipo rechaza con
#   `orden_no_cancelable` ANTES de bloquear nada. Bloquea (cuentas → invernadero → variedad → sectores → insumos → la orden y sus reservas),
#   vuelve a verificar (extensiones 8a y 8b) y cancela, avisa al Capataz y escribe UN registro `cancelacion_orden`.
# - `cancelar_orden_incluida`: para un caso de uso que incluye la cancelación. Corre en la transacción de su llamador (que ya tiene
#   bloqueados invernadero, variedad y sectores), acepta CUALQUIER tipo, no audita ni notifica: devuelve lo que el llamador necesita.

# Las tablas de ocupaciones solo existen para estos tipos: una entrega o un mantenimiento no consultan ocupaciones (punto 3 de «Tipos futuros»).
TIPOS_CON_SECTORES = (Tipo.SIEMBRA, Tipo.TRANSICION)
LARGO_DEL_MOTIVO = 300
LARGO_DEL_AVISO = 500

CancelacionIncluida = namedtuple("CancelacionIncluida", "orden reservas sectores_afectados alertas_resueltas notificar_a")
# Un sector cuyos agujeros comprometidos bajan con la cancelación: `antes` y `despues` son los comprometidos.
SectorAfectado = namedtuple("SectorAfectado", "sector antes despues")
ReservaQueSeLibera = namedtuple("ReservaQueSeLibera", "nombre cantidad unidad")
# `lote`, `etapa_origen` y `etapa_destino` (nombres) solo en una transición (extensión 4a); `None` en una siembra.
ResumenDeCancelacion = namedtuple("ResumenDeCancelacion", "orden reservas sectores lote etapa_origen etapa_destino")


def _error(codigo, mensaje, campo=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo)


def _orden_del_agronomo(actor, orden_id):
    """Permiso y tipo de PROD-CNL-ORD, SIN bloquear: `actor` es un Agrónomo activo a cargo del invernadero de la orden (regla 2 de 8.22,
    aunque la haya planificado InfoPonia) y la orden es de un tipo que cancela `produccion` (`orden_no_cancelable`). Devuelve la orden."""
    if (
        actor is None
        or rol_de(actor) != Usuario.Rol.AGRONOMO
        or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise _error("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")
    orden = OrdenTrabajo.objects.select_related("invernadero").filter(pk=orden_id).first()
    if orden is None:
        raise Http404("No existe esa orden.")
    if orden.invernadero.agronomo_id != actor.pk:
        raise _error("sin_permiso", "Esa orden no es de un invernadero a tu cargo.")
    if orden.tipo_orden not in TIPOS_QUE_CANCELA_PRODUCCION:
        raise _error(
            "orden_no_cancelable",
            f"Las órdenes de «{Tipo(orden.tipo_orden).label}» no se cancelan desde acá: se cancelan desde su propia pantalla.",
        )
    return orden


def _exigir_a_realizar(orden):
    """Extensión 8a: la orden sigue «a realizar»; si no, `orden_no_pendiente` con su estado actual."""
    if orden.estado_orden != Estado.A_REALIZAR:
        raise _error(
            "orden_no_pendiente",
            f"La orden {orden.codigo} ya no está «a realizar»: su estado actual es «{Estado(orden.estado_orden).label}».",
        )


def _motivo_valido(motivo):
    """Paso 5 y extensión 6a: el motivo es obligatorio (sin espacios al borde) y tiene hasta 300 caracteres."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise _error("motivo_obligatorio", "Indicá el motivo de la cancelación.", "motivo")
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise _error("motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.", "motivo")
    return motivo


def _hija_con_capataz(orden):
    """La hija de `orden` que tiene Capataz (D-53), con su Capataz cargado; `None` si su tipo no tiene (entrega, mantenimiento) o no es
    una de las que `produccion` conoce. Solo consulta para los tipos que pueden tenerlo."""
    if orden.tipo_orden not in TIPOS_DE_PRODUCCION:
        return None
    for clase in _HIJAS_CON_CAPATAZ:
        hija = clase.objects.select_related("capataz").filter(pk=orden.pk).first()
        if hija is not None:
            return hija
    return None


def resumen_de_cancelacion(actor, orden_id):
    """Pasos 4 y 6 de PROD-CNL-ORD: la orden y lo que libera su cancelación: las reservas de insumo activas (insumo y cantidad) y los
    sectores con los agujeros comprometidos que se liberan. Valida permiso, tipo y estado como `cancelar_orden`. No escribe ni bloquea."""
    orden = _orden_del_agronomo(actor, orden_id)
    _exigir_a_realizar(orden)
    reservas = ReservaInsumo.objects.filter(orden=orden, estado=ReservaInsumo.Estado.ACTIVA).select_related("insumo_invernadero__insumo").order_by("pk")
    sectores = (
        OcupacionSector.objects.filter(orden=orden).select_related("sector").order_by("pk") if orden.tipo_orden in TIPOS_CON_SECTORES else []
    )
    lote = etapa_origen = etapa_destino = None
    if orden.tipo_orden == Tipo.TRANSICION:  # extensión 4a: el lote, su etapa actual y la etapa destino
        transicion = TransicionEtapa.objects.select_related("lote__etapa__tipo_etapa", "etapa_destino__tipo_etapa").get(pk=orden.pk)
        lote = transicion.lote
        etapa_origen, etapa_destino = lote.etapa.tipo_etapa.nombre_etapa, transicion.etapa_destino.tipo_etapa.nombre_etapa
    return ResumenDeCancelacion(
        orden,
        [ReservaQueSeLibera(r.insumo_invernadero.insumo.nombre_insumo, r.cantidad_reservada, r.insumo_invernadero.insumo.unidad_medida_insumo) for r in reservas],
        [(o.sector, o.cant_agujeros_planificados) for o in sectores],
        lote,
        etapa_origen,
        etapa_destino,
    )


def _acortar(texto, exceso):
    """`texto` sin `exceso` caracteres, terminado en «…»."""
    nuevo_largo = max(1, len(texto) - exceso)
    return texto if nuevo_largo >= len(texto) else texto[: nuevo_largo - 1] + "…"


def texto_de_cancelacion(orden, motivo, actor):
    """`(título, detalle)` del aviso al Capataz (docs/casos_de_uso/produccion/cancelar_orden.md, «Notificación»): «Orden OT-0007 cancelada» y
    «Motivo: <motivo>. <Siembra> del dd/mm/aaaa en <invernadero>, cancelada por <nombre>.». Si el detalle pasa de 500, se acorta con «…»
    primero el nombre de quien cancela y después el del invernadero: el motivo no se recorta nunca. Lo usa también la cancelación de una
    cosecha (COM-04a)."""
    cabeza = f"Motivo: {motivo}. {Tipo(orden.tipo_orden).label} del {orden.fecha_programada_orden:%d/%m/%Y} en "
    invernadero, nombre = orden.invernadero.nombre_invernadero, (actor.get_full_name() or actor.email) if actor else "InfoPonia"

    def armar():
        return f"{cabeza}{invernadero}, cancelada por {nombre}."

    if len(armar()) > LARGO_DEL_AVISO:
        nombre = _acortar(nombre, len(armar()) - LARGO_DEL_AVISO)
    if len(armar()) > LARGO_DEL_AVISO:
        invernadero = _acortar(invernadero, len(armar()) - LARGO_DEL_AVISO)
    return f"Orden {orden.codigo} cancelada", armar()


def marcar_cancelada(orden, motivo):
    """Lo común de cancelar cualquier orden: pasa a «cancelada» con la fecha de hoy y el motivo (ya validado, hasta 300). Devuelve la
    orden. La usa `cancelar_orden` y la reutilizará la cancelación de una cosecha (COM-04a)."""
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        estado_orden=Estado.CANCELADA, fecha_resolucion_orden=stock.hoy(), motivo_cancelacion=motivo
    )
    orden.estado_orden, orden.fecha_resolucion_orden, orden.motivo_cancelacion = Estado.CANCELADA, stock.hoy(), motivo
    return orden


def _foto_de_las_reservas(orden):
    """Lo que cuenta de las reservas para detectar que cambiaron entre leer y bloquear (extensión 8b)."""
    return [(r.pk, r.cantidad_reservada, r.estado) for r in ReservaInsumo.objects.filter(orden_id=orden.pk).order_by("pk")]


def _cancelar_en_transaccion(orden, motivo, *, avisar, foto=None):
    """Lo que sigue en el orden de bloqueos a invernadero, variedad y sectores (que el llamador ya tiene): los insumos de las reservas
    (`Insumo` y `InsumoInvernadero`, en orden de id), la orden y sus reservas. Relee, verifica que la orden siga «a realizar» (8a) y que
    las reservas no hayan cambiado (8b, si hay `foto`), y cancela. Devuelve la `CancelacionIncluida`. No audita ni notifica."""
    hoy = stock.hoy()
    existencias_ids = sorted({i for i in ReservaInsumo.objects.filter(orden_id=orden.pk).values_list("insumo_invernadero_id", flat=True)})
    existencias = list(InsumoInvernadero.objects.select_for_update(no_key=True).filter(pk__in=existencias_ids).order_by("pk"))
    list(Insumo.objects.select_for_update(no_key=True).filter(pk__in={e.insumo_id for e in existencias}).order_by("pk"))
    if orden.tipo_orden == Tipo.TRANSICION:  # nivel 4 de bloqueos.md: el lote, antes que la orden (quien llama ya tiene los sectores)
        lote_id = TransicionEtapa.objects.filter(pk=orden.pk).values_list("lote_id", flat=True).first()
        Lote.objects.select_for_update(no_key=True).filter(pk=lote_id).first()
    fila = OrdenTrabajo.objects.select_for_update(no_key=True).filter(pk=orden.pk).first()
    if fila is None:
        raise Http404("No existe esa orden.")
    _exigir_a_realizar(fila)
    reservas = list(ReservaInsumo.objects.select_for_update(no_key=True).filter(orden_id=orden.pk).order_by("pk"))
    if foto is not None and [(r.pk, r.cantidad_reservada, r.estado) for r in reservas] != foto:
        raise _error("cambio_simultaneo", "Mientras cancelabas, cambiaron las reservas de la orden. Volvé a abrir la cancelación.")
    activas = [r for r in reservas if r.estado == ReservaInsumo.Estado.ACTIVA]
    ocupaciones = (
        list(OcupacionSector.objects.filter(orden_id=orden.pk).select_related("sector").order_by("pk"))
        if orden.tipo_orden in TIPOS_CON_SECTORES
        else []
    )
    sectores = [o.sector for o in ocupaciones]
    antes = api_sectores.agujeros_de(sectores) if sectores else {}
    marcar_cancelada(orden, motivo)
    if activas:
        ReservaInsumo.objects.filter(pk__in=[r.pk for r in activas]).update(
            estado=ReservaInsumo.Estado.CANCELADA, cantidad_utilizada=None, cantidad_devuelta=None
        )
        for reserva in activas:
            reserva.estado, reserva.cantidad_utilizada, reserva.cantidad_devuelta = ReservaInsumo.Estado.CANCELADA, None, None
    despues = api_sectores.agujeros_de(sectores) if sectores else {}
    resueltas = []
    for existencia_id in sorted({r.insumo_invernadero_id for r in activas}):
        resueltas += alertas_de_stock.reevaluar_alertas_del_insumo(existencia_id).resueltas
    notificar_a = []
    if avisar:
        hija = _hija_con_capataz(orden)
        if hija is not None and hija.capataz.is_active:
            notificar_a = [hija.capataz]
    return CancelacionIncluida(
        orden,
        activas,
        [SectorAfectado(s, antes[s.pk].comprometidos, despues[s.pk].comprometidos) for s in sectores],
        resueltas,
        notificar_a,
    )


def cancelar_orden_incluida(actor, orden, motivo, *, avisar=False):
    """PROD-CNL-ORD como parte de otro caso de uso (PRD-04: sector fuera de servicio; COM-05a1: la entrega; IOT-07: el mantenimiento).

    - Corre en la transacción de su llamador, que ya tiene bloqueados el invernadero, la variedad y los sectores en el orden de
      `docs/patrones/bloqueos.md`: acá se toma lo que sigue (insumos de las reservas, orden y reservas). NO abre una transacción propia, NO
      audita y NO notifica: devuelve lo que el llamador pone en su único registro (D-36) y a quién avisar.
    - `actor` es quien actúa en el caso de uso que incluye, o `None` si actúa InfoPonia (no cambia lo que hace esta función).
    - Acepta CUALQUIER tipo de orden (D-67 punto 1): no da por hecho que tenga Capataz (si no lo tiene, `notificar_a` queda vacío aunque
      `avisar=True`) ni sectores (`sectores_afectados` vacío, sin consultar ocupaciones) y funciona con o sin reservas de insumo.
    - Cancela solo órdenes «a realizar»: si ya no lo está, `orden_no_pendiente`.
    - El motivo ya viene armado; si pasa de 300, se recorta con «…» (el «…» cuenta dentro de los 300) y no lanza `motivo_largo`.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise _error("motivo_obligatorio", "Indicá el motivo de la cancelación.", "motivo")
    if len(motivo) > LARGO_DEL_MOTIVO:
        motivo = motivo[: LARGO_DEL_MOTIVO - 1] + "…"
    return _cancelar_en_transaccion(orden, motivo, avisar=avisar)


def cancelar_orden(actor, orden_id, motivo):
    """PROD-CNL-ORD: cancela una orden de siembra (o de transición, desde PRD-02) y la devuelve.

    - Precondición a y regla 2 de 8.22: Agrónomo activo a cargo del invernadero (`sin_permiso`). Solo `TIPOS_QUE_CANCELA_PRODUCCION`: con
      otro tipo, `orden_no_cancelable` ANTES de bloquear nada y sin cambiar la orden (una cosecha se cancela con `comercial.cancelar_cosecha`).
    - Extensiones 6a y 8a y 8b: motivo obligatorio (`motivo_obligatorio`, `motivo_largo`); la orden sigue «a realizar» (`orden_no_pendiente`);
      las reservas no cambiaron entre leer y bloquear (`cambio_simultaneo`).
    - Postcondiciones a a d: orden «cancelada» con la fecha de hoy y el motivo; reservas activas «canceladas» sin cantidades; alertas
      «stock inconsistente» cubiertas, resueltas; ocupaciones conservadas (lo planificado deja de comprometer). Sin consumos ni movimientos.
    - Postcondición k: aviso al Capataz con el motivo entero, dentro de la transacción (D-42); sin Capataz activo no avisa (9a).
    - Postcondiciones m y n y D-36: UN registro `cancelacion_orden`.
    - Bloqueos (`FOR NO KEY UPDATE`): cuentas del Agrónomo y del Capataz (orden de id) → invernadero → variedad → sectores → insumos → la
      orden y sus reservas. Todo o nada (D-22).
    - Una transición suma, en su lugar de la jerarquía, la variedad del lote (2b) y el lote (4, antes que la orden), sin reservas de insumo.
    """
    orden = _orden_del_agronomo(actor, orden_id)
    motivo = _motivo_valido(motivo)
    _exigir_a_realizar(orden)
    hija = _hija_con_capataz(orden)
    foto = _foto_de_las_reservas(orden)
    sector_ids = list(OcupacionSector.objects.filter(orden=orden).values_list("sector_id", flat=True)) if orden.tipo_orden in TIPOS_CON_SECTORES else []
    # Siembra: su variedad; transición: la del lote (nivel 2b de bloqueos.md).
    variedad_id = hija.lote.siembra.variedad_id if isinstance(hija, TransicionEtapa) else getattr(hija, "variedad_id", None)
    with transaction.atomic():
        cuentas = {actor.pk, *([hija.capataz_id] if hija is not None else [])}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        traducir(bloquear_invernadero_activo, orden.invernadero_id, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)})
        if variedad_id is not None:
            traducir(variedades.bloquear_variedad, variedad_id)
        if sector_ids:
            traducir(api_sectores.bloquear_sectores, orden.invernadero_id, sector_ids)
        resultado = _cancelar_en_transaccion(orden, motivo, avisar=True, foto=foto)
        if resultado.notificar_a:
            titulo, detalle = texto_de_cancelacion(orden, motivo, actor)
            notificaciones.notificar_a_varios(resultado.notificar_a, titulo, detalle, excluir=actor)
        cambios = {
            "estado": {"antes": Estado.A_REALIZAR.value, "despues": Estado.CANCELADA.value},
            "fecha_resolucion_orden": {"antes": None, "despues": f"{stock.hoy():%d/%m/%Y}"},
            "motivo_cancelacion": {"antes": None, "despues": motivo},
        }
        if resultado.sectores_afectados:
            cambios["agujeros_comprometidos"] = {
                "antes": [f"{a.sector.nombre_sector}: {a.antes}" for a in resultado.sectores_afectados],
                "despues": [f"{a.sector.nombre_sector}: {a.despues}" for a in resultado.sectores_afectados],
            }
        detalle_de_auditoria = {"cambios": cambios}
        if resultado.alertas_resueltas:
            detalle_de_auditoria["datos"] = {"alertas_resueltas": [referencia(a) for a in resultado.alertas_resueltas]}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.CANCELACION_ORDEN,
            afectados=[hija or orden, *resultado.reservas, *[a.sector for a in resultado.sectores_afectados], *resultado.alertas_resueltas],
            detalle=detalle_de_auditoria,
        )
    return resultado.orden


# ---- Detalle de una orden (ventana de `MODALS.orden` del prototipo; PRD-01, paso 8) ----

DetalleDeOrden = namedtuple("DetalleDeOrden", "orden hija invernadero reservas ocupaciones puede_cancelar puede_concretar")


def detalle_de_orden(actor, orden_id):
    """La orden con sus reservas y sus ocupaciones, para su ventana de detalle. Solo de los tipos de `TIPOS_DE_PRODUCCION`. La ven el
    Gerente (solo lectura) y el Agrónomo a cargo de su invernadero, y el Capataz asignado; para cualquier otra cuenta, o una orden de
    otro tipo, `Http404` (no se revela que existe). Trae además qué puede hacer `actor`: cancelar (el Agrónomo a cargo, si la orden
    es de las que cancela `produccion` y está «a realizar») o concretar (el Capataz asignado a una siembra «a realizar»)."""
    orden = (
        OrdenTrabajo.objects.select_related("invernadero")
        .filter(pk=orden_id, tipo_orden__in=list(TIPOS_DE_PRODUCCION))
        .exclude(tipo_orden=Tipo.COSECHA)  # hasta COM-04a: su ventana de detalle todavía no existe
        .first()
    )
    if orden is None or actor is None or not getattr(actor, "is_active", False):
        raise Http404("No existe esa orden.")
    hija = None
    for clase in _HIJAS_CON_CAPATAZ:
        hija = clase.objects.select_related("capataz", "agronomo", *_RELACIONES[clase]).filter(pk=orden.pk).first()
        if hija is not None:
            break
    rol = rol_de(actor)
    es_su_capataz = rol == Usuario.Rol.CAPATAZ and hija is not None and hija.capataz_id == actor.pk
    en_alcance = rol in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO) and Invernadero.objects.en_alcance_de(actor).filter(pk=orden.invernadero_id).exists()
    if not (es_su_capataz or en_alcance):
        raise Http404("No existe esa orden.")
    a_realizar = orden.estado_orden == Estado.A_REALIZAR
    return DetalleDeOrden(
        orden,
        hija,
        orden.invernadero,
        list(ReservaInsumo.objects.filter(orden=orden).select_related("insumo_invernadero__insumo").order_by("pk")),
        list(OcupacionSector.objects.filter(orden=orden).select_related("sector").order_by("pk")) if orden.tipo_orden in TIPOS_CON_SECTORES else [],
        puede_cancelar=a_realizar and rol == Usuario.Rol.AGRONOMO and orden.tipo_orden in TIPOS_QUE_CANCELA_PRODUCCION,
        puede_concretar=a_realizar and es_su_capataz and orden.tipo_orden in TIPOS_QUE_CANCELA_PRODUCCION,  # siembra y transición
    )
