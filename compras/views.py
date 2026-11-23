# Pantallas de «Compras» → «Proveedores» (CMP-01; prototipo: ``tabPrv``, ``VIEWS.c_prv`` y ``VIEWS.c_prvform``). Las vistas solo orquestan: validan la
# entrada, llaman al servicio y renderizan. Gerente y Agrónomo consultan (lista y ficha); solo el Gerente da de alta, modifica, da de baja y reactiva:
# los demás roles reciben 403 (SEG-13). La ventana de la baja tiene las dos formas de las de maestros: fragmento con HTMX y, sin JavaScript, la
# ficha con la ventana abierta. Ningún botón lleva a un 403 (D-30): lo que el actor no puede hacer no se muestra.

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_headers

from compras.errores import ErrorDeCompras
from compras.forms import FormularioProveedor
from compras.servicios import proveedores as api
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.models import TipoInsumo

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO

PLANTILLA_DE_BAJA = "compras/proveedores/_ventana_baja.html"


def _pasar_errores(form, error):
    """Pasa los errores de un ``ValidationError`` del servicio al formulario: por campo si el campo existe y, si no, generales."""
    for campo, errores in error.error_dict.items():
        for e in errores:
            form.add_error(campo if campo in form.fields else None, e)


def _contexto_del_formulario(form, proveedor, modo, **extra):
    """Lo que necesita el formulario: ``modo`` es «alta», «modificar» o «reactivar»."""
    return {
        "form": form,
        "proveedor": proveedor,
        "modo": modo,
        "categorias": form.opciones_de_categorias(),
        "cuit_fijo": modo == "reactivar" or (proveedor is not None and api.tiene_pedidos_u_ordenes(proveedor)),
        **extra,
    }


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def proveedores(request):
    """«Compras» → «Proveedores» (CMP-CNS-PRV, ``tabPrv`` del prototipo): la lista con sus filtros (estado, texto y tipo de insumo). Por defecto, los
    activos. No audita (regla 6)."""
    estado = request.GET.get("estado", "activo")
    texto = request.GET.get("q", "").strip()
    categoria = request.GET.get("categoria", "")
    categoria = int(categoria) if categoria.isdigit() else ""
    lista = api.listar_proveedores(request.user, {"estado": estado, "texto": texto, "tipo_de_insumo": categoria})
    return render(
        request,
        "compras/proveedores/lista.html",
        {
            "filas": [{"proveedor": p, "acciones": api.acciones_permitidas(request.user, p)} for p in lista],
            "puede_gestionar": request.user.rol == GERENTE,
            "categorias": TipoInsumo.objects.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO).order_by("nombre_tipo_insumo"),
            "filtros": {"estado": estado, "q": texto, "categoria": categoria},
            "hay_filtros": bool(texto or categoria or estado != "activo"),
        },
    )


def _contexto_de_la_ficha(request, proveedor_id, **extra):
    """El proveedor con sus categorías activas y los botones que le corresponden a quien mira (D-30)."""
    proveedor = api.ficha_de_proveedor(request.user, proveedor_id)
    return {
        "proveedor": proveedor,
        "acciones": api.acciones_permitidas(request.user, proveedor),
        # CMP-02a, regla 4 de CMP-CNS-PRV: sus pedidos, según el alcance de quien mira (las órdenes, pagos y reclamos se suman de CMP-03 a CMP-06).
        "pedidos": api.pedidos_del_proveedor(request.user, proveedor),
        **extra,
    }


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def proveedor_ficha(request, proveedor_id):
    """Ficha del proveedor (CMP-CNS-PRV regla 4, ``VIEWS.c_prv`` del prototipo). Sus pedidos, órdenes, pagos y reclamos se suman de CMP-02a a CMP-06."""
    return render(request, "compras/proveedores/ficha.html", _contexto_de_la_ficha(request, proveedor_id))


@rol_requerido(GERENTE)
@never_cache
def proveedor_nuevo(request):
    """Nuevo proveedor (CMP-ALT-PRV, ``VIEWS.c_prvform`` del prototipo). Si el CUIT es el de un proveedor dado de baja, el formulario ofrece
    reactivarlo con los datos escritos (postcondición c): el botón envía ``reactivar_id``."""
    inactivo = None
    if request.method == "POST":
        form = FormularioProveedor(request.POST)
        form.is_valid()
        reactivar_id = request.POST.get("reactivar_id", "")
        try:
            if reactivar_id.isdigit():
                proveedor = api.reactivar_proveedor(request.user, int(reactivar_id), form.datos_del_servicio())
                messages.success(request, f"{proveedor} está activo otra vez.")
            else:
                proveedor = api.alta_proveedor(request.user, form.datos_del_servicio())
                messages.success(request, f"Registramos a {proveedor}.")
        except ValidationError as error:
            _pasar_errores(form, error)
        except ErrorDeCompras as error:
            if error.codigo == "cuit_de_inactivo":
                inactivo = api.ficha_de_proveedor(request.user, error.datos["proveedor_id"])
                form.add_error("cuit", error.mensaje)
            else:
                messages.error(request, error.mensaje)
                return redirect("compras:proveedores")
        else:
            return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
    else:
        form = FormularioProveedor()
    return render(request, "compras/proveedores/formulario.html", _contexto_del_formulario(form, None, "alta", inactivo=inactivo))


@rol_requerido(GERENTE)
@never_cache
def proveedor_editar(request, proveedor_id):
    """Modificar un proveedor activo (CMP-MOD-PRV). El tipo no se cambia y el CUIT solo si no tiene pedidos ni órdenes. Uno inactivo no se
    modifica: se reactiva."""
    proveedor = api.ficha_de_proveedor(request.user, proveedor_id)
    if api.ACCION_MODIFICAR not in api.acciones_permitidas(request.user, proveedor):
        messages.error(request, "El proveedor está dado de baja: solo se puede reactivar.")
        return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
    if request.method == "POST":
        form = FormularioProveedor(request.POST, proveedor=proveedor)
        form.is_valid()
        datos = form.datos_del_servicio()
        if api.tiene_pedidos_u_ordenes(proveedor):  # el CUIT no se envía (campo de solo lectura): se mantiene
            datos["cuit"] = proveedor.cuit_proveedor
        try:
            api.modificar_proveedor(request.user, proveedor.pk, datos)
        except ValidationError as error:
            _pasar_errores(form, error)
        except ErrorDeCompras as error:
            messages.error(request, error.mensaje)
            return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
        else:
            messages.success(request, "Guardamos los cambios.")
            return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
    else:
        form = FormularioProveedor(proveedor=proveedor)
    return render(request, "compras/proveedores/formulario.html", _contexto_del_formulario(form, proveedor, "modificar"))


@rol_requerido(GERENTE)
@never_cache
def proveedor_reactivar(request, proveedor_id):
    """Reactivar un proveedor dado de baja (CMP-ALT-PRV postcondición c), con un formulario con sus datos para corregirlos. El CUIT y el tipo no cambian."""
    proveedor = api.ficha_de_proveedor(request.user, proveedor_id)
    if api.ACCION_REACTIVAR not in api.acciones_permitidas(request.user, proveedor):
        messages.error(request, "El proveedor no está dado de baja.")
        return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
    if request.method == "POST":
        form = FormularioProveedor(request.POST, proveedor=proveedor)
        form.is_valid()
        try:
            api.reactivar_proveedor(request.user, proveedor.pk, form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        except ErrorDeCompras as error:
            messages.error(request, error.mensaje)
            return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
        else:
            messages.success(request, f"{proveedor} está activo otra vez.")
            return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
    else:
        form = FormularioProveedor(proveedor=proveedor)
    return render(request, "compras/proveedores/formulario.html", _contexto_del_formulario(form, proveedor, "reactivar"))


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def proveedor_baja(request, proveedor_id):
    """Dar de baja un proveedor (CMP-BAJ-PRV), con confirmación previa. Si algo lo impide (órdenes sin terminar o pagos pendientes: CMP-03 y
    CMP-05), la ventana dice qué y cómo resolverlo y no ofrece confirmar. Abrirla (GET) no cambia nada; la baja es un POST."""
    proveedor = api.ficha_de_proveedor(request.user, proveedor_id)
    if api.ACCION_BAJA not in api.acciones_permitidas(request.user, proveedor):
        messages.error(request, "El proveedor ya está dado de baja.")
        return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
    impedimentos = api.impedimentos_de_baja(proveedor)
    if request.method == "POST" and not impedimentos:
        try:
            api.baja_proveedor(request.user, proveedor.pk)
        except ErrorDeCompras as error:
            if error.codigo != "baja_con_impedimentos":
                messages.error(request, error.mensaje)
                return redirect("compras:proveedor_ficha", proveedor_id=proveedor.pk)
            impedimentos = error.datos["impedimentos"]
        else:
            messages.success(request, f"{proveedor} quedó inactivo.")
            return redirect("compras:proveedores")
    contexto = {"proveedor": proveedor, "impedimentos": impedimentos}
    if request.headers.get("HX-Request") == "true":
        return render(request, PLANTILLA_DE_BAJA, contexto)
    return render(
        request, "compras/proveedores/ficha.html", _contexto_de_la_ficha(request, proveedor.pk, plantilla_de_ventana=PLANTILLA_DE_BAJA, **contexto)
    )
