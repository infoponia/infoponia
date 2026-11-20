# Puntos de extensión de core para las apps de negocio (MAE-02b, D-43; regla A4 de D-37). ``core`` es de nivel 1 y no puede
# importar las apps altas: ellas se registran acá desde su ``AppConfig.ready()`` y ``core`` les pregunta lo que necesita
# sin conocerlas. Patrón: Variaciones protegidas con Indirección (Larman), el mismo de ``core/menu.py`` y
# ``maestros/extensiones.py``.
#
# Cuatro puntos (la identidad de la organización y las fuentes de la campana van aparte, al final):
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


# ---- Identidad de la organización (UI-01, D-48) ----
# Quinto punto, aparte de los cuatro de D-43: ``PerfilOrganizacion`` vive en ``maestros`` (nivel 3) y ``core`` (nivel 1)
# no puede importarlo (regla A1 de D-37). ``maestros`` registra en ``ready()`` una función que devuelve el perfil
# guardado (lo hace MAE-04); ``core`` la consulta sin conocerla.

# El nombre y el color principal (``#RRGGBB`` o vacío) de la organización.
Identidad = namedtuple("Identidad", "nombre color_principal")

_IDENTIDAD = []


def registrar_identidad_de_la_organizacion(funcion):
    """Registra ``funcion() -> Identidad | None``: la identidad guardada de la organización. Idempotente. Se admite un
    solo registrante útil: ``identidad_registrada`` usa el primero."""
    return _registrar(_IDENTIDAD, funcion)


def identidad_registrada():
    """La ``Identidad`` del primer registrante, o ``None`` si no hay registrante o no devuelve nada."""
    for funcion in list(_IDENTIDAD):
        return funcion()
    return None


# ---- Campana: fuentes de alertas y contadores de pendientes del Gerente (NOT-01, D-42) ----
# Dos puntos más, aparte de los cuatro de D-43: ``Alerta`` vive en ``maestros`` (D-38) y ``core`` no puede importarlo
# (regla A1 de D-37). Cada app registra en ``AppConfig.ready()`` de dónde salen sus alertas para la campana y lo que
# espera una resolución del Gerente. Contrato completo: docs/api/notificaciones.md.

# Una alerta activa tal como la muestra la campana. ``severidad``: ``critica``, ``advertencia`` o ``informativa``;
# ``url``: adónde lleva (la ficha del invernadero); ``leida``: si el destinatario ya la abrió (regla 7 de 8.18).
ItemDeAlerta = namedtuple("ItemDeAlerta", "severidad titulo detalle url leida")

# Orden de la campana: lo más urgente arriba (el prototipo, ``alertas``: crítica, advertencia, informativa). Una
# severidad que no figura va al final.
ORDEN_DE_SEVERIDAD = {"critica": 0, "advertencia": 1, "informativa": 2}

_FUENTES_DE_ALERTAS = []
_CONTADORES_DE_PENDIENTES = []


def registrar_fuente_de_alertas(funcion):
    """Registra ``funcion(usuario) -> list[ItemDeAlerta]``: las alertas activas de ``usuario`` en su app (todas las que
    recibe, leídas o no). Solo lectura. Idempotente."""
    return _registrar(_FUENTES_DE_ALERTAS, funcion)


def alertas_para(usuario):
    """Las alertas de todas las fuentes para ``usuario``, ordenadas por severidad (crítica, advertencia, informativa) y,
    dentro de cada nivel, en el orden en que las dio cada fuente y en el de registro de las fuentes (el orden de Python
    es estable)."""
    items = []
    for funcion in list(_FUENTES_DE_ALERTAS):
        items.extend(funcion(usuario))
    return sorted(items, key=lambda item: ORDEN_DE_SEVERIDAD.get(item.severidad, len(ORDEN_DE_SEVERIDAD)))


def registrar_contador_de_pendientes(funcion):
    """Registra ``funcion() -> list[tuple[str, int]]``: lo que, en su app, espera una resolución del Gerente, como
    ``(descripción, cantidad)``; sin nada pendiente, lista vacía (D-14). Idempotente."""
    return _registrar(_CONTADORES_DE_PENDIENTES, funcion)


def contadores_de_pendientes():
    """Los ``(descripción, cantidad)`` de todos los registrantes, juntos y en el orden de registro. Los suma
    ``core.notificaciones.pendientes_del_gerente``."""
    juntos = []
    for funcion in list(_CONTADORES_DE_PENDIENTES):
        juntos.extend(funcion())
    return juntos
