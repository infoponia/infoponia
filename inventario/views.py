# Vistas de inventario para INV-01: el catálogo de insumos (CMP-CNS-INS, CMP-ALT-INS, CMP-MOD-INS, CMP-BAJ-INS) y las categorías
# (CMP-CNS-TIN, CMP-ALT-TIN, CMP-MOD-TIN, CMP-BAJ-TIN). Las vistas solo orquestan: validan la entrada, llaman al servicio y renderizan
# (CLAUDE.md, arquitectura). Solo el Agrónomo: otros roles reciben 403 y sin sesión, el inicio de sesión (D-25, SEG-13). Las vistas de
# lectura no se auditan (SEG-14).
#
# Ventanas (D-47, patrón ABM §7): cada una es una vista con dos formas. Con HTMX (``HX-Request``) devuelve solo la ventana, que se
# inserta sobre la página; sin JavaScript devuelve la página completa con la ventana abierta (``plantilla_de_ventana``). Los
# formularios envían con un POST común: si sale bien, redirigen con un aviso breve (D-29); si no, vuelven a mostrar la ventana con los
# errores por campo. Ningún botón lleva a un 403 (D-30): lo que la cuenta no puede hacer no se ofrece, o se muestra deshabilitado con
# el motivo (regla 3 de CMP-CNS-INS).

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from inventario import forms
from inventario.servicios import insumos as api_insumos
from inventario.servicios import tipos_de_insumo as api_tipos

AGRONOMO = Usuario.Rol.AGRONOMO

PLANTILLA_DE_CATEGORIA = "inventario/categorias/_ventana_formulario.html"
PLANTILLA_BAJA_DE_CATEGORIA = "inventario/categorias/_ventana_baja.html"
PLANTILLA_DE_INSUMO = "inventario/catalogo/_ventana_formulario.html"
PLANTILLA_BAJA_DE_INSUMO = "inventario/catalogo/_ventana_baja.html"


def _pasar_errores(form, error):
    """Pasa los errores de un ``ValidationError`` del servicio al formulario: por campo si el campo existe y, si no, generales."""
    for campo, errores in error.error_dict.items():
        for e in errores:
            form.add_error(campo if campo in form.fields else None, e)


def _mensaje_general(error):
    """El primer mensaje de un ``ValidationError`` del servicio (sea de campo o general)."""
    return error.messages[0]


# ---- Catálogo de insumos ----


def _contexto_del_catalogo(request, **extra):
    """Lo que necesita el catálogo: cada insumo con sus botones (``acciones_permitidas``), si el actor puede gestionarlo y, si no, quién
    lo usa (regla 3 de CMP-CNS-INS)."""
    filas = []
    for insumo in api_insumos.consultar_insumos(request.user):
        acciones = api_insumos.acciones_permitidas(request.user, insumo)
        puede = api_insumos.puede_gestionar(request.user, insumo, insumo.habilitado_en)
        filas.append(
            {
                "insumo": insumo,
                "acciones": acciones,
                "puede": puede,
                "quienes": [] if puede or not acciones else api_insumos.quienes_lo_usan(insumo.pk),
            }
        )
    return {"filas": filas, "pestana": "catalogo", **extra}


def _ventana_de_insumo(request, plantilla, **contexto):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, el catálogo con la ventana abierta (respaldo sin JavaScript)."""
    if request.headers.get("HX-Request") == "true":
        return render(request, plantilla, contexto)
    return render(
        request, "inventario/catalogo/lista.html", _contexto_del_catalogo(request, plantilla_de_ventana=plantilla, **contexto)
    )


@rol_requerido(AGRONOMO)
@require_safe
def catalogo(request):
    """Catálogo de insumos (CMP-CNS-INS, ``catalogoTab`` del prototipo): activos primero, con su categoría, unidad, vencimiento, dónde
    está habilitado y sus botones. Las semillas indican que vienen de su variedad. No audita."""
    return render(request, "inventario/catalogo/lista.html", _contexto_del_catalogo(request))


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def insumo_nuevo(request):
    """Nuevo insumo (CMP-ALT-INS, ``MODALS['insumo-form']`` del prototipo). Cualquier Agrónomo activo. Habilitarlo en un invernadero
    (regla 7) lo agrega INV-02: por ahora el aviso dice que falta habilitarlo."""
    categorias = forms.categorias_para_el_alta()
    if request.method == "POST":
        form = forms.FormularioInsumo(request.POST, categorias=categorias)
        form.is_valid()
        try:
            nuevo = api_insumos.alta_insumo(request.user, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            messages.success(request, f"Insumo creado: {nuevo.nombre_insumo}. Habilitalo en un invernadero para cargarle stock.")
            return redirect("inventario:catalogo")
    else:
        form = forms.FormularioInsumo(categorias=categorias)
    return _ventana_de_insumo(request, PLANTILLA_DE_INSUMO, form=form, insumo=None, a_avisar=[], bloqueos={})


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def insumo_modificar(request, insumo_id):
    """Modificar un insumo (CMP-MOD-INS, ``MODALS['insumo-form']`` del prototipo). Antes de confirmar informa a quiénes se avisará
    (regla 5) y muestra bloqueados, con su motivo, los campos que hoy no se pueden cambiar (regla 3). Uno que no puede gestionar, una
    semilla o uno inactivo no se modifican: vuelve al catálogo con el motivo (D-30)."""
    insumo = api_insumos.obtener_insumo(request.user, insumo_id)
    if api_insumos.ACCION_MODIFICAR not in api_insumos.acciones_permitidas(request.user, insumo):
        messages.error(request, "Ese insumo no se puede modificar: está inactivo o viene de una variedad.")
        return redirect("inventario:catalogo")
    if not api_insumos.puede_gestionar(request.user, insumo, insumo.habilitado_en):
        messages.error(request, f"Lo usan {', '.join(api_insumos.quienes_lo_usan(insumo.pk))}. Solo lo gestiona el Agrónomo de alguno de esos invernaderos.")
        return redirect("inventario:catalogo")
    bloqueos = api_insumos.bloqueos_de_modificacion(insumo)
    categorias = forms.categorias_para_modificar(insumo)
    a_avisar = api_insumos.a_quienes_avisara(request.user, insumo.pk)
    if request.method == "POST":
        form = forms.FormularioInsumo(request.POST, insumo=insumo, bloqueos=bloqueos, categorias=categorias)
        form.is_valid()
        try:
            api_insumos.modificar_insumo(request.user, insumo.pk, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            avisados = f" Se notificó a {', '.join(i.nombre_invernadero for i in a_avisar)}." if a_avisar else ""
            messages.success(request, f"Se guardó el insumo.{avisados}")
            return redirect("inventario:catalogo")
    else:
        form = forms.FormularioInsumo(insumo=insumo, bloqueos=bloqueos, categorias=categorias)
    return _ventana_de_insumo(request, PLANTILLA_DE_INSUMO, form=form, insumo=insumo, a_avisar=a_avisar, bloqueos=bloqueos)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def insumo_baja(request, insumo_id):
    """Dar de baja un insumo (CMP-BAJ-INS, ``MODALS['ins-baja']`` del prototipo), con confirmación previa. Si hay impedimentos
    (regla 2) la ventana los dice todos, por invernadero y con cómo resolverlos, y no ofrece confirmar. Abrirla (GET) no cambia nada;
    la baja es un POST. Si el servicio rechaza la baja porque apareció un impedimento con la ventana abierta, vuelve a mostrarse."""
    insumo = api_insumos.obtener_insumo(request.user, insumo_id)
    if api_insumos.ACCION_BAJA not in api_insumos.acciones_permitidas(request.user, insumo):
        messages.error(request, "Ese insumo no se puede dar de baja: ya está inactivo o viene de una variedad.")
        return redirect("inventario:catalogo")
    if not api_insumos.puede_gestionar(request.user, insumo, insumo.habilitado_en):
        messages.error(request, f"Lo usan {', '.join(api_insumos.quienes_lo_usan(insumo.pk))}. Solo lo gestiona el Agrónomo de alguno de esos invernaderos.")
        return redirect("inventario:catalogo")
    contexto = {
        "insumo": insumo,
        "habilitado_en": insumo.habilitado_en,
        "impedimentos": api_insumos.impedimentos_de_baja(request.user, insumo.pk),
        "error": "",
    }
    if request.method == "POST":
        try:
            api_insumos.baja_insumo(request.user, insumo.pk)
        except ValidationError as rechazo:
            try:
                contexto["impedimentos"] = api_insumos.impedimentos_de_baja(request.user, insumo.pk)
            except ValidationError:
                contexto["impedimentos"] = []  # ya no se puede dar de baja por otro motivo
            if not contexto["impedimentos"]:
                contexto["error"] = _mensaje_general(rechazo)
        else:
            messages.success(request, f"{insumo.nombre_insumo} quedó inactivo.")
            return redirect("inventario:catalogo")
    return _ventana_de_insumo(request, PLANTILLA_BAJA_DE_INSUMO, **contexto)


@rol_requerido(AGRONOMO)
@require_POST
def insumo_reactivar(request, insumo_id):
    """Reactivar un insumo dado de baja (CMP-MOD-INS, postcondición c; ``ACT['ins-react']`` del prototipo), sin ventana. No lo
    vuelve a habilitar en ningún invernadero. Si su categoría está inactiva, el servicio lo rechaza y se muestra el motivo."""
    insumo = api_insumos.obtener_insumo(request.user, insumo_id)
    try:
        api_insumos.reactivar_insumo(request.user, insumo.pk)
    except ValidationError as error:
        messages.error(request, _mensaje_general(error))
    else:
        messages.success(request, "Insumo reactivado. Para usarlo, habilitalo de nuevo en cada invernadero.")
    return redirect("inventario:catalogo")


# ---- Categorías (tipos de insumo) ----


def _contexto_de_categorias(request, **extra):
    """Lo que necesita la pestaña «Categorías»: cada categoría con sus botones (``acciones_permitidas``)."""
    filas = [
        {"tipo": tipo, "acciones": api_tipos.acciones_permitidas(request.user, tipo)}
        for tipo in api_tipos.consultar_tipos_de_insumo(request.user)
    ]
    return {"filas": filas, "pestana": "categorias", **extra}


def _ventana_de_categoria(request, plantilla, **contexto):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la pestaña con la ventana abierta (respaldo sin JavaScript)."""
    if request.headers.get("HX-Request") == "true":
        return render(request, plantilla, contexto)
    return render(
        request,
        "inventario/categorias/lista.html",
        _contexto_de_categorias(request, plantilla_de_ventana=plantilla, **contexto),
    )


@rol_requerido(AGRONOMO)
@require_safe
def categorias(request):
    """Categorías de insumo (CMP-CNS-TIN, ``tiposTab`` del prototipo): activas primero, con su consumo directo, su cantidad de insumos
    y sus botones. Las del sistema llevan el candado y no tienen acciones. No audita."""
    return render(request, "inventario/categorias/lista.html", _contexto_de_categorias(request))


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def categoria_nueva(request):
    """Nueva categoría (CMP-ALT-TIN, ``MODALS['cat-form']`` del prototipo). Cualquier Agrónomo activo."""
    if request.method == "POST":
        form = forms.FormularioCategoria(request.POST)
        form.is_valid()
        try:
            nueva = api_tipos.alta_tipo_insumo(request.user, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            messages.success(request, f"Categoría creada: {nueva.nombre_tipo_insumo}.")
            return redirect("inventario:categorias")
    else:
        form = forms.FormularioCategoria()
    return _ventana_de_categoria(request, PLANTILLA_DE_CATEGORIA, form=form, tipo=None)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def categoria_modificar(request, tipo_id):
    """Modificar una categoría (CMP-MOD-TIN, ``MODALS['cat-form']`` del prototipo). Una del sistema o inactiva no se modifica:
    vuelve a la pestaña con el motivo (D-30)."""
    tipo = api_tipos.obtener_tipo_de_insumo(request.user, tipo_id)
    if api_tipos.ACCION_MODIFICAR not in api_tipos.acciones_permitidas(request.user, tipo):
        messages.error(
            request,
            "Es una categoría del sistema: no se modifica."
            if tipo.es_del_sistema
            else "La categoría está inactiva: solo se puede reactivar.",
        )
        return redirect("inventario:categorias")
    if request.method == "POST":
        form = forms.FormularioCategoria(request.POST, tipo=tipo)
        form.is_valid()
        try:
            api_tipos.modificar_tipo_insumo(request.user, tipo.pk, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            messages.success(request, "Se guardó la categoría.")
            return redirect("inventario:categorias")
    else:
        form = forms.FormularioCategoria(tipo=tipo)
    return _ventana_de_categoria(request, PLANTILLA_DE_CATEGORIA, form=form, tipo=tipo)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def categoria_baja(request, tipo_id):
    """Dar de baja una categoría (CMP-BAJ-TIN, ``ACT['cat-baja']`` del prototipo), con confirmación previa. Con insumos activos
    el servicio la rechaza y la ventana vuelve a mostrarse con cuántos son. Abrirla (GET) no cambia nada; la baja es un POST."""
    tipo = api_tipos.obtener_tipo_de_insumo(request.user, tipo_id)
    if api_tipos.ACCION_BAJA not in api_tipos.acciones_permitidas(request.user, tipo):
        messages.error(request, "Esa categoría no se puede dar de baja: es del sistema o ya está inactiva.")
        return redirect("inventario:categorias")
    error = ""
    if request.method == "POST":
        try:
            api_tipos.baja_tipo_insumo(request.user, tipo.pk)
        except ValidationError as rechazo:
            error = _mensaje_general(rechazo)
        else:
            messages.success(request, "Categoría dada de baja.")
            return redirect("inventario:categorias")
    return _ventana_de_categoria(request, PLANTILLA_BAJA_DE_CATEGORIA, tipo=tipo, error=error)


@rol_requerido(AGRONOMO)
@require_POST
def categoria_reactivar(request, tipo_id):
    """Reactivar una categoría dada de baja (CMP-MOD-TIN, ``ACT['cat-baja']`` del prototipo), sin ventana. No reactiva sus insumos."""
    tipo = api_tipos.obtener_tipo_de_insumo(request.user, tipo_id)
    try:
        api_tipos.reactivar_tipo_insumo(request.user, tipo.pk)
    except ValidationError as error:
        messages.error(request, _mensaje_general(error))
    else:
        messages.success(request, "Categoría reactivada.")
    return redirect("inventario:categorias")
