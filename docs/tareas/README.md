# Tareas — InfoPonia

Índice de las tareas pendientes de todas las apps. Se lee al elegir la próxima tarea. Cada tarea es un archivo en
`docs/tareas/<app>/<ID>-<nombre>.md`, escrito con `_plantilla.md`.

- Estados: pendiente, bloqueada, en curso, en revisión (PR abierta) y hecha.
- Las hechas salen de este índice; su archivo queda en su carpeta como registro y se anota una línea en
  `docs/historial.md`.
- IDs: `<PREFIJO>-NN`, con el prefijo de la app. La tarea termina en número (`USR-07`); el caso de uso, en tres letras
  (`USR-INI-SES`). Ojo: el prefijo de tarea `PRD` y el de caso de uso `PROD` son cosas distintas.
- Las tareas las escribe una persona, o Claude en claude.ai, y el estudiante las aprueba antes de pasarlas a Claude Code
  (regla M6).

| Prefijo | App |
|---|---|
| USR | core, cuentas y seguridad |
| AUD | core, auditoría |
| ALR | core, alertas y notificaciones |
| MAE | maestros (incluye organización, configuración y geografía) |
| INV | inventario |
| PRD | produccion (y PRD-00, que crea las apps) |
| CMP | compras |
| COM | comercial |
| IOT | iot |
| CON | contabilidad |
| DOC | documentación |

## Pendientes

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| USR-07 | Foto de perfil | core | bloqueada | Proveedor de almacenamiento; permiso para Pillow y `django-storages` (D-20) | `usuarios/USR-07-foto-perfil.md` |
| USR-09 | Seguridad de producción | core | pendiente | — | `usuarios/USR-09-seguridad-produccion.md` |
| AUD-02 | Exportar la auditoría a CSV | core | pendiente | Reglas del caso de uso, sin escribir | `auditoria/AUD-02-exportar-csv.md` |
| PRD-00 | Crear las apps de los módulos de negocio | config | pendiente | — | `produccion/PRD-00-crear-apps.md` |
| ALR-01 | Alerta común (la usan producción e IoT) | core | pendiente | Archivo por escribir. Va antes que el invernadero; la hace Fabrizio | — |

## Tareas hechas antes del traspaso (18/11/2026)

No tienen archivo: su registro está en `docs/historial.md`. Los IDs nuevos sirven para nombrarlas en
`docs/revisiones_pendientes.md`.

| ID nuevo | Nombre anterior |
|---|---|
| USR-01 a USR-06 | Tareas 01, 02, 03, 04a, 04b, 05a, 05b, 06a y 06b |
| USR-08 | Tarea 08 (recuperar contraseña por correo) |
| USR-08b | Tarea 08b (invitación por correo) |
| AUD-01 | Tarea AUD-CNS-REG |
| UX | Tarea chica de experiencia de uso (rama `chore/pendientes`) |
