# Ronda «Contabilidad 2» — plan completo

Reabre lo que ya está programado (o lo estará) para que genere su asiento, y suma el registro de lotes existentes. Decisión: **D-92**. Criterio
de documentación y tamaño de las tareas: **D-44**. Este archivo lo lee la persona que planifica; Claude Code lo abre solo para completar la fila
de su tarea al cerrar (M3).

## 1. Tareas

| ID | Tarea | App | Casos de uso | Depende de | Tamaño |
|---|---|---|---|---|---|
| CON-04b | Asientos de los ajustes de stock (carga inicial contra Capital Inicial) (**hecha**, 24/11/2026) | inventario | CMP-AJT-STK | CON-02 | chica |
| PRD-05 | Registrar Lote Existente (**hecha**, 25/11/2026) | produccion | PROD-REG-LTE | CON-02, PRD-03 (hecha) | mediana |
| CON-04a | Asientos de producción (**hecha**, 25/11/2026) | produccion | PROD-CNC-SMB, PROD-CNC-TRN, PROD-REG-MRM, PROD-REG-APL, PROD-PNR-FDS | CON-02 (PRD-04, hecha) | mediana |
| CON-04c | Asientos de cosecha, cámara y entregas (**hecha**, 26/11/2026) | comercial, produccion | PROD-CNC-CSC, PROD-REG-MRM (cámara), PROD-VNC-CAM, COM-CNC-ENT | CON-02, COM-04a, COM-04b, COM-06a | mediana |
| CON-04d | Asientos de cobros, indemnizaciones y multas | comercial | COM-REG-CBR, COM-ANL-CBR, COM-CNL-CVT, COM-EVL-DSC, COM-RSV-QJA, COM-ANL-SRV, COM-RSV-SUM, COM-ATN-ENR | CON-02, USR-11, COM-06b a COM-08b | mediana (o vacía) |

## 2. Por qué este orden

1. **CON-04b y PRD-05 primero:** son las dos cargas iniciales (insumos y lotes). Conviene tenerlas antes de cargar los datos reales, para que el
   valor de lo que ya existe entre contra Capital Inicial desde el primer día.
2. **CON-04a después:** sin ella, cada siembra, merma o aplicación que se haga queda sin asiento (P6: no se asienta hacia atrás). Va apenas
   CON-02 esté en `main`.
3. **CON-04c y CON-04d esperan a Comercial**, que todavía no está programado. Si CON-02 llega antes que cada tarea de Comercial, esa tarea ya
   trae su asiento (D-92 punto 9) y estas dos se achican o desaparecen.

## 3. Lo que queda fuera (y dónde se retoma)

| Qué | Dónde |
|---|---|
| Partidas en cámara y cosechas previas a la puesta en marcha | Asiento manual del Contador (CON-REG-ASI) |
| Pago de la multa por resolución | Asiento manual del Contador (D-92 punto 10) |
