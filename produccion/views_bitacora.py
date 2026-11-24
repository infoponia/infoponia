# Vistas de la bitácora de `produccion` (PRD-03, paso 7): «Registrar en bitácora» (menú), «Registrar merma» y «Registrar aplicación» (en pasos, pensadas para el
# celular del Capataz), «Otro evento» y la consulta de la bitácora (página y pestaña de la ficha del invernadero). Las vistas SOLO orquestan: validan la entrada con
# `formularios`, llaman al servicio y renderizan; las reglas están en `produccion/servicios/`. Todo funciona sin JavaScript (cada pantalla es una página y cada acción,
# un POST con su «accion»); con HTMX solo se redibuja el bloque que depende de lo elegido, SIN validar ni calcular al escribir (.claude/rules/interfaz.md): validar y
# calcular es únicamente con «Ver resumen» y «Confirmar». Quién ve qué (D-30): el Agrónomo a cargo y el Capataz asignado registran; el Gerente solo consulta la bitácora
# (en las pantallas de registro, 404); el Capataz no consulta la bitácora. El Capataz NO recibe valores en dinero: los servicios no se los devuelven.

from itertools import groupby
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario, rol_de
from produccion import formularios
from produccion.extensiones import entradas_de_comercial
from produccion.errores import ErrorDeProduccion
from produccion.servicios import alcance, aplicaciones, bitacora, mermas
from produccion.views import _en_vivo, _errores_por_campo, _firma, _ocultar_al_gerente, _servicio

AGRONOMO, CAPATAZ, GERENTE = Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ, Usuario.Rol.GERENTE


def _firma_de(datos):
    """La marca de lo que se calculó: como `_firma`, pero con los campos de varios valores (los sectores marcados) y SIN lo que la persona «vio» (`visto*`,
    `vistos_*`, `plantas_vistas`): eso se refresca con cada resumen y no es un dato que ella cambie."""
    return _firma({c: datos.getlist(c) for c in datos if not c.startswith(("visto", "plantas_vistas"))})


def _volver(request, invernadero_id):
    """A dónde se vuelve tras registrar: el Capataz, a su bandeja; el Agrónomo, a la bitácora del invernadero."""
    if rol_de(request.user) == CAPATAZ:
        return redirect("produccion:bandeja")
    return redirect(f"{reverse('produccion:bitacora')}?{urlencode({'invernadero': invernadero_id})}")


# ---- Registrar en bitácora (el menú de lo que se puede registrar) ----


@rol_requerido(AGRONOMO, CAPATAZ, GERENTE)
@require_safe
def registrar(request):
    """«Registrar en bitácora» (`VIEWS['bit-reg']`): qué se va a registrar (merma, aplicación de insumos u otro evento). El Agrónomo puede elegir antes el
    invernadero; el Capataz va directo. Las siembras, las transiciones y las cosechas se registran solas al concretar cada orden."""
    _ocultar_al_gerente(request)
    invernaderos = alcance.invernaderos_del_actor(request.user)
    elegido_id = formularios.entero(request.GET.get("invernadero"))
    elegido = next((i for i in invernaderos if i.pk == elegido_id), None)
    return render(request, "produccion/registrar.html", {"invernaderos": invernaderos, "elegido": elegido, "es_capataz": rol_de(request.user) == CAPATAZ})


# ---- Registrar merma (PROD-REG-MRM) ----


@rol_requerido(AGRONOMO, CAPATAZ, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def registrar_merma(request):
    """«Registrar merma» (PROD-REG-MRM, `VIEWS.merma`): invernadero → lote → plantas perdidas por sector, causa y descripción → resumen → confirmar. Cambiar
    el invernadero o el lote (HTMX o «Continuar» sin JavaScript) solo redibuja lo que depende de ello, sin validar. «Ver resumen» valida y no escribe;
    «Confirmar» vuelve a verificar bajo bloqueo (extensión 10d) y escribe. Sin lotes activos (extensión 4b) el formulario queda deshabilitado con su motivo."""
    _ocultar_al_gerente(request)
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    errores, invernadero_id, lotes, lote_id, propuesta = {}, formularios.entero(datos.get("invernadero")), [], None, None
    invernaderos = alcance.invernaderos_del_actor(request.user)
    if invernadero_id:
        try:
            lotes = _servicio(mermas.lotes_con_merma_posible, request.user, invernadero_id)
        except ErrorDeProduccion as error:  # por ejemplo, un invernadero que se dio de baja mientras tanto: se vuelve a la lista
            errores, invernadero_id = _errores_por_campo(error), None
    if invernadero_id:
        pedido = formularios.entero(datos.get("lote"))
        lote_id = pedido if pedido in {f.lote_id for f in lotes} else None
    if lote_id:
        try:
            propuesta = _servicio(mermas.datos_de_merma, request.user, lote_id)
        except ErrorDeProduccion as error:
            errores, lote_id = _errores_por_campo(error), None
    resumen, firma, cambio_la_firma = None, "", False
    if accion in ("calcular", "confirmar") and lote_id:
        firma = _firma_de(datos)
        try:
            if accion == "confirmar" and datos.get("firma") == firma:
                merma = _servicio(mermas.registrar_merma, request.user, formularios.merma_desde_post(datos))
                messages.success(request, f"La merma quedó registrada: {merma.descripcion_evento}")
                return _volver(request, invernadero_id)
            cambio_la_firma = accion == "confirmar"
            resumen = _servicio(mermas.resumen_de_merma, request.user, formularios.merma_desde_post(datos, con_vistos=False))
        except ErrorDeProduccion as error:
            errores = _errores_por_campo(error)
            firma = ""
    contexto = {
        "invernaderos": invernaderos,
        "invernadero_id": invernadero_id,
        "lotes": lotes,
        "lote_id": lote_id,
        "propuesta": propuesta,
        "valores": dict(datos.items()),
        "errores": errores,
        "resumen": resumen,
        "firma": firma,
        "cambio_la_firma": cambio_la_firma,
        "es_capataz": rol_de(request.user) == CAPATAZ,
        # COM-04b (D-64 punto 11): la opción «Pérdida en cámara» (extensión 4a de PROD-REG-MRM) solo si `comercial` la registró y hay partidas; si no, `None`.
        "url_de_merma_en_camara": entradas_de_comercial(request.user).merma_en_camara,
    }
    plantilla = "produccion/_merma_formulario.html" if _en_vivo(request) else "produccion/registrar_merma.html"
    return render(request, plantilla, contexto)


# ---- Registrar aplicación de insumos (PROD-REG-APL) ----


@rol_requerido(AGRONOMO, CAPATAZ, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def registrar_aplicacion(request):
    """«Registrar aplicación» (PROD-REG-APL, `VIEWS.aplic`), para celular: invernadero (nunca se elige solo) → alcance (todo el invernadero o sectores activos) →
    insumos y cantidades (con el reparto FEFO) → descripción → resumen según el rol → confirmar. «Ver resumen» valida y no escribe; «Confirmar» vuelve a verificar
    bajo bloqueo (extensión 12a) y escribe. El Capataz no recibe valores, destinos, reparto ni avisos de stock: los servicios no se los devuelven."""
    _ocultar_al_gerente(request)
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    errores, invernadero_id = {}, formularios.entero(datos.get("invernadero"))
    invernaderos = alcance.invernaderos_del_actor(request.user)
    filas, sectores = [], []
    if invernadero_id:
        try:
            filas = _servicio(aplicaciones.insumos_aplicables, request.user, invernadero_id)
            sectores = _servicio(aplicaciones.sectores_de_aplicacion, request.user, invernadero_id)
        except ErrorDeProduccion as error:
            errores, invernadero_id, filas, sectores = _errores_por_campo(error), None, [], []
    resumen, firma, cambio_la_firma, vistos, plantas_vistas = None, "", False, {}, ""
    if accion in ("calcular", "confirmar") and invernadero_id:
        existencia_ids = [f.existencia_id for f in filas]
        firma = _firma_de(datos)
        try:
            if accion == "confirmar" and datos.get("firma") == firma:
                resultado = _servicio(aplicaciones.registrar_aplicacion, request.user, formularios.aplicacion_desde_post(datos, existencia_ids))
                messages.success(request, "La aplicación quedó registrada en la bitácora.")
                if rol_de(request.user) == AGRONOMO:
                    mensajes = [l.aviso for l in resultado.lineas if l.aviso] + [
                        f"El stock de {l.nombre} quedó negativo: faltan {l.faltante.normalize():f} sin lote." for l in resultado.lineas if l.faltante
                    ]
                    for texto in mensajes:
                        messages.warning(request, texto)
                return _volver(request, invernadero_id)
            cambio_la_firma = accion == "confirmar"
            sin_vistos = formularios.aplicacion_desde_post(datos, existencia_ids, con_vistos=False)
            resumen = _servicio(aplicaciones.resumen_de_aplicacion, request.user, sin_vistos)
            # Lo que la persona ve en este resumen: es lo que «Confirmar» compara (extensión 12a).
            vistos = {f.existencia_id: ",".join(f"{lote_id}:{disponible:f}" for lote_id, disponible, _ in f.lotes) for f in filas}
            plantas_vistas = ",".join(f"{lote_id}:{plantas}" for lote_id, plantas in _servicio(aplicaciones.plantas_del_alcance, request.user, sin_vistos))
        except ErrorDeProduccion as error:
            errores = _errores_por_campo(error)
            firma = ""
    vencimientos = {lote_id: vence for f in filas for lote_id, _, vence in f.lotes}
    grupos = [(tipo, list(lista)) for tipo, lista in groupby(sectores, key=lambda s: s.tipo_etapa)]
    contexto = {
        "invernaderos": invernaderos,
        "invernadero_id": invernadero_id,
        "filas": filas,
        "grupos_de_sectores": grupos,
        "hay_sectores": bool(sectores),
        "marcados": {formularios.entero(s) for s in datos.getlist("sectores")},
        "alcance_elegido": datos.get("alcance", "todo"),
        "valores": dict(datos.items()),
        "errores": errores,
        "resumen": resumen,
        "firma": firma,
        "cambio_la_firma": cambio_la_firma,
        "vistos": vistos,
        "plantas_vistas": plantas_vistas,
        "vencimientos": vencimientos,
        "es_capataz": rol_de(request.user) == CAPATAZ,
    }
    plantilla = "produccion/_aplicacion_formulario.html" if _en_vivo(request) else "produccion/registrar_aplicacion.html"
    return render(request, plantilla, contexto)


# ---- Registrar evento (PROD-REG-EVT) ----


@rol_requerido(AGRONOMO, CAPATAZ, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def registrar_evento(request):
    """«Otro evento» (PROD-REG-EVT, `VIEWS.evento`): invernadero (viene elegido si hay uno solo), lote y sector opcionales y la descripción obligatoria (hasta 500).
    Se registra con la fecha y la hora actuales; no hay edición ni baja de un registro de bitácora. Cambiar el invernadero solo redibuja los lotes y sectores."""
    _ocultar_al_gerente(request)
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    errores, invernadero_id = {}, formularios.entero(datos.get("invernadero"))
    try:
        propuesta = _servicio(bitacora.datos_de_evento, request.user, invernadero_id)
    except ErrorDeProduccion as error:
        errores, invernadero_id = _errores_por_campo(error), None
        propuesta = bitacora.datos_de_evento(request.user)
    if propuesta.invernadero is not None:
        invernadero_id = propuesta.invernadero.pk
    if accion == "confirmar" and invernadero_id:
        try:
            _servicio(bitacora.registrar_evento, request.user, formularios.evento_desde_post({**datos.dict(), "invernadero": invernadero_id}))
            messages.success(request, "El evento quedó registrado en la bitácora.")
            return _volver(request, invernadero_id)
        except ErrorDeProduccion as error:
            errores = _errores_por_campo(error)
    contexto = {
        "propuesta": propuesta,
        "invernadero_id": invernadero_id,
        "valores": dict(datos.items()),
        "errores": errores,
        "es_capataz": rol_de(request.user) == CAPATAZ,
    }
    plantilla = "produccion/_evento_formulario.html" if _en_vivo(request) else "produccion/registrar_evento.html"
    return render(request, plantilla, contexto)


# ---- Consultar bitácora (PROD-CNS-BIT) ----


def contexto_de_la_consulta(usuario, invernadero_id, datos):
    """Lo que necesitan la página y la pestaña: la página de la bitácora, los tipos del filtro, lo escrito en cada filtro y el texto de consulta (para paginar)."""
    filtros = formularios.filtros_de_bitacora(datos)
    error_de_filtro = None
    try:
        pagina = _servicio(bitacora.consultar_bitacora, usuario, invernadero_id, filtros, formularios.entero(datos.get("pagina")) or 1)
    except ErrorDeProduccion as error:
        if error.codigo != "filtro_invalido":
            raise
        error_de_filtro, datos = error.mensaje, {"invernadero": invernadero_id}  # un tipo que no se ofrece: se muestra sin filtros y con el aviso
        pagina = _servicio(bitacora.consultar_bitacora, usuario, invernadero_id, bitacora.FiltrosDeBitacora(), 1)
    consulta = {k: v for k, v in datos.items() if k in ("q", "tipo", "lote", "sector", "desde", "hasta") and v != ""}
    return {
        "pagina": pagina,
        "tipos": bitacora.TIPOS_DE_FILTRO,
        "valores": dict(datos.items()),
        "consulta": urlencode({"invernadero": invernadero_id, **consulta}),
        "puede_registrar": rol_de(usuario) == AGRONOMO and pagina.invernadero.activo,
        "error_de_filtro": error_de_filtro,
    }


@rol_requerido(AGRONOMO, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def consulta(request):
    """«Bitácora» (PROD-CNS-BIT, `bitTab`): los registros de un invernadero por vez, del más reciente al más antiguo y agrupados por día, de a 50, con filtros
    combinables. Es una consulta GET: funciona sin JavaScript; con HTMX cada filtro reemplaza solo los resultados. El Agrónomo (los suyos) y el Gerente (todos, también
    los dados de baja). No audita (SEG-14). El Capataz no la ve."""
    invernaderos = bitacora.invernaderos_de_bitacora(request.user)
    invernadero_id = formularios.entero(request.GET.get("invernadero"))
    if invernadero_id is None and len(invernaderos) == 1:  # regla 1: si hay uno solo, viene elegido
        invernadero_id = invernaderos[0].pk
    contexto = {"invernaderos": invernaderos, "invernadero_id": invernadero_id, "pagina": None}
    if invernadero_id:
        contexto.update(contexto_de_la_consulta(request.user, invernadero_id, request.GET))
    plantilla = "produccion/_bitacora_resultados.html" if _en_vivo(request) and invernadero_id else "produccion/bitacora.html"
    return render(request, plantilla, contexto)
