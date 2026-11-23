# Modelos de la app `contabilidad` (nivel 2, D-37). En la ronda «Producción 1» existe una sola clase:
# `OrigenDocumento` (D-52). El ejercicio, el plan de cuentas y los asientos quedan fuera (D-45).
from django.db import models


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
