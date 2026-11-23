# Casos de uso · comercial · Solicitudes de revisión

Copia para el repo de **COM-EVL-DSC · Evaluar Discrepancia, versión 0.2** (documento de Drive «CU extendidos», consultado el 22/11/2026), de
**COM-RSV-QJA · Resolver Queja, versión 0.2**, de **COM-ANL-SRV · Anular Resolución de Solicitud, versión 0.1** (documentos «CU · COM-RSV-QJA ·
Resolver Queja (v0.2)» y «CU · COM-ANL-SRV · Anular Resolución de Solicitud (v0.1)», carpeta «InfoPonia · Comercial · Análisis»; iguales a sus
copias de «CU extendidos») y de **COM-CNS-SRV · Consultar Solicitudes de Revisión, versión 0.1** (alto nivel, de «CU · Consultas comerciales ·
COM-CNS-CVT/SUM/SRV (v0.1)»). Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU (comercial)», con el modelo de dominio
(reglas 1 a 15 de 8.14; ronda 22) y con «MD · Cambios para el modelo de dominio (comercial)» (MD-114, MD-115, MD-117 y MD-135).

**El código va en la app `comercial`** (`comercial/servicios/solicitudes.py`, que ya tiene `crear_solicitud` de COM-06a;
`comercial/servicios/indemnizaciones.py`, funciones puras; `comercial/servicios/resoluciones.py`, el disparo de COM-RSV-SUM; las vistas en
`comercial/views_solicitudes.py`; modelo en `docs/modelo/comercial.md`: «SolicitudRevision», «DiscrepanciaEntrega y LineaDiscrepancia»,
«Queja», «Anulacion» y «AlertaComercial»). Cómo se guarda y cómo corre: **D-69**. Tarea: **COM-07a**. La resolución del contrato que
disparan las aceptaciones está en `docs/casos_de_uso/comercial/resolucion.md` (COM-RSV-SUM, COM-07b). Archivos de pruebas:
`comercial/tests/test_com_evl_dsc.py`, `test_com_rsv_qja.py`, `test_com_anl_srv.py`, `test_com_cns_srv.py`, `test_indemnizaciones.py`,
`test_solicitudes_concurrencia.py` y `test_solicitudes_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-EVL-DSC y COM-RSV-QJA no numeran sus reglas (`test_regla_tope_del_monto_manual_…`); postcondiciones
`test_post_<letra>_…`; extensiones `test_ext_<numero>_…` (`test_ext_4a_3a_…`). COM-ANL-SRV no numera sus reglas; COM-CNS-SRV sí
(`test_regla_3_…`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-EVL-DSC | Evaluar Discrepancia | Gerente | `comercial/tests/test_com_evl_dsc.py` |
| COM-RSV-QJA | Resolver Queja | Gerente | `comercial/tests/test_com_rsv_qja.py` |
| COM-ANL-SRV | Anular Resolución de Solicitud | Gerente | `comercial/tests/test_com_anl_srv.py` |
| COM-CNS-SRV | Consultar Solicitudes de Revisión (alto nivel) | Vendedor o Gerente | `comercial/tests/test_com_cns_srv.py` |

## COM-EVL-DSC · Evaluar Discrepancia

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial.

**Versión:** 0.2

**Actor principal:** Gerente.

**Personal involucrado e intereses**

  - Gerente: quiere decidir si una entrega por debajo del mínimo fue un incumplimiento de la empresa, con todos los datos de la entrega a la vista. No quiere calcular a mano la indemnización ni el efecto sobre el contrato.
  - Cliente: quiere que lo compensen según la cláusula cuando recibió menos del mínimo por causa de la empresa, saber si la indemnización se le descontó o se le reintegró, y saber si se le reconoció la discrepancia de su entrega, se acepte o se rechace.
  - Vendedor: quiere conocer la decisión sobre las discrepancias de sus contratos y cobrar el monto correcto de cada entrega.
  - Organización (Jardín Botánico): quiere varias cosas:
  - indemnizar solo lo que la cláusula prevé;
  - que la contabilidad refleje la indemnización cuando se reconoce (base devengado);
  - que el contador de incumplimientos refleje solo las fallas de la empresa, porque de él depende la resolución del contrato.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - La discrepancia que evalúa la genera COM-CNC-ENT · Concretar Entrega (extensión 14c), junto con una alerta para el Gerente.
  - Si con la aceptación la cantidad de incumplimientos supera la tolerada y el contrato está vigente, InfoPonia ejecuta COM-RSV-SUM · Resolver Suministro por Incumplimientos.
  - Registrar Cobro de Suministro cobra el monto a cobrar de la entrega, que descuenta las indemnizaciones aceptadas antes del pago.

**Precondiciones**

a. El Gerente está autenticado en el Sistema.

b. Existe al menos una discrepancia de entrega en estado “pendiente de revisión”.

c. Existe un ejercicio contable vigente y existen las cuentas contables Indemnizaciones por Incumplimiento a Cliente, Deudores por Ventas, Caja y Banco c/c.

**Garantías mínimas**

  - La evaluación es atómica. Si el caso de uso se cancela o falla, la discrepancia sigue “pendiente de revisión”, sin Gerente asociado, y su alerta sigue sin resolver. No se registra ningún cambio en el contrato, la contabilidad, la bitácora ni el log de auditoría.
  - Una discrepancia se resuelve una única vez y origina como máximo un asiento contable.
  - El monto de la indemnización es el que surge de las cláusulas de sus líneas y nadie lo modifica.
  - La cantidad de incumplimientos del contrato solo aumenta al aceptar una discrepancia, y aumenta de a uno.
  - Solo un Gerente resuelve una discrepancia.

**Garantías de éxito (Postcondiciones)**

**En toda discrepancia evaluada**

a. La discrepancia pasó de “pendiente de revisión” a “aceptada” o “rechazada”. Quedó con la fecha de resolución igual a la fecha actual, asociada al Gerente que la resolvió y con sus observaciones, si se indicaron.

b. La alerta de la discrepancia quedó resuelta, con la fecha de resolución igual a la fecha actual.

**Si la discrepancia fue aceptada**

c. Quedó registrado el monto de la indemnización: la suma, por cada línea de la discrepancia, de (cantidad mínima estipulada − cantidad entregada) × indemnización por mercadería de la cláusula del suministrante de su detalle.

d. La cantidad de incumplimientos del contrato aumentó en uno, una sola vez, aunque la discrepancia tenga varias líneas.

e. Se generó un asiento contable por el monto de la indemnización, originado en la discrepancia, en el libro diario del ejercicio vigente:

  - Entrega sin pagar: Debe Indemnizaciones por Incumplimiento a Cliente / Haber Deudores por Ventas. El monto a cobrar de la entrega bajó en el monto de la indemnización.
  - Entrega ya pagada: Debe Indemnizaciones por Incumplimiento a Cliente / Haber Caja o Banco c/c, según el medio de reintegro.

f. Se registró en la bitácora del invernadero de origen de la entrega un evento de tipo “incumplimiento de cláusula suministrante”:

  - con la fecha y hora actuales;
  - sin lote, etapa productiva ni Capataz;
  - con una descripción que indica el Transportista responsable (o que fue un retiro en invernadero) y la entrega; por cada línea, el detalle, la cantidad entregada, la cantidad mínima estipulada y su monto; y el monto total de la indemnización.

g. Se envió al cliente por correo el comprobante de indemnización (uso interno) y se notificó al Vendedor del contrato.

h. Si el contrato estaba vigente y la cantidad de incumplimientos superó la tolerada, se disparó COM-RSV-SUM · Resolver Suministro por Incumplimientos.

**Si la discrepancia fue rechazada**

i. No cambió la cantidad de incumplimientos del contrato. No se registró monto de indemnización, asiento contable ni evento de bitácora. Se notificó al Vendedor del contrato la decisión y sus observaciones, y se envió al cliente un aviso de que la discrepancia no fue reconocida, con las observaciones del Gerente.

**Auditoría**

j. Se creó un log de auditoría por cada discrepancia, alerta y contrato modificados, con usuario, rol, fecha, hora, identificador y cambios de valor.

k. Se creó un log de auditoría por cada asiento contable y registro de bitácora creados, con usuario, rol, fecha, hora e identificador.

**Escenario principal de éxito (o Flujo Básico)**

(Aceptación de una discrepancia de una entrega sin pagar, con el contrato vigente y sin superar la cantidad de incumplimientos tolerados.)

1. El Gerente inicia la evaluación de discrepancias.
2. El Sistema presenta las discrepancias “pendiente de revisión”, de la más antigua a la más reciente, con una fila por discrepancia (es decir, por entrega). Para cada una indica el identificador de la discrepancia, la fecha de la solicitud, el cliente, el contrato, la fecha de la entrega y la cantidad de líneas por debajo del mínimo.
3. El Gerente selecciona una discrepancia.
4. El Sistema presenta la información para decidir:
  - el cliente y el contrato;
  - la fecha prometida y la fecha real de la entrega, y el Transportista que la realizó (o que fue un retiro en invernadero);
  - una tabla con una fila por cada línea por debajo del mínimo: el detalle de suministro (variedad y dirección), la cantidad mínima estipulada, las cantidades planificada, entregada, perdida y devuelta (lo que llegó en buen estado y el cliente no recibió), la indemnización por planta faltante de su cláusula y el monto de la línea; debajo, el monto total de la indemnización;
  - la causa y la descripción de las pérdidas;
  - cómo se aplicaría el monto total de la indemnización;
  - los incumplimientos registrados en el contrato, los tolerados y si una aceptación provocaría la resolución del contrato y la multa por resolución que se aplicaría.
5. El Gerente indica que hubo incumplimiento de la empresa y, si lo desea, una observación.
6. El Sistema presenta un resumen con:
  - la decisión;
  - el monto de la indemnización;
  - que se descontará de lo que el cliente debe por la entrega, y el nuevo monto a cobrar;
  - la cantidad de incumplimientos que quedará en el contrato, frente a los tolerados.
7. El Gerente confirma la evaluación.
8. El Sistema registra la discrepancia como aceptada:
  - registra la fecha de resolución, el Gerente, la observación y el monto de la indemnización;
  - suma un incumplimiento al contrato;
  - registra el asiento de la indemnización y el evento de bitácora;
  - resuelve la alerta de la discrepancia;
  - registra la auditoría correspondiente.
9. El Sistema envía al cliente el comprobante de indemnización (uso interno) y notifica la decisión al Vendedor del contrato.
10. El Sistema informa al Gerente que la discrepancia fue aceptada y presenta el monto de la indemnización, el nuevo monto a cobrar de la entrega (o, en la extensión 6a, el reintegro y su medio) y el asiento generado.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 7, el Gerente cancela la evaluación:**

1. El Sistema descarta los datos ingresados sin registrar ningún cambio. La discrepancia sigue “pendiente de revisión”.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1. El Sistema revierte cualquier registro parcial de la operación.
2. Al restablecerse, el Sistema informa al Gerente que la discrepancia no fue evaluada.
3. El Gerente reinicia el caso de uso desde el paso 1.

**1a. El Gerente inicia la evaluación desde la alerta de la discrepancia:**

1. El Sistema presenta directamente la discrepancia de la alerta.
2. El caso de uso continúa en el paso 4.

**1a1. La discrepancia de la alerta ya no está “pendiente de revisión” (por ejemplo, el Gerente ya la resolvió desde otra sesión):**

1. El Sistema informa la decisión tomada, el Gerente que la tomó y la fecha de resolución.
2. El caso de uso termina.

**3a. La discrepancia seleccionada ya no está “pendiente de revisión” (por ejemplo, el Gerente ya la resolvió desde otra sesión):**

1. El Sistema informa la decisión tomada, el Gerente que la tomó y la fecha de resolución.
2. El caso de uso vuelve al paso 2.

**5a. El Gerente considera que no hubo incumplimiento de la empresa:**

1. El Gerente indica que rechaza la discrepancia e ingresa las observaciones.
2. El Sistema presenta un resumen: sin indemnización y sin cambios en la cantidad de incumplimientos del contrato.
3. El Gerente confirma la evaluación.
4. El Sistema registra la discrepancia como rechazada:
  - registra la fecha de resolución, el Gerente y las observaciones;
  - resuelve la alerta de la discrepancia;
  - registra la auditoría correspondiente.
5. El Sistema notifica al Vendedor del contrato la decisión y las observaciones, y envía al cliente un aviso de que la discrepancia no fue reconocida, con las observaciones del Gerente.
6. El Sistema informa al Gerente que la discrepancia fue rechazada y el caso de uso termina.

**5b. El Gerente rechaza la discrepancia sin ingresar observaciones:**

1. El Sistema señala que las observaciones son obligatorias al rechazar.
2. El Gerente ingresa las observaciones (vuelve a 5a.1).

**6a. La entrega ya está pagada:**

1. El Sistema informa que la indemnización se reintegrará al cliente.
2. El Gerente indica el medio de reintegro.
3. El caso de uso continúa en el paso 6, con tres diferencias:
  - el resumen indica el reintegro y su medio;
  - en el paso 8, el asiento se registra contra Caja o Banco c/c;
  - en el paso 9, el comprobante indica que el monto se reintegró.

**6b. Con esta aceptación, la cantidad de incumplimientos supera la tolerada y el contrato está vigente:**

1. El Sistema repite en el resumen la advertencia de que la aceptación provocará la resolución del contrato por incumplimientos, con la multa por resolución. Confirmar no exige una confirmación adicional.
2. El Gerente confirma la evaluación (continúa en el paso 7) o cambia su decisión (vuelve al paso 5).
3. Una vez registrada la aceptación en el paso 8, InfoPonia ejecuta COM-RSV-SUM · Resolver Suministro por Incumplimientos, fuera de la transacción de esta evaluación.

**6c. El contrato ya está “finalizado” o “resuelto”:**

1. El Sistema informa que el incumplimiento se registra como historial y no provoca la resolución del contrato.
2. El caso de uso continúa en el paso 7.

**7a. El Gerente quiere cambiar su decisión o la observación:**

1. El caso de uso vuelve al paso 5.

**8a. Al registrar, la discrepancia ya no está “pendiente de revisión” (por ejemplo, el Gerente ya la resolvió desde otra sesión):**

1. El Sistema no registra ningún cambio e informa la decisión tomada, el Gerente que la tomó y la fecha de resolución.
2. El caso de uso termina.

**8b. Al registrar, cambió el estado de pago de la entrega o la cantidad de incumplimientos del contrato (por un cobro, o por otra discrepancia o queja aceptada mientras tanto):**

1. El Sistema no registra ningún cambio e informa qué dato cambió.
2. El caso de uso vuelve al paso 4, con los datos actualizados.

**9a. El Sistema no logra enviar el correo al cliente o la notificación al Vendedor:**

1. La evaluación permanece registrada.
2. El Sistema reintenta el envío.

**Requisitos especiales**

  - La interfaz del Gerente está pensada para computadora.
  - La información del paso 4 se presenta en no más de 2 segundos desde la selección.
  - El registro del paso 8 se completa en no más de 5 segundos.
  - El paso 8 se ejecuta como una única transacción. La resolución del contrato (COM-RSV-SUM) se ejecuta fuera de ella.
  - El control de concurrencia cumple tres funciones:
  - impide que una discrepancia se resuelva dos veces;
  - impide que dos aceptaciones simultáneas sobre el mismo contrato (discrepancias o quejas) pierdan un incumplimiento;
  - impide que la entrega se cobre mientras se registra la aceptación.
  - Solo los usuarios con rol Gerente acceden a este caso de uso.
  - La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los montos se expresan en pesos argentinos, con dos decimales.
  - El comprobante de indemnización es de uso interno y no tiene validez fiscal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

  - Discrepancia evaluable: la que está en estado “pendiente de revisión”. (Pasos 2 y 3)
  - Una discrepancia por entrega: abarca todas las líneas de la entrega que quedaron por debajo de su cantidad mínima; su monto es la suma de los montos de esas líneas, y al aceptarse suma un solo incumplimiento (regla 19 de 8.20; reglas 3, 6 y 11 de 8.14). (Pasos 2, 4 y 8)
  - Estados de una solicitud de revisión: “pendiente de revisión”, “aceptada” o “rechazada”. Aceptada significa que hubo incumplimiento de la empresa; en una queja, que es procedente. Una solicitud tiene Gerente asociado si y solo si está resuelta. (Paso 8 y extensión 5a)
  - Origen de la discrepancia: se genera aunque la diferencia venga de un rechazo del cliente. El Gerente decide si hubo incumplimiento de la empresa. (Paso 4)
  - Observaciones: obligatorias al rechazar, opcionales al aceptar. (Paso 5 y extensiones 5a y 5b)
  - Decisión total: el Gerente acepta o rechaza. No ajusta el monto ni acepta en parte. (Paso 5)
  - Monto de la indemnización: (cantidad mínima estipulada − cantidad entregada) × indemnización por mercadería de la cláusula del suministrante del detalle. Se calcula y se guarda al aceptar, y no cambia aunque cambie después la cláusula. Las cantidades son las que la discrepancia registró al generarse. Por ejemplo, con un mínimo de 80, 70 entregadas y $50 por planta: 10 × $50 = $500. (Pasos 4 y 8)
  - Aplicación de la indemnización: no existe saldo a favor del cliente. (Paso 6 y extensión 6a)
  - Si la entrega no está pagada, se descuenta de lo que el cliente debe por esa entrega. Monto a cobrar = monto total de la entrega − Σ montos de las solicitudes aceptadas de sus detalles antes del pago.
  - Si la entrega está pagada, se reintegra al cliente. El reintegro se considera hecho al aceptar.
  - Asiento de la indemnización: uno solo por discrepancia, originado en ella. (Paso 8)
  - Cantidad de incumplimientos: suma uno por cada solicitud aceptada, no por detalle. Una solicitud rechazada no suma. (Paso 8)
  - Resolución del contrato: se produce cuando la cantidad de incumplimientos supera la tolerada. Por ejemplo, con 3 tolerados, el contrato se resuelve con el cuarto incumplimiento. Solo se dispara si el contrato está vigente, y la ejecuta InfoPonia en COM-RSV-SUM. Si el contrato está finalizado o resuelto, el incumplimiento y la indemnización se registran igual, como historial, sin resolución. (Extensiones 6b y 6c)
  - Bitácora: solo al aceptar, en la bitácora del invernadero de origen de la entrega, sin lote, etapa ni Capataz. El evento es de tipo “incumplimiento de cláusula suministrante”. (Paso 8)
  - Avisos: (Pasos 8 y 9, y extensión 5a)
  - Al aceptar, el cliente recibe el comprobante de indemnización y el Vendedor del contrato, una notificación.
  - Al rechazar, se notifica al Vendedor del contrato y se envía al cliente un aviso de que la discrepancia no fue reconocida, con las observaciones del Gerente.
  - La alerta del Gerente queda resuelta con cualquiera de las dos decisiones.

**Lista de tecnología y variaciones de datos**

  - 4a. Las cantidades se expresan en plantas, como números enteros, y los montos en pesos.
  - 5a. Las observaciones son texto libre.
  - 6a. El medio de reintegro se elige de la lista: efectivo (Caja) o transferencia (Banco c/c).
  - 9a. El comprobante de indemnización incluye:
  - la entrega y su fecha;
  - la variedad del detalle;
  - la cantidad entregada y la cantidad mínima estipulada;
  - la indemnización por planta y el monto total;
  - si el monto se descontó de lo que se debe por la entrega o se reintegró, y en ese caso con qué medio.
  - Aclara que es de uso interno, sin validez fiscal.

**Frecuencia**

Ocasional. Una vez por cada discrepancia generada. Depende de cuántas entregas de suministro queden por debajo del mínimo.

**Temas abiertos**

  - No hay plazo para evaluar una discrepancia. Mientras esté pendiente, el cliente paga el total de la entrega, y si se acepta después, la indemnización se reintegra. ¿Debería recordársele al Gerente una discrepancia que sigue pendiente después de cierta cantidad de días, o antes del vencimiento del pago?
  - El reintegro se considera hecho al aceptar. ¿Quién lo ejecuta físicamente, y hay que avisarle?
  - Una decisión no puede revisarse. ¿Hace falta una forma de anularla ante un error, con contraasiento y corrección del contador?
  - ________________


## COM-RSV-QJA · Resolver Queja

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial.

**Versión:** 0.2

**Actor principal:** Gerente.

**Personal involucrado e intereses**

  - Gerente: quiere decidir si una queja del cliente es procedente, con todos los datos de la entrega a la vista: días de retraso, intentos fallidos y lo que se entregó. No quiere calcular a mano la indemnización ni el efecto sobre el contrato y, en una queja sin indemnización de cláusula, quiere poder compensar al cliente con un monto acotado.
  - Cliente: quiere que su queja se evalúe, que lo compensen cuando corresponde y que le informen el resultado, sea cual sea.
  - Vendedor: quiere conocer la decisión sobre las quejas de sus contratos y cobrar el monto correcto de cada entrega.
  - Transportista: quiere que un retraso causado por la ausencia del cliente no se cuente como incumplimiento de la empresa.
  - Organización (Jardín Botánico): quiere tres cosas:
  - indemnizar lo que la cláusula prevé y, en una queja sin cláusula, no más de lo que el cliente pagó por los detalles de la queja;
  - que la contabilidad refleje la indemnización cuando se reconoce (base devengado);
  - que el contador de incumplimientos refleje solo las fallas de la empresa, porque de él depende la resolución del contrato.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - Las quejas que resuelve las presenta el Cliente en COM-CNF-ENT · Confirmar Entrega. Cada queja genera una alerta para el Gerente.
  - Si con la aceptación la cantidad de incumplimientos supera la tolerada y el contrato está vigente, InfoPonia ejecuta COM-RSV-SUM · Resolver Suministro por Incumplimientos.
  - COM-REG-CBR · Registrar Cobro de Suministro cobra el monto a cobrar de la entrega. Ese monto ya descuenta las indemnizaciones aceptadas antes del pago.
  - Lo sigue, si hubo un error: Anular Resolución de Solicitud (por especificar), que devuelve la queja a «pendiente de revisión» para volver a resolverla con este caso de uso.

**Precondiciones**

a. El Gerente está autenticado en el Sistema.

b. Existe al menos una queja en estado «pendiente de revisión».

c. Existe un ejercicio contable vigente y existen las cuentas contables Indemnizaciones por Incumplimiento a Cliente, Deudores por Ventas, Caja y Banco c/c.

**Garantías mínimas**

  - La resolución es atómica. Si el caso de uso se cancela o falla:
  - la queja sigue «pendiente de revisión», sin Gerente asociado, y su alerta sigue sin resolver;
  - no se registra ningún cambio en el contrato, la contabilidad, la bitácora ni el log de auditoría.
  - Una queja se resuelve una única vez y origina como máximo un asiento contable.
  - En una queja por retraso, el monto de la indemnización es el que surge de la cláusula, y nadie lo modifica. En una queja por estado de la mercadería u otro, es el que carga el Gerente, y nunca supera el tope de la regla «Tope del monto manual».
  - El monto a cobrar de una entrega nunca queda negativo: no hay saldo a favor del cliente.
  - La cantidad de incumplimientos del contrato solo aumenta al aceptar una queja, y aumenta de a uno por queja, sin importar cuántos detalles incluya.
  - Solo un Gerente resuelve una queja.

**Garantías de éxito (Postcondiciones)**

**En toda queja resuelta**

a. La queja pasó de «pendiente de revisión» a «aceptada» o «rechazada». Quedó con la fecha de resolución igual a la fecha actual, asociada al Gerente que la resolvió y con sus observaciones, si se indicaron.

b. La alerta de la queja quedó resuelta, con la fecha de resolución igual a la fecha actual.

**Si la queja fue aceptada**

c. La queja quedó con su monto de indemnización:

  - Retraso: la suma, por cada detalle de la queja, de (fecha de resolución de la entrega − (fecha del período + plazo de entrega de su cláusula)) × indemnización por retraso de esa cláusula. Solo se suman los detalles con días de retraso mayores que cero.
  - Estado de la mercadería u otro: el monto que cargó el Gerente, o cero si no cargó ninguno.

d. La cantidad de incumplimientos del contrato aumentó en uno.

e. Si el monto de la indemnización es mayor que cero, se generó un asiento contable por ese monto, originado en la queja, en el libro diario del ejercicio vigente:

  - Entrega sin pagar, con monto a cobrar igual o mayor que la indemnización: Debe Indemnizaciones por Incumplimiento a Cliente / Haber Deudores por Ventas. El monto a cobrar de la entrega bajó en el monto de la indemnización.
  - Entrega sin pagar, con monto a cobrar menor que la indemnización: Debe Indemnizaciones por Incumplimiento a Cliente, por el total / Haber Deudores por Ventas, por el monto a cobrar / Haber Caja o Banco c/c, por el resto, según el medio de reintegro. El monto a cobrar de la entrega quedó en cero.
  - Entrega ya pagada: Debe Indemnizaciones por Incumplimiento a Cliente / Haber Caja o Banco c/c, según el medio de reintegro.

f. Se registró en la bitácora del invernadero de origen de la entrega un evento de tipo «incumplimiento de cláusula suministrante». El evento:

  - tiene la fecha y la hora actuales;
  - no tiene lote, etapa productiva ni Capataz;
  - incluye una descripción con el Transportista responsable (o que fue un retiro en invernadero), la entrega, los detalles, el tipo de queja, los días de retraso si corresponde y el monto de la indemnización.

g. Se envió al Cliente por correo:

  - con indemnización: el comprobante de indemnización (uso interno), que indica cuánto se descontó y cuánto se reintegró;
  - sin indemnización: un aviso de que la queja fue aceptada.

Se notificó al Vendedor del contrato.

h. Si el contrato estaba vigente y la cantidad de incumplimientos superó la tolerada, se disparó COM-RSV-SUM · Resolver Suministro por Incumplimientos.

**Si la queja fue rechazada**

i. No cambió la cantidad de incumplimientos del contrato. No se registró monto de indemnización, asiento contable ni evento de bitácora.

j. Se envió al Cliente por correo un aviso de que la queja no fue reconocida, con las observaciones del Gerente, y se notificó la decisión al Vendedor del contrato.

**Auditoría**

k. Se creó un log de auditoría por cada queja, alerta y contrato modificados. Registra el usuario, el rol, la fecha, la hora, el identificador y los cambios de valor.

l. Se creó un log de auditoría por cada asiento contable y registro de bitácora creados. Registra el usuario, el rol, la fecha, la hora y el identificador.

**Escenario principal de éxito (o Flujo Básico)**

(Aceptación de una queja por retraso de una entrega sin pagar, con el contrato vigente, sin superar la cantidad de incumplimientos tolerados y con una indemnización menor o igual que el monto a cobrar.)

1. El Gerente inicia la resolución de quejas.
2. El Sistema presenta las quejas «pendiente de revisión», de la más antigua a la más reciente. Para cada una indica la fecha de la solicitud, el cliente, el contrato, el tipo de queja, la fecha de la entrega y la cantidad de detalles.
3. El Gerente selecciona una queja.
4. El Sistema presenta la información para decidir:
  - el cliente, el contrato, el tipo de queja y su motivo;
  - la fecha real de la entrega y el Transportista que la realizó (o que fue un retiro en invernadero);
  - los intentos fallidos de entrega registrados, con su fecha y su motivo;
  - por cada detalle de la queja: la variedad, la fecha del período, el plazo de entrega de su cláusula, los días de retraso, la indemnización por día de retraso y las cantidades planificada, entregada, perdida y devuelta;
  - el monto de indemnización que correspondería, el monto a cobrar actual de la entrega y cómo se aplicaría;
  - los incumplimientos registrados en el contrato, los tolerados y si una aceptación provocaría la resolución del contrato.
5. El Gerente indica que la queja es procedente y, si lo desea, una observación.
6. El Sistema presenta el resumen:
  - la decisión;
  - el monto de la indemnización;
  - que se descontará de lo que el cliente debe por la entrega, y el nuevo monto a cobrar;
  - la cantidad de incumplimientos que quedará en el contrato, frente a los tolerados.
7. El Gerente confirma la resolución.
8. El Sistema registra la queja como aceptada:
  - registra la fecha de resolución, el Gerente, la observación y el monto de la indemnización;
  - suma un incumplimiento al contrato;
  - registra el asiento de la indemnización y el evento de bitácora;
  - resuelve la alerta de la queja;
  - registra la auditoría correspondiente.
9. El Sistema envía al Cliente el comprobante de indemnización (uso interno) y notifica la decisión al Vendedor del contrato.
10. El Sistema informa al Gerente que la queja fue aceptada y presenta el monto de la indemnización, el nuevo monto a cobrar de la entrega y el asiento generado.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 7, el Gerente cancela la resolución:**

1. El Sistema descarta los datos ingresados sin registrar ningún cambio. La queja sigue «pendiente de revisión».

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1. El Sistema revierte cualquier registro parcial de la operación.
2. Al restablecerse, el Sistema informa al Gerente que la queja no fue resuelta.
3. El Gerente reinicia el caso de uso desde el paso 1.

**1a. El Gerente inicia la resolución desde la alerta de la queja:**

1. El Sistema presenta directamente la queja de la alerta.
2. El caso de uso continúa en el paso 4.

**1a1. La queja de la alerta ya no está «pendiente de revisión»:**

1. El Sistema informa la decisión tomada, el Gerente que la tomó y la fecha de resolución.
2. El caso de uso termina.

**4a. La queja es de tipo «estado de la mercadería» u «otro»:**

1. El Sistema informa que este tipo de queja no tiene indemnización de cláusula y que, si la acepta, puede cargar un monto de indemnización. Presenta el tope del monto: lo que el cliente paga por los detalles de la queja.
2. En el paso 4 no se presentan días de retraso ni indemnizaciones por día.
3. En el paso 5, el Gerente indica que la queja es procedente y, si lo desea, el monto de la indemnización y una observación.
4. Si el Gerente no carga un monto, o carga cero:
  - en el paso 6, el resumen no incluye monto ni cambios en lo que el cliente debe;
  - en el paso 8, el monto de la indemnización queda en cero y no se registra asiento;
  - en el paso 9, el Cliente recibe un aviso de que la queja fue aceptada, sin comprobante de indemnización.
5. Si el Gerente carga un monto mayor que cero, el caso de uso continúa en el paso 6 igual que una queja por retraso, con ese monto (y con las extensiones 6a y 6d cuando correspondan).

**4a.3a. El monto cargado no es válido: es negativo, tiene más de dos decimales o supera el tope:**

1. El Sistema señala el error e informa el tope.
2. El Gerente corrige el monto (vuelve a 4a.3).

**4b. La queja es por retraso y la entrega tiene un intento fallido dentro del plazo de algún detalle de la queja:**

1. El Sistema destaca el intento fallido y recuerda el criterio: si el retraso se debe a la ausencia del cliente, no es de la empresa.
2. El caso de uso continúa en el paso 5. Decide el Gerente.

**5a. El Gerente considera que la queja no es procedente:**

1. El Gerente indica que rechaza la queja e ingresa las observaciones.
2. El Sistema presenta un resumen: sin indemnización y sin cambios en la cantidad de incumplimientos del contrato.
3. El Gerente confirma la resolución.
4. El Sistema registra la queja como rechazada:
  - registra la fecha de resolución, el Gerente y las observaciones;
  - resuelve la alerta de la queja;
  - registra la auditoría correspondiente.
5. El Sistema envía al Cliente un aviso de que la queja no fue reconocida, con las observaciones, y notifica la decisión al Vendedor del contrato.
6. El Sistema informa al Gerente que la queja fue rechazada y el caso de uso termina.

**5b. El Gerente rechaza la queja sin ingresar observaciones:**

1. El Sistema señala que las observaciones son obligatorias al rechazar.
2. El Gerente ingresa las observaciones (vuelve a 5a.1).

**6a. La queja tiene indemnización y la entrega ya está pagada:**

1. El Sistema informa que la indemnización se reintegrará al cliente.
2. El Gerente indica el medio de reintegro.
3. El caso de uso continúa en el paso 6, con estas diferencias:
  - el resumen indica el reintegro y su medio;
  - en el paso 8, el asiento se registra contra Caja o Banco c/c;
  - en el paso 9, el comprobante indica que el monto se reintegró.

**6b. Con esta aceptación, la cantidad de incumplimientos supera la tolerada y el contrato está vigente:**

1. El Sistema advierte que la aceptación provocará la resolución del contrato por incumplimientos e informa la multa por resolución.
2. El Gerente confirma la resolución (continúa en el paso 7) o cambia su decisión (vuelve al paso 5).
3. Una vez registrada la aceptación en el paso 8, InfoPonia ejecuta COM-RSV-SUM · Resolver Suministro por Incumplimientos, fuera de la transacción de esta resolución.

**6c. El contrato ya está «finalizado» o «resuelto»:**

1. El Sistema informa que el incumplimiento se registra como historial y no provoca la resolución del contrato.
2. El caso de uso continúa en el paso 7.

**6d. La entrega no está pagada y la indemnización supera su monto a cobrar:**

1. El Sistema informa que se descontará el monto a cobrar completo, que la entrega quedará con monto a cobrar cero y que el resto se reintegrará al cliente.
2. El Gerente indica el medio de reintegro del resto.
3. El caso de uso continúa en el paso 6, con estas diferencias:
  - el resumen indica cuánto se descuenta, cuánto se reintegra y con qué medio;
  - en el paso 8, el asiento registra el descuento contra Deudores por Ventas y el resto contra Caja o Banco c/c;
  - en el paso 9, el comprobante indica las dos partes.

**7a. El Gerente quiere cambiar su decisión, el monto cargado o la observación:**

1. El caso de uso vuelve al paso 5 (o a 4a.3, si la queja es de tipo «estado de la mercadería» u «otro»).

**8a. Al registrar, la queja ya no está «pendiente de revisión» (por ejemplo, el Gerente ya la resolvió desde otra sesión):**

1. El Sistema no registra ningún cambio e informa la decisión tomada, el Gerente que la tomó y la fecha de resolución.
2. El caso de uso termina.

**8b. Al registrar, cambió el estado de pago de la entrega, su monto a cobrar o la cantidad de incumplimientos del contrato (por un cobro, o por otra discrepancia o queja aceptada mientras tanto):**

1. El Sistema no registra ningún cambio e informa qué dato cambió.
2. El caso de uso vuelve al paso 4, con los datos actualizados.

**9a. El Sistema no logra enviar el correo al Cliente o la notificación al Vendedor:**

1. La resolución permanece registrada.
2. El Sistema reintenta el envío.

**Requisitos especiales**

  - La interfaz del Gerente está pensada para computadora.
  - La información del paso 4 se presenta en no más de 2 segundos desde la selección.
  - El registro del paso 8 se completa en no más de 5 segundos.
  - El paso 8 se ejecuta como una única transacción. La resolución del contrato (COM-RSV-SUM) se ejecuta fuera de ella.
  - El control de concurrencia impide tres situaciones:
  - que una queja se resuelva dos veces;
  - que dos aceptaciones simultáneas sobre el mismo contrato (discrepancias o quejas) pierdan un incumplimiento o dejen negativo el monto a cobrar de una entrega;
  - que la entrega se cobre mientras se registra la aceptación.
  - Solo los usuarios con rol Gerente acceden a este caso de uso.
  - La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los montos se expresan en pesos argentinos, con dos decimales.
  - El comprobante de indemnización es de uso interno y no tiene validez fiscal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

  - Queja resoluble: la que está en estado «pendiente de revisión». (Pasos 2 y 3)
  - Estados de una solicitud de revisión: «pendiente de revisión», «aceptada» o «rechazada». En una queja, «aceptada» significa que es procedente. Una solicitud tiene Gerente asociado si y solo si está resuelta. (Paso 8 y extensión 5a)
  - Observaciones: obligatorias al rechazar, opcionales al aceptar. (Paso 5 y extensiones 5a y 5b)
  - Decisión sobre la queja completa: el Gerente acepta o rechaza la queja con todos sus detalles. No acepta detalles sueltos ni ajusta el monto de una cláusula; solo en una queja sin indemnización de cláusula carga un monto (regla 2 de 8.14). (Paso 5 y extensión 4a)
  - Monto de la indemnización: se calcula o se carga, y se guarda, al aceptar, y no cambia aunque cambie después la cláusula. (Pasos 4 y 8, y extensión 4a)
  - Retraso: por cada detalle, días de retraso = fecha de resolución de la entrega − (fecha del período + plazo de entrega); si son más de cero, se multiplican por la indemnización por retraso de su cláusula. El monto es la suma de todos los detalles. Ejemplo: período del 10/11, 2 días de tolerancia, entrega el 15/11, lechuga a $1.000 y rúcula a $500 por día: 3 × $1.000 + 3 × $500 = $4.500.
  - Estado de la mercadería u otro: no tienen indemnización de cláusula. El monto es el que carga el Gerente al aceptar, o cero si no carga ninguno (regla 8 de 8.14; MD-14).
  - Tope del monto manual: el monto que carga el Gerente es igual o mayor que cero, con dos decimales, y no supera lo que el cliente paga por los detalles de la queja: la suma, por cada detalle de entrega de la queja, de la cantidad entregada × el precio unitario. Ejemplo: una queja sobre la lechuga de una entrega con 70 plantas a $1.200 tiene un tope de $84.000. Compensar más de lo vendido ya no es una indemnización por la mercadería y se negocia fuera del Sistema. (Extensión 4a; precisión de la regla 8 de 8.14, a registrar en pendientes_MD)
  - Intento fallido: si hubo un intento fallido de entrega dentro del plazo por ausencia del cliente, el retraso no es de la empresa y la queja se rechaza. El Sistema no lo descarta solo, porque el intento queda registrado en la auditoría y en las notificaciones: lo evalúa el Gerente. (Paso 4 y extensión 4b)
  - Aplicación de la indemnización: no existe saldo a favor del cliente (regla 9 de 8.14). (Paso 6 y extensiones 6a y 6d)
  - Si la entrega no está pagada, la indemnización se descuenta de lo que el cliente debe por esa entrega, como máximo hasta su monto a cobrar. Lo que exceda el monto a cobrar se reintegra al cliente con el medio que indique el Gerente. Monto a cobrar = monto total de la entrega − Σ montos descontados por las solicitudes aceptadas de sus detalles antes del pago; nunca es negativo.
  - Si la entrega está pagada, se reintegra al cliente, y el reintegro se considera hecho al aceptar.
  - Asiento de la indemnización: uno solo por queja, originado en ella, y solo si el monto es mayor que cero. Si hay descuento y reintegro, el asiento es compuesto. (Paso 8 y extensiones 4a, 6a y 6d)
  - Cantidad de incumplimientos: suma uno por cada queja aceptada, tenga o no indemnización y sin importar cuántos detalles incluya. Una queja rechazada no suma. (Paso 8)
  - Resolución del contrato: se produce cuando la cantidad de incumplimientos supera la tolerada: con 3 tolerados, se resuelve con el cuarto incumplimiento. Solo se dispara si el contrato está vigente, y la ejecuta InfoPonia en COM-RSV-SUM. Si el contrato está finalizado o resuelto, el incumplimiento y la indemnización se registran igual, como historial, sin resolución. (Extensiones 6b y 6c)
  - Bitácora: solo al aceptar, en la bitácora del invernadero de origen de la entrega, sin lote, etapa ni Capataz. El evento es de tipo «incumplimiento de cláusula suministrante». (Paso 8)
  - Avisos: la alerta del Gerente queda resuelta con cualquiera de las decisiones. (Paso 9 y extensiones 4a y 5a)
  - Al aceptar con indemnización, el Cliente recibe el comprobante de indemnización.
  - Al aceptar sin indemnización, el Cliente recibe un aviso de aceptación.
  - Al rechazar, el Cliente recibe un aviso de rechazo con las observaciones.
  - En todos los casos se notifica al Vendedor del contrato.

**Lista de tecnología y variaciones de datos**

- 4a. Las cantidades se expresan en plantas, como números enteros; los días de retraso, en días corridos; y los montos, en pesos.
- 4b. El monto que carga el Gerente se expresa en pesos argentinos, con dos decimales.
- 5a. Las observaciones son texto libre.
- 6a. El medio de reintegro se elige de la lista: efectivo (Caja) o transferencia (Banco c/c).
- 9a. El comprobante de indemnización incluye:

  - la entrega y su fecha;
  - los detalles con su variedad y, si la queja es por retraso, sus días de retraso y la indemnización por día;
  - el monto total;
  - cuánto se descontó de lo que se debe por la entrega y cuánto se reintegró, y en ese caso con qué medio.

Aclara que es de uso interno, sin validez fiscal.
- 9b. Los avisos de aceptación sin indemnización y de rechazo indican el número y el tipo de la queja, la entrega, la decisión y las observaciones del Gerente.

**Frecuencia:** ocasional. Una vez por cada queja presentada. Depende de cuántas quejas presenten los clientes al confirmar sus entregas.

**Temas abiertos**

  - No hay plazo para resolver una queja. Mientras esté pendiente, el cliente paga el total de la entrega, y si la queja se acepta después, la indemnización se reintegra. ¿Debería recordársele al Gerente una queja que sigue pendiente después de cierta cantidad de días, o antes del vencimiento del pago?
  - El reintegro se considera hecho al aceptar. ¿Quién lo ejecuta físicamente, y hay que avisarle?
  - Los intentos fallidos de entrega no son un concepto del modelo: el Sistema los obtiene de la auditoría y de las notificaciones. Si el criterio de la regla 7 de 8.14 se vuelve central, ¿conviene modelarlos?


## COM-ANL-SRV · Anular Resolución de Solicitud

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Reemplaza al caso 28 de PCU. Decisiones del 20/11/2026 aplicadas: la reversión la origina una Anulación (A; MD-135); contraasiento con las mismas cuentas e importes invertidos y fecha actual (B); bloqueo si la indemnización ya se pagó (F1); una solicitud rechazada también se puede anular (F2).

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial / Solicitudes.

**Versión:** 0.1

**Actor principal:** Gerente.

**Personal involucrado e intereses**

  - Gerente: quiere corregir una resolución equivocada sin borrar la historia.
  - Cliente: quiere que su solicitud se vuelva a evaluar bien.
  - Vendedor: quiere enterarse de que cambió el monto a cobrar o el cumplimiento de su contrato.
  - Organización: quiere que cada corrección contable quede con su motivo y su vínculo con lo que corrige.

**Relaciones con otros casos de uso**

  - Lo preceden: COM-EVL-DSC · Evaluar Discrepancia y COM-RSV-QJA · Resolver Queja.
  - Lo siguen: esos mismos casos de uso, para volver a resolver.
  - Relacionado: COM-CNS-SRV, desde donde el Gerente lo inicia.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Gerente.

b. Existe una discrepancia o una queja resuelta (aceptada o rechazada).

**Garantías mínimas**

  - La anulación es atómica: si falla, la solicitud, el contador, los asientos y el monto a cobrar quedan como estaban.
  - No se anula una resolución que provocó la resolución del contrato, que ya se cobró con el descuento o cuya indemnización ya se pagó.
  - El asiento original no se borra ni se modifica.

**Garantías de éxito (Postcondiciones)**

a. La solicitud volvió a «pendiente de revisión».

b. Se creó una Anulación con la fecha actual, el motivo obligatorio, el usuario y la solicitud anulada (MD-135).

c. Si la solicitud estaba aceptada: la Anulación originó el contraasiento de la indemnización (mismas cuentas e importes, Debe y Haber invertidos, fecha actual); el contador de incumplimientos del suministro bajó en 1, si la solicitud había contado como incumplimiento; y el monto a cobrar de la entrega volvió a su valor sin la indemnización.

d. Se registró un evento de bitácora en la solicitud.

e. Se notificó al Vendedor del contrato.

f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la solicitud y de la Anulación, el motivo y los valores anteriores y nuevos.

**Escenario principal de éxito (o Flujo Básico)**

(Una discrepancia aceptada, que contó como incumplimiento, con la entrega sin cobrar.)

1. El Gerente abre una solicitud resuelta desde COM-CNS-SRV e inicia la anulación.
2. El Sistema presenta la resolución vigente y qué va a pasar: el estado nuevo, el contraasiento, el contador de incumplimientos antes y después y el monto a cobrar antes y después.
3. El Gerente escribe el motivo.
4. El Gerente confirma.
5. El Sistema vuelve a verificar los bloqueos. Luego, en una única transacción, registra la Anulación, su contraasiento, el estado, el contador, la bitácora y la auditoría.
6. El Sistema notifica al Vendedor.
7. El Sistema informa que la solicitud está pendiente de revisión y ofrece volver a resolverla (COM-EVL-DSC o COM-RSV-QJA).

**Extensiones (o Flujos Alternativos)**

**\*a. Antes del paso 4, el Gerente cancela:**

1. No se registra nada.

**\*b. El Sistema falla:**

1. El Sistema revierte cualquier registro parcial.

**2a. La aceptación provocó la resolución del contrato (COM-RSV-SUM):**

1. El Sistema informa que no se puede anular y el caso de uso termina.

**2b. La entrega ya se cobró con el descuento:**

1. El Sistema informa que primero hay que anular el cobro (COM-ANL-CBR) y el caso de uso termina.

**2c. La indemnización ya se le pagó al cliente (queja con indemnización en dinero, MD-123):**

1. El Sistema informa que no se puede anular y el caso de uso termina.

**2d. La solicitud estaba rechazada:**

1. El Sistema informa que vuelve a «pendiente» sin contraasiento y sin tocar el contador, y continúa en el paso 3.

**3a. El motivo está vacío:**

1. El Sistema lo pide.

**5a. Al registrar, otra operación cambió la solicitud, cobró la entrega o resolvió el contrato:**

1. El Sistema no registra ningún cambio, informa la situación actual y vuelve al paso 2.

**Requisitos especiales**

  - El paso 5 es una única transacción, serializada con COM-REG-CBR, COM-RSV-SUM y la resolución de solicitudes del mismo contrato.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción.

**Reglas de negocio**

  - Quién anula: solo el Gerente, con motivo obligatorio.
  - Bloqueos: no se anula si la aceptación provocó la resolución del contrato, si la entrega ya se cobró con el descuento o si la indemnización ya se pagó. (Extensiones 2a a 2c)
  - Contraasiento: lo origina la Anulación (MD-135), con las mismas cuentas e importes, Debe y Haber invertidos y la fecha actual. Si el ejercicio del asiento original está cerrado, va al ejercicio vigente.
  - Contador: baja en 1 solo si la solicitud anulada había contado como incumplimiento.
  - Solicitud rechazada: vuelve a «pendiente» sin contraasiento ni cambio en el contador.
  - Después: la solicitud se vuelve a resolver con su caso de uso, con todas sus reglas, incluidos los topes de MD-114 y MD-115.

**Frecuencia:** rara.


## COM-CNS-SRV · Consultar Solicitudes de Revisión

Caso de uso de alto nivel (versión 0.1, de «CU · Consultas comerciales»).

**Actores:** Vendedor o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver las quejas y discrepancias de los contratos y cómo se resolvieron.

**Precondición**

a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

**Postcondición**

a. Ninguna: es una consulta.

**Reglas**

1. Alcance: el Vendedor ve las solicitudes de los contratos de los que es Vendedor, pendientes y resueltas, en modo lectura y sin acciones de evaluar ni resolver; el Gerente, todas.
2. Filtros: tipo (queja o discrepancia), estado (pendiente o resuelta), cliente, contrato, rango de fechas y, solo para el Gerente, Vendedor.
3. Ficha: la entrega y el detalle afectados; las cantidades pactada, entregada y reclamada; el motivo y la descripción del cliente; el monto de la indemnización (calculado o manual, con su tope, MD-114); si cuenta como incumplimiento; y el estado de pago de la entrega.
4. Pendiente: el Vendedor ve un aviso de que la evalúa o resuelve el Gerente (COM-EVL-DSC o COM-RSV-QJA).
5. Resuelta: además, la decisión, el Gerente que la tomó, la fecha de resolución y las observaciones; si hubo descuento, cómo quedó el monto a cobrar (MD-115).
6. El Vendedor y el Gerente abren la ficha directamente desde la notificación de la solicitud.
7. Si la solicitud está pendiente, el Gerente puede ir desde la ficha a COM-EVL-DSC o COM-RSV-QJA.

## Cambios ya decididos que se aplican

| Fuente | Qué cambia | Dónde |
|---|---|---|
| MD-115; **D-69, punto 2** | COM-EVL-DSC aplica el tope del descuento como la extensión 6d de COM-RSV-QJA: en una entrega sin pagar, se descuenta hasta el monto a cobrar y el resto se reintegra con el medio que indique el Gerente. El monto a cobrar nunca queda negativo. La versión 0.2 no lo tiene (MD-115: «COM-EVL-DSC (próxima versión)»); va a pendientes_CU | COM-EVL-DSC, pasos 6, 8 y 10, y regla «Aplicación de la indemnización» |
| MD-114 | El tope del monto manual de una queja sin cláusula: Σ `cant_entregada × precio_unitario` de los detalles de entrega de la queja | COM-RSV-QJA, 4a y regla «Tope del monto manual» (ya en la v0.2) |
| MD-117 | Un solo Gerente activo resuelve las solicitudes («el Gerente ya la resolvió desde otra sesión») | Los tres casos de uso (ya en sus versiones) |
| MD-135; **D-69, punto 10** | La anulación es una `Anulacion` (hija de `OrigenDocumento`), con una copia de la resolución anulada | COM-ANL-SRV |
| **D-69, punto 4** | La alerta de una solicitud anulada no se reabre ni se crea otra | COM-ANL-SRV (el caso de uso no lo dice) |
| **D-69, punto 5** | 2a: `Suministro.solicitud_resolucion`; 2c: `monto_reintegrado > 0`; «contó como incumplimiento» = estaba aceptada | COM-ANL-SRV |
| **D-69, punto 6** | La bitácora de la anulación va en el invernadero de origen de la entrega, con el tipo `anulacion_de_resolucion`, solo si la solicitud estaba aceptada | COM-ANL-SRV, postcondición d |
| D-68, punto 6 | Los intentos fallidos se leen de `IntentoFallido` (`concrecion.intentos_fallidos`), no de la auditoría | COM-RSV-QJA, paso 4, 4b y regla «Intento fallido» |
| **D-69, punto 16** | Las notificaciones no tienen enlace (D-42): el aviso nombra la solicitud y la pestaña la busca por número | COM-CNS-SRV, regla 6 |
| D-57; **D-69, punto 8** | Fuera de esta ronda · contabilidad: la precondición c de COM-EVL-DSC y de COM-RSV-QJA, sus postcondiciones e (el asiento) y lo que muestran del asiento (paso 10), y el contraasiento de COM-ANL-SRV (postcondición c) | Los tres casos de uso |

## Cómo se aplica en la ronda «Comercial 1» (COM-07a; D-44, D-57, D-68, D-69)

### Qué entra y qué no

- **Entra:** los cuatro casos de uso completos, sin los asientos; `Anulacion` con la solicitud; la aplicación de la indemnización (descuento
  y reintegro, D-69 punto 9); el contador de incumplimientos; los eventos de bitácora (con la función que deja COM-04a, `docs/api/produccion.md`,
  sección 11); el comprobante de indemnización y los avisos al cliente; la pestaña, la ficha, el grupo «Solicitudes» del panel del Gerente y
  la sección «Solicitudes de revisión» de la ficha del suministro; el enlace de las alertas de discrepancia y de queja a la ficha de la
  solicitud.
- **COM-07b:** COM-RSV-SUM (lo que dispara la extensión 6b de los dos casos de uso: COM-07a llama a `resoluciones.resolver_si_corresponde`,
  que hasta COM-07b no hace nada, D-69 punto 13) y la extensión 2a de COM-ANL-SRV con datos reales (el campo y la verificación los deja
  COM-07a; los carga COM-07b).
- **COM-08a** (lote C8; D-94, punto 1): una entrega de suministro «pagada» (6a de COM-EVL-DSC y de COM-RSV-QJA; el cobro de sus 8b; 2b de COM-ANL-SRV). Se escriben con
  `entregas.estado_de_pago` (que hasta COM-08a nunca devuelve «pagada») y se prueban con una fábrica que simula la entrega pagada con
  `mock.patch`; COM-08a las prueba con datos reales (`cobranza.md`, «Lo que completa a otras tareas»). `Anulacion.pago` y
  `cliente_pago_en_fecha` (COM-ANL-CBR): **COM-08b**.
- **Fuera de esta ronda · contabilidad** (D-57): precondición c, asientos, contraasiento. El código guarda todo lo que esos asientos necesitan
  (el monto, lo descontado, lo reintegrado y el medio) y no crea asientos.

### Servicios

| Función | Caso de uso | Qué hace |
|---|---|---|
| `solicitudes.lista_de_solicitudes(actor, filtros, pagina) -> PaginaDeSolicitudes` | COM-CNS-SRV, reglas 1 y 2; paso 2 de COM-EVL-DSC y de COM-RSV-QJA | Lectura. Ver «La lista» |
| `solicitudes.ficha_de_solicitud(actor, solicitud_id) -> FichaDeSolicitud` | COM-CNS-SRV, reglas 3 a 5 y 7; paso 4 de COM-EVL-DSC y de COM-RSV-QJA (con 4a y 4b) | Lectura. Ver «La ficha» |
| `solicitudes.resumen_de_resolucion(actor, solicitud_id, datos) -> ResumenDeResolucion` | Paso 6 (y 5a.2, 4a.3a, 5b, 6a a 6d) | No escribe. Valida `datos`, calcula el monto y su aplicación, arma el resumen y la **huella** (D-69, punto 12) |
| `solicitudes.resolver_solicitud(actor, solicitud_id, datos, huella) -> SolicitudRevision` | Paso 8 y 5a.4 de los dos casos de uso | Ver «Registrar la resolución». `evaluar_discrepancia` y `resolver_queja` son dos nombres finos que verifican el tipo y la llaman |
| `solicitudes.datos_de_anulacion(actor, solicitud_id) -> DatosDeAnulacion` | COM-ANL-SRV, paso 2 (y 2a a 2d) | Lectura: la resolución vigente, los bloqueos, el estado nuevo, el contador y el monto a cobrar antes y después, y la huella |
| `solicitudes.anular_resolucion(actor, solicitud_id, motivo, huella) -> Anulacion` | COM-ANL-SRV, paso 5 | Ver «Anular una resolución» |
| `solicitudes.reenviar_aviso(actor, solicitud_id) -> bool` | 9a de COM-EVL-DSC y de COM-RSV-QJA | Vuelve a mandar el comprobante o el aviso al cliente; devuelve si salió |
| `indemnizaciones.*` (puras, sin base) | Reglas «Monto de la indemnización», «Retraso», «Tope del monto manual» y «Aplicación de la indemnización» | Ver «Cálculos» |
| `resoluciones.resolver_si_corresponde(suministro_id) -> None` | Disparador 1 de COM-RSV-SUM | **Se completa en COM-07b.** En COM-07a no hace nada (docstring y comentario «Se completa en COM-07b») |

Todas las de escritura reciben al actor, verifican que sea el **Gerente activo** después de bloquear (MD-117; `sin_permiso`) y lanzan
`ErrorComercial(codigo, mensaje, campo=None)`. Códigos nuevos: `solicitud_no_pendiente` (1a1, 3a, 8a), `solicitud_no_resuelta`,
`solicitud_cambio` (8b, 5a de COM-ANL-SRV; con lo que cambió), `decision_obligatoria`, `observaciones_obligatorias` (5b), `observaciones_largas`,
`monto_invalido` (4a.3a; con el tope), `monto_no_admitido` (un monto cargado en una queja por retraso o en una discrepancia),
`medio_obligatorio` (6a, 6d), `resolucion_del_contrato` (2a), `entrega_cobrada` (2b), `indemnizacion_reintegrada` (2c),
`motivo_obligatorio`, `motivo_largo` (COM-ANL-SRV); y los comunes `cambio_simultaneo` y `sin_permiso`.

### Cálculos (`comercial/servicios/indemnizaciones.py`, funciones puras con pruebas de tabla)

- **Discrepancia** (regla «Monto de la indemnización» de COM-EVL-DSC): por cada `LineaDiscrepancia`, `(cantidad_minima_estipulada −
  cantidad_entregada) × indemnizacion_faltante` de la cláusula del suministrante del detalle de su `DetalleEntrega`; el total es la suma. Las
  cantidades son las copiadas al generarse (COM-06a); la indemnización por planta es la de la cláusula **al aceptar**, y el monto de cada
  línea y el total se guardan (`monto_indemnizacion_linea`, `monto_indemnizacion`): no cambian si después cambia la cláusula. Ejemplo de la
  regla: mínimo 80, 70 entregadas, $50 por planta → $500,00.
- **Queja por retraso** (regla «Retraso»): por cada detalle de la queja, `dias_de_retraso(linea)` (la regla de COM-06b, `confirmacion.md`,
  «Servicios»: `fecha_resolucion_orden − (fecha_periodo + plazo_entrega_dias)`, 0 si es negativo; si COM-06b la dejó dentro de otra función,
  sacala a `indemnizaciones.dias_de_retraso` sin cambiar sus pruebas) × `indemnizacion_retraso_entrega` de su cláusula; se
  suman los de días > 0. Se guarda solo el total (`monto_indemnizacion`); el detalle por línea va en el comprobante y en la bitácora.
  Ejemplo de la regla: 3 × $1.000 + 3 × $500 = $4.500,00.
- **Queja por estado de la mercadería u otro** (4a y regla «Tope del monto manual», MD-114): el monto que carga el Gerente, de 0 al
  **tope** = Σ `monto_pagar` (`cant_entregada × precio_unitario`) de los `DetalleEntrega` de la queja, con dos decimales; vacío = 0.
  `monto_invalido` si es negativo, tiene más de dos decimales o supera el tope (el mensaje dice el tope). Ejemplo de la regla: 70 × $1.200 =
  $84.000,00.
- **Aplicación** (regla «Aplicación de la indemnización», MD-115, D-69 puntos 2 y 9): `aplicacion(monto, monto_a_cobrar, pagada) ->
  (descontado, reintegrado)`. Pagada: `(0, monto)`. Sin pagar: `descontado = mín(monto, monto_a_cobrar)`, `reintegrado = monto − descontado`.
  Con monto 0: `(0, 0)`. Siempre `descontado + reintegrado = monto`.
- Todo en `Decimal`, `ROUND_HALF_UP` a dos decimales, y nunca con `float`.

### Monto a cobrar (D-69, punto 9; corrige la nota de D-68, punto 7)

`entregas.monto_a_cobrar(entrega_ids)` (COM-06a) pasa a restar **lo descontado**: `monto_total_entrega − Σ monto_descontado` de las
solicitudes `aceptada` de la entrega. Una consulta para todas las entregas. Nunca da negativo (lo garantiza la aplicación; un invariante
nuevo en `verificar_invariantes_de_solicitudes` lo prueba). Las pruebas de COM-06a no cambian: hasta COM-07a no había aceptadas.

### La lista (COM-CNS-SRV, reglas 1 y 2; paso 2)

- **Alcance:** el Gerente, todas; el Vendedor, las de los contratos de los que es Vendedor (`Contrato.objects.en_alcance_de(actor)`, D-28),
  en lectura. Los demás roles, 403 con mensaje.
- **Filtros** (en la URL, con el desplegable propio y el buscador de clientes de COM-02): tipo (todas / quejas / discrepancias), estado
  (pendientes / resueltas / aceptadas / rechazadas; las dos últimas son «resuelta» separada, como el prototipo), cliente (buscador),
  contrato, rango de fechas de la solicitud, número (`SR-0012` o `12`, D-69 punto 16) y, solo para el Gerente, Vendedor.
- **Orden** (criterio «tablas siempre ordenadas»): primero las pendientes, de la más antigua a la más reciente (paso 2 de los dos casos de
  uso: el Gerente atiende primero la que más espera); después las resueltas, de la resolución más reciente a la más antigua.
- **Columnas** (prototipo, `tabSolicitudes`): solicitud (`SR-0012`), tipo («Queja · retraso» o «Discrepancia de cantidad»), entrega y
  contrato con el cliente debajo, fecha de la solicitud, indemnización (la guardada si está aceptada; «—» si no) y estado. Paso 2: además, la
  fecha de la entrega y la cantidad de líneas o de detalles. 50 por página; sin consultas por fila.
- **Contador de la pestaña** (solo el Gerente): las pendientes, en rojo si hay (criterio «contadores rojos»).

### La ficha (COM-CNS-SRV, reglas 3 a 5 y 7; paso 4)

`FichaDeSolicitud` trae, para cualquiera de los dos roles:

- **Encabezado:** número, tipo, estado; el cliente, el contrato con «N de M incumplimientos», la entrega (`OT-0231`) con su fecha
  prometida (`fecha_periodo` de sus líneas; si son distintas, la menor y la mayor), su fecha real (`fecha_resolucion_orden`) y el
  Transportista (o «Retiro en invernadero»), la fecha de la solicitud y el estado de pago de la entrega con su monto a cobrar (regla 3).
- **Lo que indicó el cliente** (queja): el tipo y el motivo.
- **Las líneas:**
  - discrepancia: una fila por `LineaDiscrepancia`: el detalle (variedad y dirección), la mínima estipulada, las cantidades planificada
    (`entregada + perdida + devuelta`, D-68 punto 7), entregada, perdida y devuelta, la indemnización por planta faltante y el monto; debajo,
    el total;
  - queja por retraso: la variedad, la fecha del período, el plazo de entrega, los días de retraso, la indemnización por día, las cantidades
    y el monto;
  - queja sin cláusula: la variedad y las cantidades, y el tope (4a.1).
- **Pérdidas** (paso 4 de COM-EVL-DSC: «la causa y la descripción de las pérdidas»): las mermas de la entrega (`Merma.orden`, causa
  `dano_en_entrega`, COM-04a) con su cantidad y su descripción.
- **Intentos fallidos** (queja; paso 4 y 4b de COM-RSV-QJA): `concrecion.intentos_fallidos([entrega.id])` con fecha y hora, motivo y
  descripción. **4b:** si la queja es por retraso y algún intento tiene `fecha_programada` dentro del plazo de algún detalle de la queja
  (`fecha_programada <= fecha_periodo + plazo_entrega_dias`), la ficha lo destaca con el texto del criterio: «Hubo un intento de entrega
  dentro del plazo. Si el retraso se debió a la ausencia del cliente, no es de la empresa y corresponde rechazar.». Sin intentos: «No hay
  intentos de entrega fallidos registrados.».
- **Pendiente** (regla 4): al Vendedor, «La evalúa el Gerente. Vas a recibir una notificación con la decisión.»; al Gerente, el panel para
  decidir (regla 7 y paso 4: el monto que correspondería, cómo se aplicaría, los incumplimientos y si una aceptación resolvería el contrato
  con su multa; 6c si el contrato no está vigente).
- **Resuelta** (regla 5): la decisión, el Gerente, la fecha y las observaciones; con indemnización, cuánto se descontó (y el monto a
  cobrar que quedó) y cuánto se reintegró y con qué medio; «Cuenta como incumplimiento» si está aceptada; el estado del aviso al cliente con
  «Reenviar aviso» (9a) y, si el cliente no tiene correo, «Imprimir comprobante». Al Gerente, «Anular resolución».
- **Historial de resoluciones anuladas** (D-69, punto 10): por cada `Anulacion` de la solicitud, la resolución anulada (decisión, Gerente,
  fecha, monto), quién la anuló, cuándo y el motivo. De la más reciente a la más antigua.

### Registrar la resolución (paso 8 y 5a.4 de los dos casos de uso)

- **`datos`** (`DatosDeResolucion`): `decision` (`aceptar` / `rechazar`; `decision_obligatoria`), `observaciones` (hasta 500, sin espacios al
  borde; obligatorias al rechazar: 5b), `monto` (solo en una queja sin cláusula; en las demás, `monto_no_admitido`) y `medio_reintegro`
  (`efectivo` / `transferencia`; obligatorio si `reintegrado > 0`: 6a, 6d).
- **Bloqueos** (`docs/patrones/bloqueos.md`, «Resolver o anular una solicitud»; D-69, punto 11): las cuentas (el Gerente y el Vendedor del
  contrato) → el **invernadero de origen** de la entrega (`bloquear_invernadero_para_alertas`: activo o no) → el **suministro** → la
  **entrega** → la **solicitud** (y su hija) → su `AlertaComercial`. Después, la relectura: la solicitud sigue «pendiente» (8a:
  `solicitud_no_pendiente`, con la decisión, el Gerente y la fecha) y la **huella** coincide (8b: `solicitud_cambio` con qué cambió: el estado
  de pago, el monto a cobrar, los incumplimientos o el estado del contrato; la pantalla vuelve al paso 4 con los datos nuevos).
- **Con todo verificado, al aceptar:**
  1. el monto (sección «Cálculos») y la aplicación con el monto a cobrar **releído bajo bloqueo**;
  2. la solicitud: `estado_solicitud = aceptada`, `fecha_resolucion = hoy`, `gerente`, `observaciones_resolucion`, `monto_indemnizacion`,
     `monto_descontado`, `monto_reintegrado`, `medio_reintegro`; en una discrepancia, el `monto_indemnizacion_linea` de cada línea;
  3. `suministro.cantidad_incumplimientos += 1` (postcondición d), cualquiera sea el estado del contrato (6c: historial);
  4. la bitácora (postcondición f): `bitacora.registrar_evento_de_contrato(invernadero_de_origen, "incumplimiento_de_clausula", descripcion,
     responsable=gerente)` (`docs/api/produccion.md`, sección 11). Descripción (hasta 500; si no entra, las líneas que sobran como «y N más»):
     «SR-0012 · Discrepancia · OT-0231 de SUM-0013 · Transportista: Juan Pérez · Lechuga Crespa: 70 de 80, $500,00 · Total: $500,00» o
     «SR-0013 · Queja por retraso · OT-0231 de SUM-0013 · Retiro en invernadero · Lechuga Crespa: 3 días, $3.000,00 · Total: $4.500,00»;
  5. la alerta: `resolver_alerta(alerta_comercial.alerta_id)` (b); si ya estaba resuelta (una solicitud reabierta, D-69 punto 4), nada;
  6. el aviso al Vendedor del contrato, si está activo (D-42, dentro de la transacción): «SR-0012 aceptada», «El Gerente aceptó la
     discrepancia de OT-0231 (Pérez SA): indemnización de $500,00, descontada del monto a cobrar. Incumplimientos: 2 de 3.»;
  7. el registro de auditoría (j, k; ver abajo);
  8. `on_commit`, en este orden: el correo al cliente (g) y `resoluciones.resolver_si_corresponde(suministro.id)` (h, 6b; D-69 punto 13).
- **Al rechazar** (5a.4): la solicitud `rechazada` con `fecha_resolucion`, `gerente` y `observaciones_resolucion` (los montos quedan nulos);
  la alerta resuelta; el aviso al Vendedor con las observaciones; la auditoría; `on_commit`, el aviso de rechazo al cliente. No cambia el
  contador ni hay bitácora (i).
- **El correo al cliente** (9, 5a.5, 9a; `comercial/servicios/comprobantes.py` de COM-02, siempre con `transaction.on_commit`):
  - aceptada con monto > 0: el **comprobante de indemnización** (tipo `indemnizacion`, «Lista de tecnología», 9a): la entrega y su fecha;
    cada línea (discrepancia: variedad, entregada, mínima, por planta y monto; queja por retraso: variedad, días e indemnización por día);
    el total; cuánto se descontó de lo que debe por la entrega y cuánto se reintegró y con qué medio; pie «Comprobante interno, sin validez
    fiscal.»;
  - queja aceptada con monto 0: el **aviso de aceptación** (9b de COM-RSV-QJA: número y tipo, entrega, decisión y observaciones);
  - rechazada: el **aviso de rechazo** con las observaciones (9b; en una discrepancia, que «no fue reconocida»).
  El resultado va a `SolicitudRevision.estado_aviso_cliente` (`enviado` / `pendiente_envio` / `sin_correo`; D-69, punto 17). Sin correo (un
  contrato no vigente cuyo cliente quitó el correo): no se intenta, y la ficha ofrece «Imprimir comprobante» (la página imprimible, como en
  COM-02). **9a:** con `pendiente_envio`, «Reenviar aviso» en la ficha y el reintento de la parte 4 del paso 50 («Correos pendientes»,
  `entregas.md`), que suma las solicitudes con `pendiente_envio` (como COM-06a sumó las entregas concretadas).
- **Auditoría** (D-36): un registro `evaluacion_discrepancia` o `resolucion_queja`, con el Gerente y su rol; afectados: la solicitud
  (principal, con los cambios), la alerta, el suministro (`cantidad_incumplimientos` antes y después) y el registro de bitácora creado; en
  `datos`, la entrega, el monto a cobrar antes y después y, si hubo, el reintegro y su medio.
- **Lo que no hace:** no crea asientos (D-57); no resuelve el contrato (lo hace COM-RSV-SUM fuera de la transacción); no toca el stock, las
  reservas ni la entrega.

### Anular una resolución (COM-ANL-SRV)

- **Quién y desde dónde:** el Gerente, desde la ficha de una solicitud resuelta («Anular resolución», ventana `MODALS.anlsrv`; sin
  JavaScript, una página).
- **Bloqueos de 2a a 2c** (D-69, punto 5), en `datos_de_anulacion` y otra vez bajo bloqueo:
  - **2a** (`resolucion_del_contrato`): `suministro.solicitud_resolucion_id == solicitud.id`. «No se puede anular: esta aceptación resolvió el
    contrato SUM-0013.» El campo lo crea COM-07a (vacío) y lo carga COM-07b: hasta entonces 2a se prueba con una fábrica que lo carga.
  - **2b** (`entrega_cobrada`): aceptada con `monto_descontado > 0` y la entrega «pagada» (`estado_de_pago`; desde COM-08a). «Primero anulá el
    cobro de OT-0231 (Anular cobro).»
  - **2c** (`indemnizacion_reintegrada`): `monto_reintegrado > 0`. «No se puede anular: la indemnización ya se le reintegró al cliente
    ($ 1.200,00 por transferencia).»
  - **2d:** rechazada: «Vuelve a pendiente sin cambios en los incumplimientos ni en el monto a cobrar.» y sigue.
- **Paso 2 (lo que va a pasar):** el estado nuevo; con una aceptada, el contador antes y después y el monto a cobrar antes y después (`+
  monto_descontado`); el contraasiento como «Fuera de esta ronda · contabilidad» (`fueraRonda`).
- **Paso 3:** `motivo` obligatorio (`motivo_obligatorio`), de 1 a 500 caracteres, sin espacios al borde (`motivo_largo`).
- **Paso 5, la transacción:** los bloqueos de «Registrar la resolución» (cuentas → invernadero de origen → suministro → entrega → solicitud);
  la relectura: la solicitud sigue resuelta (`solicitud_no_resuelta`), 2a a 2c siguen sin darse y la huella coincide (5a: `solicitud_cambio`;
  vuelve al paso 2). Con todo verificado:
  1. la `Anulacion`: `fecha_anulacion = hoy`, `motivo_anulacion`, `usuario`, `solicitud` y la copia de la resolución (D-69, punto 10);
  2. la solicitud a «pendiente», con `fecha_resolucion`, `gerente`, `monto_indemnizacion`, `monto_descontado`, `monto_reintegrado` y
     `medio_reintegro` nulos y `observaciones_resolucion` vacías; en una discrepancia, el `monto_indemnizacion_linea` de cada línea, nulo;
     `estado_aviso_cliente` vuelve a su valor inicial;
  3. si estaba aceptada: `suministro.cantidad_incumplimientos -= 1` (postcondición c; nunca menos de 0: restricción de la base) y el evento
     de bitácora `anulacion_de_resolucion` en el invernadero de origen (d; D-69 punto 6): «Se anuló la aceptación de SR-0012 (OT-0231 de
     SUM-0013): vuelve a pendiente. Motivo: …»;
  4. la alerta no se toca (D-69, punto 4);
  5. el aviso al Vendedor, si está activo (e): «Se anuló la resolución de SR-0012», «El Gerente anuló la aceptación de la discrepancia de
     OT-0231 (Pérez SA). Monto a cobrar: $ 9.500,00 → $ 10.000,00. Incumplimientos: 2 → 1. Motivo: …»;
  6. el registro de auditoría `anulacion_resolucion_solicitud` (f): afectados la solicitud (principal, con los valores anteriores y los
     nuevos), la anulación creada, el suministro (el contador) y el registro de bitácora; el motivo en `datos`.
- **Paso 7:** «SR-0012 volvió a pendiente de revisión.» con el botón «Volver a resolver» (la misma ficha, con el panel).
- **Lo que no hace:** no envía nada al cliente (el caso de uso no lo pide); no crea el contraasiento (D-57); no vuelve un contrato a
  «vigente» (mejora futura, tema abierto de COM-RSV-SUM).

### El enlace de las alertas (1a de COM-EVL-DSC y de COM-RSV-QJA)

COM-06a y COM-06b registraron `comercial_discrepancia_entrega` y `comercial_queja` en `registrar_enlace_de_alerta` con la ficha del suministro
(`rutas.md` y `confirmacion.md`). Un código admite un solo registrante: COM-07a **cambia esa función** para que devuelva la ficha de la
solicitud (`/comercial/solicitudes/<id>/`) con el detalle «SR-0012 · Discrepancia · pendiente» (o la decisión, si ya se resolvió). Solo la
recibe el Gerente, que puede abrirla (nunca un enlace a un 403). Prueba mínima del registrante (`docs/api/alertas.md`, sección 8).

### Lo que completa a otras tareas

| Tarea | Qué |
|---|---|
| COM-06a | `monto_a_cobrar` resta lo descontado (D-69, punto 9); el registrante del enlace de la alerta de discrepancia |
| COM-06b | El registrante del enlace de la alerta de queja |
| COM-05a1 | La parte 4 del paso 50 («Correos pendientes») suma las solicitudes con `pendiente_envio` |
| COM-03a | La ficha del suministro, sección «Solicitudes de revisión» (regla 8 de COM-CNS-SUM): número, fecha y entrega, tipo, estado y «Cuenta como incumplimiento», con «Ver»; de la más reciente a la más antigua |
| Panel de control | El grupo «Solicitudes» del Gerente (abajo, «Pantallas») |

## Pantallas

Referencia visual (D-61): `docs/prototipos/comercial/` (`README.md`). Vale la versión final de cada función.

| Pantalla | Funciones del prototipo | Qué tiene |
|---|---|---|
| Comercial · pestaña «Solicitudes de revisión» (`/comercial/solicitudes/`) | `tabSolicitudes` (línea 960), `comTabs` (línea 1487, el contador) | La lista (arriba, «La lista») |
| Ficha de la solicitud, con el panel del Gerente (`/comercial/solicitudes/<id>/`) | `INIT.srv`, `VIEWS.srv` (líneas 1152 y 1765: vale la de 1765 para una pendiente del Gerente), `srvCalc` (línea 1759), `ACT['srv-ok']` (la última) | La ficha (arriba) y el panel «Evaluar la discrepancia» o «Resolver la queja»: decisión, monto (solo sin cláusula), medio del reintegro (cuando hay reintegro), incumplimientos antes y después, la advertencia de resolución (6b) o de historial (6c), observaciones y el resumen con «Confirmar la decisión» |
| Anular la resolución (ventana) | `MODALS.anlsrv`, `ACT['anlsrv-ok']` (línea 1176) | Paso 2, el motivo y «Anular resolución»; con un bloqueo, solo el mensaje y «Volver» |
| Panel de control del Gerente · grupo «Solicitudes» | `secComercial` (línea 1548) | Un indicador «Pendientes» («quejas y discrepancias a resolver»; en el color de advertencia si hay) que lleva a la pestaña filtrada por pendientes. Solo el Gerente (plan de la ronda, sección 4) |
| Ficha del suministro · «Solicitudes de revisión» | `VIEWS.sum` (línea 1600, `ccard('sol', …)`) | La sección de la regla 8 de COM-CNS-SUM |

- **Panel de control (comparado con lo que va a estar implementado, plan de la ronda, sección 5):** el grupo «Solicitudes» va dentro de
  la sección «Comercial» que registró COM-05a2 con `registrar_seccion_de_inicio` (grupo «Entregas»), después de él; COM-07a suma su
  indicador en la **misma** sección (no registra otra) y COM-08a sumará «Cobranza» (y COM-08c, para el Vendedor, «Resultados del mes en curso»). Para el Vendedor no se muestra (regla 4 de COM-CNS-SRV:
  la resuelve el Gerente).
- **Campana:** las alertas de discrepancia y de queja ya salen (COM-06a, COM-06b); COM-07a solo cambia su enlace.
- **Menú:** sin cambios (la pestaña es de «Comercial»).
- **Pasos bloqueados** (criterio de la ronda): en el panel, las observaciones, el monto y el medio aparecen después de elegir la decisión,
  y «Confirmar la decisión» queda deshabilitado mientras falte algo obligatorio. Sin JavaScript: el resumen es una página
  (`/comercial/solicitudes/<id>/resolver/revisar/`).
- **Textos explicativos** (criterio «textos explicativos siempre»):
  - bajo «Decisión»: «Aceptar significa que hubo un incumplimiento de la empresa: suma uno al contrato y, si corresponde, indemniza al
    cliente. Rechazar no cambia nada del contrato; el cliente recibe tus observaciones.»;
  - bajo la indemnización calculada: «Sale de la cláusula del contrato; no se puede modificar.»; bajo la manual: «Entre $ 0 y $ 84.000,00:
    lo que el cliente paga por los productos de la queja.»;
  - bajo «Medio del reintegro»: «La entrega ya no debe lo suficiente: el resto se le devuelve al cliente.»;
  - en la lista, arriba: «Las quejas las presenta el cliente al confirmar la entrega; las discrepancias se generan solas cuando una entrega
    queda por debajo del mínimo pactado. Las resuelve el Gerente.»;
  - en la ventana de anulación: «La solicitud vuelve a pendiente para resolverla de nuevo. La resolución anulada queda en el historial.».
- URLs: `solicitudes/`, `solicitudes/<id>/`, `solicitudes/<id>/resolver/revisar/`, `solicitudes/<id>/resolver/`, `solicitudes/<id>/anular/`,
  `solicitudes/<id>/comprobante/` (imprimible) y `solicitudes/<id>/reenviar-aviso/`, bajo el espacio `comercial`. Vistas que solo
  orquestan, `never_cache`, con `rol_requerido("gerente", "vendedor")` para leer y `rol_requerido("gerente")` para escribir.

### Lo que difiere del prototipo (corregir, D-61)

| Pantalla | Prototipo | Caso de uso (manda) |
|---|---|---|
| Resolver queja sin cláusula | El tope es el monto total de la entrega (`tope: e.monto`) | MD-114: lo que el cliente paga **por los detalles de la queja** (Σ `monto_pagar` de sus líneas) |
| Resolver queja por retraso | «Intentos de entrega fallidos registrados: ninguno», fijo | Paso 4 y 4b: los intentos de `IntentoFallido`, con el destacado de 4b |
| Evaluar y resolver | Al aceptar, el contrato pasa a «resuelto» en la misma operación (`c.est = 'resuelto'`) | COM-RSV-SUM lo resuelve fuera de la transacción (COM-07b); la ficha dice «se resolverá» |
| Ficha | Sin historial de anulaciones; la anulación no deja rastro | D-69, punto 10: el historial con cada `Anulacion` |
| Lista | Filtros tipo, estado y Vendedor | Regla 2: además cliente, contrato y fechas (y el número, D-69 punto 16) |
| Ficha | «Pago de la entrega» con «vencida» | MD-139: «en mora» |
| Evaluar discrepancia | Las pérdidas no se muestran | Paso 4 de COM-EVL-DSC: la causa y la descripción de las pérdidas |

## Pruebas

- `test_indemnizaciones.py`: tablas para cada cálculo (los ejemplos de las reglas; redondeo; tope exacto y un centavo más; aplicación con
  monto 0, menor, igual y mayor que el monto a cobrar, y con la entrega pagada).
- `test_com_evl_dsc.py` (`ComEvlDscServicioTests`): una por postcondición (a a k, sin e: «Fuera de la ronda»; con el asiento que **no** se
  crea) y extensión (1a, 1a1, 3a, 5a, 5b, 6a con `mock.patch` de `estado_de_pago`, **6d** (D-69 punto 2), 6b (se llama a
  `resolver_si_corresponde` después del commit, con `captureOnCommitCallbacks`), 6c (finalizado, resuelto y rescindido), 7a en el servicio,
  8a, 8b por cada dato de la huella, 9a); cada regla (decisión total, observaciones, monto fijo aunque cambie la cláusula después, un solo
  incumplimiento con varias líneas, bitácora solo al aceptar).
- `test_com_rsv_qja.py` (`ComRsvQjaServicioTests`): lo mismo para la queja, más 4a (sin monto, con 0, con monto), 4a.3a (negativo, tres
  decimales, el tope y un centavo más), 4b (con un intento dentro del plazo, fuera y sin intentos), 6d (asiento compuesto que no se crea, el
  reintegro guardado) y `monto_no_admitido`.
- `test_com_anl_srv.py` (`ComAnlSrvServicioTests`): una por postcondición (a a f) y extensión (2a con la fábrica, 2b con `mock.patch`, 2c con
  reintegro total y parcial, 2d, 3a, 5a); el contador no baja de 0; la copia en la `Anulacion`; resolver de nuevo después de anular (la
  alerta no cambia, el número de incumplimientos vuelve a subir, el monto a cobrar vuelve a bajar); dos anulaciones sucesivas de la misma
  solicitud (dos `Anulacion`).
- `test_com_cns_srv.py`: una por regla (1 a 7, la 6 como D-69 punto 16); el orden; los filtros; el Vendedor no ve otras; sin consultas por
  fila (`assertNumQueries` igual con una y con veinte).
- `test_solicitudes_concurrencia.py` (`@tag("concurrencia")`): dos aceptaciones de solicitudes distintas del mismo contrato (el contador sube
  2); la misma solicitud desde dos sesiones (una sola); aceptar contra anular la misma; aceptar contra concretar otra entrega del mismo
  contrato (sin interbloqueo); dos aceptaciones de la misma entrega (discrepancia y queja) con el monto a cobrar justo (nunca negativo).
- `test_solicitudes_vistas.py`: permisos (Vendedor en lectura, otros roles 403); el flujo con HTMX y sin JavaScript; el registrante del
  enlace de la alerta; el grupo del panel y el contador de la pestaña; la sección de la ficha del suministro.
- Invariantes: `verificar_invariantes_de_solicitudes()` (con lo nuevo: la restricción de los montos, el monto a cobrar nunca negativo y
  `cantidad_incumplimientos` = aceptadas del contrato) después de cada prueba que resuelve o anula.

## Para más adelante

- **COM-07b:** COM-RSV-SUM (lo que dispara 6b) y `solicitud_resolucion` cargado (2a con datos reales).
- **COM-08a:** la entrega pagada (6a, el cobro de 8b, 2b) con datos reales; **COM-08b:** `Anulacion.pago` y `cliente_pago_en_fecha`; COM-REG-CBR cobra el
  monto a cobrar que deja esta tarea.
- **Ronda de contabilidad:** los asientos de la indemnización (simple o compuesto) y el contraasiento, originados en la solicitud y en la
  `Anulacion`.
- Temas abiertos de los casos de uso: un plazo o recordatorio para las solicitudes pendientes; quién ejecuta el reintegro y si hay que
  avisarle.

## Solo prototipo

Los de `docs/prototipos/comercial/README.md`, «Elementos del prototipo que no van en el sistema». En estas pantallas, además: los datos de
ejemplo (`DB.srv`), los identificadores armados a mano (`QJA-017` en el acuse del portal) y el valor por omisión de la cláusula en `srvCalc`
(`{indR:1000, indM:800, …}`, cuando no encuentra el detalle).
