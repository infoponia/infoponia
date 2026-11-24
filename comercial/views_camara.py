# Vista de la merma en cámara de `comercial` (COM-04b, PROD-REG-MRM sobre una partida; docs/casos_de_uso/produccion/merma.md, «Cómo se aplica en la ronda «Comercial 1»», «Pantallas»).
# Las vistas SOLO orquestan: arman los datos del pedido, llaman al servicio (`comercial/servicios/merma_camara.py`) y renderizan; todas las reglas son del servicio. Sin JavaScript
# funciona igual: cada pantalla es una página, «Continuar» (dentro de `<noscript>`) redibuja y «Ver resumen» valida y calcula; con HTMX solo se redibuja el bloque que cambia y NUNCA se
# valida ni se calcula al escribir (`.claude/rules/interfaz.md`). La pantalla no está en el prototipo comercial: se arma con el mismo esquema de la merma de PRD-03 (D-61).
# Quién: el Agrónomo a cargo y el Capataz asignado (el Gerente y los demás, 403: `rol_requerido`). El Capataz no recibe precios ni clientes: el resumen solo nombra contratos.

import hashlib
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from comercial.servicios import merma_camara
from comercial.servicios.merma_camara import DatosDeMermaEnCamara
from core.acceso import rol_requerido
from core.models import Usuario, rol_de

AGRONOMO, CAPATAZ = Usuario.Rol.AGRONOMO, Usuario.Rol.CAPATAZ
CAMPOS_DE_LA_FIRMA = ("invernadero", "partida", "cantidad", "causa", "descripcion")


def _es_htmx(request):
    """Un pedido de HTMX (redibuja solo el formulario)."""
    return request.headers.get("HX-Request") == "true"


def _entero(texto):
    """El entero de un texto, o `None` si está vacío o no es un número."""
    try:
        return int(str(texto or "").strip())
    except ValueError:
        return None


def _firma(datos):
    """La marca de lo que se calculó en el resumen: si la persona cambia un dato después de verlo, «Confirmar» no escribe y vuelve a mostrar el resumen."""
    crudo = json.dumps({c: (datos.get(c) or "").strip() for c in CAMPOS_DE_LA_FIRMA}, sort_keys=True)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:24]


def _errores_por_campo(error):
    """`{campo: mensaje}` de un `ValidationError` (el primer mensaje de cada campo); sin campo, `general`."""
    if hasattr(error, "error_dict"):
        return {campo: lista[0].message for campo, lista in error.error_dict.items()}
    return {"general": error.messages[0]}


def _datos(datos, con_visto):
    """`DatosDeMermaEnCamara` desde el formulario. `con_visto`: lo que la persona vio (`visto_disponible`), que solo «Confirmar» compara (extensión 10d)."""
    return DatosDeMermaEnCamara(
        partida_id=_entero(datos.get("partida")),
        cantidad=(datos.get("cantidad") or "").strip(),
        causa=datos.get("causa", ""),
        descripcion=datos.get("descripcion", ""),
        visto_disponible=_entero(datos.get("visto_disponible")) if con_visto and "visto_disponible" in datos else None,
    )


def _volver(request, invernadero_id):
    """Adónde se vuelve tras registrar: el Capataz, a su bandeja; el Agrónomo, a la pestaña «Cámara» de su invernadero."""
    if rol_de(request.user) == CAPATAZ:
        return redirect("produccion:bandeja")
    return redirect(f"{reverse('maestros:invernadero', args=[invernadero_id])}?pestana=camara")


@rol_requerido(AGRONOMO, CAPATAZ)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def merma(request):
    """«Registrar merma en cámara»: invernadero → partida → cantidad, causa y descripción → resumen → confirmar. Cambiar el invernadero o la partida («Continuar» sin JavaScript, o HTMX)
    solo redibuja lo que depende de ello, sin validar. «Ver resumen» valida y no escribe; «Confirmar» vuelve a verificar bajo bloqueo (extensión 10d) y escribe. Sin partidas
    disponibles (extensión 4b) el formulario lo dice."""
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    invernaderos = merma_camara.invernaderos_con_merma_en_camara(request.user)
    invernadero_id = _entero(datos.get("invernadero"))
    if invernadero_id not in {i.pk for i in invernaderos}:
        invernadero_id = None
    partidas, partida_id = [], None
    if invernadero_id:
        partidas = merma_camara.partidas_con_merma_posible(request.user, invernadero_id)
        pedida = _entero(datos.get("partida"))
        partida_id = pedida if pedida in {p.partida_id for p in partidas} else None
    errores, resumen, firma, cambio_la_firma = {}, None, "", False
    if accion in ("calcular", "confirmar") and partida_id:
        firma = _firma(datos)
        try:
            if accion == "confirmar" and datos.get("firma") == firma:
                resultado = merma_camara.registrar_merma_en_camara(request.user, _datos(datos, con_visto=True))
                messages.success(request, f"La merma quedó registrada: {resultado.merma.descripcion_evento}")
                return _volver(request, invernadero_id)
            cambio_la_firma = accion == "confirmar"
            resumen = merma_camara.resumen_de_merma_en_camara(request.user, _datos(datos, con_visto=False))
        except ValidationError as error:
            errores, firma, resumen = _errores_por_campo(error), "", None
        except PermissionDenied:
            return redirect("comercial:merma_camara")
    contexto = {
        "invernaderos": invernaderos,
        "invernadero_id": invernadero_id,
        "partidas": partidas,
        "partida_id": partida_id,
        "valores": dict(datos.items()),
        "errores": errores,
        "causas": merma_camara.causas_de_camara(),
        "resumen": resumen,
        "firma": firma,
        "cambio_la_firma": cambio_la_firma,
        "es_capataz": rol_de(request.user) == CAPATAZ,
    }
    plantilla = "comercial/camara/_merma_formulario.html" if _es_htmx(request) else "comercial/camara/merma.html"
    return render(request, plantilla, contexto)
