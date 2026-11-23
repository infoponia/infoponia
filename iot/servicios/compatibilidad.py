# Compatibilidad de los actuadores con lo que anunció el nodo (IOT-02; docs/casos_de_uso/iot/hardware.md, «Cómo se aplica», «Compatibilidad»;
# regla 14 de IOT-ALT-HDW, regla 10 de IOT-MOD-HDW, regla 9 y postcondición c de IOT-MOD-TAC). ``recalcular_compatibilidad`` es la ÚNICA función que
# calcula y escribe la compatibilidad: la usan el alta, la modificación y la reactivación del hardware, IOT-MOD-TAC y la API de anuncios (IOT-03).
#
# Sin anuncio del equipo: ``sin_verificar`` y ninguna acción incompatible (no se restringe nada). Con anuncio: se comparan los comandos de las acciones
# ACTIVAS del tipo con los anunciados para el identificador (sin distinguir mayúsculas) en el sistema del actuador.
#
# Bloqueos (D-40 y la decisión D-82): quien llama con varios actuadores no necesita ordenarlos ni bloquear nada; esta función los ordena por invernadero y
# bloquea, para cada uno, el invernadero (con ``bloquear_invernadero_para_alertas``, reentrante) ANTES que la fila del actuador, y recién después crea o
# resuelve su alerta. Así dos modificaciones de tipos distintos, que tocan los mismos invernaderos, no se bloquean entre sí.

from collections import namedtuple

from maestros.servicios import alertas as api_alertas

from iot.models import Actuador, EquipoAnunciado
from iot.servicios import alertas_iot

TIPO_DE_ALERTA = "iot_configuracion_incompatible"

# Resultado de comparar un tipo con un anuncio: ``estado`` es ``compatible``, ``incompatible`` o ``sin_verificar``; ``acciones_incompatibles`` son
# las acciones activas del tipo cuyo comando el nodo no anunció.
Compatibilidad = namedtuple("Compatibilidad", "estado acciones_incompatibles")
# Lo que hizo ``recalcular_compatibilidad`` con un actuador: su alerta creada o resuelta, si hubo (para los ``afectados`` de la auditoría).
Recalculo = namedtuple("Recalculo", "actuador alerta_creada alerta_resuelta")


def calcular_compatibilidad(sistema, identificador, tipo):
    """Compara las acciones activas de ``tipo`` con el anuncio del nodo para ``identificador`` en ``sistema``, SIN escribir. Es lo que se
    muestra antes de guardar (regla 10 de IOT-MOD-HDW) y lo que usa ``recalcular_compatibilidad``."""
    anunciado = EquipoAnunciado.objects.filter(sistema=sistema, identificador_equipo__iexact=(identificador or "").strip()).first()
    if anunciado is None:
        return Compatibilidad("sin_verificar", [])
    anunciados = set(anunciado.comandos.values_list("pk", flat=True))
    acciones = tipo.acciones.filter(estado="activa").select_related("comando").order_by("id")
    faltan = [accion for accion in acciones if accion.comando_id not in anunciados]
    return Compatibilidad("incompatible" if faltan else "compatible", faltan)


def _descripcion_de_la_alerta(actuador, faltan):
    """«Ventilador norte/ventilador · el nodo no anunció APAGAR (acción «Apagar»)»: lo que muestra la alerta."""
    comandos = ", ".join(accion.comando.codigo for accion in faltan)
    acciones = ", ".join(f"«{accion.nombre_accion}»" for accion in faltan)
    return f"{actuador.tipo_actuador.nombre_actuador} {actuador.identificador_equipo} · el nodo no anunció {comandos} (acción {acciones})"


def recalcular_compatibilidad(actuadores):
    """Recalcula la compatibilidad de cada actuador de ``actuadores`` (los dados de baja se saltean) y genera o resuelve su alerta
    «configuración incompatible» (clave ``hw:<id>``), con su ``AlertaIot`` (R052), por ``alertas_iot`` (IOT-03: una sola forma de crear un ``AlertaIot``). Corre dentro de la transacción de quien llama. Devuelve una lista de
    ``Recalculo`` y deja actualizados los objetos recibidos. Postcondición d de IOT-MOD-HDW; regla 14 de IOT-ALT-HDW."""
    ordenados = sorted(actuadores, key=lambda a: (a.sistema.invernadero_id, a.pk))
    resultado = []
    for recibido in ordenados:
        if recibido.estado_hardware == Actuador.Estado.INACTIVO:
            continue
        invernadero = api_alertas.bloquear_invernadero_para_alertas(recibido.sistema.invernadero_id)
        actuador = Actuador.objects.select_for_update(no_key=True).select_related("sistema", "tipo_actuador").get(pk=recibido.pk)
        if actuador.estado_hardware == Actuador.Estado.INACTIVO:
            continue
        calculada = calcular_compatibilidad(actuador.sistema, actuador.identificador_equipo, actuador.tipo_actuador)
        if actuador.compatibilidad != calculada.estado:
            actuador.compatibilidad = calculada.estado
            actuador.save(update_fields=["compatibilidad"])
        actuador.acciones_incompatibles.set(calculada.acciones_incompatibles)
        clave = f"hw:{actuador.pk}"
        creada = resuelta = None
        if calculada.estado == "incompatible":
            resultado_alerta = alertas_iot.asegurar_alerta_iot(
                invernadero.pk,
                actuador.sistema,
                TIPO_DE_ALERTA,
                clave,
                _descripcion_de_la_alerta(actuador, calculada.acciones_incompatibles),
                hardware=actuador,
            )
            creada = resultado_alerta.alerta if resultado_alerta.creada else None
        else:
            resuelta = alertas_iot.resolver_alerta_iot(invernadero.pk, TIPO_DE_ALERTA, clave)
        recibido.compatibilidad = calculada.estado
        resultado.append(Recalculo(recibido, creada, resuelta))
    return resultado
