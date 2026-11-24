# Servicios de las reglas de actuación (IOT-06): alta, modificación (con reactivar), baja y consulta (IOT-ALT-RGL, IOT-MOD-RGL, IOT-BAJ-RGL e IOT-CNS-RGL;
# docs/casos_de_uso/iot/reglas_de_actuacion.md, con «Cómo se aplica en la ronda «IoT 1»»). Cada caso de uso es una función dentro de ``transaction.atomic()``, audita con el
# formato de D-36 (docs/patrones/auditoria.md) y recibe ``ahora``: nunca lee la hora por su cuenta. El disparo de una regla (IOT-ENT-INF, paso 6) está en ``lecturas.py``.
#
# Orden de bloqueos (siempre ``FOR NO KEY UPDATE``): en alta, modificación y reactivación, el TIPO del actuador primero (D-82: ``modificar_tipo_actuador`` mira las acciones en uso
# y el ``INSERT`` de la regla solo toma ``FOR KEY SHARE`` sobre la acción, que no frena ese cambio), después el invernadero, el sistema, el sensor, el actuador y la regla (D-78,
# punto 11). La baja no toca el tipo: invernadero, sistema y regla. El índice único parcial ``regla_actuacion_activa_unica`` respalda la regla 6 de ALT: su ``IntegrityError``
# se traduce al mismo error, nunca un 500.
#
# La acción y el valor los valida ``comandos.validar_comando``, la misma función de un comando manual (regla 4 de ALT). Este módulo no importa ``lecturas`` (ni ``nodo``): ellos importan
# este para reiniciar las reglas.

from collections import namedtuple
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404

from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios.variedades import umbral_efectivo
from iot.alcance import invernaderos_que_consulta, puede_operar
from iot.models import Accion, Actuador, Comando, NodoCentral, ReglaActuacion, Sensor, SistemaIoT
from iot.servicios.comandos import _normalizar_valor, validar_comando
from iot.servicios.sistemas import ESTADOS_VIGENTES, Estado, _error_de_alcance, _exigir_operador
from iot.servicios.tipos_actuador import bloquear_tipo_activo
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

Condicion = ReglaActuacion.Condicion
EstadoRegla = ReglaActuacion.Estado
# Regla 5 de ALT: solo estas variables admiten reglas (la temperatura y el nivel de la solución se monitorean con alertas).
VARIABLES_CON_REGLAS = ("temperatura", "humedad", "intensidad_luz")
# La variable del umbral efectivo de cada variable del sensor (la misma tabla que ``lecturas.VARIABLES_DEL_UMBRAL``, sin importar ``lecturas``).
VARIABLE_DEL_UMBRAL = {"temperatura": "temp_ambiente", "humedad": "humedad", "intensidad_luz": "intensidad_luz"}
# El texto de cada condición dentro de la frase de la regla (prototipo ``COND``).
TEXTO_DE_CONDICION = {valor: etiqueta[0].lower() + etiqueta[1:] for valor, etiqueta in Condicion.choices}

DatosParaRegla = namedtuple("DatosParaRegla", "sensores actuadores acciones")
# Un motivo por el que una regla no emite o no se evalúa: ``clave`` estable y ``texto`` visible.
Motivo = namedtuple("Motivo", "clave texto")
FiltrosDeReglas = namedtuple("FiltrosDeReglas", "estado sensor_id actuador_id", defaults=("", None, None))
FilaDeRegla = namedtuple("FilaDeRegla", "regla codigo texto evaluacion ultimo_disparo motivos")
FichaDeRegla = namedtuple("FichaDeRegla", "fila comandos")

MOTIVOS = {
    "sistema_desconectado": "No se evalúa: sistema desconectado",
    "actuador_fuera_de_servicio": "No emite: actuador fuera de servicio",
    "accion_incompatible": "No emite: acción incompatible con el nodo",
    "sin_umbral": "No se evalúa: sin umbral efectivo",
    "modo_local": "No se evalúa: nodo en modo local",
    "sector_fuera_de_servicio": "No se evalúa: sensor en un sector fuera de servicio",
    "sensor_fuera_de_servicio": "No se evalúa: sensor fuera de servicio",
}


@dataclass
class DatosDeRegla:
    """Lo que manda el formulario de una regla. Los valores pueden venir como texto: el servicio los valida. En una modificación, ``sensor_id`` y ``actuador_id`` se ignoran
    (regla 3 de MOD: no se cambian)."""

    sensor_id: object = None
    actuador_id: object = None
    condicion: object = ""
    accion_id: object = None
    valor: object = None

    @classmethod
    def desde_post(cls, post):
        """Arma los datos desde el POST (``sensor``, ``actuador``, ``condicion``, ``accion`` y ``valor``); tolera campos que faltan: los errores los da el servicio."""
        return cls(
            sensor_id=post.get("sensor") or None,
            actuador_id=post.get("actuador") or None,
            condicion=post.get("condicion", ""),
            accion_id=post.get("accion") or None,
            valor=post.get("valor"),
        )


# ---- comunes ----


def _entero(valor):
    """``valor`` como entero, o ``None`` si falta o no lo es."""
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def texto_de_regla(regla):
    """El texto de la regla (prototipo ``rglText``): «Cuando {sensor} {identificador} {condición}, {actuador} {identificador}: {acción}[ {valor} {unidad}]»."""
    return _texto(regla.sensor, regla.condicion, regla.actuador, regla.accion, regla.aplicar_valor)


def _texto(sensor, condicion, actuador, accion, valor):
    """El texto de una regla a partir de sus partes (también sirve antes de que la regla exista)."""
    texto_del_valor = f" {valor} {accion.unidad_valor}" if valor is not None else ""
    return (
        f"Cuando {sensor.get_tipo_variable_sensor_display()} {sensor.identificador_equipo} {TEXTO_DE_CONDICION.get(condicion, condicion)}, "
        f"{actuador.tipo_actuador.nombre_actuador} {actuador.identificador_equipo}: {accion.nombre_accion}{texto_del_valor}"
    )


def _regla_igual_activa(sensor_id, condicion, actuador_id, excluir_pk=None):
    """Regla 6 de ALT y regla 5 de MOD: la regla ACTIVA con el mismo sensor, condición y actuador, o ``None``."""
    consulta = ReglaActuacion.objects.filter(sensor_id=sensor_id, condicion=condicion, actuador_id=actuador_id, estado_regla=EstadoRegla.ACTIVA)
    if excluir_pk is not None:
        consulta = consulta.exclude(pk=excluir_pk)
    return consulta.select_related("sensor", "actuador__tipo_actuador", "accion").first()


def _error_repetida(texto):
    """Regla 6 de ALT: «Ya hay una regla activa igual: {texto de la regla}.»."""
    return _error_general(f"Ya hay una regla activa igual: {texto}.", "regla_repetida")


def reiniciar_reglas(reglas):
    """Deja las ``reglas`` (instancias o ids) en «sin evaluar» con el contador de confirmación en 0 («Disparo de una regla»: al crear, modificar, reactivar, activar el sistema,
    volver el nodo de modo local y quedarse el invernadero sin umbral). Devuelve cuántas filas cambió. Corre dentro de la transacción de quien llama."""
    ids = [getattr(regla, "pk", regla) for regla in reglas]
    if not ids:
        return 0
    return ReglaActuacion.objects.filter(pk__in=ids).update(ultima_evaluacion=ReglaActuacion.Evaluacion.SIN_EVALUAR, contador_confirmacion=0)


def sin_umbral_efectivo(invernadero_id):
    """Regla 7 de ALT: el invernadero no tiene lotes activos ni siembras a realizar, así que no tiene umbral efectivo. La pantalla lo advierte; el alta deja continuar."""
    return umbral_efectivo([invernadero_id])[invernadero_id] is None


def _sistema_bloqueado(invernadero_id):
    """El sistema no dado de baja del invernadero, bloqueado, o ``None``."""
    return SistemaIoT.objects.select_for_update(no_key=True).filter(invernadero_id=invernadero_id, estado_sistema__in=ESTADOS_VIGENTES).first()


def _bloquear_para_regla(actor, invernadero_id, tipo_id):
    """Bloquea (tipo, invernadero) y verifica, ya bloqueado, que quien actúa siga activo y opere el invernadero (extensión 8b de IOT-REG-SIS). Devuelve el invernadero."""
    if tipo_id is not None:
        bloquear_tipo_activo(tipo_id)
    invernadero = api_alertas.bloquear_invernadero_para_alertas(invernadero_id)
    _actor_sigue_activo(actor)
    if not puede_operar(actor, invernadero):
        raise _error_de_alcance(actor, invernadero)
    return invernadero


def _guardar(regla, campos):
    """Guarda ``campos``; si dos pedidos dejaron la regla igual a otra activa a la vez, el índice único respalda y el ``IntegrityError`` se traduce al mismo error."""
    try:
        with transaction.atomic():  # punto de guardado: el IntegrityError no rompe la transacción de afuera
            regla.save(update_fields=campos) if regla.pk else regla.save()
    except IntegrityError as error:
        if "regla_actuacion_activa_unica" in str(error):
            raise _error_repetida(_texto(regla.sensor, regla.condicion, regla.actuador, regla.accion, regla.aplicar_valor)) from error
        raise


def _validar_accion_y_valor(actuador, accion, valor, errores):
    """Regla 4: la acción y el valor, con ``comandos.validar_comando`` (los mismos códigos que un comando manual). Suma los errores a ``errores``."""
    if accion is None:
        errores.setdefault("accion", []).append(ValidationError("Seleccioná la acción.", code="obligatorio"))
    else:
        for campo, lista in validar_comando(actuador, accion, valor).items():
            errores.setdefault(campo, []).extend(lista)


def _valor_a_aplicar(accion, valor):
    """El valor de la regla: entero si la acción lleva valor y nulo si no."""
    return _normalizar_valor(valor) if accion.comando.lleva_valor else None


# ---- lo que ofrece el formulario ----


def _invernadero_operado(actor, invernadero_id):
    """El invernadero que ``actor`` opera: ``Http404`` si no lo consulta (D-28) y ``PermissionDenied`` si lo consulta pero no lo opera (el Gerente con Agrónomo activo)."""
    _exigir_operador(actor)
    invernadero = invernaderos_que_consulta(actor).filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if not puede_operar(actor, invernadero):
        raise PermissionDenied("Este invernadero lo operás solo si no tiene un Agrónomo activo.")
    return invernadero


def datos_para_regla(actor, invernadero_id, actuador_id=None):
    """Lo que ofrece el formulario (prototipo ``rglSensors`` y ``r-act``): los sensores activos que admiten reglas (también los de un sector fuera de servicio: el CU no los excluye),
    los actuadores activos y, del actuador elegido, sus acciones activas compatibles con el nodo. Sin sistema IoT, todo vacío. Solo para quien opera el invernadero."""
    invernadero = _invernadero_operado(actor, invernadero_id)
    sistema = SistemaIoT.objects.filter(invernadero=invernadero, estado_sistema__in=ESTADOS_VIGENTES).first()
    if sistema is None:
        return DatosParaRegla([], [], [])
    sensores = list(
        Sensor.objects.filter(sistema=sistema, estado_hardware="activo", tipo_variable_sensor__in=VARIABLES_CON_REGLAS).select_related("sector").order_by("identificador_equipo", "pk")
    )
    actuadores = list(Actuador.objects.filter(sistema=sistema, estado_hardware="activo").select_related("tipo_actuador").order_by("identificador_equipo", "pk"))
    acciones = []
    elegido = next((a for a in actuadores if str(a.pk) == str(actuador_id)), None)
    if elegido is not None:
        marcadas = set(elegido.acciones_incompatibles.values_list("pk", flat=True))
        todas = elegido.tipo_actuador.acciones.filter(estado=Accion.Estado.ACTIVA).select_related("comando").order_by("id")
        acciones = [a for a in todas if a.pk not in marcadas]
    return DatosParaRegla(sensores, actuadores, acciones)


# ---- alta (IOT-ALT-RGL) ----


def alta_regla(actor, invernadero_id, datos, ahora):
    """IOT-ALT-RGL: da de alta una regla de actuación y la devuelve.

    - Precondición a y regla 1: Agrónomo o Gerente activos, con el alcance de IOT-DSC-SIS (``fuera_de_alcance``, vuelto a verificar DESPUÉS de bloquear); un invernadero fuera del
      alcance de consulta, ``Http404`` (D-28). Precondición b: sistema activo o desconectado (``sin_sistema_iot``; regla 9: desconectado se crea igual).
    - Reglas 2 a 5: sensor y actuador del invernadero y activos, variable que admite reglas, condición y, con ``validar_comando``, acción y valor; todos los errores juntos y por campo.
    - Regla 6: ninguna otra regla activa igual (``regla_repetida``; el índice único respalda). La advertencia de la regla 7 la da ``sin_umbral_efectivo``.
    - Postcondición a: activa, «sin evaluar» y contador en 0. Postcondición b y D-36: ``alta_regla_actuacion``. Bloqueos: tipo, invernadero, sistema, sensor, actuador y regla (D-82)."""
    _exigir_operador(actor)
    if not invernaderos_que_consulta(actor).filter(pk=invernadero_id).exists():
        raise Http404("No existe ese invernadero.")
    actuador_id, sensor_id = _entero(datos.actuador_id), _entero(datos.sensor_id)
    tipo_id = Actuador.objects.filter(pk=actuador_id).values_list("tipo_actuador_id", flat=True).first() if actuador_id is not None else None
    with transaction.atomic():
        invernadero = _bloquear_para_regla(actor, invernadero_id, tipo_id)
        sistema = _sistema_bloqueado(invernadero.pk)
        if sistema is None:
            raise _error_general("Este invernadero no tiene un sistema IoT activo o desconectado.", "sin_sistema_iot")
        sensor = Sensor.objects.select_for_update(no_key=True, of=("self",)).select_related("sector").filter(pk=sensor_id).first() if sensor_id is not None else None
        actuador = Actuador.objects.select_for_update(no_key=True, of=("self",)).select_related("tipo_actuador").filter(pk=actuador_id).first() if actuador_id is not None else None
        errores = {}
        if sensor_id is None and not str(datos.sensor_id or "").strip():
            errores["sensor"] = [ValidationError("Seleccioná un sensor.", code="obligatorio")]
        elif sensor is None or sensor.sistema_id != sistema.pk or sensor.estado_hardware != "activo":
            errores["sensor"] = [ValidationError("El sensor tiene que ser un sensor activo de este invernadero.", code="sensor_no_disponible")]
            sensor = None
        elif sensor.tipo_variable_sensor not in VARIABLES_CON_REGLAS:
            errores["sensor"] = [
                ValidationError(
                    "Solo la temperatura, la humedad y la intensidad lumínica admiten reglas: la solución nutritiva se monitorea con alertas.", code="sensor_no_admite_reglas"
                )
            ]
        if actuador_id is None and not str(datos.actuador_id or "").strip():
            errores["actuador"] = [ValidationError("Seleccioná un actuador.", code="obligatorio")]
        elif actuador is None or actuador.sistema_id != sistema.pk or actuador.estado_hardware != "activo":
            errores["actuador"] = [ValidationError("El actuador tiene que ser un actuador activo de este invernadero.", code="actuador_no_disponible")]
            actuador = None
        condicion = str(datos.condicion or "").strip()
        if not condicion:
            errores["condicion"] = [ValidationError("Seleccioná la condición.", code="obligatorio")]
        elif condicion not in Condicion.values:
            errores["condicion"] = [ValidationError("La condición no es válida.", code="condicion_invalida")]
        accion = None
        if actuador is not None:
            accion_id = _entero(datos.accion_id)
            accion = Accion.objects.select_related("comando").filter(pk=accion_id).first() if accion_id is not None else None
            _validar_accion_y_valor(actuador, accion, datos.valor, errores)
        if errores:
            raise ValidationError(errores)
        igual = _regla_igual_activa(sensor.pk, condicion, actuador.pk)
        if igual is not None:
            raise _error_repetida(texto_de_regla(igual))
        regla = ReglaActuacion(
            sensor=sensor, actuador=actuador, accion=accion, condicion=condicion, aplicar_valor=_valor_a_aplicar(accion, datos.valor), estado_regla=EstadoRegla.ACTIVA
        )
        _guardar(regla, None)
        cambios = {"condicion": {"antes": None, "despues": condicion}, "estado_regla": {"antes": None, "despues": EstadoRegla.ACTIVA.value}}
        if regla.aplicar_valor is not None:
            cambios["aplicar_valor"] = {"antes": None, "despues": regla.aplicar_valor}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_REGLA_ACTUACION,
            afectados=[regla],
            detalle={"cambios": cambios, "datos": {"sensor": referencia(sensor), "actuador": referencia(actuador), "accion": referencia(accion)}},
        )
        return regla


# ---- modificar, reactivar y baja (IOT-MOD-RGL, IOT-BAJ-RGL) ----


def _previo(actor, regla_id):
    """Lo que se sabe de la regla antes de bloquear: ``Http404`` si no existe o su invernadero está fuera del alcance de consulta (D-28)."""
    fila = ReglaActuacion.objects.filter(pk=regla_id).values("sensor_id", "actuador_id", "actuador__tipo_actuador_id", "sensor__sistema_id", "sensor__sistema__invernadero_id").first()
    if fila is None or not invernaderos_que_consulta(actor).filter(pk=fila["sensor__sistema__invernadero_id"]).exists():
        raise Http404("No existe esa regla.")
    return fila


def _bloquear_regla(actor, regla_id, previo, con_tipo):
    """Bloquea, en el orden de D-82, el tipo (si ``con_tipo``), el invernadero, el sistema, el sensor, el actuador y la regla, y los lee de nuevo. Con todo bloqueado: quien actúa sigue
    activo y opera el invernadero (regla 1). Devuelve ``(sistema, regla)`` con la regla trayendo su sensor, su actuador y su acción."""
    _bloquear_para_regla(actor, previo["sensor__sistema__invernadero_id"], previo["actuador__tipo_actuador_id"] if con_tipo else None)
    sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=previo["sensor__sistema_id"])
    Sensor.objects.select_for_update(no_key=True).get(pk=previo["sensor_id"])
    Actuador.objects.select_for_update(no_key=True).get(pk=previo["actuador_id"])
    regla = ReglaActuacion.objects.select_for_update(no_key=True).get(pk=regla_id)
    regla = ReglaActuacion.objects.select_related("sensor", "actuador__tipo_actuador", "accion__comando").get(pk=regla.pk)
    return sistema, regla


def _exigir_sistema_vigente(sistema):
    """Precondición b de MOD: el sistema está activo o desconectado."""
    if sistema.estado_sistema == Estado.INACTIVO:
        raise _error_general("El sistema IoT está dado de baja.", "sistema_dado_de_baja")


def modificar_regla(actor, regla_id, datos, ahora):
    """IOT-MOD-RGL: cambia la condición, la acción o el valor de una regla y la devuelve.

    - Precondición a y regla 1: Agrónomo o Gerente activos, dentro de su alcance; id inexistente o fuera del alcance de consulta, ``Http404``. Precondición b: sistema activo o desconectado
      (``sistema_dado_de_baja``). Regla 6: una regla inactiva no se modifica (``regla_inactiva``).
    - Reglas 2 y 3: las del alta (condición, y acción y valor con ``validar_comando``); el sensor y el actuador de ``datos`` se ignoran.
    - Regla 5: no puede quedar igual a otra regla activa (``regla_repetida``). Regla 4: el cambio reinicia la evaluación; los comandos ya emitidos no cambian.
    - D-28: sin cambios no se escribe ni se audita. Postcondición c y D-36: ``modificacion_regla_actuacion`` con el antes y el después. Bloqueos: tipo, invernadero, sistema, sensor, actuador y regla."""
    _exigir_operador(actor)
    previo = _previo(actor, regla_id)
    with transaction.atomic():
        sistema, regla = _bloquear_regla(actor, regla_id, previo, con_tipo=True)
        _exigir_sistema_vigente(sistema)
        if regla.estado_regla != EstadoRegla.ACTIVA:
            raise _error_general("Una regla dada de baja no se modifica: solo se reactiva.", "regla_inactiva")
        errores = {}
        condicion = str(datos.condicion or "").strip()
        if not condicion:
            errores["condicion"] = [ValidationError("Seleccioná la condición.", code="obligatorio")]
        elif condicion not in Condicion.values:
            errores["condicion"] = [ValidationError("La condición no es válida.", code="condicion_invalida")]
        accion_id = _entero(datos.accion_id)
        accion = Accion.objects.select_related("comando").filter(pk=accion_id).first() if accion_id is not None else None
        _validar_accion_y_valor(regla.actuador, accion, datos.valor, errores)
        if errores:
            raise ValidationError(errores)
        igual = _regla_igual_activa(regla.sensor_id, condicion, regla.actuador_id, excluir_pk=regla.pk)
        if igual is not None:
            raise _error_repetida(texto_de_regla(igual))
        valor = _valor_a_aplicar(accion, datos.valor)
        cambios = {}
        if condicion != regla.condicion:
            cambios["condicion"] = {"antes": regla.condicion, "despues": condicion}
        if accion.pk != regla.accion_id:
            cambios["accion"] = {"antes": referencia(regla.accion), "despues": referencia(accion)}
        if valor != regla.aplicar_valor:
            cambios["aplicar_valor"] = {"antes": regla.aplicar_valor, "despues": valor}
        if not cambios:
            return regla  # D-28
        regla.condicion, regla.accion, regla.aplicar_valor = condicion, accion, valor
        regla.ultima_evaluacion, regla.contador_confirmacion = ReglaActuacion.Evaluacion.SIN_EVALUAR, 0  # regla 4
        _guardar(regla, ["condicion", "accion", "aplicar_valor", "ultima_evaluacion", "contador_confirmacion"])
        RegistroAuditoria.objects.registrar(
            usuario=actor, accion=RegistroAuditoria.Accion.MODIFICACION_REGLA_ACTUACION, afectados=[regla], detalle={"cambios": cambios}
        )
        return regla


def reactivar_regla(actor, regla_id, ahora):
    """IOT-MOD-RGL, postcondición b y regla 6: una regla dada de baja vuelve a «activa». Exige el sistema activo o desconectado (``sistema_dado_de_baja``), el sensor y el actuador activos
    (``sensor_no_activo`` y ``actuador_no_activo``), que la acción siga siendo válida (``validar_comando``) y ninguna regla activa igual (``regla_repetida``). Reinicia la evaluación.
    Se audita como ``modificacion_regla_actuacion`` con el cambio de estado y ``datos.reactivada``. Mismos bloqueos que ``modificar_regla``."""
    _exigir_operador(actor)
    previo = _previo(actor, regla_id)
    with transaction.atomic():
        sistema, regla = _bloquear_regla(actor, regla_id, previo, con_tipo=True)
        _exigir_sistema_vigente(sistema)
        if regla.estado_regla != EstadoRegla.INACTIVA:
            raise _error_general("La regla no está dada de baja.", "regla_no_inactiva")
        if regla.sensor.estado_hardware != "activo":
            raise _error_general("El sensor de la regla no está activo: volvé a activarlo o reactivalo desde Hardware antes.", "sensor_no_activo")
        if regla.actuador.estado_hardware != "activo":
            raise _error_general("El actuador de la regla no está activo: volvé a activarlo o reactivalo desde Hardware antes.", "actuador_no_activo")
        errores = {}
        _validar_accion_y_valor(regla.actuador, regla.accion, regla.aplicar_valor, errores)
        if errores:
            raise ValidationError(errores)
        igual = _regla_igual_activa(regla.sensor_id, regla.condicion, regla.actuador_id, excluir_pk=regla.pk)
        if igual is not None:
            raise _error_repetida(texto_de_regla(igual))
        regla.estado_regla = EstadoRegla.ACTIVA
        regla.ultima_evaluacion, regla.contador_confirmacion = ReglaActuacion.Evaluacion.SIN_EVALUAR, 0
        _guardar(regla, ["estado_regla", "ultima_evaluacion", "contador_confirmacion"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_REGLA_ACTUACION,
            afectados=[regla],
            detalle={"cambios": {"estado_regla": {"antes": EstadoRegla.INACTIVA.value, "despues": EstadoRegla.ACTIVA.value}}, "datos": {"reactivada": True}},
        )
        return regla


def baja_regla(actor, regla_id, ahora):
    """IOT-BAJ-RGL: baja lógica de una regla activa (``regla_no_activa`` si no lo está). Los comandos pendientes que generó siguen su curso (regla 2) y se conserva su historial.
    Postcondición b y D-36: ``baja_regla_actuacion`` con el cambio de estado. Bloqueos: invernadero, sistema y regla (no toca el tipo)."""
    _exigir_operador(actor)
    previo = _previo(actor, regla_id)
    with transaction.atomic():
        _bloquear_para_regla(actor, previo["sensor__sistema__invernadero_id"], None)
        SistemaIoT.objects.select_for_update(no_key=True).get(pk=previo["sensor__sistema_id"])
        regla = ReglaActuacion.objects.select_for_update(no_key=True).get(pk=regla_id)
        if regla.estado_regla != EstadoRegla.ACTIVA:
            raise _error_general("La regla ya está dada de baja.", "regla_no_activa")
        regla.estado_regla = EstadoRegla.INACTIVA
        regla.save(update_fields=["estado_regla"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_REGLA_ACTUACION,
            afectados=[regla],
            detalle={"cambios": {"estado_regla": {"antes": EstadoRegla.ACTIVA.value, "despues": EstadoRegla.INACTIVA.value}}},
        )
        return regla


# ---- consulta (IOT-CNS-RGL) ----


def _evaluacion_visible(regla, confirmacion):
    """La evaluación como la muestra el prototipo (``ultB``), con la corrección de D-78 punto 8: una regla ocupada queda «no cumplida» con el contador en la confirmación."""
    if regla.ultima_evaluacion == ReglaActuacion.Evaluacion.CUMPLIDA:
        return "Se cumple"
    if regla.ultima_evaluacion == ReglaActuacion.Evaluacion.NO_CUMPLIDA:
        if regla.contador_confirmacion >= confirmacion:
            return "Confirmada · esperando al actuador"
        if regla.contador_confirmacion > 0:
            return f"Confirmando {regla.contador_confirmacion} de {confirmacion}"
        return "No se cumple"
    return "Sin evaluar"


def _filas_de(invernadero_id, consulta):
    """Las ``FilaDeRegla`` de ``consulta`` (reglas del invernadero) con UN número fijo de consultas, sin consultas por fila: el sistema, el nodo, el umbral efectivo, las acciones
    incompatibles de los actuadores y el último comando de cada regla."""
    reglas = list(consulta.select_related("sensor__sector", "actuador__tipo_actuador", "accion").order_by("id"))
    if not reglas:
        return []
    sistema = SistemaIoT.objects.filter(invernadero_id=invernadero_id, estado_sistema__in=ESTADOS_VIGENTES).first()
    modo_local = sistema is not None and NodoCentral.objects.filter(sistema=sistema, modo=NodoCentral.Modo.LOCAL).exists()
    umbral = umbral_efectivo([invernadero_id])[invernadero_id]
    confirmacion = configuracion.obtener().cant_lecturas_confirmacion
    incompatibles = set(Actuador.acciones_incompatibles.through.objects.filter(actuador_id__in={r.actuador_id for r in reglas}).values_list("actuador_id", "accion_id"))
    ultimos = {
        c.regla_id: c
        for c in Comando.objects.filter(regla__in=reglas).select_related("actuador", "accion").order_by("regla_id", "-emitido_en", "-pk").distinct("regla_id")
    }
    filas = []
    for regla in reglas:
        claves = []
        if sistema is not None and sistema.estado_sistema == Estado.DESCONECTADO:
            claves.append("sistema_desconectado")
        if regla.actuador.estado_hardware == "fuera_de_servicio":
            claves.append("actuador_fuera_de_servicio")
        if (regla.actuador_id, regla.accion_id) in incompatibles:
            claves.append("accion_incompatible")
        if umbral is None or getattr(umbral, VARIABLE_DEL_UMBRAL.get(regla.sensor.tipo_variable_sensor, ""), None) is None:
            claves.append("sin_umbral")
        if modo_local:
            claves.append("modo_local")
        if regla.sensor.sector is not None and regla.sensor.sector.estado_sector == "fuera_de_servicio":
            claves.append("sector_fuera_de_servicio")
        if regla.sensor.estado_hardware == "fuera_de_servicio":
            claves.append("sensor_fuera_de_servicio")
        motivos = [Motivo(clave, MOTIVOS[clave]) for clave in claves] if regla.estado_regla == EstadoRegla.ACTIVA else []
        filas.append(FilaDeRegla(regla, f"RGL-{regla.pk}", texto_de_regla(regla), _evaluacion_visible(regla, confirmacion), ultimos.get(regla.pk), motivos))
    return filas


def buscar_reglas(actor, invernadero_id, filtros=None):
    """IOT-CNS-RGL, reglas 1 a 3: las reglas del invernadero (también las dadas de baja, con el filtro de estado), por id, con su texto, su situación, su último disparo y los motivos por
    los que no emite. ``filtros``: ``FiltrosDeReglas`` (estado, sensor y actuador; un valor desconocido no filtra). Agrónomo o Gerente activos; un invernadero fuera de su alcance de
    consulta, ``Http404`` (D-28). No audita (regla 6, SEG-14)."""
    _exigir_operador(actor)
    if not invernaderos_que_consulta(actor).filter(pk=invernadero_id).exists():
        raise Http404("No existe ese invernadero.")
    filtros = filtros or FiltrosDeReglas()
    consulta = ReglaActuacion.objects.filter(sensor__sistema__invernadero_id=invernadero_id)
    if filtros.estado in EstadoRegla.values:
        consulta = consulta.filter(estado_regla=filtros.estado)
    if str(filtros.sensor_id or "").isdigit():
        consulta = consulta.filter(sensor_id=int(filtros.sensor_id))
    if str(filtros.actuador_id or "").isdigit():
        consulta = consulta.filter(actuador_id=int(filtros.actuador_id))
    return _filas_de(invernadero_id, consulta)


def ficha_de_regla(actor, regla_id):
    """IOT-CNS-RGL, regla 4: la regla con su situación y el historial de los comandos que generó, del más reciente al más viejo. Mismo alcance que ``buscar_reglas``."""
    _exigir_operador(actor)
    invernadero_id = ReglaActuacion.objects.filter(pk=regla_id).values_list("sensor__sistema__invernadero_id", flat=True).first()
    if invernadero_id is None or not invernaderos_que_consulta(actor).filter(pk=invernadero_id).exists():
        raise Http404("No existe esa regla.")
    fila = _filas_de(invernadero_id, ReglaActuacion.objects.filter(pk=regla_id))[0]
    comandos = list(Comando.objects.filter(regla_id=regla_id).select_related("actuador__tipo_actuador", "accion").order_by("-emitido_en", "-pk"))
    return FichaDeRegla(fila, comandos)


def acciones_permitidas(actor, regla, sistema=None):
    """D-30: las acciones que ``actor`` puede hacer sobre ``regla``, un ``frozenset``. Quien opera el IoT del invernadero (regla 1 de IOT-DSC-SIS) con el sistema no dado de baja: modificar y dar
    de baja una regla activa, o reactivar una inactiva; quien solo consulta, ninguna. ``sistema``, si ya se lo tiene, ahorra una consulta. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        return frozenset()
    sistema = SistemaIoT.objects.select_related("invernadero").get(pk=regla.sensor.sistema_id) if sistema is None else sistema
    if sistema.estado_sistema == Estado.INACTIVO or not puede_operar(actor, sistema.invernadero):
        return frozenset()
    if regla.estado_regla == EstadoRegla.ACTIVA:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})
