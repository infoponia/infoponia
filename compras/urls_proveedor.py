# Rutas públicas del portal del proveedor (CMP-ENV-COT; D-88 punto 4): ``/proveedor/<token>/`` valida el enlace y redirige a ``/proveedor/enlace/``. Sin
# ``login_required``: las vistas se eximen con ``login_not_required``. «enlace/» va antes del token para que no se lo confunda con uno.

from django.urls import path

from compras import views_proveedor

app_name = "proveedor"

urlpatterns = [
    path("enlace/", views_proveedor.portal, name="enlace"),
    path("<str:token>/", views_proveedor.entrada, name="entrada"),
]
