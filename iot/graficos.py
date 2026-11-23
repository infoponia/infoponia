# Gráficos SVG del panel de monitoreo (IOT-04; docs/casos_de_uso/iot/consultar_lecturas.md, «Gráficos»; regla 4 de IOT-CNS-LEC; D-76 punto 8). Se arman en el SERVIDOR, sin
# bibliotecas de gráficos (no hay dependencias nuevas): ``grafico_de_sensor`` es una función pura, como ``spark`` del prototipo (360 × 96, línea de la serie, franja del umbral
# o del rango con sus dos valores a la derecha y un punto en el último valor). Los elementos llevan clases (``grafico-*``) para el CSS y las pruebas.

from django.utils.html import escape
from django.utils.safestring import mark_safe

from iot.textos import numero_legible

ANCHO, ALTO, IZQUIERDA, DERECHA, MARGEN = 360, 96, 6, 46, 8
VACIO = '<div class="spark empty">Sin lecturas en este período</div>'


def grafico_de_sensor(serie, franja, resumido, etiqueta=""):
    """El SVG de un sensor. ``serie``: hasta 24 horas, los valores de las lecturas válidas en orden; 7 y 30 días (``resumido``), ``(mínimo, promedio, máximo)`` por hora.
    ``franja``: ``(mínimo, máximo)`` del umbral efectivo o del rango de la solución, o ``None`` (sin franja). ``etiqueta``: el ``aria-label`` (variable y período), escapado.
    Sin datos devuelve «Sin lecturas en este período». La línea y el punto van en el verde primario, o en el color de peligro si el último valor queda fuera de la franja."""
    if not serie:
        return mark_safe(VACIO)
    promedios = [float(p[1]) for p in serie] if resumido else [float(v) for v in serie]
    valores = [float(x) for p in serie for x in (p[0], p[2])] if resumido else list(promedios)
    if franja is not None:
        valores += [float(franja[0]), float(franja[1])]
    menor, mayor = min(valores), max(valores)
    relleno = (mayor - menor) * 0.14 or 1.0
    menor, mayor = menor - relleno, mayor + relleno
    ancho_util = ANCHO - IZQUIERDA - DERECHA

    def x(i):
        return IZQUIERDA + (i * ancho_util / (len(serie) - 1) if len(serie) > 1 else ancho_util / 2)

    def y(valor):
        return ALTO - MARGEN - (valor - menor) / (mayor - menor) * (ALTO - 2 * MARGEN)

    fuera = franja is not None and (promedios[-1] > float(franja[1]) or promedios[-1] < float(franja[0]))
    color = "var(--status-danger)" if fuera else "var(--primary)"
    partes = [f'<svg class="spark" viewBox="0 0 {ANCHO} {ALTO}" role="img" aria-label="{escape(etiqueta)}">']
    if franja is not None:
        arriba_y, abajo_y = y(float(franja[1])), y(float(franja[0]))
        partes.append(
            f'<rect class="grafico-franja" x="{IZQUIERDA}" y="{arriba_y:.1f}" width="{ancho_util}" height="{max(2.0, abajo_y - arriba_y):.1f}" fill="#cfe7d9"/>'
            f'<line class="grafico-franja" x1="{IZQUIERDA}" x2="{ANCHO - DERECHA}" y1="{arriba_y:.1f}" y2="{arriba_y:.1f}" stroke="#7dbb97" stroke-dasharray="3 3"/>'
            f'<line class="grafico-franja" x1="{IZQUIERDA}" x2="{ANCHO - DERECHA}" y1="{abajo_y:.1f}" y2="{abajo_y:.1f}" stroke="#7dbb97" stroke-dasharray="3 3"/>'
            f'<text class="grafico-franja" x="{ANCHO - DERECHA + 6}" y="{arriba_y + 3.5:.1f}" font-size="10" fill="#3f6a52">{escape(numero_legible(franja[1]))}</text>'
            f'<text class="grafico-franja" x="{ANCHO - DERECHA + 6}" y="{abajo_y + 3.5:.1f}" font-size="10" fill="#3f6a52">{escape(numero_legible(franja[0]))}</text>'
        )
    if resumido:
        de_ida = " ".join(f"{x(i):.1f},{y(float(p[2])):.1f}" for i, p in enumerate(serie))
        de_vuelta = " ".join(f"{x(i):.1f},{y(float(p[0])):.1f}" for i, p in reversed(list(enumerate(serie))))
        partes.append(f'<polygon class="grafico-envolvente" points="{de_ida} {de_vuelta}" fill="#9cc7ae" opacity=".45"/>')
    puntos = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(promedios))
    partes.append(f'<polyline class="grafico-linea" points="{puntos}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>')
    if not resumido:
        partes.append(f'<circle class="grafico-ultimo" cx="{x(len(serie) - 1):.1f}" cy="{y(promedios[-1]):.1f}" r="3.5" fill="{color}"/>')
    partes.append("</svg>")
    return mark_safe("".join(partes))
