# Tareas — InfoPonia

Índice de las tareas pendientes de todas las apps. Se lee al elegir la próxima tarea. Cada tarea es un archivo en
`docs/tareas/<app>/<ID>-<nombre>.md`, escrito con `_plantilla.md`.

**Una tarea es un bloque funcional** (D-44): los casos de uso que comparten modelo, servicios y pantallas, de 4 a 10 casos
de uso, en una sola sesión de Claude Code y un solo PR. La documentación de toda una ronda está completa en el repo antes
de programar su primera tarea. El plan de la ronda vigente (tareas, orden, casos de uso y pantallas) es
`docs/tareas/ronda_produccion_1.md`. Para trabajar de a dos sin pisarse: `docs/patrones/trabajo_en_paralelo.md`.

- Estados: pendiente, bloqueada, en curso, en revisión (PR abierta) y hecha.
- Las hechas salen de este índice; su archivo queda en su carpeta como registro y se anota una línea en
  `docs/historial.md`.
- IDs: `<PREFIJO>-NN`, con el prefijo de la app. La tarea termina en número (`USR-07`); el caso de uso, en tres letras
  (`USR-INI-SES`). Ojo: el prefijo de tarea `PRD` y el de caso de uso `PROD` son cosas distintas.
- Las tareas las escribe una persona, o Claude en claude.ai, y el estudiante las aprueba antes de pasarlas a Claude Code
  (regla M6, definida en `docs/README.md`, «Ciclo de una tarea»).

| Prefijo | App |
|---|---|
| USR | core, cuentas y seguridad |
| AUD | core, auditoría |
| MAE | maestros (incluye organización, configuración, geografía y alertas) |
| INV | inventario (y los modelos de variedad que crea INV-03) |
| PRD | produccion (y PRD-00, que crea las apps) |
| CMP | compras |
| COM | comercial |
| IOT | iot |
| CON | contabilidad |
| UI | interfaz (hoja de estilos y marco, en core) |
| DOC | documentación |

## Pendientes

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| USR-07 | Foto de perfil | core | bloqueada | Proveedor de almacenamiento; permiso para Pillow y `django-storages` (D-20) | `usuarios/USR-07-foto-perfil.md` |
| USR-09 | Seguridad de producción | core | pendiente | — | `usuarios/USR-09-seguridad-produccion.md` |
| AUD-02 | Exportar la auditoría a CSV | core | pendiente | Reglas del caso de uso, sin escribir | `auditoria/AUD-02-exportar-csv.md` |
| MAE-02c | Alerta: consulta (CU-46) y entrada «Alertas» del menú | maestros | pendiente | MAE-02b (hecha, en revisión). Archivo por escribir | — |

### Ronda «Producción 1» (D-44, D-45)

Plan completo en `docs/tareas/ronda_produccion_1.md`. «Por escribir» quiere decir que el archivo de la tarea todavía no
está en el repo: no se puede programar hasta que llegue su lote de documentación.

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|


| INV-01 | Tipos de insumo y catálogo de insumos (y los modelos de todo `inventario`) | inventario | pendiente | UI-01, NOT-01, CON-01 | `inventario/INV-01-tipos-de-insumo-y-catalogo.md` |
| INV-02 | Insumos del invernadero, existencias, ajuste de stock y vencimientos | inventario | pendiente | INV-01, UI-01 | `inventario/INV-02-insumos-del-invernadero-stock-y-vencimientos.md` |
| INV-03 | Variedades, con la creación de su semilla | inventario | pendiente | MAE-03, INV-02, UI-01, NOT-01 | `inventario/INV-03-variedades-y-semillas.md` |
| PRD-01 | Siembra: planificar, concretar, cancelar orden y bandeja del Capataz | produccion | pendiente | MAE-03, MAE-04, INV-02, INV-03, NOT-01, CON-01 (y UI-01) | `produccion/PRD-01-siembra-ordenes-y-bandeja.md` |
| PRD-02 | Transición: planificar, concretar y cancelar | produccion | pendiente | PRD-01 | `produccion/PRD-02-transicion-de-etapa.md` |
| PRD-03 | Eventos del lote: merma, aplicación de insumos, otro evento y bitácora | produccion | pendiente | PRD-02 | `produccion/PRD-03-eventos-del-lote-merma-aplicacion-bitacora.md` |
| PRD-04 | Sector fuera de servicio e Inicio del Agrónomo | produccion | pendiente | PRD-03 | `produccion/PRD-04-sector-fuera-de-servicio-e-inicio.md` |

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

## Tareas agregadas fuera de la ronda «Producción 1»

- **USR-10** (`docs/tareas/core/USR-10-envio-de-correo-publico.md`, D-54): función pública de correo de `core`. Se hace después de la ronda y antes de IOT-03.
- **IOT-NN** (módulo `iot`): se hacen **después** de PRD-04 y USR-10, no en paralelo. Sus tareas y su plan (`docs/tareas/ronda_iot_1.md`) se documentan en lotes aparte; el orden entre las personas lo fija ese plan.
