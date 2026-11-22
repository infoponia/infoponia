# Estado — InfoPonia

Actualizado: 22/11/2026, tras implementar IOT-01 y con el lote C7 de «Comercial 1». Se reescribe al cerrar cada tarea y no pasa de 2 KB: lo hecho va a `docs/historial.md`.

## En curso

- Mergeadas: UI-01 y NOT-01; MAE-03, MAE-04, CON-01, INV-01, DIA-01, INV-02, MAE-05 (PR #45), MAE-02c (#47) e INV-03 (#48), con la revisión a mano pendiente. IOT-01 hecha (app `iot`, esquema completo y tipos de actuador), a la espera del merge y de su revisión.
- «Comercial 1»: C0 a C6 validados (D-57 a D-68); C7 a validar (D-69). Sigue C8 (decisiones desde D-80).
  COM-03 a COM-07 partidas (D-67 a D-69): COM-03a/b, COM-04a/b/c, COM-05a1/a2, COM-06a/b, COM-07a/b. IoT: I0 validado; I1 a I4 a validar.

## Siguiente

- MAE-02d (lo que le faltó a MAE-02c de D-62): antes de COM-03b y de IOT-04.
- Ronda «Producción 1»: PRD-01 a PRD-04 (INV-03 ya está hecha; plan en `docs/tareas/ronda_produccion_1.md`). PRD-01 deja hechos los tipos
  de orden futuros (D-67, punto 1).
- USR-10 (correo público, D-54): antes de COM-02 y de IOT-04.
- Comercial (`ronda_comercial_1.md`; sigue C8) e IoT (`ronda_iot_1.md`) en paralelo. USR-09 y AUD-02, sin fecha.
- Procesos: a mano (`proceso_diario`, D-56; `revision_iot`, D-71); los cron jobs, al final.

## Revisiones a mano pendientes (en `docs/revisiones_pendientes.md`)

- UX: 8 · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 (sin migraciones)
- Con migración (el último paso, tras el despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 (antes de `migrate`, borrar las variedades cargadas a mano) · IOT-01: 8

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).
