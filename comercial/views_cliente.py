# Portal público del cliente (COM-DCD-FLT; D-65 punto 3; docs/patrones/enlace_del_cliente.md, sección 4): el cliente decide un faltante sin cuenta, por el enlace que recibió por
# correo. `/cliente/<token>/` valida el enlace, guarda en la sesión SOLO el id y redirige a `/cliente/enlace/`, así el token no queda en la barra, el historial ni el encabezado
# `Referer`. Las páginas no leen `request.user` (una sesión de usuario abierta en el mismo navegador no cambia nada), no llevan menú ni campana y responden con `Cache-Control: no-store`,
# `Referrer-Policy: same-origin` (D-65 corregida el 23/11/2026: con `no-referrer` el navegador manda `Origin: null` y Django rechaza el CSRF) y `X-Robots-Tag: noindex`.
# Cada vista vuelve a leer el enlace por el id de la sesión y verifica que siga sirviendo. Las vistas solo orquestan: arman los datos, llaman al servicio y renderizan.
# `manejar` es el flujo de las dos pantallas (formulario → resumen → registrar) y lo comparte la del Vendedor (`views_faltantes.py`, extensión 1a). Sin JavaScript todo
# funciona: son páginas y un POST (el envío en curso lo resuelve `infoponia.js`).

import functools

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import EnlaceCliente
from comercial.servicios import confirmacion, enlaces, faltantes
from comercial.servicios.compra_ventas import texto_de_pesos

SESION = "enlace_cliente"
SESION_LISTO = "enlace_cliente_listo"
RUTA_DEL_PORTAL = "/cliente/enlace/"
RUTA_LISTO = "/cliente/enlace/listo/"
NO_SIRVE = ("enlace_no_sirve", "venta_no_decidible")  # los códigos que terminan el flujo (2a, 6a)


def _pagina_publica(vista):
    """Marca de las páginas del portal: exentas del login obligatorio, nunca guardadas en el caché y con los encabezados que evitan que el token o la página se filtren."""

    @functools.wraps(vista)
    def envuelta(request, *args, **kwargs):
        respuesta = vista(request, *args, **kwargs)
        respuesta["Cache-Control"] = "no-store, private"
        respuesta["Referrer-Policy"] = "same-origin"
        respuesta["X-Robots-Tag"] = "noindex"
        return respuesta

    return login_not_required(never_cache(vary_on_headers("HX-Request")(envuelta)))


def codigos_de(error):
    """Los códigos de un `ValidationError` con `error_dict`."""
    return [e.code for errores in error.error_dict.values() for e in errores]


def _por_campo(error):
    """`(errores por detalle, errores generales)` de un `ValidationError` del servicio: `decision_<id>` va al detalle; el resto, a la cabecera."""
    por_detalle, generales = {}, []
    for campo, lista in error.error_dict.items():
        for e in lista:
            if campo.startswith("decision_"):
                por_detalle.setdefault(int(campo.partition("_")[2]), []).append(e.messages[0])
            else:
                generales.append(e.messages[0])
    return por_detalle, generales


def _no_valido(request):
    """«Este enlace no es válido»: un token que no existe o una sesión sin enlace. Sin más datos."""
    return render(request, "comercial/cliente/no_valido.html", status=404)


def _es_confirmacion(enlace):
    return enlace.tipo == EnlaceCliente.Tipo.CONFIRMACION_ENTREGA


def _no_sirve(request, motivo, enlace):
    """«Este enlace no se puede usar», con el motivo y los datos de contacto del Vendedor del contrato (extensiones 2a y 6a de COM-DCD-FLT y de COM-CNF-ENT)."""
    if _es_confirmacion(enlace):
        contacto = confirmacion.contacto_de_la_entrega(enlace.entrega_id)
    else:
        contacto = faltantes.contacto_del_vendedor(enlace.compra_venta_id) if enlace.compra_venta_id else None
    contexto = {"motivo": enlaces.texto_del_motivo(motivo, enlace.tipo), "contacto": contacto, "es_confirmacion": _es_confirmacion(enlace)}
    return render(request, "comercial/cliente/no_sirve.html", contexto)


def _leer(post, datos):
    """`(decisiones, vistos)` del formulario: la elección de cada detalle pendiente y la cantidad disponible que mostró la pantalla (campo oculto, 6b)."""
    decisiones, vistos = {}, {}
    for fila in datos.pendientes:
        decisiones[fila.detalle_id] = post.get(f"decision_{fila.detalle_id}", "")
        visto = post.get(f"disponible_{fila.detalle_id}", "")
        vistos[fila.detalle_id] = int(visto) if visto.isdigit() else -1
    return decisiones, vistos


def _pantalla(request, plantilla, paso, datos, url, es_cliente, **extra):
    """Dibuja el formulario (paso 2) o el resumen (paso 4) con la plantilla de quien decide."""
    contexto = {"paso": paso, "datos": datos, "url": url, "es_cliente": es_cliente, "decisiones": {}, "errores": {}, "generales": [], **extra}
    # Una fila por detalle pendiente con lo elegido y sus errores (la plantilla no puede buscar por id en un diccionario).
    contexto["filas"] = [
        {"f": f, "decision": contexto["decisiones"].get(f.detalle_id, ""), "errores": contexto["errores"].get(f.detalle_id, [])} for f in datos.pendientes
    ]
    return render(request, plantilla, contexto)


def manejar(request, *, plantilla, url, enlace=None, vendedor=None, venta_id=None):
    """El flujo de COM-DCD-FLT (pasos 2 a 6) para el cliente (con `enlace`) o el Vendedor (con `vendedor` y `venta_id`). Devuelve `(respuesta, resultado)`: `resultado` es el
    `ResultadoDecision` (más el `resumen` mostrado) cuando se registró y entonces `respuesta` es `None`. Un `ValidationError` con `enlace_no_sirve` o `venta_no_decidible` sube al
    llamador (extensiones 2a y 6a: termina el flujo)."""
    es_cliente = enlace is not None
    datos = faltantes.datos_de_decision(enlace, vendedor=vendedor, venta_id=venta_id)
    if request.method == "GET":
        return _pantalla(request, plantilla, "formulario", datos, url, es_cliente), None
    decisiones, vistos = _leer(request.POST, datos)
    accion = request.POST.get("accion", "revisar")
    if accion == "cambiar":  # 4b: vuelve al formulario con lo elegido
        return _pantalla(request, plantilla, "formulario", datos, url, es_cliente, decisiones=decisiones), None
    cambiaron = {f.detalle_id: f.disponible for f in datos.pendientes if vistos[f.detalle_id] != f.disponible}
    if cambiaron:  # 6b antes de mostrar el resumen: la cantidad que vio ya no es la de hoy
        general = ["La cantidad disponible cambió mientras decidías. Revisá las cantidades y volvé a elegir."]
        mantenidas = {i: v for i, v in decisiones.items() if i not in cambiaron}
        return _pantalla(request, plantilla, "formulario", datos, url, es_cliente, decisiones=mantenidas, generales=general), None
    try:
        resumen = faltantes.resumen_de_decision(datos, decisiones)
    except ValidationError as error:  # 4a y 2b: por campo
        por_detalle, generales = _por_campo(error)
        return _pantalla(request, plantilla, "formulario", datos, url, es_cliente, decisiones=decisiones, errores=por_detalle, generales=generales), None
    if accion != "confirmar":  # paso 4
        return _pantalla(request, plantilla, "resumen", datos, url, es_cliente, decisiones=decisiones, resumen=resumen), None
    try:  # paso 6
        resultado = faltantes.registrar_decision(
            enlace.pk if enlace else None, decisiones, vistos, vendedor=vendedor, venta_id=venta_id
        )
    except ValidationError as error:
        if any(c in NO_SIRVE for c in codigos_de(error)):
            raise
        mantenidas = dict(decisiones)
        por_detalle, generales = _por_campo(error)
        for e in error.error_dict.get("__all__", []):
            if e.code == "disponible_cambio":  # 6b: lo afectado se vuelve a decidir; lo demás se conserva
                for i in e.params["disponibles"]:
                    mantenidas.pop(i, None)
        datos = faltantes.datos_de_decision(enlace, vendedor=vendedor, venta_id=venta_id)
        return _pantalla(request, plantilla, "formulario", datos, url, es_cliente, decisiones=mantenidas, errores=por_detalle, generales=generales), None
    return None, (resultado, resumen)


# ---- las páginas públicas ----


@_pagina_publica
@require_safe
def entrada(request, token):
    """`/cliente/<token>/`: valida el enlace; si sirve guarda el id en la sesión y redirige a una URL sin el token. Un token que no existe da «no es válido»; uno que no sirve, el motivo y
    el contacto del Vendedor (extensión 2a)."""
    enlace = enlaces.enlace_por_token(token)
    if enlace is None:
        return _no_valido(request)
    situacion = enlaces.situacion_del_enlace(enlace)
    if situacion == enlaces.SIRVE:
        request.session[SESION] = enlace.pk
        return redirect(RUTA_DEL_PORTAL)
    return _no_sirve(request, situacion, enlace)


@_pagina_publica
@require_http_methods(["GET", "POST"])
def decision(request):
    """`/cliente/enlace/`: GET muestra la venta y el formulario (paso 2); POST con `accion` = `revisar` (resumen del paso 4), `cambiar` (4b) o `confirmar` (paso 6). Según el tipo del enlace
    es la decisión de un faltante (COM-DCD-FLT) o la confirmación de una entrega (COM-CNF-ENT, `_confirmar`)."""
    enlace = enlaces.enlace_por_id(request.session.get(SESION))
    if enlace is None:
        return _no_valido(request)
    if _es_confirmacion(enlace):
        return _confirmar(request, enlace)
    try:
        respuesta, hecho = manejar(request, plantilla="comercial/cliente/decision.html", url=RUTA_DEL_PORTAL, enlace=enlace)
    except ValidationError as error:
        motivo = error.error_dict["__all__"][0].params["motivo"]
        return _no_sirve(request, motivo, enlace)
    if respuesta is not None:
        return respuesta
    _, resumen = hecho
    request.session[SESION_LISTO] = {
        "enlace": enlace.pk,
        "filas": [{"variedad": f["variedad"], "acepta": f["acepta"], "cantidad": f["cantidad"], "subtotal": texto_de_pesos(f["subtotal"])} for f in resumen.filas],
        "total": texto_de_pesos(resumen.monto_total),
        "cancelada": resumen.queda_cancelada,
    }
    return redirect(RUTA_LISTO)


@_pagina_publica
@require_safe
def listo(request):
    """`/cliente/enlace/listo/`: paso 9, «Gracias. Recibimos su decisión.» con lo que recibirá. Solo para quien acaba de decidir con ese enlace."""
    hecho = request.session.get(SESION_LISTO)
    if not hecho or hecho["enlace"] != request.session.get(SESION):
        return _no_valido(request)
    if hecho.get("tipo") == "confirmacion":
        return render(request, "comercial/cliente/confirmacion_lista.html", {"hecho": hecho})
    return render(request, "comercial/cliente/listo.html", {"hecho": hecho})


# ---- COM-CNF-ENT: confirmar la entrega (COM-06b; docs/casos_de_uso/comercial/confirmacion.md, «Pantallas») ----
# La página del cliente muestra su entrega y le pide la respuesta: «recibí y estoy conforme», «recibí pero tengo quejas» (una por tipo, con sus productos y su motivo) o «no recibí». Sin JavaScript el
# formulario es una página, el resumen es otra y el envío, un POST; con HTMX, al elegir la respuesta solo se vuelve a dibujar el bloque de quejas o de motivo (`redibujar`, que no valida: D-29).

SESION_ACUSE = "enlace_cliente_acuse"


def _errores_por_campo(error):
    """`{campo: [mensajes]}` de un `ValidationError` del servicio (el campo `__all__` va a la cabecera)."""
    return {campo: [e.messages[0] for e in lista] for campo, lista in error.error_dict.items()}


def _filas_de_quejas(datos, tipos, respuesta, errores):
    """Una fila por tipo de queja disponible con lo elegido y sus errores (la plantilla no puede buscar por clave en un diccionario). En «retraso», solo los productos con días de retraso."""
    por_tipo = {q.tipo: q for q in respuesta.quejas}
    filas = []
    for valor, texto in tipos:
        pedida = por_tipo.get(valor)
        productos = [
            {"id": l.detalle_id, "variedad": l.variedad, "dias": l.dias_de_retraso, "marcado": pedida is not None and l.detalle_id in pedida.lineas}
            for l in datos.lineas
            if valor != "retraso" or l.dias_de_retraso > 0
        ]
        filas.append(
            {
                "valor": valor,
                "texto": texto,
                "marcada": pedida is not None,
                "productos": productos,
                "motivo": pedida.motivo if pedida is not None else "",
                "obligatorio": valor != "retraso",
                "error_tipo": errores.get(f"queja_{valor}", []),
                "error_productos": errores.get(f"lineas_{valor}", []),
                "error_motivo": errores.get(f"motivo_{valor}", []),
            }
        )
    return filas


def _contexto_de_confirmacion(datos, respuesta, errores=None, **extra):
    errores = errores or {}
    tipos = confirmacion.tipos_de_queja_disponibles(datos)
    contexto = {
        "datos": datos,
        "url": RUTA_DEL_PORTAL,
        "respuesta": respuesta,
        "errores": errores,
        "error_respuesta": errores.get("respuesta", []),
        "generales": errores.get("__all__", []),
        "quejas": _filas_de_quejas(datos, tipos, respuesta, errores),
        "motivo_no_recibi": respuesta.motivo_no_recibi,
        "error_motivo_no_recibi": errores.get("motivo_no_recibi", []),
        # Sin elegir todavía se muestran los dos bloques (así funciona sin JavaScript); elegida la respuesta, solo el que corresponde.
        "ver_quejas": respuesta.respuesta in ("", confirmacion.CON_QUEJAS),
        "ver_motivo": respuesta.respuesta in ("", confirmacion.NO_RECIBI),
        "paso": "formulario",
    }
    contexto.update(extra)
    return contexto


def _campos_ocultos(respuesta):
    """Lo elegido, como campos ocultos del formulario del resumen (el envío vuelve a leerlo con `datos_de_respuesta`)."""
    campos = [("respuesta", respuesta.respuesta)]
    for q in respuesta.quejas:
        campos.append((f"queja_{q.tipo}", "1"))
        campos.extend((f"lineas_{q.tipo}", i) for i in q.lineas)
        campos.append((f"motivo_{q.tipo}", q.motivo))
    if respuesta.respuesta == confirmacion.NO_RECIBI:
        campos.append(("motivo_no_recibi", respuesta.motivo_no_recibi))
    return campos


def _confirmar(request, enlace):
    """El flujo de COM-CNF-ENT para el cliente. GET: la entrega y el formulario (paso 2). POST con `accion` = `redibujar` (HTMX: solo el bloque de quejas o de motivo, sin validar), `revisar` (el
    resumen del paso 4 o de 3b.2), `cambiar` (4a: vuelve al formulario con lo elegido) o `confirmar` (paso 6 o 3b.4). Un enlace que ya no sirve (2a, 6a) termina el flujo."""
    try:
        datos = confirmacion.datos_para_el_cliente(enlace)
    except ValidationError as error:
        return _no_sirve(request, error.error_dict["__all__"][0].params["motivo"], enlace)
    if request.method == "GET":
        return render(request, "comercial/cliente/confirmacion.html", _contexto_de_confirmacion(datos, confirmacion.DatosDeRespuesta()))
    respuesta = confirmacion.datos_de_respuesta(request.POST)
    accion = request.POST.get("accion", "revisar")
    if accion == "redibujar":
        plantilla = "comercial/cliente/_confirmacion_bloques.html" if request.headers.get("HX-Request") == "true" else "comercial/cliente/confirmacion.html"
        return render(request, plantilla, _contexto_de_confirmacion(datos, respuesta))
    if accion == "cambiar":
        return render(request, "comercial/cliente/confirmacion.html", _contexto_de_confirmacion(datos, respuesta))
    try:
        resumen = confirmacion.resumen_de_respuesta(datos, respuesta)
    except ValidationError as error:  # 3a.4a, 3a.4b, 3a.6a y 3b.1a: por campo
        return render(request, "comercial/cliente/confirmacion.html", _contexto_de_confirmacion(datos, respuesta, _errores_por_campo(error)))
    if accion != "confirmar":
        return render(request, "comercial/cliente/confirmacion.html", _contexto_de_confirmacion(datos, respuesta, paso="resumen", resumen=resumen, ocultas=_campos_ocultos(respuesta)))
    try:
        hecho = confirmacion.registrar_respuesta(enlace.pk, respuesta)
    except ValidationError as error:
        if "enlace_no_sirve" in codigos_de(error):  # 6a: ya se usó o venció mientras completaba la respuesta
            return _no_sirve(request, error.error_dict["__all__"][0].params["motivo"], enlace)
        return render(request, "comercial/cliente/confirmacion.html", _contexto_de_confirmacion(datos, respuesta, _errores_por_campo(error)))
    request.session[SESION_LISTO] = {
        "enlace": enlace.pk,
        "tipo": "confirmacion",
        "respuesta": hecho.respuesta,
        "quejas": [{"codigo": q.codigo, "tipo": q.get_tipo_queja_display()} for q in hecho.quejas],
        "acuse_enviado": hecho.acuse_enviado,
        "contacto": {"nombre": datos.contacto.nombre, "telefono": datos.contacto.telefono, "email": datos.contacto.email},
    }
    return redirect(RUTA_LISTO)


@_pagina_publica
@require_POST
def reenviar_acuse(request):
    """`/cliente/enlace/listo/reenviar/` (extensión 8a): reenvía el acuse al correo registrado del cliente, las veces que haga falta. Solo para quien acaba de responder con ese enlace (la sesión): al salir
    de la pantalla final no se puede volver, porque el enlace ya está usado (2a)."""
    hecho = request.session.get(SESION_LISTO)
    if not hecho or hecho["enlace"] != request.session.get(SESION) or hecho.get("tipo") != "confirmacion":
        return _no_valido(request)
    try:
        salio = confirmacion.reenviar_acuse(hecho["enlace"])
    except ValidationError:
        return _no_valido(request)
    hecho["acuse_enviado"] = salio
    request.session[SESION_LISTO] = hecho
    if salio:
        messages.success(request, "Le reenviamos el acuse a su correo.")
    else:
        messages.error(request, "No pudimos enviar el acuse. Puede volver a pedirlo.")
    return redirect(RUTA_LISTO)
