# Rutas de `estadisticas` (EST-01). Se montan en `/estadisticas/` desde `config/urls.py`; EST-02 suma `consolidadas/`.

from django.urls import path

from estadisticas import views

app_name = "estadisticas"

urlpatterns = [
    path("", views.produccion, name="produccion"),
    path("consolidadas/", views.consolidadas, name="consolidadas"),
]
