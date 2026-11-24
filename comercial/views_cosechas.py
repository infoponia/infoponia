# Vistas de las cosechas de `comercial` (COM-04a): «Planificar cosecha», «Modificar cosecha», «Concretar cosecha» (para celular) y «Cancelar cosecha»
# (docs/casos_de_uso/produccion/cosecha.md y cancelar_orden.md, «Pantallas»). Las vistas SOLO orquestan: arman los datos del pedido, llaman al servicio
# (`comercial/servicios/cosechas.py`) y renderizan; todas las reglas son del servicio (docs/patrones/abm.md, sección 1). Sin JavaScript todo funciona:
# cada pantalla es una página, «Actualizar» redibuja, «Ver resumen» valida y «Confirmar» escribe. Con HTMX solo se redibuja el bloque que cambia y NUNCA se valida
# ni se calcula al escribir (`.claude/rules/interfaz.md`): los selectores redibujan sin validar, con ``hx-swap="innerHTML show:none"``. Las páginas `calcular/` no
# escriben nada.

import hashlib
import json
from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import cosechas
from comercial.servicios.cosechas import DatosDeConcrecion, DatosDeCosecha, DatosDeModificacion
from core.acceso import rol_requerido
from core.models import Usuario
from produccion.models import Merma

AGRONOMO, CAPATAZ = Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ
NO_CAMPO = "__all__"
SIN_FIRMA = {"csrfmiddlewaretoken", "firma", "huella", "confirmar"}
CAUSAS = [(c.value, c.label) for c in Merma.CAUSAS_EN_PIE if c != Merma.Causa.DESCARTE_POR_SELECCION]
PRIORIDADES = [("alta", "Alta"), ("media", "Media"), ("baja", "Baja")]


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _entero(texto):
    """El entero que escribió la persona; `None` si está vacío y el texto tal cual si no es un número (el servicio lo rechaza con su error)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return texto


def _fecha(texto):
    """La fecha de un campo `<input type=date>` (`aaaa-mm-dd`); `None` si falta o no se entiende."""
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def _clave(campo):
    """Las plantillas de Django no leen claves que empiezan con guion bajo: lo general (`__all__`) se llama `general`."""
    return "general" if campo == NO_CAMPO else campo


def _mensajes(error):
    """`{campo: [mensajes]}` de un `ValidationError` del servicio (los generales, bajo `general`)."""
    if hasattr(error, "error_dict"):
        return {_clave(campo): [e.message for e in lista] for campo, lista in error.error_dict.items()}
    return {"general": error.messages}


def _de_la_verificacion(errores):
    """`{campo: [mensajes]}` de lo que devuelve `verificar_*` (`{campo: [(codigo, mensaje)]}`)."""
    return {_clave(campo): [mensaje for _, mensaje in lista] for campo, lista in errores.items()}


def _firma(post):
    """Marca de lo que se calculó: cambia si cambia cualquier dato. Al confirmar se compara con lo enviado: si la persona cambió algo después de ver el
    resumen y confirmó sin volver a verlo (posible sin JavaScript), no se confirma lo que no vio: se recalcula y se muestra el nuevo (como en `produccion`)."""
    texto = json.dumps(sorted((c, v) for c, v in post.items() if c not in SIN_FIRMA), ensure_ascii=False)
    return hashlib.sha256(texto.encode()).hexdigest()[:20]


def _valores(post):
    """Lo que escribió la persona, para volver a mostrarlo: un diccionario simple."""
    return {c: v for c, v in post.items() if c not in {"csrfmiddlewaretoken"}}


def _pantalla(request, plantilla, parcial, contexto):
    """La página completa o, con HTMX, solo el bloque del formulario."""
    return render(request, parcial if _es_htmx(request) else plantilla, contexto)


# ---- Planificar cosecha (PROD-PNF-CSC) ----


def _datos_de_planificacion(valores):
    """`DatosDeCosecha` a partir de lo que llegó (los lotes sin cantidad no cuentan)."""
    lotes = []
    for campo, valor in valores.items():
        if campo.startswith("lote_") and (valor or "").strip():
            lotes.append((int(campo[5:]), _entero(valor)))
    modo = valores.get("modo", "contrato")
    return DatosDeCosecha(
        invernadero_id=_entero(valores.get("invernadero")) if isinstance(_entero(valores.get("invernadero")), int) else 0,
        clave_de_detalle=valores.get("detalle", "") if modo == "contrato" else "",
        variedad_id=_entero(valores.get("variedad")) if modo == "sin" and isinstance(_entero(valores.get("variedad")), int) else None,
        fecha_programada=_fecha(valores.get("fecha_programada")),
        prioridad=valores.get("prioridad", "media") or "media",
        descripcion=valores.get("descripcion", ""),
        lotes=tuple(sorted(lotes)),
    )


def _contexto_de_planificacion(request, valores, errores=None, verificacion=None, firma="", aviso_de_cambio=False):
    """Lo que necesita la pantalla: los invernaderos (con su motivo si no pueden), los detalles o las variedades del invernadero elegido, los lotes
    cosechables y, si se pidió, el resumen. Solo lectura."""
    invernaderos = cosechas.invernaderos_para_cosechar(request.user)
    elegido = _entero(valores.get("invernadero"))
    habilitado = next((f for f in invernaderos if f.invernadero.pk == elegido and f.motivo is None), None)
    detalles, variedades, lotes, variedad_id = [], [], [], None
    modo = valores.get("modo", "contrato")
    if habilitado is not None:
        detalles = cosechas.detalles_cubribles(request.user, habilitado.invernadero.pk, valores.get("busqueda", ""))
        variedades = cosechas.variedades_sin_contrato(request.user, habilitado.invernadero.pk)
        if modo == "contrato":
            variedad_id = next((d.variedad_id for d in detalles if d.clave == valores.get("detalle")), None)
        else:
            variedad_id = _entero(valores.get("variedad")) if isinstance(_entero(valores.get("variedad")), int) else None
        if variedad_id is not None:
            lotes = cosechas.lotes_cosechables(habilitado.invernadero.pk, variedad_id, _fecha(valores.get("fecha_programada")))
    return {
        "invernaderos": invernaderos,
        "habilitado": habilitado,
        "detalles": detalles,
        "variedades": variedades,
        "lotes": lotes,
        "valores": valores,
        "modo": modo,
        "prioridades": PRIORIDADES,
        "errores": errores or {},
        "verificacion": verificacion,
        "firma": firma,
        "aviso_de_cambio": aviso_de_cambio,
        "activa": "ordenes",
    }


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def planificar(request):
    """«Planificar cosecha» (PROD-PNF-CSC, `VIEWS.cscnew`): invernadero → con o sin contrato → detalle o variedad → fecha y prioridad → lotes → resumen →
    «Confirmar planificación». El GET abre el formulario vacío; el POST confirma: vuelve a verificar todo bajo bloqueo y escribe (15b)."""
    if request.method != "POST":
        return render(request, "comercial/cosechas/planificar.html", _contexto_de_planificacion(request, {"modo": "contrato", "prioridad": "media"}))
    valores = _valores(request.POST)
    datos = _datos_de_planificacion(valores)
    if request.POST.get("firma") != _firma(request.POST):  # cambió algo después de ver el resumen: se muestra de nuevo
        return _revisar(request, valores, datos, aviso_de_cambio=True)
    try:
        cosecha = cosechas.planificar_cosecha(request.user, datos)
    except ValidationError as error:
        return render(request, "comercial/cosechas/planificar.html", _contexto_de_planificacion(request, valores, _mensajes(error)))
    messages.success(request, f"Cosecha {cosecha.codigo} planificada: el Capataz ya la tiene en su bandeja.")
    return redirect(f"{reverse('produccion:ordenes')}?tipo=cosecha")


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def planificar_calcular(request):
    """Redibuja el formulario con lo elegido (invernadero, modo, detalle, variedad o fecha: lo que cambia las opciones de abajo). **No valida y no escribe.**"""
    return _pantalla(
        request, "comercial/cosechas/planificar.html", "comercial/cosechas/_planificar_formulario.html", _contexto_de_planificacion(request, _valores(request.POST))
    )


def _revisar(request, valores, datos, aviso_de_cambio=False):
    """El resumen de la planificación: `verificar_cosecha` (no escribe). Con errores, vuelve al formulario con ellos."""
    try:
        verificacion = cosechas.verificar_cosecha(request.user, datos)
    except Http404:
        raise
    contexto = _contexto_de_planificacion(
        request, valores, _de_la_verificacion(verificacion.errores), None if verificacion.errores else verificacion, _firma(request.POST), aviso_de_cambio
    )
    return render(request, "comercial/cosechas/planificar.html", contexto)


@rol_requerido(AGRONOMO)
@never_cache
@require_POST
def planificar_revisar(request):
    """«Ver resumen» (paso 13): valida y muestra lo que se va a registrar. **No escribe.**"""
    valores = _valores(request.POST)
    return _revisar(request, valores, _datos_de_planificacion(valores))


# ---- Modificar cosecha (PROD-MOD-CSC) ----


def _datos_de_modificacion(valores):
    """`DatosDeModificacion` a partir de lo que llegó (lo que la pantalla no ofrece, 5c, nunca viaja)."""
    lotes = []
    for campo, valor in valores.items():
        if campo.startswith("lote_") and (valor or "").strip():
            lotes.append((int(campo[5:]), _entero(valor)))
    return DatosDeModificacion(
        fecha_programada=_fecha(valores.get("fecha_programada")),
        prioridad=valores.get("prioridad", "media") or "media",
        descripcion=valores.get("descripcion", ""),
        lotes=tuple(sorted(lotes)),
    )


def _contexto_de_modificacion(request, cosecha_id, valores=None, errores=None, verificacion=None, firma="", aviso_de_cambio=False):
    """La ficha de la cosecha y los valores del formulario (los guardados si no se envió nada)."""
    ficha = cosechas.datos_de_modificacion(request.user, cosecha_id)
    if valores is None:
        valores = {"fecha_programada": ficha.cosecha.fecha_programada_orden.isoformat(), "prioridad": ficha.cosecha.prioridad_orden, "descripcion": ficha.cosecha.descripcion_orden}
        valores.update({f"lote_{l.lote_id}": str(l.reservada) for l in ficha.lineas})
    propias = {l.lote_id: l for l in ficha.lineas}
    para_elegir = [(l.lote_id, l.codigo, l.libre, l.fecha_maxima, propias[l.lote_id].reservada if l.lote_id in propias else 0) for l in ficha.lotes]
    para_elegir += [(l.lote_id, l.codigo, l.libre, l.fecha_maxima, l.reservada) for l in ficha.lineas if l.lote_id not in {x.lote_id for x in ficha.lotes}]
    return {
        "ficha": ficha,
        "cosecha": ficha.cosecha,
        "lotes_para_elegir": sorted(para_elegir),
        "valores": valores,
        "prioridades": PRIORIDADES,
        "errores": errores or {},
        "verificacion": verificacion,
        "firma": firma,
        "huella": valores.get("huella") or ficha.huella,
        "aviso_de_cambio": aviso_de_cambio,
        "activa": "ordenes",
    }


def _pagina_de_cosecha(request, cosecha_id, vista, volver_a=None):
    """Corre `vista` y traduce lo que la pantalla no maneja: una cosecha que ya no está «a realizar» (8a, 10a y 13b) vuelve a la lista (al Agrónomo) o a la
    bandeja (al Capataz) con su estado actual; un 403 es un 403."""
    try:
        return vista()
    except ValidationError as error:
        if hasattr(error, "error_dict") and any(e.code in ("cosecha_resuelta", "orden_no_a_realizar") for lista in error.error_dict.values() for e in lista):
            messages.error(request, " ".join(m for lista in _mensajes(error).values() for m in lista))
            return redirect(volver_a or f"{reverse('produccion:ordenes')}?tipo=cosecha")
        raise


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def modificar(request, cosecha_id):
    """«Modificar cosecha» (PROD-MOD-CSC, `VIEWS.cscmod`): fecha, prioridad, descripción y reparto entre lotes; no ofrece variedad, invernadero, contrato ni
    cantidad total (5c). El GET abre la cosecha; el POST confirma (vuelve a verificar bajo bloqueo, 10a y 10b)."""

    def vista():
        if request.method != "POST":
            return render(request, "comercial/cosechas/modificar.html", _contexto_de_modificacion(request, cosecha_id))
        valores = _valores(request.POST)
        if request.POST.get("firma") != _firma(request.POST):
            return _revisar_modificacion(request, cosecha_id, valores, aviso_de_cambio=True)
        try:
            cosecha = cosechas.modificar_cosecha(request.user, cosecha_id, _datos_de_modificacion(valores), valores.get("huella", ""))
        except ValidationError as error:
            codigos = {e.code for lista in getattr(error, "error_dict", {}).values() for e in lista}
            if "cosecha_resuelta" in codigos:
                raise
            if "cosecha_cambio" in codigos:
                messages.error(request, "Mientras modificabas, la cosecha cambió. Mirá cómo quedó y volvé a indicar tus cambios.")
                return redirect(reverse("comercial:cosecha_modificar", args=[cosecha_id]))
            return render(request, "comercial/cosechas/modificar.html", _contexto_de_modificacion(request, cosecha_id, valores, _mensajes(error)))
        messages.success(request, f"Cosecha {cosecha.codigo} modificada: el Capataz ya tiene el aviso.")
        return redirect(f"{reverse('produccion:ordenes')}?tipo=cosecha")

    return _pagina_de_cosecha(request, cosecha_id, vista)


def _revisar_modificacion(request, cosecha_id, valores, aviso_de_cambio=False):
    """El resumen de la modificación (paso 8): cada cambio con su valor anterior y el nuevo. **No escribe.**"""
    verificacion = cosechas.verificar_modificacion(request.user, cosecha_id, _datos_de_modificacion(valores))
    contexto = _contexto_de_modificacion(
        request, cosecha_id, valores, _de_la_verificacion(verificacion.errores), None if verificacion.errores else verificacion, _firma(request.POST), aviso_de_cambio
    )
    return render(request, "comercial/cosechas/modificar.html", contexto)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def modificar_calcular(request, cosecha_id):
    """Redibuja el formulario con lo que escribió la persona. **No valida y no escribe.**"""
    return _pagina_de_cosecha(
        request,
        cosecha_id,
        lambda: _pantalla(
            request, "comercial/cosechas/modificar.html", "comercial/cosechas/_modificar_formulario.html", _contexto_de_modificacion(request, cosecha_id, _valores(request.POST))
        ),
    )


@rol_requerido(AGRONOMO)
@never_cache
@require_POST
def modificar_revisar(request, cosecha_id):
    """«Ver resumen» (paso 8). **No escribe.**"""
    return _pagina_de_cosecha(request, cosecha_id, lambda: _revisar_modificacion(request, cosecha_id, _valores(request.POST)))


# ---- Concretar cosecha (PROD-CNC-CSC), para celular ----


def _datos_de_concrecion(valores):
    """`DatosDeConcrecion` a partir de lo que llegó: `cant_<lote>_<sector>`, `perd_<lote>_<sector>`, `causa_<lote>` y `desc_<lote>`; lo que se deja vacío toma la
    propuesta (cantidades) o cero (perdidas)."""
    cantidades, perdidas, causas = [], [], {}
    for campo, valor in valores.items():
        partes = campo.split("_")
        if campo.startswith(("cant_", "perd_")) and len(partes) == 3 and (valor or "").strip():
            (cantidades if partes[0] == "cant" else perdidas).append((int(partes[1]), int(partes[2]), _entero(valor)))
        elif campo.startswith("causa_") and (valor or "").strip():
            causas[int(partes[1])] = [valor.strip(), causas.get(int(partes[1]), ["", ""])[1]]
    for campo, valor in valores.items():
        if campo.startswith("desc_") and int(campo[5:]) in causas:
            causas[int(campo[5:])][1] = valor
    return DatosDeConcrecion(
        fecha_efectiva=_fecha(valores.get("fecha_efectiva")),
        cantidades=tuple(cantidades),
        perdidas=tuple(perdidas),
        causas=tuple((l, c, d) for l, (c, d) in causas.items()),
    )


def _contexto_de_concrecion(request, cosecha_id, valores=None, errores=None, resumen=None, firma="", aviso_de_cambio=False):
    """La ficha de la cosecha con su propuesta por sector y, si se pidió, el resumen. Solo lectura."""
    ficha = cosechas.datos_de_concrecion(request.user, cosecha_id)
    return {
        "ficha": ficha,
        "cosecha": ficha.cosecha,
        "valores": valores or {},
        "errores": errores or {},
        "resumen": resumen,
        "firma": firma,
        "causas": CAUSAS,
        "aviso_de_cambio": aviso_de_cambio,
        "activa": "bandeja",
    }


def _revisar_concrecion(request, cosecha_id, valores, aviso_de_cambio=False):
    """El resumen de la concreción (paso 11): por lote, lo reservado, lo cosechado, el excedente, lo perdido y el destino. **No escribe.**"""
    resumen = cosechas.verificar_concrecion(request.user, cosecha_id, _datos_de_concrecion(valores))
    contexto = _contexto_de_concrecion(
        request, cosecha_id, valores, _de_la_verificacion(resumen.errores), None if resumen.errores else resumen, _firma(request.POST), aviso_de_cambio
    )
    return render(request, "comercial/cosechas/concretar.html", contexto)


@rol_requerido(CAPATAZ)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def concretar(request, cosecha_id):
    """«Concretar cosecha» (PROD-CNC-CSC, `VIEWS.capcsc`), pensada para el celular: fecha → cantidad por sector → plantas perdidas → resumen. El sistema propone
    todo; el Capataz solo escribe lo que difiere. Una cosecha que ya no está «a realizar» (13b) no se abre: se informa su estado y se vuelve a la bandeja. El
    GET abre la carga; el POST confirma (vuelve a verificar bajo bloqueo)."""

    def vista():
        if request.method != "POST":
            cosechas._exigir_a_realizar(cosechas._cosecha_del_capataz(request.user, cosecha_id))  # 13b: no se abre una que ya no está «a realizar»
            return render(request, "comercial/cosechas/concretar.html", _contexto_de_concrecion(request, cosecha_id))
        valores = _valores(request.POST)
        if request.POST.get("firma") != _firma(request.POST):
            return _revisar_concrecion(request, cosecha_id, valores, aviso_de_cambio=True)
        try:
            resultado = cosechas.concretar_cosecha(request.user, cosecha_id, _datos_de_concrecion(valores))
        except ValidationError as error:
            if any(e.code == "orden_no_a_realizar" for lista in getattr(error, "error_dict", {}).values() for e in lista):
                raise
            return render(request, "comercial/cosechas/concretar.html", _contexto_de_concrecion(request, cosecha_id, valores, _mensajes(error)))
        messages.success(request, f"Cosecha {resultado.cosecha.codigo} concretada.")
        return redirect("produccion:bandeja")

    return _pagina_de_cosecha(request, cosecha_id, vista, reverse("produccion:bandeja"))


@rol_requerido(CAPATAZ)
@never_cache
@vary_on_headers("HX-Request")
@require_POST
def concretar_calcular(request, cosecha_id):
    """Redibuja la carga con lo escrito. **No valida y no escribe.**"""
    return _pagina_de_cosecha(
        request,
        cosecha_id,
        lambda: _pantalla(request, "comercial/cosechas/concretar.html", "comercial/cosechas/_concretar_formulario.html", _contexto_de_concrecion(request, cosecha_id, _valores(request.POST))),
        reverse("produccion:bandeja"),
    )


@rol_requerido(CAPATAZ)
@never_cache
@require_POST
def concretar_revisar(request, cosecha_id):
    """«Ver resumen» (paso 11). **No escribe.**"""
    return _pagina_de_cosecha(request, cosecha_id, lambda: _revisar_concrecion(request, cosecha_id, _valores(request.POST)), reverse("produccion:bandeja"))


# ---- Cancelar cosecha (PROD-CNL-ORD) ----


def _contexto_de_cancelacion(request, cosecha_id, motivo="", errores=None):
    """El resumen de la cancelación (4b, 4c, 6b y 6c)."""
    resumen = cosechas.resumen_de_cancelacion_de_cosecha(request.user, cosecha_id)
    return {"resumen": resumen, "cosecha": resumen.cosecha, "motivo": motivo, "errores": errores or {}, "activa": "ordenes"}


@rol_requerido(AGRONOMO)
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def cancelar(request, cosecha_id):
    """«Cancelar cosecha» (PROD-CNL-ORD, `MODALS.cnlcsc`), como página (cada ventana es una página, D-47): lo que se libera, lo que se vuelve a cubrir y el
    motivo obligatorio. El POST cancela (vuelve a verificar bajo bloqueo: 8a y 8b)."""

    def vista():
        if request.method != "POST":
            return render(request, "comercial/cosechas/cancelar.html", _contexto_de_cancelacion(request, cosecha_id))
        motivo = request.POST.get("motivo", "")
        try:
            resultado = cosechas.cancelar_cosecha(request.user, cosecha_id, motivo, request.POST.get("huella", ""))
        except ValidationError as error:
            if any(e.code == "cosecha_cambio" for lista in getattr(error, "error_dict", {}).values() for e in lista):
                messages.error(request, "Mientras mirabas el resumen, la cosecha o su contrato cambiaron. Revisalo de nuevo.")
                return redirect(reverse("comercial:cosecha_cancelar", args=[cosecha_id]))
            if any(e.code == "orden_no_a_realizar" for lista in getattr(error, "error_dict", {}).values() for e in lista):
                raise
            return render(request, "comercial/cosechas/cancelar.html", _contexto_de_cancelacion(request, cosecha_id, motivo, _mensajes(error)))
        messages.success(request, f"Cosecha {resultado.cosecha.codigo} cancelada.")
        return redirect(f"{reverse('produccion:ordenes')}?tipo=cosecha")

    return _pagina_de_cosecha(request, cosecha_id, vista)
