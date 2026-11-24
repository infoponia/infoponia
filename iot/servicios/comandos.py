# Servicios de los comandos del IoT (IOT-05): emitir (IOT-EMT-CMD, docs/casos_de_uso/iot/emitir_comando.md), cancelar (IOT-CNL-CMD) y, en los pasos siguientes de la tarea, el retiro y el
# resultado que informa el nodo (IOT-RSV-CMD). Cada caso de uso es una función dentro de ``transaction.atomic()``, audita con el formato de D-36 (docs/patrones/auditoria.md) y recibe
# ``ahora``: nunca lee la hora por su cuenta.
#
# Orden de bloqueos (siempre ``FOR NO KEY UPDATE``): la emisión toma primero el TIPO del actuador, después el invernadero, el sistema y el actuador (D-82: un pendiente impide quitar la
# acción de un tipo, y IOT-MOD-TAC bloquea el tipo antes que los invernaderos; es un agregado a D-78, punto 11, que no nombra el tipo). El resto de los casos de uso de comandos no toca el tipo.
# El índice único «un pendiente por actuador» respalda la extensión 8a: su ``IntegrityError`` se traduce al mismo error, nunca un 500.

import math
import re
from collections import namedtuple
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.http import Http404
from django.utils import timezone

from core.models import Agronomo, RegistroAuditoria, Usuario, referencia, rol_de
from iot.alcance import invernaderos_que_consulta, puede_operar
from iot.catalogo import estado_que_deja
from iot.models import Accion, Actuador, Comando, Hardware, NodoCentral, RegistroComando, ReglaActuacion, SistemaIoT
from iot.servicios import alertas_iot
from iot.servicios import nodo as servicio_nodo
from iot.servicios.sistemas import Estado, _error_de_alcance, _exigir_operador, _sistema_vigente, conectividad
from iot.servicios.tipos_actuador import bloquear_tipo_activo
from iot.textos import estado_legible
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general

LARGO_DE_LA_DESCRIPCION = Comando._meta.get_field("descripcion_comando").max_length
LARGO_DE_LA_BITACORA = 500  # ``Bitacora.descripcion_evento``
ENTERO = re.compile(r"^[+-]?\d{1,9}$")

# ``clave`` es una de ``reglas``, ``mismo_estado``, ``sin_confirmar``, ``sin_senal``, ``tiempo_minimo`` o ``modo_local`` (6b a 6g, en ese orden).
Advertencia = namedtuple("Advertencia", "clave texto")
ResumenDeComando = namedtuple("ResumenDeComando", "actuador accion valor descripcion advertencias")
# Un actuador de la lista del paso 2.
FilaDeEmision = namedtuple("FilaDeEmision", "actuador sector estado_texto desde sin_confirmar compatibilidad comando_pendiente")
DatosParaEmitir = namedtuple(
    "DatosParaEmitir", "invernadero sistema nodo conectividad modo actuadores elegido acciones acciones_incompatibles reglas bloqueo"
)


def codigo_de(comando):
    """El código visible de un comando: ``CMD-{id}``."""
    return f"CMD-{comando.pk}"


@dataclass
class DatosDeComando:
    """Lo que manda el formulario de emisión. Los valores pueden venir como texto: el servicio los valida."""

    accion_id: object = None
    valor: object = None
    descripcion: object = ""

    @classmethod
    def desde_post(cls, post):
        """Arma los datos desde el POST; tolera campos que faltan (los errores los da el servicio)."""
        return cls(accion_id=post.get("accion") or None, valor=post.get("valor"), descripcion=post.get("descripcion", ""))


# ---- la regla «Comando válido» (una sola función; también la usan las reglas de actuación, IOT-06) ----


def _normalizar_valor(valor):
    """El valor como entero; ``ValueError`` si no lo es (un decimal, un texto, un booleano)."""
    if isinstance(valor, bool):
        raise ValueError(valor)
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and ENTERO.match(valor.strip()):
        return int(valor.strip())
    raise ValueError(valor)


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def validar_comando(actuador, accion, valor):
    """Regla «Comando válido» de IOT-EMT-CMD, sin escribir. Devuelve ``{campo: [ValidationError]}`` (vacío si está bien). Es la ÚNICA función de la regla: la usan la emisión manual
    y las reglas de actuación (IOT-06), así que los códigos son un contrato compartido:

    - campo ``accion``: ``accion_no_disponible`` (no es una acción activa del tipo del actuador) y ``accion_incompatible`` (el nodo no la soporta, regla 14 de IOT-ALT-HDW);
    - campo ``valor``: ``valor_requerido`` (la acción lleva valor y falta), ``valor_invalido`` (no es un entero o está fuera del rango; el mensaje informa el rango) y
      ``valor_de_mas`` (la acción no lleva valor y viene uno)."""
    errores = {}

    def agregar(campo, mensaje, codigo):
        errores.setdefault(campo, []).append(ValidationError(mensaje, code=codigo))

    if accion.tipo_actuador_id != actuador.tipo_actuador_id or accion.estado != Accion.Estado.ACTIVA:
        agregar("accion", "La acción ya no está disponible para este actuador.", "accion_no_disponible")
    elif actuador.acciones_incompatibles.filter(pk=accion.pk).exists():
        agregar("accion", "El nodo no la soporta para este actuador: su configuración es incompatible.", "accion_incompatible")
    if accion.comando.lleva_valor:
        rango = f"un número entero entre {accion.valor_minimo} y {accion.valor_maximo} {accion.unidad_valor}"
        if _vacio(valor):
            agregar("valor", f"Ingresá el valor: {rango}.", "valor_requerido")
        else:
            try:
                entero = _normalizar_valor(valor)
            except ValueError:
                entero = None
            if entero is None or not accion.valor_minimo <= entero <= accion.valor_maximo:
                agregar("valor", f"Ingresá {rango}, sin decimales.", "valor_invalido")
    elif not _vacio(valor):
        agregar("valor", "Esta acción no lleva valor.", "valor_de_mas")
    return errores


# ---- lecturas que comparten el resumen y la emisión ----


def _pendiente_de(actuador):
    """El comando pendiente del actuador, o ``None``."""
    return Comando.objects.filter(actuador=actuador, estado_comando=Comando.Estado.PENDIENTE).first()


def _reglas_activas(actuador):
    """Las reglas de actuación activas del actuador (6b). Hasta IOT-06, que es quien las crea, no hay ninguna."""
    return list(ReglaActuacion.objects.filter(actuador=actuador, estado_regla=ReglaActuacion.Estado.ACTIVA).order_by("id"))


def _error_pendiente(pendiente):
    """Extensiones 3a y 8a: ya hay un comando pendiente (se nombra con su código si se lo conoce)."""
    quien = f" ({codigo_de(pendiente)})" if pendiente is not None else ""
    return _error_general(
        f"Ya hay un comando pendiente para este actuador{quien}. Cancelalo o esperá su resultado: solo se admite uno por actuador.", "comando_pendiente"
    )


def _motivo_de_bloqueo(sistema, actuador):
    """Por qué no se puede emitir al actuador ahora (sistema, actuador o comando pendiente), como ``ValidationError``, o ``None`` (regla «Actuador elegible»)."""
    if sistema.estado_sistema == Estado.DESCONECTADO:
        return _error_general("El sistema IoT está desconectado. No se pueden emitir comandos hasta activarlo.", "sistema_no_activo")
    if sistema.estado_sistema != Estado.ACTIVO:
        return _error_general("El sistema IoT está dado de baja.", "sistema_no_activo")
    if actuador.estado_hardware == Actuador.Estado.FUERA_DE_SERVICIO:
        return _error_general("Este actuador está fuera de servicio. Volvé a activarlo desde Hardware antes de emitir comandos.", "actuador_no_activo")
    if actuador.estado_hardware != Actuador.Estado.ACTIVO:
        return _error_general("Este actuador está dado de baja.", "actuador_no_activo")
    pendiente = _pendiente_de(actuador)
    return _error_pendiente(pendiente) if pendiente is not None else None


def _verificar(actor, invernadero, sistema, actuador, datos):
    """Las verificaciones del paso 6 y del 8b, con el alcance ya releído: el alcance del actor, los bloqueos y, si no hay, los errores de los campos (``accion``, ``valor`` y
    ``descripcion``, juntos en una sola ``ValidationError``). Devuelve ``(accion, valor entero o None, descripción recortada)``."""
    if not puede_operar(actor, invernadero):
        raise _error_de_alcance(actor, invernadero)
    bloqueo = _motivo_de_bloqueo(sistema, actuador)
    if bloqueo is not None:
        raise bloqueo
    errores = {}
    accion = None
    if datos.accion_id not in (None, ""):
        try:
            accion = Accion.objects.select_related("comando").filter(pk=int(datos.accion_id)).first()
        except (TypeError, ValueError):
            accion = None
    if accion is None:
        errores["accion"] = [ValidationError("Seleccioná la acción.", code="accion_no_disponible")]
    else:
        errores.update(validar_comando(actuador, accion, datos.valor))
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        errores["descripcion"] = [ValidationError(f"Hasta {LARGO_DE_LA_DESCRIPCION} caracteres.", code="descripcion_larga")]
    if errores:
        raise ValidationError(errores)
    valor = _normalizar_valor(datos.valor) if accion.comando.lleva_valor else None
    return accion, valor, descripcion


def _previo(actor, actuador_id):
    """Lo que se sabe del actuador antes de bloquear: ``Http404`` si no existe o su invernadero está fuera del alcance de consulta (D-28)."""
    fila = Actuador.objects.filter(pk=actuador_id).values("tipo_actuador_id", "sistema_id", "sistema__invernadero_id").first()
    if fila is None or not invernaderos_que_consulta(actor).filter(pk=fila["sistema__invernadero_id"]).exists():
        raise Http404("No existe ese actuador.")
    return fila


def _duracion(segundos):
    """«20 s», «3 min» o «3 min 5 s»."""
    if segundos < 60:
        return f"{segundos} s"
    minutos, resto = divmod(segundos, 60)
    return f"{minutos} min" + (f" {resto} s" if resto else "")


# ---- pasos 2 y 4 ----


def _fila(actuador, pendiente):
    return FilaDeEmision(
        actuador=actuador,
        sector=actuador.sector.nombre_sector if actuador.sector_id else "General",
        estado_texto=estado_legible(actuador.estado_informado) or "Desconocido",
        desde=actuador.estado_informado_en if actuador.estado_informado else None,
        sin_confirmar=actuador.ultimo_mensaje_en is None,
        compatibilidad=actuador.compatibilidad,
        comando_pendiente=pendiente,
    )


def datos_para_emitir(actor, invernadero_id, ahora, actuador_id=None):
    """Pasos 2 y 4 de IOT-EMT-CMD: el nodo (conectividad y modo), los actuadores activos del sistema activo y, si se elige uno (``actuador_id``, extensión 1b), sus acciones activas
    compatibles, las incompatibles aparte (extensión 4a) y sus reglas activas. ``bloqueo`` es el texto de por qué no se puede emitir (sin sistema, desconectado, actuador no activo o
    con un comando pendiente), o ``None``. Solo para quien opera el invernadero: ``PermissionDenied`` a otros roles y a quien solo consulta; ``Http404`` fuera del alcance (D-28)."""
    _exigir_operador(actor)
    invernadero = invernaderos_que_consulta(actor).select_related("agronomo").filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if not puede_operar(actor, invernadero):
        raise PermissionDenied("Este invernadero lo operás solo si no tiene un Agrónomo activo.")
    sistema = _sistema_vigente(invernadero.pk)
    if sistema is None:
        return DatosParaEmitir(invernadero, None, None, None, None, [], None, [], [], [], "Este invernadero no tiene un sistema IoT.")
    nodo = NodoCentral.objects.get(sistema=sistema)
    # Con el sistema no activo no hay actuadores que ofrecer: ``_motivo_de_bloqueo`` da el texto sin llegar a mirar al actuador.
    motivo_del_sistema = _motivo_de_bloqueo(sistema, None) if sistema.estado_sistema != Estado.ACTIVO else None
    bloqueo = motivo_del_sistema.messages[0] if motivo_del_sistema is not None else None
    activos = []
    if sistema.estado_sistema == Estado.ACTIVO:
        activos = list(
            Actuador.objects.filter(sistema=sistema, estado_hardware=Actuador.Estado.ACTIVO)
            .select_related("sector", "tipo_actuador")
            .order_by(Lower("identificador_equipo"), "pk")
        )
    pendientes = {c.actuador_id: c for c in Comando.objects.filter(actuador__in=activos, estado_comando=Comando.Estado.PENDIENTE)}
    filas = [_fila(a, pendientes.get(a.pk)) for a in activos]
    elegido, acciones, incompatibles, reglas = None, [], [], []
    if actuador_id is not None:
        actuador = (
            Actuador.objects.select_related("sector", "tipo_actuador").filter(pk=actuador_id, sistema=sistema).first()
        )
        if actuador is None:
            raise Http404("No existe ese actuador.")
        elegido = next((f for f in filas if f.actuador.pk == actuador.pk), None) or _fila(actuador, _pendiente_de(actuador))
        if bloqueo is None:
            motivo = _motivo_de_bloqueo(sistema, actuador)
            bloqueo = motivo.messages[0] if motivo is not None else None
        if actuador.estado_hardware == Actuador.Estado.ACTIVO:
            marcadas = set(actuador.acciones_incompatibles.values_list("pk", flat=True))
            todas = list(actuador.tipo_actuador.acciones.filter(estado=Accion.Estado.ACTIVA).select_related("comando").order_by("id"))
            acciones = [a for a in todas if a.pk not in marcadas] if bloqueo is None or elegido.comando_pendiente is not None else []
            incompatibles = [a for a in todas if a.pk in marcadas]
            reglas = _reglas_activas(actuador)
    return DatosParaEmitir(invernadero, sistema, nodo, conectividad(nodo, ahora), nodo.modo, filas, elegido, acciones, incompatibles, reglas, bloqueo)


# ---- paso 6 ----


def _advertencias(actuador, accion, valor, nodo, ahora):
    """Las advertencias 6b a 6g, en ese orden, con los textos de «Cómo se aplica». Ninguna bloquea."""
    advertencias = []
    reglas = _reglas_activas(actuador)
    if reglas:
        advertencias.append(
            Advertencia(
                "reglas",
                f"El actuador tiene {len(reglas)} regla(s) activa(s): este comando puede contradecirlas. Una regla solo vuelve a actuar cuando su condición pasa a cumplirse.",
            )
        )
    if actuador.estado_informado and estado_que_deja(accion.comando.codigo, valor) == actuador.estado_informado:
        advertencias.append(
            Advertencia(
                "mismo_estado",
                f"Según el último estado que informó el nodo, el actuador ya está {estado_legible(actuador.estado_informado).lower()}. El nodo lo informará como ejecutado sin cambiar nada.",
            )
        )
    if actuador.ultimo_mensaje_en is None:
        advertencias.append(
            Advertencia("sin_confirmar", "Del actuador nunca llegó ningún mensaje. Si su identificador está mal cargado, el comando no se va a ejecutar.")
        )
    if conectividad(nodo, ahora).estado == "sin_senal":
        advertencias.append(Advertencia("sin_senal", "El nodo está sin señal. El comando queda pendiente, sin consumir intentos, hasta que el nodo se comunique."))
    minimo = actuador.tipo_actuador.tiempo_minimo_entre_comandos
    # D-78, punto 7: desde ``resuelto_en`` del último comando EJECUTADO (no del último emitido, fallido ni cancelado).
    ultimo = Comando.objects.filter(actuador=actuador, estado_comando=Comando.Estado.EJECUTADO).order_by("-resuelto_en").first()
    if ultimo is not None and minimo > 0:
        pasaron = int((ahora - ultimo.resuelto_en).total_seconds())
        if pasaron < minimo:
            advertencias.append(
                Advertencia(
                    "tiempo_minimo",
                    f"El actuador cambió de estado hace {_duracion(max(pasaron, 0))}. Cambiarlo tan seguido puede dañar el equipo: faltan {minimo - pasaron} s para cumplir el tiempo mínimo entre comandos. Podés emitirlo igual.",
                )
            )
    if nodo.modo == NodoCentral.Modo.LOCAL:
        advertencias.append(
            Advertencia("modo_local", "El nodo está operando en modo local. El comando queda pendiente, sin consumir intentos, hasta que vuelva a «remoto».")
        )
    return advertencias


def resumen_de_comando(actor, actuador_id, datos, ahora):
    """Paso 6 de IOT-EMT-CMD: verifica los datos (los mismos errores que la emisión) y devuelve el resumen con las advertencias 6b a 6g. No escribe ni audita ni bloquea."""
    _exigir_operador(actor)
    previo = _previo(actor, actuador_id)
    invernadero = invernaderos_que_consulta(actor).get(pk=previo["sistema__invernadero_id"])
    sistema = SistemaIoT.objects.get(pk=previo["sistema_id"])
    actuador = Actuador.objects.select_related("tipo_actuador").get(pk=actuador_id)
    accion, valor, descripcion = _verificar(actor, invernadero, sistema, actuador, datos)
    nodo = NodoCentral.objects.get(sistema=sistema)
    return ResumenDeComando(actuador, accion, valor, descripcion, _advertencias(actuador, accion, valor, nodo, ahora))


# ---- la bitácora de cada hecho (D-78, punto 3) ----


def registrar_hecho(comando, resultado, ahora, responsable=None, numero_intento=None, que_paso=""):
    """Un ``RegistroComando`` por hecho del comando (nunca por el retiro). Descripción: «{tipo} {identificador}: {acción}[ {valor} {unidad}] · {qué pasó}», hasta 500. ``responsable``
    es quien emitió o canceló, y ``None`` si fue InfoPonia o el nodo. Corre dentro de la transacción de quien llama."""
    actuador, accion = comando.actuador, comando.accion
    valor = f" {comando.valor_comando} {accion.unidad_valor}" if comando.valor_comando is not None else ""
    texto = f"{actuador.tipo_actuador.nombre_actuador} {actuador.identificador_equipo}: {accion.nombre_accion}{valor} · {que_paso or resultado}"
    local = timezone.localtime(ahora)
    return RegistroComando.objects.create(
        comando=comando,
        resultado=resultado,
        numero_intento=numero_intento,
        responsable=responsable,
        fecha_bitacora=local.date(),
        hora_bitacora=local.time(),
        descripcion_evento=texto[:LARGO_DE_LA_BITACORA],
    )


# ---- paso 8 ----


def emitir_comando(actor, actuador_id, datos, ahora):
    """IOT-EMT-CMD: emite un comando a un actuador y lo devuelve.

    - Precondición a: Agrónomo o Gerente activos. Regla «Alcance» y extensión 1a: el Gerente, solo sin Agrónomo activo. Se vuelve a verificar todo DESPUÉS de bloquear (extensión 8b).
    - Reglas «Actuador elegible», «Un comando pendiente por actuador» (extensiones 3a y 8a) y «Comando válido» (``validar_comando``).
    - Postcondición a: el comando, pendiente, con 0 intentos; ``agronomo`` solo si lo emitió un Agrónomo (R050). b: su ``RegistroComando`` ``emitido``. c: ``emision_comando``.
    - Bloqueos: tipo, invernadero, sistema y actuador (D-82), releídos."""
    _exigir_operador(actor)
    previo = _previo(actor, actuador_id)
    with transaction.atomic():
        bloquear_tipo_activo(previo["tipo_actuador_id"])
        invernadero = api_alertas.bloquear_invernadero_para_alertas(previo["sistema__invernadero_id"])
        _actor_sigue_activo(actor)
        sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=previo["sistema_id"])
        actuador = Actuador.objects.select_for_update(no_key=True).select_related("tipo_actuador").get(pk=actuador_id)
        accion, valor, descripcion = _verificar(actor, invernadero, sistema, actuador, datos)
        agronomo = Agronomo.objects.filter(pk=actor.pk).first() if rol_de(actor) == Usuario.Rol.AGRONOMO else None
        try:
            with transaction.atomic():  # punto de guardado: el IntegrityError no rompe la transacción de afuera
                comando = Comando.objects.create(
                    actuador=actuador, accion=accion, agronomo=agronomo, emitido_en=ahora, estado_comando=Comando.Estado.PENDIENTE,
                    valor_comando=valor, descripcion_comando=descripcion, cantidad_intentos=0,
                )
        except IntegrityError as error:
            if "comando_un_pendiente_por_actuador" in str(error):
                raise _error_pendiente(_pendiente_de(actuador)) from error
            raise
        registro = registrar_hecho(comando, RegistroComando.Resultado.EMITIDO, ahora, responsable=actor, que_paso="emitido")
        datos_de_auditoria = {"actuador": referencia(actuador), "accion": referencia(accion)}
        if valor is not None:
            datos_de_auditoria["valor"] = valor
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.EMISION_COMANDO,
            afectados=[comando, registro],
            detalle={"cambios": {"estado_comando": {"antes": None, "despues": "pendiente"}}, "datos": datos_de_auditoria},
        )
        return comando


# ---- IOT-CNL-CMD · cancelar (D-78, puntos 3 y 6) ----


def segundos_para_cancelar(comando, ahora):
    """Regla 2 de IOT-CNL-CMD y D-78, punto 6: 0 si el comando se puede cancelar (el nodo no lo retiró, o su último intento ya venció) y, si no, cuántos segundos faltan
    (``ultimo_intento_en + intervalo - ahora``, redondeado hacia arriba). El intervalo es ``segundos_intervalo_reintento`` de la Configuración Operativa, leído en cada uso."""
    if comando.cantidad_intentos == 0 or comando.ultimo_intento_en is None:
        return 0
    intervalo = timedelta(seconds=configuracion.obtener().segundos_intervalo_reintento)
    falta = (comando.ultimo_intento_en + intervalo - ahora).total_seconds()
    return max(0, math.ceil(falta))


def _cancelar(comando, motivo, ahora, responsable):
    """Pasa el comando bloqueado a «cancelado» y deja su registro de bitácora. Lo comparten ``cancelar_comando`` y ``cancelar_comando_incluido``."""
    comando.estado_comando = Comando.Estado.CANCELADO
    comando.resuelto_en = ahora
    comando.save(update_fields=["estado_comando", "resuelto_en"])
    return registrar_hecho(comando, RegistroComando.Resultado.CANCELADO, ahora, responsable=responsable, que_paso=f"cancelado ({motivo})" if motivo else "cancelado")


def cancelar_comando_incluido(comando, motivo, ahora, responsable=None):
    """La misma cancelación SIN verificación de alcance ni auditoría propia: para quien cancela como parte de otro caso de uso (2c de IOT-RSV-CMD, la desactivación y la baja del
    sistema y del hardware en IOT-06), que ya bloqueó, verificó y audita lo suyo. No espera a que venza el intento. Un comando que no está pendiente es un error de programación
    (``ValueError``). Devuelve el ``RegistroComando``."""
    if comando.estado_comando != Comando.Estado.PENDIENTE:
        raise ValueError(f"{codigo_de(comando)} no está pendiente: no se puede cancelar.")
    return _cancelar(comando, motivo, ahora, responsable)


def cancelar_comando(actor, comando_id, ahora):
    """IOT-CNL-CMD: cancela un comando pendiente y lo devuelve.

    - Precondición a y regla 1: Agrónomo o Gerente activos, con el alcance de IOT-DSC-SIS (el Gerente, solo sin Agrónomo activo); se vuelve a verificar después de bloquear.
    - Precondición b: pendiente (``comando_no_pendiente``). Reglas 2 y 5 (D-78, punto 6): si el nodo puede estar ejecutándolo, no se cancela y se informa cuánto falta
      (``comando_en_curso``); la carrera con un retiro la resuelve el bloqueo del comando. El servicio no distingue la regla 2 de la 5: mismo código y mismo mensaje.
    - Regla 3: manuales y automáticos. Postcondiciones a, b (``RegistroComando`` ``cancelado``, con el responsable) y c (``cancelacion_comando``).
    - Bloqueos: invernadero, sistema, actuador y comando (D-78, punto 11), releídos."""
    _exigir_operador(actor)
    fila = Comando.objects.filter(pk=comando_id).values("actuador_id", "actuador__sistema_id", "actuador__sistema__invernadero_id").first()
    if fila is None or not invernaderos_que_consulta(actor).filter(pk=fila["actuador__sistema__invernadero_id"]).exists():
        raise Http404("No existe ese comando.")
    with transaction.atomic():
        invernadero = api_alertas.bloquear_invernadero_para_alertas(fila["actuador__sistema__invernadero_id"])
        _actor_sigue_activo(actor)
        SistemaIoT.objects.select_for_update(no_key=True).get(pk=fila["actuador__sistema_id"])
        Actuador.objects.select_for_update(no_key=True).get(pk=fila["actuador_id"])
        comando = Comando.objects.select_for_update(no_key=True).select_related("actuador__tipo_actuador", "accion").get(pk=comando_id)
        if not puede_operar(actor, invernadero):
            raise _error_de_alcance(actor, invernadero)
        if comando.estado_comando != Comando.Estado.PENDIENTE:
            raise _error_general(f"{codigo_de(comando)} ya no está pendiente: no se puede cancelar.", "comando_no_pendiente")
        falta = segundos_para_cancelar(comando, ahora)
        if falta > 0:
            raise _error_general(
                f"El nodo acaba de retirar el comando: no se canceló. Podés cancelarlo cuando venza el intento (en {falta} s).", "comando_en_curso"
            )
        registro = _cancelar(comando, "", ahora, actor)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.CANCELACION_COMANDO,
            afectados=[comando, registro],
            detalle={"cambios": {"estado_comando": {"antes": "pendiente", "despues": "cancelado"}}},
        )
        return comando


# ---- IOT-RSV-CMD · el retiro y el resultado que informa el nodo (D-77, D-78) ----
# Bloqueos: invernadero → sistema → nodo → actuadores → comandos (en orden de id), en UNA transacción por mensaje (D-78, punto 11). No se toca el tipo del actuador.

TIPO_COMANDO_FALLIDO = "iot_comando_fallido"
TIPO_CONFIGURACION_INCOMPATIBLE = "iot_configuracion_incompatible"
TIPO_SIN_ACTIVIDAD = "iot_dispositivo_sin_actividad"
LARGO_DEL_DETALLE = Comando._meta.get_field("detalle_resultado").max_length

# Lo que informó el nodo, ya traducido: ``resultado`` es ``ejecutado``, ``fallo`` o ``rechazado``; ``estado`` e ``informado_en`` (un ``datetime`` con zona) son optativos.
ResultadoRecibido = namedtuple("ResultadoRecibido", "resultado detalle estado informado_en")
# ``resultado`` es ``aceptado`` o ``ya_resuelto``; ``estado_comando``, el estado que quedó (o el que ya tenía).
ResultadoDeComando = namedtuple("ResultadoDeComando", "resultado estado_comando")
EntregaDeComando = namedtuple("EntregaDeComando", "id identificador comando valor intento espera_segundos")
Retiro = namedtuple("Retiro", "modo comandos")


class ComandoInexistente(Exception):
    """Extensión 4e y D-78, punto 12: el comando no existe, no es de un actuador del nodo o es un pendiente que nunca se entregó. La vista lo responde 404 ``comando_inexistente``."""


class _Hechos:
    """Lo que un mensaje del nodo hizo con los comandos: se junta para escribir UN registro de auditoría (postcondición q) con los comandos, registros, equipos y alertas
    creados o modificados, los cambios de estado y un texto por hecho."""

    def __init__(self):
        self.afectados, self.cambios, self.textos = [], {}, []

    def sumar(self, *objetos):
        for objeto in objetos:
            if objeto is not None and all((objeto.pk, type(objeto)) != (o.pk, type(o)) for o in self.afectados):
                self.afectados.append(objeto)

    def hay(self):
        return bool(self.textos)


def _recortar(texto):
    return (texto or "").strip()[:LARGO_DEL_DETALLE]


def _ultimo_resultado(resultado, detalle):
    """«falló: detalle», «falló» o «sin respuesta»: el último resultado que nombra la alerta «comando fallido» (D-78, punto 10)."""
    if resultado == Comando.Resultado.SIN_RESPUESTA:
        return "sin respuesta"
    return f"falló: {detalle}" if detalle else "falló"


def _escalar(comando, actuador, sistema, resultado, detalle, ahora, hechos):
    """Extensión 4b (sin 4b.4: la orden de mantenimiento es de IOT-07) y D-78, puntos 3 y 10: el comando pasa a «fallido», el actuador a «fuera de servicio», se asegura la alerta
    crítica «comando fallido» (el correo lo manda la revisión periódica, D-71) y se registra el fallo definitivo."""
    antes = comando.estado_comando
    comando.estado_comando, comando.resultado_comando, comando.detalle_resultado, comando.resuelto_en = Comando.Estado.FALLIDO, resultado, detalle, ahora
    comando.save(update_fields=["estado_comando", "resultado_comando", "detalle_resultado", "resuelto_en"])
    desde = actuador.estado_hardware
    actuador.estado_hardware = Actuador.Estado.FUERA_DE_SERVICIO
    actuador.save(update_fields=["estado_hardware"])
    ultimo = _ultimo_resultado(resultado, detalle)
    descripcion = f"{actuador.identificador_equipo} · {comando.accion.nombre_accion} no se ejecutó en {comando.cantidad_intentos} intentos (último: {ultimo})"
    alerta = alertas_iot.asegurar_alerta_iot(actuador.sistema.invernadero_id, sistema, TIPO_COMANDO_FALLIDO, f"hw:{actuador.pk}", descripcion, hardware=actuador)
    registro = registrar_hecho(comando, RegistroComando.Resultado.FALLIDO, ahora, que_paso=f"fallido tras {comando.cantidad_intentos} intentos (último: {ultimo})")
    hechos.sumar(comando, actuador, alerta.alerta if alerta.creada else None, registro)
    hechos.cambios[f"Estado de {codigo_de(comando)}"] = {"antes": antes, "despues": "fallido"}
    hechos.cambios[f"Estado del equipo {actuador.identificador_equipo}"] = {"antes": desde, "despues": "fuera_de_servicio"}
    hechos.textos.append(f"{codigo_de(comando)}: fallido tras {comando.cantidad_intentos} intentos")


def _intento_fallido(comando, resultado, detalle, que_paso, ahora, hechos):
    """Extensiones 2a y 4a (con intentos restantes): sigue «pendiente» con el último resultado y deja un registro ``intento_fallido`` con el número de intento."""
    comando.resultado_comando, comando.detalle_resultado = resultado, detalle
    comando.save(update_fields=["resultado_comando", "detalle_resultado"])
    registro = registrar_hecho(comando, RegistroComando.Resultado.INTENTO_FALLIDO, ahora, numero_intento=comando.cantidad_intentos, que_paso=que_paso)
    hechos.sumar(comando, registro)
    hechos.textos.append(f"{codigo_de(comando)}: intento {comando.cantidad_intentos}: {que_paso.lower()}")


def _auditar(hechos, sistema, mensaje, identificador=None):
    """Postcondición q: un registro ``resolucion_comando_iot`` (actor ``None``, origen «nodo_central») con lo que hizo el mensaje. Solo si hubo hechos."""
    datos = {"origen": "nodo_central", "sistema": referencia(sistema), "mensaje": mensaje, "hechos": hechos.textos}
    if identificador is not None:
        datos["identificador"] = identificador
    detalle = {"datos": datos}
    if hechos.cambios:
        detalle["cambios"] = hechos.cambios
    RegistroAuditoria.objects.registrar(None, RegistroAuditoria.Accion.RESOLUCION_COMANDO_IOT, hechos.afectados, detalle)


def _respondio_con_fallo(comando):
    """Si el nodo ya respondió «falló» al intento en curso (extensión 4a): su registro ``intento_fallido`` lleva el número de ese intento. Distingue un intento fallido de uno «sin
    respuesta» que todavía no se registró: solo este último se da por vencido (2a) o se descuenta (2a.1a). Corre con el comando bloqueado."""
    return RegistroComando.objects.filter(
        comando=comando, resultado=RegistroComando.Resultado.INTENTO_FALLIDO, numero_intento=comando.cantidad_intentos
    ).exists()


def retirar_comandos(sistema_id, ahora):
    """IOT-RSV-CMD, pasos 1 y 2 y extensiones *a, 2a, 2a.1a, 2b, 2c y 2d: el retiro de los comandos disponibles del nodo, en una sola transacción. ``SistemaDesconectado`` si el
    sistema ya no está activo (extensión *a).

    1. Se lee la comunicación ANTERIOR del nodo y después se registra la de ahora (postcondición a; D-78, punto 2). En modo ``local`` termina acá (2d): no se toca ningún comando.
    2. 2c: el pendiente de un actuador que no está activo pasa a «cancelado» y no se entrega.
    3. 2a y 2a.1a (D-78, puntos 1 y 2): cada intento vencido se descuenta si el nodo estuvo «sin señal» y, si no, es un intento fallido «sin respuesta»; el último escala (4b).
    4. Disponibles (regla «Comando disponible»): nunca retirados, o con el último intento vencido y con intentos restantes: +1 intento y ``ultimo_intento_en`` (postcondición b).
    Se audita solo si canceló o dio por vencido un intento (la entrega sola y el descuento no)."""
    with transaction.atomic():
        sistema, nodo = servicio_nodo._bloquear_sistema_y_nodo(sistema_id)
        anterior = nodo.ultima_comunicacion
        servicio_nodo.registrar_comunicacion(sistema_id, ahora)
        if nodo.modo == NodoCentral.Modo.LOCAL:
            return Retiro(nodo.modo, [])
        config = configuracion.obtener()
        intervalo = timedelta(seconds=config.segundos_intervalo_reintento)
        maximo = 1 + config.cant_reintentos_comando
        sin_senal = anterior is None or ahora - anterior > timedelta(minutes=config.minutos_sin_comunicacion)
        actuadores = {a.pk: a for a in Actuador.objects.select_for_update(no_key=True).filter(sistema=sistema).order_by("pk")}
        pendientes = list(
            Comando.objects.select_for_update(no_key=True)
            .filter(actuador_id__in=list(actuadores), estado_comando=Comando.Estado.PENDIENTE)
            .prefetch_related("accion__comando")
            .order_by("pk")
        )
        hechos, entregas = _Hechos(), []
        for comando in pendientes:
            actuador = actuadores[comando.actuador_id]
            comando.actuador = actuador
            if actuador.estado_hardware != Actuador.Estado.ACTIVO:  # 2c
                motivo = "Actuador fuera de servicio" if actuador.estado_hardware == Actuador.Estado.FUERA_DE_SERVICIO else "Actuador dado de baja"
                registro = cancelar_comando_incluido(comando, motivo, ahora)
                hechos.sumar(comando, registro)
                hechos.cambios[f"Estado de {codigo_de(comando)}"] = {"antes": "pendiente", "despues": "cancelado"}
                hechos.textos.append(f"{codigo_de(comando)}: cancelado ({motivo})")
                continue
            vencido = comando.cantidad_intentos > 0 and comando.ultimo_intento_en + intervalo <= ahora
            if comando.cantidad_intentos > 0 and not vencido:
                continue  # dentro de su espera: no se vuelve a entregar
            if vencido and _respondio_con_fallo(comando):
                vencido = False  # el nodo SÍ respondió «falló» a este intento (4a): ya está registrado; no es «sin respuesta» ni se descuenta (2a.1a)
            if vencido and sin_senal:  # 2a.1a: la falta de respuesta es del nodo, no del actuador
                comando.cantidad_intentos -= 1
                comando.save(update_fields=["cantidad_intentos"])
            elif vencido:  # 2a: «sin respuesta»
                if comando.cantidad_intentos >= maximo:
                    _escalar(comando, actuador, sistema, Comando.Resultado.SIN_RESPUESTA, "", ahora, hechos)
                    continue
                _intento_fallido(comando, Comando.Resultado.SIN_RESPUESTA, "", "Sin respuesta", ahora, hechos)
            comando.cantidad_intentos += 1
            comando.ultimo_intento_en = ahora
            comando.save(update_fields=["cantidad_intentos", "ultimo_intento_en"])
            entregas.append(
                EntregaDeComando(
                    comando.pk, actuador.identificador_equipo, comando.accion.comando.codigo, comando.valor_comando, comando.cantidad_intentos,
                    config.segundos_intervalo_reintento,
                )
            )
        if hechos.hay():
            _auditar(hechos, sistema, "retiro")
        return Retiro(nodo.modo, entregas)


def _descripcion_incompatible(actuador, accion, detalle):
    """D-78, punto 5 y respuesta del estudiante: «{tipo} {identificador} · el nodo rechazó {COMANDO} (acción «{acción}»)[: {detalle}]»."""
    texto = f"{actuador.tipo_actuador.nombre_actuador} {actuador.identificador_equipo} · el nodo rechazó {accion.comando.codigo} (acción «{accion.nombre_accion}»)"
    return f"{texto}: {detalle}" if detalle else texto


def registrar_resultado(sistema_id, comando_id, recibido, ahora):
    """IOT-RSV-CMD, pasos 4 a 6 y extensiones 4a a 4f: registra el resultado que informó el nodo para ``comando_id`` y devuelve un ``ResultadoDeComando``.

    - 4e: un comando que no existe o no es de un actuador del sistema es ``ComandoInexistente`` sin registrar nada (ni la comunicación): se detecta antes de bloquear.
    - Después de bloquear se registra la comunicación. 4d: uno que ya no está pendiente es ``ya_resuelto``, sin cambios. D-78, punto 12: un pendiente que nunca se entregó
      (``cantidad_intentos = 0``) también es ``ComandoInexistente``, pero esta comunicación sí queda registrada. 4c: uno tardío que sigue pendiente se acepta.
    - ``ejecutado`` (postcondiciones c a e), ``fallo`` (4a con intentos restantes; 4b en el último) y ``rechazado`` (4f). Auditoría: ``resolucion_comando_iot`` (postcondición q)."""
    fila = Comando.objects.filter(pk=comando_id, actuador__sistema_id=sistema_id).values("actuador_id").first()
    if fila is None:
        raise ComandoInexistente(comando_id)
    with transaction.atomic():
        sistema, nodo = servicio_nodo._bloquear_sistema_y_nodo(sistema_id)
        servicio_nodo.registrar_comunicacion(sistema_id, ahora)
        actuador = Actuador.objects.select_for_update(no_key=True).select_related("tipo_actuador").get(pk=fila["actuador_id"])
        comando = Comando.objects.select_for_update(no_key=True).select_related("accion__comando").get(pk=comando_id)
        comando.actuador = actuador
        if comando.estado_comando != Comando.Estado.PENDIENTE:  # 4d
            return ResultadoDeComando("ya_resuelto", comando.estado_comando)
        if comando.cantidad_intentos > 0:
            hechos = _Hechos()
            _aplicar(recibido, comando, actuador, sistema, ahora, hechos)
            _auditar(hechos, sistema, "resultado", actuador.identificador_equipo)
            return ResultadoDeComando("aceptado", comando.estado_comando)
    # D-78, punto 12: se detecta después de bloquear y de registrar la comunicación, que ya quedó confirmada al salir del ``atomic``.
    raise ComandoInexistente(comando_id)


def _aplicar(recibido, comando, actuador, sistema, ahora, hechos):
    """Los pasos 5 y las extensiones 4a, 4b y 4f para un comando pendiente y bloqueado."""
    detalle = _recortar(recibido.detalle)
    maximo = 1 + configuracion.obtener().cant_reintentos_comando
    Hardware.objects.filter(pk=actuador.pk).update(ultimo_mensaje_en=ahora)  # «Lo que esto completa»: un resultado también carga ``ultimo_mensaje_en``
    actuador.ultimo_mensaje_en = ahora
    antes = comando.estado_comando
    if recibido.resultado == "ejecutado":
        comando.estado_comando, comando.resultado_comando, comando.detalle_resultado, comando.resuelto_en = Comando.Estado.EJECUTADO, Comando.Resultado.EJECUTADO, detalle, ahora
        comando.save(update_fields=["estado_comando", "resultado_comando", "detalle_resultado", "resuelto_en"])
        if recibido.estado:  # D-78, punto 4: lo informa el resultado, así que no queda «cambiado en el invernadero»
            if actuador.estado_informado != recibido.estado:
                hechos.cambios["estado_informado"] = {"antes": actuador.estado_informado, "despues": recibido.estado}
            actuador.estado_informado, actuador.estado_informado_en, actuador.cambiado_en_invernadero = recibido.estado, recibido.informado_en or ahora, False
            actuador.save(update_fields=["estado_informado", "estado_informado_en", "cambiado_en_invernadero"])
            hechos.sumar(actuador)
        resuelta = alertas_iot.resolver_alerta_iot(actuador.sistema.invernadero_id, TIPO_SIN_ACTIVIDAD, f"hw:{actuador.pk}")
        registro = registrar_hecho(comando, RegistroComando.Resultado.EJECUTADO, ahora, que_paso=f"ejecutado{': ' + detalle if detalle else ''}")
        hechos.sumar(comando, registro, resuelta)
    elif recibido.resultado == "fallo":
        if comando.cantidad_intentos < maximo:
            _intento_fallido(comando, Comando.Resultado.FALLO, detalle, f"Falló: {detalle}" if detalle else "Falló", ahora, hechos)
            hechos.cambios["resultado_comando"] = {"antes": None, "despues": "fallo"}
            return
        _escalar(comando, actuador, sistema, Comando.Resultado.FALLO, detalle, ahora, hechos)
        hechos.cambios["estado_comando"] = {"antes": antes, "despues": "fallido"}
        return
    else:  # rechazado (4f): falla sin reintentos y el actuador sigue activo
        comando.estado_comando, comando.resultado_comando, comando.detalle_resultado, comando.resuelto_en = Comando.Estado.FALLIDO, Comando.Resultado.RECHAZADO, detalle, ahora
        comando.save(update_fields=["estado_comando", "resultado_comando", "detalle_resultado", "resuelto_en"])
        actuador.acciones_incompatibles.add(comando.accion)
        if actuador.compatibilidad != Actuador.Compatibilidad.INCOMPATIBLE:
            hechos.cambios["compatibilidad"] = {"antes": actuador.compatibilidad, "despues": "incompatible"}
            actuador.compatibilidad = Actuador.Compatibilidad.INCOMPATIBLE
            actuador.save(update_fields=["compatibilidad"])
        alerta = alertas_iot.asegurar_alerta_iot(
            actuador.sistema.invernadero_id, sistema, TIPO_CONFIGURACION_INCOMPATIBLE, f"hw:{actuador.pk}", _descripcion_incompatible(actuador, comando.accion, detalle), hardware=actuador
        )
        registro = registrar_hecho(comando, RegistroComando.Resultado.RECHAZADO, ahora, que_paso=f"rechazado por el nodo{': ' + detalle if detalle else ''}")
        hechos.sumar(comando, actuador, alerta.alerta if alerta.creada else None, registro)
    hechos.cambios["estado_comando"] = {"antes": antes, "despues": comando.estado_comando}
    hechos.textos.append(f"{codigo_de(comando)}: {comando.estado_comando}")


# ---- consulta: la lista de «Comandos», el historial de la ficha del actuador y lo que muestra el panel (IOT-05, paso 7; emitir_comando.md, «Pantalla «Comandos»») ----

POR_PAGINA = 25
ESTADOS_DEL_FILTRO = tuple(Comando.Estado.values)
ORIGENES_DEL_FILTRO = ("manual", "regla")
# Cómo se muestra cada estado: (texto, tono de la insignia). Un rechazo del nodo se distingue del fallo del actuador (prototipo, ``cmdBadge``).
ESTADO_VISIBLE = {
    "pendiente": ("Pendiente", "info"),
    "ejecutado": ("Ejecutado", "ok"),
    "fallido": ("Fallido", "danger"),
    "cancelado": ("Cancelado", "neutral"),
}

FiltrosDeComandos = namedtuple("FiltrosDeComandos", "estado actuador_id origen", defaults=("", None, ""))
FilaDeComando = namedtuple(
    "FilaDeComando", "comando codigo actuador accion_texto codigo_del_comando origen estado estado_tono intentos ultimo_intento cancelable segundos nota"
)
PaginaDeComandos = namedtuple("PaginaDeComandos", "filas pagina paginas total")


def _nombre_de_persona(persona):
    """«Laura Benítez» o, sin nombre, el correo; el Gerente lleva «(Gerente)»."""
    nombre = persona.get_full_name() or persona.email
    return f"{nombre} (Gerente)" if rol_de(persona) == Usuario.Rol.GERENTE else nombre


def _origen_de(comando, emisores):
    """«Manual · {persona}» (quien lo emitió, de su registro de bitácora ``emitido``) o «Regla de actuación · RGL-n» (prototipo: columna «Origen»)."""
    if comando.regla_id:
        return f"Regla de actuación · RGL-{comando.regla_id}"
    persona = emisores.get(comando.pk)
    return f"Manual · {_nombre_de_persona(persona)}" if persona is not None else "Manual"


def _nota_de(comando):
    """El aviso bajo un comando fallido (prototipo, ``c.nota``); nada para los demás estados."""
    if comando.estado_comando != Comando.Estado.FALLIDO:
        return ""
    detalle = f": {comando.detalle_resultado}" if comando.detalle_resultado else ""
    if comando.resultado_comando == Comando.Resultado.RECHAZADO:
        return f"El nodo no reconoció el comando{detalle}. La acción quedó marcada como incompatible para este actuador."
    if comando.resultado_comando == Comando.Resultado.SIN_RESPUESTA:
        return f"El actuador no respondió en {comando.cantidad_intentos} intentos."
    return f"El actuador falló en {comando.cantidad_intentos} intentos (último resultado{detalle or ': sin detalle'})."


def filas_de_comandos(comandos, ahora):
    """Las filas de lista (``FilaDeComando``) de ``comandos``: la usa la ficha de una regla (IOT-CNS-RGL, regla 4) para mostrar los comandos que generó con el mismo aspecto que la lista."""
    return _filas_de(comandos, ahora)


def _filas_de(comandos_de_la_pagina, ahora):
    """Las filas de la lista con todo lo que dibuja la pantalla, sin consultas por fila (una para los emisores)."""
    maximo = 1 + configuracion.obtener().cant_reintentos_comando
    emitidos = RegistroComando.objects.filter(comando__in=comandos_de_la_pagina, resultado=RegistroComando.Resultado.EMITIDO).select_related("responsable")
    emisores = {registro.comando_id: registro.responsable for registro in emitidos if registro.responsable_id}
    filas = []
    for comando in comandos_de_la_pagina:
        texto, tono = ESTADO_VISIBLE[comando.estado_comando]
        if comando.estado_comando == Comando.Estado.FALLIDO and comando.resultado_comando == Comando.Resultado.RECHAZADO:
            texto = "Rechazado por el nodo"
        accion = comando.accion
        valor = f" · {comando.valor_comando} {accion.unidad_valor}" if comando.valor_comando is not None else ""
        pendiente = comando.estado_comando == Comando.Estado.PENDIENTE
        segundos = segundos_para_cancelar(comando, ahora) if pendiente else 0
        filas.append(
            FilaDeComando(
                comando=comando,
                codigo=codigo_de(comando),
                actuador=comando.actuador,
                accion_texto=f"{accion.nombre_accion}{valor}",
                codigo_del_comando=accion.comando.codigo,
                origen=_origen_de(comando, emisores),
                estado=texto,
                estado_tono=tono,
                intentos=f"{comando.cantidad_intentos} de {maximo}",
                ultimo_intento=comando.ultimo_intento_en,
                cancelable=pendiente and segundos == 0,
                segundos=segundos,
                nota=_nota_de(comando),
            )
        )
    return filas


def listar_comandos(actor, invernadero_id, ahora, filtros=None, pagina=1, por_pagina=POR_PAGINA):
    """La lista de comandos del invernadero (prototipo ``comandos``): del más reciente al más viejo, de a ``por_pagina``, con los filtros de estado, actuador y origen (manual o
    regla). Agrónomo o Gerente activos: otros roles, ``PermissionDenied``; un invernadero fuera de su alcance de consulta, ``Http404`` (D-28). Solo lectura: no audita (SEG-14).
    Un filtro desconocido se ignora y una página fuera de rango se acota."""
    _exigir_operador(actor)
    if not invernaderos_que_consulta(actor).filter(pk=invernadero_id).exists():
        raise Http404("No existe ese invernadero.")
    filtros = filtros or FiltrosDeComandos()
    consulta = Comando.objects.filter(actuador__sistema__invernadero_id=invernadero_id)
    if filtros.estado in ESTADOS_DEL_FILTRO:
        consulta = consulta.filter(estado_comando=filtros.estado)
    if str(filtros.actuador_id or "").isdigit():
        consulta = consulta.filter(actuador_id=int(filtros.actuador_id))
    if filtros.origen == "manual":
        consulta = consulta.filter(regla__isnull=True)
    elif filtros.origen == "regla":
        consulta = consulta.filter(regla__isnull=False)
    total = consulta.count()
    paginas = max(1, -(-total // por_pagina))
    pagina = min(max(int(pagina or 1), 1), paginas)
    pagina_de_comandos = list(
        consulta.select_related("actuador__tipo_actuador", "accion__comando").order_by("-emitido_en", "-pk")[(pagina - 1) * por_pagina : pagina * por_pagina]
    )
    return PaginaDeComandos(_filas_de(pagina_de_comandos, ahora), pagina, paginas, total)


def historial_del_actuador(actor, actuador, ahora, limite=10):
    """Los últimos ``limite`` comandos del actuador, para su ficha (IOT-CNS-HDW, regla 6): ``(filas, total)``. Mismo alcance que ``listar_comandos``."""
    pagina = listar_comandos(actor, actuador.sistema.invernadero_id, ahora, FiltrosDeComandos(actuador_id=actuador.pk), por_pagina=limite)
    return pagina.filas, pagina.total


def puede_emitir_a(actor, actuador):
    """Si ``actor`` ve «Emitir comando» en el actuador (D-30: ningún botón lleva a un 403): opera el invernadero y el actuador y su sistema están activos."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        return False
    sistema = actuador.sistema
    return (
        sistema.estado_sistema == Estado.ACTIVO
        and actuador.estado_hardware == Actuador.Estado.ACTIVO
        and puede_operar(actor, sistema.invernadero)
    )


def puede_cancelar(actor, comando):
    """Si ``actor`` ve «Cancelar» en un comando pendiente: lo opera (regla 1 de IOT-CNL-CMD) y está pendiente. Si el nodo puede estar ejecutándolo, el botón se ve deshabilitado
    con cuánto falta (regla 2): eso lo decide ``segundos_para_cancelar``."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        return False
    return comando.estado_comando == Comando.Estado.PENDIENTE and puede_operar(actor, comando.actuador.sistema.invernadero)


def comando_para_cancelar(actor, comando_id, ahora):
    """Lo que muestra la ventana de cancelar (prototipo ``ccan:<id>``): ``(fila, puede)``. Agrónomo o Gerente activos; fuera del alcance de consulta, ``Http404``. ``puede`` es
    falso si no lo opera, ya no está pendiente o el nodo puede estar ejecutándolo (la fila trae ``segundos``). No escribe: la cancelación es ``cancelar_comando``."""
    _exigir_operador(actor)
    comando = Comando.objects.select_related("actuador__tipo_actuador", "actuador__sistema__invernadero", "accion__comando").filter(pk=comando_id).first()
    if comando is None or not invernaderos_que_consulta(actor).filter(pk=comando.actuador.sistema.invernadero_id).exists():
        raise Http404("No existe ese comando.")
    fila = _filas_de([comando], ahora)[0]
    return fila, puede_cancelar(actor, comando) and fila.cancelable
