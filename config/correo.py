# Reglas de la configuración del correo (D-33, SEG-12): cuándo el envío está configurado y cuándo se usa la consola.
# Son funciones puras que reciben el entorno y DEBUG, sin importar Django, para probarlas sin recargar los settings.
# config/settings.py las llama una vez al arrancar y guarda el resultado en CORREO_CONFIGURADO.


def correo_por_consola(entorno, debug):
    """True si el correo se imprime en la consola en vez de enviarse (solo desarrollo).

    D-33: hace falta ``DEBUG`` encendido y ``CORREO_CONSOLA=1``. Con ``DEBUG`` apagado se ignora: en producción
    imprimiría los enlaces de recuperación en los registros del servidor, y quien los lea podría usarlos.
    """
    return bool(debug) and entorno.get("CORREO_CONSOLA", "") == "1"


def correo_configurado(entorno, debug):
    """True si el envío de correo está configurado (SEG-12, precondición a de USR-RCP-CTR).

    Es la única fuente de verdad: lo está si están definidos ``EMAIL_HOST_USER`` y ``EMAIL_HOST_PASSWORD`` (la
    contraseña de aplicación de Google), o si se usa la consola en desarrollo (``correo_por_consola``).
    """
    if correo_por_consola(entorno, debug):
        return True
    return bool(entorno.get("EMAIL_HOST_USER", "")) and bool(entorno.get("EMAIL_HOST_PASSWORD", ""))
