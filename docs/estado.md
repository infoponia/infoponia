# Estado — InfoPonia

Actualizado: 25/11/2026 (CMP-05 en rama). Máx. 2 KB; detalle en `docs/historial.md`.

## En curso

- Mergeadas hasta COM-05b (#85; antes COM-05a2 #84, COM-05a1 #81, CMP-04 #82, CON-04b #83 y CON-03a #80). Al cerrar la tanda de «Comercial 1»: navegador real de COM-05a1, COM-05a2 y COM-05b (y `URL_DEL_SITIO` en Render).
- CMP-05 (pago a proveedores): en rama (`compras` 0005, `contabilidad` 0007, `core` 0044). Falta PR y navegador real.
- «Comercial 1»: C0–C6 y C8 validados (D-57–D-68, D-94); C7 a validar (D-69). COM-06–COM-08 partidas. IoT: I0 validado; I1–I4 a validar.

## Siguiente

- Rondas A0 aprobadas: Contabilidad 1–2, Compras 1, Estadísticas 1 (D-84–D-93). Orden: `docs/tareas/orden_de_implementacion.md`.
- COM-06a, CMP-06, CON-03b, USR-09b y AUD-02.
- Procesos: `proceso_diario` (D-56; pasos 5, 20, 25, 27, 35, 40, 50 y 60–62) y `revision_iot` (D-71); cron al final.

## Revisiones a mano pendientes (`docs/revisiones_pendientes.md`; D-96)

- UX: 8 · USR-09a: 15 (en Render, tras despliegue) · USR-08: 5 · USR-08b: 6 · AUD-01: 6 · CFG: 1 · MAE-02b: 14 · UI-01: 6 · NOT-01: 7
- MAE-03: 12 · MAE-04: 10 · CON-01: 6 · DIA-01: 3 · MAE-02c: 12 · MAE-02d: 7 · CON-03a: 28 · CON-04b: 17
- Con migración (tras despliegue): INV-01: 14 · INV-02: 16 · MAE-05: 10 · INV-03: 14 · IOT-01: 11 · PRD-01: 15 · PRD-02: 10 · IOT-02: 15 · PRD-03: 12 · PRD-04: 11 · IOT-04: 13 · COM-01: 11 · CMP-01: 17 · CMP-02a: 19 · IOT-05: 17 · COM-03a: 13 · IOT-06: 37 · CMP-02b: 21 · COM-03b: 14 · IOT-07: 11 · COM-04a: 18 · USR-11: 15 · CMP-03: 31 · COM-04b: 16 · CON-02: 16 · COM-04c: 14 · COM-05a1: 10 · CMP-04: 44 · COM-05a2: 14 · COM-05b: 22 · CMP-05: 24

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).
