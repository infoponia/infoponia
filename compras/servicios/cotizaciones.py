# Servicios de la Cotización (CMP-02a): CMP-ENV-COT · Enviar Cotización, el portal del proveedor sin cuenta. Fuente: docs/casos_de_uso/compras/pedidos.md
# (CMP-ENV-COT v0.2 con las «Actualizaciones de A0»), D-88 (enlace y concurrencia) y D-89 (el proveedor carga el total o el unitario; se guarda el total).
#
# Bloqueos (D-88 punto 7, docs/patrones/enlace_del_proveedor.md sección 4 y docs/patrones/bloqueos.md, «compras»; siempre ``FOR NO KEY UPDATE``): el
# proveedor → el pedido → el enlace; se vuelve a verificar todo con las filas bloqueadas, se calcula «cubierto» ANTES y DESPUÉS con el pedido bloqueado
# (así el aviso sale una sola vez aunque dos proveedores envíen a la vez) y la única ``(pedido, proveedor)`` de ``Cotizacion`` respalda la extensión 11b.
# El acuse sale en ``on_commit``; el aviso de pedido cubierto es una notificación dentro de la transacción (D-42).

from collections import namedtuple
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import Http404
from django.utils import timezone

from compras import precios
from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, DetalleCotizacion, DetallePedido, EnlaceProveedor, Pedido, Proveedor
from compras.servicios import avisos, cobertura, enlaces
from core import notificaciones
from core.correo import correo_configurado, enviar_correo
from core.models import ROL_PROVEEDOR_ENLACE, RegistroAuditoria, referencia
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad, texto_precio
from inventario.unidades import Unidad, validar_cantidad
from maestros.servicios import configuracion

DOS_DECIMALES = Decimal("0.01")
LIMITE_DE_IMPORTE = Decimal(10) ** 12  # DecimalField(14, 2)
LIMITE_DE_CANTIDAD = Decimal(10) ** 11  # DecimalField(14, 3)
LIMITE_DEL_PLAZO = 2_147_483_647  # el de la columna entera de la base
LARGO_DE_OBSERVACIONES = Cotizacion._meta.get_field("observaciones_cotizacion").max_length

# Una línea ya validada: el detalle del pedido, la cantidad, el total (lo que se guarda), el unitario derivado (4 decimales) y el plazo.
LineaCotizada = namedtuple("LineaCotizada", "detalle cantidad total unitario plazo")
ResumenCotizacion = namedtuple("ResumenCotizacion", "lineas monto validez observaciones")
# Una línea de una cotización ya registrada, tal como se muestra al proveedor, en el acuse y en la ficha del pedido. ``unitario`` es ``None`` cuando el
# unitario mostrado (2 decimales) × la cantidad no da el total: entonces se muestra solo el total, que es el que manda (D-89 punto 7).
LineaParaMostrar = namedtuple("LineaParaMostrar", "insumo invernadero unidad_medida unidad cantidad unitario total plazo")


def proponer_validez(pedido):
    """Regla «Validez de la cotización»: la fecha límite del pedido + ``dias_validez_cotizacion`` de la configuración operativa (leído en cada uso)."""
    return pedido.fecha_limite_cotizaciones + timedelta(days=configuracion.obtener().dias_validez_cotizacion)


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _importe(valor):
    """Un importe en pesos con dos decimales y mayor que cero (reglas 6b), o ``None`` si no lo es. Acepta coma o punto; nunca ``float``."""
    if isinstance(valor, float) or isinstance(valor, bool):
        return None
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not numero.is_finite() or numero <= 0 or numero != numero.quantize(DOS_DECIMALES) or numero >= LIMITE_DE_IMPORTE:
        return None
    return numero.quantize(DOS_DECIMALES)


def _plazo(valor):
    """El plazo de entrega: un entero de 1 o más (6c con A0, P2), o ``None``."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and valor.strip().isascii() and valor.strip().isdigit():
        numero = int(valor.strip())
    else:
        return None
    return numero if 1 <= numero <= LIMITE_DEL_PLAZO else None


def _validar(pedido, detalles, lineas, validez, observaciones):
    """Todas las reglas de la cotización sobre un pedido ya leído, con TODOS los errores juntos en un ``ValidationError`` por campo. Devuelve
    ``(lineas_cotizadas, validez, observaciones)``."""
    errores = {}

    def agregar(campo, mensaje, codigo):
        errores.setdefault(campo, []).append(ValidationError(mensaje, code=codigo))

    lineas = list(lineas or [])
    if not lineas:
        agregar("lineas", "Cotice al menos un detalle.", "sin_lineas")
    resultado, vistos = [], set()
    for crudo_id, crudo_cantidad, total, unitario, plazo in lineas:
        try:
            detalle_id = int(crudo_id)
        except (TypeError, ValueError):
            detalle_id = None
        detalle = detalles.get(detalle_id)
        if detalle is None:
            agregar(f"detalle_{crudo_id}", "Ese detalle no es de este pedido.", "detalle_invalido")
            continue
        if detalle_id in vistos:
            agregar(f"detalle_{detalle_id}", "Ese detalle ya está en la cotización.", "detalle_repetido")
            continue
        vistos.add(detalle_id)
        unidad = detalle.insumo_invernadero.insumo.unidad_medida_insumo
        cantidad = None
        try:
            if isinstance(crudo_cantidad, float):
                raise ValidationError("Ingrese una cantidad válida.", code="cantidad_invalida")
            cantidad = validar_cantidad(crudo_cantidad, unidad)
            if cantidad <= 0 or cantidad >= LIMITE_DE_CANTIDAD:
                raise ValidationError("Ingrese una cantidad mayor que cero.", code="cantidad_invalida")
        except ValidationError as error:
            cantidad = None
            codigo = error.code if error.code in ("cantidad_invalida", "decimales_de_la_unidad") else "cantidad_invalida"
            agregar(f"cantidad_{detalle_id}", error.messages[0], codigo)
        # D-89 punto 2: se carga el total o el unitario, no los dos ni ninguno.
        campo_precio = f"precio_{detalle_id}"
        tiene_total, tiene_unitario = not _vacio(total), not _vacio(unitario)
        valor_total = None
        if tiene_total and tiene_unitario:
            agregar(campo_precio, "Cargue el total de la línea o el precio unitario, no los dos.", "precio_ambiguo")
        elif not tiene_total and not tiene_unitario:
            agregar(campo_precio, "Indique el precio.", "precio_invalido")
        else:
            cargado = _importe(total if tiene_total else unitario)
            if cargado is None:
                agregar(campo_precio, "Ingrese un precio mayor que cero, con hasta 2 decimales.", "precio_invalido")
            elif tiene_total:
                valor_total = cargado
            elif cantidad is not None:
                valor_total = precios.total_desde_unitario(cargado, cantidad)
                if valor_total <= 0 or valor_total >= LIMITE_DE_IMPORTE:
                    agregar(campo_precio, "Ingrese un precio mayor que cero, con hasta 2 decimales.", "precio_invalido")
                    valor_total = None
        dias = _plazo(plazo)
        if dias is None:
            agregar(f"plazo_{detalle_id}", "Indique el plazo en días, un número entero de 1 o más.", "plazo_invalido")
        if cantidad is not None and valor_total is not None and dias is not None:
            unitario_derivado = precios.precio_unitario(SimpleNamespace(cantidad_cotizada=cantidad, total_linea=valor_total))
            resultado.append(LineaCotizada(detalle, cantidad, valor_total, unitario_derivado, dias))

    limite = pedido.fecha_limite_cotizaciones
    if not isinstance(validez, date) or validez < limite:
        agregar("validez", f"Tiene que valer como mínimo hasta el {limite:%d/%m/%Y}, la fecha límite del pedido.", "validez_invalida")
    observaciones = (observaciones or "").strip()
    if len(observaciones) > LARGO_DE_OBSERVACIONES:
        agregar("observaciones", f"Las observaciones pasan de {LARGO_DE_OBSERVACIONES} caracteres.", "observaciones_largas")
    if errores:
        raise ValidationError(errores)
    return resultado, validez, observaciones


def _exigir_que_sirva(situacion):
    """Extensiones 2a, 2b y 11a: si el enlace no sirve para cotizar, el error con el motivo (``enlace_no_sirve``) o, si ya envió, ``ya_cotizo``."""
    if situacion == enlaces.SIRVE:
        return
    if situacion == enlaces.SOLO_LECTURA:
        raise ErrorDeCompras("ya_cotizo", "Ya envió su cotización para este pedido: no puede enviar otra.", datos={"situacion": situacion})
    raise ErrorDeCompras("enlace_no_sirve", "Este enlace ya no puede usarse.", datos={"situacion": situacion})


def _detalles_del_pedido(pedido):
    """``{id: DetallePedido}`` de los detalles del pedido, con su insumo e invernadero."""
    return {
        d.pk: d
        for d in DetallePedido.objects.filter(pedido=pedido).select_related(
            "insumo_invernadero__insumo", "insumo_invernadero__invernadero__direccion"
        )
    }


def resumir_cotizacion(enlace, lineas, validez, observaciones=""):
    """Pasos 8 y 9: valida la cotización (las mismas reglas que ``registrar_cotizacion``) y arma el resumen, sin escribir ni bloquear nada.

    ``lineas = [(detalle_pedido_id, cantidad, total | None, unitario | None, plazo)]``. ``enlace`` tiene que seguir sirviendo (``ErrorDeCompras``
    ``enlace_no_sirve`` o ``ya_cotizo``). Con errores en los datos, ``ValidationError`` por campo (``lineas``, ``detalle_<id>``, ``cantidad_<id>``,
    ``precio_<id>``, ``plazo_<id>``, ``validez``, ``observaciones``)."""
    actual = enlaces.enlace_por_id(enlace.pk)
    if actual is None:
        raise Http404("No existe ese enlace.")
    _exigir_que_sirva(enlaces.situacion_del_enlace(actual))
    pedido = actual.invitacion.pedido
    lineas_cotizadas, validez, observaciones = _validar(pedido, _detalles_del_pedido(pedido), lineas, validez, observaciones)
    monto = sum((l.total for l in lineas_cotizadas), Decimal("0.00"))
    return ResumenCotizacion(lineas_cotizadas, monto, validez, observaciones)


def lineas_para_mostrar(cotizacion):
    """Las líneas de ``cotizacion`` tal como se muestran (D-89 punto 7): el unitario con dos decimales, o ``None`` si no cierra con el total."""
    lineas = cotizacion.lineas.select_related(
        "detalle_pedido__insumo_invernadero__insumo", "detalle_pedido__insumo_invernadero__invernadero"
    ).order_by("detalle_pedido_id")
    resultado = []
    for linea in lineas:
        insumo = linea.detalle_pedido.insumo_invernadero.insumo
        invernadero = linea.detalle_pedido.insumo_invernadero.invernadero
        cierra = precios.unitario_cierra_con_el_total(linea)
        resultado.append(
            LineaParaMostrar(
                insumo.nombre_insumo,
                invernadero.nombre_invernadero,
                insumo.unidad_medida_insumo,
                Unidad(insumo.unidad_medida_insumo).label,
                linea.cantidad_cotizada,
                precios.precio_unitario_para_mostrar(linea) if cierra else None,
                linea.total_linea,
                linea.plazo_entrega_dias,
            )
        )
    return resultado


def cotizacion_del_enlace(enlace):
    """La cotización que envió el proveedor del ``enlace`` para su pedido (o ``None``), para mostrarla en solo lectura (extensión 2b)."""
    return Cotizacion.objects.filter(pedido=enlace.invitacion.pedido, proveedor=enlace.invitacion.proveedor).first()


def _texto_del_aviso(pedido, sumas):
    """El texto del aviso de pedido cubierto: pedido, fecha límite y líneas de cotización recibidas por detalle (``Lista de tecnología`` 11c)."""
    por_detalle = []
    for detalle in DetallePedido.objects.filter(pedido=pedido).select_related("insumo_invernadero__insumo", "insumo_invernadero__invernadero"):
        n = sumas.get(detalle.pk, 0)
        por_detalle.append(f"{detalle}: {n} {'línea' if n == 1 else 'líneas'}")
    texto = (
        f"Con las cotizaciones recibidas el pedido {pedido} quedó cubierto. Sigue en cotización hasta el "
        f"{pedido.fecha_limite_cotizaciones:%d/%m/%Y}. Líneas recibidas: " + "; ".join(por_detalle) + "."
    )
    return texto if len(texto) <= notificaciones.LARGO_DETALLE else texto[: notificaciones.LARGO_DETALLE - 1] + "…"


def _acuse(cotizacion_id):
    """El acuse de la cotización al proveedor (postcondición d y 12a). Fuera de la transacción; si falla, la cotización permanece."""
    if not correo_configurado():
        return
    cotizacion = Cotizacion.objects.select_related("proveedor", "pedido").get(pk=cotizacion_id)
    proveedor = cotizacion.proveedor
    enviar_correo(
        enlaces.Destinatario(proveedor.pk, proveedor.email_proveedor),
        f"Recibimos su cotización del pedido {cotizacion.pedido}",
        "compras/correo/acuse.txt",
        {
            "pedido": str(cotizacion.pedido),
            "proveedor": proveedor.nombre_para_mostrar,
            "enviada_el": timezone.localtime(cotizacion.enviada_el),
            "lineas": lineas_para_mostrar(cotizacion),
            "monto": cotizacion.monto_cotizacion,
            "validez": cotizacion.fecha_validez_cotizacion,
            "observaciones": cotizacion.observaciones_cotizacion,
        },
    )


def registrar_cotizacion(enlace_id, lineas, validez, observaciones=""):
    """CMP-ENV-COT paso 11: registra la cotización «propuesta» con sus líneas, deja el enlace ``usado``, audita ``alta_cotizacion`` con origen «proveedor
    mediante enlace» y, si con ella el pedido quedó cubierto por primera vez, avisa (una sola vez) a quien corresponde según H21. Devuelve la ``Cotizacion``.
    El acuse al proveedor sale en ``on_commit``.

    - Extensiones 2a, 11a y 11b: con el proveedor, el pedido y el enlace bloqueados y releídos se verifica que el enlace siga sirviendo (vigente, el
      pedido «en cotización», el proveedor activo y hoy ≤ la fecha límite) y que no exista ya una cotización del proveedor; si no, ``ErrorDeCompras``
      (``enlace_no_sirve`` con la ``situacion``, o ``ya_cotizo``) y no se registra nada. Un enlace inexistente es ``Http404``.
    - Reglas de las líneas: ``resumir_cotizacion``. No modifica el pedido, el stock ni la contabilidad."""
    leido = EnlaceProveedor.objects.select_related("invitacion").filter(pk=enlace_id).first()
    if leido is None:
        raise Http404("No existe ese enlace.")
    with transaction.atomic():
        proveedor = Proveedor.objects.select_for_update(no_key=True).get(pk=leido.invitacion.proveedor_id)
        pedido = Pedido.objects.select_for_update(no_key=True).get(pk=leido.invitacion.pedido_id)
        enlace = enlaces.bloquear_enlace(enlace_id)
        _exigir_que_sirva(enlaces.situacion_del_enlace(enlace))
        if Cotizacion.objects.filter(pedido=pedido, proveedor=proveedor).exists():
            raise ErrorDeCompras("ya_cotizo", "Ya envió su cotización para este pedido: no puede enviar otra.")
        detalles = _detalles_del_pedido(pedido)
        lineas_cotizadas, validez, observaciones = _validar(pedido, detalles, lineas, validez, observaciones)

        tolerancia = configuracion.obtener().porc_tolerancia_cobertura_pedido  # una sola lectura: antes y después con el mismo valor
        previas = list(Cotizacion.objects.filter(pedido=pedido))
        cubierto_antes = cobertura.esta_cubierto(cobertura.cobertura(pedido, previas, tolerancia=tolerancia))

        try:
            with transaction.atomic():  # respaldo de la 11b: la única ``(pedido, proveedor)``
                cotizacion = Cotizacion.objects.create(
                    pedido=pedido,
                    proveedor=proveedor,
                    fecha_cotizacion=stock.hoy(),
                    fecha_validez_cotizacion=validez,
                    observaciones_cotizacion=observaciones,
                )
        except IntegrityError as error:
            raise ErrorDeCompras("ya_cotizo", "Ya envió su cotización para este pedido: no puede enviar otra.") from error
        lineas_creadas = [
            DetalleCotizacion.objects.create(
                cotizacion=cotizacion,
                detalle_pedido=l.detalle,
                cantidad_cotizada=l.cantidad,
                total_linea=l.total,
                plazo_entrega_dias=l.plazo,
            )
            for l in lineas_cotizadas
        ]
        cubierto_despues = cobertura.esta_cubierto(cobertura.cobertura(pedido, previas + [cotizacion], tolerancia=tolerancia))

        enlace.estado = EnlaceProveedor.Estado.USADO
        enlace.fecha_uso = timezone.now()
        enlace.save(update_fields=["estado", "fecha_uso"])

        pasa_a_cubierto = cubierto_despues and not cubierto_antes
        monto = sum((l.total for l in lineas_cotizadas), Decimal("0.00"))
        cambios = {
            "estado": {"antes": None, "despues": cotizacion.estado_cotizacion},
            "fecha_validez_cotizacion": {"antes": None, "despues": validez.isoformat()},
            "monto_cotizacion": {"antes": None, "despues": texto_precio(monto)},
        }
        if observaciones:
            cambios["observaciones_cotizacion"] = {"antes": None, "despues": observaciones}
        RegistroAuditoria.objects.registrar(
            usuario=None,
            rol_externo=ROL_PROVEEDOR_ENLACE,
            accion=RegistroAuditoria.Accion.ALTA_COTIZACION,
            afectados=[proveedor, pedido, cotizacion, *lineas_creadas],
            detalle={
                "cambios": cambios,
                "datos": {
                    "proveedor": referencia(proveedor),
                    "pedido": referencia(pedido),
                    "lineas_cotizadas": [
                        f"{l.detalle}: {texto_cantidad(l.cantidad, l.detalle.insumo_invernadero.insumo.unidad_medida_insumo)} "
                        f"por {texto_precio(l.total)}, entrega en {l.plazo} {'día' if l.plazo == 1 else 'días'}"
                        for l in lineas_cotizadas
                    ],
                    "pedido_cubierto": pasa_a_cubierto,
                },
            },
        )
        if pasa_a_cubierto:  # 11c: una sola vez, con el pedido bloqueado (regla 14 de 8.16)
            sumas = dict(
                DetalleCotizacion.objects.filter(cotizacion__pedido=pedido).values_list("detalle_pedido_id").annotate(n=Count("id"))
            )
            destinos = {d.insumo_invernadero.invernadero_id for d in detalles.values()}
            notificaciones.notificar_a_varios(
                avisos.destinatarios_por_destino(destinos), f"Pedido {pedido} cubierto", _texto_del_aviso(pedido, sumas)
            )
        transaction.on_commit(lambda: _acuse(cotizacion.pk))
    return cotizacion
