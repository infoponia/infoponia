# Rutas de variedades bajo /produccion/ (INV-03, paso 8): son parte de «Producción» → «Cultivos y variedades» (MAE-03), que vive en
# `maestros`; por eso no cuelgan de /inventario/. Cada pantalla es una página (respaldo sin JavaScript). Solo el Agrónomo (el Gerente: 404).

from django.urls import path

from inventario import views_variedades

app_name = "variedades"

urlpatterns = [
    path("cultivos/<int:cultivo_id>/variedades/nueva/", views_variedades.variedad_nueva, name="variedad_nueva"),
    path("variedades/etapas/", views_variedades.etapas_del_perfil, name="etapas_del_perfil"),
    path("variedades/<int:variedad_id>/", views_variedades.variedad, name="variedad"),
    path("variedades/<int:variedad_id>/creada/", views_variedades.variedad_creada, name="variedad_creada"),
    path("variedades/<int:variedad_id>/baja/", views_variedades.variedad_baja, name="variedad_baja"),
    path("variedades/<int:variedad_id>/reactivar/", views_variedades.variedad_reactivar, name="variedad_reactivar"),
]
