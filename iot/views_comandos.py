# Vistas de la pestaña «Comandos» (IOT-05, paso 7; docs/casos_de_uso/iot/emitir_comando.md y cancelar_comando.md, «Cómo se aplica» y «Pantallas»; ``comandos``, ``cmdForm`` y
# ``ccan:<id>`` del prototipo). Las vistas solo orquestan (docs/patrones/abm.md, sección 1): validan la entrada, llaman al servicio y renderizan. Consultan el Gerente y el Agrónomo;
# el formulario de emisión y los botones «Cancelar» son solo de quien opera el IoT del invernadero (D-30: ningún botón lleva a un 403).
#
# Una sola URL para la emisión (``comandos/``): el formulario manda ``paso``. ``refrescar`` vuelve a dibujar SIN validar (con HTMX cambia solo ``#emision``; sin JavaScript se recarga
# la página); ``resumen`` verifica y muestra el resumen con sus advertencias (paso 6); ``emitir`` confirma (paso 8). Las validaciones corren solo al apretar un botón. La lista y sus
# filtros son un GET: con HTMX se reemplaza solo ``#lista-de-comandos``. La ventana de cancelar es un fragmento con HTMX y, sin JavaScript, esta misma página con la ventana abierta.

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.functions import Lower
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.contexto import contexto_del_modulo, errores_del_servicio, es_htmx
from iot.models import Actuador
from iot.servicios import comandos as api
from iot.servicios import reglas as api_reglas
from iot.servicios import sistemas as api_sistemas
from maestros.servicios import configuracion

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO
VENTANA_CANCELAR = "iot/comandos/_ventana_cancelar.html"
# Qué advertencias del resumen son informativas y cuáles de cuidado (prototipo: 6b y 6c en azul; el resto, en amarillo).
ADVERTENCIAS_INFORMATIVAS = ("reglas", "mismo_estado")
AVISO_DE_EMISION = "Comando {codigo} pendiente. El nodo lo retira en su próxima consulta; el resultado se verá en Monitoreo y en la ficha del actuador."


def _entero(texto):
    """El texto como entero positivo o ``None``."""
    texto = str(texto or "").strip()
    return int(texto) if texto.isascii() and texto.isdigit() else None


def _url_de_la_lista(invernadero_id):
    return f"{reverse('iot:comandos')}?{urlencode({'invernadero': invernadero_id})}"


def _filtros(request):
    """Los filtros de la lista (estado, actuador y origen); uno desconocido o vacío no filtra."""
    return api.FiltrosDeComandos(
        estado=request.GET.get("estado", "").strip(),
        actuador_id=_entero(request.GET.get("filtro_actuador")),
        origen=request.GET.get("origen", "").strip(),
    )


def _consulta_de_los_filtros(elegido, filtros):
    """El texto de consulta que conservan los enlaces de las páginas."""
    datos = {"invernadero": elegido.pk}
    if filtros.estado in api.ESTADOS_DEL_FILTRO:
        datos["estado"] = filtros.estado
    if filtros.actuador_id:
        datos["filtro_actuador"] = filtros.actuador_id
    if filtros.origen in api.ORIGENES_DEL_FILTRO:
        datos["origen"] = filtros.origen
    return urlencode(datos)


def _la_emision(request, elegido, ahora, errores=None, general=None):
    """Lo que dibuja el formulario de emisión (pasos 2 a 7): el actuador elegido, sus acciones, el resumen si ya se pidió y los errores. Solo para quien opera el invernadero."""
    params = request.POST if request.method == "POST" else request.GET
    actuador_id = _entero(params.get("actuador"))
    datos = api.DatosDeComando.desde_post(params)
    para = api.datos_para_emitir(request.user, elegido.pk, ahora, actuador_id)
    permitidas = {str(a.pk) for a in para.acciones}
    if str(datos.accion_id) not in permitidas:  # cambió el actuador: la acción elegida ya no es de su tipo
        datos = api.DatosDeComando(accion_id=None, valor="", descripcion=datos.descripcion)
    accion = next((a for a in para.acciones if str(a.pk) == str(datos.accion_id)), None)
    pendiente = None
    if para.elegido is not None and para.elegido.comando_pendiente is not None:
        fila, _ = api.comando_para_cancelar(request.user, para.elegido.comando_pendiente.pk, ahora)
        pendiente = fila
    return {
        "para": para,
        "datos": datos,
        "accion": accion,
        "actuador_id": actuador_id,
        "pendiente": pendiente,
        # Paso 4 de IOT-EMT-CMD: las reglas de actuación activas del actuador elegido (IOT-06), con su frase.
        "reglas": [{"pk": r.pk, "codigo": f"RGL-{r.pk}", "texto": api_reglas.texto_de_regla(r)} for r in para.reglas],
        "errores": errores or {},
        "general": general or [],
        "resumen": None,
    }


def _contexto_de_la_pagina(request, contexto, ahora, emision=None, **extra):
    """La página «Comandos»: el formulario (si opera), la lista con sus filtros y, si ``extra`` lo trae, la ventana abierta."""
    elegido = contexto["elegido"]
    contexto = contexto | {"sistema": None, "emision": None, "lista": None, **extra}
    if elegido is None:
        return contexto
    sistema = api_sistemas.sistema_del_invernadero(request.user, elegido.pk)
    contexto["sistema"] = sistema
    if sistema is None:
        return contexto
    if contexto["opera"]:
        config = configuracion.obtener()
        contexto["max_intentos"], contexto["intervalo"] = 1 + config.cant_reintentos_comando, config.segundos_intervalo_reintento
        contexto["emision"] = emision if emision is not None else _la_emision(request, elegido, ahora)
    return contexto | _la_lista(request, elegido, ahora)


def _la_lista(request, elegido, ahora):
    """La lista de comandos con sus filtros y su paginación (prototipo ``comandos``)."""
    filtros = _filtros(request)
    pagina = api.listar_comandos(request.user, elegido.pk, ahora, filtros, _entero(request.GET.get("pagina")) or 1)
    consulta = _consulta_de_los_filtros(elegido, filtros)
    return {
        "lista": pagina,
        "filtros": filtros,
        "hay_filtros": bool(filtros.estado or filtros.actuador_id or filtros.origen),
        "actuadores_del_filtro": list(
            Actuador.objects.filter(sistema__invernadero_id=elegido.pk).select_related("tipo_actuador").order_by(Lower("identificador_equipo"), "pk")
        ),
        "consulta_base": consulta,
        "url_de_la_pagina": f"{reverse('iot:comandos')}?{consulta}",
    }


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def comandos(request):
    """«Comandos» (IOT-EMT-CMD, IOT-CNL-CMD; ``comandos`` y ``cmdForm`` del prototipo): el formulario de emisión (solo para quien opera) y la lista de comandos del invernadero
    elegido. Un GET dibuja la página (con ``?actuador=`` desde la ficha, extensión 1b); con HTMX, solo la lista (filtros y páginas). Un POST es un paso del formulario."""
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])
    ahora = timezone.now()
    contexto = contexto_del_modulo(request, "comandos")
    elegido = contexto["elegido"]
    if request.method == "POST":
        if elegido is None:
            raise Http404("No existe ese invernadero.")
        if not contexto["opera"]:
            # Solo lo ve quien opera: ningún botón lleva acá, pero un POST escrito a mano no escribe nada.
            raise PermissionDenied("Solo consultás el IoT de este invernadero: lo opera su Agrónomo.")
        return _paso_del_formulario(request, contexto, ahora)
    if es_htmx(request) and elegido is not None:
        sistema = api_sistemas.sistema_del_invernadero(request.user, elegido.pk)
        if sistema is not None:
            return render(request, "iot/comandos/_lista.html", contexto | _la_lista(request, elegido, ahora) | {"sistema": sistema, "fuera_de_banda": True})
    return render(request, "iot/comandos/pagina.html", _contexto_de_la_pagina(request, contexto, ahora))


def _paso_del_formulario(request, contexto, ahora):
    """Un POST del formulario de emisión: ``refrescar`` (sin validar), ``resumen`` (paso 6) o ``emitir`` (paso 8, extensiones 8a y 8b)."""
    elegido = contexto["elegido"]
    paso = request.POST.get("paso", "refrescar")
    emision = _la_emision(request, elegido, ahora)
    errores, general = {}, []
    if paso in ("resumen", "emitir"):
        if emision["actuador_id"] is None:
            errores = {"actuador": ["Seleccioná un actuador."]}
        else:
            try:
                if paso == "resumen":
                    emision["resumen"] = api.resumen_de_comando(request.user, emision["actuador_id"], emision["datos"], ahora)
                else:
                    comando = api.emitir_comando(request.user, emision["actuador_id"], emision["datos"], ahora)
                    messages.success(request, AVISO_DE_EMISION.format(codigo=api.codigo_de(comando)))
                    return redirect(_url_de_la_lista(elegido.pk))
            except ValidationError as error:
                errores, general = errores_del_servicio(error)
    emision["errores"], emision["general"] = errores, general
    if es_htmx(request):
        # Con HTMX solo se vuelve a dibujar el formulario («#emision»); la página entera es el respaldo sin JavaScript.
        pagina = _contexto_de_la_pagina(request, contexto, ahora, emision=emision)
        return render(request, "iot/comandos/_emision.html", pagina)
    return render(request, "iot/comandos/pagina.html", _contexto_de_la_pagina(request, contexto, ahora, emision=emision))


# ---- cancelar (IOT-CNL-CMD) ----


def _destino_al_volver(request, comando):
    """A dónde vuelve quien cancela o cierra la ventana: la lista, el panel o la ficha del actuador, según de dónde vino (``volver``, de una lista cerrada)."""
    volver = request.POST.get("volver") or request.GET.get("volver") or ""
    invernadero_id = comando.actuador.sistema.invernadero_id
    if volver == "monitoreo":
        return f"{reverse('iot:monitoreo')}?{urlencode({'invernadero': invernadero_id})}"
    if volver == "ficha":
        return f"{reverse('iot:hardware_ficha', args=[comando.actuador_id])}?{urlencode({'invernadero': invernadero_id})}"
    return _url_de_la_lista(invernadero_id)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def comando_cancelar(request, comando_id):
    """Cancelar un comando pendiente (IOT-CNL-CMD; ventana ``ccan:<id>`` del prototipo), con confirmación previa. Abrirla (GET) no cambia nada; cancelar es un POST. Si el nodo puede
    estar ejecutándolo (regla 2) la ventana dice cuánto falta y no ofrece confirmar; si lo retiró entre la pantalla y la confirmación (regla 5), el servicio lo informa."""
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])
    ahora = timezone.now()
    fila, puede = api.comando_para_cancelar(request.user, comando_id, ahora)
    comando = fila.comando
    error = ""
    if request.method == "POST":
        try:
            api.cancelar_comando(request.user, comando_id, ahora)
        except ValidationError as rechazo:
            error = rechazo.messages[0]
            fila, puede = api.comando_para_cancelar(request.user, comando_id, ahora)
        else:
            messages.success(request, f"{fila.codigo} cancelado: el nodo no lo va a recibir y no se reintenta.")
            return redirect(_destino_al_volver(request, comando))
    ventana = {
        "fila": fila,
        "puede": puede,
        "error": error,
        "volver": request.POST.get("volver") or request.GET.get("volver") or "",
        "volver_url": _destino_al_volver(request, comando),
    }
    if es_htmx(request):
        return render(request, VENTANA_CANCELAR, ventana)
    # Sin JavaScript: la lista de comandos del invernadero del comando, con la ventana abierta.
    contexto = contexto_del_modulo(request, "comandos", comando.actuador.sistema.invernadero_id)
    return render(request, "iot/comandos/pagina.html", _contexto_de_la_pagina(request, contexto, ahora, plantilla_de_ventana=VENTANA_CANCELAR, **ventana))
