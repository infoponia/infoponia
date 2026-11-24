# Servicios de TipoActuador (IOT-01): alta (IOT-ALT-TAC), modificación con su reactivación (IOT-MOD-TAC), baja (IOT-BAJ-TAC) y
# consulta (IOT-CNS-TAC). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36
# (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/iot/tipos_de_actuador.md; orden de docs/patrones/abm.md, sección 2.
#
# Bloqueos (tipos_de_actuador.md, «Bloqueos»; siempre ``FOR NO KEY UPDATE``): modificar, reactivar y dar de baja bloquean la fila del tipo
# y, después, sus acciones activas en orden de id, y las releen. El alta no bloquea nada: la unicidad del nombre la respalda la base.
# Quien cree un actuador de un tipo (IOT-02) tiene que llamar antes a ``bloquear_tipo_activo`` (mismo contrato que
# ``bloquear_invernadero_activo``, D-40): el ``INSERT`` solo toma ``FOR KEY SHARE``, que no choca con el de la baja.
#
# «Se completa en IOT-NN»: ``acciones_en_uso`` (comandos: IOT-05; reglas: IOT-06), ``acciones_con_historial`` (hecha en IOT-05) y la compatibilidad de los
# actuadores del tipo (``recalcular_compatibilidad``, ya completo desde IOT-02).

import re
from dataclasses import dataclass, field
from collections import namedtuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, Value
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404

from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from iot.catalogo import RANGO_DEL_PORCENTAJE, UNIDAD_PORCENTAJE, UNIDADES_CON_MINIMO_CERO, UNIDADES_POR_COMANDO
from iot.models import Accion, Actuador, Capacidad, Comando, ComandoCatalogo, TipoActuador
from iot.servicios.compatibilidad import recalcular_compatibilidad
from maestros.models import Invernadero
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, _tiene_contenido

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

LARGO_DEL_NOMBRE = TipoActuador._meta.get_field("nombre_actuador").max_length
LARGO_DEL_NOMBRE_DE_ACCION = Accion._meta.get_field("nombre_accion").max_length
MENSAJE_NOMBRE_REPETIDO = "Ya existe un tipo de actuador con ese nombre."
MENSAJE_TIEMPO = "Ingresá un número entero de segundos (0 o más)."
MAXIMO_ENTERO = 2_147_483_647  # lo que cabe en una columna entera de la base
MAXIMO_DE_FILAS = 50  # tope de filas de acciones que lee ``desde_post``: un tipo tiene a lo sumo una activa por comando (seis)

Estado = TipoActuador.Estado
EstadoAccion = Accion.Estado

# Un uso de una acción por una regla de actuación activa o un comando pendiente: su código (``RGL-3``, ``CMD-7``) y el valor que aplica.
UsoDeAccion = namedtuple("UsoDeAccion", "codigo valor")


# ---- datos del formulario ----


def _entero(valor):
    """El entero que representa ``valor`` (un ``int`` o un texto como «-10» o « 7 »), o ``None`` si no es un entero (un decimal,
    un texto cualquiera, un booleano, vacío o más grande que una columna entera)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and re.fullmatch(r"-?\d+", valor.strip()):
        numero = int(valor.strip())
    else:
        return None
    return numero if abs(numero) <= MAXIMO_ENTERO else None


@dataclass
class DatosDeAccion:
    """Una fila del formulario de acciones: ``comando`` es el código del catálogo, ``id`` el de la acción original (nulo si es nueva).
    ``minimo``, ``maximo`` y ``unidad`` pueden venir como texto: el servicio los valida."""

    nombre: object
    comando: object
    minimo: object = None
    maximo: object = None
    unidad: object = None
    id: int | None = None


@dataclass
class DatosDeTipoActuador:
    """Lo que manda el formulario de un tipo: nombre, tiempo mínimo y la lista COMPLETA de acciones activas."""

    nombre: object
    tiempo_minimo: object
    acciones: list = field(default_factory=list)

    @classmethod
    def desde_post(cls, post):
        """Arma los datos desde el POST: ``nombre``, ``tiempo_minimo``, ``acciones_total`` y, por fila, ``accion_<i>_id``,
        ``accion_<i>_nombre``, ``accion_<i>_comando``, ``accion_<i>_minimo``, ``accion_<i>_maximo`` y ``accion_<i>_unidad``. Tolera
        campos que faltan y totales raros: los errores los da el servicio."""
        total = min(max(_entero(post.get("acciones_total")) or 0, 0), MAXIMO_DE_FILAS)
        acciones = []
        for i in range(total):
            prefijo = f"accion_{i}_"
            acciones.append(
                DatosDeAccion(
                    nombre=post.get(prefijo + "nombre", ""),
                    comando=post.get(prefijo + "comando", ""),
                    minimo=post.get(prefijo + "minimo"),
                    maximo=post.get(prefijo + "maximo"),
                    unidad=post.get(prefijo + "unidad"),
                    id=_entero(post.get(prefijo + "id")),
                )
            )
        return cls(nombre=post.get("nombre", ""), tiempo_minimo=post.get("tiempo_minimo", ""), acciones=acciones)


# Una fila ya validada: ``comando`` es el ``ComandoCatalogo``; sin valor, ``minimo``, ``maximo`` y ``unidad`` son ``None``.
_Fila = namedtuple("_Fila", "id nombre comando minimo maximo unidad")


# ---- validación sin tocar la base de datos de negocio (reglas 2 a 4, 8, 9 y 10 de IOT-ALT-TAC) ----


def _texto(valor):
    """``valor`` como texto recortado (vacío si es ``None``)."""
    return "" if valor is None else str(valor).strip()


def _validar(datos):
    """Normaliza y valida ``datos``. Junta TODOS los errores y lanza un solo ``ValidationError`` con un error por campo (``nombre``,
    ``tiempo_minimo``, ``acciones``). Devuelve ``(nombre, tiempo, filas)``. Solo lee el catálogo de comandos, que es fijo."""
    errores = {"nombre": [], "tiempo_minimo": [], "acciones": []}

    nombre = _texto(datos.nombre)
    if not nombre:
        errores["nombre"].append(ValidationError("Ingresá el nombre del tipo.", code="obligatorio"))
    elif not _tiene_contenido(nombre):
        errores["nombre"].append(ValidationError("Ingresá un texto con al menos una letra o un número.", code="sin_contenido"))
    elif len(nombre) > LARGO_DEL_NOMBRE:
        errores["nombre"].append(ValidationError(f"Usá como máximo {LARGO_DEL_NOMBRE} caracteres.", code="demasiado_largo"))

    tiempo = _entero(datos.tiempo_minimo)
    if tiempo is None or tiempo < 0:
        errores["tiempo_minimo"].append(ValidationError(MENSAJE_TIEMPO, code="tiempo_invalido"))

    filas = []
    mensajes = []  # (texto, código) sin repetir

    def avisar(texto, codigo):
        if (texto, codigo) not in mensajes:
            mensajes.append((texto, codigo))

    if not datos.acciones:
        avisar("El tipo necesita al menos una acción activa.", "sin_acciones")
    comandos = {c.codigo: c for c in ComandoCatalogo.objects.select_related("capacidad")}
    nombres, usados = set(), set()
    for dato in datos.acciones:
        nombre_accion = _texto(dato.nombre)
        if not nombre_accion:
            avisar("Cada acción necesita un nombre.", "accion_sin_nombre")
            continue
        if len(nombre_accion) > LARGO_DEL_NOMBRE_DE_ACCION:
            avisar(f"El nombre de la acción «{nombre_accion}» tiene más de {LARGO_DEL_NOMBRE_DE_ACCION} caracteres.", "accion_nombre_largo")
            continue
        comando = comandos.get(_texto(dato.comando))
        if comando is None:
            avisar(f"Elegí el comando de «{nombre_accion}».", "accion_sin_comando")
            continue
        if nombre_accion.lower() in nombres:
            avisar(f"La acción «{nombre_accion}» está repetida.", "accion_repetida")
            continue
        nombres.add(nombre_accion.lower())
        if comando.codigo in usados:
            avisar(f"Dos acciones usan el comando {comando.codigo}.", "comando_repetido")
            continue
        usados.add(comando.codigo)
        minimo = maximo = unidad = None
        if comando.lleva_valor:
            minimo, maximo = _entero(dato.minimo), _entero(dato.maximo)
            if minimo is None or maximo is None or minimo >= maximo:
                avisar(f"“{nombre_accion}” necesita un mínimo y un máximo enteros, con el mínimo menor al máximo.", "rango_invalido")
                continue
            unidad = _texto(dato.unidad)
            if not unidad:
                avisar(f"“{nombre_accion}” necesita una unidad.", "unidad_obligatoria")
                continue
            if unidad not in [valor for valor, _ in UNIDADES_POR_COMANDO[comando.codigo]]:
                avisar(f"La unidad de “{nombre_accion}” no es válida para el comando {comando.codigo}.", "unidad_invalida")
                continue
            # D-80: el rango según la unidad.
            if unidad == UNIDAD_PORCENTAJE and not (RANGO_DEL_PORCENTAJE[0] <= minimo and maximo <= RANGO_DEL_PORCENTAJE[1]):
                avisar(f"“{nombre_accion}” necesita un rango dentro de {RANGO_DEL_PORCENTAJE[0]} a {RANGO_DEL_PORCENTAJE[1]} %.", "rango_fuera_de_unidad")
                continue
            if unidad in UNIDADES_CON_MINIMO_CERO and minimo < 0:
                avisar(f"“{nombre_accion}” necesita un mínimo de 0 o más.", "rango_fuera_de_unidad")
                continue
        filas.append(_Fila(dato.id, nombre_accion, comando, minimo, maximo, unidad))
    errores["acciones"] = [ValidationError(texto, code=codigo) for texto, codigo in mensajes]

    errores = {campo: lista for campo, lista in errores.items() if lista}
    if errores:
        raise ValidationError(errores)
    return nombre, tiempo, filas


# ---- comunes ----


def _exigir_gerente(actor):
    """Precondición a y regla 1 de ALT, MOD y BAJ: ``actor`` es un Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo el Gerente puede administrar los tipos de actuador.")


def _exigir_consulta(actor):
    """Precondición a de CNS: ``actor`` es un Gerente o un Agrónomo con la cuenta activa."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
        raise PermissionDenied("Solo el Gerente y el Agrónomo consultan los tipos de actuador.")


def _nombre_repetido(nombre, excluir_pk=None):
    """True si ya hay un tipo con ese nombre, sin distinguir mayúsculas, activo o inactivo (regla 2 de IOT-ALT-TAC)."""
    existentes = TipoActuador.objects.annotate(_minuscula=Lower("nombre_actuador"))
    if excluir_pk is not None:
        existentes = existentes.exclude(pk=excluir_pk)
    return existentes.filter(_minuscula=Lower(Value(nombre))).exists()


def _error_nombre_repetido():
    """El error de campo de un nombre repetido."""
    return ValidationError({"nombre": [ValidationError(MENSAJE_NOMBRE_REPETIDO, code="nombre_repetido")]})


def _bloquear_tipo(actor, tipo_id):
    """El tipo bloqueado (``FOR NO KEY UPDATE``) y leído de nuevo; 404 si no existe. Verifica, ya bloqueado, que quien actúa siga
    activo. Hay que llamarla dentro de ``transaction.atomic()``."""
    tipo = TipoActuador.objects.select_for_update(no_key=True).filter(pk=tipo_id).first()
    if tipo is None:
        raise Http404("No existe ese tipo de actuador.")
    _actor_sigue_activo(actor)
    return tipo


def bloquear_tipo_activo(tipo_id):
    """Contrato para quien cree algo que impida la baja del tipo (un actuador, IOT-02): bloquea el tipo ``FOR NO KEY UPDATE`` ANTES de
    crearlo y rechaza uno inactivo (``tipo_inactivo``). Así la baja espera, ve el actuador y se rechaza. Dentro de ``atomic``."""
    tipo = TipoActuador.objects.select_for_update(no_key=True).filter(pk=tipo_id).first()
    if tipo is None:
        raise Http404("No existe ese tipo de actuador.")
    if tipo.estado == Estado.INACTIVO:
        raise _error_general("El tipo de actuador está dado de baja.", "tipo_inactivo")
    return tipo


def _guardar_tipo(tipo, campos):
    """Guarda ``campos``; si dos pedidos eligieron el mismo nombre a la vez, el segundo recibe el ``IntegrityError`` de la restricción
    única y se traduce al mismo error de campo (nunca un 500)."""
    try:
        with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
            tipo.save(update_fields=campos)
    except IntegrityError as error:
        if "tipo_actuador_nombre_unico" in str(error):
            raise _error_nombre_repetido() from error
        raise


def _cambio_de_estado(antes, despues):
    """El detalle de auditoría (D-36) de un cambio de estado."""
    return {"cambios": {"estado": {"antes": antes, "despues": despues}}}


def _crear_acciones(tipo, filas):
    """Crea las acciones de ``filas`` en el tipo y las devuelve, en orden."""
    return [
        Accion.objects.create(
            tipo_actuador=tipo,
            nombre_accion=fila.nombre,
            comando=fila.comando,
            unidad_valor=fila.unidad,
            valor_minimo=fila.minimo,
            valor_maximo=fila.maximo,
        )
        for fila in filas
    ]


# ---- «Se completa en IOT-NN» ----


def acciones_en_uso(tipo):
    """``{id de acción: [UsoDeAccion, ...]}``: las acciones del tipo (o de cada tipo de una lista: una sola consulta para toda la lista) usadas por una regla de actuación ACTIVA o por un comando
    PENDIENTE, con cada uso (regla 4 de IOT-MOD-TAC; marca «en uso» de IOT-CNS-TAC). IOT-05 completó los comandos pendientes (código ``CMD-n`` y
    valor); **IOT-06 suma las reglas activas** (código ``RGL-n``): hasta entonces no hay ninguna."""
    usos = {}
    tipos = list(tipo) if isinstance(tipo, (list, tuple)) else [tipo]
    pendientes = Comando.objects.filter(accion__tipo_actuador__in=tipos, estado_comando=Comando.Estado.PENDIENTE).order_by("pk")
    for accion_id, pk, valor in pendientes.values_list("accion_id", "pk", "valor_comando"):
        usos.setdefault(accion_id, []).append(UsoDeAccion(f"CMD-{pk}", valor))
    return usos


def acciones_con_historial(tipo):
    """Los ids de las acciones del tipo con algún comando en su historial, en cualquier estado (regla 4 de IOT-MOD-TAC). Completo desde IOT-05."""
    return set(Comando.objects.filter(accion__tipo_actuador=tipo).values_list("accion_id", flat=True))


def equipos_afectados(tipo):
    """``[(Invernadero, cantidad)]``, por nombre: los actuadores del tipo que NO están dados de baja, por invernadero (regla 6 de
    IOT-MOD-TAC y regla 2 de IOT-BAJ-TAC). Ya está escrita; tiene datos desde IOT-02."""
    cuentas = dict(
        Actuador.objects.filter(tipo_actuador=tipo)
        .exclude(estado_hardware="inactivo")
        .order_by()
        .values_list("sistema__invernadero")
        .annotate(cantidad=Count("pk"))
    )
    invernaderos = Invernadero.objects.filter(pk__in=cuentas).order_by(Lower("nombre_invernadero"), "pk")
    return [(invernadero, cuentas[invernadero.pk]) for invernadero in invernaderos]


def texto_de_equipos_afectados(equipos):
    """«Invernadero Norte (3), Invernadero Sur (1)» a partir de ``equipos_afectados`` (aviso de la regla 6 de IOT-MOD-TAC)."""
    return ", ".join(f"{invernadero.nombre_invernadero} ({cantidad})" for invernadero, cantidad in equipos)


def mensaje_de_equipos_activos(equipos):
    """«Hay N equipo(s) de este tipo en Invernadero Norte e Invernadero Sur. Dalos de baja antes de dar de baja el tipo.» (regla 2 de
    IOT-BAJ-TAC), a partir de ``equipos_afectados``. Lo usan la baja y la ventana que la confirma."""
    total = sum(cantidad for _, cantidad in equipos)
    hay = "Hay 1 equipo" if total == 1 else f"Hay {total} equipos"
    lugares = _lista_de_nombres([invernadero.nombre_invernadero for invernadero, _ in equipos])
    return f"{hay} de este tipo en {lugares}. Dalos de baja antes de dar de baja el tipo."


def _lista_de_nombres(nombres):
    """«A», «A y B» o «A, B y C»; la «y» pasa a «e» delante de un nombre que empieza con el sonido «i»."""
    if len(nombres) == 1:
        return nombres[0]
    ultimo = nombres[-1].lower()
    conjuncion = "e" if ultimo.startswith("i") or (ultimo.startswith("hi") and not ultimo.startswith(("hia", "hie"))) else "y"
    return f"{', '.join(nombres[:-1])} {conjuncion} {nombres[-1]}"


# ---- casos de uso ----


def alta_tipo_actuador(actor, datos):
    """IOT-ALT-TAC: crea un tipo de actuador activo con sus acciones y lo devuelve.

    - Precondición a y regla 1: ``actor`` es un Gerente activo (sin alcance por invernadero).
    - Precondición b y reglas 2 a 4, 8, 9 y 10: nombre, tiempo mínimo y acciones válidos (``_validar``); nombre único entre todos los
      tipos, activos o inactivos, sin distinguir mayúsculas ni espacios (``nombre_repetido``). Dos altas a la vez: la base respalda.
    - Postcondición a: queda «activo» con al menos una acción. Postcondición b, D-22 y D-36: un registro ``alta_tipo_actuador``
      con el tipo y cada acción creada, en la misma transacción.
    """
    _exigir_gerente(actor)
    nombre, tiempo, filas = _validar(datos)
    with transaction.atomic():
        _actor_sigue_activo(actor)
        if _nombre_repetido(nombre):
            raise _error_nombre_repetido()
        try:
            with transaction.atomic():
                tipo = TipoActuador.objects.create(
                    nombre_actuador=nombre, tiempo_minimo_entre_comandos=tiempo, estado=Estado.ACTIVO
                )
        except IntegrityError as error:
            if "tipo_actuador_nombre_unico" in str(error):
                raise _error_nombre_repetido() from error
            raise
        acciones = _crear_acciones(tipo, filas)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_TIPO_ACTUADOR,
            afectados=[tipo, *acciones],
            detalle={
                "cambios": {
                    "nombre": {"antes": None, "despues": nombre},
                    "tiempo_minimo_entre_comandos": {"antes": None, "despues": tiempo},
                    "estado": {"antes": None, "despues": Estado.ACTIVO.value},
                },
                "datos": {"acciones_creadas": [referencia(accion) for accion in acciones]},
            },
        )
    return tipo


def _en_texto(usos):
    """«RGL-3, CMD-7»: los códigos de los usos de una acción."""
    return ", ".join(uso.codigo for uso in usos)


def _cambios_de_acciones(modificadas):
    """El detalle de auditoría (D-36) de las acciones modificadas, ``{clave: {"antes", "despues"}}``, un cambio por cada dato que cambió
    (nombre, comando, unidad, mínimo y máximo). La clave dice qué cambió y de qué acción (con su nombre anterior), por ejemplo
    «Comando de la acción «Apagar»»: ``ETIQUETAS`` no tiene claves por acción y una clave desconocida se muestra tal cual."""
    cambios = {}
    for original, fila in modificadas:
        pares = (
            ("Nombre", original.nombre_accion, fila.nombre),
            ("Comando", original.comando.codigo, fila.comando.codigo),
            ("Unidad", original.unidad_valor, fila.unidad),
            ("Valor mínimo", original.valor_minimo, fila.minimo),
            ("Valor máximo", original.valor_maximo, fila.maximo),
        )
        for etiqueta, antes, despues in pares:
            if antes != despues:
                cambios[f"{etiqueta} de la acción «{original.nombre_accion}»"] = {"antes": antes, "despues": despues}
    return cambios


def modificar_tipo_actuador(actor, tipo_id, datos):
    """IOT-MOD-TAC: cambia el nombre, el tiempo mínimo y las acciones de un tipo y lo devuelve.

    - Precondición a y regla 1: Gerente activo. Regla 7: un tipo inactivo no se modifica (``tipo_inactivo``). Regla 2: las reglas del
      alta. Regla 5: el tipo conserva al menos una acción activa.
    - Regla 4: una acción en uso (``acciones_en_uso``) no se quita, no se renombra y no cambia su comando ni su unidad, y su rango se
      achica solo si ningún valor de esos usos queda afuera; una con historial (``acciones_con_historial``) no cambia su comando ni su
      unidad. Todos los impedimentos llegan juntos.
    - Regla 8 y postcondición a: una acción quitada con historial queda inactiva; sin historial, se borra.
    - Postcondición c: la compatibilidad de los actuadores del tipo se recalcula (``recalcular_compatibilidad``, IOT-02).
    - D-28: sin cambios no se escribe ni se audita. Postcondición d y D-36: un registro ``modificacion_tipo_actuador`` con los cambios
      del tipo (nombre y tiempo, antes y después), el antes y el después de cada dato que cambió en cada acción modificada y las listas de
      acciones creadas, modificadas, desactivadas y borradas.
    - Bloqueos: el tipo y sus acciones activas (orden de id), releídos. Dos modificaciones a la vez: gana la última, salvo el nombre.
    """
    _exigir_gerente(actor)
    nombre, tiempo, filas = _validar(datos)
    with transaction.atomic():
        tipo = _bloquear_tipo(actor, tipo_id)
        if tipo.estado == Estado.INACTIVO:
            raise _error_general("El tipo de actuador está dado de baja: solo se puede reactivar.", "tipo_inactivo")
        if _nombre_repetido(nombre, excluir_pk=tipo.pk):
            raise _error_nombre_repetido()
        originales = {
            a.pk: a
            for a in Accion.objects.select_for_update(no_key=True)
            .select_related("comando")
            .filter(tipo_actuador=tipo, estado=EstadoAccion.ACTIVA)
            .order_by("id")
        }
        ids = [fila.id for fila in filas if fila.id is not None]
        if len(set(ids)) != len(ids) or any(i not in originales for i in ids):
            raise _error_general(
                "Las acciones del tipo cambiaron mientras lo editabas. Volvé a abrirlo para ver cómo quedaron.", "cambio_simultaneo"
            )
        usos = acciones_en_uso(tipo)
        con_historial = acciones_con_historial(tipo)

        impedimentos = []

        def impedir(texto, codigo):
            impedimentos.append(ValidationError(texto, code=codigo))

        modificadas, quitadas = [], []  # (original, fila) y originales
        for original in originales.values():
            fila = next((f for f in filas if f.id == original.pk), None)
            sus_usos = usos.get(original.pk, [])
            nombre_accion = original.nombre_accion
            if fila is None:
                if sus_usos:
                    impedir(f"No se puede quitar «{nombre_accion}»: la usan {_en_texto(sus_usos)}.", "accion_en_uso")
                else:
                    quitadas.append(original)
                continue
            motivo = f"la usan {_en_texto(sus_usos)}" if sus_usos else "tiene comandos en su historial"
            if fila.nombre != original.nombre_accion and sus_usos:
                impedir(f"No se puede renombrar «{nombre_accion}»: la usan {_en_texto(sus_usos)}.", "accion_en_uso")
            if fila.comando.pk != original.comando_id and (sus_usos or original.pk in con_historial):
                impedir(f"No se puede cambiar el comando de «{nombre_accion}»: {motivo}. Agregá una acción nueva.", "accion_en_uso")
            if fila.unidad != original.unidad_valor and (sus_usos or original.pk in con_historial):
                impedir(f"No se puede cambiar la unidad de «{nombre_accion}»: {motivo}. Agregá una acción nueva.", "accion_en_uso")
            if sus_usos and original.valor_minimo is not None and fila.minimo is not None:
                if fila.minimo > original.valor_minimo or fila.maximo < original.valor_maximo:
                    afuera = [u for u in sus_usos if u.valor is not None and not fila.minimo <= u.valor <= fila.maximo]
                    if afuera:
                        impedir(
                            f"No se puede achicar el rango de «{nombre_accion}»: quedarían afuera los valores de {_en_texto(afuera)}.",
                            "rango_con_usos",
                        )
            if (fila.nombre, fila.comando.pk, fila.minimo, fila.maximo, fila.unidad) != (
                original.nombre_accion,
                original.comando_id,
                original.valor_minimo,
                original.valor_maximo,
                original.unidad_valor,
            ):
                modificadas.append((original, fila))
        if impedimentos:
            raise ValidationError({"acciones": impedimentos})

        creadas_filas = [f for f in filas if f.id is None]
        cambios_de_acciones = _cambios_de_acciones(modificadas)  # antes de escribir: ``original`` todavía tiene lo anterior
        cambios = {}
        if nombre != tipo.nombre_actuador:
            cambios["nombre"] = {"antes": tipo.nombre_actuador, "despues": nombre}
        if tiempo != tipo.tiempo_minimo_entre_comandos:
            cambios["tiempo_minimo_entre_comandos"] = {"antes": tipo.tiempo_minimo_entre_comandos, "despues": tiempo}
        if not (cambios or creadas_filas or modificadas or quitadas):
            return tipo  # D-28: sin cambios no se escribe ni se audita

        if cambios:
            tipo.nombre_actuador, tipo.tiempo_minimo_entre_comandos = nombre, tiempo
            _guardar_tipo(tipo, ["nombre_actuador", "tiempo_minimo_entre_comandos"])

        # Primero salen las quitadas (así una acción nueva puede usar su nombre o su comando), después las que cambian y por último las nuevas.
        desactivadas = [a for a in quitadas if a.pk in con_historial]
        borradas = [a for a in quitadas if a.pk not in con_historial]
        referencias_de_borradas = [referencia(a) for a in borradas]
        if desactivadas:
            Accion.objects.filter(pk__in=[a.pk for a in desactivadas]).update(estado=EstadoAccion.INACTIVA)
        if borradas:
            Accion.objects.filter(pk__in=[a.pk for a in borradas]).delete()  # el ``delete`` de un QuerySet no borra el ``pk`` de los objetos
        # Una acción que cambia de nombre o de comando sale un momento de los índices únicos parciales (queda inactiva): así dos acciones
        # pueden intercambiar nombres o comandos. Los valores finales ya se validaron como distintos entre sí.
        cambian_clave = [o for o, f in modificadas if f.nombre != o.nombre_accion or f.comando.pk != o.comando_id]
        if cambian_clave:
            Accion.objects.filter(pk__in=[a.pk for a in cambian_clave]).update(estado=EstadoAccion.INACTIVA)
        for original, fila in modificadas:
            original.nombre_accion, original.comando = fila.nombre, fila.comando
            original.unidad_valor, original.valor_minimo, original.valor_maximo = fila.unidad, fila.minimo, fila.maximo
            original.estado = EstadoAccion.ACTIVA
            original.save(update_fields=["nombre_accion", "comando", "unidad_valor", "valor_minimo", "valor_maximo", "estado"])
        creadas = _crear_acciones(tipo, creadas_filas)

        # Postcondición c y regla 9 de IOT-MOD-TAC (IOT-02): se recalcula la compatibilidad de los actuadores del tipo que no están dados de baja. La función
        # ordena por invernadero y los bloquea uno por uno DESPUÉS del tipo (D-82), así no se cruza con el alta de un actuador de este tipo.
        actuadores = list(
            Actuador.objects.filter(tipo_actuador=tipo).exclude(estado_hardware="inactivo").select_related("sistema").order_by("pk")
        )
        alertas_de_compatibilidad = [
            a for r in recalcular_compatibilidad(actuadores) for a in (r.alerta_creada, r.alerta_resuelta) if a is not None
        ]

        datos_del_registro = {
            clave: [referencia(a) for a in lista]
            for clave, lista in (
                ("acciones_creadas", creadas),
                ("acciones_modificadas", [o for o, _ in modificadas]),
                ("acciones_desactivadas", desactivadas),
            )
            if lista
        }
        if referencias_de_borradas:
            datos_del_registro["acciones_borradas"] = referencias_de_borradas
        detalle = {}
        if cambios or cambios_de_acciones:
            detalle["cambios"] = cambios | cambios_de_acciones
        if datos_del_registro:
            detalle["datos"] = datos_del_registro
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_TIPO_ACTUADOR,
            afectados=[tipo, *creadas, *[o for o, _ in modificadas], *desactivadas, *borradas, *alertas_de_compatibilidad],
            detalle=detalle,
        )
    return tipo


def reactivar_tipo_actuador(actor, tipo_id):
    """IOT-MOD-TAC (postcondición b y regla 7): reactiva un tipo dado de baja y lo devuelve. Uno que no está dado de baja se rechaza
    con ``tipo_no_inactivo``. El nombre sigue siendo único entre todos los tipos (la base lo garantiza), así que no puede chocar con
    otro. Se audita como ``reactivacion_tipo_actuador``."""
    _exigir_gerente(actor)
    with transaction.atomic():
        tipo = _bloquear_tipo(actor, tipo_id)
        if tipo.estado != Estado.INACTIVO:
            raise _error_general("El tipo de actuador no está dado de baja.", "tipo_no_inactivo")
        tipo.estado = Estado.ACTIVO
        tipo.save(update_fields=["estado"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_TIPO_ACTUADOR,
            afectados=[tipo],
            detalle=_cambio_de_estado(Estado.INACTIVO.value, Estado.ACTIVO.value),
        )
    return tipo


def baja_tipo_actuador(actor, tipo_id):
    """IOT-BAJ-TAC: da de baja lógica un tipo activo y lo devuelve.

    - Precondición a: Gerente activo. Precondición b: el tipo está activo (``tipo_inactivo``).
    - Precondición c y regla 2: ningún actuador que no esté dado de baja es del tipo; si hay, se rechaza (``equipos_activos``) y se dice
      cuántos son y de qué invernaderos. Se cuentan DESPUÉS de bloquear el tipo.
    - Postcondición a y regla 1: queda «inactivo» y conserva sus acciones. Postcondición b y D-36: un registro ``baja_tipo_actuador``.
    """
    _exigir_gerente(actor)
    with transaction.atomic():
        tipo = _bloquear_tipo(actor, tipo_id)
        if tipo.estado == Estado.INACTIVO:
            raise _error_general("El tipo de actuador ya está dado de baja.", "tipo_inactivo")
        equipos = equipos_afectados(tipo)
        if equipos:
            raise _error_general(mensaje_de_equipos_activos(equipos), "equipos_activos")
        tipo.estado = Estado.INACTIVO
        tipo.save(update_fields=["estado"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_TIPO_ACTUADOR,
            afectados=[tipo],
            detalle=_cambio_de_estado(Estado.ACTIVO.value, Estado.INACTIVO.value),
        )
    return tipo


# ---- consulta (IOT-CNS-TAC) ----


def _consultados(consulta):
    """Los tipos de ``consulta`` con ``cantidad_equipos`` y ``acciones_activas`` (cada una con ``comando`` y su capacidad ya cargados y
    la marca ``en_uso``), en una consulta por cosa."""
    tipos = list(
        consulta.annotate(cantidad_equipos=Count("actuadores", filter=~Q(actuadores__estado_hardware="inactivo")))
        .prefetch_related(
            Prefetch(
                "acciones",
                queryset=Accion.objects.filter(estado=EstadoAccion.ACTIVA).select_related("comando__capacidad").order_by("id"),
                to_attr="acciones_activas",
            )
        )
        .order_by("estado", Lower("nombre_actuador"), "id")
    )
    usos = acciones_en_uso(tipos)  # una sola consulta para toda la lista (no una por tipo)
    for tipo in tipos:
        for accion in tipo.acciones_activas:
            accion.en_uso = accion.pk in usos
    return tipos


def listar_tipos(actor):
    """IOT-CNS-TAC: todos los tipos, activos e inactivos, los activos primero y por nombre (regla 1, sin alcance por invernadero),
    con sus acciones activas y la cantidad de equipos (regla 2). Gerente y Agrónomo activos; otros, ``PermissionDenied``. No audita."""
    _exigir_consulta(actor)
    return _consultados(TipoActuador.objects.all())


def obtener_tipo(actor, tipo_id):
    """IOT-CNS-TAC: el tipo ``tipo_id`` con lo mismo que ``listar_tipos`` (404 si no existe)."""
    _exigir_consulta(actor)
    get_object_or_404(TipoActuador, pk=tipo_id)
    return _consultados(TipoActuador.objects.filter(pk=tipo_id))[0]


def catalogo():
    """El catálogo de capacidades en solo lectura (regla 7 de IOT-ALT-TAC): ``[{"capacidad", "comandos": [{"comando", "unidades"}]}]``,
    con las unidades de cada comando con valor (regla 10)."""
    return [
        {
            "capacidad": capacidad,
            "comandos": [
                {"comando": comando, "unidades": UNIDADES_POR_COMANDO.get(comando.codigo, [])} for comando in capacidad.comandos.all()
            ],
        }
        for capacidad in Capacidad.objects.prefetch_related("comandos").order_by("id")
    ]


def acciones_permitidas(actor, tipo):
    """D-30: las acciones que ``actor`` puede hacer sobre ``tipo``, un ``frozenset`` (regla 3 de IOT-CNS-TAC). Solo el Gerente activo:
    sobre un tipo activo, modificar y dar de baja; sobre uno inactivo, solo reactivar. El Agrónomo solo consulta. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        return frozenset()
    if tipo.estado == Estado.ACTIVO:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})
