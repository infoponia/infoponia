# Modelos de maestros (nivel 3 de D-37) para MAE-01: la geografía de Georef, la dirección (jerarquía multi-tabla,
# como Usuario y los roles, D-01) y el invernadero con su personal. Decisiones D-04, D-05, D-28, D-37 y D-39.
# MAE-02a: Alerta (D-38: vive en maestros con una FK al invernadero; los orígenes de las apps altas la apuntan desde su app).
# MAE-03: TipoEtapa (catálogo fijo), SectorProduccion, Cultivo y, con columnas mínimas, Variedad, Ciclo y EtapaProductiva
# (docs/modelo/maestros.md; INV-03 completa Variedad).

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import Agronomo, Capataz, Tecnico, Usuario, Vendedor, rol_de
from maestros.validadores import validar_con_contenido, validar_kilometro, validar_numero_calle


class Provincia(models.Model):
    """Provincia precargada de Georef (MD-88, R108): no tiene ABM. ``id_georef`` conserva el código oficial."""

    id_georef = models.CharField("código de Georef", max_length=12, unique=True)
    nombre_provincia = models.CharField("provincia", max_length=60)

    class Meta:
        ordering = ["nombre_provincia"]
        verbose_name = "Provincia"
        verbose_name_plural = "Provincias"

    def __str__(self):
        return self.nombre_provincia


class Departamento(models.Model):
    """Departamento (o partido, o comuna) precargado de Georef (MD-88, R108 y R109)."""

    id_georef = models.CharField("código de Georef", max_length=12, unique=True)
    nombre_departamento = models.CharField("departamento", max_length=60)
    provincia = models.ForeignKey(Provincia, on_delete=models.PROTECT, related_name="departamentos")

    class Meta:
        ordering = ["nombre_departamento"]
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return f"{self.nombre_departamento} ({self.provincia})"


class Localidad(models.Model):
    """Localidad precargada de Georef (MD-88, R109 y R110). El texto es el que guarda la auditoría (D-36)."""

    id_georef = models.CharField("código de Georef", max_length=12, unique=True)
    nombre_localidad = models.CharField("localidad", max_length=80)
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, related_name="localidades")

    class Meta:
        ordering = ["nombre_localidad"]
        verbose_name = "Localidad"
        verbose_name_plural = "Localidades"

    def __str__(self):
        return f"{self.nombre_localidad} ({self.departamento.nombre_departamento}, {self.departamento.provincia})"


class Direccion(models.Model):
    """Dirección (abstracta en el modelo de dominio, R096 y R110): solo existen sus hijas, urbana y rural.

    Multi-tabla como Usuario y los roles (D-39, decisión 3): nunca se crea una ``Direccion`` sola. Tiene la
    localidad y el estado; los datos de calle o de ruta están en la hija.
    """

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    localidad = models.ForeignKey(Localidad, on_delete=models.PROTECT, related_name="direcciones")
    estado_direccion = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        verbose_name = "Dirección"
        verbose_name_plural = "Direcciones"

    def concreta(self):
        """La hija (urbana o rural) de esta dirección."""
        for nombre in ("direccionurbana", "direccionrural"):
            if hasattr(self, nombre):
                return getattr(self, nombre)
        return self

    def __str__(self):
        hija = self.concreta()
        return hija.texto() if hija is not self else f"Dirección {self.pk}"


class DireccionUrbana(Direccion):
    """Dirección urbana: calle y número obligatorios (regla 2 de PROD-ALT-INV). Número y piso son texto
    porque admiten «S/N» o «1234 bis» (D-39, decisión 6); el número tiene validador de formato y los textos libres exigen contenido (D-39)."""

    ZONA = "urbana"

    calle = models.CharField(max_length=100, validators=[validar_con_contenido])
    numero_calle = models.CharField("número", max_length=10, validators=[validar_numero_calle])
    piso = models.CharField(max_length=10, blank=True, validators=[validar_con_contenido])
    departamento = models.CharField(
        "departamento (unidad)", max_length=10, blank=True, validators=[validar_con_contenido]
    )
    barrio = models.CharField(max_length=80, blank=True, validators=[validar_con_contenido])
    referencias = models.CharField(max_length=200, blank=True, validators=[validar_con_contenido])

    class Meta:
        verbose_name = "Dirección urbana"
        verbose_name_plural = "Direcciones urbanas"

    def texto(self):
        """«Calle número, Piso X, Dpto. Y, barrio» (``dirCalle`` del prototipo)."""
        partes = [
            f"{self.calle} {self.numero_calle}".strip(),
            f"Piso {self.piso}" if self.piso else "",
            f"Dpto. {self.departamento}" if self.departamento else "",
            self.barrio,
        ]
        return ", ".join(p for p in partes if p)


class DireccionRural(Direccion):
    """Dirección rural: ruta y kilómetro obligatorios (regla 2 de PROD-ALT-INV). El kilómetro es texto con validador
    de formato: un entero de hasta 4 dígitos y un decimal con coma como máximo (D-39)."""

    ZONA = "rural"

    ruta = models.CharField("ruta o camino", max_length=100, validators=[validar_con_contenido])
    kilometro = models.CharField("kilómetro", max_length=10, validators=[validar_kilometro])
    lote = models.CharField(max_length=30, blank=True, validators=[validar_con_contenido])

    class Meta:
        verbose_name = "Dirección rural"
        verbose_name_plural = "Direcciones rurales"

    def texto(self):
        """«Ruta, km N, lote» (``dirCalle`` del prototipo)."""
        partes = [self.ruta, f"km {self.kilometro}" if self.kilometro else "", self.lote]
        return ", ".join(p for p in partes if p)


class InvernaderoQuerySet(models.QuerySet):
    """QuerySet con el alcance por usuario en un único lugar (D-28, regla 1 de PROD-CNS-INV)."""

    def en_alcance_de(self, actor):
        """Invernaderos que ``actor`` consulta: el Gerente activo, todos; el Agrónomo activo, solo los activos
        a su cargo; cualquier otro actor (o una cuenta inactiva), ninguno. El Capataz no consulta invernaderos."""
        if actor is None or not getattr(actor, "is_active", False):
            return self.none()
        rol = rol_de(actor)
        if rol == Usuario.Rol.GERENTE:
            return self.all()
        if rol == Usuario.Rol.AGRONOMO:
            return self.filter(agronomo_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO)
        return self.none()


class Invernadero(models.Model):
    """Invernadero (PROD-ALT-INV, PROD-MOD-INV, PROD-BAJ-INV, PROD-CNS-INV).

    Personal opcional (0..1 por rol, MD-87) y sin sectores al crearse (MD-74): manda el caso de uso sobre el
    diagrama. Las FK de los cuatro roles se declaran acá (A2 de D-37; R051, R149, R097 y R134).
    El nombre es único sin distinguir mayúsculas (regla 1 de PROD-ALT-INV); el servicio recorta los espacios.
    ``nombre_invernadero`` corrige el error de tipeo ``nombreInverdadero`` del diagrama (D-05, D-39).
    """

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    # Atributo y nombre visible de cada persona del invernadero, en el orden en que se muestran.
    ROLES = (
        ("agronomo", "Agrónomo"),
        ("capataz", "Capataz"),
        ("vendedor", "Vendedor"),
        ("tecnico", "Técnico"),
    )

    nombre_invernadero = models.CharField("nombre", max_length=80, validators=[validar_con_contenido])
    estado_invernadero = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    direccion = models.OneToOneField(Direccion, on_delete=models.PROTECT, related_name="invernadero")
    agronomo = models.ForeignKey(
        Agronomo, null=True, blank=True, on_delete=models.PROTECT, related_name="invernaderos"
    )
    capataz = models.ForeignKey(
        Capataz, null=True, blank=True, on_delete=models.PROTECT, related_name="invernaderos"
    )
    vendedor = models.ForeignKey(
        Vendedor, null=True, blank=True, on_delete=models.PROTECT, related_name="invernaderos"
    )
    tecnico = models.ForeignKey(
        Tecnico, null=True, blank=True, on_delete=models.PROTECT, related_name="invernaderos"
    )

    objects = InvernaderoQuerySet.as_manager()

    class Meta:
        ordering = ["nombre_invernadero"]
        verbose_name = "Invernadero"
        verbose_name_plural = "Invernaderos"
        constraints = [
            # Regla 1 de PROD-ALT-INV: nombre único sin distinguir mayúsculas.
            models.UniqueConstraint(Lower("nombre_invernadero"), name="invernadero_nombre_unico"),
        ]

    def __str__(self):
        return self.nombre_invernadero

    @property
    def activo(self):
        """True si el invernadero está activo."""
        return self.estado_invernadero == self.Estado.ACTIVO

    def tiene_sistema_iot(self):
        """Falso hasta que exista ``SistemaIoT`` (nivel 7): lo conecta el bloque IoT por un punto de extensión
        (A4 de D-37). Mientras tanto, el Técnico no hace falta (regla 5 de PROD-ALT-INV)."""
        return False

    def tiene_sectores(self):
        """Verdadero si el invernadero tiene algún sector activo o fuera de servicio (postcondición b de PROD-ALT-SCT,
        regla 3 de PROD-CNS-INV): si no, muestra la marca «sin sectores: todavía no se puede sembrar» (regla 7 de
        PROD-ALT-INV). Los sectores dados de baja no cuentan."""
        return self.sectores.filter(
            estado_sector__in=[SectorProduccion.Estado.ACTIVO, SectorProduccion.Estado.FUERA_DE_SERVICIO]
        ).exists()

    def equipo(self):
        """El personal de los cuatro roles para mostrarlo en la lista y en la ficha (``people`` y ``person`` del
        prototipo): una lista de diccionarios con ``nombre`` del rol, ``persona``, ``iniciales`` y ``estado``:
        «activo», «inactivo» (asignada pero dada de baja), «sin_asignar» o «no_hace» (el Técnico de un invernadero
        sin IoT, regla 5 de PROD-ALT-INV)."""
        equipo = []
        for atributo, nombre in self.ROLES:
            persona = getattr(self, atributo)
            if persona is None:
                estado = "no_hace" if atributo == "tecnico" and not self.tiene_sistema_iot() else "sin_asignar"
                iniciales = ""
            else:
                estado = "activo" if persona.is_active else "inactivo"
                partes = (persona.get_full_name() or persona.email).split()[:2]
                iniciales = "".join(parte[0] for parte in partes).upper()
            equipo.append({"nombre": nombre, "persona": persona, "iniciales": iniciales, "estado": estado})
        return equipo

    def roles_faltantes(self):
        """Roles sin asignar o con la persona inactiva, como lista de ``(atributo, nombre, nunca_asignado)``.
        El del Técnico solo cuenta si hay sistema IoT (regla 5 de PROD-ALT-INV, regla 3 de 8.22)."""
        faltan = []
        for atributo, nombre in self.ROLES:
            if atributo == "tecnico" and not self.tiene_sistema_iot():
                continue
            persona = getattr(self, atributo)
            if persona is None or not persona.is_active:
                faltan.append((atributo, nombre, persona is None))
        return faltan


class AlertaQuerySet(models.QuerySet):
    """QuerySet de alertas con el alcance por usuario en un único lugar (D-28, regla 1 de 8.9)."""

    def para(self, usuario):
        """Alertas que ``usuario`` recibe: el Gerente activo, las marcadas ``para_gerente`` (R007); el Agrónomo activo,
        las suyas (R049); cualquier otro, o una cuenta inactiva, ninguna."""
        if usuario is None or not getattr(usuario, "is_active", False):
            return self.none()
        rol = rol_de(usuario)
        if rol == Usuario.Rol.GERENTE:
            return self.filter(para_gerente=True)
        if rol == Usuario.Rol.AGRONOMO:
            return self.filter(agronomo_id=usuario.pk)
        return self.none()

    def activas(self):
        """Solo las alertas en estado «activa»."""
        return self.filter(estado_alerta="activa")

    def no_leidas(self):
        """Solo las alertas «no leída» (las que cuenta la campana, tarea de notificaciones)."""
        return self.filter(estado_lectura_alerta="no_leida")


class Alerta(models.Model):
    """Alerta (D-38; docs/modelo/maestros.md, ficha ``Alerta``): aviso de un hecho que requiere atención y que sigue
    activo hasta que ese hecho se resuelve.

    - Regla 7 de 8.18: ``estado_alerta`` nace «activa» y pasa a «resuelta» cuando se resuelve el hecho (ahí se carga
      ``fecha_resolucion``); ``estado_lectura_alerta`` nace «no leída» y pasa a «leída» cuando la abre uno de sus
      destinatarios. Los dos estados son independientes.
    - Regla 1 de 8.9: al menos un destinatario, el Gerente (R007, ``para_gerente``: hay a lo sumo un Gerente activo, D-09)
      o el Agrónomo (R049, ``agronomo``). Se aparta del diagrama (FK al Gerente) para que el Gerente nuevo vea lo
      pendiente (D-14).
    - ``tipo_alerta`` es un código registrado en ``maestros.alertas`` (sin ``choices``: cada app agrega los suyos).
    - ``clave_estado`` identifica la condición de las alertas de estado (a lo sumo una activa por invernadero, tipo y
      clave); en las de evento es nula.
    """

    class Severidad(models.TextChoices):
        CRITICA = "critica", "Crítica"
        ADVERTENCIA = "advertencia", "Advertencia"
        INFORMATIVA = "informativa", "Informativa"

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        RESUELTA = "resuelta", "Resuelta"

    class Lectura(models.TextChoices):
        NO_LEIDA = "no_leida", "No leída"
        LEIDA = "leida", "Leída"

    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="alertas")
    tipo_alerta = models.CharField("tipo", max_length=50)
    descripcion_alerta = models.CharField("descripción", max_length=200)
    nivel_severidad = models.CharField("severidad", max_length=15, choices=Severidad.choices)
    estado_alerta = models.CharField("estado", max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    estado_lectura_alerta = models.CharField(
        "lectura", max_length=10, choices=Lectura.choices, default=Lectura.NO_LEIDA
    )
    fecha_hora_alerta = models.DateTimeField("fecha y hora", default=timezone.now, editable=False)
    fecha_resolucion = models.DateTimeField("fecha de resolución", null=True, blank=True)
    para_gerente = models.BooleanField("para el Gerente", default=False)
    # A2 de D-37: la FK se declara acá, en la app de nivel mayor. Es el mismo modelo que ``Invernadero.agronomo``.
    agronomo = models.ForeignKey(Agronomo, null=True, blank=True, on_delete=models.PROTECT, related_name="alertas")
    clave_estado = models.CharField(max_length=100, null=True, blank=True)

    objects = AlertaQuerySet.as_manager()

    class Meta:
        ordering = ["-fecha_hora_alerta", "-id"]
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        indexes = [models.Index(fields=["invernadero", "estado_alerta"], name="alerta_inv_estado")]
        constraints = [
            # Regla 1 de 8.9: toda alerta tiene al menos un destinatario.
            models.CheckConstraint(
                condition=Q(para_gerente=True) | Q(agronomo__isnull=False), name="alerta_con_destinatario"
            ),
            # Regla 7 de 8.18: la fecha de resolución se carga cuando la alerta pasa a resuelta, y solo entonces.
            models.CheckConstraint(
                condition=(Q(estado_alerta="activa") & Q(fecha_resolucion__isnull=True))
                | (Q(estado_alerta="resuelta") & Q(fecha_resolucion__isnull=False)),
                name="alerta_resolucion_coherente",
            ),
            # Alertas de estado: a lo sumo una activa por invernadero, tipo y clave. Índice parcial: no sube el UPDATE a
            # FOR UPDATE (docs/patrones/bloqueos.md). Respaldo del bloqueo del invernadero.
            models.UniqueConstraint(
                fields=["invernadero", "tipo_alerta", "clave_estado"],
                condition=Q(estado_alerta="activa") & Q(clave_estado__isnull=False),
                name="alerta_de_estado_unica",
            ),
        ]

    def __str__(self):
        """La descripción: es el texto que guarda la auditoría al referenciarla (D-36)."""
        return self.descripcion_alerta


# ---- MAE-03: tipos de etapa, sectores, cultivos, variedades, ciclos y etapas ----

# Los seis perfiles familiares, lista fija en código (docs/modelo/maestros.md, «Tipo de etapa»; confirmada el 19/11/2026).
# Los códigos son de MAE-03 (la ficha del modelo da solo los nombres visibles): se registran en «temas abiertos».
PERFILES_FAMILIARES = (
    ("hoja_verde", "Hoja verde"),
    ("pastura", "Pastura"),
    ("frutos_grandes", "Frutos grandes"),
    ("frutos_pequenos", "Frutos pequeños"),
    ("flores", "Flores"),
    ("hierbas", "Hierbas"),
)
CODIGOS_DE_PERFIL = [codigo for codigo, _ in PERFILES_FAMILIARES]


class TipoEtapa(models.Model):
    """Tipo de etapa (MD-52, R092 y R093): catálogo fijo de cinco filas que carga la migración ``0005``; no tiene alta,
    modificación ni baja. Las reglas se apoyan en ``codigo``, nunca en el nombre. ``perfiles_permitidos`` es la lista
    de valores de ``Variedad.perfil_familia`` que admite el tipo («permitida» no es «obligatoria»)."""

    # Color fijo de cada tipo en la interfaz (``--e-ger``, ``--e-cre``, ``--e-flo``, ``--e-fru``, ``--e-mad``).
    CLASES_DE_COLOR = {
        "germinacion": "ger",
        "crecimiento": "cre",
        "floracion": "flo",
        "fructificacion": "fru",
        "maduracion": "mad",
    }

    codigo = models.CharField(max_length=20, unique=True)
    nombre_etapa = models.CharField("nombre", max_length=20)
    puesto_global = models.PositiveSmallIntegerField("puesto global", unique=True)
    perfiles_permitidos = models.JSONField("perfiles permitidos", default=list)

    class Meta:
        ordering = ["puesto_global"]
        verbose_name = "Tipo de etapa"
        verbose_name_plural = "Tipos de etapa"
        constraints = [
            models.CheckConstraint(
                condition=Q(puesto_global__gte=1, puesto_global__lte=5), name="tipo_etapa_puesto_1_a_5"
            ),
        ]

    def __str__(self):
        return self.nombre_etapa

    @property
    def clase_de_color(self):
        """Sufijo de la clase de color del tipo (``ger``, ``cre``...): se elige por ``codigo``."""
        return self.CLASES_DE_COLOR.get(self.codigo, "ger")


class SectorProduccionQuerySet(models.QuerySet):
    """QuerySet de sectores con el alcance por usuario en un único lugar (D-28, regla 1 de PROD-CNS-SCT)."""

    def en_alcance_de(self, actor):
        """Sectores que ``actor`` consulta: los de los invernaderos de su alcance (el Gerente, todos, en solo lectura; el
        Agrónomo, los de los activos a su cargo). Cualquier otro actor, ninguno."""
        return self.filter(invernadero__in=Invernadero.objects.en_alcance_de(actor))


class SectorProduccion(models.Model):
    """Sector de producción (PROD-ALT-SCT, PROD-MOD-SCT, PROD-BAJ-SCT, PROD-CNS-SCT; R098 y R092).

    Tres estados (manda el caso de uso sobre el modelo, que nombra dos): «activo», «fuera de servicio» (conserva su
    capacidad pero no recibe plantas ni órdenes) e «inactivo» (baja lógica). Los agujeros ocupados, comprometidos y
    libres se calculan, no se guardan (regla 5 de PROD-ALT-SCT). El nombre es único por invernadero sin distinguir
    mayúsculas, bajas incluidas. Sin ubicación ni densidad (regla 6).
    """

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        FUERA_DE_SERVICIO = "fuera_de_servicio", "Fuera de servicio"
        INACTIVO = "inactivo", "Inactivo"

    # A2 de D-37: las FK se declaran acá, en la app de nivel mayor.
    invernadero = models.ForeignKey(Invernadero, on_delete=models.PROTECT, related_name="sectores")
    tipo_etapa = models.ForeignKey(TipoEtapa, on_delete=models.PROTECT, related_name="sectores")
    nombre_sector = models.CharField("nombre", max_length=40, validators=[validar_con_contenido])
    cant_agujeros_total = models.PositiveIntegerField("agujeros totales")
    estado_sector = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)

    objects = SectorProduccionQuerySet.as_manager()

    class Meta:
        ordering = ["nombre_sector"]
        verbose_name = "Sector de producción"
        verbose_name_plural = "Sectores de producción"
        constraints = [
            # Regla 2 de PROD-ALT-SCT: nombre único por invernadero, sin distinguir mayúsculas.
            models.UniqueConstraint(Lower("nombre_sector"), "invernadero", name="sector_nombre_unico_por_invernadero"),
            # Regla 4 de PROD-ALT-SCT: la cantidad es un entero mayor que cero.
            models.CheckConstraint(condition=Q(cant_agujeros_total__gt=0), name="sector_agujeros_mayor_que_cero"),
            models.CheckConstraint(
                condition=Q(estado_sector__in=["activo", "fuera_de_servicio", "inactivo"]), name="sector_estado_valido"
            ),
        ]

    def __str__(self):
        """El nombre: es el texto que guarda la auditoría al referenciarlo (D-36)."""
        return self.nombre_sector

    @property
    def activo(self):
        """True si el sector está activo."""
        return self.estado_sector == self.Estado.ACTIVO


class Cultivo(models.Model):
    """Cultivo (PROD-ALT-CLT y siguientes; R074): lo comparten todos los invernaderos. Nombre de hasta 40 caracteres
    (con la variedad de hasta 50, la semilla «Semilla {cultivo} {variedad}» entra en los 100 del insumo), único sin
    distinguir mayúsculas; el servicio guarda el nombre recortado."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    nombre_cultivo = models.CharField("nombre", max_length=40, validators=[validar_con_contenido])
    estado_cultivo = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        ordering = ["nombre_cultivo"]
        verbose_name = "Cultivo"
        verbose_name_plural = "Cultivos"
        constraints = [
            # Regla 2 de PROD-ALT-CLT: nombre único entre todos los cultivos, activos o inactivos.
            models.UniqueConstraint(Lower("nombre_cultivo"), name="cultivo_nombre_unico"),
            models.CheckConstraint(
                condition=Q(estado_cultivo__in=["activo", "inactivo"]), name="cultivo_estado_valido"
            ),
        ]

    def __str__(self):
        return self.nombre_cultivo

    @property
    def activo(self):
        """True si el cultivo está activo."""
        return self.estado_cultivo == self.Estado.ACTIVO


class Variedad(models.Model):
    """Variedad de un cultivo, con las columnas mínimas de MAE-03 (contar las activas de un cultivo y calcular qué
    variedades dejan de poder sembrarse al cambiar el tipo de un sector). INV-03 agrega el resto con una migración
    propia (docs/modelo/maestros.md, «Variedad, Ciclo y EtapaProductiva»)."""

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"

    cultivo = models.ForeignKey(Cultivo, on_delete=models.PROTECT, related_name="variedades")
    nombre_variedad = models.CharField("nombre", max_length=50)
    perfil_familia = models.CharField("perfil familiar", max_length=20, choices=PERFILES_FAMILIARES)
    estado_variedad = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        ordering = ["nombre_variedad"]
        verbose_name = "Variedad"
        verbose_name_plural = "Variedades"
        constraints = [
            models.CheckConstraint(
                condition=Q(estado_variedad__in=["activo", "inactivo"]), name="variedad_estado_valido"
            ),
            models.CheckConstraint(condition=Q(perfil_familia__in=CODIGOS_DE_PERFIL), name="variedad_perfil_valido"),
        ]

    def __str__(self):
        return f"{self.cultivo} {self.nombre_variedad}"


class Ciclo(models.Model):
    """Ciclo de una variedad (R091, uno a uno, composición): se crea junto con la variedad. La duración completa se
    deriva de sus etapas y no se guarda (MD-70)."""

    variedad = models.OneToOneField(Variedad, on_delete=models.PROTECT, related_name="ciclo")

    class Meta:
        verbose_name = "Ciclo"
        verbose_name_plural = "Ciclos"

    def __str__(self):
        return f"Ciclo de {self.variedad}"


class EtapaProductiva(models.Model):
    """Etapa de un ciclo (R090 y R093). Una variedad no repite un tipo en su ciclo. Sin estado propio: sigue el de su
    variedad (decidido el 19/11/2026). ``descripcion_etapa`` no la pide ningún caso de uso: queda vacía."""

    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT, related_name="etapas")
    tipo_etapa = models.ForeignKey(TipoEtapa, on_delete=models.PROTECT, related_name="etapas")
    duracion_estimada_dias = models.PositiveIntegerField("duración estimada (días)")
    descripcion_etapa = models.TextField("descripción", blank=True)

    class Meta:
        verbose_name = "Etapa productiva"
        verbose_name_plural = "Etapas productivas"
        constraints = [
            models.UniqueConstraint(fields=["ciclo", "tipo_etapa"], name="etapa_un_tipo_por_ciclo"),
            models.CheckConstraint(condition=Q(duracion_estimada_dias__gt=0), name="etapa_duracion_mayor_que_cero"),
        ]

    def __str__(self):
        return f"{self.tipo_etapa} de {self.ciclo}"
