# Servicios de Vehículo (COM-01): alta (COM-ALT-VEH), modificación con su reactivación (COM-MOD-VEH), baja (COM-BAJ-VEH) y consulta
# (COM-CNS-VEH), más los dos registrantes que `comercial` suma a `maestros` y a `core`: la «Logística» de la ficha del invernadero
# y el «Vehículo» de la ficha de la cuenta del Transportista. Cada caso de uso es una función dentro de ``transaction.atomic()`` y
# audita con el formato de D-36 (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/comercial/vehiculos.md («Cómo se
# aplica»).
#
# Bloqueos (docs/patrones/bloqueos.md, sección «comercial»; siempre ``FOR NO KEY UPDATE``): las cuentas (quien actúa y los
# transportistas entrante y saliente, en una sola consulta y en orden de id, D-40: las cuentas primero) y, después, el vehículo; todo
# se vuelve a leer ya bloqueado. La base respalda lo que no se puede bloquear: la patente única y el ``OneToOneField`` del
# transportista (``IntegrityError`` traducido al mismo error de campo, nunca un 500).
#
# Lo que completó COM-05a1: ``entregas_a_realizar_del_transportista`` y ``carga_maxima_asignada`` (reglas 2 y 3 de COM-MOD-VEH, precondición c y regla 1 de COM-BAJ-VEH).

import re
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from comercial.models import REGEX_PATENTE, Entrega, Vehiculo
from core import notificaciones
from core.extensiones import DatoDeCuenta
from core.models import RegistroAuditoria, Transportista, Usuario, referencia, rol_de
from maestros.extensiones import Logistica

Estado = Vehiculo.Estado

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
MENSAJE_CAPACIDAD = "Un número mayor que 0, en kg, con hasta 2 decimales."
MENSAJE_EN_RUTA = (
    "El vehículo está en ruta: el producto de las entregas de hoy está cargado. "
    "Podés modificarlo o darlo de baja cuando finalice la ruta."
)
NOTA_DEL_VEHICULO = "Se asigna desde el vehículo, en Comercial › Vehículos."

LARGO_DE_MARCA_Y_MODELO = Vehiculo._meta.get_field("marca").max_length
CAPACIDAD_MAXIMA = Decimal("999999.99")  # DecimalField(8, 2)

FilaDeVehiculo = namedtuple("FilaDeVehiculo", "vehiculo invernadero en_ruta")
FichaDelVehiculo = namedtuple("FichaDelVehiculo", "vehiculo transportista invernadero en_ruta")
OpcionDeTransportista = namedtuple("OpcionDeTransportista", "transportista invernadero")


@dataclass
class DatosDeVehiculo:
    """Lo que carga el formulario del vehículo (alta y modificación). ``transportista_id`` vacío o ``None``: sin transportista."""

    patente: str = ""
    tipo_vehiculo: str = ""
    marca: str = ""
    modelo: str = ""
    capacidad_carga: str = ""
    transportista_id: object = None

    @classmethod
    def desde_post(cls, post):
        """Arma los datos del formulario: cada campo por su nombre."""
        return cls(
            patente=post.get("patente", ""),
            tipo_vehiculo=post.get("tipo_vehiculo", ""),
            marca=post.get("marca", ""),
            modelo=post.get("modelo", ""),
            capacidad_carga=post.get("capacidad_carga", ""),
            transportista_id=post.get("transportista_id", ""),
        )


# ---- lo que completó COM-05a1 ----


def entregas_a_realizar_del_transportista(transportista):
    """Las entregas «a realizar» de ``transportista`` (regla 3 de COM-MOD-VEH; precondición c y regla 1 de COM-BAJ-VEH): sin vehículo no podría concretarlas. Por fecha
    programada e id; lista vacía si no tiene ninguna."""
    return list(Entrega.objects.filter(transportista_id=transportista.pk, estado_orden="a_realizar").order_by("fecha_programada_orden", "pk"))


def carga_maxima_asignada(vehiculo, desde):
    """``(peso, fecha)``: el mayor peso que el transportista del vehículo tiene asignado en un día desde ``desde`` en adelante (la suma del peso de sus entregas no canceladas
    de esa fecha) y esa fecha (regla 2 de COM-MOD-VEH; regla 6 de 8.12); con empate, la más próxima. Sin transportista o sin entregas, ``(0, None)``."""
    from comercial.servicios import entregas

    if vehiculo.transportista_id is None:
        return Decimal("0"), None
    por_dia = defaultdict(list)
    for entrega_id, fecha in (
        Entrega.objects.filter(transportista_id=vehiculo.transportista_id, fecha_programada_orden__gte=desde)
        .exclude(estado_orden="cancelada")
        .values_list("pk", "fecha_programada_orden")
    ):
        por_dia[fecha].append(entrega_id)
    if not por_dia:
        return Decimal("0"), None
    pesos = entregas.peso_de_entregas([e for ids in por_dia.values() for e in ids])
    totales = {fecha: sum((pesos[e] for e in ids), Decimal("0")) for fecha, ids in por_dia.items()}
    fecha = max(totales, key=lambda f: (totales[f], -f.toordinal()))
    return totales[fecha], fecha


# ---- textos ----


def texto_capacidad(capacidad):
    """«800 kg», «800,5 kg», «1.250,25 kg»: kilogramos con coma decimal, punto de miles y sin ceros de más. Lo usan la lista, la
    ficha, las notificaciones, «Logística» y la ficha de la cuenta."""
    entero, decimales = f"{Decimal(capacidad).quantize(Decimal('0.01')):.2f}".split(".")
    entero = f"{int(entero):,}".replace(",", ".")
    decimales = decimales.rstrip("0")
    return f"{entero},{decimales} kg" if decimales else f"{entero} kg"


def _capacidad_auditada(capacidad):
    """La capacidad como texto con dos decimales («800,00»): un ``Decimal`` no entra en la auditoría (D-36)."""
    return f"{Decimal(capacidad).quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _descripcion(vehiculo):
    """«Camioneta AE123CD · 800 kg» (el texto de la «Logística» y de la ficha de la cuenta)."""
    return f"{vehiculo.get_tipo_vehiculo_display()} {vehiculo.patente} · {texto_capacidad(vehiculo.capacidad_carga)}"


# ---- comunes ----


def _exigir_gerente(actor):
    """Precondición a de ALT, MOD, BAJ y CNS: Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede gestionar vehículos.")


def _error(mensaje, codigo):
    """Un error de campo con su código."""
    return [ValidationError(mensaje, code=codigo)]


def _texto(valor):
    """``valor`` como texto recortado (``None`` es vacío)."""
    return "" if valor is None else str(valor).strip()


def _entero_o_none(valor):
    """``valor`` como entero o ``None`` si falta o no es un número."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _normalizar_patente(texto):
    """Regla 1 de ALT (MD-129): mayúsculas, sin espacios ni guiones."""
    return re.sub(r"[\s-]", "", _texto(texto)).upper()


def _capacidad(texto):
    """Regla 3 de ALT: el ``Decimal`` de una capacidad en kg con coma o punto decimal, de hasta dos decimales, mayor que 0 y hasta
    999.999,99; ``None`` si no cumple."""
    texto = _texto(texto)
    if not re.fullmatch(r"\d+([.,]\d{1,2})?", texto):
        return None
    try:
        capacidad = Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None
    return capacidad if 0 < capacidad <= CAPACIDAD_MAXIMA else None


@dataclass
class _Validado:
    """Los datos ya limpios: la patente normalizada, el ``Decimal`` de la capacidad y el id del transportista (o ``None``)."""

    patente: str
    tipo_vehiculo: str
    marca: str
    modelo: str
    capacidad_carga: Decimal
    transportista_id: object


def _validar(datos):
    """Valida y limpia los datos sin tocar la base (patrón ABM, sección 2, paso 2): junta todos los errores en un solo
    ``ValidationError`` con un error por campo. Reglas 1 a 4 de COM-ALT-VEH (lo que depende de la base, después de bloquear)."""
    errores = {}
    patente = _normalizar_patente(datos.patente)
    if not patente:
        errores["patente"] = _error("Ingresá la patente.", "obligatorio")
    elif not re.fullmatch(REGEX_PATENTE, patente):
        errores["patente"] = _error("Ingresá una patente argentina: AAA123 o AA123AA.", "patente_invalida")

    tipo = _texto(datos.tipo_vehiculo)
    if tipo not in Vehiculo.Tipo.values:
        errores["tipo_vehiculo"] = _error("Elegí el tipo de vehículo de la lista.", "tipo_invalido")

    textos = {}
    for campo, mensaje in (("marca", "Ingresá la marca."), ("modelo", "Ingresá el modelo.")):
        textos[campo] = _texto(getattr(datos, campo))
        if not textos[campo]:
            errores[campo] = _error(mensaje, "obligatorio")
        elif len(textos[campo]) > LARGO_DE_MARCA_Y_MODELO:
            errores[campo] = _error(f"Usá como máximo {LARGO_DE_MARCA_Y_MODELO} caracteres.", "demasiado_largo")

    capacidad = _capacidad(datos.capacidad_carga)
    if capacidad is None:
        errores["capacidad_carga"] = _error(MENSAJE_CAPACIDAD, "capacidad_invalida")

    transportista_id = None
    if _texto(datos.transportista_id):
        transportista_id = _entero_o_none(datos.transportista_id)
        if transportista_id is None:
            errores["transportista"] = _error("Elegí un transportista de la lista.", "transportista_invalido")

    if errores:
        raise ValidationError(errores)
    return _Validado(patente, tipo, textos["marca"], textos["modelo"], capacidad, transportista_id)


def _bloquear_cuentas(actor, ids):
    """Las cuentas de quien actúa y de los transportistas que entran o salen, bloqueadas en una sola consulta y en orden de id
    (D-40: las cuentas primero), y verifica que quien actúa siga activo (pudo quedar inactivo mientras esperaba)."""
    ids = sorted({actor.pk, *(i for i in ids if i is not None)})
    filas = list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk"))
    if not any(fila.pk == actor.pk and fila.is_active for fila in filas):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _chequear_base(validado, errores, vehiculo=None):
    """Con las cuentas bloqueadas: la patente no es la de otro vehículo (regla 1, también inactivos) y el transportista es un
    Transportista activo sin otro vehículo (regla 4); el que el vehículo ya tiene se acepta aunque su cuenta esté inactiva.
    Devuelve el ``Transportista`` elegido o ``None``."""
    otros = Vehiculo.objects.exclude(pk=vehiculo.pk) if vehiculo else Vehiculo.objects.all()
    if otros.filter(patente=validado.patente).exists():
        errores["patente"] = _error("Ya hay un vehículo con esa patente.", "patente_repetida")
    if validado.transportista_id is None:
        return None
    if vehiculo and vehiculo.transportista_id == validado.transportista_id:
        return vehiculo.transportista
    transportista = Transportista.objects.filter(pk=validado.transportista_id, is_active=True).first()
    if transportista is None:
        errores["transportista"] = _error("Elegí un transportista activo de la lista.", "transportista_invalido")
    elif otros.filter(transportista=transportista).exists():
        errores["transportista"] = _error("Ese transportista ya tiene otro vehículo.", "transportista_con_vehiculo")
    return transportista


def _traducir_integridad(error, validado, vehiculo=None):
    """Una restricción de la base respaldó a un bloqueo: se informa como el mismo error de campo (nunca un 500)."""
    errores = {}
    _chequear_base(validado, errores, vehiculo)
    if errores:
        raise ValidationError(errores) from error
    raise error


def _referencia_de_cuenta(cuenta):
    """La referencia de una cuenta para ``cambios`` de la auditoría (o ``None``)."""
    return referencia(cuenta) if cuenta else None


def _aviso_de_asignacion(vehiculo, transportista):
    """Postcondición b de ALT y MOD: «Tenés un vehículo asignado»."""
    notificaciones.notificar(
        transportista,
        "Tenés un vehículo asignado",
        f"Desde ahora hacés tus entregas con {vehiculo.get_tipo_vehiculo_display().lower()} {vehiculo.patente} "
        f"({texto_capacidad(vehiculo.capacidad_carga)}).",
    )


def _aviso_de_salida(vehiculo, transportista):
    """Postcondición b de MOD (el saliente): «Ya no tenés el vehículo {patente}»."""
    notificaciones.notificar(
        transportista,
        f"Ya no tenés el vehículo {vehiculo.patente}",
        "No vas a recibir entregas con envío hasta que te asignen otro vehículo.",
    )


# ---- alta, modificación, reactivación y baja ----


def alta_vehiculo(actor, datos):
    """COM-ALT-VEH: registra un vehículo y lo devuelve.

    - Precondición a: Gerente activo. Regla 1 y precondición b: la patente se normaliza y no es la de otro vehículo, activo o
      inactivo (``patente_repetida``). Reglas 2 y 3: tipo de la lista cerrada, marca, modelo y capacidad.
    - Regla 4 y postcondición b: transportista opcional, activo y sin otro vehículo (``transportista_con_vehiculo``); recibe una
      notificación. Postcondición a: nace «activo», sin ruta iniciada. Postcondición c y D-36: ``alta_vehiculo``.
    - Dos vehículos que eligen al mismo transportista a la vez: el segundo recibe el mismo error de campo, nunca un 500.
    """
    _exigir_gerente(actor)
    validado = _validar(datos)
    with transaction.atomic():
        _bloquear_cuentas(actor, [validado.transportista_id])
        errores = {}
        transportista = _chequear_base(validado, errores)
        if errores:
            raise ValidationError(errores)
        try:
            with transaction.atomic():  # punto de guardado: un IntegrityError no aborta la transacción de afuera
                vehiculo = Vehiculo.objects.create(
                    patente=validado.patente,
                    tipo_vehiculo=validado.tipo_vehiculo,
                    marca=validado.marca,
                    modelo=validado.modelo,
                    capacidad_carga=validado.capacidad_carga,
                    transportista=transportista,
                )
        except IntegrityError as error:
            _traducir_integridad(error, validado)
        cambios = {
            "patente": {"antes": None, "despues": vehiculo.patente},
            "tipo_vehiculo": {"antes": None, "despues": vehiculo.tipo_vehiculo},
            "marca": {"antes": None, "despues": vehiculo.marca},
            "modelo": {"antes": None, "despues": vehiculo.modelo},
            "capacidad_carga": {"antes": None, "despues": _capacidad_auditada(vehiculo.capacidad_carga)},
        }
        if transportista:
            cambios["transportista"] = {"antes": None, "despues": referencia(transportista)}
            _aviso_de_asignacion(vehiculo, transportista)
        cambios["estado"] = {"antes": None, "despues": vehiculo.estado_vehiculo}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_VEHICULO,
            afectados=[vehiculo, *([transportista] if transportista else [])],
            detalle={"cambios": cambios},
        )
    return vehiculo


def _pre_leer(vehiculo_id):
    """El vehículo leído sin bloquear, para saber qué cuentas bloquear; 404 si no existe."""
    vehiculo = Vehiculo.objects.filter(pk=vehiculo_id).first()
    if vehiculo is None:
        raise Http404("No existe ese vehículo.")
    return vehiculo


def _bloquear_vehiculo(actor, vehiculo_id, transportista_leido_id, extra=()):
    """Las cuentas (quien actúa, el transportista que tenía y los ``extra``) y, después, el vehículo, bloqueados y leídos de nuevo
    con su estado real. Si mientras esperaba cambió de transportista, ``cambio_simultaneo`` (no se reintenta: reintentar tomaría los
    bloqueos fuera de orden, docs/patrones/bloqueos.md)."""
    _bloquear_cuentas(actor, [transportista_leido_id, *extra])
    vehiculo = Vehiculo.objects.select_for_update(no_key=True).filter(pk=vehiculo_id).first()
    if vehiculo is None:
        raise Http404("No existe ese vehículo.")
    vehiculo.transportista_leido_id = transportista_leido_id
    return vehiculo


def _exigir_sin_cambio_simultaneo(vehiculo):
    """Si el vehículo cambió de transportista mientras esperaba el bloqueo, ``cambio_simultaneo``. Se verifica DESPUÉS del estado
    (un vehículo dado de baja a la vez se informa como inactivo, que es lo que le pasó)."""
    if vehiculo.transportista_id != vehiculo.transportista_leido_id:
        raise ValidationError("El vehículo cambió mientras se procesaba tu pedido. Volvé a intentarlo.", code="cambio_simultaneo")


def _exigir_modificable(vehiculo):
    """Precondición b de MOD y de BAJ: el vehículo está activo (``vehiculo_inactivo``) y no está en ruta (``vehiculo_en_ruta``,
    MD-118)."""
    if not vehiculo.activo:
        raise ValidationError("El vehículo está dado de baja: solo se puede reactivar.", code="vehiculo_inactivo")
    if vehiculo.esta_en_ruta(timezone.localdate()):
        raise ValidationError(MENSAJE_EN_RUTA, code="vehiculo_en_ruta")


def modificar_vehiculo(actor, vehiculo_id, datos):
    """COM-MOD-VEH: actualiza los datos de un vehículo y su transportista, y lo devuelve.

    - Precondición a: Gerente activo. Precondición b: no está en ruta (``vehiculo_en_ruta``). Precondición c: la patente nueva no
      es la de otro vehículo. Regla 4: un vehículo inactivo no se modifica (``vehiculo_inactivo``): solo se reactiva.
    - Regla 2: no se baja la capacidad por debajo del peso asignado desde hoy (``carga_maxima_asignada``, de COM-05). Regla 3: no se
      quita ni se cambia un transportista con entregas «a realizar» (``entregas_a_realizar_del_transportista``, de COM-05).
    - Postcondición b: el transportista entrante y el saliente reciben una notificación. D-28: si nada cambió, no se escribe, no se
      avisa ni se audita. Postcondición d y D-36: ``modificacion_vehiculo``.
    """
    _exigir_gerente(actor)
    leido = _pre_leer(vehiculo_id)
    validado = _validar(datos)
    with transaction.atomic():
        vehiculo = _bloquear_vehiculo(actor, vehiculo_id, leido.transportista_id, [validado.transportista_id])
        _exigir_modificable(vehiculo)
        _exigir_sin_cambio_simultaneo(vehiculo)
        errores = {}
        entrante = _chequear_base(validado, errores, vehiculo)
        saliente = vehiculo.transportista
        cambia_el_transportista = (vehiculo.transportista_id or None) != validado.transportista_id
        hoy = timezone.localdate()
        if not errores.get("capacidad_carga") and saliente and validado.capacidad_carga < vehiculo.capacidad_carga:
            maxima, fecha = carga_maxima_asignada(vehiculo, hoy)
            if maxima > validado.capacidad_carga:
                cuando = f" el {fecha:%d/%m/%Y}" if fecha else ""
                errores["capacidad_carga"] = _error(
                    f"No se puede bajar la capacidad por debajo de {texto_capacidad(maxima)}, el peso que ya tiene asignado{cuando}. "
                    "Reasigná primero esas entregas.",
                    "capacidad_menor_que_la_carga",
                )
        if saliente and cambia_el_transportista and "transportista" not in errores:
            if entregas_a_realizar_del_transportista(saliente):
                errores["transportista"] = _error(
                    "Ese transportista tiene entregas a realizar: reasignalas primero.", "transportista_con_entregas"
                )
        if errores:
            raise ValidationError(errores)

        antes = {
            "patente": vehiculo.patente,
            "tipo_vehiculo": vehiculo.tipo_vehiculo,
            "marca": vehiculo.marca,
            "modelo": vehiculo.modelo,
            "capacidad_carga": vehiculo.capacidad_carga,
        }
        despues = {
            "patente": validado.patente,
            "tipo_vehiculo": validado.tipo_vehiculo,
            "marca": validado.marca,
            "modelo": validado.modelo,
            "capacidad_carga": validado.capacidad_carga,
        }
        cambios = {}
        for campo, valor_anterior in antes.items():
            if valor_anterior != despues[campo]:
                nuevo = despues[campo]
                if campo == "capacidad_carga":
                    valor_anterior, nuevo = _capacidad_auditada(valor_anterior), _capacidad_auditada(nuevo)
                cambios[campo] = {"antes": valor_anterior, "despues": nuevo}
                setattr(vehiculo, campo, despues[campo])
        campos = list(cambios)
        if cambia_el_transportista:
            cambios["transportista"] = {"antes": _referencia_de_cuenta(saliente), "despues": _referencia_de_cuenta(entrante)}
            vehiculo.transportista = entrante
            campos.append("transportista")
        if not cambios:
            return vehiculo  # D-28: sin cambios no se escribe, no se avisa ni se audita
        try:
            with transaction.atomic():
                vehiculo.save(update_fields=campos)
        except IntegrityError as error:
            _traducir_integridad(error, validado, vehiculo)
        if cambia_el_transportista:
            if saliente:
                _aviso_de_salida(vehiculo, saliente)
            if entrante:
                _aviso_de_asignacion(vehiculo, entrante)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_VEHICULO,
            afectados=[vehiculo, *(c for c in (saliente, entrante) if c and cambia_el_transportista)],
            detalle={"cambios": cambios},
        )
    return vehiculo


def reactivar_vehiculo(actor, vehiculo_id):
    """COM-MOD-VEH (postcondición c y regla 4): reactiva un vehículo dado de baja; queda «activo» y **sin transportista**. Uno que no
    está inactivo se rechaza con ``vehiculo_no_inactivo``. Se audita como ``reactivacion_vehiculo``."""
    _exigir_gerente(actor)
    leido = _pre_leer(vehiculo_id)
    with transaction.atomic():
        vehiculo = _bloquear_vehiculo(actor, vehiculo_id, leido.transportista_id)
        if vehiculo.activo:
            raise ValidationError("El vehículo no está dado de baja.", code="vehiculo_no_inactivo")
        _exigir_sin_cambio_simultaneo(vehiculo)
        vehiculo.estado_vehiculo = Estado.ACTIVO
        vehiculo.save(update_fields=["estado_vehiculo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_VEHICULO,
            afectados=[vehiculo],
            detalle={"cambios": {"estado": {"antes": Estado.INACTIVO.value, "despues": Estado.ACTIVO.value}}},
        )
    return vehiculo


def baja_vehiculo(actor, vehiculo_id):
    """COM-BAJ-VEH: da de baja lógica un vehículo y lo devuelve.

    - Precondición a: Gerente activo. Precondición b: activo (``vehiculo_inactivo``) y fuera de ruta (``vehiculo_en_ruta``).
      Precondición c y regla 1: si su transportista tiene entregas «a realizar», no se da de baja
      (``transportista_con_entregas``).
    - Postcondición a: queda «inactivo» y sin transportista, en la misma escritura (la restricción de la base lo exige).
      Postcondición b: el transportista recibe una notificación. Postcondición c y D-36: ``baja_vehiculo``.
    """
    _exigir_gerente(actor)
    leido = _pre_leer(vehiculo_id)
    with transaction.atomic():
        vehiculo = _bloquear_vehiculo(actor, vehiculo_id, leido.transportista_id)
        _exigir_modificable(vehiculo)
        _exigir_sin_cambio_simultaneo(vehiculo)
        transportista = vehiculo.transportista
        if transportista and entregas_a_realizar_del_transportista(transportista):
            raise ValidationError(
                "El transportista tiene entregas a realizar: reasignalas antes de dar de baja el vehículo.",
                code="transportista_con_entregas",
            )
        vehiculo.estado_vehiculo = Estado.INACTIVO
        vehiculo.transportista = None
        vehiculo.save(update_fields=["estado_vehiculo", "transportista"])
        if transportista:
            notificaciones.notificar(
                transportista,
                "Tu vehículo se dio de baja",
                f"El vehículo {vehiculo.patente} se dio de baja. No vas a recibir entregas nuevas hasta que te asignen otro.",
            )
        cambios = {"estado": {"antes": Estado.ACTIVO.value, "despues": Estado.INACTIVO.value}}
        if transportista:
            cambios["transportista"] = {"antes": referencia(transportista), "despues": None}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_VEHICULO,
            afectados=[vehiculo, *([transportista] if transportista else [])],
            detalle={"cambios": cambios},
        )
    return vehiculo


# ---- consulta (COM-CNS-VEH) ----


def _invernadero_de(transportista):
    """El invernadero de ``transportista`` (``TransportistaInvernadero``, D-55) o ``None``; sin consultar si vino precargado."""
    if transportista is None:
        return None
    try:
        return transportista.invernadero_asignado.invernadero
    except ObjectDoesNotExist:
        return None


def buscar_vehiculos(actor, texto="", estado="", invernadero_id=None):
    """COM-CNS-VEH, regla 1: los vehículos por patente (sin importar mayúsculas, espacios ni guiones), tipo o nombre del
    transportista, filtrados por ``estado`` (vacío: todos) y por el invernadero de su transportista, ordenados por patente. Cada
    ``FilaDeVehiculo`` trae el invernadero y si está en ruta hoy (MD-118); el transportista y su invernadero se precargan (sin
    consultas por fila). No audita (SEG-14)."""
    _exigir_gerente(actor)
    lista = (
        Vehiculo.objects.en_alcance_de(actor)
        .select_related("transportista__invernadero_asignado__invernadero")
        .annotate(_transportista=Concat("transportista__first_name", Value(" "), "transportista__last_name"))
    )
    texto = _texto(texto)
    if texto:
        minuscula = texto.lower()
        tipos = [valor for valor, etiqueta in Vehiculo.Tipo.choices if minuscula in etiqueta.lower()]
        lista = lista.filter(
            Q(patente__icontains=_normalizar_patente(texto))
            | Q(tipo_vehiculo__in=tipos)
            | Q(_transportista__icontains=texto)
        )
    if estado in Estado.values:
        lista = lista.filter(estado_vehiculo=estado)
    invernadero = _entero_o_none(invernadero_id)
    if invernadero is not None:
        lista = lista.filter(transportista__invernadero_asignado__invernadero_id=invernadero)
    hoy = timezone.localdate()
    return [
        FilaDeVehiculo(v, _invernadero_de(v.transportista), v.esta_en_ruta(hoy)) for v in lista.order_by("patente", "id")
    ]


def ficha_del_vehiculo(actor, vehiculo_id):
    """COM-CNS-VEH, regla 2: el vehículo con su transportista, el invernadero de este y si está en ruta hoy. La carga asignada
    frente a la capacidad se suma en COM-05a2. 404 si no existe."""
    _exigir_gerente(actor)
    vehiculo = get_object_or_404(
        Vehiculo.objects.en_alcance_de(actor).select_related("transportista__invernadero_asignado__invernadero"), pk=vehiculo_id
    )
    return FichaDelVehiculo(
        vehiculo, vehiculo.transportista, _invernadero_de(vehiculo.transportista), vehiculo.esta_en_ruta(timezone.localdate())
    )


def transportistas_disponibles(actor, vehiculo=None):
    """Regla 4 de COM-ALT-VEH: los transportistas que se ofrecen: activos y sin otro vehículo (más el actual, al modificar), cada
    uno con su invernadero (o ``None``), por apellido y nombre."""
    _exigir_gerente(actor)
    libres = Q(vehiculo__isnull=True)
    if vehiculo is not None and vehiculo.transportista_id:
        libres |= Q(pk=vehiculo.transportista_id)
    transportistas = (
        Transportista.objects.filter(libres, is_active=True)
        .select_related("invernadero_asignado__invernadero")
        .order_by("last_name", "first_name", "id")
    )
    return [OpcionDeTransportista(t, _invernadero_de(t)) for t in transportistas]


def acciones_permitidas(actor, vehiculo):
    """D-30: los botones que ``actor`` ve sobre ``vehiculo`` (un ``frozenset``): solo el Gerente activo; en un activo, «modificar» y
    «baja»; en un inactivo, solo «reactivar» (regla 4 de MOD). Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        return frozenset()
    return frozenset({ACCION_MODIFICAR, ACCION_BAJA} if vehiculo.activo else {ACCION_REACTIVAR})


# ---- lo que `comercial` registra en `maestros` y en `core` ----


def logistica_de_transportistas(transportistas):
    """Lo que `comercial` registra en ``maestros.extensiones.registrar_logistica_de_transportista`` (D-55): ``{id: Logistica}`` con
    el vehículo activo («Camioneta AE123CD · 800 kg» o ``None``), si está en ruta hoy y sus entregas «a realizar» con la URL de la lista de entregas filtrada por él (COM-05a1; sin
    entregas, ``None``). Una consulta por tabla para toda la lista."""
    from comercial.servicios import entregas

    ids = [t.pk for t in transportistas]
    if not ids:
        return {}
    hoy = timezone.localdate()
    a_realizar = dict(
        Entrega.objects.filter(transportista_id__in=ids, estado_orden="a_realizar").values_list("transportista_id").annotate(cantidad=Count("pk")).order_by()
    )
    por_transportista = {
        v.transportista_id: v
        for v in Vehiculo.objects.filter(transportista_id__in=ids, estado_vehiculo=Estado.ACTIVO)
    }
    return {
        pk: Logistica(
            _descripcion(por_transportista[pk]) if pk in por_transportista else None,
            bool(pk in por_transportista and por_transportista[pk].esta_en_ruta(hoy)),
            a_realizar.get(pk, 0),
            entregas.url_de_entregas(transportista=pk) if a_realizar.get(pk) else None,
        )
        for pk in ids
    }


def datos_de_cuenta_del_transportista(cuenta):
    """Lo que `comercial` registra en ``core.extensiones.registrar_datos_de_cuenta`` (decisión del estudiante del 21/11/2026): para
    un Transportista, ``DatoDeCuenta("Vehículo", «Camioneta AE123CD · 800 kg» o «Sin vehículo», nota)``; para los demás roles,
    nada. Una consulta para el Transportista y ninguna para los otros. Un vehículo inactivo no cuenta (no tiene transportista)."""
    if cuenta.rol != Usuario.Rol.TRANSPORTISTA:
        return []
    vehiculo = Vehiculo.objects.filter(transportista_id=cuenta.pk, estado_vehiculo=Estado.ACTIVO).first()
    return [DatoDeCuenta("Vehículo", _descripcion(vehiculo) if vehiculo else "Sin vehículo", NOTA_DEL_VEHICULO)]
