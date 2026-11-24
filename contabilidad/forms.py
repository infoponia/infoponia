# Formulario de filtros del libro de gestión (CON-03a, CON-CNS-LGS regla 2; docs/patrones/abm.md, sección 1). Solo normaliza y valida el formato de lo que se
# escribe: las reglas del libro son de `contabilidad/servicios/libro.py`. Es de consulta (se envía por GET con «Filtrar»), no valida mientras se tipea
# (.claude/rules/interfaz.md). Un campo inválido se marca con su error y se ignora: la pantalla se sigue viendo con los demás filtros.
from django import forms

from contabilidad.models import OrigenDocumento

VISTAS = (("cronologica", "Cronológica"), ("cuenta", "Por cuenta"))
TIPOS = (("", "Todos los tipos"), ("automatico", "Automáticos"), ("manual", "Manuales"), ("contraasiento", "Contraasientos"))
ANULADOS = (("", "Anulados: todos"), ("si", "Solo anulados"), ("no", "Sin anulados"))


class FormularioDelLibro(forms.Form):
    """Filtros del libro: ejercicio, vista (cronológica o por cuenta), rango de fechas, tipo, origen, cuenta, anulados y texto.

    Recibe las listas que dependen de la base (``ejercicios``: los `EjercicioNumerado`; ``cuentas``: las `CuentaContable`) para armar los desplegables sin
    consultar por su cuenta. `filtros()` devuelve lo que `libro.listar_asientos` espera, solo con los campos válidos.
    """

    ejercicio = forms.ChoiceField(required=False, label="Ejercicio")
    vista = forms.ChoiceField(required=False, choices=VISTAS, label="Vista")
    desde = forms.DateField(required=False, label="Desde", widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, label="Hasta", widget=forms.DateInput(attrs={"type": "date"}))
    tipo = forms.ChoiceField(required=False, choices=TIPOS, label="Tipo")
    origen = forms.ChoiceField(required=False, label="Origen")
    cuenta = forms.ChoiceField(required=False, label="Cuenta")
    anulados = forms.ChoiceField(required=False, choices=ANULADOS, label="Anulados")
    q = forms.CharField(required=False, max_length=100, label="Buscar")

    def __init__(self, *args, ejercicios=(), cuentas=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ejercicio"].choices = [(str(e.ejercicio.pk), f"Ejercicio {e.numero}") for e in ejercicios]
        self.fields["origen"].choices = [("", "Todos los orígenes")] + list(OrigenDocumento.Tipo.choices)
        self.fields["cuenta"].choices = [("", "Todas las cuentas")] + [(c.codigo_cuenta, f"{c.codigo_cuenta} · {c.nombre_cuenta}") for c in cuentas]
        for campo in self.fields.values():  # aspecto del sistema: los desplegables los convierte `infoponia.js` (D-24); sin JavaScript queda el nativo
            campo.widget.attrs.update({"class": "field-input", "aria-label": campo.label})
            if isinstance(campo, forms.ChoiceField):
                campo.widget.attrs["data-desplegable"] = ""
        self.fields["q"].widget = forms.TextInput(
            attrs={"class": "field-input", "aria-label": "Buscar", "type": "search", "placeholder": "Buscar en la descripción, el número o el origen"}
        )

    def clean(self):
        """«Desde» posterior a «hasta» no da ningún asiento: se marca y se ignoran las dos fechas."""
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            self.add_error("hasta", "La fecha «hasta» no puede ser anterior a «desde».")
            datos.pop("desde", None)
            datos.pop("hasta", None)
        return datos

    def vista_elegida(self):
        """`cronologica` (por defecto) o `cuenta`."""
        return self.cleaned_data.get("vista") or "cronologica"

    def filtros(self):
        """Los argumentos de `libro.listar_asientos` (sin actor ni ejercicio) que salen de los campos válidos."""
        datos = self.cleaned_data
        anulados = {"si": True, "no": False}.get(datos.get("anulados"))
        return {
            "desde": datos.get("desde"),
            "hasta": datos.get("hasta"),
            "tipo": datos.get("tipo") or None,
            "origen_tipo": datos.get("origen") or None,
            "cuenta": datos.get("cuenta") or None,
            "anulados": anulados,
            "texto": datos.get("q") or "",
        }

    def hay_filtros(self):
        """True si se aplica algún filtro (para ofrecer «Quitar filtros» y distinguir «no hay asientos» de «no hay con esos filtros»)."""
        datos = self.cleaned_data
        return any(datos.get(clave) for clave in ("desde", "hasta", "tipo", "origen", "cuenta", "anulados", "q"))
