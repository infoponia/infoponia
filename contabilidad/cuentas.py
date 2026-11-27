# El plan de cuentas en el código (D-84 punto 7, `docs/modelo/contabilidad.md`): una constante por cuenta, los rubros y subrubros del árbol y la
# descripción de cada cuenta. NADIE escribe un código de cuenta suelto (docs/api/asientos.md): se usa la constante.
# Las 19 cuentas las carga la migración `0005_plan_de_cuentas` (con los valores escritos en ella, no importados de acá: una migración
# no depende de código que cambia); una prueba compara las dos fuentes para que no se separen.
# La descripción NO es una columna (regla 3 de CON-CNS-PCT): así reabrir un caso de uso (CON-04a a CON-04d) no necesita una migración.
from contabilidad.constantes import DEBE, HABER  # noqa: F401 - se reexportan: la tarea CON-02 los nombra acá y la API, en `constantes`

# Activo
CAJA = "1.1.01"
BANCO = "1.1.02"
DEUDORES_POR_VENTAS = "1.1.03"
INSUMOS_EN_STOCK = "1.1.04"
PRODUCTOS_EN_PROCESO = "1.1.05"
PRODUCTOS_TERMINADOS = "1.1.06"
# Pasivo
PROVEEDORES = "2.1.01"
INDEMNIZACIONES_A_PAGAR = "2.1.02"
# Patrimonio neto
CAPITAL_INICIAL = "3.1.01"
# Resultado positivo
VENTAS = "4.1.01"
INDEMNIZACIONES_POR_ATRASO = "4.1.02"
OTROS_INGRESOS = "4.1.03"
# Resultado negativo
COSTO_DE_PRODUCCION_VENDIDA = "5.1.01"
PERDIDAS_POR_MERMAS = "5.1.02"
GASTOS_DE_PRODUCCION = "5.1.03"
INDEMNIZACIONES_POR_INCUMPLIMIENTO = "5.1.04"
INDEMNIZACIONES_POR_RESOLUCION = "5.1.05"
DIFERENCIAS_DE_INVENTARIO = "5.1.06"
GASTOS_GENERALES = "5.1.07"

# Los códigos en el orden del plan.
TODAS = (
    CAJA,
    BANCO,
    DEUDORES_POR_VENTAS,
    INSUMOS_EN_STOCK,
    PRODUCTOS_EN_PROCESO,
    PRODUCTOS_TERMINADOS,
    PROVEEDORES,
    INDEMNIZACIONES_A_PAGAR,
    CAPITAL_INICIAL,
    VENTAS,
    INDEMNIZACIONES_POR_ATRASO,
    OTROS_INGRESOS,
    COSTO_DE_PRODUCCION_VENDIDA,
    PERDIDAS_POR_MERMAS,
    GASTOS_DE_PRODUCCION,
    INDEMNIZACIONES_POR_INCUMPLIMIENTO,
    INDEMNIZACIONES_POR_RESOLUCION,
    DIFERENCIAS_DE_INVENTARIO,
    GASTOS_GENERALES,
)

# Rubros y subrubros del árbol (modelo de contabilidad, «Plan de cuentas aprobado»).
RUBROS = {"1": "Activo", "2": "Pasivo", "3": "Patrimonio neto", "4": "Ingresos", "5": "Egresos"}
SUBRUBROS = {
    "1.1": "Activo corriente",
    "2.1": "Pasivo corriente",
    "3.1": "Capital",
    "4.1": "Ingresos operativos",
    "5.1": "Egresos operativos",
}

# Texto de `docs/casos_de_uso/contabilidad/plan_de_cuentas.md` (tabla de «Cómo se aplica»): para qué se usa la cuenta y qué casos de uso la
# mueven. Cada tarea de reapertura (CON-04a a CON-04d) lo completa cuando agrega el asiento de su caso de uso.
DESCRIPCION_DE_CUENTA = {
    CAJA: "Efectivo de la organización. La mueven: pagos a proveedores en efectivo (Haber), cobros en efectivo (Debe) y asientos manuales.",
    BANCO: (
        "Cuenta bancaria. La mueven: pagos por transferencia o tarjeta (Haber), cobros y reintegros (Debe o Haber) y asientos manuales."
    ),
    DEUDORES_POR_VENTAS: (
        "Lo que los clientes le deben a la organización. La mueven: entregas concretadas (Debe), cobros y anulaciones de cobro, "
        "indemnizaciones descontadas."
    ),
    INSUMOS_EN_STOCK: (
        "Valor de los insumos en los invernaderos. La mueven: recepción (Debe), consumos, aplicaciones, ajustes de stock y "
        "corrección de recepción (Haber)."
    ),
    PRODUCTOS_EN_PROCESO: (
        "Valor de las plantas en cultivo. La mueven: siembra, transiciones, aplicaciones sobre lotes y lotes existentes (Debe); "
        "cosechas y mermas (Haber)."
    ),
    PRODUCTOS_TERMINADOS: (
        "Valor de lo cosechado y todavía no entregado. La mueven: cosecha (Debe); entregas, mermas y vencimientos en cámara (Haber)."
    ),
    PROVEEDORES: (
        "Lo que la organización les debe a sus proveedores. La mueven: recepción (Haber); pago y corrección de recepción (Debe)."
    ),
    INDEMNIZACIONES_A_PAGAR: (
        "Multas por resolución de contratos que la organización todavía no pagó. La mueven: resolución del suministro "
        "(Haber, COM-RSV-SUM); su pago, un asiento manual del Contador (Debe)."
    ),
    CAPITAL_INICIAL: (
        "Lo que ya existía al poner en marcha InfoPonia. La mueven el asiento de apertura (CON-INI-EJE), el ajuste «carga inicial» de "
        "insumos y los lotes existentes (Haber)."
    ),
    VENTAS: "Ingresos por entregas. La mueven: entregas concretadas (Haber).",
    INDEMNIZACIONES_POR_ATRASO: (
        "Lo que cobra la organización por atraso de un cliente. La mueve: el pago en mora (COM-VNC-PAG, COM-REG-CBR)."
    ),
    OTROS_INGRESOS: "Ingresos sin cuenta propia. La mueven: asientos manuales.",
    COSTO_DE_PRODUCCION_VENDIDA: "Costo de lo entregado. La mueven: entregas concretadas (Debe).",
    PERDIDAS_POR_MERMAS: "Plantas o producto perdidos. La mueven: mermas en lotes y en cámara, y vencimientos.",
    GASTOS_DE_PRODUCCION: "Insumos aplicados sin lote en pie. La mueve: la aplicación de insumos sin lote (PROD-REG-APL).",
    INDEMNIZACIONES_POR_INCUMPLIMIENTO: (
        "Lo que paga la organización por cantidades o calidad faltantes. La mueven: la evaluación de discrepancias y de quejas "
        "(COM-EVL-DSC, COM-RSV-QJA)."
    ),
    INDEMNIZACIONES_POR_RESOLUCION: "Multa por resolver un suministro. La mueve: COM-RSV-SUM.",
    DIFERENCIAS_DE_INVENTARIO: (
        "Diferencias entre el stock del sistema y el real. La mueven: los ajustes de stock (CMP-AJT-STK). Puede quedar acreedora."
    ),
    GASTOS_GENERALES: "Gastos sin cuenta propia. La mueven: asientos manuales.",
}
