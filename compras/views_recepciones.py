# Pantallas de la recepción y del cierre con faltante (CMP-04; prototipo: ``tabRec``, ``VIEWS.c_rcp`` y ``VIEWS.c_flt``). Las vistas solo orquestan: leen lo que se envió, llaman al servicio
# (``compras/servicios/recepciones.py``) y renderizan; las reglas son de los servicios. Las dos pantallas con acciones funcionan **sin JavaScript** y sin validar mientras se escribe
# (.claude/rules/interfaz.md): el estado viaja en los campos del formulario y ``accion`` dice qué botón se apretó (como en «Generar la orden»): «revisar» muestra el resumen (paso 7) y «confirmar»
# registra (paso 9). Agregar un lote o un inconveniente a una línea es un botón que vuelve a dibujar el formulario con una fila más. Ningún botón lleva a un 403 (D-30).

from decimal import Decimal, InvalidOperation
from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from compras.errores import ErrorDeCompras
from compras.models import InconvenienteRecepcion, OrdenCompra
from compras.servicios import recepciones as api
from core.acceso import rol_requerido
from core.models import Usuario

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO
TIPOS = InconvenienteRecepcion.Tipo.choices
FILAS_INICIALES = 1


# ---- «Por recibir» (tabRec) ----


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def por_recibir(request):
    """«Compras» → «Por recibir» (CMP-REG-RCP paso 2, ``tabRec``): las entregas pendientes de los invernaderos a cargo del Agrónomo (todas, si es el Gerente), por proveedor e invernadero, de la
    entrega esperada más próxima a la más lejana, con la cantidad de líneas pendientes y los días de atraso. «Registrar recepción» lleva al formulario de esa entrega; una entrega con todo el
    destino inactivo se muestra sin el botón (extensión 4a1). No audita."""
    return render(request, "compras/recepciones/por_recibir.html", {"entregas": api.entregas_pendientes(request.user)})


# ---- lectura del formulario ----


def _decimal(texto):
    """``Decimal`` de lo que se escribió (acepta la coma decimal); ``None`` si no es un número."""
    try:
        return Decimal(texto.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _fecha(texto):
    """``date`` de ``AAAA-MM-DD``; ``None`` si no es una fecha."""
    try:
        return date.fromisoformat(texto.strip())
    except (ValueError, AttributeError):
        return None


def _entero(texto, minimo=FILAS_INICIALES, maximo=12):
    try:
        return max(minimo, min(maximo, int(texto)))
    except (TypeError, ValueError):
        return minimo


def _leer_recepcion(post, lineas):
    """Lee el formulario de la recepción: ``(lineas_recibidas, filas, errores)``. ``filas`` conserva lo escrito para volver a dibujar (``{detalle_id: {"lotes": [...], "incs": [...]}}``); ``errores`` son los
    textos de lo que no se pudo leer (un número o una fecha mal escritos), por línea. Una línea sin nada escrito no entra en la recepción."""
    recibidas, filas, errores = [], {}, {}
    for l in lineas:
        i = l.detalle.pk
        lotes = [
            {"cant": post.get(f"cant_{i}_{k}", ""), "venc": post.get(f"venc_{i}_{k}", "")}
            for k in range(_entero(post.get(f"lotes_{i}")))
        ]
        incs = [
            {"tipo": post.get(f"inc_tipo_{i}_{k}", ""), "cant": post.get(f"inc_cant_{i}_{k}", ""), "desc": post.get(f"inc_desc_{i}_{k}", "")}
            for k in range(_entero(post.get(f"incs_{i}"), 0))
        ]
        filas[i] = {"lotes": lotes, "incs": incs}
        partes, inconvenientes, malos = [], [], []
        for fila in lotes:
            if not fila["cant"].strip() and not fila["venc"].strip():
                continue
            cantidad = _decimal(fila["cant"]) if fila["cant"].strip() else None
            vencimiento = _fecha(fila["venc"]) if fila["venc"].strip() else None
            if cantidad is None:
                malos.append("Escribí la cantidad recibida como un número, por ejemplo 12 o 12,5.")
            elif fila["venc"].strip() and vencimiento is None:
                malos.append("Escribí el vencimiento como una fecha válida.")
            else:
                partes.append((cantidad, vencimiento))
        for fila in incs:
            if not (fila["tipo"] or fila["cant"].strip() or fila["desc"].strip()):
                continue
            cantidad = _decimal(fila["cant"]) if fila["cant"].strip() else Decimal("0")
            if cantidad is None:
                malos.append("Escribí la cantidad afectada como un número.")
            else:
                inconvenientes.append((fila["tipo"], cantidad, fila["desc"]))
        if malos:
            errores[i] = malos
        if partes or inconvenientes:
            recibidas.append(api.LineaRecibida(i, partes, inconvenientes))
    return recibidas, filas, errores


def _filas_para_dibujar(lineas, filas, por_linea=None):
    """Junta cada línea con lo escrito (o con las filas vacías iniciales) y con sus errores para la plantilla."""
    por_linea = por_linea or {}
    return [
        {
            "linea": l,
            "lotes": filas.get(l.detalle.pk, {}).get("lotes") or [{"cant": "", "venc": ""}] * FILAS_INICIALES,
            "incs": filas.get(l.detalle.pk, {}).get("incs") or [],
            "errores": por_linea.get(l.detalle.pk, []),
        }
        for l in lineas
    ]


def _como_error_por_linea(error):
    """Las líneas a las que se refiere un ``ErrorDeCompras`` (por ``linea`` o ``lineas``), para marcarlas en el formulario."""
    ids = list(error.datos.get("lineas", []))
    if "linea" in error.datos:
        ids.append(error.datos["linea"])
    return {i if isinstance(i, int) else i[0] for i in ids}


def _hidden(post):
    """Todo lo que se envió, para repetirlo oculto en el resumen y que «Confirmar» registre exactamente lo mismo (sin el token y el botón)."""
    return [(k, v) for k in post for v in post.getlist(k) if k not in ("csrfmiddlewaretoken", "accion")]


# ---- registrar la recepción (CMP-REG-RCP) ----


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
def recepcion_nueva(request, orden_id):
    """«Registrar recepción» (CMP-REG-RCP pasos 3 a 11, ``VIEWS.c_rcp``): la entrega se elige con ``?proveedor=&invernadero=`` (sin eso, la primera de la orden). GET: las líneas pendientes con lo pedido, lo
    ya recibido y lo que falta; por cada una, uno o más lotes (cantidad y vencimiento) y los inconvenientes. POST con ``revisar``: el resumen del paso 7; ``confirmar``: registra (paso 9) y lleva a la
    ficha de la orden, con el aviso de las líneas que quedaron pendientes y el camino a «Cerrar con faltante» (extensión 11a); ``mas_lote:<id>`` y ``mas_inc:<id>`` suman una fila a esa línea;
    ``editar`` vuelve al formulario. Un error de negocio (7a, 7b, 7c, 7e, 9a, 9b…) vuelve al formulario con lo escrito. El Agrónomo de otro destino es 403 y una orden inexistente, 404."""
    orden = get_object_or_404(OrdenCompra, pk=orden_id)
    entregas = [e for e in api.entregas_pendientes(request.user) if e.orden.pk == orden.pk]
    datos = request.POST if request.method == "POST" else request.GET
    try:
        proveedor_id = int(datos.get("proveedor") or (entregas[0].proveedor.pk if entregas else 0))
        invernadero_id = int(datos.get("invernadero") or (entregas[0].invernadero.pk if entregas else 0))
    except ValueError as error:
        raise Http404("Entrega inexistente.") from error
    if not entregas:
        if not OrdenCompra.objects.en_alcance_de(request.user).filter(pk=orden.pk).exists():
            raise PermissionDenied("Esa orden no tiene destinos a tu cargo.")
        return render(request, "compras/recepciones/recepcion_vacia.html", {"orden": orden})
    lineas = api.lineas_a_recibir(request.user, orden.pk, proveedor_id, invernadero_id)
    if not lineas:
        messages.info(request, "Esa entrega ya no tiene líneas pendientes.")
        return redirect("compras:orden_ficha", orden_id=orden.pk)
    entrega = next((e for e in entregas if e.proveedor.pk == proveedor_id and e.invernadero.pk == invernadero_id), None)
    contexto = {"orden": orden, "entregas": entregas, "proveedor": lineas[0].detalle.proveedor, "invernadero": lineas[0].existencia.invernadero, "entrega": entrega, "tipos": TIPOS, "errores": []}

    if request.method != "POST":
        return render(request, "compras/recepciones/recepcion_form.html", {**contexto, "lineas": _filas_para_dibujar(lineas, {}), "observaciones": ""})

    accion = request.POST.get("accion", "")
    recibidas, filas, errores_de_lectura = _leer_recepcion(request.POST, lineas)
    observaciones = request.POST.get("observaciones", "")
    if accion.startswith("mas_lote:") or accion.startswith("mas_inc:"):
        clave, _, i = accion.partition(":")
        filas.setdefault(int(i), {"lotes": [], "incs": []})
        lista = filas[int(i)]["lotes" if clave == "mas_lote" else "incs"]
        lista.append({"cant": "", "venc": ""} if clave == "mas_lote" else {"tipo": "", "cant": "", "desc": ""})
        return render(request, "compras/recepciones/recepcion_form.html", {**contexto, "lineas": _filas_para_dibujar(lineas, filas), "observaciones": observaciones, "agregada": int(i)})
    if accion == "editar" or accion not in ("revisar", "confirmar"):
        return render(request, "compras/recepciones/recepcion_form.html", {**contexto, "lineas": _filas_para_dibujar(lineas, filas), "observaciones": observaciones})

    def volver(mensajes, por_linea):
        return render(
            request,
            "compras/recepciones/recepcion_form.html",
            {**contexto, "lineas": _filas_para_dibujar(lineas, filas, por_linea), "observaciones": observaciones, "errores": mensajes},
        )

    if errores_de_lectura:
        return volver(["Revisá lo marcado: hay datos que no se pudieron leer."], errores_de_lectura)
    datos_de_recepcion = api.DatosDeRecepcion(orden.pk, proveedor_id, invernadero_id, recibidas, observaciones)
    try:
        if accion == "revisar":
            resumen = api.resumir_recepcion(request.user, datos_de_recepcion)
            return render(request, "compras/recepciones/recepcion_resumen.html", {**contexto, "resumen": resumen, "estado_texto": OrdenCompra.Estado(resumen.estado_orden).label, "campos": _hidden(request.POST)})
        recepcion = api.registrar_recepcion(request.user, datos_de_recepcion)
    except ErrorDeCompras as error:
        if error.codigo in ("orden_no_recibible", "destino_inactivo"):  # 9b y la orden ya no se recibe: se vuelve a la ficha, que muestra cómo quedó
            messages.error(request, error.mensaje)
            return redirect("compras:orden_ficha", orden_id=orden.pk)
        return volver([error.mensaje], {i: [error.mensaje] for i in _como_error_por_linea(error)})
    messages.success(request, f"Registramos la recepción {recepcion}. La orden quedó {recepcion.orden.get_estado_orden_compra_display().lower()}.")
    pendientes = api.lineas_pendientes_de_cierre(request.user, recepcion_id=recepcion.pk)
    if pendientes:  # extensión 11a: se ofrece cerrar con faltante lo que quedó pendiente
        messages.info(
            request,
            format_html(
                "Quedó pendiente {} de la recepción. Si el proveedor no va a entregar el resto, <a href=\"{}\">cerrala con faltante</a>.",
                ", ".join(f"{l.insumo.nombre_insumo} (faltan {l.falta})" for l in pendientes),
                reverse("compras:cierre_faltante", args=[orden.pk]) + f"?recepcion={recepcion.pk}",
            ),
        )
    return redirect("compras:orden_ficha", orden_id=orden.pk)


# ---- cerrar con faltante (CMP-CRR-FLT) ----


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
def cierre_faltante(request, orden_id):
    """«Cerrar con faltante» (CMP-CRR-FLT pasos 1 a 8, ``VIEWS.c_flt``): las líneas pendientes de la orden (con ``?recepcion=``, solo las de esa recepción: extensión 2a), cada una con su casilla y su
    motivo. POST con ``revisar``: el resumen del paso 5; ``confirmar``: cierra (paso 7) y lleva a la ficha; ``editar`` vuelve a la lista. Un error de negocio (sin líneas, motivo, 7a) vuelve a la lista con lo
    elegido. Cerrar no se deshace: el resumen lo dice antes de confirmar. El Agrónomo ve solo lo de sus invernaderos."""
    orden = get_object_or_404(OrdenCompra, pk=orden_id)
    recepcion_id = request.GET.get("recepcion") or request.POST.get("recepcion") or None
    try:
        recepcion_id = int(recepcion_id) if recepcion_id else None
    except ValueError as error:
        raise Http404("Recepción inexistente.") from error
    lineas = api.lineas_pendientes_de_cierre(request.user, orden_id=orden.pk, recepcion_id=recepcion_id)
    if not lineas:
        if not OrdenCompra.objects.en_alcance_de(request.user).filter(pk=orden.pk).exists():
            raise PermissionDenied("Esa orden no tiene destinos a tu cargo.")
        messages.info(request, "Esta orden no tiene líneas pendientes para cerrar.")
        return redirect("compras:orden_ficha", orden_id=orden.pk)
    contexto = {"orden": orden, "recepcion_id": recepcion_id}
    elegidas = {int(i) for i in request.POST.getlist("linea") if i.isdigit()} if request.method == "POST" else set()
    motivos = {l.detalle.pk: request.POST.get(f"motivo_{l.detalle.pk}", "") for l in lineas} if request.method == "POST" else {}

    def dibujar(errores=None, por_linea=None):
        return render(
            request,
            "compras/recepciones/cierre_form.html",
            {**contexto, "lineas": [{"linea": l, "elegida": l.detalle.pk in elegidas, "motivo": motivos.get(l.detalle.pk, ""), "errores": (por_linea or {}).get(l.detalle.pk, [])} for l in lineas], "errores": errores or []},
        )

    accion = request.POST.get("accion", "") if request.method == "POST" else ""
    if accion not in ("revisar", "confirmar"):
        return dibujar()
    pedido = [(i, motivos.get(i, "")) for i in sorted(elegidas)]
    try:
        if accion == "revisar":
            resumen = api.resumir_cierre(request.user, pedido)
            return render(request, "compras/recepciones/cierre_resumen.html", {**contexto, "resumen": resumen, "estado_texto": OrdenCompra.Estado(resumen.estados_de_ordenes[orden.pk]).label, "campos": _hidden(request.POST)})
        api.cerrar_con_faltante(request.user, pedido)
    except ErrorDeCompras as error:
        if error.codigo == "linea_no_pendiente":  # 7a: se vuelve a la lista de lo que sigue pendiente
            messages.error(request, error.mensaje)
            return redirect("compras:cierre_faltante", orden_id=orden.pk)
        return dibujar([error.mensaje], {i: [error.mensaje] for i in _como_error_por_linea(error)})
    messages.success(request, f"Cerramos {len(pedido)} línea{'s' if len(pedido) != 1 else ''} con faltante. La orden quedó {OrdenCompra.objects.get(pk=orden.pk).get_estado_orden_compra_display().lower()}.")
    return redirect("compras:orden_ficha", orden_id=orden.pk)
