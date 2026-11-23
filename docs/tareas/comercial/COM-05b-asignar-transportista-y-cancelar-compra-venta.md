# COM-05b · Asignar transportista y cancelar la compra-venta

Estado: pendiente | App: comercial | Rama: feature/com-05b-asignar-transportista-y-cancelar-compra-venta | Ronda: Comercial 1

Depende de: **COM-05a2** (y, con ella, COM-05a1: `Entrega`, `candidatos_para`, `peso_de_entregas`, `en_curso`, la lista de entregas,
`cancelar_entrega_incluida`, la acción `asignacion_transportista`; y todo lo anterior: `cancelar_cosecha_incluida` de COM-04a,
`crear_partida` y `costo_unitario_de_cosecha` del núcleo, PROD-ASG-CAM de COM-04b, `anular_enlaces_de` de COM-04c, los comprobantes de
COM-02). Si COM-05a2 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Lo que una **persona** hace sobre una entrega que ya existe o sobre la venta (D-66, punto 1): el Vendedor (o el Gerente)
**asigna o cambia el transportista** de una entrega, eligiendo entre los que pueden llevarla ese día (COM-ASG-TRP), y **cancela una
compra-venta** que el cliente ya no quiere: libera todo lo reservado, manda a la cámara lo ya cosechado, cancela las cosechas y las entregas
pendientes, anula el enlace de decisión y le manda al cliente el comprobante (COM-CNL-CVT, que incluye PROD-CNL-ORD). La alerta «entrega sin
transportista» pasa a llevar al Gerente directo a la asignación. **No toca `produccion`.**

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-ASG-TRP | Asignar Transportista a Entrega | docs/casos_de_uso/comercial/entregas.md (sección «COM-ASG-TRP» y su «Cómo se aplica») | 9a: las notificaciones van dentro de la transacción (D-42); el correo, con reintento en el paso 50 (D-66, punto 12) |
| COM-CNL-CVT | Cancelar Compra-venta | docs/casos_de_uso/comercial/compra_venta.md (sección «COM-CNL-CVT» y su «Cómo se aplica») | Extensión 6a y el cobro (postcondición f): COM-06 y COM-08. Asiento del cobro: **Fuera de esta ronda · contabilidad** (D-57). Detalles confirmados sin entregar: se cancelan (D-67, punto 4) |
| PROD-CNL-ORD | Cancelar Orden, incluida por COM-CNL-CVT (cosechas y entregas de la venta) | docs/casos_de_uso/produccion/cancelar_orden.md (sección «Comercial 1»: la compra-venta cancelada) | Sin código nuevo de cancelación: usa `cancelar_cosecha_incluida` y `cancelar_entrega_incluida` |

## Leer

- Casos de uso: de docs/casos_de_uso/comercial/entregas.md, **la sección «COM-ASG-TRP» completa** (el caso de uso, «Cómo se aplica», «Pantallas»,
  «Lo que difiere» y «Pruebas») y, de lo de COM-05a1, «Candidatos, verificaciones y selección», «Avisos y textos», «Alerta…» y «Auditoría»; de
  docs/casos_de_uso/comercial/compra_venta.md, **la sección «COM-CNL-CVT» completa** (con «Cambios ya decididos», «Cómo se aplica» y la
  contradicción de los confirmados) y, de lo de COM-02, «COM-CNS-CVT» (reglas 4 y 5) y el comprobante de «COM-REG-CVT»; de
  docs/casos_de_uso/produccion/cancelar_orden.md, las secciones «Comercial 1»: cosechas (`cancelar_cosecha_incluida`), «entregas y envasado»
  (`cancelar_entrega_incluida`) y «la compra-venta cancelada»; de faltante.md, el paso 6.4 (el rechazo: es el mismo cálculo de la partida).
- Modelo: docs/modelo/comercial.md (**CompraVenta** con los datos de MD-130 y sus restricciones; **DetalleVenta**, el estado «cancelado»;
  ReservaStock, DetalleReserva, Entrega, DetalleEntrega, EnlaceCliente); docs/modelo/produccion.md (StockCosechado: el motivo
  `cancelacion_cliente`).
- Decisiones: **D-67** (la de esta tarea, puntos 3 y 4), D-66 (puntos 9 a 12), D-65, D-64 (puntos 3 y 12), D-59, D-61, D-55, D-14, D-25, D-27,
  D-28, D-29, D-36, D-37, D-40, D-42, D-44, D-54, D-57.
- Patrones: docs/patrones/bloqueos.md (sección `comercial`: «Cosecha y cámara» y «Entregas y envasado», con «Asignar un transportista» y
  «Cancelar una compra-venta»), docs/patrones/stock_maduro.md (secciones 1 y 8), docs/patrones/enlace_del_cliente.md (`anular_enlaces_de`),
  docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: docs/api/produccion.md (secciones 1 y 8: `cancelar_orden_incluida`, `crear_partida`, `costo_unitario_de_cosecha`; no se cambian),
  docs/api/alertas.md (secciones 1, 2, 4 y 8), docs/api/notificaciones.md.
- Disparadores: docs/disparadores.md — «Cuando exista Entrega», puntos 2, 7, 8 y 9.
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `tabEntregas` (las acciones), `INIT.asg`, `VIEWS.asg` y `candidatos` (vale
  la última definición), `ACT['asg-ok']`; `VIEWS.cv` (el botón), `INIT.cvcancel`, `VIEWS.cvcancel`, `ACT['cvcancel-ok']`. Lo que difiere está
  en «Lo que difiere del prototipo» de cada sección.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-05a2): modelos, `servicios/` (`entregas.py`, `compra_ventas.py`, `cosechas.py`, `camara.py`,
    `faltantes.py`, `enlaces.py`, `comprobantes.py`, `stock_maduro.py`, `vehiculos.py`), vistas y plantillas de entregas y de compra-venta,
    `apps.py` (el registrante del enlace de la alerta), fábricas, `verificar_invariantes_de_reservas` y `verificar_invariantes_de_entregas`;
  - `produccion/servicios/ordenes.py` y `camara.py`, para **usarlos**;
  - `maestros/servicios/invernaderos.py` (`bloquear_invernadero_activo`, `bloquear_invernadero_para_alertas`), `maestros/extensiones.py`
    (`registrar_enlace_de_alerta`), `maestros/servicios/alertas.py`;
  - `core/notificaciones.py`, `core/correo.py`, `core/models.py` (auditoría).

## Límites

- Crea modelos: en `comercial`, los tres campos de MD-130 en `CompraVenta` con sus restricciones (`docs/modelo/comercial.md`) y, **si COM-02
  no lo creó**, el valor `cancelado` de `DetalleVenta.estado_detalle_venta` (la ficha lo lista desde COM-02: miralo en el código).
  → revisá docs/disparadores.md: cierra los de la sección 9 del plan para COM-05b (paso 7).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_cancelacion_compra_venta.py`: los tres campos, sus restricciones y, si hace falta, los `choices` del detalle;
  - `core/migrations/00NN_comercial_cancelacion_compra_venta.py`: solo `choices` (acción `cancelacion_compra_venta`;
    `asignacion_transportista` ya existe).
  **Ninguna en `produccion`.**
- Permitido fuera de `comercial`:
  - `core`: en `core/models.py`, la acción, `ETIQUETAS` (los campos nuevos), `VALORES_VISIBLES` (`motivo_cancelacion_venta`) y
    `ACCIONES_DE_NEGOCIO`;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md`, `docs/temas_abiertos.md`
    y `docs/estado.md`.
  **Nada de `produccion` ni de `maestros`**: lo que se usa de ellas ya existe.
- Dependencias nuevas: ninguna.
- Fuera de alcance: la extensión 6a de COM-CNL-CVT y el cobro de lo entregado (COM-06 deja el rechazo con datos reales y COM-08 el cobro, con
  `PagoCliente`; disparador «Cuando exista Entrega», punto 9); los asientos (D-57); iniciar la ruta, concretar y el intento fallido (COM-06:
  hasta entonces, «en curso» solo se da con un vehículo de fábrica); la cancelación automática de una venta que nunca se retira (el caso de uso
  no la tiene); quitar el transportista de una entrega sin poner otro (decisión D de COM-ASG-TRP); reintentos automáticos de notificaciones.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y auditoría** (MD-130). Los tres campos de `CompraVenta` con sus restricciones; el valor `cancelado` si falta; la acción de
   `core`. Fábricas: `venta_con_todo(...)` (una venta con un detalle abierto con cosecha «a realizar», otro con líneas de lote ya cosechadas y
   de cámara, y su entrega «a realizar» con envases), `vehiculo_en_ruta(...)`.
   Pruebas: en `comercial/tests/test_modelos_compra_venta.py` (o el archivo de modelos de COM-02), métodos nuevos: cada restricción, la viola
   y no la viola (una venta cancelada por COM-DCD-FLT sin motivo no la viola).
2. **COM-ASG-TRP, servicios** (`entregas.md`, «COM-ASG-TRP», «Servicios» y «Reglas en el código»): `datos_de_asignacion`,
   `resumen_de_asignacion`, `huella_de_entrega`, `asignar_transportista`; el registrante del enlace de la alerta cambia a la asignación (1b).
   Pruebas: `comercial/tests/test_com_asg_trp.py`, `ComAsgTrpServicioTests` (la lista de «Pruebas» de la sección).
3. **COM-CNL-CVT, servicios** (`compra_venta.md`, «COM-CNL-CVT», «Servicios» y «Reglas en el código»): `datos_de_cancelacion`,
   `resumen_de_cancelacion_de_venta`, `huella_de_venta`, `cancelar_compra_venta`; el comprobante de cancelación en `comprobantes.py`.
   Pruebas: `comercial/tests/test_com_cnl_cvt.py`, `ComCnlCvtServicioTests` (la lista de «Pruebas» de la sección) y los métodos nuevos de
   `test_prod_cnl_ord_entregas.py` y `test_cancelar_cosecha_incluida.py` (`cancelar_orden.md`, «la compra-venta cancelada»).
4. **Concurrencia**: los métodos nuevos de `test_entregas_concurrencia.py` (COM-ASG-TRP) y `test_com_cnl_cvt_concurrencia.py` (COM-CNL-CVT);
   en `test_entregas_concurrencia.py`, también la que COM-05a1 dejó para esta tarea («una planificación contra la cancelación de la misma
   venta»).
5. **Vistas y plantillas.** En la lista de entregas, «Asignar transportista» y «Cambiar transportista» (y «En curso» sin acción); la pantalla
   de asignación con su `calcular/` y el respaldo «Ver cómo queda»; en la ficha de la compra-venta, «Cancelar compra-venta» y los datos de una
   venta cancelada; la pantalla de cancelación con su `revisar/` y la ventana de resumen; «Imprimir comprobante» sin correo. Vistas que solo
   orquestan, `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript, errores por campo y aviso breve
   (D-29): «OT-0231 asignada a Ana Pérez.» (con «Se reprogramó para hoy y se avisó el retraso.» en 4a); «CV-0044 cancelada. Se canceló 1
   cosecha y 1 entrega; 40 plantas entraron a la cámara.» más lo del comprobante.
   Pruebas: `ComAsgTrpVistaTests` y `ComCnlCvtVistaTests` (las de las dos secciones) y los métodos nuevos de `test_entregas_vistas.py`.
6. **Invariantes**: `verificar_invariantes_de_reservas()` y `verificar_invariantes_de_entregas()` después de cada prueba de los pasos 2 y 3
   que escribe (ninguna reserva de un detalle cancelado queda sin liberar; ninguna entrega «a realizar» de una venta cancelada).
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de COM-05b (la fila de la sección 9 del
   plan) y confirmar el punto 9 (lo que queda para COM-06 y COM-08); la fila de la tarea en `docs/tareas/README.md` y en el plan; lo distinto
   de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el respaldo «Ver cómo queda» sin JavaScript de la asignación (queda en
`docs/temas_abiertos.md`; la asignación sin JavaScript sigue funcionando, con el resumen después de elegir). No se recortan las restricciones de
la base, los bloqueos, la relectura de 8a y 8b de los dos casos de uso, la cancelación de los confirmados sin entregar ni las pruebas de
concurrencia.

## Hecho cuando

- El Vendedor (o el Gerente) asigna un transportista a una entrega sin transportista, o la cambia de transportista, eligiendo entre los que
  pueden llevarla ese día; la alerta se resuelve, los dos transportistas y (si actuó el Gerente) el Vendedor reciben el aviso, y si la fecha
  ya había pasado, la entrega sale hoy con el aviso de retraso y el correo al cliente. Una entrega en curso no se reasigna.
- Desde la alerta «entrega sin transportista», el Gerente llega directo a la asignación de esa entrega.
- El Vendedor (o el Gerente) cancela una compra-venta abierta o pendiente sin entregas en curso: todo lo reservado se libera, lo cosechado
  entra a la cámara (y se asigna solo a quien lo espera), las cosechas y entregas pendientes se cancelan con aviso a quienes las tenían, el
  enlace de decisión queda anulado y el cliente recibe el comprobante (o se imprime).
- Todas las pruebas de `produccion`, `maestros`, `core`, `inventario` y de las tareas anteriores de `comercial` siguen pasando.
- Comando de pruebas:
  python manage.py test comercial produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial`, `core`): `python manage.py migrate`. Datos: los de COM-05a2 (invernadero «Sur» con Juan —camioneta de
50 kg— y Ana —furgón de 400 kg—, un envase con stock, un cliente con correo y otro sin correo); en «Configuración», máximo de entregas diarias 2
y de localidades 2.

1. Con una entrega sin transportista (la del punto 2 de COM-05a1): en la campana del Gerente, «Entrega sin transportista»; abrila: lleva a
   «Asignar transportista · OT-…». Juan aparece con «Capacidad de carga insuficiente» y no se puede elegir; elegí a Ana: «Cómo queda» muestra
   su carga y sus entregas del día. «Asignar transportista»: la alerta queda resuelta, Ana tiene «Nueva entrega…» y el Vendedor «OT-… ya tiene
   transportista». En «Auditoría», un `asignacion_transportista` con el Gerente.
2. Con el Vendedor, en «Comercial › Entregas», «Cambiar transportista» de una entrega de Ana para mañana: elegí otro que cumpla; Ana recibe
   «Ya no tenés la entrega…».
3. Con una entrega de fecha pasada sin transportista: la pantalla avisa que sale hoy; asignala: la fecha pasa a hoy, el Vendedor tiene «Entrega
   con retraso» y el cliente el correo con la fecha nueva.
4. Abrí la asignación de la misma entrega en dos pestañas; asigná en una y después en la otra: «La entrega cambió mientras la mirabas».
5. Con el Vendedor, una compra-venta con dos detalles: uno con su cosecha «a realizar» y otro ya cosechado con su entrega «a realizar» y 20
   bandejas reservadas. En su ficha, «Cancelar compra-venta»: la pantalla dice qué vuelve a los lotes, qué entra a la cámara (con su fecha
   límite) y qué cosecha y qué entrega se cancelan. Sin motivo: error. Elegí «El cliente desistió», «Revisar y cancelar», confirmá.
6. La venta queda «Cancelada» con el motivo y la fecha; en la pestaña «Cámara» aparece la partida «Cancelación del cliente»; la cosecha y la
   entrega quedan canceladas; el Capataz, el Agrónomo y el transportista tienen el aviso; las bandejas vuelven a estar libres; el cliente
   recibió el comprobante. En «Auditoría», un `cancelacion_compra_venta`.
7. Repetí con una venta «pendiente de decisión del cliente»: después de cancelar, el enlace del correo dice «Este enlace no se puede usar».
8. Con el cliente sin correo: al terminar, «El cliente no tiene correo: imprimí el comprobante.» y el botón «Imprimir comprobante».
9. Sin JavaScript: la asignación y la cancelación funcionan con el resumen como página.
10. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
