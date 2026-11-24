# Consulta del plan de cuentas (CON-CNS-PCT, D-84 punto 7): el árbol por rubro y subrubro y la búsqueda de una cuenta por código. Solo
# lee: no escribe, no bloquea y no audita (SEG-14). Importa solo de `contabilidad` (nivel 2, regla A1 de D-37).
from collections import namedtuple

from contabilidad import cuentas
from contabilidad.models import CuentaContable

# Rubro(codigo="1", nombre="Activo", subrubros=[Subrubro(codigo="1.1", nombre="Activo corriente", cuentas=[CuentaContable, ...])])
Subrubro = namedtuple("Subrubro", "codigo nombre cuentas")
Rubro = namedtuple("Rubro", "codigo nombre subrubros")


def arbol():
    """El plan completo como lista de `Rubro`, ordenado por código (regla 2 de CON-CNS-PCT). Una sola consulta: sin consultas por fila."""
    por_subrubro = {}
    for cuenta in CuentaContable.objects.order_by("codigo_cuenta"):
        por_subrubro.setdefault(cuenta.codigo_cuenta.rsplit(".", 1)[0], []).append(cuenta)
    resultado = []
    for codigo_rubro, nombre_rubro in cuentas.RUBROS.items():
        subrubros = [
            Subrubro(codigo, nombre, por_subrubro.get(codigo, []))
            for codigo, nombre in cuentas.SUBRUBROS.items()
            if codigo.startswith(f"{codigo_rubro}.")
        ]
        resultado.append(Rubro(codigo_rubro, nombre_rubro, subrubros))
    return resultado


def cuenta(codigo):
    """La `CuentaContable` de ese código; lanza `CuentaContable.DoesNotExist` si no existe (usá las constantes de `cuentas.py`)."""
    return CuentaContable.objects.get(codigo_cuenta=codigo)
