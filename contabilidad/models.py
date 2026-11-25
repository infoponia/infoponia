# Modelos de la app `contabilidad` (nivel 2, D-37): `OrigenDocumento` (CON-01, D-52) y, desde CON-02 (D-84), el núcleo contable:
# `EjercicioContable`, `CuentaContable`, `AsientoContable` y `MovimientoContable` (`docs/modelo/contabilidad.md`).
from django.db import models
from django.db.models import Q


class OrigenDocumento(models.Model):
    """Documento de origen común: el padre de todo lo que genera movimientos (D-52, `docs/modelo/contabilidad.md`).

    Es una tabla concreta con un único campo propio, `tipo` (el discriminador). En el dominio es abstracta: nadie
    crea un `OrigenDocumento` solo; lo crean sus hijas directas (herencia multitabla de Django, D-52 punto 2).
    El `id` es el automático y se comparte entre todos los tipos de documento (no es consecutivo por tipo).
    """

    class Tipo(models.TextChoices):
        """Tipos de documento de esta ronda; las rondas futuras suman los suyos junto con su clase."""

        ORDEN_DE_TRABAJO = "orden_de_trabajo", "Orden de trabajo"
        BITACORA = "bitacora", "Bitácora"
        MOVIMIENTO_DE_INSUMO = "movimiento_de_insumo", "Movimiento de insumo"
        CONTRATO = "contrato", "Contrato"  # COM-02 (D-52, D-59): lo crea `comercial.Contrato`
        MOVIMIENTO_DE_STOCK = "movimiento_de_stock", "Movimiento de stock"  # COM-04a (D-64 punto 1): lo crea `produccion.MovimientoStock`
        RECEPCION = "recepcion", "Recepción"  # CMP-04 (D-90 punto 3): lo crea `compras.Recepcion`

    # Convención de las hijas directas (D-52 puntos 1 y 2). `MovimientoInsumo` (INV-01), `OrdenTrabajo` y `Bitacora`
    # (PRD-01) la usan sin repetir lógica:
    #   - la hija directa declara `TIPO_DE_ORIGEN = OrigenDocumento.Tipo.<X>` como atributo de clase y NO reescribe
    #     `save()`: el de este padre copia ese valor en `tipo` antes de guardar, así que `tipo` lo fija la hija y
    #     nunca cambia;
    #   - las hijas de las hijas (`Siembra`, `Consumo`, etc.) heredan el atributo y no lo vuelven a declarar;
    #   - una clase sin `TIPO_DE_ORIGEN` válido (el padre puro o una hija mal declarada) no puede guardarse;
    #   - la clave primaria de la hija directa es `origendocumento_ptr` (`.id` sigue funcionando);
    #   - un tipo nuevo se suma a `Tipo` junto con su clase.
    TIPO_DE_ORIGEN = None

    # Obligatorio y dentro de la lista (modelo de contabilidad, «Restricciones y reglas»).
    # max_length 30: sobra para los tipos futuros (el más largo previsto, «solicitud_de_revision», tiene 21).
    tipo = models.CharField(max_length=30, choices=Tipo.choices)

    class Meta:
        verbose_name = "documento de origen"
        verbose_name_plural = "documentos de origen"

    def __str__(self):
        return f"{self.get_tipo_display()} #{self.pk}"

    def save(self, *args, **kwargs):
        """Guarda el documento fijando `tipo` desde `TIPO_DE_ORIGEN`; lanza `TypeError` si la clase no lo tiene.

        Regla de `docs/modelo/contabilidad.md` («Restricciones y reglas») y D-52 punto 1: nadie crea un
        `OrigenDocumento` solo; la hija directa fija su `tipo`.
        """
        tipo = type(self).TIPO_DE_ORIGEN
        if tipo not in OrigenDocumento.Tipo.values:  # no `self.Tipo`: una hija (OrdenTrabajo) puede declarar su propio `Tipo`
            raise TypeError(
                f"{type(self).__name__} no puede guardarse: OrigenDocumento es abstracto en el dominio y solo "
                "se guardan sus hijas directas, que declaran TIPO_DE_ORIGEN con un valor de OrigenDocumento.Tipo."
            )
        self.tipo = tipo
        super().save(*args, **kwargs)


class AsientoInmutableError(Exception):
    """Se intentó modificar o borrar un asiento contable o uno de sus movimientos: solo se corrigen con un contraasiento
    (D-84 punto 1, regla 17 de 8.20). Igual que el registro de auditoría (D-22)."""


class InmutableQuerySet(models.QuerySet):
    """QuerySet que no permite modificar ni borrar en bloque (D-84 punto 1); crear (`create`, `bulk_create`) sí."""

    def update(self, **kwargs):
        raise AsientoInmutableError("Un asiento y sus movimientos no se modifican: se corrigen con un contraasiento (D-84).")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AsientoInmutableError("Un asiento y sus movimientos no se modifican: se corrigen con un contraasiento (D-84).")

    def delete(self):
        raise AsientoInmutableError("Un asiento y sus movimientos no se borran: se corrigen con un contraasiento (D-84).")


class EjercicioContable(models.Model):
    """Período contable de 12 meses donde se registran los asientos (MD-115, D-84; `docs/modelo/contabilidad.md`).

    Estados: `abierto` (recibe los asientos automáticos de hoy), `en_cierre` (terminó su fecha prevista y el Contador todavía
    puede cargar asientos con fecha en su rango) y `cerrado` (definitivo, sin reapertura). A lo sumo uno abierto y uno en cierre
    (H1): lo respaldan dos restricciones parciales de la base. La apertura la hace `servicios/ejercicios.py`.
    """

    class Estado(models.TextChoices):
        """Estados del ejercicio (MD-115)."""

        ABIERTO = "abierto", "Abierto"
        EN_CIERRE = "en_cierre", "En cierre"
        CERRADO = "cerrado", "Cerrado"

    fecha_inicio_ejercicio = models.DateField("inicio")
    # Fecha PREVISTA de fin, fijada al abrir y nunca modificada (H1).
    fecha_cierre_ejercicio = models.DateField("cierre previsto")
    estado_ejercicio = models.CharField("estado", max_length=10, choices=Estado.choices)
    # Técnico (D-84 punto 4): último número usado; lo toma y suma el servicio con el ejercicio bloqueado. PositiveIntegerField ya
    # crea en la base el CHECK (>= 0) que pide el modelo.
    ultimo_numero_asiento = models.PositiveIntegerField("último número de asiento", default=0)
    # R010 (MD-116): el Contador que lo cerró. Vacío mientras no está cerrado, y si lo cerró el Gerente (sin Contador activo) o el Sistema (C1).
    contador = models.ForeignKey(
        "core.Contador", null=True, blank=True, on_delete=models.PROTECT, related_name="ejercicios_cerrados"
    )

    class Meta:
        verbose_name = "ejercicio contable"
        verbose_name_plural = "ejercicios contables"
        ordering = ["fecha_inicio_ejercicio", "id"]
        constraints = [
            # Respaldo de los servicios (H1): dos parciales sobre el estado.
            models.UniqueConstraint(
                fields=["estado_ejercicio"], condition=Q(estado_ejercicio="abierto"), name="un_solo_ejercicio_abierto"
            ),
            models.UniqueConstraint(
                fields=["estado_ejercicio"], condition=Q(estado_ejercicio="en_cierre"), name="un_solo_ejercicio_en_cierre"
            ),
            models.CheckConstraint(
                condition=Q(fecha_cierre_ejercicio__gte=models.F("fecha_inicio_ejercicio")),
                name="ejercicio_cierre_no_anterior_al_inicio",
            ),
            models.CheckConstraint(
                condition=Q(contador__isnull=True) | Q(estado_ejercicio="cerrado"),
                name="ejercicio_contador_solo_si_cerrado",
            ),
        ]

    def __str__(self):
        """El rango, para que la auditoría y el libro lo muestren sin consultar nada más."""
        return f"Ejercicio {self.fecha_inicio_ejercicio:%d/%m/%Y} al {self.fecha_cierre_ejercicio:%d/%m/%Y}"


class CuentaContable(models.Model):
    """Cuenta del plan de cuentas (MD-118). No es un ABM: el plan se carga por migración de datos (D-84 punto 7)."""

    class Tipo(models.TextChoices):
        """Tipo de cuenta; define el signo de su saldo (H7)."""

        ACTIVO = "activo", "Activo"
        PASIVO = "pasivo", "Pasivo"
        PATRIMONIO_NETO = "patrimonio_neto", "Patrimonio neto"
        RESULTADO_POSITIVO = "resultado_positivo", "Resultado positivo"
        RESULTADO_NEGATIVO = "resultado_negativo", "Resultado negativo"

    # Jerárquico `rubro.subrubro.cuenta`, por ejemplo `1.1.01`. Único (una cuenta por código).
    codigo_cuenta = models.CharField("código", max_length=10, unique=True)
    nombre_cuenta = models.CharField("nombre", max_length=80, unique=True)
    tipo_cuenta = models.CharField("tipo", max_length=20, choices=Tipo.choices)

    class Meta:
        verbose_name = "cuenta contable"
        verbose_name_plural = "cuentas contables"
        ordering = ["codigo_cuenta"]

    def __str__(self):
        return f"{self.codigo_cuenta} {self.nombre_cuenta}"


class AsientoContable(models.Model):
    """Registro de un hecho económico con sus movimientos (`docs/modelo/contabilidad.md`). **Inmutable** (D-84 punto 1): `save()` sobre
    una fila existente y `delete()` lanzan `AsientoInmutableError`, y el queryset (`update`, `delete`) también.

    El tipo (regla 15 de 8.20) se deduce y no se guarda: `automatico` si tiene `origen`, `contraasiento` si tiene `anula` y `manual` si
    no tiene ninguno. Debe = Haber y los dos o más movimientos no tienen restricción de base (comparan varias filas): los cuida el
    servicio y los verifica `verificar_invariantes_contables`.
    """

    class Tipo:
        """Valores de la propiedad derivada `tipo` (no es un campo)."""

        AUTOMATICO = "automatico"
        CONTRAASIENTO = "contraasiento"
        MANUAL = "manual"

    # Correlativo por ejercicio, sin huecos (H8, MD-117). Indica orden de registro, no de fecha.
    numero_asiento = models.PositiveIntegerField("número")
    # La fecha del hecho (H10).
    fecha_asiento = models.DateField("fecha")
    # Obligatoria sin documento de origen (regla 16 de 8.20); en un automático la completa el Sistema si hace falta aclarar (H10).
    descripcion_asiento = models.CharField("descripción", max_length=300, blank=True)
    # Técnico: cuándo se registró (el «fecha de registro» de H10).
    registrado_el = models.DateTimeField(auto_now_add=True)
    # R012: un origen, un asiento (D-86 punto 5). `related_name` propio: las hijas de OrigenDocumento ya usan sus nombres (D-83).
    origen = models.OneToOneField(
        "contabilidad.OrigenDocumento",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asiento_contable",
    )
    # R013.
    ejercicio = models.ForeignKey(EjercicioContable, on_delete=models.PROTECT, related_name="asientos")
    # R161: en el contraasiento, apunta al asiento anulado. «Anulado» se deriva con `hasattr(asiento, "contraasiento")`.
    anula = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="contraasiento"
    )

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "asiento contable"
        verbose_name_plural = "asientos contables"
        ordering = ["ejercicio", "numero_asiento"]
        constraints = [
            models.UniqueConstraint(fields=["ejercicio", "numero_asiento"], name="asiento_numero_unico_por_ejercicio"),
            # Un asiento no puede tener `origen` y `anula` a la vez (modelo, «Tipo»).
            models.CheckConstraint(
                condition=~(Q(origen__isnull=False) & Q(anula__isnull=False)), name="asiento_no_es_automatico_y_contraasiento"
            ),
            # Regla 16 de 8.20: sin documento de origen, la descripción es obligatoria.
            models.CheckConstraint(
                condition=~Q(origen__isnull=True, descripcion_asiento=""), name="asiento_sin_origen_con_descripcion"
            ),
        ]

    def __str__(self):
        return f"Asiento N.º {self.numero_asiento} del {self.ejercicio}"

    @property
    def tipo(self):
        """`automatico`, `contraasiento` o `manual` (regla 15 de 8.20): se deduce, no se guarda."""
        if self.origen_id is not None:
            return self.Tipo.AUTOMATICO
        if self.anula_id is not None:
            return self.Tipo.CONTRAASIENTO
        return self.Tipo.MANUAL

    def save(self, *args, **kwargs):
        """Guarda un asiento nuevo; una fila que ya existe no se modifica (D-84 punto 1)."""
        if not self._state.adding:
            raise AsientoInmutableError("Un asiento no se modifica: se corrige con un contraasiento (D-84).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Un asiento no se borra (D-84 punto 1)."""
        raise AsientoInmutableError("Un asiento no se borra: se corrige con un contraasiento (D-84).")


class MovimientoContable(models.Model):
    """Una línea de un asiento: una cuenta, Debe o Haber, un importe. Inmutable como su asiento (D-84 punto 1)."""

    class Tipo(models.TextChoices):
        """Debe o Haber."""

        DEBE = "D", "Debe"
        HABER = "H", "Haber"

    tipo_movimiento = models.CharField("Debe o Haber", max_length=1, choices=Tipo.choices)
    # Pesos argentinos con dos decimales; mayor que cero (el importe cero no se registra, H11).
    importe_movimiento = models.DecimalField("importe", max_digits=14, decimal_places=2)
    # R014: composición.
    asiento = models.ForeignKey(AsientoContable, on_delete=models.PROTECT, related_name="movimientos")
    # R015.
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.PROTECT, related_name="movimientos")

    objects = InmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "movimiento contable"
        verbose_name_plural = "movimientos contables"
        ordering = ["asiento", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(importe_movimiento__gt=0), name="movimiento_importe_mayor_que_cero"),
        ]

    def __str__(self):
        return f"{self.get_tipo_movimiento_display()} {self.cuenta.codigo_cuenta} {self.importe_movimiento}"

    def save(self, *args, **kwargs):
        """Guarda un movimiento nuevo; una fila que ya existe no se modifica (D-84 punto 1)."""
        if not self._state.adding:
            raise AsientoInmutableError("Un movimiento no se modifica: se corrige con un contraasiento (D-84).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Un movimiento no se borra (D-84 punto 1)."""
        raise AsientoInmutableError("Un movimiento no se borra: se corrige con un contraasiento (D-84).")
