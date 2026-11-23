# Auditoría de lo que entrega el nodo central (postcondición z de IOT-ENT-INF; D-36; docs/casos_de_uso/iot/entregar_informacion.md, «Auditoría»).
# Una sola función para lecturas, estados, modo y anuncio: acción ``entrega_informacion_iot``, actor ``None`` (InfoPonia, como los procesos de D-56).
# El detalle tiene SOLO las claves ``datos`` y ``cambios`` de D-36. Nunca lleva el token (D-70). Las lecturas que no cambian nada no se auditan.

from core.models import RegistroAuditoria, referencia


def auditar_entrega(sistema, mensaje, identificador, afectados, cambios=None, alertas_generadas=(), alertas_resueltas=()):
    """Escribe UN registro ``entrega_informacion_iot`` y lo devuelve. ``mensaje`` es ``lectura``, ``estado``, ``modo``, ``anuncio`` o ``comunicacion`` (la
    comunicación que solo resolvió «nodo sin comunicación»); ``identificador`` es el texto o ``None``. ``cambios`` es ``{campo: {"antes", "despues"}}``
    solo con lo que cambió (los decimales y las fechas, ya como texto). ``afectados`` son instancias de modelo (el equipo, las alertas y, en el anuncio,
    los actuadores): las alertas generadas y resueltas se suman solas. Corre dentro de la transacción de quien llama."""
    datos = {
        "origen": "nodo_central",
        "sistema": referencia(sistema),
        "mensaje": mensaje,
        "identificador": identificador,
        "alertas_generadas": [referencia(alerta) for alerta in alertas_generadas],
        "alertas_resueltas": [referencia(alerta) for alerta in alertas_resueltas],
    }
    detalle = {"datos": datos}
    if cambios:
        detalle["cambios"] = cambios
    todos = [*afectados, *alertas_generadas, *alertas_resueltas]
    return RegistroAuditoria.objects.registrar(None, RegistroAuditoria.Accion.ENTREGA_INFORMACION_IOT, todos, detalle)
