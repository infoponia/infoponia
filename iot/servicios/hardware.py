# Servicios del hardware (IOT-02): alta (IOT-ALT-HDW), modificación con volver a activar y reactivar (IOT-MOD-HDW) y consulta (IOT-CNS-HDW). Cada caso de
# uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36 (docs/patrones/auditoria.md). Casos de uso:
# docs/casos_de_uso/iot/hardware.md; orden de docs/patrones/abm.md, sección 2.
#
# Orden de bloqueos (siempre ``FOR NO KEY UPDATE``; decisión D-82 que completa D-40): el TIPO de actuador, el invernadero, el sistema y el equipo. El tipo
# va primero porque es de toda la organización (como las cuentas) y ``modificar_tipo_actuador`` lo bloquea y después, al recalcular la compatibilidad, bloquea
# los invernaderos de sus actuadores: si el alta bloqueara invernadero y después tipo, las dos transacciones se cruzarían. El alta de un actuador (y el
# cambio de su tipo) llama a ``bloquear_tipo_activo`` ANTES de insertar: el ``INSERT`` solo toma ``FOR KEY SHARE``, que no frena la baja del tipo
# (contrato de IOT-BAJ-TAC). Las alertas se crean y se resuelven con el invernadero ya bloqueado.
#
# «Se completa en IOT-NN»: ``tiene_lecturas`` (hecha en IOT-03), ``tiene_comandos`` y ``tiene_comando_pendiente`` (hechas en IOT-05), ``tiene_reglas`` (IOT-06) y
# ``mantenimientos_a_realizar`` (IOT-07). Consultan sus tablas, vacías hasta entonces. La baja del equipo (IOT-06) está en «baja».

from collections import defaultdict, namedtuple
from dataclasses import dataclass

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia
from iot.alcance import invernaderos_que_consulta, puede_operar
from iot.models import Actuador, AlertaIot, Comando, EquipoAnunciado, Hardware, MantenimientoTecnico, ReglaActuacion, Sensor, SistemaIoT, Telemetria, TipoActuador
from iot.servicios import compatibilidad
from iot.servicios.sistemas import (
    Estado,
    _error_de_alcance,
    _exigir_operador,
    insumos_de_hardware,
)
from iot.servicios.tipos_actuador import bloquear_tipo_activo
from iot.textos import estado_legible
from iot.validadores import (
    texto,
    validar_calibracion,
    validar_fecha_de_instalacion,
    validar_identificador_equipo,
    validar_texto,
)
from maestros.extensiones import Contenido, Impedimento
from maestros.models import Alerta, SectorProduccion
from maestros.servicios import alertas as api_alertas
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general
from produccion.errores import ErrorDeProduccion
from produccion.servicios import ordenes as ordenes_de_produccion

ACCION_MODIFICAR = "modificar"
ACCION_VOLVER_A_ACTIVAR = "volver_a_activar"
ACCION_REACTIVAR = "reactivar"
ACCION_BAJA = "baja"

LARGO_DEL_MODELO = Hardware._meta.get_field("modelo_hardware").max_length
LARGO_DE_LA_SERIE = Hardware._meta.get_field("numero_serie").max_length
LARGO_DEL_NOMBRE_DEL_SENSOR = Sensor._meta.get_field("nombre_sensor").max_length
LARGO_DE_LA_DESCRIPCION = Actuador._meta.get_field("descripcion_actuador").max_length

EstadoHw = Hardware.Estado
ESTADOS_DE_SECTOR_ADMITIDOS = ("activo", "fuera_de_servicio")  # regla 3 de IOT-ALT-HDW
TIPO_NO_REGISTRADO = "iot_dispositivo_no_registrado"
# Las alertas de falla que se resuelven al volver a activar un equipo (postcondición b de IOT-MOD-HDW).
TIPOS_DE_FALLA = ("iot_dispositivo_en_falla", "iot_comando_fallido")

# Lo que se ofrece al dar de alta (regla 14 de ALT): un identificador anunciado que todavía no está registrado y, si era de un equipo dado de baja, cuál.
Anunciado = namedtuple("Anunciado", "identificador clase era_de")
# La «Situación» de un equipo en la lista (clave estable y texto visible).
Situacion = namedtuple("Situacion", "clave texto")


@dataclass
class DatosDeEquipo:
    """Lo que manda el formulario de un equipo. ``clase`` es ``sensor`` o ``actuador`` (solo cuenta al dar de alta: el tipo de equipo nunca cambia,
    regla 3 de MOD). Los datos de la otra clase se ignoran. La fecha y el insumo solo cuentan al dar de alta. Los valores pueden venir como texto."""

    clase: object = ""
    identificador: object = ""
    modelo: object = ""
    numero_serie: object = ""
    fecha_instalacion: object = None
    insumo_id: object = None
    sector_id: object = None
    variable: object = ""
    nombre_sensor: object = ""
    calibracion_min: object = ""
    calibracion_max: object = ""
    tipo_actuador_id: object = None
    descripcion: object = ""

    @classmethod
    def desde_post(cls, post, clase=""):
        """Arma los datos desde el POST; tolera campos que faltan (los errores los da el servicio)."""
        return cls(
            clase=clase or post.get("clase", ""),
            identificador=post.get("identificador", ""),
            modelo=post.get("modelo", ""),
            numero_serie=post.get("numero_serie", ""),
            fecha_instalacion=post.get("fecha_instalacion") or None,
            insumo_id=post.get("insumo") or None,
            sector_id=post.get("sector") or None,
            variable=post.get("variable", ""),
            nombre_sensor=post.get("nombre_sensor", ""),
            calibracion_min=post.get("calibracion_min", ""),
            calibracion_max=post.get("calibracion_max", ""),
            tipo_actuador_id=post.get("tipo_actuador") or None,
            descripcion=post.get("descripcion", ""),
        )


# ---- las funciones que completan otras tareas ----


def tiene_lecturas(sensor):
    """Regla 3 de IOT-MOD-HDW: el sensor ya tiene lecturas (la variable no se cambia). Con IOT-03 las escribe la API del nodo: consulta la tabla de lecturas."""
    return Telemetria.objects.filter(sensor_id=sensor.pk).exists()


def tiene_comandos(actuador):
    """Regla 3 de IOT-MOD-HDW: el actuador ya tiene comandos, en cualquier estado (el tipo no se cambia). Completa IOT-05: consulta los comandos reales."""
    return Comando.objects.filter(actuador_id=actuador.pk).exists()


def tiene_comando_pendiente(actuador):
    """Precondición c de IOT-MOD-HDW: el actuador tiene un comando pendiente (no se modifica). Completa IOT-05: consulta los comandos reales."""
    return Comando.objects.filter(actuador_id=actuador.pk, estado_comando=Comando.Estado.PENDIENTE).exists()


def tiene_reglas(equipo):
    """Regla 3 de IOT-MOD-HDW: el equipo es el sensor o el actuador de alguna regla de actuación, activa o no (el tipo del actuador no se cambia).
    **Se completa en IOT-06.**"""
    return ReglaActuacion.objects.filter(Q(sensor_id=equipo.pk) | Q(actuador_id=equipo.pk)).exists()


def mantenimientos_a_realizar(equipo):
    """Regla 8 de IOT-MOD-HDW y precondición d de IOT-BAJ-HDW: las órdenes de mantenimiento «a realizar» que incluyen al equipo, por ``id`` (IOT-07). Una sola consulta."""
    return list(MantenimientoTecnico.objects.filter(hardware=equipo, estado_orden="a_realizar").select_related("tecnico", "invernadero").order_by("pk"))


def ya_reporto(equipo):
    """Regla 4 de IOT-MOD-HDW: el equipo ya reportó si el nodo mandó algún mensaje sobre él, o tiene lecturas, un estado informado o comandos."""
    if equipo.ultimo_mensaje_en is not None:
        return True
    if equipo.clase == "sensor":
        return tiene_lecturas(equipo)
    return equipo.estado_informado_en is not None or tiene_comandos(equipo)


# ---- comunes ----


def nombre_del_equipo(equipo):
    """El nombre del equipo del prototipo (``hwName``): la variable del sensor o el tipo del actuador."""
    if equipo.clase == "sensor":
        return equipo.get_tipo_variable_sensor_display()
    return equipo.tipo_actuador.nombre_actuador


def _especifico(equipo):
    """El ``Sensor`` o el ``Actuador`` de una fila de ``Hardware`` (la tabla base no trae los datos de su clase)."""
    if equipo.clase == "sensor":
        return Sensor.objects.get(pk=equipo.pk)
    return Actuador.objects.select_related("tipo_actuador").get(pk=equipo.pk)


def _enteros(valor):
    """``valor`` como entero, o ``None`` si está vacío o no lo es."""
    try:
        return int(texto(valor))
    except ValueError:
        return None


def _validar(datos, clase, alta):
    """Normaliza y valida ``datos`` sin bloquear nada. Junta TODOS los errores en un solo ``ValidationError`` por campo (``identificador``, ``modelo``,
    ``numero_serie``, ``fecha_instalacion``, ``insumo``, ``variable``, ``nombre_sensor``, ``calibracion_min``, ``calibracion_max``, ``tipo_actuador``,
    ``descripcion``). Lo que depende del invernadero (el sector y la unicidad del identificador) se verifica después de bloquear. Devuelve los valores limpios."""
    errores, limpios = {}, {}

    def revisar(campo, funcion, *argumentos, nombre=None):
        try:
            limpios[nombre or campo] = funcion(*argumentos)
        except ValidationError as error:
            errores.setdefault(campo, []).extend(error.error_list)

    def fallar(campo, mensaje, codigo):
        errores.setdefault(campo, []).append(ValidationError(mensaje, code=codigo))

    revisar("identificador", validar_identificador_equipo, datos.identificador)
    revisar("modelo", validar_texto, datos.modelo, LARGO_DEL_MODELO, True, "el modelo")
    revisar("numero_serie", validar_texto, datos.numero_serie, LARGO_DE_LA_SERIE, False, "el número de serie")
    if alta:
        revisar("fecha_instalacion", validar_fecha_de_instalacion, datos.fecha_instalacion)
        if texto(datos.insumo_id) == "":
            fallar("insumo", "Seleccioná el insumo.", "obligatorio")
        else:
            numero = _enteros(datos.insumo_id)
            insumo = insumos_de_hardware().filter(pk=numero).first() if numero is not None else None
            if insumo is None:
                fallar("insumo", "Elegí un insumo activo de «Repuestos de hardware».", "insumo_invalido")
            limpios["insumo"] = insumo
    if clase == "sensor":
        variable = texto(datos.variable)
        if not variable:
            fallar("variable", "Seleccioná la variable que mide.", "obligatorio")
        elif variable not in Sensor.Variable.values:
            fallar("variable", "Elegí una variable de la lista.", "variable_invalida")
        limpios["variable"] = variable
        revisar("nombre_sensor", validar_texto, datos.nombre_sensor, LARGO_DEL_NOMBRE_DEL_SENSOR, False, "el nombre")
        limpios["calibracion"] = (None, None)
        if variable and variable in Sensor.Variable.values and variable != Sensor.Variable.NIVEL_SOLUCION:
            try:
                limpios["calibracion"] = validar_calibracion(datos.calibracion_min, datos.calibracion_max)
            except ValidationError as error:
                for campo, lista in error.error_dict.items():
                    errores.setdefault(campo, []).extend(lista)
    else:
        revisar("descripcion", validar_texto, datos.descripcion, LARGO_DE_LA_DESCRIPCION, False, "la descripción")
        if texto(datos.tipo_actuador_id) == "":
            fallar("tipo_actuador", "Seleccioná el tipo de actuador.", "obligatorio")
        else:
            numero = _enteros(datos.tipo_actuador_id)
            tipo = TipoActuador.objects.filter(pk=numero).first() if numero is not None else None
            if tipo is None:
                fallar("tipo_actuador", "Elegí un tipo de actuador de la lista.", "tipo_invalido")
            elif tipo.estado == TipoActuador.Estado.INACTIVO:
                fallar("tipo_actuador", "El tipo de actuador está dado de baja.", "tipo_inactivo")
            limpios["tipo_id"] = None if tipo is None else tipo.pk
    if errores:
        raise ValidationError(errores)
    return limpios


def _error_de_campo(campo, mensaje, codigo):
    """Un ``ValidationError`` de un solo campo."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _tipo_bloqueado(tipo_id, campo=None):
    """``bloquear_tipo_activo``; si ``campo`` está, un tipo dado de baja se informa como error de ese campo (carrera con IOT-BAJ-TAC)."""
    try:
        return bloquear_tipo_activo(tipo_id)
    except ValidationError as error:
        if campo is None:
            raise
        raise _error_de_campo(campo, "El tipo de actuador está dado de baja.", "tipo_inactivo") from error


def _verificar_sector(invernadero, sector_id):
    """Regla 3 de IOT-ALT-HDW (regla 21 de 8.20): el sector, si se indicó, es un sector activo o fuera de servicio del mismo invernadero. Devuelve el
    sector o ``None`` (equipo general). Lanza un ``ValidationError`` del campo ``sector``."""
    if texto(sector_id) == "":
        return None
    numero = _enteros(sector_id)
    sector = (
        SectorProduccion.objects.filter(pk=numero, invernadero=invernadero, estado_sector__in=ESTADOS_DE_SECTOR_ADMITIDOS).first()
        if numero is not None
        else None
    )
    if sector is None:
        raise _error_de_campo("sector", "Elegí un sector activo o fuera de servicio de este invernadero.", "sector_invalido")
    return sector


def _equipo_con_identificador(sistema, identificador, excluir_pk=None):
    """El equipo NO dado de baja del sistema que usa ``identificador`` (sin distinguir mayúsculas), o ``None``."""
    usan = (
        Hardware.objects.filter(sistema=sistema)
        .exclude(estado_hardware=EstadoHw.INACTIVO)
        .annotate(_minuscula=Lower("identificador_equipo"))
        .filter(_minuscula=identificador.strip().lower())
    )
    if excluir_pk is not None:
        usan = usan.exclude(pk=excluir_pk)
    equipo = usan.first()
    return None if equipo is None else _especifico(equipo)


def _error_identificador_en_uso(otro=None):
    """El error de campo de un identificador repetido (regla 2 de IOT-ALT-HDW)."""
    quien = "otro equipo" if otro is None else nombre_del_equipo(otro)
    return _error_de_campo("identificador", f"Ya lo usa {quien} en este sistema IoT.", "identificador_en_uso")


def _valores_del_equipo(equipo):
    """Los datos de un equipo que se audita (D-36): ``{campo: valor}``, con las referencias de ``referencia()`` y los ``Decimal`` como texto."""
    valores = {
        "identificador_equipo": equipo.identificador_equipo,
        "modelo_hardware": equipo.modelo_hardware,
        "numero_serie": equipo.numero_serie or None,
        "sector": referencia(equipo.sector) if equipo.sector_id else None,
    }
    if equipo.clase == "sensor":
        valores |= {
            "tipo_variable_sensor": equipo.tipo_variable_sensor,
            "nombre_sensor": equipo.nombre_sensor or None,
            "valor_calibracion_min": None if equipo.valor_calibracion_min is None else str(equipo.valor_calibracion_min),
            "valor_calibracion_max": None if equipo.valor_calibracion_max is None else str(equipo.valor_calibracion_max),
        }
    else:
        valores |= {
            "tipo_actuador": referencia(equipo.tipo_actuador),
            "descripcion_actuador": equipo.descripcion_actuador or None,
        }
    return valores


def _resolver_no_registrado(invernadero, identificador):
    """Postcondición d de IOT-ALT-HDW, c de IOT-MOD-HDW: resuelve la alerta activa «dispositivo no registrado» con ese identificador (en minúsculas)."""
    return api_alertas.resolver_alerta_de_estado(invernadero.pk, TIPO_NO_REGISTRADO, f"id:{identificador.lower()}")


def _alertas_de(recalculos):
    """Las alertas creadas o resueltas por ``recalcular_compatibilidad``, para los ``afectados`` de la auditoría."""
    return [a for r in recalculos for a in (r.alerta_creada, r.alerta_resuelta) if a is not None]


def _previo(equipo_id):
    """Lo que se sabe de un sensor o actuador antes de bloquear (el nodo no se opera desde acá): ``Http404`` si no existe."""
    fila = (
        Hardware.objects.filter(pk=equipo_id)
        .exclude(clase="nodo")
        .values("clase", "sistema_id", "sistema__invernadero_id")
        .first()
    )
    if fila is None:
        raise Http404("No existe ese equipo.")
    return fila


def _bloquear_equipo(actor, equipo_id, previo, tipo_id=None, campo_del_tipo=None):
    """Bloquea, en el orden de D-82, el tipo (si se pasa), el invernadero, el sistema y el equipo, y los lee de nuevo. Con ya bloqueado: quien actúa sigue
    activo, el sistema no está dado de baja (precondición b, regla 9) y ``actor`` opera el invernadero (regla 1). Devuelve ``(invernadero, sistema, equipo)``."""
    if tipo_id is not None:
        _tipo_bloqueado(tipo_id, campo_del_tipo)
    invernadero = api_alertas.bloquear_invernadero_para_alertas(previo["sistema__invernadero_id"])
    _actor_sigue_activo(actor)
    sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=previo["sistema_id"])
    modelo = Sensor if previo["clase"] == "sensor" else Actuador
    equipo = modelo.objects.select_for_update(no_key=True).get(pk=equipo_id)
    if sistema.estado_sistema == Estado.INACTIVO:
        raise _error_general("El sistema IoT está dado de baja.", "sistema_dado_de_baja")
    if not puede_operar(actor, invernadero):
        raise _error_de_alcance(actor, invernadero)
    return invernadero, sistema, equipo


# ---- alta (IOT-ALT-HDW) ----


def alta_hardware(actor, sistema_id, datos):
    """IOT-ALT-HDW: registra un sensor o un actuador en el sistema IoT ``sistema_id`` y lo devuelve.

    - Precondición a y regla 1: Agrónomo o Gerente activos, dentro de su alcance (``fuera_de_alcance``). Precondición b: el sistema está activo o
      desconectado (``sistema_dado_de_baja``; regla 11: desconectado también). Un id de sistema que no existe, ``Http404``.
    - Reglas 2 a 9 y 13: errores por campo, todos juntos. Precondición c y regla 2: el identificador es único entre los equipos no dados de baja del sistema
      (``identificador_en_uso``, sin distinguir mayúsculas); dos altas a la vez, el índice único de la base respalda y su ``IntegrityError`` se traduce.
    - Regla 7 (D-40, D-82): al crear un actuador se bloquea el tipo con ``bloquear_tipo_activo`` ANTES de insertarlo.
    - Postcondiciones a, b y c: el equipo queda «activo», con su clase y sus datos. Postcondición d y regla 12: se resuelve la alerta «dispositivo no
      registrado» con ese identificador. Regla 14: un actuador se compara con el último anuncio (``recalcular_compatibilidad``).
    - Postcondición e y D-36: un registro ``alta_hardware`` con el equipo y las alertas generadas o resueltas."""
    _exigir_operador(actor)
    clase = texto(datos.clase)
    if clase not in ("sensor", "actuador"):
        raise _error_de_campo("clase", "Elegí si es un sensor o un actuador.", "clase_invalida")
    limpios = _validar(datos, clase, alta=True)
    previo = SistemaIoT.objects.filter(pk=sistema_id).values("invernadero_id").first()
    if previo is None:
        raise Http404("No existe ese sistema IoT.")
    with transaction.atomic():
        if clase == "actuador":
            tipo = _tipo_bloqueado(limpios["tipo_id"], "tipo_actuador")
        invernadero = api_alertas.bloquear_invernadero_para_alertas(previo["invernadero_id"])
        if not invernadero.activo:
            raise _error_general("El invernadero está inactivo: no se puede crear nada sobre él.", "invernadero_inactivo")
        _actor_sigue_activo(actor)
        sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=sistema_id)
        if sistema.estado_sistema == Estado.INACTIVO:
            raise _error_general("El sistema IoT está dado de baja.", "sistema_dado_de_baja")
        if not puede_operar(actor, invernadero):
            raise _error_de_alcance(actor, invernadero)
        errores = {}
        try:
            sector = _verificar_sector(invernadero, datos.sector_id)
        except ValidationError as error:
            errores |= error.error_dict
            sector = None
        otro = _equipo_con_identificador(sistema, limpios["identificador"])
        if otro is not None:
            errores |= _error_identificador_en_uso(otro).error_dict
        if errores:
            raise ValidationError(errores)

        base = {
            "sistema": sistema,
            "clase": clase,
            "identificador_equipo": limpios["identificador"],
            "modelo_hardware": limpios["modelo"],
            "numero_serie": limpios["numero_serie"],
            "fecha_instalacion": limpios["fecha_instalacion"],
            "insumo": limpios["insumo"],
            "sector": sector,
        }
        try:
            with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
                if clase == "sensor":
                    minimo, maximo = limpios["calibracion"]
                    equipo = Sensor.objects.create(
                        **base,
                        tipo_variable_sensor=limpios["variable"],
                        nombre_sensor=limpios["nombre_sensor"],
                        valor_calibracion_min=minimo,
                        valor_calibracion_max=maximo,
                    )
                else:
                    equipo = Actuador.objects.create(**base, tipo_actuador=tipo, descripcion_actuador=limpios["descripcion"])
        except IntegrityError as error:
            if "hardware_identificador_unico_por_sistema" in str(error):
                raise _error_identificador_en_uso() from error
            raise
        alertas = [_resolver_no_registrado(invernadero, equipo.identificador_equipo)]
        if clase == "actuador":
            alertas += _alertas_de(compatibilidad.recalcular_compatibilidad([equipo]))
            equipo.refresh_from_db()
        cambios = {campo: {"antes": None, "despues": valor} for campo, valor in _valores_del_equipo(equipo).items() if valor is not None}
        cambios["fecha_instalacion"] = {"antes": None, "despues": equipo.fecha_instalacion.isoformat()}
        cambios["insumo"] = {"antes": None, "despues": referencia(equipo.insumo)}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_HARDWARE,
            afectados=[equipo, *[a for a in alertas if a is not None]],
            detalle={"cambios": cambios, "datos": {"clase": clase, "invernadero": referencia(invernadero)}},
        )
    return equipo


# ---- modificar, volver a activar y reactivar (IOT-MOD-HDW) ----


def modificar_hardware(actor, equipo_id, datos):
    """IOT-MOD-HDW: cambia los datos de un sensor o de un actuador y lo devuelve.

    - Precondición a y regla 1: Agrónomo o Gerente activos, dentro de su alcance. Precondición b: el sistema está activo o desconectado. Precondición c y
      regla 5: sin comandos pendientes (``comando_pendiente``). Regla 9: un equipo dado de baja no se modifica (``equipo_dado_de_baja``).
    - Regla 2: se cambian el modelo, el número de serie, el sector, el nombre del sensor, la descripción del actuador y la calibración, con las reglas del
      alta. La fecha, el insumo y la clase de ``datos`` se ignoran (regla 3: el tipo de equipo no cambia).
    - Regla 3: la variable no cambia con lecturas (``variable_con_lecturas``) y el tipo del actuador, con reglas o comandos (``tipo_con_historial``).
      Regla 4: el identificador se corrige solo si el equipo nunca reportó (``identificador_ya_reporto``) y resuelve la alerta «dispositivo no registrado» del
      identificador nuevo. Regla 10 y postcondición d: al cambiar el tipo se recalcula la compatibilidad.
    - D-28: sin cambios no se escribe ni se audita. D-36: un registro ``modificacion_hardware`` con el antes y el después. Bloqueos de D-82."""
    _exigir_operador(actor)
    previo = _previo(equipo_id)
    clase = previo["clase"]
    limpios = _validar(datos, clase, alta=False)
    tipo_nuevo = None
    if clase == "actuador":
        tipo_actual = Actuador.objects.values_list("tipo_actuador_id", flat=True).get(pk=equipo_id)
        tipo_nuevo = limpios["tipo_id"] if limpios["tipo_id"] != tipo_actual else None
    with transaction.atomic():
        invernadero, sistema, equipo = _bloquear_equipo(actor, equipo_id, previo, tipo_nuevo, "tipo_actuador")
        if equipo.estado_hardware == EstadoHw.INACTIVO:
            raise _error_general("Un equipo dado de baja no se modifica: solo se reactiva.", "equipo_dado_de_baja")
        if clase == "actuador" and tiene_comando_pendiente(equipo):
            raise _error_general("El equipo tiene un comando pendiente: esperá su resultado o cancelalo antes de modificarlo.", "comando_pendiente")

        errores = {}
        antes = _valores_del_equipo(equipo)
        identificador_cambia = limpios["identificador"] != equipo.identificador_equipo
        if identificador_cambia:
            if ya_reporto(equipo):
                errores |= _error_de_campo(
                    "identificador", "Ya reportó: identifica su historial y no se puede corregir.", "identificador_ya_reporto"
                ).error_dict
            else:
                otro = _equipo_con_identificador(sistema, limpios["identificador"], excluir_pk=equipo.pk)
                if otro is not None:
                    errores |= _error_identificador_en_uso(otro).error_dict
        if clase == "sensor" and limpios["variable"] != equipo.tipo_variable_sensor and tiene_lecturas(equipo):
            errores |= _error_de_campo(
                "variable", "No se puede cambiar: el sensor ya tiene lecturas.", "variable_con_lecturas"
            ).error_dict
        if tipo_nuevo is not None and (tiene_reglas(equipo) or tiene_comandos(equipo)):
            errores |= _error_de_campo(
                "tipo_actuador",
                "No se puede cambiar: ya tiene comandos o reglas de actuación. Para otro tipo, se da de baja y se registra uno nuevo.",
                "tipo_con_historial",
            ).error_dict
        sector = equipo.sector
        if texto(datos.sector_id) == "":
            sector = None
        elif _enteros(datos.sector_id) != equipo.sector_id:  # el sector que ya tenía no se vuelve a verificar
            try:
                sector = _verificar_sector(invernadero, datos.sector_id)
            except ValidationError as error:
                errores |= error.error_dict
        if errores:
            raise ValidationError(errores)

        equipo.identificador_equipo = limpios["identificador"]
        equipo.modelo_hardware = limpios["modelo"]
        equipo.numero_serie = limpios["numero_serie"]
        equipo.sector = sector
        campos = ["identificador_equipo", "modelo_hardware", "numero_serie", "sector"]
        if clase == "sensor":
            minimo, maximo = limpios["calibracion"]
            equipo.tipo_variable_sensor, equipo.nombre_sensor = limpios["variable"], limpios["nombre_sensor"]
            equipo.valor_calibracion_min, equipo.valor_calibracion_max = minimo, maximo
            campos += ["tipo_variable_sensor", "nombre_sensor", "valor_calibracion_min", "valor_calibracion_max"]
        else:
            equipo.descripcion_actuador = limpios["descripcion"]
            campos.append("descripcion_actuador")
            if tipo_nuevo is not None:
                equipo.tipo_actuador = TipoActuador.objects.get(pk=tipo_nuevo)
                campos.append("tipo_actuador")
        despues = _valores_del_equipo(equipo)
        cambios = {campo: {"antes": antes[campo], "despues": despues[campo]} for campo in despues if antes[campo] != despues[campo]}
        if not cambios:
            return equipo  # D-28
        try:
            with transaction.atomic():
                equipo.save(update_fields=campos)
        except IntegrityError as error:
            if "hardware_identificador_unico_por_sistema" in str(error):
                raise _error_identificador_en_uso() from error
            raise
        alertas = []
        if identificador_cambia:
            alertas.append(_resolver_no_registrado(invernadero, equipo.identificador_equipo))
        if clase == "actuador" and (tipo_nuevo is not None or identificador_cambia):
            alertas += _alertas_de(compatibilidad.recalcular_compatibilidad([equipo]))
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_HARDWARE,
            afectados=[equipo, *[a for a in alertas if a is not None]],
            detalle={"cambios": cambios},
        )
    return equipo


def _mensaje_de_reactivar_con_reemplazo(equipo, otro):
    """Regla 9 de IOT-MOD-HDW: «No se puede reactivar: el identificador X ya lo usa {equipo} (registrado como reemplazo).»"""
    return f"No se puede reactivar: el identificador {equipo.identificador_equipo} ya lo usa {nombre_del_equipo(otro)} (registrado como reemplazo)."


def impedimento_de_reactivacion(equipo):
    """Lo que impide reactivar ``equipo`` (dado de baja) ahora, como texto, o ``None``: su sistema dado de baja, un reemplazo con su identificador (regla 9 de
    IOT-MOD-HDW) o, un actuador, su tipo dado de baja. Solo lectura, para la ventana que lo informa; ``reactivar_hardware`` lo vuelve a verificar bloqueado."""
    if equipo.sistema.estado_sistema == Estado.INACTIVO:
        return "El sistema IoT está dado de baja: un equipo suyo no se reactiva."
    otro = _equipo_con_identificador(equipo.sistema, equipo.identificador_equipo, excluir_pk=equipo.pk)
    if otro is not None:
        return _mensaje_de_reactivar_con_reemplazo(equipo, otro)
    if equipo.clase == "actuador" and equipo.tipo_actuador.estado == TipoActuador.Estado.INACTIVO:
        return f"El tipo «{equipo.tipo_actuador.nombre_actuador}» está dado de baja: el Gerente tiene que reactivarlo antes."
    return None


def tipos_de_actuador_activos():
    """Los tipos de actuador que se ofrecen al registrar o cambiar un actuador (regla 7 de IOT-ALT-HDW), por nombre."""
    return TipoActuador.objects.filter(estado=TipoActuador.Estado.ACTIVO).order_by(Lower("nombre_actuador"), "pk")


def sectores_del_invernadero(invernadero):
    """Los sectores que se ofrecen para un equipo (regla 3 de IOT-ALT-HDW): los activos o fuera de servicio del invernadero, por nombre."""
    return SectorProduccion.objects.filter(invernadero=invernadero, estado_sector__in=ESTADOS_DE_SECTOR_ADMITIDOS).order_by(Lower("nombre_sector"), "pk")


def campos_bloqueados(equipo):
    """Qué no se puede cambiar de ``equipo`` (regla 3 y 4 de IOT-MOD-HDW), para que la pantalla muestre el dato deshabilitado con su motivo: ``variable``
    (el sensor tiene lecturas), ``tipo_actuador`` (el actuador tiene reglas o comandos) e ``identificador`` (el equipo ya reportó)."""
    sensor = equipo.clase == "sensor"
    return {
        "variable": sensor and tiene_lecturas(equipo),
        "tipo_actuador": not sensor and (tiene_reglas(equipo) or tiene_comandos(equipo)),
        "identificador": ya_reporto(equipo),
    }


def _auditar_cambio_de_estado(actor, equipo, desde, alertas, afectados_extra=(), datos_extra=None):
    """El registro ``reactivacion_hardware`` (volver a activar o reactivar): el cambio de estado, de dónde viene y las alertas resueltas o generadas. IOT-07 suma las órdenes de
    mantenimiento canceladas como afectados (``afectados_extra``) y ``ordenes_canceladas`` y ``ordenes_mantenidas`` en ``datos`` (``datos_extra``)."""
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.REACTIVACION_HARDWARE,
        afectados=[equipo, *[a for a in alertas if a is not None], *afectados_extra],
        detalle={"cambios": {"estado": {"antes": desde, "despues": EstadoHw.ACTIVO.value}}, "datos": {"desde": desde, **(datos_extra or {})}},
    )


# Lo que la ventana de volver a activar muestra de cada orden (D-79, punto 8): ``otros_fuera_de_servicio`` son los DEMÁS equipos de la orden que siguen «fuera de servicio»; si hay alguno, no se ofrece cancelarla.
OrdenAlVolver = namedtuple("OrdenAlVolver", "orden cancelable otros_fuera_de_servicio")
CANCELAR, MANTENER = "cancelar", "mantener"
ELEGI_QUE_HACER = "Elegí qué hacer con cada orden de mantenimiento."
ORDENES_CAMBIARON = "Las órdenes del equipo cambiaron mientras confirmabas: revisalas de nuevo."


def ordenes_al_volver_a_activar(equipo):
    """Regla 8 de IOT-MOD-HDW (IOT-07): las órdenes de mantenimiento «a realizar» del equipo, por ``id``, cada una con si se puede cancelar y qué otros equipos suyos siguen fuera de servicio.
    Dos consultas para toda la lista, con el Técnico y el invernadero de cada orden cargados."""
    ordenes = mantenimientos_a_realizar(equipo)
    if not ordenes:
        return []
    otros = defaultdict(list)
    enlaces = (
        MantenimientoTecnico.hardware.through.objects.filter(mantenimientotecnico_id__in=[o.pk for o in ordenes], hardware__estado_hardware=EstadoHw.FUERA_DE_SERVICIO)
        .exclude(hardware_id=equipo.pk)
        .select_related("hardware")
        .order_by("hardware_id")
    )
    for enlace in enlaces:
        otros[enlace.mantenimientotecnico_id].append(enlace.hardware)
    return [OrdenAlVolver(orden, not otros[orden.pk], otros[orden.pk]) for orden in ordenes]


def _decisiones_validas(decisiones):
    """``{orden_id: "cancelar" | "mantener"}`` con las claves como entero (vienen de un formulario). Un valor que no es ninguno de los dos, o una clave que no es un número, es «Elegí qué hacer…»."""
    limpias = {}
    for clave, decision in (decisiones or {}).items():
        try:
            limpias[int(clave)] = decision
        except (TypeError, ValueError):
            raise _error_general(ELEGI_QUE_HACER, "decisiones_incompletas") from None
        if decision not in (CANCELAR, MANTENER):
            raise _error_general(ELEGI_QUE_HACER, "decisiones_incompletas")
    return limpias


def volver_a_activar(actor, equipo_id, decisiones=None):
    """IOT-MOD-HDW, postcondición b y reglas 7 y 8: un equipo «fuera de servicio» vuelve a «activo» a mano y sus alertas activas de falla («dispositivo en falla» y «comando fallido») pasan a «resuelta».
    Se rechaza si el equipo no está fuera de servicio (``equipo_no_fuera_de_servicio``) o tiene un comando pendiente.

    Regla 8 (IOT-07; D-73 punto 2, D-79 punto 8): si el equipo está en órdenes de mantenimiento «a realizar», ``decisiones`` dice qué hacer con cada una, ``{orden_id: "cancelar" | "mantener"}``.
    - Con órdenes y sin decisión para alguna (o con un valor inválido): ``decisiones_incompletas``. Pedir cancelar una que incluye otros equipos fuera de servicio: ``orden_no_cancelable``.
    - Después de bloquear, si una orden decidida ya no está «a realizar» o no es de este equipo: ``ordenes_cambiaron``.
    - Cada orden a cancelar: ``cancelar_orden_incluida`` con el motivo «Se volvió a activar el equipo {identificador}.» y aviso al Técnico (solo con la cuenta activa). Una mantenida no cambia.
    Bloqueos (D-78, punto 11; sin tipo, D-82 no aplica): las cuentas del actor y de los Técnicos de las órdenes a cancelar (una consulta) → invernadero → sistemas → el equipo y los demás equipos de esas
    órdenes (en orden de ``id``) → las órdenes (``cancelar_orden_incluida``).
    Se audita como ``reactivacion_hardware`` con ``datos.desde = fuera_de_servicio`` y, si había órdenes, ``ordenes_canceladas`` y ``ordenes_mantenidas`` (códigos)."""
    _exigir_operador(actor)
    previo = _previo(equipo_id)
    decisiones = _decisiones_validas(decisiones)
    previas = list(MantenimientoTecnico.objects.filter(hardware=equipo_id, estado_orden="a_realizar").values("pk", "tecnico_id"))
    if {fila["pk"] for fila in previas} - set(decisiones):
        raise _error_general(ELEGI_QUE_HACER, "decisiones_incompletas")
    a_cancelar = [fila for fila in previas if decisiones.get(fila["pk"]) == CANCELAR]
    otros_ids = set(MantenimientoTecnico.hardware.through.objects.filter(mantenimientotecnico_id__in=[f["pk"] for f in a_cancelar]).values_list("hardware_id", flat=True))
    equipos_ids = sorted(otros_ids | {int(equipo_id)})
    tecnicos = {fila["tecnico_id"] for fila in a_cancelar}
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, *tecnicos}).order_by("pk"))
        invernadero = api_alertas.bloquear_invernadero_para_alertas(previo["sistema__invernadero_id"])
        _actor_sigue_activo(actor)
        sistema_ids = sorted({previo["sistema_id"], *Hardware.objects.filter(pk__in=equipos_ids).values_list("sistema_id", flat=True)})
        sistemas = {s.pk: s for s in SistemaIoT.objects.select_for_update(no_key=True).filter(pk__in=sistema_ids).order_by("pk")}
        list(Hardware.objects.select_for_update(no_key=True).filter(pk__in=equipos_ids).order_by("pk"))
        if sistemas[previo["sistema_id"]].estado_sistema == Estado.INACTIVO:
            raise _error_general("El sistema IoT está dado de baja.", "sistema_dado_de_baja")
        if not puede_operar(actor, invernadero):
            raise _error_de_alcance(actor, invernadero)
        equipo = (Sensor if previo["clase"] == "sensor" else Actuador).objects.get(pk=equipo_id)
        if equipo.estado_hardware != EstadoHw.FUERA_DE_SERVICIO:
            raise _error_general("El equipo no está fuera de servicio.", "equipo_no_fuera_de_servicio")
        if previo["clase"] == "actuador" and tiene_comando_pendiente(equipo):
            raise _error_general("El equipo tiene un comando pendiente: esperá su resultado o cancelalo antes de volver a activarlo.", "comando_pendiente")
        filas = ordenes_al_volver_a_activar(equipo)
        ahora_ids = {fila.orden.pk for fila in filas}
        if ahora_ids - set(decisiones):
            raise _error_general(ELEGI_QUE_HACER, "decisiones_incompletas")
        if set(decisiones) - ahora_ids:
            raise _error_general(ORDENES_CAMBIARON, "ordenes_cambiaron")
        for fila in filas:
            if decisiones[fila.orden.pk] == CANCELAR:
                if not fila.cancelable:
                    raise _error_general(f"La orden {fila.orden.codigo} incluye otros equipos fuera de servicio: no se puede cancelar.", "orden_no_cancelable")
                if fila.orden.tecnico_id not in tecnicos:  # un traspaso la cambió de Técnico mientras tanto: su cuenta no quedó bloqueada
                    raise _error_general(ORDENES_CAMBIARON, "ordenes_cambiaron")
        equipo.estado_hardware = EstadoHw.ACTIVO
        equipo.save(update_fields=["estado_hardware"])
        alertas = [api_alertas.resolver_alerta_de_estado(invernadero.pk, tipo, f"hw:{equipo.pk}") for tipo in TIPOS_DE_FALLA]
        canceladas, mantenidas, afectados = [], [], []
        motivo = f"Se volvió a activar el equipo {equipo.identificador_equipo}."
        for fila in filas:
            if decisiones[fila.orden.pk] != CANCELAR:
                mantenidas.append(fila.orden.codigo)
                continue
            try:
                resultado = ordenes_de_produccion.cancelar_orden_incluida(actor, fila.orden, motivo, avisar=False)
            except ErrorDeProduccion as error:  # otra operación la canceló entre la lectura y su bloqueo
                if error.codigo == "orden_no_pendiente":
                    raise _error_general(ORDENES_CAMBIARON, "ordenes_cambiaron") from error
                raise
            canceladas.append(fila.orden.codigo)
            afectados += [fila.orden, *resultado.reservas, *resultado.alertas_resueltas]
            if fila.orden.tecnico.is_active:  # extensión 9a: sin Técnico activo no se avisa
                titulo, detalle = ordenes_de_produccion.texto_de_cancelacion(fila.orden, motivo, actor)
                notificaciones.notificar_a_varios([fila.orden.tecnico], titulo, detalle, excluir=actor)
        datos = {"ordenes_canceladas": canceladas, "ordenes_mantenidas": mantenidas} if filas else None
        _auditar_cambio_de_estado(actor, equipo, EstadoHw.FUERA_DE_SERVICIO.value, alertas, afectados, datos)
    return equipo


def reactivar_hardware(actor, equipo_id):
    """IOT-MOD-HDW, postcondición c y reglas 9 y 10: un equipo dado de baja vuelve a «activo» con su historial y ``fecha_baja`` nula. No se reactiva si
    su sistema está dado de baja (``sistema_dado_de_baja``) ni si otro equipo no dado de baja del sistema usa su identificador (``identificador_en_uso``,
    «registrado como reemplazo»), ni, un actuador, si su tipo está dado de baja (``tipo_inactivo``: lo completa el plan de IOT-02, regla 9 en L7). Resuelve
    la alerta «dispositivo no registrado» y, en un actuador, recalcula la compatibilidad. Se audita como ``reactivacion_hardware`` con ``datos.desde = inactivo``."""
    _exigir_operador(actor)
    previo = _previo(equipo_id)
    tipo_id = None
    if previo["clase"] == "actuador":
        tipo_id = Actuador.objects.values_list("tipo_actuador_id", flat=True).get(pk=equipo_id)
    with transaction.atomic():
        invernadero, sistema, equipo = _bloquear_equipo(actor, equipo_id, previo, tipo_id)
        if equipo.estado_hardware != EstadoHw.INACTIVO:
            raise _error_general("El equipo no está dado de baja.", "equipo_no_inactivo")
        otro = _equipo_con_identificador(sistema, equipo.identificador_equipo, excluir_pk=equipo.pk)
        if otro is not None:
            raise _error_general(_mensaje_de_reactivar_con_reemplazo(equipo, otro), "identificador_en_uso")
        equipo.estado_hardware, equipo.fecha_baja = EstadoHw.ACTIVO, None
        try:
            with transaction.atomic():
                equipo.save(update_fields=["estado_hardware", "fecha_baja"])
        except IntegrityError as error:
            if "hardware_identificador_unico_por_sistema" in str(error):
                raise _error_general("No se puede reactivar: el identificador ya lo usa otro equipo.", "identificador_en_uso") from error
            raise
        alertas = [_resolver_no_registrado(invernadero, equipo.identificador_equipo)]
        if previo["clase"] == "actuador":
            alertas += _alertas_de(compatibilidad.recalcular_compatibilidad([equipo]))
        _auditar_cambio_de_estado(actor, equipo, EstadoHw.INACTIVO.value, alertas)
    return equipo


# ---- baja (IOT-BAJ-HDW; IOT-06) ----
# Bloqueos (D-82 y D-78, punto 11): invernadero → sistema → equipo. No toma el tipo del actuador: la baja no crea nada que impida bajar un tipo.

DatosDeBajaDelEquipo = namedtuple("DatosDeBajaDelEquipo", "equipo impedimentos advertencia")


def _impedimentos_de_baja(equipo):
    """Las precondiciones c a e de IOT-BAJ-HDW como ``Impedimento`` con cómo resolverlas (regla 2): un comando pendiente (solo un actuador), una orden de mantenimiento a realizar
    (IOT-07) y una regla de actuación activa que usa el equipo (como sensor o como actuador)."""
    impedimentos = []
    if equipo.clase == "actuador":
        pendientes = Comando.objects.filter(actuador_id=equipo.pk, estado_comando=Comando.Estado.PENDIENTE).order_by("pk")
        for comando in pendientes:
            impedimentos.append(Impedimento("comandos_pendientes", f"Tiene el comando pendiente CMD-{comando.pk}.", "Esperá su resultado o cancelalo desde Comandos."))
    for orden in mantenimientos_a_realizar(equipo):  # IOT-07: un impedimento por orden; no se concreta en esta ronda, se cancela (D-61)
        impedimentos.append(
            Impedimento(
                "ordenes_de_mantenimiento",
                f"Está en la orden de mantenimiento {orden.codigo}, a realizar:",
                "cancelala desde «Órdenes de mantenimiento», en la ficha del equipo.",
            )
        )
    usan = ReglaActuacion.objects.filter(Q(sensor_id=equipo.pk) | Q(actuador_id=equipo.pk), estado_regla=ReglaActuacion.Estado.ACTIVA).order_by("pk")
    codigos = ", ".join(f"RGL-{regla.pk}" for regla in usan)
    if codigos:
        impedimentos.append(Impedimento("reglas_activas", f"Lo usan las reglas de actuación activas {codigos}.", "Dalas de baja primero desde Reglas de actuación."))
    return impedimentos


def _advertencia_de_baja(equipo):
    """Regla 7: de un actuador, su último estado informado por el nodo (o «desconocido») y que, después de la baja, InfoPonia no podrá enviarle comandos. No impide la baja."""
    if equipo.clase != "actuador":
        return None
    if equipo.estado_informado:
        desde = f" desde las {timezone.localtime(equipo.estado_informado_en):%H:%M}" if equipo.estado_informado_en else ""
        ultimo = f"{estado_legible(equipo.estado_informado).lower()}{desde}"
    else:
        ultimo = "desconocido"
    return (
        f"Último estado informado por el nodo: {ultimo}. Después de la baja, InfoPonia no podrá enviarle comandos: si tiene que quedar apagado o cerrado, "
        "llevalo a ese estado antes, con Emitir comando, o en el invernadero."
    )


def datos_de_baja_del_equipo(actor, equipo_id):
    """IOT-BAJ-HDW, reglas 2 y 7: lo que muestra la ventana de la baja de un equipo: los impedimentos de las precondiciones c a e y, de un actuador, la advertencia de su último
    estado. No escribe ni audita. Solo para quien opera el invernadero (``PermissionDenied`` si solo lo consulta); un equipo fuera del alcance de consulta o el nodo, ``Http404``;
    uno dado de baja, ``equipo_dado_de_baja``."""
    _exigir_operador(actor)
    previo = _previo(equipo_id)
    if not invernaderos_que_consulta(actor).filter(pk=previo["sistema__invernadero_id"]).exists():
        raise Http404("No existe ese equipo.")
    equipo = _especifico(Hardware.objects.select_related("sistema__invernadero").get(pk=equipo_id))
    if not puede_operar(actor, equipo.sistema.invernadero):
        raise PermissionDenied("Este invernadero lo operás solo si no tiene un Agrónomo activo.")
    if equipo.estado_hardware == EstadoHw.INACTIVO:
        raise _error_general("El equipo ya está dado de baja.", "equipo_dado_de_baja")
    return DatosDeBajaDelEquipo(equipo, _impedimentos_de_baja(equipo), _advertencia_de_baja(equipo))


def baja_hardware(actor, equipo_id, ahora):
    """IOT-BAJ-HDW: baja lógica de un sensor o un actuador, y lo devuelve.

    - Precondición a y regla 1: Agrónomo o Gerente activos, con el alcance de IOT-DSC-SIS (``fuera_de_alcance``, vuelto a verificar DESPUÉS de bloquear); un equipo inexistente, el nodo
      (regla 3: se da de baja con IOT-BAJ-SIS) o uno fuera del alcance de consulta, ``Http404`` (D-28). Precondición b: activo o fuera de servicio (``equipo_dado_de_baja``).
    - Precondiciones c a e y regla 2, vueltas a verificar DESPUÉS de bloquear: sin comando pendiente (``comandos_pendientes``), sin orden de mantenimiento a realizar
      (``ordenes_de_mantenimiento``) y sin regla activa que lo use (``reglas_activas``); los impedimentos llegan juntos con cómo resolverlos.
    - Postcondición a: «inactivo» con ``fecha_baja`` = hoy; el historial se conserva. Postcondición b: las alertas activas originadas en el equipo (las de su vínculo
      ``AlertaIot``: claves ``hw:<id>`` y ``sensor:<id>``) pasan a «resuelta». Postcondición c y D-36: UN registro ``baja_hardware``.
    - Bloqueos: invernadero, sistema y equipo."""
    _exigir_operador(actor)
    previo = _previo(equipo_id)
    if not invernaderos_que_consulta(actor).filter(pk=previo["sistema__invernadero_id"]).exists():
        raise Http404("No existe ese equipo.")
    with transaction.atomic():
        invernadero, _, equipo = _bloquear_equipo(actor, equipo_id, previo)
        if equipo.estado_hardware == EstadoHw.INACTIVO:
            raise _error_general("El equipo ya está dado de baja.", "equipo_dado_de_baja")
        impedimentos = _impedimentos_de_baja(equipo)
        if impedimentos:
            raise ValidationError({NON_FIELD_ERRORS: [ValidationError(f"{i.texto} {i.como_resolver}", code=i.codigo) for i in impedimentos]})
        antes = equipo.estado_hardware
        equipo.estado_hardware, equipo.fecha_baja = EstadoHw.INACTIVO, timezone.localtime(ahora).date()
        equipo.save(update_fields=["estado_hardware", "fecha_baja"])
        vinculos = (
            AlertaIot.objects.filter(Q(hardware_id=equipo.pk) | Q(telemetria__sensor_id=equipo.pk), alerta__estado_alerta=Alerta.Estado.ACTIVA)
            .select_related("alerta")
            .order_by("alerta_id")
        )
        resueltas = [api_alertas.resolver_alerta_de_estado(invernadero.pk, v.alerta.tipo_alerta, v.alerta.clave_estado) for v in vinculos]
        alertas = [alerta for alerta in resueltas if alerta is not None]
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_HARDWARE,
            afectados=[equipo, *alertas],
            detalle={"cambios": {"estado_hardware": {"antes": antes, "despues": EstadoHw.INACTIVO.value}}, "datos": {"alertas_resueltas": [referencia(a) for a in alertas]}},
        )
        return equipo


# ---- consulta (IOT-CNS-HDW) ----


def _exigir_consulta_del_sistema(actor, sistema):
    """Regla 1 de IOT-CNS-HDW: Agrónomo o Gerente activos y un sistema de un invernadero de su alcance de consulta; si no, 403 o ``Http404`` (D-28)."""
    _exigir_operador(actor)
    if not invernaderos_que_consulta(actor).filter(pk=sistema.invernadero_id).exists():
        raise Http404("No existe ese sistema IoT.")


def buscar_equipos(actor, sistema, filtros):
    """IOT-CNS-HDW, reglas 3 y 5: los sensores y después los actuadores del sistema (el nodo no), por identificador, también los dados de baja. ``filtros``
    es un ``dict`` con ``tipo`` (``sensor`` o ``actuador``), ``estado``, ``sector`` (el id, o ``_`` para «General») y ``q`` (busca, sin distinguir
    mayúsculas, en el identificador, el número de serie, el nombre del sensor, la variable y el tipo del actuador); un valor vacío o «todos» no filtra.
    Los actuadores traen ``comando_pendiente`` ya calculado: dos consultas para toda la lista. No audita (regla 8, SEG-14)."""
    _exigir_consulta_del_sistema(actor, sistema)
    tipo = texto(filtros.get("tipo"))
    estado = texto(filtros.get("estado"))
    sector = texto(filtros.get("sector"))
    q = texto(filtros.get("q")).lower()

    def filtrar(consulta):
        if estado in EstadoHw.values:
            consulta = consulta.filter(estado_hardware=estado)
        if sector == "_":
            consulta = consulta.filter(sector__isnull=True)
        elif sector.isdigit():
            consulta = consulta.filter(sector_id=int(sector))
        return consulta

    sensores, actuadores = [], []
    if tipo != "actuador":
        busqueda = Q(identificador_equipo__icontains=q) | Q(numero_serie__icontains=q) | Q(nombre_sensor__icontains=q)
        variables = [valor for valor, etiqueta in Sensor.Variable.choices if q and q in etiqueta.lower()]
        if variables:
            busqueda |= Q(tipo_variable_sensor__in=variables)
        consulta = filtrar(Sensor.objects.filter(sistema=sistema).select_related("sector"))
        sensores = list((consulta.filter(busqueda) if q else consulta).order_by(Lower("identificador_equipo"), "pk"))
    if tipo != "sensor":
        busqueda = Q(identificador_equipo__icontains=q) | Q(numero_serie__icontains=q) | Q(tipo_actuador__nombre_actuador__icontains=q)
        pendiente = Comando.objects.filter(actuador=OuterRef("pk"), estado_comando=Comando.Estado.PENDIENTE)
        consulta = filtrar(
            Actuador.objects.filter(sistema=sistema).select_related("sector", "tipo_actuador").annotate(comando_pendiente=Exists(pendiente))
        )
        actuadores = list((consulta.filter(busqueda) if q else consulta).order_by(Lower("identificador_equipo"), "pk"))
    return sensores + actuadores


def ficha_del_equipo(actor, equipo_id):
    """IOT-CNS-HDW, regla 6: el sensor o el actuador con lo que necesita su ficha. Fuera del alcance de consulta o inexistente, ``Http404`` (D-28);
    otros roles, ``PermissionDenied``. No audita (regla 8)."""
    _exigir_operador(actor)
    fila = Hardware.objects.filter(pk=equipo_id).exclude(clase="nodo").values("clase", "sistema__invernadero_id").first()
    if fila is None or not invernaderos_que_consulta(actor).filter(pk=fila["sistema__invernadero_id"]).exists():
        raise Http404("No existe ese equipo.")
    if fila["clase"] == "sensor":
        return Sensor.objects.select_related("sistema__invernadero", "sector", "insumo").get(pk=equipo_id)
    return Actuador.objects.select_related("sistema__invernadero", "sector", "insumo", "tipo_actuador").get(pk=equipo_id)


# La situación por las alertas activas de un sensor o de un actuador, en orden de prioridad (IOT-ENT-INF, «Lo que completa en Hardware»): (tipo de alerta, clave, texto).
SITUACIONES_POR_ALERTA = (
    ("iot_nivel_solucion_bajo", "nivel_bajo", "Nivel bajo"),
    ("iot_lectura_invalida", "lectura_invalida", "Lectura inválida"),
    ("iot_fuera_de_umbral", "fuera_de_umbral", "Fuera de umbral"),
    ("iot_solucion_fuera_de_rango", "fuera_de_rango", "Fuera de rango"),
    ("iot_dispositivo_sin_actividad", "sin_actividad", "Sin actividad"),
)
# Lo que muestra la lista de cada equipo: la última lectura (``Telemetria`` o ``None``) y los códigos de sus alertas activas.
ResumenDeEquipo = namedtuple("ResumenDeEquipo", "ultima_lectura alertas")


def _consulta_de_alertas_activas(ids):
    """Los vínculos de alertas activas de los equipos ``ids``: las de origen en el equipo (R052) y las de origen en una de sus lecturas (R053)."""
    return AlertaIot.objects.filter(
        Q(hardware_id__in=ids) | Q(telemetria__sensor_id__in=ids), alerta__estado_alerta=Alerta.Estado.ACTIVA
    )


def resumen_de_equipos(equipos):
    """``{equipo.pk: ResumenDeEquipo}`` de todos los ``equipos`` con DOS consultas, sin consultas por fila: la última lectura de cada sensor (``DISTINCT ON``) y
    los códigos de sus alertas activas (las de origen en el equipo o en una de sus lecturas)."""
    ids = [equipo.pk for equipo in equipos]
    resumen = {i: ResumenDeEquipo(None, set()) for i in ids}
    if not ids:
        return resumen
    ultimas = Telemetria.objects.filter(sensor_id__in=ids).order_by("sensor_id", "-medida_en", "-id").distinct("sensor_id")
    for lectura in ultimas:
        resumen[lectura.sensor_id] = ResumenDeEquipo(lectura, resumen[lectura.sensor_id].alertas)
    for hardware_id, sensor_id, tipo in _consulta_de_alertas_activas(ids).values_list("hardware_id", "telemetria__sensor_id", "alerta__tipo_alerta"):
        resumen[hardware_id if hardware_id is not None else sensor_id].alertas.add(tipo)
    return resumen


def situacion_de(equipo, alertas=None):
    """La «Situación» de un equipo (regla 4 de IOT-CNS-HDW y «Cómo se aplica»): dado de baja, fuera de servicio, comando pendiente (actuador), sin confirmar
    (``ultimo_mensaje_en`` nulo), configuración incompatible (actuador) y después, por sus alertas activas (IOT-03): «Nivel bajo», «Lectura inválida», «Fuera de
    umbral», «Fuera de rango» y «Sin actividad»; si nada de eso, operativo. ``alertas`` son los códigos de sus alertas activas (de ``resumen_de_equipos``, para no
    consultar por fila); sin ellos, se consultan."""
    if equipo.estado_hardware == EstadoHw.INACTIVO:
        return Situacion("baja", "Dado de baja")
    if equipo.estado_hardware == EstadoHw.FUERA_DE_SERVICIO:
        return Situacion("fuera_de_servicio", "Fuera de servicio")
    if equipo.clase == "actuador":
        pendiente = getattr(equipo, "comando_pendiente", None)
        if pendiente is None:
            pendiente = tiene_comando_pendiente(equipo)
        if pendiente:
            return Situacion("comando_pendiente", "Comando pendiente")
    if equipo.ultimo_mensaje_en is None:
        return Situacion("sin_confirmar", "Sin confirmar")
    if equipo.clase == "actuador" and equipo.compatibilidad == Actuador.Compatibilidad.INCOMPATIBLE:
        return Situacion("incompatible", "Configuración incompatible")
    if alertas is None:
        alertas = set(_consulta_de_alertas_activas([equipo.pk]).values_list("alerta__tipo_alerta", flat=True))
    for tipo, clave, texto in SITUACIONES_POR_ALERTA:
        if tipo in alertas:
            return Situacion(clave, texto)
    return Situacion("operativo", "Operativo")


def alertas_activas_del_equipo(equipo):
    """Regla 6 de IOT-CNS-HDW: las alertas activas del equipo, por id: las vinculadas a él (``AlertaIot.hardware``) y, en un sensor, las de sus lecturas (``AlertaIot.telemetria``)."""
    return [vinculo.alerta for vinculo in _consulta_de_alertas_activas([equipo.pk]).select_related("alerta").order_by("alerta_id")]


def acciones_permitidas(actor, equipo):
    """D-30: las acciones que ``actor`` puede hacer sobre ``equipo``, un ``frozenset``. Quien opera el IoT del invernadero (regla 1 de IOT-DSC-SIS),
    con el sistema no dado de baja: modifica y da de baja un equipo activo, modifica, vuelve a activar y da de baja uno fuera de servicio y reactiva uno dado de baja;
    quien solo consulta, ninguna. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active:
        return frozenset()
    sistema = equipo.sistema
    try:
        _exigir_operador(actor)
    except PermissionDenied:
        return frozenset()
    if sistema.estado_sistema == Estado.INACTIVO or not puede_operar(actor, sistema.invernadero):
        return frozenset()
    if equipo.estado_hardware == EstadoHw.INACTIVO:
        return frozenset({ACCION_REACTIVAR})
    if equipo.estado_hardware == EstadoHw.FUERA_DE_SERVICIO:
        return frozenset({ACCION_MODIFICAR, ACCION_VOLVER_A_ACTIVAR, ACCION_BAJA})
    return frozenset({ACCION_MODIFICAR, ACCION_BAJA})


def baja_con_identificador(sistema, identificador):
    """Regla 12 de IOT-ALT-HDW: el último equipo dado de baja del sistema que tenía ``identificador`` (sin distinguir mayúsculas ni espacios al borde),
    o ``None`` si lo usa un equipo en uso o no hubo ninguno. El alta lo advierte y ofrece reactivarlo."""
    identificador = texto(identificador)
    if not identificador or _equipo_con_identificador(sistema, identificador) is not None:
        return None
    baja = (
        Hardware.objects.filter(sistema=sistema, estado_hardware=EstadoHw.INACTIVO)
        .annotate(_minuscula=Lower("identificador_equipo"))
        .filter(_minuscula=identificador.lower())
        .order_by("-pk")
        .first()
    )
    return None if baja is None else _especifico(baja)


def identificadores_anunciados_libres(sistema):
    """Regla 14 de IOT-ALT-HDW: los identificadores que el nodo anunció y todavía no están registrados (ningún equipo no dado de baja los usa), por
    identificador, marcando con ``era_de`` el equipo dado de baja que los tenía. Los escribe la API del nodo (IOT-03, ``anuncios.py``)."""
    en_uso = {
        i.lower()
        for i in Hardware.objects.filter(sistema=sistema)
        .exclude(estado_hardware=EstadoHw.INACTIVO)
        .exclude(identificador_equipo__isnull=True)
        .values_list("identificador_equipo", flat=True)
    }
    libres = []
    for anunciado in EquipoAnunciado.objects.filter(sistema=sistema).order_by(Lower("identificador_equipo")):
        if anunciado.identificador_equipo.lower() not in en_uso:
            libres.append(
                Anunciado(anunciado.identificador_equipo, anunciado.clase, baja_con_identificador(sistema, anunciado.identificador_equipo))
            )
    return libres


# ---- los registrantes de sector de `maestros` (IOT-02; docs/api/extensiones_de_maestros.md, «Sectores»; los registra ``IotConfig.ready()``) ----


def _descripcion_de_equipo_en_un_sector(equipo):
    """«Sensor de temperatura norte/sectorA/temperatura» o «Actuador Ventilador norte/ventilador»."""
    if equipo.clase == "sensor":
        return f"Sensor de {equipo.get_tipo_variable_sensor_display().lower()} {equipo.identificador_equipo}"
    return f"Actuador {equipo.tipo_actuador.nombre_actuador} {equipo.identificador_equipo}"


def _equipos_de_sectores(sectores):
    """``{sector_id: [Sensor | Actuador]}`` con los equipos NO dados de baja de esos sectores, por identificador. Una consulta por clase para toda la lista."""
    ids = [sector.pk for sector in sectores]
    por_sector = {i: [] for i in ids}
    consultas = (
        Sensor.objects.filter(sector_id__in=ids),
        Actuador.objects.filter(sector_id__in=ids).select_related("tipo_actuador"),
    )
    for consulta in consultas:
        for equipo in consulta.exclude(estado_hardware=EstadoHw.INACTIVO).order_by(Lower("identificador_equipo"), "pk"):
            por_sector[equipo.sector_id].append(equipo)
    return por_sector


def impedimentos_de_baja_del_sector(sector):
    """Registrante de ``registrar_impedimento_de_baja_de_sector``: un sector con equipos no dados de baja no se da de baja (regla 3 de PROD-BAJ-SCT y regla 4 de IOT-BAJ-HDW).
    Código ``hardware_activo``."""
    equipos = _equipos_de_sectores([sector])[sector.pk]
    if not equipos:
        return []
    cantidad = f"{len(equipos)} equipo{'s' if len(equipos) != 1 else ''}"
    lista = ", ".join(e.identificador_equipo for e in equipos)
    return [
        Impedimento(
            "hardware_activo",
            f"Tiene {cantidad} del sistema IoT: {lista}.",
            "Quitales el sector o dalos de baja desde IoT · Hardware.",
        )
    ]


def contenido_de_sectores(sectores):
    """Registrante de ``registrar_contenido_de_sector``: un ``Contenido`` de tipo ``hardware`` por equipo no dado de baja de cada sector, con la URL de su ficha
    (regla 3 de PROD-CNS-SCT). Una consulta por clase para toda la lista (sin consultas por fila)."""
    sectores = list(sectores)
    por_sector = _equipos_de_sectores(sectores)
    return {
        sector.pk: [
            Contenido("hardware", _descripcion_de_equipo_en_un_sector(e), None, None, reverse("iot:hardware_ficha", args=[e.pk]))
            for e in por_sector[sector.pk]
        ]
        for sector in sectores
    }
