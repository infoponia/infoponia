# Vistas de variedades (INV-03, paso 8): la consulta dentro de «Cultivos y variedades» (PROD-CNS-VAR), el formulario de alta y de modificación con
# su resumen y la advertencia de rangos (PROD-ALT-VAR y PROD-MOD-VAR), «Qué sigue» tras el alta, la baja (PROD-BAJ-VAR) y la reactivación.
# Las vistas solo orquestan: validan la entrada, llaman al servicio y renderizan (CLAUDE.md, arquitectura). Todas exigen un Agrónomo: el
# Gerente no consulta variedades (regla 5 de PROD-CNS-VAR), así que toda ruta de variedades le da 404, con HTMX o sin JavaScript; los demás
# roles reciben 403 (``rol_requerido``). La consulta no se audita (SEG-14).
#
# Formulario en pasos, sin estado en el servidor (docs de INV-03, «Resumen antes de confirmar»): cada paso reenvía todo lo escrito y el
# campo ``accion`` dice qué se quiere: ``revisar`` (valida y muestra el resumen), ``volver`` (vuelve a editar sin validar), ``actualizar``
# (redibuja las etapas del perfil sin validar: respaldo sin JavaScript), ``guardar`` y ``guardar_igual`` (confirma; el servicio vuelve a
# validar todo dentro de su transacción). HTMX solo redibuja las etapas al cambiar el perfil (``etapas_del_perfil``, sin validar).
#
# El registrante ``variedades_de_cultivos`` entrega a `maestros` el HTML de la cabecera y del cuerpo de cada tarjeta de cultivo
# (``registrar_variedades_de_cultivo``, regla A4 de D-37). Como no recibe el pedido, ninguno de los dos lleva formularios con CSRF: la
# reactivación abre una página de confirmación.

from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers
from django.db.models.functions import Lower

from core.acceso import rol_requerido
from core.models import Usuario
from inventario import forms
from inventario.models import InsumoInvernadero
from inventario.servicios import ciclos as api_ciclos
from inventario.servicios import variedades as api
from inventario.servicios.insumos import _nombre_del_agronomo
from maestros.extensiones import VariedadesDelCultivo
from maestros.models import Cultivo, Invernadero, TipoEtapa, Variedad
from maestros.servicios.sectores import FaltaConfirmarAdvertencia

AGRONOMO = Usuario.Rol.AGRONOMO
GERENTE = Usuario.Rol.GERENTE

# Cómo se llama cada variable en la advertencia de rangos.
NOMBRES_DE_VARIABLE = {
    "temp_ambiente": "temperatura ambiente",
    "humedad": "humedad",
    "intensidad_luz": "intensidad lumínica",
    "fotoperiodo": "fotoperíodo",
}


def _ocultar_al_gerente(request):
    """Regla 5 de PROD-CNS-VAR: el Gerente no consulta variedades; si entra por la URL, 404 (sin pista de que existen)."""
    if request.user.rol == GERENTE:
        raise Http404("No existe esa página.")


def _clase_de_etapa(codigo):
    """La clase de color de un tipo de etapa (``--e-ger``, ``--e-cre``…)."""
    return TipoEtapa.CLASES_DE_COLOR.get(codigo, "ger")


def _ciclo_para_mostrar(etapas):
    """Las etapas de ``ciclos.etapas_de`` como ``{nombre, dias, clase}`` para el diagrama del ciclo."""
    return [{"nombre": e.nombre, "dias": e.duracion_dias, "clase": _clase_de_etapa(e.codigo)} for e in etapas]


def _dias_hasta_maduracion(etapas):
    """Los días hasta entrar en Maduración: la suma de las etapas anteriores a ella (regla 5 de PROD-ALT-VAR)."""
    return sum(e.duracion_dias for e in etapas if e.codigo != api_ciclos.MADURACION)


# ---- Consulta dentro de «Cultivos y variedades» (PROD-CNS-VAR): el registrante de `maestros` ----


def variedades_de_cultivos(actor, cultivos):
    """El registrante de ``registrar_variedades_de_cultivo`` (docs/api/extensiones_de_maestros.md, «Cultivos»): ``{cultivo_id:
    VariedadesDelCultivo(cabecera, cuerpo)}``. La cabecera lleva «+ Variedad» (solo con el cultivo activo) y el cuerpo la tabla de
    variedades (reglas 1 a 4 de PROD-CNS-VAR). Cantidad fija de consultas para todos los cultivos, sin una por fila."""
    cultivos = list(cultivos)
    lista = list(
        Variedad.objects.filter(cultivo__in=cultivos)
        .select_related("cultivo")
        .order_by("estado_variedad", Lower("nombre_variedad"), "id")
    )
    ids = [v.pk for v in lista]
    etapas = api_ciclos.etapas_de(ids)
    semillas = api.semilla_de(ids)
    habilitada = defaultdict(list)
    for variedad_id, invernadero in (
        InsumoInvernadero.objects.filter(
            insumo__semilla__variedad_id__in=ids, estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO
        )
        .order_by("invernadero__nombre_invernadero", "id")
        .values_list("insumo__semilla__variedad_id", "invernadero__nombre_invernadero")
    ):
        habilitada[variedad_id].append(invernadero)
    acciones = api.acciones_de(actor, lista)
    filas = defaultdict(list)
    for variedad in lista:
        filas[variedad.cultivo_id].append(
            {
                "variedad": variedad,
                "ciclo": _ciclo_para_mostrar(etapas[variedad.pk]),
                "dias": sum(e.duracion_dias for e in etapas[variedad.pk]),
                "semilla": semillas.get(variedad.pk),
                "habilitada_en": habilitada.get(variedad.pk, []),
                "acciones": acciones[variedad.pk],
            }
        )
    return {
        cultivo.pk: VariedadesDelCultivo(
            mark_safe(render_to_string("inventario/variedades/_cabecera.html", {"cultivo": cultivo})),
            mark_safe(render_to_string("inventario/variedades/_cuerpo.html", {"filas": filas.get(cultivo.pk, []), "cultivo": cultivo})),
        )
        for cultivo in cultivos
    }


# ---- Formulario de alta y de modificación ----


def _quienes_la_usan(variedad, actor):
    """Los otros invernaderos que usan la variedad, con su Agrónomo (regla 3 de PROD-CNS-VAR), por nombre; sin los del propio actor."""
    usan = api.invernaderos_que_usan([variedad.pk])[variedad.pk]
    invernaderos = Invernadero.objects.filter(pk__in=usan).select_related("agronomo").order_by("nombre_invernadero", "id")
    return [f"{g.nombre_invernadero} ({_nombre_del_agronomo(g)})" for g in invernaderos if g.agronomo_id != actor.pk]


def _pasar_errores(form, error):
    """Pasa los errores del servicio al formulario: por campo si el campo existe y, si no (``etapas`` o generales), al aviso general."""
    for campo, errores in error.error_dict.items():
        for e in errores:
            form.add_error(campo if campo in form.fields else None, e)


def _contexto_del_formulario(request, cultivo, variedad, **extra):
    """Lo común de las páginas del formulario: el cultivo, la variedad (``None`` en el alta), lo que ya tiene de uso y sus acciones."""
    contexto = {"cultivo": cultivo, "variedad": variedad, "es_gerente": False, **extra}
    if variedad is not None:
        etapas = api_ciclos.etapas_de([variedad.pk])[variedad.pk]
        semilla = api.semilla_de([variedad.pk]).get(variedad.pk)
        contexto.update(
            acciones=api.acciones_permitidas(request.user, variedad),
            semilla=semilla,
            habilitada_en=sorted(
                InsumoInvernadero.objects.filter(insumo=semilla, estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO)
                .values_list("invernadero__nombre_invernadero", flat=True)
            ) if semilla else [],
            ciclo_guardado=_ciclo_para_mostrar(etapas),
            dias_guardados=sum(e.duracion_dias for e in etapas),
            maduracion_guardada=_dias_hasta_maduracion(etapas),
            otros=_quienes_la_usan(variedad, request.user),
        )
    return contexto


def _formulario(request, cultivo, variedad, datos=None):
    """El ``FormularioVariedad`` de la pantalla: vacío (alta), con lo guardado (detalle y modificación) o con lo enviado (``datos``)."""
    tipos = list(TipoEtapa.objects.all())
    argumentos = {"tipos": tipos}
    if variedad is not None:
        uso = api.uso_de_variedades([variedad.pk])[variedad.pk]
        argumentos.update(
            variedad=variedad,
            etapas_actuales=api_ciclos.etapas_de([variedad.pk])[variedad.pk],
            etapas_bloqueadas=uso.con_lotes,
            perfil_bloqueado=bool(uso.lotes_activos or uso.ordenes_a_realizar),
        )
    return forms.FormularioVariedad(datos, **argumentos) if datos is not None else forms.FormularioVariedad(**argumentos)


def _rotulo_del_perfil(codigo):
    return dict(Variedad._meta.get_field("perfil_familia").choices).get(codigo, codigo)


def _numero(texto):
    """Un número escrito (con coma o punto) como texto de pantalla, sin ceros de más."""
    return forms.texto_de_numero(Decimal(texto.replace(",", ".")))


def _filas_del_resumen(form, cambios, variedad):
    """Las filas del resumen: ``(rótulo, valor nuevo, valor anterior o None)``. El anterior solo si cambió (regla 8 de PROD-MOD-VAR)."""
    def antes(campo):
        return cambios[campo][0] if campo in cambios else None

    filas = [("Nombre", form.valor("nombre"), antes("nombre"))]
    anterior = antes("perfil_familia")
    filas.append(("Perfil familiar", _rotulo_del_perfil(form.perfil), _rotulo_del_perfil(anterior) if anterior else None))
    for variable, titulo, unidad, _genero in forms.RANGOS_DEL_FORMULARIO:
        minimo, maximo = f"{variable}_min", f"{variable}_max"
        nuevo = f"{_numero(form.valor(minimo))} a {_numero(form.valor(maximo))} {unidad}"
        previo = None
        if minimo in cambios or maximo in cambios:
            previo_min = cambios[minimo][0] if minimo in cambios else forms.texto_de_numero(getattr(variedad, minimo))
            previo_max = cambios[maximo][0] if maximo in cambios else forms.texto_de_numero(getattr(variedad, maximo))
            previo = f"{_numero(previo_min)} a {_numero(previo_max)} {unidad}"
        filas.append((titulo, nuevo, previo))
    for campo, titulo, unidad in (
        ("duracion_post_cosecha", "Postcosecha", "días"),
        ("peso_promedio_planta", "Peso promedio por planta", "g"),
    ):
        filas.append((titulo, f"{form.valor(campo)} {unidad}", f"{antes(campo)} {unidad}" if antes(campo) else None))
    return filas


def _etapas_del_resumen(form):
    """Las etapas que se enviaron, para el diagrama del resumen: ``{nombre, dias, clase}`` (ya validadas por el servicio)."""
    return [
        {"nombre": t.nombre_etapa, "dias": int(form.valor(f"duracion_{t.codigo}")), "clase": _clase_de_etapa(t.codigo)}
        for t in form.tipos
        if form.se_envia(t)
    ]


def _incompatibilidades_para_mostrar(advertencias):
    """Las ``Incompatibilidad`` de la advertencia de rangos con los nombres a la vista: «Invernadero Norte: temperatura ambiente (con
    Lechuga Romana)»."""
    invernaderos = {g.pk: g.nombre_invernadero for g in Invernadero.objects.filter(pk__in={a.invernadero_id for a in advertencias})}
    otras = {v.pk: f"{v.cultivo.nombre_cultivo} {v.nombre_variedad}" for v in Variedad.objects.filter(pk__in={a.variedad_id for a in advertencias}).select_related("cultivo")}
    return [
        {
            "invernadero": invernaderos.get(a.invernadero_id, "—"),
            "variable": NOMBRES_DE_VARIABLE.get(a.variable, a.variable),
            "con": otras.get(a.variedad_id, "otra variedad"),
        }
        for a in advertencias
    ]


def _pagina_de_formulario(request, cultivo, variedad, form, **extra):
    """La página del formulario (alta, modificación o detalle) con ``form``."""
    contexto = _contexto_del_formulario(request, cultivo, variedad, form=form, **extra)
    contexto["solo_lectura"] = variedad is not None and not contexto["acciones"].modificar
    if contexto["solo_lectura"] and not form.is_bound:
        for campo in form.fields.values():
            campo.disabled = True
    return render(request, "inventario/variedades/formulario.html", contexto)


def _pagina_de_resumen(request, cultivo, variedad, form, resumen, **extra):
    """La página del resumen (paso 2): lo escrito, los valores anteriores y lo que sigue al confirmar."""
    cambios = getattr(resumen, "cambios", {})
    contexto = _contexto_del_formulario(
        request,
        cultivo,
        variedad,
        form=form,
        resumen=resumen,
        filas=_filas_del_resumen(form, cambios, variedad),
        ciclo=_etapas_del_resumen(form),
        cambio_de_etapas="etapas" in cambios,
        nombre_semilla=resumen.nombre_semilla,
        **extra,
    )
    if variedad is not None and not resumen.nombre_semilla:
        contexto["nombre_semilla"] = contexto["semilla"].nombre_insumo if contexto["semilla"] else ""
    return render(request, "inventario/variedades/resumen.html", contexto)


def _trabajar_el_formulario(request, cultivo, variedad):
    """El corazón de las dos pantallas (alta si ``variedad`` es ``None``, modificación y detalle si no). Ver el comentario del módulo."""
    if request.method != "POST":
        return _pagina_de_formulario(request, cultivo, variedad, _formulario(request, cultivo, variedad))
    detalle = reverse("variedades:variedad", args=[variedad.pk]) if variedad is not None else reverse("variedades:variedad_nueva", args=[cultivo.pk])
    if variedad is not None and not api.acciones_permitidas(request.user, variedad).modificar:
        messages.error(request, "Esa variedad no se puede modificar: está inactiva o no podés gestionarla.")
        return redirect(detalle)
    form = _formulario(request, cultivo, variedad, request.POST)
    form.is_valid()
    accion = request.POST.get("accion", "revisar")
    if accion in ("actualizar", "volver"):  # sin validar: solo vuelve a mostrar lo escrito (con las etapas del perfil)
        return _pagina_de_formulario(request, cultivo, variedad, form)
    datos = form.datos_del_servicio()
    try:
        if accion == "revisar":
            resumen = (
                api.resumen_de_alta(request.user, cultivo.pk, datos)
                if variedad is None
                else api.resumen_de_modificacion(request.user, variedad.pk, datos)
            )
            return _pagina_de_resumen(request, cultivo, variedad, form, resumen)
        if variedad is None:
            nueva = api.alta_variedad(request.user, cultivo.pk, datos)
            return redirect("variedades:variedad_creada", variedad_id=nueva.pk)
        guardada = api.modificar_variedad(request.user, variedad.pk, datos, advertencia_confirmada=accion == "guardar_igual")
    except ValidationError as error:
        if hasattr(error, "error_dict"):
            _pasar_errores(form, error)
        else:
            form.add_error(None, error)
        return _pagina_de_formulario(request, cultivo, variedad, form)
    except FaltaConfirmarAdvertencia as falta:
        resumen = api.resumen_de_modificacion(request.user, variedad.pk, datos)
        return _pagina_de_resumen(
            request, cultivo, variedad, form, resumen, incompatibilidades=_incompatibilidades_para_mostrar(falta.avisos)
        )
    messages.success(request, f"Se guardaron los cambios de {cultivo.nombre_cultivo} {guardada.nombre_variedad}.")
    return redirect("maestros:cultivos")


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def variedad_nueva(request, cultivo_id):
    """Nueva variedad (PROD-ALT-VAR, ``VIEWS['var-form']`` del prototipo): formulario, resumen y confirmación. Cualquier Agrónomo activo."""
    _ocultar_al_gerente(request)
    cultivo = get_object_or_404(Cultivo, pk=cultivo_id)
    if not cultivo.activo:
        messages.error(request, f"El cultivo {cultivo.nombre_cultivo} está inactivo: reactivalo antes de crear variedades.")
        return redirect("maestros:cultivos")
    return _trabajar_el_formulario(request, cultivo, None)


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def variedad(request, variedad_id):
    """El formulario de una variedad, que es también su detalle (regla 3 de PROD-CNS-VAR) y su modificación (PROD-MOD-VAR). Una variedad
    inactiva o que la cuenta no puede gestionar se ve con los campos deshabilitados y el motivo (D-30)."""
    _ocultar_al_gerente(request)
    la_variedad = api.obtener_variedad(variedad_id)
    return _trabajar_el_formulario(request, la_variedad.cultivo, la_variedad)


@rol_requerido(GERENTE, AGRONOMO)
@vary_on_headers("HX-Request")
def etapas_del_perfil(request):
    """El fragmento de etapas que se redibuja al cambiar el perfil (HTMX, sin validar). ``?variedad=`` dice de cuál variedad se trata,
    para saber si sus etapas están congeladas por tener lotes."""
    _ocultar_al_gerente(request)
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    identificador = request.GET.get("variedad", "")
    la_variedad = api.obtener_variedad(int(identificador)) if identificador.isdigit() else None
    form = _formulario(request, la_variedad.cultivo if la_variedad else None, la_variedad, request.GET)
    return render(request, "inventario/variedades/_etapas.html", {"form": form, "variedad": la_variedad})


# ---- «Qué sigue» tras el alta ----


@rol_requerido(GERENTE, AGRONOMO)
@vary_on_headers("HX-Request")
def variedad_creada(request, variedad_id):
    """«Qué sigue» tras el alta (regla 9 de PROD-ALT-VAR): para pedir o sembrar la variedad hay que habilitar su semilla en cada invernadero.
    El botón abre la ventana de CMP-HAB-IIN (INV-02) con la semilla ya elegida."""
    _ocultar_al_gerente(request)
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    la_variedad = api.obtener_variedad(variedad_id)
    semilla = api.semilla_de([la_variedad.pk]).get(la_variedad.pk)
    puede_habilitar = Invernadero.objects.en_alcance_de(request.user).exists()
    return render(
        request,
        "inventario/variedades/creada.html",
        {"variedad": la_variedad, "cultivo": la_variedad.cultivo, "semilla": semilla, "puede_habilitar": puede_habilitar, "es_gerente": False},
    )


# ---- Baja y reactivación ----


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def variedad_baja(request, variedad_id):
    """Dar de baja una variedad (PROD-BAJ-VAR, ``MODALS['var-baja']`` del prototipo), con confirmación previa. Si hay impedimentos (regla 2)
    la página los dice todos, cada uno con cómo resolverlo, y no ofrece confirmar. Informa dónde está habilitada la semilla y cuánto stock
    queda (regla 3). Abrirla (GET) no cambia nada; la baja es un POST."""
    _ocultar_al_gerente(request)
    la_variedad = api.obtener_variedad(variedad_id)
    acciones = api.acciones_permitidas(request.user, la_variedad)
    if not acciones.dar_de_baja:
        messages.error(request, acciones.motivo or "Esa variedad no se puede dar de baja: ya está inactiva.")
        return redirect("maestros:cultivos")
    errores = []
    if request.method == "POST":
        try:
            api.baja_variedad(request.user, la_variedad.pk)
        except ValidationError as rechazo:
            errores = rechazo.messages  # apareció un impedimento con la página abierta: se vuelve a mostrar
        else:
            messages.success(request, f"{la_variedad.cultivo.nombre_cultivo} {la_variedad.nombre_variedad} y su semilla quedaron inactivas.")
            return redirect("maestros:cultivos")
    informe = api.informe_de_baja(la_variedad)
    return render(
        request,
        "inventario/variedades/baja.html",
        {"variedad": la_variedad, "cultivo": la_variedad.cultivo, "informe": informe, "errores": errores, "es_gerente": False},
    )


@rol_requerido(GERENTE, AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
def variedad_reactivar(request, variedad_id):
    """Reactivar una variedad dada de baja (PROD-MOD-VAR, regla 9). Pide confirmar en una página (GET) y reactiva con un POST: reactiva
    también su semilla y no vuelve a habilitar nada. Con el cultivo inactivo no se ofrece («Primero reactivá el cultivo X»)."""
    _ocultar_al_gerente(request)
    la_variedad = api.obtener_variedad(variedad_id)
    acciones = api.acciones_permitidas(request.user, la_variedad)
    if not acciones.reactivar:
        messages.error(request, acciones.motivo or "Esa variedad ya está activa.")
        return redirect("maestros:cultivos")
    if request.method == "POST":
        try:
            api.reactivar_variedad(request.user, la_variedad.pk)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(
                request,
                f"{la_variedad.cultivo.nombre_cultivo} {la_variedad.nombre_variedad} y su semilla están activas de nuevo. Para usar la semilla, habilitala en cada invernadero.",
            )
        return redirect("maestros:cultivos")
    return render(request, "inventario/variedades/reactivar.html", {"variedad": la_variedad, "cultivo": la_variedad.cultivo, "es_gerente": False})
