# Vistas de `estadisticas` (EST-01): la pantalla «Estadísticas» de producción (EST-CNS-PRD) del Agrónomo y del Gerente. Las vistas solo orquestan:
# leen el filtro (un GET: la URL se puede compartir y volver a abrir), llaman al servicio y arman lo que muestra la plantilla. No audita (regla 9).

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
from estadisticas.servicios import produccion as servicio
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
    contexto = {"filtro": filtro, "atajos": periodos.TEXTOS_DE_ATAJO.items(), "hoy": hoy, "error": None, "resultado": None}
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
