# Casos de uso · producción · Cosecha

Copia para el repo de tres casos de uso: PROD-PNF-CSC versión 0.4 y PROD-CNC-CSC versión 0.4 de «CU extendidos», y PROD-MOD-CSC versión 0.1
(documento de Drive «CU · PROD-MOD-CSC · Modificar Cosecha (v0.1)», carpeta «InfoPonia · Comercial · Análisis»). Cotejado con pendientes_CU,
con «PCU · Cambios para pendientes_CU (comercial)» (secciones 1 a 16: las 5 y 11 los cambian), con «MD · Cambios para el modelo de dominio
(comercial)» (MD-126, MD-127, MD-131), con el modelo de dominio (reglas 13 a 18 y 28 a 31 de 8.6, 7 a 15 de 8.8, 3 a 10 y 16 de 8.9, 2 a 4 de
8.20) y con el glosario.

Aunque sus códigos empiezan con PROD, **el código va en la app `comercial`** (D-59, regla A3 de D-37): los tres crean o cambian reservas.
Lo físico lo escriben las funciones de núcleo de `produccion` (D-64). Archivos de pruebas: `comercial/tests/test_prod_pnf_csc.py`,
`test_prod_mod_csc.py` y `test_prod_cnc_csc.py`. La merma de las plantas perdidas (extensión 10a de PROD-CNC-CSC) es PROD-REG-MRM
(`docs/casos_de_uso/produccion/merma.md`); la cancelación de una cosecha, PROD-CNL-ORD (`cancelar_orden.md`); el faltante, COM-DCD-FLT
(`docs/casos_de_uso/comercial/faltante.md`).

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: los tres casos de uso no numeran sus reglas (`test_lote_cosechable_…`, `test_detalle_cubrible_…`), sus
postcondiciones son `test_post_<letra>_…` y sus extensiones `test_ext_<numero>_…` (`test_ext_13a_…`).

En el documento de Drive de PROD-MOD-CSC los pasos que siguen a «El Agrónomo repite los pasos 5 y 6» se numeran otra vez desde 1; las
extensiones los citan como 7 a 12. Esta copia los numera 7 a 12 (hay que corregir el documento, `docs/temas_abiertos.md`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-PNF-CSC | Planificar Cosecha | Agrónomo | `comercial/tests/test_prod_pnf_csc.py` |
| PROD-MOD-CSC | Modificar Cosecha | Agrónomo del invernadero | `comercial/tests/test_prod_mod_csc.py` |
| PROD-CNC-CSC | Concretar Cosecha | Capataz asignado | `comercial/tests/test_prod_cnc_csc.py` |

## PROD-PNF-CSC · Planificar Cosecha
**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Producción / Órdenes.

**Actor principal:** Agrónomo.

**Versión**: 0.4

**Personal involucrado e intereses:**

  - **Agrónomo:** quiere planificar la cosecha eligiendo él mismo los lotes, ya sea para cubrir un contrato o para cosechar sin contrato. Necesita información confiable sobre el stock libre de cada lote y sobre la cantidad que cada contrato todavía no tiene cubierta.
  - **Capataz:** quiere recibir una orden clara (qué variedad, de qué lotes, cuántas plantas de cada uno y para qué fecha) y saber que esas plantas no están comprometidas con otra orden.
  - **Vendedor:** quiere que los contratos que gestiona queden cubiertos a tiempo y con producto que llegue a la entrega en condiciones comerciales, y enterarse cuando se planifica una cosecha que cubre uno de sus contratos.
  - **Cliente:** quiere recibir la cantidad pactada en la fecha prometida.
  - **Gerente:** quiere trazabilidad completa de quién planificó qué cosecha, para qué contrato y sobre qué lotes, y que el stock maduro no se comprometa dos veces.
  - **Organización (Jardín Botánico):** quiere aprovechar el stock maduro antes de que se pierda y cumplir los contratos de suministro para evitar quejas e indemnizaciones.

**Relaciones con otros casos de uso:** no incluye («include») otros casos de uso ni es extendido («extend») por ellos.

**Precondiciones:**

a. El Agrónomo está autenticado en el Sistema.

b. El Agrónomo tiene a su cargo al menos un invernadero en estado "activo".

c. Al menos uno de los invernaderos a cargo del Agrónomo tiene un Capataz activo asignado y al menos un lote activo, en la etapa "Maduración", con stock libre mayor que cero.

**Garantías mínimas:**

  - La operación es atómica. Si el caso de uso se cancela o falla, no queda registrada ninguna orden de cosecha, reserva de stock, línea de reserva ni log de auditoría parcial.
  - La cantidad actual de los lotes no se modifica, cualquiera sea la forma en que termine el caso de uso.
  - El estado de los contratos y de sus detalles no se modifica, cualquiera sea la forma en que termine el caso de uso.
  - Ningún lote queda reservado por encima de su stock libre y ningún detalle de contrato queda cubierto por encima de su cantidad pedida, aun cuando otro Agrónomo o InfoPonia reserven stock al mismo tiempo.

**Garantías de éxito (Postcondiciones):**

a. Se creó una orden de trabajo de cosecha en estado "a realizar", con fecha de creación, fecha programada, prioridad y descripción (si se indicó). Está asociada al Agrónomo que la planificó y al Capataz del invernadero.

b. Se creó una reserva de stock en estado "activa", con fecha de creación igual a la fecha actual, asociada a la orden de cosecha.

c. Se crearon una o más líneas de reserva, una por cada lote seleccionado, con la cantidad reservada de ese lote y sin cantidad cosechada. Todos los lotes pertenecen al mismo invernadero y a la misma variedad.

d. Si la cosecha cubre un detalle de compra-venta, la reserva quedó asociada a ese detalle y su fecha de entrega es la fecha pactada de la venta.

e. Si la cosecha cubre un período de un detalle de suministro, la reserva quedó asociada a ese detalle y su fecha de entrega es la fecha del período cubierto.

f. Si la cosecha no cubre ningún contrato, la reserva no quedó asociada a ningún detalle y no tiene fecha de entrega.

g. Se envió al Capataz una notificación de la nueva orden asignada.

h. Si la cosecha cubre un contrato, se envió al Vendedor del contrato una notificación de la cosecha planificada, con la cantidad que el detalle queda sin cubrir.

i. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la orden de trabajo de cosecha creada.

j. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la reserva de stock y de cada línea de reserva creadas.

**Escenario principal de éxito (o Flujo Básico):**

1.  El Agrónomo inicia la planificación de una nueva cosecha.
2.  El Sistema presenta los invernaderos activos a cargo del Agrónomo.
3.  El Agrónomo selecciona un invernadero.
4.  El Sistema presenta el Capataz asignado al invernadero y los detalles de contrato que pueden cubrirse desde ese invernadero, ordenados por fecha de entrega.
      
      - Para los detalles de compra-venta indica cliente, variedad, cantidad sin cubrir y fecha pactada.
      - Para los períodos de suministro indica cliente, variedad, cantidad sin cubrir y fecha del período.
5.  El Agrónomo selecciona el detalle de contrato a cubrir.
6.  El Sistema establece la variedad del detalle, verifica que el invernadero tenga lotes cosechables de esa variedad y presenta su cantidad sin cubrir, su fecha de entrega y la duración postcosecha de la variedad.
7.  El Agrónomo introduce la fecha programada y la prioridad de la cosecha y, opcionalmente, una descripción.
8.  El Sistema verifica dos condiciones:
      
      - que la fecha programada sea igual o posterior a la fecha actual;
      - que el producto cosechado en esa fecha conserve su aptitud comercial hasta la fecha de entrega.
9.  El Sistema presenta los lotes activos del invernadero, de la variedad del detalle, que están en la etapa “Maduración” y tienen stock libre, con el stock libre y la fecha máxima de cosecha de cada uno, y señala los lotes cuya fecha máxima de cosecha es anterior a la fecha programada. 
10. El Agrónomo selecciona un lote e indica la cantidad de plantas a cosechar de él.
11. El Sistema verifica la cantidad, registra la asignación al lote y presenta el total asignado y la cantidad que el detalle todavía tiene sin cubrir.

*El Agrónomo repite los pasos 10-11 por cada lote que quiera asignar.*

1.  El Agrónomo indica que terminó de asignar lotes.
2.  El Sistema presenta el resumen de la orden: invernadero, Capataz responsable, contrato y detalle cubierto, variedad, fecha de entrega, fecha programada, prioridad, lotes con su cantidad a cosechar y total a cosechar. Si la fecha programada supera la fecha máxima de cosecha de algún lote, el resumen repite la advertencia, con la fecha máxima y los días de exceso de cada uno.
3.  El Agrónomo confirma la planificación.
4.  El Sistema registra:
      
      - la orden de trabajo de cosecha, en estado "a realizar"; 
      - su reserva de stock, con las líneas de cada lote, asociada al detalle de contrato; 
      - la auditoría correspondiente.
5.  El Sistema notifica al Capataz la nueva orden asignada y, si la cosecha cubre un contrato, al Vendedor del contrato.
6.  El Sistema informa al Agrónomo que la cosecha fue planificada y presenta el identificador de la orden.

**Extensiones (o Flujos Alternativos):**

***a.** En cualquier momento antes del paso 14, el Agrónomo cancela la planificación:

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.

***b.** En cualquier momento el Sistema falla o se interrumpe la conexión:

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que la cosecha no fue planificada.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.

**3a.** El invernadero seleccionado no tiene un Capataz activo asignado:

1.  El Sistema informa que no hay un Capataz que pueda recibir la orden en ese invernadero.
2.  El Agrónomo selecciona otro invernadero (vuelve al paso 3) o cancela.

**3b.** El invernadero seleccionado no tiene lotes activos en la etapa "Maduración" con stock libre:

1.  El Sistema informa que no hay stock maduro libre para cosechar en ese invernadero.
2.  El Agrónomo selecciona otro invernadero (vuelve al paso 3) o cancela.

**4a.** El Agrónomo planifica una cosecha sin contrato:

1.  El Agrónomo indica que la cosecha no cubre ningún contrato.
2.  El Sistema presenta las variedades que tienen lotes activos en el invernadero, en la etapa "Maduración", con stock libre.
3.  El Agrónomo selecciona la variedad.
4.  El caso de uso continúa en el paso 7, con estas diferencias:
      
      - En el paso 8, el Sistema solo verifica que la fecha programada sea igual o posterior a la fecha actual.
      - En el paso 11, el Sistema verifica la cantidad solo contra el stock libre del lote; la advertencia de fecha máxima de cosecha (extensión 11c) se aplica igual. 
      - En el resumen del paso 13 no figuran contrato, detalle ni fecha de entrega, y la reserva se registra sin asociarse a ningún detalle.
      - En el paso 16 solo se notifica al Capataz.

**4b.** No hay detalles de contrato que puedan cubrirse desde el invernadero seleccionado:

1.  El Sistema informa que no hay contratos con cantidad sin cubrir que puedan atenderse desde ese invernadero.
2.  El Agrónomo planifica una cosecha sin contrato (continúa en 4a), selecciona otro invernadero (vuelve al paso 3) o cancela.

**6a.** No hay lotes activos de la variedad del detalle en la etapa "Maduración" con stock libre en el invernadero:

1.  El Sistema informa que ese detalle no puede cubrirse desde ese invernadero.
2.  El Agrónomo selecciona otro detalle (vuelve al paso 5), selecciona otro invernadero (vuelve al paso 3) o cancela.

**8a.** La fecha programada es anterior a la fecha actual:

1.  El Sistema señala el error y rechaza la fecha.
2.  El Agrónomo introduce una nueva fecha (vuelve al paso 7).

**8b.** La fecha programada más la duración postcosecha de la variedad es anterior a la fecha de entrega:

1.  El Sistema rechaza la fecha, informa que el producto perdería su aptitud comercial antes de la entrega e indica la primera fecha programada admitida.
2.  El Agrónomo introduce una nueva fecha (vuelve al paso 7).

**8c.** La fecha programada es posterior a la fecha de entrega:

1.  El Sistema advierte que la entrega saldrá con retraso. Si el detalle es de un suministro, advierte además que el retraso puede originar una queja o una indemnización según la cláusula del contrato.
2.  El Agrónomo mantiene la fecha (continúa en el paso 9) o introduce una nueva (vuelve al paso 7).

**10-11a.** El Agrónomo quita un lote ya asignado o cambia su cantidad:

1.  El Sistema actualiza las asignaciones, el total asignado y la cantidad sin cubrir.
2.  El caso de uso continúa en el paso 10.

**11a.** La cantidad indicada supera el stock libre del lote:

1.  El Sistema señala el error e informa el stock libre del lote.
2.  El Agrónomo indica una cantidad menor o elige otro lote (vuelve al paso 10).

**11b.** La cantidad indicada supera la cantidad que el detalle tiene sin cubrir:

1.  El Sistema señala el error e informa la cantidad sin cubrir.
2.  El Agrónomo corrige la cantidad (vuelve al paso 10).

**11c.** La cantidad es válida, pero la fecha programada supera la fecha máxima de cosecha del lote:

1.  El Sistema advierte que el lote se cosecharía después de su fecha máxima de cosecha e informa esa fecha y los días de exceso.
2.  El Agrónomo mantiene el lote (el Sistema registra la asignación y presenta el total asignado y la cantidad sin cubrir, como en el paso 11), elige otro lote (vuelve al paso 10) o cambia la fecha programada (vuelve al paso 7).

  

**12.a.** El Agrónomo termina de asignar lotes sin cubrir toda la cantidad del detalle: 

1.  El Sistema informa que el detalle quedará con cantidad sin cubrir, que podrá cubrirse con otra cosecha.
2.  El caso de uso continúa en el paso 13.

**12b.** El Agrónomo no asignó ningún lote:

1.  El Sistema informa que la orden debe incluir al menos un lote con al menos una planta.
2.  El Agrónomo asigna un lote (vuelve al paso 10) o cancela.

**14a.** El Agrónomo quiere corregir un dato del resumen: 

1.  El Agrónomo indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5, 4a.3, 7 o 10). Después de corregir, el Agrónomo vuelve a indicar que terminó de asignar lotes (paso 12). 
2.  Si cambia el detalle de contrato o la variedad, el Sistema descarta las asignaciones de lotes y repite las verificaciones desde el paso 6. 

**15a.** Ya existe una orden de trabajo de cosecha con los mismos valores en todos sus atributos (sin contar el identificador) y con las mismas líneas de reserva:

1.  El Sistema rechaza el registro e informa el identificador de la orden existente.
2.  El Agrónomo corrige algún dato (vuelve a 14a) o cancela.

**15b.** Entre las verificaciones y la confirmación cambió el stock libre de un lote, la cantidad sin cubrir del detalle o la situación del contrato. Por ejemplo: InfoPonia asignó stock de cámara al detalle, la venta fue cancelada, el detalle pasó a esperar la decisión del cliente o un lote dejó de estar activo.

1.  El Sistema vuelve a verificar, al momento de registrar, el stock libre de cada lote, la cantidad sin cubrir y que el detalle siga pudiendo cubrirse.
2.  Si alguna verificación ya no se cumple, el Sistema no registra nada e informa qué dato cambió.
3.  El caso de uso vuelve al paso afectado (5 o 10).

**16a.** El Sistema no logra entregar la notificación al Capataz:

1.  La orden permanece registrada y visible entre las órdenes asignadas al Capataz.
2.  El Sistema reintenta el envío y avisa al Agrónomo que la notificación está pendiente.

**16b.** El Sistema no logra entregar la notificación al Vendedor:

1.  La orden permanece registrada.
2.  El Sistema reintenta el envío.

**Requisitos especiales:**

  - Tras cada selección o dato ingresado por el Agrónomo (pasos 3 a 12), la pantalla se actualiza con las verificaciones y los valores calculados en no más de 1 segundo.
  - El registro del paso 15 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un indicador de progreso.
  - El paso 15 se ejecuta como una única transacción: la orden, la reserva, sus líneas y los logs se registran juntos o no se registra ninguno.
  - El control de concurrencia sobre el stock libre de los lotes y la cantidad sin cubrir de los detalles impide la sobreasignación entre planificaciones simultáneas, sean del Agrónomo o de InfoPonia.
  - Solo el rol Agrónomo accede a este caso de uso, y únicamente sobre los invernaderos que tiene a cargo.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio:**

  - **Alcance de la orden:** una orden de cosecha abarca una sola variedad y un solo invernadero, con uno o varios lotes, y tiene una única reserva de stock cuyas líneas apuntan a esos lotes. (Pasos 3, 6, 9 y 15)
  - **Capataz del invernadero:** el Capataz asignado al invernadero de la orden. Se asigna automáticamente y se le notifica. (Pasos 4 y 16)
  - **Lote cosechable:** lote activo del invernadero, de la variedad de la orden, cuya etapa actual es "Maduración" al momento de planificar y cuyo stock libre es mayor que cero. (Pasos 6, 9 y 11)
  - **Stock libre de un lote:** cantidad actual del lote menos la suma de las cantidades reservadas en sus líneas de reserva cuya reserva está "activa". Nunca es menor que cero. (Pasos 9 y 11)
  - **Fecha máxima de cosecha:** fecha de entrada del lote a la etapa “Maduración” más la duración estimada de esa etapa en el ciclo de su variedad. Es una estimación, así que no bloquea: si la fecha programada la supera, el Sistema advierte, con la fecha máxima y los días de exceso (fecha programada menos fecha máxima), al asignar el lote y otra vez en el resumen, y el Agrónomo decide. Vale con contrato y sin contrato. A diferencia de la asignación automática (PROD-ASG-STK), un lote que superó su fecha máxima no se excluye. (Reglas 3 y 4 de 8.20; pasos 9, 11 y 13, y extensión 11c) 
  - **Detalle cubrible:** (Pasos 4 y 5)
      
      - En una compra-venta, un detalle en estado "abierto" de una venta en estado "abierta". Si la venta es con retiro en invernadero, solo puede cubrirse desde el invernadero de retiro.
      - En un suministro, un período de entrega de un detalle de suministro vigente.
      - En ambos casos, la cantidad sin cubrir debe ser mayor que cero.
      - En una compra-venta con envío y en un suministro, solo si el Vendedor del contrato es el Vendedor del invernadero.
      - En un suministro, solo los períodos cuya fecha esté entre la fecha actual y la fecha actual más el horizonte de planificación de cosecha, ambas inclusive.
  - **Horizonte de planificación de cosecha:** cantidad de días hacia adelante dentro de la cual el Agrónomo puede cubrir un período de suministro con una cosecha manual. Es un parámetro de la configuración operativa. Los períodos con fecha anterior a la actual no pueden cubrirse. (Pasos 4 y 5)
  - **Cantidad cubierta de una línea de reserva:** (Pasos 4, 6 y 11)
      
      - la cantidad reservada, si la línea es de un lote y todavía no se cosechó;
      - el menor valor entre la cantidad cosechada y la reservada, si es de un lote y ya se cosechó;
      - la cantidad reservada, si es de cámara.
  - **Cantidad sin cubrir de un detalle:** cantidad pedida menos la suma de la cantidad cubierta de las líneas de sus reservas que no están "liberadas". La cantidad pedida es la cantidad solicitada en una compra-venta, o la cantidad del período en un suministro. (Pasos 4, 6 y 11)
  - **Validación de vencimiento:** la fecha programada más la duración postcosecha de la variedad debe ser igual o posterior a la fecha de entrega. Es bloqueante. (Paso 8)
  - **Advertencia de retraso:** si la fecha programada es posterior a la fecha de entrega, el Sistema advierte y permite confirmar. La fecha de entrega de la reserva conserva la fecha prometida. (Paso 8)
  - **Cantidad a cosechar:** en cada lote, un número entero entre uno y su stock libre. Con contrato, el total no puede superar la cantidad sin cubrir del detalle. (Paso 11)

**Lista de tecnología y variaciones de datos:**

5a. Los detalles de contrato pueden buscarse por cliente o por variedad.

7a. La fecha programada se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.

7b. La prioridad toma los valores alta, media o baja. El Sistema propone "media" por defecto.

10a. La cantidad a cosechar se expresa en plantas, como número entero.

16a. La notificación al Capataz se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.

**Frecuencia:** a confirmar con el Jardín Botánico. Depende de la cantidad de contratos que requieran una cosecha manual y de las cosechas sin contrato que decida el Agrónomo.

**Temas abiertos:**

  - ¿Con qué frecuencia se planifican cosechas manuales en cada invernadero?
  - ¿Qué sucede con las órdenes de cosecha "a realizar" cuya fecha programada pasó sin concretarse? ¿Se notifica al Agrónomo?

## PROD-MOD-CSC · Modificar Cosecha

Caso de uso nuevo del módulo de producción (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Reemplaza al caso 3 de pendientes_CU («Validar o Modificar Cosecha Automática»). Decisiones del 20/11/2026 aplicadas: no hay validación obligatoria (A, opción b); sirve para cualquier cosecha pendiente (B); se modifican fecha, prioridad, descripción y reparto entre lotes (C); desde cualquier estado no concretado ni cancelado (D); avisos al Capataz y, si hay retraso, al Vendedor (E); solo el Agrónomo del invernadero (F).

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Producción / Órdenes.

**Versión:** 0.1

**Actor principal:** Agrónomo del invernadero de la cosecha.

**Personal involucrado e intereses**

  - **Agrónomo:** quiere ajustar la fecha, la prioridad o los lotes de una cosecha según el estado real del invernadero, sin cancelarla y planificarla de nuevo.
  - **Capataz:** quiere enterarse de cualquier cambio en una cosecha que le toca hacer.
  - **Vendedor:** quiere saber si un cambio atrasa la entrega de un contrato suyo.
  - **Cliente:** quiere recibir el producto a tiempo y en buen estado.
  - **Gerente:** quiere que nunca se coseche algo que vence antes de la entrega y que ningún lote quede reservado por encima de su stock.

**Relaciones con otros casos de uso**

  - No incluye otros casos de uso ni es extendido por ellos.
  - **Lo preceden:** PROD-PNF-CSC · Planificar Cosecha (cosechas manuales); PROD-ASG-STK · Asignar Stock Maduro, COM-PCT-SUM, la pre-reserva diaria y el encadenamiento (cosechas automáticas).
  - **Lo sigue:** PROD-CNC-CSC · Concretar Cosecha.
  - **Relacionado:** PROD-CNL-ORD · Cancelar Orden, que es el camino para cambiar la variedad, el invernadero, el contrato o la cantidad.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Agrónomo y tiene a cargo el invernadero de la cosecha.

b. Existe al menos una cosecha de ese invernadero que no está concretada ni cancelada.

**Garantías mínimas**

  - La modificación es atómica. Si falla o se cancela, la cosecha y su reserva quedan como estaban.
  - Ningún lote queda con más reservado que su stock, aunque se planifique o asigne stock al mismo tiempo.
  - Ninguna cosecha con contrato queda programada para una fecha en la que el producto vence antes de la entrega.
  - No cambian la variedad, el invernadero, el contrato ni la cantidad total reservada.

**Garantías de éxito (Postcondiciones)**, según lo que cambió el actor:

a. La cosecha quedó con la fecha programada, la prioridad o la descripción nuevas.

b. Si cambió los lotes, cada línea de lote de la reserva quedó con su nueva cantidad reservada; las líneas de los lotes quitados se eliminaron y se crearon las de los agregados. El total reservado no cambió y el stock libre de cada lote bajó o subió en la diferencia.

c. La fecha de entrega de la reserva no cambió: se conserva la fecha prometida (regla 12 de 8.8).

d. Se notificó el cambio al Capataz del invernadero.

e. Si la cosecha es con contrato y la fecha nueva es posterior a la de entrega, se notificó el retraso al Vendedor del contrato; en un suministro, con la advertencia de posible queja o indemnización.

f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la cosecha y cada cambio con su valor anterior y el nuevo.

**Escenario principal de éxito (o Flujo Básico)**

(El Agrónomo cambia la fecha de una cosecha automática con contrato; la fecha nueva no genera advertencias.)

1.  El Agrónomo inicia la modificación de cosechas.
2.  El Sistema presenta las cosechas pendientes de sus invernaderos, ordenadas por fecha programada, con la variedad, el invernadero, la fecha programada, la prioridad, la cantidad reservada, el origen (automática, manual o encadenada) y, si tiene contrato, el contrato y la fecha de entrega.
3.  El Agrónomo selecciona una cosecha.
4.  El Sistema presenta la cosecha con sus líneas de lote (cantidad reservada, stock libre y fecha máxima de cosecha de cada lote) y, si hay contrato, la fecha de entrega y la primera y la última fecha programada admitidas.
5.  El Agrónomo indica la nueva fecha programada.
6.  El Sistema verifica la fecha y presenta cómo queda la cosecha.

*El Agrónomo repite los pasos 5 y 6 para cambiar la prioridad, la descripción o los lotes (extensiones 5a y 5b).*

7.  El Agrónomo termina los cambios.
8.  El Sistema presenta el resumen: cada cambio con su valor anterior y el nuevo.
9.  El Agrónomo confirma.
10. El Sistema vuelve a verificar que la cosecha siga pendiente y que el stock libre de cada lote alcance para lo reservado. Luego, en una única transacción, registra los cambios y la auditoría.
11. El Sistema notifica el cambio al Capataz.
12. El Sistema informa al Agrónomo que la cosecha quedó modificada.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 9, el Agrónomo cancela:**

1.  El Sistema descarta los cambios.

**\*b. En cualquier momento el Sistema falla:**

1.  El Sistema revierte cualquier registro parcial y, al restablecerse, informa que la modificación no se registró.

**2a. El Agrónomo inicia desde la notificación de una cosecha automática:**

1.  El Sistema presenta directamente esa cosecha y el caso de uso continúa en el paso 4.

**5a. El Agrónomo cambia la prioridad o la descripción:**

1.  El Sistema registra el valor nuevo (alta, media o baja; o un texto opcional) y continúa en el paso 6.

**5b. El Agrónomo cambia los lotes:**

1.  El Sistema presenta los lotes cosechables de la misma variedad en el mismo invernadero (regla «Lote cosechable» de PROD-PNF-CSC), con su stock libre, que incluye su propia cantidad reservada en esta cosecha, y su fecha máxima.
2.  El Agrónomo cambia la cantidad de un lote, lo quita o agrega otro.
3.  El Sistema muestra el total asignado frente al total reservado.
4.  **5b.4a.** El total asignado no coincide con el reservado: el Sistema lo informa y no deja terminar hasta que coincidan.
5.  **5b.4b.** La cantidad indicada para un lote supera su stock libre: el Sistema informa el máximo y deja la cantidad sin cambios.
6.  **5b.4c.** Los lotes de la variedad no alcanzan para cubrir lo reservado: el Sistema informa que, para reducir la cantidad, corresponde cancelar la orden (PROD-CNL-ORD), y que lo sin cubrir se cubre con una cosecha nueva (regla 13 de 8.8).

**5c. El Agrónomo intenta cambiar la variedad, el invernadero, el contrato o la cantidad total:**

1.  El Sistema informa que no se puede y que corresponde cancelar la orden y planificar otra.

**6a. La fecha es anterior a la actual:**

1.  El Sistema rechaza la fecha y el Agrónomo indica otra.

**6b. Con contrato, el producto vencería antes de la entrega (fecha programada + duración postcosecha anterior a la fecha de entrega):**

1.  El Sistema rechaza la fecha, explica que el producto perdería su aptitud comercial e indica la primera fecha admitida. El Agrónomo indica otra (regla 11 de 8.8).

**6c. Con contrato, la fecha es posterior a la de entrega:**

1.  El Sistema advierte que la entrega saldrá con retraso; en un suministro, además, la posible queja o indemnización según la cláusula.
2.  El Agrónomo mantiene la fecha o indica otra. Si la mantiene, en el paso 11 se notifica además al Vendedor (regla 12 de 8.8).

**6d. La fecha supera la fecha máxima de cosecha de algún lote:**

1.  El Sistema advierte, con la fecha máxima y los días de exceso de cada lote afectado.
2.  El Agrónomo mantiene la fecha, cambia los lotes (extensión 5b) o indica otra fecha. No bloquea (MD-09; regla 4 de 8.20).

**7a. El Agrónomo no indicó ningún cambio:**

1.  El Sistema lo informa y vuelve al paso 4.

**10a. Al registrar, la cosecha ya se concretó o se canceló en otra operación:**

1.  El Sistema no registra ningún cambio, informa el estado actual y vuelve al paso 2.

**10b. Al registrar, el stock libre de algún lote ya no alcanza (otra operación lo reservó):**

1.  El Sistema no registra ningún cambio, informa los lotes afectados y vuelve a la extensión 5b con los datos actualizados.

**11a. El Sistema no logra enviar una notificación:**

1.  La modificación permanece registrada y el Sistema reintenta el envío.

**Requisitos especiales**

  - La interfaz del Agrónomo está pensada para computadora.
  - El paso 10 se ejecuta como una única transacción.
  - La modificación se serializa con la planificación de cosechas, la asignación de stock, la concreción de la cosecha y la cancelación de órdenes sobre los mismos lotes.
  - La fecha se ingresa como dd/mm/aaaa y la fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción.

**Reglas de negocio**

  - **Quién modifica:** solo el Agrónomo a cargo del invernadero de la cosecha. (Precondición a)
  - **Cosecha modificable:** cualquiera (automática, manual o encadenada) que no esté concretada ni cancelada. No requiere validación previa: una cosecha automática queda programada al crearse y el Capataz la ve sin esperar al Agrónomo. (Paso 2)
  - **Datos modificables:** fecha programada, prioridad, descripción y reparto entre lotes. No se modifican la variedad, el invernadero, el contrato ni la cantidad total reservada. (Pasos 5 y 6, extensiones 5a a 5c)
  - **Lotes:** de la misma variedad y el mismo invernadero, cosechables y con stock libre suficiente; el total asignado coincide con el reservado. El Agrónomo elige los lotes, como en una cosecha manual (reglas 8 y 9 de 8.6; supuesto 7 de 8.7). (Extensión 5b)
  - **Validaciones de fecha:** no puede ser pasada; con contrato, bloquea si el producto vence antes de la entrega (regla 11 de 8.8) y advierte si se atrasa la entrega (regla 12 de 8.8); advierte si supera la fecha máxima de cosecha de un lote (regla 4 de 8.20). (Extensiones 6a a 6d)
  - **Fecha prometida:** la fecha de entrega de la reserva no cambia. (Postcondición c)
  - **Avisos:** al Capataz, siempre; al Vendedor, solo si la fecha nueva atrasa la entrega de un contrato. (Paso 11 y extensión 6c)

**Lista de tecnología y variaciones de datos**

  - **6d.** Los días de exceso se cuentan como días corridos entre la fecha máxima y la fecha programada.

**Frecuencia:** frecuente. Cada vez que el Agrónomo ajusta la planificación del invernadero.

**Temas abiertos:** ninguno.

## PROD-CNC-CSC · Concretar Cosecha
**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Producción / Órdenes.

  
 **Actor principal:** Capataz.

  
 **Versión:** 0.4

**Personal involucrado e intereses:**

  - **Capataz:** quiere registrar rápido lo que realmente cosechó de cada lote y de cada sector, e informar las plantas que se perdieron, sin tener que hacer cálculos de stock ni de costos.
  - **Agrónomo:** quiere saber cuánto rindió cada lote frente a lo reservado, cuántas plantas se perdieron y qué lotes quedaron finalizados, para planificar nuevas siembras y cosechas.
  - **Vendedor:** quiere saber si el contrato quedó cubierto y enterarse a tiempo de cualquier faltante o excedente.
  - **Cliente:** quiere recibir la cantidad pactada y, si falta producto, poder decidir si acepta una cantidad menor.
  - **Gerente:** quiere que el costo de lo cosechado pase de producción en proceso a productos terminados por lote, con trazabilidad completa en la auditoría y en el libro diario.
  - **Organización (Jardín Botánico):** quiere que el stock de los lotes, la cámara y los sectores refleje la realidad, que los agujeros liberados queden disponibles para nuevas siembras y que ningún contrato quede sin atender por un faltante no detectado.

**Relaciones con otros casos de uso:**

  - **«include»** PROD-ASG-STK · Asignar Stock Maduro: se incluye en la extensión 13a para cubrir el faltante de una cosecha con contrato.
  - **«extend»** PROD-REG-MRM · Registrar Merma: extiende este caso de uso en el punto de extensión *Plantas perdidas en la cosecha* (extensión 10a) y se ejecuta una vez por cada lote con plantas perdidas.

**Puntos de extensión:**

  - *Plantas perdidas en la cosecha* (paso 10): un lote rindió menos de lo reservado y el Capataz declara que parte de la diferencia se perdió.

**Precondiciones:**

a. El Capataz está autenticado en el Sistema.

b. Existe al menos una orden de trabajo de cosecha en estado "a realizar" asignada al Capataz.

c. Existe un ejercicio contable vigente.

d. Existen las cuentas contables "Productos Terminados", "Productos en Proceso" y "Pérdidas por Mermas".

**Garantías mínimas:**

  - La operación es atómica, incluidos el caso de uso incluido y el que extiende a este. Si el caso de uso se cancela o falla:
      
      - la orden permanece en estado "a realizar" y su reserva permanece "activa";
      - no se registra ningún cambio en lotes, sectores, cámara, contratos ni contabilidad;
      - no queda ningún log de auditoría parcial.
  - Una orden de cosecha se concreta una única vez.
  - Ninguna cosecha toma plantas reservadas por otra orden.

**Garantías de éxito (Postcondiciones):**

a. La orden de trabajo de cosecha pasó de estado "a realizar" a "concretada", con la fecha de resolución igual a la fecha actual y la fecha de cosecha igual a la fecha efectiva.

b. Cada línea de reserva que apunta a un lote quedó con su cantidad cosechada.

c. La cantidad actual de cada lote se redujo en la cantidad cosechada de ese lote. Cada lote cuya cantidad actual llegó a cero quedó en estado "finalizado". El costo acumulado de cada lote cosechado se redujo en la cantidad cosechada multiplicada por el costo por planta que tenía el lote antes de la cosecha.

d. En cada sector, la cantidad de agujeros ocupados por la ocupaciones vigentes del lote se redujo en la cantidad de plantas cosechadas en ese sector, y la cantidad de agujeros disponibles del sector aumentó en esa misma cantidad.

e. Por cada lote con cantidad cosechada mayor que cero, se registró un movimiento de stock de tipo "salida por cosecha", con la cantidad cosechada y la fecha efectiva, asociado al lote y originado en la cosecha.

f. Por cada movimiento de stock de salida, se generó un asiento contable en el libro diario del ejercicio vigente, originado en ese movimiento. El asiento debita la cuenta "Productos Terminados" y acredita la cuenta "Productos en Proceso" por la cantidad cosechada multiplicada por el costo por planta del lote.

g. Por cada lote cosechado, se registró en su bitácora un evento de tipo "cosecha", con la cantidad cosechada, la fecha efectiva y el Capataz como responsable. El evento está asociado a la cosecha, al lote, a su etapa productiva y al invernadero.

h. Si la cosecha cubre un contrato, la reserva pasó a "lista para entrega". Si la cantidad cubierta total de la reserva es cero, pasó a "liberada".

i. Si la cosecha cubre un contrato y algún lote rindió más de lo reservado, se creó una partida en cámara por cada uno de esos lotes, con:

  - estado "disponible" y motivo "excedente de cosecha";
  - cantidad igual al excedente;
  - costo unitario igual al costo por planta del lote;
  - fecha de ingreso igual a la fecha efectiva y fecha límite calculada.

Por cada partida se registró un movimiento de stock de tipo "ingreso a cámara", originado en la cosecha.

j. Si la cosecha no cubre ningún contrato, la reserva pasó a "liberada". Por cada lote con cantidad cosechada mayor que cero se creó una partida en cámara, con:

  - estado "disponible" y motivo "cosecha planificada por el Agrónomo";
  - cantidad igual a lo cosechado;
  - costo unitario igual al costo por planta del lote;
  - fecha de ingreso igual a la fecha efectiva y fecha límite calculada.

Por cada partida se registró un movimiento de stock de tipo "ingreso a cámara", originado en la cosecha.

k. Si ingresó producto a la cámara, se disparó la asignación automática de cámara a cargo de InfoPonia.

l. Si la cosecha cubre un contrato y tuvo faltante, se ejecutó PROD-ASG-STK por la diferencia. Si el stock maduro libre no alcanzó a cubrir todo el faltante, se reservó lo disponible y, para lo que quedó sin cubrir:

  - en una compra-venta, el detalle y la venta quedaron en estado "pendiente de decisión del cliente", y se envió al cliente un correo con un enlace de acceso temporal para que decida;
  - en un suministro, el detalle quedó con cantidad sin cubrir y la entrega del período saldrá con lo disponible.

m. Si el Capataz declaró plantas perdidas, se ejecutó PROD-REG-MRM · Registrar Merma por cada lote afectado.

n. Si con esta cosecha quedaron listas para entrega todas las reservas de una compra-venta, o todas las reservas de un período de suministro, se disparó la planificación automática de la Entrega a cargo de InfoPonia.

o. Se envió al Agrónomo responsable del invernadero una notificación de la cosecha concretada, con lo reservado, lo cosechado y lo perdido en cada lote. Si la cosecha cubre un contrato y hubo faltante o excedente, se notificó también al Vendedor del contrato.

p. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la orden de cosecha y los cambios en su estado, su fecha de resolución y su fecha de cosecha.

q. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambios de valor de cada línea de reserva, reserva, lote, ocupación de sector, sector y detalle de contrato modificados.

r. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada movimiento de stock, asiento contable, registro de bitácora y partida de cámara creados.

**Escenario principal de éxito (o Flujo Básico):**

1.  El Capataz inicia la concreción de una cosecha.  
      
2.  El Sistema presenta las órdenes de cosecha en estado "a realizar" asignadas al Capataz, ordenadas por prioridad (alta, media, baja) y, dentro de cada prioridad, por fecha programada. Para cada una indica la variedad, la fecha programada, la prioridad, el total a cosechar y, si cubre un contrato, el cliente y la fecha de entrega.  
      
3.  El Capataz selecciona una orden.  
      
4.  El Sistema presenta el detalle de la orden:  
      
      
      - la variedad;
      - el contrato y la fecha de entrega, si corresponde;
      - para cada lote, la cantidad reservada y los sectores que ocupa, con los agujeros ocupados por el lote en cada uno.

Propone como fecha efectiva la fecha actual y, en cada sector de cada lote, la cantidad propuesta como cantidad cosechada.  
  

1.  El Capataz confirma o modifica la fecha efectiva de cosecha.  
      
2.  El Sistema verifica que la fecha efectiva esté comprendida entre la fecha de creación de la orden y la fecha actual.  
      
3.  El Capataz indica, para un sector de un lote, la cantidad de plantas realmente cosechadas en él.  
      
4.  El Sistema verifica la cantidad, recalcula el total cosechado del lote y presenta la diferencia con la cantidad reservada.  
      
     *El Capataz repite los pasos 7 y 8 por cada sector en el que cosechó una cantidad distinta de la propuesta. En los demás sectores se toma la cantidad propuesta.**  
      
    *
5.  El Capataz indica que terminó de registrar la cosecha por sector.  
      
6.  El Sistema verifica el total cosechado de cada lote y presenta, para cada uno, la cantidad cosechada frente a la reservada.  
      
7.  El Sistema presenta el resumen de la concreción:  
      
      
      - la fecha efectiva;
      - para cada lote, la cantidad reservada, la cosechada, el excedente y las plantas perdidas;
      - el total cosechado frente al reservado;
      - el destino de lo cosechado.
8.  El Capataz confirma la concreción.  
      
9.  El Sistema registra la orden como concretada:  
      
      
      - actualiza las líneas de reserva, la cantidad actual de cada lote, las ocupaciones de sector y los agujeros de cada sector;
      - registra los movimientos de stock, los asientos contables y los registros de bitácora;
      - resuelve la reserva y el destino del excedente;
      - registra la auditoría correspondiente.
10. El Sistema notifica la cosecha concretada al Agrónomo responsable del invernadero.  
      
11. El Sistema informa al Capataz que la cosecha fue concretada.  
      

**Extensiones (o Flujos Alternativos):**

***a.** En cualquier momento antes del paso 12, el Capataz cancela la concreción:

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio y la orden permanece en estado "a realizar".

***b.** En cualquier momento el Sistema falla o se interrumpe la conexión:

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Capataz que la cosecha no fue concretada.
3.  El Capataz reinicia el caso de uso desde el paso 1.

**4a.** La orden no cubre ningún contrato:

1.  El Sistema indica que todo lo cosechado ingresará a la cámara.
2.  El caso de uso continúa en el paso 5. En el paso 13, la reserva pasa a "liberada" y lo cosechado de cada lote ingresa a la cámara con motivo "cosecha planificada por el Agrónomo".

**6a.** La fecha efectiva es posterior a la fecha actual:

1.  El Sistema señala el error y rechaza la fecha.
2.  El Capataz introduce una nueva fecha (vuelve al paso 5).

**6b.** La fecha efectiva es anterior a la fecha de creación de la orden:

1.  El Sistema señala el error e informa la fecha de creación de la orden.
2.  El Capataz introduce una nueva fecha (vuelve al paso 5).

**8a.** La cantidad indicada para un sector supera los agujeros ocupados por el lote en ese sector:

1.  El Sistema señala el error e informa los agujeros ocupados por el lote en ese sector.
2.  El Capataz corrige la cantidad (vuelve al paso 7).

**8b.** El total cosechado del lote supera la cantidad reservada más el stock libre del lote:

1.  El Sistema señala el error e informa la cantidad máxima que puede cosecharse de ese lote sin tomar plantas reservadas por otras órdenes.
2.  El Capataz corrige las cantidades (vuelve al paso 7).

**10a.** Un lote rindió menos de lo reservado (punto de extensión *Plantas perdidas en la cosecha*):

1.  El Sistema presenta, para cada lote que rindió menos, la cantidad de plantas reservadas que no se cosecharon, e informa que, salvo que se declaren perdidas, permanecerán en el lote como stock libre.
2.  El Capataz indica, para un lote, cuántas plantas se perdieron en cada sector y la causa y, opcionalmente, una descripción.
3.  El Sistema verifica las cantidades y presenta las plantas perdidas del lote y las que quedan como stock libre.
4.  El Capataz repite los puntos 2 y 3 por cada lote en el que se perdieron plantas. En los demás lotes se toman cero plantas perdidas.
5.  El Capataz solicita el resumen de la concreción.
6.  En el paso 13 se ejecuta PROD-REG-MRM · Registrar Merma por cada lote con cantidad perdida mayor que cero, con las cantidades por sector y la causa.
7.  El resto de las plantas no cosechadas permanece en el lote como stock libre. El caso de uso continúa en el paso 11.

**10a.3a.** La cantidad perdida de un lote supera las plantas que no se cosecharon, o la cantidad perdida en un sector supera las plantas que quedan del lote en ese sector:

1.  El Sistema señala el error e informa la cantidad máxima admitida.
2.  El Capataz corrige la cantidad (vuelve a 10a.2).

**10a.3b.** El Capataz indicó plantas perdidas sin indicar la causa:

1.  El Sistema señala que la causa es obligatoria.
2.  El Capataz indica la causa (vuelve a 10a.2).

**10b.** Un lote rindió más de lo reservado y la orden cubre un contrato:

1.  El Sistema informa que el excedente de ese lote ingresará a la cámara con motivo "excedente de cosecha".
2.  El caso de uso continúa en el paso 11.

**12a.** El Capataz quiere corregir un dato del resumen:

1.  El Capataz indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5, 7 o 10a).
2.  Si corrige una cantidad cosechada, el Capataz vuelve a indicar que terminó el registro (paso 9) y el Sistema repite las verificaciones desde el paso 10.
3.  Si corrige las plantas perdidas (10a), el Capataz vuelve a solicitar el resumen (10a.5).

**13a.** La orden cubre un contrato y la cantidad cubierta total de la reserva es menor que la cantidad reservada en sus líneas de lote:

1.  El Sistema incluye PROD-ASG-STK · Asignar Stock Maduro para el mismo detalle de contrato, por la diferencia.
2.  Si el stock maduro libre cubre toda la diferencia, el caso de uso continúa en el paso 14.
3.  Si la cubre solo en parte o no la cubre, PROD-ASG-STK reserva lo disponible, y lo que queda sin cubrir sigue el camino de faltante:
      
    1.  Si el detalle es de una compra-venta:
          
        1.  El Sistema pasa el detalle y la venta a estado "pendiente de decisión del cliente".
        2.  El Sistema envía al cliente un correo con un enlace de acceso temporal para que decida si acepta la cantidad disponible.
        3.  El Sistema notifica el faltante al Vendedor del contrato.
    2.  Si el detalle es de un suministro:
          
        1.  El detalle queda con cantidad sin cubrir para ese período y la entrega saldrá con lo disponible.
        2.  El Sistema notifica el faltante al Vendedor del contrato.

**13b.** La orden ya no se encuentra en estado "a realizar" al momento de registrar (por ejemplo, el Agrónomo la canceló mientras el Capataz ingresaba los datos):

1.  El Sistema no registra ningún cambio e informa al Capataz el estado actual de la orden.
2.  El caso de uso termina.

**13c.** Entre las verificaciones y la confirmación cambió el stock libre de un lote, y ahora el total cosechado de ese lote supera la cantidad reservada más el stock libre:

1.  El Sistema no registra ningún cambio e informa qué lote se vio afectado y cuál es la nueva cantidad máxima.
2.  El caso de uso vuelve al paso 7.

**14a.** El Sistema no logra entregar la notificación al Agrónomo:

1.  La concreción permanece registrada.
2.  El Sistema reintenta el envío.
3.  En el paso 15, el Sistema avisa además al Capataz que la notificación al Agrónomo quedó pendiente.

**Requisitos especiales:**

  - La interfaz del Capataz está pensada para pantallas de celular, con la carga dividida en pasos.
  - Tras cada dato ingresado por el Capataz (pasos 3 a 10), la pantalla se actualiza con las verificaciones y los valores calculados en no más de 1 segundo.
  - El registro del paso 13 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un indicador de progreso.
  - El paso 13, incluidas la ejecución de PROD-ASG-STK y la de PROD-REG-MRM, se ejecuta como una única transacción: todos los cambios y registros se confirman juntos o no se confirma ninguno.
  - El control de concurrencia impide:
      
      - que una misma orden se concrete dos veces;
      - que una orden se concrete y se cancele al mismo tiempo;
      - que una cosecha tome plantas reservadas por otra orden.
  - Solo el Capataz asignado a la orden puede concretarla.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los montos de los asientos contables se expresan en pesos argentinos, con dos decimales.
  - El enlace de acceso temporal enviado al cliente es de uso único y tiene una vigencia limitada.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio:**

  - **Valores propuestos:** el Sistema propone:  
      
      
      - la fecha actual como fecha efectiva;
      - en cada sector de cada lote, la cantidad propuesta como cantidad cosechada;
      - en cada sector de un lote que rindió menos de lo reservado, cero plantas perdidas.

El Capataz solo indica los valores que difieren de lo propuesto; los demás se toman tal como los propone el Sistema. (Pasos 4, 5 y 7, y extensión 10a)  
  

  - **Fecha efectiva válida:** fecha comprendida entre la fecha de creación de la orden y la fecha actual, ambas inclusive. (Paso 6)  
      
  - **Cantidad cosechada válida:** en cada sector, un número entero entre cero y los agujeros ocupados por el lote en ese sector. En cada lote, el total no puede superar la cantidad reservada en su línea más el stock libre del lote. (Pasos 8, 10 y 13)  
      
  - **Stock libre de un lote:** cantidad actual del lote menos la suma de las cantidades reservadas en sus líneas de reserva cuya reserva está "activa", sin contar la reserva de la orden que se concreta. (Pasos 8 y 13)  
      
  - **Excedente de un lote:** cantidad cosechada menos cantidad reservada, cuando es mayor que cero. Con contrato, ingresa a la cámara con motivo "excedente de cosecha". (Pasos 10 y 13)  
      
  - **Plantas no cosechadas:** cantidad reservada menos cantidad cosechada, cuando es mayor que cero. El Capataz declara las que se perdieron en cada sector, que se registran con PROD-REG-MRM. Las que no declara perdidas permanecen en el lote como stock libre. (Paso 10)  
      
  - **Cantidad cubierta de una línea de lote cosechada:** el menor valor entre la cantidad cosechada y la cantidad reservada, porque el excedente ya no corresponde a la reserva sino a la cámara. (Paso 13)  
      
  - **Resolución de la reserva:** con contrato, pasa a "lista para entrega", salvo que su cantidad cubierta total sea cero, en cuyo caso pasa a "liberada". Sin contrato, pasa siempre a "liberada". (Paso 13)  
      
  - **Faltante:** con contrato, la cantidad reservada en las líneas de lote menos su cantidad cubierta. Se intenta cubrir con PROD-ASG-STK, que aplica la prioridad de asignación: primero cámara, después lotes. Si el stock maduro libre cubre solo una parte, se reserva lo disponible. Lo que no se cubre sigue el camino de faltante de la compra-venta o del suministro. (Paso 13)  
      
  - **Costo por planta de un lote:** costo acumulado del lote dividido por su cantidad actual. El costo acumulado es la suma de los montos de consumo de su siembra y de sus imputaciones de costo, menos lo que ya salió por cosecha y por merma; cada cosecha lo baja en la cantidad cosechada por el costo por planta de ese momento. La partida de cámara conserva el costo por planta del momento de la cosecha. Falta precisar si el costo acumulado se guarda en el lote o se calcula (MD-79). (Paso 13)  
      
  - **Liberación de agujeros:** en cada sector, se liberan tantos agujeros como plantas se cosecharon en ese sector. (Paso 13)  
      
  - **Fin del lote:** un lote cuya cantidad actual llega a cero pasa a estado "finalizado". (Paso 13)  
      
  - **Partida de cámara:** una por cada lote que aporta producto a la cámara, con:  
      
      
      - costo unitario igual al costo por planta del lote en ese momento; se guarda al crear la partida y no se recalcula después;
      - fecha de ingreso igual a la fecha efectiva;
      - fecha límite igual a la fecha de la cosecha más la duración postcosecha de la variedad. (Paso 13)  
          

**Lista de tecnología y variaciones de datos:**

5a. La fecha efectiva se ingresa con formato dd/mm/aaaa, mediante calendario o teclado. El Sistema propone por defecto la fecha actual.

7a. Las cantidades cosechadas se expresan en plantas, como números enteros. La cantidad propuesta en cada sector es la parte proporcional de la cantidad reservada del lote, según los agujeros que el lote ocupa en ese sector:

  - cada sector recibe la parte entera de su cuota;
  - las unidades restantes se asignan de a una a los sectores con mayor parte decimal (método del resto mayor);
  - si hay empate, se asignan al sector con más agujeros ocupados por el lote y, si el empate sigue, al primero de la lista.

10a. La causa de las plantas perdidas se elige de la lista de causas de merma que aplican a un lote en pie: plaga, enfermedad, falla de riego o nutrientes, condiciones ambientales, daño mecánico u otra. Opcionalmente puede agregarse una descripción.

13a. El correo al cliente incluye el enlace de acceso temporal, las cantidades solicitada y disponible de cada detalle afectado y la fecha pactada.

14a. La notificación al Agrónomo y al Vendedor se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.

**Frecuencia:** una vez por cada orden de cosecha planificada, ya sea por el Agrónomo o por InfoPonia. La frecuencia real está a confirmar con el Jardín Botánico.

**Temas abiertos:**

  - Falta definir el caso de uso con el que el cliente, a través del enlace de acceso temporal, decide si acepta la cantidad disponible (Decidir Faltante).
  - ¿Qué pasa con las órdenes de cosecha "a realizar" cuya fecha programada pasó sin concretarse?

## Cambios ya decididos que se aplican (PCU, secciones 5 y 11)

1. **PROD-PNF-CSC nombra a PROD-MOD-CSC** como el caso de uso para corregir una cosecha ya planificada (PCU 11). Va en «Relaciones»: «Lo
   sigue: PROD-MOD-CSC · Modificar Cosecha, para cambiar la fecha, la prioridad, la descripción o los lotes sin cancelarla».
2. **PROD-CNC-CSC sin el tema abierto de Decidir Faltante** (PCU 5, contradicción C10): COM-DCD-FLT ya existe
   (`docs/casos_de_uso/comercial/faltante.md`). El enlace del correo de la extensión 13a es el de ese caso de uso.
3. **PROD-CNL-ORD 4c, punto 2** dice «Validar o Modificar Cosecha Automática»: es **PROD-MOD-CSC**, que vale para toda cosecha pendiente
   (PCU 11). Se aplica igual en la ventana de cancelar (`cancelar_orden.md`).

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57, D-59, D-61, D-64)

**El código va en `comercial`** (D-59, regla A3): los tres casos de uso crean o cambian reservas. Lo físico (lotes, partidas, bitácora,
movimientos de stock) lo escriben las funciones de núcleo de `produccion` (`docs/api/produccion.md`, sección 8; D-64 punto 2). Servicios:
`comercial/servicios/cosechas.py`. Bloqueos: `docs/patrones/bloqueos.md`, sección `comercial` («Cosecha y cámara»). Fuera de esta ronda ·
contabilidad (D-57): las precondiciones c y d y la postcondición f de PROD-CNC-CSC (asientos); el movimiento de stock **sí** se registra,
con su costo, para que el asiento pueda originarse en él cuando exista contabilidad.

### PROD-PNF-CSC · Planificar Cosecha

- **Funciones:** `invernaderos_para_cosechar(actor)`, `detalles_cubribles(actor, invernadero_id)`, `variedades_sin_contrato(actor,
  invernadero_id)`, `lotes_cosechables(invernadero_id, variedad_id, fecha_programada)`, `verificar_cosecha(actor, datos)` (lectura, para el
  recálculo de la pantalla y el resumen) y `planificar_cosecha(actor, datos) -> Cosecha`.
- **Permisos (precondiciones a y b):** el Agrónomo a cargo de invernaderos **activos**. El Gerente no planifica (en Producción es de solo
  lectura, como en «Producción 1»). Cualquier otro rol: 403.
- **3a y 3b:** sin Capataz activo (asignado y con la cuenta activa) o sin lotes cosechables, el invernadero se muestra deshabilitado con su
  motivo, y el servicio rechaza con `sin_capataz` o `sin_stock_maduro`.
- **Detalles cubribles (paso 4, regla «Detalle cubrible»):**
  - compra-venta: detalle «abierto» de una venta «abierta»; con retiro, solo si el invernadero es el de retiro; con envío, solo si el
    Vendedor del contrato es el del invernadero; cantidad sin cubrir > 0;
  - suministro: un **período** (`Periodo(detalle, fecha)`) de un detalle que tiene cantidad sin cubrir (vigente o, por D-64 punto 8,
    finalizado con la fecha ≤ `fecha_fin_detalle`), con `hoy <= fecha <= hoy + dias_horizonte_cosecha` (configuración), Vendedor del
    contrato = Vendedor del invernadero; cantidad sin cubrir > 0 (`sin_cubrir_de_periodos`, una consulta para todos);
  - orden: fecha de entrega, después compra-ventas antes que períodos con la misma fecha (no lo dice el CU: es el orden de la pantalla, sin
    efecto en las reglas), después el código del contrato. Búsqueda por cliente o variedad (5a de la lista de tecnología).
- **Fechas (pasos 7 y 8):** prioridad obligatoria, «media» propuesta (7b); descripción opcional, hasta 500 (la de `OrdenTrabajo`). 8a
  `fecha_pasada`; 8b `vence_antes_de_la_entrega` con la primera fecha admitida = `fecha_entrega − duracion_post_cosecha`; 8c es una
  **advertencia** (`retraso`) que no impide seguir, con el texto de suministro cuando corresponde. Sin contrato (4a) solo 8a.
- **Lotes (pasos 9 a 11):** lote cosechable = activo, del invernadero y de la variedad, con etapa actual de tipo Maduración y stock libre > 0
  (`stock_maduro.reservado_de_lotes`). Fecha máxima de cosecha (`lotes.fecha_maxima_de_cosecha`): advertencia 11c con los días de exceso,
  al asignar y en el resumen. 11a `supera_stock_libre`; 11b `supera_sin_cubrir` (solo con contrato); 12b `sin_lotes`. 12a (queda sin cubrir) es
  un aviso.
- **15a (duplicado):** se rechaza con `cosecha_duplicada` (con el código de la existente) si hay otra cosecha **«a realizar»** del mismo
  invernadero, variedad, fecha programada, prioridad, descripción, Agrónomo y detalle (o período, o sin contrato), con las mismas líneas
  (lote y cantidad). «Todos sus atributos» incluye la fecha de creación: dos iguales del mismo día. Se verifica después de bloquear.
- **15b y registro (paso 15):** se bloquea en el orden del patrón (cuentas → el invernadero → la variedad → los sectores de los lotes → los
  lotes → con contrato, el contrato y el detalle), **se releen** y se vuelve a verificar todo (Capataz activo, lote cosechable, stock libre,
  cantidad sin cubrir, detalle cubrible). Si algo cambió: `ValidationError` con el código del dato y nada registrado. Se crean:
  - la `Cosecha` «a realizar» (`origen_cosecha = manual`, `agronomo` = el actor, `capataz` = el del invernadero, número de la secuencia
    `OT-…`);
  - una `ReservaStock` «activa» con `fecha_reserva` = hoy, el invernadero y, con contrato, el detalle (o el detalle de suministro) y
    `fecha_entrega_reserva` (la pactada o la del período); sin contrato, sin detalle y sin fecha (D-64 punto 6);
  - una `DetalleReserva` por lote, con su cantidad y sin cantidad cosechada.
- **Avisos (paso 16):** dentro de la transacción (D-42), sin reintento (16a y 16b: no hay cola): al Capataz, «Nueva cosecha OT-0051»,
  «<Variedad>: <N> plantas para el <dd/mm/aaaa> en <invernadero>. Planificó <Agrónomo>.»; con contrato, al Vendedor del contrato, «Cosecha
  planificada para CV-0044», «<N> plantas de <Variedad> para el <dd/mm>. El detalle queda con <M> plantas sin cubrir.» (postcondición h).
  Sin Capataz activo no se llega acá (3a).
- **Auditoría (i y j):** un registro, acción nueva `planificacion_cosecha`, con la cosecha, la reserva y sus líneas.

### PROD-MOD-CSC · Modificar Cosecha

- **Funciones:** `cosechas_modificables(actor)`, `datos_de_modificacion(actor, cosecha_id)`, `verificar_modificacion(actor, cosecha_id,
  datos)` y `modificar_cosecha(actor, cosecha_id, datos, huella)`.
- **Cosechas (paso 2):** las «a realizar» de los invernaderos del Agrónomo, de cualquier origen, ordenadas por fecha programada; muestra el
  origen (`origen_cosecha`). 2a: la notificación de una cosecha automática lleva directo a la cosecha.
- **Qué se modifica (pasos 5 y 6, 5a a 5c):** fecha programada, prioridad, descripción y el reparto entre lotes. 5c: la pantalla no ofrece
  cambiar variedad, invernadero, contrato ni total; si llegan en el POST, `no_modificable`.
- **Lotes (5b):** los cosechables de la misma variedad e invernadero; el stock libre de cada uno **suma lo que ya reserva esta cosecha**.
  5b.4a `total_distinto` (hasta que coincidan no se puede terminar); 5b.4b `supera_stock_libre`; 5b.4c es el aviso cuando los lotes no
  alcanzan, con el enlace a «Cancelar cosecha». Las líneas de lotes quitados **se borran** (postcondición b: una línea de lote de una
  reserva «activa» no tiene historia que conservar; el cambio queda en la auditoría) y las nuevas se crean.
- **Fechas (6a a 6d):** las mismas de PROD-PNF-CSC (6a y 6b bloquean; 6c y 6d advierten); la fecha de entrega de la reserva **no cambia**
  (postcondición c).
- **7a:** sin cambios, `sin_cambios`.
- **Registro (paso 10, 10a, 10b):** huella (`huella_de(cosecha)`: estado, fecha, prioridad, descripción y líneas) leída al abrir; al
  registrar se bloquea en el orden del patrón (con la fila de la cosecha antes que su reserva), se relee y, si la cosecha ya no está «a
  realizar», `cosecha_resuelta` (10a); si la huella cambió, `cosecha_cambio`; si un lote ya no tiene stock libre, `supera_stock_libre` con los
  lotes (10b).
- **Avisos (paso 11):** al Capataz siempre, «Cosecha OT-0051 modificada», con lo que cambió; con 6c mantenida, al Vendedor del contrato,
  «Cosecha de CV-0044 con retraso», y en un suministro el texto de la posible queja o indemnización. Dentro de la transacción.
- **Auditoría (f):** un registro, acción nueva `modificacion_cosecha`, con cada cambio (valor anterior y nuevo) y las líneas creadas,
  cambiadas y borradas.

### PROD-CNC-CSC · Concretar Cosecha

- **Funciones:** `datos_de_concrecion(actor, cosecha_id)` (con la propuesta por sector), `verificar_concrecion(actor, cosecha_id, datos)`,
  `concretar_cosecha(actor, cosecha_id, datos) -> ResultadoConcrecion`.
- **Quién:** solo el Capataz asignado a la cosecha (`Cosecha.capataz`) con la cuenta activa; cualquier otro, 403. La bandeja (PRD-01) la
  lista por `ordenes_del_capataz` (COM-02 ya suma `Cosecha`); el botón «Concretar» sale de `registrar_acciones_de_cosecha` (D-64 punto 11).
  Orden de la bandeja: el de PRD-01 (fecha programada, prioridad, id); el paso 2 del CU dice «prioridad y después fecha»: **manda la
  bandeja**, que agrupa por «Vencidas», «Hoy» y «Próximas» y ya tiene un orden único para todas las órdenes (anotado en
  `docs/temas_abiertos.md`).
- **Propuesta por sector (pasos 4 y 7a de la lista de tecnología):** la cantidad reservada del lote repartida según los agujeros ocupados
  por el lote en cada sector (ocupaciones vigentes, `lotes.sectores_de_origen`), por **resto mayor**; con empate, el sector con más agujeros
  ocupados y después el primero de la lista (orden por `id` de sector). Si `transiciones.repartir_proporcional` (PRD-02) desempata igual, se
  usa esa; si no, una función pura nueva con sus pruebas de tabla.
- **Validaciones:** 6a `fecha_futura`, 6b `fecha_antes_de_creacion` (entre la creación de la orden y hoy, ambas inclusive); 8a
  `supera_sector`; 8b `supera_maximo` con el máximo = reservado del lote en esta cosecha + su stock libre (sin contar esta reserva); 10a.3a
  `supera_no_cosechadas` (por lote) o `supera_sector` (por sector, contra lo que queda en el sector **después** de la cosecha); 10a.3b
  `causa_obligatoria`. Causas de 10a: las de lote en pie **sin** «descarte por selección» (10a de la lista de tecnología).
- **Registro (paso 13), en una transacción, en este orden:**
  1. bloqueos (cuentas → invernadero → variedad → sectores de los lotes → lotes → partidas candidatas si hay faltante → contrato y detalle →
     la cosecha → su reserva y sus líneas), relectura y 13b (`orden_no_a_realizar`) y 13c (`supera_maximo` con el máximo nuevo);
  2. por cada lote, `cosechas.cosechar_lote` (cantidad por sector, fecha efectiva, el Capataz como responsable) y la línea con su
     `cantidad_cosechada` (b, c, d, e, g);
  3. por cada lote con plantas perdidas, `mermas.aplicar_merma(..., por_sector=…, sector_ids=…)` (m, extensión 10a), con la fecha y hora
     actuales y la etapa actual del lote: la merma de una cosecha es una merma de lote en pie y **sí** cuenta para el umbral;
  4. `cosechas.concretar_orden(cosecha, fecha_efectiva)` (a);
  5. la reserva (h, j): con contrato, «lista para entrega», salvo que su cubierto total sea 0 → «liberada»; sin contrato, «liberada»;
  6. las partidas (i, j), con `camara.crear_partida`, `fecha_cosecha` = `fecha_ingreso` = la efectiva y el costo de la salida del lote: con
     contrato, una por lote con excedente (`excedente_de_cosecha`, cantidad = cosechada − reservada); sin contrato, una por lote con cosechada
     > 0 (`cosecha_del_agronomo`). Origen del movimiento: la cosecha;
  7. con contrato y faltante (13a, regla «Faltante»), `stock_maduro.asignar(Capataz, detalle o período, faltante, fecha_entrega_reserva,
     parametro, origen_cosecha="encadenada")` y lo no cubierto por el camino de faltante (`docs/patrones/stock_maduro.md`, sección 8). Una
     cosecha cuya reserva quedó «liberada» (todo 0) también tiene faltante: el total reservado;
  8. si ingresó producto a la cámara, `transaction.on_commit` con PROD-ASG-CAM para las partidas creadas (k; D-64 punto 9);
  9. postcondición n (planificar la entrega): **se completa en COM-05**.
- **Avisos (paso 14, o):** dentro de la transacción. Al Agrónomo del invernadero (o, sin Agrónomo activo, a nadie: la alerta «sin
  agrónomo» ya existe): «Cosecha OT-0051 concretada», con lo reservado, lo cosechado y lo perdido de cada lote (si no entra en los 500
  caracteres del detalle, los totales y «ver la cosecha»). Con contrato y faltante o excedente, al Vendedor del contrato: «Cosecha de CV-0044:
  faltaron <N>» y, si hubo, «se volvieron a reservar <M>» y «<K> quedan sin cubrir; el cliente recibe un enlace para decidir» (o «el período
  sale con lo disponible»). 14a no aplica (D-42).
- **Auditoría (p, q, r):** un registro, acción nueva `concrecion_cosecha`, con la orden (estado, fechas), las líneas, la reserva, los lotes,
  las ocupaciones y sectores (agujeros antes → después), los movimientos, los registros de bitácora, las partidas, la merma (y sus alertas)
  y lo que creó `asignar` (reservas, líneas, cosechas encadenadas) y el camino de faltante (detalle, venta, enlace). Como en COM-02, lo de
  `asignar` va en este mismo registro (D-36).
- **Tema abierto del CU** («cosechas cuya fecha programada pasó»): la bandeja y la lista las muestran en «Vencidas» (PRD-01). No hay aviso
  automático: queda en `docs/temas_abiertos.md`.

### Lo que completa a COM-02, COM-03 y a `produccion`

- **Bandeja del Capataz y lista de órdenes del Agrónomo** (PRD-01): dejan de excluir las cosechas («hasta COM-04», comentario de COM-02).
  Cada fila de cosecha muestra variedad, total, lotes, contrato y fecha de entrega (`detalle_de_cosechas`, una consulta) y los botones de
  `acciones_de_cosechas`. La vista filtrada por el tipo «Cosecha» suma las columnas «Origen» y «Contrato» y el aviso de la alerta «período sin
  cobertura completa» si el Agrónomo tiene una activa (prototipo `tabCosechas`).
- **Bitácora** (PROD-CNS-BIT, PRD-03): el filtro ofrece el tipo «Cosecha» (disparador «Cuando exista `produccion` completa», punto 3).
- **Notificación de una cosecha automática** (COM-02, COM-03): su enlace lleva a «Modificar cosecha» de esa cosecha (2a de PROD-MOD-CSC)
  para el Agrónomo y a «Concretar» para el Capataz.
- **Panel de control del Agrónomo** (`secCosecha`, PRD-04): suma el grupo «Cosechas» (a realizar hoy, vencidas, sin Capataz) con
  `registrar_seccion_de_inicio`, después de la sección de PRD-04.

## Pantallas

Prototipo: `docs/prototipos/comercial/comercial_y_cosecha.html` (leé su `README.md`; vale la última definición de cada función).

| Pantalla | Funciones | Notas |
|---|---|---|
| Órdenes del Agrónomo con cosechas | `VIEWS.prod`, `ordenesTab`, `tabCosechas`, `MODALS['nueva-orden']` | Es la pantalla de PRD-01: las cosechas se suman a su lista; `tabCosechas` es la vista filtrada por tipo (D-61) |
| Planificar cosecha | `INIT.cscnew`, `VIEWS.cscnew` (y su sobrescritura de la línea 1714), `lotErrs` | Pasos en una página: invernadero → con o sin contrato → detalle o variedad → fecha y prioridad → lotes → resumen |
| Modificar cosecha | `INIT.cscmod`, `VIEWS.cscmod` (y la de la línea 1715) | |
| Cancelar cosecha | `MODALS.cnlcsc` | Va en `cancelar_orden.md` |
| Bandeja y Concretar Cosecha (celular) | `VIEWS.caphome` (la de la línea 1490), `INIT.capcsc` y `VIEWS.capcsc` (las de 1652 y 1657), `capcscCalc`, `reparto` | Carga en pasos: fecha → sectores → plantas perdidas → resumen |
| Panel del Agrónomo | `secCosecha` | Solo el grupo de cosechas (el de envasado es de COM-05) |

### Lo que difiere del prototipo (corregir, D-61)

- `VIEWS.cscnew`: no muestra la **primera fecha admitida** de 8b ni el aviso de retraso de 8c con el texto de suministro; no ofrece la
  búsqueda por cliente o variedad (5a); el error de cantidad mayor que la cantidad sin cubrir (11b) falta. No hay resumen antes de
  confirmar (paso 13): agregar la ventana de resumen (y su página sin JavaScript).
- `VIEWS.cscmod`: falta el **resumen con valor anterior y nuevo** (paso 8) y el aviso 5b.4c con el enlace a cancelar.
- `MODALS.cnlcsc`: no tiene el resumen de lo que se libera ni la estimación de recobertura (6b, 6c): ver `cancelar_orden.md`.
- `VIEWS.capcsc`: la fecha efectiva no valida la fecha de creación (6b); el error 8b (máximo del lote) y 10a.3a por sector faltan; agregar el
  resumen final con el destino de lo cosechado (paso 11: cámara, contrato, faltante).
- `ordenesTab` y `tabCosechas` del prototipo son dos listas; en el sistema es **una** con filtro por tipo (la de PRD-01).

## Para más adelante

- COM-05: planificar la entrega cuando la cosecha deja lista la venta o el período (postcondición n de PROD-CNC-CSC); el envasado.
- Contabilidad (D-57): los asientos de la cosecha, originados en cada movimiento «salida por cosecha» (regla 1 de «Contabilidad» de 8.9).
- Aviso de cosechas vencidas sin concretar (tema abierto de los dos casos de uso).
