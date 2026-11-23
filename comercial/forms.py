# Formularios de `comercial` (COM-01): el cliente, cada dirección del cliente y el vehículo. Como en `maestros`, el formulario solo
# normaliza lo que se escribe y arma las listas (D-24); las reglas las aplican los servicios (comercial/servicios/) y la vista les
# pasa sus errores. Nunca validan al tipear (docs: .claude/rules/interfaz.md): ni siquiera cuando HTMX redibuja un selector.

from django import forms
from django.urls import reverse_lazy

from comercial.models import Cliente, Vehiculo
from maestros.servicios import direcciones, geografia
from maestros.validadores import formatear_cuit

SELECCIONAR = [("", "Seleccionar…")]
CAMPOS_DE_URBANA = ("calle", "numero_calle", "piso", "departamento_unidad", "barrio", "referencias")
CAMPOS_DE_RURAL = ("ruta", "kilometro", "lote_rural")


def _texto(etiqueta, largo, **extra):
    """Campo de texto opcional a nivel de formulario (las reglas son del servicio) con su largo máximo."""
    return forms.CharField(
        label=etiqueta,
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "maxlength": largo, "autocomplete": "off", **extra}),
    )


def _lista(etiqueta, **extra):
    """Campo de lista desplegable propio (D-24); las opciones las arma el formulario al construirse. Sin JavaScript queda el
    ``<select>`` nativo como respaldo."""
    return forms.CharField(
        label=etiqueta, required=False, widget=forms.Select(attrs={"class": "field-input", "data-desplegable": "", **extra})
    )


# ---- cliente ----


class FormularioCliente(forms.Form):
    """Los datos del cliente (COM-ALT-CLT, COM-MOD-CLT; ``VIEWS.cliform`` del prototipo). El tipo se elige con dos fichas de
    radio: con CSS (``:has``) se muestran la razón social o el nombre y el apellido, sin JavaScript y sin pedir nada al servidor; los
    datos del tipo que no se eligió se descartan al guardar (regla 3)."""

    tipo_cliente = forms.ChoiceField(
        label="Tipo de cliente", required=False, choices=Cliente.Tipo.choices, widget=forms.RadioSelect
    )
    cuit = _texto("CUIT", 20, placeholder="30-12345678-9")
    razon_social = _texto("Razón social", 150)
    nombre = _texto("Nombre", 80)
    apellido = _texto("Apellido", 80)
    email = _texto("Correo electrónico", 254, type="email")
    telefono = _texto("Teléfono", 25)

    def __init__(self, *args, cliente=None, **kwargs):
        if cliente is not None and not args and "data" not in kwargs:
            kwargs.setdefault(
                "initial",
                {
                    "tipo_cliente": cliente.tipo_cliente,
                    "cuit": formatear_cuit(cliente.cuit_cliente),
                    "razon_social": cliente.razon_social_cliente,
                    "nombre": cliente.nombre_cliente,
                    "apellido": cliente.apellido_cliente,
                    "email": cliente.email_cliente,
                    "telefono": cliente.telefono_cliente,
                },
            )
        elif cliente is None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", {"tipo_cliente": Cliente.Tipo.JURIDICA})
        super().__init__(*args, **kwargs)
        self.cliente = cliente

    @property
    def es_fisica(self):
        """True si se eligió persona física (si no, jurídica, que es la que arranca elegida)."""
        return self["tipo_cliente"].value() == Cliente.Tipo.FISICA


class FormularioDireccion(forms.Form):
    """Una dirección de un cliente (regla 6 de COM-ALT-CLT; docs/api/direcciones.md). Se usa con un ``prefix``
    (``nueva-<i>`` o ``corregida-<id>``): los nombres de los campos son los que arma ``DatosDeCliente.desde_post``. ``provincia`` y
    ``departamento`` no se guardan: encadenan las listas hasta la ``localidad`` (Georef, MD-88). Con HTMX, al cambiar una lista se
    pide el fragmento de la siguiente (``comercial:direccion_*``, solo GET y sin validar nada); sin JavaScript, el botón
    «Actualizar» reenvía el formulario sin guardar."""

    tipo_direccion = forms.ChoiceField(
        label="Tipo de dirección",
        required=False,
        choices=[("urbana", "Urbana"), ("rural", "Rural")],
        widget=forms.RadioSelect,
    )
    provincia = _lista("Provincia")
    departamento = _lista("Departamento")
    localidad = _lista("Localidad")
    calle = _texto("Calle", 100)
    numero_calle = _texto("Número", 10)
    piso = _texto("Piso", 10)
    departamento_unidad = _texto("Departamento (unidad)", 10)
    barrio = _texto("Barrio", 80)
    referencias = _texto("Referencias", 200)
    ruta = _texto("Ruta o camino", 100)
    kilometro = _texto("Kilómetro", 10)
    lote_rural = _texto("Lote", 30)

    def __init__(self, *args, hija=None, **kwargs):
        if hija is not None and not args and "data" not in kwargs:
            localidad = hija.localidad
            kwargs.setdefault(
                "initial",
                {
                    "tipo_direccion": hija.ZONA,
                    "provincia": localidad.departamento.provincia_id,
                    "departamento": localidad.departamento_id,
                    "localidad": localidad.pk,
                    **{campo: valor or "" for campo, valor in direcciones.datos_de_la_direccion(hija).items()},
                },
            )
        elif hija is None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", {"tipo_direccion": "urbana"})
        super().__init__(*args, **kwargs)
        self.hija = hija

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
        # HTMX: al cambiar el tipo, la provincia o el departamento se pide el fragmento de lo que depende. ``show:none`` no mueve el
        # scroll ni le roba el foco al campo (interfaz.md); no se valida nada. Cada bloque lleva su prefijo en ``hx-vals``.
        prefijo = self.prefix or ""
        pedido = {"hx-include": "closest [data-direccion]", "hx-trigger": "change", "hx-swap": "innerHTML show:none"}
        self.fields["tipo_direccion"].widget.attrs.update(
            {"hx-get": reverse_lazy("comercial:direccion_campos"), "hx-target": f"#dir-{prefijo}-campos", "hx-vals": f'{{"prefijo": "{prefijo}"}}', **pedido}
        )
        self.fields["provincia"].widget.attrs.update(
            {"hx-get": reverse_lazy("comercial:direccion_departamentos"), "hx-target": f"#dir-{prefijo}-departamento-y-localidad", "hx-vals": f'{{"prefijo": "{prefijo}"}}', **pedido}
        )
        self.fields["departamento"].widget.attrs.update(
            {"hx-get": reverse_lazy("comercial:direccion_localidades"), "hx-target": f"#dir-{prefijo}-localidad", "hx-vals": f'{{"prefijo": "{prefijo}"}}', **pedido}
        )

    @property
    def es_urbana(self):
        """True si se eligió una dirección urbana."""
        return self["tipo_direccion"].value() == "urbana"

    @property
    def es_rural(self):
        """True si se eligió una dirección rural."""
        return self["tipo_direccion"].value() == "rural"

    @property
    def id_base(self):
        """El prefijo para armar los ids de los bloques que HTMX reemplaza."""
        return self.prefix or ""

    def esta_vacia(self):
        """True si no se escribió ni se eligió nada de la dirección (un bloque de «Agregar dirección» que quedó sin usar se ignora)."""
        datos = self.data if self.is_bound else {}
        campos = (*CAMPOS_DE_URBANA, *CAMPOS_DE_RURAL, "localidad")
        return not any(str(datos.get(self.add_prefix(campo), "")).strip() for campo in campos)


# ---- vehículo ----


class FormularioVehiculo(forms.Form):
    """Alta y modificación de un vehículo (COM-ALT-VEH, COM-MOD-VEH; ``VIEWS.vehform`` del prototipo, líneas 1136 y 1807). La marca y el
    modelo son dos campos (manda el CU, MD-129). El transportista sale de ``transportistas_disponibles``: activos y libres, cada uno con
    su invernadero (o «sin invernadero»)."""

    patente = _texto("Patente", 12, placeholder="AE123CD o ABC123")
    tipo_vehiculo = _lista("Tipo")
    marca = _texto("Marca", 50)
    modelo = _texto("Modelo", 50)
    capacidad_carga = forms.CharField(
        label="Capacidad de carga (kg)",
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input num", "inputmode": "decimal", "autocomplete": "off"}),
    )
    transportista_id = _lista("Transportista")

    def __init__(self, *args, vehiculo=None, opciones=(), **kwargs):
        if vehiculo is not None and not args and "data" not in kwargs:
            kwargs.setdefault(
                "initial",
                {
                    "patente": vehiculo.patente,
                    "tipo_vehiculo": vehiculo.tipo_vehiculo,
                    "marca": vehiculo.marca,
                    "modelo": vehiculo.modelo,
                    "capacidad_carga": f"{vehiculo.capacidad_carga:.2f}".replace(".", ",").removesuffix(",00"),
                    "transportista_id": vehiculo.transportista_id or "",
                },
            )
        super().__init__(*args, **kwargs)
        self.vehiculo = vehiculo
        self.fields["tipo_vehiculo"].widget.choices = SELECCIONAR + list(Vehiculo.Tipo.choices)
        self.opciones = list(opciones)
        self.fields["transportista_id"].widget.choices = [("", "Sin transportista")] + [
            (
                o.transportista.pk,
                f"{o.transportista.get_full_name() or o.transportista.email} · "
                f"{o.invernadero.nombre_invernadero if o.invernadero else 'sin invernadero'}",
            )
            for o in self.opciones
        ]

    @property
    def transportista_sin_invernadero(self):
        """True si el transportista elegido no pertenece a ningún invernadero: el vehículo se puede asignar, pero no recibe entregas
        hasta que se lo agregue a uno (aviso del formulario, «Cómo se aplica»)."""
        elegido = str(self["transportista_id"].value() or "")
        return any(str(o.transportista.pk) == elegido and o.invernadero is None for o in self.opciones)
