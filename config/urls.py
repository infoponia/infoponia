# Rutas del proyecto: el admin de Django y las pantallas de core (inicio y sesión).

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
