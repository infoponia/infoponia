# Pantallas de «Contabilidad» (CON-03a; prototipo: ``VIEWS.k_main``, ``tabLibro``, ``libroCron``, ``libroCta``, ``VIEWS.k_asi``, ``tabEje``, ``VIEWS.k_cierre``, ``tabPlan``).
# Las vistas solo orquestan: leen lo que se envió, llaman a los servicios (`contabilidad/servicios/`) y renderizan; las reglas son de los servicios. Solo el
# Contador y el Gerente entran (regla 1 de CON-CNS-LGS y de CON-CNS-PCT, X3): el Vendedor y los demás roles reciben 403. Las consultas no se auditan (SEG-14).
# Ningún botón lleva a un 403 (D-30): «Cerrar ejercicio», «Registrar asiento» y «Contraasentar» se muestran solo a quien puede (``responsables.puede_registrar_asientos``); al Gerente con un
# Contador activo el libro le dice «Lo registra el Contador». CON-03b suma el formulario del asiento manual (``VIEWS.k_new``) y el del contraasiento (``VIEWS.k_contra``).
# Todo funciona sin JavaScript: los filtros y el cierre son formularios comunes.
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.vary import vary_on_headers

from contabilidad import cuentas
from contabilidad.errores import ErrorContable
from contabilidad.constantes import DEBE, HABER
from contabilidad.forms import (
    FormularioDelLibro,
    asiento_precargado,
    asiento_vacio,
    errores_para_pantalla,
    etiqueta_de_cuenta,
    fecha_desde_texto,
    leer_asiento,
)
from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios as servicio_de_ejercicios
from contabilidad.servicios import asientos, libro, plan, responsables
from core.acceso import rol_requerido
from core.models import Usuario

CONTADOR = Usuario.Rol.CONTADOR
GERENTE = Usuario.Rol.GERENTE
Estado = EjercicioContable.Estado


def _contexto_de_pestanas(ejercicios_numerados=None):
    """Lo que necesita la barra de pestañas: si hay un ejercicio en cierre, para marcar «Ejercicios» (prototipo: ``ts`` de ``VIEWS.k_main``)."""
    if ejercicios_numerados is None:
        hay = servicio_de_ejercicios.ejercicio_en_cierre() is not None
    else:
        hay = any(e.ejercicio.estado_ejercicio == Estado.EN_CIERRE for e in ejercicios_numerados)
    return {"hay_ejercicio_en_cierre": hay}


def _cuentas_del_arbol(arbol):
    """Las cuentas del plan, en orden de código, a partir del árbol (así el árbol y los desplegables salen de una sola consulta)."""
    return [cuenta for rubro in arbol for subrubro in rubro.subrubros for cuenta in subrubro.cuentas]


def _rubros_con_saldos(arbol, saldos, texto=""):
    """El árbol del plan como listas para la plantilla: por rubro y subrubro, las filas de cuenta con su descripción y su saldo en el ejercicio.
    ``texto`` filtra por código, nombre o descripción; los rubros y subrubros sin filas no se muestran."""
    rubros = []
    for rubro in arbol:
        subrubros = []
        for subrubro in rubro.subrubros:
            filas = []
            for cuenta in subrubro.cuentas:
                descripcion = cuentas.DESCRIPCION_DE_CUENTA[cuenta.codigo_cuenta]
                if texto and not (
                    texto.lower() in cuenta.codigo_cuenta
                    or texto.lower() in cuenta.nombre_cuenta.lower()
                    or texto.lower() in descripcion.lower()
                ):
                    continue
                saldo = saldos.get(cuenta.codigo_cuenta)
                con_movimientos = bool(saldo and (saldo.debe or saldo.haber or saldo.saldo_inicial))
                filas.append({"cuenta": cuenta, "descripcion": descripcion, "saldo": saldo, "con_movimientos": con_movimientos})
            if filas:
                subrubros.append({"codigo": subrubro.codigo, "nombre": subrubro.nombre, "filas": filas})
        if subrubros:
            rubros.append({"codigo": rubro.codigo, "nombre": rubro.nombre, "subrubros": subrubros})
    return rubros


# ---- plan de cuentas (CON-CNS-PCT) ----


@rol_requerido(GERENTE, CONTADOR)
@require_safe
@never_cache
def plan_de_cuentas(request):
    """Pestaña «Plan de cuentas» (CON-CNS-PCT; ``tabPlan``): el árbol por rubro y subrubro con código, nombre, tipo, para qué se usa y el saldo en el
    ejercicio abierto; cada saldo lleva al libro de gestión por cuenta (regla 4). El buscador se envía con «Buscar»: sin JavaScript funciona igual."""
    texto = request.GET.get("q", "").strip()
    abierto = servicio_de_ejercicios.ejercicio_abierto()
    saldos = libro.saldo_por_cuenta(abierto.pk) if abierto else {}
    rubros = _rubros_con_saldos(plan.arbol(), saldos, texto)
    return render(request, "contabilidad/plan.html", {"rubros": rubros, "q": texto, "ejercicio": abierto, **_contexto_de_pestanas()})


# ---- libro de gestión (CON-CNS-LGS) ----


def _ejercicio_elegido(form, numerados):
    """El ejercicio que se mira: el elegido; si no hay o no es válido, el abierto (regla 2) y, sin abierto, el más reciente. `None` si no hay ninguno."""
    por_id = {str(e.ejercicio.pk): e for e in numerados}
    elegido = por_id.get(form.cleaned_data.get("ejercicio"))
    if elegido is not None:
        return elegido
    for e in numerados:
        if e.ejercicio.estado_ejercicio == Estado.ABIERTO:
            return e
    return numerados[-1] if numerados else None


def _consulta_sin_pagina(request):
    """La cadena de consulta actual sin «pagina», para que los enlaces de la paginación conserven los filtros."""
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return parametros.urlencode()


@rol_requerido(GERENTE, CONTADOR)
@require_safe
@never_cache
def libro_de_gestion(request):
    """Pestaña «Libro de gestión» (CON-CNS-LGS; ``tabLibro``): selector de ejercicio, interruptor Cronológica / Por cuenta y filtros (que se envían con «Filtrar»).

    Cronológica: los asientos del ejercicio por fecha y número, con filtros y 50 por página. Por cuenta: sin cuenta elegida, el plan con el saldo de cada
    una; con cuenta, sus movimientos con el saldo acumulado, 100 por página. Un ejercicio «en cierre» o «cerrado» lleva su aviso (regla 6). Sin acciones de
    asientos manuales: llegan con CON-03b. No audita (regla 9).
    """
    numerados = servicio_de_ejercicios.ejercicios_numerados()
    arbol = plan.arbol()
    form = FormularioDelLibro(request.GET, ejercicios=numerados, cuentas=_cuentas_del_arbol(arbol))
    form.is_valid()  # todos los campos son opcionales: un valor inválido queda con su error y no se aplica
    elegido = _ejercicio_elegido(form, numerados)
    contexto = {
        "form": form,
        "numerados": numerados,
        "elegido": elegido,
        "ejercicio": elegido.ejercicio if elegido else None,
        "vista": form.vista_elegida(),
        "hay_filtros": form.hay_filtros(),
        "consulta_base": _consulta_sin_pagina(request),
        "hoy": timezone.localdate(),
        "puede_registrar": responsables.puede_registrar_asientos(request.user),
        **_contexto_de_pestanas(numerados),
    }
    if elegido is None:  # la contabilidad todavía no se puso en marcha
        return render(request, "contabilidad/libro.html", contexto)
    ejercicio_id = elegido.ejercicio.pk
    if contexto["vista"] == "cuenta":
        codigo = form.cleaned_data.get("cuenta") or None
        saldos = libro.saldo_por_cuenta(ejercicio_id)
        if codigo is None:
            contexto["rubros"] = _rubros_con_saldos(arbol, saldos)
        else:
            cuenta = next(c for c in _cuentas_del_arbol(arbol) if c.codigo_cuenta == codigo)
            pagina = libro.pagina_de_movimientos_de_cuenta(codigo, ejercicio_id, request.GET.get("pagina"))
            contexto.update({"cuenta": cuenta, "saldo": saldos[codigo], "pagina_de_cuenta": pagina, "saldo_actual": pagina.saldo_final})
    else:
        asientos = libro.listar_asientos(request.user, ejercicio_id=ejercicio_id, **form.filtros())
        pagina = Paginator(asientos, libro.POR_PAGINA_ASIENTOS).get_page(request.GET.get("pagina"))
        filas = []
        for asiento in pagina:
            movimientos = list(asiento.movimientos.all())  # ya traídos con `prefetch_related`
            filas.append(
                {
                    "asiento": asiento,
                    "movimientos": movimientos,
                    "total": sum((m.importe_movimiento for m in movimientos if m.tipo_movimiento == "D"), 0),
                    "anulado": hasattr(asiento, "contraasiento"),
                }
            )
        contexto.update({"pagina": pagina, "filas": filas, "total_general": libro.total_de_los_asientos(asientos)})
    return render(request, "contabilidad/libro.html", contexto)


@rol_requerido(GERENTE, CONTADOR)
@require_safe
@never_cache
def asiento(request, ejercicio_id, numero):
    """Ficha del asiento (CON-CNS-LGS regla 5; ``VIEWS.k_asi``): movimientos, origen con su enlace, quién lo registró y el asiento que anula o que lo anuló.
    Con «Contraasentar» si se puede anular y quien mira puede registrar (CON-03b), y, recién hecho un contraasiento (?corregir=1), la oferta de registrar el asiento
    correcto (paso 8). Un asiento inexistente es 404."""
    ficha = libro.ficha_de_asiento(request.user, ejercicio_id, numero)
    ejercicio = ficha.asiento.ejercicio
    puede = responsables.puede_registrar_asientos(request.user)
    anulable = ficha.anula is None and ficha.anulado_por is None
    return render(
        request,
        "contabilidad/asiento.html",
        {
            "ficha": ficha,
            "ejercicio": ejercicio,
            "numero_de_ejercicio": servicio_de_ejercicios.numero_de_ejercicio(ejercicio),
            "puede_contraasentar": puede and anulable,
            "lo_registra_el_contador": not puede and anulable,
            "ofrecer_correccion": puede and ficha.anula is not None and request.GET.get("corregir") == "1",
            **_contexto_de_pestanas(),
        },
    )


# ---- ejercicios y cierre (CON-CRR-EJE) ----


@rol_requerido(GERENTE, CONTADOR)
@require_safe
@never_cache
def pestana_de_ejercicios(request):
    """Pestaña «Ejercicios» (``tabEje``): número, rango, estado, cantidad de asientos y quién lo cerró; el «en cierre» lleva «Cerrar ejercicio» solo si quien
    mira puede cerrar (el Contador, o el Gerente sin Contador activo, regla 5; D-30) y todos, «Ver libro»."""
    hoy = timezone.localdate()
    numerados = servicio_de_ejercicios.ejercicios_numerados()
    filas = [
        {"numero": e.numero, "ejercicio": e.ejercicio, "asientos": e.cantidad_de_asientos, "dias_desde_el_fin": (hoy - e.ejercicio.fecha_cierre_ejercicio).days}
        for e in reversed(numerados)
    ]
    contexto = {"filas": filas, "puede_cerrar": responsables.puede_registrar_asientos(request.user), **_contexto_de_pestanas(numerados)}
    return render(request, "contabilidad/ejercicios.html", contexto)


@rol_requerido(GERENTE, CONTADOR)
@require_http_methods(["GET", "POST"])
@never_cache
def cierre(request, ejercicio_id):
    """Pantalla de confirmación del cierre (CON-CRR-EJE regla 4; ``VIEWS.k_cierre``): el resumen (rango, cantidad de asientos, total del Debe y del Haber), el
    aviso de que no se deshace y una casilla de confirmación (C9). GET muestra el resumen; POST con la casilla marcada cierra. Quien no puede cerrar recibe
    403 (no hay botón que lleve acá, D-30); un ejercicio que no está «en cierre» vuelve a la lista con un aviso."""
    if not responsables.puede_registrar_asientos(request.user):
        raise PermissionDenied("Solo el Contador, o el Gerente si no hay un Contador activo, cierra un ejercicio.")
    resumen = servicio_de_ejercicios.resumen_para_cierre(ejercicio_id)
    ejercicio = resumen.ejercicio
    numero = servicio_de_ejercicios.numero_de_ejercicio(ejercicio)
    if ejercicio.estado_ejercicio != Estado.EN_CIERRE:
        messages.error(request, f"El ejercicio N.º {numero} no está en cierre: no se puede cerrar.")
        return redirect("contabilidad:ejercicios")
    falta_confirmar = False
    if request.method == "POST":
        if request.POST.get("confirmo"):
            try:
                servicio_de_ejercicios.cerrar_ejercicio(request.user, ejercicio_id)
            except ErrorContable as error:  # `ejercicio_no_esta_en_cierre`: otro lo cerró mientras se miraba el resumen
                messages.error(request, error.mensaje)
            else:
                messages.success(request, f"Cerraste el ejercicio N.º {numero}. Ya no recibe asientos.")
            return redirect("contabilidad:ejercicios")
        falta_confirmar = True
    siguiente = EjercicioContable.objects.filter(fecha_inicio_ejercicio__gt=ejercicio.fecha_cierre_ejercicio).order_by("fecha_inicio_ejercicio").first()
    contexto = {
        "resumen": resumen,
        "ejercicio": ejercicio,
        "numero_de_ejercicio": numero,
        "siguiente_numero": servicio_de_ejercicios.numero_de_ejercicio(siguiente) if siguiente else None,
        "falta_confirmar": falta_confirmar,
        "es_contador": request.user.rol == CONTADOR,
        **_contexto_de_pestanas(),
    }
    return render(request, "contabilidad/cierre.html", contexto, status=200)


# ---- asiento manual (CON-REG-ASI) ----

ATAJOS = {
    # Extensiones 3a y 3b: solo precargan la descripción y sugieren cuentas; no tienen código propio (el asiento se registra como cualquier manual).
    "apertura": ("Asiento de apertura", [(cuentas.CAJA, DEBE), (cuentas.CAPITAL_INICIAL, HABER)]),
    "venta_previa": ("Venta de producción previa a la puesta en marcha", [(cuentas.CAJA, DEBE), (cuentas.VENTAS, HABER)]),
}


def _errores_vacios():
    return {"descripcion": [], "fecha": [], "general": [], "filas": {}}


def _dibujar_formulario(request, datos, errores=None, corrige=None):
    """El formulario del asiento: la página entera o, para un pedido de HTMX que solo agrega o quita una fila, el cuerpo del formulario (sin validar, interfaz.md)."""
    errores = errores or _errores_vacios()
    contexto = {
        "puede": True,
        "datos": datos,
        "filas": [{**fila, "errores": errores["filas"].get(fila["i"], {})} for fila in datos.filas],
        "puede_quitar": len(datos.filas) > 2,
        "errores": errores,
        "cuentas": _cuentas_del_arbol(plan.arbol()),
        "etiqueta_de_cuenta": etiqueta_de_cuenta,
        "corrige": corrige,
        "hoy": timezone.localdate(),
    }
    plantilla = "contabilidad/_asiento_formulario.html" if request.headers.get("HX-Request") else "contabilidad/asiento_nuevo.html"
    return render(request, plantilla, contexto)


def _numero_corregido(texto):
    """El número del asiento anulado que se corrige (campo oculto `corrige`), o `None`."""
    return int(texto) if texto and texto.isdigit() else None


@rol_requerido(GERENTE, CONTADOR)
@require_http_methods(["GET", "POST"])
@never_cache
@vary_on_headers("HX-Request")
def asiento_nuevo(request):
    """«Registrar asiento» (CON-REG-ASI; ``VIEWS.k_new``): formulario con filas que se agregan y se quitan, buscador de cuenta, los atajos de apertura y venta previa, el
    resumen previo y la confirmación en una pantalla aparte. Todo son botones de un formulario (``accion``): funciona sin JavaScript; con HTMX, agregar y quitar una
    fila solo redibuja el formulario. ``?corrige=<id>`` precarga las líneas de un asiento anulado (C4; extensión 1b). Quien no puede registrar ve el motivo (no hay
    botón que lleve acá, D-30); un POST suyo es 403."""
    hoy = timezone.localdate()
    if not responsables.puede_registrar_asientos(request.user):
        if request.method == "POST":
            raise PermissionDenied("Lo registra el Contador.")
        return render(request, "contabilidad/asiento_nuevo.html", {"puede": False})
    cuentas_del_plan = _cuentas_del_arbol(plan.arbol())
    if request.method == "GET":
        corrige = request.GET.get("corrige")
        if corrige and corrige.isdigit():
            precarga = asientos.datos_para_correccion(request.user, int(corrige))
            datos = asiento_precargado(hoy, precarga["descripcion"], precarga["movimientos"], cuentas_del_plan)
            return _dibujar_formulario(request, datos, corrige=precarga["numero_anulado"])
        return _dibujar_formulario(request, asiento_vacio(hoy))

    accion = request.POST.get("accion", "revisar")
    datos = leer_asiento(request.POST, hoy)
    corrige = _numero_corregido(request.POST.get("corrige"))
    if accion == "agregar":
        datos.agregar_fila()
        return _dibujar_formulario(request, datos, corrige=corrige)
    if accion.startswith("quitar:"):
        datos.quitar_fila(int(accion.split(":", 1)[1]) if accion.split(":", 1)[1].isdigit() else -1)
        return _dibujar_formulario(request, datos, corrige=corrige)
    if accion.startswith("atajo:") and accion.split(":", 1)[1] in ATAJOS:
        descripcion, lineas = ATAJOS[accion.split(":", 1)[1]]
        precargado = asiento_precargado(hoy, descripcion, [(codigo, tipo, None) for codigo, tipo in lineas], cuentas_del_plan)
        datos.descripcion, datos.filas = precargado.descripcion, precargado.filas
        return _dibujar_formulario(request, datos, corrige=corrige)
    if accion not in ("revisar", "confirmar"):  # «editar» (volver del resumen) o una acción desconocida
        return _dibujar_formulario(request, datos, corrige=corrige)

    movimientos = datos.movimientos(cuentas_del_plan)
    if datos.fecha is None:  # sin fecha válida nunca se registra: se validan igual los demás campos, para marcarlos juntos
        try:
            asientos.resumir_asiento_manual(request.user, hoy, datos.descripcion, movimientos, hoy=hoy)
            errores = _errores_vacios()
        except ErrorContable as error:
            errores = errores_para_pantalla(error, datos.filas)
        errores["fecha"].insert(0, "Indicá una fecha válida.")
        return _dibujar_formulario(request, datos, errores, corrige)
    try:
        if accion == "confirmar":
            asiento = asientos.registrar_asiento_manual(request.user, datos.fecha, datos.descripcion, movimientos, hoy=hoy)
        else:
            resumen = asientos.resumir_asiento_manual(request.user, datos.fecha, datos.descripcion, movimientos, hoy=hoy)
    except ErrorContable as error:
        return _dibujar_formulario(request, datos, errores_para_pantalla(error, datos.filas), corrige)
    if accion == "confirmar":
        numero = servicio_de_ejercicios.numero_de_ejercicio(asiento.ejercicio)
        messages.success(request, f"Asiento N.º {asiento.numero_asiento} registrado en el ejercicio {numero}.")
        return redirect("contabilidad:asiento", asiento.ejercicio_id, asiento.numero_asiento)
    return render(request, "contabilidad/asiento_resumen.html", {"datos": datos, "resumen": resumen, "corrige": corrige})


# ---- contraasiento (CON-CTR-ASI) ----


@rol_requerido(GERENTE, CONTADOR)
@require_http_methods(["GET", "POST"])
@never_cache
def contraasiento(request, ejercicio_id, numero):
    """«Contraasentar el asiento N.º X» (CON-CTR-ASI; ``VIEWS.k_contra``): el asiento a anular, cómo queda el contraasiento (Debe y Haber invertidos), la fecha (hoy por defecto) y
    el motivo; el resumen y la confirmación van aparte. Un asiento que no se puede anular (un contraasiento o uno ya anulado) muestra el motivo y, si ya está anulado,
    su contraasiento (extensión 1b). Quien no puede registrar recibe 403 (no hay botón que lleve acá, D-30). Al terminar lleva a la ficha del contraasiento, que ofrece
    registrar el asiento correcto (paso 8)."""
    ficha = libro.ficha_de_asiento(request.user, ejercicio_id, numero)
    if not responsables.puede_registrar_asientos(request.user):
        raise PermissionDenied("Lo registra el Contador.")
    hoy = timezone.localdate()
    asiento = ficha.asiento
    contexto = {"ficha": ficha, "asiento": asiento, "numero_de_ejercicio": servicio_de_ejercicios.numero_de_ejercicio(asiento.ejercicio), "hoy": hoy}
    if ficha.anula is not None or ficha.anulado_por is not None:
        return render(request, "contabilidad/contraasiento.html", {**contexto, "no_anulable": True})
    if request.method == "GET":
        return render(request, "contabilidad/contraasiento.html", {**contexto, "fecha_texto": hoy.isoformat(), "motivo": "", "errores": _errores_vacios()})

    accion = request.POST.get("accion", "revisar")
    fecha_texto, motivo = request.POST.get("fecha", hoy.isoformat()), request.POST.get("motivo", "")
    formulario = {**contexto, "fecha_texto": fecha_texto, "motivo": motivo}
    fecha = fecha_desde_texto(fecha_texto)
    if accion not in ("revisar", "confirmar"):  # «editar»: volver del resumen
        return render(request, "contabilidad/contraasiento.html", {**formulario, "errores": _errores_vacios()})
    try:
        if fecha is None:  # sin fecha válida nunca se registra
            asientos.resumir_contraasiento(request.user, asiento.pk, hoy, motivo, hoy=hoy)
            errores = _errores_vacios()
            errores["fecha"].append("Indicá una fecha válida.")
            return render(request, "contabilidad/contraasiento.html", {**formulario, "errores": errores})
        if accion == "confirmar":
            nuevo = asientos.contraasentar(request.user, asiento.pk, fecha, motivo, hoy=hoy)
        else:
            resumen = asientos.resumir_contraasiento(request.user, asiento.pk, fecha, motivo, hoy=hoy)
    except ErrorContable as error:
        errores = errores_para_pantalla(error)
        if error.codigo == "asiento_no_anulable":  # otro lo anuló mientras tanto (6a): la ficha ya lo muestra anulado
            messages.error(request, error.mensaje)
            return redirect("contabilidad:asiento", ejercicio_id, numero)
        if fecha is None:
            errores["fecha"].insert(0, "Indicá una fecha válida.")
        return render(request, "contabilidad/contraasiento.html", {**formulario, "errores": errores})
    if accion == "confirmar":
        messages.success(request, f"Asiento N.º {asiento.numero_asiento} anulado con el contraasiento N.º {nuevo.numero_asiento}.")
        return redirect(reverse("contabilidad:asiento", args=[nuevo.ejercicio_id, nuevo.numero_asiento]) + "?corregir=1")
    return render(request, "contabilidad/contraasiento_resumen.html", {**contexto, "resumen": resumen, "fecha": fecha, "fecha_texto": fecha_texto, "motivo": motivo})
