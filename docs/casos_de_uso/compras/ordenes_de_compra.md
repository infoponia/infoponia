# Casos de uso · compras · Órdenes de compra

Copia para el repo de CMP-GNR-ODC (v0.2) y CMP-APR-ODC (v0.4), de «CU extendidos» (Drive), el cambio del punto 6 de CMP-APR-ODC y CMP-CNS-ODC (A0, v0.1). Fuentes: Drive «CU extendidos», `CMP-APR-ODC-punto6.md` y `CMP-alto-nivel.md`. Cotejado con `decisiones_A0.md` y `pendientes_para_pegar.md`: **esas decisiones ganan** si algo
difiere (regla del estudiante del 23/11/2026); lo que cambian está en «Actualizaciones de A0 que mandan», al final de cada caso de uso o del
archivo.

**El código va en la app `compras`** (D-37, nivel 6; D-87). Archivos de pruebas bajo `compras/tests/`. Si este archivo y el documento de
Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>`, `test_post_<letra>_<que_espera>` y
`test_ext_<codigo>_<que_espera>`.

---

## **Caso de uso CMP-GNR-ODC: Generar Orden de Compra** 

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
**Módulo:** Compras e Inventario.  
 **Versión:** 0.2

**Actor principal:** Agrónomo que realizó el pedido.

  

**Personal involucrado e intereses:**

  - **Agrónomo:**
      
      - quiere comparar las cotizaciones de los proveedores, por insumo y en conjunto, por precio y por plazo, en un solo lugar;
      - quiere elegir las que convienen sin hacer cuentas;
      - quiere saber si con lo elegido el pedido queda cubierto.
  - **Gerente:**
      
      - quiere recibir una orden ya armada y justificada, con el monto real frente al estimado, para aprobarla o rechazarla;
      - no quiere ser él quien elige a los proveedores.
  - **Proveedor:**
      
      - quiere enterarse si su cotización no fue elegida;
      - si fue elegida, quiere recibir solo sus propias líneas, cuando la compra esté aprobada.
  - **Organización (Jardín Botánico):**
      
      - quiere comprar al mejor precio entre ofertas comparables, sin perder ofertas que lleguen hasta la fecha límite;
      - quiere que quien elige no sea quien aprueba;
      - quiere trazabilidad desde el pedido hasta la orden de compra.

**Relaciones con otros casos de uso:**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - **Disparador:** el aviso de InfoPonia que informa que venció la fecha límite de cotizaciones del pedido.
  - **Lo preceden:** CMP-RLZ-PED · Realizar Pedido y CMP-ENV-COT · Enviar Cotización.
  - **Lo sigue:** la orden generada se aprueba o se rechaza en CMP-APR-ODC · Aprobar Orden de Compra. 
  - **Pedido que no alcanza la cobertura:** se resuelve con Cancelar Pedido, que está por especificar.

**Precondiciones:**

a. El Agrónomo está autenticado en el Sistema.

b. Existe al menos un pedido realizado por el Agrónomo que cumple tres condiciones:

  - está “en cotización”;
  - su fecha límite de cotizaciones ya venció;
  - tiene al menos una cotización “propuesta”.

**Garantías mínimas:**

  - La generación es atómica. Si el caso de uso se cancela o falla:
      
      - el pedido sigue “en cotización” y sus cotizaciones siguen “propuesta”;
      - no se registra ninguna orden de compra, detalle de orden, notificación, correo ni log de auditoría parcial.
  - Un pedido tiene como máximo una orden de compra.
  - Una cotización se elige o se descarta completa, con todas sus líneas.
  - No se genera la orden si algún detalle del pedido no alcanza la cobertura mínima.
  - No se modifica el stock, la cantidad en tránsito ni la contabilidad. La cantidad en tránsito sube recién al aprobarse la orden.
  - Ningún proveedor recibe todavía la orden ni ve las líneas ni las cotizaciones de los demás.

**Garantías de éxito (Postcondiciones):**

a. Se creó una orden de compra con:

  - estado “pendiente de aprobación”;
  - fecha de emisión igual a la fecha actual;
  - monto total igual a la suma de cantidad × precio unitario de sus detalles;
  - las observaciones del Agrónomo, si se indicaron.

b. Se creó un detalle de orden por cada línea de las cotizaciones elegidas. Cada detalle copia la cantidad cotizada y el precio unitario cotizado de su línea, no tiene fecha de entrega esperada y está asociado a esa línea y a su detalle de pedido.

c. Cada cotización elegida pasó a “seleccionada”, y el resto de las cotizaciones “propuesta” del pedido pasó a “descartada”.

d. El pedido pasó de “en cotización” a “cerrado”, con fecha de cierre igual a la fecha actual.

e. Se notificó al Gerente que hay una orden de compra pendiente de aprobación.

f. Se envió a cada proveedor cuya cotización fue descartada un correo que le informa que su cotización no fue seleccionada.

g. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambios de valor del pedido y de cada cotización modificada.

h. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la orden de compra y de cada detalle de orden creado.

**Escenario principal de éxito (o Flujo Básico):**

*(Todos los detalles quedan cubiertos con las cotizaciones elegidas, sin comprar de más.)*

1.  El Agrónomo inicia la generación de una orden de compra.
2.  El Sistema presenta sus pedidos “en cotización” con la fecha límite vencida. Para cada uno indica:
      
      - el identificador;
      - la fecha del pedido;
      - la fecha límite;
      - la cantidad de detalles;
      - la cantidad de cotizaciones recibidas;
      - si las cotizaciones recibidas alcanzan para cubrirlo.
3.  El Agrónomo selecciona un pedido.
4.  El Sistema presenta dos vistas:
      
      - **Las cotizaciones “propuesta” del pedido.** Para cada una muestra el proveedor, sus líneas (insumo, invernadero de destino, cantidad, precio unitario, subtotal y plazo), el monto total, la fecha de validez y las observaciones. 
      - **Por cada detalle del pedido:**
          
          - el insumo, con su unidad, y el invernadero de destino;
          - la cantidad pedida, la cantidad mínima a cubrir y el precio de referencia;
          - una tabla con las líneas que lo cotizan, ordenadas del precio unitario más barato al más caro, con el proveedor, la cantidad, el precio unitario y el plazo.
5.  El Agrónomo elige una cotización.
6.  El Sistema agrega la cotización completa a la selección. En cada detalle que esa cotización cubre, actualiza la suma elegida frente a lo pedido e indica si el detalle quedó cubierto. *El Agrónomo repite los pasos 5 y 6 hasta cubrir todos los detalles.*
7.  El Agrónomo indica que terminó de elegir y, si lo desea, ingresa observaciones para el Gerente.
8.  El Sistema verifica que todos los detalles estén cubiertos.
9.  El Sistema presenta el resumen de la orden:
      
      - por cada proveedor elegido, sus líneas: insumo, invernadero de destino, cantidad, precio unitario, subtotal y plazo;
      - por cada detalle, la cantidad comprada frente a la pedida;
      - el monto total de la orden;
      - el monto estimado del pedido y la diferencia con el total de la orden, en pesos y en porcentaje;
      - las cotizaciones que se descartarán;
      - las observaciones.
10. El Agrónomo confirma la orden.
11. El Sistema registra la orden:
      
      - crea la orden “pendiente de aprobación” con un detalle por cada línea de las cotizaciones elegidas;
      - pasa las cotizaciones elegidas a “seleccionada” y el resto de las “propuesta” a “descartada”;
      - pasa el pedido a “cerrado”;
      - registra la auditoría correspondiente.
12. El Sistema notifica al Gerente la orden pendiente de aprobación y envía el correo de descarte a cada proveedor cuya cotización fue descartada.
13. El Sistema informa al Agrónomo que la orden fue generada y presenta su identificador.

**Extensiones (o Flujos Alternativos):**

**\*a.** En cualquier momento antes del paso 10, el Agrónomo cancela la generación:

1.  El Sistema descarta las elecciones sin registrar ningún cambio. El pedido sigue “en cotización”.

**\*b.** En cualquier momento el Sistema falla o se interrumpe la conexión:

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que la orden no fue generada.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.

**1a.** El Agrónomo inicia la generación desde el aviso de vencimiento de un pedido:

1.  El Sistema presenta directamente ese pedido.
2.  El caso de uso continúa en el paso 4.

**1a1.** El pedido del aviso ya no está “en cotización”:

1.  El Sistema informa el estado del pedido y, si tiene orden, su identificador.
2.  El caso de uso termina.

**4a.** Un detalle del pedido no tiene líneas de cotización, o la suma de todas las líneas que lo cotizan no alcanza la cantidad mínima a cubrir:

1.  El Sistema lo indica en ese detalle (“sin ofertas” u “ofertas insuficientes”) e informa que el pedido no podrá generar una orden.
2.  El Agrónomo abandona la generación. El pedido se resuelve con Cancelar Pedido.

**4b.** El proveedor de una cotización está “inactivo”:

1.  El Sistema muestra la cotización con la indicación “proveedor inactivo” y no permite elegirla.
2.  Si, sin esa cotización, algún detalle no alcanza la cobertura mínima, se aplica la extensión 4a.

**4c.** La fecha de validez de una cotización ya venció:

1.  El Sistema muestra la cotización con la indicación “validez vencida” y no permite elegirla.
2.  Si, sin esa cotización, algún detalle no alcanza la cobertura mínima, se aplica la extensión 4a.

**5a.** El Agrónomo elige desde la tabla de un detalle una línea de cotización:

1.  El Sistema informa que se elige la cotización completa de ese proveedor y presenta todas sus líneas.
2.  El caso de uso continúa en el paso 6.

**6a.** El Agrónomo quita una cotización elegida:

1.  El Sistema la quita completa de la selección y actualiza la suma y la cobertura de cada detalle que cubría.
2.  El caso de uso continúa en el paso 5.

**6b.** Con la cotización elegida, la suma de uno o más detalles supera la cantidad pedida:

1.  El Sistema advierte que en esos detalles se comprará más de lo pedido e informa la diferencia de cada uno.
2.  El Agrónomo mantiene la elección (continúa en el paso 5 o en el 7) o la quita (continúa en 6a).

**8a.** Algún detalle no alcanza la cantidad mínima a cubrir con las cotizaciones elegidas:

1.  El Sistema señala los detalles no cubiertos y cuánto les falta.
2.  El Agrónomo elige más cotizaciones (vuelve al paso 5) o abandona la generación. Si no hay cotizaciones suficientes, se aplica la extensión 4a.

**10a.** El Agrónomo quiere corregir la selección o las observaciones:

1.  El caso de uso vuelve al paso 5 o al paso 7.

**11a.** Al registrar, el pedido ya no está “en cotización”. Por ejemplo, se canceló o se generó su orden en otra sesión:

1.  El Sistema no registra ningún cambio e informa el estado actual del pedido.
2.  El caso de uso termina.

**11b.** Al registrar, el proveedor de una cotización elegida pasó a “inactivo”, o la validez de una cotización elegida venció:

1.  El Sistema no registra ningún cambio e informa qué cotización quedó afectada y por qué.
2.  El caso de uso vuelve al paso 4.

**12a.** El Sistema no logra enviar la notificación al Gerente o un correo de descarte:

1.  La orden permanece registrada.
2.  El Sistema reintenta el envío.

**12b.** No hay un Gerente activo:

1.  La orden queda “pendiente de aprobación” igual.
2.  El Sistema omite la notificación al Gerente.
3.  En el paso 13, el Sistema informa además al Agrónomo que la orden quedará pendiente hasta que haya un Gerente activo.

  

**Requisitos especiales:**

  - La interfaz del Agrónomo está pensada para computadora.
  - La pantalla del paso 4 se presenta en no más de 2 segundos. Tras cada elección (pasos 5 y 6), la cobertura de todos los detalles se actualiza en no más de 1 segundo.
  - El paso 11 se ejecuta como una única transacción y se completa en no más de 5 segundos. La orden, sus detalles, los cambios de estado de las cotizaciones y del pedido, y los logs se registran juntos o no se registra ninguno. La notificación y los correos se envían fuera de la transacción.
  - El control de concurrencia impide que un pedido genere dos órdenes, y que se genere la orden de un pedido mientras se lo cancela.
  - Solo el Agrónomo que realizó el pedido accede a este caso de uso para ese pedido.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios y montos se expresan en pesos argentinos, con dos decimales. La diferencia porcentual se expresa con un decimal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio:**

  - **Aviso de vencimiento (InfoPonia):** al terminar el día de la fecha límite de un pedido “en cotización”, InfoPonia le avisa al Agrónomo del pedido: “venció la fecha límite del pedido N; hay X cotizaciones para revisar”. El aviso indica, por cada detalle, cuántas líneas recibió y si alcanzan la cobertura mínima. Si algún detalle no puede cubrirse, anticipa que el pedido deberá cancelarse. (Regla 12 de 8.16; disparador y extensión 1a)
  - **Pedido resoluble:** un pedido del Agrónomo, “en cotización”, con la fecha límite vencida y al menos una cotización “propuesta”. (Regla 11 de 8.16; pasos 2 y 3)
  - **Agrónomo del pedido:** solo el Agrónomo que realizó el pedido lo resuelve. Si pasa a inactivo o deja de estar a cargo del invernadero de destino, el pedido se cancela (MD-62). (Precondición b) 
  - **Una orden por pedido:** un pedido tiene como máximo una orden de compra, que lo cubre completo y puede incluir varios proveedores. Todos los detalles de la orden pertenecen al mismo pedido. Los proveedores de la orden se obtienen desde sus detalles (línea de cotización → cotización → proveedor). (Regla 13 de 8.16; paso 11)
  - **Cotización elegida completa:** cada proveedor tiene como máximo una cotización por pedido (C8), y esa cotización se elige o se descarta entera, con todas sus líneas. No se pueden elegir líneas sueltas. (Regla 14 de 8.16 y regla 3 de 8.17; pasos 5 y 6, y extensión 5a)
  - **Cobertura mínima de un detalle:** la suma de las cantidades cotizadas en las líneas de las cotizaciones elegidas para ese detalle debe ser mayor o igual que la cantidad pedida × (1 − porcentaje de tolerancia de cobertura). La orden solo se genera si todos los detalles están cubiertos. Si la suma supera lo pedido, se permite, con advertencia. (Regla 14 de 8.16; pasos 6 y 8, y extensiones 4a, 6b y 8a)
      
      - Ejemplo: se piden 20 lechugas y 20 tomates, con 10 % de tolerancia (mínimo 18 de cada uno).
      - A (20 L, 10 T) + B (10 T): se genera.
      - A (15 L, 10 T) + B (10 L, 10 T): se genera, con advertencia de 5 lechugas de más.
      - A (19 L, 10 T) + B (10 T): se genera.
      - A (15 L, 10 T) + B (10 T): no se genera.
  - **Proveedor inactivo:** su cotización se conserva, pero no puede elegirse. (Extensiones 4b y 11b)
  - **Cotización con la validez vencida:** se conserva y se muestra, pero no puede elegirse, igual que la de un proveedor inactivo. La validez se controla al presentarla y también al registrar (MD-64; regla 6 de 8.22). (Paso 4 y extensiones 4c y 11b) 
  - **Presentación:** las cotizaciones se presentan completas. Además, por cada detalle hay una tabla con sus líneas, ordenadas del precio unitario más barato al más caro, junto al precio de referencia y a la cobertura alcanzada. El Sistema no preselecciona ninguna cotización. Un detalle sin líneas se muestra como “sin ofertas”. (Regla 15 de 8.16; paso 4)
  - **Detalles de la orden:** cada línea de una cotización elegida genera un detalle de la orden, que copia su cantidad y su precio unitario. El detalle de pedido de ese detalle de la orden es el mismo que el de la línea. (Regla 16 de 8.16 y regla 5 de 8.17; paso 11)
  - **Resolución en una sola operación:** al confirmar, en una sola operación:
      
      - se genera la orden;
      - las cotizaciones elegidas pasan a “seleccionada”;
      - el resto de las “propuesta” del pedido pasan a “descartada”;
      - el pedido pasa a “cerrado”.
  - (Regla 17 de 8.16; paso 11)
  - **Monto de la orden:** Σ cantidad × precio unitario de sus detalles. El resumen muestra el monto estimado del pedido, el monto real de la orden y la diferencia en pesos y en porcentaje, sin advertencia. (Regla 18 de 8.16; paso 9)
  - **Fecha de entrega esperada:** queda vacía hasta la aprobación. Al aprobarse la orden, se calcula como la fecha de resolución de la orden (fechaResolucion, que en una orden aprobada es la fecha de aprobación) más el plazo de entrega de la línea de cotización de ese detalle. (Regla 23 de 8.16; paso 11) 
  - **Avisos:**
      
      - el Gerente recibe una notificación (no una alerta) por la orden pendiente de aprobación. Si no hay un Gerente activo, la notificación se omite y la orden queda pendiente; el Gerente que se dé de alta la ve entre sus pendientes; 
      - cada proveedor cuya cotización se descartó recibe un correo que le informa que no fue seleccionada;
      - los proveedores seleccionados no reciben nada todavía. Al aprobarse la orden, cada uno recibe solo sus líneas.
  - (Reglas 19 y 20 de 8.16; paso 12)
  - **Cantidad en tránsito:** no cambia en este caso de uso. Sube al aprobarse la orden y baja con cada recepción. (Regla 22 de 8.16; paso 11)

**Lista de tecnología y variaciones de datos:**

4a. Las cantidades se expresan en la unidad de medida del insumo, con hasta dos decimales. El plazo de entrega se expresa en días.

4b. La tolerancia de cobertura es un porcentaje de la configuración operativa.

7a. Las observaciones se ingresan como texto libre.

12a. El correo de descarte indica el pedido, la fecha de la cotización y su monto. No menciona a los otros proveedores ni sus precios.

12b. La notificación al Gerente indica:

  - el identificador de la orden;
  - el pedido;
  - el monto total;
  - la diferencia con el monto estimado;
  - la cantidad de proveedores.

**Frecuencia:** una vez por cada pedido que alcanza la cobertura. Depende de la cantidad de pedidos de insumos.

**Temas abiertos:**

  - Si el Agrónomo no resuelve un pedido vencido, ¿hace falta un recordatorio después de cierta cantidad de días?
  - Hoy, un pedido que no alcanza la cobertura solo puede cancelarse y volver a hacerse. Extender Pedido queda como mejora futura.
  - El estado “cancelada” de la orden de compra queda como mejora futura.
  - Comprar de más solo genera una advertencia. ¿Hace falta un límite?
  - Como cada cotización se elige completa, no se le puede comprar a un proveedor solo parte de lo que cotizó. La elección de líneas sueltas queda como mejora futura.



---

## **Caso de uso CMP-APR-ODC: Aprobar Orden de Compra**

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Compras e Inventario.  
 **Actor principal:** Gerente.  
 **Versión:** 0.4

**Personal involucrado e intereses**

**Gerente:**

  - quiere decidir con todo a la vista: qué se pidió, quién lo pidió, a qué proveedores se les compra, en qué plazos y cuánto cuesta frente a lo estimado;
  - no quiere elegir a los proveedores ni armar la orden: la recibe armada y justificada.

**Agrónomo del pedido:**

  - quiere enterarse de la decisión sobre su orden;
  - si se aprueba, quiere saber cuándo se espera cada entrega;
  - si se rechaza, quiere conocer el motivo para armar el pedido nuevo.

**Proveedor:**

  - si su cotización fue elegida y la orden se aprueba, quiere recibir solo sus líneas, con la fecha de entrega;
  - si la orden se rechaza, quiere enterarse de que su cotización no fue seleccionada.

**Organización (Jardín Botánico):**

  - quiere que quien elige no sea quien aprueba;
  - quiere que ninguna compra se pague ni se espere sin aprobación;
  - quiere trazabilidad desde el pedido hasta el pago de cada proveedor.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - **Disparador:** la notificación de orden pendiente de aprobación que envía CMP-GNR-ODC (paso 12).
  - **Lo precede:** CMP-GNR-ODC · Generar Orden de Compra.
  - **Lo sigue:** si la orden se aprueba, CMP-REG-RCP · Registrar Recepción de Mercadería, que baja la cantidad en tránsito. El pago a cada proveedor se registra después de la recepción, por lo recibido, en un caso de uso aparte (Registrar Pago a Proveedor, a especificar). Si se rechaza, lo no comprado se resuelve con un pedido nuevo (CMP-RLZ-PED · Realizar Pedido). 
  - **Proveedor inactivo:** se trata en la regla de negocio “Proveedor inactivo”.

**Precondiciones**

a. El Gerente está autenticado en el Sistema.  
 b. Existe al menos una orden de compra en estado “pendiente de aprobación”.

**Garantías mínimas**

La resolución es atómica. Si el caso de uso se cancela o falla:

  - la orden sigue “pendiente de aprobación”, sin Gerente asociado ni fecha de resolución;
  - sus cotizaciones siguen “seleccionada” y el pedido sigue “cerrado”;
  - no se registra ningún cambio de la cantidad en tránsito, fecha de entrega esperada, notificación, correo ni log de auditoría parcial.

**Además:**

  - Una orden se resuelve una única vez, y la resuelve un solo Gerente.
  - La orden no se modifica: ni sus líneas, ni sus cantidades, ni sus precios, ni sus proveedores. Se aprueba o se rechaza completa.
  - El pedido sigue “cerrado”, sea cual sea la decisión.
  - No se modifica el stock actual ni las reservas de ningún insumo.
  - Este caso de uso no registra pagos ni asientos contables, en ningún caso.
  - Ningún proveedor ve las líneas ni las cotizaciones de los demás.

**Garantías de éxito (Postcondiciones)**

**En toda orden resuelta:****  
** a. La orden pasó de “pendiente de aprobación” a “aprobada” o “rechazada”. Quedó con la fecha de resolución igual a la fecha actual y asociada al Gerente que la resolvió.  
 b. El pedido siguió “cerrado”.  
 c. Se notificó al Agrónomo que realizó el pedido la decisión y, si la orden fue rechazada, su motivo.  
 d. Las alertas de insumo bajo el mínimo de los insumos de la orden no cambiaron: siguen activas hasta que se resuelvan al registrar la recepción (CMP-REG-RCP). 

**Si la orden fue aprobada:****  
** e. Cada detalle de la orden quedó con su fecha de entrega esperada, igual a la fecha de resolución más el plazo de entrega de su línea de cotización.  
 f. La cantidad en tránsito del InsumoInvernadero de destino de cada detalle aumentó en la cantidad del detalle. Si varios detalles de la orden cubren un mismo detalle del pedido, aumentó en la suma de sus cantidades.  
 g. Las cotizaciones de la orden siguieron “seleccionada”.  
 h. Se envió a cada proveedor de la orden un correo con las líneas que le corresponden, sin las de los demás proveedores.

**Si la orden fue rechazada:****  
** i. Quedó registrado el motivo del rechazo.  
 j. Las cotizaciones seleccionadas de la orden pasaron a “descartada”.  
 k. Se envió a cada proveedor de la orden un correo que le informa que su cotización no fue seleccionada.  
 l. No cambió la cantidad en tránsito de ningún insumo ni la fecha de entrega esperada de ningún detalle.

**Auditoría:****  
** m. Se creó un log de auditoría por la orden y por cada cotización, InsumoInvernadero y detalle de la orden modificados, con usuario, rol, fecha, hora, identificador y cambios de valor.

**Escenario principal de éxito (o Flujo Básico)**

(Aprobación de una orden pendiente, sin cambios entre la presentación y el registro.)

1.  **El Gerente inicia la aprobación de órdenes de compra.**
2.  **El Sistema presenta las órdenes “pendiente de aprobación”, de la más antigua a la más reciente. Para cada una indica:**
      
      - el identificador;
      - la fecha de emisión;
      - el pedido y el Agrónomo que lo realizó;
      - la cantidad de proveedores;
      - el monto total.
3.  **El Gerente selecciona una orden.**
4.  **El Sistema presenta la información para decidir:**
      
      - el pedido (identificador, fecha y fecha límite de cotizaciones), el Agrónomo que lo realizó y las observaciones que dejó, si las hay;
      - por cada proveedor, sus líneas (insumo, invernadero de destino, cantidad, precio unitario, subtotal y plazo de entrega) y el monto total de sus líneas;
      - por cada detalle del pedido, la cantidad comprada frente a la pedida;
      - el monto total de la orden, el monto estimado del pedido y la diferencia entre ambos, en pesos y en porcentaje.
5.  **El Gerente decide aprobar la orden.**
6.  **El Sistema verifica los datos y presenta el resumen de la aprobación:**
      
      - la fecha de entrega esperada de cada línea;
      - cómo subirá la cantidad en tránsito de cada insumo en cada invernadero;
      - que cada proveedor recibirá solo sus líneas;
      - que la aprobación no registra ningún pago: el pago a cada proveedor se registra después de recibir la mercadería.
7.  **El Gerente confirma la aprobación.**
8.  **El Sistema registra la aprobación:**
      
      - pasa la orden a “aprobada”, con la fecha de resolución y el Gerente;
      - calcula la fecha de entrega esperada de cada detalle;
      - sube la cantidad en tránsito de cada insumo en cada invernadero de destino;
      - registra la auditoría correspondiente.
9.  **El Sistema notifica al Agrónomo del pedido la aprobación y envía a cada proveedor de la orden un correo con sus líneas.**
10. **El Sistema informa al Gerente que la orden fue aprobada.**

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 7, o paso 5a.4 si rechaza), el Gerente cancela la resolución:**

1.  **El Sistema descarta los datos ingresados sin registrar ningún cambio. La orden sigue “pendiente de aprobación”.**

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1.  **El Sistema revierte cualquier registro parcial de la operación.**
2.  **Al restablecerse, el Sistema informa al Gerente que la orden no fue resuelta.**
3.  **El Gerente reinicia el caso de uso desde el paso 1.**

**1a. El Gerente inicia la resolución desde la notificación de la orden pendiente:**

1.  **El Sistema presenta directamente esa orden.**
2.  **El caso de uso continúa en el paso 4.**

**1a1. La orden de la notificación ya no está “pendiente de aprobación”:**

1.  **El Sistema informa la decisión tomada, el Gerente que la tomó, la fecha de resolución y, si fue rechazada, el motivo.**
2.  **El caso de uso termina.**

**4a. Alguna línea de la orden es de un invernadero “inactivo”, o de un insumo “inactivo” en su invernadero de destino:**

1.  **El Sistema señala las líneas afectadas (“invernadero inactivo” o “insumo inactivo en el invernadero”) e informa que la orden no puede aprobarse.**
2.  **El Gerente rechaza la orden (continúa en 5a) o abandona el caso de uso. En ese caso, la orden sigue “pendiente de aprobación”.**

**5a. El Gerente decide rechazar la orden:**

1.  **El Sistema solicita el motivo del rechazo.**
2.  **El Gerente ingresa el motivo.**
3.  **El Sistema presenta el resumen del rechazo:**
      
      - el motivo;
      - las cotizaciones que pasarán a “descartada” y los proveedores a los que se les avisará;
      - que no cambiará la cantidad en tránsito;
      - que el pedido seguirá “cerrado” y que lo no comprado se resuelve con un pedido nuevo.
4.  **El Gerente confirma el rechazo.**
5.  **El Sistema registra el rechazo:**
      
      - pasa la orden a “rechazada”, con la fecha de resolución, el Gerente y el motivo;
      - pasa las cotizaciones seleccionadas de la orden a “descartada”;
      - registra la auditoría correspondiente.
6.  **El Sistema notifica al Agrónomo del pedido el rechazo y su motivo, y envía a cada proveedor de la orden un correo que le informa que su cotización no fue seleccionada.**
7.  **El Sistema informa al Gerente que la orden fue rechazada y el caso de uso termina.**

  

**4b. Alguna cotización de la orden tiene la fecha de validez vencida:**

1.  **\*\*El Sistema señala las cotizaciones afectadas (“validez vencida”) e informa que la orden no puede aprobarse.\*\***
2.  **\*\*El Gerente rechaza la orden (continúa en 5a) o abandona el caso de uso. En ese caso, la orden sigue “pendiente de aprobación”.\*\***

  

**5a.4a. El Gerente quiere cambiar el motivo o su decisión:**

1.  **El caso de uso vuelve al paso 5a.2 (cambiar el motivo) o al paso 5 (aprobar en lugar de rechazar).**

**5a.5a. Al registrar el rechazo, la orden ya no está “pendiente de aprobación”:**

1.  **Se aplica la extensión 8a.**

**5a.6a. El Sistema no logra enviar la notificación al Agrónomo o un correo a un proveedor:**

1.  **El rechazo permanece registrado.**
2.  **El Sistema reintenta el envío.**

**5b. El Gerente rechaza la orden sin ingresar el motivo:**

1.  **El Sistema señala que el motivo es obligatorio al rechazar.**
2.  **El Gerente ingresa el motivo (vuelve a 5a.2).**

**7a. El Gerente quiere cambiar su decisión (rechazar en lugar de aprobar):**

1.  **El caso de uso continúa en el paso 5a.**

**8a. Al registrar, la orden ya no está “pendiente de aprobación” (por ejemplo, el Gerente ya la resolvió desde otra sesión):** 

1.  **El Sistema no registra ningún cambio e informa la decisión tomada, el Gerente que la tomó y la fecha de resolución.**
2.  **El caso de uso termina.**

**8b. Al registrar la aprobación, algún invernadero o insumo de destino de la orden pasó a “inactivo”, o venció la validez de alguna cotización de la orden:**

1.  **\*\*El Sistema no registra ningún cambio e informa qué líneas o cotizaciones quedaron afectadas y por qué.\*\***
2.  **\*\*El caso de uso vuelve al paso 4, donde se aplica la extensión 4a o la 4b.\*\***

**9a. El Sistema no logra enviar la notificación al Agrónomo o un correo a un proveedor:**

1.  **La aprobación permanece registrada.**
2.  **El Sistema reintenta el envío.**

**Requisitos especiales**

  - La interfaz del Gerente está pensada para computadora.
  - La información del paso 4 se presenta en no más de 2 segundos desde la selección.
  - El registro del paso 8 (y el del paso 5a.5) se completa en no más de 5 segundos.
  - El registro se ejecuta como una única transacción. La orden, sus detalles, las cotizaciones, la cantidad en tránsito y los logs se registran juntos o no se registra ninguno. Las notificaciones y los correos se envían fuera de la transacción.
  - El control de concurrencia cumple tres funciones:
      
      - impide que una orden se resuelva dos veces;
      - impide que dos aprobaciones simultáneas de órdenes con el mismo insumo en el mismo invernadero pierdan un aumento de la cantidad en tránsito;
      - impide que se apruebe una orden mientras se da de baja un invernadero o un insumo de destino.
  - Solo los usuarios con rol Gerente acceden a este caso de uso.
  - La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios y montos se expresan en pesos argentinos, con dos decimales. La diferencia porcentual se expresa con un decimal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

  - **Orden resoluble:** la que está en estado “pendiente de aprobación”. La resuelve el Gerente, y queda asociado el que la resolvió. Una orden tiene Gerente y fecha de resolución si y solo si está resuelta. (R011; pasos 2 y 3) 
  - **El Gerente no elige:** la orden llega armada por el Agrónomo del pedido. El Gerente no genera órdenes ni elige proveedores: las aprueba o las rechaza. (Regla 11 de 8.16)
  - **Decisión total:** el Gerente aprueba o rechaza la orden completa. No quita líneas, ni cambia cantidades, precios o proveedores. La aprobación parcial queda como mejora futura. (Paso 5 y extensión 5a)
  - **Estados de la orden:** nace “pendiente de aprobación” y pasa a “aprobada” o “rechazada”. Una orden resuelta no vuelve a resolverse. Los estados “parcialmente recibida”, “recibida” y “recibida con faltante” se aplican en CMP-REG-RCP · Registrar Recepción de Mercadería. (Regla 24 de 8.16; paso 8).
  - **Estado del pedido:** el pedido sigue “cerrado” tanto si la orden se aprueba como si se rechaza. Si se rechaza, lo no comprado se resuelve con un pedido nuevo. (Regla 24 de 8.16)
  - **Destino inactivo:** una orden con alguna línea de un invernadero “inactivo”, o de un insumo “inactivo” en su invernadero, no puede aprobarse: el Sistema lo advierte y no lo permite. Solo puede rechazarse, o dejarse pendiente. Esto puede ocurrir porque la baja de un invernadero o de un insumo de invernadero solo exige stock actual igual a cero (reglas 3 y 4 de 8.4) y no considera la mercadería pedida. (Extensiones 4a y 8b)
  - **Proveedor inactivo:** este caso de uso no tiene extensión para ese caso, porque no ocurre: no se permite dar de baja a un proveedor que tiene una cotización “seleccionada” en una orden sin resolver o aprobada. (Regla de la baja de Proveedor, a especificar; ver tema abierto)
  - **Rechazo:** el motivo es obligatorio y se ingresa como texto libre. Al rechazar, las cotizaciones seleccionadas de la orden pasan a “descartada” y cada uno de sus proveedores recibe un correo que le informa que su cotización no fue seleccionada. Una orden rechazada no se reabre. (Regla 24 de 8.16 y regla 5 de 8.18; extensiones 5a y 5b)
  - **Pago diferido:** aprobar la orden no registra pagos ni asientos contables. El pago a cada proveedor se registra después de recibir la mercadería, por lo efectivamente recibido y no por lo pedido, en un caso de uso aparte (Registrar Pago a Proveedor, a especificar). Si la orden se rechaza, no hay pagos. (MD-03 y MD-26, confirmada el 28/10/2026; pasos 6 y 8)
  - **Fecha de entrega esperada:** queda vacía hasta la aprobación. Al aprobar, es la fecha de resolución (en una orden aprobada, su fecha de aprobación) más el plazo de entrega de la línea de cotización de ese detalle. Por ejemplo, aprobada el 26/10 con un plazo de 5 días, se espera el 31/10. (Regla 23 de 8.16; paso 8)
  - **Cantidad en tránsito:** al aprobar, sube en el InsumoInvernadero del insumo y del invernadero de destino de cada detalle, en la cantidad del detalle de la orden. Las líneas de distintos proveedores que cubren un mismo detalle del pedido suman en el mismo InsumoInvernadero. Baja con cada recepción. Si se rechaza, no cambia. (Regla 22 de 8.16; paso 8)
  - **Alerta de insumo bajo el mínimo:** aprobar la orden no la resuelve, aunque la cantidad en tránsito aumente. Se resuelve al registrar la recepción. (Glosario, “Insumo bajo el mínimo”; postcondición d)
  - **Avisos:** (Reglas 19 y 20 de 8.16 y regla 5 de 8.18; pasos 9 y 5a.6)
      
      - el Agrónomo del pedido recibe una notificación (no una alerta) con la decisión y, si se rechazó, el motivo;
      - si la orden se aprueba, cada proveedor recibe un correo con solo sus líneas;
      - si se rechaza, cada proveedor de la orden recibe un correo que le informa que su cotización no fue seleccionada;
      - los proveedores cuyas cotizaciones se descartaron al generar la orden ya fueron avisados en CMP-GNR-ODC y no reciben nada ahora.
  - **Cotización vencida:** una orden con alguna cotización cuya fecha de validez venció no puede aprobarse: el Sistema lo advierte y no lo permite. Solo puede rechazarse, o dejarse pendiente; lo pedido se resuelve con un pedido nuevo. La validez se controla al presentar la orden y también al registrar. (Regla 6 de 8.22 y regla 24 de 8.16; extensiones 4b y 8b) 

**Lista de tecnología y variaciones de datos**

  - **4a.** El monto total y el monto de cada proveedor se expresan en pesos. Las cantidades se expresan en la unidad de medida del insumo, con hasta dos decimales, y el plazo de entrega en días.
  - **5a.2.** El motivo del rechazo es texto libre.
  - **9a.** El correo a cada proveedor cuya cotización se aprobó indica:
      
      - el identificador de la orden;
      - sus líneas: insumo, cantidad, precio unitario y subtotal;
      - el invernadero de destino, con su dirección;
      - la fecha de entrega esperada de cada línea;
      - el total de sus líneas.
  - No menciona a los otros proveedores ni sus líneas.
  - **9b.** La notificación al Agrónomo indica el identificador de la orden, el pedido, la decisión y el monto total y, si se aprobó, las fechas de entrega esperadas.
  - **5a.6.** La notificación al Agrónomo por un rechazo indica además el motivo. El correo a cada proveedor indica el pedido, la fecha de su cotización y su monto. No incluye el motivo del rechazo ni menciona a los otros proveedores.

**Frecuencia**

Una vez por cada orden de compra generada. Depende de la cantidad de pedidos que alcanzan la cobertura.

**Temas abiertos**

  - Si el Gerente no resuelve una orden pendiente, ¿hace falta un recordatorio después de cierta cantidad de días?
  - El Gerente solo aprÚltima actualización: 14/11/2026 (DSS-10: Concretar Siembra, versión 0.4). Antes: ueba o rechaza la orden completa. Si quiere comprar solo a algunos proveedores, tiene que rechazarla y se hace un pedido nuevo. La aprobación parcial queda como mejora futura (relacionada con la elección parcial de una cotización, MD-29).
  - Una orden con un destino inactivo solo puede rechazarse o quedar pendiente. ¿Hace falta una forma de reactivar el invernadero o el insumo desde este caso de uso? Además, las reglas 3 y 4 de 8.4 no impiden dar de baja un destino que tiene mercadería en tránsito o una orden aprobada sin recibir. ¿Hay que agregarlo a esas reglas?
  - Hay que especificar el caso de uso Registrar Pago a Proveedor: quién lo ejecuta y a quién se avisa (caso por especificar 20 de pendientes\_CU). Lo pedido y no recibido no se paga: si el proveedor no manda el resto, el Agrónomo cierra el detalle con faltante, que es un estado del detalle de la orden con un motivo obligatorio (MD-26; regla 8 de 8.20). 
  - La baja de un Proveedor hoy considera las cotizaciones “seleccionada” de órdenes sin resolver o aprobadas. ¿Debe considerar también las recibidas con pago pendiente?
  - Una decisión no puede revisarse. ¿Hace falta una forma de anularla ante un error? El estado “cancelada” de la orden de compra queda como mejora futura.

<!-- end list -->

  - Si el Agrónomo del pedido pasó a inactivo o dejó el invernadero de destino, ¿a quién van las notificaciones de los pasos 9 y 5a.6? La regla 5 de 8.22 (MD-62) las manda al Agrónomo activo del invernadero de destino o, si no hay, al Gerente. Falta precisar qué pasa si los invernaderos de destino quedaron a cargo de Agrónomos distintos, y si hace falta avisar al Gerente cuando es él quien resolvió la orden. Está en revisión en el modelo. 



---

# CMP-APR-ODC · Cambio del punto 6 de «Actualizaciones pendientes» (H21, cierra MD-67)

Texto para reemplazar el tema abierto de CMP-APR-ODC (CU extendidos, temas abiertos: «Si el Agrónomo del pedido pasó a inactivo o dejó el invernadero de destino, ¿a quién van las notificaciones…?») y el punto 6 de pendientes_CU › Actualizaciones, CMP-APR-ODC. Decisión de Ezequiel del 23/11/2026 (decisiones_A0.md, H21). Fuente del punto: PCU › CMP-APR-ODC, «Actualizaciones pendientes», punto 6.

**Regla nueva «Destinatarios de los avisos de la orden»** (pasos 9 y 5a.6, aprobación y rechazo):
1. Cada aviso va a cada Agrónomo activo de los invernaderos de destino que la orden involucra (uno o varios). 
2. Por cada invernadero de destino sin Agrónomo activo, el aviso va al Gerente.
3. Nunca se notifica a quien hizo la acción: si el Gerente resolvió la orden, no recibe su propio aviso, aunque sea el respaldo de un destino sin Agrónomo.
4. «El Agrónomo del pedido ya no está» incluye al Agrónomo inactivo y al activo que dejó de estar a cargo del invernadero de destino (criterio de MD-62).

**Quitar** el tema abierto de CMP-APR-ODC y marcar el punto 6 de PCU como resuelto (✔️, 23/11/2026, H21). Regla 5 de 8.22 de MD: agregar que los avisos siguen la regla anterior; la cancelación del pedido (MD-62) no cambia.

**Otros casos de uso afectados:** CMP-GNR-ODC (el aviso de vencimiento y los demás avisos al Agrónomo del pedido, PCU, «avisos al Agrónomo del pedido»), y cualquier aviso nuevo de compras: se rige por la misma regla general («nunca se notifica a quien hizo la acción»).


---

## **Caso de uso CMP-CNS-ODC: Consultar Orden de Compra**

Caso de uso nuevo (el contexto, sección 3.1, lo propone junto con CMP-CNS-PED: «ningún caso de uso deja ver el historial de compras»), con recepciones, pagos y reclamos.

**Actores:** Agrónomo, Gerente o Contador.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver el estado y la historia completa de una orden de compra: qué se compró a cada proveedor, qué llegó, qué se pagó y qué reclamos hay.

**Precondición:**

a. El actor está identificado con una cuenta activa de Agrónomo, de Gerente o de Contador.

**Postcondición:**

a. Ninguna: es una consulta, no modifica datos ni registra auditoría.

**Reglas:**

1.  Alcance: el Agrónomo ve las órdenes con destino en los invernaderos que tiene a cargo. El Gerente ve todas. El Contador ve todas, en solo lectura, para seguir los pagos.
2.  Filtros: estado (pendiente de aprobación, aprobada, rechazada, parcialmente recibida, recibida, recibida con faltante), proveedor, invernadero de destino, rango de fechas y, para el Gerente, Agrónomo del pedido. Atajos: «por aprobar», «por recibir», «con pago pendiente» y «con reclamo sin emitir».
3.  Listado: identificador, pedido de origen, fecha, monto, proveedores, estado, y marcas de líneas atrasadas, pago pendiente o reclamo sin emitir.
4.  Ficha · orden: el pedido de origen y su Agrónomo; el monto; el estado; si se resolvió, el Gerente que la resolvió, la fecha de resolución, las observaciones del Agrónomo y, si se rechazó, el motivo.
5.  Ficha · líneas: por cada proveedor e invernadero de destino, las líneas con insumo, cantidad pedida, recibida y pendiente, precio unitario, fecha de entrega esperada (con los días de atraso si corresponde) y estado (pendiente, completo, cerrado con faltante; con el motivo del cierre).
6.  Ficha · recepciones: cada recepción con fecha, quién la registró (Agrónomo o, si está vacío, el Gerente por auditoría), las cantidades recibidas, los lotes ingresados con su vencimiento y las observaciones.
7.  Ficha · pagos y reclamos: por cada proveedor, el pago (fecha, medio, monto) o que está pendiente; y sus reclamos con sus inconvenientes, el estado (abierto o cerrado) y si están emitidos o sin emitir.
8.  Acciones desde la ficha, según el actor y el estado: Aprobar Orden de Compra (CMP-APR-ODC, solo el Gerente, si está pendiente de aprobación); Registrar Recepción (CMP-REG-RCP, el Agrónomo a cargo o, si no está, el Gerente); Registrar Pago a Proveedor (CMP-REG-PAG, el Contador o, sin Contador, el Gerente); y, Cerrar Detalle con Faltante (CMP-CRR-FLT), Emitir y Cerrar Reclamo (CMP-EMT-RCL, CMP-CRR-RCL, el Gerente) y Corregir Recepción (CMP-COR-RCP, el Agrónomo).
9.  Las alertas y notificaciones de compras (orden pendiente de aprobación, recepción con inconvenientes, proveedor para pagar) abren esta ficha.
10. La consulta no se audita (SEG-14).

---


---

## Actualizaciones de A0 que mandan sobre el texto de arriba

| Caso de uso | Qué cambia | Fuente |
|---|---|---|
| CMP-GNR-ODC | Compara las cotizaciones por el **precio unitario calculado** (total ÷ cantidad cotizada, 4 decimales); la cobertura suma la **cantidad cotizada** (que puede superar la pedida) y la pantalla muestra la diferencia | MD-125, P2; D-89 |
| CMP-GNR-ODC | Cada detalle de la orden copia la **cantidad cotizada** y el **total de la línea** (no el unitario) | MD-125, consecuencias de P2 |
| CMP-GNR-ODC | **Disparadores:** pasos diarios 60 (aviso de fecha límite vencida, y cancelación «nadie cotizó» si no hay cotizaciones), 61 (recordatorio de validez) y 62 (cancelación sin cotizaciones elegibles); el tema abierto del recordatorio queda resuelto | H16; D-87 punto 4 |
| CMP-GNR-ODC | **4a** se resuelve con Cancelar Pedido, que se puede antes o después de la fecha límite | CMP-CNL-PED |
| CMP-APR-ODC | **P1:** si al aprobar una cotización elegida venció o su proveedor está inactivo, el Gerente **solo puede rechazar** (con un motivo **propuesto** por el Sistema: «La cotización de {proveedor} venció el {fecha}» o «{proveedor} está inactivo»; lo puede editar) y el Agrónomo hace un pedido nuevo | P1 |
| CMP-APR-ODC | **Destinatarios de los avisos (pasos 9 y 5a.6):** regla nueva de `CMP-APR-ODC-punto6.md` (abajo): cada Agrónomo activo de los destinos; el Gerente por cada destino sin Agrónomo; nunca quien resolvió. Se quita el tema abierto | H21; MD-67 |
| CMP-APR-ODC | El tema abierto «la baja de un Proveedor… ¿pago pendiente?» queda resuelto: sí bloquea (H22) | H22 |
| CMP-CNS-ODC | El Contador ve todas las órdenes en solo lectura | pasada general 3 |

## Cómo se aplica (código)

Decisiones: **D-87**, **D-89**, **D-90** (tránsito), **D-56** (pasos diarios). Modelo: `docs/modelo/compras.md` (`OrdenCompra`, `DetalleOrdenCompra`).

### CMP-GNR-ODC (CMP-03)

- `compras/servicios/ordenes.py`: `pedidos_resolubles(actor)`, `comparacion(actor, pedido_id)` (las dos vistas del paso 4, con `cobertura(...)` de
  `compras/servicios/cobertura.py` y la marca de **elegible** de cada cotización: proveedor activo y `fecha_validez ≥ hoy`), `resumir_orden(actor,
  pedido_id, cotizacion_ids, observaciones)` y `generar_orden(actor, pedido_id, cotizacion_ids, observaciones) -> OrdenCompra`.
- **Generar:** bloquear los proveedores de las cotizaciones elegidas (en orden de id), el pedido y sus cotizaciones; verificar: el actor es el
  Agrónomo del pedido y sigue activo, el pedido sigue «en cotización» con la fecha límite vencida (11a), cada elegida sigue elegible (11b) y todos
  los detalles cubiertos con la tolerancia (8a). Crear la orden (`OneToOne` con el pedido: la base impide dos), un detalle por línea elegida
  (copia cantidad y total), elegidas → `seleccionada`, el resto de las propuestas → `descartada`, pedido → `cerrado` con `fecha_cierre_pedido`.
  Auditar el pedido, cada cotización modificada, la orden y cada detalle. `on_commit`: notificación al Gerente activo (12b: sin Gerente, se omite y
  el mensaje final lo dice) y correo de descarte a cada proveedor descartado.

### CMP-APR-ODC (CMP-03)

- `ordenes_por_aprobar()`, `detalle_para_resolver(orden_id)` (con las marcas de 4a y 4b), `resumir_aprobacion`, `aprobar_orden(actor,
  orden_id)` y `rechazar_orden(actor, orden_id, motivo)`; `motivo_propuesto(orden)` para P1.
- **Aprobar:** bloquear los invernaderos de destino (en orden de id), los `InsumoInvernadero` de destino (en orden de id), la orden y sus
  detalles; verificar «pendiente de aprobación» (8a), destinos activos (4a/8b) y cotizaciones vigentes y de proveedores activos (4b/8b, P1);
  `estado = aprobada`, `fecha_resolucion = hoy`, `gerente = actor`; `fecha_entrega_esperada = hoy + plazo` en cada detalle; `stock.sumar_transito`
  por `InsumoInvernadero` con la **suma** de sus detalles (postcondición f); auditar orden, detalles y cada `InsumoInvernadero`
  (`modificacion_insumo_invernadero`, con el tránsito antes y después). `on_commit`: los avisos de H21 (`avisos.destinatarios_por_destino(destinos,
  excluir=actor)`) y el correo a cada proveedor con **solo sus líneas**.
- **Rechazar:** bloquear la orden; motivo obligatorio (5b); `rechazada`, cotizaciones seleccionadas → `descartada`; avisos y correos de descarte.
- Las alertas de bajo el mínimo **no** se tocan (postcondición d).

### CMP-CNS-ODC (CMP-03 lo crea; CMP-04, CMP-05 y CMP-06 suman sus secciones)

- `consultar_ordenes(actor, filtros)` y `ficha_de_orden(actor, orden_id)`. Alcance: el Agrónomo, las que tienen algún destino a su cargo; el
  Gerente y el Contador, todas (el Contador sin acciones). Atajos: «por aprobar» (CMP-03), «por recibir» (CMP-04), «con pago pendiente» (CMP-05),
  «con reclamo sin emitir» (CMP-04). Las secciones «recepciones», «pagos» y «reclamos» de la ficha (reglas 6 y 7) las completa cada tarea.

### Pasos diarios 60 a 62 (CMP-03; D-87 punto 4)

`compras/procesos.py` con `paso_pedidos_vencidos(hoy)`, `paso_recordatorio_de_validez(hoy)` y `paso_pedidos_sin_cotizacion_elegible(hoy)`;
cada uno devuelve `ResumenDePaso` y procesa **un pedido por transacción** (si uno falla, los demás siguen). Las cancelaciones usan
`cancelar_pedido_automaticamente` (CMP-02b). Textos de los avisos: el de 60 es el de la regla «Aviso de vencimiento» de CMP-GNR-ODC (con las líneas
por detalle y si alcanzan); el de 61, «Mañana vence la cotización de {proveedor} en el pedido P-…: si querés elegirla, generá la orden hoy»; el de
62, «Se canceló el pedido P-… porque ninguna cotización se puede elegir (validez vencida o proveedor inactivo)».

### Impedimentos (H20, CMP-03)

Suma al registrante de `inventario.registrar_impedimento_de_deshabilitacion` el código `orden_de_compra_aprobada` para **toda orden no
terminada** con un detalle a ese `InsumoInvernadero`. Completa `proveedores.impedimentos_de_baja` con `orden_no_terminada`.

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| CMP-GNR-ODC (incluidos los cuatro ejemplos de cobertura de la regla y la cantidad cotizada mayor que la pedida) | `test_cmp_gnr_odc.py` |
| CMP-APR-ODC (aprobación, rechazo, P1, destino inactivo, tránsito sumado por `InsumoInvernadero`, destinatarios de H21) | `test_cmp_apr_odc.py` |
| CMP-CNS-ODC: alcance por rol, filtros, atajos | `test_cmp_cns_odc.py` |
| Pasos 60, 61 y 62: idempotencia (dos corridas el mismo día no repiten), cada caso | `test_pasos_diarios_compras.py` |
| `destinatarios_por_destino` (un Agrónomo, dos, uno sin Agrónomo, todos sin, el actor excluido) | `test_avisos.py` |
| Concurrencia: dos generaciones del mismo pedido; generar contra cancelar; dos aprobaciones de órdenes con el mismo insumo y destino (el tránsito suma las dos); aprobar contra dar de baja el invernadero | `test_ordenes_concurrencia.py` |

### Pantallas (prototipo)

`VIEWS.c_gen` (2490): comparar y elegir. `tabOdc` (2373) y `VIEWS.c_odc` (2383): «Órdenes de compra» y ficha. `VIEWS.c_apr` (2528): revisar,
aprobar o rechazar (con el motivo propuesto de P1). Panel del Gerente: `panelGer` (2944), «órdenes por aprobar».
