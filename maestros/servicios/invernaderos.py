# Servicios de Invernadero: alta (PROD-ALT-INV) y consulta (PROD-CNS-INV), de MAE-01a, y modificación con su
# reactivación (PROD-MOD-INV) y baja (PROD-BAJ-INV), de MAE-01b. Cada caso de uso es una función dentro de
# ``transaction.atomic()`` y audita con el formato de D-36 (docs/patrones/auditoria.md). D-37: un archivo por entidad
# raíz. MAE-02a (D-41): las alertas de personal faltante se crean, traspasan y resuelven con ``maestros.servicios.alertas``
# y van en los ``datos`` del registro de auditoría; las notificaciones no existen todavía (D-38, D-42). Modelo de
# dominio: ronda 22 (docs/modelo/maestros.md).

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404

from core.extensiones import Asignacion, Efecto, SeccionDeInicio
from core.models import (
    Agronomo,
    Capataz,
    RegistroAuditoria,
    Tecnico,
    Usuario,
    Vendedor,
    referencia,
    rol_de,
)
from maestros import extensiones
from maestros.models import Alerta, Direccion, DireccionRural, DireccionUrbana, Invernadero, Localidad
from maestros.servicios import alertas as api_alertas
from maestros.validadores import validar_con_contenido, validar_kilometro, validar_numero_calle

TIPOS_DE_DIRECCION = ("urbana", "rural")

# Clase de cuenta de cada rol del invernadero (R051, R149, R097 y R134), en el orden en que se muestran.
CLASE_DEL_ROL = {
    "agronomo": Agronomo,
    "capataz": Capataz,
    "vendedor": Vendedor,
    "tecnico": Tecnico,
}
NOMBRE_DEL_ROL = dict(Invernadero.ROLES)

MENSAJE_NOMBRE_REPETIDO = "Ya existe un invernadero con ese nombre."

# Largo máximo de cada texto que carga el alta (D-39, decisión 6): los de las columnas, para rechazarlo con un error de
# campo en vez de dejar que la base lo rechace con un error 500.
LARGOS = {
    "nombre": Invernadero._meta.get_field("nombre_invernadero").max_length,
    "calle": DireccionUrbana._meta.get_field("calle").max_length,
    "numero_calle": DireccionUrbana._meta.get_field("numero_calle").max_length,
    "piso": DireccionUrbana._meta.get_field("piso").max_length,
    "departamento_unidad": DireccionUrbana._meta.get_field("departamento").max_length,
    "barrio": DireccionUrbana._meta.get_field("barrio").max_length,
    "referencias": DireccionUrbana._meta.get_field("referencias").max_length,
    "ruta": DireccionRural._meta.get_field("ruta").max_length,
    "kilometro": DireccionRural._meta.get_field("kilometro").max_length,
    "lote_rural": DireccionRural._meta.get_field("lote").max_length,
}


# Validador de formato o de contenido de cada campo que lo tiene (D-39): el mismo que usa el campo del modelo. El número y
# el kilómetro tienen su formato; los textos libres (calle, ruta y los opcionales) exigen una letra o un número.
FORMATOS = {
    "numero_calle": validar_numero_calle,
    "kilometro": validar_kilometro,
    "calle": validar_con_contenido,
    "ruta": validar_con_contenido,
    "piso": validar_con_contenido,
    "departamento_unidad": validar_con_contenido,
    "barrio": validar_con_contenido,
    "referencias": validar_con_contenido,
    "lote_rural": validar_con_contenido,
}


def _datos_de_alertas(creadas=(), resueltas=(), traspasadas=()):
    """Los ``datos`` de auditoría (D-36) con, solo si no están vacías, las alertas que el caso de uso creó, resolvió o
    traspasó, como referencias (D6 de MAE-02, D-41). Los usa también la baja y la reactivación de una cuenta (D-43)."""
    return {
        clave: [referencia(alerta) for alerta in alertas]
        for clave, alertas in (
            ("alertas_creadas", creadas),
            ("alertas_resueltas", resueltas),
            ("alertas_traspasadas", traspasadas),
        )
        if alertas
    }


def _detalle_con_alertas(cambios, creadas=(), resueltas=(), traspasadas=()):
    """El detalle de auditoría (D-36) con ``cambios`` y, solo si no están vacías, las alertas que el caso de uso creó,
    resolvió o traspasó, como referencias en ``datos`` (D6 de MAE-02, D-41)."""
    detalle = {"cambios": cambios}
    datos = _datos_de_alertas(creadas, resueltas, traspasadas)
    if datos:
        detalle["datos"] = datos
    return detalle


def _tiene_contenido(texto):
    """True si ``texto`` pasa ``validar_con_contenido`` (D-39): tiene al menos una letra o un número."""
    try:
        validar_con_contenido(texto)
    except ValidationError:
        return False
    return True


def _largo_excedido(campo, texto):
    """Error de campo si ``texto`` supera el largo máximo de ``campo``; si no, ``None``."""
    if len(texto) > LARGOS[campo]:
        return _error(f"Usá como máximo {LARGOS[campo]} caracteres.", "demasiado_largo")
    return None


def _exigir_gerente(actor, accion="dar de alta"):
    """Precondición a de PROD-ALT-INV, PROD-MOD-INV y PROD-BAJ-INV: ``actor`` es un Gerente con la cuenta activa
    (SEG-13). ``accion`` es el verbo del mensaje."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied(f"Solo un Gerente activo puede {accion} invernaderos.")


def _exigir_quien_consulta(actor):
    """Precondición a de PROD-CNS-INV: ``actor`` es un Gerente o un Agrónomo con la cuenta activa (SEG-13)."""
    if (
        actor is None
        or not actor.is_active
        or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO)
    ):
        raise PermissionDenied("Tu cuenta no tiene acceso a los invernaderos.")


def _error(mensaje, codigo):
    """Un error de campo con su código."""
    return [ValidationError(mensaje, code=codigo)]


def _entero_o_none(valor):
    """``valor`` como entero, o ``None`` si falta o no es un número (un id mal formado cuenta como no elegido)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _limpiar_direccion(tipo, datos, errores):
    """Regla 2 de PROD-ALT-INV: valida y recorta los datos de la dirección del tipo elegido, y descarta los del otro.
    Devuelve ``{campo: texto}`` solo con los datos del tipo, o ``{}`` si el tipo no es válido."""
    if tipo not in TIPOS_DE_DIRECCION:
        errores["tipo_direccion"] = _error("Elegí si la dirección es urbana o rural.", "tipo_invalido")
        return {}
    if tipo == "urbana":
        obligatorios = {"calle": "Ingresá la calle.", "numero_calle": "Ingresá el número."}
        opcionales = ("piso", "departamento_unidad", "barrio", "referencias")
    else:
        obligatorios = {"ruta": "Ingresá la ruta o el camino.", "kilometro": "Ingresá el kilómetro."}
        opcionales = ("lote_rural",)
    limpios = {}
    for campo in (*obligatorios, *opcionales):
        limpios[campo] = (datos.get(campo) or "").strip()
    for campo, mensaje in obligatorios.items():
        if not limpios[campo]:
            errores[campo] = _error(mensaje, "obligatorio")
    # Formato (D-39): solo de lo que se escribió; vacío ya quedó como «obligatorio».
    for campo, validador in FORMATOS.items():
        if campo in limpios and limpios[campo] and campo not in errores:
            try:
                validador(limpios[campo])
            except ValidationError as error:
                errores[campo] = error.error_list
    for campo, texto in limpios.items():
        if campo not in errores and (error := _largo_excedido(campo, texto)):
            errores[campo] = error
    return limpios


def _buscar_personal(ids, errores, actuales=None):
    """Regla 4 de PROD-ALT-INV: cada persona tiene que ser una cuenta activa de ese rol. Devuelve
    ``{atributo: cuenta}`` solo con los roles que se asignaron.

    ``actuales`` (``{atributo: id}``, solo al modificar): la persona que el invernadero ya tiene en un rol se conserva
    aunque haya quedado inactiva (regla 4 de PROD-MOD-INV: «se muestra con esa marca hasta que se la reemplace»)."""
    actuales = actuales or {}
    personal = {}
    for atributo, clase in CLASE_DEL_ROL.items():
        valor = ids.get(atributo)
        if valor in (None, ""):
            continue
        pk = _entero_o_none(valor)
        conserva = pk is not None and pk == actuales.get(atributo)
        cuenta = clase.objects.filter(pk=pk, **({} if conserva else {"is_active": True})).first()
        if cuenta is None:
            errores[atributo] = _error(
                f"Elegí un {NOMBRE_DEL_ROL[atributo]} activo de la lista.", "persona_invalida"
            )
        else:
            personal[atributo] = cuenta
    return personal


def _crear_direccion(tipo, localidad, datos):
    """Crea la dirección urbana o rural (postcondición b). Los nombres de ``datos`` son los del servicio:
    ``departamento_unidad`` y ``lote_rural`` evitan chocar con otras entidades del glosario (D-39)."""
    if tipo == "urbana":
        return DireccionUrbana.objects.create(
            localidad=localidad,
            calle=datos["calle"],
            numero_calle=datos["numero_calle"],
            piso=datos["piso"],
            departamento=datos["departamento_unidad"],
            barrio=datos["barrio"],
            referencias=datos["referencias"],
        )
    return DireccionRural.objects.create(
        localidad=localidad, ruta=datos["ruta"], kilometro=datos["kilometro"], lote=datos["lote_rural"]
    )


def _validar_nombre(nombre, errores, excluir_pk=None):
    """Regla 1 de PROD-ALT-INV (y de PROD-MOD-INV): obligatorio, con contenido, único entre todos los invernaderos
    sin distinguir mayúsculas ni espacios en los extremos y de hasta 80 caracteres. ``excluir_pk``: el propio
    invernadero, que no cuenta como repetido al modificar. Devuelve el nombre recortado."""
    nombre = (nombre or "").strip()
    repetidos = Invernadero.objects.filter(nombre_invernadero__iexact=nombre)
    if excluir_pk is not None:
        repetidos = repetidos.exclude(pk=excluir_pk)
    if not nombre:
        errores["nombre"] = _error("Ingresá el nombre del invernadero.", "obligatorio")
    elif not _tiene_contenido(nombre):
        errores["nombre"] = _error("Ingresá un texto con al menos una letra o un número.", "sin_contenido")
    elif repetidos.exists():
        errores["nombre"] = _error(MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")
    elif error := _largo_excedido("nombre", nombre):
        errores["nombre"] = error
    return nombre


def _buscar_localidad(localidad_id, errores):
    """Regla 3 de PROD-ALT-INV: la localidad es una de las precargadas de Georef (MD-88)."""
    localidad = (
        Localidad.objects.select_related("departamento__provincia")
        .filter(pk=_entero_o_none(localidad_id))
        .first()
    )
    if localidad is None:
        errores["localidad"] = _error("Elegí la localidad de la lista.", "localidad_invalida")
    return localidad


def alta_invernadero(
    actor,
    nombre,
    *,
    tipo_direccion,
    localidad_id,
    calle="",
    numero_calle="",
    piso="",
    departamento_unidad="",
    barrio="",
    referencias="",
    ruta="",
    kilometro="",
    lote_rural="",
    agronomo_id=None,
    capataz_id=None,
    vendedor_id=None,
    tecnico_id=None,
):
    """PROD-ALT-INV: da de alta un invernadero con su dirección y, si se conoce, su personal; lo devuelve.

    Todo lo que sigue a ``actor`` y ``nombre`` es solo por nombre: son muchos parámetros del mismo tipo y así no
    se pueden pasar en el orden equivocado.

    - Precondición a: ``actor`` es un Gerente activo (``PermissionDenied`` si no).
    - Precondición b y regla 1: nombre obligatorio y único entre todos los invernaderos, activos o inactivos, sin
      distinguir mayúsculas ni espacios al principio o al final (se guarda recortado).
    - Regla 2: dirección urbana (calle y número obligatorios) o rural (ruta y kilómetro obligatorios); los datos
      del otro tipo se ignoran.
    - Regla 3: la localidad es una de las precargadas de Georef (MD-88); no se crea ninguna.
    - Regla 4: el personal es opcional; cada persona es una cuenta activa de ese rol. La regla 5 no exige Técnico.
    - Postcondiciones a, b y c: invernadero activo, sin sectores ni sistema IoT, con su dirección y su personal.
    - Postcondición f, D-22 y D-36: un registro de auditoría, en la misma transacción, con el invernadero y las
      personas asignadas como afectados y los datos cargados en ``cambios`` (con «antes» nulo).
    - Postcondición d y regla 5 (MAE-02a): por cada rol sin asignar queda una alerta activa para el Gerente; la del Técnico
      solo con sistema IoT. Van en ``datos.alertas_creadas`` del registro.
    - Fuera de alcance: las notificaciones (postcondición e; tarea aparte en core, D-42).

    Falla con ``ValidationError`` por campo y no cambia nada.
    """
    _exigir_gerente(actor)
    errores = {}

    nombre = _validar_nombre(nombre, errores)

    datos = _limpiar_direccion(
        tipo_direccion,
        {
            "calle": calle,
            "numero_calle": numero_calle,
            "piso": piso,
            "departamento_unidad": departamento_unidad,
            "barrio": barrio,
            "referencias": referencias,
            "ruta": ruta,
            "kilometro": kilometro,
            "lote_rural": lote_rural,
        },
        errores,
    )

    localidad = _buscar_localidad(localidad_id, errores)

    personal = _buscar_personal(
        {
            "agronomo": agronomo_id,
            "capataz": capataz_id,
            "vendedor": vendedor_id,
            "tecnico": tecnico_id,
        },
        errores,
    )
    if errores:
        raise ValidationError(errores)

    with transaction.atomic():
        direccion = _crear_direccion(tipo_direccion, localidad, datos)
        try:
            # Savepoint: dos altas simultáneas con el mismo nombre las rechaza la restricción de la base; se informa
            # como nombre repetido en vez de un error 500.
            with transaction.atomic():
                invernadero = Invernadero.objects.create(
                    nombre_invernadero=nombre,
                    direccion=direccion,
                    **personal,
                )
        except IntegrityError:
            raise ValidationError({"nombre": _error(MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")})

        # Postcondición d: las alertas de personal faltante (el invernadero ya está bloqueado por su propio INSERT).
        alertas_creadas = api_alertas.sincronizar_alertas_de_personal(invernadero).creadas

        # D-36: ``cambios`` con cada dato cargado y «antes» nulo; los opcionales vacíos no figuran.
        cargados = {
            "nombre": nombre,
            "estado": Invernadero.Estado.ACTIVO.value,
            "tipo_direccion": tipo_direccion,
            "localidad": referencia(localidad),
            **{campo: valor for campo, valor in datos.items() if valor},
            **{atributo: referencia(cuenta) for atributo, cuenta in personal.items()},
        }
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_INVERNADERO,
            afectados=[invernadero, *personal.values()],
            detalle=_detalle_con_alertas(
                {campo: {"antes": None, "despues": valor} for campo, valor in cargados.items()},
                creadas=alertas_creadas,
            ),
        )
    return invernadero


# Todo lo que la lista y la ficha leen de cada invernadero, en una sola consulta.
_RELACIONADOS = (
    "direccion__direccionurbana",
    "direccion__direccionrural",
    "direccion__localidad__departamento__provincia",
    "agronomo",
    "capataz",
    "vendedor",
    "tecnico",
)


def consultar_invernaderos(actor):
    """PROD-CNS-INV: los invernaderos del alcance de ``actor`` (regla 1), activos primero y por nombre.

    - Precondición a: ``actor`` es un Gerente o un Agrónomo activos (``PermissionDenied`` si no).
    - Regla 1 y D-28: el alcance vive en ``Invernadero.objects.en_alcance_de``.
    - Regla 7 y SEG-14: la consulta no se audita.
    """
    _exigir_quien_consulta(actor)
    return (
        Invernadero.objects.en_alcance_de(actor)
        .select_related(*_RELACIONADOS)
        .order_by("estado_invernadero", Lower("nombre_invernadero"))
    )


def obtener_invernadero(actor, invernadero_id):
    """PROD-CNS-INV: el invernadero ``invernadero_id`` si está dentro del alcance de ``actor`` (ficha).

    Un id que no existe da ``Http404``; uno que existe pero está fuera del alcance (el de otro Agrónomo, o uno
    inactivo para el Agrónomo), ``PermissionDenied`` (D-28, SEG-13). No audita (regla 7).
    """
    _exigir_quien_consulta(actor)
    invernadero = get_object_or_404(Invernadero.objects.select_related(*_RELACIONADOS), pk=invernadero_id)
    if not Invernadero.objects.en_alcance_de(actor).filter(pk=invernadero.pk).exists():
        raise PermissionDenied("Este invernadero no está a tu cargo.")
    return invernadero


def cuentas_asignables(atributo):
    """Regla 4 de PROD-ALT-INV: las cuentas activas del rol ``atributo`` (``agronomo``, ``capataz``, ``vendedor`` o
    ``tecnico``) que se ofrecen en el formulario, por apellido y nombre."""
    return CLASE_DEL_ROL[atributo].objects.filter(is_active=True).order_by("last_name", "first_name", "email")


# ---- MAE-01b: modificar (PROD-MOD-INV), reactivar y dar de baja (PROD-BAJ-INV) ----
# Modelo de dominio: ronda 22 (docs/modelo/maestros.md). Orden de los bloqueos (docs/patrones/bloqueos.md, D-30 y D-32),
# siempre ``FOR NO KEY UPDATE`` y el mismo en todos los servicios de este archivo y de las apps que se registren en
# ``maestros.extensiones``:
#   1. las filas de ``Usuario`` de quien actúa y de las cuentas de personal enviadas, en UNA consulta y en orden de id;
#   2. el invernadero (y se vuelve a leer);
#   3. recién después, lo que bloqueen los registrantes de los puntos de extensión.

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
MENSAJE_INACTIVO_NO_SE_MODIFICA = "El invernadero está inactivo: solo se puede reactivar."
MENSAJE_YA_INACTIVO = "El invernadero ya está dado de baja."
MENSAJE_YA_ACTIVO = "El invernadero ya está activo."

# Nombre del atributo del modelo de cada dato de la dirección cuyo nombre en el servicio es otro (D-39).
_ATRIBUTO_DE_LA_DIRECCION = {"departamento_unidad": "departamento", "lote_rural": "lote"}


class FaltaConfirmarPersonal(Exception):
    """Regla 2 de PROD-MOD-INV: hay un cambio de personal que la persona todavía no confirmó. No se guardó nada.

    ``aviso`` es una lista con una entrada por rol que cambia: ``{"rol", "nombre_rol", "saliente", "entrante",
    "recibe", "queda_vacio"}``; ``recibe`` es la lista de ``(descripcion, cantidad)`` que recibiría la persona entrante.
    """

    def __init__(self, aviso):
        super().__init__("Hay un cambio de personal sin confirmar.")
        self.aviso = aviso


def _error_general(mensaje, codigo):
    """Un ``ValidationError`` general (``NON_FIELD_ERRORS``) con ``mensaje`` y ``codigo``."""
    return ValidationError({NON_FIELD_ERRORS: [ValidationError(mensaje, code=codigo)]})


def _actor_sigue_activo(actor):
    """Precondición a, después de esperar los bloqueos: ``actor`` sigue activo ahora. Es una consulta nueva, así que
    ve lo que otra operación confirmó mientras esta esperaba (D-30; igual que ``core.servicios``)."""
    if not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _bloquear_invernadero(invernadero_id):
    """El invernadero ``invernadero_id`` bloqueado (``FOR NO KEY UPDATE``) y leído de nuevo, con su estado real;
    ``Http404`` si no existe. Hay que llamarla dentro de ``transaction.atomic()``, después de bloquear las cuentas
    (orden de bloqueos de arriba)."""
    invernadero = Invernadero.objects.select_for_update(no_key=True).filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    return invernadero


def bloquear_invernadero_activo(invernadero_id):
    """Contrato de los puntos de extensión (D-37, regla A4; docs/patrones/bloqueos.md): todo caso de uso que cree algo
    que impide la baja del invernadero (un lote, una orden, una partida, un movimiento de stock, un transportista, un
    sistema IoT...) lo llama dentro de su transacción y ANTES de crearlo. Bloquea el invernadero (``FOR NO KEY UPDATE``)
    y lo devuelve; si está inactivo, ``ValidationError`` con el código ``invernadero_inactivo``; si no existe,
    ``Http404``.

    La clave foránea sola no alcanza: el ``INSERT`` toma ``FOR KEY SHARE`` sobre el invernadero, y ese bloqueo no choca
    con el ``FOR NO KEY UPDATE`` de la baja. Con este bloqueo, la baja espera a que el creador confirme (y ve lo que
    creó) o el creador espera a la baja (y la ve inactiva).
    """
    invernadero = _bloquear_invernadero(invernadero_id)
    if not invernadero.activo:
        raise _error_general("El invernadero está inactivo: no se puede crear nada sobre él.", "invernadero_inactivo")
    return invernadero


def _ids_actuales(invernadero):
    """``{atributo: id}`` de las personas que el invernadero tiene asignadas hoy (activas o no)."""
    return {atributo: getattr(invernadero, f"{atributo}_id") for atributo, _ in Invernadero.ROLES}


def datos_de_la_direccion(hija):
    """Los datos de una dirección (urbana o rural) con los nombres del servicio y ``None`` en los que están vacíos."""
    if hija.ZONA == "urbana":
        campos = ("calle", "numero_calle", "piso", "departamento_unidad", "barrio", "referencias")
    else:
        campos = ("ruta", "kilometro", "lote_rural")
    return {campo: getattr(hija, _ATRIBUTO_DE_LA_DIRECCION.get(campo, campo)) or None for campo in campos}


def _aviso_de_personal(invernadero, cambiados):
    """Regla 2 de PROD-MOD-INV: por cada rol que cambia, quién sale, quién entra y lo que recibiría la persona
    entrante (lo cuentan los registrantes de ``maestros.extensiones``). Al Agrónomo entrante se suman las alertas activas
    que le pasarían (MAE-02a, D4), como ``("alertas activas", N)``, solo si hay alguna."""
    aviso = []
    for atributo, (saliente, entrante) in cambiados.items():
        recibe = extensiones.contar_traspaso(invernadero, atributo, saliente, entrante)
        if atributo == "agronomo":
            cantidad = api_alertas.contar_alertas_que_recibe(invernadero, saliente, entrante)
            if cantidad:
                recibe = [*recibe, ("alertas activas", cantidad)]
        aviso.append(
            {
                "rol": atributo,
                "nombre_rol": NOMBRE_DEL_ROL[atributo],
                "saliente": saliente,
                "entrante": entrante,
                "recibe": recibe,
                "queda_vacio": entrante is None,
            }
        )
    return aviso


def modificar_invernadero(
    actor,
    invernadero_id,
    nombre,
    *,
    tipo_direccion,
    localidad_id,
    calle="",
    numero_calle="",
    piso="",
    departamento_unidad="",
    barrio="",
    referencias="",
    ruta="",
    kilometro="",
    lote_rural="",
    agronomo_id=None,
    capataz_id=None,
    vendedor_id=None,
    tecnico_id=None,
    personal_confirmado=False,
):
    """PROD-MOD-INV: modifica el nombre, la dirección y el personal de un invernadero activo y lo devuelve.

    Se recibe el formulario completo: un rol sin id queda sin asignar. Todo lo que sigue a ``actor``, ``invernadero_id``
    y ``nombre`` es solo por nombre (D-39).

    - Precondición a: ``actor`` es un Gerente activo (``PermissionDenied``); un id inexistente da ``Http404``.
    - Precondición b y regla 1: el nombre sigue las reglas de PROD-ALT-INV, sin contar el propio invernadero.
    - Reglas 1 a 3 de PROD-ALT-INV (por la regla 1): dirección urbana o rural y localidad de Georef.
    - Regla 4: se ofrecen solo cuentas activas del rol; la persona ya asignada que quedó inactiva se conserva.
    - Regla 5: un invernadero inactivo no se modifica (código ``invernadero_inactivo``).
    - Regla 2: un cambio de personal sin ``personal_confirmado`` lanza ``FaltaConfirmarPersonal`` con el aviso, y no
      guarda nada.
    - Regla 3 y postcondición b: lo que tenía el saliente pasa al entrante (o queda sin responsable, y pasa a quien se
      asigne después); lo hacen los registrantes de ``maestros.extensiones.traspasar``. Las alertas activas del
      Agrónomo pasan al entrante (o al Gerente si el rol queda vacío, MD-61) y las «invernadero sin {rol} activo» del rol
      asignado pasan a «resuelta» (MAE-02a, D4 de D-41).
    - Postcondiciones d y regla 3 de 8.22 (MAE-02a): si dejó un rol sin asignar (o con la persona inactiva), queda una alerta
      activa para el Gerente; la del Técnico solo con sistema IoT. D-28: sin cambios, no se tocan las alertas.
    - Postcondición a: se actualizan el nombre, la dirección y el personal. Si cambia el tipo de dirección se crea la
      nueva y se borra la anterior (D-39, opción A: nada más la referencia todavía).
    - Postcondición f, D-22 y D-36: un registro de auditoría en la misma transacción con lo que cambió; los afectados
      son el invernadero y las personas que salen y entran. D-28: si no cambió nada, no se guarda ni se audita.
    - Fuera de alcance: las notificaciones (postcondición c; tarea aparte en core, D-42).

    Bloqueos (ver el encabezado de esta sección): cuentas y quien actúa, el invernadero y, recién ahí, los traspasos.
    Si dos Gerentes modifican a la vez, gana el último: lo que cambió se calcula contra lo leído después de bloquear.
    """
    _exigir_gerente(actor, "modificar")
    actual = Invernadero.objects.filter(pk=invernadero_id).first()
    if actual is None:
        raise Http404("No existe ese invernadero.")
    if not actual.activo:
        raise _error_general(MENSAJE_INACTIVO_NO_SE_MODIFICA, "invernadero_inactivo")

    ids = {"agronomo": agronomo_id, "capataz": capataz_id, "vendedor": vendedor_id, "tecnico": tecnico_id}
    pedido = {
        "calle": calle,
        "numero_calle": numero_calle,
        "piso": piso,
        "departamento_unidad": departamento_unidad,
        "barrio": barrio,
        "referencias": referencias,
        "ruta": ruta,
        "kilometro": kilometro,
        "lote_rural": lote_rural,
    }

    # Validación previa, sin bloquear: rechaza pronto lo evidente y junta todos los errores de campo.
    errores = {}
    nombre = _validar_nombre(nombre, errores, excluir_pk=actual.pk)
    datos = _limpiar_direccion(tipo_direccion, pedido, errores)
    localidad = _buscar_localidad(localidad_id, errores)
    _buscar_personal(ids, errores, _ids_actuales(actual))
    if errores:
        raise ValidationError(errores)

    with transaction.atomic():
        # 1) Las cuentas de quien actúa y de todo el personal enviado, en una sola consulta y en orden de id. Se
        #    bloquean aunque no cambien: cuál es la entrante se decide recién con el invernadero leído de nuevo, y así
        #    nunca se bloquea una cuenta después del invernadero (orden de baja_usuario: cuenta, y después lo suyo).
        cuentas = {actor.pk} | {pk for pk in map(_entero_o_none, ids.values()) if pk is not None}
        bloqueadas = list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        if not any(cuenta.pk == actor.pk and cuenta.is_active for cuenta in bloqueadas):
            raise PermissionDenied(MENSAJE_SIN_ACCESO)  # la fila de quien actúa ya está bloqueada
        # 2) El invernadero, leído de nuevo con su estado real (regla 5 y D-28).
        invernadero = _bloquear_invernadero(invernadero_id)
        if not invernadero.activo:
            raise _error_general(MENSAJE_INACTIVO_NO_SE_MODIFICA, "invernadero_inactivo")
        # Con las cuentas bloqueadas, la regla 4 se revalida con el estado real (pudo darse de baja una mientras tanto).
        errores = {}
        personal = _buscar_personal(ids, errores, _ids_actuales(invernadero))
        if errores:
            raise ValidationError(errores)

        # Lo que cambia, contra lo que acabamos de leer.
        hija = invernadero.direccion.concreta()
        tipo_actual = hija.ZONA
        cambios = {}
        if nombre != invernadero.nombre_invernadero:
            cambios["nombre"] = {"antes": invernadero.nombre_invernadero, "despues": nombre}
        if tipo_direccion != tipo_actual:
            cambios["tipo_direccion"] = {"antes": tipo_actual, "despues": tipo_direccion}
        antes_de_la_direccion = datos_de_la_direccion(hija)
        despues_de_la_direccion = {campo: valor or None for campo, valor in datos.items()}
        for campo in dict.fromkeys([*antes_de_la_direccion, *despues_de_la_direccion]):
            antes, despues = antes_de_la_direccion.get(campo), despues_de_la_direccion.get(campo)
            if antes != despues:
                cambios[campo] = {"antes": antes, "despues": despues}
        if invernadero.direccion.localidad_id != localidad.pk:
            cambios["localidad"] = {
                "antes": referencia(invernadero.direccion.localidad),
                "despues": referencia(localidad),
            }
        cambiados = {}  # {atributo: (saliente, entrante)}, en el orden de Invernadero.ROLES
        for atributo, _ in Invernadero.ROLES:
            saliente = getattr(invernadero, atributo)
            entrante = personal.get(atributo)
            if (saliente.pk if saliente else None) != (entrante.pk if entrante else None):
                cambiados[atributo] = (saliente, entrante)
                cambios[atributo] = {
                    "antes": referencia(saliente) if saliente else None,
                    "despues": referencia(entrante) if entrante else None,
                }

        # Regla 2: antes de guardar un cambio de personal, la persona confirma lo que va a pasar.
        if cambiados and not personal_confirmado:
            raise FaltaConfirmarPersonal(_aviso_de_personal(invernadero, cambiados))
        if not cambios:
            return invernadero  # D-28

        # Postcondición a. El UPDATE del invernadero (que puede cambiar ``direccion_id``, columna con índice único, y
        # entonces toma FOR UPDATE) va ANTES de llamar a los registrantes de traspaso: así, ninguna transacción que lo
        # haga esperar (porque tiene FOR KEY SHARE sobre el invernadero) puede estar esperando filas de las apps altas
        # que esta ya haya bloqueado, y no se cierra un ciclo de esperas (docs/patrones/bloqueos.md, «Invernadero»).
        campos_a_guardar = []
        direccion_vieja = None
        if "nombre" in cambios:
            invernadero.nombre_invernadero = nombre
            campos_a_guardar.append("nombre_invernadero")
        if tipo_direccion != tipo_actual:
            direccion_vieja = invernadero.direccion_id
            invernadero.direccion = _crear_direccion(tipo_direccion, localidad, datos)
            campos_a_guardar.append("direccion")
        elif any(campo in cambios for campo in (*despues_de_la_direccion, "localidad")):
            hija.localidad = localidad
            for campo, valor in datos.items():
                setattr(hija, _ATRIBUTO_DE_LA_DIRECCION.get(campo, campo), valor)
            hija.save()
        for atributo, (_, entrante) in cambiados.items():
            setattr(invernadero, f"{atributo}_id", entrante.pk if entrante else None)
            campos_a_guardar.append(f"{atributo}_id")
        if campos_a_guardar:
            try:
                # Savepoint: dos renombres simultáneos al mismo nombre los rechaza el índice único de la base; se
                # informa como nombre repetido en vez de un error 500 (D-30).
                with transaction.atomic():
                    invernadero.save(update_fields=campos_a_guardar)
            except IntegrityError as error:
                if "nombre" not in cambios:
                    raise
                raise ValidationError({"nombre": _error(MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")}) from error
        if direccion_vieja is not None:
            Direccion.objects.filter(pk=direccion_vieja).delete()  # D-39, opción A

        # Postcondiciones b y d (MAE-02a): las alertas del Agrónomo pasan al entrante y se sincronizan las de personal. Son
        # filas de ``maestros``: se bloquean después del invernadero y ANTES de las de las apps altas (orden de D-40), por eso
        # van antes de ``extensiones.traspasar`` y se llaman directo, sin pasar por un registrante.
        alertas_traspasadas = []
        if "agronomo" in cambiados:
            saliente, entrante = cambiados["agronomo"]
            alertas_traspasadas = api_alertas.traspasar_alertas_del_agronomo(invernadero, saliente, entrante)
        sincronizadas = api_alertas.sincronizar_alertas_de_personal(invernadero)

        # Postcondición b y regla 3: el traspaso (punto de extensión), con el invernadero ya guardado.
        for atributo, (saliente, entrante) in cambiados.items():
            extensiones.traspasar(actor, invernadero, atributo, saliente, entrante)

        # Postcondición f, D-22 y D-36.
        afectados = [invernadero]
        for saliente, entrante in cambiados.values():
            for cuenta in (saliente, entrante):
                if cuenta is not None and all(cuenta.pk != otra.pk for otra in afectados[1:]):
                    afectados.append(cuenta)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO,
            afectados=afectados,
            detalle=_detalle_con_alertas(
                cambios,
                creadas=sincronizadas.creadas,
                resueltas=sincronizadas.resueltas,
                traspasadas=alertas_traspasadas,
            ),
        )
    return invernadero


def reactivar_invernadero(actor, invernadero_id):
    """PROD-MOD-INV (reactivación; regla 5 de PROD-BAJ-INV): reactiva un invernadero inactivo y lo devuelve.

    - Precondición a: ``actor`` es un Gerente activo; un id inexistente da ``Http404``.
    - Un invernadero ya activo se rechaza con el código ``invernadero_activo``.
    - Postcondición e y regla 6: queda «activo» y una alerta «invernadero sin {rol} activo» por cada rol sin una
      persona activa (MAE-02a); sus sectores y sus insumos siguen inactivos (los reactivan el Agrónomo y Habilitar Insumo en Invernadero): no interviene ningún punto de
      extensión.
    - Postcondición f, D-22 y D-36: un registro ``reactivacion_invernadero`` con el cambio de estado.
    Orden de bloqueos: quien actúa sigue activo; el invernadero.
    """
    _exigir_gerente(actor, "reactivar")
    with transaction.atomic():
        _actor_sigue_activo(actor)
        invernadero = _bloquear_invernadero(invernadero_id)
        if invernadero.activo:
            raise _error_general(MENSAJE_YA_ACTIVO, "invernadero_activo")
        invernadero.estado_invernadero = Invernadero.Estado.ACTIVO
        invernadero.save(update_fields=["estado_invernadero"])
        sincronizadas = api_alertas.sincronizar_alertas_de_personal(invernadero)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_INVERNADERO,
            afectados=[invernadero],
            detalle=_detalle_con_alertas(
                {"estado": {"antes": "inactivo", "despues": "activo"}},
                creadas=sincronizadas.creadas,
                resueltas=sincronizadas.resueltas,
            ),
        )
    return invernadero


def _obtener_para_baja(invernadero_id):
    """El invernadero sin bloquear, para mostrar la ventana de baja (404 si no existe)."""
    invernadero = Invernadero.objects.filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    return invernadero


def impedimentos_para_baja(actor, invernadero_id):
    """PROD-BAJ-INV, regla 2: los impedimentos de la baja, para la ventana de confirmación. Solo lectura: no bloquea,
    no cambia nada y no audita; ``baja_invernadero`` los vuelve a verificar con el invernadero bloqueado.

    Precondición a: ``actor`` es un Gerente activo. Precondición b: uno inactivo se rechaza con
    ``invernadero_inactivo``.
    """
    _exigir_gerente(actor, "dar de baja")
    invernadero = _obtener_para_baja(invernadero_id)
    if not invernadero.activo:
        raise _error_general(MENSAJE_YA_INACTIVO, "invernadero_inactivo")
    return extensiones.impedimentos_de_baja(invernadero)


def baja_invernadero(actor, invernadero_id):
    """PROD-BAJ-INV: da de baja lógica un invernadero activo y lo devuelve.

    - Precondición a: ``actor`` es un Gerente activo; un id inexistente da ``Http404``.
    - Precondición b: el invernadero está activo (``invernadero_inactivo``).
    - Precondiciones c a f y h y regla 2: los registrantes de ``maestros.extensiones.impedimentos_de_baja`` (lotes,
      órdenes, partidas, insumos, sistema IoT) declaran lo que impide la baja; se informan TODOS, cada uno con cómo
      resolverlo, y no se cambia nada. Mientras no haya ninguna app registrada, se dan por cumplidas. La precondición
      g (transportistas activos, regla 3) espera a R155.
    - Postcondición a: queda «inactivo». Postcondición d y regla 1: el personal, la dirección y el nombre se conservan.
    - Postcondiciones b y c: los efectos (sectores e insumos pasan a inactivos) los aplican los registrantes de
      ``maestros.extensiones.aplicar_efectos_de_baja``, que auditan sus propios logs por sector e insumo (f).
    - Postcondición f, D-22 y D-36: un registro ``baja_invernadero`` con el cambio de estado, en la misma transacción.
    - Postcondición e (MAE-02a): las alertas activas del invernadero pasan a «resuelta» y van en ``datos.alertas_resueltas``;
      el invernadero inactivo deja de generar alertas (``maestros.servicios.alertas`` no crea nada sobre él).
    Orden de bloqueos: quien actúa sigue activo; el invernadero; sus alertas activas; recién ahí, los registrantes.
    """
    _exigir_gerente(actor, "dar de baja")
    with transaction.atomic():
        _actor_sigue_activo(actor)
        invernadero = _bloquear_invernadero(invernadero_id)
        if not invernadero.activo:
            raise _error_general(MENSAJE_YA_INACTIVO, "invernadero_inactivo")
        api_alertas.bloquear_alertas_activas(invernadero.pk)  # D-40: las alertas, antes que las filas de las apps altas
        impedimentos = extensiones.impedimentos_de_baja(invernadero)
        if impedimentos:
            raise ValidationError(
                {
                    NON_FIELD_ERRORS: [
                        ValidationError(f"{i.texto} {i.como_resolver}", code=i.codigo) for i in impedimentos
                    ]
                }
            )
        invernadero.estado_invernadero = Invernadero.Estado.INACTIVO
        invernadero.save(update_fields=["estado_invernadero"])
        alertas_resueltas = api_alertas.resolver_alertas_activas(invernadero)
        extensiones.aplicar_efectos_de_baja(actor, invernadero)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_INVERNADERO,
            afectados=[invernadero],
            detalle=_detalle_con_alertas(
                {"estado": {"antes": "activo", "despues": "inactivo"}}, resueltas=alertas_resueltas
            ),
        )
    return invernadero


def acciones_permitidas(actor, invernadero):
    """D-30: las acciones que ``actor`` puede hacer sobre ``invernadero``: un ``frozenset`` (como
    ``core.servicios.acciones_permitidas``) de ``{"modificar", "baja", "reactivar"}``. Solo el Gerente activo
    (regla 6 de PROD-CNS-INV); sobre uno activo modifica y da de baja; sobre uno inactivo solo reactiva (regla 5 de
    PROD-MOD-INV). Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        return frozenset()
    if invernadero.activo:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})


# ---- MAE-02b: cuentas con invernaderos a cargo (USR-BAJ-USR, USR-MOD-USR) y Inicio del Gerente (PROD-CNS-INV) ----
# Se registran en ``core.extensiones`` desde ``MaestrosConfig.ready()`` (regla A4 de D-37). Orden de bloqueos (D-40, D-43):
# la cuenta (que ya bloqueó ``core``), los invernaderos a cargo en orden de id, y las alertas de cada uno en orden de id.
# IMPORTANTE (D-43): el bloqueo previo de TODOS los invernaderos va ANTES de ``traspasar_alertas_del_agronomo``: esta y
# ``bloquear_alertas_activas`` solo bloquean filas de ``Alerta`` y no ven una alerta que otra transacción creó y todavía no
# confirmó; lo que hace esperar al creador es el bloqueo del invernadero (``bloquear_invernadero_para_alertas``).

# Atributo del invernadero de cada rol que tiene invernaderos a cargo (el Gerente, el Administrador y el Transportista no).
ATRIBUTO_DEL_ROL = {
    Usuario.Rol.AGRONOMO: "agronomo",
    Usuario.Rol.CAPATAZ: "capataz",
    Usuario.Rol.VENDEDOR: "vendedor",
    Usuario.Rol.TECNICO: "tecnico",
}
PLANTILLA_DE_INICIO = "maestros/invernaderos/_inicio_personal.html"


def _atributo_del_rol(cuenta):
    """El atributo del invernadero que apunta a las cuentas del rol de ``cuenta``, o ``None`` si ese rol no tiene
    invernaderos a cargo."""
    return ATRIBUTO_DEL_ROL.get(cuenta.rol)


def _bloquear_a_cargo(cuenta, atributo):
    """Bloquea (``FOR NO KEY UPDATE``) todos los invernaderos que tienen a ``cuenta`` en ese rol, en orden de id, y los
    devuelve ya releídos. NO filtra por estado: uno inactivo puede estar reactivándose en otra transacción y, si se lo
    excluyera, la baja no lo vería (D-43, docs/patrones/bloqueos.md: conjunto filtrado). Hay que llamarla dentro de
    ``transaction.atomic()``, con la cuenta ya bloqueada."""
    ids = Invernadero.objects.filter(**{f"{atributo}_id": cuenta.pk}).order_by("pk").values_list("pk", flat=True)
    return [api_alertas.bloquear_invernadero_para_alertas(pk) for pk in list(ids)]


def _efecto_de_alertas(afectados, creadas, resueltas, traspasadas):
    """Un ``Efecto`` con los invernaderos donde cambió alguna alerta y los ``datos`` de auditoría de lo hecho."""
    return Efecto(afectados, _datos_de_alertas(creadas, resueltas, traspasadas))


def efectos_de_baja_de_cuenta(actor, cuenta):
    """Post e de USR-BAJ-USR y regla 4 de 8.22 (MD-61): ``cuenta`` ya está inactiva y bloqueada. Bloquea todos sus
    invernaderos a cargo (sin filtrar por estado), en orden de id; si es un Agrónomo, pasa sus alertas activas al Gerente
    (``traspasar_alertas_del_agronomo`` sin entrante, sin mirar el estado del invernadero); y sincroniza solo la alerta
    «sin {rol}» de su rol (``roles=[rol]``, D-43). Devuelve un ``Efecto`` con los invernaderos donde cambió algo."""
    atributo = _atributo_del_rol(cuenta)
    if atributo is None:
        return Efecto([], {})
    afectados, creadas, resueltas, traspasadas = [], [], [], []
    for invernadero in _bloquear_a_cargo(cuenta, atributo):
        if getattr(invernadero, f"{atributo}_id") != cuenta.pk:
            continue  # lo asignaron a otra persona mientras esperaba el bloqueo: ya no es suyo
        pasadas = []
        if atributo == "agronomo":
            pasadas = api_alertas.traspasar_alertas_del_agronomo(invernadero, invernadero.agronomo, None)
        sincronizadas = api_alertas.sincronizar_alertas_de_personal(invernadero, roles=[atributo])
        if pasadas or sincronizadas.creadas or sincronizadas.resueltas:
            afectados.append(invernadero)
        creadas += sincronizadas.creadas
        resueltas += sincronizadas.resueltas
        traspasadas += pasadas
    return _efecto_de_alertas(afectados, creadas, resueltas, traspasadas)


def efectos_de_reactivacion_de_cuenta(actor, cuenta):
    """Post c de USR-MOD-USR y D8 (D4 de D-41): ``cuenta`` ya está activa y bloqueada. Bloquea sus invernaderos a cargo y,
    si es un Agrónomo, le pasa (con el Agrónomo releído después de bloquear) las alertas que habían ido al Gerente por falta
    de Agrónomo: las ``AGRONOMO_O_GERENTE`` pasan a él y las ``AGRONOMO_Y_GERENTE`` lo suman; después resuelve la alerta
    «sin {rol}» de su rol. Devuelve un ``Efecto`` con los invernaderos donde cambió algo."""
    atributo = _atributo_del_rol(cuenta)
    if atributo is None:
        return Efecto([], {})
    afectados, creadas, resueltas, traspasadas = [], [], [], []
    for invernadero in _bloquear_a_cargo(cuenta, atributo):
        if getattr(invernadero, f"{atributo}_id") != cuenta.pk:
            continue  # lo asignaron a otra persona mientras esperaba el bloqueo: ya no es suyo
        pasadas = []
        if atributo == "agronomo":
            pasadas = api_alertas.traspasar_alertas_del_agronomo(invernadero, None, invernadero.agronomo)
        sincronizadas = api_alertas.sincronizar_alertas_de_personal(invernadero, roles=[atributo])
        if pasadas or sincronizadas.creadas or sincronizadas.resueltas:
            afectados.append(invernadero)
        creadas += sincronizadas.creadas
        resueltas += sincronizadas.resueltas
        traspasadas += pasadas
    return _efecto_de_alertas(afectados, creadas, resueltas, traspasadas)


def _alertas_del_agronomo_a_cargo(cuenta):
    """Las alertas activas que pasarían al Gerente si se diera de baja al Agrónomo ``cuenta``: las suyas, en los invernaderos
    que tiene a cargo, de cualquier estado. Es el mismo conjunto que mueve ``efectos_de_baja_de_cuenta``."""
    return Alerta.objects.filter(estado_alerta="activa", agronomo_id=cuenta.pk, invernadero__agronomo_id=cuenta.pk)


def asignaciones_de_cuenta(cuenta):
    """Regla 4 de USR-BAJ-USR: lo que ``cuenta`` tiene a cargo y qué pasará con eso, para la ventana de baja. Solo lectura:
    no bloquea ni audita. Devuelve una lista de ``core.extensiones.Asignacion``: los invernaderos activos a cargo (por
    nombre, sin distinguir mayúsculas) y, para un Agrónomo con alertas activas (``N > 0``), esas alertas."""
    atributo = _atributo_del_rol(cuenta)
    if atributo is None:
        return []
    asignaciones = []
    activos = list(
        Invernadero.objects.filter(**{f"{atributo}_id": cuenta.pk}, estado_invernadero=Invernadero.Estado.ACTIVO)
        .order_by(Lower("nombre_invernadero"), "pk")
    )
    if activos:
        if atributo == "tecnico" and not any(invernadero.tiene_sistema_iot() for invernadero in activos):
            que_pasa = "Quedan sin Técnico; sin sistema IoT no generan alerta (regla 3 de 8.22). Lo asigna el Gerente al modificarlos."
        else:
            nombre = NOMBRE_DEL_ROL[atributo]
            que_pasa = (
                f"{'Queda' if len(activos) == 1 else 'Cada uno queda'} con la alerta «Invernadero sin {nombre} activo» "
                "para el Gerente hasta que asignes a otra persona al modificarlo."
            )
        asignaciones.append(
            Asignacion(
                "Invernaderos a cargo: " + ", ".join(i.nombre_invernadero for i in activos), len(activos), que_pasa
            )
        )
    if atributo == "agronomo":
        cantidad = _alertas_del_agronomo_a_cargo(cuenta).count()
        if cantidad:
            asignaciones.append(
                Asignacion(
                    "Alertas activas",
                    cantidad,
                    f"{'Pasa' if cantidad == 1 else 'Pasan'} al Gerente hasta que asignes otro Agrónomo (regla 4 de 8.22).",
                )
            )
    return asignaciones


def invernaderos_con_personal_por_asignar(actor):
    """Regla 5 de PROD-CNS-INV: los invernaderos activos con personal por asignar, por nombre (sin distinguir mayúsculas),
    como lista de ``(invernadero, faltantes)`` con ``faltantes`` de ``Invernadero.roles_faltantes()`` (sin persona o con
    la persona inactiva; el Técnico solo con sistema IoT). Sale de lo que falta y no de las alertas, así también cubre los
    invernaderos anteriores a MAE-02a (D9). Precondición: Gerente activo (``PermissionDenied``). No audita (regla 7,
    SEG-14)."""
    _exigir_gerente(actor, "consultar")
    invernaderos = (
        Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO)
        .select_related(*_RELACIONADOS)
        .order_by(Lower("nombre_invernadero"), "pk")
    )
    return [(i, faltantes) for i in invernaderos if (faltantes := i.roles_faltantes())]


def seccion_de_inicio(usuario):
    """Regla 5 de PROD-CNS-INV: la sección «Personal por asignar» del Inicio, para un Gerente activo; ``None`` para
    cualquier otro. El contexto trae ``filas`` (cada una con el ``invernadero`` y su ``detalle``: «Falta Capataz · Vendedor
    inactivo (Nombre)») y ``hay_activos`` (para decir que todo está asignado solo si hay algún invernadero activo)."""
    if usuario is None or not usuario.is_active or rol_de(usuario) != Usuario.Rol.GERENTE:
        return None
    filas = []
    for invernadero, faltantes in invernaderos_con_personal_por_asignar(usuario):
        partes = []
        for atributo, nombre, nunca_asignado in faltantes:
            if nunca_asignado:
                partes.append(f"Falta {nombre}")
            else:
                persona = getattr(invernadero, atributo)
                partes.append(f"{nombre} inactivo ({persona.get_full_name() or persona.email})")
        filas.append({"invernadero": invernadero, "detalle": " · ".join(partes)})
    hay_activos = bool(filas) or Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO).exists()
    return SeccionDeInicio(PLANTILLA_DE_INICIO, {"filas": filas, "hay_activos": hay_activos})
