# Orden de implementación de las tres rondas nuevas (Contabilidad, Compras, Estadísticas)

Mapa para decidir qué tarea programar y cuándo. Ordenado por **dependencia técnica** y, dentro de cada nivel, por **importancia** (A0 P1(a):
el núcleo contable primero; Estadísticas, último, porque solo lee lo que ya existe). «Lote» = en qué entrega de documentación llega el archivo.

| # | Tarea | Qué entrega | Depende de | Ronda | Lote | Archivo |
|---|---|---|---|---|---|---|
| 1 | USR-11 | Rol Contador y «quién registra» | — | Contabilidad 1 | 1 | `core/USR-11-rol-contador.md` |
| 2 | CON-02 | Núcleo contable y asientos automáticos | 1 | Contabilidad 1 | 1 | `contabilidad/CON-02-nucleo-contable.md` |
| 3 | CON-03a | Libro, plan y ejercicios (con cierre) | 2 | Contabilidad 1 | 1 | `contabilidad/CON-03a-libro-plan-y-ejercicios.md` |
| 4 | CON-03b | Asientos manuales y contraasientos | 3 | Contabilidad 1 | 1 | `contabilidad/CON-03b-asientos-manuales-y-contraasientos.md` |
| 5 | CMP-01 | App `compras` y proveedores | INV-02 (hecha) | Compras 1 | 2 | `compras/CMP-01-app-compras-y-proveedores.md` |
| 6 | CMP-02a | Pedido de cotización y portal del proveedor | 5 | Compras 1 | 2 | `compras/CMP-02a-pedido-y-portal-del-proveedor.md` |
| 7 | CMP-02b | Cancelar, reenviar y lo que cancela solo | 6 | Compras 1 | 2 | `compras/CMP-02b-cancelar-reenviar-y-bajas.md` |
| 8 | CMP-03 | Orden de compra y pasos diarios 60 a 62 | 7 | Compras 1 | 2 | `compras/CMP-03-orden-de-compra-y-pasos-diarios.md` |
| 9 | CMP-04 | Recepción y cierre con faltante (con asiento) | 8 y 2 | Compras 1 | 2 | `compras/CMP-04-recepcion-y-cierre-con-faltante.md` |
| 10 | CMP-05 | Pago a proveedores (con asiento) | 9, 1 y 2 | Compras 1 | 2 | `compras/CMP-05-pago-a-proveedores.md` |
| 11 | CMP-06 | Corrección de recepción y reclamos | 10 | Compras 1 | 2 | `compras/CMP-06-correccion-de-recepcion-y-reclamos.md` |
| 11b | CMP-07 | Pedido automático por stock bajo | 6 y 8 | Compras 1 | 2 | `compras/CMP-07-pedido-automatico-por-stock-bajo.md` |
| 12 | CON-04b | Asientos de los ajustes (carga inicial contra Capital Inicial) | 2 | Contabilidad 2 | 3 | `contabilidad/CON-04b-asientos-de-inventario.md` |
| 13 | PRD-05 | Registrar Lote Existente (PROD-REG-LTE) | 2 y PRD-03 (hecha) | Contabilidad 2 | 3 | `produccion/PRD-05-registrar-lote-existente.md` |
| 14 | CON-04a | Asientos de producción (reapertura) | 2 (PRD-04 ya está) | Contabilidad 2 | 3 | `contabilidad/CON-04a-asientos-de-produccion.md` |
| 15 | CON-04c | Asientos de cosecha, cámara y entregas | 2, COM-04a, COM-04b, COM-06a | Contabilidad 2 | 3 | `contabilidad/CON-04c-asientos-de-cosecha-camara-y-entregas.md` |
| 16 | CON-04d | Asientos de cobros, indemnizaciones y multas | 2, 1, COM-06b a COM-08b | Contabilidad 2 | 3 | `contabilidad/CON-04d-asientos-de-cobros-indemnizaciones-y-multas.md` |
| 17 | EST-01 | App `estadisticas` (nivel 8) y estadísticas de producción | PRD-03 (hecha); mejor después de 14 | Estadísticas 1 | 4 | `estadisticas/EST-01-app-y-estadisticas-de-produccion.md` |
| 18 | EST-02 | Estadísticas consolidadas del Gerente (sin lo comercial) | 17, 3 y 11 | Estadísticas 1 | 4 | `estadisticas/EST-02-estadisticas-consolidadas.md` |
| 19 | EST-03 | Lo comercial dentro de las consolidadas | 18 y COM-08c | Estadísticas 1 | 4 | `estadisticas/EST-03-estadisticas-comerciales-en-las-consolidadas.md` |
| 20 | CON-05 | Iniciar el ejercicio contable con el capital inicial (CON-INI-EJE) y «sin ejercicio no hay asiento» | 1 a 19 | — (puesta en marcha) | — | `contabilidad/CON-05-iniciar-ejercicio-contable.md` |

**Paralelismo.** 1 a 4 y 5 a 8 pueden empezar ya, en dos líneas paralelas: la contable y la de compras (la orden de compra no asienta).
Se juntan en 9 (la recepción necesita CON-02) y 10 (el pago necesita además USR-11). 12 a 14 pueden ir apenas esté 2; 15 y 16 esperan a Comercial, y si 2 llega antes
que cada tarea de Comercial, esa tarea ya trae su asiento (D-92 punto 9). 17 a 19 van últimas; 19 espera a COM-08c.
