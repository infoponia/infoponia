# Formularios de inventario (INV-01): categorías (tipos de insumo) e insumos del catálogo. Como en maestros, el formulario solo
# normaliza lo que se escribe y arma las opciones; todas las reglas las aplican los servicios (inventario/servicios/) y la vista
# pasa sus errores al formulario. Los campos son opcionales a nivel de formulario: el servicio da el error de cada uno.

from django import forms
from django.urls import reverse

from inventario.categorias import SEMILLAS
from inventario.models import TipoInsumo
from inventario.unidades import Unidad, texto_de_decimales

# Texto de cada opción de consumo directo (MODALS['cat-form'] del prototipo).
OPCIONES_DE_CONSUMO_DIRECTO = [
    (
        TipoInsumo.ConsumoDirecto.NO_ADMITE,
        "No admite",
        "Sus insumos solo se consumen con una orden de trabajo: siembra, entrega o mantenimiento.",
    ),
    (
        TipoInsumo.ConsumoDirecto.COMO_GASTO,
        "Como gasto",
        "Se registran con «Registrar aplicación de insumos» y su costo va a gasto. Ejemplo: limpieza.",
    ),
    (
        TipoInsumo.ConsumoDirecto.COMO_COSTO_DE_LOS_LOTES,
        "Como costo de los lotes",
        "Se registran igual, y su costo se reparte entre los lotes de plantas de los sectores donde se aplicó. Ejemplo: nutrientes.",
    ),
]


def _texto(etiqueta, largo, **extra):
    """Campo de texto opcional a nivel de formulario (las reglas son del servicio) con su largo máximo."""
    return forms.CharField(
        label=etiqueta,
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "maxlength": largo, "autocomplete": "off", **extra}),
    )


class FormularioCategoria(forms.Form):
    """Nueva categoría o modificar una (CMP-ALT-TIN y CMP-MOD-TIN, ``MODALS['cat-form']`` del prototipo). El consumo directo se elige
    con fichas de radio (funcionan sin JavaScript). Las reglas (nombre obligatorio, con contenido, único; consumo directo obligatorio
    y sin reservas) las aplica el servicio."""

    nombre = _texto("Nombre", 100, placeholder="Ej. Fitosanitarios")
    consumo_directo = forms.CharField(label="Consumo directo", required=False, widget=forms.HiddenInput)

    def __init__(self, *args, tipo=None, **kwargs):
        if tipo is not None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", {"nombre": tipo.nombre_tipo_insumo, "consumo_directo": tipo.consumo_directo})
        super().__init__(*args, **kwargs)
        self.tipo = tipo

    @property
    def opciones_de_consumo(self):
        """Las tres fichas: ``(valor, título, ayuda, elegida)``."""
        elegido = self["consumo_directo"].value()
        return [(valor, titulo, ayuda, valor == elegido) for valor, titulo, ayuda in OPCIONES_DE_CONSUMO_DIRECTO]

    def datos_del_servicio(self):
        """Los argumentos de ``alta_tipo_insumo`` y ``modificar_tipo_insumo`` (sin el actor ni el id) a partir de lo escrito."""
        return {
            "nombre": self.cleaned_data.get("nombre", ""),
            "consumo_directo": self.cleaned_data.get("consumo_directo", ""),
        }


class FormularioInsumo(forms.Form):
    """Nuevo insumo o modificar uno (CMP-ALT-INS y CMP-MOD-INS, ``MODALS['insumo-form']`` del prototipo).

    Con ``insumo`` (modificar) el formulario sin datos arranca con los suyos. ``bloqueos`` es ``{campo: motivo}`` de
    ``bloqueos_de_modificacion``: un campo bloqueado no se ofrece, se muestra su valor con el motivo y se envía el valor actual
    (el servicio solo rechaza un campo bloqueado si su valor cambia, regla 3 de CMP-MOD-INS).
    """

    nombre = _texto("Nombre", 100)
    descripcion = forms.CharField(
        label="Descripción (opcional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "field-input",
                "rows": 2,
                "maxlength": 300,
                "placeholder": "Ej. Solución nutritiva para hojas verdes, dosis 2 ml por litro",
            }
        ),
    )
    categoria = forms.CharField(label="Categoría", required=False, widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}))
    unidad = forms.CharField(label="Unidad de medida", required=False, widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}))
    controla_vencimiento = forms.BooleanField(label="Controla vencimiento", required=False)

    def __init__(self, *args, insumo=None, bloqueos=None, categorias=(), **kwargs):
        if insumo is not None and not args and "data" not in kwargs:
            kwargs.setdefault(
                "initial",
                {
                    "nombre": insumo.nombre_insumo,
                    "descripcion": insumo.descripcion_insumo,
                    "categoria": insumo.tipo_insumo_id,
                    "unidad": insumo.unidad_medida_insumo,
                    "controla_vencimiento": insumo.controla_vencimiento,
                },
            )
        super().__init__(*args, **kwargs)
        self.insumo = insumo
        self.bloqueos = bloqueos or {}
        self.fields["categoria"].widget.choices = [("", "Seleccionar…")] + [
            (tipo.pk, _texto_de_categoria(tipo)) for tipo in categorias
        ]
        self.fields["unidad"].widget.choices = [("", "Seleccionar…")] + [
            (unidad.value, f"{unidad.label} ({texto_de_decimales(unidad)})") for unidad in Unidad
        ]

    def datos_del_servicio(self):
        """Los argumentos de ``alta_insumo`` y ``modificar_insumo`` (sin el actor ni el id) a partir de lo escrito; un campo bloqueado
        lleva su valor actual."""
        datos = self.cleaned_data
        resultado = {
            "nombre": datos.get("nombre", ""),
            "descripcion": datos.get("descripcion", ""),
            "tipo_insumo_id": datos.get("categoria") or None,
            "unidad": datos.get("unidad", ""),
            "controla_vencimiento": bool(datos.get("controla_vencimiento")),
        }
        if self.insumo is not None:
            if "categoria" in self.bloqueos:
                resultado["tipo_insumo_id"] = self.insumo.tipo_insumo_id
            if "unidad" in self.bloqueos:
                resultado["unidad"] = self.insumo.unidad_medida_insumo
            if "controla_vencimiento" in self.bloqueos:
                resultado["controla_vencimiento"] = self.insumo.controla_vencimiento
        return resultado


def _texto_de_categoria(tipo):
    """El texto de una categoría en la lista: su nombre, con la marca «del sistema» o «inactiva» si corresponde."""
    marca = " (del sistema)" if tipo.es_del_sistema else (" — inactiva" if tipo.estado_tipo_insumo != TipoInsumo.Estado.ACTIVO else "")
    return f"{tipo.nombre_tipo_insumo}{marca}"


def categorias_para_el_alta():
    """CMP-ALT-INS regla 4: las categorías activas menos Semillas (``catOpts`` del prototipo), por nombre."""
    return list(
        TipoInsumo.objects.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO)
        .exclude(codigo=SEMILLAS)
        .order_by("nombre_tipo_insumo", "id")
    )


def categorias_para_modificar(insumo):
    """CMP-MOD-INS regla 3: las activas que no son del sistema (un insumo no entra ni sale de ellas), más la categoría actual del insumo
    aunque esté inactiva o sea del sistema, para que la lista siempre la muestre."""
    activas = TipoInsumo.objects.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO, es_del_sistema=False)
    categorias = list(activas.order_by("nombre_tipo_insumo", "id"))
    if all(tipo.pk != insumo.tipo_insumo_id for tipo in categorias):
        categorias.append(insumo.tipo_insumo)
    return categorias


# ---- INV-02: habilitar un insumo en un invernadero y modificar su mínimo y precio (CMP-HAB-IIN y CMP-MOD-IIN) ----


class FormularioExistencia(forms.Form):
    """«Habilitar insumo» (``MODALS.habilitar`` del prototipo) y «Mínimo y precio» (``MODALS['ex-form']``). Solo normaliza lo escrito: las
    reglas de cantidad y de precio las aplica el servicio (reglas 3 y 4 de CMP-HAB-IIN). ``insumos`` e ``invernaderos`` arman las listas
    de elección; con ``fijo_insumo`` o ``fijo_invernadero`` el campo no se ofrece (se muestra su valor)."""

    insumo = forms.CharField(label="Insumo", required=False, widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}))
    invernadero = forms.CharField(label="Invernadero", required=False, widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}))
    cant_min = forms.CharField(
        label="Stock mínimo",
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "inputmode": "decimal", "autocomplete": "off"}),
    )
    referencia_precio = forms.CharField(
        label="Precio de referencia",
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "inputmode": "decimal", "autocomplete": "off"}),
    )

    def __init__(self, *args, insumos=(), invernaderos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["insumo"].widget.choices = [("", "Seleccionar…")] + [(i.pk, i.nombre_insumo) for i in insumos]
        self.fields["invernadero"].widget.choices = [("", "Seleccionar…")] + [(g.pk, g.nombre_invernadero) for g in invernaderos]

    def datos_del_servicio(self):
        """Los argumentos ``cant_min`` y ``referencia_precio`` del servicio, tal como se escribieron (el servicio los valida)."""
        return {
            "cant_min": self.cleaned_data.get("cant_min", ""),
            "referencia_precio": self.cleaned_data.get("referencia_precio", ""),
        }


# ---- INV-03: variedades (PROD-ALT-VAR y PROD-MOD-VAR, ``VIEWS['var-form']`` del prototipo) ----

# Las dos etapas obligatorias de todo ciclo (regla 4 de PROD-ALT-VAR): siempre incluidas y sin poder sacarse.
ETAPAS_FIJAS = ("germinacion", "maduracion")
# (variable, título, unidad, género): los cuatro rangos ambientales del formulario (``RANGOS`` del prototipo).
RANGOS_DEL_FORMULARIO = (
    ("temp_ambiente", "Temperatura ambiente", "°C", "f"),
    ("humedad", "Humedad", "%", "f"),
    ("intensidad_luz", "Intensidad lumínica", "lux", "f"),
    ("fotoperiodo", "Fotoperíodo", "h/día", "m"),
)
CAMPOS_DE_RANGO = [f"{variable}_{lado}" for variable, *_ in RANGOS_DEL_FORMULARIO for lado in ("min", "max")]


def texto_de_numero(valor):
    """Un ``Decimal`` o entero como texto para mostrar: coma decimal y sin ceros de más (``Decimal('18.50')`` → ``18,5``)."""
    texto = str(valor)
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _numerico(etiqueta="", modo="numeric"):
    """Campo de texto numérico opcional a nivel de formulario (las reglas son del servicio)."""
    return forms.CharField(
        label=etiqueta,
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input num", "inputmode": modo, "autocomplete": "off"}),
    )


class FormularioVariedad(forms.Form):
    """Nueva variedad o modificar una (PROD-ALT-VAR y PROD-MOD-VAR). Solo normaliza lo escrito y arma las filas de etapas; todas las
    reglas las aplica el servicio (``DatosDeVariedad``), que nunca confía en la pantalla.

    ``tipos`` son los ``TipoEtapa`` del catálogo (en su orden). ``variedad`` y ``etapas_actuales`` (de ``ciclos.etapas_de``) arman el
    valor inicial de una variedad ya guardada. ``etapas_bloqueadas`` (la variedad ya tiene lotes, regla 3 de PROD-MOD-VAR) congela
    qué etapas hay: se reenvían tal cual, sin poder agregar ni quitar. ``perfil_bloqueado`` congela el perfil (regla 4).
    Las etapas viajan como ``etapa_<codigo>`` (casilla) y ``duracion_<codigo>`` (días)."""

    nombre = _texto("Nombre de la variedad", 50)
    perfil_familia = forms.CharField(
        label="Perfil familiar", required=False, widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""})
    )
    duracion_post_cosecha = _numerico("Duración postcosecha")
    peso_promedio_planta = _numerico("Peso promedio por planta")

    def __init__(self, *args, tipos, variedad=None, etapas_actuales=(), etapas_bloqueadas=False, perfil_bloqueado=False, **kwargs):
        from maestros.models import Variedad

        if variedad is not None:  # también con datos enviados: un campo deshabilitado (el perfil con lotes) toma su valor inicial
            inicial = {
                "nombre": variedad.nombre_variedad,
                "perfil_familia": variedad.perfil_familia,
                "duracion_post_cosecha": str(variedad.duracion_post_cosecha),
                "peso_promedio_planta": str(variedad.peso_promedio_planta),
            }
            for campo in CAMPOS_DE_RANGO:
                inicial[campo] = texto_de_numero(getattr(variedad, campo))
            for etapa in etapas_actuales:
                inicial[f"etapa_{etapa.codigo}"] = "1"
                inicial[f"duracion_{etapa.codigo}"] = str(etapa.duracion_dias)
            kwargs.setdefault("initial", inicial)
        super().__init__(*args, **kwargs)
        self.tipos = list(tipos)
        self.variedad = variedad
        self.etapas_bloqueadas = etapas_bloqueadas
        self.perfil_bloqueado = perfil_bloqueado
        self.fields["perfil_familia"].widget.choices = [("", "Seleccionar…")] + list(Variedad._meta.get_field("perfil_familia").choices)
        self.fields["perfil_familia"].disabled = perfil_bloqueado  # regla 4 de PROD-MOD-VAR: no se cambia con lotes activos u órdenes
        # HTMX solo redibuja las etapas al cambiar el perfil, sin validar (``hx-swap`` sin saltar a ningún lado). Sin JavaScript, el botón
        # «Actualizar etapas» de la pantalla hace lo mismo con un envío común.
        self.fields["perfil_familia"].widget.attrs.update(
            {
                "hx-get": reverse("variedades:etapas_del_perfil"),
                "hx-target": "#etapas",
                "hx-swap": "innerHTML show:none",
                "hx-include": "closest form",
            }
        )
        for campo in CAMPOS_DE_RANGO:
            self.fields[campo] = _numerico(modo="decimal")
        for tipo in self.tipos:
            self.fields[f"duracion_{tipo.codigo}"] = _numerico(f"Duración estimada de {tipo.nombre_etapa} en días")

    # -- lo escrito --

    def valor(self, nombre):
        """El valor de un campo (inicial o enviado) como texto sin espacios de los bordes."""
        valor = self[nombre].value()
        return "" if valor is None else str(valor).strip()

    @property
    def perfil(self):
        """El perfil elegido ('' si todavía no hay)."""
        return self.valor("perfil_familia")

    def _marcada(self, codigo):
        """¿La etapa ``codigo`` está incluida? Las fijas, siempre; las demás, según la casilla enviada o el valor inicial."""
        if codigo in ETAPAS_FIJAS:
            return True
        if self.is_bound:
            return self.data.get(f"etapa_{codigo}") not in (None, "", "0", "false")
        return bool(self.initial.get(f"etapa_{codigo}"))

    def _permitida(self, tipo):
        return tipo.codigo in ETAPAS_FIJAS or self.perfil in tipo.perfiles_permitidos

    def se_envia(self, tipo):
        """¿La etapa va en los datos del servicio? Incluida y permitida por el perfil; con lotes, toda la incluida (si el perfil nuevo
        no la permite, el servicio lo rechaza con un error en el perfil)."""
        return self._marcada(tipo.codigo) and (self._permitida(tipo) or self.etapas_bloqueadas)

    @property
    def filas_de_etapas(self):
        """Las filas de etapas que se ofrecen: las fijas, las que permite el perfil elegido y, con lotes, las ya incluidas. Cada
        fila: ``tipo``, ``clase`` de color, ``marcada``, ``fija``, ``congelada`` (su casilla no se cambia) y ``dias`` (el campo)."""
        filas = []
        for tipo in self.tipos:
            marcada = self._marcada(tipo.codigo)
            if not (self._permitida(tipo) or (self.etapas_bloqueadas and marcada)):
                continue
            filas.append(
                {
                    "tipo": tipo,
                    "clase": tipo.CLASES_DE_COLOR.get(tipo.codigo, "ger"),
                    "marcada": marcada,
                    "fija": tipo.codigo in ETAPAS_FIJAS,
                    "congelada": tipo.codigo in ETAPAS_FIJAS or self.etapas_bloqueadas,
                    "dias": self[f"duracion_{tipo.codigo}"],
                }
            )
        return filas

    @property
    def etapas_no_ofrecidas(self):
        """Los nombres de las etapas que el perfil elegido no permite (para el aviso «No se ofrecen para el perfil …»)."""
        if not self.perfil:
            return []
        return [t.nombre_etapa for t in self.tipos if not self._permitida(t)]

    @property
    def rangos(self):
        """Los cuatro rangos para la plantilla: ``(título, unidad, campo mínimo, campo máximo, género)``."""
        return [
            (titulo, unidad, self[f"{variable}_min"], self[f"{variable}_max"], genero)
            for variable, titulo, unidad, genero in RANGOS_DEL_FORMULARIO
        ]

    def campos_ocultos(self):
        """Todo lo escrito como pares ``(nombre, valor)`` para reenviarlo desde el resumen sin tocarlo. El servicio vuelve a validar todo."""
        pares = [("nombre", self.valor("nombre")), ("perfil_familia", self.perfil)]
        for tipo in self.tipos:
            if self.se_envia(tipo):
                pares.append((f"etapa_{tipo.codigo}", "1"))
            pares.append((f"duracion_{tipo.codigo}", self.valor(f"duracion_{tipo.codigo}")))
        pares += [(campo, self.valor(campo)) for campo in (*CAMPOS_DE_RANGO, "duracion_post_cosecha", "peso_promedio_planta")]
        return pares

    def datos_del_servicio(self):
        """Los ``DatosDeVariedad`` de lo escrito: las etapas que se envían, como pares ``(codigo, dias)`` en el orden del catálogo."""
        from inventario.servicios.variedades import DatosDeVariedad

        datos = {
            "nombre": self.valor("nombre"),
            "perfil_familia": self.perfil,
            "etapas": tuple((t.codigo, self.valor(f"duracion_{t.codigo}")) for t in self.tipos if self.se_envia(t)),
            "duracion_post_cosecha": self.valor("duracion_post_cosecha"),
            "peso_promedio_planta": self.valor("peso_promedio_planta"),
        }
        datos.update({campo: self.valor(campo) for campo in CAMPOS_DE_RANGO})
        return DatosDeVariedad(**datos)
