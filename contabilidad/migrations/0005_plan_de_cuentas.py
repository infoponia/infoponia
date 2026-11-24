# Datos: las 19 cuentas del plan de cuentas (CON-02, D-84 punto 7, MD-118; `docs/modelo/contabilidad.md`): las 18 de H5/H6/H7 más 2.1.02
# «Indemnizaciones a Pagar» (MD-123). Idempotente (`update_or_create` por código); la inversa no hace nada. Los valores van escritos acá,
# no importados de `contabilidad/cuentas.py`: una migración no depende de código que cambia (`docs/patrones/datos_de_migracion.md`).
# Expone `cargar` y `descargar` para que las pruebas recarguen el plan si un `TransactionTestCase` lo vació.
from django.db import migrations

# (código, nombre, tipo)
CUENTAS = [
    ("1.1.01", "Caja", "activo"),
    ("1.1.02", "Banco c/c", "activo"),
    ("1.1.03", "Deudores por Ventas", "activo"),
    ("1.1.04", "Insumos en Stock", "activo"),
    ("1.1.05", "Productos en Proceso", "activo"),
    ("1.1.06", "Productos Terminados", "activo"),
    ("2.1.01", "Proveedores", "pasivo"),
    ("2.1.02", "Indemnizaciones a Pagar", "pasivo"),
    ("3.1.01", "Capital Inicial", "patrimonio_neto"),
    ("4.1.01", "Ventas", "resultado_positivo"),
    ("4.1.02", "Indemnizaciones por Atraso en el Pago", "resultado_positivo"),
    ("4.1.03", "Otros Ingresos", "resultado_positivo"),
    ("5.1.01", "Costo de Producción Vendida", "resultado_negativo"),
    ("5.1.02", "Pérdidas por Mermas", "resultado_negativo"),
    ("5.1.03", "Gastos de Producción", "resultado_negativo"),
    ("5.1.04", "Indemnizaciones por Incumplimiento a Cliente", "resultado_negativo"),
    ("5.1.05", "Indemnizaciones por Resolución de Contratos", "resultado_negativo"),
    ("5.1.06", "Diferencias de Inventario de Insumos", "resultado_negativo"),
    ("5.1.07", "Gastos Generales", "resultado_negativo"),
]


def cargar(apps, schema_editor):
    """Carga las 19 cuentas; si una ya existe (por código), le pone el nombre y el tipo del plan aprobado."""
    CuentaContable = apps.get_model("contabilidad", "CuentaContable")
    for codigo, nombre, tipo in CUENTAS:
        CuentaContable.objects.update_or_create(
            codigo_cuenta=codigo, defaults={"nombre_cuenta": nombre, "tipo_cuenta": tipo}
        )


def descargar(apps, schema_editor):
    """La inversa no hace nada (D-84 punto 7): las cuentas pueden tener movimientos y la tabla se elimina con la migración de esquema."""


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidad", "0004_nucleo_contable"),
    ]

    operations = [
        migrations.RunPython(cargar, descargar),
    ]
