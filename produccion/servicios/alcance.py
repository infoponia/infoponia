# Alcance de quien registra en un invernadero (PRD-03): lo comparten Registrar Merma, Registrar Aplicación de Insumos y Registrar Evento.
# Fuente: regla «Ámbito del actor» de PROD-REG-MRM, regla «Quién lo registra» de PROD-REG-APL y regla 1 de PROD-REG-EVT: el Capataz opera en
# los invernaderos que tiene asignados y el Agrónomo en los que tiene a su cargo; el Gerente no registra. Un invernadero inactivo no admite
# operaciones nuevas (regla 4 de PROD-BAJ-INV). Estas funciones no escriben ni bloquean: quien llama las repite después de bloquear.

from django.db.models.functions import Lower
from django.http import Http404

from core.models import Usuario, rol_de
from maestros.models import Invernadero
from produccion.errores import ErrorDeProduccion

AGRONOMO, CAPATAZ = Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ


def exigir_actor(actor):
    """El actor es un Agrónomo o un Capataz con la cuenta activa (se lee de la base: pudo darse de baja mientras tanto); si no, `sin_permiso`."""
    if (
        actor is None
        or rol_de(actor) not in (AGRONOMO, CAPATAZ)
        or not Usuario.objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise ErrorDeProduccion("sin_permiso", "Tu cuenta no tiene acceso a esta acción.")


def es_del_actor(actor, invernadero):
    """True si el invernadero está a cargo del Agrónomo `actor` o asignado al Capataz `actor` (no mira si está activo)."""
    rol = rol_de(actor)
    if rol == AGRONOMO:
        return invernadero.agronomo_id == actor.pk
    if rol == CAPATAZ:
        return invernadero.capataz_id == actor.pk
    return False


def exigir_en_alcance(actor, invernadero):
    """Verifica que `invernadero` sea del actor (`sin_permiso`) y esté activo (`invernadero_inactivo`)."""
    if not es_del_actor(actor, invernadero):
        raise ErrorDeProduccion("sin_permiso", "Ese invernadero no está a tu cargo ni asignado a tu cuenta.")
    if not invernadero.activo:
        raise ErrorDeProduccion("invernadero_inactivo", "El invernadero está dado de baja: no admite operaciones nuevas.")


def invernadero_del_actor(actor, invernadero_id):
    """El invernadero (activo y del actor) para operar en él: `sin_permiso` si el actor no es Capataz o Agrónomo activo o el invernadero
    no es suyo, `invernadero_inactivo` si está dado de baja, `Http404` si no existe."""
    exigir_actor(actor)
    invernadero = Invernadero.objects.filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    exigir_en_alcance(actor, invernadero)
    return invernadero


def invernaderos_del_actor(actor):
    """Los invernaderos ACTIVOS en los que `actor` puede registrar (paso 2 de PROD-REG-MRM y de PROD-REG-APL), por nombre: los que tiene a
    su cargo (Agrónomo) o asignados (Capataz). Cualquier otra cuenta, o una inactiva, no tiene ninguno."""
    if actor is None or not getattr(actor, "is_active", False):
        return []
    rol = rol_de(actor)
    if rol == AGRONOMO:
        filtro = {"agronomo_id": actor.pk}
    elif rol == CAPATAZ:
        filtro = {"capataz_id": actor.pk}
    else:
        return []
    return list(
        Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO, **filtro).order_by(Lower("nombre_invernadero"), "pk")
    )
