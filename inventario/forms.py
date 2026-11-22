# Formularios de inventario (INV-01): categorías (tipos de insumo) e insumos del catálogo. Como en maestros, el formulario solo
# normaliza lo que se escribe y arma las opciones; todas las reglas las aplican los servicios (inventario/servicios/) y la vista
# pasa sus errores al formulario. Los campos son opcionales a nivel de formulario: el servicio da el error de cada uno.

from django import forms

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
