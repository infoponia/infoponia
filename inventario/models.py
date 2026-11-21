# Modelos de `inventario` (nivel 4 de D-37), INV-01: TipoInsumo, Insumo, InsumoInvernadero, LoteInsumo y MovimientoInsumo.
# Fuente: docs/modelo/inventario.md (fichas y reglas 8.4, 8.13, 8.19 y 8.23). Cantidades: Decimal con 3 decimales en la base,
# validadas contra la unidad del insumo en el servicio (inventario/unidades.py); precios: Decimal(14, 2). Nunca float.
# Bajas lógicas (D-36): nunca se borra una fila de negocio; las FK son PROTECT. A2 de D-37: las FK a `maestros` y a
# `contabilidad` se declaran acá, en la app de nivel mayor.
#
# DIFERENCIA CON LA DOCUMENTACIÓN: el campo propio de MovimientoInsumo que la ficha llama `tipo` se llama `tipo_movimiento`,
# porque `contabilidad.OrigenDocumento` (padre, D-52) ya tiene un campo `tipo` y Django no admite el mismo nombre en la hija.
# Decidido por el estudiante; anotado en el cierre de INV-01 y en docs/temas_abiertos.md.

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario.categorias import CATEGORIAS_DEL_SISTEMA
from inventario.unidades import Unidad
from maestros.models import Invernadero


class TipoInsumo(models.Model):
    """Categoría de insumos (CMP-ALT-TIN y siguientes; regla 1 de 8.23). Vale para todos los invernaderos. Cuatro son del
    sistema (`es_del_sistema`, con `codigo` fijo): no se renombran ni se dan de baja, y las reglas las buscan por `codigo`."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    class ConsumoDirecto(models.TextChoices):
        """Si los insumos se pueden registrar sin orden de trabajo y a dónde va su costo (regla 3 de CMP-ALT-TIN)."""

        NO_ADMITE = "no_admite", "No admite"
        COMO_GASTO = "como_gasto", "Como gasto"
        COMO_COSTO_DE_LOS_LOTES = "como_costo_de_los_lotes", "Como costo de los lotes"

    nombre_tipo_insumo = models.CharField("nombre", max_length=100)
    estado_tipo_insumo = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)
    consumo_directo = models.CharField(max_length=30, choices=ConsumoDirecto.choices)
    es_del_sistema = models.BooleanField(default=False)
    # No está en el modelo de dominio: clave estable para que las reglas no busquen por nombre (regla 1 de 8.23).
    codigo = models.CharField(max_length=30, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["nombre_tipo_insumo"]
        verbose_name = "Categoría de insumos"
        verbose_name_plural = "Categorías de insumos"
        constraints = [
            # Regla 2 de CMP-ALT-TIN: nombre único sin distinguir mayúsculas, activas e inactivas.
            models.UniqueConstraint(Lower("nombre_tipo_insumo"), name="tipo_insumo_nombre_unico"),
            models.CheckConstraint(
                condition=Q(estado_tipo_insumo__in=["activo", "inactivo"]), name="tipo_insumo_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(consumo_directo__in=["no_admite", "como_gasto", "como_costo_de_los_lotes"]),
                name="tipo_insumo_consumo_directo_valido",
            ),
            # Regla 1 de 8.23: del sistema ⇒ con código y sin consumo directo.
            models.CheckConstraint(
                condition=Q(es_del_sistema=False) | (Q(codigo__isnull=False) & Q(consumo_directo="no_admite")),
                name="tipo_insumo_del_sistema_con_codigo_y_sin_consumo",
            ),
            # Solo las del sistema tienen código.
            models.CheckConstraint(
                condition=Q(codigo__isnull=True) | Q(es_del_sistema=True), name="tipo_insumo_codigo_solo_del_sistema"
            ),
            # CMP-MOD-TIN regla 3: las del sistema no se dan de baja ni se renombran. Respaldo de la base (decidido en
            # INV-01; la ficha del modelo no lo trae): activa, y su (código, nombre) es uno de los cuatro pares fijos.
            models.CheckConstraint(
                condition=Q(es_del_sistema=False)
                | (
                    Q(estado_tipo_insumo="activo")
                    & Q(
                        *[Q(codigo=codigo, nombre_tipo_insumo=nombre) for codigo, nombre in CATEGORIAS_DEL_SISTEMA],
                        _connector=Q.OR,
                    )
                ),
                name="tipo_insumo_del_sistema_fija",
            ),
        ]

    def __str__(self):
        """El nombre: es el texto que guarda la auditoría al referenciarla (D-36)."""
        return self.nombre_tipo_insumo

    @property
    def activo(self):
        """True si la categoría está activa."""
        return self.estado_tipo_insumo == self.Estado.ACTIVO


class Insumo(models.Model):
    """Insumo del catálogo (CMP-ALT-INS y siguientes): nombre, unidad y categoría, compartido por todos los invernaderos. El
    stock, el mínimo y el precio son de `InsumoInvernadero`. Es una semilla si su categoría es la del sistema `semillas`."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    nombre_insumo = models.CharField("nombre", max_length=100)
    descripcion_insumo = models.CharField("descripción", max_length=300, blank=True, default="")
    tipo_insumo = models.ForeignKey(TipoInsumo, on_delete=models.PROTECT, related_name="insumos")  # R153
    unidad_medida_insumo = models.CharField("unidad de medida", max_length=10, choices=Unidad.choices)
    estado_insumo = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)
    controla_vencimiento = models.BooleanField(default=False)

    class Meta:
        ordering = ["nombre_insumo"]
        verbose_name = "Insumo"
        verbose_name_plural = "Insumos"
        constraints = [
            models.UniqueConstraint(Lower("nombre_insumo"), name="insumo_nombre_unico"),
            models.CheckConstraint(
                condition=Q(unidad_medida_insumo__in=[unidad.value for unidad in Unidad]), name="insumo_unidad_valida"
            ),
            models.CheckConstraint(condition=Q(estado_insumo__in=["activo", "inactivo"]), name="insumo_estado_valido"),
        ]

    def __str__(self):
        """El nombre (texto de la auditoría, D-36)."""
        return self.nombre_insumo

    @property
    def activo(self):
        """True si el insumo está activo."""
        return self.estado_insumo == self.Estado.ACTIVO


class InsumoInvernadero(models.Model):
    """Existencia de un insumo del catálogo en un invernadero (R130, R131): su mínimo, su tránsito y su precio de referencia.
    El stock actual NO se guarda: se calcula sumando sus lotes (regla 3 de 8.23; `inventario.servicios.stock`). INV-01 solo
    crea el modelo; INV-02 agrega habilitar, ajustar y deshabilitar."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name="existencias")
    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="insumos_habilitados")
    cant_min_insumo = models.DecimalField("mínimo", max_digits=14, decimal_places=3, default=0)
    # En esta ronda vale 0 y solo la escribirá `compras` (D-45). La columna existe.
    cant_transito_insumo = models.DecimalField("en tránsito", max_digits=14, decimal_places=3, default=0)
    referencia_precio = models.DecimalField("precio de referencia", max_digits=14, decimal_places=2)
    estado_insumo_invernadero = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        ordering = ["id"]
        verbose_name = "Insumo en un invernadero"
        verbose_name_plural = "Insumos en un invernadero"
        constraints = [
            # Regla 1 de 8.4: un solo registro por (insumo, invernadero); un par inactivo se reactiva.
            models.UniqueConstraint(fields=["insumo", "invernadero"], name="insumo_invernadero_unico"),
            models.CheckConstraint(condition=Q(cant_min_insumo__gte=0), name="insumo_invernadero_minimo_no_negativo"),
            models.CheckConstraint(
                condition=Q(cant_transito_insumo__gte=0), name="insumo_invernadero_transito_no_negativo"
            ),
            models.CheckConstraint(condition=Q(referencia_precio__gt=0), name="insumo_invernadero_precio_positivo"),
            models.CheckConstraint(
                condition=Q(estado_insumo_invernadero__in=["activo", "inactivo"]),
                name="insumo_invernadero_estado_valido",
            ),
        ]

    def __str__(self):
        """«Insumo · Invernadero» (texto de la auditoría, D-36)."""
        return f"{self.insumo.nombre_insumo} · {self.invernadero.nombre_invernadero}"

    @property
    def activo(self):
        """True si el insumo está habilitado y activo en el invernadero."""
        return self.estado_insumo_invernadero == self.Estado.ACTIVO


class LoteInsumo(models.Model):
    """Partida de un insumo que entró a un invernadero (R165), con su cantidad y su vencimiento; incluye el lote especial
    «faltante sin lote» (regla 4 de 8.23). NO confundir con `produccion.Lote` (el de plantas)."""

    insumo_invernadero = models.ForeignKey(InsumoInvernadero, on_delete=models.PROTECT, related_name="lotes")
    # Nulos en el faltante sin lote.
    cantidad_ingresada = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    cantidad_disponible = models.DecimalField(max_digits=14, decimal_places=3)
    fecha_ingreso = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    es_faltante_sin_lote = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "Lote de insumo"
        verbose_name_plural = "Lotes de insumo"
        constraints = [
            # Regla 4 de 8.23: a lo sumo un faltante sin lote por InsumoInvernadero.
            models.UniqueConstraint(
                fields=["insumo_invernadero"],
                condition=Q(es_faltante_sin_lote=True),
                name="lote_insumo_un_faltante_por_existencia",
            ),
            # El faltante: nunca positivo y sin cantidad ingresada, ingreso ni vencimiento.
            models.CheckConstraint(
                condition=Q(es_faltante_sin_lote=False)
                | (
                    Q(cantidad_disponible__lte=0)
                    & Q(cantidad_ingresada__isnull=True)
                    & Q(fecha_ingreso__isnull=True)
                    & Q(fecha_vencimiento__isnull=True)
                ),
                name="lote_insumo_faltante_valido",
            ),
            # Un lote común: disponible ≥ 0, ingresada > 0 y fecha de ingreso. (El vencimiento obligatorio según el insumo
            # depende de otra tabla: lo verifica el servicio.)
            models.CheckConstraint(
                condition=Q(es_faltante_sin_lote=True)
                | (
                    Q(cantidad_disponible__gte=0)
                    & Q(cantidad_ingresada__isnull=False)  # un CHECK con NULL «pasa»: hay que pedir el no nulo
                    & Q(cantidad_ingresada__gt=0)
                    & Q(fecha_ingreso__isnull=False)
                ),
                name="lote_insumo_comun_valido",
            ),
        ]

    def __str__(self):
        """«Lote N» o «Faltante sin lote» (texto de la auditoría, D-36)."""
        return "Faltante sin lote" if self.es_faltante_sin_lote else f"Lote {self.pk}"


class MovimientoInsumo(OrigenDocumento):
    """Kárdex: todo cambio de `cantidad_disponible` de un lote genera exactamente un movimiento de ese lote (regla 1 de 8.19).

    Hereda de `contabilidad.OrigenDocumento` (D-52, herencia multitabla; clave `origendocumento_ptr`, `.id` sigue
    funcionando): cada movimiento de ajuste es su propio documento de origen. NO redeclara `save()`: el del padre fija `tipo`
    desde `TIPO_DE_ORIGEN`. Su propio tipo se llama `tipo_movimiento` (el `tipo` ya es del padre; ver el encabezado).
    """

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.MOVIMIENTO_DE_INSUMO

    class TipoMovimiento(models.TextChoices):
        INGRESO_POR_RECEPCION = "ingreso_por_recepcion", "Ingreso por recepción"  # lo crea `compras` (ronda futura)
        SALIDA_POR_CONSUMO = "salida_por_consumo", "Salida por consumo"
        AJUSTE_POSITIVO = "ajuste_positivo", "Ajuste positivo"
        AJUSTE_NEGATIVO = "ajuste_negativo", "Ajuste negativo"
        SALIDA_POR_CORRECCION = "salida_por_correccion", "Salida por corrección entre lotes"
        ENTRADA_POR_CORRECCION = "entrada_por_correccion", "Entrada por corrección entre lotes"

    class MotivoAjuste(models.TextChoices):
        RECUENTO_FISICO = "recuento_fisico", "Recuento físico"
        ROTURA_O_PERDIDA = "rotura_o_perdida", "Rotura o pérdida"
        CARGA_INICIAL = "carga_inicial", "Carga inicial"
        VENCIMIENTO = "vencimiento", "Vencimiento"
        OTRO = "otro", "Otro"

    lote_insumo = models.ForeignKey(LoteInsumo, on_delete=models.PROTECT, related_name="movimientos")  # R166
    # La fecha de la operación con la hora actual; en una salida de siembra, la efectiva (D-50 punto 7).
    fecha = models.DateTimeField(default=timezone.now)
    cantidad = models.DecimalField(max_digits=14, decimal_places=3)  # siempre positiva: el sentido lo da el tipo
    tipo_movimiento = models.CharField(max_length=30, choices=TipoMovimiento.choices)
    motivo_ajuste = models.CharField(max_length=30, choices=MotivoAjuste.choices, null=True, blank=True)
    descripcion_ajuste = models.TextField(blank=True, default="")
    # R016 (D-52 puntos 2 y 4): reemplaza a `movimiento_origen`. Salida por consumo → el Consumo (produccion); entrada por
    # corrección → su salida; ingreso por recepción → la recepción (compras). Que sea el documento correcto lo verifica el
    # servicio o la app que lo crea (A1: inventario no puede nombrarlos).
    origen = models.ForeignKey(
        OrigenDocumento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_de_insumo",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Movimiento de insumo"
        verbose_name_plural = "Movimientos de insumo"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="movimiento_insumo_cantidad_positiva"),
            models.CheckConstraint(
                condition=Q(
                    tipo_movimiento__in=[
                        "ingreso_por_recepcion",
                        "salida_por_consumo",
                        "ajuste_positivo",
                        "ajuste_negativo",
                        "salida_por_correccion",
                        "entrada_por_correccion",
                    ]
                ),
                name="movimiento_insumo_tipo_valido",
            ),
            # motivo_ajuste no nulo si y solo si es un ajuste, y dentro de la lista.
            models.CheckConstraint(
                condition=(
                    Q(tipo_movimiento__in=["ajuste_positivo", "ajuste_negativo"])
                    & Q(motivo_ajuste__isnull=False)  # un CHECK con NULL «pasa»: hay que pedir el no nulo
                    & Q(
                        motivo_ajuste__in=["recuento_fisico", "rotura_o_perdida", "carga_inicial", "vencimiento", "otro"]
                    )
                )
                | (~Q(tipo_movimiento__in=["ajuste_positivo", "ajuste_negativo"]) & Q(motivo_ajuste__isnull=True)),
                name="movimiento_insumo_motivo_segun_tipo",
            ),
            # La descripción es obligatoria si el motivo es «otro».
            models.CheckConstraint(
                condition=~Q(motivo_ajuste="otro") | ~Q(descripcion_ajuste=""),
                name="movimiento_insumo_otro_con_descripcion",
            ),
            # Regla 3 de 8.19 (D-52 punto 4): origen nulo si y solo si es ajuste o salida por corrección entre lotes.
            models.CheckConstraint(
                condition=(
                    Q(tipo_movimiento__in=["ajuste_positivo", "ajuste_negativo", "salida_por_correccion"])
                    & Q(origen__isnull=True)
                )
                | (
                    ~Q(tipo_movimiento__in=["ajuste_positivo", "ajuste_negativo", "salida_por_correccion"])
                    & Q(origen__isnull=False)
                ),
                name="movimiento_insumo_origen_segun_tipo",
            ),
        ]

    def __str__(self):
        """«Tipo de movimiento #N» (texto de la auditoría, D-36)."""
        return f"{self.get_tipo_movimiento_display()} #{self.pk}"
