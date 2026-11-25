# COM-08b · Anular un cobro y cobrar lo entregado al cancelar una compra-venta

Estado: hecha (25/11/2026; revisión a mano pendiente) | App: comercial | Rama: feature/com-08b-anular-cobro | Ronda: Comercial 1

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

## Verificación a mano (la completó Claude Code al cerrar; la hace el estudiante)

Sin datos cargados (D-95, D-96): el cargador de la primera versión de esta tarea se retiró y no vuelve; los datos los creás vos a mano con los valores de abajo. Cada paso dice si ya lo cubre una prueba (el recorrido es `comercial/tests/test_recorrido_anulacion_de_cobro.py`).

**Antes de empezar**

1. En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `comercial` 0014 `anulacion_de_cobro`: dos columnas nuevas en `Anulacion` y `PagoCliente` y las restricciones de `Anulacion`; `core` 0052, solo `choices`; y, si todavía no la tenías, `maestros` 0013 de CMP-07) y `python manage.py runserver`. Abrí `http://localhost:8000/`.
2. Cuentas: **Gerente**, **Vendedor** del invernadero, **otro Vendedor** sin contratos, **Agrónomo** y **Capataz** del invernadero. Para el paso 11 (cancelar con cobro) también hace falta un **Transportista** con un vehículo activo en cada invernadero de origen.
3. Lo que tiene que existir (si ya lo tenés de COM-08a, usalo): un invernadero activo con su Agrónomo, Capataz y Vendedor; una variedad con un lote en Maduración de por lo menos **300 plantas**; y un **cliente con un correo que puedas leer**, con una dirección (Comercial → Clientes → «Nuevo cliente»). Por ejemplo: persona jurídica «Verdulería Los Pinos S.R.L.», CUIT **30-71234567-1**, correo el tuyo.
4. **Correo en desarrollo:** en tu `.env` local dejá `CORREO_CONSOLA=1` (los correos se imprimen en la terminal del `runserver`).
5. **Entregas de suministro concretadas del mismo cliente.** Es la misma preparación que los pasos 5 a 7 de «Antes de empezar» de COM-08a: pactá un suministro (plazo de pago **10** días, indemnización por atraso **300**, un detalle de **50** plantas a precio fijo **20**, primera entrega «hoy») y llevá cuatro entregas a «concretada» (`python manage.py proceso_diario --solo pre_reservar_suministros`, después `--solo planificar_entregas`; el Capataz concreta la cosecha; el Transportista inicia la ruta y concreta la entrega). Podés pactar un segundo y un tercer suministro del mismo cliente para tener entregas del mismo cliente en contratos distintos. Cada entrega vale $ 1.000,00. En la **tercera** (`C`) concretá con **20** plantas recibidas de 50: crea una discrepancia pendiente (Comercial → Solicitudes). Los números `OT-…` de abajo son los tuyos: los ves en Comercial → Entregas.
6. **Envejecerlas** (solo en tu base local de desarrollo). Concretar siempre pone fecha de hoy, así que para tener mora hay que mover fechas. En la terminal, `python manage.py shell` y pegá, cambiando los números por los de tus entregas (`OT-0231` es el 231):

   ```python
   from datetime import timedelta
   from django.utils import timezone
   from comercial.models import Entrega
   hoy = timezone.localdate()
   # (número de la entrega, hace cuántos días se concretó)
   for numero, dias in ((231, 15), (232, 5), (233, 5), (234, 14)):
       concretada = hoy - timedelta(days=dias)
       Entrega.objects.filter(numero=numero).update(fecha_resolucion_orden=concretada, fecha_vencimiento_pago=concretada + timedelta(days=10))
   ```

   Queda: `A` (OT-0231) venció hace **5** días (en mora), `B` (OT-0232) vence en **5** días (pendiente), `C` (OT-0233, la de la discrepancia) vence en **5** días y `D` (OT-0234) venció hace **4** días (en mora). **No corras todavía** `proceso_diario --solo vencer_pagos`: el paso 3 necesita que `A` no haya sido avisada nunca.
7. **Para el paso 11** (cancelar con cobro): un **segundo invernadero** activo del **mismo Vendedor**, con su Capataz y un Transportista con vehículo, y una **segunda variedad** con un lote en Maduración de por lo menos **100 plantas** en ese invernadero. Registrá una compra-venta (Vendedor: Comercial → Contratos → «Nueva compra-venta») del cliente, **envío a domicilio**, fecha pactada **hoy**, con dos renglones: la variedad del invernadero 1 (**40** plantas) y la del invernadero 2 (**30**). Corré `python manage.py proceso_diario --solo planificar_entregas`: nacen **dos entregas** (una por invernadero). El Transportista del invernadero 1 inicia la ruta y **concreta** su entrega. La otra queda «a realizar» (su Transportista no inició la ruta).

**Los pasos**

1. **El cobro de partida (Gerente).** Entrá como **Gerente** → Comercial → «Cobranza» → «Registrar cobro» del cliente. Marcá **`A` y `B`**, medio **Transferencia**, «Revisar y registrar» y «Confirmar cobro». **Tiene que ver:** «COB-0001 registrado: $ 3.500,00» ($ 1.000,00 + $ 1.000,00 + 5 días × $ 300,00 de atraso de `A`). Todavía no hay alerta de `A` ni correo de mora (nunca se corrió el paso 30). *(Lo cubre el recorrido, paso 1.)*
2. **El Vendedor no puede anular.** Entrá como el **Vendedor** → «Cobranza» → «Cobros registrados»: el cobro COB-0001 **no** tiene «Anular»; abrí su ficha («Ver»): tampoco. Escribí a mano `/comercial/cobranza/cobros/<id>/anular/` (el id lo ves en la barra al abrir la ficha): **«Prohibido (403)»**. Lo mismo con **otro Vendedor**, el **Agrónomo** y el **Capataz**; sin sesión te lleva a ingresar. *(Lo cubre el recorrido, paso 2, y `test_regla_solo_el_gerente_ve_y_abre_anular_el_vendedor_recibe_403`.)*
3. **Anular un cobro (Gerente): la pantalla.** Como **Gerente**: «Cobros registrados» → «Anular» de COB-0001. **Tiene que ver:** «Anular COB-0001» con el cliente, la fecha, el medio y $ 3.500,00; «Qué va a pasar» con **OT-0231 → vuelve a «en mora»: se activa otra vez su alerta «Pago en mora»** y **OT-0232 → vuelve a «pendiente»**; la aclaración «Se avisa al Vendedor de cada contrato. Al cliente no se le escribe.»; «El contraasiento… Fuera de esta ronda · contabilidad»; el motivo y la casilla «El cliente pagó en esa fecha (se corrige un error de carga)». **Sin escribir el motivo**, «Anular cobro»: vuelve con **«Escribí el motivo de la anulación.»** junto al campo, con la casilla como la dejaste, y el cobro sigue «Vigente» (miralo en «Cobros registrados»). *(Lo cubre el recorrido, pasos 3 y 4, y `AnulacionVistasTests`.)*
4. **Anular: el efecto.** Escribí el motivo «Cargué la transferencia con el cliente equivocado», **marcá** «El cliente pagó en esa fecha» y «Anular cobro». **Tiene que ver:** la ficha del cobro con el aviso «COB-0001 anulado…», la insignia «Anulado», la tarjeta «Anulación» (fecha, quién anuló, el motivo, «El cliente pagó en la fecha del cobro: Sí», «Cobro correcto: Todavía no se registró.») y el botón **«Registrar el cobro correcto»**; ya no hay botón «Anular». «Cobros registrados» lo lista «Anulado» (filtro «Anulados»). Gerente: campana → «Alertas»: **otra vez «Pago en mora» de `A`** (la de `B` no, es pendiente). **Vendedor:** campana → «Notificaciones»: **una** sola, «COB-0001 anulado»: «El Gerente anuló el cobro de Verdulería Los Pinos S.R.L. ($ 3.500,00). Vuelven a estar sin pagar: OT-0231 (en mora) y OT-0232 (pendiente). Motivo: …» (y **ninguna** «OT-0231 en mora»). **Correo** (terminal del servidor): **uno solo**, «Pago en mora de la entrega OT-0231» (es la primera vez que `A` se avisa); **ninguno** por la anulación misma. «Auditoría» (Gerente): «Anulación de cobro de suministro» con el cobro, la anulación, las líneas y la alerta nueva. *(Lo cubre el recorrido, paso 5, y `test_com_anl_cbr.py`.)*
5. **Un cobro de compra-venta no se anula desde acá.** Ningún cobro de compra-venta aparece en «Cobranza». Para verlo por URL: en el `shell`, `from comercial.models import PagoCliente; PagoCliente.objects.filter(tipo_pago="compra_venta").first().pk` y escribí `/comercial/cobranza/cobros/<ese id>/anular/`. **Tiene que ver:** vuelve a «Cobranza» con **«Este cobro es de una compra-venta: va dentro del asiento de la entrega y se corrige con un asiento manual.»**. *(Lo cubre el recorrido, paso 3, y `test_ext_1a_…`.)*
6. **El cobro correcto con la fecha original (7a).** Hacé que el cobro original sea de hace dos días (en el `shell`): cobrá primero `D` (Gerente, Efectivo; son 4 días × $ 300,00 de atraso) y luego, con el id de ese cobro: `from datetime import timedelta; from django.utils import timezone; from comercial.models import PagoCliente, LineaPago; hoy = timezone.localdate(); p = PagoCliente.objects.get(pk=<id>); PagoCliente.objects.filter(pk=p.pk).update(fecha_pago=hoy - timedelta(days=2)); LineaPago.objects.filter(pago=p).update(dias_atraso=2, indemnizacion_atraso=600)` y `PagoCliente.objects.filter(pk=p.pk).update(monto_pagado=1600)`. Anulalo como Gerente **marcando** «El cliente pagó en esa fecha» y tocá **«Registrar el cobro correcto»**. **Tiene que ver:** «Registrar cobro» con el cliente fijo, **`D` ya elegida**, la casilla **«Usar la fecha del cobro anulado (dd/mm): el cliente pagó ese día» marcada**, «Es la fecha del cobro anulado: el cliente pagó ese día.» y el atraso de **2 días · $ 600,00** (no 4 días · $ 1.200,00). Desmarcá la casilla: la fecha pasa a hoy y el atraso a 4 días · $ 1.200,00 (**sin mover la página ni borrar lo elegido**). Volvé a marcarla, elegí **Efectivo**, «Revisar y registrar» (la fecha del pago es la del cobro anulado) y «Confirmar cobro». **Tiene que ver:** un cobro nuevo con la fecha de hace dos días por $ 1.600,00; en la ficha del anulado, «Cobro correcto: COB-…». Volvé a escribir la misma dirección `/comercial/cobranza/registrar/?anulacion=<id de la anulación>`: vuelve a «Cobranza» con **«El cobro correcto de esa anulación ya se registró.»** (la fecha anterior se usa una sola vez). *(Lo cubre el recorrido, paso 6, y `test_ext_7a_…`.)*
7. **Sin la casilla.** Cobrá `C` (Gerente), anulá ese cobro **sin marcar** «El cliente pagó en esa fecha» y tocá «Registrar el cobro correcto»: la pantalla abre con `C` elegida pero **sin la casilla** y con «Es la fecha de hoy: no se registran cobros con fecha anterior.»; es un cobro común. *(Lo cubre el recorrido, paso 7.)*
8. **Lo que libera la anulación (2b).** `C` tiene una discrepancia pendiente: como Gerente, Comercial → Solicitudes → esa discrepancia → «Hubo incumplimiento (aceptar)» con descuento y confirmá (antes de cobrar `C` otra vez). Cobrá `C` (monto con el descuento). Volvé a la solicitud → «Anular resolución»: **«Primero anulá el cobro de OT-0233 (Anular cobro).»**. Anulá el cobro de `C` (paso 4) y volvé a «Anular resolución»: **ya no rechaza** y muestra «Qué va a pasar». *(Lo cubre el recorrido, paso 8, y `test_regla_despues_de_anular_2b_…`.)*
9. **Lo que libera la anulación (regla 5 de «Entrega no reconocida»).** Es difícil de preparar a mano (hace falta una alerta «entrega no reconocida» de una entrega ya cobrada): *lo cubre una prueba* (`test_regla_despues_de_anular_la_regla_5_de_com_atn_enr_deja_de_rechazar`).
10. **Dos pestañas (opcional).** Abrí «Anular» del mismo cobro en dos pestañas. Anulá en la primera. En la segunda, «Anular cobro»: vuelve a la ficha con **«COB-… ya está anulado: no hay nada más que anular.»**; hay una sola anulación. *(Lo cubre el recorrido y `test_anulacion_cobro_concurrencia.py`.)*
11. **Cancelar una compra-venta con una entrega concretada (6a).** Como **Vendedor**: Comercial → Contratos → la compra-venta del paso 7 de «Antes de empezar» → «Cancelar compra-venta». **Tiene que ver:** «Qué se cancela» (el renglón entregado «Ya entregado: no cambia» y el otro «Se cancela»), «Qué pasa con el producto» (la entrega pendiente se cancela y su Transportista recibe un aviso) y la sección **«3 · Cobro de lo entregado»**: «La venta ya tiene entregas concretadas: lo entregado se cobra ahora, en un solo pago. El resto se cancela.», la entrega concretada con su monto, **«Monto a cobrar»**, los **cuatro medios de pago** como botones de opción y «Fuera de esta ronda · contabilidad»; «4 · Motivo»; a la derecha «Estado final: **Concretada (se cobra lo entregado)**». **Sin elegir el medio**, elegí el motivo «El cliente desistió» y «Revisar y cancelar»: **«Elegí el medio de pago con que el cliente paga lo entregado.»** junto a los botones. Elegí **Tarjeta de débito**, «Revisar y cancelar»: la ventana de resumen con «Cobro de lo entregado: $ … · Tarjeta de débito» y «Concretada (se cobra lo entregado)»; **todavía no se escribió nada** (la ficha de la venta sigue «Abierta»). «Confirmar cancelación». **Tiene que ver:** el aviso «CV-… cancelada. Se cobró lo entregado ($ …, tarjeta de débito) y la venta quedó concretada.»; la ficha de la venta **«Concretada»** con los datos de la cancelación y su pago; la entrega pendiente «Cancelada»; el correo «Cancelación de tu compra CV-…» con la sección **«Cobro de lo entregado»** y el total; y «Imprimir comprobante» (la página imprimible) con el mismo cobro. Si cancela el **Gerente**, el Vendedor recibe «CV-… cancelada» con «Se cobró lo entregado: $ … con tarjeta de débito.». *(Lo cubre el recorrido, paso 9, `ComCnlCvtVistaConCobroTests` y las pruebas de 6a de `test_com_cnl_cvt.py`.)*
12. **Cancelar sin entregas concretadas sigue igual.** Con una compra-venta sin entregas concretadas la pantalla no tiene «Cobro de lo entregado», no pide medio y la venta queda «Cancelada». *(Lo cubre `test_regla_sin_entregas_concretadas_la_pantalla_no_tiene_la_seccion_de_cobro`.)*
13. **Navegador real.** Abrí «Anular» y la cancelación en una **ventana privada** (sin otra sesión): entrá como Gerente, abrí «Anular» de un cobro vigente, escribí el motivo y **enviá el formulario hasta el final** («Anular cobro»); después abrí la ficha y «Cobros registrados». Repetí con la cancelación: como Vendedor, «Cancelar compra-venta» de una venta con una entrega concretada, medio de pago, «Revisar y cancelar» y **«Confirmar cancelación» hasta el final**, y volvé a abrir la ficha. Tiene que mostrar el resultado esperado. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Fijate también que **marcar o desmarcar la casilla «Usar la fecha del cobro anulado» redibuja el total y la fecha sin mover la página ni borrar el medio**, que «Anular cobro» se deshabilita al apretarlo («Anulando…») y que la ventana del resumen de la cancelación se abre y se cierra con «Volver».
14. **Sin JavaScript.** Desactivá JavaScript y repetí: «Anular cobro» (una página: motivo, casilla y botón) funciona igual; en «Registrar el cobro correcto» la casilla no redibuja sola: **marcala o desmarcala y tocá «Calcular total»**; «Revisar y registrar» y «Confirmar cobro» funcionan; la cancelación con cobro: «Revisar y cancelar» abre el resumen como **página** (con «Volver» y «Confirmar cancelación») y cobra igual. *(Lo cubre `AnulacionVistasTests` y `ComCnlCvtVistaConCobroTests`: las mismas peticiones, sin HTMX.)*
15. **Opcional: en un celular** «Anular», «Registrar el cobro correcto» y la cancelación se leen y se operan.
16. **Después del merge:** en el log de Render, las migraciones `comercial.0014_anulacion_de_cobro` y `core.0052_comercial_anulacion_cobro` aplicadas (y `maestros.0013` de CMP-07 si todavía no estaba).

## Cierre (lo completó Claude Code al cerrar, 25/11/2026)

**Qué se hizo** (en el orden de los pasos)

1. **Modelos y migraciones.** `Anulacion.pago_cliente` (`OneToOneField` nulo a `PagoCliente`) y `cliente_pago_en_fecha`; `PagoCliente.anulacion_corregida` (`OneToOneField` nulo a `Anulacion`); las restricciones de `Anulacion` reescritas («exactamente uno de `solicitud` y `pago_cliente`», `pago_cliente` ⇔ `cliente_pago_en_fecha`, `solicitud` ⇔ `estado_anulado`). Migraciones `comercial/0014_anulacion_de_cobro` y `core/0052_comercial_anulacion_cobro` (solo `choices`). Acción `anulacion_cobro` con sus etiquetas. Fábricas `anulacion_de_cobro` (y `cobro(estado="anulado")` crea su `Anulacion`) y los invariantes 8 y 9 de `verificar_invariantes_de_cobros`.
2. **Anular un cobro** (`cobranza.py`): `datos_de_anulacion_de_cobro` (solo lectura) y `anular_cobro` (cuentas → invernaderos → entregas → pago y líneas; relectura y huella; la `Anulacion`, el pago «anulado» y las líneas `vigente = False`, `reevaluar_mora` de cada entrega, el aviso al Vendedor y la auditoría `anulacion_cobro`).
3. **El cobro correcto (7a):** `DatosDeCobro.anulacion_id` y `usar_fecha_anulada`; `_fecha_de_pago` (límites: solo el Gerente, solo el cobro anulado con `cliente_pago_en_fecha`, solo sus entregas, nunca una fecha futura, una sola vez), `anulacion_para_registrar` y la huella con la fecha del pago.
4. **La extensión 6a de COM-CNL-CVT** (`compra_ventas.py`): `medio_pago` en `DatosDeCancelacionDeVenta` (`medio_de_pago_obligatorio` / `medio_no_admitido`), `cobro` en `datos_de_cancelacion`, la huella con las entregas concretadas y su monto, el pago de compra-venta, la venta «concretada», el aviso, la auditoría y el comprobante con «Cobro de lo entregado»; `cancelar_compra_venta` recibe `hoy`.
5. **Concurrencia:** `test_anulacion_cobro_concurrencia.py` (7) y 2 métodos nuevos en `test_com_cnl_cvt_concurrencia.py`.
6. **Vistas y plantillas:** `anular.html` (una página), «Anular» en «Cobros registrados» y en la ficha (solo el Gerente), la tarjeta «Anulación» y «Registrar el cobro correcto», la casilla y la fecha de 7a en «Registrar cobro», la sección «Cobro de lo entregado» de la cancelación y su resumen.

**Pruebas** (todas verdes)

- Archivos nuevos: `test_com_anl_cbr` (`ComAnlCbrServicioTests` y `ComAnlCbrCobroCorrectoTests`), `test_anulacion_cobro_concurrencia` (7) y `test_recorrido_anulacion_de_cobro` (1, `RecorridoDeAnulacionDeCobroTests`). Pruebas nuevas en `test_com_reg_cbr` (`ComRegCbrFechaDelCobroAnuladoTests`), `test_com_cnl_cvt` (6a y `ComCnlCvtVistaConCobroTests`), `test_com_cnl_cvt_concurrencia` (2), `test_cobranza_vistas` (`AnulacionVistasTests`) y `test_modelos_cobranza` (restricciones de `Anulacion` e invariantes 8 y 9).
- `python manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **Ran 3600 tests · OK** (con la base de pruebas recreada con `--noinput`, porque CMP-07 sumó `maestros` 0013).
- `python manage.py test comercial --keepdb --tag concurrencia`: **Ran 142 tests · OK**.
- **Pruebas existentes reemplazadas o cambiadas** (para el PR; las demás de COM-05b, COM-06a y COM-08a no se tocaron):
  - **Reemplazadas** (esperaban el rechazo `venta_con_entregas_concretadas`, que ya no existe): `test_com_cnl_cvt.ComCnlCvtServicioTests.test_ext_6a_con_una_entrega_concretada_se_rechaza_con_venta_con_entregas_concretadas` (COM-05b) → `…_ya_no_se_rechaza_pide_el_medio_de_pago_para_cobrar_lo_entregado`; y `ComCnlCvtConEntregaConcretadaRealTests.test_ext_6a_con_una_entrega_concretada_real_el_servicio_sigue_rechazando_hasta_la_cobranza` (COM-06a, la tarea nombraba solo la de COM-05b) → `…_real_se_cancela_lo_pendiente_y_se_cobra_lo_entregado`.
  - **Cambiadas de COM-08a** (hay que decirlo; no se debilitaron): `test_reevaluar_mora.test_regla_si_la_entrega_vuelve_a_estar_en_mora_se_asegura_una_alerta_nueva_sin_correo` (dejaba el cobro «anulado» con dos `update` a mano; ahora usa `anulacion_de_cobro(pago)`, que hace lo mismo y suma la `Anulacion` que pide el invariante 8; mismas aserciones) y `test_cobranza_vistas.PestanaTests.test_cobros_registrados_lista_el_cobro_con_su_monto_y_el_atraso` (afirmaba que la lista **no** tenía «Anular», que es justo lo que agrega esta tarea; ahora afirma que el Gerente ve el enlace, y el Vendedor sin enlace lo prueba `AnulacionVistasTests`). La fábrica `cobro(estado="anulado")` ahora crea su `Anulacion` (las seis pruebas que la usan no cambian).
  - **Ayuda** de `venta_con_una_entrega_concretada`: suma el parámetro `fecha_de_la_segunda` (por omisión, la de antes) para que la segunda entrega no quede «en curso» (4a); `test_d67_4_…` no cambia.

**Decisiones**

- Ninguna decisión nueva. **Lo que corrige documentación existente** (a proponer en M3, no se aplicó): el campo se llama `Anulacion.pago_cliente` y no `pago` (D-94 punto 11, `docs/modelo/comercial.md` y los extractos `cobranza.md` y `solicitudes.md`): `compras.Pago` también es hija de `OrigenDocumento` y le da a esa clase el acceso inverso `pago`, así que `Anulacion.pago` falla con el error E006; el `related_name` es `anulacion_de_cobro` (no `anulacion`, que `PagoCliente` ya hereda de `OrigenDocumento`).

**Lo que implementé distinto de lo escrito** (para `docs/temas_abiertos.md`; no se corrigió en silencio)

1. **`Anulacion.pago` → `Anulacion.pago_cliente`** (con `related_name="anulacion_de_cobro"`), por el choque E006 con `compras.Pago`. El estudiante lo aprobó en el plan. Las restricciones se llaman `anulacion_solicitud_o_pago`, `anulacion_pago_con_fecha` y `anulacion_estado_con_solicitud`.
2. **Eran dos las pruebas que esperaban `venta_con_entregas_concretadas`**, no una (la segunda la sumó COM-06a); y dos pruebas de COM-08a cambiaron su armado o su aserción (arriba).
3. **«Anular» es una página** (`anular.html`), no la ventana de `MODALS.anlcbr`, igual que «Anular resolución» de COM-07a: sin JavaScript funciona sin duplicar la pantalla. Al confirmar vuelve a la ficha del cobro anulado, que ofrece «Registrar el cobro correcto» (no una «pantalla final» aparte).
4. **La extensión 8a de la cancelación avisa cualquiera de los dos códigos** (`venta_cambio` o `venta_no_cancelable`) cuando la otra entrega se concreta en medio y cierra la venta: la huella no se compara si la venta ya no es cancelable. La validación del medio de pago va **después** de la huella bajo bloqueo (así lo que cambió se informa como `venta_cambio` y no como un medio faltante).
5. **Lo entregado en cero.** Si todas las entregas concretadas valen cero (todo rechazado al recibir), no hay nada que cobrar: `cobro` es `None`, no se pide medio y la venta queda «cancelada» (no «concretada», que exige un pago por un monto mayor que cero). La documentación no lo dice.
6. **`_bloquear_para_cancelar` ahora bloquea también las entregas concretadas de la venta** (en el mismo `select_for_update` que las «a realizar», en orden de id): `compra_venta.md` decía que «ya se bloquean con las demás», pero solo se bloqueaban las «a realizar».
7. **La anulación y los bloqueos:** el cobro y la anulación comparten las cuentas del Gerente y del Vendedor, así que quedan en fila ahí; el único contrincante que puede cruzarse con ellas en los invernaderos y las entregas es el paso 30, y sobre la **misma** entrega no puede competir (una entrega cobrada no es candidata). Por eso la prueba que detecta un orden invertido es **sondeada**: se detiene la anulación en cada punto y se mira con `NOWAIT` qué filas tiene tomadas (`test_regla_la_anulacion_toma_el_invernadero_y_todavia_no_las_entregas_antes_de_tomarlas` y `…_el_pago_y_las_lineas_al_final_…`). Las demás pruebas de concurrencia no la detectan solas (lo comprobé invirtiendo el orden a propósito).
8. **«Anular contra registrar el cobro correcto de la misma anulación»** se probó como dos cobros correctos a la vez de la misma anulación (uno gana, el otro `anulacion_ya_usada`).
9. **La huella de la anulación** suma la fecha de hoy y el estado en que quedaría cada entrega (puede cambiar de «pendiente» a «en mora» al pasar el día); la documentación no la define. **La huella del cobro** suma la fecha del pago (en 7a es la del cobro anulado).
10. **`anulacion_para_registrar`** (el GET de «Registrar el cobro correcto») es solo del Gerente: el Vendedor recibe 403; y con la casilla marcada la pantalla muestra solo las entregas del cobro anulado.
11. **Entorno:** con `--parallel`, una prueba que falla hace caer el ejecutor con `TypeError: cannot pickle 'traceback' object` (falta `tblib`); además, una base de pruebas clonada **sin** la migración nueva de otra tarea falla con «no existe la columna …» (recrearla sin `--keepdb` y con `--noinput`).

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Anular cobro (`MODALS.anlcbr`) | Una ventana que decía solo «vuelven a estar sin pagar», sin el estado de cada entrega | Una página que dice, por cada entrega, si vuelve a «pendiente» o a «en mora» (con su alerta), el contraasiento como «Fuera de esta ronda · contabilidad» y el motivo con su error junto al campo | Paso 2 y 3 de COM-ANL-CBR; D-57 |
| Anular cobro (`ACT['anlcbr-ok']`) | No releía ni bloqueaba: anulaba directo | Con la huella: si cambió el cobro o el día vuelve a la pantalla con lo de ahora; si ya estaba anulado, informa y vuelve a la ficha | Paso 5 y extensión 5a |
| Anular cobro (`ACT['anlcbr-ok']`) | Borraba la alerta del cobro y no la volvía a crear | Asegura una alerta nueva por cada entrega que vuelve a «en mora» (la anterior queda en el historial) y avisa al Vendedor; el correo de mora solo si nunca había salido | Postcondición e; D-94 punto 5 |
| Anular cobro (`ACT['anlcbr-ok']`) | Tras anular con la casilla, iba directo a «Registrar cobro» con un aviso | Vuelve a la ficha del cobro anulado (con la anulación y «Registrar el cobro correcto»); la fecha original se propone desde ahí (`?anulacion=`) | Paso 7 y extensión 7a |
| Registrar cobro (`VIEWS.cobro`, `S.p.fc`) | La fecha del cobro anulado llegaba por el estado de la pantalla, sin límite | La casilla «Usar la fecha del cobro anulado» (marcada por omisión si el cliente pagó ese día), solo para el Gerente, solo con las entregas del cobro anulado y una sola vez; redibuja con HTMX sin validar y, sin JavaScript, con «Calcular total» | D-94 punto 10; `.claude/rules/interfaz.md` |
| Cobros registrados / ficha del cobro | Sin «Anular» y sin ficha | «Anular» (solo el Gerente, con el cobro vigente), la tarjeta «Anulación» (fecha, Gerente, motivo, si el cliente pagó) y el cobro que la corrigió | Pantallas de `cobranza.md`; D-30 (ningún botón lleva a un 403) |
| Cancelar compra-venta (`VIEWS.cvcancel`, sección 3) | «Cobro de lo entregado» con el medio como lista (`Efectivo`, `Transferencia`, `Tarjeta de débito`) y «Asientos: solo el del cobro» | Los **cuatro** medios de `PagoCliente.medio_pago` como botones de opción (menos clics), el detalle de lo entregado por entrega, el texto de la extensión 6a y el asiento como «Fuera de esta ronda · contabilidad»; el motivo pasa a la sección 4; el estado final dice «Concretada (se cobra lo entregado)» | Extensión 6a; D-57; criterio de interfaz |
| Cancelar compra-venta (`ACT['cvcancel-ok']`) | Dejaba el cobro sin resumen ni error del medio | El resumen muestra el cobro y el medio; sin medio, el error sale junto a los botones de opción; «Volver» conserva el medio | Pasos 6 y 7; 6a.2 |

**Verifiqué** (Claude Code, sin navegador, D-96)

- **El recorrido** `RecorridoDeAnulacionDeCobroTests` (cliente de Django, por rol y por estado): el Gerente anula un cobro de dos entregas (una en mora —con el **primer** correo de mora— y una pendiente) con motivo y «el cliente sí pagó»; el Vendedor sin «Anular» y con 403 por URL (también otro Vendedor, el Agrónomo y el Capataz); un cobro de compra-venta que no se anula desde acá; el error de motivo vacío; el cobro correcto con la fecha original (una sola vez) y sin la casilla; lo que libera la anulación (2b); y la cancelación de una compra-venta con una entrega concretada (el medio, el resumen sin escribir, el cobro, la venta «concretada», el comprobante con el cobro) y la auditoría. Pasa.
- **Migraciones:** `makemigrations --check`: sin cambios. `sqlmigrate comercial 0014`: borra dos restricciones de `Anulacion` (`anulacion_con_solicitud` y `anulacion_estado_con_solicitud`), agrega dos columnas **nulas** (`cliente_pago_en_fecha`, `pago_cliente_id` con `UNIQUE`) a `Anulacion` y una (`anulacion_corregida_id`, `UNIQUE`) a `PagoCliente`, y crea tres restricciones de `CHECK`; **no borra ni reescribe datos** (las `Anulacion` que ya existen tienen `solicitud` y `estado_anulado`, así que cumplen las nuevas). `sqlmigrate core 0052`: no-op (solo `choices`). Las dos se aplican en la base `test_…` cada vez que se la recrea (la recreé con `--noinput`, D-101).
- **`git fetch`** antes de crearlas y al cerrar: CMP-07 (PR #96) pasó a `main` mientras trabajaba; lo integré (`git merge origin/main`, sin conflictos); no sumó migraciones de `comercial` ni de `core` (sí `maestros` 0013): las mías siguen siendo 0014 y 0052.
- **Orden de bloqueo:** invertí a propósito el orden de la anulación (entregas antes que invernaderos; y el pago antes que las entregas) y las dos pruebas sondeadas fallaron; restauré el código y pasan. Las otras pruebas de concurrencia no lo detectan solas (ver «Lo que implementé distinto», punto 7).
- **Comandos de «Hecho cuando» (M1):** `python manage.py test comercial core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → `Ran 3600 tests … OK`; `python manage.py test comercial --keepdb --tag concurrencia` → `Ran 142 tests … OK`.
- **Tu base de desarrollo:** no la toqué (ni borré ni cargué datos); solo recreé bases `test_…`.

**Lo cubre una prueba** (no hace falta repetirlo a mano)

- Cada regla, postcondición y extensión de COM-ANL-CBR (1a, 3a, 5a, 7a con sus límites): `test_com_anl_cbr.py` y `ComRegCbrFechaDelCobroAnuladoTests` (`test_com_reg_cbr.py`).
- Las restricciones de la base y los invariantes 8 y 9: `test_modelos_cobranza.py`.
- Lo que libera la anulación (2b de COM-ANL-SRV y la regla 5 de COM-ATN-ENR): `test_regla_despues_de_anular_2b_…` y `…_la_regla_5_…` (la regla 5 no se puede preparar a mano con facilidad: la cubre solo la prueba).
- La extensión 6a (el pago, la venta «concretada», el medio, el aviso, la auditoría, el comprobante y la huella): `test_com_cnl_cvt.py`.
- Las pantallas y los permisos (el Vendedor sin «Anular», la casilla de 7a con HTMX, la sección «Cobro de lo entregado» y su resumen): `test_cobranza_vistas.py` (`AnulacionVistasTests`) y `ComCnlCvtVistaConCobroTests`.
- Dos anulaciones del mismo cobro, dos cobros correctos de la misma anulación, la anulación contra el paso 30, el orden de los bloqueos y la cancelación contra la concreción de la otra entrega: `test_anulacion_cobro_concurrencia.py` y `test_com_cnl_cvt_concurrencia.py`.

**No pude verificar**

- **Lo que solo ve un navegador:** el CSRF y el encabezado `Origin` de los formularios de anulación y de cancelación, el comportamiento real de HTMX (la casilla de 7a y la ventana del resumen), el aspecto, el teclado y el celular: van como los pasos 13, 14 y 15 de la «Verificación a mano».
- **El envío real de correo** (SMTP): las pruebas usan el servidor de correo simulado.
- **El contraasiento y el asiento del cobro de 6a:** fuera de la ronda (D-57); el código guarda todo lo que necesitan.
- **La migración hacia atrás** (`migrate comercial 0013`): no la ejercité.
- **La regla 5 de «Entrega no reconocida» a mano** (hace falta una alerta que nace de un cliente que responde «no recibí»): solo la cubre la prueba.
- **El despliegue en Render/Neon:** el paso 16 de la «Verificación a mano».
