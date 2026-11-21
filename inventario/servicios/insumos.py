# Servicios de Insumo, el catálogo (INV-01): alta (CMP-ALT-INS), modificación con su reactivación (CMP-MOD-INS), baja (CMP-BAJ-INS)
# y consulta (CMP-CNS-INS). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36
# (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/inventario/insumos.md. Misma forma que ``tipos_de_insumo.py`` y
# ``maestros/servicios/cultivos.py`` (docs/patrones/abm.md).
#
# Bloqueos (siempre ``FOR NO KEY UPDATE``; orden de docs/patrones/stock.md, sección 5: invernaderos → TipoInsumo → Insumo →
# InsumoInvernadero, cada grupo en orden de id):
# - Alta: bloquea la categoría ANTES de crear el insumo, para que una baja simultánea de la categoría no deje un insumo activo en una
#   categoría inactiva.
# - Modificación y baja: se leen SIN bloquear las habilitaciones del insumo, se bloquean los invernaderos donde está habilitado
#   (contrato de D-40: quien carga stock bloquea el invernadero antes), la categoría destino si cambia, el insumo y sus
#   ``InsumoInvernadero``, y se vuelve a leer. Si lo leído cambió, ``cambio_simultaneo`` (no se reintenta: tomaría bloqueos fuera de orden).
# Dos nombres iguales a la vez: la restricción única de la base lo respalda y su ``IntegrityError`` se traduce a ``nombre_repetido``.

from collections import defaultdict, namedtuple

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum, Value
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario import extensiones
from inventario.categorias import SEMILLAS, es_semilla
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo, MovimientoInsumo, TipoInsumo
from inventario.servicios.formato import texto_cantidad
from inventario.servicios.tipos_de_insumo import _exigir_agronomo
from inventario.unidades import Unidad
from maestros.models import Invernadero
from maestros.servicios import alertas as api_alertas
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, _tiene_contenido

Estado = Insumo.Estado
EstadoExistencia = InsumoInvernadero.Estado

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

LARGO_DEL_NOMBRE = Insumo._meta.get_field("nombre_insumo").max_length
LARGO_DE_LA_DESCRIPCION = Insumo._meta.get_field("descripcion_insumo").max_length
MENSAJE_NOMBRE_REPETIDO = "Ya existe un insumo con ese nombre."
RESTRICCION_NOMBRE_UNICO = "insumo_nombre_unico"
# Clave de la alerta «bajo el mínimo» de un insumo en un invernadero (docs/patrones/stock.md, sección 4; decidido en INV-01).
TIPO_DE_ALERTA_BAJO_MINIMO = "inv_insumo_bajo_minimo"

# Un impedimento de la baja del insumo, de UN invernadero (regla 2 de CMP-BAJ-INS): qué pasa y cómo resolverlo.
ImpedimentoDeBaja = namedtuple("ImpedimentoDeBaja", "invernadero codigo texto como_resolver")


# ---- quién usa el insumo y quién lo gestiona (regla 1 de CMP-MOD-INS) ----


def _nombre_del_agronomo(invernadero):
    """El nombre del Agrónomo activo del invernadero o «sin Agrónomo»."""
    agronomo = invernadero.agronomo
    if agronomo is None or not agronomo.is_active:
        return "sin Agrónomo"
    return agronomo.get_full_name() or agronomo.email


def _por_nombre(invernaderos):
    return sorted(invernaderos, key=lambda invernadero: (invernadero.nombre_invernadero.lower(), invernadero.pk))


def _usos_de(insumo_ids):
    """``{insumo_id: [Invernadero, ...]}``: «un invernadero usa el insumo si está activo y lo tiene habilitado» (regla 1 de
    CMP-MOD-INS), por nombre y con su Agrónomo a mano. Una sola consulta para toda la lista."""
    usos = defaultdict(list)
    existencias = InsumoInvernadero.objects.filter(
        insumo_id__in=list(insumo_ids),
        estado_insumo_invernadero=EstadoExistencia.ACTIVO,
        invernadero__estado_invernadero=Invernadero.Estado.ACTIVO,
    ).select_related("invernadero", "invernadero__agronomo")
    for existencia in existencias:
        usos[existencia.insumo_id].append(existencia.invernadero)
    return {i: _por_nombre(usos[i]) for i in insumo_ids}


def _usan_desde(existencias):
    """Los invernaderos que usan el insumo, a partir de sus ``InsumoInvernadero`` ya leídos (con el invernadero)."""
    return _por_nombre(
        [e.invernadero for e in existencias if e.activo and e.invernadero.activo]
    )


def invernaderos_que_usan(insumo_id):
    """CMP-MOD-INS regla 1 y CMP-CNS-INS regla 3: los invernaderos activos que tienen el insumo habilitado, por nombre. Solo
    lectura. La pantalla pide con esta función la lista de a quiénes se avisará (regla 5)."""
    return _usos_de([insumo_id])[insumo_id]


def _textos_de_quienes_usan(invernaderos):
    return [f"{i.nombre_invernadero} ({_nombre_del_agronomo(i)})" for i in invernaderos]


def quienes_lo_usan(insumo_id):
    """CMP-CNS-INS regla 3: «<invernadero> (<Agrónomo>)» o «<invernadero> (sin Agrónomo)» de cada invernadero que usa el insumo; es el
    texto de las acciones deshabilitadas."""
    return _textos_de_quienes_usan(invernaderos_que_usan(insumo_id))


def _es_agronomo_activo(actor):
    return actor is not None and actor.is_active and rol_de(actor) == Usuario.Rol.AGRONOMO


def puede_gestionar(actor, insumo, usan=None):
    """CMP-MOD-INS regla 1: un Agrónomo activo gestiona el insumo si es el Agrónomo de algún invernadero que lo usa; si ningún
    invernadero lo usa, cualquier Agrónomo activo. ``usan`` es la lista de invernaderos ya leída (por ejemplo, ``habilitado_en`` de
    ``consultar_insumos``); si no se pasa, se consulta."""
    if not _es_agronomo_activo(actor):
        return False
    if usan is None:
        usan = invernaderos_que_usan(insumo.pk)
    return not usan or any(invernadero.agronomo_id == actor.pk for invernadero in usan)


def _exigir_que_pueda_gestionar(actor, insumo, usan):
    """Precondición b de MOD y BAJ: si no puede gestionarlo, se le informa qué invernaderos lo usan y quiénes son sus Agrónomos."""
    if not puede_gestionar(actor, insumo, usan):
        raise _error_general(
            f"Lo usan {', '.join(_textos_de_quienes_usan(usan))}. Solo lo gestiona el Agrónomo de alguno de esos invernaderos.",
            "insumo_en_uso_por_otros",
        )


def _exigir_activo_y_que_no_sea_semilla(insumo):
    """Precondición c de MOD y BAJ: el insumo no es una semilla (se gestiona con su variedad) y está activo."""
    if es_semilla(insumo):
        raise _error_general(
            "Es una semilla: viene del alta de su variedad y se modifica y se da de baja con ella.", "insumo_semilla"
        )
    if insumo.estado_insumo == Estado.INACTIVO:
        raise _error_general("El insumo está inactivo: solo se puede reactivar.", "insumo_inactivo")


# ---- validación de los datos (sin tocar la base) ----


def _agregar(errores, campo, mensaje, codigo):
    """Anota un error de campo (el primero de cada campo manda)."""
    errores.setdefault(campo, [ValidationError(mensaje, code=codigo)])


def _normalizar(nombre, descripcion, tipo_insumo_id, unidad, controla_vencimiento):
    """Reglas 2 a 6 de CMP-ALT-INS sin tocar la base. Devuelve ``(datos, errores)``: ``datos`` con el nombre y la descripción
    recortados, el id de la categoría como ``int`` (o ``None``) y la unidad; ``errores`` con un error por campo."""
    errores = {}
    nombre = nombre.strip() if isinstance(nombre, str) else ("" if nombre is None else str(nombre).strip())
    if not nombre:
        _agregar(errores, "nombre", "Ingresá el nombre del insumo.", "obligatorio")
    elif not _tiene_contenido(nombre):
        _agregar(errores, "nombre", "Ingresá un texto con al menos una letra o un número.", "sin_contenido")
    elif len(nombre) > LARGO_DEL_NOMBRE:
        _agregar(errores, "nombre", f"Usá como máximo {LARGO_DEL_NOMBRE} caracteres.", "demasiado_largo")
    descripcion = descripcion.strip() if isinstance(descripcion, str) else ("" if descripcion is None else str(descripcion).strip())
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        _agregar(errores, "descripcion", f"Usá como máximo {LARGO_DE_LA_DESCRIPCION} caracteres.", "demasiado_largo")
    tipo_id = None
    if tipo_insumo_id in (None, ""):
        _agregar(errores, "categoria", "Elegí la categoría.", "obligatorio")
    else:
        try:
            tipo_id = int(tipo_insumo_id)
        except (TypeError, ValueError):
            _agregar(errores, "categoria", "Elegí una categoría de la lista.", "invalida")
    if not unidad:
        _agregar(errores, "unidad", "Elegí la unidad de medida.", "obligatorio")
    elif unidad not in Unidad.values:
        _agregar(errores, "unidad", "Elegí una de las unidades de la lista.", "invalida")
    datos = {
        "nombre": nombre,
        "descripcion": descripcion,
        "tipo_id": tipo_id,
        "unidad": unidad,
        "controla_vencimiento": bool(controla_vencimiento),
    }
    return datos, errores


def _nombre_repetido(nombre, excluir_pk=None):
    """True si ya hay un insumo con ese nombre, sin distinguir mayúsculas, activo o inactivo (regla 2 de CMP-ALT-INS)."""
    existentes = Insumo.objects.annotate(_minuscula=Lower("nombre_insumo"))
    if excluir_pk is not None:
        existentes = existentes.exclude(pk=excluir_pk)
    return existentes.filter(_minuscula=Lower(Value(nombre))).exists()


def _guardar(insumo, campos=None):
    """Guarda el insumo; si dos pedidos eligieron el mismo nombre a la vez, el segundo recibe el ``IntegrityError`` de la
    restricción única y se traduce al mismo error de campo (nunca un 500)."""
    try:
        with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
            insumo.save(update_fields=campos) if campos else insumo.save()
    except IntegrityError as error:
        if RESTRICCION_NOMBRE_UNICO in str(error):
            raise ValidationError(
                {"nombre": [ValidationError(MENSAJE_NOMBRE_REPETIDO, code="nombre_repetido")]}
            ) from error
        raise


def _validar_categoria_destino(errores, tipo):
    """Regla 4 de CMP-ALT-INS: la categoría existe, está activa y no es Semillas. Solo anota el error."""
    if tipo is None:
        _agregar(errores, "categoria", "Elegí una categoría de la lista.", "invalida")
    elif tipo.codigo == SEMILLAS:
        _agregar(
            errores,
            "categoria",
            "Las semillas no se cargan acá: se crean solas al dar de alta una variedad.",
            "categoria_de_semillas",
        )
    elif tipo.estado_tipo_insumo != TipoInsumo.Estado.ACTIVO:
        _agregar(errores, "categoria", "La categoría está inactiva: elegí otra o reactivala.", "categoria_inactiva")


# ---- alta ----


def alta_insumo(actor, *, nombre, tipo_insumo_id, unidad, descripcion="", controla_vencimiento=False):
    """CMP-ALT-INS: crea un insumo activo, sin habilitar en ningún invernadero, y lo devuelve.

    - Precondición a y regla 1: ``actor`` es un Agrónomo activo (cualquiera: el catálogo es el mismo para toda la organización).
    - Precondición b y regla 2: nombre obligatorio, con contenido, de hasta 100 y único entre todos los insumos, activos o inactivos,
      sin distinguir mayúsculas ni espacios al borde (``nombre_repetido``). Regla 3: descripción opcional, de hasta 300.
    - Regla 4: la categoría se elige entre las activas y no es Semillas. Regla 5: la unidad es una de las ocho. Regla 6:
      ``controla_vencimiento``. TODOS los errores de campo vienen juntos en un solo ``ValidationError``.
    - Bloquea la categoría antes de crear el insumo (una baja simultánea de la categoría espera o se rechaza).
    - Postcondición a y b, D-22 y D-36: queda «activo» y un registro ``alta_insumo`` en la misma transacción. La regla 7 (ofrecer
      habilitarlo) es de la pantalla.
    """
    _exigir_agronomo(actor)
    datos, errores = _normalizar(nombre, descripcion, tipo_insumo_id, unidad, controla_vencimiento)
    with transaction.atomic():
        tipo = None
        if datos["tipo_id"] is not None:
            tipo = TipoInsumo.objects.select_for_update(no_key=True).filter(pk=datos["tipo_id"]).first()
            _validar_categoria_destino(errores, tipo)
        _actor_sigue_activo(actor)
        if "nombre" not in errores and _nombre_repetido(datos["nombre"]):
            _agregar(errores, "nombre", MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")
        if errores:
            raise ValidationError(errores)
        insumo = Insumo(
            nombre_insumo=datos["nombre"],
            descripcion_insumo=datos["descripcion"],
            tipo_insumo=tipo,
            unidad_medida_insumo=datos["unidad"],
            controla_vencimiento=datos["controla_vencimiento"],
            estado_insumo=Estado.ACTIVO,
        )
        _guardar(insumo)
        cambios = {"nombre": {"antes": None, "despues": datos["nombre"]}}
        if datos["descripcion"]:
            cambios["descripcion"] = {"antes": None, "despues": datos["descripcion"]}
        cambios["categoria"] = {"antes": None, "despues": referencia(tipo)}
        cambios["unidad_medida"] = {"antes": None, "despues": datos["unidad"]}
        cambios["controla_vencimiento"] = {"antes": None, "despues": datos["controla_vencimiento"]}
        cambios["estado"] = {"antes": None, "despues": Estado.ACTIVO.value}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_INSUMO,
            afectados=[insumo],
            detalle={"cambios": cambios},
        )
    return insumo


# ---- bloqueos de modificar y de baja ----


def _bloquear(actor, insumo_id, tipo_destino_id=None):
    """Toma los bloqueos en el orden de docs/patrones/stock.md (sección 5) y devuelve ``(insumo, existencias)`` ya leídos de nuevo:
    1. se leen SIN bloquear las habilitaciones del insumo (404 si no existe); 2. se bloquean los invernaderos donde está habilitado,
    en orden de id; 3. las categorías (la actual y la destino, si cambia), en orden de id; 4. el insumo; 5. sus ``InsumoInvernadero``,
    en orden de id. Si lo leído cambió (otra operación lo movió mientras esperaba), ``cambio_simultaneo``. Hay que llamarla dentro
    de ``transaction.atomic()``."""
    leido = Insumo.objects.filter(pk=insumo_id).first()
    if leido is None:
        raise Http404("No existe ese insumo.")
    invernadero_ids = set(
        InsumoInvernadero.objects.filter(insumo_id=insumo_id).values_list("invernadero_id", flat=True)
    )
    list(Invernadero.objects.select_for_update(no_key=True).filter(pk__in=invernadero_ids).order_by("id"))
    if tipo_destino_id is not None and tipo_destino_id != leido.tipo_insumo_id:
        tipos = {leido.tipo_insumo_id, tipo_destino_id}
        list(TipoInsumo.objects.select_for_update(no_key=True).filter(pk__in=tipos).order_by("id"))
    insumo = Insumo.objects.select_for_update(no_key=True, of=("self",)).select_related("tipo_insumo").get(pk=insumo_id)
    _actor_sigue_activo(actor)
    existencias = list(
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",))
        .filter(insumo_id=insumo_id)
        .select_related("insumo", "invernadero", "invernadero__agronomo")
        .order_by("id")
    )
    if insumo.tipo_insumo_id != leido.tipo_insumo_id or {e.invernadero_id for e in existencias} != invernadero_ids:
        raise _error_general("El insumo cambió mientras se procesaba. Volvé a intentarlo.", "cambio_simultaneo")
    return insumo, existencias


# ---- modificación ----


def a_quienes_avisara(actor, insumo_id):
    """CMP-MOD-INS regla 5: los invernaderos cuyo Agrónomo recibirá el aviso del cambio (los que usan el insumo, sin el actor; uno sin
    Agrónomo activo no genera aviso), por nombre. La pantalla lo informa ANTES de confirmar; el aviso no bloquea el cambio. Solo
    lectura."""
    _exigir_agronomo(actor)
    if not Insumo.objects.filter(pk=insumo_id).exists():
        raise Http404("No existe ese insumo.")
    return _a_avisar(actor, invernaderos_que_usan(insumo_id))


def _a_avisar(actor, usan):
    """De los invernaderos que usan el insumo, los que tienen un Agrónomo activo distinto de ``actor``."""
    return [
        invernadero
        for invernadero in usan
        if invernadero.agronomo is not None and invernadero.agronomo.is_active and invernadero.agronomo.pk != actor.pk
    ]


def _tuvo_stock_o_movimientos(insumo):
    """Regla 3 de CMP-MOD-INS: el insumo tuvo algún lote o movimiento en cualquier invernadero (aunque sea de una habilitación inactiva)."""
    return (
        LoteInsumo.objects.filter(insumo_invernadero__insumo=insumo).exists()
        or MovimientoInsumo.objects.filter(lote_insumo__insumo_invernadero__insumo=insumo).exists()
    )


def _stock_total(insumo):
    """Suma de la cantidad disponible de todos los lotes del insumo (incluido el faltante) y si algún lote tiene stock distinto de cero."""
    lotes = LoteInsumo.objects.filter(insumo_invernadero__insumo=insumo).exclude(cantidad_disponible=0)
    return lotes.aggregate(total=Sum("cantidad_disponible"))["total"], lotes.exists()


def _error_de_reservas_al_cambiar_de_categoria(existencias, insumo):
    """Regla 3 de CMP-MOD-INS: texto de lo reservado por órdenes a realizar (con las órdenes), o ``None`` si no hay reservas."""
    if not existencias:
        return None
    ids = [e.pk for e in existencias]
    reservado = extensiones.reservado_de(ids)
    con_reservas = [e for e in existencias if reservado[e.pk] > 0]
    if not con_reservas:
        return None
    ordenes = extensiones.ordenes_que_reservan([e.pk for e in con_reservas])
    partes = []
    for existencia in con_reservas:
        cantidad = texto_cantidad(reservado[existencia.pk], insumo.unidad_medida_insumo)
        nombres = ", ".join(orden.texto for orden in ordenes.get(existencia.pk, []))
        partes.append(f"{cantidad} en {existencia.invernadero.nombre_invernadero}" + (f" ({nombres})" if nombres else ""))
    return "No puede pasar a una categoría con otro consumo directo: tiene reservados " + "; ".join(partes) + " por órdenes a realizar."


def bloqueos_de_modificacion(insumo):
    """Regla 3 de CMP-MOD-INS, solo lectura: ``{campo: motivo}`` de los campos que hoy NO se pueden cambiar (``unidad``, ``categoria``,
    ``controla_vencimiento``), con el mismo texto que da ``modificar_insumo``. La pantalla los muestra bloqueados con su motivo
    (``insLocks`` del prototipo); el servicio los vuelve a exigir con todo bloqueado, así que esto es solo informativo."""
    bloqueos = {}
    if _tuvo_stock_o_movimientos(insumo):
        bloqueos["unidad"] = "No se cambia: el insumo ya tuvo stock o movimientos."
    if insumo.tipo_insumo.es_del_sistema:
        bloqueos["categoria"] = f"No se cambia: «{insumo.tipo_insumo}» es una categoría del sistema."
    total, con_stock = _stock_total(insumo)
    if con_stock:
        bloqueos["controla_vencimiento"] = (
            f"No se cambia mientras tenga stock ({texto_cantidad(total, insumo.unidad_medida_insumo)} en total)."
        )
    return bloqueos


def modificar_insumo(actor, insumo_id, *, nombre, tipo_insumo_id, unidad, descripcion="", controla_vencimiento=False):
    """CMP-MOD-INS: actualiza los datos de un insumo y lo devuelve.

    - Precondición a: Agrónomo activo. Precondición b y regla 1: ``actor`` puede gestionarlo (``insumo_en_uso_por_otros``).
      Precondición c y regla 4: no es una semilla (``insumo_semilla``). Regla 6: uno inactivo solo se reactiva (``insumo_inactivo``).
    - Precondición d y regla 2: los datos se validan con las reglas 2 a 6 de CMP-ALT-INS; el nombre no lo tiene otro insumo.
    - Regla 3, campo por campo y solo si el valor CAMBIA (cada uno, un error en su campo): ``unidad`` (``unidad_bloqueada``: ya tuvo lotes o
      movimientos), ``controla_vencimiento`` (``vencimiento_bloqueado``: tiene stock distinto de cero), ``categoria``
      (``categoria_del_sistema``, ``categoria_destino_del_sistema``, ``categoria_inactiva``, ``reservas_activas``).
    - D-28: sin cambios no se escribe, no se audita y no se avisa. Postcondición a y d, D-36: ``modificacion_insumo`` con lo que cambió.
    - Postcondición b y regla 5: UNA llamada a ``notificar_a_varios`` al Agrónomo de cada otro invernadero que lo usa (sin el actor y sin
      repetir cuentas), dentro de la transacción. El aviso no bloquea el cambio.
    """
    _exigir_agronomo(actor)
    datos, errores = _normalizar(nombre, descripcion, tipo_insumo_id, unidad, controla_vencimiento)
    with transaction.atomic():
        insumo, existencias = _bloquear(actor, insumo_id, datos["tipo_id"])
        _exigir_activo_y_que_no_sea_semilla(insumo)
        usan = _usan_desde(existencias)
        _exigir_que_pueda_gestionar(actor, insumo, usan)
        if "nombre" not in errores and _nombre_repetido(datos["nombre"], excluir_pk=insumo.pk):
            _agregar(errores, "nombre", MENSAJE_NOMBRE_REPETIDO, "nombre_repetido")
        unidad_cambia = "unidad" not in errores and datos["unidad"] != insumo.unidad_medida_insumo
        if unidad_cambia and _tuvo_stock_o_movimientos(insumo):
            _agregar(errores, "unidad", "No se cambia: el insumo ya tuvo stock o movimientos.", "unidad_bloqueada")
        controla_cambia = datos["controla_vencimiento"] != insumo.controla_vencimiento
        if controla_cambia:
            total, con_stock = _stock_total(insumo)
            if con_stock:
                _agregar(
                    errores,
                    "controla_vencimiento",
                    f"No se cambia mientras tenga stock ({texto_cantidad(total, insumo.unidad_medida_insumo)} en total).",
                    "vencimiento_bloqueado",
                )
        tipo_nuevo = insumo.tipo_insumo
        if "categoria" not in errores and datos["tipo_id"] != insumo.tipo_insumo_id:
            tipo_nuevo = TipoInsumo.objects.filter(pk=datos["tipo_id"]).first()
            if insumo.tipo_insumo.es_del_sistema:
                _agregar(errores, "categoria", f"No se cambia: «{insumo.tipo_insumo}» es una categoría del sistema.", "categoria_del_sistema")
            elif tipo_nuevo is not None and tipo_nuevo.es_del_sistema:
                _agregar(
                    errores,
                    "categoria",
                    "Las categorías del sistema no se ofrecen: un insumo no entra ni sale de ellas.",
                    "categoria_destino_del_sistema",
                )
            else:
                _validar_categoria_destino(errores, tipo_nuevo)
                if "categoria" not in errores and tipo_nuevo.consumo_directo != insumo.tipo_insumo.consumo_directo:
                    texto = _error_de_reservas_al_cambiar_de_categoria(existencias, insumo)
                    if texto:
                        _agregar(errores, "categoria", texto, "reservas_activas")
        if errores:
            raise ValidationError(errores)
        cambios = {}
        if datos["nombre"] != insumo.nombre_insumo:
            cambios["nombre"] = {"antes": insumo.nombre_insumo, "despues": datos["nombre"]}
        if datos["descripcion"] != insumo.descripcion_insumo:
            cambios["descripcion"] = {"antes": insumo.descripcion_insumo, "despues": datos["descripcion"]}
        if tipo_nuevo.pk != insumo.tipo_insumo_id:
            cambios["categoria"] = {"antes": referencia(insumo.tipo_insumo), "despues": referencia(tipo_nuevo)}
        if unidad_cambia:
            cambios["unidad_medida"] = {"antes": insumo.unidad_medida_insumo, "despues": datos["unidad"]}
        if controla_cambia:
            cambios["controla_vencimiento"] = {"antes": insumo.controla_vencimiento, "despues": datos["controla_vencimiento"]}
        if not cambios:
            return insumo
        nombre_anterior = insumo.nombre_insumo
        insumo.nombre_insumo = datos["nombre"]
        insumo.descripcion_insumo = datos["descripcion"]
        insumo.tipo_insumo = tipo_nuevo
        insumo.unidad_medida_insumo = datos["unidad"]
        insumo.controla_vencimiento = datos["controla_vencimiento"]
        _guardar(
            insumo,
            ["nombre_insumo", "descripcion_insumo", "tipo_insumo", "unidad_medida_insumo", "controla_vencimiento"],
        )
        cuentas = [invernadero.agronomo for invernadero in _a_avisar(actor, usan)]
        if cuentas:
            notificaciones.notificar_a_varios(
                cuentas,
                f"Cambió el insumo {nombre_anterior}",
                f"{actor.get_full_name() or actor.email} modificó sus datos en el catálogo. Revisá si afecta a tus invernaderos.",
                excluir=actor,
            )
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO,
            afectados=[insumo],
            detalle={"cambios": cambios},
        )
    return insumo


def reactivar_insumo(actor, insumo_id):
    """CMP-MOD-INS (postcondición c y regla 6): reactiva un insumo dado de baja y lo devuelve. Solo si su categoría está activa
    (``categoria_inactiva``); no lo vuelve a habilitar en ningún invernadero (sus ``InsumoInvernadero`` siguen inactivos). Protecciones:
    una semilla (``insumo_semilla``) y uno que no está dado de baja (``insumo_no_inactivo``). Un insumo inactivo no lo usa ningún
    invernadero, así que lo reactiva cualquier Agrónomo activo. Bloquea categoría → insumo. Se audita como ``reactivacion_insumo``."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        leido = Insumo.objects.filter(pk=insumo_id).first()
        if leido is None:
            raise Http404("No existe ese insumo.")
        tipo = TipoInsumo.objects.select_for_update(no_key=True).get(pk=leido.tipo_insumo_id)
        insumo = Insumo.objects.select_for_update(no_key=True).get(pk=insumo_id)
        _actor_sigue_activo(actor)
        if insumo.tipo_insumo_id != tipo.pk:
            raise _error_general("El insumo cambió mientras se procesaba. Volvé a intentarlo.", "cambio_simultaneo")
        insumo.tipo_insumo = tipo
        if es_semilla(insumo):
            raise _error_general("Es una semilla: se reactiva junto con su variedad.", "insumo_semilla")
        if insumo.estado_insumo != Estado.INACTIVO:
            raise _error_general("El insumo no está dado de baja.", "insumo_no_inactivo")
        if tipo.estado_tipo_insumo != TipoInsumo.Estado.ACTIVO:
            raise _error_general(
                f"No se puede reactivar: la categoría {tipo.nombre_tipo_insumo} está inactiva. Primero reactivala.",
                "categoria_inactiva",
            )
        insumo.estado_insumo = Estado.ACTIVO
        insumo.save(update_fields=["estado_insumo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_INSUMO,
            afectados=[insumo],
            detalle={"cambios": {"estado": {"antes": Estado.INACTIVO.value, "despues": Estado.ACTIVO.value}}},
        )
    return insumo


# ---- baja ----


def _impedimentos(existencias):
    """Regla 2 de CMP-BAJ-INS: los impedimentos de cada habilitación ACTIVA, invernadero por invernadero y TODOS juntos (stock distinto de
    cero —también el negativo—, reservas, tránsito y los de los registrantes de deshabilitación)."""
    juntos = []
    for existencia in existencias:
        if not existencia.activo:
            continue
        for impedimento in extensiones.impedimentos_de_deshabilitacion(existencia):
            juntos.append(
                ImpedimentoDeBaja(existencia.invernadero, impedimento.codigo, impedimento.texto, impedimento.como_resolver)
            )
    return juntos


def _error_de_impedimentos(impedimentos):
    return ValidationError(
        {
            NON_FIELD_ERRORS: [
                ValidationError(f"{i.invernadero.nombre_invernadero}: {i.texto} {i.como_resolver}", code=i.codigo)
                for i in impedimentos
            ]
        }
    )


def impedimentos_de_baja(actor, insumo_id):
    """CMP-BAJ-INS regla 2: los impedimentos de la baja, para la ventana de confirmación: lista de ``ImpedimentoDeBaja(invernadero,
    codigo, texto, como_resolver)``. Solo lectura: no bloquea, no cambia nada y no audita; ``baja_insumo`` los vuelve a verificar con
    todo bloqueado. Mismas precondiciones a, b y c que la baja."""
    _exigir_agronomo(actor)
    insumo = get_object_or_404(Insumo.objects.select_related("tipo_insumo"), pk=insumo_id)
    _exigir_activo_y_que_no_sea_semilla(insumo)
    existencias = list(
        InsumoInvernadero.objects.filter(insumo=insumo).select_related("insumo", "invernadero", "invernadero__agronomo").order_by("id")
    )
    _exigir_que_pueda_gestionar(actor, insumo, _usan_desde(existencias))
    return _impedimentos(existencias)


def baja_insumo(actor, insumo_id):
    """CMP-BAJ-INS: da de baja lógica un insumo activo, deshabilita todas sus habilitaciones y lo devuelve.

    - Precondición a: Agrónomo activo. Precondición b: puede gestionarlo (``insumo_en_uso_por_otros``). Precondición c: está activo
      (``insumo_inactivo``) y no es una semilla (``insumo_semilla``; regla 3: se da de baja con su variedad).
    - Precondiciones d y e y regla 2: se juntan TODOS los impedimentos, invernadero por invernadero, en un solo ``ValidationError`` con un
      error por impedimento (código del impedimento, texto «<invernadero>: <qué pasa> <cómo resolverlo>»). No se cambia nada.
    - Postcondiciones a y b y regla 1: el insumo y todos sus ``InsumoInvernadero`` pasan a inactivos; conserva lotes y movimientos.
    - Postcondición c y D-36: un registro ``baja_insumo`` y uno ``baja_insumo_invernadero`` por cada habilitación que se deshabilitó; la
      alerta «bajo el mínimo» (clave ``insumo:<id>``) de cada una se resuelve y va en ``datos.alertas_resueltas``.
    Orden de bloqueos: invernaderos, insumo, existencias (``_bloquear``); las alertas, después del invernadero.
    """
    _exigir_agronomo(actor)
    with transaction.atomic():
        insumo, existencias = _bloquear(actor, insumo_id)
        _exigir_activo_y_que_no_sea_semilla(insumo)
        _exigir_que_pueda_gestionar(actor, insumo, _usan_desde(existencias))
        impedimentos = _impedimentos(existencias)
        if impedimentos:
            raise _error_de_impedimentos(impedimentos)
        insumo.estado_insumo = Estado.INACTIVO
        insumo.save(update_fields=["estado_insumo"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_INSUMO,
            afectados=[insumo],
            detalle={"cambios": {"estado": {"antes": Estado.ACTIVO.value, "despues": Estado.INACTIVO.value}}},
        )
        for existencia in existencias:
            if not existencia.activo:
                continue
            existencia.estado_insumo_invernadero = EstadoExistencia.INACTIVO
            existencia.save(update_fields=["estado_insumo_invernadero"])
            resuelta = api_alertas.resolver_alerta_de_estado(
                existencia.invernadero_id, TIPO_DE_ALERTA_BAJO_MINIMO, clave=f"insumo:{insumo.pk}"
            )
            detalle = {
                "cambios": {
                    "estado": {"antes": EstadoExistencia.ACTIVO.value, "despues": EstadoExistencia.INACTIVO.value}
                }
            }
            if resuelta is not None:
                detalle["datos"] = {"alertas_resueltas": [referencia(resuelta)]}
            RegistroAuditoria.objects.registrar(
                usuario=actor,
                accion=RegistroAuditoria.Accion.BAJA_INSUMO_INVERNADERO,
                afectados=[existencia, existencia.invernadero],
                detalle=detalle,
            )
    return insumo


# ---- consulta (CMP-CNS-INS) ----


def consultar_insumos(actor):
    """CMP-CNS-INS: todo el catálogo, activos e inactivos y con las semillas, los activos primero y por nombre sin distinguir mayúsculas
    (regla 1). Cada insumo trae su categoría y ``habilitado_en`` (los invernaderos que lo usan, por nombre; vacío = «ninguno») y
    ``es_semilla`` (regla 2). Dos consultas en total. Precondición a: Agrónomo activo; el Gerente no consulta el catálogo (regla 4):
    ``PermissionDenied``. No audita (regla 5 y SEG-14)."""
    _exigir_agronomo(actor)
    lista = list(
        Insumo.objects.select_related("tipo_insumo").order_by("estado_insumo", Lower("nombre_insumo"), "id")
    )
    usos = _usos_de([insumo.pk for insumo in lista])
    for insumo in lista:
        insumo.habilitado_en = usos[insumo.pk]
        insumo.es_semilla = es_semilla(insumo)
    return lista


def obtener_insumo(actor, insumo_id):
    """CMP-CNS-INS: el insumo con ``habilitado_en`` y ``es_semilla`` (404 si no existe). Solo el Agrónomo."""
    _exigir_agronomo(actor)
    insumo = get_object_or_404(Insumo.objects.select_related("tipo_insumo"), pk=insumo_id)
    insumo.habilitado_en = invernaderos_que_usan(insumo.pk)
    insumo.es_semilla = es_semilla(insumo)
    return insumo


def acciones_permitidas(actor, insumo):
    """D-30 y regla 3 de CMP-CNS-INS: las acciones que ``actor`` puede iniciar sobre ``insumo``, un ``frozenset`` de ``{"modificar",
    "baja", "reactivar"}`` según su estado. Una semilla no tiene estas acciones. Si ``puede_gestionar`` es falso, la pantalla las muestra
    deshabilitadas con ``quienes_lo_usan``. «Habilitar» es de INV-02. Ningún botón lleva a un 403."""
    if not _es_agronomo_activo(actor) or es_semilla(insumo):
        return frozenset()
    if insumo.estado_insumo == Estado.ACTIVO:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})
