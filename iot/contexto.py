# Lo que comparten las pantallas del módulo IoT por invernadero (IOT-02; docs/casos_de_uso/iot/sistema_iot.md, «Para los cinco», «Elección del invernadero»):
# la barra de contexto (``ctxBar`` del prototipo) con el invernadero elegido, el aviso de solo lectura (``opBanner``) y las ayudas de las vistas.
# Las vistas solo orquestan (docs/patrones/abm.md, sección 1): el alcance y las reglas están en ``iot/alcance.py`` y en los servicios.

from django.core.exceptions import NON_FIELD_ERRORS
from django.db.models.functions import Lower
from django.http import Http404

from iot.alcance import invernaderos_que_consulta, puede_operar

CLAVE_DE_LA_SESION = "iot_invernadero"


def es_htmx(request):
    """True si el pedido lo hizo HTMX (``HX-Request``)."""
    return request.headers.get("HX-Request") == "true"


def errores_del_servicio(error):
    """``({campo: [mensajes]}, [mensajes generales])`` de un ``ValidationError`` con errores por campo."""
    if not hasattr(error, "error_dict"):
        return {}, list(error.messages)
    errores = {campo: [e.message for e in lista] for campo, lista in error.error_dict.items()}
    return errores, errores.pop(NON_FIELD_ERRORS, [])


def codigos_del_servicio(error):
    """Los códigos de todos los errores de un ``ValidationError``."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


def elegir_invernadero(request, forzado=None):
    """El invernadero sobre el que trabaja la pantalla (``?invernadero=<id>`` y, si no viene, el recordado en la sesión ``iot_invernadero``; si no, el
    primero por nombre de los que ``request.user`` consulta; ``forzado`` es el id que manda una URL con id, como la ventana de regenerar el token). Un ``?invernadero=`` fuera del alcance o que no existe da ``Http404``. Devuelve
    ``(invernaderos, elegido)``; ``elegido`` es ``None`` si la cuenta no consulta ninguno. Recuerda la elección en la sesión."""
    invernaderos = list(invernaderos_que_consulta(request.user).order_by(Lower("nombre_invernadero"), "pk"))
    pedido = str(forzado) if forzado is not None else request.GET.get("invernadero", "").strip()
    elegido = None
    if pedido:
        elegido = next((i for i in invernaderos if str(i.pk) == pedido), None)
        if elegido is None:
            raise Http404("No existe ese invernadero.")
    else:
        recordado = str(request.session.get(CLAVE_DE_LA_SESION, ""))
        elegido = next((i for i in invernaderos if str(i.pk) == recordado), None) or (invernaderos[0] if invernaderos else None)
    if elegido is not None:
        request.session[CLAVE_DE_LA_SESION] = elegido.pk
    return invernaderos, elegido


def contexto_del_modulo(request, activa, forzado=None):
    """El contexto de una pantalla por invernadero: ``invernaderos``, ``elegido``, ``opera`` (si ``request.user`` lo opera) y ``pestana`` (la activa).
    ``aviso`` dice por qué un Gerente solo consulta o que opera por no haber Agrónomo activo (``opBanner`` del prototipo)."""
    invernaderos, elegido = elegir_invernadero(request, forzado)
    opera = elegido is not None and puede_operar(request.user, elegido)
    aviso = None
    if elegido is not None and request.user.rol == "gerente":
        agronomo = elegido.agronomo
        if opera:
            aviso = ("ok", "Operás este invernadero como Gerente porque no tiene Agrónomo activo.")
        elif agronomo is not None and agronomo.is_active:
            nombre = agronomo.get_full_name() or agronomo.email
            aviso = (
                "info",
                f"{elegido.nombre_invernadero} tiene Agrónomo activo ({nombre}). El Gerente lo consulta, pero lo opera solo cuando no hay Agrónomo activo.",
            )
    return {"invernaderos": invernaderos, "elegido": elegido, "opera": opera, "aviso": aviso, "pestana": activa, "es_gerente": request.user.rol == "gerente"}


def sin_cache(respuesta):
    """Marca la respuesta para que ni el navegador ni un intermediario la guarde (la pantalla del token, que se ve una sola vez: D-70)."""
    respuesta["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    respuesta["Pragma"] = "no-cache"
    return respuesta
