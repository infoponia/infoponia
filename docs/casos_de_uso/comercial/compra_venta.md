# Casos de uso · comercial · Compra-venta

Copia para el repo de COM-REG-CVT, versión 0.3 de «CU extendidos», y de COM-CNS-CVT, versión 0.1 del documento de Drive «CU · Consultas
comerciales · COM-CNS-CVT/SUM/SRV» (carpeta «InfoPonia · Comercial · Análisis») y, desde el lote C5b, de **COM-CNL-CVT · Cancelar
Compra-venta, versión 0.1** (documento «CU · COM-CNL-CVT · Cancelar Compra-venta (v0.1)», misma carpeta, 20/11/2026). Cotejado con pendientes_CU, con «PCU · Cambios para
pendientes_CU (comercial)» (secciones 1 a 16), con pendientes_MD hasta MD-113 más MD-114 a MD-139 del documento comercial, con el modelo de
dominio (reglas 5 a 12 y 19 a 27 de 8.6, 1 a 3 de 8.11, 18 de 8.20) y con el glosario.

**El código va en la app `comercial`** (D-37). Archivos de pruebas: `comercial/tests/test_com_reg_cvt.py` y `test_com_cns_cvt.py`.
COM-REG-CVT incluye PROD-ASG-STK: su extracto es `docs/casos_de_uso/produccion/stock_maduro.md` y su cálculo, `docs/patrones/stock_maduro.md`.
La cancelación de una compra-venta (COM-CNL-CVT) es de **COM-05b**: está al final de este archivo (archivo de pruebas
`comercial/tests/test_com_cnl_cvt.py`).

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-REG-CVT no numera sus reglas, así que se usa el nombre de la regla (`test_precio_unitario_…`,
`test_una_variedad_por_venta_…`), y para las postcondiciones, `test_post_<letra>_<que_espera>`, y para las extensiones, `test_ext_<numero>_…`
(`test_ext_14a_…`). COM-CNS-CVT sí numera: `test_regla_<numero>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-REG-CVT | Registrar Compra-venta | Vendedor o Gerente | `comercial/tests/test_com_reg_cvt.py` |
| COM-CNS-CVT | Consultar Compra-venta | Vendedor o Gerente | `comercial/tests/test_com_cns_cvt.py` |
| COM-CNL-CVT | Cancelar Compra-venta (COM-05b) | Vendedor o Gerente | `comercial/tests/test_com_cnl_cvt.py` |

## COM-REG-CVT · Registrar Compra-venta

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Comercial.  
 **Actor principal:** Vendedor. El Gerente también puede ejecutar este caso de uso; en ese caso elige al Vendedor responsable de la venta.  
 **Versión:** 0.3

**Personal involucrado e intereses**

  - **Vendedor:** quiere registrar la venta rápido, con el cliente presente, sabiendo en el momento cuánto stock hay de cada variedad para la fecha pactada, y con un precio sugerido para no tener que recordarlo.
  - **Cliente:** quiere tener la certeza de que el producto que compra está reservado para él, recibir un comprobante con lo que pidió y pagar recién cuando lo recibe.
  - **Agrónomo:** quiere enterarse de las cosechas que se generan automáticamente para cubrir la venta, para validarlas o modificarlas a tiempo.
  - **Capataz:** quiere recibir con anticipación las órdenes de cosecha que surgen de las ventas.
  - **Gerente:** quiere que ninguna venta comprometa stock que no existe o que ya está reservado, y que cada venta quede asociada a un Vendedor responsable, con trazabilidad de quién la cargó.
  - **Organización (Jardín Botánico):** quiere vender primero el producto que ya está en cámara, antes de que venza, y cumplir lo pactado con cada cliente.

**Relaciones con otros casos de uso**

  - **«include»** PROD-ASG-STK · Asignar Stock Maduro: se incluye en el paso 15, una vez por cada detalle de la venta.
  - **«include»** Alta Cliente: se incluye en la extensión 4a, cuando el cliente no está registrado o está dado de baja.
  - **«include»** Modificación Cliente: se incluye en la extensión 7a, cuando el envío va a una dirección distinta de las registradas del cliente.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Vendedor o Gerente.  
 b. Existe al menos un Vendedor activo con invernaderos asignados.  
 c. En al menos un invernadero activo existe stock maduro libre de al menos una variedad.

**Garantías mínimas**

  - La venta, sus detalles, sus reservas de stock y las órdenes de cosecha creadas por PROD-ASG-STK se registran juntas o no se registra ninguna. Si el caso de uso se cancela o falla, no queda ninguna de ellas ni su log de auditoría.
  - El alta de un cliente y el registro de una dirección nueva, hechos mediante los casos de uso incluidos, no se revierten aunque la venta se cancele o falle.
  - Ningún lote ni partida de cámara queda reservado por encima de su stock libre, aun cuando otro Vendedor, el Agrónomo o InfoPonia reserven stock al mismo tiempo.
  - Al registrar la venta no se genera ningún pago ni asiento contable.

**Garantías de éxito (Postcondiciones)**

a. Se creó una compra-venta en estado “abierta”, con fecha de realización igual a la fecha actual, la fecha pactada y la modalidad de entrega indicadas, asociada al cliente y al Vendedor responsable.  
 b. Si la modalidad es envío a domicilio, la compra-venta quedó asociada a la dirección de envío, que es una de las direcciones del cliente. Si la modalidad es retiro en invernadero, quedó asociada al invernadero de retiro, que es uno de los invernaderos del Vendedor responsable.  
 c. Se crearon uno o más detalles de venta en estado “abierto”, cada uno con su variedad, la cantidad solicitada y el precio unitario, sin cantidad entregada. La venta no repite variedades.  
 d. Por cada detalle se ejecutó PROD-ASG-STK, que creó una o más reservas de stock asociadas al detalle, una por cada invernadero de origen, con fecha de entrega igual a la fecha pactada. La suma de sus cantidades reservadas es igual a la cantidad solicitada del detalle.  
 e. Cada reserva con al menos una línea de lote quedó en estado “activa” y tiene una orden de cosecha en estado “a realizar”, con la fecha programada y la prioridad de la regla “Cosechas automáticas” y el Capataz del invernadero como responsable. Se notificó la orden al Capataz y al Agrónomo del invernadero, a este último para que la valide o la modifique.  
 f. Cada reserva con todas sus líneas de cámara quedó en estado “lista para entrega”.  
 g. Si todas las reservas de la venta quedaron “lista para entrega”, se disparó la planificación automática de la Entrega para la fecha pactada, a cargo de InfoPonia.  
 h. Se envió al cliente un correo con el comprobante de la compra-venta o, si el cliente no tiene correo, el Sistema presentó el comprobante para entregarlo impreso.  
 i. Se creó un log de auditoría con el usuario que cargó la venta, su rol, fecha, hora e identificador de la compra-venta creada.  
 j. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada detalle de venta, reserva de stock, línea de reserva y orden de cosecha creados.

**Escenario principal de éxito (o Flujo Básico)**

1.  **El Vendedor inicia el registro de una compra-venta.**
2.  **El Sistema solicita identificar al cliente.**
3.  **El Vendedor introduce el CUIT del cliente.**
4.  **El Sistema presenta los datos del cliente y sus direcciones registradas.**
5.  **El Vendedor indica la fecha pactada y la modalidad de entrega “envío a domicilio”.**
6.  **El Sistema verifica que la fecha pactada sea igual o posterior a la fecha actual y presenta las direcciones del cliente.**
7.  **El Vendedor selecciona la dirección de envío.**
8.  **El Sistema presenta las variedades que tienen stock maduro libre disponible para la fecha pactada en los invernaderos del Vendedor, con la cantidad disponible de cada una y el último precio unitario usado para ella.**
9.  **El Vendedor selecciona una variedad, indica la cantidad solicitada y confirma o modifica el precio unitario propuesto.**
10. **El Sistema verifica la cantidad, el precio y que la variedad no esté ya en la venta, agrega el detalle a la venta en curso y presenta su subtotal estimado y el monto estimado de la venta.** *El Vendedor repite los pasos 9-10 hasta incluir todas las variedades que pide el cliente.*
11. **El Vendedor indica que terminó de cargar los detalles.**
12. **El Sistema presenta el resumen de la compra-venta: cliente, Vendedor responsable, modalidad y dirección de envío, fecha pactada, detalles con cantidad, precio unitario y subtotal estimado, y monto estimado total.**
13. **El Vendedor confirma la venta.**
14. **El Sistema vuelve a verificar que haya stock maduro libre suficiente para cada detalle.**
15. **El Sistema registra la compra-venta en estado “abierta” con sus detalles en estado “abierto”, incluye PROD-ASG-STK · Asignar Stock Maduro para cada detalle y registra la auditoría correspondiente. PROD-ASG-STK crea las órdenes de cosecha necesarias y avisa de cada una al Capataz y al Agrónomo del invernadero. Si todas las reservas de la venta quedan “lista para entrega”, el Sistema dispara la planificación automática de la Entrega (COM-PNF-ENT) para la fecha pactada.**
16. **El Sistema envía al cliente el correo con el comprobante de la compra-venta.**
17. **El Sistema informa al Vendedor que la venta fue registrada y presenta su identificador.**

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 13, el actor cancela el registro:**

1.  El Sistema descarta los datos de la venta sin registrarla. El cliente dado de alta y la dirección agregada durante el caso de uso permanecen registrados.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1.  El Sistema revierte cualquier registro parcial de la venta, sus detalles, reservas y cosechas.
2.  Al restablecerse, el Sistema informa al actor que la venta no fue registrada. El cliente dado de alta y la dirección agregada permanecen registrados.
3.  El actor reinicia el caso de uso desde el paso 1.

**1a. El actor es el Gerente:**

1.  El Sistema presenta los Vendedores activos con sus invernaderos.
2.  El Gerente selecciona el Vendedor responsable de la venta.
3.  El caso de uso continúa en el paso 2. En adelante, los invernaderos habilitados son los del Vendedor seleccionado.

**3a. El Vendedor no conoce el CUIT del cliente:**

1.  El Vendedor busca al cliente por nombre, apellido o razón social.
2.  El Sistema presenta los clientes que coinciden.
3.  El Vendedor selecciona uno. El caso de uso continúa en el paso 4.

**3a.2a. Ningún cliente coincide con la búsqueda:**

1.  El Sistema informa que no hay clientes que coincidan.
2.  El Vendedor busca con otro criterio (vuelve a 3a.1), introduce un CUIT (vuelve al paso 3) o da de alta al cliente (continúa en 4a.2).

**4a. El cliente no está registrado o está dado de baja:**

1.  El Sistema informa que el cliente no está registrado, o que está dado de baja, y ofrece registrarlo o reactivarlo.
2.  Se incluye el caso de uso Alta Cliente, que registra al cliente o lo reactiva.
3.  El caso de uso continúa en el paso 4 con ese cliente.

**5a. La modalidad de entrega es retiro en invernadero:**

1.  El Sistema verifica la fecha pactada (igual que en el paso 6) y presenta los invernaderos activos del Vendedor, con la dirección de cada uno.
2.  El Vendedor selecciona el invernadero de retiro.
3.  El caso de uso continúa en el paso 8. Las variedades y cantidades disponibles se calculan solo sobre los lotes y partidas de ese invernadero.

**6a. La fecha pactada es anterior a la fecha actual:**

1.  El Sistema señala el error y rechaza la fecha.
2.  El Vendedor introduce una nueva fecha (vuelve al paso 5).

**7a. El cliente pide el envío a una dirección distinta de las registradas:**

1.  Se incluye el caso de uso Modificación Cliente, que agrega la nueva dirección al cliente.
2.  El Vendedor selecciona la nueva dirección y el caso de uso continúa en el paso 8.

**8a. No hay stock maduro libre de ninguna variedad para la fecha pactada en los invernaderos habilitados:**

1.  El Sistema informa que no hay stock disponible para esa fecha.
2.  El Vendedor cambia la fecha pactada o la modalidad de entrega (vuelve al paso 5), o cancela.

**9a. La variedad seleccionada nunca se vendió:**

1.  El Sistema no propone precio y el Vendedor introduce el precio unitario.

**10a. La cantidad solicitada es menor que uno o supera el stock maduro libre disponible de la variedad para la fecha pactada:**

1.  El Sistema informa la cantidad máxima disponible.
2.  Según lo que decida el cliente, el Vendedor ajusta la cantidad (vuelve al paso 9) o elige otra variedad (vuelve al paso 9).

**10b. La variedad ya está incluida en la venta:**

1.  El Sistema informa que la venta no puede repetir variedades y presenta el detalle existente.
2.  El Vendedor modifica el detalle existente (continúa en 9-10a) o elige otra variedad (vuelve al paso 9).

**10c. El precio unitario es cero o negativo:**

1.  El Sistema señala el error.
2.  El Vendedor corrige el precio (vuelve al paso 9).

**9-10a. El Vendedor modifica la cantidad o el precio de un detalle ya cargado:**

1.  El Vendedor selecciona el detalle e indica la nueva cantidad solicitada y el nuevo precio unitario.
2.  El Sistema verifica la cantidad y el precio igual que en el paso 10, actualiza el detalle y presenta su subtotal estimado y el monto estimado de la venta.
3.  El caso de uso continúa en el paso 9 o en el paso 11.

**9-10a.2a. La nueva cantidad es menor que uno o supera el stock maduro libre disponible de la variedad para la fecha pactada:**

1.  El Sistema informa la cantidad máxima disponible y deja el detalle sin cambios.
2.  El Vendedor corrige la cantidad (vuelve a 9-10a.1).

**9-10a.2b. El nuevo precio unitario es cero o negativo:**

1.  El Sistema señala el error y deja el detalle sin cambios.
2.  El Vendedor corrige el precio (vuelve a 9-10a.1).

**9-10b. El Vendedor quita un detalle ya cargado:**

1.  El Vendedor selecciona el detalle a quitar.
2.  El Sistema lo quita de la venta en curso y presenta el monto estimado actualizado.
3.  El caso de uso continúa en el paso 9 o en el paso 11.

**11a. El Vendedor indica que terminó sin haber cargado ningún detalle:**

1.  El Sistema informa que la venta debe incluir al menos una variedad.
2.  El Vendedor agrega un detalle (vuelve al paso 9) o cancela.

**13a. El Vendedor quiere corregir un dato del resumen:**

1.  El Vendedor indica el dato a corregir, y el caso de uso vuelve al paso donde se ingresó ese dato:
      
      - Vendedor responsable: 1a.2, solo si el actor es el Gerente;
      - cliente: paso 3 o 3a;
      - fecha pactada o modalidad de entrega: paso 5;
      - invernadero de retiro: 5a.2;
      - dirección de envío: paso 7;
      - detalles: paso 9 para agregar uno, 9-10a para modificarlo, 9-10b para quitarlo.
2.  El Vendedor vuelve a indicar que terminó de cargar los detalles (paso 11), y el Sistema presenta el resumen actualizado.

**13a.1a. Cambió el Vendedor responsable, la fecha pactada, la modalidad o el invernadero de retiro:**

1.  El Sistema vuelve a calcular el stock disponible de cada detalle e informa los que ya no pueden cubrirse.
2.  El Vendedor ajusta esos detalles (9-10a) o los quita (9-10b).
3.  Si cambió el Vendedor responsable y la modalidad es retiro, el Sistema descarta el invernadero de retiro, y el Vendedor elige uno de los invernaderos del nuevo Vendedor (5a.2).

**13a.1b. Cambió el cliente y la modalidad es envío a domicilio:**

1.  El Sistema descarta la dirección de envío, porque era del cliente anterior.
2.  El Sistema presenta las direcciones del nuevo cliente, y el Vendedor selecciona una (paso 7).

**14a. El stock maduro libre de algún detalle cambió mientras se cargaba la venta y ya no alcanza:**

1.  El Sistema no registra la venta e informa, para cada detalle afectado, la nueva cantidad máxima disponible.
2.  El Vendedor ajusta o quita los detalles afectados (9-10a o 9-10b), vuelve a indicar que terminó (paso 11) y confirma de nuevo, o cancela.

**16a. El Sistema no logra enviar el correo al cliente:**

1.  La venta permanece registrada.
2.  El Sistema reintenta el envío y avisa al Vendedor que el comprobante está pendiente de envío.

**16b. El cliente no tiene correo registrado:**

1.  El Sistema presenta el comprobante de la compra-venta para entregarlo impreso al cliente.
2.  El caso de uso continúa en el paso 17.

**Requisitos especiales**

  - Tras cada dato ingresado por el actor (pasos 3 a 10 y extensiones 9-10a y 9-10b), la pantalla se actualiza con las verificaciones, el stock disponible y los montos estimados en no más de 1 segundo.
  - El registro del paso 15 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un indicador de progreso.
  - El paso 15, incluida la ejecución de PROD-ASG-STK para cada detalle, se ejecuta como una única transacción. El alta de cliente y la dirección nueva quedan fuera de esa transacción.
  - El control de concurrencia sobre el stock libre de lotes y partidas impide la sobreasignación entre ventas, cosechas manuales y asignaciones automáticas simultáneas.
  - El Vendedor solo puede vender stock de sus invernaderos. El Gerente puede registrar ventas para cualquier Vendedor, y el log de auditoría registra al usuario que cargó la venta.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios y montos se expresan en pesos argentinos, con dos decimales.
  - El comprobante es interno y no tiene validez fiscal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio**

  - **Vendedor responsable:** el actor, si es un Vendedor; el seleccionado, si el actor es el Gerente. Toda venta pertenece a un único Vendedor. (Paso 1 y extensión 1a)
  - **Invernaderos habilitados:** en un envío, los invernaderos del Vendedor responsable. En un retiro, solo el invernadero de retiro, que debe ser uno de los del Vendedor. (Pasos 8 y 15, extensión 5a)
  - **Stock maduro libre disponible para la fecha pactada:** para cada variedad, la suma del stock libre de sus lotes activos en la etapa “Maduración” de los invernaderos habilitados, más el stock libre de sus partidas de cámara “disponibles” de esos invernaderos cuya fecha límite sea igual o posterior a la fecha pactada. Un lote cuenta solo si su fecha máxima de cosecha no es anterior a la fecha programada que tendría su cosecha (regla 11 de 8.6; regla 3 de 8.20). Se cuentan solo los lotes y las partidas que PROD-ASG-STK puede tomar (sus reglas “Lote elegible” y “Partida elegible”), así que tampoco cuentan los lotes de un invernadero sin Capataz activo. (Pasos 8, 10 y 14, y extensión 9-10a)
  - **Cantidad solicitada válida:** un número entero de al menos una planta y como máximo el stock maduro libre disponible de la variedad para la fecha pactada. (Pasos 10 y 14, y extensión 9-10a)
  - **Precio unitario:** mayor que cero, en pesos con dos decimales. El Sistema propone el último precio unitario usado para esa variedad en una compra-venta; si nunca se vendió, no propone ninguno. (Pasos 9 y 10, y extensión 9-10a)
  - **Una variedad por venta:** una compra-venta no puede tener dos detalles de la misma variedad. (Paso 10)
  - **Fecha pactada válida:** igual o posterior a la fecha actual, sin anticipación mínima ni fecha máxima. (Paso 6)
  - **Dirección de envío:** debe ser una de las direcciones del cliente. Solo existe si la modalidad es envío a domicilio. (Paso 7 y extensión 7a)
  - **Monto estimado:** suma de la cantidad solicitada por el precio unitario de cada detalle. Se muestra en el resumen y en el comprobante, pero no se guarda: el subtotal y el monto total son derivados y se calculan sobre la cantidad entregada. (Pasos 10, 12 y 16)
  - **Estado inicial:** la compra-venta queda “abierta” y sus detalles “abiertos”. (Paso 15)
  - **Cosechas automáticas:** las crea PROD-ASG-STK con su regla “Cosechas automáticas” (regla 3 de 8.11), usando el parámetro de anticipación de compra-venta (diasAnticipacionCosechaCompraVenta). La fecha programada es la mayor entre la fecha actual y la fecha pactada menos la anticipación efectiva, y la prioridad es media. Se notifican al Capataz y al Agrónomo del invernadero, que puede validarlas o modificarlas. (Paso 15)
  - **Reserva desde cámara:** una reserva cuyas líneas son todas de cámara queda “lista para entrega” al registrarse. Si todas las reservas de la venta quedan así, InfoPonia planifica la Entrega para la fecha pactada (regla 24 de 8.6). (Paso 15)

**Lista de tecnología y variaciones de datos**

  - **3a.** El cliente se identifica por CUIT, o se busca por nombre, apellido o razón social.
  - **5a.** La fecha pactada se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.
  - **9a.** La cantidad solicitada se expresa en plantas, como número entero.
  - **9b.** El precio unitario se expresa en pesos argentinos con dos decimales.
  - **16a.** El correo al cliente contiene el comprobante de la compra-venta: detalles, cantidades, precios unitarios, monto estimado, fecha pactada y modalidad (dirección de envío, o invernadero de retiro con su dirección). Aclara que es un comprobante interno sin validez fiscal y que el pago se realiza al recibir el producto.

**Frecuencia**

A confirmar con el Jardín Botánico. Se espera que ocurra varias veces por semana, cada vez que un minorista o un cliente particular realiza un pedido.

**Temas abiertos**

  - Falta definir el caso de uso con el que el Vendedor cancela una compra-venta (regla 22 de 8.6).

## COM-CNS-CVT · Consultar Compra-venta

Del documento de Drive «CU · Consultas comerciales · COM-CNS-CVT/SUM/SRV (v0.1)», del 20/11/2026: caso de uso de alto nivel. Reemplaza a
CU-36 de «Documentacion para la IA» (PCU, sección 10).

**Actores:** Vendedor o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver el estado y la historia completa de una compra-venta.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta, no modifica datos ni registra auditoría.

**Reglas:**

1.  Alcance: el Vendedor ve las compra-ventas de los contratos de los que es Vendedor; el Gerente, todas.
2.  Filtros: cliente, estado, rango de fechas (pactada o de realización) y, solo para el Gerente, Vendedor.
3.  Listado: cliente, fecha pactada, modalidad, monto (estimado si está abierta, final si está concretada) y estado.
4.  Ficha: el cliente, el Vendedor, la modalidad, la dirección de envío o el invernadero de retiro y las fechas de realización, pactada y de concreción; cada detalle con su variedad, cantidad solicitada y entregada, precio, subtotal y estado (abierto, pendiente de decisión, confirmado, rechazado o cancelado); las entregas, con invernadero de origen, fecha, estado y transportista; el cobro, si lo hay, con fecha, medio y monto; si está cancelada, el motivo, la descripción y la fecha (MD-130); si está pendiente de decisión del cliente, la fecha de vencimiento del enlace.
5.  Desde la ficha se puede ir a Cancelar Compra-venta (COM-CNL-CVT), si la venta es cancelable, y a la ficha del cliente (COM-CNS-CLT).

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57)

### COM-REG-CVT

- **Servicio** (`comercial/servicios/compra_ventas.py`). Un caso de uso = una función: `registrar_compra_venta(actor, datos) ->
  CompraVenta`, en `transaction.atomic()`. `datos` es un `dataclass` (`DatosDeCompraVenta`: vendedor, cliente, fecha pactada, modalidad,
  dirección o invernadero de retiro y la lista de `Renglon(variedad, cantidad, precio)`) que arma `desde_post`. Los errores de negocio son
  `ValidationError` con `code` y, si corresponde, el campo (como en COM-01). Lectura sin escribir: `datos_del_formulario(actor, datos)`
  (lo que muestra la pantalla en cada cambio: Vendedores, direcciones, invernaderos de retiro, variedades con disponible y precio propuesto,
  subtotales, monto estimado y errores por campo) y `resumen(actor, datos)` (paso 12).
- **La venta en curso no se guarda** (pasos 2 a 13): vive en el formulario. Cada cambio vuelve a pedir `datos_del_formulario`, que **no
  bloquea** y usa `stock_maduro.disponible` (una consulta por tabla, sin consultas por renglón: requisito «no más de 1 segundo», prueba con
  `assertNumQueries` igual con 1 y con 5 renglones).
- **Paso 1 y extensión 1a (Vendedor responsable, regla 1 de 8.11).** El Vendedor activo es el responsable y no lo elige. El Gerente elige
  uno de los Vendedores **activos con al menos un invernadero activo** (lista con sus invernaderos); si cambia de Vendedor con el
  formulario cargado, aplica 13a.1a.
- **Precondición b.** Si no hay ningún Vendedor activo con invernaderos activos (Gerente), o el Vendedor que actúa no tiene invernaderos
  activos, «Nueva compra-venta» se muestra deshabilitado con el motivo («No tenés invernaderos activos asignados: pedile al Gerente que te
  asigne uno.» / «No hay Vendedores con invernaderos activos.»). La precondición c no se verifica de antemano: depende de la fecha, y la
  cubre la extensión 8a.
- **Pasos 3 y 3a (cliente).** Un buscador (no un desplegable: los clientes crecen), por CUIT, nombre, apellido o razón social, desde dos
  caracteres, con `buscar_clientes` de COM-01 y solo clientes **activos**. 3a.2a: «No hay clientes que coincidan.» con el enlace al alta.
- **Extensión 4a y 7a (casos de uso incluidos, fuera de la transacción).** «Registrar o reactivar un cliente» abre COM-ALT-CLT y «Agregar una
  dirección al cliente» abre COM-MOD-CLT, los dos con `volver` (regla 7 de ALT y regla 5 de MOD; COM-01 dejó el parámetro). `volver` es la URL
  de «Nueva compra-venta» con los datos de las secciones 1 y 2 en la consulta (`vendedor`, `cliente`, `fecha`, `modalidad`, `invernadero`) más
  el cliente o la dirección recién creados, que quedan elegidos. **Las variedades ya cargadas no viajan**: si había alguna, el enlace avisa
  antes «Vas a tener que volver a cargar las variedades.» Lo creado en el caso de uso incluido queda aunque la venta no se registre
  (garantía mínima 2).
- **Pasos 5 a 7, 5a y 6a.** Fecha pactada `>= stock.hoy()`, sin máximo (regla «Fecha pactada válida»), error `fecha_pasada` en el campo. Envío:
  solo las direcciones **activas** del cliente (regla 23 de 8.6; D-58). Retiro: los invernaderos activos del Vendedor responsable con su
  dirección; si tiene uno solo, queda elegido (como el prototipo, `retiroFld`).
- **Paso 8 y extensión 8a.** Solo las variedades con stock maduro libre mayor que 0 para la fecha en los invernaderos habilitados (más las que
  ya están en un renglón, para poder corregirlas), con «Disponible: N plantas» en cada renglón. Sin ninguna: «No hay stock disponible para el
  dd/mm/aaaa en {tus invernaderos | el invernadero de retiro}. Probá con otra fecha o con otra modalidad.» y la sección 3 bloqueada.
- **Paso 9 y 9a (precio propuesto).** El `precio_unitario_de_venta` del `DetalleVenta` más reciente de esa variedad (por
  `fecha_realizacion` del contrato y después por `id`), **de cualquier compra-venta, Vendedor y estado**: el caso de uso dice «el último
  precio usado para ella en una compra-venta», sin más condiciones. (Confirmado por el estudiante el 21/11/2026.) Sin ventas previas, el campo queda vacío con la ayuda «Nunca se vendió:
  ingresá el precio.»
- **Paso 10 y extensiones 10a a 10c, 9-10a, 9-10b, 11a.** Cantidad: entero, `>= 1` y `<=` disponible (`cantidad_invalida`: «Ingresá un número
  entero de plantas.»; `supera_disponible`: «Hay N plantas disponibles para esa fecha.»). Precio: `> 0`, dos decimales, como máximo
  9.999.999.999,99 (el `DecimalField(12, 2)`), con coma decimal (`precio_invalido`). Variedad repetida: el desplegable no la ofrece y el
  servicio la rechaza igual (`variedad_repetida`, «La venta ya tiene esa variedad: corregí ese renglón.»). Sin renglones: «Cargá al menos
  una variedad.» Quitar un renglón no pide confirmación.
- **Pasos 12, 13 y 13a (resumen y confirmación).** «Revisar y registrar» abre una ventana con el resumen del paso 12 (cliente, Vendedor,
  modalidad con la dirección o el invernadero, fecha, renglones con subtotal estimado y monto estimado) y dos botones: «Confirmar
  compra-venta» (paso 13) y «Volver a la carga» (13a: vuelve al formulario con todo lo cargado). El prototipo registra sin resumen; manda el
  caso de uso. 13a.1a y 13a.1b los resuelve el recálculo de `datos_del_formulario`: al cambiar Vendedor, fecha, modalidad o invernadero,
  los renglones que ya no alcanzan quedan con su error, y al cambiar de cliente se borra la dirección elegida.
- **Pasos 14 y 15 (la transacción).** En este orden (`docs/patrones/stock_maduro.md`, sección 3):
  1. bloquea las cuentas del actor y del Vendedor responsable (en orden de id) y verifica rol y estado de las dos (`sin_permiso`,
     `vendedor_inactivo`);
  2. bloquea los invernaderos considerados (`bloquear_invernadero_activo`) y verifica que sigan siendo del Vendedor; en retiro, que el de retiro
     siga activo y del Vendedor (`invernadero_no_habilitado`);
  3. bloquea el cliente y verifica que siga activo (`cliente_inactivo`, «El cliente se dio de baja mientras cargabas la venta.») y, en envío,
     que la dirección siga activa y sea suya (`direccion_no_valida`);
  4. bloquea las variedades, los lotes y las partidas candidatos;
  5. crea la `CompraVenta` («abierta», `fecha_realizacion` = hoy, `numero` de `comercial_compraventa_numero_seq`) y sus `DetalleVenta`
     («abierto», sin cantidad entregada);
  6. por cada detalle, en orden de variedad, `stock_maduro.asignar(actor, detalle, cantidad, fecha_pactada, "compra_venta")`;
  7. si **algún** detalle quedó con cantidad sin cubrir, lanza `ValidationError` `stock_insuficiente` con la nueva cantidad máxima de cada
     detalle afectado: la transacción se revierte entera (extensión 14a; garantía mínima 1). La pantalla vuelve al formulario con esos
     renglones marcados y el mensaje «El stock cambió mientras cargabas la venta.»;
  8. audita (abajo) y devuelve la venta.
  No hay una verificación aparte antes de registrar (paso 14): con todo bloqueado, el resultado de `asignar` **es** la verificación.
- **Postcondición g (planificar la entrega si todo salió de cámara).** **Se completa en COM-05**, que crea `Entrega` y COM-PNF-ENT: en COM-02
  una venta con todas sus reservas «lista para entrega» queda «abierta» y sin entrega. Hasta COM-04 no hay partidas reales (solo de
  fábrica en las pruebas), así que el caso no se da con datos reales. COM-05 suma la llamada al final de `registrar_compra_venta` y su paso
  diario 50 planifica también las ventas que ya estaban así (disparador nuevo en «Cuando exista Entrega»).
- **Paso 16 y extensiones 16a y 16b (comprobante).** Después de confirmar la transacción, **fuera de ella** (D-14, D-54), la vista llama a
  `comprobantes.enviar_comprobante(contrato)` (una sola función para los dos tipos de contrato: COM-03 suma la plantilla del suministro):
  - con correo del cliente y el correo del sistema configurado, envía con `core.correo.enviar_correo` (USR-10) un texto plano con lo de la
    variación de datos 16a. `enviar_correo` espera una cuenta (`.pk` y `.email`): se le pasa `Destinatario(pk=cliente.pk,
    email=cliente.email_cliente)`, un `namedtuple` de `comercial`; el registro de la falla dirá «cuenta N» con el id del cliente (anotado en
    `docs/temas_abiertos.md`, «Correo a quien no tiene cuenta»);
  - el resultado queda en `Contrato.estado_comprobante` (`enviado`, `pendiente_envio` o `para_imprimir`; campo nuevo, «Pendientes de MD»
    del modelo);
  - **16a** (falla o correo del sistema sin configurar): `pendiente_envio`. El aviso final dice «No se pudo enviar el comprobante a {correo}.
    Podés reenviarlo desde la ficha.» y, si registró el Gerente, el Vendedor responsable recibe la notificación «El comprobante de CV-… quedó
    pendiente de envío.». **El reintento es manual**: «Reenviar comprobante» en la ficha (Vendedor responsable o Gerente), sin auditoría. No
    hay reintento automático porque no hay cola de envíos (`docs/temas_abiertos.md`, «Notificaciones»);
  - **16b** (cliente sin correo): `para_imprimir`, y el aviso final ofrece «Imprimir comprobante».
  - El comprobante imprimible (`compra-ventas/<id>/comprobante/`, una página con estilos de impresión, sin menú) existe para toda venta y se
    abre desde la ficha. Dice «Comprobante interno, sin validez fiscal. El pago se realiza al recibir el producto.»
- **Paso 17.** Redirige a la ficha de la venta con el aviso breve (D-29) «CV-0044 registrada. Se reservó el stock{ y se programaron N
  cosechas}.» más lo del comprobante.
- **Auditoría (postcondiciones i y j, D-36).** Un solo registro, acción nueva `registro_compra_venta`, con el actor y su rol (el Gerente queda
  como quien cargó; el Vendedor responsable va en `datos`). Afectados: la compra-venta (principal), sus detalles, y lo que devolvió
  `asignar` (reservas, líneas y cosechas), cada uno con sus valores en `datos`. Montos y fechas como texto.
- **Requisitos especiales.** La fecha es `stock.hoy()`. El botón de confirmar muestra «Registrando…» y se deshabilita al enviar (indicador de
  progreso, `hx-indicator`), siempre, no solo después de 10 segundos.
- **Concurrencia** (`@tag("concurrencia")`): dos ventas por el último stock de un lote (una registra, la otra recibe `stock_insuficiente`
  con el nuevo máximo 0); una venta contra la baja del cliente; una venta contra el cambio de Vendedor del invernadero (D-60).

### COM-CNS-CVT

- **Lectura** (`comercial/servicios/compra_ventas.py`): `buscar_compra_ventas(actor, filtros, pagina)` y `ficha_de_compra_venta(actor,
  id)`, sin escribir y sin consultas por fila.
- **Regla 1 (alcance).** `ContratoQuerySet.en_alcance_de(actor)` (un único lugar, D-28). Una ficha fuera del alcance da 403 con mensaje
  (SEG-13); un id que no existe, 404.
- **Regla 2 (filtros).** Cliente (buscador, como en el alta), estado, rango de fechas con «Fecha pactada» o «Fecha de realización» (por
  defecto, sin rango) y, solo el Gerente, Vendedor. Los filtros van en la URL (se pueden compartir y volver con el botón Atrás).
- **Regla 3 (listado).** Columnas: compra-venta (`CV-…` y la fecha de realización; el Gerente ve además el Vendedor), cliente, entrega
  (modalidad y fecha pactada, con «en N días» o «hace N días»), monto y estado. Orden: fecha de realización descendente, después número
  descendente. Páginas de 50.
- **Monto.** Por detalle: confirmado → entregada × precio; abierto o pendiente de decisión → solicitada × precio; rechazado o cancelado → 0.
  Etiqueta «final» si la venta está concretada o cancelada y «estimado» si no. Es la fórmula del prototipo y respeta «Monto estimado» de
  COM-REG-CVT; se calcula en la base (`Sum` con `Case`), no en Python fila por fila.
- **Regla 4 (ficha).** En COM-02: cliente (con CUIT y enlace a su ficha), Vendedor, modalidad con la dirección o el invernadero de retiro, las
  tres fechas, los detalles (variedad, solicitada, entregada o «—», precio, subtotal y estado) y el estado del comprobante. **Se completan
  después:** las entregas (COM-05; mientras no hay: «La entrega se planifica cuando todo el producto esté listo.»), el cobro (COM-06a y
  COM-08b, el de una venta cancelada con entregas concretadas), los datos de la cancelación (COM-05, MD-130) y la fecha de vencimiento del enlace de un faltante (COM-04).
- **Regla 5.** «Ver cliente» siempre. «Cancelar compra-venta» **se completa en COM-05b** (COM-CNL-CVT, al final): en COM-02 no se muestra (D-25:
  solo lo que existe).
- **Reservas en la ficha (decisión de aplicación).** El caso de uso no las pide y el prototipo no las muestra: no se muestran. Lo que el
  Vendedor necesita ver (de dónde sale y cuándo se cosecha) llega con COM-04 y COM-05.

### Cambio de Vendedor de un invernadero (D-60)

`comercial` registra `maestros.extensiones.registrar_traspaso(contar_contratos, traspasar_contratos)`; las dos funciones solo actúan con
`rol == "vendedor"` y devuelven o hacen nada con otro rol. Qué contratos pasan: D-60, punto 2. En COM-02, «vigentes o abiertos» son las
compra-ventas «abierta» o «pendiente_decision»; COM-03 suma los suministros vigentes a las mismas funciones. `traspasar` bloquea los
contratos después del invernadero, en orden de id, y los devuelve para que `modificar_invernadero` los ponga entre los afectados de su
registro (contrato de `maestros/extensiones.py`). Texto de `contar`: «Compra-ventas abiertas: N». Las reservas no cambian.

## Pantallas

Prototipo `docs/prototipos/comercial/`: `tabContratos` (con `cv`), `VIEWS.cv`, `INIT.cvnew`, `VIEWS.cvnew`, `ACT['cvnew-ok']`, `cliPick`,
`retiroFld`, `stockLibre` (solo para ver qué se muestra: el cálculo real es el del patrón). Referencia (L7, D-61): lo que difiere lo decide el
caso de uso.

- **Comercial › Contratos** pasa a ser la primera pestaña y `/comercial/` redirige a ella (COM-01 redirigía a Clientes). En COM-02 muestra
  solo compra-ventas: el selector «Compra-ventas / Suministros» del prototipo (`ctrSel`) lo agrega COM-03.
- URLs: `contratos/` (lista), `contratos/compra-ventas/nueva/`, `contratos/compra-ventas/nueva/calcular/` (fragmento, `POST` sin escribir),
  `contratos/compra-ventas/nueva/revisar/` (ventana del resumen), `contratos/compra-ventas/<id>/`, `contratos/compra-ventas/<id>/comprobante/`
  y `contratos/compra-ventas/<id>/reenviar-comprobante/` (`POST`).
- Formulario en tres secciones numeradas (Cliente, Entrega, Variedades) y el resumen a la derecha, como el prototipo. **Pasos bloqueados
  hasta completar el anterior** (criterio de interfaz del plan, sección 5): Entrega se habilita con el cliente elegido y Variedades con la
  fecha y la dirección o el invernadero.
- Textos explicativos:
  - bajo «Fecha pactada»: «El día en que el cliente recibe o retira el producto. Puede ser hoy.»;
  - en la sección Variedades: «Cada variedad va una sola vez, con un único precio. "Disponible" es lo que se puede reservar para esa fecha en
    {tus invernaderos | el invernadero de retiro}: producto en cámara y lotes en Maduración que llegan a tiempo.»;
  - en el resumen: «Al confirmar se reserva el stock y se programan las cosechas necesarias. El cliente paga al recibir.»;
  - con cliente sin correo: «El cliente no tiene correo: el comprobante se entrega impreso.»
- Sin JavaScript: cada cambio se envía con «Actualizar» (el formulario se vuelve a mostrar con los cálculos) y el resumen es una página.

### Lo que difiere del prototipo

| N.º | Prototipo | Se hace | Por qué |
|---|---|---|---|
| 1 | Registra sin resumen | Ventana de resumen y confirmación | Pasos 12, 13 y 13a |
| 2 | «Disponible» sin fecha ni invernaderos (`stockLibre`) | Para la fecha pactada y los invernaderos habilitados | Regla «Stock maduro libre disponible» |
| 3 | Ofrece todas las variedades | Solo las que tienen disponible (y las ya cargadas) | Paso 8 |
| 4 | No propone precio | Último precio de la variedad | Paso 9 |
| 5 | Sin filtro de fechas en la lista | Rango por fecha pactada o de realización | Regla 2 de COM-CNS-CVT |
| 6 | «Cancelar compra-venta» en la ficha | Lo agrega COM-05b | D-25 |
| 7 | Vendedor por nombre (`Sofía Ríos`) | Lista de Vendedores activos con invernaderos activos | Extensión 1a, precondición b |
| 8 | Sin estado del comprobante ni «Reenviar» | Estado y «Reenviar comprobante» | Extensión 16a |

## Para más adelante

- COM-03: el selector de tipo de contrato; los suministros en la lista y en el alcance; los suministros en el traspaso de D-60.
- COM-04: la fecha de vencimiento del enlace (estado «pendiente de decisión»); el enlace de la notificación de cada cosecha.
- COM-05a1 y COM-05a2: postcondición g (COM-PNF-ENT); las entregas en la ficha. COM-05b: «Cancelar compra-venta» y los datos de la
  cancelación (MD-130), al final de este archivo.
- COM-06a y COM-08b: el cobro en la ficha (el de la última entrega y el de una cancelación con entregas concretadas); la fecha de concreción.

## Solo prototipo

Los de `docs/prototipos/comercial/README.md`, «Elementos del prototipo que no van en el sistema». En estas pantallas, además: los datos de
ejemplo (`DB.cv`, `CV-0040` a `CV-0048`), el cálculo del identificador nuevo (`'CV-00'+…`) y el aviso «se envió el comprobante» sin
verificar el envío.

---

## COM-CNL-CVT · Cancelar Compra-venta

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Especifica el caso 5 de pendientes_CU.
Decisiones del 20/11/2026 aplicadas: cancela el Vendedor o el Gerente; desde «abierta» o «pendiente de decisión del cliente»; con entregas
concretadas se cancela lo pendiente y se cobra lo entregado en la misma operación (opciones C-b y L); no se cancela con entregas en curso;
motivo obligatorio (MD-130); comprobante al cliente.

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** Comercial / Contratos. **Versión:** 0.1

**Actor principal:** Vendedor del contrato. El Gerente también puede ejecutarlo.

**Personal involucrado e intereses**

- **Vendedor:** quiere registrar rápido que el cliente desistió o no retiró, y cobrar lo que ya entregó.
- **Gerente:** quiere que el stock reservado vuelva a estar disponible, que no quede ninguna deuda sin camino de cobro y que cada cancelación
  tenga un motivo.
- **Agrónomo y Capataz:** quieren que no se coseche ni se envase para una venta que ya no existe.
- **Cliente:** quiere la confirmación de la cancelación y pagar solo lo que recibió.
- **Organización:** quiere que lo cosechado no se pierda y entre a la cámara.

**Relaciones con otros casos de uso**

- **Incluye («include»):** PROD-CNL-ORD · Cancelar Orden, para las órdenes de cosecha pendientes y las entregas «a realizar» de la venta, con
  sus reservas de envases.
- **Lo preceden:** COM-REG-CVT · Registrar Compra-venta; COM-DCD-FLT · Decidir Faltante, si la venta está pendiente de decisión; COM-CNC-ENT,
  si ya se concretó una entrega.
- **Relacionados:** COM-PNF-ENT, cuya recuperación diaria ya no planifica nada de una venta cancelada.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Vendedor o Gerente.

b. Existe al menos una compra-venta «abierta» o «pendiente de decisión del cliente»; si el actor es Vendedor, de un contrato del que es
Vendedor.

**Garantías mínimas**

- La cancelación es atómica. Si falla o se cancela, la venta, sus reservas, sus cosechas, sus entregas y la cámara quedan como estaban.
- Ninguna entrega en curso se cancela.
- Ninguna venta queda con una deuda del cliente sin cobrar ni sin camino de cobro.
- Solo se registra un asiento cuando hay un cobro (por lo ya entregado).

**Garantías de éxito (Postcondiciones)**

a. Cada detalle de la venta que no estaba confirmado ni rechazado pasó a «cancelado» (MD-130).

b. Las reservas de esos detalles quedaron «liberadas»: las líneas de lote no cosechadas devolvieron su stock libre al lote y las de cámara, a
la partida.

c. Lo ya cosechado de esas reservas que no se entregó ingresó a la cámara con el motivo «cancelación del cliente», con su movimiento de
ingreso a cámara y la fecha límite calculada desde la fecha de cosecha (regla 29 de 8.6).

d. Las órdenes de cosecha pendientes de esas reservas y las entregas «a realizar» de la venta quedaron canceladas (PROD-CNL-ORD), con sus
reservas de envases canceladas y sus alertas resueltas.

e. Si la venta estaba pendiente de decisión del cliente, el enlace de decisión de faltante quedó sin efecto.

f. La venta quedó con su motivo, su descripción opcional y su fecha de cancelación (MD-130), y en estado «cancelada» si no tenía entregas
concretadas, o «concretada» si las tenía. En ese caso se registró además el cobro de lo entregado (PagoCliente) con su asiento Debe Caja o
Banco c/c / Haber Deudores por Ventas (extensión 6a).

g. Se le envió al cliente por correo el comprobante de cancelación, que incluye el cobro si lo hubo, o se imprimió si no tiene correo (regla
18 de 8.20).

h. Si el actor fue el Gerente, se notificó la cancelación al Vendedor del contrato.

i. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la venta, el motivo, los detalles cancelados, las reservas
liberadas, los ingresos a cámara, las órdenes y entregas canceladas y el cobro, si lo hubo.

**Escenario principal de éxito** (la venta no tiene entregas concretadas ni en curso)

1. El Vendedor inicia la cancelación de una compra-venta.
2. El Sistema presenta las compra-ventas «abiertas» y «pendientes de decisión del cliente» de sus contratos, con el cliente, la fecha pactada,
   la modalidad, el monto estimado y el estado.
3. El Vendedor selecciona una venta.
4. El Sistema presenta qué va a pasar: cada detalle con su estado y su variedad; las reservas que se liberan, separando lo que vuelve a los
   lotes, lo que vuelve a las partidas de cámara y lo ya cosechado que ingresa a la cámara; las órdenes de cosecha y las entregas que se
   cancelan; y la lista de motivos.
5. El Vendedor elige el motivo («el cliente desistió», «el cliente no retiró» u «otro») y, si quiere, escribe una descripción.
6. El Sistema presenta el resumen de la cancelación.
7. El Vendedor confirma.
8. El Sistema vuelve a verificar que la venta siga «abierta» o «pendiente de decisión del cliente» y que ninguna de sus entregas esté en
   curso. Luego, en una única transacción, cancela los detalles, libera las reservas, ingresa lo cosechado a la cámara, cancela las órdenes y
   las entregas mediante PROD-CNL-ORD, registra el motivo y la fecha y registra la auditoría.
9. El Sistema envía al cliente el comprobante de cancelación.
10. El Sistema informa al Vendedor que la venta quedó cancelada.

**Extensiones**

- **\*a. En cualquier momento antes del paso 7, el actor cancela:** 1. El Sistema descarta la operación y la venta queda como estaba.
- **\*b. En cualquier momento el Sistema falla:** 1. El Sistema revierte cualquier registro parcial y, al restablecerse, informa que la
  cancelación no se registró.
- **1a. El actor es el Gerente:** 1. En el paso 2, el Sistema presenta las ventas de todos los contratos. 2. En el paso 9, el Sistema
  notifica además al Vendedor del contrato.
- **4a. Alguna entrega de la venta está en curso (con envío, con la fecha igual o anterior a la actual y con el vehículo de su transportista
  en ruta):** 1. El Sistema informa que no se puede cancelar mientras el producto está en viaje, y explica que el cliente puede rechazar al
  recibir (regla 27 de 8.6) o el transportista registrar el intento fallido, y que después se puede cancelar. 2. El actor elige otra venta
  (vuelve al paso 3) o termina.
- **6a. La venta tiene entregas concretadas (envío desde varios invernaderos):** 1. En el paso 4, el Sistema presenta también los detalles
  ya entregados, que no se cancelan, y el monto a cobrar: la suma de las ventas registradas en esas entregas. 2. El Sistema pide el cobro y el
  Vendedor indica el medio de pago con el que paga el cliente. 3. En el paso 8, el Sistema registra además el cobro y su asiento, y la venta
  pasa a «concretada».
- **6b. La venta tiene una entrega de retiro en invernadero «a realizar»:** 1. La entrega se cancela igual que una con envío, sin
  transportista que avisar.
- **8a. Al registrar, la venta cambió de estado, o una entrega se concretó o pasó a estar en curso en otra operación:** 1. El Sistema no
  registra ningún cambio, informa la situación actual y vuelve al paso 4 con los datos actualizados.
- **8b. Al registrar, una orden de cosecha se concretó en otra operación:** 1. El Sistema no registra ningún cambio y vuelve al paso 4, donde
  lo cosechado figura ahora como ingreso a la cámara.
- **9a. El Sistema no logra enviar el correo:** 1. La cancelación permanece registrada, el Sistema reintenta el envío y ofrece imprimir el
  comprobante.

**Requisitos especiales**

- La interfaz está pensada para computadora.
- El paso 8 se ejecuta como una única transacción, que incluye PROD-CNL-ORD.
- La cancelación se serializa con la concreción de cosechas, la planificación y concreción de entregas y el inicio de ruta de la misma venta.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**

- **Quién cancela:** el Vendedor del contrato o el Gerente. Las ventas de un Vendedor inactivo las cancela el Gerente. (Paso 1 y extensión 1a)
- **Venta cancelable:** «abierta» o «pendiente de decisión del cliente», sin entregas en curso. (Paso 2 y extensión 4a)
- **Detalles afectados:** se cancelan los «abiertos» y los «pendientes de decisión del cliente». Los confirmados (ya entregados) y los
  rechazados no cambian. (Postcondición a)
- **Reservas y cámara:** según la regla 22 de 8.6. Lo cosechado no entregado ingresa a la cámara con el motivo «cancelación del cliente» y
  conserva su vida útil (regla 29 de 8.6). (Postcondiciones b y c)
- **Envases:** solo están reservados hasta concretar la entrega (PROD-PNF-ENV). Al cancelarse la entrega se cancelan sus reservas; aunque el
  producto ya esté envasado, los envases nunca se descontaron. (Postcondición d)
- **Cobro de lo entregado:** si la venta tiene entregas concretadas, la deuda registrada en ellas (regla 32 de 8.6) se cobra en esta misma
  operación, por el total y en un único pago (regla 5 de 8.7). El cliente paga en ese momento, porque la compra-venta es al contado. La venta
  queda «concretada», porque ya no le quedan detalles pendientes (regla 21 de 8.6). (Extensión 6a)
- **Asientos:** sin entregas concretadas, ninguno (regla 22 de 8.6); con entregas concretadas, solo el del cobro. (Postcondición f)
- **Motivo:** obligatorio, de una lista cerrada, con descripción opcional; la fecha de cancelación es la actual. (Paso 5)
- **Venta que el cliente nunca retira:** la cancela el Vendedor con el motivo «el cliente no retiró»; no hay cancelación automática (regla 3
  de 8.7).

**Frecuencia:** ocasional.

**Temas abiertos:** ninguno. El tema de los envases de pendientes_CU (caso 5) queda cerrado por la regla «Envases».

## Cambios ya decididos que se aplican a COM-CNL-CVT

1. **MD-130:** los datos de la cancelación (`motivo_cancelacion_venta`, `descripcion_cancelacion`, `fecha_cancelacion_venta`) y el estado
   «cancelado» del detalle (`docs/modelo/comercial.md`, «CompraVenta» y «DetalleVenta»).
2. **PCU, sección 7:** la cancelación de una entrega resuelve su alerta «entrega sin transportista» (la hace `cancelar_entrega_incluida`, de
   COM-05a1).
3. **D-65 (disparador «Cuando exista Entrega», punto 7, tercer guion):** la postcondición e es `anular_enlaces_de(venta)`.

## Cómo se aplica en la ronda «Comercial 1»: COM-CNL-CVT (COM-05b; D-44, D-57, D-59, D-64, D-65, D-66, D-67)

### Qué entra y qué no

| Parte | En COM-05b |
|---|---|
| Escenario, extensiones \*a, \*b, 1a, 4a, 6b, 8a, 8b, 9a; postcondiciones a a e, f (sin entregas concretadas), g, h, i | **Sí** |
| Extensión 6a y el cobro de la postcondición f (PagoCliente) | **No en COM-05b.** Antes de COM-06 ninguna entrega se concreta, así que 6a no puede darse. COM-06 suma el rechazo `venta_con_entregas_concretadas` y **COM-08b** (D-94, punto 14), el cobro y el paso a «concretada» (disparador «Cuando exista Entrega», punto 9): ver «La extensión 6a (COM-08b)», al final |
| El asiento del cobro (postcondición f, garantía mínima 4, regla «Asientos») | **Fuera de esta ronda · contabilidad** (D-57) |
| 9a «reintenta el envío» | No hay cola (D-14, D-54): el comprobante guarda su estado y la ficha ofrece «Reenviar comprobante» e «Imprimir», como el de COM-REG-CVT (16a y 16b) |

### Una contradicción y cómo se aplica (D-67, punto 4, a validar)

La regla «Detalles afectados» dice que los **confirmados** no se cancelan porque están «ya entregados». En el sistema, un detalle también queda
«confirmado» **antes** de entregarse: cuando el cliente acepta un faltante (postcondición g de COM-DCD-FLT, COM-04c). Si ese detalle no se
cancelara, su reserva quedaría «lista para entrega» sin entrega (la venta cancelada no se vuelve a planificar) y su producto, bloqueado para
siempre. Por eso, en el código, **se cancela todo detalle cuyo producto no se entregó**: «abierto», «pendiente de decisión» o «confirmado»
**sin línea en una entrega concretada**. Los confirmados entregados (desde COM-06) y los rechazados no cambian. Es lo que la regla quiere
decir («ya entregados») y va a pendientes_CU para la próxima versión del caso de uso.

### Servicios (`comercial/servicios/compra_ventas.py`)

- **Lectura, sin escribir:** `datos_de_cancelacion(actor, compra_venta_id) -> DatosDeCancelacion`: los detalles con su efecto («Se cancela»
  / «Ya entregado: no cambia» / «Rechazado: no cambia»); las reservas que se liberan, en tres grupos: lo que **vuelve a los lotes** (líneas de
  lote sin cosechar), lo que **vuelve a las partidas** (líneas de cámara) y lo ya **cosechado que ingresa a la cámara** (con la cantidad y la
  fecha límite que va a tener); las cosechas «a realizar» y las entregas «a realizar» que se cancelan (con su transportista y si tienen
  envases); las entregas en curso (4a) y las concretadas (6a); el destino del comprobante (correo o impreso); y la `huella`.
- `resumen_de_cancelacion_de_venta(actor, compra_venta_id, datos)`: lo de arriba con el motivo elegido y el estado final («Cancelada»).
- **Escritura:** `cancelar_compra_venta(actor, compra_venta_id, datos, huella) -> CompraVenta`, en `transaction.atomic()`. `datos` es
  `DatosDeCancelacionDeVenta(motivo, descripcion)`. Errores con `ValidationError` y `code`.
- **Huella** (`huella_de_venta(venta)`): el estado de la venta, de cada detalle, de cada reserva, de cada cosecha y de cada entrega, y la
  cantidad cosechada de cada línea, al abrir el resumen.

### Reglas en el código

- **Quién** (paso 1, 1a): `rol_requerido("gerente", "vendedor")`; `Contrato.objects.en_alcance_de(actor)` (D-28). Un Vendedor inactivo no
  entra: sus ventas las cancela el Gerente. Fuera del alcance, 403 con mensaje.
- **Paso 2:** no hay una lista aparte: es la lista de contratos de COM-02 con el filtro de estado («Abierta» o «Pendiente de decisión del
  cliente») y, en la ficha, el botón «Cancelar compra-venta» (regla 5 de COM-CNS-CVT, que se completa acá: lo ven el Vendedor del contrato y el
  Gerente, con la venta «abierta» o «pendiente de decisión del cliente»).
- **Venta cancelable** (precondición b): `venta_no_cancelable` si está «concretada» o «cancelada».
- **4a (en curso):** si alguna entrega «a realizar» de la venta está `en_curso(entrega, hoy)`: la pantalla muestra el aviso «No se puede
  cancelar mientras el producto está en viaje: {OT-0231} salió hoy con {transportista}. Si el cliente no lo quiere, puede rechazarlo al
  recibir, o el transportista registra el intento fallido. Después vas a poder cancelar.» y no deja seguir; el servicio rechaza
  `entrega_en_curso`.
- **6a (entregas concretadas):** no puede darse en COM-05b (ver «Qué entra y qué no»). Si una prueba de fábrica la arma, el servicio
  rechaza `venta_con_entregas_concretadas` («Esta venta ya tiene entregas concretadas: su cancelación con cobro llega con la cobranza.»).
- **Paso 5 (motivo):** `motivo_cancelacion_venta` obligatorio (`motivo_obligatorio`), de la lista cerrada `cliente_desistio` («El cliente
  desistió»), `cliente_no_retiro` («El cliente no retiró»), `otro` («Otro»); `descripcion_cancelacion` opcional, hasta 300 caracteres, sin
  espacios al borde (`descripcion_larga`). Con «Otro» sigue siendo opcional (lo dice el caso de uso; la sugerencia de pedirla, como en la
  rescisión, va a pendientes_CU).
- **Pasos 6 y 7:** ventana de resumen («Revisar y cancelar» → resumen → «Confirmar cancelación»), como COM-REG-CVT; sin JavaScript, una página.
  La advertencia: «La cancelación no se puede deshacer.»
- **Paso 8, la transacción** (`docs/patrones/bloqueos.md`, «comercial», «Cancelar una compra-venta»):
  1. las **cuentas**: el actor, el Vendedor, los Capataces y Agrónomos de las cosechas que se cancelan y los transportistas de las entregas que
     se cancelan (en una consulta y en orden de id); el actor, activo y con su rol;
  2. los **invernaderos** de las reservas y de las entregas, en orden de id, con `bloquear_invernadero_para_alertas` (activo o no: el
     producto existe aunque el invernadero se haya dado de baja; es la misma excepción que COM-DCD-FLT, D-64 punto 12). Así también se pone en
     fila con las planificaciones y el inicio de ruta del mismo invernadero (D-66, punto 11);
  3. el **cliente** (sin verificar que siga activo: un cliente dado de baja también puede cancelar, regla 2 de 8.18);
  4. las **variedades**, los **sectores** y los **lotes** de las reservas, y sus **partidas**;
  5. la **venta** y sus **detalles**; las **cosechas** «a realizar» de esas reservas; las **reservas** y sus líneas; las **entregas** de la
     venta (después de las reservas, como dice «Cancelar una entrega»); y al final el **enlace** de la venta (`bloquear_enlace`, D-65).
  Después, la relectura: la venta sigue «abierta» o «pendiente» (8a: `venta_cambio`); ninguna entrega se concretó ni está en curso (8a); ninguna
  cosecha se concretó (8b); la huella coincide (si no, `venta_cambio`, y la pantalla vuelve al paso 4 con los datos nuevos).
  Con todo verificado, en este orden:
  1. por cada cosecha «a realizar» de las reservas de los detalles afectados: `cancelar_cosecha_incluida(actor, cosecha, motivo,
     recubrir=False, avisar=True)` (COM-04a; aviso al Capataz y al Agrónomo);
  2. por cada línea de lote **ya cosechada** con cubierto > 0 de esas reservas: una partida `cancelacion_cliente` con `camara.crear_partida`:
     cantidad = `min(cosechada, reservada)`, `fecha_cosecha` = la de su cosecha (la fecha límite sale de ahí: regla 29 de 8.6), `fecha_ingreso`
     = hoy, costo = `costo_unitario_de_cosecha` (D-64 punto 3) y origen del movimiento = **la compra-venta** (c); es el mismo cálculo que el
     rechazo de COM-DCD-FLT;
  3. las reservas no liberadas de los detalles afectados, a «liberada» (b): las líneas de lote sin cosechar dejan de reservar (el stock libre
     del lote vuelve solo, porque es un derivado) y las de cámara, igual con la partida;
  4. por cada entrega «a realizar» de la venta (también la de retiro, 6b): `cancelar_entrega_incluida(actor, entrega, motivo)` (COM-05a1): la
     orden y sus reservas de envases canceladas, la alerta «entrega sin transportista» resuelta, el aviso al Transportista y, si tenía envases,
     al Agrónomo (d);
  5. `anular_enlaces_de(venta)` si estaba «pendiente de decisión del cliente» (e);
  6. los detalles afectados, a «cancelado» (a); la venta, a «cancelada», con `motivo_cancelacion_venta`, `descripcion_cancelacion` y
     `fecha_cancelacion_venta = hoy` (f);
  7. el aviso al Vendedor si actuó el Gerente (h) y el registro de auditoría (i);
  8. `on_commit`: PROD-ASG-CAM con las partidas creadas y las de las líneas de cámara liberadas (para que ese producto vaya a quien lo espera:
     COM-04b), y el comprobante al cliente (g).
  El motivo que reciben las órdenes canceladas (de 1 a 300, `cancelar_orden_incluida` lo recorta): «Se canceló la compra-venta CV-0044: el
  cliente desistió.» (con la descripción, si entra).
- **Comprobante (paso 9, g, 9a):** `enviar_comprobante(venta, tipo="cancelacion")` después de confirmar, fuera de la transacción, con
  `estado_comprobante` y «Reenviar comprobante», como COM-REG-CVT. Contenido: la venta, el cliente, el Vendedor, la fecha de cancelación, el
  motivo (y la descripción), los detalles cancelados con su variedad y cantidad y los que no cambian. Sin cobro en COM-05b (6a, COM-08b). Pie:
  «Comprobante interno, sin validez fiscal.» **Sin correo** (regla 18 de 8.20): no se intenta; el aviso final dice «El cliente no tiene
  correo: imprimí el comprobante.» con el botón «Imprimir comprobante» (la página imprimible del comprobante, como en COM-02).
- **Avisos** (D-42: dentro de la transacción, sin enlace):

  | Cuándo | A quién | Título | Detalle |
  |---|---|---|---|
  | h | Vendedor (si actuó el Gerente y está activo) | «CV-0044 cancelada» | «El Gerente canceló la venta de Pérez SA. Motivo: el cliente desistió.» |
  | d (cosechas) | Capataz y Agrónomo | Los de `cancelar_cosecha_incluida` (COM-04a), con el motivo de arriba | |
  | d (entregas) | Transportista y, con envases, Agrónomo | Los de `cancelar_entrega_incluida` (COM-05a1), con el motivo de arriba | |

  El aviso al cliente de la entrega cancelada (que `cancelar_entrega_incluida` deja al caso de uso base) es el comprobante: no sale otro correo.
- **Auditoría (i; D-36):** un registro, acción nueva `cancelacion_compra_venta`, con el actor y su rol; afectados: la venta (principal), los
  detalles cancelados, las reservas liberadas, las partidas creadas con su movimiento, las cosechas y las entregas canceladas con sus reservas
  de envases, las alertas resueltas y el enlace anulado. `cambios`: los estados (antes → después) y los datos de la cancelación (como texto).
- **Venta que nunca se retira:** no hay cancelación automática (regla del caso de uso): ningún paso diario cancela ventas.
- **Después de cancelar:** la recuperación del paso 50 no planifica nada (la venta no está «abierta»: «Venta lista» de COM-PNF-ENT) y la
  ficha muestra los datos de la cancelación (regla 4 de COM-CNS-CVT, que se completa acá: «Cancelada el dd/mm. Motivo: …»).

### Pantallas

| Pantalla | Funciones del prototipo | Qué hace en COM-05b |
|---|---|---|
| Ficha de la compra-venta: «Cancelar compra-venta» | `VIEWS.cv` (el botón, línea 975) | El botón para el Vendedor del contrato y el Gerente, con la venta «abierta» o «pendiente»; los datos de la cancelación en una venta cancelada |
| Cancelar compra-venta | `INIT.cvcancel`, `VIEWS.cvcancel`, `ACT['cvcancel-ok']` | URL `contratos/compra-ventas/<id>/cancelar/` (con `revisar/`). Secciones «Qué se cancela» (cada detalle con su efecto), «Qué pasa con el producto» (los tres grupos de reservas, las cosechas y las entregas) y «Motivo»; el resumen a la derecha. Texto explicativo arriba: «Cancelar libera todo lo reservado para esta venta: lo ya cosechado entra a la cámara y queda disponible para otros contratos. Las cosechas y las entregas pendientes se cancelan y se avisa a quienes las tenían.» |

### Lo que difiere del prototipo (corregir, D-61)

- `ACT['cvcancel-ok']` registra directo: falta el resumen (pasos 6 y 7) y la relectura (8a, 8b).
- `VIEWS.cvcancel` toma `curso=false`: falta 4a (no deja seguir con una entrega en curso).
- `VIEWS.cvcancel` cancela solo los detalles «abierto» y «pendiente»: también los «confirmados» sin entregar (D-67, punto 4).
- La sección 3 «Cobro de lo entregado» y «Asientos: Solo el del cobro» del resumen: no en COM-05b (6a llega con COM-06 y COM-08b; los
  asientos, fuera de la ronda, D-57).
- «Se imprimirá el comprobante»: el sistema ofrece el botón «Imprimir comprobante» (no imprime solo).
- El motivo es un desplegable: con tres opciones, van como botones de opción (criterio de interfaz: menos clics, todo a la vista).

### Pruebas

- `comercial/tests/test_com_cnl_cvt.py`, `ComCnlCvtServicioTests` (para nombrar: `test_regla_<nombre>_…`, `test_post_<letra>_…`,
  `test_ext_<numero>_…`): una por regla (quién cancela, con el Vendedor inactivo; venta cancelable; detalles afectados, **con el confirmado sin
  entregar** —D-67 punto 4—; reservas y cámara; envases; motivo; sin cancelación automática), por postcondición (a, b, c, d, e, f sin
  concretadas, g, h, i) y por extensión (1a, 4a, 6b, 8a con cada causa, 8b, 9a); 6a rechazada con `venta_con_entregas_concretadas`; la venta
  «pendiente» con el enlace anulado; la partida `cancelacion_cliente` con la fecha límite de la cosecha y el costo de la cosecha; el
  `on_commit` de PROD-ASG-CAM y del comprobante (`captureOnCommitCallbacks`); el cliente sin correo (no se intenta); el cliente dado de baja;
  el invernadero dado de baja con una partida de la venta; que la recuperación del paso 50 ya no planifica nada de la venta; una venta de dos
  invernaderos (dos entregas canceladas, dos invernaderos bloqueados); `verificar_invariantes_de_reservas` y `verificar_invariantes_de_entregas`
  después de cada una.
- `comercial/tests/test_prod_cnl_ord_entregas.py` (métodos nuevos): la cancelación de una entrega desde COM-CNL-CVT, con y sin envases, con y
  sin transportista, de retiro.
- Concurrencia (`test_com_cnl_cvt_concurrencia.py`, `@tag("concurrencia")`): cancelar contra concretar una cosecha de la venta (8b); cancelar
  contra la planificación de su entrega (la del `on_commit` y la del paso 50: la que llega segunda no encuentra nada que hacer); cancelar
  contra la decisión del cliente por el enlace (la segunda ve el enlace anulado o la venta cancelada); cancelar contra PROD-ASG-CAM sobre una
  partida de la venta; cancelar contra asignar un transportista a su entrega.
- `comercial/tests/test_com_cnl_cvt.py`, `ComCnlCvtVistaTests`: permisos (el Vendedor de otro contrato y los demás roles no ven el botón ni
  entran; ningún botón lleva a un 403); el flujo con HTMX y sin él; `revisar/` no escribe nada; el aviso de 4a.

### La extensión 6a (COM-08b; D-94, punto 14)

Lo que COM-08b le suma a COM-CNL-CVT. Lo demás de esta sección no cambia.

- **Deja de rechazar** `venta_con_entregas_concretadas`: la prueba de COM-05b que lo esperaba se reemplaza (anotala en el PR).
- **Lectura** (`datos_de_cancelacion`, paso 4 y 6a.1): con entregas concretadas, los detalles ya entregados («Ya entregado: no cambia», como
  hasta ahora) y el **monto a cobrar de lo entregado**: Σ `monto_pagar` de las líneas de venta de las entregas **concretadas** de la venta (lo
  que registró cada entrega, regla 32 de 8.6), con el detalle por entrega (código, fecha, monto). El estado final que muestra el resumen pasa a
  «Concretada (se cobra lo entregado)».
- **Datos:** `DatosDeCancelacionDeVenta` suma `medio_pago` (obligatorio solo con entregas concretadas: `medio_de_pago_obligatorio`; sin ellas,
  `medio_no_admitido`), de la lista de `PagoCliente.medio_pago` (6a.2).
- **Huella:** suma la lista de entregas concretadas y su monto (8a: una entrega que se concretó mientras tanto cambia el monto a cobrar).
- **En la transacción** (el mismo orden de bloqueos; las entregas concretadas ya se bloquean con las demás de la venta), después del paso 6
  de «Reglas en el código» y antes de los avisos:
  1. el `PagoCliente`: `tipo_pago = compra_venta`, `compra_venta = venta`, `cliente` (el de la venta), `medio_pago`, `fecha_pago = hoy`,
     `monto_pagado` (el de arriba), `estado_pago = vigente`, `usuario = actor`; sin `numero` (no es un cobro de suministro) ni `LineaPago`;
  2. la venta a `concretada` (no a `cancelada`) con `fecha_concrecion_venta = hoy` y los datos de la cancelación (MD-130; la restricción ya
     admite motivo con `concretada`).
- **Comprobante** (g): la sección «Cobro de lo entregado» (cada entrega con su monto, el total cobrado y el medio). Sigue sin asiento (D-57).
- **Aviso al Vendedor** (h, si actuó el Gerente): suma «Se cobró lo entregado: $ 12.000,00 en efectivo.».
- **Auditoría** (i): el pago, en los afectados.
- **Pantalla** (`VIEWS.cvcancel`): la sección 3 «Cobro de lo entregado» del prototipo, con el medio de pago (botones de opción) y el texto
  «La venta ya tiene entregas concretadas: lo entregado se cobra ahora, en un solo pago. El resto se cancela.». El asiento, «Fuera de esta
  ronda · contabilidad».
- **Pruebas** (métodos nuevos en `test_com_cnl_cvt.py`): 6a con una venta de dos invernaderos y una entrega concretada (el pago, el monto, la
  venta concretada con los datos de la cancelación, el comprobante con el cobro); el medio obligatorio y no admitido; 8a con una entrega que
  se concreta en medio (concurrencia, en `test_com_cnl_cvt_concurrencia.py`); el invariante de COM-06a «una venta concretada tiene
  exactamente un pago vigente».
