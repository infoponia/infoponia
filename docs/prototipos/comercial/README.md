# Prototipo · Comercial y cosecha

Archivo: `comercial_y_cosecha.html` (en esta carpeta). Es la copia del artefacto «InfoPonia · Comercial y cosecha», versión
`1795306795-c806` (21/11/2026: la `1795284117-b773`, revisada contra los casos de uso ese mismo día, más la rescisión de suministros,
COM-RSC-SUM y COM-ANL-RSC). Es la guía visual de la app `comercial` y de lo que la
ronda «Comercial 1» suma a `produccion` y a `maestros` (D-24): **manda el caso de uso**. Es una referencia, no una especificación (D-61):
si a una pantalla le falta algo o algo está mal como interfaz, Claude Code la corrige y lo anota en el «Cierre» (regla L7). Qué pantalla va en qué tarea: `docs/tareas/ronda_comercial_1.md`, sección 4.

Es un solo archivo de 1.862 líneas. Cada pantalla es una función de JavaScript: buscala con Grep por el nombre de abajo y leé solo esa
parte. El CSS (líneas 5 a 692) no se lee entero: buscá solo las clases que necesites. No leas el archivo entero (regla L6).

> **Estilo (D-47).** Es el mismo estilo del prototipo de producción («Diseño v2»), que UI-01 ya pasó al sistema. Igual que allá, los
> filtros usan el `<select>` nativo, que D-24 descartó: se usa el desplegable propio con este aspecto.

## Cómo está armado (leelo antes de buscar una pantalla)

- **Vistas y ventanas.** Las pantallas están en el objeto `VIEWS` (`VIEWS.cli`, `VIEWS.cvnew`…) y las ventanas en `MODALS`
  (`MODALS.bajacli`…). `INIT.<vista>` carga el formulario antes de mostrarla y `ACT.<acción>` es lo que hace cada botón (`data-act`).
- **Versión final de cada pantalla.** El archivo tiene varias capas: la primera definición (líneas 900 a 1375) y, desde la línea 1376,
  sobrescrituras («Integración con lo que ya existe…» y tres bloques «Revisión del 21/11/2026»). Muchas sobrescrituras **envuelven** a la
  anterior: `VIEWS.vehform=(o=>()=>{…o()…})(VIEWS.vehform)` ejecuta la vieja y le cambia partes. Para saber cómo queda una pantalla,
  leé **todas** sus definiciones, de la primera a la última; la columna «Líneas» de abajo las lista en orden. Lo que vale es lo que
  resulta de la última.
- **Marcas.** El botón «Resaltar lo nuevo» del pie pinta lo nuevo de la ronda (`mk-new`), lo que ya existe en el sistema o en el
  prototipo de producción (`mk-ext`) y lo del IoT (`mk-iot`). Lo marcado `mk-ext` o `mk-iot` no lo hace esta ronda.
- **Roles.** `USERS` (línea 695) tiene un usuario por rol (Gerente `ger`, Vendedor `ven`, Agrónomo `agr`, Capataz `cap`, Transportista
  `tra` y Cliente `cli`, que es el portal de enlaces). `NAV` es el menú; vale la versión de la línea 1383.

## Pantallas

| Pantalla | Funciones | Líneas (de la primera a la última definición) | Tarea |
|---|---|---|---|
| Marco, menú y campana | `shell`, `NAV` (versión de «Integración»), `alertas` | 873, 1383 a 1385 | Ya existe (UI-01, NOT-01); COM-01 agrega «Comercial» |
| Panel de control del Gerente y del Vendedor | `VIEWS.inicio`, `secPersonal`, `secComercial`, `secMes` | 908, 1426; `secComercial` 1418 y 1548; `secMes` 1725 | MAE-05 (`secPersonal`); COM-05a, COM-07 y COM-08 (grupos de `secComercial` y `secMes`) |
| Panel de control del Agrónomo | `VIEWS.inicio`, `secPrd04`, `secCosecha` | 1422 a 1426 | PRD-04 (`secPrd04`, ya documentado); COM-04 y COM-05a (`secCosecha`) |
| Comercial: pestañas | `VIEWS.com`, `comTabs` | 926, 1485, 1487 | COM-01 (Clientes y Vehículos) y cada tarea suma la suya |
| Clientes: lista | `tabClientes` | 963 | COM-01 |
| Cliente: ficha | `VIEWS.cli` | 1102 | COM-01 (datos y direcciones); COM-02, COM-03, COM-06 y COM-08 suman contratos, entregas y deuda |
| Cliente: alta, modificación y reactivación | `INIT.cliform`, `VIEWS.cliform`, `ACT['cliform-ok']`, `ACT.reactcli`, `cuitOk`, `dirForm`, `dirAdd`, `ACT.dirdesact` | 1109 a 1129; `dirForm` y `dirAdd` 1532 a 1540 | COM-01 |
| Cliente: baja | `MODALS.bajacli`, `ACT['bajacli-ok']` | 1130 a 1132 | COM-01 |
| Vehículos: lista | `tabVehiculos` | 967 | COM-01 (sin la columna «Entregas a realizar», que suma COM-05a) |
| Vehículo: alta y modificación | `INIT.vehform`, `VIEWS.vehform`, `ACT['vehform-ok']` | 1135, 1136 y 1807; `ACT['vehform-ok']` 1142 y 1817 | COM-01 (la carga asignada, COM-05a) |
| Vehículo: baja y reactivación | `MODALS.bajaveh`, `ACT['bajaveh-ok']`, `ACT.reactveh` | 1145 a 1148 | COM-01 (las entregas a realizar, COM-05a) |
| Buscador de clientes (para contratos y cobros) | `cliHit`, `cliPick`, `cliSearch`, `cliMatch` | 1515 a 1524 | COM-02 |
| Contratos: lista | `tabContratos`, `ctrSel` | 931, 1525 | COM-02 (compra-venta) y COM-03 (suministro) |
| Compra-venta: ficha, alta y cancelación | `VIEWS.cv`, `INIT.cvnew`, `VIEWS.cvnew`, `retiroFld`, `INIT.cvcancel`, `VIEWS.cvcancel` | 972, 1001 a 1003, 1528, 985 y 986 | COM-02 (ficha y alta), COM-05b (cancelación); las entregas de la ficha, COM-05a |
| Suministro: ficha, pactar, modificar e historial | `VIEWS.sum`, `INIT.sumnew`, `VIEWS.sumnew`, `INIT.summod`, `VIEWS.summod`, `MODALS.sumhist`, `ccard`, `detForm`, `detErr`, `calRow`, `versiones`, `ultimas`, `chgDiff` | 1021 y 1585; 1041 y 1049; 1063, 1065 y 1611; 1602; 1557 a 1618 | COM-03 |
| Suministro: rescindir y dejar sin efecto la rescisión | `rscConserva`, `MODALS.sumrsc`, `ACT['sumrsc-ok']`, `MODALS.sumrscanl`, `ACT['sumrscanl-ok']` y los reemplazos de `VIEWS.sum` y `tabContratos` (bloque «Revisión del 21/11/2026 (5)») | 1819 a 1859 | COM-03 |
| Producción del Agrónomo: órdenes, cosechas, envasado | `VIEWS.prod`, `ordenesTab`, `tabCosechas`, `tabEnvasado`, `MODALS['nueva-orden']` | 1235 y 1437; 1440; 1238; 1248; 1449 | COM-04 (cosechas) y COM-05a (envasado) |
| Planificar, modificar y cancelar cosecha | `INIT.cscnew`, `VIEWS.cscnew`, `INIT.cscmod`, `VIEWS.cscmod`, `lotErrs`, `MODALS.cnlcsc` | 1255, 1257 y 1714; 1271, 1272 y 1715; 1713; 1251 | COM-04 |
| Capataz (celular): bandeja y Concretar Cosecha | `VIEWS.caphome`, `INIT.capcsc`, `VIEWS.capcsc`, `capcscCalc`, `reparto`, `inp` | 1302 y 1490; 1305 y 1652; 1306 y 1657; 1653; 1650; 1658 | COM-04 |
| Ficha del invernadero (con «Logística» y «Cámara») | `VIEWS.invfic`, `logistica`, `camaraTab`, `tabCamara`, `MODALS.tragregar`, `MODALS.trquitar`, `trVeh`, `trRuta`, `trPend`, `sinInv` | 1455; 1467; 1470; 1242; 1472; 1479; 1405 a 1408 | MAE-05 («Logística», con su propio prototipo); COM-01 y COM-05a (columnas de comercial); COM-04 (pestaña «Cámara») |
| Configuración: aviso de vencimiento de cámara | `VIEWS.cfg`, `ACT.cfgok` | 1502, 1504 | COM-04 (solo el parámetro nuevo; la pantalla es de MAE-04) |
| Planificar envasado | `INIT.env`, `VIEWS.env`, `envDisp`, `envErr`, `dupOf` | 1289; 1290 y 1704; 1702 a 1704 | COM-05a |
| Entregas y Asignar transportista | `tabEntregas`, `INIT.asg`, `VIEWS.asg`, `candidatos` | 944; 1088; 1091 y 1804; 1089 y 1803 | COM-05a (`tabEntregas`, sin asignar) y COM-05b (asignar) |
| Transportista (celular): ruta, concretar, intento fallido, finalizar | `VIEWS.ruta`, `MODALS.inirut`, `INIT.cncent`, `VIEWS.cncent`, `cncentCalc`, `MODALS.fallo`, `MODALS.finrut`, `loc`, `entR` | 1319 y 1732; 1325; 1331 y 1675; 1332 y 1682; 1676; 1327; 1329 y 1699; 1733; 1642 | COM-06 |
| Portal del cliente: Confirmar Entrega y Decidir Faltante | `VIEWS.portal`, `INIT.cnf`, `VIEWS.cnf`, `qErr`, `INIT.dcd`, `VIEWS.dcd` | 1349; 1353 y 1741; 1354 y 1742; 1745; 1367; 1368 | COM-06 (confirmar), COM-04 (faltante) |
| Atender entrega no reconocida | `INIT.atnenr`, `VIEWS.atnenr` | 1203; 1204 y 1814 | COM-06 |
| Solicitudes de revisión | `tabSolicitudes`, `INIT.srv`, `VIEWS.srv`, `srvCalc`, `MODALS.anlsrv`, `pendSrv` | 960; 1151; 1152 y 1765; 1759; 1176; 1792 | COM-07 |
| Cobranza: registrar y anular cobro | `tabCobranza`, `cobGroups`, `INIT.cobro`, `VIEWS.cobro`, `MODALS.anlcbr` | 951; 1543; 1183 y 1787; 1185 y 1788; 1198 | COM-08 |
| Estadísticas (pestaña de Comercial) | `VIEWS.est`, `kpi`, la versión de `VIEWS.com` de la línea 1485 | 1214; 1411; 1485 | COM-08 |

**Ayudas comunes** que usan varias pantallas (no son pantallas): `fld`, `seg`, `ro`, `sel`, `chk`, `card`, `facts`, `table`, `badge`,
`bs` (insignia de estado), `alertBox`, `kebab` (menú «⋯»), `money`, `kg`, `fmt` (fechas), `cliN` (nombre del cliente),
`applySteps` (línea 1511: los pasos que siguen al primero incompleto quedan bloqueados, criterio general de la ronda) y `fueraRonda`
(línea 1729: el recuadro «Fuera de esta ronda · contabilidad»).

Todos los nombres de esta tabla se verificaron contra el archivo el 21/11/2026.

## Elementos del prototipo que no van en el sistema

Cada caso de uso de la ronda los repite en su lista «Solo prototipo», como `docs/casos_de_uso/usuarios.md`.

- El selector «Solo prototipo · ver como» (`USERS`, `ACT.role`) para cambiar de rol, y el aviso del Técnico, que remite al prototipo
  del IoT.
- El pie «Prototipo de pantallas · módulo comercial y cosecha», el botón «Resaltar lo nuevo» (`ACT.hl`) y sus marcas `mk-*`, y
  «Reiniciar datos de ejemplo» (`ACT.reset`).
- La fecha fija `HOY` (21/11/2026) y los datos de ejemplo (`seed`, `DB`, `EXOT`, `GEOP`).
- La pantalla «Enlaces recibidos» (`VIEWS.portal`): en el sistema, el cliente entra directo desde el enlace de cada correo.
- La lista de muestra de provincias, departamentos y localidades (`GEOP`): el sistema usa Georef (MAE-01, D-39).
- Los recuadros «Solo prototipo» (`protoBox`), «Ya existe» (`EXT_TAB`) y los botones que remiten a otros prototipos (`ACT.otro`,
  `OTRO`): muestran dónde va lo que ya existe o lo que trae el IoT.
- Los recuadros «Fuera de esta ronda · contabilidad» (`fueraRonda`) **sí** describen algo real (el asiento que no se programa, D-57),
  pero en el sistema no se muestra ningún recuadro: el asiento simplemente no existe.
- Los avisos breves (`toast`) con textos de ejemplo: los textos del sistema son los de cada tarea, con voseo (el prototipo a veces usa
  «usted»: «Ingrese el CUIT», «revise el dígito»).
- Los identificadores de ejemplo (`CL-01`, `CV-0041`, `ENT-0110`): el sistema usa los suyos.
- El cálculo de las fechas y las cantidades de ejemplo dentro de las pantallas: las reglas salen del caso de uso.
