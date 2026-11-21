# Rutas de «Configuración» (MAE-04) bajo /configuracion/: la pantalla del Gerente y el guardado de cada pestaña. Van aparte de
# maestros/urls.py (que cuelga de /produccion/) para que el menú marque activa solo «Configuración» (se elige por prefijo).

from django.urls import path

from maestros import views

app_name = "configuracion"

urlpatterns = [
    path("", views.configuracion, name="pantalla"),
    path("parametros/", views.configuracion_guardar_parametros, name="guardar_parametros"),
    path("organizacion/", views.configuracion_guardar_organizacion, name="guardar_organizacion"),
]
