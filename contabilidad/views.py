# Pantallas de «Contabilidad» (CON-03a; prototipo: ``VIEWS.k_main``, ``tabLibro``, ``libroCron``, ``libroCta``, ``VIEWS.k_asi``, ``tabEje``, ``VIEWS.k_cierre``, ``tabPlan``).
# Las vistas solo orquestan: leen lo que se envió, llaman a los servicios (`contabilidad/servicios/`) y renderizan; las reglas son de los servicios. Solo el
# Contador y el Gerente entran (regla 1 de CON-CNS-LGS y de CON-CNS-PCT, X3): el Vendedor y los demás roles reciben 403. Las consultas no se auditan (SEG-14).
# Ningún botón lleva a un 403 (D-30): «Cerrar ejercicio» se muestra solo a quien puede cerrar. Las acciones de la ficha (contraasentar, registrar) llegan con CON-03b.
# Todo funciona sin JavaScript: los filtros y el cierre son formularios comunes.
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from contabilidad import cuentas
from contabilidad.errores import ErrorContable
from contabilidad.forms import FormularioDelLibro
from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios as servicio_de_ejercicios
from contabilidad.servicios import libro, plan, responsables
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
    Sin las acciones de contraasentar y registrar (CON-03b). Un asiento inexistente es 404."""
    ficha = libro.ficha_de_asiento(request.user, ejercicio_id, numero)
    ejercicio = ficha.asiento.ejercicio
    return render(
        request,
        "contabilidad/asiento.html",
        {
            "ficha": ficha,
            "ejercicio": ejercicio,
            "numero_de_ejercicio": servicio_de_ejercicios.numero_de_ejercicio(ejercicio),
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
