# Textos de las alertas del IoT (docs/casos_de_uso/iot/entregar_informacion.md, «Alertas: textos y origen»): los valores se escriben con coma decimal,
# sin ceros de más y con punto de miles (``28,4``, ``32.000``), con la unidad del sensor (``°C``, ``% HR``, ``lux``).

from decimal import Decimal


def numero_legible(valor):
    """``Decimal(\"32000.00\")`` -> ``32.000``; ``Decimal(\"28.40\")`` -> ``28,4``; ``Decimal(\"-10.00\")`` -> ``-10``."""
    texto = format(Decimal(str(valor)).normalize(), "f")
    signo = "-" if texto.startswith("-") else ""
    entero, _, decimales = texto.lstrip("-").partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    return f"{signo}{entero}" + (f",{decimales}" if decimales else "")


def valor_legible(valor, unidad=""):
    """El valor legible con su unidad si la tiene: ``valor_legible(Decimal(\"28.4\"), \"°C\")`` -> ``28,4 °C``."""
    numero = numero_legible(valor)
    return f"{numero} {unidad}" if unidad else numero


def estado_legible(estado):
    """El estado informado de un actuador para mostrarlo: ``encendido`` -> ``Encendido``, ``nivel:60`` -> ``Nivel 60``, ``posicion:-15`` -> ``Posición -15``."""
    if not estado:
        return ""
    if ":" in estado:
        nombre, valor = estado.split(":", 1)
        return f"{ {'nivel': 'Nivel', 'posicion': 'Posición'}.get(nombre, nombre) } {valor}"
    return estado.capitalize()


def lectura_legible(telemetria):
    """La lectura para mostrarla: «24,5 °C» o, en el nivel de la solución, «Normal» o «Bajo»."""
    if telemetria.estado_nivel_medido:
        return telemetria.get_estado_nivel_medido_display()
    return valor_legible(telemetria.valor_medido, telemetria.unidad_medida_telemetria or "")
