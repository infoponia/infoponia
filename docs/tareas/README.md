# Tareas — InfoPonia

Índice de las tareas pendientes de todas las apps. Se lee al elegir la próxima tarea. Cada tarea es un archivo en
`docs/tareas/<app>/<ID>-<nombre>.md`, escrito con `_plantilla.md`.

**Una tarea es un bloque funcional** (D-44): los casos de uso que comparten modelo, servicios y pantallas, de 4 a 10 casos
de uso, en una sola sesión de Claude Code y un solo PR. La documentación de toda una ronda está completa en el repo antes
de programar su primera tarea. Los planes de ronda (tareas, orden, casos de uso y pantallas) son
`docs/tareas/ronda_produccion_1.md`, `docs/tareas/ronda_comercial_1.md` y `docs/tareas/ronda_iot_1.md`. Para trabajar de a dos sin pisarse: `docs/patrones/trabajo_en_paralelo.md`.

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
| DIA | proceso diario (en core; D-56) |

## Pendientes

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| USR-07 | Foto de perfil | core | bloqueada | Proveedor de almacenamiento; permiso para Pillow y `django-storages` (D-20) | `usuarios/USR-07-foto-perfil.md` |
| USR-09 | Seguridad de producción | core | pendiente | — | `usuarios/USR-09-seguridad-produccion.md` |
| AUD-02 | Exportar la auditoría a CSV | core | pendiente | Reglas del caso de uso, sin escribir | `auditoria/AUD-02-exportar-csv.md` |
| MAE-05 | Transportista del invernadero: «Logística», agregar, trasladar y quitar (D-55) | maestros (y core) | hecha (PR #45, 21/11/2026; revisión a mano pendiente) | — (MAE-01b, MAE-02b y NOT-01, hechas). Va antes del módulo comercial | `maestros/MAE-05-transportista-del-invernadero.md` |
| MAE-02d | Enlace de cada alerta a la pantalla de su origen, ruta `alertas:ir` y filtro por varios tipos (D-62, tercera enmienda) | maestros | pendiente | MAE-02c (hecha). La esperan COM-03b e IOT-04 | `maestros/MAE-02d-enlace-de-alertas.md` |

### Ronda «Producción 1» (D-44, D-45)

Plan completo en `docs/tareas/ronda_produccion_1.md`. «Por escribir» quiere decir que el archivo de la tarea todavía no
está en el repo: no se puede programar hasta que llegue su lote de documentación.

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| INV-03 | Variedades, con la creación de su semilla | inventario | hecha (PR #48, 22/11/2026; revisión a mano pendiente) | MAE-03, INV-02, UI-01, NOT-01 | `inventario/INV-03-variedades-y-semillas.md` |
| PRD-01 | Siembra: planificar, concretar, cancelar orden y bandeja del Capataz (y los tipos de orden futuros, D-67) | produccion | pendiente | MAE-03, MAE-04, INV-02, INV-03, NOT-01, CON-01 (y UI-01) | `produccion/PRD-01-siembra-ordenes-y-bandeja.md` |
| PRD-02 | Transición: planificar, concretar y cancelar | produccion | pendiente | PRD-01 | `produccion/PRD-02-transicion-de-etapa.md` |
| PRD-03 | Eventos del lote: merma, aplicación de insumos, otro evento y bitácora | produccion | pendiente | PRD-02 | `produccion/PRD-03-eventos-del-lote-merma-aplicacion-bitacora.md` |
| PRD-04 | Sector fuera de servicio e Inicio del Agrónomo | produccion | pendiente | PRD-03 | `produccion/PRD-04-sector-fuera-de-servicio-e-inicio.md` |

### Ronda «Comercial 1» (D-56, D-57)

Plan completo en `docs/tareas/ronda_comercial_1.md`. Todas dependen de MAE-05 (arriba). Va en paralelo con la del IoT y, desde
COM-02, con `produccion` completa. COM-03, COM-04 y COM-05a están partidas en subtareas, cada una con su PR (D-67, punto 2), y COM-06 y
COM-07 también (D-68, punto 1; D-69, punto 1).

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| COM-01 | App `comercial`, clientes y vehículos | comercial | pendiente | MAE-05 | `comercial/COM-01-clientes-y-vehiculos.md` |
| COM-02 | Stock maduro y compra-venta | comercial (y modelos en produccion, D-59) | pendiente | COM-01, USR-10, PRD-04 | `comercial/COM-02-stock-maduro-y-compra-venta.md` |
| COM-03a | Suministros: pactar y consultar | comercial | pendiente | COM-02 | `comercial/COM-03a-suministros-pactar-y-consultar.md` |
| COM-03b | Suministros: modificar, rescindir, dejar sin efecto y pre-reservar (pasos 35 y 40) | comercial (y los orígenes de alertas en maestros, D-62) | pendiente | COM-03a, MAE-02d (DIA-01, hecha) | `comercial/COM-03b-suministros-modificar-rescindir-y-pre-reservar.md` |
| COM-04a | Cosechas: núcleo en produccion; planificar, modificar, concretar y cancelar | comercial y produccion (todo el núcleo, D-64, también el de la entrega, D-68, y la bitácora de las solicitudes, D-69) | pendiente | COM-03b | `comercial/COM-04a-cosechas.md` |
| COM-04b | Cámara: asignación, vencimiento y merma en cámara (pasos 20 y 25) | comercial (y un parámetro en maestros) | pendiente | COM-04a | `comercial/COM-04b-camara.md` |
| COM-04c | Faltante y enlace del cliente (paso 27) | comercial (y piezas de core) | pendiente | COM-04b | `comercial/COM-04c-faltante-y-enlace-del-cliente.md` |
| COM-05a1 | Entregas: modelo, planificación automática (paso diario 50) y cancelación incluida | comercial | pendiente | COM-04c, MAE-02d (INV-02, hecha) | `comercial/COM-05a1-planificacion-de-entregas.md` |
| COM-05a2 | Envasado y las entregas en el panel, las fichas y los vehículos | comercial (y la restricción de `ReservaInsumo` y el núcleo de reservas en produccion, D-66) | pendiente | COM-05a1 | `comercial/COM-05a2-envasado-y-pantallas-de-entregas.md` |
| COM-05b | Asignar transportista y cancelar la compra-venta | comercial | pendiente | COM-05a2 | `comercial/COM-05b-asignar-transportista-y-cancelar-compra-venta.md` |
| COM-06a | Ruta y concreción de entregas: iniciar y finalizar la ruta, concretar, intento fallido y discrepancia (D-68) | comercial | pendiente | COM-05b | `comercial/COM-06a-ruta-y-concrecion.md` |
| COM-06b | Confirmación del cliente: el enlace, las quejas y la entrega no reconocida (D-68) | comercial | pendiente | COM-06a | `comercial/COM-06b-confirmacion-del-cliente.md` |
| COM-07a | Solicitudes de revisión: evaluar, resolver, anular y consultar (D-69) | comercial | pendiente | COM-06b (y la sección 11 de COM-04a) | `comercial/COM-07a-solicitudes-de-revision.md` |
| COM-07b | Resolución del suministro por incumplimientos (paso diario 33) | comercial | pendiente | COM-07a | `comercial/COM-07b-resolucion-del-suministro.md` |
| COM-08 | Cobranza y estadísticas | comercial | por escribir | COM-07b; lote C8 | — |

### Ronda «IoT 1» (D-70 a D-73)

Plan completo en `docs/tareas/ronda_iot_1.md`. Va en paralelo con «Comercial 1»; IOT-01 e IOT-02, también con «Producción 1» (aprobado
por el estudiante el 21/11/2026). Cada tarea espera a las de producción que necesita (plan, sección 2).

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| IOT-02 | Sistema IoT y hardware | iot (y punto de extensión en maestros) | pendiente | IOT-01 | `iot/IOT-02-sistema-iot-y-hardware.md` |
| IOT-03 | API del nodo I: token, lecturas, estados, modo y anuncio | iot | pendiente | IOT-02, INV-03 | `iot/IOT-03-api-del-nodo-lecturas.md` |
| IOT-04 | Revisión periódica, panel de monitoreo y configuración IoT | iot (y la configuración de maestros) | pendiente | IOT-03, USR-10, MAE-02d, MAE-04 | `iot/IOT-04-revision-panel-y-configuracion.md` |
| IOT-05 | Comandos: emitir, retirar, resolver y cancelar | iot (y un valor en produccion) | pendiente | IOT-03, PRD-01 | `iot/IOT-05-comandos.md` |
| IOT-06 | Reglas de actuación y ciclo de vida del sistema y del hardware | iot | pendiente | IOT-05 | `iot/IOT-06-reglas-y-ciclo-de-vida.md` |
| IOT-07 | Orden de mantenimiento automática, su cancelación y el traspaso del Técnico | iot (y migración en produccion) | pendiente | IOT-06, PRD-01 | `iot/IOT-07-orden-de-mantenimiento.md` |

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

- **USR-10** (`docs/tareas/core/USR-10-envio-de-correo-publico.md`, D-54): función pública de correo de `core`. Se hace después de la ronda y antes de COM-02 y de IOT-04 (el correo del IoT lo manda la revisión periódica, D-71).
- **IOT-01 a IOT-07** (módulo `iot`): ver «Ronda «IoT 1»» arriba y `docs/tareas/ronda_iot_1.md`.
