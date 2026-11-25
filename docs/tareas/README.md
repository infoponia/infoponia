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
| EST | estadisticas (app nueva, nivel 8; D-93) |

## Pendientes

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| USR-07 | Foto de perfil | core | bloqueada | Proveedor de almacenamiento; permiso para Pillow y `django-storages` (D-20) | `usuarios/USR-07-foto-perfil.md` |
| USR-09b | Topes de intentos de identificación y de pedidos de recuperación (USR-09a hizo el resto) | core | pendiente | — | `usuarios/USR-09-seguridad-produccion.md` |
| AUD-02 | Exportar la auditoría a CSV | core | pendiente | Reglas del caso de uso, sin escribir | `auditoria/AUD-02-exportar-csv.md` |
| MAE-05 | Transportista del invernadero: «Logística», agregar, trasladar y quitar (D-55) | maestros (y core) | hecha (PR #45, 21/11/2026; revisión a mano pendiente) | — (MAE-01b, MAE-02b y NOT-01, hechas). Va antes del módulo comercial | `maestros/MAE-05-transportista-del-invernadero.md` |


### Ronda «Producción 1» (D-44, D-45)

Plan completo en `docs/tareas/ronda_produccion_1.md`. «Por escribir» quiere decir que el archivo de la tarea todavía no
está en el repo: no se puede programar hasta que llegue su lote de documentación.

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| PRD-02 | Transición: planificar, concretar y cancelar | produccion | hecha (PR #53, 22/11/2026; revisión a mano pendiente) | PRD-01 | `produccion/PRD-02-transicion-de-etapa.md` |
| PRD-03 | Eventos del lote: merma, aplicación de insumos, otro evento y bitácora | produccion | hecha (PR #57, 23/11/2026; revisión a mano pendiente) | PRD-02 | `produccion/PRD-03-eventos-del-lote-merma-aplicacion-bitacora.md` |
| PRD-04 | Sector fuera de servicio e Inicio del Agrónomo | produccion | hecha (PR #58, 23/11/2026; revisión a mano pendiente) | PRD-03 | `produccion/PRD-04-sector-fuera-de-servicio-e-inicio.md` |

### Ronda «Comercial 1» (D-56, D-57)

Plan completo en `docs/tareas/ronda_comercial_1.md`. Todas dependen de MAE-05 (arriba). Va en paralelo con la del IoT y, desde
COM-02, con `produccion` completa. COM-03, COM-04 y COM-05a están partidas en subtareas, cada una con su PR (D-67, punto 2), y COM-06 y
COM-07 también (D-68, punto 1; D-69, punto 1).

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| COM-01 | App `comercial`, clientes y vehículos | comercial | hecha (PR #__, 23/11/2026; revisión a mano pendiente) | MAE-05 | `comercial/COM-01-clientes-y-vehiculos.md` |
| COM-02 | Stock maduro y compra-venta | comercial (y modelos en produccion, D-59) | hecha (PR #65, 23/11/2026) | COM-01, USR-10, PRD-04 | `comercial/COM-02-stock-maduro-y-compra-venta.md` |
| COM-03a | Suministros: pactar y consultar | comercial | hecha (PR #68, 23/11/2026) | COM-02 |`comercial/COM-03a-suministros-pactar-y-consultar.md` |
| COM-03b | Suministros: modificar, rescindir, dejar sin efecto y pre-reservar (pasos 35 y 40) | comercial (y los orígenes de alertas en maestros, D-62) | hecha (PR #__, 24/11/2026) | COM-03a, MAE-02d (DIA-01, hecha) |`comercial/COM-03b-suministros-modificar-rescindir-y-pre-reservar.md` |
| COM-04b | Cámara: asignación, vencimiento y merma en cámara (pasos 20 y 25) | comercial (y un parámetro en maestros) | hecha (PR #__, 24/11/2026) | COM-04a | `comercial/COM-04b-camara.md` | |
| COM-04c | Faltante y enlace del cliente (paso 27) | comercial (y piezas de core) | hecha (PR #79, 24/11/2026; revisión a mano pendiente) | COM-04b | `comercial/COM-04c-faltante-y-enlace-del-cliente.md` |
| COM-05a1 | Entregas: modelo, planificación automática (paso diario 50) y cancelación incluida | comercial (y `core`: acciones de auditoría) | hecha (PR #__, 24/11/2026; revisión a mano pendiente) | COM-04c, MAE-02d (INV-02, hecha) | `comercial/COM-05a1-planificacion-de-entregas.md` |
| COM-05a2 | Envasado y las entregas en el panel, las fichas y los vehículos | comercial (y la restricción de `ReservaInsumo` y el núcleo de reservas en produccion, D-66) | pendiente | COM-05a1 | `comercial/COM-05a2-envasado-y-pantallas-de-entregas.md` |
| COM-05b | Asignar transportista y cancelar la compra-venta | comercial | pendiente | COM-05a2 | `comercial/COM-05b-asignar-transportista-y-cancelar-compra-venta.md` |
| COM-06a | Ruta y concreción de entregas: iniciar y finalizar la ruta, concretar, intento fallido y discrepancia (D-68) | comercial | pendiente | COM-05b | `comercial/COM-06a-ruta-y-concrecion.md` |
| COM-06b | Confirmación del cliente: el enlace, las quejas y la entrega no reconocida (D-68) | comercial | pendiente | COM-06a | `comercial/COM-06b-confirmacion-del-cliente.md` |
| COM-07a | Solicitudes de revisión: evaluar, resolver, anular y consultar (D-69) | comercial | pendiente | COM-06b (y la sección 11 de COM-04a) | `comercial/COM-07a-solicitudes-de-revision.md` |
| COM-07b | Resolución del suministro por incumplimientos (paso diario 33) | comercial | pendiente | COM-07a | `comercial/COM-07b-resolucion-del-suministro.md` |
| COM-08a | Cobro de suministros y mora (paso diario 30) (D-94) | comercial | pendiente | COM-07b | `comercial/COM-08a-cobro-y-mora.md` |
| COM-08b | Anular un cobro y cobrar lo entregado al cancelar una compra-venta (D-94) | comercial | pendiente | COM-08a | `comercial/COM-08b-anular-cobro-y-cobro-al-cancelar.md` |
| COM-08c | Estadísticas comerciales y «Resultados del mes en curso» (D-94) | comercial | pendiente | COM-08b (o en paralelo con ella) | `comercial/COM-08c-estadisticas.md` |

### Ronda «IoT 1» (D-70 a D-79)

Plan completo en `docs/tareas/ronda_iot_1.md`. Va en paralelo con «Comercial 1»; IOT-01 e IOT-02, también con «Producción 1» (aprobado
por el estudiante el 21/11/2026). Cada tarea espera a las de producción que necesita (plan, sección 2).

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| IOT-05 | Comandos: emitir, retirar, resolver y cancelar | iot (y un valor en produccion) | hecha (PR #__, 23/11/2026; revisión a mano pendiente) | IOT-03, PRD-01 | `iot/IOT-05-comandos.md` |

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

### Ronda «Contabilidad 1» (D-84 a D-86; reabre casos de uso en CON-04)

Plan completo en `docs/tareas/ronda_contabilidad_1.md`. **Es la primera de las tres rondas nuevas** (el núcleo contable va primero, A0 P1(a)):
compras y estadísticas dependen de ella. Las tareas están en orden de implementación.

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| CON-03b | Asientos manuales y contraasientos | contabilidad | pendiente | CON-03a | `contabilidad/CON-03b-asientos-manuales-y-contraasientos.md` |

### Ronda «Compras 1» (D-87 a D-91)

Plan completo en `docs/tareas/ronda_compras_1.md`. CMP-01 a CMP-03 no esperan a la contabilidad; CMP-04 espera a CON-02 y CMP-05, además, a USR-11.

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| CMP-04 | Recepción y cierre con faltante (con asiento) | compras (y el ingreso en inventario; `contabilidad` y `core`: un tipo de origen y las acciones de auditoría) | hecha (PR #__, 24/11/2026; revisión a mano pendiente) | CMP-03, CON-02 | `compras/CMP-04-recepcion-y-cierre-con-faltante.md` |
| CMP-05 | Pago a proveedores (con asiento) | compras | pendiente | CMP-04, USR-11 (hecha), CON-02 | `compras/CMP-05-pago-a-proveedores.md` |
| CMP-06 | Corrección de recepción y reclamos | compras (y un tipo en inventario) | pendiente | CMP-05 | `compras/CMP-06-correccion-de-recepcion-y-reclamos.md` |

### Ronda «Contabilidad 2» (D-92; reaperturas y lote existente)

Plan completo en `docs/tareas/ronda_contabilidad_2.md`. CON-04b y PRD-05 van apenas esté CON-02; CON-04c y CON-04d esperan a Comercial (y se
achican si cada tarea de Comercial ya trae su asiento, D-92 punto 9).

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| CON-04b | Asientos de los ajustes de stock | inventario | pendiente | CON-02 | `contabilidad/CON-04b-asientos-de-inventario.md` |
| PRD-05 | Registrar Lote Existente | produccion | pendiente | CON-02, PRD-03 (hecha) | `produccion/PRD-05-registrar-lote-existente.md` |
| CON-04a | Asientos de producción (reapertura) | produccion | pendiente | CON-02 (PRD-04, hecha) | `contabilidad/CON-04a-asientos-de-produccion.md` |
| CON-04c | Asientos de cosecha, cámara y entregas | comercial, produccion | pendiente | CON-02, COM-04a, COM-04b, COM-06a | `contabilidad/CON-04c-asientos-de-cosecha-camara-y-entregas.md` |
| CON-04d | Asientos de cobros, indemnizaciones y multas | comercial | pendiente | CON-02, USR-11 (hecha), COM-06b a COM-08b | `contabilidad/CON-04d-asientos-de-cobros-indemnizaciones-y-multas.md` |

### Ronda «Estadísticas 1» (D-93)

Plan completo en `docs/tareas/ronda_estadisticas_1.md`. Va última; EST-03 espera a COM-08c.

| ID | Título | App | Estado | Depende de / espera | Archivo |
|---|---|---|---|---|---|
| EST-01 | App `estadisticas` y estadísticas de producción | estadisticas | pendiente | PRD-03 (hecha); mejor después de CON-04a | `estadisticas/EST-01-app-y-estadisticas-de-produccion.md` |
| EST-02 | Estadísticas consolidadas del Gerente | estadisticas | pendiente | EST-01, CON-03a, CMP-06 | `estadisticas/EST-02-estadisticas-consolidadas.md` |
| EST-03 | Lo comercial dentro de las consolidadas | estadisticas | pendiente | EST-02, COM-08c | `estadisticas/EST-03-estadisticas-comerciales-en-las-consolidadas.md` |
