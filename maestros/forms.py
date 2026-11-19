# Formularios de maestros: el alta de un invernadero (PROD-ALT-INV). Como en core, el formulario solo normaliza lo que
# se escribe y arma las listas; todas las reglas las aplica el servicio (maestros/servicios/invernaderos.py), y la
# vista pasa sus errores al formulario. Provincia, departamento y localidad son listas encadenadas de Georef (regla 3).

from django import forms
from django.urls import reverse_lazy

from maestros.servicios import geografia
from maestros.servicios.invernaderos import NOMBRE_DEL_ROL, cuentas_asignables

SELECCIONAR = [("", "Seleccionar…")]


def _texto(etiqueta, largo, **extra):
    """Campo de texto opcional a nivel de formulario (las reglas son del servicio) con su largo máximo."""
    return forms.CharField(
        label=etiqueta,
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "maxlength": largo, "autocomplete": "off", **extra}),
    )


def _lista(etiqueta):
    """Campo de lista desplegable propio (D-24); las opciones las arma el formulario al construirse."""
    return forms.CharField(
        label=etiqueta,
        required=False,
        widget=forms.Select(attrs={"class": "field-input", "data-desplegable": ""}),
    )


class FormularioInvernadero(forms.Form):
    """Alta de un invernadero (PROD-ALT-INV, ``VIEWS['inv-form']`` del prototipo).

    ``provincia`` y ``departamento`` no se guardan: solo encadenan las listas hasta la ``localidad``. Las opciones de
    cada lista salen de lo que llega en ``data``: sin provincia no hay departamentos, y sin departamento, no hay
    localidades. Con HTMX, al cambiar una lista se pide el fragmento de la siguiente (``departamentos`` y
    ``localidades`` en views.py); sin JavaScript, el botón «Actualizar» reenvía el formulario sin guardar.
    """

    nombre = _texto("Nombre", 80, placeholder="Ej. Invernadero E")
    tipo_direccion = forms.ChoiceField(
        label="Tipo de dirección",
        required=False,
        choices=[("urbana", "Urbana"), ("rural", "Rural")],
        widget=forms.RadioSelect,
    )
    provincia = _lista("Provincia")
    departamento = _lista("Departamento")
    localidad = _lista("Localidad")
    # Dirección urbana (regla 2): calle y número obligatorios.
    calle = _texto("Calle", 100)
    numero_calle = _texto("Número", 10)
    piso = _texto("Piso", 10)
    departamento_unidad = _texto("Departamento (unidad)", 10)
    barrio = _texto("Barrio", 80)
    referencias = _texto("Referencias", 200)
    # Dirección rural (regla 2): ruta y kilómetro obligatorios.
    ruta = _texto("Ruta o camino", 100)
    kilometro = _texto("Kilómetro", 10)
    lote_rural = _texto("Lote", 30)
    # Personal (regla 4): opcional; solo cuentas activas de cada rol.
    agronomo = _lista("Agrónomo")
    capataz = _lista("Capataz")
    vendedor = _lista("Vendedor")
    tecnico = _lista("Técnico")

    AYUDAS = {
        "agronomo": "Es quien crea los sectores y planifica las órdenes.",
        "capataz": "Recibe las órdenes de siembra, transición y cosecha.",
        "vendedor": "Vende lo que produce este invernadero.",
        "tecnico": "Solo hace falta si el invernadero tiene sistema IoT.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def valor(nombre):
            """Lo que se eligió en el campo ``nombre`` (enviado o inicial), o texto vacío."""
            return self[nombre].value() or ""

        self.fields["provincia"].widget.choices = SELECCIONAR + [(p.pk, p.nombre_provincia) for p in geografia.provincias()]
        self.fields["departamento"].widget.choices = SELECCIONAR + [
            (d.pk, d.nombre_departamento) for d in geografia.departamentos_de(valor("provincia"))
        ]
        self.fields["localidad"].widget.choices = SELECCIONAR + [
            (loc.pk, loc.nombre_localidad) for loc in geografia.localidades_de(valor("departamento"))
        ]
        # HTMX (regla 3): al cambiar el tipo se piden los datos de su dirección; al cambiar la provincia, sus
        # departamentos; al cambiar el departamento, sus localidades. Sin JavaScript no hacen nada y queda «Actualizar».
        self.fields["tipo_direccion"].widget.attrs.update(
            {
                "hx-get": reverse_lazy("maestros:campos_direccion"),
                "hx-target": "#campos-direccion",
                "hx-include": "closest form",
                "hx-trigger": "change",
            }
        )
        self.fields["provincia"].widget.attrs.update(
            {
                "hx-get": reverse_lazy("maestros:departamentos"),
                "hx-target": "#departamento-y-localidad",
                "hx-trigger": "change",
            }
        )
        self.fields["departamento"].widget.attrs.update(
            {
                "hx-get": reverse_lazy("maestros:localidades"),
                "hx-target": "#campo-localidad",
                "hx-trigger": "change",
            }
        )
        for atributo in NOMBRE_DEL_ROL:
            self.fields[atributo].widget.choices = [("", "Sin asignar")] + [
                (c.pk, c.get_full_name() or c.email) for c in cuentas_asignables(atributo)
            ]

    @property
    def es_urbana(self):
        """True si se eligió una dirección urbana."""
        return self["tipo_direccion"].value() == "urbana"

    @property
    def es_rural(self):
        """True si se eligió una dirección rural."""
        return self["tipo_direccion"].value() == "rural"

    @property
    def personal(self):
        """Los cuatro campos de personal con su ayuda, en el orden de la pantalla."""
        return [(self[atributo], self.AYUDAS[atributo]) for atributo in NOMBRE_DEL_ROL]

    def datos_del_servicio(self):
        """Los argumentos de ``alta_invernadero`` (sin el actor) a partir de lo escrito."""
        datos = self.cleaned_data
        return {
            "nombre": datos.get("nombre", ""),
            "tipo_direccion": datos.get("tipo_direccion", ""),
            "localidad_id": datos.get("localidad") or None,
            **{
                campo: datos.get(campo, "")
                for campo in (
                    "calle",
                    "numero_calle",
                    "piso",
                    "departamento_unidad",
                    "barrio",
                    "referencias",
                    "ruta",
                    "kilometro",
                    "lote_rural",
                )
            },
            **{f"{atributo}_id": datos.get(atributo) or None for atributo in NOMBRE_DEL_ROL},
        }
