# COM-07a · Solicitudes de revisión: evaluar discrepancias, resolver quejas, anular y consultar

Estado: pendiente | App: comercial | Rama: feature/com-07a-solicitudes-de-revision | Ronda: Comercial 1

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

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial`, `contabilidad`, `core`): `python manage.py migrate`. Datos: los de COM-06b, con un cliente de suministro
**con un correo que puedas leer**, un suministro con 1 incumplimiento tolerado, una entrega concretada por debajo del mínimo (discrepancia) y
otra con una queja por retraso y otra por estado de la mercadería.

1. Con el Gerente, desde la alerta de la discrepancia: la ficha muestra mínimo, cantidades, pérdidas y el monto; «Aceptar»: el resumen dice
   el descuento y el nuevo monto a cobrar. Confirmá: la alerta se resuelve, el contrato pasa a «1 de 1», llega el comprobante, el Vendedor
   tiene el aviso y la bitácora del invernadero muestra el evento.
2. La queja por estado de la mercadería: cargá un monto mayor que el tope: error con el tope; cargá uno válido mayor que lo que queda a
   cobrar: se pide el medio del reintegro y el resumen muestra las dos partes.
3. La queja por retraso: la ficha muestra los días y los intentos fallidos; rechazala sin observaciones: error; con observaciones: el cliente
   recibe el aviso.
4. La segunda aceptación supera la tolerancia: el resumen advierte que el contrato se resolverá (hasta COM-07b, queda «vigente»).
5. Anulá la resolución de la discrepancia: el contador y el monto a cobrar vuelven atrás, la ficha muestra el historial; volvé a resolverla.
   Anular la queja con reintegro: «No se puede anular».
6. Con el Vendedor: ve sus solicitudes en lectura, con «La evalúa el Gerente»; no ve el panel para decidir ni «Anular resolución».
7. Sin JavaScript: evaluar, resolver y anular funcionan.
8. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
