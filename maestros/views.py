# MAE-04 suma la pantalla «Configuración» (al final del archivo).
# MAE-03 suma la pestaña «Sectores» de la ficha, con la capacidad, y las ventanas de los sectores (al final del archivo).
# Vistas de maestros para MAE-01: lista y ficha de invernaderos (PROD-CNS-INV), alta (PROD-ALT-INV), modificación y
# reactivación (PROD-MOD-INV), baja (PROD-BAJ-INV) y los fragmentos HTMX de las listas encadenadas de Georef. Las vistas
# solo orquestan: validan la entrada, llaman al servicio y renderizan (CLAUDE.md, arquitectura).

from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Transportista, Usuario
from maestros import extensiones
from maestros.forms import (
    FormularioConfiguracion,
    FormularioCultivo,
    FormularioInvernadero,
    FormularioPerfil,
    FormularioSector,
)
from maestros.models import SectorProduccion
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion as api_configuracion
from maestros.servicios import cultivos as api_cultivos
from maestros.servicios import perfil as api_perfil
from maestros.servicios import sectores as api_sectores
from maestros.servicios import transportistas as api_transportistas
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
    """Lo que necesita la ficha: el invernadero, si quien mira es el Gerente, las acciones que le corresponden y la
    tarjeta «Logística» (MAE-05)."""
    return {
        "invernadero": invernadero,
        "es_gerente": request.user.rol == GERENTE,
        "acciones": acciones_permitidas(request.user, invernadero),
        **_logistica(invernadero),
        **_pestana_de_sectores(request, invernadero),
        **_pestanas_registradas(request, invernadero),
        **extra,
    }


def _pestanas_registradas(request, invernadero):
    """Las pestañas que registraron otras apps (PRD-01: «Lotes activos»; ``docs/api/extensiones_de_maestros.md``) y la elegida con
    ``?pestana=<clave>``: sin elegir, o con una clave que no existe o que el actor no ve, queda «Sectores». Cada pestaña es un
    enlace, así que funciona sin JavaScript."""
    pestanas = extensiones.pestanas_de_invernadero(request.user, invernadero)
    clave = request.GET.get("pestana")
    return {
        "pestanas_registradas": pestanas,
        "pestana_elegida": next((p for p in pestanas if p.clave == clave), None),
    }


def _logistica(invernadero):
    """La tarjeta «Logística» (regla 3 de PROD-CNS-INV, D-55): los transportistas del invernadero (una consulta) y, si `comercial`
    registró su punto de extensión, el vehículo, la situación y las entregas de todos juntos (una sola llamada, sin consultas
    por fila). Sin registrante, ``con_logistica`` es falso y la tarjeta no muestra esas columnas."""
    cuentas = invernadero.transportistas()
    datos = extensiones.logistica_de(cuentas) if cuentas else None
    sin_datos = extensiones.Logistica(None, False, 0, None)
    return {
        "transportistas": [
            {"cuenta": cuenta, "logistica": (datos or {}).get(cuenta.pk, sin_datos)} for cuenta in cuentas
        ],
        "con_logistica": datos is not None,
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


# ---- MAE-03: pestaña «Sectores» de la ficha y sus ventanas (PROD-ALT-SCT, PROD-MOD-SCT, PROD-BAJ-SCT, PROD-CNS-SCT) ----
# Cada ventana es una vista con dos formas (D-47, patrón ABM §7): con HTMX (``HX-Request``) devuelve solo la ventana, que
# se inserta sobre la ficha; sin JavaScript devuelve la ficha completa con la ventana abierta (``plantilla_de_ventana``).
# Los formularios envían con un POST común: si sale bien, redirigen a la ficha con un aviso; si no, vuelven a mostrar la
# ventana con los errores por campo. Solo el Agrónomo a cargo llega acá (el Gerente consulta, sin acciones: 403 por rol).

PLANTILLA_FORMULARIO_DE_SECTOR = "maestros/sectores/_ventana_formulario.html"
PLANTILLA_AVISO_DE_SECTOR = "maestros/sectores/_ventana_aviso.html"
PLANTILLA_BAJA_DE_SECTOR = "maestros/sectores/_ventana_baja.html"
PLANTILLA_REACTIVAR_SECTOR = "maestros/sectores/_ventana_reactivar.html"
PLANTILLA_VOLVER_A_SERVICIO = "maestros/sectores/_ventana_volver_a_servicio.html"


def _porcentaje(parte, total):
    """Porcentaje entero de ``parte`` sobre ``total`` para el ancho de una barra (sin decimales: la localización los
    mostraría con coma y el CSS no los entendería)."""
    return round(parte * 100 / total) if total else 0


def _pestana_de_sectores(request, invernadero):
    """Lo que necesita la pestaña «Sectores» y la tarjeta «Capacidad» de la ficha (PROD-CNS-SCT, regla 3 de PROD-CNS-INV): los
    sectores agrupados por tipo de etapa y los dados de baja aparte, cada uno con sus agujeros, su perfil, su contenido y los
    botones que le corresponden a quien mira (``acciones_permitidas``)."""
    lista = list(api_sectores.consultar_sectores(request.user, invernadero.pk))
    agujeros = api_sectores.agujeros_de(lista)
    perfiles = api_sectores.perfiles_de_sectores([s.pk for s in lista])
    contenido = api_sectores.contenido_de_sectores(lista)

    def tarjeta(sector):
        usados = agujeros[sector.pk]
        return {
            "sector": sector,
            "agujeros": usados,
            "perfil": perfiles[sector.pk],
            "contenido": contenido[sector.pk],
            "acciones": api_sectores.acciones_permitidas(request.user, sector),
            "porcentaje_ocupados": _porcentaje(usados.ocupados, usados.total),
            "porcentaje_comprometidos": _porcentaje(usados.comprometidos, usados.total),
        }

    grupos, dados_de_baja = api_sectores.agrupar_sectores(lista)
    capacidad = api_sectores.capacidad_del_invernadero(lista, agujeros)
    en_capacidad = [s for s in lista if s.estado_sector != SectorProduccion.Estado.INACTIVO]
    total = sum(agujeros[s.pk].total for s in en_capacidad)
    ocupados = sum(agujeros[s.pk].ocupados for s in en_capacidad)
    return {
        "grupos_de_sectores": [(grupo, [tarjeta(s) for s in grupo.sectores]) for grupo in grupos],
        "sectores_dados_de_baja": [tarjeta(s) for s in dados_de_baja],
        "capacidad": capacidad,
        "capacidad_total": total,
        "capacidad_ocupados": ocupados,
        "capacidad_porcentaje": _porcentaje(ocupados, total),
        "hay_sectores": bool(lista),
        "puede_agregar_sectores": api_sectores.puede_agregar_sectores(request.user, invernadero),
    }


def _pasar_errores(form, error):
    """Pasa los errores de un ``ValidationError`` del servicio al formulario: por campo si el campo existe y, si no, generales."""
    for campo, errores in error.error_dict.items():
        for e in errores:
            form.add_error(campo if campo in form.fields else None, e)


def _ventana(request, invernadero, plantilla, **contexto):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la ficha completa con la ventana abierta (respaldo sin
    JavaScript)."""
    if request.headers.get("HX-Request") == "true":
        return render(request, plantilla, {"invernadero": invernadero, **contexto})
    return render(
        request,
        "maestros/invernaderos/ficha.html",
        _contexto_de_la_ficha(request, invernadero, plantilla_de_ventana=plantilla, **contexto),
    )


def _sector_de(request, invernadero, sector_id):
    """El sector ``sector_id`` si está en el alcance de quien mira y es de ``invernadero`` (si no, 404)."""
    sector = api_sectores.obtener_sector(request.user, sector_id)
    if sector.invernadero_id != invernadero.pk:
        raise Http404("Ese sector no es de este invernadero.")
    return sector


def _volver_a_la_ficha(invernadero):
    """Vuelve a la ficha del invernadero."""
    return redirect("maestros:invernadero", invernadero.pk)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sector_nuevo(request, invernadero_id):
    """Agregar un sector (PROD-ALT-SCT, ``MODALS['sector-form']`` del prototipo). Solo el Agrónomo a cargo."""
    invernadero = obtener_invernadero(request.user, invernadero_id)
    if request.method == "POST":
        form = FormularioSector(request.POST)
        form.is_valid()  # todos los campos son opcionales; las reglas son del servicio
        try:
            sector = api_sectores.alta_sector(request.user, invernadero.pk, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            messages.success(request, f"Sector {sector.nombre_sector} agregado.")
            return _volver_a_la_ficha(invernadero)
    else:
        form = FormularioSector()
    return _ventana(request, invernadero, PLANTILLA_FORMULARIO_DE_SECTOR, form=form, sector=None, tipo_bloqueado=False)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sector_modificar(request, invernadero_id, sector_id):
    """Modificar un sector (PROD-MOD-SCT, ``MODALS['sector-form']`` del prototipo). Con una advertencia de la regla 4 (el
    último sector activo de una etapa cambia de tipo) muestra la ventana de aviso, con «Volver» (reenvía sin guardar) y
    «Continuar igual» (``advertencia_confirmada``). Un sector dado de baja no se modifica: solo se reactiva."""
    invernadero = obtener_invernadero(request.user, invernadero_id)
    sector = _sector_de(request, invernadero, sector_id)
    if api_sectores.ACCION_MODIFICAR not in api_sectores.acciones_permitidas(request.user, sector):
        messages.error(request, "El sector está dado de baja: solo se puede reactivar.")
        return _volver_a_la_ficha(invernadero)
    agujeros = api_sectores.agujeros_de([sector])[sector.pk]
    contexto = {"sector": sector, "agujeros": agujeros, "tipo_bloqueado": bool(agujeros.ocupados + agujeros.comprometidos)}
    avisos = None
    if request.method == "POST":
        form = FormularioSector(request.POST, sector=sector)
        form.is_valid()
        if "volver" not in request.POST:  # «Volver» de la ventana de aviso reenvía sin guardar
            try:
                api_sectores.modificar_sector(
                    request.user,
                    sector.pk,
                    advertencia_confirmada="advertencia_confirmada" in request.POST,
                    **form.datos_del_servicio(),
                )
            except api_sectores.FaltaConfirmarAdvertencia as falta:
                avisos = falta.avisos
            except ValidationError as error:
                _pasar_errores(form, error)
            else:
                messages.success(request, f"Se guardaron los cambios del sector {form.cleaned_data['nombre'].strip()}.")
                return _volver_a_la_ficha(invernadero)
    else:
        form = FormularioSector(sector=sector)
    plantilla = PLANTILLA_AVISO_DE_SECTOR if avisos else PLANTILLA_FORMULARIO_DE_SECTOR
    return _ventana(request, invernadero, plantilla, form=form, avisos=avisos, **contexto)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sector_baja(request, invernadero_id, sector_id):
    """Dar de baja un sector (PROD-BAJ-SCT, ``MODALS['sector-baja']`` del prototipo), con confirmación previa.

    - GET: no cambia nada. Con impedimentos (reglas 2 y 3) la ventana los dice todos con cómo resolverlos y no ofrece
      confirmar. Sin ellos, pide confirmar y, si es el último sector activo de su tipo (regla 4), muestra la advertencia: la
      ventana es la confirmación.
    - POST: llama al servicio. Si apareció algo nuevo mientras la ventana estaba abierta, la ventana vuelve a mostrarse.
    """
    invernadero = obtener_invernadero(request.user, invernadero_id)
    sector = _sector_de(request, invernadero, sector_id)
    if api_sectores.ACCION_BAJA not in api_sectores.acciones_permitidas(request.user, sector):
        messages.error(request, "El sector ya está dado de baja.")
        return _volver_a_la_ficha(invernadero)
    contexto = {"sector": sector, "impedimentos": api_sectores.impedimentos_para_baja(request.user, sector.pk), "error": ""}
    contexto["avisos"] = [] if contexto["impedimentos"] else api_sectores.avisos_para_baja(request.user, sector.pk)
    if request.method == "POST":
        try:
            api_sectores.baja_sector(
                request.user, sector.pk, advertencia_confirmada="advertencia_confirmada" in request.POST
            )
        except api_sectores.FaltaConfirmarAdvertencia as falta:
            contexto["avisos"] = falta.avisos  # apareció mientras la ventana estaba abierta: sin confirmar
        except ValidationError as error:
            try:
                contexto["impedimentos"] = api_sectores.impedimentos_para_baja(request.user, sector.pk)
            except ValidationError:
                contexto["impedimentos"] = []  # ya no está activo
            if not contexto["impedimentos"]:
                contexto["error"] = error.messages[0]
        else:
            messages.success(request, f"Sector {sector.nombre_sector} dado de baja.")
            return _volver_a_la_ficha(invernadero)
    return _ventana(request, invernadero, PLANTILLA_BAJA_DE_SECTOR, **contexto)


def _confirmar_cambio_de_estado(request, invernadero_id, sector_id, accion, plantilla, servicio, mensaje_de_exito, mensaje_de_rechazo):
    """Ventana de confirmación de un cambio de estado sin validaciones (reactivar o volver a servicio): el GET la muestra sin
    cambiar nada y el POST llama a ``servicio``. Si el estado del sector ya no lo permite, vuelve a la ficha con el motivo."""
    invernadero = obtener_invernadero(request.user, invernadero_id)
    sector = _sector_de(request, invernadero, sector_id)
    if accion not in api_sectores.acciones_permitidas(request.user, sector):
        messages.error(request, mensaje_de_rechazo)
        return _volver_a_la_ficha(invernadero)
    if request.method == "POST":
        try:
            servicio(request.user, sector.pk)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, mensaje_de_exito.format(sector=sector.nombre_sector))
        return _volver_a_la_ficha(invernadero)
    return _ventana(request, invernadero, plantilla, sector=sector)


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sector_reactivar(request, invernadero_id, sector_id):
    """Reactivar un sector dado de baja (PROD-MOD-SCT, postcondición c; ``MODALS['sector-activar']`` del prototipo)."""
    return _confirmar_cambio_de_estado(
        request,
        invernadero_id,
        sector_id,
        api_sectores.ACCION_REACTIVAR,
        PLANTILLA_REACTIVAR_SECTOR,
        api_sectores.reactivar_sector,
        "Sector {sector} activo de nuevo.",
        "El sector no está dado de baja.",
    )


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def sector_volver_a_servicio(request, invernadero_id, sector_id):
    """Volver a activar un sector fuera de servicio (PROD-MOD-SCT, postcondición b; ``MODALS['sector-activar']`` del
    prototipo). Ningún caso de uso de MAE-03 produce ese estado (lo produce PRD-04), pero la ventana ya funciona."""
    return _confirmar_cambio_de_estado(
        request,
        invernadero_id,
        sector_id,
        api_sectores.ACCION_VOLVER_A_SERVICIO,
        PLANTILLA_VOLVER_A_SERVICIO,
        api_sectores.volver_a_servicio_sector,
        "Sector {sector} activo de nuevo.",
        "El sector no está fuera de servicio.",
    )


# ---- MAE-03: «Producción» → «Cultivos y variedades» (PROD-ALT-CLT, PROD-MOD-CLT, PROD-BAJ-CLT, PROD-CNS-CLT) ----
# Solo el Agrónomo: el Gerente no consulta cultivos (regla 4 de PROD-CNS-CLT), así que toda ruta de cultivos le da 404, con
# HTMX o sin JavaScript (no hay botón ni pestaña que lo lleve ahí). Las ventanas tienen las dos formas de las de sectores:
# fragmento con HTMX y, sin JavaScript, la página completa con la ventana abierta. Cualquier Agrónomo activo hace altas,
# modificaciones y bajas: no hay «a cargo». Los botones y el cuerpo de variedades salen de ``variedades_de_cultivos``
# (``registrar_variedades_de_cultivo``, de INV-03): hasta entonces, «No tiene variedades» y sin botones de variedad.

PLANTILLA_FORMULARIO_DE_CULTIVO = "maestros/cultivos/_ventana_formulario.html"
PLANTILLA_BAJA_DE_CULTIVO = "maestros/cultivos/_ventana_baja.html"


def _ocultar_al_gerente(request):
    """Regla 4 de PROD-CNS-CLT: el Gerente no ve cultivos; si entra por la URL, 404 (sin pista de que existen)."""
    if request.user.rol == GERENTE:
        raise Http404("No existe esa página.")


def _contexto_de_cultivos(request, **extra):
    """Lo que necesita la página de cultivos: cada cultivo con sus botones (``acciones_permitidas``) y la cabecera y el cuerpo
    de sus variedades (``variedades_de_cultivos``)."""
    lista = list(api_cultivos.consultar_cultivos(request.user))
    variedades = api_cultivos.variedades_de_cultivos(request.user, lista)
    return {
        "tarjetas_de_cultivos": [
            {
                "cultivo": cultivo,
                "acciones": api_cultivos.acciones_permitidas(request.user, cultivo),
                "cabecera": variedades[cultivo.pk].cabecera,
                "cuerpo": variedades[cultivo.pk].cuerpo,
            }
            for cultivo in lista
        ],
        "es_gerente": False,
        **extra,
    }


def _ventana_de_cultivo(request, plantilla, **contexto):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la página de cultivos con la ventana abierta (respaldo
    sin JavaScript)."""
    if request.headers.get("HX-Request") == "true":
        return render(request, plantilla, contexto)
    return render(
        request,
        "maestros/cultivos/lista.html",
        _contexto_de_cultivos(request, plantilla_de_ventana=plantilla, **contexto),
    )


@rol_requerido(GERENTE, AGRONOMO)
def cultivos_y_variedades(request):
    """«Cultivos y variedades» (PROD-CNS-CLT, ``cultivosTab`` del prototipo): tarjetas por cultivo, activos primero. El Gerente
    no la ve (regla 4): 404. No audita (regla 5)."""
    _ocultar_al_gerente(request)  # antes de mirar el método: al Gerente nunca un 405 que delate la ruta
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "maestros/cultivos/lista.html", _contexto_de_cultivos(request))


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def cultivo_nuevo(request):
    """Nuevo cultivo (PROD-ALT-CLT, ``MODALS.cultivo`` del prototipo). Cualquier Agrónomo activo."""
    _ocultar_al_gerente(request)
    if request.method == "POST":
        form = FormularioCultivo(request.POST)
        form.is_valid()
        try:
            cultivo = api_cultivos.alta_cultivo(request.user, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            messages.success(request, f"Cultivo creado: {cultivo.nombre_cultivo}.")
            return redirect("maestros:cultivos")
    else:
        form = FormularioCultivo()
    return _ventana_de_cultivo(request, PLANTILLA_FORMULARIO_DE_CULTIVO, form=form, cultivo=None, aviso=None)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def cultivo_renombrar(request, cultivo_id):
    """Renombrar un cultivo (PROD-MOD-CLT, ``MODALS.cultivo`` del prototipo). Antes de confirmar informa cuántas semillas
    cambian de nombre y a qué invernaderos se les avisa (regla 3). Uno inactivo no se modifica: solo se reactiva."""
    _ocultar_al_gerente(request)
    cultivo = api_cultivos.obtener_cultivo(request.user, cultivo_id)
    if api_cultivos.ACCION_MODIFICAR not in api_cultivos.acciones_permitidas(request.user, cultivo):
        messages.error(request, "El cultivo está inactivo: solo se puede reactivar.")
        return redirect("maestros:cultivos")
    aviso = api_cultivos.aviso_de_renombre(request.user, cultivo.pk)
    if request.method == "POST":
        form = FormularioCultivo(request.POST)
        form.is_valid()
        try:
            api_cultivos.modificar_cultivo(request.user, cultivo.pk, **form.datos_del_servicio())
        except ValidationError as error:
            _pasar_errores(form, error)
        else:
            cantidad = aviso.cantidad_de_semillas
            semillas = f" Se actualizó el nombre de {cantidad} semilla{'s' if cantidad != 1 else ''}." if cantidad else ""
            messages.success(request, f"Se guardó el cultivo {form.cleaned_data['nombre'].strip()}.{semillas}")
            return redirect("maestros:cultivos")
    else:
        form = FormularioCultivo(cultivo=cultivo)
    return _ventana_de_cultivo(request, PLANTILLA_FORMULARIO_DE_CULTIVO, form=form, cultivo=cultivo, aviso=aviso)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def cultivo_baja(request, cultivo_id):
    """Dar de baja un cultivo (PROD-BAJ-CLT, ``MODALS['cult-baja']`` del prototipo), con confirmación previa. Con variedades
    activas (precondición c y regla 2) la ventana dice cuántas son y no ofrece confirmar: primero se dan de baja con Baja
    Variedad. Abrirla (GET) no cambia nada; la baja es un POST."""
    _ocultar_al_gerente(request)
    cultivo = api_cultivos.obtener_cultivo(request.user, cultivo_id)
    if api_cultivos.ACCION_BAJA not in api_cultivos.acciones_permitidas(request.user, cultivo):
        messages.error(request, "El cultivo ya está dado de baja.")
        return redirect("maestros:cultivos")
    error = ""
    if request.method == "POST":
        try:
            api_cultivos.baja_cultivo(request.user, cultivo.pk)
        except ValidationError as rechazo:
            error = rechazo.messages[0]
            cultivo = api_cultivos.obtener_cultivo(request.user, cultivo.pk)  # el conteo de ahora
        else:
            messages.success(request, f"El cultivo {cultivo.nombre_cultivo} quedó inactivo.")
            return redirect("maestros:cultivos")
    return _ventana_de_cultivo(request, PLANTILLA_BAJA_DE_CULTIVO, cultivo=cultivo, error=error)


@rol_requerido(GERENTE, AGRONOMO)
def cultivo_reactivar(request, cultivo_id):
    """Reactivar un cultivo dado de baja (PROD-MOD-CLT, postcondición c; ``ACT['cult-react']`` del prototipo), sin ventana: no
    tiene validaciones y no reactiva sus variedades (regla 6)."""
    _ocultar_al_gerente(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    cultivo = api_cultivos.obtener_cultivo(request.user, cultivo_id)
    try:
        api_cultivos.reactivar_cultivo(request.user, cultivo.pk)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"El cultivo {cultivo.nombre_cultivo} está activo de nuevo.")
    return redirect("maestros:cultivos")


# ---- MAE-04: «Configuración» del Gerente (ADM-MOD-CFG y ADM-MOD-ORG; VIEWS.config del prototipo) ----
# Dos pestañas, cada una con su formulario y su botón «Guardar cambios». Con HTMX el formulario se guarda sin recargar y, si
# hay errores, vuelve el formulario con ellos (por campo); si sale bien, ``HX-Redirect`` recarga la página para que el color
# nuevo rija desde esa carga (D-48) y se vea el aviso. Sin JavaScript es un POST común con redirección. Las vistas de lectura
# no se auditan (SEG-14). Solo el Gerente llega acá: otros roles, 403; sin sesión, inicio de sesión.

PESTANA_PARAMETROS = "parametros"
PESTANA_ORGANIZACION = "organizacion"
MENSAJE_GUARDADO = "Se guardó la configuración."


def _es_htmx(request):
    """True si el pedido lo hizo HTMX (``HX-Request``)."""
    return request.headers.get("HX-Request") == "true"


def _advertencias_de_lo_escrito(form, configuracion):
    """Las advertencias de la regla 5 para lo que la persona escribió (o, donde no es un entero, lo guardado)."""
    valores = {}
    for campo in ("dias_horizonte_cosecha", "dias_pre_reserva_suministro"):
        escrito = str(form.data.get(campo, "")).strip() if form.is_bound else ""
        valores[campo] = int(escrito) if escrito.isdigit() else getattr(configuracion, campo)
    return api_configuracion.advertencias_de(valores)


def _contexto_de_configuracion(pestana, form_parametros=None, form_perfil=None):
    """Lo que dibuja la pantalla: la pestaña activa, su formulario (los valores guardados si no viene uno con errores) y,
    en los parámetros, la advertencia de la regla 5 junto al formulario."""
    contexto = {"pestana": pestana}
    if pestana == PESTANA_ORGANIZACION:
        contexto["form"] = form_perfil or FormularioPerfil(perfil=api_perfil.obtener())
    else:
        configuracion = api_configuracion.obtener()
        form = form_parametros or FormularioConfiguracion(configuracion=configuracion)
        contexto["form"] = form
        contexto["advertencias"] = _advertencias_de_lo_escrito(form, configuracion)
    return contexto


def _pasar_errores_de_campo(form, error):
    """Pasa los errores de un ``ValidationError`` del servicio al formulario, cada uno en su campo."""
    for campo, errores in error.error_dict.items():
        for e in errores:
            form.add_error(campo if campo in form.fields else None, e)


@rol_requerido(GERENTE)
@require_safe
def configuracion(request):
    """Pantalla «Configuración» (ADM-MOD-CFG y ADM-MOD-ORG): «Parámetros operativos» por defecto y «Organización» con
    ``?pestana=organizacion``. Muestra los valores actuales (regla 1 de los dos casos de uso)."""
    pestana = PESTANA_ORGANIZACION if request.GET.get("pestana") == PESTANA_ORGANIZACION else PESTANA_PARAMETROS
    return render(request, "maestros/configuracion/pantalla.html", _contexto_de_configuracion(pestana))


def _guardar(request, pestana, formulario, servicio, plantilla_fragmento):
    """Lo común de las dos pestañas: valida con el servicio (todo o nada), y si sale bien avisa y recarga la pantalla; si no,
    muestra los errores por campo (el fragmento con HTMX, la página entera sin JavaScript)."""
    form = formulario(request.POST)
    form.is_valid()  # los campos son de texto libre; las reglas son del servicio
    try:
        servicio(request.user, **form.datos_del_servicio())
    except ValidationError as error:
        _pasar_errores_de_campo(form, error)
    else:
        messages.success(request, MENSAJE_GUARDADO)
        destino = reverse("configuracion:pantalla") + (f"?pestana={pestana}" if pestana != PESTANA_PARAMETROS else "")
        if _es_htmx(request):
            respuesta = HttpResponse(status=204)
            respuesta["HX-Redirect"] = destino
            return respuesta
        return redirect(destino)
    contexto = _contexto_de_configuracion(
        pestana,
        form_parametros=form if pestana == PESTANA_PARAMETROS else None,
        form_perfil=form if pestana == PESTANA_ORGANIZACION else None,
    )
    if _es_htmx(request):
        return render(request, plantilla_fragmento, contexto)
    return render(request, "maestros/configuracion/pantalla.html", contexto)


@rol_requerido(GERENTE)
@require_POST
@never_cache
@vary_on_headers("HX-Request")
def configuracion_guardar_parametros(request):
    """Guarda la pestaña «Parámetros operativos» (ADM-MOD-CFG): todo o nada, con la advertencia de la regla 5 junto al
    formulario."""
    return _guardar(
        request,
        PESTANA_PARAMETROS,
        FormularioConfiguracion,
        lambda actor, **datos: api_configuracion.modificar_configuracion(actor, **datos),
        "maestros/configuracion/_parametros.html",
    )


@rol_requerido(GERENTE)
@require_POST
@never_cache
@vary_on_headers("HX-Request")
def configuracion_guardar_organizacion(request):
    """Guarda la pestaña «Organización» (ADM-MOD-ORG): todo o nada. Sin el campo del logo (D-45)."""
    return _guardar(
        request,
        PESTANA_ORGANIZACION,
        FormularioPerfil,
        lambda actor, **datos: api_perfil.modificar_perfil(actor, **datos),
        "maestros/configuracion/_organizacion.html",
    )


# ---- MAE-05 (D-55): transportistas de un invernadero, desde la tarjeta «Logística» de la ficha ----

# Los códigos de los impedimentos de las reglas 9 y 10 (los registra `comercial`): la ventana los muestra y no ofrece confirmar.
CODIGOS_DE_IMPEDIMENTO = {"transportista_en_ruta", "transportista_con_entregas"}


def _nombre_de(cuenta):
    """El nombre con el que se ve a una cuenta en los avisos."""
    return cuenta.get_full_name() or cuenta.email


def _url_de_entregas(cuenta):
    """«Ver sus entregas» (COM-ASG-TRP): la URL que dio `comercial`, o ``None`` si no hay registrante o no la dio."""
    datos = extensiones.logistica_de([cuenta])
    return datos[cuenta.pk].url_entregas if datos and cuenta.pk in datos else None


def _ventana_de_transportista(request, invernadero, plantilla, error=None, cuenta=None, **contexto):
    """La ventana ``plantilla`` con el resultado de un rechazo del servicio (``error``, un ``ValidationError``): si lleva algún
    impedimento de las reglas 9 y 10, la ventana los lista (todos) y no ofrece confirmar; si no, muestra el motivo."""
    if error is not None:
        codigos = [e.code for errores in getattr(error, "error_dict", {}).values() for e in errores]
        if any(c in CODIGOS_DE_IMPEDIMENTO for c in codigos):
            contexto["impedimentos"] = error.messages
            contexto["url_entregas"] = _url_de_entregas(cuenta) if cuenta is not None else None
        else:
            contexto["error"] = error.messages[0]
    return _ventana(request, invernadero, plantilla, **contexto)


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def transportista_agregar(request, invernadero_id):
    """Agregar o trasladar un transportista (PROD-MOD-INV reglas 8 a 10, ``ventanaAgregar`` del prototipo). Solo el Gerente.

    - GET: no cambia nada; lista los candidatos (los activos que no trabajan para este invernadero, con su invernadero actual).
    - POST con un candidato: si es un traslado sin confirmar, la ventana vuelve con el aviso y «Confirmar traslado»; si hay
      impedimentos (reglas 9 y 10), los lista (con «Ver sus entregas» si `comercial` dio la URL) y no ofrece confirmar; si sale
      bien, vuelve a la ficha con un aviso breve (D-29).
    - Un invernadero inactivo no se modifica (regla 5): vuelve a la ficha con el motivo (D-30).
    """
    invernadero = obtener_invernadero(request.user, invernadero_id)
    if "modificar" not in acciones_permitidas(request.user, invernadero):
        messages.error(request, "El invernadero está inactivo: solo se puede reactivar.")
        return redirect("maestros:invernadero", invernadero.pk)
    plantilla = "maestros/invernaderos/_ventana_agregar_transportista.html"
    candidatos = api_transportistas.candidatos(request.user, invernadero.pk)
    if request.method == "POST":
        try:
            elegido = int(request.POST.get("transportista_id", ""))
        except ValueError:
            return _ventana_de_transportista(
                request, invernadero, plantilla, candidatos=candidatos, error=ValidationError("Elegí un transportista.")
            )
        candidato = next((c for c in candidatos if c.transportista.pk == elegido), None)
        try:
            fila = api_transportistas.agregar_transportista(
                request.user,
                invernadero.pk,
                elegido,
                traslado_confirmado="traslado_confirmado" in request.POST,
            )
        except api_transportistas.FaltaConfirmarTraslado:
            return _ventana(request, invernadero, plantilla, candidatos=candidatos, traslado={"candidato": candidato})
        except ValidationError as error:
            cuenta = candidato.transportista if candidato else None
            return _ventana_de_transportista(
                request, invernadero, plantilla, error=error, cuenta=cuenta, candidatos=candidatos, elegido=elegido
            )
        nombre = _nombre_de(fila.transportista)
        if candidato is not None and candidato.invernadero is not None:
            aviso = f"{nombre} pasó de {candidato.invernadero.nombre_invernadero} a {invernadero.nombre_invernadero}."
        else:
            aviso = f"{nombre} ahora trabaja para {invernadero.nombre_invernadero}."
        messages.success(request, aviso)
        return _volver_a_la_ficha(invernadero)
    return _ventana(request, invernadero, plantilla, candidatos=candidatos)


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def transportista_quitar(request, invernadero_id, transportista_id):
    """Quitar un transportista del invernadero (PROD-MOD-INV reglas 5, 9 y 10, ``ventanaQuitar`` del prototipo). Solo el Gerente.

    - GET: no cambia nada; muestra la confirmación o, si hay impedimentos, los lista y no ofrece confirmar.
    - POST: quita y vuelve a la ficha con un aviso breve (D-29). Si el servicio lo rechaza, la ventana vuelve con el motivo.
    - Un invernadero inactivo, o un transportista que no trabaja para él, vuelve a la ficha con el motivo (D-30).
    """
    invernadero = obtener_invernadero(request.user, invernadero_id)
    cuenta = get_object_or_404(Transportista, pk=transportista_id)
    plantilla = "maestros/invernaderos/_ventana_quitar_transportista.html"
    try:
        impedimentos = api_transportistas.impedimentos_para_quitar(request.user, invernadero.pk, cuenta.pk)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return _volver_a_la_ficha(invernadero)
    if request.method == "POST":
        try:
            api_transportistas.quitar_transportista(request.user, invernadero.pk, cuenta.pk)
        except ValidationError as error:
            return _ventana_de_transportista(
                request, invernadero, plantilla, error=error, cuenta=cuenta, transportista=cuenta
            )
        messages.success(request, f"{_nombre_de(cuenta)} ya no trabaja para {invernadero.nombre_invernadero}.")
        return _volver_a_la_ficha(invernadero)
    contexto = {"transportista": cuenta}
    if impedimentos:
        contexto["impedimentos"] = [f"{i.texto} {i.como_resolver}" for i in impedimentos]
        contexto["url_entregas"] = _url_de_entregas(cuenta)
    return _ventana(request, invernadero, plantilla, **contexto)


# ---- MAE-02c (CU-46): consulta de alertas ----
# Solo el Gerente y el Agrónomo (decisión 2 de MAE-02c: son los únicos que reciben alertas; cualquier otro rol, 403).

_MAXIMO_ID = 2**63 - 1  # un id más grande no cabe en la base: no puede ser el de ninguna alerta ni invernadero


def _id_de_filtro(texto):
    """El id numérico de un filtro del formulario GET. ``(None, False)`` si está vacío (no filtra), ``(id, False)`` si es un
    número válido y ``(None, True)`` si no lo es (``?invernadero=abc``): la lista queda vacía, sin error y sin revelar nada."""
    if not texto:
        return None, False
    try:
        valor = int(texto)
    except ValueError:
        return None, True
    return (valor, False) if 0 < valor <= _MAXIMO_ID else (None, True)


@rol_requerido(GERENTE, AGRONOMO)
@require_safe
@vary_on_headers("HX-Request")
def alertas(request):
    """CU-46: listado de las alertas activas del usuario, filtrable por invernadero y por tipo (R2 a R5). No cambia nada: no
    marca ninguna como leída (eso es el detalle). Con HTMX (``HX-Request``) devuelve solo la tabla (R8); sin JavaScript, la
    página completa."""
    invernadero = request.GET.get("invernadero", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    invernadero_id, invalido = _id_de_filtro(invernadero)
    lista = [] if invalido else api_alertas.consultar_alertas(request.user, invernadero_id=invernadero_id, tipo=tipo or None)
    contexto = {"alertas": lista, "hay_filtros": bool(invernadero or tipo)}
    if _es_htmx(request):
        return render(request, "maestros/alertas/_tabla.html", contexto)
    contexto |= {
        "filtros": api_alertas.filtros_de_alertas(request.user),
        "f_invernadero": invernadero,
        "f_tipo": tipo,
    }
    return render(request, "maestros/alertas/lista.html", contexto)


@rol_requerido(GERENTE, AGRONOMO)
@require_GET
@never_cache
def alerta(request, alerta_id):
    """CU-46, R6 y R7: el detalle de una alerta. Abrirlo la marca «leída» (``detalle_de_alerta`` llama a ``abrir_alerta``), así
    que no se guarda en la caché del navegador ni responde a HEAD. Una alerta que no existe da 404 y una ajena, 403 (D-28)."""
    return render(request, "maestros/alertas/detalle.html", {"detalle": api_alertas.detalle_de_alerta(request.user, alerta_id)})
