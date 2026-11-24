# Reglas de seguridad del despliegue (SEG-16 y USR-09a): cuándo está encendido DEBUG y qué ajustes de HTTPS, cookies y HSTS
# se aplican. Son funciones puras, sin importar Django, para probarlas sin recargar los settings (mismo estilo que
# config/correo.py). config/settings.py las llama una vez al arrancar.

# HSTS de un día (decisión de USR-09a): corto a propósito, para poder volver atrás si algo sale mal. Subirlo a un año
# está en docs/disparadores.md. No se incluyen subdominios ni preload.
HSTS_SEGUNDOS = 86400


def debug_encendido(entorno):
    """True solo si ``DJANGO_DEBUG`` vale exactamente «1» (decisión de USR-09a, punto 2 de USR-09).

    Si la variable falta, está vacía o tiene otro valor, DEBUG queda apagado: un descuido en el servidor no enciende
    el modo de desarrollo (ni, con él, el admin de Django, D-30).
    """
    return entorno.get("DJANGO_DEBUG", "") == "1"


def ajustes_https(debug, corriendo_pruebas):
    """Devuelve los ajustes de HTTPS, cookies seguras y HSTS que ``settings.py`` aplica (SEG-16, USR-09a).

    Con DEBUG encendido (desarrollo, por http) son los valores de Django por defecto. Con DEBUG apagado se redirige a
    https, las cookies de sesión y de CSRF llevan ``Secure`` y se manda HSTS de un día. Con ``manage.py test`` la
    redirección no se aplica, para que las pruebas con el cliente de Django (por http) no reciban un 301; las cookies
    seguras y el HSTS sí, porque no afectan a esas pruebas. No toca la política de Referer (D-88) ni el HttpOnly.
    """
    if debug:
        return {
            "SECURE_SSL_REDIRECT": False,
            "SESSION_COOKIE_SECURE": False,
            "CSRF_COOKIE_SECURE": False,
            "SECURE_HSTS_SECONDS": 0,
        }
    return {
        "SECURE_SSL_REDIRECT": not corriendo_pruebas,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_HSTS_SECONDS": HSTS_SEGUNDOS,
    }
