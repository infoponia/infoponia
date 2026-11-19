# Modelos de maestros (nivel 3 de D-37) para MAE-01: la geografía de Georef, la dirección (jerarquía multi-tabla,
# como Usuario y los roles, D-01) y el invernadero con su personal. Decisiones D-04, D-05, D-28, D-37 y D-39.

from django.db import models
from django.db.models.functions import Lower

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
        """Falso hasta que exista ``SectorProduccion``: el invernadero muestra la marca «sin sectores: todavía
        no se puede sembrar» (regla 7 de PROD-ALT-INV)."""
        return False

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
