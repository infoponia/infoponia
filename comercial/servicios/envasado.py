# PROD-PNF-ENV · Planificar Envasado (COM-05a2; docs/casos_de_uso/produccion/envasado.md, «Cómo se aplica en la ronda «Comercial 1»»; D-66 puntos 8, 11 y 13).
# El Agrónomo del invernadero de origen reserva envases del depósito para cada entrega «a realizar»: crea, cambia y quita las reservas de insumo (`ReservaInsumo`) de la entrega.
# El código va en `comercial` (D-59, A3: el caso de uso cambia una entrega); las reservas se crean con el núcleo de `produccion` (`produccion/servicios/reservas.py`) y lo disponible lo da
# `inventario` (`stock.disponible_para_planificar`). Reservar NO descuenta stock: el consumo se registra al concretar la entrega (COM-06).
#
# Hay tres lecturas sin escribir (`entregas_para_envasar`, `datos_de_envasado` y `resumen_de_envasado`) y una escritura (`planificar_envasado`). Los errores de negocio son
# `ValidationError` con `code` y el campo de la fila (`cantidad_<id del envase>`), como el resto de `comercial`.
#
# Bloqueos de `planificar_envasado` (`docs/patrones/bloqueos.md`, «Entregas y envasado», «Planificar el envasado»; `FOR NO KEY UPDATE`): la cuenta del Agrónomo → el invernadero
# (`bloquear_invernadero_activo`, el semáforo de la planificación, D-66 punto 11) → los `InsumoInvernadero` de los envases (de la carga y de las reservas activas, por id) y sus lotes
# (`docs/patrones/stock.md`, sección 5) → la entrega (`OrdenTrabajo`) → sus reservas de insumo. Con todo tomado se relee y se verifica (10a, 10c y 10b) antes de escribir.

import json
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.urls import reverse

from comercial.models import DetalleEntrega, Entrega, Vehiculo
from comercial.servicios import entregas
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario import categorias, unidades
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.servicios import alertas_de_stock, insumos_invernadero, stock
from maestros.models import Invernadero
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.models import OrdenTrabajo, ReservaInsumo
from produccion.servicios import reservas

A_REALIZAR = OrdenTrabajo.Estado.A_REALIZAR
ACTIVA = ReservaInsumo.Estado.ACTIVA
RETIRO = Entrega.Modalidad.RETIRO

AYUDA_DE_STOCK = "Si necesitás más, pedilo con un pedido de compra o, si el depósito tiene más de lo registrado, ajustá el stock."
SIN_ENVASES_HABILITADOS = "Este invernadero no tiene envases habilitados."
REEMPLAZADO = "Ya estaba en la lista: se reemplazó la cantidad."

FilaDeEnvasado = namedtuple(
    "FilaDeEnvasado",
    "entrega codigo contrato_codigo invernadero invernadero_id cliente destino es_retiro transportista contenido peso fecha cuando atrasada tiene_envasado en_curso",
)
EnvaseOfrecido = namedtuple("EnvaseOfrecido", "insumo_invernadero_id nombre unidad_codigo unidad disponible reservado en_carga")
FilaDeCarga = namedtuple("FilaDeCarga", "insumo_invernadero_id nombre unidad_codigo unidad cantidad anterior disponible queda error codigo_de_error ayuda aviso")
DatosDeEnvasado = namedtuple("DatosDeEnvasado", "fila fecha_de_referencia ofrecidos filas huella avisos bloqueo url_habilitar")
FilaDeResumen = namedtuple("FilaDeResumen", "nombre unidad anterior nueva queda situacion")
ResumenDeEnvasado = namedtuple("ResumenDeEnvasado", "fila filas quitados aviso_sin_envasado")


@dataclass(frozen=True)
class CargaDeEnvasado:
    """Lo que el Agrónomo cargó: `filas` es una tupla de `(id del InsumoInvernadero, cantidad como texto)`, una por envase (indicar un envase que ya está reemplaza su cantidad:
    extensión 6c), ordenada por id; `huella` es la de las reservas de la entrega al abrir la pantalla (10c); `reemplazados` son los envases cuya cantidad se reemplazó (6c)."""

    entrega_id: int
    filas: tuple = ()
    huella: str = ""
    reemplazados: tuple = ()

    @classmethod
    def desde_post(cls, entrega_id, post):
        """Arma la carga desde un `POST`: `cantidad_<id>` por cada fila, `quitar=<id>` (una fila menos) y `agregar=<id>` con `nueva_<id>` (una fila más; si ya estaba, reemplaza)."""
        filas, reemplazados = {}, []
        for campo, valor in post.items():
            if campo.startswith("cantidad_") and campo[9:].isdigit():
                filas[int(campo[9:])] = (valor or "").strip()
        for valor in post.getlist("quitar"):
            if valor.isdigit():
                filas.pop(int(valor), None)
        agregar = (post.get("agregar") or "").strip()
        if agregar.isdigit():
            iin_id = int(agregar)
            if iin_id in filas:
                reemplazados.append(iin_id)
            filas[iin_id] = (post.get(f"nueva_{iin_id}") or "").strip()
        return cls(entrega_id, tuple(sorted(filas.items())), (post.get("huella") or "").strip(), tuple(reemplazados))


def _rechazar(errores):
    """`ValidationError` con códigos estables: `errores` es `{campo: [(codigo, mensaje)]}`."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo) for codigo, mensaje in lista] for campo, lista in errores.items()})


def _campo(iin_id):
    return f"cantidad_{iin_id}"


def _numero(valor):
    """«20» o «2,5»."""
    return entregas._cantidad(valor)


def _texto_de_unidad(unidad_codigo, cantidad):
    """«unidad» o «unidades» para una unidad contada; para las demás, su abreviatura (kg, g, L…)."""
    if unidad_codigo == unidades.Unidad.UNIDAD:
        return "unidad" if Decimal(cantidad) == 1 else "unidades"
    return unidades.Unidad(unidad_codigo).label


def _con_unidad(cantidad, unidad_codigo):
    return f"{_numero(cantidad)} {_texto_de_unidad(unidad_codigo, cantidad)}"


def _error_de_cantidad(unidad_codigo):
    """6a: «Ingresá una cantidad mayor que 0, con hasta 2 decimales (g).» o, para la unidad, «… un número entero (unidad).»"""
    etiqueta = unidades.Unidad(unidad_codigo).label
    decimales = unidades.decimales_de(unidad_codigo)
    if decimales == 0:
        return f"Ingresá una cantidad mayor que 0, un número entero ({etiqueta})."
    return f"Ingresá una cantidad mayor que 0, con hasta {decimales} decimal{'es' if decimales > 1 else ''} ({etiqueta})."


def _leer_cantidad(texto, unidad_codigo):
    """`Decimal` mayor que 0 con los decimales de la unidad (coma o punto), o `None` si no es válida (regla «Cantidad válida»)."""
    if not (texto or "").strip():
        return None
    try:
        cantidad = unidades.validar_cantidad(texto, unidad_codigo)
    except ValidationError:
        return None
    return cantidad if cantidad > 0 else None


def huella_de(entrega_id):
    """Un texto estable con las reservas de insumo de la entrega (`id`, envase, cantidad reservada y estado, por id): cambia si cualquiera cambia (10c). Lee de la base."""
    filas = ReservaInsumo.objects.filter(orden_id=entrega_id).order_by("pk").values_list("pk", "insumo_invernadero_id", "cantidad_reservada", "estado")
    return json.dumps([list(f) for f in filas], default=str)


# ---- quién y qué entrega ----


def _exigir_agronomo(actor):
    """Solo el Agrónomo activo (regla «Quién lo ejecuta»; requisito «Solo el Agrónomo a cargo»): cualquier otro rol o cuenta inactiva, `PermissionDenied`."""
    if not getattr(actor, "is_active", False) or rol_de(actor) != Usuario.Rol.AGRONOMO:
        raise PermissionDenied("Solo el Agrónomo a cargo del invernadero de origen planifica el envasado.")


def _entrega_de(actor, entrega_id):
    """La entrega, leída sin bloquear. `Http404` si no existe o no es una entrega; `PermissionDenied` si su invernadero no está a cargo de `actor` (D-28)."""
    entrega = (
        Entrega.objects.select_related(
            "invernadero", "contrato_entrega__cliente", "transportista", "direccion_destino__localidad", "direccion_destino__direccionurbana", "direccion_destino__direccionrural"
        )
        .filter(pk=entrega_id)
        .first()
    )
    if entrega is None:
        raise Http404("No existe esa entrega.")
    if entrega.invernadero.agronomo_id != actor.pk:
        raise PermissionDenied("El invernadero de origen de la entrega no está a tu cargo.")
    return entrega


# ---- la lista (pasos 2 y 2a) ----


def _filas(lista, hoy):
    """Las `FilaDeEnvasado` de las entregas dadas: una consulta por tabla, nunca una por entrega."""
    ids = [e.pk for e in lista]
    pesos = entregas.peso_de_entregas(ids)
    lineas = list(DetalleEntrega.objects.filter(entrega_id__in=ids).select_related("detalle_venta__variedad__cultivo", "detalle_suministro__variedad__cultivo").order_by("pk"))
    planificadas = entregas.cantidades_planificadas([l.pk for l in lineas])
    contenidos = defaultdict(list)
    for linea in lineas:
        if planificadas[linea.pk] > 0:
            contenidos[linea.entrega_id].append(f"{planificadas[linea.pk]} {(linea.detalle_venta or linea.detalle_suministro).variedad}")
    con_envasado = set(ReservaInsumo.objects.filter(orden_id__in=ids, estado=ACTIVA).values_list("orden_id", flat=True))
    en_ruta = {v.transportista_id: v for v in Vehiculo.objects.filter(transportista_id__in=[e.transportista_id for e in lista if e.transportista_id])}
    filas = []
    for e in lista:
        vehiculo = en_ruta.get(e.transportista_id)
        curso = e.transportista_id is not None and e.fecha_programada_orden <= hoy and vehiculo is not None and vehiculo.esta_en_ruta(hoy)
        contrato = e.contrato_entrega
        filas.append(
            FilaDeEnvasado(
                entrega=e,
                codigo=e.codigo,
                contrato_codigo=contrato.codigo,
                invernadero=str(e.invernadero),
                invernadero_id=e.invernadero_id,
                cliente=contrato.cliente.nombre_visible,
                destino=entregas._destino_de_la_fila(e),
                es_retiro=e.modalidad_entrega == RETIRO,
                transportista=e.transportista.get_full_name() if e.transportista_id else "",
                contenido=contenidos[e.pk],
                peso=pesos[e.pk],
                fecha=e.fecha_programada_orden,
                cuando=entregas._cuando(e.fecha_programada_orden, hoy, True),
                atrasada=e.fecha_programada_orden < hoy,
                tiene_envasado=e.pk in con_envasado,
                en_curso=curso,
            )
        )
    return filas


def invernaderos_para_envasar(actor):
    """Los invernaderos activos a cargo del Agrónomo (para el filtro de la lista), por nombre."""
    _exigir_agronomo(actor)
    return list(Invernadero.objects.en_alcance_de(actor).order_by("nombre_invernadero", "pk"))


def entregas_para_envasar(actor, *, invernadero_id=None, fecha=None):
    """Pasos 2 y 2a: las entregas «a realizar» de los invernaderos **activos** a cargo del Agrónomo, por fecha programada y después id. `fecha` filtra por la fecha programada exacta.
    Cada `FilaDeEnvasado` trae el invernadero, el cliente, la modalidad, el transportista, el contenido, el peso, la fecha (con «atrasada»), `tiene_envasado` y `en_curso`.
    Una consulta por tabla. No escribe."""
    _exigir_agronomo(actor)
    consulta = Entrega.objects.filter(estado_orden=A_REALIZAR, invernadero__in=Invernadero.objects.en_alcance_de(actor))
    if invernadero_id:
        consulta = consulta.filter(invernadero_id=invernadero_id)
    if fecha:
        consulta = consulta.filter(fecha_programada_orden=fecha)
    consulta = consulta.select_related(
        "invernadero", "contrato_entrega__cliente", "transportista", "direccion_destino__localidad", "direccion_destino__direccionurbana", "direccion_destino__direccionrural"
    ).order_by("fecha_programada_orden", "pk")
    return _filas(list(consulta), stock.hoy())


# ---- lectura común de la carga (pasos 4 a 8; también la relee el registro, ya bloqueado) ----


@dataclass
class _Lectura:
    """Todo lo que `datos_de_envasado`, `resumen_de_envasado` y `planificar_envasado` necesitan saber de una carga (sin escribir)."""

    entrega: object
    hoy: object
    fecha_de_referencia: object
    propias: dict  # {iin_id: ReservaInsumo activa}
    ofrecidos: list  # [InsumoInvernadero] habilitados y activos (envases), por nombre
    envases: dict  # {iin_id: InsumoInvernadero} de todo lo que interviene
    disponibles: dict  # {iin_id: Decimal} lo disponible para planificar, más lo propio (extensión 3a)
    filas: list  # [FilaDeCarga]
    en_curso: bool


def _leer(actor, entrega_id, carga=None, busqueda=""):
    """Lee la entrega, sus reservas, los envases ofrecidos y lo disponible, y evalúa cada fila de la carga. No escribe y no bloquea: el registro lo llama con todo ya bloqueado."""
    _exigir_agronomo(actor)
    entrega = _entrega_de(actor, entrega_id)
    hoy = stock.hoy()
    fecha_de_referencia = max(entrega.fecha_programada_orden, hoy)  # regla «Fecha de referencia» (4b)
    propias = {r.insumo_invernadero_id: r for r in ReservaInsumo.objects.filter(orden_id=entrega.pk, estado=ACTIVA).order_by("pk")}
    ofrecidos = [
        i
        for i in insumos_invernadero.habilitados(entrega.invernadero_id)
        if i.insumo.tipo_insumo.codigo == categorias.ENVASES and i.insumo.activo  # por código de la categoría del sistema, nunca por nombre (regla «Envase»)
    ]
    ofrecidos.sort(key=lambda i: (i.insumo.nombre_insumo.lower(), i.pk))
    pedidos = {iin_id for iin_id, _ in carga.filas} if carga is not None else set()
    envases = {i.pk: i for i in ofrecidos}
    faltan = (set(propias) | pedidos) - set(envases)
    for i in InsumoInvernadero.objects.select_related("insumo__tipo_insumo").filter(pk__in=faltan, invernadero_id=entrega.invernadero_id):
        envases[i.pk] = i
    disponibles = {
        iin_id: dpp + (propias[iin_id].cantidad_reservada if iin_id in propias else Decimal(0))  # regla «Disponible al modificar»
        for iin_id, dpp in stock.disponible_para_planificar(list(envases), fecha_de_referencia).items()
    }
    ofrecidos_ids = {i.pk for i in ofrecidos}
    filas = []
    if carga is None:
        origen = [(iin_id, _numero(r.cantidad_reservada)) for iin_id, r in propias.items()]
    else:
        origen = list(carga.filas)
    for iin_id, texto in origen:
        iin = envases.get(iin_id)
        if iin is None:
            filas.append(FilaDeCarga(iin_id, "Envase desconocido", "unidad", "unidad", texto, None, Decimal(0), None, "Ese envase no existe en este invernadero.", "envase_no_ofrecido", "", ""))
            continue
        unidad_codigo = iin.insumo.unidad_medida_insumo
        anterior = propias[iin_id].cantidad_reservada if iin_id in propias else None
        disponible = disponibles.get(iin_id, Decimal(0))
        cantidad = _leer_cantidad(texto, unidad_codigo)
        error, codigo, ayuda = "", "", ""
        if cantidad is None:
            error, codigo = _error_de_cantidad(unidad_codigo), "cantidad_invalida"
        elif iin_id not in ofrecidos_ids and (anterior is None or cantidad > anterior):
            error, codigo = "Este envase ya no está habilitado: solo podés bajar su cantidad o quitarlo.", "envase_no_ofrecido"
        elif cantidad > disponible:
            verbo = "queda" if disponible == 1 and unidad_codigo == unidades.Unidad.UNIDAD else "quedan"
            error = f"Supera lo disponible: {verbo} {_con_unidad(disponible, unidad_codigo)} (sin contar los lotes que estarán vencidos el {fecha_de_referencia:%d/%m})."
            codigo, ayuda = "supera_disponible", AYUDA_DE_STOCK
        aviso = REEMPLAZADO if carga is not None and iin_id in carga.reemplazados else ""
        filas.append(
            FilaDeCarga(
                iin_id,
                iin.insumo.nombre_insumo,
                unidad_codigo,
                unidades.Unidad(unidad_codigo).label,
                texto,
                anterior,
                disponible,
                (disponible - cantidad) if cantidad is not None else None,
                error,
                codigo,
                ayuda,
                aviso,
            )
        )
    filas.sort(key=lambda f: (f.nombre.lower(), f.insumo_invernadero_id))
    if busqueda:
        ofrecidos = [i for i in ofrecidos if busqueda.strip().lower() in i.insumo.nombre_insumo.lower()]
    return _Lectura(entrega, hoy, fecha_de_referencia, propias, ofrecidos, envases, disponibles, filas, entregas.en_curso(entrega, hoy))


def _texto_de_en_curso(entrega):
    nombre = entrega.transportista.get_full_name() if entrega.transportista_id else "El transportista"
    return f"{nombre} ya inició la ruta con esta entrega: su envasado no se puede cambiar. Los envases se confirman al concretarla."


def _exigir_pendiente(entrega, en_curso):
    """Extensión 10a (y 3b): la entrega sigue «a realizar» y no está en curso."""
    if entrega.estado_orden != A_REALIZAR:
        texto = "concretada" if entrega.estado_orden == OrdenTrabajo.Estado.CONCRETADA else "cancelada"
        raise _rechazar({"__all__": [("entrega_no_a_realizar", f"La entrega {entrega.codigo} ya no está a realizar: está {texto}.")]})
    if en_curso:
        raise _rechazar({"__all__": [("entrega_en_curso", _texto_de_en_curso(entrega))]})


# ---- pasos 4 a 6: el detalle y la carga ----


def datos_de_envasado(actor, entrega_id, carga=None, busqueda=""):
    """Pasos 4 a 6 (sin escribir): el detalle de la entrega, los envases ofrecidos (con lo disponible y la unidad; `busqueda` los filtra por nombre, variación 5), las filas de la carga con lo
    disponible de cada envase y su error, la **huella** de las reservas de la entrega (10c) y los avisos (3b, 4a, 4b). Sin `carga`, la inicial es la de las reservas activas (3a) o vacía.
    `ValidationError` con `entrega_no_a_realizar` si la entrega ya se concretó o canceló (10a) y `invernadero_inactivo` si su invernadero está inactivo."""
    lectura = _leer(actor, entrega_id, carga, busqueda)
    entrega = lectura.entrega
    if not entrega.invernadero.activo:
        raise _rechazar({"__all__": [("invernadero_inactivo", "El invernadero de origen está inactivo: no se puede planificar el envasado.")]})
    if entrega.estado_orden != A_REALIZAR:
        _exigir_pendiente(entrega, False)
    en_carga = {f.insumo_invernadero_id for f in lectura.filas}
    ofrecidos = [
        EnvaseOfrecido(
            i.pk,
            i.insumo.nombre_insumo,
            i.insumo.unidad_medida_insumo,
            unidades.Unidad(i.insumo.unidad_medida_insumo).label,
            lectura.disponibles.get(i.pk, Decimal(0)),
            lectura.propias[i.pk].cantidad_reservada if i.pk in lectura.propias else None,
            i.pk in en_carga,
        )
        for i in lectura.ofrecidos
    ]
    avisos = []
    if not lectura.ofrecidos and not busqueda:
        avisos.append(SIN_ENVASES_HABILITADOS)  # 4a
    if entrega.fecha_programada_orden < lectura.hoy:
        avisos.append("La entrega está atrasada: lo disponible se calcula a la fecha de hoy.")  # 4b
    huella = carga.huella if carga is not None and carga.huella else huella_de(entrega.pk)
    return DatosDeEnvasado(
        fila=_filas([entrega], lectura.hoy)[0],
        fecha_de_referencia=lectura.fecha_de_referencia,
        ofrecidos=ofrecidos,
        filas=lectura.filas,
        huella=huella,
        avisos=avisos,
        bloqueo=_texto_de_en_curso(entrega) if lectura.en_curso else None,  # 3b
        url_habilitar=reverse("inventario:existencias"),
    )


# ---- pasos 7 y 8: el resumen ----


def _errores_de_filas(lectura, solo=None):
    """`{campo: [(codigo, mensaje)]}` de las filas con error (de un código, si `solo`)."""
    return {_campo(f.insumo_invernadero_id): [(f.codigo_de_error, f.error)] for f in lectura.filas if f.error and (solo is None or f.codigo_de_error == solo)}


def _cantidades_de_la_carga(lectura):
    """`{iin_id: Decimal}` de las filas de la carga (todas válidas)."""
    return {f.insumo_invernadero_id: _leer_cantidad(f.cantidad, f.unidad_codigo) for f in lectura.filas}


def _verificar_carga(lectura):
    """8a (sin envases) y 8c (sin cambios): se lanzan con la carga ya sin errores de fila. Devuelve las cantidades nuevas."""
    nuevas = _cantidades_de_la_carga(lectura)
    if not nuevas and not lectura.propias:
        raise _rechazar({"__all__": [("sin_envases", "Indicá al menos un envase.")]})
    if nuevas == {iin_id: r.cantidad_reservada for iin_id, r in lectura.propias.items()}:
        raise _rechazar({"__all__": [("sin_cambios", "No hay cambios para registrar.")]})
    return nuevas


def resumen_de_envasado(actor, carga):
    """Pasos 7 y 8 (sin escribir): por envase, la cantidad anterior (si la había) y la nueva, lo disponible que le queda y los quitados; el aviso de 8b. Lanza `ValidationError` con los
    errores de las filas (6a, 6b), `sin_envases` (8a) y `sin_cambios` (8c), y `entrega_no_a_realizar` o `entrega_en_curso` (10a)."""
    lectura = _leer(actor, carga.entrega_id, carga)
    _exigir_pendiente(lectura.entrega, lectura.en_curso)
    errores = _errores_de_filas(lectura)
    if errores:
        raise _rechazar(errores)
    nuevas = _verificar_carga(lectura)
    filas = [
        FilaDeResumen(
            f.nombre,
            f.unidad,
            f.anterior,
            nuevas[f.insumo_invernadero_id],
            f.queda,
            "nuevo" if f.anterior is None else ("igual" if f.anterior == nuevas[f.insumo_invernadero_id] else "cambia"),
        )
        for f in lectura.filas
    ]
    quitados = [
        (lectura.envases[iin_id].insumo.nombre_insumo, unidades.Unidad(lectura.envases[iin_id].insumo.unidad_medida_insumo).label, r.cantidad_reservada)
        for iin_id, r in lectura.propias.items()
        if iin_id not in nuevas
    ]
    return ResumenDeEnvasado(_filas([lectura.entrega], lectura.hoy)[0], filas, quitados, aviso_sin_envasado=not nuevas)  # 8b: todos quitados


# ---- pasos 9 a 11: el registro ----


def planificar_envasado(actor, carga):
    """Pasos 9 a 11. En una única transacción: bloquea (cuenta → invernadero → envases y lotes → entrega → reservas), relee y verifica (10a: la entrega sigue «a realizar» y no está en
    curso; 10c: sus reservas no cambiaron, `envasado_cambio`; 10b: cada cantidad nueva o aumentada sigue cubierta, `disponible_cambio`), y registra con el núcleo de `produccion`:
    `reservas.reservar` por cada envase nuevo (a), `cambiar_cantidad` por cada cambio (b) y `cancelar` por cada quitado (b). Después reevalúa las alertas de stock de los envases que
    bajaron o se quitaron y audita (`planificacion_envasado`, e y f). No cambia la entrega ni descuenta stock. Devuelve la entrega.

    Errores: `PermissionDenied`, `Http404`, `invernadero_inactivo`, `entrega_no_a_realizar`, `entrega_en_curso`, `envasado_cambio`, `disponible_cambio`, `cantidad_invalida`,
    `envase_no_ofrecido`, `sin_envases` y `sin_cambios`."""
    _exigir_agronomo(actor)
    previa = _entrega_de(actor, carga.entrega_id)
    envases_ids = sorted({iin_id for iin_id, _ in carga.filas} | set(ReservaInsumo.objects.filter(orden_id=previa.pk, estado=ACTIVA).values_list("insumo_invernadero_id", flat=True)))
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk))
        if not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
            raise PermissionDenied("Tu cuenta ya no está activa.")
        invernadero = bloquear_invernadero_activo(previa.invernadero_id)  # `invernadero_inactivo` si se dio de baja
        if invernadero.agronomo_id != actor.pk:
            raise PermissionDenied("El invernadero de origen de la entrega ya no está a tu cargo.")
        list(InsumoInvernadero.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=envases_ids).order_by("pk"))
        list(LoteInsumo.objects.select_for_update(no_key=True).filter(insumo_invernadero_id__in=envases_ids).order_by("insumo_invernadero_id", "pk"))
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=previa.pk))
        list(ReservaInsumo.objects.select_for_update(no_key=True).filter(orden_id=previa.pk).order_by("pk"))

        lectura = _leer(actor, carga.entrega_id, carga)  # con todo bloqueado: lo que sigue es lo vigente
        _exigir_pendiente(lectura.entrega, lectura.en_curso)  # 10a
        if huella_de(previa.pk) != carga.huella:
            raise _rechazar({"__all__": [("envasado_cambio", "Mientras cargabas, el envasado de esta entrega cambió. Mirá cómo quedó y volvé a indicar tus cambios.")]})  # 10c
        otros = {c: m for c, m in _errores_de_filas(lectura).items() if m[0][0] != "supera_disponible"}
        if otros:
            raise _rechazar(otros)
        superan = {}
        for f in lectura.filas:
            if f.codigo_de_error == "supera_disponible":  # 10b: lo disponible bajó entre la carga y la confirmación
                superan[_campo(f.insumo_invernadero_id)] = [("disponible_cambio", f"Mientras cargabas, cambió lo disponible de {f.nombre}. {f.error}")]
        if superan:
            raise _rechazar(superan)
        nuevas = _verificar_carga(lectura)

        entrega = lectura.entrega
        creadas, cambiadas, canceladas, a_reevaluar = [], [], [], set()
        nombres = {i: e.insumo.nombre_insumo for i, e in lectura.envases.items()}
        for iin_id in sorted(nuevas):
            cantidad = nuevas[iin_id]
            if iin_id not in lectura.propias:
                creadas.append(reservas.reservar(entrega, lectura.envases[iin_id], cantidad, lectura.hoy))  # (a)
            elif lectura.propias[iin_id].cantidad_reservada != cantidad:
                reserva = lectura.propias[iin_id]
                antes = reserva.cantidad_reservada
                cambiadas.append((reservas.cambiar_cantidad(reserva, cantidad), antes))  # (b)
                if cantidad < antes:
                    a_reevaluar.add(iin_id)
        for iin_id in sorted(set(lectura.propias) - set(nuevas)):
            canceladas.append(reservas.cancelar(lectura.propias[iin_id]))  # (b)
            a_reevaluar.add(iin_id)
        for iin_id in sorted(a_reevaluar):  # regla 3 de `docs/api/stock.md`: se liberó stock
            alertas_de_stock.reevaluar_alertas_del_insumo(iin_id)

        datos = {"entrega": referencia(entrega)}
        if creadas:
            datos["reservas_creadas"] = [f"{nombres[r.insumo_invernadero_id]}: {_numero(r.cantidad_reservada)} ({r.fecha_reserva:%d/%m/%Y})" for r in creadas]
        cambios = {}
        if cambiadas:
            cambios["cantidad_reservada"] = {
                "antes": [f"{nombres[r.insumo_invernadero_id]}: {_numero(antes)}" for r, antes in cambiadas],
                "despues": [f"{nombres[r.insumo_invernadero_id]}: {_numero(r.cantidad_reservada)}" for r, _ in cambiadas],
            }
        if canceladas:
            cambios["estado_reserva_insumo"] = {
                "antes": [f"{nombres[r.insumo_invernadero_id]}: activa" for r in canceladas],
                "despues": [f"{nombres[r.insumo_invernadero_id]}: cancelada" for r in canceladas],
            }
        detalle = {"datos": datos}
        if cambios:
            detalle["cambios"] = cambios
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.PLANIFICACION_ENVASADO,
            afectados=[entrega, *creadas, *[r for r, _ in cambiadas], *canceladas],
            detalle=detalle,
        )
        return entrega
