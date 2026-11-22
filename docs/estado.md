# Estado — InfoPonia

Actualizado: 22/11/2026, tras implementar MAE-02c (consulta de alertas, CU-46). Se reescribe al cerrar cada tarea y no pasa de 2 KB: lo hecho va a `docs/historial.md`.

## En curso

- UI-01 y NOT-01 mergeadas; MAE-03, MAE-04, CON-01, INV-01, DIA-01, INV-02, MAE-05 y MAE-02c en su rama, esperando revisión a mano.
- Lote 5, D-52, D-55 y D-56 validados (21/11/2026). Decisiones previas de MAE-02c aprobadas (22/11/2026).

## Siguiente

- Ronda «Producción 1»: INV-03 (ya puede empezar: INV-02 hecha) y PRD-01 a PRD-04. Cada una se programa cuando su lote de documentación está en el repo (plan en `docs/tareas/ronda_produccion_1.md`).
- USR-10 (correo público, D-54): antes de IOT-03.
- IoT y comercial: en paralelo entre sí, y los dos después de lo que necesiten de «Producción 1». USR-09 y AUD-02, sin fecha; ver `docs/temas_abiertos.md`.
- Proceso diario: a mano con `python manage.py proceso_diario` (el paso 10 revisa vencimientos); el cron job, uno solo, al final (D-56).

## Revisiones a mano pendientes (en `docs/revisiones_pendientes.md`)

- UX: 8 · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · INV-01: 14 (migrar; el último, tras el despliegue) · DIA-01: 3 · INV-02: 16 (migrar; el último, tras el despliegue) · MAE-05: 10 (migrar; el último, tras el despliegue) · MAE-02c: 12 (sin migraciones)

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).
