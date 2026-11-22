# Ajuste de stock de un insumo (CMP-AJT-STK; INV-02, paso 6). Caso de uso: docs/casos_de_uso/inventario/ajuste_de_stock.md, con su sección
# «Cómo se aplica en la ronda»; stock: docs/patrones/stock.md. Seis motivos y un recuento físico POR LOTE de todo el insumo (manda el CU, L7).
#
# DOS PASOS Y UNA CONFIRMACIÓN:
#   - ``calcular_ajuste`` NO escribe ni bloquea: valida, calcula las diferencias, el valor, la advertencia 12b y la «huella» del estado que usó.
#   - ``confirmar_ajuste`` bloquea (invernadero → existencia → lotes en orden de id, docs/patrones/stock.md, sección 5), compara la huella ANTES
#     de validar (si cambió, ``AjusteDesactualizado``: extensión 14a, sin cambiar nada), recalcula y escribe todo en UNA transacción.
# La HUELLA es lo que el cálculo usó: las cantidades disponibles de los lotes que usó (el recuento, todos, incluido el faltante; los demás motivos,
# los lotes que nombran) y las RESERVAS activas del insumo, que cambian el stock libre y la cobertura. Un cambio en otro lote no la invalida.
#
# Sin asientos contables (D-45): se omiten las precondiciones c y d, la postcondición e y el asiento del paso 14; el VALOR del ajuste (diferencia de
# stock × precio de referencia, en pesos con 2 decimales) sí se calcula y se muestra. Todo cambio de un lote genera exactamente un movimiento (regla 1
# de 8.19), con la fecha y la hora actuales y sin documento de origen; la corrección entre lotes son dos movimientos (salida y entrada por corrección)
# y la entrada se origina en su salida (R016). Se audita UN registro ``ajuste_stock`` (postcondiciones k, l y m) con los ``Decimal`` como texto (D-36).
# Se puede ajustar la existencia ACTIVA de una semilla dada de baja con su variedad (regla 3 de PROD-BAJ-VAR): no se exige que el insumo del catálogo
# esté activo.

from collections import namedtuple
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import RegistroAuditoria, referencia
from inventario import alertas as tipos_de_alerta
from inventario import extensiones
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import alertas_de_stock, insumos_invernadero, stock
from inventario.servicios.formato import texto_cantidad
from inventario.servicios.tipos_de_insumo import _exigir_agronomo
from inventario.unidades import validar_cantidad
from maestros.models import Alerta, Invernadero
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _error_general

Mov = MovimientoInsumo.TipoMovimiento
CERO = Decimal("0")
CENTAVOS = Decimal("0.01")

RECUENTO = "recuento_fisico"
ROTURA = "rotura_o_perdida"
CARGA_INICIAL = "carga_inicial"
VENCIMIENTO = "vencimiento"
CORRECCION = "correccion_entre_lotes"
OTRO = "otro"
# Los seis motivos del CU, en el orden del prototipo. La corrección entre lotes no es un motivo guardado (se guarda con sus dos tipos de
# movimiento), pero la pantalla la ofrece como uno más.
MOTIVOS = (
    (RECUENTO, "Recuento físico"),
    (ROTURA, "Rotura o pérdida"),
    (CARGA_INICIAL, "Carga inicial"),
    (VENCIMIENTO, "Vencimiento"),
    (CORRECCION, "Corregir entre lotes"),
    (OTRO, "Otro"),
)
CODIGOS_DE_MOTIVO = [codigo for codigo, _ in MOTIVOS]
# Motivo guardado en el movimiento (``MovimientoInsumo.MotivoAjuste``); la corrección no tiene.
MOTIVO_DEL_MOVIMIENTO = {
    RECUENTO: MovimientoInsumo.MotivoAjuste.RECUENTO_FISICO,
    ROTURA: MovimientoInsumo.MotivoAjuste.ROTURA_O_PERDIDA,
    CARGA_INICIAL: MovimientoInsumo.MotivoAjuste.CARGA_INICIAL,
    VENCIMIENTO: MovimientoInsumo.MotivoAjuste.VENCIMIENTO,
    OTRO: MovimientoInsumo.MotivoAjuste.OTRO,
}

Situacion = namedtuple("Situacion", "iin insumo stock_actual lotes faltante precio controla_vencimiento motivos")
CambioDeLote = namedtuple("CambioDeLote", "lote registrada contada diferencia")
LoteNuevo = namedtuple("LoteNuevo", "cantidad vencimiento")
Advertencia = namedtuple("Advertencia", "ordenes stock_vigente reservado")
Resumen = namedtuple(
    "Resumen", "lotes lotes_nuevos faltante_a_cero stock_antes stock_despues diferencia valor con_valor advertencia huella"
)
Resultado = namedtuple(
    "Resultado", "resumen movimientos lotes_nuevos stock_actual alertas_creadas alertas_resueltas inconsistente"
)
# Lo calculado de un ajuste, listo para escribir: ``cambios`` es ``[(lote, nueva_disponible)]``; ``nuevos`` es ``[(cantidad, vencimiento)]``;
# ``faltante`` es el lote del faltante sin lote que el recuento deja en cero (o ``None``) y ``faltante_a_cero`` lo que faltaba (positivo).
Plan = namedtuple("Plan", "motivo cambios nuevos descripcion faltante faltante_a_cero")
# El estado leído: la existencia, su insumo, sus lotes (por id), lo reservado y hoy.
Estado = namedtuple("Estado", "iin insumo lotes reservado hoy")


class AjusteDesactualizado(Exception):
    """Extensión 14a de CMP-AJT-STK: entre la carga y la confirmación otra operación cambió lo que el ajuste usó (la cantidad disponible de un
    lote indicado, el faltante sin lote o las reservas activas). No se cambió nada; ``vigente`` trae lo que hay ahora:
    ``{"lotes": {lote_id: disponible}, "reservado": Decimal}``, para volver al paso con los valores vigentes."""

    def __init__(self, vigente):
        super().__init__("Los datos cambiaron mientras tanto: revisá los valores vigentes y volvé a confirmar.")
        self.vigente = vigente


# ---- lectura del estado y permisos ----


def _entero(valor):
    """``valor`` como ``int`` o ``None`` (para los ids que llegan de una pantalla como texto)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _verificar_alcance(actor, invernadero):
    """Precondición b: el invernadero está a cargo del actor (``PermissionDenied``) y está activo (``invernadero_inactivo``)."""
    if invernadero.agronomo_id != actor.pk:
        raise PermissionDenied(insumos_invernadero.MENSAJE_AJENO)
    if not invernadero.activo:
        raise _error_general("El invernadero está inactivo: no se puede ajustar su stock.", "invernadero_inactivo")


def _exigir_habilitado(iin):
    """Extensión 4a: el insumo tiene que estar habilitado (existencia activa) en el invernadero."""
    if iin is None or not iin.activo:
        raise _error_general(
            "Ese insumo no está habilitado en el invernadero: habilitalo para ajustar su stock.", "insumo_no_habilitado"
        )


def _leer(actor, invernadero_id, insumo_id):
    """Lectura sin bloquear (``calcular_ajuste`` y ``situacion_del_insumo``): precondiciones a y b, extensión 4a y el estado."""
    _exigir_agronomo(actor)
    invernadero = get_object_or_404(Invernadero, pk=invernadero_id)
    get_object_or_404(Insumo, pk=insumo_id)
    _verificar_alcance(actor, invernadero)
    iin = (
        InsumoInvernadero.objects.select_related("insumo", "invernadero")
        .filter(insumo_id=insumo_id, invernadero_id=invernadero_id)
        .first()
    )
    _exigir_habilitado(iin)
    return _estado(iin, LoteInsumo.objects.filter(insumo_invernadero=iin).order_by("id"))


def _estado(iin, lotes):
    """El ``Estado`` de la existencia con sus lotes ya leídos (bloqueados o no)."""
    return Estado(iin, iin.insumo, {l.pk: l for l in lotes}, extensiones.reservado_de([iin.pk])[iin.pk], stock.hoy())


def _comunes(estado):
    """Los lotes que no son el faltante sin lote."""
    return [l for l in estado.lotes.values() if not l.es_faltante_sin_lote]


def _faltante_de(estado):
    return next((l for l in estado.lotes.values() if l.es_faltante_sin_lote), None)


def _huella(motivo, entrada, estado):
    """La huella del estado que usa un ajuste (ver el encabezado) y lo vigente de eso mismo: ``(huella, vigente)``."""
    if motivo == RECUENTO:
        usados = set(estado.lotes)
    else:
        usados = set()
        if motivo == ROTURA or (motivo == OTRO and entrada.get("sentido") == "resta"):
            usados.add(_entero(entrada.get("lote_id")))
        elif motivo == VENCIMIENTO:
            usados.update(_entero(i) for i in (entrada.get("lotes") or []))
        elif motivo == CORRECCION:
            usados.update([_entero(entrada.get("origen_id")), _entero(entrada.get("destino_id"))])
    lotes = {i: estado.lotes[i].cantidad_disponible for i in sorted(usados, key=lambda x: (x is None, x)) if i in estado.lotes}
    huella = (tuple((i, str(c)) for i, c in lotes.items()), str(estado.reservado))
    return huella, {"lotes": lotes, "reservado": estado.reservado}


# ---- validación de los datos ----


def _agregar(errores, campo, mensaje, codigo):
    """Anota un error de campo (el primero de cada campo manda)."""
    errores.setdefault(campo, [ValidationError(mensaje, code=codigo)])


def _cantidad(valor, unidad, errores, campo, permite_cero=False):
    """Regla «Cantidad válida»: un número mayor que cero (en el recuento, la contada puede ser cero) con los decimales de la unidad. Devuelve
    el ``Decimal`` o ``None`` (y anota el error de ``campo``)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        _agregar(errores, campo, "Ingresá la cantidad.", "obligatorio")
        return None
    if isinstance(valor, (float, bool)):
        _agregar(errores, campo, "Ingresá una cantidad válida.", "cantidad_invalida")
        return None
    try:
        numero = validar_cantidad(valor, unidad)
    except ValidationError as error:
        _agregar(errores, campo, error.messages[0], error.code)
        return None
    if numero < 0 and permite_cero:
        _agregar(errores, campo, "La cantidad contada no puede ser negativa.", "cantidad_negativa")
        return None
    if numero <= 0 and not permite_cero:
        _agregar(errores, campo, "La cantidad tiene que ser mayor que cero.", "cantidad_no_positiva")
        return None
    return numero


def _vencimiento(valor, controla, hoy, errores, campo):
    """Extensiones 7a.3b y 10b.2: si el insumo controla vencimiento, la fecha es obligatoria y no anterior a hoy (lo vencido no ingresa al
    stock). Si no lo controla, no se pide y el lote queda sin fecha."""
    if not controla:
        return None
    if isinstance(valor, str) and valor.strip():
        try:
            valor = datetime.fromisoformat(valor.strip()).date()
        except ValueError:
            valor = None
    if valor is None or valor == "":
        _agregar(errores, campo, "Ingresá la fecha de vencimiento que figura en el envase.", "vencimiento_obligatorio")
        return None
    if valor < hoy:
        _agregar(errores, campo, "Esa fecha ya pasó: lo vencido no ingresa al stock.", "vencimiento_vencido")
        return None
    return valor


def _texto_con_unidad(valor, estado):
    return alertas_de_stock._con_unidad(valor, estado.insumo.unidad_medida_insumo)


def _validar_carga(entrada, estado, errores, prefijo=""):
    """Extensión 7a: la cantidad y el vencimiento de un lote nuevo. Devuelve ``(cantidad, vencimiento)``."""
    unidad = estado.insumo.unidad_medida_insumo
    cantidad = _cantidad(entrada.get("cantidad"), unidad, errores, f"{prefijo}cantidad")
    vencimiento = _vencimiento(
        entrada.get("vencimiento"), estado.insumo.controla_vencimiento, estado.hoy, errores, f"{prefijo}vencimiento"
    )
    return cantidad, vencimiento


def _validar_rotura(entrada, estado, errores):
    """Extensión 7b: un lote con cantidad disponible mayor que cero y una cantidad que no supere lo disponible. Devuelve ``(lote, cantidad)``."""
    unidad = estado.insumo.unidad_medida_insumo
    lote = None
    if entrada.get("lote_id") in (None, ""):
        _agregar(errores, "lote", "Elegí el lote afectado.", "obligatorio")
    else:
        candidato = estado.lotes.get(_entero(entrada.get("lote_id")))
        if candidato is None or candidato.es_faltante_sin_lote or candidato.cantidad_disponible <= 0:
            _agregar(errores, "lote", "Elegí un lote con cantidad disponible.", "lote_invalido")
        else:
            lote = candidato
    cantidad = _cantidad(entrada.get("cantidad"), unidad, errores, "cantidad")
    if lote is not None and cantidad is not None and cantidad > lote.cantidad_disponible:
        _agregar(
            errores,
            "cantidad",
            f"El lote tiene {_texto_con_unidad(lote.cantidad_disponible, estado)} disponibles.",
            "supera_lo_disponible",
        )
        cantidad = None
    return lote, cantidad


# ---- el plan de cada motivo ----


def _plan_de_carga(motivo, entrada, estado, errores, descripcion=""):
    cantidad, vencimiento = _validar_carga(entrada, estado, errores)
    if errores:
        return None
    return Plan(motivo, [], [(cantidad, vencimiento)], descripcion, None, CERO)


def _plan_de_rotura(motivo, entrada, estado, errores, descripcion=""):
    lote, cantidad = _validar_rotura(entrada, estado, errores)
    if errores:
        return None
    return Plan(motivo, [(lote, lote.cantidad_disponible - cantidad)], [], descripcion, None, CERO)


def _plan_de_vencimiento(entrada, estado):
    """Extensión 7c: da de baja todo lo que les queda a los lotes VENCIDOS indicados."""
    vencidos = {
        l.pk: l for l in _comunes(estado) if l.cantidad_disponible > 0 and stock.esta_vencido(l, estado.hoy)
    }
    if not vencidos:  # 7c.1a
        raise _error_general("Este insumo no tiene lotes vencidos con cantidad disponible.", "sin_lotes_vencidos")
    errores = {}
    pedidos = [_entero(i) for i in (entrada.get("lotes") or [])]
    if not pedidos:  # 7c.3a
        _agregar(errores, "lotes", "Indicá al menos un lote vencido.", "sin_lotes")
    elif any(i not in vencidos for i in pedidos):
        _agregar(errores, "lotes", "Solo se dan de baja lotes vencidos con cantidad disponible.", "lote_invalido")
    if errores:
        raise ValidationError(errores)
    return Plan(VENCIMIENTO, [(vencidos[i], CERO) for i in sorted(set(pedidos))], [], "", None, CERO)


def _plan_de_correccion(entrada, estado):
    """Extensión 7d: pasa cantidad de un lote de origen a uno de destino (o al faltante sin lote) sin cambiar el total."""
    unidad = estado.insumo.unidad_medida_insumo
    errores = {}
    origen = destino = None
    if entrada.get("origen_id") in (None, ""):
        _agregar(errores, "origen", "Elegí el lote de origen.", "obligatorio")
    else:
        candidato = estado.lotes.get(_entero(entrada.get("origen_id")))
        if candidato is None or candidato.es_faltante_sin_lote or candidato.cantidad_disponible <= 0:
            _agregar(errores, "origen", "Elegí un lote de origen con cantidad disponible.", "lote_invalido")
        else:
            origen = candidato
    if entrada.get("destino_id") in (None, ""):
        _agregar(errores, "destino", "Elegí el lote de destino.", "obligatorio")
    else:
        destino = estado.lotes.get(_entero(entrada.get("destino_id")))
        if destino is None:
            _agregar(errores, "destino", "Elegí un lote de destino de este insumo.", "lote_invalido")
        elif origen is not None and destino.pk == origen.pk:  # 7d.3a
            _agregar(errores, "destino", "El lote de destino tiene que ser distinto del de origen.", "mismo_lote")
            destino = None
    cantidad = _cantidad(entrada.get("cantidad"), unidad, errores, "cantidad")
    if cantidad is not None and origen is not None and cantidad > origen.cantidad_disponible:  # 7d.3b
        _agregar(
            errores,
            "cantidad",
            f"El lote de origen tiene {_texto_con_unidad(origen.cantidad_disponible, estado)} disponibles.",
            "supera_lo_disponible",
        )
    elif cantidad is not None and destino is not None and destino.es_faltante_sin_lote and cantidad > -destino.cantidad_disponible:
        _agregar(
            errores,
            "cantidad",
            f"El faltante sin lote es de {_texto_con_unidad(-destino.cantidad_disponible, estado)}: no puede quedar positivo.",
            "supera_el_faltante",
        )
    if errores:
        raise ValidationError(errores)
    return Plan(
        CORRECCION,
        [(origen, origen.cantidad_disponible - cantidad), (destino, destino.cantidad_disponible + cantidad)],
        [],
        "",
        None,
        CERO,
    )


def _plan_de_otro(entrada, estado):
    """Extensión 7e: «otro», con descripción obligatoria; si suma, crea un lote nuevo (7a); si resta, descuenta de un lote (7b)."""
    errores = {}
    sentido = entrada.get("sentido")
    if sentido in (None, ""):
        _agregar(errores, "sentido", "Indicá si el ajuste suma o resta stock.", "obligatorio")
    elif sentido not in ("suma", "resta"):
        _agregar(errores, "sentido", "Elegí «suma» o «resta».", "invalido")
    descripcion = (entrada.get("descripcion") or "").strip() if isinstance(entrada.get("descripcion"), (str, type(None))) else ""
    if not descripcion:
        _agregar(errores, "descripcion", "Contá qué pasó.", "obligatorio")
    if "sentido" in errores:
        raise ValidationError(errores)
    detalle = _plan_de_carga if sentido == "suma" else _plan_de_rotura
    plan = detalle(OTRO, entrada, estado, errores, descripcion)
    if errores:
        raise ValidationError(errores)
    return plan


def _plan_de_recuento(entrada, estado):
    """Pasos 8 a 12 y extensiones 10a, 10b y 12a: el recuento es de todo el insumo y por lote. Se indican solo los lotes que difieren; el
    faltante sin lote queda siempre en cero; lo que se encuentra sin lote registrado es un lote nuevo."""
    unidad = estado.insumo.unidad_medida_insumo
    errores = {}
    comunes = {l.pk: l for l in _comunes(estado)}
    cambios = []
    for clave, valor in (entrada.get("contados") or {}).items():
        lote = comunes.get(_entero(clave))
        if lote is None:
            _agregar(errores, "contados", "Solo se cuentan lotes registrados de este insumo.", "lote_invalido")
            continue
        contada = _cantidad(valor, unidad, errores, f"contado_{lote.pk}", permite_cero=True)
        if contada is None or contada == lote.cantidad_disponible:
            continue
        if contada > lote.cantidad_disponible and stock.esta_vencido(lote, estado.hoy):
            _agregar(errores, f"contado_{lote.pk}", "No se puede contar más de lo registrado: lo vencido no ingresa al stock.", "lote_vencido_no_sube")
            continue
        cambios.append((lote, contada))
    nuevos = []
    for n, item in enumerate(entrada.get("nuevos") or []):
        cantidad, vencimiento = _validar_carga(item, estado, errores, prefijo=f"nuevo_{n}_")
        if cantidad is not None and f"nuevo_{n}_vencimiento" not in errores:
            nuevos.append((cantidad, vencimiento))
    if errores:
        raise ValidationError(errores)
    faltante = _faltante_de(estado)
    a_cero = -faltante.cantidad_disponible if faltante is not None and faltante.cantidad_disponible < 0 else CERO
    if not cambios and not nuevos and a_cero == 0:  # 12a
        raise _error_general("No hay nada que ajustar: el recuento coincide con lo registrado.", "sin_diferencias")
    cambios.sort(key=lambda par: par[0].pk)
    descripcion = (entrada.get("descripcion") or "").strip()
    return Plan(RECUENTO, cambios, nuevos, descripcion, faltante if a_cero else None, a_cero)


def _planificar(motivo, entrada, estado):
    """Valida ``entrada`` según ``motivo`` y devuelve el ``Plan`` (``ValidationError`` con un error por campo si hay datos inválidos)."""
    if motivo in (None, ""):
        raise ValidationError({"motivo": [ValidationError("Elegí el motivo del ajuste.", code="obligatorio")]})
    if motivo not in CODIGOS_DE_MOTIVO:
        raise ValidationError({"motivo": [ValidationError("Elegí uno de los motivos de la lista.", code="invalido")]})
    errores = {}
    if motivo == RECUENTO:
        return _plan_de_recuento(entrada, estado)
    if motivo == CARGA_INICIAL:
        plan = _plan_de_carga(motivo, entrada, estado, errores, (entrada.get("descripcion") or "").strip())
    elif motivo == ROTURA:
        plan = _plan_de_rotura(motivo, entrada, estado, errores, (entrada.get("descripcion") or "").strip())
    elif motivo == VENCIMIENTO:
        return _plan_de_vencimiento(entrada, estado)
    elif motivo == CORRECCION:
        return _plan_de_correccion(entrada, estado)
    else:
        return _plan_de_otro(entrada, estado)
    if errores:
        raise ValidationError(errores)
    return plan


# ---- el resumen del paso 12 ----


def _resumen(plan, estado, huella):
    """El resumen del paso 12: los lotes que cambian, los lotes nuevos, el faltante que queda en cero, el stock antes y después y el valor."""
    antes = sum((l.cantidad_disponible for l in estado.lotes.values()), CERO)
    cambios = [
        CambioDeLote(lote, lote.cantidad_disponible, nueva, nueva - lote.cantidad_disponible) for lote, nueva in plan.cambios
    ]
    nuevos = [LoteNuevo(cantidad, vencimiento) for cantidad, vencimiento in plan.nuevos]
    con_valor = plan.motivo != CORRECCION
    diferencia = (
        sum((c.diferencia for c in cambios), CERO) + sum((n.cantidad for n in nuevos), CERO) + plan.faltante_a_cero
        if con_valor
        else CERO
    )
    valor = (diferencia * estado.iin.referencia_precio).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    # Extensión 12b: el stock vigente (sin lotes vencidos) que quedaría, contra las reservas activas.
    despues = {l.pk: l.cantidad_disponible for l in estado.lotes.values()}
    despues.update({lote.pk: nueva for lote, nueva in plan.cambios})
    if plan.faltante is not None:
        despues[plan.faltante.pk] = CERO
    vigente = sum((despues[l.pk] for l in estado.lotes.values() if not stock.esta_vencido(l, estado.hoy)), CERO) + sum(
        (n.cantidad for n in nuevos), CERO
    )
    advertencia = None
    if vigente < estado.reservado:
        ordenes = stock.ordenes_sin_cobertura(estado.iin.pk, estado.hoy, vigente=vigente)
        advertencia = Advertencia(ordenes, vigente, estado.reservado)
    return Resumen(cambios, nuevos, plan.faltante_a_cero, antes, antes + diferencia, diferencia, valor, con_valor, advertencia, huella)


# ---- lectura para la pantalla (pasos 4 a 6) ----


def situacion_del_insumo(actor, invernadero_id, insumo_id):
    """Pasos 4 a 6 del CU, para la pantalla: el stock actual, los lotes (con stock primero, por vencimiento; después los agotados y por último el
    faltante sin lote), el faltante, el precio de referencia, si controla vencimiento y los motivos. Solo lectura. Incluye la existencia ACTIVA de
    una semilla dada de baja con su variedad. Mismas precondiciones que ``calcular_ajuste``."""
    estado = _leer(actor, invernadero_id, insumo_id)
    dias_de_aviso = configuracion.obtener().dias_aviso_vencimiento
    comunes = _comunes(estado)
    con_stock = sorted(
        (l for l in comunes if l.cantidad_disponible > 0),
        key=lambda l: (l.fecha_vencimiento is None, l.fecha_vencimiento or estado.hoy, l.fecha_ingreso, l.pk),
    )
    ordenados = con_stock + sorted((l for l in comunes if l.cantidad_disponible <= 0), key=lambda l: l.pk)
    faltante = _faltante_de(estado)
    if faltante is not None:
        ordenados.append(faltante)
    lotes = [
        insumos_invernadero.LoteConEstado(l, insumos_invernadero._estado_del_lote(l, estado.hoy, dias_de_aviso)) for l in ordenados
    ]
    return Situacion(
        estado.iin,
        estado.insumo,
        sum((l.cantidad_disponible for l in estado.lotes.values()), CERO),
        lotes,
        faltante,
        estado.iin.referencia_precio,
        estado.insumo.controla_vencimiento,
        MOTIVOS,
    )


# ---- calcular (no escribe) ----


def calcular_ajuste(actor, invernadero_id, insumo_id, motivo, entrada):
    """Pasos 7 a 12 de CMP-AJT-STK: valida ``entrada`` según ``motivo`` y devuelve el ``Resumen`` con la huella del estado que usó. NO escribe, no
    bloquea y no audita. Un dato inválido es un ``ValidationError`` con un error por campo (``docs/…/ajustes_comunes``): ``motivo``, ``cantidad``,
    ``vencimiento``, ``lote``, ``lotes``, ``origen``, ``destino``, ``sentido``, ``descripcion``, ``contado_<id>``, ``nuevo_<n>_cantidad`` y
    ``nuevo_<n>_vencimiento``, o general."""
    entrada = entrada or {}
    estado = _leer(actor, invernadero_id, insumo_id)
    plan = _planificar(motivo, entrada, estado)
    huella, _ = _huella(motivo, entrada, estado)
    return _resumen(plan, estado, huella)


# ---- confirmar (paso 14) ----


def _escribir(actor, plan, estado, resumen):
    """Paso 14: actualiza los lotes, crea los nuevos, deja en cero el faltante y registra UN movimiento por lote que cambió. Devuelve
    ``(movimientos, lotes_nuevos, lotes_tocados)``. Se llama con todo bloqueado y releído."""
    ahora = timezone.now()
    movimientos, tocados, nuevos = [], [], []
    motivo = MOTIVO_DEL_MOVIMIENTO.get(plan.motivo)

    def crear(lote, tipo, cantidad, origen_id=None, ajuste=True):
        movimientos.append(
            MovimientoInsumo.objects.create(
                lote_insumo=lote,
                fecha=ahora,
                cantidad=cantidad,
                tipo_movimiento=tipo,
                motivo_ajuste=motivo if ajuste else None,
                descripcion_ajuste=plan.descripcion if ajuste else "",
                origen_id=origen_id,
            )
        )
        return movimientos[-1]

    if plan.motivo == CORRECCION:
        (origen, nueva_origen), (destino, nueva_destino) = plan.cambios
        cantidad = origen.cantidad_disponible - nueva_origen
        origen.cantidad_disponible = nueva_origen
        origen.save(update_fields=["cantidad_disponible"])
        destino.cantidad_disponible = nueva_destino
        destino.save(update_fields=["cantidad_disponible"])
        salida = crear(origen, Mov.SALIDA_POR_CORRECCION, cantidad, ajuste=False)
        crear(destino, Mov.ENTRADA_POR_CORRECCION, cantidad, origen_id=salida.pk, ajuste=False)  # R016: se origina en su salida
        return movimientos, nuevos, [origen, destino]
    for lote, nueva in plan.cambios:
        diferencia = nueva - lote.cantidad_disponible
        lote.cantidad_disponible = nueva
        lote.save(update_fields=["cantidad_disponible"])
        crear(lote, Mov.AJUSTE_POSITIVO if diferencia > 0 else Mov.AJUSTE_NEGATIVO, abs(diferencia))
        tocados.append(lote)
    for cantidad, vencimiento in plan.nuevos:
        nuevo = LoteInsumo.objects.create(
            insumo_invernadero=estado.iin,
            cantidad_ingresada=cantidad,
            cantidad_disponible=cantidad,
            fecha_ingreso=estado.hoy,
            fecha_vencimiento=vencimiento,
        )
        crear(nuevo, Mov.AJUSTE_POSITIVO, cantidad)
        nuevos.append(nuevo)
        tocados.append(nuevo)
    if plan.faltante is not None:  # postcondición c: el faltante sin lote queda en cero
        plan.faltante.cantidad_disponible = CERO
        plan.faltante.save(update_fields=["cantidad_disponible"])
        crear(plan.faltante, Mov.AJUSTE_POSITIVO, plan.faltante_a_cero)
        tocados.append(plan.faltante)
    return movimientos, nuevos, tocados


def _inconsistente_activa(iin):
    return Alerta.objects.filter(
        invernadero_id=iin.invernadero_id,
        tipo_alerta=tipos_de_alerta.STOCK_INCONSISTENTE,
        clave_estado=f"insumo:{iin.pk}",
        estado_alerta=Alerta.Estado.ACTIVA,
    ).exists()


def confirmar_ajuste(actor, invernadero_id, insumo_id, motivo, entrada, huella):
    """Pasos 13 a 15 de CMP-AJT-STK: bloquea, recalcula, compara la ``huella`` y escribe todo en una sola transacción. Devuelve el ``Resultado``.

    - Orden de bloqueos: invernadero (contrato de D-40) → existencia → lotes (todos, en orden de id).
    - Extensión 14a: si la huella ya no coincide (un lote que usó, el faltante o las reservas cambiaron), ``AjusteDesactualizado`` sin cambiar nada.
      Se compara ANTES de validar: un dato que dejó de ser válido porque el estado cambió es un desactualizado, no un error de la persona.
    - Postcondiciones a a d y g; reevalúa las alertas (h, i, j, 12b) y audita un registro ``ajuste_stock`` (k, l y m).
    """
    entrada = entrada or {}
    _exigir_agronomo(actor)
    get_object_or_404(Invernadero, pk=invernadero_id)
    get_object_or_404(Insumo, pk=insumo_id)
    with transaction.atomic():
        invernadero = insumos_invernadero._bloquear_para(actor, invernadero_id)
        iin = (
            InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",))
            .select_related("insumo")
            .filter(insumo_id=insumo_id, invernadero_id=invernadero_id)
            .first()
        )
        _exigir_habilitado(iin)
        lotes = list(LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero=iin).order_by("id"))
        estado = _estado(iin, lotes)
        actual, vigente = _huella(motivo, entrada, estado)
        if actual != huella:
            raise AjusteDesactualizado(vigente)
        plan = _planificar(motivo, entrada, estado)
        resumen = _resumen(plan, estado, actual)
        antes_inconsistente = _inconsistente_activa(iin)
        movimientos, nuevos, tocados = _escribir(actor, plan, estado, resumen)
        reevaluacion = alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk, estado.hoy)
        despues_inconsistente = _inconsistente_activa(iin)
        unidad = estado.insumo.unidad_medida_insumo
        detalle = {}
        if resumen.diferencia != 0:  # D-36: antes igual a después se rechaza (una corrección no cambia el stock)
            detalle["cambios"] = {
                "stock": {
                    "antes": texto_cantidad(resumen.stock_antes, unidad),
                    "despues": texto_cantidad(resumen.stock_despues, unidad),
                }
            }
        datos = {
            "insumo": referencia(estado.insumo),
            "motivo_ajuste": plan.motivo,
            "lotes": [referencia(l) for l in tocados],
            "movimientos": [referencia(m) for m in movimientos],
        }
        if plan.descripcion:
            datos["descripcion_ajuste"] = plan.descripcion
        datos.update(insumos_invernadero._datos_de_alertas({}, reevaluacion))
        detalle["datos"] = datos
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.AJUSTE_STOCK,
            afectados=[iin, invernadero],
            detalle=detalle,
        )
        stock_actual = stock.stock_actual_de([iin.pk])[iin.pk]
    if despues_inconsistente:
        inconsistente = "activa"
    else:
        inconsistente = "resuelta" if antes_inconsistente else None
    return Resultado(
        resumen, movimientos, nuevos, stock_actual, reevaluacion.creadas, reevaluacion.resueltas, inconsistente
    )
