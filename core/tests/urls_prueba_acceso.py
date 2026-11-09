# URLconf solo para pruebas de SEG-13 (acceso según el rol). Todavía no hay pantallas de negocio
# restringidas por rol, así que las pruebas usan esta vista mínima protegida con rol_requerido.
# Incluye core.urls para que el marco con sesión (403.html) pueda resolver sus enlaces.

from django.http import HttpResponse
from django.urls import include, path

from core.acceso import rol_requerido
from core.models import Usuario


@rol_requerido(Usuario.Rol.GERENTE)
def vista_solo_gerente(request):
    """Vista de prueba a la que solo accede el Gerente (SEG-13)."""
    return HttpResponse("Pantalla del Gerente")


urlpatterns = [
    path("prueba/solo-gerente/", vista_solo_gerente, name="prueba_solo_gerente"),
    path("", include("core.urls")),
]
