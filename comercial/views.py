# Vistas de `comercial` para COM-01: la pantalla «Comercial» con sus pestañas «Clientes» y «Vehículos» (solo el Gerente), las fichas, los
# formularios, las ventanas de baja y los fragmentos de HTMX de las direcciones. Las vistas solo orquestan: validan la entrada, llaman
# al servicio y renderizan (CLAUDE.md, arquitectura; docs/patrones/abm.md, sección 1). Los pedidos de HTMX reciben solo la ventana; sin
# JavaScript, cada ventana es una página (la ficha con la ventana abierta).

import re

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from comercial.forms import FormularioCliente, FormularioDireccion, FormularioVehiculo
from comercial.servicios import clientes as api_clientes
from comercial.servicios import vehiculos as api_vehiculos
from comercial.servicios.clientes import DatosDeCliente
from comercial.servicios.vehiculos import DatosDeVehiculo
from comercial.views_contratos import con_parametro
from core.acceso import rol_requerido
from core.models import Usuario
from maestros.models import Invernadero

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR

_CUIT_REPETIDO = ("cuit_de_cliente_activo", "cuit_de_cliente_inactivo")
_PREFIJO = re.compile(r"(nueva|corregida)-\d+")


def _volver_seguro(request):
    """El parámetro ``volver`` (regla 7 de COM-ALT-CLT y regla 5 de COM-MOD-CLT: volver al caso de uso que incluye el alta o la
    modificación) solo si es una URL interna; si no, texto vacío (como la vuelta a la pantalla pedida de D-29). Lo usa «Nueva
    compra-venta» (COM-02); COM-03 suma «Pactar suministro»."""
    candidato = request.POST.get("volver") or request.GET.get("volver") or ""
    if candidato and url_has_allowed_host_and_scheme(candidato, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return candidato
    return ""


def _es_htmx(request):
    return request.headers.get("HX-Request") == "true"


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def inicio(request):
    """«Comercial»: abre en «Contratos», la primera pestaña (COM-02; COM-01 redirigía a «Clientes»)."""
    return redirect("comercial:contratos")


# ---- clientes: consulta (COM-CNS-CLT) ----


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def clientes(request):
    """Pestaña «Clientes» (``tabClientes`` del prototipo): búsqueda por CUIT, razón social o nombre y apellido, filtro por estado y
    páginas de 50. Los filtros son un formulario GET común (sin JavaScript funciona igual). No audita."""
    texto = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    pagina = api_clientes.buscar_clientes(request.user, texto, estado, request.GET.get("pagina"))
    return render(
        request,
        "comercial/clientes/lista.html",
        {
            "pagina": pagina,
            "activas_por_cliente": api_clientes.direcciones_activas_por_cliente(pagina.object_list),
            "vigentes_por_cliente": api_clientes.contratos_vigentes_por_cliente(request.user, pagina.object_list),
            "q": texto,
            "estado": estado,
            "es_gerente": request.user.rol == GERENTE,
        },
    )


def _contexto_de_la_ficha(request, cliente_id, **extra):
    """Lo que necesita la ficha del cliente (``VIEWS.cli``)."""
    ficha = api_clientes.ficha_del_cliente(request.user, cliente_id)
    return {
        "ficha": ficha,
        "cliente": ficha.cliente,
        "acciones": api_clientes.acciones_permitidas(request.user, ficha.cliente),
        "contratos": api_clientes.contratos_del_cliente(request.user, ficha.cliente),
        "es_gerente": request.user.rol == GERENTE,
        **extra,
    }


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
def cliente(request, cliente_id):
    """Ficha del cliente (COM-CNS-CLT, regla 2): sus datos y sus direcciones, activas e inactivas. Los contratos
    (compra-ventas, COM-02; el Vendedor ve solo las suyas) y, más adelante, las entregas sin cobrar (COM-06 y COM-08)."""
    return render(request, "comercial/clientes/ficha.html", _contexto_de_la_ficha(request, cliente_id))


# ---- clientes: alta, modificación y reactivación (COM-ALT-CLT, COM-MOD-CLT) ----


def _indices_de_nuevas(post):
    """Las posiciones de los bloques ``nueva-<i>`` que llegaron en el formulario, en orden."""
    return sorted({int(m.group(1)) for clave in post if (m := re.match(r"nueva-(\d+)-", clave))})


def _pasar_errores(error, form, nuevas, usadas, corregidas):
    """Pasa los errores del servicio al formulario: los de datos a su campo, los de una dirección nueva (``nueva-<posición>``) o
    corregida (``corregida-<id>``) al formulario de esa dirección y los demás como generales. ``usadas`` es la lista de las
    posiciones de las nuevas que se mandaron al servicio (las vacías se ignoran). Devuelve el CUIT repetido, si lo hubo."""
    repetido = None
    for campo, lista in error.error_dict.items():
        for e in lista:
            destino, nombre = form, campo
            if campo == "cuit" and e.code in _CUIT_REPETIDO:
                repetido = {"codigo": e.code, "cliente_id": (e.params or {}).get("cliente_id")}
            elif (m := re.fullmatch(r"nueva-(\d+)(?:-(.+))?", campo)) and int(m.group(1)) < len(usadas):
                destino, nombre = nuevas[usadas[int(m.group(1))]], m.group(2)
            elif m := re.fullmatch(r"corregida-(\d+)(?:-(.+))?", campo):
                destino, nombre = corregidas.get(int(m.group(1)), form), m.group(2)
            destino.add_error(nombre if nombre in destino.fields else None, e)
    return repetido


def _formulario_de_cliente(request, cliente_, modo):
    """El formulario del cliente para el alta (``modo="alta"``), la modificación (``"modificar"``) y la reactivación (``"reactivar"``,
    que abre el mismo formulario del alta con los datos guardados). El servicio recibe un ``DatosDeCliente`` con todo lo del
    formulario: las direcciones existentes siempre van como «corregidas» (si no cambiaron, no pasa nada, D-28) y las que se marcan
    «Desactivar» o «Borrar» se retiran. «Agregar dirección» y «Actualizar» (sin JavaScript) redibujan sin guardar."""
    ficha = api_clientes.ficha_del_cliente(request.user, cliente_.pk) if cliente_ else None
    activas = list(ficha.direcciones_activas) if ficha else []
    inactivas = list(ficha.direcciones_inactivas) if ficha else []
    en_uso = api_clientes.direcciones_en_uso([h.pk for h in activas]) if activas else set()
    volver = _volver_seguro(request)
    repetido = None
    # Con ``volver`` (regreso a «Nueva compra-venta»): qué direcciones tenía el cliente antes, para devolver la nueva elegida.
    antes = set(api_clientes.ids_de_direcciones(cliente_)) if (volver and cliente_) else set()
    desactivar = {int(i) for i in request.POST.getlist("desactivar") if i.isdigit()}
    borrar = {int(i) for i in request.POST.getlist("borrar") if i.isdigit()}

    if request.method == "POST":
        form = FormularioCliente(request.POST, cliente=cliente_)
        form.is_valid()
        indices = _indices_de_nuevas(request.POST)
        nuevas = {i: FormularioDireccion(request.POST, prefix=f"nueva-{i}") for i in indices}
        corregidas = {h.pk: FormularioDireccion(request.POST, prefix=f"corregida-{h.pk}", hija=h) for h in activas}
        if "agregar_direccion" in request.POST:
            siguiente = (indices[-1] + 1) if indices else 0
            nuevas[siguiente] = FormularioDireccion(prefix=f"nueva-{siguiente}")
        elif "actualizar" not in request.POST:
            datos = DatosDeCliente.desde_post(request.POST)
            usadas = [i for i in indices if not nuevas[i].esta_vacia()]
            datos.direcciones_nuevas = [d for i, d in zip(indices, datos.direcciones_nuevas) if i in usadas]
            try:
                if modo == "alta":
                    guardado = api_clientes.alta_cliente(request.user, datos)
                    aviso = f"Cliente registrado: {guardado}."
                elif modo == "reactivar":
                    guardado = api_clientes.reactivar_cliente(request.user, cliente_.pk, datos)
                    aviso = f"{guardado} está activo de nuevo."
                    if request.user.rol == VENDEDOR:
                        aviso += " Se notificó al Gerente."
                else:
                    guardado = api_clientes.modificar_cliente(request.user, cliente_.pk, datos)
                    aviso = f"Se guardaron los cambios de {guardado}."
            except ValidationError as error:
                if hasattr(error, "error_dict"):
                    repetido = _pasar_errores(error, form, nuevas, usadas, corregidas)
                else:
                    form.add_error(None, error)
            else:
                messages.success(request, aviso)
                if volver:
                    # Regla 7 de ALT y 5 de MOD: se vuelve a «Nueva compra-venta» con el cliente (alta) o la dirección (modificación) recién
                    # creados, que quedan elegidos.
                    nuevas_ids = sorted(set(api_clientes.ids_de_direcciones(guardado)) - antes)
                    extra = {"cliente": guardado.pk} if modo in ("alta", "reactivar") else {"cliente": guardado.pk, "direccion": nuevas_ids[-1] if nuevas_ids else None}
                    return redirect(con_parametro(request, volver, **extra))
                return redirect("comercial:cliente", guardado.pk)
        nuevas_en_orden = [nuevas[i] for i in sorted(nuevas)]
    else:
        form = FormularioCliente(cliente=cliente_)
        corregidas = {h.pk: FormularioDireccion(hija=h, prefix=f"corregida-{h.pk}") for h in activas}
        nuevas_en_orden = []

    return render(
        request,
        "comercial/clientes/formulario.html",
        {
            "form": form,
            "cliente": cliente_,
            "modo": modo,
            "nuevas": nuevas_en_orden,
            "existentes": [
                {
                    "hija": h,
                    "dform": corregidas[h.pk],
                    "en_uso": h.pk in en_uso,
                    "desactivar": h.pk in desactivar,
                    "borrar": h.pk in borrar,
                }
                for h in activas
            ],
            "inactivas": inactivas,
            "volver": volver,
            "cuit_repetido": repetido,
            "es_vendedor": request.user.rol == VENDEDOR,
        },
    )


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
def cliente_nuevo(request):
    """Registrar cliente (COM-ALT-CLT, ``VIEWS.cliform``). Un CUIT que ya es de un cliente se rechaza con «Abrir su ficha» (activo) o
    «Reactivarlo» (inactivo, regla 2). Con el parámetro ``volver`` (URL interna) regresa a la pantalla que lo pidió."""
    return _formulario_de_cliente(request, None, "alta")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
def cliente_modificar(request, cliente_id):
    """Modificar cliente (COM-MOD-CLT, ``VIEWS.cliform``): también un cliente inactivo, que no se reactiva (regla 2)."""
    ficha = api_clientes.ficha_del_cliente(request.user, cliente_id)
    return _formulario_de_cliente(request, ficha.cliente, "modificar")


@rol_requerido(GERENTE, VENDEDOR)
@never_cache
def cliente_reactivar(request, cliente_id):
    """Reactivar cliente (COM-ALT-CLT, postcondición c y regla 2; ``ACT.reactcli``): abre el formulario del alta con los datos guardados
    para corregirlos y, al confirmar, lo pasa a «activo». Si lo hace un Vendedor, el Gerente recibe una notificación. Uno que está
    activo vuelve a su ficha con el motivo (D-30)."""
    ficha = api_clientes.ficha_del_cliente(request.user, cliente_id)
    if api_clientes.ACCION_REACTIVAR not in api_clientes.acciones_permitidas(request.user, ficha.cliente):
        messages.error(request, "El cliente no está dado de baja.")
        return redirect("comercial:cliente", ficha.cliente.pk)
    return _formulario_de_cliente(request, ficha.cliente, "reactivar")


# ---- clientes: baja (COM-BAJ-CLT) ----


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def cliente_baja(request, cliente_id):
    """Dar de baja un cliente (COM-BAJ-CLT, ``MODALS.bajacli``), con confirmación previa. Solo el Gerente (el Vendedor recibe 403 y no ve el
    botón). La ventana informa lo pendiente del cliente (regla 1) y no se bloquea nunca. Abrirla (GET) no cambia nada; la baja es un
    POST. Con HTMX llega solo la ventana; sin JavaScript, la ficha con la ventana abierta."""
    ficha = api_clientes.ficha_del_cliente(request.user, cliente_id)
    if api_clientes.ACCION_BAJA not in api_clientes.acciones_permitidas(request.user, ficha.cliente):
        messages.error(request, "El cliente ya está dado de baja.")
        return redirect("comercial:cliente", ficha.cliente.pk)
    error = ""
    if request.method == "POST":
        try:
            api_clientes.baja_cliente(request.user, ficha.cliente.pk)
        except ValidationError as rechazo:
            error = rechazo.messages[0]
        else:
            messages.success(request, f"{ficha.cliente} se dio de baja.")
            return redirect("comercial:cliente", ficha.cliente.pk)
    pendientes = api_clientes.pendientes_del_cliente(ficha.cliente, request.user)
    contexto = {"cliente": ficha.cliente, "pendientes": pendientes, "error": error}
    if _es_htmx(request):
        return render(request, "comercial/clientes/_ventana_baja.html", contexto)
    return render(
        request,
        "comercial/clientes/ficha.html",
        _contexto_de_la_ficha(request, cliente_id, plantilla_de_ventana="comercial/clientes/_ventana_baja.html", **contexto),
    )


# ---- fragmentos de HTMX de las direcciones: solo GET, no validan ni cambian nada (D-58, punto 7) ----


def _formulario_del_fragmento(request, **datos):
    """El ``FormularioDireccion`` de un fragmento: el prefijo (``nueva-<i>`` o ``corregida-<id>``) tiene que ser uno de los del
    formulario; si no, 404."""
    prefijo = request.GET.get("prefijo", "")
    if not _PREFIJO.fullmatch(prefijo):
        raise Http404("Prefijo de dirección inválido.")
    return FormularioDireccion(datos or request.GET, prefix=prefijo)


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
@vary_on_headers("HX-Request")
def direccion_campos(request):
    """Los datos de la dirección del tipo elegido: calle y número, o ruta y kilómetro (regla 2 de PROD-ALT-INV)."""
    return render(request, "comercial/clientes/_direccion_campos.html", {"dform": _formulario_del_fragmento(request)})


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
@vary_on_headers("HX-Request")
def direccion_departamentos(request):
    """Los campos de departamento y localidad de la provincia elegida (regla 3 de PROD-ALT-INV): la localidad se vacía. Lee Georef con
    ``maestros.servicios.geografia``."""
    prefijo = request.GET.get("prefijo", "")
    dform = _formulario_del_fragmento(request, **{f"{prefijo}-provincia": request.GET.get(f"{prefijo}-provincia", "")})
    return render(request, "comercial/clientes/_direccion_departamento_y_localidad.html", {"dform": dform})


@rol_requerido(GERENTE, VENDEDOR)
@require_safe
@vary_on_headers("HX-Request")
def direccion_localidades(request):
    """El campo de localidad del departamento elegido (regla 3 de PROD-ALT-INV)."""
    prefijo = request.GET.get("prefijo", "")
    dform = _formulario_del_fragmento(request, **{f"{prefijo}-departamento": request.GET.get(f"{prefijo}-departamento", "")})
    return render(request, "comercial/clientes/_direccion_localidad.html", {"dform": dform})


# ---- vehículos (solo el Gerente) ----


@rol_requerido(GERENTE)
@require_safe
def vehiculos(request):
    """Pestaña «Vehículos» (``tabVehiculos`` del prototipo; COM-CNS-VEH): búsqueda por patente, tipo o transportista y filtros por
    estado y por el invernadero del transportista. Solo el Gerente (el Vendedor recibe 403). No audita."""
    texto = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    invernadero_id = request.GET.get("invernadero", "")
    filas = api_vehiculos.buscar_vehiculos(request.user, texto, estado, invernadero_id)
    return render(
        request,
        "comercial/vehiculos/lista.html",
        {
            "filas": filas,
            "q": texto,
            "estado": estado,
            "invernadero_id": invernadero_id,
            "invernaderos": Invernadero.objects.en_alcance_de(request.user).order_by("nombre_invernadero"),
        },
    )


def _contexto_de_la_ficha_del_vehiculo(request, vehiculo_id, **extra):
    """Lo que necesita la ficha del vehículo (se arma con el mismo estilo que ``VIEWS.cli``)."""
    ficha = api_vehiculos.ficha_del_vehiculo(request.user, vehiculo_id)
    return {"ficha": ficha, "vehiculo": ficha.vehiculo, "acciones": api_vehiculos.acciones_permitidas(request.user, ficha.vehiculo), **extra}


@rol_requerido(GERENTE)
@require_safe
def vehiculo(request, vehiculo_id):
    """Ficha del vehículo (COM-CNS-VEH, regla 2): datos, transportista, su invernadero y «En ruta hoy» o «En el invernadero». La carga
    asignada frente a la capacidad se suma en COM-05 (no se muestra hasta que exista, D-25)."""
    return render(request, "comercial/vehiculos/ficha.html", _contexto_de_la_ficha_del_vehiculo(request, vehiculo_id))


def _pasar_errores_de_vehiculo(error, form):
    """Pasa los errores del servicio al formulario del vehículo: ``transportista`` va al campo ``transportista_id``; los generales
    (``vehiculo_en_ruta``, ``vehiculo_inactivo``…) quedan arriba."""
    if not hasattr(error, "error_dict"):
        form.add_error(None, error)
        return
    for campo, lista in error.error_dict.items():
        nombre = "transportista_id" if campo == "transportista" else campo
        for e in lista:
            form.add_error(nombre if nombre in form.fields else None, e)


def _formulario_de_vehiculo(request, vehiculo_):
    """El formulario del vehículo (alta si ``vehiculo_`` es ``None``). Los transportistas que se ofrecen son los de
    ``transportistas_disponibles`` (activos y libres, más el actual). «Actualizar» (sin JavaScript) redibuja sin guardar."""
    opciones = api_vehiculos.transportistas_disponibles(request.user, vehiculo_)
    if request.method == "POST":
        form = FormularioVehiculo(request.POST, vehiculo=vehiculo_, opciones=opciones)
        form.is_valid()
        if "actualizar" not in request.POST:
            datos = DatosDeVehiculo(
                patente=form.cleaned_data.get("patente", ""),
                tipo_vehiculo=form.cleaned_data.get("tipo_vehiculo", ""),
                marca=form.cleaned_data.get("marca", ""),
                modelo=form.cleaned_data.get("modelo", ""),
                capacidad_carga=form.cleaned_data.get("capacidad_carga", ""),
                transportista_id=form.cleaned_data.get("transportista_id", ""),
            )
            try:
                if vehiculo_ is None:
                    guardado = api_vehiculos.alta_vehiculo(request.user, datos)
                    aviso = f"Vehículo registrado: {guardado.patente}."
                else:
                    guardado = api_vehiculos.modificar_vehiculo(request.user, vehiculo_.pk, datos)
                    aviso = f"Se guardaron los cambios de {guardado.patente}."
            except ValidationError as error:
                _pasar_errores_de_vehiculo(error, form)
            else:
                messages.success(request, aviso)
                return redirect("comercial:vehiculo", guardado.pk)
    else:
        form = FormularioVehiculo(vehiculo=vehiculo_, opciones=opciones)
    return render(request, "comercial/vehiculos/formulario.html", {"form": form, "vehiculo": vehiculo_})


@rol_requerido(GERENTE)
@never_cache
def vehiculo_nuevo(request):
    """Registrar vehículo (COM-ALT-VEH, ``VIEWS.vehform``). Solo el Gerente."""
    return _formulario_de_vehiculo(request, None)


@rol_requerido(GERENTE)
@never_cache
def vehiculo_modificar(request, vehiculo_id):
    """Modificar vehículo (COM-MOD-VEH, ``VIEWS.vehform`` líneas 1136 y 1807). Uno inactivo no se modifica: solo se reactiva; vuelve a
    la ficha con el motivo (D-30). Uno en ruta lo rechaza el servicio con su aviso."""
    ficha = api_vehiculos.ficha_del_vehiculo(request.user, vehiculo_id)
    if api_vehiculos.ACCION_MODIFICAR not in api_vehiculos.acciones_permitidas(request.user, ficha.vehiculo):
        messages.error(request, "El vehículo está dado de baja: solo se puede reactivar.")
        return redirect("comercial:vehiculo", ficha.vehiculo.pk)
    return _formulario_de_vehiculo(request, ficha.vehiculo)


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def vehiculo_baja(request, vehiculo_id):
    """Dar de baja un vehículo (COM-BAJ-VEH, ``MODALS.bajaveh``), con confirmación previa. La ventana dice si está en ruta o si su
    transportista tiene entregas a realizar (no ofrece confirmar). Abrirla (GET) no cambia nada; la baja es un POST."""
    ficha = api_vehiculos.ficha_del_vehiculo(request.user, vehiculo_id)
    vehiculo_ = ficha.vehiculo
    if api_vehiculos.ACCION_BAJA not in api_vehiculos.acciones_permitidas(request.user, vehiculo_):
        messages.error(request, "El vehículo ya está dado de baja.")
        return redirect("comercial:vehiculo", vehiculo_.pk)
    error = ""
    if request.method == "POST":
        try:
            api_vehiculos.baja_vehiculo(request.user, vehiculo_.pk)
        except ValidationError as rechazo:
            error = rechazo.messages[0]
        else:
            messages.success(request, f"El vehículo {vehiculo_.patente} se dio de baja.")
            return redirect("comercial:vehiculo", vehiculo_.pk)
    entregas = bool(vehiculo_.transportista and api_vehiculos.entregas_a_realizar_del_transportista(vehiculo_.transportista))
    contexto = {"vehiculo": vehiculo_, "en_ruta": ficha.en_ruta, "con_entregas": entregas, "error": error}
    if _es_htmx(request):
        return render(request, "comercial/vehiculos/_ventana_baja.html", contexto)
    return render(
        request,
        "comercial/vehiculos/ficha.html",
        _contexto_de_la_ficha_del_vehiculo(request, vehiculo_id, plantilla_de_ventana="comercial/vehiculos/_ventana_baja.html", **contexto),
    )


@rol_requerido(GERENTE)
@require_POST
def vehiculo_reactivar(request, vehiculo_id):
    """Reactivar un vehículo dado de baja (COM-MOD-VEH, postcondición c; ``ACT.reactveh``), sin ventana: queda activo y sin transportista."""
    try:
        reactivado = api_vehiculos.reactivar_vehiculo(request.user, vehiculo_id)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"El vehículo {reactivado.patente} está activo de nuevo. Quedó sin transportista.")
    return redirect("comercial:vehiculo", vehiculo_id)
