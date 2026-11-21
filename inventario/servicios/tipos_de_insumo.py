# Servicios de TipoInsumo, la categoría de insumos (INV-01): alta (CMP-ALT-TIN), modificación con su reactivación (CMP-MOD-TIN),
# baja (CMP-BAJ-TIN) y consulta (CMP-CNS-TIN). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con
# el formato de D-36 (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/inventario/tipos_de_insumo.md. Misma forma que
# ``maestros/servicios/cultivos.py`` (docs/patrones/abm.md).
#
# Bloqueos (siempre ``FOR NO KEY UPDATE``; orden de docs/patrones/stock.md, sección 5: TipoInsumo → Insumo → InsumoInvernadero):
# modificar, reactivar y dar de baja bloquean la fila de la categoría y la releen. Quien agrega un insumo a la categoría (el alta
# y la modificación de insumos) la bloquea ANTES: así una baja simultánea espera, ve el insumo y se rechaza. Si cambia el consumo
# directo, además se bloquean los ``InsumoInvernadero`` de la categoría en orden de id, antes de preguntar por las reservas.
# Dos Agrónomos que renombran a la vez: gana el último, calculado contra lo leído después de bloquear (``modificar_invernadero``,
# D-40); el nombre repetido lo respalda la restricción única de la base.

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Value
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404

from core.models import RegistroAuditoria, Usuario, rol_de
from inventario import extensiones
from inventario.models import Insumo, InsumoInvernadero, TipoInsumo
from inventario.servicios.formato import texto_cantidad
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, _tiene_contenido

Estado = TipoInsumo.Estado
Consumo = TipoInsumo.ConsumoDirecto

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

LARGO_DEL_NOMBRE = TipoInsumo._meta.get_field("nombre_tipo_insumo").max_length
MENSAJE_NOMBRE_REPETIDO = "Ya existe una categoría con ese nombre."
MENSAJE_DEL_SISTEMA = "Es una categoría del sistema: no se modifica ni se da de baja."
RESTRICCION_NOMBRE_UNICO = "tipo_insumo_nombre_unico"


# ---- comunes ----


def _exigir_agronomo(actor):
    """Precondición a de ALT, MOD, BAJ y CNS: ``actor`` es un Agrónomo con la cuenta activa (SEG-13). Cualquier Agrónomo activo
    (regla 1 de ALT y MOD): la categoría es del catálogo y no hay «a cargo». El Gerente no consulta categorías (regla 5 de CNS)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise PermissionDenied("Solo un Agrónomo activo puede gestionar categorías de insumos.")


def _error_de_campo(campo, mensaje, codigo):
    """Un ``ValidationError`` con un solo error de campo."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _validar(nombre, consumo_directo):
    """Reglas 2 y 3 de CMP-ALT-TIN, sin tocar la base: el nombre recortado, obligatorio, con contenido y de hasta 100
    caracteres; el consumo directo obligatorio y uno de los tres valores. Junta TODOS los errores de campo en un solo
    ``ValidationError`` (docs/patrones/abm.md, sección 2). Devuelve ``(nombre, consumo_directo)`` normalizados."""
    errores = {}
    nombre = nombre.strip() if isinstance(nombre, str) else ("" if nombre is None else str(nombre).strip())
    if not nombre:
        errores["nombre"] = [ValidationError("Ingresá el nombre de la categoría.", code="obligatorio")]
    elif not _tiene_contenido(nombre):
        errores["nombre"] = [ValidationError("Ingresá un texto con al menos una letra o un número.", code="sin_contenido")]
    elif len(nombre) > LARGO_DEL_NOMBRE:
        errores["nombre"] = [ValidationError(f"Usá como máximo {LARGO_DEL_NOMBRE} caracteres.", code="demasiado_largo")]
    if not consumo_directo:
        errores["consumo_directo"] = [ValidationError("Elegí una opción.", code="obligatorio")]
    elif consumo_directo not in Consumo.values:
        errores["consumo_directo"] = [ValidationError("Elegí una de las opciones.", code="invalido")]
    if errores:
        raise ValidationError(errores)
    return nombre, consumo_directo


def _nombre_repetido(nombre, excluir_pk=None):
    """True si ya hay una categoría con ese nombre, sin distinguir mayúsculas, activa, inactiva o del sistema (regla 2 de
    CMP-ALT-TIN). Usa la misma expresión que la restricción de la base."""
    existentes = TipoInsumo.objects.annotate(_minuscula=Lower("nombre_tipo_insumo"))
    if excluir_pk is not None:
        existentes = existentes.exclude(pk=excluir_pk)
    return existentes.filter(_minuscula=Lower(Value(nombre))).exists()


def _error_nombre_repetido():
    """El error de campo de un nombre repetido."""
    return _error_de_campo("nombre", MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")


def _guardar(tipo, campos=None):
    """Guarda la categoría (o ``campos``); si dos pedidos eligieron el mismo nombre a la vez, el segundo recibe el
    ``IntegrityError`` de la restricción única y se traduce al mismo error de campo (nunca un 500)."""
    try:
        with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
            tipo.save(update_fields=campos) if campos else tipo.save()
    except IntegrityError as error:
        if RESTRICCION_NOMBRE_UNICO in str(error):
            raise _error_nombre_repetido() from error
        raise


def _bloquear_tipo(actor, tipo_id):
    """La categoría bloqueada (``FOR NO KEY UPDATE``) y leída de nuevo, con su estado real; 404 si no existe. Verifica, ya
    bloqueada, que quien actúa siga activo. Hay que llamarla dentro de ``transaction.atomic()``."""
    tipo = TipoInsumo.objects.select_for_update(no_key=True).filter(pk=tipo_id).first()
    if tipo is None:
        raise Http404("No existe esa categoría.")
    _actor_sigue_activo(actor)
    return tipo


def _exigir_que_no_sea_del_sistema(tipo):
    """Precondición b y regla 3 de MOD y de BAJ: las del sistema no se modifican ni se dan de baja. Lo rechaza el servicio
    (``categoria_del_sistema``) aunque la pantalla no ofrezca la acción."""
    if tipo.es_del_sistema:
        raise _error_general(MENSAJE_DEL_SISTEMA, "categoria_del_sistema")


def _cambio_de_estado(antes, despues):
    """El detalle de auditoría (D-36) de un cambio de estado."""
    return {"cambios": {"estado": {"antes": antes, "despues": despues}}}


# ---- casos de uso ----


def alta_tipo_insumo(actor, *, nombre, consumo_directo):
    """CMP-ALT-TIN: crea una categoría activa, que no es del sistema y sin insumos, y la devuelve.

    - Precondición a y regla 1: ``actor`` es un Agrónomo activo (cualquiera: la categoría vale para todos los invernaderos).
    - Precondición b y regla 2: nombre obligatorio, con contenido, de hasta 100 caracteres y único entre todas las categorías,
      activas, inactivas o del sistema, sin distinguir mayúsculas ni espacios al borde (``nombre_repetido``).
    - Regla 3: consumo directo obligatorio y uno de los tres valores. Regla 4: nunca crea una del sistema.
    - Postcondición a y b, D-22 y D-36: queda «activa» y un registro ``alta_tipo_insumo`` en la misma transacción.
    """
    _exigir_agronomo(actor)
    nombre, consumo_directo = _validar(nombre, consumo_directo)
    with transaction.atomic():
        _actor_sigue_activo(actor)
        if _nombre_repetido(nombre):
            raise _error_nombre_repetido()
        tipo = TipoInsumo(
            nombre_tipo_insumo=nombre,
            consumo_directo=consumo_directo,
            estado_tipo_insumo=Estado.ACTIVO,
            es_del_sistema=False,
        )
        _guardar(tipo)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_TIPO_INSUMO,
            afectados=[tipo],
            detalle={
                "cambios": {
                    "nombre": {"antes": None, "despues": nombre},
                    "consumo_directo": {"antes": None, "despues": consumo_directo},
                    "estado": {"antes": None, "despues": Estado.ACTIVO.value},
                }
            },
        )
    return tipo


def _reservas_que_impiden_cambiar_el_consumo(tipo):
    """Regla 4 de CMP-MOD-TIN: bloquea los ``InsumoInvernadero`` de la categoría en orden de id y devuelve un texto por cada insumo
    con cantidades reservadas por órdenes a realizar (con las órdenes que las reservan), o una lista vacía. Los registra
    `produccion` (``registrar_reservas_de_insumo``); sin registrantes, no hay reservas."""
    existencias = list(
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",))
        .filter(insumo__tipo_insumo=tipo)
        .select_related("insumo", "invernadero")
        .order_by("id")
    )
    if not existencias:
        return []
    ids = [existencia.pk for existencia in existencias]
    reservado = extensiones.reservado_de(ids)
    ordenes = extensiones.ordenes_que_reservan([i for i in ids if reservado[i] > 0])
    textos = []
    for existencia in existencias:
        if reservado[existencia.pk] <= 0:
            continue
        cantidad = texto_cantidad(reservado[existencia.pk], existencia.insumo.unidad_medida_insumo)
        detalle = f"{existencia.insumo.nombre_insumo} ({cantidad} reservados en {existencia.invernadero.nombre_invernadero}"
        nombres = ", ".join(orden.texto for orden in ordenes.get(existencia.pk, []))
        textos.append(detalle + (f" por {nombres})" if nombres else ")"))
    return textos


def modificar_tipo_insumo(actor, tipo_id, *, nombre, consumo_directo):
    """CMP-MOD-TIN: cambia el nombre o el consumo directo de una categoría y la devuelve.

    - Precondición a y regla 1: cualquier Agrónomo activo. Precondición b y regla 3: no es del sistema
      (``categoria_del_sistema``). Regla 6: una inactiva no se modifica, solo se reactiva (``categoria_inactiva``).
    - Precondición c y regla 2: el nombre y el consumo siguen las reglas 2 y 3 de CMP-ALT-TIN; el nombre nuevo no lo tiene otra
      categoría (``nombre_repetido``).
    - Regla 4: el consumo directo no cambia si algún insumo de la categoría tiene cantidades reservadas por órdenes a realizar
      (``reservas_activas``, en el campo ``consumo_directo``, con los insumos y las órdenes). El nombre sí se puede cambiar.
    - D-28: sin cambios no se escribe ni se audita. Postcondición a y c, D-36: un registro ``modificacion_tipo_insumo`` con lo que
      cambió. Regla 5: el cambio rige desde ahora (no toca insumos ni aplicaciones ya registradas).
    """
    _exigir_agronomo(actor)
    nombre, consumo_directo = _validar(nombre, consumo_directo)
    with transaction.atomic():
        tipo = _bloquear_tipo(actor, tipo_id)
        _exigir_que_no_sea_del_sistema(tipo)
        if tipo.estado_tipo_insumo == Estado.INACTIVO:
            raise _error_general("La categoría está inactiva: solo se puede reactivar.", "categoria_inactiva")
        if _nombre_repetido(nombre, excluir_pk=tipo.pk):
            raise _error_nombre_repetido()
        cambios = {}
        if nombre != tipo.nombre_tipo_insumo:
            cambios["nombre"] = {"antes": tipo.nombre_tipo_insumo, "despues": nombre}
        if consumo_directo != tipo.consumo_directo:
            cambios["consumo_directo"] = {"antes": tipo.consumo_directo, "despues": consumo_directo}
        if not cambios:
            return tipo
        if "consumo_directo" in cambios:
            con_reservas = _reservas_que_impiden_cambiar_el_consumo(tipo)
            if con_reservas:
                raise _error_de_campo(
                    "consumo_directo",
                    "No se puede cambiar el consumo directo: tiene stock reservado por órdenes a realizar: "
                    + "; ".join(con_reservas)
                    + ". Primero deben concretarse o cancelarse.",
                    "reservas_activas",
                )
        tipo.nombre_tipo_insumo = nombre
        tipo.consumo_directo = consumo_directo
        _guardar(tipo, ["nombre_tipo_insumo", "consumo_directo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_TIPO_INSUMO,
            afectados=[tipo],
            detalle={"cambios": cambios},
        )
    return tipo


def reactivar_tipo_insumo(actor, tipo_id):
    """CMP-MOD-TIN (postcondición b y regla 6): reactiva una categoría dada de baja, sin validaciones, y la devuelve. Después se
    modifica como cualquier otra. Protecciones: una del sistema se rechaza con ``categoria_del_sistema`` y una que no está dada
    de baja, con ``categoria_no_inactiva``. Se audita como ``reactivacion_tipo_insumo``."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        tipo = _bloquear_tipo(actor, tipo_id)
        _exigir_que_no_sea_del_sistema(tipo)
        if tipo.estado_tipo_insumo != Estado.INACTIVO:
            raise _error_general("La categoría no está dada de baja.", "categoria_no_inactiva")
        tipo.estado_tipo_insumo = Estado.ACTIVO
        tipo.save(update_fields=["estado_tipo_insumo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_TIPO_INSUMO,
            afectados=[tipo],
            detalle=_cambio_de_estado(Estado.INACTIVO.value, Estado.ACTIVO.value),
        )
    return tipo


def _texto_de_insumos_activos(cantidad):
    """«1 insumo activo» o «N insumos activos»."""
    return f"{cantidad} insumo activo" if cantidad == 1 else f"{cantidad} insumos activos"


def baja_tipo_insumo(actor, tipo_id):
    """CMP-BAJ-TIN: da de baja lógica una categoría activa y la devuelve.

    - Precondición a: Agrónomo activo. Precondición b: la categoría está activa (``categoria_inactiva``) y no es del sistema
      (``categoria_del_sistema``).
    - Precondición c y regla 2: sin insumos activos; si los tiene, no se da de baja y se dice cuántos son (``insumos_activos``):
      primero se pasan a otra categoría con Modificar Insumo. Los inactivos no impiden la baja. Se cuentan DESPUÉS de bloquear la
      categoría: quien agrega un insumo la bloquea antes.
    - Postcondición a y regla 1: queda «inactiva» y conserva sus insumos inactivos. Postcondición b y D-36: ``baja_tipo_insumo``.
    """
    _exigir_agronomo(actor)
    with transaction.atomic():
        tipo = _bloquear_tipo(actor, tipo_id)
        _exigir_que_no_sea_del_sistema(tipo)
        if tipo.estado_tipo_insumo == Estado.INACTIVO:
            raise _error_general("La categoría ya está dada de baja.", "categoria_inactiva")
        activos = Insumo.objects.filter(tipo_insumo=tipo, estado_insumo=Insumo.Estado.ACTIVO).count()
        if activos:
            raise _error_general(
                f"Tiene {_texto_de_insumos_activos(activos)}. Primero deben pasarse a otra categoría con Modificar Insumo.",
                "insumos_activos",
            )
        tipo.estado_tipo_insumo = Estado.INACTIVO
        tipo.save(update_fields=["estado_tipo_insumo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_TIPO_INSUMO,
            afectados=[tipo],
            detalle=_cambio_de_estado(Estado.ACTIVO.value, Estado.INACTIVO.value),
        )
    return tipo


# ---- consulta (CMP-CNS-TIN) ----


def _con_cantidad_de_insumos():
    """Las categorías con su cantidad de insumos del catálogo, activos e inactivos (``cantidad_de_insumos``), en la misma consulta."""
    return TipoInsumo.objects.annotate(cantidad_de_insumos=Count("insumos"))


def consultar_tipos_de_insumo(actor):
    """CMP-CNS-TIN: todas las categorías, activas e inactivas, las activas primero y por nombre sin distinguir mayúsculas
    (regla 1), cada una con su cantidad de insumos (regla 2). Precondición a: Agrónomo activo; el Gerente no consulta
    categorías (regla 5): ``PermissionDenied``. No audita (regla 6 y SEG-14)."""
    _exigir_agronomo(actor)
    return _con_cantidad_de_insumos().order_by("estado_tipo_insumo", Lower("nombre_tipo_insumo"), "id")


def obtener_tipo_de_insumo(actor, tipo_id):
    """CMP-CNS-TIN: la categoría ``tipo_id`` con su cantidad de insumos (404 si no existe). Solo el Agrónomo."""
    _exigir_agronomo(actor)
    return get_object_or_404(_con_cantidad_de_insumos(), pk=tipo_id)


def acciones_permitidas(actor, tipo):
    """D-30: las acciones que ``actor`` puede hacer sobre ``tipo``, un ``frozenset`` de ``{"modificar", "baja", "reactivar"}``
    (regla 4 de CMP-CNS-TIN). Solo un Agrónomo activo; una categoría del sistema no tiene acciones; una activa se modifica y se
    da de baja; una inactiva solo se reactiva. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        return frozenset()
    if tipo.es_del_sistema:
        return frozenset()
    if tipo.estado_tipo_insumo == Estado.ACTIVO:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})
