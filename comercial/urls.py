# Rutas de `comercial` (COM-01): la pantalla «Comercial» (clientes y vehículos) y los fragmentos de HTMX de las direcciones. Los
# vehículos son solo del Gerente (D-37; vehiculos.md, «Quién»). COM-02 suma «Contratos» (compra-ventas) y el inicio redirige a ellos.

from django.urls import path

from comercial import views, views_camara, views_contratos, views_cosechas, views_entregas, views_envasado, views_faltantes, views_rutas, views_suministros

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
    # COM-05b (COM-CNL-CVT): cancelar la compra-venta, con su `revisar/` (el resumen; no escribe).
    path("contratos/compra-ventas/<int:venta_id>/cancelar/", views_contratos.compra_venta_cancelar, name="compra_venta_cancelar"),
    path("contratos/compra-ventas/<int:venta_id>/cancelar/revisar/", views_contratos.compra_venta_cancelar_revisar, name="compra_venta_cancelar_revisar"),
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
    # Cosechas (COM-04a): planificar y modificar (Agrónomo), concretar (Capataz, para celular) y cancelar (Agrónomo). Cada pantalla tiene su `calcular/` (redibuja
    # sin validar) y su `revisar/` (el resumen): ninguna de las dos escribe. Se llega desde las pantallas de `produccion` (lista de órdenes y bandeja).
    path("cosechas/planificar/", views_cosechas.planificar, name="cosecha_planificar"),
    path("cosechas/planificar/calcular/", views_cosechas.planificar_calcular, name="cosecha_planificar_calcular"),
    path("cosechas/planificar/revisar/", views_cosechas.planificar_revisar, name="cosecha_planificar_revisar"),
    path("cosechas/<int:cosecha_id>/modificar/", views_cosechas.modificar, name="cosecha_modificar"),
    path("cosechas/<int:cosecha_id>/modificar/calcular/", views_cosechas.modificar_calcular, name="cosecha_modificar_calcular"),
    path("cosechas/<int:cosecha_id>/modificar/revisar/", views_cosechas.modificar_revisar, name="cosecha_modificar_revisar"),
    path("cosechas/<int:cosecha_id>/concretar/", views_cosechas.concretar, name="cosecha_concretar"),
    path("cosechas/<int:cosecha_id>/concretar/calcular/", views_cosechas.concretar_calcular, name="cosecha_concretar_calcular"),
    path("cosechas/<int:cosecha_id>/concretar/revisar/", views_cosechas.concretar_revisar, name="cosecha_concretar_revisar"),
    path("cosechas/<int:cosecha_id>/cancelar/", views_cosechas.cancelar, name="cosecha_cancelar"),
    # Faltantes (COM-DCD-FLT, extensión 1a; COM-04c): el Vendedor registra la decisión por el cliente sin correo o con el enlace vencido.
    path("faltantes/", views_faltantes.lista, name="faltantes"),
    path("contratos/compra-ventas/<int:venta_id>/decidir-faltante/", views_faltantes.decidir, name="faltante_decidir"),
    # Entregas (COM-05a1): la lista de entregas de Comercial, con `?entrega=<id>` (la alerta) y `?transportista=<id>` (la ficha del invernadero › «Logística»).
    path("entregas/", views_entregas.lista, name="entregas"),
    # COM-05b (COM-ASG-TRP): asignar o cambiar el transportista de una entrega, con su `calcular/` («Cómo queda»; no escribe).
    path("entregas/<int:entrega_id>/asignar/", views_entregas.asignar, name="entrega_asignar"),
    path("entregas/<int:entrega_id>/asignar/calcular/", views_entregas.asignar_calcular, name="entrega_asignar_calcular"),
    # COM-06a (COM-INI-RUT, COM-FIN-RUT, COM-CNC-ENT): «Mi ruta» del Transportista, iniciar y finalizar la ruta, el intento fallido y concretar una entrega (con `calcular/`, que no escribe).
    path("ruta/", views_rutas.ruta, name="ruta"),
    path("ruta/iniciar/", views_rutas.iniciar, name="ruta_iniciar"),
    path("ruta/finalizar/", views_rutas.finalizar, name="ruta_finalizar"),
    path("entregas/<int:entrega_id>/intento-fallido/", views_rutas.intento_fallido, name="entrega_intento_fallido"),
    path("entregas/<int:entrega_id>/concretar/", views_rutas.concretar, name="entrega_concretar"),
    path("entregas/<int:entrega_id>/concretar/calcular/", views_rutas.concretar_calcular, name="entrega_concretar_calcular"),
    path("entregas/<int:entrega_id>/comprobante/", views_rutas.comprobante, name="entrega_comprobante"),
    # Envasado (COM-05a2, PROD-PNF-ENV): la lista de entregas a envasar del Agrónomo, la carga de envases de cada una (con `calcular/`) y su resumen (`revisar/`); ninguna de las dos escribe.
    path("envasado/", views_envasado.lista, name="envasado"),
    path("envasado/<int:entrega_id>/", views_envasado.entrega, name="envasado_entrega"),
    path("envasado/<int:entrega_id>/calcular/", views_envasado.calcular, name="envasado_calcular"),
    path("envasado/<int:entrega_id>/revisar/", views_envasado.revisar, name="envasado_revisar"),
    # Clientes (COM-ALT-CLT, COM-MOD-CLT, COM-BAJ-CLT, COM-CNS-CLT).
    path("camara/merma/", views_camara.merma, name="merma_camara"),  # COM-04b

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
