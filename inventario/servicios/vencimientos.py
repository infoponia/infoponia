# CMP-REV-VNC · Revisar Vencimientos de Insumos (INV-02, paso 7; docs/casos_de_uso/inventario/vencimientos.md; D-56).
# ``revisar_vencimientos(hoy)`` la usan el comando ``revisar_vencimientos`` y el paso 10 del proceso diario (``paso_diario``): la misma función.
# Una transacción por invernadero (en orden de id): se bloquea el invernadero, se releen los lotes y recién entonces se decide. Una falla se deshace
# entera, se informa y no impide revisar los demás. Es idempotente: mira el estado de cada lote contra ``hoy``, no el día anterior.
# Las alertas se piden a la API de ``maestros`` tomada como atributo del módulo (``api_alertas.asegurar_alerta_de_estado``), no con ``from ... import``,
# para que las pruebas puedan simular una falla.

from collections import namedtuple
from datetime import timedelta

from django.db import transaction

from core.models import RegistroAuditoria, referencia
from core.procesos import ResumenDePaso
from inventario import alertas as tipos
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, stock
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion

# ``revisados``: invernaderos cuya revisión terminó; ``creadas`` y ``resueltas``: listas de ``Alerta``; ``fallas``: ``[(invernadero_id, error)]``.
Resultado = namedtuple("Resultado", "revisados creadas resueltas fallas")


def _activa(invernadero_id, tipo, clave):
    """La alerta activa de ese tipo y clave, o ``None``."""
    return Alerta.objects.filter(
        invernadero_id=invernadero_id, tipo_alerta=tipo, clave_estado=clave, estado_alerta=Alerta.Estado.ACTIVA
    ).first()


def _asegurar(invernadero_id, tipo, clave, descripcion):
    """Asegura la alerta con la API y devuelve la ``Alerta`` si la creó ahora; ``None`` si ya existía (regla 5)."""
    if _activa(invernadero_id, tipo, clave) is not None:
        return None
    return api_alertas.asegurar_alerta_de_estado(invernadero_id, tipo, clave=clave, descripcion=descripcion)


def _auditar(invernadero, insumo, lote, creada, resueltas):
    """Postcondición d (D-27, D-36): un registro por alerta creada, con ``usuario=None`` (el sistema)."""
    datos = {"insumo": referencia(insumo), "alertas_creadas": [referencia(creada)]}
    if lote is not None:
        datos["lotes"] = [referencia(lote)]
    if resueltas:
        datos["alertas_resueltas"] = [referencia(a) for a in resueltas]
    RegistroAuditoria.objects.registrar(
        usuario=None, accion=RegistroAuditoria.Accion.ALERTA_DE_VENCIMIENTO, afectados=[insumo, invernadero], detalle={"datos": datos}
    )


def _revisar_invernadero(invernadero_id, hoy, dias_de_aviso, creadas, resueltas):
    """Revisa un invernadero dentro de la transacción de quien llama; suma lo creado y lo resuelto a las listas."""
    invernadero = api_alertas.bloquear_invernadero_para_alertas(invernadero_id)
    if not invernadero.activo:
        return
    agronomo_activo = bool(invernadero.agronomo_id and invernadero.agronomo.is_active)  # regla 6: sin Agrónomo no se alerta
    lotes = list(
        LoteInsumo.objects.select_related("insumo_invernadero__insumo")
        .filter(
            insumo_invernadero__invernadero_id=invernadero_id,
            insumo_invernadero__estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO,
            es_faltante_sin_lote=False,
        )
        .order_by("id")
    )
    limite = hoy + timedelta(days=dias_de_aviso)
    con_lote_vencido = {}  # insumo_invernadero -> True (regla 11)
    for lote in lotes:
        iin = lote.insumo_invernadero
        clave = f"lote:{lote.pk}"
        if lote.cantidad_disponible <= 0:
            # Regla 7 y postcondición c: un lote agotado ya no tiene alertas de vencimiento activas.
            for tipo in (tipos.INSUMO_POR_VENCER, tipos.INSUMO_VENCIDO):
                if _activa(invernadero_id, tipo, clave) is not None:
                    resuelta = api_alertas.resolver_alerta_de_estado(invernadero_id, tipo, clave=clave)
                    if resuelta is not None:
                        resueltas.append(resuelta)
            continue
        if lote.fecha_vencimiento is None:  # regla 2: solo lotes con fecha de vencimiento
            continue
        if stock.esta_vencido(lote, hoy):  # regla 4: vencido desde el día siguiente
            con_lote_vencido[iin.pk] = iin
        if not agronomo_activo:
            continue
        descripcion = alertas_de_stock.descripcion_de_vencimiento(iin.insumo, lote)
        if stock.esta_vencido(lote, hoy):
            creada = _asegurar(invernadero_id, tipos.INSUMO_VENCIDO, clave, descripcion)
            if creada is not None:
                # Postcondición b: la «por vencer» del mismo lote se resuelve al vencer, en el mismo registro.
                propias = []
                if _activa(invernadero_id, tipos.INSUMO_POR_VENCER, clave) is not None:
                    por_vencer = api_alertas.resolver_alerta_de_estado(invernadero_id, tipos.INSUMO_POR_VENCER, clave=clave)
                    if por_vencer is not None:
                        propias.append(por_vencer)
                creadas.append(creada)
                resueltas.extend(propias)
                _auditar(invernadero, iin.insumo, lote, creada, propias)
        elif lote.fecha_vencimiento <= limite:  # regla 3: faltan entre 0 y ``dias_aviso_vencimiento`` días
            creada = _asegurar(invernadero_id, tipos.INSUMO_POR_VENCER, clave, descripcion)
            if creada is not None:
                creadas.append(creada)
                _auditar(invernadero, iin.insumo, lote, creada, [])
    # Regla 11: «bajo el mínimo» de los insumos con algún lote vencido con stock. Solo la crea; nunca la resuelve.
    if agronomo_activo and con_lote_vencido:
        existencias = stock.existencias(list(con_lote_vencido), hoy)
        for iin_id, iin in con_lote_vencido.items():
            existencia = existencias[iin_id]
            if not (iin.insumo.activo and existencia.bajo_minimo):
                continue
            creada = _asegurar(
                invernadero_id, tipos.INSUMO_BAJO_MINIMO, f"insumo:{iin_id}", alertas_de_stock.descripcion_de_bajo_minimo(iin.insumo, existencia)
            )
            if creada is not None:
                creadas.append(creada)
                _auditar(invernadero, iin.insumo, None, creada, [])


def revisar_vencimientos(hoy=None):
    """CMP-REV-VNC: revisa los lotes con vencimiento de los insumos activos de los invernaderos activos y devuelve ``Resultado``.

    ``hoy`` permite simular un día (sin él, la fecha de ``America/Argentina/Buenos_Aires``). ``dias_aviso_vencimiento`` se lee una vez
    al empezar la corrida (regla 10). No modifica stock (regla 8) ni escribe bitácora ni asientos (regla 9)."""
    if hoy is None:
        hoy = stock.hoy()
    dias_de_aviso = configuracion.obtener().dias_aviso_vencimiento
    ids = (
        InsumoInvernadero.objects.filter(
            estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO, invernadero__estado_invernadero="activo"
        )
        .order_by("invernadero_id")
        .values_list("invernadero_id", flat=True)
        .distinct()
    )
    creadas, resueltas, fallas, revisados = [], [], [], 0
    for invernadero_id in list(ids):
        propias_creadas, propias_resueltas = [], []
        try:
            with transaction.atomic():
                _revisar_invernadero(invernadero_id, hoy, dias_de_aviso, propias_creadas, propias_resueltas)
        except Exception as error:  # noqa: BLE001 — una falla se informa y no impide revisar los demás (D-56, punto 5)
            fallas.append((invernadero_id, error))
            continue
        revisados += 1
        creadas.extend(propias_creadas)
        resueltas.extend(propias_resueltas)
    return Resultado(revisados, creadas, resueltas, fallas)


def paso_diario(hoy):
    """Paso 10 del proceso diario (D-56): llama a ``revisar_vencimientos(hoy)``. Si algún invernadero falló, lanza el error AL TERMINAR
    (con los demás ya revisados) para que ``proceso_diario`` lo informe como fallido."""
    resultado = revisar_vencimientos(hoy)
    if resultado.fallas:
        detalle = "; ".join(f"invernadero {id_}: {error}" for id_, error in resultado.fallas)
        raise RuntimeError(f"Falló la revisión de {len(resultado.fallas)} invernadero(s): {detalle}")
    return ResumenDePaso(procesados=resultado.revisados, creados=len(resultado.creadas), resueltos=len(resultado.resueltas))
