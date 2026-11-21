# Rutas del proyecto: las pantallas de core y, solo en desarrollo, el admin de Django (SEG-18, D-30).

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    # MAE-01: invernaderos (Producción).
    path("produccion/", include("maestros.urls")),
    # MAE-04: configuración operativa y perfil de la organización (Gerente).
    path("configuracion/", include("maestros.urls_configuracion")),
]

# SEG-18: con ``ADMIN_DJANGO_HABILITADO`` apagado (producción) no se registra ninguna ruta de /admin/, así que
# responde 404 incluso a un Administrador con sesión abierta.
if settings.ADMIN_DJANGO_HABILITADO:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
