# Casos de uso · comercial · Resolución del suministro por incumplimientos

Copia para el repo de **COM-RSV-SUM · Resolver Suministro por Incumplimientos, versión 0.1** (documento de Drive «CU extendidos», consultado
el 22/11/2026). Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU (comercial)» (sección 7), con el modelo de dominio (reglas
11 a 14 de 8.14; 5 de 8.11; 9, 10, 13, 14 y 16 de 8.8; 22, 28 y 29 de 8.6; 13 de 8.12; ronda 22) y con «MD · Cambios para el modelo de dominio
(comercial)» (MD-119 a MD-123).

**El código va en la app `comercial`** (`comercial/servicios/resoluciones.py`, que COM-07a deja con `resolver_si_corresponde` neutra; la
lectura de la ficha del suministro en `comercial/servicios/suministros.py`; modelo en `docs/modelo/comercial.md`: «Suministro»,
«DetalleSuministro», «AlertaComercial», «SolicitudRevision»). Incluye PROD-CNL-ORD con las funciones que ya existen
(`docs/casos_de_uso/produccion/cancelar_orden.md`: `cancelar_cosecha_incluida`, COM-04a, y `cancelar_entrega_incluida`, COM-05a1) y crea
partidas con `camara.crear_partida` (`docs/api/produccion.md`, sección 8). Cómo se guarda y cómo corre: **D-69**. Tarea: **COM-07b**. Las
aceptaciones que lo disparan están en `docs/casos_de_uso/comercial/solicitudes.md` (COM-07a). Archivos de pruebas:
`comercial/tests/test_com_rsv_sum.py`, `test_resolucion_concurrencia.py` y `test_resolucion_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-RSV-SUM no numera sus reglas (`test_regla_que_no_cambia_…`); postcondiciones `test_post_<letra>_…`;
extensiones `test_ext_<numero>_…` (`test_ext_3c_…`); disparadores `test_disparador_<numero>_…`.

## COM-RSV-SUM · Resolver Suministro por Incumplimientos

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial.

**Actor principal:** InfoPonia (proceso automático). Resuelve el contrato sin intervención de una persona: la decisión que lo provoca ya la tomó el Gerente al aceptar una discrepancia o una queja.

**Versión:** 0.1

**Disparadores**

1. Aceptación de una solicitud de revisión: COM-EVL-DSC · Evaluar Discrepancia o COM-RSV-QJA · Resolver Queja registran una aceptación con la que la cantidad de incumplimientos de un suministro «vigente» supera la tolerada (extensión 6b de cada uno). InfoPonia lo ejecuta fuera de la transacción de esa aceptación, una vez confirmada.
2. Recuperación diaria: una vez por día, InfoPonia busca los suministros «vigentes» cuya cantidad de incumplimientos ya supera la tolerada y los resuelve (extensión 1a). Cubre el disparo que falló o no llegó a ejecutarse.

**Personal involucrado e intereses**

  - Gerente: quiere que el contrato quede resuelto en cuanto su decisión lo provoca, sin tener que deshacer a mano reservas, cosechas ni entregas, que la multa por resolución quede registrada en la contabilidad y que le llegue una alerta con todo lo que se deshizo y la multa que hay que pagar.
  - Cliente: quiere enterarse enseguida de que el contrato terminó, de la multa que le corresponde y de qué entregas ya no va a recibir, y seguir pudiendo confirmar o reclamar las que ya recibió.
  - Vendedor: quiere saber que su contrato quedó resuelto y qué entregas se cancelaron, para atender al cliente, y seguir cobrando las entregas ya concretadas.
  - Agrónomo: quiere enterarse de las cosechas que se cancelaron, del producto ya cosechado que volvió a la cámara de su invernadero y de los envases que estaban reservados para entregas que ya no salen.
  - Capataz y Transportista: quieren que las cosechas y las entregas canceladas salgan de su bandeja y enterarse en el momento, sobre todo si la entrega ya está en el vehículo.
  - Organización (Jardín Botánico): quiere varias cosas:
  - que el stock que el contrato tenía apartado vuelva a estar libre enseguida, para venderlo a otros clientes antes de que pierda su aptitud comercial;
  - que la multa se registre cuando se produce la resolución (base devengado) y por el monto pactado, sin que nadie lo modifique;
  - que lo que ya ocurrió (entregas concretadas, deudas del cliente, indemnizaciones, bitácora) se conserve sin cambios.

**Relaciones con otros casos de uso**

  - «include» PROD-CNL-ORD · Cancelar Orden: se incluye en el paso 6, una vez por cada cosecha «a realizar» del contrato y una vez por cada entrega «a realizar» del contrato («Cancelación de una entrega»), dentro de la transacción de este caso de uso.
  - Lo disparan: COM-EVL-DSC · Evaluar Discrepancia (postcondición h) y COM-RSV-QJA · Resolver Queja (postcondición h).
  - Dispara: PROD-ASG-CAM · Asignar Stock de Cámara, si ingresó producto a la cámara o se liberó alguna línea de cámara (disparadores 1 y 2 de PROD-ASG-CAM).
  - Lo siguen: COM-REG-CBR · Registrar Cobro de Suministro, que sigue cobrando las entregas concretadas sin pagar del contrato resuelto; COM-EVL-DSC y COM-RSV-QJA, que siguen evaluando las solicitudes pendientes como historial (extensión 6c de cada uno); CMP-AJT-STK · Ajustar Stock de Insumo, si los envases de una entrega cancelada ya se usaron; Registrar Asiento (CU-17), con el que el Gerente registra el pago de la multa (ver la situación 2).
  - Relacionados, sin inclusión: COM-CNF-ENT · Confirmar Entrega, porque el cliente puede confirmar y presentar quejas sobre entregas de un contrato resuelto (regla 8 de 8.15); el proceso de pre-reserva de períodos (regla 16 de 8.8), PROD-ASG-STK, PROD-ASG-CAM y COM-PNF-ENT, que dejan de actuar sobre el contrato porque sus detalles ya no están «vigentes».

**Puntos de extensión**

  - Ninguno: no es extendido por otros casos de uso.

**Precondiciones**

a. La aceptación de la discrepancia o de la queja que provocó el disparo quedó registrada (su transacción se confirmó), o el disparo es la recuperación diaria.

b. El disparo identifica el suministro.

c. Existe un ejercicio contable vigente y existen las cuentas contables Indemnizaciones por Resolución de Contratos e Indemnizaciones a Pagar (ver la situación 2). Si no se cumple, se aplica la extensión 5b.

**Garantías mínimas**

  - La resolución es atómica, incluidas las cancelaciones de PROD-CNL-ORD. Si el caso de uso falla, el suministro y sus detalles siguen «vigentes», no cambia ninguna reserva, cosecha ni entrega, no se crea ninguna partida de cámara ni movimiento de stock, no se registra el asiento de la multa, no se genera la alerta y no queda ningún log de auditoría parcial. El disparo queda pendiente y se vuelve a intentar.
  - Un suministro se resuelve una única vez, solo si está «vigente» y su cantidad de incumplimientos supera la tolerada. Un suministro «finalizado» o «resuelto» nunca cambia de estado en este caso de uso.
  - Lo que ya ocurrió no se modifica: las entregas concretadas, sus montos a cobrar y su estado de pago, las reservas «entregada», las solicitudes de revisión y sus asientos, y los registros de bitácora.
  - Ningún stock queda apartado para el contrato resuelto: al terminar, ninguna reserva de sus detalles queda «activa» ni «lista para entrega», y ninguna de sus órdenes queda «a realizar».
  - La resolución origina como máximo un asiento contable, por la multa, con el Debe igual al Haber. Liberar reservas, cancelar cosechas y entregas e ingresar producto a la cámara no genera asientos.
  - No se envía ningún correo, notificación ni alerta de una resolución que no quedó registrada.

**Garantías de éxito (Postcondiciones)**

**Contrato**

a. El suministro pasó de «vigente» a «resuelto», con la fecha actual como fecha de resolución (ver la situación 4). Su cantidad de incumplimientos no cambió.

b. Cada detalle de suministro «vigente» del contrato pasó a «resuelto». Los detalles «finalizados» conservaron su estado.

**Reservas y cosechas**

c. Cada cosecha «a realizar» que cubría un período de un detalle del contrato quedó «cancelada» por PROD-CNL-ORD, con la fecha actual como fecha de resolución y el motivo «Resolución del suministro por incumplimientos». Su reserva de stock pasó a «liberada» sin volver a cubrirse, y el stock que apartaban sus líneas de lote volvió a estar libre en los lotes.

d. Cada reserva «lista para entrega» de los detalles del contrato pasó a «liberada». El stock que apartaban sus líneas de cámara volvió a estar libre en las partidas.

e. Por cada línea de lote ya cosechada de esas reservas se creó una partida de cámara con:

  - estado «disponible» y motivo «resolución del contrato» (ver la situación 3);
  - cantidad igual a la cantidad cubierta de la línea;
  - costo unitario igual al costo por planta del lote;
  - fecha de ingreso igual a la fecha actual y fecha límite igual a la fecha de la cosecha más la duración postcosecha de la variedad.

Por cada partida se registró un movimiento de stock de tipo «ingreso a cámara», originado en el suministro.

**Entregas**

f. Cada entrega «a realizar» del contrato quedó «cancelada» por PROD-CNL-ORD («Cancelación de una entrega»), con la fecha actual como fecha de resolución y el motivo «Resolución del suministro por incumplimientos». Sus reservas de envases pasaron a «cancelada», sin consumo, y dejó de contar para la capacidad y los límites diarios de su Transportista.

g. La alerta «entrega sin transportista» de cada entrega cancelada que la tuviera activa pasó a «resuelta», con la fecha actual como fecha de resolución (ver la situación 8).

**Multa y alerta**

h. Si la multa por resolución es mayor que cero, se generó un asiento originado en el suministro (R012), en el libro diario del ejercicio vigente, con la fecha actual: Debe Indemnizaciones por Resolución de Contratos / Haber Indemnizaciones a Pagar, por la multa por resolución del contrato.

i. Se generó para el Gerente una alerta «suministro resuelto», activa, con una descripción que identifica el contrato, el cliente, la solicitud de revisión que provocó la resolución, la multa y lo que se deshizo (ver la situación 5).

**Después de confirmar la transacción**

j. Si ingresó producto a la cámara o se liberó alguna línea de cámara, se disparó PROD-ASG-CAM · Asignar Stock de Cámara.

k. Se envió al cliente, por correo, el aviso de resolución del contrato, con la multa y las entregas canceladas.

l. Se notificó la resolución al Vendedor del contrato y, por cada invernadero afectado, a su Agrónomo, con las cosechas canceladas, las partidas que ingresaron a su cámara y los envases que estaban reservados. PROD-CNL-ORD notificó al Capataz cada cosecha cancelada y al Transportista cada entrega cancelada.

**Auditoría**

m. Se creó un log de auditoría, con origen «proceso automático», por el cambio de estado del suministro y de cada detalle; por cada reserva, cosecha, entrega, reserva de insumo y alerta modificadas, con el valor anterior y el nuevo; y por cada partida, movimiento de stock, asiento y alerta creados. Las cancelaciones de PROD-CNL-ORD dejan sus propios logs con el mismo origen.

**Escenario principal de éxito (o Flujo Básico)**

(El Gerente aceptó la cuarta discrepancia de un suministro «vigente» con 3 incumplimientos tolerados y multa mayor que cero. El suministro tiene un solo detalle «vigente». Su período más próximo tiene la entrega «a realizar», sin Transportista en ruta, con una reserva «lista para entrega» de una línea de lote ya cosechada y con envasado planificado. El período siguiente tiene una reserva «activa» con su cosecha «a realizar». Los períodos posteriores todavía no tienen reservas.)

1. InfoPonia recibe el disparo con el suministro cuya cantidad de incumplimientos superó la tolerada.
2. InfoPonia verifica que el suministro siga «vigente» y que su cantidad de incumplimientos supere la tolerada.
3. InfoPonia determina lo que el contrato tiene pendiente:
   3.1. los detalles «vigentes»;
   3.2. las reservas no liberadas ni entregadas de esos detalles, separadas en «activa» (con su cosecha «a realizar») y «lista para entrega» (con sus líneas de lote cosechadas y sus líneas de cámara);
   3.3. las entregas «a realizar» del contrato, con su Transportista, su envasado y sus alertas activas.
4. InfoPonia calcula, por cada línea de lote cosechada de una reserva «lista para entrega», la partida de cámara que se creará: su cantidad, su costo unitario y su fecha límite.
5. InfoPonia toma la multa por resolución del contrato y arma el asiento de la multa.
6. InfoPonia verifica que no cambiaron el estado del suministro, sus reservas, sus cosechas ni sus entregas. Luego, en una única transacción:
   6.1. pasa el suministro y su detalle a «resuelto», con la fecha actual como fecha de resolución del suministro;
   6.2. incluye PROD-CNL-ORD · Cancelar Orden para la entrega «a realizar» («Cancelación de una entrega») y para la cosecha «a realizar», con el motivo «Resolución del suministro por incumplimientos»;
   6.3. pasa a «liberada» la reserva «lista para entrega», crea la partida de cámara de su línea cosechada y su movimiento de stock;
   6.4. registra el asiento de la multa;
   6.5. genera la alerta «suministro resuelto» para el Gerente;
   6.6. registra la auditoría correspondiente.
7. InfoPonia dispara PROD-ASG-CAM · Asignar Stock de Cámara con la partida creada.
8. InfoPonia envía al cliente el aviso de resolución del contrato.
9. InfoPonia notifica la resolución al Vendedor del contrato y al Agrónomo del invernadero de origen, con la cosecha cancelada, la partida que ingresó a la cámara y los envases que estaban reservados para la entrega.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes de confirmar la transacción (paso 6), InfoPonia falla:**

1. InfoPonia revierte cualquier registro parcial de la operación, incluidas las cancelaciones de PROD-CNL-ORD.
2. El disparo queda pendiente. InfoPonia lo reintenta desde el paso 2, con los datos vigentes; si tampoco lo logra, lo retoma la recuperación diaria (extensión 1a).

**1a. El disparo es la recuperación diaria:**

1. InfoPonia busca los suministros «vigentes» cuya cantidad de incumplimientos supera la tolerada.
2. Si no hay ninguno, el caso de uso termina sin registrar nada.
3. InfoPonia procesa los suministros de a uno, del que superó la tolerancia antes al que la superó después. Cada uno sigue el caso de uso desde el paso 2, con su propia transacción.

**2a. El suministro ya no está «vigente» (otro disparo ya lo resolvió, o quedó «finalizado» antes de la aceptación):**

1. InfoPonia no registra ningún cambio.
2. El caso de uso termina.

**2b. La cantidad de incumplimientos no supera la tolerada (el disparo no corresponde):**

1. InfoPonia no registra ningún cambio y deja constancia del disparo descartado en el log de auditoría.
2. El caso de uso termina.

**3a. El contrato no tiene reservas ni entregas pendientes (por ejemplo, el próximo período todavía no entró en la ventana de pre-reserva):**

1. InfoPonia no incluye PROD-CNL-ORD ni crea partidas.
2. El caso de uso continúa en el paso 5. En el paso 6 solo se resuelven el suministro y sus detalles, se registra el asiento, se genera la alerta y se registra la auditoría; se omite el paso 7.

**3b. Una reserva «lista para entrega» tiene líneas de cámara:**

1. InfoPonia no crea partidas por esas líneas: al liberarse la reserva, el stock que apartaban vuelve a estar libre en sus partidas.
2. El caso de uso continúa. En el paso 7, InfoPonia dispara PROD-ASG-CAM también por cada partida con una línea liberada.

**3c. Una entrega «a realizar» del contrato está en curso (su Transportista inició la ruta del día y la entrega tiene fecha programada igual o anterior a la actual):**

1. La entrega se cancela igual, con la «Cancelación de una entrega» de PROD-CNL-ORD, que notifica de inmediato al Transportista que no la entregue y que devuelva el producto y los envases al invernadero de origen.
2. El caso de uso continúa. La partida de cámara se crea en el paso 6, aunque el producto todavía esté en el vehículo (ver los temas abiertos).

**3d. Una entrega «a realizar» del contrato no tiene envasado planificado:**

1. PROD-CNL-ORD la cancela sin reservas de insumo que cancelar.
2. En el paso 9, la notificación al Agrónomo no menciona envases para esa entrega.

**5a. La multa por resolución del contrato es cero:**

1. InfoPonia no arma ningún asiento.
2. El caso de uso continúa en el paso 6, que no registra asiento, y la alerta y el aviso al cliente informan que el contrato no prevé multa.

**5b. No hay un ejercicio contable vigente o falta alguna de las cuentas de la precondición c:**

1. InfoPonia no registra ningún cambio: el suministro sigue «vigente» y el disparo queda pendiente.
2. InfoPonia notifica al Gerente que la resolución del contrato espera un ejercicio contable vigente o la cuenta faltante, y la recuperación diaria la vuelve a intentar.
3. Mientras tanto, lo que InfoPonia cree para el contrato (por ejemplo, una reserva de un período que entra en la ventana de pre-reserva) se deshace cuando la resolución se registre, porque el paso 3 toma lo pendiente en ese momento.

**6a. Al registrar, cambió el estado del suministro, de una reserva, de una cosecha o de una entrega del contrato (por ejemplo, el Capataz concretó la cosecha, el Transportista concretó la entrega o InfoPonia creó una reserva nueva):**

1. InfoPonia descarta lo calculado y lo recalcula una sola vez, desde el paso 2, con los datos vigentes y dentro de la misma transacción.
2. Una entrega que ya quedó «concretada» se conserva como está, con sus reservas «entregada», su deuda y su enlace de confirmación. Una cosecha que ya quedó «concretada» deja su reserva «lista para entrega», que se trata en el paso 6 como las demás.
3. Si al recalcular vuelve a cambiar algo, InfoPonia no registra ningún cambio y deja el disparo pendiente, como en la extensión *a.

**6b. No hay un Gerente activo:**

1. La alerta «suministro resuelto» se registra igual y queda esperando al Gerente, que la verá entre sus pendientes cuando se dé de alta (caso por especificar 23 de pendientes_CU).
2. El caso de uso continúa en el paso 7.

**7a. PROD-ASG-CAM no logra asignar la partida:**

1. La resolución permanece registrada. El reintento lo maneja PROD-ASG-CAM (su extensión *a), y la partida sigue con su stock libre disponible para nuevas ventas y suministros.

**8a. El Sistema no logra enviar el correo al cliente o una notificación:**

1. La resolución permanece registrada.
2. InfoPonia reintenta el envío.

**9a. El Vendedor del contrato está inactivo, o un invernadero afectado no tiene Agrónomo activo:**

1. InfoPonia no envía esa notificación. El Gerente ya recibió la alerta «suministro resuelto» y, si falta el Agrónomo, la alerta «invernadero sin Agrónomo activo» ya existe (regla 3 de 8.22).
2. El caso de uso termina.

**Ejecución de PROD-CNL-ORD desde este caso de uso**

  - Se aplica lo que PROD-CNL-ORD define en «Desde Cancelar Compra-venta, COM-RSV-SUM y Modificar Suministro»: las cosechas se cancelan sin incluir PROD-ASG-STK ni seguir el camino de faltante, y las entregas se cancelan con la «Cancelación de una entrega».
  - El motivo es «Resolución del suministro por incumplimientos». El origen de la auditoría es un proceso automático.
  - Se ejecuta el paso 9 de PROD-CNL-ORD (aviso al Capataz de cada cosecha cancelada) y se omite su paso 10, porque no hay un usuario a quien informar: el aviso al Agrónomo es el paso 9 de este caso de uso (ver la situación 9).
  - La precondición de la «Cancelación de una entrega» se cumple, porque las reservas de la entrega se liberan en la misma transacción y el contrato queda resuelto.

**Requisitos especiales**

  - El paso 6, incluidas las cancelaciones de PROD-CNL-ORD, se ejecuta como una única transacción y se completa en no más de 5 segundos para un contrato con hasta 10 detalles.
  - El disparo desde COM-EVL-DSC o COM-RSV-QJA se procesa en no más de 1 minuto desde que se confirma la aceptación.
  - El control de concurrencia bloquea el suministro mientras se resuelve. Impide resolverlo mientras se registra, sobre una de sus órdenes o reservas, la concreción de una cosecha (PROD-CNC-CSC) o de una entrega (COM-CNC-ENT), la modificación de una cosecha automática, el envasado de una entrega (PROD-PNF-ENV), la asignación de un transportista, el inicio de la ruta de su Transportista (COM-INI-RUT), una asignación de stock (PROD-ASG-STK o PROD-ASG-CAM) o la planificación de una entrega (COM-PNF-ENT). La operación que llega segunda vuelve a verificar sus condiciones con el resultado de la primera: si el contrato ya está «resuelto», no actúa sobre él.
  - Las notificaciones, los correos y los disparos se envían después de confirmar la transacción. Las notificaciones se presentan dentro del Sistema y pueden, además, enviarse por correo electrónico.
  - La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los montos se expresan en pesos argentinos, con dos decimales.
  - El aviso de resolución al cliente es de uso interno y no tiene validez fiscal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un proceso automático.

**Reglas de negocio**

  - Disparador: al aceptarse una discrepancia o una queja, la cantidad de incumplimientos supera la tolerada con el contrato «vigente». Con 3 tolerados, el contrato se resuelve con el cuarto incumplimiento (reglas 11 y 13 de 8.14). (Paso 1)
  - Solo contratos vigentes: si el contrato ya está «finalizado» o «resuelto», el incumplimiento se registra como historial y no hay resolución (regla 12 de 8.14). (Paso 2; extensión 2a)
  - Recuperación diaria: como el caso de uso se ejecuta fuera de la transacción de la aceptación, una falla dejaría un contrato «vigente» con más incumplimientos que los tolerados. La recuperación diaria lo detecta por esa misma condición, sin guardar nada adicional (ver la situación 6). (Extensión 1a)
  - Estados: el suministro y sus detalles «vigentes» pasan a «resuelto» (regla 5 de 8.11). Un detalle «finalizado» ya cumplió todas sus entregas y conserva su estado. La resolución no vuelve atrás: no hay reactivación de un contrato resuelto. (Paso 6)
  - Qué se deshace: todo lo que el contrato tiene apartado y todavía no se entregó, en el momento de registrar: reservas «activa» y «lista para entrega», cosechas «a realizar» y entregas «a realizar». Lo que InfoPonia haya creado entre la aceptación y la resolución también se deshace, porque se toma lo vigente al registrar. (Pasos 3 y 6)
  - Qué no cambia: las entregas concretadas, sus montos a cobrar y su estado de pago (COM-REG-CBR las cobra cualquiera sea el estado del contrato), las reservas «entregada», las solicitudes de revisión pendientes, que se evalúan como historial (regla 12 de 8.14), los enlaces de confirmación de las entregas concretadas (regla 8 de 8.15) y la cantidad de incumplimientos. (Garantías mínimas)
  - Cosechas a realizar: se cancelan con PROD-CNL-ORD y su reserva pasa a «liberada» sin volver a cubrirse, porque el detalle ya no debe entregarse. El stock vuelve a estar libre en los lotes, que no cambian su cantidad actual (reglas 13 y 14 de 8.8). (Paso 6)
  - Producto ya cosechado: lo cosechado de una reserva que se libera ingresa a la cámara (regla 28 de 8.6), con el mismo tratamiento que la cancelación después de cosechar (regla 22 de 8.6) y el rechazo de un detalle en COM-DCD-FLT (postcondición k): cantidad igual a la cantidad cubierta de la línea (regla 9 de 8.8), fecha límite desde la fecha de la cosecha, para no reiniciar su vida útil (regla 29 de 8.6), y costo unitario igual al costo por planta del lote (regla 16 de 8.9). El movimiento de stock se origina en el suministro (R017). (Pasos 4 y 6)
  - Líneas de cámara: al liberarse la reserva, su cantidad reservada deja de restar del stock libre de la partida (regla 10 de 8.6). La partida no cambia su cantidad disponible. (Extensión 3b)
  - Entregas a realizar: se cancelan, aunque estén en curso, con la «Cancelación de una entrega» de PROD-CNL-ORD (regla 13 de 8.12). Sus envases reservados se cancelan sin consumo y el Agrónomo los regulariza con CMP-AJT-STK si ya se usaron. (Paso 6; extensión 3c)
  - Períodos sin reserva: no hay nada que deshacer. Como el detalle deja de estar «vigente», el proceso de pre-reserva no vuelve a crear reservas para sus períodos (regla 16 de 8.8). (Extensión 3a)
  - Multa por resolución: es la pactada en el contrato y nadie la modifica. Su asiento se origina en el suministro (R012) y se imputa a Indemnizaciones por Resolución de Contratos, de resultado negativo, porque la multa la paga la empresa (regla 13 de 8.14), contra Indemnizaciones a Pagar, de pasivo, hasta que se pague (ver la situación 2). Con multa cero no hay asiento. (Paso 6; extensión 5a)
  - Sin otros asientos: liberar reservas, cancelar órdenes e ingresar producto a la cámara no genera asientos: el producto cosechado ya está en Productos Terminados desde la concreción de la cosecha (reglas 22 y 32 de 8.6). (Paso 6)
  - Sin bitácora: la resolución no se registra en la bitácora. Queda en el estado del contrato, en el asiento, en la alerta al Gerente y en el log de auditoría, y los incumplimientos que la provocaron ya están en la bitácora de cada invernadero (reglas 13 y 14 de 8.14). (Paso 6)
  - Alerta «suministro resuelto»: una por contrato, para el Gerente (R007), sin origen en el modelo, identificada por su descripción. Pasa a «resuelta» cuando el Gerente la da por atendida, una vez pagada la multa y avisado el cliente (ver la situación 5). (Paso 6)
  - Avisos: el cliente recibe por correo el aviso de resolución (el cliente de un suministro siempre tiene correo, regla 18 de 8.20); el Vendedor y el Agrónomo de cada invernadero afectado, una notificación; el Capataz y el Transportista, las de PROD-CNL-ORD. (Pasos 8 y 9)

**Lista de tecnología y variaciones de datos**

  - 6. La descripción de la alerta «suministro resuelto» indica el contrato, el cliente, el Vendedor, la solicitud de revisión que provocó la resolución (tipo, entrega y fecha de aceptación), la cantidad de incumplimientos y la tolerada, la multa y la cantidad de cosechas y entregas canceladas y de partidas que ingresaron a la cámara. Su nivel de severidad es alto.
  - 8. El aviso de resolución al cliente indica el contrato, la fecha de resolución, la cantidad de incumplimientos que la provocaron, la multa que le corresponde, las entregas canceladas con su fecha programada y que las entregas ya concretadas se siguen cobrando según su vencimiento. Aclara que es de uso interno, sin validez fiscal.
  - 9. La notificación al Vendedor indica el contrato, el cliente, la multa y las entregas canceladas. La del Agrónomo indica, para su invernadero, las cosechas canceladas, las partidas que ingresaron a la cámara con su cantidad y su fecha límite, y los envases que estaban reservados en cada entrega cancelada.

**Frecuencia**

Muy baja: solo cuando un contrato supera los incumplimientos tolerados, más una ejecución diaria de recuperación que en general no encuentra nada. A confirmar con el Jardín Botánico.

**Temas abiertos**

  - Pago de la multa: hoy el Gerente lo registra con un asiento manual (Registrar Asiento, CU-17): Debe Indemnizaciones a Pagar / Haber Caja o Banco c/c. ¿Hace falta un caso de uso propio? ¿Debe poder compensarse con las entregas concretadas que el cliente todavía no pagó?
  - Producto cosechado que ya pasó su fecha límite: si una reserva «lista para entrega» tiene producto cuya fecha límite ya pasó (por ejemplo, una entrega demorada), la partida nace vencida. ¿Se registra en ese momento la merma por vencimiento? Es el mismo tema abierto de COM-DCD-FLT.
  - Producto en el vehículo: la partida de una entrega en curso ingresa a la cámara antes de que el producto vuelva al invernadero. Si el Transportista no lo devuelve completo, la diferencia se registra hoy como merma en cámara. ¿Hace falta registrar la devolución física?
  - Anulación de una resolución: si el Gerente aceptó por error la solicitud que provocó la resolución, hoy no hay forma de volver el contrato a «vigente». Queda como mejora futura, junto con la cancelación por mutuo acuerdo (observación 2 de 8.11).

**Situaciones encontradas y propuestas (versión 0.1)**

  - 1. Qué se hace con las reservas, cosechas y entregas del contrato.
  - Situación: la regla 13 de 8.14 y el caso por especificar 8 de pendientes_CU dejan por definir qué pasa con las reservas, cosechas y entregas a realizar, los estados y los avisos.
  - Propuesta: se deshace todo lo pendiente al registrar (cosechas y entregas «a realizar» con PROD-CNL-ORD, reservas «lista para entrega» liberadas y su producto cosechado a la cámara) y se conserva todo lo ya ocurrido. El suministro y sus detalles «vigentes» pasan a «resuelto»; los «finalizados» no cambian.
  - Por qué: un contrato resuelto ya no obliga a entregar, así que mantener el stock apartado lo inmovilizaría hasta perderlo como merma. Conservar lo ocurrido respeta lo que el modelo ya decidió para un contrato resuelto: se cobran sus entregas (COM-REG-CBR), el cliente confirma y reclama (regla 8 de 8.15) y los incumplimientos posteriores quedan como historial (regla 12 de 8.14). Usar PROD-CNL-ORD cumple lo que ese caso de uso ya prevé para COM-RSV-SUM y deja las reglas de una entrega cancelada en un solo lugar.
  - 2. Contrapartida del asiento de la multa.
  - Situación: la regla 13 de 8.14 fija el Debe (Indemnizaciones por Resolución de Contratos), pero no el Haber. Como el actor es InfoPonia, no hay nadie que elija un medio de pago, y el plan de cuentas del glosario no tiene una cuenta de pasivo para lo que la empresa le debe al cliente.
  - Propuesta: Haber Indemnizaciones a Pagar, cuenta nueva de pasivo, que se cancela cuando el Gerente registra el pago con un asiento manual (CU-17). Hay que registrarla en pendientes_MD (plan de cuentas y regla 13 de 8.14) y en el glosario («Plan de Cuentas»).
  - Por qué: la multa se devenga al resolverse el contrato, aunque se pague después, igual que la deuda con un proveedor en la cuenta Proveedores (MD-43). **Resuelto (23/11/2026):** la cuenta 2.1.02 «Indemnizaciones a Pagar» (Pasivo) entra al plan de cuentas (D-84 punto 7, aprobada por Ezequiel); su pago lo registra el Contador con un asiento manual (D-92 punto 10). Registrar el pago contra Caja o Banco supondría un pago que nadie hizo. Además, el prototipo ya usa una cuenta llamada «Indemnizaciones a pagar» (decisiones de COM-EVL-DSC en pendientes_CU).
  - 3. Motivo de la partida de cámara.
  - Situación: StockCosechado.motivoCosechado admite «cancelación del cliente», «rechazo por cantidad reducida», «rechazo en la entrega», «cosecha planificada por el Agrónomo» y «excedente de cosecha». Ninguno describe el producto que vuelve a la cámara porque la empresa incumplió el contrato.
  - Propuesta: valor nuevo «resolución del contrato». Hay que registrarlo en pendientes_MD (ficha de StockCosechado y regla 28 de 8.6).
  - Por qué: «cancelación del cliente» diría lo contrario de lo que ocurrió, y el motivo sirve para la trazabilidad y para las estadísticas de producto no vendido. Sigue el mismo criterio de los demás motivos.
  - 4. Fecha de resolución del contrato.
  - Situación: Suministro no tiene un atributo con la fecha en que se resolvió. Hoy solo quedaría en el asiento (que no existe si la multa es cero), en la alerta y en el log de auditoría, que no es un dato del dominio.
  - Propuesta: atributo nuevo Suministro.fechaResolucionSuministro, que se carga al pasar a «resuelto». Hay que registrarlo en pendientes_MD.
  - Por qué: el aviso al cliente y la consulta del suministro (CU-39) necesitan mostrarla, y es el mismo criterio que PROD-CNL-ORD propuso para el motivo de cancelación de una orden (su situación 5) y que ya tiene OrdenCompra.fechaResolucion (MD-34).
  - 5. Alerta «suministro resuelto».
  - Situación: la regla 13 de 8.14 menciona una alerta al Gerente, pero el tipo no figura en tipoAlerta, Alerta no tiene asociación con Contrato y nada dice cuándo se resuelve. La regla 7 de 8.18 dice que se resuelve cuando se resuelve el hecho que la originó, y acá el hecho pendiente es el pago de la multa y la gestión con el cliente, que ocurren fuera del sistema.
  - Propuesta: tipoAlerta «suministro resuelto», sin origen en el modelo, como «stock inconsistente» y «pago vencido» (COM-REG-CBR, situación 5): una por contrato, para el Gerente, con severidad alta, que pasa a «resuelta» cuando el Gerente la da por atendida. Hay que registrarlo en pendientes_MD.
  - Por qué: el modelo ya admite alertas sin origen identificadas por su descripción (nota de la 8ª ronda en Alerta), así que no hace falta cambiar el diagrama. El Sistema no puede saber cuándo se pagó la multa, porque el pago se registra con un asiento manual sin documento de origen (MD-31); por eso la resolución de la alerta queda en manos del Gerente.
  - 6. Falla fuera de la transacción de la aceptación.
  - Situación: COM-EVL-DSC y COM-RSV-QJA ejecutan este caso de uso fuera de su transacción. Si falla o no llega a ejecutarse, el contrato queda «vigente» con más incumplimientos que los tolerados, y nada vuelve a mirarlo: el contador ya no sube por esa solicitud.
  - Propuesta: reintento inmediato y una recuperación diaria que busca los suministros «vigentes» con más incumplimientos que los tolerados (disparador 2 y extensión 1a).
  - Por qué: es el mismo criterio que COM-PNF-ENT adoptó el 12/11/2026 para lo listo sin entrega (pendientes_CU, COM-PNF-ENT, punto 1). La condición se detecta con los datos que ya existen, sin un atributo nuevo, y el caso de uso es idempotente: si el contrato ya está «resuelto», no hace nada (extensión 2a).
  - 7. Detalles resueltos como candidatos de la asignación de cámara.
  - Situación: la regla 10 de 8.8 dice que un detalle de venta «confirmado» o «rechazado» no tiene cantidad sin cubrir, pero no dice nada de un detalle de suministro «resuelto» o «finalizado». El paso 3 de PROD-ASG-CAM busca «los períodos de suministro… que tienen cantidad sin cubrir» sin exigir que el detalle esté «vigente», así que podría volver a reservar producto para el contrato que este caso de uso acaba de resolver. PROD-ASG-STK (precondición b) y COM-PNF-ENT (precondición c) sí exigen «vigente».
  - Propuesta: agregar a la regla 10 de 8.8 que un detalle de suministro «finalizado» o «resuelto» no tiene cantidad sin cubrir, y al paso 3 de PROD-ASG-CAM que el detalle de suministro esté «vigente». Hay que registrarlo en pendientes_MD y en pendientes_CU.
  - Por qué: sin esa regla, el disparo del paso 7 de este caso de uso le asignaría a su propio contrato el producto que acaba de liberar. Con ella, el criterio queda en el modelo y vale para todos los casos de uso que calculan la cantidad sin cubrir.
  - 8. Alerta «entrega sin transportista» de una entrega cancelada.
  - Situación: COM-PNF-ENT genera esa alerta para el Gerente y la resuelve al asignar un transportista, pero la «Cancelación de una entrega» de PROD-CNL-ORD no dice qué pasa con ella. Una entrega cancelada dejaría la alerta activa para siempre.
  - Propuesta: la alerta pasa a «resuelta» al cancelarse la entrega (postcondición g). Conviene moverlo a la «Cancelación de una entrega» de PROD-CNL-ORD, para que valga también para Cancelar Compra-venta y Modificar Suministro. Hay que anotarlo en pendientes_CU.
  - Por qué: una entrega cancelada ya no necesita transportista, así que el hecho que originó la alerta desapareció (regla 7 de 8.18).
  - 9. PROD-CNL-ORD incluido por un proceso automático.
  - Situación: la ejecución «Desde Cancelar Compra-venta, COM-RSV-SUM y Modificar Suministro» de PROD-CNL-ORD no dice si se ejecutan sus pasos 9 (aviso al Capataz) y 10 (informe al Agrónomo, que es su actor). Cuando lo incluye InfoPonia, no hay un usuario a quien informar.
  - Propuesta: se ejecuta su paso 9 y se omite el 10; el aviso al Agrónomo es el paso 9 de este caso de uso, una notificación por invernadero. Hay que agregarlo en PROD-CNL-ORD y anotarlo en pendientes_CU.
  - Por qué: el Capataz necesita saber que la cosecha salió de su bandeja, y una notificación por invernadero evita que el Agrónomo reciba un aviso por cada orden cancelada del mismo contrato. Es el mismo criterio que PROD-CNL-ORD ya aplica desde PROD-PNR-FDS, que omite esos pasos porque los cubre el caso de uso base.

**Cambios pendientes aplicados en este caso de uso**

  - PROD-CNL-ORD, situación 5 (motivo de cancelación de una orden, todavía no registrado en pendientes_MD): las cosechas y las entregas canceladas llevan el motivo «Resolución del suministro por incumplimientos» y la fecha actual como fecha de resolución (postcondiciones c y f). Se aplica la propuesta de OrdenTrabajo.motivoCancelacion.
  - Caso por especificar 23 de pendientes_CU (pendientes por rol, sin Gerente activo): la alerta queda esperando al Gerente y la notificación sin destinatario se omite (extensión 6b).


## Cambios ya decididos que se aplican

| Fuente | Qué cambia | Dónde |
|---|---|---|
| MD-120 | `Suministro.fecha_resolucion_suministro` (ya existe desde COM-03a, nula) | Postcondición a, situación 4 |
| MD-121 | Motivo de partida `resolucion_del_contrato` (ya existe desde COM-02, en la ficha de `StockCosechado`) | Postcondición e, situación 3 |
| MD-122 | La alerta «suministro resuelto» **sí** tiene asociación con el suministro (Alerta → Suministro = 0..1): en el código, `AlertaComercial.suministro` (D-63). Reemplaza «sin origen en el modelo, identificada por su descripción» de la regla «Alerta “suministro resuelto”» y de la situación 5 | Paso 6.5, postcondición i |
| MD-123 | Haber de la multa: «Indemnizaciones a Pagar» | Postcondición h: **fuera de esta ronda** (D-57) |
| MD-119 | La cosecha y la entrega canceladas llevan motivo y fecha (`motivo_cancelacion`, `fecha_resolucion_orden`; H2, ya en el código desde PRD-01) | Postcondiciones c y f |
| PCU, sección 7 | La «Cancelación de una entrega» resuelve la alerta «entrega sin transportista» (ya lo hace `cancelar_entrega_incluida`, COM-05a1); un proceso automático que incluye PROD-CNL-ORD omite su paso 10 (situación 9) | Postcondición g; «Ejecución de PROD-CNL-ORD» |
| D-64 (punto sobre los detalles resueltos) | Un detalle de suministro «finalizado» o «resuelto» no tiene cantidad sin cubrir: PROD-ASG-CAM no le vuelve a asignar el producto que este caso de uso libera (situación 7, ya en el código desde COM-04b) | Paso 7 |
| **D-69, punto 5** | `Suministro.solicitud_resolucion`: la solicitud cuya aceptación provocó la resolución (para 2a de COM-ANL-SRV) | Paso 6.1 |
| **D-69, puntos 7, 13, 14 y 15** | El paso diario 33, el disparo con `on_commit`, la alerta y «Dar por atendida», y el registro del disparo descartado | Disparadores, 2b, paso 6.5 |
| D-57; **D-69, punto 8** | **Fuera de esta ronda · contabilidad:** la precondición c, el asiento de la multa (postcondición h, pasos 5 y 6.4, extensión 5a en lo contable) y la extensión 5b (sin ejercicio ni cuentas no se puede dar: no se verifican). La multa se informa igual en la alerta y en el aviso al cliente | Precondición c, paso 6.4, 5b |

## Cómo se aplica en la ronda «Comercial 1» (COM-07b; D-44, D-57, D-59, D-64, D-66, D-67, D-69)

### Qué entra y qué no

- **Entra:** el caso de uso completo, salvo lo contable (arriba); el disparo desde una aceptación (completa `resolver_si_corresponde` de
  COM-07a); la recuperación diaria (paso 33); la alerta «suministro resuelto» con «Dar por atendida»; la carga de
  `Suministro.solicitud_resolucion` (2a de COM-ANL-SRV con datos reales); la resolución en la ficha y en la lista del suministro; la
  resolución de un contrato con rescisión acordada (disparador «Resolución de un contrato con rescisión acordada»).
- **No entra:** el asiento de la multa (D-57); un caso de uso para pagar la multa (tema abierto; hoy es un asiento manual, CU-17, de la ronda de
  contabilidad); volver un contrato resuelto a «vigente» (mejora futura, tema abierto); registrar la devolución física del producto que
  estaba en el vehículo (tema abierto 3: la diferencia se registra como merma en cámara, COM-04b).

### Servicios (`comercial/servicios/resoluciones.py`)

| Función | Qué hace |
|---|---|
| `resolver_si_corresponde(suministro_id) -> ResultadoDeResolucion \| None` | Disparador 1. La llama COM-07a con `on_commit` después de cada aceptación (D-69, punto 13). Corre el caso de uso en **su propia transacción**; si algo falla, registra la excepción (`logger.exception`) y devuelve `None`: la aceptación ya quedó (garantía mínima; *a: el paso 33 lo retoma). `None` también en 2a |
| `resolver_suministro(suministro_id, hoy, *, intento=1) -> ResultadoDeResolucion \| None` | Pasos 2 a 9 para un suministro (abajo). La usan las dos entradas |
| `resolver_suministros_pendientes(hoy) -> ResumenDePaso` | Disparador 2 y 1a (paso 33). Ver «Recuperación diaria» |
| `suministros.dar_por_atendida_la_resolucion(actor, suministro_id) -> Alerta` | «Dar por atendida» (regla «Alerta “suministro resuelto”») |

`ResultadoDeResolucion`: el suministro, los detalles resueltos, las cosechas y las entregas canceladas, las reservas liberadas, las partidas
creadas, las alertas resueltas y la alerta creada. Errores con `ErrorComercial` solo en «Dar por atendida» (`sin_permiso`,
`alerta_resuelta`); el resto no tiene usuario a quien mostrarle un error.

### Resolver un suministro (pasos 2 a 6)

1. **Lectura sin bloquear** (pasos 2 y 3): el suministro; si no está «vigente» (2a) o si `cantidad_incumplimientos <=
   incumplimientos_tolerados` (2b), termina (2b deja el registro `resolucion_suministro_descartada`, D-69 punto 15, sin usuario, con los dos
   números). Si sigue, lo pendiente: los detalles «vigentes»; sus reservas no `liberada` ni `entregada`, con sus líneas; las cosechas «a
   realizar» de esas reservas; las entregas «a realizar» del contrato (con o sin transportista, con o sin envío). De ahí salen las filas a
   bloquear.
2. **Bloqueos** (`docs/patrones/bloqueos.md`, «Resolver un suministro»; el orden de «Cancelar una compra-venta» con el suministro en lugar de
   la venta): las cuentas (el Vendedor, los Capataces y los Agrónomos de las cosechas y de los invernaderos afectados, los transportistas de
   las entregas; en una consulta y en orden de id) → los **invernaderos** de las reservas y de las entregas, en orden de id, con
   `bloquear_invernadero_para_alertas` (activo o no: el producto existe aunque el invernadero se haya dado de baja, D-64 punto 12) → el
   cliente → las variedades → los sectores → los lotes → las partidas → el **suministro** → sus detalles → las **cosechas** → las reservas y
   sus líneas → las **entregas** (y, por `cancelar_orden_incluida`, sus insumos y reservas de insumo). No toma enlaces: los de confirmación de
   las entregas concretadas no cambian (regla «Qué no cambia»).
3. **Relectura** (6a): con todo bloqueado, se vuelve a calcular lo pendiente. Si el suministro ya no está «vigente» (2a) o no supera los
   tolerados (2b, por una anulación que llegó antes), termina sin cambios. Si lo pendiente necesita filas que no se bloquearon (una reserva,
   una cosecha o una entrega nueva de otro invernadero, creada entre la lectura y el bloqueo), se descarta la transacción y se repite **una
   vez** desde el punto 1 (`intento=2`, 6a.1); si en el segundo intento vuelve a pasar, no registra nada y termina (6a.3: el disparo queda
   pendiente y lo toma el paso 33). Una entrega o una cosecha que se concretó antes de bloquear ya no figura como «a realizar»: se conserva
   (6a.2).
4. **Con todo verificado, en este orden** (paso 6):
   1. **Cosechas «a realizar»** (c): `cancelar_cosecha_incluida(None, cosecha, motivo, recubrir=False, avisar=True,
      avisar_agronomo=False)`: la cosecha cancelada con su fecha y su motivo, su reserva «liberada» y el aviso al Capataz (paso 9 de
      PROD-CNL-ORD). El argumento `avisar_agronomo` es **nuevo** (por omisión `True`, para que COM-DCD-FLT y COM-CNL-CVT no cambien): el
      Agrónomo recibe una sola notificación por invernadero en el punto 9 (situación 9).
   2. **Producto ya cosechado** (e): por cada línea de lote con cantidad cosechada > 0 de las reservas que siguen sin liberar, una partida con
      `camara.crear_partida(lote, cantidad, "resolucion_del_contrato", fecha_cosecha=la de su cosecha, fecha_ingreso=hoy,
      costo_unitario=costo_unitario_de_cosecha(…), origen=suministro)`: cantidad = `mín(cosechada, reservada)` de la línea, como COM-CNL-CVT y
      COM-DCD-FLT; el movimiento «ingreso a cámara» se origina en el suministro (R017). Una partida que nace con la fecha límite vencida (tema
      abierto 2) se crea igual: el paso 20 la vence al día siguiente.
   3. **Reservas** (d): las que siguen sin liberar, a «liberada»; sus líneas de cámara dejan de restar del stock libre de su partida (3b).
   4. **Entregas «a realizar»** (f, g; 3c, 3d): `cancelar_entrega_incluida(None, entrega, motivo, avisar_agronomo=False)` (argumento nuevo,
      como en el punto 4.1): la orden cancelada con su fecha y su motivo, sus reservas de envases canceladas sin consumo, la alerta «entrega sin
      transportista» resuelta y el aviso al Transportista. **Una entrega en curso se cancela igual** (3c; a diferencia de COM-CNL-CVT, que no
      sigue): `cancelar_entrega_incluida` ya le dice «No la entregues: devolvé el producto y los envases a {invernadero}.» (situación 11 de
      PROD-CNL-ORD).
   5. **El contrato** (a, b): `estado_suministro = resuelto`, `fecha_resolucion_suministro = hoy`, `solicitud_resolucion` = la solicitud
      aceptada del contrato con la `fecha_resolucion` más reciente (a igual fecha, la de mayor id; D-69 punto 5); los detalles «vigentes», a
      «resuelto» (los «finalizados» no cambian). `cantidad_incumplimientos` no cambia. Con rescisión acordada, los datos de la rescisión
      quedan como estaban (disparador «Resolución de un contrato con rescisión acordada»: la resolución prevalece y el paso 35 ya no lo toma).
   6. **Alertas del contrato que dejan de tener sentido** (regla 7 de 8.18: se resuelven cuando desaparece el hecho): la «período sin cobertura
      completa» activas de los detalles del contrato (una por período: se encuentran por `AlertaComercial.detalle_suministro` y se
      resuelven con `resolver_alerta_de_estado(invernadero.pk, "comercial_periodo_sin_cobertura", clave=…)` (la API recibe el id), COM-03b). El
      caso de uso no lo dice (va a pendientes_CU). Las alertas de las solicitudes pendientes **no** cambian: se evalúan como historial.
   7. **La alerta «suministro resuelto»** (i; D-69 punto 14): `crear_alerta_de_evento(invernadero.pk, "comercial_suministro_resuelto",
      descripcion)` con su `AlertaComercial(suministro=…)`. Invernadero: el de D-63, punto 2 (el del primer detalle con alguna reserva; si no
      hay, el activo de menor id del Vendedor). Si ese invernadero está inactivo, `crear_alerta_de_evento` devuelve `None`: se usa el activo de
      menor id del Vendedor; si tampoco hay, sin alerta y con aviso al Gerente (D-63, punto 4). Descripción («Lista de tecnología», 6; hasta
      500): «SUM-0013 (Pérez SA, Vendedor: Ana Gómez) resuelto por incumplimientos: 4 de 3 tolerados, por SR-0012 (discrepancia de OT-0231,
      aceptada el 22/11). Multa: $ 50.000,00. Se cancelaron 2 cosechas y 1 entrega; 1 partida ingresó a la cámara (Invernadero Sur).». Sin
      Gerente activo, la alerta queda igual (6b).
   8. **Auditoría** (m; D-36): **un** registro `resolucion_suministro`, sin usuario (InfoPonia, D-27); afectados: el suministro (principal,
      con el estado y la fecha), los detalles, las reservas liberadas, las cosechas y las entregas canceladas con sus reservas de envases, las
      partidas creadas con su movimiento, las alertas resueltas y la creada; la solicitud que lo provocó en `datos`. Las funciones incluidas
      no auditan por su cuenta (devuelven lo afectado), como en COM-CNL-CVT: es el único registro del caso de uso, y no uno por cancelación
      (diferencia con la postcondición m, que pide «sus propios logs»; va a pendientes_CU).
   9. **Avisos dentro de la transacción** (l; D-42): al Vendedor, si está activo: «SUM-0013 resuelto por incumplimientos», «Pérez SA. Multa:
      $ 50.000,00. Entregas canceladas: OT-0231 (25/11), OT-0240 (02/12).»; al Agrónomo de **cada invernadero afectado**, si está activo, una
      sola: «SUM-0013 resuelto: cambios en Invernadero Sur», con las cosechas canceladas, las partidas que ingresaron a la cámara (cantidad y
      fecha límite) y los envases que estaban reservados en cada entrega cancelada (9a: sin Agrónomo activo, no se envía; la alerta
      «invernadero sin Agrónomo activo» ya existe).
5. **`on_commit`** (j, k): PROD-ASG-CAM con las partidas creadas y las de las líneas de cámara liberadas (`asignar_camara(partida_ids)`,
   COM-04b; 7a: si falla, lo reintenta PROD-ASG-CAM); el **aviso de resolución al cliente** con `enviar_comprobante(suministro,
   tipo="resolucion")` (`comprobantes.py`, COM-02; «Lista de tecnología», 8: el contrato, la fecha de resolución, los incumplimientos, la
   multa, las entregas canceladas con su fecha programada y que las concretadas se siguen cobrando según su vencimiento; pie «Comprobante
   interno, sin validez fiscal.»), con `Contrato.estado_comprobante` y «Reenviar comprobante» en la ficha (8a), como al pactar.

El **motivo** que reciben las órdenes canceladas: «Resolución del suministro por incumplimientos» (el texto del caso de uso), con el código del
contrato: «Resolución del suministro SUM-0013 por incumplimientos.» (de 1 a 300).

### Recuperación diaria (disparador 2, 1a; paso 33)

- Registro en `ComercialConfig.ready()`: `registrar_paso_diario("resolver_suministros", "Resolver suministros con incumplimientos superados",
  33, resolver_suministros_pendientes)` (D-56, punto 6, enmendado por D-69 punto 7). `core/procesos.py`: COM-07b suma el 33 a la tabla de
  órdenes del comentario.
- Candidatos (1a.1): `Suministro.objects.filter(estado_suministro="vigente", cantidad_incumplimientos__gt=F("incumplimientos_tolerados"))`.
  Orden (1a.3, «del que superó la tolerancia antes»): por la `fecha_resolucion` de su solicitud aceptada más reciente y, a igual fecha, por
  id. Cada uno con `resolver_suministro`, en su propia transacción; si uno falla, se registra y siguen los demás (D-56, punto 5: el paso no
  se corta).
- Sin candidatos (1a.2): no registra nada. `ResumenDePaso` con los resueltos, los descartados y los que fallaron. Idempotente: un segundo
  pase el mismo día no encuentra nada.
- Va **antes** del 35 (cerrar rescisiones), del 40 (pre-reservar) y del 50 (planificar entregas): así un contrato que hay que resolver no
  recibe reservas ni entregas nuevas ese día (5b.3 ya no hace falta en la práctica).

### La resolución en la ficha y en la lista del suministro (COM-CNS-SUM)

- **Ficha** (regla 4 de COM-CNS-SUM, que ya muestra la fecha de resolución): el aviso «Resuelto por incumplimientos el dd/mm/aaaa: 4 de 3
  tolerados, por SR-0012. Multa: $ 50.000,00. Las entregas concretadas se siguen cobrando.» con el enlace a la solicitud; la multa como
  «Fuera de esta ronda · contabilidad» en lo que hace al asiento. Mientras la alerta «suministro resuelto» siga activa, el Gerente ve el
  botón **«Dar por atendida»** con el texto «Usalo cuando hayas pagado la multa y avisado al cliente. La alerta deja de figurar entre tus
  pendientes.» (regla «Alerta “suministro resuelto”»).
- **«Dar por atendida»:** `dar_por_atendida_la_resolucion(actor, suministro_id)`: solo el Gerente activo; bloquea la cuenta → el invernadero
  de la alerta (`bloquear_invernadero_para_alertas`) → la `AlertaComercial`; relee que siga activa (`alerta_resuelta`); `resolver_alerta`;
  auditoría `atencion_suministro_resuelto` con el suministro y la alerta.
- **Lista:** el estado «Resuelto» ya existe (COM-03a); se suma, para el Gerente, la marca «Resolución sin atender» mientras la alerta esté
  activa.
- **Enlace de la alerta** (MAE-02d, `registrar_enlace_de_alerta(("comercial_suministro_resuelto",), …)`): la ficha del suministro, con el
  detalle «SUM-0013 · resuelto · multa $ 50.000,00».
- **Regla 10 de COM-CNS-SUM:** un suministro resuelto no ofrece «Modificar» ni «Rescindir» (ya lo dice: solo «vigente»).

### Lo que completa a otras tareas

| Tarea | Qué |
|---|---|
| COM-07a | `resolver_si_corresponde` deja de ser neutra; 2a de COM-ANL-SRV con datos reales |
| COM-04a | `cancelar_cosecha_incluida(..., avisar_agronomo=True)` (argumento nuevo; las pruebas existentes no cambian) |
| COM-05a1 | `cancelar_entrega_incluida(..., avisar_agronomo=True)` (ídem) |
| COM-03a | La ficha y la lista del suministro resuelto (arriba) |
| COM-03b | La resolución de un contrato con rescisión acordada (prevalece); el paso 35 no toma un contrato resuelto (ya lo filtra por «vigente») |

## Pantallas

COM-RSV-SUM no tiene pantalla propia (el actor es InfoPonia). Lo que se ve:

| Pantalla | Funciones del prototipo | Qué suma COM-07b |
|---|---|---|
| Ficha del suministro | `VIEWS.sum` (las dos definiciones y el reemplazo de la rescisión) | El aviso de la resolución, el enlace a la solicitud y «Dar por atendida» (el prototipo solo muestra «resuelto» y la fecha: se completa, D-61) |
| Lista de contratos (suministros) | `tabContratos` (rama `sum`) | La marca «Resolución sin atender» (Gerente) |
| Campana y detalle de la alerta | (NOT-01, MAE-02c y MAE-02d) | La alerta «suministro resuelto», con su enlace |

- Sin JavaScript, «Dar por atendida» es un formulario con su botón (POST), con la confirmación en la misma página.
- Panel de control: sin cambios (la alerta ya sale en la campana; el grupo «Solicitudes» de COM-07a no cuenta contratos resueltos).

### Lo que difiere del prototipo (corregir, D-61)

| Pantalla | Prototipo | Caso de uso (manda) |
|---|---|---|
| Resolver queja / evaluar discrepancia | El contrato pasa a «resuelto» en la misma operación y no se deshace nada | Fuera de la transacción, y deshace reservas, cosechas y entregas (COM-07b) |
| Ficha del suministro | Sin aviso de la resolución ni forma de atender la alerta | Postcondición i y regla «Alerta “suministro resuelto”» |

## Pruebas

- `test_com_rsv_sum.py` (`ComRsvSumServicioTests`): una por postcondición (a a m, sin h: «Fuera de la ronda»; con el asiento que **no** se
  crea) y extensión (*a con una excepción simulada: nada cambia y el paso 33 lo resuelve después; 1a con dos candidatos en orden; 2a; 2b con
  su registro; 3a sin nada pendiente; 3b; 3c con la entrega en curso y el aviso al Transportista; 3d; 5a con multa 0; 6a con una reserva
  creada entre la lectura y el bloqueo, y con la repetición que vuelve a fallar; 6b sin Gerente; 7a; 8a; 9a); los dos disparadores (desde
  una aceptación con `captureOnCommitCallbacks`, y el paso 33); el escenario principal completo (las cifras del caso); una por regla («Qué se
  deshace», «Qué no cambia» con una entrega concretada sin cobrar, sus reservas «entregada», su enlace y una solicitud pendiente, «Producto
  ya cosechado» con la fecha límite desde la cosecha, «Líneas de cámara», «Períodos sin reserva»); la rescisión acordada que se resuelve;
  la alerta de período sin cobertura resuelta; `solicitud_resolucion` cargada y 2a de COM-ANL-SRV que ahora se da; idempotencia (dos
  disparos seguidos: uno resuelve, el otro termina en 2a); «Dar por atendida» (Gerente, otro rol, ya resuelta); 10 detalles en menos de
  5 segundos (`@tag("rendimiento")`, opcional).
- `test_resolucion_concurrencia.py` (`@tag("concurrencia")`): resolver contra concretar una cosecha del contrato; contra concretar una entrega;
  contra planificar una entrega; contra la pre-reserva (paso 40) de un período; contra iniciar la ruta del transportista de una entrega
  del contrato; dos resoluciones del mismo contrato a la vez (una sola, la otra en 2a); resolver contra anular la solicitud que lo provoca.
- `test_resolucion_vistas.py`: la ficha y la lista del suministro resuelto; «Dar por atendida» con y sin JavaScript; el enlace de la alerta;
  permisos (solo el Gerente ve el botón; el Vendedor ve el aviso).
- Invariantes: `verificar_invariantes_de_reservas()` (ninguna reserva «activa» ni «lista para entrega» de un detalle resuelto; ninguna orden
  «a realizar» de un contrato resuelto) y `verificar_invariantes_de_solicitudes()` después de cada prueba que resuelve.

## Para más adelante

- **Ronda de contabilidad:** el asiento de la multa (Debe Indemnizaciones por Resolución de Contratos / Haber Indemnizaciones a Pagar,
  MD-123) y su pago con CU-17.
- Temas abiertos del caso de uso: un caso de uso para pagar la multa (o compensarla con lo que el cliente debe); la merma por vencimiento de
  una partida que nace vencida; la devolución física del producto en el vehículo; anular una resolución del contrato.
- pendientes_CU: la alerta «período sin cobertura completa» se resuelve al resolver el contrato (punto 4.6); un solo registro de auditoría
  para el caso de uso con sus cancelaciones (punto 4.8).

## Solo prototipo

Los de `docs/prototipos/comercial/README.md`, «Elementos del prototipo que no van en el sistema». En estas pantallas, además: el cambio de
estado del contrato dentro de `ACT['srv-ok']` (`c.est = 'resuelto'; c.fres = HOY`) y el aviso de la resolución en el `toast`.
