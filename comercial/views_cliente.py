# Portal público del cliente (COM-DCD-FLT; D-65 punto 3; docs/patrones/enlace_del_cliente.md, sección 4): el cliente decide un faltante sin cuenta, por el enlace que recibió por
# correo. `/cliente/<token>/` valida el enlace, guarda en la sesión SOLO el id y redirige a `/cliente/enlace/`, así el token no queda en la barra, el historial ni el encabezado
# `Referer`. Las páginas no leen `request.user` (una sesión de usuario abierta en el mismo navegador no cambia nada), no llevan menú ni campana y responden con `Cache-Control: no-store`,
# `Referrer-Policy: same-origin` (D-65 corregida el 23/11/2026: con `no-referrer` el navegador manda `Origin: null` y Django rechaza el CSRF) y `X-Robots-Tag: noindex`.
# Cada vista vuelve a leer el enlace por el id de la sesión y verifica que siga sirviendo. Las vistas solo orquestan: arman los datos, llaman al servicio y renderizan.
# `manejar` es el flujo de las dos pantallas (formulario → resumen → registrar) y lo comparte la del Vendedor (`views_faltantes.py`, extensión 1a). Sin JavaScript todo
# funciona: son páginas y un POST (el envío en curso lo resuelve `infoponia.js`).

import functools

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import enlaces, faltantes
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


def _no_sirve(request, motivo, venta_id=None):
    """«Este enlace no se puede usar», con el motivo y los datos de contacto del Vendedor (extensión 2a)."""
    contacto = faltantes.contacto_del_vendedor(venta_id) if venta_id else None
    return render(request, "comercial/cliente/no_sirve.html", {"motivo": enlaces.MOTIVOS.get(motivo, "Este enlace ya no puede usarse."), "contacto": contacto})


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
    return _no_sirve(request, situacion, enlace.compra_venta_id)


@_pagina_publica
@require_http_methods(["GET", "POST"])
def decision(request):
    """`/cliente/enlace/`: GET muestra la venta y el formulario (paso 2); POST con `accion` = `revisar` (resumen del paso 4), `cambiar` (4b) o `confirmar` (paso 6)."""
    enlace = enlaces.enlace_por_id(request.session.get(SESION))
    if enlace is None:
        return _no_valido(request)
    try:
        respuesta, hecho = manejar(request, plantilla="comercial/cliente/decision.html", url=RUTA_DEL_PORTAL, enlace=enlace)
    except ValidationError as error:
        motivo = error.error_dict["__all__"][0].params["motivo"]
        return _no_sirve(request, motivo, enlace.compra_venta_id)
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
    return render(request, "comercial/cliente/listo.html", {"hecho": hecho})
