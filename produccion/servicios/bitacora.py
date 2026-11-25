# Bitácora de `produccion` (PRD-03): Registrar Evento (PROD-REG-EVT) y, más abajo, Consultar Bitácora (PROD-CNS-BIT). Un evento es un hecho de un
# invernadero que no es una merma, una aplicación de insumos ni una operación que el Sistema ya registra. Un registro de bitácora NO se modifica ni se
# elimina (regla 5): este módulo no tiene ninguna función que lo haga. Las vistas solo orquestan: las reglas están acá.
# Fuente: docs/casos_de_uso/produccion/bitacora.md («PROD-REG-EVT» y «Cómo se aplica en la ronda «Producción 1»»), docs/patrones/bloqueos.md
# (sección `produccion`, «Lote 5»: cuentas → invernadero → sector → lote) y D-51 punto 2 (un evento tiene a lo sumo un sector).

from collections import namedtuple
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Prefetch
from django.db.models.functions import Lower
from django.http import Http404
from django.utils import timezone

from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.unidades import Unidad
from maestros.models import Invernadero, SectorProduccion
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Consumo, Lote
from produccion.servicios import alcance
from produccion.servicios.bloqueos import traducir as _bloquear

LARGO_DE_LA_DESCRIPCION = 500

# Lo que presenta la pantalla «Otro evento». `lotes` es `[(lote_id, codigo, variedad)]`; `sectores`, `[(sector_id, nombre)]`.
PropuestaDeEvento = namedtuple("PropuestaDeEvento", "invernaderos invernadero lotes sectores")
# Todo lo que `_planear` resuelve y que `registrar_evento` usa para escribir.
PlanDeEvento = namedtuple("PlanDeEvento", "invernadero descripcion lote sector")


@dataclass(frozen=True)
class DatosDeEvento:
    """Lo que la persona carga: el invernadero, la descripción (obligatoria, hasta 500) y, opcionales, un lote activo y un sector que no esté
    inactivo. No hay fecha ni hora: son las del registro (regla 4)."""

    invernadero_id: int
    descripcion: str = ""
    lote_id: int | None = None
    sector_id: int | None = None


def _error(codigo, mensaje, campo=None):
    """Un `ErrorDeProduccion` (docs/api/produccion.md, sección 1)."""
    return ErrorDeProduccion(codigo, mensaje, campo)


def datos_de_evento(actor, invernadero_id=None):
    """Regla 1 y paso de elegir: los invernaderos activos del actor, el invernadero elegido (el pedido, o el único si hay uno solo, o `None`) y, con
    uno elegido, sus lotes ACTIVOS y sus sectores que no están inactivos (también los fuera de servicio, regla 3). No escribe ni bloquea."""
    alcance.exigir_actor(actor)
    invernaderos = alcance.invernaderos_del_actor(actor)
    if invernadero_id is not None:
        elegido = alcance.invernadero_del_actor(actor, invernadero_id)
    else:
        elegido = invernaderos[0] if len(invernaderos) == 1 else None
    if elegido is None:
        return PropuestaDeEvento(invernaderos, None, [], [])
    lotes = Lote.objects.filter(invernadero=elegido, estado_lote=Lote.Estado.ACTIVO).select_related("siembra__variedad__cultivo").order_by("pk")
    sectores = (
        SectorProduccion.objects.filter(invernadero=elegido).exclude(estado_sector=SectorProduccion.Estado.INACTIVO).order_by("nombre_sector", "pk")
    )
    return PropuestaDeEvento(
        invernaderos,
        elegido,
        [(l.pk, l.codigo, str(l.siembra.variedad)) for l in lotes],
        [(s.pk, s.nombre_sector) for s in sectores],
    )


def _planear(actor, datos):
    """Las reglas 1 a 3 con lo que haya en la base en este momento (registrar vuelve a llamarla después de bloquear). No escribe."""
    invernadero = alcance.invernadero_del_actor(actor, datos.invernadero_id)
    descripcion = (datos.descripcion or "").strip()
    if not descripcion:
        raise _error("descripcion_obligatoria", "Describí el evento.", "descripcion")
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_larga", f"La descripción admite hasta {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    sector = None
    if datos.sector_id is not None:
        sector = (
            SectorProduccion.objects.filter(pk=datos.sector_id, invernadero=invernadero)
            .exclude(estado_sector=SectorProduccion.Estado.INACTIVO)
            .first()
        )
        if sector is None:
            raise _error("sector_no_elegible", "Ese sector no es del invernadero o está dado de baja.", "sector")
    lote = None
    if datos.lote_id is not None:
        lote = Lote.objects.filter(pk=datos.lote_id, invernadero=invernadero, estado_lote=Lote.Estado.ACTIVO).first()
        if lote is None:
            raise _error("lote_no_activo", "Ese lote no es un lote activo de este invernadero.", "lote")
    return PlanDeEvento(invernadero, descripcion, lote, sector)


def registrar_evento(actor, datos):
    """PROD-REG-EVT: registra un evento de «otro evento» y devuelve la `Bitacora`.

    - Quién: Agrónomo a cargo o Capataz asignado, con la cuenta activa (`sin_permiso`); invernadero activo (`invernadero_inactivo`).
    - Verificaciones DESPUÉS de bloquear: descripción (`descripcion_obligatoria`, `descripcion_larga`), sector (`sector_no_elegible`) y lote
      (`lote_no_activo`).
    - Postcondición a: tipo «otro evento», fecha y hora actuales, la descripción, el actor como responsable, el invernadero y, si se indicaron, el
      lote y el sector (uno solo); sin etapa. Postcondición b y D-36: UN registro `registro_evento`. Sin alertas ni notificaciones (regla 6).
    - Bloqueos, todos `FOR NO KEY UPDATE`: las cuentas del actor y del Agrónomo → el invernadero → el sector (directo: `bloquear_sectores` rechaza un
      sector fuera de servicio y la regla 3 lo acepta) → el lote.
    """
    alcance.exigir_actor(actor)
    previo = alcance.invernadero_del_actor(actor, datos.invernadero_id)
    with transaction.atomic():
        cuentas = {actor.pk, *([previo.agronomo_id] if previo.agronomo_id else [])}
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        alcance.exigir_actor(actor)  # después de bloquear: pudo darse de baja mientras esperaba
        _bloquear(bloquear_invernadero_activo, previo.pk, equivalencias={"invernadero_inactivo": ("invernadero_inactivo", None)})
        if datos.sector_id is not None:
            list(SectorProduccion.objects.select_for_update(no_key=True).filter(pk=datos.sector_id, invernadero_id=previo.pk))
        if datos.lote_id is not None:
            list(Lote.objects.select_for_update(no_key=True).filter(pk=datos.lote_id, invernadero_id=previo.pk))
        plan = _planear(actor, datos)  # todo de nuevo, con lo bloqueado
        evento = Bitacora.objects.create(
            invernadero=plan.invernadero,
            lote=plan.lote,
            responsable=actor,
            fecha_bitacora=timezone.localdate(),
            hora_bitacora=timezone.localtime().time(),
            tipo_evento=Bitacora.TipoEvento.OTRO_EVENTO,
            descripcion_evento=plan.descripcion,
        )
        if plan.sector is not None:
            evento.sectores.set([plan.sector.pk])
        datos_de_auditoria = {"invernadero": referencia(plan.invernadero)}
        afectados = [evento]
        if plan.lote is not None:
            datos_de_auditoria["lote"] = referencia(plan.lote)
            afectados.append(plan.lote)
        if plan.sector is not None:
            datos_de_auditoria["sectores"] = [referencia(plan.sector)]
            afectados.append(plan.sector)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REGISTRO_EVENTO,
            afectados=afectados,
            detalle={"cambios": {"descripcion_evento": {"antes": None, "despues": plan.descripcion}}, "datos": datos_de_auditoria},
        )
        return evento


TIPOS_DE_CONTRATO = (Bitacora.TipoEvento.INCUMPLIMIENTO_DE_CLAUSULA, Bitacora.TipoEvento.ANULACION_DE_RESOLUCION)


def registrar_evento_de_contrato(invernadero, tipo, descripcion, responsable):
    """Núcleo para COM-07a (COM-04a, D-69 punto 3; docs/api/produccion.md, sección 11): un registro de bitácora del `invernadero` de `tipo`
    `incumplimiento_de_clausula` o `anulacion_de_resolucion` (con otro, `ValueError`), con `descripcion` de 1 a 500 caracteres (sin espacios al
    borde; `ErrorDeProduccion('descripcion_invalida')` si queda vacía o pasa de 500), fecha y hora actuales, el `responsable` (el Gerente) y SIN
    lote, etapa, sectores ni cosecha. No verifica que el invernadero esté activo (un contrato puede tener entregas de uno dado de baja). Corre
    en la transacción de quien llama (sin ella, `RuntimeError`), con el invernadero ya bloqueado; no audita ni notifica."""
    from produccion.servicios import movimientos

    movimientos.exigir_transaccion("registrar_evento_de_contrato")
    if tipo not in TIPOS_DE_CONTRATO:
        raise ValueError(f"`registrar_evento_de_contrato` solo registra {[t.value for t in TIPOS_DE_CONTRATO]}, no «{tipo}».")
    descripcion = (descripcion or "").strip()
    if not 1 <= len(descripcion) <= LARGO_DE_LA_DESCRIPCION:
        raise _error("descripcion_invalida", f"La descripción debe tener entre 1 y {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    return Bitacora.objects.create(
        invernadero=invernadero,
        responsable=responsable,
        fecha_bitacora=timezone.localdate(),
        hora_bitacora=timezone.localtime().time(),
        tipo_evento=tipo,
        descripcion_evento=descripcion,
    )


# ---- PROD-CNS-BIT · Consultar Bitácora ----
# Quién: el Agrónomo (invernaderos a su cargo) y el Gerente (todos), también los dados de baja (regla 2: la baja es lógica y conserva el historial).
# El Capataz no consulta. Una consulta por tabla para toda la página (`select_related` y `prefetch_related`), sin consultas por fila, y sin auditoría
# (regla 9, SEG-14). Cosecha e incumplimiento de cláusula no existen todavía: no se ofrecen en el filtro de tipos (los suman sus rondas).

POR_PAGINA = 50
TIPOS_DE_FILTRO = [
    (t.value, t.label)
    for t in (
        Bitacora.TipoEvento.SIEMBRA,
        Bitacora.TipoEvento.TRANSICION,
        Bitacora.TipoEvento.MERMA,
        Bitacora.TipoEvento.APLICACION,
        Bitacora.TipoEvento.OTRO_EVENTO,
        Bitacora.TipoEvento.FUERA_DE_SERVICIO,  # PRD-04 (docs/disparadores.md, «Cuando exista PROD-PNR-FDS»)
        Bitacora.TipoEvento.REUBICACION,
        Bitacora.TipoEvento.CARGA_INICIAL,  # PRD-05: la carga de un lote existente
        Bitacora.TipoEvento.COSECHA,  # COM-04a (docs/disparadores.md, «Cuando exista `produccion` completa», punto 3)
        Bitacora.TipoEvento.INCUMPLIMIENTO_DE_CLAUSULA,
        Bitacora.TipoEvento.ANULACION_DE_RESOLUCION,
    )
]

DiaDeBitacora = namedtuple("DiaDeBitacora", "fecha registros")
RegistroDeBitacora = namedtuple(
    "RegistroDeBitacora", "id fecha hora tipo tipo_texto lote sectores descripcion responsable consumos"
)
# `lotes` (`[(lote_id, codigo)]`, todos los del invernadero: la bitácora es historia) y `sectores` (`[(sector_id, nombre)]`) son las opciones de los filtros.
PaginaDeBitacora = namedtuple("PaginaDeBitacora", "invernadero dias total pagina paginas hay_filtros lotes sectores")


@dataclass(frozen=True)
class FiltrosDeBitacora:
    """Regla 6: texto en la descripción, tipo, lote, sector y rango de fechas (inclusive). Se combinan; vacío = sin filtro."""

    texto: str = ""
    tipo: str = ""
    lote_id: int | None = None
    sector_id: int | None = None
    desde: date | None = None
    hasta: date | None = None


def _consulta_permitida(actor):
    """Precondiciones a y b: una cuenta activa de Agrónomo o de Gerente; si no, `sin_permiso`."""
    rol = rol_de(actor) if actor is not None else None
    if rol not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE) or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
        raise _error("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")
    return rol


def invernaderos_de_bitacora(actor):
    """Regla 1: los invernaderos cuya bitácora puede consultar `actor`, por nombre: el Agrónomo, los que tiene a su cargo; el Gerente, todos. También los
    dados de baja (regla 2). Cualquier otra cuenta (el Capataz), o una inactiva, ninguno."""
    if actor is None or not getattr(actor, "is_active", False):
        return []
    rol = rol_de(actor)
    if rol == Usuario.Rol.GERENTE:
        consulta = Invernadero.objects.all()
    elif rol == Usuario.Rol.AGRONOMO:
        consulta = Invernadero.objects.filter(agronomo_id=actor.pk)
    else:
        return []
    return list(consulta.order_by(Lower("nombre_invernadero"), "pk"))


def _responsable(registro):
    """Quién lo registró: «Nombre Apellido» (o el correo si no tiene nombre) o «InfoPonia» si lo generó el Sistema (regla 4)."""
    usuario = registro.responsable
    if usuario is None:
        return "InfoPonia"
    return f"{usuario.first_name} {usuario.last_name}".strip() or usuario.email


def _consumos_de(registro):
    """Los consumos de una aplicación como texto «Limpiador: 5 L» (ya traídos con `Prefetch`); vacío para cualquier otro registro."""
    try:
        aplicacion = registro.aplicacioninsumos
    except ObjectDoesNotExist:
        return []
    if aplicacion is None:
        return []
    texto = lambda c: (
        f"{c.insumo_invernadero.insumo.nombre_insumo}: {format(Decimal(c.cant_consumo).normalize(), 'f')} "
        f"{Unidad(c.insumo_invernadero.insumo.unidad_medida_insumo).label}"
    )
    return [texto(c) for c in sorted(aplicacion.consumos.all(), key=lambda c: c.pk)]


def _filtrar(consulta, filtros):
    """Aplica los filtros de la regla 6 combinados. El sector va por subconsulta sobre la tabla de la relación: encuentra el registro si el sector es uno
    de los suyos y no lo duplica."""
    if filtros.tipo and filtros.tipo not in [v for v, _ in TIPOS_DE_FILTRO]:
        raise _error("filtro_invalido", "Ese tipo de evento no existe.", "tipo")
    texto = (filtros.texto or "").strip()
    if texto:
        consulta = consulta.filter(descripcion_evento__icontains=texto)
    if filtros.tipo:
        consulta = consulta.filter(tipo_evento=filtros.tipo)
    if filtros.lote_id:
        consulta = consulta.filter(lote_id=filtros.lote_id)
    if filtros.sector_id:
        con_el_sector = Bitacora.sectores.through.objects.filter(sectorproduccion_id=filtros.sector_id).values("bitacora_id")
        consulta = consulta.filter(pk__in=con_el_sector)
    if filtros.desde:
        consulta = consulta.filter(fecha_bitacora__gte=filtros.desde)
    if filtros.hasta:
        consulta = consulta.filter(fecha_bitacora__lte=filtros.hasta)
    return consulta


def consultar_bitacora(actor, invernadero_id, filtros=None, pagina=1):
    """Reglas 1 a 9: la página `pagina` (de a 50) de la bitácora del invernadero, del más reciente al más antiguo por `(fecha, hora, id)` y agrupada por día,
    con los filtros combinados. No lista el consumo interno de una aplicación (se ve dentro de ella). `pagina` fuera de rango se acota.
    `sin_permiso` si la cuenta no consulta o el invernadero no es del Agrónomo; `Http404` si no existe; `filtro_invalido` si el tipo no se ofrece. No audita."""
    filtros = filtros or FiltrosDeBitacora()
    rol = _consulta_permitida(actor)
    invernadero = Invernadero.objects.filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if rol == Usuario.Rol.AGRONOMO and invernadero.agronomo_id != actor.pk:
        raise _error("sin_permiso", "Ese invernadero no está a tu cargo.")
    consulta = _filtrar(Bitacora.objects.filter(invernadero=invernadero).exclude(tipo_evento=Bitacora.TipoEvento.CONSUMO), filtros)
    total = consulta.count()
    paginas = max(1, -(-total // POR_PAGINA))
    pagina = min(max(int(pagina or 1), 1), paginas)
    filas = (
        consulta.select_related("lote", "responsable")
        .prefetch_related(
            "sectores",
            Prefetch("aplicacioninsumos__consumos", queryset=Consumo.objects.select_related("insumo_invernadero__insumo")),
        )
        .order_by("-fecha_bitacora", "-hora_bitacora", "-pk")[(pagina - 1) * POR_PAGINA : pagina * POR_PAGINA]
    )
    dias = []
    for fila in filas:
        registro = RegistroDeBitacora(
            fila.pk,
            fila.fecha_bitacora,
            fila.hora_bitacora,
            fila.tipo_evento,
            Bitacora.TipoEvento(fila.tipo_evento).label,
            fila.lote.codigo if fila.lote_id else None,
            sorted(s.nombre_sector for s in fila.sectores.all()),
            fila.descripcion_evento,
            _responsable(fila),
            _consumos_de(fila),
        )
        if not dias or dias[-1].fecha != registro.fecha:
            dias.append(DiaDeBitacora(registro.fecha, []))
        dias[-1].registros.append(registro)
    hay_filtros = bool((filtros.texto or "").strip() or filtros.tipo or filtros.lote_id or filtros.sector_id or filtros.desde or filtros.hasta)
    lotes = [(l.pk, l.codigo) for l in Lote.objects.filter(invernadero=invernadero).order_by("pk")]
    sectores = [(s.pk, s.nombre_sector) for s in SectorProduccion.objects.filter(invernadero=invernadero).order_by("nombre_sector", "pk")]
    return PaginaDeBitacora(invernadero, dias, total, pagina, paginas, hay_filtros, lotes, sectores)
