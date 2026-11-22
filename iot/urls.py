# Rutas de la app `iot` bajo /iot/ (IOT-01): el inicio del módulo y los tipos de actuador. Cada tarea siguiente suma las suyas
# (sistema, hardware, monitoreo, comandos y reglas). Las de texto fijo van antes que las que llevan id.

from django.urls import path

from iot import views

app_name = "iot"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("tipos/", views.tipos, name="tipos"),
    path("tipos/nuevo/", views.tipo_nuevo, name="tipo_nuevo"),
    path("tipos/<int:tipo_id>/modificar/", views.tipo_modificar, name="tipo_modificar"),
    path("tipos/<int:tipo_id>/reactivar/", views.tipo_reactivar, name="tipo_reactivar"),
    path("tipos/<int:tipo_id>/baja/", views.tipo_baja, name="tipo_baja"),
]
