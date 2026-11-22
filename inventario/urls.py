# Rutas de inventario bajo /inventario/: «Existencias de insumos» (INV-02, primera pestaña), el catálogo de insumos y las categorías
# (INV-01) y el ajuste de stock (INV-02). Cada pestaña es una página (respaldo sin JavaScript). El inicio lleva a las existencias.

from django.urls import path
from django.views.generic import RedirectView

from inventario import views, views_ajuste, views_existencias

app_name = "inventario"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="inventario:existencias", permanent=False), name="inicio"),
    # Existencias de insumos (CMP-CNS-IIN, CMP-HAB-IIN, CMP-MOD-IIN, CMP-DSH-IIN) y ajuste de stock (CMP-AJT-STK).
    path("existencias/", views_existencias.existencias, name="existencias"),
    path("existencias/habilitar/", views_existencias.habilitar, name="habilitar"),
    path("existencias/<int:iin_id>/modificar/", views_existencias.existencia_modificar, name="existencia_modificar"),
    path("existencias/<int:iin_id>/deshabilitar/", views_existencias.existencia_deshabilitar, name="existencia_deshabilitar"),
    path("ajuste/", views_ajuste.ajuste, name="ajuste"),
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
