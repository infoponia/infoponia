# Modelos de la app `iot` (nivel 7 de D-37). IOT-01 crea TODO el esquema del módulo (D-72, punto 6), salvo `RegistroComando`
# (IOT-05, necesita `produccion.Bitacora`) y `MantenimientoTecnico` (IOT-07): las demás tareas agregan comportamiento sin
# cambiar modelos. Fuente: docs/modelo/iot.md. Convenciones: nombres de D-05; bajas lógicas; claves foráneas `PROTECT` (la única
# excepción es `EquipoAnunciado.sistema`, que es `CASCADE`: dato de diseño que cada anuncio del nodo reemplaza, MD-102);
# comparación de nombres e identificadores sin distinguir mayúsculas (`Lower` en los índices únicos).

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import Agronomo, Usuario, rol_de
from iot import alcance

# ---- QuerySets con el alcance por usuario (D-28; docs/modelo/iot.md, «Convenciones de esta ficha») ----


class PorInvernaderoQuerySet(models.QuerySet):
    """QuerySet de un modelo que pertenece a un invernadero por la ruta ``RUTA_INVERNADERO`` (por ejemplo,
    ``sistema__invernadero``). ``para`` filtra lo que ``usuario`` consulta y ``operables_por`` lo que opera (MD-98); el cálculo
    del alcance está en ``iot/alcance.py``."""

    RUTA_INVERNADERO = "invernadero"

    def para(self, usuario):
        """Filas de los invernaderos que ``usuario`` consulta (el Agrónomo, los suyos; el Gerente, todos; otro rol, ninguno)."""
        return self.filter(**{f"{self.RUTA_INVERNADERO}__in": alcance.invernaderos_que_consulta(usuario)})

    def operables_por(self, usuario):
        """Filas de los invernaderos cuyo IoT ``usuario`` opera (el Agrónomo, los suyos; el Gerente, solo los sin Agrónomo activo)."""
        return self.filter(**{f"{self.RUTA_INVERNADERO}__in": alcance.invernaderos_que_opera(usuario)})


def _queryset_por(ruta):
    """Un ``QuerySet`` por invernadero con su ruta (patrón Factory Method: una sola implementación de ``para`` y
    ``operables_por`` en lugar de repetirla en nueve ``QuerySet``)."""
    return type("PorInvernaderoQuerySet", (PorInvernaderoQuerySet,), {"RUTA_INVERNADERO": ruta})


class TipoActuadorQuerySet(models.QuerySet):
    """Los tipos de actuador son de toda la organización y no tienen alcance por invernadero (regla 1 de IOT-ALT-TAC)."""

    def para(self, usuario):
        """Los tipos que ``usuario`` consulta: todos, para el Gerente y el Agrónomo activos (regla 1 de IOT-CNS-TAC); otro rol, ninguno."""
        if getattr(usuario, "is_active", False) and rol_de(usuario) in (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO):
            return self.all()
        return self.none()

    def operables_por(self, usuario):
        """Los tipos que ``usuario`` administra: todos, solo para el Gerente activo (regla 1 de IOT-ALT-TAC)."""
        if getattr(usuario, "is_active", False) and rol_de(usuario) == Usuario.Rol.GERENTE:
            return self.all()
        return self.none()


# ---- Catálogo de capacidades (MD-103): cargado por la migración 0002, sin alta, baja ni modificación ----


class Capacidad(models.Model):
    """Capacidad del catálogo (IOT-ALT-TAC, regla 7): ``encendido``, ``nivel`` o ``posicion``. Forma parte del contrato con el
    nodo central y cambia solo con una versión nueva de la API; se carga por migración, como ``TipoEtapa``."""

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=30)

    class Meta:
        ordering = ["id"]
        verbose_name = "Capacidad"
        verbose_name_plural = "Capacidades"

    def __str__(self):
        return self.nombre


class ComandoCatalogo(models.Model):
    """Comando del catálogo (IOT-ALT-TAC, reglas 7 y 8): lo que viaja al nodo. ``lleva_valor`` es verdadero solo en
    ``FIJAR_NIVEL`` y ``FIJAR_POSICION``; «requiere valor» de una acción es este campo, no se guarda en ella (MD-103)."""

    codigo = models.CharField(max_length=20, unique=True)
    capacidad = models.ForeignKey(Capacidad, on_delete=models.PROTECT, related_name="comandos")
    lleva_valor = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "Comando del catálogo"
        verbose_name_plural = "Comandos del catálogo"

    def __str__(self):
        return self.codigo


# ---- Tipos de actuador y sus acciones (MD-104, MD-103) ----


class TipoActuador(models.Model):
    """Tipo de actuador (IOT-ALT-TAC, IOT-MOD-TAC, IOT-BAJ-TAC, IOT-CNS-TAC): una clase de equipo con las acciones que admite.
    Común a toda la organización: lo administra solo el Gerente (MD-98). El nombre es único entre TODOS los tipos, activos o
    inactivos, sin distinguir mayúsculas (regla 2 de IOT-ALT-TAC)."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    nombre_actuador = models.CharField("nombre", max_length=60)
    # Regla 9 de IOT-ALT-TAC: segundos entre dos comandos ejecutados sobre un mismo actuador (valor inicial 60, a confirmar).
    tiempo_minimo_entre_comandos = models.PositiveIntegerField("tiempo mínimo entre comandos (s)", default=60)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    objects = TipoActuadorQuerySet.as_manager()

    class Meta:
        ordering = ["estado", "nombre_actuador"]
        verbose_name = "Tipo de actuador"
        verbose_name_plural = "Tipos de actuador"
        constraints = [
            # Regla 2 de IOT-ALT-TAC: nombre único entre todos, sin distinguir mayúsculas.
            models.UniqueConstraint(Lower("nombre_actuador"), name="tipo_actuador_nombre_unico"),
            models.CheckConstraint(
                condition=Q(estado__in=["activo", "inactivo"]), name="tipo_actuador_estado_valido"
            ),
        ]

    def __str__(self):
        """El nombre: es el texto que guarda la auditoría al referenciarlo (D-36)."""
        return self.nombre_actuador

    @property
    def codigo(self):
        """Código que se muestra, ``TAC-NN`` (el id con dos dígitos; en el prototipo era fijo, en el sistema sale del id)."""
        return f"TAC-{self.pk:02d}"


class Accion(models.Model):
    """Acción de un tipo de actuador (IOT-ALT-TAC, reglas 3, 4 y 8; R059): un nombre asociado a un comando del catálogo. Si el
    comando lleva valor, tiene unidad, mínimo y máximo enteros (regla 4). Una acción quitada con comandos en su historial queda
    ``inactiva``; una sin historial se BORRA (IOT-MOD-TAC, postcondición a): es la única baja física de una fila de negocio, junto
    con la retención de la telemetría."""

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        INACTIVA = "inactiva", "Inactiva"

    tipo_actuador = models.ForeignKey(TipoActuador, on_delete=models.PROTECT, related_name="acciones")
    nombre_accion = models.CharField("nombre", max_length=40)
    comando = models.ForeignKey(ComandoCatalogo, on_delete=models.PROTECT, related_name="acciones")
    # Los tres nulos o los tres no nulos; que coincidan con ``comando.lleva_valor`` lo controla el servicio (otra tabla).
    unidad_valor = models.CharField("unidad", max_length=5, null=True, blank=True)
    valor_minimo = models.IntegerField("valor mínimo", null=True, blank=True)
    valor_maximo = models.IntegerField("valor máximo", null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVA)

    class Meta:
        ordering = ["id"]
        verbose_name = "Acción"
        verbose_name_plural = "Acciones"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(unidad_valor__isnull=True, valor_minimo__isnull=True, valor_maximo__isnull=True)
                    | Q(
                        unidad_valor__isnull=False,
                        valor_minimo__isnull=False,
                        valor_maximo__isnull=False,
                        valor_minimo__lt=F("valor_maximo"),
                    )
                ),
                name="accion_unidad_y_rango_coherentes",
            ),
            # Reglas 3 de IOT-ALT-TAC: nombre y comando únicos dentro del tipo, entre las acciones ACTIVAS.
            models.UniqueConstraint(
                Lower("nombre_accion"),
                "tipo_actuador",
                condition=Q(estado="activa"),
                name="accion_nombre_unico_por_tipo_activa",
            ),
            models.UniqueConstraint(
                fields=["tipo_actuador", "comando"],
                condition=Q(estado="activa"),
                name="accion_comando_unico_por_tipo_activa",
            ),
            models.CheckConstraint(condition=Q(estado__in=["activa", "inactiva"]), name="accion_estado_valido"),
            # D-80: el rango según la unidad. «%» de 0 a 100; «rpm», «L/min» y «cm» con mínimo 0 o más; «°» sin límite fijo. Una unidad que no
            # es de la lista cerrada (regla 10) tampoco pasa.
            models.CheckConstraint(
                condition=(
                    Q(unidad_valor__isnull=True)
                    | Q(unidad_valor="°")
                    | Q(unidad_valor="%", valor_minimo__gte=0, valor_maximo__lte=100)
                    | Q(unidad_valor__in=["rpm", "L/min", "cm"], valor_minimo__gte=0)
                ),
                name="accion_rango_segun_unidad",
            ),
        ]

    def __str__(self):
        return self.nombre_accion

    @property
    def requiere_valor(self):
        """Verdadero si el comando de la acción lleva valor (MD-103: no se guarda, sale del comando)."""
        return self.comando.lleva_valor


# ---- Sistema IoT y hardware (MD-99 a MD-102; D-72) ----


class SistemaIoT(models.Model):
    """Sistema IoT de un invernadero (IOT-REG-SIS; R068, composición). Estados: ``activo``, ``desconectado`` (se revierte) e
    ``inactivo`` (la baja, definitiva y en cascada). A lo sumo uno no inactivo por invernadero (índice único parcial). El token
    del nodo nunca se guarda: solo su resumen SHA-256 (D-70, punto 3)."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        DESCONECTADO = "desconectado", "Desconectado"
        INACTIVO = "inactivo", "Inactivo"

    invernadero = models.ForeignKey("maestros.Invernadero", on_delete=models.PROTECT, related_name="sistemas_iot")
    estado_sistema = models.CharField(max_length=15, choices=Estado.choices, default=Estado.ACTIVO)
    # IOT-MOD-SIS, regla 7: rango de temperatura de la solución, los dos o ninguno, con el mínimo menor que el máximo.
    temp_solucion_min = models.DecimalField("temperatura mínima de la solución (°C)", max_digits=4, decimal_places=1, null=True, blank=True)
    temp_solucion_max = models.DecimalField("temperatura máxima de la solución (°C)", max_digits=4, decimal_places=1, null=True, blank=True)
    # D-70: SHA-256 en hexadecimal (64); nulo después de la baja. Único.
    token_resumen = models.CharField(max_length=64, null=True, blank=True, unique=True)
    token_generado_en = models.DateTimeField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)

    objects = _queryset_por("invernadero").as_manager()

    class Meta:
        ordering = ["invernadero__nombre_invernadero", "id"]
        verbose_name = "Sistema IoT"
        verbose_name_plural = "Sistemas IoT"
        constraints = [
            # R068: un sistema no inactivo por invernadero (MD-99).
            models.UniqueConstraint(
                fields=["invernadero"], condition=~Q(estado_sistema="inactivo"), name="sistema_iot_uno_por_invernadero"
            ),
            models.CheckConstraint(
                condition=Q(estado_sistema__in=["activo", "desconectado", "inactivo"]), name="sistema_iot_estado_valido"
            ),
            models.CheckConstraint(
                condition=(
                    Q(temp_solucion_min__isnull=True, temp_solucion_max__isnull=True)
                    | Q(
                        temp_solucion_min__isnull=False,
                        temp_solucion_max__isnull=False,
                        temp_solucion_min__lt=F("temp_solucion_max"),
                    )
                ),
                name="sistema_iot_rango_solucion_coherente",
            ),
        ]

    def __str__(self):
        return f"Sistema IoT de {self.invernadero}"


class HardwareQuerySet(_queryset_por("sistema__invernadero")):
    """``QuerySet`` de los equipos con el alcance por invernadero (el del sistema, regla 20 de 8.20)."""


class Hardware(models.Model):
    """Equipo del sistema IoT (abstracta en el modelo; tabla base en el código, D-72): herencia de varias tablas, como
    ``OrdenTrabajo`` (D-50), con ``clase`` como discriminador. Una sola FK ``sistema`` reemplaza a R064, R065 y R066: el nodo de
    un sensor o actuador es el nodo de su sistema. Así los índices únicos de abajo garantizan en la base la unicidad del
    identificador (MD-100) y un solo nodo por sistema."""

    class Clase(models.TextChoices):
        NODO = "nodo", "Nodo central"
        SENSOR = "sensor", "Sensor"
        ACTUADOR = "actuador", "Actuador"

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        FUERA_DE_SERVICIO = "fuera_de_servicio", "Fuera de servicio"
        INACTIVO = "inactivo", "Inactivo"

    sistema = models.ForeignKey(SistemaIoT, on_delete=models.PROTECT, related_name="equipos")
    clase = models.CharField(max_length=10, choices=Clase.choices, editable=False)
    modelo_hardware = models.CharField("modelo", max_length=60)
    numero_serie = models.CharField("número de serie", max_length=60, blank=True, default="")
    fecha_instalacion = models.DateField("fecha de instalación")
    estado_hardware = models.CharField("estado", max_length=20, choices=Estado.choices, default=Estado.ACTIVO)
    # MD-100: obligatorio en sensor y actuador, nulo en el nodo.
    identificador_equipo = models.CharField(
        "identificador",
        max_length=64,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^[A-Za-z0-9._/-]{1,64}$", "Usá solo letras, números, - _ . y /.")],
    )
    # Último mensaje del nodo SOBRE este equipo (lectura, estado o resultado). Nulo = «sin confirmar».
    ultimo_mensaje_en = models.DateTimeField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)
    # R070 (regla 21 de 8.20): opcional; si lo tiene, del mismo invernadero (lo controla el servicio). Nulo en el nodo.
    sector = models.ForeignKey(
        "maestros.SectorProduccion", null=True, blank=True, on_delete=models.PROTECT, related_name="equipos_iot"
    )
    # R072: de la categoría ``repuestos_de_hardware`` (lo controla el servicio).
    insumo = models.ForeignKey("inventario.Insumo", on_delete=models.PROTECT, related_name="equipos_iot")

    objects = HardwareQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        constraints = [
            # MD-100: nodo ⇔ identificador nulo.
            models.CheckConstraint(
                condition=(
                    Q(clase="nodo", identificador_equipo__isnull=True)
                    | (~Q(clase="nodo") & Q(identificador_equipo__isnull=False))
                ),
                name="hardware_nodo_sin_identificador",
            ),
            # Regla 21 de 8.20: un nodo no tiene sector.
            models.CheckConstraint(
                condition=~Q(clase="nodo") | Q(sector__isnull=True), name="hardware_nodo_sin_sector"
            ),
            # MD-100: un identificador no se repite entre los equipos no dados de baja del mismo sistema (un reemplazo
            # puede reusar el de uno dado de baja).
            models.UniqueConstraint(
                Lower("identificador_equipo"),
                "sistema",
                condition=Q(identificador_equipo__isnull=False) & ~Q(estado_hardware="inactivo"),
                name="hardware_identificador_unico_por_sistema",
            ),
            # R066 (1–1): un nodo por sistema. Incluye los dados de baja: el nodo no se reemplaza (D-72, punto 2).
            models.UniqueConstraint(
                fields=["sistema"], condition=Q(clase="nodo"), name="hardware_un_nodo_por_sistema"
            ),
            models.CheckConstraint(condition=Q(clase__in=["nodo", "sensor", "actuador"]), name="hardware_clase_valida"),
            models.CheckConstraint(
                condition=Q(estado_hardware__in=["activo", "fuera_de_servicio", "inactivo"]), name="hardware_estado_valido"
            ),
        ]

    def __str__(self):
        return f"{self.get_clase_display()} {self.identificador_equipo or self.modelo_hardware}"


class NodoCentral(Hardware):
    """Nodo central del sistema (R066): el que habla con InfoPonia por la API (D-70). No tiene identificador ni sector. La
    conectividad NO se guarda: «en línea» si ``ultima_comunicacion`` es más reciente que ``minutos_sin_comunicacion``."""

    class Modo(models.TextChoices):
        REMOTO = "remoto", "Remoto"
        LOCAL = "local", "Local"

    nombre_nodo = models.CharField("nombre", max_length=60)
    modo = models.CharField(max_length=10, choices=Modo.choices, default=Modo.REMOTO)
    ultima_comunicacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Nodo central"
        verbose_name_plural = "Nodos centrales"
        constraints = [models.CheckConstraint(condition=Q(modo__in=["remoto", "local"]), name="nodo_modo_valido")]

    def __str__(self):
        return self.nombre_nodo


class Sensor(Hardware):
    """Sensor (MD-101). La unidad de medida no se guarda: la fija la variable (``unidad_medida``). Solo ``temperatura``,
    ``humedad`` e ``intensidad_luz`` admiten reglas de actuación."""

    class Variable(models.TextChoices):
        TEMPERATURA = "temperatura", "Temperatura"
        HUMEDAD = "humedad", "Humedad"
        INTENSIDAD_LUZ = "intensidad_luz", "Intensidad lumínica"
        TEMPERATURA_SOLUCION = "temperatura_solucion", "Temperatura de la solución"
        NIVEL_SOLUCION = "nivel_solucion", "Nivel de la solución"

    # Unidad de cada variable (docs/modelo/iot.md, «Sensor»): el nivel no tiene.
    UNIDADES = {
        "temperatura": "°C",
        "humedad": "% HR",
        "intensidad_luz": "lux",
        "temperatura_solucion": "°C",
        "nivel_solucion": "",
    }

    tipo_variable_sensor = models.CharField("variable", max_length=25, choices=Variable.choices)
    # Obligatorios salvo en el nivel de la solución, donde son nulos; mínimo < máximo.
    valor_calibracion_min = models.DecimalField("calibración mínima", max_digits=9, decimal_places=2, null=True, blank=True)
    valor_calibracion_max = models.DecimalField("calibración máxima", max_digits=9, decimal_places=2, null=True, blank=True)
    # Opcional (los casos de uso lo nombran pero no lo exigen; el prototipo no lo tiene: D-61).
    nombre_sensor = models.CharField("nombre", max_length=60, blank=True, default="")

    class Meta:
        verbose_name = "Sensor"
        verbose_name_plural = "Sensores"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    tipo_variable_sensor__in=[
                        "temperatura",
                        "humedad",
                        "intensidad_luz",
                        "temperatura_solucion",
                        "nivel_solucion",
                    ]
                ),
                name="sensor_variable_valida",
            ),
            # La calibración: nula en el nivel y completa, con mínimo < máximo, en las demás variables.
            models.CheckConstraint(
                condition=(
                    Q(tipo_variable_sensor="nivel_solucion", valor_calibracion_min__isnull=True, valor_calibracion_max__isnull=True)
                    | (
                        ~Q(tipo_variable_sensor="nivel_solucion")
                        & Q(
                            valor_calibracion_min__isnull=False,
                            valor_calibracion_max__isnull=False,
                            valor_calibracion_min__lt=F("valor_calibracion_max"),
                        )
                    )
                ),
                name="sensor_calibracion_coherente",
            ),
        ]

    def __str__(self):
        return self.nombre_sensor or f"{self.get_tipo_variable_sensor_display()} {self.identificador_equipo}"

    @property
    def unidad_medida(self):
        """La unidad que fija la variable del sensor (MD-101); vacía en el nivel de la solución."""
        return self.UNIDADES[self.tipo_variable_sensor]


class Actuador(Hardware):
    """Actuador (MD-102): un equipo de un tipo, que recibe comandos. ``compatibilidad`` y ``acciones_incompatibles`` las calcula
    ``recalcular_compatibilidad`` (IOT-02) comparando las acciones de su tipo con el último anuncio del nodo."""

    class Compatibilidad(models.TextChoices):
        COMPATIBLE = "compatible", "Compatible"
        INCOMPATIBLE = "incompatible", "Incompatible"
        SIN_VERIFICAR = "sin_verificar", "Sin verificar"

    descripcion_actuador = models.CharField("descripción", max_length=300, blank=True, default="")
    # Estado que informó el nodo (``encendido``, ``apagado``, ``abierto``, ``cerrado``, ``nivel:<n>``, ``posicion:<n>``). Nulo = «desconocido».
    estado_informado = models.CharField(max_length=30, null=True, blank=True)
    estado_informado_en = models.DateTimeField(null=True, blank=True)
    # Verdadero si el último estado informado no lo explica un comando de InfoPonia ejecutado sobre él.
    cambiado_en_invernadero = models.BooleanField(default=False)
    compatibilidad = models.CharField(max_length=15, choices=Compatibilidad.choices, default=Compatibilidad.SIN_VERIFICAR)
    # R060: cambia solo si el actuador no tiene comandos ni reglas (IOT-MOD-HDW, regla 3).
    tipo_actuador = models.ForeignKey(TipoActuador, on_delete=models.PROTECT, related_name="actuadores")
    # MD-102: las acciones de su tipo que el nodo no soporta.
    acciones_incompatibles = models.ManyToManyField(Accion, blank=True, related_name="actuadores_incompatibles")

    class Meta:
        verbose_name = "Actuador"
        verbose_name_plural = "Actuadores"
        constraints = [
            models.CheckConstraint(
                condition=Q(compatibilidad__in=["compatible", "incompatible", "sin_verificar"]),
                name="actuador_compatibilidad_valida",
            ),
        ]

    def __str__(self):
        return f"{self.tipo_actuador} {self.identificador_equipo}"


class EquipoAnunciado(models.Model):
    """Lo que el nodo anunció (IOT-ENT-INF, extensión 1c; dato de diseño, MD-102). Cada anuncio REEMPLAZA los equipos anunciados
    del sistema. La FK es ``CASCADE``: es la excepción a «todas las FK son PROTECT» (docs/modelo/iot.md, «Convenciones»)."""

    class Clase(models.TextChoices):
        SENSOR = "sensor", "Sensor"
        ACTUADOR = "actuador", "Actuador"

    sistema = models.ForeignKey(SistemaIoT, on_delete=models.CASCADE, related_name="equipos_anunciados")
    identificador_equipo = models.CharField("identificador", max_length=64)
    clase = models.CharField(max_length=10, choices=Clase.choices)
    # Vacío en un sensor. La tabla intermedia queda con el CASCADE que Django pone por defecto.
    comandos = models.ManyToManyField(ComandoCatalogo, blank=True, related_name="equipos_anunciados")
    anunciado_en = models.DateTimeField(default=timezone.now)

    objects = _queryset_por("sistema__invernadero").as_manager()

    class Meta:
        ordering = ["identificador_equipo"]
        verbose_name = "Equipo anunciado"
        verbose_name_plural = "Equipos anunciados"
        constraints = [
            models.UniqueConstraint(
                Lower("identificador_equipo"), "sistema", name="equipo_anunciado_identificador_unico_por_sistema"
            ),
            models.CheckConstraint(condition=Q(clase__in=["sensor", "actuador"]), name="equipo_anunciado_clase_valida"),
        ]

    def __str__(self):
        return self.identificador_equipo


# ---- Lecturas (MD-107) ----


class Telemetria(models.Model):
    """Lectura de un sensor (MD-107). ``BigAutoField``: es la tabla que más crece. En el nivel de la solución no hay valor ni
    unidad ni marca de validez: solo ``estado_nivel_medido``. Única por ``(sensor, medida_en)``: un lote reenviado por el nodo no
    se duplica (D-74, punto 6). La retención (IOT-04) es la única baja física de esta tabla."""

    class EstadoNivel(models.TextChoices):
        NORMAL = "normal", "Normal"
        BAJO = "bajo", "Bajo"

    id = models.BigAutoField(primary_key=True)
    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="telemetrias")
    # La de medición que informó el nodo o, si no vino, la de recepción (extensión 3e de IOT-ENT-INF).
    medida_en = models.DateTimeField("medida en")
    valor_medido = models.DecimalField("valor medido", max_digits=9, decimal_places=2, null=True, blank=True)
    estado_nivel_medido = models.CharField(max_length=10, choices=EstadoNivel.choices, null=True, blank=True)
    unidad_medida_telemetria = models.CharField("unidad", max_length=10, null=True, blank=True)
    # Se guarda: no cambia si después cambia la calibración. Nula en el nivel.
    valida = models.BooleanField(null=True, blank=True)

    objects = _queryset_por("sensor__sistema__invernadero").as_manager()

    class Meta:
        ordering = ["-medida_en", "-id"]
        verbose_name = "Lectura"
        verbose_name_plural = "Lecturas"
        constraints = [
            models.UniqueConstraint(fields=["sensor", "medida_en"], name="telemetria_una_por_sensor_e_instante"),
            # num_nonnulls(valor_medido, estado_nivel_medido) = 1.
            models.CheckConstraint(
                condition=(
                    Q(valor_medido__isnull=False, estado_nivel_medido__isnull=True)
                    | Q(valor_medido__isnull=True, estado_nivel_medido__isnull=False)
                ),
                name="telemetria_valor_o_nivel",
            ),
            # ``valida`` nula ⇔ ``estado_nivel_medido`` no nulo.
            models.CheckConstraint(
                condition=(
                    Q(valida__isnull=True, estado_nivel_medido__isnull=False)
                    | Q(valida__isnull=False, estado_nivel_medido__isnull=True)
                ),
                name="telemetria_valida_nula_si_nivel",
            ),
            models.CheckConstraint(
                condition=Q(estado_nivel_medido__isnull=True) | Q(estado_nivel_medido__in=["normal", "bajo"]),
                name="telemetria_estado_nivel_valido",
            ),
        ]

    def __str__(self):
        return f"{self.sensor} · {self.medida_en:%d/%m/%Y %H:%M}"


class ResumenHorario(models.Model):
    """Resumen por hora de las lecturas de un sensor (dato de diseño, MD-107; D-71, D-76 punto 4). No hay resúmenes del nivel. No
    se borra por la retención. Único por ``(sensor, hora)`` (``hora`` con los minutos en 0)."""

    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="resumenes_horarios")
    hora = models.DateTimeField()
    minimo = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    promedio = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    maximo = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    cantidad_lecturas = models.PositiveIntegerField(default=0)
    cantidad_invalidas = models.PositiveIntegerField(default=0)

    objects = _queryset_por("sensor__sistema__invernadero").as_manager()

    class Meta:
        ordering = ["sensor", "-hora"]
        verbose_name = "Resumen horario"
        verbose_name_plural = "Resúmenes horarios"
        constraints = [models.UniqueConstraint(fields=["sensor", "hora"], name="resumen_horario_unico_por_sensor_y_hora")]

    def __str__(self):
        return f"{self.sensor} · {self.hora:%d/%m/%Y %H}h"


class FotoperiodoDiario(models.Model):
    """Horas de luz de un día de un sensor de intensidad lumínica (dato de diseño, MD-107; D-76 punto 5). ``incompleto`` si al
    sensor le faltaron lecturas ese día. No se borra por la retención. Único por ``(sensor, fecha)``."""

    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="fotoperiodos")
    fecha = models.DateField()
    horas = models.DecimalField(max_digits=4, decimal_places=2)
    incompleto = models.BooleanField(default=False)

    objects = _queryset_por("sensor__sistema__invernadero").as_manager()

    class Meta:
        ordering = ["sensor", "-fecha"]
        verbose_name = "Fotoperíodo diario"
        verbose_name_plural = "Fotoperíodos diarios"
        constraints = [
            models.UniqueConstraint(fields=["sensor", "fecha"], name="fotoperiodo_unico_por_sensor_y_fecha"),
            models.CheckConstraint(condition=Q(horas__gte=0, horas__lte=24), name="fotoperiodo_horas_de_0_a_24"),
        ]

    def __str__(self):
        return f"{self.sensor} · {self.fecha:%d/%m/%Y}"


# ---- Reglas de actuación y comandos (MD-105, MD-106) ----


class ReglaActuacion(models.Model):
    """Regla de actuación (MD-106): cuando la lectura de un sensor cumple una ``condicion`` respecto del umbral efectivo, se
    emite la ``accion`` sobre el actuador. A lo sumo una regla ACTIVA por ``(sensor, condicion, actuador)``. Que el sensor y el
    actuador sean del mismo sistema lo controla el servicio (IOT-06)."""

    class Condicion(models.TextChoices):
        SUPERA_MAXIMO = "supera_maximo", "Supera el máximo del umbral efectivo"
        BAJA_DEL_MINIMO = "baja_del_minimo", "Baja del mínimo del umbral efectivo"
        VUELVE_AL_RANGO = "vuelve_al_rango", "Vuelve a quedar dentro del umbral efectivo"

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        INACTIVA = "inactiva", "Inactiva"

    class Evaluacion(models.TextChoices):
        CUMPLIDA = "cumplida", "Cumplida"
        NO_CUMPLIDA = "no_cumplida", "No cumplida"
        SIN_EVALUAR = "sin_evaluar", "Sin evaluar"

    # No cambian después de creada la regla (IOT-06, regla 3).
    sensor = models.ForeignKey(Sensor, on_delete=models.PROTECT, related_name="reglas")
    actuador = models.ForeignKey(Actuador, on_delete=models.PROTECT, related_name="reglas")
    # R069: una acción activa del tipo del actuador.
    accion = models.ForeignKey(Accion, on_delete=models.PROTECT, related_name="reglas")
    condicion = models.CharField(max_length=20, choices=Condicion.choices)
    # Obligatorio si el comando de la acción lleva valor, dentro del rango de la acción (lo controla el servicio).
    aplicar_valor = models.IntegerField(null=True, blank=True)
    estado_regla = models.CharField("estado", max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    ultima_evaluacion = models.CharField(max_length=15, choices=Evaluacion.choices, default=Evaluacion.SIN_EVALUAR)
    contador_confirmacion = models.PositiveIntegerField(default=0)
    # R062: las lecturas que completaron la confirmación (no se borran por la retención).
    telemetrias = models.ManyToManyField(Telemetria, blank=True, related_name="reglas_que_disparo")

    objects = _queryset_por("sensor__sistema__invernadero").as_manager()

    class Meta:
        ordering = ["id"]
        verbose_name = "Regla de actuación"
        verbose_name_plural = "Reglas de actuación"
        constraints = [
            models.UniqueConstraint(
                fields=["sensor", "condicion", "actuador"],
                condition=Q(estado_regla="activa"),
                name="regla_actuacion_activa_unica",
            ),
            models.CheckConstraint(condition=Q(contador_confirmacion__gte=0), name="regla_actuacion_contador_no_negativo"),
            models.CheckConstraint(
                condition=Q(condicion__in=["supera_maximo", "baja_del_minimo", "vuelve_al_rango"]),
                name="regla_actuacion_condicion_valida",
            ),
            models.CheckConstraint(condition=Q(estado_regla__in=["activa", "inactiva"]), name="regla_actuacion_estado_valido"),
            models.CheckConstraint(
                condition=Q(ultima_evaluacion__in=["cumplida", "no_cumplida", "sin_evaluar"]),
                name="regla_actuacion_evaluacion_valida",
            ),
        ]

    def __str__(self):
        return f"RGL-{self.pk}"


class Comando(models.Model):
    """Comando emitido a un actuador (MD-105; IOT-EMT-CMD, IOT-RSV-CMD). Un solo comando PENDIENTE por actuador, también frente a
    las reglas: lo garantiza la base. ``regla`` nula = comando manual. ``agronomo`` es nulo en los automáticos y en los del
    Gerente (la persona va en la auditoría, R050)."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EJECUTADO = "ejecutado", "Ejecutado"
        FALLIDO = "fallido", "Fallido"
        CANCELADO = "cancelado", "Cancelado"

    class Resultado(models.TextChoices):
        EJECUTADO = "ejecutado", "Ejecutado"
        FALLO = "fallo", "Falló"
        RECHAZADO = "rechazado", "Rechazado"
        SIN_RESPUESTA = "sin_respuesta", "Sin respuesta"

    actuador = models.ForeignKey(Actuador, on_delete=models.PROTECT, related_name="comandos")
    # R058.
    accion = models.ForeignKey(Accion, on_delete=models.PROTECT, related_name="comandos")
    regla = models.ForeignKey(ReglaActuacion, null=True, blank=True, on_delete=models.PROTECT, related_name="comandos")
    agronomo = models.ForeignKey(Agronomo, null=True, blank=True, on_delete=models.PROTECT, related_name="comandos_iot")
    emitido_en = models.DateTimeField(default=timezone.now)
    estado_comando = models.CharField("estado", max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    valor_comando = models.IntegerField(null=True, blank=True)
    descripcion_comando = models.CharField("descripción", max_length=300, blank=True, default="")
    # El último resultado que informó el nodo o el vencimiento.
    resultado_comando = models.CharField(max_length=15, choices=Resultado.choices, null=True, blank=True)
    detalle_resultado = models.CharField(max_length=300, blank=True, default="")
    cantidad_intentos = models.PositiveIntegerField(default=0)
    ultimo_intento_en = models.DateTimeField(null=True, blank=True)
    # Momento de la resolución (ejecutado, fallido o cancelado); nulo mientras está pendiente.
    resuelto_en = models.DateTimeField(null=True, blank=True)

    objects = _queryset_por("actuador__sistema__invernadero").as_manager()

    class Meta:
        ordering = ["-emitido_en", "-id"]
        verbose_name = "Comando"
        verbose_name_plural = "Comandos"
        indexes = [models.Index(fields=["actuador", "emitido_en"], name="comando_actuador_emitido")]
        constraints = [
            models.UniqueConstraint(
                fields=["actuador"], condition=Q(estado_comando="pendiente"), name="comando_un_pendiente_por_actuador"
            ),
            # ``resuelto_en`` nula ⇔ pendiente.
            models.CheckConstraint(
                condition=(
                    Q(estado_comando="pendiente", resuelto_en__isnull=True)
                    | (~Q(estado_comando="pendiente") & Q(resuelto_en__isnull=False))
                ),
                name="comando_resuelto_en_coherente",
            ),
            models.CheckConstraint(condition=Q(cantidad_intentos__gte=0), name="comando_intentos_no_negativos"),
            models.CheckConstraint(
                condition=Q(estado_comando__in=["pendiente", "ejecutado", "fallido", "cancelado"]),
                name="comando_estado_valido",
            ),
        ]

    def __str__(self):
        return f"CMD-{self.pk}"


# ---- Alertas del IoT (D-72, punto 4) ----


class AlertaIot(models.Model):
    """Vínculo de cada alerta del IoT con su sistema y su origen (R052 o R053), como ``AlertaComercial`` (D-63): ``maestros.Alerta``
    no conoce a ``iot`` (D-38, regla A2). Guarda además el estado del correo de las críticas (D-71) y, en «dispositivo no
    registrado», el último mensaje rechazado (D-76, punto 3). Las alertas son de clase ``ESTADO``: «una activa por equipo y tipo»
    la garantiza la unicidad que ya tiene ``maestros``."""

    alerta = models.OneToOneField("maestros.Alerta", on_delete=models.PROTECT, related_name="vinculo_iot")
    sistema = models.ForeignKey(SistemaIoT, on_delete=models.PROTECT, related_name="alertas")
    # R052 y R053: a lo sumo uno de los dos.
    hardware = models.ForeignKey(Hardware, null=True, blank=True, on_delete=models.PROTECT, related_name="alertas_iot")
    telemetria = models.ForeignKey(Telemetria, null=True, blank=True, on_delete=models.PROTECT, related_name="alertas_iot")
    correo_enviado_en = models.DateTimeField(null=True, blank=True)
    intentos_correo = models.PositiveIntegerField(default=0)
    ultimo_mensaje_en = models.DateTimeField(null=True, blank=True)

    objects = _queryset_por("sistema__invernadero").as_manager()

    class Meta:
        verbose_name = "Alerta del IoT"
        verbose_name_plural = "Alertas del IoT"
        constraints = [
            # Restricción C5, la parte que cabe en una tabla: num_nonnulls(hardware, telemetria) <= 1.
            models.CheckConstraint(
                condition=Q(hardware__isnull=True) | Q(telemetria__isnull=True), name="alerta_iot_a_lo_sumo_un_origen"
            ),
        ]

    def __str__(self):
        return f"{self.alerta} ({self.sistema})"
