# Límites de la API del nodo (D-70, punto 5; docs/api/nodo/respuestas_y_errores.md, sección 2). Los números son del contrato: si se ajustan,
# se ajustan acá y en ese documento, sin cambiar de versión.
#
# El contador de pedidos vive en la caché por defecto de Django (sin dependencias nuevas, D-70 punto 5): alcanza para un solo proceso de
# gunicorn; con más procesos, cada uno cuenta aparte (se anota si cambia el despliegue). Ventana FIJA por minuto de reloj, por nodo (por el
# resumen del token), y cuenta todo pedido que trae un token, aceptado o no (D-74, punto 8).

from datetime import timezone as zona

from django.core.cache import cache

PEDIDOS_POR_MINUTO = 120
BYTES_POR_PEDIDO = 262144
ELEMENTOS_POR_PEDIDO = 500
# La clave de un minuto vive el doble de la ventana: sobra para que el último pedido del minuto no la encuentre vencida.
SEGUNDOS_DE_LA_CLAVE = 120


def contar_pedido(resumen, ahora):
    """Cuenta un pedido del nodo ``resumen`` en el minuto de ``ahora`` y devuelve ``None`` si todavía está dentro del límite, o los segundos de
    ``Retry-After`` (los que faltan para el minuto siguiente, de 1 a 60) si ya pasó los ``PEDIDOS_POR_MINUTO``. Clave
    ``iot:pedidos:<16 primeros caracteres del resumen>:<AAAAMMDDHHMM>`` con ``cache.add`` y ``cache.incr`` (atómicas): dos nodos no se mezclan y
    el minuto siguiente vuelve a empezar."""
    momento = ahora.astimezone(zona.utc)
    clave = f"iot:pedidos:{resumen[:16]}:{momento:%Y%m%d%H%M}"
    cache.add(clave, 0, SEGUNDOS_DE_LA_CLAVE)
    cantidad = cache.incr(clave)
    if cantidad > PEDIDOS_POR_MINUTO:
        return 60 - momento.second
    return None
