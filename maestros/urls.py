# Rutas de maestros bajo /produccion/: lista, ficha y alta de invernaderos (MAE-01a) y los fragmentos de HTMX del
# formulario. Las de texto fijo van antes que la ficha (``<int:...>`` no las confunde, pero así se lee el orden).

from django.urls import path

from maestros import views

app_name = "maestros"

urlpatterns = [
    path("", views.invernaderos, name="invernaderos"),
    path("nuevo/", views.invernadero_nuevo, name="invernadero_nuevo"),
    # Fragmentos de HTMX del formulario de alta (solo GET).
    path("nuevo/direccion/", views.campos_direccion, name="campos_direccion"),
    path("nuevo/departamentos/", views.departamentos, name="departamentos"),
    path("nuevo/localidades/", views.localidades, name="localidades"),
    path("<int:invernadero_id>/", views.invernadero, name="invernadero"),
]
