# Puntos de extensión de maestros para el invernadero (MAE-01b, regla A4 de D-37; modelo de dominio, ronda 22).
# Patrón: Variaciones protegidas con Indirección (Larman). ``maestros`` es de nivel 3 y no puede importar las apps altas
# (``produccion``, ``inventario``, ``iot``, ``compras``, ``comercial``): ellas se registran acá desde su
# ``AppConfig.ready()`` y ``maestros`` les pregunta lo que necesita saber, sin conocerlas.
#
# Hoy no hay ninguna app registrada: sin registrantes, cada condición se da por cumplida (y se prueba con registrantes
# falsos). Cada app alta se registra en ``AppConfig.ready()`` de la forma:
#     from maestros import extensiones
#     extensiones.registrar_impedimento_de_baja(impedimentos_lotes)
#     extensiones.registrar_efecto_de_baja(pasar_lotes_a_inactivos)
#     extensiones.registrar_traspaso(contar_ordenes, traspasar_ordenes)
#
# Hay tres puntos:
#   1. Impedimentos de la baja (PROD-BAJ-INV, precondiciones c a f y h).
#   2. Efectos de la baja (postcondiciones b y c y los logs por sector e insumo de la f).
#   3. Traspaso por cambio de personal (PROD-MOD-INV, regla 2 y postcondiciones b y c).
#
# CONTRATO (se repite en docs/patrones/bloqueos.md):
#   - Todo corre dentro de la transacción del servicio, después de que el servicio tomó sus bloqueos.
#   - Un registrante que bloquee filas propias lo hace después del invernadero y en orden de id.
#   - Quien crea algo que impide la baja (lote activo, orden a realizar, partida disponible, stock, tránsito u orden de
#     compra aprobada, transportista activo, sistema IoT activo), o lo vuelve a poner en ese estado, llama a
#     ``maestros.servicios.invernaderos.bloquear_invernadero_activo`` dentro de su transacción y antes de crearlo. La FK
#     sola no alcanza: el INSERT toma FOR KEY SHARE sobre el invernadero, que no choca con el FOR NO KEY UPDATE de la baja.

from collections import namedtuple

# Un impedimento de la baja: un código estable, qué pasa y cómo resolverlo (regla 2 de PROD-BAJ-INV).
Impedimento = namedtuple("Impedimento", "codigo texto como_resolver")

# Registrantes. Listas de módulo: las pruebas las reemplazan con ``mock.patch.object``.
_IMPEDIMENTOS = []
_EFECTOS_DE_BAJA = []
_TRASPASOS = []  # pares (contar, traspasar)


def registrar_impedimento_de_baja(funcion):
    """Registra ``funcion(invernadero) -> list[Impedimento]``: lo que, en su app, impide dar de baja ese invernadero
    (lotes activos, órdenes a realizar, partidas en cámara, stock, tránsito u orden de compra aprobada, sistema IoT
    activo). Devuelve una lista vacía si no hay nada. Se llama con el invernadero ya bloqueado."""
    _IMPEDIMENTOS.append(funcion)
    return funcion


def impedimentos_de_baja(invernadero):
    """Los impedimentos de todos los registrantes, juntos (regla 2 de PROD-BAJ-INV: no se queda con el primero)."""
    juntos = []
    for funcion in list(_IMPEDIMENTOS):
        juntos.extend(funcion(invernadero))
    return juntos


def registrar_efecto_de_baja(funcion):
    """Registra ``funcion(actor, invernadero)``: pasa a inactivo lo suyo (sectores, insumos habilitados) y audita sus
    propios logs, uno por sector e insumo (postcondición f de PROD-BAJ-INV). Corre dentro de la transacción de la baja,
    con el invernadero bloqueado y ya inactivo."""
    _EFECTOS_DE_BAJA.append(funcion)
    return funcion


def aplicar_efectos_de_baja(actor, invernadero):
    """Corre los efectos de todos los registrantes."""
    for funcion in list(_EFECTOS_DE_BAJA):
        funcion(actor, invernadero)


def registrar_traspaso(contar, traspasar):
    """Registra ``contar(invernadero, rol, saliente, entrante) -> list[(descripcion, cantidad)]`` y
    ``traspasar(actor, invernadero, rol, saliente, entrante)``. ``rol`` es el atributo del invernadero (``"capataz"``);
    ``saliente`` y ``entrante`` son cuentas de la clase del rol, o ``None`` (rol sin responsable, o rol vacío).
    ``contar`` no cambia nada; ``traspasar`` pasa lo del saliente al entrante en ese invernadero (MD-60)."""
    _TRASPASOS.append((contar, traspasar))


def contar_traspaso(invernadero, rol, saliente, entrante):
    """Lo que recibiría la persona entrante, de todos los registrantes: lista de ``(descripcion, cantidad)``."""
    recibe = []
    for contar, _ in list(_TRASPASOS):
        recibe.extend(contar(invernadero, rol, saliente, entrante))
    return recibe


def traspasar(actor, invernadero, rol, saliente, entrante):
    """Traspasa lo del saliente al entrante en ese invernadero (postcondición b de PROD-MOD-INV)."""
    for _, traspasar_uno in list(_TRASPASOS):
        traspasar_uno(actor, invernadero, rol, saliente, entrante)
