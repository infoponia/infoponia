# Vistas de `estadisticas`: la pantalla «Estadísticas» de producción (EST-01, EST-CNS-PRD) del Agrónomo y del Gerente y las «Estadísticas consolidadas»
# del Gerente (EST-02, EST-CNS-CNS). Las vistas solo orquestan: leen el filtro (un GET: la URL se puede compartir y volver a abrir), llaman al servicio y
# arman lo que muestra la plantilla. No auditan (regla 9 de EST-CNS-PRD; regla 7 de EST-CNS-CNS).

from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe

from core.acceso import rol_de, rol_requerido
from core.models import Usuario
from estadisticas import periodos
from estadisticas.presentacion import barras, delta
from contabilidad.servicios.ejercicios import ejercicios_numerados
from estadisticas.servicios import consolidadas as servicio_consolidado
from estadisticas.servicios import produccion as servicio
from estadisticas.servicios.produccion import _porcentaje
from maestros.models import Invernadero
from produccion import formularios

AGRONOMO = Usuario.Rol.AGRONOMO
GERENTE = Usuario.Rol.GERENTE


def _ultimo(datos, nombre, defecto=""):
    """El último valor de un campo del GET: la pantalla manda el valor actual escondido y, después, el del botón que se apretó."""
    valores = datos.getlist(nombre)
    return valores[-1] if valores else defecto


def _filtro(datos):
    """Lo que eligió la persona, ya normalizado: atajo del período, fechas a mano, invernadero, selector de órdenes y comparación. La primera
    vez que se abre (sin `enviado`) la comparación viene prendida, como en el prototipo."""
    codigo = _ultimo(datos, "periodo")
    return {
        "periodo": codigo if codigo in periodos.CODIGOS_DE_ATAJO else "mes",
        "desde": _ultimo(datos, "desde"),
        "hasta": _ultimo(datos, "hasta"),
        "invernadero": formularios.entero(_ultimo(datos, "invernadero")),
        "ordenes": "produccion" if _ultimo(datos, "ordenes") == "produccion" else "todas",
        "comparar": ("comparar" in datos) if "enviado" in datos else True,
    }


def _periodo(filtro, hoy):
    """El `Periodo` del filtro o `ValidationError`. «Personalizado» valida las fechas escritas; un atajo se valida igual (el ejercicio puede
    pasar de un año)."""
    if filtro["periodo"] == "personalizado" and (filtro["desde"] or filtro["hasta"]):
        return periodos.validar(formularios.fecha(filtro["desde"]), formularios.fecha(filtro["hasta"]), hoy)
    elegido = periodos.atajo(filtro["periodo"], hoy)
    return periodos.validar(elegido.desde, elegido.hasta, hoy)


def _invernadero_unico(elegido_id, invernaderos):
    """El invernadero de los enlaces: el elegido o, si el alcance tiene uno solo, ese; si no, `None` (varios: el enlace no puede elegir uno)."""
    if elegido_id is not None:
        return elegido_id
    return invernaderos[0].pk if len(invernaderos) == 1 else None


def _enlaces(rol, periodo, invernadero_id):
    """Cada indicador enlaza a la consulta que lo detalla con el mismo invernadero y, si la consulta filtra por fechas, el mismo período
    (D-93 punto 6, EST-CNS-PRD regla 5). Un enlace solo aparece si la cuenta puede abrir esa pantalla (D-30: ningún botón lleva a un 403) y
    si la consulta puede mostrar lo que se pide: la bitácora y las existencias se miran de un invernadero por vez."""
    fechas = {"desde": periodo.desde.isoformat(), "hasta": periodo.hasta.isoformat()}
    enlaces = {"ordenes": reverse("produccion:ordenes") + ("?" + urlencode({"invernadero": invernadero_id}) if invernadero_id else "")}
    if invernadero_id:
        enlaces["bitacora"] = reverse("produccion:bitacora") + "?" + urlencode({"invernadero": invernadero_id, **fechas})
        enlaces["bitacora_merma"] = reverse("produccion:bitacora") + "?" + urlencode({"invernadero": invernadero_id, "tipo": "merma", **fechas})
        if rol == AGRONOMO:  # el inventario es del Agrónomo a cargo; el Gerente recibiría un 403
            enlaces["insumos"] = reverse("inventario:existencias") + "?" + urlencode({"invernadero": invernadero_id})
    enlaces["iot"] = reverse("iot:monitoreo")
    return enlaces


def _deltas(resultado):
    """El texto de comparación de cada tarjeta (vacío si la comparación está apagada)."""
    c = resultado.comparaciones
    if not c:
        return {}
    return {
        "sembradas": delta(c["sembradas"]),
        "cosechadas": delta(c["cosechadas"]),
        "merma": delta(c["merma"], mejor_si_sube=False, decimales=1, unidad="pts", con_porcentaje=False),
        "ordenes": delta(c["ordenes_a_tiempo"], decimales=1, unidad="pts", con_porcentaje=False),
        "costo": delta(c["costo_por_planta"], mejor_si_sube=False, decimales=2),
        "consumo": delta(c["consumo"], mejor_si_sube=False, decimales=2),
        "alertas_iot": delta(c.get("alertas_iot"), mejor_si_sube=False),
    }


def _hay_actividad(bloques):
    """Si el período tuvo algo que mostrar (si no, la pantalla dice «No hay actividad en este período»)."""
    return any(
        (
            bloques.sembradas_y_cosechadas.filas,
            bloques.merma.perdidas,
            bloques.ordenes.total,
            bloques.consumo.categorias,
            bloques.alertas_iot and bloques.alertas_iot.total,
        )
    )


@rol_requerido(AGRONOMO, GERENTE)
@require_safe
def produccion(request):
    """«Estadísticas» de producción (EST-CNS-PRD): los seis indicadores del período elegido, de los invernaderos del Agrónomo o de todos los
    del Gerente, comparados con el período anterior. Es una consulta GET: funciona sin JavaScript y no se audita."""
    hoy = timezone.localdate()
    filtro = _filtro(request.GET)
    contexto = {
        "filtro": filtro,
        "atajos": periodos.TEXTOS_DE_ATAJO.items(),
        "hoy": hoy,
        "error": None,
        "resultado": None,
        "es_gerente": rol_de(request.user) == GERENTE,
    }
    try:
        periodo = _periodo(filtro, hoy)
        resultado = servicio.estadisticas_de_produccion(
            request.user, filtro["invernadero"], periodo, filtro["comparar"], hoy, solo_produccion=filtro["ordenes"] == "produccion"
        )
    except ValidationError as error:
        # Un período o un invernadero inválido no muestra datos, pero el formulario sigue ahí para corregirlo.
        contexto["error"] = error.messages[0]
        contexto["invernaderos"] = [
            servicio.InvernaderoDelAlcance(pk, nombre)
            for pk, nombre in Invernadero.objects.en_alcance_de(request.user).order_by("nombre_invernadero").values_list("pk", "nombre_invernadero")
        ]
        return render(request, "estadisticas/produccion.html", contexto, status=200)
    actual = resultado.actual
    contexto.update(
        resultado=resultado,
        invernaderos=resultado.invernaderos,
        periodo=resultado.periodo,
        deltas=_deltas(resultado),
        enlaces=_enlaces(rol_de(request.user), resultado.periodo, _invernadero_unico(filtro["invernadero"], resultado.invernaderos)),
        hay_actividad=_hay_actividad(actual),
        barras_de_merma=barras(actual.merma.por_causa, lambda f: f.plantas),
        barras_de_alertas=barras(actual.alertas_iot.filas, lambda f: f.cantidad) if actual.alertas_iot else [],
    )
    return render(request, "estadisticas/produccion.html", contexto)


# ---------------------------------------------------------------------------------------------------------------------------------
# Estadísticas consolidadas del Gerente (EST-02)
# ---------------------------------------------------------------------------------------------------------------------------------

TEXTOS_DE_PESTANA = {"resumen": "Resumen", "produccion": "Producción", "comercial": "Comercial", "compras": "Compras", "resultados": "Resultados"}


def _ejercicios_del_periodo(periodo):
    """Los ejercicios que toca el período (uno, o dos si lo cruza): el libro filtra de a un ejercicio, así que cada enlace lleva el suyo."""
    return [
        e
        for e in ejercicios_numerados()
        if e.ejercicio.fecha_inicio_ejercicio <= periodo.hasta and e.ejercicio.fecha_cierre_ejercicio >= periodo.desde
    ]


def _enlaces_al_libro(periodo, **filtros):
    """`[(texto, url)]`: la consulta del libro de gestión (cronológica) con el mismo período y los `filtros`, una por ejercicio que toca el período
    (D-93 punto 6, EST-CNS-CNS regla 4). Solo el Gerente llega acá y puede abrir el libro (D-30)."""
    enlaces = []
    for e in _ejercicios_del_periodo(periodo):
        consulta = {
            "ejercicio": e.ejercicio.pk,
            "desde": max(periodo.desde, e.ejercicio.fecha_inicio_ejercicio).isoformat(),
            "hasta": periodo.hasta.isoformat(),
            **filtros,
        }
        enlaces.append((f"Ejercicio {e.numero}", reverse("contabilidad:libro") + "?" + urlencode(consulta)))
    return enlaces


def _enlace_de_produccion(periodo, invernadero_id=None):
    """La pantalla de producción (EST-01) con el mismo período (personalizado) y, si se indica, ese invernadero (regla 5 de EST-CNS-PRD)."""
    consulta = {"enviado": 1, "periodo": "personalizado", "desde": periodo.desde.isoformat(), "hasta": periodo.hasta.isoformat()}
    if invernadero_id:
        consulta["invernadero"] = invernadero_id
    return reverse("estadisticas:produccion") + "?" + urlencode(consulta)


def _con_porcentaje(filas, total, periodo):
    """`[(fila, % del total, enlaces al libro)]` de las filas de un detalle por cuenta: el prototipo muestra el % de cada cuenta y cada una lleva a sus
    asientos del libro, con el mismo período (uno por ejercicio que toca el período)."""
    return [(f, _porcentaje(f.monto, total), _enlaces_al_libro(periodo, cuenta=f.codigo)) for f in filas]


def _deltas_consolidadas(resultado):
    """El texto de comparación de cada cifra (vacío si la comparación está apagada). Egresos, compras, consumo y merma mejoran si bajan."""
    c = resultado.comparaciones
    if not c:
        return {}

    def delta_de(clave, **opciones):
        return delta(c.get(clave), **opciones)

    return {
        "ventas": delta_de("ventas", decimales=2),
        "compras": delta_de("compras", mejor_si_sube=False, decimales=2),
        "resultado": delta_de("resultado", decimales=2),
        "ingresos": delta_de("ingresos", decimales=2),
        "egresos": delta_de("egresos", mejor_si_sube=False, decimales=2),
        "sembradas": delta_de("sembradas"),
        "cosechadas": delta_de("cosechadas"),
        "merma": delta_de("merma", mejor_si_sube=False, decimales=1, unidad="pts", con_porcentaje=False),
        "ordenes_a_tiempo": delta_de("ordenes_a_tiempo", decimales=1, unidad="pts", con_porcentaje=False),
        "costo_por_planta": delta_de("costo_por_planta", mejor_si_sube=False, decimales=2),
        "consumo": delta_de("consumo", mejor_si_sube=False, decimales=2),
        "alertas_iot": delta_de("alertas_iot", mejor_si_sube=False),
        # Pestaña «Comercial» (EST-03): sube es bueno en ventas y en puntualidad; es malo en retraso, intentos, incumplimientos y faltantes.
        "ventas_monto": delta_de("ventas_monto", decimales=2),
        "ventas_entregas": delta_de("ventas_entregas"),
        "ventas_plantas": delta_de("ventas_plantas"),
        "a_tiempo": delta_de("a_tiempo", decimales=1, unidad="pts", con_porcentaje=False),
        "promedio_de_retraso": delta_de("promedio_de_retraso", mejor_si_sube=False, decimales=1, unidad="días", con_porcentaje=False),
        "intentos_fallidos": delta_de("intentos_fallidos", mejor_si_sube=False),
        "incumplimientos": delta_de("incumplimientos", mejor_si_sube=False),
        "indemnizado": delta_de("indemnizado", mejor_si_sube=False, decimales=2),
        "con_faltante": delta_de("con_faltante", mejor_si_sube=False),
        "rechazados_por_cantidad": delta_de("rechazados_por_cantidad", mejor_si_sube=False),
        "rechazados_al_recibir": delta_de("rechazados_al_recibir", mejor_si_sube=False),
        "cancelados": delta_de("cancelados", mejor_si_sube=False),
    }


def _contexto_de_la_pestana(resultado):
    """Lo que la plantilla necesita de cada pestaña (barras, porcentajes y enlaces) además del resultado del servicio."""
    pestana, periodo, actual = resultado.pestana, resultado.periodo, resultado.actual
    contexto = {}
    if pestana == "produccion":
        contexto["barras_de_camara"] = barras(actual.merma_en_camara.causas, lambda f: f.plantas)
        contexto["enlace_de_produccion"] = _enlace_de_produccion(periodo)
        contexto["filas_con_enlace"] = [(f, _enlace_de_produccion(periodo, f.invernadero_id)) for f in actual.por_invernadero.filas]
    elif pestana == "comercial":
        # Los enlaces de cada indicador ya vienen de `comercial` (regla 10 de COM-CNS-EST); este lleva a la misma pantalla con el período (la puede abrir el Gerente, D-30).
        consulta = {"periodo": "rango", "desde": periodo.desde.isoformat(), "hasta": periodo.hasta.isoformat()}
        contexto["enlace_a_comercial"] = reverse("comercial:estadisticas") + "?" + urlencode(consulta)
    elif pestana == "compras":
        compras = actual.compras
        contexto["barras_por_proveedor"] = barras(compras.por_proveedor, lambda f: max(f.monto, 0))
        contexto["barras_por_categoria"] = barras(compras.por_categoria, lambda f: max(f.monto, 0))
        contexto["barras_por_mes"] = barras(compras.por_mes, lambda f: max(f.monto, 0))
        contexto["enlaces_de_recepciones"] = _enlaces_al_libro(periodo, origen="recepcion")
        contexto["enlaces_de_correcciones"] = _enlaces_al_libro(periodo, origen="correccion_de_recepcion")
    elif pestana == "resultados":
        libro = actual.libro
        contexto["ingresos_con_porcentaje"] = _con_porcentaje(libro.ingresos_por_cuenta, libro.ingresos, periodo)
        contexto["costos_con_porcentaje"] = _con_porcentaje(libro.costos_por_cuenta, libro.egresos, periodo)
        contexto["enlaces_al_libro"] = _enlaces_al_libro(periodo)
    return contexto


@rol_requerido(GERENTE)
@require_safe
def consolidadas(request):
    """«Estadísticas» consolidadas del Gerente (EST-CNS-CNS): las pestañas Resumen, Producción, Comercial, Compras y Resultados del período elegido, comparadas
    con el período anterior. Es una consulta GET (funciona sin JavaScript y no se audita); el filtro del período es el de EST-01. La pestaña «Comercial» (indicador 8, EST-03) muestra lo de `comercial`."""
    hoy = timezone.localdate()
    filtro = _filtro(request.GET)
    pestana = _ultimo(request.GET, "pestana")
    pestana = pestana if pestana in servicio_consolidado.PESTANAS else "resumen"
    contexto = {
        "filtro": filtro,
        "pestana": pestana,
        "pestanas": TEXTOS_DE_PESTANA.items(),
        "atajos": periodos.TEXTOS_DE_ATAJO.items(),
        "hoy": hoy,
        "error": None,
        "resultado": None,
    }
    try:
        periodo = _periodo(filtro, hoy)
    except ValidationError as error:
        contexto["error"] = error.messages[0]  # un período inválido no muestra datos, pero el formulario sigue ahí para corregirlo
        return render(request, "estadisticas/consolidadas.html", contexto)
    resultado = servicio_consolidado.estadisticas_consolidadas(
        request.user, pestana, periodo, filtro["comparar"], hoy, solo_produccion=filtro["ordenes"] == "produccion"
    )
    # Los enlaces de las cifras del Resumen a su pestaña conservan el filtro (sin la pestaña).
    parametros = {"enviado": 1, "periodo": filtro["periodo"], "ordenes": filtro["ordenes"]}
    if filtro["periodo"] == "personalizado":
        parametros.update(desde=periodo.desde.isoformat(), hasta=periodo.hasta.isoformat())
    if filtro["comparar"]:
        parametros["comparar"] = "on"
    contexto.update(
        resultado=resultado, periodo=periodo, consulta=urlencode(parametros), deltas=_deltas_consolidadas(resultado), **_contexto_de_la_pestana(resultado)
    )
    return render(request, "estadisticas/consolidadas.html", contexto)
