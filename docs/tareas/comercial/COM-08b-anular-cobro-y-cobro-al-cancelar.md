# COM-08b · Anular un cobro y cobrar lo entregado al cancelar una compra-venta

Estado: pendiente | App: comercial | Rama: feature/com-08b-anular-cobro | Ronda: Comercial 1

Depende de: **COM-08a** (`LineaPago`, `estado_de_pago` con «pagada», `reevaluar_mora`, `registrar_cobro`, la pestaña «Cobranza») y, con ella,
toda la cadena. Usa de COM-07a `Anulacion` y de COM-05b `cancelar_compra_venta`. Si COM-08a no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La segunda de las tres partes de COM-08 (D-94, punto 1): el Gerente **anula un cobro de suministro** mal cargado sin
borrarlo (queda «anulado» con su historia y su `Anulacion`), las entregas vuelven a estar sin pagar (y en mora, con su alerta, si ya
vencieron) y, si el cliente sí había pagado ese día, **registra el cobro correcto con la fecha original**, para no cobrarle un atraso que no
tuvo. Además, una compra-venta con entregas concretadas **se puede cancelar**: lo entregado se cobra en la misma operación y la venta queda
«concretada» (extensión 6a de COM-CNL-CVT).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-ANL-CBR | Anular Cobro | docs/casos_de_uso/comercial/cobranza.md («Anular un cobro») | Postcondición c (contraasiento): fuera, D-57 |
| COM-REG-CBR | Registrar Cobro de Suministro: la fecha del cobro anulado (7a de COM-ANL-CBR; D-94, punto 10) | docs/casos_de_uso/comercial/cobranza.md | — |
| COM-CNL-CVT | Cancelar Compra-venta: extensión 6a (el cobro de lo entregado) | docs/casos_de_uso/comercial/compra_venta.md («La extensión 6a (COM-08b)») | El asiento del cobro: fuera, D-57 |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/cobranza.md **completo**; de compra_venta.md, «COM-CNL-CVT» y su «Cómo se aplica» **completo**
  (con «La extensión 6a (COM-08b)»); de solicitudes.md, «Anular una resolución» (2b) y «Lo que completa a otras tareas»; de confirmacion.md,
  «Atender una entrega no reconocida» (regla 5).
- Modelo: docs/modelo/comercial.md (**Anulacion**, **PagoCliente** —`anulacion_corregida`—, LineaPago, Entrega, CompraVenta, DetalleVenta).
- Decisiones: **D-94** (puntos 5, 8 a 11, 13, 14 y 16), D-69 (punto 10), D-68 (punto 4), D-67 (punto 4), D-65, D-57, D-42, D-36.
- Patrones: docs/patrones/bloqueos.md («Cobranza» y «Cancelar una compra-venta»), docs/patrones/auditoria.md.
- API: docs/api/alertas.md (secciones 2 y 8); docs/api/notificaciones.md.
- Pantallas: docs/prototipos/comercial/ (`README.md`): `MODALS.anlcbr` (línea 1198), `ACT['anlcbr-ok']` (línea 1199), `tabCobranza` (rama
  `cob`), `VIEWS.cobro` (la fecha con `S.p.fc`, línea 1788), `VIEWS.cvcancel` (la sección 3 «Cobro de lo entregado»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `comercial/servicios/cobranza.py` y sus vistas (COM-08a), `servicios/compra_ventas.py` (`cancelar_compra_venta`,
  `datos_de_cancelacion`, la huella), `servicios/comprobantes.py`, `servicios/solicitudes.py` (2b), `servicios/atencion.py` (regla 5),
  `models.py` (`Anulacion`, `PagoCliente`), las fábricas e invariantes; `core/models.py`, `core/notificaciones.py`.

## Límites

- Crea modelos (en `comercial`): en `Anulacion`, `pago` y `cliente_pago_en_fecha` (D-94, punto 11); en `PagoCliente`, `anulacion_corregida`
  (punto 10).
  → revisá docs/disparadores.md: cierra el punto 9 de «Cuando exista Entrega» (lo de COM-08) y lo de COM-08b del punto 11.
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_anulacion_de_cobro.py`: los campos nuevos y las restricciones de `Anulacion` reescritas («exactamente uno de
    `solicitud` y `pago`», `pago` ⇔ `cliente_pago_en_fecha`, `solicitud` ⇔ `estado_anulado`);
  - `core/migrations/00NN_comercial_anulacion_cobro.py`: solo `choices` (acción `anulacion_cobro`).
- Permitido fuera de `comercial`: `core/models.py` (la acción, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`); al cerrar (M3), los
  textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`. Dentro de `comercial`:
  `registrar_cobro` y su pantalla suman `anulacion_id` y `usar_fecha_anulada` (7a); `cancelar_compra_venta` y su pantalla, la extensión 6a. La
  prueba de COM-05b que esperaba `venta_con_entregas_concretadas` se **reemplaza** (anotala en el PR); las demás de COM-05b y COM-08a no se
  modifican.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el contraasiento y el asiento del cobro de 6a (ronda de contabilidad, D-57); anular un cobro de compra-venta (1a: se
  corrige con CU-17); una fecha anterior fuera del camino de 7a (tema abierto «Pago anterior a su registro»).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones** (las fichas; D-94, puntos 10 y 11). Fábricas: `anulacion_de_cobro(...)`; los invariantes nuevos en
   `verificar_invariantes_de_cobros` (un pago anulado tiene exactamente una `Anulacion`; un cobro con `anulacion_corregida` tiene solo entregas
   del cobro anulado). Pruebas: métodos nuevos en `test_modelos_cobranza.py`.
2. **Anular un cobro** (`cobranza.md`, «Anular un cobro»). Pruebas: `test_com_anl_cbr.py`.
3. **El cobro correcto** (7a; `cobranza.md`, «Anular un cobro», paso 7, y «Registrar el cobro», fecha del pago). Pruebas: en
   `test_com_anl_cbr.py`, las de 7a; en `test_com_reg_cbr.py`, `fecha_no_admitida` y `anulacion_ya_usada`.
4. **La extensión 6a de COM-CNL-CVT** (`compra_venta.md`, «La extensión 6a (COM-08b)»). Pruebas: métodos nuevos en `test_com_cnl_cvt.py`.
5. **Concurrencia.** Pruebas: `test_anulacion_cobro_concurrencia.py` y el método nuevo de `test_com_cnl_cvt_concurrencia.py`.
6. **Vistas y plantillas**: «Anular» en «Cobros registrados» y en la ficha del cobro (solo el Gerente), la ventana, la pantalla final con
   «Registrar el cobro correcto», la fecha de 7a en la pantalla de registro, la sección «Cobro de lo entregado» de la cancelación. Pruebas: en
   `test_cobranza_vistas.py` y `test_com_cnl_cvt.py` (`ComCnlCvtVistaTests`).
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar el punto 9 de «Cuando exista Entrega» (lo de
   COM-08) y lo de COM-08b del 11; marcar COM-08b en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a
   `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es mostrar en la ficha del cobro anulado el cobro que lo corrigió (el vínculo se guarda igual;
queda en `docs/temas_abiertos.md`). No se recortan los bloqueos, la relectura, los límites de 7a ni las pruebas de concurrencia.

## Hecho cuando

- El Gerente anula un cobro de suministro con un motivo: el cobro queda «anulado» con su historia, la `Anulacion` registrada, las entregas
  vuelven a «pendiente» o «en mora» (con su alerta activa si están en mora; el correo de mora solo si nunca había salido) y el Vendedor recibe
  el aviso. Un cobro de compra-venta no se anula desde acá.
- Si indicó que el cliente sí pagó, «Registrar el cobro correcto» abre el cobro con las mismas entregas y la fecha original, y la
  indemnización por atraso es la de esa fecha. Esa fecha no se puede usar para otras entregas ni dos veces.
- Después de anular, la anulación de una solicitud de esas entregas (2b) y la atención de una entrega no reconocida (regla 5) dejan de
  rechazar.
- Una compra-venta con una entrega concretada se cancela: lo entregado se cobra con el medio elegido, la venta queda «concretada» con los datos
  de la cancelación y el comprobante muestra el cobro.
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

Hay migraciones nuevas (`comercial` y `core`, esta solo `choices`): `python manage.py migrate`. Datos: los de COM-08a, con un cobro de dos
entregas (una ya vencida al cobrarse) y una compra-venta con envío desde dos invernaderos con una de sus entregas concretada.

1. Con el Gerente, en «Cobros registrados», «Anular» el cobro: la ventana dice qué entrega vuelve a «en mora» y cuál a «pendiente». Sin
   motivo: error. Con motivo y «El cliente pagó en esa fecha»: el cobro queda «Anulado», la campana tiene otra vez «Pago en mora», el
   Vendedor recibe el aviso y el cliente **no** recibe otro correo.
2. «Registrar el cobro correcto»: las dos entregas elegidas, la fecha del cobro anulado con su texto, la misma indemnización de antes.
   Confirmá. Volvé a la URL con la misma anulación: «El cobro correcto de esa anulación ya se registró».
3. Anulá otro cobro sin marcar la casilla: el cobro nuevo tiene la fecha de hoy y la indemnización a hoy.
4. Con el Vendedor: «Cobros registrados» sin «Anular»; por URL, 403.
5. Cancelá la compra-venta de dos invernaderos: la sección «Cobro de lo entregado» pide el medio; confirmá: la venta queda «Concretada», la
   entrega pendiente se cancela y el comprobante muestra el cobro.
6. Sin JavaScript: anular y cancelar con cobro funcionan.
7. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
