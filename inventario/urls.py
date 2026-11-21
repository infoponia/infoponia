# Rutas de inventario bajo /inventario/ (INV-01): el catálogo de insumos y las categorías (tipos de insumo). Cada pestaña es una
# página (respaldo sin JavaScript); INV-02 sumará «Existencias de insumos» como primera pestaña. El inicio lleva al catálogo.

from django.urls import path
from django.views.generic import RedirectView

from inventario import views

app_name = "inventario"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="inventario:catalogo", permanent=False), name="inicio"),
    # Catálogo de insumos (CMP-ALT-INS, CMP-MOD-INS, CMP-BAJ-INS, CMP-CNS-INS).
    path("catalogo/", views.catalogo, name="catalogo"),
    path("catalogo/nuevo/", views.insumo_nuevo, name="insumo_nuevo"),
    path("catalogo/<int:insumo_id>/modificar/", views.insumo_modificar, name="insumo_modificar"),
    path("catalogo/<int:insumo_id>/baja/", views.insumo_baja, name="insumo_baja"),
    path("catalogo/<int:insumo_id>/reactivar/", views.insumo_reactivar, name="insumo_reactivar"),
    # Categorías (CMP-ALT-TIN, CMP-MOD-TIN, CMP-BAJ-TIN, CMP-CNS-TIN).
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nueva/", views.categoria_nueva, name="categoria_nueva"),
    path("categorias/<int:tipo_id>/modificar/", views.categoria_modificar, name="categoria_modificar"),
    path("categorias/<int:tipo_id>/baja/", views.categoria_baja, name="categoria_baja"),
    path("categorias/<int:tipo_id>/reactivar/", views.categoria_reactivar, name="categoria_reactivar"),
]
