# Puntos de extensión de `inventario` (INV-01, regla A4 de D-37; contrato en docs/api/extensiones_de_inventario.md).
# Patrón: Variaciones protegidas con Indirección (Larman), el mismo de ``maestros/extensiones.py``. `inventario` es de nivel 4 y
# no puede importar `produccion` (reservas y órdenes) ni `compras` (órdenes de compra, pedidos): ellas se registran acá desde su
# ``AppConfig.ready()`` y `inventario` les pregunta lo que necesita saber, sin conocerlas.
#
# Sin registrantes, cada punto da su resultado neutro: nada reservado, ninguna orden y ningún impedimento de las apps altas.
# Se prueban con registrantes falsos (``mock.patch.object`` sobre las listas de módulo, o ``reservas_de_prueba`` de
# ``inventario/tests/fabricas.py``).
#
# CONTRATO (se repite en docs/api/extensiones_de_inventario.md):
#   - Todo corre DENTRO de la transacción del servicio de `inventario`, después de que este tomó el invernadero y sus propias
#     filas (orden de docs/patrones/stock.md, sección 5). Un registrante que bloquee filas propias lo hace después, en orden de id.
#   - Reciben LISTAS de ids y devuelven diccionarios por id: una consulta por tabla para toda la lista, nunca una por fila.

from collections import defaultdict, namedtuple
from decimal import Decimal

from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad
from maestros.extensiones import Impedimento

# Una orden que reserva insumo (docs/api/extensiones_de_inventario.md): para nombrarla en los avisos y en «sin cobertura».
OrdenQueReserva = namedtuple("OrdenQueReserva", "orden_id texto cantidad fecha_programada url")

# Códigos de los impedimentos propios de `inventario` (los de los registrantes traen los suyos).
STOCK_DISTINTO_DE_CERO = "stock_distinto_de_cero"
RESERVAS_ACTIVAS = "reservas_activas"
CANTIDAD_EN_TRANSITO = "cantidad_en_transito"

# Registrantes. Listas de módulo: las pruebas las reemplazan con ``mock.patch.object``.
_RESERVAS = []
_ORDENES_QUE_RESERVAN = []
_IMPEDIMENTOS_DE_DESHABILITACION = []


def registrar_reservas_de_insumo(funcion):
    """Registra ``funcion(ids) -> dict[int, Decimal]``: por ``InsumoInvernadero``, lo reservado por las ``ReservaInsumo``
    ACTIVAS; lo que no figura es 0. Lo registra `produccion` (PRD-01)."""
    _RESERVAS.append(funcion)
    return funcion


def reservado_de(iin_ids):
    """``{id: Decimal}`` con lo reservado de cada ``InsumoInvernadero`` de ``iin_ids``, sumando todos los registrantes (sin
    ninguno, 0 para cada id). Una llamada por registrante, no por fila."""
    ids = list(iin_ids)
    total = {i: Decimal("0") for i in ids}
    for funcion in list(_RESERVAS):
        for i, cantidad in funcion(ids).items():
            if i in total:
                total[i] += Decimal(cantidad)
    return total


def registrar_ordenes_que_reservan(funcion):
    """Registra ``funcion(ids) -> dict[int, list[OrdenQueReserva]]``: las órdenes que reservan cada ``InsumoInvernadero``. Lo
    registra `produccion`."""
    _ORDENES_QUE_RESERVAN.append(funcion)
    return funcion


def ordenes_que_reservan(iin_ids):
    """``{id: [OrdenQueReserva, ...]}`` de todos los registrantes, ordenadas por fecha programada y después por id de orden
    (las ordena `inventario`); sin registrantes, una lista vacía por id."""
    ids = list(iin_ids)
    juntas = defaultdict(list)
    for funcion in list(_ORDENES_QUE_RESERVAN):
        for i, ordenes in funcion(ids).items():
            if i in ids:
                juntas[i].extend(ordenes)
    return {i: sorted(juntas[i], key=lambda orden: (orden.fecha_programada, orden.orden_id)) for i in ids}


def registrar_impedimento_de_deshabilitacion(funcion):
    """Registra ``funcion(insumo_invernadero) -> list[Impedimento]``: lo que, en su app, impide deshabilitar el insumo en el
    invernadero (códigos ``orden_de_compra_aprobada`` y ``pedido_en_curso``). Lo registra `compras` (ronda futura)."""
    _IMPEDIMENTOS_DE_DESHABILITACION.append(funcion)
    return funcion


def impedimentos_de_deshabilitacion(insumo_invernadero):
    """Todos los impedimentos de deshabilitar ``insumo_invernadero``, JUNTOS (no se queda con el primero): los propios
    (stock distinto de cero, reservas activas, cantidad en tránsito) y los de los registrantes. Los usan CMP-DSH-IIN,
    CMP-BAJ-INS y la baja del invernadero. Una sola consulta de stock y de reservas por llamada."""
    unidad = insumo_invernadero.insumo.unidad_medida_insumo
    nombre = insumo_invernadero.insumo.nombre_insumo
    impedimentos = []
    actual = stock.stock_actual_de([insumo_invernadero.pk])[insumo_invernadero.pk]
    if actual != 0:
        impedimentos.append(
            Impedimento(
                STOCK_DISTINTO_DE_CERO,
                f"{nombre} tiene {'stock negativo' if actual < 0 else 'stock'} ({texto_cantidad(actual, unidad)}).",
                "Usá el stock o llevalo a cero con un ajuste.",
            )
        )
    reservado = reservado_de([insumo_invernadero.pk])[insumo_invernadero.pk]
    if reservado > 0:
        impedimentos.append(
            Impedimento(
                RESERVAS_ACTIVAS,
                f"{nombre} tiene {texto_cantidad(reservado, unidad)} reservados por órdenes a realizar.",
                "Concretá o cancelá las órdenes que lo reservan.",
            )
        )
    if insumo_invernadero.cant_transito_insumo > 0:
        impedimentos.append(
            Impedimento(
                CANTIDAD_EN_TRANSITO,
                f"{nombre} tiene {texto_cantidad(insumo_invernadero.cant_transito_insumo, unidad)} en tránsito.",
                "Recibí la mercadería o cerrá la orden de compra.",
            )
        )
    for funcion in list(_IMPEDIMENTOS_DE_DESHABILITACION):
        impedimentos.extend(funcion(insumo_invernadero))
    return impedimentos
