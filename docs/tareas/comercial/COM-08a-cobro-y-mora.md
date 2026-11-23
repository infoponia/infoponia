# COM-08a · Cobro de suministros y mora (paso diario 30)

Estado: pendiente | App: comercial | Rama: feature/com-08a-cobro-y-mora | Ronda: Comercial 1

Depende de: **COM-07b** (y, con ella, toda la cadena COM-02 a COM-07a, MAE-05, MAE-02d, DIA-01, USR-10 y «Producción 1»). Usa de COM-06a
`PagoCliente`, `monto_a_cobrar` y `estado_de_pago`; de COM-07a, la aplicación de la indemnización, la huella de las solicitudes y `Anulacion`.
Si COM-07b no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La primera de las tres partes de COM-08 (D-94, punto 1): el Vendedor (o el Gerente) **registra lo que pagó un cliente de
suministro** por una o varias entregas, sin pagos parciales y con la **indemnización por atraso** calculada por el sistema; la entrega queda
**pagada**, su alerta se resuelve y el cliente recibe el comprobante. Cada día, InfoPonia **pone en mora** las entregas que vencieron sin
pagarse: alerta al Gerente, aviso al Vendedor y un correo al cliente, una sola vez. Con el cobro real, lo que COM-06 y COM-07 dejaron
probado con `mock.patch` (la entrega pagada en las solicitudes y en la entrega no reconocida) pasa a probarse con datos reales. Anular un
cobro y cobrar al cancelar una compra-venta son de **COM-08b**; las estadísticas, de **COM-08c**.

**Estado de paso** (`docs/temas_abiertos.md`, «Abiertos desde el lote C8»): entre COM-08a y COM-08b, un cobro mal registrado no se puede
anular, la extensión 2b de COM-ANL-SRV bloquea la anulación de una solicitud cuya entrega se cobró con descuento, y COM-CNL-CVT sigue
rechazando `venta_con_entregas_concretadas`. No rompe datos: programá COM-08b enseguida.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-REG-CBR | Registrar Cobro de Suministro | docs/casos_de_uso/comercial/cobranza.md | Precondición c y postcondición d (asiento): fuera, D-57. 7a de COM-ANL-CBR (la fecha del cobro anulado): COM-08b |
| COM-VNC-PAG | Vencer Pagos de Suministro (alto nivel; paso diario 30) | docs/casos_de_uso/comercial/cobranza.md | Regla 7: la reactivación la hace COM-08b con `reevaluar_mora` |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/cobranza.md **completo menos «Anular un cobro»**; de solicitudes.md, «Cómo se aplica» («Monto a
  cobrar», «Registrar la resolución» —la huella y la aplicación—, «Anular una resolución» —2b—); de rutas.md, «Concretar» (pasos 5 y 7: la
  fecha de vencimiento y el pago de compra-venta) y «Servicios» (`monto_a_cobrar`, `estado_de_pago`); de confirmacion.md, «Atender una
  entrega no reconocida»; de entregas.md, la parte 4 del paso 50 («Correos pendientes»); de suministro.md, «COM-CNS-SUM» (reglas 7 y 10); de
  clientes.md, «Consulta (CNS)» y «Baja (BAJ)».
- Modelo: docs/modelo/comercial.md (**PagoCliente**, **LineaPago**, **Entrega** —`fecha_aviso_mora`, `estado_aviso_mora`—,
  **AlertaComercial**, SolicitudRevision, Suministro y sus cláusulas, Cliente, Contrato); docs/modelo/contabilidad.md (`OrigenDocumento`).
- Decisiones: **D-94** (puntos 1 a 9, 12, 13 y 16), D-69 (puntos 8, 9, 12 y 17), D-68 (puntos 4 y 7), D-66 (punto 12), D-65, D-63, D-62,
  D-57, D-56, D-42, D-36, D-28, D-25.
- Patrones: docs/patrones/bloqueos.md (**«Cobranza»** y «Resolver o anular una solicitud»), docs/patrones/auditoria.md, docs/patrones/abm.md
  (sección 1).
- API: docs/api/alertas.md (secciones 1, 2, 4 y 8); docs/api/notificaciones.md; `core/extensiones.py` (`registrar_seccion_de_inicio`);
  `core/procesos.py`.
- Pantallas: docs/prototipos/comercial/ (`README.md`): `tabCobranza` (línea 951), `cobGroups` (línea 1543), `ACT.cobtog`, `INIT.cobro` y
  `VIEWS.cobro` (las de las líneas 1787 y 1788), `atrasoDe` (línea 1184), `ACT['cobro-ok']`, `cliPick`, `secComercial` (línea 1548), `comTabs`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `comercial/` completo (COM-01 a COM-07b), en especial `models.py` (`PagoCliente`, `Entrega`, `AlertaComercial`),
  `servicios/entregas.py` (`monto_a_cobrar`, `estado_de_pago`, el paso 50), `servicios/concrecion.py`, `servicios/solicitudes.py`,
  `servicios/indemnizaciones.py`, `servicios/atencion.py`, `servicios/comprobantes.py`, `servicios/suministros.py` (la ficha),
  `servicios/clientes.py` (la ficha y la baja), `apps.py` (los tipos de alerta, los enlaces y los pasos), las fábricas e invariantes;
  `core/procesos.py`, `core/models.py`, `core/notificaciones.py`, `core/correo.py`; `maestros/servicios/alertas.py`, `maestros/extensiones.py`.

## Límites

- Crea modelos (en `comercial`): **`LineaPago`** (R154, D-94 punto 2); en `PagoCliente`, `tipo_pago`, `numero`, `usuario` y
  `estado_aviso_cliente` (punto 3); en `Entrega`, `fecha_aviso_mora`, `estado_aviso_mora` (punto 5) e `indemnizacion_retraso_dia` (punto 12: la cláusula vigente al vencer). La secuencia
  `comercial_cobro_numero_seq` (como la de las solicitudes).
  → revisá docs/disparadores.md: cierra lo de COM-08a de los puntos 10 y 11 de «Cuando exista Entrega» y «Completan el ABM de cliente», punto 4.
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_cobranza.py`: la tabla de `LineaPago` con sus restricciones (el índice único parcial de la línea vigente), los
    campos nuevos de `PagoCliente` (`tipo_pago` con valor por omisión `compra_venta` para las filas que ya existan) y de `Entrega`, la
    restricción C7 reescrita y las de `numero`, la secuencia (`RunSQL` con su reverso, como la de las solicitudes);
  - `core/migrations/00NN_comercial_cobranza.py`: solo `choices` (acciones `registro_cobro` y `vencimiento_pago`).
- Permitido fuera de `comercial`: `core/models.py` (las acciones, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`); `core/procesos.py`
  (solo el comentario con la tabla de órdenes, si no tiene el 30); al cerrar (M3), los textos de `docs/disparadores.md`,
  `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`. **No toca `produccion` ni `contabilidad`** (`PagoCliente` ya
  es hija de `OrigenDocumento` desde COM-06a). Dentro de `comercial`, se completan: `estado_de_pago` (COM-06a), `concretar_entrega` (el pago
  de compra-venta con `tipo_pago` y `usuario`; en un suministro, la copia de `indemnizacion_retraso_dia`), `modificar_suministro` (COM-03b:
  actualiza `indemnizacion_retraso_dia` solo en las entregas con `fecha_vencimiento_pago >= hoy`; prueba: una vencida conserva la suya), `resolver_solicitud` y `anular_resolucion` (la llamada a `reevaluar_mora`), la ficha de la
  solicitud, `ficha_de_no_reconocida` y `atender_entrega_no_reconocida` (COM-06b), la ficha del suministro, la ficha y la baja del cliente, la
  parte 4 del paso 50 y la sección «Comercial» del panel. Las pruebas de COM-07a y COM-06b que usaban `mock.patch` de `estado_de_pago` se
  **reemplazan** por otras con un cobro real: anotalas en el PR. Las demás pruebas de COM-06a, COM-06b y COM-07a no se modifican.
- Dependencias nuevas: ninguna.
- Fuera de alcance: anular un cobro, la fecha del cobro anulado (7a) y el cobro de 6a de COM-CNL-CVT (COM-08b); las estadísticas y
  «Resultados del mes en curso» (COM-08c); el asiento del cobro (ronda de contabilidad, D-57); el pago mixto, el pago anterior a su registro,
  la condonación del atraso y el pago a cuenta (temas abiertos del caso de uso).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones** (las fichas; D-94, puntos 2, 3 y 5). Fábricas: `cobro(...)` (un pago de suministro con sus líneas),
   `entrega_en_mora(...)`; `verificar_invariantes_de_cobros()` (`cobranza.md`, «Pruebas»). Pruebas: `comercial/tests/test_modelos_cobranza.py`
   (una por restricción).
2. **Cálculos y estado de pago** (`cobranza.md`, «Cálculos» y «Estado de pago y monto a cobrar»). Pruebas: `test_cobranza_calculos.py` (de
   tabla) y `test_estado_de_pago.py`.
3. **La mora** (`cobranza.md`, «La mora»): el tipo `comercial_pago_en_mora`, `reevaluar_mora`, el registrante del enlace, el aviso de mora.
   Pruebas: `test_reevaluar_mora.py` y la prueba mínima del registrante.
4. **Paso diario 30** (`cobranza.md`, «Paso diario 30»), registrado. Pruebas: `test_com_vnc_pag.py`.
5. **Por cobrar y registrar el cobro** (`cobranza.md`, «Por cobrar», «Entregas cobrables» y «Registrar el cobro»), con el comprobante,
   «Reenviar comprobante» y la parte 4 del paso 50. Pruebas: `test_com_reg_cbr.py`.
6. **Concurrencia.** Pruebas: `test_cobranza_concurrencia.py`.
7. **Lo que completa a otras tareas** (`cobranza.md`, «Lo que completa a otras tareas», filas de 08a): las solicitudes con datos reales (y
   `reevaluar_mora` en la aceptación y en la anulación), COM-ATN-ENR, las fichas del suministro y del cliente, el pago de compra-venta de la
   concreción.
8. **Vistas y plantillas** (`cobranza.md`, «Pantallas»): la pestaña «Cobranza» (sin «Anular»), registrar, la ficha del cobro, el grupo
   «Cobranza» del panel. Pruebas: `test_cobranza_vistas.py`.
9. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de COM-08a de los puntos 10 y 11 de
   «Cuando exista Entrega» y el punto 4 de «Completan el ABM de cliente»; marcar COM-08a en `docs/tareas/README.md` y en el plan; lo distinto
   de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el indicador «Sin confirmar por el cliente» del panel y la ficha del cobro (los cobros se ven
igual en «Cobros registrados»; queda en `docs/temas_abiertos.md`). No se recortan las restricciones de la base, los bloqueos, la huella, la
fecha guardada de la mora ni las pruebas de concurrencia.

## Hecho cuando

- El Vendedor ve en «Cobranza» a sus clientes con deuda (total y en mora), elige las entregas que el cliente paga, ve la indemnización por
  atraso de cada una y el total, elige el medio y confirma: queda el cobro `COB-NNNN` con sus entregas «pagadas», la alerta resuelta, el
  comprobante enviado y, si cobró el Gerente, el aviso al Vendedor.
- No se puede cobrar dos veces una entrega, ni una saldada, ni una de otro cliente, ni una de un contrato ajeno; si cambió algo mientras
  tanto (otro cobro, una aceptación, el día), el sistema lo dice y vuelve con los datos nuevos.
- `python manage.py proceso_diario --solo vencer_pagos` pone en mora las entregas vencidas (alerta, aviso y correo) y, corrido otra vez, no
  repite nada.
- Una aceptación que salda una entrega en mora resuelve su alerta; una aceptación después del cobro reintegra (con un cobro real); la
  anulación de una solicitud de una entrega cobrada con descuento se rechaza (2b) con un cobro real.
- Todas las pruebas de `comercial` y `core` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial` y `core`, esta solo `choices`): `python manage.py migrate`. Datos: los de COM-07b, con un cliente de
suministro **con un correo que puedas leer**, un suministro con plazo de pago de 10 días y $ 300 por día de atraso, tres entregas concretadas
(una con fecha de concreción de hace 15 días, otra de hace 5, otra con una discrepancia pendiente).

1. Corré `python manage.py proceso_diario --solo vencer_pagos`: la entrega de hace 15 días queda en mora; el Gerente tiene la alerta «Pago en
   mora», el Vendedor el aviso y el cliente el correo. Corré otra vez: nada nuevo.
2. Con el Vendedor, en «Cobranza»: el cliente con su total y lo que está en mora. «Registrar cobro»: las tres entregas, de la que vence
   primero a la última, la de la discrepancia con su advertencia. Elegí la de mora: 5 días de atraso, $ 1.500,00. Revisá y confirmá: llega el
   comprobante; la alerta del Gerente se resuelve; la ficha del suministro dice «Pagada · COB-0001».
3. Desde la alerta (con el Gerente, en otra entrega en mora): la pantalla abre con la entrega elegida; cobrala; el Vendedor recibe el aviso.
4. En dos pestañas, cobrá la misma entrega: la segunda dice que ya está pagada, con el cobro, la fecha y quién.
5. Aceptá la discrepancia de la entrega ya cobrada: se pide el medio del reintegro (6a). Intentá anular esa resolución: «No se puede anular:
   la indemnización ya se le reintegró…» (2c).
6. Con el Vendedor de otro contrato: no ve las entregas ajenas; por URL, 403.
7. Sin JavaScript: registrar un cobro funciona.
8. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
