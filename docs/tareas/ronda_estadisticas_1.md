# Ronda «Estadísticas 1» — plan completo

Tercera y última de las rondas nuevas. Crea la app `estadisticas` (nivel 8, enmienda a D-37) con dos consultas de solo lectura: producción
(Agrónomo y Gerente) y consolidadas (Gerente). Decisión: **D-93** (incluye las fórmulas, a validar: los indicadores son provisorios, H26).
Criterio de documentación y tamaño de las tareas: **D-44**. Este archivo lo lee la persona que planifica; Claude Code lo abre solo para completar
la fila de su tarea al cerrar (M3).

## 1. Tareas

| ID | Tarea | Casos de uso | Depende de | Tamaño |
|---|---|---|---|---|
| EST-01 | App `estadisticas` y estadísticas de producción | EST-CNS-PRD | PRD-03 (hecha); mejor después de CON-04a; la cosecha, de COM-04a (si no, «no disponible») | mediana · hecha (PR #__, 26/11/2026; revisión a mano pendiente) |
| EST-02 | Estadísticas consolidadas del Gerente (sin lo comercial) | EST-CNS-CNS (indicadores 7, 9 y 10) | EST-01, CON-03a, CMP-06 | mediana · hecha (PR #__, 26/11/2026; revisión a mano pendiente) |
| EST-03 | Lo comercial dentro de las consolidadas | EST-CNS-CNS (indicador 8) | EST-02, COM-08c | chica |

## 2. Por qué este orden

1. **Va última** porque solo lee lo que hacen las otras (A0: Estadísticas, al final).
2. **No espera a todo Comercial:** EST-01 y EST-02 se pueden hacer con lo que ya existe (producción, inventario, IoT, compras, contabilidad); lo
   que lee de la cosecha se muestra «no disponible» hasta COM-04a (D-93 punto 5), y lo comercial queda aparte en EST-03, que espera a COM-08c.
3. **EST-02 espera a CMP-06** porque «compras del período» resta las correcciones; y a CON-03a, por las lecturas del libro.

## 3. Pantallas

Prototipo: `docs/prototipos/compras_contabilidad/` (su README, sección «Estadísticas»). Ya sigue el caso de uso y D-93; si
algo difiere, mandan ellos.

## 4. Lo que queda fuera

| Qué | Dónde |
|---|---|
| Ajustar los indicadores tras la entrevista al productor (H26) | Una decisión nueva que enmiende D-93 |
| Estadísticas comerciales del Vendedor (COM-CNS-EST) | COM-08c (D-94) |
