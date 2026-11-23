# Casos de uso · comercial · Confirmación de la entrega por el cliente

Copia para el repo de **COM-CNF-ENT · Confirmar Entrega, versión 0.2** (documento de Drive «CU extendidos», consultado el 22/11/2026) y de
**COM-ATN-ENR · Atender Entrega No Reconocida, versión 0.1** (documento «CU · COM-ATN-ENR · Atender Entrega No Reconocida (v0.1)», carpeta
«InfoPonia · Comercial · Análisis», 20/11/2026; caso de uso de alto nivel). Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU
(comercial)» (secciones 2, 4, 14 y 16 los cambian), con el modelo de dominio (reglas 1 a 4 y 12 de 8.14; regla 15 de 8.12; ronda 22) y con
«MD · Cambios para el modelo de dominio (comercial)» (MD-115, MD-122 y MD-137).

**El código va en la app `comercial`** (`comercial/servicios/confirmacion.py` y `comercial/servicios/atencion.py`; las vistas públicas en
`comercial/views_cliente.py`, las del Gerente en `comercial/views_entregas.py`; modelo en `docs/modelo/comercial.md`: «Queja»,
«SolicitudRevision», «EnlaceCliente» y «AlertaComercial»). El enlace sigue `docs/patrones/enlace_del_cliente.md` (D-65). Cómo se guarda y
cómo corre: **D-68**. Tarea: **COM-06b**. La concreción que manda el enlace está en `docs/casos_de_uso/comercial/rutas.md` (COM-06a).
Archivos de pruebas: `comercial/tests/test_com_cnf_ent.py`, `test_com_atn_enr.py`, `test_confirmacion_concurrencia.py` y
`test_confirmacion_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-CNF-ENT no numera sus reglas (`test_regla_tipos_de_queja_…`); postcondiciones `test_post_<letra>_…`;
extensiones `test_ext_<numero>_…` (`test_ext_3a_4b_…`). COM-ATN-ENR numera sus reglas (`test_regla_2_…`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-CNF-ENT | Confirmar Entrega | Cliente del suministro, por el enlace (sin usuario) | `comercial/tests/test_com_cnf_ent.py` |
| COM-ATN-ENR | Atender Entrega No Reconocida (alto nivel) | Gerente | `comercial/tests/test_com_atn_enr.py` |

## COM-CNF-ENT · Confirmar Entrega

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial.

**Versión:** 0.2

**Actor principal:** Cliente del contrato de suministro. Es un actor externo sin usuario en el Sistema: accede mediante el enlace de confirmación que recibió por correo.

**Personal involucrado e intereses**

  - Cliente: quiere dejar constancia de que recibió la entrega y, si no está conforme, reclamar sin tener que llamar a nadie. Quiere ver exactamente lo que se le entregó y lo que se le va a cobrar, y saber si un faltante ya está en revisión.
  - Vendedor: quiere saber qué entregas de sus contratos confirmó el cliente, enterarse en el momento de cada queja y de cada entrega que el cliente no reconoce.
  - Gerente: quiere recibir cada queja con datos suficientes para resolverla, y enterarse de inmediato si un cliente niega haber recibido una entrega.
  - Transportista: quiere que una entrega que realizó quede reconocida por el cliente, y que un reclamo por retraso se evalúe con los intentos fallidos a la vista, para que no se le atribuya si el cliente estuvo ausente.
  - Organización (Jardín Botánico): quiere tener constancia de la recepción de cada entrega de suministro y que solo lleguen al Gerente quejas que la cláusula puede sostener. También quiere que el acceso de un externo no exponga datos internos ni permita modificar nada más que su propia respuesta.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - Lo habilita COM-CNC-ENT · Concretar Entrega, que envía el enlace de confirmación al concretar una entrega de suministro.
  - Las quejas que registra se resuelven con COM-RSV-QJA · Resolver Queja.
  - La discrepancia que se muestra como “en revisión” la resuelve COM-EVL-DSC · Evaluar Discrepancia.

**Precondiciones**

a. El Cliente recibió un enlace de confirmación.

b. La entrega del enlace es de un suministro, está “concretada” y su confirmación del cliente está en “no confirmado”.

**Garantías mínimas**

  - El registro es atómico. Si el Cliente abandona antes de confirmar, o si el caso de uso falla:
  - la entrega sigue en “no confirmado” y el enlace puede volver a usarse mientras esté vigente;
  - no se registra ninguna queja, alerta, notificación ni log de auditoría parcial.
  - El enlace admite un solo envío.
  - El Cliente solo ve y responde sobre la entrega de su enlace. No ve datos internos, como las plantas perdidas en el traslado o los costos.
  - Este caso de uso no modifica el estado de la orden de la entrega, sus montos, su cobro, la contabilidad, el stock ni la cantidad de incumplimientos del contrato.

**Garantías de éxito (Postcondiciones)**

**En toda respuesta registrada**

a. El enlace quedó usado y ya no admite otro envío.

b. Se envió al Cliente por correo un acuse de su respuesta.

c. Se creó un log de auditoría con origen “cliente mediante enlace”, el identificador del cliente y el de la entrega, la fecha, la hora, los cambios de valor de la entrega si se modificó, y el identificador de cada queja y de cada alerta creadas.

**Si el Cliente confirmó la recepción**

d. La confirmación del cliente de la entrega pasó de “no confirmado” a “confirmado”.

**Por cada queja presentada**

e. Se registró una queja con los siguientes datos:
  - estado “pendiente de revisión”;
  - fecha de solicitud igual a la fecha actual;
  - su tipo y su motivo (si se indicó);
  - asociada al Cliente y a los detalles de la entrega que eligió;
  - sin Gerente ni monto de indemnización.

f. Se generó una alerta para el Gerente, asociada a la queja.

g. Se notificó la queja al Vendedor del contrato.

h. El acuse al Cliente incluye el número y el tipo de cada queja.

**Si el Cliente indicó que no recibió la entrega**

i. La confirmación del cliente de la entrega siguió en “no confirmado”.

j. Se generó una alerta para el Gerente de tipo “entrega no reconocida por el cliente”, con la entrega y el motivo indicado. No se registró ninguna queja.

k. Se notificó al Vendedor del contrato que el Cliente no reconoce la entrega, con el motivo.

**Escenario principal de éxito (o Flujo Básico)**

(El Cliente confirma la recepción y no presenta quejas.)
1. El Cliente abre el enlace de confirmación.
2. El Sistema verifica el enlace y presenta la entrega:
  - el contrato y la fecha real de la entrega;
  - por cada detalle: la variedad, la fecha prometida, las cantidades planificada, entregada y devuelta, el precio unitario y el monto;
  - el monto total y el vencimiento del pago.
3. El Cliente indica que recibió la entrega y que no presentará quejas.
4. El Sistema presenta el resumen de la respuesta: confirmación de la recepción, sin quejas. Advierte que el enlace no podrá volver a usarse.
5. El Cliente confirma su respuesta.
6. El Sistema registra la respuesta:
  - pasa la confirmación del cliente de la entrega a “confirmado”;
  - marca el enlace como usado;
  - registra la auditoría correspondiente.
7. El Sistema envía al Cliente el acuse de la confirmación.
8. El Sistema informa al Cliente que la recepción quedó confirmada.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 5, el Cliente abandona la respuesta (por ejemplo, cierra la página):**

1. El Sistema descarta los datos ingresados sin registrar ningún cambio.
2. El enlace puede volver a usarse mientras esté vigente.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1. El Sistema revierte cualquier registro parcial de la operación.
2. Al restablecerse, el Cliente puede volver a abrir el enlace mientras esté vigente. Si la respuesta ya había quedado registrada, se aplica la extensión 2a.

**2a. El enlace no es válido, ya fue usado o venció:**

1. El Sistema informa que el enlace no puede usarse y el motivo (inválido, ya usado o vencido).
2. El Sistema presenta los datos de contacto del Vendedor del contrato, para cualquier reclamo.
3. El caso de uso termina.

**2b. La entrega tiene una discrepancia “pendiente de revisión”:**

1. El Sistema muestra, en cada detalle que figura en la discrepancia, el aviso “La cantidad entregada de este producto está por debajo del mínimo pactado y está siendo revisada”.
2. El caso de uso continúa en el paso 3.

**3a. El Cliente recibió la entrega, pero no está conforme:**

1. El Cliente indica que presentará una o más quejas.
2. El Sistema presenta los tipos de queja disponibles: “estado de la mercadería”, “otro” y, solo si algún detalle tiene días de retraso mayores que cero, “retraso”. No ofrece un tipo que ya se agregó.
3. El Cliente elige un tipo de queja, los detalles de la entrega a los que se refiere y el motivo. En una queja por retraso, el Sistema solo ofrece los detalles con días de retraso mayores que cero, con sus días de retraso.
4. El Sistema verifica la queja y la agrega a la respuesta.
5. El Cliente repite 3a.3 y 3a.4 por cada tipo de queja que quiere presentar.
6. El caso de uso continúa en el paso 4. El resumen incluye la confirmación de la recepción y cada queja con su tipo, sus detalles y su motivo.
7. En el paso 6, el Sistema registra además cada queja, genera su alerta para el Gerente y notifica cada queja al Vendedor del contrato.
8. En el paso 7, el acuse incluye el número y el tipo de cada queja.

**3a.4a. La queja no tiene ningún detalle:**

1. El Sistema señala que debe elegir al menos un detalle.
2. El Cliente elige los detalles (vuelve a 3a.3).

**3a.4b. La queja es de tipo “estado de la mercadería” u “otro” y no tiene motivo:**

1. El Sistema señala que el motivo es obligatorio para ese tipo de queja.
2. El Cliente ingresa el motivo (vuelve a 3a.3).

**3a.5a. El Cliente quiere quitar o modificar una queja ya agregada:**

1. El Cliente indica la queja.
2. El Sistema la quita o la presenta para modificarla (vuelve a 3a.3).

**3a.6a. El Cliente indicó que presentará quejas, pero no agregó ninguna y quiere pasar al resumen:**

1. El Sistema señala que debe agregar al menos una queja o indicar que recibió la entrega y está conforme.
2. El Cliente agrega una queja (vuelve a 3a.3) o indica que está conforme (vuelve al paso 3).

**3b. El Cliente no recibió la entrega:**

1. El Cliente indica que no recibió la entrega e ingresa el motivo.
2. El Sistema presenta el resumen: la entrega no será confirmada y se informará al Gerente y al Vendedor. Advierte que el enlace no podrá volver a usarse.
3. El Cliente confirma su respuesta.
4. El Sistema registra la respuesta:
  - deja la confirmación del cliente de la entrega en “no confirmado”;
  - marca el enlace como usado;
  - genera una alerta para el Gerente de tipo “entrega no reconocida por el cliente”, con el motivo;
  - registra la auditoría correspondiente.
5. El Sistema notifica al Vendedor del contrato y envía al Cliente el acuse de su respuesta.
6. El Sistema informa al Cliente que su respuesta fue registrada y el caso de uso termina.

**3b.1a. El Cliente no ingresa el motivo:**

1. El Sistema señala que el motivo es obligatorio.
2. El Cliente ingresa el motivo (vuelve a 3b.1).

**4a. El Cliente quiere cambiar su respuesta:**

1. El caso de uso vuelve al paso 3. Si el Cliente pasa a “conforme” o a “no recibí la entrega”, el Sistema le pide confirmar el cambio y descarta las quejas agregadas. Las quejas solo se conservan si vuelve a presentar quejas antes de enviar.

**6a. Al registrar, el enlace ya fue usado (por ejemplo, el Cliente envió la respuesta desde otra pestaña) o venció mientras completaba la respuesta:**

1. El Sistema no registra ningún cambio e informa que el enlace ya no puede usarse.
2. El Sistema presenta los datos de contacto del Vendedor del contrato.
3. El caso de uso termina.

**7a. El Sistema no logra enviar el acuse al Cliente o una notificación al Vendedor:**

1. La respuesta permanece registrada.
2. El Sistema reintenta el envío.
3. Si el que falló es el acuse, en el paso 8 el Sistema informa además al Cliente que el acuse todavía no se envió y que puede pedir el reenvío (extensión 8a).

**8a. El Cliente pide reenviar el acuse:**

1. El Sistema reenvía el acuse al correo registrado del cliente.
2. El Sistema informa si el envío se realizó o si falló; si falló, el Cliente puede volver a pedirlo.
3. El caso de uso termina cuando el Cliente sale de la pantalla.

**Requisitos especiales**

  - El enlace se abre desde cualquier navegador web moderno, en celular o en computadora, sin instalación ni inicio de sesión. La pantalla se adapta a pantallas pequeñas.
  - El enlace contiene un identificador no adivinable, que solo da acceso a la entrega para la que se generó.
  - La pantalla del paso 2 se presenta en no más de 2 segundos.
  - El registro del paso 6 (o de 3b.4) se completa en no más de 5 segundos y se ejecuta como una única transacción: la confirmación, las quejas, las alertas, el uso del enlace y los logs se registran juntos o no se registra ninguno.
  - El control de concurrencia impide que un mismo enlace registre dos respuestas.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los montos se expresan en pesos argentinos, con dos decimales.
  - Los logs de auditoría son de solo inserción e indican como origen “cliente mediante enlace”, con el identificador del cliente y el de la entrega.

**Reglas de negocio**

  - Enlace de confirmación: (Pasos 2 y 6, y extensiones 2a y 6a)
  - Se genera uno por cada entrega de suministro concretada (COM-CNC-ENT).
  - Es de uso único: puede abrirse las veces que haga falta, pero admite un solo envío.
  - Vence en la fecha de resolución de la entrega más los días de vigencia del enlace de la configuración operativa. Si se cambia ese parámetro, cambia también la vigencia de los enlaces ya enviados.
  - Significado de la confirmación: confirmar es reconocer que se recibió la entrega, aunque se presenten quejas. No cambia el estado de la orden, ni afecta el cobro ni la cantidad de incumplimientos del contrato. (Paso 6 y extensión 3a)
  - Sin confirmación tácita: si el Cliente no usa el enlace, la entrega queda en “no confirmado”. El Vendedor ve en sus contratos qué entregas siguen sin confirmar. (Paso 6)
  - Información visible: la del comprobante de entrega (variedad, cantidades planificada, entregada y devuelta, precio, monto y vencimiento del pago), la fecha prometida de cada detalle y la fecha real de la entrega. No se muestran las plantas perdidas en el traslado. (Paso 2)
  - Discrepancia en revisión: si un detalle tiene una discrepancia “pendiente de revisión”, se avisa al Cliente que el faltante está siendo revisado. No hay tipo de queja por faltante: un faltante por debajo de la cantidad mínima de mercadería se trata como discrepancia (COM-EVL-DSC · Evaluar Discrepancia), y un faltante que no baja del mínimo no da lugar a reclamo, porque el cliente paga solo lo que recibió y la cláusula tolera esa diferencia. (Extensión 2b)
  - Tipos de queja: “estado de la mercadería”, “retraso” u “otro”. Como máximo una queja por tipo en la respuesta, y cada una con al menos un detalle de la entrega. (Extensión 3a)
  - Queja por retraso: solo se ofrece si algún detalle tiene días de retraso mayores que cero, y solo con esos detalles. Días de retraso de un detalle = fecha de resolución de la entrega − (fecha del período + plazo de entrega de su cláusula). (Extensión 3a)
  - Motivo de la queja: obligatorio en “estado de la mercadería” y en “otro”; opcional en “retraso”, porque el retraso lo calcula el Sistema. (Extensión 3a)
  - Queja registrada: nace “pendiente de revisión”, sin Gerente ni monto de indemnización. El monto se calcula al aceptarla en Resolver Queja. Cada queja genera su alerta para el Gerente y una notificación al Vendedor del contrato. No se registra nada en la bitácora. (Extensión 3a)
  - Entrega no reconocida: (Extensión 3b)
  - el motivo es obligatorio;
  - no se registra ninguna queja;
  - la entrega sigue “no confirmado”;
  - se genera una alerta para el Gerente de tipo “entrega no reconocida por el cliente” y se notifica al Vendedor del contrato.
  - Contrato finalizado o resuelto: el Cliente puede confirmar y presentar quejas igual. Un incumplimiento aceptado se registra como historial, sin disparar la resolución (regla 12 de 8.14). (Paso 6)
  - Reenvío del acuse: el Cliente puede pedirlo desde la pantalla final, las veces que quiera, siempre al correo registrado del cliente; el correo no se puede cambiar desde el enlace. Al salir de esa pantalla no puede volver, porque el enlace ya está usado (extensión 2a). (Extensión 8a)

**Lista de tecnología y variaciones de datos**

  - 1a. El enlace llega en el correo del comprobante de entrega que envía COM-CNC-ENT.
  - 2a. Las fechas se presentan con formato dd/mm/aaaa, las cantidades en plantas y los montos en pesos con dos decimales.
  - 2b. Los datos de contacto del Vendedor son nombre, apellido, teléfono y correo electrónico.
  - 3a. El tipo de queja se elige de la lista de tipos disponibles. El motivo se ingresa como texto libre.
  - 7a. El acuse al Cliente indica la entrega, la fecha y la hora de la respuesta y, según corresponda, la confirmación de la recepción, el número y el tipo de cada queja, o la constancia de que no reconoció la entrega.

**Frecuencia**

Como máximo una respuesta por cada entrega de suministro concretada. Depende de la cantidad de contratos de suministro vigentes y de la frecuencia de sus entregas.

**Temas abiertos**

  - Si el Cliente no reconoce una entrega, la entrega sigue concretada, cobrable y con su venta registrada, y la corrección se hace fuera del Sistema. ¿Hace falta un caso de uso para anular una concreción y revertir asientos, stock y reservas? La alerta “entrega no reconocida por el cliente” que genera este caso de uso hoy no la atiende ningún caso de uso; se resolverá en el caso de uso que anule una concreción.
  - Si el enlace venció o ya se usó, el Cliente solo puede reclamar al Vendedor. ¿Debería el Vendedor poder registrar una queja en nombre del Cliente?
  - ¿Debería el Vendedor poder reenviar el enlace con una vigencia nueva, si el Cliente no recibió el correo o el enlace venció antes de usarlo?


## COM-ATN-ENR · Atender Entrega No Reconocida

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos», sección «Casos de uso de alto nivel».
Reemplaza al caso 27 de PCU. Decisión G del 20/11/2026: opción (a), sin reversión automática; la corrección contable es manual con CU-17; el
reingreso del producto devuelto queda como mejora futura; el resultado de la averiguación sale de una lista (MD-137).

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** averiguar qué pasó con una entrega que el cliente dice no haber recibido y cerrar la alerta.

**Precondición**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. Existe una alerta «entrega no reconocida por el cliente» activa (COM-CNF-ENT).

**Postcondición**

a. La alerta quedó resuelta, con la fecha actual, el resultado de la averiguación y una descripción obligatoria de lo averiguado (MD-137).

b. Si el resultado es «no llegó», se notificó al Gerente y a quien registra los asientos manuales que corresponde corregir con CU-17, y al
Vendedor del contrato.

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la alerta y de la entrega, y el resultado.

**Reglas**

1. Qué ve el Gerente: todo lo que generó la entrega: detalles y cantidades, transportista, vehículo, fecha y hora de concreción, motivos
   registrados, confirmación del cliente, los asientos de la venta y del costo, los consumos de envases y el cobro, si lo hay.
2. Resultado, de una lista cerrada: «la entrega llegó» (el cliente se equivocó; no hay nada que corregir), «no llegó, producto perdido» o
   «no llegó, producto devuelto».
3. Sin reversión automática: este caso de uso no anula la concreción, no toca asientos ni stock y no cuenta incumplimientos. La corrección
   contable se hace a mano con CU-17. Si el producto se perdió: Debe Ventas / Haber Deudores por Ventas para revertir la venta, y Debe
   Pérdidas por Mermas / Haber Costo de Producción Vendida para pasar el costo a pérdida.
4. Producto devuelto: como el producto ya salió del stock al concretarse la entrega, hoy no se puede reingresar a la cámara. Queda como
   mejora futura, junto con la anulación automática de una concreción; mientras tanto, se registra en la descripción.
5. Si la entrega ya se cobró y no llegó, el Gerente primero anula el cobro con COM-ANL-CBR.

## Cambios ya decididos que se aplican

| Fuente | Qué cambia | Dónde |
|---|---|---|
| PCU, sección 2 | COM-CNF-ENT está en la versión 0.2 de «CU extendidos» | Encabezado |
| PCU, sección 4 (caso 27) y sección 14 | El tema abierto de COM-CNF-ENT («la alerta “entrega no reconocida” no la atiende ningún caso de uso») queda cerrado: la atiende COM-ATN-ENR. No hay «ajuste de stock» de producto: la corrección es solo contable | COM-CNF-ENT, «Temas abiertos»; COM-ATN-ENR |
| PCU, sección 16 | Paso 2: además del precio unitario, el monto de cada línea y el total de la entrega (y lo que queda a pagar si hubo indemnizaciones descontadas) | Pantalla del cliente |
| PCU, sección 16 | Los asientos que muestra COM-ATN-ENR (regla 1) quedan «Fuera de esta ronda · contabilidad» | Pantalla del Gerente |
| MD-137 | El resultado de la averiguación y su descripción, en la alerta | `AlertaComercial` (D-68, punto 9) |
| D-68, punto 8 | La vigencia del enlace de confirmación se calcula con el parámetro vigente | «Enlace de confirmación» |

## Cómo se aplica en la ronda «Comercial 1» (COM-06b; D-44, D-57, D-65, D-68)

### Qué entra y qué no

- **Entra:** los dos casos de uso completos; el tipo `confirmacion_entrega` del enlace y **el enlace en el correo de la concreción** de una
  entrega de suministro (postcondición l de COM-CNC-ENT, que COM-06a dejó sin enlace; D-68 punto 1); `Queja`; el resultado de la
  averiguación.
- **No entra:** las entregas de suministro concretadas **antes** de COM-06b no reciben enlace (estado de paso, D-68 punto 1); resolver la
  queja (COM-RSV-QJA, COM-07); el cobro (COM-08a); los asientos que muestra COM-ATN-ENR (D-57); notificar a «quien registra los asientos
  manuales» (postcondición b de COM-ATN-ENR): ese rol es de la ronda de contabilidad; hasta entonces se notifica a los Gerentes activos y al
  Vendedor (`docs/temas_abiertos.md`).

### El enlace de confirmación (regla «Enlace de confirmación»; D-65, D-68 punto 8)

- **Se crea al concretar** una entrega de suministro (COM-06b suma la llamada en `concretar_entrega` de COM-06a), dentro de su transacción,
  después de sus bloqueos: `enlaces.crear_enlace("confirmacion_entrega", cliente, entrega=entrega)` (la función de COM-04c suma el argumento
  `entrega`; `compra_venta` y `vence` quedan para el faltante). Uno por entrega, **sin reemplazo** (la base lo impide). Solo con un cliente
  con correo: sin correo no hay enlace y la entrega queda «no confirmado» (regla «Sin confirmación tácita»); el Vendedor lo ve en la ficha del
  suministro.
- **Un solo correo** (postcondición l): el del comprobante de entrega de COM-06a pasa a ser `enviar_enlace` con la plantilla
  `comercial/correos/confirmacion_entrega` (el comprobante más el enlace y hasta cuándo sirve). El resultado va a `EnlaceCliente.estado_envio`
  y a `Entrega.estado_aviso_cliente`.
- **Si el correo no sale** (15a de COM-CNC-ENT: «el Sistema reintenta el envío»): el token no se guarda (D-65), así que no se puede volver
  a mandar el mismo enlace. El reintento del paso 50 (la parte 4, con las concretadas que suma COM-06a) llama a
  `enlaces.reemitir_enlace(enlace)`: si sigue `vigente` y sin usar, le pone un **token nuevo** en la misma fila (`token_resumen` nuevo; el
  viejo, que nunca llegó, deja de servir) y lo manda con `on_commit`. No es un reemplazo (la fila es la misma; la regla «uno por entrega»
  se cumple). Vencido o usado, no se reintenta.
- **Vigencia:** `entrega.fecha_resolucion_orden + configuracion.obtener().dias_vigencia_enlace_confirmacion`, **calculada** al abrir y al
  registrar (`fecha_vencimiento` nula en este tipo); sirve hasta el final de ese día. `enlace_vigente(token)` (COM-04c) mira el tipo para
  saber de dónde sale la fecha. El paso 27 no toma este tipo: la confirmación no tiene aviso de vencimiento.
- **Abrir** (`/cliente/<token>/`, la misma entrada pública de COM-04c): por el tipo, redirige a `/cliente/enlace/` con la pantalla de
  confirmación. No sirve (2a): «inválido», «ya usado» o «vencido», con los datos de contacto del Vendedor (nombre, apellido, teléfono y
  correo). Las cabeceras y la sesión, como el patrón (secciones 3 y 4).

### Servicios (`comercial/servicios/confirmacion.py`)

| Función | Qué hace |
|---|---|
| `datos_para_el_cliente(enlace) -> DatosDeEntregaParaElCliente` | Paso 2 y 2b. El contrato y la fecha real; por línea: variedad, fecha prometida (`fecha_periodo`), planificada (`entregada + perdida + devuelta`), entregada y devuelta, precio y monto; el total, lo que queda a pagar (`monto_a_cobrar`, PCU 16) y el vencimiento; **nunca** las perdidas ni los costos (garantía mínima); los días de retraso de cada línea; las líneas con discrepancia «pendiente» (2b) |
| `tipos_de_queja_disponibles(datos)` | «estado de la mercadería», «otro» y, si alguna línea tiene días de retraso `> 0`, «retraso» (3a.2) |
| `resumen_de_respuesta(enlace, datos) -> ResumenDeRespuesta` | No escribe. Verifica 3a.4a, 3a.4b, 3a.6a y 3b.1a, y arma el resumen del paso 4 (o 3b.2) |
| `registrar_respuesta(enlace_id, datos) -> Respuesta` | Paso 6 o 3b.4 (abajo) |
| `reenviar_acuse(enlace_id)` | 8a: reenvía el acuse al correo del cliente; devuelve si salió. Solo desde la pantalla final (la sesión guarda que la respuesta se registró) |

- **Días de retraso de una línea** (regla «Queja por retraso»): `fecha_resolucion_orden − (fecha_periodo + plazo_entrega_dias)` de la
  cláusula del suministrante de su detalle; si es negativo, 0.
- **La respuesta** (`DatosDeRespuesta`): `conforme`, `con_quejas` (una lista de quejas, cada una con tipo, ids de líneas y motivo) o
  `no_recibi` (con motivo). A lo sumo una queja por tipo; en la de retraso, solo líneas con retraso; el motivo obligatorio en «estado de la
  mercadería» y en «otro» y en «no recibí» (hasta 500 caracteres, recortado). 4a (cambiar de respuesta) es de la pantalla: el servicio recibe
  solo lo último.

### Registrar la respuesta (paso 6, 3b.4)

- **Bloqueos** (`docs/patrones/bloqueos.md`, «Confirmar una entrega»): la cuenta del Vendedor del contrato (para el aviso) → el
  **invernadero de origen** (`bloquear_invernadero_para_alertas`: activo o no, porque crea alertas; D-64 punto 12) → la **entrega** → el
  **enlace** (`bloquear_enlace`, al final, como dice el patrón, sección 5). Con todo tomado se verifica que siga `vigente` y dentro de la
  vigencia calculada (6a: no registra nada y la pantalla muestra «Este enlace ya no se puede usar» con el contacto del Vendedor) y que la
  entrega siga «concretada» y «no confirmado».
- **Conforme o con quejas:** `estado_confirmacion_cliente = confirmado` (postcondición d; confirmar es reconocer que se recibió, aunque se
  presenten quejas). Por cada queja (postcondiciones e a g): `solicitudes.crear_solicitud` (la de COM-06a) con una `Queja` «pendiente», `fecha_solicitud
  = hoy`, el tipo, el motivo, el cliente y sus líneas; la alerta `comercial_queja` (`GERENTE`, `ADVERTENCIA`, `Clase.EVENTO`, origen
  `SOLICITUD_REVISION`, `crear_alerta_de_evento` del invernadero de origen) con su `AlertaComercial(solicitud=…)`; el aviso al Vendedor
  («OT-0231 · SR-0013: queja por retraso del cliente Verdulería Norte»). Descripción de la alerta: «OT-0231 · SR-0013 · Retraso · 2 productos».
  Enlace de la alerta: la ficha del suministro (como la discrepancia, COM-06a) hasta COM-07.
- **No recibí** (3b.4): la entrega sigue «no confirmado»; la alerta `comercial_entrega_no_reconocida` (`GERENTE`, `CRITICA`, `Clase.EVENTO`,
  origen `ENTREGA`) con su `AlertaComercial(entrega=…)` y el motivo en la descripción («OT-0231 · el cliente dice que no la recibió: “…”»);
  el aviso al Vendedor con el motivo. Ninguna queja. Enlace de la alerta (MAE-02d, `registrar_enlace_de_alerta`): la pantalla de COM-ATN-ENR.
- El enlace pasa a `usado` con `fecha_uso` (postcondición a).
- **Auditoría:** un registro `respuesta_cliente_entrega` sin usuario y con `rol_externo="cliente_enlace"` (D-65 punto 8, como `decision_faltante`
  de COM-DCD-FLT), con el id del cliente en `datos`, la entrega
  (y el cambio de su confirmación si cambió), el enlace, y en `datos` las quejas y las alertas creadas (postcondición c).
- **Acuse** (postcondiciones b y h; 7a): con `transaction.on_commit`, al correo del cliente: la entrega, la fecha y la hora de la respuesta
  y, según el caso, la confirmación, el número (`SR-0013`) y el tipo de cada queja, o la constancia de que no reconoció la entrega. Si
  falla, la pantalla final lo dice y ofrece «Reenviar acuse» (8a).
- **Contrato finalizado o resuelto:** se confirma y se queja igual (regla del caso de uso). No toca el estado de la orden, los montos, el
  cobro, el stock ni los incumplimientos (garantía mínima).

### Atender una entrega no reconocida (COM-ATN-ENR; `comercial/servicios/atencion.py`)

| Función | Qué hace |
|---|---|
| `ficha_de_no_reconocida(actor, alerta_id) -> FichaDeNoReconocida` | Regla 1: la entrega con sus líneas (planificada, entregada, perdida y devuelta), el transportista y su vehículo de hoy, la fecha y la hora de la concreción (del registro `concrecion_entrega`), los intentos fallidos (`intentos_fallidos`, COM-06a), la confirmación del cliente con el motivo, los consumos de envases (por `Consumo.orden`), el cobro (hasta COM-08a, «Sin cobro registrado») y los asientos como «Fuera de esta ronda · contabilidad». Solo el Gerente activo y una alerta de ese tipo, activa |
| `atender_entrega_no_reconocida(actor, alerta_id, resultado, descripcion) -> Alerta` | Bloqueos: las cuentas (el Gerente y el Vendedor) → el invernadero (`bloquear_invernadero_para_alertas`) → la entrega → la `AlertaComercial`. Relee que la alerta siga activa (si no, `alerta_resuelta`). Carga `resultado_averiguacion` (de la lista de la regla 2) y `descripcion_averiguacion` (obligatoria, hasta 500) y resuelve la alerta (`resolver_alerta`). Con «no llegó»: aviso a los Gerentes activos y al Vendedor («OT-0231 no llegó al cliente (producto perdido): corresponde corregir los asientos a mano.»). Regla 3: no toca la entrega, el stock, los asientos ni los incumplimientos. Regla 5: si la entrega tiene un pago vigente (desde COM-08a), rechaza con `entrega_cobrada` («Primero anulá el cobro.»). Auditoría `atencion_entrega_no_reconocida` con la alerta, la entrega y el resultado |

### Lo que completa a otras tareas

| Tarea | Qué |
|---|---|
| COM-06a | La llamada a `crear_enlace` en `concretar_entrega` y el correo con el enlace (postcondición l) |
| COM-04c | `crear_enlace(..., entrega=...)` y `enlace_vigente` por tipo; la pantalla «Este enlace no se puede usar» con los motivos de la confirmación |
| COM-03a | La ficha del suministro: «No confirmada» / «Confirmada» por entrega y las quejas pendientes |
| COM-01 | La baja del cliente informa sus quejas pendientes (regla 1 de COM-BAJ-CLT) |

## Pantallas

Referencia visual (D-61): `docs/prototipos/comercial/` (`README.md`).

| Pantalla | Funciones del prototipo | Qué tiene |
|---|---|---|
| Portal del cliente · Confirmar Entrega (`/cliente/enlace/`) | `VIEWS.portal`, `INIT.cnf`, `VIEWS.cnf` (línea 1742), `qErr` | La entrega (paso 2), «Recibí y estoy conforme», «Recibí pero tengo quejas» (con los tipos, las líneas y el motivo), «No recibí la entrega»; el resumen; la pantalla final con «Reenviar acuse» |
| Atender entrega no reconocida (`/comercial/entregas/<id>/no-reconocida/`) | `INIT.atnenr`, `VIEWS.atnenr` (línea 1814) | Todo lo de la regla 1 y el formulario del resultado. Solo el Gerente |

- La página del cliente usa la plantilla base propia de `/cliente/` (sin menú ni campana; COM-04c) y se adapta al celular. Sin JavaScript,
  cada paso es una página (agregar una queja, el resumen).
- Vistas que solo orquestan, `never_cache`; las públicas con las tres cabeceras del patrón; las del Gerente con `rol_requerido`.

### Lo que difiere del prototipo (corregir, D-61)

| Pantalla | Prototipo | Caso de uso (manda) |
|---|---|---|
| Confirmar Entrega | El precio unitario se deduce del monto (`e.monto / sumEn`) | Paso 2: el precio de cada línea es el guardado (recalculado al concretar), con su monto, el total y lo que queda a pagar (PCU 16) |
| Confirmar Entrega | La pantalla final no ofrece reenviar el acuse | 7a.3 y 8a: «Reenviar acuse» |
| Atender entrega no reconocida | Muestra los asientos con datos de ejemplo | Regla 1: «Fuera de esta ronda · contabilidad» en su lugar (ya lo marca la sobrescritura de la línea 1814) |

## Pruebas

- `test_com_cnf_ent.py` (`ComCnfEntServicioTests`): una por postcondición (a a k) y extensión (2a con sus tres motivos, 2b, 3a con 3a.4a,
  3a.4b, 3a.5a y 3a.6a, 3b con 3b.1a, 4a en el servicio, 6a, 7a, 8a); cada regla (los tipos disponibles con y sin retraso, una por tipo, el
  retraso solo con sus líneas, el contrato finalizado); la vigencia calculada (cambiar el parámetro cambia la de un enlace ya creado; el
  último día sirve y el siguiente no); el cliente no ve perdidas ni costos (el texto no está en la respuesta); la concreción de un suministro
  crea el enlace y manda un solo correo; un cliente sin correo no tiene enlace.
- `test_com_atn_enr.py` (`ComAtnEnrServicioTests`): una por regla (1 a 5) y postcondición (a a c); solo el Gerente; la alerta ya resuelta.
- `test_confirmacion_concurrencia.py` (`@tag("concurrencia")`): dos respuestas del mismo enlace a la vez (una sola); la respuesta contra
  atender la no reconocida de la misma entrega.
- `test_confirmacion_vistas.py`: las cabeceras de `/cliente/`; la sesión de un enlace no abre otra entrega; el flujo completo con HTMX y sin
  JavaScript; permisos de la pantalla del Gerente (los demás roles, 403).
- Invariantes: `verificar_invariantes_de_solicitudes()` después de cada prueba que registra una queja.

## Para más adelante

- **COM-07:** COM-RSV-QJA resuelve las quejas (con los intentos fallidos a la vista) y COM-EVL-DSC la discrepancia; el correo al cliente
  cuando se rechaza una discrepancia (regla 15 de 8.14).
- **COM-08a:** el cobro que muestra COM-ATN-ENR (regla 1) y su regla 5 con datos reales (`cobranza.md`, «Lo que completa a otras tareas»).
- **Ronda de contabilidad:** el aviso a quien registra los asientos manuales (COM-ATN-ENR, postcondición b); los asientos de la regla 1.
- Temas abiertos de COM-CNF-ENT: que el Vendedor registre una queja en nombre del cliente; reenviar el enlace con una vigencia nueva.
- Mejoras futuras: anular una concreción y reingresar el producto devuelto (COM-ATN-ENR, regla 4).
