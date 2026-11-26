# Vista de «Estadísticas» de Comercial (COM-08c; docs/casos_de_uso/comercial/estadisticas.md, «Pantallas»): la pestaña con los filtros (período, invernadero y, para el Gerente, Vendedor), las cuatro tarjetas
# y los seis indicadores. La vista SOLO orquesta: arma los filtros, llama al servicio (`estadisticas`) y renderiza; no calcula nada. El formulario es un GET común con «Ver estadísticas» (funciona sin JavaScript;
# con HTMX solo se redibuja el cuerpo). Nada se valida ni se recalcula al cambiar un desplegable (`.claude/rules/interfaz.md`): la validación del período corre al presionar el botón.

from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import estadisticas
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import stock

GERENTE, VENDEDOR = Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
@vary_on_headers("HX-Request")
@require_safe
def lista(request):
    """`/comercial/estadisticas/`: los ocho indicadores del período y los filtros elegidos (por omisión, el mes actual hasta hoy). Un filtro inválido no muestra números: muestra el motivo y «Corregí el filtro para
    ver las estadísticas.». Los demás roles reciben 403; con HTMX devuelve solo el cuerpo. No escribe ni audita."""
    hoy = stock.hoy()
    pedido = {campo: (request.GET.get(campo) or "").strip() for campo in ("periodo", "desde", "hasta", "invernadero", "vendedor")}
    errores, datos = [], None
    try:
        filtros = estadisticas.filtros_de_estadisticas(request.user, request.GET, hoy)
        datos = estadisticas.estadisticas(request.user, filtros, hoy)
        pedido["periodo"] = filtros.periodo
    except ValidationError as error:
        errores = error.messages
        filtros = estadisticas.filtros_de_estadisticas(request.user, {}, hoy)  # solo para las opciones de los desplegables
    contexto = {
        "filtros": filtros,
        "pedido": pedido,
        "datos": datos,
        "errores": errores,
        "es_gerente": request.user.rol == GERENTE,
        "hoy": hoy,
    }
    plantilla = "comercial/estadisticas/_cuerpo.html" if request.headers.get("HX-Request") == "true" else "comercial/estadisticas/lista.html"
    return render(request, plantilla, contexto)
