# Prototipo · IoT

Archivo: `iot.html` (en esta carpeta). Es la copia del artefacto «InfoPonia IoT», versión v8.5, que acompañó a la ronda 23 de los casos de uso del IoT
(Lote 1 v5.6, 20/11/2026), copiado al repositorio el 21/11/2026. Es la guía visual de la app `iot` y de lo poco que la ronda «IoT 1» toca en
`maestros` y en Configuración (D-24): **manda el caso de uso**. Es una referencia, no una especificación (D-61): si a una pantalla le falta
algo o algo está mal como interfaz, Claude Code la corrige y lo anota en el «Cierre» (regla L7). Qué pantalla va en qué tarea:
`docs/tareas/ronda_iot_1.md`, sección 4.

Es un solo archivo de 835 líneas. Cada pantalla es una función de JavaScript: buscala con Grep por el nombre de abajo y leé solo esa parte.
El CSS (líneas 9 a 195) no se lee entero: buscá solo las clases que necesites. No leas el archivo entero (regla L6).

> **Estilo (D-47).** Es el estilo del prototipo de producción («Diseño v2»), que UI-01 ya pasó al sistema. Los filtros y la barra de
> contexto usan el `<select>` nativo, que D-24 descartó: se usa el desplegable propio con este aspecto.

## Cómo está armado (leelo antes de buscar una pantalla)

- **Pantallas.** `SCR` (línea 632) une cada pestaña con su función: `monitoreo`, `comandos`, `reglas`, `hardware`, `sistema`, `tipos` y
  `config`. `NAV` (línea 631) es la fila de pestañas del módulo y `MODS` (línea 634), el menú lateral. Cada función de pantalla tiene
  **ramas**: una misma función dibuja la lista, la ficha o el formulario según `S.v` (por ejemplo `hardware` con `S.v.t==='hw-form'`).
- **Ventanas.** Todas en `modalHtml` (línea 636), elegidas por `S.modal.t`, con la forma `clave` o `clave:<id>` (`baj:<id>`, `react:<id>`…).
- **Botones.** `act` (línea 671) es un único `switch` con un `case` por cada `data-act`. Para ver qué hace un botón, buscá su `case '…'`.
- **Estado.** `S` (línea 307) es el estado de la pantalla y `DB` (línea 244), los datos de ejemplo.
- **Barra de contexto.** `ctxBar` (línea 635): el invernadero elegido; deshabilitada en «Tipos de actuador» (comunes a la organización).
- **Alcance.** `canOp` y `opBanner` (líneas 329 y 330) y `visInv` (línea 335): quién opera y quién solo consulta (MD-98).

## Pantallas

| Pantalla | Funciones (línea) | Casos de uso | Tarea |
|---|---|---|---|
| Marco, menú y pestañas | `render` 655, `NAV` 631, `MODS` 634, `ctxBar` 635 | — | IOT-01 (la entrada «IoT» del menú y las pestañas que existen) |
| Tipos de actuador: lista, alta, modificación, baja y reactivación | `tipos` 599, `cmdOpts` 596, `enUsoTac` 597, `histTac` 598, `unidOpts` 319; `case 'tac-new'`, `'tac-mod'`, `'acc-add'`, `'acc-del'`, `'save-tac'`; ventana `tbaj:<id>` | IOT-ALT/MOD/BAJ/CNS-TAC | IOT-01 (lo que mira comandos y reglas, IOT-05 e IOT-06) |
| Sistema IoT: registrar, ficha, modificar, token | `sistema` 434, `sysEstB` 433, `newTok` 663; `case 'open-sys-form'`, `'save-sys'`, `'tok-ck'`, `'copy'`, `'guia'`; ventanas `token` y `regen` | IOT-REG-SIS, IOT-MOD-SIS, IOT-CNS (ficha del nodo en Hardware) | IOT-02 |
| Sistema IoT: desconectar, activar y dar de baja | `sistema` 434; `case 'sys-activar'`; ventanas `desc` y `baj` (sin id) | IOT-DSC-SIS, IOT-ACT-SIS, IOT-BAJ-SIS | IOT-06 |
| Hardware: lista, ficha, alta, modificación | `hardware` 460, `hwBadge` 458, `anunciadosLibres` 459, `sensorState` 369, `actState` 384, `estInf` 392, `compatB` 396, `tipoCambiable` 321, `IDRE` 308, `recompat` 511, `announced` 509, `announcedBad` 507, `bajaDe` 518; `case 'hw-new'`, `'hw-mod'`, `'hw-ficha'`, `'hw-back'`, `'save-hw'`, `'reg-alert'`, `'hwf-*'` | IOT-ALT-HDW, IOT-MOD-HDW, IOT-CNS-HDW | IOT-02 (lecturas: IOT-03; comandos: IOT-05; reglas: IOT-06) |
| Hardware: volver a activar y reactivar | ventanas `react:<id>` y `rebaja:<id>` | IOT-MOD-HDW | IOT-02 (las órdenes de mantenimiento, IOT-07) |
| Hardware: dar de baja | ventana `baj:<id>` | IOT-BAJ-HDW | IOT-06 |
| Orden de mantenimiento al fallar un comando | `failCmd` 664, `DB.ordenes` 302; los textos de `react:<id>`, `baj:<id>` y `baj` | IOT-RSV-CMD (4b.4), IOT-MOD-HDW (regla 8), IOT-BAJ-HDW, IOT-BAJ-SIS | IOT-07 (`docs/casos_de_uso/iot/mantenimiento_automatico.md`; la ficha del equipo y el Inicio del Técnico no tienen pantalla en el prototipo) |
| Monitoreo | `monitoreo` 407, `sensCard` 398, `series` 350, `spark` 361, `refRange` 368, `RNG` 347, `RSUM` 348, `SEV` 397; `case 'range'`, `'grp'`, `'refresh'` | IOT-CNS-LEC (ENT-INF lo alimenta) | IOT-04 |
| Comandos: lista, emitir, cancelar | `comandos` 546, `cmdForm` 522, `cmdBadge` 521, `mismoEstado` 545, `CMDV` 236, `CMDST` 237; `case 'cmd-for'`, `'c-act'`, `'c-acc'`, `'emit'`, `'cf-*'`; ventana `ccan:<id>` | IOT-EMT-CMD, IOT-RSV-CMD, IOT-CNL-CMD | IOT-05 |
| Reglas de actuación | `reglas` 573, `rglText` 564, `ultB` 565, `rglTags` 566, `rglSensors` 572, `COND` 304; `case 'rgl-new'`, `'rgl-mod'`, `'r-cond'`, `'r-act'`, `'r-acc'`, `'save-rgl'`; ventana `rbaj:<id>` | IOT-ALT/MOD/BAJ/CNS-RGL | IOT-06 |
| Configuración: sección «Módulo IoT» | `config` 626, `CFGP` 620; `case 'save-cfg'`, `'cfg-reset'` | ADM-MOD-CFG (sección IoT) | IOT-01 (los parámetros), IOT-04 (la pantalla) |

**Ayudas comunes** (no son pantallas): `esc`, `ic` (íconos), `bd` (insignia), `fld`, `tx`, `nm`, `sl`, `ph` (encabezado), `invSel`, `menu`
y `menuStyle` (menú «⋯»), `toast`, `go`, `fmt`, `ago`, `val`, `sys` (el sistema del invernadero elegido), `gh`, `tipoDe`, `hwName` y `hwLbl`
(nombres de un equipo), `accsAct`, `accsOk` y `accDe` (acciones de un tipo), `UNID` (unidades por comando), `VARS` y `UVARS` (variables y
unidades), `CAPS` (capacidades), `INSUMOS` e `INVS`.

Todos los nombres y líneas de esta tabla se verificaron contra el archivo el 21/11/2026.

## Lo que difiere de los casos de uso (manda el CU)

- **La guía del nodo.** El botón «Descargar guía» (`case 'guia'`) cita `docs/api_nodo.md`: la guía es `docs/api/nodo/README.md` (D-70) y
  el botón es un enlace a ella (`URL_GUIA_DEL_NODO`, `docs/casos_de_uso/iot/sistema_iot.md`).
- **Volver a activar un equipo** cancela la orden de mantenimiento sin preguntar: el CU (regla 8 de IOT-MOD-HDW) deja elegir por cada orden
  (D-73).
- **La variable de un sensor** no se puede cambiar nunca en el prototipo: el CU lo permite si no tiene lecturas. El nombre del sensor
  (opcional) no está en el prototipo.
- **Los parámetros.** `CFGP` y `case 'save-cfg'` traen los 14 parámetros con sus rangos, con las cuatro histéresis (la temperatura
  de la solución tiene la suya). Si un nombre o un valor inicial difiere, vale `docs/modelo/iot.md`, «Parámetros IoT de ConfiguracionOperativa».

Los demás desvíos de cada pantalla están en la sección «Pantallas» de su extracto (`docs/casos_de_uso/iot/`).

## Solo prototipo (elementos que no van en el sistema)

Cada caso de uso de la ronda los repite en su lista «Solo prototipo».

- El selector «Ver como» de `render` (Agrónomo, Gerente y «Gerente · invernadero sin Agrónomo»; `case 'role'`).
- La insignia «Prototipo IoT» del encabezado.
- Los recuadros «SOLO PROTOTIPO · simula lo que informa el nodo» y «… simula la respuesta del nodo» (clase `proto`) y sus botones:
  `case 'sim-modo'`, `'sim-ok'`, `'sim-rech'`, `'sim-fail'`. En el sistema lo informa el nodo por la API (IOT-03 e IOT-05).
- El token de ejemplo de `newTok` (en el sistema, `core.enlaces.nuevo_token`, D-65) y `failCmd` (en el sistema, la revisión periódica,
  D-71).
- Los datos de ejemplo `DB`, los anuncios fijos `SOP` y `t0cmds`, los identificadores `TAC-0N`, `HW-NN`, `CMD-NN` y `RGL-NN` (en el sistema,
  el id o el código armado con él) y las horas relativas («hace 20 s»).
- La actualización cada 20 s con `setInterval` (`case 'refresh-quiet'`): en el sistema, la pantalla de Monitoreo consulta al servidor con
  HTMX (IOT-04).
- El borrado físico de un tipo de actuador en la ventana `tbaj:<id>` y en `case 'm-ok'`: la baja es lógica (IOT-BAJ-TAC) y se
  reactiva con IOT-MOD-TAC.
- Los módulos del menú lateral que no son «IoT» ni «Configuración»: son de las otras rondas.
