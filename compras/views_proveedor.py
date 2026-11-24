# Portal público del proveedor (CMP-ENV-COT; D-88 punto 4; docs/patrones/enlace_del_proveedor.md, secciones 3 y 4): el proveedor cotiza sin cuenta por el
# enlace que recibió por correo. ``/proveedor/<token>/`` valida el enlace, guarda en la sesión SOLO el id y redirige a ``/proveedor/enlace/``, así el token no
# queda en la barra ni en el historial ni en el encabezado ``Referer``. Las páginas no leen ``request.user`` (una sesión de usuario abierta en el mismo
# navegador no cambia nada), no llevan menú ni campana y responden con ``Cache-Control: no-store``, ``Referrer-Policy: no-referrer`` y ``X-Robots-Tag:
# noindex``. Cada vista vuelve a leer el enlace por el id de la sesión y verifica que siga sirviendo: la sesión no da acceso a otro pedido. Las vistas solo
# orquestan: arman los datos del formulario, llaman al servicio (``compras/servicios/cotizaciones.py``) y renderizan.

import functools
from datetime import date
from decimal import ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from compras import precios
from compras.errores import ErrorDeCompras
from compras.models import DetallePedido
from compras.servicios import cotizaciones, enlaces
from inventario.unidades import Unidad

SESION = "enlace_proveedor"
RUTA_DEL_PORTAL = "/proveedor/enlace/"

# El motivo de cada situación en que el enlace no sirve (extensión 2a de CMP-ENV-COT): se muestra sin ningún dato del pedido.
MOTIVOS = {
    enlaces.VENCIDO: "El plazo para cotizar terminó.",
    enlaces.PEDIDO_CANCELADO: "El pedido fue cancelado.",
    enlaces.PEDIDO_CERRADO: "El pedido ya no está recibiendo cotizaciones.",
    enlaces.PROVEEDOR_INACTIVO: "El proveedor no está activo.",
    enlaces.REEMPLAZADO: "Este enlace fue reemplazado por uno más nuevo.",
    enlaces.ANULADO: "Este enlace fue anulado.",
}


def _pagina_publica(vista):
    """Marca de las páginas del portal: exentas del login obligatorio, nunca guardadas en el caché del navegador y con los encabezados que evitan
    que el token o la página se filtren (``Referrer-Policy`` y ``X-Robots-Tag``)."""

    @functools.wraps(vista)
    def envuelta(request, *args, **kwargs):
        respuesta = vista(request, *args, **kwargs)
        respuesta["Cache-Control"] = "no-store, private"
        # D-88 punto 4 pedía ``no-referrer``, pero con esa política los navegadores mandan ``Origin: null`` en los POST del mismo sitio y Django rechaza el CSRF
        # (lo encontró una verificación con navegador real; el cliente de Django no lo ve). ``same-origin`` protege igual: el token solo viaja en ``/proveedor/<token>/``, que responde una
        # redirección sin página (nada que pida recursos con ese ``Referer``), y a otro sitio no se manda ningún ``Referer``.
        respuesta["Referrer-Policy"] = "same-origin"
        respuesta["X-Robots-Tag"] = "noindex"
        return respuesta

    return login_not_required(never_cache(envuelta))


def _no_valido(request):
    """«Este enlace no es válido»: un token que no existe o una sesión sin enlace (o con un id que no existe). Sin más datos."""
    return render(request, "compras/proveedor/no_valido.html", status=404)


def _no_sirve(request, situacion):
    """«Este enlace no se puede usar», con el motivo y sin ningún dato del pedido (extensión 2a)."""
    return render(request, "compras/proveedor/no_sirve.html", {"motivo": MOTIVOS.get(situacion, "Este enlace ya no puede usarse.")})


@_pagina_publica
@require_safe
def entrada(request, token):
    """``/proveedor/<token>/``: valida el enlace; si sirve (o ya cotizó y todavía puede ver su cotización) guarda el id en la sesión y redirige a una URL
    sin el token. Un token que no existe da «no es válido»; uno que no sirve, el motivo."""
    enlace = enlaces.enlace_por_token(token)
    if enlace is None:
        return _no_valido(request)
    situacion = enlaces.situacion_del_enlace(enlace)
    if situacion in (enlaces.SIRVE, enlaces.SOLO_LECTURA):
        request.session[SESION] = enlace.pk
        return redirect(RUTA_DEL_PORTAL)
    return _no_sirve(request, situacion)


def _lineas_de_la_pantalla(pedido, escrito=None, errores=None):
    """Los detalles del pedido tal como los ve el proveedor (insumo, descripción, unidad, cantidad pedida, invernadero de destino y su dirección), cada
    uno con lo que escribió y sus errores. **Sin el precio de referencia.**"""
    escrito, errores = escrito or {}, errores or {}
    detalles = DetallePedido.objects.filter(pedido=pedido).select_related(
        "insumo_invernadero__insumo", "insumo_invernadero__invernadero__direccion"
    )
    filas = []
    for detalle in detalles:
        insumo = detalle.insumo_invernadero.insumo
        invernadero = detalle.insumo_invernadero.invernadero
        filas.append(
            {
                "id": detalle.pk,
                "insumo": insumo.nombre_insumo,
                "descripcion": insumo.descripcion_insumo,
                "unidad_medida": insumo.unidad_medida_insumo,
                "unidad": Unidad(insumo.unidad_medida_insumo).label,
                "pedida": detalle.cantidad_detalle,
                "invernadero": invernadero.nombre_invernadero,
                "direccion": str(invernadero.direccion),
                "escrito": escrito.get(detalle.pk, {}),
                "errores": errores.get(detalle.pk, {}),
            }
        )
    return filas


def _leer_formulario(datos, pedido):
    """El formulario del portal como lo espera el servicio: ``(modo, lineas, escrito, validez_texto, validez, observaciones)``. Una línea sin cantidad,
    precio ni plazo no se cotiza (los detalles que no elige quedan sin cotizar)."""
    modo = "unitario" if datos.get("modo") == "unitario" else "total"
    lineas, escrito = [], {}
    for detalle in DetallePedido.objects.filter(pedido=pedido).order_by("id"):
        cantidad = datos.get(f"cantidad_{detalle.pk}", "").strip()
        precio = datos.get(f"precio_{detalle.pk}", "").strip()
        plazo = datos.get(f"plazo_{detalle.pk}", "").strip()
        escrito[detalle.pk] = {"cantidad": cantidad, "precio": precio, "plazo": plazo}
        if cantidad or precio or plazo:
            lineas.append((detalle.pk, cantidad, precio if modo == "total" else None, precio if modo == "unitario" else None, plazo))
    validez_texto = datos.get("validez", "").strip()
    try:
        validez = date.fromisoformat(validez_texto)
    except ValueError:
        validez = None
    return modo, lineas, escrito, validez_texto, validez, datos.get("observaciones", "").strip()


def _errores_por_campo(error):
    """Los errores de un ``ValidationError`` del servicio, repartidos por línea (``cantidad_<id>``, ``precio_<id>``, ``plazo_<id>``, ``detalle_<id>``) y
    generales (``lineas``, ``validez``, ``observaciones``)."""
    por_linea, generales = {}, {}
    for campo, lista in error.error_dict.items():
        textos = [e.messages[0] for e in lista]
        tipo, _, identificador = campo.partition("_")
        if tipo in ("cantidad", "precio", "plazo", "detalle") and identificador.isdigit():
            por_linea.setdefault(int(identificador), {})["detalle" if tipo == "detalle" else tipo] = textos
        else:
            generales[campo] = textos
    return por_linea, generales


def _formulario(request, enlace, **extra):
    """Dibuja el formulario de cotización (paso 2 y volver a corregir un dato del resumen)."""
    pedido = enlace.invitacion.pedido
    contexto = {
        "enlace": enlace,
        "pedido": pedido,
        "proveedor": enlace.invitacion.proveedor,
        "modo": "total",
        "validez": cotizaciones.proponer_validez(pedido).isoformat(),
        "observaciones": "",
        "lineas": _lineas_de_la_pantalla(pedido),
        "errores": {},
    }
    contexto.update(extra)
    return render(request, "compras/proveedor/portal.html", contexto)


def _solo_lectura(request, enlace):
    """Extensión 2b: la cotización que el proveedor ya envió, en solo lectura (hasta el final del día de la fecha límite, H15.2)."""
    cotizacion = cotizaciones.cotizacion_del_enlace(enlace)
    return render(
        request,
        "compras/proveedor/solo_lectura.html",
        {
            "pedido": enlace.invitacion.pedido,
            "proveedor": enlace.invitacion.proveedor,
            "cotizacion": cotizacion,
            "lineas": cotizaciones.lineas_para_mostrar(cotizacion) if cotizacion else [],
            "monto": cotizacion.monto_cotizacion if cotizacion else None,
        },
    )


@_pagina_publica
@require_http_methods(["GET", "POST"])
def portal(request):
    """``/proveedor/enlace/``: el portal. GET muestra el pedido y el formulario (o, con el enlace ya usado, la cotización en solo lectura). POST con
    ``accion`` = ``revisar`` (valida y muestra el resumen del paso 9), ``enviar`` (paso 10: registra) o ``editar`` (vuelve a corregir sin validar)."""
    enlace = enlaces.enlace_por_id(request.session.get(SESION))
    if enlace is None:
        return _no_valido(request)
    situacion = enlaces.situacion_del_enlace(enlace)
    if situacion == enlaces.SOLO_LECTURA:
        return _solo_lectura(request, enlace)
    if situacion != enlaces.SIRVE:
        return _no_sirve(request, situacion)
    if request.method == "GET":
        return _formulario(request, enlace)

    pedido = enlace.invitacion.pedido
    modo, lineas, escrito, validez_texto, validez, observaciones = _leer_formulario(request.POST, pedido)
    accion = request.POST.get("accion", "revisar")
    base = {"modo": modo, "validez": validez_texto, "observaciones": observaciones}

    def con_errores(error):
        por_linea, generales = _errores_por_campo(error)
        return _formulario(
            request, enlace, **base, lineas=_lineas_de_la_pantalla(pedido, escrito, por_linea), errores=generales
        )

    if accion == "editar":
        return _formulario(request, enlace, **base, lineas=_lineas_de_la_pantalla(pedido, escrito))
    try:
        if accion == "enviar":
            cotizaciones.registrar_cotizacion(enlace.pk, lineas, validez, observaciones)
        else:
            resumen = cotizaciones.resumir_cotizacion(enlace, lineas, validez, observaciones)
    except ValidationError as error:
        return con_errores(error)
    except ErrorDeCompras as error:
        if error.codigo == "ya_cotizo":  # extensión 11b: la otra pestaña ya envió
            return redirect(RUTA_DEL_PORTAL)
        return _no_sirve(request, error.datos.get("situacion"))
    if accion == "enviar":
        messages.success(request, "Recibimos su cotización. Ya no puede modificarla ni enviar otra.")
        return redirect(RUTA_DEL_PORTAL)
    filas = []
    for linea in resumen.lineas:
        unitario = linea.unitario.quantize(precios.DOS_DECIMALES, ROUND_HALF_UP)
        insumo = linea.detalle.insumo_invernadero.insumo
        filas.append(
            {
                "linea": linea,
                "insumo": insumo.nombre_insumo,
                "invernadero": linea.detalle.insumo_invernadero.invernadero.nombre_invernadero,
                "unidad_medida": insumo.unidad_medida_insumo,
                "unidad": Unidad(insumo.unidad_medida_insumo).label,
                # D-89 punto 7: si el unitario mostrado × la cantidad no da el total, se muestra solo el total, que manda.
                "unitario": unitario if precios.total_desde_unitario(unitario, linea.cantidad) == linea.total else None,
            }
        )
    return render(
        request,
        "compras/proveedor/resumen.html",
        {
            "enlace": enlace,
            "pedido": pedido,
            "proveedor": enlace.invitacion.proveedor,
            "resumen": resumen,
            "filas": filas,
            "todas": [{"id": detalle_id, **datos} for detalle_id, datos in escrito.items()],
            **base,
        },
    )
