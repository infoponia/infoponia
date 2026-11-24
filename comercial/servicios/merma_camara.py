# PROD-REG-MRM para una partida en cámara (COM-04b; docs/casos_de_uso/produccion/merma.md, «Cómo se aplica en la ronda «Comercial 1»»): extensiones 4a, 4a.4a, 4a.4b, 4b, 10c y 10d;
# postcondiciones f, g, h y j. La pantalla de merma de `produccion` (PRD-03) ofrece «Pérdida en cámara» con la URL de esta página (`entradas_de_comercial`, D-64 punto 11).
# Lo físico (la `Merma` sin etapa, la baja de la partida y el movimiento `merma_en_camara`) lo escribe el núcleo de `produccion` (`camara.aplicar_merma_de_partida`); acá se decide qué
# pasa con las reservas (el recorte de la regla 6 de 8.9 y volver a cubrir lo perdido, `camara.py`). Quién: el Capataz asignado y el Agrónomo a cargo, en sus invernaderos activos.
#
# Estructura: una lectura que NO escribe ni bloquea (`partidas_con_merma_posible`, `resumen_de_merma_en_camara`) y la función que escribe (`registrar_merma_en_camara`), que repite TODA
# la verificación después de bloquear (extensión 10d). Bloqueos: los de `camara.py` (cuentas → invernaderos → variedad → lotes y partidas → contratos y detalles → reservas y líneas;
# docs/patrones/bloqueos.md, «Cosecha y cámara»). Sin asientos (D-57).
# Decisión del estudiante (plan de COM-04b): la única causa que se ofrece es «Daño en cámara», porque el núcleo de `produccion` (`CAUSAS_DE_CAMARA`) solo admite esa y la de vencimiento
# (de InfoPonia); merma.md decía también las de lote en pie. La descripción llega hasta 300 caracteres (el límite del núcleo; merma.md decía 500).

from collections import defaultdict, namedtuple
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from comercial.models import DetalleReserva
from comercial.servicios import camara, stock_maduro
from core.models import RegistroAuditoria, Usuario, referencia
from maestros.models import Variedad
from produccion.models import Merma, StockCosechado
from produccion.servicios import alcance
from produccion.servicios import camara as fisico

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
LARGO_DE_LA_DESCRIPCION = 300
CAUSA_DE_CAMARA = Merma.Causa.DANO_EN_CAMARA

FilaDePartidaConMerma = namedtuple("FilaDePartidaConMerma", "partida_id codigo variedad lote_codigo fecha_limite disponible reservado libre")
ResumenDeMermaEnCamara = namedtuple("ResumenDeMermaEnCamara", "partida variedad cantidad causa descripcion disponible_resultante libre recortes")
ResultadoDeMermaEnCamara = namedtuple("ResultadoDeMermaEnCamara", "partida merma movimiento recortes agotada")


@dataclass(frozen=True)
class DatosDeMermaEnCamara:
    """Lo que la persona carga: la partida, la cantidad (un entero o el texto que escribió), la causa y la descripción (opcional), y lo que VIO (`visto_disponible`: la cantidad
    disponible de la partida en el resumen; si al confirmar cambió, `cambio_simultaneo`, extensión 10d; `None` no lo verifica)."""

    partida_id: object = None
    cantidad: object = None
    causa: str = ""
    descripcion: str = ""
    visto_disponible: object = None


def _rechazar(errores):
    """`ValidationError` con un error por campo y su código: `errores` es `{campo: [(codigo, mensaje)]}`."""
    raise ValidationError({campo: [ValidationError(mensaje, code=codigo) for codigo, mensaje in lista] for campo, lista in errores.items()})


def causas_de_camara():
    """Paso 4a.4b: las causas que se ofrecen, `[(valor, texto)]`: solo «Daño en cámara» (decisión del estudiante; «Vencimiento en cámara» es de InfoPonia)."""
    return [(CAUSA_DE_CAMARA.value, CAUSA_DE_CAMARA.label)]


def _entero(valor):
    """El entero de `valor` (un entero o un texto de un entero, sin signo), o `None`."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isascii() and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _invernaderos_del_actor(actor):
    """Los invernaderos activos en los que `actor` registra (Capataz asignado, Agrónomo a cargo); `PermissionDenied` si no tiene ninguno (otro rol o cuenta inactiva)."""
    invernaderos = alcance.invernaderos_del_actor(actor)
    if not invernaderos:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return invernaderos


def invernaderos_con_merma_en_camara(actor):
    """Paso 2 y extensión 4b: los invernaderos activos del actor con alguna partida «disponible» (aunque no tengan lotes activos). Otro rol, lista vacía."""
    propios = alcance.invernaderos_del_actor(actor)
    if not propios:
        return []
    con_partidas = set(
        StockCosechado.objects.filter(
            lote__invernadero_id__in=[i.pk for i in propios], estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE, cantidad_disponible_cosechado__gt=0
        ).values_list("lote__invernadero_id", flat=True)
    )
    return [i for i in propios if i.pk in con_partidas]


def partidas_con_merma_posible(actor, invernadero_id):
    """Paso 4a: las partidas «disponibles» del invernadero, por fecha límite, con su variedad, lote de origen, disponible, reservado y stock libre. `PermissionDenied` si el
    invernadero no es del actor. No escribe ni bloquea."""
    if invernadero_id not in {i.pk for i in _invernaderos_del_actor(actor)}:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    consulta = camara._con_libre(
        StockCosechado.objects.filter(
            lote__invernadero_id=invernadero_id, estado_stock_cosechado=StockCosechado.Estado.DISPONIBLE, cantidad_disponible_cosechado__gt=0
        )
    ).select_related("lote__siembra__variedad")
    return [
        FilaDePartidaConMerma(p.pk, p.codigo, str(p.lote.siembra.variedad), p.lote.codigo, p.fecha_limite, p.cantidad_disponible_cosechado, p.reservado, max(0, p.libre))
        for p in consulta.order_by("fecha_limite", "pk")
    ]


def _evaluar(actor, datos, *, bloqueado=False):
    """Valida los datos contra la partida (releída): `(partida, cantidad, descripcion)` o `ValidationError` por campo. `bloqueado` es verdadero cuando ya se bloqueó todo (extensión
    10d: se compara también lo que la persona vio). `PermissionDenied` si la partida no es de un invernadero del actor."""
    propios = {i.pk for i in _invernaderos_del_actor(actor)}
    errores = {}
    partida = None
    if not datos.partida_id:
        errores["partida"] = [("partida_obligatoria", "Elegí la partida.")]
    else:
        pk = _entero(datos.partida_id)
        partida = StockCosechado.objects.select_related("lote__siembra__variedad", "lote__invernadero").filter(pk=pk).first() if pk else None
        if partida is not None and partida.lote.invernadero_id not in propios:
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        if partida is None or partida.estado_stock_cosechado != StockCosechado.Estado.DISPONIBLE or partida.cantidad_disponible_cosechado <= 0:
            errores["partida"] = [("partida_no_disponible", "Esa partida ya no está disponible.")]
            partida = None
    cantidad = _entero(datos.cantidad)
    if partida is not None:
        vigente = partida.cantidad_disponible_cosechado
        visto = _entero(datos.visto_disponible)
        if bloqueado and datos.visto_disponible is not None and visto != vigente:
            errores["cantidad"] = [("cambio_simultaneo", f"La partida cambió mientras mirabas el resumen: ahora tiene {vigente} plantas disponibles. Revisá y volvé a intentar.")]
        elif cantidad is None or not 1 <= cantidad <= vigente:
            errores["cantidad"] = [("cantidad_invalida", f"Ingresá un número entero entre 1 y {vigente} (las plantas disponibles de la partida).")]
    elif "cantidad" not in errores and (cantidad is None or cantidad < 1):
        errores["cantidad"] = [("cantidad_invalida", "Ingresá un número entero de plantas, mayor que cero.")]
    if not datos.causa:
        errores["causa"] = [("causa_obligatoria", "Elegí la causa de la pérdida.")]
    elif datos.causa != CAUSA_DE_CAMARA:
        errores["causa"] = [("causa_invalida", "Esa causa no corresponde a una pérdida en cámara.")]
    descripcion = (datos.descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        errores["descripcion"] = [("descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.")]
    if errores:
        _rechazar(errores)
    return partida, cantidad, descripcion


def _recortes_de(por_detalle):
    """`[(código del contrato, plantas que pierde)]` en el orden del recorte, sumando los detalles de un mismo contrato."""
    suma, orden = defaultdict(int), []
    for a in por_detalle:
        if a.contrato.codigo not in suma:
            orden.append(a.contrato.codigo)
        suma[a.contrato.codigo] += a.recortado
    return [(codigo, suma[codigo]) for codigo in orden]


def _simular_recorte(partida, nueva_disponible):
    """Lo que `camara.recortar_partida` recortaría, SIN escribir: `[(código del contrato, plantas)]` en el orden de la regla (paso 9: qué contratos pierden producto)."""
    lineas = list(
        DetalleReserva.objects.filter(partida=partida, reserva__estado_reserva__in=camara.OCUPAN, cantidad_reservada__gt=0)
        .select_related("reserva__detalle_venta__compra_venta", "reserva__detalle_suministro__suministro")
        .order_by("pk")
    )
    exceso = sum(l.cantidad_reservada for l in lineas) - nueva_disponible
    if exceso <= 0:
        return []
    items = [camara.LineaARecortar("cv" if l.reserva.detalle_venta_id else "sum", l.reserva.fecha_entrega_reserva, l.reserva_id, l) for l in lineas]
    suma, orden = defaultdict(int), []
    for item in camara.orden_de_recorte(items):
        if exceso <= 0:
            break
        quitar = min(exceso, item.linea.cantidad_reservada)
        reserva = item.linea.reserva
        codigo = (reserva.detalle_venta.compra_venta if reserva.detalle_venta_id else reserva.detalle_suministro.suministro).codigo
        if codigo not in suma:
            orden.append(codigo)
        suma[codigo] += quitar
        exceso -= quitar
    return [(codigo, suma[codigo]) for codigo in orden]


def resumen_de_merma_en_camara(actor, datos):
    """Paso 9: valida todo como `registrar_merma_en_camara` (sin bloquear) y presenta la partida, la cantidad, la causa, la disponible que queda y, si la pérdida supera el stock
    libre, qué contratos pierden producto y cuánto, en el orden del recorte (se intentará volver a cubrirlos). No escribe."""
    partida, cantidad, descripcion = _evaluar(actor, datos)
    reservado = camara._reservado_de(partida.pk)
    libre = max(0, partida.cantidad_disponible_cosechado - reservado)
    nueva = partida.cantidad_disponible_cosechado - cantidad
    return ResumenDeMermaEnCamara(
        partida, str(partida.lote.siembra.variedad), cantidad, datos.causa, descripcion, nueva, libre, _simular_recorte(partida, nueva)
    )


def _registrar(actor, datos, previo):
    """Un intento de registrar (todo en una transacción). `previo` son los ids de detalles con líneas que vio la lectura sin bloquear; si al bloquear aparecen otros,
    `camara._ContratosNuevos`."""
    detalles_de_venta, detalles_de_suministro = previo
    with transaction.atomic():
        previa = StockCosechado.objects.select_related("lote__siembra__variedad", "lote__invernadero").get(pk=_entero(datos.partida_id))
        ventas, suministros = camara._contratos_de(detalles_de_venta, detalles_de_suministro)
        invernadero_id = previa.lote.invernadero_id
        camara._bloquear_cuentas({actor.pk, previa.lote.invernadero.agronomo_id, *[c.vendedor_id for c in (*ventas, *suministros)]})
        if not Usuario.objects.filter(pk=actor.pk, is_active=True).exists():
            raise PermissionDenied(MENSAJE_SIN_ACCESO)  # quedó inactiva mientras esperaba
        activos = camara._bloquear_invernaderos(invernadero_id, [*ventas, *suministros], activo=False)
        list(Variedad.objects.select_for_update(no_key=True).filter(pk=previa.lote.siembra.variedad_id))
        stock_maduro.bloquear_candidatos([previa.lote.siembra.variedad_id], activos)
        camara._bloquear_filas(previa, ventas, suministros, detalles_de_venta, detalles_de_suministro)
        partida, cantidad, descripcion = _evaluar(actor, datos, bloqueado=True)  # 10d y todo lo demás, con lo bloqueado
        actual = camara._contratos_con_lineas(partida.pk)
        if not (actual[0] <= detalles_de_venta and actual[1] <= detalles_de_suministro):
            raise camara._ContratosNuevos()
        recorte = camara.recortar_partida(partida, partida.cantidad_disponible_cosechado - cantidad)  # 10c (vacío si la pérdida cabe en el stock libre)
        resultado = fisico.aplicar_merma_de_partida(partida, cantidad, datos.causa, descripcion, actor)  # f, g y h; primero lo físico, después se vuelve a cubrir
        recubierto = camara._recubrir(recorte.por_detalle, actor)
        agotada = partida.estado_stock_cosechado == StockCosechado.Estado.AGOTADO
        if agotada:
            camara.resolver_aviso_de_partida(partida)  # la alerta «partida por vencer»
        alerta = None
        if recorte.lineas:  # 10c.6: la alerta para el Agrónomo (regla 2 de 8.9) y el aviso al Vendedor de cada contrato afectado
            alerta = camara._avisar_merma_reservada(partida, resultado.merma, recubierto, recorte.por_detalle, "Merma en la partida")
        afectados = [partida, resultado.merma, resultado.movimiento, *[l for l, _ in recorte.lineas], *recorte.reservas_liberadas]
        afectados += [*recubierto.reservas, *recubierto.cosechas, *recubierto.detalles]
        if alerta is not None:
            afectados.append(alerta)
        recortes = _recortes_de(recorte.por_detalle)
        datos_de_auditoria = {"partida": referencia(partida), "plantas_perdidas": cantidad, "causa_merma": Merma.Causa(datos.causa).label}
        if recortes:
            datos_de_auditoria["lineas_recortadas"] = [f"{codigo}: {n}" for codigo, n in recortes]
            if recorte.reservas_liberadas:
                datos_de_auditoria["reservas_liberadas"] = [str(r) for r in recorte.reservas_liberadas]
        if recubierto.reservas:
            datos_de_auditoria["recubierto"] = [str(r) for r in recubierto.reservas]
        if recubierto.faltantes:
            datos_de_auditoria["sin_cubrir_tras_recorte"] = [f"{codigo}: {n}" for codigo, n in recubierto.faltantes]
        RegistroAuditoria.objects.registrar(
            usuario=actor, accion=RegistroAuditoria.Accion.REGISTRO_MERMA, afectados=afectados, detalle={"datos": datos_de_auditoria}
        )
        return ResultadoDeMermaEnCamara(partida, resultado.merma, resultado.movimiento, recortes, agotada)


def registrar_merma_en_camara(actor, datos):
    """PROD-REG-MRM sobre una partida en cámara (paso 10, 10c, 10d; postcondiciones f, g, h y j). Devuelve `ResultadoDeMermaEnCamara(partida, merma, movimiento, recortes, agotada)`.

    - Quién: el Capataz asignado o el Agrónomo a cargo del invernadero de la partida, con la cuenta activa (`PermissionDenied`).
    - Errores por campo (`ValidationError`): `partida_obligatoria`, `partida_no_disponible`, `cantidad_invalida`, `cambio_simultaneo` (10d), `causa_obligatoria`, `causa_invalida`
      y `descripcion_larga`. Todos se verifican de nuevo DESPUÉS de bloquear.
    - En UNA transacción: el recorte hasta que lo reservado iguale la disponible nueva (10c), la merma en cámara (`aplicar_merma_de_partida`), volver a cubrir lo recortado con el
      camino de faltante, resolver la alerta «partida por vencer» si la partida se agotó, la alerta de merma con producto reservado y el aviso a los Vendedores, y UN registro
      `registro_merma` (D-36). Sin asiento (D-57).
    """
    _evaluar(actor, datos)  # rechaza antes de bloquear lo que ya se ve mal (y `PermissionDenied`)
    for _ in range(2):
        previo = camara._contratos_con_lineas(_entero(datos.partida_id))
        try:
            return _registrar(actor, datos, previo)
        except camara._ContratosNuevos:
            continue
    raise ValidationError({"cantidad": [ValidationError("La partida cambió mientras se registraba. Volvé a intentar.", code="cambio_simultaneo")]})
