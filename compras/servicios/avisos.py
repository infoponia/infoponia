# Regla única de destinatarios de los avisos de compras (H21, D-87 punto 3; cierra MD-67). La usan todos los avisos «al Agrónomo del pedido o de la
# orden»: pedido cubierto (CMP-02a), cancelación automática (CMP-02b), fecha límite vencida, aprobación y rechazo de una orden (CMP-03). Los avisos
# al Contador usan ``responsables.notificar_al_responsable_contable`` (D-85), no esto. Solo lee: crear la notificación es de quien llama.

from core.models import Usuario
from maestros.models import Invernadero


def destinatarios_por_destino(invernadero_ids, *, excluir=None):
    """Las cuentas a avisar por un pedido o una orden con esos invernaderos de destino: el Agrónomo **activo** de cada uno y, si alguno no lo tiene
    (sin Agrónomo o con el Agrónomo inactivo), el Gerente activo **una sola vez**; sin repetidos. «Nunca se notifica a quien hizo la acción»: se
    cumple pasando ``excluir=actor``; el destino de un Agrónomo excluido no suma al Gerente (ese destino sí tiene Agrónomo). Sin Gerente activo no
    hay a quién avisar y no falla (D-14). Devuelve una lista de cuentas (``Usuario``) en orden de invernadero."""
    ids = sorted(set(invernadero_ids))
    vistas = {excluir.pk} if excluir is not None else set()
    destinatarios = []
    hace_falta_el_gerente = False
    for invernadero in Invernadero.objects.filter(pk__in=ids).select_related("agronomo").order_by("id"):
        agronomo = invernadero.agronomo
        if agronomo is None or not agronomo.is_active:
            hace_falta_el_gerente = True
        elif agronomo.pk not in vistas:
            vistas.add(agronomo.pk)
            destinatarios.append(agronomo)
    if hace_falta_el_gerente:
        gerente = Usuario.objects.filter(rol=Usuario.Rol.GERENTE, is_active=True).first()
        if gerente is not None and gerente.pk not in vistas:
            destinatarios.append(gerente)
    return destinatarios
