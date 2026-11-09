# Menú lateral según el rol. Muestra solo lo que existe: cada tarea o módulo agrega su entrada
# cuando tiene pantalla (decisión del 08/11/2026, tarea 02). Basado en NAV del prototipo.

from core.acceso import ADMINISTRADOR
from core.models import Usuario

Rol = Usuario.Rol

# Entrada: (texto, nombre de la URL, ícono de core/templatetags/iconos.py).
_PANEL = ("Panel de control", "core:inicio", "dash")

MENU_POR_ROL = {
    Rol.GERENTE: [_PANEL],
    Rol.AGRONOMO: [_PANEL],
    Rol.VENDEDOR: [_PANEL],
    # Roles de campo (celular): sin menú lateral.
    Rol.CAPATAZ: [],
    Rol.TECNICO: [],
    Rol.TRANSPORTISTA: [],
    # El Administrador sumará «Cuentas» en la tarea 05.
    ADMINISTRADOR: [],
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
    ADMINISTRADOR: "ADM",
}
