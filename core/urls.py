# Rutas de core: inicio, inicio de sesión, cierre de sesión, elegir contraseña y usuarios del Gerente.

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("iniciar-sesion/", views.IniciarSesionView.as_view(), name="iniciar_sesion"),
    path("cerrar-sesion/", views.cerrar_sesion, name="cerrar_sesion"),
    path("elegir-contrasena/", views.elegir_contrasena, name="elegir_contrasena"),
    # Usuarios del Gerente (USR-CNS-USR y USR-ALT-USR; tarea 04a).
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:cuenta_id>/", views.usuario_ficha, name="usuario"),
]
