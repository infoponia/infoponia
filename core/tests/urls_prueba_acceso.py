# URLconf solo para pruebas del marco: SEG-13 (acceso según el rol) y los avisos breves (D-24). Todavía no
# hay pantallas de negocio restringidas por rol, así que las pruebas usan esta vista mínima protegida con
# rol_requerido, y otra que deja mensajes de éxito y de error.
# Incluye core.urls para que el marco con sesión (403.html) pueda resolver sus enlaces.

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
]
