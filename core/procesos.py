# Proceso diario (DIA-01, D-56): registro de los pasos que corren una vez por día y la función que los corre en orden.
# ``core`` no conoce ningún paso: cada app registra el suyo en su ``AppConfig.ready()`` (regla A4 de D-37), con el mismo
# patrón que ``core/extensiones.py`` (Variaciones protegidas con Indirección, Larman): una lista de módulo, que las
# pruebas reemplazan con ``mock.patch.object``, y un registro idempotente. El comando ``proceso_diario`` es el «cron job
# sin cron job»: lo lanza una persona; más adelante el cron único (disparador «Cuando se arme el cron único») ejecuta
# exactamente el mismo comando.
#
# Órdenes reservados (D-56, punto 6), de 10 en 10 para poder intercalar pasos; se usan solo los que existan:
#
#   Orden | Paso                              | App
#   ------+-----------------------------------+------------
#     10  | Revisar vencimientos de insumos   | inventario
#     20  | Vencer partidas en cámara         | comercial (D-59: toca reservas)
#     25  | Reasignar cámara                  | comercial (COM-04b: recupera PROD-ASG-CAM)
#     30  | Vencer pagos de suministro        | comercial
#     35  | Cerrar rescisiones de suministros | comercial (COM-03b)
#     40  | Pre-reservar suministros          | comercial
#     50  | Planificar entregas               | comercial
#     60  | Pedidos vencidos                  | compras (CMP-03: avisa del vencimiento o cancela «nadie cotizó»)
#     61  | Recordatorio de validez           | compras (CMP-03: mañana vence la primera cotización elegible)
#     62  | Pedidos sin cotización elegible   | compras (CMP-03: cancela si ninguna cotización se puede elegir)
#
# ``iot`` no usa este proceso (su revisión es periódica y la decide su documentación).
#
# CONTRATO de cada paso (D-56, punto 4): ``funcion(hoy) -> ResumenDePaso``, con ``hoy`` un ``date``. Es idempotente (correrlo
# dos veces el mismo día no duplica nada), trabaja por unidad con una transacción por unidad, y nunca lee la fecha por su
# cuenta: así ``--fecha`` simula el paso del tiempo. Este módulo no abre transacciones ni audita (D-22): cada paso audita lo
# suyo.

import logging
from collections import namedtuple

from django.utils import timezone

logger = logging.getLogger("infoponia.proceso_diario")

# Un paso registrado: su código (el de ``--solo``), su nombre para mostrar, su orden y su función ``funcion(hoy)``.
PasoDiario = namedtuple("PasoDiario", "codigo nombre orden funcion")
# Lo que informa un paso al terminar; ``detalle`` es texto libre y opcional.
ResumenDePaso = namedtuple("ResumenDePaso", "procesados creados resueltos detalle", defaults=("",))

# Lista de módulo: las pruebas la reemplazan con ``mock.patch.object``.
_PASOS_DIARIOS = []


def registrar_paso_diario(codigo, nombre, orden, funcion):
    """Registra un paso del proceso diario y devuelve su ``PasoDiario``. ``funcion(hoy) -> ResumenDePaso``.

    Idempotente: ``ready()`` puede correr más de una vez, así que un registro idéntico (código, nombre, orden y función)
    no se duplica. Lanza ``RuntimeError`` si el ``codigo`` ya existe con cualquier otra diferencia, o si el ``orden`` ya
    lo usa otro paso (D-56, punto 2; DIA-01, paso 1).
    """
    nuevo = PasoDiario(codigo, nombre, orden, funcion)
    for existente in _PASOS_DIARIOS:
        if existente.codigo == codigo:
            if existente == nuevo:
                return existente
            raise RuntimeError(
                f"El paso diario «{codigo}» ya está registrado con otro nombre, otro orden u otra función."
            )
        if existente.orden == orden:
            raise RuntimeError(
                f"El orden {orden} ya lo usa el paso diario «{existente.codigo}»: no puede usarlo «{codigo}»."
            )
    _PASOS_DIARIOS.append(nuevo)
    return nuevo


def pasos_diarios():
    """Los pasos registrados, ordenados por ``orden``."""
    return sorted(_PASOS_DIARIOS, key=lambda paso: paso.orden)


def correr_proceso_diario(hoy=None, solo=None):
    """Corre los pasos en orden y devuelve una lista de ``(paso, ResumenDePaso | None, error | None)``.

    - ``hoy`` (un ``date``) vale ``timezone.localdate()`` por defecto; se lee una sola vez y se pasa a todos los pasos.
    - ``solo`` es un ``codigo``: corre únicamente ese paso; si no existe, ``ValueError`` con los códigos válidos.
    - Si un paso lanza una excepción, se registra en el log y los demás siguen (D-56, punto 5): un paso no puede dejar a
      los siguientes sin correr. No abre transacciones: cada paso maneja las suyas, una por unidad (D-56, punto 4).
    """
    if hoy is None:
        hoy = timezone.localdate()
    pasos = pasos_diarios()
    if solo is not None:
        elegidos = [paso for paso in pasos if paso.codigo == solo]
        if not elegidos:
            validos = ", ".join(paso.codigo for paso in pasos) or "(ninguno)"
            raise ValueError(f"No existe el paso diario «{solo}». Códigos válidos: {validos}.")
        pasos = elegidos

    resultados = []
    for paso in pasos:
        try:
            resultados.append((paso, paso.funcion(hoy), None))
        except Exception as error:  # noqa: BLE001 - un paso roto no puede frenar a los demás (D-56, punto 5)
            logger.exception("Falló el paso diario «%s»: %r", paso.codigo, error)
            resultados.append((paso, None, error))
    return resultados
