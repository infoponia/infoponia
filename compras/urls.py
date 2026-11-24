# Rutas de `compras` (CMP-01): «Compras» → «Proveedores». Cada tarea de la ronda suma las suyas.

from django.urls import path

from compras import views, views_ordenes, views_pedidos

app_name = "compras"

urlpatterns = [
    # CMP-02a: «Compras» → «Pedidos» (el Agrónomo hace pedidos; el Gerente los consulta). «nuevo/» va antes del id.
    path("pedidos/", views_pedidos.pedidos, name="pedidos"),
    path("pedidos/nuevo/", views_pedidos.pedido_nuevo, name="pedido_nuevo"),
    path("pedidos/<int:pedido_id>/", views_pedidos.pedido_ficha, name="pedido_ficha"),
    # CMP-02b: cancelar el pedido (formulario, resumen y confirmación) y reenviar la invitación a un proveedor (ventana).
    path("pedidos/<int:pedido_id>/cancelar/", views_pedidos.pedido_cancelar, name="pedido_cancelar"),
    path("pedidos/invitaciones/<int:invitacion_id>/reenviar/", views_pedidos.invitacion_reenviar, name="invitacion_reenviar"),
    # CMP-03: comparar las cotizaciones y generar la orden (Agrónomo), y «Compras» → «Órdenes» (lista, ficha y revisar y decidir).
    path("pedidos/<int:pedido_id>/generar-orden/", views_ordenes.pedido_generar_orden, name="pedido_generar_orden"),
    path("ordenes/", views_ordenes.ordenes, name="ordenes"),
    path("ordenes/<int:orden_id>/", views_ordenes.orden_ficha, name="orden_ficha"),
    path("ordenes/<int:orden_id>/resolver/", views_ordenes.orden_resolver, name="orden_resolver"),
    path("proveedores/", views.proveedores, name="proveedores"),
    path("proveedores/nuevo/", views.proveedor_nuevo, name="proveedor_nuevo"),
    path("proveedores/<int:proveedor_id>/", views.proveedor_ficha, name="proveedor_ficha"),
    path("proveedores/<int:proveedor_id>/editar/", views.proveedor_editar, name="proveedor_editar"),
    path("proveedores/<int:proveedor_id>/reactivar/", views.proveedor_reactivar, name="proveedor_reactivar"),
    path("proveedores/<int:proveedor_id>/baja/", views.proveedor_baja, name="proveedor_baja"),
]
