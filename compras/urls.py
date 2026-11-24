# Rutas de `compras` (CMP-01): «Compras» → «Proveedores». Cada tarea de la ronda suma las suyas.

from django.urls import path

from compras import views, views_pedidos

app_name = "compras"

urlpatterns = [
    # CMP-02a: «Compras» → «Pedidos» (el Agrónomo hace pedidos; el Gerente los consulta). «nuevo/» va antes del id.
    path("pedidos/", views_pedidos.pedidos, name="pedidos"),
    path("pedidos/nuevo/", views_pedidos.pedido_nuevo, name="pedido_nuevo"),
    path("pedidos/<int:pedido_id>/", views_pedidos.pedido_ficha, name="pedido_ficha"),
    path("proveedores/", views.proveedores, name="proveedores"),
    path("proveedores/nuevo/", views.proveedor_nuevo, name="proveedor_nuevo"),
    path("proveedores/<int:proveedor_id>/", views.proveedor_ficha, name="proveedor_ficha"),
    path("proveedores/<int:proveedor_id>/editar/", views.proveedor_editar, name="proveedor_editar"),
    path("proveedores/<int:proveedor_id>/reactivar/", views.proveedor_reactivar, name="proveedor_reactivar"),
    path("proveedores/<int:proveedor_id>/baja/", views.proveedor_baja, name="proveedor_baja"),
]
