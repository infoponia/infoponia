# Funciones puras para generar un token secreto y su resumen (D-65, punto 2; D-70, punto 3; docs/patrones/enlace_del_cliente.md,
# «1. Piezas»). Sin modelos: las usan el token del nodo central del IoT (`iot`, IOT-02) y el enlace del cliente (`comercial`, COM-04).
# La base guarda SOLO el resumen (SHA-256 en hexadecimal, 64 caracteres), como una contraseña: una copia de la base no sirve para
# entrar. El token vive solo en memoria, el tiempo justo para mostrarlo una vez. Nunca va a la base, a la auditoría ni a un registro de errores.

import hashlib
import secrets


def nuevo_token():
    """Genera un token con una fuente criptográficamente segura (``secrets.token_urlsafe(32)``: 256 bits, 43 caracteres aptos para una
    URL o un encabezado) y devuelve ``(token, resumen)``. El llamador muestra el token una sola vez y guarda solo el resumen."""
    token = secrets.token_urlsafe(32)
    return token, resumen_de(token)


def resumen_de(token):
    """El SHA-256 en hexadecimal (64 caracteres) de ``token``. Se busca por el resumen: comparar resúmenes, y no tokens, hace innecesaria
    una comparación en tiempo constante (D-65, punto 4)."""
    return hashlib.sha256(token.encode()).hexdigest()
