# Rutas de «Alertas» (MAE-02c, CU-46) bajo /alertas/: el listado con filtros, el detalle de una alerta y la ruta que la abre y redirige a su origen (MAE-02d). Van aparte de
# maestros/urls.py (que cuelga de /produccion/) para que el menú marque activa solo «Alertas» (se elige por prefijo), igual que
# «Configuración» (maestros/urls_configuracion.py).

from django.urls import path

from maestros import views

app_name = "alertas"

urlpatterns = [
    path("", views.alertas, name="lista"),
    path("<int:alerta_id>/", views.alerta, name="detalle"),
    # MAE-02d (D-62): abre la alerta y redirige a la pantalla de su origen (o al detalle).
    path("<int:alerta_id>/ir/", views.alerta_ir, name="ir"),
]
