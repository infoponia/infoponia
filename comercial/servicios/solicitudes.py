# Solicitudes de revisión de `comercial`. COM-06a: la única función que crea una `SolicitudRevision` y escribe su `entrega` y su número (D-68, punto 5); la usan `concrecion.crear_discrepancia` y
# `confirmacion.registrar_respuesta` (las quejas). COM-07a (D-69; docs/casos_de_uso/comercial/solicitudes.md): consultar (COM-CNS-SRV), evaluar una discrepancia (COM-EVL-DSC), resolver una queja
# (COM-RSV-QJA) y anular una resolución (COM-ANL-SRV). Las de escritura reciben al actor, verifican que sea el Gerente activo **después de bloquear** (MD-117) y corren en UNA transacción con UN
# registro de auditoría (D-36). Sin asientos ni contraasientos (D-57). Los códigos de error son `ValidationError` con `code` (el patrón de `comercial`; el extracto los llama `ErrorComercial`).
#
# Bloqueos (`FOR NO KEY UPDATE`; docs/patrones/bloqueos.md, «Resolver o anular una solicitud»; D-69, punto 11): las cuentas (el Gerente y el Vendedor del contrato, por id) → el invernadero de origen
# de la entrega (`bloquear_invernadero_para_alertas`) → el contrato (el contador de incumplimientos) → la entrega (el cobro de COM-08 la bloquea también) → la solicitud → su `AlertaComercial`. Va en el
# mismo sentido que la concreción (invernadero → contrato → entrega): no se cruzan. Los correos y la resolución del contrato salen con `transaction.on_commit` (D-14, D-65, D-69 punto 13).
# Fuente: docs/modelo/comercial.md («SolicitudRevision», «Anulacion»), D-69, D-68, D-52 punto 3 (la secuencia de números).

import json
import logging
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import partial

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Case, Count, DateField, F, IntegerField, OuterRef, Q, Subquery, When
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, Anulacion, Contrato, DiscrepanciaEntrega, Entrega, LineaDiscrepancia, Queja, SolicitudRevision, Suministro
from comercial.servicios import asientos_comerciales, cobranza, entregas, indemnizaciones, resoluciones
from comercial.servicios.compra_ventas import texto_de_pesos
from comercial.servicios.comprobantes import Destinatario
from contabilidad.models import AsientoContable
from contabilidad.servicios import responsables
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import stock
from maestros.extensiones import Enlace
from maestros.servicios import alertas
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from produccion.models import Merma, OrdenTrabajo
from produccion.servicios import bitacora

logger = logging.getLogger("infoponia.solicitudes")

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
GERENTE, VENDEDOR = Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR
Estado = SolicitudRevision.Estado
Tipo = SolicitudRevision.Tipo
AVISO = Entrega.EstadoDelAviso
MEDIOS = SolicitudRevision.MedioDeReintegro.values
ACEPTAR, RECHAZAR = "aceptar", "rechazar"
LARGO_DE_OBSERVACIONES = 500
LARGO_DEL_MOTIVO = 500
LARGO_DEL_EVENTO = 500
POR_PAGINA = 50
TEXTO_DE_LA_QUEJA = {"estado_mercaderia": "estado de la mercadería", "retraso": "retraso", "otro": "otro"}
TEXTO_DEL_CAMBIO = {
    "estado_solicitud": "el estado de la solicitud",
    "estado_contrato": "el estado del contrato",
    "incumplimientos": "los incumplimientos del contrato",
    "monto_a_cobrar": "el monto a cobrar de la entrega",
    "estado_de_pago": "el estado de pago de la entrega",
    "solicitud_resolucion": "la resolución del contrato",
}


def siguiente_numero():
    """El número de la próxima solicitud, de la secuencia ``comercial_solicitud_numero_seq`` (D-52 punto 3, como ``compra_ventas.siguiente_numero``). Puede haber huecos si una
    transacción se deshace (``docs/temas_abiertos.md``, «Huecos en el número de orden»). Nunca un ``max()+1``."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_solicitud_numero_seq')")
        return cursor.fetchone()[0]


def crear_solicitud(clase, entrega, **campos):
    """Crea una solicitud de la ``clase`` hija (`DiscrepanciaEntrega` o `Queja`) para ``entrega``, «pendiente», con el número de la secuencia y la fecha de hoy
    (``fecha_solicitud`` puede pasarse en ``campos``). Corre dentro de la transacción del caso de uso que la llama (sin ella, `RuntimeError`). El tipo lo fija la hija."""
    if transaction.get_autocommit():
        raise RuntimeError("`crear_solicitud` corre dentro de la transacción del caso de uso que la llama.")
    if not issubclass(clase, SolicitudRevision):
        raise TypeError("`clase` tiene que ser una hija de `SolicitudRevision`.")
    campos.setdefault("fecha_solicitud", timezone.localdate())
    return clase.objects.create(entrega=entrega, numero=siguiente_numero(), **campos)


# ---- utilidades ----


def _pesos(valor):
    """«$ 1.500,50»."""
    return texto_de_pesos(valor)


def _rechazar(codigo, mensaje, campo="__all__", params=None):
    """Un `ValidationError` con código estable (patrón de `comercial`). Se lanza con `raise`."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo, params=params)]})


def _lanzar(errores):
    """Los errores por campo de `_evaluar` (``{campo: [(código, mensaje)]}``) como un solo `ValidationError`."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo) for codigo, mensaje in lista] for campo, lista in errores.items()})


def _nombre(usuario):
    """«Nombre Apellido», o el correo si la cuenta no tiene nombre."""
    if usuario is None:
        return ""
    return f"{usuario.first_name} {usuario.last_name}".strip() or usuario.email


def _acotar(texto, largo):
    return entregas._acotar(texto, largo)


def _exigir_gerente(actor):
    """El Gerente con la cuenta activa, leída de la base (una cuenta dada de baja después de cargarse no resuelve). Cualquier otro: `PermissionDenied` (MD-117; `sin_permiso`)."""
    vigente = Usuario.objects.filter(pk=actor.pk).first() if actor is not None and getattr(actor, "pk", None) else None
    if vigente is None or not vigente.is_active or rol_de(vigente) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return vigente


def _exigir_lector(actor):
    """El Gerente o el Vendedor con la cuenta activa (COM-CNS-SRV, precondición a)."""
    vigente = Usuario.objects.filter(pk=actor.pk).first() if actor is not None and getattr(actor, "pk", None) else None
    if vigente is None or not vigente.is_active or rol_de(vigente) not in (GERENTE, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return vigente


def _solicitud(solicitud_id):
    """La solicitud (padre) con su entrega y su contrato; `Http404` si no existe."""
    s = SolicitudRevision.objects.select_related("entrega__contrato_entrega__cliente", "entrega__transportista", "entrega__invernadero", "gerente").filter(pk=solicitud_id).first()
    if s is None:
        raise Http404("No existe esa solicitud.")
    return s


def _del_alcance(actor, solicitud_id):
    """``(actor, solicitud)`` si la solicitud es de un contrato del alcance del actor (regla 1 de COM-CNS-SRV; D-28); si no, `PermissionDenied`."""
    actor = _exigir_lector(actor)
    s = _solicitud(solicitud_id)
    if not Contrato.objects.en_alcance_de(actor).filter(pk=s.entrega.contrato_entrega_id).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return actor, s


def _hija(s):
    """La hija (`DiscrepanciaEntrega` o `Queja`) de la solicitud `s`."""
    clase = Queja if s.tipo_solicitud == Tipo.QUEJA else DiscrepanciaEntrega
    return clase.objects.select_related("entrega__contrato_entrega__cliente", "entrega__transportista", "gerente").get(pk=s.pk)


def _texto_del_tipo(s):
    """«Discrepancia de cantidad» o «Queja · retraso» (la lista y la ficha)."""
    if s.tipo_solicitud == Tipo.DISCREPANCIA:
        return "Discrepancia de cantidad"
    return f"Queja · {TEXTO_DE_LA_QUEJA[s.tipo_queja]}"


def _texto_corto_del_tipo(s):
    """«discrepancia» o «queja» (los avisos)."""
    return "discrepancia" if s.tipo_solicitud == Tipo.DISCREPANCIA else "queja"


def _no_pendiente(s):
    """8a, 3a y 1a1: la decisión tomada, el Gerente que la tomó y la fecha de resolución."""
    decision = s.get_estado_solicitud_display().lower()
    gerente = _nombre(s.gerente)
    fecha = f"{s.fecha_resolucion:%d/%m/%Y}" if s.fecha_resolucion else ""
    return _rechazar(
        "solicitud_no_pendiente",
        f"{s.codigo} ya no está pendiente de revisión: fue {decision} por {gerente} el {fecha}.",
        params={"decision": decision, "gerente": gerente, "fecha": fecha},
    )


# ---- lo que se lee de una solicitud (la ficha, el resumen y el registro leen lo mismo) ----


@dataclass
class LineaDeSolicitud:
    """Una línea de la ficha: un detalle de la entrega (de una discrepancia o de una queja) con lo que dice su cláusula."""

    id: int  # el `DetalleEntrega`
    linea_discrepancia_id: int | None
    variedad: str
    fecha_periodo: date
    plazo: int
    dias: int
    por_dia: Decimal
    minima: int | None
    por_planta: Decimal
    planificada: int
    entregada: int
    perdida: int
    devuelta: int
    monto_a_pagar: Decimal
    monto: Decimal | None = None


@dataclass
class Lectura:
    """Todo lo que se necesita para decidir (pasos 4 de COM-EVL-DSC y COM-RSV-QJA) y para la huella (D-69, punto 12)."""

    solicitud: object
    entrega: object
    suministro: object
    lineas: list
    monto_a_cobrar: Decimal
    estado_de_pago: str | None
    pagada: bool
    es_manual: bool
    tope: Decimal | None
    calculado: Decimal | None
    hoy: date
    cobro: object = None  # COM-08a: el `CobroDeEntrega` de la entrega (código, fecha y quién lo registró) o `None` si no tiene un cobro vigente (una saldada no tiene cobro)

    @property
    def datos_de_huella(self):
        s, su = self.solicitud, self.suministro
        return {
            "estado_solicitud": s.estado_solicitud,
            "estado_contrato": su.estado_suministro,
            "incumplimientos": su.cantidad_incumplimientos,
            "monto_a_cobrar": str(self.monto_a_cobrar),
            "estado_de_pago": self.estado_de_pago or "",
            "solicitud_resolucion": su.solicitud_resolucion_id,
        }

    @property
    def huella(self):
        return json.dumps(self.datos_de_huella, sort_keys=True)


def _armar_lineas(s, entrega):
    """Las líneas de la solicitud `s` (hija), con el monto de cada una. Discrepancia: lo guardado si está aceptada, o lo que da la cláusula de hoy. Queja por retraso: días × indemnización por día.
    Una consulta por tabla."""
    cargar = ("detalle_suministro__variedad__cultivo", "detalle_suministro__clausula_suministrante")
    if s.tipo_solicitud == Tipo.DISCREPANCIA:
        registros = [
            (linea.detalle_entrega, linea)
            for linea in LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).select_related(*[f"detalle_entrega__{c}" for c in cargar]).order_by("pk")
        ]
    else:
        registros = [(d, None) for d in s.detalles.select_related(*cargar).order_by("pk")]
    lineas = []
    for detalle, linea in registros:
        clausula = detalle.detalle_suministro.clausula_suministrante
        lineas.append(
            LineaDeSolicitud(
                id=detalle.pk,
                linea_discrepancia_id=linea.pk if linea else None,
                variedad=str(detalle.detalle_suministro.variedad),
                fecha_periodo=detalle.fecha_periodo,
                plazo=clausula.plazo_entrega_dias,
                dias=indemnizaciones.dias_de_retraso(entrega.fecha_resolucion_orden, detalle.fecha_periodo, clausula.plazo_entrega_dias),
                por_dia=clausula.indemnizacion_retraso_entrega,
                minima=linea.cantidad_minima_estipulada if linea else None,
                por_planta=clausula.indemnizacion_faltante,
                planificada=(detalle.cant_entregada or 0) + (detalle.cant_perdida or 0) + (detalle.cant_devuelta or 0),
                entregada=linea.cantidad_entregada if linea else (detalle.cant_entregada or 0),
                perdida=detalle.cant_perdida or 0,
                devuelta=detalle.cant_devuelta or 0,
                monto_a_pagar=detalle.monto_pagar or Decimal("0.00"),
            )
        )
    if s.tipo_solicitud == Tipo.DISCREPANCIA:
        if s.estado_solicitud == Estado.ACEPTADA:
            guardados = {linea.pk: linea.monto_indemnizacion_linea for _, linea in registros}
            for l in lineas:
                l.monto = guardados[l.linea_discrepancia_id]
        else:
            montos, _ = indemnizaciones.montos_de_discrepancia([(l.minima, l.entregada, l.por_planta) for l in lineas])
            for l, monto in zip(lineas, montos):
                l.monto = monto
    elif s.tipo_queja == Queja.TipoDeQueja.RETRASO:
        for l in lineas:
            l.monto = indemnizaciones.monto_por_retraso([(l.dias, l.por_dia)])
    return lineas


def _leer(solicitud_id, hoy):
    """La `Lectura` de una solicitud: la hija, la entrega con su destino, el suministro (con el contador y el estado), las líneas, el monto a cobrar y el estado de pago de la entrega."""
    previa = SolicitudRevision.objects.get(pk=solicitud_id)
    s = _hija(previa)
    entrega = Entrega.objects.select_related(
        "contrato_entrega__cliente", "transportista", "invernadero", "direccion_destino__localidad", "direccion_destino__direccionurbana", "direccion_destino__direccionrural"
    ).get(pk=s.entrega_id)
    suministro = Suministro.objects.select_related("cliente").get(pk=entrega.contrato_entrega_id)
    lineas = _armar_lineas(s, entrega)
    es_manual = s.tipo_solicitud == Tipo.QUEJA and s.tipo_queja != Queja.TipoDeQueja.RETRASO
    if s.tipo_solicitud == Tipo.DISCREPANCIA:
        calculado = s.monto_indemnizacion if s.estado_solicitud == Estado.ACEPTADA else indemnizaciones.redondear(sum((l.monto for l in lineas), Decimal("0.00")))
    elif es_manual:
        calculado = None
    else:
        calculado = indemnizaciones.monto_por_retraso([(l.dias, l.por_dia) for l in lineas])
    estado_de_pago = entregas.estado_de_pago([entrega.pk], hoy)[entrega.pk]
    return Lectura(
        solicitud=s,
        entrega=entrega,
        suministro=suministro,
        lineas=lineas,
        monto_a_cobrar=entregas.monto_a_cobrar([entrega.pk])[entrega.pk],
        estado_de_pago=estado_de_pago,
        pagada=estado_de_pago == "pagada",
        es_manual=es_manual,
        tope=indemnizaciones.tope_manual([l.monto_a_pagar for l in lineas]) if es_manual else None,
        calculado=calculado,
        hoy=hoy,
        cobro=getattr(estado_de_pago, "cobro", None),
    )


def _cambios_de_la_huella(huella_vieja, datos_nuevos):
    """Qué cambió entre la huella que trajo la pantalla y lo que hay ahora (8b de COM-EVL-DSC y COM-RSV-QJA, 5a de COM-ANL-SRV): la lista de textos."""
    try:
        vieja = json.loads(huella_vieja)
    except (TypeError, ValueError):
        return ["los datos de la solicitud"]
    return [TEXTO_DEL_CAMBIO[clave] for clave in TEXTO_DEL_CAMBIO if vieja.get(clave) != datos_nuevos.get(clave)] or ["los datos de la solicitud"]


def _cambio_simultaneo(cambios):
    return _rechazar("solicitud_cambio", f"Mientras mirabas la solicitud cambió {', '.join(cambios)}. Mirá cómo quedó y volvé a decidir.", params={"cambios": cambios})


# ---- los datos y el resumen de la resolución (pasos 5 y 6) ----


@dataclass
class DatosDeResolucion:
    """Lo que carga el Gerente (paso 5): la decisión (`aceptar` o `rechazar`), las observaciones, el monto (solo en una queja sin cláusula) y el medio del reintegro (`efectivo` o `transferencia`)."""

    decision: str = ""
    observaciones: str = ""
    monto: str = ""
    medio_reintegro: str = ""


def datos_de_resolucion(post):
    """`DatosDeResolucion` desde un `QueryDict` (las claves `decision`, `observaciones`, `monto` y `medio_reintegro`)."""
    return DatosDeResolucion(
        (post.get("decision") or "").strip(),
        (post.get("observaciones") or "").strip(),
        (post.get("monto") or "").strip(),
        (post.get("medio_reintegro") or "").strip(),
    )


@dataclass
class ResumenDeResolucion:
    """El paso 6: la decisión, el monto y cómo se aplicaría, los incumplimientos antes y después, la advertencia de resolución del contrato (6b) o de historial (6c) y la huella (D-69, punto 12)."""

    lectura: Lectura
    datos: DatosDeResolucion
    errores: dict = field(default_factory=dict)
    decision: str = ""
    observaciones: str = ""
    monto: Decimal | None = None
    descontado: Decimal | None = None
    reintegrado: Decimal | None = None
    medio: str = ""
    necesita_medio: bool = False
    monto_a_cobrar_antes: Decimal | None = None
    monto_a_cobrar_despues: Decimal | None = None
    incumplimientos_antes: int = 0
    incumplimientos_despues: int = 0
    tolerados: int = 0
    resolveria: bool = False
    historial: bool = False
    multa: Decimal | None = None
    textos: list = field(default_factory=list)
    huella: str = ""
    asiento: list = field(default_factory=list)  # CON-04d: las líneas del asiento de la indemnización que se registrará (decisión (3) del 26/11/2026); vacío si rechaza, si el monto es 0 o si hay errores

    @property
    def hay_errores(self):
        return bool(self.errores)

    @property
    def solicitud(self):
        return self.lectura.solicitud


def _evaluar(lectura, datos):
    """Los pasos 5 y 6 con una sola lógica para el resumen y para el registro: valida `datos`, calcula el monto y su aplicación y arma los textos. No escribe."""
    s, suministro, entrega = lectura.solicitud, lectura.suministro, lectura.entrega
    resumen = ResumenDeResolucion(
        lectura=lectura,
        datos=datos,
        decision=datos.decision,
        observaciones=datos.observaciones.strip(),
        monto_a_cobrar_antes=lectura.monto_a_cobrar,
        incumplimientos_antes=suministro.cantidad_incumplimientos,
        tolerados=suministro.incumplimientos_tolerados,
        multa=suministro.multa_resolucion,
        huella=lectura.huella,
    )
    errores = resumen.errores

    def error(campo, codigo, mensaje):
        errores.setdefault(campo, []).append((codigo, mensaje))

    if datos.decision not in (ACEPTAR, RECHAZAR):
        error("decision", "decision_obligatoria", "Elegí si aceptás o rechazás.")
    if len(resumen.observaciones) > LARGO_DE_OBSERVACIONES:
        error("observaciones", "observaciones_largas", f"Las observaciones pasan de {LARGO_DE_OBSERVACIONES} caracteres.")
    if datos.decision == RECHAZAR and not resumen.observaciones:
        error("observaciones", "observaciones_obligatorias", "Las observaciones son obligatorias al rechazar: el cliente las recibe.")
    aceptar = datos.decision == ACEPTAR
    resumen.incumplimientos_despues = resumen.incumplimientos_antes + (1 if aceptar else 0)
    resumen.monto_a_cobrar_despues = lectura.monto_a_cobrar
    if aceptar:
        monto = None
        if lectura.es_manual:
            try:
                monto = indemnizaciones.monto_manual(datos.monto, lectura.tope)
            except ValueError as mensaje:
                error("monto", "monto_invalido", f"{mensaje} Tiene que estar entre {_pesos(0)} y {_pesos(lectura.tope)}.")
        else:
            if datos.monto.strip():
                error("monto", "monto_no_admitido", "Esta solicitud no admite cargar un monto: sale de la cláusula del contrato.")
            monto = lectura.calculado
        if monto is not None:
            resumen.monto = monto
            resumen.descontado, resumen.reintegrado = indemnizaciones.aplicacion(monto, lectura.monto_a_cobrar, lectura.pagada)
            resumen.monto_a_cobrar_despues = lectura.monto_a_cobrar - resumen.descontado
            resumen.necesita_medio = resumen.reintegrado > 0
            if resumen.necesita_medio:
                if datos.medio_reintegro in MEDIOS:
                    resumen.medio = datos.medio_reintegro
                else:
                    error("medio_reintegro", "medio_obligatorio", "Elegí el medio del reintegro: efectivo o transferencia.")
        resumen.resolveria = suministro.estado_suministro == Suministro.Estado.VIGENTE and resumen.incumplimientos_despues > suministro.incumplimientos_tolerados  # 6b
        resumen.historial = suministro.estado_suministro != Suministro.Estado.VIGENTE  # 6c
    resumen.textos = _textos_del_resumen(resumen, s, entrega, suministro)
    return resumen


def _texto_de_la_aplicacion(resumen, entrega):
    """Cómo se aplica la indemnización (paso 6 y extensiones 6a y 6d)."""
    monto, descontado, reintegrado = resumen.monto, resumen.descontado, resumen.reintegrado
    if monto is None:
        return ""
    if monto <= 0:
        return "Sin indemnización: no cambia lo que el cliente debe."
    medio = SolicitudRevision.MedioDeReintegro(resumen.medio).label.lower() if resumen.medio else "el medio que elijas"
    if resumen.lectura.pagada:
        return f"La entrega ya está pagada: se reintegran {_pesos(reintegrado)} al cliente con {medio}."
    if reintegrado > 0:
        return f"Se descuentan {_pesos(descontado)} de lo que el cliente debe por {entrega.codigo} (queda en {_pesos(0)}) y se le reintegran {_pesos(reintegrado)} con {medio}."
    return f"Se descuentan {_pesos(descontado)} de lo que el cliente debe por {entrega.codigo}: el monto a cobrar pasa de {_pesos(resumen.monto_a_cobrar_antes)} a {_pesos(resumen.monto_a_cobrar_despues)}."


def _textos_del_resumen(resumen, s, entrega, suministro):
    """Las líneas del resumen del paso 6 (y de 5a.2): la decisión, el monto, su aplicación y los incumplimientos."""
    if resumen.decision == RECHAZAR:
        return ["Rechazada: sin indemnización y sin cambios en los incumplimientos del contrato.", "El cliente recibe un aviso con tus observaciones y se notifica al Vendedor."]
    if resumen.decision != ACEPTAR or resumen.monto is None:
        return []
    textos = [f"{'Queja aceptada' if s.tipo_solicitud == Tipo.QUEJA else 'Discrepancia aceptada'}, con indemnización de {_pesos(resumen.monto)}."]
    aplicacion = _texto_de_la_aplicacion(resumen, entrega)
    if aplicacion:
        textos.append(aplicacion)
    textos.append(f"Incumplimientos del contrato {suministro.codigo}: {resumen.incumplimientos_despues} de {resumen.tolerados} tolerados.")
    if resumen.resolveria:
        textos.append(f"Con esta aceptación se superan los incumplimientos tolerados: {suministro.codigo} se resolverá y se aplicará la multa de {_pesos(resumen.multa)}.")
    elif resumen.historial:
        textos.append(f"{suministro.codigo} está {suministro.get_estado_suministro_display().lower()}: el incumplimiento se registra como historial, sin resolución.")
    textos.append("Se registra el evento en la bitácora del invernadero y se avisa al cliente y al Vendedor.")
    return textos


def resumen_de_resolucion(actor, solicitud_id, datos=None, hoy=None):
    """Paso 6 (solo lectura: no escribe ni bloquea). Valida `datos`, calcula el monto y su aplicación y devuelve el resumen con los errores por campo y la huella. Solo el Gerente activo
    (`PermissionDenied`); `Http404` si no existe; `solicitud_no_pendiente` si ya se resolvió (1a1, 3a)."""
    _exigir_gerente(actor)
    s = _solicitud(solicitud_id)
    if s.estado_solicitud != Estado.PENDIENTE:
        raise _no_pendiente(s)
    resumen = _evaluar(_leer(solicitud_id, hoy or stock.hoy()), datos or DatosDeResolucion())
    if resumen.decision == ACEPTAR and not resumen.hay_errores and resumen.monto and resumen.monto > 0:
        resumen.asiento = asientos_comerciales.filas_de(asientos_comerciales.movimientos_de_indemnizacion(resumen.monto, resumen.descontado, resumen.reintegrado, resumen.medio))
    return resumen


# ---- el registro (paso 8) ----


def _bloquear(previa, actor):
    """Toma los bloqueos del encabezado y devuelve ``(cuenta del actor, invernadero)``. Quien resuelve o anula verifica su rol **después** de bloquear."""
    entrega = previa.entrega
    cuentas = {actor.pk, entrega.contrato_entrega.vendedor_id}
    por_id = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk")}
    quien = por_id.get(actor.pk)
    if quien is None or not quien.is_active or rol_de(quien) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    invernadero = bloquear_invernadero_para_alertas(entrega.invernadero_id)
    list(Contrato.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega.contrato_entrega_id))
    list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega.pk))
    list(SolicitudRevision.objects.select_for_update(no_key=True, of=("self",)).filter(pk=previa.pk))
    list(AlertaComercial.objects.select_for_update(no_key=True, of=("self",)).filter(solicitud_id=previa.pk))
    return quien, invernadero


def _correr(funcion, *argumentos):
    """Corre algo de un `on_commit` sin que una falla vuelva a quien lo disparó: lo suyo ya quedó registrado (9a; garantía mínima de COM-RSV-SUM)."""
    try:
        funcion(*argumentos)
    except Exception:  # noqa: BLE001
        logger.exception("Falló %s%s disparada por una solicitud de revisión", funcion.__name__, argumentos)


def _cambios(**pares):
    """``{campo: {"antes", "despues"}}`` solo de lo que cambió (D-36: un cambio con el mismo valor antes y después se rechaza)."""
    return {campo: {"antes": antes, "despues": despues} for campo, (antes, despues) in pares.items() if antes != despues}


def _iso(fecha):
    return fecha.isoformat() if fecha else None


def _texto(valor):
    return None if valor is None else str(valor)


def _descripcion_del_evento(s, entrega, suministro, lineas, monto):
    """La descripción del evento «incumplimiento de cláusula suministrante» (postcondición f; hasta 500: si no entra, las líneas que sobran van como «y N más»)."""
    donde = f"Transportista: {_nombre(entrega.transportista)}" if entrega.transportista_id else "Retiro en invernadero"
    tipo = "Discrepancia" if s.tipo_solicitud == Tipo.DISCREPANCIA else f"Queja por {TEXTO_DE_LA_QUEJA[s.tipo_queja]}"
    prefijo = f"{s.codigo} · {tipo} · {entrega.codigo} de {suministro.codigo} · {donde}"
    if s.tipo_solicitud == Tipo.DISCREPANCIA:
        piezas = [f"{l.variedad}: {l.entregada} de {l.minima}, {_pesos(l.monto)}" for l in lineas]
    elif s.tipo_queja == Queja.TipoDeQueja.RETRASO:
        piezas = [f"{l.variedad}: {l.dias} días, {_pesos(l.monto)}" for l in lineas if l.dias > 0]
    else:
        piezas = [l.variedad for l in lineas]
    total = f"Total: {_pesos(monto)}"
    for k in range(len(piezas), -1, -1):
        resto = [f"y {len(piezas) - k} más"] if k < len(piezas) else []
        texto = " · ".join([prefijo, *piezas[:k], *resto, total])
        if len(texto) <= LARGO_DEL_EVENTO:
            return texto
    return _acotar(f"{prefijo} · {total}", LARGO_DEL_EVENTO)


def _aviso_al_vendedor(vendedor, titulo, detalle):
    """Un aviso al Vendedor del contrato si su cuenta está activa (D-42; dentro de la transacción)."""
    if vendedor is not None:
        notificaciones.notificar(vendedor, _acotar(titulo, notificaciones.LARGO_TITULO), _acotar(detalle, notificaciones.LARGO_DETALLE))


def resolver_solicitud(actor, solicitud_id, datos, huella):
    """Paso 8 de COM-EVL-DSC y de COM-RSV-QJA (y 5a.4): registra la resolución en UNA transacción, con los bloqueos del encabezado y un único registro de auditoría. Devuelve la solicitud (hija).

    Después de bloquear vuelve a leer y verifica: `solicitud_no_pendiente` (8a), la huella (`solicitud_cambio`: la pantalla vuelve al paso 4, 8b) y todos los datos (los mismos errores por campo del
    resumen: `decision_obligatoria`, `observaciones_obligatorias`, `observaciones_largas`, `monto_invalido`, `monto_no_admitido`, `medio_obligatorio`). Al aceptar: guarda el monto y su aplicación
    (descontado y reintegrado), suma un incumplimiento, escribe la bitácora, resuelve la alerta, avisa al Vendedor y, con `on_commit`, manda el correo al cliente y llama a
    `resoluciones.resolver_si_corresponde` (D-69, punto 13). Al rechazar: sin montos, sin contador y sin bitácora. Sin asientos (D-57)."""
    _exigir_gerente(actor)
    previa = _solicitud(solicitud_id)
    datos = datos or DatosDeResolucion()
    with transaction.atomic():
        quien, invernadero = _bloquear(previa, actor)
        solicitud = SolicitudRevision.objects.select_related("gerente").get(pk=solicitud_id)
        if solicitud.estado_solicitud != Estado.PENDIENTE:
            raise _no_pendiente(solicitud)
        lectura = _leer(solicitud_id, stock.hoy())
        if lectura.huella != huella:
            raise _cambio_simultaneo(_cambios_de_la_huella(huella, lectura.datos_de_huella))
        resumen = _evaluar(lectura, datos)
        if resumen.hay_errores:
            raise _lanzar(resumen.errores)
        return _registrar(quien, invernadero, lectura, resumen)


def evaluar_discrepancia(actor, solicitud_id, datos, huella):
    """COM-EVL-DSC: `resolver_solicitud` de una discrepancia (`Http404` si la solicitud es una queja)."""
    if _solicitud(solicitud_id).tipo_solicitud != Tipo.DISCREPANCIA:
        raise Http404("No existe esa discrepancia.")
    return resolver_solicitud(actor, solicitud_id, datos, huella)


def resolver_queja(actor, solicitud_id, datos, huella):
    """COM-RSV-QJA: `resolver_solicitud` de una queja (`Http404` si la solicitud es una discrepancia)."""
    if _solicitud(solicitud_id).tipo_solicitud != Tipo.QUEJA:
        raise Http404("No existe esa queja.")
    return resolver_solicitud(actor, solicitud_id, datos, huella)


def _registrar(quien, invernadero, lectura, resumen):
    """Los pasos del 8 en este orden: la solicitud → el contador → la bitácora → la alerta → el aviso al Vendedor → la auditoría → los correos y la resolución del contrato (`on_commit`)."""
    s, entrega, suministro = lectura.solicitud, lectura.entrega, lectura.suministro
    hoy = lectura.hoy
    aceptar = resumen.decision == ACEPTAR
    cliente = suministro.cliente
    aviso = AVISO.PENDIENTE_ENVIO if cliente.email_cliente else AVISO.SIN_CORREO
    campos = {
        "estado_solicitud": Estado.ACEPTADA if aceptar else Estado.RECHAZADA,
        "fecha_resolucion": hoy,
        "gerente": quien,
        "observaciones_resolucion": resumen.observaciones,
        "estado_aviso_cliente": aviso,
    }
    if aceptar:
        campos.update(
            monto_indemnizacion=resumen.monto,
            monto_descontado=resumen.descontado,
            monto_reintegrado=resumen.reintegrado,
            medio_reintegro=resumen.medio if resumen.reintegrado > 0 else None,
        )
    SolicitudRevision.objects.filter(pk=s.pk).update(**campos)
    evento = None
    if aceptar:
        if s.tipo_solicitud == Tipo.DISCREPANCIA:
            for l in lectura.lineas:
                LineaDiscrepancia.objects.filter(pk=l.linea_discrepancia_id).update(monto_indemnizacion_linea=l.monto)
        Suministro.objects.filter(pk=suministro.pk).update(cantidad_incumplimientos=F("cantidad_incumplimientos") + 1)  # postcondición d, también en un contrato no vigente (6c: historial)
        evento = bitacora.registrar_evento_de_contrato(
            invernadero, "incumplimiento_de_clausula", _descripcion_del_evento(s, entrega, suministro, lectura.lineas, resumen.monto), quien
        )
    vinculo = AlertaComercial.objects.select_related("alerta").filter(solicitud_id=s.pk).first()
    alerta_resuelta = alertas.resolver_alerta(vinculo.alerta_id) if vinculo is not None else None  # `None` si ya estaba resuelta (una solicitud reabierta, D-69 punto 4)
    mora_resueltas, mora_nuevas = cobranza.reevaluar_mora_con_rastro(entrega.pk, hoy)  # COM-08a, MD-125: una aceptación que salda la entrega resuelve su alerta «pago en mora»
    _avisar_resolucion_al_vendedor(s, entrega, suministro, resumen, aceptar)
    # postcondición e (CON-04d), después de todos los bloqueos de negocio: el ejercicio va último (D-86). Decisión del estudiante del 26/11/2026 (choque con R012, un origen un asiento): si esta solicitud ya tuvo
    # asiento (una aceptación anterior que se anuló), la nueva aceptación NO asienta: avisa al responsable contable para que lo registre a mano y queda constancia en la auditoría.
    asiento, pendiente_a_mano = None, None
    if aceptar and resumen.monto > 0:
        if AsientoContable.objects.filter(origen_id=s.pk).exists():
            pendiente_a_mano = f"{s.codigo}: {_pesos(resumen.monto)} ({_pesos(resumen.descontado)} contra Deudores por Ventas y {_pesos(resumen.reintegrado)} reintegrados)"
            responsables.notificar_al_responsable_contable(
                _acotar(f"Registrar el asiento de {s.codigo}", notificaciones.LARGO_TITULO),
                _acotar(f"Se volvió a aceptar {s.codigo} después de anular su aceptación y el sistema no puede repetir el asiento: registrá a mano la indemnización de {pendiente_a_mano}.", notificaciones.LARGO_DETALLE),
                excluir=quien,
            )
        else:
            asiento = asientos_comerciales.asentar_indemnizacion(quien, s, resumen.monto, resumen.descontado, resumen.reintegrado, resumen.medio, hoy)
    cambios = _cambios(
        estado_solicitud=("pendiente", campos["estado_solicitud"]),
        fecha_resolucion=(None, _iso(hoy)),
        gerente=(None, referencia(quien)),
        observaciones_resolucion=("", resumen.observaciones),
        monto_indemnizacion=(None, _texto(resumen.monto)),
        monto_descontado=(None, _texto(resumen.descontado)),
        monto_reintegrado=(None, _texto(resumen.reintegrado)),
        medio_reintegro=(None, campos.get("medio_reintegro")),
        estado_aviso_cliente=(None, aviso),
    )
    datos = {
        "entrega": referencia(entrega),
        "suministro": referencia(suministro),
        "monto_a_cobrar_antes": str(resumen.monto_a_cobrar_antes),
        "monto_a_cobrar_despues": str(resumen.monto_a_cobrar_despues),
        "incumplimientos_antes": resumen.incumplimientos_antes,
        "incumplimientos_despues": resumen.incumplimientos_despues,
    }
    if aceptar and resumen.reintegrado > 0:
        datos["reintegro"] = f"{_pesos(resumen.reintegrado)} por {SolicitudRevision.MedioDeReintegro(resumen.medio).label.lower()}"
    resueltas = ([alerta_resuelta] if alerta_resuelta is not None else []) + mora_resueltas
    if resueltas:
        datos["alertas_resueltas"] = [str(a) for a in resueltas]
    if mora_nuevas:
        datos["alertas_creadas"] = [str(a) for a in mora_nuevas]
    if asiento is not None:
        datos["asientos"] = [str(asiento)]
    if pendiente_a_mano is not None:
        datos["asiento_manual_pendiente"] = pendiente_a_mano
    afectados = [s] + resueltas + mora_nuevas + ([suministro, evento] if aceptar else []) + ([asiento] if asiento is not None else [])
    RegistroAuditoria.objects.registrar(
        usuario=quien,
        accion=RegistroAuditoria.Accion.EVALUACION_DISCREPANCIA if s.tipo_solicitud == Tipo.DISCREPANCIA else RegistroAuditoria.Accion.RESOLUCION_QUEJA,
        afectados=afectados,
        detalle={"cambios": cambios, "datos": datos},
    )
    if aviso == AVISO.PENDIENTE_ENVIO:
        transaction.on_commit(partial(_correr, enviar_aviso_de_resolucion, s.pk))
    if aceptar:
        transaction.on_commit(partial(_correr, resoluciones.resolver_si_corresponde, suministro.pk))
    return type(s).objects.get(pk=s.pk)


def _avisar_resolucion_al_vendedor(s, entrega, suministro, resumen, aceptar):
    """Postcondición g (aceptada) o i (rechazada): una notificación al Vendedor del contrato, si su cuenta está activa."""
    vendedor = entregas._usuario_activo(suministro.vendedor_id)
    cliente = suministro.cliente.nombre_visible
    tipo = _texto_corto_del_tipo(s)
    if not aceptar:
        _aviso_al_vendedor(vendedor, f"{s.codigo} rechazada", f"El Gerente rechazó la {tipo} de {entrega.codigo} ({cliente}). Observaciones: {resumen.observaciones}")
        return
    if resumen.monto <= 0:
        como = "sin indemnización"
    elif resumen.reintegrado <= 0:
        como = f"indemnización de {_pesos(resumen.monto)}, descontada del monto a cobrar"
    elif resumen.descontado <= 0:
        como = f"indemnización de {_pesos(resumen.monto)}, reintegrada al cliente"
    else:
        como = f"indemnización de {_pesos(resumen.monto)}: {_pesos(resumen.descontado)} descontados y {_pesos(resumen.reintegrado)} reintegrados"
    _aviso_al_vendedor(
        vendedor, f"{s.codigo} aceptada", f"El Gerente aceptó la {tipo} de {entrega.codigo} ({cliente}): {como}. Incumplimientos: {resumen.incumplimientos_despues} de {resumen.tolerados}."
    )


# ---- los correos al cliente (9, 5a.5 y 9a) ----


def contexto_del_aviso(solicitud_id):
    """Lo que dicen el comprobante de indemnización (9a, «Lista de tecnología»), el aviso de aceptación sin indemnización y el aviso de rechazo (9b): la entrega y su fecha, cada línea, el total, cuánto se
    descontó y cuánto se reintegró y con qué medio. De uso interno, sin validez fiscal. Lo usan el correo y la página para imprimir."""
    s = _hija(_solicitud(solicitud_id))
    entrega = s.entrega
    suministro = Suministro.objects.select_related("cliente", "vendedor").get(pk=entrega.contrato_entrega_id)
    aceptada = s.estado_solicitud == Estado.ACEPTADA
    return {
        "codigo": s.codigo,
        "es_queja": s.tipo_solicitud == Tipo.QUEJA,
        "tipo": _texto_corto_del_tipo(s),
        "tipo_queja": TEXTO_DE_LA_QUEJA[s.tipo_queja] if s.tipo_solicitud == Tipo.QUEJA else "",
        "es_retraso": s.tipo_solicitud == Tipo.QUEJA and s.tipo_queja == Queja.TipoDeQueja.RETRASO,
        "entrega": entrega.codigo,
        "fecha_entrega": entrega.fecha_resolucion_orden,
        "contrato": suministro.codigo,
        "cliente": suministro.cliente.nombre_visible,
        "vendedor": suministro.vendedor,
        "decision": s.get_estado_solicitud_display().lower(),
        "aceptada": aceptada,
        "observaciones": s.observaciones_resolucion,
        "lineas": _armar_lineas(s, entrega) if aceptada else [],
        "monto": s.monto_indemnizacion,
        "descontado": s.monto_descontado,
        "reintegrado": s.monto_reintegrado,
        "medio": s.get_medio_reintegro_display() if s.medio_reintegro else "",
        "motivo_de_la_queja": s.motivo_queja if s.tipo_solicitud == Tipo.QUEJA else "",
    }


def _plantilla_y_asunto(contexto):
    """La plantilla y el asunto del correo según el caso: comprobante de indemnización, aviso de aceptación sin indemnización o aviso de rechazo."""
    if not contexto["aceptada"]:
        return "comercial/correos/solicitud_rechazada.txt", f"Tu {contexto['tipo']} {contexto['codigo']} no fue reconocida"
    if contexto["monto"] and contexto["monto"] > 0:
        return "comercial/correos/indemnizacion.txt", f"Comprobante de indemnización {contexto['codigo']}"
    return "comercial/correos/solicitud_aceptada.txt", f"Tu {contexto['tipo']} {contexto['codigo']} fue aceptada"


def enviar_aviso_de_resolucion(solicitud_id):
    """El correo al cliente con el comprobante o el aviso de la resolución. Se llama SIEMPRE fuera de una transacción (D-14). Solo sale desde «pendiente de envío»: sin el correo del sistema configurado o
    si el envío falla, queda «pendiente» (lo reintenta el paso 50, 9a); si sale, «enviado». Devuelve `True` si salió."""
    s = SolicitudRevision.objects.select_related("entrega__contrato_entrega__cliente").filter(pk=solicitud_id).first()
    if s is None or s.estado_solicitud == Estado.PENDIENTE or s.estado_aviso_cliente != AVISO.PENDIENTE_ENVIO:
        return False
    cliente = s.entrega.contrato_entrega.cliente
    if not cliente.email_cliente or not correo.correo_configurado():
        return False
    contexto = contexto_del_aviso(s.pk)
    plantilla, asunto = _plantilla_y_asunto(contexto)
    salio = correo.enviar_correo(Destinatario(cliente.pk, cliente.email_cliente), asunto, plantilla, contexto)
    if salio:
        SolicitudRevision.objects.filter(pk=s.pk, estado_aviso_cliente=AVISO.PENDIENTE_ENVIO).update(estado_aviso_cliente=AVISO.ENVIADO)
    return salio


def reenviar_aviso(actor, solicitud_id):
    """«Reenviar aviso» (9a): lo pueden hacer el Gerente y el Vendedor del contrato, solo si el aviso está «pendiente de envío». Sin auditoría (no cambia datos de negocio). Devuelve si salió. Errores:
    `aviso_no_pendiente` y `cliente_sin_correo`. Fuera de una transacción (D-14)."""
    _, s = _del_alcance(actor, solicitud_id)
    if s.estado_aviso_cliente != AVISO.PENDIENTE_ENVIO:
        raise _rechazar("aviso_no_pendiente", "El aviso de esta solicitud no está pendiente de envío.")
    if not s.entrega.contrato_entrega.cliente.email_cliente:
        raise _rechazar("cliente_sin_correo", "El cliente no tiene correo: el comprobante se entrega impreso.")
    return enviar_aviso_de_resolucion(s.pk)


# ---- anular una resolución (COM-ANL-SRV) ----


@dataclass
class DatosDeAnulacion:
    """El paso 2 de COM-ANL-SRV: la resolución vigente, el estado nuevo, el contador y el monto a cobrar antes y después, y el bloqueo (2a a 2c) si lo hay."""

    solicitud: object
    entrega: object
    suministro: object
    aceptada: bool
    estado_nuevo: str
    contador_antes: int
    contador_despues: int
    monto_a_cobrar_antes: Decimal
    monto_a_cobrar_despues: Decimal
    bloqueo: tuple | None
    huella: str
    datos_de_huella: dict
    contraasiento: list | None = None  # CON-04d: las líneas del contraasiento que se registrará, o `None` (rechazada, sin asiento original o ya revertido)

    @property
    def codigo_del_bloqueo(self):
        return self.bloqueo[0] if self.bloqueo else ""

    @property
    def texto_del_bloqueo(self):
        return self.bloqueo[1] if self.bloqueo else ""


def _bloqueo_de_anulacion(lectura):
    """Los bloqueos de COM-ANL-SRV (D-69, punto 5): 2a la aceptación resolvió el contrato; 2b la entrega ya se cobró con el descuento; 2c la indemnización ya se reintegró al cliente. ``(código, mensaje)`` o `None`."""
    s, suministro, entrega = lectura.solicitud, lectura.suministro, lectura.entrega
    if suministro.solicitud_resolucion_id == s.pk:
        return ("resolucion_del_contrato", f"No se puede anular: esta aceptación resolvió el contrato {suministro.codigo}.")
    if s.estado_solicitud == Estado.ACEPTADA and (s.monto_descontado or 0) > 0 and lectura.cobro is not None:  # COM-08a: un cobro vigente de verdad; una entrega saldada cuenta como «pagada» pero no tiene cobro que anular
        return ("entrega_cobrada", f"Primero anulá el cobro de {entrega.codigo} (Anular cobro).")
    if s.estado_solicitud == Estado.ACEPTADA and (s.monto_reintegrado or 0) > 0:
        return ("indemnizacion_reintegrada", f"No se puede anular: la indemnización ya se le reintegró al cliente ({_pesos(s.monto_reintegrado)} por {s.get_medio_reintegro_display().lower()}).")
    return None


def _datos_de_anulacion(lectura):
    s = lectura.solicitud
    aceptada = s.estado_solicitud == Estado.ACEPTADA
    descontado = s.monto_descontado or Decimal("0.00")
    return DatosDeAnulacion(
        solicitud=s,
        entrega=lectura.entrega,
        suministro=lectura.suministro,
        aceptada=aceptada,
        estado_nuevo=Estado.PENDIENTE.label,
        contador_antes=lectura.suministro.cantidad_incumplimientos,
        contador_despues=max(0, lectura.suministro.cantidad_incumplimientos - 1) if aceptada else lectura.suministro.cantidad_incumplimientos,
        monto_a_cobrar_antes=lectura.monto_a_cobrar,
        monto_a_cobrar_despues=lectura.monto_a_cobrar + descontado if aceptada else lectura.monto_a_cobrar,
        bloqueo=_bloqueo_de_anulacion(lectura),
        huella=lectura.huella,
        datos_de_huella=lectura.datos_de_huella,
    )


def datos_de_anulacion(actor, solicitud_id, hoy=None):
    """Paso 2 de COM-ANL-SRV (solo lectura): lo que va a pasar y los bloqueos 2a a 2c (`bloqueo`), sin lanzarlos: la ventana los muestra con «Volver». Solo el Gerente activo; `Http404` si no existe;
    `solicitud_no_resuelta` si está pendiente."""
    _exigir_gerente(actor)
    s = _solicitud(solicitud_id)
    if s.estado_solicitud == Estado.PENDIENTE:
        raise _rechazar("solicitud_no_resuelta", f"{s.codigo} está pendiente de revisión: no hay una resolución para anular.")
    datos = _datos_de_anulacion(_leer(solicitud_id, hoy or stock.hoy()))
    if datos.aceptada:
        datos.contraasiento = asientos_comerciales.contraasiento_previsto(s)
    return datos


def anular_resolucion(actor, solicitud_id, motivo, huella):
    """Paso 5 de COM-ANL-SRV: en UNA transacción, con los bloqueos de `resolver_solicitud`, crea la `Anulacion` (con la copia de la resolución), deja la solicitud «pendiente» (campos de resolución y montos
    de las líneas en nulo), baja el contador de incumplimientos si estaba aceptada (nunca menos de 0), escribe el evento de bitácora `anulacion_de_resolucion` (solo si estaba aceptada), avisa al Vendedor y
    audita. La alerta no se toca (D-69, punto 4). Sin contraasiento (D-57). Devuelve la `Anulacion`.

    Errores: `motivo_obligatorio` y `motivo_largo` (en `motivo`); `solicitud_no_resuelta`, `resolucion_del_contrato` (2a), `entrega_cobrada` (2b), `indemnizacion_reintegrada` (2c) y `solicitud_cambio` (5a)."""
    _exigir_gerente(actor)
    motivo = (motivo or "").strip()
    if not motivo:
        raise _rechazar("motivo_obligatorio", "Contá por qué anulás la resolución: el motivo es obligatorio.", campo="motivo")
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise _rechazar("motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.", campo="motivo")
    previa = _solicitud(solicitud_id)
    with transaction.atomic():
        quien, invernadero = _bloquear(previa, actor)
        solicitud = SolicitudRevision.objects.get(pk=solicitud_id)
        if solicitud.estado_solicitud == Estado.PENDIENTE:
            raise _rechazar("solicitud_no_resuelta", f"{solicitud.codigo} ya está pendiente de revisión: no hay una resolución para anular.")
        lectura = _leer(solicitud_id, stock.hoy())
        datos = _datos_de_anulacion(lectura)
        if datos.bloqueo is not None:
            raise _rechazar(*datos.bloqueo)
        if datos.huella != huella:
            raise _cambio_simultaneo(_cambios_de_la_huella(huella, datos.datos_de_huella))
        return _anular(quien, invernadero, lectura, datos, motivo)


def _anular(quien, invernadero, lectura, datos, motivo):
    s, entrega, suministro = lectura.solicitud, lectura.entrega, lectura.suministro
    hoy = lectura.hoy
    anterior = {
        "estado_solicitud": s.estado_solicitud,
        "fecha_resolucion": s.fecha_resolucion,
        "gerente": s.gerente,
        "observaciones_resolucion": s.observaciones_resolucion,
        "monto_indemnizacion": s.monto_indemnizacion,
        "monto_descontado": s.monto_descontado,
        "monto_reintegrado": s.monto_reintegrado,
        "medio_reintegro": s.medio_reintegro,
        "estado_aviso_cliente": s.estado_aviso_cliente,
    }
    anulacion = Anulacion.objects.create(
        fecha_anulacion=hoy,
        motivo_anulacion=motivo,
        usuario=quien,
        solicitud=SolicitudRevision.objects.get(pk=s.pk),
        estado_anulado=s.estado_solicitud,
        fecha_resolucion_anulada=s.fecha_resolucion,
        gerente_anulado=s.gerente,
        observaciones_anuladas=s.observaciones_resolucion,
        monto_indemnizacion_anulado=s.monto_indemnizacion,
        monto_descontado_anulado=s.monto_descontado,
        monto_reintegrado_anulado=s.monto_reintegrado,
        medio_reintegro_anulado=s.medio_reintegro,
    )
    SolicitudRevision.objects.filter(pk=s.pk).update(
        estado_solicitud=Estado.PENDIENTE,
        fecha_resolucion=None,
        gerente=None,
        observaciones_resolucion="",
        monto_indemnizacion=None,
        monto_descontado=None,
        monto_reintegrado=None,
        medio_reintegro=None,
        estado_aviso_cliente=None,
    )
    evento = None
    if datos.aceptada:
        if s.tipo_solicitud == Tipo.DISCREPANCIA:
            LineaDiscrepancia.objects.filter(discrepancia_id=s.pk).update(monto_indemnizacion_linea=None)
        Suministro.objects.filter(pk=suministro.pk).update(cantidad_incumplimientos=Greatest(F("cantidad_incumplimientos") - 1, 0, output_field=IntegerField()))  # nunca menos de 0
        evento = bitacora.registrar_evento_de_contrato(
            invernadero,
            "anulacion_de_resolucion",
            _acotar(f"Se anuló la aceptación de {s.codigo} ({entrega.codigo} de {suministro.codigo}): vuelve a pendiente. Motivo: {motivo}", LARGO_DEL_EVENTO),
            quien,
        )
    mora_resueltas, mora_nuevas = cobranza.reevaluar_mora_con_rastro(entrega.pk, hoy)  # COM-08a: si la entrega deja de estar saldada y ya venció, se asegura su alerta «pago en mora» (sin correo ni aviso: su aviso ya lo dice)
    vendedor = entregas._usuario_activo(suministro.vendedor_id)
    cliente = suministro.cliente.nombre_visible
    detalle = f"El Gerente anuló la {'aceptación' if datos.aceptada else 'resolución'} de la {_texto_corto_del_tipo(s)} de {entrega.codigo} ({cliente})."
    if datos.aceptada:
        detalle += f" Monto a cobrar: {_pesos(datos.monto_a_cobrar_antes)} → {_pesos(datos.monto_a_cobrar_despues)}. Incumplimientos: {datos.contador_antes} → {datos.contador_despues}."
    _aviso_al_vendedor(vendedor, f"Se anuló la resolución de {s.codigo}", f"{detalle} Motivo: {motivo}")
    # postcondición c (CON-04d), después de todos los bloqueos de negocio: el ejercicio va último (D-86). Si el asiento original ya se revirtió con una anulación anterior (decisión del estudiante del 26/11/2026: la
    # re-aceptación no asentó), no hay contraasiento y se avisa al responsable contable por si registró a mano la indemnización.
    contraasiento, pendiente_a_mano = None, None
    if datos.aceptada:
        if asientos_comerciales.ya_contraasentado(anulacion, s):
            pendiente_a_mano = f"{s.codigo}: el asiento de su primera aceptación ya se revirtió y no se repite"
            responsables.notificar_al_responsable_contable(
                _acotar(f"Revertir a mano el asiento de {s.codigo}", notificaciones.LARGO_TITULO),
                _acotar(f"Se anuló otra vez la aceptación de {s.codigo} y el sistema no puede repetir el contraasiento (el asiento original ya se revirtió): si registraste a mano la indemnización de la nueva aceptación, revertila con un asiento manual.", notificaciones.LARGO_DETALLE),
                excluir=quien,
            )
        else:
            contraasiento = asientos_comerciales.asentar_anulacion(quien, anulacion, s, hoy, f"Anulación de la resolución de {s.codigo}")
    cambios = _cambios(
        estado_solicitud=(anterior["estado_solicitud"], Estado.PENDIENTE.value),
        fecha_resolucion=(_iso(anterior["fecha_resolucion"]), None),
        gerente=(referencia(anterior["gerente"]) if anterior["gerente"] is not None else None, None),
        observaciones_resolucion=(anterior["observaciones_resolucion"], ""),
        monto_indemnizacion=(_texto(anterior["monto_indemnizacion"]), None),
        monto_descontado=(_texto(anterior["monto_descontado"]), None),
        monto_reintegrado=(_texto(anterior["monto_reintegrado"]), None),
        medio_reintegro=(anterior["medio_reintegro"], None),
        estado_aviso_cliente=(anterior["estado_aviso_cliente"], None),
    )
    datos_auditoria = {
        "motivo": motivo,
        "entrega": referencia(entrega),
        "suministro": referencia(suministro),
        "monto_a_cobrar_antes": str(datos.monto_a_cobrar_antes),
        "monto_a_cobrar_despues": str(datos.monto_a_cobrar_despues),
        "incumplimientos_antes": datos.contador_antes,
        "incumplimientos_despues": datos.contador_despues,
    }
    if mora_resueltas:
        datos_auditoria["alertas_resueltas"] = [str(a) for a in mora_resueltas]
    if mora_nuevas:
        datos_auditoria["alertas_creadas"] = [str(a) for a in mora_nuevas]
    if contraasiento is not None:
        datos_auditoria["asientos"] = [str(contraasiento)]
    if pendiente_a_mano is not None:
        datos_auditoria["asiento_manual_pendiente"] = pendiente_a_mano
    RegistroAuditoria.objects.registrar(
        usuario=quien,
        accion=RegistroAuditoria.Accion.ANULACION_RESOLUCION_SOLICITUD,
        afectados=[s, anulacion] + mora_resueltas + mora_nuevas + ([suministro, evento] if datos.aceptada else []) + ([contraasiento] if contraasiento is not None else []),
        detalle={"cambios": cambios, "datos": datos_auditoria},
    )
    return Anulacion.objects.get(pk=anulacion.pk)


# ---- COM-CNS-SRV: la lista y la ficha ----

ESTADOS_DE_LA_LISTA = (("", "Todos los estados"), ("pendiente", "Pendientes"), ("resueltas", "Resueltas"), ("aceptada", "Aceptadas"), ("rechazada", "Rechazadas"))
TIPOS_DE_LA_LISTA = (("", "Todas las solicitudes"), ("queja", "Quejas"), ("discrepancia", "Discrepancias"))
FilaDeSolicitud = namedtuple("FilaDeSolicitud", "solicitud id codigo tipo_texto entrega_codigo contrato_codigo cliente fecha_solicitud fecha_entrega cantidad indemnizacion estado estado_texto pendiente")
PaginaDeSolicitudes = namedtuple("PaginaDeSolicitudes", "pagina filas filtros pendientes tipos estados")


def _fecha(texto):
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def _numero(texto):
    """«SR-0012», «sr 12» o «12» → 12; `None` si no hay dígitos."""
    digitos = "".join(c for c in (texto or "") if c.isdigit())
    return int(digitos) if digitos else None


@dataclass
class FiltrosDeSolicitudes:
    """Regla 2 de COM-CNS-SRV: tipo, estado, cliente (texto), contrato (número), rango de fechas de la solicitud, número de la solicitud (D-69, punto 16) y, solo para el Gerente, Vendedor."""

    tipo: str = ""
    estado: str = ""
    cliente: str = ""
    contrato: str = ""
    desde: date | None = None
    hasta: date | None = None
    numero: str = ""
    vendedor: str = ""

    @classmethod
    def desde_get(cls, get):
        return cls(
            tipo=(get.get("tipo") or "").strip(),
            estado=(get.get("estado") or "").strip(),
            cliente=(get.get("cliente") or "").strip(),
            contrato=(get.get("contrato") or "").strip(),
            desde=_fecha(get.get("desde")),
            hasta=_fecha(get.get("hasta")),
            numero=(get.get("numero") or "").strip(),
            vendedor=(get.get("vendedor") or "").strip(),
        )

    @property
    def hay_filtros(self):
        return any((self.tipo, self.estado, self.cliente, self.contrato, self.desde, self.hasta, self.numero, self.vendedor))


def pendientes_para(usuario):
    """El contador de la pestaña y del panel: las solicitudes pendientes, solo para el Gerente activo (`None` para los demás). Una consulta."""
    if not getattr(usuario, "is_active", False) or rol_de(usuario) != GERENTE:
        return None
    return SolicitudRevision.objects.filter(estado_solicitud=Estado.PENDIENTE).count()


def lista_de_solicitudes(actor, filtros=None, pagina=1):
    """COM-CNS-SRV, reglas 1 y 2 (y el paso 2 de COM-EVL-DSC y COM-RSV-QJA): las solicitudes del alcance del actor (el Gerente, todas; el Vendedor, las de sus contratos) con los filtros. Primero las
    pendientes, de la más antigua a la más reciente; después las resueltas, de la resolución más reciente a la más antigua. De a 50 y sin consultas por fila."""
    actor = _exigir_lector(actor)
    f = filtros or FiltrosDeSolicitudes()
    consulta = SolicitudRevision.objects.filter(entrega__contrato_entrega_id__in=Contrato.objects.en_alcance_de(actor).values("pk"))
    if f.tipo in (Tipo.QUEJA, Tipo.DISCREPANCIA):
        consulta = consulta.filter(tipo_solicitud=f.tipo)
    if f.estado == "resueltas":
        consulta = consulta.exclude(estado_solicitud=Estado.PENDIENTE)
    elif f.estado in Estado.values:
        consulta = consulta.filter(estado_solicitud=f.estado)
    if f.cliente:
        cliente = Q(entrega__contrato_entrega__cliente__razon_social_cliente__icontains=f.cliente)
        cliente |= Q(entrega__contrato_entrega__cliente__nombre_cliente__icontains=f.cliente) | Q(entrega__contrato_entrega__cliente__apellido_cliente__icontains=f.cliente)
        consulta = consulta.filter(cliente | Q(entrega__contrato_entrega__cliente__cuit_cliente__icontains="".join(c for c in f.cliente if c.isdigit()) or "no-es-un-cuit"))
    if _numero(f.contrato) is not None:
        consulta = consulta.filter(entrega__contrato_entrega__numero=_numero(f.contrato))
    if f.desde:
        consulta = consulta.filter(fecha_solicitud__gte=f.desde)
    if f.hasta:
        consulta = consulta.filter(fecha_solicitud__lte=f.hasta)
    if _numero(f.numero) is not None:
        consulta = consulta.filter(numero=_numero(f.numero))
    if f.vendedor.isdigit() and rol_de(actor) == GERENTE:
        consulta = consulta.filter(entrega__contrato_entrega__vendedor_id=int(f.vendedor))
    lineas = LineaDiscrepancia.objects.filter(discrepancia_id=OuterRef("pk")).values("discrepancia_id").annotate(c=Count("pk")).values("c")
    detalles = Queja.detalles.through.objects.filter(queja_id=OuterRef("pk")).values("queja_id").annotate(c=Count("pk")).values("c")
    consulta = (
        consulta.select_related("entrega__contrato_entrega__cliente", "queja")
        .annotate(
            cantidad=Coalesce(Subquery(lineas), Subquery(detalles), 0, output_field=IntegerField()),
            grupo=Case(When(estado_solicitud=Estado.PENDIENTE, then=0), default=1),
            clave_pendiente=Case(When(estado_solicitud=Estado.PENDIENTE, then=F("fecha_solicitud")), default=None, output_field=DateField()),
            clave_resuelta=Case(When(estado_solicitud=Estado.PENDIENTE, then=None), default=F("fecha_resolucion"), output_field=DateField()),
        )
        .order_by("grupo", F("clave_pendiente").asc(nulls_last=True), F("clave_resuelta").desc(nulls_last=True), "pk")
    )
    paginador = Paginator(consulta, POR_PAGINA)
    pagina_actual = paginador.get_page(pagina)
    filas = []
    for s in pagina_actual:
        if s.tipo_solicitud == Tipo.QUEJA:
            tipo_texto = f"Queja · {TEXTO_DE_LA_QUEJA[s.queja.tipo_queja]}"
        else:
            tipo_texto = "Discrepancia de cantidad"
        contrato = s.entrega.contrato_entrega
        filas.append(
            FilaDeSolicitud(
                solicitud=s,
                id=s.pk,
                codigo=s.codigo,
                tipo_texto=tipo_texto,
                entrega_codigo=s.entrega.codigo,
                contrato_codigo=contrato.codigo,
                cliente=contrato.cliente.nombre_visible,
                fecha_solicitud=s.fecha_solicitud,
                fecha_entrega=s.entrega.fecha_resolucion_orden,
                cantidad=s.cantidad,
                indemnizacion=s.monto_indemnizacion if s.estado_solicitud == Estado.ACEPTADA else None,
                estado=s.estado_solicitud,
                estado_texto=s.get_estado_solicitud_display(),
                pendiente=s.estado_solicitud == Estado.PENDIENTE,
            )
        )
    return PaginaDeSolicitudes(pagina_actual, filas, f, pendientes_para(actor), TIPOS_DE_LA_LISTA, ESTADOS_DE_LA_LISTA)


@dataclass
class FichaDeSolicitud:
    """COM-CNS-SRV, reglas 3 a 5 y 7, y el paso 4 de COM-EVL-DSC y COM-RSV-QJA: todo para ver (y, el Gerente, decidir) una solicitud."""

    lectura: Lectura
    codigo: str
    tipo_texto: str
    es_gerente: bool
    perdidas: list
    intentos: list
    intento_en_plazo: bool
    historial: list
    vista_previa: ResumenDeResolucion | None
    cuenta_como_incumplimiento: bool
    gerente_que_resolvio: str
    puede_evaluar: bool
    puede_anular: bool
    puede_reenviar: bool
    puede_imprimir: bool

    @property
    def solicitud(self):
        return self.lectura.solicitud


def ficha_de_solicitud(actor, solicitud_id, hoy=None):
    """La ficha de una solicitud del alcance del actor (`PermissionDenied` si es de otro contrato; `Http404` si no existe). Al Gerente con la solicitud pendiente le suma la vista previa del
    panel (el monto que correspondería, cómo se aplicaría, los incumplimientos y si el contrato se resolvería); al Vendedor, solo lectura."""
    actor, previa = _del_alcance(actor, solicitud_id)
    hoy = hoy or stock.hoy()
    lectura = _leer(solicitud_id, hoy)
    s, entrega = lectura.solicitud, lectura.entrega
    from comercial.servicios import concrecion  # adentro: `concrecion` importa este módulo

    intentos = concrecion.intentos_fallidos([entrega.pk])[entrega.pk]
    en_plazo = False
    if s.tipo_solicitud == Tipo.QUEJA and s.tipo_queja == Queja.TipoDeQueja.RETRASO:  # 4b
        en_plazo = any(i.fecha_programada <= l.fecha_periodo + timedelta(days=l.plazo) for i in intentos for l in lectura.lineas)
    es_gerente = rol_de(actor) == GERENTE
    pendiente = s.estado_solicitud == Estado.PENDIENTE
    resuelta = not pendiente
    return FichaDeSolicitud(
        lectura=lectura,
        codigo=s.codigo,
        tipo_texto=_texto_del_tipo(s),
        es_gerente=es_gerente,
        perdidas=[(m.cant_merma, m.get_causa_display(), m.descripcion_evento) for m in Merma.objects.filter(orden_id=entrega.pk).order_by("pk")],
        intentos=intentos,
        intento_en_plazo=en_plazo,
        historial=list(Anulacion.objects.filter(solicitud_id=s.pk).select_related("usuario", "gerente_anulado").order_by("-fecha_anulacion", "-pk")),
        vista_previa=_evaluar(lectura, DatosDeResolucion(decision=ACEPTAR)) if es_gerente and pendiente else None,
        cuenta_como_incumplimiento=s.estado_solicitud == Estado.ACEPTADA,
        gerente_que_resolvio=_nombre(s.gerente),
        puede_evaluar=es_gerente and pendiente,
        puede_anular=es_gerente and resuelta,
        puede_reenviar=resuelta and s.estado_aviso_cliente == AVISO.PENDIENTE_ENVIO and bool(lectura.suministro.cliente.email_cliente),
        puede_imprimir=resuelta and s.estado_aviso_cliente == AVISO.SIN_CORREO,
    )


FilaDeSolicitudDelContrato = namedtuple("FilaDeSolicitudDelContrato", "id codigo fecha entrega_codigo tipo_texto estado estado_texto cuenta_como_incumplimiento")


def solicitudes_del_suministro(suministro_id):
    """La sección «Solicitudes de revisión» de la ficha del suministro (regla 8 de COM-CNS-SUM): número, fecha y entrega, tipo, estado y «Cuenta como incumplimiento», de la más reciente a la más antigua.
    Una consulta."""
    return [
        FilaDeSolicitudDelContrato(
            s.pk,
            s.codigo,
            s.fecha_solicitud,
            s.entrega.codigo,
            f"Queja · {TEXTO_DE_LA_QUEJA[s.queja.tipo_queja]}" if s.tipo_solicitud == Tipo.QUEJA else "Discrepancia de cantidad",
            s.estado_solicitud,
            s.get_estado_solicitud_display(),
            s.estado_solicitud == Estado.ACEPTADA,
        )
        for s in SolicitudRevision.objects.filter(entrega__contrato_entrega_id=suministro_id).select_related("entrega", "queja").order_by("-fecha_solicitud", "-numero")
    ]


def enlaces_de_alertas(usuario, alertas_de_solicitudes):
    """`registrar_enlace_de_alerta` para `comercial_discrepancia_entrega` y `comercial_queja` (1a de COM-EVL-DSC y de COM-RSV-QJA; D-62): solo el Gerente la recibe; lleva a la ficha de la solicitud con el
    detalle «SR-0012 · Discrepancia · pendiente» (o la decisión, si ya se resolvió). Una consulta para toda la lista. Reemplaza a `concrecion.enlaces_de_alertas`."""
    alertas_de_solicitudes = list(alertas_de_solicitudes)
    if not alertas_de_solicitudes or rol_de(usuario) != GERENTE:
        return {}
    enlaces = {}
    vinculos = AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_de_solicitudes], solicitud__isnull=False).select_related("solicitud")
    for vinculo in vinculos:
        s = vinculo.solicitud
        enlaces[vinculo.alerta_id] = Enlace(reverse("comercial:solicitud", args=[s.pk]), f"{s.codigo} · {_texto_corto_del_tipo(s).capitalize()} · {s.estado_solicitud}")
    return enlaces
