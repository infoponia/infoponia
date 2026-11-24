# Rutas de `comercial` (COM-01): la pantalla «Comercial» (clientes y vehículos) y los fragmentos de HTMX de las direcciones. Los
# vehículos son solo del Gerente (D-37; vehiculos.md, «Quién»). COM-02 suma «Contratos» (compra-ventas) y el inicio redirige a ellos.

from django.urls import path

from comercial import views, views_contratos, views_suministros

app_name = "comercial"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    # Contratos (COM-REG-CVT, COM-CNS-CVT): compra-ventas. COM-03a suma los suministros (COM-PCT-SUM, COM-CNS-SUM); la lista es la misma, con ?tipo=suministro.
    path("contratos/", views_contratos.contratos, name="contratos"),
    path("contratos/compra-ventas/nueva/", views_contratos.compra_venta_nueva, name="compra_venta_nueva"),
    path("contratos/compra-ventas/nueva/calcular/", views_contratos.compra_venta_calcular, name="compra_venta_calcular"),
    path("contratos/compra-ventas/nueva/revisar/", views_contratos.compra_venta_revisar, name="compra_venta_revisar"),
    path("contratos/compra-ventas/<int:venta_id>/", views_contratos.compra_venta, name="compra_venta"),
    path("contratos/compra-ventas/<int:venta_id>/comprobante/", views_contratos.compra_venta_comprobante, name="compra_venta_comprobante"),
    path(
        "contratos/compra-ventas/<int:venta_id>/reenviar-comprobante/",
        views_contratos.compra_venta_reenviar_comprobante,
        name="compra_venta_reenviar_comprobante",
    ),
    path("contratos/suministros/nuevo/", views_suministros.suministro_nuevo, name="suministro_nuevo"),
    path("contratos/suministros/nuevo/calcular/", views_suministros.suministro_calcular, name="suministro_calcular"),
    path("contratos/suministros/nuevo/revisar/", views_suministros.suministro_revisar, name="suministro_revisar"),
    path("contratos/suministros/<int:suministro_id>/", views_suministros.suministro, name="suministro"),
    path("contratos/suministros/<int:suministro_id>/calendario/", views_suministros.suministro_calendario, name="suministro_calendario"),
    path("contratos/suministros/<int:suministro_id>/comprobante/", views_suministros.suministro_comprobante, name="suministro_comprobante"),
    path(
        "contratos/suministros/<int:suministro_id>/reenviar-comprobante/",
        views_suministros.suministro_reenviar_comprobante,
        name="suministro_reenviar_comprobante",
    ),
    # COM-03b: modificar (con calcular/ y revisar/), rescindir, dejar sin efecto la rescisión y el historial de cambios.
    path("contratos/suministros/<int:suministro_id>/modificar/", views_suministros.suministro_modificar, name="suministro_modificar"),
    path("contratos/suministros/<int:suministro_id>/modificar/calcular/", views_suministros.suministro_modificar_calcular, name="suministro_modificar_calcular"),
    path("contratos/suministros/<int:suministro_id>/modificar/revisar/", views_suministros.suministro_modificar_revisar, name="suministro_modificar_revisar"),
    path("contratos/suministros/<int:suministro_id>/rescindir/", views_suministros.suministro_rescindir, name="suministro_rescindir"),
    path(
        "contratos/suministros/<int:suministro_id>/dejar-sin-efecto-rescision/", views_suministros.suministro_dejar_sin_efecto, name="suministro_dejar_sin_efecto"
    ),
    path("contratos/suministros/<int:suministro_id>/historial/", views_suministros.suministro_historial, name="suministro_historial"),
    # Clientes (COM-ALT-CLT, COM-MOD-CLT, COM-BAJ-CLT, COM-CNS-CLT).
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_nuevo, name="cliente_nuevo"),
    path("clientes/<int:cliente_id>/", views.cliente, name="cliente"),
    path("clientes/<int:cliente_id>/modificar/", views.cliente_modificar, name="cliente_modificar"),
    path("clientes/<int:cliente_id>/reactivar/", views.cliente_reactivar, name="cliente_reactivar"),
    path("clientes/<int:cliente_id>/baja/", views.cliente_baja, name="cliente_baja"),
    # Vehículos (COM-ALT-VEH, COM-MOD-VEH, COM-BAJ-VEH, COM-CNS-VEH).
    path("vehiculos/", views.vehiculos, name="vehiculos"),
    path("vehiculos/nuevo/", views.vehiculo_nuevo, name="vehiculo_nuevo"),
    path("vehiculos/<int:vehiculo_id>/", views.vehiculo, name="vehiculo"),
    path("vehiculos/<int:vehiculo_id>/modificar/", views.vehiculo_modificar, name="vehiculo_modificar"),
    path("vehiculos/<int:vehiculo_id>/reactivar/", views.vehiculo_reactivar, name="vehiculo_reactivar"),
    path("vehiculos/<int:vehiculo_id>/baja/", views.vehiculo_baja, name="vehiculo_baja"),
    # Fragmentos de las listas encadenadas de Georef (D-58, punto 7): solo GET.
    path("direccion/campos/", views.direccion_campos, name="direccion_campos"),
    path("direccion/departamentos/", views.direccion_departamentos, name="direccion_departamentos"),
    path("direccion/localidades/", views.direccion_localidades, name="direccion_localidades"),
]
