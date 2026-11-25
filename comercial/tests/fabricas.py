# Fábricas compartidas por las pruebas de comercial/tests/: clientes, direcciones de clientes y vehículos creados directo en
# la base (sin pasar por los servicios), con datos válidos por defecto. Reutilizan las de core y maestros. Una sola firma
# por función.

import itertools
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from comercial.models import Cliente, DireccionCliente, Vehiculo
from produccion.models import StockCosechado
from produccion.tests.fabricas import Escenario

_secuencia = itertools.count(1)
# Los CUIT automáticos arrancan lejos de los que las pruebas escriben a mano (30000000090, 30712345671...).
_cuits = itertools.count(5_000_000)
_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_valido(numero=None):
    """Un CUIT de persona jurídica («30…») con dígito verificador correcto, sin guiones. ``numero`` (hasta 8 dígitos) lo hace
    reproducible; sin él, uno nuevo en cada llamada."""
    automatico = numero is None
    while True:
        numero = next(_cuits) if automatico else numero
        base = f"30{int(numero):08d}"
        resto = 11 - sum(p * int(d) for p, d in zip(_PESOS_CUIT, base)) % 11
        verificador = 0 if resto == 11 else resto
        if verificador != 10:  # con 10 no hay CUIT válido: se pasa al número siguiente
            return f"{base}{verificador}"
        if not automatico:
            numero += 1


def cliente(
    tipo="juridica",
    cuit=None,
    razon_social="Verdulería Los Pinos S.R.L.",
    nombre="Marta",
    apellido="Gómez",
    telefono="",
    email="",
    activo=True,
):
    """Un cliente creado directo. En una persona jurídica solo cuenta la razón social; en una física, el nombre y el apellido
    (la restricción de la base lo exige)."""
    juridica = tipo == Cliente.Tipo.JURIDICA
    return Cliente.objects.create(
        tipo_cliente=tipo,
        cuit_cliente=cuit or cuit_valido(),
        razon_social_cliente=razon_social if juridica else "",
        nombre_cliente="" if juridica else nombre,
        apellido_cliente="" if juridica else apellido,
        telefono_cliente=telefono,
        email_cliente=email,
        estado_cliente=Cliente.Estado.ACTIVO if activo else Cliente.Estado.INACTIVO,
    )


def direccion_de_cliente(cliente_, tipo="urbana", localidad_id=None, **extra):
    """Una dirección activa del cliente, creada con la API pública de direcciones de `maestros` (D-58) y su vínculo
    ``DireccionCliente``. ``extra`` pisa los datos de la dirección (``calle``, ``ruta``…)."""
    from maestros.servicios import direcciones
    from maestros.tests.fabricas import localidad

    datos = {"tipo_direccion": tipo, "localidad": localidad_id or localidad().pk}
    datos.update(
        {"calle": "San Martín", "numero_calle": "123"} if tipo == "urbana" else {"ruta": "Ruta 12", "kilometro": "1034"}
    )
    datos.update(extra)
    hija = direcciones.crear_direccion(direcciones.validar_direccion(datos))
    return DireccionCliente.objects.create(cliente=cliente_, direccion=hija.direccion_ptr)


def vehiculo(
    patente=None,
    tipo="camioneta",
    marca="Ford",
    modelo="Ranger",
    capacidad="800",
    activo=True,
    transportista=None,
    en_ruta_hoy=False,
):
    """Un vehículo creado directo. ``en_ruta_hoy`` lo deja con la ruta iniciada hoy (MD-118: en COM-01 nadie inicia una ruta,
    lo hace COM-06). Un vehículo inactivo no puede tener transportista (restricción de la base)."""
    return Vehiculo.objects.create(
        patente=patente or f"AB{next(_secuencia):03d}CD",
        tipo_vehiculo=tipo,
        marca=marca,
        modelo=modelo,
        capacidad_carga=capacidad,
        estado_vehiculo=Vehiculo.Estado.ACTIVO if activo else Vehiculo.Estado.INACTIVO,
        transportista=transportista,
        en_ruta=en_ruta_hoy,
        fecha_inicio_ruta=timezone.localdate() if en_ruta_hoy else None,
    )


CUIT_VALIDO = "30-71234567-1"  # el de los ejemplos de docs/api/direcciones.md


def datos_de_direccion(tipo="urbana", localidad_id=None, **extra):
    """Los datos de una dirección para ``DatosDeCliente`` (los nombres de ``docs/api/direcciones.md``). ``extra`` los pisa."""
    from maestros.tests.fabricas import localidad

    datos = {"tipo_direccion": tipo, "localidad": localidad_id or localidad().pk}
    datos.update({"calle": "San Martín", "numero_calle": "123"} if tipo == "urbana" else {"ruta": "Ruta 12", "kilometro": "1034"})
    datos.update(extra)
    return datos


def datos_de_cliente(**extra):
    """Un ``DatosDeCliente`` válido (persona jurídica con CUIT con guiones). ``extra`` pisa cualquier campo."""
    from comercial.servicios.clientes import DatosDeCliente

    campos = {"tipo_cliente": "juridica", "cuit": CUIT_VALIDO, "razon_social": "Verdulería Los Pinos S.R.L."}
    campos.update(extra)
    return DatosDeCliente(**campos)


def datos_de_cliente_de(cliente_, **extra):
    """Los datos guardados de ``cliente_`` como ``DatosDeCliente`` (sin direcciones), para modificarlo cambiando solo ``extra``."""
    from comercial.servicios.clientes import DatosDeCliente

    campos = {
        "tipo_cliente": cliente_.tipo_cliente,
        "cuit": cliente_.cuit_cliente,
        "razon_social": cliente_.razon_social_cliente,
        "nombre": cliente_.nombre_cliente,
        "apellido": cliente_.apellido_cliente,
        "telefono": cliente_.telefono_cliente,
        "email": cliente_.email_cliente,
    }
    campos.update(extra)
    return DatosDeCliente(**campos)


def datos_de_vehiculo(**extra):
    """Un ``DatosDeVehiculo`` válido (una camioneta de 800 kg sin transportista). ``extra`` pisa cualquier campo."""
    from comercial.servicios.vehiculos import DatosDeVehiculo

    campos = {"patente": "AE123CD", "tipo_vehiculo": "camioneta", "marca": "Ford", "modelo": "Ranger", "capacidad_carga": "800"}
    campos.update(extra)
    return DatosDeVehiculo(**campos)


def datos_de_vehiculo_de(vehiculo_, **extra):
    """Los datos guardados de ``vehiculo_`` como ``DatosDeVehiculo``, para modificarlo cambiando solo ``extra``."""
    from comercial.servicios.vehiculos import DatosDeVehiculo

    campos = {
        "patente": vehiculo_.patente,
        "tipo_vehiculo": vehiculo_.tipo_vehiculo,
        "marca": vehiculo_.marca,
        "modelo": vehiculo_.modelo,
        "capacidad_carga": str(vehiculo_.capacidad_carga),
        "transportista_id": vehiculo_.transportista_id,
    }
    campos.update(extra)
    return DatosDeVehiculo(**campos)


# ---- COM-02: contratos, reservas y stock maduro ----
# Armar un escenario comercial completo directo en la base (sin pasar por las pantallas): un invernadero con Agrónomo, Capataz y Vendedor,
# lotes en Maduración, partidas de cámara, un cliente con dirección, compra-ventas con detalles y reservas. Reutiliza las fábricas de
# `produccion` (`invernadero_con_produccion`, `lote_maduro`).


class EscenarioComercial(Escenario):
    """Un `Escenario` de `produccion` con su Vendedor, su cliente y la dirección de envío de ese cliente. `direccion` es la
    `maestros.Direccion` (no el vínculo)."""

    def __init__(self, escenario, vendedor, cliente_, vinculo):
        super().__init__(**{nombre: getattr(escenario, nombre) for nombre in vars(escenario)})
        self.vendedor = vendedor
        self.cliente = cliente_
        self.vinculo = vinculo
        self.direccion = vinculo.direccion if vinculo else None


def escenario_comercial(sufijo="", email_del_cliente="cliente@ejemplo.com", **opciones):
    """Un invernadero activo con su Agrónomo, su Capataz y su Vendedor (`vendedor{sufijo}@infoponia.com`), una variedad con ciclo completo
    y un cliente con una dirección activa. `opciones` va a `invernadero_con_produccion` (``geografia_propia=True`` para las de concurrencia: sin dirección del cliente)."""
    from maestros.models import Invernadero
    from maestros.tests.fabricas import crear_vendedor
    from produccion.tests.fabricas import invernadero_con_produccion

    opciones.setdefault("nombre", f"Invernadero Norte{sufijo}")
    base = invernadero_con_produccion(sufijo=sufijo, **opciones)
    vendedor = crear_vendedor(email=f"vendedor{sufijo}@infoponia.com")
    Invernadero.objects.filter(pk=base.invernadero.pk).update(vendedor=vendedor)
    base.invernadero.refresh_from_db()
    cliente_ = cliente(email=email_del_cliente)
    # Con `geografia_propia` (las pruebas de concurrencia, `TransactionTestCase`) no hay Georef: el cliente queda sin dirección (se retira).
    vinculo = None if opciones.get("geografia_propia") else direccion_de_cliente(cliente_)
    return EscenarioComercial(base, vendedor, cliente_, vinculo)


def segundo_invernadero(escenario, nombre="Invernadero Sur", con_capataz=True, activo=True, geografia_propia=False):
    """Otro invernadero del MISMO Vendedor, con la misma variedad y un sector por tipo de etapa. Con ``con_capataz=False`` queda sin
    Capataz (extensión 5a de PROD-ASG-STK). Devuelve un `Escenario` de `produccion` para usar con `lote_maduro`."""
    from maestros.tests.fabricas import crear_capataz_activo, crear_invernadero, crear_invernadero_con_geografia_propia, crear_sector
    from produccion.tests.fabricas import CODIGOS_DE_ETAPA, Escenario as EscenarioDeProduccion

    # El `Escenario` conserva siempre un Capataz (las siembras de los lotes lo exigen); con `con_capataz=False` el invernadero queda sin él.
    capataz = crear_capataz_activo(email=f"capataz.{nombre.lower().replace(' ', '')}@infoponia.com")
    crear = crear_invernadero_con_geografia_propia if geografia_propia else crear_invernadero
    inv = crear(
        nombre, activo=activo, agronomo=escenario.agronomo, capataz=capataz if con_capataz else None, vendedor=escenario.vendedor
    )
    sectores = {c: crear_sector(inv, nombre=f"Sector {c}", tipo=c, agujeros=100) for c in CODIGOS_DE_ETAPA}
    return EscenarioDeProduccion(
        inv, escenario.agronomo, capataz, sectores, escenario.variedad, escenario.semilla, escenario.existencia_semilla, None
    )


def compra_venta(
    escenario, *, dias=3, modalidad="envio", cliente_=None, vendedor=None, retiro=None, estado="abierta", direccion=None,
    comprobante="pendiente_envio",
):
    """Una `CompraVenta` abierta (o en el `estado` pedido) creada directo, sin detalles ni reservas. ``dias`` es cuántos días desde hoy
    es la fecha pactada. Con ``modalidad="retiro"`` hace falta ``retiro`` (un invernadero)."""
    from comercial.models import CompraVenta
    from comercial.servicios.compra_ventas import siguiente_numero

    cliente_ = cliente_ or escenario.cliente
    return CompraVenta.objects.create(
        tipo_contrato="compra_venta",
        numero=siguiente_numero(),
        cliente=cliente_,
        vendedor=vendedor or escenario.vendedor,
        estado_comprobante=comprobante,
        estado_venta=estado,
        fecha_pactada_venta=timezone.localdate() + timedelta(days=dias),
        modalidad_entrega=modalidad,
        direccion_envio=(direccion or escenario.direccion) if modalidad == "envio" else None,
        invernadero_retiro=(retiro or escenario.invernadero) if modalidad == "retiro" else None,
    )


def enlace(venta, *, estado="vigente", vence=None, estado_envio="enviado", cliente_=None):
    """Un `EnlaceCliente` de decisión de faltante de ``venta`` creado directo (sin correo ni `on_commit`), con su token. Devuelve ``(enlace, token)``: la base guarda solo el
    resumen. Por defecto vigente, vence dentro de 2 días (la vigencia de fábrica) y con el correo ya enviado; con ``estado="usado"`` guarda `fecha_uso` (restricción)."""
    from comercial.models import EnlaceCliente
    from core.enlaces import nuevo_token

    token, resumen = nuevo_token()
    return (
        EnlaceCliente.objects.create(
            tipo=EnlaceCliente.Tipo.DECISION_FALTANTE,
            cliente=cliente_ or venta.cliente,
            compra_venta=venta,
            token_resumen=resumen,
            fecha_vencimiento=vence or timezone.localdate() + timedelta(days=2),
            estado=estado,
            fecha_uso=timezone.now() if estado == "usado" else None,
            estado_envio=estado_envio,
        ),
        token,
    )


def detalle(venta, variedad, cantidad=10, precio="100.00", estado="abierto"):
    """Un `DetalleVenta` de ``venta`` (sin reservas)."""
    from comercial.models import DetalleVenta

    return DetalleVenta.objects.create(
        compra_venta=venta,
        variedad=variedad,
        cant_solicitada_venta=cantidad,
        precio_unitario_de_venta=Decimal(precio),
        estado_detalle_venta=estado,
    )


def partida_cosechada(lote_, disponible=10, fecha_limite=None, estado="disponible", costo="1.0000", *, origen=None, motivo="excedente_de_cosecha"):
    """Una partida de cámara (`StockCosechado`) del ``lote_`` con ``disponible`` plantas, su fecha límite (por defecto, dentro de 30 días) y su
    movimiento `ingreso_a_camara` (invariante de COM-04a: toda partida nace con el suyo), escrita directo en la base. ``origen`` es el
    documento que la origina (por defecto, una orden suelta de cosecha del invernadero del lote)."""
    from produccion.models import MovimientoStock
    from produccion.tests.fabricas import orden_suelta

    hoy = timezone.localdate()
    nueva = StockCosechado.objects.create(
        lote=lote_,
        cantidad_ingreso_cosechado=max(1, disponible),
        cantidad_disponible_cosechado=disponible,
        fecha_ingreso=hoy,
        fecha_limite=fecha_limite or hoy + timedelta(days=30),
        motivo_cosechado=motivo,
        estado_stock_cosechado=estado if disponible else "agotado",
        costo_unitario_cosechado=Decimal(costo),
    )
    MovimientoStock.objects.create(
        origen_id=(origen or orden_suelta(lote_.invernadero, "cosecha", estado="concretada")).pk,
        partida=nueva,
        tipo_movimiento="ingreso_a_camara",
        cantidad=max(1, disponible),
        costo_unitario=Decimal(costo),
    )
    return nueva


def partida(lote_, disponible=10, fecha_limite=None, estado="disponible", costo="1.0000"):
    """Una partida de cámara (`StockCosechado`) del ``lote_`` (COM-02): ver `partida_cosechada`, que desde COM-04a también crea su movimiento."""
    return partida_cosechada(lote_, disponible, fecha_limite, estado, costo)


def cosecha_manual(escenario, lineas, *, detalle_=None, periodo_=None, dias=0, prioridad="media", descripcion="", origen="manual", fecha_entrega=None):
    """Una `Cosecha` «a realizar» de origen ``origen`` (por defecto `manual`, la que planifica el Agrónomo) con su reserva «activa» y una línea por
    cada ``(lote, cantidad)`` de ``lineas``, escrita directo en la base (sin pasar por `planificar_cosecha`). Con ``detalle_`` (un `DetalleVenta`)
    o ``periodo_`` (un `Periodo`) cubre ese contrato, con su fecha de entrega; sin ninguno, es una cosecha sin contrato (reserva sin detalle ni fecha)."""
    from comercial.models import DetalleReserva, ReservaStock
    from produccion.models import Cosecha
    from produccion.servicios import ordenes

    hoy = timezone.localdate()
    lote_ = lineas[0][0]
    entrega = fecha_entrega
    if detalle_ is not None:
        entrega = entrega or detalle_.compra_venta.fecha_pactada_venta
    if periodo_ is not None:
        entrega = entrega or periodo_.fecha
    cosecha_ = Cosecha.objects.create(
        tipo_orden="cosecha",
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=min(hoy, hoy + timedelta(days=dias)),
        fecha_programada_orden=hoy + timedelta(days=dias),
        prioridad_orden=prioridad,
        descripcion_orden=descripcion,
        agronomo=escenario.agronomo if origen == "manual" else None,
        invernadero=lote_.invernadero,
        capataz=lote_.invernadero.capataz,
        variedad=lote_.siembra.variedad,
        origen_cosecha=origen,
    )
    reserva_ = ReservaStock.objects.create(
        detalle_venta=detalle_,
        detalle_suministro=periodo_.detalle if periodo_ is not None else None,
        invernadero=lote_.invernadero,
        fecha_entrega_reserva=entrega if (detalle_ is not None or periodo_ is not None) else None,
        estado_reserva="activa",
        cosecha=cosecha_,
    )
    for lote_de_la_linea, cantidad in lineas:
        DetalleReserva.objects.create(reserva=reserva_, lote=lote_de_la_linea, cantidad_reservada=cantidad)
    return cosecha_


def reserva(detalle_, lineas, estado=None, fecha_entrega=None, con_cosecha=True, detalle_suministro=None):
    """Una `ReservaStock` del ``detalle_`` con una línea por cada ``(lote_o_partida, cantidad)`` de ``lineas``. El invernadero es el del
    primer origen. Con algún lote y ``con_cosecha``, crea también su `Cosecha` «a realizar». El estado, si no se pide: «activa» con
    algún lote y «lista para entrega» si todo es de cámara (regla 12 de 8.6)."""
    from comercial.models import DetalleReserva, ReservaStock
    from produccion.models import Cosecha, Lote
    from produccion.servicios import ordenes

    hoy = timezone.localdate()
    hay_lote = any(isinstance(origen, Lote) for origen, _ in lineas)
    invernadero = (lineas[0][0].invernadero if isinstance(lineas[0][0], Lote) else lineas[0][0].lote.invernadero)
    cosecha_ = None
    if hay_lote and con_cosecha:
        lote_ = next(origen for origen, _ in lineas if isinstance(origen, Lote))
        cosecha_ = Cosecha.objects.create(
            tipo_orden="cosecha",
            numero=ordenes.siguiente_numero(),
            fecha_programada_orden=hoy,
            prioridad_orden="media",
            invernadero=invernadero,
            capataz=invernadero.capataz,
            variedad=lote_.siembra.variedad,
        )
    reserva_ = ReservaStock.objects.create(
        detalle_venta=detalle_,
        detalle_suministro=detalle_suministro,
        invernadero=invernadero,
        fecha_entrega_reserva=fecha_entrega or detalle_.compra_venta.fecha_pactada_venta,
        estado_reserva=estado or ("activa" if hay_lote else "lista_para_entrega"),
        cosecha=cosecha_,
    )
    for origen, cantidad in lineas:
        DetalleReserva.objects.create(
            reserva=reserva_,
            cantidad_reservada=cantidad,
            **({"lote": origen} if isinstance(origen, Lote) else {"partida": origen}),
        )
    return reserva_


def verificar_invariantes_de_reservas():
    """Invariantes de `docs/patrones/stock_maduro.md`, sección 6: se llama al final de cada prueba que escribe reservas (y de las de
    concurrencia). Lanza `AssertionError` con lo que encuentra: (1) ningún lote ni partida con stock libre negativo; (2) ninguna reserva
    con líneas de dos invernaderos; (3) ninguna cosecha sin reserva ni de dos variedades; (4) ningún detalle con más cubierto que lo pedido."""
    from django.db.models import Count, F, Sum

    from comercial.models import DetalleReserva, DetalleVenta, ReservaStock
    from comercial.servicios import stock_maduro
    from produccion.models import Bitacora, Cosecha, Lote, MovimientoStock

    problemas = []
    # 1. Stock libre nunca negativo.
    for lote_ in Lote.objects.all():
        reservado = stock_maduro.reservado_de_lotes([lote_.pk]).get(lote_.pk, 0)
        if reservado > lote_.cantidad_actual:
            problemas.append(f"{lote_.codigo}: reservado {reservado} > cantidad actual {lote_.cantidad_actual}")
    for p in StockCosechado.objects.all():
        reservado = (
            DetalleReserva.objects.filter(partida=p, reserva__estado_reserva__in=["activa", "lista_para_entrega"]).aggregate(t=Sum("cantidad_reservada"))["t"]
            or 0
        )
        if reservado > p.cantidad_disponible_cosechado:
            problemas.append(f"{p}: reservado {reservado} > disponible {p.cantidad_disponible_cosechado}")
    # 2. Todas las líneas de una reserva son de su invernadero.
    for linea in DetalleReserva.objects.select_related("reserva", "lote", "partida__lote"):
        inv = linea.lote.invernadero_id if linea.lote_id else linea.partida.lote.invernadero_id
        if inv != linea.reserva.invernadero_id:
            problemas.append(f"Reserva #{linea.reserva_id}: línea #{linea.pk} de otro invernadero")
    # 3. Toda cosecha tiene su reserva y una sola variedad.
    for c in Cosecha.objects.all():
        reserva_ = ReservaStock.objects.filter(cosecha=c).first()
        if reserva_ is None:
            problemas.append(f"{c.codigo}: cosecha sin reserva")
            continue
        variedades = set(reserva_.lineas.filter(lote__isnull=False).values_list("lote__siembra__variedad_id", flat=True))
        if variedades - {c.variedad_id}:
            problemas.append(f"{c.codigo}: cosecha con lotes de otra variedad")
    # 4. Ningún detalle con más cubierto que lo pedido.
    for d in DetalleVenta.objects.all():
        # Regla 9 de 8.8 (COM-04a): una línea de lote ya cosechada cubre `min(cosechada, reservada)`.
        cubierto = sum(
            min(c, r) if lote_id and c is not None else r
            for r, c, lote_id in DetalleReserva.objects.filter(reserva__detalle_venta=d)
            .exclude(reserva__estado_reserva="liberada")
            .values_list("cantidad_reservada", "cantidad_cosechada", "lote_id")
        )
        if cubierto > d.cant_solicitada_venta:
            problemas.append(f"{d}: cubierto {cubierto} > solicitado {d.cant_solicitada_venta}")
    # COM-04a (sección 8 de `docs/patrones/stock_maduro.md`):
    # 5. Ninguna reserva sin detalle que no sea de una cosecha `manual`; ninguna con detalle y sin fecha de entrega, ni al revés.
    for r in ReservaStock.objects.filter(detalle_venta__isnull=True, detalle_suministro__isnull=True).select_related("cosecha"):
        if r.cosecha is None or r.cosecha.origen_cosecha != "manual":
            problemas.append(f"Reserva #{r.pk}: sin contrato y sin ser de una cosecha manual")
        if r.fecha_entrega_reserva is not None:
            problemas.append(f"Reserva #{r.pk}: sin contrato y con fecha de entrega")
    for r in ReservaStock.objects.exclude(detalle_venta__isnull=True, detalle_suministro__isnull=True).filter(fecha_entrega_reserva__isnull=True):
        problemas.append(f"Reserva #{r.pk}: con contrato y sin fecha de entrega")
    # 6. Toda partida tiene su movimiento «ingreso a cámara».
    for p in StockCosechado.objects.all():
        if not MovimientoStock.objects.filter(partida=p, tipo_movimiento="ingreso_a_camara").exists():
            problemas.append(f"{p}: partida sin su ingreso a cámara")
    # 7. Toda cosecha concretada tiene un registro de bitácora por lote y sus líneas de lote con la cantidad cosechada.
    for c in Cosecha.objects.filter(estado_orden="concretada"):
        reserva_ = ReservaStock.objects.filter(cosecha=c).first()
        if reserva_ is None:
            continue
        for linea in reserva_.lineas.filter(lote__isnull=False):
            if linea.cantidad_cosechada is None:
                problemas.append(f"{c.codigo}: línea #{linea.pk} concretada sin cantidad cosechada")
            if not Bitacora.objects.filter(cosecha=c, lote_id=linea.lote_id, tipo_evento="cosecha").exists():
                problemas.append(f"{c.codigo}: sin registro de bitácora del lote {linea.lote_id}")
    # 8. Ninguna reserva «lista para entrega» con una línea de lote sin cosechar.
    for linea in DetalleReserva.objects.filter(reserva__estado_reserva="lista_para_entrega", lote__isnull=False, cantidad_cosechada__isnull=True):
        problemas.append(f"Reserva #{linea.reserva_id}: «lista para entrega» con la línea #{linea.pk} sin cosechar")
    # COM-05b (COM-CNL-CVT, paso 6): ninguna reserva de un detalle «cancelado» queda sin liberar.
    for r in ReservaStock.objects.filter(detalle_venta__estado_detalle_venta="cancelado").exclude(estado_reserva="liberada"):
        problemas.append(f"Reserva #{r.pk}: sin liberar y de un detalle cancelado")
    if problemas:
        raise AssertionError("Invariantes de reservas rotos: " + "; ".join(problemas))
    verificar_invariantes_de_suministros()


# ---- COM-03a: suministros, detalles y períodos ----


def _sumar_meses(fecha, n):
    """El mismo día del mes, ``n`` meses después (el último del mes si no existe). Copia mínima para armar ``fecha_fin`` sin depender del
    servicio que se prueba (``calendario.sumar_meses``)."""
    import calendar

    mes = fecha.month - 1 + n
    anio, mes = fecha.year + mes // 12, mes % 12 + 1
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, calendar.monthrange(anio, mes)[1]))


def suministro(
    escenario, *, cliente_=None, vendedor=None, duracion=6, tolerados=3, incumplimientos=0, multa="50000.00", plazo_pago=15,
    indemnizacion_pago="100.00", estado="vigente", comprobante="pendiente_envio", fecha_realizacion=None, con_clausula=True,
):
    """Un `Suministro` «vigente» (o en el `estado` pedido) con su cláusula del suministrado, creado directo, sin detalles. ``estado`` distinto
    de «vigente» solo vale para «finalizado»: «resuelto» y «rescindido» exigen sus fechas y las pone cada prueba con `update`."""
    from django.db import connection

    from comercial.models import ClausulaSuministrado, Suministro

    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_suministro_numero_seq')")
        numero = cursor.fetchone()[0]
    realizacion = fecha_realizacion or timezone.localdate()
    contrato = Suministro.objects.create(
        tipo_contrato="suministro",
        numero=numero,
        cliente=cliente_ or escenario.cliente,
        vendedor=vendedor or escenario.vendedor,
        estado_comprobante=comprobante,
        fecha_realizacion=realizacion,
        duracion_meses=duracion,
        estado_suministro=estado,
        fecha_fin=_sumar_meses(realizacion, duracion),
        incumplimientos_tolerados=tolerados,
        cantidad_incumplimientos=incumplimientos,
        multa_resolucion=Decimal(multa),
    )
    if con_clausula:
        ClausulaSuministrado.objects.create(
            suministro=contrato, plazo_pago_dias=plazo_pago, indemnizacion_retraso_pago=Decimal(indemnizacion_pago)
        )
    return contrato


def detalle_suministro(
    suministro_, variedad, *, direccion=None, cantidad=10, periodo=7, primera_en_dias=3, mecanismo="fijo", precio="100.00", porcentaje=None,
    meses=None, estado="vigente", fecha_fin_detalle=None, reemplaza_a=None, fecha_base_ajuste=None, minima=1, plazo_entrega=0,
    indemnizacion_retraso="10.00", indemnizacion_faltante="5.00",
):
    """Un `DetalleSuministro` de ``suministro_`` con su cláusula del suministrante, sin reservas. ``primera_en_dias`` es cuántos días desde
    hoy cae la primera entrega. Con ``mecanismo="ajuste_periodico"`` hacen falta ``porcentaje`` y ``meses``. La dirección por defecto es la
    del cliente del contrato (hace falta que la tenga)."""
    from comercial.models import ClausulaSuministrante, DetalleSuministro, DireccionCliente

    if direccion is None:
        direccion = DireccionCliente.objects.filter(cliente=suministro_.cliente).order_by("pk").first().direccion
    detalle_ = DetalleSuministro.objects.create(
        suministro=suministro_,
        direccion=direccion,
        variedad=variedad,
        periodo_entrega_dias=periodo,
        fecha_primer_entrega=timezone.localdate() + timedelta(days=primera_en_dias),
        cantidad_por_periodo=cantidad,
        mecanismo_precio=mecanismo,
        estado_detalle_suministro=estado,
        precio_unitario_suministro=Decimal(precio),
        porcentaje_ajuste=Decimal(porcentaje) if porcentaje is not None else None,
        meses_ajuste=meses,
        fecha_fin_detalle=fecha_fin_detalle,
        fecha_base_ajuste=fecha_base_ajuste or suministro_.fecha_realizacion,
        reemplaza_a=reemplaza_a,
    )
    ClausulaSuministrante.objects.create(
        detalle=detalle_,
        plazo_entrega_dias=plazo_entrega,
        indemnizacion_retraso_entrega=Decimal(indemnizacion_retraso),
        cantidad_minima=minima,
        indemnizacion_faltante=Decimal(indemnizacion_faltante),
    )
    return detalle_


def periodo(detalle_, fecha):
    """Un `Periodo` (detalle, fecha) de ``detalle_`` (sección 7 de `docs/patrones/stock_maduro.md`)."""
    from comercial.servicios.stock_maduro import Periodo

    return Periodo(detalle_, fecha)


def reserva_de_periodo(detalle_, fecha, lineas, estado=None, con_cosecha=True):
    """Una `ReservaStock` del período (``detalle_``, ``fecha``) con una línea por cada ``(lote_o_partida, cantidad)``; igual que `reserva`,
    pero para un detalle de suministro."""
    return reserva(None, lineas, estado=estado, fecha_entrega=fecha, con_cosecha=con_cosecha, detalle_suministro=detalle_)


def alerta_de_periodo(detalle_, fecha, *, cantidad_sin_cubrir=5, invernadero=None, resuelta=False, para_gerente=False, agronomo=None):
    """Una alerta «período sin cobertura completa» del período (``detalle_``, ``fecha``) con su `AlertaComercial`, creada directo en la base (D-63,
    punto 3): clave ``periodo:{detalle}:{aaaa-mm-dd}``, la del invernadero pedido (por defecto el de la primera reserva del escenario no se
    conoce acá: se pasa ``invernadero``). ``resuelta=True`` la deja resuelta con su fecha."""
    from comercial.models import AlertaComercial
    from maestros.tests.fabricas import crear_alerta

    alerta = crear_alerta(
        invernadero,
        "comercial_periodo_sin_cobertura",
        para_gerente=para_gerente or agronomo is None,
        agronomo=agronomo,
        resuelta=resuelta,
        clave_estado=f"periodo:{detalle_.pk}:{fecha.isoformat()}",
        descripcion_alerta=f"Período sin cobertura completa · {detalle_.variedad} · {detalle_.suministro.cliente} · {fecha:%d/%m}",
    )
    AlertaComercial.objects.create(alerta=alerta, detalle_suministro=detalle_, fecha_periodo=fecha, cantidad_sin_cubrir=cantidad_sin_cubrir)
    return alerta


def verificar_invariantes_de_suministros():
    """Invariantes de la sección 7 de `docs/patrones/stock_maduro.md` (COM-03a): ningún período con más cubierto que su cantidad; ninguna
    reserva de un período fuera del calendario de su detalle; ninguna reserva con los dos detalles a la vez; ``fecha_fin`` de cada
    suministro igual a ``sumar_meses(fecha_realizacion, duracion)``; un detalle finalizado tiene ``fecha_fin_detalle`` y uno vigente la
    tiene solo si su suministro tiene una rescisión acordada. (El de la rescisión lo suma COM-03b.) Lanza `AssertionError`."""
    from django.db.models import Sum

    from comercial.models import DetalleReserva, DetalleSuministro, ReservaStock, Suministro
    problemas = []
    for r in ReservaStock.objects.filter(detalle_venta__isnull=False, detalle_suministro__isnull=False):
        problemas.append(f"Reserva #{r.pk}: con detalle de venta y de suministro a la vez")
    totales = {}
    for detalle_id, fecha_, r, c, lote_id in (
        DetalleReserva.objects.filter(reserva__detalle_suministro__isnull=False)
        .exclude(reserva__estado_reserva="liberada")
        .values_list("reserva__detalle_suministro_id", "reserva__fecha_entrega_reserva", "cantidad_reservada", "cantidad_cosechada", "lote_id")
    ):
        clave = (detalle_id, fecha_)
        totales[clave] = totales.get(clave, 0) + (min(c, r) if lote_id and c is not None else r)  # COM-04a: regla 9 de 8.8
    cubierto = [{"reserva__detalle_suministro_id": d_, "reserva__fecha_entrega_reserva": f_, "total": t} for (d_, f_), t in totales.items()]
    detalles = {d.pk: d for d in DetalleSuministro.objects.select_related("suministro")}
    if detalles:
        from comercial.servicios import calendario
    for fila in cubierto:
        d = detalles[fila["reserva__detalle_suministro_id"]]
        fecha = fila["reserva__fecha_entrega_reserva"]
        if fila["total"] > d.cantidad_por_periodo:
            problemas.append(f"{d}: período {fecha} con {fila['total']} cubiertas > {d.cantidad_por_periodo}")
        if fecha not in set(calendario.calendario(d)):
            problemas.append(f"{d}: reserva del {fecha}, que no es un período de su calendario")
    for s in Suministro.objects.all():
        from comercial.servicios import calendario

        if s.fecha_fin != calendario.sumar_meses(s.fecha_realizacion, s.duracion_meses):
            problemas.append(f"{s.codigo}: fecha de fin {s.fecha_fin} no coincide con su duración")
    for d in detalles.values():
        if d.estado_detalle_suministro == "finalizado" and d.fecha_fin_detalle is None:
            problemas.append(f"{d}: finalizado sin fecha de fin del detalle")
        if d.estado_detalle_suministro == "vigente" and d.fecha_fin_detalle is not None and not d.suministro.tiene_rescision_acordada:
            problemas.append(f"{d}: vigente con fecha de fin del detalle y sin rescisión acordada")
    if problemas:
        raise AssertionError("Invariantes de suministros rotos: " + "; ".join(problemas))


# ---- COM-05a1: entregas ----


def reserva_lista(detalle_, lote_, cantidad, *, fecha_entrega=None, detalle_suministro=None):
    """Una `ReservaStock` «lista para entrega» de ``cantidad`` plantas de una partida nueva de ``lote_`` (sin cosecha): lo que deja el stock de cámara. Para un período,
    ``detalle_`` es ``None`` y se pasa ``detalle_suministro`` con ``fecha_entrega``."""
    partida_ = partida_cosechada(lote_, cantidad)
    return reserva(detalle_, [(partida_, cantidad)], fecha_entrega=fecha_entrega, detalle_suministro=detalle_suministro)


def transportista_con_vehiculo(invernadero, capacidad="800", *, email=None, en_ruta=False, tipo="camioneta", activo=True, con_vehiculo=True):
    """Un Transportista del ``invernadero`` (`TransportistaInvernadero`) con un vehículo activo de ``capacidad`` kg (``en_ruta=True`` lo deja con la ruta iniciada hoy;
    ``con_vehiculo=False``, sin vehículo; ``activo=False``, con la cuenta inactiva). Devuelve el `Transportista`; el vehículo es ``transportista.vehiculo``."""
    from maestros.tests.fabricas import asignar_transportista, crear_transportista

    numero = next(_secuencia)
    transportista = crear_transportista(email=email or f"transportista{numero}@infoponia.com", nombre=f"Trans{numero}", apellido="Porte", activo=activo)
    asignar_transportista(transportista, invernadero)
    if con_vehiculo:
        vehiculo(capacidad=capacidad, transportista=transportista, en_ruta_hoy=en_ruta, tipo=tipo)
    return transportista


def entrega(contrato, reservas, *, fecha=None, transportista=None, estado="a_realizar", direccion=None, precio=None, aviso=None):
    """Una `Entrega` de ``contrato`` (una `CompraVenta` o un `Suministro`) creada directo, sin avisos ni alertas, con una línea por detalle de venta (o por período) de
    ``reservas`` y esas reservas asociadas (R150). El invernadero es el de las reservas. ``fecha`` es la programada (por defecto, la prometida; una pasada baja
    ``fecha_creacion_orden`` para cumplir la restricción de la orden). ``estado`` puede ser «concretada» o «cancelada». Escribe los datos copiados igual que
    `entregas._crear_entrega` (D-66 punto 3)."""
    from comercial.models import DetalleEntrega, Entrega
    from comercial.servicios import calendario
    from produccion.servicios import ordenes

    hoy = timezone.localdate()
    reservas = list(reservas)
    es_venta = contrato.tipo_contrato == "compra_venta"
    prometida = contrato.fecha_pactada_venta if es_venta else reservas[0].fecha_entrega_reserva
    fecha = fecha or max(prometida, hoy)
    if es_venta:
        modalidad = contrato.modalidad_entrega
        destino = contrato.direccion_envio if modalidad == "envio" else None
    else:
        modalidad = "envio"
        destino = direccion or reservas[0].detalle_suministro.direccion
    extra = {}
    if estado != "a_realizar":
        extra["fecha_resolucion_orden"] = hoy
    if estado == "cancelada":
        extra["motivo_cancelacion"] = "Motivo de prueba"
    nueva = Entrega.objects.create(
        tipo_orden="entrega",
        numero=ordenes.siguiente_numero(),
        fecha_creacion_orden=min(hoy, fecha),
        fecha_programada_orden=fecha,
        estado_orden=estado,
        invernadero=reservas[0].invernadero,
        contrato_entrega_id=contrato.pk,
        modalidad_entrega=modalidad,
        direccion_destino=destino,
        transportista=transportista,
        estado_confirmacion_cliente=None if es_venta else "no_confirmado",
        estado_aviso_cliente=aviso,
        **extra,
    )
    grupos = {}
    for r in reservas:
        clave = ("v", r.detalle_venta_id) if r.detalle_venta_id else ("s", r.detalle_suministro_id, r.fecha_entrega_reserva)
        grupos.setdefault(clave, []).append(r)
    for clave, rs in grupos.items():
        if clave[0] == "v":
            detalle_venta_ = rs[0].detalle_venta
            linea = DetalleEntrega.objects.create(entrega=nueva, detalle_venta=detalle_venta_, precio_unitario=precio or detalle_venta_.precio_unitario_de_venta)
        else:
            detalle_ = rs[0].detalle_suministro
            linea = DetalleEntrega.objects.create(
                entrega=nueva, detalle_suministro=detalle_, fecha_periodo=clave[2], precio_unitario=precio or calendario.precio_en(detalle_, fecha)
            )
        linea.reservas.set(rs)
    return nueva


def verificar_invariantes_de_entregas():
    """Invariantes de `docs/modelo/comercial.md`, «Entrega» y «DetalleEntrega» (COM-05a1), los que la base no puede vigilar: se llama al final de cada prueba que
    crea entregas. Verifica que (1) el contrato, la modalidad y el destino de cada entrega coinciden con los de sus líneas; (2) la confirmación del cliente es no nula
    si y solo si el contrato es un suministro; (3) todas las reservas de sus líneas son del invernadero de origen; (4) cada línea tiene al menos una reserva, del mismo
    detalle y, en un suministro, de la fecha de su período; (5) una reserva tiene a lo sumo una línea en una entrega no cancelada (regla 4 de 8.8); (6) la entrega no
    tiene Agrónomo planificador. Lanza `AssertionError` con lo que encuentra."""
    from collections import defaultdict

    from comercial.models import CompraVenta, DetalleEntrega, Entrega

    problemas = []
    for e in Entrega.objects.select_related("contrato_entrega").order_by("pk"):
        venta = CompraVenta.objects.filter(pk=e.contrato_entrega_id).first()
        es_suministro = venta is None
        if e.agronomo_id is not None:
            problemas.append(f"{e.codigo}: con Agrónomo planificador")
        if (e.estado_confirmacion_cliente is not None) != es_suministro:
            problemas.append(f"{e.codigo}: confirmación del cliente {e.estado_confirmacion_cliente!r} con un contrato de {'suministro' if es_suministro else 'compra-venta'}")
        if venta is not None:
            if e.modalidad_entrega != venta.modalidad_entrega:
                problemas.append(f"{e.codigo}: modalidad distinta de la de {venta.codigo}")
            if e.modalidad_entrega == "envio" and e.direccion_destino_id != venta.direccion_envio_id:
                problemas.append(f"{e.codigo}: destino distinto de la dirección de envío de {venta.codigo}")
            if e.modalidad_entrega == "retiro" and e.invernadero_id != venta.invernadero_retiro_id:
                problemas.append(f"{e.codigo}: retiro en un invernadero que no es el de {venta.codigo}")
        elif e.modalidad_entrega != "envio":
            problemas.append(f"{e.codigo}: un suministro siempre es con envío")
        for linea in e.lineas.select_related("detalle_venta", "detalle_suministro").order_by("pk"):
            if linea.detalle_venta_id:
                if linea.detalle_venta.compra_venta_id != e.contrato_entrega_id:
                    problemas.append(f"{e.codigo}: línea #{linea.pk} de otro contrato")
            else:
                if linea.detalle_suministro.suministro_id != e.contrato_entrega_id:
                    problemas.append(f"{e.codigo}: línea #{linea.pk} de otro contrato")
                if linea.detalle_suministro.direccion_id != e.direccion_destino_id:
                    problemas.append(f"{e.codigo}: línea #{linea.pk} con otra dirección de destino")
            reservas = list(linea.reservas.all())
            if not reservas:
                problemas.append(f"{e.codigo}: línea #{linea.pk} sin reservas")
            for r in reservas:
                if r.invernadero_id != e.invernadero_id:
                    problemas.append(f"{e.codigo}: línea #{linea.pk} con la reserva #{r.pk} de otro invernadero")
                if linea.detalle_venta_id and r.detalle_venta_id != linea.detalle_venta_id:
                    problemas.append(f"{e.codigo}: línea #{linea.pk} con la reserva #{r.pk} de otro detalle")
                if linea.detalle_suministro_id and (r.detalle_suministro_id != linea.detalle_suministro_id or r.fecha_entrega_reserva != linea.fecha_periodo):
                    problemas.append(f"{e.codigo}: línea #{linea.pk} con la reserva #{r.pk} de otro detalle o de otro período")
    # COM-05b (COM-CNL-CVT, paso 6): ninguna entrega «a realizar» de una venta cancelada.
    for e in Entrega.objects.filter(estado_orden="a_realizar", contrato_entrega__in=CompraVenta.objects.filter(estado_venta="cancelada").values("pk")):
        problemas.append(f"{e.codigo}: «a realizar» y de una venta cancelada")
    vivas = defaultdict(list)
    for entrega_id, reserva_id in DetalleEntrega.objects.exclude(entrega__estado_orden="cancelada").values_list("entrega_id", "reservas"):
        if reserva_id is not None:
            vivas[reserva_id].append(entrega_id)
    for reserva_id, entregas_ in vivas.items():
        if len(entregas_) > 1:
            problemas.append(f"Reserva #{reserva_id}: en {len(entregas_)} entregas no canceladas")
    if problemas:
        raise AssertionError("Invariantes de entregas rotos: " + "; ".join(problemas))


def envase(invernadero, stock=30, unidad="unidad", *, nombre="Bandeja PET 1 kg", vence=None, activo=True, habilitado=True, insumo_activo=True, minimo=0):
    """Un envase (insumo de la categoría del sistema «envases», D-66 punto 8) habilitado en `invernadero` con `stock` en un lote (`vence` es su fecha de vencimiento;
    `stock=0` no crea lote). Devuelve el `InsumoInvernadero`. `activo=False` deja inactivo el insumo del invernadero; `habilitado=False`, también (no se ofrece);
    `insumo_activo=False`, el insumo del catálogo. COM-05a2 (PROD-PNF-ENV)."""
    from inventario.tests.fabricas import categoria_del_sistema, existencia, insumo, lote

    base = insumo(nombre=nombre, tipo=categoria_del_sistema("envases"), unidad=unidad, controla_vencimiento=vence is not None, activo=insumo_activo)
    creado = existencia(base, invernadero, minimo=minimo, activo=activo and habilitado)
    if Decimal(str(stock)) > 0:
        lote(creado, stock, vence=vence)
    return creado


# ---- COM-05b: asignar un transportista y cancelar la compra-venta ----


def vehiculo_en_ruta(transportista, *, fecha=None):
    """Deja el vehículo de ``transportista`` con la ruta iniciada (hoy, o en ``fecha``): MD-118; en COM-05b nadie inicia una ruta (lo hace COM-06), así que se arma directo.
    Con la fecha de hoy, sus entregas de hoy o anteriores están «en curso»."""
    Vehiculo.objects.filter(transportista=transportista).update(en_ruta=True, fecha_inicio_ruta=fecha or timezone.localdate())
    return Vehiculo.objects.get(transportista=transportista)


def con_cosecha_concretada(escenario, detalle_, lote_, *, reservada=20, cosechada=20, costo="2.5000", dias_atras=2):
    """Una reserva de ``detalle_`` con una cosecha ya concretada (hace ``dias_atras`` días) que cosechó ``cosechada`` de las ``reservada`` plantas de ``lote_``, con su salida por
    cosecha (el costo de la partida que nazca después) y su bitácora (invariante de COM-04a). La reserva queda «lista para entrega». Devuelve la reserva."""
    from comercial.models import DetalleReserva, ReservaStock
    from produccion.models import Bitacora, Cosecha, MovimientoStock

    hoy = timezone.localdate()
    r = reserva(detalle_, [(lote_, reservada)])
    Bitacora.objects.create(
        invernadero=lote_.invernadero, lote=lote_, etapa=lote_.etapa, tipo_evento="cosecha", cosecha=r.cosecha,
        fecha_bitacora=hoy, hora_bitacora=timezone.localtime().time(),
    )
    Cosecha.objects.filter(pk=r.cosecha_id).update(estado_orden="concretada", fecha_resolucion_orden=hoy, fecha_cosecha=hoy - timedelta(days=dias_atras))
    DetalleReserva.objects.filter(reserva=r).update(cantidad_cosechada=cosechada)
    ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="lista_para_entrega")
    MovimientoStock.objects.create(origen_id=r.cosecha_id, lote=lote_, tipo_movimiento="salida_por_cosecha", cantidad=cosechada, costo_unitario=Decimal(costo))
    r.refresh_from_db()
    return r


def venta_con_todo(escenario, *, pendiente=False, con_envases=False, transportista=None, cliente_=None, dias=3):
    """Una compra-venta con envío con todo lo que COM-CNL-CVT tiene que deshacer (D-67 punto 4), en dos variedades:

    - el detalle ``abierto`` (la variedad del escenario, 40 plantas): una reserva «activa» sobre ``lote_a`` con su cosecha «a realizar»;
    - el detalle ``cosechado`` (otra variedad, «Rúcula», 30 plantas a $100): una línea de lote ya cosechada (20 de ``lote_b``, con su cosecha concretada) y una línea de cámara (10
      de una partida), en reservas «lista para entrega», y su ``entrega`` «a realizar» con las dos (con ``transportista`` si se pasa; con ``con_envases``, 5 envases reservados).

    Con ``pendiente=True`` la venta queda «pendiente de decisión del cliente» (el detalle ``abierto`` también) y con su enlace vigente. Devuelve un `SimpleNamespace` con la venta, los
    dos detalles, sus reservas, las cosechas, los lotes, la partida de cámara, la entrega, el enlace (o ``None``) y los envases (o ``None``)."""
    from types import SimpleNamespace

    from produccion.tests.fabricas import lote_maduro, reservar, variedad_con_stock

    otra, _ = variedad_con_stock(escenario, f"Rúcula {next(_secuencia)}")
    lote_a = lote_maduro(escenario, 300)
    lote_b = lote_maduro(escenario, 300, variedad=otra)
    estado = "pendiente_decision" if pendiente else "abierta"
    venta = compra_venta(escenario, dias=dias, estado=estado, cliente_=cliente_)
    abierto = detalle(venta, escenario.variedad, 40, estado="pendiente_decision" if pendiente else "abierto")
    if pendiente:
        from comercial.models import DetalleVenta

        DetalleVenta.objects.filter(pk=abierto.pk).update(fecha_pendiente_decision=timezone.localdate())
    reserva_abierta = reserva(abierto, [(lote_a, 40)])
    cosechado = detalle(venta, otra, 30)
    reserva_cosechada = con_cosecha_concretada(escenario, cosechado, lote_b, reservada=20, cosechada=20)
    en_camara = partida(lote_b, 10)
    reserva_de_camara = reserva(cosechado, [(en_camara, 10)])
    entrega_ = entrega(venta, [reserva_cosechada, reserva_de_camara], transportista=transportista)
    envases = None
    if con_envases:
        envases = envase(escenario.invernadero, stock=30)
        reservar(entrega_, envases, 5)
    enlace_, token = None, None
    if pendiente and (cliente_ or escenario.cliente).email_cliente:
        enlace_, token = enlace(venta)
    return SimpleNamespace(
        venta=venta, abierto=abierto, cosechado=cosechado, reserva_abierta=reserva_abierta, cosecha=reserva_abierta.cosecha, reserva_cosechada=reserva_cosechada,
        reserva_de_camara=reserva_de_camara, lote_a=lote_a, lote_b=lote_b, partida=en_camara, entrega=entrega_, enlace=enlace_, token=token, envases=envases, variedad_b=otra,
    )
