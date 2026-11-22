# Estado — InfoPonia

Actualizado: 22/11/2026, tras implementar PRD-01 y con el lote C7 de «Comercial 1». Se reescribe al cerrar cada tarea y no pasa de 2 KB: lo hecho va a `docs/historial.md`.

## En curso

- Mergeadas: UI-01 y NOT-01; MAE-03, MAE-04, CON-01, INV-01, DIA-01, INV-02, MAE-05 (PR #45), MAE-02c (#47), INV-03 (#48) e IOT-01 (#50), con la revisión a mano pendiente. PRD-01 hecha (siembra, bandeja y tipos de orden futuros; D-81), a la espera de su PR y de su revisión.
- «Comercial 1»: C0 a C6 validados (D-57 a D-68); C7 a validar (D-69). Sigue C8 (decisiones desde D-82).
  COM-03 a COM-07 partidas (D-67 a D-69): COM-03a/b, COM-04a/b/c, COM-05a1/a2, COM-06a/b, COM-07a/b. IoT: I0 validado; I1 a I4 a validar.

## Siguiente

- MAE-02d (lo que le faltó a MAE-02c de D-62): antes de COM-03b y de IOT-04.
- Ronda «Producción 1»: PRD-02 a PRD-04 (plan en `docs/tareas/ronda_produccion_1.md`). El panel «Ritmo sostenible» de PRD-01 quedó recortado (`temas_abiertos.md`).
- Corregir `tipo` → `tipo_orden` (D-81) en COM-02, COM-05a1/a2, IOT-07 y `docs/modelo/produccion.md`.
- USR-10 (correo público, D-54): antes de COM-02 y de IOT-04.
- Comercial (`ronda_comercial_1.md`; sigue C8) e IoT (`ronda_iot_1.md`) en paralelo. USR-09 y AUD-02, sin fecha.
- Procesos: a mano (`proceso_diario`, D-56; `revision_iot`, D-71); los cron jobs, al final.

## Revisiones a mano pendientes (en `docs/revisiones_pendientes.md`)

- UX: 8 · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 (sin migraciones)
- Con migración (el último paso, tras el despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 (antes de `migrate`, borrar las variedades cargadas a mano) · IOT-01: 11 · PRD-01: 15

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).