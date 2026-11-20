# Puntos de extensión de core para las apps de negocio (MAE-02b, D-43; regla A4 de D-37). ``core`` es de nivel 1 y no puede
# importar las apps altas: ellas se registran acá desde su ``AppConfig.ready()`` y ``core`` les pregunta lo que necesita
# sin conocerlas. Patrón: Variaciones protegidas con Indirección (Larman), el mismo de ``core/menu.py`` y
# ``maestros/extensiones.py``.
#
# Cuatro puntos:
#   1. Efectos de la baja de una cuenta (postcondición e y regla 4 de USR-BAJ-USR; MD-61).
#   2. Efectos de la reactivación de una cuenta (postcondición c de USR-MOD-USR; D8).
#   3. Lo que la cuenta tiene asignado, para informarlo en la ventana de baja (regla 4 de USR-BAJ-USR).
#   4. Secciones del Inicio (regla 5 de PROD-CNS-INV).
#
# CONTRATO (se repite en docs/patrones/bloqueos.md):
#   - Los efectos corren dentro de la transacción del servicio, DESPUÉS de que este bloqueó las cuentas (orden de D-30,
#     D-32 y D-40: las cuentas primero, después lo de las apps altas). Siempre ``FOR NO KEY UPDATE``.
#   - Un registrante que bloquee filas propias lo hace en orden de id y nunca bloquea una cuenta después de lo suyo.
#   - Cada ``registrar_*`` es idempotente: ``ready()`` puede correr más de una vez.
#   - Un efecto devuelve un ``Efecto``: las instancias que quedan como afectadas en la auditoría y los ``datos`` (D-36)
#     que suma al detalle, como ``{clave: lista de referencias}``.

from collections import namedtuple

# Lo que hizo un efecto: las instancias afectadas y los ``datos`` que suma al detalle de la auditoría.
Efecto = namedtuple("Efecto", "afectados datos")
# Algo que la cuenta tiene asignado (regla 4 de USR-BAJ-USR): qué es, cuántos y qué pasará con eso.
Asignacion = namedtuple("Asignacion", "texto cantidad que_pasa")
# Una sección del Inicio: la plantilla a incluir y su contexto (en la plantilla, ``datos``).
SeccionDeInicio = namedtuple("SeccionDeInicio", "plantilla contexto")

# Registrantes. Listas de módulo: las pruebas las reemplazan con ``mock.patch.object``.
_EFECTOS_DE_BAJA_DE_CUENTA = []
_EFECTOS_DE_REACTIVACION_DE_CUENTA = []
_ASIGNACIONES_DE_CUENTA = []
_SECCIONES_DE_INICIO = []


def _registrar(registrantes, funcion):
    """Agrega ``funcion`` a ``registrantes`` si todavía no está (idempotente) y la devuelve."""
    if funcion not in registrantes:
        registrantes.append(funcion)
    return funcion


def _juntar(efectos):
    """Un solo ``Efecto`` con los afectados (sin repetir una misma instancia) y los ``datos`` de todos: las listas de una
    misma clave se concatenan, en el orden de registro."""
    afectados, datos = [], {}
    for efecto in efectos:
        for objeto in efecto.afectados:
            if all((type(objeto), objeto.pk) != (type(otro), otro.pk) for otro in afectados):
                afectados.append(objeto)
        for clave, valores in efecto.datos.items():
            datos.setdefault(clave, []).extend(valores)
    return Efecto(afectados, datos)


def registrar_efecto_de_baja_de_cuenta(funcion):
    """Registra ``funcion(actor, cuenta) -> Efecto``: lo que, en su app, pasa cuando se da de baja ``cuenta`` (ya
    inactiva y bloqueada). Idempotente."""
    return _registrar(_EFECTOS_DE_BAJA_DE_CUENTA, funcion)


def aplicar_efectos_de_baja_de_cuenta(actor, cuenta):
    """Corre los efectos de todos los registrantes y devuelve un ``Efecto`` con los afectados y los ``datos`` juntos."""
    return _juntar([funcion(actor, cuenta) for funcion in list(_EFECTOS_DE_BAJA_DE_CUENTA)])


def registrar_efecto_de_reactivacion_de_cuenta(funcion):
    """Registra ``funcion(actor, cuenta) -> Efecto``: lo que pasa cuando se reactiva ``cuenta`` (ya activa y
    bloqueada). Idempotente."""
    return _registrar(_EFECTOS_DE_REACTIVACION_DE_CUENTA, funcion)


def aplicar_efectos_de_reactivacion_de_cuenta(actor, cuenta):
    """Corre los efectos de todos los registrantes y devuelve un ``Efecto`` con los afectados y los ``datos`` juntos."""
    return _juntar([funcion(actor, cuenta) for funcion in list(_EFECTOS_DE_REACTIVACION_DE_CUENTA)])


def registrar_asignaciones_de_cuenta(funcion):
    """Registra ``funcion(cuenta) -> list[Asignacion]``: lo que la cuenta tiene asignado en su app. Solo lectura: no
    bloquea ni cambia nada. Idempotente."""
    return _registrar(_ASIGNACIONES_DE_CUENTA, funcion)


def asignaciones_de_cuenta(cuenta):
    """Las asignaciones de todos los registrantes, juntas y en el orden de registro."""
    asignaciones = []
    for funcion in list(_ASIGNACIONES_DE_CUENTA):
        asignaciones.extend(funcion(cuenta))
    return asignaciones


def registrar_seccion_de_inicio(funcion):
    """Registra ``funcion(usuario) -> SeccionDeInicio | None``: una sección del Inicio de ``usuario`` (``None`` si no le
    corresponde). Idempotente."""
    return _registrar(_SECCIONES_DE_INICIO, funcion)


def secciones_de_inicio(usuario):
    """Las secciones de todos los registrantes que devuelven una, en el orden de registro."""
    secciones = (funcion(usuario) for funcion in list(_SECCIONES_DE_INICIO))
    return [seccion for seccion in secciones if seccion is not None]
