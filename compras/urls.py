# Rutas de `compras` (CMP-01): «Compras» → «Proveedores». Cada tarea de la ronda suma las suyas.

from django.urls import path

from compras import views

app_name = "compras"

urlpatterns = [
    path("proveedores/", views.proveedores, name="proveedores"),
    path("proveedores/nuevo/", views.proveedor_nuevo, name="proveedor_nuevo"),
    path("proveedores/<int:proveedor_id>/", views.proveedor_ficha, name="proveedor_ficha"),
    path("proveedores/<int:proveedor_id>/editar/", views.proveedor_editar, name="proveedor_editar"),
    path("proveedores/<int:proveedor_id>/reactivar/", views.proveedor_reactivar, name="proveedor_reactivar"),
    path("proveedores/<int:proveedor_id>/baja/", views.proveedor_baja, name="proveedor_baja"),
]
