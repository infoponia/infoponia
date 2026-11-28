# Ayudante de las pruebas de UI-06, paso 3 (D-109 punto 9, UX-27): «enviar vacío marca todos los obligatorios independientes, cada uno con el texto de hoy».
# El texto de hoy es el del servicio: no se copia en la prueba. Se obtiene enviando el formulario con UN solo campo vacío (la pantalla muestra lo que rechaza el servicio) y se exige que ese
# mismo texto aparezca cuando faltan todos a la vez. Si alguien cambia el texto del servicio o el de la vista, la prueba avisa. Además comprueba: que un campo de solo espacios cuenta como vacío
# (el criterio de los servicios) y que, con todo vacío, la pantalla lleva la vista a UN solo error, el primero en orden de pantalla (`data-llevar-vista`, paso 2).

import html
import re

from core.tests.marcas_ui06 import Marcas

CLASES_DE_ERROR = ("err", "field-error", "alert alert-danger")


def textos_de_error(respuesta, clases=CLASES_DE_ERROR):
    """Los textos de error que muestra la pantalla (avisos generales y errores de campo), sin etiquetas y en el orden en que se ven. ``clases`` limita qué `<div class="…">` cuentan
    como error (una pantalla puede traer un aviso rojo informativo que no es un error de lo enviado)."""
    patron = re.compile(r'<div class="(?:' + "|".join(re.escape(c) for c in clases) + r')"[^>]*>(.*?)</div>', re.S)
    textos = []
    for crudo in patron.findall(respuesta.content.decode()):
        texto = html.unescape(re.sub(r"<[^>]*>", "", crudo)).strip()
        if texto:
            textos.append(texto)
    return textos


class ObligatoriosJuntos(Marcas):
    """Mixin de `TestCase`."""

    def comprobar_obligatorios_juntos(self, enviar, campos, clases=CLASES_DE_ERROR, espacios=(), con_marca=True):
        """``enviar(vacios, espacios=frozenset())`` manda el formulario con los campos de ``vacios`` (un `frozenset`) vacíos —los de ``espacios`` con solo espacios, el resto con el texto vacío— y todo lo
        demás válido, y devuelve la respuesta.

        1. Con un solo campo vacío la pantalla muestra un error: el del servicio para ese campo. Los textos de los campos son distintos entre sí.
        2. Con todos vacíos, la pantalla muestra el texto de cada uno (y no solo el del primero que rechaza el servicio).
        3. Lo mismo con los campos de ``espacios`` escritos con solo espacios: el servicio los trata como vacíos.
        4. Con todos vacíos hay exactamente un `data-llevar-vista`, en el primer error en orden de pantalla (``con_marca=False`` para una ventana, donde `abrirVentana` maneja el foco: ninguno)."""
        propios = {}
        for campo in campos:
            textos = textos_de_error(enviar(frozenset({campo})), clases)
            self.assertTrue(textos, f"con «{campo}» vacío la pantalla debería mostrar un error")
            propios[campo] = textos[0]
        self.assertEqual(len(set(propios.values())), len(campos), f"cada campo tiene su texto: {propios}")
        respuesta = enviar(frozenset(campos))
        juntos = textos_de_error(respuesta, clases)
        for campo, texto in propios.items():
            self.assertIn(texto, juntos, f"con todos vacíos falta el error de «{campo}»: {juntos}")
        if espacios:
            con_espacios = textos_de_error(enviar(frozenset(campos), espacios=frozenset(espacios)), clases)
            for campo in espacios:
                self.assertIn(propios[campo], con_espacios, f"«{campo}» escrito con solo espacios debe contar como vacío: {con_espacios}")
        if con_marca:
            self.una_marca(respuesta)
            self.assertEqual(self.texto_marcado(respuesta), juntos[0], "la marca va en el primer error en orden de pantalla")
        else:
            self.sin_marcas(respuesta)

    def sin_errores(self, respuesta, clases=CLASES_DE_ERROR):
        """Un redibujo (selector, «Actualizar», abrir la ventana) con los campos vacíos no valida: ningún error y ninguna marca (regla de INV-02)."""
        self.assertEqual(textos_de_error(respuesta, clases), [])
        self.sin_marcas(respuesta)
