# Informe de ``estado_demo`` (DAT-02, paso 4): SOLO LECTURA. Dice, en castellano, qué fechas usa el guion de la defensa, qué escenas están
# listas, qué piezas del repo están y qué cuentas hay. No escribe nada, no imprime la contraseña ni el token del sistema IoT (solo si fue
# generado y cuándo) y no falla por lo que falte: cada cosa que no encuentra se informa como «no está lista».

import importlib
import inspect
from datetime import timedelta

from django.utils import timezone

from comercial.models import ReservaStock, Suministro
from core.models import Usuario
from core.procesos import pasos_diarios
from inventario.models import InsumoInvernadero, LoteInsumo
from iot.models import SistemaIoT
from produccion import extensiones as extensiones_produccion
from produccion.models import Lote


def _linea(lista, nombre, detalle):
    """«[lista] <nombre>: <detalle>» o «[falta] …»: una escena del guion."""
    return f"  [{'lista' if lista else 'falta'}] {nombre}: {detalle}"


def _lote(invernadero, variedad):
    return Lote.objects.filter(
        invernadero__nombre_invernadero=invernadero, siembra__variedad__nombre_variedad=variedad
    ).select_related("etapa__tipo_etapa").first()


def _escena_ln1():
    lote = _lote("Norte", "Criolla")
    if lote is None:
        return _linea(False, "LN-1", "no está cargado (sección 12)")
    libre = lote.cantidad_actual - extensiones_produccion.reservado_de_lotes([lote.pk])[lote.pk]
    en_maduracion = lote.etapa.tipo_etapa.codigo == "maduracion"
    return _linea(en_maduracion, "LN-1 (Lechuga Criolla, Norte)", f"{libre} plantas libres de {lote.cantidad_actual}, en {lote.etapa.tipo_etapa.codigo}")


def _escena_ln2():
    lote = _lote("Norte", "Morada")
    if lote is None:
        return _linea(False, "LN-2", "no está cargado (sección 12)")
    codigo = lote.etapa.tipo_etapa.codigo
    if codigo == "crecimiento":
        return _linea(True, "LN-2 (Lechuga Morada, Norte)", "en Crecimiento, lista para la transición a Maduración")
    return _linea(False, "LN-2 (Lechuga Morada, Norte)", f"ya está en {codigo}: la escena de la transición ya se hizo")


def _reservas_de(cuit):
    return list(
        ReservaStock.objects.filter(detalle_suministro__suministro__cliente__cuit_cliente=cuit)
        .order_by("fecha_entrega_reserva")
        .select_related("cosecha")
    )


def _suministro_existe(cuit):
    return Suministro.objects.filter(cliente__cuit_cliente=cuit).exists()


def _escena_s1(hoy):
    if not _suministro_existe("30714567809"):
        return _linea(False, "S-1", "no está pactado (sección 13)")
    reservas = _reservas_de("30714567809")
    if not reservas:
        return _linea(False, "S-1 (Súper Del Parque)", "sin reservas")
    primera = reservas[0]
    cosecha = primera.cosecha
    a_realizar = cosecha is not None and cosecha.estado_orden == "a_realizar"
    programada = f"{cosecha.fecha_programada_orden:%d/%m/%Y}" if cosecha is not None else "—"
    return _linea(a_realizar, "S-1 (Súper Del Parque)", f"{len(reservas)} períodos reservados; primera cosecha {'«a realizar»' if a_realizar else 'ya no está a realizar'}, programada para {programada}")


def _escena_s2():
    if not _suministro_existe("30711223300"):
        return _linea(False, "S-2", "no está pactado (sección 13)")
    reservas = _reservas_de("30711223300")
    if reservas:
        return _linea(False, "S-2 (Restaurante El Mensú)", f"ya tiene {len(reservas)} reserva(s): la pre-reserva en vivo ya corrió")
    return _linea(True, "S-2 (Restaurante El Mensú)", "sin reservas, lista para la pre-reserva del paso 40")


def _escena_iot():
    sistema = SistemaIoT.objects.filter(invernadero__nombre_invernadero="Norte").first()
    if sistema is None:
        return _linea(False, "Sistema IoT de Norte", "no está registrado (sección 14)")
    if sistema.token_generado_en is None:
        return _linea(True, "Sistema IoT de Norte", "sin token: generalo en la pantalla (IoT · Sistema IoT · Regenerar token)")
    generado = timezone.localtime(sistema.token_generado_en)
    # Nunca se muestra el valor ni su resumen: solo que existe y cuándo se generó.
    return _linea(True, "Sistema IoT de Norte", f"token generado el {generado:%d/%m/%Y %H:%M} (el valor no se muestra: regeneralo en la pantalla para usarlo en Node-RED)")


def _escena_solucion():
    existencia = InsumoInvernadero.objects.filter(
        invernadero__nombre_invernadero="Norte", insumo__nombre_insumo="Solución nutritiva A"
    ).first()
    if existencia is None:
        return _linea(False, "Solución nutritiva A (Norte)", "no está cargada (sección 7)")
    stock = sum(l.cantidad_disponible for l in LoteInsumo.objects.filter(insumo_invernadero=existencia))
    bajo = stock < existencia.cant_min_insumo
    return _linea(bajo, "Solución nutritiva A (Norte)", f"{_cantidad(stock)} contra un mínimo de {_cantidad(existencia.cant_min_insumo)}")


def _cantidad(valor):
    """Una cantidad sin ceros de más: 12.000 → «12»."""
    return format(valor.normalize(), "f")


def _paso_registrado(codigo):
    return any(paso.codigo == codigo for paso in pasos_diarios())


def _asiento_de_la_multa():
    """CON-04d: el asiento de la multa está si ``comercial.servicios.resoluciones`` llama al servicio de asientos."""
    modulo = importlib.import_module("comercial.servicios.resoluciones")
    return "registrar_asiento_automatico" in inspect.getsource(modulo)


def _lote_existente():
    try:
        modulo = importlib.import_module("produccion.servicios.lotes_existentes")
    except ImportError:
        return False
    return hasattr(modulo, "registrar_lote_existente")


def armar_informe(hoy):
    """Las líneas del informe, en este orden: fechas, escenas, piezas y cuentas."""
    lineas = ["Fechas del guion:"]
    lineas += [
        f"  HOY: {hoy:%d/%m/%Y}",
        f"  HOY+1: {hoy + timedelta(days=1):%d/%m/%Y} (proceso diario con --fecha, paso 40: pre-reserva de S-2)",
        f"  HOY+3: {hoy + timedelta(days=3):%d/%m/%Y} (vence el lote de 3 l del fungicida)",
        f"  HOY+8: {hoy + timedelta(days=8):%d/%m/%Y} (primera entrega de S-2)",
        "Escenas:",
        _escena_ln1(),
        _escena_ln2(),
        _escena_s1(hoy),
        _escena_s2(),
        _escena_iot(),
        _escena_solucion(),
        "Piezas del repo:",
        f"  Lote existente (PRD-05): {'está' if _lote_existente() else 'no está'}",
        f"  Pedido automático (CMP-07): {'está' if _paso_registrado('generar_pedidos_automaticos') else 'no está'}",
        f"  Cobro de suministro (COM-08a): {'está' if _paso_registrado('vencer_pagos') else 'no está'}",
        "  Asiento de la multa (CON-04d): " + ("está" if _asiento_de_la_multa() else "no está (la resolución sí)"),
        "Cuentas:",
    ]
    cuentas = list(Usuario.objects.exclude(rol="").order_by("id"))
    lineas += [f"  {cuenta.get_rol_display()}: {cuenta.email}" for cuenta in cuentas] or ["  (ninguna: la carga todavía no se hizo)"]
    return lineas
