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


def partida(lote_, disponible=10, fecha_limite=None, estado="disponible", costo="1.0000"):
    """Una partida de cámara (`StockCosechado`) del ``lote_`` con ``disponible`` plantas y su fecha límite (por defecto, dentro de 30
    días). Las partidas reales las crea COM-04: acá solo existen en las pruebas."""
    hoy = timezone.localdate()
    return StockCosechado.objects.create(
        lote=lote_,
        cantidad_ingreso_cosechado=max(1, disponible),
        cantidad_disponible_cosechado=disponible,
        fecha_ingreso=hoy,
        fecha_limite=fecha_limite or hoy + timedelta(days=30),
        motivo_cosechado="excedente_de_cosecha",
        estado_stock_cosechado=estado if disponible else "agotado",
        costo_unitario_cosechado=Decimal(costo),
    )


def reserva(detalle_, lineas, estado=None, fecha_entrega=None, con_cosecha=True):
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
    from produccion.models import Cosecha, Lote

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
        cubierto = (
            DetalleReserva.objects.filter(reserva__detalle_venta=d).exclude(reserva__estado_reserva="liberada").aggregate(t=Sum("cantidad_reservada"))["t"]
            or 0
        )
        if cubierto > d.cant_solicitada_venta:
            problemas.append(f"{d}: cubierto {cubierto} > solicitado {d.cant_solicitada_venta}")
    if problemas:
        raise AssertionError("Invariantes de reservas rotos: " + "; ".join(problemas))
