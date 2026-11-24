# Rutas de la app `iot` bajo /iot/ (IOT-01 e IOT-02): el inicio del módulo, el sistema IoT, el hardware y los tipos de actuador. Cada tarea siguiente suma las
# suyas (monitoreo, comandos y reglas). Las de texto fijo van antes que las que llevan id.

from django.urls import path

from iot import views, views_comandos, views_hardware, views_monitoreo, views_reglas, views_sistema

app_name = "iot"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    # IOT-04: Monitoreo (IOT-CNS-LEC)
    path("monitoreo/", views_monitoreo.monitoreo, name="monitoreo"),
    # IOT-05: Comandos (IOT-EMT-CMD, IOT-CNL-CMD)
    path("comandos/", views_comandos.comandos, name="comandos"),
    path("comandos/<int:comando_id>/cancelar/", views_comandos.comando_cancelar, name="comando_cancelar"),
    # IOT-06: Reglas de actuación (IOT-ALT-RGL, IOT-MOD-RGL, IOT-BAJ-RGL, IOT-CNS-RGL)
    path("reglas/", views_reglas.reglas, name="reglas"),
    path("reglas/nueva/", views_reglas.regla_nueva, name="regla_nueva"),
    path("reglas/<int:regla_id>/", views_reglas.regla_ficha, name="regla_ficha"),
    path("reglas/<int:regla_id>/modificar/", views_reglas.regla_modificar, name="regla_modificar"),
    path("reglas/<int:regla_id>/baja/", views_reglas.regla_baja, name="regla_baja"),
    path("reglas/<int:regla_id>/reactivar/", views_reglas.regla_reactivar, name="regla_reactivar"),
    # IOT-02: Sistema IoT (IOT-REG-SIS, IOT-MOD-SIS) e IOT-06 (IOT-DSC-SIS, IOT-ACT-SIS, IOT-BAJ-SIS)
    path("sistema/", views_sistema.sistema, name="sistema"),
    path("sistema/<int:sistema_id>/desactivar/", views_sistema.sistema_desactivar, name="sistema_desactivar"),
    path("sistema/<int:sistema_id>/activar/", views_sistema.sistema_activar, name="sistema_activar"),
    path("sistema/<int:sistema_id>/baja/", views_sistema.sistema_baja, name="sistema_baja"),
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
    path("hardware/<int:equipo_id>/baja/", views_hardware.hardware_baja, name="hardware_baja"),
    # IOT-01: Tipos de actuador
    path("tipos/", views.tipos, name="tipos"),
    path("tipos/nuevo/", views.tipo_nuevo, name="tipo_nuevo"),
    path("tipos/<int:tipo_id>/modificar/", views.tipo_modificar, name="tipo_modificar"),
    path("tipos/<int:tipo_id>/reactivar/", views.tipo_reactivar, name="tipo_reactivar"),
    path("tipos/<int:tipo_id>/baja/", views.tipo_baja, name="tipo_baja"),
]
