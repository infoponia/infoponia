# Servicios de Cultivo (MAE-03): alta (PROD-ALT-CLT), modificación con su reactivación (PROD-MOD-CLT), baja (PROD-BAJ-CLT) y
# consulta (PROD-CNS-CLT). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36
# (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/maestros/cultivos.md; contrato de los puntos de extensión:
# docs/api/extensiones_de_maestros.md.
#
# Bloqueos (cultivos.md, «Bloqueos»; siempre ``FOR NO KEY UPDATE``): modificar, reactivar y dar de baja bloquean la fila del
# cultivo y, recién después, lo que bloqueen los registrantes (semillas, en orden de id). Quien crea una variedad (INV-03)
# bloquea el cultivo ANTES de insertarla (cultivo -> variedad): así la baja espera, ve la variedad y se rechaza. Dos
# Agrónomos que renombran a la vez: gana el último, calculado contra lo leído después de bloquear (misma convención que
# ``modificar_invernadero``, D-40).

from collections import namedtuple

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Value
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, rol_de
from maestros import extensiones
from maestros.extensiones import VariedadesDelCultivo
from maestros.models import Cultivo, Invernadero, Variedad
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, _tiene_contenido

Estado = Cultivo.Estado

# Lo que el renombre informa antes de confirmar (regla 3 de PROD-MOD-CLT y prototipo): cuántas semillas cambian de nombre y los
# invernaderos cuyo Agrónomo recibirá una notificación.
AvisoDeRenombre = namedtuple("AvisoDeRenombre", "cantidad_de_semillas invernaderos")

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

LARGO_DEL_NOMBRE = Cultivo._meta.get_field("nombre_cultivo").max_length
MENSAJE_NOMBRE_REPETIDO = "Ya existe un cultivo con ese nombre."
PLANTILLA_DE_VARIEDADES = "maestros/cultivos/_variedades_simples.html"


# ---- comunes ----


def _exigir_agronomo(actor):
    """Precondición a de ALT, MOD, BAJ y CNS: ``actor`` es un Agrónomo con la cuenta activa (SEG-13). Cualquier Agrónomo
    activo (reglas 1 y 2 de ALT y MOD, regla 3 de BAJ): no hay «a cargo». El Gerente no consulta cultivos (regla 4 de CNS)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise PermissionDenied("Solo un Agrónomo activo puede gestionar cultivos.")


def _nombre_valido(nombre):
    """Regla 2 de PROD-ALT-CLT: el nombre recortado, obligatorio, con contenido y de hasta 40 caracteres; si no, un
    ``ValidationError`` con el error del campo ``nombre``."""
    nombre = nombre.strip() if isinstance(nombre, str) else ("" if nombre is None else str(nombre).strip())
    if not nombre:
        error = ValidationError("Ingresá el nombre del cultivo.", code="obligatorio")
    elif not _tiene_contenido(nombre):
        error = ValidationError("Ingresá un texto con al menos una letra o un número.", code="sin_contenido")
    elif len(nombre) > LARGO_DEL_NOMBRE:
        error = ValidationError(f"Usá como máximo {LARGO_DEL_NOMBRE} caracteres.", code="demasiado_largo")
    else:
        return nombre
    raise ValidationError({"nombre": [error]})


def _nombre_repetido(nombre, excluir_pk=None):
    """True si ya hay un cultivo con ese nombre, sin distinguir mayúsculas, activo o inactivo (regla 2 de PROD-ALT-CLT). Usa
    la misma expresión que la restricción de la base."""
    existentes = Cultivo.objects.annotate(_minuscula=Lower("nombre_cultivo"))
    if excluir_pk is not None:
        existentes = existentes.exclude(pk=excluir_pk)
    return existentes.filter(_minuscula=Lower(Value(nombre))).exists()


def _error_nombre_repetido():
    """El error de campo de un nombre repetido."""
    return ValidationError({"nombre": [ValidationError(MENSAJE_NOMBRE_REPETIDO, code="nombre_repetido")]})


def _bloquear_cultivo(actor, cultivo_id):
    """El cultivo bloqueado (``FOR NO KEY UPDATE``) y leído de nuevo, con su estado real; 404 si no existe. Verifica, ya
    bloqueado, que quien actúa siga activo. Hay que llamarla dentro de ``transaction.atomic()``."""
    cultivo = Cultivo.objects.select_for_update(no_key=True).filter(pk=cultivo_id).first()
    if cultivo is None:
        raise Http404("No existe ese cultivo.")
    _actor_sigue_activo(actor)
    return cultivo


def _guardar_con_nombre_unico(cultivo, campos):
    """Guarda ``campos`` del cultivo; si dos pedidos eligieron el mismo nombre a la vez, el segundo recibe el ``IntegrityError``
    de la restricción única y se traduce al mismo error de campo (nunca un 500)."""
    try:
        with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
            cultivo.save(update_fields=campos)
    except IntegrityError as error:
        if "cultivo_nombre_unico" in str(error):
            raise _error_nombre_repetido() from error
        raise


def _cambio_de_estado(antes, despues):
    """El detalle de auditoría (D-36) de un cambio de estado."""
    return {"cambios": {"estado": {"antes": antes, "despues": despues}}}


# ---- casos de uso ----


def alta_cultivo(actor, *, nombre):
    """PROD-ALT-CLT: crea un cultivo activo, sin variedades, y lo devuelve.

    - Precondición a y reglas 1: ``actor`` es un Agrónomo activo (cualquiera: el cultivo lo comparten todos).
    - Precondición b y regla 2: nombre obligatorio, con contenido, de hasta 40 caracteres y único entre todos los cultivos,
      activos o inactivos, sin distinguir mayúsculas ni espacios al borde (``nombre_repetido``).
    - Postcondición a y regla 3: queda «activo» y sin variedades. Postcondición b, D-22 y D-36: un registro ``alta_cultivo``
      en la misma transacción.
    """
    _exigir_agronomo(actor)
    nombre = _nombre_valido(nombre)
    with transaction.atomic():
        _actor_sigue_activo(actor)
        if _nombre_repetido(nombre):
            raise _error_nombre_repetido()
        try:
            with transaction.atomic():
                cultivo = Cultivo.objects.create(nombre_cultivo=nombre, estado_cultivo=Estado.ACTIVO)
        except IntegrityError as error:
            if "cultivo_nombre_unico" in str(error):
                raise _error_nombre_repetido() from error
            raise
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_CULTIVO,
            afectados=[cultivo],
            detalle={
                "cambios": {
                    "nombre": {"antes": None, "despues": nombre},
                    "estado": {"antes": None, "despues": Estado.ACTIVO.value},
                }
            },
        )
    return cultivo


def _invernaderos_a_notificar(cultivo, actor):
    """Regla 4 de PROD-MOD-CLT: los invernaderos ACTIVOS que usan alguna variedad del cultivo (los informa `inventario` por
    ``registrar_uso_de_cultivo``; se vuelve a verificar el estado) y cuyo Agrónomo, activo y distinto de ``actor``, recibirá la
    notificación. Por nombre. Sin registrantes, ninguno."""
    ids = extensiones.invernaderos_que_usan_el_cultivo(cultivo)
    if not ids:
        return []
    invernaderos = Invernadero.objects.filter(pk__in=ids, estado_invernadero=Invernadero.Estado.ACTIVO).select_related(
        "agronomo"
    )
    return [
        invernadero
        for invernadero in invernaderos.order_by("nombre_invernadero")
        if invernadero.agronomo is not None
        and invernadero.agronomo.is_active
        and invernadero.agronomo.pk != actor.pk
    ]


def aviso_de_renombre(actor, cultivo_id):
    """PROD-MOD-CLT regla 3 y regla 4: lo que el Sistema informa ANTES de confirmar un renombre. Cuántas semillas cambian de
    nombre (``contar_semillas_a_renombrar``) y los invernaderos cuyo Agrónomo recibirá una notificación. Solo lectura: no
    bloquea, no cambia nada y no audita."""
    _exigir_agronomo(actor)
    cultivo = get_object_or_404(Cultivo, pk=cultivo_id)
    return AvisoDeRenombre(
        extensiones.contar_semillas_a_renombrar(cultivo), _invernaderos_a_notificar(cultivo, actor)
    )


def modificar_cultivo(actor, cultivo_id, *, nombre):
    """PROD-MOD-CLT: cambia el nombre de un cultivo y lo devuelve.

    - Precondición a y regla 2: cualquier Agrónomo activo. Precondición b y regla 1: el nombre nuevo cumple la regla 2 de
      PROD-ALT-CLT y no lo tiene otro cultivo. Regla 5: un cultivo inactivo no se modifica (``cultivo_inactivo``).
    - D-28: si el nombre no cambia, no se escribe ni se audita (ni se renombran semillas ni se notifica).
    - Postcondición a y regla 3: se renombran las semillas de sus variedades (``renombrar_semillas``, de INV-03, que escribe
      su propio log ``modificacion_semilla`` por semilla; ve el cultivo ya con su nombre nuevo).
    - Postcondición b y regla 4: ``notificar_a_varios`` al Agrónomo de cada invernadero que usa alguna variedad, sin el actor,
      con una sola llamada y DENTRO de la transacción (si algo falla no queda ninguna). No se audita (D-42).
    - Postcondición d y D-36: un registro ``modificacion_cultivo`` con el cambio de nombre; si se renombraron semillas, su
      cantidad va en ``datos``. Dos renombres a la vez: gana el último, calculado contra lo leído después de bloquear.
    """
    _exigir_agronomo(actor)
    nombre = _nombre_valido(nombre)
    with transaction.atomic():
        cultivo = _bloquear_cultivo(actor, cultivo_id)
        if cultivo.estado_cultivo == Estado.INACTIVO:
            raise _error_general("El cultivo está inactivo: solo se puede reactivar.", "cultivo_inactivo")
        if _nombre_repetido(nombre, excluir_pk=cultivo.pk):
            raise _error_nombre_repetido()
        nombre_anterior = cultivo.nombre_cultivo
        if nombre == nombre_anterior:
            return cultivo
        cultivo.nombre_cultivo = nombre
        _guardar_con_nombre_unico(cultivo, ["nombre_cultivo"])
        semillas = extensiones.renombrar_semillas(actor, cultivo, nombre_anterior)
        cuentas = [invernadero.agronomo for invernadero in _invernaderos_a_notificar(cultivo, actor)]
        if cuentas:
            notificaciones.notificar_a_varios(
                cuentas,
                f"Cambió el cultivo {nombre_anterior}",
                f"{actor.get_full_name() or actor.email} lo renombró a {nombre}. Sus variedades siguen igual.",
                excluir=actor,
            )
        detalle = {"cambios": {"nombre": {"antes": nombre_anterior, "despues": nombre}}}
        if semillas:
            detalle["datos"] = {"semillas_renombradas": semillas}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_CULTIVO,
            afectados=[cultivo],
            detalle=detalle,
        )
    return cultivo


def reactivar_cultivo(actor, cultivo_id):
    """PROD-MOD-CLT (postcondición c y regla 6): reactiva un cultivo dado de baja, sin validaciones, y lo devuelve. No reactiva
    sus variedades (se reactivan una por una con Modificar Variedad). Uno que no está dado de baja se rechaza con
    ``cultivo_no_inactivo``. Se audita como ``reactivacion_cultivo``."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        cultivo = _bloquear_cultivo(actor, cultivo_id)
        if cultivo.estado_cultivo != Estado.INACTIVO:
            raise _error_general("El cultivo no está dado de baja.", "cultivo_no_inactivo")
        cultivo.estado_cultivo = Estado.ACTIVO
        cultivo.save(update_fields=["estado_cultivo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_CULTIVO,
            afectados=[cultivo],
            detalle=_cambio_de_estado(Estado.INACTIVO.value, Estado.ACTIVO.value),
        )
    return cultivo


def _texto_de_variedades_activas(cantidad):
    """«1 variedad activa» o «N variedades activas»."""
    return f"{cantidad} variedad activa" if cantidad == 1 else f"{cantidad} variedades activas"


def baja_cultivo(actor, cultivo_id):
    """PROD-BAJ-CLT: da de baja lógica un cultivo activo y lo devuelve.

    - Precondición a y regla 3: cualquier Agrónomo activo. Precondición b: el cultivo está activo (``cultivo_inactivo``).
    - Precondición c y regla 2: sin variedades activas; si las tiene, no se da de baja y se dice cuántas son
      (``variedades_activas``). La baja no es en cascada: primero se dan de baja con Baja Variedad. Se cuentan DESPUÉS de
      bloquear el cultivo: quien crea una variedad lo bloquea antes (cultivo -> variedad).
    - Postcondición a y regla 1: queda «inactivo» y conserva sus variedades inactivas. Postcondición b y D-36: un registro
      ``baja_cultivo`` con el cambio de estado.
    """
    _exigir_agronomo(actor)
    with transaction.atomic():
        cultivo = _bloquear_cultivo(actor, cultivo_id)
        if cultivo.estado_cultivo == Estado.INACTIVO:
            raise _error_general("El cultivo ya está dado de baja.", "cultivo_inactivo")
        activas = Variedad.objects.filter(cultivo=cultivo, estado_variedad=Variedad.Estado.ACTIVO).count()
        if activas:
            raise _error_general(
                f"Tiene {_texto_de_variedades_activas(activas)}. Primero se dan de baja con Baja Variedad.",
                "variedades_activas",
            )
        cultivo.estado_cultivo = Estado.INACTIVO
        cultivo.save(update_fields=["estado_cultivo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_CULTIVO,
            afectados=[cultivo],
            detalle=_cambio_de_estado(Estado.ACTIVO.value, Estado.INACTIVO.value),
        )
    return cultivo


# ---- consulta (PROD-CNS-CLT) ----


def _con_variedades_activas():
    """Los cultivos con su cantidad de variedades activas (``variedades_activas``) en la misma consulta."""
    return Cultivo.objects.annotate(
        variedades_activas=Count("variedades", filter=Q(variedades__estado_variedad=Variedad.Estado.ACTIVO))
    )


def consultar_cultivos(actor):
    """PROD-CNS-CLT: todos los cultivos, activos e inactivos, los activos primero y por nombre (regla 1), cada uno con su
    cantidad de variedades activas (``variedades_activas``, regla 2). Precondición a: Agrónomo activo; el Gerente no consulta
    cultivos (regla 4): ``PermissionDenied``. No audita (regla 5 y SEG-14)."""
    _exigir_agronomo(actor)
    return _con_variedades_activas().order_by("estado_cultivo", Lower("nombre_cultivo"), "id")


def obtener_cultivo(actor, cultivo_id):
    """PROD-CNS-CLT: el cultivo ``cultivo_id`` con su cantidad de variedades activas (404 si no existe). Solo el Agrónomo."""
    _exigir_agronomo(actor)
    return get_object_or_404(_con_variedades_activas(), pk=cultivo_id)


def acciones_permitidas(actor, cultivo):
    """D-30: las acciones que ``actor`` puede hacer sobre ``cultivo``, un ``frozenset`` (regla 3 de PROD-CNS-CLT). Solo un
    Agrónomo activo: sobre un cultivo activo, modificar (renombrar) y dar de baja; sobre uno inactivo, solo reactivar. «Alta
    Variedad» y las acciones de variedad no se ofrecen hasta INV-03. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        return frozenset()
    if cultivo.estado_cultivo == Estado.ACTIVO:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})


def variedades_de_cultivos(actor, cultivos):
    """``{id: VariedadesDelCultivo(cabecera, cuerpo)}``: el HTML de la cabecera (botones de variedad) y del cuerpo (la tabla) de
    la tarjeta de cada cultivo. Lo arma el único registrante de ``registrar_variedades_de_cultivo`` (INV-03). Sin registrante
    (hasta INV-03), o para un cultivo que no trae, usa lo propio de `maestros`: «No tiene variedades» o la lista simple de
    nombres si las hay (cargadas a mano), y sin botones."""
    cultivos = list(cultivos)
    tarjetas = dict(extensiones.variedades_registradas(actor, cultivos) or {})
    faltan = [cultivo for cultivo in cultivos if cultivo.pk not in tarjetas]
    if faltan:
        por_cultivo = {cultivo.pk: [] for cultivo in faltan}
        for variedad in Variedad.objects.filter(cultivo__in=faltan).order_by(Lower("nombre_variedad"), "id"):
            por_cultivo[variedad.cultivo_id].append(variedad)
        for cultivo in faltan:
            cuerpo = render_to_string(PLANTILLA_DE_VARIEDADES, {"variedades": por_cultivo[cultivo.pk]})
            tarjetas[cultivo.pk] = VariedadesDelCultivo(mark_safe(""), cuerpo)
    return tarjetas
