# Rutas de «Alertas» (MAE-02c, CU-46) bajo /alertas/: el listado con filtros y el detalle de una alerta. Van aparte de
# maestros/urls.py (que cuelga de /produccion/) para que el menú marque activa solo «Alertas» (se elige por prefijo), igual que
# «Configuración» (maestros/urls_configuracion.py).

from django.urls import path

from maestros import views

app_name = "alertas"

urlpatterns = [
    path("", views.alertas, name="lista"),
    path("<int:alerta_id>/", views.alerta, name="detalle"),
]
