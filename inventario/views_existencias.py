# Vistas de «Existencias de insumos» (INV-02, paso 8): la pestaña (CMP-CNS-IIN) y las ventanas «Habilitar insumo» (CMP-HAB-IIN), «Mínimo y
# precio» (CMP-MOD-IIN) y «Deshabilitar» (CMP-DSH-IIN). Las vistas solo orquestan: validan la entrada, llaman al servicio y renderizan.
# Solo el Agrónomo a cargo del invernadero: otros roles reciben 403 (``rol_requerido``) y un Agrónomo ajeno también (el servicio lanza
# ``PermissionDenied``). Ningún botón lleva a un 403 (D-30): lo que la cuenta no puede hacer no se ofrece (``acciones_permitidas``).
#
# Ventanas (D-47, patrón ABM §7): como en el catálogo, cada una es una vista con dos formas. Con HTMX devuelve solo la ventana; sin
# JavaScript, la pestaña completa con la ventana abierta (``plantilla_de_ventana``). Los formularios envían con un POST común.

from collections import namedtuple

from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from core.obligatorios import faltantes
from inventario import forms
from inventario.models import InsumoInvernadero, TipoInsumo
from inventario.servicios import alertas_de_stock
from inventario.servicios import insumos as api_insumos
from inventario.servicios import insumos_invernadero as api_iin
from inventario.views import _pasar_errores
from maestros.models import Invernadero

AGRONOMO = Usuario.Rol.AGRONOMO
PLANTILLA_DE_HABILITAR = "inventario/existencias/_ventana_habilitar.html"
# UI-06 (UX-27): los obligatorios de «Habilitar» que el servicio mira recién cuando el insumo y el invernadero están elegidos. Fila: (campo del formulario, nombre, texto).
OBLIGATORIOS_DE_HABILITAR = (
    ("cant_min", "cant_min", "Ingresá el stock mínimo."),
    ("referencia_precio", "referencia_precio", "Ingresá el precio de referencia."),
)
PLANTILLA_DE_MINIMO = "inventario/existencias/_ventana_minimo.html"
PLANTILLA_DE_DESHABILITAR = "inventario/existencias/_ventana_deshabilitar.html"


def _entero(valor):
    """``valor`` como ``int`` o ``None`` (los filtros llegan como texto en la URL)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _contexto_de_existencias(request, **extra):
    """Lo que necesita la pestaña: las filas de ``consultar_existencias`` con los filtros del CU (regla 2: invernadero, categoría, «con
    vencimientos» y «bajo el mínimo»), las listas de los filtros y, si venimos de habilitar un insumo, el aviso «Cargar stock inicial»."""
    invernadero_id = _entero(request.GET.get("invernadero"))
    categoria_id = _entero(request.GET.get("categoria"))
    con_vencimientos = request.GET.get("vencimientos") == "1"
    bajo_minimo = request.GET.get("bajo_minimo") == "1"
    filas = api_iin.consultar_existencias(
        request.user,
        invernadero_id=invernadero_id,
        categoria_id=categoria_id,
        con_vencimientos=con_vencimientos,
        bajo_minimo=bajo_minimo,
    )
    recien = None
    recien_id = _entero(request.GET.get("recien"))
    if recien_id is not None:  # solo una existencia propia y activa: nunca se revela una ajena
        recien = (
            InsumoInvernadero.objects.select_related("insumo", "invernadero")
            .filter(pk=recien_id, invernadero__agronomo_id=request.user.pk, estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO)
            .first()
        )
    return {
        "filas": filas,
        "pestana": "existencias",
        "invernaderos": Invernadero.objects.en_alcance_de(request.user).order_by("nombre_invernadero", "id"),
        "categorias": TipoInsumo.objects.order_by("nombre_tipo_insumo", "id"),
        "f_invernadero": invernadero_id,
        "f_categoria": categoria_id,
        "f_vencimientos": con_vencimientos,
        "f_bajo_minimo": bajo_minimo,
        "hay_filtros": any((invernadero_id, categoria_id, con_vencimientos, bajo_minimo)),
        "recien": recien,
        "puede_habilitar": Invernadero.objects.en_alcance_de(request.user).exists(),
        **extra,
    }


def _ventana(request, plantilla, **contexto):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la pestaña con la ventana abierta (respaldo sin JavaScript)."""
    if request.headers.get("HX-Request") == "true":
        return render(request, plantilla, contexto)
    return render(
        request, "inventario/existencias/lista.html", _contexto_de_existencias(request, plantilla_de_ventana=plantilla, **contexto)
    )


@rol_requerido(AGRONOMO)
@require_safe
def existencias(request):
    """«Existencias de insumos» (CMP-CNS-IIN, ``existTab`` del prototipo): una fila por insumo habilitado de los invernaderos a cargo, con
    sus cantidades, su vencimiento y, desplegables, sus lotes con su estado. No audita (regla 6 y SEG-14)."""
    return render(request, "inventario/existencias/lista.html", _contexto_de_existencias(request))


def _existencia_propia(request, iin_id):
    """La existencia ``iin_id`` (404 si no existe) con su insumo e invernadero. Una de un invernadero que no es del actor es 403 (D-28):
    se verifica antes de ofrecer cualquier ventana, así un Agrónomo ajeno no recibe un aviso que revele algo."""
    iin = get_object_or_404(InsumoInvernadero.objects.select_related("insumo", "invernadero"), pk=iin_id)
    if iin.invernadero.agronomo_id != request.user.pk:
        raise PermissionDenied(api_iin.MENSAJE_AJENO)
    return iin


def _volver(request):
    return redirect("inventario:existencias")


# ---- Habilitar (CMP-HAB-IIN) ----


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def habilitar(request):
    """«Habilitar insumo en un invernadero» (CMP-HAB-IIN, ``MODALS.habilitar`` del prototipo). Con ``?insumo=`` (desde el catálogo) o
    ``?invernadero=`` el campo ya viene elegido y no se cambia. Al terminar, la pestaña ofrece «Cargar stock inicial» (el stock arranca en
    cero). La lista ofrece todos los insumos activos, **semillas incluidas** (regla 2 de CMP-HAB-IIN y regla 3 de CMP-CNS-INS); un insumo
    inactivo no se habilita. (Antes las semillas solo se podían habilitar desde «Qué sigue» de la variedad.)"""
    invernaderos = list(Invernadero.objects.en_alcance_de(request.user).order_by("nombre_invernadero", "id"))
    todos = [i for i in api_insumos.consultar_insumos(request.user) if i.activo]
    insumos = todos
    datos = request.POST if request.method == "POST" else request.GET
    # ``?insumo=`` (desde el catálogo, «Qué sigue» de la variedad o el aviso de PRD-01) deja el insumo ya elegido.
    fijo_insumo = next((i for i in todos if i.pk == _entero(datos.get("insumo"))), None) if datos.get("insumo") else None
    habilitables = insumos
    fijo_invernadero = next((g for g in invernaderos if g.pk == _entero(datos.get("invernadero"))), None) if datos.get("invernadero") else None
    if request.method == "POST":
        form = forms.FormularioExistencia(request.POST, insumos=insumos, invernaderos=invernaderos)
        form.is_valid()
        insumo = next((i for i in habilitables if i.pk == _entero(form.cleaned_data.get("insumo"))), None)
        invernadero = next((g for g in invernaderos if g.pk == _entero(form.cleaned_data.get("invernadero"))), None)
        if insumo is None:
            form.add_error("insumo", "Elegí el insumo.")
        if invernadero is None:
            form.add_error("invernadero", "Elegí el invernadero.")
        if insumo is None or invernadero is None:
            # UI-06 (UX-27, D-109 punto 9): como la vista cortó antes de llamar al servicio, este no llega a mirar el mínimo ni el precio: se suman si vinieron vacíos, con los textos del
            # servicio (`insumos_invernadero.py:64` y `:86`, regla 3 y regla 4 de CMP-HAB-IIN).
            for campo, texto in faltantes(request.POST, OBLIGATORIOS_DE_HABILITAR).items():
                form.add_error(campo, texto)
        if insumo is not None and invernadero is not None:
            try:
                iin = api_iin.habilitar_insumo(request.user, insumo.pk, invernadero.pk, **form.datos_del_servicio())
            except ValidationError as error:
                _pasar_errores(form, error)
            else:
                messages.success(request, f"{insumo.nombre_insumo} habilitado en {invernadero.nombre_invernadero}.")
                return redirect(f"{reverse('inventario:existencias')}?recien={iin.pk}")
    else:
        inicial = {"insumo": fijo_insumo.pk if fijo_insumo else "", "invernadero": fijo_invernadero.pk if fijo_invernadero else ""}
        form = forms.FormularioExistencia(initial=inicial, insumos=insumos, invernaderos=invernaderos)
    return _ventana(
        request,
        PLANTILLA_DE_HABILITAR,
        form=form,
        fijo_insumo=fijo_insumo,
        fijo_invernadero=fijo_invernadero,
        sin_invernaderos=not invernaderos,
        unidad=_unidad_elegida(form, insumos, fijo_insumo),
    )


def _unidad_elegida(form, insumos, fijo_insumo):
    """La unidad del insumo elegido (para el texto de ayuda del mínimo), o ``None`` si todavía no hay uno."""
    if fijo_insumo is not None:
        return fijo_insumo.get_unidad_medida_insumo_display()
    elegido = _entero(form["insumo"].value())
    insumo = next((i for i in insumos if i.pk == elegido), None)
    return insumo.get_unidad_medida_insumo_display() if insumo else None


# ---- Modificar mínimo y precio (CMP-MOD-IIN) ----


def _texto_editable(valor, unidad=None):
    """Un ``Decimal`` como texto para un campo: con coma decimal y sin ceros de más (cantidades) o con 2 decimales (precio)."""
    if unidad is not None:
        return alertas_de_stock._numero(valor, unidad)
    return f"{valor:.2f}".replace(".", ",")


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def existencia_modificar(request, iin_id):
    """«Mínimo y precio» (CMP-MOD-IIN, ``MODALS['ex-form']`` del prototipo). Sin cambios no se escribe ni se audita (D-28)."""
    iin = _existencia_propia(request, iin_id)
    if api_iin.ACCION_MODIFICAR not in api_iin.acciones_permitidas(request.user, iin):
        messages.error(request, "Ese insumo no se puede modificar: está deshabilitado o su invernadero no está a tu cargo.")
        return _volver(request)
    unidad = iin.insumo.unidad_medida_insumo
    if request.method == "POST":
        form = forms.FormularioExistencia(request.POST)
        form.is_valid()
        try:
            api_iin.modificar_insumo_invernadero(request.user, iin.pk, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            messages.success(request, "Se guardaron el mínimo y el precio.")
            return _volver(request)
    else:
        form = forms.FormularioExistencia(
            initial={
                "cant_min": _texto_editable(iin.cant_min_insumo, unidad),
                "referencia_precio": _texto_editable(iin.referencia_precio),
            }
        )
    return _ventana(request, PLANTILLA_DE_MINIMO, form=form, iin=iin, unidad=iin.insumo.get_unidad_medida_insumo_display())


# ---- Deshabilitar (CMP-DSH-IIN) ----


# Lo que la ventana muestra de un impedimento: el texto («qué pasa» y «cómo resolverlo») y, si lo trae, la URL de lo que lo impide (CMP-02b, H20).
ImpedimentoVisible = namedtuple("ImpedimentoVisible", "texto url")


def _visibles(impedimentos):
    """Los impedimentos de ``api_iin.impedimentos_para_deshabilitar`` como ``ImpedimentoVisible``."""
    return [ImpedimentoVisible(f"{i.texto} {i.como_resolver}", i.url) for i in impedimentos]


def _impedimentos(error, actor=None, iin=None):
    """Los impedimentos de un ``ValidationError`` general del servicio de deshabilitar (uno por impedimento, ``_error_de_impedimentos``). Con ``actor`` e ``iin`` se vuelven
    a pedir al servicio para conservar sus URL (el error solo trae los textos); si eso falla, se usan los mensajes del error."""
    if actor is not None and iin is not None:
        try:
            visibles = _visibles(api_iin.impedimentos_para_deshabilitar(actor, iin.pk))
        except ValidationError:
            visibles = []
        if visibles:
            return visibles
    if hasattr(error, "error_dict") and NON_FIELD_ERRORS in error.error_dict:
        return [ImpedimentoVisible(e.messages[0], None) for e in error.error_dict[NON_FIELD_ERRORS]]
    return [ImpedimentoVisible(texto, None) for texto in error.messages]


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def existencia_deshabilitar(request, iin_id):
    """«Deshabilitar» (CMP-DSH-IIN, ``MODALS['ex-baja']`` del prototipo), con confirmación previa. Si hay impedimentos (regla 2) la ventana los
    dice todos, cada uno con cómo resolverlo, y no ofrece confirmar. Abrirla (GET) no cambia nada; deshabilitar es un POST."""
    iin = _existencia_propia(request, iin_id)
    if api_iin.ACCION_DESHABILITAR not in api_iin.acciones_permitidas(request.user, iin):
        messages.error(request, "Ese insumo no se puede deshabilitar: ya está deshabilitado o su invernadero no está a tu cargo.")
        return _volver(request)
    impedimentos, error = [], ""
    try:
        impedimentos = _visibles(api_iin.impedimentos_para_deshabilitar(request.user, iin.pk))
    except ValidationError as rechazo:
        error = rechazo.messages[0]
    if request.method == "POST" and not impedimentos and not error:
        try:
            api_iin.deshabilitar_insumo(request.user, iin.pk)
        except ValidationError as rechazo:  # apareció un impedimento con la ventana abierta: se vuelve a mostrar
            impedimentos = _impedimentos(rechazo, request.user, iin)
        else:
            messages.success(request, f"{iin.insumo.nombre_insumo} quedó deshabilitado en {iin.invernadero.nombre_invernadero}.")
            return _volver(request)
    return _ventana(request, PLANTILLA_DE_DESHABILITAR, iin=iin, impedimentos=impedimentos, error=error)
