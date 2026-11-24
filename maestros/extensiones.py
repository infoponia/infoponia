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
# MAE-03 suma los puntos de sectores y cultivos (al final de este archivo). Los de invernadero son tres:
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

from django.core.exceptions import ImproperlyConfigured

# Un impedimento de la baja: un código estable, qué pasa y cómo resolverlo (regla 2 de PROD-BAJ-INV). ``url`` (CMP-02b, opcional) lleva a lo que lo
# impide, por ejemplo la ficha del pedido en curso: las ventanas la muestran como «Ver detalle». Los que se construyen con tres valores quedan en ``None``.
Impedimento = namedtuple("Impedimento", "codigo texto como_resolver url", defaults=(None,))

# Registrantes. Listas de módulo: las pruebas las reemplazan con ``mock.patch.object``.
_IMPEDIMENTOS = []
_EFECTOS_DE_BAJA = []
_TRASPASOS = []  # pares (contar, traspasar)
_AVISOS_DE_TRASPASO = []


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
    ``contar`` no cambia nada; ``traspasar`` pasa lo del saliente al entrante en ese invernadero (MD-60) y devuelve la lista de
    instancias que tocó (o ``None``) para que quede en la auditoría (PRD-01)."""
    _TRASPASOS.append((contar, traspasar))


def contar_traspaso(invernadero, rol, saliente, entrante):
    """Lo que recibiría la persona entrante, de todos los registrantes: lista de ``(descripcion, cantidad)``."""
    recibe = []
    for contar, _ in list(_TRASPASOS):
        recibe.extend(contar(invernadero, rol, saliente, entrante))
    return recibe


def registrar_aviso_de_traspaso(funcion):
    """Registra ``funcion(invernadero, rol, saliente, entrante) -> list[str]`` (CMP-02b): lo que se CANCELA o se pierde al cambiar a la persona del rol, para
    la ventana de la regla 2 de PROD-MOD-INV. A diferencia de ``contar`` (lo que RECIBE quien entra), se informa aunque no haya entrante y no va a la
    notificación de quien entra. Solo lectura. Lo registra `compras` (los pedidos del Agrónomo saliente)."""
    _AVISOS_DE_TRASPASO.append(funcion)
    return funcion


def avisos_de_traspaso(invernadero, rol, saliente, entrante):
    """Los textos de todos los registrantes, juntos y en el orden de registro (sin registrantes, lista vacía)."""
    textos = []
    for funcion in list(_AVISOS_DE_TRASPASO):
        textos.extend(funcion(invernadero, rol, saliente, entrante))
    return textos


def traspasar(actor, invernadero, rol, saliente, entrante):
    """Traspasa lo del saliente al entrante en ese invernadero (postcondición b de PROD-MOD-INV) y devuelve las instancias que
    tocaron los registrantes, juntas (PRD-01, D-36 y D-60 punto 4): ``modificar_invernadero`` las suma a los afectados de su único
    registro de auditoría. Cada ``traspasar`` devuelve una lista de instancias o ``None`` (el contrato anterior: nada)."""
    afectados = []
    for _, traspasar_uno in list(_TRASPASOS):
        afectados.extend(traspasar_uno(actor, invernadero, rol, saliente, entrante) or [])
    return afectados


# ---- MAE-03: puntos de extensión de sectores y cultivos (docs/api/extensiones_de_maestros.md) ----
# Los registran `produccion` (PRD-01 y PRD-04), `inventario` (INV-03) e `iot` en su ``AppConfig.ready()``. Sin registrantes,
# cada punto da su resultado neutro: 0 agujeros ocupados y comprometidos, ningún impedimento, ningún contenido, ningún aviso,
# ninguna semilla y ningún invernadero que use el cultivo. Todo corre dentro de la transacción del servicio, después de que
# este tomó el invernadero y los sectores (o el cultivo); un registrante que bloquee filas propias lo hace después y en orden
# de id (docs/patrones/bloqueos.md).

# Un elemento de lo que contiene un sector (regla 3 de PROD-CNS-SCT): ``tipo`` es «lote», «orden» o «hardware».
Contenido = namedtuple("Contenido", "tipo texto cantidad fecha url")
# Una advertencia del cambio de tipo o de la baja de un sector (regla 4 de PROD-MOD-SCT y de PROD-BAJ-SCT).
Aviso = namedtuple("Aviso", "texto cantidad")
# Lo que `inventario` entrega para la tarjeta de un cultivo: ``cabecera`` (botones) y ``cuerpo`` (la tabla), HTML ya armado.
VariedadesDelCultivo = namedtuple("VariedadesDelCultivo", "cabecera cuerpo")

_AGUJEROS = []
_IMPEDIMENTOS_DE_SECTOR = []
_CONTENIDOS = []
_PERFILES = []
_AVISOS_DE_CAMBIO_DE_TIPO = []
_VUELTAS_A_SERVICIO = []
_EFECTOS_DE_BAJA_DE_SECTOR = []
_SEMILLAS = []  # pares (contar, renombrar)
_USOS_DE_CULTIVO = []
_VARIEDADES = []  # a lo sumo un registrante


def registrar_agujeros_de_sector(funcion):
    """Registra ``funcion(ids) -> dict[int, tuple[int, int]]``: por sector, ``(ocupados, comprometidos)``; lo que no figura es
    ``(0, 0)``. Lo registra `produccion` (PRD-01)."""
    _AGUJEROS.append(funcion)
    return funcion


def agujeros_registrados(ids):
    """``{id: (ocupados, comprometidos)}`` para cada id de ``ids``, sumando todos los registrantes (sin ninguno, todo en 0)."""
    ids = list(ids)
    total = {i: (0, 0) for i in ids}
    for funcion in list(_AGUJEROS):
        for i, (ocupados, comprometidos) in funcion(ids).items():
            if i in total:
                total[i] = (total[i][0] + ocupados, total[i][1] + comprometidos)
    return total


def registrar_impedimento_de_baja_de_sector(funcion):
    """Registra ``funcion(sector) -> list[Impedimento]`` con los códigos ``agujeros_ocupados``, ``agujeros_comprometidos`` y
    ``hardware_activo`` (reglas 2 y 3 de PROD-BAJ-SCT). Lo registran `produccion` e `iot`."""
    _IMPEDIMENTOS_DE_SECTOR.append(funcion)
    return funcion


def impedimentos_registrados_de_sector(sector):
    """Los impedimentos de todos los registrantes, juntos: no se queda con el primero."""
    juntos = []
    for funcion in list(_IMPEDIMENTOS_DE_SECTOR):
        juntos.extend(funcion(sector))
    return juntos


def registrar_contenido_de_sector(funcion):
    """Registra ``funcion(sectores) -> dict[int, list[Contenido]]``: lotes, órdenes y hardware de cada sector (regla 3 de
    PROD-CNS-SCT). Lo registran `produccion` e `iot`."""
    _CONTENIDOS.append(funcion)
    return funcion


def contenido_registrado(sectores):
    """``{id: [Contenido, ...]}`` con lo de todos los registrantes (sin ninguno, vacío para cada sector)."""
    sectores = list(sectores)
    juntos = {sector.pk: [] for sector in sectores}
    for funcion in list(_CONTENIDOS):
        for i, elementos in funcion(sectores).items():
            if i in juntos:
                juntos[i].extend(elementos)
    return juntos


def registrar_perfil_de_sector(funcion):
    """Registra ``funcion(ids) -> dict[int, str | None]``: el perfil familiar de las plantas del sector; ``None`` si está
    vacío. Lo registra `produccion`."""
    _PERFILES.append(funcion)
    return funcion


def perfiles_registrados(ids):
    """``{id: perfil o None}``: el primer perfil que informe algún registrante (sin ninguno, ``None``: sin plantas)."""
    ids = list(ids)
    perfiles = {i: None for i in ids}
    for funcion in list(_PERFILES):
        for i, perfil in funcion(ids).items():
            if i in perfiles and perfiles[i] is None:
                perfiles[i] = perfil
    return perfiles


def registrar_aviso_de_cambio_de_tipo(funcion):
    """Registra ``funcion(invernadero, tipo_etapa) -> list[Aviso]``: lo que queda sin un sector activo de ese tipo (lotes que
    deben pasar por esa etapa, siembras a realizar). Lo registra `produccion`."""
    _AVISOS_DE_CAMBIO_DE_TIPO.append(funcion)
    return funcion


def avisos_registrados_de_cambio_de_tipo(invernadero, tipo_etapa):
    """Los avisos de todos los registrantes, juntos."""
    juntos = []
    for funcion in list(_AVISOS_DE_CAMBIO_DE_TIPO):
        juntos.extend(funcion(invernadero, tipo_etapa))
    return juntos


def registrar_efecto_de_vuelta_a_servicio(funcion):
    """Registra ``funcion(actor, sector)``: cierra el registro «Fuera de servicio» abierto con la fecha de hoy y escribe en la
    bitácora que el sector vuelve a estar activo (postcondición b de PROD-MOD-SCT). Lo registra `produccion` (PRD-04)."""
    _VUELTAS_A_SERVICIO.append(funcion)
    return funcion


def aplicar_efectos_de_vuelta_a_servicio(actor, sector):
    """Corre los efectos de todos los registrantes, dentro de la transacción del servicio."""
    for funcion in list(_VUELTAS_A_SERVICIO):
        funcion(actor, sector)


def registrar_efecto_de_baja_de_sector(funcion):
    """Registra ``funcion(actor, sector)``: cierra el registro «Fuera de servicio» abierto con la fecha de hoy (postcondición
    b de PROD-BAJ-SCT). Lo registra `produccion` (PRD-04; D-51, punto 7)."""
    _EFECTOS_DE_BAJA_DE_SECTOR.append(funcion)
    return funcion


def aplicar_efectos_de_baja_de_sector(actor, sector):
    """Corre los efectos de todos los registrantes, dentro de la transacción de la baja y con el sector bloqueado."""
    for funcion in list(_EFECTOS_DE_BAJA_DE_SECTOR):
        funcion(actor, sector)


def registrar_semillas_de_cultivo(contar, renombrar):
    """Registra ``contar(cultivo) -> int`` (semillas que cambiarían de nombre) y ``renombrar(actor, cultivo,
    nombre_anterior) -> int`` (las renombra y escribe su propio log por semilla, acción ``modificacion_semilla``, D-36).
    Lo registra `inventario` (INV-03)."""
    _SEMILLAS.append((contar, renombrar))


def contar_semillas_a_renombrar(cultivo):
    """Cuántas semillas cambiarían de nombre si se renombra el cultivo (regla 3 de PROD-MOD-CLT); 0 sin registrantes."""
    return sum(contar(cultivo) for contar, _ in list(_SEMILLAS))


def renombrar_semillas(actor, cultivo, nombre_anterior):
    """Renombra las semillas de las variedades del cultivo y devuelve cuántas (postcondiciones a y d de PROD-MOD-CLT)."""
    return sum(renombrar(actor, cultivo, nombre_anterior) for _, renombrar in list(_SEMILLAS))


def registrar_uso_de_cultivo(funcion):
    """Registra ``funcion(cultivo) -> set[int]``: ids de los invernaderos **activos** que usan alguna variedad del cultivo
    (semilla habilitada o lotes activos; regla 4 de PROD-MOD-CLT). Lo registra solo `inventario` (INV-03)."""
    _USOS_DE_CULTIVO.append(funcion)
    return funcion


def invernaderos_que_usan_el_cultivo(cultivo):
    """Los ids de los invernaderos que usan el cultivo, de todos los registrantes; vacío sin registrantes."""
    usan = set()
    for funcion in list(_USOS_DE_CULTIVO):
        usan |= set(funcion(cultivo))
    return usan


def registrar_variedades_de_cultivo(funcion):
    """Registra ``funcion(actor, cultivos) -> dict[int, VariedadesDelCultivo]``: el HTML ya armado (``SafeString``) de la
    cabecera y del cuerpo de la tarjeta de cada cultivo. **Admite un solo registrante**: una segunda llamada lanza
    ``RuntimeError``. Lo registra `inventario` (INV-03), porque la semilla y sus invernaderos son de `inventario`."""
    if _VARIEDADES:
        raise RuntimeError("registrar_variedades_de_cultivo admite un solo registrante.")
    _VARIEDADES.append(funcion)
    return funcion


def variedades_registradas(actor, cultivos):
    """``{id: VariedadesDelCultivo}`` del registrante, o ``None`` si no hay ninguno (la pantalla usa entonces lo propio de
    `maestros`: «No tiene variedades» y sin botones)."""
    if not _VARIEDADES:
        return None
    return _VARIEDADES[0](actor, list(cultivos))


# ---- PRD-01: pestañas de la ficha del invernadero (docs/api/extensiones_de_maestros.md, «Pestañas de la ficha del invernadero») ----
# `maestros` no puede armar «Lotes activos» (regla A1: los lotes son de `produccion`): la app alta registra la pestaña. Sin
# registrantes, la ficha no tiene pestañas extra.

# Una pestaña lista para mostrar: ``html`` es el fragmento ya armado y escapado por quien la registra (``SafeString``).
PestanaDeInvernadero = namedtuple("PestanaDeInvernadero", "clave titulo html")

_PESTANAS = []  # ternas (clave, titulo, funcion), en orden de registro


def registrar_pestana_de_invernadero(clave, titulo, funcion):
    """Registra ``funcion(actor, invernadero) -> SafeString | None``: el HTML ya armado y escapado de la pestaña ``clave`` («Lotes
    activos»); ``None`` si el actor no la ve. Una ``clave`` repetida lanza ``RuntimeError``. La registra `produccion` (y,
    después, `iot`)."""
    if any(registrada == clave for registrada, _, _ in _PESTANAS):
        raise RuntimeError(f"La pestaña «{clave}» ya está registrada.")
    _PESTANAS.append((clave, titulo, funcion))


def pestanas_de_invernadero(actor, invernadero):
    """Las pestañas registradas que ``actor`` ve, **en orden de registro**, como ``PestanaDeInvernadero``; las que devuelven
    ``None`` no figuran. Sin registrantes, lista vacía. La ficha las muestra después de las propias."""
    pestanas = []
    for clave, titulo, funcion in list(_PESTANAS):
        html = funcion(actor, invernadero)
        if html is not None:
            pestanas.append(PestanaDeInvernadero(clave, titulo, html))
    return pestanas


# ---- MAE-05: puntos de extensión de los transportistas (D-55; docs/api/extensiones_de_maestros.md, «Transportistas») ----
# `maestros` guarda a qué invernadero pertenece cada Transportista (TransportistaInvernadero) y no conoce `Entrega` ni
# `Vehiculo`, que vivirán en `comercial`: los dos puntos los registra `comercial` en su ``AppConfig.ready()``. Sin
# registrantes, cada uno da su resultado neutro (ningún impedimento; ninguna columna de logística). Corren dentro de la
# transacción del servicio, con la cuenta del Transportista y los invernaderos ya bloqueados (D-40).

# Lo que `comercial` informa de cada Transportista para «Logística»: ``vehiculo`` es un texto («Camioneta AE123CD · 800 kg»)
# o ``None`` (sin vehículo); ``url_entregas`` lleva a sus entregas (COM-ASG-TRP).
Logistica = namedtuple("Logistica", "vehiculo en_ruta entregas_a_realizar url_entregas")

_IMPEDIMENTOS_DE_TRANSPORTISTA = []
_LOGISTICA = []  # a lo sumo un registrante


def registrar_impedimento_de_transportista(funcion):
    """Registra ``funcion(transportista) -> list[Impedimento]`` con los códigos ``transportista_en_ruta`` y
    ``transportista_con_entregas`` (reglas 9 y 10 de PROD-MOD-INV). Solo lectura. Lo registra `comercial`."""
    _IMPEDIMENTOS_DE_TRANSPORTISTA.append(funcion)
    return funcion


def impedimentos_de_transportista(transportista):
    """Los impedimentos de todos los registrantes, juntos (sin registrantes, lista vacía: no se bloquea nada). Los usan
    quitar y trasladar, y la ventana que los informa."""
    juntos = []
    for funcion in list(_IMPEDIMENTOS_DE_TRANSPORTISTA):
        juntos.extend(funcion(transportista))
    return juntos


def registrar_logistica_de_transportista(funcion):
    """Registra ``funcion(transportistas) -> dict[int, Logistica]``: vehículo, situación y entregas a realizar de cada
    Transportista, en una sola llamada para toda la lista. **Admite un solo registrante**: una segunda llamada lanza
    ``RuntimeError``. Lo registra `comercial`."""
    if _LOGISTICA:
        raise RuntimeError("registrar_logistica_de_transportista admite un solo registrante.")
    _LOGISTICA.append(funcion)
    return funcion


def logistica_de(transportistas):
    """``{id: Logistica}`` del registrante, o ``None`` si no hay ninguno (entonces «Logística» muestra solo el nombre y el
    estado de la cuenta, sin las columnas de vehículo, situación y entregas)."""
    if not _LOGISTICA:
        return None
    return _LOGISTICA[0](list(transportistas))


# ---- IOT-02: estado del IoT del invernadero (docs/api/extensiones_de_maestros.md, «Estado del IoT del invernadero») ----
# `maestros` muestra en la ficha («Ubicación») y en la lista («Con IoT») si el invernadero tiene sistema IoT, y lo usa en la alerta
# del Técnico (regla 3 de 8.22) y en el campo del Técnico del alta (regla 5 de PROD-ALT-INV). No puede importar `iot` (A1): `iot`
# se registra desde `IotConfig.ready()`. Sin registrante, todo queda como antes de IOT-02: ningún estado y ningún enlace.

# Lo que `iot` informa de un invernadero con sistema NO dado de baja: ``estado`` es «activo» o «desconectado»; ``url`` lleva a la
# pestaña «Sistema IoT» de ese invernadero.
EstadoIot = namedtuple("EstadoIot", "estado url")

_ESTADO_IOT = []  # a lo sumo un registrante: la lista guarda el par (estados, url_de_registro)


def registrar_estado_iot(estados, url_de_registro):
    """Registra ``estados(invernadero_ids) -> dict[int, EstadoIot]`` (solo los invernaderos con un sistema no dado de baja) y
    ``url_de_registro(actor, invernadero) -> str | None`` (el enlace «Registrar sistema IoT», o ``None`` si el actor no opera el
    IoT de ese invernadero). **Admite un solo registrante**: una segunda llamada lanza ``RuntimeError``. Lo registra `iot`."""
    if _ESTADO_IOT:
        raise RuntimeError("registrar_estado_iot admite un solo registrante.")
    _ESTADO_IOT.append((estados, url_de_registro))


def estados_iot(ids):
    """``{id: EstadoIot}`` de los invernaderos de ``ids`` con un sistema IoT no dado de baja. Una sola llamada para toda la lista
    (sin consultas por fila). Sin registrante, o sin ids, vacío."""
    ids = list(ids)
    if not _ESTADO_IOT or not ids:
        return {}
    return _ESTADO_IOT[0][0](ids)


def url_de_registro_iot(actor, invernadero):
    """El enlace «Registrar sistema IoT» para ``actor`` en ``invernadero``, o ``None`` si no opera el IoT de ese invernadero (ningún
    botón lleva a un 403, D-30) o no hay registrante."""
    if not _ESTADO_IOT:
        return None
    return _ESTADO_IOT[0][1](actor, invernadero)


# ---- MAE-02d: enlace de cada alerta a la pantalla de su origen (D-62, puntos 2 y 3; docs/api/alertas.md, sección 8) ----
# `maestros` no puede conocer las pantallas de las apps altas (regla A1 de D-37): cada una registra, para sus códigos de tipo,
# una función que dice adónde lleva cada alerta a ese usuario. Sin registrantes, rige el enlace por omisión (el detalle de la
# alerta; lo arma ``maestros.servicios.alertas.enlaces_de_alertas``). Patrón: Variaciones protegidas con Indirección (Larman).

# Adónde lleva una alerta y qué texto va debajo de su título. ``detalle`` puede ser ``None``: se usa el de omisión.
Enlace = namedtuple("Enlace", "url detalle")

_ENLACES = []  # pares (codigos, funcion), en orden de registro


def registrar_enlace_de_alerta(codigos, funcion):
    """Registra ``funcion(usuario, alertas) -> dict[int, Enlace]`` para los códigos de tipo de ``codigos`` (una tupla). Recibe
    la lista entera de alertas de esos tipos (una llamada por registrante, nunca una por alerta) y devuelve, por id de alerta,
    adónde lleva **a ese usuario**; nunca a una pantalla que le dé 403 (D-62, punto 4). Una alerta que no devuelve usa el
    enlace por omisión.

    Un código con otro registrante lanza ``ImproperlyConfigured`` (D-62, punto 2). Se validan **todos** los códigos antes de
    agregar nada: un registro que falla no deja registrados los demás códigos. Registrar de nuevo la misma función para el mismo
    código no hace nada (``ready()`` puede correr más de una vez)."""
    codigos = tuple(codigos)
    nuevos = []
    for codigo in codigos:
        existente = next((f for registrados, f in _ENLACES if codigo in registrados), None)
        if existente is None:
            nuevos.append(codigo)
        elif existente is not funcion:
            raise ImproperlyConfigured(f"El código de alerta «{codigo}» ya tiene otro registrante de enlaces.")
    if nuevos:
        _ENLACES.append((tuple(nuevos), funcion))
    return funcion


def enlaces_registrados():
    """Los pares ``(codigos, funcion)`` registrados, en orden de registro (una copia: ``enlaces_de_alertas`` los agrupa)."""
    return list(_ENLACES)
