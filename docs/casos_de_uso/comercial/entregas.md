# Casos de uso · comercial · Entregas

Copia para el repo de **COM-PNF-ENT · Planificar Entrega, versión 0.3** (documento de Drive «CU · COM-PNF-ENT · Planificar Entrega (v0.3)»,
carpeta «InfoPonia · Comercial · Análisis», 20/11/2026) y, desde el lote C5b, de **COM-ASG-TRP · Asignar Transportista a Entrega, versión
0.1** (documento «CU · COM-ASG-TRP · Asignar Transportista a Entrega (v0.1)», misma carpeta, 20/11/2026, con el cambio de «CU · Transportista
en el invernadero (v0.1)», sección «COM-ASG-TRP»). Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU (comercial)»
(secciones 2, 7, 8 y 12 lo cambian), con «CU · Transportista en el invernadero (v0.1)», con el modelo de dominio (reglas 3, 4, 18 y 25 de
8.8; 1 a 17 de 8.12; ronda 22) y con «MD · Cambios para el modelo de dominio (comercial)» (MD-69, MD-118, MD-119, MD-122, MD-138 y MD-139).

**El código va en la app `comercial`** (`comercial/servicios/entregas.py`; modelo en `docs/modelo/comercial.md`, «Entrega» y
«DetalleEntrega»). Cómo se guarda y cómo corre: **D-66** (y D-67 para COM-ASG-TRP). Tareas: **COM-05a1** y **COM-05a2** (lote C5a, partida
en el C5b: D-67 punto 2; donde abajo dice «COM-05a», leé la tabla de la sección 1 del plan) y **COM-05b** (COM-ASG-TRP, que reutiliza los
candidatos y el peso de acá). Crece con COM-06 (rutas y concreción). Archivos de pruebas: `comercial/tests/test_com_pnf_ent.py`
(`ComPnfEntServicioTests` y `ComPnfEntDiariaTests`), `test_entregas_concurrencia.py` y `test_entregas_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-PNF-ENT no numera sus reglas (`test_seleccion_…`, `test_agrupamiento_…`), sus postcondiciones son
`test_post_<letra>_…` y sus extensiones `test_ext_<numero>_…` (`test_ext_6a_…`, `test_ext_1b_4_…`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-PNF-ENT | Planificar Entrega (con la ejecución diaria, paso 50) | InfoPonia | `comercial/tests/test_com_pnf_ent.py` |
| (consulta) | Lista de entregas de Comercial (paso 2 de COM-ASG-TRP, sin la asignación) | Vendedor, Gerente | `comercial/tests/test_entregas_vistas.py` |
| COM-ASG-TRP | Asignar Transportista a Entrega (COM-05b) | Vendedor o Gerente | `comercial/tests/test_com_asg_trp.py` |

## COM-PNF-ENT · Planificar Entrega

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial / Órdenes.

**Versión:** 0.3

**Actor principal:** InfoPonia (proceso automático). Planifica la entrega sin intervención de una persona.

**Disparadores**

1.  **Venta lista para entrega:** quedan en “lista para entrega” todas las reservas no liberadas de una compra-venta “abierta” que no tiene detalles “pendiente de decisión del cliente”. Puede ocurrir al registrarse la venta (si todo sale de la cámara), al concretarse una cosecha, al asignarse stock de cámara o cuando el cliente acepta la cantidad disponible de un detalle.
2.  **Período de suministro listo para entrega:** quedan en “lista para entrega” todas las reservas de un período de un detalle de suministro vigente. Puede ocurrir al pactarse el suministro, al concretarse una cosecha o al asignarse stock de cámara.
3.  **Ejecución diaria:** una vez por día, a una hora fija. Planifica las compra-ventas y los períodos de suministro listos para entrega que todavía no tienen entrega (recuperación diaria), y busca transportista para cada entrega con envío en estado 'a realizar' y sin transportista, cualquiera sea su fecha programada.

**Personal involucrado e intereses**

  - **Cliente:** quiere saber con anticipación cuándo y dónde recibe o retira su pedido, y recibirlo en la fecha prometida.
  - **Vendedor:** quiere que las entregas de sus contratos se planifiquen solas, sin olvidos, y enterarse enseguida si alguna sale con retraso o queda sin transportista. En un retiro, es quien entrega el producto.
  - **Transportista:** quiere recibir entregas que pueda cumplir con su vehículo en un solo viaje, dentro de los límites diarios de entregas y de localidades, y no recibir entregas nuevas una vez que inició su ruta.
  - **Agrónomo:** quiere enterarse de cada entrega planificada para planificar a tiempo su envasado.
  - **Gerente:** quiere que se respeten los límites de la configuración operativa, que protegen las condiciones de trabajo de los transportistas, y que se le avise cuando la flota de un invernadero no alcanza.
  - **Organización (Jardín Botánico):** quiere cumplir las fechas prometidas para evitar quejas e indemnizaciones, y entregar el producto cosechado antes de que pierda su aptitud comercial.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - Se dispara a partir de lo que registran COM-REG-CVT · Registrar Compra-venta, COM-PCT-SUM · Pactar Suministro, PROD-CNC-CSC · Concretar Cosecha, PROD-ASG-STK · Asignar Stock Maduro y la asignación automática de cámara, cuando dejan listas para entrega todas las reservas de una venta o de un período.
  - Una entrega con envío que queda sin transportista también puede completarse con COM-ASG-TRP · Asignar Transportista a Entrega, que además permite reemplazar al transportista asignado.

**Precondiciones**

a. La configuración operativa tiene definidas la cantidad máxima de entregas diarias y la cantidad máxima de localidades distintas diarias.

b. Las reservas a entregar están en estado “lista para entrega”, y ninguna tiene un detalle de entrega en una entrega no cancelada.

c. En una compra-venta, la venta está “abierta” y ninguno de sus detalles está “pendiente de decisión del cliente”. En un suministro, el contrato y el detalle están “vigentes”.

**Garantías mínimas**

  - Cada entrega se registra junto con sus detalles de entrega, su transportista (si lo tiene) y su log de auditoría, o no se registra nada.
  - Si la planificación falla, el disparador queda pendiente e InfoPonia la vuelve a intentar: ninguna venta ni período listo queda sin entrega planificada por una falla.
  - Ninguna reserva queda incluida en dos entregas no canceladas.
  - Ningún transportista queda con entregas que superen la capacidad de carga de su vehículo ni los límites diarios de la configuración operativa, aun cuando se planifiquen varias entregas al mismo tiempo.
  - Ningún transportista recibe una entrega nueva, ni líneas nuevas en una entrega suya, para el día en que ya inició su ruta.
  - La planificación no modifica el estado de las reservas, el stock, el contrato ni la contabilidad.

**Garantías de éxito (Postcondiciones)**

a. Se creó una entrega en estado “a realizar” por cada invernadero de origen de las reservas, con fecha de creación igual a la fecha actual y la fecha programada que corresponde. No tiene Agrónomo planificador, porque la planificó InfoPonia. Si es una entrega de suministro, su confirmación del cliente quedó en “no confirmado”.

b. Cada entrega quedó con un detalle de entrega por cada detalle de contrato que incluye. Cada detalle de entrega satisface su propio detalle (de venta o de suministro), está asociado a las reservas que entrega y tiene su precio unitario, calculado con la fecha programada. La cantidad entregada y el monto a pagar de cada línea, y el monto total de la entrega, quedan vacíos hasta que se concrete la entrega.

c. Si la entrega es con envío y hubo transportistas candidatos, quedó asignado el seleccionado y se le notificó la entrega.

d. Si la entrega es con envío y no hubo ningún transportista candidato, quedó sin transportista. Se generó una alerta para el Gerente y se notificó al Vendedor del contrato.

e. Si la entrega es un retiro en invernadero, quedó sin transportista y se notificó al Vendedor del contrato, que es quien la concreta.

f. Si las líneas de un período de suministro cumplían las condiciones de agrupamiento con una entrega existente, se agregaron a esa entrega en lugar de crear otra, y se notificó el cambio a su transportista, si lo tiene.

g. Si la fecha prometida ya había pasado, la fecha programada es la fecha actual y se notificó el retraso al Vendedor del contrato. En un suministro, la notificación advierte que puede haber una queja o una indemnización.

h. Se notificó al Agrónomo del invernadero de origen que debe planificar el envasado de la entrega.

i. Se envió al cliente un correo con la fecha de entrega, el destino (en un retiro, el invernadero y su dirección) y las variedades y cantidades a entregar.

j. En la ejecución diaria, si se encontró un transportista para una entrega que no lo tenía:

  - quedó asignado;
  - si la fecha programada había pasado, pasó a la fecha actual, se notificó el retraso al Vendedor (con la advertencia de posible queja o indemnización en un suministro) y se envió al cliente un correo con la nueva fecha;
  - se notificó al transportista y al Vendedor;
  - la alerta enviada al Gerente quedó resuelta.

k. En la ejecución diaria, si no se encontró transportista y la fecha programada es el día siguiente, se envió un único recordatorio al Gerente y al Vendedor de que la entrega sigue sin transportista. En cualquier otro caso, la entrega quedó sin cambios.

l. En la ejecución diaria, cada compra-venta o período de suministro listo para entrega que todavía no tenía entrega quedó planificado según las postcondiciones a a i.

m. Se creó un log de auditoría con fecha, hora e identificador de cada entrega y de cada detalle de entrega creados, de cada asignación de transportista, de cada cambio en una entrega existente (líneas agregadas o fecha programada) y de cada alerta generada o resuelta. El log indica que el origen de la operación es un proceso automático.

**Escenario principal de éxito (o Flujo Básico)**

1.  **InfoPonia detecta que todas las reservas no liberadas de una compra-venta “abierta” con envío a domicilio, sin detalles pendientes de decisión del cliente, están listas para entrega.**
2.  **InfoPonia agrupa las reservas de la venta por invernadero de origen.**
3.  **InfoPonia establece la fecha programada de la entrega, igual a la fecha pactada de la venta.**
4.  **InfoPonia arma los detalles de la entrega: uno por cada detalle de venta con reservas en ese invernadero, con su cantidad planificada y el precio unitario del detalle de venta. Calcula el peso total de la entrega.**
5.  **InfoPonia busca los transportistas candidatos: los del invernadero de origen que están activos y tienen un vehículo activo.**
6.  **InfoPonia verifica, para cada candidato y para la fecha programada, que al sumar la nueva entrega no supere la capacidad de carga de su vehículo, la cantidad máxima de entregas diarias ni la cantidad máxima de localidades distintas diarias.**
7.  **InfoPonia selecciona, entre los candidatos que cumplen, el que menos entregas tiene asignadas en esa fecha.**
8.  **InfoPonia registra la entrega en estado “a realizar”, con su fecha programada, el transportista seleccionado y sus detalles de entrega asociados a los detalles de venta y a sus reservas, y registra la auditoría correspondiente.**
9.  **InfoPonia notifica la entrega al transportista.**
10. **InfoPonia notifica al Agrónomo del invernadero de origen que debe planificar el envasado de la entrega.**
11. **InfoPonia envía al cliente el correo con la fecha de entrega, el destino y las variedades y cantidades.** \*InfoPonia repite los pasos 3-11 por cada invernadero de origen de la venta.\*

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento InfoPonia falla:**

1.  InfoPonia revierte los registros parciales de la entrega en curso. Las entregas ya registradas para otros invernaderos de origen se conservan.
2.  El disparador queda pendiente. Al restablecerse, InfoPonia retoma la planificación desde el paso 2 con las reservas que todavía no tienen entrega.

**1a. El disparador es un período de suministro listo para entrega:**

1.  InfoPonia detecta que todas las reservas de un período de un detalle de suministro vigente están listas para entrega, y continúa en el paso 2 con esas reservas, con estas diferencias:
    1.  En el paso 3, la fecha programada es la fecha de entrega del período.
    2.  En el paso 4, el destino es la dirección del detalle de suministro y el precio unitario es el del período, calculado con la fecha programada.
    3.  Antes del paso 5, InfoPonia verifica si puede agrupar las líneas en una entrega existente (extensión 4a).

**1b. El disparador es la ejecución diaria:**

1.  InfoPonia busca las compra-ventas y los períodos de suministro listos para entrega que tienen alguna reserva “lista para entrega” sin detalle de entrega en una entrega no cancelada, y planifica cada uno desde el paso 2, como si su disparador inmediato hubiera ocurrido (con las extensiones 1a, 2a y 3a cuando correspondan).
2.  Para cada entrega con envío, “a realizar” y sin transportista, InfoPonia toma como fecha de búsqueda la fecha programada o, si ya pasó, la fecha actual.
3.  InfoPonia repite los pasos 5 a 7 para esa fecha, con los datos de la entrega.
4.  Si encuentra un transportista:
    1.  Lo asigna a la entrega.
    2.  Si la fecha programada ya había pasado, la pasa a la fecha actual, notifica el retraso al Vendedor del contrato (en un suministro, con la advertencia de posible queja o indemnización) y envía al cliente un correo con la nueva fecha.
    3.  Registra la auditoría, notifica la asignación al transportista y al Vendedor del contrato, y da por resuelta la alerta enviada al Gerente.
5.  Si no encuentra un transportista y la fecha programada es el día siguiente, envía al Gerente y al Vendedor del contrato un único recordatorio de que la entrega sigue sin transportista.
6.  Si no encuentra un transportista en cualquier otro caso, la entrega queda sin cambios y no se envía ningún aviso.

**2a. La compra-venta es con retiro en invernadero:**

1.  Todas las reservas son del invernadero de retiro, así que se planifica una sola entrega, con origen y destino en ese invernadero.
2.  InfoPonia continúa en el paso 3 y omite los pasos 5 a 7. En el paso 8, la entrega se registra sin transportista.
3.  En el paso 9, InfoPonia notifica al Vendedor del contrato que el retiro quedó planificado.
4.  En el paso 11, el correo al cliente indica el invernadero de retiro y su dirección.

**3a. La fecha prometida ya pasó:**

1.  InfoPonia establece como fecha programada la fecha actual.
2.  InfoPonia notifica al Vendedor del contrato que la entrega sale con retraso respecto de la fecha prometida. En un suministro, la notificación advierte que el retraso puede originar una queja o una indemnización según la cláusula del suministrante.

**4a. En un período de suministro, existe una entrega que cumple todas las condiciones de agrupamiento:**

1.  InfoPonia agrega los nuevos detalles de entrega a esa entrega, cada uno asociado a su propio detalle de suministro y a sus reservas.
2.  InfoPonia registra la auditoría y notifica el cambio al transportista de la entrega, si lo tiene.
3.  El caso de uso continúa en el paso 10.

Si ninguna entrega cumple todas las condiciones, InfoPonia continúa en el paso 5 y arma una entrega nueva.

**6a. El invernadero de origen no tiene transportistas candidatos, o ninguno cumple las verificaciones:**

1.  InfoPonia registra la entrega sin transportista (paso 8).
2.  InfoPonia genera una alerta para el Gerente que indica la entrega y el motivo: sin transportistas activos con vehículo activo, todos en ruta, capacidad de carga insuficiente, cantidad máxima de entregas diarias o cantidad máxima de localidades distintas diarias.
3.  InfoPonia notifica al Vendedor del contrato que la entrega quedó sin transportista.
4.  El caso de uso continúa en el paso 10. La entrega queda para la ejecución diaria o para COM-ASG-TRP · Asignar Transportista a Entrega.

**7a. Varios candidatos tienen la misma cantidad de entregas asignadas en esa fecha:**

1.  InfoPonia selecciona el que tiene mayor capacidad libre en su vehículo en esa fecha.
2.  Si siguen empatados, selecciona el de menor identificador.

**8a. Al registrar, el transportista seleccionado ya no cumple las verificaciones, porque otra planificación simultánea le asignó entregas o porque inició su ruta:**

1.  InfoPonia descarta a ese transportista y vuelve al paso 6 con los demás candidatos.

**8b. Al registrar, alguna reserva ya no está “lista para entrega” o ya tiene un detalle de entrega en otra entrega no cancelada (por ejemplo, porque se canceló la venta):**

1.  InfoPonia no registra esa entrega y el caso de uso termina para ese invernadero de origen.

**9-11a. InfoPonia no logra entregar una notificación, una alerta o el correo al cliente:**

1.  La entrega permanece registrada.
2.  InfoPonia reintenta el envío.

**Requisitos especiales**

  - La planificación se ejecuta en segundo plano, inmediatamente después de la transacción que deja listas las reservas, sin demorar la operación del usuario que la disparó.
  - La entrega queda registrada y notificada en no más de 30 segundos desde el disparador.
  - El registro de cada entrega se ejecuta como una única transacción.
  - Las planificaciones que involucran a un mismo transportista en una misma fecha se ejecutan de a una, para que dos planificaciones simultáneas no superen sus límites.
  - La ejecución diaria se realiza una vez por día, a una hora fija.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los pesos se expresan en kilogramos con dos decimales; los precios, en pesos argentinos con dos decimales.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un proceso automático.
  - Las notificaciones y alertas se presentan dentro del Sistema y pueden, además, enviarse por correo electrónico.

**Reglas de negocio**

  - **Venta lista para entrega:** todas las reservas no liberadas de sus detalles no rechazados están “lista para entrega”, y ningún detalle está “pendiente de decisión del cliente”. (Paso 1)
  - **Período listo para entrega:** todas las reservas de un detalle de suministro cuya fecha de entrega es la del período están “lista para entrega”. (Extensión 1a)
  - **Alcance de una entrega:** tiene un único invernadero de origen, un cliente, un contrato, un destino y una fecha programada. No mezcla una compra-venta con un suministro (C7). Una venta con retiro se entrega en una sola entrega; una venta con envío, en una por cada invernadero de origen. (Pasos 2 a 4)
  - **Invernadero de origen:** el de las reservas que entrega la entrega (regla 3 de 8.8). (Paso 2)
  - **Destino:** la dirección de envío de la venta, si es con envío; la dirección del detalle de suministro, en un suministro; el invernadero de retiro, en un retiro. (Paso 4 y extensiones 1a y 2a)
  - **Fecha programada:** la fecha prometida (la fecha pactada de la venta o la fecha de entrega del período). Si ya pasó, la fecha actual. No hay entregas anticipadas. (Paso 3 y extensiones 1b y 3a)
  - **Cantidad planificada de una línea:** suma de la cantidad cubierta de las reservas que entrega. No se guarda: se calcula a partir de las reservas. (Paso 4)
  - **Datos económicos de una línea:** (Paso 4)
      - Al planificar se guarda el precio unitario: en una compra-venta, el del detalle de venta; en un suministro, el del período según la regla 7 de 8.11, calculado con la fecha programada.
      - Al concretar la entrega se recalcula el precio unitario de suministro con la fecha real, y recién entonces se calculan el monto a pagar de cada línea (cantidad entregada × precio unitario) y el monto total de la entrega, porque dependen de la cantidad entregada.
  - **Peso de una entrega:** suma, por cada línea, de la cantidad planificada por el peso promedio por planta de su variedad, en gramos, dividida por 1.000 para expresarla en kilogramos con dos decimales, como la capacidad de carga del vehículo (regla 6 de 8.12; MD-69). Es la misma fórmula de la regla «Peso de la ruta» de COM-INI-RUT. (Paso 4)
  - **Transportista candidato:** transportista del invernadero de origen, en estado activo, con un vehículo activo. Si la fecha es la actual, no son candidatos los transportistas cuyo vehículo ya está en ruta. La misma exclusión vale en el agrupamiento (extensión 4a), en la ejecución diaria (extensión 1b) y en COM-ASG-TRP. (Paso 5)
  - **Capacidad de carga:** la suma del peso de todas las entregas no canceladas del transportista en la fecha, incluida la nueva, no puede superar la capacidad de carga de su vehículo. Se supone un solo viaje por día. (Paso 6)
  - **Límite de entregas diarias:** la cantidad de entregas no canceladas del transportista en la fecha, incluida la nueva, no puede superar la cantidad máxima de entregas diarias. (Paso 6)
  - **Límite de localidades:** la cantidad de localidades distintas de destino de esas entregas, incluida la nueva, no puede superar la cantidad máxima de localidades distintas diarias. (Paso 6)
  - **Capacidad libre del vehículo:** capacidad de carga menos la suma del peso de las entregas no canceladas del transportista en la fecha. (Extensión 7a)
  - **Selección del transportista:** entre los candidatos que cumplen, el que menos entregas tiene asignadas en la fecha. Si empatan, el de mayor capacidad libre del vehículo. Si siguen empatados, el de menor identificador. Así la elección es siempre la misma ante los mismos datos. (Paso 7 y extensión 7a)
  - **Agrupamiento en un suministro:** las líneas de un período se agregan a una entrega existente solo si se cumplen todas estas condiciones; si alguna falla, se arma una entrega nueva. (Extensión 4a)
      - es del mismo contrato, invernadero de origen, destino y fecha programada;
      - la entrega está “a realizar”;
      - la entrega todavía no tiene envasado planificado, es decir, no tiene reservas de insumo;
      - si tiene transportista, con el peso nuevo no se supera la capacidad de carga de su vehículo;
      - si tiene transportista, no está en ruta.
  - **Entrega sin transportista:** una entrega con envío sin transportista no se puede concretar. InfoPonia vuelve a buscar un transportista una vez por día, aunque la fecha programada haya pasado: en ese caso busca candidatos para el día actual y, al asignar uno, pasa la fecha programada al día actual. Los retiros no entran en la búsqueda diaria de transportista, pero sí en la recuperación diaria. (Extensiones 1b y 6a)
  - **Recuperación diaria:** la ejecución diaria planifica además lo que quedó listo para entrega sin entrega, por ejemplo porque un disparador inmediato no se ejecutó. Así, nada listo espera más de un día. Una reserva nunca se planifica dos veces (extensión 8b). (Extensión 1b)
  - **Avisos de una entrega sin transportista:** se envían solo estos tres. (Extensiones 1b y 6a)
      - la alerta al Gerente y la notificación al Vendedor cuando la entrega queda sin transportista;
      - un único recordatorio al Gerente y al Vendedor el día anterior a la fecha programada, si todavía no hay transportista;
      - la notificación al transportista y al Vendedor cuando se consigue uno.
  - **Estado inicial:** la entrega nace “a realizar”. En una entrega de suministro, la confirmación del cliente nace “no confirmado”; en una de compra-venta no aplica, porque no tiene enlace de confirmación (regla 26 de 8.6). (Paso 8)
  - **Aviso de envasado:** toda entrega planificada se notifica al Agrónomo del invernadero de origen para que planifique su envasado (regla 18 de 8.8). (Paso 10)

**Lista de tecnología y variaciones de datos**

  - **4a.** El peso promedio por planta de cada variedad se expresa en gramos, como número entero. El peso de la entrega se expresa en kilogramos, con dos decimales.
  - **6a.** La localidad de destino es la localidad de la dirección de destino.
  - **11a.** El correo al cliente indica la fecha de entrega, el destino (en un retiro, el invernadero y su dirección) y las variedades y cantidades a entregar.

**Frecuencia**

Cada vez que quedan listas todas las reservas de una venta o de un período de suministro, más una ejecución diaria para las entregas sin transportista y para lo listo que todavía no tiene entrega. Depende de la cantidad de ventas y de contratos de suministro vigentes.

**Temas abiertos**

  - ¿A qué hora se realiza la ejecución diaria?
  - Una entrega que nunca consigue transportista se sigue buscando cada día, sin límite. ¿Hace falta un tope, o alcanza con la alerta y el recordatorio al Gerente?

## Cambios ya decididos que se aplican

1. **PCU, sección 8 (decisión E):** la ejecución diaria envía además **un aviso único** al Vendedor del contrato y al Gerente por cada entrega
   con envío, «a realizar», con transportista y con la fecha programada vencida (por ejemplo, porque la ruta no se finalizó), para que la
   reasignen con COM-ASG-TRP. Es una postcondición nueva: acá se llama **n**.
2. **PCU, sección 12 (T-04):** el disparador «Ejecución diaria» es el **paso 50** del proceso diario único (D-56): corre después de vencer
   partidas (20), reasignar cámara (25), avisar enlaces vencidos (27), vencer pagos (30), cerrar rescisiones (35) y pre-reservar (40).
3. **PCU, sección 7:** la cancelación de una entrega resuelve su alerta «entrega sin transportista» (va en la «Cancelación de una entrega»,
   `docs/casos_de_uso/produccion/cancelar_orden.md`).
4. **MD-118:** «en ruta» = `en_ruta` y `fecha_inicio_ruta` = hoy (`Vehiculo.esta_en_ruta(hoy)`). Una ruta no finalizada deja de estar
   vigente al terminar el día.
5. **MD-138 y «Transportista en el invernadero» v0.1:** los candidatos son los transportistas **del invernadero de origen**
   (`maestros.TransportistaInvernadero`, D-55). Un transportista sin invernadero no es candidato de ninguna entrega.
6. **MD-139:** una entrega con la fecha programada pasada se muestra «atrasada», no «vencida».
7. **MD-69:** el peso promedio por planta está en gramos (ya en la versión 0.3).

## Cómo se aplica en la ronda «Comercial 1» (COM-05a; D-44, D-57, D-59, D-66)

### Qué entra y qué no

| Parte | En COM-05a |
|---|---|
| Disparadores 1 y 2 (inmediatos) y el paso 50 (disparador 3, con la postcondición n de PCU 8) | **Sí** |
| Escenario, extensiones 1a, 1b, 2a, 3a, 4a, 6a, 7a, 8a, 8b, \*a | **Sí** |
| 9-11a («no logra entregar») | Las notificaciones y la alerta se crean **dentro** de la transacción (D-42): no fallan por separado. El correo al cliente sí: sale después de confirmar y, si falla, lo reintenta el paso 50 (D-66, punto 12) |
| «Las notificaciones pueden, además, enviarse por correo» | No: solo dentro del Sistema (D-42) |
| COM-ASG-TRP (la relación «una entrega sin transportista también puede completarse con…») | **COM-05b.** En COM-05a la alerta lleva a la lista de entregas |

### Cuándo corre: los disparadores inmediatos (D-66, punto 5)

Cada caso de uso que deja listas las reservas llama, **dentro de su transacción y al final**, a una de estas dos funciones, que registran un
`transaction.on_commit` y no hacen nada más:

- `programar_planificacion_de_venta(compra_venta_id)`;
- `programar_planificacion_de_periodo(detalle_suministro_id, fecha_periodo)`.

El `on_commit` llama a `planificar_venta(compra_venta_id, hoy)` o a `planificar_periodo(detalle_suministro_id, fecha_periodo, hoy)`, que
**vuelven a leer** si la venta o el período están listos (si no, no hacen nada) y planifican **una transacción por invernadero de origen**
(extensión \*a). Una excepción en un invernadero se registra con `logger.exception` (con el id del contrato y del invernadero) y no corta los
demás: la retoma el paso 50 (garantía mínima 2). Nunca vuelve a la persona que disparó: su operación ya quedó registrada.

| Quién la llama | Dónde (extracto) | Cuándo |
|---|---|---|
| COM-REG-CVT | `compra_venta.md`, postcondición g | Al final de `registrar_compra_venta`, si todas las reservas quedaron «lista para entrega» (la venta salió toda de cámara) |
| COM-PCT-SUM | `suministro.md`, postcondición f | Por cada período de la ventana que quedó con todas sus reservas listas |
| PROD-PRR-SUM (paso 40) | `pre_reserva.md` | Por cada período pre-reservado que quedó listo (todo de cámara). El paso 50 corre después igual |
| PROD-CNC-CSC | `cosecha.md`, postcondición n | Si la reserva de la cosecha quedó «lista para entrega» y con ella la venta o el período |
| PROD-ASG-CAM (y el paso 25) | `camara.md`, paso 9 | Por cada venta o período que la asignación dejó listo |
| COM-DCD-FLT | `faltante.md`, paso 7 | Si la decisión deja la venta «abierta» y lista |
| PROD-CNL-ORD (cosechas) | `cancelar_orden.md`, postcondición i | Si las reservas que creó PROD-ASG-STK dejaron lista la venta o el período |
| PROD-VNC-CAM 3a y la merma en cámara 10c | `camara.md` y `merma.md` | Si PROD-ASG-STK volvió a cubrir lo recortado con stock listo |

Si un caso de uso programa dos veces el mismo contrato o período en una transacción, no importa: `planificar_venta` y `planificar_periodo`
vuelven a leer y la segunda llamada no encuentra nada sin entrega (8b).

### «Lista para entrega»: qué se planifica

- **Venta lista** (regla «Venta lista para entrega»; precondición c): `estado_venta = abierta`; ningún detalle `pendiente_decision`; ninguna
  reserva `activa` entre las de sus detalles `abierto` o `confirmado` (las `liberada` no cuentan y las `entregada` ya tienen su entrega); y
  al menos una reserva `lista_para_entrega` **sin línea en una entrega no cancelada**. Se planifican esas reservas.
- **Período listo** (regla «Período listo para entrega»): el suministro `vigente` (también con rescisión acordada: sigue «vigente» hasta el
  cierre, COM-RSC-SUM); el detalle `vigente` o `finalizado` con `fecha_periodo <= fecha_fin_detalle` (D-64, punto 8: ese período se debe);
  ninguna reserva `activa` del período; y al menos una `lista_para_entrega` sin línea en una entrega no cancelada.
- **Invernadero inactivo** (regla 4 de PROD-BAJ-INV; disparador «Cuando exista un caso de uso que planifique… o reintente entregas»): no se
  planifica nada con origen en él, ni en el paso 50. No puede pasar con reservas vivas (lotes y partidas impiden la baja), pero el filtro
  va igual.

### El registro de una entrega (pasos 2 a 11)

Por invernadero de origen (`ReservaStock.invernadero`, D-59), dentro de `transaction.atomic()`:

1. **Bloqueos** (`docs/patrones/bloqueos.md`, «comercial», «Entregas y envasado»): cuentas → invernadero → cliente → contrato → detalles →
   reservas → entregas candidatas a agrupar. Relectura (8b): si alguna reserva ya no está lista o ya tiene línea, **no se registra esa
   entrega** y se sigue con el próximo invernadero.
2. **Fecha programada** (paso 3, 3a): la prometida (`fecha_pactada_venta` o `fecha_periodo`) o hoy si ya pasó.
3. **Destino y modalidad** (paso 4, 1a, 2a): venta con envío → `direccion_envio`; suministro → la dirección del detalle; venta con retiro →
   `modalidad_entrega = retiro`, sin dirección (el destino es el invernadero de origen, que es el de retiro).
4. **Líneas** (paso 4): una por detalle de venta, o por período, con sus reservas (M2M) y `precio_unitario`: el del detalle de venta o
   `precio_en(detalle_suministro, fecha_programada)` (COM-03, regla 7 de 8.11). Peso con `peso_de_entregas` (D-66, punto 4).
5. **Agrupamiento** (4a; y en una venta, D-66 punto 7, a validar): ver abajo. Si agrupa, se agregan las líneas (o las reservas a la línea
   que ya tiene ese detalle) y se sigue en el paso 10.
6. **Transportista** (pasos 5 a 7, 6a, 7a), solo con envío: ver «Candidatos». Con retiro, sin transportista (2a).
7. **Registro** (paso 8): `Entrega` (`tipo = entrega`, `agronomo = None`, `fecha_creacion_orden = hoy`, `numero` de la secuencia de
   órdenes, `estado_confirmacion_cliente = no_confirmado` si es de suministro) y sus líneas. **Antes de crearla,
   `bloquear_invernadero_activo`** (contrato de D-40: una entrega «a realizar» impide la baja del invernadero).
8. **Sin transportista** (6a): la alerta (abajo) y la notificación al Vendedor.
9. **Avisos** (pasos 9 a 11; 2a.3; 3a.2): las notificaciones, dentro de la transacción; el correo al cliente, con `on_commit` (abajo).
10. **Auditoría** (m): abajo.

8a no puede darse: con el invernadero bloqueado, nadie más cambia las entregas de sus transportistas. Igual, la verificación de los pasos 5 a
7 se hace **después** de bloquear (no hay una «elección previa» que repetir).

### Candidatos, verificaciones y selección (pasos 5 a 7)

`candidatos_para(invernadero, fecha, peso, localidad, *, excluir=None, hoy) -> list[Candidato]`, con
`Candidato = namedtuple("Candidato", "transportista vehiculo entregas_del_dia peso_del_dia localidades_del_dia capacidad_libre motivo")`:
un elemento por cada transportista del invernadero (los que cumplen tienen `motivo = None`). La usa COM-05b (COM-ASG-TRP, pasos 4 y 4b) con
`excluir` = el transportista actual. Una consulta por tabla, sin consultas por transportista.

- **Del invernadero de origen:** `TransportistaInvernadero.invernadero` (D-55).
- **Motivo, en este orden** (el primero que falla): «Inactivo» (la cuenta no está activa); «Sin vehículo activo» (sin vehículo, o vehículo
  `inactivo`); «En ruta» (`fecha == hoy` y `vehiculo.esta_en_ruta(hoy)`); «Capacidad de carga insuficiente» (Σ peso de sus entregas **no
  canceladas** de esa fecha + el nuevo > `capacidad_carga`); «Máximo de entregas diarias» (sus entregas no canceladas de esa fecha + 1 >
  `cant_maxima_entregas_diarias`); «Máximo de localidades distintas por día» (las localidades distintas de destino de esas entregas, con la
  nueva, > `cant_max_ciudades_distintas_diarias`). Las entregas del día cuentan concretadas y a realizar (regla «Capacidad de carga»).
- **Localidad de destino** (6a): `direccion_destino.localidad`. Un retiro no tiene transportista, así que no cuenta.
- **Selección** (paso 7, 7a): `seleccionar(candidatos)`, función pura con pruebas de tabla: menos `entregas_del_dia`; después mayor
  `capacidad_libre`; después menor `transportista.pk`.
- **Motivo de la alerta** (6a.2): sin ningún transportista en el invernadero, «sin transportistas activos con vehículo activo»; si no, los
  motivos distintos de los que no cumplen, en el orden de arriba, en minúscula y separados por « · » («capacidad de carga insuficiente ·
  en ruta»). Si todos son «Inactivo» o «Sin vehículo activo», es «sin transportistas activos con vehículo activo».

### Agrupamiento (extensión 4a; D-66, punto 7)

`entrega_para_agrupar(contrato, invernadero, destino, fecha, peso_nuevo, hoy) -> Entrega | None`: la entrega del **mismo contrato**,
invernadero, `direccion_destino` (o retiro) y `fecha_programada_orden`, que cumple **todas**:

- «a realizar»;
- sin `ReservaInsumo` «activa» (sin envasado planificado);
- si tiene transportista: Σ peso de sus entregas no canceladas del día + `peso_nuevo` ≤ `capacidad_carga` (la entrega ya cuenta en el día:
  no se suma una entrega ni una localidad nuevas), y su vehículo no `esta_en_ruta(hoy)` si la fecha es hoy.

Si hay más de una, la de menor id. **En un suministro** (4a): las líneas del período nuevo se agregan como líneas nuevas. **En una venta**
(D-66, punto 7, a validar): solo pasa cuando la venta ya tiene entrega y le quedan reservas listas sin línea (después de un recorte y una nueva
cobertura); las reservas se suman a la línea de su detalle si ya existe en esa entrega, o en una línea nueva. En los dos casos: auditoría
`modificacion_entrega` (líneas agregadas), notificación al transportista si lo tiene (f) y se sigue en el paso 10 (aviso al Agrónomo y correo
al cliente con la entrega completa).

### Ejecución diaria: el paso 50 (disparador 3; D-66, punto 6)

`registrar_paso_diario("planificar_entregas", "Planificar entregas", 50, planificar_entregas)` en `ComercialConfig.ready()`.
`planificar_entregas(hoy) -> ResumenDePaso`. Cada elemento en su transacción; si uno falla, `logger.exception` y sigue (como el paso 25).
Idempotente: dos corridas el mismo día no crean ni avisan nada nuevo.

1. **Recuperación (1b.1, l).** Las ventas y los períodos listos (arriba) con alguna reserva lista sin línea: `planificar_venta` /
   `planificar_periodo` con `hoy`. Con la fecha pasada, 3a.
2. **Búsqueda de transportista (1b.2 a 1b.6, j, k).** Las entregas con envío, «a realizar», sin transportista, de invernaderos activos y
   **creadas antes de hoy** (las de hoy ya se buscaron al crearlas; así no salen dos avisos el mismo día). Fecha de búsqueda: la programada o
   hoy si ya pasó. Con candidato: se asigna; si la fecha había pasado, `fecha_programada_orden = hoy`, aviso de retraso al Vendedor y correo
   al cliente con la nueva fecha; notificación al transportista y al Vendedor; la alerta se resuelve; auditoría `asignacion_transportista`.
   Sin candidato y con la fecha programada = mañana y `recordatorio_para` distinto de esa fecha: el recordatorio al Gerente y al Vendedor, y
   `recordatorio_para = fecha programada`. Si no, nada.
3. **Atrasadas con transportista (n, PCU 8).** Las entregas con envío, «a realizar», con transportista, `fecha_programada_orden < hoy` y
   `aviso_atrasada_para` distinto de su fecha programada: un aviso al Vendedor y al Gerente («reasignala con Asignar transportista») y
   `aviso_atrasada_para = fecha programada`. No cambia nada más (la reasignación es de una persona, COM-ASG-TRP).
4. **Correos pendientes (9-11a).** Las entregas «a realizar» con `estado_aviso_cliente = pendiente_envio`: se vuelve a enviar el último
   correo (el de la planificación, o el del cambio de fecha si lo hubo).

Resumen: `ResumenDePaso(procesados=contratos y períodos revisados + entregas revisadas, creados=entregas creadas, resueltos=alertas
resueltas, detalle="N entregas siguen sin transportista")`.

### Avisos y textos (D-42: dentro de la transacción; sin enlace)

Los textos usan el código de la entrega (`OT-0231`), el del contrato (`CV-0044`, `SUM-0003`) y nombres, nunca ids. Fechas `dd/mm`; peso
«12,40 kg»; cantidades «100 Lechuga Crespa». Si un detalle pasa de 500 caracteres, se recorta con «…» y se cierra con el total de plantas.

| Cuándo | A quién | Título | Detalle |
|---|---|---|---|
| Paso 9 (c) | Transportista | «Nueva entrega para el 26/11» | «OT-0231 · Pérez SA · Mitre 1234, Paraná · 12,40 kg: 100 Lechuga Crespa, 40 Rúcula.» |
| 2a.3 (e) | Vendedor | «Retiro planificado: OT-0231» | «Pérez SA retira el 26/11 en Invernadero Sur: 100 Lechuga Crespa. Lo concretás vos cuando el cliente venga.» |
| 6a.3 (d) | Vendedor | «Entrega sin transportista: OT-0231» | «CV-0044 · Pérez SA · 26/11. Motivo: capacidad de carga insuficiente. InfoPonia vuelve a buscar cada día; el Gerente tiene la alerta.» |
| 3a.2 y 1b.4.2 (g, j) | Vendedor | «Entrega con retraso: OT-0231» | «La fecha prometida era el 24/11 y sale el 26/11.» En un suministro, suma: «Puede haber una queja o una indemnización según la cláusula del suministrante.» |
| 4a.2 (f) | Transportista de la entrega | «Cambió la entrega OT-0231» | «Se agregaron 50 Rúcula de SUM-0003. Peso nuevo: 15,20 kg.» |
| Paso 10 (h) | Agrónomo del invernadero (si está activo) | «Planificá el envasado de OT-0231» | «Entrega del 26/11 a Pérez SA (envío; retiro): 100 Lechuga Crespa, 40 Rúcula · 12,40 kg. Está en Producción › Envasado.» |
| 1b.4.3 (j) | Transportista | «Nueva entrega para el 26/11» | El mismo del paso 9 |
| 1b.4.3 (j) | Vendedor | «OT-0231 ya tiene transportista» | «Lo lleva Juan Gómez el 26/11.» |
| 1b.5 (k) | Gerente y Vendedor | «Mañana sale OT-0231 sin transportista» | «CV-0044 · Pérez SA. Asignale uno o revisá la flota del invernadero.» |
| PCU 8 (n) | Gerente y Vendedor | «Entrega atrasada: OT-0231» | «Era para el 24/11 con Juan Gómez y sigue a realizar. Reasignala con «Asignar transportista».» |

Sin Agrónomo activo en el invernadero, el aviso del paso 10 no se envía (lo verá el que se asigne: regla «Invernadero sin Agrónomo» de
PROD-PNF-ENV). Sin Gerente activo, `notificar_al_gerente` no hace nada (D-14). Un Vendedor inactivo no recibe nada.

**Correo al cliente** (paso 11, 2a.4, 1b.4.2; D-66 punto 12), con `core.correo.enviar_correo` (USR-10) en un `on_commit`:

- Asunto «Tu entrega del 26/11 (OT-0231)», o «Cambió la fecha de tu entrega OT-0231: ahora es el 27/11».
- Cuerpo: la fecha; el destino (con envío, la dirección; con retiro, «Retirala en Invernadero Sur, <dirección del invernadero>»); cada
  variedad con su cantidad; el contacto del Vendedor (nombre, correo y teléfono si lo tiene). Sin montos (se calculan al concretar).
- Un cliente sin correo (solo en compra-venta): `estado_aviso_cliente = sin_correo` y no se intenta. Si `enviar_correo` falla:
  `pendiente_envio` (el paso 50 lo reintenta); si sale: `enviado`.

### Alerta «entrega sin transportista» (6a; D-66 punto 10)

- `TipoAlerta(codigo="comercial_entrega_sin_transportista", nombre="Entrega sin transportista", destinatario=GERENTE,
  severidad=ADVERTENCIA, clase=ESTADO, origen=Origen.ENTREGA)`, registrado en `ComercialConfig.ready()`.
- Se crea con `asegurar_alerta_de_estado(invernadero_id, tipo, clave=f"entrega:{entrega.pk}", descripcion=...)` y su `AlertaComercial`
  con `entrega`. Descripción (200 caracteres como máximo; se recorta primero el cliente): «OT-0231 del 26/11 (Pérez SA) sin transportista:
  capacidad de carga insuficiente».
- Se resuelve con `resolver_alerta_de_estado` al asignarle transportista (paso 50; COM-ASG-TRP, en COM-05b) y al cancelarse la entrega.
- **Enlace** (D-62, `registrar_enlace_de_alerta`): para el Gerente, la lista de entregas con `?entrega=<id>` (la fila de esa entrega),
  texto «OT-0231 · 26/11 · Pérez SA». Cualquier otro rol no la recibe. COM-05b lo cambia a la pantalla de asignación.

### Auditoría (m; D-36: un registro por cambio, origen InfoPonia, D-27)

Acciones nuevas de `core` (con su migración de `choices`): `planificacion_entrega` (una entrega creada: la entrega principal; afectados, sus
líneas y sus reservas; `datos` con la fecha programada, el destino, el peso, el transportista o el motivo y `alertas_creadas`),
`modificacion_entrega` (líneas agregadas o fecha programada cambiada: antes → después) y `asignacion_transportista` (el anterior y el nuevo,
la fecha si cambió y `alertas_resueltas`; la usa también COM-ASG-TRP en COM-05b). El recordatorio y los avisos no se auditan (D-42).
Decimales y fechas como texto.

### Lo que completa a otras tareas

| Tarea | Qué | Dónde estaba |
|---|---|---|
| MAE-05 | `registrar_logistica_de_transportista`: `entregas_a_realizar` (las «a realizar» del transportista) y `url_entregas` (la lista de entregas con `?transportista=<id>`), en el mismo registrante de COM-01 | «Cuando exista Entrega», punto 3 |
| MAE-05 | `registrar_impedimento_de_transportista` con `transportista_con_entregas`: «Tiene N entregas a realizar (la próxima, OT-0231 del 26/11).», como resolver «Reasignalas a otro transportista con «Asignar transportista» (Comercial › Entregas) y volvé a intentarlo.» (regla 9 de PROD-MOD-INV). `transportista_en_ruta` es de COM-06 | «Cuando exista Entrega», punto 2 |
| USR-BAJ-USR | `registrar_asignaciones_de_cuenta`: «Entregas a realizar: N» (regla 4). `registrar_efecto_de_baja_de_cuenta` (postcondición g): sus entregas «a realizar» quedan **sin transportista**, con la alerta (motivo «el transportista fue dado de baja») y la notificación al Vendedor; auditadas en el registro de la baja (`datos.entregas_sin_transportista`, `alertas_creadas`). El paso 50 les busca otro | «Cuando exista Entrega», punto 1 |
| COM-01 (vehículos) | `entregas_a_realizar_del_transportista(transportista)` y `carga_maxima_asignada(vehiculo, desde)` (la mayor Σ peso de las entregas no canceladas del transportista en un día ≥ `desde`), con `peso_de_entregas`; la columna «Entregas a realizar» de la lista y «Carga de los próximos días» en la ficha (regla 2 de COM-CNS-VEH: los próximos 7 días con entregas, cada uno con su peso frente a la capacidad). COM-MOD-VEH y COM-BAJ-VEH bloquean, entre las cuentas, la del transportista del vehículo (y la del nuevo) | «Completan el ABM de vehículo» |
| COM-02 (CNS-CVT) | Regla 4: «Entregas» en la ficha (invernadero de origen, fecha programada, estado —«Atrasada» si corresponde—, transportista o «Retiro»); mientras no hay ninguna, «La entrega se planifica cuando todo el producto esté listo.» | `compra_venta.md`, «Cómo se aplica», regla 4 |
| COM-03 (CNS-SUM) | Regla 6: «Entrega planificada» en el calendario (el período tiene línea en una entrega «a realizar»). Regla 7: «Entregas» en la ficha con fecha, estado y confirmación («No confirmada»); monto, vencimiento y pago, «—» hasta COM-06 y COM-08 | `suministro.md`, «Cómo se aplica», reglas 6 y 7 |
| COM-03 (paso 35) | `cerrar_rescisiones` espera que **no queden entregas del contrato «a realizar»** (si queda una atrasada, el contrato sigue «vigente» y se cierra el día que se concrete o se cancele) | «Cuando exista Entrega», punto 6 |
| COM-04 | PROD-ASG-CAM: la condición «sin línea en una entrega no cancelada» de sus candidatos (un detalle de venta o un período con alguna línea en una entrega «a realizar» o «concretada» no es candidato). El paso 9 y los demás disparadores (tabla de arriba) | «Cuando exista Entrega», punto 7 |
| COM-04 | PROD-VNC-CAM 3a y la merma en cámara 10c: después del recorte, `quitar_lineas_liberadas(entrega_ids)`: las líneas sin reservas vivas quedan en 0 (D-66, punto 4) y cada entrega vacía se cancela con `cancelar_entrega_incluida` (motivo «Se venció en cámara el producto reservado» o «Se perdió en cámara el producto reservado»), todo en la misma transacción. El correo al cliente lo manda el caso de uso base. La entrega **en curso** (3b) es de COM-06 | «Cuando exista Entrega», punto 7 |

Con esto se cierran los puntos 1, 2 (solo `transportista_con_entregas`), 3, 4, 6 y 7 (salvo el enlace de COM-CNL-CVT, que es de COM-05b, y lo
de COM-06) de «Cuando exista Entrega»; «Completan el ABM de vehículo»; y «Cuando exista un caso de uso que planifique… o reintente
entregas» para las entregas.

## Pantallas

Guía visual: `docs/prototipos/comercial/comercial_y_cosecha.html` (leé su `README.md`). Vale la **última** definición de cada función.
Estilo «Diseño v2» (D-47). Criterios de la ronda: tablas siempre ordenadas, contadores en rojo, textos explicativos.

| Pantalla | Funciones del prototipo | Qué hace en COM-05a |
|---|---|---|
| Comercial › **Entregas** (pestaña de Comercial, Gerente y Vendedor) | `tabEntregas` (línea 944) | La lista de entregas: el paso 2 de COM-ASG-TRP **sin** la asignación. Filtros: estado («A realizar» por omisión, «Concretadas», «Canceladas», «Todos los estados»), invernadero (si el actor tiene más de uno en sus contratos) y transportista (con «Sin transportista»). Orden: primero las de envío sin transportista, después fecha programada, después id. Columnas: entrega (`OT-0231` y el contrato), cliente y destino (con retiro, «Retiro en Invernadero Sur»; abajo, el contenido «100 Lechuga Crespa, 40 Rúcula»), fecha (con «hoy», «mañana» o «Atrasada · hace 2 días» en rojo), peso, transportista («No corresponde» en un retiro; «Sin transportista» en rojo), estado y la acción «Ver contrato». Los parámetros `?entrega=<id>` (la alerta) y `?transportista=<id>` (Logística) filtran. Texto explicativo arriba: «InfoPonia planifica las entregas solo, cuando todo el producto de una venta o de un período está listo. Las que quedaron sin transportista se vuelven a buscar cada día.» Vacío: «No hay entregas con estos filtros.» |
| Panel de control del Gerente y del Vendedor: grupo **«Entregas»** | `secComercial` (líneas 1418 y 1548) | Dos indicadores y una tarjeta: «Entregas de hoy» (a realizar con fecha ≤ hoy: de hoy o atrasadas), «Sin transportista» (con envío, a realizar; en rojo si hay) y «Próximas entregas» (las 5 primeras a realizar, por fecha, con «Ver todas»). Cada uno lleva a la lista con su filtro. **No** los indicadores de cobranza (COM-08) ni de solicitudes (COM-07). Sección de `comercial` registrada con `registrar_seccion_de_inicio`; queda después de «Personal por asignar» del Gerente (orden de `INSTALLED_APPS`) |
| Panel del Agrónomo: «Entregas sin envasado» | `secCosecha` (línea 1422) | El indicador del grupo «Cosecha y cámara» de COM-04: entregas «a realizar» de sus invernaderos sin envasado, en ámbar si hay; lleva a «Envasado» (`docs/casos_de_uso/produccion/envasado.md`) |
| Ficha de la compra-venta y del suministro: «Entregas» | `VIEWS.cv` (972), `VIEWS.sum` (1021 y 1585) | Las secciones de la tabla «Lo que completa a otras tareas» (COM-02 y COM-03) |
| Ficha del invernadero › «Logística» | `logistica` (1467), `trPend` | La columna «Entregas a realizar» con su número |
| Vehículos: lista y ficha | `tabVehiculos` (967), `VIEWS.vehform` (1136 y 1807) | La columna «Entregas a realizar» y la carga de los próximos días |

Ninguna pantalla nueva en el menú: «Entregas» es una pestaña de «Comercial» (`comTabs`), después de «Contratos».

### Lo que difiere del prototipo (corregir, D-61)

- `tabEntregas` ofrece «Asignar transportista», «Cambiar transportista» y «Concretar retiro»: en COM-05a, solo «Ver contrato» (las otras dos
  son de COM-05b y COM-06; D-25: solo lo que existe).
- `tabEntregas` dice «Vencida» para una entrega con la fecha pasada: es «Atrasada» (MD-139).
- `tabEntregas` filtra transportistas por nombre (`e.tra===S.flt.etra`): en el sistema, por id.
- `secComercial` muestra «Cobranza vencida» y «Solicitudes pendientes»: no en COM-05a; y «vencida» es «en mora» (MD-139) cuando llegue.
- El prototipo usa identificadores `ENT-0110`: el sistema, `OT-0231` (D-52, punto 3).

### Solo prototipo

Lo de la lista general de `docs/prototipos/comercial/README.md`, más: los datos de ejemplo de `DB.ent`, `destino(e)` y `rel(…)` como
funciones de muestra.

## Pruebas

- `comercial/tests/test_com_pnf_ent.py`:
  - `ComPnfEntServicioTests`: una por regla (venta lista, período listo, alcance, destino, fecha, cantidad planificada, precio, peso,
    candidato, capacidad, límites, capacidad libre, selección, agrupamiento —cada condición, una por prueba—, estado inicial, aviso de
    envasado), por postcondición (a a i, m) y por extensión (1a, 2a, 3a, 4a, 6a con cada motivo, 7a, 8b, \*a: un invernadero falla y el otro
    queda); la venta de dos invernaderos (dos entregas); el período de un detalle finalizado con fecha ≤ fin; el invernadero inactivo; el
    agrupamiento de la venta (D-66 punto 7); `seleccionar` con pruebas de tabla; el correo con `captureOnCommitCallbacks` (enviado, falla,
    sin correo); que los disparadores **no** planifican dentro de la transacción del que llama (`on_commit`).
  - `ComPnfEntDiariaTests`: las cuatro partes del paso 50 (j, k, l, n y el reintento de correos), cada una con y sin datos; dos corridas el
    mismo día sin nada nuevo; el recordatorio una sola vez; la entrega creada hoy que no recibe recordatorio; la atrasada con transportista
    avisada una vez y otra vez si cambia la fecha; un elemento que falla y los demás que siguen; `proceso_diario --listar` muestra el 50.
- `comercial/tests/test_entregas_concurrencia.py` (`@tag("concurrencia")`): dos planificaciones del mismo invernadero por el último lugar de
  un transportista (una queda sin transportista); una planificación contra la cancelación de la misma venta (COM-05b: mientras tanto, contra
  una merma en cámara que libera la reserva); dos corridas del paso 50 a la vez.
- `comercial/tests/test_entregas_vistas.py`: permisos (Gerente todas, Vendedor solo las suyas, Agrónomo y Capataz 403), filtros, orden, los
  parámetros `?entrega=` y `?transportista=`, el panel por rol, las secciones de las fichas de contrato, la columna de Logística y de
  vehículos.
- Invariantes: `verificar_invariantes_de_entregas()` (los de `docs/modelo/comercial.md`) después de cada prueba que crea entregas.

## Para más adelante

- **COM-05b:** COM-ASG-TRP está abajo, después de esta sección; COM-CNL-CVT, en `compra_venta.md`.
- **COM-06a** (lote C6, `docs/casos_de_uso/comercial/rutas.md`): COM-INI-RUT (el peso de la ruta con `peso_de_entregas`; las entregas en curso), COM-CNC-ENT (cantidad entregada, monto,
  vencimiento, precio recalculado), `transportista_en_ruta` (impedimento del invernadero y de la baja de cuenta), PROD-VNC-CAM 3b.
- Temas abiertos del caso de uso: la hora de la ejecución diaria (con el cron único, D-56) y el tope de búsquedas de una entrega sin
  transportista (hoy, sin tope: lo avisa la alerta).

---

## COM-ASG-TRP · Asignar Transportista a Entrega

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Decisiones del 20/11/2026 aplicadas: A
(una entrega en curso no se reasigna; la salida es el intento fallido), B (el actor elige entre los candidatos), C (una fecha vencida pasa al
día actual con aviso de retraso), D (no se quita el transportista sin poner otro) y E (aviso diario por entregas asignadas con fecha vencida,
en COM-PNF-ENT).

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** Comercial / Órdenes. **Versión:** 0.1

**Actor principal:** Vendedor del contrato de la entrega. El Gerente también puede ejecutarlo.

**Personal involucrado e intereses**

- **Vendedor:** quiere resolver rápido una entrega que quedó sin transportista, o reemplazar a uno que no puede cumplir, sin rearmar la entrega.
- **Gerente:** quiere que la asignación respete la capacidad de los vehículos y los límites diarios de la configuración operativa, y dejar de
  recibir la alerta de una entrega sin transportista.
- **Transportista:** quiere que se le avise cuando recibe una entrega y cuando se la quitan, y no recibir más de lo que puede llevar.
- **Cliente:** quiere recibir su entrega en la fecha prometida y que, si cambia la fecha, se le avise.

**Relaciones con otros casos de uso**

- No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
- **Lo preceden:** COM-PNF-ENT · Planificar Entrega, que puede dejar una entrega sin transportista (extensión 6a), y COM-CNC-ENT · Concretar
  Entrega, que deja sin transportista una entrega que no se pudo realizar (extensión 4a).
- **Lo siguen:** COM-INI-RUT · Iniciar Ruta y COM-CNC-ENT · Concretar Entrega, con el transportista nuevo.
- **Relacionados, sin inclusión:** la ejecución diaria de COM-PNF-ENT, que también busca transportista para las entregas que no lo tienen;
  COM-MOD-VEH y COM-BAJ-VEH, que mandan a este caso de uso a reasignar las entregas antes de bajar la capacidad, cambiar el transportista o
  dar de baja un vehículo.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Vendedor o Gerente.

b. Existe al menos una entrega con envío en estado «a realizar»; si el actor es Vendedor, de un contrato del que es Vendedor.

**Garantías mínimas**

- La asignación es atómica. Si falla o se cancela, la entrega conserva su transportista, su fecha y sus alertas.
- Ningún transportista queda con entregas que superen la capacidad de carga de su vehículo ni los límites diarios de la configuración
  operativa, aun cuando se asignen o se planifiquen entregas al mismo tiempo.
- Ninguna entrega en curso cambia de transportista.
- El contenido de la entrega (detalles, reservas y envasado) no cambia.

**Garantías de éxito (Postcondiciones)**

a. La entrega quedó asignada al transportista elegido.

b. Si su fecha programada ya había pasado, pasó a la fecha actual. Se notificó el retraso al Vendedor del contrato (en un suministro, con la
advertencia de posible queja o indemnización) y se le envió al cliente un correo con la nueva fecha.

c. Si la entrega tenía activa la alerta «entrega sin transportista», la alerta quedó resuelta, con la fecha actual como fecha de resolución.

d. Se notificó la entrega al transportista nuevo y, si había uno, se notificó al anterior que ya no la tiene.

e. Si el actor fue el Gerente, se notificó la asignación al Vendedor del contrato.

f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la entrega, el transportista anterior y el nuevo, el cambio
de fecha si lo hubo y la alerta resuelta.

**Escenario principal de éxito** (la entrega no tiene transportista, su fecha es futura y hay candidatos)

1. El Vendedor inicia la asignación de transportistas.
2. El Sistema presenta las entregas con envío «a realizar» de sus contratos, primero las que no tienen transportista y después las demás,
   ordenadas por fecha programada. Para cada una indica el cliente, el destino, la fecha, el peso, el invernadero de origen y el transportista
   actual, si lo tiene.
3. El Vendedor selecciona una entrega.
4. El Sistema presenta los transportistas candidatos para la fecha de la entrega. Para cada uno indica la capacidad libre de su vehículo, las
   entregas que ya tiene ese día y las localidades distintas que visita.
5. El Vendedor selecciona un transportista.
6. El Sistema presenta el resumen: la entrega, el transportista elegido y cómo quedan su carga, sus entregas y sus localidades del día frente
   a los límites.
7. El Vendedor confirma.
8. El Sistema vuelve a verificar que la entrega siga «a realizar» y que el transportista siga cumpliendo las verificaciones. Después registra
   la asignación, resuelve la alerta y registra la auditoría.
9. El Sistema notifica la entrega al transportista.
10. El Sistema informa al Vendedor que la entrega quedó asignada.

**Extensiones**

- **\*a. En cualquier momento antes del paso 7, el actor cancela:** 1. El Sistema descarta la elección y la entrega queda como estaba.
- **\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:** 1. El Sistema revierte cualquier registro parcial y, al
  restablecerse, informa que la asignación no se registró.
- **1a. El actor es el Gerente:** 1. En el paso 2, el Sistema presenta las entregas de todos los contratos. 2. En el paso 9, el Sistema
  notifica además al Vendedor del contrato.
- **1b. El actor inicia la asignación desde la alerta «entrega sin transportista»:** 1. El Sistema presenta directamente la entrega de la
  alerta y el caso de uso continúa en el paso 4.
- **3a. La entrega está en curso: su transportista inició la ruta del día (MD-118) y la fecha programada es igual o anterior a la actual:**
  1. El Sistema informa que no se puede reasignar, porque el producto ya está cargado en el vehículo, y explica que, si no puede entregarse,
  el transportista debe registrar el intento fallido (COM-CNC-ENT, extensión 4a). 2. El actor elige otra entrega (vuelve al paso 3) o cancela.
- **4a. La fecha programada de la entrega ya pasó:** 1. El Sistema informa que la entrega se reprogramará para la fecha actual y presenta los
  candidatos para hoy. 2. El caso de uso continúa en el paso 5. En el paso 8, la fecha pasa a hoy y se avisa el retraso.
- **4b. Ningún transportista cumple las verificaciones:** 1. El Sistema informa el motivo de cada transportista del invernadero de origen:
  inactivo, sin vehículo activo, en ruta, capacidad insuficiente, máximo de entregas diarias o máximo de localidades. 2. El Sistema informa
  que el Gerente puede dar de alta un transportista o un vehículo, o ajustar la configuración operativa. 3. La entrega queda como estaba y el
  caso de uso termina.
- **5a. La entrega ya tenía transportista y el actor elige otro:** 1. En el paso 6, el resumen indica también el transportista que la deja.
  2. En el paso 9, el Sistema notifica además al transportista anterior que ya no tiene la entrega.
- **8a. Al registrar, la entrega ya no está «a realizar», ya está en curso, o le asignaron otro transportista en otra operación:** 1. El
  Sistema no registra ningún cambio, informa la situación actual y vuelve al paso 2.
- **8b. Al registrar, el transportista elegido ya no cumple las verificaciones (otra planificación le asignó entregas, o inició su ruta):**
  1. El Sistema no registra ningún cambio, informa el motivo y vuelve al paso 4 con los candidatos actualizados.
- **9a. El Sistema no logra enviar una notificación o el correo al cliente:** 1. La asignación permanece registrada y el Sistema reintenta
  el envío.

**Requisitos especiales**

- La interfaz del Vendedor y la del Gerente están pensadas para computadora.
- Los candidatos del paso 4 se presentan en no más de 2 segundos.
- El paso 8 se ejecuta como una única transacción.
- La asignación se serializa con las planificaciones, las asignaciones y el inicio de ruta del mismo transportista y la misma fecha, para que
  dos operaciones simultáneas no superen sus límites (COM-PNF-ENT, requisito de concurrencia).
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los pesos se expresan en kilogramos con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

- **Quién asigna:** el Vendedor del contrato de la entrega o el Gerente (regla 12 de 8.12). Las entregas de un contrato cuyo Vendedor está
  inactivo las asigna el Gerente. (Paso 1 y extensión 1a)
- **Entrega asignable:** con envío, «a realizar» y que no está en curso. Los retiros en invernadero no tienen transportista. (Pasos 2 y 3,
  extensión 3a)
- **Entrega en curso:** con envío, con la fecha programada igual o anterior a la actual y con el vehículo de su transportista en ruta (MD-118;
  regla «Entregas de la ruta» de COM-INI-RUT). No se reasigna, porque el producto ya salió en otro vehículo; la salida es el intento fallido.
  (Extensión 3a)
- **Candidatos:** los de la regla «Transportista candidato» de COM-PNF-ENT para la fecha de la entrega, sin contar al transportista actual.
  Se aplican la capacidad de carga, el límite de entregas diarias y el límite de localidades, sumando la entrega nueva (reglas 5 a 7 de 8.12).
  A diferencia de COM-PNF-ENT, el actor elige entre los candidatos y no se aplica el criterio de selección automática. (Paso 4)
- **Contenido sin cambios:** la asignación no cambia los detalles, las reservas ni el envasado de la entrega. (Garantías mínimas)
- **Fecha:** cambia solo si ya venció, y pasa a la fecha actual, con el aviso de retraso (regla 3 de 8.12). No hay entregas anticipadas.
  (Extensión 4a)
- **Sin quitar el transportista:** este caso de uso no deja una entrega sin transportista; solo lo asigna o lo cambia. (Paso 5)
- **Alerta:** al asignar, se resuelve la alerta «entrega sin transportista» de la entrega, como en la ejecución diaria de COM-PNF-ENT
  (postcondición j). (Paso 8)
- **Avisos:** el transportista nuevo y el anterior reciben una notificación; si la fecha cambió, el cliente recibe un correo y el Vendedor,
  el aviso de retraso; si asignó el Gerente, se notifica al Vendedor. (Pasos 8 y 9)
- **Transportista en el invernadero** (regla a agregar de «CU · Transportista en el invernadero (v0.1)»): una entrega del día cuyo
  transportista está en ruta no se reasigna mientras lo esté. Los candidatos son los transportistas activos del invernadero de la entrega
  (R155), con vehículo, que no están en ruta. (Es la misma regla que la extensión 3a y la de «Candidatos»: no agrega nada nuevo.)

**Lista de tecnología y variaciones de datos:** 4a. La capacidad libre se expresa en kilogramos, con dos decimales, junto a la capacidad total
del vehículo.

**Frecuencia:** ocasional. Cuando una entrega queda sin transportista o cuando un transportista no puede cumplir.

**Temas abiertos:** una entrega que nunca consigue transportista se sigue buscando cada día, sin límite (tema abierto de COM-PNF-ENT).

## Cómo se aplica en la ronda «Comercial 1»: COM-ASG-TRP (COM-05b; D-44, D-57, D-66, D-67)

Todo el caso de uso entra. No tiene asientos (no hay nada «fuera de la ronda»). Lo que reutiliza de COM-05a1 no se vuelve a escribir:
`candidatos_para` (con `excluir`), `peso_de_entregas`, `en_curso`, `atrasada`, los textos de «Avisos y textos», el correo del cambio de fecha
con `estado_aviso_cliente` y la acción de auditoría `asignacion_transportista`.

### Servicios (`comercial/servicios/entregas.py`)

- **Lectura, sin escribir y sin consultas por fila:** `datos_de_asignacion(actor, entrega_id) -> DatosDeAsignacion` (la entrega con su
  contrato, cliente, destino, peso, invernadero y transportista actual; `en_curso`; `fecha_de_busqueda` = la programada o hoy si ya pasó, con
  `reprograma=True`; los candidatos de `candidatos_para(..., excluir=transportista actual)`, con su motivo; la `huella`) y
  `resumen_de_asignacion(actor, entrega_id, transportista_id) -> ComoQueda` (carga del día con la entrega, entregas «N + 1 de M»,
  localidades, la fecha, y el transportista que la deja). Una consulta por tabla: los candidatos se presentan en menos de 2 segundos.
- **Escritura:** `asignar_transportista(actor, entrega_id, transportista_id, huella) -> Entrega`, en `transaction.atomic()`. Errores con
  `ValidationError` y `code`, como el resto de `comercial`.
- **Huella** (`huella_de_entrega(entrega)`): estado, transportista, fecha programada y peso al abrir la pantalla. Si al confirmar no coincide:
  8a (`entrega_cambio`: «La entrega cambió mientras la mirabas (se asignó, se canceló o salió en ruta). Volvé a la lista.»).

### Reglas en el código

- **Quién** (paso 1, 1a; regla 12 de 8.12): `rol_requerido("gerente", "vendedor")` en las vistas; en el servicio, `Entrega.objects.en_alcance_de(actor)`
  (D-28): el Vendedor activo, las de sus contratos; el Gerente, todas. Un contrato de un Vendedor inactivo solo aparece para el Gerente (lo
  da el alcance: el Vendedor inactivo no entra). Fuera del alcance, 403 con mensaje (SEG-13).
- **Entrega asignable** (pasos 2 y 3): con envío, «a realizar» y no en curso. Un retiro no se ofrece y el servicio lo rechaza
  (`entrega_sin_envio`); una «concretada» o «cancelada», `entrega_no_a_realizar`.
- **3a (en curso):** `en_curso(entrega, hoy)`. La pantalla no muestra candidatos: muestra el aviso del prototipo («{transportista} ya inició
  la ruta: el producto está cargado en su vehículo y la entrega no se puede reasignar. Si no puede entregarla, el transportista registra el
  intento fallido.») y el servicio rechaza `entrega_en_curso`. Es también la regla «Transportista en el invernadero» y la del disparador
  «Cuando exista Entrega», punto 2 (D-55): una entrega del día de un transportista en ruta no se reasigna.
- **4 y 4b:** se muestran **todos** los transportistas del invernadero de origen, cada uno con su motivo si no cumple (en el orden de
  «Candidatos…»), y solo los que cumplen se pueden elegir. Sin ninguno que cumpla (4b), el aviso dice el motivo de cada uno y, según el rol:
  Gerente, «Podés dar de alta un transportista en la ficha del invernadero («Logística»), un vehículo, o ajustar los límites en
  «Configuración».»; Vendedor, «Avisale al Gerente: puede sumar un transportista o un vehículo, o ajustar los límites.». El botón de
  asignar queda deshabilitado con su motivo. Sin transportistas en el invernadero: «El invernadero de origen no tiene transportistas.»
- **4a (fecha pasada):** el aviso «La fecha ya pasó: la entrega se reprogramará para hoy, dd/mm. Se avisará el retraso al cliente y al
  Vendedor.» y los candidatos para hoy.
- **5, 6 y 5a (elegir y ver cómo queda):** la tarjeta «Cómo queda» del prototipo es el **resumen del paso 6**: aparece al elegir (con HTMX,
  por `calcular/`, que no escribe) y, sin JavaScript, con el botón «Ver cómo queda» (la misma página con la tarjeta). Muestra la carga del día
  «12,40 + 15,20 = 27,60 de 400,00 kg», las entregas «2 de 3», las localidades «2 de 2», la fecha y, en 5a, «Deja la entrega: Juan Gómez
  (recibirá un aviso)». «Asignar transportista» es la confirmación (paso 7). No hay una ventana aparte: el resumen ya está en la misma
  pantalla, junto al botón (D-61).
- **Sin quitar el transportista** (regla; decisión D): no hay ninguna acción para dejar una entrega sin transportista.
- **Paso 8, la transacción** (`docs/patrones/bloqueos.md`, «Entregas y envasado», «Asignar un transportista»):
  1. las cuentas del actor, del Vendedor del contrato, del transportista nuevo y del actual (en una consulta y en orden de id); se releen:
     el actor activo y con su rol (`sin_permiso`), el nuevo activo y **todavía del invernadero de origen** (un traslado de MAE-05 lo sacó: 8b);
  2. el **invernadero de origen** (`bloquear_invernadero_activo`, el semáforo de D-66 punto 11: pone en fila esta asignación con las
     planificaciones, las otras asignaciones y el inicio de ruta del mismo transportista);
  3. la **entrega** (`OrdenTrabajo`, `FOR NO KEY UPDATE`).
  Después, la relectura: **8a** (la huella, «a realizar», no en curso) y **8b** (`candidatos_para` otra vez, ya con el invernadero
  bloqueado, para ese transportista y la fecha de búsqueda con `hoy`: si ahora tiene motivo, `transportista_no_cumple` con el motivo y la
  pantalla vuelve al paso 4 con los candidatos actualizados). Si `hoy` cambió entre la lectura y la confirmación y la fecha programada
  pasó a estar vencida, se trata como 4a: la fecha de búsqueda se recalcula y, si el transportista ya no cumple para hoy, es 8b.
  Con todo verificado: `transportista` = el nuevo; si la fecha programada es anterior a hoy, `fecha_programada_orden = hoy` (4a, b); la
  alerta `comercial_entrega_sin_transportista` de la entrega, resuelta si estaba activa (c); los avisos (d, e, b) y el registro (f).
- **Avisos** (D-42: dentro de la transacción, sin enlace; textos de «Avisos y textos» y estos dos nuevos):

  | Cuándo | A quién | Título | Detalle |
  |---|---|---|---|
  | d | Transportista nuevo | «Nueva entrega para el 26/11» | El mismo del paso 9 de COM-PNF-ENT |
  | 5a.2 (d) | Transportista anterior (si está activo) | «Ya no tenés la entrega OT-0231» | «{Nombre del actor} se la asignó a otro transportista. Era para el 26/11 a Pérez SA.» |
  | b | Vendedor | «Entrega con retraso: OT-0231» | El mismo de 3a.2 de COM-PNF-ENT (con la advertencia en un suministro) |
  | 1a.2 (e) | Vendedor (si actuó el Gerente y el Vendedor está activo) | «OT-0231 ya tiene transportista» | «El Gerente se la asignó a Ana Pérez para el 26/11.» |

  El correo al cliente con la nueva fecha (b) es el del cambio de fecha de COM-PNF-ENT (1b.4.2), con `on_commit` y `estado_aviso_cliente`.
- **9a:** las notificaciones van dentro de la transacción (D-42): no fallan por separado. El correo que no sale queda `pendiente_envio` y lo
  reintenta el paso 50 (D-66, punto 12), como en COM-PNF-ENT.
- **Auditoría (f; D-36):** un registro `asignacion_transportista` (ya existe desde COM-05a1) con el actor y su rol como origen (usuario, no
  InfoPonia); afectados: la entrega (principal); `cambios`: transportista anterior → nuevo y, si cambió, la fecha programada (como texto);
  `datos`: `alertas_resueltas`.
- **Alerta «entrega sin transportista», enlace** (D-66 punto 10; extensión 1b): COM-05b cambia el registrante de `registrar_enlace_de_alerta`
  de COM-05a1: para el Gerente, la pantalla de asignación de esa entrega (`entregas/<id>/asignar/`), con el mismo texto. Si la entrega ya no
  es asignable (en curso, concretada, cancelada), la pantalla lo dice y ofrece «Ver la lista de entregas».
- **La lista de entregas** (paso 2) es la de COM-05a1, con dos acciones nuevas en cada fila con envío «a realizar»: «Asignar transportista»
  (sin transportista) y «Cambiar transportista» (con transportista y no en curso). Una en curso dice «En curso» sin acción. Los retiros no
  tienen acción de asignar.

### Pantallas

| Pantalla | Funciones del prototipo | Qué hace en COM-05b |
|---|---|---|
| Comercial › Entregas: acciones | `tabEntregas` | «Asignar transportista» y «Cambiar transportista» (arriba). «Concretar retiro» sigue siendo de COM-06 |
| Asignar / Cambiar transportista | `INIT.asg`, `VIEWS.asg` (las dos definiciones: vale la de la línea 1804, que suma el aviso de en curso), `candidatos` (las dos: vale la de la línea 1803, que suma «Inactivo» y «Máximo de localidades») | La pantalla de arriba. URL `comercial/entregas/<id>/asignar/` (con `calcular/`); texto explicativo arriba: «Elegí quién lleva la entrega. Solo se pueden elegir los transportistas del invernadero de origen que pueden llevarla ese día: el resto muestra por qué no.» |

### Lo que difiere del prototipo (corregir, D-61)

- `candidatos` filtra por nombre (`t.n!==e.tra`) y no mira si la cuenta está inactiva en la primera definición: en el sistema, por id y con
  todos los motivos de `candidatos_para`, en su orden.
- `ACT['asg-ok']` asigna sin volver a verificar (8a, 8b), sin auditoría y sin avisos: en el sistema, la transacción de arriba.
- `ACT['asg-ok']` borra la alerta (`DB.alertas.filter`): en el sistema se **resuelve** (queda en el historial).
- El aviso de 4b dice «Registre un vehículo»: el sistema usa voseo («Podés…») y nombra también al transportista y la configuración.

### Pruebas

- `comercial/tests/test_com_asg_trp.py`, `ComAsgTrpServicioTests`: una por regla (quién asigna, con el Vendedor inactivo; asignable; en curso;
  candidatos sin el actual; contenido sin cambios: las líneas, las reservas y las reservas de insumo quedan iguales; fecha; sin quitar;
  alerta; avisos), por postcondición (a a f) y por extensión (1a, 1b, 3a, 4a, 4b con cada motivo, 5a, 8a con cada causa, 8b con cada causa,
  `hoy` que cambia entre la lectura y la confirmación); el retiro rechazado; el transportista trasladado a otro invernadero en el medio (8b);
  el correo con `captureOnCommitCallbacks` (enviado y falla: `pendiente_envio`); sin consultas por fila en `datos_de_asignacion`
  (`assertNumQueries` con 1 y con 5 transportistas).
- `comercial/tests/test_entregas_concurrencia.py` (`@tag("concurrencia")`, métodos nuevos): una asignación y una planificación por el último
  lugar del mismo transportista (la segunda ve 8b o queda sin transportista); dos asignaciones de la misma entrega (la segunda ve 8a); una
  asignación contra la baja de la cuenta del transportista; una asignación contra la cancelación de la venta (COM-CNL-CVT: 8a).
- `comercial/tests/test_entregas_vistas.py` (métodos nuevos) y `test_com_asg_trp.py`, `ComAsgTrpVistaTests`: permisos (el Vendedor no ve
  entregas ajenas, Agrónomo y Capataz 403, ningún botón lleva a un 403); las acciones de la lista según el estado; la campana del Gerente que
  lleva a la asignación; el flujo con HTMX y sin él («Ver cómo queda»); `calcular/` no escribe nada.
