# Rutas de la app `iot` bajo /iot/ (IOT-01 e IOT-02): el inicio del módulo, el sistema IoT, el hardware y los tipos de actuador. Cada tarea siguiente suma las
# suyas (monitoreo, comandos y reglas). Las de texto fijo van antes que las que llevan id.

from django.urls import path

from iot import views, views_hardware, views_sistema

app_name = "iot"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    # IOT-02: Sistema IoT (IOT-REG-SIS, IOT-MOD-SIS)
    path("sistema/", views_sistema.sistema, name="sistema"),
    path("sistema/registrar/", views_sistema.sistema_registrar, name="sistema_registrar"),
    path("sistema/<int:sistema_id>/modificar/", views_sistema.sistema_modificar, name="sistema_modificar"),
    path("sistema/<int:sistema_id>/regenerar-token/", views_sistema.sistema_regenerar_token, name="sistema_regenerar_token"),
    # IOT-02: Hardware (IOT-ALT-HDW, IOT-MOD-HDW, IOT-CNS-HDW)
    path("hardware/", views_hardware.hardware, name="hardware"),
    path("hardware/nuevo/", views_hardware.hardware_nuevo, name="hardware_nuevo"),
    path("hardware/avisos/", views_hardware.hardware_avisos, name="hardware_avisos"),
    path("hardware/<int:equipo_id>/", views_hardware.hardware_ficha, name="hardware_ficha"),
    path("hardware/<int:equipo_id>/modificar/", views_hardware.hardware_modificar, name="hardware_modificar"),
    path("hardware/<int:equipo_id>/volver-a-activar/", views_hardware.hardware_volver_a_activar, name="hardware_volver_a_activar"),
    path("hardware/<int:equipo_id>/reactivar/", views_hardware.hardware_reactivar, name="hardware_reactivar"),
    # IOT-01: Tipos de actuador
    path("tipos/", views.tipos, name="tipos"),
    path("tipos/nuevo/", views.tipo_nuevo, name="tipo_nuevo"),
    path("tipos/<int:tipo_id>/modificar/", views.tipo_modificar, name="tipo_modificar"),
    path("tipos/<int:tipo_id>/reactivar/", views.tipo_reactivar, name="tipo_reactivar"),
    path("tipos/<int:tipo_id>/baja/", views.tipo_baja, name="tipo_baja"),
]
