# Modelos de `compras` (nivel 6 de D-37), CMP-01: Proveedor. Fuente: docs/modelo/compras.md (ficha Proveedor; MD-121, MD-122 y MD-130
# de A0; D-87). Nunca se borra una fila de negocio: hay baja lógica (estado inactivo) y reactivación. A2 de D-37: la M2M a
# `inventario.TipoInsumo` se declara acá, en la app de nivel mayor. Ningún import de `comercial` ni de `produccion` (A1).

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from core.models import Usuario, rol_de
from core.validadores import validar_telefono
from inventario.models import TipoInsumo
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
