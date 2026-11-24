# Vista de la pestaña «Entregas» de Comercial (COM-05a1; docs/casos_de_uso/comercial/entregas.md, «Pantallas»): la lista de entregas del Gerente y del Vendedor, con filtros en la URL
# (estado, invernadero, transportista y los dos parámetros `?entrega=` de la alerta y `?transportista=` de «Logística»). Solo «Ver contrato»: «Asignar transportista» es de COM-05b y
# «Concretar retiro», de COM-06. La vista solo orquesta: arma los filtros, llama al servicio y renderiza; sin JavaScript todo funciona (el formulario es un GET común con «Filtrar»;
# con HTMX solo se redibuja la tabla). Nunca se filtra mientras se tipea (`.claude/rules/interfaz.md`).

from urllib.parse import urlencode

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import entregas
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import stock

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def lista(request):
    """Pestaña «Entregas» (`tabEntregas` del prototipo): las entregas del alcance del usuario, de a 50, con sus filtros. El Gerente ve todas y el Vendedor las de sus contratos; el
    Agrónomo y el Capataz reciben 403 (SEG-13). Con HTMX devuelve solo la tabla. No audita."""
    filtros = entregas.FiltrosDeEntregas.desde_get(request.GET)
    datos = entregas.lista_de_entregas(request.user, filtros, stock.hoy())
    contexto = {
        "datos": datos,
        "filtros": filtros,
        "estados": entregas.ESTADOS_DE_LA_LISTA,
        "sin_transportista": entregas.SIN_TRANSPORTISTA,
        "es_gerente": request.user.rol == GERENTE,
        "consulta": urlencode({k: v for k, v in request.GET.items() if k != "pagina"}),
    }
    plantilla = "comercial/entregas/_tabla.html" if request.headers.get("HX-Request") == "true" else "comercial/entregas/lista.html"
    return render(request, plantilla, contexto)
