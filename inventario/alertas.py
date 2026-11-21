# Los cuatro tipos de alerta de `inventario` (docs/patrones/stock.md, sección 4; contrato en docs/api/alertas.md). Todos son de
# ESTADO (duran mientras dure la condición; a lo sumo una activa por invernadero, tipo y clave) y van al Agrónomo del
# invernadero o, sin Agrónomo activo, al Gerente (D-41: ``AGRONOMO_O_GERENTE``). Las severidades son las del prototipo (el
# modelo no las define). Los códigos llevan el prefijo de la app y tienen a lo sumo 50 caracteres. Las alertas de vencimiento
# las crea solo CMP-REV-VNC (INV-02).

from maestros.alertas import Clase, Destinatario, TipoAlerta, registrar_tipo_de_alerta
from maestros.models import Alerta

STOCK_INCONSISTENTE = "inv_stock_inconsistente"
INSUMO_BAJO_MINIMO = "inv_insumo_bajo_minimo"
INSUMO_POR_VENCER = "inv_insumo_por_vencer"
INSUMO_VENCIDO = "inv_insumo_vencido"


def tipos_de_stock():
    """Las definiciones de los cuatro tipos (se arman acá para poder compararlas en las pruebas)."""
    return [
        TipoAlerta(STOCK_INCONSISTENTE, "Stock inconsistente", Destinatario.AGRONOMO_O_GERENTE, Alerta.Severidad.CRITICA, Clase.ESTADO),
        TipoAlerta(INSUMO_BAJO_MINIMO, "Insumo bajo el mínimo", Destinatario.AGRONOMO_O_GERENTE, Alerta.Severidad.ADVERTENCIA, Clase.ESTADO),
        TipoAlerta(INSUMO_POR_VENCER, "Insumo por vencer", Destinatario.AGRONOMO_O_GERENTE, Alerta.Severidad.ADVERTENCIA, Clase.ESTADO),
        TipoAlerta(INSUMO_VENCIDO, "Insumo vencido", Destinatario.AGRONOMO_O_GERENTE, Alerta.Severidad.CRITICA, Clase.ESTADO),
    ]


def registrar_tipos_de_stock():
    """Registra los cuatro tipos en ``maestros.alertas``; registrar dos veces la misma definición no hace nada."""
    for tipo in tipos_de_stock():
        registrar_tipo_de_alerta(tipo)
