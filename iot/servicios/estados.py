# Estados del nodo (IOT-03; IOT-ENT-INF extensión 1a y postcondiciones m a p y t; «Un estado» de docs/casos_de_uso/iot/entregar_informacion.md; D-75, puntos 1 y 6).
# ``registrar_estado`` procesa UN estado en su propia transacción. Bloqueos (``FOR NO KEY UPDATE``): invernadero → sistema (releído) → equipo. Recibe ``ahora``.

import re
from collections import namedtuple

from django.db import transaction

from iot.models import Actuador, AlertaIot, Hardware, Sensor, SistemaIoT
from iot.servicios.auditoria_nodo import auditar_entrega
from iot.servicios.lecturas import _Cambios, _equipo_de, _fecha
from maestros.servicios import alertas as api_alertas

ESTADOS_DE_CONECTIVIDAD = ("en_linea", "desconectado", "en_falla")
ESTADOS_OPERATIVOS_FIJOS = ("encendido", "apagado", "abierto", "cerrado")
ESTADO_CON_VALOR = re.compile(r"^(nivel|posicion):-?\d{1,6}$")  # D-75, punto 6
TIPO_SIN_ACTIVIDAD = "iot_dispositivo_sin_actividad"

ResultadoDeEstado = namedtuple("ResultadoDeEstado", "resultado motivo detalle", defaults=(None, ""))


def explica_un_comando(actuador, estado):
    """Postcondición p: el estado lo explica un comando de InfoPonia ejecutado sobre ese actuador. **Se completa en IOT-05** (comandos): hasta entonces, falso (D-75, punto 1)."""
    return False


def _rechazo(motivo, detalle):
    return ResultadoDeEstado("rechazado", motivo, detalle)


def _es_operativo(estado):
    return isinstance(estado, str) and (estado in ESTADOS_OPERATIVOS_FIJOS or ESTADO_CON_VALOR.fullmatch(estado) is not None)


def registrar_estado(sistema_id, estado, ahora):
    """Los pasos de «Un estado» para ``estado`` (un ``EstadoRecibido``). Devuelve un ``ResultadoDeEstado``: ``aceptado`` o ``rechazado`` con su ``motivo`` y ``detalle``."""
    with transaction.atomic():
        invernadero_id = SistemaIoT.objects.values_list("invernadero_id", flat=True).get(pk=sistema_id)
        api_alertas.bloquear_invernadero_para_alertas(invernadero_id)
        sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=sistema_id)
        if sistema.estado_sistema != SistemaIoT.Estado.ACTIVO:
            return _rechazo("sistema_desconectado", "El sistema IoT se desconectó mientras se procesaba el pedido.")
        cambios_de_alertas = _Cambios(invernadero_id, sistema)
        equipo, era_de_baja = _equipo_de(sistema.pk, estado.identificador)
        if equipo is None:  # extensión 3a y postcondición t
            return _no_registrado(cambios_de_alertas, sistema, estado, era_de_baja, ahora)
        informado_en, rechazo = _fecha(estado.informado_en, ahora)
        if rechazo:
            return _rechazo(rechazo.motivo, rechazo.detalle)
        valor = estado.estado
        if not (valor in ESTADOS_DE_CONECTIVIDAD if isinstance(valor, str) else False) and not _es_operativo(valor):
            return _rechazo("estado_invalido", f"«{valor}» no es un estado del contrato.")
        if equipo.clase == "sensor" and _es_operativo(valor):
            return _rechazo("estado_invalido", f"«{valor}» es un estado de actuador y «{estado.identificador_enviado}» es un sensor.")
        Hardware.objects.select_for_update(no_key=True).get(pk=equipo.pk)
        especifico = (Sensor if equipo.clase == "sensor" else Actuador).objects.get(pk=equipo.pk)
        clave = f"hw:{especifico.pk}"
        cambios = {}
        if valor == "en_linea":
            cambios_de_alertas.resolver(TIPO_SIN_ACTIVIDAD, clave)
        elif valor == "desconectado":
            cambios_de_alertas.asegurar(
                TIPO_SIN_ACTIVIDAD, clave, f"{especifico.identificador_equipo} · el nodo lo informó desconectado", hardware=especifico
            )
        elif valor == "en_falla":
            if especifico.estado_hardware == Hardware.Estado.ACTIVO:
                especifico.estado_hardware = Hardware.Estado.FUERA_DE_SERVICIO
                especifico.save(update_fields=["estado_hardware"])
                cambios["estado_hardware"] = {"antes": "activo", "despues": "fuera_de_servicio"}
            cambios_de_alertas.asegurar(
                "iot_dispositivo_en_falla", clave, f"{especifico.identificador_equipo} · el nodo lo informó en falla", hardware=especifico
            )
        else:  # estado operativo de un actuador
            cambios_de_alertas.resolver(TIPO_SIN_ACTIVIDAD, clave)
            _estado_operativo(especifico, valor, informado_en, cambios)
        Hardware.objects.filter(pk=especifico.pk).update(ultimo_mensaje_en=ahora)
        if cambios or cambios_de_alertas.generadas or cambios_de_alertas.resueltas:
            auditar_entrega(sistema, "estado", estado.identificador, [especifico], cambios, cambios_de_alertas.generadas, cambios_de_alertas.resueltas)
        return ResultadoDeEstado("aceptado")


def _estado_operativo(actuador, valor, informado_en, cambios):
    """Postcondición p y D-75, punto 1: guarda el estado informado con su fecha. Un estado igual al actual no cambia nada. «Cambiado en el invernadero»: el
    primer estado no se marca (sincronización inicial); los siguientes, si no los explica un comando de InfoPonia."""
    if actuador.estado_informado == valor:
        return
    antes = actuador.estado_informado
    marca = False if antes is None else not explica_un_comando(actuador, valor)
    cambios["estado_informado"] = {"antes": antes, "despues": valor}
    if marca != actuador.cambiado_en_invernadero:
        cambios["cambiado_en_invernadero"] = {"antes": actuador.cambiado_en_invernadero, "despues": marca}
    actuador.estado_informado, actuador.estado_informado_en, actuador.cambiado_en_invernadero = valor, informado_en, marca
    actuador.save(update_fields=["estado_informado", "estado_informado_en", "cambiado_en_invernadero"])


def _no_registrado(cambios, sistema, estado, era_de_baja, ahora):
    """Extensión 3a y postcondición t: rechaza el estado y genera (o encuentra) la alerta «dispositivo no registrado», con el estado en la descripción."""
    descripcion = f"El nodo envió el estado «{estado.estado}» de «{estado.identificador}», que no está registrado."
    resultado = cambios.asegurar("iot_dispositivo_no_registrado", f"id:{estado.identificador.lower()}", descripcion)
    if resultado.alerta is not None:
        AlertaIot.objects.filter(alerta=resultado.alerta).update(ultimo_mensaje_en=ahora)
    if cambios.generadas:
        auditar_entrega(sistema, "estado", estado.identificador, [], None, cambios.generadas, [])
    if era_de_baja:
        return _rechazo("equipo_dado_de_baja", f"«{estado.identificador_enviado}» era de un equipo dado de baja de este sistema IoT.")
    return _rechazo("equipo_no_registrado", f"«{estado.identificador_enviado}» no es un equipo registrado de este sistema IoT.")
