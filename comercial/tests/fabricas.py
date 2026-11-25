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


def enlace_de_confirmacion(entrega_, *, estado="vigente", estado_envio="enviado", cliente_=None):
    """COM-06b: el `EnlaceCliente` de confirmación de ``entrega_`` (una entrega de suministro) creado directo (sin correo ni `on_commit`), con su token. Devuelve ``(enlace, token)``: la base
    guarda solo el resumen. Nunca lleva `fecha_vencimiento` (la vigencia se calcula, D-68 punto 8); con ``estado="usado"`` guarda `fecha_uso` (restricción)."""
    from comercial.models import EnlaceCliente
    from core.enlaces import nuevo_token

    token, resumen = nuevo_token()
    return (
        EnlaceCliente.objects.create(
            tipo=EnlaceCliente.Tipo.CONFIRMACION_ENTREGA,
            cliente=cliente_ or entrega_.contrato_entrega.cliente,
            entrega=entrega_,
            token_resumen=resumen,
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
    if estado == "concretada":
        marcar_concretada(nueva)  # desde COM-06a, una entrega concretada trae sus cantidades y sus montos (invariantes de `verificar_invariantes_de_entregas`)
    return nueva


def marcar_concretada(entrega_, *, cantidades=None, hace_dias=0):
    """COM-06a: deja ``entrega_`` «concretada» **directo en la base** (sin pasar por `concretar_entrega`, que prueba el bloque 2), con los datos de la concreción que exigen la
    base y `verificar_invariantes_de_entregas`: por línea, entregada, perdida, devuelta y monto, y en la entrega el total (y, en un suministro, el vencimiento del pago con el plazo de
    la cláusula). ``cantidades`` es una lista de ``(entregada, perdida, devuelta)`` en el orden de las líneas (por omisión, todo lo planificado se entrega). COM-08a: ``hace_dias`` la
    concreta en el pasado (la fecha de resolución y, a partir de ella, el vencimiento del pago) y, en un suministro, copia la indemnización por día de la cláusula en la entrega (D-94, punto 12),
    como `concretar_entrega`. No toca reservas, cámara, detalles ni contrato. Devuelve la entrega refrescada."""
    from comercial.models import ClausulaSuministrado, CompraVenta, DetalleEntrega, Entrega
    from comercial.servicios import entregas as servicio

    hoy = timezone.localdate()
    lineas = list(entrega_.lineas.order_by("pk"))
    planificadas = servicio.cantidades_planificadas([linea.pk for linea in lineas])
    total = Decimal("0.00")
    for i, linea in enumerate(lineas):
        entregada, perdida, devuelta = cantidades[i] if cantidades else (planificadas[linea.pk], 0, 0)
        monto = (Decimal(entregada) * linea.precio_unitario).quantize(Decimal("0.01"))
        DetalleEntrega.objects.filter(pk=linea.pk).update(cant_entregada=entregada, cant_perdida=perdida, cant_devuelta=devuelta, monto_pagar=monto)
        total += monto
    vencimiento = None
    por_dia = None
    concrecion = hoy - timedelta(days=hace_dias)
    if not CompraVenta.objects.filter(pk=entrega_.contrato_entrega_id).exists():
        clausula = ClausulaSuministrado.objects.filter(suministro_id=entrega_.contrato_entrega_id).first()
        vencimiento = concrecion + timedelta(days=clausula.plazo_pago_dias if clausula else 30)
        por_dia = clausula.indemnizacion_retraso_pago if clausula else None
    Entrega.objects.filter(pk=entrega_.pk).update(
        estado_orden="concretada", fecha_resolucion_orden=concrecion, monto_total_entrega=total, fecha_vencimiento_pago=vencimiento, indemnizacion_retraso_dia=por_dia
    )
    entrega_.refresh_from_db()
    return entrega_


def entrega_concretada(contrato, reservas, *, cantidades=None, transportista=None, fecha=None, con_pago=False, medio="efectivo"):
    """COM-06a: una entrega ya concretada, armada directo (ver `marcar_concretada`) con ``cantidades``. En una compra-venta con ``con_pago=True``, además deja sus detalles
    «confirmados» con lo entregado, un `PagoCliente` vigente por el total y la venta «concretada» con la fecha de hoy (la concreción de su única entrega, postcondición k)."""
    from comercial.models import CompraVenta, DetalleVenta

    nueva = entrega(contrato, reservas, fecha=fecha, transportista=transportista)
    marcar_concretada(nueva, cantidades=cantidades)
    if con_pago and contrato.tipo_contrato == "compra_venta":
        for linea in nueva.lineas.filter(detalle_venta__isnull=False):
            DetalleVenta.objects.filter(pk=linea.detalle_venta_id).update(estado_detalle_venta="confirmado", cant_entregada_venta=linea.cant_entregada)
        CompraVenta.objects.filter(pk=contrato.pk).update(estado_venta="concretada", fecha_concrecion_venta=timezone.localdate())
        pago_de_compra_venta(CompraVenta.objects.get(pk=contrato.pk), medio, monto=nueva.monto_total_entrega)
    return nueva


def pago_de_compra_venta(venta, medio="efectivo", *, monto=None, estado="vigente"):
    """COM-06a: un `PagoCliente` de ``venta`` creado directo, de hoy, por ``monto`` (por omisión, lo entregado de sus detalles «confirmados» o 100,00). Para las pruebas de las
    restricciones y de las fichas; la concreción real lo crea `concretar_entrega`."""
    from comercial.models import DetalleVenta, PagoCliente

    if monto is None:
        confirmados = DetalleVenta.objects.filter(compra_venta=venta, estado_detalle_venta="confirmado")
        monto = sum((Decimal(d.cant_entregada_venta or 0) * d.precio_unitario_de_venta for d in confirmados), Decimal("0.00")) or Decimal("100.00")
    return PagoCliente.objects.create(cliente=venta.cliente, compra_venta=venta, medio_pago=medio, fecha_pago=timezone.localdate(), monto_pagado=monto, estado_pago=estado)


def entrega_de_suministro(escenario, lote_, *, contrato=None, cantidad=10, precio="100.00", plazo_pago=10, indemnizacion_pago="300.00", hace_dias=0, cantidades=None, vendedor=None, cliente_=None):
    """COM-08a: una entrega de suministro ya concretada, armada directo (ver `marcar_concretada`), de ``cantidad`` plantas a ``precio`` (por omisión $ 1.000,00), con ``hace_dias`` de concretada: vence
    ``plazo_pago`` días después de eso. Sin ``contrato`` crea un suministro nuevo del cliente del escenario (con su plazo de pago y su indemnización por día); con ``contrato``, suma otra entrega (otro
    período del mismo detalle, de modo que dos de un contrato no chocan). ``vendedor`` y ``cliente_`` arman el contrato nuevo de otro Vendedor o de otro cliente (este necesita una dirección). Devuelve la `Entrega` refrescada."""
    from comercial.models import DetalleEntrega

    if contrato is None:
        contrato = suministro(escenario, plazo_pago=plazo_pago, indemnizacion_pago=indemnizacion_pago, vendedor=vendedor, cliente_=cliente_)
        detalle_ = detalle_suministro(contrato, escenario.variedad, cantidad=cantidad, primera_en_dias=0, precio=precio)
    else:
        detalle_ = contrato.detalles.order_by("pk").first()
    k = DetalleEntrega.objects.filter(detalle_suministro=detalle_).count()
    fecha_periodo = detalle_.fecha_primer_entrega + timedelta(days=detalle_.periodo_entrega_dias * k)
    reserva_ = reserva_lista(None, lote_, cantidad, fecha_entrega=fecha_periodo, detalle_suministro=detalle_)
    nueva = entrega(contrato, [reserva_], fecha=timezone.localdate())
    return marcar_concretada(nueva, cantidades=cantidades, hace_dias=hace_dias)


def entrega_en_mora(escenario, lote_, *, dias_de_mora=3, plazo_pago=10, **extra):
    """COM-08a: una entrega de suministro concretada que venció hace ``dias_de_mora`` días (hace `plazo_pago + dias_de_mora` que se concretó). Sin pago ni aviso: la deja así `marcar_concretada`; el
    paso 30 es el que la avisa. Acepta lo de `entrega_de_suministro`."""
    return entrega_de_suministro(escenario, lote_, plazo_pago=plazo_pago, hace_dias=plazo_pago + dias_de_mora, **extra)


def cobro(entregas_, *, medio="efectivo", usuario=None, fecha=None, estado="vigente", aviso="enviado"):
    """COM-08a: un `PagoCliente` de suministro de ``entregas_`` (todas de un mismo cliente) creado directo, con una `LineaPago` por entrega: lo cobrado es su monto a cobrar de hoy y el atraso, los días
    entre su vencimiento y ``fecha`` (por omisión, hoy) por la indemnización por día que guardó la entrega. ``estado = anulado`` deja el pago y sus líneas anulados (como lo hará COM-08b). No resuelve
    alertas ni manda nada: es para las pruebas de las restricciones, del estado de pago y de las fichas; el cobro real lo registra `cobranza.registrar_cobro`."""
    from django.db import connection

    from comercial.models import Contrato, LineaPago, PagoCliente
    from comercial.servicios import entregas as servicio

    entregas_ = list(entregas_)
    fecha = fecha or timezone.localdate()
    vigente = estado == "vigente"
    montos = servicio.monto_a_cobrar([e.pk for e in entregas_])
    lineas, total = [], Decimal("0.00")
    for e in entregas_:
        dias = max(0, (fecha - e.fecha_vencimiento_pago).days)
        indemnizacion = (Decimal(dias) * (e.indemnizacion_retraso_dia or Decimal("0.00"))).quantize(Decimal("0.01"))
        lineas.append((e, montos[e.pk], dias, indemnizacion))
        total += montos[e.pk] + indemnizacion
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_cobro_numero_seq')")
        numero = cursor.fetchone()[0]
    cliente_ = Contrato.objects.get(pk=entregas_[0].contrato_entrega_id).cliente
    pago = PagoCliente.objects.create(
        tipo_pago="suministro", numero=numero, cliente=cliente_, medio_pago=medio, fecha_pago=fecha, monto_pagado=total, estado_pago=estado, usuario=usuario, estado_aviso_cliente=aviso
    )
    for e, monto, dias, indemnizacion in lineas:
        LineaPago.objects.create(pago=pago, entrega=e, monto_cobrado=monto, dias_atraso=dias, indemnizacion_atraso=indemnizacion, vigente=vigente)
    return pago


def verificar_invariantes_de_cobros():
    """Invariantes de `docs/modelo/comercial.md`, «PagoCliente», «LineaPago» y «Entrega» (COM-08a; `cobranza.md`, «Pruebas»), los que la base no puede vigilar: se llama al final de cada prueba que
    cobra. Verifica que (1) un pago de suministro tiene al menos una línea y uno de compra-venta ninguna; (2) `monto_pagado` es Σ (`monto_cobrado` + `indemnizacion_atraso`) de sus líneas; (3) `vigente`
    de cada línea es el estado de su pago; (4) las entregas de un pago son de suministro, están concretadas y son del cliente del pago; (5) una entrega con línea vigente tiene `monto_cobrado` igual a su
    monto a cobrar; (6) solo una entrega de suministro concretada tiene `fecha_aviso_mora`; (7) una entrega en mora, sin pagar y con `fecha_aviso_mora` tiene su alerta «pago en mora» activa si su
    invernadero está activo. (El de «un pago anulado tiene su `Anulacion`» es de COM-08b.) Lanza `AssertionError` con lo que encuentra."""
    from comercial.models import AlertaComercial, CompraVenta, Entrega, LineaPago, PagoCliente
    from comercial.servicios import entregas as servicio

    problemas = []
    hoy = timezone.localdate()
    for p in PagoCliente.objects.order_by("pk"):
        lineas = list(p.lineas.select_related("entrega"))
        if p.tipo_pago == "compra_venta":
            if lineas:
                problemas.append(f"{p.codigo}: un pago de compra-venta con {len(lineas)} líneas de pago")
            continue
        if not lineas:
            problemas.append(f"{p.codigo}: un pago de suministro sin líneas")
            continue
        suma = sum((l.monto_cobrado + l.indemnizacion_atraso for l in lineas), Decimal("0.00"))
        if p.monto_pagado != suma:
            problemas.append(f"{p.codigo}: monto pagado {p.monto_pagado} distinto de la suma de sus líneas {suma}")
        for l in lineas:
            if l.vigente != (p.estado_pago == "vigente"):
                problemas.append(f"{p.codigo}: la línea #{l.pk} con vigente={l.vigente} y el pago {p.estado_pago}")
            e = l.entrega
            if e.estado_orden != "concretada" or e.fecha_vencimiento_pago is None:
                problemas.append(f"{p.codigo}: la línea #{l.pk} es de {e.codigo}, que no es una entrega de suministro concretada")
            elif e.contrato_entrega.cliente_id != p.cliente_id:
                problemas.append(f"{p.codigo}: la línea #{l.pk} es de {e.codigo}, de otro cliente")
        for l in lineas:
            if l.vigente and l.monto_cobrado != servicio.monto_a_cobrar([l.entrega_id])[l.entrega_id]:
                problemas.append(f"{p.codigo}: lo cobrado de {l.entrega.codigo} ({l.monto_cobrado}) no es su monto a cobrar")
    cobradas = set(LineaPago.objects.filter(vigente=True).values_list("entrega_id", flat=True))
    en_ventas = set(CompraVenta.objects.values_list("pk", flat=True))
    for e in Entrega.objects.filter(fecha_aviso_mora__isnull=False).select_related("invernadero").order_by("pk"):
        if e.estado_orden != "concretada" or e.contrato_entrega_id in en_ventas or e.fecha_vencimiento_pago is None:
            problemas.append(f"{e.codigo}: con fecha de aviso de mora y no es una entrega de suministro concretada")
            continue
        monto = servicio.monto_a_cobrar([e.pk])[e.pk]
        if e.pk not in cobradas and monto > 0 and e.fecha_vencimiento_pago < hoy and e.invernadero.estado_invernadero == "activo":
            if not AlertaComercial.objects.filter(entrega=e, alerta__tipo_alerta="comercial_pago_en_mora", alerta__estado_alerta="activa").exists():
                problemas.append(f"{e.codigo}: en mora y avisada, sin su alerta «pago en mora» activa")
    if problemas:
        raise AssertionError("Invariantes de cobros rotos: " + "; ".join(problemas))


def discrepancia(entrega_, *, minima=None, con_alerta=True):
    """COM-06a: la `DiscrepanciaEntrega` de una entrega de suministro concretada, con una línea por cada línea de la entrega (la entregada que tiene y ``minima``, por omisión, una
    más) y su alerta para el Gerente con su `AlertaComercial`, creadas directo. La concreción real la crea `concrecion.crear_discrepancia`."""
    from django.db import transaction

    from comercial.models import AlertaComercial, DiscrepanciaEntrega, LineaDiscrepancia
    from comercial.servicios import solicitudes
    from maestros.tests.fabricas import crear_alerta

    with transaction.atomic():  # `crear_solicitud` exige la transacción del caso de uso (también en los `TransactionTestCase`)
        creada = solicitudes.crear_solicitud(DiscrepanciaEntrega, entrega_)
    for linea in entrega_.lineas.filter(detalle_suministro__isnull=False).order_by("pk"):
        entregada = linea.cant_entregada or 0
        LineaDiscrepancia.objects.create(discrepancia=creada, detalle_entrega=linea, cantidad_entregada=entregada, cantidad_minima_estipulada=minima or entregada + 1)
    if con_alerta:
        alerta = crear_alerta(entrega_.invernadero, "comercial_discrepancia_entrega", descripcion_alerta=f"{entrega_.codigo} · {creada.codigo}")
        AlertaComercial.objects.create(alerta=alerta, solicitud=creada)
    return creada


def queja(entrega_, tipo="estado_mercaderia", lineas=None, motivo=None, *, con_alerta=True):
    """COM-06b: una `Queja` «pendiente» de una entrega de suministro concretada, creada directo con `solicitudes.crear_solicitud`. ``lineas`` son las `DetalleEntrega` a las que se refiere (por
    omisión, todas las de la entrega); ``motivo`` por omisión es un texto para «estado de la mercadería» u «otro» y vacío para «retraso». Con ``con_alerta`` deja su alerta `comercial_queja` para el
    Gerente con su `AlertaComercial`. La respuesta real del cliente la registra `confirmacion.registrar_respuesta`."""
    from django.db import transaction

    from comercial.models import AlertaComercial, Queja
    from comercial.servicios import solicitudes
    from maestros.tests.fabricas import crear_alerta

    if motivo is None:
        motivo = "" if tipo == "retraso" else "El producto llegó en mal estado."
    with transaction.atomic():
        creada = solicitudes.crear_solicitud(Queja, entrega_, tipo_queja=tipo, motivo_queja=motivo, cliente=entrega_.contrato_entrega.cliente)
    creada.detalles.set(lineas if lineas is not None else entrega_.lineas.all())
    if con_alerta:
        alerta = crear_alerta(entrega_.invernadero, "comercial_queja", descripcion_alerta=f"{entrega_.codigo} · {creada.codigo}")
        AlertaComercial.objects.create(alerta=alerta, solicitud=creada)
    return creada


def alerta_no_reconocida(entrega_, motivo="No llegó nada.", *, resuelta=False):
    """COM-06b: la alerta crítica «entrega no reconocida por el cliente» de ``entrega_`` para el Gerente, con su `AlertaComercial(entrega=…)`, creada directo (la respuesta real del cliente la
    crea `confirmacion.registrar_respuesta`). Devuelve la `Alerta`."""
    from comercial.models import AlertaComercial
    from maestros.models import Alerta
    from maestros.tests.fabricas import crear_alerta

    alerta = crear_alerta(
        entrega_.invernadero,
        "comercial_entrega_no_reconocida",
        nivel_severidad=Alerta.Severidad.CRITICA,
        resuelta=resuelta,
        descripcion_alerta=f"{entrega_.codigo} · el cliente dice que no la recibió: “{motivo}”",
    )
    AlertaComercial.objects.create(alerta=alerta, entrega=entrega_)
    return alerta


def _aceptar(solicitud, *, monto, descontado, reintegrado, medio, gerente, observaciones, contar):
    """COM-07a: deja ``solicitud`` «aceptada» **directo en la base** (sin pasar por `resolver_solicitud`), con la aplicación pedida: ``monto`` (la indemnización), ``reintegrado`` y
    ``descontado`` (por omisión, ``monto − reintegrado``); ``medio`` solo con reintegro. Con ``contar`` suma 1 al contador del suministro (el invariante «contador = aceptadas»). En una
    discrepancia reparte el monto en sus líneas (todo en la primera, el resto en 0). Devuelve la solicitud refrescada."""
    from django.db.models import F

    from comercial.models import LineaDiscrepancia, SolicitudRevision, Suministro
    from core.models import Gerente
    from core.tests.fabricas import crear_gerente

    monto = Decimal(monto)
    reintegrado = Decimal(reintegrado)
    descontado = monto - reintegrado if descontado is None else Decimal(descontado)
    gerente = gerente or Gerente.objects.filter(is_active=True).first() or crear_gerente()
    if reintegrado > 0 and medio is None:
        medio = "efectivo"
    SolicitudRevision.objects.filter(pk=solicitud.pk).update(
        estado_solicitud="aceptada",
        fecha_resolucion=timezone.localdate(),
        gerente=gerente,
        observaciones_resolucion=observaciones,
        monto_indemnizacion=monto,
        monto_descontado=descontado,
        monto_reintegrado=reintegrado,
        medio_reintegro=medio if reintegrado > 0 else None,
        estado_aviso_cliente="enviado",
    )
    for i, linea in enumerate(LineaDiscrepancia.objects.filter(discrepancia_id=solicitud.pk).order_by("pk")):
        LineaDiscrepancia.objects.filter(pk=linea.pk).update(monto_indemnizacion_linea=monto if i == 0 else Decimal("0.00"))
    if contar:
        Suministro.objects.filter(pk=solicitud.entrega.contrato_entrega_id).update(cantidad_incumplimientos=F("cantidad_incumplimientos") + 1)
    return SolicitudRevision.objects.get(pk=solicitud.pk)


def discrepancia_aceptada(entrega_, *, monto="100.00", descontado=None, reintegrado="0.00", medio=None, gerente=None, observaciones="", contar=True, minima=None, con_alerta=True):
    """COM-07a: una `DiscrepanciaEntrega` de ``entrega_`` ya «aceptada», creada directo en la base (ver `_aceptar`). La resolución real la registra `solicitudes.resolver_solicitud`."""
    return _aceptar(
        discrepancia(entrega_, minima=minima, con_alerta=con_alerta), monto=monto, descontado=descontado, reintegrado=reintegrado, medio=medio, gerente=gerente, observaciones=observaciones, contar=contar
    )


def queja_aceptada(entrega_, tipo="estado_mercaderia", *, monto="100.00", descontado=None, reintegrado="0.00", medio=None, gerente=None, observaciones="", contar=True, lineas=None, motivo=None, con_alerta=True):
    """COM-07a: una `Queja` de ``entrega_`` ya «aceptada», creada directo en la base (ver `_aceptar`)."""
    return _aceptar(
        queja(entrega_, tipo, lineas, motivo, con_alerta=con_alerta), monto=monto, descontado=descontado, reintegrado=reintegrado, medio=medio, gerente=gerente, observaciones=observaciones, contar=contar
    )


def solicitud_rechazada(solicitud, *, gerente=None, observaciones="No corresponde."):
    """COM-07a: deja ``solicitud`` «rechazada» directo en la base (sin montos, sin contador). Devuelve la solicitud refrescada."""
    from comercial.models import SolicitudRevision
    from core.models import Gerente
    from core.tests.fabricas import crear_gerente

    gerente = gerente or Gerente.objects.filter(is_active=True).first() or crear_gerente()
    SolicitudRevision.objects.filter(pk=solicitud.pk).update(
        estado_solicitud="rechazada", fecha_resolucion=timezone.localdate(), gerente=gerente, observaciones_resolucion=observaciones, estado_aviso_cliente="enviado"
    )
    return SolicitudRevision.objects.get(pk=solicitud.pk)


def anulacion(solicitud, *, usuario=None, motivo="Error de carga.", reabrir=True):
    """COM-07a: una `Anulacion` de ``solicitud`` creada directo en la base, con la copia de la resolución que ésta tiene hoy (la solicitud tiene que estar resuelta). Con ``reabrir`` (por
    omisión) además la deja «pendiente» como lo hace `solicitudes.anular_resolucion` (campos de resolución y montos de las líneas vacíos y, si estaba aceptada, el contador −1)."""
    from django.db.models import F

    from comercial.models import Anulacion, LineaDiscrepancia, SolicitudRevision, Suministro
    from core.models import Gerente
    from core.tests.fabricas import crear_gerente

    solicitud = SolicitudRevision.objects.select_related("entrega").get(pk=solicitud.pk)
    usuario = usuario or Gerente.objects.filter(is_active=True).first() or crear_gerente()
    creada = Anulacion.objects.create(
        usuario=usuario,
        solicitud=solicitud,
        motivo_anulacion=motivo,
        estado_anulado=solicitud.estado_solicitud,
        fecha_resolucion_anulada=solicitud.fecha_resolucion,
        gerente_anulado=solicitud.gerente,
        observaciones_anuladas=solicitud.observaciones_resolucion,
        monto_indemnizacion_anulado=solicitud.monto_indemnizacion,
        monto_descontado_anulado=solicitud.monto_descontado,
        monto_reintegrado_anulado=solicitud.monto_reintegrado,
        medio_reintegro_anulado=solicitud.medio_reintegro,
    )
    if reabrir:
        SolicitudRevision.objects.filter(pk=solicitud.pk).update(
            estado_solicitud="pendiente", fecha_resolucion=None, gerente=None, observaciones_resolucion="", monto_indemnizacion=None, monto_descontado=None, monto_reintegrado=None,
            medio_reintegro=None, estado_aviso_cliente=None,
        )
        LineaDiscrepancia.objects.filter(discrepancia_id=solicitud.pk).update(monto_indemnizacion_linea=None)
        if solicitud.estado_solicitud == "aceptada":
            Suministro.objects.filter(pk=solicitud.entrega.contrato_entrega_id).update(cantidad_incumplimientos=F("cantidad_incumplimientos") - 1)
    return creada


def resolucion_del_suministro(suministro_, solicitud):
    """COM-07a (D-69, punto 5): deja ``suministro_`` «resuelto» por ``solicitud`` (carga `solicitud_resolucion` y la fecha), como lo hará COM-RSV-SUM en COM-07b; sirve para probar la extensión 2a de COM-ANL-SRV."""
    from comercial.models import Suministro

    Suministro.objects.filter(pk=suministro_.pk).update(estado_suministro="resuelto", fecha_resolucion_suministro=timezone.localdate(), solicitud_resolucion_id=solicitud.pk)
    return Suministro.objects.get(pk=suministro_.pk)


def verificar_invariantes_de_resolucion():
    """COM-07b (COM-RSV-SUM, «Garantías mínimas»): ninguna reserva «activa» ni «lista para entrega» de un detalle «resuelto» ni de un suministro «resuelto»; ninguna orden «a realizar» (cosecha o
    entrega) de un suministro «resuelto»; y el suministro «resuelto» con la fecha de resolución. Es un invariante APARTE de `verificar_invariantes_de_reservas` porque las pruebas de COM-07a dejan
    contratos «resueltos» con reservas sin tocar (las arma con `update`, sin pasar por el caso de uso). Lanza `AssertionError` con lo que encuentra."""
    from comercial.models import Entrega, ReservaStock, Suministro
    from produccion.models import Cosecha

    problemas = []
    for r in ReservaStock.objects.filter(estado_reserva__in=["activa", "lista_para_entrega"]).filter(
        detalle_suministro__estado_detalle_suministro="resuelto"
    ) | ReservaStock.objects.filter(estado_reserva__in=["activa", "lista_para_entrega"], detalle_suministro__suministro__estado_suministro="resuelto"):
        problemas.append(f"Reserva #{r.pk}: {r.estado_reserva} y de un contrato o un detalle resuelto")
    resueltos = list(Suministro.objects.filter(estado_suministro="resuelto").values_list("pk", flat=True))
    for e in Entrega.objects.filter(estado_orden="a_realizar", contrato_entrega_id__in=resueltos):
        problemas.append(f"{e.codigo}: a realizar y de un suministro resuelto")
    for c in Cosecha.objects.filter(estado_orden="a_realizar", reserva__detalle_suministro__suministro_id__in=resueltos):
        problemas.append(f"{c.codigo}: a realizar y de un suministro resuelto")
    if problemas:
        raise AssertionError("Invariantes de la resolución rotos: " + "; ".join(problemas))


def verificar_invariantes_de_solicitudes():
    """Invariantes de `docs/modelo/comercial.md`, «SolicitudRevision» y «DiscrepanciaEntrega» (COM-06a), los que la base no puede vigilar: (1) la entrega de una solicitud es de un
    suministro y está «concretada»; (2) las líneas de una discrepancia son de la entrega de la discrepancia y de un detalle de suministro; (3) una discrepancia tiene al menos una línea;
    (4) cada solicitud tiene exactamente una `AlertaComercial`; y, desde COM-06b, de cada `Queja`
    (docs/modelo/comercial.md, «Queja»): (5) al menos un detalle y todos de su entrega, (6) a lo sumo una por tipo en cada entrega (el enlace admite un solo envío), (7) la de retraso solo con
    detalles con días de retraso mayores que cero y (8) su `cliente` es el del contrato. Lanza `AssertionError` con lo que encuentra."""
    from collections import Counter
    from datetime import timedelta

    from comercial.models import AlertaComercial, CompraVenta, DiscrepanciaEntrega, Queja, SolicitudRevision

    problemas = []
    for s in SolicitudRevision.objects.select_related("entrega").order_by("pk"):
        if CompraVenta.objects.filter(pk=s.entrega.contrato_entrega_id).exists():
            problemas.append(f"{s.codigo}: de una entrega de compra-venta")
        if s.entrega.estado_orden != "concretada":
            problemas.append(f"{s.codigo}: de la entrega {s.entrega.codigo}, que no está concretada")
        alertas_ = AlertaComercial.objects.filter(solicitud_id=s.pk).count()
        if alertas_ != 1:
            problemas.append(f"{s.codigo}: con {alertas_} alertas")
    for d in DiscrepanciaEntrega.objects.order_by("pk"):
        lineas = list(d.lineas.select_related("detalle_entrega"))
        if not lineas:
            problemas.append(f"{d.codigo}: sin líneas")
        for linea in lineas:
            if linea.detalle_entrega.entrega_id != d.entrega_id or linea.detalle_entrega.detalle_suministro_id is None:
                problemas.append(f"{d.codigo}: línea #{linea.pk} de otra entrega o de un detalle que no es de suministro")
    quejas = list(Queja.objects.select_related("entrega__contrato_entrega").order_by("pk"))
    for (entrega_id, tipo), cuantas in Counter((q.entrega_id, q.tipo_queja) for q in quejas).items():
        if cuantas > 1:
            problemas.append(f"entrega #{entrega_id}: {cuantas} quejas de tipo {tipo} (a lo sumo una por tipo)")
    for q in quejas:
        detalles = list(q.detalles.select_related("detalle_suministro__clausula_suministrante"))
        if not detalles:
            problemas.append(f"{q.codigo}: sin detalles")
        if q.cliente_id != q.entrega.contrato_entrega.cliente_id:
            problemas.append(f"{q.codigo}: de un cliente que no es el del contrato")
        for detalle_ in detalles:
            if detalle_.entrega_id != q.entrega_id:
                problemas.append(f"{q.codigo}: el detalle #{detalle_.pk} es de otra entrega")
            if q.tipo_queja == "retraso":
                if detalle_.detalle_suministro_id is None or q.entrega.fecha_resolucion_orden is None:
                    problemas.append(f"{q.codigo}: queja por retraso con el detalle #{detalle_.pk}, que no es de un suministro concretado")
                    continue
                limite = detalle_.fecha_periodo + timedelta(days=detalle_.detalle_suministro.clausula_suministrante.plazo_entrega_dias)
                if q.entrega.fecha_resolucion_orden <= limite:
                    problemas.append(f"{q.codigo}: queja por retraso con el detalle #{detalle_.pk}, que no llegó con retraso")
    # COM-07a (docs/modelo/comercial.md, «SolicitudRevision»): (9) el monto a cobrar de una entrega nunca es negativo; (10) la cantidad de incumplimientos de un suministro con solicitudes es
    # la de sus solicitudes aceptadas; (11) en una discrepancia aceptada, el monto es la suma de sus líneas; (12) una pendiente o rechazada no tiene montos en sus líneas.
    from django.db.models import Count, Sum

    from comercial.models import Entrega, LineaDiscrepancia, Suministro

    aceptadas = SolicitudRevision.objects.filter(estado_solicitud="aceptada")
    descontado = {i: total for i, total in aceptadas.values("entrega_id").annotate(total=Sum("monto_descontado")).values_list("entrega_id", "total")}
    for entrega_id, total in Entrega.objects.filter(pk__in=descontado).values_list("pk", "monto_total_entrega"):
        if total is None or total - descontado[entrega_id] < 0:
            problemas.append(f"entrega #{entrega_id}: el monto a cobrar queda negativo ({total} − {descontado[entrega_id]})")
    por_contrato = dict(aceptadas.values("entrega__contrato_entrega_id").annotate(n=Count("pk")).values_list("entrega__contrato_entrega_id", "n"))
    con_solicitudes = set(SolicitudRevision.objects.values_list("entrega__contrato_entrega_id", flat=True))
    for suministro_id, cantidad in Suministro.objects.filter(pk__in=con_solicitudes).values_list("pk", "cantidad_incumplimientos"):
        if cantidad != por_contrato.get(suministro_id, 0):
            problemas.append(f"suministro #{suministro_id}: {cantidad} incumplimientos y {por_contrato.get(suministro_id, 0)} solicitudes aceptadas")
    for d in DiscrepanciaEntrega.objects.order_by("pk"):
        montos = list(LineaDiscrepancia.objects.filter(discrepancia_id=d.pk).values_list("monto_indemnizacion_linea", flat=True))
        if d.estado_solicitud == "aceptada":
            if any(m is None for m in montos) or sum(montos) != d.monto_indemnizacion:
                problemas.append(f"{d.codigo}: el monto de la indemnización no es la suma de sus líneas")
        elif any(m is not None for m in montos):
            problemas.append(f"{d.codigo}: {d.estado_solicitud} con montos en sus líneas")
    if problemas:
        raise AssertionError("Invariantes de solicitudes rotos: " + "; ".join(problemas))


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
    # COM-06a (docs/modelo/comercial.md, «Entrega», «DetalleEntrega» y «PagoCliente»): lo que deja la concreción.
    for e in Entrega.objects.order_by("pk"):
        concretada = e.estado_orden == "concretada"
        es_venta = CompraVenta.objects.filter(pk=e.contrato_entrega_id).exists()
        if (e.monto_total_entrega is not None) != concretada:
            problemas.append(f"{e.codigo}: monto total {e.monto_total_entrega!r} con la entrega en estado {e.estado_orden}")
        if (e.fecha_vencimiento_pago is not None) != (concretada and not es_venta):
            problemas.append(f"{e.codigo}: vencimiento del pago {e.fecha_vencimiento_pago!r} (solo lo tiene una entrega de suministro concretada)")
        lineas = list(e.lineas.order_by("pk"))
        con_datos = [linea for linea in lineas if linea.cant_entregada is not None]
        if len(con_datos) != (len(lineas) if concretada else 0):
            problemas.append(f"{e.codigo}: {len(con_datos)} de {len(lineas)} líneas con los datos de la concreción (estado {e.estado_orden})")
        if concretada and e.monto_total_entrega is not None and sum((l.monto_pagar or 0 for l in lineas), Decimal("0.00")) != e.monto_total_entrega:
            problemas.append(f"{e.codigo}: el monto total no es la suma de los montos de sus líneas")
        for linea in con_datos:
            if linea.monto_pagar != (Decimal(linea.cant_entregada) * linea.precio_unitario).quantize(Decimal("0.01")):
                problemas.append(f"{e.codigo}: línea #{linea.pk} con un monto que no es entregada × precio")
            if es_venta and linea.cant_entregada > 0 and linea.cant_devuelta > 0:
                problemas.append(f"{e.codigo}: línea #{linea.pk} de venta aceptada con devueltas (el cliente acepta todo lo que llegó o lo rechaza todo)")
    for v in CompraVenta.objects.order_by("pk"):
        vigentes = list(v.pagos.filter(estado_pago="vigente"))
        concretadas = Entrega.objects.filter(contrato_entrega_id=v.pk, estado_orden="concretada").exists()
        if any(p.cliente_id != v.cliente_id for p in v.pagos.all()):
            problemas.append(f"{v.codigo}: un pago de otro cliente")
        if v.estado_venta == "concretada" and concretadas:
            if len(vigentes) != 1:
                problemas.append(f"{v.codigo}: concretada con {len(vigentes)} pagos vigentes (tiene que tener uno)")
            else:
                total = sum((Decimal(d.cant_entregada_venta or 0) * d.precio_unitario_de_venta for d in v.detalles.filter(estado_detalle_venta="confirmado")), Decimal("0.00"))
                if vigentes[0].monto_pagado != total:
                    problemas.append(f"{v.codigo}: el pago ({vigentes[0].monto_pagado}) no es el total de lo entregado ({total})")
        if v.estado_venta == "cancelada" and not concretadas and vigentes:
            problemas.append(f"{v.codigo}: cancelada sin entregas concretadas y con un pago vigente")
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


def iniciar_ruta_de(transportista, escenario=None, lote_=None):
    """COM-06a: inicia de verdad la ruta de ``transportista`` con `rutas.iniciar_ruta` (reemplaza a `vehiculo_en_ruta` en las pruebas de «en curso», que desde esta tarea usan el servicio).
    Si no tiene entregas de la ruta (con envío, «a realizar», de hoy o anteriores) y se pasan ``escenario`` y ``lote_``, le arma una de 1 planta para hoy. Devuelve el `Vehiculo`."""
    from comercial.servicios import rutas

    if not rutas._de_la_ruta(transportista.pk, timezone.localdate()).exists() and escenario is not None:
        venta = compra_venta(escenario, dias=0)
        entrega(venta, [reserva_lista(detalle(venta, escenario.variedad, 1), lote_, 1)], transportista=transportista, fecha=timezone.localdate())
    return rutas.iniciar_ruta(transportista, rutas.ruta_del_dia(transportista).huella)


def entrega_concretable(escenario, lote_, *, tipo="venta", cantidad=50, con_envasado=False, ruta_iniciada=True, transportista=None, retiro=False, minima=None, plazo_pago=15, precio="100.00", dias=0):
    """COM-06a: una entrega lista para concretar con `concrecion.concretar_entrega`. ``tipo`` es «venta» (una compra-venta de ``cantidad`` plantas a ``precio``, sola en su venta) o «suministro»
    (un período de ``cantidad`` plantas con cantidad mínima ``minima``, que por omisión es la cantidad); con ``retiro=True`` la venta es con retiro (sin transportista, la concreta el Vendedor).
    ``con_envasado`` reserva 10 envases (de un stock de 30). Con envío y ``ruta_iniciada`` (por omisión) el Transportista inicia la ruta con `rutas.iniciar_ruta`. Devuelve un `SimpleNamespace`
    con `entrega`, `contrato`, `detalle`, `reserva`, `transportista` y `envases` (el `InsumoInvernadero` o ``None``)."""
    from types import SimpleNamespace

    from produccion.tests.fabricas import reservar

    envio = not retiro
    transportista = transportista or (transportista_con_vehiculo(escenario.invernadero) if envio else None)
    if tipo == "venta":
        contrato = compra_venta(escenario, dias=dias, modalidad="retiro" if retiro else "envio")
        detalle_ = detalle(contrato, escenario.variedad, cantidad, precio=precio)
        reserva_ = reserva_lista(detalle_, lote_, cantidad)
    else:
        contrato = suministro(escenario, plazo_pago=plazo_pago)
        detalle_ = detalle_suministro(contrato, escenario.variedad, cantidad=cantidad, minima=minima or cantidad, primera_en_dias=dias, precio=precio)
        reserva_ = reserva_lista(None, lote_, cantidad, fecha_entrega=detalle_.fecha_primer_entrega, detalle_suministro=detalle_)
    entrega_ = entrega(contrato, [reserva_], transportista=transportista if envio else None, fecha=timezone.localdate() - timedelta(days=0) if dias == 0 else None)
    envases = None
    if con_envasado:
        envases = envase(escenario.invernadero, stock=30)
        reservar(entrega_, envases, 10)
    if envio and ruta_iniciada:
        iniciar_ruta_de(transportista)
    return SimpleNamespace(entrega=entrega_, contrato=contrato, detalle=detalle_, reserva=reserva_, transportista=transportista, envases=envases)


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
