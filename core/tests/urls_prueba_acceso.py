# URLconf solo para pruebas del marco: SEG-13 (acceso según el rol) y los avisos breves (D-24). Todavía no
# hay pantallas de negocio restringidas por rol, así que las pruebas usan esta vista mínima protegida con
# rol_requerido, y otra que deja mensajes de éxito y de error.
# Incluye core.urls y maestros.urls para que el marco con sesión (403.html y el menú) pueda resolver sus enlaces: el
# menú del Gerente tiene la entrada «Producción» (MAE-01).

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import include, path

from core.acceso import rol_requerido
from core.models import Usuario


@rol_requerido(Usuario.Rol.GERENTE)
def vista_solo_gerente(request):
    """Vista de prueba a la que solo accede el Gerente (SEG-13)."""
    return HttpResponse("Pantalla del Gerente")


def vista_con_mensajes(request):
    """Vista de prueba que deja un mensaje de éxito y uno de error y muestra una pantalla con el marco
    (avisos breves, D-24)."""
    messages.success(request, "Todo salió bien.")
    messages.error(request, "Algo salió mal.")
    return render(request, "core/inicio.html")


urlpatterns = [
    path("prueba/solo-gerente/", vista_solo_gerente, name="prueba_solo_gerente"),
    path("prueba/mensajes/", vista_con_mensajes, name="prueba_mensajes"),
    path("", include("core.urls")),
    path("produccion/", include("maestros.urls")),
    # INV-03: las variedades cuelgan de /produccion/ (el menú y los enlaces de cultivos las resuelven).
    path("produccion/", include("inventario.urls_variedades")),
    # MAE-04: el menú del Gerente tiene también «Configuración» (maestros la registra en ready()).
    path("configuracion/", include("maestros.urls_configuracion")),
    # MAE-02c: el menú del Gerente y del Agrónomo tiene también «Alertas» (maestros la registra en ready()).
    path("alertas/", include("maestros.urls_alertas")),
    # INV-01: el menú del Agrónomo tiene también «Inventario» (inventario la registra en ready()).
    path("inventario/", include("inventario.urls")),
    # IOT-01: el menú del Gerente y del Agrónomo tiene también «IoT» (iot la registra en ready()).
    path("iot/", include("iot.urls")),
]
