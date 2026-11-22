# Servicios del Sistema IoT (IOT-02): registrar (IOT-REG-SIS), modificar y regenerar el token (IOT-MOD-SIS) y la lectura que usan las
# pantallas. Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36 (docs/patrones/auditoria.md).
# Casos de uso: docs/casos_de_uso/iot/sistema_iot.md; orden de docs/patrones/abm.md, sección 2.
#
# Bloqueos (siempre ``FOR NO KEY UPDATE``, docs/patrones/bloqueos.md y «Cómo se aplica»): el invernadero (``bloquear_invernadero_activo`` al
# registrar, D-40), quien actúa sigue activo, el alcance se vuelve a verificar DESPUÉS de bloquear (extensión 8b) y, al modificar, el sistema y su
# nodo, releídos. El alta no toma más: un invernadero tiene un solo sistema no dado de baja y lo respalda un índice único parcial.
#
# El token (D-70, punto 3): se genera con ``core.enlaces.nuevo_token`` y se guarda SOLO su resumen. Nunca va a la auditoría, a un mensaje de
# error ni a un registro. Lo devuelve la función, que lo muestra una sola vez.
#
# «Se completa en IOT-06»: ``acciones_permitidas`` suma desactivar, activar y dar de baja el sistema.

from collections import namedtuple
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.db.models.functions import Lower
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from core.enlaces import nuevo_token
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.categorias import REPUESTOS_DE_HARDWARE
from inventario.models import Insumo
from iot.alcance import invernaderos_que_consulta, invernaderos_que_opera, puede_operar
from iot.models import NodoCentral, SistemaIoT
from iot.validadores import texto, validar_fecha_de_instalacion, validar_rango_de_la_solucion, validar_texto
from maestros.extensiones import EstadoIot, Impedimento
from maestros.models import Invernadero
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, bloquear_invernadero_activo

ACCION_MODIFICAR = "modificar"
ACCION_REGENERAR_TOKEN = "regenerar_token"

LARGO_DEL_NOMBRE = NodoCentral._meta.get_field("nombre_nodo").max_length
LARGO_DEL_MODELO = NodoCentral._meta.get_field("modelo_hardware").max_length
LARGO_DE_LA_SERIE = NodoCentral._meta.get_field("numero_serie").max_length

Estado = SistemaIoT.Estado
# Los estados en que el sistema cuenta como «no dado de baja» (R068).
ESTADOS_VIGENTES = (Estado.ACTIVO, Estado.DESCONECTADO)

Conectividad = namedtuple("Conectividad", "estado texto")
# Un invernadero que se ofrece en el paso 2: su Técnico activo (o ``None``: «sin Técnico») y si tuvo un sistema dado de baja (extensión 3a).
Elegible = namedtuple("Elegible", "invernadero tecnico tuvo_sistema")
# Lo que muestra el resumen del paso 6 (con los datos ya validados).
ResumenDeRegistro = namedtuple(
    "ResumenDeRegistro",
    "invernadero tecnico sin_tecnico nombre modelo numero_serie fecha_instalacion insumo temp_min temp_max tuvo_sistema_dado_de_baja",
)


@dataclass
class DatosDeSistema:
    """Lo que manda el formulario: el invernadero y los datos del nodo (registro) o solo nombre, modelo, serie y rango (modificación,
    que ignora el resto). Los valores pueden venir como texto: el servicio los valida."""

    invernadero_id: object = None
    nombre: object = ""
    modelo: object = ""
    numero_serie: object = ""
    fecha_instalacion: object = None
    insumo_id: object = None
    temp_min: object = ""
    temp_max: object = ""

    @classmethod
    def desde_post(cls, post, invernadero_id=None):
        """Arma los datos desde el POST (``nombre``, ``modelo``, ``numero_serie``, ``fecha_instalacion``, ``insumo``, ``temp_min`` y
        ``temp_max``); tolera campos que faltan: los errores los da el servicio."""
        return cls(
            invernadero_id=invernadero_id,
            nombre=post.get("nombre", ""),
            modelo=post.get("modelo", ""),
            numero_serie=post.get("numero_serie", ""),
            fecha_instalacion=post.get("fecha_instalacion") or None,
            insumo_id=post.get("insumo") or None,
            temp_min=post.get("temp_min", ""),
            temp_max=post.get("temp_max", ""),
        )


# ---- comunes ----


def _exigir_operador(actor):
    """Precondición a de IOT-REG-SIS e IOT-MOD-SIS: ``actor`` es un Agrónomo o un Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        raise PermissionDenied("Solo el Agrónomo y el Gerente operan el IoT.")


def _error_de_alcance(actor, invernadero):
    """Extensión 8b de IOT-REG-SIS: el error general con el motivo, «Ya no operás el IoT de este invernadero: …»."""
    if not invernadero.activo:
        motivo = "está dado de baja"
    elif rol_de(actor) == Usuario.Rol.GERENTE:
        motivo = "ahora tiene un Agrónomo activo, y el Gerente lo opera solo cuando no hay uno"
    else:
        motivo = "ya no lo tenés a cargo"
    return _error_general(f"Ya no operás el IoT de este invernadero: {motivo}.", "fuera_de_alcance")


def _error_sistema_existente():
    """Extensión 8a de IOT-REG-SIS."""
    return _error_general("Este invernadero ya tiene un sistema IoT.", "sistema_existente")


def _sistema_vigente(invernadero_id):
    """El sistema no dado de baja del invernadero (activo o desconectado), o ``None``."""
    return SistemaIoT.objects.filter(invernadero_id=invernadero_id, estado_sistema__in=ESTADOS_VIGENTES).first()


def insumos_de_hardware():
    """Precondición c de IOT-REG-SIS (regla 8 de IOT-ALT-HDW): los insumos ACTIVOS de la categoría del sistema «Repuestos de hardware»
    (por ``codigo``, regla 1 de 8.23), por nombre. No importa que estén habilitados en el invernadero ni que tengan stock."""
    return Insumo.objects.filter(
        tipo_insumo__codigo=REPUESTOS_DE_HARDWARE, estado_insumo=Insumo.Estado.ACTIVO
    ).order_by(Lower("nombre_insumo"), "pk")


def _tecnico_activo(invernadero):
    """El Técnico del invernadero si su cuenta está activa; si no, ``None`` (extensión 6b: «sin Técnico»)."""
    tecnico = invernadero.tecnico
    return tecnico if tecnico is not None and tecnico.is_active else None


# ---- validación (pasos 5 y 6, extensión 6a) ----


def _validar(datos, registro):
    """Normaliza y valida ``datos`` sin escribir. Junta TODOS los errores en un solo ``ValidationError`` (por campo: ``nombre``, ``modelo``,
    ``numero_serie``, ``fecha_instalacion``, ``insumo``, ``temp_solucion_min`` y ``temp_solucion_max``; general: ``sin_insumos_de_hardware``).
    Con ``registro`` valida también la fecha y el insumo, que la modificación no cambia. Devuelve un diccionario con los valores limpios."""
    errores = {}
    limpios = {}

    def revisar(campo, funcion, *argumentos):
        try:
            limpios[campo] = funcion(*argumentos)
        except ValidationError as error:
            errores.setdefault(campo, []).extend(error.error_list)

    revisar("nombre", validar_texto, datos.nombre, LARGO_DEL_NOMBRE, True, "el nombre del nodo")
    revisar("modelo", validar_texto, datos.modelo, LARGO_DEL_MODELO, True, "el modelo")
    revisar("numero_serie", validar_texto, datos.numero_serie, LARGO_DE_LA_SERIE, False, "el número de serie")
    if registro:
        revisar("fecha_instalacion", validar_fecha_de_instalacion, datos.fecha_instalacion)
        hay_insumos = insumos_de_hardware().exists()
        if not hay_insumos:  # precondición c
            errores.setdefault(NON_FIELD_ERRORS, []).append(
                ValidationError(
                    "Primero registrá en Compras e Inventario el insumo del nodo, en la categoría «Repuestos de hardware».",
                    code="sin_insumos_de_hardware",
                )
            )
        else:
            insumo = _insumo_elegido(datos.insumo_id)
            if texto(datos.insumo_id) == "":
                errores.setdefault("insumo", []).append(ValidationError("Seleccioná el insumo.", code="obligatorio"))
            elif insumo is None:
                errores.setdefault("insumo", []).append(
                    ValidationError("Elegí un insumo activo de «Repuestos de hardware».", code="insumo_invalido")
                )
            limpios["insumo"] = insumo
    try:
        limpios["temp_min"], limpios["temp_max"] = validar_rango_de_la_solucion(datos.temp_min, datos.temp_max)
    except ValidationError as error:
        for campo, lista in error.error_dict.items():
            errores.setdefault(campo, []).extend(lista)
    if errores:
        raise ValidationError(errores)
    return limpios


def _insumo_elegido(insumo_id):
    """El insumo activo de «Repuestos de hardware» con ese id, o ``None`` (vacío, no numérico, de otra categoría o inactivo)."""
    try:
        numero = int(texto(insumo_id))
    except ValueError:
        return None
    return insumos_de_hardware().filter(pk=numero).first()


def _texto_del_rango(minimo, maximo):
    """«18.0 a 24.0 °C» para la auditoría (un ``Decimal`` no es un valor permitido, D-36), o ``None`` sin rango."""
    return None if minimo is None else f"{minimo} a {maximo} °C"


# ---- registrar (IOT-REG-SIS) ----


def _invernadero_del_registro(actor, invernadero_id):
    """Lee el invernadero sin bloquearlo (para el resumen). ``Http404`` si no existe; ``fuera_de_alcance`` si ``actor`` no lo opera."""
    try:
        invernadero = Invernadero.objects.select_related("tecnico").get(pk=invernadero_id)
    except (Invernadero.DoesNotExist, TypeError, ValueError):
        raise Http404("No existe ese invernadero.") from None
    if not puede_operar(actor, invernadero):
        raise _error_de_alcance(actor, invernadero)
    return invernadero


def resumen_de_registro(actor, datos):
    """IOT-REG-SIS, pasos 5 y 6: valida todo y arma el resumen para confirmar, SIN escribir ni auditar.

    - Precondición a: Agrónomo o Gerente activos. Extensión 6a: los errores de los datos, todos juntos y por campo. Precondición c.
    - Regla «Alcance» y extensión 1a: el invernadero está dentro de lo que ``actor`` opera. Extensión 8a: sin un sistema no dado de baja.
    - Extensión 6b: ``sin_tecnico`` avisa de la alerta del Técnico. Extensión 3a: ``tuvo_sistema_dado_de_baja``.
    El registro lo vuelve a verificar todo después de bloquear: el resumen es solo lo que se ve antes de confirmar."""
    _exigir_operador(actor)
    limpios = _validar(datos, registro=True)
    invernadero = _invernadero_del_registro(actor, datos.invernadero_id)
    if _sistema_vigente(invernadero.pk) is not None:
        raise _error_sistema_existente()
    return ResumenDeRegistro(
        invernadero=invernadero,
        tecnico=_tecnico_activo(invernadero),
        sin_tecnico=_tecnico_activo(invernadero) is None,
        nombre=limpios["nombre"],
        modelo=limpios["modelo"],
        numero_serie=limpios["numero_serie"],
        fecha_instalacion=limpios["fecha_instalacion"],
        insumo=limpios["insumo"],
        temp_min=limpios["temp_min"],
        temp_max=limpios["temp_max"],
        tuvo_sistema_dado_de_baja=SistemaIoT.objects.filter(invernadero=invernadero, estado_sistema=Estado.INACTIVO).exists(),
    )


def registrar_sistema_iot(actor, datos):
    """IOT-REG-SIS, paso 8: registra el sistema IoT de un invernadero con su nodo central y su token, y devuelve ``(sistema, token)``.

    - Precondición a: Agrónomo o Gerente activos. Precondición c y reglas «Datos del nodo central» y 7 de IOT-MOD-SIS (extensión 6a).
    - Se bloquea el invernadero (``bloquear_invernadero_activo``: inactivo, extensión 8b), quien actúa sigue activo y el alcance se verifica
      DESPUÉS de bloquear (extensión 8b: ``fuera_de_alcance``). Con un sistema no dado de baja, ``sistema_existente`` (extensión 8a); si dos
      pedidos llegan a la vez, el índice único parcial de la base respalda y su ``IntegrityError`` se traduce al mismo error (nunca un 500).
    - Postcondiciones a y b: sistema «activo» y nodo «activo» (modo «remoto», sin sector). Postcondición c: el token se genera con una fuente
      segura y se guarda solo su SHA-256; se devuelve para mostrarlo una sola vez. Postcondición d: la conectividad nace «sin señal».
    - Postcondición e: ``sincronizar_alertas_de_personal`` con ``roles=["tecnico"]`` crea la alerta del Técnico si falta (D-43).
    - Postcondición f y D-36: un registro ``alta_sistema_iot`` con el sistema, el nodo y la alerta si se creó. Nunca el token ni su resumen."""
    _exigir_operador(actor)
    limpios = _validar(datos, registro=True)
    with transaction.atomic():
        invernadero = bloquear_invernadero_activo(datos.invernadero_id)
        _actor_sigue_activo(actor)
        if not puede_operar(actor, invernadero):
            raise _error_de_alcance(actor, invernadero)
        if _sistema_vigente(invernadero.pk) is not None:
            raise _error_sistema_existente()
        token, resumen = nuevo_token()
        try:
            with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
                sistema = SistemaIoT.objects.create(
                    invernadero=invernadero,
                    estado_sistema=Estado.ACTIVO,
                    temp_solucion_min=limpios["temp_min"],
                    temp_solucion_max=limpios["temp_max"],
                    token_resumen=resumen,
                    token_generado_en=timezone.now(),
                )
        except IntegrityError as error:
            if "sistema_iot_uno_por_invernadero" in str(error):
                raise _error_sistema_existente() from error
            raise
        nodo = NodoCentral.objects.create(
            sistema=sistema,
            clase="nodo",
            nombre_nodo=limpios["nombre"],
            modelo_hardware=limpios["modelo"],
            numero_serie=limpios["numero_serie"],
            fecha_instalacion=limpios["fecha_instalacion"],
            insumo=limpios["insumo"],
        )
        alertas = api_alertas.sincronizar_alertas_de_personal(invernadero, roles=["tecnico"]).creadas
        datos_del_registro = {"invernadero": referencia(invernadero), "nodo": referencia(nodo)}
        rango = _texto_del_rango(sistema.temp_solucion_min, sistema.temp_solucion_max)
        if rango:
            datos_del_registro["rango_de_la_solucion"] = rango
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_SISTEMA_IOT,
            afectados=[sistema, nodo, *alertas],
            detalle={"datos": datos_del_registro},
        )
    return sistema, token


# ---- modificar y regenerar el token (IOT-MOD-SIS) ----


def _bloquear_sistema(actor, sistema_id):
    """Bloquea el invernadero, el sistema y su nodo (``FOR NO KEY UPDATE``, ese orden), los lee de nuevo y verifica, ya bloqueados, que
    quien actúa siga activo, que el sistema no esté dado de baja (regla 6) y que ``actor`` opere el invernadero (regla 1). Devuelve
    ``(invernadero, sistema, nodo)``. ``Http404`` si el sistema no existe. Hay que llamarla dentro de ``transaction.atomic()``."""
    previo = SistemaIoT.objects.filter(pk=sistema_id).values_list("invernadero_id", flat=True).first()
    if previo is None:
        raise Http404("No existe ese sistema IoT.")
    invernadero = api_alertas.bloquear_invernadero_para_alertas(previo)
    _actor_sigue_activo(actor)
    sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=sistema_id)
    nodo = NodoCentral.objects.select_for_update(no_key=True).get(sistema=sistema)
    if sistema.estado_sistema == Estado.INACTIVO:
        raise _error_general("Un sistema IoT dado de baja no se modifica.", "sistema_dado_de_baja")
    if not puede_operar(actor, invernadero):
        raise _error_de_alcance(actor, invernadero)
    return invernadero, sistema, nodo


def modificar_sistema_iot(actor, sistema_id, datos):
    """IOT-MOD-SIS: cambia el nombre, el modelo y el número de serie del nodo y el rango de la solución, y devuelve el sistema.

    - Precondición a y regla 1: Agrónomo o Gerente activos, dentro de su alcance (``fuera_de_alcance``). Precondición b y regla 6: un
      sistema dado de baja no se modifica (``sistema_dado_de_baja``); un id que no existe, ``Http404``.
    - Reglas 2 y 7: las validaciones del registro, todos los errores juntos. La fecha, el insumo y el invernadero de ``datos`` se ignoran.
    - Regla 5: el estado no se cambia acá. El token tampoco (se regenera con ``regenerar_token``).
    - D-28: sin cambios no se escribe ni se audita. Postcondición c y D-36: un registro ``modificacion_sistema_iot`` con el antes y el
      después de cada dato que cambió. Bloqueos: el invernadero, el sistema y el nodo, releídos."""
    _exigir_operador(actor)
    limpios = _validar(datos, registro=False)
    with transaction.atomic():
        _, sistema, nodo = _bloquear_sistema(actor, sistema_id)
        cambios = {}
        for campo, antes, despues in (
            ("nombre_nodo", nodo.nombre_nodo, limpios["nombre"]),
            ("modelo_hardware", nodo.modelo_hardware, limpios["modelo"]),
            ("numero_serie", nodo.numero_serie or None, limpios["numero_serie"] or None),
            ("temp_solucion_min", sistema.temp_solucion_min, limpios["temp_min"]),
            ("temp_solucion_max", sistema.temp_solucion_max, limpios["temp_max"]),
        ):
            if antes != despues:
                como_texto = (lambda valor: None if valor is None else str(valor)) if campo.startswith("temp") else (lambda valor: valor)
                cambios[campo] = {"antes": como_texto(antes), "despues": como_texto(despues)}
        if not cambios:
            return sistema  # D-28
        nodo.nombre_nodo, nodo.modelo_hardware, nodo.numero_serie = limpios["nombre"], limpios["modelo"], limpios["numero_serie"]
        nodo.save(update_fields=["nombre_nodo", "modelo_hardware", "numero_serie"])
        sistema.temp_solucion_min, sistema.temp_solucion_max = limpios["temp_min"], limpios["temp_max"]
        sistema.save(update_fields=["temp_solucion_min", "temp_solucion_max"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_SISTEMA_IOT,
            afectados=[sistema, nodo],
            detalle={"cambios": cambios},
        )
    return sistema


def regenerar_token(actor, sistema_id):
    """IOT-MOD-SIS, postcondición b y reglas 3 y 4: genera un token nuevo, reemplaza el resumen y devuelve el token, que se muestra una sola
    vez. El anterior deja de servir en ese momento. Mismas precondiciones y bloqueos que ``modificar_sistema_iot``. Postcondición c y D-36:
    un registro ``regeneracion_token_iot`` que dice que se regeneró, sin ningún token ni resumen."""
    _exigir_operador(actor)
    with transaction.atomic():
        invernadero, sistema, nodo = _bloquear_sistema(actor, sistema_id)
        token, resumen = nuevo_token()
        sistema.token_resumen, sistema.token_generado_en = resumen, timezone.now()
        sistema.save(update_fields=["token_resumen", "token_generado_en"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REGENERACION_TOKEN_IOT,
            afectados=[sistema, nodo],
            detalle={"datos": {"invernadero": referencia(invernadero), "nodo": referencia(nodo)}},
        )
    return token


# ---- lectura ----


def invernaderos_para_registrar(actor):
    """IOT-REG-SIS, paso 2 y extensión 1a: los invernaderos que ``actor`` opera y que no tienen un sistema no dado de baja, por nombre, cada uno
    con su Técnico activo (o ``None``) y si tuvo un sistema dado de baja (extensión 3a)."""
    _exigir_operador(actor)
    dados_de_baja = SistemaIoT.objects.filter(invernadero=OuterRef("pk"), estado_sistema=Estado.INACTIVO)
    elegibles = (
        invernaderos_que_opera(actor)
        .exclude(sistemas_iot__estado_sistema__in=ESTADOS_VIGENTES)
        .select_related("tecnico")
        .annotate(_tuvo_sistema=Exists(dados_de_baja))
        .order_by(Lower("nombre_invernadero"), "pk")
    )
    return [Elegible(i, _tecnico_activo(i), i._tuvo_sistema) for i in elegibles]


def sistema_del_invernadero(actor, invernadero_id):
    """El sistema no dado de baja del invernadero elegido, o ``None`` (pestaña «Sistema IoT»). Solo consulta: Agrónomo y Gerente activos; un
    invernadero fuera de su alcance de consulta o que no existe, ``Http404``. No audita (SEG-14)."""
    _exigir_operador(actor)
    if not invernaderos_que_consulta(actor).filter(pk=invernadero_id).exists():
        raise Http404("No existe ese invernadero.")
    return _sistema_vigente(invernadero_id)


def nodo_del_sistema(sistema):
    """El nodo central del sistema (R066: uno por sistema)."""
    return NodoCentral.objects.get(sistema=sistema)


AnuncioDelNodo = namedtuple("AnuncioDelNodo", "cantidad anunciado_en sin_registrar")


def anuncio_del_nodo(sistema):
    """Lo que muestra la ficha del sistema del último anuncio de equipos del nodo (IOT-ENT-INF, extensión 1c): cuántos equipos anunció, cuándo y cuántos
    todavía no están registrados; ``None`` si el nodo no anuncia sus equipos (la compatibilidad queda «sin verificar»). **Los anuncios los escribe la API
    de IOT-03**: hasta entonces siempre es ``None``."""
    from iot.models import EquipoAnunciado
    from iot.servicios.hardware import identificadores_anunciados_libres

    anunciados = EquipoAnunciado.objects.filter(sistema=sistema)
    if not anunciados.exists():
        return None
    ultimo = anunciados.order_by("-anunciado_en").values_list("anunciado_en", flat=True).first()
    return AnuncioDelNodo(anunciados.count(), ultimo, len(identificadores_anunciados_libres(sistema)))


def conectividad(nodo, ahora):
    """«Para los cinco», «Conectividad» (regla 3 de IOT-ACT-SIS): ``en_linea`` si la última comunicación del nodo es MÁS reciente que
    ``minutos_sin_comunicacion`` (parámetro de la Configuración Operativa, leído en cada uso); si no, ``sin_senal``. Con ``ultima_comunicacion``
    nula, ``sin_senal`` con el texto «Todavía no se comunicó». No se guarda: la actualiza la API (IOT-03)."""
    if nodo.ultima_comunicacion is None:
        return Conectividad("sin_senal", "Todavía no se comunicó")
    plazo = timedelta(minutes=configuracion.obtener().minutos_sin_comunicacion)
    ultima = timezone.localtime(nodo.ultima_comunicacion).strftime("%d/%m/%Y %H:%M")
    estado = "en_linea" if ahora - nodo.ultima_comunicacion < plazo else "sin_senal"
    return Conectividad(estado, f"Última comunicación: {ultima}")


def acciones_permitidas(actor, sistema):
    """D-30: las acciones que ``actor`` puede hacer sobre ``sistema``, un ``frozenset``: modificar y regenerar el token a quien opera el IoT de
    ese invernadero (regla 1 de IOT-DSC-SIS), si el sistema no está dado de baja (regla 6 de IOT-MOD-SIS); a quien solo consulta, ninguna.
    **Se completa en IOT-06** (desactivar, activar y dar de baja). Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        return frozenset()
    if sistema.estado_sistema == Estado.INACTIVO or not puede_operar(actor, sistema.invernadero):
        return frozenset()
    return frozenset({ACCION_MODIFICAR, ACCION_REGENERAR_TOKEN})


# ---- los registrantes de `maestros` (IOT-02; docs/api/extensiones_de_maestros.md, «Estado del IoT del invernadero»; los registra ``IotConfig.ready()``) ----


def estados_de_sistemas(invernadero_ids):
    """Registrante de ``registrar_estado_iot``: ``{invernadero_id: EstadoIot}`` de los invernaderos con un sistema NO dado de baja, con la URL de la pestaña
    «Sistema IoT» de cada uno. UNA sola consulta para toda la lista (sin consultas por fila)."""
    vigentes = SistemaIoT.objects.filter(invernadero_id__in=list(invernadero_ids), estado_sistema__in=ESTADOS_VIGENTES)
    base = reverse("iot:sistema")
    return {s.invernadero_id: EstadoIot(s.estado_sistema, f"{base}?invernadero={s.invernadero_id}") for s in vigentes}


def url_de_registro(actor, invernadero):
    """Registrante de ``registrar_estado_iot``: el enlace «Registrar sistema IoT» de ``invernadero``, o ``None`` si ``actor`` no opera su IoT (ningún botón
    lleva a un 403, D-30)."""
    if actor is None or not puede_operar(actor, invernadero):
        return None
    return f"{reverse('iot:sistema_registrar')}?invernadero={invernadero.pk}"


def impedimentos_de_baja_del_invernadero(invernadero):
    """Registrante de ``registrar_impedimento_de_baja``: un invernadero con un sistema IoT activo o desconectado no se da de baja; primero se da de baja su
    sistema (precondición h de PROD-BAJ-INV, regla 6 de IOT-BAJ-SIS). Código ``sistema_iot``. Se llama con el invernadero ya bloqueado."""
    sistema = _sistema_vigente(invernadero.pk)
    if sistema is None:
        return []
    nodo = nodo_del_sistema(sistema)
    return [Impedimento("sistema_iot", f"Tiene el sistema IoT «{nodo.nombre_nodo}».", "Dalo de baja desde IoT · Sistema IoT.")]
