# Estado — InfoPonia

Actualizado: 23/11/2026, con COM-01, IOT-04 y CMP-01 hechas (esperan su PR) y el lote C8 de «Comercial 1». Máximo 2 KB: lo hecho va a `docs/historial.md`.

## En curso

- Mergeadas: UI-01, NOT-01, MAE-03, MAE-04, CON-01, INV-01, DIA-01, INV-02, MAE-05, MAE-02c, INV-03, IOT-01, PRD-01, IOT-02, PRD-02 (#53), MAE-02d (#54), IOT-03 (#55), USR-10, PRD-03 (#57) y PRD-04 (#58), con revisión a mano pendiente.
- IOT-04 (revisión periódica, panel y configuración IoT): hecha en su rama, con `migrate` (`core` 0025). Falta su PR.
- COM-01 (clientes y vehículos, API de direcciones y CUIT): hecha en su rama, con `migrate` (`comercial` 0001, `core` 0024). Falta su PR.
- CMP-01 (`compras`, proveedores): hecha en su rama (`core` 0026); falta su PR.
- «Comercial 1»: C0 a C6 validados (D-57 a D-68); C7 a validar (D-69); C8 validado (D-94). COM-03 a COM-08 partidas (D-67 a D-69, D-94). IoT: I0 validado; I1 a I4 a validar.

## Siguiente

- Rondas nuevas (A0), documentadas y aprobadas: Contabilidad 1 y 2, Compras 1, Estadísticas 1 (D-84 a D-93). Orden: `docs/tareas/orden_de_implementacion.md`; USR-11, CON-02 y CMP-02a pueden empezar ya.
- IOT-05. COM-02 en adelante, cuando COM-01 esté mergeada (correcciones de D-81 y D-83 ya en los documentos).
- USR-09 y AUD-02, sin fecha.
- Procesos a mano: `proceso_diario` (D-56) y `revision_iot` (D-71, hecha en IOT-04); los cron jobs, al final.

## Revisiones a mano pendientes (congeladas; `docs/revisiones_pendientes.md`)

- UX: 8 · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 · MAE-02d: 7 (sin migraciones)
- Con migración (tras el despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 · IOT-01: 11 · PRD-01: 15 · PRD-02: 10 · IOT-02: 15 · PRD-03: 12 · PRD-04: 11 · IOT-04: 13 · COM-01: 11

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).