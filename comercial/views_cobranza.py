# Vistas de la cobranza de suministros (COM-08a; docs/casos_de_uso/comercial/cobranza.md, «Pantallas»): la pestaña «Cobranza», «Registrar cobro» (con su resumen), la ficha del cobro, el comprobante
# imprimible y «Reenviar comprobante». Las vistas SOLO orquestan. Mientras no se escribe el paso 8 de la tarea, cada vista responde 404: las URLs existen para que el enlace de la alerta «pago en mora»
# (`cobranza.enlaces_de_alertas`) pueda construirse.

from django.http import Http404
from django.views.decorators.cache import never_cache

from core.acceso import rol_requerido


@never_cache
@rol_requerido("gerente", "vendedor")
def pendiente(request, **kwargs):
    """Provisoria (paso 8 de COM-08a)."""
    raise Http404("Pantalla de cobranza todavía sin escribir.")
