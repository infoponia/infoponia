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
from produccion.models import Cosecha, Lote, OrdenTrabajo, StockCosechado

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
    cancelación (MD-130, COM-05b) los carga COM-CNL-CVT. El monto no se guarda: es derivado (docs/modelo/comercial.md, «CompraVenta»)."""

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

    class MotivoCancelacion(models.TextChoices):
        """MD-130: la lista cerrada de motivos de COM-CNL-CVT (paso 5)."""

        CLIENTE_DESISTIO = "cliente_desistio", "El cliente desistió"
        CLIENTE_NO_RETIRO = "cliente_no_retiro", "El cliente no retiró"
        OTRO = "otro", "Otro"

    estado_venta = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ABIERTA)
    fecha_pactada_venta = models.DateField()  # igual o posterior a la de hoy al registrar
    fecha_concrecion_venta = models.DateField(null=True, blank=True)  # la carga COM-06a
    # MD-130 (COM-05b): los carga solo COM-CNL-CVT; una venta que queda «cancelada» porque el cliente rechazó todo (COM-DCD-FLT) no los tiene.
    motivo_cancelacion_venta = models.CharField(max_length=20, choices=MotivoCancelacion.choices, null=True, blank=True)
    descripcion_cancelacion = models.CharField(max_length=300, blank=True, default="")  # opcional, también con «otro»
    fecha_cancelacion_venta = models.DateField(null=True, blank=True)  # la de hoy al cancelar
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
            # MD-130 (COM-05b): el motivo y la fecha de la cancelación van juntos; el motivo solo con una venta cancelada o concretada (la segunda,
            # cuando COM-08b cobre lo entregado, extensión 6a); la descripción, solo con motivo; y el motivo, de su lista cerrada.
            models.CheckConstraint(
                condition=Q(motivo_cancelacion_venta__isnull=True, fecha_cancelacion_venta__isnull=True)
                | Q(motivo_cancelacion_venta__isnull=False, fecha_cancelacion_venta__isnull=False),
                name="compra_venta_cancelacion_con_fecha",
            ),
            models.CheckConstraint(
                condition=Q(motivo_cancelacion_venta__isnull=True) | Q(estado_venta__in=["cancelada", "concretada"]),
                name="compra_venta_motivo_segun_estado",
            ),
            models.CheckConstraint(
                condition=Q(descripcion_cancelacion="") | Q(motivo_cancelacion_venta__isnull=False),
                name="compra_venta_descripcion_con_motivo",
            ),
            models.CheckConstraint(
                condition=Q(motivo_cancelacion_venta__isnull=True) | Q(motivo_cancelacion_venta__in=["cliente_desistio", "cliente_no_retiro", "otro"]),
                name="compra_venta_motivo_cancelacion_valido",
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
            # COM-04a (D-64 punto 6): `fecha_entrega_reserva` es nula si y solo si la reserva no tiene detalle (postcondición f de PROD-PNF-CSC).
            models.CheckConstraint(
                condition=(Q(fecha_entrega_reserva__isnull=True) & Q(detalle_venta__isnull=True) & Q(detalle_suministro__isnull=True))
                | (Q(fecha_entrega_reserva__isnull=False) & (Q(detalle_venta__isnull=False) | Q(detalle_suministro__isnull=False))),
                name="reserva_stock_fecha_segun_detalle",
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


class EnlaceCliente(models.Model):
    """El enlace de acceso temporal de un cliente sin cuenta (COM-04c, D-65; `docs/patrones/enlace_del_cliente.md`, `docs/modelo/comercial.md`). Tabla técnica, no una
    clase del dominio: es cómo el código cumple «uso único», «vencimiento» y «reemplazo» de COM-DCD-FLT. La base guarda SOLO el resumen SHA-256 del token
    (`core/enlaces.py`), nunca el token. Un cliente sin correo no tiene enlace. COM-06b suma el tipo `confirmacion_entrega` y su FK a `Entrega`. No se audita por su
    cuenta: el caso de uso que lo crea o lo usa lo pone en su registro (D-36)."""

    class Tipo(models.TextChoices):
        DECISION_FALTANTE = "decision_faltante", "Decisión de faltante"

    class Estado(models.TextChoices):
        VIGENTE = "vigente", "Vigente"
        USADO = "usado", "Usado"
        REEMPLAZADO = "reemplazado", "Reemplazado"
        ANULADO = "anulado", "Anulado"
        VENCIDO = "vencido", "Vencido"

    class EstadoEnvio(models.TextChoices):
        ENVIADO = "enviado", "Enviado"
        PENDIENTE_ENVIO = "pendiente_envio", "No se pudo enviar"

    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.DECISION_FALTANTE)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="enlaces")
    compra_venta = models.ForeignKey(CompraVenta, null=True, blank=True, on_delete=models.PROTECT, related_name="enlaces")
    token_resumen = models.CharField(max_length=64, unique=True)
    fecha_creacion = models.DateTimeField(default=timezone.now, editable=False)
    # Sirve hasta el final de ese día (D-65 punto 4). Faltante: la `fecha_pendiente_decision` más reciente de los detalles pendientes + `dias_vigencia_enlace_faltante`.
    fecha_vencimiento = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.VIGENTE)
    fecha_uso = models.DateTimeField(null=True, blank=True)
    # Nulo hasta que se intenta el envío (el correo sale fuera de la transacción, D-65 punto 6).
    estado_envio = models.CharField(max_length=20, choices=EstadoEnvio.choices, null=True, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Enlace del cliente"
        verbose_name_plural = "Enlaces del cliente"
        constraints = [
            # D-65 punto 5: a lo sumo un enlace vigente por venta y tipo.
            models.UniqueConstraint(fields=["compra_venta", "tipo"], condition=Q(estado="vigente"), name="enlace_cliente_un_vigente_por_venta_y_tipo"),
            models.CheckConstraint(condition=Q(estado__in=["vigente", "usado", "reemplazado", "anulado", "vencido"]), name="enlace_cliente_estado_valido"),
            models.CheckConstraint(condition=Q(tipo__in=["decision_faltante"]), name="enlace_cliente_tipo_valido"),
            models.CheckConstraint(
                condition=Q(estado_envio__isnull=True) | Q(estado_envio__in=["enviado", "pendiente_envio"]), name="enlace_cliente_estado_envio_valido"
            ),
            # Modelo, «EnlaceCliente»: usado <=> fecha de uso.
            models.CheckConstraint(
                condition=(Q(estado="usado") & Q(fecha_uso__isnull=False)) | (~Q(estado="usado") & Q(fecha_uso__isnull=True)),
                name="enlace_cliente_usado_con_fecha_de_uso",
            ),
            # Modelo, «EnlaceCliente»: decision_faltante => compra_venta no nula.
            models.CheckConstraint(condition=~Q(tipo="decision_faltante") | Q(compra_venta__isnull=False), name="enlace_cliente_faltante_con_venta"),
        ]

    def __str__(self):
        """«Enlace de CV-0044 (vigente)»."""
        return f"Enlace de {self.compra_venta.codigo if self.compra_venta_id else self.tipo} ({self.estado})"


class AlertaComercial(models.Model):
    """Tabla de vínculo entre una alerta de `maestros` y su origen comercial (D-63, T-01; regla A2 de D-37: `Alerta` no conoce a `comercial`).
    Una FK nula por cada origen posible y **exactamente una** cargada. COM-03b crea `suministro` y `detalle_suministro`; COM-04 suma `partida`,
    COM-05a1 `entrega` y COM-06a `solicitud`, cada una reescribiendo la restricción. La crea el mismo servicio que crea la alerta, en la misma
    transacción. Las alertas que se resuelven solas se encuentran por esta tabla, nunca por el texto de la descripción."""

    alerta = models.OneToOneField("maestros.Alerta", on_delete=models.PROTECT, related_name="vinculo_comercial")
    suministro = models.ForeignKey(Suministro, null=True, blank=True, on_delete=models.PROTECT, related_name="alertas")  # MD-122 (COM-07b)
    detalle_suministro = models.ForeignKey(
        DetalleSuministro, null=True, blank=True, on_delete=models.PROTECT, related_name="alertas"
    )  # MD-133
    fecha_periodo = models.DateField(null=True, blank=True)  # el período de la alerta MD-133
    cantidad_sin_cubrir = models.PositiveIntegerField(null=True, blank=True)  # se actualiza en cada intento de la pre-reserva (D-63, punto 3)
    # COM-04b (MD-134, D-64 punto 10): «partida por vencer». La FK vive acá (regla A2 de D-37: `StockCosechado` es de `produccion`, nivel menor).
    partida = models.ForeignKey(StockCosechado, null=True, blank=True, on_delete=models.PROTECT, related_name="alertas_comerciales")
    # COM-05a1 (MD-122, extensión 6a de COM-PNF-ENT, D-66 punto 10): «entrega sin transportista». La FK vive acá (regla A2 de D-37: `Entrega` es de `comercial`).
    entrega = models.ForeignKey("Entrega", null=True, blank=True, on_delete=models.PROTECT, related_name="alertas")
    # COM-06a (R054, D-68 punto 5): la alerta de una discrepancia de entrega (y, en COM-06b, de una queja). Una sola alerta por solicitud.
    solicitud = models.ForeignKey("SolicitudRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="alertas")

    class Meta:
        verbose_name = "Alerta comercial"
        verbose_name_plural = "Alertas comerciales"
        constraints = [
            # Exactamente una FK de origen cargada (D-63, punto 1): `suministro`, `detalle_suministro`, `partida` (COM-04), `entrega` (COM-05a1) o `solicitud` (COM-06a).
            models.CheckConstraint(
                condition=(
                    Q(suministro__isnull=False) & Q(detalle_suministro__isnull=True) & Q(partida__isnull=True) & Q(entrega__isnull=True) & Q(solicitud__isnull=True)
                )
                | (Q(suministro__isnull=True) & Q(detalle_suministro__isnull=False) & Q(partida__isnull=True) & Q(entrega__isnull=True) & Q(solicitud__isnull=True))
                | (Q(suministro__isnull=True) & Q(detalle_suministro__isnull=True) & Q(partida__isnull=False) & Q(entrega__isnull=True) & Q(solicitud__isnull=True))
                | (Q(suministro__isnull=True) & Q(detalle_suministro__isnull=True) & Q(partida__isnull=True) & Q(entrega__isnull=False) & Q(solicitud__isnull=True))
                | (Q(suministro__isnull=True) & Q(detalle_suministro__isnull=True) & Q(partida__isnull=True) & Q(entrega__isnull=True) & Q(solicitud__isnull=False)),
                name="alerta_comercial_un_solo_origen",
            ),
            models.UniqueConstraint(fields=["solicitud"], condition=Q(solicitud__isnull=False), name="alerta_comercial_una_por_solicitud"),
            # detalle_suministro no nulo <=> fecha_periodo y cantidad_sin_cubrir no nulos.
            models.CheckConstraint(
                condition=(
                    Q(detalle_suministro__isnull=False) & Q(fecha_periodo__isnull=False) & Q(cantidad_sin_cubrir__isnull=False)
                )
                | (Q(detalle_suministro__isnull=True) & Q(fecha_periodo__isnull=True) & Q(cantidad_sin_cubrir__isnull=True)),
                name="alerta_comercial_periodo_completo",
            ),
        ]

    def __str__(self):
        """«Alerta comercial #12»."""
        return f"Alerta comercial #{self.pk}"


# ---- COM-05a1: Entrega y DetalleEntrega (docs/modelo/comercial.md; D-66) ----


class EntregaQuerySet(models.QuerySet):
    """QuerySet de entregas con el alcance por usuario en un único lugar (D-28; docs/modelo/comercial.md, «Entrega», «Alcance»)."""

    def en_alcance_de(self, actor):
        """Entregas que ``actor`` consulta: el Gerente activo, todas; el Vendedor activo, las de sus contratos; el Agrónomo activo, las de sus invernaderos a cargo
        (solo para el envasado, COM-05a2); el Transportista activo, las suyas (COM-06a); cualquier otro actor, o una cuenta inactiva, ninguna."""
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        rol = rol_de(actor)
        if rol == Usuario.Rol.GERENTE:
            return self.all()
        if rol == Usuario.Rol.VENDEDOR:
            return self.filter(contrato_entrega__vendedor_id=actor.pk)
        if rol == Usuario.Rol.AGRONOMO:
            return self.filter(invernadero__agronomo_id=actor.pk)
        if rol == Usuario.Rol.TRANSPORTISTA:
            return self.filter(transportista_id=actor.pk)
        return self.none()


class Entrega(OrdenTrabajo):
    """Entrega del producto al cliente, con envío (con Transportista) o con retiro en el invernadero (sin Transportista). Hija multitabla de
    `produccion.OrdenTrabajo` (``tipo_orden = entrega``; D-50, D-66 punto 2), sin `ConCapataz` (D-53). Sale de un único invernadero (el de la orden) y la planifica
    siempre InfoPonia (``agronomo`` nulo). ``contrato``, ``modalidad_entrega`` y ``direccion_destino`` no están en el modelo: son desnormalizaciones del código (D-66
    punto 3) que una sola función escribe al crearla (`entregas._crear_entrega`) y no cambian. Su clave es ``ordentrabajo_ptr``."""

    class Modalidad(models.TextChoices):
        """La misma lista que `CompraVenta.Modalidad`; un suministro siempre es «envío»."""

        RETIRO = "retiro", "Retiro en invernadero"
        ENVIO = "envio", "Envío a domicilio"

    class Confirmacion(models.TextChoices):
        """Solo en una entrega de suministro (regla 15 de 8.12); la cambia COM-CNF-ENT (COM-06)."""

        NO_CONFIRMADO = "no_confirmado", "No confirmada"
        CONFIRMADO = "confirmado", "Confirmada"

    class EstadoDelAviso(models.TextChoices):
        """Resultado del último correo al cliente (D-66 punto 12)."""

        ENVIADO = "enviado", "Enviado"
        PENDIENTE_ENVIO = "pendiente_envio", "Pendiente de envío"
        SIN_CORREO = "sin_correo", "Sin correo"

    # DIFERENCIA CON LA DOCUMENTACIÓN: el modelo lo llama `contrato`, pero choca con la relación inversa `OrigenDocumento.contrato` (la hija `Contrato`); se llama `contrato_entrega`, como `tipo_orden` y `tipo_contrato` (D-81).
    contrato_entrega = models.ForeignKey(Contrato, on_delete=models.PROTECT, related_name="entregas")
    modalidad_entrega = models.CharField(max_length=10, choices=Modalidad.choices)
    # Con envío: la dirección de envío de la venta (R146) o la del detalle de suministro (R125). Con retiro: nula (el destino es el invernadero, R151).
    direccion_destino = models.ForeignKey(Direccion, null=True, blank=True, on_delete=models.PROTECT, related_name="entregas_con_destino")
    transportista = models.ForeignKey(Transportista, null=True, blank=True, on_delete=models.PROTECT, related_name="entregas")  # R122
    estado_confirmacion_cliente = models.CharField(max_length=15, choices=Confirmacion.choices, null=True, blank=True)
    estado_aviso_cliente = models.CharField(max_length=20, choices=EstadoDelAviso.choices, null=True, blank=True)
    recordatorio_para = models.DateField(null=True, blank=True)  # la fecha programada por la que ya salió el recordatorio único (postcondición k)
    aviso_atrasada_para = models.DateField(null=True, blank=True)  # la fecha programada por la que ya salió el aviso de atrasada (PCU, sección 8)
    # COM-06a (D-68 punto 7): se fijan al concretar. El total es la suma de los `monto_pagar` de las líneas; el vencimiento, solo en un suministro (MD-124, MD-132).
    monto_total_entrega = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    fecha_vencimiento_pago = models.DateField(null=True, blank=True)

    objects = EntregaQuerySet.as_manager()

    class Meta:
        verbose_name = "Entrega"
        verbose_name_plural = "Entregas"
        indexes = [
            models.Index(fields=["transportista"], condition=Q(transportista__isnull=False), name="entrega_transportista_idx"),
            models.Index(fields=["contrato_entrega"], name="entrega_contrato_idx"),
        ]
        constraints = [
            # Con envío, dirección de destino; con retiro, ninguna (R151: el destino es el invernadero). Cubre también la lista de modalidades.
            models.CheckConstraint(
                condition=(Q(modalidad_entrega="envio") & Q(direccion_destino__isnull=False))
                | (Q(modalidad_entrega="retiro") & Q(direccion_destino__isnull=True)),
                name="entrega_destino_segun_modalidad",
            ),
            # Regla 25 de 8.8: un retiro no tiene transportista.
            models.CheckConstraint(
                condition=~Q(modalidad_entrega="retiro") | Q(transportista__isnull=True), name="entrega_retiro_sin_transportista"
            ),
            models.CheckConstraint(
                condition=Q(aviso_atrasada_para__isnull=True) | Q(transportista__isnull=False), name="entrega_atrasada_avisada_con_transportista"
            ),
            models.CheckConstraint(
                condition=Q(estado_confirmacion_cliente__isnull=True) | Q(estado_confirmacion_cliente__in=["no_confirmado", "confirmado"]),
                name="entrega_confirmacion_valida",
            ),
            models.CheckConstraint(
                condition=Q(estado_aviso_cliente__isnull=True) | Q(estado_aviso_cliente__in=["enviado", "pendiente_envio", "sin_correo"]),
                name="entrega_aviso_valido",
            ),
            # COM-06a: el total de una entrega concretada no es negativo (que esté no nulo ⇔ «concretada» lo verifica `verificar_invariantes_de_entregas`: el estado está en otra tabla).
            models.CheckConstraint(
                condition=Q(monto_total_entrega__isnull=True) | Q(monto_total_entrega__gte=0), name="entrega_monto_total_no_negativo"
            ),
        ]

    @property
    def es_retiro(self):
        """True si la entrega es un retiro en el invernadero (sin transportista)."""
        return self.modalidad_entrega == self.Modalidad.RETIRO


class DetalleEntrega(models.Model):
    """Una línea de la entrega: satisface un detalle de venta o un período de un detalle de suministro (C4) y dice qué reservas entrega (R150). Su cantidad planificada
    no se guarda: es la suma de la cantidad cubierta de sus reservas no liberadas (D-66 punto 4). Una línea cuyas reservas quedaron todas liberadas queda en 0 y se da por
    quitada: nunca se borra. ``cant_entregada`` y ``monto_pagar`` quedan vacíos hasta que COM-06a concreta la entrega."""

    entrega = models.ForeignKey(Entrega, on_delete=models.PROTECT, related_name="lineas")  # R120
    detalle_venta = models.ForeignKey(DetalleVenta, null=True, blank=True, on_delete=models.PROTECT, related_name="lineas_de_entrega")  # R147
    detalle_suministro = models.ForeignKey(DetalleSuministro, null=True, blank=True, on_delete=models.PROTECT, related_name="lineas_de_entrega")  # R121
    fecha_periodo = models.DateField(null=True, blank=True)  # la fecha del período del detalle de suministro; nula en una línea de venta
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)  # al planificar; COM-06a lo recalcula con la fecha real en un suministro
    cant_entregada = models.PositiveIntegerField(null=True, blank=True)  # nula hasta concretar (COM-06a)
    monto_pagar = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  # nulo hasta concretar (COM-06a)
    # COM-06a (D-68 punto 7; no están en el modelo): después de concretar, la planificada ya no se puede recalcular de las reservas (las de un detalle rechazado quedan «liberadas»).
    cant_perdida = models.PositiveIntegerField(null=True, blank=True)  # lo que no llegó en buen estado (la merma «daño en la entrega»)
    cant_devuelta = models.PositiveIntegerField(null=True, blank=True)  # lo que llegó y volvió a la cámara
    reservas =models.ManyToManyField(ReservaStock, related_name="lineas_de_entrega")  # R150

    class Meta:
        verbose_name = "Línea de entrega"
        verbose_name_plural = "Líneas de entrega"
        constraints = [
            # C4: exactamente uno de `detalle_venta` y `detalle_suministro`.
            models.CheckConstraint(
                condition=(Q(detalle_venta__isnull=False) & Q(detalle_suministro__isnull=True))
                | (Q(detalle_venta__isnull=True) & Q(detalle_suministro__isnull=False)),
                name="linea_entrega_venta_o_suministro",
            ),
            models.CheckConstraint(
                condition=(Q(detalle_suministro__isnull=False) & Q(fecha_periodo__isnull=False))
                | (Q(detalle_suministro__isnull=True) & Q(fecha_periodo__isnull=True)),
                name="linea_entrega_periodo_segun_detalle",
            ),
            models.UniqueConstraint(fields=["entrega", "detalle_venta"], name="linea_entrega_un_detalle_de_venta_por_entrega"),
            models.UniqueConstraint(
                fields=["entrega", "detalle_suministro", "fecha_periodo"], name="linea_entrega_un_periodo_por_entrega"
            ),
            models.CheckConstraint(condition=Q(precio_unitario__gt=0), name="linea_entrega_precio_positivo"),
            models.CheckConstraint(
                condition=Q(cant_entregada__isnull=True) | Q(cant_entregada__gte=0), name="linea_entrega_entregada_no_negativa"
            ),
            # COM-06a: la concreción de una línea se carga entera (entregada, perdida, devuelta y monto) o no se carga. Que entregada + perdida + devuelta sea la planificada lo
            # verifica el servicio (la planificada sale de las reservas) y el invariante.
            models.CheckConstraint(
                condition=(
                    Q(cant_entregada__isnull=True) & Q(cant_perdida__isnull=True) & Q(cant_devuelta__isnull=True) & Q(monto_pagar__isnull=True)
                )
                | (
                    Q(cant_entregada__isnull=False) & Q(cant_perdida__isnull=False) & Q(cant_devuelta__isnull=False) & Q(monto_pagar__isnull=False)
                ),
                name="linea_entrega_concrecion_completa",
            ),
            models.CheckConstraint(condition=Q(cant_perdida__isnull=True) | Q(cant_perdida__gte=0), name="linea_entrega_perdida_no_negativa"),
            models.CheckConstraint(condition=Q(cant_devuelta__isnull=True) | Q(cant_devuelta__gte=0), name="linea_entrega_devuelta_no_negativa"),
            models.CheckConstraint(condition=Q(monto_pagar__isnull=True) | Q(monto_pagar__gte=0), name="linea_entrega_monto_no_negativo"),
        ]

    def __str__(self):
        """«Línea de entrega #N» (texto de la auditoría, D-36)."""
        return f"Línea de entrega #{self.pk}"


# ---- COM-06a: PagoCliente, IntentoFallido, SolicitudRevision, DiscrepanciaEntrega y LineaDiscrepancia (docs/modelo/comercial.md; D-68 puntos 4 a 6) ----


class PagoCliente(OrigenDocumento):
    """El pago que hace el cliente (MD-136). Hija directa de `contabilidad.OrigenDocumento` (``TIPO_DE_ORIGEN = pago_cliente``), como `MovimientoStock` (D-52). En COM-06a solo lo crea
    la concreción de la última entrega de una **compra-venta** (R117, postcondición k de COM-CNC-ENT): COM-08a suma el de las entregas de suministro y reescribe C7 como el {xor}
    del modelo; COM-08b, la anulación. No origina asiento propio en una compra-venta (regla 32 de 8.6). Su clave es ``origendocumento_ptr``."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.PAGO_CLIENTE

    class Medio(models.TextChoices):
        """Regla 15 de 8.13 (11a de COM-CNC-ENT): el efectivo va a Caja y los demás a Banco c/c, en el asiento (fuera de la ronda, D-57)."""

        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"
        TARJETA_DEBITO = "tarjeta_debito", "Tarjeta de débito"
        TARJETA_CREDITO = "tarjeta_credito", "Tarjeta de crédito"

    class Estado(models.TextChoices):
        """MD-136: un pago anulado (COM-08b) conserva sus datos."""

        VIGENTE = "vigente", "Vigente"
        ANULADO = "anulado", "Anulado"

    medio_pago = models.CharField(max_length=20, choices=Medio.choices)
    fecha_pago = models.DateField(default=timezone.localdate)
    monto_pagado = models.DecimalField(max_digits=14, decimal_places=2)  # en una compra-venta, el total de la venta
    estado_pago = models.CharField(max_length=10, choices=Estado.choices, default=Estado.VIGENTE)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="pagos")  # R116
    # R117. C7 (COM-06a): no nula; COM-08a la reescribe con el {xor} con el cobro de suministro.
    compra_venta = models.ForeignKey(CompraVenta, null=True, blank=True, on_delete=models.PROTECT, related_name="pagos")

    class Meta:
        verbose_name = "Pago del cliente"
        verbose_name_plural = "Pagos de clientes"
        constraints = [
            models.CheckConstraint(condition=Q(monto_pagado__gt=0), name="pago_cliente_monto_positivo"),
            models.CheckConstraint(condition=Q(medio_pago__in=["efectivo", "transferencia", "tarjeta_debito", "tarjeta_credito"]), name="pago_cliente_medio_valido"),
            models.CheckConstraint(condition=Q(estado_pago__in=["vigente", "anulado"]), name="pago_cliente_estado_valido"),
            models.CheckConstraint(condition=Q(compra_venta__isnull=False), name="pago_cliente_c7_con_compra_venta"),
            # Una venta se paga una vez: a lo sumo un pago vigente (COM-08b puede dejar uno anulado y registrar el correcto).
            models.UniqueConstraint(fields=["compra_venta"], condition=Q(estado_pago="vigente"), name="pago_cliente_un_vigente_por_venta"),
        ]

    def __str__(self):
        """«Pago #12» (texto de la auditoría, D-36)."""
        return f"Pago #{self.pk}"


class IntentoFallido(models.Model):
    """El registro de una entrega que no se pudo realizar (COM-CNC-ENT, extensión 4a, y COM-FIN-RUT, regla 1). No es una clase del modelo (D-68, punto 6): lo leen COM-RSV-QJA,
    la ficha de la entrega y COM-ATN-ENR. Se audita como parte del registro del caso de uso, no por su cuenta."""

    class Motivo(models.TextChoices):
        """La lista de 4a («Lista de tecnología»)."""

        CLIENTE_AUSENTE = "cliente_ausente", "Cliente ausente"
        DOMICILIO_CERRADO = "domicilio_cerrado", "Domicilio cerrado"
        DIRECCION_INCORRECTA = "direccion_incorrecta", "Dirección incorrecta"
        OTRO = "otro", "Otro"

    entrega = models.ForeignKey(Entrega, on_delete=models.PROTECT, related_name="intentos_fallidos")
    transportista = models.ForeignKey(Transportista, on_delete=models.PROTECT, related_name="intentos_fallidos")  # el que la tenía asignada al intentar
    fecha_hora = models.DateTimeField(default=timezone.now)
    fecha_programada = models.DateField()  # la que tenía la entrega al intentar (la nueva es el día siguiente)
    motivo = models.CharField(max_length=20, choices=Motivo.choices)
    descripcion = models.CharField(max_length=300, blank=True, default="")  # opcional, sin espacios al borde

    class Meta:
        verbose_name = "Intento fallido"
        verbose_name_plural = "Intentos fallidos"
        indexes = [models.Index(fields=["entrega", "fecha_hora"], name="intento_fallido_entrega_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(motivo__in=["cliente_ausente", "domicilio_cerrado", "direccion_incorrecta", "otro"]), name="intento_fallido_motivo_valido"
            ),
        ]

    def __str__(self):
        """«Intento fallido #3» (texto de la auditoría, D-36)."""
        return f"Intento fallido #{self.pk}"


class SolicitudRevision(OrigenDocumento):
    """Solicitud de revisión: abstracta en el modelo, **padre multitabla concreto** en el código (D-68 punto 5, como `OrdenTrabajo`, D-50). Hija directa de `OrigenDocumento`
    (``TIPO_DE_ORIGEN = solicitud_revision``: una solicitud aceptada origina el asiento de su indemnización, fuera de la ronda, D-57). Hijas: `DiscrepanciaEntrega` (COM-06a) y `Queja`
    (COM-06b). Nace «pendiente», sin Gerente, fecha de resolución ni monto (COM-07 los carga). ``entrega`` no está en el modelo (R129 se eliminó: se deduce de los detalles): la guarda
    el código para exigir en la base una sola discrepancia por entrega (regla 3 de 8.14); la escribe una sola función (`solicitudes.crear_solicitud`). Su clave es ``origendocumento_ptr``."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.SOLICITUD_REVISION

    class Tipo(models.TextChoices):
        """Lo fija la hija al crearse; las listas parten del padre y usan el tipo."""

        DISCREPANCIA = "discrepancia", "Discrepancia"
        QUEJA = "queja", "Queja"

    class Estado(models.TextChoices):
        """Nace «pendiente»; lo cambia COM-07."""

        PENDIENTE = "pendiente", "Pendiente de revisión"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"

    # El nombre `tipo` ya es del padre (`OrigenDocumento`): el discriminador se llama `tipo_solicitud` (como `tipo_contrato` y `tipo_orden`, D-81).
    tipo_solicitud = models.CharField(max_length=15, choices=Tipo.choices)
    numero = models.PositiveIntegerField(unique=True)  # de la secuencia `comercial_solicitud_numero_seq`; código visible «SR-0012»
    fecha_solicitud = models.DateField(default=timezone.localdate)
    estado_solicitud = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    fecha_resolucion = models.DateField(null=True, blank=True)  # COM-07
    observaciones_resolucion = models.TextField(blank=True, default="")  # COM-07 (obligatoria al rechazar)
    monto_indemnizacion = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  # COM-07a, al aceptar
    gerente = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="solicitudes_revisadas")  # R009 (COM-07)
    entrega = models.ForeignKey(Entrega, on_delete=models.PROTECT, related_name="solicitudes")

    class Meta:
        verbose_name = "Solicitud de revisión"
        verbose_name_plural = "Solicitudes de revisión"
        constraints = [
            models.CheckConstraint(condition=Q(tipo_solicitud__in=["discrepancia", "queja"]), name="solicitud_tipo_valido"),
            models.CheckConstraint(condition=Q(estado_solicitud__in=["pendiente", "aceptada", "rechazada"]), name="solicitud_estado_valido"),
            # Regla 3 de 8.14: una sola discrepancia por entrega.
            models.UniqueConstraint(fields=["entrega"], condition=Q(tipo_solicitud="discrepancia"), name="solicitud_una_discrepancia_por_entrega"),
            # Pendiente ⇔ sin fecha de resolución ⇔ sin Gerente.
            models.CheckConstraint(
                condition=(Q(estado_solicitud="pendiente") & Q(fecha_resolucion__isnull=True) & Q(gerente__isnull=True))
                | (~Q(estado_solicitud="pendiente") & Q(fecha_resolucion__isnull=False) & Q(gerente__isnull=False)),
                name="solicitud_pendiente_sin_resolucion",
            ),
            # Aceptada ⇒ monto no nulo y >= 0; monto no nulo ⇒ aceptada.
            models.CheckConstraint(
                condition=~Q(estado_solicitud="aceptada") | (Q(monto_indemnizacion__isnull=False) & Q(monto_indemnizacion__gte=0)),
                name="solicitud_aceptada_con_monto",
            ),
            models.CheckConstraint(
                condition=Q(monto_indemnizacion__isnull=True) | Q(estado_solicitud="aceptada"), name="solicitud_monto_solo_si_aceptada"
            ),
        ]

    @property
    def codigo(self):
        """``SR-0012``: el número que ven el Gerente y el cliente."""
        return f"SR-{self.numero:04d}"

    def __str__(self):
        """El código (texto de ``referencia()`` en la auditoría, D-36)."""
        return self.codigo


class DiscrepanciaEntrega(SolicitudRevision):
    """Discrepancia de entrega (``tipo_solicitud = discrepancia``), sin atributos propios (ronda 19). La crea la concreción de una entrega de suministro cuando uno o más detalles quedan
    por debajo de la cantidad mínima de su cláusula (extensión 14c de COM-CNC-ENT; regla 12 de 8.13). Una por entrega, con una línea por detalle. Su clave es ``solicitudrevision_ptr``."""

    def save(self, *args, **kwargs):
        """Fija el discriminador: lo decide la hija y nunca cambia."""
        self.tipo_solicitud = SolicitudRevision.Tipo.DISCREPANCIA
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Discrepancia de entrega"
        verbose_name_plural = "Discrepancias de entrega"


class LineaDiscrepancia(models.Model):
    """Una línea de la discrepancia: un detalle de la entrega que quedó por debajo de la cantidad mínima de su cláusula (R162, R163). Las dos cantidades son copias fijas, por si
    la cláusula cambia después. ``monto_indemnizacion_linea`` lo carga COM-07a al aceptar."""

    discrepancia = models.ForeignKey(DiscrepanciaEntrega, on_delete=models.PROTECT, related_name="lineas")  # R162
    detalle_entrega = models.OneToOneField(DetalleEntrega, on_delete=models.PROTECT, related_name="linea_de_discrepancia")  # R163
    cantidad_entregada = models.PositiveIntegerField()  # copia fija de `cant_entregada` de la línea
    cantidad_minima_estipulada = models.PositiveIntegerField()  # copia fija de la mínima de la cláusula del suministrante del detalle
    monto_indemnizacion_linea = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  # COM-07a

    class Meta:
        verbose_name = "Línea de discrepancia"
        verbose_name_plural = "Líneas de discrepancia"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_entregada__lt=F("cantidad_minima_estipulada")), name="linea_discrepancia_bajo_el_minimo"),
            models.CheckConstraint(condition=Q(cantidad_minima_estipulada__gte=1), name="linea_discrepancia_minima_positiva"),
            models.CheckConstraint(
                condition=Q(monto_indemnizacion_linea__isnull=True) | Q(monto_indemnizacion_linea__gte=0), name="linea_discrepancia_monto_no_negativo"
            ),
        ]

    def __str__(self):
        """«Línea de discrepancia #5» (texto de la auditoría, D-36)."""
        return f"Línea de discrepancia #{self.pk}"
