# Ayudante de las pruebas de UI-06 (D-109 punto 9): cuenta y describe las etiquetas que llevan `data-llevar-vista`, para las pantallas de las apps de nivel mayor.
# Las pruebas de `core` (`test_ui06_llevar_vista.py`) prueban las etiquetas; cada app prueba que sus pantallas marquen el elemento correcto.

import re

MARCA = re.compile(r"<[^<>]*\bdata-llevar-vista\b[^<>]*>")


class Marcas:
    """Mixin de `TestCase`: lo que se mira en el HTML es cuántas etiquetas llevan `data-llevar-vista`, cuál es y qué dice."""

    def marcadas(self, respuesta):
        return MARCA.findall(respuesta.content.decode())

    def una_marca(self, respuesta):
        """Exactamente una etiqueta marcada, con `tabindex="-1"` (sin él no recibe el foco); devuelve la etiqueta de apertura."""
        marcadas = self.marcadas(respuesta)
        self.assertEqual(len(marcadas), 1, marcadas)
        self.assertIn('tabindex="-1"', marcadas[0])
        return marcadas[0]

    def sin_marcas(self, respuesta):
        self.assertEqual(self.marcadas(respuesta), [])

    def texto_marcado(self, respuesta):
        """El texto (sin etiquetas) del elemento marcado, hasta el primer `</`: lo que lee quien recibe el foco."""
        html = respuesta.content.decode()
        encontrado = re.search(r"<[^<>]*\bdata-llevar-vista\b[^<>]*>(.*?)</(?:div|h4|h3|section)>", html, re.S)
        self.assertIsNotNone(encontrado)
        return re.sub(r"<[^>]*>", "", encontrado.group(1)).strip()
