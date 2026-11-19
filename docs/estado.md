# Estado — InfoPonia

Actualizado: 19/11/2026, al cerrar MAE-02a (alerta: modelo, API y alertas de personal del invernadero). Este archivo se reescribe al
cerrar cada tarea y no pasa de 2 KB: lo hecho va a `docs/historial.md`.

## En curso

- Ninguna tarea de código. MAE-02a está lista y espera revisión (rama `feature/mae-02-alerta`).

## Siguiente

- MAE-02b (alerta en la baja y reactivación de cuenta, Inicio del Gerente, `abrir_alerta` y CU-46) y la tarea de notificaciones
  en `core` (NOT-01, D-42). Detalle en docs/tareas/README.md.
- Módulo IoT (en paralelo, sobre la API de `docs/api/alertas.md`), USR-09 y AUD-02, sin fecha.

## Revisiones a mano pendientes

- UX: 8 pasos → `docs/revisiones_pendientes.md`, sección UX
- USR-08: 5 pasos → sección USR-08 (incluye cargar las variables de correo en Render)
- USR-08b: 6 pasos → sección USR-08b
- AUD-01: 6 pasos → sección AUD-01
- CFG: 1 paso → sección CFG (exigir el check de `pruebas.yml` en main)
- MAE-02a: 13 pasos → sección MAE-02a (el último: verificar en el log de Render que se aplicó `maestros 0003_alerta`)

## Esperas y bloqueos

- USR-07: proveedor de almacenamiento y permiso para Pillow y `django-storages` (D-20).
