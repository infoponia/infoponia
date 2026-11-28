# Vistas de `produccion` (PRD-01, paso 8; PRD-02, paso 7): «Producción y órdenes» (lista y detalle), «Nueva siembra» y «Nueva transición», la
# bandeja del Capataz, «Concretar siembra» y «Concretar transición» (para celular) y «Cancelar orden». Las vistas SOLO orquestan: validan la entrada con los formularios, llaman al servicio y
# renderizan; todas las reglas y los cálculos son de `produccion/servicios/`. Todo funciona sin JavaScript (cada pantalla es una página y
# cada acción, un POST); con HTMX solo se redibuja el bloque que cambia, SIN validar ni calcular al escribir (.claude/rules/interfaz.md):
# validar y calcular se hace únicamente con «Ver resumen» y «Confirmar». Quién ve qué (D-30): el Agrónomo a cargo planifica y cancela, el
# Capataz concreta y ve su bandeja, el Gerente solo ve la lista y el detalle (en las demás pantallas, 404, como «Cultivos»).

import hashlib
import json
from types import SimpleNamespace

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario, rol_de
from core.obligatorios import sumar_faltantes
from maestros.models import Invernadero
from produccion import formularios
from produccion.errores import ErrorDeProduccion
from produccion import extensiones
from produccion.models import Lote, Merma, OrdenTrabajo
from produccion.servicios import lotes_existentes, ordenes, siembras, transiciones

AGRONOMO, CAPATAZ, GERENTE = Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ, Usuario.Rol.GERENTE
# Los campos que no entran en la «firma» de lo que se calculó.
SIN_FIRMA = {"csrfmiddlewaretoken", "accion", "firma"}
# UI-06 (UX-27, D-109 punto 9): los obligatorios que no dependen de otros se muestran juntos al enviar. El servicio rechaza en el primero; la vista suma los demás si vinieron vacíos, con el
# texto del servicio (`core/obligatorios.py`). Cada fila: (clave del error, nombre del campo, texto).
OBLIGATORIOS_DE_SIEMBRA = (
    ("fecha_programada", "fecha_programada", "Indicá la fecha programada."),  # siembras.py:353 (`_verificar`), después de la cantidad (:351)
)
OBLIGATORIOS_DE_LOTE_EXISTENTE = (
    ("fecha_siembra", "fecha_siembra", "Indicá la fecha de siembra."),  # lotes_existentes.py:152
    ("fecha_ingreso_etapa", "fecha_ingreso_etapa", "Indicá la fecha de ingreso a la etapa."),  # lotes_existentes.py:156
)
TIPOS_DEL_FILTRO = [(t.value, t.label) for t in ordenes.TIPOS_DE_PRODUCCION]  # solo los de producción (D-67 punto 1), no `Tipo.choices`
ESTADOS_DEL_FILTRO = [(e.value, e.label) for e in OrdenTrabajo.Estado]


def _ocultar_al_gerente(request):
    """El Gerente no ve estas pantallas: 404 (no se le revela que la ruta existe), como en «Cultivos» (regla 4 de PROD-CNS-CLT)."""
    if rol_de(request.user) == GERENTE:
        raise Http404("No existe esa página.")


def _servicio(llamada, *argumentos):
    """Llama a un servicio y traduce lo que la pantalla no maneja: `sin_permiso` es un 403 y `orden_no_cancelable`, un 404 (D-28 y D-30).
    Los demás `ErrorDeProduccion` los ve quien llama."""
    try:
        return llamada(*argumentos)
    except ErrorDeProduccion as error:
        if error.codigo == "sin_permiso":
            raise PermissionDenied(error.mensaje) from error
        if error.codigo == "orden_no_cancelable":
            raise Http404(error.mensaje) from error
        raise


def _firma(datos):
    """Marca de lo que se calculó: cambia si cambia cualquier dato. Al confirmar se compara con lo enviado: si la persona cambió algo después
    de ver el resumen y confirmó sin recalcular (posible sin JavaScript), no se confirma lo que no vio: se recalcula y se muestra el nuevo."""
    texto = json.dumps(sorted((c, v) for c, v in datos.items() if c not in SIN_FIRMA), ensure_ascii=False)
    return hashlib.sha256(texto.encode()).hexdigest()[:20]


def _en_vivo(request):
    return request.headers.get("HX-Request") == "true"


# ---- Producción y órdenes ----


def _hay_periodos_sin_cobertura(usuario):
    """El aviso de la vista «Cosecha» (prototipo `tabCosechas`): el Agrónomo tiene una alerta activa «período sin cobertura completa» en sus invernaderos."""
    from maestros.models import Alerta

    if rol_de(usuario) != AGRONOMO:
        return False
    return Alerta.objects.filter(
        tipo_alerta="comercial_periodo_sin_cobertura", estado_alerta=Alerta.Estado.ACTIVA, invernadero__in=Invernadero.objects.en_alcance_de(usuario)
    ).exists()


@rol_requerido(AGRONOMO, GERENTE)
@require_safe
@vary_on_headers("HX-Request")
def lista(request):
    """«Producción y órdenes» (`VIEWS.prod` / `ordenesTab`): las órdenes de siembra, transición y cosecha con filtros por invernadero, tipo y
    estado (no hay otros tipos en el filtro). El Agrónomo ve las de sus invernaderos; el Gerente, todas y en solo lectura. Con HTMX se
    reemplaza solo la tabla; sin JavaScript, el filtro es un formulario GET."""
    tipo, estado = request.GET.get("tipo", ""), request.GET.get("estado", "")
    filtros = ordenes.FiltrosDeOrdenes(
        invernadero_id=formularios.entero(request.GET.get("invernadero")),
        tipo=tipo if tipo in dict(TIPOS_DEL_FILTRO) else None,
        estado=estado if estado in dict(ESTADOS_DEL_FILTRO) else None,
    )
    filas = ordenes.lista_de_ordenes(request.user, filtros)
    contexto = {
        "filas": filas,
        **ordenes.contexto_de_cosechas(request.user, filas),
        "entradas": extensiones.entradas_de_comercial(request.user),
        "ver_cosechas": filtros.tipo == OrdenTrabajo.Tipo.COSECHA,
        "periodos_sin_cobertura": filtros.tipo == OrdenTrabajo.Tipo.COSECHA and _hay_periodos_sin_cobertura(request.user),
        "invernaderos": Invernadero.objects.en_alcance_de(request.user).order_by("nombre_invernadero", "id"),
        "tipos": TIPOS_DEL_FILTRO,
        "estados": ESTADOS_DEL_FILTRO,
        "filtros": {"invernadero": request.GET.get("invernadero", ""), "tipo": filtros.tipo or "", "estado": filtros.estado or ""},
        "es_gerente": rol_de(request.user) == GERENTE,
        "hay_lotes_existentes": bool(lotes_existentes.invernaderos_disponibles(request.user)),  # PRD-05: «Registrar lote existente»
        "activa": "ordenes",
    }
    plantilla = "produccion/_tabla_de_ordenes.html" if _en_vivo(request) else "produccion/lista.html"
    return render(request, plantilla, contexto)


@rol_requerido(AGRONOMO, GERENTE, CAPATAZ)
@require_safe
def orden(request, orden_id):
    """La ventana de detalle de una orden (`MODALS.orden`): sus datos, sus reservas y sus sectores, y lo que la cuenta puede hacer con
    ella (ningún botón lleva a un 403, D-30). Una orden que la cuenta no ve da 404."""
    detalle = ordenes.detalle_de_orden(request.user, orden_id)
    de_cosecha = ordenes.contexto_de_cosechas(request.user, [SimpleNamespace(orden_id=detalle.orden.pk, tipo_orden=detalle.orden.tipo_orden)])
    return render(
        request,
        "produccion/detalle.html",
        {
            "detalle": detalle,
            "activa": "ordenes",
            "es_gerente": rol_de(request.user) == GERENTE,
            "acciones_de_cosecha": de_cosecha["acciones"].get(detalle.orden.pk),
            "detalle_de_cosecha": de_cosecha["detalles"].get(detalle.orden.pk),
            "origen_de_cosecha": de_cosecha["origenes"].get(detalle.orden.pk),
        },
    )


# ---- Nueva siembra (PROD-PNF-SMB) ----


def _errores_por_campo(error):
    """`{campo: mensaje}` de un `ErrorDeProduccion`; un rechazo sin campo es general."""
    return {error.campo or "general": error.mensaje}


def _para_habilitar_la_semilla(error):
    """Extensión 8b de PROD-PNF-SMB: si el rechazo es `semilla_no_habilitada`, los ids con que la plantilla enlaza a CMP-HAB-IIN
    («Habilitar insumo», `?insumo=&invernadero=`); si no, `None`."""
    return error.datos if error.codigo == "semilla_no_habilitada" else None


@rol_requerido(AGRONOMO, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def nueva_siembra(request):
    """«Nueva siembra» (PROD-PNF-SMB, `VIEWS.siembra`): invernadero → variedad → cantidad y fecha → distribución por sector → insumos
    adicionales → resumen. Cambiar el invernadero o la variedad (HTMX o «Continuar» sin JavaScript) solo redibuja lo que depende de ellos,
    sin validar. «Ver resumen» valida todo y no escribe; «Confirmar planificación» vuelve a verificar bajo bloqueo y escribe."""
    _ocultar_al_gerente(request)
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    invernadero_id, variedad_id = formularios.entero(datos.get("invernadero")), formularios.entero(datos.get("variedad"))
    errores_de_carga = {}
    try:
        ofrecido = _servicio(
            siembras.datos_de_planificacion, request.user, invernadero_id, variedad_id if invernadero_id else None,
            formularios.fecha(datos.get("fecha_programada")),
        )
    except ErrorDeProduccion as error:  # por ejemplo, un invernadero que se dio de baja mientras tanto: se vuelve a la lista de invernaderos
        errores_de_carga = _errores_por_campo(error)
        invernadero_id = variedad_id = None
        ofrecido = siembras.datos_de_planificacion(request.user)
    contexto = {
        "ofrecido": ofrecido,
        "valores": dict(datos.items()),
        "invernadero_id": invernadero_id,
        "variedad_id": variedad_id,
        "prioridades": formularios.PRIORIDADES,
        "errores": errores_de_carga,
        "para_habilitar": None,
        "resumen": None,
        "firma": "",
        "activa": "ordenes",
        "cambio_la_firma": False,
    }
    if accion in ("calcular", "confirmar"):
        if not (invernadero_id and variedad_id):
            contexto["errores"] = {"general": "Elegí el invernadero y la variedad antes de seguir."}
        else:
            planificacion = formularios.siembra_desde_post(datos)
            firma = _firma(datos)
            try:
                if accion == "confirmar" and datos.get("firma") == firma:
                    siembra = _servicio(siembras.planificar_siembra, request.user, planificacion)
                    messages.success(request, f"La orden {siembra.codigo} quedó planificada. El Capataz ya recibió el aviso.")
                    return redirect("produccion:ordenes")
                contexto["cambio_la_firma"] = accion == "confirmar"
                contexto["resumen"] = _servicio(siembras.resumen_de_planificacion, request.user, planificacion)
                contexto["firma"] = firma
            except ErrorDeProduccion as error:
                contexto["errores"] = sumar_faltantes(_errores_por_campo(error), datos, OBLIGATORIOS_DE_SIEMBRA)
                contexto["para_habilitar"] = _para_habilitar_la_semilla(error)
    plantilla = "produccion/_nueva_siembra_formulario.html" if _en_vivo(request) else "produccion/nueva_siembra.html"
    return render(request, plantilla, contexto)


# ---- Registrar lote existente (PROD-REG-LTE, PRD-05) ----


@rol_requerido(AGRONOMO, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def registrar_lote_existente(request):
    """«Registrar lote existente» (PROD-REG-LTE): invernadero → variedad → etapa actual → fechas, plantas y costo → distribución por sector → resumen
    con el asiento. No está en el prototipo: se armó con el patrón de «Nueva siembra» (D-61). Cambiar el invernadero, la variedad o la etapa (HTMX o
    «Continuar» sin JavaScript) solo redibuja lo que depende de ellos, sin validar. «Ver resumen» valida todo y no escribe; «Confirmar registro» vuelve a
    verificar bajo bloqueo y escribe. Tras registrar vuelve a esta dirección con `?registrado=<lote>`, que muestra la confirmación con sus enlaces."""
    _ocultar_al_gerente(request)
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    invernadero_id, variedad_id, etapa_id = (formularios.entero(datos.get(c)) for c in ("invernadero", "variedad", "etapa"))
    errores_de_carga = {}
    try:
        ofrecido = _servicio(
            lotes_existentes.datos_de_registro,
            request.user,
            invernadero_id,
            variedad_id if invernadero_id else None,
            etapa_id if invernadero_id and variedad_id else None,
        )
    except ErrorDeProduccion as error:  # un invernadero que ya no está disponible, una variedad dada de baja...: se vuelve a la lista de invernaderos
        errores_de_carga = _errores_por_campo(error)
        invernadero_id = variedad_id = etapa_id = None
        ofrecido = lotes_existentes.datos_de_registro(request.user)
    contexto = {
        "ofrecido": ofrecido,
        "valores": dict(datos.items()),
        "invernadero_id": invernadero_id,
        "variedad_id": variedad_id,
        "etapa_id": etapa_id,
        "es_primera_etapa": bool(ofrecido.etapas) and etapa_id == ofrecido.etapas[0].etapa_id,
        "errores": errores_de_carga,
        "resumen": None,
        "firma": "",
        "activa": "ordenes",
        "cambio_la_firma": False,
        "registrado": None,
        "entradas": extensiones.entradas_de_comercial(request.user),
    }
    if request.method != "POST" and datos.get("registrado"):
        # La confirmación: solo de un lote de un invernadero que la cuenta tiene a su cargo (si no, no se muestra nada).
        contexto["registrado"] = (
            Lote.objects.filter(pk=formularios.entero(datos.get("registrado")), invernadero__agronomo_id=request.user.pk)
            .select_related("etapa__tipo_etapa", "siembra__variedad")
            .first()
        )
    if accion in ("calcular", "confirmar"):
        if not (invernadero_id and variedad_id and etapa_id):
            # Si el invernadero dejó de estar disponible mientras tanto (extensión 10a), se informa qué cambió y no un genérico.
            contexto["errores"] = errores_de_carga or {"general": "Elegí el invernadero, la variedad y la etapa antes de seguir."}
        else:
            carga = formularios.lote_existente_desde_post(datos)
            firma = _firma(datos)
            try:
                if accion == "confirmar" and datos.get("firma") == firma:
                    lote = _servicio(lotes_existentes.registrar_lote_existente, request.user, carga)
                    messages.success(request, f"El lote {lote.codigo} quedó registrado.")
                    return redirect(f"{request.path}?registrado={lote.pk}")
                contexto["cambio_la_firma"] = accion == "confirmar"
                contexto["resumen"] = _servicio(lotes_existentes.resumen_de_registro, request.user, carga)
                contexto["firma"] = firma
            except ErrorDeProduccion as error:
                contexto["errores"] = sumar_faltantes(_errores_por_campo(error), datos, OBLIGATORIOS_DE_LOTE_EXISTENTE)
    plantilla = "produccion/_lote_existente_formulario.html" if _en_vivo(request) else "produccion/registrar_lote_existente.html"
    return render(request, plantilla, contexto)


# ---- Bandeja y «Concretar siembra» (PROD-CNC-SMB) ----


@rol_requerido(CAPATAZ)
@require_safe
def bandeja(request):
    """La bandeja del Capataz (`VIEWS.bandeja`): sus órdenes «a realizar», en «vencidas», «hoy» y «próximas», por fecha y prioridad."""
    bandeja_ = ordenes.bandeja_del_capataz(request.user)
    return render(
        request,
        "produccion/bandeja.html",
        {"bandeja": bandeja_, **ordenes.contexto_de_cosechas(request.user, [*bandeja_.vencidas, *bandeja_.hoy, *bandeja_.proximas])},
    )


@rol_requerido(CAPATAZ)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def concretar(request, orden_id):
    """«Concretar siembra» (PROD-CNC-SMB, `VIEWS['c-siembra']`), pensada para el celular: fecha, lo sembrado por sector, el motivo de la
    diferencia, lo utilizado y devuelto de cada insumo y los lotes de los que sale. El sistema propone todo; el Capataz solo cambia lo que
    difiere. «Ver resumen» valida y no escribe; «Confirmar concreción» vuelve a verificar bajo bloqueo y escribe. Una orden que ya no está
    «a realizar» (extensión 19a) no se abre: se informa su estado y se vuelve a la bandeja. Una transición se concreta con «Concretar
    transición» (misma dirección: la bandeja no distingue)."""
    if OrdenTrabajo.objects.filter(pk=orden_id, tipo_orden=OrdenTrabajo.Tipo.TRANSICION).exists():
        return _concretar_transicion(request, orden_id)
    try:
        propuesta = _servicio(siembras.datos_de_concrecion, request.user, orden_id)
    except ErrorDeProduccion as error:
        messages.warning(request, error.mensaje)
        return redirect("produccion:bandeja")
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    contexto = {
        "propuesta": propuesta,
        "valores": dict(datos.items()),
        "lotes_de_insumo": siembras.lotes_de_insumo_disponibles([f.existencia_id for f in propuesta.reservas]),
        "errores": {},
        "resumen": None,
        "firma": "",
        "cambio_la_firma": False,
    }
    if accion in ("calcular", "confirmar"):
        concrecion = formularios.concrecion_desde_post(datos, propuesta.reservas)
        firma = _firma(datos)
        try:
            if accion == "confirmar" and datos.get("firma") == firma:
                lote = _servicio(siembras.concretar_siembra, request.user, orden_id, concrecion)
                messages.success(request, f"La siembra quedó concretada: se creó el lote {lote.codigo}.")
                return redirect("produccion:bandeja")
            contexto["cambio_la_firma"] = accion == "confirmar"
            contexto["resumen"] = _servicio(siembras.resumen_de_concrecion, request.user, orden_id, concrecion)
            contexto["firma"] = firma
        except ErrorDeProduccion as error:
            if error.codigo == "orden_no_pendiente":
                messages.warning(request, error.mensaje)
                return redirect("produccion:bandeja")
            contexto["errores"] = _errores_por_campo(error)
    return render(request, "produccion/concretar.html", contexto)


# ---- Cancelar orden (PROD-CNL-ORD) ----


@rol_requerido(AGRONOMO, GERENTE)
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def cancelar(request, orden_id):
    """«Cancelar orden» (PROD-CNL-ORD, `ACT['orden-cancelar']`): el resumen de lo que libera la cancelación (reservas y agujeros), el motivo
    obligatorio (hasta 300 caracteres) y la confirmación. Es una página y un POST: funciona sin JavaScript."""
    _ocultar_al_gerente(request)
    try:
        resumen = _servicio(ordenes.resumen_de_cancelacion, request.user, orden_id)
    except ErrorDeProduccion as error:
        messages.warning(request, error.mensaje)
        return redirect("produccion:ordenes")
    contexto = {"resumen": resumen, "motivo": "", "errores": {}, "activa": "ordenes"}
    if request.method == "POST":
        contexto["motivo"] = request.POST.get("motivo", "")
        try:
            _servicio(ordenes.cancelar_orden, request.user, orden_id, contexto["motivo"])
        except ErrorDeProduccion as error:
            if error.codigo == "orden_no_pendiente":
                messages.warning(request, error.mensaje)
                return redirect("produccion:ordenes")
            contexto["errores"] = _errores_por_campo(error)
        else:
            messages.success(request, f"La orden {resumen.orden.codigo} quedó cancelada. Se liberaron sus reservas y sus agujeros.")
            return redirect("produccion:ordenes")
    return render(request, "produccion/cancelar.html", contexto)


# ---- Nueva transición (PROD-PNF-TRN) ----

CAUSAS_DE_LA_MERMA = [(c.value, c.label) for c in Merma.CAUSAS_EN_PIE]  # COM-04a: sin las de cámara y entrega
CODIGOS_DE_LA_CAUSA = ("causa_obligatoria", "causa_invalida", "descripcion_larga")


@rol_requerido(AGRONOMO, GERENTE)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def nueva_transicion(request):
    """«Nueva transición» (PROD-PNF-TRN, `VIEWS.transicion`): lote trasladable → fecha → distribución por sector destino → resumen. Elegir
    el lote (HTMX o «Continuar» sin JavaScript) solo redibuja lo que depende de él, sin validar. «Ver resumen» valida todo y no escribe;
    «Confirmar transición» vuelve a verificar bajo bloqueo y escribe. La cantidad y la etapa que se vieron viajan en campos ocultos: si
    cambiaron al confirmar, el servicio lo informa (extensiones 13a y 13b). El Gerente, 404."""
    _ocultar_al_gerente(request)
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    lote_id = formularios.entero(datos.get("lote"))
    errores = {}
    try:
        ofrecido = _servicio(transiciones.datos_de_planificacion, request.user, lote_id, formularios.fecha(datos.get("fecha_programada")))
    except ErrorDeProduccion as error:  # el lote ya no se puede elegir (3a, 3b o 3c): se vuelve a la lista de lotes con el motivo
        errores = _errores_por_campo(error)
        lote_id = None
        ofrecido = transiciones.datos_de_planificacion(request.user)
    valores = dict(datos.items())
    resumen, firma, cambio_la_firma = None, "", False
    if accion in ("calcular", "confirmar"):
        if not ofrecido.lote:
            errores = errores or {"general": "Elegí el lote antes de seguir."}
        else:
            planificacion = formularios.transicion_desde_post(datos)
            firma = _firma(datos)
            try:
                if accion == "confirmar" and datos.get("firma") == firma:
                    orden = _servicio(transiciones.planificar_transicion, request.user, planificacion)
                    messages.success(request, f"La orden {orden.codigo} quedó planificada. El Capataz ya recibió el aviso.")
                    return redirect("produccion:ordenes")
                cambio_la_firma = accion == "confirmar"
                resumen = _servicio(transiciones.resumen_de_planificacion, request.user, planificacion)
            except ErrorDeProduccion as error:
                errores = _errores_por_campo(error)
                if error.codigo == "cambio_simultaneo":  # 13a y 13b: se descarta la distribución y se muestra lo nuevo
                    valores = {c: v for c, v in valores.items() if not c.startswith("sector_") and c not in ("cantidad_vista", "etapa_vista")}
                firma = ""
    contexto = {
        "ofrecido": ofrecido,
        "valores": valores,
        "lote_id": ofrecido.lote.lote_id if ofrecido.lote else None,
        "hay_trasladables": any(f.trasladable for f in ofrecido.lotes),
        "motivos": transiciones.MOTIVOS,
        "prioridades": formularios.PRIORIDADES,
        "errores": errores,
        "resumen": resumen,
        "firma": firma,
        "cambio_la_firma": cambio_la_firma,
        "activa": "ordenes",
    }
    plantilla = "produccion/_nueva_transicion_formulario.html" if _en_vivo(request) else "produccion/nueva_transicion.html"
    return render(request, plantilla, contexto)


# ---- «Concretar transición» (PROD-CNC-TRN) ----


def _concretar_transicion(request, orden_id):
    """«Concretar transición» (PROD-CNC-TRN, `VIEWS['c-trans']`), pensada para el celular: fecha del traslado, plantas ubicadas en cada sector
    destino (el sistema propone lo planificado, o su parte proporcional si el lote perdió plantas), y, solo si faltan plantas, la causa de
    la merma. «Ver resumen» valida y no escribe; «Confirmar transición» vuelve a verificar bajo bloqueo y escribe. Una orden que ya no está
    «a realizar» (13b) o un lote sin plantas (4a) no se abre: se informa y se vuelve a la bandeja."""
    try:
        propuesta = _servicio(transiciones.datos_de_concrecion, request.user, orden_id)
    except ErrorDeProduccion as error:
        messages.warning(request, error.mensaje)
        return redirect("produccion:bandeja")
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    valores = dict(datos.items())
    errores, resumen, firma, cambio_la_firma = {}, None, "", False
    if accion in ("calcular", "confirmar"):
        concrecion = formularios.concrecion_de_transicion_desde_post(datos)
        firma = _firma(datos)
        try:
            if accion == "confirmar" and datos.get("firma") == firma:
                orden = _servicio(transiciones.concretar_transicion, request.user, orden_id, concrecion)
                messages.success(
                    request, f"La transición quedó concretada: el lote {orden.lote.codigo} pasó a {orden.etapa_destino.tipo_etapa.nombre_etapa}."
                )
                return redirect("produccion:bandeja")
            cambio_la_firma = accion == "confirmar"
            resumen = _servicio(transiciones.resumen_de_concrecion, request.user, orden_id, concrecion)
        except ErrorDeProduccion as error:
            if error.codigo in ("orden_no_pendiente", "lote_sin_plantas"):
                messages.warning(request, error.mensaje)
                return redirect("produccion:bandeja")
            errores = _errores_por_campo(error)
            firma = ""
            if error.codigo == "cambio_simultaneo":  # 13a y 13c: se vuelve a proponer con lo que hay ahora
                valores = {c: v for c, v in valores.items() if not c.startswith("ubicadas_") and c != "cantidad_vista"}
    contexto = {
        "propuesta": propuesta,
        "valores": valores,
        "errores": errores,
        "resumen": resumen,
        "firma": firma,
        "cambio_la_firma": cambio_la_firma,
        "causas": CAUSAS_DE_LA_MERMA,
        "causas_legibles": dict(CAUSAS_DE_LA_MERMA),
        # La causa solo aparece cuando faltan plantas: lo sabe el servicio al validar (10a), no la pantalla al escribir.
        "pide_causa": any(c in errores for c in ("causa", "descripcion")) or bool(resumen and resumen.plantas_sin_trasladar) or bool(valores.get("causa")),
        "activa": "ordenes",
    }
    return render(request, "produccion/concretar_transicion.html", contexto)
