# COM-CNS-EST · Consultar Estadísticas Comerciales (COM-08c; docs/casos_de_uso/comercial/estadisticas.md; D-94, puntos 1 y 15).
# SOLO LECTURA: ninguna función de este módulo escribe ni audita (postcondición a). `filtros_de_estadisticas` valida y normaliza lo que llega de la URL; `estadisticas` calcula los ocho
# indicadores de un período; `resultados_del_mes` es lo que muestra el panel del Vendedor. EST-03 (app `estadisticas`, nivel 8) llama a las dos primeras con un período cualquiera.
#
# ESQUELETO DEL PASO DE PRUEBAS EN ROJO: las firmas y los tipos que fijan las pruebas de `comercial/tests/test_com_cns_est.py`; el cuerpo de cada función se escribe después de que el estudiante revise las pruebas.

from collections import namedtuple
from dataclasses import dataclass
from datetime import date

# ---- Tipos que devuelven las funciones (las pruebas leen estos campos) ----

# Lo que se ofrece en los desplegables de la pantalla: meses (valor «AAAA-MM», texto), invernaderos y Vendedores (id, texto). Vacíos si el `FiltrosDeEstadisticas` no viene de `filtros_de_estadisticas`.
VentaDeVariedad = namedtuple("VentaDeVariedad", "variedad plantas monto")
Ventas = namedtuple("Ventas", "total entregas plantas variedades")
Puntualidad = namedtuple("Puntualidad", "total a_tiempo con_retraso porcentaje_a_tiempo porcentaje_con_retraso promedio_de_retraso intentos_fallidos")
Incumplimientos = namedtuple("Incumplimientos", "cantidad quejas discrepancias descuentos pagos_en_dinero total")
Cobranza = namedtuple("Cobranza", "pendiente_total pendiente_cantidad en_mora_total en_mora_cantidad hasta_30 de_31_a_60 mas_de_60")
Faltantes = namedtuple("Faltantes", "con_faltante rechazados_por_cantidad rechazados_al_recibir cancelados")
ClienteConMasCompras = namedtuple("ClienteConMasCompras", "cliente_id nombre entregas monto porcentaje url_compra_ventas url_suministros")
Enlaces = namedtuple("Enlaces", "compra_ventas suministros entregas solicitudes cobranza faltantes")
Estadisticas = namedtuple("Estadisticas", "filtros ventas puntualidad incumplimientos cobranza faltantes clientes enlaces")
ResultadosDelMes = namedtuple("ResultadosDelMes", "desde hasta ventas puntualidad incumplimientos")


@dataclass(frozen=True)
class FiltrosDeEstadisticas:
    """Los filtros normalizados (reglas 1, 2 y 11): el período (`desde` y `hasta`, inclusivos), `periodo` («AAAA-MM» o «rango»), el invernadero y, solo para el Gerente, el Vendedor, más las opciones
    de los desplegables. EST-03 puede armar uno con solo `desde` y `hasta`."""

    desde: date
    hasta: date
    periodo: str = ""
    invernadero_id: int | None = None
    vendedor_id: int | None = None
    meses: tuple = ()
    invernaderos: tuple = ()
    vendedores: tuple = ()


def filtros_de_estadisticas(actor, get, hoy):
    """Reglas 1, 2 y 11: valida y normaliza el período, el invernadero y el Vendedor. `PermissionDenied` (`sin_permiso`) si no es un Vendedor o un Gerente activo; `ValidationError` con
    `periodo_invalido`, `invernadero_fuera_de_alcance` o `vendedor_no_admitido`. Lectura pura."""
    raise NotImplementedError


def estadisticas(actor, filtros, hoy):
    """Reglas 3 a 8 y 10: los ocho indicadores del período de `filtros`, con los enlaces de cada uno. Acepta cualquier `desde`/`hasta`; vuelve a verificar el alcance (rol, invernadero, Vendedor).
    Lectura pura: ninguna escritura, ninguna auditoría (postcondición a)."""
    raise NotImplementedError


def resultados_del_mes(actor, hoy):
    """Reglas 3, 4 y 5 del mes en curso (del 1 a `hoy`) para el panel del Vendedor: ventas, entregas a tiempo e indemnizado, con las mismas funciones internas que `estadisticas`."""
    raise NotImplementedError


# ---- Un indicador por función (`(actor, filtros)`; la cobranza, además, `hoy`) ----


def _ventas(actor, filtros):
    """Indicador 3: ventas por variedad."""
    raise NotImplementedError


def _puntualidad(actor, filtros):
    """Indicador 4: entregas a tiempo y con retraso, y los intentos fallidos del período."""
    raise NotImplementedError


def _incumplimientos(actor, filtros):
    """Indicador 5: incumplimientos aceptados e indemnizado."""
    raise NotImplementedError


def _cobranza(actor, filtros, hoy):
    """Indicador 6: cobranza pendiente y en mora, a la fecha `hoy` (no por período)."""
    raise NotImplementedError


def _faltantes(actor, filtros):
    """Indicador 7: faltantes y rechazos de compra-venta."""
    raise NotImplementedError


def _clientes(actor, filtros):
    """Indicador 8: los diez clientes con más compras."""
    raise NotImplementedError
