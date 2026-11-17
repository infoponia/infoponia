# Rutas de core: inicio, inicio de sesión, cierre de sesión, elegir contraseña, Mi perfil y cuentas del Gerente y del
# Administrador (consultar, alta, modificar y baja) y la consulta del registro de auditoría.

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("iniciar-sesion/", views.IniciarSesionView.as_view(), name="iniciar_sesion"),
    path("cerrar-sesion/", views.cerrar_sesion, name="cerrar_sesion"),
    path("elegir-contrasena/", views.elegir_contrasena, name="elegir_contrasena"),
    # Recuperar contraseña por correo (USR-RCP-CTR y SEG-12; tarea 08). La de ``elegir`` va antes de la del token:
    # «elegir» también encajaría como token.
    path("recuperar-contrasena/", views.recuperar_contrasena, name="recuperar_contrasena"),
    path("recuperar-contrasena/enviado/", views.recuperacion_enviada, name="recuperacion_enviada"),
    path("recuperar-contrasena/<str:uidb64>/elegir/", views.recuperacion_elegir, name="recuperacion_elegir"),
    path("recuperar-contrasena/<str:uidb64>/<str:token>/", views.recuperacion_enlace, name="recuperacion_enlace"),
    # Aceptar la invitación por correo (SEG-20; tarea 08b, D-35). Como en la recuperación, la de ``elegir`` va antes
    # de la del token.
    path("invitacion/<str:uidb64>/elegir/", views.invitacion_elegir, name="invitacion_elegir"),
    path("invitacion/<str:uidb64>/<str:token>/", views.invitacion_enlace, name="invitacion_enlace"),
    # Mi perfil y cambio voluntario de contraseña (USR-GST-PRF y USR-CMB-CTR; tarea 06a).
    path("mi-perfil/", views.mi_perfil, name="mi_perfil"),
    path("mi-perfil/contrasena/", views.cambiar_mi_contrasena, name="cambiar_mi_contrasena"),
    # Cuentas vinculadas (USR-VNC-CTA y SEG-09; tarea 06b).
    path("mi-perfil/vincular/", views.vincular, name="vincular_cuenta"),
    path("mi-perfil/desvincular/<int:cuenta_id>/", views.desvincular, name="desvincular_cuenta"),
    path("cambiar-de-cuenta/", views.cambiar_de_cuenta, name="cambiar_de_cuenta"),
    # Usuarios del Gerente (USR-CNS-USR y USR-ALT-USR; tarea 04a).
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:cuenta_id>/", views.usuario_ficha, name="usuario"),
    # Modificar, restablecer, reactivar y dar de baja (USR-MOD-USR y USR-BAJ-USR; tarea 04b).
    path("usuarios/<int:cuenta_id>/modificar/", views.usuario_modificar, name="usuario_modificar"),
    path("usuarios/<int:cuenta_id>/restablecer/", views.usuario_restablecer, name="usuario_restablecer"),
    path("usuarios/<int:cuenta_id>/reactivar/", views.usuario_reactivar, name="usuario_reactivar"),
    path("usuarios/<int:cuenta_id>/baja/", views.usuario_baja, name="usuario_baja"),
    # Consultar el registro de auditoría (AUD-CNS-REG; D-36): solo lectura.
    path("auditoria/", views.auditoria, name="auditoria"),
    path("auditoria/<int:registro_id>/", views.auditoria_registro, name="auditoria_registro"),
]
