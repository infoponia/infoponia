# Rutas de `contabilidad` (CON-03a): el libro de gestión (con la ficha del asiento), los ejercicios (con el cierre) y el plan de cuentas, tres pestañas de «Contabilidad».
from django.urls import path

from contabilidad import views

app_name = "contabilidad"

urlpatterns = [
    path("", views.libro_de_gestion, name="libro"),
    path("asientos/<int:ejercicio_id>/<int:numero>/", views.asiento, name="asiento"),
    path("ejercicios/", views.pestana_de_ejercicios, name="ejercicios"),
    path("ejercicios/<int:ejercicio_id>/cerrar/", views.cierre, name="cierre"),
    path("plan-de-cuentas/", views.plan_de_cuentas, name="plan"),
]
