# Rutas de `produccion` (PRD-01), bajo `/produccion/`. Las de la lista y el detalle de órdenes empiezan con `ordenes/` y las del Capataz,
# con `bandeja/`: no chocan con las de `maestros` (`/produccion/<id>/...`, `/produccion/cultivos/...`) ni con las de
# `inventario.urls_variedades`.
from django.urls import path

from produccion import views, views_bitacora, views_fuera_de_servicio

app_name = "produccion"

urlpatterns = [
    path("ordenes/", views.lista, name="ordenes"),
    path("ordenes/nueva-siembra/", views.nueva_siembra, name="nueva_siembra"),
    path("ordenes/nueva-transicion/", views.nueva_transicion, name="nueva_transicion"),
    path("ordenes/<int:orden_id>/", views.orden, name="orden"),
    path("ordenes/<int:orden_id>/cancelar/", views.cancelar, name="cancelar"),
    path("bandeja/", views.bandeja, name="bandeja"),
    path("bandeja/<int:orden_id>/concretar/", views.concretar, name="concretar"),
    # PRD-03: la bitácora (consulta y registros). Ninguna ruta edita ni borra un registro de bitácora (regla 5 de PROD-REG-EVT).
    path("bitacora/", views_bitacora.consulta, name="bitacora"),
    path("registrar/", views_bitacora.registrar, name="registrar"),
    path("registrar/merma/", views_bitacora.registrar_merma, name="registrar_merma"),
    path("registrar/aplicacion/", views_bitacora.registrar_aplicacion, name="registrar_aplicacion"),
    path("registrar/evento/", views_bitacora.registrar_evento, name="registrar_evento"),
    # PRD-04: poner un sector fuera de servicio (PROD-PNR-FDS). `?sector=<id>` lo deja elegido (entrada desde la ficha del sector).
    path("sectores/fuera-de-servicio/", views_fuera_de_servicio.poner_fuera_de_servicio, name="fuera_de_servicio"),
]
