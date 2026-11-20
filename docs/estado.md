# Estado — InfoPonia

Actualizado: 20/11/2026, tras mergear MAE-02b (PR #32) y entregar el lote 5 (el último) de la documentación de la ronda «Producción 1». Este
archivo se reescribe al cerrar cada tarea y no pasa de 2 KB: lo hecho va a `docs/historial.md`.

## En curso

- Ninguna tarea de código. Documentación de la ronda «Producción 1»: lotes 0 a 4 validados, lote 5 (PRD-03 y PRD-04) entregado a validar; con los lotes 4 y 5 en el repo empieza la implementación (PRD-01 primero)
  (`docs/tareas/ronda_produccion_1.md`; D-42 y D-44 a D-50 vigentes, D-51, D-52, D-53 y D-54 a validar).

## Siguiente

- MAE-02c (pantalla de consulta de alertas, CU-46, con la entrada «Alertas» del menú; archivo por escribir).
- Ronda «Producción 1»: UI-01, NOT-01, MAE-03, MAE-04, CON-01, INV-01 a INV-03 y PRD-01 a PRD-04. Se programa cada una cuando su lote de
  documentación está en el repo (plan y orden en `docs/tareas/ronda_produccion_1.md`).
- USR-10 (envío de correo público, D-54): va antes de IOT-03.
- Módulo IoT (**después** de la ronda «Producción 1», no en paralelo; sobre la API de `docs/api/alertas.md`), USR-09 y AUD-02, sin fecha. La documentación del IoT se arma en lotes aparte; ver `docs/temas_abiertos.md`, «Abiertos desde la preparación del IoT».

## Revisiones a mano pendientes

- UX: 8 pasos → `docs/revisiones_pendientes.md`, sección UX
- USR-08: 5 pasos → sección USR-08 (incluye cargar las variables de correo en Render)
- USR-08b: 6 pasos → sección USR-08b
- AUD-01: 6 pasos → sección AUD-01
- CFG: 1 paso → sección CFG (exigir el check de `pruebas.yml` en main)
- MAE-02b: 14 pasos → sección MAE-02b (el último: después del despliegue, ver «Personal por asignar» en Render)

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).
