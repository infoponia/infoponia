# Casos de uso · compras · Recepción y cierre con faltante

Copia para el repo de CMP-REG-RCP (v0.3), de «CU extendidos» (Drive), y CMP-CRR-FLT (A0, v0.1). Fuentes: Drive «CU extendidos» y `CMP-CRR-FLT.md`. Cotejado con `decisiones_A0.md` y `pendientes_para_pegar.md`: **esas decisiones ganan** si algo
difiere (regla del estudiante del 23/11/2026); lo que cambian está en «Actualizaciones de A0 que mandan», al final de cada caso de uso o del
archivo.

**El código va en la app `compras`** (D-37, nivel 6; D-87). Archivos de pruebas bajo `compras/tests/`. Si este archivo y el documento de
Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>`, `test_post_<letra>_<que_espera>` y
`test_ext_<codigo>_<que_espera>`.

---

## **Caso de uso CMP-REG-RCP: Registrar Recepción de Mercadería**

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Compras e Inventario.  
 **Actor principal:** Agrónomo a cargo del invernadero de destino. Si no está, el Gerente (extensión 1a).  
 **Versión:** 0.3

**Personal involucrado e intereses**

**Agrónomo:**

  - quiere registrar lo que llegó apenas lo recibe, desde la computadora o el celular;
  - quiere ver qué falta recibir de cada línea y si alguna llegó tarde;
  - quiere dejar constancia de lo que llegó roto, tarde o equivocado, sin tener que gestionar él el reclamo.

**Gerente:**

  - quiere enterarse cuando una recepción tiene inconvenientes, para emitir el reclamo al proveedor;
  - quiere que lo recibido quede registrado, porque es la base del pago a cada proveedor;
  - quiere poder registrar la recepción cuando el Agrónomo no está.

**Proveedor:**

  - quiere constancia de lo que se le recibió y de lo que no se le aceptó por daño;
  - quiere que se le pague por lo que entregó.

**Organización (Jardín Botánico):**

  - quiere que el stock refleje lo que realmente entró y en buen estado;
  - quiere que la deuda con el proveedor nazca al recibir y por lo recibido (base devengado), sin pagar lo dañado;
  - quiere trazabilidad desde el pedido hasta el pago de cada proveedor.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso.
  - **Es extendido por:** Cerrar Detalle con Faltante (a especificar), en el punto de extensión “recepción parcial” (extensión 11a).
  - **Disparador:** la llegada física al invernadero de la mercadería de un proveedor.
  - **Lo precede:** CMP-APR-ODC · Aprobar Orden de Compra.
  - **Lo sigue:** Registrar Pago a Proveedor (a especificar), cuando todos los detalles de un proveedor en la orden están completos o cerrados con faltante.
  - **Reclamos:** Emitir Reclamo a Proveedor (CU-98) y Cerrar Reclamo a Proveedor (CU-99) no extienden este caso de uso. Los ejecuta el Gerente después, sobre el reclamo sin emitir que este caso de uso genera.

**Precondiciones**

a. El actor está autenticado en el Sistema.  
 b. Existe al menos una orden de compra “aprobada” o “parcialmente recibida” con algún detalle “pendiente”.  
 c. Existe un ejercicio contable vigente y existen las cuentas contables Insumos en Stock y Proveedores.

**Garantías mínimas**

El registro es atómico. Si el caso de uso se cancela o falla:

  - no queda registrada ninguna recepción, detalle de recepción, movimiento de insumo, asiento, reclamo, inconveniente ni alerta;
  - no cambia el stock actual ni la cantidad en tránsito de ningún insumo, ni el estado de ningún detalle de la orden, de la orden ni de ninguna alerta;
  - no se registra ningún log de auditoría parcial y no se envía ningún correo.

**Además:**

  - Ningún detalle de la orden recibe más de lo que le falta recibir.
  - Lo que llegó dañado o vencido nunca ingresa al stock, no forma parte del asiento y no se paga.
  - Una recepción es de una sola orden, un solo proveedor y un solo invernadero.
  - No se modifica la cantidad pedida, el precio ni la fecha de entrega esperada de ningún detalle de la orden.
  - No se modifica el precio de referencia de ningún insumo ni las reservas de insumo.
  - Este caso de uso no registra pagos, no cierra detalles con faltante y no emite ni cierra reclamos.

**Garantías de éxito (Postcondiciones)**

**En toda recepción registrada:****  
** a. Se creó una recepción con fecha igual a la fecha actual y las observaciones, si se indicaron. Quedó asociada a la orden y al Agrónomo que la registró. Si la registró el Gerente, quedó sin Agrónomo.  
 b. Se creó un detalle de recepción por cada línea recibida, con la cantidad recibida (lo que ingresó al stock, sin lo dañado ni lo vencido), asociado a su detalle de la orden.  
 c. Por cada detalle de recepción con cantidad recibida mayor que cero:

  - se cubrió primero el faltante sin lote del InsumoInvernadero de destino, si lo había, y el resto se ingresó en uno o más lotes de insumo nuevos, con su fecha de vencimiento si el insumo la controla; el stock actual del InsumoInvernadero, que es la suma de sus lotes, aumentó en la cantidad recibida y su cantidad en tránsito bajó en la misma cantidad;
  - por cada lote en que ingresó cantidad, incluido el faltante sin lote, se creó un movimiento de insumo de tipo “ingreso por recepción”, con la cantidad ingresada en ese lote y la fecha actual, asociado al lote de insumo y al detalle de recepción.

d. Cada detalle de la orden recibido pasó a “completo” si lo recibido acumulado iguala la cantidad pedida. Si no, siguió “pendiente”.  
 e. La orden quedó:

  - “recibida”, si todos sus detalles quedaron completos;
  - “recibida con faltante”, si todos quedaron completos o cerrados con faltante y al menos uno está cerrado con faltante;
  - en otro caso, “parcialmente recibida”.

f. Si algún detalle de recepción tiene cantidad recibida mayor que cero, se registró un asiento originado en la recepción: Debe Insumos en Stock / Haber Proveedores, por Σ cantidad recibida × precio unitario de la orden. Si no ingresó nada al stock, no se registró asiento.  
 g. Las alertas de insumo bajo el mínimo activas de los InsumoInvernadero recibidos quedaron resueltas, con su fecha de resolución, si el insumo dejó de estar bajo el mínimo. Las demás siguieron activas. Las alertas de «stock inconsistente» de esos InsumoInvernadero se resolvieron si el stock sin lotes vencidos volvió a cubrir las reservas.  
 h. Se envió al Proveedor un correo con lo recibido por línea y lo no aceptado por daño o por estar vencido.

**Si se declararon inconvenientes:****  
** i. Se creó un inconveniente por cada uno declarado, con su tipo, cantidad afectada y descripción, asociado a su detalle de recepción, con a lo sumo uno de cada tipo por detalle de recepción.  
 j. Se creó un reclamo del proveedor en estado “abierto”, sin emitir (sin Gerente y sin fecha de emisión), que agrupa todos los inconvenientes de la recepción.  
 k. Se creó una alerta para el Gerente, activa y no leída, que identifica la recepción, el proveedor y el reclamo sin emitir.

**Auditoría:****  
** l. Se creó un log de auditoría por la recepción y por cada detalle de recepción, movimiento de insumo, InsumoInvernadero, detalle de la orden, orden, asiento, reclamo, inconveniente y alerta creados o modificados, con usuario, rol, fecha, hora, identificador y cambios de valor.

**Escenario principal de éxito (o Flujo Básico)**

(Llega completa y en buen estado la mercadería pendiente de un proveedor en un invernadero, sin inconvenientes ni cambios entre la presentación y el registro.)

1.  **El Agrónomo inicia el registro de una recepción.**
2.  **El Sistema presenta las entregas pendientes de los invernaderos a cargo del Agrónomo, agrupadas por proveedor e invernadero, de la fecha de entrega esperada más próxima a la más lejana. Para cada orden indica:**
      
      - el identificador de la orden;
      - la cantidad de líneas pendientes;
      - la fecha de entrega esperada más próxima;
      - si alguna línea está atrasada, y cuántos días.
3.  **El Agrónomo selecciona la orden del proveedor y el invernadero cuya mercadería llegó.**
4.  **El Sistema presenta las líneas pendientes de esa orden para ese proveedor e invernadero. Para cada una indica:**
      
      - el insumo y su unidad de medida;
      - la cantidad pedida, la ya recibida y la que falta recibir;
      - la fecha de entrega esperada y, si la fecha actual la superó, los días de atraso.
5.  **El Agrónomo indica, para cada línea que llegó, la cantidad recibida en buen estado y, si el insumo controla vencimiento, la fecha de vencimiento de lo recibido (una cantidad por cada fecha distinta) y, si quiere, las observaciones de la recepción.**
6.  **El Agrónomo indica que terminó de cargar la recepción.**
7.  **El Sistema verifica los datos y presenta el resumen de la recepción:**
      
      - por cada línea, la cantidad que ingresa al stock, los lotes en que ingresa (primero el faltante sin lote, si lo hay) y cómo cambian el stock actual y la cantidad en tránsito del insumo;
      - el estado en que quedará cada línea y la orden;
      - el monto del asiento;
      - las alertas de insumo bajo el mínimo que se resolverán;
      - que la recepción no registra ningún pago.
8.  **El Agrónomo confirma la recepción.**
9.  **El Sistema registra la recepción:**
      
      - crea la recepción y sus detalles;
      - cubre primero el faltante sin lote de cada insumo recibido, si lo hay; ingresa el resto en lotes de insumo nuevos, con su fecha de vencimiento si el insumo la controla; sube el stock actual y baja la cantidad en tránsito, con un movimiento de insumo por cada lote;
      - actualiza el estado de cada línea recibida y el de la orden;
      - registra el asiento;
      - resuelve las alertas de insumo bajo el mínimo que correspondan;
      - registra la auditoría correspondiente.
10. **El Sistema envía al Proveedor un correo con lo recibido por línea.**
11. **El Sistema informa al Agrónomo que la recepción fue registrada y el estado en que quedó la orden.**

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 8), el actor cancela el registro:**

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al actor que la recepción no fue registrada.
3.  El actor reinicia el caso de uso desde el paso 1.

**1a. El Gerente registra la recepción porque el Agrónomo no está:**

1.  En el paso 2, el Sistema presenta las entregas pendientes de todos los invernaderos.
2.  El caso de uso continúa en el paso 3, con el Gerente como actor.
3.  En el paso 9, la recepción queda sin Agrónomo; el Gerente queda registrado en el log de auditoría.

**4a. Alguna línea es de un invernadero “inactivo”, o de un insumo “inactivo” en ese invernadero:**

1.  El Sistema advierte que llegó mercadería para un destino inactivo y señala la línea (“invernadero inactivo” o “insumo inactivo en el invernadero”), sin permitir indicarle cantidad.
2.  El Sistema informa que, para recibirla, primero hay que reactivar el destino.
3.  El actor continúa con las demás líneas (paso 5) o cancela.

**4a1. Todas las líneas pendientes tienen el destino inactivo:**

1.  El Sistema informa que no se puede registrar la recepción hasta que se reactive el destino.
2.  El caso de uso termina.

**5a. Parte de lo que llegó de una línea está dañado:**

1.  El actor indica la cantidad dañada y, si quiere, describe el daño.
2.  El Sistema agrega un inconveniente de tipo “daño” a la línea. La cantidad dañada no cuenta como recibida, así que la línea sigue pendiente por esa cantidad.
3.  El caso de uso continúa en el paso 5.

**5a.1a. Todo lo que llegó de la línea está dañado:**

1.  El actor indica 0 como cantidad recibida y la cantidad dañada.
2.  El caso de uso continúa en 5a.2.

**5b. La línea está atrasada y el actor declara el retraso:**

1.  El Sistema agrega un inconveniente de tipo “retraso” a la línea, con la cantidad recibida como cantidad afectada y los días de atraso en la descripción.
2.  El caso de uso continúa en el paso 5.

**5c. El actor declara otro inconveniente con lo que llegó (por ejemplo, un insumo equivocado):**

1.  El actor indica la cantidad afectada y la descripción.
2.  El Sistema agrega un inconveniente de tipo “otro” a la línea.
3.  El caso de uso continúa en el paso 5.

**5d. El actor quiere quitar o cambiar un inconveniente, o declarar uno de un tipo que la línea ya tiene:**

1.  El Sistema presenta el inconveniente existente de ese tipo para modificarlo o quitarlo. Una línea tiene a lo sumo un inconveniente de cada tipo.
2.  El caso de uso continúa en el paso 5.

**5e. Parte de lo que llegó de una línea está vencido (el actor indica una fecha de vencimiento anterior a la fecha actual):**

1.  El Sistema agrega un inconveniente de tipo “vencido” a la línea, con la cantidad vencida como cantidad afectada. Esa cantidad no cuenta como recibida ni ingresa al stock, así que la línea sigue pendiente por esa cantidad.
2.  El caso de uso continúa en el paso 5.

**7a. La cantidad recibida de una línea supera lo que falta recibir:**

1.  El Sistema señala la línea, informa lo que falta recibir y que el excedente no se ingresa al stock.
2.  El actor corrige la cantidad (vuelve al paso 5) y puede dejar constancia del excedente en las observaciones.

**7b. Una cantidad es negativa o tiene más de dos decimales:**

1.  El Sistema señala el error.
2.  El actor corrige la cantidad (vuelve al paso 5).

**7c. Una línea tiene cantidad recibida 0 sin un inconveniente de daño o de vencido:**

1.  El Sistema señala que una línea en 0 solo se registra si todo lo que llegó estaba dañado o vencido.
2.  El actor declara el daño o el vencimiento (continúa en 5a o en 5e) o quita la línea de la recepción (vuelve al paso 5).

**7d. Ninguna línea tiene cantidad indicada:**

1.  El Sistema informa que la recepción debe incluir al menos una línea.
2.  El actor indica una cantidad (vuelve al paso 5) o cancela.

**7e. Un inconveniente está incompleto (cantidad afectada no mayor que cero, o de tipo “otro” sin descripción):**

1.  El Sistema señala el error.
2.  El actor lo completa (vuelve al paso 5).

**7f. La recepción tiene al menos un inconveniente declarado:**

1.  En el paso 7, el resumen incluye los inconvenientes por línea y que se generará un reclamo sin emitir, con su alerta al Gerente.
2.  En el paso 9, el Sistema además crea los inconvenientes y el reclamo “abierto” sin emitir, que los agrupa y queda sin fecha de emisión, y la alerta para el Gerente.
3.  En el paso 10, el correo incluye además lo no aceptado por daño o por vencimiento.

**8a. El actor quiere cambiar algún dato antes de confirmar:**

1.  El caso de uso vuelve al paso 5.

**9a. Al registrar, lo que falta recibir de alguna línea cambió, o la línea ya no está “pendiente” (otro usuario registró una recepción o la cerró con faltante):**

1.  El Sistema no registra ningún cambio e informa qué líneas quedaron afectadas y lo que les falta recibir ahora.
2.  El caso de uso vuelve al paso 4.

**9b. Al registrar, el invernadero o algún insumo de destino pasó a “inactivo”:**

1.  El Sistema no registra ningún cambio e informa qué líneas quedaron afectadas.
2.  El caso de uso vuelve al paso 4, donde se aplica la extensión 4a.

**10a. El Sistema no logra enviar el correo al Proveedor:**

1.  La recepción permanece registrada.
2.  El Sistema reintenta el envío.

**11a. Alguna línea de la recepción quedó “pendiente” (recepción parcial):**

1.  El Sistema informa las líneas pendientes con lo que les falta recibir y ofrece cerrarlas con faltante.
2.  Si el actor acepta, se ejecuta Cerrar Detalle con Faltante (punto de extensión “recepción parcial”). Si no, las líneas siguen pendientes y el caso de uso termina.

**Requisitos especiales**

  - La interfaz se adapta a computadora y a celular.
  - La información del paso 4 se presenta en no más de 2 segundos desde la selección.
  - El registro del paso 9 se completa en no más de 5 segundos.
  - El registro se ejecuta como una única transacción. La recepción, sus detalles, los movimientos de insumo, el stock actual, la cantidad en tránsito, los estados de las líneas y de la orden, el asiento, el reclamo, los inconvenientes, las alertas y los logs se registran juntos o no se registra ninguno. El correo se envía fuera de la transacción.
  - El control de concurrencia cumple tres funciones:
      
      - impide que dos recepciones simultáneas de una misma línea superen lo que le falta recibir;
      - impide que dos registros simultáneos sobre un mismo InsumoInvernadero pierdan un cambio del stock actual o de la cantidad en tránsito;
      - impide que se reciba una línea mientras se la cierra con faltante o se da de baja su destino.
  - El Agrónomo accede solo a las órdenes con destino en los invernaderos que tiene a cargo. El Gerente accede a todas.
  - La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Las cantidades se expresan en la unidad de medida del insumo, con hasta dos decimales. Los montos se expresan en pesos argentinos, con dos decimales.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

  - **Quién registra:** el Agrónomo a cargo del invernadero de destino en el momento de recibir (R051). Si no está, el Gerente. El Sistema no controla la presencia del Agrónomo: que registre el Gerente es una decisión del actor. Cuando registra el Gerente, la recepción no tiene Agrónomo y el usuario real queda en el log de auditoría (R039 en 0..1, ronda 20; mismo criterio que R046 y R076). (Paso 1 y extensión 1a)
  - **Una recepción:** es la mercadería que un proveedor entrega en un invernadero, para una orden. Todos sus detalles son de esa orden, de ese proveedor y de ese invernadero. (Regla 7 de 8.20; R019; pasos 2 y 3)
  - **Línea recibible:** detalle “pendiente” de una orden “aprobada” o “parcialmente recibida”, con su invernadero y su insumo de destino activos. (Regla 8 de 8.20; pasos 2 y 4)
  - **Cantidad recibida:** es lo que ingresó al stock. No puede superar lo que falta recibir de la línea (cantidad pedida − Σ recibido); el excedente no se ingresa. Vale 0 solo si todo lo que llegó estaba dañado o vencido. (Reglas 6 y 9 de 8.20; extensiones 7a y 7c)
  - **Inconvenientes:** registran un problema con lo que llegó, de tipo daño, vencido, retraso u otro, con a lo sumo uno de cada tipo por línea. Lo que no llegó no es un inconveniente: se resuelve con el cierre con faltante. Lo dañado o vencido no cuenta como recibido y deja la línea pendiente, porque el proveedor puede reponerlo. (Regla 10 de 8.20; extensiones 5a a 5e)
  - **Retraso:** una línea está atrasada si la fecha actual es posterior a su fecha de entrega esperada. Los días de atraso son la diferencia entre las dos fechas. El Sistema lo muestra y el actor decide si lo declara. (Regla 23 de 8.16; paso 4 y extensión 5b)
  - **Reclamo sin emitir:** si la recepción tiene inconvenientes, genera un reclamo del proveedor que los agrupa a todos, “abierto”, sin Gerente y sin fecha de emisión. Un reclamo está emitido si y solo si tiene Gerente, y solo entonces tiene fecha de emisión. Lo emite después un Gerente (CU-98), y solo se cierra un reclamo emitido (CU-99). (R008 en 0..1 y regla 10 de 8.20 modificada, ronda 20; extensión 7f)
  - **Estado de la línea:** pasa a “completo” cuando lo recibido acumulado iguala lo pedido; si no, sigue “pendiente”. El cierre con faltante lo hace otro caso de uso. (Regla 8 de 8.20; paso 9 y extensión 11a)
  - **Estado de la orden:** pasa a “parcialmente recibida” con la primera recepción, aunque no haya ingresado nada al stock; a “recibida”, cuando todas sus líneas están completas; y a “recibida con faltante”, cuando todas están completas o cerradas con faltante y al menos una está cerrada con faltante. (Regla 24 de 8.16; paso 9)
  - **Stock y tránsito:** por cada línea, el stock actual sube y la cantidad en tránsito baja en la cantidad recibida. Lo dañado o vencido no cambia ninguno de los dos. El stock actual es la suma de los lotes del insumo (MD-84). (Regla 22 de 8.16; paso 9)
  - **Movimiento de insumo:** un detalle de recepción genera un movimiento de tipo “ingreso por recepción” por cada lote en que ingresa cantidad, y solo si su cantidad recibida es mayor que 0. (Regla 9 de 8.20; regla 1 de 8.19; R032)
  - **Lotes de la recepción:** lo recibido de una línea cubre primero el faltante sin lote del InsumoInvernadero, si lo hay, hasta dejarlo en cero; el resto forma lotes de insumo nuevos, con su fecha de vencimiento si el insumo la controla. Un insumo que llega vencido se trata como el daño: no ingresa al stock y la línea sigue pendiente, con un inconveniente de tipo “vencido”. (Paso 9, y extensión 5e; regla 4 de 8.19; MD-84 y MD-85)
  - **Asiento:** Debe Insumos en Stock / Haber Proveedores, por Σ cantidad recibida × precio unitario de la orden, originado en la recepción. Una recepción sin ingreso al stock no genera asiento. (Regla 14 de 8.20; paso 9)
  - **Precio de referencia:** no se actualiza al recibir. (Regla 6 de 8.18)
  - **Alerta de insumo bajo el mínimo:** se resuelve en la recepción, y no al pedir ni al aprobar la orden, si después de recibir el insumo deja de estar bajo el mínimo (stock libre + cantidad en tránsito ≥ stock mínimo). Es una decisión explícita: la alerta queda activa como recordatorio hasta que llega la mercadería. (Reglas 11 y 12 de 8.15, la 12 precisada en la ronda 20; paso 9)
  - **Destino inactivo:** una línea de un invernadero o de un insumo inactivo no se recibe. El Sistema advierte que la mercadería llegó y bloquea esa línea hasta que se reactive el destino. (Extensiones 4a y 9b)
  - **Fecha de recepción:** siempre la fecha del registro, sin fechas retroactivas. Un registro tardío se aclara en las observaciones. (Mismo criterio que la regla 7 de 8.13; paso 9)
  - **Pago diferido:** este caso de uso no registra pagos. El pago a cada proveedor se registra después, por lo recibido, cuando todas sus líneas en la orden están completas o cerradas con faltante. (Regla 13 de 8.20)
  - **Avisos:** (Pasos 10 y 11; extensión 7f)
      
      - el Proveedor recibe un correo con lo recibido por línea y lo no aceptado por daño o por vencimiento;
      - si hay inconvenientes, el Gerente recibe una alerta por la recepción, para emitir el reclamo.

**Lista de tecnología y variaciones de datos**

  - **5.** Las observaciones de la recepción son texto libre y opcional (Recepcion.observacionesRecepcion, ronda 20).
  - **5a–5c y 5e.** La descripción de un inconveniente es obligatoria en el tipo “otro” y opcional en el daño y en el vencido; en el retraso, la completa el Sistema con los días de atraso (descripcionInconveniente, precisada en la ronda 20).
  - **10.** El correo al Proveedor indica:
      
      - el identificador de la orden y la fecha de la recepción;
      - el invernadero de destino;
      - por cada línea: insumo, cantidad recibida y, si la hay, cantidad no aceptada por daño o por vencimiento;
      - las líneas que siguen pendientes, con lo que falta recibir.
  - No menciona a los otros proveedores de la orden.
  - **7f.** La alerta al Gerente indica la recepción, el proveedor, el invernadero, el reclamo sin emitir y la cantidad de inconvenientes por tipo. Su tipoAlerta es “recepción con inconvenientes” (valor a registrar en el modelo; ver nota).

**Frecuencia**

Una o más veces por cada orden de compra aprobada: una por cada entrega de un proveedor en un invernadero.

**Temas abiertos**

  - Aviso para el pago: ¿InfoPonia avisa, y a quién, cuando todas las líneas de un proveedor en la orden quedan completas o cerradas con faltante? Se define en Registrar Pago a Proveedor (caso por especificar 20).
  - Retraso sin recepción: si una línea supera su fecha de entrega esperada y no llegó nada, no hay recepción donde declarar el retraso. ¿Hace falta un aviso al Agrónomo?
  - Corrección de una recepción registrada con error (cantidad mal cargada): no hay forma de anularla. ¿Hace falta un caso de uso con contraasiento y ajuste de stock?
  - Daño detectado después de registrar la recepción: no se puede agregar un inconveniente a una recepción ya registrada.
  - Destino inactivo: las reglas 3 y 4 de 8.4 permiten dar de baja un destino con mercadería en tránsito (pendientes\_CU, Ajustes pendientes en la documentación, punto 6). Si se bloquea esa baja, la extensión 4a deja de ocurrir.

-----


---

## **Caso de uso CMP-CRR-FLT: Cerrar Detalle con Faltante**

Caso de uso extendido del módulo Compras e Inventario (versión 0.1, 23/11/2026), con el formato de «CU extendidos». Reemplaza a PCU › caso 26. Fuentes: MD › regla 8 de 8.20, regla 22 de 8.16, ficha DetalleOrdenCompra (estadoDetalleOrden, motivoCierreFaltante), MD-26; CUE › CMP-REG-RCP, extensión 11a.

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Compras e Inventario.
**Actor principal:** Agrónomo a cargo del invernadero de destino. Si no está, el Gerente (extensión 1a), como en CMP-REG-RCP.
**Versión:** 0.1

**Personal involucrado e intereses**

**Agrónomo:**
- quiere terminar una línea que el proveedor no va a completar, aunque no haya llegado nada, para que la orden no quede abierta para siempre.

**Gerente y Contador:**
- quieren poder pagar por lo recibido cuando el proveedor ya no va a mandar más.

**Organización (Jardín Botánico):**
- quiere que el stock en tránsito refleje solo lo que de verdad va a llegar, para que el insumo vuelva a aparecer bajo el mínimo si hace falta.

**Relaciones con otros casos de uso**
- No incluye otros casos de uso.
- **Extiende a:** CMP-REG-RCP · Registrar Recepción de Mercadería, en el punto de extensión «recepción parcial» (extensión 11a). También se ejecuta solo, aunque no haya llegado nada.
- **Lo sigue:** CMP-REG-PAG · Registrar Pago a Proveedor, cuando todas las líneas del proveedor quedan completas o cerradas.
- **No es:** un reclamo. Lo que no llegó no es un inconveniente (regla 10 de 8.20).

**Precondiciones**
a. El actor está autenticado con una cuenta activa de Agrónomo.
b. Existe una orden «aprobada» o «parcialmente recibida» con alguna línea «pendiente» en un invernadero a cargo del actor.

**Garantías mínimas**
La operación es atómica. Si se cancela o falla, no cambia el estado de ninguna línea ni de la orden, la cantidad en tránsito, las alertas ni los logs.

**Además:**
- No se modifica el stock actual, la cantidad pedida, el precio ni las reservas.
- No registra asiento, no registra pagos y no emite ni cierra reclamos.

**Garantías de éxito (Postcondiciones)**
a. Cada línea elegida pasó a «cerrada con faltante», con su motivo de cierre (obligatorio). La cantidad faltante es la pedida menos la recibida.
b. La cantidad en tránsito del InsumoInvernadero de cada línea bajó en la cantidad faltante.
c. La orden quedó «recibida con faltante» si todas sus líneas están completas o cerradas y al menos una está cerrada con faltante; en otro caso siguió «parcialmente recibida» o «aprobada».
d. Se reevaluaron las alertas de insumo bajo el mínimo (stock libre + tránsito < mínimo): puede activarse una nueva.
e. Si todas las líneas del proveedor en la orden quedaron completas o cerradas y se recibió algo de al menos una, el proveedor pasó a la bandeja de pagos pendientes y se notificó al Contador (o al Gerente). Si no se recibió nada, no hay pago.
f. Se envió al proveedor un correo que le avisa que no se espera el resto de las líneas cerradas.
g. Se creó un log de auditoría por cada línea, InsumoInvernadero, orden y alerta creados o modificados.

**Escenario principal de éxito (Flujo Básico)**
(El Agrónomo cierra con faltante una línea que el proveedor no va a completar.)

1. **El Agrónomo inicia el cierre de líneas con faltante, desde la ficha de la orden (o desde el aviso de recepción parcial de CMP-REG-RCP).**
2. **El Sistema presenta las líneas pendientes de las órdenes de los invernaderos del Agrónomo, agrupadas por orden, proveedor e invernadero. Para cada una: el insumo, la cantidad pedida, la recibida, lo que falta recibir y la fecha de entrega esperada con sus días de atraso.**
3. **El Agrónomo selecciona las líneas a cerrar.**
4. **El Agrónomo indica el motivo del cierre de cada una.**
5. **El Sistema verifica y presenta el resumen: por línea, la cantidad faltante y cómo cambia la cantidad en tránsito; el estado en que quedará la orden; si el proveedor queda listo para pagar o sin pago; las alertas que se activarán.**
6. **El Agrónomo confirma el cierre.**
7. **El Sistema registra el cierre y, fuera de la transacción, envía al proveedor el aviso por correo:**
   - bloquea las líneas y verifica que sigan «pendiente»;
   - las pasa a «cerrada con faltante» con su motivo;
   - baja la cantidad en tránsito;
   - actualiza el estado de la orden;
   - reevalúa las alertas;
   - registra la auditoría correspondiente.
8. **El Sistema informa al Agrónomo que el cierre fue registrado y el estado en que quedó la orden.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 6), el actor cancela:**
1. El Sistema descarta los datos sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial y, al restablecerse, informa que el cierre no fue registrado.
2. El actor reinicia desde el paso 1.

**1a. El Gerente cierra porque el Agrónomo no está:**
1. En el paso 2, el Sistema presenta las líneas pendientes de todos los invernaderos; el Gerente queda en el log de auditoría.

**2a. Se llegó desde CMP-REG-RCP (extensión 11a):**
1. El Sistema presenta solo las líneas pendientes de esa recepción y continúa en el paso 3.

**4a. Falta el motivo de alguna línea:**
1. El Sistema señala el error.
2. El actor lo completa (vuelve al paso 4).

**7b. No se logra enviar el correo al proveedor:**
1. El cierre permanece registrado y el Sistema reintenta el envío.

**7a. Al registrar, alguna línea ya no está «pendiente» (se recibió o cerró en otra sesión):**
1. El Sistema no registra ningún cambio, informa qué líneas quedaron afectadas y vuelve al paso 2.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 7 se completa en no más de 3 segundos.
- El registro es una única transacción.
- El control de concurrencia impide cerrar una línea mientras se la recibe o se da de baja su destino, y que dos cierres simultáneos resten dos veces el tránsito.
- El Agrónomo accede solo a las órdenes de los invernaderos que tiene a cargo.
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**
- **Cierre con faltante:** estado de la línea, con motivo obligatorio, aunque no haya llegado nada. La cantidad faltante no se guarda. (Regla 8 de 8.20; MD-26)
- **Tránsito:** baja por la cantidad faltante, para que el insumo vuelva a aparecer bajo el mínimo si corresponde. (Regla 22 de 8.16)
- **Estado de la orden:** «recibida con faltante» si todas las líneas están completas o cerradas y al menos una cerrada. (Regla 24 de 8.16)
- **Pago:** se paga por lo recibido; sin recepción de ninguna línea del proveedor, no hay pago ni asiento. (Regla 13 de 8.20)
- **Sin asiento:** cerrar no mueve dinero: la deuda nació al recibir. (Regla 14 de 8.20)
- **Inconveniente no repuesto:** si el proveedor no repone lo que llegó dañado, vencido o no conforme (tipos de inconveniente de la decisión P4), la línea pendiente se cierra con faltante. (Regla 10 de 8.20)

**Lista de tecnología y variaciones de datos**
- **4.** Motivo: texto libre.

**Frecuencia**
Baja: una por cada línea que un proveedor no completa.

**Decisiones derivadas (R1 a R6)**
1. Al cerrar con faltante se le avisa al proveedor por correo que no se espera el resto.
2. Un cierre con faltante no se deshace: limitación aceptada, mitigada por el correo.

---

## Actualizaciones de A0 que mandan sobre el texto de arriba

| Caso de uso | Qué cambia | Fuente |
|---|---|---|
| CMP-REG-RCP | **Sobreentrega bloqueada:** 7a rechaza la cantidad que supera lo que falta recibir (el excedente va en las observaciones y entra por ajuste de stock o se devuelve) | P3 |
| CMP-REG-RCP | **Tipos de inconveniente:** mercadería dañada, calidad no conforme, producto distinto al pedido, vencido o próximo a vencer, otro (descripción obligatoria). **Se quita la 5b** (el retraso no se declara: se calcula y se muestra; para reclamarlo, «otro»). La 5a, 5c y 5e se leen con los tipos nuevos; la 7c acepta 0 con cualquier inconveniente que no sea «otro» | P4; MD-130 |
| CMP-REG-RCP | **Valorización del asiento** con el total por línea (D-89 punto 4) | MD-125 |
| CMP-REG-RCP | **11a** incluye Cerrar Detalle con Faltante (CMP-CRR-FLT) | 2.A-4 (b) |
| CMP-REG-RCP | Se quita el tema abierto «corrección de una recepción»: lo resuelve CMP-COR-RCP | H24 |
| CMP-REG-RCP | **Aviso al pago:** cuando todas las líneas de un proveedor en la orden quedan completas o cerradas (con algo recibido), se notifica al Contador (o al Gerente) y entra en la bandeja; no se notifica a quien registró | H23, H21 |
| CMP-REG-RCP | Precondición c: siempre hay ejercicio (la contabilidad se recupera sola, H9; D-84) y las cuentas existen desde la migración | H9; D-84 |
| CMP-REG-RCP | Cantidades: decimales según la unidad del insumo | regla 2 de 8.23 |
| CMP-CRR-FLT | El actor es el mismo que el de la recepción (Agrónomo del destino; Gerente sin Agrónomo) y se avisa al proveedor por correo | R3, R4 |

## Cómo se aplica (código)

Decisiones: **D-90** (lo que escribe `inventario`, vínculos, bloqueos), **D-89** (importes), **D-91** (aviso al pago), **D-86** (asiento).
Modelo: `docs/modelo/compras.md` (`Recepcion`, `DetalleRecepcion`, `DetalleRecepcionMovimiento`, `InconvenienteRecepcion`, `ReclamoProveedor`,
`AlertaCompras`). API: `docs/api/stock.md` («Escritura de compras») y `docs/api/asientos.md`. Patrón: `docs/patrones/asientos.md`.

### CMP-REG-RCP (CMP-04)

- `compras/servicios/recepciones.py`: `entregas_pendientes(actor)`, `lineas_a_recibir(actor, orden_id, proveedor_id, invernadero_id)`,
  `resumir_recepcion(actor, datos)` y `registrar_recepcion(actor, datos) -> Recepcion`. `datos.lineas = [(detalle_orden_id, partes=[(cantidad,
  vencimiento)], inconvenientes=[(tipo, cantidad, descripcion)])]`.
- **Quién (1a):** el Agrónomo activo a cargo del invernadero de destino, o el Gerente. El Gerente registra en cualquier invernadero; la recepción
  queda con `agronomo = None`.
- **Registrar (orden de D-90 punto 5):** leer sin bloquear; bloquear cuentas, el invernadero, los `Insumo` y `InsumoInvernadero` de las líneas, sus
  lotes, la orden y las líneas; volver a verificar (9a: lo pendiente no cambió y las líneas siguen «pendiente»; 9b: destinos activos). Crear la
  recepción (es un `OrigenDocumento`) y sus detalles; por cada detalle con cantidad > 0, `stock.registrar_ingreso_por_recepcion(iin_id, partes,
  origen_id=recepcion.id)` y un `DetalleRecepcionMovimiento` por movimiento devuelto; estados de las líneas (`completo` si lo acumulado iguala lo
  pedido) y de la orden (regla 24 de 8.16); inconvenientes, el reclamo sin emitir, la alerta del Gerente y su `AlertaCompras` (7f);
  `pagos.avisar_si_quedo_para_pagar(...)` (D-91); **por último** el asiento: `registrar_asiento_automatico(actor, recepcion, hoy,
  [(INSUMOS_EN_STOCK, DEBE, importe), (PROVEEDORES, HABER, importe)])` con el importe de D-89 punto 4 (devuelve `None` si no ingresó nada).
  Auditar cada cosa creada o modificada (postcondición l). `on_commit`: correo al proveedor con lo recibido y lo no aceptado.
- **Fecha de vencimiento anterior a hoy** en una parte (5e): no es un ingreso, es un inconveniente `vencido_o_por_vencer`; la pantalla lo
  convierte y el servicio rechaza un ingreso con vencimiento pasado (`ErrorDeCompras` `vencimiento_pasado`).
- **Alertas:** las resuelve `inventario` (`reevaluar_alertas_del_insumo`, dentro de la función de ingreso); el resumen las muestra con la misma
  función en modo lectura.
- **11a:** al terminar, si quedaron líneas pendientes, la pantalla ofrece «Cerrar con faltante» con esas líneas (CMP-CRR-FLT, extensión 2a).

### CMP-CRR-FLT (CMP-04)

- `cerrar_con_faltante(actor, lineas=[(detalle_orden_id, motivo)])`: mismos permisos y bloqueos que la recepción (invernadero → `InsumoInvernadero`
  → orden → líneas); verificar «pendiente» (7a); `cerrado_con_faltante`, motivo y `fecha_cierre_faltante = hoy`; `stock.restar_transito(iin_id,
  pedido − recibido)`; reevaluar alertas (`alertas_de_stock.reevaluar_alertas_del_insumo`); estado de la orden; `avisar_si_quedo_para_pagar`;
  auditar `cierre_con_faltante` (y la modificación del `InsumoInvernadero`). **Sin asiento.** `on_commit`: correo al proveedor (R4).

### Lo que se completa en otras tareas

- La ficha de la orden (CMP-CNS-ODC) suma la sección «Recepciones» (regla 6) y los atajos «por recibir» y «con reclamo sin emitir».
- Panel del Agrónomo: «mercadería por recibir» (`panelAgr`).
- `contabilidad.registrar_enlace_de_origen("recepcion", ...)` → la ficha de la orden.

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| CMP-REG-RCP: cada regla, extensión y postcondición (incluidos: faltante sin lote cubierto primero, varios lotes por línea, línea en 0 por daño, sobreentrega rechazada, asiento con la valorización de D-89) | `test_cmp_reg_rcp.py` |
| CMP-CRR-FLT | `test_cmp_crr_flt.py` |
| Proveedores en cero: tres recepciones parciales y el valor acumulado igual al total (D-89 punto 4) | `test_valorizacion.py` |
| Las funciones nuevas de `inventario` (con `verificar_invariantes` de stock) | `inventario/tests/test_stock_compras.py` |
| Concurrencia: dos recepciones de la misma línea (no superan lo pendiente); recibir contra cerrar con faltante; recepción contra consumo del mismo insumo (el tránsito y el stock no pierden cambios); el ejercicio se bloquea último | `test_recepciones_concurrencia.py` |

### Pantallas (prototipo)

`tabRec` (2411) «Por recibir», `VIEWS.c_rcp` (2561) registrar recepción (con lotes, vencimientos e inconvenientes), `VIEWS.c_flt` (2590) cerrar con
faltante. El prototipo ya usa los tipos de inconveniente de P4 (línea 2545) y muestra el atraso sin declararlo.
