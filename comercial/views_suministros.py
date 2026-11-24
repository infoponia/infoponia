# Vistas de los suministros de `comercial` (COM-03a): la lista (la pestaña «Contratos» con `?tipo=suministro`) y la ficha (COM-CNS-SUM), el formulario
# «Pactar suministro» con su recálculo por HTMX, el resumen y la confirmación (COM-PCT-SUM), el calendario completo, el comprobante imprimible y
# «Reenviar comprobante». Las vistas solo orquestan: arman los datos del pedido, llaman al servicio y renderizan (docs/patrones/abm.md, sección 1).
# Sin JavaScript todo funciona: cada cambio se manda con «Actualizar» y el resumen es una página. Nunca se valida al tipear
# (`.claude/rules/interfaz.md`): solo los selectores y los botones redibujan, sin validar, con ``hx-swap="innerHTML show:none"``.

import re
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
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
