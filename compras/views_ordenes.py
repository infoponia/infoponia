# Pantallas de «Compras» → «Órdenes» (CMP-03; prototipo: ``tabOdc``, ``VIEWS.c_odc``, ``VIEWS.c_gen`` y ``VIEWS.c_apr``). Las vistas solo orquestan: leen lo que se envió, llaman al servicio
# (``compras/servicios/ordenes.py``) y renderizan; las reglas son de los servicios. El Agrónomo del pedido compara las cotizaciones y genera la orden; el Gerente revisa, aprueba o rechaza;
# los dos consultan. Ningún botón lleva a un 403 (D-30): lo que quien mira no puede hacer no se muestra.
#
# Las dos pantallas con acciones funcionan **sin JavaScript** y sin validar mientras se escribe (.claude/rules/interfaz.md): el estado viaja en los campos del formulario y ``accion`` dice
# qué botón se apretó, como en «Nuevo pedido». «Generar» elige cotizaciones **completas** con un botón cada una (pasos 5 y 6, extensiones 5a y 6a) y la cobertura se vuelve a calcular con
# cada elección; «revisar» muestra el resumen del paso 9 y «confirmar» registra (paso 11). «Resolver» tiene dos caminos, aprobar (pasos 5 a 8) y rechazar (5a), los dos con su resumen antes de confirmar.

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from compras.errores import ErrorDeCompras
from compras.models import OrdenCompra, Proveedor
from compras.servicios import ordenes as api
from core.acceso import rol_requerido
from core.models import Agronomo, Usuario
from maestros.models import Invernadero

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO
CONTADOR = Usuario.Rol.CONTADOR


# ---- lista y ficha (CMP-CNS-ODC) ----


@rol_requerido(GERENTE, AGRONOMO, CONTADOR)
@require_safe
def ordenes(request):
    """«Compras» → «Órdenes» (CMP-CNS-ODC regla 3, ``tabOdc``): una fila por orden, de la más reciente a la más antigua, con el atajo «Por aprobar» y los filtros de la regla 2 (estado, proveedor,
    invernadero de destino, rango de fechas de emisión y, solo para el Gerente, Agrónomo del pedido). Los filtros se envían con «Filtrar»: sin JavaScript funciona igual. No audita (regla 10)."""
    entrada = request.GET
    filtros = {
        "estado": entrada.get("estado", ""),
        "proveedor_id": entrada.get("proveedor", ""),
        "invernadero_id": entrada.get("invernadero", ""),
        "desde": entrada.get("desde", ""),
        "hasta": entrada.get("hasta", ""),
        "agronomo_id": entrada.get("agronomo", ""),
        "atajo": entrada.get("atajo", ""),
    }
    es_gerente = request.user.rol == GERENTE
    es_contador = request.user.rol == CONTADOR
    filas = api.consultar_ordenes(request.user, filtros)
    return render(
        request,
        "compras/ordenes/lista.html",
        {
            "filas": filas,
            "filtros": dict(entrada.items()),
            "hay_filtros": any(entrada.get(k) for k in ("estado", "proveedor", "invernadero", "desde", "hasta", "agronomo")),
            "atajo": filtros["atajo"] if filtros["atajo"] in api.ATAJOS else "",
            "por_aprobar": len(api.consultar_ordenes(request.user, {"atajo": api.ATAJO_POR_APROBAR})),
            "por_recibir": len(api.consultar_ordenes(request.user, {"atajo": api.ATAJO_POR_RECIBIR})),
            "con_reclamo": len(api.consultar_ordenes(request.user, {"atajo": api.ATAJO_CON_RECLAMO})),
            "con_pago": len(api.consultar_ordenes(request.user, {"atajo": api.ATAJO_CON_PAGO})),
            "estados": OrdenCompra.Estado.choices,
            # El Contador ve todas las órdenes: sus filtros ofrecen todos los invernaderos y proveedores (solo nombres), que su alcance de ``en_alcance_de`` no le da.
            "invernaderos": (Invernadero.objects.all() if es_contador else Invernadero.objects.en_alcance_de(request.user)).order_by(Lower("nombre_invernadero"), "id"),
            "proveedores": (Proveedor.objects.all() if es_contador else Proveedor.objects.en_alcance_de(request.user)).order_by(Lower("razon_social_proveedor"), "id"),
            "agronomos": Agronomo.objects.order_by(Lower("last_name"), "id") if es_gerente else [],
            "es_gerente": es_gerente,
            "es_contador": es_contador,
        },
    )


@rol_requerido(GERENTE, AGRONOMO, CONTADOR)
@require_safe
def orden_ficha(request, orden_id):
    """Ficha de la orden (CMP-CNS-ODC reglas 4, 5 y 8, ``VIEWS.c_odc``): el pedido de origen, el monto, el estado, la resolución y las líneas por proveedor e invernadero. El Gerente ve
    «Revisar y decidir» si está pendiente. Una orden fuera del alcance es 403 y una inexistente, 404 (D-28)."""
    ficha = api.ficha_de_orden(request.user, orden_id)
    return render(request, "compras/ordenes/ficha.html", {"ficha": ficha, "orden": ficha.orden, "es_gerente": request.user.rol == GERENTE, "es_contador": request.user.rol == CONTADOR})


# ---- generar (CMP-GNR-ODC) ----


def _ids_de(texto):
    """Los ids de cotización que llegaron del formulario, sin repetir y en el orden en que llegaron."""
    return list(dict.fromkeys(valor for valor in texto if valor))


def _dibujar_generacion(request, comparacion, elegidas, observaciones, *, errores=None):
    """Dibuja «Comparar cotizaciones y generar orden» con lo elegido hasta ahora. Se normaliza la selección: solo quedan las cotizaciones elegibles (pasos 5 y 6)."""
    eleccion = api.cobertura_de_la_eleccion(comparacion, elegidas)
    return render(
        request,
        "compras/ordenes/generar.html",
        {
            "pedido": comparacion.pedido,
            "comparacion": comparacion,
            "eleccion": eleccion,
            "elegidas_ids": [c.cotizacion.pk for c in eleccion.elegidas],
            "observaciones": observaciones,
            "errores": errores or [],
        },
    )


@rol_requerido(AGRONOMO)
@never_cache
def pedido_generar_orden(request, pedido_id):
    """«Comparar cotizaciones y generar orden» (CMP-GNR-ODC pasos 3 a 13, ``VIEWS.c_gen``). GET: las dos vistas de comparación, sin nada elegido. POST con ``elegir:<id>`` o ``quitar:<id>``: agrega o
    quita **una cotización completa** (pasos 5 y 6, extensiones 5a y 6a) y vuelve a calcular la cobertura; con ``revisar``, muestra el resumen del paso 9 (extensión 8a si algún detalle no queda
    cubierto); con ``confirmar``, genera la orden (paso 11) y lleva a su ficha; con ``editar`` (extensión 10a), vuelve a la elección. Si el pedido ya no se puede resolver (1a1, 11a), se vuelve a su
    ficha con el motivo. Solo el Agrónomo del pedido; otro es 403 y un pedido inexistente, 404."""
    pedido_url = redirect("compras:pedido_ficha", pedido_id=pedido_id)
    try:
        comparacion = api.comparacion(request.user, pedido_id)
    except ErrorDeCompras as error:  # 1a1 y precondición b
        messages.error(request, error.mensaje)
        return pedido_url
    if request.method != "POST":
        return _dibujar_generacion(request, comparacion, [], "")

    elegidas = _ids_de(request.POST.getlist("cotizacion"))
    observaciones = request.POST.get("observaciones", "")
    accion = request.POST.get("accion", "")
    if accion.startswith("elegir:"):
        elegidas = _ids_de([*elegidas, accion.partition(":")[2]])
    elif accion.startswith("quitar:"):
        elegidas = [i for i in elegidas if i != accion.partition(":")[2]]
    elif accion in ("revisar", "confirmar"):
        ids = [c.cotizacion.pk for c in api.cobertura_de_la_eleccion(comparacion, elegidas).elegidas]
        try:
            if accion == "confirmar":
                orden = api.generar_orden(request.user, pedido_id, ids, observaciones)
            else:
                resumen = api.resumir_orden(request.user, pedido_id, ids, observaciones)
        except ErrorDeCompras as error:
            if error.codigo == "pedido_no_en_cotizacion":  # 11a
                messages.error(request, error.mensaje)
                return pedido_url
            messages.error(request, error.mensaje)  # 8a, 11b y sin elegir: se vuelve a la elección con lo que sigue siendo válido
            return _dibujar_generacion(request, comparacion, elegidas, observaciones, errores=[error.mensaje])
        if accion == "confirmar":
            messages.success(request, f"Generamos la orden {orden}. Quedó pendiente de aprobación del Gerente.")
            if orden.sin_gerente_activo:  # 12b
                messages.info(request, "No hay un Gerente activo: la orden queda pendiente hasta que haya uno.")
            return redirect("compras:orden_ficha", orden_id=orden.pk)
        return render(request, "compras/ordenes/generar_resumen.html", {"pedido": comparacion.pedido, "resumen": resumen, "elegidas_ids": ids, "observaciones": resumen.observaciones})
    return _dibujar_generacion(request, comparacion, elegidas, observaciones)


# ---- aprobar y rechazar (CMP-APR-ODC) ----


def _a_la_ficha(request, error, orden_id):
    """Extensiones 1a1, 8a y 5a.5a: la orden ya no está pendiente (u otra cosa la cambió): se informa y se vuelve a la ficha, que muestra la decisión tomada."""
    messages.error(request, error.mensaje)
    return redirect("compras:orden_ficha", orden_id=orden_id)


def _marcar_lo_afectado(detalle):
    """Deja en cada línea y cotización de la orden por qué no se puede aprobar (4a, 4b y P1), para que la plantilla lo muestre donde corresponde."""
    por_linea, por_cotizacion = dict(detalle.lineas_afectadas), dict(detalle.cotizaciones_afectadas)
    for proveedor in detalle.proveedores:
        proveedor.cotizacion.motivo_afectada = por_cotizacion.get(proveedor.cotizacion.pk)
        for linea in proveedor.lineas:
            linea.motivo_destino = por_linea.get(linea.pk)


@rol_requerido(GERENTE)
@never_cache
def orden_resolver(request, orden_id):
    """«Revisar y decidir» (CMP-APR-ODC, ``VIEWS.c_apr``). GET: la información para decidir (paso 4) y, si la orden no se puede aprobar (4a, 4b, P1), por qué y el motivo propuesto para rechazar. POST con
    ``revisar_aprobacion``: el resumen del paso 6; ``confirmar_aprobacion``: aprueba (paso 8). ``revisar_rechazo``: pide el motivo (5a.1 y 5b) y muestra el resumen 5a.3; ``confirmar_rechazo``: rechaza
    (5a.5). ``editar`` vuelve a la información sin cambiar nada. Si al registrar la orden ya no está pendiente (8a), se informa la decisión tomada y se vuelve a la ficha. Solo el Gerente."""
    es_envio = request.method == "POST"
    accion = request.POST.get("accion", "") if es_envio else ""
    motivo = request.POST.get("motivo", "") if es_envio else None
    errores_del_motivo = []
    try:
        if accion == "confirmar_aprobacion":
            orden = api.aprobar_orden(request.user, orden_id)
            messages.success(request, f"Orden {orden} aprobada. Avisamos al Agrónomo y a cada proveedor.")
            return redirect("compras:orden_ficha", orden_id=orden.pk)
        if accion == "confirmar_rechazo":
            orden = api.rechazar_orden(request.user, orden_id, motivo)
            messages.success(request, f"Orden {orden} rechazada. Avisamos al Agrónomo y a cada proveedor.")
            return redirect("compras:orden_ficha", orden_id=orden.pk)
        if accion == "revisar_aprobacion":
            return render(request, "compras/ordenes/resumen_aprobacion.html", {"resumen": api.resumir_aprobacion(request.user, orden_id)})
        if accion == "revisar_rechazo":
            return render(request, "compras/ordenes/resumen_rechazo.html", {"resumen": api.resumir_rechazo(request.user, orden_id, motivo)})
        detalle = api.detalle_para_resolver(request.user, orden_id)
    except ValidationError as error:  # 5b: el motivo es obligatorio
        errores_del_motivo = [m for lista in error.message_dict.values() for m in lista]
        detalle = None
    except ErrorDeCompras as error:
        if error.codigo == "orden_no_pendiente":
            return _a_la_ficha(request, error, orden_id)
        messages.error(request, error.mensaje)  # 4a, 4b y 8b: se vuelve al paso 4, donde se muestra qué lo impide
        return redirect("compras:orden_resolver", orden_id=orden_id)
    if detalle is None:
        try:
            detalle = api.detalle_para_resolver(request.user, orden_id)
        except ErrorDeCompras as error:
            return _a_la_ficha(request, error, orden_id)
    if motivo is None:
        motivo = detalle.motivo_propuesto  # P1: el Sistema propone el motivo cuando una cotización venció o su proveedor está inactivo; el Gerente lo puede editar
    _marcar_lo_afectado(detalle)
    return render(request, "compras/ordenes/resolver.html", {"detalle": detalle, "orden": detalle.orden, "motivo": motivo, "errores_del_motivo": errores_del_motivo})
