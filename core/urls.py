# Rutas de core: inicio, inicio de sesión y cierre de sesión.

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("iniciar-sesion/", views.IniciarSesionView.as_view(), name="iniciar_sesion"),
    path("cerrar-sesion/", views.cerrar_sesion, name="cerrar_sesion"),
]
