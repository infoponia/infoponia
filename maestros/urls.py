# Rutas de maestros bajo /produccion/: lista, ficha, alta, modificación, baja y reactivación de invernaderos (MAE-01) y los
# fragmentos de HTMX del formulario. Las de texto fijo van antes que la ficha (``<int:...>`` no las confunde, pero así se lee el orden).

from django.urls import path

from maestros import views

app_name = "maestros"

urlpatterns = [
    path("", views.invernaderos, name="invernaderos"),
    path("nuevo/", views.invernadero_nuevo, name="invernadero_nuevo"),
    # MAE-03: «Cultivos y variedades» (solo el Agrónomo; al Gerente le dan 404). Van antes de la ficha por orden de lectura.
    path("cultivos/", views.cultivos_y_variedades, name="cultivos"),
    path("cultivos/nuevo/", views.cultivo_nuevo, name="cultivo_nuevo"),
    path("cultivos/<int:cultivo_id>/renombrar/", views.cultivo_renombrar, name="cultivo_renombrar"),
    path("cultivos/<int:cultivo_id>/baja/", views.cultivo_baja, name="cultivo_baja"),
    path("cultivos/<int:cultivo_id>/reactivar/", views.cultivo_reactivar, name="cultivo_reactivar"),
    # Fragmentos de HTMX del formulario de alta (solo GET).
    path("nuevo/direccion/", views.campos_direccion, name="campos_direccion"),
    path("nuevo/departamentos/", views.departamentos, name="departamentos"),
    path("nuevo/localidades/", views.localidades, name="localidades"),
    path("<int:invernadero_id>/", views.invernadero, name="invernadero"),
    path("<int:invernadero_id>/modificar/", views.invernadero_modificar, name="invernadero_modificar"),
    path("<int:invernadero_id>/baja/", views.invernadero_baja, name="invernadero_baja"),
    path("<int:invernadero_id>/reactivar/", views.invernadero_reactivar, name="invernadero_reactivar"),
    # MAE-03: sectores de un invernadero. Cada ventana es una página (respaldo sin JavaScript) y, con HTMX, un fragmento.
    path("<int:invernadero_id>/sectores/nuevo/", views.sector_nuevo, name="sector_nuevo"),
    path("<int:invernadero_id>/sectores/<int:sector_id>/modificar/", views.sector_modificar, name="sector_modificar"),
    path("<int:invernadero_id>/sectores/<int:sector_id>/baja/", views.sector_baja, name="sector_baja"),
    path("<int:invernadero_id>/sectores/<int:sector_id>/reactivar/", views.sector_reactivar, name="sector_reactivar"),
    path(
        "<int:invernadero_id>/sectores/<int:sector_id>/volver-a-servicio/",
        views.sector_volver_a_servicio,
        name="sector_volver_a_servicio",
    ),
]
