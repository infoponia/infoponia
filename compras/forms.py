# Formularios de compras: el alta, la modificación y la reactivación de un proveedor (CMP-ALT-PRV, CMP-MOD-PRV; ``VIEWS.c_prvform`` del prototipo).
# Como en maestros, el formulario solo normaliza lo que se escribe y arma las listas; todas las reglas las aplica el servicio
# (compras/servicios/proveedores.py) y la vista le pasa sus errores. Ningún campo se valida acá (por eso todos son de texto y opcionales).

from django import forms

from compras.models import Proveedor
from inventario.models import TipoInsumo


def _texto(etiqueta, largo, **extra):
    """Campo de texto opcional a nivel de formulario (las reglas son del servicio) con su largo máximo."""
    return forms.CharField(
        label=etiqueta,
        required=False,
        widget=forms.TextInput(attrs={"class": "field-input", "maxlength": largo, "autocomplete": "off", **extra}),
    )


class FormularioProveedor(forms.Form):
    """Alta (sin ``proveedor``), modificación o reactivación (con ``proveedor``) de un proveedor.

    Con ``proveedor``, el formulario sin datos arranca con los suyos; el tipo y, al reactivar, el CUIT no se cambian (el servicio los ignora).
    ``especialidades`` no es un campo de Django: son casillas que se dibujan a mano (``opciones_de_categorias``) y se leen de ``data``;
    existe solo para que el servicio pueda marcarle un error."""

    tipo = forms.CharField(required=False)
    cuit = _texto("CUIT", 13, placeholder="30-12345678-9", inputmode="numeric")
    razon_social = _texto("Razón social", 150)
    nombre = _texto("Nombre", 80)
    apellido = _texto("Apellido", 80)
    email = forms.CharField(
        label="Correo electrónico",
        required=False,
        widget=forms.EmailInput(attrs={"class": "field-input", "maxlength": 254, "placeholder": "ventas@empresa.com.ar"}),
    )
    telefono = _texto("Teléfono", 25, placeholder="342 456-7788", inputmode="tel")
    especialidades = forms.Field(required=False)

    def __init__(self, *args, proveedor=None, **kwargs):
        if proveedor is not None and not args and "data" not in kwargs:
            kwargs.setdefault(
                "initial",
                {
                    "tipo": proveedor.tipo_proveedor,
                    "cuit": proveedor.cuit_formateado,
                    "razon_social": proveedor.razon_social_proveedor,
                    "nombre": proveedor.nombre_proveedor,
                    "apellido": proveedor.apellido_proveedor,
                    "email": proveedor.email_proveedor,
                    "telefono": proveedor.telefono_proveedor,
                },
            )
        super().__init__(*args, **kwargs)
        self.proveedor = proveedor

    @property
    def tipo_elegido(self):
        """El tipo con que se dibuja el formulario: el del proveedor, o el elegido (jurídica por defecto en el alta)."""
        if self.proveedor is not None:
            return self.proveedor.tipo_proveedor
        elegido = self.data.get("tipo") if self.is_bound else self.initial.get("tipo")
        return elegido if elegido in Proveedor.Tipo.values else Proveedor.Tipo.JURIDICA

    def opciones_de_categorias(self):
        """Las categorías activas que se pueden elegir (regla 3 de CMP-ALT-PRV), cada una como ``{id, nombre, marcada}``. Marcadas: las
        que se enviaron o, sin datos, las activas del proveedor. Las dadas de baja no se ofrecen: su vínculo se conserva (regla 4 de MOD)."""
        if self.is_bound:
            marcadas = set(self.data.getlist("especialidades"))
        elif self.proveedor is not None:
            marcadas = {str(c.pk) for c in self.proveedor.especialidades.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO)}
        else:
            marcadas = set()
        activas = TipoInsumo.objects.filter(estado_tipo_insumo=TipoInsumo.Estado.ACTIVO).order_by("nombre_tipo_insumo")
        return [{"id": c.pk, "nombre": c.nombre_tipo_insumo, "marcada": str(c.pk) in marcadas} for c in activas]

    def datos_del_servicio(self):
        """El ``datos`` de ``alta_proveedor``, ``modificar_proveedor`` y ``reactivar_proveedor`` a partir de lo enviado (sin validar nada)."""
        leer = self.data.get
        return {
            "tipo": leer("tipo", ""),
            "cuit": leer("cuit", ""),
            "razon_social": leer("razon_social", ""),
            "nombre": leer("nombre", ""),
            "apellido": leer("apellido", ""),
            "email": leer("email", ""),
            "telefono": leer("telefono", ""),
            "especialidades": self.data.getlist("especialidades"),
        }
