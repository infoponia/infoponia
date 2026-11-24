# Servicios del nodo central (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md, «Servicios» y «El modo»): encontrar el sistema por el resumen
# del token, registrar la comunicación del nodo (postcondición a) y su modo (extensión 1b, postcondición q). Todos reciben ``ahora`` y datos ya traducidos;
# ninguno conoce HTTP. El token nunca llega acá: solo su resumen.
#
# Bloqueos (siempre ``FOR NO KEY UPDATE``; orden de toda la API, docs/api/alertas.md, sección 3): invernadero → sistema → equipo. Cada mensaje es su
# propia transacción.

from django.db import transaction

from iot.models import NodoCentral, SistemaIoT
from iot.servicios import alertas_iot
from iot.servicios.auditoria_nodo import auditar_entrega
from maestros.servicios import alertas as api_alertas

TIPO_NODO_SIN_COMUNICACION = "iot_nodo_sin_comunicacion"


class SistemaDesconectado(Exception):
    """El sistema IoT ya no está activo (extensión *a): el mensaje se rechaza sin registrar ningún cambio. La vista lo responde 403 ``sistema_desconectado``."""


def sistema_por_resumen(resumen):
    """El sistema IoT cuyo ``token_resumen`` es ``resumen`` y que no está dado de baja (activo o desconectado), o ``None`` (verificación 5 del contrato:
    ``token_invalido``). Se busca por el resumen: no se comparan tokens (D-70, punto 3)."""
    return SistemaIoT.objects.select_related("invernadero").filter(token_resumen=resumen).exclude(estado_sistema="inactivo").first()


def _bloquear_sistema_y_nodo(sistema_id):
    """Bloquea invernadero → sistema → nodo, releídos, y devuelve ``(sistema, nodo)``. ``SistemaDesconectado`` si el sistema ya no está activo."""
    invernadero_id = SistemaIoT.objects.values_list("invernadero_id", flat=True).get(pk=sistema_id)
    api_alertas.bloquear_invernadero_para_alertas(invernadero_id)
    sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=sistema_id)
    if sistema.estado_sistema != SistemaIoT.Estado.ACTIVO:
        raise SistemaDesconectado()
    nodo = NodoCentral.objects.select_for_update(no_key=True).get(sistema_id=sistema_id)
    return sistema, nodo


def registrar_comunicacion(sistema_id, ahora):
    """Postcondición a: pone ``NodoCentral.ultima_comunicacion = ahora`` (el nodo queda «en línea») y resuelve la alerta ``iot_nodo_sin_comunicacion`` (clave
    ``nodo:<id>``) si estaba activa. Un lote vacío hace solo esto: es el latido (D-74, punto 2). Se audita solo si resolvió esa alerta. Corre en su propia
    transacción, antes de procesar los elementos."""
    with transaction.atomic():
        sistema, nodo = _bloquear_sistema_y_nodo(sistema_id)
        nodo.ultima_comunicacion = ahora
        nodo.save(update_fields=["ultima_comunicacion"])
        resuelta = alertas_iot.resolver_alerta_iot(sistema.invernadero_id, TIPO_NODO_SIN_COMUNICACION, f"nodo:{nodo.pk}")
        if resuelta is not None:
            auditar_entrega(sistema, "comunicacion", None, [nodo], alertas_resueltas=[resuelta])
        return resuelta


def al_volver_a_remoto(sistema):
    """Extensión 1b.3: cuando el nodo vuelve a ``remoto``, cada regla de actuación se evalúa desde la próxima lectura como si antes su condición no se cumpliera
    (última evaluación «sin evaluar», contador en cero), porque el control local pudo cambiar el estado de los actuadores. Corre en la transacción de ``registrar_modo``, con el sistema
    ya bloqueado. ``reglas`` se importa acá y no arriba: ``reglas`` importa ``comandos``, que importa este módulo."""
    from iot.models import ReglaActuacion
    from iot.servicios import reglas

    ids = ReglaActuacion.objects.filter(sensor__sistema=sistema, estado_regla=ReglaActuacion.Estado.ACTIVA).values_list("pk", flat=True)
    reglas.reiniciar_reglas(list(ids))


def registrar_modo(sistema_id, modo, ahora):
    """Extensión 1b y postcondición q: registra el modo informado (``remoto`` o ``local``, ya verificado por la traducción) y devuelve ``True`` si cambió.
    Si no cambió no escribe ni audita. Si volvió a ``remoto``, llama a ``al_volver_a_remoto``. «Local»: InfoPonia deja de evaluar reglas y de entregar comandos
    (IOT-05 e IOT-06 lo leen del modo guardado). ``ahora`` se recibe por contrato: los servicios nunca leen la hora por su cuenta."""
    with transaction.atomic():
        sistema, nodo = _bloquear_sistema_y_nodo(sistema_id)
        if nodo.modo == modo:
            return False
        antes = nodo.modo
        nodo.modo = modo
        nodo.save(update_fields=["modo"])
        auditar_entrega(sistema, "modo", None, [nodo], cambios={"modo": {"antes": antes, "despues": modo}})
        if modo == NodoCentral.Modo.REMOTO:
            al_volver_a_remoto(sistema)
        return True
