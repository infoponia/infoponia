# Fábricas compartidas por las pruebas de compras/tests/ (CMP-01): CUIT válidos, un proveedor creado directo en la base (sin pasar por el
# servicio de alta) y los datos de un alta. Reutilizan las fábricas de cuentas de core y de maestros. Una sola firma por función.

from compras.models import Proveedor
from inventario.tests.fabricas import tipo_de_insumo  # noqa: F401  (lo reexportan para las pruebas de compras)

# Marca de «el actor por defecto» de los auxiliares de las pruebas: ``None`` es un actor válido (sin cuenta) y tiene que llegar al servicio.
GERENTE = object()

_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_valido(n=1):
    """El ``n``-ésimo CUIT válido de la fábrica (11 dígitos, sin guiones), distinto para cada ``n``. Calcula el verificador por su cuenta
    (módulo 11), sin usar ``maestros.validadores``: así una prueba del validador no depende de lo que verifica. Salta los números cuyo
    verificador daría 10, que no son válidos."""
    base = 3_000_000_000 + n * 13
    while True:
        resto = sum(peso * int(digito) for peso, digito in zip(_PESOS_CUIT, str(base))) % 11
        verificador = 11 - resto
        if verificador == 11:
            verificador = 0
        if verificador != 10:
            return f"{base}{verificador}"
        base += 1


def con_guiones(cuit):
    """``cuit`` (11 dígitos) como «30-71234567-1»."""
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}"


def proveedor(
    razon_social="Semillas del Sur S. A.",
    n=1,
    cuit=None,
    tipo="juridica",
    nombre="",
    apellido="",
    email="ventas@semillasdelsur.com",
    telefono="",
    activo=True,
    especialidades=(),
):
    """Un proveedor creado directo en la base. Por defecto es una persona jurídica activa con el CUIT número ``n``; con
    ``tipo="fisica"`` hay que pasar ``nombre`` y ``apellido`` (y la razón social se deja vacía)."""
    if tipo == "fisica":
        razon_social = ""
    else:
        nombre = apellido = ""
    creado = Proveedor.objects.create(
        tipo_proveedor=tipo,
        cuit_proveedor=cuit or cuit_valido(n),
        razon_social_proveedor=razon_social,
        nombre_proveedor=nombre,
        apellido_proveedor=apellido,
        email_proveedor=email,
        telefono_proveedor=telefono,
        estado_proveedor="activo" if activo else "inactivo",
    )
    creado.especialidades.set(especialidades)
    return creado


def datos_de_alta(**cambios):
    """Los datos de un alta de proveedor (una persona jurídica) con el CUIT número 1; ``cambios`` pisa lo que se indique. Las claves son
    las del servicio: ``tipo``, ``cuit``, ``razon_social``, ``nombre``, ``apellido``, ``email``, ``telefono`` y ``especialidades``."""
    datos = {
        "tipo": "juridica",
        "cuit": cuit_valido(1),
        "razon_social": "Semillas del Sur S. A.",
        "nombre": "",
        "apellido": "",
        "email": "ventas@semillasdelsur.com",
        "telefono": "",
        "especialidades": [],
    }
    datos.update(cambios)
    return datos


def datos_de(proveedor, **cambios):
    """Los datos de una modificación o de una reactivación que dejan al ``proveedor`` igual que está; ``cambios`` pisa lo que se indique.
    Las claves son las del servicio (como ``datos_de_alta``, con el CUIT en 11 dígitos)."""
    datos = {
        "cuit": proveedor.cuit_proveedor,
        "razon_social": proveedor.razon_social_proveedor,
        "nombre": proveedor.nombre_proveedor,
        "apellido": proveedor.apellido_proveedor,
        "email": proveedor.email_proveedor,
        "telefono": proveedor.telefono_proveedor,
        "especialidades": [categoria.pk for categoria in proveedor.especialidades.all()],
    }
    datos.update(cambios)
    return datos


def ref(objeto, texto=None):
    """Cómo queda una referencia en el detalle de la auditoría (D-36): ``{"id", "texto"}``; el texto es el ``__str__`` del objeto
    (o ``texto`` si se indica)."""
    return {"id": objeto.pk, "texto": texto if texto is not None else str(objeto)}


def afectado_de(proveedor):
    """Cómo queda un proveedor entre los afectados de un registro de auditoría (D-36), sin el rol (solo lo llevan las cuentas)."""
    return {"modelo": "compras.proveedor", "id": proveedor.pk, "texto": str(proveedor)}


# ---------------------------------------------------------------------------------------------------------------------------------
# Pedidos, enlaces y cotizaciones (CMP-02a). Armados directo en la base, sin pasar por los servicios: cada prueba arma sus datos.
# ---------------------------------------------------------------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.utils import timezone  # noqa: E402

from compras.models import Cotizacion, DetalleCotizacion, DetallePedido, EnlaceProveedor, InvitacionPedido, Pedido  # noqa: E402
from core.enlaces import nuevo_token  # noqa: E402


def pedido(agronomo, dias_al_limite=3, estado="en_cotizacion", causa=None, motivo="", cerrado_el=None, **extra):
    """Un ``Pedido`` de ``agronomo`` hecho hoy, con la fecha límite dentro de ``dias_al_limite`` días. Sin detalles ni invitados."""
    hoy = timezone.localdate()
    if estado != "en_cotizacion" and cerrado_el is None:
        cerrado_el = hoy
    return Pedido.objects.create(
        agronomo=agronomo,
        fecha_pedido=hoy,
        fecha_limite_cotizaciones=hoy + timedelta(days=dias_al_limite),
        estado_pedido=estado,
        causa_cancelacion=causa,
        motivo_cancelacion=motivo,
        fecha_cierre_pedido=cerrado_el,
        **extra,
    )


def detalle_de_pedido(pedido, existencia, cantidad="10", precio=None):
    """Un detalle de ``pedido`` para la ``existencia`` (``InsumoInvernadero``); el precio por omisión es su precio de referencia."""
    return DetallePedido.objects.create(
        pedido=pedido,
        insumo_invernadero=existencia,
        cantidad_detalle=Decimal(str(cantidad)),
        precio_unitario_de_pedido=Decimal(str(precio)) if precio is not None else existencia.referencia_precio,
    )


def invitar(pedido, proveedor):
    """La invitación de ``proveedor`` a ``pedido``, sin enlace."""
    return InvitacionPedido.objects.create(pedido=pedido, proveedor=proveedor)


def enlace_de(invitacion, estado="vigente", usado_el=None, envio=None):
    """Un enlace de ``invitacion`` en ``estado``. Devuelve ``(enlace, token)``: el token solo vive en la prueba."""
    token, resumen = nuevo_token()
    if estado == "usado" and usado_el is None:
        usado_el = timezone.now()
    enlace = EnlaceProveedor.objects.create(
        invitacion=invitacion, token_resumen=resumen, estado=estado, fecha_uso=usado_el, estado_envio=envio
    )
    return enlace, token


def cotizacion_de(pedido, proveedor, lineas, validez_en_dias=10, observaciones="", estado="propuesta"):
    """Una cotización de ``proveedor`` para ``pedido``. ``lineas = [(detalle_pedido, cantidad, total_linea, plazo_en_dias)]``."""
    hoy = timezone.localdate()
    cotizacion = Cotizacion.objects.create(
        pedido=pedido,
        proveedor=proveedor,
        fecha_cotizacion=hoy,
        fecha_validez_cotizacion=hoy + timedelta(days=validez_en_dias),
        observaciones_cotizacion=observaciones,
        estado_cotizacion=estado,
    )
    for detalle, cantidad, total, plazo in lineas:
        DetalleCotizacion.objects.create(
            cotizacion=cotizacion,
            detalle_pedido=detalle,
            cantidad_cotizada=Decimal(str(cantidad)),
            total_linea=Decimal(str(total)),
            plazo_entrega_dias=plazo,
        )
    return cotizacion


# ---------------------------------------------------------------------------------------------------------------------------------
# Órdenes de compra (CMP-03). Armadas directo en la base, sin pasar por los servicios.
# ---------------------------------------------------------------------------------------------------------------------------------

from compras.models import DetalleOrdenCompra, OrdenCompra  # noqa: E402


def orden_de(pedido, cotizaciones, estado="pendiente_aprobacion", gerente=None, hoy=None, motivo=""):
    """Una ``OrdenCompra`` de ``pedido`` con un detalle por cada línea de las ``cotizaciones`` (que pasan a «seleccionada», o a «descartada» si la
    orden es «rechazada»; el pedido, a «cerrado»). Si ``estado`` no es «pendiente de aprobación» hace falta ``gerente`` (y ``motivo`` si es
    «rechazada»); la fecha de resolución es ``hoy``. No calcula la fecha de entrega esperada: la pone el servicio al aprobar."""
    hoy = hoy or timezone.localdate()
    resuelta = estado != "pendiente_aprobacion"
    if pedido.estado_pedido == "en_cotizacion":
        Pedido.objects.filter(pk=pedido.pk).update(estado_pedido="cerrado", fecha_cierre_pedido=hoy)
        pedido.refresh_from_db()
    orden = OrdenCompra.objects.create(
        pedido=pedido,
        fecha_emision=hoy,
        fecha_resolucion=hoy if resuelta else None,
        estado_orden_compra=estado,
        gerente=gerente if resuelta else None,
        motivo_rechazo=motivo,
    )
    for cotizacion in cotizaciones:
        Cotizacion.objects.filter(pk=cotizacion.pk).update(estado_cotizacion="descartada" if estado == "rechazada" else "seleccionada")
        for linea in cotizacion.lineas.order_by("id"):
            DetalleOrdenCompra.objects.create(
                orden=orden, detalle_cotizacion=linea, cantidad_detalle_orden=linea.cantidad_cotizada, total_linea=linea.total_linea
            )
    return orden


# ---------------------------------------------------------------------------------------------------------------------------------
# Recepciones (CMP-04). El escenario compartido por las pruebas de la recepción, del cierre con faltante y de la concurrencia.
# ---------------------------------------------------------------------------------------------------------------------------------


def orden_aprobada(gerente, pedido, cotizaciones):
    """Una ``OrdenCompra`` «aprobada» por el servicio real (``ordenes.aprobar_orden``): la fecha de entrega esperada de cada línea (hoy + su plazo) y el tránsito de cada
    ``InsumoInvernadero`` quedan como en producción. Devuelve la orden releída."""
    from compras.servicios import ordenes  # adentro: los servicios importan estas fábricas en sus pruebas

    orden = orden_de(pedido, cotizaciones)
    return ordenes.aprobar_orden(gerente, orden.pk)


class EscenarioDeRecepcion:
    """Mixin de pruebas: ``self.armar()`` deja armado el escenario de CMP-04 (se llama desde ``setUp``).

    Ana (invernaderos Norte y Norte 2) y Beto (Sur), un Gerente, los proveedores A y B y una orden **aprobada** de Ana con tres líneas:
    - ``l_fert`` (A, Norte): 10 kg de Fertilizante (controla vencimiento), total $100,00 ($10,00 el kg), entrega en 3 días;
    - ``l_maceta`` (A, Norte): 20 unidades de Maceta (no vence), total $200,00 ($10,00 la unidad), entrega en 5 días;
    - ``l_tomate`` (B, Norte 2): 8 unidades de Tomate (no vence), total $80,00, entrega en 2 días.
    El tránsito de cada existencia ya es la cantidad pedida y no hay stock. ``hoy`` y ``vence`` (hoy + 90 días) son los de la prueba.
    """

    def armar(self):
        from datetime import timedelta

        from core.tests.fabricas import crear_gerente
        from inventario.tests.fabricas import existencia, insumo
        from maestros.tests.fabricas import crear_agronomo_con_invernadero, crear_invernadero

        self.hoy = timezone.localdate()
        self.vence = self.hoy + timedelta(days=90)
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        self.fertilizante = existencia(insumo("Fertilizante", unidad="kg", controla_vencimiento=True), self.norte, minimo=0, precio="10.00")
        self.maceta = existencia(insumo("Maceta", unidad="unidad"), self.norte, minimo=0, precio="10.00")
        self.norte2 = crear_invernadero("Norte 2", agronomo=self.ana)
        self.tomate = existencia(insumo("Tomate", unidad="unidad"), self.norte2, minimo=0, precio="10.00")
        self.proveedor = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.proveedor_b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.pedido = pedido(self.ana)
        self.d_fert = detalle_de_pedido(self.pedido, self.fertilizante, cantidad="10")
        self.d_maceta = detalle_de_pedido(self.pedido, self.maceta, cantidad="20")
        self.d_tomate = detalle_de_pedido(self.pedido, self.tomate, cantidad="8")
        self.cotizacion = cotizacion_de(self.pedido, self.proveedor, [(self.d_fert, 10, "100.00", 3), (self.d_maceta, 20, "200.00", 5)])
        self.cotizacion_b = cotizacion_de(self.pedido, self.proveedor_b, [(self.d_tomate, 8, "80.00", 2)])
        self.orden = orden_aprobada(self.gerente, self.pedido, [self.cotizacion, self.cotizacion_b])
        self.l_fert = self.orden.detalles.get(detalle_cotizacion__detalle_pedido=self.d_fert)
        self.l_maceta = self.orden.detalles.get(detalle_cotizacion__detalle_pedido=self.d_maceta)
        self.l_tomate = self.orden.detalles.get(detalle_cotizacion__detalle_pedido=self.d_tomate)

    def otra_orden(self, agronomo, invernadero, nombre_de_insumo="Sustrato", cantidad=6, total="60.00", n=5, plazo=2):
        """Una segunda orden **aprobada** de ``agronomo`` con una línea de ``cantidad`` unidades de un insumo nuevo en ``invernadero`` (otro proveedor, ``n``).
        Devuelve ``(orden, linea, existencia)``."""
        from inventario.tests.fabricas import existencia, insumo

        iin = existencia(insumo(nombre_de_insumo, unidad="unidad"), invernadero, minimo=0, precio="10.00")
        otro_pedido = pedido(agronomo)
        detalle = detalle_de_pedido(otro_pedido, iin, cantidad=str(cantidad))
        proveedor_b = proveedor(f"Proveedor {n} S. R. L.", n=n, email=f"p{n}@proveedor.com")
        cotizacion = cotizacion_de(otro_pedido, proveedor_b, [(detalle, cantidad, total, plazo)])
        orden = orden_aprobada(self.gerente, otro_pedido, [cotizacion])
        return orden, orden.detalles.get(), iin
