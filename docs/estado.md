# Estado — InfoPonia

Actualizado: 24/11/2026 (USR-11 en rama). Máx. 2 KB; detalle en `docs/historial.md`.

## En curso

- Mergeadas: UI-01, NOT-01, MAE-03, MAE-04, CON-01, INV-01, DIA-01, INV-02, MAE-05, MAE-02c, INV-03, IOT-01, PRD-01, IOT-02, PRD-02 (#53), MAE-02d (#54), IOT-03 (#55), USR-10, PRD-03 (#57), PRD-04 (#58), COM-01 (#62), IOT-04 (#63), CMP-01 (#64), COM-02 (#65), CMP-02a (#66), IOT-05 (#67), COM-03a (#68), CMP-02b (#69), IOT-06 (#70), COM-03b (#71), IOT-07 (#72), COM-04a (#73). Revisión pendiente (D-96).
- USR-11 (rol Contador y `responsables.py`): en rama (`core` 0035). Falta PR.
- «Comercial 1»: C0–C6 validados (D-57–D-68); C7 a validar (D-69); C8 validado (D-94). COM-04b–COM-08 partidas. IoT: I0 validado; I1–I4 a validar.

## Siguiente

- Rondas A0 aprobadas: Contabilidad 1–2, Compras 1, Estadísticas 1 (D-84–D-93). Orden: `docs/tareas/orden_de_implementacion.md`; CON-02 y CMP-03 listas.
- COM-04b (tras COM-04a), USR-09 y AUD-02.
- Procesos: `proceso_diario` (D-56; pasos 35, 40 en COM-03b) y `revision_iot` (D-71); cron jobs al final.

## Revisiones a mano pendientes (`docs/revisiones_pendientes.md`; D-96)

- UX: 8 · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 · MAE-02d: 7 (sin migraciones)
- Con migración (tras el despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 · IOT-01: 11 · PRD-01: 15 · PRD-02: 10 · IOT-02: 15 · PRD-03: 12 · PRD-04: 11 · IOT-04: 13 · COM-01: 11 · CMP-01: 17 · CMP-02a: 19 · IOT-05: 17 · COM-03a: 13 · IOT-06: 37 · CMP-02b: 21 · COM-03b: 14 · IOT-07: 11 · COM-04a: 18 · USR-11: 15

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).