# Servicios de Proveedor (CMP-01): alta con su reactivación (CMP-ALT-PRV), modificación (CMP-MOD-PRV), baja (CMP-BAJ-PRV) y consulta
# (CMP-CNS-PRV). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36
# (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/compras/proveedores.md; patrón: docs/patrones/abm.md.
#
# Bloqueos (docs/patrones/bloqueos.md, «compras»; siempre ``FOR NO KEY UPDATE``): modificar, reactivar y dar de baja bloquean la fila del
# proveedor y la vuelven a leer. La unicidad del CUIT la asegura la restricción ``UNIQUE`` de la base (no un bloqueo): el alta o la
# modificación concurrente que pierde recibe el ``IntegrityError``, traducido al mismo error de campo ``cuit_repetido``.
# ``compras`` no importa de ``comercial`` ni de ``produccion`` (A1 de D-37).

from collections import namedtuple
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Case, F, Prefetch, Q, Sum, Value, When
from django.db.models.functions import Concat, Lower
from django.shortcuts import get_object_or_404
from django.http import Http404

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, DetalleOrdenCompra, OrdenCompra, Pedido, Proveedor
from compras.servicios import enlaces
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from core.validadores import validar_telefono
from inventario.models import TipoInsumo
from maestros.extensiones import Impedimento  # noqa: F401  (los impedimentos de la baja son de este tipo)
from maestros.servicios.invernaderos import _actor_sigue_activo, _tiene_contenido
from maestros.validadores import validar_cuit

Estado = Proveedor.Estado
Tipo = Proveedor.Tipo

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

_LARGOS = {
    "razon_social": Proveedor._meta.get_field("razon_social_proveedor").max_length,
    "nombre": Proveedor._meta.get_field("nombre_proveedor").max_length,
    "apellido": Proveedor._meta.get_field("apellido_proveedor").max_length,
    "email": Proveedor._meta.get_field("email_proveedor").max_length,
}
_ROTULOS = {"razon_social": "la razón social", "nombre": "el nombre", "apellido": "el apellido"}


# ---- comunes ----


def _exigir_gerente(actor):
    """Precondición a de ALT, MOD y BAJ: ``actor`` es un Gerente con la cuenta activa (SEG-13). El Agrónomo solo consulta."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede gestionar proveedores.")


def _exigir_lectura(actor):
    """Precondición a de CNS: ``actor`` es un Agrónomo o un Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
        raise PermissionDenied("Solo un Gerente o un Agrónomo activos pueden consultar proveedores.")


def tiene_pedidos_u_ordenes(proveedor):
    """Regla 2 de CMP-MOD-PRV: True si el proveedor tiene pedidos (invitaciones) o cotizaciones, y entonces su CUIT no se modifica. CMP-02a la completó
    (docs/casos_de_uso/compras/proveedores.md, «Cómo se aplica»); las órdenes de compra cuelgan de sus cotizaciones (CMP-03)."""
    return proveedor.invitaciones.exists() or proveedor.cotizaciones.exists()


# Un pedido en la ficha del proveedor (regla 4 de CMP-CNS-PRV): el pedido y si este proveedor cotizó.
PedidoDelProveedor = namedtuple("PedidoDelProveedor", "pedido cotizo")


def pedidos_del_proveedor(actor, proveedor):
    """Regla 4 de CMP-CNS-PRV: los pedidos a los que se invitó al proveedor (o donde cotizó), del más reciente al más viejo, **según el alcance de quien mira**
    (el Agrónomo, los suyos; el Gerente, todos), y si cotizó. Una consulta por tabla; no audita."""
    _exigir_lectura(actor)
    pedidos = list(
        Pedido.objects.en_alcance_de(actor)
        .filter(Q(invitaciones__proveedor=proveedor) | Q(cotizaciones__proveedor=proveedor))
        .distinct()
        .order_by("-fecha_pedido", "-id")
    )
    cotizaron = set(Cotizacion.objects.filter(proveedor=proveedor, pedido__in=pedidos).values_list("pedido_id", flat=True))
    return [PedidoDelProveedor(p, p.pk in cotizaron) for p in pedidos]


# Una orden en la ficha del proveedor (regla 4 de CMP-CNS-PRV): la orden y el monto de las líneas de este proveedor.
OrdenDelProveedor = namedtuple("OrdenDelProveedor", "orden monto")


def ordenes_del_proveedor(actor, proveedor):
    """Regla 4 de CMP-CNS-PRV (CMP-03): las órdenes de compra con líneas de ``proveedor``, de la más reciente a la más vieja, **según el alcance de quien mira** (el Agrónomo,
    las que tienen algún destino a su cargo; el Gerente, todas), con el monto de las líneas de este proveedor. Dos consultas; no audita."""
    _exigir_lectura(actor)
    ordenes = list(
        OrdenCompra.objects.en_alcance_de(actor)
        .filter(detalles__detalle_cotizacion__cotizacion__proveedor=proveedor)
        .distinct()
        .order_by("-fecha_emision", "-id")
    )
    montos = {
        fila["orden_id"]: fila["monto"]
        for fila in DetalleOrdenCompra.objects.filter(orden__in=ordenes, detalle_cotizacion__cotizacion__proveedor=proveedor)
        .values("orden_id")
        .annotate(monto=Sum("total_linea"))
    }
    return [OrdenDelProveedor(o, montos.get(o.pk, Decimal("0.00"))) for o in ordenes]


def impedimentos_de_baja(proveedor):
    """Precondiciones c y d de CMP-BAJ-PRV: la lista de ``Impedimento(codigo, texto, como_resolver)`` que impiden la baja. Hoy: ``orden_no_terminada`` (CMP-03, H22), una
    por cada orden pendiente de aprobación, aprobada o parcialmente recibida con una línea de una cotización de este proveedor; CMP-05 suma ``pago_pendiente``. Un
    pedido «en cotización» donde está invitado no es un impedimento (regla 5). Una sola consulta; no confundir con el ``orden_de_compra_aprobada`` del insumo."""
    sin_terminar = (
        OrdenCompra.objects.filter(estado_orden_compra__in=OrdenCompra.NO_TERMINADAS, detalles__detalle_cotizacion__cotizacion__proveedor=proveedor)
        .distinct()
        .order_by("id")
    )
    return [
        Impedimento(
            "orden_no_terminada",
            f"Tiene la orden de compra {orden} sin terminar ({orden.get_estado_orden_compra_display().lower()}).",
            "Esperá a que se rechace o a recibir o cerrar con faltante la mercadería.",
        )
        for orden in sin_terminar
    ]


def _error(mensaje, codigo):
    """Un error de campo."""
    return ValidationError(mensaje, code=codigo)


def _texto(valor):
    """``valor`` como texto recortado (``None`` es vacío)."""
    return "" if valor is None else str(valor).strip()


def _especialidades_pedidas(valores):
    """Los ids de las categorías que se pidieron (ids, textos de ids o ``TipoInsumo``); ``None`` si alguno no es un id."""
    ids = []
    for valor in valores or []:
        try:
            ids.append(valor.pk if hasattr(valor, "pk") else int(valor))
        except (TypeError, ValueError):
            return None
    return ids


def _normalizar(datos, tipo, cuit_fijo=None, vinculadas=()):
    """``(limpios, errores)``: los datos de un proveedor normalizados y los errores de campo, todos juntos (docs/patrones/abm.md, sección 2).
    Sin tocar las filas de los proveedores. ``tipo`` es el del proveedor (en el alta lo elige el actor y se valida acá). ``cuit_fijo``:
    en la reactivación el CUIT no se toca y no se valida. ``vinculadas``: ids de categorías que el proveedor ya tiene; las dadas de baja
    que ya tiene no se rechazan (se conservan, regla 4 de CMP-MOD-PRV)."""
    errores = {}

    def error(campo, mensaje, codigo):
        errores.setdefault(campo, []).append(_error(mensaje, codigo))

    limpios = {}
    # Tipo (solo en el alta).
    if tipo is None:
        tipo = _texto(datos.get("tipo"))
        if not tipo:
            error("tipo", "Elegí si es una persona jurídica o una persona física.", "obligatorio")
        elif tipo not in Tipo.values:
            error("tipo", "Elegí si es una persona jurídica o una persona física.", "invalido")
    limpios["tipo"] = tipo

    # CUIT (regla 2 de ALT; D-58).
    if cuit_fijo is not None:
        limpios["cuit"] = cuit_fijo
    else:
        cuit = _texto(datos.get("cuit"))
        if not cuit:
            error("cuit", "Ingresá el CUIT.", "obligatorio")
        else:
            try:
                limpios["cuit"] = validar_cuit(cuit)
            except ValidationError as e:
                error("cuit", e.message, e.code)

    # Razón social o nombre y apellido (regla 1 de ALT); los datos del otro tipo se ignoran.
    limpios.update({"razon_social": "", "nombre": "", "apellido": ""})
    campos = ("razon_social",) if tipo == Tipo.JURIDICA else ("nombre", "apellido") if tipo == Tipo.FISICA else ()
    for campo in campos:
        valor = _texto(datos.get(campo))
        if not valor:
            error(campo, f"Ingresá {_ROTULOS[campo]}.", "obligatorio")
        elif not _tiene_contenido(valor):
            error(campo, "Ingresá un texto con al menos una letra o un número.", "sin_contenido")
        elif len(valor) > _LARGOS[campo]:
            error(campo, f"Usá como máximo {_LARGOS[campo]} caracteres.", "demasiado_largo")
        else:
            limpios[campo] = valor

    # Correo obligatorio (regla 1 de ALT: el proveedor solo recibe pedidos y órdenes por correo).
    email = _texto(datos.get("email"))
    if not email:
        error("email", "Ingresá el correo: es donde recibe los pedidos.", "obligatorio")
    elif len(email) > _LARGOS["email"]:
        error("email", f"Usá como máximo {_LARGOS['email']} caracteres.", "demasiado_largo")
    else:
        try:
            validate_email(email)
        except ValidationError:
            error("email", "Ingresá un correo válido. Ej. ventas@empresa.com.ar", "email_invalido")
    limpios["email"] = email

    # Teléfono opcional con el formato de D-21.
    telefono = _texto(datos.get("telefono"))
    try:
        validar_telefono(telefono)
    except ValidationError as e:
        error("telefono", e.message, e.code)
    limpios["telefono"] = telefono

    # Especialidades (regla 3 de ALT): cero o más categorías activas.
    ids = _especialidades_pedidas(datos.get("especialidades"))
    limpios["especialidades"] = []
    if ids is None:
        error("especialidades", "Elegí categorías de la lista.", "categoria_inexistente")
    else:
        categorias = {c.pk: c for c in TipoInsumo.objects.filter(pk__in=ids)}
        if any(i not in categorias for i in ids):
            error("especialidades", "Hay una categoría que no existe: elegí de la lista.", "categoria_inexistente")
        else:
            inactivas = [c for i, c in categorias.items() if c.estado_tipo_insumo != TipoInsumo.Estado.ACTIVO and i not in vinculadas]
            if inactivas:
                nombres = ", ".join(c.nombre_tipo_insumo for c in inactivas)
                error("especialidades", f"La categoría {nombres} está dada de baja: no se puede elegir.", "categoria_inactiva")
            limpios["especialidades"] = sorted(set(ids))
    return limpios, errores


def _lanzar_si_hay(errores):
    if errores:
        raise ValidationError(errores)


def _bloquear_proveedor(actor, proveedor_id):
    """El proveedor bloqueado (``FOR NO KEY UPDATE``) y leído de nuevo, con su estado real; 404 si no existe. Verifica, ya bloqueado, que
    quien actúa siga activo. Hay que llamarla dentro de ``transaction.atomic()``."""
    proveedor = Proveedor.objects.select_for_update(no_key=True).filter(pk=proveedor_id).first()
    if proveedor is None:
        raise Http404("No existe ese proveedor.")
    _actor_sigue_activo(actor)
    return proveedor


def _error_cuit_repetido(otro=None):
    """El error de campo de un CUIT que ya tiene otro proveedor (regla 2 de ALT, H14)."""
    if otro is None:
        mensaje = "Ya hay un proveedor con ese CUIT."
    elif otro.activo:
        mensaje = f"Ya está registrado como {otro}."
    else:
        mensaje = f"Ya existe {otro}, dado de baja."
    return ValidationError({"cuit": [_error(mensaje, "cuit_repetido")]})


def _guardar(proveedor, campos=None):
    """Guarda el proveedor. Si dos pedidos eligieron el mismo CUIT a la vez, el segundo recibe el ``IntegrityError`` de la restricción única
    y se traduce al mismo error de campo (nunca un 500). Punto de guardado: un ``IntegrityError`` no rompe la transacción de afuera."""
    try:
        with transaction.atomic():
            proveedor.save(update_fields=campos)
    except IntegrityError as error:
        if "proveedor_cuit_unico" in str(error):
            raise _error_cuit_repetido() from error
        raise


def _categorias(ids):
    """Las categorías ``ids`` por nombre (el orden del modelo)."""
    return list(TipoInsumo.objects.filter(pk__in=ids))


def _referencias(categorias):
    return [referencia(c) for c in categorias]


def _aplicar(proveedor, limpios, cuit_nuevo=None):
    """Aplica ``limpios`` al ``proveedor`` (ya bloqueado y releído) y devuelve ``cambios`` de la auditoría (D-36), con el CUIT en 11 dígitos
    como ``cuit_organizacion`` (los guiones se agregan al mostrar, D-58). Las categorías dadas de baja que ya tenía se conservan (regla 4
    de CMP-MOD-PRV). No escribe nada si no hay cambios."""
    cambios = {}
    campos = []
    pares = [
        ("cuit", "cuit_proveedor", cuit_nuevo),
        ("razon_social", "razon_social_proveedor", limpios["razon_social"]),
        ("nombre", "nombre_proveedor", limpios["nombre"]),
        ("apellido", "apellido_proveedor", limpios["apellido"]),
        ("email", "email_proveedor", limpios["email"]),
        ("telefono", "telefono_proveedor", limpios["telefono"]),
    ]
    for clave, atributo, nuevo in pares:
        if nuevo is None:
            continue
        anterior = getattr(proveedor, atributo)
        if nuevo != anterior:
            cambios[clave] = {"antes": anterior, "despues": nuevo}
            setattr(proveedor, atributo, nuevo)
            campos.append(atributo)
    actuales = list(proveedor.especialidades.all())
    conservadas = [c for c in actuales if c.estado_tipo_insumo != TipoInsumo.Estado.ACTIVO]
    finales = _categorias({c.pk for c in conservadas} | set(limpios["especialidades"]))
    if {c.pk for c in actuales} != {c.pk for c in finales}:
        cambios["especialidades"] = {"antes": _referencias(actuales), "despues": _referencias(finales)}
    return cambios, campos, finales


# ---- casos de uso ----


def alta_proveedor(actor, datos):
    """CMP-ALT-PRV: crea un proveedor activo y lo devuelve.

    - Precondición a: ``actor`` es un Gerente activo. Regla 1: razón social (jurídica) o nombre y apellido (física); correo obligatorio;
      teléfono opcional (D-21). Regla 2: CUIT obligatorio, válido (D-58) y único entre activos e inactivos: el de un activo da
      ``cuit_repetido``; el de un inactivo, ``ErrorDeCompras`` ``cuit_de_inactivo`` (la pantalla ofrece ``reactivar_proveedor``).
      Regla 3: especialidades, cero o más categorías activas.
    - Postcondición a y b: queda «activo» y un registro ``alta_proveedor`` en la misma transacción (D-22, D-36).
    """
    _exigir_gerente(actor)
    limpios, errores = _normalizar(datos, None)
    with transaction.atomic():
        _actor_sigue_activo(actor)
        existente = None
        if "cuit" in limpios and limpios["cuit"] and "cuit" not in errores:
            existente = Proveedor.objects.filter(cuit_proveedor=limpios["cuit"]).first()
            if existente is not None and existente.activo:
                errores["cuit"] = _error_cuit_repetido(existente).error_dict["cuit"]
        _lanzar_si_hay(errores)
        if existente is not None:
            raise ErrorDeCompras(
                "cuit_de_inactivo",
                f"Ya existe {existente}, dado de baja. Podés reactivarlo: conserva todo su historial.",
                campo="cuit",
                datos={"proveedor_id": existente.pk},
            )
        creado = Proveedor(
            tipo_proveedor=limpios["tipo"],
            cuit_proveedor=limpios["cuit"],
            razon_social_proveedor=limpios["razon_social"],
            nombre_proveedor=limpios["nombre"],
            apellido_proveedor=limpios["apellido"],
            email_proveedor=limpios["email"],
            telefono_proveedor=limpios["telefono"],
            estado_proveedor=Estado.ACTIVO,
        )
        try:
            with transaction.atomic():
                creado.save()
        except IntegrityError as error:
            if "proveedor_cuit_unico" in str(error):
                raise _error_cuit_repetido() from error
            raise
        categorias = _categorias(limpios["especialidades"])
        creado.especialidades.set(categorias)
        cambios = {"tipo_proveedor": {"antes": None, "despues": creado.tipo_proveedor}, "cuit": {"antes": None, "despues": creado.cuit_proveedor}}
        for clave, atributo in (
            ("razon_social", "razon_social_proveedor"),
            ("nombre", "nombre_proveedor"),
            ("apellido", "apellido_proveedor"),
            ("email", "email_proveedor"),
            ("telefono", "telefono_proveedor"),
        ):
            valor = getattr(creado, atributo)
            if valor:
                cambios[clave] = {"antes": None, "despues": valor}
        if categorias:
            cambios["especialidades"] = {"antes": None, "despues": _referencias(categorias)}
        cambios["estado"] = {"antes": None, "despues": Estado.ACTIVO.value}
        RegistroAuditoria.objects.registrar(
            usuario=actor, accion=RegistroAuditoria.Accion.ALTA_PROVEEDOR, afectados=[creado], detalle={"cambios": cambios}
        )
    return creado


def reactivar_proveedor(actor, proveedor_id, datos):
    """CMP-ALT-PRV (postcondición c y regla 2): reactiva al proveedor inactivo con ese CUIT, con los datos que indicó el actor, y lo devuelve.
    El CUIT y el tipo no cambian. Los mismos controles que el alta; uno que no está inactivo se rechaza con ``proveedor_no_inactivo``.
    Se audita como ``reactivacion_proveedor``: el cambio de estado y los datos que cambiaron."""
    _exigir_gerente(actor)
    with transaction.atomic():
        proveedor = _bloquear_proveedor(actor, proveedor_id)
        if proveedor.activo:
            raise ErrorDeCompras("proveedor_no_inactivo", "El proveedor no está dado de baja.")
        vinculadas = set(proveedor.especialidades.values_list("pk", flat=True))
        limpios, errores = _normalizar(datos, proveedor.tipo_proveedor, cuit_fijo=proveedor.cuit_proveedor, vinculadas=vinculadas)
        _lanzar_si_hay(errores)
        cambios, campos, finales = _aplicar(proveedor, limpios)
        proveedor.estado_proveedor = Estado.ACTIVO
        _guardar(proveedor, campos + ["estado_proveedor"])
        if "especialidades" in cambios:
            proveedor.especialidades.set(finales)
        cambios["estado"] = {"antes": Estado.INACTIVO.value, "despues": Estado.ACTIVO.value}
        RegistroAuditoria.objects.registrar(
            usuario=actor, accion=RegistroAuditoria.Accion.REACTIVACION_PROVEEDOR, afectados=[proveedor], detalle={"cambios": cambios}
        )
    return proveedor


def modificar_proveedor(actor, proveedor_id, datos):
    """CMP-MOD-PRV: modifica un proveedor activo y lo devuelve.

    - Precondición a: Gerente activo. Precondición b: el proveedor está activo (``proveedor_inactivo``). El tipo no se cambia.
    - Regla 1: las mismas validaciones que el alta (CUIT único entre todos, ``cuit_repetido``). Regla 2: teléfono, correo, nombre,
      apellido, razón social y especialidades se modifican siempre; el CUIT no si tiene pedidos u órdenes (``cuit_con_pedidos``).
    - Regla 4: las categorías dadas de baja que ya tenía se conservan. D-28: sin cambios no se escribe ni se audita.
    - Postcondición b: un registro ``modificacion_proveedor`` con los campos modificados (antes y después).
    """
    _exigir_gerente(actor)
    with transaction.atomic():
        proveedor = _bloquear_proveedor(actor, proveedor_id)
        if not proveedor.activo:
            raise ErrorDeCompras("proveedor_inactivo", "El proveedor está dado de baja: solo se puede reactivar.")
        vinculadas = set(proveedor.especialidades.values_list("pk", flat=True))
        limpios, errores = _normalizar(datos, proveedor.tipo_proveedor, vinculadas=vinculadas)
        cuit_nuevo = limpios.get("cuit") if "cuit" not in errores else None
        if cuit_nuevo and cuit_nuevo != proveedor.cuit_proveedor:
            if tiene_pedidos_u_ordenes(proveedor):
                errores["cuit"] = [_error("El CUIT no se puede cambiar: el proveedor tiene pedidos u órdenes de compra.", "cuit_con_pedidos")]
            else:
                otro = Proveedor.objects.filter(cuit_proveedor=cuit_nuevo).exclude(pk=proveedor.pk).first()
                if otro is not None:
                    errores["cuit"] = _error_cuit_repetido(otro).error_dict["cuit"]
        _lanzar_si_hay(errores)
        cambios, campos, finales = _aplicar(proveedor, limpios, cuit_nuevo=cuit_nuevo)
        if not cambios:
            return proveedor
        if campos:
            _guardar(proveedor, campos)
        if "especialidades" in cambios:
            proveedor.especialidades.set(finales)
        RegistroAuditoria.objects.registrar(
            usuario=actor, accion=RegistroAuditoria.Accion.MODIFICACION_PROVEEDOR, afectados=[proveedor], detalle={"cambios": cambios}
        )
    return proveedor


def baja_proveedor(actor, proveedor_id):
    """CMP-BAJ-PRV: da de baja lógica a un proveedor activo y lo devuelve.

    - Precondición a: Gerente activo. Precondición b: el proveedor está activo (``proveedor_inactivo``).
    - Precondiciones c y d y regla 2: sin órdenes no terminadas ni pagos pendientes (``impedimentos_de_baja``; hoy vacía). Si hay, se rechaza
      con ``baja_con_impedimentos`` y TODOS juntos (qué lo impide y cómo resolverlo). Se calculan con el proveedor ya bloqueado.
    - Regla 1 y postcondición a: queda «inactivo» y conserva todo. Regla 3 (CMP-02b): sus enlaces vigentes de pedidos en cotización pasan a «anulado» (``enlaces.anular_enlaces_de_proveedor``) y van en la auditoría.
    - Postcondición b: un registro ``baja_proveedor`` con el cambio de estado.
    """
    _exigir_gerente(actor)
    with transaction.atomic():
        proveedor = _bloquear_proveedor(actor, proveedor_id)
        if not proveedor.activo:
            raise ErrorDeCompras("proveedor_inactivo", "El proveedor ya está dado de baja.")
        impedimentos = impedimentos_de_baja(proveedor)
        if impedimentos:
            detalle = " ".join(f"{i.texto} {i.como_resolver}" for i in impedimentos)
            raise ErrorDeCompras(
                "baja_con_impedimentos", f"No se puede dar de baja a {proveedor}. {detalle}", datos={"impedimentos": list(impedimentos)}
            )
        proveedor.estado_proveedor = Estado.INACTIVO
        proveedor.save(update_fields=["estado_proveedor"])
        # Regla 3 (CMP-02b): sus enlaces vigentes de pedidos en cotización dejan de servir; la cotización «propuesta» no se toca.
        anulados = enlaces.anular_enlaces_de_proveedor(proveedor)
        detalle = {"cambios": {"estado": {"antes": Estado.ACTIVO.value, "despues": Estado.INACTIVO.value}}}
        if anulados:
            detalle["datos"] = {"enlaces_anulados": [referencia(e) for e in anulados]}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_PROVEEDOR,
            afectados=[proveedor, *anulados],
            detalle=detalle,
        )
    return proveedor


# ---- consulta (CMP-CNS-PRV) ----


def _con_categorias_activas(consulta):
    """``consulta`` con las categorías activas de cada proveedor en ``categorias_activas`` (una consulta aparte para todos): la regla 3 de
    CMP-CNS-PRV muestra solo las activas, aunque el vínculo con las dadas de baja se conserve."""
    return consulta.prefetch_related(
        Prefetch("especialidades", queryset=TipoInsumo.objects.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO), to_attr="categorias_activas")
    )


def listar_proveedores(actor, filtros=None):
    """CMP-CNS-PRV: los proveedores del alcance de ``actor`` (todos, activos e inactivos; regla 1), los activos primero y por nombre.
    ``filtros`` (regla 2): ``estado`` («activo», «inactivo» o vacío para todos), ``texto`` (cada palabra en la razón social, el nombre, el
    apellido o el CUIT; el CUIT también por sus dígitos, con o sin guiones) y ``tipo_de_insumo`` (id de una categoría). No audita (SEG-14)."""
    _exigir_lectura(actor)
    filtros = filtros or {}
    consulta = Proveedor.objects.en_alcance_de(actor)
    if filtros.get("estado") in Estado.values:
        consulta = consulta.filter(estado_proveedor=filtros["estado"])
    for palabra in _texto(filtros.get("texto")).split():
        condicion = Q(razon_social_proveedor__icontains=palabra) | Q(nombre_proveedor__icontains=palabra) | Q(apellido_proveedor__icontains=palabra)
        digitos = "".join(c for c in palabra if c.isdigit())
        if len(digitos) >= 2:
            condicion |= Q(cuit_proveedor__contains=digitos)
        consulta = consulta.filter(condicion)
    if filtros.get("tipo_de_insumo"):
        consulta = consulta.filter(especialidades=filtros["tipo_de_insumo"])
    consulta = consulta.annotate(
        _nombre=Case(
            When(tipo_proveedor=Tipo.JURIDICA, then=Lower("razon_social_proveedor")),
            default=Lower(Concat(F("nombre_proveedor"), Value(" "), F("apellido_proveedor"))),
        )
    )
    return _con_categorias_activas(consulta.distinct().order_by("estado_proveedor", "_nombre", "id"))


def ficha_de_proveedor(actor, proveedor_id):
    """CMP-CNS-PRV regla 4: el proveedor con sus categorías activas (404 si no existe). Sus pedidos, órdenes, pagos y reclamos se completan
    de CMP-02a a CMP-06. No audita."""
    _exigir_lectura(actor)
    return get_object_or_404(_con_categorias_activas(Proveedor.objects.en_alcance_de(actor)), pk=proveedor_id)


def acciones_permitidas(actor, proveedor):
    """D-30: las acciones que ``actor`` puede hacer sobre ``proveedor``, un ``frozenset`` (regla 5 de CMP-CNS-PRV). Solo el Gerente activo: sobre un
    proveedor activo, modificar y dar de baja; sobre uno inactivo, reactivar (desde el alta). El Agrónomo solo consulta. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        return frozenset()
    if proveedor.activo:
        return frozenset({ACCION_MODIFICAR, ACCION_BAJA})
    return frozenset({ACCION_REACTIVAR})
