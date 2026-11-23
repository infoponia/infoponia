# Vistas de `iot` (IOT-01): «IoT» → «Tipos de actuador» (IOT-CNS-TAC, IOT-ALT-TAC, IOT-MOD-TAC, IOT-BAJ-TAC). Las vistas solo orquestan
# (docs/patrones/abm.md, sección 1): arman los datos del formulario, llaman al servicio y renderizan. Consultan el Gerente y el Agrónomo;
# solo el Gerente escribe (el Agrónomo recibe 403 en las URL de escritura y no ve los botones, D-30). Los demás roles, 403 en todo el módulo.
#
# El formulario de un tipo es una página con HTMX y respaldo sin JavaScript: «Agregar acción», «Quitar» y el cambio de comando (que
# vacía la unidad y el rango) mandan el formulario entero a la misma URL, que lo vuelve a dibujar SIN llamar al servicio. Con HTMX
# devuelve solo el fragmento de las acciones; sin JavaScript, la página entera. La baja es una ventana: fragmento con HTMX y, sin
# JavaScript, la lista con la ventana abierta.

from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from iot.catalogo import UNIDADES_POR_COMANDO
from iot.servicios import tipos_actuador as api

GERENTE, AGRONOMO = Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO

PLANTILLA_DE_BAJA = "iot/tipos/_ventana_baja.html"
UNIDAD_PROPUESTA = "%"  # el formulario propone «%» al elegir un comando con valor (tipos_de_actuador.md, «Acciones»)
TIEMPO_PROPUESTO = "60"  # y 60 segundos de tiempo mínimo (regla 9 de IOT-ALT-TAC)


def _es_htmx(request):
    """True si el pedido lo hizo HTMX (``HX-Request``)."""
    return request.headers.get("HX-Request") == "true"


@rol_requerido(GERENTE, AGRONOMO)
def inicio(request):
    """``/iot/``: lleva a «Monitoreo», la primera pestaña del módulo (IOT-04; IOT-02 la llevaba a «Sistema IoT»)."""
    return redirect("iot:monitoreo")


# ---- consulta (IOT-CNS-TAC) ----


def _contexto_de_la_lista(request, **extra):
    """Lo que dibuja la lista: cada tipo con sus botones (``acciones_permitidas``, D-30) y el catálogo en solo lectura."""
    tipos = api.listar_tipos(request.user)
    return {
        "filas": [{"tipo": tipo, "acciones": api.acciones_permitidas(request.user, tipo)} for tipo in tipos],
        "catalogo": api.catalogo(),
        "es_gerente": request.user.rol == GERENTE,
        **extra,
    }


def _con_ventana(request, plantilla, **contexto):
    """La ventana ``plantilla``: sola si el pedido es de HTMX; si no, la lista con la ventana abierta (respaldo sin JavaScript)."""
    if _es_htmx(request):
        return render(request, plantilla, contexto)
    return render(request, "iot/tipos/lista.html", _contexto_de_la_lista(request, plantilla_de_ventana=plantilla, **contexto))


@rol_requerido(GERENTE, AGRONOMO)
def tipos(request):
    """«Tipos de actuador» (IOT-CNS-TAC, ``tipos`` del prototipo): todos los tipos con sus acciones y, debajo, el catálogo de
    capacidades en solo lectura. Para el Agrónomo, sin botones. No audita (regla 4)."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "iot/tipos/lista.html", _contexto_de_la_lista(request))


# ---- el formulario de un tipo (IOT-ALT-TAC e IOT-MOD-TAC) ----


def _datos_de_un_tipo(tipo):
    """Los datos del formulario de un tipo guardado: cada acción activa con el id de la original."""
    return api.DatosDeTipoActuador(
        nombre=tipo.nombre_actuador,
        tiempo_minimo=str(tipo.tiempo_minimo_entre_comandos),
        acciones=[
            api.DatosDeAccion(
                nombre=a.nombre_accion,
                comando=a.comando.codigo,
                minimo=a.valor_minimo,
                maximo=a.valor_maximo,
                unidad=a.unidad_valor,
                id=a.pk,
            )
            for a in tipo.acciones_activas
        ],
    )


def _filas_del_formulario(datos, tipo):
    """Las filas de acciones como las dibuja la plantilla: cada una con su índice, si lleva valor su lista de unidades y, en una
    modificación, qué se bloquea (la acción en uso no se renombra y ni ella ni una con historial cambian de comando ni de unidad)."""
    comandos = {x["comando"].codigo: x["comando"] for grupo in api.catalogo() for x in grupo["comandos"]}
    usos = api.acciones_en_uso(tipo) if tipo else {}
    con_historial = api.acciones_con_historial(tipo) if tipo else set()
    filas = []
    for i, dato in enumerate(datos.acciones):
        comando = comandos.get(str(dato.comando or "").strip())
        lleva_valor = bool(comando and comando.lleva_valor)
        en_uso = bool(dato.id and usos.get(dato.id))
        con_comandos = bool(dato.id and dato.id in con_historial)
        filas.append(
            {
                "i": i,
                "id": dato.id,
                "nombre": dato.nombre or "",
                "comando": comando.codigo if comando else "",
                "lleva_valor": lleva_valor,
                "minimo": "" if dato.minimo is None else dato.minimo,
                "maximo": "" if dato.maximo is None else dato.maximo,
                "unidad": (dato.unidad or UNIDAD_PROPUESTA) if lleva_valor else "",
                "unidades": UNIDADES_POR_COMANDO.get(comando.codigo, []) if comando else [],
                "bloquea_nombre": en_uso,
                "bloquea_comando": en_uso or con_comandos,
                "motivo": "La acción está en uso: no se renombra ni cambia su comando o su unidad."
                if en_uso
                else ("Tiene comandos en su historial: su comando y su unidad no se cambian." if con_comandos else ""),
            }
        )
    return filas


def _errores_del_servicio(error):
    """``({campo: [mensajes]}, [mensajes generales])`` de un ``ValidationError`` del servicio."""
    errores = {campo: [e.message for e in lista] for campo, lista in error.error_dict.items()}
    return errores, errores.pop(NON_FIELD_ERRORS, [])


def _dibujar_formulario(request, tipo, datos, errores=None, general=None, solo_acciones=False):
    """La página del formulario o, con HTMX y ``solo_acciones``, el fragmento de las acciones."""
    contexto = {
        "tipo": tipo,
        "datos": datos,
        "filas": _filas_del_formulario(datos, tipo),
        "total": len(datos.acciones),
        "catalogo": api.catalogo(),
        "errores": errores or {},
        "general": general or [],
        "aviso_de_equipos": "",
        "es_gerente": True,
    }
    if tipo is not None:
        equipos = api.equipos_afectados(tipo)
        if equipos:
            total = sum(cantidad for _, cantidad in equipos)
            contexto["aviso_de_equipos"] = (
                f"Los cambios afectan a {total} equipo{'s' if total != 1 else ''} de este tipo: "
                f"{api.texto_de_equipos_afectados(equipos)}."
            )
    if solo_acciones:
        return render(request, "iot/tipos/_acciones.html", contexto)
    return render(request, "iot/tipos/formulario.html", contexto)


def _cambio_de_filas(request, datos):
    """Aplica al formulario lo que pidió un botón que no guarda: «Agregar acción» (una fila más), «Quitar» (saca esa fila) o la
    actualización de las filas al cambiar de comando. Devuelve ``True`` si fue uno de esos pedidos."""
    if "agregar" in request.POST:
        datos.acciones.append(api.DatosDeAccion(nombre="", comando=""))
    elif "quitar" in request.POST:
        try:
            del datos.acciones[int(request.POST["quitar"])]
        except (ValueError, IndexError):
            pass
    elif "refrescar" not in request.POST:
        return False
    return True


def _formulario(request, tipo):
    """Alta (``tipo`` es ``None``) o modificación de un tipo. Los botones de las acciones solo vuelven a dibujar; «guardar» llama
    al servicio y, si lo rechaza, dibuja el formulario con los errores por campo y lo escrito."""
    if request.method == "POST":
        datos = api.DatosDeTipoActuador.desde_post(request.POST)
        if _cambio_de_filas(request, datos):
            return _dibujar_formulario(request, tipo, datos, solo_acciones=_es_htmx(request))
        try:
            if tipo is None:
                guardado = api.alta_tipo_actuador(request.user, datos)
                messages.success(request, f"Tipo de actuador creado: {guardado.nombre_actuador}.")
            else:
                guardado = api.modificar_tipo_actuador(request.user, tipo.pk, datos)
                messages.success(request, f"Se guardó el tipo de actuador {guardado.nombre_actuador}.")
        except ValidationError as error:
            errores, general = _errores_del_servicio(error)
            return _dibujar_formulario(request, tipo, datos, errores, general)
        return redirect("iot:tipos")
    if tipo is None:
        datos = api.DatosDeTipoActuador(
            nombre="", tiempo_minimo=TIEMPO_PROPUESTO, acciones=[api.DatosDeAccion(nombre="", comando="")]
        )
    else:
        datos = _datos_de_un_tipo(tipo)
    return _dibujar_formulario(request, tipo, datos)


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def tipo_nuevo(request):
    """Nuevo tipo de actuador (IOT-ALT-TAC, ``tac-new`` del prototipo). Solo el Gerente."""
    return _formulario(request, None)


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def tipo_modificar(request, tipo_id):
    """Modificar un tipo de actuador (IOT-MOD-TAC, ``tac-mod`` del prototipo). Uno inactivo no se modifica: solo se reactiva."""
    tipo = api.obtener_tipo(request.user, tipo_id)
    if api.ACCION_MODIFICAR not in api.acciones_permitidas(request.user, tipo):
        messages.error(request, "El tipo de actuador está dado de baja: solo se puede reactivar.")
        return redirect("iot:tipos")
    return _formulario(request, tipo)


# ---- baja y reactivación ----


@rol_requerido(GERENTE)
@never_cache
@vary_on_headers("HX-Request")
def tipo_baja(request, tipo_id):
    """Dar de baja un tipo (IOT-BAJ-TAC, ventana ``tbaj`` del prototipo), con confirmación previa. Con equipos que no están dados de
    baja (precondición c) la ventana lo dice y no ofrece confirmar. Abrirla (GET) no cambia nada; la baja es un POST."""
    tipo = api.obtener_tipo(request.user, tipo_id)
    if api.ACCION_BAJA not in api.acciones_permitidas(request.user, tipo):
        messages.error(request, "El tipo de actuador ya está dado de baja.")
        return redirect("iot:tipos")
    error = ""
    if request.method == "POST":
        try:
            api.baja_tipo_actuador(request.user, tipo.pk)
        except ValidationError as rechazo:
            error = rechazo.messages[0]
        else:
            messages.success(request, f"El tipo de actuador {tipo.nombre_actuador} quedó inactivo.")
            return redirect("iot:tipos")
    equipos = api.equipos_afectados(tipo)
    impedimento = api.mensaje_de_equipos_activos(equipos) if equipos else ""
    return _con_ventana(request, PLANTILLA_DE_BAJA, tipo=tipo, impedimento=impedimento, error=error)


@rol_requerido(GERENTE)
def tipo_reactivar(request, tipo_id):
    """Reactivar un tipo dado de baja (IOT-MOD-TAC, postcondición b), sin ventana: no tiene validaciones. Solo POST."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    tipo = api.obtener_tipo(request.user, tipo_id)
    try:
        api.reactivar_tipo_actuador(request.user, tipo.pk)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"El tipo de actuador {tipo.nombre_actuador} está activo de nuevo.")
    return redirect("iot:tipos")
