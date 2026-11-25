# Rutas públicas del portal del cliente (COM-DCD-FLT; D-65 punto 3): `/cliente/<token>/` valida el enlace y redirige a `/cliente/enlace/`. Sin `login_required`: las vistas se eximen con
# `login_not_required`. «enlace/» va antes del token para que no se lo confunda con uno.

from django.urls import path

from comercial import views_cliente

app_name = "cliente"

urlpatterns = [
    path("enlace/", views_cliente.decision, name="decision"),
    path("enlace/listo/", views_cliente.listo, name="listo"),
    path("enlace/listo/reenviar/", views_cliente.reenviar_acuse, name="reenviar_acuse"),  # COM-06b, extensión 8a de COM-CNF-ENT
    path("<str:token>/", views_cliente.entrada, name="entrada"),
]
