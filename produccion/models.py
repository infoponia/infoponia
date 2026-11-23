# Modelos de `produccion` (nivel 5 de D-37), PRD-01: OrdenTrabajo, ReservaInsumo, Siembra, OcupacionSector, Lote, Bitacora y Consumo.
# Fuente: docs/modelo/produccion.md (fichas y reglas 8.9, 8.13, 8.20, 8.21 y 8.22) y D-50 a D-53. Cantidades de insumo: Decimal con
# 3 decimales; montos: Decimal(14, 2); plantas y agujeros: enteros. Nunca float. Nada se borra (D-36): las FK son PROTECT, una orden
# se cancela y un lote se finaliza. A2 de D-37: las FK a `maestros`, `inventario`, `contabilidad` y `core` se declaran acá.
#
# DIFERENCIA CON LA DOCUMENTACIÓN: el campo discriminador que la ficha llama `tipo` se llama `tipo_orden`, porque
# `contabilidad.OrigenDocumento` (padre, D-52) ya tiene un campo `tipo` y Django no admite el mismo nombre en la hija
# (FieldError). Mismo caso que `MovimientoInsumo.tipo_movimiento` (INV-01). Decidido por el estudiante en PRD-01; anotado en el
# cierre y en docs/temas_abiertos.md.
#
# PRD-02 suma `TransicionEtapa`, `Merma` y `AlertaDeMerma`; PRD-03 suma `AplicacionInsumos` (hija de `Bitacora`), `ImputacionCosto`, el
# origen `aplicacion` del `Consumo` (D-51 puntos 3 y 4) y los tipos de bitácora `aplicacion`, `otro_evento` y `consumo`. NO hay todavía
# tablas de PRD-04 (`FueraDeServicio`, `Reubicacion`): sus tipos de evento los suma esa tarea. `OrdenTrabajo.Tipo` ya nace con los cinco
# valores (D-67 punto 1), para que las tareas siguientes no cambien sus `choices` ni sus restricciones.

from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from core.models import Agronomo, Capataz, Usuario
from inventario.models import InsumoInvernadero
from maestros.models import Alerta, EtapaProductiva, Invernadero, SectorProduccion, Variedad


class ConCapataz(models.Model):
    """Clase abstracta (D-53): el Capataz asignado a la orden. La heredan `Siembra` y, después, `TransicionEtapa` y `Cosecha`.
    No crea tabla. Quien necesite «las órdenes de un Capataz» llama a `ordenes.ordenes_del_capataz`: nadie arma esa unión."""

    # R075, R077, R078. El índice lo crea la propia FK.
    capataz = models.ForeignKey(Capataz, on_delete=models.PROTECT, related_name="%(class)s_asignadas")

    class Meta:
        abstract = True


class OrdenTrabajo(OrigenDocumento):
    """Orden planificada por el Agrónomo (o por InfoPonia) para que el Capataz (o el Técnico) la realice (docs/modelo/produccion.md).

    Hija directa de `OrigenDocumento` (D-52): `TIPO_DE_ORIGEN = orden_de_trabajo`, su clave es `origendocumento_ptr`. Es el padre de
    `Siembra` (acá) y de las hijas de las tareas siguientes. Su código legible es `OT-{numero:04d}`."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.ORDEN_DE_TRABAJO

    class Tipo(models.TextChoices):
        """Los cinco valores nacen en PRD-01 (D-67 punto 1), aunque las hijas lleguen después."""

        SIEMBRA = "siembra", "Siembra"
        TRANSICION = "transicion", "Transición de etapa"
        COSECHA = "cosecha", "Cosecha"
        ENTREGA = "entrega", "Entrega"
        MANTENIMIENTO = "mantenimiento", "Mantenimiento técnico"

    class Estado(models.TextChoices):
        A_REALIZAR = "a_realizar", "a realizar"
        CONCRETADA = "concretada", "concretada"
        CANCELADA = "cancelada", "cancelada"

    class Prioridad(models.TextChoices):
        ALTA = "alta", "Alta"
        MEDIA = "media", "Media"
        BAJA = "baja", "Baja"

    # Discriminador de la herencia (la ficha lo llama `tipo`; ver el encabezado). Obligatorio y nunca cambia.
    tipo_orden = models.CharField(max_length=20, choices=Tipo.choices)
    # Lo asigna el servicio con la secuencia `produccion_orden_numero_seq` (D-52 punto 3); puede haber huecos.
    numero = models.PositiveIntegerField(unique=True)
    fecha_creacion_orden = models.DateField(default=timezone.localdate)  # nunca posterior a hoy: lo verifica el servicio
    fecha_programada_orden = models.DateField()
    fecha_resolucion_orden = models.DateField(null=True, blank=True)
    descripcion_orden = models.CharField(max_length=500, blank=True, default="")
    estado_orden = models.CharField(max_length=20, choices=Estado.choices, default=Estado.A_REALIZAR)
    prioridad_orden = models.CharField(max_length=10, choices=Prioridad.choices, null=True, blank=True)  # MD-73
    motivo_cancelacion = models.CharField(max_length=300, null=True, blank=True)  # PROD-CNL-ORD; ver «Diferencias», n.º 17
    # R046: nulo = planificó InfoPonia. D-50: sube al padre.
    agronomo = models.ForeignKey(Agronomo, null=True, blank=True, on_delete=models.PROTECT, related_name="ordenes_planificadas")
    # R136 (+ R099 en la transición). D-50: sube al padre.
    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="ordenes")

    class Meta:
        verbose_name = "Orden de trabajo"
        verbose_name_plural = "Órdenes de trabajo"
        indexes = [models.Index(fields=["invernadero", "estado_orden", "fecha_programada_orden"], name="orden_trabajo_lista_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_orden__in=["siembra", "transicion", "cosecha", "entrega", "mantenimiento"]),
                name="orden_trabajo_tipo_valido",
            ),
            models.CheckConstraint(
                condition=Q(estado_orden__in=["a_realizar", "concretada", "cancelada"]), name="orden_trabajo_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(prioridad_orden__isnull=True) | Q(prioridad_orden__in=["alta", "media", "baja"]),
                name="orden_trabajo_prioridad_valida",
            ),
            # `fecha_resolucion_orden` es nula si y solo si la orden está «a realizar».
            models.CheckConstraint(
                condition=(Q(estado_orden="a_realizar") & Q(fecha_resolucion_orden__isnull=True))
                | (~Q(estado_orden="a_realizar") & Q(fecha_resolucion_orden__isnull=False)),
                name="orden_trabajo_resolucion_segun_estado",
            ),
            # `motivo_cancelacion` no nulo y no vacío si y solo si está «cancelada» (un CHECK con NULL «pasa»: se pide el no nulo).
            models.CheckConstraint(
                condition=(Q(estado_orden="cancelada") & Q(motivo_cancelacion__isnull=False) & ~Q(motivo_cancelacion=""))
                | (~Q(estado_orden="cancelada") & Q(motivo_cancelacion__isnull=True)),
                name="orden_trabajo_motivo_segun_estado",
            ),
            models.CheckConstraint(
                condition=Q(fecha_programada_orden__gte=F("fecha_creacion_orden")), name="orden_trabajo_programada_desde_creacion"
            ),
        ]

    def __str__(self):
        """El código (texto de la auditoría y de las notificaciones, D-36)."""
        return self.codigo

    @property
    def codigo(self):
        """`OT-0001`: lo que muestran las pantallas y los avisos."""
        return f"OT-{self.numero:04d}"


class ReservaInsumo(models.Model):
    """Compromiso temporal de una cantidad de un insumo del invernadero, generado al planificar una orden y resuelto al
    concretarla o cancelarla (R138, R139). Lo consumido no se guarda: es `cantidad_reservada − cantidad_devuelta`."""

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        CONSUMIDA = "consumida", "Consumida"
        CANCELADA = "cancelada", "Cancelada"

    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.PROTECT, related_name="reservas")  # R138
    insumo_invernadero = models.ForeignKey(InsumoInvernadero, on_delete=models.PROTECT, related_name="reservas")  # R139
    cantidad_reservada = models.DecimalField(max_digits=14, decimal_places=3)
    cantidad_utilizada = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    cantidad_devuelta = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVA)
    fecha_reserva = models.DateField(default=timezone.localdate)

    class Meta:
        verbose_name = "Reserva de insumo"
        verbose_name_plural = "Reservas de insumo"
        indexes = [models.Index(fields=["insumo_invernadero", "estado"], name="reserva_insumo_stock_idx")]
        constraints = [
            # Sin condición en PRD-01 (la cambia COM-05a2 a «a lo sumo una activa», D-66 punto 8).
            models.UniqueConstraint(fields=["orden", "insumo_invernadero"], name="reserva_insumo_unica_por_orden"),
            models.CheckConstraint(condition=Q(cantidad_reservada__gt=0), name="reserva_insumo_reservada_positiva"),
            models.CheckConstraint(
                condition=Q(estado__in=["activa", "consumida", "cancelada"]), name="reserva_insumo_estado_valido"
            ),
            # Activa: ambas nulas. Consumida: ambas cargadas. Cancelada: ambas nulas (cancelación de la orden) o ambas cargadas.
            models.CheckConstraint(
                condition=(Q(estado="activa") & Q(cantidad_utilizada__isnull=True) & Q(cantidad_devuelta__isnull=True))
                | (Q(estado="consumida") & Q(cantidad_utilizada__isnull=False) & Q(cantidad_devuelta__isnull=False))
                | (Q(estado="cancelada") & Q(cantidad_utilizada__isnull=True) & Q(cantidad_devuelta__isnull=True))
                | (Q(estado="cancelada") & Q(cantidad_utilizada__isnull=False) & Q(cantidad_devuelta__isnull=False)),
                name="reserva_insumo_cantidades_segun_estado",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_utilizada__isnull=True) | Q(cantidad_utilizada__gte=0),
                name="reserva_insumo_utilizada_no_negativa",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_devuelta__isnull=True) | Q(cantidad_devuelta__gte=0),
                name="reserva_insumo_devuelta_no_negativa",
            ),
            # Para siempre (D-68 punto 2): la utilizada nunca supera la reservada; el exceso de envases va en el consumo.
            models.CheckConstraint(
                condition=Q(cantidad_utilizada__isnull=True) | Q(cantidad_utilizada__lte=F("cantidad_reservada")),
                name="reserva_insumo_utilizada_hasta_reservada",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_devuelta__isnull=True)
                | Q(cantidad_utilizada__isnull=True)
                | Q(cantidad_devuelta__lte=F("cantidad_reservada") - F("cantidad_utilizada")),
                name="reserva_insumo_devuelta_hasta_lo_no_utilizado",
            ),
        ]

    def __str__(self):
        """«Reserva #N» (texto de la auditoría, D-36)."""
        return f"Reserva #{self.pk}"


class Siembra(OrdenTrabajo, ConCapataz):
    """Orden de sembrar una variedad en sectores de Germinación; al concretarla crea el lote (`tipo_orden = siembra`).
    Su clave es `ordentrabajo_ptr`. El Capataz viene de `ConCapataz` (D-53)."""

    cant_plantines_siembra = models.PositiveIntegerField()  # la planificada: no cambia al concretar (la real es Lote.cantidad_inicial)
    fecha_siembra = models.DateField(null=True, blank=True)  # nula mientras está «a realizar»; la efectiva al concretar
    motivo_diferencia_siembra = models.CharField(max_length=300, blank=True, default="")
    variedad = models.ForeignKey(Variedad, on_delete=models.PROTECT, related_name="siembras")  # R104

    class Meta:
        verbose_name = "Siembra"
        verbose_name_plural = "Siembras"
        constraints = [
            models.CheckConstraint(condition=Q(cant_plantines_siembra__gt=0), name="siembra_plantines_positivos"),
        ]


class Lote(models.Model):
    """Plantas de una misma siembra que atraviesan juntas las etapas del ciclo (R099, R100, R103). Lo crea Concretar Siembra.
    No hereda: su `id` es propio y su código es `L-{id}`. Nunca se borra: se finaliza al llegar a cero plantas."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        FINALIZADO = "finalizado", "Finalizado"

    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="lotes")  # R099
    etapa = models.ForeignKey(EtapaProductiva, on_delete=models.PROTECT, related_name="lotes")  # R100: la etapa ACTUAL
    siembra = models.OneToOneField(Siembra, on_delete=models.PROTECT, related_name="lote")  # R103 (de ahí sale la variedad)
    cantidad_inicial = models.PositiveIntegerField()
    cantidad_actual = models.PositiveIntegerField()
    estado_lote = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)
    # docs/patrones/costo_del_lote.md: se guarda, y solo lo cambian las funciones de `costos.py`.
    costo_acumulado = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_inicial__gt=0), name="lote_inicial_positiva"),
            models.CheckConstraint(condition=Q(cantidad_actual__lte=F("cantidad_inicial")), name="lote_actual_hasta_inicial"),
            models.CheckConstraint(condition=Q(estado_lote__in=["activo", "finalizado"]), name="lote_estado_valido"),
            models.CheckConstraint(condition=Q(costo_acumulado__gte=0), name="lote_costo_no_negativo"),
            # «finalizado» si y solo si no quedan plantas.
            models.CheckConstraint(
                condition=(Q(estado_lote="finalizado") & Q(cantidad_actual=0))
                | (Q(estado_lote="activo") & Q(cantidad_actual__gt=0)),
                name="lote_finalizado_si_y_solo_si_sin_plantas",
            ),
            models.CheckConstraint(
                condition=Q(cantidad_actual__gt=0) | Q(costo_acumulado=0), name="lote_sin_plantas_sin_costo"
            ),
        ]

    def __str__(self):
        """El código (texto de la auditoría, D-36)."""
        return self.codigo

    @property
    def codigo(self):
        """`L-1`: lo que muestran las pantallas y los avisos."""
        return f"L-{self.pk}"


class OcupacionSector(models.Model):
    """Lo que una orden planifica ocupar en un sector y, una vez concretada, lo que el lote ocupa de verdad (R094, R095, R140).
    Los agujeros comprometidos y ocupados de un sector se DERIVAN de estas filas (D-50 punto 4): no se guardan en el sector."""

    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.PROTECT, related_name="ocupaciones")  # R140; PRD-04 la vuelve nula (D-51)
    sector = models.ForeignKey(SectorProduccion, on_delete=models.PROTECT, related_name="ocupaciones")  # R095
    # Tiene lote si y solo si la orden está concretada y ocupó al menos un agujero al concretar; lo conserva aunque los libere.
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.PROTECT, related_name="ocupaciones")  # R094
    cant_agujeros_planificados = models.PositiveIntegerField()  # se fija al planificar y no cambia
    cant_agujeros_ocupados = models.PositiveIntegerField(default=0)  # cero mientras la orden está «a realizar»

    class Meta:
        verbose_name = "Ocupación de sector"
        verbose_name_plural = "Ocupaciones de sector"
        constraints = [
            models.CheckConstraint(condition=Q(cant_agujeros_planificados__gt=0), name="ocupacion_planificados_positivos"),
            models.CheckConstraint(
                condition=Q(cant_agujeros_ocupados__lte=F("cant_agujeros_planificados")),
                name="ocupacion_ocupados_hasta_planificados",
            ),
            # Una orden usa un sector una sola vez (PRD-04 la cambia a condicional, D-51 punto 1).
            models.UniqueConstraint(fields=["orden", "sector"], name="ocupacion_unica_por_orden_y_sector"),
        ]

    def __str__(self):
        """«Ocupación #N» (texto de la auditoría, D-36)."""
        return f"Ocupación #{self.pk}"


class Bitacora(OrigenDocumento):
    """Registro de un evento con fecha, hora y responsable (R081, R082, R106). Hija directa de `OrigenDocumento` (D-52):
    `TIPO_DE_ORIGEN = bitacora`. En PRD-01 solo la escribe el consumo de una siembra (`Consumo` es su hija)."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.BITACORA

    class TipoEvento(models.TextChoices):
        """`siembra`, `transicion` y `merma` nacen en PRD-01; PRD-03 suma `aplicacion`, `otro_evento` y el interno `consumo` (el de una
        aplicación: la consulta de la bitácora no lo lista, D-51 punto 3); los demás los suman sus tareas (PRD-04, COM-04a, IOT-05)."""

        SIEMBRA = "siembra", "Siembra"
        TRANSICION = "transicion", "Transición de etapa"
        MERMA = "merma", "Merma"
        APLICACION = "aplicacion", "Aplicación de insumos"
        OTRO_EVENTO = "otro_evento", "Otro evento"
        CONSUMO = "consumo", "Consumo"  # interno: no se lista en la bitácora

    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="bitacoras")  # R081
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.PROTECT, related_name="bitacoras")  # R082
    etapa = models.ForeignKey(  # R106: la etapa del lote en ese momento
        EtapaProductiva, null=True, blank=True, on_delete=models.PROTECT, related_name="bitacoras"
    )
    # MD-28 + MD-77 (D-51 punto 2): en una siembra, los sectores donde se sembró al menos una planta.
    sectores = models.ManyToManyField(SectorProduccion, blank=True, related_name="bitacoras")
    # R076 + MD-77: nulo = lo registró InfoPonia. Una sola clave a `core.Usuario`.
    responsable = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="registros_de_bitacora"
    )
    fecha_bitacora = models.DateField()  # nunca posterior a hoy: lo verifica el servicio
    hora_bitacora = models.TimeField()
    tipo_evento = models.CharField(max_length=30, choices=TipoEvento.choices)
    descripcion_evento = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Registro de bitácora"
        verbose_name_plural = "Bitácora"
        indexes = [
            models.Index(fields=["invernadero", "fecha_bitacora"], name="bitacora_invernadero_fecha_idx"),
            models.Index(fields=["lote", "fecha_bitacora", "hora_bitacora"], name="bitacora_lote_fecha_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_evento__in=["siembra", "transicion", "merma", "aplicacion", "otro_evento", "consumo"]),
                name="bitacora_tipo_evento_valido",
            ),
        ]

    def __str__(self):
        """«Bitácora #N» (texto de la auditoría, D-36)."""
        return f"Bitácora #{self.pk}"


class AplicacionInsumos(Bitacora):
    """Uso de insumos sin una orden de trabajo, como la limpieza o los nutrientes (PROD-REG-APL; MD-28, D-51). Hija de `Bitacora` con
    `tipo_evento = aplicacion`: que lo sea lo garantiza el servicio (una restricción de la hija no ve el campo del padre). No tiene
    atributos propios: usa la fecha y la hora actuales, la descripción, el invernadero y el responsable de `Bitacora`, sin lote ni etapa.
    El alcance va en `Bitacora.sectores` (vacío = todo el invernadero); sus consumos, en `Consumo.aplicacion`."""

    class Meta:
        verbose_name = "Aplicación de insumos"
        verbose_name_plural = "Aplicaciones de insumos"

    def __str__(self):
        """«Aplicación #N» (texto de la auditoría, D-36)."""
        return f"Aplicación #{self.pk}"


class Consumo(Bitacora):
    """Un consumo por cada reserva de insumo de la siembra que se consumió (cantidad consumida mayor que cero), o por cada insumo de una
    aplicación (PRD-03: fila de bitácora de tipo interno `consumo`). Hijo de `Bitacora` con `tipo_evento = siembra` o `consumo`. Sus
    movimientos de insumo llevan `origen = este consumo` (D-52): no hay tabla de enlace. Se crea ANTES que sus movimientos."""

    monto_consumo = models.DecimalField(max_digits=14, decimal_places=2)  # cant_consumo × precio de referencia al concretar; fijo
    cant_consumo = models.DecimalField(max_digits=14, decimal_places=3)  # reservada − devuelta
    fecha_consumo = models.DateField()  # la fecha efectiva de la siembra
    insumo_invernadero = models.ForeignKey(InsumoInvernadero, on_delete=models.PROTECT, related_name="consumos")  # R045
    # R105. Exactamente uno de `siembra` y `aplicacion` (D-51 punto 3, regla 7 de 8.4 con MD-28); COM-04a suma el tercero, `orden`.
    siembra = models.ForeignKey(Siembra, null=True, blank=True, on_delete=models.PROTECT, related_name="consumos")
    aplicacion = models.ForeignKey(AplicacionInsumos, null=True, blank=True, on_delete=models.PROTECT, related_name="consumos")

    class Meta:
        verbose_name = "Consumo"
        verbose_name_plural = "Consumos"
        constraints = [
            models.CheckConstraint(condition=Q(monto_consumo__gte=0), name="consumo_monto_no_negativo"),
            models.CheckConstraint(condition=Q(cant_consumo__gt=0), name="consumo_cantidad_positiva"),
            # Un solo origen (D-51 punto 3): reemplaza a la de PRD-01 («`siembra` no nula», `consumo_origen_es_siembra`).
            models.CheckConstraint(
                condition=(Q(siembra__isnull=False) & Q(aplicacion__isnull=True))
                | (Q(siembra__isnull=True) & Q(aplicacion__isnull=False)),
                name="consumo_un_solo_origen",
            ),
        ]

    def __str__(self):
        """«Consumo #N» (texto de la auditoría, D-36)."""
        return f"Consumo #{self.pk}"


class TransicionEtapa(OrdenTrabajo, ConCapataz):
    """Orden de trasladar el lote ENTERO a la etapa siguiente de su ciclo (`tipo_orden = transicion`; docs/modelo/produccion.md).
    Su clave es `ordentrabajo_ptr`. El Capataz viene de `ConCapataz` (D-53). La etapa de origen no se guarda (regla 1 de 8.20).

    Un lote tiene a lo sumo UNA transición «a realizar» (regla 4 de 8.21): el estado vive en el padre y una restricción de la base no
    cruza tablas, así que lo garantiza el servicio con el bloqueo del lote y lo prueba la concurrencia (docs/patrones/bloqueos.md).
    Por la misma razón, «`cant_transferido` y `fecha_transicion` están cargados si y solo si la orden está concretada» lo cumple el
    servicio; la base solo exige que se carguen juntos y que la cantidad sea positiva."""

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="transiciones")  # R160
    etapa_destino = models.ForeignKey(EtapaProductiva, on_delete=models.PROTECT, related_name="transiciones")  # R107
    # Nulos mientras la orden está «a realizar» o «cancelada»; al concretar, la suma de los ocupados y la fecha efectiva (MD-53).
    cant_transferido = models.PositiveIntegerField(null=True, blank=True)
    fecha_transicion = models.DateField(null=True, blank=True)
    # R080: el registro de bitácora que genera al concretarse; nulo hasta entonces. DIFERENCIA CON LA DOCUMENTACIÓN: la ficha lo llama
    # `bitacora`, pero `OrigenDocumento` ya tiene el accesorio `bitacora` (su hija) y Django no admite el choque (models.E006), como
    # con `tipo_orden` (D-81). Anotado en el cierre y en docs/temas_abiertos.md.
    bitacora_de_transicion = models.OneToOneField(Bitacora, null=True, blank=True, on_delete=models.PROTECT, related_name="transicion")

    class Meta:
        verbose_name = "Transición de etapa"
        verbose_name_plural = "Transiciones de etapa"
        constraints = [
            models.CheckConstraint(
                condition=Q(cant_transferido__isnull=True) | Q(cant_transferido__gt=0), name="transicion_transferido_positivo"
            ),
            models.CheckConstraint(
                condition=Q(cant_transferido__isnull=True, fecha_transicion__isnull=True)
                | Q(cant_transferido__isnull=False, fecha_transicion__isnull=False),
                name="transicion_cantidad_y_fecha_juntas",
            ),
        ]


class Merma(Bitacora):
    """Plantas de un lote que se perdieron o se descartaron (`tipo_evento = merma`; R082, R106). Hija de `Bitacora`. La crea el núcleo
    `mermas.aplicar_merma`; que `tipo_evento` sea «merma» lo garantiza el servicio (una restricción de la hija no ve el campo del padre).
    PRD-03 la completa con la pantalla; COM-04a suma las causas de cámara y de entrega."""

    class Causa(models.TextChoices):
        """Las del lote en pie (MD-78). El «descarte por selección» no suma a la merma acumulada (regla de PROD-REG-MRM)."""

        PLAGA = "plaga", "Plaga"
        ENFERMEDAD = "enfermedad", "Enfermedad"
        FALLA_RIEGO_O_NUTRIENTES = "falla_riego_o_nutrientes", "Falla de riego o nutrientes"
        CONDICIONES_AMBIENTALES = "condiciones_ambientales", "Condiciones ambientales"
        DANO_MECANICO = "dano_mecanico", "Daño mecánico"
        DESCARTE_POR_SELECCION = "descarte_por_seleccion", "Descarte por selección"
        OTRA = "otra", "Otra"

    cant_merma = models.PositiveIntegerField()
    causa = models.CharField(max_length=30, choices=Causa.choices)

    class Meta:
        verbose_name = "Merma"
        verbose_name_plural = "Mermas"
        constraints = [
            models.CheckConstraint(condition=Q(cant_merma__gt=0), name="merma_cantidad_positiva"),
            models.CheckConstraint(
                condition=Q(
                    causa__in=[
                        "plaga",
                        "enfermedad",
                        "falla_riego_o_nutrientes",
                        "condiciones_ambientales",
                        "dano_mecanico",
                        "descarte_por_seleccion",
                        "otra",
                    ]
                ),
                name="merma_causa_valida",
            ),
        ]

    def __str__(self):
        """«Merma #N» (texto de la auditoría, D-36)."""
        return f"Merma #{self.pk}"


class AlertaDeMerma(models.Model):
    """Tabla de enlace (A2, restricción C5): una alerta de las dos que puede disparar una merma (umbral y plantas comprometidas) con
    su merma de origen (docs/api/alertas.md, sección 4). Se crea en la misma transacción que la alerta."""

    merma = models.ForeignKey(Merma, on_delete=models.PROTECT, related_name="alertas_de_merma")  # R089
    alerta = models.OneToOneField(Alerta, on_delete=models.PROTECT, related_name="de_merma")

    class Meta:
        verbose_name = "Alerta de merma"
        verbose_name_plural = "Alertas de merma"

    def __str__(self):
        """«Alerta de merma #N» (texto de la auditoría, D-36)."""
        return f"Alerta de merma #{self.pk}"


class ImputacionCosto(models.Model):
    """Parte del costo de un consumo de aplicación que recibe un lote de plantas (MD-28, D-51 punto 4). La suma de las imputaciones de un
    consumo es exactamente su `monto_consumo` (la verifica el servicio y la prueba de invariantes) y cada una suma a `Lote.costo_acumulado`
    (docs/patrones/costo_del_lote.md). Un lote que recibe cero no tiene imputación."""

    consumo = models.ForeignKey(Consumo, on_delete=models.PROTECT, related_name="imputaciones")
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="imputaciones")
    monto_imputado = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Imputación de costo"
        verbose_name_plural = "Imputaciones de costo"
        constraints = [
            models.UniqueConstraint(fields=["consumo", "lote"], name="imputacion_unica_por_consumo_y_lote"),
            models.CheckConstraint(condition=Q(monto_imputado__gte=0), name="imputacion_monto_no_negativo"),
        ]

    def __str__(self):
        """«Imputación #N» (texto de la auditoría, D-36)."""
        return f"Imputación #{self.pk}"
