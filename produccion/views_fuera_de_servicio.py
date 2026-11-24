# Vista de «Poner fuera de servicio» (PRD-04, paso 7; PROD-PNR-FDS, `VIEWS.fs` del prototipo). La vista SOLO orquesta: valida la entrada con `formularios`, llama
# al servicio y renderiza; las reglas están en `produccion/servicios/sectores_fuera_de_servicio.py`. Es una sola pantalla con tres acciones, todas un POST común
# (funciona sin JavaScript): «actualizar» (elegir el sector: solo redibuja lo que depende de él, SIN validar y sin mover el scroll con HTMX), «calcular» («Ver
# resumen»: valida y no escribe) y «confirmar» (vuelve a verificar bajo bloqueo, extensión 14a, y escribe). Nada se valida ni se calcula al escribir
# (.claude/rules/interfaz.md). Quién ve qué (D-30): solo el Agrónomo a cargo; el Capataz y el Gerente reciben 404 (no se les revela la ruta).

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from core.models import Usuario, rol_de
from produccion import formularios
from produccion.errores import ErrorDeProduccion
from produccion.models import Merma
from produccion.servicios import sectores_fuera_de_servicio as fds
from produccion.views import _en_vivo, _errores_por_campo, _servicio
from produccion.views_bitacora import _firma_de


def _causas():
    """Las causas que se ofrecen: las de un lote en pie, sin «descarte por selección» (regla «Causa de la merma»)."""
    return [(c.value, c.label) for c in Merma.CAUSAS_EN_PIE if c != Merma.Causa.DESCARTE_POR_SELECCION]


def _vistos(detalle, filas):
    """Lo que la persona vio, para la extensión 14a: las plantas de cada lote en el sector, los agujeros libres de cada destino y las órdenes."""
    return {
        "plantas": ",".join(f"{f['lote'].lote.pk}:{f['lote'].plantas}" for f in filas),
        "libres": ",".join(f"{d.sector.pk}:{d.libres}" for f in filas for d in {d.sector.pk: d for d in f["destinos"]}.values()),
        "ordenes": ",".join(str(o.orden.pk) for o in detalle.ordenes),
    }


@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def poner_fuera_de_servicio(request):
    """«Poner fuera de servicio» (PROD-PNR-FDS): sector → detalle, fecha y motivo → por lote, destinos y cantidades → causa de la merma por lote → resumen →
    confirmar. Sin sectores activos (precondición b) el formulario queda deshabilitado con su motivo. Elegir otro sector redibuja el bloque que depende de
    él (HTMX o «Continuar» sin JavaScript), sin validar. «Ver resumen» valida y no escribe; «Confirmar» vuelve a verificar con todo bloqueado y escribe."""
    if rol_de(request.user) != Usuario.Rol.AGRONOMO:
        raise Http404("No existe esa página.")
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    errores = {}
    grupos = _servicio(fds.sectores_para_fuera_de_servicio, request.user)
    ofrecidos = {s.pk for g in grupos for grupo in g.grupos for s in grupo.sectores}
    pedido = formularios.entero(datos.get("sector"))
    sector_id = pedido if pedido in ofrecidos else None
    if pedido and sector_id is None:
        errores["general"] = "Ese sector no está activo o no es de un invernadero a tu cargo."
    detalle, filas = None, []
    if sector_id:
        try:
            detalle = _servicio(fds.detalle_de_sector, request.user, sector_id)
        except ErrorDeProduccion as error:  # por ejemplo, un sector que otra persona puso fuera de servicio mientras tanto
            errores, sector_id = _errores_por_campo(error), None
    if detalle:
        destinos = fds.destinos_elegibles(detalle.sector, detalle.lotes)
        filas = [{"lote": l, "destinos": destinos[l.lote.pk]} for l in detalle.lotes]
    resumen, firma, cambio_la_firma = None, "", False
    if accion in ("calcular", "confirmar") and detalle:
        firma = _firma_de(datos)
        try:
            if accion == "confirmar" and datos.get("firma") == firma:
                registro = _servicio(fds.poner_fuera_de_servicio, request.user, formularios.fuera_de_servicio_desde_post(datos))
                canceladas = [o.orden.codigo for o in detalle.ordenes]
                texto = f"El sector {detalle.sector.nombre_sector} quedó fuera de servicio desde el {registro.fecha_efectiva:%d/%m/%Y}."
                if canceladas:
                    texto += f" Se cancelaron las órdenes {', '.join(canceladas)}: volvé a planificarlas."
                messages.success(request, texto)
                return redirect("maestros:invernadero", detalle.invernadero.pk)
            cambio_la_firma = accion == "confirmar"
            resumen = _servicio(fds.resumen_de_fuera_de_servicio, request.user, formularios.fuera_de_servicio_desde_post(datos, con_vistos=False))
        except ErrorDeProduccion as error:
            errores = _errores_por_campo(error)
            firma = ""
            if error.codigo == "cambio_simultaneo":  # 14a: se vuelve a mostrar con lo vigente
                errores["general"] = error.mensaje
    valores = dict(datos.items())
    valores.setdefault("fecha", f"{detalle.fecha_propuesta:%Y-%m-%d}" if detalle else "")
    contexto = {
        "grupos": grupos,
        "hay_sectores": bool(ofrecidos),
        "sector_id": sector_id,
        "detalle": detalle,
        "filas": filas,
        "causas": _causas(),
        "valores": valores,
        "errores": errores,
        "resumen": resumen,
        "firma": firma,
        "cambio_la_firma": cambio_la_firma,
        "vistos": _vistos(detalle, filas) if detalle else {},
        "hoy": timezone.localdate(),
    }
    plantilla = "produccion/_fuera_de_servicio_formulario.html" if _en_vivo(request) else "produccion/fuera_de_servicio.html"
    return render(request, plantilla, contexto)
