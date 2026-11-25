# COM-07a · Solicitudes de revisión: evaluar discrepancias, resolver quejas, anular y consultar

Estado: hecha | App: comercial | Rama: feature/com-07a-solicitudes-de-revision | Ronda: Comercial 1

Depende de: **COM-06b** (y, con ella, COM-06a: `SolicitudRevision`, `DiscrepanciaEntrega`, `LineaDiscrepancia`, `IntentoFallido`,
`crear_solicitud`, `monto_a_cobrar`; COM-06b: `Queja` y su alerta). Usa lo que **COM-04a** dejó en `produccion` para las solicitudes
(`docs/api/produccion.md`, **sección 11**: los tipos `incumplimiento_de_clausula` y `anulacion_de_resolucion` y
`bitacora.registrar_evento_de_contrato`). Si COM-06b no está mergeada, o si falta algo de la sección 11, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La primera de las dos partes de COM-07 (D-69, punto 1): el Gerente **evalúa las discrepancias** (una entrega por debajo
del mínimo) y **resuelve las quejas** de los clientes, con todos los datos a la vista; al aceptar, el sistema calcula la indemnización (o la
carga el Gerente, con tope, en una queja sin cláusula), la **descuenta** de lo que el cliente debe por la entrega hasta dejarlo en cero y
**reintegra** el resto, suma un **incumplimiento** al contrato, deja el evento en la **bitácora** y avisa al cliente y al Vendedor. Si se
equivocó, **anula** la resolución, que queda en el historial, y la vuelve a resolver. El Vendedor **consulta** las solicitudes de sus
contratos. La resolución del contrato por incumplimientos es de **COM-07b**.

**Estado de paso** (`docs/temas_abiertos.md`, «Abiertos desde el lote C7»): entre COM-07a y COM-07b, una aceptación que supera los
incumplimientos tolerados deja el contrato «vigente» con más incumplimientos que los tolerados (`resolver_si_corresponde` todavía no hace
nada); la recuperación diaria de COM-07b lo resuelve en su primera ejecución. No rompe datos: programá COM-07b enseguida.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-EVL-DSC | Evaluar Discrepancia (con MD-115, D-69 punto 2) | docs/casos_de_uso/comercial/solicitudes.md | Precondición c y postcondición e (asiento): fuera, D-57. 6a y el cobro de 8b: con datos reales en COM-08. Postcondición h (la resolución): COM-07b |
| COM-RSV-QJA | Resolver Queja | docs/casos_de_uso/comercial/solicitudes.md | Ídem |
| COM-ANL-SRV | Anular Resolución de Solicitud | docs/casos_de_uso/comercial/solicitudes.md | Postcondición c (contraasiento): fuera, D-57. 2a con datos reales: COM-07b. 2b: COM-08 |
| COM-CNS-SRV | Consultar Solicitudes de Revisión (alto nivel) | docs/casos_de_uso/comercial/solicitudes.md | Regla 6: D-69, punto 16 |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/solicitudes.md **completo**; de rutas.md, «Cómo se aplica» (la discrepancia, `crear_solicitud`,
  `intentos_fallidos`, `monto_a_cobrar`, los correos); de confirmacion.md, «Cómo se aplica» (las quejas, los días de retraso, el registrante
  del enlace de la alerta); de entregas.md, la parte 4 del paso 50 («Correos pendientes»); de suministro.md, «COM-CNS-SUM» (la ficha); de
  resolucion.md, solo «Servicios» (qué va a hacer `resolver_si_corresponde` en COM-07b).
- Modelo: docs/modelo/comercial.md (**SolicitudRevision**, **DiscrepanciaEntrega y LineaDiscrepancia**, **Queja**, **Anulacion**,
  **Suministro** (`cantidad_incumplimientos`, `solicitud_resolucion`), Entrega, DetalleEntrega, las cláusulas, **AlertaComercial**,
  IntentoFallido); docs/modelo/produccion.md (Bitacora, Merma); docs/modelo/contabilidad.md (`OrigenDocumento`).
- Decisiones: **D-69** (todos sus puntos), **D-68** (puntos 5 a 7), D-66 (punto 12), D-65, D-63, D-62, D-59, D-57, D-42, D-36, D-29, D-28,
  D-27, D-25.
- Patrones: docs/patrones/bloqueos.md («Resolver o anular una solicitud»), docs/patrones/auditoria.md, docs/patrones/abm.md (sección 1).
- API: **docs/api/produccion.md, sección 11**; docs/api/alertas.md (secciones 2 y 8); docs/api/notificaciones.md;
  `core/extensiones.py` (`registrar_seccion_de_inicio`).
- Pantallas: docs/prototipos/comercial/ (`README.md`): `tabSolicitudes`, `comTabs`, `INIT.srv`, `VIEWS.srv` (vale la de la línea 1765 para el
  panel del Gerente), `srvCalc`, `ACT['srv-ok']` (la última), `MODALS.anlsrv`, `ACT['anlsrv-ok']`, `secComercial` (línea 1548) y la sección
  `ccard('sol', …)` de `VIEWS.sum` (línea 1600).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `comercial/` completo (COM-01 a COM-06b), en especial `models.py` (las solicitudes), `servicios/solicitudes.py`,
  `servicios/concrecion.py`, `servicios/confirmacion.py`, `servicios/entregas.py`, `servicios/comprobantes.py`, `servicios/suministros.py`,
  `apps.py`, las vistas de entregas y de suministros, las fábricas e invariantes; `produccion/servicios/bitacora.py`; `core/models.py`
  (auditoría), `core/notificaciones.py`, `core/correo.py`, `core/extensiones.py`; `maestros/servicios/alertas.py`, `maestros/extensiones.py`;
  `contabilidad/models.py`.

## Límites

- Crea modelos (en `comercial`): `Anulacion` (hija de `OrigenDocumento`); en `SolicitudRevision`, `monto_descontado`, `monto_reintegrado`,
  `medio_reintegro` y `estado_aviso_cliente` (D-69, puntos 9 y 17); en `Suministro`, `solicitud_resolucion` (D-69, punto 5).
  → revisá docs/disparadores.md: cierra lo de COM-07a del punto 10 de «Cuando exista Entrega».
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_solicitudes.py`: la tabla de `Anulacion`, los campos nuevos y las restricciones de `SolicitudRevision`
    (reescritas con los montos), de `Anulacion` y de `Suministro` (`cantidad_incumplimientos >= 0`);
  - `contabilidad/migrations/00NN_anulacion.py`: solo `choices` (`anulacion`);
  - `core/migrations/00NN_comercial_solicitudes.py`: solo `choices` (acciones `evaluacion_discrepancia`, `resolucion_queja`,
    `anulacion_resolucion_solicitud`).
- Permitido fuera de `comercial`: `contabilidad/models.py` (el valor de `TIPO_DE_ORIGEN`); `core/models.py` (las acciones, `ETIQUETAS`,
  `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`); al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`,
  `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`. **No toca `produccion`** (lo suyo lo dejó COM-04a). Las pruebas de COM-06a y
  COM-06b no se modifican, salvo las del registrante del enlace de las alertas de discrepancia y de queja (ahora llevan a la solicitud):
  anotalas en el PR.
- Dependencias nuevas: ninguna.
- Fuera de alcance: resolver el contrato (COM-RSV-SUM, COM-07b: acá `resoluciones.resolver_si_corresponde` queda neutra); el cobro y la
  entrega «pagada» (COM-08); los asientos y el contraasiento (ronda de contabilidad, D-57); un plazo o recordatorio para las pendientes y
  avisar a quien ejecuta el reintegro (temas abiertos de los casos de uso).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones** (las fichas; D-69, puntos 5, 9, 10 y 17). Fábricas: `discrepancia_aceptada(...)`, `queja_aceptada(...)`,
   `anulacion(...)`; invariantes nuevos en `verificar_invariantes_de_solicitudes` (montos, monto a cobrar nunca negativo, contador = aceptadas).
   Pruebas: `comercial/tests/test_modelos_solicitudes.py` (una por restricción).
2. **Cálculos** (`solicitudes.md`, «Cálculos»; `servicios/indemnizaciones.py`). Pruebas: `test_indemnizaciones.py`.
3. **El monto a cobrar** con lo descontado (`solicitudes.md`, «Monto a cobrar»). Pruebas: métodos nuevos en el archivo donde COM-06a probó
   `monto_a_cobrar` (buscalo con Grep; si no tiene uno propio, `test_monto_a_cobrar.py`).
4. **Lista y ficha** (`solicitudes.md`, «La lista» y «La ficha»). Pruebas: `test_com_cns_srv.py`.
5. **Evaluar y resolver** (`solicitudes.md`, «Registrar la resolución»), con `resoluciones.resolver_si_corresponde` neutra, los
   comprobantes y avisos, y «Reenviar aviso» con la parte 4 del paso 50. Pruebas: `test_com_evl_dsc.py`, `test_com_rsv_qja.py`.
6. **Anular** (`solicitudes.md`, «Anular una resolución»). Pruebas: `test_com_anl_srv.py`.
7. **Concurrencia.** Pruebas: `test_solicitudes_concurrencia.py`.
8. **Lo que completa a otras tareas** (`solicitudes.md`, «El enlace de las alertas» y «Lo que completa a otras tareas»): el registrante del
   enlace, la ficha del suministro y el grupo del panel.
9. **Vistas y plantillas** (`solicitudes.md`, «Pantallas»). Pruebas: `test_solicitudes_vistas.py`.
10. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de COM-07a del punto 10 y dejar lo que
    nace (COM-08: la entrega pagada y `Anulacion.pago`); marcar COM-07a en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a
    `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el historial de anulaciones en la ficha (la `Anulacion` y su copia se guardan igual; queda en
`docs/temas_abiertos.md`). No se recortan las restricciones de la base, los bloqueos, la huella, el tope del descuento ni las pruebas de
concurrencia.

## Hecho cuando

- El Gerente abre una discrepancia o una queja desde la alerta o desde la pestaña y ve todo para decidir (cantidades, pérdidas, intentos
  fallidos, el monto, cómo se aplicaría, los incumplimientos y si el contrato se resolvería).
- Al aceptar: la indemnización calculada (o la manual, con tope) queda guardada; se descuenta hasta el monto a cobrar y el resto se reintegra
  con el medio elegido; el contrato suma un incumplimiento; queda el evento en la bitácora del invernadero; la alerta se resuelve; el
  cliente recibe el comprobante y el Vendedor el aviso. Al rechazar: observaciones obligatorias, sin cambios en el contrato, aviso al
  cliente con las observaciones.
- El Gerente anula una resolución (salvo 2a a 2c): la solicitud vuelve a pendiente, el contador y el monto a cobrar vuelven atrás, queda la
  `Anulacion` con la copia y el evento de bitácora; la vuelve a resolver.
- El Vendedor ve las solicitudes de sus contratos, en lectura; el Gerente, todas, con el contador de pendientes en la pestaña y en el panel.
- Todas las pruebas de `comercial`, `contabilidad` y `core` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la hace el estudiante; D-96)

Los datos de verificación los crea el estudiante a mano: el cargador `comercial/verificacion.py` y la sección «Datos para verificar» de las versiones anteriores de este archivo se retiraron (D-95) y no vuelven. No hay navegador automatizado ni capturas.

**Antes de empezar**

1. Aplicá las migraciones nuevas: `python manage.py migrate` (aplica `comercial 0012`, `contabilidad 0010` y `core 0049`; las dos últimas solo cambian listas de valores). Después `python manage.py runserver` y entrá en `http://localhost:8000/`.
2. Cuentas: el **Gerente** (el único activo), el **Vendedor** del contrato (por ejemplo «Vendedor Uno») y un **Agrónomo** (para probar el rol sin acceso). La contraseña de las cuentas de prueba es la tuya (no está en este archivo).
3. Cliente: «Verdulería Los Pinos S.R.L.», CUIT `30-71234567-1`, **con un correo que puedas leer** (el tuyo). Con una dirección en Paraná. Sin el correo del sistema configurado los avisos quedan «pendientes de envío» (pasos 2 y 10); para ver los correos, configuralo o usá `CORREO_CONSOLA=1` en tu `.env` y mirá la terminal de `runserver`.
4. Un suministro del cliente con el Vendedor Uno: 6 meses, **1 incumplimiento tolerado**, multa `50000`, plazo de pago 15 días, indemnización por atraso de pago `100`. Un detalle de **Lechuga Crespa**, 100 plantas cada 7 días, precio `100`, cláusula: tolerancia 0 días, **retraso `10` por día, mínimo `100` plantas, `5` por planta faltante**.
5. Tres entregas concretadas de ese suministro (recorrido de «Concretar entrega», COM-06a; hace falta stock en cámara o un lote en Maduración y un Transportista con ruta iniciada):
   - **E1**: llegaron **80** de 100 (el resto perdido). Genera la **discrepancia** (indemnización 20 × $5 = $100).
   - **E2**: llegaron las 100, y desde el enlace del correo de confirmación (COM-06b) el cliente presenta una **queja por «estado de la mercadería»** con el motivo «Llegó marchita» (tope = 100 × $100 = $10.000).
   - **E3**: concretada **3 días después** del período, y el cliente presenta una **queja por retraso**. Si no podés atrasarla, saltá el paso 5 (lo cubre una prueba).
   Cada una deja su alerta para el Gerente en la campana.

**El camino feliz (Gerente)**

1. **La pestaña y el panel.** Entrá con el Gerente. En el «Panel de control», dentro de «Comercial», tiene que aparecer «Solicitudes de revisión» con **Pendientes: 3** en el color de advertencia. Tocalo: abre la pestaña filtrada por pendientes. En «Comercial», la pestaña «Solicitudes de revisión» tiene el **número 3 en rojo**. Arriba de la tabla se lee «Las quejas las presenta el cliente al confirmar la entrega…». Las filas van de la más antigua a la más reciente. *(Lo cubren `test_solicitudes_vistas` y el recorrido.)*
2. **Desde la alerta.** Abrí la campana, elegí la alerta de la discrepancia y tocá «Ver»: lleva a la **ficha de la solicitud** (`/comercial/solicitudes/<id>/`) y el texto de la alerta dice «SR-… · Discrepancia · pendiente». La ficha muestra: cliente, contrato con «0 de 1 incumplimientos», la entrega, el transportista, el pago de la entrega y su monto a cobrar ($8.000,00), la tabla con **mínimo pactado 100, planificadas/entregadas/perdidas/devueltas 100 / 80 / 20 / 0, $5,00 por planta faltante y $100,00**, y las pérdidas.
3. **Aceptar la discrepancia.** En el panel «Evaluar la discrepancia» elegí «Hubo incumplimiento (aceptar)», escribí la observación «Faltaron 20 plantas» y tocá **Ver resumen**. Tiene que verse: «Discrepancia aceptada, con indemnización de $ 100,00», «se descuentan $ 100,00 de lo que el cliente debe por OT-…: el monto a cobrar pasa de $ 8.000,00 a $ 7.900,00», «Incumplimientos … 1 de 1 tolerados» y la etiqueta «Fuera de esta ronda · contabilidad». Tocá **Confirmar la decisión**. Vuelve a la ficha con «SR-… aceptada: indemnización de $ 100,00. Se avisó al Vendedor y al cliente.», «Cuenta como incumplimiento», el monto a cobrar nuevo y los botones «Anular resolución» y (si el aviso quedó pendiente) «Reenviar aviso».
4. **Lo que dejó la aceptación.** (a) La alerta de la campana ya no está activa. (b) El contrato SUM-… dice **«1 de 1 incumplimientos»**. (c) En Producción → Bitácora del invernadero hay un evento «Incumplimiento de cláusula suministrante» con la descripción «SR-… · Discrepancia · OT-… de SUM-… · … · Lechuga Crespa: 80 de 100, $ 100,00 · Total: $ 100,00», sin lote ni etapa. (d) El Vendedor Uno recibió la notificación «SR-… aceptada». (e) Tu correo recibió el **comprobante de indemnización** (si el correo está configurado), con «Descontado de lo que debés por la entrega» y «Comprobante interno, sin validez fiscal.». (f) En Auditoría hay un registro «Evaluación de discrepancia» con la solicitud, la alerta, el suministro y el evento.
5. **La queja por retraso.** Abrí la solicitud de E3: la ficha muestra los **días de retraso (3), el plazo, $10,00 por día** y la indemnización de $30,00, «Sale de la cláusula; no se puede modificar.» y **no hay campo de monto**. Elegí «No es procedente (rechazar)» sin escribir observaciones y tocá «Ver resumen»: tiene que decir «Las observaciones son obligatorias al rechazar…» y **no** ofrecer «Confirmar la decisión». Escribí «El cliente estaba ausente.», volvé a tocar «Ver resumen» y confirmá. El cliente recibe el aviso «no fue reconocida» con esas observaciones y el Vendedor, la notificación. El contrato **no** suma incumplimientos. *(Lo cubren `test_com_rsv_qja` y el recorrido.)*

**Errores y casos especiales**

6. **La queja por estado de la mercadería: el monto.** Abrí la solicitud de E2 y elegí «Es procedente (aceptar)». En el campo de la indemnización aparece «Entre $ 0,00 y $ 10.000,00». Probá, con «Ver resumen» cada vez: `-5` (error: «El monto no puede ser negativo.»), `100,123` («El monto tiene hasta dos decimales.»), `abc`, `10000,01` («El monto supera el tope. Tiene que estar entre $ 0,00 y $ 10.000,00.») y vacío (se acepta **sin indemnización**: «Sin indemnización: no cambia lo que el cliente debe»; el cliente recibe solo el aviso de que se aceptó).
7. **El monto que supera lo que queda a cobrar.** Con el monto a cobrar de E2 en $10.000, cargá `10000`: se descuenta todo. Para ver el reintegro: primero aceptá otra solicitud de E2 por $9.500 (o usá una entrega más chica) y después cargá `1000`: el resumen dice «Se descuentan $ 500,00 … y se le reintegran $ 500,00» y aparece el desplegable **«Medio del reintegro»** (Efectivo / Transferencia). Si confirmás sin elegir, vuelve el error «Elegí el medio del reintegro». El monto a cobrar queda en $ 0,00 (nunca negativo).
8. **Se superan los incumplimientos tolerados.** Con el contrato en «1 de 1», aceptar otra solicitud muestra la advertencia «Con esta aceptación se superan los incumplimientos tolerados: SUM-… se resolverá y se aplicará la multa de $ 50.000,00. Hasta que se complete COM-07b, el contrato queda «vigente»». Confirmá: el contrato queda **«vigente» con 2 de 1** (estado de paso hasta COM-07b; no es un error). Con un contrato finalizado, la advertencia dice que se registra como historial.
9. **Anular una resolución.** En la ficha de la discrepancia aceptada tocá «Anular resolución»: la página dice «La solicitud vuelve a pendiente…», «Incumplimientos de SUM-…: 2 → 1», «Monto a cobrar de OT-…: $ 7.900,00 → $ 8.000,00» y «Fuera de esta ronda · contabilidad» para el contraasiento. Tocá «Anular resolución» **sin motivo**: error «el motivo es obligatorio». Escribí «Me equivoqué» y confirmá: vuelve a la ficha, «SR-… volvió a pendiente de revisión», aparece el panel para decidir otra vez, el **historial** («Historial de resoluciones anuladas» con la resolución anulada, quién y el motivo) y en la bitácora un evento «Anulación de una resolución». La alerta **sigue resuelta** (no se reabre ni se crea otra). Volvé a aceptarla: todo se repite.
10. **Un bloqueo.** Anulá la aceptación de la queja con reintegro del paso 7: la página dice «**No se puede anular.** … la indemnización ya se le reintegró al cliente (…)» y solo ofrece «Volver». *(Los bloqueos de «la aceptación resolvió el contrato» y «ya se cobró» los cubren `test_com_anl_srv`: dependen de COM-07b y COM-08.)*
11. **«Reenviar aviso» e «Imprimir comprobante».** Si el correo del sistema no está configurado, la ficha de una resuelta muestra el aviso «Pendiente de envío» y el botón **Reenviar aviso**; al configurarlo y tocarlo dice «Se envió el aviso al cliente» y el estado pasa a «Enviado». Con un cliente **sin correo**, la ficha ofrece «Imprimir comprobante» (página para imprimir, «Comprobante interno, sin validez fiscal.»).
12. **Filtros y buscador.** En la lista, filtrá por tipo, estado (Pendientes / Resueltas / Aceptadas / Rechazadas), cliente, contrato (`SUM-0001`), vendedor, fechas y escribí `SR-0012` o solo `12` en «Solicitud»: encuentra esa solicitud. Con filtros sin resultados: «No hay solicitudes con estos filtros.».
13. **La ficha del suministro.** En el contrato, la sección **«Solicitudes de revisión»** lista cada solicitud (de la más reciente a la más antigua) con el tipo, el estado, «Cuenta como incumplimiento» y «Ver».

**Por rol**

14. **Vendedor Uno.** Entrá con él: en «Comercial» ve la pestaña **sin número**, la lista con **solo las solicitudes de sus contratos** y, al abrir una pendiente, «La evalúa el Gerente. Vas a recibir una notificación con la decisión.» **sin** panel, **sin** «Ver resumen», **sin** «Anular resolución». En una resuelta ve la decisión y, si el aviso está pendiente, «Reenviar aviso». El «Panel de control» **no** muestra el grupo «Solicitudes». Escribí a mano `/comercial/solicitudes/<id>/anular/` y `/comercial/solicitudes/<id>/resolver/`: «Prohibido (403)». Con otro Vendedor, la ficha de una solicitud ajena también da 403.
15. **Agrónomo (sin acceso).** Escribí `/comercial/solicitudes/`: «Prohibido (403)» con el mensaje del rol; el menú no ofrece la pestaña.

**Navegador real** (la tarea tiene formularios que se envían). Abrí `/comercial/solicitudes/<id>/` en una **ventana privada**, entrá con el Gerente y **completá y enviá hasta el final** el panel («Ver resumen» y «Confirmar la decisión») y, en otra solicitud, «Anular resolución». Después recargá la ficha. Tiene que mostrar el resultado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no ve. Con **HTMX**: «Ver resumen» redibuja solo el resumen, sin recargar la página ni mover el scroll. El desplegable «Medio del reintegro» y los filtros de la lista usan el desplegable propio.

**Opcionales**

16. **Sin JavaScript** (desactivalo en el navegador): «Ver resumen» recarga la misma ficha con el resumen; confirmar, anular y reenviar funcionan igual; los filtros de la lista funcionan con «Filtrar».
17. **En un celular** (o ventana angosta): la lista y la ficha se ven y se pueden operar (el Gerente trabaja en computadora, pero no tiene que romperse).

**Después del merge**

18. En el log de Render, revisá que se aplicaron `comercial 0012`, `contabilidad 0010` y `core 0049`.

## Cierre

**Qué se hizo.** Las solicitudes de revisión completas (D-69), en `comercial`:

- **Modelos y migraciones.** `Anulacion` (hija de `OrigenDocumento`, con la copia de la resolución anulada); en `SolicitudRevision`, `monto_descontado`, `monto_reintegrado`, `medio_reintegro` y `estado_aviso_cliente` con sus 7 restricciones; `Suministro.solicitud_resolucion`. Migraciones `comercial/0012_solicitudes`, `contabilidad/0010_anulacion` y `core/0049_comercial_solicitudes` (las dos últimas, solo `choices`; ninguna de datos).
- **Servicios.** `indemnizaciones.py` (cálculos puros), `resoluciones.py` (`resolver_si_corresponde`, neutra hasta COM-07b) y, en `solicitudes.py`: la lista y la ficha (COM-CNS-SRV), `resumen_de_resolucion`, `resolver_solicitud` con `evaluar_discrepancia` y `resolver_queja` (COM-EVL-DSC y COM-RSV-QJA), `datos_de_anulacion` y `anular_resolucion` (COM-ANL-SRV), los correos y `reenviar_aviso`. Bloqueos en el orden de D-69 punto 11; la huella (punto 12); el correo y la resolución del contrato con `on_commit` (punto 13).
- **Lo que completa a otras tareas.** `monto_a_cobrar` resta lo descontado; la parte 4 del paso 50 reintenta los avisos pendientes; el registrante de las alertas de discrepancia y de queja lleva a la ficha de la solicitud; el grupo «Solicitudes» del panel; la sección «Solicitudes de revisión» de la ficha del suministro.
- **Vistas, plantillas y correos.** `views_solicitudes.py`, `templates/comercial/solicitudes/` (lista, tabla, ficha, resumen, anular, comprobante) y tres correos (`indemnizacion`, `solicitud_aceptada`, `solicitud_rechazada`).
- **Auditoría (`core`).** Acciones `evaluacion_discrepancia`, `resolucion_queja` y `anulacion_resolucion_solicitud`, 10 etiquetas y 2 listas de valores (sin claves repetidas, D-36).

**Pruebas (M1).**

- `python manage.py test comercial contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **Ran 3707 tests, OK**.
- `python manage.py test comercial --keepdb --tag concurrencia`: **Ran 111 tests, OK** (incluye las 7 de `test_solicitudes_concurrencia`).
- `makemigrations --check --dry-run`: «No changes detected». `manage.py check`: sin problemas.
- `sqlmigrate`: `comercial 0012` crea la tabla `comercial_anulacion`, suma 4 columnas nulas a `SolicitudRevision` y 1 a `Suministro` y 14 restricciones `CHECK` (7 en las solicitudes, 1 en el suministro y 6 en la tabla nueva); no borra ni reescribe datos (las filas existentes cumplen: ninguna solicitud está aceptada hasta ahora). `contabilidad 0010` y `core 0049` son «no-op» en SQL. Las migraciones se aplicaron en las bases `test_…` durante las corridas.
- Archivos de pruebas nuevos: `test_modelos_solicitudes`, `test_indemnizaciones`, `test_com_evl_dsc`, `test_com_rsv_qja`, `test_com_anl_srv`, `test_com_cns_srv`, `test_solicitudes_concurrencia`, `test_solicitudes_vistas`, `test_recorrido_solicitudes_de_revision` y `base_solicitudes.py`; más 5 pruebas de `monto_a_cobrar` en `test_extensiones_entregas.py`.

**Decisiones.** Ninguna nueva: se implementa D-69 (puntos 9 a 17, validados por el estudiante al empezar). No toca `produccion`. Sin dependencias nuevas.

**Pruebas existentes cambiadas (anotar en el PR).**

| Archivo | Qué cambió | Por qué |
|---|---|---|
| `test_confirmacion_vistas.py` (2 pruebas) | El enlace de la alerta de queja es la ficha de la solicitud; la sección de la ficha del suministro se llama «Solicitudes de revisión» (antes «Quejas de entrega»). | La tarea cambia el registrante del enlace; la sección única reemplaza las dos tarjetas (regla 8 de COM-CNS-SUM). |
| `test_rutas_vistas.py` (1 prueba) | «Discrepancias de entrega» y «80 de 100 mínimas» pasan a «Solicitudes de revisión», «Discrepancia de cantidad» y «Pendiente de revisión». | Ídem; las cantidades están en la ficha de la solicitud. |
| `test_modelos_concrecion.py` (1 prueba) | La solicitud «aceptada» válida lleva también `monto_descontado` y `monto_reintegrado` en 0. | La restricción nueva de D-69 punto 9 (aceptada ⇔ los dos montos). Las demás aserciones no cambian. |

**Lo implementado distinto de lo escrito** (para `docs/temas_abiertos.md`, M3).

1. **Errores.** El extracto los llama `ErrorComercial(codigo, mensaje, campo)`, pero esa clase no existe: se usan `ValidationError` con `code`, `PermissionDenied` y `Http404`, como COM-06a y COM-06b.
2. **`Suministro.cantidad_incumplimientos >= 0`** ya existía (COM-03): la migración no la repite; suma solo «`solicitud_resolucion` no nula ⇒ resuelto».
3. **Restricciones de `SolicitudRevision`.** Las tres de COM-06a se conservan; las nuevas son restricciones separadas (no se reescribieron).
4. **Un solo código para los cambios.** `cambio_simultaneo` no se usa: todo cambio entre el resumen y la confirmación es `solicitud_cambio`, con qué cambió.
5. **Dos aceptaciones simultáneas del mismo contrato.** Como la huella incluye el contador, la segunda se rechaza con `solicitud_cambio` y, con el resumen nuevo, el contador sube a 2 (extensión 8b).
6. **`resolver_si_corresponde`** se llama (con `on_commit`) en **toda** aceptación, no solo cuando se superan los tolerados; en COM-07b decide la función.
7. **El contador al anular** usa `Greatest(contador − 1, 0)`: nunca baja de 0.
8. **El filtro de cliente** de la lista es de texto (nombre, razón social o CUIT), no un buscador con desplegable.
9. **Reenviar aviso e «Imprimir comprobante»** pueden usarlos el Gerente y el Vendedor del contrato (no son evaluar ni resolver).
10. **El Vendedor inactivo** no recibe avisos (D-42); la resolución se registra igual.
11. **`concrecion.enlaces_de_alertas`** queda sin registrar (lo reemplaza `solicitudes.enlaces_de_alertas`); se puede borrar en una limpieza.
12. **Pérdidas en la ficha** (`Merma` de la entrega): leídas pero sin prueba con una `Merma` real (ver «No pude verificar»).
13. **Datos de verificación.** La sección «Datos para verificar» de la versión anterior de este archivo (cargador `comercial/verificacion.py`) se ignoró: D-95 retiró los cargadores.

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Resolver queja sin cláusula (`VIEWS.srv`) | El tope era el monto total de la entrega | El tope es lo que el cliente paga por los **detalles de la queja** | MD-114; «Lo que difiere del prototipo» |
| Resolver queja por retraso | «Intentos de entrega fallidos registrados: ninguno», fijo | Los intentos de `IntentoFallido`, con el destacado de 4b | Paso 4 y 4b de COM-RSV-QJA |
| Evaluar y resolver (`ACT['srv-ok']`) | Al aceptar, el contrato pasaba a «resuelto» en la misma operación | Queda «vigente»; el resumen advierte que se resolverá (COM-07b) | 6b; D-69 puntos 1 y 13 |
| Ficha | Sin historial; la anulación no dejaba rastro | «Historial de resoluciones anuladas» | D-69 punto 10 |
| Lista (`tabSolicitudes`) | Filtros tipo, estado y Vendedor | Además cliente, contrato, fechas y número (`SR-0012` o `12`) | Regla 2 de COM-CNS-SRV; D-69 punto 16 |
| Ficha | «Pago de la entrega» con «vencida» | «En mora» | MD-139 |
| Evaluar discrepancia | Las pérdidas no se mostraban | Se muestran las pérdidas de la entrega | Paso 4 de COM-EVL-DSC |
| Anular la resolución (`MODALS.anlsrv`) | Ventana (modal) | Una página con el mismo contenido; con un bloqueo, solo el mensaje y «Volver» | Respaldo sin JavaScript (`interfaz.md`) |
| Panel de la ficha | Los campos aparecían después de elegir la decisión y el botón de confirmar se deshabilitaba | Todo visible; «Ver resumen» valida y solo entonces aparece «Confirmar la decisión» (con el medio del reintegro cuando hace falta) | Sin JavaScript todo funciona; nada se valida al tipear (`interfaz.md`) |
| Resumen | Una línea de texto | El resumen lista la decisión, el monto, cómo se aplica, los incumplimientos, la advertencia de 6b o de historial (6c) y «Fuera de esta ronda · contabilidad» | Pasos 6 y 10; D-57 |
| Estados vacío y de error | No existían | «Todavía no hay solicitudes…», «No hay solicitudes con estos filtros.», errores junto a cada campo y mensajes de «ya resuelta» y «cambió algo» | `interfaz.md` (estados y errores) |

**Informe.**

*Verifiqué:* el recorrido de punta a punta con el cliente de Django (`RecorridoDeSolicitudesDeRevisionTests`: el Gerente evalúa una discrepancia con HTMX, resuelve una queja con monto inválido, con tope y con advertencia de resolución, rechaza una queja por retraso sin y con observaciones, anula y vuelve a resolver; el Vendedor, en lectura y sin botones de escritura); las migraciones (`makemigrations --check` y `sqlmigrate` leídos: nada borra ni reescribe datos; aplicadas en las bases de prueba); la suite completa de `comercial`, `contabilidad` y `core` (3707 OK) y la concurrencia (111 OK).

*Lo cubre una prueba:* los cálculos y la aplicación (`test_indemnizaciones`); cada postcondición, extensión y regla de los cuatro casos de uso (`test_com_evl_dsc`, `test_com_rsv_qja`, `test_com_anl_srv`, `test_com_cns_srv`); las restricciones de la base (`test_modelos_solicitudes`); los bloqueos y la huella con dos hilos (`test_solicitudes_concurrencia`); los botones y enlaces por rol y estado, el resumen con HTMX y sin JavaScript, el medio del reintegro, el enlace de las alertas, el panel y la sección de la ficha del suministro (`test_solicitudes_vistas`).

*No pude verificar:* el aspecto, el desplegable propio, HTMX en un navegador real, el CSRF y el encabezado `Origin` de los formularios (paso de «navegador real»); el envío real de correo; las pérdidas (`Merma`) en la ficha con una merma real; los bloqueos 2a y 2b con datos reales (`Suministro.solicitud_resolucion` lo carga COM-07b y el cobro, COM-08a: hoy se prueban con una fábrica y con `mock.patch`); los asientos y el contraasiento (fuera de la ronda, D-57); que Render aplique las migraciones.

**Archivos tocados fuera de `comercial/`:** `core/models.py` y `core/migrations/0049_comercial_solicitudes.py`; `contabilidad/models.py` y `contabilidad/migrations/0010_anulacion.py`; este archivo de la tarea.
