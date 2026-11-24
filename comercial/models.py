# Modelos de `comercial` (nivel 6 de D-37) para COM-01: Cliente, DireccionCliente y Vehiculo (docs/modelo/comercial.md).
# Decisiones: D-05 (nombres en snake_case con el sufijo de la clase), D-06 (id automático), D-28 (alcance en un único
# lugar), D-37 (A2: la FK la declara la app de nivel mayor) y D-58 (DireccionCliente, la tabla de vínculo de R119).
# Las bajas son lógicas y las claves foráneas son PROTECT (docs/modelo/comercial.md, «Convenciones de esta ficha»).
#
# COM-02 suma `Contrato` (hija de `contabilidad.OrigenDocumento`, D-52), `CompraVenta`, `DetalleVenta`, `ReservaStock` y `DetalleReserva`
# (D-59). Las claves foráneas hacia `produccion` (`ReservaStock.cosecha`, `DetalleReserva.lote` y `.partida`) se declaran acá (A2 de D-37).

from django.db import models
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from core.models import Transportista, Usuario, Vendedor, rol_de
from core.validadores import validar_telefono
from maestros.models import Direccion, Invernadero, Variedad
from produccion.models import Cosecha, Lote, StockCosechado

# La patente argentina: AAA123 (formato viejo) o AA123AA (Mercosur), en mayúsculas y sin espacios (MD-129).
REGEX_PATENTE = r"^([A-Z]{3}[0-9]{3}|[A-Z]{2}[0-9]{3}[A-Z]{2})$"


class ClienteQuerySet(models.QuerySet):
    """QuerySet de clientes con el alcance por usuario en un único lugar (D-28, regla 3 de COM-CNS-CLT)."""

    def en_alcance_de(self, actor):
        """Clientes que ``actor`` consulta: el Gerente y el Vendedor activos ven todos (un cliente puede comprarle a varios
        Vendedores); cualquier otro actor, o una cuenta inactiva, ninguno."""
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        if rol_de(actor) in (Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR):
            return self.all()
        return self.none()


class Cliente(models.Model):
    """Cliente: persona física o jurídica externa que adquiere producción (COM-ALT-CLT; docs/modelo/comercial.md).

    El CUIT se guarda sin guiones y es único entre activos e inactivos (MD-48). ``tipo_cliente`` no está en el modelo de
    dominio: lo pide la regla 3 de COM-ALT-CLT. Solo se conservan los datos del tipo elegido (restricción de la base).
    """

    class Tipo(models.TextChoices):
        """Persona jurídica (razón social) o física (nombre y apellido)."""

        JURIDICA = "juridica", "Persona jurídica"
        FISICA = "fisica", "Persona física"

    class Estado(models.TextChoices):
        """Baja lógica (regla 1 de 8.18)."""

        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    tipo_cliente = models.CharField("tipo de cliente", max_length=10, choices=Tipo.choices)
    cuit_cliente = models.CharField("CUIT", max_length=11, unique=True)
    razon_social_cliente = models.CharField("razón social", max_length=150, blank=True)
    nombre_cliente = models.CharField("nombre", max_length=80, blank=True)
    apellido_cliente = models.CharField("apellido", max_length=80, blank=True)
    telefono_cliente = models.CharField("teléfono", max_length=25, blank=True, validators=[validar_telefono])
    # No es único: dos sucursales pueden compartir el correo de compras.
    email_cliente = models.EmailField("correo", blank=True)
    estado_cliente = models.CharField("estado", max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        constraints = [
            models.CheckConstraint(condition=Q(cuit_cliente__regex=r"^[0-9]{11}$"), name="cliente_cuit_11_digitos"),
            # Regla 3 de COM-ALT-CLT: jurídica ⇒ razón social y nada más; física ⇒ nombre y apellido y sin razón social.
            models.CheckConstraint(
                condition=(
                    Q(tipo_cliente="juridica")
                    & ~Q(razon_social_cliente="")
                    & Q(nombre_cliente="")
                    & Q(apellido_cliente="")
                )
                | (
                    Q(tipo_cliente="fisica")
                    & Q(razon_social_cliente="")
                    & ~Q(nombre_cliente="")
                    & ~Q(apellido_cliente="")
                ),
                name="cliente_datos_segun_tipo",
            ),
        ]

    @property
    def activo(self):
        """True si el cliente está en estado «activo»."""
        return self.estado_cliente == self.Estado.ACTIVO

    @property
    def nombre_visible(self):
        """La razón social o «Nombre Apellido» (``cliN`` del prototipo)."""
        if self.tipo_cliente == self.Tipo.JURIDICA:
            return self.razon_social_cliente
        return f"{self.nombre_cliente} {self.apellido_cliente}".strip()

    def __str__(self):
        """Es el texto de ``referencia()`` en la auditoría."""
        return self.nombre_visible


class DireccionCliente(models.Model):
    """R119 en el código (D-58): a qué cliente pertenece una dirección. La declara `comercial` porque es la app de nivel mayor
    (regla A2 de D-37). El ``OneToOneField`` hace que la base garantice que una dirección es de un solo cliente. La restricción
    C6 (cada dirección es de un invernadero o de un cliente) la garantizan los servicios: `comercial` crea siempre una dirección
    nueva y nunca vincula una existente."""

    direccion = models.OneToOneField(Direccion, on_delete=models.PROTECT, related_name="del_cliente")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="direcciones")

    class Meta:
        verbose_name = "Dirección de cliente"
        verbose_name_plural = "Direcciones de clientes"

    def __str__(self):
        return f"{self.cliente} · dirección {self.direccion_id}"


class VehiculoQuerySet(models.QuerySet):
    """QuerySet de vehículos con el alcance por usuario en un único lugar (D-28)."""

    def en_alcance_de(self, actor):
        """Vehículos que ``actor`` consulta: solo el Gerente activo (COM-ALT/MOD/BAJ/CNS-VEH); cualquier otro, ninguno."""
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        if rol_de(actor) == Usuario.Rol.GERENTE:
            return self.all()
        return self.none()


class Vehiculo(models.Model):
    """Vehículo con el que un Transportista hace las entregas con envío (COM-ALT-VEH; docs/modelo/comercial.md).

    Trabaja para el invernadero de su transportista (R155 indirecta): no se guarda en el vehículo. La patente se guarda en
    mayúsculas, sin espacios ni guiones (MD-129).
    """

    class Tipo(models.TextChoices):
        """Lista cerrada de tipos (MD-129)."""

        CAMIONETA = "camioneta", "Camioneta"
        FURGON = "furgon", "Furgón"
        CAMION = "camion", "Camión"
        UTILITARIO = "utilitario", "Utilitario"
        MOTO = "moto", "Moto"

    class Estado(models.TextChoices):
        """Baja lógica."""

        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    patente = models.CharField("patente", max_length=7, unique=True)
    tipo_vehiculo = models.CharField("tipo", max_length=12, choices=Tipo.choices)
    marca = models.CharField("marca", max_length=50)
    modelo = models.CharField("modelo", max_length=50)
    # Peso máximo que lleva en el día, en un solo viaje (regla 6 de 8.12): hasta 999.999,99 kg.
    capacidad_carga = models.DecimalField("capacidad de carga (kg)", max_digits=8, decimal_places=2)
    estado_vehiculo = models.CharField("estado", max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    en_ruta = models.BooleanField("en ruta", default=False)
    fecha_inicio_ruta = models.DateField("fecha de inicio de la ruta", null=True, blank=True)
    # R073: a lo sumo un vehículo por transportista, garantizado por la base. Se asigna desde el vehículo (regla 1 de 8.22).
    transportista = models.OneToOneField(
        Transportista, null=True, blank=True, on_delete=models.PROTECT, related_name="vehiculo"
    )

    objects = VehiculoQuerySet.as_manager()

    class Meta:
        ordering = ["patente"]
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"
        constraints = [
            models.CheckConstraint(condition=Q(patente__regex=REGEX_PATENTE), name="vehiculo_patente_con_formato"),
            models.CheckConstraint(condition=Q(capacidad_carga__gt=0), name="vehiculo_capacidad_mayor_que_cero"),
            # MD-118: una ruta iniciada tiene su fecha.
            models.CheckConstraint(
                condition=Q(en_ruta=False) | Q(fecha_inicio_ruta__isnull=False), name="vehiculo_en_ruta_con_fecha"
            ),
            # Postcondición a de COM-BAJ-VEH y c de COM-MOD-VEH: un vehículo inactivo no tiene transportista.
            models.CheckConstraint(
                condition=Q(estado_vehiculo="activo") | Q(transportista__isnull=True),
                name="vehiculo_inactivo_sin_transportista",
            ),
        ]

    @property
    def activo(self):
        """True si el vehículo está en estado «activo»."""
        return self.estado_vehiculo == self.Estado.ACTIVO

    def esta_en_ruta(self, hoy):
        """MD-118: está en ruta si ``en_ruta`` es verdadero **y** la ruta se inició ``hoy``. Una ruta que no se finalizó deja
        de estar vigente al terminar el día. Nadie lee ``en_ruta`` solo."""
        return bool(self.en_ruta and self.fecha_inicio_ruta == hoy)

    def __str__(self):
        """«Camioneta AE123CD»: es el texto de ``referencia()`` en la auditoría."""
        return f"{self.get_tipo_vehiculo_display()} {self.patente}"


class ContratoQuerySet(models.QuerySet):
    """QuerySet de contratos con el alcance por usuario en un único lugar (D-28; docs/modelo/comercial.md, «Contrato»)."""

    def en_alcance_de(self, actor):
        """Contratos que ``actor`` consulta: el Gerente activo ve todos; el Vendedor activo, solo aquellos de los que es ``vendedor``;
        cualquier otro actor, o una cuenta inactiva, ninguno."""
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        rol = rol_de(actor)
        if rol == Usuario.Rol.GERENTE:
            return self.all()
        if rol == Usuario.Rol.VENDEDOR:
            return self.filter(vendedor_id=actor.pk)
        return self.none()


class Contrato(OrigenDocumento):
    """Contrato con un cliente: padre de `CompraVenta` (COM-02) y de `Suministro` (COM-03), con herencia multitabla como `OrdenTrabajo`.
    Hija directa de `OrigenDocumento` (D-52): ``TIPO_DE_ORIGEN = contrato``; su clave es ``origendocumento_ptr``. ``numero`` es único por
    tipo y lo asigna el servicio con una secuencia de PostgreSQL por tipo (``comercial_compraventa_numero_seq``). El Vendedor es el
    responsable (regla 1 de 8.11); quien lo cargó queda en la auditoría. Puede cambiar por un traspaso (D-60)."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.CONTRATO

    class Tipo(models.TextChoices):
        """Discriminador de la herencia; nunca cambia."""

        COMPRA_VENTA = "compra_venta", "Compra-venta"
        SUMINISTRO = "suministro", "Suministro"

    class EstadoDelComprobante(models.TextChoices):
        """Resultado del envío del último comprobante (pasos 16, 16a y 16b de COM-REG-CVT); permite «Reenviar comprobante»."""

        ENVIADO = "enviado", "Enviado"
        PENDIENTE_ENVIO = "pendiente_envio", "Pendiente de envío"
        PARA_IMPRIMIR = "para_imprimir", "Para imprimir"

    # El nombre `tipo` ya es del padre (`OrigenDocumento`): el discriminador se llama `tipo_contrato` (mismo caso que `tipo_orden`, D-81).
    tipo_contrato = models.CharField(max_length=20, choices=Tipo.choices)
    numero = models.PositiveIntegerField()
    fecha_realizacion = models.DateField(default=timezone.localdate)
    estado_comprobante = models.CharField(
        max_length=20, choices=EstadoDelComprobante.choices, default=EstadoDelComprobante.PENDIENTE_ENVIO
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="contratos")  # R114
    vendedor = models.ForeignKey(Vendedor, on_delete=models.PROTECT, related_name="contratos")  # R115

    objects = ContratoQuerySet.as_manager()

    class Meta:
        verbose_name = "Contrato"
        verbose_name_plural = "Contratos"
        constraints = [
            models.UniqueConstraint(fields=["tipo_contrato", "numero"], name="contrato_numero_unico_por_tipo"),
            models.CheckConstraint(condition=Q(tipo_contrato__in=["compra_venta", "suministro"]), name="contrato_tipo_valido"),
            models.CheckConstraint(
                condition=Q(estado_comprobante__in=["enviado", "pendiente_envio", "para_imprimir"]), name="contrato_comprobante_valido"
            ),
        ]

    @property
    def codigo(self):
        """``CV-0001`` o ``SUM-0001``: lo que muestran las pantallas, los avisos y el registro de auditoría."""
        prefijo = "CV" if self.tipo_contrato == self.Tipo.COMPRA_VENTA else "SUM"
        return f"{prefijo}-{self.numero:04d}"

    def __str__(self):
        """El código (texto de ``referencia()`` en la auditoría, D-36)."""
        return self.codigo


class CompraVentaQuerySet(ContratoQuerySet):
    """El alcance del contrato más el monto de cada venta, calculado en la base (sin consultas por fila)."""

    def con_monto(self):
        """Anota ``monto``: por detalle, confirmado → entregada × precio; abierto o pendiente de decisión → solicitada × precio; rechazado o
        cancelado → 0 (COM-CNS-CVT, «Monto»). La etiqueta «final» o «estimado» la da el estado de la venta (``monto_es_final``)."""
        pesos = DecimalField(max_digits=18, decimal_places=2)
        entregado = ExpressionWrapper(
            Coalesce(F("detalles__cant_entregada_venta"), 0) * F("detalles__precio_unitario_de_venta"), output_field=pesos
        )
        pedido = ExpressionWrapper(F("detalles__cant_solicitada_venta") * F("detalles__precio_unitario_de_venta"), output_field=pesos)
        importe = Case(
            When(detalles__estado_detalle_venta="confirmado", then=entregado),
            When(detalles__estado_detalle_venta__in=["abierto", "pendiente_decision"], then=pedido),
            default=Value(0, output_field=pesos),
            output_field=pesos,
        )
        return self.annotate(monto=Coalesce(Sum(importe), Value(0, output_field=pesos), output_field=pesos))


class CompraVenta(Contrato):
    """Venta al contado: al registrarse queda abierta, con el stock reservado y sin pago ni asiento (regla 19 de 8.6). Los datos de la
    cancelación (MD-130) los suma COM-05b. El monto no se guarda: es derivado (docs/modelo/comercial.md, «CompraVenta»)."""

    class Estado(models.TextChoices):
        """Regla 21 de 8.6: nace «abierta»."""

        ABIERTA = "abierta", "Abierta"
        PENDIENTE_DECISION = "pendiente_decision", "Pendiente de decisión del cliente"
        CONCRETADA = "concretada", "Concretada"
        CANCELADA = "cancelada", "Cancelada"

    class Modalidad(models.TextChoices):
        """Cómo recibe el producto el cliente."""

        RETIRO = "retiro", "Retiro en invernadero"
        ENVIO = "envio", "Envío a domicilio"

    estado_venta = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ABIERTA)
    fecha_pactada_venta = models.DateField()  # igual o posterior a la de hoy al registrar
    fecha_concrecion_venta = models.DateField(null=True, blank=True)  # la carga COM-06a
    modalidad_entrega = models.CharField(max_length=10, choices=Modalidad.choices)
    # R146: solo con envío, y una dirección ACTIVA del cliente (D-58): la base no puede verificarlo entre dos apps, lo verifica el servicio.
    direccion_envio = models.ForeignKey(
        Direccion, null=True, blank=True, on_delete=models.PROTECT, related_name="compra_ventas_con_envio"
    )
    # R151: solo con retiro; uno de los invernaderos activos del Vendedor.
    invernadero_retiro = models.ForeignKey(
        Invernadero, null=True, blank=True, on_delete=models.PROTECT, related_name="compra_ventas_con_retiro"
    )

    objects = CompraVentaQuerySet.as_manager()

    @property
    def monto_es_final(self):
        """«final» si la venta está concretada o cancelada; «estimado» si no (COM-CNS-CVT, «Monto»)."""
        return self.estado_venta in (self.Estado.CONCRETADA, self.Estado.CANCELADA)

    class Meta:
        verbose_name = "Compra-venta"
        verbose_name_plural = "Compra-ventas"
        indexes = [models.Index(fields=["estado_venta"], name="compra_venta_estado_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(estado_venta__in=["abierta", "pendiente_decision", "concretada", "cancelada"]),
                name="compra_venta_estado_valido",
            ),
            # Envío ⇒ dirección y sin invernadero; retiro ⇒ invernadero y sin dirección.
            models.CheckConstraint(
                condition=(Q(modalidad_entrega="envio") & Q(direccion_envio__isnull=False) & Q(invernadero_retiro__isnull=True))
                | (Q(modalidad_entrega="retiro") & Q(invernadero_retiro__isnull=False) & Q(direccion_envio__isnull=True)),
                name="compra_venta_destino_segun_modalidad",
            ),
        ]


class DetalleVenta(models.Model):
    """Una variedad de una compra-venta, con su cantidad, su precio y su estado (R113, R127). La cantidad solicitada no se modifica
    (regla 20 de 8.6). El subtotal es derivado: cantidad entregada (o solicitada, para el estimado) × precio."""

    class Estado(models.TextChoices):
        """Nace «abierto»; «cancelado» es de MD-130."""

        ABIERTO = "abierto", "Abierto"
        PENDIENTE_DECISION = "pendiente_decision", "Pendiente de decisión del cliente"
        CONFIRMADO = "confirmado", "Confirmado"
        RECHAZADO = "rechazado", "Rechazado"
        CANCELADO = "cancelado", "Cancelado"

    compra_venta = models.ForeignKey(CompraVenta, on_delete=models.PROTECT, related_name="detalles")
    variedad = models.ForeignKey(Variedad, on_delete=models.PROTECT, related_name="detalles_de_venta")  # R127
    cant_solicitada_venta = models.PositiveIntegerField()
    precio_unitario_de_venta = models.DecimalField(max_digits=12, decimal_places=2)
    cant_entregada_venta = models.PositiveIntegerField(null=True, blank=True)  # nula hasta que se fija (reglas 16 y 27 de 8.6)
    estado_detalle_venta = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ABIERTO)
    fecha_pendiente_decision = models.DateField(null=True, blank=True)  # la carga COM-04

    class Meta:
        verbose_name = "Detalle de venta"
        verbose_name_plural = "Detalles de venta"
        constraints = [
            # Regla 2 de 8.11: una variedad por venta.
            models.UniqueConstraint(fields=["compra_venta", "variedad"], name="detalle_venta_una_variedad_por_venta"),
            models.CheckConstraint(condition=Q(cant_solicitada_venta__gte=1), name="detalle_venta_cantidad_positiva"),
            models.CheckConstraint(condition=Q(precio_unitario_de_venta__gt=0), name="detalle_venta_precio_positivo"),
            models.CheckConstraint(
                condition=Q(cant_entregada_venta__isnull=True) | Q(cant_entregada_venta__gte=0), name="detalle_venta_entregada_no_negativa"
            ),
            models.CheckConstraint(
                condition=Q(estado_detalle_venta__in=["abierto", "pendiente_decision", "confirmado", "rechazado", "cancelado"]),
                name="detalle_venta_estado_valido",
            ),
        ]

    def __str__(self):
        """«CV-0001 · Lechuga Crespa» (texto de la auditoría, D-36)."""
        return f"{self.compra_venta.codigo} · {self.variedad}"


class ReservaStock(models.Model):
    """Producto apartado para un detalle de contrato (o, desde COM-04, para una cosecha manual sin contrato). Toma todo su stock de un
    único invernadero (regla 1 de 8.8), que se guarda para consultar y bloquear sin recorrer las líneas. No tiene variedad propia: es la
    del detalle (o la de su cosecha)."""

    class Estado(models.TextChoices):
        """Estado inicial: regla 12 de 8.6."""

        ACTIVA = "activa", "Activa"
        LISTA_PARA_ENTREGA = "lista_para_entrega", "Lista para entrega"
        ENTREGADA = "entregada", "Entregada"
        LIBERADA = "liberada", "Liberada"

    detalle_venta = models.ForeignKey(
        DetalleVenta, null=True, blank=True, on_delete=models.PROTECT, related_name="reservas"
    )  # R123
    # R124 (COM-03): la reserva de un período lleva el detalle y `fecha_entrega_reserva` = la fecha del período.
    detalle_suministro = models.ForeignKey(
        "DetalleSuministro", null=True, blank=True, on_delete=models.PROTECT, related_name="reservas"
    )
    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="reservas_de_stock")
    fecha_reserva = models.DateField(default=timezone.localdate)
    # En una compra-venta, la pactada; nunca cambia (regla 12 de 8.8). Nula solo en la reserva de una cosecha sin contrato (D-64 punto 6).
    fecha_entrega_reserva = models.DateField(null=True, blank=True)
    estado_reserva = models.CharField(max_length=20, choices=Estado.choices)
    # R087: «toda cosecha tiene una reserva» lo garantiza el servicio que la crea.
    cosecha = models.OneToOneField(Cosecha, null=True, blank=True, on_delete=models.PROTECT, related_name="reserva")

    class Meta:
        verbose_name = "Reserva de stock"
        verbose_name_plural = "Reservas de stock"
        indexes = [models.Index(fields=["estado_reserva"], name="reserva_stock_estado_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(estado_reserva__in=["activa", "lista_para_entrega", "entregada", "liberada"]),
                name="reserva_stock_estado_valido",
            ),
            # C3: a lo sumo uno de R123 y R124 (ninguno: la reserva de una cosecha manual sin contrato, COM-04).
            models.CheckConstraint(
                condition=Q(detalle_venta__isnull=True) | Q(detalle_suministro__isnull=True), name="reserva_stock_un_solo_detalle"
            ),
        ]

    def __str__(self):
        """«Reserva #N» (texto de la auditoría, D-36)."""
        return f"Reserva #{self.pk}"


class DetalleReserva(models.Model):
    """Línea de una reserva: de qué origen físico sale una parte (un lote en pie o una partida de cámara)."""

    reserva = models.ForeignKey(ReservaStock, on_delete=models.PROTECT, related_name="lineas")  # R141
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.PROTECT, related_name="lineas_de_reserva")  # R142
    partida = models.ForeignKey(
        StockCosechado, null=True, blank=True, on_delete=models.PROTECT, related_name="lineas_de_reserva"
    )  # R143
    cantidad_reservada = models.PositiveIntegerField()
    # Solo en líneas de lote; vacío = todavía no se cosechó; un número, incluido 0, es lo que rindió (lo carga COM-04).
    cantidad_cosechada = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Línea de reserva"
        verbose_name_plural = "Líneas de reserva"
        constraints = [
            # C1: exactamente uno de `lote` y `partida`.
            models.CheckConstraint(
                condition=(Q(lote__isnull=False) & Q(partida__isnull=True)) | (Q(lote__isnull=True) & Q(partida__isnull=False)),
                name="linea_reserva_lote_o_partida",
            ),
            # Al menos 1, salvo en una línea de partida, que admite 0 (D-64 punto 7: el recorte de la merma en cámara).
            models.CheckConstraint(
                condition=Q(cantidad_reservada__gte=1) | (Q(partida__isnull=False) & Q(cantidad_reservada=0)),
                name="linea_reserva_cantidad_positiva",
            ),
            # Una partida nunca se «cosecha».
            models.CheckConstraint(
                condition=Q(partida__isnull=True) | Q(cantidad_cosechada__isnull=True), name="linea_reserva_partida_sin_cosechada"
            ),
        ]

    def __str__(self):
        """«Línea #N» (texto de la auditoría, D-36)."""
        return f"Línea #{self.pk}"


# ---- COM-03: Suministro, DetalleSuministro y sus cláusulas (docs/modelo/comercial.md) ----


class Suministro(Contrato):
    """Contrato de entregas periódicas a un cliente, con cláusulas resolutorias (COM-PCT-SUM). Hija de `Contrato` (``tipo_contrato =
    suministro``). Código visible ``SUM-0001`` con la secuencia ``comercial_suministro_numero_seq``. ``fecha_fin`` es derivada pero se
    guarda (la filtran las consultas y la pre-reserva): la calcula solo el servicio con ``calendario.sumar_meses``. Los campos de la rescisión
    (MD-140) y ``fecha_resolucion_suministro`` (MD-120) los escriben COM-03b y COM-07b: se crean ya para tener una sola migración."""

    class Estado(models.TextChoices):
        """Regla 5 de 8.11: nace «vigente». «Rescindido» es de COM-RSC-SUM (MD-140)."""

        VIGENTE = "vigente", "Vigente"
        FINALIZADO = "finalizado", "Finalizado"
        RESUELTO = "resuelto", "Resuelto"
        RESCINDIDO = "rescindido", "Rescindido"

    class MotivoDeRescision(models.TextChoices):
        """MD-140."""

        A_PEDIDO_DEL_CLIENTE = "a_pedido_del_cliente", "A pedido del cliente"
        A_PEDIDO_DE_LA_EMPRESA = "a_pedido_de_la_empresa", "A pedido de la empresa"
        OTRO = "otro", "Otro"

    duracion_meses = models.PositiveSmallIntegerField()
    estado_suministro = models.CharField(max_length=12, choices=Estado.choices, default=Estado.VIGENTE)
    fecha_fin = models.DateField()
    incumplimientos_tolerados = models.PositiveSmallIntegerField()  # PCU 16: de 0 a 99
    multa_resolucion = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_incumplimientos = models.PositiveIntegerField(default=0)  # regla 6 de 8.11
    fecha_resolucion_suministro = models.DateField(null=True, blank=True)  # MD-120: la carga COM-07b
    # MD-140 (los carga COM-03b): rescisión por mutuo acuerdo.
    motivo_rescision = models.CharField(max_length=25, choices=MotivoDeRescision.choices, null=True, blank=True)
    descripcion_rescision = models.CharField(max_length=500, blank=True, default="")
    fecha_acuerdo_rescision = models.DateField(null=True, blank=True)
    fecha_registro_rescision = models.DateField(null=True, blank=True)
    fecha_ultima_entrega_rescision = models.DateField(null=True, blank=True)
    fecha_rescision = models.DateField(null=True, blank=True)

    objects = ContratoQuerySet.as_manager()

    class Meta:
        verbose_name = "Suministro"
        verbose_name_plural = "Suministros"
        indexes = [models.Index(fields=["estado_suministro"], name="suministro_estado_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(estado_suministro__in=["vigente", "finalizado", "resuelto", "rescindido"]), name="suministro_estado_valido"
            ),
            models.CheckConstraint(condition=Q(duracion_meses__gte=1, duracion_meses__lte=120), name="suministro_duracion_valida"),
            models.CheckConstraint(
                condition=Q(incumplimientos_tolerados__gte=0, incumplimientos_tolerados__lte=99), name="suministro_tolerados_validos"
            ),
            models.CheckConstraint(condition=Q(multa_resolucion__gte=0), name="suministro_multa_no_negativa"),
            models.CheckConstraint(condition=Q(cantidad_incumplimientos__gte=0), name="suministro_incumplimientos_no_negativos"),
            # resuelto <=> fecha de resolución.
            models.CheckConstraint(
                condition=(Q(estado_suministro="resuelto") & Q(fecha_resolucion_suministro__isnull=False))
                | (~Q(estado_suministro="resuelto") & Q(fecha_resolucion_suministro__isnull=True)),
                name="suministro_resuelto_con_fecha",
            ),
            # rescindido <=> fecha de rescisión.
            models.CheckConstraint(
                condition=(Q(estado_suministro="rescindido") & Q(fecha_rescision__isnull=False))
                | (~Q(estado_suministro="rescindido") & Q(fecha_rescision__isnull=True)),
                name="suministro_rescindido_con_fecha",
            ),
            # Rescisión acordada (motivo no nulo) <=> las tres fechas del acuerdo no nulas.
            models.CheckConstraint(
                condition=(
                    Q(motivo_rescision__isnull=False)
                    & Q(fecha_acuerdo_rescision__isnull=False)
                    & Q(fecha_registro_rescision__isnull=False)
                    & Q(fecha_ultima_entrega_rescision__isnull=False)
                )
                | (
                    Q(motivo_rescision__isnull=True)
                    & Q(fecha_acuerdo_rescision__isnull=True)
                    & Q(fecha_registro_rescision__isnull=True)
                    & Q(fecha_ultima_entrega_rescision__isnull=True)
                ),
                name="suministro_rescision_completa",
            ),
            models.CheckConstraint(
                condition=Q(fecha_acuerdo_rescision__isnull=True)
                | Q(fecha_registro_rescision__isnull=True)
                | Q(fecha_acuerdo_rescision__lte=F("fecha_registro_rescision")),
                name="suministro_acuerdo_no_posterior_al_registro",
            ),
            # rescindido => rescisión acordada.
            models.CheckConstraint(
                condition=~Q(estado_suministro="rescindido") | Q(motivo_rescision__isnull=False), name="suministro_rescindido_acordado"
            ),
        ]

    @property
    def al_limite(self):
        """Regla 9 de COM-CNS-SUM: un contrato vigente está «al límite» si le queda un solo incumplimiento tolerado o ya usó todos (el próximo lo
        resuelve, regla 5 de 8.11)."""
        return self.estado_suministro == self.Estado.VIGENTE and self.cantidad_incumplimientos >= self.incumplimientos_tolerados - 1

    @property
    def tiene_rescision_acordada(self):
        """«Rescisión acordada» = motivo no nulo con el estado «vigente» (docs/modelo/comercial.md)."""
        return self.motivo_rescision is not None and self.estado_suministro == self.Estado.VIGENTE


class DetalleSuministro(models.Model):
    """Una variedad que se entrega periódicamente en una dirección del cliente (R112, R125, R126). El calendario no se guarda: se calcula
    (``calendario.calendario``). ``reemplaza_a`` y ``fecha_fin_detalle`` (MD-131) los escribe COM-03b. ``fecha_base_ajuste`` no está en el
    modelo: desde cuándo se cuentan los meses del ajuste (docs/modelo/comercial.md)."""

    class Mecanismo(models.TextChoices):
        """Mecanismo de precio."""

        FIJO = "fijo", "Fijo"
        AJUSTE_PERIODICO = "ajuste_periodico", "Ajuste periódico"

    class Estado(models.TextChoices):
        """Nace «vigente»; «finalizado» lo escribe COM-MOD-SUM y «resuelto», COM-RSV-SUM."""

        VIGENTE = "vigente", "Vigente"
        FINALIZADO = "finalizado", "Finalizado"
        RESUELTO = "resuelto", "Resuelto"

    suministro = models.ForeignKey(Suministro, on_delete=models.PROTECT, related_name="detalles")  # R112
    # R125: una dirección activa del cliente del contrato; la verifica el servicio (D-58), no la base.
    direccion = models.ForeignKey(Direccion, on_delete=models.PROTECT, related_name="detalles_de_suministro")
    variedad = models.ForeignKey(Variedad, on_delete=models.PROTECT, related_name="detalles_de_suministro")  # R126
    periodo_entrega_dias = models.PositiveSmallIntegerField()
    fecha_primer_entrega = models.DateField()
    cantidad_por_periodo = models.PositiveIntegerField()
    mecanismo_precio = models.CharField(max_length=20, choices=Mecanismo.choices)
    estado_detalle_suministro = models.CharField(max_length=12, choices=Estado.choices, default=Estado.VIGENTE)
    precio_unitario_suministro = models.DecimalField(max_digits=9, decimal_places=2)  # precio inicial
    porcentaje_ajuste = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    meses_ajuste = models.PositiveSmallIntegerField(null=True, blank=True)
    fecha_fin_detalle = models.DateField(null=True, blank=True)  # MD-131
    fecha_base_ajuste = models.DateField()
    reemplaza_a = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="sucesor")  # MD-131

    class Meta:
        verbose_name = "Detalle de suministro"
        verbose_name_plural = "Detalles de suministro"
        constraints = [
            models.CheckConstraint(condition=Q(periodo_entrega_dias__gte=1, periodo_entrega_dias__lte=365), name="detalle_suministro_periodo_valido"),
            models.CheckConstraint(condition=Q(cantidad_por_periodo__gte=1, cantidad_por_periodo__lte=500000), name="detalle_suministro_cantidad_valida"),
            models.CheckConstraint(
                condition=Q(precio_unitario_suministro__gte="0.01", precio_unitario_suministro__lte="9999999.99"),
                name="detalle_suministro_precio_valido",
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_ajuste__isnull=True) | Q(porcentaje_ajuste__gte="0.01", porcentaje_ajuste__lte=100),
                name="detalle_suministro_porcentaje_valido",
            ),
            models.CheckConstraint(
                condition=Q(meses_ajuste__isnull=True) | Q(meses_ajuste__gte=1, meses_ajuste__lte=60), name="detalle_suministro_meses_validos"
            ),
            models.CheckConstraint(
                condition=Q(mecanismo_precio__in=["fijo", "ajuste_periodico"]), name="detalle_suministro_mecanismo_valido"
            ),
            models.CheckConstraint(
                condition=Q(estado_detalle_suministro__in=["vigente", "finalizado", "resuelto"]), name="detalle_suministro_estado_valido"
            ),
            # fijo => sin ajuste; ajuste periódico => porcentaje y meses.
            models.CheckConstraint(
                condition=(Q(mecanismo_precio="fijo") & Q(porcentaje_ajuste__isnull=True) & Q(meses_ajuste__isnull=True))
                | (Q(mecanismo_precio="ajuste_periodico") & Q(porcentaje_ajuste__isnull=False) & Q(meses_ajuste__isnull=False)),
                name="detalle_suministro_ajuste_segun_mecanismo",
            ),
            # Regla «Dirección y modalidad» y MD-131: un par (variedad, dirección) vigente por contrato; los finalizados no cuentan.
            models.UniqueConstraint(
                fields=["suministro", "variedad", "direccion"],
                condition=Q(estado_detalle_suministro="vigente"),
                name="detalle_suministro_par_vigente_unico",
            ),
        ]

    def __str__(self):
        """«SUM-0001 · Lechuga Crespa» (texto de la auditoría, D-36)."""
        return f"{self.suministro.codigo} · {self.variedad}"


class ClausulaResolutoria(models.Model):
    """Padre sin atributos de las dos cláusulas: abstracta (una tabla vacía no agrega nada y cada hija tiene un solo dueño)."""

    class Meta:
        abstract = True


class ClausulaSuministrado(ClausulaResolutoria):
    """Una por contrato (MD-124): rige el pago de todas sus entregas. Un cambio la actualiza (MD-132)."""

    suministro = models.OneToOneField(Suministro, on_delete=models.PROTECT, related_name="clausula_suministrado")
    plazo_pago_dias = models.PositiveSmallIntegerField()
    indemnizacion_retraso_pago = models.DecimalField(max_digits=9, decimal_places=2)

    class Meta:
        verbose_name = "Cláusula del suministrado"
        verbose_name_plural = "Cláusulas del suministrado"
        constraints = [
            models.CheckConstraint(condition=Q(plazo_pago_dias__gte=0, plazo_pago_dias__lte=365), name="clausula_suministrado_plazo_valido"),
            models.CheckConstraint(
                condition=Q(indemnizacion_retraso_pago__gte=0, indemnizacion_retraso_pago__lte="9999999.99"),
                name="clausula_suministrado_indemnizacion_valida",
            ),
        ]

    def __str__(self):
        """«Cláusula del suministrado de SUM-0001»."""
        return f"Cláusula del suministrado de {self.suministro.codigo}"


class ClausulaSuministrante(ClausulaResolutoria):
    """Una por detalle. Un cambio crea el detalle sucesor con su cláusula nueva. ``cantidad_minima`` no puede superar la cantidad por
    período del detalle: está en otra tabla y lo verifica el servicio."""

    detalle = models.OneToOneField(DetalleSuministro, on_delete=models.PROTECT, related_name="clausula_suministrante")
    plazo_entrega_dias = models.PositiveSmallIntegerField()
    indemnizacion_retraso_entrega = models.DecimalField(max_digits=9, decimal_places=2)
    cantidad_minima = models.PositiveIntegerField()
    indemnizacion_faltante = models.DecimalField(max_digits=9, decimal_places=2)

    class Meta:
        verbose_name = "Cláusula del suministrante"
        verbose_name_plural = "Cláusulas del suministrante"
        constraints = [
            models.CheckConstraint(condition=Q(plazo_entrega_dias__gte=0, plazo_entrega_dias__lte=365), name="clausula_suministrante_plazo_valido"),
            models.CheckConstraint(
                condition=Q(indemnizacion_retraso_entrega__gte=0, indemnizacion_retraso_entrega__lte="9999999.99"),
                name="clausula_suministrante_retraso_valido",
            ),
            models.CheckConstraint(condition=Q(cantidad_minima__gte=1), name="clausula_suministrante_minima_valida"),
            models.CheckConstraint(
                condition=Q(indemnizacion_faltante__gte=0, indemnizacion_faltante__lte="9999999.99"),
                name="clausula_suministrante_faltante_valido",
            ),
        ]

    def __str__(self):
        """«Cláusula del suministrante de SUM-0001 · Lechuga Crespa»."""
        return f"Cláusula del suministrante de {self.detalle}"
