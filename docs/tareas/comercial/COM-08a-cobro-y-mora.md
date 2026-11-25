# COM-08a · Cobro de suministros y mora (paso diario 30)

Estado: hecha (25/11/2026; revisión a mano pendiente) | App: comercial | Rama: feature/com-08a-cobro-y-mora | Ronda: Comercial 1

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

## Verificación a mano (la completó Claude Code al cerrar; la hace el estudiante)

Sin datos cargados (D-95, D-96): el cargador de verificación de la primera versión de esta tarea se retiró y no vuelve; los datos los creás vos a mano con los valores de abajo. Cada paso dice si ya lo cubre una prueba (el recorrido es `comercial/tests/test_recorrido_cobranza.py`).

**Antes de empezar**

1. En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `comercial` 0013, que crea la tabla de líneas de pago, los campos nuevos del pago y de la entrega y la secuencia `comercial_cobro_numero_seq`, y `core` 0051, solo `choices`) y `python manage.py runserver`. Abrí `http://localhost:8000/`.
2. Cuentas que necesitás (las de prueba que ya usás): **Gerente**, **Vendedor** del invernadero, **otro Vendedor** que no tenga ningún contrato (para ver que no ve nada ajeno), **Agrónomo** y **Capataz** del invernadero y un **Transportista** con un vehículo activo asignado al invernadero (Gerente: «Comercial» → pestaña «Vehículos»).
3. Lo que tiene que existir (si ya lo tenés de otras verificaciones, usalo): un invernadero activo con su Agrónomo, Capataz y Vendedor; una variedad con un lote en Maduración de por lo menos **300 plantas**; un insumo «envase» con stock habilitado en el invernadero; y un **cliente con un correo que puedas leer**, con una dirección (Comercial → Clientes → «Nuevo cliente»). Por ejemplo: persona jurídica «Verdulería Los Pinos S.R.L.», CUIT **30-71234567-1**, correo el tuyo.
4. **Correo en desarrollo.** Para ver los correos sin un servidor real, en tu `.env` local dejá `CORREO_CONSOLA=1` (el correo se imprime en la terminal del `runserver`; sin esa variable ni credenciales, los avisos al cliente quedan «pendientes de envío» y es lo que prueba el paso 13).
5. **Pactar el suministro** (Vendedor: Comercial → Contratos → Suministros → «Pactar suministro») con estos valores: cliente, el de arriba; duración **6** meses; incumplimientos tolerados **3**; multa por resolución **50000**; plazo de pago **10** días; indemnización por atraso en el pago **300**; un detalle con la variedad del lote, la dirección del cliente, **50** plantas cada **7** días, primera entrega **hoy**, precio fijo **20** (cada entrega vale $ 1.000,00), tolerancia de entrega **0**, retraso **100** por día, cantidad mínima **30** y faltante **30** por planta. «Ver resumen» y «Confirmar».
6. **Tres entregas concretadas del mismo cliente.** Es la parte más larga y es la misma de COM-07b (pasos 6 y 7 de su «Antes de empezar»): `python manage.py proceso_diario --solo pre_reservar_suministros` y después `--solo planificar_entregas`; la cosecha la concreta el Capataz; el Transportista inicia la ruta y **concreta** la entrega. Repetí para llegar a **tres** entregas concretadas del mismo cliente (podés pactar un segundo y un tercer suministro del mismo cliente con las mismas condiciones, cada uno con su primera entrega «hoy»). En una de ellas (la que va a ser la **tercera**, `C`), concretá con **20** plantas recibidas de 50 (el mínimo es 30): crea una discrepancia pendiente (Comercial → Solicitudes). Si ya tenés entregas concretadas de verificaciones anteriores (COM-06a, COM-07a o COM-07b), usalas: sirven las de un suministro, con el plazo de pago y la indemnización que tengan.
7. **Envejecerlas.** Concretar siempre fecha hoy, así que para que haya mora hay que mover las fechas en tu base local de desarrollo (solo ahí). En la terminal: `python manage.py shell` y pegá, cambiando los números por los de tus entregas (`OT-0231` es el número 231; los ves en Comercial → Entregas):

   ```python
   from datetime import timedelta
   from django.utils import timezone
   from comercial.models import Entrega
   hoy = timezone.localdate()
   # (número de la entrega, hace cuántos días se concretó)
   for numero, dias in ((231, 15), (232, 14), (233, 5)):
       concretada = hoy - timedelta(days=dias)
       Entrega.objects.filter(numero=numero).update(fecha_resolucion_orden=concretada, fecha_vencimiento_pago=concretada + timedelta(days=10))
   ```

   Queda: `A` (OT-0231) venció hace **5** días, `B` (OT-0232) venció hace **4** días y `C` (OT-0233, la de la discrepancia) vence en **5** días. Si tus entregas tienen otro plazo de pago, calculá `fecha_vencimiento_pago` con el tuyo.

**Los pasos**

1. **El paso diario 30, a mano.** En la terminal: `python manage.py proceso_diario --solo vencer_pagos`. **Tiene que ver:** «Vencer pagos de suministro: procesados 2 · creados 2 · resueltos 0 · 0 correos de mora pendientes» (las dos entregas vencidas, `A` y `B`). Gerente: campana → «Alertas»: dos alertas **rojas** «Pago en mora» con «OT-0231 · Verdulería Los Pinos S.R.L. · SUM-… · $ 1.000,00 · venció el dd/mm · $ 300,00 por día de atraso». Vendedor: campana → «Notificaciones»: «OT-0231 en mora» («… no pagó OT-0231 (SUM-…): $ 1.000,00, venció el dd/mm. Desde hoy suma $ 300,00 por día de atraso.»). Correo (en la terminal del servidor, con `CORREO_CONSOLA=1`): «Pago en mora de la entrega OT-0231» con el monto, el vencimiento y los $ 300,00 por día. **Corrélo otra vez:** «procesados 0 · creados 0»; ninguna alerta, aviso ni correo nuevo. *(Lo cubre el recorrido, paso 1, y `test_com_vnc_pag.py`.)*
2. **Por cobrar (Vendedor).** Entrá como el **Vendedor** → «Comercial» → pestaña «Cobranza» (con el número rojo **2**). **Tiene que ver:** arriba el texto «Las entregas de suministro se cobran después de entregarlas…»; el cliente «Verdulería Los Pinos S.R.L.» con «3 entregas», **Total a cobrar $ 3.000,00 · $ 2.000,00 en mora** (en rojo), desplegado; sus tres entregas de la que vence primero a la última (`A`, `B`, `C`), cada una con «hace 5 días» / «hace 4 días» / «en 5 días» y «En mora · 5 días», «En mora · 4 días» y «Pendiente». Ningún botón «Anular» (es de COM-08b). La subpestaña «Cobros registrados» dice «No hay cobros registrados.». *(Lo cubre `test_cobranza_vistas.py`, `PestanaTests`.)*
3. **Registrar un cobro (el camino feliz).** «Registrar cobro» del cliente. **Tiene que ver:** «1 Cliente» fijo («Se registra el cobro de este cliente.»), «2 Entregas que paga» con las tres entregas y, en `C`, la marca «Discrepancia SR-… pendiente (dd/mm)». Marcá **solo `A`**. **Tiene que ver:** «A: 5 días de atraso · $ 1.500,00», el resumen de la derecha con «Montos a cobrar $ 1.000,00», «Indemnización por atraso en el pago $ 1.500,00», «**Total a cobrar $ 2.500,00**»; aparece «3 Pago» con el medio y «Es la fecha de hoy: no se registran cobros con fecha anterior.». Marcá también `C`: aparece la advertencia amarilla «Una entrega elegida tiene una queja o una discrepancia pendiente… se reintegra al cliente.»; desmarcá `C`. **Sin elegir el medio**, «Revisar y registrar»: vuelve con «Elegí el medio de pago.» junto al campo y **no** muestra el resumen. Elegí **Transferencia** y «Revisar y registrar»: la página «Revisá el cobro» con la entrega, «5 días · $ 1.500,00», «$ 2.500,00», «Transferencia», la fecha de hoy y «Fuera de esta ronda · contabilidad». **Todavía no se escribió nada:** «Cobros registrados» sigue vacía (abrila en otra pestaña). «Confirmar cobro». **Tiene que ver:** la ficha del cobro «COB-0001» con el aviso verde «COB-0001 registrado: $ 2.500,00 cobrados a Verdulería Los Pinos S.R.L.…», «Registrado por» el Vendedor, «Total cobrado $ 2.500,00» y «El comprobante se envió al cliente.»; el correo «Comprobante de cobro COB-0001» en la terminal (con el detalle de la entrega, «Atraso: 5 días; indemnización por atraso: $ 1.500,00», «Total cobrado: $ 2.500,00» y «Comprobante interno, sin validez fiscal.»). Gerente: la alerta de `A` **ya no está** en la campana (la de `B` sigue). La ficha del suministro de `A` dice «**Pagada · COB-0001**» y ya no suma esa entrega al total de Cobranza. En «Auditoría» (Gerente): un registro «Registro de cobro de suministro» del Vendedor con el cobro, su línea y la alerta resuelta. *(Lo cubre el recorrido, paso 2, y `test_com_reg_cbr.py`.)*
4. **Desde la alerta (Gerente).** Entrá como **Gerente**, campana → «Alertas» → la de `B` («Pago en mora»). **Tiene que ver:** que abre «Registrar cobro» con el cliente fijo y **`B` ya marcada**, y el detalle de la alerta dice «En mora desde el dd/mm · 4 días · $ 1.200,00 por atraso». Elegí **Efectivo**, «Revisar y registrar» y «Confirmar cobro». **Tiene que ver:** «COB-0002» por **$ 2.200,00** ($ 1.000,00 + 4 × $ 300,00). El **Vendedor** recibe, en «Notificaciones», «COB-0002 registrado»: «El Gerente registró el cobro de Verdulería Los Pinos S.R.L.: OT-0232 (SUM-…), $ 2.200,00 en efectivo, con $ 1.200,00 de atraso.»; la alerta de `B` se va. *(Lo cubre el recorrido, paso 3.)*
5. **La entrega de la alerta ya está cobrada.** Con la alerta de `A` o `B` ya resuelta no queda enlace; escribí a mano `/comercial/cobranza/registrar/?entrega=<id de B>` (el id lo ves en el `shell`: `from comercial.models import Entrega; Entrega.objects.get(numero=232).pk`). **Tiene que ver:** vuelve a «Cobranza» con el aviso «OT-0232 ya está pagada: COB-0002, el dd/mm/aaaa, registrado por …». *(Lo cubre `test_ext_1a1_…`.)*
6. **Dos pestañas, la misma entrega.** Abrí **dos pestañas** como Gerente, las dos en «Registrar cobro» de `C` (desde la ficha del cliente → «Registrar cobro»). En la primera: marcá `C`, medio **Efectivo**, «Revisar y registrar» (sin confirmar todavía). En la segunda: lo mismo y «Confirmar cobro» (queda registrada, COB-0003). Volvé a la primera y apretá «Confirmar cobro». **Tiene que ver:** la pantalla vuelve con «OT-0233 ya está pagada: COB-0003, el dd/mm/aaaa, registrado por …» y sin `C` entre las entregas. En «Cobros registrados» hay **un solo** cobro de `C`. *(Lo cubre el recorrido, paso 4, y `test_cobranza_concurrencia.py`.)*
7. **Cambió el monto mientras tanto.** Con otra entrega sin cobrar (si ya cobraste las tres, concretá una más repitiendo los pasos 5 y 6 de «Antes de empezar»), abrí «Registrar cobro» y llegá hasta el resumen sin confirmar. En otra pestaña, como Gerente, aceptá una discrepancia o una queja de **esa** entrega con descuento (Comercial → Solicitudes). Volvé y «Confirmar cobro». **Tiene que ver:** «Mientras armabas el cobro cambió: OT-…: monto a cobrar $ 1.000,00 → $ …» con la entrega todavía marcada y los montos nuevos; recién ahí confirmás. *(Lo cubre `test_ext_10b_…` y `test_cobranza_vistas.py`.)*
8. **Aceptar una discrepancia de una entrega ya cobrada (6a).** Como Gerente: Comercial → Solicitudes → la discrepancia de `C` (ya cobrada) → «Hubo incumplimiento (aceptar)» y «Ver resumen». **Tiene que ver:** «La entrega ya está pagada: se reintegran $ … al cliente con …» y el pedido del **medio del reintegro**. «Confirmar la decisión» sin medio: «medio obligatorio». Elegí **Transferencia** y confirmá: queda aceptada. La ficha del cobro **no cambió** ($ 1.000,00 cobrados). Después, en la solicitud, «Anular resolución»: **«No se puede anular: la indemnización ya se le reintegró al cliente…»** y solo «Volver». *(Lo cubre el recorrido, paso 5, y `test_com_evl_dsc.py` / `test_com_anl_srv.py` con un cobro real.)*
9. **El cobro de una entrega con una indemnización descontada.** Con una entrega cuya discrepancia se aceptó **antes** del cobro (descontó $ …): en «Registrar cobro» la entrega muestra «Total $ 1.000,00 − $ … de indemnizaciones» y su «Monto a cobrar» es el monto con el descuento; el cobro registra ese monto. En la ficha de la solicitud, «Pago de la entrega»: «Pagada · COB-…» con «Cobrada el dd/mm/aaaa por …». Con una entrega **saldada** (el descuento cubrió todo) no aparece en «Por cobrar» y la ficha del suministro dice «Saldada». *(Lo cubre `test_completa_cobranza.py`.)*
10. **Roles.** Entrá como el **otro Vendedor** (sin contratos): «Cobranza» dice «No hay entregas por cobrar» y no muestra al cliente; la ficha de un cobro ajeno por dirección (`/comercial/cobranza/cobros/<id>/`) y registrar una entrega ajena por dirección (`/comercial/cobranza/registrar/?entrega=<id>`) dan «Prohibido (403)». El **Agrónomo** y el **Transportista**: «Cobranza» por dirección da **403**. Sin sesión: te lleva a ingresar. *(Lo cubre el recorrido, paso 6, y `PermisosTests`.)*
11. **Reenviar y imprimir el comprobante.** Con un cliente al que el correo del sistema no le llega (quitá `CORREO_CONSOLA` y reiniciá, o ponele al cliente un correo y un cobro con el correo apagado): el cobro queda «Pendiente de envío» en su ficha, con «**Reenviar comprobante**» (que manda el correo, vuelve a la ficha con «Se envió el comprobante al cliente.» y lo deja «enviado»). Con un cliente **sin correo**: «Sin correo» y «**Imprimir comprobante**» (abre el comprobante imprimible con «Comprobante interno, sin validez fiscal.»). *(Lo cubre `FichaYComprobanteTests` y `test_ext_11a_…`.)*
12. **Navegador real.** Abrí «Registrar cobro» en una **ventana privada** (sin otra sesión): entrá con el Vendedor, elegí una entrega pendiente, completá el medio y **enviá el formulario hasta el final** (Revisar y registrar → Confirmar cobro); después abrí la ficha del cobro y volvé a «Cobranza». Tiene que mostrar el resultado esperado. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Fijate también que **marcar una casilla o cambiar un filtro redibuja el total sin mover la página ni borrar el medio ya elegido** (HTMX), y que «Revisar y registrar» se deshabilita unos segundos al apretarlo («Revisando…»).
13. **Sin JavaScript.** Desactivá JavaScript en el navegador y repetí el cobro de una entrega: las casillas ya no redibujan solas, pero **«Calcular total»** vuelve a dibujar la página con el total; «Revisar y registrar» y «Confirmar cobro» funcionan igual; el grupo de cada cliente en «Cobranza» se despliega y se pliega (es un `<details>` nativo); el cliente se elige con el desplegable y «Calcular total». *(Lo cubre `test_cobranza_vistas.py`: las mismas peticiones, sin HTMX.)*
14. **Panel de control.** Gerente y Vendedor: «Panel de control» → sección «Comercial» → grupo «**Cobranza**»: «Por cobrar» (total y cantidad de entregas), «En mora» (en rojo si hay) y «Sin confirmar por el cliente» («no afecta el cobro»); cada uno lleva a «Cobranza». El Vendedor ve solo lo suyo. *(Lo cubre `PanelYFichasTests`.)*
15. **Las fichas.** Ficha del suministro: la tabla de entregas dice «En mora · N días», «Pendiente», «Pagada · COB-…» o «Saldada» y el botón «**Registrar cobro**» solo mientras haya entregas sin pagar. Ficha del cliente: la tarjeta «Entregas sin cobrar» con «En mora · N días» y el botón «Registrar cobro»; con todo cobrado, la tarjeta desaparece. «Dar de baja» al cliente (Gerente): la ventana dice «Entregas sin cobrar: N ($ …; la primera vence el …; M en mora).» y **no bloquea**. *(Lo cubre `PanelYFichasTests` y `test_completa_cobranza.py`.)*
16. **Cambio de la cláusula.** En el suministro de `C` (que todavía no venció), «Modificar suministro» y subí la **indemnización por atraso** a **250**; guardá. En la base (`shell`): `Entrega.objects.get(numero=233).indemnizacion_retraso_dia` da `Decimal('250.00')`, y la de `A` o `B` (ya vencidas) **conserva `300.00`**. *(Lo cubre `test_regla_modificar_la_clausula_actualiza_solo_las_entregas_que_no_vencieron`.)*
17. **Opcional: en un celular** la pestaña «Cobranza» y «Registrar cobro» se leen y se operan.
18. **Después del merge:** en el log de Render, las migraciones `comercial.0013_cobranza` y `core.0051_comercial_cobranza` aplicadas. (Todavía no hay cron job: el paso 30 se corre a mano o con el cron único, D-56.)

## Cierre (la completó Claude Code al cerrar, 25/11/2026)

**Qué se hizo** (en el orden de los pasos)

1. **Modelos y migraciones.** `LineaPago` (R154: una fila por entrega cobrada, con el índice único parcial de la línea vigente); en `PagoCliente`, `tipo_pago` (por omisión `compra_venta`), `numero` (con `codigo` `COB-NNNN`), `usuario` y `estado_aviso_cliente`, y la restricción C7 reescrita como el o-excluyente; en `Entrega`, `fecha_aviso_mora`, `estado_aviso_mora` e `indemnizacion_retraso_dia`. Migraciones `comercial/0013_cobranza` (con `RunSQL` de la secuencia y su reverso) y `core/0051_comercial_cobranza` (solo `choices`). Acciones `registro_cobro` y `vencimiento_pago` con sus etiquetas. Fábricas `cobro`, `entrega_de_suministro`, `entrega_en_mora` y `verificar_invariantes_de_cobros`; `marcar_concretada` acepta `hace_dias`.
2. **Cálculos y estado de pago** (`comercial/servicios/cobranza.py`): `dias_de_atraso`, `indemnizacion_por_atraso` (`ROUND_HALF_UP`) y `total_del_cobro`; `entregas.estado_de_pago` devuelve «pagada» (cobrada, con su `cobro`, o saldada) con una consulta por tabla.
3. **La mora:** el tipo `comercial_pago_en_mora`, `reevaluar_mora`, el aviso de mora al cliente (`enviar_aviso_de_mora`) y el enlace de la alerta («Registrar cobro» con la entrega ya elegida).
4. **Paso diario 30** `vencer_pagos`: una transacción por entrega (invernadero → entrega, relectura, `reevaluar_mora`, auditoría sin usuario) y el reintento de los correos de mora.
5. **Cobrar:** `clientes_con_deuda`, `entregas_cobrables`, `cliente_de_la_entrega` (1a y 1a1), `resumen_de_cobro` (no escribe; arma la huella), `registrar_cobro` (cuentas → invernaderos → entregas), el comprobante de cobro con su reenvío, `cobros_registrados` y `ficha_de_cobro`; la parte 4 del paso 50 reintenta los comprobantes pendientes.
6. **Concurrencia:** `test_cobranza_concurrencia.py` (9 pruebas con `@tag("concurrencia")`).
7. **Lo que completa a otras tareas:** `concretar_entrega` (pago de compra-venta con `tipo_pago` y `usuario`; copia `indemnizacion_retraso_dia`), `modificar_suministro` (actualiza la indemnización solo en las entregas que todavía no vencieron), `resolver_solicitud` y `anular_resolucion` (`reevaluar_mora` con su rastro en la auditoría), la ficha de la solicitud, la ficha y la regla 5 de ATN-ENR, la ficha del suministro, la ficha y la baja del cliente.
8. **Vistas y plantillas:** la pestaña «Cobranza» (con su contador), «Registrar cobro» (con HTMX y sin JavaScript), el resumen, la ficha del cobro, el comprobante imprimible, «Reenviar comprobante» y el grupo «Cobranza» del panel.

**Pruebas** (todas verdes)

- Archivos nuevos: `test_modelos_cobranza` (36), `test_cobranza_calculos` (7), `test_estado_de_pago` (15), `test_reevaluar_mora` (30), `test_com_vnc_pag` (27), `test_com_reg_cbr` (53), `test_completa_cobranza` (18), `test_cobranza_vistas` (28), `test_recorrido_cobranza` (1, `RecorridoDeCobranzaTests`) y `test_cobranza_concurrencia` (9, con `@tag("concurrencia")`). Más `base_cobranza.py`.
- `python manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **Ran 3513 tests · OK**.
- `python manage.py test comercial --keepdb --tag concurrencia`: **Ran 133 tests · OK**.
- **Las pruebas con `mock.patch` de COM-06b y COM-07a que se reemplazaron por otras con un cobro real** (para el PR; el resto de las pruebas de COM-06a, COM-06b y COM-07a no se tocó): `test_com_anl_srv` (2b y 2c), `test_com_evl_dsc` (6a y 8b), `test_com_rsv_qja` (6a) y `test_com_atn_enr` (regla 5, que simulaba `_tiene_cobro_vigente`). Cada una conserva su nombre, su regla y sus aserciones; solo cambia cómo se arma la entrega pagada.

**Decisiones**

- Ninguna decisión nueva. Lo que difiere de la documentación va a `docs/temas_abiertos.md` (abajo). Las dos que decidió el estudiante en el plan (L7): `EstadoDePago` es un `str` con atributos, y `verificar_invariantes_de_cobros` va en `comercial/tests/fabricas.py`.

**Lo que implementé distinto de lo escrito** (para `docs/temas_abiertos.md`; no se corrigió en silencio)

1. `EstadoDePago` (D-94, punto 4, y `cobranza.md`) se describe como una tupla; es un `str` («pendiente», «en_mora», «pagada») con `.estado`, `.saldada` y `.cobro`. Así `clientes.py`, `solicitudes.py`, las plantillas y `test_extensiones_entregas.py` siguen andando sin tocarse. La compra-venta conserva su `None` (el documento decía que la clave no está).
2. `verificar_invariantes_de_cobros()` está en `comercial/tests/fabricas.py`, junto a las demás, y no en `comercial/tests/invariantes.py` (que no existe).
3. **2b de COM-ANL-SRV** («Primero anulá el cobro») se dispara con un **cobro vigente real**, no con «pagada»: una entrega saldada (monto a cobrar 0) cuenta como «pagada» pero no tiene un cobro que anular, y el bloqueo dejaba la anulación sin salida y pisaba a 2c (tres pruebas que ya existían lo mostraron: `test_post_b_…`, 2c y `AnularTests.test_con_un_bloqueo_solo_el_mensaje_y_volver`).
4. La alerta de `maestros` admite 200 caracteres (la API recorta); `cobranza.md` decía 500 para la descripción de «pago en mora».
5. Los servicios lanzan `ValidationError` con `code` (el patrón de `comercial`), no `ErrorComercial`.
6. El comprobante de cobro y el aviso de mora al cliente están en `cobranza.py` (como los avisos de las solicitudes están en `solicitudes.py`), no en `comprobantes.py`.
7. El aviso al Vendedor cuando cobra el Gerente lista **solo las entregas de ese Vendedor** y lo que suman; la documentación dice «el total cobrado».
8. Si hay una solicitud pendiente, el texto dice «discrepancia pendiente» o «queja pendiente» según el tipo (el documento solo da el ejemplo de la queja).
9. «Revisar y registrar» está deshabilitado mientras no haya ninguna entrega elegida, **no** mientras falte el medio: el medio se valida al apretarlo (`.claude/rules/interfaz.md`: las validaciones corren en los botones de acción) y sin JavaScript un botón no podría habilitarse al elegir el medio.
10. Los grupos de «Por cobrar» se despliegan con `<details>` (sin JavaScript) en lugar del botón `cobtog` del prototipo; el cliente se elige de un **desplegable de los clientes con deuda** y no con el buscador de COM-02 (la lista es corta).
11. `procesados` del paso 30 cuenta las entregas candidatas de la parte 1; `detalle` dice «N correos de mora pendientes» (sin singular).
12. Sobre la «consulta para los grupos y otra para las entregas»: `clientes_con_deuda` y `entregas_cobrables` usan un número fijo de consultas (una por tabla), no dos.
13. `cobro` y aceptación de una solicitud de la misma entrega ya se serializan en las cuentas (las dos toman al Vendedor del contrato), así que la prueba de orden de bloqueo que lo detecta es la del paso 30 (que no toma cuentas); está explicado en la docstring de `test_cobranza_concurrencia.py`.
14. D-94 tiene dos líneas «Estado» («aprobada el 23/11/2026» arriba y «propuesta (a validar…)» al final): la segunda quedó vieja.
15. Entorno: con `--parallel`, una prueba que **falla** hace caer el ejecutor con `TypeError: cannot pickle 'traceback' object` (falta `tblib`) y no muestra qué falló; para ver las fallas hay que correr en serie. Pasa también en el CI si una prueba falla.

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Registrar cobro (`ACT['cobro-ok']`) | Registraba directo, sin resumen ni relectura | Resumen en otra página (`revisar/`, no escribe), «Confirmar cobro» con la huella y vuelta con los datos nuevos ante 10a y 10b | Pasos 8 a 10 y 10a, 10b |
| Registrar cobro (`fc`) | La fecha era un campo validado contra hoy | La fecha no se elige: es la de hoy, dicho junto al medio | Regla «Fecha del pago» |
| Registrar cobro (`VIEWS.cobro`) | «Total … − … de indemnizaciones» con la indemnización entera | Se muestra lo **descontado** (`monto_descontado`) | Paso 4, D-69 punto 9 |
| Registrar cobro (`ACT['cobro-ok']`) | El texto final decía «Se envió el comprobante» siempre | La ficha dice el estado real del correo, con «Reenviar comprobante» o «Imprimir comprobante» | 11a |
| Registrar cobro (`cliPick`) | Buscador de clientes | Desplegable de los clientes con deuda (o el cliente fijo desde un grupo, una ficha o la alerta) | La lista es corta; sin JavaScript queda el desplegable nativo |
| Registrar cobro (estados «vencida») | «Vencida» | «En mora» | MD-139 |
| Registrar cobro (pasos bloqueados) | Todo visible | «Entregas que paga» aparece al elegir el cliente y «Pago», al elegir una entrega; el total parcial no valida nada; marcar y los filtros redibujan con HTMX (`show:none`, `data-sin-envio-en-curso`); sin JavaScript, «Calcular total» | Pantallas, «Pasos bloqueados» y «HTMX» de `cobranza.md`; `.claude/rules/interfaz.md` |
| Por cobrar (`tabCobranza`, primera definición) | Incluía entregas con monto a cobrar 0 | No se ofrecen las saldadas | Regla «Entrega cobrable» |
| Por cobrar (`cobGroups`, `ACT.cobtog`) | Grupo plegable con JavaScript | `<details>` nativo; abierto si hay mora; «Registrar cobro» por grupo | Funciona sin JavaScript |
| Cobranza (`comTabs`) | Sin contador | Contador rojo con las entregas en mora | Pantallas, «Comercial · pestaña Cobranza» |
| Cobros registrados | Sin ficha | Ficha del cobro (cobro, entregas con lo cobrado y atraso, estado del comprobante) y comprobante imprimible | `cobranza.md`, «Ficha del cobro» |
| Panel (`secComercial`) | Grupo «Cobranza» dentro de la sección | El grupo va en la misma sección que «Entregas» y «Solicitudes», después de ellos, con los tres indicadores; «Resultados del mes en curso» es de COM-08c | Pantallas, «Panel de control» |
| Anular cobro (`MODALS.anlcbr`) | — | No se hizo: es de COM-08b | Alcance |

**Verifiqué** (Claude Code, sin navegador, D-96)

- **El recorrido** `RecorridoDeCobranzaTests` (cliente de Django, por rol y por estado): el paso diario 30 corrido a mano y otra vez (sin repetir), «Cobranza» del Vendedor, el resumen que no escribe, el cobro con su comprobante y su alerta resuelta, el cobro del Gerente desde la alerta con el aviso al Vendedor, el segundo cobro de la misma entrega («ya está pagada»), la aceptación posterior con el reintegro y la anulación bloqueada, el Vendedor ajeno y el Transportista (403). Pasa.
- **Migraciones:** `makemigrations --check`: sin cambios. `sqlmigrate comercial 0013`: crea la secuencia y la tabla, agrega columnas **nulas o con valor por omisión** (`tipo_pago` con `DEFAULT 'compra_venta'`, que se quita después), cambia la restricción C7 (`DROP CONSTRAINT` de la vieja y las nuevas); **no borra ni reescribe datos**. `sqlmigrate core 0051`: no-op (solo `choices`). Las dos se aplican en la base `test_…` cada vez que se la recrea (la recreé con `--noinput`: D-101).
- **`git fetch`** antes de crearlas y al cerrar: `main` no sumó migraciones (siguen `comercial` 0012 y `core` 0050): sin choque.
- **Orden de bloqueo:** invertí a propósito el orden del cobro (entregas antes que invernaderos) y las dos pruebas del paso 30 fallaron (una por deadlock); restauré el código y pasan.
- **Comandos de «Hecho cuando» (M1):** `python manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → `Ran 3513 tests … OK`; `python manage.py test comercial --keepdb --tag concurrencia` → `Ran 133 tests … OK`.
- No toqué tu base de desarrollo (ni borré ni cargué datos).

**Lo cubre una prueba** (no hace falta repetirlo a mano)

- Cada regla, postcondición y extensión de COM-REG-CBR y COM-VNC-PAG: `test_com_reg_cbr.py` y `test_com_vnc_pag.py` (con la numeración de las reglas del extracto).
- Las restricciones de la base y los invariantes: `test_modelos_cobranza.py`.
- Los cálculos y el estado de pago: `test_cobranza_calculos.py` y `test_estado_de_pago.py`.
- La mora y el enlace de la alerta: `test_reevaluar_mora.py`.
- Lo que completa a otras tareas: `test_completa_cobranza.py` y las seis pruebas reemplazadas.
- Las vistas, los permisos y los textos: `test_cobranza_vistas.py`.
- Dos cobros de la misma entrega, cobro contra aceptación, cobro contra el paso 30 y el orden de los bloqueos: `test_cobranza_concurrencia.py`.

**No pude verificar**

- **Lo que solo ve un navegador:** el CSRF y el encabezado `Origin` de los formularios, el comportamiento real de HTMX (que marcar una casilla redibuje sin mover la página), el aspecto, el teclado y el celular: van como los pasos 12, 13 y 17 de la «Verificación a mano».
- **El envío real de correo** (SMTP): las pruebas usan el servidor de correo simulado.
- **La migración hacia atrás** (`migrate comercial 0012`): el `RunSQL` trae su reverso, pero no la ejercité.
- **La cadena de datos de partida** (cosecha, ruta, concreción): la armo con fábricas; recorrerla a mano es lo más largo de la «Verificación a mano» (pasos 6 y 7 de «Antes de empezar»).
- **El despliegue en Render/Neon** y el cron único (todavía no existe, D-56).
