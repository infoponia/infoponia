# Vistas de maestros para MAE-01: lista y ficha de invernaderos (PROD-CNS-INV), alta (PROD-ALT-INV), modificación y
# reactivación (PROD-MOD-INV), baja (PROD-BAJ-INV) y los fragmentos HTMX de las listas encadenadas de Georef. Las vistas
# solo orquestan: validan la entrada, llaman al servicio y renderizan (CLAUDE.md, arquitectura).

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from maestros.forms import FormularioInvernadero
from maestros.servicios.invernaderos import (
    FaltaConfirmarPersonal,
    acciones_permitidas,
    alta_invernadero,
    baja_invernadero,
    consultar_invernaderos,
    impedimentos_para_baja,
    modificar_invernadero,
    obtener_invernadero,
    reactivar_invernadero,
)

GERENTE = Usuario.Rol.GERENTE
AGRONOMO = Usuario.Rol.AGRONOMO


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def invernaderos(request):
    """Lista de invernaderos del alcance de la cuenta (PROD-CNS-INV, ``invCard`` e ``invListBody`` del prototipo).
    Solo lectura, no audita (regla 7)."""
    return render(
        request,
        "maestros/invernaderos/lista.html",
        {"invernaderos": consultar_invernaderos(request.user), "es_gerente": request.user.rol == GERENTE},
    )


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
def invernadero(request, invernadero_id):
    """Ficha de un invernadero (PROD-CNS-INV, ``VIEWS.inv`` del prototipo). Fuera del alcance da 403 y un id
    inexistente, 404 (D-28). Los botones de modificar, dar de baja y reactivar son los de ``acciones_permitidas``: ningún
    botón lleva a un 403 (D-30)."""
    invernadero = obtener_invernadero(request.user, invernadero_id)
    return render(request, "maestros/invernaderos/ficha.html", _contexto_de_la_ficha(request, invernadero))


def _contexto_de_la_ficha(request, invernadero, **extra):
    """Lo que necesita la ficha: el invernadero, si quien mira es el Gerente y las acciones que le corresponden."""
    return {
        "invernadero": invernadero,
        "es_gerente": request.user.rol == GERENTE,
        "acciones": acciones_permitidas(request.user, invernadero),
        **extra,
    }


@rol_requerido(GERENTE)
@never_cache
def invernadero_nuevo(request):
    """Alta de un invernadero (PROD-ALT-INV, ``VIEWS['inv-form']`` del prototipo). Solo el Gerente.

    El botón «Actualizar» (sin JavaScript) reenvía el formulario para armar las listas encadenadas y los datos de la
    dirección del tipo elegido, sin guardar. Si el alta sale bien, va a la ficha con un aviso breve (D-29), sin
    notificaciones (D-38).
    """
    if request.method == "POST":
        form = FormularioInvernadero(request.POST)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        if "actualizar" not in request.POST:
            try:
                nuevo = alta_invernadero(request.user, **form.datos_del_servicio())
            except ValidationError as error:
                for campo, errores in error.error_dict.items():
                    for e in errores:
                        form.add_error(campo if campo in form.fields else None, e)
            else:
                messages.success(request, f"Invernadero creado: {nuevo.nombre_invernadero}.")
                return redirect("maestros:invernadero", nuevo.pk)
    else:
        form = FormularioInvernadero()
    return render(request, "maestros/invernaderos/formulario.html", {"form": form})


@rol_requerido(GERENTE)
@never_cache
def invernadero_modificar(request, invernadero_id):
    """Modificar un invernadero (PROD-MOD-INV, ``VIEWS['inv-form']`` del prototipo). Solo el Gerente.

    - Regla 5: uno inactivo no se modifica; la persona vuelve a la ficha con el motivo (sin 403: ya no ve el botón).
    - Regla 2: si el guardado cambia al personal y todavía no lo confirmó, el servicio lo avisa
      (``FaltaConfirmarPersonal``) y la página vuelve a mostrarse con la ventana de confirmación, armada en el
      servidor (sin JavaScript propio). «Volver» reenvía el formulario sin guardar («actualizar», que también sirve para
      armar las listas sin JavaScript) y «Confirmar y guardar» manda ``personal_confirmado``.
    - Solo se muestran los avisos del caso de uso: las notificaciones no se modelan (D-38) y el prototipo avisa de más.
    """
    invernadero = obtener_invernadero(request.user, invernadero_id)
    if "modificar" not in acciones_permitidas(request.user, invernadero):
        messages.error(request, "El invernadero está inactivo: solo se puede reactivar.")
        return redirect("maestros:invernadero", invernadero.pk)
    aviso = None
    if request.method == "POST":
        form = FormularioInvernadero(request.POST, invernadero=invernadero)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        if "actualizar" not in request.POST:
            try:
                modificar_invernadero(
                    request.user,
                    invernadero.pk,
                    personal_confirmado="personal_confirmado" in request.POST,
                    **form.datos_del_servicio(),
                )
            except FaltaConfirmarPersonal as falta:
                aviso = falta.aviso
            except ValidationError as error:
                for campo, errores in error.error_dict.items():
                    for e in errores:
                        form.add_error(campo if campo in form.fields else None, e)
            else:
                messages.success(request, f"Se guardaron los cambios de {invernadero.nombre_invernadero}.")
                return redirect("maestros:invernadero", invernadero.pk)
    else:
        form = FormularioInvernadero(invernadero=invernadero)
    return render(
        request, "maestros/invernaderos/formulario.html", {"form": form, "invernadero": invernadero, "aviso": aviso}
    )


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def invernadero_baja(request, invernadero_id):
    """Dar de baja un invernadero activo (PROD-BAJ-INV, ``MODALS['inv-baja']`` del prototipo), con confirmación previa.

    - GET: no cambia nada. Un pedido de HTMX recibe solo la ventana (se inserta sobre la ficha); los demás, la ficha con
      la ventana abierta. Con impedimentos (regla 2) la ventana los dice todos, cada uno con cómo resolverlo, y no
      ofrece confirmar.
    - POST: llama al servicio. Si sale bien, vuelve a la ficha con un aviso; si lo rechaza (por ejemplo, apareció un
      impedimento mientras la ventana estaba abierta), la ventana vuelve a mostrarse con el motivo.
    - Uno ya inactivo no se da de baja: vuelve a la ficha con el motivo (D-30).
    """
    invernadero = obtener_invernadero(request.user, invernadero_id)
    if "baja" not in acciones_permitidas(request.user, invernadero):
        messages.error(request, "El invernadero ya está dado de baja.")
        return redirect("maestros:invernadero", invernadero.pk)
    contexto = {"impedimentos": impedimentos_para_baja(request.user, invernadero.pk), "error": ""}
    if request.method == "POST":
        try:
            baja_invernadero(request.user, invernadero.pk)
        except ValidationError as error:
            try:
                contexto["impedimentos"] = impedimentos_para_baja(request.user, invernadero.pk)
            except ValidationError:
                contexto["impedimentos"] = []  # ya no está activo
            if not contexto["impedimentos"]:
                contexto["error"] = error.messages[0]
        else:
            messages.success(request, f"{invernadero.nombre_invernadero} se dio de baja.")
            return redirect("maestros:invernadero", invernadero.pk)
    if request.headers.get("HX-Request") == "true":
        return render(request, "maestros/invernaderos/_ventana_baja.html", {**contexto, "invernadero": invernadero})
    return render(
        request,
        "maestros/invernaderos/ficha.html",
        _contexto_de_la_ficha(request, invernadero, ventana="baja", **contexto),
    )


@rol_requerido(GERENTE)
@require_POST
def invernadero_reactivar(request, invernadero_id):
    """Reactivar un invernadero inactivo (PROD-MOD-INV, ``ACT['inv-react']`` del prototipo), sin ventana: no tiene
    impedimentos y se deshace con la baja. Avisa que los sectores siguen inactivos (regla 6)."""
    try:
        reactivar_invernadero(request.user, invernadero_id)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(
            request, "Invernadero reactivado. Sus sectores siguen inactivos: los reactiva el Agrónomo."
        )
    return redirect("maestros:invernadero", invernadero_id)


# ---- Fragmentos de HTMX del formulario: solo GET, no cambian nada ----


@rol_requerido(GERENTE)
@require_safe
@vary_on_headers("HX-Request")
def campos_direccion(request):
    """Los datos de la dirección del tipo elegido (regla 2 de PROD-ALT-INV): calle y número, o ruta y kilómetro."""
    return render(
        request, "maestros/invernaderos/_campos_direccion.html", {"form": FormularioInvernadero(request.GET)}
    )


@rol_requerido(GERENTE)
@require_safe
@vary_on_headers("HX-Request")
def departamentos(request):
    """Los campos de departamento y localidad de la provincia elegida (regla 3): la localidad se vacía."""
    form = FormularioInvernadero({"provincia": request.GET.get("provincia", "")})
    return render(request, "maestros/invernaderos/_departamento_y_localidad.html", {"form": form})


@rol_requerido(GERENTE)
@require_safe
@vary_on_headers("HX-Request")
def localidades(request):
    """El campo de localidad del departamento elegido (regla 3)."""
    form = FormularioInvernadero({"departamento": request.GET.get("departamento", "")})
    return render(request, "maestros/invernaderos/_localidad.html", {"form": form})
