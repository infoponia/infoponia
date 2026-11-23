# Modelos de `comercial` (nivel 6 de D-37) para COM-01: Cliente, DireccionCliente y Vehiculo (docs/modelo/comercial.md).
# Decisiones: D-05 (nombres en snake_case con el sufijo de la clase), D-06 (id automático), D-28 (alcance en un único
# lugar), D-37 (A2: la FK la declara la app de nivel mayor) y D-58 (DireccionCliente, la tabla de vínculo de R119).
# Las bajas son lógicas y las claves foráneas son PROTECT (docs/modelo/comercial.md, «Convenciones de esta ficha»).

from django.db import models
from django.db.models import Q

from core.models import Transportista, Usuario, rol_de
from core.validadores import validar_telefono
from maestros.models import Direccion

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
