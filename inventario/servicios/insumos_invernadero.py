# Servicios de InsumoInvernadero (INV-02, paso 3): habilitar (CMP-HAB-IIN), modificar (CMP-MOD-IIN), deshabilitar (CMP-DSH-IIN) y
# consultar existencias (CMP-CNS-IIN). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de
# D-36 (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/inventario/insumo_invernadero.md; forma: docs/patrones/abm.md.
#
# Bloqueos (siempre ``FOR NO KEY UPDATE``; orden de docs/patrones/stock.md, sección 5: invernadero → Insumo → InsumoInvernadero):
# - El invernadero se bloquea con ``bloquear_invernadero_activo`` ANTES de tocar nada (contrato de D-40: habilitar y deshabilitar
#   cambian lo que impide la baja del invernadero) y se verifica que esté a cargo del actor DESPUÉS de bloquear y releer.
# - Habilitar bloquea además el ``Insumo``: así ``baja_insumo`` (que toma insumo → existencias) no lo desactiva en paralelo y deja una
#   existencia activa de un insumo inactivo.
# - Dos habilitaciones del mismo par: el bloqueo del invernadero las serializa; la restricción única de la base es el respaldo.
# - Las alertas las crea o resuelve ``reevaluar_alertas_del_insumo`` (un solo punto); el invernadero ya está bloqueado.
# Los ``Decimal`` van como texto en la auditoría (``texto_cantidad`` y ``texto_precio``).

from collections import namedtuple
from decimal import Decimal, InvalidOperation

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404

from core.models import RegistroAuditoria, referencia
from inventario import extensiones
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, stock
from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.servicios.tipos_de_insumo import _exigir_agronomo
from inventario.unidades import validar_cantidad
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, bloquear_invernadero_activo

Estado = InsumoInvernadero.Estado

ACCION_MODIFICAR = "modificar"
ACCION_DESHABILITAR = "deshabilitar"
ACCION_AJUSTAR = "ajustar"

MENSAJE_AJENO = "Ese invernadero no está a tu cargo."
DECIMAL_PRECIO = Decimal("0.01")
LIMITE_DE_PRECIO = Decimal(10) ** 12  # DecimalField(14, 2)
LIMITE_DE_CANTIDAD = Decimal(10) ** 11  # DecimalField(14, 3)

# Una fila de «Existencias de insumos» (regla 3 de CMP-CNS-IIN): el registro, sus cantidades (``stock.Existencia``), sus lotes con
# su estado, lo vencido y lo por vencer (cantidades) y la marca «stock_negativo» o «no_cubre_reservas» (o ``None``).
FilaDeExistencia = namedtuple("FilaDeExistencia", "iin stock lotes vencido por_vencer marca")
LoteConEstado = namedtuple("LoteConEstado", "lote estado")


# ---- validación de los datos (sin tocar la base) ----


def _error_de_campo(errores, campo, mensaje, codigo):
    errores.setdefault(campo, [ValidationError(mensaje, code=codigo)])


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _validar_minimo(valor, unidad, errores):
    """Regla 3 de CMP-HAB-IIN: obligatorio, cero o más, con los decimales de la unidad. Devuelve el ``Decimal`` o ``None``."""
    if _vacio(valor):
        _error_de_campo(errores, "cant_min", "Ingresá el stock mínimo.", "obligatorio")
        return None
    if isinstance(valor, float):
        _error_de_campo(errores, "cant_min", "Ingresá una cantidad válida.", "cantidad_invalida")
        return None
    try:
        numero = validar_cantidad(valor, unidad)
    except ValidationError as error:
        _error_de_campo(errores, "cant_min", error.messages[0], error.code)
        return None
    if numero < 0:
        _error_de_campo(errores, "cant_min", "El stock mínimo no puede ser negativo.", "minimo_negativo")
        return None
    if numero >= LIMITE_DE_CANTIDAD:
        _error_de_campo(errores, "cant_min", "Ingresá una cantidad válida.", "cantidad_invalida")
        return None
    return numero


def _validar_precio(valor, errores):
    """Regla 4 de CMP-HAB-IIN: obligatorio, mayor que cero, con 2 decimales. Devuelve el ``Decimal`` o ``None``."""
    if _vacio(valor):
        _error_de_campo(errores, "referencia_precio", "Ingresá el precio de referencia.", "obligatorio")
        return None
    mensaje = "Ingresá un precio mayor que 0, con hasta 2 decimales."
    if isinstance(valor, float):
        _error_de_campo(errores, "referencia_precio", mensaje, "precio_invalido")
        return None
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        _error_de_campo(errores, "referencia_precio", mensaje, "precio_invalido")
        return None
    if not numero.is_finite() or numero <= 0 or numero != numero.quantize(DECIMAL_PRECIO) or numero >= LIMITE_DE_PRECIO:
        _error_de_campo(errores, "referencia_precio", mensaje, "precio_invalido")
        return None
    return numero.quantize(DECIMAL_PRECIO)


def _validar_datos(unidad, cant_min, referencia_precio):
    """Reglas 3 y 4 de CMP-HAB-IIN (y regla 1 de CMP-MOD-IIN): los dos campos, con TODOS los errores juntos en un solo
    ``ValidationError`` (uno por campo). Devuelve ``(minimo, precio)``."""
    errores = {}
    minimo = _validar_minimo(cant_min, unidad, errores)
    precio = _validar_precio(referencia_precio, errores)
    if errores:
        raise ValidationError(errores)
    return minimo, precio


# ---- bloqueos y permisos ----


def _bloquear_para(actor, invernadero_id):
    """Bloquea el invernadero (rechaza uno inactivo: ``invernadero_inactivo``), verifica que quien actúa siga activo y que el
    invernadero esté a cargo de ``actor`` (precondición b; ``PermissionDenied`` si es ajeno) y lo devuelve ya releído."""
    invernadero = bloquear_invernadero_activo(invernadero_id)
    _actor_sigue_activo(actor)
    if invernadero.agronomo_id != actor.pk:
        raise PermissionDenied(MENSAJE_AJENO)
    return invernadero


def _existencia_para_actuar(actor, iin_id):
    """Lectura sin bloquear de una existencia (404 si no existe) para saber qué invernadero bloquear; verifica ya el alcance."""
    leida = get_object_or_404(InsumoInvernadero.objects.select_related("invernadero"), pk=iin_id)
    if leida.invernadero.agronomo_id != actor.pk:
        raise PermissionDenied(MENSAJE_AJENO)
    return leida


def _bloquear_existencia(iin_id):
    """La existencia bloqueada y releída, con su insumo (después del invernadero)."""
    return (
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",))
        .select_related("insumo", "invernadero")
        .get(pk=iin_id)
    )


def _datos_de_alertas(datos, reevaluacion):
    """Suma a ``datos`` las alertas creadas y resueltas (solo las no vacías; docs/api/alertas.md, «Auditoría»)."""
    if reevaluacion.creadas:
        datos["alertas_creadas"] = [referencia(a) for a in reevaluacion.creadas]
    if reevaluacion.resueltas:
        datos["alertas_resueltas"] = [referencia(a) for a in reevaluacion.resueltas]
    return datos


# ---- habilitar (CMP-HAB-IIN) ----


def habilitar_insumo(actor, insumo_id, invernadero_id, cant_min, referencia_precio):
    """CMP-HAB-IIN: habilita ``insumo_id`` en ``invernadero_id`` con su mínimo y su precio de referencia y devuelve el
    ``InsumoInvernadero``. La llaman la pantalla de INV-02 y PRD-01 (extensión del caso de uso).

    - Precondición a: Agrónomo activo (``PermissionDenied``). Precondición b: invernadero activo (``invernadero_inactivo``) y a cargo
      del actor (``PermissionDenied``). Precondición c: insumo activo del catálogo (``insumo_inactivo``). Precondición d: no está ya
      habilitado (``ya_habilitado``). Un id inexistente da ``Http404``.
    - Reglas 3 y 4: ``cant_min`` y ``referencia_precio`` con todos los errores juntos, uno por campo.
    - Regla 5 y postcondiciones a y b: un registro por par; el par deshabilitado se REACTIVA (mismo registro y su historial).
    - Postcondición c y regla 8: reevalúa «bajo el mínimo» (y el resto de las alertas del insumo).
    - Postcondición d y D-36: ``habilitacion_insumo_invernadero`` con el mínimo y el precio como texto.
    Orden de bloqueos: invernadero → insumo → existencia.
    """
    _exigir_agronomo(actor)
    get_object_or_404(Insumo, pk=insumo_id)
    get_object_or_404(Invernadero, pk=invernadero_id)
    with transaction.atomic():
        invernadero = _bloquear_para(actor, invernadero_id)
        insumo = Insumo.objects.select_for_update(no_key=True).get(pk=insumo_id)  # frena una baja del insumo en paralelo
        if not insumo.activo:
            raise _error_general("El insumo está inactivo en el catálogo: reactivalo antes de habilitarlo.", "insumo_inactivo")
        minimo, precio = _validar_datos(insumo.unidad_medida_insumo, cant_min, referencia_precio)
        unidad = insumo.unidad_medida_insumo
        previo = (
            InsumoInvernadero.objects.select_for_update(no_key=True)
            .filter(insumo=insumo, invernadero=invernadero)
            .first()
        )
        if previo is not None and previo.activo:
            raise _error_general("Ese insumo ya está habilitado en el invernadero.", "ya_habilitado")
        if previo is None:
            try:
                with transaction.atomic():  # respaldo: la restricción única del par
                    iin = InsumoInvernadero.objects.create(
                        insumo=insumo, invernadero=invernadero, cant_min_insumo=minimo, referencia_precio=precio
                    )
            except IntegrityError as error:
                raise _error_general("Ese insumo ya está habilitado en el invernadero.", "ya_habilitado") from error
            cambios = {
                "cant_min_insumo": {"antes": None, "despues": texto_cantidad(minimo, unidad)},
                "referencia_precio": {"antes": None, "despues": texto_precio(precio)},
            }
        else:  # postcondición b: se reactiva el mismo registro
            iin = previo
            cambios = {"estado": {"antes": Estado.INACTIVO.value, "despues": Estado.ACTIVO.value}}
            if iin.cant_min_insumo != minimo:
                cambios["cant_min_insumo"] = {
                    "antes": texto_cantidad(iin.cant_min_insumo, unidad),
                    "despues": texto_cantidad(minimo, unidad),
                }
            if iin.referencia_precio != precio:
                cambios["referencia_precio"] = {
                    "antes": texto_precio(iin.referencia_precio),
                    "despues": texto_precio(precio),
                }
            iin.estado_insumo_invernadero = Estado.ACTIVO
            iin.cant_min_insumo = minimo
            iin.referencia_precio = precio
            iin.save(update_fields=["estado_insumo_invernadero", "cant_min_insumo", "referencia_precio"])
        reevaluacion = alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.HABILITACION_INSUMO_INVERNADERO,
            afectados=[iin, invernadero],
            detalle={"cambios": cambios, "datos": _datos_de_alertas({"insumo": referencia(insumo)}, reevaluacion)},
        )
    return iin


# ---- modificar (CMP-MOD-IIN) ----


def modificar_insumo_invernadero(actor, iin_id, *, cant_min, referencia_precio):
    """CMP-MOD-IIN: actualiza el stock mínimo y el precio de referencia de un insumo habilitado y lo devuelve.

    - Precondiciones a, b y c: Agrónomo activo; invernadero activo y a cargo; el insumo está habilitado (``insumo_deshabilitado``,
      regla 4: uno deshabilitado se vuelve a habilitar con CMP-HAB-IIN).
    - Regla 1: se validan como en CMP-HAB-IIN. Regla 2: el precio nuevo no toca lo ya registrado (lotes y movimientos).
    - D-28: sin cambios no se escribe ni se audita. Postcondición b: si cambió el MÍNIMO se reevalúan las alertas del insumo.
    - Postcondición c y D-36: ``modificacion_insumo_invernadero`` con antes y después (como texto).
    Dos modificaciones a la vez: gana la última (la segunda calcula sus cambios contra lo que dejó la primera).
    """
    _exigir_agronomo(actor)
    leida = _existencia_para_actuar(actor, iin_id)
    with transaction.atomic():
        invernadero = _bloquear_para(actor, leida.invernadero_id)
        iin = _bloquear_existencia(iin_id)
        if not iin.activo:
            raise _error_general("El insumo está deshabilitado en el invernadero: habilitalo de nuevo.", "insumo_deshabilitado")
        unidad = iin.insumo.unidad_medida_insumo
        minimo, precio = _validar_datos(unidad, cant_min, referencia_precio)
        cambios = {}
        if minimo != iin.cant_min_insumo:
            cambios["cant_min_insumo"] = {"antes": texto_cantidad(iin.cant_min_insumo, unidad), "despues": texto_cantidad(minimo, unidad)}
        if precio != iin.referencia_precio:
            cambios["referencia_precio"] = {"antes": texto_precio(iin.referencia_precio), "despues": texto_precio(precio)}
        if not cambios:
            return iin
        iin.cant_min_insumo = minimo
        iin.referencia_precio = precio
        iin.save(update_fields=["cant_min_insumo", "referencia_precio"])
        detalle = {"cambios": cambios}
        if "cant_min_insumo" in cambios:
            datos = _datos_de_alertas({}, alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk))
            if datos:
                detalle["datos"] = datos
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO,
            afectados=[iin, invernadero],
            detalle=detalle,
        )
    return iin


# ---- deshabilitar (CMP-DSH-IIN) ----


def _error_de_impedimentos(impedimentos):
    """Un solo ``ValidationError`` general con un error por impedimento: código, y mensaje «qué pasa + cómo resolverlo»."""
    return ValidationError(
        {NON_FIELD_ERRORS: [ValidationError(f"{i.texto} {i.como_resolver}", code=i.codigo) for i in impedimentos]}
    )


def impedimentos_para_deshabilitar(actor, iin_id):
    """CMP-DSH-IIN regla 2, para la ventana: los impedimentos de deshabilitar (lista de ``Impedimento(codigo, texto,
    como_resolver)``). Solo lectura: no bloquea, no cambia nada y no audita; ``deshabilitar_insumo`` los vuelve a verificar con todo
    bloqueado. Mismas precondiciones a, b y c que la baja."""
    _exigir_agronomo(actor)
    iin = _existencia_para_actuar(actor, iin_id)
    if not iin.invernadero.activo:
        raise _error_general("El invernadero está inactivo.", "invernadero_inactivo")
    if not iin.activo:
        raise _error_general("El insumo ya está deshabilitado en el invernadero.", "insumo_deshabilitado")
    iin = InsumoInvernadero.objects.select_related("insumo", "invernadero").get(pk=iin.pk)
    return extensiones.impedimentos_de_deshabilitacion(iin)


def deshabilitar_insumo(actor, iin_id):
    """CMP-DSH-IIN: deja inactivo el insumo en el invernadero y lo devuelve.

    - Precondiciones a, b y c: Agrónomo activo; invernadero activo y a cargo; el insumo está habilitado (``insumo_deshabilitado``).
    - Precondiciones d y e y regla 2: se juntan TODOS los impedimentos (stock distinto de cero, reservas, tránsito y los de
      ``compras``) en un solo ``ValidationError`` con un error por impedimento. No se cambia nada.
    - Postcondición a y regla 1: queda «inactivo» y conserva lotes, movimientos e historial. Postcondición b: la alerta «bajo el
      mínimo» activa se resuelve y va en ``datos.alertas_resueltas``. Postcondición c y D-36: ``baja_insumo_invernadero``.
    Orden de bloqueos: invernadero → existencia.
    """
    _exigir_agronomo(actor)
    leida = _existencia_para_actuar(actor, iin_id)
    with transaction.atomic():
        invernadero = _bloquear_para(actor, leida.invernadero_id)
        iin = _bloquear_existencia(iin_id)
        if not iin.activo:
            raise _error_general("El insumo ya está deshabilitado en el invernadero.", "insumo_deshabilitado")
        impedimentos = extensiones.impedimentos_de_deshabilitacion(iin)
        if impedimentos:
            raise _error_de_impedimentos(impedimentos)
        iin.estado_insumo_invernadero = Estado.INACTIVO
        iin.save(update_fields=["estado_insumo_invernadero"])
        detalle = {"cambios": {"estado": {"antes": Estado.ACTIVO.value, "despues": Estado.INACTIVO.value}}}
        datos = _datos_de_alertas({}, alertas_de_stock.reevaluar_alertas_del_insumo(iin.pk))
        if datos:
            detalle["datos"] = datos
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_INSUMO_INVERNADERO,
            afectados=[iin, invernadero],
            detalle=detalle,
        )
    return iin


# ---- conexión con la baja del invernadero (PROD-BAJ-INV; disparador «Cuando exista InsumoInvernadero») ----
# Se registran en ``maestros.extensiones`` desde ``InventarioConfig.ready()`` (regla A4 de D-37) y corren dentro de la transacción de
# la baja, con el invernadero ya bloqueado: bloquean sus filas después de él y en orden de id (docs/api/extensiones_de_inventario.md).


def impedimentos_de_baja_de_invernadero(invernadero):
    """Precondición f de PROD-BAJ-INV: lo que impide dar de baja ``invernadero`` por sus insumos. Por cada ``InsumoInvernadero`` ACTIVO,
    en orden de id: stock distinto de cero (también el negativo), cantidad en tránsito y los impedimentos de los registrantes de
    ``registrar_impedimento_de_deshabilitacion`` (``compras``). Las reservas NO se incluyen: las órdenes que reservan son impedimento
    de baja de `produccion` y no se informan dos veces. Solo lectura."""
    existencias = (
        InsumoInvernadero.objects.filter(invernadero=invernadero, estado_insumo_invernadero=Estado.ACTIVO)
        .select_related("insumo", "invernadero")
        .order_by("id")
    )
    impedimentos = []
    for existencia in existencias:
        impedimentos.extend(
            i for i in extensiones.impedimentos_de_deshabilitacion(existencia) if i.codigo != extensiones.RESERVAS_ACTIVAS
        )
    return impedimentos


def efecto_de_baja_de_invernadero(actor, invernadero):
    """Postcondición c de PROD-BAJ-INV: al dar de baja el invernadero, sus ``InsumoInvernadero`` activos pasan a inactivos, con un
    registro ``baja_insumo_invernadero`` por cada uno y las alertas activas de ese insumo resueltas (van en ``datos.alertas_resueltas``).
    Los bloquea en orden de id (después del invernadero, que ya está bloqueado) y conserva lotes y movimientos. Un insumo ya
    deshabilitado no cambia ni se audita. Reactivar el invernadero no los reactiva (regla 6): los habilita el Agrónomo."""
    a_dar_de_baja = (
        InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",))
        .filter(invernadero=invernadero, estado_insumo_invernadero=Estado.ACTIVO)
        .select_related("insumo")
        .order_by("id")
    )
    for existencia in list(a_dar_de_baja):
        existencia.estado_insumo_invernadero = Estado.INACTIVO
        existencia.save(update_fields=["estado_insumo_invernadero"])
        detalle = {"cambios": {"estado": {"antes": Estado.ACTIVO.value, "despues": Estado.INACTIVO.value}}}
        datos = _datos_de_alertas({}, alertas_de_stock.reevaluar_alertas_del_insumo(existencia.pk))
        if datos:
            detalle["datos"] = datos
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_INSUMO_INVERNADERO,
            afectados=[existencia, invernadero],
            detalle=detalle,
        )


# ---- consulta (CMP-CNS-IIN) ----


def _estado_del_lote(lote, hoy, dias_de_aviso):
    """El estado de un lote para la pantalla (regla 4 de CMP-CNS-IIN): faltante, agotado, sin vencimiento, vencido (desde el día
    siguiente a su fecha), por vencer (entre 0 y ``dias_de_aviso`` días) o al día."""
    if lote.es_faltante_sin_lote:
        return "faltante"
    if lote.cantidad_disponible == 0:
        return "agotado"
    if lote.fecha_vencimiento is None:
        return "sin_vencimiento"
    if stock.esta_vencido(lote, hoy):
        return "vencido"
    if (lote.fecha_vencimiento - hoy).days <= dias_de_aviso:
        return "por_vencer"
    return "al_dia"


def consultar_existencias(
    actor, invernadero_id=None, categoria_id=None, con_vencimientos=False, bajo_minimo=False, hoy=None
):
    """CMP-CNS-IIN: los insumos habilitados de los invernaderos ACTIVOS a cargo de ``actor``, por invernadero y por nombre, como
    ``FilaDeExistencia``. No audita (regla 6 y SEG-14).

    - Precondición a y regla 1: Agrónomo activo; el Gerente no consulta existencias (``PermissionDenied``).
    - Regla 2: filtros por invernadero (uno ajeno da ``PermissionDenied``, D-28), categoría, «con vencimientos» (algún lote vencido o por
      vencer) y «bajo el mínimo».
    - Reglas 3 y 4: cantidades de ``stock.existencias`` y los lotes con su estado. Una consulta por tabla, no por fila.
    ``hoy`` (por omisión, la de hoy) permite probar cualquier fecha.
    """
    _exigir_agronomo(actor)
    if invernadero_id is not None:
        propio = get_object_or_404(Invernadero, pk=invernadero_id)
        if propio.agronomo_id != actor.pk:
            raise PermissionDenied(MENSAJE_AJENO)
    if hoy is None:
        hoy = stock.hoy()
    consulta = InsumoInvernadero.objects.filter(
        estado_insumo_invernadero=Estado.ACTIVO,
        invernadero__estado_invernadero=Invernadero.Estado.ACTIVO,
        invernadero__agronomo_id=actor.pk,
    ).select_related("insumo", "insumo__tipo_insumo", "invernadero")
    if invernadero_id is not None:
        consulta = consulta.filter(invernadero_id=invernadero_id)
    if categoria_id is not None:
        consulta = consulta.filter(insumo__tipo_insumo_id=categoria_id)
    existencias = list(consulta.order_by(Lower("invernadero__nombre_invernadero"), Lower("insumo__nombre_insumo"), "id"))
    if not existencias:
        return []
    ids = [e.pk for e in existencias]
    cantidades = stock.existencias(ids, hoy)
    lotes_de = {i: [] for i in ids}
    for lote in LoteInsumo.objects.filter(insumo_invernadero_id__in=ids).order_by("insumo_invernadero_id", "id"):
        lotes_de[lote.insumo_invernadero_id].append(lote)
    dias_de_aviso = configuracion.obtener().dias_aviso_vencimiento  # una vez por consulta (regla 10 de CMP-REV-VNC)
    filas = []
    for existencia in existencias:
        cantidad = cantidades[existencia.pk]
        lotes = [LoteConEstado(l, _estado_del_lote(l, hoy, dias_de_aviso)) for l in lotes_de[existencia.pk]]
        vencido = sum((l.lote.cantidad_disponible for l in lotes if l.estado == "vencido"), Decimal("0"))
        por_vencer = sum((l.lote.cantidad_disponible for l in lotes if l.estado == "por_vencer"), Decimal("0"))
        if con_vencimientos and not (vencido or por_vencer):
            continue
        if bajo_minimo and not cantidad.bajo_minimo:
            continue
        marca = "stock_negativo" if cantidad.vigente < 0 else ("no_cubre_reservas" if cantidad.inconsistente else None)
        filas.append(FilaDeExistencia(existencia, cantidad, lotes, vencido, por_vencer, marca))
    return filas


def habilitados(invernadero_id):
    """Los ``InsumoInvernadero`` activos de un invernadero activo, con su insumo y categoría, por nombre (para las listas de elección:
    ajuste, aplicación de insumos, pedidos). Sin permisos: quien llama ya los verificó. Un invernadero inactivo no ofrece insumos."""
    return list(
        InsumoInvernadero.objects.filter(
            invernadero_id=invernadero_id,
            estado_insumo_invernadero=Estado.ACTIVO,
            invernadero__estado_invernadero=Invernadero.Estado.ACTIVO,
        )
        .select_related("insumo", "insumo__tipo_insumo", "invernadero")
        .order_by(Lower("insumo__nombre_insumo"), "id")
    )


def acciones_permitidas(actor, iin):
    """D-30 y regla 5 de CMP-CNS-IIN: las acciones que ``actor`` puede iniciar sobre ``iin`` (``InsumoInvernadero``): un
    ``frozenset`` de ``{"modificar", "deshabilitar", "ajustar"}``. Solo el Agrónomo a cargo de un invernadero activo, sobre un insumo
    habilitado. Ningún botón lleva a un 403."""
    from core.models import Usuario, rol_de

    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.AGRONOMO:
        return frozenset()
    if not iin.activo or not iin.invernadero.activo or iin.invernadero.agronomo_id != actor.pk:
        return frozenset()
    return frozenset({ACCION_MODIFICAR, ACCION_DESHABILITAR, ACCION_AJUSTAR})
