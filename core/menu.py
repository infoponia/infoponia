# Menú lateral según el rol. Muestra solo lo que existe: cada tarea o módulo agrega su entrada
# cuando tiene pantalla (decisión del 08/11/2026, tarea 02). Basado en NAV del prototipo.
# Las entradas de las apps de negocio no se nombran acá: ``core`` es de nivel 1 y no puede importar apps de nivel mayor
# (D-23, D-37 regla A1). Cada app registra su entrada en ``AppConfig.ready()`` con ``registrar_entrada`` (punto de
# extensión, regla A4 de D-37; MAE-01b) y el menú se arma con ``menu_de``.

from core.acceso import ADMINISTRADOR
from core.models import Usuario

Rol = Usuario.Rol

# Entrada: (texto, nombre de la URL, ícono de core/templatetags/iconos.py).
_PANEL = ("Panel de control", "core:inicio", "dash")

_USUARIOS = ("Usuarios y seguridad", "core:usuarios", "users")
# D-16: la misma pantalla de cuentas, con el alcance del Administrador y el nombre del prototipo (NAV).
_CUENTAS = ("Cuentas", "core:usuarios", "users")

# AUD-CNS-REG (D-36): el Gerente y el Administrador consultan la auditoría, cada uno con su alcance.
_AUDITORIA = ("Auditoría", "core:auditoria", "eye")

# Entradas fijas de ``core`` por rol. «Producción» (MAE-01) la registra ``maestros`` (``MaestrosConfig.ready``).
MENU_POR_ROL = {
    Rol.GERENTE: [_PANEL, _USUARIOS, _AUDITORIA],
    Rol.AGRONOMO: [_PANEL],
    Rol.VENDEDOR: [_PANEL],
    # D-85 punto 6: el Contador es de escritorio; entra al «Panel de control» y no tiene «Estadísticas» (H28). «Contabilidad»
    # la registra `contabilidad` en `ready()` (CON-03a, ``registrar_entrada``) y «Compras», `compras` (CMP-03).
    Rol.CONTADOR: [_PANEL],
    # Roles de campo (celular): sin menú lateral.
    Rol.CAPATAZ: [],
    Rol.TECNICO: [],
    Rol.TRANSPORTISTA: [],
    # Tarea 05a: sin «Panel de control»; su inicio es «Cuentas» (prototipo, enter()).
    ADMINISTRADOR: [_CUENTAS, _AUDITORIA],
}

# FIELD del prototipo: usan el marco angosto de celular, sin menú lateral.
ROLES_DE_CAMPO = {Rol.CAPATAZ, Rol.TECNICO, Rol.TRANSPORTISTA}

# SHORT del prototipo: sigla que va en el avatar.
SIGLAS = {
    Rol.GERENTE: "GER",
    Rol.AGRONOMO: "AGR",
    Rol.CAPATAZ: "CAP",
    Rol.VENDEDOR: "VEN",
    Rol.TECNICO: "TEC",
    Rol.TRANSPORTISTA: "TRP",
    Rol.CONTADOR: "CON",  # D-85 punto 6
    ADMINISTRADOR: "ADM",
}


# Punto de extensión (regla A4 de D-37): {rol: [(entrada, texto de la entrada después de la cual va)]}. Lo llenan las apps
# de nivel mayor en ``AppConfig.ready()``; hoy, ``maestros`` con «Producción».
_ENTRADAS_DE_APPS = {}


def registrar_entrada(entrada, roles, despues_de=None):
    """Agrega ``entrada`` (texto, nombre de la URL, ícono) al menú de cada rol de ``roles``, después de la entrada cuyo
    texto es ``despues_de`` (al final si no se indica o no está). Registrar dos veces la misma entrada para un rol no la
    repite. La llaman las apps desde ``AppConfig.ready()``."""
    for rol in roles:
        registradas = _ENTRADAS_DE_APPS.setdefault(rol, [])
        if all(registrada != entrada for registrada, _ in registradas):
            registradas.append((entrada, despues_de))


def menu_de(rol):
    """El menú lateral del ``rol``: sus entradas de ``core`` más las que registraron las apps, cada una en su lugar."""
    menu = list(MENU_POR_ROL.get(rol, []))
    for entrada, despues_de in _ENTRADAS_DE_APPS.get(rol, []):
        textos = [texto for texto, _, _ in menu]
        posicion = textos.index(despues_de) + 1 if despues_de in textos else len(menu)
        menu.insert(posicion, entrada)
    return menu
