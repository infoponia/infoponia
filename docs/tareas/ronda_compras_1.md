# Ronda «Compras 1» — plan completo

Segunda de las tres rondas nuevas (Contabilidad, Compras, Estadísticas; A0 P2). Crea la app `compras` (nivel 6, D-37) y el circuito completo:
proveedores → pedido de cotización → cotización del proveedor por enlace → orden de compra → aprobación → recepción → pago, más la corrección de
recepciones y los reclamos. Decisiones: **D-87** (la de la ronda), **D-88** (enlace del proveedor), **D-89** (precios y valores), **D-90**
(recepción y stock), **D-91** (pago). Criterio de documentación y tamaño de las tareas: **D-44**. Este archivo lo lee la persona que planifica;
Claude Code lo abre solo para completar la fila de su tarea al cerrar (M3).

## 1. Tareas

| ID | Tarea | Casos de uso | Depende de | Tamaño |
|---|---|---|---|---|
| CMP-01 | App `compras` y proveedores (**hecha**, 23/11/2026) | CMP-ALT/MOD/BAJ/CNS-PRV | INV-02 (hecha) | chica |
| CMP-02a | Pedido de cotización y portal del proveedor (**hecha**, 23/11/2026) | CMP-RLZ-PED, CMP-ENV-COT, CMP-CNS-PED | CMP-01 (hecha), USR-10 (hecha) | grande |
| CMP-02b | Cancelar pedido, reenviar invitación y lo que cancela solo (**hecha**, 24/11/2026) | CMP-CNL-PED, reenvío, MD-62, H20 | CMP-02a (hecha) | mediana |
| CMP-03 | Orden de compra y pasos diarios | CMP-GNR-ODC, CMP-APR-ODC, CMP-CNS-ODC, pasos 60 a 62 | CMP-02b | grande |
| CMP-04 | Recepción y cierre con faltante | CMP-REG-RCP, CMP-CRR-FLT | CMP-03, **CON-02** | grande y delicada |
| CMP-05 | Pago a proveedores | CMP-REG-PAG | CMP-04, **USR-11**, CON-02 | mediana |
| CMP-06 | Corrección de recepción y reclamos | CMP-COR-RCP, CMP-EMT-RCL, CMP-CRR-RCL | CMP-05 | mediana |

Son 17 casos de uso. Ninguna tarea importa de `comercial` ni de `produccion` (mismo nivel 6; D-37 regla A2).

## 2. Por qué este orden

1. **CMP-01 a CMP-03 no tocan la contabilidad:** la orden de compra no genera asiento (D-91). Pueden empezar **ya**, en paralelo con la ronda
   «Contabilidad 1». Esto es lo que A0 P1(a) permite: el núcleo contable primero, pero lo que no asienta no tiene por qué esperarlo.
2. **El pedido se parte en dos (02a y 02b)** porque el portal del proveedor (vistas públicas sin cuenta, token, acuse, concurrencia) ya es una
   sesión entera; cancelar, reenviar y las cancelaciones automáticas por baja o traspaso del Agrónomo son registrantes en otras apps y conviene
   probarlas aparte.
3. **CMP-04 espera a CON-02** porque cada recepción genera su asiento; es la más delicada de la ronda (stock, tránsito, redondeo del valor y el
   orden de bloqueos que termina en `EjercicioContable`).
4. **CMP-05 espera además a USR-11:** paga el responsable contable (el Contador, o el Gerente si no hay).
5. **CMP-06 al final:** corregir una recepción exige que exista el pago (no se corrige lo pagado) y el tipo nuevo de movimiento de inventario.

## 3. Pantallas

Prototipo: `docs/prototipos/compras_contabilidad/` (su README, sección «Compras»). Menú «Compras» con pestañas Pedidos, Órdenes, Por recibir,
Reclamos, Proveedores y Pagos; el portal del proveedor (`VIEWS.c_cotz`) es una pantalla pública aparte; la entrada «Pagos a proveedores» la
registra compras junto a «Contabilidad» para el Contador (D-87).

## 4. Lo que queda fuera de esta ronda (y dónde se retoma)

| Qué | Dónde |
|---|---|
| Indicadores de compras (plazo de entrega, cumplimiento del proveedor) | EST-02 (ronda Estadísticas) |
| Pagos parciales, notas de crédito, devoluciones con dinero, anular un pago | Mejoras futuras (A0) |
| Inconveniente de tipo «retraso» (se ve por la fecha, P4) | No se declara |
