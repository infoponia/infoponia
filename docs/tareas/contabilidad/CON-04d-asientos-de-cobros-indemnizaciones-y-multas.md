# CON-04d · Asientos de cobros, indemnizaciones y multas (comercial con dinero)

Estado: hecha (a la espera de la revisión a mano) | App: comercial | Rama: feature/con-04d-asientos-comercial-dinero | Ronda: Contabilidad 2

Depende de: **CON-02**, **USR-11** y de las tareas de Comercial que programan cada caso de uso (COM-06b, COM-07a, COM-07b, COM-08a, COM-08b). **D-92 punto
9:** si CON-02 ya estaba en `main` cuando se programó una de ellas, su fila ya está hecha; acá van solo las que falten.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Lo que mueve dinero en comercial sin mover stock: el cobro de un suministro y su anulación, el cobro al cancelar una
compra-venta, las indemnizaciones de las solicitudes de revisión y su anulación, la multa por resolución del suministro. Y el aviso «corregir con asiento manual» de una entrega no
reconocida pasa del Vendedor al **responsable contable** (H12).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto) | Lo programa |
|---|---|---|---|---|
| COM-REG-CBR | Registrar Cobro (post. d) | docs/casos_de_uso/comercial/cobranza.md | El `PagoCliente`, **un asiento compuesto** · Debe Caja (efectivo) o Banco c/c (los demás medios) por `monto_pagado` / Haber Deudores por Ventas por Σ `LineaPago.monto_cobrado` y Haber Indemnizaciones por Atraso en el Pago por Σ `indemnizacion_atraso`, si es mayor que 0 · fecha del cobro | COM-08a o esta tarea |
| COM-ANL-CBR | Anular Cobro (post. c) | docs/casos_de_uso/comercial/cobranza.md | La `Anulacion` · el contraasiento del cobro completo (incluida la indemnización por atraso), invertido, fecha actual | COM-08b o esta tarea |
| COM-CNL-CVT | Cancelar Compra-venta (post. f, ext. 6a) | docs/casos_de_uso/comercial/compra_venta.md («La extensión 6a (COM-08b)») | El `PagoCliente` de compra-venta · Caja o Banco c/c (según el medio) / Deudores por Ventas · lo cobrado | COM-08b o esta tarea |
| COM-EVL-DSC | Evaluar Discrepancia (post. e) | docs/casos_de_uso/comercial/solicitudes.md | La `SolicitudRevision` · Indemnizaciones por Incumplimiento a Cliente / Deudores por Ventas (sin pagar) o Caja o Banco c/c (ya pagada, según el medio de reintegro) · la indemnización | COM-07a o esta tarea |
| COM-RSV-QJA | Resolver Queja (post. e) | docs/casos_de_uso/comercial/solicitudes.md | Igual, con el caso compuesto (parte contra Deudores, el resto contra Caja o Banco) · solo si el monto es mayor que 0 | COM-07a o esta tarea |
| COM-ANL-SRV | Anular Resolución de Solicitud (post. c) | docs/casos_de_uso/comercial/solicitudes.md | La `Anulacion` · el contraasiento del de la solicitud (mismas cuentas e importes, invertidos), fecha actual; si el ejercicio del original está cerrado, va al abierto | COM-07a o esta tarea |
| COM-RSV-SUM | Resolver Suministro por Incumplimientos (post. h) | docs/casos_de_uso/comercial/resolucion.md | El `Suministro` (R012) · Indemnizaciones por Resolución de Contratos / **2.1.02 Indemnizaciones a Pagar** · la multa, si es mayor que 0 | COM-07b o esta tarea |
| COM-ATN-ENR | Atender Entrega No Reconocida (post. b) | docs/casos_de_uso/comercial/confirmacion.md | Sin asiento: el aviso «corresponde corregir con un asiento manual» va a `responsable_contable()` (y al Gerente), no al Vendedor | COM-06b o esta tarea |

La cuenta **2.1.02 Indemnizaciones a Pagar** ya la carga CON-02 (D-84 punto 7; la aprobó Ezequiel el 23/11/2026). El pago de la multa no tiene
caso de uso: el Contador lo registra con un asiento manual (Debe Indemnizaciones a Pagar / Haber Caja o Banco c/c; D-92 punto 10).

## Leer

- Casos de uso: de cada extracto, la postcondición del asiento, su regla «Asiento», lo marcado «Fuera de esta ronda · contabilidad» y, en
  `resolucion.md`, los temas abiertos de la multa (quedan resueltos por D-92 punto 10).
- Decisiones: D-92, D-86, D-85 (responsable contable), D-94 (cobranza: `LineaPago`, puntos 2, 3, 10 y 14), D-69 (punto 8), D-67, D-68, D-57, D-44.
- API: docs/api/asientos.md (`registrar_asiento_automatico` y `responsables.notificar_al_responsable_contable`). `contraasentar` es del Contador
  (CON-03b): la anulación usa `registrar_asiento_automatico` con los movimientos del original invertidos y la `Anulacion` como origen.
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md.
- Reglas: .claude/rules/pruebas.md.
- Código a leer: los servicios que nombra la «Cómo se aplica» de cada extracto, sus pruebas y las de concurrencia.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `docs/casos_de_uso/comercial/resolucion.md` (cerrar los temas abiertos de la multa citando D-92); al cerrar, M3 y
  `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el cobro de una compra-venta en su última entrega (va dentro del asiento compuesto de la entrega: CON-04c).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Cobros:** el de un suministro (con y sin indemnización por atraso), su anulación y el cobro al cancelar una compra-venta. — pruebas: las de
   COM-REG-CBR, COM-ANL-CBR y COM-CNL-CVT (ext. 6a).
2. **Indemnizaciones** (discrepancia y queja, con el caso compuesto). — pruebas: las de COM-EVL-DSC y COM-RSV-QJA (sin asiento con monto 0).
3. **Anulación** con el contraasiento (también cuando el original quedó en un ejercicio cerrado). — pruebas: las de COM-ANL-SRV.
4. **Multa** del suministro. — pruebas: las de COM-RSV-SUM (multa 0 → sin asiento).
5. **Aviso de COM-ATN-ENR** al responsable contable. — pruebas: las de COM-ATN-ENR (con y sin Contador activo).

## Hecho cuando

- Cada fila asienta lo que dice; el Vendedor ya no recibe el aviso de COM-ATN-ENR y el Contador (o el Gerente sin Contador) sí.
- Comando de pruebas: `python manage.py test comercial contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test comercial --keepdb --tag concurrencia`.

## Verificación a mano

Precondiciones: la base de desarrollo con el plan de cuentas (lo carga la migración) y **un ejercicio abierto** (si no hay, el primer asiento lo abre solo). Cuentas: un **Gerente**, un **Vendedor**, un **Contador activo** (alta desde «Cuentas», como Gerente) y un **Agrónomo**. Un **cliente con correo** y un **suministro vigente** del Vendedor, con tres entregas **concretadas** por el flujo normal y **sin cobrar**. Para la mora: una entrega concretada cuyo vencimiento del pago ya pasó (plazo de pago corto, por ejemplo 5 días, y una concreción de hace más de 5 días). Tené a mano la contraseña de cada cuenta (no la escribas en ningún archivo).

1. **Cobro con atraso (Vendedor).** Entrá como **Vendedor** › «Comercial» › «Cobranza» › «Registrar cobro». Elegí el cliente y **una entrega en mora**, medio **«Transferencia»**, y tocá «Revisar y registrar». *Tiene que verse* un bloque **«Asiento que se registra al confirmar»** con una tabla: **Banco c/c · Debe** por el total, **Deudores por Ventas · Haber** por lo cobrado e **Indemnizaciones por Atraso en el Pago · Haber** por el atraso. Ya **no** debe decir «Fuera de esta ronda». *(lo cubre `test_tarea_con04d_el_resumen_del_cobro_muestra_las_lineas…`)*
2. **Confirmar.** Tocá «Confirmar cobro». Entrá a la ficha del cobro (COB-NNNN): abajo tiene que decir **«Asiento del cobro · Asiento N.º 1»** con las mismas líneas, **sin ser un enlace**. *(lo cubre el recorrido)*
3. **Cobro en efectivo sin atraso.** Cobrá otra entrega **no vencida** con medio **«Efectivo»**: el asiento tiene solo **Caja · Debe** y **Deudores por Ventas · Haber** (sin línea de atraso). *(lo cubre `test_post_d_efectivo_sin_atraso…`)*
4. **Anular el cobro (Gerente).** Entrá como **Gerente** › «Cobranza» › «Cobros registrados» › el primer cobro › «Anular». La pantalla muestra **«Contraasiento que se registra»** con Debe y Haber **invertidos**. Escribí un motivo y confirmá. La ficha del cobro ahora muestra **«Contraasiento de la anulación · Asiento N.º 2»**. *(lo cubre `test_tarea_con04d_anular_cobro_muestra…`)*
5. **El libro (Contador y Gerente).** Entrá como **Contador** › «Contabilidad». Tienen que estar los asientos creados, con **Debe = Haber** en «Totales». Abrí la ficha del N.º 1: el origen dice **«Cobro COB-NNNN · <cliente>»** y el del N.º 2 **«Anulación del cobro COB-NNNN»**, como **texto, sin enlace**. Repetí como **Gerente**: se ve igual. *(lo cubre el recorrido)*
6. **Quién no ve nada.** Entrá como **Agrónomo** y como **Vendedor** y probá abrir «Contabilidad»: no aparece en el menú y, por URL, da «Prohibido (403)». El Contador tampoco ve «Cobranza» (403). *(lo cubren el recorrido y `PermisosTests`)*
7. **Indemnización de una discrepancia (Gerente).** Con una discrepancia pendiente (una entrega concretada con menos plantas que la mínima), entrá como **Gerente** › «Solicitudes» › la solicitud › «Aceptar» › «Ver resumen». *Tiene que verse* **«Asiento que se registra al confirmar»**: **Indemnizaciones por Incumplimiento a Cliente · Debe** y **Deudores por Ventas · Haber** (entrega sin cobrar). Confirmá y mirá el libro: un asiento nuevo con origen **«Indemnización de la discrepancia SR-NNNN…»**. *(lo cubre `test_tarea_con04d_el_resumen_de_aceptar…`)*
8. **Entrega ya cobrada.** Con otra solicitud sobre una entrega **ya cobrada**, el resumen pide el medio de reintegro: con «Transferencia» el asiento va contra **Banco c/c · Haber**; con «Efectivo», contra **Caja**. *(lo cubren `test_ext_6a_con_la_entrega_pagada…`)*
9. **Anular la resolución.** Anulá la solicitud del paso 7: la pantalla muestra **«Contraasiento que se registra»**; al confirmar, el libro tiene el contraasiento (fecha de hoy). *(lo cubre `test_post_c_la_anulacion_origina_el_contraasiento…`)*
10. **Volver a aceptar (decisión del 26/11/2026).** Aceptá otra vez la misma solicitud. **No** se crea un asiento nuevo (un origen, un asiento): entrá como **Contador** › campana: hay un aviso **«Registrar el asiento de SR-NNNN»**. Anulala de nuevo: no hay otro contraasiento y el Contador recibe **«Revertir a mano el asiento de SR-NNNN»**. *(lo cubren `test_tarea_con04d_reaceptacion…` y `test_tarea_con04d_anular_reaceptacion…`)*
11. **Multa por resolución.** Con un suministro de **multa mayor que 0** y más incumplimientos que los tolerados (aceptá quejas hasta superarlos), la última aceptación **resuelve el contrato**. Abrí la ficha del suministro como **Gerente**: la multa muestra **«Asiento N.º X»** con **Indemnizaciones por Resolución de Contratos · Debe** e **Indemnizaciones a Pagar · Haber**. En el libro, «Indemnizaciones a Pagar» queda con **saldo acreedor**. Con multa 0, la ficha dice «El contrato no prevé multa» y no hay asiento. *(lo cubren `ComRsvSumAsientoTests` y `test_tarea_con04d_la_ficha_muestra_el_asiento_de_la_multa…`)*
12. **Cancelar una compra-venta con lo entregado.** Con una compra-venta de dos entregas, la primera ya concretada: «Cancelar» › elegí motivo y medio **«Efectivo»** › «Revisar»: el resumen muestra **Caja · Debe / Deudores por Ventas · Haber** por lo entregado. Confirmá y verificá el asiento en el libro (origen «Cobro de lo entregado · CV-…»). *(lo cubre `test_post_f_el_cobro_en_efectivo_asienta_caja…`)*
13. **Entrega no reconocida.** Con una entrega concretada que el cliente respondió «no recibí» (alerta crítica), entrá como **Gerente** › la alerta › «Atender». En «Asientos» se ven **los de la entrega** (venta y costo, y los consumos de envases). Elegí **«No llegó, producto perdido»**, escribí la descripción y resolvé. Entrá como **Contador**: aviso **«Corregir los asientos de OT-…»**. Entrá como **Vendedor**: **no** hay aviso. *(lo cubren `test_post_b_con_contador_…` y `test_post_b_no_llego_ya_no_avisa_al_vendedor…`)*
14. **Auditoría.** Como **Gerente** › «Auditoría»: los registros de cobro, anulación de cobro, evaluación de discrepancia, anulación de resolución y resolución de suministro nombran el asiento entre los afectados; aparecen aparte los «alta de asiento contable». *(lo cubren las pruebas `test_post_g…`, `test_post_f…`, `test_post_k…` y `test_post_m…`)*
15. **Navegador real.** Abrí **una ventana privada**, entrá como **Vendedor** y **enviá hasta el final** «Registrar cobro» («Revisar y registrar» y «Confirmar cobro»); después, como **Gerente**, enviá hasta el final «Anular cobro», «Aceptar» y «Anular resolución» de una solicitud, «Cancelar» una compra-venta con cobro y «Atender» una entrega no reconocida. En cada una volvé a abrir la pantalla: tiene que mostrar el resultado y el asiento tiene que estar en el libro. Si aparece **«Prohibido (403)»** o **«Verificación CSRF fallida»**, o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. *(Opcional)* **Sin JavaScript** en «Registrar cobro» y en «Aceptar»: los dos pasos (resumen y confirmar) funcionan con envíos comunes.
16. **Todo o nada y la fecha del hecho en un ejercicio cerrado (D-102).** No se pueden forzar a mano: los cubren las pruebas (`test_garantia_si_falla_el_asiento…`, `test_d102_…`).

## Cierre

### Qué se hizo

**Ninguna de las ocho filas estaba hecha** (COM-06b, COM-07a, COM-07b, COM-08a y COM-08b se mergearon con «Fuera de esta ronda · contabilidad»; el código no llamaba a `registrar_asiento_automatico`): se hicieron las ocho. Sin modelos, sin migraciones, sin dependencias (`makemigrations --check`: «No changes detected»).

| Fila | Dónde | Asiento |
|---|---|---|
| COM-REG-CBR (d) | `cobranza._registrar` | UN compuesto, origen el `PagoCliente`: Debe Caja (efectivo) o Banco c/c por `monto_pagado` / Haber Deudores por Ventas por Σ `monto_cobrado` / Haber Indemnizaciones por Atraso por Σ `indemnizacion_atraso` (si > 0); fecha = `fecha_pago` |
| COM-ANL-CBR (c) | `cobranza._anular` | contraasiento con la `Anulacion` de origen: los movimientos del cobro invertidos, fecha de hoy |
| COM-CNL-CVT 6a | `compra_ventas._cancelar` | origen el `PagoCliente` de la compra-venta: Debe Caja o Banco c/c / Haber Deudores por Ventas por lo cobrado; fecha de hoy |
| COM-EVL-DSC y COM-RSV-QJA (e) | `solicitudes._registrar` | origen la `SolicitudRevision`: Debe Indemnizaciones por Incumplimiento / Haber Deudores (descontado) y Caja o Banco (reintegrado); monto 0, sin asiento |
| COM-ANL-SRV (c) | `solicitudes._anular` | contraasiento con la `Anulacion` de origen (los movimientos del asiento de la indemnización invertidos), fecha de hoy |
| COM-RSV-SUM (h) | `resoluciones._resolver` | origen el `Suministro`, actor `None` (InfoPonia): Debe Indemnizaciones por Resolución / Haber 2.1.02 Indemnizaciones a Pagar; multa 0, sin asiento |
| COM-ATN-ENR (b) | `atencion.atender_entrega_no_reconocida` | sin asiento; el aviso va solo a `responsable_contable()` (sin el Gerente que atiende, H21) |

- **Reutilización.** Todo en `comercial/servicios/asientos_comerciales.py` (CON-04c): funciones puras que arman los movimientos (las usan también los resúmenes, así la pantalla muestra exactamente lo que se registra) y funciones que asientan. El asiento va **después de todos los bloqueos de negocio** (el ejercicio se bloquea último, D-86) y entra en los `afectados` y en `datos["asientos"]` del registro de auditoría de cada caso de uso (no se audita aparte).
- **Contraasientos.** `asentar_anulacion` usa `registrar_asiento_automatico` con los movimientos del original invertidos y la `Anulacion` como origen (no `contraasentar`, que es del Contador). Si el original no tiene asiento (anterior a esta tarea, D-92 punto 1) no hay contraasiento y no falla.
- **Texto de origen en el libro** (`comercial/apps.py`): `pago_cliente`, `solicitud_revision`, `anulacion` y `contrato` (la multa), **sin dirección** (el Contador no abre esas pantallas y D-30 prohíbe un enlace que lleve a un error; mismo criterio que CON-04a y CON-04c).
- **Pantallas** (decisión 3 de abajo): un fragmento común `comercial/_asiento.html` reemplaza las siete etiquetas «Fuera de esta ronda · contabilidad».

**Decisiones del estudiante del 26/11/2026** (se registran en `docs/temas_abiertos.md`):
1. **Asiento del cobro que corrige uno anulado (7a):** lleva la `fecha_pago` (la del cobro anulado), no la actual, según D-92 punto 4; si cae en un ejercicio cerrado, D-102. *(Prueba: `test_d92_cobro_7a_asienta_con_la_fecha_del_cobro_anulado` y `test_d102_cobro_7a_con_el_ejercicio_de_esa_fecha_cerrado…`.)*
2. **Sin transición para Deudores por Ventas:** las entregas anteriores a CON-04c sin asiento solo existen en datos de desarrollo y de prueba; lo real entra por la carga inicial (D-92 punto 1). *(Prueba: `test_d92_cobro_de_entrega_sin_asiento_de_concrecion_va_contra_deudores`.)*
3. **Pantallas con el asiento real**, sin enlace y solo a los roles que ya ven importes. *(Pruebas: `test_tarea_con04d_…` en `test_cobranza_vistas`, `test_solicitudes_vistas`, `test_resolucion_vistas`, `test_confirmacion_vistas` y `test_com_cnl_cvt`.)*
4. **Re-aceptación de una solicitud cuya aceptación anterior se anuló** (choque con R012, un origen un asiento): no asienta y avisa al responsable contable («Registrar el asiento de SR-…») para registrarla a mano, con constancia en la auditoría (`asiento_manual_pendiente`). Si después se anula esa re-aceptación, no hay contraasiento (el original ya se revirtió) y se avisa («Revertir a mano el asiento de SR-…»). Un origen nuevo exigiría modelo y migración: queda para una decisión aparte. *(Pruebas: `test_tarea_con04d_reaceptacion_…` y `test_tarea_con04d_anular_reaceptacion_no_contraasienta_de_nuevo`.)*
5. **H21 en COM-ATN-ENR:** sin Contador, el responsable contable es el Gerente que atiende y no se le avisa a quien actúa (D-85 punto 7). La frase «el Gerente sin Contador sí» de «Hecho cuando» y «(y al Gerente)» de la tabla **no se pueden cumplir sin excepcionar H21**; se siguió H21.

**Diferencias con la documentación** (para `docs/temas_abiertos.md`):
- **Riesgo del contraasiento automático.** No se vincula al original con `anula` (la restricción `asiento_no_es_automatico_y_contraasiento` lo impide): el original **no figura «Anulado»** en el libro, y el Contador podría contraasentar a mano el mismo cobro o la misma solicitud y revertirlo **dos veces**. Un candado exigiría un cambio de modelo.
- La tabla pide «fecha del cobro» y la postcondición d de COM-REG-CBR dice «fecha actual»: rige D-92 punto 4 (decisión 1).
- Las marcas «Fuera de esta ronda · contabilidad» de `cobranza.md`, `solicitudes.md`, `compra_ventas.md`, `confirmacion.md` y de los «Cómo se aplica» de esos extractos y de `resolucion.md` quedan falsas (se actualizan en M3; solo se tocó el tema abierto de la multa de `resolucion.md`, permitido por la tarea).
- `DESCRIPCION_DE_CUENTA` de «Indemnizaciones por Atraso en el Pago» (`contabilidad/cuentas.py`) nombra a COM-VNC-PAG como quien la mueve, pero el paso 30 no asienta (solo alerta): no se tocó `contabilidad/`.
- `docs/patrones/bloqueos.md` («Resolver o anular… la entrega no reconocida») nombra al Vendedor entre las cuentas que bloquea COM-ATN-ENR: ya no se bloquea (no recibe el aviso).
- COM-ATN-ENR, regla 1: «los asientos» de la ficha son los de la entrega (venta y costo), sus mermas, sus consumos de envase y el del cobro vigente.

**Pantallas: lo que se corrigió del prototipo (D-61).** Ninguna pantalla nueva. En las existentes, el bloque «asiento» del prototipo («Solo prototipo», con datos de ejemplo) se reemplazó por el asiento real, que el prototipo no tiene.

**Pruebas existentes que cambiaron** (sin debilitarlas: la regla cambió; las listo para el PR): se **reemplazaron** `test_post_d_no_se_crea_ningun_asiento_en_esta_ronda` (reg_cbr), `test_post_c_no_crea_el_contraasiento_fuera_de_esta_ronda` (anl_cbr), `test_post_e_no_se_crea_ningun_asiento_fuera_de_la_ronda` (evl_dsc), `test_post_h_no_se_crea_ningun_asiento_aunque_haya_multa` (rsv_sum) y dos de COM-ATN-ENR (`test_post_b_no_llego_avisa_al_vendedor_…` y `test_post_b_con_contador_el_aviso_va_al_contador_y_no_al_gerente`). Cambiaron las listas de afectados que fijaban (`evl_dsc`, `rsv_qja`, `anl_srv`: suman `contabilidad.asientocontable`), el recorrido de confirmación (el Vendedor ya no recibe el aviso) y las aserciones del texto «Fuera de esta ronda» de las pruebas de vistas y de recorrido. Las `Base` de `test_com_atn_enr`, `BaseDeCobranza`, `BaseDeSolicitudes`, `BaseDeResolucion`, `test_com_cnl_cvt`, `test_resolucion_vistas`, `test_confirmacion_vistas` y de dos recorridos heredan `PlanDeCuentasMixin`: **el cambio en `test_com_atn_enr` corrige una falla previa con `--keepdb`** (18 errores también en `main`: faltaba el plan de cuentas, que CON-04c necesita al concretar una entrega).

**Datos de la base de desarrollo.** No se tocó tu base de desarrollo: no se corrió `migrate`, ni `runserver`, ni nada contra ella. Las pruebas usaron bases `test_…`. No se borró nada.

**Integración con `main`.** Se trajo la PR de COM-08c (#102, ya en `main`) con `git merge --no-commit`: sin conflictos (no comparte archivos con esta tarea). El merge queda **sin commitear** para que lo confirmes.

**Decisiones.** Ninguna nueva en `docs/decisiones/` (D-92, D-86, D-85, D-102, D-94, D-69). Las cuatro decisiones del 26/11/2026 van a `temas_abiertos.md`; el origen nuevo de la re-aceptación necesitaría una decisión.

### Pruebas (M1)

- `python manage.py test comercial contabilidad --keepdb --exclude-tag concurrencia --exclude-tag migracion` (en serie: el runner paralelo no muestra los tracebacks sin `tblib`) → **3500 pruebas, 1 falla ajena**: `test_prod_asg_stk.test_post_a_b_c_d_una_reserva_activa…` espera `^OT-\d{4}$` y la secuencia de la base de pruebas con `--keepdb` ya va por `OT-33262`; no depende de esta tarea: el patrón de 4 dígitos choca con la secuencia acumulada de la base `--keepdb`. **Con una base de pruebas nueva pasa** (93 pruebas OK).
- `python manage.py test comercial --keepdb --tag concurrencia` → **167 pruebas, OK** (en serie).
- `python manage.py test demo` → **78 pruebas, OK** en una base de pruebas nueva. (Corrida justo después de las de concurrencia sobre la misma base `--keepdb`, `demo` dio `KeyError: 'Ventilador'` en `demo/carga.py`: el `flush` de los `TransactionTestCase` borra los datos de catálogo de las migraciones; no es de esta tarea y no se tocó `demo/`.)
- `makemigrations --check`: sin cambios.
- **Las pruebas de cada paso (cobros, indemnizaciones, anulación, multa y aviso, y las de la decisión 3 de las pantallas) se escribieron primero y se mostró que fallaban** antes de implementar, y las revisaste antes de cada servicio.

### Informe

**Verifiqué:**
- El recorrido `RecorridoDeAsientosDeDineroTests` y `RecorridoDeIndemnizacionesTests` (2 pruebas, por rol y por estado): el Vendedor revisa y confirma el cobro de una entrega en mora (resumen y ficha con el asiento); el Gerente anula (contraasiento) y registra el correcto; el Contador y el Gerente leen el libro y la ficha de cada asiento con su origen **sin enlace**; el Agrónomo, el Capataz, el Vendedor y el Transportista reciben 403 en el libro. La indemnización: aceptar, anular, volver a aceptar (sin asiento y con aviso al Contador); el Vendedor y el Agrónomo reciben 403 en «Anular».
- Migraciones: no hay.
- Concurrencia: cierre del ejercicio contra el cobro, la aceptación, la anulación y la resolución (los dos órdenes), el ejercicio como último bloqueo (cobro, aceptación y resolución) y numeración sin huecos (cobro y anulación).

**Lo cubre una prueba:** cada paso de la «Verificación a mano» dice cuál.

**No pude verificar:**
- Todo lo que se ve en tu navegador y en tu base de desarrollo (pasos 1 a 15): no abro navegador ni toco esa base.
- **El paso de «navegador real» (paso 15):** CSRF, `Origin` y JavaScript de los formularios de registrar y anular cobro, aceptar y anular una solicitud, cancelar una compra-venta con cobro y atender una entrega no reconocida.
- **Sin prueba de concurrencia del asiento de 6a** (cancelar una compra-venta con cobro): armarla exige una compra-venta con una entrega concretada y la ruta iniciada; la numeración y el bloqueo del ejercicio los cubren las pruebas del cobro.
- **Sin prueba del orden de bloqueo (el ejercicio como último bloqueo) en la anulación de un cobro ni en la de una resolución:** solo el Gerente anula y es uno solo, así que dos anulaciones quedan en fila en su cuenta y la prueba no distinguiría nada. Las cubren la de numeración sin huecos (cobro) y la de cierre contra anulación (resolución).
- **Sin prueba de numeración con dos resoluciones de suministro a la vez:** exige armar un segundo suministro con todo su escenario.
- El registro en la pantalla «Auditoría» (paso 14), que solo se ve en el navegador.
- La falla ajena de `test_prod_asg_stk` con `--keepdb` (arriba) y el cruce de `demo` con las pruebas de concurrencia en la misma base `--keepdb` (abajo): ambas pasan con la base de pruebas nueva.

