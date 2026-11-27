# Estado — InfoPonia

Actualizado: 27/11/2026 (CON-05 en rama; USR-07 mergeada). Máx. 2 KB; detalle en `docs/historial.md`.

## En curso

- **CON-05** (iniciar el ejercicio con el capital inicial; sin ejercicio no hay asiento; `core` 0054 solo `choices`): hecha en rama `feature/con-05-iniciar-ejercicio`. Falta PR, revisión a mano (28 pasos) y navegador real. Tras el merge, **antes de operar en producción**: `eliminar_ejercicio_sin_apertura` (con respaldo en Neon), iniciar la contabilidad desde la alerta y reanudar el cron (D-107, D-108). Hasta entonces: cron diario suspendido y nada que genere asientos.
- USR-07 (foto de perfil y logo; migraciones `core` 0053 y `maestros` 0014): mergeada (#105). Falta R2 real y navegador real.
- Mergeadas hasta USR-07 (#80–#105; EST-03 cierra «Estadísticas 1»). Falta navegador real de COM-05a1 a EST-03 (y `URL_DEL_SITIO` en Render) al cerrar «Comercial 1».
- «Comercial 1»: C0–C8 validados (D-57–D-69, D-94). COM-08c (#102) cerró la ronda. IoT: I0 validado; I1–I4 a validar.

## Siguiente

- Rondas A0 aprobadas: Contabilidad 1–2, Compras 1, Estadísticas 1 (D-84–D-93). Orden: `docs/tareas/orden_de_implementacion.md`.
- USR-09b y AUD-02. Retirar `eliminar_ejercicio_sin_apertura` después de correrlo en producción.
- Procesos: `proceso_diario` (D-56; pasos 5, 10, 20, 25, 27, 30, 33, 35, 40, 50, 60–63) en el cron `infoponia-proceso-diario` (6:00) y `revision_iot` (D-71) en `infoponia-revision-iot` (cada 5 min, suspendido salvo presentaciones); dos crons (D-108).

## Revisiones a mano pendientes (`docs/revisiones_pendientes.md`; D-96)

- UX: 8 · USR-09a: 15 (en Render, tras despliegue) · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 · MAE-02d: 7 · CON-03a: 28 · CON-04b: 17 · CON-03b: 41 · CON-04a: 17 · EST-01: 22 · CON-04c: 16 · EST-02: 21 · COM-08c: 15 · CON-04d: 16 · EST-03: 16
- Con migración (tras despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 · IOT-01: 11 · PRD-01: 15 · PRD-02: 10 · IOT-02: 15 · PRD-03: 12 · PRD-04: 11 · IOT-04: 13 · COM-01: 11 · CMP-01: 17 · CMP-02a: 19 · IOT-05: 17 · COM-03a: 13 · IOT-06: 37 · CMP-02b: 21 · COM-03b: 14 · IOT-07: 11 · COM-04a: 18 · USR-11: 15 · CMP-03: 31 · COM-04b: 16 · CON-02: 16 · COM-04c: 14 · COM-05a1: 10 · CMP-04: 44 · COM-05a2: 14 · COM-05b: 22 · COM-06a: 15 · CMP-05: 24 · PRD-05: 28 · CMP-06: 27 · COM-06b: 14 · COM-07a: 19 · COM-07b: 17 · COM-08a: 18 · CMP-07: 15 · COM-08b: 16 · USR-07: 41 · CON-05: 28

## Esperas y bloqueos

- Ninguna.
