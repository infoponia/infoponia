# Formularios de contabilidad: los filtros del libro de gestión (CON-03a, CON-CNS-LGS regla 2; docs/patrones/abm.md, sección 1) y, al final, la lectura del asiento manual y del contraasiento (CON-03b). Solo normaliza y valida el formato de lo que se
# escribe: las reglas del libro son de `contabilidad/servicios/libro.py`. Es de consulta (se envía por GET con «Filtrar»), no valida mientras se tipea
# (.claude/rules/interfaz.md). Un campo inválido se marca con su error y se ignora: la pantalla se sigue viendo con los demás filtros.
import datetime
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django import forms
from django.http import QueryDict

from contabilidad.constantes import DEBE, HABER
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



# --- Formulario del asiento manual y del contraasiento (CON-03b) --------------------------------------------------------------------------------------
# Solo lee y normaliza lo que se escribe (docs/patrones/abm.md, sección 1): las reglas y los errores de negocio son de `servicios/asientos.py`. Las filas del asiento
# llegan como `fila` (un valor por fila, su número) y `cuenta_<n>`, `tipo_<n>`, `importe_<n>`; el número identifica la fila aunque se quiten otras.

TEXTO_DE_IMPORTE_INVALIDO = Decimal("NaN")  # el servicio lo rechaza como `importe_invalido`: una cuenta elegida con el importe vacío o mal escrito
FILAS_INICIALES = 2


def importe_desde_texto(texto):
    """El `Decimal` de lo que se escribió en un importe: acepta «1500», «1500,50», «1.500,50» y «1500.50» (con o sin «$»). Vacío es cero; lo que no es
    un número es `Decimal("NaN")` (el servicio lo marca como importe inválido en su fila)."""
    limpio = (texto or "").replace("$", "").replace(" ", "").strip()
    if not limpio:
        return Decimal("0")
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(".") > 1:
        limpio = limpio.replace(".", "")
    try:
        return Decimal(limpio)
    except InvalidOperation:
        return TEXTO_DE_IMPORTE_INVALIDO


def importe_a_texto(importe):
    """Un importe para mostrarlo en el campo: «1000,00» (coma decimal, sin punto de mil)."""
    return f"{importe:.2f}".replace(".", ",")


def etiqueta_de_cuenta(cuenta):
    """Cómo se ve una cuenta en el buscador: «1.1.01 · Caja»."""
    return f"{cuenta.codigo_cuenta} · {cuenta.nombre_cuenta}"


def codigo_de_cuenta(texto, cuentas):
    """El código de la cuenta que la persona eligió o escribió: «1.1.01 · Caja», «1.1.01» o el nombre exacto («caja»). Si no coincide con ninguna se devuelve
    lo escrito, para que el servicio lo rechace como cuenta inexistente en su fila."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    candidato = texto.split("·")[0].strip()
    por_codigo = {c.codigo_cuenta for c in cuentas}
    if candidato in por_codigo:
        return candidato
    por_nombre = [c.codigo_cuenta for c in cuentas if c.nombre_cuenta.lower() == texto.lower()]
    return por_nombre[0] if len(por_nombre) == 1 else texto


@dataclass
class DatosDeAsiento:
    """Lo que se escribió en el formulario del asiento: la fecha (texto y `date` o `None` si no es válida), la descripción y las filas
    `{"i", "cuenta", "tipo", "importe"}` (los tres últimos, tal cual se escribieron)."""

    fecha_texto: str = ""
    fecha: datetime.date = None
    descripcion: str = ""
    filas: list = field(default_factory=list)

    def siguiente_fila(self):
        return max((f["i"] for f in self.filas), default=-1) + 1

    def agregar_fila(self, tipo=DEBE):
        self.filas.append({"i": self.siguiente_fila(), "cuenta": "", "tipo": tipo, "importe": ""})

    def quitar_fila(self, i):
        if len(self.filas) > FILAS_INICIALES:
            self.filas = [f for f in self.filas if f["i"] != i]

    def movimientos(self, cuentas):
        """`[(codigo, "D"|"H", Decimal)]` en el orden de las filas, para el servicio. Una fila vacía queda en cero (el servicio la omite); una con cuenta y sin
        importe queda inválida, para marcarla en vez de ignorarla sin avisar."""
        movimientos = []
        for fila in self.filas:
            codigo = codigo_de_cuenta(fila["cuenta"], cuentas)
            importe = importe_desde_texto(fila["importe"])
            if codigo and not fila["importe"].strip():
                importe = TEXTO_DE_IMPORTE_INVALIDO
            movimientos.append((codigo, fila["tipo"] if fila["tipo"] in (DEBE, HABER) else DEBE, importe))
        return movimientos


def fecha_desde_texto(texto):
    """`date` de «AAAA-MM-DD» (lo que envía `<input type="date">`), o `None` si no es una fecha."""
    try:
        return datetime.date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def leer_asiento(post, hoy):
    """Lee el formulario del asiento. Sin ninguna fila enviada (primera vez) arranca con dos vacías, una al Debe y una al Haber. La fecha por defecto es hoy."""
    datos = DatosDeAsiento(fecha_texto=post.get("fecha", hoy.isoformat()), descripcion=post.get("descripcion", ""))
    datos.fecha = fecha_desde_texto(datos.fecha_texto)
    vistos = []
    for texto in post.getlist("fila"):
        if texto.isdigit() and int(texto) not in vistos:
            vistos.append(int(texto))
    for i in vistos:
        datos.filas.append(
            {"i": i, "cuenta": post.get(f"cuenta_{i}", ""), "tipo": post.get(f"tipo_{i}", DEBE), "importe": post.get(f"importe_{i}", "")}
        )
    while len(datos.filas) < FILAS_INICIALES:
        datos.agregar_fila(DEBE if not datos.filas else HABER)
    return datos


def asiento_vacio(hoy):
    """El formulario de un asiento nuevo: hoy, sin descripción y dos filas vacías (Debe y Haber)."""
    return leer_asiento(QueryDict(), hoy)


def asiento_precargado(hoy, descripcion, movimientos, cuentas):
    """El formulario con una descripción y filas ya cargadas (los atajos y la corrección): ``movimientos`` es `[(codigo, "D"|"H", Decimal | None)]`; un importe `None`
    queda vacío para que lo complete la persona."""
    por_codigo = {c.codigo_cuenta: c for c in cuentas}
    datos = DatosDeAsiento(fecha_texto=hoy.isoformat(), fecha=hoy, descripcion=descripcion)
    for i, (codigo, tipo, importe) in enumerate(movimientos):
        cuenta = por_codigo.get(codigo)
        datos.filas.append(
            {
                "i": i,
                "cuenta": etiqueta_de_cuenta(cuenta) if cuenta else codigo,
                "tipo": tipo,
                "importe": "" if importe is None else importe_a_texto(importe),
            }
        )
    while len(datos.filas) < FILAS_INICIALES:
        datos.agregar_fila()
    return datos


PATRON_DE_LINEA = re.compile(r"^movimientos\[(\d+)\]\.(\w+)$")


def errores_para_pantalla(error, filas=None):
    """Los errores de un `ErrorContable` ordenados para la plantilla: `{"descripcion": [...], "fecha": [...], "general": [...], "filas": {numero_de_fila: {"cuenta": [...],
    "importe": [...], "tipo": [...]}}}`. Los errores de línea traen la posición en la lista que recibió el servicio; ``filas`` (las del formulario, en ese orden)
    la traduce al número de la fila. Los que no son de un campo son generales."""
    salida = {"descripcion": [], "fecha": [], "general": [], "filas": {}}
    for e in error.errores:
        linea = PATRON_DE_LINEA.match(e.campo or "")
        if linea and filas is not None and int(linea.group(1)) < len(filas):
            fila = filas[int(linea.group(1))]["i"]
            salida["filas"].setdefault(fila, {}).setdefault(linea.group(2), []).append(e.mensaje)
        elif e.campo in ("descripcion", "fecha"):
            salida[e.campo].append(e.mensaje)
        else:
            salida["general"].append(e.mensaje)
    return salida
