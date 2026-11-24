# Vistas de los suministros de `comercial` (COM-03a): la lista (la pestaña «Contratos» con `?tipo=suministro`) y la ficha (COM-CNS-SUM), el formulario
# «Pactar suministro» con su recálculo por HTMX, el resumen y la confirmación (COM-PCT-SUM), el calendario completo, el comprobante imprimible y
# «Reenviar comprobante». Las vistas solo orquestan: arman los datos del pedido, llaman al servicio y renderizan (docs/patrones/abm.md, sección 1).
# Sin JavaScript todo funciona: cada cambio se manda con «Actualizar» y el resumen es una página. Nunca se valida al tipear
# (`.claude/rules/interfaz.md`): solo los selectores y los botones redibujan, sin validar, con ``hx-swap="innerHTML show:none"``.

import re
from datetime import date
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import Suministro
from comercial.servicios import clientes as api_clientes
from comercial.servicios import comprobantes, suministros
from comercial.servicios.compra_ventas import NO_CAMPO, _vendedores_con_invernaderos
from comercial.servicios.suministros import DatosDeSuministro, FiltrosDeSuministros, RenglonDeSuministro
from comercial.views_contratos import _es_htmx, _mensajes
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import stock
from maestros.models import Variedad

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR
ESTADOS = Suministro.Estado.choices
MENSAJE_DE_STOCK = suministros.MENSAJE_STOCK_CAMBIO


# ---- lista y ficha (COM-CNS-SUM) ----


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def lista(request):
    """La pestaña «Contratos» con el selector en «Suministros» (``tabContratos``, rama ``sum``, del prototipo; COM-CNS-SUM, reglas 1 a 3): los
    suministros del alcance, con filtros en la URL (se pueden compartir y volver con «Atrás») y páginas de 50. No audita."""
    filtros = FiltrosDeSuministros.desde_get(request.GET)
    es_gerente = request.user.rol == GERENTE
    pagina = suministros.buscar_suministros(request.user, filtros, request.GET.get("pagina"))
    puede, motivo = suministros.puede_pactar(request.user)
    consulta = urlencode({k: v for k, v in request.GET.items() if k != "pagina" and v})
    return render(
        request,
        "comercial/suministros/lista.html",
        {
            "pagina": pagina,
            "filtros": filtros,
            "estados": ESTADOS,
            "es_gerente": es_gerente,
            "vendedores": [v for v, _ in _vendedores_con_invernaderos()] if es_gerente else [],
            "puede_pactar": puede,
            "motivo": motivo,
            "consulta": consulta,
            "hay_filtros": any(v for k, v in request.GET.items() if k not in ("tipo", "pagina")),
        },
    )


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def suministro(request, suministro_id):
    """Ficha del suministro (COM-CNS-SUM, reglas 4 a 6, 9 y 10, en lo que existe hoy). Fuera del alcance: 403 con mensaje (SEG-13); un id que no
    existe, 404."""
    ficha = suministros.ficha_de_suministro(request.user, suministro_id)
    return render(request, "comercial/suministros/ficha.html", {"ficha": ficha, "s": ficha.suministro, "es_gerente": request.user.rol == GERENTE})


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def suministro_calendario(request, suministro_id):
    """«Ver todo el calendario» (regla 6): todos los períodos de todos los detalles, de a 100."""
    s = suministros.suministro_del_alcance(request.user, suministro_id)
    pagina = suministros.calendario_completo(request.user, suministro_id, request.GET.get("pagina"))
    return render(request, "comercial/suministros/calendario.html", {"s": s, "pagina": pagina})


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def suministro_comprobante(request, suministro_id):
    """El comprobante imprimible (una página con estilos de impresión, sin menú) de todo suministro del alcance. «Comprobante interno, sin validez
    fiscal.»"""
    s = suministros.suministro_del_alcance(request.user, suministro_id)
    return render(request, "comercial/suministros/comprobante.html", suministros.datos_del_comprobante(s))


@rol_requerido(GERENTE, VENDEDOR)
@require_POST
def suministro_reenviar_comprobante(request, suministro_id):
    """«Reenviar comprobante» (extensión 15a): lo pueden hacer el Vendedor responsable y el Gerente; sin auditoría. Un POST; siempre vuelve a la ficha."""
    try:
        estado = comprobantes.reenviar_comprobante(request.user, suministro_id)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        if estado == Suministro.EstadoDelComprobante.ENVIADO:
            messages.success(request, "Comprobante enviado.")
        else:
            messages.error(request, "No se pudo enviar el comprobante. Probá de nuevo más tarde o imprimilo desde la ficha.")
    return redirect("comercial:suministro", suministro_id)


# ---- el formulario «Pactar suministro» (COM-PCT-SUM) ----


def _datos_del_pedido(base):
    """Los ``DatosDeSuministro`` de un POST o un GET, con las operaciones de los botones sobre los detalles: «Quitar» (``quitar=<índice>``), «Agregar
    detalle» (``agregar_detalle``) y «Cambiar» el cliente (``cambiar_cliente``: se descartan también la dirección de cada detalle, extensión 13a.1b).
    Siempre queda al menos un detalle en blanco para cargar."""
    datos = DatosDeSuministro.desde_post(base)
    if "cambiar_cliente" in base:
        datos.cliente_id = ""
        for renglon in datos.renglones:
            renglon.direccion_id = ""
    rapido = base.get("periodo_rapido", "")  # una opción rápida de período («<índice>:<días>»: 7, 14 o 30)
    if re.fullmatch(r"\d+:(7|14|30)", rapido):
        indice, dias = rapido.split(":")
        for renglon in datos.renglones:
            if renglon.indice == int(indice):
                renglon.periodo = dias
    quitar = base.get("quitar", "")
    if quitar.isdigit():
        datos.renglones = [r for r in datos.renglones if r.indice != int(quitar)]
    if "agregar_detalle" in base or not datos.renglones:
        datos.renglones.append(RenglonDeSuministro(max((r.indice for r in datos.renglones), default=-1) + 1))
    return datos


def _url_de_vuelta(request, datos):
    """La URL de «Pactar suministro» con los datos de las secciones 1 y 2 en la consulta (``vendedor``, ``cliente``, ``duracion``, ``tolerados``,
    ``multa``, ``plazo_pago``, ``indemnizacion_pago``), para regresar desde el alta del cliente o la carga de su correo. Los detalles no viajan. Se arma
    con ``urllib.parse`` y solo se devuelve si es una URL interna."""
    parametros = {
        "vendedor": datos.vendedor_id,
        "cliente": datos.cliente_id,
        "duracion": datos.duracion,
        "tolerados": datos.tolerados,
        "multa": datos.multa,
        "plazo_pago": datos.plazo_pago,
        "indemnizacion_pago": datos.indemnizacion_pago,
    }
    ruta = reverse("comercial:suministro_nuevo")
    url = urlunsplit(("", "", ruta, urlencode({k: v for k, v in parametros.items() if v}), ""))
    permitido = url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return url if permitido else ruta


def _contexto(request, datos, errores=None):
    """Lo que necesita la pantalla del formulario: el cálculo de ``datos_del_formulario`` (que no escribe ni bloquea), los resultados de la búsqueda
    de clientes y los errores. Los errores del servicio al resumir o registrar se reparten en sus campos."""
    base = request.POST if request.method == "POST" else request.GET
    formulario = suministros.datos_del_formulario(request.user, datos)
    if errores is not None:
        formulario.errores = errores
        for fila in formulario.filas:
            prefijo = f"detalle-{fila.renglon.indice}-"
            for campo, mensajes in errores.items():
                if campo.startswith(prefijo):
                    fila.errores[campo[len(prefijo):]] = mensajes[0]
    consulta = base.get("cliente_q", "").strip()
    encontrados = []
    if formulario.cliente is None and len(consulta) >= 2:
        encontrados = list(api_clientes.buscar_clientes(request.user, consulta, "activo").object_list[:8])
    puede, motivo = suministros.puede_pactar(request.user)
    url_para_volver = _url_de_vuelta(request, datos)
    generales = (formulario.errores or {}).get(NO_CAMPO, [])
    return {
        "f": formulario,
        "datos": datos,
        "cliente_q": consulta,
        "encontrados": encontrados,
        "busco_sin_resultado": bool(consulta and len(consulta) >= 2 and not encontrados and formulario.cliente is None),
        "puede_pactar": puede,
        "motivo": motivo,
        "es_gerente": request.user.rol == GERENTE,
        "url_para_volver": url_para_volver,
        "hay_detalles_cargados": bool(formulario.cargadas),
        "errores_generales": generales,
        "aviso_de_stock": MENSAJE_DE_STOCK in generales,
        "dias_de_ventana": (formulario.ventana - stock.hoy()).days,
        "periodos_a_reservar": sum(len(f.periodos_de_la_ventana) for f in formulario.cargadas),
        "total_de_detalles": len(formulario.cargadas),
    }


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
def suministro_nuevo(request):
    """«Pactar suministro» (COM-PCT-SUM; ``VIEWS.sumnew`` del prototipo). GET: el formulario (con los datos de la consulta, que lleva el regreso desde
    el alta del cliente). POST: ``confirmar`` pacta (paso 16, con redirección a la ficha); cualquier otro botón («Actualizar», «Agregar detalle»,
    «Quitar», «Cambiar») vuelve a mostrar el formulario con los cálculos, sin guardar nada."""
    puede, _ = suministros.puede_pactar(request.user)
    if request.method == "POST":
        datos = _datos_del_pedido(request.POST)
        if "confirmar" in request.POST and puede:
            try:
                nuevo = suministros.pactar_suministro(request.user, datos)
            except ValidationError as error:
                return render(request, "comercial/suministros/formulario.html", _contexto(request, datos, _mensajes(error)))
            _avisar_el_pacto(request, nuevo)
            return redirect("comercial:suministro", nuevo.pk)
    else:
        datos = _datos_del_pedido(request.GET)
    return render(request, "comercial/suministros/formulario.html", _contexto(request, datos))


def _avisar_el_pacto(request, nuevo):
    """El aviso breve del paso 16 (D-29): «SUM-0013 pactado. Se reservaron N períodos y se programaron M cosechas.» más lo del comprobante."""
    n, m = nuevo.periodos_reservados, nuevo.cosechas_programadas
    texto = f"{nuevo.codigo} pactado."
    if n:
        texto += f" Se reservó {n} período" if n == 1 else f" Se reservaron {n} períodos"
        if m:
            texto += f" y se programó {m} cosecha" if m == 1 else f" y se programaron {m} cosechas"
        texto += "."
    estado = nuevo.estado_comprobante
    if estado == Suministro.EstadoDelComprobante.ENVIADO:
        messages.success(request, f"{texto} Se envió el comprobante a {nuevo.cliente.email_cliente}.")
    else:
        messages.success(request, texto)
        messages.error(request, f"No se pudo enviar el comprobante a {nuevo.cliente.email_cliente}. Podés reenviarlo desde la ficha.")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def suministro_calcular(request):
    """El recálculo de la pantalla (pasos 2 a 11, extensiones 13a.1a a 13a.1c), solo al cambiar un selector (cliente, Vendedor, variedad, dirección,
    mecanismo) o con «Actualizar»: devuelve el cuerpo del formulario. **No escribe nada** ni valida lo que todavía no se cargó."""
    datos = _datos_del_pedido(request.POST)
    return render(request, "comercial/suministros/_cuerpo.html", _contexto(request, datos))


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@require_POST
def suministro_revisar(request):
    """«Revisar y pactar» (pasos 12 y 13 y extensión 13a): valida todo como al registrar y muestra el resumen. Con HTMX llega solo la ventana (sobre
    el formulario); sin JavaScript, el resumen es una página. Si algo falta o ya no alcanza, vuelve al formulario con los errores por campo (con HTMX
    redibuja el cuerpo, con ``HX-Retarget``). No escribe nada."""
    datos = _datos_del_pedido(request.POST)
    try:
        resumen = suministros.resumen(request.user, datos)
    except ValidationError as error:
        contexto = _contexto(request, datos, _mensajes(error))
        if _es_htmx(request):
            respuesta = render(request, "comercial/suministros/_cuerpo.html", contexto)
            respuesta["HX-Retarget"] = "#cuerpo-sum"
            respuesta["HX-Reswap"] = "innerHTML show:none"
            return respuesta
        return render(request, "comercial/suministros/formulario.html", contexto)
    contexto = {"resumen": resumen, "f": resumen.formulario, "datos": datos, "es_gerente": request.user.rol == GERENTE}
    plantilla = "comercial/suministros/_resumen.html" if _es_htmx(request) else "comercial/suministros/resumen.html"
    return render(request, plantilla, contexto)


# ---- modificar un suministro (COM-MOD-SUM, COM-03b) ----
#
# Como «Pactar suministro»: una sola página con el cuerpo que HTMX redibuja al tocar un selector o un botón (`calcular/`, sin escribir ni validar mientras se tipea), el resumen
# (`revisar/`, ventana sobre el formulario o página sin JavaScript) y la confirmación (un POST a `modificar/` con `confirmar`). El formulario viene cargado con los valores
# actuales: un campo igual al actual no es un cambio (convención de `CambiosDeSuministro`). La huella del contrato y la propuesta de «rige desde» que vio la persona viajan
# ocultas (10a y 10b). Las vistas solo orquestan: arman el pedido, llaman al servicio y renderizan.

CODIGOS_QUE_VUELVEN_A_LA_FICHA = {"contrato_cambio", "rescision_acordada", "sin_rescision", "rescision_cerrada"}
CAMPOS_QUE_NO_VIAJAN = {"csrfmiddlewaretoken", "confirmar", "actualizar", "agregar_detalle", "quitar_nuevo", "acortar_duracion"}


def _codigos_generales(error):
    """Los códigos de los errores generales de una ``ValidationError`` del servicio."""
    if hasattr(error, "error_dict"):
        return [e.code for e in error.error_dict.get(NO_CAMPO, [])]
    return [e.code for e in error.error_list]


def _volver_a_la_ficha(request, suministro_id, mensaje=None):
    """Vuelve a la ficha del suministro (10b: «informa la situación actual y vuelve al paso 2»), con un aviso de error. Con HTMX, por ``HX-Redirect``."""
    if mensaje:
        messages.error(request, mensaje)
    url = reverse("comercial:suministro", args=[suministro_id])
    if _es_htmx(request):
        respuesta = HttpResponse(status=204)
        respuesta["HX-Redirect"] = url
        return respuesta
    return redirect(url)


def _cambios_del_pedido(base):
    """Los `CambiosDeSuministro` de un POST o un GET, con los botones: «Agregar detalle» (un renglón nuevo en blanco), «Quitar» un detalle nuevo (``quitar_nuevo=<i>``) y «Acortar
    la duración» (``acortar_duracion=<meses>``, extensión 5c.1a)."""
    cambios = suministros.CambiosDeSuministro.desde_post(base)
    quitar = base.get("quitar_nuevo", "")
    if quitar.isdigit():
        cambios.nuevos = [r for r in cambios.nuevos if r.indice != int(quitar)]
    if "agregar_detalle" in base:
        cambios.nuevos.append(RenglonDeSuministro(max((r.indice for r in cambios.nuevos), default=-1) + 1))
    acortar = base.get("acortar_duracion", "")
    if acortar.isdigit():
        cambios.duracion = acortar
    return cambios


def _errores_con_prefijo(errores, prefijo):
    """``{campo: primer mensaje}`` de los errores cuyo campo empieza con ``prefijo`` (sin él)."""
    return {campo[len(prefijo):]: mensajes[0] for campo, mensajes in errores.items() if campo.startswith(prefijo)}


def _contexto_de_modificar(request, suministro_id, cambios, errores=None):
    """Lo que necesita la pantalla de modificar: el cálculo de `datos_de_modificacion` (que no escribe ni bloquea) y, para cada campo, lo que se muestra (lo que llegó o, si todavía
    no se tocó, el valor actual). ``None`` si el contrato ya no se puede modificar (vuelve a la ficha)."""
    datos = suministros.datos_de_modificacion(request.user, suministro_id, cambios)
    if set(_codigos_de(datos.codigos, NO_CAMPO)) & CODIGOS_QUE_VUELVEN_A_LA_FICHA:
        return datos, None
    s = datos.suministro
    base = request.POST if request.method == "POST" else request.GET
    errores = datos.errores if errores is None else errores
    por_detalle = {c.detalle_id: c for c in cambios.detalles}
    filas = []
    for fila in datos.filas:
        d, cl = fila.detalle, fila.detalle.clausula_suministrante
        cambio = por_detalle.get(d.pk)
        mostrado = lambda campo, actual, cambio=cambio: getattr(cambio, campo) if cambio is not None else actual  # noqa: E731
        hija = api_clientes.direccion_hija(d.direccion_id)
        filas.append(
            SimpleNamespace(
                fila=fila,
                direccion=f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else "",
                accion=cambio.accion if cambio is not None else "sin_cambios",
                rige_elegido=cambio.rige_desde if cambio is not None else "",
                rige_visto=(cambio.rige_visto if cambio is not None and cambio.rige_visto else (str(fila.rige_desde) if fila.rige_desde else "")),
                opciones=fila.opciones,
                cantidad=mostrado("cantidad", d.cantidad_por_periodo),
                periodo=mostrado("periodo", d.periodo_entrega_dias),
                precio=mostrado("precio", f"{fila.precio_propuesto:.2f}"),
                mecanismo=mostrado("mecanismo", d.mecanismo_precio) or d.mecanismo_precio,
                porcentaje=mostrado("porcentaje", d.porcentaje_ajuste if d.porcentaje_ajuste is not None else ""),
                meses=mostrado("meses", d.meses_ajuste if d.meses_ajuste is not None else ""),
                plazo_entrega=mostrado("plazo_entrega", cl.plazo_entrega_dias),
                indemnizacion_retraso=mostrado("indemnizacion_retraso", f"{cl.indemnizacion_retraso_entrega:.2f}"),
                cantidad_minima=mostrado("cantidad_minima", cl.cantidad_minima),
                indemnizacion_faltante=mostrado("indemnizacion_faltante", f"{cl.indemnizacion_faltante:.2f}"),
                errores=_errores_con_prefijo(errores, f"modificar-{d.pk}-"),
            )
        )
    advertencias = {f.renglon.indice: f.advertencias for f in datos.nuevas}
    nuevos = [
        SimpleNamespace(r=r, errores=_errores_con_prefijo(errores, f"detalle-{r.indice}-"), advertencias=advertencias.get(r.indice, []))
        for r in cambios.nuevos
    ]
    clausula = s.clausula_suministrado
    es_gerente = request.user.rol == GERENTE
    contrato = SimpleNamespace(
        duracion=cambios.duracion or s.duracion_meses,
        tolerados=cambios.tolerados or s.incumplimientos_tolerados,
        multa=cambios.multa or f"{s.multa_resolucion:.2f}",
        plazo_pago=cambios.plazo_pago or clausula.plazo_pago_dias,
        indemnizacion_pago=cambios.indemnizacion_pago or f"{clausula.indemnizacion_retraso_pago:.2f}",
        vendedor=cambios.vendedor_id or str(s.vendedor_id),
    )
    return datos, {
        "s": s,
        "datos": datos,
        "filas": filas,
        "nuevos": nuevos,
        "contrato": contrato,
        "errores": errores,
        "errores_generales": errores.get(NO_CAMPO, []),
        "es_gerente": es_gerente,
        "vendedores": [v for v, _ in _vendedores_con_invernaderos()] if es_gerente else [],
        "variedades": list(Variedad.objects.filter(estado_variedad=Variedad.Estado.ACTIVO).select_related("cultivo").order_by("cultivo__nombre_cultivo", "nombre_variedad")),
        "direcciones": api_clientes.direcciones_activas(s.cliente),
        "huella": base.get("huella") or datos.huella,
        "dias_de_ventana": (datos.ventana - datos.hoy).days,
    }


def _codigos_de(codigos, campo):
    """Los códigos de un campo en el diccionario ``{campo: [código]}`` del análisis."""
    return codigos.get(campo, [])


def _responder_modificar(request, suministro_id, cambios, errores=None, plantilla="comercial/suministros/modificar.html"):
    """Dibuja la pantalla (la página o, con HTMX y ``plantilla``, solo el cuerpo); si el contrato ya no se puede modificar, vuelve a la ficha con el motivo."""
    datos, contexto = _contexto_de_modificar(request, suministro_id, cambios, errores)
    if contexto is None:
        mensaje = suministros.MENSAJE_CON_RESCISION if "rescision_acordada" in _codigos_de(datos.codigos, NO_CAMPO) else suministros.MENSAJE_CONTRATO_CAMBIO
        return _volver_a_la_ficha(request, suministro_id, mensaje)
    return render(request, plantilla, contexto)


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
def suministro_modificar(request, suministro_id):
    """«Modificar suministro» (COM-MOD-SUM; ``VIEWS.summod`` del prototipo, segunda definición). GET: el formulario con los valores actuales. POST: ``confirmar`` modifica (paso 10,
    con redirección a la ficha); cualquier otro botón vuelve a mostrar el formulario con los cálculos, sin guardar nada."""
    base = request.POST if request.method == "POST" else request.GET
    cambios = _cambios_del_pedido(base)
    if request.method == "POST" and "confirmar" in request.POST:
        try:
            modificado = suministros.modificar_suministro(request.user, suministro_id, cambios, request.POST.get("huella", ""))
        except ValidationError as error:
            codigos = _codigos_generales(error)
            if set(codigos) & CODIGOS_QUE_VUELVEN_A_LA_FICHA:
                return _volver_a_la_ficha(request, suministro_id, error.error_dict[NO_CAMPO][0].message if hasattr(error, "error_dict") else error.messages[0])
            if "ventana_cambio" in codigos:  # 10a: la propuesta de «rige desde» cambió; se vuelve a mostrar con las fechas recalculadas
                for cambio in cambios.detalles:
                    cambio.rige_visto = ""
                    cambio.rige_desde = ""
            return _responder_modificar(request, suministro_id, cambios, _mensajes(error))
        _avisar_la_modificacion(request, modificado)
        return redirect("comercial:suministro", modificado.pk)
    return _responder_modificar(request, suministro_id, cambios)


def _avisar_la_modificacion(request, modificado):
    """El aviso breve del paso 12 (D-29): «SUM-0013 modificado.» más lo del comprobante (11a)."""
    texto = f"{modificado.codigo} modificado."
    if modificado.estado_suministro == Suministro.Estado.FINALIZADO:
        texto += " Ya no le quedan períodos por entregar: quedó finalizado."
    if modificado.estado_comprobante == Suministro.EstadoDelComprobante.ENVIADO:
        messages.success(request, f"{texto} Se envió el comprobante a {modificado.cliente.email_cliente}.")
    elif modificado.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
        messages.success(request, texto)
        messages.error(request, f"No se pudo enviar el comprobante a {modificado.cliente.email_cliente}. Podés reenviarlo desde la ficha.")
    else:
        messages.success(request, f"{texto} El cliente no tiene correo: el comprobante se entrega impreso.")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def suministro_modificar_calcular(request, suministro_id):
    """El recálculo de la pantalla (pasos 4 a 6 y extensiones 5a a 5g), solo al cambiar un selector o con «Actualizar»: devuelve el cuerpo del formulario. **No escribe nada.**"""
    return _responder_modificar(request, suministro_id, _cambios_del_pedido(request.POST), plantilla="comercial/suministros/_modificar_cuerpo.html")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def suministro_modificar_revisar(request, suministro_id):
    """«Revisar y guardar» (pasos 7 a 9): valida todo como al registrar y muestra el resumen con la fecha desde la que rige cada cambio. Con HTMX llega solo la ventana; sin JavaScript,
    una página. Si algo no vale, vuelve al formulario con los errores por campo. No escribe nada."""
    cambios = _cambios_del_pedido(request.POST)
    try:
        resumen = suministros.resumen_de_modificacion(request.user, suministro_id, cambios, request.POST.get("huella", ""))
    except ValidationError as error:
        codigos = _codigos_generales(error)
        if set(codigos) & CODIGOS_QUE_VUELVEN_A_LA_FICHA:
            return _volver_a_la_ficha(request, suministro_id, error.error_dict[NO_CAMPO][0].message if hasattr(error, "error_dict") else error.messages[0])
        if "ventana_cambio" in codigos:
            for cambio in cambios.detalles:
                cambio.rige_visto = ""
                cambio.rige_desde = ""
        _, contexto = _contexto_de_modificar(request, suministro_id, cambios, _mensajes(error))
        if contexto is None:  # el contrato cambió justo ahora (10b)
            return _volver_a_la_ficha(request, suministro_id, suministros.MENSAJE_CONTRATO_CAMBIO)
        if _es_htmx(request):
            respuesta = render(request, "comercial/suministros/_modificar_cuerpo.html", contexto)
            respuesta["HX-Retarget"] = "#cuerpo-mod"
            respuesta["HX-Reswap"] = "innerHTML show:none"
            return respuesta
        return render(request, "comercial/suministros/modificar.html", contexto)
    campos = [(k, v) for k in request.POST for v in request.POST.getlist(k) if k not in CAMPOS_QUE_NO_VIAJAN]
    contexto = {"resumen": resumen, "s": resumen.datos.suministro, "campos": campos}
    return render(request, "comercial/suministros/_resumen_modificacion.html" if _es_htmx(request) else "comercial/suministros/resumen_modificacion.html", contexto)


# ---- rescindir y dejar sin efecto la rescisión (COM-RSC-SUM y COM-ANL-RSC), e historial ----
#
# Ventanas como la baja del cliente: abrirlas (GET) no cambia nada; con HTMX llega solo la ventana y sin JavaScript, la ficha con la ventana abierta. Registrar es un POST
# común a la misma URL: si algo no vale, vuelve la ficha con la ventana y los errores; si la situación cambió (6b), la ficha con el aviso.


def _ficha_con_ventana(request, suministro_id, plantilla, **contexto):
    """La ficha del suministro con una ventana abierta (el respaldo sin JavaScript y la vuelta de un error)."""
    ficha = suministros.ficha_de_suministro(request.user, suministro_id)
    return render(
        request,
        "comercial/suministros/ficha.html",
        {"ficha": ficha, "s": ficha.suministro, "es_gerente": request.user.rol == GERENTE, "plantilla_de_ventana": plantilla, **contexto},
    )


def _conservados_del_pedido(post):
    """Los períodos que vio el Gerente («<id del detalle>:<aaaa-mm-dd>» en ``conservado``), como ``[(id, fecha)]``. Algo mal formado se descarta: la comparación (6a) lo rechaza."""
    conservados = []
    for texto in post.getlist("conservado"):
        detalle_id, _, fecha = texto.partition(":")
        try:
            conservados.append((int(detalle_id), date.fromisoformat(fecha)))
        except ValueError:
            continue
    return conservados


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def suministro_rescindir(request, suministro_id):
    """«Rescindir suministro» (COM-RSC-SUM; ``MODALS.sumrsc``). Solo el Gerente (el Vendedor recibe 403 y no ve el botón). La ventana presenta los períodos que se conservan y la fecha de la
    última entrega; registrar es un POST con el motivo, la fecha del acuerdo y la casilla de confirmación."""
    try:
        lectura = suministros.datos_de_rescision(request.user, suministro_id)
    except ValidationError as error:
        return _volver_a_la_ficha(request, suministro_id, error.error_dict[NO_CAMPO][0].message)
    pedido, errores = suministros.PedidoDeRescision(fecha_acuerdo=str(lectura.hoy)), {}
    if request.method == "POST":
        pedido = suministros.PedidoDeRescision.desde_post(request.POST)
        try:
            rescindido = suministros.rescindir_suministro(
                request.user, suministro_id, pedido, request.POST.get("huella", ""), _conservados_del_pedido(request.POST)
            )
        except ValidationError as error:
            if set(_codigos_generales(error)) & CODIGOS_QUE_VUELVEN_A_LA_FICHA:
                return _volver_a_la_ficha(request, suministro_id, error.error_dict[NO_CAMPO][0].message)
            errores = _mensajes(error)  # 6a (`ventana_cambio`) y 4a: la ventana vuelve con lo recalculado y el motivo
        else:
            _avisar_la_rescision(request, rescindido)
            return redirect("comercial:suministro", rescindido.pk)
    nombres = {d.pk: d.variedad for d in lectura.suministro.detalles.select_related("variedad")}
    agrupados = {}
    for detalle_id, fecha in lectura.conservados:
        agrupados.setdefault(detalle_id, []).append(fecha)
    contexto = {
        "s": lectura.suministro, "lectura": lectura, "pedido": pedido, "errores": errores, "errores_generales": errores.get(NO_CAMPO, []),
        "por_detalle": [(nombres[i], fechas) for i, fechas in agrupados.items()], "motivos": Suministro.MotivoDeRescision.choices,
    }
    if _es_htmx(request):
        return render(request, "comercial/suministros/_ventana_rescindir.html", contexto)
    return _ficha_con_ventana(request, suministro_id, "comercial/suministros/_ventana_rescindir.html", **contexto)


def _avisar_la_rescision(request, rescindido):
    """El aviso breve del paso 8 (D-29): hasta qué fecha se entrega, más lo de la constancia (7a y 7b)."""
    if rescindido.estado_suministro == Suministro.Estado.RESCINDIDO:
        texto = f"{rescindido.codigo}: rescisión registrada. El contrato quedó rescindido."
    else:
        texto = f"{rescindido.codigo}: rescisión registrada. Se entrega hasta el {rescindido.fecha_ultima_entrega_rescision:%d/%m/%Y}."
    if rescindido.estado_comprobante == Suministro.EstadoDelComprobante.ENVIADO:
        messages.success(request, f"{texto} Se envió la constancia a {rescindido.cliente.email_cliente}.")
    elif rescindido.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
        messages.success(request, texto)
        messages.error(request, f"No se pudo enviar la constancia a {rescindido.cliente.email_cliente}. Podés reenviarla desde la ficha.")
    else:
        messages.success(request, f"{texto} El cliente no tiene correo: la constancia se entrega impresa.")


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def suministro_dejar_sin_efecto(request, suministro_id):
    """«Dejar sin efecto la rescisión» (COM-ANL-RSC; ``MODALS.sumrscanl``). Solo el Gerente, mientras la última entrega conservada no haya pasado; el motivo es obligatorio."""
    ficha = suministros.ficha_de_suministro(request.user, suministro_id)
    if "dejar_sin_efecto" not in ficha.acciones:
        return _volver_a_la_ficha(request, suministro_id, "La rescisión ya no se puede dejar sin efecto.")
    motivo, errores = "", {}
    if request.method == "POST":
        motivo = request.POST.get("motivo", "")
        try:
            anulado = suministros.dejar_sin_efecto_rescision(request.user, suministro_id, motivo, request.POST.get("huella", ""))
        except ValidationError as error:
            if set(_codigos_generales(error)) & CODIGOS_QUE_VUELVEN_A_LA_FICHA:
                return _volver_a_la_ficha(request, suministro_id, error.error_dict[NO_CAMPO][0].message)
            errores = _mensajes(error)
        else:
            texto = f"{anulado.codigo}: la rescisión quedó sin efecto. El contrato sigue como estaba."
            if anulado.estado_comprobante == Suministro.EstadoDelComprobante.ENVIADO:
                messages.success(request, f"{texto} Se envió la constancia a {anulado.cliente.email_cliente}.")
            else:
                messages.success(request, texto)
                if anulado.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
                    messages.error(request, f"No se pudo enviar la constancia a {anulado.cliente.email_cliente}. Podés reenviarla desde la ficha.")
            return redirect("comercial:suministro", anulado.pk)
    contexto = {
        "s": ficha.suministro, "motivo": motivo, "errores": errores, "errores_generales": errores.get(NO_CAMPO, []), "huella": suministros.huella_de(ficha.suministro),
    }
    if _es_htmx(request):
        return render(request, "comercial/suministros/_ventana_anular.html", contexto)
    return _ficha_con_ventana(request, suministro_id, "comercial/suministros/_ventana_anular.html", **contexto)


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
@never_cache
@vary_on_headers("HX-Request")
def suministro_historial(request, suministro_id):
    """«Ver historial de cambios» (``MODALS.sumhist``): cada tramo de cada detalle que se modificó, con lo que rigió y hasta cuándo. Solo lectura."""
    cadenas = suministros.historial_de_cambios(request.user, suministro_id)
    ficha_s = suministros.suministro_del_alcance(request.user, suministro_id)
    contexto = {"s": ficha_s, "cadenas": cadenas}
    if _es_htmx(request):
        return render(request, "comercial/suministros/_ventana_historial.html", contexto)
    return _ficha_con_ventana(request, suministro_id, "comercial/suministros/_ventana_historial.html", **contexto)
