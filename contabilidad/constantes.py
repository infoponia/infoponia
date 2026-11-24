# Constantes de los movimientos contables (docs/api/asientos.md, «Constantes»): los dos lados de un asiento. Valen lo mismo que
# `MovimientoContable.Tipo` (`"D"` y `"H"`); viven acá, sin importar nada, para que cualquier app los use sin tocar los modelos.
# `contabilidad/cuentas.py` las reexporta (la tarea CON-02 las nombra allí).

DEBE = "D"
HABER = "H"
