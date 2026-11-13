# Rutas de core: inicio, inicio de sesión, cierre de sesión, elegir contraseña, Mi perfil y cuentas del Gerente y del
# Administrador (consultar, alta, modificar y baja).

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("iniciar-sesion/", views.IniciarSesionView.as_view(), name="iniciar_sesion"),
    path("cerrar-sesion/", views.cerrar_sesion, name="cerrar_sesion"),
    path("elegir-contrasena/", views.elegir_contrasena, name="elegir_contrasena"),
    # Mi perfil y cambio voluntario de contraseña (USR-GST-PRF y USR-CMB-CTR; tarea 06a).
    path("mi-perfil/", views.mi_perfil, name="mi_perfil"),
    path("mi-perfil/contrasena/", views.cambiar_mi_contrasena, name="cambiar_mi_contrasena"),
    # Usuarios del Gerente (USR-CNS-USR y USR-ALT-USR; tarea 04a).
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:cuenta_id>/", views.usuario_ficha, name="usuario"),
    # Modificar, restablecer, reactivar y dar de baja (USR-MOD-USR y USR-BAJ-USR; tarea 04b).
    path("usuarios/<int:cuenta_id>/modificar/", views.usuario_modificar, name="usuario_modificar"),
    path("usuarios/<int:cuenta_id>/restablecer/", views.usuario_restablecer, name="usuario_restablecer"),
    path("usuarios/<int:cuenta_id>/reactivar/", views.usuario_reactivar, name="usuario_reactivar"),
    path("usuarios/<int:cuenta_id>/baja/", views.usuario_baja, name="usuario_baja"),
]
