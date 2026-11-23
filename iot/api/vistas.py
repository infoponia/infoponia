# Vistas de la API del nodo (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md, «La API»; docs/api/nodo/respuestas_y_errores.md, sección 3). Solo traducen y
# orquestan (D-70, punto 4): NINGUNA regla de negocio acá. Sin sesión (``login_not_required``: ``LoginRequiredMiddleware``, SEG-13), sin CSRF y sin caché.
#
# Orden de verificación de un pedido (la primera que falla da la respuesta): 405 método, 401 token ausente, 429 límite, 401 token inválido, 403 sistema
# desconectado, 413 tamaño, 415 tipo, 400 JSON, 400 forma, 413 elementos. Superadas, se registra la comunicación del nodo (su propia transacción) y se procesa
# cada elemento (una transacción por elemento). Un error inesperado en un elemento es ``error_interno`` en ese y los demás se procesan igual.
# Registro técnico: ``logging.getLogger("iot.api")``. NUNCA el token ni el encabezado ``Authorization``: de ellos solo se calcula el resumen.

import logging
from decimal import Decimal

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import RequestDataTooBig
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from iot.api import autenticacion, limites, reloj, traduccion
from iot.api.respuestas import respuesta_error, respuesta_ok
from iot.models import SistemaIoT
from iot.servicios import anuncios, estados, lecturas, nodo

logger = logging.getLogger("iot.api")


class _Rechazo(Exception):
    """Un pedido rechazado entero: lleva la respuesta ya armada."""

    def __init__(self, respuesta):
        self.respuesta = respuesta


def _recibir(request, metodo, ahora, con_cuerpo=True):
    """Las verificaciones 2 a 9 del contrato. Devuelve ``(sistema, objeto JSON o None)`` o lanza ``_Rechazo``."""
    if request.method != metodo:
        raise _Rechazo(
            respuesta_error(405, "metodo_no_permitido", ahora, f"Esta ruta solo acepta {metodo}.", encabezados={"Allow": metodo})
        )
    resumen = autenticacion.resumen_del_encabezado(request.headers.get("Authorization"))
    if resumen is None:
        raise _Rechazo(respuesta_error(401, "token_ausente", ahora, "Falta el encabezado «Authorization: Bearer <token>»."))
    segundos = limites.contar_pedido(resumen, ahora)
    if segundos is not None:
        raise _Rechazo(
            respuesta_error(
                429,
                "demasiados_pedidos",
                ahora,
                f"Se superaron los {limites.PEDIDOS_POR_MINUTO} pedidos por minuto. Reintentá en {segundos} segundos.",
                encabezados={"Retry-After": str(segundos)},
            )
        )
    sistema = nodo.sistema_por_resumen(resumen)
    if sistema is None:
        raise _Rechazo(respuesta_error(401, "token_invalido", ahora, "El token no corresponde a ningún sistema IoT vigente."))
    if sistema.estado_sistema != SistemaIoT.Estado.ACTIVO:
        raise _Rechazo(respuesta_error(403, "sistema_desconectado", ahora, "El sistema IoT de este nodo está desconectado en InfoPonia."))
    if not con_cuerpo:
        return sistema, None
    largo = request.META.get("CONTENT_LENGTH")
    demasiado_grande = respuesta_error(413, "mensaje_demasiado_grande", ahora, "El cuerpo pesa más de 256 KB.")
    if largo and largo.isdigit() and int(largo) > limites.BYTES_POR_PEDIDO:
        raise _Rechazo(demasiado_grande)
    try:
        cuerpo = request.body
    except RequestDataTooBig:
        raise _Rechazo(demasiado_grande) from None
    if len(cuerpo) > limites.BYTES_POR_PEDIDO:
        raise _Rechazo(demasiado_grande)
    if request.content_type != "application/json" or request.content_params.get("charset", "utf-8").lower().replace("-", "") != "utf8":
        raise _Rechazo(respuesta_error(415, "tipo_no_soportado", ahora, "El cuerpo tiene que ser JSON (Content-Type: application/json)."))
    try:
        return sistema, traduccion.leer_objeto(cuerpo)
    except traduccion.JsonInvalido as error:
        raise _Rechazo(respuesta_error(400, "json_invalido", ahora, str(error))) from None


def _mal_formado(error, ahora):
    extra = {"campo": error.campo}
    if error.indice is not None:
        extra["indice"] = error.indice
    return respuesta_error(400, "mensaje_mal_formado", ahora, error.detalle, **extra)


def _limitar_elementos(lista, ahora):
    """Verificación 11: hasta 500 elementos por pedido."""
    if len(lista) > limites.ELEMENTOS_POR_PEDIDO:
        raise _Rechazo(
            respuesta_error(413, "demasiados_elementos", ahora, f"El pedido trae {len(lista)} elementos; el máximo es {limites.ELEMENTOS_POR_PEDIDO}.")
        )


def _comunicacion(sistema, ahora):
    """Postcondición a, en su propia transacción. Si el sistema se desconectó justo ahora, 403 sin registrar nada."""
    try:
        nodo.registrar_comunicacion(sistema.pk, ahora)
    except nodo.SistemaDesconectado:
        raise _Rechazo(respuesta_error(403, "sistema_desconectado", ahora, "El sistema IoT de este nodo está desconectado en InfoPonia.")) from None


def _atender(request, tratar, metodo="POST", con_cuerpo=True):
    """Envoltura común: lee la hora UNA vez, aplica las verificaciones y llama a ``tratar(sistema, objeto, ahora)``. Un fallo inesperado es 500 ``error_interno``."""
    ahora = reloj.ahora()
    try:
        sistema, objeto = _recibir(request, metodo, ahora, con_cuerpo)
        return tratar(sistema, objeto, ahora)
    except _Rechazo as rechazo:
        return rechazo.respuesta
    except Exception:
        logger.exception("Falla inesperada al atender un pedido del nodo")
        return respuesta_error(500, "error_interno", ahora, "InfoPonia no pudo procesar el pedido. Reintentá más tarde.")


def _texto_del_valor(valor):
    """El valor recibido para el registro técnico (``Decimal`` como número; el resto, tal cual)."""
    return str(valor) if isinstance(valor, (Decimal, int, str)) else repr(valor)


def _procesar_elementos(sistema, elementos, procesar, rechazado):
    """Recorre los elementos traducidos: uno mal formado o un error inesperado no impiden procesar los demás. Devuelve la lista de resultados del contrato."""
    resultados = []
    for elemento in elementos:
        if isinstance(elemento, traduccion.ElementoMalFormado):
            logger.warning("Sistema %s · %s · %s", sistema.pk, elemento.identificador_enviado, elemento.motivo)
            resultados.append((elemento, rechazado(elemento.motivo, elemento.detalle)))
            continue
        try:
            resultado = procesar(elemento)
        except Exception:
            logger.exception("Sistema %s · %s · error_interno", sistema.pk, elemento.identificador_enviado)
            resultado = rechazado("error_interno", "InfoPonia no pudo procesar este elemento; los demás se procesaron.")
        if resultado.get("resultado") in ("rechazada", "rechazado"):
            logger.warning("Sistema %s · %s · %s", sistema.pk, elemento.identificador_enviado, resultado.get("motivo"))
        resultados.append((elemento, resultado))
    return resultados


def _con_indice(resultados):
    """Los resultados con ``indice`` e ``identificador`` al principio, como pide el contrato."""
    return [{"indice": e.indice, "identificador": e.identificador_enviado, **resultado} for e, resultado in resultados]


@login_not_required
@csrf_exempt
@never_cache
def lecturas_vista(request):
    """``POST lecturas``: un lote (también el latido, si viene vacío)."""

    def tratar(sistema, objeto, ahora):
        try:
            lista = traduccion.lista_de_lecturas(objeto)
        except traduccion.MensajeMalFormado as error:
            return _mal_formado(error, ahora)
        _limitar_elementos(lista, ahora)
        _comunicacion(sistema, ahora)
        contexto = lecturas.contexto_del_mensaje(sistema, ahora)

        def procesar(lectura):
            r = lecturas.registrar_lectura(contexto, lectura, ahora)
            if r.resultado == "aceptada":
                datos = {"resultado": "aceptada"}
                if r.valida is not None:
                    datos["valida"] = r.valida
                return datos | {"atrasada": r.atrasada}
            if r.resultado == "duplicada":
                return {"resultado": "duplicada"}
            return {"resultado": "rechazada", "motivo": r.motivo, "detalle": r.detalle}

        resultados = _con_indice(
            _procesar_elementos(
                sistema,
                traduccion.traducir_lecturas(lista),
                procesar,
                lambda motivo, detalle: {"resultado": "rechazada", "motivo": motivo, "detalle": detalle},
            )
        )
        cuenta = lambda clave: sum(1 for r in resultados if r["resultado"] == clave)  # noqa: E731
        return respuesta_ok(
            {"aceptadas": cuenta("aceptada"), "duplicadas": cuenta("duplicada"), "rechazadas": cuenta("rechazada"), "resultados": resultados}, ahora
        )

    return _atender(request, tratar)


@login_not_required
@csrf_exempt
@never_cache
def estados_vista(request):
    """``POST estados``: el estado de uno o más equipos."""

    def tratar(sistema, objeto, ahora):
        try:
            lista = traduccion.lista_de_estados(objeto)
        except traduccion.MensajeMalFormado as error:
            return _mal_formado(error, ahora)
        _limitar_elementos(lista, ahora)
        _comunicacion(sistema, ahora)

        def procesar(estado):
            r = estados.registrar_estado(sistema.pk, estado, ahora)
            if r.resultado == "aceptado":
                return {"resultado": "aceptado"}
            return {"resultado": "rechazado", "motivo": r.motivo, "detalle": r.detalle}

        resultados = _con_indice(
            _procesar_elementos(
                sistema,
                traduccion.traducir_estados(lista),
                procesar,
                lambda motivo, detalle: {"resultado": "rechazado", "motivo": motivo, "detalle": detalle},
            )
        )
        cuenta = lambda clave: sum(1 for r in resultados if r["resultado"] == clave)  # noqa: E731
        return respuesta_ok({"aceptados": cuenta("aceptado"), "rechazados": cuenta("rechazado"), "resultados": resultados}, ahora)

    return _atender(request, tratar)


@login_not_required
@csrf_exempt
@never_cache
def modo_vista(request):
    """``POST modo``: ``remoto`` o ``local``."""

    def tratar(sistema, objeto, ahora):
        try:
            modo = traduccion.traducir_modo(objeto)
        except traduccion.MensajeMalFormado as error:
            return _mal_formado(error, ahora)
        _comunicacion(sistema, ahora)
        try:
            cambio = nodo.registrar_modo(sistema.pk, modo, ahora)
        except nodo.SistemaDesconectado:
            raise _Rechazo(respuesta_error(403, "sistema_desconectado", ahora, "El sistema IoT de este nodo está desconectado en InfoPonia.")) from None
        return respuesta_ok({"resultado": "aceptado", "modo": modo, "cambio": cambio}, ahora)

    return _atender(request, tratar)


@login_not_required
@csrf_exempt
@never_cache
def anuncio_vista(request):
    """``POST anuncio``: la lista completa de equipos. Entero o nada."""

    def tratar(sistema, objeto, ahora):
        try:
            lista = traduccion.lista_de_equipos(objeto)
            _limitar_elementos(lista, ahora)
            equipos = traduccion.traducir_anuncio(lista)
        except traduccion.MensajeMalFormado as error:
            return _mal_formado(error, ahora)
        _comunicacion(sistema, ahora)
        try:
            resultado = anuncios.registrar_anuncio(sistema.pk, equipos, ahora)
        except nodo.SistemaDesconectado:
            raise _Rechazo(respuesta_error(403, "sistema_desconectado", ahora, "El sistema IoT de este nodo está desconectado en InfoPonia.")) from None
        return respuesta_ok(
            {
                "resultado": "aceptado",
                "equipos": resultado.equipos,
                "actuadores": [
                    {"identificador": a.identificador, "compatibilidad": a.compatibilidad, "acciones_incompatibles": a.acciones_incompatibles}
                    for a in resultado.actuadores
                ],
                "sin_registrar": resultado.sin_registrar,
            },
            ahora,
        )

    return _atender(request, tratar)


@login_not_required
@csrf_exempt
@never_cache
def ruta_inexistente(request, *args, **kwargs):
    """Cualquier otra ruta bajo ``/api/iot/v1/``: 404 ``ruta_inexistente`` en JSON, sin pedir token (verificación 1 del contrato)."""
    return respuesta_error(404, "ruta_inexistente", reloj.ahora(), "La ruta no existe en la API v1.")
