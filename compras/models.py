# Modelos de `compras` (nivel 6 de D-37): Proveedor (CMP-01) y, desde CMP-02a, Pedido, DetallePedido, InvitacionPedido, EnlaceProveedor,
# Cotizacion y DetalleCotizacion. Fuente: docs/modelo/compras.md (MD-121 a MD-130 de A0; D-87, D-88 y D-89). Nunca se borra una fila de
# negocio: hay estados. A2 de D-37: toda FK o M2M se declara acá, en la app de nivel mayor. Ningún import de `comercial` ni de
# `produccion` (A1).

from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce, Round
from django.utils import timezone

from core.models import Agronomo, Usuario, rol_de
from core.validadores import validar_telefono
from inventario.models import InsumoInvernadero, TipoInsumo
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
