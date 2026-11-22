# Casos de uso · producción · Asignar Stock Maduro

Copia para el repo de PROD-ASG-STK, versión 0.3 de «CU extendidos» (la tabla de pendientes_CU decía 0.2: lo corrige PCU, sección 2).
Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU (comercial)» (Drive, secciones 1 a 16: las 7 y 9 cambian este caso de uso),
con el modelo de dominio (reglas 5 a 12 de 8.6, 1, 2, 9, 10 y 14 de 8.8, 3 de 8.11 y 2 y 3 de 8.20) y con el glosario.

Aunque su código empieza con PROD, **el código va en la app `comercial`** (D-59, regla A3 de D-37): crea reservas, que son de `comercial`.
Lo programa COM-02 y lo reutilizan sin cambiarlo COM-03, COM-04 y COM-05. El cálculo, los bloqueos y la API están en
`docs/patrones/stock_maduro.md`; el archivo de pruebas es `comercial/tests/test_prod_asg_stk.py`.

Si este archivo y «CU extendidos» no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: este caso de uso no numera sus reglas, así que se usa el nombre de la regla en minúsculas y con guiones bajos
(`test_partida_elegible_…`, `test_orden_de_asignacion_…`), y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## PROD-ASG-STK · Asignar Stock Maduro

**Alcance:** Sistema InfoPonia.  
 **Nivel:** Subfunción.  
 **Módulo:** Producción / Órdenes.  
 **Actor principal:** InfoPonia, por cuenta del caso de uso que lo incluye. No hay interacción con usuarios.  
 **Versión:** 0.3

**Personal involucrado e intereses**

**Vendedor:**

  - quiere que el producto de sus contratos quede reservado en cuanto se pacta, sin elegir él de dónde sale;
  - quiere enterarse, por el caso de uso base, de lo que no se pudo cubrir.

**Cliente:**

  - quiere que lo que compró esté apartado para él y le llegue en condiciones comerciales en la fecha prometida.

**Agrónomo:**

  - quiere enterarse de cada cosecha automática de sus invernaderos, para validarla o modificarla a tiempo.

**Capataz:**

  - quiere recibir con anticipación las órdenes de cosecha de su invernadero, con los lotes y las cantidades ya definidos.

**Gerente:**

  - quiere que ningún lote ni ninguna partida se comprometa dos veces;
  - quiere enterarse si un invernadero sin Capataz activo deja lotes sin poder asignarse.

**Organización (Jardín Botánico):**

  - quiere vender primero lo que está en cámara, antes de que venza, y después los lotes más antiguos, antes de que se pasen;
  - quiere no comprometer producto que perderá su aptitud comercial antes de la entrega.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - **Es incluido por:**
      
      - COM-REG-CVT · Registrar Compra-venta (paso 15);
      - COM-PCT-SUM · Pactar Suministro (paso 14);
      - PROD-CNC-CSC · Concretar Cosecha (extensión 13a);
      - PROD-REG-MRM · Registrar Merma (extensión 10c).
  - **Inclusiones previstas:**
      
      - Planificar Cosecha por Contrato (a especificar), proceso diario de InfoPonia que reserva los períodos de suministro que entran en la ventana de pre-reserva;
      - Cancelar Orden (CU-11), al cancelar una cosecha que cubre un contrato.
  - **Relacionados, sin inclusión:**
      
      - la asignación automática de cámara es un proceso aparte (caso por especificar 9);
      - la cosecha manual del Agrónomo (PROD-PNF-CSC) no usa esta asignación;
      - la alerta por invernadero sin Capataz activo la resuelve el caso de uso que le asigne un Capataz (Modificación Invernadero o Baja Capataz, a especificar).

**Precondiciones**

Las garantiza el caso de uso base:

a. Hay una transacción del caso de uso base en curso.  
 b. El detalle de contrato es uno que se puede cubrir: un detalle de venta “abierto” de una venta “abierta”, o un detalle de suministro “vigente” para el período indicado.  
 c. El caso de uso base indicó la fecha de entrega y una cantidad a cubrir mayor que cero.

**Garantías mínimas**

  - El caso de uso forma parte de la transacción del caso de uso base. Si el base se revierte, no queda ninguna reserva, línea de reserva ni orden de cosecha creadas por este caso de uso, ni sus logs de auditoría, y no se envía ningún aviso.
  - La única excepción es la alerta al Gerente por invernadero sin Capataz activo, que permanece registrada, con su log de auditoría, aunque el caso de uso base se revierta.
  - Ningún lote ni ninguna partida queda reservado por encima de su stock libre, aun con asignaciones simultáneas.
  - Ningún detalle queda reservado por encima de su cantidad sin cubrir.
  - No se modifica la cantidad actual de ningún lote ni la cantidad disponible de ninguna partida.
  - No se modifica el estado del detalle ni del contrato, no se avisa al cliente ni al Vendedor y no se planifica ninguna entrega.

**Garantías de éxito (Postcondiciones)**

**Si se reservó alguna cantidad:**

a. Se creó una reserva por cada invernadero del que se tomó stock, asociada al detalle de contrato, con la fecha de entrega indicada.  
 b. Cada reserva quedó con una línea por cada partida y por cada lote de los que se tomó stock, con su cantidad reservada. Las líneas de lote quedaron sin cantidad cosechada.  
 c. Cada reserva quedó “lista para entrega” si todas sus líneas son de cámara, o “activa” si tiene al menos una línea de lote.  
 d. Por cada reserva con líneas de lote, se creó una orden de cosecha “a realizar”, asociada a la reserva, con:

  - la variedad, el invernadero y sus lotes;
  - la fecha de creación igual a la fecha actual;
  - la fecha programada según la regla de cosechas automáticas;
  - la prioridad media;
  - el Capataz del invernadero.

e. La cantidad total reservada es la menor entre la cantidad a cubrir y el stock maduro libre que se pudo tomar.

**En todo caso:**

f. Se devolvió al caso de uso base la cantidad cubierta, la cantidad que quedó sin cubrir y las reservas y cosechas creadas.  
 g. Por cada invernadero considerado sin Capataz activo que tenía lotes que podían asignarse, existe una alerta activa para el Gerente.  
 h. Después de que el caso de uso base confirmó su transacción, se notificó cada orden de cosecha creada al Capataz y al Agrónomo del invernadero; a este último, para que la valide o la modifique.

**Auditoría:**

i. Se creó un log de auditoría por cada reserva, línea de reserva, orden de cosecha y alerta creadas, con fecha, hora, identificador y valores. El origen es el del caso de uso base: un usuario, con su rol, o un proceso automático.

**Escenario principal de éxito (o Flujo Básico)**

(Detalle de una compra-venta con envío, cubierto con una partida de cámara y un lote del mismo invernadero; se crean una reserva “activa” y una orden de cosecha.)

1.  **El caso de uso base solicita la asignación de stock maduro para un detalle de contrato, con la fecha de entrega y la cantidad a cubrir.**
2.  **InfoPonia determina la cantidad a reservar: la menor entre la cantidad indicada y la cantidad sin cubrir del detalle.**
3.  **InfoPonia determina los invernaderos considerados: en una compra-venta con envío, los invernaderos del Vendedor del contrato.**
4.  **InfoPonia toma stock de las partidas de cámara elegibles, de la que vence antes a la que vence después, hasta reservar la cantidad o agotar las partidas.**
5.  **InfoPonia calcula la fecha programada de la cosecha y toma el resto de los lotes elegibles, del que entró antes en Maduración al que entró después, hasta reservar la cantidad.**
6.  **InfoPonia crea una reserva para el invernadero, con una línea para la partida y otra para el lote, en estado “activa”.**
7.  **InfoPonia crea la orden de cosecha “a realizar” de la reserva, con el lote, la fecha programada, la prioridad media y el Capataz del invernadero.**
8.  **InfoPonia registra la auditoría correspondiente.**
9.  **InfoPonia devuelve al caso de uso base la cantidad cubierta (toda la indicada), la cantidad sin cubrir (cero), la reserva y la cosecha.**
10. **Cuando el caso de uso base confirma su transacción, InfoPonia notifica la orden de cosecha al Capataz y al Agrónomo del invernadero.**

**Extensiones (o Flujos Alternativos)**

**2a. El detalle no tiene cantidad sin cubrir:**

1.  InfoPonia no crea nada y devuelve una cantidad cubierta de cero y una cantidad sin cubrir de cero.
2.  El caso de uso termina.

**3a. El detalle es de una compra-venta con retiro:**

1.  InfoPonia considera solo el invernadero de retiro.

**3b. El detalle es de un suministro:**

1.  InfoPonia considera los invernaderos del Vendedor del contrato, igual que en una compra-venta con envío.

**4a. Las partidas de cámara cubren toda la cantidad:**

1.  InfoPonia no toma stock de lotes.
2.  Cada reserva queda “lista para entrega”, sin orden de cosecha.
3.  El caso de uso continúa en el paso 8, y en el paso 10 no hay avisos.

**5a. Un invernadero considerado no tiene Capataz activo:**

1.  InfoPonia no considera los lotes de ese invernadero; sus partidas de cámara sí se consideran.
2.  Si el invernadero tenía lotes que podían asignarse y no hay una alerta activa de ese tipo para él, InfoPonia genera una alerta para el Gerente que indica que el invernadero no tiene Capataz activo y que sus lotes no se están asignando. La alerta queda registrada aunque el caso de uso base se revierta.

**5b. El stock tomado viene de más de un invernadero:**

1.  InfoPonia crea una reserva por cada invernadero, con sus líneas de cámara y de lote.
2.  Cada reserva con líneas de lote tiene su propia orden de cosecha, con el Capataz de ese invernadero.

**5c. El stock maduro libre cubre solo una parte de la cantidad (cobertura parcial):**

1.  InfoPonia reserva todo lo disponible.
2.  En el paso 9 devuelve la cantidad cubierta y la que quedó sin cubrir.

**5d. No hay stock maduro libre en los invernaderos considerados:**

1.  InfoPonia no crea ninguna reserva ni cosecha.
2.  Devuelve una cantidad cubierta de cero y toda la cantidad como sin cubrir.
3.  El caso de uso termina.

**8a. Al registrar, otra operación simultánea tomó parte del stock libre de una partida o de un lote elegido:**

1.  InfoPonia descarta la asignación calculada y la recalcula una sola vez, desde el paso 4, con el stock vigente y dentro de la misma transacción.
2.  Si el recálculo cubre toda la cantidad, el caso de uso continúa en el paso 6.
3.  Si no la cubre, InfoPonia reserva lo disponible y devuelve lo no cubierto, como en la extensión 5c. El caso de uso base decide.

**9a. El caso de uso base revierte su transacción (por ejemplo, porque no aceptó una cobertura parcial):**

1.  No queda nada de lo creado por este caso de uso y no se envía ningún aviso.
2.  Las alertas por invernadero sin Capataz activo generadas en la extensión 5a permanecen registradas.

**10a. InfoPonia no logra entregar una notificación:**

1.  Las reservas y las cosechas permanecen registradas.
2.  InfoPonia reintenta el envío.

**Ejecución desde cada caso de uso base**

**Desde COM-REG-CVT · Registrar Compra-venta (paso 15):**

  - Se ejecuta una vez por cada detalle de la venta. La cantidad es la cantidad solicitada y la fecha es la fecha pactada.
  - Si queda cantidad sin cubrir, el caso de uso base revierte el registro y aplica su extensión de stock insuficiente.
  - Si todas las reservas de la venta quedan “lista para entrega”, el caso de uso base dispara COM-PNF-ENT.

**Desde COM-PCT-SUM · Pactar Suministro (paso 14):**

  - Se ejecuta una vez por cada período de cada detalle que cae dentro de la ventana de pre-reserva, en orden de fecha. La cantidad es la cantidad por período y la fecha es la del período.
  - Si queda cantidad sin cubrir, el caso de uso base revierte el registro y aplica su extensión 14a.

**Desde PROD-CNC-CSC · Concretar Cosecha (extensión 13a):**

  - Se ejecuta para el mismo detalle de la orden concretada. La cantidad es la cantidad reservada en las líneas de lote menos su cantidad cubierta, y la fecha es la fecha de entrega de la reserva concretada.
  - Lo que queda sin cubrir sigue el camino de faltante del caso de uso base (13a.3).

**Desde PROD-REG-MRM · Registrar Merma (extensión 10c):**

  - Se ejecuta una vez por cada detalle afectado por el recorte de reservas de cámara. La cantidad es la recortada y la fecha es la fecha de entrega de la reserva recortada.
  - Lo que queda sin cubrir sigue el camino de faltante del caso de uso base (10c.4 y 10c.5).

**Desde Planificar Cosecha por Contrato (prevista):**

  - Se ejecuta por cada período de un detalle de suministro vigente que entra en la ventana de pre-reserva sin reserva. La cantidad es la cantidad por período y la fecha es la del período. El origen es un proceso automático.
  - Qué se hace con lo no cubierto se define en ese caso de uso.

**Desde Cancelar Orden (CU-11) (prevista):**

  - Se ejecuta al cancelar una orden de cosecha que cubre un contrato. La cantidad es la cubierta por la reserva liberada y la fecha es su fecha de entrega.
  - Qué se hace con lo no cubierto se define en ese caso de uso.

**Requisitos especiales**

  - Se ejecuta dentro de la transacción del caso de uso base, y su tiempo forma parte del tiempo de registro de ese caso de uso.
  - La alerta al Gerente por invernadero sin Capataz activo se registra en una transacción propia, para que permanezca aunque el caso de uso base se revierta, igual que la alerta «stock inconsistente» (regla 6 de 8.13).
  - El control de concurrencia sobre el stock libre de lotes y partidas impide la sobreasignación entre ventas, suministros, cosechas manuales y asignaciones automáticas simultáneas. El stock tomado queda bloqueado hasta que el caso de uso base confirma o revierte. Ante un conflicto, la asignación se recalcula una sola vez (extensión 8a).
  - Las notificaciones se envían después de que el caso de uso base confirma su transacción. Se presentan dentro del Sistema y pueden, además, enviarse por correo electrónico.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican el origen del caso de uso base: un usuario o un proceso automático.

**Reglas de negocio**

  - **Cantidad a reservar:** la menor entre la cantidad que indica el caso de uso base y la cantidad sin cubrir del detalle. Nunca se reserva más que lo sin cubrir. (Regla 10 de 8.8; paso 2 y extensión 2a)
  - **Invernaderos considerados:** en una compra-venta con retiro, solo el invernadero de retiro (R151). En una compra-venta con envío y en un suministro, los invernaderos del Vendedor del contrato (R115, R097). (Regla 7 de 8.6; paso 3 y extensiones 3a y 3b)
  - **Partida elegible:** una partida de cámara “disponible” de la variedad, en un invernadero considerado, con fecha límite igual o posterior a la fecha de entrega y con stock libre mayor que cero. Stock libre de una partida = cantidad disponible − Σ cantidad reservada de sus líneas cuya reserva está “activa” o “lista para entrega”. (Reglas 7 y 10 de 8.6; paso 4)
  - **Lote elegible:** un lote “activo” de la variedad, en la etapa “Maduración”, en un invernadero considerado que tiene Capataz activo (R149), con stock libre mayor que cero y cuya fecha máxima de cosecha no es anterior a la fecha programada que tendría su cosecha. Stock libre de un lote = cantidad actual − Σ cantidad reservada de sus líneas cuya reserva está “activa”. (Reglas 7, 9 y 11 de 8.6, las 7 y 11 modificadas en la ronda 20; regla 3 de 8.20, modificada en la ronda 20; paso 5 y extensión 5a)
  - **Orden de asignación:** primero las partidas, de la que vence antes a la que vence después. Después los lotes, del que entró antes en Maduración al que entró después y, como desempate, el de menor stock libre. Se aplica igual aunque el stock termine saliendo de varios invernaderos. (Regla 7 de 8.6; regla 2 de 8.20; pasos 4 y 5)
  - **Cosechas automáticas:** la fecha programada y la prioridad de cada orden de cosecha siguen la regla 3 de 8.11, con el parámetro de anticipación del contrato del detalle. Los casos de uso base citan esta regla a través de este caso de uso. (Paso 7)
  - **Una reserva por invernadero:** cada reserva toma todo su stock (cámara y lotes) de un único invernadero. Si el stock viene de varios, se crea una reserva por cada uno. (Regla 5 de 8.6; regla 1 de 8.8; paso 6 y extensión 5b)
  - **Una cosecha por reserva con lotes:** abarca una sola variedad y un solo invernadero, con uno o varios lotes, y su Capataz es el del invernadero (R149). Una reserva solo de cámara no tiene cosecha. (Regla 6 de 8.6; regla 2 de 8.8; paso 7 y extensión 4a)
  - **Estado inicial de la reserva:** “lista para entrega” si todas sus líneas son de cámara; “activa” si tiene al menos una línea de lote. (Regla 12 de 8.6; paso 6)
  - **Sin descuento de stock:** reservar no modifica la cantidad actual del lote ni la cantidad disponible de la partida. El lote baja recién al concretar la cosecha. (Regla 14 de 8.8)
  - **Cobertura parcial:** siempre se reserva lo disponible y se devuelve lo no cubierto, también después del recálculo por concurrencia. El caso de uso base decide si acepta la cobertura parcial o revierte. (Regla 15 de 8.6; extensiones 5c, 5d, 8a y 9a)
  - **Alerta por invernadero sin Capataz activo:** (Extensión 5a)
      
      - se genera si un invernadero considerado sin Capataz activo tenía lotes que podían asignarse;
      - es de tipo “invernadero sin Capataz activo”, está dirigida al Gerente y no tiene origen en el modelo (C5);
      - no se genera otra si ya hay una activa para ese invernadero;
      - se registra aunque el caso de uso base se revierta, con el criterio de la regla 6 de 8.13: el caso típico es una venta rechazada por falta de stock, y sin la alerta nadie sabría por qué faltó;
      - se resuelve, con su fecha de resolución, cuando el invernadero vuelve a tener un Capataz activo. La resuelve el caso de uso que asigna el Capataz (Modificación Invernadero o Baja Capataz, a especificar); este caso de uso solo la crea.
  - **Faltante y entrega:** el camino de faltante (pendiente de decisión del cliente, entrega con lo disponible) y la planificación de la entrega quedan a cargo del caso de uso base. (Reglas 16 y 17 de 8.6; “Ejecución desde cada caso de uso base”)
  - **Avisos:** cada orden de cosecha se notifica al Capataz y al Agrónomo del invernadero. No se avisa al Vendedor, y una reserva solo de cámara no genera aviso. (Regla 3 de 8.11; paso 10)

**Lista de tecnología y variaciones de datos**

  - **2–7.** Las cantidades se expresan en plantas, como números enteros.
  - **10.** La notificación al Capataz indica la orden de cosecha, la variedad, el invernadero, los lotes con la cantidad de cada uno y la fecha programada. La notificación al Agrónomo indica además el contrato, la fecha de entrega y que puede validar o modificar la cosecha.
  - **5a.** La alerta al Gerente indica el invernadero y la variedad cuyos lotes no se pudieron asignar.

**Frecuencia**

Una vez por cada detalle de compra-venta registrado, por cada período de suministro que se reserva y por cada faltante que se intenta cubrir.

**Temas abiertos**

  - Validar o Modificar Cosecha Automática (caso por especificar 3) debe permitir cambiar los lotes de la cosecha. Si no lo permite, el Agrónomo cancelaría la cosecha para cambiar lotes, y este caso de uso volvería a elegir el mismo lote por la regla 7 de 8.6.
  - Planificar Cosecha por Contrato y Cancelar Orden (CU-11) deben definir qué hacen con la cantidad que quede sin cubrir.
  - Con la regla 7 de 8.6 aplicada tal cual, un detalle puede tomar stock de varios invernaderos, con una cosecha y una entrega por cada uno. Conviene observarlo en el uso real.

## Cambios ya decididos que la próxima versión aplica (PCU, secciones 7 y 9)

1. **Lotes excluidos** (PCU 7; PROD-CNL-ORD, situación 6). «Desde Cancelar Orden» recibe los lotes de la cosecha cancelada y **no los
   considera**. `asignar` lo recibe como `lotes_excluidos` (vacío por defecto). COM-02 deja el parámetro y su prueba; lo usa COM-04.
2. **Detalle finalizado** (PCU 9; MD-131). Un detalle de suministro finalizado no reserva períodos posteriores a su fecha de fin. Es de
   suministros: lo programa COM-03 (en COM-02 no hay suministros).

Los dos «Inclusiones previstas» ya tienen nombre: Planificar Cosecha por Contrato es **PROD-PRR-SUM** (COM-03, PCU 12) y Cancelar Orden es
**PROD-CNL-ORD** (COM-04). Sus temas abiertos «qué hacen con lo no cubierto» los cierran esos casos de uso. El tema abierto de «Validar o
Modificar Cosecha Automática» lo cierra **PROD-MOD-CSC** (COM-04, PCU 11: permite cambiar el reparto entre lotes).

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57)

Lo que este caso de uso dice de una forma y el código del repo hace de otra está en `docs/patrones/stock_maduro.md`, sección 5. Resumen y
decisiones de aplicación:

1. **Una función, sin pantalla.** `comercial.servicios.stock_maduro.asignar(origen, detalle, cantidad, fecha_entrega, parametro,
   *, lotes_excluidos=())`. Corre **dentro** de la transacción del caso de uso base, que ya tomó los bloqueos del patrón (sección 3). Si
   la llama alguien sin transacción abierta, lanza `RuntimeError` (prueba con `transaction.get_autocommit()`).
2. **Precondiciones a, b y c**: las verifica `asignar` igual (lanza `ValueError`, no un error de negocio: es un error de programación del
   base). b, en COM-02: un `DetalleVenta` «abierto» de una `CompraVenta` «abierta».
3. **Paso 2 y extensión 2a** (regla 10 de 8.8): `cantidad_sin_cubrir(detalle)`. En COM-02 el detalle es nuevo, así que lo sin cubrir es toda
   la cantidad solicitada; la regla igual se programa completa (la usan COM-04 y COM-05) y se prueba con reservas de fábrica.
4. **Paso 3 y extensiones 3a y 3b** (regla 7 de 8.6): los invernaderos **activos** del Vendedor del contrato (`Invernadero.vendedor`,
   `estado_invernadero = activo`), o solo el de retiro. Un invernadero inactivo nunca se considera (regla 4 de PROD-BAJ-INV; cierra para
   esta ronda el disparador «Cuando exista un caso de uso que planifique… asigne stock»).
5. **Pasos 4 y 5** (reglas 7, 9 a 11 de 8.6; 2 y 3 de 8.20): las definiciones del patrón (sección 1). «Etapa Maduración» = la etapa actual
   del lote es de `TipoEtapa` con `codigo = "maduracion"` (nunca por el nombre). La fecha de entrada a Maduración y la fecha máxima de cosecha salen de
   `produccion.servicios.lotes` (`fecha_de_entrada_a_maduracion`, `fecha_maxima_de_cosecha`, PRD-02); la postcosecha de la variedad, de
   `inventario.servicios.variedades` (INV-03). **Nunca** se calculan a mano en `comercial`.
6. **Extensión 5a** (Capataz activo = el invernadero tiene `capataz` y su cuenta está activa). Los lotes de ese invernadero no se consideran;
   sus partidas, sí. La alerta **es la `sin_capataz` de `maestros`** (D-41, MAE-02a), que ya está activa mientras falte un Capataz activo:
   la crean y la resuelven el alta y la modificación del invernadero y la baja y la reactivación de la cuenta. `asignar` llama a
   `maestros.servicios.alertas.asegurar_alerta_de_estado(invernadero.id, "sin_capataz")` solo si ese invernadero tenía lotes que podían
   asignarse (idempotente: si ya está, no crea otra). **No hay transacción aparte**: la garantía «permanece aunque el base se revierta» se
   cumple porque la alerta ya existía antes de la venta (la mantiene `maestros`); si se revirtiera, era porque no faltaba. Prueba:
   `test_ext_5a_…` con la alerta ya activa (no se duplica) y con la venta revertida (la alerta sigue).
7. **Pasos 6 y 7, extensión 5b** (reglas 1 y 2 de 8.8; 5, 6 y 12 de 8.6; 3 de 8.11): sección 4 del patrón. La cosecha se crea con
   `produccion` (`Cosecha.objects.create` dentro de `comercial` está permitido porque el modelo es de nivel menor y los servicios de reserva
   viven en `comercial`, D-59); el número sale de la secuencia `produccion_orden_numero_seq` con la misma función que usa `produccion` para sus órdenes
   (D-52 punto 3; si PRD-01 la dejó privada, COM-02 la hace pública sin cambiarla), nunca con un `max()+1`.
8. **Paso 8 y auditoría (postcondición i).** `asignar` **no audita**: devuelve lo creado y el base lo pone como afectado en su único registro
   (D-36). Es lo que hace `cancelar_orden_incluida` en `produccion`. Postcondición i se cumple así: cada reserva, línea y cosecha queda en el
   registro del base con sus valores.
9. **Paso 10, extensión 10a y requisito de las notificaciones:** dentro de la transacción del base (D-42), una por cosecha al Capataz y otra
   al Agrónomo del invernadero (si hay uno activo). Sin reintento (no hay cola de envíos: «Notificaciones» de `docs/temas_abiertos.md`). Textos:
   - Capataz: «Nueva cosecha {OT-…}: {variedad}, {invernadero}. Lotes: {L-… (N plantas)}, … Fecha programada: {dd/mm/aaaa}.»
   - Agrónomo: el mismo texto más «Para {CV-…}, entrega el {dd/mm/aaaa}. Podés modificarla o cancelarla desde Órdenes de trabajo.» El
     enlace a la orden llega con COM-04 (hasta entonces, la notificación no tiene enlace).
10. **Extensión 8a:** no se programa (patrón, sección 3): con los lotes y las partidas bloqueados antes de leer sus reservas, el cálculo ya
    usa el stock vigente. Se prueba con la concurrencia mínima del patrón (sección 6).
11. **«Ejecución desde cada caso de uso base»**: en COM-02, solo «Desde COM-REG-CVT». El resto lo agregan COM-03 (Pactar Suministro, Modificar
    Suministro con un detalle nuevo y PROD-PRR-SUM, con un `Periodo`: `docs/patrones/stock_maduro.md`, sección 7) y COM-04 (Concretar Cosecha, Registrar Merma en cámara, Cancelar Orden); cada uno llama a `asignar` con su parámetro de
    anticipación (`compra_venta` o `suministro`) y decide qué hace con lo no cubierto.
12. **Lo que `produccion` ve de la cosecha** (D-59): la cuenta en `ordenes_del_capataz` (traspaso del Capataz y aviso de baja de su cuenta),
    en los impedimentos que ya cuentan órdenes «a realizar» (baja del invernadero, baja de la variedad) y, por
    `registrar_reservado_de_lote`, en la condición 1 de la alerta de plantas comprometidas (regla 15 de 8.8). La bandeja del Capataz y la
    lista del Agrónomo **no** muestran cosechas hasta COM-04.

## Para más adelante

- COM-03: suministros (detalles, períodos, PCU 9) y COM-PCT-SUM, COM-MOD-SUM y PROD-PRR-SUM como bases (lote C3).
- COM-04: bases Concretar Cosecha (13a), Registrar Merma en cámara (10c) y Cancelar Orden (con `lotes_excluidos`); bandeja y lista con
  cosechas, y el enlace de la notificación.
- Tema abierto del caso de uso que queda: «un detalle puede tomar stock de varios invernaderos… conviene observarlo en el uso real». No es
  una tarea: queda en `docs/temas_abiertos.md`.
