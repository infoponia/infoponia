# Servicios de Invernadero (MAE-01a): alta (PROD-ALT-INV) y consulta (PROD-CNS-INV). La modificación, la reactivación
# y la baja llegan en MAE-01b. Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el
# formato de D-36 (docs/patrones/auditoria.md). D-37: un archivo por entidad raíz; D-38: sin alertas ni notificaciones.

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404

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
from maestros.models import DireccionRural, DireccionUrbana, Invernadero, Localidad
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


def _exigir_gerente(actor):
    """Precondición a de PROD-ALT-INV: ``actor`` es un Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede dar de alta invernaderos.")


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


def _buscar_personal(ids, errores):
    """Regla 4 de PROD-ALT-INV: cada persona tiene que ser una cuenta activa de ese rol. Devuelve
    ``{atributo: cuenta}`` solo con los roles que se asignaron."""
    personal = {}
    for atributo, clase in CLASE_DEL_ROL.items():
        valor = ids.get(atributo)
        if valor in (None, ""):
            continue
        cuenta = clase.objects.filter(pk=_entero_o_none(valor), is_active=True).first()
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
    - Fuera de alcance (D-38): las alertas de personal faltante (postcondición d) y las notificaciones (e).

    Falla con ``ValidationError`` por campo y no cambia nada.
    """
    _exigir_gerente(actor)
    errores = {}

    nombre = (nombre or "").strip()
    if not nombre:
        errores["nombre"] = _error("Ingresá el nombre del invernadero.", "obligatorio")
    elif not _tiene_contenido(nombre):
        errores["nombre"] = _error("Ingresá un texto con al menos una letra o un número.", "sin_contenido")
    elif Invernadero.objects.filter(nombre_invernadero__iexact=nombre).exists():
        errores["nombre"] = _error(MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")
    elif error := _largo_excedido("nombre", nombre):
        errores["nombre"] = error

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

    localidad = (
        Localidad.objects.select_related("departamento__provincia")
        .filter(pk=_entero_o_none(localidad_id))
        .first()
    )
    if localidad is None:
        errores["localidad"] = _error("Elegí la localidad de la lista.", "localidad_invalida")

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
            detalle={"cambios": {campo: {"antes": None, "despues": valor} for campo, valor in cargados.items()}},
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
