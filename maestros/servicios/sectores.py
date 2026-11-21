# Servicios de SectorProduccion (MAE-03): alta (PROD-ALT-SCT), modificación con su reactivación y su vuelta a servicio
# (PROD-MOD-SCT), baja (PROD-BAJ-SCT) y consulta (PROD-CNS-SCT). Cada caso de uso es una función dentro de
# ``transaction.atomic()`` y audita con el formato de D-36 (docs/patrones/auditoria.md). D-37: un archivo por entidad raíz.
# Casos de uso: docs/casos_de_uso/maestros/sectores.md; contrato de los puntos de extensión: docs/api/extensiones_de_maestros.md.
#
# Orden de los bloqueos (D-30, D-40; siempre ``FOR NO KEY UPDATE``): 1) el invernadero (``bloquear_invernadero_activo``);
# 2) que quien actúa siga activo y a cargo; 3) el sector, releído; 4) recién después, lo que bloqueen los registrantes de
# ``maestros.extensiones`` (filas de las apps altas). El efecto de la baja de un invernadero bloquea sus sectores en orden
# de id, después del invernadero.

import re
from collections import namedtuple

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404

from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from maestros import extensiones
from maestros.extensiones import Aviso
from maestros.models import Invernadero, SectorProduccion, TipoEtapa, Variedad
from maestros.servicios.invernaderos import (
    _actor_sigue_activo,
    _error_general,
    _tiene_contenido,
    bloquear_invernadero_activo,
)

Estado = SectorProduccion.Estado

# Agujeros de un sector, calculados y no guardados (regla 5 de PROD-ALT-SCT, MD-74).
Agujeros = namedtuple("Agujeros", "total ocupados comprometidos libres")
# Un grupo de la consulta: los sectores de un tipo de etapa con su cantidad de sectores y de agujeros (regla 2 de PROD-CNS-SCT).
GrupoDeSectores = namedtuple("GrupoDeSectores", "tipo_etapa sectores cantidad_de_sectores cantidad_de_agujeros")
# Una fila de la tarjeta «Capacidad» de la ficha (regla 3 de PROD-CNS-INV): por tipo de etapa.
CapacidadPorEtapa = namedtuple("CapacidadPorEtapa", "tipo_etapa agujeros libres cantidad_de_sectores")

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"
ACCION_VOLVER_A_SERVICIO = "volver_a_servicio"

LARGO_DEL_NOMBRE = SectorProduccion._meta.get_field("nombre_sector").max_length
MAXIMO_DE_AGUJEROS = 2_147_483_647  # el de la columna entera de la base
MENSAJE_NOMBRE_REPETIDO = "Ya hay un sector con ese nombre en este invernadero."
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
_ENTERO = re.compile(r"^\d+$", re.ASCII)


class FaltaConfirmarAdvertencia(Exception):
    """Regla 4 de PROD-MOD-SCT y de PROD-BAJ-SCT: hay una advertencia que la persona todavía no confirmó. No se cambió nada.
    ``avisos`` es la lista de ``maestros.extensiones.Aviso`` (``texto``, ``cantidad``)."""

    def __init__(self, avisos):
        super().__init__("Hay una advertencia sin confirmar.")
        self.avisos = avisos


# ---- validación y bloqueos comunes ----


def _exigir_agronomo(actor):
    """Precondición a de ALT, MOD y BAJ: ``actor`` es un Agrónomo con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise PermissionDenied("Solo un Agrónomo activo puede gestionar sectores.")


def _exigir_quien_consulta(actor):
    """Precondición a de PROD-CNS-SCT: Agrónomo o Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        raise PermissionDenied("Tu cuenta no tiene acceso a los sectores.")


def _entero_positivo(valor):
    """El entero mayor que cero que representa ``valor`` (un entero o un texto de dígitos), o ``None``."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _ENTERO.match(valor.strip()):
        numero = int(valor.strip())
    else:
        return None
    return numero if 0 < numero <= MAXIMO_DE_AGUJEROS else None


def _datos_validos(nombre, tipo_etapa_id, cant_agujeros_total):
    """Regla 2, 3 y 4 de PROD-ALT-SCT sin tocar los datos del invernadero: ``(nombre recortado, TipoEtapa, cantidad)``.
    Junta TODOS los errores en un solo ``ValidationError`` con un error por campo (patrón ABM, §2)."""
    errores = {}
    nombre = (nombre or "").strip() if isinstance(nombre, str) or nombre is None else str(nombre).strip()
    if not nombre:
        errores["nombre"] = [ValidationError("Ingresá el nombre del sector.", code="obligatorio")]
    elif not _tiene_contenido(nombre):
        errores["nombre"] = [ValidationError("Ingresá un texto con al menos una letra o un número.", code="sin_contenido")]
    elif len(nombre) > LARGO_DEL_NOMBRE:
        errores["nombre"] = [
            ValidationError(f"Usá como máximo {LARGO_DEL_NOMBRE} caracteres.", code="demasiado_largo")
        ]

    tipo = None
    if tipo_etapa_id in (None, ""):
        errores["tipo_etapa"] = [ValidationError("Elegí el tipo de etapa.", code="obligatorio")]
    else:
        try:
            tipo = TipoEtapa.objects.filter(pk=int(tipo_etapa_id)).first()
        except (TypeError, ValueError):
            tipo = None
        if tipo is None:
            errores["tipo_etapa"] = [ValidationError("Elegí uno de los tipos de etapa.", code="no_existe")]

    cantidad = _entero_positivo(cant_agujeros_total)
    if cant_agujeros_total is None or (isinstance(cant_agujeros_total, str) and not cant_agujeros_total.strip()):
        errores["cant_agujeros_total"] = [ValidationError("Ingresá la cantidad de agujeros.", code="obligatorio")]
    elif cantidad is None:
        errores["cant_agujeros_total"] = [
            ValidationError("Ingresá un número entero mayor que 0.", code="cantidad_invalida")
        ]
    if errores:
        raise ValidationError(errores)
    return nombre, tipo, cantidad


def _bloquear_a_cargo(actor, invernadero_id):
    """El invernadero bloqueado (404 si no existe, ``invernadero_inactivo`` si está inactivo) con la verificación, ya
    bloqueado, de que quien actúa sigue activo y está a cargo (precondición b y regla 1 de PROD-ALT-SCT)."""
    invernadero = bloquear_invernadero_activo(invernadero_id)
    _actor_sigue_activo(actor)
    if invernadero.agronomo_id != actor.pk:
        raise PermissionDenied("Este invernadero no está a tu cargo.")
    return invernadero


def _bloquear_sector_a_cargo(actor, sector_id):
    """``(invernadero, sector)`` bloqueados en el orden invernadero -> sector, el sector releído. Hay que llamarla dentro de
    ``transaction.atomic()``. 404 si el sector no existe."""
    invernadero_id = SectorProduccion.objects.filter(pk=sector_id).values_list("invernadero_id", flat=True).first()
    if invernadero_id is None:
        raise Http404("No existe ese sector.")
    invernadero = _bloquear_a_cargo(actor, invernadero_id)
    # ``of=("self",)``: solo la fila del sector, no la del tipo de etapa que se trae con ``select_related``.
    sector = (
        SectorProduccion.objects.select_for_update(no_key=True, of=("self",))
        .select_related("tipo_etapa")
        .filter(pk=sector_id)
        .first()
    )
    if sector is None:
        raise Http404("No existe ese sector.")
    return invernadero, sector


def _nombre_repetido(invernadero_id, nombre, excluir_pk=None):
    """True si el invernadero ya tiene un sector con ese nombre, sin distinguir mayúsculas y bajas incluidas (regla 2 de
    PROD-ALT-SCT). La consulta usa la misma expresión que la restricción de la base."""
    sectores = SectorProduccion.objects.filter(invernadero_id=invernadero_id).annotate(
        _minuscula=Lower("nombre_sector")
    )
    if excluir_pk is not None:
        sectores = sectores.exclude(pk=excluir_pk)
    return sectores.filter(_minuscula=Lower(Value(nombre))).exists()


def _error_nombre_repetido():
    """El error de campo de un nombre repetido."""
    return ValidationError({"nombre": [ValidationError(MENSAJE_NOMBRE_REPETIDO, code="nombre_repetido")]})


def _es_nombre_repetido(error):
    """True si un ``IntegrityError`` es de la restricción única del nombre."""
    return "sector_nombre_unico_por_invernadero" in str(error)


def _cambio_de_estado(sector, antes, despues):
    """El detalle de auditoría (D-36) de un cambio de estado."""
    return {"cambios": {"estado": {"antes": antes, "despues": despues}}}


# ---- avisos de la regla 4 ----


def _hay_otro_activo_del_tipo(sector):
    """True si el invernadero tiene otro sector ACTIVO del mismo tipo que ``sector``."""
    return (
        SectorProduccion.objects.filter(
            invernadero_id=sector.invernadero_id, tipo_etapa_id=sector.tipo_etapa_id, estado_sector=Estado.ACTIVO
        )
        .exclude(pk=sector.pk)
        .exists()
    )


def avisos_de_cambio_de_tipo(invernadero, tipo_etapa):
    """Regla 4 de PROD-MOD-SCT y de PROD-BAJ-SCT: lo que queda sin un sector activo de ``tipo_etapa``. Junta los avisos
    de los registrantes (lotes que todavía deben pasar por la etapa y siembras a realizar, de `produccion`) y el propio de
    `maestros`: las variedades activas cuyo ciclo incluye ese tipo y que dejan de poder sembrarse."""
    avisos = extensiones.avisos_registrados_de_cambio_de_tipo(invernadero, tipo_etapa)
    variedades = (
        Variedad.objects.filter(estado_variedad=Variedad.Estado.ACTIVO, ciclo__etapas__tipo_etapa=tipo_etapa)
        .select_related("cultivo")
        .distinct()
        .order_by("cultivo__nombre_cultivo", "nombre_variedad")
    )
    nombres = [str(variedad) for variedad in variedades]
    if nombres:
        avisos.append(
            Aviso(f"Variedades que dejan de poder sembrarse en el invernadero: {', '.join(nombres)}.", len(nombres))
        )
    return avisos


def _avisos_del_ultimo_sector(sector, invernadero):
    """Los avisos completos cuando ``sector`` es el último sector activo de su tipo: el encabezado, la recomendación y lo
    que calcula ``avisos_de_cambio_de_tipo``."""
    encabezado = Aviso(
        f"{sector.nombre_sector} es el último sector activo de {sector.tipo_etapa.nombre_etapa} de "
        f"{invernadero.nombre_invernadero}. Se recomienda registrar otro sector de esa etapa o cambiar el tipo de uno "
        "existente.",
        None,
    )
    return [encabezado, *avisos_de_cambio_de_tipo(invernadero, sector.tipo_etapa)]


# ---- casos de uso ----


def alta_sector(actor, invernadero_id, *, nombre, tipo_etapa_id, cant_agujeros_total):
    """PROD-ALT-SCT: crea un sector activo en un invernadero y lo devuelve.

    - Precondición a: ``actor`` es un Agrónomo activo. Precondición b y regla 1: el invernadero está activo y a su cargo
      (404 si no existe, ``invernadero_inactivo`` si está inactivo, ``PermissionDenied`` si es de otro).
    - Precondición c y regla 2: nombre obligatorio, con contenido, de hasta 40 caracteres y único en el invernadero sin
      distinguir mayúsculas (bajas incluidas). Regla 3: tipo del catálogo. Regla 4: entero mayor que cero.
    - Postcondición a: queda «activo». Postcondición b: la marca «sin sectores» deja de mostrarse (``tiene_sectores``).
    - Postcondición c, D-22 y D-36: un registro ``alta_sector`` en la misma transacción.
    """
    _exigir_agronomo(actor)
    nombre, tipo, cantidad = _datos_validos(nombre, tipo_etapa_id, cant_agujeros_total)
    with transaction.atomic():
        invernadero = _bloquear_a_cargo(actor, invernadero_id)
        if _nombre_repetido(invernadero.pk, nombre):
            raise _error_nombre_repetido()
        try:
            with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
                sector = SectorProduccion.objects.create(
                    invernadero=invernadero,
                    tipo_etapa=tipo,
                    nombre_sector=nombre,
                    cant_agujeros_total=cantidad,
                    estado_sector=Estado.ACTIVO,
                )
        except IntegrityError as error:
            if _es_nombre_repetido(error):
                raise _error_nombre_repetido() from error
            raise
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_SECTOR,
            afectados=[sector, invernadero],
            detalle={
                "cambios": {
                    "nombre": {"antes": None, "despues": nombre},
                    "tipo_etapa": {"antes": None, "despues": referencia(tipo)},
                    "cant_agujeros_total": {"antes": None, "despues": cantidad},
                    "estado": {"antes": None, "despues": Estado.ACTIVO.value},
                }
            },
        )
    return sector


def modificar_sector(actor, sector_id, *, nombre, tipo_etapa_id, cant_agujeros_total, advertencia_confirmada=False):
    """PROD-MOD-SCT: actualiza el nombre, el tipo de etapa o la cantidad de agujeros de un sector y lo devuelve.

    - Precondiciones a y b como en el alta; precondición c: el nombre nuevo no se repite en el invernadero.
    - Regla 1: el nombre, siempre; el total sube siempre y baja hasta ocupados + comprometidos (``por_debajo_del_minimo``);
      el tipo solo si no hay agujeros ocupados ni comprometidos (``tipo_bloqueado``); el invernadero no se cambia.
    - Regla 2: un sector activo o fuera de servicio se modifica y conserva su estado. Regla 3: uno dado de baja no
      (``sector_inactivo``): solo se reactiva.
    - Regla 4: si el cambio de tipo deja al invernadero sin sectores activos del tipo anterior y no viene
      ``advertencia_confirmada``, lanza ``FaltaConfirmarAdvertencia`` y no cambia nada. Se calcula después de bloquear.
    - D-28: sin cambios no se escribe ni se audita. Postcondición d: ``modificacion_sector`` con lo que cambió.
    """
    _exigir_agronomo(actor)
    nombre, tipo, cantidad = _datos_validos(nombre, tipo_etapa_id, cant_agujeros_total)
    with transaction.atomic():
        invernadero, sector = _bloquear_sector_a_cargo(actor, sector_id)
        if sector.estado_sector == Estado.INACTIVO:
            raise _error_general("El sector está dado de baja: solo se puede reactivar.", "sector_inactivo")
        errores = {}
        if _nombre_repetido(invernadero.pk, nombre, excluir_pk=sector.pk):
            errores["nombre"] = [ValidationError(MENSAJE_NOMBRE_REPETIDO, code="nombre_repetido")]
        agujeros = agujeros_de([sector])[sector.pk]
        en_uso = agujeros.ocupados + agujeros.comprometidos
        if cantidad < en_uso:
            errores["cant_agujeros_total"] = [
                ValidationError(
                    f"Hay {agujeros.ocupados} agujeros ocupados y {agujeros.comprometidos} comprometidos: "
                    f"como mínimo {en_uso}.",
                    code="por_debajo_del_minimo",
                )
            ]
        cambia_el_tipo = tipo.pk != sector.tipo_etapa_id
        if cambia_el_tipo and en_uso:
            errores["tipo_etapa"] = [
                ValidationError(
                    "No se puede cambiar mientras el sector tenga agujeros ocupados o comprometidos.",
                    code="tipo_bloqueado",
                )
            ]
        if errores:
            raise ValidationError(errores)

        cambios = {}
        if nombre != sector.nombre_sector:
            cambios["nombre"] = {"antes": sector.nombre_sector, "despues": nombre}
        if cambia_el_tipo:
            cambios["tipo_etapa"] = {"antes": referencia(sector.tipo_etapa), "despues": referencia(tipo)}
        if cantidad != sector.cant_agujeros_total:
            cambios["cant_agujeros_total"] = {"antes": sector.cant_agujeros_total, "despues": cantidad}
        if not cambios:
            return sector
        if (
            cambia_el_tipo
            and sector.estado_sector == Estado.ACTIVO
            and not advertencia_confirmada
            and not _hay_otro_activo_del_tipo(sector)
        ):
            raise FaltaConfirmarAdvertencia(_avisos_del_ultimo_sector(sector, invernadero))

        sector.nombre_sector, sector.tipo_etapa, sector.cant_agujeros_total = nombre, tipo, cantidad
        try:
            with transaction.atomic():
                sector.save(update_fields=["nombre_sector", "tipo_etapa", "cant_agujeros_total"])
        except IntegrityError as error:
            if _es_nombre_repetido(error):
                raise _error_nombre_repetido() from error
            raise
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_SECTOR,
            afectados=[sector, invernadero],
            detalle={"cambios": cambios},
        )
    return sector


def reactivar_sector(actor, sector_id):
    """PROD-MOD-SCT (postcondición c y reglas 3 y 5): reactiva un sector dado de baja, sin más validaciones, y lo devuelve.
    Solo con el invernadero activo. Uno que no está dado de baja se rechaza con ``sector_no_inactivo``. Se audita como
    ``reactivacion_sector``."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        invernadero, sector = _bloquear_sector_a_cargo(actor, sector_id)
        if sector.estado_sector != Estado.INACTIVO:
            raise _error_general("El sector no está dado de baja.", "sector_no_inactivo")
        sector.estado_sector = Estado.ACTIVO
        sector.save(update_fields=["estado_sector"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_SECTOR,
            afectados=[sector, invernadero],
            detalle=_cambio_de_estado(sector, Estado.INACTIVO.value, Estado.ACTIVO.value),
        )
    return sector


def volver_a_servicio_sector(actor, sector_id):
    """PROD-MOD-SCT (postcondiciones b y d, regla 5): vuelve a activar un sector fuera de servicio, sin validaciones.

    Cerrar el registro «Fuera de servicio» y escribir la bitácora es de PRD-04: lo hacen los registrantes de
    ``registrar_efecto_de_vuelta_a_servicio``, dentro de esta transacción y con el sector ya activo. Se audita como
    ``modificacion_sector`` con el cambio de estado."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        invernadero, sector = _bloquear_sector_a_cargo(actor, sector_id)
        if sector.estado_sector != Estado.FUERA_DE_SERVICIO:
            raise _error_general("El sector no está fuera de servicio.", "sector_no_fuera_de_servicio")
        sector.estado_sector = Estado.ACTIVO
        sector.save(update_fields=["estado_sector"])
        extensiones.aplicar_efectos_de_vuelta_a_servicio(actor, sector)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_SECTOR,
            afectados=[sector, invernadero],
            detalle=_cambio_de_estado(sector, Estado.FUERA_DE_SERVICIO.value, Estado.ACTIVO.value),
        )
    return sector


def _errores_de_impedimentos(impedimentos):
    """Un ``ValidationError`` general con UN error por impedimento (código, qué pasa y cómo resolverlo)."""
    return ValidationError(
        {
            NON_FIELD_ERRORS: [
                ValidationError(f"{i.texto} {i.como_resolver}", code=i.codigo) for i in impedimentos
            ]
        }
    )


def impedimentos_para_baja(actor, sector_id):
    """PROD-BAJ-SCT, reglas 2 y 3: los impedimentos de la baja para la ventana de confirmación. Solo lectura: no bloquea,
    no cambia nada y no audita; ``baja_sector`` los vuelve a verificar con todo bloqueado. Un sector ya dado de baja se
    rechaza con ``sector_inactivo``."""
    _exigir_agronomo(actor)
    sector = obtener_sector(actor, sector_id)
    if sector.estado_sector == Estado.INACTIVO:
        raise _error_general("El sector ya está dado de baja.", "sector_inactivo")
    return impedimentos_de_baja_de_sector(sector)


def avisos_para_baja(actor, sector_id):
    """PROD-BAJ-SCT, regla 4: las advertencias de la baja para mostrarlas en la ventana ANTES de confirmar (la ventana es la
    confirmación, como ``ultimoAviso`` del prototipo). Solo lectura: no bloquea ni audita. Lista vacía si el sector no es el
    último activo de su tipo; ``baja_sector`` los vuelve a calcular con todo bloqueado."""
    _exigir_agronomo(actor)
    sector = obtener_sector(actor, sector_id)
    if sector.estado_sector != Estado.ACTIVO or _hay_otro_activo_del_tipo(sector):
        return []
    return _avisos_del_ultimo_sector(sector, sector.invernadero)


def baja_sector(actor, sector_id, *, advertencia_confirmada=False):
    """PROD-BAJ-SCT: da de baja lógica un sector activo o fuera de servicio y lo devuelve.

    - Precondiciones a y b como en el alta; c: activo o fuera de servicio (``sector_inactivo``).
    - Precondiciones d y e y reglas 2 y 3: los impedimentos de los registrantes (lotes y órdenes de `produccion`, hardware
      de `iot`); se informan TODOS juntos y no se cambia nada. Van antes que la advertencia.
    - Regla 4: si deja al invernadero sin sectores activos de ese tipo y no viene ``advertencia_confirmada``,
      ``FaltaConfirmarAdvertencia``. Un sector fuera de servicio no es «activo»: no la dispara.
    - Postcondición a: queda «inactivo» (regla 5: deja de contar como capacidad). Postcondición b: los registrantes de
      ``registrar_efecto_de_baja_de_sector`` cierran el registro «Fuera de servicio» (PRD-04).
    - Postcondición c y D-36: ``baja_sector`` con el cambio de estado.
    """
    _exigir_agronomo(actor)
    with transaction.atomic():
        invernadero, sector = _bloquear_sector_a_cargo(actor, sector_id)
        if sector.estado_sector == Estado.INACTIVO:
            raise _error_general("El sector ya está dado de baja.", "sector_inactivo")
        impedimentos = impedimentos_de_baja_de_sector(sector)
        if impedimentos:
            raise _errores_de_impedimentos(impedimentos)
        if (
            sector.estado_sector == Estado.ACTIVO
            and not advertencia_confirmada
            and not _hay_otro_activo_del_tipo(sector)
        ):
            raise FaltaConfirmarAdvertencia(_avisos_del_ultimo_sector(sector, invernadero))
        antes = sector.estado_sector
        sector.estado_sector = Estado.INACTIVO
        sector.save(update_fields=["estado_sector"])
        extensiones.aplicar_efectos_de_baja_de_sector(actor, sector)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_SECTOR,
            afectados=[sector, invernadero],
            detalle=_cambio_de_estado(sector, antes, Estado.INACTIVO.value),
        )
    return sector


def efecto_de_baja_de_invernadero(actor, invernadero):
    """Postcondición f de PROD-BAJ-INV: al dar de baja el invernadero, sus sectores activos o fuera de servicio pasan a
    inactivos, con un registro ``baja_sector`` por sector. Se registra en ``maestros.extensiones.registrar_efecto_de_baja``
    desde ``MaestrosConfig.ready()``; corre dentro de la transacción de la baja, con el invernadero ya bloqueado: bloquea
    los sectores en orden de id (D-40). Un sector ya dado de baja no cambia y no se audita. Reactivar el invernadero no los
    reactiva (regla 6 de PROD-BAJ-INV): los reactiva el Agrónomo."""
    a_dar_de_baja = (
        SectorProduccion.objects.select_for_update(no_key=True, of=("self",))
        .filter(invernadero=invernadero, estado_sector__in=[Estado.ACTIVO, Estado.FUERA_DE_SERVICIO])
        .order_by("id")
    )
    for sector in list(a_dar_de_baja):
        antes = sector.estado_sector
        sector.estado_sector = Estado.INACTIVO
        sector.save(update_fields=["estado_sector"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_SECTOR,
            afectados=[sector],
            detalle=_cambio_de_estado(sector, antes, Estado.INACTIVO.value),
        )


# ---- consulta (PROD-CNS-SCT) ----


def consultar_sectores(actor, invernadero_id):
    """PROD-CNS-SCT: los sectores del invernadero ``invernadero_id``, por nombre, dentro del alcance de ``actor``.

    - Precondición a: Agrónomo o Gerente activos. Regla 1 y D-28: el Agrónomo, solo los invernaderos activos a su cargo; el
      Gerente, cualquiera, en solo lectura. Un invernadero que no existe da 404; uno fuera del alcance, ``PermissionDenied``.
    - Regla 7 y SEG-14: no audita.
    """
    _exigir_quien_consulta(actor)
    if not Invernadero.objects.filter(pk=invernadero_id).exists():
        raise Http404("No existe ese invernadero.")
    if not Invernadero.objects.en_alcance_de(actor).filter(pk=invernadero_id).exists():
        raise PermissionDenied("Este invernadero no está a tu cargo.")
    return (
        SectorProduccion.objects.filter(invernadero_id=invernadero_id)
        .select_related("tipo_etapa", "invernadero")
        .order_by(Lower("nombre_sector"), "id")
    )


def obtener_sector(actor, sector_id):
    """PROD-CNS-SCT: el sector ``sector_id`` si está dentro del alcance de ``actor`` (404 si no existe, 403 fuera del
    alcance, D-28). No audita."""
    _exigir_quien_consulta(actor)
    sector = get_object_or_404(SectorProduccion.objects.select_related("tipo_etapa", "invernadero"), pk=sector_id)
    if not SectorProduccion.objects.en_alcance_de(actor).filter(pk=sector.pk).exists():
        raise PermissionDenied("Este invernadero no está a tu cargo.")
    return sector


def agrupar_sectores(sectores):
    """PROD-CNS-SCT regla 2: ``(grupos, dados_de_baja)``. Los grupos son uno por tipo de etapa que tenga sectores (activos o
    fuera de servicio), en el orden de las etapas, con su cantidad de sectores y de agujeros; los dados de baja van aparte."""
    por_tipo, dados_de_baja = {}, []
    for sector in sorted(sectores, key=lambda s: (s.nombre_sector.lower(), s.pk)):
        if sector.estado_sector == Estado.INACTIVO:
            dados_de_baja.append(sector)
        else:
            por_tipo.setdefault(sector.tipo_etapa, []).append(sector)
    grupos = [
        GrupoDeSectores(tipo, lista, len(lista), sum(s.cant_agujeros_total for s in lista))
        for tipo, lista in sorted(por_tipo.items(), key=lambda par: par[0].puesto_global)
    ]
    return grupos, dados_de_baja


def capacidad_del_invernadero(sectores, agujeros):
    """PROD-CNS-INV regla 3: por tipo de etapa, los agujeros totales, los libres y la cantidad de sectores. Cuentan los
    sectores activos y los fuera de servicio (regla 5 de PROD-BAJ-SCT); los dados de baja no. ``agujeros`` es el resultado de
    ``agujeros_de``."""
    grupos, _ = agrupar_sectores(sectores)
    return [
        CapacidadPorEtapa(
            grupo.tipo_etapa,
            grupo.cantidad_de_agujeros,
            sum(agujeros[s.pk].libres for s in grupo.sectores),
            grupo.cantidad_de_sectores,
        )
        for grupo in grupos
    ]


# ---- apoyo para quienes se enganchan (PRD-01, PRD-02, PRD-04) ----


def bloquear_sectores(invernadero_id, ids):
    """Contrato de los puntos de extensión (docs/api/extensiones_de_maestros.md): quien reserva o libera agujeros bloquea el
    invernadero (``bloquear_invernadero_activo``, que se repite acá sin costo) y después los sectores (``FOR NO KEY UPDATE``,
    en orden de id) y los recibe releídos. Rechaza con ``sector_no_disponible`` un sector que no es del invernadero, que no
    existe, o que está inactivo o fuera de servicio (no recibe plantas ni órdenes). Hay que llamarla dentro de una
    transacción."""
    bloquear_invernadero_activo(invernadero_id)
    ids = set(ids)
    bloqueados = list(
        SectorProduccion.objects.select_for_update(no_key=True, of=("self",))
        .filter(invernadero_id=invernadero_id, pk__in=ids)
        .order_by("id")
    )
    if len(bloqueados) != len(ids) or any(s.estado_sector != Estado.ACTIVO for s in bloqueados):
        raise _error_general(
            "Algún sector no es de este invernadero o no está activo: no recibe plantas ni órdenes.",
            "sector_no_disponible",
        )
    return bloqueados


def agujeros_de(sectores):
    """``{id: Agujeros(total, ocupados, comprometidos, libres)}``: los ocupados y comprometidos los suman todos los registrantes
    de ``registrar_agujeros_de_sector`` (sin ninguno, 0); los libres son el total menos los dos (regla 5 de PROD-ALT-SCT)."""
    sectores = list(sectores)
    usados = extensiones.agujeros_registrados([s.pk for s in sectores])
    return {
        s.pk: Agujeros(
            s.cant_agujeros_total,
            usados[s.pk][0],
            usados[s.pk][1],
            s.cant_agujeros_total - usados[s.pk][0] - usados[s.pk][1],
        )
        for s in sectores
    }


def impedimentos_de_baja_de_sector(sector):
    """Los impedimentos de baja de todos los registrantes, juntos (reglas 2 y 3 de PROD-BAJ-SCT); lista vacía sin ellos."""
    return extensiones.impedimentos_registrados_de_sector(sector)


def contenido_de_sectores(sectores):
    """``{id: [Contenido]}``: lotes, órdenes y hardware de cada sector (regla 3 de PROD-CNS-SCT); vacío sin registrantes."""
    return extensiones.contenido_registrado(sectores)


def perfiles_de_sectores(ids):
    """``{id: perfil o None}``: «Perfil familiar: X» o, con ``None``, «Sin plantas: acepta cualquier perfil»."""
    return extensiones.perfiles_registrados(ids)


# ---- botones (D-30) ----


def _a_cargo(actor, invernadero):
    """True si ``actor`` es el Agrónomo activo a cargo del invernadero activo ``invernadero``."""
    return (
        actor is not None
        and actor.is_active
        and rol_de(actor) == Usuario.Rol.AGRONOMO
        and invernadero.activo
        and invernadero.agronomo_id == actor.pk
    )


def acciones_permitidas(actor, sector):
    """D-30: las acciones que ``actor`` puede hacer sobre ``sector``, un ``frozenset`` (regla 6 de PROD-CNS-SCT). Solo el
    Agrónomo activo a cargo de un invernadero activo; el Gerente y los demás, ninguna. Un sector activo se modifica y se da
    de baja; uno fuera de servicio se modifica, vuelve a servicio o se da de baja; uno dado de baja solo se reactiva.
    Ningún botón lleva a un 403."""
    if not _a_cargo(actor, sector.invernadero):
        return frozenset()
    if sector.estado_sector == Estado.ACTIVO:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    if sector.estado_sector == Estado.FUERA_DE_SERVICIO:
        return frozenset({ACCION_MODIFICAR, ACCION_VOLVER_A_SERVICIO, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})


def puede_agregar_sectores(actor, invernadero):
    """D-30: si ``actor`` ve «Agregar sector» en ``invernadero`` (regla 5 de PROD-CNS-SCT)."""
    return _a_cargo(actor, invernadero)
