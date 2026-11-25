# Pantalla de «Corregir una recepción» (CMP-06; prototipo: ``VIEWS.c_cor``). La vista solo orquesta: lee lo que se envió, llama al servicio (``compras/servicios/correcciones.py``) y renderiza; las reglas son
# del servicio. Funciona **sin JavaScript** y sin validar mientras se escribe (.claude/rules/interfaz.md): «Ver resumen» muestra el paso 7 y «Confirmar corrección» registra el paso 9. Lo que el prototipo
# traía de más o de menos se corrige según el caso de uso (D-61): la observación es opcional (el prototipo la exigía como «motivo»), hay un resumen antes de confirmar (el prototipo registraba directo), se
# muestran los lotes de cada línea y lo que cada uno permite corregir, y las líneas que no se pueden corregir dicen por qué (cerrada con faltante, lote sin stock). Ningún botón lleva a un 403 (D-30).

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from compras.errores import ErrorDeCompras
from compras.models import OrdenCompra
from compras.servicios import correcciones as api
from compras.views_recepciones import _como_error_por_linea, _hidden
from core.acceso import rol_requerido
from core.models import Usuario

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO
MOTIVOS = {
    "cerrada_con_faltante": "Está cerrada con faltante: no se corrige.",
    "sin_stock_en_el_lote": "El lote ya no conserva nada: lo restante se resuelve con un ajuste de stock.",
}


def _decimal(texto):
    """``Decimal`` de lo que se escribió (acepta la coma decimal); ``None`` si no es un número."""
    try:
        return Decimal(texto.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _leer(post, lineas):
    """Lee el formulario: ``(pedidas, escritas, errores)``. ``pedidas`` es ``[(detalle_recepcion_id, Decimal)]`` de las líneas con algo escrito; ``escritas`` conserva el texto para volver a dibujar; ``errores``
    marca lo que no es un número (por línea)."""
    pedidas, escritas, errores = [], {}, {}
    for l in lineas:
        i = l.detalle_recepcion.pk
        texto = post.get(f"cant_{i}", "").strip()
        escritas[i] = post.get(f"cant_{i}", "")
        if not texto:
            continue
        numero = _decimal(texto)
        if numero is None:
            errores[i] = "Escribí un número."
        else:
            pedidas.append((i, numero))
    return pedidas, escritas, errores


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
def correccion_nueva(request, orden_id):
    """«Corregir una recepción» (CMP-COR-RCP pasos 1 a 11, ``VIEWS.c_cor``), desde la ficha de la orden. GET: las recepciones corregibles de la orden (se elige con ``?recepcion=``; sin eso, la primera) y las
    líneas de la elegida con su lote, lo recibido, lo máximo corregible y un campo para la cantidad a descontar; sin recepciones corregibles, el aviso de la extensión 2a. POST con ``revisar``: el resumen del
    paso 7 (con el asiento inverso); ``confirmar``: registra (paso 9) y vuelve a la ficha de la orden; ``editar``: vuelve al formulario. Un error de negocio vuelve al formulario con lo escrito (5a, 5b, 9a); un
    proveedor ya pagado (c) lleva a la ficha con el aviso. El Agrónomo ve solo lo de sus invernaderos."""
    orden = get_object_or_404(OrdenCompra, pk=orden_id)
    recepciones = api.recepciones_corregibles(request.user, orden.pk)
    if not recepciones:
        if not OrdenCompra.objects.en_alcance_de(request.user).filter(pk=orden.pk).exists():
            raise PermissionDenied("Esa orden no tiene destinos a tu cargo.")
        if request.method == "POST":  # extensión 9a: entre el resumen y la confirmación el proveedor se pagó o el lote cambió; la ficha muestra cómo quedó
            messages.error(request, "Ya no hay recepciones para corregir: el proveedor ya fue pagado o no queda nada recibido. No se registró ningún cambio.")
            return redirect("compras:orden_ficha", orden_id=orden.pk)
        return render(request, "compras/correcciones/vacia.html", {"orden": orden})
    elegida = request.POST.get("recepcion") or request.GET.get("recepcion") or ""
    actual = next((r for r in recepciones if str(r.recepcion.pk) == elegida), recepciones[0])
    lineas = actual.lineas
    contexto = {"orden": orden, "recepciones": recepciones, "actual": actual, "motivos": MOTIVOS, "errores": []}

    def filas(escritas, por_linea=None):
        return [{"linea": l, "texto": escritas.get(l.detalle_recepcion.pk, ""), "error": (por_linea or {}).get(l.detalle_recepcion.pk, "")} for l in lineas]

    if request.method != "POST":
        return render(request, "compras/correcciones/formulario.html", {**contexto, "filas": filas({}), "observacion": ""})

    accion = request.POST.get("accion", "")
    pedidas, escritas, errores_de_lectura = _leer(request.POST, lineas)
    observacion = request.POST.get("observacion", "")
    if accion not in ("revisar", "confirmar"):
        return render(request, "compras/correcciones/formulario.html", {**contexto, "filas": filas(escritas), "observacion": observacion})

    def volver(mensajes, por_linea):
        return render(request, "compras/correcciones/formulario.html", {**contexto, "filas": filas(escritas, por_linea), "observacion": observacion, "errores": mensajes})

    if errores_de_lectura:
        return volver(["Revisá lo marcado: hay cantidades que no se pudieron leer."], errores_de_lectura)
    try:
        if accion == "revisar":
            resumen = api.resumir_correccion(request.user, actual.recepcion.pk, pedidas)
            return render(request, "compras/correcciones/resumen.html", {**contexto, "resumen": resumen, "estado_texto": OrdenCompra.Estado(resumen.estado_orden).label, "campos": _hidden(request.POST)})
        correccion = api.registrar_correccion(request.user, actual.recepcion.pk, pedidas, observacion)
    except ErrorDeCompras as error:
        if error.codigo == "pago_registrado":  # precondición c: ya no se corrige; la ficha de la orden muestra el pago
            messages.error(request, error.mensaje)
            return redirect("compras:orden_ficha", orden_id=orden.pk)
        return volver([error.mensaje], {i: error.mensaje for i in _como_error_por_linea(error)})
    messages.success(
        request,
        f"Registramos la corrección {correccion} de la recepción {actual.recepcion}. La orden quedó {OrdenCompra.objects.get(pk=orden.pk).get_estado_orden_compra_display().lower()}.",
    )
    return redirect("compras:orden_ficha", orden_id=orden.pk)
