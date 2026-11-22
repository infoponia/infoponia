# Casos de uso · producción · Cámara

Copia para el repo de dos casos de uso: PROD-ASG-CAM versión 0.1 de «CU extendidos» y PROD-VNC-CAM versión 0.1 (documento de Drive «CU ·
PROD-VNC-CAM · Vencer Partidas en Cámara (v0.1)», carpeta «InfoPonia · Comercial · Análisis»). Cotejado con pendientes_CU, con «PCU · Cambios
para pendientes_CU (comercial)» (secciones 6, 7 y 12 los cambian), con «MD · Cambios para el modelo de dominio (comercial)» (MD-126,
MD-127, MD-134), con el modelo de dominio (reglas 7, 10 y 28 a 31 de 8.6; 1, 5, 9, 10, 16 y 17 de 8.8; 3, 4, 6 y 8 de 8.9) y con el glosario.

Aunque sus códigos empiezan con PROD, **el código va en la app `comercial`** (D-59, regla A3): los dos crean o recortan reservas. Archivos de
pruebas: `comercial/tests/test_prod_asg_cam.py` y `test_prod_vnc_cam.py`. La merma en cámara que registra una persona es PROD-REG-MRM
(`docs/casos_de_uso/produccion/merma.md`); el reparto y el recorte, `docs/patrones/stock_maduro.md`, sección 8.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: no numeran sus reglas (`test_candidato_…`, `test_orden_de_prioridad_…`, `test_aviso_previo_…`), sus postcondiciones
son `test_post_<letra>_…` y sus extensiones `test_ext_<numero>_…`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-ASG-CAM | Asignar Stock de Cámara (y el paso diario 25) | InfoPonia | `comercial/tests/test_prod_asg_cam.py` |
| PROD-VNC-CAM | Vencer Partidas en Cámara (paso diario 20) | InfoPonia | `comercial/tests/test_prod_vnc_cam.py` |

## PROD-ASG-CAM · Asignar Stock de Cámara
**Alcance:** Sistema InfoPonia.  
**Nivel:** Objetivo de usuario.  
**Módulo:** Producción / Comercial.  
**Actor principal:** InfoPonia (proceso automático). Asigna el stock de la cámara sin intervención de una persona.  
**Versión:** 0.1

**Disparadores**

1.  **Ingreso a cámara:** se crea una partida en la cámara, o una partida existente recibe producto devuelto. Hoy lo registran PROD-CNC-CSC · Concretar Cosecha (cosecha sin contrato y excedente de cosecha), COM-CNC-ENT · Concretar Entrega (devolución y rechazo en la entrega) y COM-DCD-FLT · Decidir Faltante (rechazo de un detalle con producto ya cosechado).
2.  **Liberación de una línea de cámara:** una reserva con líneas de cámara pasa a «liberada», y el stock que apartaba en esas partidas vuelve a estar libre. Hoy lo registra COM-DCD-FLT (rechazo de un detalle). También lo registrarán Cancelar Compra-venta, COM-RSV-SUM · Resolver Suministro por Incumplimientos y Modificar Suministro (CU-38), a especificar.
3.  **Reintento:** un disparo anterior que no pudo completarse queda pendiente, e InfoPonia lo vuelve a ejecutar (extensión *a).

**Personal involucrado e intereses**

  - **Organización (Jardín Botánico):** quiere vender el producto de la cámara antes de su fecha límite, en lugar de perderlo como merma por vencimiento, y no inmovilizarlo en contratos cuya entrega está lejos.
  - **Cliente:** quiere recibir completo lo que pidió. Si estaba por decidir sobre un faltante, quiere enterarse de que ya no hace falta.
  - **Vendedor:** quiere que los faltantes de sus contratos se cubran solos con lo que hay en la cámara, y enterarse de qué se cubrió y de qué sigue faltando.
  - **Agrónomo:** quiere saber qué partidas de la cámara de su invernadero quedaron comprometidas y para qué entregas, para prever el envasado.
  - **Gerente:** quiere que ninguna partida se comprometa dos veces y que los suministros, que tienen cláusulas de indemnización, no queden descubiertos.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - **Lo disparan:**  
      - PROD-CNC-CSC · Concretar Cosecha (postcondición k);
      - COM-CNC-ENT · Concretar Entrega (lo devuelto y lo rechazado que ingresa a la cámara);
      - COM-DCD-FLT · Decidir Faltante (postcondición l);
      - previstos: Cancelar Compra-venta, COM-RSV-SUM · Resolver Suministro por Incumplimientos y Modificar Suministro (CU-38).
  - **Dispara:** COM-PNF-ENT · Planificar Entrega, cuando deja listas para entrega todas las reservas de una venta o de un período de suministro (disparadores 1 y 2 de COM-PNF-ENT).
  - **Relacionados, sin inclusión:**  
      - PROD-ASG-STK · Asignar Stock Maduro aplica la misma prioridad (primero la cámara) cuando el que necesita stock es un detalle. Este caso de uso parte de la partida: busca a quién asignarle el stock libre que acaba de aparecer;
      - COM-DCD-FLT · Decidir Faltante: un detalle que este caso de uso cubre deja de estar pendiente, y el enlace ya no lo ofrece (extensión 6a de COM-DCD-FLT).

**Precondiciones**

a. El caso de uso que registró el ingreso a la cámara o la liberación de la línea confirmó su transacción.  
b. El disparo identifica las partidas afectadas.

**Garantías mínimas**

  - Cada partida se asigna en una única transacción: sus reservas, sus líneas, los cambios de estado de detalles y ventas, y los logs de auditoría se registran juntos o no se registra ninguno.
  - Si la asignación falla, el disparo queda pendiente e InfoPonia la vuelve a intentar: ninguna partida queda sin asignar por una falla.
  - Ninguna partida queda reservada por encima de su stock libre, aun con asignaciones simultáneas.
  - Ningún detalle de venta ni período de suministro queda reservado por encima de su cantidad sin cubrir. Un detalle «confirmado» o «rechazado» nunca recibe reservas.
  - No se modifica la cantidad disponible de ninguna partida ni la cantidad actual de ningún lote. No se registran movimientos de stock, asientos contables ni registros de bitácora, y no se crean órdenes de cosecha ni entregas.
  - No se envía ningún aviso ni correo de una asignación que no quedó registrada.

**Garantías de éxito (Postcondiciones)**

**Por cada partida de la que se asignó stock:**  
a. Se creó una reserva por cada candidato cubierto (un detalle de venta, o un período de un detalle de suministro), asociada a ese detalle, con:

  - la fecha de creación igual a la fecha actual;
  - la fecha de entrega del detalle (la fecha pactada de la venta) o la del período;
  - el estado «lista para entrega».

b. Cada reserva quedó con una única línea, que apunta a la partida, con su cantidad reservada: la menor entre el stock libre que le quedaba a la partida y la cantidad sin cubrir del candidato.

c. El stock se asignó en el orden de prioridad de los candidatos, hasta agotar el stock libre de la partida o los candidatos.

d. Cada detalle de venta «pendiente de decisión del cliente» que quedó sin cantidad sin cubrir pasó a «abierto». Si su venta ya no tiene detalles pendientes, la venta pasó a «abierta» y su enlace de decisión dejó de servir.

e. Si una venta quedó «abierta» con todas las reservas no liberadas de sus detalles no rechazados en «lista para entrega», o si un período de suministro quedó con todas sus reservas en «lista para entrega», se disparó COM-PNF-ENT · Planificar Entrega.

f. Después de confirmar la transacción, se notificó al Vendedor de cada contrato que recibió reservas y al Agrónomo del invernadero de la partida, si el invernadero tiene uno.

g. Por cada detalle que dejó de estar pendiente, se envió al cliente un correo que le informa que el faltante quedó cubierto, si el cliente tiene correo.

h. Se creó un log de auditoría por cada reserva y cada línea de reserva creadas, con fecha, hora, identificador y valores, y por cada detalle y cada venta que cambiaron de estado, con el valor anterior y el nuevo. El log indica que el origen es un proceso automático.

**Si no se asignó nada:**  
i. La partida quedó sin cambios, con su stock libre disponible para nuevas ventas y suministros (PROD-ASG-STK la toma primero). No se envió ningún aviso.

**Escenario principal de éxito (o Flujo Básico)**

(Una partida ingresa a la cámara por el excedente de una cosecha. Hay un solo candidato: un detalle de una compra-venta con envío, «pendiente de decisión del cliente», cuya venta no tiene otros detalles pendientes. La partida lo cubre por completo.)

1.  **InfoPonia recibe el disparo con la partida que ingresó a la cámara.**
2.  **InfoPonia verifica que la partida sea asignable: «disponible», con fecha límite igual o posterior a la fecha actual y con stock libre mayor que cero.**
3.  **InfoPonia busca los candidatos: los detalles de venta y los períodos de suministro de la variedad de la partida que tienen cantidad sin cubrir, cuya fecha de entrega no supera la fecha límite de la partida, cuyo contrato admite el invernadero de la partida y que todavía no tienen entrega.**
4.  **InfoPonia ordena los candidatos por prioridad: primero la fecha de entrega más próxima.**
5.  **InfoPonia toma el primer candidato y determina la cantidad a reservar: la menor entre el stock libre de la partida y la cantidad sin cubrir del candidato.**
6.  **InfoPonia arma la reserva «lista para entrega» del candidato, con su fecha de entrega y una línea de cámara por esa cantidad.**  
    *InfoPonia repite los pasos 5-6 con el candidato siguiente mientras a la partida le quede stock libre.*
7.  **InfoPonia determina que el detalle ya no tiene cantidad sin cubrir y lo pasa a «abierto». Como la venta ya no tiene detalles pendientes, la pasa a «abierta».**
8.  **InfoPonia verifica que no cambiaron el stock libre de la partida ni la cantidad sin cubrir y el estado de los candidatos. Luego, en una única transacción, registra las reservas y sus líneas, los cambios de estado del detalle y de la venta, y la auditoría correspondiente.**
9.  **Como todas las reservas de la venta están «lista para entrega», InfoPonia dispara COM-PNF-ENT · Planificar Entrega.**
10. **InfoPonia notifica la asignación al Vendedor del contrato y al Agrónomo del invernadero de la partida.**
11. **InfoPonia envía al cliente un correo que le informa que el faltante quedó cubierto y que ya no necesita decidir.**

**Extensiones (o Flujos Alternativos)**

***a. En cualquier momento antes de confirmar el registro (paso 8), InfoPonia falla:**

1.  InfoPonia revierte cualquier registro parcial de la partida en curso. Las partidas ya registradas del mismo disparo se conservan.
2.  El disparo queda pendiente. Al restablecerse, InfoPonia retoma la asignación desde el paso 2, con los datos vigentes.

**1a. El disparo afecta a varias partidas (por ejemplo, el rechazo de un detalle con varias líneas de cámara):**

1.  InfoPonia procesa las partidas de a una, de la que vence antes a la que vence después; si empatan, la de menor identificador.
2.  Cada partida sigue el caso de uso desde el paso 2, con su propia transacción.

**1b. El disparo es la liberación de una línea de cámara:**

1.  InfoPonia toma la partida a la que apuntaba la línea liberada.
2.  El caso de uso continúa en el paso 2.

**2a. La partida ya no es asignable (está agotada o vencida, su fecha límite es anterior a la fecha actual, o su stock libre es cero porque otra operación lo tomó):**

1.  InfoPonia no registra ningún cambio ni envía ningún aviso.
2.  El caso de uso termina para esa partida.

**3a. No hay candidatos:**

1.  InfoPonia no registra ningún cambio ni envía ningún aviso. La partida queda con su stock libre (postcondición i).
2.  El caso de uso termina para esa partida.

**4a. Varios candidatos tienen la misma fecha de entrega:**

1.  InfoPonia ubica primero los períodos de suministro y después los detalles de venta.
2.  Si siguen empatados, ubica primero el del contrato realizado antes y, por último, el de menor identificador.

**5a. El stock libre de la partida no alcanza para la cantidad sin cubrir del candidato (cobertura parcial):**

1.  InfoPonia reserva todo el stock libre de la partida para ese candidato, que conserva la diferencia como cantidad sin cubrir.
2.  Si el candidato es un detalle «pendiente de decisión del cliente», sigue pendiente: la cantidad disponible que ve el cliente en el enlace aumenta, pero no se le envía correo.
3.  El caso de uso continúa en el paso 8. En el paso 10, la notificación al Vendedor indica la cantidad que sigue sin cubrir.

**6a. Después de cubrir a todos los candidatos, a la partida le queda stock libre:**

1.  El stock que sobra queda libre en la partida.
2.  El caso de uso continúa en el paso 7.

**7a. El candidato cubierto es un detalle «abierto» o un período de suministro:**

1.  InfoPonia no cambia el estado del detalle ni del contrato.
2.  El caso de uso continúa en el paso 8. En el paso 11 no se envía correo al cliente.

**7b. La venta conserva otros detalles «pendiente de decisión del cliente»:**

1.  InfoPonia pasa a «abierto» el detalle cubierto, pero la venta sigue en «pendiente de decisión del cliente». El enlace sigue sirviendo para los detalles que quedan pendientes.
2.  El caso de uso continúa en el paso 8. En el paso 9 no se dispara COM-PNF-ENT.

**8a. Al registrar, otra operación simultánea cambió el stock libre de la partida, o la cantidad sin cubrir o el estado de un candidato (por ejemplo, una decisión del cliente, una merma en cámara, una cancelación o PROD-ASG-STK):**

1.  InfoPonia descarta la asignación calculada y la recalcula una sola vez, desde el paso 2, con los datos vigentes y dentro de la misma transacción.
2.  Si el conflicto se repite, InfoPonia no registra ningún cambio y el disparo queda pendiente, como en la extensión *a.

**9a. La venta o el período todavía tiene alguna reserva que no está «lista para entrega» (por ejemplo, con una cosecha «a realizar»):**

1.  InfoPonia no dispara COM-PNF-ENT. Se dispara cuando la última reserva quede lista (disparadores 1 y 2 de COM-PNF-ENT).
2.  El caso de uso continúa en el paso 10.

**10a. Las reservas creadas son de varios contratos:**

1.  InfoPonia envía una notificación al Vendedor de cada contrato, solo con lo de ese contrato.
2.  Al Agrónomo le envía una única notificación por partida, con todos los contratos.

**10b. El invernadero de la partida no tiene Agrónomo:**

1.  InfoPonia notifica solo a los Vendedores.

**11a. El cliente no tiene correo:**

1.  InfoPonia no envía el correo. La notificación al Vendedor del paso 10 indica que el detalle dejó de estar pendiente y que el cliente no tiene correo, para que se lo informe él.

**10-11a. InfoPonia no logra entregar una notificación o el correo al cliente:**

1.  Las reservas y los cambios de estado permanecen registrados.
2.  InfoPonia reintenta el envío.

**Requisitos especiales**

  - Se ejecuta en segundo plano, inmediatamente después de que el caso de uso que lo dispara confirma su transacción, sin demorar la operación del usuario.
  - Las reservas quedan registradas y notificadas en no más de 30 segundos desde el disparo.
  - La asignación de cada partida se ejecuta como una única transacción.
  - El control de concurrencia sobre el stock libre de las partidas y sobre los detalles de contrato impide que una misma partida se asigne dos veces, o que un detalle se cubra de más, entre esta asignación, PROD-ASG-STK, las ventas y suministros que se registran, las decisiones del cliente, las mermas en cámara y las cancelaciones simultáneas. Dos asignaciones de la misma partida se ejecutan de a una. Ante un conflicto, la asignación se recalcula una sola vez (extensión 8a).
  - Las notificaciones se presentan dentro del Sistema y pueden, además, enviarse por correo electrónico.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un proceso automático.

**Reglas de negocio**

  - **Qué es:** cuando queda en la cámara stock libre, InfoPonia lo reserva para los contratos que esperan esa variedad, antes de que pierda su aptitud comercial. (Regla 17 de 8.8; todo el caso de uso)
  - **Cuándo se ejecuta:** al ingresar producto a la cámara (regla 28 de 8.6) o al liberarse una línea de cámara, en una transacción propia, inmediatamente después de que el caso de uso que lo dispara confirma la suya. (Regla 17 de 8.8; disparadores)
  - **Partida asignable:** en estado «disponible», con fecha límite igual o posterior a la fecha actual y con stock libre mayor que cero. Stock libre de una partida = cantidad disponible − Σ cantidad reservada de sus líneas cuya reserva está «activa» o «lista para entrega». (Regla 10 de 8.6; paso 2 y extensión 2a)
  - **Candidato:** cumple todas estas condiciones. (Paso 3 y extensión 3a)
      
      - es un detalle de venta «abierto» o «pendiente de decisión del cliente» de una venta «abierta» o «pendiente de decisión del cliente», o un período de un detalle de suministro «vigente» de un suministro vigente. Un detalle «confirmado» o «rechazado» no tiene cantidad sin cubrir (regla 10 de 8.8);
      - en un suministro, la fecha del período cae dentro de la ventana de pre-reserva: no es posterior a la fecha actual más díasPreReservaSuministro (regla 16 de 8.8);
      - es de la variedad de la partida, es decir, de la variedad de su lote de origen;
      - su fecha de entrega (la fecha pactada de la venta o la fecha del período) no es posterior a la fecha límite de la partida (regla 17 de 8.8);
      - su contrato admite el invernadero de la partida: en una compra-venta con retiro, si es el invernadero de retiro; en una compra-venta con envío y en un suministro, si es uno de los invernaderos del Vendedor del contrato (regla 7 de 8.6; regla 5 de 8.8);
      - no tiene un detalle de entrega en una entrega no cancelada;
      - tiene cantidad sin cubrir mayor que cero.
  - **Cantidad sin cubrir:** cantidad pedida (la cantidad solicitada del detalle de venta o la cantidad del período) − Σ cantidad cubierta de las líneas de sus reservas no liberadas. (Reglas 9 y 10 de 8.8; paso 5)
  - **Orden de prioridad:** primero la fecha de entrega más próxima. Si empatan, primero los períodos de suministro, después el contrato realizado antes y, por último, el de menor identificador. Así la asignación es siempre la misma ante los mismos datos. (Regla 17 de 8.8; paso 4 y extensión 4a)
  - **Cantidad a reservar:** la menor entre el stock libre que le queda a la partida y la cantidad sin cubrir del candidato. Siempre se reserva lo disponible, aunque no alcance (cobertura parcial). (Regla 17 de 8.8; paso 5 y extensión 5a)
  - **Reserva creada:** una por cada candidato cubierto y por cada partida, con una sola línea de cámara, en estado «lista para entrega» y con la fecha de entrega del candidato. Toma su stock de un único invernadero, el de la partida. No se agregan líneas a reservas existentes. (Reglas 5, 8 y 12 de 8.6; reglas 1 y 17 de 8.8; paso 6)
  - **Sin cosecha ni descuento de stock:** la reserva no tiene orden de cosecha, porque todo su stock ya está cosechado. Reservar no modifica la cantidad disponible de la partida ni registra movimientos de stock: la partida baja recién al entregar (regla 30 de 8.6). Tampoco hay asientos. (Paso 8)
  - **Fecha de entrega pasada:** un candidato cuya fecha de entrega ya pasó sigue siendo candidato, porque la entrega se debe. COM-PNF-ENT la programa para la fecha actual y avisa el retraso (extensión 3a de COM-PNF-ENT). (Paso 3)
  - **Detalle que deja de estar pendiente:** un detalle «pendiente de decisión del cliente» que queda sin cantidad sin cubrir vuelve a «abierto» y se le informa al cliente (regla 17 de 8.8). La venta vuelve a «abierta» cuando ya no tiene detalles pendientes (regla 21 de 8.6). La fecha en que el detalle pasó a pendiente se conserva como historial. (Paso 7 y extensión 7b)
  - **Detalle pendiente cubierto en parte:** sigue pendiente, y su cantidad disponible aumenta en lo reservado. El cliente la ve actualizada al abrir el enlace (extensión 6b de COM-DCD-FLT). No se le envía correo. (Extensión 5a)
  - **Planificación de la entrega:** si la asignación deja listas para entrega todas las reservas de una venta o de un período, InfoPonia dispara COM-PNF-ENT. (Regla 24 de 8.6; paso 9 y extensión 9a)
  - **Avisos:** (Pasos 10 y 11, extensiones 10a, 10b y 11a)
      
      - al Vendedor de cada contrato que recibió reservas, y al Agrónomo del invernadero de la partida, si lo tiene (regla 17 de 8.8);
      - al cliente, solo cuando un detalle deja de estar pendiente, y si tiene correo;
      - no se avisa al Capataz, porque no hay nada que cosechar;
      - si no se asignó nada, no hay avisos.

**Lista de tecnología y variaciones de datos**

  - **2–6.** Las cantidades se expresan en plantas, como números enteros.
  - **10.** La notificación al Vendedor indica el contrato, el cliente, la variedad, la cantidad reservada desde la cámara, la fecha de entrega, la cantidad que sigue sin cubrir y, si corresponde, que el detalle dejó de estar pendiente (y si el cliente no tiene correo).
  - **10.** La notificación al Agrónomo indica la partida, su fecha límite, los contratos con su cantidad reservada y su fecha de entrega, y el stock libre que le queda a la partida.
  - **11.** El correo al cliente indica la venta, la variedad, la cantidad que recibirá, la fecha pactada y que ya no necesita decidir sobre el faltante de ese producto.

**Frecuencia**

Cada vez que ingresa producto a la cámara o se libera una línea de cámara. Depende de los excedentes de cosecha, las cosechas sin contrato, los rechazos, las devoluciones y las cancelaciones. Se estima que varias veces por semana en cada invernadero. A confirmar con el Jardín Botánico.

**Temas abiertos**

  - **Sin ejecución diaria:** a diferencia de COM-PNF-ENT, este caso de uso no tiene una recuperación diaria. Si una partida queda con stock libre y después aparece un detalle con faltante (por ejemplo, al cancelarse una cosecha), lo tiene que cubrir el caso de uso que genera ese faltante, con PROD-ASG-STK, que toma primero la cámara. Hay que verificarlo al especificar Cancelar Orden (CU-11) y Planificar Cosecha por Contrato.
  - **Reemplazar una cosecha pendiente por stock de cámara:** la regla 17 de 8.8 solo cubre la cantidad sin cubrir. Si en la cámara hay una partida por vencer y, para la misma variedad, una cosecha «a realizar» con contrato, la partida puede vencer igual mientras se cosecha el lote. ¿Conviene que InfoPonia libere esa cosecha y use la cámara?
  - **Ventana de pre-reserva:** limitar los suministros a los períodos dentro de la ventana es una propuesta de esta versión (ver «Situaciones encontradas»). Hay que confirmarla.

**Situaciones encontradas y propuestas (versión 0.1)**

  - **1. La regla 17 de 8.8 no limita los invernaderos.**  
      - **Situación:** la regla busca los detalles de la variedad sin mirar de qué invernadero es la partida. En cambio, la regla 7 de 8.6 y la regla 5 de 8.8 limitan toda asignación de stock: en un retiro, solo el invernadero de retiro; en un envío y en un suministro, solo los invernaderos del Vendedor del contrato.
      - **Propuesta:** un detalle es candidato solo si su contrato admite el invernadero de la partida (regla «Candidato»).
      - **Por qué:** si no, una venta con retiro podría recibir producto de otro invernadero, y no podría entregarse en una sola entrega en el invernadero de retiro (supuesto 4 de 8.7). Además, la cámara quedaría con más derechos que los lotes, cuando PROD-ASG-STK trata igual a los dos.
  - **2. Períodos de suministro fuera de la ventana de pre-reserva.**  
      - **Situación:** la regla 17 de 8.8 no pone un límite a los períodos. Pero la regla 16 de 8.8 crea la reserva de un período solo si «no tiene reserva». Si la cámara le reserva una parte a un período lejano, la pre-reserva después lo encuentra con reserva y no cubre el resto.
      - **Propuesta:** solo son candidatos los períodos cuya fecha cae dentro de la ventana de pre-reserva (fecha actual + díasPreReservaSuministro).
      - **Por qué:** evita ese hueco en la regla 16, respeta la política de la pre-reserva (no comprometer stock con mucha anticipación) y deja el stock perecedero para las entregas más cercanas.
  - **3. Detalles que ya tienen entrega.**  
      - **Situación:** una reserva «entregada» no está liberada, así que cuenta en la cantidad cubierta (regla 10 de 8.8). Un período de suministro que se entregó con faltante (regla 17 de 8.6) sigue teniendo cantidad sin cubrir, y la regla 17 de 8.8 le reservaría stock a una entrega que ya ocurrió.
      - **Propuesta:** no es candidato un detalle o un período que ya tiene un detalle de entrega en una entrega no cancelada, sea «a realizar» o concretada.
      - **Por qué:** si la entrega está concretada, el faltante ya se trata con la discrepancia o la queja (regla 17 de 8.6). Si está «a realizar», el cliente ya recibió el correo con las cantidades y el Agrónomo puede haber planificado el envasado. Sumarle una reserva obligaría a rehacer la entrega, y una venta con retiro se entrega en una sola entrega.
  - **4. Desempates no definidos.**  
      - **Situación:** la regla 17 de 8.8 ordena por fecha de entrega, pero no dice qué pasa si dos candidatos tienen la misma fecha.
      - **Propuesta:** primero los períodos de suministro, después el contrato realizado antes y, por último, el menor identificador (extensión 4a).
      - **Por qué:** la asignación queda determinista, igual que la selección del transportista en COM-PNF-ENT. Dar prioridad al suministro es coherente con la regla 8 de 8.9, que protege a los suministros al recortar reservas de cámara, porque su incumplimiento genera indemnizaciones.
  - **5. Momento de ejecución.**  
      - **Situación:** la regla 17 de 8.8 dice que se ejecuta «en el momento del evento», pero COM-DCD-FLT dispara la asignación después de confirmar su transacción (requisitos especiales de COM-DCD-FLT).
      - **Propuesta:** se ejecuta en una transacción propia, inmediatamente después de que el caso de uso que la dispara confirma la suya.
      - **Por qué:** si corriera dentro de la transacción del otro caso de uso, una falla en la asignación revertiría, por ejemplo, la decisión del cliente o la concreción de una cosecha, que no dependen de ella. Así lo trata también PROD-ASG-STK («Relacionados, sin inclusión»).
  - **6. Detalle pendiente cubierto en parte.**  
      - **Situación:** la regla 17 de 8.8 solo dice que se informa al cliente cuando el detalle «queda cubierto».
      - **Propuesta:** si se cubre solo una parte, el detalle sigue pendiente, la cantidad disponible aumenta y no se le envía correo al cliente. Sí se notifica al Vendedor.
      - **Por qué:** el cliente ve la cantidad actualizada cada vez que abre el enlace (extensión 6b de COM-DCD-FLT), y así no recibe un correo por cada partida que ingresa.
  - **7. Término «pedido» en el glosario.**  
      - **Situación:** el glosario define «Asignación automática de cámara» como la asignación «a los pedidos de la misma variedad», y el término «InfoPonia» habla de «asignar producto en cámara a un pedido». Pero en el glosario un Pedido es la solicitud de cotización de insumos del Agrónomo.
      - **Propuesta:** reemplazar «pedidos» por «detalles de compra-venta y períodos de suministro con cantidad sin cubrir», y agregar que solo se consideran los invernaderos que admite el contrato (situación 1). Va a pendientes_MD.
      - **Por qué:** el glosario define cada término del proyecto, y usar «pedido» con otro sentido lleva a confundir el módulo Comercial con el de Compras.

**Cambios pendientes aplicados en este caso de uso**

  - **MD-87 (pendientes_MD, «Decidido sin aplicar»):** un invernadero puede no tener Agrónomo (R051 pasa a 0..1). Por eso la notificación al Agrónomo es «si el invernadero tiene uno» (postcondición f y extensión 10b).

## PROD-VNC-CAM · Vencer Partidas en Cámara

Caso de uso nuevo del módulo de producción (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Reemplaza al caso 33 de PCU. Decisiones del 20/11/2026 aplicadas: una partida vence cuando su fecha límite es anterior a hoy (F); el producto reservado se trata como una merma en cámara con producto reservado (G); se incluye el aviso previo al vencimiento (H; MD-134).

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Producción / Cámara.

**Versión:** 0.1

**Actor principal:** InfoPonia (proceso automático).

**Personal involucrado e intereses**

  - **Agrónomo:** quiere enterarse antes de que una partida venza y que lo vencido salga del stock sin trabajo manual.
  - **Vendedor:** quiere saber qué partidas están por vencer, para ofrecerlas, y si una entrega suya pierde producto.
  - **Gerente:** quiere que la pérdida quede valorizada y asentada, y bajar la merma.
  - **Cliente:** quiere no recibir producto vencido.

**Relaciones con otros casos de uso**

  - **Incluye («include»):** PROD-CNL-ORD · Cancelar Orden, para una entrega que queda vacía; PROD-ASG-STK · Asignar Stock Maduro, para volver a cubrir un detalle afectado.
  - **Relacionados:** PROD-REG-MRM · Registrar Merma, que trata igual una merma en cámara con producto reservado; COM-PNF-ENT, que planifica en la misma ejecución lo que se vuelva a cubrir.

**Disparador:** la ejecución diaria de InfoPonia, en su paso 1 (T-04).

**Precondiciones**

a. Existe la Configuración Operativa con los días de aviso de vencimiento (MD-134).

**Garantías mínimas**

  - Cada partida es atómica: si falla una, no queda nada parcial de esa partida y las demás siguen.
  - Ninguna partida vencida sigue disponible ni reservada, y ninguna entrega sale con producto vencido.
  - Ninguna partida genera más de una merma por vencimiento ni más de un aviso previo.

**Garantías de éxito (Postcondiciones)**

Por cada partida que venció:

a. Se registró una merma con causa «vencimiento en cámara», por la cantidad disponible, asociada a la partida y a su lote de origen (regla 3 de 8.9), con su movimiento de tipo «merma en cámara».

b. Se registró el asiento Debe Pérdidas por Mermas / Haber Productos Terminados, por la cantidad por el costo unitario de la partida (regla 33 de 8.6).

c. La partida quedó «vencida», con cantidad disponible 0.

d. Si tenía líneas reservadas: las líneas se recortaron a 0 y las reservas sin cobertura pasaron a «liberadas»; las líneas se quitaron de su entrega «a realizar» y la entrega que quedó vacía se canceló (PROD-CNL-ORD); para cada detalle afectado se intentó una reserva nueva (PROD-ASG-STK, con cosecha según la regla 3 de 8.11) y lo no cubierto siguió el camino de faltante (reglas 16 y 17 de 8.6); se generó la alerta de merma en cámara con producto reservado al Agrónomo y se notificó al Vendedor de cada contrato afectado (regla 8 de 8.9).

e. Si la partida tenía activa la alerta «partida por vencer», quedó resuelta.

Por cada partida que entró en el plazo de aviso:

f. Se generó la alerta «partida por vencer» al Agrónomo del invernadero, con variedad, cantidad libre, fecha límite y días que faltan, y se notificó al Vendedor del invernadero (MD-134).

En todos los casos:

g. Se creó un log de auditoría por partida, con origen InfoPonia.

**Escenario principal de éxito (o Flujo Básico)**

(Una partida vence sin producto reservado.)

1.  InfoPonia inicia el paso 1 de la ejecución diaria.
2.  InfoPonia busca las partidas «disponibles» con fecha límite anterior a la fecha actual.
3.  Para cada una, registra la merma, el movimiento, el asiento y el estado «vencida», resuelve su alerta «partida por vencer» si la tenía y registra la auditoría.

*InfoPonia repite el paso 3 por cada partida vencida.*

4.  InfoPonia busca las partidas «disponibles», con stock libre mayor que 0, que vencen dentro del plazo de aviso y no tienen la alerta «partida por vencer».
5.  Para cada una, genera la alerta y la notificación.
6.  InfoPonia termina el paso 1 y la ejecución continúa con el vencimiento de pagos.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento InfoPonia falla:**

1.  InfoPonia revierte la partida en curso; las ya registradas se conservan y en la próxima ejecución se retoman las pendientes.

**2a. No hay partidas vencidas:**

1.  InfoPonia continúa en el paso 4.

**3a. La partida vencida tiene líneas reservadas:**

1.  En la misma transacción, InfoPonia recorta las líneas, libera las reservas sin cobertura, quita las líneas de su entrega «a realizar» y cancela la entrega que quede vacía (PROD-CNL-ORD).
2.  Para cada detalle afectado, ejecuta PROD-ASG-STK por la cantidad que quedó sin cubrir, con la fecha de entrega de la reserva liberada.
3.  **3a.2a.** El stock no alcanza: lo sin cubrir sigue el camino de faltante; en una compra-venta, el detalle pasa a «pendiente de decisión del cliente» (regla 16 de 8.6); en un suministro, se entrega lo disponible (regla 17 de 8.6).
4.  InfoPonia genera la alerta de merma en cámara con producto reservado y notifica al Vendedor.

**3b. La partida vencida tiene líneas en una entrega en curso:**

1.  No debería ocurrir, porque la ejecución diaria corre antes de que empiece cualquier ruta del día. Si ocurre, InfoPonia deja esa partida para la próxima ejecución y genera una alerta al Gerente.

**4a. Los días de aviso valen 0:**

1.  No se generan avisos previos.

**5a. InfoPonia no logra enviar una notificación:**

1.  El registro se conserva y InfoPonia reintenta el envío.

**Requisitos especiales**

  - Cada partida se registra en su propia transacción, con su asiento y lo que se incluye.
  - El proceso se serializa con la asignación de stock, la planificación de entregas y el registro de mermas sobre las mismas partidas.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican que el origen es InfoPonia.

**Reglas de negocio**

  - **Partida vencida:** su fecha límite es anterior a la fecha actual; el día de la fecha límite todavía se puede entregar (regla 17 de 8.8). (Paso 2)
  - **Merma por vencimiento:** una por partida, por toda la cantidad disponible, con la causa «vencimiento en cámara», que solo usa este proceso (regla 4 de 8.9), asociada al lote de origen. (Paso 3)
  - **Asiento:** Debe Pérdidas por Mermas / Haber Productos Terminados, por la cantidad por el costo unitario de la partida, originado en la merma (regla 33 de 8.6). (Postcondición b)
  - **Producto reservado:** se trata como una merma en cámara con producto reservado: se recortan las líneas, se liberan las reservas sin cobertura, se ajustan o cancelan sus entregas, se intenta volver a cubrir y lo no cubierto sigue el camino de faltante (reglas 6 y 8 de 8.9). (Extensión 3a)
  - **Aviso previo:** una sola vez por partida disponible con stock libre, cuando faltan los días de aviso o menos para su fecha límite; al Agrónomo del invernadero, con notificación al Vendedor del invernadero para que pueda ofrecerla. Se resuelve cuando la partida se agota o vence. (Pasos 4 y 5)
  - **Orden:** es el primer paso de la ejecución diaria, para que ningún paso siguiente reserve ni planifique producto vencido.

**Lista de tecnología y variaciones de datos**

  - **Paso 3.** El importe del asiento se redondea a 2 decimales.

**Frecuencia:** una vez por día.

**Temas abiertos**

  - Confirmar con el Jardín Botánico el valor inicial de los días de aviso (propuesta: 3).

## Cambios ya decididos que se aplican (PCU, secciones 6, 7 y 12; MD-126, MD-127, MD-134)

1. **PROD-ASG-CAM, paso 3: el detalle de suministro tiene que estar vigente** (PCU 6, MD-126). Ya lo dice la regla «Candidato» de la versión
   0.1. Con D-64 punto 8: también un período de un detalle **finalizado** cuya fecha no supera su fecha de fin.
2. **PROD-ASG-CAM: la ventana de pre-reserva queda confirmada** (PCU 7) y su tema abierto «Ventana de pre-reserva» se quita; las situaciones 1 a
   4 son MD-127 (decidido sin aplicar). La situación 7 (término «pedido» del glosario) va a «GLO · Cambios para el Glosario».
3. **Ejecución diaria única** (PCU 12, T-04): PROD-VNC-CAM es el primer paso del negocio comercial. En el código es el **paso 20** (D-56, con
   la numeración de 10 en 10; el 10 es el de insumos) y lo registra `comercial` (D-59).
4. **Aviso previo** (MD-134): `dias_aviso_vencimiento_camara` en la configuración operativa (entero ≥ 0, inicial 3; 0 lo desactiva) y la
   alerta «partida por vencer» (D-64 punto 10).
5. **En el documento de Drive de PROD-VNC-CAM** los pasos que siguen a «InfoPonia repite el paso 3» se numeran otra vez desde 1; la extensión
   5a cita el paso 5. Esta copia los numera 4 a 6.

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57, D-59, D-64)

**El código va en `comercial`** (D-59, A3): los dos casos de uso crean o recortan reservas. `comercial/servicios/camara.py`. Lo físico, con el
núcleo de `produccion` (`camara.crear_partida`, `camara.vencer_partida`; `docs/api/produccion.md`, sección 8). **Fuera de esta ronda ·
contabilidad** (D-57): la postcondición b de PROD-VNC-CAM (asiento) y la regla «Asiento». **Se completa en COM-05:** todo lo de entregas
(«sin entrega» de la regla «Candidato» de PROD-ASG-CAM; el paso 9 de PROD-ASG-CAM, COM-PNF-ENT; quitar líneas de una entrega «a realizar» y
cancelar la entrega vacía, postcondición d y extensión 3a de PROD-VNC-CAM). **Se completa en COM-06:** la extensión 3b de PROD-VNC-CAM (entrega
en curso).

### PROD-ASG-CAM · Asignar Stock de Cámara

- **Entrada:** `asignar_camara(partida_ids)`. La llaman, siempre con `transaction.on_commit` (D-64 punto 9): PROD-CNC-CSC (las partidas que
  crea), COM-DCD-FLT (las del rechazo) y PROD-CNL-ORD (las partidas de las líneas de cámara de la reserva liberada); desde COM-05 y COM-06,
  sus casos de uso. **Paso diario 25** (`reasignar_camara`, «Reasignar cámara»): toda partida «disponible», con `fecha_limite >= hoy` y stock
  libre > 0, en el mismo orden (recupera una asignación que falló, garantía mínima 2).
- **1a:** de a una, por `fecha_limite` y después `id`; cada partida en su transacción. Si una falla, se registra en el log
  (`logger.exception` con el id de la partida) y siguen las demás; la recupera el paso 25.
- **Paso 2 y 2a:** partida «disponible», `fecha_limite >= hoy`, stock libre > 0 (releída después de bloquear).
- **Candidatos (paso 3, regla «Candidato»):**
  - detalle de venta «abierto» o «pendiente de decisión del cliente» de una venta «abierta» o «pendiente de decisión del cliente» (un
    detalle «confirmado», «rechazado» o «cancelado» no tiene cantidad sin cubrir);
  - período de un detalle de suministro que tiene cantidad sin cubrir (sección 7 del patrón de stock, con D-64 punto 8), de un suministro
    «vigente», con `fecha <= hoy + dias_pre_reserva_suministro` (la ventana). Un período **anterior** a hoy sigue siendo candidato («Fecha de
    entrega pasada»), pero solo los del calendario desde la fecha de primera entrega;
  - de la variedad del lote de la partida; con fecha de entrega `<= fecha_limite` de la partida;
  - cuyo contrato admite el invernadero de la partida: retiro → el de retiro; envío y suministro → un invernadero **activo** del Vendedor
    **actual** del contrato (D-60);
  - «sin detalle de entrega en una entrega no cancelada»: **se completa en COM-05** (en COM-04 no hay entregas);
  - con cantidad sin cubrir > 0.
  Una consulta por tabla (`sin_cubrir_de_periodos` y su equivalente para detalles de venta), nunca una por candidato.
- **Orden (paso 4, 4a):** fecha de entrega; con la misma fecha, primero los períodos y después los detalles de venta; después el contrato con
  `fecha_realizacion` más antigua; por último el menor `id` (del detalle de venta, o el par `(id del detalle de suministro, fecha)`). Es una
  función pura `orden_de_candidatos(candidatos)` con pruebas de tabla.
- **Reserva (pasos 5 y 6):** `min(libre que queda, sin cubrir)`; una `ReservaStock` «lista para entrega» por candidato, con
  `fecha_reserva` = hoy, `fecha_entrega_reserva` = la del candidato, el invernadero de la partida y una sola `DetalleReserva` de partida;
  sin cosecha. No se agregan líneas a reservas existentes.
- **Paso 7 (7a, 7b):** un detalle «pendiente de decisión del cliente» que queda sin cantidad sin cubrir pasa a «abierto» (su
  `fecha_pendiente_decision` se conserva); su venta, a «abierta» si no le queda otro pendiente, y su enlace de decisión pasa a `anulado`
  (`anular_enlaces_de`, D-65). Si le quedan pendientes, el enlace sigue sirviendo y muestra la cantidad nueva (5a: sin correo).
- **Bloqueos (paso 8):** por partida, en el orden del patrón: las cuentas (los Vendedores de los contratos candidatos y el Agrónomo del
  invernadero) → el invernadero de la partida → la variedad → **la partida** → los contratos, sus detalles y sus enlaces, releídos. Con la
  partida bloqueada no hace falta la 8a (sección 3 del patrón): el cálculo se hace sobre lo vigente.
- **Avisos (pasos 10 y 11, 10a, 10b, 11a):** dentro de la transacción (D-42): al Vendedor de cada contrato, uno por contrato («Stock de cámara
  para CV-0044», con la variedad, lo reservado, la fecha de entrega y lo que sigue sin cubrir; «el detalle dejó de estar pendiente» y, si el
  cliente no tiene correo, «avisale vos»); al Agrónomo del invernadero, uno por partida con todos los contratos. El correo al cliente («el
  faltante quedó cubierto», 11) con `transaction.on_commit`, solo si el detalle dejó de estar pendiente y el cliente tiene correo. El
  reintento (10-11a) no aplica: no hay cola.
- **Auditoría (h):** un registro por partida, acción nueva `asignacion_camara`, actor `None` (InfoPonia), con las reservas, las líneas, los
  detalles y las ventas que cambiaron de estado y los enlaces anulados.
- **Sin asignación (i):** nada que registrar, ni auditoría ni avisos.

### PROD-VNC-CAM · Vencer Partidas en Cámara (paso diario 20)

- **Entrada:** `vencer_partidas_en_camara(hoy) -> ResumenDePaso`, registrado en `ComercialConfig.ready()` con
  `registrar_paso_diario("vencer_partidas_en_camara", "Vencer partidas en cámara", 20, …)` (D-56; D-59 lo pasó a `comercial`). Contrato del
  paso: idempotente, una transacción por partida, nunca lee la fecha por su cuenta.
- **Paso 2:** partidas «disponibles» con `fecha_limite < hoy` (el día de la fecha límite todavía se entrega). Por cada una, en su transacción:
  1. bloqueos (se leen antes, sin bloquear, los contratos con líneas en la partida): las cuentas (sus Vendedores y el Agrónomo) → el
     invernadero de la partida **y los invernaderos considerados de esos contratos** (para volver a cubrir), juntos en orden de id → la
     variedad → los sectores y lotes candidatos → las partidas candidatas (con esta) → sus reservas y líneas, los detalles, los contratos y sus
     enlaces; relectura (si ya no está «disponible», se saltea; si aparecieron contratos nuevos con líneas, se repite la lectura una vez);
  2. **3a, si tiene líneas en reservas «activas» o «lista para entrega»:** todas se recortan a 0 (la disponible va a 0), con
     `orden_de_recorte` (`docs/patrones/stock_maduro.md`, sección 8) solo para el orden de los avisos y de la auditoría; cada reserva cuyo
     cubierto queda en 0 pasa a «liberada». Por cada detalle o período afectado, con lo recortado de **ese** detalle:
     - detalle de venta «abierto» de una venta «abierta», o período: `stock_maduro.asignar(None, …, lo recortado, fecha_entrega_reserva, …)`
       y lo no cubierto por el camino de faltante (3a.2, 3a.2a);
     - detalle «pendiente de decisión del cliente»: no se llama a `asignar` (precondición b de PROD-ASG-STK); suma al faltante por el camino de
       faltante, como 8d de PROD-CNL-ORD (fecha de pendiente nueva y enlace nuevo con las cantidades actualizadas);
     - detalle «confirmado» (el cliente ya aceptó una cantidad): `asignar` por lo perdido (con la cantidad aceptada como pedida) y, si no
       alcanza, vuelve a «pendiente de decisión del cliente» con `cant_entregada_venta` vacía y enlace nuevo (D-64 punto 13);
  3. `camara.vencer_partida(partida, hoy)` (a, c): merma «vencimiento en cámara» por la disponible que quedaba, sin responsable (InfoPonia),
     movimiento «merma en cámara» y la partida «vencida»;
  4. si tenía líneas reservadas, la alerta `comercial_merma_camara_reservada` (`crear_alerta_de_evento`, enlazada a la merma con
     `produccion.AlertaDeMerma`), «Venció la partida P-12 (Lechuga Crespa) con 30 plantas reservadas para CV-0044 y SUM-0003», y la
     notificación al Vendedor de cada contrato afectado (3a.4, regla 8 de 8.9);
  5. la alerta «partida por vencer» de la partida, si estaba activa, pasa a resuelta (e);
  6. un registro de auditoría `vencimiento_partida` (g), actor `None`, con la merma, el movimiento, la partida, las líneas recortadas, las
     reservas liberadas, lo que creó `asignar` y el camino de faltante.
- **Pasos 4 y 5 (aviso previo):** con `dias = configuracion.obtener().dias_aviso_vencimiento_camara`; si es 0, nada (4a). Partidas
  «disponibles» con stock libre > 0 y `hoy <= fecha_limite <= hoy + dias`: por cada una, en su transacción (invernadero → partida),
  `asegurar_alerta_de_estado(invernadero, "comercial_partida_por_vencer", clave=f"partida:{id}", descripcion=…)`; si la creó (no estaba),
  el `AlertaComercial(partida=…)`, la notificación al Vendedor del invernadero (si tiene uno activo) y un registro de auditoría
  `aviso_partida_por_vencer`. Descripción: «Lechuga Crespa · P-12: 40 plantas libres vencen el 25/11/2026 (en 2 días)». Una partida que
  ya tiene la alerta no se vuelve a avisar.
- **Resolución de «partida por vencer»** fuera de este paso: cuando la partida se agota (merma en cámara de PROD-REG-MRM en COM-04; entrega en
  COM-06). Una función de `comercial`, `resolver_aviso_de_partida(partida)`, que llama todo caso de uso que agota una partida.
- **Resumen del paso:** `ResumenDePaso(procesados=partidas vencidas, creados=avisos nuevos, resueltos=alertas resueltas, detalle="N partidas
  con producto reservado")`.
- **\*a:** cada partida en su transacción; si una falla, `logger.exception` y siguen las demás; al día siguiente se retoma (sigue
  «disponible» y vencida).
- **5a:** no aplica (D-42).

### Pestaña «Cámara» de la ficha del invernadero

- La registra `comercial` con `registrar_pestana_de_invernadero("camara", "Cámara", …)` (disparador «Cuando exista Lote, OrdenTrabajo o
  StockCosechado»), porque lo reservado es de `comercial`; los datos de la partida, con `camara.partidas_del_invernadero` de `produccion`.
- La ven el Gerente, el Agrónomo a cargo, el Capataz asignado y el Vendedor del invernadero (los cuatro necesitan saber qué hay: el Vendedor
  para ofrecerlo, MD-134); `None` para los demás. Solo consulta (`camaraTab`: «las partidas entran con las cosechas y salen con las
  entregas»).
- Contenido (`tabCamara`): tres indicadores (partidas disponibles y plantas; plantas libres; por vencer en `dias_aviso_vencimiento_camara`
  días o menos) y la tabla de partidas (código `P-12`, variedad, lote y motivo, ingreso, fecha límite, disponible, reservado, libre y estado:
  «Disponible», «Vence el …» o «Vencida» con la merma por vencimiento). Disponibles primero, por fecha límite; después las agotadas y
  vencidas de los últimos 30 días (para que la tabla no crezca sin fin; las demás quedan en la bitácora y en la auditoría). Sin consultas
  por fila.
- La campana: «partida por vencer» lleva a esta pestaña (Agrónomo, Gerente) con `registrar_enlace_de_alerta` (D-62); «merma en cámara con
  producto reservado», a la ficha del contrato para el Gerente y a esta pestaña para el Agrónomo.

### Configuración

- `dias_aviso_vencimiento_camara` en la pantalla de MAE-04, grupo «Comercial», con el texto del prototipo (`VIEWS.cfg`: «Aviso de
  vencimiento de cámara», «días antes»), su validación (entero ≥ 0) y su ayuda («0 desactiva el aviso»). Migración propia en `maestros`
  (`docs/patrones/trabajo_en_paralelo.md`, «Migraciones»: el IoT también suma parámetros).

## Pantallas

| Pantalla | Funciones | Notas |
|---|---|---|
| Ficha del invernadero · «Cámara» | `camaraTab`, `tabCamara` | Solo consulta |
| Configuración | `VIEWS.cfg`, `ACT.cfgok` | Solo el parámetro nuevo; la pantalla es de MAE-04 |

### Lo que difiere del prototipo (corregir, D-61)

- `tabCamara` muestra todas las partidas sin orden ni corte: ordenar y limitar las cerradas (arriba).
- `camaraTab` solo tiene datos para el invernadero «A»: en el sistema, los del invernadero de la ficha.
- `VIEWS.cfg` no muestra `dias_vigencia_enlace_faltante` (ya lo notó MAE-04) ni dice que 0 desactiva el aviso.

## Para más adelante

- COM-05: candidatos «sin entrega» de PROD-ASG-CAM; COM-PNF-ENT después de asignar (paso 9); en PROD-VNC-CAM, quitar las líneas de su entrega «a
  realizar» y cancelar la entrega vacía.
- COM-06: la extensión 3b de PROD-VNC-CAM; resolver «partida por vencer» al entregar lo último de una partida; la devolución a una partida
  vencida (regla 29 de 8.6: merma por vencimiento directa).
- Contabilidad (D-57): el asiento de la merma por vencimiento.
- Temas abiertos de PROD-ASG-CAM: reemplazar una cosecha pendiente por stock de cámara que está por vencer (sigue abierto; el paso 25 no lo
  resuelve).
