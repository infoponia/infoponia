# Casos de uso · compras · Pedidos de cotización y cotizaciones

Copia para el repo de CMP-RLZ-PED (v0.2) y CMP-ENV-COT (v0.2), de «CU extendidos» (Drive), y CMP-CNS-PED y CMP-CNL-PED (A0, v0.1). Fuentes: Drive «CU extendidos» (exportado el 23/11/2026), `CMP-alto-nivel.md` y `CMP-CNL-PED.md`. Cotejado con `decisiones_A0.md` y `pendientes_para_pegar.md`: **esas decisiones ganan** si algo
difiere (regla del estudiante del 23/11/2026); lo que cambian está en «Actualizaciones de A0 que mandan», al final de cada caso de uso o del
archivo.

**El código va en la app `compras`** (D-37, nivel 6; D-87). Archivos de pruebas bajo `compras/tests/`. Si este archivo y el documento de
Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>`, `test_post_<letra>_<que_espera>` y
`test_ext_<codigo>_<que_espera>`.

---

## **Caso de uso CMP-RLZ-PED: Realizar Pedido**

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Compras e Inventario.  
 **Versión:** 0.2

**Actor principal:** Agrónomo.

**Personal involucrado e intereses:**

  - **Agrónomo:** quiere reponer a tiempo los insumos de sus invernaderos sin tener que revisar el stock uno por uno. Quiere pedir en un solo pedido lo que necesita para varios invernaderos y que le coticen los proveedores que eligió.
  - **Proveedor:** quiere recibir un pedido claro, con qué insumos, cuánto, dónde entregarlos y hasta cuándo puede cotizar, para ofrecer un precio que contemple el flete.
  - **Capataz y Técnico:** quieren contar con los insumos (semillas, nutrientes, repuestos, envases) cuando planifican y concretan sus órdenes.
  - **Gerente:** quiere saber qué se pidió, quién lo pidió y cuánto se estima gastar antes de aprobar cualquier compra.
  - **Organización (Jardín Botánico):** quiere evitar quedarse sin insumos, comprar al mejor precio comparando proveedores y tener trazabilidad desde el pedido hasta la recepción.

**Relaciones con otros casos de uso:**

  - No incluye («include») otros casos de uso. Lo extiende CMP-HAB-IIN · Habilitar Insumo en Invernadero (extensión 3a.1a).
  - El enlace que envía a cada proveedor habilita CMP-ENV-COT · Enviar Cotización.
  - Las cotizaciones recibidas se resuelven en CMP-GNR-ODC · Generar Orden de Compra.
  - Puede iniciarse desde la alerta de insumo bajo el mínimo, que no se resuelve con este caso de uso sino al registrar la recepción (CU-53).

**Precondiciones:**

a. El Agrónomo está autenticado en el Sistema.

b. El Agrónomo tiene a su cargo al menos un invernadero en estado “activo”, con al menos un insumo activo habilitado.

c. Existe al menos un proveedor en estado “activo” con correo electrónico registrado.

**Garantías mínimas:**

  - El registro es atómico. Si el caso de uso se cancela o falla, no queda registrado ningún pedido, detalle de pedido, invitación ni log de auditoría parcial, y no se envía ningún correo.
  - El pedido no modifica el stock actual, la cantidad en tránsito, el stock mínimo ni las reservas de ningún insumo, ni la contabilidad, cualquiera sea la forma en que termine el caso de uso.
  - Ningún pedido repite el par insumo–invernadero en dos detalles.
  - Ningún proveedor recibe el precio de referencia de los insumos.

**Garantías de éxito (Postcondiciones):**

a. Se creó un pedido en estado “en cotización”, con:

  - fecha de pedido igual a la fecha actual;
  - la fecha límite de cotizaciones indicada;
  - monto estimado igual a la suma de cantidad × precio unitario de sus detalles;
  - sin fecha de cierre.

El pedido está asociado al Agrónomo que lo realizó.

b. Se crearon uno o más detalles de pedido, uno por cada par insumo–invernadero. Cada detalle tiene la cantidad pedida y un precio unitario igual al precio de referencia del insumo en el invernadero de destino en ese momento, y está asociado al insumo y al invernadero de destino.

c. El pedido quedó asociado a cada proveedor invitado.

d. Se generó un enlace de acceso para cada proveedor invitado, asociado al pedido. Vence al terminar el día de la fecha límite de cotizaciones.

e. Se envió a cada proveedor invitado un correo con su enlace, el detalle de lo pedido y la fecha límite.

f. Si el pedido se inició desde una alerta de insumo bajo el mínimo, la alerta sigue sin resolver.

g. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del pedido, de cada detalle de pedido y de cada invitación a un proveedor.

**Escenario principal de éxito (o Flujo Básico):**

1.  El Agrónomo inicia un nuevo pedido.
2.  El Sistema presenta los insumos bajo el mínimo de los invernaderos activos a cargo del Agrónomo. Para cada uno indica:
      
      - el invernadero y el insumo, con su unidad de medida;
      - el stock libre, la cantidad en tránsito y el stock mínimo;
      - la cantidad sugerida;
      - si ya figura en otro pedido “en cotización”.
3.  El Agrónomo selecciona los insumos que incluye y, para cada uno, confirma o modifica la cantidad sugerida.
4.  El Sistema verifica las cantidades, agrega los detalles al pedido con su precio de referencia y presenta el monto estimado. *El Agrónomo repite los pasos 3 y 4 hasta terminar de armar el pedido.*
5.  El Agrónomo indica que terminó de armar el pedido.
6.  El Sistema propone la fecha límite de cotizaciones y presenta los proveedores activos, con su especialidad.
7.  El Agrónomo confirma o modifica la fecha límite y selecciona los proveedores a invitar.
8.  El Sistema verifica la fecha límite y los proveedores seleccionados.
9.  El Sistema presenta el resumen del pedido:
      
      - los detalles agrupados por invernadero de destino, con el insumo, la cantidad, la unidad, el precio de referencia y el subtotal;
      - el monto estimado;
      - la fecha límite de cotizaciones;
      - los proveedores invitados.
10. El Agrónomo confirma el pedido.
11. El Sistema registra el pedido “en cotización”, sus detalles y las invitaciones a los proveedores, genera el enlace de cada proveedor y registra la auditoría correspondiente.
12. El Sistema envía a cada proveedor invitado el correo con su enlace.
13. El Sistema informa al Agrónomo que el pedido fue registrado y presenta su identificador.

**Extensiones (o Flujos Alternativos):**

**\*a.** En cualquier momento antes del paso 10, el Agrónomo cancela el pedido:

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.

**\*b.** En cualquier momento el Sistema falla o se interrumpe la conexión:

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que el pedido no fue registrado.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.

**1a.** El Agrónomo inicia el pedido desde una alerta de insumo bajo el mínimo:

1.  El Sistema incluye en el pedido el insumo y el invernadero de la alerta, con la cantidad sugerida.
2.  El caso de uso continúa en el paso 2. En el paso 3, el Agrónomo puede modificar la cantidad del insumo de la alerta, quitarlo o agregar otros.

**2a.** No hay insumos bajo el mínimo en los invernaderos del Agrónomo:

1.  El Sistema informa que no hay insumos bajo el mínimo.
2.  El caso de uso continúa en la extensión 3a.

**3a.** El Agrónomo agrega un insumo que no está en la lista de insumos bajo el mínimo:

1.  El Agrónomo selecciona uno de sus invernaderos activos y busca el insumo en el catálogo.
2.  El Sistema presenta el stock libre, la cantidad en tránsito y el stock mínimo del insumo en ese invernadero.
3.  El Agrónomo indica la cantidad a pedir.
4.  El caso de uso continúa en el paso 4.

**3a.1a.** El insumo no está habilitado en el invernadero seleccionado:

1.  El Sistema informa que el insumo no está habilitado en ese invernadero y ofrece habilitarlo.
2.  El Agrónomo ejecuta CMP-HAB-IIN · Habilitar Insumo en Invernadero para ese insumo y el caso de uso continúa en 3a.2, con el insumo habilitado, que tiene stock cero y ningún lote; o selecciona otro insumo u otro invernadero (vuelve a 3a.1) o cancela.

**3b.** El Agrónomo quita un detalle ya agregado o cambia su cantidad:

1.  El Sistema actualiza los detalles y el monto estimado.
2.  El caso de uso continúa en el paso 3.

**4a.** La cantidad indicada no es mayor que cero o tiene más de dos decimales:

1.  El Sistema señala el error.
2.  El Agrónomo corrige la cantidad (vuelve al paso 3).

**4b.** El par insumo–invernadero ya está en el pedido:

1.  El Sistema informa que ese insumo ya figura en el pedido para ese invernadero y presenta su cantidad actual.
2.  El Agrónomo modifica la cantidad del detalle existente (continúa en 3b) o descarta el agregado.

**4c.** El par insumo–invernadero ya está en otro pedido “en cotización”, o en un pedido “cerrado” cuya orden de compra está “pendiente de aprobación”:

1.  El Sistema advierte que ese insumo ya fue pedido para ese invernadero e informa el identificador del otro pedido, su cantidad y, según su estado, su fecha límite de cotizaciones o que su orden de compra está pendiente de aprobación.
2.  El Agrónomo mantiene el detalle (continúa en el paso 4) o lo quita (continúa en 3b).

**5a.** El pedido no tiene ningún detalle:

1.  El Sistema informa que el pedido debe incluir al menos un insumo.
2.  El Agrónomo agrega un insumo (vuelve al paso 3 o a 3a) o cancela.

**6a.** Un proveedor activo no tiene correo registrado:

1.  El Sistema lo presenta en la lista sin permitir seleccionarlo e informa que hay que completarle el correo para poder invitarlo.

**7a.** El Agrónomo filtra la lista de proveedores por especialidad:

1.  El Sistema presenta solo los proveedores activos de esa especialidad.
2.  El caso de uso continúa en el paso 7.

**7b.** El Agrónomo selecciona todos los proveedores:

1.  El Sistema selecciona todos los proveedores activos que figuran en la lista y que tienen correo. Si la lista está filtrada, selecciona solo los proveedores filtrados.
2.  El caso de uso continúa en el paso 7.

**8a.** La fecha límite es anterior al día siguiente a la fecha actual:

1.  El Sistema señala el error e informa la primera fecha admitida.
2.  El Agrónomo introduce una nueva fecha (vuelve al paso 7).

**8b.** El Agrónomo no seleccionó ningún proveedor:

1.  El Sistema informa que debe invitar al menos a un proveedor.
2.  El Agrónomo selecciona proveedores (vuelve al paso 7).

**10a.** El Agrónomo quiere corregir un dato del resumen:

1.  El Agrónomo indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (3 o 7).

**11a.** Entre las verificaciones y la confirmación cambió alguna condición del pedido. Por ejemplo:

  - un insumo dejó de estar activo o habilitado en su invernadero;
  - un invernadero dejó de estar activo o a cargo del Agrónomo;
  - un proveedor dejó de estar activo o se quedó sin correo.

<!-- end list -->

1.  El Sistema no registra ningún cambio e informa qué dato cambió.
2.  El caso de uso vuelve al paso afectado (3 o 7).

**12a.** El Sistema no logra enviar el correo a un proveedor:

1.  El pedido y la invitación permanecen registrados.
2.  El Sistema reintenta el envío.
3.  En el paso 13, el Sistema avisa además al Agrónomo a qué proveedores no se pudo enviar el correo todavía.

**Requisitos especiales:**

  - La interfaz del Agrónomo está pensada para computadora.
  - Tras cada selección o dato ingresado por el Agrónomo (pasos 3 a 8), la pantalla se actualiza con las verificaciones y el monto estimado en no más de 1 segundo.
  - El registro del paso 11 se completa en no más de 5 segundos y se ejecuta como una única transacción: el pedido, sus detalles, las invitaciones, los enlaces y los logs se registran juntos o no se registra ninguno. El envío de los correos (paso 12) queda fuera de la transacción.
  - El enlace de cada proveedor contiene un identificador no adivinable. Solo da acceso a ese pedido y solo para ese proveedor.
  - Solo el rol Agrónomo accede a este caso de uso, y únicamente sobre los invernaderos que tiene a cargo.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los montos se expresan en pesos argentinos, con dos decimales.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio:**

  - **Insumo pedible:** insumo activo, habilitado (con existencia registrada) en un invernadero activo a cargo del Agrónomo. (Pasos 2 y 3, y extensión 3a)
  - **Insumo bajo el mínimo:** stock libre + cantidad en tránsito \< stock mínimo, en ese invernadero. El stock libre es el stock actual, sin contar los lotes vencidos, menos lo reservado en reservas de insumo activas. Es el mismo criterio que usa la alerta de insumo bajo el mínimo. (Paso 2)
  - **Cantidad sugerida:** stock mínimo − (stock libre + cantidad en tránsito). El Sistema no incluye ningún insumo por su cuenta: el Agrónomo elige cuáles incluir. (Pasos 2 y 3)
  - **Cantidad pedida:** mayor que cero, con hasta dos decimales, expresada en la unidad de medida del insumo. (Paso 4)
  - **Detalle único:** un pedido no repite el par insumo–invernadero. El mismo insumo puede aparecer más de una vez si va a invernaderos distintos. (Paso 4 y extensión 4b)
  - **Insumo ya pedido:** si el par insumo–invernadero está en otro pedido “en cotización”, o en un pedido “cerrado” cuya orden de compra está “pendiente de aprobación”, el Sistema advierte y deja continuar (regla 14 de 8.15). (Extensión 4c) 
  - **Precio y monto estimado:** el precio unitario de cada detalle es una copia del precio de referencia del insumo en el invernadero de destino al registrar el pedido. El monto del pedido es Σ cantidad × precio unitario, solo como estimación. El precio no se muestra a los proveedores. (Pasos 4 y 11)
  - **Fecha límite de cotizaciones:** el Sistema propone la fecha actual más los días límite de cotización de la configuración operativa. El Agrónomo puede cambiarla, pero como mínimo debe ser el día siguiente a la fecha actual. (Pasos 6 y 8)
  - **Proveedores invitables:** proveedores en estado “activo” con correo registrado. El Agrónomo elige a cuáles invitar, al menos a uno. El Sistema no selecciona ninguno por su cuenta, salvo que el Agrónomo pida seleccionarlos todos. (Pasos 6 a 8)
  - **Enlace del proveedor:**
      
      - uno por cada proveedor invitado;
      - vence al terminar el día de la fecha límite de cotizaciones;
      - solo da acceso al pedido para el que se generó.
  - (Paso 11)
  - **Estado inicial:** el pedido nace “en cotización”. Pasa a “cerrado” cuando vence la fecha límite y se resuelven sus cotizaciones, o a “cancelado”. El avance de la compra se registra en cada orden de compra. (Paso 11)
  - **Efectos sobre el inventario:** el pedido no modifica el stock actual ni la cantidad en tránsito. La cantidad en tránsito aumenta recién al aprobarse la orden de compra (CU-52). (Paso 11)
  - **Alerta de insumo bajo el mínimo:** no se resuelve al pedir. Se resuelve al registrar la recepción, cuando el insumo deja de estar bajo el mínimo. (Extensión 1a)

**Lista de tecnología y variaciones de datos:**

2a. La unidad de medida de un insumo es kg, g, litro, ml o unidad.

3a. Las cantidades se ingresan con hasta dos decimales. El insumo se busca en el catálogo por nombre o por tipo de insumo.

6a. La fecha límite se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.

7a. La especialidad del proveedor se usa como filtro de la lista.

12a. El correo al proveedor incluye:

  - el enlace de acceso;
  - por cada detalle: el nombre, la descripción y la unidad del insumo, la cantidad y el invernadero de destino con su dirección;
  - la fecha límite de cotizaciones.

No incluye el precio de referencia ni el monto estimado.

**Frecuencia:** a confirmar con el Jardín Botánico. Depende del consumo de insumos de cada invernadero y de la frecuencia con que sus insumos quedan bajo el mínimo.

**Temas abiertos:**

  - Todavía no existe un caso de uso para habilitar un insumo en un invernadero. Cuando exista, este caso de uso agrega una extensión que lo invoque y vuelva al pedido. \[Resuelto el 15/11/2026 (MD-82): el caso de uso es CMP-HAB-IIN · Habilitar Insumo en Invernadero, y este caso de uso lo tiene como extensión (3a.1a).\]
  - El pedido no indica para cuándo se necesitan los insumos, y la cotización no informa un plazo de entrega. ¿Se resuelve en Enviar Cotización?
  - ¿Se puede invitar a más proveedores o reenviar un enlace después de registrar el pedido, mientras siga “en cotización”?
  - ¿Qué proceso genera la alerta de insumo bajo el mínimo, y en qué momentos se evalúa?



---

## **Caso de uso CMP-ENV-COT: Enviar Cotización**

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Compras e Inventario.  
 **Versión:** 0.2  
 **Actor principal:** Proveedor invitado al pedido. Es un actor externo, sin usuario en el Sistema, que accede mediante el enlace que recibió por correo.

**Personal involucrado e intereses**

**Proveedor:**

  - quiere cotizar de forma simple y sin registrarse, en una sola pantalla, los insumos que puede ofrecer y en las cantidades que puede cubrir;
  - quiere tomarse el tiempo necesario hasta la fecha límite;
  - quiere dejar claro hasta cuándo sostiene sus precios;
  - quiere constancia de lo que ofreció.

**Agrónomo:**

  - quiere recibir cotizaciones comparables, con precio final puesto en el invernadero, plazo de entrega y validez;
  - quiere enterarse cuando el pedido ya está cubierto, sin recibir un aviso por cada cotización.

**Gerente:** quiere que las órdenes de compra que aprueba salgan de ofertas reales, registradas, trazables y con precios vigentes.

**Organización (Jardín Botánico):** quiere cuatro cosas:

  - comparar ofertas en igualdad de condiciones, sin que un proveedor conozca el precio de referencia ni las ofertas de los demás;
  - que nadie cambie su oferta después de enviarla;
  - que solo coticen los proveedores invitados;
  - que toda oferta tenga un plazo de validez conocido.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - Lo habilita CMP-RLZ-PED · Realizar Pedido, que envía el enlace a cada proveedor invitado.
  - Las cotizaciones registradas se comparan y se eligen en CMP-GNR-ODC · Generar Orden de Compra.
  - Si el pedido se cancela (Cancelar Pedido, por especificar, o por MD-62 cuando su Agrónomo pasa a inactivo o deja el invernadero de destino), el enlace deja de servir y las cotizaciones “propuesta” pasan a “descartada”.

**Precondiciones**

a. El Proveedor recibió un enlace de cotización.

**Garantías mínimas**

  - El envío es atómico. Si el Proveedor abandona el envío antes de confirmarlo, o si el caso de uso falla, no se registra ninguna cotización, línea, notificación ni log de auditoría parcial, y el enlace sigue sirviendo mientras esté vigente.
  - Un proveedor tiene como máximo una cotización por pedido, con a lo sumo una línea por cada detalle de ese pedido.
  - Una cotización enviada no se modifica.
  - El Proveedor solo ve el pedido de su enlace y su propia cotización. No ve el precio de referencia, las cotizaciones de otros proveedores ni a quién más se invitó.
  - Este caso de uso no modifica el estado del pedido, sus detalles, el stock ni la contabilidad.

**Garantías de éxito (Postcondiciones)**

a. Se creó una cotización en estado “propuesta”, asociada al Proveedor, con:

  - fecha de cotización igual a la fecha actual;
  - la fecha de validez indicada;
  - las observaciones, si se indicaron;
  - monto igual a la suma de los subtotales de sus líneas.

b. Se creó una línea de cotización por cada detalle cotizado, asociada a su detalle de pedido, con la cantidad cotizada, el precio unitario cotizado, el plazo de entrega en días y el subtotal (cantidad × precio unitario).  
 c. El enlace del Proveedor quedó sin servir para nuevos envíos. Si lo vuelve a abrir, solo ve su cotización.  
 d. Se envió al Proveedor por correo el acuse de la cotización.  
 e. Si con esta cotización el pedido quedó cubierto por primera vez, se notificó al Agrónomo que realizó el pedido. El pedido siguió “en cotización”.  
 f. Se creó un log de auditoría con origen “proveedor mediante enlace”, el identificador del proveedor y el del pedido, la fecha, la hora y el identificador de la cotización y de cada línea creadas.

**Escenario principal de éxito (o Flujo Básico)**

(El Proveedor cotiza algunos detalles del pedido, no todos, en una sola cotización, sin que con su envío el pedido quede cubierto.)

1.  **El Proveedor abre el enlace de cotización.**
2.  **El Sistema verifica el enlace y presenta el pedido:**
      
      - la fecha límite de cotizaciones;
      - por cada detalle: el insumo (nombre, descripción y unidad), la cantidad pedida y el invernadero de destino con su dirección;
      - la fecha de validez propuesta para la cotización.
3.  **El Proveedor elige un detalle para cotizarlo.**
4.  **El Sistema propone la cantidad pedida como cantidad cotizada.**
5.  **El Proveedor confirma o modifica la cantidad cotizada e indica el precio unitario y el plazo de entrega en días.**
6.  **El Sistema verifica la línea y presenta su subtotal y el monto de la cotización.** *El Proveedor repite los pasos 3 a 6 por cada detalle que quiere cotizar. Los detalles que no elige quedan sin cotizar.*
7.  **El Proveedor confirma o modifica la fecha de validez y, si lo desea, ingresa observaciones.**
8.  **El Proveedor indica que terminó de armar la cotización.**
9.  **El Sistema verifica la fecha de validez y presenta el resumen de la cotización:**
      
      - cada línea, con el insumo, el invernadero de destino, la cantidad, el precio unitario, el subtotal y el plazo;
      - el monto de la cotización;
      - la fecha de validez y las observaciones;
      - la advertencia de que la cotización se envía una sola vez y no podrá modificarse ni reemplazarse.
10. **El Proveedor confirma el envío.**
11. **El Sistema registra la cotización en estado “propuesta” con sus líneas, deja el enlace sin servir para nuevos envíos y registra la auditoría correspondiente.**
12. **El Sistema envía al Proveedor el acuse de la cotización.**
13. **El Sistema informa al Proveedor que la cotización fue registrada y que ya no puede modificarla ni enviar otra.**

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 10, el Proveedor abandona el envío (por ejemplo, cierra la página):**

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
2.  El enlace sigue sirviendo mientras esté vigente.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Proveedor puede volver a abrir el enlace mientras esté vigente. Si la cotización llegó a registrarse, se aplica la extensión 2b.

**2a. El enlace no es válido, el proveedor no está invitado al pedido o está inactivo, el pedido ya no está “en cotización”, o venció la fecha límite:**

1.  El Sistema informa que el enlace no puede usarse y el motivo.
2.  El caso de uso termina.

**2b. El Proveedor ya envió su cotización para este pedido:**

1.  El Sistema informa que ya no puede enviar otra cotización y presenta la suya en modo de solo lectura: líneas, monto, fecha de validez, observaciones y fecha de envío.
2.  El caso de uso termina.

**3a. El Proveedor quiere quitar un detalle que ya agregó, o modificar su línea, antes de confirmar:**

1.  El Proveedor indica la línea.
2.  El Sistema la quita de la cotización (vuelve al paso 3) o la presenta para modificarla (vuelve al paso 5).

**6a. La cantidad cotizada no es mayor que cero, supera la cantidad pedida o tiene más de dos decimales:**

1.  El Sistema señala el error e informa la cantidad pedida.
2.  El Proveedor corrige la cantidad (vuelve al paso 5).

**6b. El precio unitario no es mayor que cero o tiene más de dos decimales:**

1.  El Sistema señala el error.
2.  El Proveedor corrige el precio (vuelve al paso 5).

**6c. Falta el plazo de entrega, o no es un número entero mayor o igual que cero:**

1.  El Sistema señala el error.
2.  El Proveedor corrige el plazo (vuelve al paso 5).

**8a. El Proveedor indica que terminó sin haber cotizado ningún detalle:**

1.  El Sistema informa que la cotización debe incluir al menos un detalle.
2.  El Proveedor elige un detalle (vuelve al paso 3) o abandona el envío.

**9a. Falta la fecha de validez, o es anterior a la fecha límite de cotizaciones del pedido:**

1.  El Sistema señala el error e informa la fecha límite y la fecha propuesta.
2.  El Proveedor corrige la fecha (vuelve al paso 7).

**10a. El Proveedor quiere corregir un dato del resumen:**

1.  El Proveedor indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó: 3 para agregar un detalle, 3a para quitar o modificar una línea, 7 para la fecha de validez o las observaciones.
2.  El Proveedor vuelve a indicar que terminó (paso 8).

**11a. Al registrar se produce alguna de estas situaciones, por ejemplo porque el Proveedor armó la cotización durante varias horas:**

  - venció la fecha límite;
  - el pedido dejó de estar “en cotización”;
  - el proveedor pasó a “inactivo”.

<!-- end list -->

1.  El Sistema no registra ningún cambio e informa que el enlace ya no puede usarse y el motivo.
2.  El caso de uso termina.

**11b. Al registrar, ya existe una cotización del Proveedor para el pedido (por ejemplo, la envió desde otra pestaña):**

1.  El Sistema no registra ningún cambio e informa que ya había enviado una cotización.
2.  El caso de uso continúa en la extensión 2b.

**11c. Con esta cotización, el pedido queda cubierto por primera vez:**

1.  Una vez registrada la cotización, el Sistema notifica al Agrónomo que realizó el pedido que el pedido está cubierto.
2.  El pedido sigue “en cotización” hasta la fecha límite.
3.  El caso de uso continúa en el paso 12.

**12a. El Sistema no logra enviar el acuse al Proveedor o la notificación al Agrónomo:**

1.  La cotización permanece registrada.
2.  El Sistema reintenta el envío.

**Requisitos especiales**

  - El enlace se abre desde cualquier navegador web moderno, en celular o en computadora, sin instalación ni inicio de sesión. La pantalla se adapta a pantallas pequeñas, y la cotización completa se arma en una sola pantalla.
  - El enlace contiene un identificador no adivinable. Solo da acceso al pedido para el que se generó, y solo para ese proveedor.
  - La pantalla del paso 2 se presenta en no más de 2 segundos.
  - El registro del paso 11 se completa en no más de 5 segundos y se ejecuta como una única transacción: la cotización, sus líneas y sus logs se registran juntos o no se registra ninguno. El acuse y el aviso de pedido cubierto se envían fuera de la transacción.
  - El control de concurrencia cumple dos funciones:
      
      - impide que un proveedor registre dos cotizaciones para el mismo pedido, por ejemplo desde dos pestañas;
      - garantiza que el aviso de pedido cubierto se envíe una sola vez, aunque dos proveedores envíen sus cotizaciones al mismo tiempo.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios y montos se expresan en pesos argentinos, con dos decimales.
  - Los logs de auditoría son de solo inserción. Indican como origen “proveedor mediante enlace”, con el identificador del proveedor y el del pedido.

**Reglas de negocio**

  - **Enlace del proveedor:** se genera uno por proveedor invitado y por pedido (R157). (Pasos 2 y 11, y extensiones 2a, 2b, 11a y 11b)
      
      - Admite un solo envío.
      - Deja de servir en cuatro casos: al terminar el día de la fecha límite, cuando el pedido deja de estar “en cotización”, cuando el proveedor pasa a “inactivo” o cuando el proveedor ya envió su cotización (regla 2 de 8.16).
      - La vigencia se controla al abrirlo y también al registrar.
      - Si el proveedor ya envió su cotización, el enlace solo la muestra en modo de solo lectura.
  - **Una cotización por proveedor y por pedido:** un proveedor ofrece como máximo una cotización por pedido. La cotización se arma completa y se envía una sola vez; una vez enviada, no se modifica ni se reemplaza (C8; regla 19 de 8.15; reglas 1 y 3 de 8.17). (Paso 11 y extensión 11b)
  - **Líneas de la cotización:** una por cada detalle que el proveedor cotiza, a lo sumo una por detalle, y al menos una. La cotización puede cubrir una parte o todos los detalles del pedido (C8; regla 1 de 8.17). (Pasos 3 a 6 y extensión 8a)
  - **Detalles abiertos:** mientras el pedido está “en cotización”, todos sus detalles están abiertos para todos los invitados, sin importar lo que ya cotizaron otros. La cobertura se resuelve en CMP-GNR-ODC. (Pasos 2 y 3)
  - **Cantidad cotizada:** mayor que cero, menor o igual que la cantidad pedida, con hasta dos decimales, en la unidad del insumo. El Sistema propone la cantidad pedida. (Pasos 4 a 6)
  - **Precio unitario cotizado:** precio final por unidad, puesto en el invernadero de destino, con flete e impuestos incluidos. Es mayor que cero, con dos decimales. (Pasos 5 y 6)
  - **Plazo de entrega:** días corridos, contados desde la aprobación de la orden de compra. Es un entero mayor o igual que cero. Al aprobarse la orden, la fecha de entrega esperada de su detalle es la fecha de aprobación más este plazo. (Pasos 5 y 6)
  - **Subtotal y monto:** el subtotal de una línea es cantidad × precio unitario; el monto de la cotización es la suma de los subtotales de sus líneas. Los dos son derivados (regla 6 de 8.17). (Paso 6)
  - **Observaciones:** van en la cotización, no en cada línea, y son opcionales. (Paso 7)
  - **Insumo cotizado:** solo se cotiza el insumo pedido. Si el proveedor ofrece uno equivalente, lo aclara en las observaciones, indicando a qué detalle se refiere. (Pasos 5 y 7)
  - **Validez de la cotización:** el Proveedor indica hasta qué fecha sostiene sus precios. El Sistema propone la fecha límite de cotizaciones del pedido más los días de validez de la configuración operativa (diasValidezCotizacion), y no acepta una fecha anterior a la fecha límite. Una cotización con la validez vencida se muestra, pero no se puede elegir, en CMP-GNR-ODC (MD-64; regla 6 de 8.22). (Pasos 2, 7 y 9, y extensión 9a)
  - **Estado inicial:** la cotización nace “propuesta”. En CMP-GNR-ODC pasa, completa, a “seleccionada” o a “descartada”. Si el pedido se cancela, pasa a “descartada” (regla 3 de 8.17). (Paso 11)
  - **Información visible:** el Proveedor ve la fecha límite, los detalles del pedido con su destino y su propia cotización. No ve el precio de referencia, las cotizaciones de otros proveedores ni a quién más se invitó. (Paso 2 y extensión 2b)
  - **Pedido cubierto:** (Extensión 11c)
      
      - Un pedido está cubierto cuando, en cada uno de sus detalles, la suma de las cantidades cotizadas en las líneas de las cotizaciones recibidas alcanza la cantidad pedida × (1 − porcentaje de tolerancia de cobertura). Es el mismo criterio de cobertura con tolerancia que usa CMP-GNR-ODC (regla 14 de 8.16; porcToleranciaCoberturaPedido).
      - Como mientras el pedido está “en cotización” las cotizaciones solo se agregan, el pedido pasa de “no cubierto” a “cubierto” una sola vez. En ese momento se avisa al Agrónomo. El Sistema lo detecta sin un atributo nuevo, comparando la cobertura antes y después de registrar.
      - El aviso es informativo: no considera precio, plazo ni validez, y no cierra el pedido antes de la fecha límite.
  - **Destinatario del aviso de pedido cubierto:** el Agrónomo que realizó el pedido. Si estuviera inactivo, el aviso va al Agrónomo activo del invernadero de destino o, si no hay, al Gerente (MD-62; regla 5 de 8.22). En la práctica no ocurre, porque el pedido de un Agrónomo inactivo se cancela y su enlace deja de servir. (Extensión 11c)
  - **Proveedor que pasa a inactivo:** la cotización que ya envió se mantiene. (Extensión 11a)

**Lista de tecnología y variaciones de datos**

  - **2a.** Las fechas se presentan con formato dd/mm/aaaa.
  - **5a.** La cantidad cotizada se ingresa en la unidad de medida del insumo (kg, g, litro, ml o unidad), con hasta dos decimales. El precio unitario se ingresa en pesos, con dos decimales. El plazo de entrega se ingresa en días, como número entero.
  - **7a.** La fecha de validez se ingresa con formato dd/mm/aaaa, mediante calendario o teclado. El Sistema propone por defecto la fecha límite más diasValidezCotizacion. Las observaciones son texto libre.
  - **12a.** El acuse al Proveedor indica el pedido, la fecha y la hora del envío, cada línea (insumo, invernadero de destino, cantidad, precio unitario, subtotal y plazo), el monto de la cotización, la fecha de validez y las observaciones.
  - **11c.** El aviso al Agrónomo indica el pedido, la fecha límite y la cantidad de líneas de cotización recibidas por detalle.

**Frecuencia**

Como máximo una cotización por cada proveedor invitado a un pedido, hasta la fecha límite. Depende de la cantidad de pedidos y de proveedores invitados.

**Temas abiertos**

  - El proveedor no puede indicar “no cotizo este detalle” ni “no participo”: queda como mejora futura.
  - Extender Pedido (reabrir el pedido con una fecha límite nueva e invitar a más proveedores) queda como mejora futura.



---

## **Caso de uso CMP-CNS-PED: Consultar Pedido**

Caso de uso nuevo (el contexto, sección 3.1, lo propone: «ningún caso de uso deja ver el historial de compras»). La parte de órdenes de compra (CMP-CNS-ODC) se escribe aparte, después de H20 a H24.

**Actores:** Agrónomo o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver el estado y la historia de los pedidos, qué cotizó cada proveedor invitado y qué falta resolver.

**Precondición:**

a. El actor está identificado con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta, salvo la acción «Reenviar invitación» (regla 7), que tiene su propio efecto y auditoría.

**Reglas:**

1.  Alcance: el Agrónomo ve los pedidos que él realizó; el Gerente ve todos, en solo lectura (decisión sobre el ABM de Proveedor).
2.  Filtros: estado (en cotización, cerrado, cancelado), invernadero de destino, proveedor invitado, rango de fechas (de pedido o de la fecha límite) y, solo para el Gerente, Agrónomo.
3.  Listado: identificador, fecha del pedido, fecha límite de cotizaciones, monto estimado, cantidad de proveedores invitados y de cotizaciones recibidas, y estado. Se marcan los pedidos con la fecha límite vencida por resolver (el panel del Agrónomo los muestra, H16).
4.  Ficha · pedido: el Agrónomo que lo realizó; los detalles agrupados por invernadero de destino, con insumo, cantidad, unidad, precio de referencia y subtotal; el monto estimado; si está cancelado, el motivo, la fecha de cierre y si fue automática; si está cerrado, la orden de compra que generó.
5.  Ficha · proveedores invitados: por cada uno, si cotizó o no, y el estado de su enlace (vigente, usado, vencido, anulado, reemplazado; tabla `EnlaceProveedor`, H15).
6.  Ficha · cotizaciones: la cotización enviada por cada proveedor se ve en solo lectura hasta el final del día de la fecha límite; después se compara y se elige en Generar Orden de Compra (H15.2).
7.  Acción **Reenviar invitación** (H15.1): disponible solo para el Agrónomo del pedido, con el pedido «en cotización» y para un proveedor que todavía no cotizó. El Sistema genera un enlace nuevo, el anterior pasa a «reemplazado» y se le envía el correo con el enlace nuevo. Si el correo falla, se notifica al Agrónomo, y el mensaje indica pedirle al Gerente que corrija el correo del proveedor (solo el Gerente modifica proveedores). Se audita.
8.  Acciones desde la ficha: Cancelar Pedido (CMP-CNL-PED) y Generar Orden de Compra (CMP-GNR-ODC) si venció la fecha límite, solo para el Agrónomo del pedido.
9.  El resto de la consulta no se audita (SEG-14).

**Temas abiertos:**

1.  ¿«Reenviar invitación» debería ser un caso de uso aparte (CMP-RNV-INV)? La decisión H15.1 la ubica como acción de la consulta; como cambia el enlace y envía un correo, afecta a más de una clase solo en sentido estricto (EnlaceProveedor y el log), por eso se mantuvo acá.

---



---

## **Caso de uso CMP-CNL-PED: Cancelar Pedido**

Caso de uso extendido del módulo Compras e Inventario (versión 0.1, 23/11/2026), con el formato de «CU extendidos». Sale de PCU › caso 13 («Cancelar Pedido», por especificar) y de las decisiones H16, H17 y «CMP-CNL-PED» de decisiones_A0.md. Lo marcado [confirmar] no está confirmado por Ezequiel.

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Compras e Inventario.
**Actor principal:** Agrónomo que realizó el pedido.
**Versión:** 0.1

**Personal involucrado e intereses**

**Agrónomo:**
- quiere dejar sin efecto un pedido que ya no hace falta, o que no alcanza la cobertura, y poder hacer uno nuevo;
- quiere que los proveedores dejen de cotizar algo cancelado.

**Proveedor invitado:**
- quiere enterarse de que el pedido se canceló, para no perder tiempo cotizando.

**Organización (Jardín Botánico):**
- quiere que un pedido cancelado no deje cotizaciones vivas, enlaces abiertos ni compras a medias.

**Relaciones con otros casos de uso**
- No incluye otros casos de uso.
- No es extendido por otros casos de uso.
- **Lo precede:** CMP-RLZ-PED · Realizar Pedido (el pedido nace «en cotización»).
- **Alternativa de:** CMP-GNR-ODC · Generar Orden de Compra: cuando el pedido no alcanza la cobertura, se resuelve cancelándolo (CMP-GNR-ODC, extensión 4a).
- **Disparador automático:** el proceso diario (pasos 60 y 62, H16) y los puntos de extensión de baja y traspaso del Agrónomo (MD-62, H17) cancelan pedidos con la misma función, sin actor humano (regla «Cancelaciones automáticas»).
- **Lo sigue:** CMP-CNS-PED · Consultar Pedido, donde se ve el pedido cancelado con su motivo.

**Precondiciones**
a. El actor está autenticado con una cuenta activa de Agrónomo.
b. El actor es el Agrónomo que realizó el pedido.
c. El pedido está «en cotización».

**Garantías mínimas**
La cancelación es atómica. Si se cancela o falla:
- el pedido sigue «en cotización», con sus cotizaciones y enlaces como estaban;
- no se registra ningún log de auditoría parcial y no se envía ningún correo.

**Además:**
- Cancelar no modifica el stock actual, la cantidad en tránsito, el stock mínimo ni las reservas de ningún insumo, ni la contabilidad. No hay orden de compra que cancelar: un pedido «en cotización» no la tiene.
- Las alertas de insumo bajo el mínimo no cambian (se resuelven al recibir, no al pedir).

**Garantías de éxito (Postcondiciones)**
a. El pedido pasó a «cancelado», con fecha de cierre (`fechaCierrePedido`) igual a la fecha actual, que se usa para «cerrado» y «cancelado», y el motivo de cancelación (`Pedido.motivoCancelacion`, obligatorio en la cancelación manual, texto de hasta 500 caracteres).
b. Cada cotización «propuesta» del pedido pasó a «descartada».
c. Cada enlace de proveedor «vigente» del pedido pasó a «anulado» (H15): deja de servir para cotizar.
d. Se envió por correo un aviso de cancelación a todos los proveedores invitados, sin el motivo (H15/CMP-CNL-PED).
e. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del pedido, el cambio de estado, el motivo y los cambios de las cotizaciones y los enlaces.

**Escenario principal de éxito (Flujo Básico)**
(El Agrónomo cancela un pedido «en cotización» indicando el motivo.)

1. **El Agrónomo inicia la cancelación de un pedido, desde su ficha en CMP-CNS-PED.**
2. **El Sistema presenta el pedido: sus detalles, la fecha límite, los proveedores invitados y cuáles ya cotizaron (con su monto), y advierte que la cancelación no se puede deshacer.**
3. **El Agrónomo indica el motivo de la cancelación.**
4. **El Sistema presenta el resumen: cuántas cotizaciones se descartarán, cuántos enlaces se anularán y a quién se avisará por correo.**
5. **El Agrónomo confirma la cancelación.**
6. **El Sistema registra la cancelación:**
   - bloquea el pedido y verifica que siga «en cotización»;
   - pasa el pedido a «cancelado» con su motivo y fecha de cierre;
   - descarta las cotizaciones «propuesta» y anula los enlaces vigentes;
   - registra la auditoría correspondiente.
7. **El Sistema envía el aviso de cancelación a cada proveedor invitado.**
8. **El Sistema informa al Agrónomo que el pedido fue cancelado.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 5), el Agrónomo desiste:**
1. El Sistema descarta los datos sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa que el pedido no fue cancelado.
3. El Agrónomo reinicia desde el paso 1.

**3a. Falta el motivo:**
1. El Sistema señala que el motivo es obligatorio.
2. El Agrónomo lo completa (vuelve al paso 3).

**6a. Al registrar, el pedido ya no está «en cotización» (otro usuario lo canceló o se generó su orden de compra):**
1. El Sistema no registra ningún cambio e informa el estado actual del pedido.
2. El caso de uso termina.

**7a. No se logra enviar el correo a algún proveedor:**
1. La cancelación permanece registrada.
2. El Sistema reintenta el envío.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- La cancelación del paso 6 se completa en no más de 3 segundos.
- La cancelación es una única transacción: pedido, cotizaciones, enlaces y logs se registran juntos o ninguno. Los correos se envían fuera de la transacción.
- El control de concurrencia impide que se cancele un pedido mientras se genera su orden de compra y que un proveedor envíe una cotización mientras se lo cancela.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**
- **Quién cancela:** solo el Agrónomo que hizo el pedido. Ni otro Agrónomo ni el Gerente cancelan a mano. (Decisión CMP-CNL-PED; regla 5 de 8.22 por la cual nadie más puede continuarlo)
- **Cuándo:** solo un pedido «en cotización». Una vez generada la orden de compra, el pedido está «cerrado» y no se cancela. Se puede cancelar antes o después de vencida la fecha límite, mientras siga «en cotización» (decisión de Ezequiel; también cubre el pedido que no alcanza la cobertura, CMP-GNR-ODC extensión 4a).
- **Motivo:** obligatorio en la cancelación manual; las automáticas lo completan solas con un texto fijo según su causa.
- **Cotizaciones y enlaces:** las cotizaciones «propuesta» pasan a «descartada» y los enlaces vigentes a «anulado». (CMP-ENV-COT, Relaciones; H15)
- **Aviso a los proveedores:** por correo a todos los invitados, hayan o no cotizado, sin el motivo. (CMP-CNL-PED)
- **Cancelaciones automáticas:** las hace InfoPonia, con la misma función y sin este flujo, en tres casos: (1) pedido sin ninguna cotización al vencer la fecha límite, con aviso «nadie cotizó» (H16); (2) pedido sin ninguna cotización elegible (validez vencida o proveedor inactivo), paso 62 del proceso diario (H16); (3) el Agrónomo del pedido pasó a inactivo o dejó de tener a cargo un invernadero de destino (MD-62, regla 5 de 8.22; H17). En todas se avisa según la regla H21 (cierra MD-67): a cada Agrónomo activo de los invernaderos de destino y, por cada destino sin Agrónomo activo, al Gerente; nunca se notifica a quien hizo la acción.
- **Pedido y alertas:** cancelar no resuelve ninguna alerta. (CMP-RLZ-PED, garantía f)

**Lista de tecnología y variaciones de datos**
- **3.** Motivo de cancelación: texto libre. En las automáticas: «nadie cotizó», «sin cotizaciones elegibles», «Agrónomo inactivo», «Agrónomo sin el invernadero de destino».
- **7.** El correo indica el identificador del pedido, la fecha y que el pedido fue cancelado; no incluye el motivo ni a los otros proveedores.

**Frecuencia**
Baja: pocas veces por mes.

**Temas abiertos**
1. (Resuelto) Se puede cancelar mientras esté «en cotización», antes o después de la fecha límite.
2. Si el Agrónomo del pedido dejó de estar activo (MD-62), el pedido se cancela solo; ¿no hay caso donde otra persona deba poder cancelar un pedido huérfano? Hoy no.

---

## Actualizaciones de A0 que mandan sobre el texto de arriba

Por regla del estudiante (23/11/2026), lo decidido en `decisiones_A0.md` y `pendientes_para_pegar.md` manda aunque el caso de uso de Drive todavía
no lo diga:

| Caso de uso | Qué cambia | Fuente |
|---|---|---|
| CMP-RLZ-PED | **6a queda obsoleta** (el correo del proveedor es obligatorio); la falla de envío se resuelve con «Reenviar invitación» | P5; 2.A-5 |
| CMP-RLZ-PED | **Paso 6 y 7a:** la lista se filtra por los **tipos de insumo en que se especializa** el proveedor (MD-121), no por un atributo; el Sistema **propone** el filtro con las categorías de los insumos del pedido | H13; MD-121 |
| CMP-RLZ-PED | Cantidades: decimales según la unidad del insumo (`validar_cantidad`), no «hasta dos» | regla 2 de 8.23; D-87 punto 7 |
| CMP-ENV-COT | **Cantidad cotizada puede superar la pedida** (6a: solo se rechaza no mayor que cero o con más decimales de los que admite la unidad); el plazo de entrega es un entero **≥ 1** (6c) | P2; MD-130 |
| CMP-ENV-COT | **Precio:** el proveedor carga el **total de la línea** o el unitario y el Sistema calcula el otro; se guarda el total (6b se aplica al que cargó) | MD-125; D-89 |
| CMP-ENV-COT | El enlace se **anula** también al pasar el proveedor a inactivo y al cancelarse el pedido; estados vigente / usado / vencido / anulado / reemplazado | H15, H22; MD-123 |
| CMP-ENV-COT | La cotización enviada se ve en **solo lectura hasta el final del día de la fecha límite** (2b) | H15.2 |
| CMP-ENV-COT | Teléfono del proveedor opcional (no afecta al caso de uso) | P5 |
| CMP-CNS-PED | Ya incluye «Reenviar invitación» (regla 7) y los estados del enlace (regla 5) | H15.1 |
| Todos | **Avisos al Agrónomo** según la regla única de destinatarios (H21) y nunca a quien hizo la acción | H21; D-87 punto 3 |

## Cómo se aplica (código)

Decisiones: **D-87**, **D-88**, **D-89**. Modelo: `docs/modelo/compras.md` (`Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`,
`Cotizacion`, `DetalleCotizacion`). Patrón: `docs/patrones/enlace_del_proveedor.md`. Contrato de lectura de stock: `docs/api/stock.md`.

### CMP-RLZ-PED (CMP-02a)

- `compras/servicios/pedidos.py`: `insumos_bajo_el_minimo(actor)` (los `InsumoInvernadero` de los invernaderos activos a cargo, con
  `stock.existencias(...)`: `libre`, `transito`, `minimo`, `bajo_minimo`, y la cantidad sugerida `minimo − (libre + transito)`; una consulta por
  tabla), `ya_pedido(iin_ids)` (extensión 4c: en otro pedido «en cotización» o con orden «pendiente de aprobación»), `resumir_pedido(actor, datos)`
  (las mismas validaciones, sin escribir) y `registrar_pedido(actor, datos) -> Pedido`.
- **Registrar:** bloquear las cuentas (actor), los invernaderos de destino (`bloquear_invernadero_activo`, en orden de id), los
  `InsumoInvernadero` (verificar activos y habilitados, extensión 11a) y los proveedores invitados (verificar activos, 11a), en ese orden; crear
  pedido, detalles (precio de referencia copiado **ahora**), invitaciones y enlaces (`enlaces.crear_enlace`); auditar `alta_pedido` con los
  detalles y las invitaciones en `afectados` (o un registro por detalle, como hace INV-02: elegí el patrón que ya usa el repo para «una fila y sus
  hijas»); `on_commit`: los correos (`enlaces.enviar_invitacion`).
- **Fecha límite:** propone `hoy + dias_limite_cotizacion` (ya existe en `maestros.ConfiguracionOperativa`; se lee con
  `maestros.servicios.configuracion.obtener()` en cada uso) y rechaza una anterior a mañana (8a).
- **Extensión 1a** (desde la alerta de bajo el mínimo): la URL lleva el id del `InsumoInvernadero`; la alerta **no** se resuelve (postcondición f).
- **Extensión 3a.1a** (habilitar): `insumos_invernadero.habilitar_insumo(...)` de `inventario` (ya existe) y vuelve al pedido.

### CMP-ENV-COT (CMP-02a)

- Vistas públicas (D-88) y `compras/servicios/cotizaciones.py`: `resumir_cotizacion(enlace, lineas, validez, observaciones)` y
  `registrar_cotizacion(enlace_id, ...)` con el orden del patrón, sección 4. `lineas = [(detalle_pedido_id, cantidad, total | None, unitario | None,
  plazo)]`: exactamente uno de total o unitario (D-89 punto 2).
- **Validez:** propone fecha límite + `dias_validez_cotizacion` (ya existe en la configuración operativa); rechaza una anterior a la fecha
  límite (9a).
- **Pedido cubierto (11c):** `cobertura(pedido, cotizaciones) -> dict[detalle_id, Cobertura]` en `compras/servicios/cobertura.py` (la misma que
  usa CMP-03 con la tolerancia `porc_tolerancia_cobertura_pedido` (configuración operativa, ya existe)); se compara antes y después con el pedido bloqueado.
- **Auditoría** con `rol_externo=ROL_PROVEEDOR_ENLACE` (D-88 punto 5): `alta_cotizacion` con sus líneas.

### CMP-CNS-PED (CMP-02a; la acción «Reenviar invitación», CMP-02b)

- `consultar_pedidos(actor, filtros)` y `ficha_de_pedido(actor, pedido_id)`. Alcance: el Agrónomo, los suyos; el Gerente, todos en solo lectura;
  nadie más. La cotización de cada proveedor se muestra **solo después** del final del día de la fecha límite (H15.2): antes, solo «cotizó / no
  cotizó» y el estado del enlace.
- **Reenviar invitación (CMP-02b):** `reenviar_invitacion(actor, invitacion_id)`: solo el Agrónomo del pedido, pedido «en cotización», proveedor sin
  cotización y activo; `enlaces.reemplazar_enlace`, auditar `reenvio_invitacion`, correo en `on_commit`.

### CMP-CNL-PED (CMP-02b)

- `cancelar_pedido(actor, pedido_id, motivo)` para la manual y `cancelar_pedido_automaticamente(pedido, causa, *, actor=None)` para las
  automáticas; **las dos usan la misma función interna** `_cancelar(pedido, causa, motivo, actor)`: bloquea el pedido (`FOR NO KEY UPDATE`),
  verifica «en cotización», pasa a `cancelado` con `fecha_cierre_pedido = hoy`, descarta las propuestas, anula los enlaces vigentes, audita
  `cancelacion_pedido` (con `actor=None` y el rol `infoponia` si es automática) y registra en `on_commit` el correo a cada invitado (sin el
  motivo) y, en las automáticas, el aviso al Agrónomo del pedido o a los destinatarios de H21.
- **Disparadores automáticos (H17, MD-62):** el efecto de baja de cuenta de un Agrónomo (`core.registrar_efecto_de_baja_de_cuenta`) cancela sus
  pedidos en cotización (`agronomo_inactivo`); el traspaso del rol `agronomo` de un invernadero (`maestros.registrar_traspaso`: `contar` dice
  cuántos pedidos se cancelarían, `traspasar` los cancela) cancela los del saliente con algún detalle a ese invernadero
  (`agronomo_sin_invernadero`). Los pasos 60 y 62 usan la misma función (CMP-03).
- **Concurrencia:** la cancelación contra la generación de la orden (los dos bloquean el pedido; uno gana y el otro ve el estado nuevo, 6a y 11a)
  y contra un proveedor que envía su cotización (el envío bloquea el pedido después del proveedor y antes del enlace: espera y ve «cancelado»).

### Impedimentos (H20, CMP-02b)

`inventario.registrar_impedimento_de_deshabilitacion`: un pedido «en cotización» con ese `InsumoInvernadero` → código `pedido_en_curso`, texto
«Está en el pedido P-0031, en cotización hasta el 28/11» con su enlace (no se cancela solo).

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| CMP-RLZ-PED: cada regla, extensión y postcondición | `test_cmp_rlz_ped.py` |
| CMP-ENV-COT: cada regla, extensión y postcondición, con la vista pública | `test_cmp_env_cot.py` |
| CMP-CNS-PED (y «Reenviar invitación») | `test_cmp_cns_ped.py` |
| CMP-CNL-PED (manual y las tres automáticas) | `test_cmp_cnl_ped.py` |
| Enlaces (patrón, sección 5) | `test_enlaces.py` |
| Bajas y traspasos del Agrónomo; impedimento de deshabilitación | `test_registrantes_de_pedidos.py` |
| Concurrencia: dos pedidos que habilitan el mismo insumo; cancelar contra cotizar; dos proveedores que cubren a la vez (un aviso) | `test_pedidos_concurrencia.py` |

### Pantallas (prototipo)

`VIEWS.c_main` (2323) y `tabPed` (2327): «Compras › Pedidos». `VIEWS.c_pednew` (2450): nuevo pedido (con los insumos bajo el mínimo, el buscador
del catálogo y la lista de proveedores con el filtro propuesto). `VIEWS.c_ped` (2340): ficha del pedido (con «Reenviar invitación» y «Cancelar
pedido»). `VIEWS.c_pedcnl` (2477): cancelar. `VIEWS.c_cotz` (2689): **portal del proveedor** (en el sistema, sin el selector «enlace de ejemplo»).

## Solo prototipo

El selector «enlace de ejemplo» del portal del proveedor, el menú «ver como» y «Reiniciar datos de ejemplo».
