# Casos de uso · contabilidad · Asientos manuales y contraasientos

Copia para el repo de CON-REG-ASI y CON-CTR-ASI, de los archivos fuente de la ronda de Contabilidad (CON-REG-ASI.md, CON-CTR-ASI.md). Cotejado con `decisiones_A0.md` y
`pendientes_para_pegar.md` (**esas decisiones ganan** si algo difiere, regla de Ezequiel del 23/11/2026).

**El código va en la app `contabilidad`** (D-37, nivel 2); archivos de pruebas bajo `contabilidad/tests/`. Si este archivo y el
documento de Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>` y `test_post_<letra>_<que_espera>`.

---

## **Caso de uso CON-REG-ASI: Registrar Asiento Manual**

Caso de uso extendido del módulo Contabilidad (versión 0.1, 23/11/2026), con el formato de «CU extendidos». Reemplaza a CU-17 de «Documentación para la IA» y al caso 11 de PCU en lo que hace al asiento manual (el contraasiento pasa a CON-CTR-ASI). Decisiones aplicadas: X3 (rol Contador), H1, H3/H4 (asiento de apertura), H5/H6/H7 (plan de cuentas), H8 (numeración), H10 (fecha), H11 (importe cero), H12 y C2, C4, C6 (decisiones_A0.md).

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Contabilidad.
**Actor principal:** Contador. Si no hay un Contador activo, el Gerente (extensión 1a).
**Versión:** 0.1

**Personal involucrado e intereses**

**Contador:**
- quiere registrar hechos económicos que el Sistema no asienta solo (la apertura, las ventas de producción previa a la puesta en marcha, el arqueo de caja, un pago no previsto);
- quiere que el asiento quede balanceado y con el motivo explicado, sin tener que corregirlo después.

**Gerente:**
- quiere que los números de gestión reflejen todo lo que pasó en la organización;
- quiere poder registrar el asiento cuando no hay un Contador activo.

**Organización (Jardín Botánico):**
- quiere que lo anterior a la puesta en marcha entre a la contabilidad por una vía controlada (Capital Inicial);
- quiere que el libro de gestión nunca tenga un asiento desbalanceado ni con huecos de numeración.

**Relaciones con otros casos de uso**
- No incluye otros casos de uso.
- No es extendido por otros casos de uso.
- **Disparador:** un hecho económico sin asiento automático, o el aviso «registrar asiento manual» que genera COM-ATN-ENR (postcondición b), según H12.
- **Lo sigue:** CON-CNS-LGS · Consultar Libro de Gestión, donde se ve el asiento registrado.
- **Relacionado:** CON-CTR-ASI · Contraasentar Asiento al terminar un contraasiento se ofrece registrar el asiento correcto con este caso de uso, con datos precargados (extensión 1b, C4).

**Precondiciones**
a. El actor está autenticado en el Sistema con una cuenta activa de Contador o, si no hay un Contador activo, de Gerente.
b. Existe al menos un ejercicio contable «abierto» (siempre existe: ver CON-ABR-EJE y H9).
c. Existen las cuentas contables del plan de cuentas (se cargan por migración, D-37).

**Garantías mínimas**
El registro es atómico. Si el caso de uso se cancela o falla:
- no queda registrado ningún asiento ni movimiento contable;
- no cambia el último número de asiento de ningún ejercicio;
- no se registra ningún log de auditoría parcial.

**Además:**
- Un asiento registrado no se edita ni se elimina: se corrige con CON-CTR-ASI (GLO › Asiento Contable).
- Nunca se registra un asiento con importe total cero ni con menos de dos movimientos (H11).
- No se modifica ninguna otra entidad del Sistema (stock, contratos, entregas, etc.): el asiento manual solo toca la contabilidad.

**Garantías de éxito (Postcondiciones)**
a. Se creó un asiento contable sin documento de origen, con la fecha indicada, la descripción y el número siguiente al último del ejercicio que lo contiene (correlativo, sin huecos).
b. Se creó un movimiento contable por cada línea ingresada (cuenta, tipo Debe o Haber e importe mayor que cero). La suma del Debe es igual a la suma del Haber.
c. El ejercicio que contiene al asiento guardó el nuevo último número.
d. Se creó un log de auditoría por el asiento y por cada movimiento creado, con usuario, rol (Contador o Gerente), fecha, hora, identificador y valores. No hay documento de origen: el usuario queda en el log (regla 16 de 8.20).

**Escenario principal de éxito (Flujo Básico)**
(El Contador registra un asiento manual, con fecha dentro del ejercicio abierto, balanceado y con descripción.)

1. **El Contador inicia el registro de un asiento manual.**
2. **El Sistema presenta el formulario del asiento: fecha (por defecto, la fecha actual), descripción, y las líneas de movimiento (cuenta del plan de cuentas, Debe o Haber, importe). Muestra el ejercicio abierto y su rango.**
3. **El Contador indica la fecha, la descripción y, para cada línea, la cuenta, si va al Debe o al Haber y el importe.**
4. **El Contador indica que terminó de cargar el asiento.**
5. **El Sistema verifica los datos y presenta el resumen: el ejercicio al que irá el asiento, el total del Debe, el total del Haber, la diferencia (debe ser 0) y el tipo de cada cuenta (Activo, Pasivo, etc.).**
6. **El Contador confirma el registro.**
7. **El Sistema registra el asiento:**
   - bloquea el ejercicio, toma su último número y le suma 1;
   - crea el asiento y sus movimientos;
   - registra la auditoría correspondiente.
8. **El Sistema informa al Contador que el asiento fue registrado, con su número y ejercicio.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 6), el actor cancela el registro:**
1. El Sistema descarta los datos ingresados sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa al actor que el asiento no fue registrado.
3. El actor reinicia desde el paso 1.

**1b. El actor llega desde CON-CTR-ASI para registrar el asiento correcto de una corrección (C4):**
1. En el paso 2, el formulario viene precargado con las líneas del asiento anulado y una descripción sugerida («corrección del asiento N.º X»); el actor las modifica.
2. El caso de uso continúa en el paso 3. Es un asiento manual común: no queda vinculado al contraasiento.

**1a. No hay un Contador activo y el Gerente registra el asiento:**
1. El caso de uso continúa en el paso 2 con el Gerente como actor.
2. En el paso 7, el log de auditoría deja al Gerente como autor (rol Gerente).
3. Si hay un Contador activo, el Sistema no permite el registro al Gerente e indica que lo registra el Contador (regla «Quién registra»).

**3a. El actor quiere registrar el asiento de apertura (carga inicial de saldos):**
1. El actor usa como descripción «Asiento de apertura» (o equivalente) y carga Debe en Caja, Banco c/c y/o las demás cuentas de activo previas, y Haber en Capital Inicial y/o Proveedores (deudas previas).
2. El caso de uso continúa en el paso 4. (H3/H4; la parte de insumos va por el ajuste «carga inicial» de CMP-AJT-STK, no por acá.)

**3b. El actor quiere registrar la venta de producción previa a la puesta en marcha:**
1. El actor carga Debe Caja o Banco c/c / Haber Ventas.
2. El caso de uso continúa en el paso 4. (Decisión sobre lotes previos, H3/H4.)

**5a. Falta la descripción:**
1. El Sistema señala que la descripción es obligatoria en un asiento sin documento de origen.
2. El actor la completa (vuelve al paso 3).

**5b. El Debe y el Haber no suman lo mismo:**
1. El Sistema señala la diferencia y no permite confirmar.
2. El actor corrige (vuelve al paso 3).

**5c. El asiento tiene menos de dos movimientos, o una línea tiene importe cero, negativo o con más de dos decimales:**
1. El Sistema señala el error. Las líneas de importe cero se omiten y, si quedan menos de dos movimientos, no hay asiento (H11).
2. El actor corrige (vuelve al paso 3) o cancela.

**5d. La fecha cae en un ejercicio «en cierre»:**
1. El Sistema acepta el asiento: en ese ejercicio entran los asientos manuales con fecha en su rango (H1).
2. El resumen del paso 5 indica que el asiento va al ejercicio en cierre.

**5e. La fecha cae en un ejercicio «cerrado», es anterior al primer ejercicio o es posterior a la fecha actual:**
1. El Sistema rechaza el asiento con un mensaje que explica el motivo (C2). Solo se aceptan fechas dentro de un ejercicio «abierto» o «en cierre» y no posteriores a hoy.
2. El actor corrige la fecha (vuelve al paso 3) o cancela.

**7a. Al registrar, la cuenta elegida ya no existe o dejó de estar disponible:**
1. El Sistema no registra ningún cambio e informa las líneas afectadas.
2. El caso de uso vuelve al paso 3.

**7b. Al registrar, el ejercicio cambió de estado (por ejemplo, pasó a «cerrado» u otro ejercicio pasó a «en cierre») y la fecha ya no cae donde estaba:**
1. El Sistema no registra ningún cambio, informa el nuevo estado y vuelve al paso 5 (se reevalúa la regla de la fecha).

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 7 se completa en no más de 3 segundos.
- El registro es una única transacción: el asiento, sus movimientos, el último número del ejercicio y los logs se registran juntos o ninguno.
- El control de concurrencia (`select_for_update` sobre el ejercicio) impide que dos asientos simultáneos tomen el mismo número y garantiza la numeración correlativa sin huecos (H8).
- Los montos se expresan en pesos argentinos con dos decimales.
- La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**
- **Quién registra:** el Contador. Si no hay un Contador activo, el Gerente; si hay uno activo, el Gerente no registra asientos. El Vendedor no los registra (X3 y H12; cambia MD-31). (Precondición a, extensión 1a)
- **Tipo de asiento:** un asiento sin documento de origen ni contraasiento es manual; el tipo se deduce, no se guarda. (Regla 15 de 8.20)
- **Descripción:** obligatoria; explica el motivo. (Regla 16 de 8.20; extensión 5a)
- **Balance:** Debe = Haber, con al menos dos movimientos, con importes mayores que cero. Los de importe cero se omiten. (H11; extensiones 5b y 5c)
- **Ejercicio del asiento:** va al ejercicio cuyo rango contiene su fecha. Si ese ejercicio está «en cierre», entra igual (H1). Si la fecha cae en un ejercicio «cerrado» o es futura, se rechaza (C2); la redirección al abierto de H10 vale solo para los asientos automáticos. (Extensiones 5d y 5e)
- **Fecha:** la del hecho, no la del registro, salvo en el caso anterior. (H10)
- **Numeración:** correlativa por ejercicio, sin huecos; el número indica el orden de registro, no el de la fecha (consecuencia aceptada de H1 b). (H8)
- **Plan de cuentas:** solo se usan cuentas del plan vigente (CON-CNS-PCT). No hay restricciones sobre qué cuentas se pueden usar a mano (C6). No hay IVA (simplificación declarada). (H5/H6/H7)
- **Apertura:** la realidad previa a la puesta en marcha entra con asiento manual de apertura, acreditando Capital Inicial, más el ajuste de insumo «carga inicial». (H3/H4; extensión 3a)
- **Sin efecto operativo:** el asiento no toca stock, contratos ni entregas.
- **Auditoría:** el usuario real queda en el log, con su rol. (Regla 16 de 8.20)

**Lista de tecnología y variaciones de datos**
- **3.** Cuenta: de la lista del plan de cuentas (código rubro.subrubro.cuenta; tipos Activo, Pasivo, Patrimonio neto, Resultado positivo, Resultado negativo). Importe: hasta dos decimales. Descripción: texto libre, obligatoria.

**Frecuencia**
Baja: unas pocas por mes, más algunas muy al comienzo (apertura y ventas previas).



---

## **Caso de uso CON-CTR-ASI: Contraasentar Asiento**

Caso de uso extendido del módulo Contabilidad (versión 0.1, 23/11/2026), con el formato de «CU extendidos». Sale de dividir el caso 11 de PCU («Registrar Asiento (manual y contraasiento)») en dos casos de uso, porque tienen objetivos distintos: uno crea un asiento desde cero y el otro anula uno existente (ver README). Decisiones aplicadas: X3 (Contador; el Gerente recibe aviso), H1, H8, H10, H11 y C2 a C5 (decisiones_A0.md).

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Contabilidad.
**Actor principal:** Contador. Si no hay un Contador activo, el Gerente (extensión 1a).
**Versión:** 0.1

**Personal involucrado e intereses**

**Contador:**
- quiere anular un asiento erróneo sin borrarlo, dejando la historia a la vista;
- quiere que el contraasiento sea exacto (los mismos movimientos, invertidos) sin tener que cargarlo a mano.

**Gerente:**
- quiere enterarse de cada contraasiento, porque indica que algo se registró mal;
- quiere poder registrarlo cuando no hay un Contador activo.

**Organización (Jardín Botánico):**
- quiere que lo registrado nunca se borre ni se edite, y que un error quede explicado.

**Relaciones con otros casos de uso**
- No incluye otros casos de uso.
- No es extendido por otros casos de uso.
- **Disparador:** el Contador detecta un asiento erróneo al consultar el libro de gestión.
- **Lo precede:** CON-CNS-LGS · Consultar Libro de Gestión (desde la ficha del asiento se inicia).
- **Relacionado:** CON-REG-ASI · Registrar Asiento Manual al terminar, se ofrece registrar el asiento correcto con ese caso de uso, con datos precargados (C4); siguen siendo dos operaciones separadas.

**Precondiciones**
a. El actor está autenticado con una cuenta activa de Contador o, si no hay un Contador activo, de Gerente.
b. Existe un ejercicio contable «abierto».
c. Existe al menos un asiento que no es contraasiento y que todavía no fue anulado.

**Garantías mínimas**
La operación es atómica. Si se cancela o falla:
- no queda registrado ningún asiento, movimiento ni notificación;
- no cambia el último número del ejercicio;
- el asiento a anular no queda marcado como anulado;
- no se registra ningún log de auditoría parcial.

**Además:**
- Un asiento se anula como máximo una vez y un contraasiento no se anula (R161; regla 17 de 8.20).
- No se modifica ni se elimina el asiento anulado ni sus movimientos.
- El contraasiento no revierte ningún efecto operativo (stock, entregas, cobros): solo la contabilidad.

**Garantías de éxito (Postcondiciones)**
a. Se creó un contraasiento con el número siguiente al último del ejercicio que lo contiene, la fecha indicada y la descripción (motivo). Quedó vinculado al asiento anulado (R161) y sin documento de origen.
b. Se creó, por cada movimiento del asiento anulado, un movimiento del contraasiento con la misma cuenta y el mismo importe, con el Debe y el Haber invertidos.
c. El ejercicio que contiene al contraasiento guardó el nuevo último número.
d. Se notificó al Gerente del contraasiento (con el asiento anulado, el contraasiento, el motivo y quién lo registró), salvo que lo haya registrado él mismo. (X3)
e. Se creó un log de auditoría por el contraasiento, sus movimientos y el vínculo con el asiento anulado, con usuario, rol, fecha, hora, identificador y valores.

**Escenario principal de éxito (Flujo Básico)**
(El Contador anula un asiento erróneo con un contraasiento fechado en el ejercicio abierto.)

1. **El Contador inicia el contraasiento de un asiento, desde su ficha en el libro de gestión (o buscándolo por número).**
2. **El Sistema presenta el asiento a anular (número, fecha, descripción, ejercicio, origen si lo tiene y sus movimientos) y el contraasiento que se generaría, con el Debe y el Haber invertidos. Si el asiento es automático, advierte que el contraasiento corrige el libro de gestión pero no anula la operación que lo originó (C5).**
3. **El Contador indica el motivo del contraasiento y, si quiere, cambia la fecha (por defecto, la fecha actual).**
4. **El Sistema verifica los datos y presenta el resumen: el ejercicio al que irá el contraasiento, los movimientos resultantes y que el asiento anulado quedará marcado como anulado.**
5. **El Contador confirma.**
6. **El Sistema registra el contraasiento:**
   - bloquea el asiento a anular y el ejercicio destino;
   - toma el siguiente número del ejercicio;
   - crea el contraasiento y sus movimientos y lo vincula al asiento anulado;
   - registra la auditoría correspondiente.
7. **El Sistema notifica al Gerente.**
8. **El Sistema informa al Contador que el contraasiento fue registrado, con su número, y le ofrece registrar el asiento correcto con CON-REG-ASI, con los datos precargados (C4).**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 5), el actor cancela:**
1. El Sistema descarta los datos sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa al actor que el contraasiento no fue registrado.
3. El actor reinicia desde el paso 1.

**1a. No hay un Contador activo y el Gerente registra el contraasiento:**
1. El caso de uso continúa en el paso 2 con el Gerente como actor.
2. En el paso 6 el Gerente queda como autor en el log de auditoría.
3. En el paso 7 no se le notifica a sí mismo.
4. Si hay un Contador activo, el Sistema no permite el registro al Gerente.

**1b. El asiento elegido ya está anulado o es un contraasiento:**
1. El Sistema informa que ese asiento no puede anularse (un asiento se anula una sola vez; un contraasiento no se anula) y, si ya está anulado, muestra su contraasiento.
2. El caso de uso termina.

**3a. Falta el motivo:**
1. El Sistema señala que la descripción es obligatoria.
2. El actor la completa (vuelve al paso 3).

**3b. La fecha cae en un ejercicio «en cierre»:**
1. El Sistema acepta el contraasiento: en el ejercicio en cierre entran los contraasientos con fecha dentro de su rango (H1, C3).
2. El resumen del paso 4 lo indica.

**3c. La fecha cae en un ejercicio «cerrado», es anterior al primer ejercicio o es posterior a la fecha actual:**
1. El Sistema rechaza la fecha con un mensaje que explica el motivo (C2).
2. El actor la corrige (vuelve al paso 3).

**8a. El actor acepta registrar el asiento correcto:**
1. Se ejecuta CON-REG-ASI con el formulario precargado (extensión 1b de ese caso de uso). Si no acepta, el caso de uso termina.

**6a. Al registrar, el asiento fue anulado por otro usuario:**
1. El Sistema no registra ningún cambio, informa que el asiento ya tiene contraasiento y muestra cuál.
2. El caso de uso termina.

**6b. Al registrar, el ejercicio cambió de estado y la fecha ya no cae donde estaba:**
1. El Sistema no registra ningún cambio, informa el nuevo estado y vuelve al paso 4.

**7a. No se puede notificar al Gerente (por ejemplo, no hay Gerente activo):**
1. El contraasiento permanece registrado.
2. El Sistema deja constancia en el log de auditoría.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 6 se completa en no más de 3 segundos.
- El registro es una única transacción: contraasiento, movimientos, vínculo, último número y logs se registran juntos o ninguno. La notificación se crea dentro de la transacción (D-42).
- El control de concurrencia impide que dos usuarios anulen el mismo asiento a la vez y que dos asientos tomen el mismo número (se bloquea primero el asiento a anular y después el ejercicio, para respetar el orden de bloqueos de `docs/patrones/bloqueos.md`).
- Los montos se expresan en pesos argentinos con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**
- **Quién registra:** el Contador; si no hay un Contador activo, el Gerente. El Vendedor no. (X3)
- **Qué se anula:** cualquier asiento (manual o automático) que no sea contraasiento y no esté ya anulado. (R161; reglas 15 y 17 de 8.20)
- **Movimientos:** los mismos del asiento anulado, con el Debe y el Haber invertidos; el usuario no los carga. (Regla 17 de 8.20; paso 2)
- **Motivo:** obligatorio; es la descripción del contraasiento. (Regla 16 de 8.20; extensión 3a)
- **Ejercicio y fecha:** la elige el Contador, por defecto hoy, y debe caer en un ejercicio abierto o en cierre; si cae en uno cerrado o es futura, se rechaza. (C2, C3)
- **Numeración:** correlativa por ejercicio, sin huecos. (H8)
- **Aviso al Gerente:** siempre, por cada contraasiento. (X3)
- **Sin efecto operativo (C5, advertido en el paso 2):** anular el asiento de una operación (por ejemplo, de una entrega) no deshace la operación; los casos de uso operativos que corresponda anular (COM-ANL-CBR, COM-ANL-SRV) generan su propio contraasiento.

**Lista de tecnología y variaciones de datos**
- **3.** Motivo: texto libre. Fecha: por defecto la fecha actual.
- **7.** La notificación al Gerente indica asiento anulado, contraasiento, motivo, fecha y usuario.

**Frecuencia**
Muy baja: solo ante errores de carga o correcciones.


---

## Cómo se aplica (código)

Decisiones: **D-84** (puntos 4 a 6 y 9), **D-85**, **D-86**. Modelo: `docs/modelo/contabilidad.md`. Contrato: `docs/api/asientos.md`.
Patrón de bloqueos: `docs/patrones/asientos.md`, sección 2.

### Servicios (`contabilidad/servicios/asientos.py`)

- `registrar_asiento_manual(actor, fecha, descripcion, movimientos) -> AsientoContable` con `movimientos = [(codigo_cuenta, "D"|"H", Decimal)]`.
  **Orden:** (1) permisos: `responsables.puede_registrar_asientos(actor)` (si no, `PermissionDenied`: el mensaje del Gerente con un Contador
  activo dice «Lo registra el Contador»); (2) validar sin bloquear (descripción obligatoria, importes, balance, cuentas existentes, fecha:
  `ejercicio_para(fecha, automatico=False)`); (3) autorrecuperación del ejercicio (H9); (4) verificar que el actor siga activo (D-30);
  (5) **bloquear el ejercicio destino** (`FOR NO KEY UPDATE`), **revalidar** que siga abierto o en cierre y que la fecha siga cayendo en él (si no,
  `ErrorContable` `cambio_simultaneo`, extensión 7b), sumar 1 a `ultimo_numero_asiento`; (6) crear asiento y movimientos; (7) auditar
  `alta_asiento_contable` y un `alta_movimiento_contable` por movimiento (con `referencia(cuenta)`, `tipo_movimiento` e `importe_movimiento` como
  texto).
- `contraasentar(actor, asiento_id, fecha, descripcion) -> AsientoContable`: permisos como arriba; (1) leer el asiento sin bloquear para saber
  qué ejercicio destino bloquear; (2) **bloquear primero el asiento a anular** y verificar que no sea contraasiento ni tenga ya el suyo
  (`asiento_no_anulable`, mensaje con el contraasiento existente si lo hay; extensiones 1b y 6a); (3) bloquear el ejercicio destino; (4) crear el
  contraasiento (`anula = asiento`) con los movimientos invertidos, numerado; (5) auditar; (6) **notificar al Gerente** con
  `notificar_a_varios([gerente], ..., excluir=actor)` dentro de la transacción: título «Contraasiento N.º X del asiento N.º Y», detalle «Lo
  registró <nombre> el dd/mm/aaaa. Motivo: <descripción>» (sin Gerente activo no falla y se deja constancia en la auditoría: `datos`
  `{"aviso_al_gerente": "no enviado: sin Gerente activo"}`, extensión 7a).
- **Fechas (C2, C3):** un asiento manual o un contraasiento con fecha futura, anterior al primer ejercicio o en un ejercicio cerrado: `ErrorContable`
  con códigos `fecha_futura`, `fecha_anterior_al_primer_ejercicio`, `fecha_en_ejercicio_cerrado`, y un mensaje que explica el motivo (el del
  cerrado nombra el ejercicio y su rango).
- **Importes (H11):** una línea de importe 0 se omite *antes* de contar (extensión 5c); menos de dos movimientos restantes → `ErrorContable`
  `faltan_movimientos`; negativo o con más de dos decimales → `importe_invalido`; Debe ≠ Haber → `asiento_desbalanceado`, con la diferencia en
  el mensaje. El servicio recibe los errores **por línea** cuando puede (`campo="movimientos[2].importe"`) para que la pantalla marque la fila.
- **Precarga (C4):** `asientos.datos_para_correccion(actor, asiento_id) -> dict` devuelve las líneas del asiento anulado (las del anulado, no
  las invertidas) y la descripción sugerida «corrección del asiento N.º X» (`CON-REG-ASI`, extensión 1b); el asiento correcto es un asiento
  manual común, **sin vínculo** con el contraasiento.
- **Resumen previo (paso 5 de ambos casos de uso):** `asientos.resumir_asiento_manual(...)` y `resumir_contraasiento(...)` hacen **las mismas
  validaciones** y devuelven el resumen (ejercicio destino y su estado, totales, diferencia, tipo de cada cuenta, o los movimientos invertidos) sin
  escribir ni bloquear. La pantalla lo muestra antes del botón «Confirmar».
- **Apertura y ventas previas (extensiones 3a y 3b de CON-REG-ASI):** no tienen código propio: son un asiento manual común. La pantalla ofrece
  dos atajos de **precarga** («Asiento de apertura» y «Venta de producción previa») que solo completan la descripción y sugieren cuentas
  (Capital Inicial / Proveedores y Caja / Banco c/c; Caja o Banco / Ventas).
- **Quién es «Contador o Gerente sin Contador»:** `responsables.puede_registrar_asientos`. Un Gerente con un Contador activo no puede registrar
  (extensión 1a, punto 3).

### Pruebas (`contabilidad/tests/`)

| Qué | Archivo |
|---|---|
| CON-REG-ASI: cada regla, extensión y postcondición, y los atajos de apertura y venta previa | `test_con_reg_asi.py` |
| CON-CTR-ASI: cada regla, extensión y postcondición, la notificación al Gerente y la auditoría | `test_con_ctr_asi.py` |
| Todo o nada (el asiento falla en medio) y `verificar_invariantes_contables` | en los dos |
| Concurrencia: dos asientos a la vez toman números distintos y sin hueco; dos contraasientos del mismo asiento (uno gana); un asiento contra el cierre del ejercicio; **orden de bloqueos** (asiento a anular antes del ejercicio) | `test_asientos_concurrencia.py` |
| Vistas y plantillas (formulario con filas, resumen, ficha, precarga) | `test_asientos_vistas.py` |

### Pantallas (prototipo: `VIEWS.k_new`, `INIT.k_new`, `ACT.mvadd`, `ACT.mvdel`, `ACT.mvt`, `ACT['asi-ok']`, `VIEWS.k_contra`, `ACT['contra-ok']`)

Formulario de asiento con filas dinámicas (agregar y quitar línea con HTMX; una fila nueva se pide al servidor), el selector de cuenta **con
buscador** (el plan tiene 19 cuentas hoy, pero el criterio del estudiante es «buscadores en lugar de desplegables» para datos que crecen: el plan
puede crecer con el ABM futuro), el resumen y la confirmación en una pantalla separada. **Diferencia a corregir en el prototipo:** el prototipo
limitó la fecha del contraasiento al mismo ejercicio del asiento original («pendiente de confirmar»); el caso de uso dice que se elige la fecha y
cae en un ejercicio **abierto o en cierre** (C3). Manda el caso de uso.

## Solo prototipo

El interruptor «Hay un Contador activo», el selector de rol y «Reiniciar datos de ejemplo».
