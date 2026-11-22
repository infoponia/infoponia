# Ronda «IoT 1» — plan completo

Plan de la ronda que construye el módulo IoT: tipos de actuador, sistema IoT y hardware, la API con el nodo central (lecturas, estados,
modo, anuncio y comandos), la revisión periódica, el panel de monitoreo, los comandos, las reglas de actuación y la orden de mantenimiento
automática. Se programa sobre el prototipo `docs/prototipos/iot/` (lo trae el lote I1). Modelo: `docs/modelo/iot.md` (ronda 23 aplicada).
Decisiones de la ronda: **D-70** (API, token y Node-RED), **D-71** (revisión periódica y correo), **D-72** (el modelo en el código) y **D-73**
(mantenimiento). Criterio de documentación y tamaño de las tareas: **D-44**. Las pantallas son una referencia (**D-61**). Este archivo lo lee
la persona que planifica; Claude Code lo abre solo para completar la fila de su tarea al cerrar (regla M3).

La ronda va **en paralelo con «Comercial 1»** (`docs/tareas/ronda_comercial_1.md`) y depende de algunas tareas de «Producción 1»
(sección 2). IOT-01 e IOT-02 pueden programarse **en paralelo con producción** (aprobado por el estudiante el 21/11/2026).

## 1. Tareas

Cada tarea es un bloque funcional: una sesión de Claude Code y un PR (D-44). «Por escribir» = su archivo llega en el lote indicado.

| ID | Tarea | App | Casos de uso | Depende de | Lote |
|---|---|---|---|---|---|
| IOT-01 | App `iot`, todos sus modelos, catálogo de capacidades, tipos de actuador y los parámetros IoT de la configuración | iot (y migración en maestros) | IOT-ALT-TAC, IOT-MOD-TAC, IOT-BAJ-TAC, IOT-CNS-TAC | MAE-03, MAE-04, INV-01 (mergeadas), UI-01 | I1 |
| IOT-02 | Sistema IoT y hardware: registrar, modificar, regenerar el token, alta, modificación y consulta de equipos; conexión con `maestros` | iot (y punto de extensión en maestros) | IOT-REG-SIS, IOT-MOD-SIS, IOT-ALT-HDW, IOT-MOD-HDW, IOT-CNS-HDW | IOT-01, MAE-02b, NOT-01 | I1 |
| IOT-03 | API del nodo I: token, lecturas, estados, modo y anuncio; alertas de lecturas; flujo de Node-RED de lecturas | iot | IOT-ENT-INF (sin la extensión \*b ni las 6a a 6d) | IOT-02, INV-03 (`umbral_efectivo`) | I2a |
| IOT-04 | Revisión periódica (inactividad, resúmenes, fotoperíodo, retención y correos) y panel de monitoreo; sección «Módulo IoT» de la configuración | iot (y la pantalla de configuración de maestros) | IOT-ENT-INF (extensión \*b), IOT-CNS-LEC, ADM-MOD-CFG (sección IoT) | IOT-03, USR-10, MAE-02d, MAE-04 | I2b |
| IOT-05 | Comandos: emitir, retirar, resolver con reintentos y cancelar; bitácora de comandos; flujo de Node-RED de comandos | iot | IOT-EMT-CMD, IOT-RSV-CMD (sin la orden de mantenimiento), IOT-CNL-CMD | IOT-03, PRD-01 (`Bitacora`) | I3 |
| IOT-06 | Reglas de actuación y su disparo automático; desactivar, activar y dar de baja el sistema; baja de equipos | iot | IOT-ALT-RGL, IOT-MOD-RGL, IOT-BAJ-RGL, IOT-CNS-RGL, IOT-ENT-INF (extensiones 6a a 6d), IOT-DSC-SIS, IOT-ACT-SIS, IOT-BAJ-SIS, IOT-BAJ-HDW | IOT-05 | I3 |
| IOT-07 | Orden de mantenimiento automática, su cancelación y el traspaso del Técnico | iot (y migración en produccion) | IOT-RSV-CMD (extensiones 4b.4, 4b.4a y 4b.4b), IOT-MOD-HDW (regla 8), la precondición d de IOT-BAJ-HDW e IOT-BAJ-SIS, PROD-CNL-ORD (para el mantenimiento), el traspaso del Técnico; D-73, D-79 | IOT-06, PRD-01 | I4 |

Son 22 casos de uso más la sección IoT de ADM-MOD-CFG. IOT-ENT-INF se reparte entre IOT-03, IOT-04 e IOT-06 (es el más grande: cada tarea
lee solo sus extensiones). La numeración reemplaza a la del 20/11/2026: lo que D-53 y `docs/disparadores.md` llamaban «IOT-05»
(mantenimiento) es **IOT-07**, y lo que D-54 llamaba «IOT-03» (el correo) es **IOT-04** (D-73).

**Por qué este corte** (D-44 y el riesgo de arquitectura del Proceso Unificado: lo más incierto, primero):
- **IOT-01 crea el esquema entero** (D-72, punto 6) junto con el ABM más simple, que no depende de nada: así las demás tareas no cambian
  modelos (salvo `RegistroComando` y `MantenimientoTecnico`, que crean IOT-05 e IOT-07 porque sus padres son de `produccion`) y la única migración de `maestros` del IoT sale antes que la de COM-04.
- **IOT-03 es el primer hito demostrable**: Node-RED manda lecturas e InfoPonia las guarda y genera alertas. Valida la integración antes de
  construir encima.
- **La baja y la desactivación van en IOT-06**, después de los comandos y las reglas, porque cancelan comandos pendientes y desactivan
  reglas (IOT-DSC-SIS, IOT-BAJ-SIS, IOT-BAJ-HDW): escritas antes, quedarían ramas sin probar.
- **El mantenimiento va último** porque necesita `OrdenTrabajo` (PRD-01) y es lo que menos pesa en la defensa (D-73).

## 2. Orden, paralelismo y dependencias de producción

### Qué necesita cada tarea de producción y de comercial

| Tarea | Necesita | Por qué | Mientras no esté |
|---|---|---|---|
| IOT-01 | MAE-03 (`SectorProduccion`), INV-01 (`Insumo`), MAE-04 (`ConfiguracionOperativa`) | FK de `Hardware` y los 14 parámetros | No se programa (las tres están en revisión al 21/11/2026) |
| IOT-02 | INV-01 (categoría `repuestos_de_hardware`), MAE-02b, NOT-01 | Insumo del equipo (R072), alerta del Técnico, aviso al Técnico | — (hechas) |
| IOT-03 | INV-03 (`umbral_efectivo`, `docs/api/variedades.md`) | Comparar lecturas con el umbral | Sin PRD-01, `variedades_presentes` no tiene registrante: todo invernadero queda «sin umbral efectivo» (extensión 5c), y las pruebas usan `variedades_presentes_de_prueba` |
| IOT-04 | USR-10 (`core.correo.enviar_correo`, D-54), MAE-02d (`tipos` en la consulta de alertas de MAE-02c, `enlaces_de_alertas` y `alertas:ir`, D-62, tercera enmienda) | Correos de la revisión; el panel reutiliza la consulta de alertas | No se programa |
| IOT-05 | PRD-01 (`produccion.Bitacora`) | `RegistroComando` es hija de `Bitacora` | No se programa |
| IOT-07 | PRD-01 (`OrdenTrabajo`, `cancelar_orden_incluida`, `registrar_traspaso` del Capataz) | `MantenimientoTecnico` es hija de `OrdenTrabajo` | No se programa |

PRD-02 a PRD-04 y las tareas COM no hacen falta para ninguna tarea del IoT. El sector fuera de servicio (PRD-04) solo cambia el estado del
sector, que ya existe desde MAE-03: el IoT lo lee directamente.

### Diagrama

```
MAE-03, MAE-04, INV-01 ──► IOT-01 ──► IOT-02 ──► IOT-03 ──► IOT-04
                                                   │          ▲
INV-03 ────────────────────────────────────────────┘          │ USR-10, MAE-02d
                                                   └──► IOT-05 ──► IOT-06 ──► IOT-07
PRD-01 ────────────────────────────────────────────────────►┘                 ▲
PRD-01 ───────────────────────────────────────────────────────────────────────┘
```

- **Pueden arrancar en cuanto se mergeen MAE-03, MAE-04 e INV-01:** IOT-01 y, después, IOT-02, en paralelo con «Producción 1».
- **IOT-04 e IOT-05 son independientes entre sí** (las dos salen de IOT-03): se pueden repartir entre las dos personas si una espera a
  USR-10 o a MAE-02d y la otra a PRD-01.
- **Con comercial:** las dos rondas comparten la pantalla de configuración, el menú, el panel de control y la campana
  (`docs/tareas/ronda_comercial_1.md`, sección 5). La regla para no pisarse está en `docs/patrones/trabajo_en_paralelo.md`.

## 3. Casos de uso de la ronda → tarea

Fuentes: «CU extendidos» (Lote 1 v5.6, Lote 2 v3, Lote 3 v3.2 y Lote 4 v2.4 del IoT, pegados el 20/11/2026). Los extractos van en
`docs/casos_de_uso/iot/` y llegan con el lote de su tarea.

| Código | Caso de uso | Actores | Tarea | Extracto (lote) |
|---|---|---|---|---|
| IOT-ALT-TAC, IOT-MOD-TAC, IOT-BAJ-TAC, IOT-CNS-TAC | ABM de tipos de actuador | Gerente (el Agrónomo consulta) | IOT-01 | `tipos_de_actuador.md` (I1) |
| IOT-REG-SIS, IOT-MOD-SIS | Registrar y modificar el sistema IoT | Agrónomo y Gerente (alcance, MD-98) | IOT-02 | `sistema_iot.md` (I1) |
| IOT-DSC-SIS, IOT-ACT-SIS, IOT-BAJ-SIS | Desactivar, activar y dar de baja el sistema IoT | Agrónomo y Gerente | IOT-06 | `sistema_iot.md` (I1) |
| IOT-ALT-HDW, IOT-MOD-HDW, IOT-CNS-HDW | Alta, modificación y consulta de hardware | Agrónomo y Gerente | IOT-02 | `hardware.md` (I1) |
| IOT-BAJ-HDW | Baja de hardware | Agrónomo y Gerente | IOT-06 | `hardware.md` (I1) |
| IOT-ENT-INF | Entregar información | Sistema IoT; InfoPonia (revisión periódica) | IOT-03 (flujo principal y extensiones \*a, 1a a 1c, 3a a 3f, 4a a 4c, 5a a 5g), IOT-04 (\*b), IOT-06 (6a a 6d) | `entregar_informacion.md` (I2a; la parte de \*b, I2b) |
| IOT-CNS-LEC | Consultar lecturas (panel de monitoreo) | Agrónomo y Gerente | IOT-04 | `consultar_lecturas.md` (I2b) |
| ADM-MOD-CFG (sección «Módulo IoT») | Modificar la configuración operativa | Gerente (el Agrónomo consulta) | IOT-04 | `maestros/configuracion.md`, sección nueva (I2b) |
| IOT-EMT-CMD | Emitir comando | Agrónomo y Gerente; InfoPonia (regla) | IOT-05 | `emitir_comando.md` (I3) |
| IOT-RSV-CMD | Resolver comando | Sistema IoT | IOT-05; IOT-07 (4b.4) | `resolver_comando.md` (I3); la parte de IOT-07, `mantenimiento_automatico.md` (I4) |
| IOT-CNL-CMD | Cancelar comando | Agrónomo y Gerente | IOT-05 | `cancelar_comando.md` (I3) |
| IOT-ALT-RGL, IOT-MOD-RGL, IOT-BAJ-RGL, IOT-CNS-RGL | ABM de reglas de actuación | Agrónomo y Gerente | IOT-06 | `reglas_de_actuacion.md` (I3) |
| PROD-CNL-ORD (para el mantenimiento automático) | Cancelar orden, desde la ficha del equipo | Agrónomo y Gerente (alcance del IoT, D-79) | IOT-07 | `mantenimiento_automatico.md` (I4) y `docs/casos_de_uso/produccion/cancelar_orden.md`, sección nueva |

Reemplazan a los casos preliminares CU-40 a CU-43, CU-46 (solo la parte del IoT), CU-82 a CU-85 y CU-90 a CU-97 de la «Documentación para
la IA»; CU-44 y CU-45 se eliminan (el umbral sale de las variedades y la calibración se edita en IOT-MOD-HDW). CU-05 y CU-06 (planificar y
concretar el mantenimiento) son de la etapa 2 (D-73).

## 4. Pantallas del prototipo → tarea

Prototipo «InfoPonia IoT» v8.5 (`docs/prototipos/iot/iot.html`, un solo archivo de 835 líneas; se lee **por función**, regla L3). Su
`README.md` (lote I1) mapea cada pantalla con su función y lista lo que es «solo prototipo».

| Pantalla | Función | Tarea |
|---|---|---|
| Barra de contexto (invernadero) y pestañas del módulo | `ctxBar`, `NAV`, `render` | IOT-01 (el marco), cada tarea su pestaña |
| Tipos de actuador y catálogo de capacidades | `tipos`, `cmdOpts`, `unidOpts`, `modalHtml` (`tbaj`) | IOT-01 |
| Sistema IoT (ficha, formulario, token) | `sistema`, `modalHtml` (`token`, `regen`) | IOT-02 |
| Sistema IoT: desconectar, activar, dar de baja | `sistema`, `modalHtml` (`desc`, `baj` del sistema) | IOT-06 |
| Hardware (lista, ficha, formulario, reactivar) | `hardware`, `recompat`, `bajaDe`, `modalHtml` (`rebaja`, `react`) | IOT-02 |
| Hardware: dar de baja | `modalHtml` (`baj:<id>`) | IOT-06 |
| Monitoreo | `monitoreo`, `sensCard`, `spark`, `sensorState`, `actState` | IOT-04 |
| Configuración operativa · Módulo IoT | `config`, `CFGP` | IOT-04 |
| Comandos | `comandos`, `cmdForm`, `modalHtml` (`ccan`) | IOT-05 |
| Reglas de actuación | `reglas`, `rglText`, `rglTags`, `modalHtml` (`rbaj`) | IOT-06 |

**Solo prototipo** (detalle en el README, lote I1): el selector «Ver como», las cajas «SOLO PROTOTIPO» que simulan al nodo, el refresco con
valores al azar, la cancelación automática de la orden al volver a activar un equipo (manda IOT-MOD-HDW, regla 8, D-73), el borrado físico de
un tipo de actuador (la baja es lógica) y la ruta `docs/api_nodo.md` de la guía (es `docs/api/nodo/`).

## 5. Puntos compartidos con lo existente y con comercial

Siguen la sección 5 de `docs/tareas/ronda_comercial_1.md` (columna «Qué cuidar con el IoT»). Lo propio del IoT:

| Punto | Qué hace el IoT | Tarea |
|---|---|---|
| Menú | Entrada «IoT» (Gerente y Agrónomo) con `core.menu.registrar_entrada`, `despues_de` = Producción. Queda después de «Comercial» porque `iot` está más abajo en `INSTALLED_APPS` | IOT-01 |
| Configuración operativa | Una migración en `maestros` con los 14 parámetros (IOT-01) y la sección «Módulo IoT» de la pantalla (IOT-04). COM-04b suma `dias_aviso_vencimiento_camara` en otra migración: la segunda en mergearse ajusta su dependencia (`trabajo_en_paralelo.md`, «Migraciones») | IOT-01, IOT-04 |
| Ficha del invernadero | El estado del sistema IoT en «Ubicación» (activo, desconectado o «sin registrar» con el enlace a registrarlo). Hoy `Invernadero.tiene_sistema_iot()` devuelve `False`: IOT-02 suma un punto de extensión en `maestros/extensiones.py` para el estado del IoT y lo registra | IOT-02 |
| Sectores | Registrantes de `registrar_impedimento_de_baja_de_sector` (`hardware_activo`) y `registrar_contenido_de_sector` (hardware) | IOT-02 |
| Baja del invernadero | Precondición h de PROD-BAJ-INV con `registrar_impedimento_de_baja` (sistema IoT no dado de baja) | IOT-02 |
| Alerta del Técnico | `sincronizar_alertas_de_personal` al registrar y al dar de baja el sistema (regla 3 de 8.22) | IOT-02, IOT-06 |
| Campana y alertas | 11 tipos registrados en `IotConfig.ready()` (`docs/modelo/iot.md`) y su enlace con `registrar_enlace_de_alerta` (D-62) a la ficha del equipo o al panel | IOT-01 (tipos), IOT-04 (enlaces) |
| Panel de control | Ninguna sección en esta ronda | — |
| Proceso diario | No lo usa (D-56, punto 6): su revisión es `revision_iot` (D-71) | IOT-04 |
| Traspaso del Técnico | Registrante de `registrar_traspaso` para el rol Técnico (las órdenes de mantenimiento a realizar) | IOT-07 |

## 6. Fuera de la ronda

- **Planificar y Concretar Mantenimiento técnico** (CU-05 y CU-06): etapa 2. La orden automática solo se cancela (D-73).
- **El cron job** de la revisión periódica: disparador «Cuando se arme el cron único» (D-56, D-71).
- **pH, conductividad y dosificación de nutrientes** (D1 del análisis): mejora futura. La medición de luz en PPFD, también.
- **MQTT directo**: InfoPonia no se conecta a un broker; lo hace el agente puente (Node-RED) del lado del cliente (D-70).
- **Una sección del IoT en el panel de control** y el historial de alertas resueltas.

## 7. Documentación por lotes (D-44)

Cada lote es el anterior más lo nuevo (zip acumulativo sobre `main`, junto con los lotes de comercial). El estudiante valida cada uno antes de
programar sus tareas (M6).

| Lote | Contenido | Estado |
|---|---|---|
| I0 | Este plan; D-70 a D-73 (reservadas hasta D-79); `docs/modelo/iot.md` con la ronda 23 aplicada y los ajustes en `maestros.md`, `produccion.md` y `api/alertas.md`; el umbral efectivo en una sola función (`docs/api/variedades.md`, INV-03, PRD-01); filas de las tareas, disparadores y temas abiertos; la fusión con el cierre de INV-02 | validado (21/11/2026) |
| I1 | IOT-01 e IOT-02: archivos de tarea; extractos `tipos_de_actuador.md`, `sistema_iot.md` y `hardware.md`; `docs/prototipos/iot/` con su README; datos de migración (catálogo y tipos iniciales); el punto de extensión del estado del IoT en `api/extensiones_de_maestros.md`; la sección «Cuando existan actuadores, comandos y reglas del IoT» de `disparadores.md`; D-72 vigente | entregado, a validar |
| I2a | IOT-03: el contrato `docs/api/nodo/` v1 (`README.md` con la guía del nodo, `mensajes.md`, `respuestas_y_errores.md` con el token, los límites, los códigos HTTP y los motivos de rechazo, y `ejemplos/*.json`); `docs/api/nodo/node-red/` (guía y flujo de lecturas, estados, modo y anuncio); extracto `entregar_informacion.md` completo, con las partes de IOT-03 aplicadas y la corrección de «al generarse» (D-71); tarea IOT-03; D-74 (contrato, vigente) y D-75 (interpretaciones, validada el 22/11/2026); índice único de `Telemetria` en el modelo y en IOT-01. Partido de I2 por el estudiante el 21/11/2026 | entregado; D-75 validada (22/11/2026) |
| I2b | IOT-04: la sección «La revisión periódica» en `entregar_informacion.md` (\*b y el correo); extracto `consultar_lecturas.md` (IOT-CNS-LEC, con los enlaces de las alertas); sección «Módulo IoT» de `maestros/configuracion.md` (ADM-MOD-CFG, reglas 2b a 7b); tarea IOT-04; D-76 (validada el 22/11/2026) y `AlertaIot.ultimo_mensaje_en`; D-75 pasa a vigente; correcciones de IOT-03 (`login_not_required`); los cambios de MAE-05 en `main` integrados al acumulativo | entregado; D-76 validada (22/11/2026) |
| I3 | IOT-05 e IOT-06: el contrato de comandos (`docs/api/nodo/mensajes.md`, secciones 5 y 6; errores y ejemplos; la guía, sección 10); `docs/api/nodo/node-red/flujo_comandos.json` y su guía; `docs/api/nodo/escenarios.md` (guion de la defensa); extractos `emitir_comando.md`, `resolver_comando.md` (con la corrección de 4b.3, D-71), `cancelar_comando.md` y `reglas_de_actuacion.md`; la sección «Reglas de actuación» en `entregar_informacion.md`; tareas IOT-05 e IOT-06; D-77 (vigente) y D-78 (validada el 22/11/2026); la PR #46 integrada al acumulativo, con la MAE-02c de `main` unida a D-62 (segunda enmienda); D-76 pasa a vigente | entregado, a validar |
| I4 | IOT-07: extracto `mantenimiento_automatico.md`, tarea IOT-07, D-79 (puntos 1 a 4 elegidos por el estudiante; 5 a 9 a validar), la sección del IoT en `docs/casos_de_uso/produccion/cancelar_orden.md`, los escenarios 7, 15 y 16; la revisión final de toda la ronda (`LEEME_LOTE_I4.md`, sección 3) con sus correcciones | entregado, a validar |

Un lote se programa recién cuando él y los anteriores están entregados y validados. IOT-01 e IOT-02 (lote I1) pueden programarse mientras se
escriben los siguientes.

## 8. Decisiones tomadas o por confirmar

| Tema | Decisión o propuesta de trabajo | Lote |
|---|---|---|
| Numeración de decisiones | El IoT usa **D-70 a D-79** (D-66 a D-69 quedaron reservadas para comercial en el lote C4) | I0 |
| La ronda 23 rige en el repo | MD-98 a MD-113 están «decididos sin aplicar»: el extracto los aplica, como los demás extractos con sus MD pendientes | I0 |
| Histéresis | Dos parámetros de temperatura: ambiente y solución (estudiante, 21/11/2026; D-72 punto 7) | I0 |
| Umbral efectivo | Una sola función en `inventario` (`umbral_efectivo`), que usan PRD-01 y el IoT (21/11/2026) | I0 |
| Mantenimiento | Solo la orden automática; se cierra cancelándola (D-73) | I0 |
| Largos de texto que los casos de uso no fijan | Nombres de tipo 60, de acción 40, de nodo 60, modelo y número de serie 60, descripciones y resultados 300 (`docs/modelo/iot.md`) | I0 |
| Límite de mensajes de la API | 120 pedidos por minuto, 256 KB y 500 elementos por pedido (D-70, punto 5); fijados sin cambios en el contrato v1 (`docs/api/nodo/respuestas_y_errores.md`, sección 2) | I2a |
| Estado del IoT en `maestros` | Punto `registrar_estado_iot(estados, url_de_registro)`, un solo registrante (`docs/api/extensiones_de_maestros.md`) | I1 |
| Token en pantalla | Se renderiza en la respuesta al POST, sin redirigir, con `no-store` (`sistema_iot.md`) | I1 |
| Contrato del nodo | Lecturas en lote, rechazos en tres niveles, ritmo de referencia, fechas con zona e idempotencia por `(sensor, medida_en)` (D-74, elegido por el estudiante el 21/11/2026); formato, token, códigos y motivos en `docs/api/nodo/` | I2a |
| Lo que IOT-ENT-INF no resuelve | Siete interpretaciones para IOT-03 (D-75, validada el 22/11/2026) | I2a |
| Contrato de comandos | Retiro de todos los disponibles, resultado por comando, repetido como `ya_resuelto` y memoria de 24 h en el nodo (D-77, elegido por el estudiante el 22/11/2026) | I3 |
| Lo que los casos de uso de comandos y reglas no resuelven | Vencimientos, «sin señal», bitácora, «lo explica un comando», rechazo y anuncio, cancelable, tiempo mínimo, máquina de estados de una regla, textos, bloqueos (D-78, validada el 22/11/2026) | I3 |
| La orden de mantenimiento automática | Se cancela solo desde la ficha del equipo, con el alcance del IoT; sufijos de la alerta; aviso y sección del Inicio para el Técnico (estudiante, 22/11/2026); largos, avisos, regla 8, traspaso y asignaciones (D-79, puntos 5 a 9, a validar) | I4 |
| Lo que \*b e IOT-CNS-LEC no resuelven | Inactividad, «no registrado» sin mensajes (columna nueva), resúmenes, fotoperíodo, retención, correo y refresco del panel (D-76, validada el 22/11/2026) | I2b |

## 9. Disparadores existentes que cierra cada tarea

Salen de `docs/disparadores.md`. Cada archivo de tarea los trae en «Límites».

| Tarea | Disparadores que cierra |
|---|---|
| IOT-01 | «Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión», punto 1, para el IoT (el vínculo es `AlertaIot`, D-72) |
| IOT-02 | «Cuando exista una ocupación de sector, una variedad con semilla o un hardware», punto 4 (`hardware_activo` y el contenido del sector); «Cuando exista SistemaIoT», punto 1 (`tiene_sistema_iot`, el Técnico y la precondición h de PROD-BAJ-INV); «Cuando exista SistemaIoT (alertas)», punto 1, al registrar |
| IOT-04 | «Cuando exista el caso de uso de consulta de alertas (CU-46) o el panel de IoT (CU-41)», la parte del panel; «Cuando exista SistemaIoT», punto 0 del correo (D-54) |
| IOT-06 | «Cuando exista SistemaIoT (alertas)», punto 1, al dar de baja |
| IOT-07 | «Cuando exista SistemaIoT», punto 0 del traspaso del Técnico (D-53); «Cuando existan actuadores, comandos y reglas del IoT», la parte de IOT-07 de los puntos 2 y 3; «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido», la parte del Técnico |
