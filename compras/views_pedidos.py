# Pantallas de «Compras» → «Pedidos» (CMP-02a; prototipo: ``tabPed``, ``VIEWS.c_ped`` y ``VIEWS.c_pednew``). Las vistas solo orquestan: arman los datos del formulario,
# llaman al servicio (``compras/servicios/pedidos.py``) y renderizan; las reglas son de los servicios. Gerente y Agrónomo consultan (lista y ficha: el Gerente en
# modo consulta); solo el Agrónomo arma pedidos. Ningún botón lleva a un 403 (D-30): lo que quien mira no puede hacer no se muestra.
#
# «Nuevo pedido» es **un solo formulario que se vuelve a dibujar con cada acción** (agregar o quitar un insumo, filtrar proveedores, seleccionar todos, habilitar un insumo,
# revisar, volver a corregir, confirmar), sin JavaScript y sin validar mientras se escribe (.claude/rules/interfaz.md). El estado viaja en los campos del formulario:
# ``detalle_iin`` y ``detalle_cantidad`` (listas paralelas), ``proveedor`` (lista), ``fecha_limite`` y ``filtro``; ``accion`` dice qué botón se apretó.

from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_headers

from compras.errores import ErrorDeCompras
from compras.models import EnlaceProveedor, InvitacionPedido, Proveedor
from compras.servicios import pedidos as api
from core.acceso import rol_requerido
from core.models import Agronomo, Usuario
from core.obligatorios import sumar_faltantes
from inventario.models import Insumo, InsumoInvernadero, TipoInsumo
from inventario.servicios import insumos_invernadero, stock
from inventario.servicios.formato import texto_cantidad
from maestros.models import Invernadero

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO


def _texto_de_cantidad(valor, unidad):
    """La cantidad para un campo de texto: con los decimales de su unidad y sin ceros de más («5», «2.5»)."""
    texto = texto_cantidad(valor, unidad)
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


# ---- lista ----


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def pedidos(request):
    """«Compras» → «Pedidos» (CMP-CNS-PED, ``tabPed``): la lista con sus filtros (estado, invernadero de destino, proveedor invitado, rango de fechas de pedido o de fecha
    límite y, solo para el Gerente, Agrónomo). Los filtros se envían con «Filtrar». No audita (regla 9)."""
    entrada = request.GET
    filtros = {
        "estado": entrada.get("estado", ""),
        "invernadero_id": entrada.get("invernadero", ""),
        "proveedor_id": entrada.get("proveedor", ""),
        "desde": entrada.get("desde", ""),
        "hasta": entrada.get("hasta", ""),
        "fecha_de": "limite" if entrada.get("fecha_de") == "limite" else "pedido",
        "agronomo_id": entrada.get("agronomo", ""),
    }
    es_gerente = request.user.rol == GERENTE
    filas = api.consultar_pedidos(request.user, filtros)
    return render(
        request,
        "compras/pedidos/lista.html",
        {
            "filas": filas,
            "filtros": {k: v for k, v in entrada.items()},
            "hay_filtros": any(entrada.get(k) for k in ("estado", "invernadero", "proveedor", "desde", "hasta", "agronomo")) or entrada.get("fecha_de") == "limite",
            "estados": [("en_cotizacion", "En cotización"), ("cerrado", "Cerrado"), ("cancelado", "Cancelado")],
            "invernaderos": Invernadero.objects.en_alcance_de(request.user).order_by(Lower("nombre_invernadero"), "id"),
            "proveedores": Proveedor.objects.en_alcance_de(request.user).order_by(Lower("razon_social_proveedor"), "id"),
            "agronomos": Agronomo.objects.order_by(Lower("last_name"), "id") if es_gerente else [],
            "es_gerente": es_gerente,
            "puede_hacer_pedidos": not es_gerente,
            "por_resolver": sum(1 for f in filas if f.por_resolver),
        },
    )


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def pedido_ficha(request, pedido_id):
    """Ficha del pedido (CMP-CNS-PED reglas 4 a 6, ``VIEWS.c_ped``): el pedido, lo pedido por invernadero, los proveedores invitados y las cotizaciones recibidas, en solo
    lectura, con «Cancelar pedido» y «Reenviar invitación» (CMP-02b) para el Agrónomo del pedido; generar la orden (CMP-03) se suma a su tarea. Un pedido ajeno es 403 y uno
    inexistente, 404 (D-28)."""
    ficha = api.ficha_de_pedido(request.user, pedido_id)
    return render(request, "compras/pedidos/ficha.html", _contexto_de_la_ficha(request, ficha))


# ---- nuevo pedido ----


def _entero(valor):
    """El valor como entero o ``None``."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _fecha(texto):
    """``AAAA-MM-DD`` como fecha, o ``None``."""
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def _leer(datos):
    """El estado del formulario: ``(filas, marcados, fecha_limite, filtro)``. Una fila es ``{"iin_id", "cantidad"}`` (el id tal como llegó, para poder mostrar un error)."""
    iins, cantidades = datos.getlist("detalle_iin"), datos.getlist("detalle_cantidad")
    filas = [{"iin_id": iin, "cantidad": cantidades[i].strip() if i < len(cantidades) else ""} for i, iin in enumerate(iins)]
    marcados = {i for i in (_entero(x) for x in datos.getlist("proveedor")) if i is not None}
    return filas, marcados, datos.get("fecha_limite", "").strip(), datos.get("filtro", "").strip()


def _opciones(actor):
    """Los insumos pedibles de cada invernadero a cargo de ``actor`` (extensión 3a), para el selector del catálogo y para conocer su stock: ``(grupos, por_iin)``."""
    grupos, por_iin = [], {}
    invernaderos = Invernadero.objects.filter(agronomo_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO).order_by(Lower("nombre_invernadero"), "id")
    for invernadero in invernaderos:
        filas = api.insumos_pedibles(actor, invernadero.pk)
        grupos.append({"invernadero": invernadero, "filas": filas})
        por_iin.update({f.iin.pk: f for f in filas})
    return grupos, por_iin


def _proveedores_visibles(filas_por_iin, filtro):
    """Pasos 6 y 7a (H13, MD-121): los proveedores que se ofrecen según el filtro. Sin filtro se propone el de las categorías de los insumos del pedido (si ninguno vende lo
    que se pide, todos); ``todos`` o el id de una categoría. Devuelve ``(lista, categorias_del_pedido)``."""
    categorias = api.categorias_del_pedido(filas_por_iin)
    if filtro == "todos":
        return api.proveedores_invitables(), categorias
    if filtro.isdigit():
        return api.proveedores_invitables([int(filtro)]), categorias
    propuestos = api.proveedores_invitables(categorias) if categorias else []
    return propuestos or api.proveedores_invitables(), categorias


def _errores_del_servicio(error):
    """Reparte los errores de un ``ValidationError`` del servicio: por insumo (``insumo_<id>`` y ``cantidad_<id>``) y generales (``detalles``, ``fecha_limite``,
    ``proveedores`` y los del Sistema)."""
    por_insumo, generales = {}, {"general": []}
    for campo, lista in getattr(error, "error_dict", {}).items():
        textos = [e.messages[0] for e in lista]
        tipo, _, identificador = campo.partition("_")
        if tipo in ("insumo", "cantidad") and identificador:
            por_insumo.setdefault(identificador, {}).setdefault(tipo, []).extend(textos)
        elif campo == NON_FIELD_ERRORS:
            generales["general"].extend(textos)
        else:
            generales.setdefault(campo, []).extend(textos)
    return por_insumo, generales


def _dibujar(request, filas, marcados, fecha_limite, filtro, *, por_insumo=None, errores=None, habilitar=None):
    """Dibuja el formulario de «Nuevo pedido» con el estado que se le pasa."""
    por_insumo, errores = por_insumo or {}, errores or {}
    grupos, por_iin = _opciones(request.user)
    para_la_pantalla = []
    for indice, fila in enumerate(filas):
        iin_id = _entero(fila["iin_id"])
        pedible = por_iin.get(iin_id)
        iin = pedible.iin if pedible else InsumoInvernadero.objects.select_related("insumo", "invernadero").filter(pk=iin_id, invernadero__agronomo_id=request.user.pk).first() if iin_id else None
        para_la_pantalla.append(
            {
                "indice": indice,
                "iin": iin,
                "iin_id": fila["iin_id"],
                "cantidad": fila["cantidad"],
                "existencia": pedible.existencia if pedible else None,
                "ya_pedido": pedible.ya_pedido if pedible else None,
                "errores": por_insumo.get(str(fila["iin_id"]), {}),
            }
        )
    visibles, categorias = _proveedores_visibles([f["iin_id"] for f in filas], filtro)
    ids_visibles = {p.pk for p in visibles}
    return render(
        request,
        "compras/pedidos/nuevo.html",
        {
            "filas": para_la_pantalla,
            "bajo_el_minimo": api.insumos_bajo_el_minimo(request.user),
            "grupos": grupos,
            "proveedores": [
                {"proveedor": p, "marcado": p.pk in marcados, "vende_lo_que_pide": bool({c.pk for c in p.especialidades.all()} & categorias)} for p in visibles
            ],
            "marcados_ocultos": sorted(marcados - ids_visibles),
            "filtro": filtro,
            "categorias": TipoInsumo.objects.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO).order_by(Lower("nombre_tipo_insumo"), "id"),
            "fecha_limite": fecha_limite or api.proponer_fecha_limite().isoformat(),
            "fecha_minima": (stock.hoy() + timedelta(days=1)).isoformat(),  # 8a: como mínimo, el día siguiente
            "errores": errores,
            "habilitar": habilitar or {},
            "invernaderos_a_cargo": [g["invernadero"] for g in grupos],
            "insumos_del_catalogo": Insumo.objects.filter(estado_insumo=Insumo.Estado.ACTIVO).order_by(Lower("nombre_insumo"), "id"),
        },
    )


def _datos_del_servicio(filas, marcados, fecha_limite):
    """Los datos que esperan ``resumir_pedido`` y ``registrar_pedido``."""
    return {
        "detalles": [(fila["iin_id"], fila["cantidad"]) for fila in filas],
        "proveedores": sorted(marcados),
        "fecha_limite": _fecha(fecha_limite),
    }


# UI-06 (UX-27): los obligatorios del bloque «Habilitar» que el servicio mira recién cuando el invernadero y el insumo están elegidos. Fila: (clave del error, campo del formulario, texto).
OBLIGATORIOS_DE_HABILITAR = (
    ("minimo", "hab_minimo", "Ingresá el stock mínimo."),  # insumos_invernadero.py:64
    ("precio", "hab_precio", "Ingresá el precio de referencia."),  # insumos_invernadero.py:86
)


def _habilitar(request, filas):
    """Extensión 3a.1a: habilita el insumo (CMP-HAB-IIN) y lo suma al pedido. Devuelve ``(filas, habilitar)``: el estado de la ventana, con sus errores si los hay."""
    datos = request.POST
    escrito = {"invernadero": datos.get("hab_invernadero", ""), "insumo": datos.get("hab_insumo", ""), "minimo": datos.get("hab_minimo", "").strip(), "precio": datos.get("hab_precio", "").strip()}
    invernadero_id, insumo_id = _entero(escrito["invernadero"]), _entero(escrito["insumo"])
    errores = {}
    if invernadero_id is None:
        errores["invernadero"] = ["Elegí el invernadero."]
    if insumo_id is None:
        errores["insumo"] = ["Elegí el insumo."]
    if errores:
        # UI-06 (UX-27, D-109 punto 9): como la vista cortó antes de llamar al servicio, este no llega a mirar el mínimo ni el precio: se suman si vinieron vacíos, con los textos del
        # servicio (`inventario/servicios/insumos_invernadero.py:64` y `:86`).
        sumar_faltantes(errores, datos, OBLIGATORIOS_DE_HABILITAR, como_lista=True)
    if not errores:
        try:
            iin = insumos_invernadero.habilitar_insumo(request.user, insumo_id, invernadero_id, escrito["minimo"], escrito["precio"])
        except ValidationError as error:
            nombres = {"cant_min": "minimo", "referencia_precio": "precio", NON_FIELD_ERRORS: "general"}
            for campo, lista in error.error_dict.items():
                errores.setdefault(nombres.get(campo, "general"), []).extend(e.messages[0] for e in lista)
        else:
            messages.success(request, f"{iin.insumo.nombre_insumo} quedó habilitado en {iin.invernadero.nombre_invernadero}. Indicá la cantidad que querés pedir.")
            if not any(_entero(f["iin_id"]) == iin.pk for f in filas):
                filas = [*filas, {"iin_id": iin.pk, "cantidad": ""}]
            return filas, {}
    return filas, {"abierto": True, **escrito, "errores": errores}


def _avisar_de_los_envios(request, pedido):
    """Paso 13 y extensión 12a: informa que el pedido se registró y, por cada proveedor al que no se pudo enviar el correo, qué hacer (D-88 punto 6; sin notificación de campana:
    nunca se avisa a quien hizo la acción, H21). El correo sale en ``on_commit``, antes de volver acá."""
    sin_enviar = EnlaceProveedor.objects.filter(invitacion__pedido=pedido, estado_envio=EnlaceProveedor.EstadoEnvio.PENDIENTE_ENVIO).select_related("invitacion__proveedor")
    for enlace in sin_enviar:
        messages.error(
            request,
            f"No se pudo enviar la invitación a {enlace.invitacion.proveedor.nombre_para_mostrar}: pedile al Gerente que revise su correo y reenviá la invitación.",
        )
    n = pedido.invitaciones.count()
    if sin_enviar:
        messages.success(request, f"Registramos el pedido {pedido}.")
    else:
        messages.success(request, f"Enviamos el pedido {pedido} a {n} proveedor{'es' if n != 1 else ''}.")


@rol_requerido(AGRONOMO)
@never_cache
def pedido_nuevo(request):
    """«Nuevo pedido de cotización» (CMP-RLZ-PED, ``VIEWS.c_pednew``). GET arma el formulario (con ``?iin=`` desde un insumo bajo el mínimo: extensión 1a); POST lo vuelve a
    dibujar con la acción que se pidió o, con ``revisar``, muestra el resumen del paso 9 y, con ``confirmar``, registra el pedido (paso 11) y lleva a su ficha."""
    if request.method != "POST":
        filas = []
        iin_id = _entero(request.GET.get("iin"))
        if iin_id is not None:
            _, por_iin = _opciones(request.user)
            if iin_id in por_iin:
                pedible = por_iin[iin_id]
                filas = [{"iin_id": iin_id, "cantidad": _texto_de_cantidad(pedible.sugerida, pedible.iin.insumo.unidad_medida_insumo) if pedible.sugerida else ""}]
        return _dibujar(request, filas, set(), "", "")

    filas, marcados, fecha_limite, filtro = _leer(request.POST)
    accion = request.POST.get("accion", "")
    habilitar = None
    if accion.startswith("agregar:") or accion == "agregar_catalogo":
        iin_id = _entero(accion.partition(":")[2] if accion.startswith("agregar:") else request.POST.get("catalogo_iin"))
        _, por_iin = _opciones(request.user)
        if iin_id in por_iin and not any(_entero(f["iin_id"]) == iin_id for f in filas):
            pedible = por_iin[iin_id]
            sugerida = _texto_de_cantidad(pedible.sugerida, pedible.iin.insumo.unidad_medida_insumo) if pedible.sugerida else ""
            filas = [*filas, {"iin_id": iin_id, "cantidad": sugerida}]
    elif accion.startswith("quitar:"):
        posicion = _entero(accion.partition(":")[2])
        filas = [f for i, f in enumerate(filas) if i != posicion]
    elif accion == "todos":
        visibles, _ = _proveedores_visibles([f["iin_id"] for f in filas], filtro)
        marcados |= {p.pk for p in visibles}
    elif accion == "habilitar":
        filas, habilitar = _habilitar(request, filas)
    elif accion in ("revisar", "confirmar"):
        datos = _datos_del_servicio(filas, marcados, fecha_limite)
        try:
            if accion == "confirmar":
                pedido = api.registrar_pedido(request.user, datos, request.build_absolute_uri)
            else:
                resumen = api.resumir_pedido(request.user, datos)
        except ValidationError as error:
            por_insumo, errores = _errores_del_servicio(error)
            return _dibujar(request, filas, marcados, fecha_limite, filtro, por_insumo=por_insumo, errores=errores)
        if accion == "confirmar":
            _avisar_de_los_envios(request, pedido)
            return redirect("compras:pedido_ficha", pedido_id=pedido.pk)
        return render(
            request,
            "compras/pedidos/resumen.html",
            {
                "resumen": resumen,
                "filas": filas,
                "proveedores_marcados": sorted(marcados),
                "fecha_limite": fecha_limite,
                "filtro": filtro,
            },
        )
    return _dibujar(request, filas, marcados, fecha_limite, filtro, habilitar=habilitar)


# ---- cancelar y reenviar (CMP-02b) ----

PLANTILLA_DE_REENVIO = "compras/pedidos/_ventana_reenviar.html"


def _contexto_de_la_ficha(request, ficha, **extra):
    """Lo que la ficha del pedido necesita para dibujarse (la usan la ficha y, con la ventana abierta, el respaldo sin JavaScript de «Reenviar invitación»)."""
    return {"ficha": ficha, "pedido": ficha.pedido, "es_gerente": request.user.rol == GERENTE, **extra}


@rol_requerido(AGRONOMO)
@never_cache
def pedido_cancelar(request, pedido_id):
    """«Cancelar pedido» (CMP-CNL-PED, ``VIEWS.c_pedcnl``). GET: qué se cancela y el motivo. POST con ``revisar``: valida el motivo y muestra el resumen del paso 4
    (cuántas cotizaciones se descartan, cuántos enlaces se anulan y a quién se avisa); con ``confirmar``, cancela (paso 6); con ``editar``, vuelve al formulario con
    lo escrito. Solo el Agrónomo del pedido y con el pedido «en cotización»: si no, se vuelve a la ficha con el motivo (extensión 6a); un ajeno es 403 (D-28)."""
    ficha = api.ficha_de_pedido(request.user, pedido_id)
    pedido = ficha.pedido
    if not ficha.puede_cancelar:
        messages.error(request, f"El pedido {pedido} ya no está en cotización: {pedido.get_estado_pedido_display().lower()}. No se puede cancelar.")
        return redirect("compras:pedido_ficha", pedido_id=pedido.pk)
    motivo = request.POST.get("motivo", "") if request.method == "POST" else ""
    accion = request.POST.get("accion", "") if request.method == "POST" else ""
    contexto = {"ficha": ficha, "pedido": pedido, "motivo": motivo, "errores": []}
    if accion in ("revisar", "confirmar"):
        try:
            if accion == "confirmar":
                api.cancelar_pedido(request.user, pedido.pk, motivo)
            else:
                resumen = api.resumir_cancelacion(request.user, pedido.pk, motivo)
        except ValidationError as error:
            contexto["errores"] = [m for lista in error.message_dict.values() for m in lista]
        except ErrorDeCompras as error:  # 6a: otra operación cambió el pedido
            messages.error(request, error.mensaje)
            return redirect("compras:pedido_ficha", pedido_id=pedido.pk)
        else:
            if accion == "confirmar":
                messages.success(request, f"Pedido {pedido} cancelado. Se avisó por correo a los proveedores invitados.")
                return redirect("compras:pedido_ficha", pedido_id=pedido.pk)
            return render(request, "compras/pedidos/cancelar_resumen.html", {**contexto, "resumen": resumen})
    return render(request, "compras/pedidos/cancelar.html", contexto)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def invitacion_reenviar(request, invitacion_id):
    """«Reenviar invitación» (regla 7 de CMP-CNS-PED, ``MODALS.reenviar``), con confirmación previa. GET abre la ventana (no cambia nada; sin JavaScript, la ficha con la
    ventana abierta); POST reenvía. Si el servicio lo rechaza (el pedido se cerró, el proveedor cotizó o se dio de baja, venció la fecha límite) vuelve a la ficha con el
    motivo. Si el correo no sale, avisa qué hacer (D-88 punto 6; sin notificación de campana, H21). Solo el Agrónomo del pedido: otro es 403."""
    invitacion = get_object_or_404(InvitacionPedido.objects.select_related("pedido", "proveedor"), pk=invitacion_id)
    ficha = api.ficha_de_pedido(request.user, invitacion.pedido_id)
    volver = redirect("compras:pedido_ficha", pedido_id=invitacion.pedido_id)
    invitado = next((i for i in ficha.invitados if i.invitacion.pk == invitacion.pk), None)
    if invitado is None or not invitado.puede_reenviar:
        messages.error(request, f"No se le puede reenviar la invitación a {invitacion.proveedor.nombre_para_mostrar}: el pedido ya no admite cotizaciones o el proveedor ya cotizó.")
        return volver
    if request.method == "POST":
        try:
            nuevo = api.reenviar_invitacion(request.user, invitacion.pk, request.build_absolute_uri)
        except ErrorDeCompras as error:
            messages.error(request, error.mensaje)
            return volver
        nuevo.refresh_from_db()  # el correo salió en ``on_commit``, antes de volver acá
        if nuevo.estado_envio == EnlaceProveedor.EstadoEnvio.ENVIADO:
            messages.success(request, f"Enviamos la invitación nueva a {invitacion.proveedor.nombre_para_mostrar}. El enlace anterior ya no sirve.")
        else:
            messages.error(
                request,
                f"No se pudo enviar la invitación a {invitacion.proveedor.nombre_para_mostrar}: pedile al Gerente que revise su correo y reenviá la invitación.",
            )
        return volver
    contexto = {"pedido": invitacion.pedido, "invitacion": invitacion, "proveedor": invitacion.proveedor}
    if request.headers.get("HX-Request") == "true":
        return render(request, PLANTILLA_DE_REENVIO, contexto)
    return render(request, "compras/pedidos/ficha.html", _contexto_de_la_ficha(request, ficha, plantilla_de_ventana=PLANTILLA_DE_REENVIO, **contexto))
