# Servicios del mantenimiento técnico del IoT (IOT-07; docs/casos_de_uso/iot/mantenimiento_automatico.md): las lecturas de las órdenes (este paso) y, en los pasos
# siguientes, la orden al escalar, su cancelación y el traspaso del Técnico. Las lecturas no escriben, no bloquean y no consultan por fila.

from iot.models import MantenimientoTecnico

A_REALIZAR = "a_realizar"
_RANGO_DE_PRIORIDAD = {"alta": 0, "media": 1, "baja": 2}


def _clave_de_a_realizar(orden):
    """El orden de las órdenes (docs/modelo/produccion.md, «Listas fijas»): fecha programada, prioridad (sin valor cuenta como media) e id."""
    return (orden.fecha_programada_orden, _RANGO_DE_PRIORIDAD.get(orden.prioridad_orden, 1), orden.pk)


def mantenimientos_del_equipo(equipo):
    """Regla 6 de IOT-CNS-HDW: todas las órdenes del equipo. Primero las «a realizar» (fecha programada, prioridad, id); después las demás, por fecha de resolución de la más
    nueva a la más vieja (desempata el id, también de mayor a menor). Una consulta, con el Técnico cargado."""
    ordenes = list(MantenimientoTecnico.objects.filter(hardware=equipo).select_related("tecnico"))
    vigentes = sorted((o for o in ordenes if o.estado_orden == A_REALIZAR), key=_clave_de_a_realizar)
    resueltas = sorted((o for o in ordenes if o.estado_orden != A_REALIZAR), key=lambda o: (o.fecha_resolucion_orden, o.pk), reverse=True)
    return vigentes + resueltas


def mantenimientos_a_realizar_del_tecnico(tecnico):
    """Las órdenes «a realizar» asignadas a ``tecnico``, en el orden de las órdenes, con el invernadero y los equipos cargados (dos consultas más, no una por orden). Las usan el
    Inicio del Técnico y las asignaciones de su cuenta."""
    ordenes = MantenimientoTecnico.objects.filter(tecnico_id=tecnico.pk, estado_orden=A_REALIZAR).select_related("invernadero").prefetch_related("hardware")
    return sorted(ordenes, key=_clave_de_a_realizar)


# ---- La orden al escalar (IOT-RSV-CMD, postcondiciones k y l, extensiones 4b.4, 4b.4a y 4b.4b; D-73, D-79 puntos 3 a 7) ----
# La llama el escalamiento de ``comandos.py`` (el resultado ``fallo`` en el último intento y el último intento vencido «sin respuesta»), en la transacción del mensaje, con invernadero → sistema →
# nodo → actuador → comando ya bloqueados (D-78, punto 11). Después de pasar el actuador a «fuera de servicio» y ANTES de asegurar la alerta, porque el texto de la alerta necesita el código de la orden.
# Bloquea, además, la orden existente del actuador (``FOR NO KEY UPDATE`` sobre ``OrdenTrabajo``, la misma fila que bloquea ``cancelar_orden_incluida``): sin cuentas ni tipo (D-82 no aplica).

from collections import namedtuple

from django.utils import timezone

from core import notificaciones
from produccion.models import OrdenTrabajo
from produccion.servicios import ordenes as ordenes_de_produccion

# ``caso`` es ``creada``, ``sin_tecnico`` u ``orden_existente``; ``orden`` es nula en ``sin_tecnico``; ``sufijo`` es la frase que la alerta suma a su texto base (D-79, punto 3).
OrdenAutomatica = namedtuple("OrdenAutomatica", "orden caso sufijo")
CREADA, SIN_TECNICO, ORDEN_EXISTENTE = "creada", "sin_tecnico", "orden_existente"

LARGO_DE_LA_ALERTA = 200  # ``Alerta.descripcion_alerta``
LARGO_DEL_NOMBRE = 40
LARGO_DEL_AVISO = 500
LARGO_DE_LA_DESCRIPCION = 500  # ``OrdenTrabajo.descripcion_orden``


def _recortar(texto, largo):
    """``texto`` con a lo sumo ``largo`` caracteres, terminado en «…» si se recortó."""
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _nombre_del_tecnico(tecnico):
    """«Nombre Apellido» (o el correo si no tiene nombre), hasta 40 caracteres con «…» (D-79, punto 5)."""
    return _recortar(tecnico.get_full_name() or tecnico.email, LARGO_DEL_NOMBRE)


def _sufijo(caso, orden, tecnico):
    """La frase de cada caso (D-79, punto 3)."""
    if caso == CREADA:
        return f" · Orden de mantenimiento {orden.codigo} asignada a {_nombre_del_tecnico(tecnico)}."
    if caso == SIN_TECNICO:
        return " · El invernadero no tiene Técnico: la orden de mantenimiento deberá planificarse cuando se asigne uno."
    return f" · Ya está en la orden de mantenimiento {orden.codigo}, a realizar."


def descripcion_de_la_alerta(identificador, accion, intentos, ultimo, sufijo):
    """El texto de la alerta «comando fallido»: el de D-78 (punto 10) más el ``sufijo`` entero. Si pasa de 200, se recorta con «…» primero el detalle del último resultado y, si todavía no
    entra, el texto base (D-79, punto 5)."""
    cabeza = f"{identificador} · {accion} no se ejecutó en {intentos} intentos (último: "
    lugar = LARGO_DE_LA_ALERTA - len(sufijo)
    if len(cabeza) + len(ultimo) + 1 <= lugar:
        return f"{cabeza}{ultimo}){sufijo}"
    para_el_detalle = lugar - len(cabeza) - 1
    if para_el_detalle >= 2:
        return f"{cabeza}{_recortar(ultimo, para_el_detalle)}){sufijo}"
    return _recortar(f"{cabeza}{ultimo})", lugar) + sufijo


def _descripcion_de_la_orden(comando, ultimo_resultado):
    """D-79, punto 7: «CMD-{id} · {acción}[ {valor} {unidad}] no se ejecutó en {n} intentos. Último resultado: {Falló: {detalle} | Sin respuesta}.», hasta 500."""
    accion = comando.accion
    valor = f" {comando.valor_comando} {accion.unidad_valor}" if comando.valor_comando is not None else ""
    return _recortar(
        f"CMD-{comando.pk} · {accion.nombre_accion}{valor} no se ejecutó en {comando.cantidad_intentos} intentos. Último resultado: {ultimo_resultado}.",
        LARGO_DE_LA_DESCRIPCION,
    )


def _orden_existente(actuador):
    """La primera orden «a realizar» del actuador, bloqueada, o ``None``. Se relee con el bloqueo: si otra operación la canceló mientras esperaba, ya no cuenta (4b.4b)."""
    ids = list(MantenimientoTecnico.objects.filter(hardware=actuador, estado_orden=A_REALIZAR).values_list("pk", flat=True))
    if not ids:
        return None
    bloqueadas = list(OrdenTrabajo.objects.select_for_update(no_key=True).filter(pk__in=ids, estado_orden=A_REALIZAR).order_by("pk"))
    return MantenimientoTecnico.objects.get(pk=bloqueadas[0].pk) if bloqueadas else None


def crear_orden_automatica(comando, ahora):
    """Extensión 4b.4 de IOT-RSV-CMD: crea la orden de mantenimiento «revisión» del actuador del ``comando`` para el Técnico del invernadero y se la avisa. Devuelve ``OrdenAutomatica``.

    - 4b.4a: sin Técnico asignado no se crea. Con uno inactivo, SÍ (regla «Orden de mantenimiento automática»); solo se omite el aviso (D-79, punto 6).
    - 4b.4b: si el actuador ya tiene una orden «a realizar», no se crea otra (D-73, punto 5) ni se avisa.
    - Si se crea: número de ``siguiente_numero``, sin Agrónomo, prioridad alta, creada y programada para el día de ``ahora`` (que se recibe: nunca se lee la fecha), con la descripción de D-79.
    - Postcondición l: aviso al Técnico (solo con la cuenta activa), «Orden OT-0231 de mantenimiento asignada».
    La asociación con la alerta la hace ``asociar_alerta``, después de crearla."""
    actuador = comando.actuador
    invernadero = actuador.sistema.invernadero
    tecnico = invernadero.tecnico
    if tecnico is None:
        return OrdenAutomatica(None, SIN_TECNICO, _sufijo(SIN_TECNICO, None, None))
    existente = _orden_existente(actuador)
    if existente is not None:
        return OrdenAutomatica(existente, ORDEN_EXISTENTE, _sufijo(ORDEN_EXISTENTE, existente, tecnico))
    hoy = timezone.localtime(ahora).date()
    if comando.resultado_comando == "sin_respuesta":
        ultimo = "Sin respuesta"
    else:
        ultimo = f"Falló: {comando.detalle_resultado}" if comando.detalle_resultado else "Falló"
    orden = MantenimientoTecnico.objects.create(
        numero=ordenes_de_produccion.siguiente_numero(),
        invernadero=invernadero,
        tecnico=tecnico,
        agronomo=None,
        tipo_mantenimiento=MantenimientoTecnico.TipoMantenimiento.REVISION,
        prioridad_orden=OrdenTrabajo.Prioridad.ALTA,
        fecha_creacion_orden=hoy,
        fecha_programada_orden=hoy,
        descripcion_orden=_descripcion_de_la_orden(comando, ultimo),
    )
    orden.hardware.add(actuador)
    if tecnico.is_active:
        notificaciones.notificar(
            tecnico,
            f"Orden {orden.codigo} de mantenimiento asignada",
            _recortar(f"Revisión de {actuador.identificador_equipo} en {invernadero.nombre_invernadero}, prioridad alta, para hoy. {orden.descripcion_orden}", LARGO_DEL_AVISO),
        )
    return OrdenAutomatica(orden, CREADA, _sufijo(CREADA, orden, tecnico))


def asociar_alerta(orden, alerta):
    """R048: ``orden.alerta = alerta``. No hace nada si no hay alerta (invernadero inactivo) o si la alerta ya tiene otra orden (R048 es 0..1: la nueva queda sin alerta)."""
    if alerta is None or MantenimientoTecnico.objects.filter(alerta=alerta).exists():
        return
    orden.alerta = alerta
    orden.save(update_fields=["alerta"])


# ---- Cancelar la orden desde la ficha (PROD-CNL-ORD para un mantenimiento: 4d, 6a, 8a, 8e, 9a y las postcondiciones j, k y m; D-73 puntos 2 a 4; D-79 puntos 1, 2 y 7) ----
# Bloqueos (siempre ``FOR NO KEY UPDATE``; docs/patrones/bloqueos.md, orden de ``produccion`` con los niveles del IoT en el medio): las cuentas del actor y del Técnico de la orden, en UNA consulta →
# el invernadero → los sistemas y los equipos de la orden (en orden de id) → la orden y sus reservas (las bloquea ``cancelar_orden_incluida``). No toma el tipo de actuador (D-82 no aplica).

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404

from core.models import RegistroAuditoria, Usuario, referencia
from inventario.servicios import stock
from iot.alcance import invernaderos_que_consulta, puede_operar
from iot.models import Hardware, SistemaIoT
from iot.servicios.sistemas import _error_de_alcance, _exigir_operador
from maestros.servicios import alertas as api_alertas
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general
from produccion.errores import ErrorDeProduccion
from produccion.models import ReservaInsumo

LARGO_DEL_MOTIVO = 300
AVISO_DE_LA_ALERTA = "La alerta «comando fallido» sigue activa: se resuelve cuando el equipo vuelva a estar activo."
ORDEN_YA_NO_PENDIENTE = "La orden ya no está a realizar: otra operación la canceló."

# ``repuestos`` son las reservas de insumo activas de la orden (vacías en esta ronda); ``aviso`` es el texto fijo de que la alerta sigue activa (D-73, punto 4).
ResumenDeCancelacionDeMantenimiento = namedtuple("ResumenDeCancelacionDeMantenimiento", "orden equipos tipo_texto tecnico repuestos aviso")


def _motivo_valido(motivo):
    """Extensión 6a: el motivo es obligatorio, de 1 a 300 caracteres y sin espacios al borde. Se valida ANTES de llamar a ``cancelar_orden_incluida``, que recorta sin avisar."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError({"motivo": [ValidationError("Indicá el motivo de la cancelación.", code="motivo_obligatorio")]})
    if len(motivo) > LARGO_DEL_MOTIVO:
        raise ValidationError({"motivo": [ValidationError(f"El motivo no puede pasar de {LARGO_DEL_MOTIVO} caracteres.", code="motivo_largo")]})
    return motivo


def _previo(actor, orden_id):
    """Antes de bloquear: ``PermissionDenied`` si ``actor`` no es Agrónomo ni Gerente activo; ``Http404`` si la orden no existe, no es un mantenimiento o su invernadero está fuera del alcance de consulta (D-28).
    Devuelve el invernadero y el Técnico de la orden, tal como se leyeron (se vuelven a verificar con los bloqueos)."""
    _exigir_operador(actor)
    fila = MantenimientoTecnico.objects.filter(pk=orden_id).values("invernadero_id", "tecnico_id").first()
    if fila is None or not invernaderos_que_consulta(actor).filter(pk=fila["invernadero_id"]).exists():
        raise Http404("No existe esa orden de mantenimiento.")
    return fila


def resumen_de_cancelacion_de_mantenimiento(actor, orden_id):
    """Paso 4d y 6 de PROD-CNL-ORD para un mantenimiento: lo que muestra la ventana «Cancelar orden». No escribe ni bloquea. Quien solo consulta (el Gerente con un Agrónomo activo) recibe
    ``PermissionDenied``; una orden que ya no está «a realizar», ``orden_no_pendiente``."""
    _previo(actor, orden_id)
    orden = MantenimientoTecnico.objects.select_related("invernadero", "tecnico").get(pk=orden_id)
    if not puede_operar(actor, orden.invernadero):
        raise PermissionDenied("Este invernadero lo operás solo si no tiene un Agrónomo activo.")
    if orden.estado_orden != A_REALIZAR:
        raise _error_general(ORDEN_YA_NO_PENDIENTE, "orden_no_pendiente")
    repuestos = list(ReservaInsumo.objects.filter(orden_id=orden.pk, estado=ReservaInsumo.Estado.ACTIVA).select_related("insumo_invernadero__insumo").order_by("pk"))
    return ResumenDeCancelacionDeMantenimiento(
        orden, list(orden.hardware.order_by("pk")), orden.get_tipo_mantenimiento_display(), orden.tecnico, repuestos, AVISO_DE_LA_ALERTA
    )


def cancelar_mantenimiento(actor, orden_id, motivo):
    """Cancela una orden de mantenimiento «a realizar» desde la ficha del equipo y la devuelve.

    - Quién (D-79, punto 2): el alcance del IoT, el Agrónomo a cargo o, sin Agrónomo activo, el Gerente (excepción a «el Gerente no cancela» de PROD-CNL-ORD). Se vuelve a verificar DESPUÉS de
      bloquear (``fuera_de_alcance``). Otros roles, ``PermissionDenied``; fuera del alcance de consulta, ``Http404``.
    - Extensión 6a: el motivo (``motivo_obligatorio`` y ``motivo_largo``, del campo ``motivo``). Extensión 8a: si ya no está «a realizar», ``orden_no_pendiente``. Si entre la lectura y los bloqueos
      cambió su Técnico (un traspaso), ``cambio_simultaneo``.
    - Efecto: ``cancelar_orden_incluida(actor, orden, motivo, avisar=False)`` de ``produccion`` (D-73, punto 3). Postcondición j: el equipo conserva su estado. D-73 punto 4: la alerta NO se resuelve.
    - Postcondición k y 9a: aviso al Técnico, solo con la cuenta activa, con el texto de PROD-CNL-ORD («Mantenimiento técnico»). Postcondición m y D-36: UN registro ``cancelacion_orden`` con la orden,
      sus reservas y las alertas resueltas como afectados; en ``datos``, ``cancelada_desde = iot`` y los equipos de la orden. Todo o nada (D-22)."""
    previo = _previo(actor, orden_id)
    motivo = _motivo_valido(motivo)
    equipo_ids = sorted(MantenimientoTecnico.hardware.through.objects.filter(mantenimientotecnico_id=orden_id).values_list("hardware_id", flat=True))
    sistema_ids = sorted(set(Hardware.objects.filter(pk__in=equipo_ids).values_list("sistema_id", flat=True)))
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, previo["tecnico_id"]}).order_by("pk"))
        _actor_sigue_activo(actor)
        invernadero = api_alertas.bloquear_invernadero_para_alertas(previo["invernadero_id"])
        if not puede_operar(actor, invernadero):
            raise _error_de_alcance(actor, invernadero)
        list(SistemaIoT.objects.select_for_update(no_key=True).filter(pk__in=sistema_ids).order_by("pk"))
        equipos = list(Hardware.objects.select_for_update(no_key=True).filter(pk__in=equipo_ids).order_by("pk"))
        orden = MantenimientoTecnico.objects.select_related("invernadero", "tecnico").get(pk=orden_id)
        if orden.estado_orden != A_REALIZAR:
            raise _error_general(ORDEN_YA_NO_PENDIENTE, "orden_no_pendiente")
        if orden.tecnico_id != previo["tecnico_id"]:
            raise _error_general("Mientras cancelabas, cambió el Técnico de la orden. Volvé a abrir la cancelación.", "cambio_simultaneo")
        try:
            resultado = ordenes_de_produccion.cancelar_orden_incluida(actor, orden, motivo, avisar=False)
        except ErrorDeProduccion as error:  # otra operación la canceló entre la lectura y su bloqueo
            if error.codigo == "orden_no_pendiente":
                raise _error_general(ORDEN_YA_NO_PENDIENTE, "orden_no_pendiente") from error
            raise
        if orden.tecnico.is_active:  # extensión 9a: sin Técnico activo no se avisa
            titulo, detalle = ordenes_de_produccion.texto_de_cancelacion(orden, motivo, actor)
            notificaciones.notificar_a_varios([orden.tecnico], titulo, detalle, excluir=actor)
        datos = {"cancelada_desde": "iot", "equipos_de_la_orden": [referencia(equipo) for equipo in equipos]}
        if resultado.alertas_resueltas:
            datos["alertas_resueltas"] = [referencia(alerta) for alerta in resultado.alertas_resueltas]
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.CANCELACION_ORDEN,
            afectados=[orden, *resultado.reservas, *resultado.alertas_resueltas],
            detalle={
                "cambios": {
                    "estado": {"antes": A_REALIZAR, "despues": "cancelada"},
                    "fecha_resolucion_orden": {"antes": None, "despues": f"{stock.hoy():%d/%m/%Y}"},
                    "motivo_cancelacion": {"antes": None, "despues": motivo},
                },
                "datos": datos,
            },
        )
        return resultado.orden


# ---- El Técnico del invernadero (IOT-07; PROD-MOD-INV regla 3 y postcondición b, USR-BAJ-USR regla 4, D-79 puntos 4 y 9) ----
# Los registra ``IotConfig.ready()``. El traspaso lo ejecuta ``maestros`` (``modificar_invernadero``), con las cuentas y el invernadero ya bloqueados; este registrante bloquea las filas de las órdenes
# después, en orden de id (contrato de ``maestros/extensiones.py``). «Lo que recibe» va por ``contar``, no por ``registrar_aviso_de_traspaso`` (D-98, punto 1: ese es para lo que se cancela o se pierde).

from core.extensiones import Asignacion, SeccionDeInicio
from core.models import Usuario, rol_de

DESCRIPCION_DEL_TRASPASO = "mantenimientos técnicos a realizar"
PLANTILLA_DEL_INICIO = "iot/_inicio_mantenimientos.html"


def _a_traspasar(invernadero, entrante):
    """Las órdenes «a realizar» del invernadero que todavía no son del Técnico entrante: TODAS, no solo las del saliente (D-79, punto 9)."""
    return MantenimientoTecnico.objects.filter(invernadero=invernadero, estado_orden=A_REALIZAR).exclude(tecnico_id=entrante.pk)


def contar_traspaso(invernadero, rol, saliente, entrante):
    """``registrar_traspaso``, ``contar``: lo que recibiría el Técnico entrante, para la ventana de la regla 2 y el aviso de la postcondición c de PROD-MOD-INV. Solo para el rol ``tecnico`` y con
    persona entrante. Una consulta de conteo."""
    if rol != "tecnico" or entrante is None:
        return []
    cantidad = _a_traspasar(invernadero, entrante).count()
    return [(DESCRIPCION_DEL_TRASPASO, cantidad)] if cantidad else []


def traspasar_mantenimientos(actor, invernadero, rol, saliente, entrante):
    """``registrar_traspaso``, ``traspasar``: las órdenes «a realizar» del invernadero pasan al Técnico entrante con UNA consulta de actualización. Bloquea las filas de ``OrdenTrabajo`` (las mismas
    que ``cancelar_orden_incluida``, así una cancelación y un traspaso a la vez se ponen en fila), en orden de id y después del invernadero, y las vuelve a leer. Sin entrante, no hace nada: ``tecnico`` es
    obligatorio y la orden queda con el Técnico anterior. Devuelve las órdenes tocadas, para que queden entre los afectados de ``modificacion_invernadero`` (D-36, D-81). No audita por su cuenta."""
    if rol != "tecnico" or entrante is None:
        return []
    ids = list(_a_traspasar(invernadero, entrante).order_by("pk").values_list("pk", flat=True))
    if not ids:
        return []
    list(OrdenTrabajo.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk"))
    tocadas = list(_a_traspasar(invernadero, entrante).order_by("pk"))  # releídas con el bloqueo: una pudo cancelarse mientras esperaba
    if tocadas:
        MantenimientoTecnico.objects.filter(pk__in=[orden.pk for orden in tocadas]).update(tecnico_id=entrante.pk)
        for orden in tocadas:
            orden.tecnico_id = entrante.pk
    return tocadas


def asignaciones_del_tecnico(cuenta):
    """``registrar_asignaciones_de_cuenta`` (regla 4 de USR-BAJ-USR): los mantenimientos «a realizar» de la cuenta de un Técnico, y qué pasará con ellos. Solo lectura; otra cuenta, ``[]``."""
    if rol_de(cuenta) != Usuario.Rol.TECNICO:
        return []
    cantidad = MantenimientoTecnico.objects.filter(tecnico_id=cuenta.pk, estado_orden=A_REALIZAR).count()
    if not cantidad:
        return []
    return [Asignacion("Mantenimientos técnicos a realizar", cantidad, "Pasan a quien el Gerente asigne al modificar el invernadero.")]


def seccion_de_mantenimientos(usuario):
    """``registrar_seccion_de_inicio``: la sección «Mantenimientos a realizar» del Inicio de un Técnico activo, o ``None`` para cualquier otro. ``hoy`` va en el contexto para marcar las vencidas: el punto
    de extensión solo recibe al usuario, así que es la única lectura de la fecha de esta tarea."""
    if not getattr(usuario, "is_active", False) or rol_de(usuario) != Usuario.Rol.TECNICO:
        return None
    return SeccionDeInicio(PLANTILLA_DEL_INICIO, {"ordenes": mantenimientos_a_realizar_del_tecnico(usuario), "hoy": timezone.localdate()})
