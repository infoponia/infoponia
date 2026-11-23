# Rutas de `comercial` (COM-01): la pantalla «Comercial» (clientes y vehículos) y los fragmentos de HTMX de las direcciones. Los
# vehículos son solo del Gerente (D-37; vehiculos.md, «Quién»). COM-02 cambia el inicio por «Contratos».

from django.urls import path

from comercial import views

app_name = "comercial"

urlpatterns = [
    path("", views.inicio, name="inicio"),
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
