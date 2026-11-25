# Vistas de «Contratos» de `comercial` (COM-02): la lista y la ficha de compra-ventas (COM-CNS-CVT), el formulario «Nueva compra-venta» con su
# recálculo por HTMX, el resumen y la confirmación (COM-REG-CVT), el comprobante imprimible y «Reenviar comprobante». Las vistas solo
# orquestan: arman los datos del pedido, llaman al servicio y renderizan (docs/patrones/abm.md, sección 1). Sin JavaScript todo funciona:
# cada cambio se manda con «Actualizar» y el resumen es una página. Nunca se valida al tipear (`.claude/rules/interfaz.md`): solo los
# selectores redibujan, sin validar, con `hx-swap="innerHTML show:none"`.

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import CompraVenta, PagoCliente
from comercial.servicios import clientes as api_clientes
from comercial.servicios import comprobantes, compra_ventas
from comercial.servicios.compra_ventas import NO_CAMPO, DatosDeCancelacionDeVenta, DatosDeCompraVenta, FiltrosDeCompraVentas, Renglon, texto_de_pesos
from core.acceso import rol_requerido
from core.models import Usuario

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR
ESTADOS = CompraVenta.Estado.choices
MENSAJE_DE_STOCK = "El stock cambió mientras cargabas la venta."


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


# ---- lista y ficha (COM-CNS-CVT) ----


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def contratos(request):
    """Pestaña «Contratos» (``tabContratos`` del prototipo, rama ``cv``; COM-CNS-CVT, reglas 1 a 3): las compra-ventas del alcance, con filtros
    en la URL (se pueden compartir y volver con «Atrás») y páginas de 50. Con ``?tipo=suministro`` (el selector «Compra-ventas / Suministros»,
    ``ctrSel``, COM-03a) muestra los suministros (COM-CNS-SUM). No audita."""
    if request.GET.get("tipo") == "suministro":
        from comercial import views_suministros  # la vista de suministros importa de este módulo: se importa acá para no cruzarlos

        return views_suministros.lista(request)
    filtros = FiltrosDeCompraVentas.desde_get(request.GET)
    es_gerente = request.user.rol == GERENTE
    pagina = compra_ventas.buscar_compra_ventas(request.user, filtros, request.GET.get("pagina"))
    puede, motivo = compra_ventas.puede_registrar(request.user)
    from comercial.servicios import faltantes  # el Vendedor ve cuántas ventas esperan una decisión que él puede registrar (COM-DCD-FLT, 1a)

    para_decidir = len(faltantes.ventas_para_decidir(request.user)) if request.user.rol == VENDEDOR else 0
    consulta = urlencode({k: v for k, v in request.GET.items() if k != "pagina" and v})
    return render(
        request,
        "comercial/contratos/lista.html",
        {
            "pagina": pagina,
            "filtros": filtros,
            "estados": ESTADOS,
            "es_gerente": es_gerente,
            "vendedores": [v for v, _ in compra_ventas._vendedores_con_invernaderos()] if es_gerente else [],
            "puede_registrar": puede,
            "para_decidir": para_decidir,
            "motivo": motivo,
            "consulta": consulta,
        },
    )


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def compra_venta(request, venta_id):
    """Ficha de la compra-venta (COM-CNS-CVT, regla 4, en lo que existe hoy). Fuera del alcance: 403 con mensaje (SEG-13); un id que no existe, 404."""
    ficha = compra_ventas.ficha_de_compra_venta(request.user, venta_id)
    return render(request, "comercial/contratos/ficha.html", {"ficha": ficha, "venta": ficha.venta, "es_gerente": request.user.rol == GERENTE})


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def compra_venta_comprobante(request, venta_id):
    """El comprobante imprimible (una página con estilos de impresión, sin menú) de toda compra-venta del alcance. «Comprobante interno, sin
    validez fiscal. El pago se realiza al recibir el producto.»"""
    ficha = compra_ventas.ficha_de_compra_venta(request.user, venta_id)
    return render(request, "comercial/contratos/comprobante.html", compra_ventas.datos_del_comprobante(ficha.venta))


@rol_requerido(GERENTE, VENDEDOR)
@require_POST
def compra_venta_reenviar_comprobante(request, venta_id):
    """«Reenviar comprobante» (extensión 16a): lo pueden hacer el Vendedor responsable y el Gerente; sin auditoría. Un POST; siempre vuelve a la ficha."""
    try:
        estado = comprobantes.reenviar_comprobante(request.user, venta_id)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        if estado == CompraVenta.EstadoDelComprobante.ENVIADO:
            messages.success(request, "Comprobante enviado.")
        else:
            messages.error(request, "No se pudo enviar el comprobante. Probá de nuevo más tarde o imprimilo desde la ficha.")
    return redirect("comercial:compra_venta", venta_id)


# ---- el formulario «Nueva compra-venta» (COM-REG-CVT) ----


def _datos_del_pedido(base):
    """Los ``DatosDeCompraVenta`` de un POST o un GET, con las operaciones de los botones sobre los renglones: «Quitar» (``quitar=<índice>``),
    «Agregar variedad» (``agregar_renglon``) y «Cambiar» el cliente (``cambiar_cliente``: se descartan también su dirección). Siempre queda al
    menos un renglón en blanco para cargar."""
    datos = DatosDeCompraVenta.desde_post(base)
    if "cambiar_cliente" in base:
        datos.cliente_id = datos.direccion_id = ""
    quitar = base.get("quitar", "")
    if quitar.isdigit():
        datos.renglones = [r for r in datos.renglones if r.indice != int(quitar)]
    if "agregar_renglon" in base or not datos.renglones:
        datos.renglones.append(Renglon(max((r.indice for r in datos.renglones), default=-1) + 1))
    return datos


def _mensajes(error):
    """``{campo: [mensajes]}`` de una ``ValidationError`` del servicio (los generales, bajo ``NO_CAMPO``)."""
    if hasattr(error, "error_dict"):
        return {campo: [e.message for e in lista] for campo, lista in error.error_dict.items()}
    return {NO_CAMPO: error.messages}


def _texto_del_precio(precio):
    """Un precio como lo escribe la persona: «1500,50»."""
    return f"{precio:.2f}".replace(".", ",")


def _contexto(request, datos, errores=None):
    """Lo que necesita la pantalla del formulario: el cálculo de ``datos_del_formulario`` (que no escribe ni bloquea), los resultados de la
    búsqueda de clientes y los errores. El precio propuesto se muestra en el renglón que todavía no tiene precio (paso 9: el Vendedor lo
    confirma o lo cambia); los errores del servicio al resumir o registrar se reparten en sus campos."""
    base = request.POST if request.method == "POST" else request.GET
    formulario = compra_ventas.datos_del_formulario(request.user, datos)
    if errores is not None:
        formulario.errores = errores
        for fila in formulario.filas:
            for campo in ("variedad", "cantidad", "precio"):
                if mensajes := errores.get(f"renglon-{fila.renglon.indice}-{campo}"):
                    fila.errores[campo] = mensajes[0]
    for fila in formulario.filas:
        if fila.precio_propuesto is not None and not fila.renglon.precio.strip():
            fila.renglon.precio = _texto_del_precio(fila.precio_propuesto)
    consulta = base.get("cliente_q", "").strip()
    encontrados = []
    if formulario.cliente is None and len(consulta) >= 2:
        encontrados = list(api_clientes.buscar_clientes(request.user, consulta, "activo").object_list[:8])
    puede, motivo = compra_ventas.puede_registrar(request.user)
    return {
        "f": formulario,
        "datos": datos,
        "cliente_q": consulta,
        "encontrados": encontrados,
        "busco_sin_resultado": bool(consulta and len(consulta) >= 2 and not encontrados and formulario.cliente is None),
        "puede_registrar": puede,
        "motivo": motivo,
        "es_gerente": request.user.rol == GERENTE,
        "url_para_volver": _url_de_vuelta(request, datos),
        "hay_variedades_cargadas": any(r.variedad_id.strip() for r in datos.renglones),
        "errores_generales": (formulario.errores or {}).get(NO_CAMPO, []),
        "aviso_de_stock": MENSAJE_DE_STOCK in (formulario.errores or {}).get(NO_CAMPO, []),
    }


def _url_de_vuelta(request, datos):
    """La URL de «Nueva compra-venta» con los datos de las secciones 1 y 2 en la consulta (``vendedor``, ``cliente``, ``fecha``,
    ``modalidad``, ``invernadero``), para regresar desde el alta del cliente o la modificación (regla 7 de ALT, regla 5 de MOD). Las
    variedades no viajan. Se arma con ``urllib.parse`` y solo se devuelve si es una URL interna (``url_has_allowed_host_and_scheme``)."""
    parametros = {
        "vendedor": datos.vendedor_id,
        "cliente": datos.cliente_id,
        "fecha": datos.fecha_pactada,
        "modalidad": datos.modalidad,
        "invernadero": datos.invernadero_id,
    }
    ruta = reverse("comercial:compra_venta_nueva")
    url = urlunsplit(("", "", ruta, urlencode({k: v for k, v in parametros.items() if v}), ""))
    permitido = url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return url if permitido else ruta


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
def compra_venta_nueva(request):
    """«Nueva compra-venta» (COM-REG-CVT; ``VIEWS.cvnew`` del prototipo). GET: el formulario (con los datos de la consulta, que lleva el
    regreso desde el alta del cliente). POST: ``confirmar`` registra (paso 15, con redirección a la ficha); cualquier otro botón
    («Actualizar», «Agregar variedad», «Quitar», «Cambiar») vuelve a mostrar el formulario con los cálculos, sin guardar nada."""
    puede, _ = compra_ventas.puede_registrar(request.user)
    if request.method == "POST":
        datos = _datos_del_pedido(request.POST)
        if "confirmar" in request.POST and puede:
            try:
                venta = compra_ventas.registrar_compra_venta(request.user, datos)
            except ValidationError as error:
                contexto = _contexto(request, datos, _mensajes(error))
                return render(request, "comercial/contratos/formulario.html", contexto)
            _avisar_el_registro(request, venta)
            return redirect("comercial:compra_venta", venta.pk)
    else:
        datos = _datos_del_pedido(request.GET)
    return render(request, "comercial/contratos/formulario.html", _contexto(request, datos))


def _avisar_el_registro(request, venta):
    """El aviso breve del paso 17 (D-29): «CV-0044 registrada. Se reservó el stock y se programaron N cosechas.» más lo del comprobante."""
    texto = f"{venta.codigo} registrada. Se reservó el stock"
    if venta.cosechas_programadas:
        texto += f" y se programó {venta.cosechas_programadas} cosecha." if venta.cosechas_programadas == 1 else f" y se programaron {venta.cosechas_programadas} cosechas."
    else:
        texto += "."
    estado = venta.estado_comprobante
    if estado == CompraVenta.EstadoDelComprobante.ENVIADO:
        messages.success(request, f"{texto} Se envió el comprobante a {venta.cliente.email_cliente}.")
    elif estado == CompraVenta.EstadoDelComprobante.PARA_IMPRIMIR:
        messages.success(request, f"{texto} El cliente no tiene correo: imprimí el comprobante desde la ficha.")
    else:
        messages.success(request, texto)
        messages.error(
            request, f"No se pudo enviar el comprobante a {venta.cliente.email_cliente}. Podés reenviarlo desde la ficha."
        )


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def compra_venta_calcular(request):
    """El recálculo de la pantalla (pasos 2 a 10, extensiones 13a.1a y 13a.1b), solo al cambiar un selector (cliente, Vendedor, modalidad,
    invernadero, dirección, variedad) o con «Actualizar»: devuelve el cuerpo del formulario. **No escribe nada** ni valida lo que todavía no se
    cargó."""
    datos = _datos_del_pedido(request.POST)
    return render(request, "comercial/contratos/_cuerpo.html", _contexto(request, datos))


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def compra_venta_revisar(request):
    """«Revisar y registrar» (pasos 12 y 13 y extensión 13a): valida todo como al registrar y muestra el resumen. Con HTMX llega solo la
    ventana (sobre el formulario); sin JavaScript, el resumen es una página. Si algo falta o ya no alcanza, vuelve al formulario con los errores
    por campo (con HTMX redibuja el cuerpo, con ``HX-Retarget``). No escribe nada."""
    datos = _datos_del_pedido(request.POST)
    try:
        resumen = compra_ventas.resumen(request.user, datos)
    except ValidationError as error:
        contexto = _contexto(request, datos, _mensajes(error))
        if _es_htmx(request):
            respuesta = render(request, "comercial/contratos/_cuerpo.html", contexto)
            respuesta["HX-Retarget"] = "#cuerpo-cv"
            respuesta["HX-Reswap"] = "innerHTML show:none"
            return respuesta
        return render(request, "comercial/contratos/formulario.html", contexto)
    contexto = {"resumen": resumen, "f": resumen.formulario, "datos": datos, "es_gerente": request.user.rol == GERENTE}
    plantilla = "comercial/contratos/_resumen.html" if _es_htmx(request) else "comercial/contratos/resumen.html"
    return render(request, plantilla, contexto)


# ---- el regreso desde el alta o la modificación de un cliente (regla 7 de COM-ALT-CLT, regla 5 de COM-MOD-CLT) ----


def con_parametro(request, url, **parametros):
    """``url`` (el ``volver`` de COM-01, ya validado como interno) con ``parametros`` sumados a su consulta (el cliente o la dirección recién
    creados, que quedan elegidos). Se arma con ``urllib.parse`` y solo se devuelve si sigue siendo una URL interna; si no, ``url`` tal cual."""
    partes = urlsplit(url)
    consulta = dict(parse_qsl(partes.query))
    consulta.update({k: str(v) for k, v in parametros.items() if v})
    nueva = urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(consulta), partes.fragment))
    permitido = url_has_allowed_host_and_scheme(nueva, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return nueva if permitido else url


# ---- COM-CNL-CVT · Cancelar compra-venta (COM-05b) ----
# Las vistas solo orquestan: arman los datos del pedido, llaman al servicio y renderizan. «Revisar y cancelar» muestra el resumen (ventana con HTMX, página sin JavaScript) y no escribe; «Confirmar
# cancelación» escribe (paso 8): vuelve a verificar todo bajo bloqueo. Si la venta cambió (8a, 8b) se vuelve al paso 4 con los datos nuevos.

MOTIVOS_DE_CANCELACION = CompraVenta.MotivoCancelacion.choices
# Códigos de los que no hay nada que corregir en el motivo: se informa y se vuelve a la ficha (la venta ya no se puede cancelar).
SIN_SALIDA_DE_CANCELACION = {"venta_no_cancelable"}
# Los errores que se corrigen en la misma pantalla, junto a su campo (el medio de pago es de 6a, COM-08b).
CODIGOS_DE_CAMPO_DE_CANCELACION = {"motivo_obligatorio", "motivo_invalido", "descripcion_larga", "medio_de_pago_obligatorio", "medio_no_admitido"}


def _codigos(error):
    if hasattr(error, "error_dict"):
        return {e.code for lista in error.error_dict.values() for e in lista}
    return {e.code for e in error.error_list}


def _cuantos_se_cancelan(datos):
    return sum(1 for d in datos.detalles if d.se_cancela)


def _pagina_de_cancelacion(request, venta_id, motivo="", descripcion="", errores=None, medio_pago=""):
    """La pantalla de cancelación con los datos de ahora (paso 4) y, si los hay, los errores por campo (`motivo`, `descripcion`, `medio_pago`). Con entregas concretadas (6a, COM-08b) suma «Cobro de lo entregado»."""
    datos = compra_ventas.datos_de_cancelacion(request.user, venta_id)
    contexto = {
        "datos": datos,
        "motivos": MOTIVOS_DE_CANCELACION,
        "motivo": motivo,
        "descripcion": descripcion,
        "medio_pago": medio_pago,
        "medios": PagoCliente.Medio.choices,
        "errores": errores or {},
        "cuantos": _cuantos_se_cancelan(datos),
    }
    return render(request, "comercial/contratos/cancelar.html", contexto)


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def compra_venta_cancelar(request, venta_id):
    """«Cancelar compra-venta» (`VIEWS.cvcancel`). El GET muestra lo que va a pasar (paso 4). El POST confirma (paso 8). Con «volver» (el resumen sin JavaScript) deja la pantalla con lo elegido.
    8a y 8b (`venta_cambio`, `entrega_en_curso`…) vuelven al paso 4 con los datos nuevos; `venta_no_cancelable`, a la ficha."""
    if request.method != "POST":
        return _pagina_de_cancelacion(request, venta_id)
    datos_post = DatosDeCancelacionDeVenta.desde_post(request.POST)
    if "volver" in request.POST:
        return _pagina_de_cancelacion(request, venta_id, datos_post.motivo, datos_post.descripcion, medio_pago=datos_post.medio_pago)
    try:
        venta = compra_ventas.cancelar_compra_venta(request.user, venta_id, datos_post, request.POST.get("huella", ""))
    except ValidationError as error:
        codigos = _codigos(error)
        if codigos & SIN_SALIDA_DE_CANCELACION:
            messages.error(request, " ".join(error.messages))
            return redirect("comercial:compra_venta", venta_id)
        if hasattr(error, "error_dict") and codigos & CODIGOS_DE_CAMPO_DE_CANCELACION:
            return _pagina_de_cancelacion(request, venta_id, datos_post.motivo, datos_post.descripcion, _mensajes(error), datos_post.medio_pago)
        messages.error(request, " ".join(error.messages))  # 8a, 8b y 4a: se vuelve al paso 4 con lo que hay ahora
        return redirect("comercial:compra_venta_cancelar", venta_id)
    _avisar_la_cancelacion(request, venta)
    return redirect("comercial:compra_venta", venta.pk)


def _avisar_la_cancelacion(request, venta):
    """El aviso breve del paso 10 (D-29): «CV-0044 cancelada. Se canceló 1 cosecha y 1 entrega; 40 plantas entraron a la cámara.» más lo del comprobante (postcondición g y extensión 9a)."""
    partes = []
    cosechas, entregas_ = len(venta.cosechas_canceladas), len(venta.entregas_canceladas)
    if cosechas:
        partes.append(f"{cosechas} cosecha" + ("" if cosechas == 1 else "s"))
    if entregas_:
        partes.append(f"{entregas_} entrega" + ("" if entregas_ == 1 else "s"))
    texto = f"{venta.codigo} cancelada."
    pago = venta.pagos.filter(estado_pago="vigente").first() if venta.estado_venta == CompraVenta.Estado.CONCRETADA else None
    if pago is not None:  # 6a: lo entregado se cobró y la venta quedó «concretada»
        texto = f"{venta.codigo} cancelada. Se cobró lo entregado ({texto_de_pesos(pago.monto_pagado)}, {pago.get_medio_pago_display().lower()}) y la venta quedó concretada."
    if partes:
        texto += f" Se canceló {' y '.join(partes)}"
        texto += f"; {venta.plantas_a_camara} planta{'' if venta.plantas_a_camara == 1 else 's'} entraron a la cámara." if venta.plantas_a_camara else "."
    elif venta.plantas_a_camara:
        texto += f" {venta.plantas_a_camara} planta{'' if venta.plantas_a_camara == 1 else 's'} entraron a la cámara."
    estado = CompraVenta.objects.filter(pk=venta.pk).values_list("estado_comprobante", flat=True).get()  # el envío salió después de confirmar
    if estado == CompraVenta.EstadoDelComprobante.ENVIADO:
        messages.success(request, f"{texto} Se envió el comprobante a {venta.cliente.email_cliente}.")
    elif estado == CompraVenta.EstadoDelComprobante.PARA_IMPRIMIR:
        messages.success(request, f"{texto} El cliente no tiene correo: imprimí el comprobante.")
    else:
        messages.success(request, texto)
        messages.error(request, f"No se pudo enviar el comprobante a {venta.cliente.email_cliente}. Podés reenviarlo desde la ficha.")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def compra_venta_cancelar_revisar(request, venta_id):
    """«Revisar y cancelar» (pasos 6 y 7): valida el motivo y que la venta se pueda cancelar, y muestra el resumen. Con HTMX llega solo la ventana; sin JavaScript, el resumen es una página. Si algo
    falta vuelve a la pantalla con los errores por campo. **No escribe nada.**"""
    datos_post = DatosDeCancelacionDeVenta.desde_post(request.POST)
    try:
        resumen = compra_ventas.resumen_de_cancelacion_de_venta(request.user, venta_id, datos_post)
    except ValidationError as error:
        if hasattr(error, "error_dict") and _codigos(error) & CODIGOS_DE_CAMPO_DE_CANCELACION:
            respuesta = _pagina_de_cancelacion(request, venta_id, datos_post.motivo, datos_post.descripcion, _mensajes(error), datos_post.medio_pago)
            if _es_htmx(request):
                respuesta["HX-Retarget"] = "body"
                respuesta["HX-Reswap"] = "innerHTML show:none"
            return respuesta
        messages.error(request, " ".join(error.messages))
        return redirect("comercial:compra_venta_cancelar", venta_id)
    contexto = {
        "resumen": resumen,
        "datos_post": {"huella": request.POST.get("huella", ""), "motivo": datos_post.motivo, "descripcion": datos_post.descripcion, "medio_pago": datos_post.medio_pago},
        "medio_texto": dict(PagoCliente.Medio.choices).get(datos_post.medio_pago, ""),
        "cuantos": _cuantos_se_cancelan(resumen.datos),
    }
    return render(request, "comercial/contratos/_cancelar_resumen.html" if _es_htmx(request) else "comercial/contratos/cancelar_resumen.html", contexto)
