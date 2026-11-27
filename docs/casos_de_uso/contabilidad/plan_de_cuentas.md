# Casos de uso · contabilidad · Plan de cuentas

Copia para el repo de CON-CNS-PCT, de los archivos fuente de la ronda de Contabilidad (CON-alto-nivel.md). Cotejado con `decisiones_A0.md` y
`pendientes_para_pegar.md` (**esas decisiones ganan** si algo difiere, regla de Ezequiel del 23/11/2026).

**El código va en la app `contabilidad`** (D-37, nivel 2); archivos de pruebas bajo `contabilidad/tests/`. Si este archivo y el
documento de Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>` y `test_post_<letra>_<que_espera>`.

---

## **Caso de uso CON-CNS-PCT: Consultar Plan de Cuentas**

Caso de uso nuevo (no existía en ninguna fuente; contexto, sección 3.2). D-37: el plan se carga por migración, así que no hay ABM; sí hace falta una consulta. Mejora futura: ABM de cuentas (H5/H6/H7).

**Actores:** Contador o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver qué cuentas existen, de qué tipo son y cómo se usan, para elegir la correcta al registrar un asiento.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Contador o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta.

**Reglas:**

1.  Alcance: el Contador y el Gerente ven el plan completo. El Vendedor no.
2.  Se muestra en forma de árbol por rubro y subrubro, con el código (rubro.subrubro.cuenta), el nombre y el tipo (Activo, Pasivo, Patrimonio neto, Resultado positivo, Resultado negativo). Plan aprobado en H5/H6/H7:
    - 1.1.01 Caja · 1.1.02 Banco c/c · 1.1.03 Deudores por Ventas · 1.1.04 Insumos en Stock · 1.1.05 Productos en Proceso · 1.1.06 Productos Terminados (Activo);
    - 2.1.01 Proveedores · 2.1.02 Indemnizaciones a Pagar (Pasivo; la 2.1.02 la sumó Ezequiel el 23/11/2026 para la multa de MD-123);
    - 3.1.01 Capital Inicial (Patrimonio neto);
    - 4.1.01 Ventas · 4.1.02 Indemnizaciones por Atraso en el Pago · 4.1.03 Otros Ingresos (Resultado positivo);
    - 5.1.01 Costo de Producción Vendida · 5.1.02 Pérdidas por Mermas · 5.1.03 Gastos de Producción · 5.1.04 Indemnizaciones por Incumplimiento a Cliente · 5.1.05 Indemnizaciones por Resolución de Contratos · 5.1.06 Diferencias de Inventario de Insumos · 5.1.07 Gastos Generales (Resultado negativo).
3.  Para cada cuenta se ve una descripción de para qué se usa y qué casos de uso la mueven. [texto a redactar con la lista de asientos automáticos, en las rondas de reapertura]
4.  Desde cada cuenta se puede ir al libro de gestión, vista por cuenta (CON-CNS-LGS).
5.  Sin IVA (simplificación declarada).
6.  La consulta no se audita (SEG-14).

---

## Cómo se aplica (código)

Decisión **D-84** (punto 7). Modelo: `docs/modelo/contabilidad.md` (`CuentaContable` y el plan aprobado).

- **Migración de datos** `contabilidad/migrations/0005_plan_de_cuentas.py` (la crea CON-02; la 0002 y la 0003 ya estaban ocupadas): una fila por cuenta, con `update_or_create` por
  `codigo_cuenta`; la inversa no hace nada. Pruebas con el mixin de `docs/patrones/datos_de_migracion.md`.
- **No hay ABM** y no hay auditoría (es una consulta, SEG-14). El servicio es de lectura: `plan.arbol() -> list[Rubro]` con
  `Rubro(codigo, nombre, subrubros=[Subrubro(codigo, nombre, cuentas=[CuentaContable])])` y `plan.cuenta(codigo)`.
- **Descripciones (regla 3):** el diccionario `DESCRIPCION_DE_CUENTA` de `contabilidad/cuentas.py` (una prueba verifica que cada cuenta del
  plan tiene su texto). Texto inicial, que **cada tarea de reapertura (CON-04a a CON-04d) completa** cuando agrega el asiento de su caso de
  uso (así el texto siempre dice lo que el sistema hace):

| Cuenta | Para qué se usa | Casos de uso que la mueven (a confirmar al reabrir cada uno) |
|---|---|---|
| 1.1.01 Caja | Efectivo de la organización | Pagos a proveedores en efectivo (Haber), cobros en efectivo (Debe), asientos manuales |
| 1.1.02 Banco c/c | Cuenta bancaria | Pagos por transferencia o tarjeta (Haber), cobros y reintegros (Debe/Haber), asientos manuales |
| 1.1.03 Deudores por Ventas | Lo que los clientes le deben a la organización | Entregas concretadas (Debe), cobros y anulaciones de cobro, indemnizaciones descontadas |
| 1.1.04 Insumos en Stock | Valor de los insumos en los invernaderos | Recepción (Debe), consumos, aplicaciones, ajustes de stock, corrección de recepción (Haber) |
| 1.1.05 Productos en Proceso | Valor de las plantas en cultivo | Siembra, transiciones, aplicaciones sobre lotes, lotes existentes (Debe), cosechas y mermas (Haber) |
| 1.1.06 Productos Terminados | Valor de lo cosechado y todavía no entregado | Cosecha (Debe), entregas, mermas y vencimientos en cámara (Haber) |
| 2.1.01 Proveedores | Lo que la organización les debe a sus proveedores | Recepción (Haber), pago y corrección de recepción (Debe) |
| 2.1.02 Indemnizaciones a Pagar | Multas por resolución de contratos que la organización todavía no pagó | Resolución del suministro (Haber, COM-RSV-SUM); su pago, asiento manual del Contador (Debe) |
| 3.1.01 Capital Inicial | Lo que ya existía al poner en marcha InfoPonia | Asiento de apertura de CON-INI-EJE, ajuste «carga inicial» de insumos y lotes existentes (Haber) |
| 4.1.01 Ventas | Ingresos por entregas | Entregas concretadas (Haber) |
| 4.1.02 Indemnizaciones por Atraso en el Pago | Lo que cobra la organización por atraso de un cliente | Pago en mora (COM-VNC-PAG, COM-REG-CBR) |
| 4.1.03 Otros Ingresos | Ingresos sin cuenta propia | Asientos manuales |
| 5.1.01 Costo de Producción Vendida | Costo de lo entregado | Entregas concretadas (Debe) |
| 5.1.02 Pérdidas por Mermas | Plantas o producto perdidos | Mermas en lotes y en cámara, vencimientos |
| 5.1.03 Gastos de Producción | Insumos aplicados sin lote en pie | Aplicación de insumos sin lote (PROD-REG-APL) |
| 5.1.04 Indemnizaciones por Incumplimiento a Cliente | Lo que paga la organización por cantidades o calidad faltantes | Evaluación de discrepancias y quejas (COM-EVL-DSC, COM-RSV-QJA) |
| 5.1.05 Indemnizaciones por Resolución de Contratos | Multa por resolver un suministro | COM-RSV-SUM |
| 5.1.06 Diferencias de Inventario de Insumos | Diferencias entre el stock del sistema y el real | Ajustes de stock (CMP-AJT-STK) (**puede quedar acreedora**) |
| 5.1.07 Gastos Generales | Gastos sin cuenta propia | Asientos manuales |

- **Pantalla:** pestaña «Plan de cuentas» de «Contabilidad» (prototipo: `tabPlan`, `PLAN`, `RUBROS`): árbol con código, nombre y tipo; desde cada
  cuenta, el enlace al libro de gestión (vista por cuenta) con su filtro ya puesto. Aviso fijo: «Sin IVA: es una simplificación declarada».
- **Pruebas** (`contabilidad/tests/test_con_cns_pct.py`): alcance (Contador y Gerente sí; Vendedor y resto, 403), el árbol completo y ordenado,
  cada cuenta con su descripción, la consulta no audita, sin consultas por fila.

## Solo prototipo

El interruptor «Hay un Contador activo» y el selector de rol.
