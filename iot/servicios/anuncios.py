# Anuncio de equipos del nodo (IOT-03; IOT-ENT-INF extensión 1c y postcondiciones r y s; «El anuncio» de docs/casos_de_uso/iot/entregar_informacion.md;
# docs/api/nodo/mensajes.md, sección 4). Se procesa ENTERO o NADA, en una transacción: reemplaza los ``EquipoAnunciado`` del sistema y recalcula la
# compatibilidad de TODOS los actuadores no dados de baja con ``compatibilidad.recalcular_compatibilidad`` (IOT-02: una sola función la calcula).
# Bloqueos (``FOR NO KEY UPDATE``): invernadero → sistema (releído) → (la compatibilidad bloquea cada actuador). No toca los tipos de actuador, así que no
# se cruza con IOT-MOD-TAC (D-82). El anuncio no cambia ``ultimo_mensaje_en``: no es un mensaje «sobre» un equipo.

from collections import namedtuple

from django.db import transaction

from iot.models import Actuador, ComandoCatalogo, EquipoAnunciado, Hardware, SistemaIoT
from iot.servicios import compatibilidad
from iot.servicios.auditoria_nodo import auditar_entrega
from iot.servicios.nodo import SistemaDesconectado
from maestros.servicios import alertas as api_alertas

ActuadorAnunciado = namedtuple("ActuadorAnunciado", "identificador compatibilidad acciones_incompatibles")
ResultadoDeAnuncio = namedtuple("ResultadoDeAnuncio", "equipos actuadores sin_registrar")


def registrar_anuncio(sistema_id, equipos, ahora):
    """Registra ``equipos`` (``EquipoRecibido``, con la forma ya verificada) y devuelve un ``ResultadoDeAnuncio``: cuántos equipos anunció el nodo, cada
    actuador registrado (no dado de baja) con su compatibilidad, por identificador, y los identificadores anunciados sin equipo vigente. Lanza
    ``SistemaDesconectado`` si el sistema ya no está activo."""
    with transaction.atomic():
        invernadero_id = SistemaIoT.objects.values_list("invernadero_id", flat=True).get(pk=sistema_id)
        api_alertas.bloquear_invernadero_para_alertas(invernadero_id)
        sistema = SistemaIoT.objects.select_for_update(no_key=True).get(pk=sistema_id)
        if sistema.estado_sistema != SistemaIoT.Estado.ACTIVO:
            raise SistemaDesconectado()
        EquipoAnunciado.objects.filter(sistema=sistema).delete()
        catalogo = {comando.codigo: comando for comando in ComandoCatalogo.objects.all()}
        for equipo in equipos:  # postcondición r
            anunciado = EquipoAnunciado.objects.create(
                sistema=sistema, identificador_equipo=equipo.identificador, clase=equipo.clase, anunciado_en=ahora
            )
            anunciado.comandos.set([catalogo[codigo] for codigo in equipo.comandos])
        actuadores = list(Actuador.objects.filter(sistema=sistema).exclude(estado_hardware="inactivo").select_related("sistema", "tipo_actuador"))
        antes = {actuador.pk: actuador.compatibilidad for actuador in actuadores}
        recalculos = compatibilidad.recalcular_compatibilidad(actuadores)  # postcondición s
        cambios, afectados, generadas, resueltas = {}, [], [], []
        for recalculo in recalculos:
            actuador = recalculo.actuador
            if antes[actuador.pk] != actuador.compatibilidad:
                cambios[f"compatibilidad de {actuador.identificador_equipo}"] = {"antes": antes[actuador.pk], "despues": actuador.compatibilidad}
                afectados.append(actuador)
            if recalculo.alerta_creada is not None:
                generadas.append(recalculo.alerta_creada)
            if recalculo.alerta_resuelta is not None:
                resueltas.append(recalculo.alerta_resuelta)
        if cambios or generadas or resueltas:
            auditar_entrega(sistema, "anuncio", None, afectados, cambios, generadas, resueltas)
        respuesta = [
            ActuadorAnunciado(
                actuador.identificador_equipo,
                actuador.compatibilidad,
                [accion.nombre_accion for accion in actuador.acciones_incompatibles.order_by("id")],
            )
            for actuador in sorted(actuadores, key=lambda a: a.identificador_equipo.lower())
        ]
        vigentes = {
            identificador.lower()
            for identificador in Hardware.objects.filter(sistema=sistema)
            .exclude(estado_hardware="inactivo")
            .exclude(identificador_equipo__isnull=True)
            .values_list("identificador_equipo", flat=True)
        }
        sin_registrar = [equipo.identificador for equipo in equipos if equipo.identificador.lower() not in vigentes]
        return ResultadoDeAnuncio(len(equipos), respuesta, sin_registrar)
