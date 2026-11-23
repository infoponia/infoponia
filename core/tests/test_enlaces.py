# Pruebas de `core/enlaces.py` (IOT-02, paso 2; D-65 y D-70, punto 3; docs/patrones/enlace_del_cliente.md, «1. Piezas»): funciones puras
# que generan un token y su resumen. Las usan el token del nodo IoT (IOT-02) y el enlace del cliente (COM-04). El resumen es el
# SHA-256 en hexadecimal (64 caracteres); la base guarda solo el resumen y nunca el token.

import hashlib

from django.test import SimpleTestCase

from core import enlaces


class EnlacesTests(SimpleTestCase):
    """``nuevo_token`` y ``resumen_de``."""

    def test_d65_el_resumen_es_el_sha256_en_hexadecimal_de_64_caracteres(self):
        """D-65, punto 2 y D-70, punto 3: «la base guarda el SHA-256» del token (64 caracteres hexadecimales)."""
        token, resumen = enlaces.nuevo_token()
        self.assertRegex(resumen, r"^[0-9a-f]{64}$")
        self.assertEqual(resumen, hashlib.sha256(token.encode()).hexdigest())

    def test_d65_resumen_de_da_el_resumen_que_devolvio_nuevo_token(self):
        """D-65: «Comparar resúmenes (no tokens)»: ``resumen_de(token)`` es el mismo que ``nuevo_token`` devolvió."""
        token, resumen = enlaces.nuevo_token()
        self.assertEqual(enlaces.resumen_de(token), resumen)

    def test_d65_resumen_de_es_determinista_y_distingue_tokens(self):
        """D-65: el mismo token da siempre el mismo resumen; tokens distintos, resúmenes distintos."""
        self.assertEqual(enlaces.resumen_de("abc"), enlaces.resumen_de("abc"))
        self.assertNotEqual(enlaces.resumen_de("abc"), enlaces.resumen_de("abd"))

    def test_d65_dos_tokens_nunca_coinciden(self):
        """D-65, punto 2: ``secrets.token_urlsafe(32)`` (256 bits): no se adivina ni se repite."""
        pares = [enlaces.nuevo_token() for _ in range(200)]
        self.assertEqual(len({token for token, _ in pares}), 200)
        self.assertEqual(len({resumen for _, resumen in pares}), 200)

    def test_d65_el_token_tiene_256_bits_y_es_seguro_para_una_url(self):
        """D-65, punto 2: ``token_urlsafe(32)`` son 43 caracteres del alfabeto de una URL (el nodo lo manda en ``Authorization``)."""
        token, _ = enlaces.nuevo_token()
        self.assertRegex(token, r"^[A-Za-z0-9_-]{43}$")

    def test_d65_el_token_no_se_puede_obtener_del_resumen(self):
        """D-65: «una copia de la base no sirve para entrar»: el resumen no es ni contiene el token."""
        token, resumen = enlaces.nuevo_token()
        self.assertNotIn(token, resumen)
        self.assertNotEqual(token, resumen)
