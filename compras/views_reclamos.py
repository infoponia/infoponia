# Pantallas de «Compras» → «Reclamos» (CMP-06; prototipo: ``tabRcl`` y ``VIEWS.c_rcl``). Las vistas solo orquestan: llaman al servicio (``compras/servicios/reclamos.py``) y renderizan; las reglas son
# de los servicios. El Gerente ve la lista, la ficha y puede emitir y cerrar; el Agrónomo ve los reclamos de sus invernaderos en solo lectura (se llega desde la ficha de la orden). Ningún botón lleva a un 403
# (D-30): las acciones de la ficha vienen de ``ficha.acciones``. Emitir y cerrar son botones de un formulario que se envía por POST desde la ficha, con la explicación de lo que hace cada uno al lado
# (el prototipo usaba ventanas; acá funciona sin JavaScript).

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from compras.errores import ErrorDeCompras
from compras.servicios import reclamos as api
from core.acceso import rol_requerido
from core.correo import correo_configurado
from core.models import Usuario

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def reclamos(request):
    """«Compras» → «Reclamos» (``tabRcl``): los reclamos con su proveedor, la orden y los tipos de inconveniente, del más reciente al más antiguo, con los filtros «Sin emitir», «Emitidos abiertos» y
    «Cerrados». No audita."""
    estado = request.GET.get("estado", "")
    return render(
        request,
        "compras/reclamos/lista.html",
        {
            "filas": api.reclamos(request.user, {"estado": estado}),
            "estado": estado if estado in api.FILTROS_DE_ESTADO else "",
            "sin_emitir": len(api.reclamos(request.user, {"estado": "sin_emitir"})),
        },
    )


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def reclamo_ficha(request, reclamo_id):
    """Ficha del reclamo (CMP-EMT-RCL regla 2, ``VIEWS.c_rcl``): la recepción, la orden, el proveedor, el invernadero y cada inconveniente, con «Emitir reclamo» o «Cerrar reclamo» según el estado y el rol."""
    return render(request, "compras/reclamos/ficha.html", {"ficha": api.ficha_de_reclamo(request.user, reclamo_id), "correo_configurado": correo_configurado()})


@rol_requerido(GERENTE)
@require_POST
@never_cache
def reclamo_emitir(request, reclamo_id):
    """Emite el reclamo (CMP-EMT-RCL) y vuelve a su ficha. Un reclamo que ya estaba emitido (otra sesión) muestra su estado actual con el aviso."""
    try:
        reclamo = api.emitir_reclamo(request.user, reclamo_id)
    except ErrorDeCompras as error:
        messages.info(request, error.mensaje)
        return redirect("compras:reclamo_ficha", reclamo_id=reclamo_id)
    messages.success(
        request,
        f"Emitimos el reclamo {reclamo}."
        + (f" Le enviamos un correo a {reclamo.proveedor.nombre_para_mostrar}." if correo_configurado() else " El correo no está configurado: no se le envió ningún aviso al proveedor."),
    )
    return redirect("compras:reclamo_ficha", reclamo_id=reclamo.pk)


@rol_requerido(GERENTE)
@require_POST
@never_cache
def reclamo_cerrar(request, reclamo_id):
    """Cierra el reclamo (CMP-CRR-RCL) y vuelve a su ficha. Un reclamo cerrado no se reabre; uno sin emitir no se cierra (el aviso lo explica)."""
    try:
        reclamo = api.cerrar_reclamo(request.user, reclamo_id)
    except ErrorDeCompras as error:
        messages.info(request, error.mensaje)
        return redirect("compras:reclamo_ficha", reclamo_id=reclamo_id)
    messages.success(request, f"Cerramos el reclamo {reclamo}.")
    return redirect("compras:reclamo_ficha", reclamo_id=reclamo.pk)
