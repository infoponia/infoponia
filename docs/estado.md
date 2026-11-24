# Estado — InfoPonia

Actualizado: 24/11/2026 (COM-04b, CMP-03 y CON-02 en rama). Máx. 2 KB; detalle en `docs/historial.md`.

## En curso

- Mergeadas: UI-01, NOT-01, MAE-03, MAE-04, CON-01, INV-01, DIA-01, INV-02, MAE-05, MAE-02c, INV-03, IOT-01, PRD-01, IOT-02, PRD-02, MAE-02d, IOT-03, USR-10, PRD-03, PRD-04, COM-01, IOT-04, CMP-01, COM-02, CMP-02a, IOT-05, COM-03a, CMP-02b, IOT-06, COM-03b, IOT-07, COM-04a (#73), USR-11 (#74), USR-09a (#75). Revisión pendiente (D-96).
- COM-04b (cámara, pasos 20 y 25): en rama (`maestros` 0011, `comercial` 0006, `core` 0037). Falta PR.
- CMP-03 (orden de compra, pasos 60–62): en rama (`compras` 0003, `core` 0036). Falta PR.
- CON-02 (núcleo contable, paso diario 5): en rama (`contabilidad` 0004 y 0005, `core` 0038). Falta PR.
- «Comercial 1»: C0–C6 validados (D-57–D-68); C7 a validar (D-69); C8 validado (D-94). COM-04c–COM-08 partidas. IoT: I0 validado; I1–I4 a validar.

## Siguiente

- Rondas A0 aprobadas: Contabilidad 1–2, Compras 1, Estadísticas 1 (D-84–D-93). Orden: `docs/tareas/orden_de_implementacion.md`; CON-02 en rama; CMP-04 espera a que se mergee.
- COM-04c (tras COM-04b), USR-09b y AUD-02.
- Procesos: `proceso_diario` (D-56; pasos 5 en CON-02, 20, 25, 35, 40; 60–62 en CMP-03) y `revision_iot` (D-71); cron jobs al final.

## Revisiones a mano pendientes (`docs/revisiones_pendientes.md`; D-96)

- UX: 8 · USR-09a: 15 (en Render, tras despliegue) · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 · MAE-02d: 7 (sin migraciones)
- Con migración (tras despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 · IOT-01: 11 · PRD-01: 15 · PRD-02: 10 · IOT-02: 15 · PRD-03: 12 · PRD-04: 11 · IOT-04: 13 · COM-01: 11 · CMP-01: 17 · CMP-02a: 19 · IOT-05: 17 · COM-03a: 13 · IOT-06: 37 · CMP-02b: 21 · COM-03b: 14 · IOT-07: 11 · COM-04a: 18 · USR-11: 15 · CMP-03: 31 · COM-04b: 16 · CON-02: 16

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).