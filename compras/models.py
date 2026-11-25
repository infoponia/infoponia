# Modelos de `compras` (nivel 6 de D-37): Proveedor (CMP-01), desde CMP-02a Pedido, DetallePedido, InvitacionPedido, EnlaceProveedor,
# Cotizacion y DetalleCotizacion, desde CMP-03, OrdenCompra y DetalleOrdenCompra, desde CMP-04, Recepcion, DetalleRecepcion, DetalleRecepcionMovimiento, ReclamoProveedor,
# InconvenienteRecepcion y AlertaCompras, desde CMP-05, Pago y, desde CMP-06, CorreccionRecepcion y DetalleCorreccionRecepcion. Fuente: docs/modelo/compras.md (MD-121 a MD-130 de A0; D-87, D-88, D-89, D-90 y D-91). Nunca se borra una fila de
# negocio: hay estados. A2 de D-37: toda FK o M2M se declara acá, en la app de nivel mayor. Ningún import de `comercial` ni de
# `produccion` (A1).

from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce, Round
from django.utils import timezone

from compras.precios import precio_unitario_para_mostrar
from contabilidad.models import OrigenDocumento
from core.models import Agronomo, Gerente, Usuario, rol_de
from core.validadores import validar_telefono
from inventario.models import InsumoInvernadero, MovimientoInsumo, TipoInsumo
from maestros.validadores import formatear_cuit

# Roles que ven a todos los proveedores (regla 1 de CMP-CNS-PRV): el Gerente y el Agrónomo activos.
ROLES_QUE_VEN_PROVEEDORES = (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO)


class ProveedorQuerySet(models.QuerySet):
    """El alcance por usuario de los proveedores, en un único lugar (CLAUDE.md, «Arquitectura»)."""

    def en_alcance_de(self, actor):
        """Regla 1 de CMP-CNS-PRV: el Gerente y el Agrónomo activos ven todos los proveedores (activos e inactivos);
        cualquier otra cuenta, una cuenta inactiva o ``None``, ninguno."""
        if actor is None or not actor.is_active or rol_de(actor) not in ROLES_QUE_VEN_PROVEEDORES:
            return self.none()
        return self.all()


class Proveedor(models.Model):
    """Persona u organización externa que cotiza y vende insumos (docs/modelo/compras.md, «Proveedor»). No tiene cuenta:
    participa por enlace enviado por correo, y no tiene dirección (X7). Es una persona jurídica (razón social) o física
    (nombre y apellido), igual que ``Cliente``. El CUIT es único entre todos, activos e inactivos (H14)."""

    class Tipo(models.TextChoices):
        """Técnico (no está en el modelo de dominio): razón social **o** nombre y apellido (regla 1 de CMP-ALT-PRV)."""

        JURIDICA = "juridica", "Persona jurídica"
        FISICA = "fisica", "Persona física"

    class Estado(models.TextChoices):
        """Baja lógica: un proveedor inactivo conserva su historial y se reactiva con el alta (regla 4 de CMP-BAJ-PRV)."""

        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    tipo_proveedor = models.CharField("tipo de proveedor", max_length=10, choices=Tipo.choices)
    # MD-122, H14: 11 dígitos, sin guiones; se valida con ``maestros.validadores.validar_cuit`` (D-58) y se muestra con ``formatear_cuit``.
    cuit_proveedor = models.CharField(
        "CUIT",
        max_length=11,
        validators=[RegexValidator(r"^\d{11}$", "El CUIT tiene 11 dígitos.", code="cuit_formato")],
    )
    razon_social_proveedor = models.CharField("razón social", max_length=150, blank=True)
    nombre_proveedor = models.CharField("nombre", max_length=80, blank=True)
    apellido_proveedor = models.CharField("apellido", max_length=80, blank=True)
    # El correo es obligatorio: el proveedor solo recibe pedidos y órdenes por correo (regla 1 de CMP-ALT-PRV).
    email_proveedor = models.EmailField("correo electrónico", max_length=254)
    # Opcional (P5, MD-130). D-21 y D-28: 25 caracteres como máximo.
    telefono_proveedor = models.CharField("teléfono", max_length=25, blank=True, validators=[validar_telefono])
    estado_proveedor = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    # MD-121: «se especializa en» (0..* – 0..*). Una categoría dada de baja conserva el vínculo (regla 4 de CMP-MOD-PRV).
    especialidades = models.ManyToManyField(
        TipoInsumo, blank=True, related_name="proveedores_especializados", verbose_name="categorías de insumos"
    )

    objects = ProveedorQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        constraints = [
            # Regla 2 de CMP-ALT-PRV (H14): CUIT único entre todos, activos e inactivos. Respalda al servicio en el alta concurrente.
            models.UniqueConstraint(fields=["cuit_proveedor"], name="proveedor_cuit_unico"),
            models.CheckConstraint(condition=Q(cuit_proveedor__regex=r"^[0-9]{11}$"), name="proveedor_cuit_11_digitos"),
            models.CheckConstraint(condition=Q(estado_proveedor__in=["activo", "inactivo"]), name="proveedor_estado_valido"),
            models.CheckConstraint(condition=Q(tipo_proveedor__in=["juridica", "fisica"]), name="proveedor_tipo_valido"),
            # Regla 1 de CMP-ALT-PRV: jurídica ⇒ razón social y sin nombre ni apellido; física ⇒ nombre y apellido y sin razón
            # social (la misma restricción por tipo que ``Cliente``).
            models.CheckConstraint(
                condition=(
                    Q(tipo_proveedor="juridica")
                    & ~Q(razon_social_proveedor="")
                    & Q(nombre_proveedor="")
                    & Q(apellido_proveedor="")
                )
                | (
                    Q(tipo_proveedor="fisica")
                    & Q(razon_social_proveedor="")
                    & ~Q(nombre_proveedor="")
                    & ~Q(apellido_proveedor="")
                ),
                name="proveedor_datos_segun_tipo",
            ),
        ]

    def __str__(self):
        """La razón social o «Nombre Apellido»: es el texto que guarda la auditoría al referenciarlo (D-36)."""
        return self.nombre_para_mostrar

    @property
    def nombre_para_mostrar(self):
        """La razón social si es una organización; «Nombre Apellido» si es una persona."""
        if self.tipo_proveedor == self.Tipo.JURIDICA:
            return self.razon_social_proveedor
        return f"{self.nombre_proveedor} {self.apellido_proveedor}".strip()

    @property
    def cuit_formateado(self):
        """El CUIT para mostrarlo, «30-71234567-1» (D-58)."""
        return formatear_cuit(self.cuit_proveedor)

    @property
    def activo(self):
        """True si el proveedor está activo."""
        return self.estado_proveedor == self.Estado.ACTIVO


# ---------------------------------------------------------------------------------------------------------------------------------
# Pedidos de cotización y cotizaciones (CMP-02a). Fuente: docs/modelo/compras.md («Pedido» a «DetalleCotizacion»).
# ---------------------------------------------------------------------------------------------------------------------------------

DOS_DECIMALES = Decimal("0.01")


class PedidoQuerySet(models.QuerySet):
    """El alcance por usuario de los pedidos, en un único lugar (CLAUDE.md, «Arquitectura»), y su monto estimado."""

    def en_alcance_de(self, actor):
        """Regla 1 de CMP-CNS-PED: el Agrónomo activo ve los pedidos que él realizó; el Gerente activo, todos (en solo lectura);
        cualquier otra cuenta, una cuenta inactiva o ``None``, ninguno."""
        if actor is None or not actor.is_active:
            return self.none()
        rol = rol_de(actor)
        if rol == Usuario.Rol.GERENTE:
            return self.all()
        if rol == Usuario.Rol.AGRONOMO:
            return self.filter(agronomo_id=actor.pk)
        return self.none()

    def con_monto(self):
        """Anota ``monto_estimado``: Σ de cada subtotal (cantidad × precio de referencia copiado, redondeado a 2 decimales),
        como ``DetallePedido.subtotal``. Es una anotación de consulta, no una columna (D-89 punto 5)."""
        importe = models.DecimalField(max_digits=16, decimal_places=2)
        return self.annotate(
            monto_estimado=Coalesce(
                Sum(Round(F("detalles__cantidad_detalle") * F("detalles__precio_unitario_de_pedido"), 2), output_field=importe),
                Decimal("0.00"),
                output_field=importe,
            )
        )


class Pedido(models.Model):
    """Lo que el Agrónomo pide cotizar, para uno o varios de sus invernaderos (docs/modelo/compras.md, «Pedido»; R038). Nace
    «en cotización» y pasa a «cerrado» (CMP-03) o a «cancelado» (CMP-02b). El monto estimado es derivado (``con_monto``)."""

    class Estado(models.TextChoices):
        EN_COTIZACION = "en_cotizacion", "En cotización"
        CERRADO = "cerrado", "Cerrado"
        CANCELADO = "cancelado", "Cancelado"

    class Causa(models.TextChoices):
        """Técnico: responde «si fue automática» (CMP-CNS-PED regla 4). La usa CMP-02b."""

        MANUAL = "manual", "Cancelado por el Agrónomo"
        NADIE_COTIZO = "nadie_cotizo", "Nadie cotizó"
        SIN_COTIZACIONES_ELEGIBLES = "sin_cotizaciones_elegibles", "Sin cotizaciones elegibles"
        AGRONOMO_INACTIVO = "agronomo_inactivo", "Agrónomo inactivo"
        AGRONOMO_SIN_INVERNADERO = "agronomo_sin_invernadero", "Agrónomo sin el invernadero de destino"

    agronomo = models.ForeignKey(Agronomo, on_delete=models.PROTECT, related_name="pedidos")
    fecha_pedido = models.DateField("fecha del pedido")
    fecha_limite_cotizaciones = models.DateField("fecha límite de cotizaciones")
    estado_pedido = models.CharField(max_length=15, choices=Estado.choices, default=Estado.EN_COTIZACION)
    # MD-124: para «cerrado» y para «cancelado».
    fecha_cierre_pedido = models.DateField("fecha de cierre", null=True, blank=True)
    motivo_cancelacion = models.CharField("motivo de la cancelación", max_length=500, blank=True)
    causa_cancelacion = models.CharField(max_length=30, choices=Causa.choices, null=True, blank=True)
    # Técnicos de los pasos diarios 60 y 61 (D-87 punto 4): los hacen idempotentes. Los escribe CMP-03.
    aviso_vencimiento_dado = models.BooleanField(default=False)
    recordatorio_validez_para = models.DateField(null=True, blank=True)

    objects = PedidoQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        verbose_name = "Pedido de cotización"
        verbose_name_plural = "Pedidos de cotización"
        constraints = [
            models.CheckConstraint(
                condition=Q(estado_pedido__in=["en_cotizacion", "cerrado", "cancelado"]), name="pedido_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(causa_cancelacion__isnull=True)
                | Q(
                    causa_cancelacion__in=[
                        "manual",
                        "nadie_cotizo",
                        "sin_cotizaciones_elegibles",
                        "agronomo_inactivo",
                        "agronomo_sin_invernadero",
                    ]
                ),
                name="pedido_causa_valida",
            ),
            # Modelo, «Pedido»: cerrado o cancelado ⇔ fecha de cierre.
            models.CheckConstraint(
                condition=(Q(estado_pedido="en_cotizacion") & Q(fecha_cierre_pedido__isnull=True))
                | (Q(estado_pedido__in=["cerrado", "cancelado"]) & Q(fecha_cierre_pedido__isnull=False)),
                name="pedido_cierre_coherente_con_estado",
            ),
            # Modelo, «Pedido»: cancelado ⇔ causa.
            models.CheckConstraint(
                condition=(Q(estado_pedido="cancelado") & Q(causa_cancelacion__isnull=False))
                | (~Q(estado_pedido="cancelado") & Q(causa_cancelacion__isnull=True)),
                name="pedido_causa_coherente_con_estado",
            ),
            # Modelo, «Pedido»: causa manual ⇒ motivo no vacío (MD-124).
            models.CheckConstraint(
                condition=~Q(causa_cancelacion="manual") | ~Q(motivo_cancelacion=""), name="pedido_manual_con_motivo"
            ),
            # Regla «Fecha límite de cotizaciones» de CMP-RLZ-PED: como mínimo, el día siguiente al del pedido.
            models.CheckConstraint(
                condition=Q(fecha_limite_cotizaciones__gt=F("fecha_pedido")), name="pedido_limite_posterior_al_pedido"
            ),
        ]

    def __str__(self):
        """«P-0031»: el identificador que ven las pantallas, los correos y la auditoría (D-36)."""
        return f"P-{self.pk:04d}" if self.pk else "P-nuevo"

    @property
    def en_cotizacion(self):
        """True si el pedido sigue «en cotización»."""
        return self.estado_pedido == self.Estado.EN_COTIZACION


# Motivo que se guarda en una cancelación automática, según su causa: los literales de la regla 3 de CMP-CNL-PED («Lista de tecnología», paso 3).
# No se derivan de ``Pedido.Causa`` (esos son los rótulos de las pantallas). La causa ``manual`` no figura: el motivo lo escribe el Agrónomo.
MOTIVOS_DE_CANCELACION_AUTOMATICA = {
    Pedido.Causa.NADIE_COTIZO: "nadie cotizó",
    Pedido.Causa.SIN_COTIZACIONES_ELEGIBLES: "sin cotizaciones elegibles",
    Pedido.Causa.AGRONOMO_INACTIVO: "Agrónomo inactivo",
    Pedido.Causa.AGRONOMO_SIN_INVERNADERO: "Agrónomo sin el invernadero de destino",
}


class DetallePedido(models.Model):
    """Una línea del pedido: un insumo habilitado en un invernadero, con la cantidad pedida y una copia del precio de referencia de
    ese momento (docs/modelo/compras.md, «DetallePedido»; R025, R037 y R133). R037 y R133 van juntas en ``insumo_invernadero``
    (técnico). El precio **no se muestra a los proveedores**."""

    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name="detalles")
    insumo_invernadero = models.ForeignKey(InsumoInvernadero, on_delete=models.PROTECT, related_name="detalles_de_pedido")
    cantidad_detalle = models.DecimalField("cantidad pedida", max_digits=14, decimal_places=3)
    precio_unitario_de_pedido = models.DecimalField("precio de referencia", max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["id"]
        verbose_name = "Detalle de pedido"
        verbose_name_plural = "Detalles de pedido"
        constraints = [
            # «Detalle único» (regla de CMP-RLZ-PED, extensión 4b): un pedido no repite el par insumo–invernadero.
            models.UniqueConstraint(fields=["pedido", "insumo_invernadero"], name="detalle_pedido_unico_por_insumo_invernadero"),
            models.CheckConstraint(condition=Q(cantidad_detalle__gt=0), name="detalle_pedido_cantidad_positiva"),
            models.CheckConstraint(condition=Q(precio_unitario_de_pedido__gt=0), name="detalle_pedido_precio_positivo"),
        ]

    def __str__(self):
        """«Insumo · Invernadero» del detalle (texto de la auditoría)."""
        return str(self.insumo_invernadero)

    @property
    def subtotal(self):
        """cantidad × precio de referencia, con dos decimales (``ROUND_HALF_UP``): lo que suma el monto estimado (D-89 punto 7)."""
        return (self.cantidad_detalle * self.precio_unitario_de_pedido).quantize(DOS_DECIMALES, ROUND_HALF_UP)


class InvitacionPedido(models.Model):
    """R157: el proveedor invitado a un pedido (técnico: la tabla de la asociación muchos a muchos). Es la «invitación» que audita
    CMP-RLZ-PED (postcondición g). Única por ``(pedido, proveedor)``."""

    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name="invitaciones")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="invitaciones")
    fecha_invitacion = models.DateTimeField("fecha de la invitación", default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "Invitación a un pedido"
        verbose_name_plural = "Invitaciones a un pedido"
        constraints = [
            models.UniqueConstraint(fields=["pedido", "proveedor"], name="invitacion_pedido_unica_por_proveedor"),
        ]

    def __str__(self):
        """«Proveedor en P-0031» (texto de la auditoría)."""
        return f"{self.proveedor} en {self.pedido}"


class EnlaceProveedor(models.Model):
    """El enlace que recibe un proveedor invitado para cotizar sin cuenta (D-88; docs/patrones/enlace_del_proveedor.md). Tabla técnica.
    La base guarda solo el resumen SHA-256 del token, nunca el token (``core/enlaces.py``). **No guarda fecha de vencimiento**: vence al
    terminar el día de la fecha límite del pedido, que se lee del pedido al abrir y al registrar. No se audita por su cuenta."""

    class Estado(models.TextChoices):
        VIGENTE = "vigente", "Vigente"
        USADO = "usado", "Usado"
        VENCIDO = "vencido", "Vencido"
        ANULADO = "anulado", "Anulado"
        REEMPLAZADO = "reemplazado", "Reemplazado"

    class EstadoEnvio(models.TextChoices):
        ENVIADO = "enviado", "Enviado"
        PENDIENTE_ENVIO = "pendiente_envio", "No se pudo enviar"

    invitacion = models.ForeignKey(InvitacionPedido, on_delete=models.PROTECT, related_name="enlaces")
    token_resumen = models.CharField(max_length=64, unique=True)
    fecha_creacion = models.DateTimeField(default=timezone.now, editable=False)
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.VIGENTE)
    fecha_uso = models.DateTimeField(null=True, blank=True)
    # Nulo hasta que se intenta el envío (el correo sale fuera de la transacción).
    estado_envio = models.CharField(max_length=20, choices=EstadoEnvio.choices, null=True, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Enlace del proveedor"
        verbose_name_plural = "Enlaces del proveedor"
        constraints = [
            # D-88 punto 1: a lo sumo un enlace vigente por invitación.
            models.UniqueConstraint(fields=["invitacion"], condition=Q(estado="vigente"), name="enlace_un_vigente_por_invitacion"),
            models.CheckConstraint(
                condition=Q(estado__in=["vigente", "usado", "vencido", "anulado", "reemplazado"]), name="enlace_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(estado_envio__isnull=True) | Q(estado_envio__in=["enviado", "pendiente_envio"]),
                name="enlace_estado_envio_valido",
            ),
            # Modelo, «EnlaceProveedor»: usado ⇔ fecha de uso.
            models.CheckConstraint(
                condition=(Q(estado="usado") & Q(fecha_uso__isnull=False)) | (~Q(estado="usado") & Q(fecha_uso__isnull=True)),
                name="enlace_usado_coherente_con_fecha_de_uso",
            ),
        ]

    def __str__(self):
        """«Enlace de Proveedor en P-0031» (nunca lleva el token)."""
        return f"Enlace de {self.invitacion}"


class Cotizacion(models.Model):
    """La oferta completa de un proveedor para un pedido, con una línea por cada detalle que cotiza (docs/modelo/compras.md,
    «Cotizacion»; R035). Se envía una sola vez y no se modifica. ``pedido`` es técnico: el modelo lo obtiene por las líneas, se guarda
    para que la base garantice **C8** con la única ``(pedido, proveedor)``. Que cada línea sea de un detalle de ese pedido lo garantiza
    el servicio. El monto es derivado (Σ de los totales de línea)."""

    class Estado(models.TextChoices):
        PROPUESTA = "propuesta", "Propuesta"
        SELECCIONADA = "seleccionada", "Seleccionada"
        DESCARTADA = "descartada", "Descartada"

    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name="cotizaciones")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="cotizaciones")
    fecha_cotizacion = models.DateField("fecha de la cotización")
    # Técnico: la hora del envío, para el acuse.
    enviada_el = models.DateTimeField("enviada el", default=timezone.now, editable=False)
    fecha_validez_cotizacion = models.DateField("válida hasta")
    estado_cotizacion = models.CharField(max_length=15, choices=Estado.choices, default=Estado.PROPUESTA)
    observaciones_cotizacion = models.CharField("observaciones", max_length=1000, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        constraints = [
            # C8: una cotización por proveedor y por pedido. Respalda al bloqueo en el envío simultáneo (extensión 11b).
            models.UniqueConstraint(fields=["pedido", "proveedor"], name="cotizacion_unica_por_pedido_y_proveedor"),
            models.CheckConstraint(
                condition=Q(estado_cotizacion__in=["propuesta", "seleccionada", "descartada"]), name="cotizacion_estado_valido"
            ),
        ]

    def __str__(self):
        """«Cotización de Proveedor para P-0031» (texto de la auditoría)."""
        return f"Cotización de {self.proveedor} para {self.pedido}"

    @property
    def monto_cotizacion(self):
        """Σ de los totales de sus líneas (derivado). Usa las líneas ya traídas con ``prefetch_related("lineas")`` si las hay."""
        return sum((linea.total_linea for linea in self.lineas.all()), Decimal("0.00"))


class DetalleCotizacion(models.Model):
    """Una línea de la cotización: lo que el proveedor ofrece para un detalle del pedido (docs/modelo/compras.md, «DetalleCotizacion»;
    R024 y R159). Se guarda el **total** de la línea; el unitario es derivado (``compras.precios.precio_unitario``, D-89). La cantidad
    cotizada puede superar la pedida (P2)."""

    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.PROTECT, related_name="lineas")
    detalle_pedido = models.ForeignKey(DetallePedido, on_delete=models.PROTECT, related_name="lineas_de_cotizacion")
    cantidad_cotizada = models.DecimalField("cantidad cotizada", max_digits=14, decimal_places=3)
    total_linea = models.DecimalField("total de la línea", max_digits=14, decimal_places=2)
    plazo_entrega_dias = models.PositiveIntegerField("plazo de entrega (días)")

    class Meta:
        ordering = ["id"]
        verbose_name = "Línea de cotización"
        verbose_name_plural = "Líneas de cotización"
        constraints = [
            models.UniqueConstraint(fields=["cotizacion", "detalle_pedido"], name="linea_cotizacion_unica_por_detalle"),
            models.CheckConstraint(condition=Q(cantidad_cotizada__gt=0), name="linea_cotizacion_cantidad_positiva"),
            models.CheckConstraint(condition=Q(total_linea__gt=0), name="linea_cotizacion_total_positivo"),
            # P2: el plazo de entrega es un entero de 1 o más (mejora sobre «≥ 0» del caso de uso original).
            models.CheckConstraint(condition=Q(plazo_entrega_dias__gte=1), name="linea_cotizacion_plazo_minimo"),
        ]

    def __str__(self):
        """«Insumo · Invernadero» de la línea (texto de la auditoría)."""
        return str(self.detalle_pedido)


# ---------------------------------------------------------------------------------------------------------------------------------
# Órdenes de compra (CMP-03). Fuente: docs/modelo/compras.md («OrdenCompra» y «DetalleOrdenCompra»; reglas 13, 16, 18, 23 y 24 de 8.16, D-89).
# ``AlertaCompras`` y ``ReclamoProveedor`` están más abajo (CMP-04).
# ---------------------------------------------------------------------------------------------------------------------------------


class OrdenCompraQuerySet(models.QuerySet):
    """El alcance por usuario de las órdenes de compra, en un único lugar (CLAUDE.md, «Arquitectura»)."""

    def en_alcance_de(self, actor):
        """Regla 1 de CMP-CNS-ODC: el Agrónomo activo ve las órdenes con algún destino en los invernaderos que tiene a cargo; el Gerente activo, todas;
        el Contador activo, todas en solo lectura (D-87 punto 6, USR-11); cualquier otra cuenta, una cuenta inactiva o ``None``, ninguna."""
        if actor is None or not actor.is_active:
            return self.none()
        rol = rol_de(actor)
        if rol in (Usuario.Rol.GERENTE, Usuario.Rol.CONTADOR):
            return self.all()
        if rol == Usuario.Rol.AGRONOMO:
            return self.filter(
                pk__in=DetalleOrdenCompra.objects.filter(
                    detalle_cotizacion__detalle_pedido__insumo_invernadero__invernadero__agronomo_id=actor.pk
                ).values("orden_id")
            )
        return self.none()

    def con_monto(self):
        """Anota ``monto_orden``: Σ ``total_linea`` de sus detalles (D-89 punto 5: derivado, no una columna; no se llama ``monto_total`` porque es la propiedad)."""
        importe = models.DecimalField(max_digits=16, decimal_places=2)
        return self.annotate(
            monto_orden=Coalesce(Sum("detalles__total_linea", output_field=importe), Decimal("0.00"), output_field=importe)
        )


class OrdenCompra(models.Model):
    """La orden que arma el Agrónomo con las cotizaciones elegidas de un pedido y resuelve el Gerente (docs/modelo/compras.md, «OrdenCompra»; R011).
    Nace «pendiente de aprobación» y pasa a «aprobada» o «rechazada» (CMP-APR-ODC); los estados de recepción los aplica CMP-04. Una por pedido
    (regla 13 de 8.16): ``pedido`` es ``OneToOne``, así que la base impide dos. El monto es derivado (``monto_total``)."""

    class Estado(models.TextChoices):
        PENDIENTE_APROBACION = "pendiente_aprobacion", "Pendiente de aprobación"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"
        PARCIALMENTE_RECIBIDA = "parcialmente_recibida", "Parcialmente recibida"
        RECIBIDA = "recibida", "Recibida"
        RECIBIDA_CON_FALTANTE = "recibida_con_faltante", "Recibida con faltante"

    # «No terminada» (H20 y H22): impide deshabilitar el insumo de destino y dar de baja a su proveedor.
    NO_TERMINADAS = (Estado.PENDIENTE_APROBACION, Estado.APROBADA, Estado.PARCIALMENTE_RECIBIDA)

    pedido = models.OneToOneField(Pedido, on_delete=models.PROTECT, related_name="orden_compra")
    fecha_emision = models.DateField("fecha de emisión")
    fecha_resolucion = models.DateField("fecha de resolución", null=True, blank=True)
    estado_orden_compra = models.CharField(max_length=25, choices=Estado.choices, default=Estado.PENDIENTE_APROBACION)
    observaciones = models.TextField("observaciones del Agrónomo", blank=True)
    motivo_rechazo = models.TextField("motivo del rechazo", blank=True)
    # R011: el Gerente que la resolvió; vacío mientras está pendiente.
    gerente = models.ForeignKey(Gerente, on_delete=models.PROTECT, null=True, blank=True, related_name="ordenes_resueltas")

    objects = OrdenCompraQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        verbose_name = "Orden de compra"
        verbose_name_plural = "Órdenes de compra"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    estado_orden_compra__in=[
                        "pendiente_aprobacion",
                        "aprobada",
                        "rechazada",
                        "parcialmente_recibida",
                        "recibida",
                        "recibida_con_faltante",
                    ]
                ),
                name="orden_estado_valido",
            ),
            # Modelo, «OrdenCompra»: resuelta (estado distinto de pendiente) ⇔ tiene Gerente y fecha de resolución (R011).
            models.CheckConstraint(
                condition=(Q(estado_orden_compra="pendiente_aprobacion") & Q(gerente__isnull=True) & Q(fecha_resolucion__isnull=True))
                | (~Q(estado_orden_compra="pendiente_aprobacion") & Q(gerente__isnull=False) & Q(fecha_resolucion__isnull=False)),
                name="orden_resolucion_coherente_con_estado",
            ),
            # Modelo, «OrdenCompra»: rechazada ⇔ motivo no vacío.
            models.CheckConstraint(
                condition=(Q(estado_orden_compra="rechazada") & ~Q(motivo_rechazo=""))
                | (~Q(estado_orden_compra="rechazada") & Q(motivo_rechazo="")),
                name="orden_motivo_de_rechazo_coherente_con_estado",
            ),
        ]

    def __str__(self):
        """«OC-0007»: el identificador que ven las pantallas, los correos y la auditoría (D-36)."""
        return f"OC-{self.pk:04d}" if self.pk else "OC-nueva"

    @property
    def pendiente(self):
        """True si la orden espera la decisión del Gerente."""
        return self.estado_orden_compra == self.Estado.PENDIENTE_APROBACION

    @property
    def monto_total(self):
        """Σ de los totales de sus detalles (derivado). Usa los detalles ya traídos con ``prefetch_related("detalles")`` si los hay."""
        return sum((detalle.total_linea for detalle in self.detalles.all()), Decimal("0.00"))


class DetalleOrdenCompra(models.Model):
    """Una línea de la orden: copia de una línea de cotización elegida (docs/modelo/compras.md, «DetalleOrdenCompra»; R022 y R023). Copia la cantidad
    **cotizada** (P2) y el **total** de la línea (D-89); el unitario es derivado (``compras.precios.precio_unitario``). **R026 se deriva**
    (``detalle_pedido``): guardarla repetiría un dato que no puede ser distinto (regla 5 de 8.17); el proveedor también. Lo recibido y el cierre con
    faltante son de CMP-04."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        COMPLETO = "completo", "Completo"
        CERRADO_CON_FALTANTE = "cerrado_con_faltante", "Cerrado con faltante"

    orden = models.ForeignKey(OrdenCompra, on_delete=models.PROTECT, related_name="detalles")
    # R023: una línea de cotización genera a lo sumo un detalle de orden.
    detalle_cotizacion = models.OneToOneField(DetalleCotizacion, on_delete=models.PROTECT, related_name="detalle_orden")
    cantidad_detalle_orden = models.DecimalField("cantidad", max_digits=14, decimal_places=3)
    total_linea = models.DecimalField("total de la línea", max_digits=14, decimal_places=2)
    # Nula hasta la aprobación: fecha de resolución + plazo de la línea (regla 23 de 8.16).
    fecha_entrega_esperada = models.DateField("fecha de entrega esperada", null=True, blank=True)
    estado_detalle_orden = models.CharField(max_length=25, choices=Estado.choices, default=Estado.PENDIENTE)
    motivo_cierre_faltante = models.TextField("motivo del cierre con faltante", blank=True)
    # Técnico (D-91): para ordenar la bandeja de pagos.
    fecha_cierre_faltante = models.DateField("fecha del cierre con faltante", null=True, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Detalle de orden de compra"
        verbose_name_plural = "Detalles de orden de compra"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_detalle_orden__gt=0), name="detalle_orden_cantidad_positiva"),
            models.CheckConstraint(condition=Q(total_linea__gt=0), name="detalle_orden_total_positivo"),
            models.CheckConstraint(
                condition=Q(estado_detalle_orden__in=["pendiente", "completo", "cerrado_con_faltante"]), name="detalle_orden_estado_valido"
            ),
            # Modelo, «DetalleOrdenCompra»: cerrado con faltante ⇔ motivo no vacío y fecha de cierre.
            models.CheckConstraint(
                condition=(
                    Q(estado_detalle_orden="cerrado_con_faltante") & ~Q(motivo_cierre_faltante="") & Q(fecha_cierre_faltante__isnull=False)
                )
                | (~Q(estado_detalle_orden="cerrado_con_faltante") & Q(motivo_cierre_faltante="") & Q(fecha_cierre_faltante__isnull=True)),
                name="detalle_orden_faltante_coherente_con_estado",
            ),
        ]

    def __str__(self):
        """«Insumo · Invernadero» de la línea (texto de la auditoría)."""
        return str(self.detalle_cotizacion.detalle_pedido)

    @property
    def detalle_pedido(self):
        """R026 derivada: el detalle del pedido que cubre esta línea (``detalle_cotizacion.detalle_pedido``)."""
        return self.detalle_cotizacion.detalle_pedido

    @property
    def proveedor(self):
        """El proveedor de la línea (línea de cotización → cotización → proveedor)."""
        return self.detalle_cotizacion.cotizacion.proveedor

    @property
    def unitario_para_mostrar(self):
        """El precio unitario derivado con dos decimales (D-89 puntos 1 y 7), para pantallas y correos."""
        return precio_unitario_para_mostrar(self)


# ---------------------------------------------------------------------------------------------------------------------------------
# Recepciones (CMP-04). Fuente: docs/modelo/compras.md («Recepcion», «DetalleRecepcion», «DetalleRecepcionMovimiento», «InconvenienteRecepcion»,
# «ReclamoProveedor» y «AlertaCompras»); D-87 punto 5, D-89 y D-90 (puntos 3, 6 y 7). Reglas 6 a 11 y 14 de 8.20.
# ---------------------------------------------------------------------------------------------------------------------------------


class Recepcion(OrigenDocumento):
    """La mercadería que un proveedor entrega en un invernadero, para una orden (docs/modelo/compras.md, «Recepcion»; regla 7 de 8.20, R019). Hereda de
    ``OrigenDocumento`` (tipo ``recepcion``, D-90 punto 3): es el ``origen`` de cada movimiento de ingreso y del asiento. NO redeclara ``save()``: el del padre
    fija ``tipo`` desde ``TIPO_DE_ORIGEN`` (D-52). ``agronomo`` es 0..1 (R039): vacío si la registró el Gerente (quien registró queda en la auditoría).
    **(técnico)** ``proveedor`` e ``invernadero``: «una recepción es de una orden, un proveedor y un invernadero»; los fija el servicio y una prueba verifica que
    coincidan con sus líneas. La fecha es siempre la del registro, sin fechas retroactivas."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.RECEPCION

    fecha_recepcion = models.DateField("fecha de recepción")
    observaciones_recepcion = models.TextField("observaciones de la recepción", blank=True)
    orden = models.ForeignKey(OrdenCompra, on_delete=models.PROTECT, related_name="recepciones")
    agronomo = models.ForeignKey(Agronomo, null=True, blank=True, on_delete=models.PROTECT, related_name="recepciones")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="recepciones")
    invernadero = models.ForeignKey("maestros.Invernadero", on_delete=models.PROTECT, related_name="recepciones")

    class Meta:
        ordering = ["id"]
        verbose_name = "Recepción"
        verbose_name_plural = "Recepciones"

    def __str__(self):
        """«RCP-0001»: el identificador que ven las pantallas, los correos y la auditoría (D-36)."""
        return f"RCP-{self.pk:04d}" if self.pk else "RCP-nueva"


class DetalleRecepcion(models.Model):
    """Una línea de la recepción: lo que **ingresó** al stock de una línea de la orden (modelo, «DetalleRecepcion»; R022 y R030). ``cantidad_recibida_detalle`` no
    cuenta lo dañado ni lo vencido; vale 0 solo si todo lo que llegó tuvo un inconveniente que no sea «otro» (extensión 7c). Única por ``(recepcion, detalle_orden)``."""

    recepcion = models.ForeignKey(Recepcion, on_delete=models.PROTECT, related_name="detalles")
    detalle_orden = models.ForeignKey(DetalleOrdenCompra, on_delete=models.PROTECT, related_name="detalles_de_recepcion")
    cantidad_recibida_detalle = models.DecimalField("cantidad recibida", max_digits=14, decimal_places=3)

    class Meta:
        ordering = ["id"]
        verbose_name = "Detalle de recepción"
        verbose_name_plural = "Detalles de recepción"
        constraints = [
            models.UniqueConstraint(fields=["recepcion", "detalle_orden"], name="detalle_recepcion_unico_por_linea"),
            models.CheckConstraint(condition=Q(cantidad_recibida_detalle__gte=0), name="detalle_recepcion_cantidad_no_negativa"),
        ]

    def __str__(self):
        """«Insumo · Invernadero» de la línea (texto de la auditoría)."""
        return str(self.detalle_orden)


class DetalleRecepcionMovimiento(models.Model):
    """R032 **(técnico, D-90 punto 3)**: une cada movimiento de ingreso con **su** línea de recepción. Uno por lote tocado (incluido el faltante sin lote).
    ``inventario`` no conoce a ``compras`` (A1, A2): el vínculo vive acá. ``related_name`` elegidos para no chocar con los accesorios de la herencia (D-83)."""

    detalle_recepcion = models.ForeignKey(DetalleRecepcion, on_delete=models.PROTECT, related_name="vinculos_de_movimiento")
    movimiento = models.OneToOneField(MovimientoInsumo, on_delete=models.PROTECT, related_name="vinculo_de_recepcion")

    class Meta:
        ordering = ["id"]
        verbose_name = "Vínculo recepción-movimiento"
        verbose_name_plural = "Vínculos recepción-movimiento"

    def __str__(self):
        return f"{self.detalle_recepcion} → movimiento {self.movimiento_id}"


class ReclamoProveedor(models.Model):
    """El reclamo a un proveedor por los inconvenientes de una recepción (modelo, «ReclamoProveedor»; R008 en 0..1, R028 y regla 10 de 8.20). CMP-04 lo crea
    «abierto» y **sin emitir** (sin Gerente y sin fecha); emitirlo y cerrarlo es de CMP-06. Emitido ⇔ tiene Gerente, y solo entonces tiene fecha. **(técnico)**
    ``recepcion`` es ``OneToOne``: un reclamo por recepción con inconvenientes."""

    class Estado(models.TextChoices):
        ABIERTO = "abierto", "Abierto"
        CERRADO = "cerrado", "Cerrado"

    fecha_reclamo = models.DateField("fecha de emisión", null=True, blank=True)
    estado_reclamo = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTO)
    gerente = models.ForeignKey(Gerente, null=True, blank=True, on_delete=models.PROTECT, related_name="reclamos_emitidos")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="reclamos")
    recepcion = models.OneToOneField(Recepcion, on_delete=models.PROTECT, related_name="reclamo")

    class Meta:
        ordering = ["-id"]
        verbose_name = "Reclamo a proveedor"
        verbose_name_plural = "Reclamos a proveedores"
        constraints = [
            models.CheckConstraint(condition=Q(estado_reclamo__in=["abierto", "cerrado"]), name="reclamo_estado_valido"),
            # Modelo, «ReclamoProveedor»: sin Gerente ⇔ sin fecha de emisión.
            models.CheckConstraint(
                condition=(Q(gerente__isnull=True) & Q(fecha_reclamo__isnull=True)) | (Q(gerente__isnull=False) & Q(fecha_reclamo__isnull=False)),
                name="reclamo_gerente_si_y_solo_si_fecha",
            ),
            # Modelo, «ReclamoProveedor»: solo se cierra un reclamo emitido.
            models.CheckConstraint(condition=~Q(estado_reclamo="cerrado") | Q(gerente__isnull=False), name="reclamo_cerrado_esta_emitido"),
        ]

    def __str__(self):
        """«REC-0001»: el identificador que ven las pantallas y la auditoría."""
        return f"REC-{self.pk:04d}" if self.pk else "REC-nuevo"

    @property
    def emitido(self):
        """True si un Gerente ya lo emitió."""
        return self.gerente_id is not None


class InconvenienteRecepcion(models.Model):
    """Un problema con lo que llegó (modelo, «InconvenienteRecepcion»; R029, R030, regla 10 de 8.20 y D-90 punto 7). Cinco tipos (P4, MD-130); el retraso no se declara: se
    calcula y se muestra. A lo sumo uno de cada tipo por línea de recepción. La descripción es obligatoria en «otro»."""

    class Tipo(models.TextChoices):
        MERCADERIA_DANADA = "mercaderia_danada", "Mercadería dañada"
        CALIDAD_NO_CONFORME = "calidad_no_conforme", "Calidad no conforme"
        PRODUCTO_DISTINTO = "producto_distinto", "Producto distinto al pedido"
        VENCIDO_O_POR_VENCER = "vencido_o_por_vencer", "Vencido o próximo a vencer"
        OTRO = "otro", "Otro"

    detalle_recepcion = models.ForeignKey(DetalleRecepcion, on_delete=models.PROTECT, related_name="inconvenientes")
    reclamo = models.ForeignKey(ReclamoProveedor, on_delete=models.PROTECT, related_name="inconvenientes")
    tipo_inconveniente = models.CharField("tipo", max_length=25, choices=Tipo.choices)
    cantidad_afectada = models.DecimalField("cantidad afectada", max_digits=14, decimal_places=3)
    descripcion_inconveniente = models.TextField("descripción", blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Inconveniente de recepción"
        verbose_name_plural = "Inconvenientes de recepción"
        constraints = [
            models.UniqueConstraint(fields=["detalle_recepcion", "tipo_inconveniente"], name="inconveniente_unico_por_tipo_y_linea"),
            models.CheckConstraint(
                condition=Q(tipo_inconveniente__in=["mercaderia_danada", "calidad_no_conforme", "producto_distinto", "vencido_o_por_vencer", "otro"]),
                name="inconveniente_tipo_valido",
            ),
            models.CheckConstraint(condition=Q(cantidad_afectada__gt=0), name="inconveniente_cantidad_positiva"),
            # Modelo, «InconvenienteRecepcion»: la descripción es obligatoria en «otro».
            models.CheckConstraint(
                condition=~Q(tipo_inconveniente="otro") | ~Q(descripcion_inconveniente=""), name="inconveniente_otro_con_descripcion"
            ),
        ]

    def __str__(self):
        """«Mercadería dañada» (texto de la auditoría)."""
        return self.get_tipo_inconveniente_display()


class AlertaCompras(models.Model):
    """Tabla de vínculo entre una alerta de `maestros` y su origen en `compras` **(técnico, D-87 punto 5; patrón de `AlertaComercial`, D-63)**: `Alerta` no conoce a
    `compras` (A2 de D-37). La crea el mismo servicio que crea la alerta (``registrar_recepcion``), en la misma transacción; la emisión del reclamo (CMP-06) la resuelve."""

    alerta = models.OneToOneField("maestros.Alerta", on_delete=models.PROTECT, related_name="vinculo_de_compras")
    reclamo = models.ForeignKey(ReclamoProveedor, on_delete=models.PROTECT, related_name="alertas")

    class Meta:
        ordering = ["id"]
        verbose_name = "Alerta de compras"
        verbose_name_plural = "Alertas de compras"

    def __str__(self):
        return f"Alerta de {self.reclamo}"


# ---------------------------------------------------------------------------------------------------------------------------------
# Pagos (CMP-05). Fuente: docs/modelo/compras.md («Pago»); D-91 punto 1 y D-89 punto 6; regla 13 de 8.20 y R158.
# ---------------------------------------------------------------------------------------------------------------------------------


class Pago(OrigenDocumento):
    """Lo que se le pagó a un proveedor por lo recibido de una orden (docs/modelo/compras.md, «Pago»; D-91 punto 1; R018 y R158). Hereda de ``OrigenDocumento`` (tipo ``pago``, D-52):
    es el ``origen`` del asiento Debe Proveedores / Haber Caja o Banco c/c. NO redeclara ``save()``: el del padre fija ``tipo`` desde ``TIPO_DE_ORIGEN``. Hay **a lo sumo uno por orden y
    proveedor** (R158, regla 13 de 8.20: los pagos parciales no existen). ``monto_pago`` **se guarda** (D-89 punto 6): es lo que se pagó, y no lo escribe quien paga: lo calcula el servicio
    (``precios.valor_recibido``). No hay comprobante ni número de operación en el modelo y un pago no se anula (D-91 punto 7). No confundir con ``PagoCliente`` de ``comercial``."""

    class MedioPago(models.TextChoices):
        """Regla 15 de 8.13 (MD-36): el efectivo se imputa a Caja y los demás medios a Banco c/c."""

        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"
        TARJETA_DEBITO = "tarjeta_debito", "Tarjeta de débito"
        TARJETA_CREDITO = "tarjeta_credito", "Tarjeta de crédito"

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.PAGO

    fecha_pago = models.DateField("fecha del pago")
    medio_pago = models.CharField("medio de pago", max_length=20, choices=MedioPago.choices)
    monto_pago = models.DecimalField("monto pagado", max_digits=14, decimal_places=2)
    orden = models.ForeignKey(OrdenCompra, on_delete=models.PROTECT, related_name="pagos")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="pagos")

    class Meta:
        ordering = ["id"]
        verbose_name = "Pago a proveedor"
        verbose_name_plural = "Pagos a proveedores"
        constraints = [
            # R158 y regla 13 de 8.20: un solo pago por proveedor y por orden. Es también la red de la concurrencia (dos pagos a la vez del mismo par).
            models.UniqueConstraint(fields=["orden", "proveedor"], name="pago_unico_por_orden_y_proveedor"),
            models.CheckConstraint(condition=Q(monto_pago__gt=0), name="pago_monto_positivo"),
            models.CheckConstraint(
                condition=Q(medio_pago__in=["efectivo", "transferencia", "tarjeta_debito", "tarjeta_credito"]), name="pago_medio_valido"
            ),
        ]

    def __str__(self):
        """«PAG-0001»: el identificador que ven las pantallas, los correos y la auditoría (D-36)."""
        return f"PAG-{self.pk:04d}" if self.pk else "PAG-nuevo"


# ---------------------------------------------------------------------------------------------------------------------------------
# Correcciones de recepción (CMP-06). Fuente: docs/modelo/compras.md («CorreccionRecepcion»); D-90 puntos 1 a 4 y D-89 punto 4; CMP-COR-RCP (MD-126).
# ---------------------------------------------------------------------------------------------------------------------------------


class CorreccionRecepcion(OrigenDocumento):
    """Lo que el Agrónomo (o el Gerente) le baja a una recepción cargada de más (docs/modelo/compras.md, «CorreccionRecepcion»; MD-126). Hereda de ``OrigenDocumento`` (tipo
    ``correccion_de_recepcion``, D-90 punto 3): es el ``origen`` de cada movimiento de salida y del asiento inverso (Debe Proveedores / Haber Insumos en Stock). NO redeclara ``save()``: el del padre
    fija ``tipo`` desde ``TIPO_DE_ORIGEN``. ``agronomo`` es 0..1, como en la recepción: vacío si corrigió el Gerente (quien corrigió queda en la auditoría). La fecha es la del registro."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.CORRECCION_DE_RECEPCION

    # Se llama ``recepcion_corregida`` y no ``recepcion`` (como dice el extracto del modelo): ``recepcion`` choca con el accesorio de la herencia multitabla
    # (``OrigenDocumento.recepcion`` es el hijo ``Recepcion``; error E006, lección de D-83). Queda anotado en temas abiertos.
    recepcion_corregida = models.ForeignKey(Recepcion, on_delete=models.PROTECT, related_name="correcciones")
    fecha_correccion = models.DateField("fecha de la corrección")
    observacion = models.TextField("observación", blank=True)
    agronomo = models.ForeignKey(Agronomo, null=True, blank=True, on_delete=models.PROTECT, related_name="correcciones_de_recepcion")

    class Meta:
        ordering = ["id"]
        verbose_name = "Corrección de recepción"
        verbose_name_plural = "Correcciones de recepción"

    def __str__(self):
        """«COR-0001»: el identificador que ven las pantallas, los correos y la auditoría (D-36)."""
        return f"COR-{self.pk:04d}" if self.pk else "COR-nueva"


class DetalleCorreccionRecepcion(models.Model):
    """Una línea de la corrección **(técnico, D-90 punto 3)**: lo descontado de una línea de la recepción en **un** lote, con su movimiento de salida. Si la corrección toca dos lotes de la misma línea, son
    dos filas. ``movimiento`` es ``OneToOne`` (R032 análoga): ``inventario`` no conoce a ``compras`` (A1, A2) y los ``related_name`` no chocan con los accesorios de la herencia (D-83)."""

    correccion = models.ForeignKey(CorreccionRecepcion, on_delete=models.PROTECT, related_name="detalles")
    detalle_recepcion = models.ForeignKey(DetalleRecepcion, on_delete=models.PROTECT, related_name="correcciones")
    cantidad_corregida = models.DecimalField("cantidad corregida", max_digits=14, decimal_places=3)
    movimiento = models.OneToOneField(MovimientoInsumo, on_delete=models.PROTECT, related_name="vinculo_de_correccion")

    class Meta:
        ordering = ["id"]
        verbose_name = "Detalle de corrección de recepción"
        verbose_name_plural = "Detalles de corrección de recepción"
        constraints = [models.CheckConstraint(condition=Q(cantidad_corregida__gt=0), name="detalle_correccion_cantidad_positiva")]

    def __str__(self):
        """«Insumo · Invernadero» de la línea (texto de la auditoría)."""
        return str(self.detalle_recepcion)
