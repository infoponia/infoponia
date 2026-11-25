# Solicitudes de revisión de `comercial` (COM-06a): la única función que crea una `SolicitudRevision` y escribe su `entrega` y su número (D-68, punto 5). La usa
# `concrecion.crear_discrepancia` (COM-06a) y la usará COM-06b para las quejas. No audita ni notifica: devuelve lo que creó para el registro del caso de uso (D-36).
# Fuente: docs/modelo/comercial.md («SolicitudRevision», «DiscrepanciaEntrega y LineaDiscrepancia»), D-68 puntos 5, y D-52 punto 3 (la secuencia de números).

from django.db import connection, transaction
from django.utils import timezone

from comercial.models import SolicitudRevision


def siguiente_numero():
    """El número de la próxima solicitud, de la secuencia ``comercial_solicitud_numero_seq`` (D-52 punto 3, como ``compra_ventas.siguiente_numero``). Puede haber huecos si una
    transacción se deshace (``docs/temas_abiertos.md``, «Huecos en el número de orden»). Nunca un ``max()+1``."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_solicitud_numero_seq')")
        return cursor.fetchone()[0]


def crear_solicitud(clase, entrega, **campos):
    """Crea una solicitud de la ``clase`` hija (`DiscrepanciaEntrega`; COM-06b suma `Queja`) para ``entrega``, «pendiente», con el número de la secuencia y la fecha de hoy
    (``fecha_solicitud`` puede pasarse en ``campos``). Corre dentro de la transacción del caso de uso que la llama (sin ella, `RuntimeError`). El tipo lo fija la hija."""
    if transaction.get_autocommit():
        raise RuntimeError("`crear_solicitud` corre dentro de la transacción del caso de uso que la llama.")
    if not issubclass(clase, SolicitudRevision):
        raise TypeError("`clase` tiene que ser una hija de `SolicitudRevision`.")
    campos.setdefault("fecha_solicitud", timezone.localdate())
    return clase.objects.create(entrega=entrega, numero=siguiente_numero(), **campos)

