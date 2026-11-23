# Ronda «Contabilidad 1» — plan completo

Primera de las tres rondas nuevas (Contabilidad, Compras, Estadísticas; A0 P2: tres rondas, **P1(a): el núcleo contable va primero**).
Construye el rol Contador, el núcleo contable (ejercicios, asientos, plan de cuentas), las pantallas de «Contabilidad» y los asientos manuales.
**Los asientos automáticos de cada operación (producción, comercial, inventario) no son de esta ronda**: se agregan al reabrir esos casos de
uso en CON-04a/b/c (lote 3; ver `docs/tareas/orden_de_implementacion.md`). Decisiones: **D-84, D-85, D-86**. Criterio de documentación y tamaño
de las tareas: **D-44**. Este archivo lo lee la persona que planifica; Claude Code lo abre solo para completar la fila de su tarea al cerrar (M3).

## 1. Tareas

| ID | Tarea | App | Casos de uso | Depende de | Lote |
|---|---|---|---|---|---|
| USR-11 | El rol Contador y quién registra los asientos | core | USR-ALT/MOD/BAJ/CNS-USR, SEG-13, SEG-15 (cambios) | — | 1 |
| CON-02 | Núcleo contable | contabilidad | CON-ABR-EJE (paso diario 5) y `registrar_asiento_automatico` | USR-11, CON-01 (hecha) | 1 |
| CON-03a | Libro de gestión, plan de cuentas y ejercicios | contabilidad | CON-CNS-LGS, CON-CNS-PCT, CON-CRR-EJE | CON-02 | 1 |
| CON-03b | Asientos manuales y contraasientos | contabilidad | CON-REG-ASI, CON-CTR-ASI | CON-03a | 1 |

Son 7 casos de uso nuevos (más los cambios de cuentas por el rol). Tamaño: USR-11, chica; CON-02, grande y delicada; CON-03a y CON-03b, medianas.

## 2. Por qué este orden

1. **USR-11 primero:** el rol Contador y `responsables.py` los necesitan todas las tareas siguientes (y compras); es chica y no toca contabilidad.
2. **CON-02 antes que cualquier pantalla:** sin el servicio de asientos nadie más (compras, comercial, producción) puede asentar, y la
   numeración sin huecos y el orden de bloqueos son lo más delicado: conviene fijarlo con pruebas de concurrencia antes de construir encima.
3. **CON-03a antes que CON-03b:** el libro es donde vive el botón «Contraasentar», y ver los asientos es lo que permite revisar a mano si
   CON-02 anda.
4. Ninguna de las cuatro depende de producción, comercial ni compras: pueden empezar **ya**, en paralelo con lo que quede de «Producción 1»,
   «Comercial 1» e «IoT 1».

## 3. Pantallas

Prototipo: `docs/prototipos/compras_contabilidad/` (su README, sección «Contabilidad»). USR-11 solo toca el alta de cuentas y el menú; CON-03a: pestañas
«Libro de gestión», «Plan de cuentas» y «Ejercicios»; CON-03b: «Registrar asiento» y «Contraasentar».

## 4. Lo que queda fuera de esta ronda (y dónde se retoma)

| Qué | Dónde |
|---|---|
| Asiento automático de recepciones, correcciones y pagos | CMP-04, CMP-05 y CMP-06 (ronda de Compras) |
| Asiento y precondiciones contables de los casos de uso de producción, inventario y comercial (`docs/disparadores.md`, «Cuando exista contabilidad con asientos») | CON-04a a CON-04d |
| Quitarle al Vendedor el aviso de «registrar asiento manual» (COM-ATN-ENR, postcondición b) | CON-04d |
| ABM del plan de cuentas, varios Contadores, asiento de cierre y refundición de resultados | Mejoras futuras (A0) |
