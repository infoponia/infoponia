# URLconf SOLO de pruebas (CON-05, paso 3): las rutas del proyecto más tres vistas mínimas que sirven para probar `ContabilidadNoIniciadaMiddleware` de punta a punta con el
# cliente de Django. Se activa con `@override_settings(ROOT_URLCONF="contabilidad.tests.urls_de_prueba")`; no es parte del sistema.
import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.http import HttpResponse

from config.urls import urlpatterns as rutas_del_proyecto
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.servicios import asientos
from contabilidad.tests.fabricas import origen_de_prueba
from django.urls import path

MOVIMIENTOS = [(cuentas.CAJA, DEBE, Decimal("10.00")), (cuentas.VENTAS, HABER, Decimal("10.00"))]


def _operacion_con_asiento(request):
    """Una operación que crea algo propio y después pide su asiento: sin ejercicio el servicio lanza `contabilidad_no_iniciada` y lo propio se tiene que deshacer."""
    actor = request.user if request.user.is_authenticated else None
    with transaction.atomic():
        origen = origen_de_prueba()
        asientos.registrar_asiento_automatico(actor, origen, datetime.date(2027, 3, 10), MOVIMIENTOS, hoy=datetime.date(2027, 3, 10))
    return HttpResponse("registrada")


def operacion_con_asiento(request):
    """Pantalla común (con sesión): la operación con asiento."""
    return _operacion_con_asiento(request)


@login_not_required
def operacion_con_asiento_por_enlace(request):
    """Pantalla de enlace externo (sin sesión: proveedor, cliente o transportista): la misma operación."""
    return _operacion_con_asiento(request)


def otro_error_contable(request):
    """Una vista que lanza un `ErrorContable` de OTRO código: el middleware no tiene que atenderlo."""
    raise ErrorContable("asiento_desbalanceado", "El asiento no está balanceado.")


def todo_bien(request):
    """Una vista que anda: sin excepción, el middleware no interviene."""
    return HttpResponse("ok")


urlpatterns = [
    path("_prueba/operacion/", operacion_con_asiento, name="prueba_operacion"),
    path("_prueba/enlace/", operacion_con_asiento_por_enlace, name="prueba_enlace"),
    path("_prueba/otro-error/", otro_error_contable, name="prueba_otro_error"),
    path("_prueba/ok/", todo_bien, name="prueba_ok"),
    *rutas_del_proyecto,
]
