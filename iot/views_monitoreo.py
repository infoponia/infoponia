# Vista del panel de monitoreo (IOT-04; IOT-CNS-LEC; docs/casos_de_uso/iot/consultar_lecturas.md, «Ruta y pestaña», «Refresco», «Pantallas»). Las vistas solo orquestan
# (docs/patrones/abm.md, sección 1): eligen el invernadero (``contexto_del_modulo``) y el período, llaman a ``monitoreo.panel`` y renderizan. Solo lectura: no audita (regla 12).
#
# El panel es una página con un fragmento (``<div id="panel">``): con ``HX-Request`` se devuelve SOLO el fragmento y sin él, la página entera (sin JavaScript se actualiza recargando).
# El período se pide con ``?periodo=`` (uno de los cinco; si no, se usa el recordado en la sesión, ``iot_periodo``, o 24). Un ``?invernadero=`` que no existe o no es del alcance es 404.

from urllib.parse import quote

from django.http import HttpResponseNotAllowed
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.contexto import contexto_del_modulo, es_htmx
from iot.servicios import monitoreo as api
from iot.servicios.alertas_iot import TIPO_NO_REGISTRADO
from iot.textos import numero_legible
from maestros.forms import GRUPOS_IOT

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO
CLAVE_DEL_PERIODO = "iot_periodo"
SEVERIDADES = {"critica": ("Crítica", "danger"), "advertencia": ("Advertencia", "warn"), "informativa": ("Informativa", "info")}


def _periodo(request):
    """El período del panel: el pedido en ``?periodo=`` si es uno de los cinco (y se recuerda en la sesión); si no (otro número, texto, vacío), el recordado o, sin recordado, 24."""
    pedido = request.GET.get("periodo", "")
    if pedido.isascii() and pedido.isdigit() and int(pedido) in api.PERIODOS:
        request.session[CLAVE_DEL_PERIODO] = int(pedido)
        return int(pedido)
    recordado = request.session.get(CLAVE_DEL_PERIODO)
    return recordado if recordado in api.PERIODOS else api.PERIODO_POR_OMISION


def _acciones_de_la_alerta(fila, panel):
    """Los botones de una fila de «Alertas activas» (regla 7 y 11): «Ver equipo» para las de un equipo; en «dispositivo no registrado», a quien opera «Registrar este equipo» o, si
    el identificador era de un equipo dado de baja, «Reactivar equipo» y «Registrar reemplazo»; a quien solo consulta, solo «Ver equipo» de la baja. Nunca un botón a un 403 (D-30)."""
    alerta, enlace = fila.alerta, fila.enlace
    if alerta.tipo_alerta == TIPO_NO_REGISTRADO:
        if not panel.opera:
            return [("Ver equipo", enlace.url)] if fila.equipo_dado_de_baja is not None else []
        if fila.equipo_dado_de_baja is None:
            return [("Registrar este equipo", enlace.url)]
        identificador = alerta.clave_estado.removeprefix("id:")
        alta = f"{reverse('iot:hardware_nuevo')}?invernadero={alerta.invernadero_id}&identificador={quote(identificador, safe='')}"
        return [("Reactivar equipo", enlace.url), ("Registrar reemplazo", alta)]
    if alerta.tipo_alerta == "iot_nodo_sin_comunicacion":
        return []
    return [("Ver equipo", enlace.url)]


def _contexto_del_panel(request, contexto, panel, periodo):
    """Lo que dibuja ``_panel.html`` y la página: el panel, el período, los botones de cada alerta y los parámetros agrupados y en texto (el Agrónomo los ve en solo lectura)."""
    elegido = contexto["elegido"]
    valores = {p.campo: p.valor for p in panel.parametros}
    return contexto | {
        "panel": panel,
        "periodo": periodo,
        "periodos": [{"valor": clave, "nombre": nombre, "actual": clave == periodo} for clave, nombre in api.PERIODOS.items()],
        "url_del_panel": f"{reverse('iot:monitoreo')}?invernadero={elegido.pk}&periodo={periodo}",
        "filas_de_alertas": [
            {"fila": fila, "severidad": SEVERIDADES[fila.severidad], "acciones": _acciones_de_la_alerta(fila, panel)} for fila in panel.alertas
        ],
        "grupos_de_parametros": [
            (grupo, [(etiqueta, numero_legible(valores[campo])) for campo, etiqueta, _ in parametros]) for grupo, parametros in GRUPOS_IOT
        ]
        if panel.parametros
        else [],
    }


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def monitoreo(request):
    """«Monitoreo» (IOT-CNS-LEC; ``monitoreo`` del prototipo): el panel del invernadero elegido. Con HTMX devuelve solo el fragmento del panel (lo que se refresca cada 30 s);
    sin él, la página entera. Solo lectura: no escribe ni audita, y abrirla no dispara la revisión periódica (reglas 10 y 12)."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    contexto = contexto_del_modulo(request, "monitoreo")
    periodo = _periodo(request)
    if contexto["elegido"] is None:
        return render(request, "iot/monitoreo/pagina.html", contexto | {"panel": None, "periodo": periodo})
    panel = api.panel(request.user, contexto["elegido"].pk, periodo, timezone.now())
    contexto = _contexto_del_panel(request, contexto, panel, periodo)
    if es_htmx(request):
        return render(request, "iot/monitoreo/_panel.html", contexto)
    return render(request, "iot/monitoreo/pagina.html", contexto)
