# Pantallas del Vendedor de COM-DCD-FLT (extensión 1a; docs/casos_de_uso/comercial/faltante.md, «Pantallas»): «Faltantes para decidir» (1a.1 y 1a.2, con 1a.2a si no hay) y «Registrar
# decisión de faltante» de una venta, que es la misma pantalla del cliente (`views_cliente.manejar`) dentro del diseño de la aplicación. Solo el Vendedor del contrato (el Gerente ve la
# ficha de la venta, pero no el botón). Las vistas solo orquestan; sin JavaScript todo funciona.

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.models import CompraVenta
from comercial.servicios import faltantes
from comercial.views_cliente import manejar
from core.acceso import rol_requerido
from core.models import Usuario

VENDEDOR = Usuario.Rol.VENDEDOR


@rol_requerido(VENDEDOR)
@require_safe
def lista(request):
    """«Faltantes para decidir» (1a.1 y 1a.2): las ventas de sus contratos que esperan una decisión que él puede registrar. Vacía: el texto de 1a.2a."""
    return render(request, "comercial/faltantes/lista.html", {"filas": faltantes.ventas_para_decidir(request.user)})


@rol_requerido(VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "POST"])
def decidir(request, venta_id):
    """«Registrar decisión de faltante» (1a): el formulario, el resumen y el registro en nombre del cliente. Otro Vendedor: 403 (SEG-13); una venta que ya no espera su decisión
    (el cliente puede decidir, o ya decidió): aviso y vuelve a la ficha."""
    venta = get_object_or_404(CompraVenta, pk=venta_id)
    ficha = reverse("comercial:compra_venta", args=[venta.pk])
    try:
        respuesta, hecho = manejar(
            request,
            plantilla="comercial/faltantes/decidir.html",
            url=reverse("comercial:faltante_decidir", args=[venta.pk]),
            vendedor=request.user,
            venta_id=venta.pk,
        )
    except ValidationError as error:
        messages.error(request, error.error_dict["__all__"][0].messages[0])
        return redirect(ficha)
    if respuesta is not None:
        return respuesta
    messages.success(request, f"Registraste la decisión del cliente sobre el faltante de {venta.codigo}.")
    return redirect(ficha)
