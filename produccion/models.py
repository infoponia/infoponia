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
# origen `aplicacion` del `Consumo` (D-51 puntos 3 y 4) y los tipos de bitácora `aplicacion`, `otro_evento` y `consumo`. PRD-04 suma
# `FueraDeServicio` y `Reubicacion` (hijas de `Bitacora`), sus tipos de evento y el cambio de `OcupacionSector` (D-51 punto 1: `orden`
# nula y `reubicacion`, exactamente una de las dos). `OrdenTrabajo.Tipo` ya nace con los cinco
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
            # COM-02 (D-59; ronda 19, MD-18): la prioridad es obligatoria en la cosecha.
            models.CheckConstraint(
                condition=~Q(tipo_orden="cosecha") | Q(prioridad_orden__isnull=False), name="orden_trabajo_cosecha_con_prioridad"
            ),
            # IOT-07 (D-53 punto 6, D-73 punto 3; docs/modelo/produccion.md): la prioridad es obligatoria en el mantenimiento. Va aparte de la
            # de la cosecha. El extracto la llama `ordentrabajo_prioridad_en_mantenimiento` y usa `tipo`; el campo real es `tipo_orden`.
            models.CheckConstraint(
                condition=~Q(tipo_orden="mantenimiento") | Q(prioridad_orden__isnull=False),
                name="ordentrabajo_prioridad_en_mantenimiento",
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
            # COM-05a2 (D-66 punto 8; docs/modelo/produccion.md, «Restricciones de la base»): a lo sumo UNA ACTIVA por orden e insumo. Un envase quitado del
            # envasado de una entrega deja su reserva «cancelada» y, si se vuelve a agregar, nace otra. PRD-01 tenía la restricción sin condición.
            models.UniqueConstraint(
                fields=["orden", "insumo_invernadero"], condition=Q(estado="activa"), name="reserva_insumo_una_activa_por_orden"
            ),
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

    class TipoSiembra(models.TextChoices):
        """PRD-05 (D-92 punto 12): el «motivo carga inicial» del caso de uso PROD-REG-LTE. No es `motivo_diferencia_siembra`."""

        NORMAL = "normal", "Normal"
        CARGA_INICIAL = "carga_inicial", "Carga inicial"

    tipo_siembra = models.CharField(max_length=20, choices=TipoSiembra.choices, default=TipoSiembra.NORMAL)
    # PRD-05 (D-92 punto 12; L1: R078 pasa a 0..1): se redeclara `capataz` de `ConCapataz` como nulo. Es nulo si y solo si la siembra es de
    # carga inicial (CHECK `siembra_capataz_segun_tipo`). Django permite redeclarar un campo heredado de una clase abstracta.
    capataz = models.ForeignKey(Capataz, null=True, blank=True, on_delete=models.PROTECT, related_name="%(class)s_asignadas")

    class Meta:
        verbose_name = "Siembra"
        verbose_name_plural = "Siembras"
        constraints = [
            models.CheckConstraint(condition=Q(cant_plantines_siembra__gt=0), name="siembra_plantines_positivos"),
            models.CheckConstraint(condition=Q(tipo_siembra__in=["normal", "carga_inicial"]), name="siembra_tipo_valido"),
            # D-92 punto 12: el Capataz es nulo si y solo si la siembra es de carga inicial (nunca se planificó ni se asignó).
            models.CheckConstraint(
                condition=(Q(tipo_siembra="carga_inicial") & Q(capataz__isnull=True))
                | (~Q(tipo_siembra="carga_inicial") & Q(capataz__isnull=False)),
                name="siembra_capataz_segun_tipo",
            ),
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

    # R140 / R164. Nula si la ocupación nace de una reubicación (PRD-04, D-51 punto 1): exactamente una de `orden` y `reubicacion`.
    orden = models.ForeignKey(OrdenTrabajo, null=True, blank=True, on_delete=models.PROTECT, related_name="ocupaciones")
    # MD-76: las ocupaciones de destino de una reubicación (nacen con planificados = ocupados y con lote).
    reubicacion = models.ForeignKey("Reubicacion", null=True, blank=True, on_delete=models.PROTECT, related_name="ocupaciones")
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
            # Una orden usa un sector una sola vez; una reubicación también (D-51 punto 1, restricción C9 de MD-76).
            models.UniqueConstraint(
                fields=["orden", "sector"], condition=Q(orden__isnull=False), name="ocupacion_unica_por_orden_y_sector"
            ),
            models.UniqueConstraint(
                fields=["reubicacion", "sector"],
                condition=Q(reubicacion__isnull=False),
                name="ocupacion_unica_por_reubicacion_y_sector",
            ),
            # Toda ocupación pertenece exactamente a una orden o a una reubicación (C9).
            models.CheckConstraint(
                condition=(Q(orden__isnull=False) & Q(reubicacion__isnull=True))
                | (Q(orden__isnull=True) & Q(reubicacion__isnull=False)),
                name="ocupacion_orden_o_reubicacion",
            ),
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
        FUERA_DE_SERVICIO = "fuera_de_servicio", "Sector fuera de servicio"  # PRD-04
        REUBICACION = "reubicacion", "Reubicación de plantas"  # PRD-04
        COMANDO = "comando", "Comando"  # IOT-05 (MD-110): lo escribe la hija `iot.RegistroComando`
        COSECHA = "cosecha", "Cosecha"  # COM-04a (D-64 punto 4): uno por cada lote de la cosecha concretada
        # COM-04a (D-69 punto 3; los usa COM-07a): sin lote, etapa ni cosecha.
        INCUMPLIMIENTO_DE_CLAUSULA = "incumplimiento_de_clausula", "Incumplimiento de cláusula suministrante"
        ANULACION_DE_RESOLUCION = "anulacion_de_resolucion", "Anulación de una resolución"
        # PRD-05 (D-92 punto 12; L2/L3): la carga de un lote existente. `etapa` = la actual; `fecha_bitacora` = el ingreso a esa etapa.
        CARGA_INICIAL = "carga_inicial", "Carga inicial"

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
    # R152 (COM-04a, D-64 punto 4): la cosecha que lo generó; `tipo_evento = cosecha` si y solo si no es nula.
    cosecha = models.ForeignKey("Cosecha", null=True, blank=True, on_delete=models.PROTECT, related_name="registros_de_bitacora")

    class Meta:
        verbose_name = "Registro de bitácora"
        verbose_name_plural = "Bitácora"
        indexes = [
            models.Index(fields=["invernadero", "fecha_bitacora"], name="bitacora_invernadero_fecha_idx"),
            models.Index(fields=["lote", "fecha_bitacora", "hora_bitacora"], name="bitacora_lote_fecha_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    tipo_evento__in=[
                        "siembra",
                        "transicion",
                        "merma",
                        "aplicacion",
                        "otro_evento",
                        "consumo",
                        "fuera_de_servicio",
                        "reubicacion",
                        "comando",
                        "cosecha",
                        "incumplimiento_de_clausula",
                        "anulacion_de_resolucion",
                        "carga_inicial",
                    ]
                ),
                name="bitacora_tipo_evento_valido",
            ),
            # COM-04a (D-64 punto 4): `tipo_evento = cosecha` ⇔ `cosecha` no nula.
            models.CheckConstraint(
                condition=(Q(tipo_evento="cosecha") & Q(cosecha__isnull=False)) | (~Q(tipo_evento="cosecha") & Q(cosecha__isnull=True)),
                name="bitacora_cosecha_segun_tipo",
            ),
            # COM-04a (D-69 punto 3): un hecho de contrato no tiene lote, etapa ni cosecha.
            models.CheckConstraint(
                condition=~Q(tipo_evento__in=["incumplimiento_de_clausula", "anulacion_de_resolucion"])
                | (Q(lote__isnull=True) & Q(etapa__isnull=True) & Q(cosecha__isnull=True)),
                name="bitacora_contrato_sin_lote_etapa_ni_cosecha",
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
    # R148 (COM-04a, D-68 punto 3): el consumo de los envases de una entrega (y, en la etapa 2 del IoT, el de un mantenimiento).
    orden = models.ForeignKey(OrdenTrabajo, null=True, blank=True, on_delete=models.PROTECT, related_name="consumos_de_orden")

    class Meta:
        verbose_name = "Consumo"
        verbose_name_plural = "Consumos"
        constraints = [
            models.CheckConstraint(condition=Q(monto_consumo__gte=0), name="consumo_monto_no_negativo"),
            models.CheckConstraint(condition=Q(cant_consumo__gt=0), name="consumo_cantidad_positiva"),
            # Un solo origen (D-51 punto 3; COM-04a suma el tercero, `orden`, D-68 punto 3): exactamente uno de los tres.
            models.CheckConstraint(
                condition=(Q(siembra__isnull=False) & Q(aplicacion__isnull=True) & Q(orden__isnull=True))
                | (Q(siembra__isnull=True) & Q(aplicacion__isnull=False) & Q(orden__isnull=True))
                | (Q(siembra__isnull=True) & Q(aplicacion__isnull=True) & Q(orden__isnull=False)),
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
        # COM-04a (D-64 y D-68 punto 3): no se ofrecen en un lote en pie (`CAUSAS_EN_PIE`).
        DANO_EN_CAMARA = "dano_en_camara", "Daño en cámara"
        VENCIMIENTO_EN_CAMARA = "vencimiento_en_camara", "Vencimiento en cámara"
        DANO_EN_ENTREGA = "dano_en_entrega", "Daño en la entrega"

    # Las que valen en un lote en pie (PROD-REG-MRM): las siete de PRD-02. Los servicios validan contra esta lista, no contra `Causa`.
    CAUSAS_EN_PIE = (
        Causa.PLAGA,
        Causa.ENFERMEDAD,
        Causa.FALLA_RIEGO_O_NUTRIENTES,
        Causa.CONDICIONES_AMBIENTALES,
        Causa.DANO_MECANICO,
        Causa.DESCARTE_POR_SELECCION,
        Causa.OTRA,
    )

    cant_merma = models.PositiveIntegerField()
    causa = models.CharField(max_length=30, choices=Causa.choices)
    # R084 (COM-04a, D-68 punto 3): la entrega que presenta la merma; solo con la causa `dano_en_entrega`.
    orden = models.ForeignKey(OrdenTrabajo, null=True, blank=True, on_delete=models.PROTECT, related_name="mermas_de_orden")

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
                        "dano_en_camara",
                        "vencimiento_en_camara",
                        "dano_en_entrega",
                    ]
                ),
                name="merma_causa_valida",
            ),
            # COM-04a (D-68 punto 3): `orden` no nula ⇔ `causa = dano_en_entrega`.
            models.CheckConstraint(
                condition=(Q(causa="dano_en_entrega") & Q(orden__isnull=False)) | (~Q(causa="dano_en_entrega") & Q(orden__isnull=True)),
                name="merma_orden_segun_causa",
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


class FueraDeServicio(Bitacora):
    """Constancia de que un sector pasó a «fuera de servicio» (PROD-PNR-FDS; MD-75, D-51). Hija de `Bitacora` con
    `tipo_evento = fuera_de_servicio` (lo garantiza el servicio: una restricción de la hija no ve el campo del padre). El sector va
    también en `Bitacora.sectores` (uno, obligatorio). La fecha efectiva es la `fecha_bitacora` y la hora es la actual.
    A lo sumo un registro abierto (`fecha_fin` nula) por sector; `fecha_fin >= fecha_efectiva` lo verifica el servicio que lo cierra
    (la restricción de la hija no ve `fecha_bitacora`, que es de la tabla padre)."""

    motivo_fuera_de_servicio = models.CharField(max_length=300)
    # Nula mientras el sector sigue fuera de servicio; la cargan la vuelta a servicio y las bajas (sector e invernadero).
    fecha_fin = models.DateField(null=True, blank=True)
    # Columna propia para respaldar con una restricción de la base que un sector no tenga dos registros abiertos.
    sector = models.ForeignKey(SectorProduccion, on_delete=models.PROTECT, related_name="registros_fuera_de_servicio")

    class Meta:
        verbose_name = "Sector fuera de servicio"
        verbose_name_plural = "Sectores fuera de servicio"
        constraints = [
            models.UniqueConstraint(
                fields=["sector"], condition=Q(fecha_fin__isnull=True), name="fuera_de_servicio_un_registro_abierto_por_sector"
            ),
        ]

    @property
    def fecha_efectiva(self):
        """Desde cuándo está fuera de servicio: la `fecha_bitacora` (no se duplica la columna)."""
        return self.fecha_bitacora

    def __str__(self):
        """«Fuera de servicio #N» (texto de la auditoría, D-36)."""
        return f"Fuera de servicio #{self.pk}"


class Reubicacion(Bitacora):
    """Traslado de las plantas de UN lote desde un sector que sale de servicio hacia otros sectores del mismo tipo de etapa (MD-76,
    D-51). Hija de `Bitacora` con `tipo_evento = reubicacion`; sin atributos propios: el lote es `Bitacora.lote`, el sector de origen
    es el único de `Bitacora.sectores`. Se crea una por lote reubicado. Sus ocupaciones de destino son `OcupacionSector.reubicacion`.
    No cambia la etapa del lote ni su fecha de entrada a la etapa."""

    class Meta:
        verbose_name = "Reubicación"
        verbose_name_plural = "Reubicaciones"

    def __str__(self):
        """«Reubicación #N» (texto de la auditoría, D-36)."""
        return f"Reubicación #{self.pk}"


class Cosecha(OrdenTrabajo, ConCapataz):
    """Orden de cosecha (`tipo_orden = cosecha`; COM-02, D-59; docs/modelo/produccion.md). Vive en `produccion` pero sus casos de uso viven en
    `comercial` (regla A3): toda cosecha tiene una reserva (R087), que es de `comercial`. Los lotes y las cantidades están en las líneas de esa
    reserva. `variedad` se guarda porque una cosecha abarca una sola variedad (regla 2 de 8.8) y `produccion` la necesita sin preguntarle a
    `comercial`. Su clave es `ordentrabajo_ptr`; el Capataz viene de `ConCapataz` (D-53). La prioridad obligatoria es una restricción de `OrdenTrabajo`."""

    class OrigenCosecha(models.TextChoices):
        """D-64 punto 5: quién la creó. `automatica`: PROD-ASG-STK y la pre-reserva; `manual`: PROD-PNF-CSC; `encadenada`: 13a de PROD-CNC-CSC."""

        AUTOMATICA = "automatica", "Automática"
        MANUAL = "manual", "Manual"
        ENCADENADA = "encadenada", "Encadenada"

    fecha_cosecha = models.DateField(null=True, blank=True)  # la efectiva; la carga COM-04a al concretar
    variedad = models.ForeignKey(Variedad, on_delete=models.PROTECT, related_name="cosechas")
    # COM-04a (D-64 punto 5): `default="automatica"` porque hasta COM-04a solo había automáticas.
    origen_cosecha = models.CharField(max_length=20, choices=OrigenCosecha.choices, default=OrigenCosecha.AUTOMATICA)

    class Meta:
        verbose_name = "Cosecha"
        verbose_name_plural = "Cosechas"
        constraints = [
            models.CheckConstraint(condition=Q(origen_cosecha__in=["automatica", "manual", "encadenada"]), name="cosecha_origen_valido"),
        ]


class StockCosechado(models.Model):
    """Partida de producto ya cosechado, en cámara (COM-02, D-59). Nadie la crea en COM-02: las partidas nacen al concretar una cosecha
    (COM-04). Se muestra como `P-{id}`. No hereda de `OrigenDocumento`: no origina asientos."""

    class Motivo(models.TextChoices):
        CANCELACION_CLIENTE = "cancelacion_cliente", "Cancelación del cliente"
        RECHAZO_CANTIDAD_REDUCIDA = "rechazo_cantidad_reducida", "Rechazo por cantidad reducida"
        RECHAZO_EN_ENTREGA = "rechazo_en_entrega", "Rechazo en la entrega"
        COSECHA_DEL_AGRONOMO = "cosecha_del_agronomo", "Cosecha planificada por el Agrónomo"
        EXCEDENTE_DE_COSECHA = "excedente_de_cosecha", "Excedente de cosecha"
        RESOLUCION_DEL_CONTRATO = "resolucion_del_contrato", "Resolución del contrato"

    class Estado(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        AGOTADO = "agotado", "Agotado"
        VENCIDO = "vencido", "Vencido"

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="partidas")  # R144: invernadero y variedad, los del lote
    cantidad_ingreso_cosechado = models.PositiveIntegerField()  # no se modifica
    # Nunca mayor que el ingreso, salvo una devolución (regla 29 de 8.6, COM-06): por eso la restricción es solo `>= 0`.
    cantidad_disponible_cosechado = models.PositiveIntegerField()
    fecha_ingreso = models.DateField()
    fecha_limite = models.DateField()  # fecha de la cosecha + postcosecha de la variedad (regla 29 de 8.6)
    motivo_cosechado = models.CharField(max_length=30, choices=Motivo.choices)
    estado_stock_cosechado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.DISPONIBLE)
    costo_unitario_cosechado = models.DecimalField(max_digits=14, decimal_places=4)  # por planta, con 4 decimales

    class Meta:
        verbose_name = "Partida de cámara"
        verbose_name_plural = "Partidas de cámara"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_ingreso_cosechado__gte=1), name="partida_ingreso_positivo"),
            models.CheckConstraint(condition=Q(cantidad_disponible_cosechado__gte=0), name="partida_disponible_no_negativo"),
            models.CheckConstraint(condition=Q(costo_unitario_cosechado__gte=0), name="partida_costo_no_negativo"),
            models.CheckConstraint(
                condition=Q(estado_stock_cosechado__in=["disponible", "agotado", "vencido"]), name="partida_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(
                    motivo_cosechado__in=[
                        "cancelacion_cliente",
                        "rechazo_cantidad_reducida",
                        "rechazo_en_entrega",
                        "cosecha_del_agronomo",
                        "excedente_de_cosecha",
                        "resolucion_del_contrato",
                    ]
                ),
                name="partida_motivo_valido",
            ),
            # Regla 30 de 8.6: agotado ⇒ nada disponible.
            models.CheckConstraint(
                condition=~Q(estado_stock_cosechado="agotado") | Q(cantidad_disponible_cosechado=0), name="partida_agotada_sin_disponible"
            ),
        ]

    def __str__(self):
        """«P-7» (texto de la auditoría, D-36)."""
        return self.codigo

    @property
    def codigo(self):
        """`P-7`: lo que muestran las pantallas y los avisos."""
        return f"P-{self.pk}"


class MovimientoStock(OrigenDocumento):
    """Movimiento de producto de un lote o de una partida (COM-04a, D-64 punto 1; docs/modelo/produccion.md). Hija directa de `OrigenDocumento`
    (`TIPO_DE_ORIGEN = movimiento_de_stock`), con el mismo esquema que `MovimientoInsumo` (D-52). Su tipo se llama `tipo_movimiento` porque
    `tipo` es del padre. Solo lo crean las funciones de núcleo de `produccion` (`cosechas`, `camara`, `mermas`). Sin carga retroactiva."""

    TIPO_DE_ORIGEN = OrigenDocumento.Tipo.MOVIMIENTO_DE_STOCK

    class TipoMovimiento(models.TextChoices):
        INGRESO_A_CAMARA = "ingreso_a_camara", "Ingreso a cámara"
        EGRESO_DE_CAMARA = "egreso_de_camara", "Egreso de cámara"
        MERMA_EN_CAMARA = "merma_en_camara", "Merma en cámara"
        SALIDA_POR_COSECHA = "salida_por_cosecha", "Salida por cosecha"
        SALIDA_POR_MERMA = "salida_por_merma", "Salida por merma"

    # La fecha de la operación con la hora actual; en la salida por cosecha, la fecha efectiva.
    fecha = models.DateTimeField(default=timezone.now)
    cantidad = models.PositiveIntegerField()  # siempre positiva: el sentido lo da el tipo
    tipo_movimiento = models.CharField(max_length=30, choices=TipoMovimiento.choices)
    # Costo por planta del lote ANTES del movimiento, o el de la partida (D-64 puntos 1 y 3).
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=4)
    # R017: el documento que lo origina (la cosecha, la merma, la orden de entrega...). Lo verifica la función que lo crea.
    origen = models.ForeignKey(OrigenDocumento, on_delete=models.PROTECT, related_name="movimientos_de_stock")
    lote = models.ForeignKey(Lote, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos_de_stock")  # R086
    partida = models.ForeignKey(StockCosechado, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos")  # R145

    class Meta:
        verbose_name = "Movimiento de stock"
        verbose_name_plural = "Movimientos de stock"
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="movimiento_stock_cantidad_positiva"),
            models.CheckConstraint(condition=Q(costo_unitario__gte=0), name="movimiento_stock_costo_no_negativo"),
            models.CheckConstraint(
                condition=Q(
                    tipo_movimiento__in=["ingreso_a_camara", "egreso_de_camara", "merma_en_camara", "salida_por_cosecha", "salida_por_merma"]
                ),
                name="movimiento_stock_tipo_valido",
            ),
            # C2: exactamente uno de `lote` y `partida`.
            models.CheckConstraint(
                condition=(Q(lote__isnull=False) & Q(partida__isnull=True)) | (Q(lote__isnull=True) & Q(partida__isnull=False)),
                name="movimiento_stock_lote_o_partida",
            ),
            # Las salidas son del lote; los movimientos de cámara, de la partida.
            models.CheckConstraint(
                condition=~Q(tipo_movimiento__in=["salida_por_cosecha", "salida_por_merma"]) | Q(lote__isnull=False),
                name="movimiento_stock_salida_de_lote",
            ),
            models.CheckConstraint(
                condition=~Q(tipo_movimiento__in=["ingreso_a_camara", "egreso_de_camara", "merma_en_camara"]) | Q(partida__isnull=False),
                name="movimiento_stock_camara_de_partida",
            ),
        ]

    def __str__(self):
        """«Movimiento de stock #N» (texto de la auditoría, D-36)."""
        return f"Movimiento de stock #{self.pk}"
