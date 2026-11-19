# Vistas de maestros para MAE-01a: lista y ficha de invernaderos (PROD-CNS-INV), alta (PROD-ALT-INV) y los fragmentos
# HTMX de las listas encadenadas de Georef. Las vistas solo orquestan: validan la entrada, llaman al servicio y
# renderizan (CLAUDE.md, arquitectura).

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from maestros.forms import FormularioInvernadero
from maestros.servicios.invernaderos import alta_invernadero, consultar_invernaderos, obtener_invernadero

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
    inexistente, 404 (D-28). En MAE-01a no hay botones de modificar ni de baja: llegan en MAE-01b (D-30)."""
    return render(
        request,
        "maestros/invernaderos/ficha.html",
        {"invernadero": obtener_invernadero(request.user, invernadero_id), "es_gerente": request.user.rol == GERENTE},
    )


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
