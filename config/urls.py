# Rutas del proyecto: las pantallas de core y, solo en desarrollo, el admin de Django (SEG-18, D-30).

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    # MAE-01: invernaderos (Producción).
    path("produccion/", include("maestros.urls")),
    # INV-03: variedades, dentro de «Cultivos y variedades» (Agrónomo).
    path("produccion/", include("inventario.urls_variedades")),
    # MAE-04: configuración operativa y perfil de la organización (Gerente).
    path("configuracion/", include("maestros.urls_configuracion")),
    # MAE-02c: consulta de alertas (Gerente y Agrónomo).
    path("alertas/", include("maestros.urls_alertas")),
    # INV-01: catálogo de insumos y categorías (Agrónomo).
    path("inventario/", include("inventario.urls")),
    # PRD-01: órdenes de siembra, bandeja del Capataz y lotes. Rutas bajo /produccion/ordenes/ (no chocan con las de maestros).
    path("produccion/", include("produccion.urls")),
    # IOT-01: módulo IoT (Gerente y Agrónomo); empieza por los tipos de actuador.
    path("iot/", include("iot.urls")),
    # COM-01: «Comercial» (clientes y vehículos; Gerente y Vendedor).
    path("comercial/", include("comercial.urls")),
    # CMP-01: «Compras» → «Proveedores» (Gerente y Agrónomo).
    path("compras/", include("compras.urls")),
    # EST-01: «Estadísticas» de producción (Agrónomo y Gerente).
    path("estadisticas/", include("estadisticas.urls")),
    # COM-04c: portal público del cliente (decide un faltante sin cuenta por el enlace que recibió por correo; D-65).
    path("cliente/", include("comercial.urls_cliente")),
    # CON-03a: «Contabilidad» (libro de gestión, plan de cuentas y ejercicios; Contador y Gerente).
    path("contabilidad/", include("contabilidad.urls")),
    # CMP-02a: portal público del proveedor (cotiza sin cuenta por el enlace que recibió por correo; D-88).
    path("proveedor/", include("compras.urls_proveedor")),
    # IOT-03: API HTTPS del nodo central (contrato en docs/api/nodo/; D-70). Sin sesión ni CSRF: la protege el token.
    path("api/iot/v1/", include("iot.api.urls")),

]

# SEG-18: con ``ADMIN_DJANGO_HABILITADO`` apagado (producción) no se registra ninguna ruta de /admin/, así que
# responde 404 incluso a un Administrador con sesión abierta.
if settings.ADMIN_DJANGO_HABILITADO:
    urlpatterns.insert(0, path("admin/", admin.site.urls))

# USR-07 (D-106 punto 4): en desarrollo sin R2 las imágenes están en el disco local (``media/``) y Django las sirve. Sin sesión: el
# logo se ve también en el inicio de sesión. Solo con DEBUG y con el almacenamiento de disco: en producción las imágenes salen de
# R2 con URL firmada y esta ruta no existe.
if settings.DEBUG and settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage":
    from django.contrib.auth.decorators import login_not_required
    from django.views.static import serve

    urlpatterns.append(
        path(f"{settings.MEDIA_URL.strip('/')}/<path:path>", login_not_required(serve), {"document_root": settings.MEDIA_ROOT})
    )
