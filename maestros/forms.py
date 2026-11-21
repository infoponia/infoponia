# Formularios de maestros: el alta y la modificación de un invernadero (PROD-ALT-INV y PROD-MOD-INV). Como en core, el formulario solo normaliza lo que
# se escribe y arma las listas; todas las reglas las aplica el servicio (maestros/servicios/invernaderos.py), y la
# vista pasa sus errores al formulario. Provincia, departamento y localidad son listas encadenadas de Georef (regla 3).

import re

from django import forms
from django.urls import reverse_lazy

from maestros.models import PARAMETROS_DE_CONFIGURACION, TipoEtapa
from maestros.servicios import geografia
from maestros.servicios import perfil as perfil_servicio
from maestros.servicios.invernaderos import NOMBRE_DEL_ROL, cuentas_asignables, datos_de_la_direccion

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


def datos_iniciales(invernadero):
    """Lo que el formulario muestra al modificar un invernadero (``INIT['inv-form']`` del prototipo): su nombre, su
    dirección con la provincia y el departamento de su localidad, y su personal."""
    direccion = invernadero.direccion
    hija = direccion.concreta()
    localidad = direccion.localidad
    return {
        "nombre": invernadero.nombre_invernadero,
        "tipo_direccion": hija.ZONA,
        "provincia": localidad.departamento.provincia_id,
        "departamento": localidad.departamento_id,
        "localidad": localidad.pk,
        **{campo: valor or "" for campo, valor in datos_de_la_direccion(hija).items()},
        **{atributo: getattr(invernadero, f"{atributo}_id") or "" for atributo in NOMBRE_DEL_ROL},
    }


class FormularioInvernadero(forms.Form):
    """Alta o modificación de un invernadero (PROD-ALT-INV y PROD-MOD-INV, ``VIEWS['inv-form']`` del prototipo).

    Con ``invernadero`` (modificar), el formulario sin datos arranca con los suyos (``datos_iniciales``) y las listas de
    personal muestran, además de las cuentas activas, a la persona asignada que quedó inactiva, con esa marca (regla 4 de
    PROD-MOD-INV).

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

    def __init__(self, *args, invernadero=None, **kwargs):
        if invernadero is not None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", datos_iniciales(invernadero))
        super().__init__(*args, **kwargs)
        self.invernadero = invernadero

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
            opciones = [(c.pk, c.get_full_name() or c.email) for c in cuentas_asignables(atributo)]
            asignada = getattr(invernadero, atributo) if invernadero is not None else None
            if asignada is not None and not asignada.is_active:
                # Regla 4 de PROD-MOD-INV: la persona asignada que quedó inactiva se muestra con esa marca.
                opciones.append((asignada.pk, f"{asignada.get_full_name() or asignada.email} — inactivo"))
            self.fields[atributo].widget.choices = [("", "Sin asignar")] + opciones

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


# ---- MAE-03: sectores ----


class FormularioSector(forms.Form):
    """Alta o modificación de un sector (PROD-ALT-SCT y PROD-MOD-SCT, ``MODALS['sector-form']`` del prototipo). Solo normaliza
    lo que se escribe y arma las opciones; las reglas las aplica el servicio (``maestros/servicios/sectores.py``) y la vista
    pasa sus errores al formulario. El tipo de etapa se elige con fichas de radio (sin JavaScript funcionan igual) y el
    catálogo sale de ``TipoEtapa`` ya ordenado por ``puesto_global``."""

    nombre = _texto("Nombre", 40, placeholder="Ej. C-3")
    tipo_etapa = forms.CharField(label="Tipo de etapa", required=False, widget=forms.HiddenInput)
    cant_agujeros_total = forms.CharField(
        label="Agujeros totales",
        required=False,
        widget=forms.NumberInput(attrs={"class": "field-input", "min": 1, "inputmode": "numeric", "autocomplete": "off"}),
    )

    def __init__(self, *args, sector=None, **kwargs):
        if sector is not None and not args and "data" not in kwargs:
            kwargs.setdefault(
                "initial",
                {
                    "nombre": sector.nombre_sector,
                    "tipo_etapa": sector.tipo_etapa_id,
                    "cant_agujeros_total": sector.cant_agujeros_total,
                },
            )
        super().__init__(*args, **kwargs)
        self.sector = sector

    @property
    def tipos(self):
        """Los cinco tipos de etapa para las fichas de radio: ``pk``, ``nombre``, ``color`` (sufijo de ``--e-…``) y si es el
        elegido."""
        elegido = str(self["tipo_etapa"].value() or "")
        return [
            {"pk": tipo.pk, "nombre": tipo.nombre_etapa, "color": tipo.clase_de_color, "elegido": str(tipo.pk) == elegido}
            for tipo in TipoEtapa.objects.all()
        ]

    def datos_del_servicio(self):
        """Los argumentos de ``alta_sector`` y de ``modificar_sector`` (sin el actor ni los ids) a partir de lo escrito."""
        datos = self.cleaned_data
        return {
            "nombre": datos.get("nombre", ""),
            "tipo_etapa_id": datos.get("tipo_etapa") or None,
            "cant_agujeros_total": datos.get("cant_agujeros_total", ""),
        }


class FormularioCultivo(forms.Form):
    """Nuevo cultivo o renombrar uno (PROD-ALT-CLT y PROD-MOD-CLT, ``MODALS.cultivo`` del prototipo). Solo normaliza lo que se
    escribe; las reglas (obligatorio, contenido, hasta 40 caracteres, nombre único) las aplica el servicio."""

    nombre = _texto("Nombre del cultivo", 40, placeholder="Ej. Acelga")

    def __init__(self, *args, cultivo=None, **kwargs):
        if cultivo is not None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", {"nombre": cultivo.nombre_cultivo})
        super().__init__(*args, **kwargs)
        self.cultivo = cultivo

    def datos_del_servicio(self):
        """Los argumentos de ``alta_cultivo`` y de ``modificar_cultivo`` (sin el actor ni el id) a partir de lo escrito."""
        return {"nombre": self.cleaned_data.get("nombre", "")}


# ---- MAE-04: pantalla «Configuración» (VIEWS.config y CFG del prototipo) ----

# (grupo, [(campo, unidad, ayuda)]). Los grupos, las unidades y las ayudas salen de ``CFG`` del prototipo; el parámetro de la
# vigencia del enlace de faltante lo agrega MAE-04 al grupo «Comercial» (el caso de uso lo tiene y el prototipo no).
GRUPOS_DE_PARAMETROS = [
    ("Producción", [
        ("porc_merma_maxima", "%", "Al superarla, se alerta al Agrónomo y al Gerente. El descarte por selección no cuenta."),
        ("dias_horizonte_cosecha", "días", ""),
    ]),
    ("Insumos", [
        ("dias_aviso_vencimiento", "días antes",
         "Con esta anticipación se alerta al Agrónomo de cada lote de insumo que está por vencer."),
    ]),
    ("Comercial", [
        ("dias_pre_reserva_suministro", "días", ""),
        ("dias_anticipacion_cosecha_compra_venta", "días", ""),
        ("dias_anticipacion_cosecha_suministro", "días", "No puede superar la pre-reserva de suministros."),
        ("dias_vigencia_enlace_confirmacion", "días", ""),
        ("dias_vigencia_enlace_faltante", "días", ""),
    ]),
    ("Compras", [
        ("dias_limite_cotizacion", "días", ""),
        ("dias_validez_cotizacion", "días", ""),
        ("porc_tolerancia_cobertura_pedido", "%", ""),
    ]),
    ("Entregas", [
        ("cant_maxima_entregas_diarias", "entregas", ""),
        ("cant_max_ciudades_distintas_diarias", "localidades", ""),
    ]),
]


class FormularioConfiguracion(forms.Form):
    """Pestaña «Parámetros operativos» (ADM-MOD-CFG): un campo numérico por parámetro. Solo normaliza lo que se escribe; los
    dominios y las reglas 4 y 5 son del servicio (``maestros/servicios/configuracion.py``), que devuelve los errores por campo."""

    def __init__(self, *args, configuracion=None, **kwargs):
        if configuracion is not None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", {c: getattr(configuracion, c) for c, *_ in PARAMETROS_DE_CONFIGURACION})
        super().__init__(*args, **kwargs)
        etiquetas = {campo: etiqueta for campo, etiqueta, *_ in PARAMETROS_DE_CONFIGURACION}
        for grupo, parametros in GRUPOS_DE_PARAMETROS:
            for campo, unidad, _ in parametros:
                self.fields[campo] = forms.CharField(
                    label=f"{etiquetas[campo]} ({unidad})",
                    required=False,
                    widget=forms.NumberInput(
                        attrs={"class": "field-input num", "inputmode": "numeric", "autocomplete": "off"}
                    ),
                )

    @property
    def grupos(self):
        """``[(título, [(campo, ayuda)])]`` para dibujar una tarjeta por grupo."""
        return [(g, [(self[campo], ayuda) for campo, _, ayuda in ps]) for g, ps in GRUPOS_DE_PARAMETROS]

    def datos_del_servicio(self):
        """Los argumentos de ``modificar_configuracion`` (sin el actor): todos los parámetros, tal como se escribieron."""
        return {campo: self.cleaned_data.get(campo, "") for campo, *_ in PARAMETROS_DE_CONFIGURACION}


class FormularioPerfil(forms.Form):
    """Pestaña «Organización» (ADM-MOD-ORG): los datos y hasta cuatro colores. Sin logo (D-45). Las reglas son del servicio
    (``maestros/servicios/perfil.py``)."""

    nombre_organizacion = _texto("Nombre", 120)
    cuit_organizacion = _texto("CUIT", 20)
    telefono_organizacion = _texto("Teléfono", 25)
    email_organizacion = _texto("Email", 254)
    direccion_organizacion = _texto("Dirección", 200)
    color_primario = _texto("Color 1 (principal)", 7, placeholder="Sin color · Ej. #1A6B3C")
    color_secundario = _texto("Color 2", 7, placeholder="Sin color · Ej. #1A6B3C")
    color_terciario = _texto("Color 3", 7, placeholder="Sin color · Ej. #1A6B3C")
    color_cuaternario = _texto("Color 4", 7, placeholder="Sin color · Ej. #1A6B3C")

    def __init__(self, *args, perfil=None, **kwargs):
        if perfil is not None and not args and "data" not in kwargs:
            kwargs.setdefault("initial", {campo: getattr(perfil, campo) for campo in perfil_servicio.CAMPOS})
        super().__init__(*args, **kwargs)

    @property
    def colores(self):
        """Los cuatro colores como ``(campo, muestra)``: ``muestra`` es el color escrito si es ``#RRGGBB`` válido (el único
        valor que va a un ``style``) y vacío si no."""
        resultado = []
        for nombre in perfil_servicio.CAMPOS_DE_COLOR:
            campo = self[nombre]
            valor = str(campo.value() or "").strip()
            resultado.append((campo, valor if re.fullmatch(r"#[0-9a-fA-F]{6}", valor) else ""))
        return resultado

    def datos_del_servicio(self):
        """Los argumentos de ``modificar_perfil`` (sin el actor): todos los datos, tal como se escribieron."""
        return {campo: self.cleaned_data.get(campo, "") for campo in perfil_servicio.CAMPOS}
