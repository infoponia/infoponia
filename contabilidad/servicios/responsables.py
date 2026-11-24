# «Quién registra» asientos y pagos: la regla única de D-85 punto 5 (USR-11). Todo caso de uso de contabilidad o de compras
# que pregunte quién registra, o a quién avisarle, usa estas funciones y nunca `rol == ...` suelto (docs/api/asientos.md,
# «Reglas para quien llama», punto 4). Solo lee, no bloquea y no escribe, salvo la notificación, que corre dentro de la
# transacción del caso de uso que la dispara (D-42). Importa solo de `core` (regla A1 de D-37).

from core import notificaciones
from core.models import Contador, Gerente


def contador_activo():
    """El Contador activo, o ``None`` si no hay (D-85 punto 2: a lo sumo uno)."""
    return Contador.objects.filter(is_active=True).first()


def responsable_contable():
    """Quien registra asientos y pagos: el Contador activo o, si no hay, el Gerente activo, o ``None`` si no hay ninguno
    (D-85 puntos 4 y 5). Sin Contador, el Gerente hace lo del Contador para que el sistema no quede bloqueado."""
    return contador_activo() or Gerente.objects.filter(is_active=True).first()


def puede_registrar_asientos(usuario):
    """True si ``usuario`` es el responsable contable: el Contador activo, o el Gerente activo cuando no hay Contador activo
    (D-85 punto 5). Vale igual para registrar pagos. Se compara contra la base y no contra la instancia recibida: una
    cuenta que se dio de baja después de cargarse no registra. El Vendedor y los demás roles nunca (D-85 punto 8)."""
    if usuario is None or getattr(usuario, "pk", None) is None:
        return False
    responsable = responsable_contable()
    return responsable is not None and responsable.pk == usuario.pk


def notificar_al_responsable_contable(titulo, detalle, *, excluir=None):
    """Crea una notificación (D-42) para el responsable contable y la devuelve; ``None`` si no hay responsable o si el
    responsable es ``excluir`` (el actor: H21, nunca se notifica a quien hizo la acción, D-85 punto 7). Sin responsable no
    hace nada ni falla (D-14); el texto se valida igual."""
    # ``notificar_a_varios`` ya omite los ``None`` y la cuenta excluida, y valida el texto aunque no haya destinatarios.
    creadas = notificaciones.notificar_a_varios([responsable_contable()], titulo, detalle, excluir=excluir)
    return creadas[0] if creadas else None
