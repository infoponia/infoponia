# Rutas de la API del nodo (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md, «La API»): sin barra final, como el contrato, y una ruta que atrapa cualquier
# otra y responde 404 ``ruta_inexistente`` en JSON. Se incluye en ``config/urls.py`` con ``path("api/iot/v1/", include("iot.api.urls"))``.

from django.urls import path, re_path

from iot.api import vistas

app_name = "iot_api"

urlpatterns = [
    path("lecturas", vistas.lecturas_vista, name="lecturas"),
    path("estados", vistas.estados_vista, name="estados"),
    path("modo", vistas.modo_vista, name="modo"),
    path("anuncio", vistas.anuncio_vista, name="anuncio"),
    re_path(r"^.*$", vistas.ruta_inexistente, name="ruta_inexistente"),
]
